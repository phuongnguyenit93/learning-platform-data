# Ký hiệu 0, #, dấu thập phân và dấu phân nhóm trong DecimalFormat

`java.text.DecimalFormat` là lớp định dạng số của Java cho phép viết **pattern** để kiểm soát số chữ số tối thiểu/tối đa, phần thập phân, nhóm chữ số và ký hiệu xuất hiện trong chuỗi kết quả. Bốn ký hiệu quan trọng nhất của bài này là:

- `0` — **chữ số bắt buộc**: khi thiếu chữ số ở vị trí cần hiển thị, formatter thêm số 0.
- `#` — **chữ số tùy chọn**: chữ số 0 không cần thiết ở vị trí đó có thể được bỏ đi.
- `.` — **vị trí dấu thập phân trong pattern**; đầu ra là dấu thập phân của `DecimalFormatSymbols`.
- `,` — **vị trí dấu phân nhóm trong pattern**; đầu ra là dấu phân nhóm của `DecimalFormatSymbols` khi grouping được bật.

Ví dụ với `Locale.US`, mẫu `#,##0.00` định dạng số `12345.6` thành `12,345.60`. Với `Locale.GERMANY`, **cùng pattern không localized** cho ra `12.345,60`. Mẫu định nghĩa **cấu trúc số**; bộ ký hiệu locale quyết định **ký tự được hiển thị**.

Bài học này phân tích riêng ý nghĩa từng ký hiệu, cách kết hợp chúng, cơ chế làm tròn và parsing, vai trò của locale, cùng ví dụ Java 17+ có thể chạy trực tiếp.

## 1. Phân biệt pattern và giá trị đầu ra

Một số như `1234.5` có thể được hiển thị thành:

| Pattern | Locale | Chuỗi đầu ra |
| --- | --- | --- |
| `0` | `en-US` | `1234` hoặc `1235` tùy quy tắc làm tròn và phần thập phân; không giữ phần lẻ |
| `0.00` | `en-US` | `1234.50` |
| `#,##0.00` | `en-US` | `1,234.50` |
| `#,##0.00` | `de-DE` | `1.234,50` |
| `000000.000` | `en-US` | `001234.500` |

Khi **định dạng**, formatter nhận số và trả chuỗi. Nó không thay đổi giá trị số gốc. Khi **phân tích chuỗi** bằng `parse`, formatter thực hiện chiều ngược lại theo cấu hình của chính nó, nhưng parsing mặc định không phải bộ kiểm tra văn bản tài chính nghiêm ngặt.

**Lưu ý làm tròn:** Với pattern `0`, `1234.5` theo mặc định `DecimalFormat` sử dụng `RoundingMode.HALF_EVEN`, do đó thành `1234` (chữ số hàng đơn vị là 4 chẵn). Nếu ứng dụng cấu hình `HALF_UP`, kết quả thành `1235`. Không dựa vào nhận định “cắt bỏ phần thập phân” vì định dạng có thể **làm tròn**, không phải truncate.

## 2. Ký hiệu `0` — một chữ số bắt buộc

Trong **vùng số** của pattern, mỗi `0` biểu thị một vị trí chữ số cần được in. Khi phần nguyên ngắn hơn số vị trí `0` tối thiểu, Java chèn thêm số 0 ở bên trái. Khi phần thập phân ngắn hơn số vị trí `0` tối thiểu, Java chèn số 0 ở bên phải.

Ví dụ `Locale.US`:

| Pattern | Giá trị | Kết quả | Lý do |
| --- | ---: | --- | --- |
| `0` | 7 | `7` | Ít nhất một chữ số nguyên |
| `0000` | 7 | `0007` | Bốn chữ số nguyên tối thiểu |
| `0000` | 12345 | `12345` | Nhiều hơn bốn chữ số vẫn được hiển thị theo cấu hình thông thường |
| `0.00` | 12.5 | `12.50` | Hai chữ số thập phân bắt buộc |
| `000.000` | 12.5 | `012.500` | Ba chữ số nguyên và ba chữ số lẻ |
| `0.00` | 0 | `0.00` | Phần thập phân vẫn in hai số 0 |

`0` **không có nghĩa chỉ được phép một chữ số**: mẫu `0` vẫn có thể hiển thị một số nguyên lớn. Số lượng ký hiệu `0` điều chỉnh **mức tối thiểu**, không nhất thiết là chiều rộng tuyệt đối của phần nguyên.

Để tạo mã có chiều rộng cố định như `0007`, cần phân biệt rõ: cách định dạng này chỉ phù hợp khi mã thực sự được tạo từ một số; nếu mã định danh chứa số 0 ở đầu như dữ liệu gốc (mã bưu chính, số tài khoản, số seri), nên lưu **chuỗi**, tránh làm mất số 0 trong quá trình chuyển đổi sang số.

## 3. Ký hiệu `#` — chữ số tùy chọn

`#` chỉ vị trí **có thể** có chữ số nhưng không ép hiển thị số 0 nếu vị trí đó không cần thiết. Nó thường được đặt bên trái phần nguyên hoặc bên phải phần thập phân:

| Pattern | Giá trị | Kết quả `en-US` |
| --- | ---: | --- |
| `0.##` | 12.5 | `12.5` |
| `0.##` | 12.00 | `12` |
| `0.##` | 12.567 | `12.57` |
| `#,##0.##` | 12345.6 | `12,345.6` |
| `#,##0.##` | 12345 | `12,345` |
| `#.##` | 12.5 | `12.5` |

Cách hiểu chính xác:

- `0.00` — **đúng hai chữ số thập phân hiển thị**, làm tròn nếu cần.
- `0.##` — **tối đa hai chữ số thập phân**, không ép hai số 0 cuối.
- `0.0#` — **ít nhất một, nhiều nhất hai** chữ số thập phân.
- `#,##0.00` — nhóm chữ số ở phần nguyên, hiển thị hai chữ số sau dấu thập phân.
- `#,##0.##` — nhóm chữ số và phần lẻ không cố định.

**Trường hợp số 0:** Mặc dù `#` mang nghĩa optional, `new DecimalFormat("#", symbols).format(0)` trên Java 17+ vẫn cho `"0"`: `DecimalFormat` bảo đảm hiển thị biểu diễn phù hợp cho giá trị 0 thay vì mặc định để trống toàn bộ số. Vì vậy không nên diễn giải máy móc “mọi ký hiệu `#` đều bỏ số 0, nên số 0 thành chuỗi rỗng”.

## 4. Ví dụ chạy được: so sánh `0` và `#`

Tạo tệp **`DigitPlaceholdersDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitPlaceholdersDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        String[] patterns = {
                "0", "0000", "#", "0.00",
                "0.##", "#.##", "#,##0.00", "#,##0.##"
        };

        for (String pattern : patterns) {
            DecimalFormat formatter = new DecimalFormat(pattern, symbols);
            System.out.println(pattern + " | " +
                    formatter.format(0) + " | " +
                    formatter.format(12.5) + " | " +
                    formatter.format(12345.678));
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac DigitPlaceholdersDemo.java
java DigitPlaceholdersDemo
~~~

Kết quả trên Java với ký hiệu `Locale.US`:

~~~text
0 | 0 | 12 | 12346
0000 | 0000 | 0012 | 12346
# | 0 | 12 | 12346
0.00 | 0.00 | 12.50 | 12345.68
0.## | 0 | 12.5 | 12345.68
#.## | 0 | 12.5 | 12345.68
#,##0.00 | 0.00 | 12.50 | 12,345.68
#,##0.## | 0 | 12.5 | 12,345.68
~~~

Từ bảng, hãy quan sát:

1. `0000` chỉ thêm số 0 ở **đầu phần nguyên** khi thiếu.
2. `0.00` luôn có hai chữ số thập phân; `0.##` có thể bỏ phần thập phân hoàn toàn.
3. `#,##0.00` áp dụng nhóm chữ số khi phần nguyên đủ lớn.
4. `12345.678` thành `12345.68` ở mẫu có hai chữ số lẻ vì **làm tròn**.

`DecimalFormatSymbols` được lấy theo `Locale.US` để ví dụ có kết quả rõ ràng, tránh phụ thuộc locale mặc định trên máy chạy.

## 5. Dấu chấm `.` trong pattern: dấu thập phân logic

Trong **pattern không localized** (dùng bởi constructor `DecimalFormat(pattern, symbols)` và `applyPattern(String)`), dấu chấm `.` là **ký hiệu vị trí phân cách phần nguyên và phần thập phân**.

Điều đó **không có nghĩa đầu ra luôn chứa ký tự dấu chấm**. Formatter sẽ dùng ký hiệu thập phân hiện hành trong `DecimalFormatSymbols` của nó. Ví dụ:

~~~text
Pattern:       #,##0.00
Locale.US:     1,234.50
Locale.GERMANY:1.234,50
~~~

Trong ví dụ Đức, dấu `.` *ở pattern* được render thành dấu `,` *ở output*. Đây là tính chất quan trọng nhất để tránh hardcode dấu thập phân trong ứng dụng quốc tế.

Một pattern như `0.00` có dấu thập phân trong thiết kế và **bắt buộc** có hai chữ số lẻ. Mẫu `0.##` chỉ đưa phần lẻ ra khi cần: `1234` định dạng thành `1234`, không nhất thiết thành `1234.`.

Ngoài ra, `DecimalFormat.setDecimalSeparatorAlwaysShown(true)` có thể ép dấu thập phân hiển thị ngay cả khi không có chữ số lẻ. Ví dụ `new DecimalFormat("#,##0.##", symbols)` với flag đó có thể định dạng `1234` thành `1,234.` (đây là tùy chọn riêng, không suy ra chỉ từ `#`).

### Dấu thập phân khác với dấu “đổi dữ liệu”

Giá trị `1234.5` trong chương trình Java vẫn đại diện số như cũ. `DecimalFormat` chỉ tạo chuỗi hiển thị. Đừng thay ký tự trong giá trị đã format rồi coi là đã “đổi locale” hoàn chỉnh: ngoài dấu thập phân còn có dấu nhóm, chữ số, tiền tệ, dấu âm, và nhiều quy tắc khác.

## 6. Dấu phẩy `,` trong pattern: vị trí phân nhóm chữ số

Trong **pattern không localized**, dấu phẩy `,` yêu cầu formatter dùng **grouping** cho phần nguyên. Thông thường, pattern `#,##0` sẽ nhóm mỗi ba chữ số tính từ phải sang trái:

| Số | `#,##0` theo `en-US` | `#,##0` theo `de-DE` |
| ---: | --- | --- |
| 123 | `123` | `123` |
| 1234 | `1,234` | `1.234` |
| 12345 | `12,345` | `12.345` |
| 1234567 | `1,234,567` | `1.234.567` |

Cùng dấu phẩy `,` trong pattern sẽ render theo `DecimalFormatSymbols.getGroupingSeparator()`, ví dụ thành dấu chấm tại `Locale.GERMANY`. Dấu grouping giúp người đọc nhưng **không tạo ra phép toán** và không ảnh hưởng số gốc.

**Grouping không phải yêu cầu bắt buộc đối với mọi ứng dụng.** Nếu là mã định danh, phiên bản phần mềm, dữ liệu trao đổi giữa máy hoặc một số biểu thức chuẩn hóa, việc chèn grouping thường không phù hợp. Với giá trị hiển thị cho người dùng, nhóm chữ số thường tăng khả năng đọc nhưng phải theo đúng thói quen địa phương.

### Phân nhóm khác với phần lẻ

Dấu grouping trong pattern thuộc **phần nguyên**, còn dấu decimal xác định **ranh giới giữa nguyên và lẻ**. Ví dụ:

~~~text
#,##0.00
 ^   ^
 |   └── vị trí dấu thập phân
 └────── vị trí phân nhóm chữ số
~~~

Vị trí dấu grouping trong pattern quyết định **kích thước nhóm**. Với mẫu này kích thước nhóm là 3. Kết quả `1234567.8` tại `Locale.US` là `1,234,567.80`.

Không đặt dấu grouping tùy tiện trong phần thập phân; pattern số của `DecimalFormat` có cú pháp riêng, và grouping được xác định ở phần nguyên.

## 7. Locale và `DecimalFormatSymbols` quyết định ký tự thực tế

`DecimalFormatSymbols` là tập ký hiệu mà `DecimalFormat` dùng để format và parse số: bao gồm decimal separator, grouping separator, chữ số 0 và dấu âm, cùng nhiều ký hiệu khác.

Tạo **`LocaleSeparatorsDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocaleSeparatorsDemo {
    public static void main(String[] args) {
        String pattern = "#,##0.00";

        DecimalFormat us = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(Locale.US));
        DecimalFormat germany = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(Locale.GERMANY));

        System.out.println("US: " + us.format(12345.6));
        System.out.println("DE: " + germany.format(12345.6));
    }
}
~~~

~~~bash
javac LocaleSeparatorsDemo.java
java LocaleSeparatorsDemo
~~~

Kết quả:

~~~text
US: 12,345.60
DE: 12.345,60
~~~

**Cơ chế:** `DecimalFormat` đọc cùng cấu trúc pattern `#,##0.00` và dùng các ký hiệu locale ở thời điểm tạo formatter. Không phải chuỗi pattern đã được dịch sang tiếng Đức; nó vẫn là **pattern chuẩn không localized**.

Dữ liệu locale có thể cập nhật theo JDK/provider và các vùng sử dụng khoảng trắng đặc biệt hoặc hệ chữ số khác. Khi cần so sánh output Unicode chính xác trong kiểm thử, xác định JDK và provider đang dùng; không coi hai dấu cách trông giống nhau là một ký tự.

## 8. Tùy chỉnh ký hiệu thay vì sửa pattern

Có thể chủ động cấu hình ký hiệu thông qua `DecimalFormatSymbols`. Đây là công cụ hữu ích khi yêu cầu đầu ra không tuân hoàn toàn quy tắc locale mặc định.

Ví dụ **`CustomSeparatorsDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class CustomSeparatorsDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator(':');

        DecimalFormat formatter =
                new DecimalFormat("#,##0.00", symbols);

        System.out.println(formatter.format(12345.6));
    }
}
~~~

~~~bash
javac CustomSeparatorsDemo.java
java CustomSeparatorsDemo
~~~

Kết quả:

~~~text
12_345:60
~~~

Dấu `,` và `.` **trong pattern vẫn giữ nguyên**. Chỉ ký tự output thay đổi theo symbols. Đây cũng là lý do không nên dùng `new DecimalFormat(pattern)` rồi dựa vào default JVM trong chương trình đa người dùng; hãy truyền locale/symbols tường minh.

`DecimalFormatSymbols` mutable, và `DecimalFormat` cũng mutable. Nếu muốn nhiều formatter có bộ ký hiệu khác nhau, tạo cấu hình rõ ràng cho từng formatter. Tránh sửa một formatter đang được nhiều thread dùng chung.

## 9. `applyPattern` và `applyLocalizedPattern` không nhận cùng thứ tiếng pattern

Đây là lỗi phổ biến khi nhìn vào một số được format theo kiểu Đức rồi tưởng pattern cũng phải đảo dấu.

- `applyPattern(String)` nhận **pattern không localized**: dùng `.` làm decimal placeholder và `,` làm grouping placeholder.
- `applyLocalizedPattern(String)` nhận **pattern theo bộ ký hiệu hiện tại**: với symbols tiếng Đức, dấu decimal và grouping trong pattern localized lần lượt là `,` và `.`.

Thí dụ:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

DecimalFormat formatter = new DecimalFormat("#,##0.00", symbols);

System.out.println(formatter.toPattern());
System.out.println(formatter.toLocalizedPattern());
~~~

Đây là **đoạn trong phương thức Java** với import `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols` và `java.util.Locale`. Kết quả trên Java dùng ký hiệu Đức phổ biến:

~~~text
#,##0.00
#.##0,00
~~~

Điều cần nhớ: **không truyền `#.##0,00` vào `applyPattern` với kỳ vọng đó là mẫu Đức**, vì hàm này sẽ giải nghĩa dấu theo cú pháp pattern chuẩn, dẫn tới ý nghĩa khác hoặc lỗi. Nếu nhận mẫu được viết theo ký hiệu người dùng nhìn thấy, cần biết rõ nguồn mẫu và dùng API tương ứng.

### Vì sao nên ưu tiên pattern không localized trong mã nguồn?

Một ứng dụng phục vụ nhiều locale thường lưu cấu trúc pattern chuẩn như `#,##0.00`. Formatter kết hợp pattern với symbols của locale hiệu lực. Điều này giúp tránh quản lý các chuỗi pattern khác nhau chỉ vì dấu decimal và grouping khác nhau.

`applyLocalizedPattern` vẫn hữu ích khi một công cụ cho phép người dùng **nhập pattern bằng dấu phân cách của chính họ**, nhưng sản phẩm cần giải thích cú pháp và xác thực đầu vào để tránh hiểu nhầm.

## 10. Kích thước nhóm và nhiều dấu phẩy

Với pattern `#,##0`, khoảng cách giữa dấu grouping cuối cùng và chữ số nguyên cuối là ba chữ số nên size thường là 3. Có thể thay đổi bằng `setGroupingSize(int)`:

~~~java
DecimalFormat fmt = new DecimalFormat(
        "#,##0", DecimalFormatSymbols.getInstance(Locale.US));
fmt.setGroupingSize(4);
System.out.println(fmt.format(12345678));
~~~

Đây là **snippet trong method**, cần import `DecimalFormat`, `DecimalFormatSymbols` và `Locale`. Kết quả là:

~~~text
1234,5678
~~~

Grouping size 4 có thể hợp nhu cầu hiển thị đặc biệt, nhưng không có nghĩa dùng đúng quy tắc grouping của mọi địa phương.

### Nhiều dấu grouping không tạo nhiều kích thước nhóm khác nhau trong `DecimalFormat`

Một pattern như:

~~~text
##,##,##0.00
~~~

có thể khiến người học kỳ vọng chuỗi theo lối “3 chữ số nhóm cuối rồi 2 chữ số các nhóm trước”, ví dụ `1,23,45,678.90`. Trong **`java.text.DecimalFormat` chuẩn**, các dấu grouping bổ sung không tạo ra nhiều grouping size phân cấp độc lập như vậy: **khoảng cách từ dấu grouping cuối bên phải** là kích thước quyết định.

Với pattern trên tại `Locale.US` và số `12345678.9`, Java tạo:

~~~text
12,345,678.90
~~~

Nếu ứng dụng thực sự cần grouping đặc thù theo nhiều mức (ví dụ chuẩn địa phương kiểu 3 rồi 2), phải kiểm tra API/thư viện đáp ứng yêu cầu và không suy luận từ việc thêm nhiều dấu phẩy vào `DecimalFormat`.

**Lưu ý:** `NumberFormat.getNumberInstance(locale)` có thể chọn quy tắc grouping của provider cho locale đó. Pattern tùy chỉnh ép size là một lựa chọn khác; hãy kiểm tra hành vi trên runtime mà bạn triển khai.

## 11. Làm tròn: `0` và `#` không quyết định mọi quy tắc

Pattern xác định **số chữ số lẻ được phép hoặc bắt buộc**, nhưng kết quả làm tròn còn phụ thuộc `RoundingMode`.

- `0.00`: ít nhất và nhiều nhất hai chữ số thập phân.
- `0.##`: từ 0 tới 2 chữ số thập phân.
- `0.0#`: từ 1 tới 2 chữ số thập phân.
- Khi số có nhiều chữ số hơn giới hạn, formatter **làm tròn** theo rounding mode.

`DecimalFormat` theo mặc định dùng `RoundingMode.HALF_EVEN` (làm tròn về chữ số chẵn khi đúng điểm giữa). Một số quy tắc nghiệp vụ yêu cầu `HALF_UP` hoặc mode khác: cần chỉ định rõ.

Ví dụ **`RoundingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.565");

        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        System.out.println(formatter.format(value));

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(formatter.format(value));
    }
}
~~~

~~~bash
javac RoundingDemo.java
java RoundingDemo
~~~

Kết quả:

~~~text
1,234.56
1,234.57
~~~

Với `HALF_EVEN`, trường hợp đúng nửa `...565` làm tròn về `...56` vì chữ số cuối giữ lại là 6 chẵn. Với `HALF_UP`, làm tròn thành `...57`.

**Tại sao dùng `BigDecimal("1234.565")`?** Giá trị thập phân được tạo chính xác từ chuỗi, tránh sai số biểu diễn nhị phân của `double` làm ví dụ điểm giữa khó dự đoán. Trong ứng dụng tiền tệ, `BigDecimal` thường phù hợp hơn cho tính toán và làm tròn nghiệp vụ; `DecimalFormat` chỉ xử lý tầng **biểu diễn**.

Không nên làm tròn bằng cách cắt chuỗi sau `format`, vì có thể phá vỡ dấu nhóm, dấu âm và quy tắc dấu thập phân.

## 12. Bật/tắt grouping và dấu thập phân bắt buộc

Ngoài pattern, `DecimalFormat` có các setter quan trọng:

| API | Tác dụng |
| --- | --- |
| `setGroupingUsed(boolean)` | Cho phép hoặc tắt phân nhóm chữ số |
| `setGroupingSize(int)` | Cấu hình số chữ số mỗi nhóm |
| `setMinimumIntegerDigits(int)` | Số chữ số nguyên tối thiểu |
| `setMinimumFractionDigits(int)` | Số chữ số thập phân tối thiểu |
| `setMaximumFractionDigits(int)` | Số chữ số thập phân tối đa |
| `setDecimalSeparatorAlwaysShown(boolean)` | Có in dấu thập phân khi không có chữ số lẻ hay không |
| `setRoundingMode(RoundingMode)` | Quy tắc làm tròn |
| `setDecimalFormatSymbols(DecimalFormatSymbols)` | Đổi bộ ký hiệu hiển thị/parsing |

Ví dụ:

~~~java
DecimalFormat f = new DecimalFormat(
        "#,##0.##", DecimalFormatSymbols.getInstance(Locale.US));
f.setGroupingUsed(false);
System.out.println(f.format(12345.6));

f.setDecimalSeparatorAlwaysShown(true);
System.out.println(f.format(1234));
~~~

Đây là **snippet trong phương thức**, cần import `DecimalFormat`, `DecimalFormatSymbols` và `Locale`. Kết quả:

~~~text
12345.6
1234.
~~~

Số `12345.6` không còn dấu nhóm khi grouping bị tắt; ở dòng sau dấu thập phân vẫn được in dù phần lẻ không có chữ số. Trong đa số UI, không cần bật `setDecimalSeparatorAlwaysShown(true)` trừ khi thiết kế dữ liệu thật sự yêu cầu dấu kết thúc đó.

**Thứ tự cấu hình có ý nghĩa:** gọi setter sau constructor có thể thay đổi những ràng buộc mà pattern ban đầu thiết lập. Nếu cache formatter, hãy đảm bảo formatter được cấu hình xong trước khi sử dụng, và không sửa cùng một instance từ nhiều thread.

## 13. Format và parse không phải cùng một phép kiểm tra chặt chẽ

`format(number)` chuyển **giá trị số → văn bản**. `parse(text)` chuyển **văn bản → một `Number`** theo cấu hình của formatter. Parsing mặc định của `DecimalFormat` có thể **dừng tại ký tự không hợp lệ** thay vì yêu cầu toàn bộ input được tiêu thụ.

Ví dụ với `Locale.US` và pattern `#,##0.00`:

~~~java
DecimalFormat f = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(f.parse("1,234.50"));
System.out.println(f.parse("1.234,50"));
~~~

Đây là đoạn minh họa trong phương thức có xử lý `ParseException` hoặc khai báo `throws Exception`, và các import tương ứng. Trên Java 17+:

~~~text
1234.5
1.234
~~~

Dòng thứ hai **không** có nghĩa `"1.234,50"` đã được hiểu đúng thành một nghìn hai trăm ba mươi bốn phẩy năm. Formatter theo kiểu Mỹ hiểu dấu chấm là dấu thập phân và có thể dừng trước dấu phẩy còn lại; nếu ứng dụng bỏ qua phần chưa đọc, có thể nhận sai số mà không nhận ra.

### Dùng `ParsePosition` để biết parser đã đọc tới đâu

Ví dụ **`ParsePositionDemo.java`**:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePositionDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        String input = "1,234.50XYZ";
        ParsePosition pos = new ParsePosition(0);
        Number result = formatter.parse(input, pos);

        System.out.println(result);
        System.out.println(pos.getIndex());
        System.out.println(pos.getIndex() == input.length());
    }
}
~~~

~~~bash
javac ParsePositionDemo.java
java ParsePositionDemo
~~~

Kết quả:

~~~text
1234.5
8
false
~~~

Parser đã đọc 8 ký tự đầu và bỏ lại `XYZ`. Khi xác thực input, cần kiểm tra `result != null`, `pos.getErrorIndex()` và liệu `pos.getIndex()` có bằng độ dài đầu vào hay không.

Ngay cả khi toàn bộ chuỗi được tiêu thụ, parsing locale cũng có thể cho phép một số cách viết nhóm không như mong đợi; nếu yêu cầu **quy tắc đầu vào nghiêm ngặt**, cần validation bổ sung theo đặc tả sản phẩm. Với JSON và dữ liệu giữa hệ thống, thường dùng biểu diễn số chuẩn, không phụ thuộc locale để trao đổi.

### Muốn nhận kết quả `BigDecimal`

Có thể gọi `formatter.setParseBigDecimal(true)` trước `parse` khi cần giữ độ chính xác của biểu diễn thập phân. Vẫn phải kiểm tra input và locale; việc trả `BigDecimal` không tự bảo đảm chuỗi ban đầu hợp lệ theo chuẩn của nghiệp vụ.

## 14. Pattern là quy ước định dạng, không phải văn bản số tùy ý

Các ví dụ thường nhầm lẫn:

- `"1,234.56"` là **chuỗi số kiểu Mỹ**, **không** phải pattern dùng để diễn tả số có grouping và hai chữ số thập phân; pattern phù hợp thường là `#,##0.00`.
- `"1.234,56"` là **chuỗi số kiểu Đức**, **không** phải pattern không localized. Nếu đưa chuỗi ấy vào `new DecimalFormat(pattern)`, Java có thể hiểu các dấu theo nghĩa khác.
- `"#,###"` và `"#,##0"` không hoàn toàn tương đương về số chữ số bắt buộc; đặc biệt nên chọn dạng có `0` rõ ràng để không mơ hồ khi zero.
- `"0.000"` không mang nghĩa “lấy ba số lẻ bằng phép cắt”; formatter làm tròn theo rounding mode.
- `"#,##0.##"` không hứa luôn có dấu thập phân hay hai chữ số lẻ.
- `"0000"` không bảo đảm output có đúng bốn ký tự cho số lớn hơn bốn chữ số.

Khi cần định dạng tiền tệ hoặc phần trăm, pattern của `DecimalFormat` còn ký hiệu `¤` hoặc `%`, nhưng các yêu cầu đó còn liên quan đơn vị, scale và quy ước locale; không tự xem những mẫu số thông thường ở bài này là thay thế đầy đủ cho `NumberFormat.getCurrencyInstance(locale)` hoặc phần logic nghiệp vụ tương ứng.

## 15. Sử dụng đúng trong ứng dụng nhiều người dùng

`DecimalFormat` là **mutable** và không bảo đảm thread-safe. Những nơi nhiều request đồng thời không nên chia sẻ một `static final DecimalFormat` rồi sửa locale, ký hiệu hoặc rounding mode cho mỗi request.

Một helper có thể tạo formatter theo yêu cầu cụ thể:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormattingService {
    public static String display(BigDecimal amount, Locale locale) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale));

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        return formatter.format(amount);
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");

        System.out.println(display(amount, Locale.US));
        System.out.println(display(amount, Locale.GERMANY));
    }
}
~~~

~~~bash
javac DecimalFormattingService.java
java DecimalFormattingService
~~~

Kết quả:

~~~text
1,234.50
1.234,50
~~~

Mỗi lời gọi tạo formatter riêng, locale rõ ràng và rounding mode rõ ràng. Với yêu cầu hiệu năng cao, có thể tối ưu vòng đời formatter sau khi đo thực tế, nhưng cần duy trì an toàn thread và tính đúng theo locale. `DecimalFormatSymbols` cũng nên được coi là phần cấu hình cần xác định cụ thể thay vì dùng default JVM toàn cục.

**Đừng lưu chuỗi đã format làm dữ liệu tính toán.** Lưu số dưới dạng kiểu phù hợp, rồi định dạng ở ranh giới trình bày. Nếu bản thân giá trị là tỷ giá hoặc tiền, cần giữ số, mã tiền tệ, scale và quy tắc làm tròn nghiệp vụ riêng, không suy ra tất cả từ dấu grouping/thập phân.

## 16. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `#.##` nhưng muốn luôn hai số lẻ | `12.5` thay vì `12.50` | Dùng `0.00` cho phần lẻ bắt buộc |
| Dùng `0000` để giới hạn tuyệt đối bốn chữ số | Số có năm chữ số vẫn dài hơn bốn | Xác thực chiều dài riêng nếu đây là mã định danh |
| Thay dấu chấm/phẩy bằng `String.replace` | Dễ tạo sai dấu nhóm/dấu thập phân | Dùng symbols của locale |
| Viết mẫu kiểu Đức vào `applyPattern` | Parser hiểu sai nghĩa dấu | Dùng pattern không localized hoặc `applyLocalizedPattern` đúng cách |
| Coi `parse` là validation toàn chuỗi | Input sai có thể bị nhận một phần | Dùng `ParsePosition` và validation bổ sung |
| Làm tròn bằng cắt chuỗi kết quả | Sai kết quả và dấu phân cách | Dùng `RoundingMode` và dữ liệu số chính xác |
| Dùng `new DecimalFormat(pattern)` cho mọi user | Dính locale mặc định JVM | Truyền `DecimalFormatSymbols.getInstance(locale)` |
| Chia sẻ formatter mutable giữa các thread | Có thể sinh race/cấu hình lẫn nhau | Tạo theo request hoặc đồng bộ có kiểm soát |
| Nhầm `#` sẽ cho số 0 thành rỗng | Kỳ vọng output sai | Chạy test với zero; hiểu cơ chế zero digits của `DecimalFormat` |
| Thêm nhiều dấu phẩy với mong muốn grouping kiểu 3-2 | Java chuẩn vẫn dùng size cuối | Kiểm tra quy tắc API hoặc thư viện phù hợp |

## 17. Bài tập tự kiểm tra

**1.** Theo `Locale.US`, `new DecimalFormat("000.00", symbols).format(7.5)` tạo ra gì?

**Đáp án:** `007.50`. Ba vị trí nguyên và hai vị trí thập phân đều bắt buộc.

**2.** Tại sao pattern `0.##` định dạng `12` thành `12` mà không phải `12.00`?

**Đáp án:** Hai ký hiệu `#` sau dấu decimal là **tùy chọn**, nên có thể bỏ phần lẻ không cần thiết.

**3.** Tại sao pattern `#,##0.00` có dấu phẩy nhưng đầu ra tiếng Đức lại có dấu chấm để phân nhóm?

**Đáp án:** Dấu phẩy trong pattern không localized là **ký hiệu logic grouping**; `DecimalFormatSymbols` của locale quyết định ký tự output thực tế.

**4.** Pattern `0000` có buộc số `123456` thành chuỗi có bốn chữ số không?

**Đáp án:** Không. `0` quy định tối thiểu, không phải giới hạn chiều dài số nguyên.

**5.** `DecimalFormat.parse("1.234,50")` dùng symbols kiểu Mỹ có chắc trả số `1234.5` không?

**Đáp án:** Không. Parser có thể hiểu dấu chấm là dấu thập phân và dừng ở dấu phẩy; cần kiểm tra vị trí parse và locale đúng.

**6.** Vì sao với số tiền nên chọn `BigDecimal("1234.565")` thay vì `double 1234.565` để minh họa làm tròn đúng điểm giữa?

**Đáp án:** `BigDecimal` tạo từ chuỗi giữ chính xác biểu diễn thập phân, tránh sai số nhị phân ảnh hưởng kết quả rounding.

**7.** Muốn chuỗi `12,345.60` từ `12345.6` theo `Locale.US`, pattern nào phù hợp?

**Đáp án:** `#,##0.00`.

**8.** Phân biệt `applyPattern` và `applyLocalizedPattern`?

**Đáp án:** Cái đầu hiểu dấu chuẩn `.`/`,` trong pattern không localized; cái sau hiểu các dấu pattern theo `DecimalFormatSymbols` của formatter.

**9.** Muốn dùng dấu `_` để grouping nhưng vẫn giữ cấu trúc pattern `#,##0.00`?

**Đáp án:** Tạo/đặt `DecimalFormatSymbols` có `setGroupingSeparator('_')` rồi dùng formatter với symbols đó.

**10.** Tại sao `DecimalFormat` không nên chia sẻ mutable instance giữa request có locale khác nhau?

**Đáp án:** Nó không được bảo đảm thread-safe, và các setter có thể làm cấu hình bị đổi giữa các thao tác định dạng.

## 18. Tóm tắt kiến thức cốt lõi

- **`0` = chữ số bắt buộc**; thêm zero để đạt mức tối thiểu.
- **`#` = chữ số tùy chọn**; không ép thêm zero ở cuối phần lẻ.
- **`.` trong pattern = vị trí dấu thập phân**, còn ký tự đầu ra đến từ symbols.
- **`,` trong pattern = vị trí grouping**, còn ký tự đầu ra và kích thước nhóm do cấu hình quyết định.
- Pattern **không localized** giữ cấu trúc đồng nhất qua các locale; symbols làm phần hiển thị thay đổi.
- `format` có thể **làm tròn**, nên dùng `BigDecimal` và `RoundingMode` rõ ràng khi độ chính xác quan trọng.
- `parse` có thể đọc **một phần** chuỗi; kiểm tra vị trí parse và chính sách validation.
- `DecimalFormat` mutable; tạo formatter theo locale ngữ cảnh thay vì phụ thuộc default JVM hay chia sẻ không đồng bộ.

**Tài liệu chuẩn để đối chiếu:** [DecimalFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html), [DecimalFormatSymbols — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html), [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html).