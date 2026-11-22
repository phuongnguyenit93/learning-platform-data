# Unscaled value, scale và công thức xác định giá trị của BigDecimal trong Java

`java.math.BigDecimal` là kiểu số **thập phân bất biến với độ chính xác tùy ý**, rất hữu ích khi cần biểu diễn giá trị thập phân một cách có kiểm soát. Điểm quan trọng nhất khi học `BigDecimal` không phải chỉ là “nó có nhiều chữ số hơn `double`”, mà là **cách Java xác định giá trị của mỗi object từ một số nguyên và một scale**.

Một `BigDecimal` có hai thành phần cốt lõi:

- **Unscaled value**: một số nguyên có dấu, có thể biểu diễn chính xác bằng `BigInteger`.
- **Scale**: một số nguyên kiểu `int`; cho biết số mũ của 10 trong cách diễn giải unscaled value.

Công thức định nghĩa giá trị là:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Vì vậy `unscaledValue = 12345`, `scale = 2` sẽ cho `123.45`; nhưng cùng unscaled value với `scale = -2` sẽ cho `1,234,500`. **Scale không phải luôn luôn là số chữ số nằm sau dấu thập phân**, vì scale có thể dương, bằng 0 hoặc âm.

Bài học này thuộc mục **Mô hình BigDecimal** và giải thích cách đọc hai thành phần, mối quan hệ với `precision`, các thao tác thay đổi scale, sự khác nhau giữa equality theo giá trị và theo biểu diễn, cùng cách dùng an toàn trong tính toán thực tế với Java 17+.

## 1. Phân tích công thức bằng ví dụ

Với `new BigDecimal("123.45")`, Java có thể mô tả giá trị bằng:

~~~text
unscaledValue = 12345
scale         = 2
value         = 12345 × 10^(-2) = 123.45
~~~

Một số biểu diễn khác:

| Unscaled value | Scale | Tính toán | Giá trị số |
| ---: | ---: | --- | ---: |
| `12345` | `2` | `12345 × 10^-2` | `123.45` |
| `12345` | `0` | `12345 × 10^0` | `12345` |
| `123` | `-2` | `123 × 10^2` | `12300` |
| `-12345` | `3` | `-12345 × 10^-3` | `-12.345` |
| `12` | `2` | `12 × 10^-2` | `0.12` |
| `0` | `4` | `0 × 10^-4` | `0` |

Ở trường hợp unscaled value bằng 0, **mọi scale đều cho cùng giá trị toán học là zero**, nhưng object vẫn có thể giữ scale khác nhau, chẳng hạn `new BigDecimal("0.000")` có scale bằng 3.

Không nên gọi `scale` là “precision”, bởi nó không đếm tổng số chữ số có nghĩa và không diễn đạt độ tin cậy vật lý của dữ liệu. Scale chỉ là **số mũ thập phân trong mô hình giá trị**.

## 2. Đọc trực tiếp bằng `unscaledValue()` và `scale()`

~~~java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount);                // 123.4500
System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 7
~~~

`unscaledValue()` trả `BigInteger`, không phải `long`. Do đó một số decimal rất lớn không nhất thiết bị giới hạn trong 64 bit. `scale()` trả `int`, thể hiện số mũ thập phân dùng trong công thức. `precision()` đếm số chữ số thập phân có nghĩa trong **unscaled value**; với `1234500` là 7 chữ số.

Kết quả `123.4500` và `123.45` **bằng nhau về giá trị toán học**, nhưng có cấu trúc khác nhau:

| Văn bản đầu vào | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"123.4500"` | `1234500` | `4` | `7` |
| `"123.45"` | `12345` | `2` | `5` |
| `"1.23E+4"` | `123` | `-2` | `3` |
| `"0.000"` | `0` | `3` | `1` |

**Đếm precision của zero:** theo hợp đồng `BigDecimal`, `precision()` của một giá trị zero là 1, không phải 0, bất kể scale của biểu diễn zero được tạo ra. Việc giữ thêm chữ số 0 trong một số decimal ảnh hưởng scale và có thể ảnh hưởng precision trong nhiều trường hợp, nhưng không biến dữ liệu đầu vào thành phép đo “đáng tin” hơn.

## 3. Scale dương, bằng 0 và âm

### Scale dương

Với `new BigDecimal("12.345")`, unscaled value là `12345` và scale là `3`: giá trị `12345 × 10^-3 = 12.345`. Đây là trường hợp quen thuộc khiến người mới học nghĩ scale luôn đồng nghĩa “ba chữ số sau dấu thập phân”.

### Scale bằng 0

`new BigDecimal("12345")` có unscaled value `12345` và scale `0`. Giá trị chính là số nguyên 12345, nhưng vẫn là một đối tượng `BigDecimal`, khác kiểu so với `BigInteger` hay `Long`.

### Scale âm

`new BigDecimal("1.23E+4")` có:

~~~java
BigDecimal scientific = new BigDecimal("1.23E+4");
System.out.println(scientific);                 // 1.23E+4
System.out.println(scientific.unscaledValue()); // 123
System.out.println(scientific.scale());         // -2
System.out.println(scientific.toPlainString()); // 12300
~~~

Vì `123 × 10^2 = 12300`, scale âm hoàn toàn hợp lệ. Dạng `toString()` có thể dùng ký pháp khoa học, còn `toPlainString()` thể hiện giá trị dưới dạng chữ số thập phân thông thường, không dùng ký pháp số mũ. **Đừng suy ra `scale < 0` là lỗi hoặc số âm.** Dấu của số nằm trong unscaled value; dấu của scale nói về vị trí dấu thập phân.

Có thể xây trực tiếp từ cặp unscaled/scale:

~~~java
new BigDecimal(BigInteger.valueOf(12345), 2); // 123.45
new BigDecimal(BigInteger.valueOf(123), -2);  // 1.23E+4
BigDecimal.valueOf(12L, 2);                    // 0.12
~~~

Overload `BigDecimal.valueOf(long unscaledVal, int scale)` khác `BigDecimal.valueOf(double)`. Đừng nhầm các overload chỉ vì cùng tên phương thức.

## 4. Cùng giá trị nhưng khác biểu diễn: `equals` và `compareTo`

Hai số:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");
~~~

đều bằng toán học với 1, nhưng `a` có unscaled = 10, scale = 1; `b` có unscaled = 100, scale = 2. Do đó:

~~~java
System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b));     // 0
~~~

- **`equals`** xem hai `BigDecimal` bằng nhau khi cả *giá trị số* và *scale* phù hợp bằng nhau; ví dụ trên trả false.
- **`compareTo`** so sánh giá trị số, nên trả 0 với hai biểu diễn `1.0` và `1.00`.

Hệ quả về collections:

~~~java
Set<BigDecimal> hashed = new HashSet<>(Arrays.asList(a, b));
Set<BigDecimal> ordered = new TreeSet<>(Arrays.asList(a, b));
// hashed.size() = 2, ordered.size() = 1
~~~

`HashSet` dựa trên `equals`/`hashCode`, còn `TreeSet` mặc định dùng `compareTo` làm thứ tự, nên **hai collection có thể gộp phần tử theo chính sách khác nhau**. Nếu dùng giá tiền hoặc số decimal làm khóa, hãy xác định scale có ý nghĩa nghiệp vụ không, và chuẩn hóa biểu diễn trước khi lưu khóa khi cần.

**Đừng thay đổi `equals`/`hashCode` tùy tiện** hoặc dùng so sánh “gần bằng” theo epsilon làm comparator của `TreeSet`; quan hệ so sánh phải giữ được hợp đồng nhất quán và bắc cầu.

## 5. `stripTrailingZeros()` thay đổi cấu trúc nhưng giữ giá trị số

`stripTrailingZeros()` loại bỏ những số 0 cuối trong **biểu diễn decimal** mà không thay đổi giá trị toán học:

~~~java
BigDecimal original = new BigDecimal("123.4500");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(stripped);                 // 123.45
System.out.println(stripped.unscaledValue()); // 12345
System.out.println(stripped.scale());         // 2
~~~

Object `original` **không thay đổi**, vì `BigDecimal` bất biến. Với một số nguyên có nhiều số 0 cuối, scale kết quả thậm chí có thể trở thành **âm**; chẳng hạn `new BigDecimal("1200.0").stripTrailingZeros()` có thể được trình bày bằng số mũ để thể hiện scale âm mà vẫn giữ giá trị 1200.

Với zero, `stripTrailingZeros` cho dạng zero chuẩn có scale 0:

~~~java
BigDecimal z = new BigDecimal("0.000");
System.out.println(z.unscaledValue());                 // 0
System.out.println(z.scale());                         // 3
System.out.println(z.precision());                     // 1
System.out.println(z.stripTrailingZeros().scale());    // 0
~~~

**Không dùng `stripTrailingZeros` nếu nghiệp vụ cần giữ số chữ số đã nhập như một thông tin riêng.** Trong báo giá hoặc phép đo, `1.20` đôi khi cần được hiển thị đúng hai chữ số phần lẻ; normalize thành `1.2` sẽ loại mất scale ban đầu dù không làm mất giá trị toán học.

## 6. `setScale`: thay đổi scale và đôi khi cần làm tròn giá trị

`setScale(newScale)` tạo một `BigDecimal` mới với scale được yêu cầu.

**Tăng scale** (thêm các vị trí thập phân) thường có thể thực hiện chính xác bằng cách nhân unscaled value với lũy thừa 10:

~~~java
BigDecimal initial = new BigDecimal("12.3");
BigDecimal padded = initial.setScale(3);
// padded = 12.300, unscaled = 12300, scale = 3
~~~

**Giảm scale** thường đòi bỏ chữ số có nghĩa và có thể cần làm tròn:

~~~java
BigDecimal amount = new BigDecimal("12.35");
BigDecimal rounded = amount.setScale(1, RoundingMode.HALF_UP);
// rounded = 12.4
~~~

Khi dùng overload `setScale(int)` không có rounding mode, Java yêu cầu phép thay đổi scale **diễn ra chính xác**. Nếu cần bỏ chữ số khác 0, nó ném `ArithmeticException`. Để phát hiện thao tác không được phép làm tròn, có thể chọn `RoundingMode.UNNECESSARY` một cách tường minh.

Sự khác nhau quan trọng:

- `setScale` đổi **scale và có thể đổi giá trị toán học** khi phải làm tròn.
- `stripTrailingZeros` đổi **cách biểu diễn, không đổi giá trị toán học**.
- `DecimalFormat.format` tạo **chuỗi hiển thị**, không đổi object nguồn.
- `BigDecimal` immutable: cần lưu kết quả trả về, không chờ object gốc bị mutate.

**Rounding mode** phải theo yêu cầu nghiệp vụ. `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING` và `FLOOR` xử lý các ranh giới và số âm khác nhau; không có mode mặc định “đúng với mọi hóa đơn”.

## 7. `scaleByPowerOfTen` và `movePointLeft/Right`

Từ công thức `unscaled × 10^-scale`, việc nhân hoặc chia cho một lũy thừa 10 có thể thực hiện bằng các API dịch dấu thập phân:

~~~java
BigDecimal input = new BigDecimal("12.30");
BigDecimal scaled = input.scaleByPowerOfTen(2);
BigDecimal moved = input.movePointRight(3);

// scaled = 1230, moved = 12300
~~~

Với `scaleByPowerOfTen(n)`, về mặt mô hình `BigDecimal`, scale mới về nguyên tắc là `scale - n`. `movePointRight(n)` và `movePointLeft(n)` mang ngữ nghĩa dịch điểm thập phân, và kết quả của chúng có scale **không âm** theo hợp đồng. Vì vậy ở những trường hợp scale âm, hai nhóm API có thể cho **biểu diễn khác nhau dù giá trị toán học bằng nhau**.

Đừng lấy kiểu biểu diễn chuỗi đã format làm tiêu chí để phân biệt phép toán có đổi giá trị hay không. Hãy kiểm tra:

~~~text
Giá trị mới = Giá trị cũ × 10^n      (dịch sang phải / scaleByPowerOfTen)
Giá trị mới = Giá trị cũ × 10^(-n)   (dịch sang trái)
~~~

Những thao tác này còn chịu giới hạn scale kiểu `int` và tài nguyên. Đối với scale quá lớn/quá nhỏ, phép biến đổi có thể ném ngoại lệ hoặc không thể biểu diễn theo giới hạn thực thi; không sử dụng giá trị `n` không tin cậy mà không kiểm tra.

## 8. Phép toán có thể tạo scale mới theo quy tắc

`BigDecimal` không chỉ giữ unscaled và scale ban đầu: **kết quả phép toán cũng có cặp unscaled/scale riêng**.

### Cộng và trừ

Đối với phép cộng/trừ chính xác, scale ưu tiên (*preferred scale*) là **lớn hơn trong hai scale của toán hạng**:

~~~java
BigDecimal x = new BigDecimal("1.20"); // scale 2
BigDecimal y = new BigDecimal("3.4");  // scale 1

BigDecimal sum = x.add(y); // 4.60, scale 2
~~~

Vì hai số cần cộng ở cùng đơn vị decimal, hệ thống có thể thêm số 0 vào biểu diễn nội bộ trước khi cộng unscaled integer.

### Nhân

Scale ưu tiên của phép nhân chính xác là **tổng hai scale**:

~~~java
BigDecimal product = new BigDecimal("1.20")
        .multiply(new BigDecimal("3.4"));
// product = 4.080, scale 3 = 2 + 1
~~~

Hai số `4.080` và `4.08` bằng nhau theo `compareTo` nhưng có scale khác nhau. Khi nhân tiền với tỷ lệ hay số lượng, hãy xác định scale đầu ra và thời điểm làm tròn theo quy tắc nghiệp vụ.

### Chia

Scale ưu tiên của phép chia là **scale của số bị chia trừ scale của số chia**, nhưng kết quả chính xác có thể cần thêm chữ số phần lẻ. Ví dụ:

~~~java
BigDecimal quotient = new BigDecimal("1.00")
        .divide(new BigDecimal("4"));
// quotient = 0.25, scale 2
~~~

Một phép chia như `BigDecimal.ONE.divide(new BigDecimal("3"))` có khai triển decimal vô hạn nên overload chia chính xác không rounding có thể ném `ArithmeticException`. Khi nghiệp vụ cho phép xấp xỉ, hãy truyền `scale` và `RoundingMode` hoặc `MathContext`, đồng thời ghi rõ tiêu chí độ chính xác.

**Lưu ý:** Khi dùng overload có `MathContext` và giới hạn precision, các phép toán có thể làm tròn, kéo theo scale thực tế khác preferred scale. Đừng dự đoán scale kết quả mà không xét overload và rounding context.

## 9. `MathContext.precision` khác `BigDecimal.scale`

`MathContext` giới hạn **tổng số chữ số có nghĩa của kết quả**, không phải số chữ số sau dấu thập phân.

~~~java
BigDecimal value = new BigDecimal("12345.67");
BigDecimal rounded = value.round(
        new MathContext(3, RoundingMode.HALF_UP));
// rounded = 1.23E+4: ba chữ số có nghĩa, scale âm
~~~

Ngược lại, `setScale(2, RoundingMode.HALF_UP)` yêu cầu hai vị trí thập phân sau dấu phân cách ở kết quả. Hai thao tác có thể cho các kết quả rất khác nhau với cùng đầu vào.

| Phương thức | Câu hỏi cần trả lời |
| --- | --- |
| `scale()` | Số mũ thập phân của object này là bao nhiêu? |
| `precision()` | Unscaled value có bao nhiêu chữ số decimal có nghĩa? |
| `setScale(2, mode)` | Muốn kết quả giữ scale chính xác bằng 2, cho phép làm tròn theo mode? |
| `round(new MathContext(3, mode))` | Muốn giữ ba chữ số có nghĩa của kết quả? |
| `format(...)` | Muốn chuỗi hiển thị theo quy tắc trình bày nào? |

`MathContext.UNLIMITED` có precision bằng 0 theo hợp đồng `MathContext` (ý nghĩa “không giới hạn”), khác với `BigDecimal.precision() == 0`; một `BigDecimal` có giá trị zero vẫn có precision bằng 1. Tránh nhầm hai kiểu “precision”.

## 10. Constructor, String và double: nguồn vào quyết định unscaled value

Nếu yêu cầu **decimal chính xác như người dùng nhập**, tạo object trực tiếp từ chuỗi decimal:

~~~java
BigDecimal exact = new BigDecimal("0.1");
// unscaled 1, scale 1
~~~

Nếu đi qua `double`, giá trị đã được làm tròn thành binary64 trước khi constructor `BigDecimal(double)` nhận được nó:

~~~java
BigDecimal fromDouble = new BigDecimal(0.1);
// 0.1000000000000000055511151231257827021181583404541015625
~~~

`new BigDecimal(0.1)` biểu diễn **chính xác giá trị binary64 đang lưu**, không phải chính xác giá trị thập phân 1/10 theo ý định literal. `BigDecimal.valueOf(0.1)` dùng chuỗi canonical do `Double.toString(0.1)` tạo ra và trong ví dụ trả decimal `0.1`, nhưng factory đó không biết cách khôi phục dữ liệu decimal ban đầu nếu đã qua một chuỗi phép toán `double`.

Để giữ cả **giá trị và scale của đầu vào decimal**, nhận chuỗi gốc là cách rõ ràng:

~~~java
new BigDecimal("1.20"); // unscaled 120, scale 2
new BigDecimal("1.2");  // unscaled 12, scale 1
~~~

Nếu bạn chuyển hai chuỗi thành `double` rồi quay lại decimal, thông tin về hai cách ghi và scale ban đầu có thể mất. Khi parse đầu vào từ CSV/JSON/form, hãy kiểm tra ngữ pháp số thập phân, locale, miền giá trị và giới hạn precision/scale một cách tường minh.

## 11. Chương trình Java 17+ hoàn chỉnh và stdout kiểm chứng

Lưu thành tệp `BigDecimalModelDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.HashSet;
import java.util.TreeSet;

public class BigDecimalModelDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");
        System.out.println("a = " + a);
        System.out.println("a.unscaledValue = " + a.unscaledValue());
        System.out.println("a.scale = " + a.scale());
        System.out.println("a.precision = " + a.precision());

        BigDecimal stripped = a.stripTrailingZeros();
        System.out.println("stripped = " + stripped);
        System.out.println("stripped unscaled = "
                + stripped.unscaledValue());
        System.out.println("stripped scale = " + stripped.scale());

        BigDecimal e = new BigDecimal("1.23E+4");
        System.out.println("e = " + e);
        System.out.println("e unscaled = " + e.unscaledValue());
        System.out.println("e scale = " + e.scale());
        System.out.println("e plain = " + e.toPlainString());
        System.out.println("construct (123,-2) = "
                + new BigDecimal(BigInteger.valueOf(123), -2));
        System.out.println("construct (12345,2) = "
                + new BigDecimal(BigInteger.valueOf(12345), 2));
        System.out.println("valueOf(12,2) = "
                + BigDecimal.valueOf(12L, 2));

        BigDecimal z = new BigDecimal("0.000");
        System.out.println("zero unscaled,scale,precision = "
                + z.unscaledValue() + "," + z.scale()
                + "," + z.precision());
        System.out.println("zero stripped scale = "
                + z.stripTrailingZeros().scale());

        System.out.println("upscale = "
                + new BigDecimal("12.3").setScale(3));
        System.out.println("downscale HALF_UP = "
                + new BigDecimal("12.35")
                .setScale(1, RoundingMode.HALF_UP));
        System.out.println("sum = "
                + new BigDecimal("1.20")
                .add(new BigDecimal("3.4")));
        System.out.println("product = "
                + new BigDecimal("1.20")
                .multiply(new BigDecimal("3.4")));
        System.out.println("division = "
                + new BigDecimal("1.00")
                .divide(new BigDecimal("4")));

        System.out.println("scaleByPowerOfTen = "
                + new BigDecimal("12.30").scaleByPowerOfTen(2));
        System.out.println("movePointRight = "
                + new BigDecimal("12.30").movePointRight(3));
        System.out.println("negative zero = "
                + new BigDecimal("-0.00"));
        System.out.println("negative zero scale = "
                + new BigDecimal("-0.00").scale());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("equals different scales = " + x.equals(y));
        System.out.println("compareTo different scales = " + x.compareTo(y));
        System.out.println("HashSet size = "
                + new HashSet<>(Arrays.asList(x, y)).size());
        System.out.println("TreeSet size = "
                + new TreeSet<>(Arrays.asList(x, y)).size());
        System.out.println("round MathContext(3) = "
                + new BigDecimal("12345.67")
                .round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("0.1 from string = "
                + new BigDecimal("0.1"));
        System.out.println("0.1 from double = "
                + new BigDecimal(0.1));

        try {
            new BigDecimal("1.23")
                    .setScale(1, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY catches rounding");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalModelDemo.java
java BigDecimalModelDemo
~~~

Stdout:

~~~text
a = 123.4500
a.unscaledValue = 1234500
a.scale = 4
a.precision = 7
stripped = 123.45
stripped unscaled = 12345
stripped scale = 2
e = 1.23E+4
e unscaled = 123
e scale = -2
e plain = 12300
construct (123,-2) = 1.23E+4
construct (12345,2) = 123.45
valueOf(12,2) = 0.12
zero unscaled,scale,precision = 0,3,1
zero stripped scale = 0
upscale = 12.300
downscale HALF_UP = 12.4
sum = 4.60
product = 4.080
division = 0.25
scaleByPowerOfTen = 1230
movePointRight = 12300
negative zero = 0.00
negative zero scale = 2
equals different scales = false
compareTo different scales = 0
HashSet size = 2
TreeSet size = 1
round MathContext(3) = 1.23E+4
0.1 from string = 0.1
0.1 from double = 0.1000000000000000055511151231257827021181583404541015625
UNNECESSARY catches rounding
~~~

Kết quả này minh họa cặp unscaled/scale **trong cả trường hợp scale âm và zero**, phép thay đổi scale có/không làm tròn, scale phép toán, việc chuẩn hóa zero, và tác động của scale lên collections.

## 12. Dạng chuỗi `toString` và `toPlainString`

`BigDecimal.toString()` tạo dạng chuỗi canonical có thể chứa ký pháp khoa học khi cần. `toPlainString()` tạo biểu diễn **không sử dụng số mũ**, phù hợp nếu bên nhận yêu cầu hiển thị decimal thông thường.

~~~java
BigDecimal big = new BigDecimal("1.23E+4");
big.toString();      // "1.23E+4"
big.toPlainString(); // "12300"
~~~

**Không nhầm định dạng xuất với cấu trúc số:** hai chuỗi trên mô tả cùng giá trị nhưng nếu parse ngược `"12300"`, object mới có thể có scale khác object ban đầu (`"1.23E+4"` có scale -2; `"12300"` có scale 0). Nếu cần giữ cả **giá trị và scale** khi serialize, phải xác định format có khả năng round-trip cả hai, chẳng hạn dùng `toString` theo hợp đồng `BigDecimal` hoặc truyền riêng unscaled/scale.

Một số nghiệp vụ không muốn dùng ký pháp khoa học khi hiển thị tiền, nhưng cũng không nên tùy tiện dùng `toPlainString()` cho dữ liệu có scale âm cực lớn vì chuỗi có thể phình to và gây tốn tài nguyên.

## 13. Các trường hợp đặc biệt và giới hạn thực tế

### Zero và dấu âm

`new BigDecimal("-0.00")` có giá trị số zero, unscaled value 0 và scale 2. `BigDecimal` **không giữ một giá trị zero âm riêng** giống IEEE 754 `double -0.0`. Chuỗi `toString()` thường biểu diễn `0.00`, dù văn bản gốc có dấu âm.

### Scale và precision có giới hạn khác nhau

Unscaled value được lưu dưới dạng số nguyên độ chính xác tùy ý nhưng **phụ thuộc tài nguyên thực tế**; scale vẫn là `int`, nên không thể sử dụng bất kỳ số mũ thập phân lớn vô hạn. Các thao tác có thể gặp `ArithmeticException` khi không thể biểu diễn scale mong muốn hoặc làm tròn bị cấm, và có thể tốn nhiều bộ nhớ khi mở rộng giá trị hoặc tạo chuỗi dài.

### Không có NaN hoặc vô cực

`BigDecimal` không biểu diễn NaN hoặc `Infinity` như `double`. Khi chuyển đầu vào bất thường sang decimal, phải có chính sách validation riêng. Nếu đang nhận `double`, sử dụng `Double.isFinite(value)` trước nếu ứng dụng chỉ chấp nhận số hữu hạn.

### Trường dữ liệu tài chính

Nếu lưu amount theo hai chữ số thập phân, bạn có thể yêu cầu `setScale(2, mode)` tại ranh giới lưu; nhưng đừng **tự động** chuẩn hóa bằng `stripTrailingZeros` nếu scale còn mang nghĩa của đơn vị tiền tệ, quy định trình bày hoặc auditing. Việc “đúng giá trị số” và “đúng đại diện số decimal” là hai hợp đồng khác nhau.

## 14. Những sai lầm thường gặp

1. **Coi scale luôn là số chữ số sau dấu phẩy.** Scale có thể âm, ví dụ `1.23E+4` có scale -2.
2. **Nhầm scale với precision.** `123.4500` có scale 4 và precision 7, không phải đều là 4.
3. **Nghĩ `stripTrailingZeros` đổi giá trị số.** Nó giữ giá trị, nhưng thay unscaled/scale và có thể khiến scale âm.
4. **Dùng `equals` để kiểm tra giá trị decimal bất kể scale.** `1.0` và `1.00` không `equals` nhưng `compareTo` bằng 0.
5. **Dùng `BigDecimal` làm khóa collection mà không quyết định chính sách scale.** `HashSet` và `TreeSet` có thể gộp dữ liệu khác nhau.
6. **Gọi `setScale` rồi nghĩ object ban đầu đã đổi.** `BigDecimal` bất biến; phải nhận object trả về.
7. **Giảm scale mà không cân nhắc rounding.** Có thể cần rounding mode hoặc ném ngoại lệ nếu chuyển không chính xác.
8. **Cho rằng `MathContext(3)` là ba chữ số sau dấu thập phân.** Nó đặt ba chữ số có nghĩa tổng cộng.
9. **Cho rằng scale kết quả phép toán luôn bằng scale một toán hạng.** Cộng/nhân/chia có quy tắc scale riêng, còn rounding context có thể thay đổi scale.
10. **Đi qua `double` khi cần giữ đúng decimal từ chuỗi đầu vào.** Binary64 làm tròn nhiều phân số thập phân trước khi tạo `BigDecimal`.
11. **Đánh đồng chuỗi in với cấu trúc object.** `toPlainString` có thể mất thông tin scale âm nếu parse lại.
12. **Bỏ qua trường hợp zero có nhiều scale hoặc dấu âm đầu vào.** Mọi zero bằng nhau theo giá trị nhưng object equality còn xét scale; BigDecimal không lưu signed zero riêng.
13. **Không xét tràn scale và giới hạn tài nguyên.** “Độ chính xác tùy ý” không có nghĩa xử lý chuỗi/mũ lớn vô hạn trong bộ nhớ thực.
14. **Coi scale là độ tin cậy của một phép đo.** Scale chỉ là một đặc tính biểu diễn decimal; độ bất định vật lý phải được mô tả bằng dữ liệu nghiệp vụ khác.

## 15. Câu hỏi tự luyện

**Câu 1.** Unscaled value 12345, scale 3 biểu diễn giá trị gì?

**Đáp án:** `12345 × 10^-3 = 12.345`.

**Câu 2.** `new BigDecimal("1.23E+4")` có unscaled value và scale là gì? Tại sao scale âm?

**Đáp án:** Unscaled = 123, scale = -2 vì `123 × 10^2 = 12300`. Scale âm là ký hiệu tăng độ lớn bằng lũy thừa của 10, không phải dấu âm của số.

**Câu 3.** Tại sao `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false nhưng `compareTo` trả 0?

**Đáp án:** `equals` xét cả scale, còn `compareTo` chỉ so sánh giá trị số decimal.

**Câu 4.** `new BigDecimal("123.4500").stripTrailingZeros()` thay đổi gì?

**Đáp án:** Giữ giá trị 123.45, nhưng unscaled từ 1234500 thành 12345 và scale từ 4 thành 2; object nguồn vẫn giữ nguyên.

**Câu 5.** `new BigDecimal("12.3").setScale(3)` khác `new BigDecimal("12.35").setScale(1, HALF_UP)` ra sao?

**Đáp án:** Lần đầu thêm số 0, giữ nguyên giá trị thành 12.300; lần sau cần làm tròn thành 12.4 theo quy tắc HALF_UP.

**Câu 6.** Vì sao `new BigDecimal("1.20").multiply(new BigDecimal("3.4"))` trả `4.080` thay vì bắt buộc `4.08`?

**Đáp án:** Phép nhân chính xác có preferred scale bằng tổng scale của hai toán hạng: 2 + 1 = 3. Hai biểu diễn có cùng giá trị số nhưng scale khác nhau.

**Câu 7.** `BigDecimal.ZERO.precision()` bằng 0 vì zero không có chữ số có nghĩa đúng không?

**Đáp án:** Sai. Theo định nghĩa `BigDecimal`, precision của zero là 1. Đừng nhầm với `MathContext.UNLIMITED` có precision bằng 0 để biểu thị không giới hạn.

**Câu 8.** Khi nào dùng `toString()` thay vì `toPlainString()` để serialize?

**Đáp án:** Nếu muốn round-trip đồng thời giá trị **và scale**, dạng canonical của `toString` phù hợp hơn. `toPlainString` bỏ ký pháp khoa học; parse lại có thể làm thay đổi scale của dữ liệu ban đầu có scale âm.

## Tài liệu tham khảo

- [Oracle Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): công thức giá trị, unscaled value, scale, precision, preferred scale, equals/compareTo, setScale và stripTrailingZeros.
- [Oracle Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html): biểu diễn số nguyên không giới hạn độ rộng dùng làm unscaled value.
- [Oracle Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision, rounding mode và UNLIMITED.
- [Oracle Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): ý nghĩa từng quy tắc làm tròn.
