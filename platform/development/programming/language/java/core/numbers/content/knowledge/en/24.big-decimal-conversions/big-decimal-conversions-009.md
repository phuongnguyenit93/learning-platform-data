# BigDecimal: phân biệt giá trị tính toán với scale trình bày

Trong Java, khi một phép tính `BigDecimal` cho ra `13.000` nhưng giao diện cần hiển thị `13.00`, câu hỏi cần trả lời là: **giá trị số cần thay đổi, hay chỉ số chữ số được trình bày cần thay đổi?** Hai nhu cầu này có thể dẫn đến những thao tác khác nhau, thậm chí kết quả lưu trữ và cách kiểm tra bằng nhau khác nhau.

Bài học thuộc chủ đề **Chuyển đổi BigDecimal** và tập trung vào ranh giới giữa **giá trị tính toán**, **biểu diễn thập phân/`scale`**, **quy tắc làm tròn** và **chuỗi hiển thị**. Ví dụ dùng Java 17+ và chuỗi đầu vào thập phân để tránh sai số do chuyển đổi `double` không cần thiết.

## 1. Ba lớp khái niệm cần phân biệt

1. **Giá trị số (numeric value):** đại lượng toán học mà `BigDecimal` biểu diễn, chẳng hạn 13; 13.0; 13.00 đều có cùng giá trị số.
2. **Biểu diễn `BigDecimal`:** cặp số nguyên `unscaledValue` và `scale`. Các cách viết cùng giá trị có thể có `scale` khác nhau. `scale` là thuộc tính của đối tượng, không đơn thuần là lựa chọn phông chữ hay định dạng màn hình.
3. **Chuỗi trình bày:** các ký tự người dùng nhìn thấy: `13`, `13.00`, `13,00`, `1,000.00` hoặc `1E+3`. Quy tắc này có thể phụ thuộc locale, đơn vị, quy ước sản phẩm và đối tượng nhận dữ liệu.

Công thức nội tại của `BigDecimal`:

~~~text
numeric value = unscaledValue × 10^(-scale)
~~~

Ví dụ:

| Khởi tạo | Giá trị số | `unscaledValue()` | `scale()` | `toString()` |
|---|---:|---:|---:|---|
| `new BigDecimal("13")` | 13 | 13 | 0 | `13` |
| `new BigDecimal("13.0")` | 13 | 130 | 1 | `13.0` |
| `new BigDecimal("13.00")` | 13 | 1300 | 2 | `13.00` |
| `new BigDecimal("1.3E+1")` | 13 | 13 | 0 | `13` |
| `new BigDecimal("1E+3")` | 1000 | 1 | -3 | `1E+3` |

Lưu ý dòng `"1.3E+1"`: `BigDecimal` phân tích chuỗi khoa học thành một giá trị có `unscaledValue = 13` và `scale = 0`, nên `toString()` của đối tượng là `13`. Chuỗi đầu vào ban đầu không được giữ nguyên như một nhãn hiển thị riêng.

Hai `BigDecimal` có cùng **giá trị số** khi `compareTo() == 0`. Phương thức `equals()` đòi hỏi thêm `scale` bằng nhau:

~~~java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.300");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

Vì vậy, câu "hai số bằng nhau" phải chỉ rõ là **bằng theo toán học** hay **bằng theo biểu diễn `BigDecimal`**.

## 2. Giá trị tính toán và scale sau phép toán

`BigDecimal` hỗ trợ các phép tính thập phân chính xác (trong giới hạn toán tử, precision/rounding và tài nguyên), nhưng **kết quả phép tính vẫn có `scale`**. Với các phép tính chính xác không dùng `MathContext`, Java có quy tắc `scale` ưu tiên:

| Phép tính | `scale` ưu tiên |
|---|---|
| `a.add(b)` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |
| `a.divide(b)` chính xác | `a.scale() - b.scale()` nếu đủ; phép chia có thể cần scale lớn hơn để biểu diễn thương chính xác |
| `a.scaleByPowerOfTen(n)` | `a.scale() - n` và **giá trị số nhân với `10^n`** |

Các quy tắc này mô tả **biểu diễn của kết quả**; chúng không tự quyết định giao diện phải in bao nhiêu chữ số. Với phép chia có kết quả thập phân vô hạn như `1 / 3`, `divide(BigDecimal)` không rounding có thể ném `ArithmeticException`. Khi đó phải chọn overload `divide` có `scale`/`RoundingMode` hoặc `MathContext` tùy ý nghĩa tính toán.

Ví dụ:

~~~java
BigDecimal quantity = new BigDecimal("12.30"); // scale 2
BigDecimal extra = new BigDecimal("0.700");   // scale 3
BigDecimal total = quantity.add(extra);

System.out.println(total);         // 13.000
System.out.println(total.scale()); // 3
~~~

Tổng số học là **13**, còn đối tượng kết quả biểu diễn ở **scale 3**. Việc màn hình cần hiện `13.00` là một yêu cầu khác với phép cộng vừa thực hiện.

**`precision()` không phải `scale()`:** `precision` là số chữ số trong phần không có dấu thập phân của biểu diễn, còn `scale` cho biết bậc thập phân. Ví dụ `123.4500` có `precision = 7` và `scale = 4`. `MathContext(5)` đặt giới hạn chữ số có nghĩa cho phép tính có context, không có nghĩa hiển thị đúng 5 chữ số sau dấu thập phân.

## 3. Những API nào đổi giá trị, API nào đổi biểu diễn?

| Thao tác | Có thể đổi **giá trị số**? | Ảnh hưởng `scale` và cách hiển thị |
|---|---|---|
| `value.setScale(2)` | Không, nếu biểu diễn chính xác được; nếu không thì ném ngoại lệ | Chỉnh `scale` thành 2 |
| `value.setScale(2, RoundingMode.HALF_UP)` | **Có** khi phải làm tròn | `scale = 2`, có thể bỏ hoặc tăng chữ số giá trị |
| `value.stripTrailingZeros()` | **Không** | Bỏ các số 0 tận cùng; `scale` có thể giảm và trở thành âm |
| `value.toString()` | **Không** | Trả chuỗi canonical, có thể dùng dạng khoa học |
| `value.toPlainString()` | **Không** | Trả chuỗi không dùng số mũ, không bắt buộc có số chữ số thập phân cố định |
| `DecimalFormat.format(value)` | Không thay đổi đối tượng đầu vào | Tạo chuỗi đã định dạng, có thể làm tròn cho mục đích hiển thị |
| `value.movePointLeft(n)` | **Có** nếu `n != 0` và giá trị khác 0 | Chia cho `10^n`, đồng thời thay `scale` |
| `value.movePointRight(n)` | **Có** nếu `n != 0` và giá trị khác 0 | Nhân với `10^n`, đồng thời thay `scale` |
| `value.scaleByPowerOfTen(n)` | **Có** nếu `n != 0` và giá trị khác 0 | Nhân với `10^n`, giữ kết quả `scale` âm khi cần |
| `value.round(MathContext)` | Có thể, nếu phải làm tròn chữ số có nghĩa | `precision` và `scale` sau rounding phụ thuộc kết quả |

Không nhìn vào tên `scaleByPowerOfTen` rồi cho rằng nó chỉ điều khiển "format": phương thức này **thực sự nhân/chia giá trị số** theo lũy thừa của 10. Ngược lại, gọi `toPlainString()` không nhân/chia và không tạo một `BigDecimal` đã được đổi `scale`.

## 4. setScale: giữ nguyên số nếu có thể, làm tròn nếu bắt buộc

`setScale(int newScale)` yêu cầu một biểu diễn có `scale` mới **mà không được thay đổi giá trị số**. Nếu đổi `scale` cần bỏ chữ số khác 0, overload này ném `ArithmeticException`.

~~~java
BigDecimal source = new BigDecimal("13.000");

System.out.println(source.setScale(2)); // 13.00
System.out.println(source.setScale(1)); // 13.0
System.out.println(source.setScale(0)); // 13
~~~

Cả ba kết quả đều bằng số học với `source`. Nhưng với `new BigDecimal("13.005").setScale(2)`, việc loại chữ số 5 làm đổi giá trị; vì thế Java **không âm thầm cắt bỏ** mà ném ngoại lệ.

Khi nghiệp vụ cho phép làm tròn, chọn `RoundingMode` **tường minh**:

~~~java
BigDecimal original = new BigDecimal("2.005");

System.out.println(
        original.setScale(2, RoundingMode.HALF_UP)
); // 2.01

System.out.println(
        original.setScale(2, RoundingMode.HALF_EVEN)
); // 2.00
~~~

Các kết quả trên khác giá trị số 2.005: **làm tròn là quyết định của miền nghiệp vụ**, không còn là lựa chọn hiển thị thuần túy nếu lấy kết quả làm đầu vào phép tính tiếp theo.

Chọn `RoundingMode.UNNECESSARY` khi muốn khẳng định phép chuyển phải chính xác: phương thức sẽ báo lỗi nếu phải làm tròn. Với tiền tệ hoặc đo lường, không chọn một quy tắc rounding chỉ vì đầu ra trông đẹp; phải theo hợp đồng nghiệp vụ.

## 5. Ví dụ Java 17+: cùng giá trị, nhiều dạng biểu diễn

Tạo tệp `BigDecimalValueDisplayDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class BigDecimalValueDisplayDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.30");
        BigDecimal b = new BigDecimal("12.300");

        System.out.println("a: " + a + " | scale=" + a.scale());
        System.out.println("b: " + b + " | scale=" + b.scale());
        System.out.println("value equal: " + (a.compareTo(b) == 0));
        System.out.println("representation equal: " + a.equals(b));

        BigDecimal total = a.add(new BigDecimal("0.700"));
        System.out.println("sum: " + total + " | scale=" + total.scale());
        System.out.println("normalized: " + total.stripTrailingZeros()
                + " | scale=" + total.stripTrailingZeros().scale());
        System.out.println("fixed: " + total.setScale(2)
                + " | scale=" + total.setScale(2).scale());

        BigDecimal scientific = new BigDecimal("1E+3");
        System.out.println("notation: " + scientific.toString());
        System.out.println("plain: " + scientific.toPlainString());
        System.out.println("scientific scale: " + scientific.scale());

        DecimalFormat display = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        display.setRoundingMode(RoundingMode.HALF_UP);

        BigDecimal amount = new BigDecimal("1234.5");
        System.out.println("display: " + display.format(amount));
        System.out.println("original after format: " + amount);
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac BigDecimalValueDisplayDemo.java
java BigDecimalValueDisplayDemo
~~~

Kết quả:

~~~text
a: 12.30 | scale=2
b: 12.300 | scale=3
value equal: true
representation equal: false
sum: 13.000 | scale=3
normalized: 13 | scale=0
fixed: 13.00 | scale=2
notation: 1E+3
plain: 1000
scientific scale: -3
display: 1,234.50
original after format: 1234.5
~~~

Giải thích:

- `a` và `b` bằng giá trị số nhưng khác `scale`. Điều này quan trọng nếu một tầng hệ thống dùng `equals()`, `hashCode()` hoặc tập hợp băm làm khóa.
- `total` là **13** về toán học. Gọi `stripTrailingZeros()` cho biểu diễn `13`; gọi `setScale(2)` cho `13.00` mà vẫn giữ giá trị 13.
- `scientific.toString()` hiển thị `1E+3` còn `toPlainString()` hiển thị `1000`. Đối tượng gốc vẫn có `scale = -3`.
- `DecimalFormat` chỉ tạo chuỗi `1,234.50` để hiển thị theo quy ước `Locale.US` trong ví dụ. `amount` sau định dạng vẫn là đối tượng biểu diễn `1234.5` với `scale = 1`.

`BigDecimal` là immutable: các phương thức chuyển đổi/rounding trả về đối tượng mới; các phương thức chuỗi/format không chỉnh sửa đối tượng đã tính.

## 6. toString, toPlainString và chuỗi có số thập phân cố định

Ba yêu cầu này không giống nhau:

**A. Cần chuỗi canonical của BigDecimal.** `toString()` trả chuỗi có quy tắc xác định; có thể chọn ký pháp khoa học, và có thể chuyển ngược bằng constructor `BigDecimal(String)` để thu lại cùng cặp biểu diễn `unscaledValue`/`scale` trong điều kiện hợp lệ. Ví dụ `new BigDecimal("1E+3").toString()` là `"1E+3"`.

**B. Cần chuỗi không dùng số mũ.** `toPlainString()` trả dạng thập phân phẳng, chẳng hạn `"1000"` thay cho `"1E+3"`. Nó **không tự đặt số chữ số thập phân cố định**, cũng không bảo toàn `scale` âm nếu sau đó parse lại chuỗi `"1000"`. Trong ví dụ này, parse `"1000"` tạo `scale = 0`, khác đối tượng ban đầu có `scale = -3`.

**C. Cần đúng hai chữ số sau dấu thập phân.** Nếu chính sách là tạo một `BigDecimal` có `scale = 2`, dùng `setScale(2)` hoặc overload có `RoundingMode`, rồi `toPlainString()` để nhận chuỗi `"1000.00"`. Nếu chỉ cần giao diện, dùng bộ định dạng trình bày phù hợp, không làm thay đổi dữ liệu tính toán.

Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("1000");
System.out.println(amount.toPlainString());           // 1000
System.out.println(amount.setScale(2).toPlainString()); // 1000.00
~~~

Chú ý `toPlainString()` trên số có số mũ cực lớn có thể tạo chuỗi rất dài, tốn bộ nhớ. Đừng dùng nó vô điều kiện trên dữ liệu số mũ do người dùng nhập mà không giới hạn.

Nếu giao diện theo locale Việt Nam, dấu nhóm nghìn và dấu thập phân có thể khác `Locale.US`; đừng tự thay dấu `.` thành `,` trong chuỗi canonical rồi dùng chuỗi đó làm đầu vào cho `new BigDecimal(...)`. Phân tích dữ liệu và định dạng cho người dùng nên có **các quy tắc riêng**.

## 7. stripTrailingZeros: chuẩn hóa giá trị, nhưng thay đổi scale

`stripTrailingZeros()` trả `BigDecimal` bằng về giá trị số và bỏ các chữ số 0 ở cuối phần không chia tỷ lệ:

~~~java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal y = x.stripTrailingZeros();

System.out.println(x);         // 1000.00
System.out.println(x.scale()); // 2
System.out.println(y);         // 1E+3
System.out.println(y.scale()); // -3
~~~

Trong ví dụ này, `stripTrailingZeros()` không thay số 1000, nhưng biểu diễn mới có **scale âm**. Vì vậy:
- Nếu mục tiêu là gộp các `BigDecimal` bằng giá trị số làm khóa, chuẩn hóa có thể hữu ích nhưng cần áp dụng cùng cách ở mọi nơi.
- Nếu `scale` thể hiện độ phân giải, số chữ số đo lường hoặc cam kết hợp đồng, không bỏ tự động.
- Nếu mục tiêu hiển thị `1000.00`, `stripTrailingZeros()` không phải công cụ phù hợp.

`stripTrailingZeros()` trên mọi giá trị bằng 0 chuẩn hóa về `BigDecimal.ZERO`, có `scale = 0`. Vì thế `new BigDecimal("0.000").stripTrailingZeros()` không giữ ba chữ số thập phân.

## 8. Scale tính toán có thể ảnh hưởng đến kết quả phép tính tiếp theo

Một quy tắc nguy hiểm là "hai số `compareTo() == 0` nên thay thế lẫn nhau trong mọi phép tính đều như nhau". Giá trị số trước phép tính giống nhau, nhưng **overload có rounding và scale mặc định có thể cho kết quả số học khác nhau**.

Ví dụ:

~~~java
BigDecimal divisor = new BigDecimal("3");

System.out.println(
        new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP)
); // 0.7

System.out.println(
        new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP)
); // 0.67
~~~

Overload `divide(BigDecimal divisor, RoundingMode roundingMode)` trả kết quả ở **scale của số bị chia**. Với `2.0`, kết quả làm tròn có một chữ số sau dấu thập phân; với `2.00`, kết quả có hai chữ số. Do đó hai đối tượng ban đầu bằng về giá trị số nhưng cho kết quả đã làm tròn khác nhau qua overload này.

Để tránh phụ thuộc ngầm, viết rõ quy tắc của nghiệp vụ:

~~~java
BigDecimal ratio = new BigDecimal("2.0")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
System.out.println(ratio); // 0.6667
~~~

`MathContext` kiểm soát số chữ số **có nghĩa** và rounding của phép tính; `scale` kiểm soát vị trí dấu thập phân. Không dùng `new MathContext(2)` với ý nghĩa "hai chữ số sau dấu phẩy". Tham số `precision = 2` có nghĩa hai chữ số có nghĩa, nên kết quả sẽ phụ thuộc độ lớn của số.

## 9. Định dạng chỉ ở lớp hiển thị: DecimalFormat và locale

Để hiển thị số cho con người, Java có `DecimalFormat` và `NumberFormat`. Đây là bước **render**: nhận một giá trị và tạo chuỗi theo pattern/locale. Ví dụ với `Locale.US`:

~~~java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

BigDecimal value = new BigDecimal("1234.5");
String label = formatter.format(value);

System.out.println(label); // 1,234.50
System.out.println(value); // 1234.5
~~~

Đoạn trên cần `import java.math.*; import java.text.*; import java.util.*;` hoặc các import cụ thể như ở chương trình mục 5.

**Lựa chọn phù hợp:**
- Cần tính toán thêm: giữ `BigDecimal` gốc với độ chính xác phù hợp.
- Cần nhập/xuất máy với format chuẩn: định nghĩa format và chính sách parse cụ thể; chuỗi `toString()` thường phù hợp cho giá trị số canonical.
- Cần hiển thị cho người dùng: dùng formatter theo locale và đơn vị mong muốn; chuỗi format có thể chứa dấu phân nhóm và không thể đưa trực tiếp vào constructor `BigDecimal(String)`.
- Cần lưu **giá trị đã chốt sau làm tròn**: áp dụng rounding vào `BigDecimal` trước thời điểm chốt theo nghiệp vụ, thay vì phụ thuộc số đã hiển thị.

`DecimalFormat` là đối tượng **không an toàn để chia sẻ và dùng đồng thời giữa nhiều luồng** nếu không đồng bộ phù hợp. Có thể tạo mỗi lần dùng hoặc cung cấp một instance riêng theo ngữ cảnh ứng dụng.

Một giao diện có thể hiển thị `12.35` từ dữ liệu `12.3456` mà không đổi dữ liệu gốc. Nếu người dùng xác nhận giao dịch ở `12.35`, ứng dụng phải quy định rõ **giá trị chốt** nào được lưu và tính toán tiếp; không suy ra ngầm rằng giá trị gốc đã bị làm tròn bởi formatter.

## 10. Chuyển đổi dữ liệu giữa các tầng ứng dụng

Hãy hình dung luồng xử lý:

~~~text
Chuỗi đầu vào / dữ liệu bên ngoài
        |
        v
Parse thành BigDecimal với quy ước rõ
        |
        v
Tính toán BigDecimal + rounding theo nghiệp vụ
        |
        +----> Lưu giá trị chốt theo hợp đồng schema
        |
        +----> Format theo locale và yêu cầu giao diện
                  |
                  v
              Chuỗi hiển thị
~~~

Tại mỗi ranh giới, cần phân biệt những hợp đồng sau.

**Đầu vào:** Với chuỗi decimal canonical `"12.345"`, `new BigDecimal("12.345")` giữ đúng giá trị thập phân. Tránh `new BigDecimal(0.1)` khi ý muốn là chính xác 0.1 vì số `double` thường không biểu diễn chính xác số thập phân đó; `BigDecimal.valueOf(0.1)` hoặc constructor từ chuỗi có hành vi phù hợp hơn cho trường hợp này.

**Tính toán:** Dùng `add`, `subtract`, `multiply`, `divide` và `MathContext`/`RoundingMode` nếu cần. Không làm tròn sau mỗi thao tác một cách máy móc; vị trí làm tròn phải theo chính sách, vì làm tròn ở các bước khác nhau có thể tạo tổng khác nhau.

**Lưu trữ:** Khi ghi vào cột cơ sở dữ liệu `DECIMAL(p,s)`/`NUMERIC(p,s)`, `p` và `s` là hợp đồng của schema/database, không mặc định trùng với `precision()` và `scale()` của đối tượng đang có. Database/driver có thể ép scale, làm tròn hoặc từ chối dữ liệu tùy hệ quản trị và schema. Hãy xác minh hành vi thực tế, dùng truy vấn có tham số và kiểm tra các trường hợp số chữ số vượt giới hạn. Không coi `toPlainString()` là một cơ chế kiểm soát schema.

**Giao tiếp JSON:** Nhiều thư viện serialize `BigDecimal` dưới dạng số JSON; một số có tùy chọn biểu diễn dạng khoa học hoặc dạng plain. Nếu gửi như **JSON number**, consumer có thể parse thành floating point và làm mất chữ số chính xác, cũng như không giữ `scale`. Nếu hợp đồng cần cả độ chính xác và số chữ số biểu diễn, có thể định nghĩa chuỗi decimal và metadata `scale`/đơn vị, đồng thời yêu cầu consumer tuân thủ. Không phụ thuộc cú pháp JSON number để truyền ý nghĩa "luôn hai chữ số".

**Hiển thị:** Chọn formatter phù hợp người dùng; ví dụ `#,##0.00` yêu cầu hai chữ số sau thập phân trong locale US. Dấu phẩy nhóm nghìn là ký hiệu trình bày, không phải thành phần của giá trị số.

## 11. Ví dụ chọn thiết kế: tiền, đo lường và số liệu báo cáo

### Trường hợp A — tiền với đơn vị nhỏ nhất

Giả sử hệ thống quy định một đơn vị lớn bằng 100 đơn vị nhỏ và chỉ chấp nhận **số nguyên đơn vị nhỏ nhất**. Giá trị gửi vào là `"12.345"` đơn vị lớn:

~~~java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal minor = amount.movePointRight(2); // 1234.5
~~~

Nếu dùng `longValue()`, phần lẻ bị cắt và làm sai số tiền. Hãy yêu cầu chuyển đổi **chính xác** bằng `longValueExact()` hoặc `toBigIntegerExact()`; nếu số lẻ không hợp lệ thì từ chối, hoặc làm tròn theo quy tắc đã được phê duyệt trước khi chuyển.

Ví dụ quy tắc chốt giá trị rõ ràng:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
long cents = rounded.movePointRight(2).longValueExact();

System.out.println(rounded); // 12.35
System.out.println(cents);   // 1235
~~~

Đây là **một quyết định làm tròn thay đổi giá trị**, không phải chỉ đổi hiển thị. Hệ số 100 chỉ đúng cho đơn vị/hệ tiền được giả định trong ví dụ; không suy rằng mọi loại tiền đều có hai chữ số đơn vị nhỏ nhất.

### Trường hợp B — số đo có độ phân giải

Hai số `1.2` và `1.20` bằng nhau về số học, nhưng nếu nguồn đo quy ước số chữ số thập phân thể hiện độ phân giải, việc gọi `stripTrailingZeros()` có thể làm mất thông tin biểu diễn. Cần xác định rõ **độ chính xác phép đo** có được mô hình hóa bằng `scale` hay bằng metadata riêng. `BigDecimal` giữ số chữ số thập phân nhưng không tự chứng minh số liệu đo thực tế có độ chính xác đến mức đó.

### Trường hợp C — báo cáo chỉ yêu cầu trình bày đồng nhất

Dữ liệu sau cộng là `13.000` nhưng báo cáo cần đúng hai chữ số. Nếu không chốt giá trị mới, có thể dùng formatter để tạo `"13.00"`. Nếu cần xuất một giá trị decimal có `scale = 2` vì hợp đồng trao đổi dữ liệu, dùng `setScale(2)` với xử lý lỗi hoặc rounding rõ ràng. Hai hướng đều cho chữ `13.00` nhưng **ý nghĩa đối với dữ liệu gốc khác nhau**.

## 12. Sai lầm thường gặp

1. **Nhầm `scale` với độ chính xác phép tính:** `scale = 2` chỉ xác định vị trí dấu thập phân trong biểu diễn, không khẳng định con số đã được đo hoặc tính chính xác đến hai chữ số đó.
2. **Tưởng `setScale` chỉ đổi nhãn:** nếu giảm `scale` mà phải loại chữ số khác 0, kết quả làm tròn đổi giá trị; overload không cho phép làm tròn sẽ ném ngoại lệ.
3. **Tưởng `toPlainString()` đảm bảo hai chữ số:** nó chỉ bỏ ký pháp mũ. `new BigDecimal("1E+3").toPlainString()` là `"1000"`, không phải `"1000.00"`.
4. **Dùng `stripTrailingZeros()` trước mọi phép tính:** có thể xóa thông tin `scale` cần thiết và làm kết quả rounding của một số overload trở nên khác trước.
5. **Dùng `scaleByPowerOfTen` để "định dạng":** phương thức này nhân/chia giá trị số theo bậc 10, không chỉ sửa cách in số.
6. **Tin rằng chuỗi hiển thị là dữ liệu canonical:** `"1,234.50"` còn phụ thuộc locale và dấu ngăn cách; tách parse và format.
7. **Nhầm `compareTo` với `equals`:** `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0`, nhưng `equals()` là `false`. Kết quả này có thể tác động đến khóa `HashMap` và cấu trúc có sắp xếp như `TreeMap`.
8. **Khởi tạo bằng `new BigDecimal(double)` rồi trách rounding/scale:** sai lệch có thể xuất phát từ giá trị binary floating point ban đầu; tạo bằng chuỗi decimal hoặc `BigDecimal.valueOf(double)` khi phù hợp.
9. **Làm tròn sớm và nhiều lần:** phép cộng các giá trị đã làm tròn từng dòng có thể khác làm tròn một lần ở tổng cuối. Quy định rõ thời điểm chốt rounding.
10. **Quên giới hạn đầu ra:** ký pháp khoa học có thể biểu diễn số có bậc mũ lớn ngắn gọn, trong khi `toPlainString()` có thể tạo rất nhiều ký tự. Kiểm soát giới hạn tài nguyên đối với dữ liệu không tin cậy.

## 13. Bài tập tự kiểm tra

**Bài 1.** Với mã:

~~~java
BigDecimal original = new BigDecimal("3.000");
BigDecimal a = original.setScale(1);
BigDecimal b = original.stripTrailingZeros();

System.out.println(a);                 // ?
System.out.println(a.scale());         // ?
System.out.println(b);                 // ?
System.out.println(b.scale());         // ?
System.out.println(original.equals(a));// ?
System.out.println(original.compareTo(b) == 0);// ?
~~~

**Đáp án:** `3.0`, `1`, `3`, `0`, `false`, `true`. Cả ba bằng về giá trị số nhưng khác `scale` và có thể khác `equals()`.

**Bài 2.** `new BigDecimal("3.005").setScale(2, RoundingMode.HALF_UP)` trả gì? **Đáp án:** `3.01`. Đây là thay đổi giá trị số; nếu không truyền rounding mode, overload `setScale(2)` ném `ArithmeticException`.

**Bài 3.** `new BigDecimal("1E+3").setScale(2).toPlainString()` trả gì? **Đáp án:** `"1000.00"`. Việc đặt `scale = 2` là một thao tác trên đối tượng mới; `toPlainString()` sau đó chuyển thành chuỗi.

**Bài 4.** Hệ thống cần tính trung bình của nhiều con số rồi hiển thị hai chữ số. Có nên `setScale(2, HALF_UP)` sau *từng phần tử* trước khi cộng? **Gợi ý:** chỉ nếu hợp đồng yêu cầu làm tròn từng phần tử. Thông thường hãy giữ giá trị tính toán phù hợp và làm tròn ở điểm xác định bởi nghiệp vụ; sau đó mới format giao diện. So sánh phương án qua các dữ liệu có chữ số thứ ba để kiểm tra chênh lệch.

**Bài 5.** Một backend gửi JSON number `1.00` cho client và yêu cầu client luôn biết người nhập đã gõ hai chữ số sau dấu thập phân. Điều đó có chắc chắn không? **Đáp án:** Không. Cấu trúc JSON number và cách parser bên nhận hoạt động không bảo đảm giữ ý nghĩa `scale`. Phải thỏa thuận hợp đồng trao đổi rõ, có thể dùng chuỗi decimal hoặc metadata riêng khi số chữ số biểu diễn là dữ liệu nghiệp vụ.

## 14. Quy tắc áp dụng và tài liệu tham khảo

Trước khi đổi một `BigDecimal`, hãy trả lời theo đúng thứ tự:

1. **Giá trị toán học có được phép thay đổi không?** Nếu không, tránh rounding không được yêu cầu; dùng chuyển đổi chính xác và kiểm tra ngoại lệ.
2. **`scale` có phải một phần hợp đồng dữ liệu không?** Nếu có, bảo toàn hoặc chuẩn hóa theo quy tắc được công bố; không tùy tiện bỏ số 0 cuối.
3. **Đầu ra phục vụ tính toán, lưu trữ hay hiển thị?** Dùng `BigDecimal` cho tính toán, định nghĩa rõ schema cho lưu trữ, dùng định dạng/locale cho trình bày.
4. **Khi nào và theo quy tắc nào sẽ làm tròn?** Mã hóa điều đó bằng `RoundingMode`/`MathContext` hoặc overload `divide` tương ứng.

Tài liệu chính thức:
- [BigDecimal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): biểu diễn `scale`, preferred scale, `setScale`, `toString`, `toPlainString`, `stripTrailingZeros` và các phép toán.
- [RoundingMode — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): ý nghĩa các chế độ làm tròn.
- [DecimalFormat — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): pattern định dạng số, locale và việc sử dụng đa luồng.
