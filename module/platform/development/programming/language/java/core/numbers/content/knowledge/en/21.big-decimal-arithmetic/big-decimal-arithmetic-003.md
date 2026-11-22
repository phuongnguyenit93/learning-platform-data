# BigDecimal.divide: chọn scale, RoundingMode hay MathContext trong Java

Phép chia số thập phân không phải lúc nào cũng có kết quả thập phân hữu hạn. Ví dụ \(1/8=0.125\) biểu diễn decimal chính xác, nhưng \(1/3=0.3333\ldots\) kéo dài vô hạn. Với `java.math.BigDecimal`, **cách gọi `divide` quyết định khi nào được làm tròn, scale của kết quả và mức chính xác được phép**.

Java có nhiều overload của `divide`, nhưng bốn cách quan trọng nhất khi học:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = BigDecimal.valueOf(3);

// a.divide(b);                            // chính xác; 1/3 gây ArithmeticException
BigDecimal x = a.divide(b, 2, RoundingMode.HALF_UP); // 0.33, scale 2
BigDecimal y = a.divide(b, RoundingMode.HALF_UP);    // 0, scale của a bằng 0
BigDecimal z = a.divide(b, new MathContext(3, RoundingMode.HALF_UP)); // 0.333
```

Những đoạn ngắn trong bài giả định đã `import java.math.BigDecimal;`, `MathContext` và `RoundingMode` và được đặt trong một method/JShell. Chương trình Java 17+ đầy đủ, chạy được, nằm ở phần 12.

**Quy tắc tổng quát:** Chọn overload theo **hợp đồng kết quả**: cần chính xác không làm tròn, cần số chữ số **sau dấu thập phân**, muốn giữ **scale của số bị chia**, hay cần số **chữ số có nghĩa**.

## 1. Nền tảng: value, scale và precision của BigDecimal

`BigDecimal` mô hình hóa một số decimal bằng:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}
\]

Ví dụ `new BigDecimal("12.3400")` có unscaled value `123400`, scale 4 và precision 6. Hai đại lượng dễ nhầm:

- **Scale**: vị trí thập phân trong biểu diễn. Khi không âm, thường là số chữ số sau dấu chấm; **scale cũng có thể âm**.
- **Precision**: tổng số chữ số có nghĩa trong dạng thập phân của giá trị không scale, không phải số chữ số sau dấu chấm.

```java
BigDecimal number = new BigDecimal("12.3400");

System.out.println(number.unscaledValue()); // 123400
System.out.println(number.scale());         // 4
System.out.println(number.precision());     // 6
```

Trong phép chia, **scale và precision là hai loại giới hạn khác nhau**. Yêu cầu “giữ hai chữ số thập phân” thường cần `scale = 2`; còn yêu cầu “giữ ba chữ số có nghĩa” thường cần `MathContext(3, mode)`.

`BigDecimal` là **immutable**: `divide` trả về một giá trị mới, không thay đổi số bị chia hay số chia.

## 2. Tổng quan những overload quan trọng

| Cách gọi | Quy tắc kết quả | Khi nào chọn |
| --- | --- | --- |
| `a.divide(b)` | Thương **chính xác**, không chấp nhận khai triển decimal vô hạn | Khi toán học bảo đảm phép chia có dạng decimal hữu hạn |
| `a.divide(b, scale, mode)` | Thương có **scale được chỉ định**, làm tròn theo mode nếu cần | Tiền, đơn vị đo, giá trị cần số chữ số sau dấu thập phân |
| `a.divide(b, mode)` | Thương có **scale bằng `a.scale()`**, làm tròn nếu cần | Khi có chủ đích duy trì scale của số bị chia |
| `a.divide(b, context)` | Làm tròn theo **precision** và `RoundingMode` của `MathContext` | Tính toán với ngân sách chữ số có nghĩa |

Còn có một overload cũ nhận `int roundingMode`/hằng số legacy; không nên sử dụng trong code mới. Các hằng trong `RoundingMode` tạo API rõ kiểu và tránh số magic.

**Điểm mấu chốt:** `divide(b, RoundingMode.HALF_UP)` **không ngầm chọn scale = 2**. Nó dùng **scale của `a`**. Nếu `a == BigDecimal.ONE` thì scale bằng 0, nên `1/3` có thể thành **`0`**. Đây là lỗi đặc biệt nguy hiểm khi lập trình viên tưởng mode chỉ quyết định cách chọn chữ số cuối mà không quan tâm scale.

## 3. Khi nào dùng `divide(divisor)` thay vì overload làm tròn?

Phép `divide(divisor)` yêu cầu **thương decimal chính xác**. Ví dụ `BigDecimal.ONE.divide(new BigDecimal("8"))` trả `0.125`, còn chia cho `3` ném `ArithmeticException` vì thương có vô hạn chữ số. Sau khi rút gọn phân số, thương hữu hạn chỉ khi mẫu gồm các thừa số nguyên tố 2 và 5; cơ chế và chứng minh thuộc bài học *divide chính xác và số thập phân vô hạn tuần hoàn*.

Ở đây, điều cần quyết định là **chính sách đầu ra**: nếu nghiệp vụ yêu cầu exact thì chấp nhận kết quả hoặc báo lỗi; nếu cho phép làm tròn, hãy chọn rõ scale hay precision trong overload tương ứng. Preferred scale của divide exact là `a.scale() - b.scale()`, nhưng scale thực tế có thể lớn hơn để biểu diễn hết thương.

## 4. divide(divisor, scale, RoundingMode): đặt scale chính xác

Đây là lựa chọn trực tiếp nếu kết quả cần **N chữ số sau dấu chấm decimal**:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

BigDecimal rounded2 =
        one.divide(three, 2, RoundingMode.HALF_UP);
BigDecimal rounded5 =
        one.divide(three, 5, RoundingMode.HALF_UP);

System.out.println(rounded2); // 0.33
System.out.println(rounded5); // 0.33333
```

Từng tham số:

- `divisor`: số chia, không được bằng zero.
- `scale`: scale yêu cầu của **thương**, kiểu `int`; có thể bằng 0 hoặc âm.
- `roundingMode`: cách chọn giá trị có scale đó nếu thương chính xác không vừa biểu diễn.

Ngay cả khi thương **đã hữu hạn**, ép scale nhỏ hơn có thể buộc phải làm tròn:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(one.divide(eight, 2, RoundingMode.HALF_UP));   // 0.13
System.out.println(one.divide(eight, 2, RoundingMode.HALF_EVEN)); // 0.12
```

`1/8 = 0.125` là điểm giữa khi làm tròn đến hai chữ số sau dấu thập phân. `HALF_UP` chọn 0.13; `HALF_EVEN` chọn 0.12 vì chữ số cuối là 2 (chẵn).

### Scale 0 và scale âm

```java
System.out.println(
        BigDecimal.ONE.divide(BigDecimal.valueOf(3),
                0, RoundingMode.HALF_UP)); // 0

System.out.println(
        new BigDecimal("123").divide(BigDecimal.ONE,
                -1, RoundingMode.HALF_UP)); // 1.2E+2
```

Scale 0 tạo thương ở đơn vị nguyên; scale -1 tạo giá trị theo bội số của 10. `new BigDecimal("123") / 1` chính xác là 123, nhưng yêu cầu scale -1 khiến kết quả làm tròn thành 120 và có thể được in bằng dạng khoa học `1.2E+2`.

**Không sử dụng `setScale` mà không nghĩ đến rounding:** nếu đang cần giảm scale và bị mất chữ số có nghĩa, `setScale(newScale)` không có mode có thể ném `ArithmeticException`. Overload divide có mode đặt rõ chính sách ngay từ đầu.

## 5. divide(divisor, RoundingMode): lấy scale từ số bị chia

Đây là overload dễ bị hiểu nhầm:

```java
BigDecimal a = new BigDecimal("1.00");
BigDecimal b = BigDecimal.valueOf(3);

System.out.println(a.divide(b, RoundingMode.HALF_UP)); // 0.33
```

`a.scale() == 2`, nên thương được làm tròn về scale 2. Nhưng khi `a` được tạo từ `BigDecimal.ONE`:

```java
BigDecimal a = BigDecimal.ONE; // scale = 0
BigDecimal b = BigDecimal.valueOf(3);

System.out.println(a.divide(b, RoundingMode.HALF_UP)); // 0
```

Hai lời gọi dùng **cùng phép chia toán học 1/3 và cùng rounding mode**, nhưng khác scale của số bị chia. Do đó khác kết quả.

Tình huống nguy hiểm khác:

```java
BigDecimal amount = new BigDecimal("100");   // scale 0
BigDecimal factor = new BigDecimal("3");
BigDecimal result = amount.divide(factor, RoundingMode.HALF_UP);
// result == 33, không phải 33.33
```

Nếu hợp đồng yêu cầu 2 chữ số sau dấu chấm, hãy chỉ rõ **`divide(factor, 2, RoundingMode.HALF_UP)`**. Đừng dùng overload 2 tham số rồi dựa vào scale đầu vào tình cờ bằng 2.

## 6. divide(divisor, MathContext): giới hạn chữ số có nghĩa

`MathContext` chứa:

- `precision`: số chữ số có nghĩa cần giữ (`0` biểu thị không giới hạn).
- `roundingMode`: quy tắc làm tròn khi precision không đủ.

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);
BigDecimal result = one.divide(three, mc);

System.out.println(result); // 0.333
```

**Không được đồng nhất `precision = 3` với `scale = 3`**. Cùng context áp dụng cho một thương lớn:

```java
BigDecimal big = new BigDecimal("12345");
BigDecimal seven = BigDecimal.valueOf(7);
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(big.divide(seven, mc)); // 1.76E+3
```

Thương toán học xấp xỉ 1763.571..., làm tròn **ba chữ số có nghĩa** thành 1760, được in `1.76E+3`. Scale của kết quả là **-1**, không phải 3.

Cùng bài toán khác với `scale = 2`:

```java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = BigDecimal.valueOf(2);

System.out.println(
        a.divide(b, 2, RoundingMode.HALF_UP)); // 61.73

System.out.println(
        a.divide(b, new MathContext(2, RoundingMode.HALF_UP))); // 62
```

`123.45/2 = 61.725`, nên:

- **Scale 2** → 61.73 (hai chữ số sau dấu thập phân).
- **Precision 2** → 62 (hai chữ số có nghĩa).

### MathContext.UNLIMITED và precision = 0

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(
        one.divide(eight, MathContext.UNLIMITED)); // 0.125
```

`MathContext.UNLIMITED` đặt precision bằng 0; đối với divide, nó yêu cầu thương **chính xác**, tương tự `divide(divisor)` trong trường hợp thông thường. Nó **không** có nghĩa tính tùy ý nhiều chữ số của `1/3` mà không giới hạn bộ nhớ.

```java
// one.divide(BigDecimal.valueOf(3), MathContext.UNLIMITED);
// -> ArithmeticException, vì 1/3 có decimal vô hạn
```

Nếu đặt precision hữu hạn nhưng `RoundingMode.UNNECESSARY` và thương cần làm tròn, Java cũng có thể ném `ArithmeticException`. Phải chọn mode chấp nhận làm tròn khi bài toán yêu cầu xấp xỉ.

## 7. RoundingMode: phân biệt điểm giữa, dấu và hướng làm tròn

`RoundingMode` quyết định cách xử lý khi buộc phải bỏ chữ số, **không** tự quyết định nên làm tròn ở bước nào.

| Mode | Ý nghĩa | `+1/8` tại scale 2 | `-1/8` tại scale 2 |
| --- | --- | --- | --- |
| `UP` | Ra xa zero nếu có phần bị loại | `0.13` | `-0.13` |
| `DOWN` | Về zero | `0.12` | `-0.12` |
| `CEILING` | Về dương vô cực | `0.13` | `-0.12` |
| `FLOOR` | Về âm vô cực | `0.12` | `-0.13` |
| `HALF_UP` | Điểm giữa thì ra xa zero | `0.13` | `-0.13` |
| `HALF_DOWN` | Điểm giữa thì về zero | `0.12` | `-0.12` |
| `HALF_EVEN` | Điểm giữa thì chọn chữ số cuối chẵn | `0.12` | `-0.12` |
| `UNNECESSARY` | Không cho phép làm tròn có mất thông tin | `ArithmeticException` | `ArithmeticException` |

Ví dụ:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_UP));   // 0.13
System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_EVEN)); // 0.12
System.out.println(
        one.negate().divide(eight, 2, RoundingMode.HALF_UP)); // -0.13
```

Không mặc định `HALF_UP` đúng cho mọi bài toán tiền tệ hoặc `HALF_EVEN` đúng cho mọi phép thống kê. Hãy tuân thủ hợp đồng của hệ thống/ngành/định dạng đầu ra.

### Khi muốn ngăn làm tròn âm thầm

```java
try {
    BigDecimal exactTwoPlaces = BigDecimal.ONE.divide(
            BigDecimal.valueOf(3), 2, RoundingMode.UNNECESSARY);
} catch (ArithmeticException ex) {
    // 1/3 không thể lưu chính xác ở scale 2
}
```

`UNNECESSARY` là công cụ để **phát hiện yêu cầu làm tròn**. Nó cũng có thể phù hợp khi hợp đồng yêu cầu từ chối giao dịch thay vì tự cắt dữ liệu.

## 8. Chia cho 0: không giống phép chia double

Một `BigDecimal` không có giá trị đặc biệt `NaN` hoặc `Infinity`. Với `BigDecimal.divide`, số chia bằng 0 gây **`ArithmeticException`**:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal zero = BigDecimal.ZERO;

// a.divide(zero, 2, RoundingMode.HALF_UP);
// -> ArithmeticException: Division by zero
```

Khác với primitive `double`:

```java
System.out.println(1.0 / 0.0); // Infinity
System.out.println(0.0 / 0.0); // NaN
```

Không viết code dùng `BigDecimal` rồi kỳ vọng `divide` có thể trả Infinity. Trong Java, phải có **hợp đồng xử lý chia cho 0**, ví dụ validate ngay đầu vào và cung cấp thông báo nghiệp vụ.

```java
static BigDecimal safeDivide(BigDecimal a, BigDecimal b,
                             int scale, RoundingMode mode) {
    if (b.signum() == 0) {
        throw new IllegalArgumentException("Divisor must be nonzero");
    }
    return a.divide(b, scale, mode);
}
```

Đây là helper minh họa cần đặt **trong một class**, không phải chương trình độc lập. `signum() == 0` kiểm tra zero theo giá trị, kể cả `0.00` có scale khác 0. Có thể validate null qua `Objects.requireNonNull` nếu đầu vào có thể null.

**Đừng bắt tất cả `ArithmeticException` rồi coi là chia cho 0**. Với overload divide chính xác hoặc `UNNECESSARY`, exception còn có thể phát sinh vì thương không biểu diễn chính xác ở precision/scale yêu cầu.

## 9. Chia chính xác không phải lúc nào cũng giữ scale mong muốn

Khi chia một giá trị có trailing zeros, kết quả của các overload có thể khác ở **scale** dù **giá trị toán học bằng nhau**:

```java
BigDecimal a = new BigDecimal("2.000");
BigDecimal b = new BigDecimal("4");

BigDecimal exact = a.divide(b);                    // 0.500
BigDecimal sameScale = a.divide(b, RoundingMode.HALF_UP); // 0.500
BigDecimal scale2 = a.divide(b, 2, RoundingMode.HALF_UP); // 0.50
```

Một vấn đề là `BigDecimal.equals` so sánh **giá trị và scale**, còn `compareTo` chỉ so sánh **giá trị số**:

```java
System.out.println(new BigDecimal("0.50")
        .equals(new BigDecimal("0.500")));    // false
System.out.println(new BigDecimal("0.50")
        .compareTo(new BigDecimal("0.500"))); // 0
```

Nếu dùng `HashSet<BigDecimal>` hoặc `HashMap<BigDecimal, ...>`, scale khác nhau có thể biến thành **hai khóa khác nhau**. Không nên bỏ qua scale sau khi chia, đặc biệt khi hệ thống dùng decimal biểu diễn đơn vị đo, tỷ lệ hoặc quy tắc làm tròn.

Một cách ổn định cho dữ liệu chốt ở scale 2 là **chỉ định scale 2 ngay trong phép chia**, chứ không chọn scale từ `a` tình cờ.

## 10. Chọn precision làm việc và thời điểm chốt kết quả

Một thuật toán nhiều bước thường cần **precision làm việc** lớn hơn precision dữ liệu được ghi nhận. Ví dụ chia ba khoản, cộng dồn, nhân tỷ lệ hay phân bổ chi phí.

Không tự động làm tròn về hai chữ số sau mỗi phép toán chỉ vì mục tiêu cuối là hai chữ số. Kết quả có thể phụ thuộc việc bạn làm tròn ở đâu.

Giả sử hai thành phần chính xác đều là `0.015`:

```text
Làm tròn từng thành phần theo HALF_UP ở scale 2:
0.015 -> 0.02
0.015 -> 0.02
Tổng = 0.04

Cộng rồi làm tròn tổng:
0.015 + 0.015 = 0.030
0.030 -> 0.03
Tổng = 0.03
```

**Cả hai có thể đúng trong những hợp đồng khác nhau**:

- Nếu từng thành phần là dòng giao dịch độc lập phải chốt ở hai chữ số, tổng đúng có thể là 0.04.
- Nếu đầu vào là các thành phần trung gian của một khoản duy nhất cần chốt một lần, kết quả có thể là 0.03.

Trong một luồng BigDecimal, nên xác định trước: đầu vào dạng decimal chính xác hay gần đúng; làm tròn ở đơn giá, dòng hay tổng; scale cần giữ; rounding mode; cách xử lý phần dư và cách lưu giá trị đã chốt.

### Precision của MathContext không thay thế hợp đồng về scale

```java
MathContext working = new MathContext(12, RoundingMode.HALF_EVEN);
BigDecimal approximateRatio =
        BigDecimal.ONE.divide(BigDecimal.valueOf(7), working);
// Có 12 chữ số có nghĩa; kết quả không mang mặc định scale 2.

BigDecimal committed =
        approximateRatio.setScale(2, RoundingMode.HALF_UP);
// Phải có quyết định rõ rằng đây chính là bước chốt ở scale 2.
```

Đừng mặc định `MathContext` có thể “làm mọi phép chia chính xác”: đó là **xấp xỉ có giới hạn chữ số có nghĩa** khi thương decimal vô hạn. Khi phải bảo toàn chính xác phân số ban đầu, mô hình cặp tử số/mẫu số hoặc một kiểu phân số hữu tỉ riêng có thể phù hợp hơn việc ép mọi kết quả sang BigDecimal hữu hạn.

## 11. Những API liên quan cần biết nhưng không nhầm với divide có rounding

`BigDecimal` còn có:

- `divideToIntegralValue(divisor)`: lấy phần nguyên của thương theo hướng về 0, trình bày dưới dạng BigDecimal.
- `remainder(divisor)`: lấy phần dư theo quy tắc BigDecimal; không phải phép `%` primitive dùng trên đối tượng.
- `divideAndRemainder(divisor)`: nhận đồng thời thương nguyên và phần dư.

Ví dụ:

```java
BigDecimal ten = new BigDecimal("10");
BigDecimal three = new BigDecimal("3");

System.out.println(ten.divideToIntegralValue(three)); // 3
System.out.println(ten.remainder(three));             // 1
```

**Không dùng `divideToIntegralValue` để thay cho `divide(..., 0, mode)` một cách bừa bãi**: phép thứ nhất lấy phần nguyên về 0, trong khi divide với scale 0 có thể làm tròn theo mode như `HALF_UP` hoặc `CEILING`.

Nếu mục tiêu là hiển thị hai chữ số, việc dùng `String.format("%.2f", someDouble)` cũng **không tương đương** với chia BigDecimal chính xác rồi chốt theo `RoundingMode` của nghiệp vụ. Định dạng chuỗi chỉ là bước biểu diễn văn bản và có thể mang các hạn chế của kiểu đầu vào.

## 12. Chương trình Java 17+ chạy độc lập

Tạo file **`BigDecimalDivideDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDivideDemo {
    static void showError(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=NOT_THROWN");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = BigDecimal.valueOf(3);
        BigDecimal eight = BigDecimal.valueOf(8);

        System.out.println("exactOneOverEight=" + one.divide(eight));
        showError("exactOneOverThree", () -> one.divide(three));
        System.out.println("scaleTwo=" +
                one.divide(three, 2, RoundingMode.HALF_UP));
        System.out.println("scaleFive=" +
                one.divide(three, 5, RoundingMode.HALF_UP));
        System.out.println("scaleZero=" +
                one.divide(three, 0, RoundingMode.HALF_UP));
        System.out.println("scaleMinusOne=" +
                new BigDecimal("123").divide(
                        BigDecimal.ONE, -1, RoundingMode.HALF_UP));

        System.out.println("implicitScaleZero=" +
                one.divide(three, RoundingMode.HALF_UP));
        System.out.println("implicitScaleTwo=" +
                new BigDecimal("1.00").divide(
                        three, RoundingMode.HALF_UP));
        System.out.println("sameScaleResult=" +
                new BigDecimal("2.000").divide(
                        new BigDecimal("4"), RoundingMode.HALF_EVEN));

        MathContext mc3 = new MathContext(3, RoundingMode.HALF_UP);
        System.out.println("contextThree=" + one.divide(three, mc3));
        System.out.println("contextBig=" +
                new BigDecimal("12345").divide(
                        new BigDecimal("7"), mc3));
        System.out.println("unlimitedExact=" +
                one.divide(eight, MathContext.UNLIMITED));
        showError("unlimitedRecurring",
                () -> one.divide(three, MathContext.UNLIMITED));

        BigDecimal a = new BigDecimal("123.45");
        BigDecimal two = BigDecimal.valueOf(2);
        System.out.println("scaleVersusPrecisionScale=" +
                a.divide(two, 2, RoundingMode.HALF_UP));
        System.out.println("scaleVersusPrecisionContext=" +
                a.divide(two, new MathContext(
                        2, RoundingMode.HALF_UP)));

        System.out.println("tieHalfUp=" +
                one.divide(eight, 2, RoundingMode.HALF_UP));
        System.out.println("tieHalfEven=" +
                one.divide(eight, 2, RoundingMode.HALF_EVEN));
        System.out.println("negativeHalfUp=" +
                one.negate().divide(
                        eight, 2, RoundingMode.HALF_UP));
        System.out.println("negativeHalfEven=" +
                one.negate().divide(
                        eight, 2, RoundingMode.HALF_EVEN));

        showError("unnecessaryRecurring",
                () -> one.divide(
                        three, 2, RoundingMode.UNNECESSARY));
        showError("divideByZero",
                () -> one.divide(
                        BigDecimal.ZERO, 2, RoundingMode.HALF_UP));

        BigDecimal exactWithScale = new BigDecimal("1.00")
                .divide(new BigDecimal("8.0"));
        System.out.println("exactPreferredScaleValue=" +
                exactWithScale.toPlainString());
        System.out.println("exactPreferredScaleActual=" +
                exactWithScale.scale());

        BigDecimal forty = new BigDecimal("40");
        System.out.println("terminatingThreeOverForty=" +
                new BigDecimal("3").divide(forty));

        BigDecimal small = new BigDecimal("0.015");
        BigDecimal settledEach =
                small.setScale(2, RoundingMode.HALF_UP);
        System.out.println("roundedEachThenSum=" +
                settledEach.add(settledEach));
        System.out.println("sumThenRound=" +
                small.add(small).setScale(
                        2, RoundingMode.HALF_UP));

        System.out.println("divideIntegral=" +
                BigDecimal.TEN.divideToIntegralValue(three));
        System.out.println("remainder=" +
                BigDecimal.TEN.remainder(three));

        System.out.println("primitiveDoubleZero=" + (1.0 / 0.0));
        System.out.println("oneUnchanged=" + one);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BigDecimalDivideDemo.java
java BigDecimalDivideDemo
```

**Stdout dự kiến:**

```text
exactOneOverEight=0.125
exactOneOverThree=ArithmeticException
scaleTwo=0.33
scaleFive=0.33333
scaleZero=0
scaleMinusOne=1.2E+2
implicitScaleZero=0
implicitScaleTwo=0.33
sameScaleResult=0.500
contextThree=0.333
contextBig=1.76E+3
unlimitedExact=0.125
unlimitedRecurring=ArithmeticException
scaleVersusPrecisionScale=61.73
scaleVersusPrecisionContext=62
tieHalfUp=0.13
tieHalfEven=0.12
negativeHalfUp=-0.13
negativeHalfEven=-0.12
unnecessaryRecurring=ArithmeticException
divideByZero=ArithmeticException
exactPreferredScaleValue=0.125
exactPreferredScaleActual=3
terminatingThreeOverForty=0.075
roundedEachThenSum=0.04
sumThenRound=0.03
divideIntegral=3
remainder=1
primitiveDoubleZero=Infinity
oneUnchanged=1
```

Đầu ra cho thấy:

- `exactOneOverEight` thành công nhưng `exactOneOverThree` ném exception.
- `implicitScaleZero=0` và `implicitScaleTwo=0.33` xuất phát từ **scale khác nhau của số bị chia**, dù đều là 1/3.
- `scaleVersusPrecisionScale=61.73` khác `scaleVersusPrecisionContext=62` vì một phía giới hạn **scale**, phía kia giới hạn **chữ số có nghĩa**.
- `tieHalfUp=0.13` và `tieHalfEven=0.12` chứng minh chính sách làm tròn điểm giữa.
- `exactPreferredScaleActual=3` chứng minh scale thương chính xác có thể **lớn hơn preferred scale**.
- `roundedEachThenSum=0.04` khác `sumThenRound=0.03` do **thời điểm chốt** chứ không phải bug BigDecimal.

## 13. Lỗi phổ biến và cách phòng tránh

| Hiểu nhầm hoặc cách làm | Thực tế |
| --- | --- |
| “`divide(b)` luôn tự chọn số chữ số hợp lý.” | Không: decimal vô hạn gây `ArithmeticException`. |
| “`divide(b, HALF_UP)` mặc định làm tròn hai chữ số.” | Không: giữ scale của số bị chia. |
| “`scale = 2` và `MathContext(2)` giống nhau.” | Không: một là hai chữ số sau dấu chấm, một là hai chữ số có nghĩa. |
| “`MathContext.UNLIMITED` tự biểu diễn được 1/3 vô hạn.” | Không: phép chia không kết thúc vẫn ném exception. |
| “`RoundingMode.UNNECESSARY` luôn an toàn với phép chia.” | Không: nếu phải làm tròn sẽ có `ArithmeticException`. |
| “Tất cả `ArithmeticException` của divide đều nghĩa là chia cho 0.” | Không: còn có thương decimal không kết thúc hoặc không vừa precision/scale. |
| “`BigDecimal.divide` cho Infinity như `double`.” | Không: BigDecimal không có NaN/Infinity. |
| “RoundingMode.HALF_EVEN luôn khác HALF_UP.” | Chỉ khác ở một số điểm giữa tùy chữ số cuối; nhiều đầu vào cho cùng kết quả. |
| “Chia chính xác đảm bảo kết quả có preferred scale.” | Preferred scale chỉ là ưu tiên; kết quả exact có thể cần scale lớn hơn. |
| “Các kết quả so sánh `equals` khi cùng số học.” | `equals` còn so scale; `compareTo` mới so giá trị số. |
| “Dùng BigDecimal tạo từ `new BigDecimal(0.1)` sẽ sửa sai số nguồn.” | Không: đó là biểu diễn chính xác của xấp xỉ nhị phân `double`. |
| “Có thể tự làm tròn sau mọi bước để an toàn hơn.” | Có thể mất thông tin; hợp đồng mới quyết định thời điểm cần chốt. |

Checklist trước mỗi `divide`:

1. **Số chia khác 0 chưa?** Kiểm tra `divisor.signum() != 0`, kể cả biểu diễn `0.00`.
2. **Thương có thể có decimal vô hạn không?** Nếu có, phải chọn scale/precision và mode chấp nhận làm tròn hoặc từ chối phép tính.
3. **Đích yêu cầu scale cố định hay chữ số có nghĩa?** Chọn `divide(b, scale, mode)` hoặc `divide(b, MathContext)` tương ứng.
4. **Có thực sự muốn giữ scale của số bị chia?** Chỉ khi đúng như vậy mới chọn `divide(b, mode)`.
5. **RoundingMode nào là hợp đồng?** Xác định ở điểm giữa, số âm, giao dịch độc lập và phép chia chính xác không vừa độ rộng.
6. **Tính nội bộ và quyết toán có tách rời không?** Chỉ làm tròn tại ranh giới có ý nghĩa, không tự làm tròn mọi bước.
7. **Đầu ra cần được lưu/so sánh thế nào?** Phân biệt `compareTo` và `equals` vì scale khác nhau.
8. **Cách xử lý exception đã rõ chưa?** Phân loại chia cho zero, decimal vô hạn và `UNNECESSARY` trước khi báo lỗi phù hợp.
9. **Kết quả có thể quá lớn hoặc tốn tài nguyên không?** Đặt giới hạn precision, scale, chiều dài đầu vào theo chính sách ứng dụng.
10. **Đã kiểm thử số âm, zero, điểm giữa và scale âm chưa?** Những trường hợp này thường phát hiện bug sớm nhất.

**Kết luận:** `BigDecimal.divide` có nhiều overload vì không có một chính sách làm tròn đúng cho mọi tình huống. `divide(divisor)` yêu cầu **chính xác**; `divide(divisor, scale, mode)` chọn **scale cụ thể**; `divide(divisor, mode)` lấy **scale của số bị chia**; còn `divide(divisor, MathContext)` giới hạn **chữ số có nghĩa**. Chọn overload dựa trên yêu cầu dữ liệu và hợp đồng làm tròn, không dựa trên cảm giác rằng một mode hay một số chữ số “có vẻ đủ”.

Tài liệu API: [Oracle Java 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) và [MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html).