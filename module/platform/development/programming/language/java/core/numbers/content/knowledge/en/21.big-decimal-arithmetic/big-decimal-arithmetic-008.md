# BigDecimal: movePointLeft, movePointRight và scaleByPowerOfTen

Ba phương thức `movePointLeft(int n)`, `movePointRight(int n)` và `scaleByPowerOfTen(int n)` của `java.math.BigDecimal` đều giúp nhân hoặc chia một số thập phân với lũy thừa của 10 **một cách chính xác**, không đi qua phép tính dấu phẩy động `double`. Điểm khác nhau quan trọng nằm ở **hướng dịch chuyển, cách giữ `scale` và cách biểu diễn kết quả**. Hiểu những điểm này giúp xử lý tiền tệ, đổi đơn vị thập phân và số ở dạng khoa học mà không làm thay đổi giá trị ngoài ý muốn.

## 1. Nền tảng: giá trị số và scale

Một `BigDecimal` có hai thành phần cốt lõi:

- `unscaledValue()`: số nguyên không chứa dấu thập phân.
- `scale()`: số chữ số thập phân theo quy tắc `value = unscaledValue × 10^(-scale)`. `scale` có thể dương, bằng 0 hoặc âm.

| Cách tạo | `toString()` | `unscaledValue()` | `scale()` | Giá trị |
|---|---|---:|---:|---:|
| `new BigDecimal("123.45")` | `123.45` | `12345` | 2 | 123,45 |
| `new BigDecimal("123.4500")` | `123.4500` | `1234500` | 4 | 123,45 |
| `new BigDecimal("123")` | `123` | `123` | 0 | 123 |
| `new BigDecimal("1.23E+3")` | `1.23E+3` | `123` | -1 | 1230 |

Do đó, hai đối tượng `BigDecimal` có thể biểu diễn **cùng giá trị số** nhưng khác `scale`. Các phương thức trong bài không làm tròn số; tuy nhiên, chúng có thể tạo kết quả khác nhau về `scale`, số chữ số 0 và `toString()`.

## 2. Bảng so sánh ba phương thức

Với `x` là giá trị ban đầu, `s = x.scale()` và `n` là số nguyên:

| Phương thức | Giá trị toán học mới | `scale` kết quả | Ý nghĩa |
|---|---|---|---|
| `x.movePointLeft(n)` | `x × 10^(-n)` | `max(s + n, 0)` | Dịch dấu thập phân sang trái `n` vị trí khi `n > 0` |
| `x.movePointRight(n)` | `x × 10^n` | `max(s - n, 0)` | Dịch dấu thập phân sang phải `n` vị trí khi `n > 0` |
| `x.scaleByPowerOfTen(n)` | `x × 10^n` | `s - n` | Thay đổi số mũ thập phân và giữ `scale` âm nếu cần |

**Quy tắc dấu của `n`:**

- `n > 0`: `movePointLeft` chia cho `10^n`; `movePointRight` và `scaleByPowerOfTen` nhân với `10^n`.
- `n < 0`: hướng dịch chuyển đảo lại. Ví dụ `movePointLeft(-2)` tương đương về giá trị với `movePointRight(2)`; `scaleByPowerOfTen(-2)` là chia cho 100.
- `n = 0`: giá trị số không đổi. Tuy nhiên `movePointLeft(0)` và `movePointRight(0)` vẫn có thể chuẩn hóa `scale` âm thành 0; `scaleByPowerOfTen(0)` giữ nguyên `scale`.

Đặc biệt, **`movePointRight(n)` và `scaleByPowerOfTen(n)` bằng nhau về giá trị số, nhưng không nhất thiết bằng nhau theo `equals()`**.

## 3. Ví dụ Java 17+ chạy độc lập

Tạo tệp `BigDecimalShiftDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalShiftDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("12.3400");

        show("original", x);
        show("left(2)", x.movePointLeft(2));
        show("right(3)", x.movePointRight(3));
        show("power(3)", x.scaleByPowerOfTen(3));

        // Chứng minh BigDecimal bất biến.
        System.out.println("original after calls: " + x);

        BigDecimal y = new BigDecimal("1.23");
        BigDecimal right = y.movePointRight(3);
        BigDecimal power = y.scaleByPowerOfTen(3);

        show("1.23 right(3)", right);
        show("1.23 power(3)", power);
        System.out.println("compareTo = " + right.compareTo(power));
        System.out.println("equals = " + right.equals(power));
        System.out.println("plain right = " + right.toPlainString());
        System.out.println("plain power = " + power.toPlainString());
    }

    private static void show(String name, BigDecimal value) {
        System.out.println(name + ": " + value + " | scale=" + value.scale());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalShiftDemo.java
java BigDecimalShiftDemo
~~~

Kết quả chuẩn:

~~~text
original: 12.3400 | scale=4
left(2): 0.123400 | scale=6
right(3): 12340.0 | scale=1
power(3): 12340.0 | scale=1
original after calls: 12.3400
1.23 right(3): 1230 | scale=0
1.23 power(3): 1.23E+3 | scale=-1
compareTo = 0
equals = false
plain right = 1230
plain power = 1230
~~~

Giải thích từng thay đổi:

1. `12.3400` có `scale = 4`. `movePointLeft(2)` tạo `0.123400` với `scale = 6`: dịch giá trị sang trái hai bậc 10 và giữ những số 0 thập phân.
2. `movePointRight(3)` tạo `12340.0` với `scale = 1`; ở đây `scaleByPowerOfTen(3)` cũng có `scale = 1` nên kết quả biểu diễn giống nhau.
3. `1.23` có `scale = 2`. Dịch phải ba vị trí làm `s - n = -1`: `movePointRight(3)` chuẩn hóa thành `1230`, `scale = 0`; `scaleByPowerOfTen(3)` giữ `scale = -1`, in ra `1.23E+3`.
4. `compareTo() == 0` vì cùng giá trị 1230, nhưng `equals() == false` vì `BigDecimal.equals()` còn xét `scale`. `toPlainString()` hiển thị cả hai là `1230`, song không làm thay đổi bản thân đối tượng.
5. Mọi thao tác trả về **BigDecimal mới**; biến `x` ban đầu vẫn là `12.3400`.

## 4. movePointLeft(n): dịch sang trái

`x.movePointLeft(n)` thực hiện phép nhân `x × 10^(-n)`. Với `n > 0`, dấu thập phân chuyển sang trái; nếu cần, Java thêm các số 0 ở đầu phần trị.

~~~java
BigDecimal a = new BigDecimal("12345.67");
System.out.println(a.movePointLeft(2)); // 123.4567
System.out.println(a.movePointLeft(5)); // 0.1234567
System.out.println(a.movePointLeft(-1)); // 123456.7
~~~

Ba dòng này là **đoạn minh họa đặt bên trong một phương thức Java**, không phải một chương trình hoàn chỉnh; đoạn chương trình ở mục 3 là ví dụ biên dịch độc lập.

Lưu ý về `scale`: `new BigDecimal("1E+3")` có giá trị 1000 nhưng `scale = -3`. Gọi `movePointLeft(2)` cho giá trị 10 và `scale = 0`, không giữ `scale = -1`. Đây là điểm khác biệt với `scaleByPowerOfTen(-2)`, vốn tạo giá trị 10 nhưng vẫn giữ `scale = -1`.

Ví dụ thực tế: từ **đơn vị nhỏ nhất** sang đơn vị lớn hơn 100 lần, `new BigDecimal("12345").movePointLeft(2)` cho `123.45`. Chỉ nên dùng hệ số 100 nếu hệ đơn vị đang xử lý thực sự có tỷ lệ 100:1.

## 5. movePointRight(n): dịch sang phải

`x.movePointRight(n)` thực hiện `x × 10^n`. Với `n > 0`, dấu thập phân chuyển sang phải; nếu không còn chữ số sau dấu thập phân, kết quả có `scale = 0` và thêm số 0 vào phần nguyên khi cần.

~~~java
BigDecimal a = new BigDecimal("12.345");
System.out.println(a.movePointRight(2));  // 1234.5
System.out.println(a.movePointRight(4));  // 123450
System.out.println(a.movePointRight(-2)); // 0.12345
~~~

Khi dùng để đổi tiền thành đơn vị nhỏ nhất, **dịch dấu thập phân không đảm bảo số nguyên**. Ví dụ `12.345 × 100 = 1234.5`; nếu đơn vị nhỏ nhất phải nguyên thì phải kiểm tra hoặc áp dụng quy tắc làm tròn rõ ràng, không dùng `intValue()` để âm thầm mất phần lẻ.

Hai phương thức `movePointLeft` và `movePointRight` có tính đối xứng **theo giá trị số**. Không nên mặc định phép dịch ngược tái tạo chính xác `scale` ban đầu, nhất là khi có `scale` âm hoặc khi một bước đã được chuẩn hóa về 0.

## 6. scaleByPowerOfTen(n): điều chỉnh lũy thừa của 10

`x.scaleByPowerOfTen(n)` trả về `x × 10^n` bằng cách chọn `scale mới = scale cũ - n`, kể cả khi kết quả âm. Điều này đặc biệt tự nhiên khi dữ liệu đang ở dạng `1.23E+3` hoặc cần thao tác với bậc 10 lớn.

~~~java
BigDecimal a = new BigDecimal("1.23");
System.out.println(a.scaleByPowerOfTen(3));  // 1.23E+3
System.out.println(a.scaleByPowerOfTen(-2)); // 0.0123
System.out.println(a.scaleByPowerOfTen(0));  // 1.23
~~~

Chẳng hạn `new BigDecimal("5").scaleByPowerOfTen(3)` cho giá trị 5000 ở dạng `5E+3` với `scale = -3`, còn `movePointRight(3)` cho `5000` với `scale = 0`. Không nên diễn giải chữ `E` là sai số; đây chỉ là **cách thể hiện giá trị số dưới dạng khoa học**.

Ví dụ với dữ liệu ban đầu đã có `scale` âm:

~~~java
BigDecimal a = new BigDecimal("1E+3");
System.out.println(a.movePointLeft(0));      // 1000
System.out.println(a.scaleByPowerOfTen(0));  // 1E+3
System.out.println(a.movePointLeft(2));      // 10
System.out.println(a.scaleByPowerOfTen(-2)); // 1E+1
~~~

Dù `movePointLeft(0)` và `scaleByPowerOfTen(0)` giữ cùng giá trị 1000, chúng biểu diễn khác nhau vì cách xử lý `scale` âm.

## 7. Phân biệt với setScale, multiply và làm tròn

Các API có tên gần giống nhưng mục đích khác nhau:

| Phép toán | Thay đổi **giá trị số**? | Mục đích |
|---|---|---|
| `movePointLeft(2)` | Có: chia 100 | Dịch dấu thập phân sang trái |
| `movePointRight(2)` | Có: nhân 100 | Dịch dấu thập phân sang phải |
| `scaleByPowerOfTen(2)` | Có: nhân 100 | Nhân theo bậc 10, giữ `scale` toán học |
| `setScale(2)` | Không, nếu có thể biểu diễn chính xác | Đặt hai chữ số thập phân; có thể ném `ArithmeticException` nếu phải làm tròn |
| `setScale(2, RoundingMode.HALF_UP)` | Có thể, do làm tròn | Quy định độ chính xác biểu diễn và cách làm tròn |
| `multiply(new BigDecimal("100"))` | Có: nhân 100 | Nhân số thập phân tổng quát; `scale` là tổng `scale` của hai toán hạng |

Ví dụ `new BigDecimal("1.234").setScale(2, RoundingMode.HALF_UP)` cho `1.23`, còn `movePointRight(2)` cho `123.4`. Hai phép toán giải quyết hai nhu cầu hoàn toàn khác nhau.

`scaleByPowerOfTen` và hai `movePoint...` không cần `MathContext` hoặc `RoundingMode` vì bản thân việc nhân/chia theo lũy thừa 10 là chính xác trong mô hình `BigDecimal`, miễn `scale` và tài nguyên biểu diễn còn hợp lệ. Nếu bài toán yêu cầu làm tròn đến số chữ số xác định, hãy thực hiện bước `setScale(..., RoundingMode...)` riêng và chọn quy tắc làm tròn theo nghiệp vụ.

Cũng đừng giả định `multiply(new BigDecimal("100"))` có cùng `scale` với `movePointRight(2)`: chẳng hạn `new BigDecimal("1.23").multiply(new BigDecimal("100"))` tạo `123.00` (`scale = 2`), còn `movePointRight(2)` tạo `123` (`scale = 0`).

## 8. Tình huống thực tế: chuyển đơn vị nhỏ nhất một cách an toàn

Giả sử một hệ thống lưu giá trị tiền bằng **đơn vị nguyên nhỏ nhất**, với quy ước một đơn vị lớn bằng 100 đơn vị nhỏ. Chiều đọc dữ liệu dùng `movePointLeft(2)`. Chiều ghi ngược cần xác nhận số đơn vị nhỏ là số nguyên.

Tệp độc lập `MinorUnitDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class MinorUnitDemo {
    public static void main(String[] args) {
        BigDecimal minorUnits = new BigDecimal("12345");
        BigDecimal majorUnits = minorUnits.movePointLeft(2);
        BigInteger exactMinorUnits =
                majorUnits.movePointRight(2).toBigIntegerExact();

        System.out.println("major = " + majorUnits);
        System.out.println("minor = " + exactMinorUnits);

        BigDecimal invalidMajor = new BigDecimal("12.345");
        try {
            invalidMajor.movePointRight(2).toBigIntegerExact();
            System.out.println("unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("fractional minor unit rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac MinorUnitDemo.java
java MinorUnitDemo
~~~

Kết quả:

~~~text
major = 123.45
minor = 12345
fractional minor unit rejected
~~~

Điểm cần nhớ:

- `toBigIntegerExact()` kiểm tra tính nguyên một cách tường minh; khác với `toBigInteger()` vốn bỏ phần lẻ nếu có.
- Nếu nghiệp vụ **cho phép** nhập nhiều hơn hai chữ số thập phân, phải quy định làm tròn hoặc từ chối trước khi lưu. `movePointRight(2)` tự nó không làm tròn.
- Không mặc định mọi loại tiền tệ hay đơn vị đo có tỷ lệ 100:1. Hệ số chuyển đổi phải đến từ quy ước của hệ thống.
- Nếu còn cần giới hạn phạm vi của kiểu `long`, có thể dùng `longValueExact()` thay cho ép kiểu thường để phát hiện cả phần lẻ lẫn tràn miền giá trị.

## 9. Hiển thị, so sánh và dữ liệu bên ngoài

**`toString()` và `toPlainString()`:** `toString()` có thể chọn ký pháp khoa học như `1.23E+3`. `toPlainString()` hiển thị dạng không dùng số mũ, ví dụ `1230`. Đây chỉ là định dạng chuỗi; không nên dùng `toPlainString()` để suy ra `scale` gốc hoặc để chuẩn hóa logic so sánh.

**`compareTo()` và `equals()`:** `compareTo()` so sánh theo giá trị số; `equals()` yêu cầu cả giá trị lẫn `scale` phù hợp. Ví dụ `new BigDecimal("1230")` và `new BigDecimal("1.23E+3")` so sánh bằng 0 theo `compareTo()` nhưng không `equals()`. Trong `HashSet` hoặc khóa `HashMap`, quy tắc `equals()/hashCode()` mới quyết định trùng khóa. Nếu ứng dụng cần giá trị số tương đương được coi là cùng một khóa, phải thống nhất quy tắc chuẩn hóa từ trước; `stripTrailingZeros()` có thể làm đổi `scale` sang số âm và không nên dùng tùy tiện khi `scale` mang ý nghĩa nghiệp vụ.

**Khởi tạo chính xác:** ưu tiên `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` thay vì `new BigDecimal(0.1)`. Constructor nhận `double` ghi nhận giá trị nhị phân chính xác của tham số và có thể tạo chuỗi thập phân dài không mong muốn. Khi đổi đơn vị, lỗi khởi tạo này thường gây nhầm lẫn với hoạt động của các phương thức dịch chuyển.

**Bất biến:** `BigDecimal` là immutable. Lệnh `x.movePointLeft(2);` nếu không giữ giá trị trả về sẽ không thay đổi `x`. Hãy gán `BigDecimal smaller = x.movePointLeft(2);` hoặc gán lại `x = x.movePointLeft(2);` khi thực sự muốn cập nhật biến.

## 10. Các lỗi phổ biến và giới hạn cần cân nhắc

1. **Nhầm hướng nhân/chia:** `movePointLeft(3)` chia 1000, còn `movePointRight(3)` và `scaleByPowerOfTen(3)` nhân 1000. Hãy kiểm tra bằng một giá trị đơn giản như 12.34 trước khi đổi dữ liệu hàng loạt.
2. **Nhầm `scale` với giá trị số:** `1.23E+3` và `1230` là cùng giá trị, nhưng có thể khác `equals()` và cách hiển thị.
3. **Ngầm giả định kết quả nguyên:** `movePointRight(2)` trên `12.345` là `1234.5`, không phải 1235 hay 1234.
4. **Dùng `setScale` thay cho phép nhân/chia:** `setScale` kiểm soát số chữ số sau dấu thập phân; nó không thể thay thế quy tắc nhân với `10^n`.
5. **Bỏ qua `n` âm hoặc bằng 0:** `n` âm đổi hướng; `n = 0` vẫn có thể khiến `movePoint...` điều chỉnh `scale` âm về 0.
6. **Dùng số mũ quá lớn:** `scale` của `BigDecimal` thuộc kiểu `int`. Yêu cầu tạo `scale` ngoài phạm vi, hoặc tạo chuỗi biểu diễn quá lớn, có thể gây `ArithmeticException` hoặc vấn đề tài nguyên. Phải xác thực bậc 10 đầu vào và tránh `toPlainString()` cho các số có số mũ cực lớn.
7. **Lưu trữ/serialize mà không có quy ước:** Nếu hệ thống cần đúng hai chữ số thập phân, hãy định nghĩa rõ số chữ số, quy tắc làm tròn và format đầu ra; không suy luận những quy ước này từ việc gọi `movePointRight` hay `scaleByPowerOfTen`.

## 11. Tự kiểm tra

Hãy dự đoán giá trị, `scale` và biểu diễn `toString()` cho các trường hợp sau:

~~~java
BigDecimal a = new BigDecimal("0.0100");
BigDecimal b = new BigDecimal("5");
BigDecimal c = new BigDecimal("1E+3");

BigDecimal q1 = a.movePointRight(2);
BigDecimal q2 = b.movePointRight(3);
BigDecimal q3 = b.scaleByPowerOfTen(3);
BigDecimal q4 = c.movePointLeft(0);
BigDecimal q5 = c.scaleByPowerOfTen(0);
~~~

Đáp án:

| Biến | Giá trị số | `toString()` | `scale()` |
|---|---:|---|---:|
| `q1` | 1 | `1.00` | 2 |
| `q2` | 5000 | `5000` | 0 |
| `q3` | 5000 | `5E+3` | -3 |
| `q4` | 1000 | `1000` | 0 |
| `q5` | 1000 | `1E+3` | -3 |

Hai câu hỏi quan trọng để tự giải thích: Vì sao `q2.compareTo(q3) == 0` nhưng `q2.equals(q3) == false`? Vì sao `q4` và `q5` có cùng giá trị mà `toString()` khác nhau? Cả hai đều bắt nguồn từ cách `scale` được bảo toàn hoặc được chuẩn hóa.

Khi chọn phương thức, hãy xuất phát từ **quy tắc toán học** (chia hay nhân với `10^n`), rồi xác định xem **`scale` có mang ý nghĩa nghiệp vụ hoặc ảnh hưởng đến đầu ra, phép so sánh và lưu trữ hay không**. Dịch dấu thập phân theo `movePointLeft`/`movePointRight` thuận tiện cho đổi đơn vị; `scaleByPowerOfTen` phù hợp khi muốn thao tác rõ ràng với bậc lũy thừa 10 và giữ `scale` có thể âm.