# `BigDecimal.floatValue()`, `doubleValue()`: chuyển đổi, làm tròn và vô cực

## 1. Ý nghĩa của phép chuyển sang số thực nhị phân

`BigDecimal` biểu diễn chính xác một giá trị thập phân có số chữ số hữu hạn thông qua unscaled value và scale; còn `float` và `double` là hai kiểu số thực dấu phẩy động nhị phân IEEE 754. Hai phương thức:

~~~java
BigDecimal amount = new BigDecimal("12.5");
float f = amount.floatValue();
double d = amount.doubleValue();
~~~

trả về giá trị số nguyên thủy tương ứng. Đây là **chuyển giá trị số**, không phải định dạng chuỗi và cũng không phải phép tính với `MathContext`.

Dữ liệu `BigDecimal` hợp lệ có thể gặp bốn tình huống khi chuyển kiểu:

1. **Chuyển chính xác:** số như `0.5`, `12.5` hoặc số nguyên nhỏ biểu diễn được đúng bằng nhị phân.
2. **Bị làm tròn:** số như `0.1` không có biểu diễn nhị phân hữu hạn đúng tuyệt đối.
3. **Overflow:** độ lớn quá lớn, kết quả trở thành `Infinity` hoặc `-Infinity`.
4. **Underflow:** số có độ lớn cực nhỏ được làm tròn thành số *subnormal*, `0.0` hoặc `-0.0`.

Hai phương thức cho phép mất độ chính xác hoặc tạo vô cực. **Chúng không tự ném `ArithmeticException` chỉ vì cần làm tròn hay tràn phạm vi.** Điều này khác những phép tính `BigDecimal` có ràng buộc làm tròn tường minh.

## 2. Độ chính xác và phạm vi khác nhau như thế nào?

| Đặc tính | `BigDecimal` | `float` | `double` |
| --- | --- | --- | --- |
| Biểu diễn | Unscaled integer × 10^(-scale) | IEEE 754 binary32 | IEEE 754 binary64 |
| Độ chính xác số có nghĩa | Theo giá trị và bộ nhớ | 24 bit nhị phân | 53 bit nhị phân |
| Số chữ số thập phân có nghĩa xấp xỉ | Không cố định | 6–9 | 15–17 |
| Có `NaN` và `Infinity` | Không | Có | Có |
| Phân biệt số không âm dấu | Không | Có | Có |
| Biểu diễn đúng `0.1` thập phân | Có | Không | Không |

`float` có miền giá trị hữu hạn đến khoảng `3.4028235E38`, còn `double` đến khoảng `1.7976931348623157E308`. Phạm vi rộng hơn không đồng nghĩa chính xác hơn vô hạn: `double` vẫn chỉ có 53 bit có nghĩa.

Cơ chế chính: phép chuyển đưa giá trị thập phân vào tập các giá trị nhị phân biểu diễn được, lựa chọn kết quả theo quy tắc làm tròn nhị phân đến gần nhất, nếu đúng giữa thì chọn giá trị có bit thấp nhất của significand là chẵn (*ties to even*). Khoảng cách giữa hai số có thể biểu diễn tăng dần theo độ lớn của chúng.

### 2.1. Khi `0.1` được in ra vẫn là `0.1`

~~~java
BigDecimal decimal = new BigDecimal("0.1");
double binary = decimal.doubleValue();
System.out.println(binary); // 0.1
~~~

Đầu ra `0.1` **không chứng minh phép chuyển bảo toàn giá trị**. `Double.toString` trả về biểu diễn thập phân ngắn đọc lại được cùng giá trị `double`. Giá trị nhị phân thực sự của `binary`, khi được chuyển chính xác về `BigDecimal`, là:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

Có thể quan sát bằng:

~~~java
double binary = new BigDecimal("0.1").doubleValue();
System.out.println(new BigDecimal(binary).toPlainString());
~~~

`new BigDecimal("0.1")` là số thập phân 0.1 đúng theo văn bản. `new BigDecimal(binary)` lại mô tả **giá trị nhị phân đã lưu** trong biến `double`; hai đối tượng này không có cùng giá trị toán học. Vì thế cần tách bạch **chuỗi in ra** và **độ chính xác số**.

## 3. Làm tròn khi chuyển sang `float` hoặc `double`

### 3.1. Ví dụ với `float`: mất một đơn vị ở số nguyên lớn

~~~java
BigDecimal n = new BigDecimal("16777217");
float f = n.floatValue();
double d = n.doubleValue();

System.out.println(f); // 1.6777216E7 = 16777216
System.out.println(d); // 1.6777217E7 = 16777217
~~~

`16_777_216 = 2^24` là mốc quan trọng: `float` còn biểu diễn chính xác số đó, nhưng không biểu diễn được mọi số nguyên kế tiếp. Giá trị `16_777_217` nằm giữa hai số `float` kề nhau `16_777_216` và `16_777_218`. Quy tắc chọn kết quả khi đúng giữa làm nó thành `16_777_216`.

`double` có độ chính xác cao hơn nên vẫn chứa được đúng `16_777_217`. Điều này **không có nghĩa mọi số nguyên đều chính xác trong `double`**.

### 3.2. Ví dụ với `double`: vượt giới hạn nguyên liên tiếp

~~~java
BigDecimal n = new BigDecimal("9007199254740993");
System.out.println(n.doubleValue());
// 9.007199254740992E15 = 9007199254740992
~~~

`9_007_199_254_740_992 = 2^53` là mốc tương ứng cho `double`. Số `2^53 + 1` không biểu diễn được đúng; sau chuyển đổi, giá trị giảm một đơn vị.

### 3.3. Không chỉ số nguyên mới chịu ảnh hưởng

Một số thập phân hữu hạn như `0.1` thường có phần thập phân nhị phân lặp vô hạn. Do đó ngay ở khoảng giá trị rất nhỏ và chưa gần overflow, quá trình chuyển vẫn có thể làm tròn.

Cần phân biệt hai loại giới hạn:

- **Giới hạn độ chính xác:** giá trị vẫn hữu hạn nhưng khác nguồn một chút do bị làm tròn.
- **Giới hạn miền giá trị:** kết quả có thể thành vô cực hoặc zero/subnormal.

Nếu cần giữ chính xác chữ số thập phân trong tính tiền, thuế, lãi suất theo quy định hoặc số liệu kế toán, nên giữ `BigDecimal` trong luồng tính toán.

## 4. Overflow: một `BigDecimal` hữu hạn có thể thành vô cực

Với giá trị lớn hơn độ lớn hữu hạn mà kiểu đích có thể biểu diễn, `floatValue()` và `doubleValue()` có thể cho `Infinity` hoặc `-Infinity`:

~~~java
BigDecimal big = new BigDecimal("1E39");

System.out.println(big.floatValue());  // Infinity
System.out.println(big.doubleValue()); // 1.0E39

BigDecimal huge = new BigDecimal("1E309");
System.out.println(huge.doubleValue()); // Infinity

BigDecimal negativeHuge = new BigDecimal("-1E309");
System.out.println(negativeHuge.doubleValue()); // -Infinity
~~~

`1E39` đã vượt phạm vi hữu hạn của `float` nhưng vẫn nằm trong phạm vi `double`. `1E309` vượt cả phạm vi của `double`. Đây là **tràn số khi chuyển kiểu**, không phải việc `BigDecimal` tự chứa vô cực.

`BigDecimal` không có giá trị `NaN` hay vô cực. Các phép `new BigDecimal("Infinity")`, `new BigDecimal(Double.POSITIVE_INFINITY)` và `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` đều không xây dựng được đối tượng `BigDecimal` hợp lệ, mà ném `NumberFormatException`.

Khi API đích cấm số không hữu hạn, phải kiểm tra **sau chuyển đổi**:

~~~java
double converted = input.doubleValue();
if (!Double.isFinite(converted)) {
    throw new ArithmeticException("Gia tri khong vua pham vi double huu han");
}
~~~

Đây là đoạn mã phương thức, giả sử `input` có kiểu `BigDecimal`. `Double.isFinite` từ chối cả `Infinity`, `-Infinity` và `NaN`; phép chuyển một `BigDecimal` hợp lệ sang `double` không tự tạo `NaN`, nhưng kiểm tra này hữu ích tại ranh giới hệ thống.

**Quan trọng:** `isFinite` chỉ bảo đảm kết quả hữu hạn; nó không phát hiện việc `0.1` hay số nguyên lớn bị làm tròn thành một giá trị hữu hạn khác.

## 5. Underflow: số subnormal và kết quả `0.0`/`-0.0`

Ngoài vùng *normal*, IEEE 754 còn có vùng *subnormal* giúp biểu diễn các giá trị dương khác 0 nhỏ hơn normal dương nhỏ nhất. Nếu độ lớn nguồn còn nhỏ hơn khả năng biểu diễn sau khi làm tròn, kết quả thành số không.

| Hằng số | Ý nghĩa |
| --- | --- |
| `Float.MIN_NORMAL` | Số `float` normal dương nhỏ nhất, khoảng `1.17549435E-38` |
| `Float.MIN_VALUE` | Số `float` dương khác 0 nhỏ nhất, subnormal, khoảng `1.4E-45` |
| `Double.MIN_NORMAL` | Số `double` normal dương nhỏ nhất, khoảng `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Số `double` dương khác 0 nhỏ nhất, subnormal, khoảng `4.9E-324` |

Lưu ý `MIN_VALUE` **không phải số âm nhỏ nhất**. Trong các kiểu `float`/`double`, đó là số dương khác 0 có độ lớn nhỏ nhất.

~~~java
System.out.println(new BigDecimal("1E-50").doubleValue()); // 1.0E-50
System.out.println(new BigDecimal("1E-50").floatValue());  // 0.0

System.out.println(new BigDecimal("5E-324").doubleValue()); // 4.9E-324
System.out.println(new BigDecimal("1E-400").doubleValue()); // 0.0
System.out.println(new BigDecimal("-1E-400").doubleValue()); // -0.0
~~~

`5E-324` làm tròn về `Double.MIN_VALUE`, còn `1E-400` thành `0.0`. Với `-1E-400`, kết quả là **zero có bit dấu âm**, in ra `-0.0`. Hai giá trị `0.0` và `-0.0` so sánh `==` cho `true`, nhưng bit dấu khác nhau.

~~~java
double zero = new BigDecimal("-1E-400").doubleValue();
boolean negativeZero =
        Double.doubleToRawLongBits(zero) == Long.MIN_VALUE;
System.out.println(negativeZero); // true
~~~

Chính `BigDecimal` không phân biệt zero âm và zero dương theo bit dấu như IEEE 754. Vì vậy đừng mong một vòng chuyển đổi qua `BigDecimal` bảo toàn biểu diễn bit `-0.0` khi giá trị toán học bằng 0.

**Underflow không nhất thiết tạo exception.** Nó có thể là lỗi nghiệp vụ nghiêm trọng nếu số rất nhỏ khác 0 bị hiểu như bằng 0 (ví dụ xác suất, hệ số đo lường hoặc thuật toán chia tỷ lệ).

## 6. Ví dụ độc lập chạy với Java 17+

Lưu đoạn sau thành tệp **BigDecimalFloatingConversionDemo.java**:

~~~java
import java.math.BigDecimal;

public class BigDecimalFloatingConversionDemo {
    private static void show(String text) {
        BigDecimal decimal = new BigDecimal(text);
        System.out.println(text
                + " -> double=" + decimal.doubleValue()
                + ", float=" + decimal.floatValue());
    }

    private static boolean exactAsDouble(BigDecimal original) {
        double converted = original.doubleValue();
        return Double.isFinite(converted)
                && original.compareTo(new BigDecimal(converted)) == 0;
    }

    private static boolean exactAsFloat(BigDecimal original) {
        float converted = original.floatValue();
        return Float.isFinite(converted)
                && original.compareTo(
                        new BigDecimal((double) converted)) == 0;
    }

    public static void main(String[] args) {
        show("0.1");
        show("16777217");
        show("1E39");
        show("1E309");
        show("1E-50");
        show("-1E-400");
        show("5E-324");

        double value = new BigDecimal("0.1").doubleValue();
        System.out.println("exact binary double decimal: "
                + new BigDecimal(value).toPlainString());
        System.out.println("shortest roundtrip decimal: "
                + BigDecimal.valueOf(value).toPlainString());

        System.out.println("0.1 exact double? "
                + exactAsDouble(new BigDecimal("0.1")));
        System.out.println("0.5 exact double? "
                + exactAsDouble(new BigDecimal("0.5")));
        System.out.println("16777217 exact float? "
                + exactAsFloat(new BigDecimal("16777217")));
        System.out.println("16777216 exact float? "
                + exactAsFloat(new BigDecimal("16777216")));

        double tinyNegative = new BigDecimal("-1E-400").doubleValue();
        System.out.println("negative zero bits? "
                + (Double.doubleToRawLongBits(tinyNegative)
                        == Long.MIN_VALUE));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalFloatingConversionDemo.java
java BigDecimalFloatingConversionDemo
~~~

Kết quả chính xác:

~~~text
0.1 -> double=0.1, float=0.1
16777217 -> double=1.6777217E7, float=1.6777216E7
1E39 -> double=1.0E39, float=Infinity
1E309 -> double=Infinity, float=Infinity
1E-50 -> double=1.0E-50, float=0.0
-1E-400 -> double=-0.0, float=-0.0
5E-324 -> double=4.9E-324, float=0.0
exact binary double decimal: 0.1000000000000000055511151231257827021181583404541015625
shortest roundtrip decimal: 0.1
0.1 exact double? false
0.5 exact double? true
16777217 exact float? false
16777216 exact float? true
negative zero bits? true
~~~

Trong chương trình, `show` in đồng thời kết quả hai kiểu cho cùng một `BigDecimal`. Các hàm `exactAsDouble` và `exactAsFloat` thực hiện bước kiểm tra tiếp theo: thay vì chỉ nhìn giá trị in ra, chúng đối chiếu **giá trị nhị phân thực sự** với `BigDecimal` nguồn.

## 7. Kiểm tra phép chuyển có chính xác hay không

Phương thức `exactAsDouble` trong ví dụ áp dụng các bước:

1. Gọi `doubleValue()`.
2. Kiểm tra `Double.isFinite` để từ chối vô cực (và NaN nếu kiểu nguồn là số thực khác).
3. Dùng `new BigDecimal(converted)` để tái hiện chính xác giá trị nhị phân hữu hạn dưới dạng thập phân.
4. So sánh `compareTo` với `BigDecimal` ban đầu. Nếu bằng 0, giá trị toán học được bảo toàn.

Với `float`, chuyển `float` kết quả thành `double` trước khi truyền vào constructor `BigDecimal` là hợp lý: mọi `float` hữu hạn đều được `double` biểu diễn chính xác. Việc mở rộng kiểu ở đây không làm mất thêm dữ liệu, nhưng **cũng không phục hồi chữ số đã mất lúc chuyển từ `BigDecimal` sang `float`**.

Các hàm này kiểm tra **tính chính xác của giá trị**, không phải bảo toàn `scale`, các số 0 tận cùng hay văn bản đầu vào. `BigDecimal("12.500")` và `BigDecimal("12.5")` bằng nhau theo `compareTo`, dù khác scale và khác `equals`.

### 7.1. Tại sao không dùng `BigDecimal.valueOf(double)` để kiểm tra?

~~~java
BigDecimal source = new BigDecimal("0.1");
double d = source.doubleValue();

System.out.println(source.compareTo(BigDecimal.valueOf(d))); // 0
System.out.println(source.compareTo(new BigDecimal(d)));      // -1
~~~

Hai kết quả khác nhau vì:

- `BigDecimal.valueOf(d)` dựa trên dạng thập phân ngắn `Double.toString(d)`, thường là dạng giúp round-trip về cùng giá trị `double` (ở đây là `0.1`).
- `new BigDecimal(d)` giữ chính xác giá trị nhị phân thực tế của `double` thành một thập phân đầy đủ.

Giá trị `double` tương ứng `0.1` hơi **lớn hơn** 0.1 thập phân chính xác, do đó `source.compareTo(new BigDecimal(d))` trả `-1`. **So sánh với `valueOf` có thể cho kết quả “bằng nhau” giả tạo nếu mục tiêu là phát hiện mọi sai số chuyển kiểu.**

Không gọi `new BigDecimal(Double.POSITIVE_INFINITY)`: constructor đó chỉ nhận giá trị hữu hạn; phải kiểm tra `isFinite` trước.

### 7.2. Hàm chuyển chỉ nhận giá trị `double` chính xác

~~~java
public static double requireExactDouble(BigDecimal input) {
    double value = input.doubleValue();
    if (!Double.isFinite(value)
            || input.compareTo(new BigDecimal(value)) != 0) {
        throw new ArithmeticException("Mat do chinh xac khi chuyen double");
    }
    return value;
}
~~~

Đây là **phương thức minh họa để đặt trong một class đã import `java.math.BigDecimal`**, không phải chương trình độc lập. Nó chấp nhận `0.5` và từ chối `0.1`, số vượt phạm vi hoặc số cực nhỏ bị làm tròn về 0.

Nếu dữ liệu có thể là `null`, phải quy định cách xử lý trước khi gọi `input.doubleValue()`; nếu không sẽ ném `NullPointerException`.

Trong `BigDecimal` không có phương thức chuẩn `doubleValueExact()` hoặc `floatValueExact()` giống như `intValueExact()` và `longValueExact()`. Nếu ứng dụng yêu cầu chuyển số thực nhị phân **mà không được mất độ chính xác**, cần kiểm tra thủ công hoặc thiết kế giao diện tiếp nhận `BigDecimal`.

## 8. Chọn chính sách chuyển kiểu theo bài toán

| Yêu cầu nghiệp vụ | Cách tiếp cận |
| --- | --- |
| Chấp nhận xấp xỉ trong tính toán | Dùng `doubleValue()` hoặc `floatValue()` khi đã hiểu sai số |
| Kết quả phải hữu hạn | Sau chuyển, kiểm tra `Double.isFinite`/`Float.isFinite` |
| Bắt buộc giữ nguyên giá trị toán học | Kiểm tra `isFinite` rồi đối chiếu với `new BigDecimal(converted)` |
| Bắt buộc giữ scale/chữ số gốc | Tiếp tục dùng `BigDecimal`; xác minh scale và định dạng riêng |
| Dùng tiền hoặc số thập phân cần chính xác | Tính toán bằng `BigDecimal` xuyên suốt, chỉ chuyển ở ranh giới API thực sự cần |
| Phát hiện underflow từ số khác 0 thành zero | So sánh giá trị nguồn với giá trị đã chuyển; kiểm tra zero khi cần thông báo đặc thù |

**Không nhầm `RoundingMode.UNNECESSARY` với kiểm tra chuyển `double`.** Ví dụ:

~~~java
BigDecimal x = new BigDecimal("0.10")
        .setScale(2, java.math.RoundingMode.UNNECESSARY);
double d = x.doubleValue();
~~~

`setScale(2, UNNECESSARY)` thành công vì số thập phân đó có thể biểu diễn ở scale 2 mà không đổi giá trị. Nhưng `d` vẫn là phép xấp xỉ nhị phân của 0.1. Đây là hai điều kiện chính xác **khác hệ cơ số**.

## 9. Lỗi phổ biến

| Dấu hiệu hoặc hiểu lầm | Thực tế |
| --- | --- |
| In `0.1` nên chắc chắn đã giữ đúng số thập phân `0.1` | `Double.toString` trả dạng ngắn; xem `new BigDecimal(double)` để biết giá trị nhị phân |
| Dùng `double` thì số nguyên nào cũng chính xác | Với số nguyên rất lớn, khoảng cách giữa các giá trị `double` vượt 1 |
| Chuyển số `BigDecimal` hữu hạn không thể ra `Infinity` | Overflow có thể cho `Infinity` hoặc `-Infinity` mà không báo lỗi |
| Underflow chỉ có thể là số 0 dương | Giá trị âm đủ nhỏ có thể thành `-0.0` |
| `Float.MIN_VALUE` là số âm cực tiểu | Đây là số **dương khác 0 nhỏ nhất**, thuộc vùng subnormal |
| `Double.isFinite` xác nhận độ chính xác | Nó chỉ loại bỏ các giá trị không hữu hạn |
| `BigDecimal.valueOf(double)` luôn tái hiện mọi chữ số nhị phân của `double` | Nó dùng biểu diễn thập phân ngắn; constructor nhận `double` cho biểu diễn chính xác |
| Mở rộng `float` đã bị làm tròn sang `double` sẽ phục hồi chữ số | Các chữ số đã mất không thể khôi phục bằng ép kiểu |
| Không có exception thì chuyển đổi không mất thông tin | Precision loss, overflow và underflow có thể xảy ra trong phép chuyển thành công |

## 10. Tự kiểm tra

1. `new BigDecimal("0.5").doubleValue()` có chính xác không? **Có:** `0.5 = 1/2` biểu diễn đúng bằng nhị phân.
2. `new BigDecimal("0.1").doubleValue()` có đúng chính xác số thập phân 0.1 không? **Không:** giá trị nhị phân gần nhất chỉ là xấp xỉ.
3. `new BigDecimal("16777217").floatValue()` cho giá trị bao nhiêu? **16_777_216**, vì giới hạn precision 24 bit và quy tắc làm tròn.
4. `new BigDecimal("1E39").floatValue()` và `doubleValue()` có như nhau không? **Không:** kết quả lần lượt là `Infinity` và `1.0E39`.
5. `new BigDecimal("1E-50").floatValue()` trả về gì? **`0.0`**, còn `doubleValue()` vẫn là `1.0E-50`.
6. Khi giá trị trả về là `0.0`, có thể kết luận `BigDecimal` nguồn bằng 0 không? **Không:** giá trị khác 0 có thể underflow về zero.
7. `Double.isFinite` có kiểm tra chuyển đúng đến từng chữ số không? **Không:** nó chỉ kiểm tra kết quả hữu hạn.
8. Muốn xác minh phép chuyển sang `double` bảo toàn giá trị, so sánh với đối tượng nào? **`new BigDecimal(result)`**, với `result` hữu hạn; không chỉ so với `BigDecimal.valueOf(result)`.

**Kết luận:** `floatValue()` và `doubleValue()` là các phép chuyển sang số dấu phẩy động nhị phân có thể **làm tròn, overflow thành vô cực hoặc underflow về subnormal/zero**. Chọn kiểu theo hợp đồng dữ liệu, kiểm tra `isFinite` khi cần, và đối chiếu **giá trị nhị phân thực sự** nếu việc giữ nguyên giá trị là bắt buộc.