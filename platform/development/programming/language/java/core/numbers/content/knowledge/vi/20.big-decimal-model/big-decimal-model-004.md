# Scale bằng 0, dương hoặc âm trong mô hình `BigDecimal`

`java.math.BigDecimal` lưu số thập phân **theo giá trị nguyên không có dấu phẩy và một số nguyên `scale`**. Scale có thể **dương, bằng 0 hoặc âm**. Đó là một phần của biểu diễn dữ liệu, không đơn giản là “bao nhiêu chữ số hiển thị sau dấu chấm”.

Trong Java, giá trị toán học của một `BigDecimal` được xác định bởi:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`unscaledValue()` trả về `BigInteger`, còn `scale()` trả về `int`. Chỉ cần nhớ quy tắc **mũ âm của scale** là có thể hiểu cả ba trường hợp:

| `unscaledValue` | `scale` | Tính toán | Giá trị |
|---:|---:|---|---:|
| 12345 | 2 | `12345 × 10^-2` | `123.45` |
| 12345 | 0 | `12345 × 10^0` | `12345` |
| 12345 | -2 | `12345 × 10^2` | `1234500` |
| -123 | 3 | `-123 × 10^-3` | `-0.123` |
| 1 | -3 | `1 × 10^3` | `1000` |

Cách mô hình hóa này giúp `BigDecimal` biểu diễn thập phân hữu hạn **chính xác**, không mắc sai số nhị phân vốn phổ biến với `double`. Bài học tập trung vào ý nghĩa của dấu scale, cách quan sát biểu diễn và những hệ quả khi thay đổi scale.

## 1. Scale dương: số chữ số về bên phải dấu thập phân

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 7
```

Đây là đoạn mã minh họa đặt trong phương thức hoặc JShell. Chuỗi `"123.4500"` có bốn chữ số sau dấu thập phân nên `scale()` bằng **4**. Theo công thức, `1234500 × 10^-4 = 123.4500`.

Hai số `new BigDecimal("1.2")` và `new BigDecimal("1.20")` có **giá trị toán học bằng nhau**, nhưng có `scale` lần lượt là 1 và 2. Các số 0 ở cuối được giữ trong biểu diễn và có thể quan trọng khi dữ liệu cần ghi lại chính xác cách biểu diễn hoặc các ràng buộc scale.

Scale dương **không đảm bảo** giá trị phải nằm giữa -1 và 1. Chẳng hạn `123.45` có scale 2, còn `12345.67` cũng có scale 2. Scale là thông tin về vị trí dấu thập phân so với `unscaledValue`.

## 2. Scale bằng 0: số nguyên theo hệ thập phân

Khi `scale = 0`, công thức trở thành:

\[
\text{value} = \text{unscaledValue} \times 10^0 = \text{unscaledValue}.
\]

Ví dụ:

```java
BigDecimal count = new BigDecimal("12345");
// count.unscaledValue() = 12345
// count.scale() = 0
// count.toPlainString() = "12345"
```

Một `BigDecimal` scale 0 biểu diễn giá trị nguyên; nhưng **không phải mọi `BigDecimal` có giá trị nguyên đều bắt buộc có scale 0**:

- `new BigDecimal("100")` có scale 0.
- `new BigDecimal("100.0")` có scale 1.
- `new BigDecimal("1E+2")` có scale -2.
- Cả ba cùng biểu diễn giá trị số **100**.

Do đó cần phân biệt **giá trị số là một số nguyên** với **biểu diễn có scale bằng 0**.

## 3. Scale âm: biểu diễn bội số của 10

Khi `scale < 0`, số mũ `-scale` là số dương; `unscaledValue` được **nhân** với một lũy thừa của 10. Vì thế:

```java
BigDecimal x = new BigDecimal("1.23E+4");
// x.unscaledValue() = 123
// x.scale() = -2
// x.toPlainString() = "12300"
```

`1.23E+4` nghĩa là `1.23 × 10^4 = 12300`. Trên thực tế, biểu diễn bên trong có `unscaledValue = 123`, `scale = -2`, nên `123 × 10^2 = 12300`.

Có thể tạo trực tiếp biểu diễn này:

```java
import java.math.BigInteger;

BigDecimal x = new BigDecimal(new BigInteger("123"), -2);
// x.scale() = -2
// x.toString() = "1.23E+4"
// x.toPlainString() = "12300"
```

Đây là ví dụ minh họa, cần đặt trong một phương thức và có đủ import. Đừng hiểu “scale âm” là “giá trị âm”: dấu của số nằm ở `unscaledValue`, còn dấu scale điều khiển **lũy thừa của 10**. Một `BigDecimal` với scale -2 vẫn có thể chứa số dương, âm hoặc 0.

Với scale -2, các giá trị được biểu diễn chính xác từ những `unscaledValue` nguyên là bội của 100; với scale -3 là bội của 1000. Chẳng hạn 12345 không thể được giữ nguyên giá trị ở scale -2 vì 12345 không chia hết cho 100.

## 4. `scale` khác `precision`

`scale()` và `precision()` không mô tả cùng một thuộc tính:

- `scale`: số mũ âm trong công thức `unscaled × 10^-scale`, có thể âm, 0 hoặc dương.
- `precision`: số **chữ số thập phân trong `unscaledValue`** (bỏ dấu âm), tính theo định nghĩa của `BigDecimal`; đối với số 0, precision là 1.

| Giá trị được tạo từ chuỗi | `unscaledValue` | `scale` | `precision` |
|---|---:|---:|---:|
| `"123.4500"` | 1234500 | 4 | 7 |
| `"12345"` | 12345 | 0 | 5 |
| `"1.23E+4"` | 123 | -2 | 3 |
| `"0.000"` | 0 | 3 | 1 |
| `"100.00"` | 10000 | 2 | 5 |

Một số có scale dương lớn không có nghĩa precision phải lớn; ví dụ `0.0001` có scale 4 nhưng precision 1. Ngược lại, số có scale âm có thể có precision nhỏ nhưng giá trị rất lớn. Khi muốn khống chế **số chữ số có nghĩa** trong phép toán, Java cung cấp `MathContext`; khi muốn quy định **vị trí phần thập phân**, API liên quan thường là `setScale`.

## 5. `setScale`: thay đổi biểu diễn và khả năng làm tròn

`setScale(int newScale)` yêu cầu kết quả có scale cụ thể. Nếu đổi scale mà vẫn giữ nguyên được giá trị số, Java trả một `BigDecimal` tương đương về toán học. Nếu việc **giảm scale** khiến phải bỏ phần giá trị khác 0, phiên bản một tham số sẽ ném `ArithmeticException` (vì phép làm tròn không được chỉ định).

### Tăng scale: thường thêm các chữ số 0

```java
BigDecimal price = new BigDecimal("1.23");
BigDecimal displayed = price.setScale(4);
// displayed.toPlainString() = "1.2300"
// displayed.unscaledValue() = 12300
// displayed.scale() = 4
// price.scale() vẫn bằng 2
```

Chuyển từ scale 2 sang scale 4 nhân `unscaledValue` với 100, nhưng **giữ nguyên giá trị số 1.23**. Những số 0 được thêm vào biểu diễn.

### Giảm scale chính xác

```java
BigDecimal whole = new BigDecimal("12300");
BigDecimal hundreds = whole.setScale(-2);
// hundreds.toString() = "1.23E+4"
// hundreds.toPlainString() = "12300"
// hundreds.unscaledValue() = 123
// hundreds.scale() = -2
```

Ở đây 12300 chia hết cho 100, nên giảm scale từ 0 xuống -2 không làm mất thông tin. Tương tự, `new BigDecimal("1.2300").setScale(2)` giữ được chính xác giá trị 1.23 vì chỉ bỏ các số 0 cuối.

### Giảm scale không chính xác: phải chọn quy tắc làm tròn

```java
BigDecimal number = new BigDecimal("12345");

// number.setScale(-2); // ArithmeticException
BigDecimal rounded = number.setScale(-2, java.math.RoundingMode.HALF_UP);
// rounded.toPlainString() = "12300"
```

Chọn scale -2 nghĩa là làm tròn tới **hàng trăm**, không phải “giữ âm hai chữ số thập phân”. Giá trị 12345 nằm gần 12300 hơn 12400, nên với `HALF_UP` kết quả là 12300. Với `12350`, trường hợp đúng giữa hai mức 12300 và 12400, `HALF_UP` cho **12400**.

`setScale(int, RoundingMode)` biểu đạt rõ trường hợp cần làm tròn. Đặt chế độ dựa trên quy định nghiệp vụ: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`, `FLOOR`, v.v. Một phép làm tròn không thể tự quyết định đúng chính sách tính tiền, thuế hoặc số liệu báo cáo nếu ứng dụng chưa xác định **thời điểm** và **quy tắc** làm tròn.

### Bảng quy đổi scale hữu ích

| Giá trị gốc | Scale gốc | Scale mới | Kết quả | Cần làm tròn? |
|---|---:|---:|---|---|
| `1.23` | 2 | 4 | `1.2300` | Không |
| `1.2300` | 4 | 2 | `1.23` | Không |
| `12300` | 0 | -2 | `1.23E+4` | Không |
| `12345` | 0 | -2 | `1.23E+4` với `HALF_UP` | Có |
| `12350` | 0 | -2 | `1.24E+4` với `HALF_UP` | Có |
| `100` | 0 | 0 | `100` | Không |

Bảng dùng biểu diễn thông thường của `toString()`. Với `toPlainString()`, kết quả scale âm ở trên được viết dưới dạng `"12300"` và `"12400"`.

## 6. `stripTrailingZeros`: vì sao scale có thể trở thành âm?

Phương thức `stripTrailingZeros()` loại các chữ số 0 cuối trong biểu diễn mà vẫn giữ **giá trị số**. Nó có thể làm `scale` giảm xuống dưới 0.

```java
BigDecimal initial = new BigDecimal("100.00");
BigDecimal stripped = initial.stripTrailingZeros();

// initial: unscaled=10000, scale=2, toString="100.00"
// stripped: unscaled=1, scale=-2, toString="1E+2"
```

Giải thích: `100.00 = 10000 × 10^-2 = 100`. Sau khi bỏ hết các số 0 cuối của `unscaledValue`, còn `1`; để tiếp tục có giá trị 100, scale phải là -2, vì `1 × 10^2 = 100`.

Một điểm đặc biệt là số 0:

```java
BigDecimal zero = new BigDecimal("0.000");
BigDecimal normalized = zero.stripTrailingZeros();
// normalized có scale=0, precision=1 và biểu diễn là "0"
```

Điều này không có nghĩa mọi số 0 ban đầu đều có scale 0: chỉ **sau** khi gọi `stripTrailingZeros()` ta nhận biểu diễn chuẩn hóa ở trường hợp ví dụ này.

## 7. `equals` và `compareTo`: scale ảnh hưởng kết quả so sánh

`BigDecimal.equals` yêu cầu cả **giá trị số** và **scale** phù hợp. Còn `compareTo` so theo **thứ tự giá trị số**, bỏ qua khác biệt biểu diễn scale.

```java
BigDecimal a = new BigDecimal("1.0");  // scale=1
BigDecimal b = new BigDecimal("1.00"); // scale=2

a.equals(b);          // false
a.compareTo(b) == 0;  // true
```

Vì vậy:

- Dùng `compareTo(...) == 0` nếu cần kiểm tra **bằng nhau về giá trị toán học**.
- Dùng `equals(...)` nếu scale là một phần quan trọng trong khái niệm bằng nhau của dữ liệu.
- `hashCode()` đi cùng hợp đồng `equals`, nên các `BigDecimal` bằng nhau về số học nhưng khác scale **có thể có hash khác nhau**. Nếu dùng làm khóa trong `HashMap`/`HashSet`, phải quyết định chính sách chuẩn hóa trước.
- `stripTrailingZeros()` có thể giúp chuẩn hóa giá trị để so sánh hoặc tạo khóa, nhưng làm thay đổi scale biểu diễn; chỉ áp dụng khi điều đó phù hợp với hợp đồng dữ liệu.

Đặc biệt, `new BigDecimal("100")` và `new BigDecimal("1E+2")` có cùng giá trị số, nhưng scale lần lượt là 0 và -2, nên `equals` là `false`, còn `compareTo` trả 0.

## 8. `toString`, `toPlainString` và ký pháp khoa học

Khi scale âm, `BigDecimal.toString()` thường biểu diễn bằng ký pháp khoa học:

```java
BigDecimal number = new BigDecimal("1.23E+4");

number.toString();      // "1.23E+4"
number.toPlainString(); // "12300"
number.scale();         // -2
```

`toString()` tạo biểu diễn chuẩn theo quy tắc của `BigDecimal` và giữ thông tin cần thiết cho việc round-trip biểu diễn. `toPlainString()` bỏ ký pháp số mũ, thường dễ hiển thị với người dùng, nhưng **không tự giữ metadata scale âm khi được phân tích ngược từ chuỗi**:

```java
BigDecimal x = new BigDecimal("1E+3"); // scale=-3
BigDecimal y = new BigDecimal(x.toPlainString()); // scale=0
// x.compareTo(y) == 0, nhưng x.equals(y) == false
```

Với dữ liệu lưu trữ cần bảo toàn scale, phải giữ biểu diễn phù hợp, hoặc lưu rõ `unscaledValue` và `scale`. Không nên dựa vào chuỗi thập phân dạng plain để phục hồi được scale âm.

## 9. `movePointRight`, `movePointLeft` và `scaleByPowerOfTen`

Các phương thức dịch dấu thập phân được sử dụng khi cần nhân/chia cho một lũy thừa của 10:

- `movePointRight(n)`: tăng giá trị lên `10^n`, nhưng đảm bảo scale kết quả **không âm**.
- `movePointLeft(n)`: chia giá trị cho `10^n`, cũng đảm bảo scale kết quả **không âm**.
- `scaleByPowerOfTen(n)`: nhân giá trị với `10^n`, chủ yếu bằng cách điều chỉnh `scale` thành `scale - n`; scale kết quả **có thể âm**.

Ví dụ cùng giá trị khởi đầu:

```java
BigDecimal original = new BigDecimal("1.00"); // unscaled=100, scale=2

BigDecimal moved = original.movePointRight(3);
// moved.toPlainString() = "1000", scale=0

BigDecimal scaled = original.scaleByPowerOfTen(3);
// scaled.toString() = "1.00E+3", scale=-1
// scaled.toPlainString() = "1000"
```

Hai kết quả cùng **giá trị số 1000**, nhưng có scale khác nhau (0 và -1); `compareTo` cho bằng nhau nhưng `equals` không bằng nhau. Đây là khác biệt có thể ảnh hưởng lưu trữ, định dạng và logic đồng nhất dữ liệu.

Các thao tác nhân/chia lũy thừa lớn có thể cần nhiều tài nguyên hoặc gây `ArithmeticException` trong trường hợp scale tính ra vượt miền `int`. Đừng coi scale là một con số luôn tăng/giảm vô hạn mà không có giới hạn.

## 10. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp **`BigDecimalScaleDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigDecimalScaleDemo {
    static void show(String name, BigDecimal x) {
        System.out.println(name + ": " + x.toString()
                + " | plain=" + x.toPlainString()
                + " | unscaled=" + x.unscaledValue()
                + " | scale=" + x.scale()
                + " | precision=" + x.precision());
    }

    public static void main(String[] args) {
        show("positive", new BigDecimal("123.4500"));
        show("zero", new BigDecimal("12345"));
        show("negative", new BigDecimal("1.23E+4"));
        show("constructor", new BigDecimal(new BigInteger("123"), -2));

        show("raise scale", new BigDecimal("1.23").setScale(4));
        show("exact lower", new BigDecimal("12300").setScale(-2));
        show("strip", new BigDecimal("100.00").stripTrailingZeros());
        show("zero after strip", new BigDecimal("0.000").stripTrailingZeros());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("equal objects: " + a.equals(b));
        System.out.println("same numeric value: " + (a.compareTo(b) == 0));

        try {
            new BigDecimal("12345").setScale(-2);
        } catch (ArithmeticException ex) {
            System.out.println("inexact setScale: ArithmeticException");
        }
        show("rounded", new BigDecimal("12350").setScale(-2, RoundingMode.HALF_UP));
        show("movePointRight", new BigDecimal("1.00").movePointRight(3));
        show("scaleByPowerOfTen", new BigDecimal("1.00").scaleByPowerOfTen(3));
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 BigDecimalScaleDemo.java
java BigDecimalScaleDemo
```

Stdout đã được xác minh bằng cách biên dịch và thực thi Java:

```text
positive: 123.4500 | plain=123.4500 | unscaled=1234500 | scale=4 | precision=7
zero: 12345 | plain=12345 | unscaled=12345 | scale=0 | precision=5
negative: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
constructor: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
raise scale: 1.2300 | plain=1.2300 | unscaled=12300 | scale=4 | precision=5
exact lower: 1.23E+4 | plain=12300 | unscaled=123 | scale=-2 | precision=3
strip: 1E+2 | plain=100 | unscaled=1 | scale=-2 | precision=1
zero after strip: 0 | plain=0 | unscaled=0 | scale=0 | precision=1
equal objects: false
same numeric value: true
inexact setScale: ArithmeticException
rounded: 1.24E+4 | plain=12400 | unscaled=124 | scale=-2 | precision=3
movePointRight: 1000 | plain=1000 | unscaled=1000 | scale=0 | precision=4
scaleByPowerOfTen: 1.00E+3 | plain=1000 | unscaled=100 | scale=-1 | precision=3
```

Chương trình cho thấy mối liên hệ nhất quán giữa ba thông tin `unscaled`, `scale`, `precision`. Hai dòng `negative`/`constructor` minh họa hai cách tạo cùng biểu diễn scale âm. Dòng `strip` cho thấy chuẩn hóa có thể tạo scale âm; `zero after strip` cho thấy trường hợp số 0 được chuẩn hóa về scale 0. Hai dòng `equal objects`/`same numeric value` phân biệt `equals` với `compareTo`. Cuối cùng `movePointRight` và `scaleByPowerOfTen` tạo **cùng giá trị** nhưng **khác scale**.

## 11. Những lỗi thường gặp

1. **Cho rằng scale luôn không âm.** Chuỗi dạng số mũ như `"1E+3"` hoặc `stripTrailingZeros()` có thể dẫn tới scale âm một cách hợp lệ.
2. **Cho rằng scale âm là số âm.** Scale âm thể hiện nhân với `10` mũ dương; dấu của giá trị độc lập với dấu của scale.
3. **Nhầm scale với precision.** `123.4500` có scale 4 nhưng precision 7; `1.23E+4` có scale -2 nhưng precision 3.
4. **Cho rằng giá trị số nguyên nhất thiết phải scale 0.** `100`, `100.0`, `1E+2` cùng giá trị số nhưng scale lần lượt 0, 1, -2.
5. **Giảm scale mà bỏ qua việc làm tròn.** `setScale(-2)` trên `12345` ném `ArithmeticException`; nếu chủ đích làm tròn tới hàng trăm, chỉ định `RoundingMode`.
6. **Lạm dụng `equals` để so giá trị toán học.** `1.0.equals(1.00)` là false; dùng `compareTo == 0` khi chỉ xét giá trị.
7. **Dùng `toPlainString` để lưu mà mong phục hồi scale âm.** Chuỗi `"1000"` phân tích ngược có scale 0, khác `"1E+3"` có scale -3.
8. **Tưởng rằng `stripTrailingZeros` chỉ giảm scale tới 0.** `100.00` chuẩn hóa thành `1E+2` có scale -2.
9. **Trộn `BigDecimal` với `double` mà bỏ qua biểu diễn.** `new BigDecimal(0.1)` tạo số thập phân chính xác tương ứng giá trị nhị phân `double` đã làm tròn; để biểu đạt 0.1 thập phân chính xác, dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)`.
10. **Suy luận scale kết quả mọi phép số học đều giống một toán hạng.** Ví dụ với phép nhân, scale ưu tiên của kết quả là tổng scale hai toán hạng (trừ các trường hợp giới hạn/điều chỉnh biểu diễn); các phép khác có quy tắc riêng. Sau phép tính, đọc `scale()` thực tế nếu đây là một phần của hợp đồng dữ liệu.

## 12. Bài tập tự kiểm tra

Dựa vào công thức `value = unscaled × 10^-scale`, hãy xác định giá trị số và `scale`:

| Câu hỏi | Đáp án |
|---|---|
| `new BigDecimal("3.1400")` có scale bao nhiêu? | 4; unscaled là 31400 |
| `new BigDecimal("4E+3")` có scale và giá trị nào? | Scale -3; giá trị 4000 |
| `new BigDecimal("150").setScale(-1)` có thành công không? | Có; giá trị 150; scale -1; `toString()` là `"1.5E+2"` |
| `new BigDecimal("155").setScale(-1)` có thành công không? | Không; ném `ArithmeticException` nếu không có rounding mode |
| `new BigDecimal("100.0").stripTrailingZeros()` có scale nào? | -2; giá trị 100; biểu diễn `"1E+2"` |
| `"100.0"` và `"1E+2"` có `compareTo == 0` không? | Có, vì cùng giá trị số 100 |
| Hai giá trị ở câu trên có `equals` không? | Không, vì scale 1 khác -2 |
| `new BigDecimal("0.000").precision()` trả gì? | 1 |

Để tự kiểm chứng thêm, thử lấy một `BigDecimal` bất kỳ rồi in `toString`, `toPlainString`, `unscaledValue`, `scale` và `precision`. Dự đoán trước những giá trị nào khiến `setScale` giảm được chính xác, những giá trị nào bắt buộc làm tròn.

## Ghi nhớ

- Công thức nền tảng là **`value = unscaledValue × 10^-scale`**.
- Scale **dương** chia phần nguyên biểu diễn cho lũy thừa của 10; scale **0** giữ nguyên; scale **âm** nhân với lũy thừa của 10.
- Scale là một phần của **biểu diễn**, không phải dấu số hay precision.
- `setScale` có thể bảo toàn giá trị hoặc cần làm tròn; `stripTrailingZeros` có thể tạo scale âm.
- `equals` xét cả scale; `compareTo` xét giá trị toán học.
- Khi cần bảo toàn scale âm qua lưu trữ, phải chọn biểu diễn có giữ được thông tin đó, thay vì chỉ dựa vào `toPlainString`.