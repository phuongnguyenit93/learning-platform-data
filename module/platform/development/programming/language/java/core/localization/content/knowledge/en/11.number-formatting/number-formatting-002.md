# Định dạng phần trăm và quan hệ với giá trị gốc trong Java

## 1. Bản chất: tỷ lệ được lưu khác với chuỗi phần trăm được hiển thị

Một tỷ lệ (*ratio*, *rate*, *proportion*) thường được lưu trong chương trình dưới dạng **giá trị số gốc**. Khi biểu diễn nó dưới dạng phần trăm, quy ước toán học là:

\[
\text{phần trăm hiển thị} = \text{giá trị tỷ lệ gốc} \times 100
\]

Vì thế, **`0.125` tương đương `12.5%`**, không phải `0.125%`. Dấu phần trăm biểu thị đơn vị “trên một trăm”.

| Giá trị gốc (ratio) | Giá trị theo đơn vị % | Chuỗi phần trăm ví dụ |
| ---: | ---: | --- |
| `0` | 0 | `0%` |
| `0.025` | 2.5 | `2.5%` |
| `0.125` | 12.5 | `12.5%` |
| `0.5` | 50 | `50%` |
| `1` | 100 | `100%` |
| `1.25` | 125 | `125%` |
| `-0.075` | -7.5 | `-7.5%` |

**Hai điều không được nhầm:**

1. **Giá trị gốc** trong phép tính vẫn là `0.125`. Khi format phần trăm, Java tạo **chuỗi** biểu diễn `12.5%`; nó không sửa giá trị biến gốc.
2. `12.5`, nếu được đưa như *ratio* cho bộ định dạng phần trăm, nghĩa là **1.250%**, không phải **12.5%**. Muốn hiển thị 12.5%, hãy đưa vào `0.125`.

Một tỷ lệ không nhất thiết luôn nằm trong khoảng 0–1. Với tỷ lệ sử dụng tài nguyên, mức tăng trưởng hoặc phần trăm chênh lệch, giá trị có thể âm hoặc lớn hơn 1. Giới hạn phạm vi là quy tắc nghiệp vụ, **không phải đặc tính bắt buộc của bộ định dạng**.

## 2. `NumberFormat.getPercentInstance(Locale)` làm gì?

Java có API chuyên dùng cho phần trăm trong `java.text.NumberFormat`:

~~~java
NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
String text = percent.format(0.125);
~~~

Đây là **đoạn mã minh họa trong method**, cần import `java.text.NumberFormat` và `java.util.Locale`.

Bộ định dạng phần trăm đảm nhận hai việc chính:

- **Quy đổi đơn vị biểu diễn:** nhân giá trị ratio với 100 khi format.
- **Áp dụng quy ước của locale:** dấu thập phân, dấu nhóm, vị trí và khoảng cách quanh ký hiệu phần trăm cùng chữ số phù hợp dữ liệu locale/provider.

Khi phân tích ngược bằng `parse` của bộ định dạng phần trăm, kết quả lại được **chia cho 100**. Ví dụ, chuỗi `"12.5%"` trong locale `en-US` tương ứng tỷ lệ `0.125`.

### Vì sao cần truyền `Locale` tường minh?

~~~java
NumberFormat us = NumberFormat.getPercentInstance(Locale.US);
NumberFormat de = NumberFormat.getPercentInstance(Locale.GERMANY);
~~~

Cùng một tỷ lệ có thể được hiển thị như:

| Locale | Minh họa với ratio `0.125` (một chữ số phần thập phân) |
| --- | --- |
| `Locale.US` | `12.5%` |
| `Locale.GERMANY` | `12,5 %` — thường có khoảng trắng không ngắt trước `%` |

Khoảng cách trước `%` tại locale Đức có thể là ký tự **NBSP** (`U+00A0`), trông giống dấu cách thông thường nhưng không phải ASCII space. Dữ liệu locale có thể được cập nhật giữa các JDK/provider. Đừng tự nối `"%”` hay thay `"."` bằng `","` để mô phỏng locale; nên dùng API chuyên dụng và kiểm thử trong môi trường triển khai.

**Lưu ý:** Nếu gọi `NumberFormat.getPercentInstance()` **không truyền locale**, API dùng locale mặc định theo ngữ cảnh FORMAT của JVM. Trong ứng dụng nhiều người dùng, nên truyền locale nhận từ hồ sơ/yêu cầu của người xem thay vì trông đợi cấu hình máy chủ là đúng.

## 3. Ví dụ Java 17+ hoàn chỉnh: ratio và cách hiển thị phần trăm

Tạo tệp `PercentFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class PercentFormatDemo {
    public static void main(String[] args) {
        BigDecimal ratio = new BigDecimal("0.125");

        NumberFormat percent =
                NumberFormat.getPercentInstance(Locale.US);
        percent.setMinimumFractionDigits(1);
        percent.setMaximumFractionDigits(1);
        percent.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("Original ratio: "
                + ratio.toPlainString());
        System.out.println("Shown as percent: "
                + percent.format(ratio));
        System.out.println("Whole ratio: "
                + percent.format(BigDecimal.ONE));
        System.out.println("Negative ratio: "
                + percent.format(new BigDecimal("-0.075")));
        System.out.println("Wrong input: "
                + percent.format(new BigDecimal("12.5")));
        System.out.println("Ratio after formatting: "
                + ratio.toPlainString());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PercentFormatDemo.java
java PercentFormatDemo
~~~

Đầu ra trong JDK hỗ trợ locale `en-US`:

~~~text
Original ratio: 0.125
Shown as percent: 12.5%
Whole ratio: 100.0%
Negative ratio: -7.5%
Wrong input: 1,250.0%
Ratio after formatting: 0.125
~~~

### Đọc kết quả

- Dòng 1 và dòng cuối đều là `0.125`: định dạng **không làm thay đổi** đối tượng `BigDecimal` đầu vào.
- `percent.format(ratio)` nhân tỷ lệ với 100 về mặt định dạng và thêm ký hiệu phần trăm; `0.125 → 12.5%`.
- `BigDecimal.ONE` tức `1`, nên là `100.0%`.
- Giá trị âm `-0.075` hiển thị `-7.5%`. Tương tự, ratio lớn hơn 1 có thể hiển thị lớn hơn 100%.
- `new BigDecimal("12.5")` là tỷ lệ 12.5, tức `1250%`. Chữ số phân nhóm tạo ra `1,250.0%` theo `Locale.US`.

**Quy tắc thiết kế API:** Hãy chọn một hợp đồng dữ liệu nhất quán. Ví dụ, trường `conversionRate` luôn lưu tỷ lệ `0.125`, còn UI hiển thị `12.5%`. Nếu hệ thống khác gửi giá trị “12.5” với ý nghĩa **đơn vị phần trăm**, cần đổi sang ratio bằng phép chia 100 ở ranh giới dữ liệu, không đưa thẳng vào `getPercentInstance`.

## 4. Fraction digits và rounding: phần thập phân của phần trăm, không phải của ratio

Factory `getPercentInstance` có cấu hình số chữ số thập phân tùy locale/provider. Đặc biệt, trong nhiều cấu hình thông dụng, formatter mặc định **không hiển thị chữ số thập phân cho phần trăm**. Điều đó có thể làm tỷ lệ `0.125` hiện thành một số nguyên phần trăm đã được làm tròn.

Muốn hiển thị 1 hoặc 2 chữ số thập phân theo yêu cầu sản phẩm, hãy đặt rõ:

~~~java
NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
percent.setMinimumFractionDigits(2);
percent.setMaximumFractionDigits(2);
percent.setRoundingMode(RoundingMode.HALF_UP);
~~~

Đây là **mảnh mã trong method**, cần import `java.text.NumberFormat`, `java.util.Locale`, `java.math.RoundingMode`.

- `setMinimumFractionDigits(2)`: ít nhất hai chữ số sau dấu thập phân **ở kết quả phần trăm**. Ví dụ 12.5% thành `12.50%`.
- `setMaximumFractionDigits(2)`: không hiển thị quá hai chữ số thập phân, làm tròn khi cần.
- `setRoundingMode(...)`: quyết định quy tắc làm tròn như `HALF_UP`, `HALF_EVEN`… khi implementation hỗ trợ.
- Các lựa chọn trên chi phối **chuỗi hiển thị**, không đổi tỷ lệ số gốc.

Ví dụ minh họa:

| Ratio | Phần trăm trước khi giới hạn precision | Hiển thị hai chữ số, `HALF_UP` |
| --- | --- | --- |
| `0.125` | 12.5% | `12.50%` |
| `0.12495` | 12.495% | `12.50%` |
| `0.1234` | 12.34% | `12.34%` |
| `0.1` | 10% | `10.00%` |

Cùng một giá trị gốc có thể hiển thị khác nhau khi đổi precision hoặc rounding mode. Chẳng hạn, tỷ lệ `0.12495` tương đương `12.495%`, nếu hiển thị hai chữ số với `HALF_UP` thì là `12.50%`. Nhưng **giá trị gốc vẫn là `0.12495`**; đừng ghi đè chuỗi hiển thị đã làm tròn về cơ sở dữ liệu rồi nghĩ rằng đã bảo toàn độ chính xác.

### Vì sao nên dùng BigDecimal với tiền và tỷ lệ nghiệp vụ?

`double` là số dấu chấm động nhị phân; nhiều phân số thập phân (ví dụ `0.1`) không có biểu diễn nhị phân chính xác. Với tỷ lệ tài chính hoặc phép tính cần kiểm soát rounding, hãy cân nhắc:

~~~java
BigDecimal ratio = new BigDecimal("0.12495");
BigDecimal percentage = ratio.multiply(BigDecimal.valueOf(100));
BigDecimal shown = percentage.setScale(2, RoundingMode.HALF_UP);

System.out.println(percentage.toPlainString()); // 12.49500
System.out.println(shown.toPlainString());      // 12.50
~~~

Đây là **mảnh mã trong method**, cần import `java.math.BigDecimal` và `java.math.RoundingMode`. Phép tính theo `BigDecimal` biểu diễn đúng giá trị thập phân nhập từ chuỗi; không tạo `BigDecimal` từ literal `double` kiểu `new BigDecimal(0.1)` nếu mục tiêu là giá trị thập phân 0.1 chính xác. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)`.

**Không làm tròn ở mỗi bước trung gian nếu nghiệp vụ chưa yêu cầu.** Thường nên bảo toàn ratio chính xác, chỉ chọn rounding tại điểm hiển thị hoặc điểm hạch toán có quy tắc riêng.

## 5. Phân tích ngược phần trăm: chuỗi 12.5% phải trở lại ratio 0.125

Khi nhập liệu, nhiều người nhập `12.5%` trên biểu mẫu nhưng ứng dụng lưu `0.125`. Một parser theo locale có thể thực hiện chuyển đổi ngược:

\[
\text{ratio} = \frac{\text{giá trị số được viết theo %}}{100}
\]

`NumberFormat.getPercentInstance(locale).parse(...)` phân tích chuỗi phần trăm theo quy ước tương ứng và trả về giá trị **ratio**, không phải đơn vị phần trăm.

### Ví dụ đầy đủ với ParsePosition và BigDecimal

Tạo tệp `PercentParseDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class PercentParseDemo {
    public static void main(String[] args) {
        String input = "12.5%";

        DecimalFormat parser = (DecimalFormat)
                NumberFormat.getPercentInstance(Locale.US);
        parser.setParseBigDecimal(true);

        ParsePosition end = new ParsePosition(0);
        Number parsed = parser.parse(input, end);

        if (parsed == null || end.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid percent input: " + input);
        }

        BigDecimal ratio = (BigDecimal) parsed;
        System.out.println("Input: " + input);
        System.out.println("Parsed ratio: " + ratio.toPlainString());
        System.out.println("As percent number: "
                + ratio.multiply(BigDecimal.valueOf(100))
                       .stripTrailingZeros().toPlainString());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PercentParseDemo.java
java PercentParseDemo
~~~

Đầu ra:

~~~text
Input: 12.5%
Parsed ratio: 0.125
As percent number: 12.5
~~~

**Tại sao kiểm tra `end.getIndex()`?** Một số parser chấp nhận phần đầu hợp lệ của chuỗi rồi dừng lại khi gặp ký tự không liên quan. Nếu chỉ xét `parsed != null`, input như `"12.5%abc"` có thể bị chấp nhận một cách thiếu nghiêm ngặt. Việc kiểm tra parser đã tiêu thụ **hết chuỗi** giúp từ chối ký tự dư.

Tuy nhiên, **tiêu thụ hết chuỗi không đủ để bảo đảm mọi quy tắc biểu mẫu nghiêm ngặt** (ví dụ vị trí dấu nhóm, khoảng trắng đặc biệt hoặc giới hạn tỷ lệ). Nếu nhập liệu quan trọng, kết hợp parser theo locale với validation riêng cho cấu trúc và phạm vi.

### Format rồi parse không phải lúc nào hoàn trả nguyên giá trị

Giả sử ratio gốc là `0.12495`, nhưng bạn chỉ hiển thị `12.50%`. Khi người dùng parse ngược chuỗi hiển thị này, giá trị nhận được là `0.125`, **khác** `0.12495`. Sự khác biệt đến từ việc **đã làm tròn khi hiển thị**.

Do đó:

- Giữ giá trị gốc chưa làm tròn trong model/dữ liệu lưu trữ.
- Xem chuỗi phần trăm là **một biểu diễn dành cho người đọc**.
- Không thiết kế luồng “format → parse → lưu đè” rồi kỳ vọng bảo toàn mọi chữ số gốc.
- Nếu người dùng chủ động sửa giá trị hiển thị, hãy coi đó là dữ liệu đầu vào mới và parse/validate theo chính sách.

## 6. `DecimalFormat`: ký hiệu % trong pattern có ý nghĩa nhân 100

`NumberFormat.getPercentInstance(locale)` thường tạo đối tượng thuộc loại `DecimalFormat` trong các implementation JDK thông dụng. Khi cần kiểm soát pattern, có thể dùng `DecimalFormat` và `DecimalFormatSymbols`:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PercentPatternDemo {
    public static void main(String[] args) {
        DecimalFormat format = new DecimalFormat(
                "0.00%",
                DecimalFormatSymbols.getInstance(Locale.US)
        );

        System.out.println(format.format(0.125));
        System.out.println(format.format(1.0));
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 PercentPatternDemo.java
java PercentPatternDemo
~~~

Đầu ra:

~~~text
12.50%
100.00%
~~~

Trong pattern `"0.00%"`, ký hiệu phần trăm là **ký tự đặc biệt của DecimalFormat**, có ý nghĩa chọn multiplier **100**, không chỉ thêm suffix. Vì vậy, không tự nhân 100 rồi truyền vào formatter có pattern `%`:

~~~java
double ratio = 0.125;
double alreadyScaled = ratio * 100; // 12.5
String wrong = format.format(alreadyScaled); // 1250.00%
~~~

Đây là **mảnh mã minh họa** trong phạm vi có biến `format` là `DecimalFormat` pattern `"0.00%"` ở trên. Đây là lỗi **nhân 100 hai lần**.

Muốn hiển thị chỉ một ký tự `%` theo nghĩa literal sau một giá trị đã tự quy đổi, phải thiết kế pattern/chuỗi riêng và kiểm soát việc quote trong `DecimalFormat`; trong ứng dụng thông thường, nên để **formatter phần trăm thực hiện toàn bộ phép tỷ lệ và định dạng** để tránh lỗi.

### Phân biệt ký hiệu % của ba API

| API | Ví dụ | Có tự nhân 100 không? |
| --- | --- | --- |
| `NumberFormat.getPercentInstance(Locale.US)` | `percent.format(0.125)` → `12.5%` nếu cấu hình một chữ số | **Có** |
| `DecimalFormat("0.0%")` | `format(0.125)` → `12.5%` | **Có** |
| `String.format(Locale.US, "%.1f%%", 0.125)` | `0.1%` | **Không**; `%%` chỉ là literal `%` |
| `String.format(Locale.US, "%.1f%%", 0.125 * 100)` | `12.5%` | Đã nhân 100 **trong code** |

Khi dùng `String.format`, cú pháp `%%` chỉ xuất ký tự phần trăm. Nó **không** thực hiện phép chia/nhân theo đơn vị phần trăm. Đây là khác biệt lớn so với `DecimalFormat` và `NumberFormat.getPercentInstance`.

**Lưu ý**: Ví dụ dòng `String.format("%.1f%%", 0.125)` cho ra `0.1%` vì chính tham số là `0.125` được in với một chữ số thập phân theo quy tắc `Formatter` (trường hợp 0.125 không ở đúng dạng thập phân nhị phân hoàn hảo). Trọng tâm là **không có phép nhân 100 tự động**; đừng coi cách làm tròn số `double` của `Formatter` như một cơ chế lưu trữ tỷ lệ chính xác.

## 7. Phần trăm thay đổi, điểm phần trăm và tỷ lệ tăng trưởng

Trong phân tích kinh doanh, câu “tăng 5%” có thể bị nhầm với “tăng 5 điểm phần trăm”. Hai phép tính **khác nhau**.

Giả sử tỷ lệ chuyển đổi tăng từ `0.20` (20%) lên `0.23` (23%).

### 7.1. Chênh lệch theo điểm phần trăm (*percentage points*)

\[
\text{Chênh lệch điểm %}=(0.23-0.20)\times100=3\text{ điểm phần trăm}
\]

Nên diễn đạt: “Tỷ lệ chuyển đổi tăng **3 điểm phần trăm**: từ 20% lên 23%”.

Ở đây, `newRatio.subtract(oldRatio)` bằng `0.03`. `NumberFormat.getPercentInstance(...).format(0.03)` có thể in `3%`, nhưng nhãn nghiệp vụ phải là **“3 điểm phần trăm”**; bản thân formatter không hiểu loại so sánh bạn đang biểu diễn.

### 7.2. Tăng trưởng tương đối (*relative percent change*)

\[
\text{Tăng trưởng tương đối}=\frac{0.23-0.20}{0.20}=0.15=15\%
\]

Nên diễn đạt: “Tỷ lệ chuyển đổi tăng **15% so với mức ban đầu**”. Mẫu số là tỷ lệ cũ, nên phải phân biệt với chênh lệch tuyệt đối.

Nếu tỷ lệ gốc bằng 0, công thức tương đối có phép chia cho 0 và cần chính sách nghiệp vụ thay vì tự hiển thị `Infinity%` hoặc ném lỗi không kiểm soát.

### 7.3. Ví dụ BigDecimal chính xác

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class PercentageChangeDemo {
    public static void main(String[] args) {
        BigDecimal oldRate = new BigDecimal("0.20");
        BigDecimal newRate = new BigDecimal("0.23");

        BigDecimal delta = newRate.subtract(oldRate);
        BigDecimal percentagePoints =
                delta.multiply(BigDecimal.valueOf(100));
        BigDecimal relativeChange =
                delta.divide(oldRate, 4, RoundingMode.HALF_UP)
                     .multiply(BigDecimal.valueOf(100));

        System.out.println("Old: "
                + oldRate.multiply(BigDecimal.valueOf(100))
                         .stripTrailingZeros().toPlainString() + "%");
        System.out.println("New: "
                + newRate.multiply(BigDecimal.valueOf(100))
                         .stripTrailingZeros().toPlainString() + "%");
        System.out.println("Difference: "
                + percentagePoints.stripTrailingZeros().toPlainString()
                + " percentage points");
        System.out.println("Relative change: "
                + relativeChange.stripTrailingZeros().toPlainString()
                + "%");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PercentageChangeDemo.java
java PercentageChangeDemo
~~~

Đầu ra:

~~~text
Old: 20%
New: 23%
Difference: 3 percentage points
Relative change: 15%
~~~

Đoạn code tạo chuỗi số theo phép tính chính xác để làm rõ đơn vị. Trong giao diện đa ngôn ngữ, nên format theo `Locale` và dịch cả nhãn `percentage points` hoặc `relative change` bằng `ResourceBundle`/i18n, không giữ nguyên tiếng Anh cho mọi người dùng.

### Điểm cơ bản (*basis points*)

Trong tài chính, **1 basis point** (1 bp) tương đương **0.01 điểm phần trăm** hay **0.0001** theo ratio. Ví dụ 2.5% = 250 bps. Đây là đơn vị khác với ký hiệu `%`; không chỉ thay suffix mà phải chuyển đổi đúng đơn vị.

## 8. Locale, dấu phân cách, ký tự Unicode và parsing ngược

Giả sử một ứng dụng ở Việt Nam xử lý dữ liệu của người dùng Đức:

~~~java
Locale locale = Locale.GERMANY;
NumberFormat format = NumberFormat.getPercentInstance(locale);
format.setMinimumFractionDigits(1);
format.setMaximumFractionDigits(1);
String output = format.format(0.125);
~~~

Đây là mảnh mã cần import `java.util.Locale` và `java.text.NumberFormat`. Kết quả dự kiến với dữ liệu locale Đức phổ biến là chuỗi có dấu phẩy thập phân và có thể có khoảng trắng không ngắt trước ký hiệu phần trăm, chẳng hạn `12,5 %`.

Để đọc lại chuỗi đó, dùng **percent parser theo cùng locale**:

~~~java
NumberFormat parser = NumberFormat.getPercentInstance(locale);
Number ratio = parser.parse(output);
~~~

Đây là mảnh mã trong method có `throws ParseException` hoặc xử lý lỗi; biến `locale` và `output` phải có sẵn.

**Đừng thay dấu phẩy/thập phân bằng thao tác chuỗi thô** nếu phải xử lý nhiều locale: dấu nhóm, khoảng trắng, chữ số Unicode, tiền tố/hậu tố và quy tắc dấu âm có thể khác nhau. Nếu cần trao đổi số giữa dịch vụ, gửi tỷ lệ dưới dạng số theo **định dạng giao thức nhất quán** (ví dụ JSON number `0.125`) thay vì chuỗi phần trăm đã bản địa hóa.

**Kiểm thử Unicode:** `"12,5 %"` có thể dùng NBSP `U+00A0`, khác `"12,5 %"` (dấu cách ASCII). Khi so sánh đầu ra trong test, cần hiểu rõ đang kiểm tra semantics hay khóa chặt ký tự theo CLDR của một phiên bản JDK. Không tự trim/replace không kiểm soát trong logic nghiệp vụ.

## 9. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Đưa `12.5` vào `getPercentInstance` để biểu diễn 12.5% | Hiện `1,250%` | Đưa `0.125` theo hợp đồng ratio |
| Nhân `100` trong code rồi lại gọi percent formatter | Nhân 100 **hai lần** | Để percent formatter tự scale |
| Dùng `String.format("%.1f%%", ratio)` và mong ra 12.5% | Chỉ thêm ký hiệu %, không scale | Dùng `NumberFormat`, hoặc nhân 100 có chủ đích |
| Dùng formatter không truyền `Locale` trong hệ thống đa người dùng | Kết quả phụ thuộc JVM mặc định | Truyền locale tường minh cho từng request |
| Nghĩ `setMaximumFractionDigits(2)` giữ nguyên ratio | Có thể làm tròn **chuỗi** hiển thị | Giữ raw value, chọn precision ở tầng giao diện |
| Lưu lại tỷ lệ bằng cách parse chuỗi đã làm tròn | Mất độ chính xác gốc | Lưu ratio trực tiếp, parse chỉ cho input mới |
| Parse `"12.5%"` bằng number formatter thông thường | Không đảm bảo tự chia 100 | Dùng percent formatter/parser với locale phù hợp |
| Chỉ kiểm tra parser trả non-null | Có thể chấp nhận phần tiền tố không hợp lệ | Kiểm tra `ParsePosition` và validation bổ sung |
| Dùng `double` cho nghiệp vụ cần thập phân chính xác | Rủi ro sai số/rounding | Dùng `BigDecimal` và quy tắc làm tròn |
| Gọi hiệu 20%→23% là “tăng 3%” mà không làm rõ | Nhầm điểm phần trăm và tăng trưởng tương đối | Ghi “3 điểm phần trăm” hoặc “15% tương đối” |
| Cho rằng mọi tỷ lệ phải trong `[0,1]` | Chặn nhầm tỷ lệ tăng trưởng âm hoặc lớn hơn 100% | Kiểm tra miền hợp lệ theo nghiệp vụ |

## 10. Quy tắc thiết kế ứng dụng

### 10.1. Đặt tên và kiểu dữ liệu rõ nghĩa

Sử dụng các tên thể hiện **đơn vị lưu trữ**:

~~~java
BigDecimal conversionRatio = new BigDecimal("0.125"); // 12.5%
BigDecimal percentNumber =
        conversionRatio.multiply(BigDecimal.valueOf(100)); // 12.5
~~~

Đây là mảnh mã trong method, cần import `java.math.BigDecimal`. Nếu một API sử dụng tỷ lệ `0..1`, ghi hợp đồng rõ trong tên trường, schema và tài liệu. Nếu API nhận đơn vị **percentage points** hoặc “giá trị số phần trăm” `12.5`, hãy đặt tên khác và chuyển đổi tại boundary, không trộn hai đơn vị.

### 10.2. Tách dữ liệu, tính toán và trình bày

~~~text
Dữ liệu gốc: 0.125 (ratio)
         |
         +--> Tính toán: BigDecimal, công thức nghiệp vụ
         |
         +--> Trình bày: NumberFormat.getPercentInstance(locale)
         |             -> "12.5%" (en-US)
         |             -> "12,5 %" (de-DE, ví dụ)
         |
         +--> Lưu trữ / API: 0.125, theo định dạng máy đã thỏa thuận
~~~

Không dùng chuỗi định dạng để làm nguồn cho các phép tính tiếp theo, trừ khi đang xử lý **input mới** do người dùng nhập.

### 10.3. Xác định chính sách precision

Một số hệ thống chỉ muốn nguyên phần trăm, một số yêu cầu 1–4 chữ số. Hãy định nghĩa:

- Số chữ số thập phân của **phần trăm hiển thị**.
- Quy tắc làm tròn (HALF_UP, HALF_EVEN, v.v.).
- Có cho phép ratio âm hoặc trên 1 không.
- Ngưỡng hiển thị như `<0.01%` có phải diễn đạt đặc biệt không (nếu có, đừng dùng literal thay cho giá trị gốc).
- Khi nhập phần trăm, parse theo locale nào; chấp nhận ký hiệu `%` bắt buộc hay cho phép input chỉ có số?
- Đơn vị lưu trữ: ratio, percentage points hay basis points.

### 10.4. Giới hạn đa luồng

`NumberFormat` và `DecimalFormat` là các đối tượng có trạng thái thay đổi và nhìn chung **không thread-safe** khi được dùng chung không có kiểm soát. Trong server nhiều request, tạo formatter theo request hoặc dùng cơ chế cache/tạo bản sao/đồng bộ phù hợp. `Locale` là immutable, nhưng formatter không nhất thiết immutable.

## 11. Bài tập củng cố

1. Với các ratio `0`, `0.005`, `0.125`, `1`, `1.2` và `-0.03`, định dạng bằng `NumberFormat.getPercentInstance(Locale.US)`. Thiết lập hai chữ số phần thập phân và ghi nhận kết quả.
2. Nếu một API đưa đến giá trị `"12.5"` nhưng tài liệu nói đó là **đơn vị phần trăm**, hãy viết phép chuyển sang ratio để bộ định dạng nhận đúng `0.125`.
3. Hiển thị `0.12495` dưới dạng phần trăm với hai chữ số và `HALF_UP`. Giải thích vì sao không nên parse ngược chuỗi đã làm tròn rồi lưu đè giá trị nguồn.
4. Chạy `PercentParseDemo` với `"12.5%abc"` và `"12.5%"`; giải thích giá trị `ParsePosition.getIndex()` và chính sách loại bỏ ký tự thừa.
5. Dùng `Locale.GERMANY` để định dạng `0.125`. Kiểm tra từng Unicode code point của chuỗi xuất ra, đặc biệt khoảng trắng và dấu thập phân.
6. Tỷ lệ tăng từ 4% lên 5%. Tính mức tăng theo **điểm phần trăm** và **phần trăm tương đối**. Đáp án: tăng **1 điểm phần trăm** và **25% so với mức cũ**.
7. Giải thích khác biệt giữa `String.format(Locale.US, "%.1f%%", 0.125)` và `NumberFormat.getPercentInstance(Locale.US).format(0.125)`.
8. Thiết kế unit test bảo đảm formatter không làm thay đổi `BigDecimal` đầu vào, kết quả đúng locale và không rò trạng thái giữa hai request.

**Ghi nhớ:** `NumberFormat.getPercentInstance(locale)` nhận **ratio gốc**, tự thực hiện quy đổi `×100` để hiển thị phần trăm, đồng thời định dạng dấu và vị trí ký hiệu theo locale; khi parse, nó quy đổi ngược `÷100`. **Formatting không sửa giá trị gốc**, nhưng việc làm tròn ở chuỗi có thể làm mất chi tiết nếu bạn parse ngược. Luôn phân biệt ratio `0.125`, giá trị phần trăm `12.5`, chuỗi `"12.5%"` và khái niệm **điểm phần trăm**.

### Tài liệu tham khảo

- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — `getPercentInstance`, format, parse, fraction digits và locale.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — pattern `%`/multiplier, rounding và `setParseBigDecimal`.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — tính toán thập phân và làm tròn.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html) — `%` literal trong `printf` và các conversion dạng số.