# `BigDecimal.pow()` và `BigDecimal.sqrt()` theo precision yêu cầu

## 1. Mục tiêu bài học

Khi làm việc với số thập phân cần kiểm soát chữ số có nghĩa, Java cung cấp `BigDecimal` cùng `MathContext`. Hai phép toán chính của bài này là lũy thừa nguyên `pow(int, MathContext)` và căn bậc hai `sqrt(MathContext)`. Cần hiểu rõ khi nào kết quả chính xác, khi nào kết quả được làm tròn, cách chọn precision phù hợp và những trường hợp API từ chối phép tính.

Các lời gọi quan trọng:

```java
BigDecimal power = base.pow(exponent, context);
BigDecimal root = value.sqrt(context);
```

`BigDecimal` có thể lưu số thập phân với độ chính xác tùy ý, nhưng căn của 2 hoặc nghịch đảo của 3 không thể được biểu diễn chính xác bằng một chuỗi chữ số thập phân hữu hạn. Vì thế, lựa chọn precision và quy tắc làm tròn là một phần của yêu cầu tính toán, không chỉ là tùy chọn hiển thị.

## 2. Phân biệt precision và scale

`BigDecimal` biểu diễn giá trị `unscaledValue × 10^(-scale)`:

- **`precision`**: số chữ số có nghĩa của giá trị thập phân, đếm từ chữ số khác 0 đầu tiên. Precision trong `MathContext` đặt giới hạn số chữ số có nghĩa *của kết quả phép toán*.
- **`scale`**: số chữ số ở bên phải dấu thập phân trong cách biểu diễn khi scale không âm; scale cũng có thể âm. `12.3400` có `precision() == 6` và `scale() == 4`.
- **`RoundingMode`**: quy tắc xử lý phần chữ số bỏ đi. `HALF_EVEN` làm tròn đến giá trị gần nhất và chọn chữ số cuối chẵn khi đúng chính giữa; `HALF_UP` làm tròn về phía xa 0 ở điểm giữa; `UNNECESSARY` yêu cầu kết quả không phải làm tròn.
- **`MathContext`**: chứa precision và rounding mode. `new MathContext(8, RoundingMode.HALF_EVEN)` có nghĩa là *8 chữ số có nghĩa*, không có nghĩa là *8 chữ số sau dấu phẩy*.

Ví dụ độc lập trong một phương thức Java đã import `java.math.*`:

```java
BigDecimal value = new BigDecimal("12345.678");
MathContext mc4 = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(value.round(mc4).toPlainString()); // 12350
System.out.println(value.setScale(4, RoundingMode.HALF_EVEN)
        .toPlainString());                              // 12345.6780
```

Lệnh thứ nhất làm tròn còn 4 chữ số có nghĩa; lệnh thứ hai đặt đúng 4 chữ số sau dấu thập phân. Việc thêm các chữ số 0 cuối có thể tăng `precision()` của đối tượng nhưng không tăng độ chính xác số học đã được tính.

Khởi tạo từ chuỗi như `new BigDecimal("0.1")` để giữ giá trị thập phân mong muốn. `new BigDecimal(0.1)` giữ chính xác giá trị `double` nhị phân đã xấp xỉ trước đó. Nếu giá trị nguồn đã là `double`, `BigDecimal.valueOf(double)` thường phù hợp hơn constructor nhận `double`, nhưng không thể khôi phục chữ số vốn đã mất tại nguồn.

## 3. Tính `pow`: số mũ nguyên

### 3.1. `pow(int n)` trả về kết quả chính xác

```java
BigDecimal exact = new BigDecimal("1.2345").pow(3);
// 1.881365963625
```

Theo Java 17, `pow(n)` nhận số mũ nguyên từ **0 đến 999_999_999**, và trả kết quả chính xác không giới hạn precision. API xác định `BigDecimal.ZERO.pow(0)` trả về `BigDecimal.ONE`. Dù một số mũ nằm trong phạm vi hợp lệ, phép tính có thể sinh ra kết quả khổng lồ và tốn bộ nhớ/thời gian; không dùng cách này tùy tiện cho số mũ lớn.

`pow` không có overload nhận `BigDecimal` làm số mũ phân số. Viết `pow(1 / 2)` là sai khi muốn lấy căn, vì `1 / 2` trong Java là phép chia nguyên, nhận giá trị `0`. Dùng `sqrt(mc)` cho căn bậc hai.

### 3.2. `pow(int n, MathContext mc)` trả về kết quả theo precision

```java
MathContext mc6 = new MathContext(6, RoundingMode.HALF_EVEN);
BigDecimal rounded = new BigDecimal("1.2345").pow(3, mc6);
// 1.88137: sáu chữ số có nghĩa
```

Khi precision của `mc` **dương**, overload này còn cho phép **số mũ nguyên âm**: `new BigDecimal("2").pow(-3, mc6)` nhận giá trị `0.125`. Số mũ âm biểu diễn nghịch đảo của lũy thừa dương và có thể cần làm tròn. Cơ số `0` với số mũ âm không hợp lệ.

Ràng buộc từ hợp đồng `BigDecimal` Java 17:

| Trường hợp | Kết quả |
| --- | --- |
| `x.pow(0)` hoặc `x.pow(0, mc)` | Bằng `1`, kể cả khi `x` bằng `0`. |
| `x.pow(n)` với `n < 0` | Ném `ArithmeticException`. |
| `x.pow(n, mc)` với `n < 0` và `mc.precision > 0` | Tính nghịch đảo theo precision; cơ số phải khác `0`. |
| `abs(n) > 999_999_999` | Ném `ArithmeticException`. |
| `mc.precision == 0` và `n < 0` | Ném `ArithmeticException`. |
| `mc.precision > 0` nhưng số chữ số thập phân của `abs(n)` lớn hơn precision | Ném `ArithmeticException`, ví dụ `pow(123, new MathContext(2))`. |
| Cần làm tròn nhưng mode là `UNNECESSARY` | Ném `ArithmeticException`. |

**Độ chính xác của thuật toán:** `pow(n, mc)` dùng thuật toán lũy thừa nội bộ có chữ số làm việc bổ sung. Java 17 mô tả kết quả nói chung nằm trong khoảng **hai ulp** của giá trị chính xác theo precision đã chọn (`ulp` là đơn vị ở vị trí chữ số cuối). Không được khẳng định `pow(n, mc)` luôn bằng từng chữ số với `pow(n).round(mc)` trong mọi trường hợp. Khi bắt buộc phải đạt kết quả của việc làm tròn *một lần* trên giá trị chính xác và số mũ đủ nhỏ, có thể tính `pow(n)` rồi `round(mc)`, chấp nhận chi phí bộ nhớ/thời gian lớn hơn.

Nếu kết quả `pow` sẽ tiếp tục tham gia các phép toán khác, cân nhắc tính bằng precision trung gian cao hơn precision đầu ra. Rounding sau mỗi bước có thể làm mất chữ số quan trọng, nhất là khi lấy hiệu của hai giá trị gần nhau.

## 4. Tính `sqrt(MathContext)` theo precision

`BigDecimal.sqrt(MathContext)` có từ **Java 9**, vì vậy dùng được trong Java 17+.

```java
MathContext mc8 = new MathContext(8, RoundingMode.HALF_EVEN);
BigDecimal root = new BigDecimal("2").sqrt(mc8);
// 1.4142136: tám chữ số có nghĩa
```

Lưu ý các tình huống:

1. **Đầu vào âm:** `new BigDecimal("-4").sqrt(mc8)` ném `ArithmeticException`. `BigDecimal` không trả về `NaN`.
2. **Căn chính xác:** `new BigDecimal("9").sqrt(mc8)` trả về giá trị `3`. Kết quả chính xác có thể sử dụng ít chữ số có nghĩa hơn precision được cấp.
3. **Căn vô tỉ:** căn của `2` có khai triển thập phân vô hạn. Muốn kết quả hữu hạn, truyền `MathContext` có precision dương và rounding mode phù hợp.
4. **`MathContext.UNLIMITED`:** precision bằng `0` yêu cầu kết quả chính xác. `sqrt(4)` hợp lệ nhưng `sqrt(2)` ném `ArithmeticException`, vì không có biểu diễn thập phân hữu hạn chính xác.
5. **`RoundingMode.UNNECESSARY`:** yêu cầu kết quả chính xác trong precision cho phép; sẽ ném `ArithmeticException` nếu cần làm tròn.
6. **Preferred scale:** scale ưu tiên của căn là `value.scale() / 2` (chia nguyên). Scale thực tế có thể khác do quy tắc biểu diễn/làm tròn. Không coi scale là precision, và không kỳ vọng số 0 cuối luôn được giữ.

Theo đặc tả Java 17, kết quả của `sqrt(mc)` nằm trong một `ulp` so với căn chính xác ở precision đó; với `HALF_UP`, `HALF_DOWN` hoặc `HALF_EVEN`, sai số nằm trong **nửa ulp**. Đây là tính chất của phép tính theo chữ số có nghĩa, khác với yêu cầu số chữ số sau dấu thập phân.

**Tránh chuyển qua `double`:**

```java
// Không tương đương với sqrt(mc) có chính sách thập phân:
BigDecimal unsafe = new BigDecimal(Math.sqrt(2.0));
```

`Math.sqrt` dùng `double` với số bit hữu hạn. Chuyển qua `double` có thể mất thông tin, tràn hoặc làm tròn theo chính sách khác với `MathContext`; nếu yêu cầu là số học thập phân có kiểm soát, giữ toàn bộ phép tính bằng `BigDecimal`.

## 5. Chương trình Java 17+ hoàn chỉnh, biên dịch và chạy

Lưu file **`PrecisionPowSqrtDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionPowSqrtDemo {
    public static void main(String[] args) {
        BigDecimal base = new BigDecimal("1.2345");
        MathContext mc6 = new MathContext(6, RoundingMode.HALF_EVEN);
        MathContext mc8 = new MathContext(8, RoundingMode.HALF_EVEN);

        System.out.println("pow exact = "
                + base.pow(3).toPlainString());
        System.out.println("pow precision 6 = "
                + base.pow(3, mc6).toPlainString());
        System.out.println("sqrt(2) precision 8 = "
                + new BigDecimal("2").sqrt(mc8).toPlainString());
        System.out.println("2^-3 precision 8 = "
                + new BigDecimal("2").pow(-3, mc8).toPlainString());
        System.out.println("sqrt(9) precision 8 = "
                + new BigDecimal("9").sqrt(mc8).toPlainString());
    }
}
```

Chạy tại thư mục chứa file, với JDK 17 trở lên:

```bash
javac PrecisionPowSqrtDemo.java
java PrecisionPowSqrtDemo
```

Stdout:

```text
pow exact = 1.881365963625
pow precision 6 = 1.88137
sqrt(2) precision 8 = 1.4142136
2^-3 precision 8 = 0.125
sqrt(9) precision 8 = 3
```

`toPlainString()` chỉ định dạng chuỗi thay vì dạng ký hiệu khoa học khi có thể; nó không sửa giá trị, làm tròn lại hay tăng precision. Các kết quả trên dùng đầu vào dạng chuỗi để không mang sai số nhị phân của `double`.

## 6. Yêu cầu số chữ số sau dấu thập phân: khi nào dùng `setScale`

Nếu yêu cầu là **6 chữ số có nghĩa**, truyền `MathContext(6, ...)`. Nếu yêu cầu là **6 chữ số sau dấu thập phân**, cần tính với precision làm việc đủ cao, rồi chuyển kết quả sang scale 6:

```java
// Đặt trong main; import java.math.* ở đầu file.
int decimalPlaces = 6;
MathContext work = new MathContext(20, RoundingMode.HALF_EVEN);
BigDecimal unformatted = new BigDecimal("2").sqrt(work);
BigDecimal display = unformatted.setScale(decimalPlaces, RoundingMode.HALF_EVEN);
System.out.println(display.toPlainString()); // 1.414214
```

Với ví dụ căn của 2, precision 20 cung cấp dư chữ số cần thiết để in 6 chữ số thập phân. **Không có công thức chung “precision = số chữ số thập phân + 2” cho mọi giá trị**: kết quả rất lớn/nhỏ, phép tính phức tạp và các giá trị sát ngưỡng làm tròn cần được đánh giá riêng.

Làm tròn hai lần (*double rounding*) có thể dẫn đến kết quả cuối không trùng với việc làm tròn trực tiếp giá trị toán học chính xác. Nếu nghiệp vụ đòi kết quả đúng tới N chữ số thập phân, cần xác định ngân sách sai số, tăng precision làm việc phù hợp và kiểm chứng các tình huống sát ngưỡng. Với tài chính, quy tắc scale/rounding của nghiệp vụ phải được nêu riêng; MathContext không tự biết quy tắc tiền tệ.

Ví dụ muốn hiển thị số lượng chữ số thập phân cố định, có thể chọn `setScale(2, RoundingMode.HALF_EVEN)` sau khi tính; nếu chỉ so sánh giá trị số học, có thể giữ `BigDecimal` gốc và tránh định dạng quá sớm.

## 7. Ngoại lệ và xác thực đầu vào

Các phép toán có thể ném `ArithmeticException` nếu miền giá trị không hợp lệ, yêu cầu precision không thể đáp ứng, hoặc `UNNECESSARY` cấm làm tròn. Ví dụ (đặt trong phương thức, đã import `java.math.*`):

```java
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

try {
    new BigDecimal("-4").sqrt(mc);
} catch (ArithmeticException ex) {
    System.out.println("Không có căn bậc hai thực cho số âm");
}
try {
    new BigDecimal("2").sqrt(MathContext.UNLIMITED);
} catch (ArithmeticException ex) {
    System.out.println("sqrt(2) không thể biểu diễn chính xác hữu hạn");
}
try {
    new BigDecimal("2").pow(-1);
} catch (ArithmeticException ex) {
    System.out.println("pow âm cần MathContext precision dương");
}
```

Nếu precision nhận từ người dùng, kiểm tra `precision > 0` cho cách tính gần đúng này; `new MathContext(-1)` ném `IllegalArgumentException`, còn `new MathContext(0)` biểu diễn unlimited. Với `pow`, kiểm tra cả giá trị số mũ, số chữ số của số mũ so với precision và cơ số 0 khi số mũ âm.

Có thể đóng gói quy tắc thống nhất bằng lớp sau, lưu riêng thành **`DecimalMath.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalMath {
    private DecimalMath() {}

    public static BigDecimal pow(BigDecimal base, int exponent, int precision) {
        Objects.requireNonNull(base, "base");
        if (precision <= 0) {
            throw new IllegalArgumentException("precision phải > 0");
        }
        MathContext mc = new MathContext(precision, RoundingMode.HALF_EVEN);
        return base.pow(exponent, mc);
    }

    public static BigDecimal sqrt(BigDecimal value, int precision) {
        Objects.requireNonNull(value, "value");
        if (precision <= 0) {
            throw new IllegalArgumentException("precision phải > 0");
        }
        MathContext mc = new MathContext(precision, RoundingMode.HALF_EVEN);
        return value.sqrt(mc);
    }
}
```

Lớp này lựa chọn `HALF_EVEN` làm chính sách mặc định *cho ví dụ*. Ứng dụng thực tế nên cho phép chọn mode theo yêu cầu nghiệp vụ. Nếu cơ số/số mũ hoặc căn không hợp lệ, ngoại lệ từ `BigDecimal` sẽ được truyền cho tầng gọi xử lý. Đừng bắt mọi `ArithmeticException` rồi trả `BigDecimal.ZERO` một cách âm thầm, vì điều đó biến lỗi thành dữ liệu sai.

## 8. Lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Tưởng `precision = 8` nghĩa là 8 số sau dấu phẩy | Precision đếm chữ số có nghĩa | Tách MathContext để tính và setScale để hiển thị |
| Dùng `pow(-2)` không có MathContext | Overload chính xác không nhận mũ âm | Dùng `pow(-2, mc)` với precision dương |
| Dùng `sqrt(MathContext.UNLIMITED)` cho số không có căn thập phân hữu hạn | Kết quả chính xác không biểu diễn được | Dùng precision dương và rounding mode |
| Dùng `pow(n)` cho n rất lớn khi chỉ cần kết quả làm tròn | Tạo kết quả chính xác quá tốn tài nguyên | Ưu tiên `pow(n, mc)` khi chấp nhận sai số API |
| Dùng `Math.pow` / `Math.sqrt` qua `double` | Không giữ phép tính thập phân theo MathContext | Tính trực tiếp bằng `BigDecimal` |
| So sánh `BigDecimal` bằng `equals` khi scale khác nhau | `1.0` không `equals` `1.00` dù bằng nhau về số học | Dùng `compareTo(...) == 0` khi chỉ xét giá trị |
| Làm tròn precision cuối ở mỗi bước tính | Tích lũy sai số trung gian | Chọn precision làm việc đủ cao, làm tròn ở ranh giới phù hợp |
| Dùng `new BigDecimal(0.1)` | Nhận giá trị chính xác của `double` xấp xỉ | Khởi tạo từ chuỗi hoặc `BigDecimal.valueOf` |

## 9. Tự luyện tập và kiểm chứng

1. `new BigDecimal("12.345").pow(2)` cho kết quả chính xác nào? Làm tròn với `new MathContext(4, HALF_EVEN)` còn bao nhiêu?
2. Vì sao `sqrt(4)` hoạt động với `MathContext.UNLIMITED`, nhưng `sqrt(2)` không?
3. Tính `new BigDecimal("10").pow(-2, new MathContext(5, HALF_EVEN))`; thử bỏ `MathContext` và giải thích.
4. Thiết kế cách hiện `sqrt(2)` với đúng hai chữ số sau dấu thập phân, đồng thời phân biệt precision tính toán và scale đầu ra.

Đáp án tham khảo: (1) chính xác là `152.399025`, sau làm tròn bốn chữ số có nghĩa là `152.4`; (2) căn của 2 có biểu diễn thập phân vô hạn; (3) `0.01`, còn `pow(-2)` không có MathContext ném ngoại lệ; (4) tính `sqrt` bằng MathContext đủ precision, rồi `setScale(2, HALF_EVEN)` cho `1.41`.

Khi dùng thực tế, hãy xác định **precision của phép tính**, **rounding mode** và **scale của kết quả xuất ra** như ba yêu cầu rõ ràng. `pow` giúp xử lý lũy thừa nguyên chính xác hoặc gần đúng; `sqrt` xử lý căn bậc hai không âm theo precision đã chọn. Với các công thức đòi hỏi sai số chặt chẽ, cần kiểm tra giới hạn thuật toán và kiểm thử tại các ranh giới làm tròn.

Nguồn API chính thức: [Java SE 17 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) (`pow(int)`, `pow(int, MathContext)`, `sqrt(MathContext)`).
