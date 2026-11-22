# Phân biệt chữ số tối thiểu, tối đa và độ chính xác giá trị trong Java

Một hệ thống có thể yêu cầu in **tối thiểu hai chữ số sau dấu thập phân**, in **không quá bốn chữ số** hoặc tính toán với **ba chữ số có nghĩa**. Ba khái niệm này không đồng nhất. Java có các API để kiểm soát **chuỗi hiển thị** như `DecimalFormat`, `String.format`, `printf`, và những API tạo **giá trị thập phân đã làm tròn** như `BigDecimal.setScale` hay `MathContext`.

Điều quan trọng nhất: **định dạng ít chữ số không làm giảm hay tăng độ chính xác của giá trị gốc đang được lưu**. Ngược lại, một giá trị `double` đã chứa sai số nhị phân vẫn sai số như cũ ngay cả khi in ra `0.30`. Bài Knowledge này thuộc phần **Biểu diễn và định dạng** trong Java Core, tập trung vào minimum/maximum digits, precision, scale, width và cách tránh nhầm lẫn khi lưu/xuất dữ liệu.

## 1. Khái niệm cốt lõi

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Minimum fraction digits | Tối thiểu bao nhiêu chữ số *sau dấu thập phân* khi in | `1.2` → `1.20` |
| Maximum fraction digits | Tối đa bao nhiêu chữ số sau dấu thập phân khi in | `1.234567` → `1.2346` khi max = 4 |
| Minimum integer digits | Đệm đủ chữ số *phần nguyên* khi in | `12.5` → `0012.50` |
| Maximum integer digits | Giới hạn số chữ số nguyên khi định dạng | Có thể **bỏ các chữ số cao**, rất nguy hiểm |
| Formatter width | Độ rộng tối thiểu **toàn chuỗi** gồm dấu, số 0 và khoảng trắng | `%8.2f` cho `"    1.20"` |
| Formatter precision | Số chữ số sau dấu thập phân của `%f` hoặc số chữ số có nghĩa của `%g` | `%.2f` khác `%.2g` |
| `BigDecimal.scale()` | Số mũ thập phân trong giá trị `unscaledValue × 10^(-scale)` | `12.3456` có scale 4 |
| `BigDecimal.precision()` | Số chữ số thập phân có nghĩa của unscaled value | `12.3456` có precision 6 |
| `MathContext.precision` | Giới hạn chữ số có nghĩa của **kết quả phép toán BigDecimal** | Làm tròn `12.3456` thành `12.3` khi precision 3 |

Các thuộc tính format quyết định hình thức xuất ra; độ chính xác số học còn phụ thuộc kiểu dữ liệu, biểu diễn đầu vào, thứ tự các phép tính và chính sách làm tròn. Một biểu thức chứa 10 chữ số sau dấu phẩy không tự bảo đảm 10 chữ số đó đều đáng tin về mặt đo lường.

## 2. `DecimalFormat`: ký tự `0` bắt buộc, `#` tùy chọn

`java.text.DecimalFormat` tạo chuỗi biểu diễn số theo một pattern. Hai ký hiệu cơ bản:

- `0`: vị trí chữ số bắt buộc; có thể in thêm số 0 nếu thiếu.
- `#`: vị trí tùy chọn; không cần in số 0 thừa.
- `.`: dấu phân cách thập phân ở biểu thức pattern.
- `,`: xác định nhóm chữ số, ký tự thực tế tùy `Locale` và `DecimalFormatSymbols`.

Ví dụ:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.ROOT);
DecimalFormat formatter = new DecimalFormat("0.00##", symbols);
formatter.setRoundingMode(RoundingMode.HALF_EVEN);

System.out.println(formatter.format(1.2));      // 1.20
System.out.println(formatter.format(1.234567)); // 1.2346
System.out.println(formatter.format(12));       // 12.00
~~~

Pattern `0.00##` có **min = 2** và **max = 4** chữ số phần thập phân. Số `1.2` được đệm thêm số 0 để in `1.20`, còn `1.234567` được làm tròn thành **chuỗi** `1.2346`.

Đọc các giới hạn ngay từ formatter:

~~~java
int minimum = formatter.getMinimumFractionDigits(); // 2
int maximum = formatter.getMaximumFractionDigits(); // 4
~~~

Pattern `0.0#` có min 1, max 2:

~~~java
DecimalFormat f = new DecimalFormat("0.0#", symbols);
f.format(1);     // "1.0"
f.format(1.23);  // "1.23"
f.format(1.234); // "1.23"
~~~

**Maximum khác minimum:** khi thiếu số lẻ, các vị trí `0` buộc xuất hiện; khi có ít chữ số lẻ, các vị trí `#` có thể bị bỏ. Nếu cần làm tròn phần dư, formatter tuân theo `RoundingMode` đã cấu hình. Nó không làm biến nguồn thay đổi.

## 3. Setter minimum/maximum fraction digits dùng khi nào?

Ngoài pattern, ta có thể cấu hình:

~~~java
DecimalFormat f = new DecimalFormat("0", symbols);
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(4);
f.setRoundingMode(RoundingMode.HALF_EVEN);
// f.format(1.2)      -> "1.20"
// f.format(1.234567) -> "1.2346"
~~~

`getMinimumFractionDigits` và `getMaximumFractionDigits` giúp kiểm tra cấu hình cuối. `NumberFormat` duy trì tính nhất quán giữa minimum và maximum; khi đặt giá trị vượt ràng buộc còn lại, setter có thể điều chỉnh cả giới hạn đối diện. Vì vậy nếu cấu hình được thay đổi động, **đọc lại cả min lẫn max** để kiểm tra.

`DecimalFormat` là mutable và không bảo đảm an toàn khi chia sẻ cùng instance để dùng đồng thời giữa các thread mà không đồng bộ. Có thể tạo instance riêng cho mỗi khu vực sử dụng hoặc quản lý vòng đời phù hợp.

**Chú ý:** “max = 2” không có nghĩa kiểu `double` đã được lưu chính xác đến hai chữ số. Nó chỉ tạo biểu diễn trông như có nhiều nhất hai chữ số sau dấu thập phân.

## 4. Integer digits: đệm số 0 có thể đúng, cắt chữ số cao rất nguy hiểm

`minimumIntegerDigits` quy định số vị trí tối thiểu phần nguyên:

~~~java
DecimalFormat padded = new DecimalFormat("0000.00", symbols);
System.out.println(padded.format(12.5)); // 0012.50
~~~

Trong ví dụ, phần nguyên `12` được đệm thêm hai số 0. Đây là trình bày, không chuyển kiểu số thành một object mang 4 chữ số nguyên cố định. Nếu `0012` là mã định danh và các số 0 đầu mang ý nghĩa, nên lưu mã **dạng chuỗi**, không chỉ lưu `int 12`.

`maximumIntegerDigits` là một bẫy khác. Khi bị giới hạn, `DecimalFormat` có thể **loại bỏ các chữ số có trọng số cao**:

~~~java
DecimalFormat limited = new DecimalFormat("0", symbols);
limited.setMaximumIntegerDigits(3);
System.out.println(limited.format(12345)); // 345
~~~

Không dùng `setMaximumIntegerDigits(3)` để “làm tròn” hay “thu gọn” số lớn. Nếu màn hình quá hẹp, hãy xử lý layout hoặc dùng một quy ước rõ ràng (ví dụ biểu diễn theo nghìn kèm đơn vị), không âm thầm biến `12345` thành `345`.

Maximum integer digits cũng không dùng để kiểm tra overflow hay xác thực đầu vào. Hợp đồng giới hạn giá trị phải được kiểm tra trên **giá trị số gốc**, không phải chuỗi rút gọn.

## 5. `Formatter` width khác precision

`String.format` và `System.out.printf` dùng `java.util.Formatter`. Cú pháp cơ bản là `%[flags][width][.precision]conversion`:

| Format | Ý nghĩa | Kết quả ví dụ |
| --- | --- | --- |
| `%.2f` | Chính xác hai chữ số **sau dấu thập phân trong chuỗi** | `1.23456` → `"1.23"` |
| `%8.2f` | Tối thiểu 8 ký tự, 2 chữ số lẻ | `1.2` → `"    1.20"` |
| `%.3g` | Ba chữ số có nghĩa của chuỗi số thực (định dạng tổng quát) | `12345.678` → `"1.23e+04"` |
| `%d` | Số nguyên | Không dùng dot-precision như `%f` |

~~~java
String width = String.format(Locale.ROOT, "%8.2f", 1.2);
String fixed = String.format(Locale.ROOT, "%.2f", 1.23456);
String significant = String.format(Locale.ROOT, "%.3g", 12345.678);
~~~

Kết quả là `"    1.20"`, `"1.23"`, `"1.23e+04"` tương ứng.

**Width** là độ rộng tối thiểu theo ký tự của toàn trường in, kể cả dấu, số lẻ và khoảng trắng; nếu chuỗi số dài hơn width, formatter có thể in dài hơn chứ không mặc định cắt dữ liệu.

**Precision của `%f`** là chữ số sau dấu thập phân; **precision của `%g`** là số chữ số có nghĩa trong cách trình bày. Không dùng chúng thay thế cho nhau. Đặc biệt `%.2f` không hề nói rằng giá trị gốc `1.23456` đã bị gán lại thành số `1.23`.

Các format dùng `Locale` có thể chọn dấu chấm hoặc dấu phẩy theo vùng. Khi nội dung cần máy đọc với kết quả ổn định, hãy chỉ định một locale thích hợp như `Locale.ROOT`. Với giao diện cho người dùng, dùng locale đúng ngôn ngữ/thị trường.

## 6. Độ chính xác lưu trữ của `float` và `double`

`float`/`double` là dấu phẩy động nhị phân IEEE 754 với độ chính xác hữu hạn: binary32 có 24 bit precision phần trị, binary64 có 53 bit. Một số decimal như `0.1`, `0.2` không biểu diễn được chính xác bằng số lượng bit hữu hạn này.

~~~java
double sum = 0.1 + 0.2;

System.out.println(sum); // 0.30000000000000004
System.out.println(
        String.format(Locale.ROOT, "%.2f", sum)); // 0.30
System.out.println(sum); // vẫn 0.30000000000000004
~~~

`String.format` tạo `String` mới và **không sửa giá trị `double` đang lưu**. Vì vậy các so sánh, tổng, thuật toán downstream vẫn sử dụng giá trị gốc. Số chữ số hiển thị nhiều hay ít không tự sửa được sai số được tạo ra bởi biểu diễn nhị phân và thứ tự tính toán.

`Double.toString` tạo biểu diễn thập phân ngắn phù hợp round-trip theo hợp đồng API, chứ không in mọi chữ số thập phân của giá trị binary64 đang lưu. Có thể dùng `new BigDecimal(double)` để khảo sát khai triển decimal chính xác của giá trị bit, nhưng đó không phải cùng khái niệm với số decimal mà người dùng dự định nhập.

Khi số thực đi từ hệ thống này sang hệ thống khác, xuất dữ liệu với giới hạn chữ số tùy tiện có thể làm mất thông tin. Để round-trip một giá trị `double`, dùng `Double.toString` kết hợp parser phù hợp hoặc một giao thức có đảm bảo tương đương; đừng tự chọn `%.2f` chỉ vì thấy dễ đọc.

## 7. `BigDecimal.precision()` và `scale()` không phải min/max digits

`BigDecimal` lưu số decimal dựa trên unscaled integer và scale: `value = unscaledValue × 10^(-scale)`.

Với:

~~~java
BigDecimal number = new BigDecimal("12.3456");
System.out.println(number.precision()); // 6
System.out.println(number.scale());     // 4
~~~

- **`precision() = 6`**: sáu chữ số có nghĩa của giá trị unscaled theo quy tắc `BigDecimal`.
- **`scale() = 4`**: số mũ decimal cần dùng để diễn giải unscaled value thành `12.3456`.

Scale không luôn là “số chữ số sau dấu thập phân” theo nghĩa chuỗi: scale có thể bằng **0 hoặc âm**, ví dụ sau khi chuẩn hóa số có số 0 đuôi. Precision không phải là sai số thực tế của phép đo hoặc số chữ số cần trình bày. Các thuộc tính này nằm trong **giá trị BigDecimal**, còn `DecimalFormat` quản lý **chuỗi khi in**.

Nếu đo lường ghi “độ chính xác ±0.01”, đó là thông tin về thiết bị và sai số/độ bất định của phép đo; không tự suy ra từ `precision()`. Cần mô hình hóa ràng buộc này trong miền nghiệp vụ.

## 8. `setScale` so với `MathContext` precision

Một `BigDecimal` có thể được làm tròn và lưu thành giá trị mới theo hai tiêu chí:

~~~java
BigDecimal value = new BigDecimal("12.3456");

BigDecimal byFractionPosition =
        value.setScale(2, RoundingMode.HALF_UP); // 12.35

BigDecimal bySignificantDigits =
        value.round(new MathContext(3, RoundingMode.HALF_UP)); // 12.3
~~~

**`setScale(2, ...)`** giữ hai vị trí lẻ theo quy tắc làm tròn. **`MathContext(3, ...)`** giữ ba chữ số có nghĩa của kết quả, tính cả phần nguyên. Với số có độ lớn khác, vị trí làm tròn tương ứng sẽ thay đổi.

Đây là **thao tác lên giá trị**, khác `DecimalFormat.format`:

~~~java
BigDecimal original = new BigDecimal("12.3456");
DecimalFormat f = new DecimalFormat("0.00", symbols);
f.setRoundingMode(RoundingMode.HALF_UP);
String shown = f.format(original); // "12.35"
// original vẫn là 12.3456
~~~

`BigDecimal` immutable: `round` và `setScale` trả một object mới, object nguồn không bị thay đổi. Muốn ghi vào sổ sách giá trị có scale 2, phải **lưu object kết quả** chứ không chỉ format object gốc.

Quy tắc `RoundingMode.HALF_EVEN` và `HALF_UP` không luôn cho kết quả giống nhau ở điểm giữa. Nếu nghiệp vụ cần tiền tệ, thuế hoặc phân bổ, hãy xác định rõ thời điểm làm tròn và rounding mode. Với `RoundingMode.UNNECESSARY`, một phép chuyển cần làm tròn có thể ném `ArithmeticException` thay vì âm thầm làm mất thông tin.

## 9. Chương trình Java 17+ chạy độc lập và stdout chính xác

Tạo tệp `DigitFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitFormatDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        DecimalFormat range = new DecimalFormat("0.00##", symbols);
        range.setRoundingMode(RoundingMode.HALF_EVEN);

        System.out.println("min fraction = "
                + range.getMinimumFractionDigits());
        System.out.println("max fraction = "
                + range.getMaximumFractionDigits());
        System.out.println("range 1.2 = " + range.format(1.2));
        System.out.println("range 1.234567 = "
                + range.format(1.234567));
        System.out.println("range 12 = " + range.format(12));

        DecimalFormat padded = new DecimalFormat("0000.00", symbols);
        System.out.println("padded 12.5 = " + padded.format(12.5));

        DecimalFormat optional = new DecimalFormat("0.0#", symbols);
        System.out.println("optional 1 = " + optional.format(1));
        System.out.println("optional 1.23 = " + optional.format(1.23));
        System.out.println("optional 1.234 = "
                + optional.format(1.234));

        DecimalFormat group = new DecimalFormat("#,##0.###", symbols);
        System.out.println("group 12345.6789 = "
                + group.format(12345.6789));

        System.out.println("width = |"
                + String.format(Locale.ROOT, "%8.2f", 1.2)
                + "|");
        System.out.println("f 1.23456 = "
                + String.format(Locale.ROOT, "%.2f", 1.23456));
        System.out.println("g 12345.678 = "
                + String.format(Locale.ROOT, "%.3g", 12345.678));

        BigDecimal original = new BigDecimal("12.3456");
        System.out.println("decimal original = " + original);
        System.out.println("formatted decimal = " + range.format(original));
        System.out.println("decimal after format = " + original);
        System.out.println("setScale(2) = "
                + original.setScale(2, RoundingMode.HALF_UP));
        System.out.println("MathContext(3) = "
                + original.round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("decimal precision = " + original.precision());
        System.out.println("decimal scale = " + original.scale());

        double sum = 0.1 + 0.2;
        System.out.println("double raw = " + sum);
        System.out.println("double display = "
                + String.format(Locale.ROOT, "%.2f", sum));
        System.out.println("double still raw = " + sum);

        DecimalFormat limited = new DecimalFormat("0", symbols);
        limited.setMaximumIntegerDigits(3);
        System.out.println("max integer 3 of 12345 = "
                + limited.format(12345));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DigitFormatDemo.java
java DigitFormatDemo
~~~

Kết quả:

~~~text
min fraction = 2
max fraction = 4
range 1.2 = 1.20
range 1.234567 = 1.2346
range 12 = 12.00
padded 12.5 = 0012.50
optional 1 = 1.0
optional 1.23 = 1.23
optional 1.234 = 1.23
group 12345.6789 = 12,345.679
width = |    1.20|
f 1.23456 = 1.23
g 12345.678 = 1.23e+04
decimal original = 12.3456
formatted decimal = 12.3456
decimal after format = 12.3456
setScale(2) = 12.35
MathContext(3) = 12.3
decimal precision = 6
decimal scale = 4
double raw = 0.30000000000000004
double display = 0.30
double still raw = 0.30000000000000004
max integer 3 of 12345 = 345
~~~

Hai dòng đầu cho thấy cấu hình min/max thực tế. Các dòng `range`, `optional` và `group` minh họa formatter. `width` và `g` phân biệt các loại precision/width. Các dòng `BigDecimal` cho thấy formatter không thay đổi object, còn `setScale`/`MathContext` tạo kết quả riêng. Cặp `double raw`/`double display` chứng minh việc chỉ rút ngắn bản in không đổi dữ liệu gốc.

## 10. Format rồi parse có phải đang làm tròn giá trị không?

Giả sử:

~~~java
double original = 1.234567;
String displayed = String.format(Locale.ROOT, "%.2f", original);
// displayed = "1.23"
double reparsed = Double.parseDouble(displayed);
// reparsed biểu diễn gần 1.23, khác original
~~~

Nếu bạn **gán `reparsed` vào biến**, chương trình thực sự có giá trị mới, nhưng đó là hậu quả của việc tự **format rồi parse lại**, không phải formatter làm thay đổi biến cũ. Cách này còn có nguy cơ:

- Làm mất thông tin vì nhiều giá trị gốc trở thành một chuỗi rút ngắn.
- Đưa vào phụ thuộc locale, nhóm chữ số và dấu thập phân.
- Vẫn có sai số binary64 ở giá trị được parse lại.
- Thay đổi thuật toán nếu áp dụng làm tròn theo chuỗi sau mỗi bước tính.

Đừng dùng mẹo này như phương pháp tổng quát để cải thiện độ chính xác. Nếu yêu cầu là lượng tử hóa số decimal, dùng kiểu decimal và chính sách tính toán; nếu yêu cầu là hiển thị, chỉ format ở bước xuất.

## 11. Tình huống ứng dụng và quyết định đúng

**Hiển thị điểm số:** Điểm gốc `9.5`, báo cáo cần hai chữ số sau dấu thập phân. `DecimalFormat("0.00")` hiển thị `9.50`. Số 0 thêm không chứng minh phép chấm chính xác hơn, cũng không thay đổi điểm gốc.

**Giao diện cảm biến:** Số đo `12.3456` nhưng màn hình chỉ đủ hiển thị `12.35`. Formatter có thể dùng maximum fraction digits = 2. Hệ thống cần giữ giá trị thô và độ bất định của thiết bị nếu mục tiêu là phân tích kỹ thuật.

**Hóa đơn:** Dữ liệu decimal `12.3456` phải được làm tròn thành `12.35` trước khi lưu. Chọn `BigDecimal#setScale(2, roundingMode)` và lưu **giá trị kết quả**, không chỉ format nguồn. Quy tắc tài chính cần nói rõ làm tròn tại dòng, tại tổng hay tại lúc thanh toán.

**Mã đơn hàng:** Mã `0012` cần giữ số 0 đầu để so khớp. Lưu `String` thay vì chỉ lưu `int 12` rồi cố phục hồi bằng minimumIntegerDigits.

**Số lớn:** `setMaximumIntegerDigits(3)` biến `12345` thành bản in `345`. Nếu cần bản xem ngắn, dùng cách viết rõ đơn vị (ví dụ 12.3 nghìn) và quy tắc giao diện cụ thể, không cắt bit có nghĩa mà không báo.

**Trao đổi dữ liệu:** Nếu bên nhận phải có đúng dữ liệu số `double`, ưu tiên định dạng round-trip có bảo đảm. Nếu bên nhận yêu cầu một decimal amount với scale bắt buộc, xác định quy tắc `BigDecimal`/serialization riêng. Một chuỗi hiển thị hai chữ số thập phân không thay thế hai hợp đồng ấy.

## 12. Lỗi thường gặp

1. **Cho rằng minimum fraction digits = 2 khiến giá trị chính xác hơn.** Nó chỉ thêm số 0 vào chuỗi nếu cần.
2. **Nhầm maximum fraction digits với precision của kiểu `double`.** Chuỗi ngắn không sửa giá trị lưu.
3. **Nhầm `%.2f` với `%.2g`.** `%f` kiểm soát chữ số phần lẻ; `%g` kiểm soát chữ số có nghĩa của cách in.
4. **Nhầm `%8.2f` là tám chữ số.** Tám là độ rộng tối thiểu tính bằng ký tự.
5. **Tự đặt maximum integer digits quá nhỏ.** Có thể bỏ chữ số đầu, gây hiển thị số sai về giá trị.
6. **Nhầm `BigDecimal.scale()` với `precision()`.** Một thuộc tính là số mũ decimal, thuộc tính kia đếm chữ số có nghĩa của unscaled value.
7. **Cho rằng `MathContext(3)` là ba số lẻ.** Nó chỉ ba chữ số có nghĩa tổng cộng.
8. **Gọi `BigDecimal#setScale` nhưng không nhận kết quả.** `BigDecimal` bất biến.
9. **Không chỉ định quy tắc làm tròn ở điểm quan trọng.** `HALF_EVEN` và `HALF_UP` có thể khác nhau.
10. **Dùng formatter chung đa luồng một cách tùy tiện.** `DecimalFormat` mutable và không thread-safe theo cách dùng chung không bảo vệ.
11. **Dùng format/parse để “sửa” sai số.** Có thể loại bỏ thông tin, lại tạo một `double` xấp xỉ.
12. **Không kiểm soát locale.** Dấu phân cách decimal khác nhau có thể phá giao thức hoặc kiểm thử.
13. **Tưởng precision lưu là chất lượng phép đo.** Độ bất định của phép đo không tự được biểu diễn bởi số chữ số của object.

## 13. Tự kiểm tra

**1.** `DecimalFormat("0.00##")` in `1.2` thế nào, và phần lẻ có giới hạn ra sao?

**Đáp án:** `1.20`; minimum = 2, maximum = 4. Nếu cần nhiều hơn 4 số lẻ để biểu diễn thì formatter làm tròn khi tạo chuỗi.

**2.** `String.format(Locale.ROOT, "%8.2f", 1.2)` chứa tám chữ số hay tám ký tự?

**Đáp án:** Tám **ký tự** tối thiểu, kết quả gồm bốn dấu cách và `1.20`.

**3.** Vì sao `%.3g` khác `%.3f`?

**Đáp án:** `%g` tập trung vào ba chữ số có nghĩa, còn `%f` vào ba chữ số sau dấu thập phân.

**4.** `new BigDecimal("12.3456")` có precision và scale bằng bao nhiêu?

**Đáp án:** Precision = 6 và scale = 4. Định dạng ít chữ số không thay đổi thuộc tính của object.

**5.** So sánh `setScale(2, HALF_UP)` và `round(new MathContext(3, HALF_UP))` trên `12.3456`.

**Đáp án:** Kết quả `12.35` và `12.3`. Một cái giữ 2 vị trí thập phân, một cái giữ 3 chữ số có nghĩa.

**6.** Vì sao `setMaximumIntegerDigits(3)` không phù hợp để thu gọn `12345`?

**Đáp án:** Có thể in thành `345`, bỏ các chữ số có trọng số cao khiến người dùng tưởng là một số khác.

**7.** `String.format("%.2f", 0.1 + 0.2)` có làm phép cộng trở nên chính xác `0.3` không?

**Đáp án:** Không. Nó chỉ in `0.30`; giá trị `double` gốc vẫn `0.30000000000000004`.

## Tài liệu tham khảo

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): pattern `0`/`#`, các giới hạn chữ số, cách làm tròn.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): minimum/maximum integer/fraction digits.
- [Java SE 21 — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html): width và precision của các conversion `%f` và `%g`.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `setScale`.
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision là số chữ số có nghĩa của phép toán.
- [JLS `4.2.3 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
