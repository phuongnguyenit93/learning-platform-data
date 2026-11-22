# Nhầm precision với số chữ số sau dấu thập phân trong Java `BigDecimal`

## 1. Sai lầm cốt lõi

Trong Java, **precision** và **scale** của `BigDecimal` là hai khái niệm khác nhau:

- **Precision (độ chính xác chữ số):** số chữ số có nghĩa trong biểu diễn thập phân của giá trị không scale. `BigDecimal.precision()` trả số chữ số của unscaled value, bỏ dấu; riêng zero có precision 1.
- **Scale:** số mũ điều chỉnh vị trí dấu thập phân trong công thức `unscaledValue × 10^(-scale)`. Với dạng thập phân thông thường có scale không âm, scale thường tương ứng số chữ số sau dấu thập phân của **biểu diễn hiện tại**. Scale cũng có thể âm.

Ví dụ, `new BigDecimal("123.4500")` có **precision = 7**, **scale = 4**, không phải precision = 4. Khi viết `new MathContext(3, HALF_UP)`, số 3 **không** có nghĩa “giữ ba chữ số sau dấu thập phân”; nó có nghĩa “tối đa ba chữ số có nghĩa”.

So sánh:

~~~java
BigDecimal number = new BigDecimal("1234.567");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(number.round(mc));                         // 1.23E+3
System.out.println(number.setScale(3, RoundingMode.HALF_UP));  // 1234.567
~~~

Đây là **đoạn minh họa cần import `java.math.*` và đặt trong phương thức**; chương trình chạy độc lập ở phần 9.

Cả hai lời gọi đều chứa số 3, nhưng có ý nghĩa hoàn toàn khác:

- `round(mc)`: chỉ giữ ba chữ số có nghĩa, nên 1234.567 trở thành khoảng 1230, được in `1.23E+3`.
- `setScale(3, ...)`: yêu cầu đúng ba chữ số sau dấu thập phân, mà `1234.567` đã có sẵn, nên không cần làm tròn.

**Cách ghi nhớ:** `MathContext` điều khiển **số chữ số có nghĩa của toàn bộ kết quả**; `setScale` điều khiển **vị trí dấu thập phân/số chữ số thập phân của biểu diễn**.

## 2. Công thức nền tảng: `unscaledValue`, scale, precision

Một `BigDecimal` gồm một số nguyên không scale và một scale nguyên:

~~~text
numericValue = unscaledValue × 10^(-scale)
~~~

Ví dụ:

| Chuỗi đầu vào | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"12"` | 12 | 0 | 2 |
| `"12.0"` | 120 | 1 | 3 |
| `"12.00"` | 1200 | 2 | 4 |
| `"123.4500"` | 1234500 | 4 | 7 |
| `"0.00120"` | 120 | 5 | 3 |
| `"0.0000"` | 0 | 4 | 1 |
| `"1E+3"` | 1 | -3 | 1 |

Đọc bảng đúng cách:

1. `"0.00120"` có 5 vị trí sau dấu thập phân nhưng chỉ có **3 chữ số có nghĩa**: 1, 2 và 0 tận cùng. Các zero đứng trước chữ số 1 chỉ xác định vị trí dấu thập phân.
2. `"123.4500"` có **7 chữ số có nghĩa** trong unscaled value 1234500. Các zero tận cùng vẫn là chữ số được lưu trong biểu diễn và được tính vào precision của đối tượng hiện tại.
3. `"1E+3"` có giá trị toán học 1000 nhưng scale **-3**: `1 × 10^3`. Không thể định nghĩa scale chỉ bằng cách “đếm dấu chấm” trên chuỗi `toString()`.
4. Zero có precision 1, nhưng có thể có nhiều scale khác nhau. `"0"` và `"0.0000"` bằng nhau về giá trị, không giống nhau về scale.

Không nên suy đoán precision hoặc scale chỉ từ độ lớn số, cũng không nên bỏ qua trailing zeros nếu hợp đồng dữ liệu cần giữ chúng.

### 2.1. `toString()` không nhất thiết cho dạng thập phân thường

Sau phép làm tròn hoặc normalize, `BigDecimal.toString()` có thể dùng ký pháp mũ như `1.23E+3`. Điều này không có nghĩa số đã biến thành kiểu `double`, cũng không phải lỗi tính toán; đó là cách biểu diễn văn bản của `BigDecimal` với precision/scale hiện tại.

`toPlainString()` cho chuỗi không sử dụng ký pháp mũ. Tuy nhiên, không nên dùng chuỗi hiển thị để xác định precision hoặc scale; dùng trực tiếp `precision()` và `scale()`.

## 3. `precision()` của đối tượng và precision trong `MathContext`

Hai chữ “precision” liên quan nhưng có vai trò khác nhau:

- `value.precision()` **đọc trạng thái hiện tại** của `BigDecimal`: bao nhiêu chữ số có nghĩa đang được lưu trong unscaled value.
- `new MathContext(p, mode)` **đặt giới hạn precision cho kết quả phép toán sử dụng context**, với `p > 0` là số chữ số có nghĩa tối đa.

Ví dụ:

~~~java
BigDecimal value = new BigDecimal("123.4500");
System.out.println(value.precision()); // 7
System.out.println(value.scale());     // 4

BigDecimal rounded = value.round(
        new MathContext(4, RoundingMode.HALF_UP));
System.out.println(rounded);            // 123.5
System.out.println(rounded.precision()); // 4
System.out.println(rounded.scale());     // 1
~~~

`MathContext` không chỉ “đặt cờ metadata”. Khi kết quả chính xác có nhiều chữ số có nghĩa hơn giới hạn, `BigDecimal` **làm tròn giá trị** theo rounding mode. Có trường hợp làm tròn chỉ loại bỏ zero tận cùng mà không đổi giá trị; có trường hợp làm tròn thật sự thay đổi số.

### 3.1. Precision = 0 trong `MathContext`

~~~java
MathContext unlimited = MathContext.UNLIMITED;
// unlimited.getPrecision() == 0
~~~

Precision bằng 0 trong `MathContext` có nghĩa **không giới hạn chữ số có nghĩa**, không phải “giữ 0 chữ số” và không phải “giữ 0 số sau dấu thập phân”. Nó không khiến các phép toán thập phân không có kết quả hữu hạn, như `1 ÷ 3`, tự có biểu diễn `BigDecimal` chính xác hữu hạn.

`MathContext.DECIMAL32`, `DECIMAL64`, `DECIMAL128` lần lượt có precision 7, 16 và 34, sử dụng `HALF_EVEN`. Chúng cũng điều khiển **chữ số có nghĩa**, không phải scale 7/16/34.

## 4. `setScale()`: quy tắc về vị trí dấu thập phân

Khi yêu cầu là “giá trị có **đúng hai chữ số sau dấu chấm**”, thường dùng:

~~~java
BigDecimal stored = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

`setScale(2, ...)` trả `BigDecimal` có scale đúng 2 hoặc ném ngoại lệ nếu không thực hiện được theo quy tắc đã chỉ định. Với dạng thường, kết quả có đúng hai chữ số thập phân khi in theo biểu diễn scale 2.

Các ví dụ:

| Giá trị ban đầu | Gọi | Kết quả |
| --- | --- | --- |
| `12` | `setScale(2, HALF_UP)` | `12.00` |
| `12.3` | `setScale(2, HALF_UP)` | `12.30` |
| `12.345` | `setScale(2, HALF_UP)` | `12.35` |
| `12.345` | `setScale(2, HALF_EVEN)` | `12.34` |
| `-1.236` | `setScale(2, HALF_UP)` | `-1.24` |
| `12.3400` | `setScale(2, UNNECESSARY)` | `12.34` |

`setScale` có thể tăng scale bằng cách thêm zero mà không đổi giá trị; khi giảm scale, nó cần bỏ bớt chữ số và có thể phải làm tròn. Vì vậy, phải xác định **rounding mode** theo yêu cầu nghiệp vụ, không chỉ đặt scale.

Nếu cấm thay đổi giá trị, dùng `RoundingMode.UNNECESSARY`:

~~~java
BigDecimal exact = new BigDecimal("12.3400")
        .setScale(2, RoundingMode.UNNECESSARY); // 12.34

// Ném ArithmeticException nếu thực thi:
// new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
~~~

**`UNNECESSARY` không có nghĩa là làm tròn xuống hoặc bỏ qua chữ số:** nó yêu cầu việc điều chỉnh scale phải **chính xác**, nếu không báo lỗi.

## 5. `round(new MathContext(...))`: giới hạn chữ số có nghĩa

Xét cùng một số dưới hai phép biến đổi:

| Đầu vào | Precision 3 với `HALF_UP` | Scale 3 với `HALF_UP` |
| --- | --- | --- |
| `1234.567` | `1.23E+3` (= 1230) | `1234.567` |
| `0.0012345` | `0.00123` | `0.001` |
| `9.995` | `10.0` | `9.995` |
| `12.34` | `12.3` | `12.340` |

Tại sao `0.0012345` với precision 3 được `0.00123`? Các số 0 trước chữ số 1 không chiếm precision. Trong khi đó, `setScale(3)` chỉ cho phép ba chữ số sau dấu chấm nên phải đổi thành `0.001`.

### 5.1. Carry làm thay đổi phần nguyên và scale

Ví dụ:

~~~java
BigDecimal value = new BigDecimal("9.995");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal rounded = value.round(mc);
System.out.println(rounded);             // 10.0
System.out.println(rounded.precision());  // 3
System.out.println(rounded.scale());      // 1

BigDecimal scaled = value.setScale(2, RoundingMode.HALF_UP);
System.out.println(scaled);              // 10.00
System.out.println(scaled.precision());   // 4
System.out.println(scaled.scale());       // 2
~~~

Cả hai đều có giá trị số học bằng 10 sau khi làm tròn, nhưng **precision và scale của kết quả khác nhau**. Chúng không thể thay thế nhau trong một hợp đồng yêu cầu scale 2.

Khi phép làm tròn tạo carry từ 9 lên 10, độ dài phần nguyên có thể tăng. Điều này rất quan trọng khi kiểm tra giới hạn cột database, miền giá trị tiền tệ hoặc độ rộng báo cáo.

### 5.2. Trailing zeros vẫn ảnh hưởng precision

~~~java
BigDecimal value = new BigDecimal("1000.00");
System.out.println(value.precision()); // 6
System.out.println(value.scale());     // 2

BigDecimal result = value.round(
        new MathContext(3, RoundingMode.HALF_UP));
System.out.println(result);            // 1.00E+3
~~~

Ở ví dụ này, phép làm tròn có thể **loại bỏ chữ số 0 dư** mà không mất giá trị toán học. Kết quả `1.00E+3` có precision 3 và scale -1, không phải scale 2.

Nếu yêu cầu là giữ hai chữ số sau dấu chấm trong đầu ra, **`MathContext(3)` không thực hiện yêu cầu ấy**.

## 6. `MathContext` trong các phép tính không giống `setScale` cuối cùng

Một số phương thức `BigDecimal` nhận `MathContext`:

~~~java
BigDecimal total = left.add(right, mc);
BigDecimal product = left.multiply(right, mc);
BigDecimal quotient = left.divide(right, mc);
~~~

Khi context giới hạn precision, **kết quả của từng phép toán** có thể bị làm tròn tới số chữ số có nghĩa được cho phép. Điều này khác với chiến lược:

~~~java
BigDecimal exactTotal = left.add(right);
BigDecimal stored = exactTotal.setScale(2, RoundingMode.HALF_EVEN);
~~~

Cách thứ nhất hạn chế **chữ số có nghĩa ở mỗi kết quả của phép toán**; cách thứ hai lấy tổng chính xác rồi chuẩn hóa về **scale 2** theo chính sách lưu trữ.

Nếu cộng nhiều khoản tiền, hai quy tắc có thể cho tổng khác nhau. Ví dụ với `1.234 + 0.004 + 0.004` và `MathContext(3, HALF_UP)`:

- Cộng chính xác được `1.242`, rồi `round(mc)` thành `1.24`.
- Dùng `add(x, mc)` ở **từng lần cộng** có thể ra `1.23`, vì các phần nhỏ đã mất khi làm tròn trung gian.

Nếu hợp đồng chỉ yêu cầu “tổng cuối cùng có hai chữ số sau dấu chấm”, không được tự coi `new MathContext(2, ...)` là cùng một yêu cầu. Nó sẽ giới hạn toàn bộ tổng chỉ còn **hai chữ số có nghĩa**, kể cả các chữ số phần nguyên.

### 6.1. Phép chia cho thấy khác biệt rõ hơn

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal byScale = one.divide(
        eight, 2, RoundingMode.HALF_UP); // 0.13

BigDecimal byPrecision = one.divide(
        eight, new MathContext(2, RoundingMode.HALF_UP)); // 0.13
~~~

Hai kết quả **tình cờ bằng nhau trong phép chia này**. Nhưng nếu đổi số bị chia hoặc tỷ lệ, ý nghĩa vẫn khác: `divide(divisor, scale, mode)` chọn scale kết quả; `divide(divisor, MathContext)` chọn precision kết quả. Không suy ra hai overload tương đương từ một test đơn lẻ.

Ví dụ phân biệt rõ:

~~~java
BigDecimal numerator = new BigDecimal("1234");
BigDecimal denominator = new BigDecimal("8");

BigDecimal byScale = numerator.divide(
        denominator, 2, RoundingMode.HALF_UP); // 154.25

BigDecimal byPrecision = numerator.divide(
        denominator, new MathContext(2, RoundingMode.HALF_UP)); // 1.5E+2
~~~

Với context precision 2, kết quả 154.25 phải làm tròn còn 150, còn scale 2 giữ kết quả chính xác 154.25.

## 7. Thiết kế dữ liệu: precision và scale trong database

Trong nhiều hệ quản trị cơ sở dữ liệu, `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` dùng:

- `p`: tổng số chữ số thập phân được phép theo định nghĩa cột.
- `s`: số chữ số sau dấu thập phân, theo quy định của hệ quản trị/cột.

Ví dụ thông thường `DECIMAL(5,2)` cho phép các giá trị như `999.99`, nhưng `1234.56` vượt phần nguyên tối đa ba chữ số của định dạng đó.

Điều này **không có nghĩa** cứ dùng `new MathContext(5, ...)` là đã đảm bảo tương thích `DECIMAL(5,2)`. Context không cố định scale và có thể đổi giá trị. Cần hai bước kiểm tra theo chính sách rõ:

~~~java
BigDecimal scaled = value.setScale(2, RoundingMode.UNNECESSARY);
if (scaled.precision() > 5) {
    throw new IllegalArgumentException("Gia tri qua gioi han DECIMAL(5,2)");
}
~~~

Đây là **đoạn minh họa**, phải đặt trong phương thức có biến `value` kiểu `BigDecimal`. Với hợp đồng cấm làm tròn, `UNNECESSARY` bảo đảm không đổi giá trị; sau đó `precision() > 5` từ chối các giá trị vượt tổng chữ số của biểu diễn đã chuẩn hóa. Nếu ứng dụng cho phép làm tròn trước lưu, chính sách khác sẽ dùng rounding mode được phê duyệt trước bước kiểm tra precision.

**Cẩn trọng:** mỗi database có quy tắc riêng về giới hạn miền số, xử lý overflow, quy tắc rounding khi ghi, và khả năng hỗ trợ scale âm. Cần đọc schema và kiểm chứng database/driver thực tế. Ví dụ ở đây nhằm diễn đạt hai điều kiện độc lập, không thay thế kiểm thử tích hợp.

### 7.1. Tràn sau khi làm tròn

Một số nằm sát ngưỡng có thể thành số **nhiều chữ số phần nguyên hơn** sau làm tròn. Ví dụ nếu chuẩn hóa scale 2, giá trị `999.995` với `HALF_UP` thành `1000.00`. Giá trị sau làm tròn này không phù hợp với `DECIMAL(5,2)` thông thường, dù giá trị nguồn có thể trông gần giới hạn.

Vì thế kiểm tra precision/miền giá trị **sau khi áp quy tắc scale đã chọn**, không chỉ trước khi làm tròn.

## 8. Kiểm thử đúng hợp đồng: số, scale, precision và chuỗi

Một bộ assertion tốt phân biệt bốn điều kiện:

| Hợp đồng | Kiểm tra gợi ý |
| --- | --- |
| Giá trị toán học bằng nhau | `expected.compareTo(actual) == 0` |
| Giá trị và scale cùng đúng | `expected.equals(actual)` hoặc hai assertion riêng |
| Scale chính xác bằng 2 | `actual.scale() == 2` |
| Precision không vượt 5 | `actual.precision() <= 5` sau bước normalize phù hợp |
| Chuỗi trao đổi đúng dạng `"12.00"` | Test riêng kết quả serialize hoặc format |

Ví dụ JUnit 5, **đặt trong một phương thức test và thêm dependencies JUnit**:

~~~java
BigDecimal actual = new BigDecimal("12.00");

assertEquals(0, new BigDecimal("12").compareTo(actual));
assertEquals(2, actual.scale());
assertTrue(actual.precision() <= 5);
~~~

Các assertion trên dùng `org.junit.jupiter.api.Assertions.assertEquals` và `assertTrue`. Chúng kiểm tra ba yêu cầu **riêng**. `actual.equals(new BigDecimal("12"))` sẽ `false` vì khác scale mặc dù giá trị bằng nhau.

Nếu cần một số không âm có chính xác hai vị trí thập phân, ngoài scale còn có thể phải kiểm tra miền giá trị (ví dụ `signum() >= 0`). Không dùng precision/scale để suy ra tất cả ràng buộc nghiệp vụ.

### 8.1. `stripTrailingZeros` thay đổi precision và scale

~~~java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal compact = raw.stripTrailingZeros();

System.out.println(compact);             // 1E+3
System.out.println(compact.precision()); // 1
System.out.println(compact.scale());     // -3
~~~

`stripTrailingZeros()` loại zero tận cùng mà vẫn giữ **giá trị toán học**. Vì vậy nó thường làm precision giảm và scale giảm; scale có thể **âm**. Nó không phải phương thức đặt “số chữ số sau dấu thập phân” và không nên được dùng để che lỗi scale của một API cam kết `scale == 2`.

Với zero, `stripTrailingZeros()` có thể trả `BigDecimal.ZERO` có scale 0, dù ban đầu là `0.0000`. Nếu kiểm thử yêu cầu giữ scale của zero, phải kiểm tra riêng.

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **PrecisionVsScaleDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionVsScaleDemo {
    private static void inspect(String label, BigDecimal value) {
        System.out.println(label + ": " + value
                + " (precision=" + value.precision()
                + ", scale=" + value.scale() + ")");
    }

    public static void main(String[] args) {
        inspect("literal", new BigDecimal("123.4500"));
        inspect("small", new BigDecimal("0.00120"));
        inspect("zero", new BigDecimal("0.0000"));
        inspect("scientific", new BigDecimal("1E+3"));

        BigDecimal original = new BigDecimal("1234.567");
        MathContext threeDigits =
                new MathContext(3, RoundingMode.HALF_UP);

        inspect("round precision3", original.round(threeDigits));
        inspect("set scale3",
                original.setScale(3, RoundingMode.HALF_UP));

        BigDecimal small = new BigDecimal("0.0012345");
        System.out.println("small precision3: "
                + small.round(threeDigits));
        System.out.println("small scale3: "
                + small.setScale(3, RoundingMode.HALF_UP));

        inspect("carry precision3",
                new BigDecimal("9.995").round(threeDigits));
        inspect("carry scale2",
                new BigDecimal("9.995")
                        .setScale(2, RoundingMode.HALF_UP));

        inspect("round trailing zeros",
                new BigDecimal("1000.00").round(threeDigits));

        BigDecimal a = new BigDecimal("12.0");
        BigDecimal b = new BigDecimal("12.00");
        System.out.println("same numeric value: "
                + (a.compareTo(b) == 0));
        System.out.println("same value and scale: "
                + a.equals(b));

        try {
            new BigDecimal("12.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale: ArithmeticException");
        }
    }
}
~~~

Chạy:

~~~bash
javac PrecisionVsScaleDemo.java
java PrecisionVsScaleDemo
~~~

Đầu ra chính xác:

~~~text
literal: 123.4500 (precision=7, scale=4)
small: 0.00120 (precision=3, scale=5)
zero: 0.0000 (precision=1, scale=4)
scientific: 1E+3 (precision=1, scale=-3)
round precision3: 1.23E+3 (precision=3, scale=-1)
set scale3: 1234.567 (precision=7, scale=3)
small precision3: 0.00123
small scale3: 0.001
carry precision3: 10.0 (precision=3, scale=1)
carry scale2: 10.00 (precision=4, scale=2)
round trailing zeros: 1.00E+3 (precision=3, scale=-1)
same numeric value: true
same value and scale: false
strict scale: ArithmeticException
~~~

Chương trình này chỉ dùng Java standard library. Các dòng `inspect` cho thấy một số 3 trong `MathContext` và một số 3 trong `setScale` tác động đến **hai thuộc tính khác nhau**. Chú ý số `9.995` sau làm tròn có cùng giá trị 10 nhưng biểu diễn `10.0` hoặc `10.00` tùy chính sách.

## 10. Quy tắc lựa chọn đúng API

### Muốn đúng N chữ số có nghĩa

Sử dụng `MathContext`:

~~~java
MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);
BigDecimal rounded = value.round(mc);
~~~

Giới hạn **precision tối đa 4** của kết quả, không ép scale thành 4. Nó thích hợp khi hợp đồng mô tả kết quả theo chữ số có nghĩa, ví dụ báo cáo đo lường hoặc tính toán có giới hạn precision.

### Muốn đúng N chữ số sau dấu thập phân

Sử dụng `setScale`:

~~~java
BigDecimal scaled = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

Kết quả có **scale đúng 2** khi thành công. Nó phù hợp với một số hợp đồng lưu trữ, hiển thị thập phân có scale cố định, hoặc quy tắc tiền tệ đã định nghĩa rõ thời điểm làm tròn.

### Muốn không được thay đổi giá trị

Đặt `UNNECESSARY` trong phép chuẩn hóa hoặc phép toán tương ứng:

~~~java
BigDecimal exactAtTwoPlaces =
        value.setScale(2, RoundingMode.UNNECESSARY);
~~~

Nếu không thể biểu diễn chính xác giá trị ở scale yêu cầu, sẽ có `ArithmeticException`. `UNNECESSARY` không tự bảo đảm miền giá trị hay số chữ số phần nguyên.

### Muốn vừa scale 2 vừa giới hạn tổng chữ số

Chuẩn hóa **theo policy được duyệt**, rồi kiểm tra cả scale lẫn precision/miền giá trị, ví dụ:

~~~java
BigDecimal normalized =
        value.setScale(2, RoundingMode.UNNECESSARY);

if (normalized.precision() > 5) {
    throw new IllegalArgumentException("Precision vuot 5");
}
~~~

Nếu hợp đồng cho phép rounding, thay `UNNECESSARY` bằng mode được phê duyệt và kiểm tra dữ liệu **sau** làm tròn. Không dùng `round(new MathContext(5, ...))` để thay thế hoàn toàn kiểm tra `DECIMAL(5,2)`.

## 11. Những lỗi hay gặp

| Hiểu lầm | Điều đúng |
| --- | --- |
| `MathContext(2)` có nghĩa hai số sau dấu chấm | Precision 2 là hai chữ số có nghĩa trên toàn bộ kết quả |
| `precision()` đếm chữ số sau dấu chấm | Nó đếm chữ số trong unscaled value, bỏ dấu; zero có precision 1 |
| `scale()` luôn không âm | Scale có thể âm, chẳng hạn `1E+3` có scale -3 |
| `0.00120` có precision 5 | Precision là 3, còn scale là 5 |
| Rounding chỉ thay phần thập phân | `MathContext` có thể làm tròn cả chữ số phần nguyên và đổi dạng sang ký pháp mũ |
| `setScale` luôn chỉ thêm số 0 | Khi giảm scale, nó có thể đổi giá trị theo mode hoặc ném lỗi |
| `UNNECESSARY` nghĩa là bỏ qua rounding | Nó từ chối thao tác phải thay đổi giá trị |
| `BigDecimal.toString()` luôn in dấu chấm thông thường | Có thể in dạng mũ, tùy scale và cách biểu diễn |
| Bằng giá trị số thì bằng scale | `compareTo == 0` không bảo đảm `equals == true` |
| `DECIMAL(5,2)` chỉ cần `MathContext(5)` | Phải kiểm tra cả scale, precision và giới hạn của DB |
| `stripTrailingZeros()` đặt scale thành 0 | Nó có thể tạo scale âm và thay đổi biểu diễn của zero |

## 12. Tự kiểm tra

1. `new BigDecimal("123.4500").precision()` là bao nhiêu? **7**; scale là **4**.
2. `new BigDecimal("0.00120")` có precision 5 vì có 5 chữ số sau dấu chấm không? **Không**; precision là **3**, scale là **5**.
3. Với `1234.567`, `MathContext(3, HALF_UP)` và `setScale(3, HALF_UP)` lần lượt trả gì? **`1.23E+3`** và **`1234.567`**.
4. Vì sao `new BigDecimal("1E+3").scale()` bằng -3? **Giá trị = 1 × 10^3**, theo công thức scale là -3.
5. `new BigDecimal("12").setScale(2)` có thay giá trị số không? **Không**; nó trở thành `12.00` với scale 2.
6. `new BigDecimal("12.345").setScale(2, UNNECESSARY)` có thành công không? **Không**; phải bỏ chữ số 5, nên ném `ArithmeticException`.
7. Vì sao `9.995` có thể thành `10.0` với precision 3, còn thành `10.00` với scale 2? **Hai ràng buộc biểu diễn khác nhau dù giá trị sau làm tròn bằng nhau**.
8. Nếu API yêu cầu scale đúng 2 và giá trị chính xác, chỉ `MathContext(2)` có đủ không? **Không**; phải dùng `setScale(2, UNNECESSARY)` hoặc kiểm tra tương đương, cùng các ràng buộc còn lại.
9. Khi hai `BigDecimal` có giá trị bằng nhau nhưng scale khác nhau, nên kiểm tra bằng gì? **`compareTo == 0`** nếu hợp đồng chỉ xét giá trị; **`equals`** hoặc kiểm tra riêng scale nếu hợp đồng yêu cầu cả hai.

**Ghi nhớ cuối cùng:** **Precision = số chữ số có nghĩa; scale = vị trí dấu thập phân trong biểu diễn.** Dùng `MathContext` khi cần giới hạn precision của phép toán, dùng `setScale` khi cần đúng số chữ số sau dấu thập phân, và kiểm tra cả hai khi hợp đồng dữ liệu yêu cầu.