# Ký hiệu khoa học và giới hạn biểu diễn với DecimalFormat trong Java

## 1. Ký hiệu khoa học dùng để làm gì?

Khi làm việc với số rất lớn, rất nhỏ hoặc có nhiều chữ số, hiển thị đầy đủ dạng thập phân có thể khiến giao diện khó đọc. **Ký hiệu khoa học (scientific notation)** biểu diễn số theo dạng:

\[
x = m \times 10^e
\]

Trong đó:

- `m` là **phần trị** (mantissa/significand) được hiển thị.
- `e` là **số mũ cơ số 10**.
- Với số khác 0 ở dạng chuẩn hóa thông thường, độ lớn của `m` thuộc khoảng từ 1 đến dưới 10.
- Giá trị gốc không phải là chuỗi; ký hiệu khoa học chỉ là **cách trình bày** hoặc biểu diễn số ở đầu vào.

Ví dụ:

| Số ban đầu | Ký hiệu khoa học | Giá trị |
| --- | --- | --- |
| `12345` | `1.2345E4` | `1.2345 × 10^4` |
| `0.000012345` | `1.2345E-5` | `1.2345 × 10^-5` |
| `-1500000` | `-1.5E6` | `-1.5 × 10^6` |
| `0` | `0E0` ở dạng minh họa | 0 |

Ký tự `E` thể hiện “nhân với lũy thừa 10” trong nhiều biểu diễn máy đọc; `E4` nghĩa là nhân `10^4`, không phải cộng 4. Trong kết quả bản địa hóa của `DecimalFormat`, phần phân cách số mũ có thể khác `E` tùy `DecimalFormatSymbols` và nguồn dữ liệu locale.

**Phạm vi của bài:** dùng `java.text.DecimalFormat` để định dạng/parse số ở ký hiệu khoa học, hiểu scientific so với engineering notation, cách locale và rounding tác động đến chuỗi, và phân biệt **giới hạn hiển thị** với **giới hạn miền giá trị/độ chính xác** của kiểu số Java.

## 2. DecimalFormat bật ký hiệu khoa học bằng pattern

`DecimalFormat` là một dạng `NumberFormat` có thể cấu hình bằng **pattern**. Trong pattern không được quote, chữ `E` là dấu giới thiệu phần mũ:

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormat scientific = new DecimalFormat(
        "0.00E0", DecimalFormatSymbols.getInstance(Locale.US));
~~~

Đây là **đoạn minh họa trong thân phương thức**, không phải file Java độc lập. Chương trình hoàn chỉnh nằm ở mục 7.

Pattern `0.00E0` được đọc như sau:

| Thành phần | Ý nghĩa |
| --- | --- |
| `0` trước dấu chấm | Ít nhất một chữ số ở phần nguyên của significand |
| `.` trong pattern | Dấu phân cách thập phân của cú pháp pattern; **kết quả hiển thị** dùng ký hiệu của locale |
| `00` sau dấu chấm | Hai chữ số bắt buộc trong significand |
| `E` | Chuyển sang biểu diễn có số mũ (scientific notation) |
| `0` sau `E` | Ít nhất một chữ số của số mũ; số mũ có thể âm |

Với `Locale.US` và làm tròn HALF_UP được cấu hình, `12345.6789` thành `1.23E4`. Nhân lại để hiểu ý nghĩa: `1.23 × 10^4 = 12300`. Kết quả là **chuỗi đã làm tròn**, không phải phép lưu số mới có đủ độ chính xác của số gốc.

### 2.1. `0` và `#` trong pattern

- `0`: vị trí chữ số **bắt buộc**, thêm chữ số 0 khi hiển thị nếu cần.
- `#`: vị trí chữ số **tùy chọn**, không thêm chữ số 0 không cần thiết.
- `E` nằm giữa pattern của significand và pattern của số mũ.

Ví dụ theo các cấu hình và môi trường dự kiến:

| Pattern | Ý tưởng | Ví dụ với `12345.6789` |
| --- | --- | --- |
| `0.00E0` | Một chữ số nguyên, hai chữ số lẻ bắt buộc | `1.23E4` |
| `0.###E0` | Một chữ số nguyên, tối đa ba chữ số lẻ | `1.235E4` |
| `00.00E00` | Hai chữ số nguyên, hai chữ số lẻ và mũ ít nhất hai chữ số | `12.35E03` |
| `##0.00E0` | Cho phép đến ba chữ số nguyên trong significand; nhóm mũ kiểu engineering | `12.346E3` |

**Chú ý `##0.00E0`:** khi phần nguyên cho phép nhiều hơn một chữ số, `DecimalFormat` có thể định dạng theo **engineering notation** với số mũ bội của số chữ số nguyên tối đa (ở đây là 3). Thuật toán phân bổ số chữ số có nghĩa theo pattern; không thể hiểu máy móc rằng kết quả lúc nào cũng có đúng hai chữ số sau dấu thập phân. Kết quả `12.346E3` của bảng đã được kiểm tra trên JDK.

Cấu hình pattern là quy tắc định dạng; nó **không chuyển** giá trị `BigDecimal` thành `double` trước khi lưu nghiệp vụ. Tuy nhiên chuỗi được format có thể bỏ bớt chữ số do rounding.

### 2.2. Đừng nhầm pattern với chuỗi hiển thị

Pattern `0.00E0` sử dụng dấu `.` theo **cú pháp pattern không bản địa hóa** của `DecimalFormat.applyPattern` hoặc constructor. Nếu định dạng với `Locale.GERMANY`:

~~~java
DecimalFormat german = new DecimalFormat(
        "0.00E0", DecimalFormatSymbols.getInstance(Locale.GERMANY));
~~~

Chuỗi hiển thị cho `12345.6789` với HALF_UP là `1,23E4`, bởi dấu thập phân hiển thị theo locale Đức là dấu phẩy. Từ `Locale` đến ký hiệu chỉ là định dạng; giá trị số gốc vẫn như nhau.

`applyLocalizedPattern(...)` nhận **pattern đã bản địa hóa** và không có cùng quy ước ký tự với `applyPattern(...)`. Để cấu hình ổn định trong source code, ưu tiên pattern chuẩn, truyền `DecimalFormatSymbols` đúng locale và dùng `applyPattern`/constructor dạng trên.

## 3. Scientific notation và engineering notation khác nhau thế nào?

**Scientific notation** thông thường chuẩn hóa significand để chỉ có **một chữ số nguyên khác 0** trước dấu thập phân; số mũ có thể là bất kỳ số nguyên.

Ví dụ:

~~~text
12345.6789  -->  1.23456789E4
0.0000123   -->  1.23E-5
~~~

**Engineering notation** dùng số mũ là **bội số của 3**, thường giữ 1–3 chữ số nguyên trong significand. Nó thuận tiện khi gắn tiền tố SI (milli, micro, kilo, mega) nhưng bản thân formatter **không tự thêm đơn vị hoặc ký hiệu SI**.

~~~text
12345.6789  -->  12.3456789E3
0.0000123   -->  12.3E-6
~~~

Trong `DecimalFormat`, pattern có nhiều vị trí chữ số nguyên tối đa có thể kích hoạt quy tắc engineering. Với `##0.00E0`, giá trị `12345.6789` được format là `12.346E3` trên runtime đã kiểm tra. Số chữ số hiển thị thay đổi theo pattern và quy tắc làm tròn; không nên dùng một pattern bất kỳ rồi tuyên bố luôn giữ nguyên mọi chữ số có nghĩa.

### 3.1. Số chữ số của mũ

Pattern `E00` yêu cầu ít nhất hai chữ số của số mũ. Với `00.00E00`, `12345.6789` trở thành `12.35E03`: số mũ là `03`, giá trị toán học vẫn là nhân `10^3`. Dấu cộng của mũ dương không nhất thiết được thêm tự động; đừng trông đợi `E+03` khi dùng `E00`.

Dấu trừ của mũ âm được format theo ký hiệu và quy ước của formatter. Ví dụ `0.000012345` với `0.00E0` thành `1.23E-5`.

### 3.2. Không phải tất cả pattern hỗ trợ cùng một lượng chữ số

Với biểu diễn dạng khoa học, lượng chữ số có nghĩa tối đa được kiểm soát bởi các vị trí số trong significand. Việc tăng số vị trí giúp giữ thêm chữ số ở **kết quả hiển thị**, nhưng không cứu được độ chính xác **đã mất** trước đó khi giá trị đi qua `float`/`double`.

Một giá trị `double` chỉ chứa một số hữu hạn bit của significand. Đổi pattern từ `0.00E0` sang nhiều chữ số hơn không thể phục hồi chữ số thập phân chính xác mà phép tính nhị phân đã làm tròn.

## 4. Làm tròn khi hiển thị: ảnh hưởng đến significand và số mũ

`DecimalFormat` hỗ trợ các chế độ làm tròn của `java.math.RoundingMode`, ví dụ `HALF_UP`, `HALF_EVEN`, `DOWN`, `UP`. Với yêu cầu rõ ràng, cấu hình tường minh:

~~~java
import java.math.RoundingMode;

scientific.setRoundingMode(RoundingMode.HALF_UP);
~~~

Đây là đoạn minh họa với biến `scientific` kiểu `DecimalFormat`.

- **HALF_UP:** khi cần làm tròn ở điểm giữa, tăng độ lớn chữ số giữ lại.
- **HALF_EVEN:** khi đúng điểm giữa, chọn chữ số cuối chẵn trong phần giữ lại (thường gọi “banker's rounding”).
- **DOWN:** cắt bớt chữ số theo hướng về 0.
- **UNNECESSARY:** yêu cầu không được xảy ra làm tròn; định dạng số cần làm tròn có thể gây `ArithmeticException`.

Ví dụ format `new BigDecimal("12345.6789")` với `0.00E0` và `HALF_UP` ra `1.23E4`. Nếu gần ranh giới như `9.995`, làm tròn có thể tăng significand thành `1.00E1`; vì vậy việc format số mũ và phần trị có liên quan với nhau.

**Cần tách hai phép toán:**

1. **Tính toán và lưu trữ:** giữ `BigDecimal` và scale/chính sách precision phù hợp nghiệp vụ; lựa chọn làm tròn phải được xác định tại tầng nghiệp vụ.
2. **Trình bày:** `DecimalFormat` sinh chuỗi có số chữ số theo pattern và rounding mode để người dùng đọc.

Dùng chuỗi `1.23E4` format ra rồi parse lại để lưu số sẽ không giữ được giá trị ban đầu `12345.6789`; chỉ thu được `12300`. Nếu phải round-trip giá trị gốc, **không** dùng format giới hạn 3 chữ số có nghĩa như kênh truyền dữ liệu chuẩn.

## 5. Giới hạn biểu diễn: double khác BigDecimal, và format không mở rộng miền giá trị

### 5.1. `double` có miền mũ hữu hạn

`double` là kiểu dấu phẩy động IEEE 754 nhị phân 64 bit của Java:

- Số dương hữu hạn lớn nhất khoảng `1.7976931348623157E308` (`Double.MAX_VALUE`).
- Số dương **nhỏ nhất khác 0** là subnormal `Double.MIN_VALUE`, khoảng `4.9E-324`. Đừng nhầm với giá trị âm nhỏ nhất hay `Double.MIN_NORMAL`.
- Khoảng 15–17 chữ số thập phân có nghĩa có thể được biểu diễn/trao đổi tùy trường hợp; số lượng chữ số **chắc chắn chính xác** phụ thuộc vào giá trị, không phải mọi số thập phân đều biểu diễn chính xác.
- Giá trị `NaN`, `POSITIVE_INFINITY`, `NEGATIVE_INFINITY` là các giá trị đặc biệt, không phải số hữu hạn với mọi chữ số mũ có thể có.

Ví dụ:

~~~java
Double.parseDouble("1e309")  // dương vô cùng (Infinity)
Double.parseDouble("1e-325") // 0.0 do underflow dưới miền biểu diễn
~~~

Đây là **các biểu thức minh họa**, không phải một file Java đầy đủ. Trên Java 17, kết quả được xác định bởi quy tắc chuyển chuỗi sang `double` và làm tròn theo IEEE 754. Format ở `DecimalFormat` chỉ nhận giá trị đã có: **không thể** biến Infinity trở lại thành số `1E309`, hoặc khôi phục `1E-325` khi đầu vào đã thành 0.

### 5.2. BigDecimal có phạm vi khác, phù hợp số thập phân chính xác

~~~java
new BigDecimal("1E+309")
new BigDecimal("0.0000000000000000000000000000000001")
~~~

`BigDecimal` xây từ **chuỗi** giữ thông tin thập phân đã cung cấp (trong giới hạn tài nguyên và `scale` của `BigDecimal`). `new BigDecimal("1E+309")` còn là số hữu hạn trong miền `BigDecimal`; định dạng với `0.00E0` cho kết quả `1.00E309` trong ví dụ ở mục 7. Nó không bị chuyển thành vô cùng như `double`.

Không hiểu đây là “độ chính xác vô hạn thực tế”: `BigDecimal` vẫn chịu giới hạn bộ nhớ, `int` scale, độ phức tạp phép tính và `MathContext` nếu được dùng. Các phép chia không kết thúc có thể yêu cầu quy tắc rounding. Muốn tính đúng, chọn kiểu số và precision **trước** khi format.

**Cảnh báo phổ biến:** `new BigDecimal(0.1)` mang theo giá trị thực đã được lưu của `double` 0.1, vốn không bằng đúng số thập phân `0.1`; nếu cần số thập phân dự kiến, dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` theo nhu cầu.

### 5.3. Các ranh giới khi hiển thị

Giới hạn của **kiểu dữ liệu** và giới hạn của **đầu ra chuỗi** khác nhau:

| Mối quan tâm | Giới hạn thực tế | Cách xử lý |
| --- | --- | --- |
| `double` overflow/underflow | Giá trị biến thành Infinity hoặc 0 trước khi format | Chọn kiểu/thuật toán thích hợp từ đầu |
| Precision của `double` | Nhiều số thập phân không được biểu diễn chính xác | Dùng `BigDecimal` cho quy tắc thập phân chính xác |
| Số chữ số hiển thị | Pattern `0.00E0` có thể làm tròn mạnh | Điều chỉnh pattern/rounding tùy mục tiêu |
| `BigDecimal` cực lớn | Bộ nhớ, scale và thời gian xử lý có giới hạn | Giới hạn độ dài input/precision, kiểm soát tài nguyên |
| Số mũ ngoài quy ước UI | Chuỗi có thể khó đọc hoặc vượt yêu cầu sản phẩm | Chọn formatter và chính sách hiển thị rõ ràng |
| `NaN` và vô cùng | Không phải giá trị hữu hạn thông thường | Kiểm tra bằng `Double.isNaN`/`Double.isFinite` trước khi xử lý theo miền nghiệp vụ |

**Không dùng pattern khoa học làm validator**: một chuỗi được parse hoặc format không có nghĩa giá trị phù hợp với miền cho phép (ví dụ độ chính xác đo lường, độ lớn cho phép, hoặc đơn vị).

## 6. Locale và ký hiệu của số mũ

`DecimalFormat` dùng `DecimalFormatSymbols` để quyết định dấu thập phân, dấu âm, chữ số và ký hiệu số mũ:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

DecimalFormat german = new DecimalFormat("0.00E0", symbols);
~~~

Tại JDK có dữ liệu locale Đức phổ biến, `german.format(new BigDecimal("12345.6789"))` với HALF_UP là `1,23E4`. Phần `E` ở **pattern** là cú pháp, còn chuỗi hiển thị sử dụng `DecimalFormatSymbols.getExponentSeparator()`. Bạn cũng có thể tùy biến `setExponentSeparator(String)` cho nhu cầu UI, nhưng phải đảm bảo parser/định dạng thống nhất nếu ứng dụng nhận chuỗi trở lại.

Các ký tự trong kết quả có thể thay đổi giữa JDK/locale provider và phiên bản dữ liệu CLDR. Nếu cần một giao thức **máy đọc** với dạng `1.23E4`, dùng quy ước locale-independent do contract API quyết định (ví dụ `BigDecimal.toString()` hoặc JSON number theo chuẩn), không lấy `DecimalFormat` của locale người dùng làm biểu diễn lưu trữ.

Không dựa vào `Locale.setDefault` mỗi khi có người dùng mới. `Locale.setDefault` ảnh hưởng toàn JVM; hãy truyền `Locale` tường minh ở presenter và tạo formatter riêng cho ngữ cảnh.

## 7. Ví dụ Java 17 hoàn chỉnh và kết quả kiểm chứng

Đặt mã trong **`ScientificDecimalDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ScientificDecimalDemo {
    static DecimalFormat format(String pattern, Locale locale) {
        DecimalFormat result = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(locale));
        result.setRoundingMode(RoundingMode.HALF_UP);
        return result;
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("12345.6789");
        DecimalFormat scientific = format("0.00E0", Locale.US);
        DecimalFormat engineering = format("##0.00E0", Locale.US);
        DecimalFormat twoIntegerDigits = format("00.00E00", Locale.US);

        System.out.println("scientific: " + scientific.format(value));
        System.out.println("engineering: " + engineering.format(value));
        System.out.println("two digits: " + twoIntegerDigits.format(value));
        System.out.println("small: " + scientific.format(
                new BigDecimal("0.000012345")));
        System.out.println("big: " + scientific.format(
                new BigDecimal("1E+309")));

        System.out.println("double overflow: " +
                Double.isInfinite(Double.parseDouble("1e309")));
        System.out.println("double underflow: " +
                (Double.parseDouble("1e-325") == 0.0));

        scientific.setParseBigDecimal(true);
        String text = "1.23E4suffix";
        ParsePosition position = new ParsePosition(0);
        Number parsed = scientific.parse(text, position);
        System.out.println("parsed: " + parsed + "; consumed=" +
                position.getIndex() + "/" + text.length());

        DecimalFormat german = format("0.00E0", Locale.GERMANY);
        System.out.println("german: " + german.format(value));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 ScientificDecimalDemo.java
java ScientificDecimalDemo
~~~

**Stdout đã được đối chiếu** trên Java với dữ liệu locale tương ứng:

~~~text
scientific: 1.23E4
engineering: 12.346E3
two digits: 12.35E03
small: 1.23E-5
big: 1.00E309
double overflow: true
double underflow: true
parsed: 1.23E+4; consumed=6/12
german: 1,23E4
~~~

Phân tích:

1. `0.00E0` hiển thị ba chữ số có nghĩa và dùng số mũ `E4` cho 12345.6789.
2. `##0.00E0` dùng biểu diễn gần engineering, nên `12.346E3` là kết quả có significand hai chữ số nguyên và số mũ bội của 3.
3. `00.00E00` yêu cầu ít nhất hai chữ số nguyên và hai chữ số mũ, nên cho `12.35E03`.
4. Giá trị nhỏ `0.000012345` được thể hiện bằng số mũ âm `E-5`.
5. `BigDecimal("1E+309")` vẫn là số hữu hạn và có thể được format thành `1.00E309`; `Double.parseDouble("1e309")` tràn thành Infinity.
6. `Double.parseDouble("1e-325")` dưới miền `double` và bị làm tròn thành 0.
7. Khi parse `1.23E4suffix`, `DecimalFormat` nhận tiền tố `1.23E4` dài 6 ký tự, trả một `BigDecimal` biểu diễn `12300` và **để lại** 6 ký tự `suffix`. Muốn kiểm tra input toàn phần, phải so `ParsePosition.getIndex()` với độ dài input.
8. Locale Đức đổi dấu thập phân hiển thị thành dấu phẩy, không đổi giá trị `BigDecimal`.

Lưu ý: biểu diễn string của `BigDecimal` sau parse có thể là `1.23E+4`, không nhất thiết là `12300`; cả hai biểu diễn cùng một giá trị. Đoạn demo dùng `Number.toString()` để hiển thị giá trị parse, còn text/locale dùng trong định dạng có quy ước khác nhau.

## 8. Parse notation khoa học: cần kiểm tra toàn bộ chuỗi

Để parse chính xác giá trị có exponent, `DecimalFormat` với pattern khoa học có thể đọc các biểu diễn phù hợp với ký hiệu của locale. Ví dụ trong chương trình:

~~~java
scientific.setParseBigDecimal(true);
ParsePosition position = new ParsePosition(0);
Number number = scientific.parse("1.23E4suffix", position);
~~~

Đây là **đoạn minh họa** dựa trên biến `scientific` đã được tạo ở mục 7, cùng import `ParsePosition`.

`setParseBigDecimal(true)` khuyến khích parser trả `BigDecimal` cho số hữu hạn thông thường, giúp giữ giá trị thập phân đã parse mà không qua chuyển đổi `double`. Không giả định mọi chuỗi đặc biệt `NaN`/Infinity được xử lý như BigDecimal hữu hạn.

**Điều kiện tối thiểu để chấp nhận input:**

~~~java
boolean valid = number != null
        && position.getIndex() == input.length();
~~~

Ở đây `input` là `String` được parse, `number` là kết quả parser, `position` là đối tượng sau parse. Đoạn này yêu cầu **đã tiêu thụ toàn bộ chuỗi**, bởi `parse` có thể dừng trước ký tự không hợp lệ mà không báo lỗi. Nếu parse không bắt đầu được, kết quả có thể `null`; hãy kiểm tra `position.getErrorIndex()` cho vị trí lỗi khi có.

**Giới hạn của việc parse thành công:** ngay cả khi tiêu thụ đủ input, ứng dụng còn phải kiểm tra độ lớn, số chữ số, vùng giá trị, ký hiệu được phép và quy tắc dấu/grouping theo contract riêng. Các parser locale có thể dễ dãi với một số cú pháp; `DecimalFormat` không phải bộ xác thực nghiêm ngặt cho mọi loại dữ liệu nghiệp vụ.

### Khi nào không dùng DecimalFormat để parse?

- Với trường JSON/API dùng quy ước máy đọc cố định, số thập phân không bản địa hóa có thể dùng `new BigDecimal(String)` theo contract, còn `Double.parseDouble` cần xử lý Overflow/Underflow rõ ràng.
- Với nhập liệu từ người dùng có phân cách theo locale, `DecimalFormat` phù hợp hơn nhưng phải kiểm tra toàn chuỗi, kiểu số và miền giá trị.
- Với mã ID, số điện thoại, mã bưu chính hoặc mã thiết bị chứa `E`, không xem là số khoa học; hãy giữ **chuỗi định danh** để tránh mất số 0 đầu và sai ý nghĩa.

## 9. Lỗi thường gặp

| Lỗi | Hậu quả | Giải pháp |
| --- | --- | --- |
| Dùng `DecimalFormat` để “tăng độ chính xác” cho `double` | Chữ số đã mất không thể phục hồi | Chọn `BigDecimal`/thuật toán đúng ở bước tính |
| Đọc `1.23E4` thành `1.23 + 4` | Hiểu sai hoàn toàn giá trị | Mũ nghĩa là nhân `10^4` |
| Tin `0.00E0` giữ toàn bộ chữ số gốc | Formatter làm tròn còn ba chữ số có nghĩa | Tăng precision nếu cần hiển thị, giữ dữ liệu gốc để tính |
| Nhầm `##0.00E0` luôn có hai chữ số lẻ | Pattern engineering phân bổ chữ số theo significand | Kiểm thử các giá trị biên/số mũ |
| Dùng pattern `E` để suy ra mọi locale hiển thị ký tự `E` | Locale symbols có thể khác | Dùng `DecimalFormatSymbols`, kiểm thử UI |
| Gửi `1,23E4` locale Đức cho hệ máy chỉ nhận `1.23E4` | Contract format không khớp | Tách chuỗi hiển thị và biểu diễn máy đọc |
| Dùng `Double.parseDouble("1e309")` như giá trị hữu hạn | Nhận Infinity | Kiểm tra finite và phạm vi hoặc dùng BigDecimal |
| Parse mà bỏ qua `ParsePosition` | Có thể nhận tiền tố của chuỗi lỗi | Yêu cầu tiêu thụ đủ và validate thêm |
| Chia sẻ một `DecimalFormat` mutable giữa các luồng | Định dạng/parse không ổn định | Tạo theo ngữ cảnh, tránh shared mutable state |
| Dùng format → parse để lưu lại số gốc | Mất chữ số vì rounding | Lưu/trao đổi giá trị gốc, định dạng tại UI |
| Hiển thị số cực nhỏ bằng `0.00` rồi xem là giá trị 0 | Thông tin bị mất trên chuỗi hiển thị | Dùng số mũ và lựa chọn precision phù hợp |

## 10. Kiểm thử cần có

Đối với mã dùng ký hiệu khoa học và `DecimalFormat`:

1. **Đúng pattern:** so `0.00E0`, `0.###E0`, `00.00E00`, `##0.00E0` trên cùng giá trị.
2. **Ranh giới exponent:** số gần 1, 10, 1000, số cực nhỏ và số làm tròn có thể đẩy số mũ sang cấp mới.
3. **Rounding:** kiểm tra `HALF_UP`, `HALF_EVEN`, `DOWN`, `UNNECESSARY` với điểm giữa và giá trị âm.
4. **Locale:** `Locale.US`, `Locale.GERMANY`, và locale sản phẩm hỗ trợ; kiểm tra separator, chữ số và dấu âm theo provider mục tiêu.
5. **Biểu diễn dữ liệu:** thử `BigDecimal("1E+309")`, `Double.MAX_VALUE`, `Double.MIN_VALUE`, Infinity, NaN, dương/âm 0.
6. **Parse đầy đủ:** `1.23E4`, `1.23E4suffix`, chuỗi rỗng, exponent lỗi, ký hiệu âm không hợp lệ; kiểm tra `ParsePosition`.
7. **Độ chính xác:** đảm bảo thao tác nghiệp vụ không lấy giá trị đã format/rounded làm nguồn; so giá trị gốc và kết quả hiển thị riêng.
8. **Concurrency:** mỗi thread/request có formatter riêng hoặc cơ chế đồng bộ có kiểm chứng; không thay default locale theo từng request.

Không viết snapshot test toàn bộ chuỗi cho mọi JDK mà không kiểm soát dữ liệu locale provider. Nếu sản phẩm cam kết một định dạng exact, cố định môi trường/test dựa trên contract cụ thể.

## 11. Bài tập thực hành

- Đổi pattern từ `0.00E0` sang `0.00000E0` và kiểm tra lượng chữ số được giữ lại.
- Format `new BigDecimal("9.995")` bằng `0.00E0` với HALF_UP; giải thích tại sao exponent thay đổi khi làm tròn.
- Thử `##0.00E0` trên `123`, `1234`, `12345`, `1234567`; tìm số mũ được dùng, đối chiếu với bội của 3.
- Gọi `format("0.00E0", Locale.GERMANY)` rồi parse một chuỗi có dấu phẩy thập phân; kiểm tra phần đã tiêu thụ.
- Dùng `DecimalFormatSymbols.setExponentSeparator("×10^")` cho giao diện và thử round-trip; lưu ý đây là chuỗi hiển thị, không phải chuẩn JSON number.
- So sánh `Double.parseDouble("1e309")` với `new BigDecimal("1E+309")`, thử thêm trường hợp `1E-325`.
- Viết validator yêu cầu full consumption, miền giá trị `[-1E6, 1E6]` và số chữ số tối đa được nhóm xác định; tách các chính sách đó khỏi parser.
- Tạo một bảng UI hiển thị cùng số ở dạng decimal thường và scientific, nhưng lưu duy nhất `BigDecimal` gốc.

## 12. Kết luận

`DecimalFormat` bật ký hiệu khoa học qua pattern có `E`, ví dụ `0.00E0`. Pattern điều khiển cách phần trị và số mũ được **hiển thị**, còn `DecimalFormatSymbols` và `Locale` điều khiển dấu/ký hiệu dùng cho người đọc. Pattern có nhiều chữ số nguyên tối đa có thể chuyển sang dạng engineering với mũ bội của 3.

Cần nhớ hai ranh giới độc lập: **precision/miền giá trị của số bên trong** (`double`, `BigDecimal`) và **precision của chuỗi hiển thị** (pattern, rounding). Không có formatter nào khôi phục được giá trị đã overflow/underflow hoặc chữ số đã mất. Khi nhận input ở ký hiệu khoa học, parse theo locale phù hợp, kiểm tra đã tiêu thụ đủ chuỗi và xác thực miền giá trị theo nghiệp vụ.

**Tài liệu tham khảo:**

- Java SE 17, `DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE 17, `DecimalFormatSymbols`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html
- Java SE 17, `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `Double`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html
