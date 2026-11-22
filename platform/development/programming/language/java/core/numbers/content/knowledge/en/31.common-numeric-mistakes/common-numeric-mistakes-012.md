# Sai lầm: định dạng rồi parse lại để thực hiện làm tròn tính toán

## 1. Vấn đề cốt lõi

Một anti-pattern trong Java là **format số thành chuỗi với N chữ số thập phân, parse lại chuỗi đó thành số, rồi dùng kết quả để tính toán tiếp**. Ví dụ:

~~~java
// Chỉ là đoạn minh họa, không phải chương trình độc lập.
String text = String.format(java.util.Locale.US, "%.2f", amount);
double rounded = Double.parseDouble(text);
~~~

Cách làm này có vẻ giống việc làm tròn nhưng đã trộn ba nhiệm vụ: **trình bày**, **đọc chuỗi**, **biến đổi số học**. Chuỗi hiển thị có thể chứa dấu nhóm hàng nghìn, dấu thập phân theo locale, ký hiệu tiền tệ, số 0 thêm vào, hoặc chữ số đã bị loại. Parse lại còn phụ thuộc loại parser và trạng thái cấu hình, có thể trả số kiểu `double` với sai số nhị phân.

Nếu nghiệp vụ cần làm tròn giá trị BigDecimal, dùng **`setScale(scale, RoundingMode)`** hoặc **`round(MathContext)`**; nếu cần làm tròn thương, dùng overload `divide` có scale/MathContext và rounding mode. Chỉ format sau khi đã xác định giá trị cần trình bày. Nếu nghiệp vụ cần giữ giá trị nguyên gốc, format bản gốc để hiển thị và không dùng chuỗi đó tính toán ngược lại.

## 2. Ba thao tác có mục đích khác nhau

| Thao tác | Mục tiêu | Ví dụ | Đặc điểm |
| --- | --- | --- | --- |
| **Format** | Hiển thị số cho người dùng | `NumberFormat.format(value)` | Có locale, grouping, ký hiệu tiền, số 0 và có thể làm tròn chuỗi |
| **Parse** | Đọc văn bản vào dạng số | `DecimalFormat.parse(text)` | Phụ thuộc cú pháp/locale, có thể chấp nhận tiền tố hợp lệ |
| **Round** | Áp dụng quy tắc số học lên giá trị | `value.setScale(2, HALF_EVEN)` | Không cần chuyển sang String, chính sách rõ ràng |

Ví dụ số chính xác `1234.567` có thể được formatter US hiển thị là `1,234.57`. Phần nghìn đã bị bỏ: parse ngược lại **không thể tái tạo `1234.567`**. Format là thao tác ở ranh giới hiển thị; không tự xác lập chính sách làm tròn cho toàn bộ phép tính.

`BigDecimal` là immutable: `setScale`, `round` và các phép cộng/trừ/nhân trả kết quả BigDecimal mà không sửa đối tượng gốc. Locale cũng không phải thuộc tính của BigDecimal. Số được tính nên có ý nghĩa nhất quán trước khi hiển thị theo US, Đức hay Việt Nam.

## 3. Minh họa anti-pattern: mất precision dù parse thành công

Đoạn chương trình sau cố ý làm format→parse để chứng minh dữ liệu bị đổi. Pattern `#,##0.00` của US thêm dấu nhóm và giữ đúng hai chữ số lẻ. Parser được cấu hình trả BigDecimal để không phát sinh thêm sai số `double`, nhưng **chữ số đã mất tại bước format vẫn không quay lại**.

Lưu thành `FormatParseTrapDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FormatParseTrapDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.567");

        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        String shown = format.format(original);
        ParsePosition position = new ParsePosition(0);
        BigDecimal parsed = (BigDecimal) format.parse(shown, position);

        System.out.println("original = " + original.toPlainString());
        System.out.println("formatted = " + shown);
        System.out.println("parsed = " + parsed.toPlainString());
        System.out.println("fully parsed = "
                + (position.getIndex() == shown.length()));
        System.out.println("same value = "
                + (original.compareTo(parsed) == 0));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac FormatParseTrapDemo.java
java FormatParseTrapDemo
~~~

Kết quả:

~~~text
original = 1234.567
formatted = 1,234.57
parsed = 1234.57
fully parsed = true
same value = false
~~~

Parser tiêu thụ hết chuỗi và trả BigDecimal, nhưng giá trị đã bị làm tròn theo yêu cầu **hiển thị**. Nếu đem `parsed` cộng vào báo cáo, tính phí hoặc làm tròn lần nữa, chương trình đã thay đổi đầu vào cho các phép tính tiếp theo mà không có chính sách số học rõ ràng.

Ngoài ra, `new BigDecimal("1,234.57")` sẽ ném `NumberFormatException`, vì constructor BigDecimal không hiểu dấu nhóm theo locale. Vì vậy chuỗi định dạng để hiển thị không phải chuỗi decimal chuẩn để lưu hoặc parse bằng constructor.

## 4. Locale: cùng chuỗi có thể có nghĩa khác

Dấu thập phân và dấu nhóm phụ thuộc locale. `1,234` thường biểu thị một nghìn hai trăm ba mươi bốn theo US, còn theo Germany lại là một phẩy hai ba bốn. Đức thường hiển thị `1234.57` dưới dạng `1.234,57`.

Các locale có thể dùng khoảng trắng Unicode, ký tự số khác, hoặc cách hiển thị tiền tệ riêng. Đừng dùng `replace(",", ".")` một cách máy móc, vì có thể biến dấu nhóm thành dấu thập phân. Không format theo `Locale.getDefault()` rồi parse bằng một locale khác; cấu hình hệ điều hành và JVM có thể thay đổi giữa máy phát triển và triển khai.

### Ví dụ Java 17: hai giá trị từ cùng một chuỗi

Lưu thành `LocaleNumberDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberDemo {
    static BigDecimal parseEntire(String text, Locale locale)
            throws ParseException {
        NumberFormat nf = NumberFormat.getNumberInstance(locale);
        if (!(nf instanceof DecimalFormat df)) {
            throw new IllegalStateException("DecimalFormat unavailable");
        }
        df.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number parsed = df.parse(text, pos);

        if (!(parsed instanceof BigDecimal result)
                || pos.getIndex() != text.length()) {
            throw new ParseException("Invalid decimal",
                    Math.max(0, pos.getIndex()));
        }
        return result;
    }

    public static void main(String[] args) throws ParseException {
        String input = "1,234";
        System.out.println("US = " + parseEntire(input, Locale.US));
        System.out.println("DE = " + parseEntire(input, Locale.GERMANY));
    }
}
~~~

~~~bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
~~~

Kết quả với dữ liệu locale chuẩn của JDK 17:

~~~text
US = 1234
DE = 1.234
~~~

`NumberFormat.parse` có thể trả `Long` hoặc `Double` theo cấu hình mặc định; không cast thẳng về BigDecimal nếu chưa bật `DecimalFormat.setParseBigDecimal(true)` và kiểm tra kiểu. `DecimalFormat` vẫn có thể parse tương đối dễ dãi, nhất là dấu nhóm. Kiểm tra `ParsePosition.getIndex() == text.length()` chỉ xác nhận đã tiêu thụ toàn chuỗi, **không xác thực cấu trúc grouping nghiêm ngặt**. Nếu giao diện yêu cầu cú pháp chặt chẽ, phải có validation bổ sung phù hợp locale. Java 17 chưa có API `DecimalFormat.setStrict`.

Đặc biệt, BigDecimal không biểu diễn `NaN` hoặc vô cực; luôn kiểm tra kết quả parse và xử lý input ngoại lệ theo hợp đồng dữ liệu.

## 5. Dùng setScale để làm tròn số học

Khi yêu cầu là **làm tròn về hai chữ số thập phân**, thao tác đúng:

~~~java
// Ví dụ minh họa; value cần được khai báo trước.
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

`setScale(2, ...)` giữ đúng hai chữ số sau dấu thập phân. Khi giảm scale làm mất chữ số có giá trị, Java dùng chế độ làm tròn được truyền vào. Nếu tăng scale, nó bổ sung số 0 mà không làm đổi giá trị toán học.

Các chế độ:

| RoundingMode | Ý nghĩa |
| --- | --- |
| `HALF_UP` | Chọn gần nhất; nếu hòa thì xa 0 |
| `HALF_DOWN` | Chọn gần nhất; nếu hòa thì gần 0 |
| `HALF_EVEN` | Chọn gần nhất; nếu hòa thì chữ số cuối giữ lại chẵn |
| `UP` | Xa 0 mỗi khi phần bỏ khác 0 |
| `DOWN` | Về 0 mỗi khi phần bỏ khác 0 |
| `CEILING` | Hướng dương vô cực |
| `FLOOR` | Hướng âm vô cực |
| `UNNECESSARY` | Cấm bỏ phần có giá trị; cần làm tròn thì ném `ArithmeticException` |

Chọn chế độ theo yêu cầu nghiệp vụ; `UP` không đồng nghĩa `HALF_UP`. Đối với số âm, `CEILING` và `FLOOR` không giống quy tắc gần hoặc xa zero. Trong tiền tệ, thuế và hóa đơn, chính sách làm tròn nên được ghi rõ, không phụ thuộc mặc định của formatter.

### Ví dụ Java 17: round rồi format

Lưu thành `RoundThenFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class RoundThenFormatDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.567");
        BigDecimal rounded = original.setScale(
                2, RoundingMode.HALF_UP);

        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setGroupingUsed(true);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println("original = " + original.toPlainString());
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("display = " + formatter.format(rounded));
        System.out.println("source remains = " + original.toPlainString());
    }
}
~~~

~~~bash
javac RoundThenFormatDemo.java
java RoundThenFormatDemo
~~~

Kết quả:

~~~text
original = 1234.567
rounded = 1234.57
display = 1,234.57
source remains = 1234.567
~~~

Nếu nghiệp vụ thật sự yêu cầu giá trị hai chữ số lẻ, tiếp tục tính bằng `rounded`. Nếu chỉ muốn giao diện **hiển thị** hai chữ số trong khi phép tính vẫn phải giữ `1234.567`, tiếp tục dùng `original` và chỉ format khi xuất giao diện. Việc chọn bên nào không được do formatter tự quyết định.

## 6. MathContext: precision không phải scale

Một nguồn hiểu lầm nữa là `MathContext`. `setScale(2, HALF_EVEN)` giữ hai chữ số **sau dấu thập phân**; `round(new MathContext(4, HALF_EVEN))` giữ tối đa bốn chữ số **có nghĩa**.

Ví dụ với `123.45`:

- `setScale(2, HALF_EVEN)` ⇒ `123.45`.
- `round(MathContext(4, HALF_EVEN))` ⇒ `123.4`.

### Ví dụ Java 17: hai khái niệm khác nhau

Lưu thành `ScalePrecisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class ScalePrecisionDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("123.45");
        System.out.println("source = " + x);
        System.out.println("scale 2 = " + x.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("precision 4 = " + x.round(
                new MathContext(4, RoundingMode.HALF_EVEN)));
    }
}
~~~

~~~bash
javac ScalePrecisionDemo.java
java ScalePrecisionDemo
~~~

Kết quả:

~~~text
source = 123.45
scale 2 = 123.45
precision 4 = 123.4
~~~

Nếu phép chia decimal là vô hạn, như `1/3`, `BigDecimal.divide(divisor)` chính xác có thể ném `ArithmeticException`. Dùng `divide(divisor, 2, RoundingMode.HALF_UP)` cho hai chữ số lẻ hoặc `divide(divisor, MathContext)` cho precision có nghĩa. **Không format rồi parse thương** để né yêu cầu phải chọn chế độ làm tròn.

## 7. Parse về double tái xuất sai số nhị phân

`double` là số nhị phân có số bit hữu hạn. Nhiều số thập phân như `0.1` không được biểu diễn hoàn toàn chính xác. Vì thế định dạng chuỗi hai số lẻ rồi `Double.parseDouble` **không tạo một số thập phân chính xác có hai số lẻ**. Nó tạo giá trị nhị phân gần nhất có thể tiếp tục sinh sai số khi cộng nhân.

Ngay cả phép chuyển BigDecimal từ double cũng có bẫy: `new BigDecimal(2.675)` biểu diễn chính xác giá trị double đã nhận, vốn hơi nhỏ hơn số thập phân lý tưởng 2.675. `new BigDecimal("2.675")` biểu diễn chính xác số decimal 2.675.

### Ví dụ Java 17: sai khác ở ranh giới làm tròn

Lưu thành `DoubleSourceTrapDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DoubleSourceTrapDemo {
    public static void main(String[] args) {
        BigDecimal decimal = new BigDecimal("2.675");
        BigDecimal binary = new BigDecimal(2.675);

        System.out.println("decimal = " + decimal.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("from double = " + binary.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("double sum = " + (0.1 + 0.2));
    }
}
~~~

~~~bash
javac DoubleSourceTrapDemo.java
java DoubleSourceTrapDemo
~~~

Kết quả:

~~~text
decimal = 2.68
from double = 2.67
double sum = 0.30000000000000004
~~~

Giá trị decimal đúng 2.675 nằm giữa 2.67 và 2.68; HALF_EVEN chọn chữ số cuối 8 chẵn. Giá trị xuất phát từ double hơi nhỏ hơn điểm giữa nên làm tròn về 2.67. `BigDecimal.valueOf(double)` dùng biểu diễn chuỗi chuẩn của double và có thể là lựa chọn tốt hơn `new BigDecimal(double)` khi buộc phải nhận double, nhưng **không phục hồi** precision đã mất ở những phép tính trước đó.

## 8. Format rồi parse có thể thay đổi scale mà không thay đổi giá trị

BigDecimal lưu cả giá trị và scale. `2.0` có scale 1, trong khi `2.00` có scale 2. Hai số bằng nhau về giá trị theo `compareTo`, nhưng khác nhau theo `equals`. Formatter có thể thêm số 0 cuối do `minimumFractionDigits` hoặc bỏ chữ số/zero do `maximumFractionDigits`, nên round-trip có thể làm thay đổi scale ngay cả khi không làm thay đổi giá trị toán học.

### Ví dụ Java 17: hai giá trị numeric bằng nhau nhưng equals khác

Lưu thành `FormatScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FormatScaleDemo {
    public static void main(String[] args) {
        BigDecimal source = new BigDecimal("2.0");
        DecimalFormat formatter = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setParseBigDecimal(true);

        String text = formatter.format(source);
        BigDecimal parsed = (BigDecimal) formatter.parse(
                text, new ParsePosition(0));

        System.out.println("source = " + source);
        System.out.println("display = " + text);
        System.out.println("parsed = " + parsed);
        System.out.println("source scale = " + source.scale());
        System.out.println("parsed scale = " + parsed.scale());
        System.out.println("numeric equal = "
                + (source.compareTo(parsed) == 0));
        System.out.println("equals = " + source.equals(parsed));
    }
}
~~~

~~~bash
javac FormatScaleDemo.java
java FormatScaleDemo
~~~

Kết quả:

~~~text
source = 2.0
display = 2.00
parsed = 2.00
source scale = 1
parsed scale = 2
numeric equal = true
equals = false
~~~

Nếu muốn cố ý chuẩn hóa scale thành 2, dùng `source.setScale(2, roundingMode)`. Việc đổi scale có thể ảnh hưởng `equals/hashCode` và những khóa BigDecimal trong `HashMap`, nên đây là quyết định dữ liệu chứ không phải mẹo format vô hại.

## 9. Làm tròn vào thời điểm nào?

Làm tròn **từng dòng** rồi cộng có thể khác cộng **giá trị chính xác** rồi làm tròn một lần ở cuối. Giả sử ba giá trị `1.005` và dùng HALF_EVEN để giữ hai chữ số lẻ:

- Mỗi giá trị làm tròn trước: `1.00`, tổng `3.00`.
- Tổng chính xác: `3.015`, làm tròn sau: `3.02`.

### Ví dụ Java 17: hai chính sách tính tổng

Lưu thành `RoundingStageDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingStageDemo {
    public static void main(String[] args) {
        BigDecimal[] entries = {
            new BigDecimal("1.005"),
            new BigDecimal("1.005"),
            new BigDecimal("1.005")
        };
        BigDecimal exact = BigDecimal.ZERO;
        BigDecimal sumOfRounded = BigDecimal.ZERO;

        for (BigDecimal x : entries) {
            exact = exact.add(x);
            sumOfRounded = sumOfRounded.add(
                    x.setScale(2, RoundingMode.HALF_EVEN));
        }

        System.out.println("exact total = " + exact);
        System.out.println("sum rounded lines = " + sumOfRounded);
        System.out.println("round after sum = " + exact.setScale(
                2, RoundingMode.HALF_EVEN));
    }
}
~~~

~~~bash
javac RoundingStageDemo.java
java RoundingStageDemo
~~~

Kết quả:

~~~text
exact total = 3.015
sum rounded lines = 3.00
round after sum = 3.02
~~~

Cả hai phép làm tròn đều tuân theo HALF_EVEN. Khác biệt đến từ **thời điểm** áp dụng. Trong tiền tệ, thuế, hóa đơn, báo cáo, phải xác định nghiệp vụ yêu cầu làm tròn từng khoản, từng giao dịch hay tổng. Không để hành vi hiển thị hai chữ số lẻ làm thay đổi dữ liệu tính toán trung gian một cách âm thầm.

## 10. Khi nào phải từ chối thay vì làm tròn?

Đôi khi quy định không cho phép làm tròn tự động; dữ liệu vượt quá số chữ số lẻ có giá trị phải bị từ chối. `RoundingMode.UNNECESSARY` hỗ trợ xác minh BigDecimal có thể chuyển về scale mong muốn **mà không mất thông tin số học** hay không.

### Ví dụ Java 17: kiểm tra cents chính xác

Lưu thành `RequireExactScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RequireExactScaleDemo {
    static BigDecimal requireCents(BigDecimal value) {
        return value.setScale(2, RoundingMode.UNNECESSARY);
    }

    public static void main(String[] args) {
        System.out.println(requireCents(new BigDecimal("12.5")));
        System.out.println(requireCents(new BigDecimal("12.5000")));

        try {
            System.out.println(requireCents(new BigDecimal("12.345")));
        } catch (ArithmeticException ex) {
            System.out.println("Rejected: rounding required");
        }
    }
}
~~~

~~~bash
javac RequireExactScaleDemo.java
java RequireExactScaleDemo
~~~

Kết quả:

~~~text
12.50
12.50
Rejected: rounding required
~~~

`12.5000` có bốn chữ số lẻ trong **chuỗi đầu vào**, nhưng giá trị có thể chuyển chính xác thành `12.50` vì phần bỏ chỉ gồm số 0. Nếu yêu cầu cấm cả input có hơn hai chữ số lẻ, kể cả zero, phải kiểm tra **cú pháp đầu vào**, không chỉ kiểm tra khả năng biểu diễn số học.

## 11. Luồng dữ liệu rõ ràng cho ứng dụng

Một luồng xử lý thập phân đáng tin nên tách biệt các bước:

1. **Xác định kiểu đầu vào:** chuỗi decimal chuẩn của máy hay chuỗi người dùng theo locale? Với input locale, dùng parser theo đúng locale và kiểm tra toàn chuỗi cùng các quy tắc được phép.
2. **Giữ giá trị số trong BigDecimal** nếu nghiệp vụ cần decimal chính xác. Tránh trung gian double hoặc chuỗi đã format để trình bày.
3. **Kiểm tra ràng buộc** min/max, dấu âm, precision, scale, mã tiền tệ và yêu cầu từ chối hay làm tròn.
4. **Tính toán trên số gốc** bằng API BigDecimal. Nếu phép tính đòi MathContext hoặc RoundingMode, cung cấp chính sách tường minh.
5. **Làm tròn ở đúng ranh giới nghiệp vụ** bằng setScale hoặc MathContext, không bị điều khiển bởi formatter.
6. **Chỉ format tại ranh giới đầu ra** theo locale và yêu cầu giao diện. Lưu/trao đổi bằng dạng decimal machine-readable có hợp đồng rõ ràng.

`NumberFormat` và `DecimalFormat` có trạng thái mutable, không mặc định thread-safe. Không chia sẻ cùng một instance formatter mutable giữa nhiều luồng mà thiếu đồng bộ phù hợp. Với phần tính toán, tránh lệ thuộc `Locale.getDefault()` khi kết quả phải nhất quán trên nhiều máy.

## 12. Sai lầm thường gặp

1. **Format→parse làm tròn số học:** biến logic tính toán thành logic trình bày.
2. **Parse bằng BigDecimal(String) chuỗi có grouping:** `"1,234.57"` không phải literal decimal hợp lệ.
3. **Format và parse ở locale khác nhau:** dấu phẩy/chấm có thể được hiểu ngược, parse sai hoặc thất bại.
4. **Cast NumberFormat.parse sang BigDecimal trực tiếp:** chưa có `setParseBigDecimal(true)` có thể nhận Long/Double.
5. **Cho rằng parse thành công nghĩa là chuỗi hợp lệ hoàn toàn:** parser có thể chỉ đọc tiền tố hoặc chấp nhận grouping lỏng; dùng ParsePosition và validation.
6. **Dùng double sau khi format BigDecimal:** vẫn còn xấp xỉ nhị phân; có thể làm mất precision.
7. **Nhầm format tối đa 2 chữ số lẻ với setScale(2):** cái đầu điều khiển chuỗi, cái sau tạo kết quả số học.
8. **Nhầm precision và scale:** MathContext đếm chữ số có nghĩa; setScale đếm chữ số sau dấu thập phân.
9. **Không truyền RoundingMode:** phụ thuộc mặc định hoặc có thể gặp ArithmeticException.
10. **Round-trip làm đổi scale:** `2.0` và `2.00` khác nhau theo equals/hashCode.
11. **Làm tròn từng bước theo yêu cầu UI:** có thể đổi tổng hoặc công thức nghiệp vụ.
12. **Dùng UNNECESSARY để kiểm tra số chữ số người dùng gõ:** nó chỉ kiểm tra không mất giá trị, không kiểm tra số zero ở cuối văn bản.
13. **Dùng formatter static chung trong xử lý song song:** DecimalFormat không thread-safe.
14. **Lưu chuỗi định dạng cho người đọc vào API/database làm số:** phụ thuộc locale và có thể mất thông tin.

## 13. Bài tập tự kiểm tra

**Câu 1.** `1234.567` format thành `"1,234.57"` rồi parse có còn bằng giá trị nguồn không?

**Đáp án:** Không. Chữ số hàng phần nghìn đã bị loại ở bước format; giá trị parse là `1234.57`.

**Câu 2.** Muốn làm tròn `1234.567` đến hai chữ số lẻ theo HALF_UP phải làm gì?

**Đáp án:** `new BigDecimal("1234.567").setScale(2, RoundingMode.HALF_UP)` cho `1234.57`. Không cần chuỗi trung gian và độc lập locale.

**Câu 3.** Vì sao `"1,234"` có hai cách hiểu?

**Đáp án:** US thường dùng dấu phẩy cho grouping ⇒ 1234; Germany dùng dấu phẩy làm decimal ⇒ 1.234.

**Câu 4.** Tại sao `2.0` format thành `2.00` rồi parse BigDecimal có thể làm `equals` false?

**Đáp án:** Source có scale 1, parse được scale 2; `compareTo` vẫn coi bằng về giá trị.

**Câu 5.** Ba giá trị `1.005` làm tròn từng khoản cho tổng nào, và nếu cộng trước thì cho tổng nào?

**Đáp án:** HALF_EVEN scale 2: tổng từng khoản đã làm tròn là `3.00`, cộng chính xác rồi làm tròn là `3.02`.

**Câu 6.** Vì sao `12.5000.setScale(2, UNNECESSARY)` không bị từ chối?

**Đáp án:** Chỉ bỏ zero nên không mất giá trị. Nếu muốn cấm nhập hơn hai chữ số lẻ phải kiểm tra chuỗi input.

## 14. Ghi nhớ

- **Format là trình bày; parse là đọc văn bản; round là biến đổi số học.** Không nên format rồi parse lại chỉ để làm tròn cho phép tính.
- Dùng `BigDecimal.setScale` cho số chữ số thập phân, `MathContext` cho chữ số có nghĩa và overload `divide` cho thương cần làm tròn.
- Luôn xác định `RoundingMode` và **thời điểm làm tròn** theo nghiệp vụ, độc lập locale giao diện.
- Giữ BigDecimal gốc nếu cần precision đầy đủ; format ở bước xuất, parse đúng một lần khi nhận đầu vào.
- Cẩn thận với `double`, grouping, parser nhận một phần chuỗi, thay đổi scale và formatter dùng chung đa luồng.

Tham khảo Java SE 17 API: `java.math.BigDecimal`, `java.math.MathContext`, `java.math.RoundingMode`, `java.text.DecimalFormat`, `java.text.NumberFormat` và `java.text.ParsePosition`.