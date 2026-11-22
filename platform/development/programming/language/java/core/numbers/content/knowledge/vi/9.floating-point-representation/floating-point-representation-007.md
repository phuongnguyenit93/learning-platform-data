# MIN_VALUE, MIN_NORMAL và MAX_VALUE của float/double trong Java

> **Java core – numbers · Biểu diễn dấu phẩy động**  
> **Mục tiêu:** Phân biệt ba hằng biên quan trọng của `Float`/`Double`, đọc đúng miền *normal* và *subnormal* của IEEE 754, hiểu underflow/overflow, nhận biết số 0 có dấu và chọn cách kiểm tra biên phù hợp trong Java 17+.

## 1. Câu trả lời quan trọng nhất

Đối với **`float` và `double`**, Java định nghĩa:

- **`MIN_VALUE`:** số dấu phẩy động **dương hữu hạn khác 0 nhỏ nhất** có thể biểu diễn, thuộc vùng **subnormal** (*dưới chuẩn hóa*).
- **`MIN_NORMAL`:** số dấu phẩy động **dương hữu hạn chuẩn hóa nhỏ nhất** (*smallest positive normal*).
- **`MAX_VALUE`:** số dấu phẩy động **dương hữu hạn lớn nhất** có thể biểu diễn.

**Cảnh báo:** `Double.MIN_VALUE` **không phải số âm nhỏ nhất**. Hằng này lớn hơn 0 nhưng cực kỳ gần 0. Nếu cần giá trị `double` hữu hạn âm có độ lớn lớn nhất, dùng `-Double.MAX_VALUE`. Quy tắc tương tự áp dụng cho `Float`.

Đây là đặc điểm khác hẳn hằng `Integer.MIN_VALUE` hay `Long.MIN_VALUE`: đối với kiểu **nguyên**, `MIN_VALUE` là số âm nhỏ nhất; đối với **dấu phẩy động**, nó là số **dương khác 0 nhỏ nhất**.

## 2. Bảng giá trị quan trọng

| Hằng | Giá trị Java in dạng thập phân | Dạng chính xác theo cơ số 2 |
| --- | --- | --- |
| `Float.MIN_VALUE` | `1.4E-45` | `2^-149` |
| `Float.MIN_NORMAL` | `1.17549435E-38` | `2^-126` |
| `Float.MAX_VALUE` | `3.4028235E38` | `(2 - 2^-23) × 2^127` |
| `Double.MIN_VALUE` | `4.9E-324` | `2^-1074` |
| `Double.MIN_NORMAL` | `2.2250738585072014E-308` | `2^-1022` |
| `Double.MAX_VALUE` | `1.7976931348623157E308` | `(2 - 2^-52) × 2^1023` |

Dãy số thập phân trong bảng là cách Java hiển thị giá trị dưới dạng chuỗi ngắn đủ nhận diện giá trị nhị phân; không nên hiểu `4.9E-324` là giá trị toán học chính xác bằng `4.9 × 10^-324`. Dạng lũy thừa của 2 mô tả trực tiếp giá trị trong hệ nhị phân.

Các hằng nằm trong `java.lang.Float` và `java.lang.Double`; không cần import riêng.

```java
float smallestPositiveFloat = Float.MIN_VALUE;
float smallestNormalFloat = Float.MIN_NORMAL;
float largestFiniteFloat = Float.MAX_VALUE;

double smallestPositiveDouble = Double.MIN_VALUE;
double smallestNormalDouble = Double.MIN_NORMAL;
double largestFiniteDouble = Double.MAX_VALUE;
```

Tất cả sáu hằng đều mang giá trị **dương, hữu hạn, khác 0**. Không hằng nào là `NaN` hoặc vô cực.

## 3. Bố cục IEEE 754 giải thích ba ranh giới

Java dùng dạng nhị phân IEEE 754 cho `float` (*binary32*) và `double` (*binary64*):

| Thuộc tính | `float` | `double` |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit exponent lưu trữ | 8 | 11 |
| Bit fraction lưu trữ | 23 | 52 |
| Số bit chính xác hiệu dụng của số normal | 24 | 53 |
| Exponent không thiên lệch nhỏ nhất của normal | −126 | −1022 |
| Exponent không thiên lệch lớn nhất của normal | +127 | +1023 |

Lược đồ:

```text
float  (32 bit): [sign:1][exponent:8 ][fraction:23]
double (64 bit): [sign:1][exponent:11][fraction:52]
```

Với một số **normal hữu hạn** có exponent field không phải toàn 0/toàn 1, giá trị tuyệt đối có dạng:

\[
(1+\mathrm{fraction})\times 2^e
\]

Bit `1` đầu tiên của phần trị normal là **ẩn** (*implicit leading 1*), nhờ vậy số bit chính xác hiệu dụng lớn hơn số bit fraction lưu trong bộ nhớ 1 bit.

Với số **subnormal**, exponent field **toàn 0**, fraction field **khác 0**, và bit dẫn đầu chuyển thành **0**:

\[
\mathrm{fraction}\times 2^{e_{\min}}
\]

Ở đây `fraction` là giá trị từ các bit phần lẻ nhị phân; `e_min` bằng −126 cho `float` và −1022 cho `double`. Vì không còn bit `1` ẩn, độ chính xác tương đối của các số subnormal giảm dần khi tiến về 0.

Exponenent field **toàn 1** được dành cho các giá trị đặc biệt: `Infinity` và `NaN`. Số 0 có exponent field và fraction field đều bằng 0, với bit dấu có thể là 0 hoặc 1.

## 4. MIN_NORMAL: ranh giới bắt đầu của số normal

Số normal dương nhỏ nhất có phần trị hiệu dụng là **1.0** và exponent nhỏ nhất của normal:

\[
\mathrm{Float.MIN\_NORMAL}=1.0\times 2^{-126}
\]

\[
\mathrm{Double.MIN\_NORMAL}=1.0\times 2^{-1022}
\]

Trong Java:

```java
float f = 0x1.0p-126f;
double d = 0x1.0p-1022;

System.out.println(f == Float.MIN_NORMAL);   // true
System.out.println(d == Double.MIN_NORMAL); // true
```

Những hằng hex này đọc là: phần trị `0x1.0` bằng 1, chữ `p` chỉ số mũ của **2**, và hậu tố `f` buộc kiểu `float`. Các biểu thức hex rất tiện khi mô tả biên nhị phân chính xác.

**Điều cần tránh:** `MIN_NORMAL` không phải số dương khác 0 nhỏ nhất. Java còn biểu diễn được các giá trị nhỏ hơn nhờ miền subnormal.

## 5. MIN_VALUE: bước nhỏ nhất khác 0 ở sát số 0

Số subnormal dương nhỏ nhất có đúng **một bit fraction thấp nhất bằng 1**. Giá trị của nó là:

\[
\mathrm{Float.MIN\_VALUE}=2^{-149}
\]

\[
\mathrm{Double.MIN\_VALUE}=2^{-1074}
\]

Có thể viết chính xác:

```java
float minFloat = 0x1p-149f;       // Float.MIN_VALUE
double minDouble = 0x1p-1074;   // Double.MIN_VALUE

System.out.println(minFloat == Float.MIN_VALUE);   // true
System.out.println(minDouble == Double.MIN_VALUE); // true
```

Với `double`, fraction field có 52 bit, nên để từ exponent −1022 đi xuống bit fraction cuối cùng cần thêm 52 bậc: `−1022 − 52 = −1074`. Với `float`: `−126 − 23 = −149`.

Khoảng giữa **0** và **MIN_NORMAL** gồm nhiều số subnormal dương:

```text
0       MIN_VALUE      ...     subnormal lớn nhất    MIN_NORMAL
|-----------|--------------------------|------------------|
            ^                                      ^
  subnormal dương nhỏ nhất               normal dương nhỏ nhất
```

Khoảng cách giữa hai giá trị subnormal dương liên tiếp bằng `MIN_VALUE` của kiểu tương ứng. Đây là cơ chế *gradual underflow*, giúp hạn chế việc một phép toán rất nhỏ bị cắt ngay về 0.

Một kiểm tra:

```java
double smallestStep = Double.MIN_VALUE;
double largestSubnormal = Math.nextDown(Double.MIN_NORMAL);

System.out.println(largestSubnormal + smallestStep
        == Double.MIN_NORMAL); // true
```

Giá trị subnormal lớn nhất là số nằm ngay trước `MIN_NORMAL` trên trục số dương.

## 6. MAX_VALUE: số hữu hạn lớn nhất, chưa phải Infinity

`Float.MAX_VALUE` và `Double.MAX_VALUE` mang **exponent hữu hạn lớn nhất** và toàn bộ fraction bit bằng 1:

\[
\mathrm{Float.MAX\_VALUE}=(2-2^{-23})\times 2^{127}
\]

\[
\mathrm{Double.MAX\_VALUE}=(2-2^{-52})\times 2^{1023}
\]

Dạng literal hex chính xác:

```java
float largestFloat = 0x1.fffffep127f;
double largestDouble = 0x1.fffffffffffffp1023;

System.out.println(largestFloat == Float.MAX_VALUE); // true
System.out.println(largestDouble == Double.MAX_VALUE); // true
```

**MAX_VALUE không phải Infinity.** Nó hữu hạn. Nhưng một phép tính vượt miền có thể **overflow thành vô cực**:

```java
double big = Double.MAX_VALUE;
double overflow = big * 2.0;

System.out.println(Double.isFinite(big)); // true
System.out.println(overflow);             // Infinity
System.out.println(Double.isInfinite(overflow)); // true
```

Không được giả định mọi phép vượt gần biên đều lập tức ra `Infinity`: IEEE 754 làm tròn kết quả; ở một số giá trị thực toán học hơi lớn hơn `MAX_VALUE`, phép làm tròn vẫn có thể trả `MAX_VALUE`. Điều đúng cần nhớ là khi **kết quả đã làm tròn vượt số hữu hạn biểu diễn được**, nó trở thành vô cực theo các quy tắc dấu phẩy động.

Với kết quả âm vượt biên dưới hữu hạn, bạn có thể nhận `Double.NEGATIVE_INFINITY`. Các hằng `POSITIVE_INFINITY`/`NEGATIVE_INFINITY` và `NaN` thuộc hệ giá trị đặc biệt, khác `MAX_VALUE`.

## 7. Miền số trên trục số: âm, 0, subnormal, normal

Xét riêng các giá trị `double` hữu hạn:

```text
   -Double.MAX_VALUE                                  Double.MAX_VALUE
          |                                                   |
     âm normal ... âm subnormal  -0.0  +0.0  dương subnormal ... normal
          |                    |    |    |                   |
          +--------------------+----+----+-------------------+

Biên dương:
0 < Double.MIN_VALUE < Double.MIN_NORMAL < Double.MAX_VALUE
```

Hai số `+0.0` và `-0.0` có **bit dấu khác nhau** nhưng so sánh bằng nhau với toán tử `==`:

```java
System.out.println(0.0 == -0.0); // true
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(1.0 / -0.0);  // -Infinity
```

Vậy `-0.0` là giá trị quan trọng ở ranh giới dưới 0, nhưng **không thể gọi** nó là “số âm hữu hạn nhỏ nhất” theo nghĩa miền giá trị; số âm hữu hạn có trị tuyệt đối lớn nhất là `-Double.MAX_VALUE`.

Một thứ tự giá trị **hữu hạn** quanh 0:

```text
... < -Double.MIN_NORMAL < -Double.MIN_VALUE < -0.0
                                                = +0.0
                                < Double.MIN_VALUE < Double.MIN_NORMAL < ...
```

Ký hiệu `-0.0 = +0.0` ở đây nói về so sánh số học thông thường (`==`), không khẳng định hai biểu diễn bit là giống nhau. Với `Double.compare` hoặc `Double.equals`, có những quy tắc khác về cách phân biệt hai số 0 có dấu.

## 8. Underflow: từ normal qua subnormal rồi về 0

*Underflow* xảy ra khi kết quả tính toán nằm rất sát 0 so với miền/độ chính xác của kiểu dấu phẩy động. Nó có thể tạo ra một số **subnormal**, hoặc về **0 có dấu** nếu kết quả quá nhỏ để làm tròn thành giá trị khác 0.

```java
double justSubnormal = Double.MIN_NORMAL / 2.0;
double underflowToZero = Double.MIN_VALUE / 2.0;

System.out.println(justSubnormal > 0.0);  // true
System.out.println(justSubnormal < Double.MIN_NORMAL); // true
System.out.println(underflowToZero);       // 0.0
```

Vì `MIN_VALUE` đã là bước subnormal nhỏ nhất khác 0, chia cho 2 tạo giá trị toán học đúng giữa 0 và `MIN_VALUE`; với chế độ làm tròn mặc định đến giá trị gần nhất, hòa thì chọn chữ số chẵn (*round to nearest, ties to even*), kết quả là `+0.0`.

Tương tự, `-Double.MIN_VALUE / 2.0` làm tròn về `-0.0`; **dấu có thể được giữ ngay cả khi độ lớn về 0**.

Vùng subnormal hữu ích vì phép trừ những số rất nhỏ còn có thể cho kết quả khác 0 thay vì lập tức đột ngột về 0. Tuy vậy số subnormal có ít bit có nghĩa hơn, nên **độ chính xác tương đối thấp hơn** so với số normal.

**Không dùng** `Double.MIN_VALUE` như “ngưỡng sai số nhỏ chuẩn” cho mọi phép so sánh gần bằng. Nó quá nhỏ so với sai số của các phép tính ở độ lớn thường gặp như gần 1 hoặc 1000.

## 9. ULP và nextUp/nextDown: cách khảo sát giá trị sát nhau

*ULP* (*unit in the last place*) mô tả khoảng cách giữa những giá trị biểu diễn được ở một vùng độ lớn nhất định. Trong Java:

- `Math.ulp(x)` cho biết đơn vị bước gần x theo quy tắc của API.
- `Math.nextUp(x)` trả số dấu phẩy động có thể biểu diễn ngay phía trên x.
- `Math.nextDown(x)` trả số có thể biểu diễn ngay phía dưới x.

Các ví dụ kiểm chứng biên:

```java
System.out.println(Math.nextUp(0.0) == Double.MIN_VALUE); // true
System.out.println(Math.nextDown(Double.MIN_NORMAL)
        + Double.MIN_VALUE == Double.MIN_NORMAL);         // true
System.out.println(Math.nextUp(Double.MAX_VALUE));       // Infinity
System.out.println(Math.ulp(0.0) == Double.MIN_VALUE);    // true
```

Với các số normal, khoảng cách giữa các số liền kề **không cố định trên toàn trục số**: càng tăng độ lớn, bước nhảy giữa các giá trị có thể biểu diễn thường tăng theo lũy thừa của 2.

Ví dụ:

```java
System.out.println(Math.ulp(1.0));    // 2.220446049250313E-16
System.out.println(Math.ulp(2.0));    // 4.440892098500626E-16
```

Vì vậy một điều kiện như `Math.abs(a - b) < Double.MIN_VALUE` gần như chỉ chấp nhận hiệu đúng bằng 0 ở nhiều vùng số; nếu muốn so sánh gần bằng, phải lựa chọn **độ sai số tuyệt đối/tương đối theo nghiệp vụ** (và cân nhắc vô cực, NaN, gần 0).

## 10. Số đặc biệt: NaN, Infinity, positive/negative zero

Ngoài số hữu hạn bình thường và subnormal, IEEE 754 còn có:

| Giá trị | Ví dụ tạo ra | Đặc điểm |
| --- | --- | --- |
| `Double.POSITIVE_INFINITY` | `1.0 / 0.0` | Không hữu hạn, lớn hơn mọi số hữu hạn |
| `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Không hữu hạn, nhỏ hơn mọi số hữu hạn |
| `Double.NaN` | `0.0 / 0.0` | “Not a Number”, so sánh số học đặc biệt |
| `+0.0` | `0.0` | Số 0 có dấu dương |
| `-0.0` | `-0.0` | Số 0 có dấu âm; `1.0 / -0.0` trả `-Infinity` |

```java
double x = Double.NaN;
System.out.println(x == x);             // false
System.out.println(Double.isNaN(x));     // true
System.out.println(Double.isFinite(x));  // false
```

Không kiểm tra NaN bằng `x == Double.NaN`. Dùng `Double.isNaN(x)`. Với vô cực dùng `Double.isInfinite(x)`, còn `Double.isFinite(x)` xác định số hữu hạn (bao gồm normal, subnormal và cả ±0.0).

Nếu API yêu cầu “số dương và hữu hạn”, điều kiện có thể là:

```java
static boolean positiveFinite(double x) {
    return Double.isFinite(x) && x > 0.0;
}
```

Điều kiện này chấp nhận số subnormal dương. Nếu nghiệp vụ muốn chỉ chấp nhận **normal dương**, phải nêu và kiểm tra thêm `x >= Double.MIN_NORMAL` (đồng thời giữ `isFinite`). Điều kiện `x >= Double.MIN_VALUE` **không** thay thế kiểm tra normal.

## 11. Inspect bit: ba hằng khác nhau ở exponent/fraction

Xem cấu trúc bit giúp kết nối giá trị thập phân với biểu diễn IEEE 754:

| Hằng | Hex của toàn bộ raw bits | Ý nghĩa |
| --- | --- | --- |
| `Float.MIN_VALUE` | `0x00000001` | exponent=0, fraction có bit thấp nhất |
| `Float.MIN_NORMAL` | `0x00800000` | exponent lưu bằng 1, fraction=0 |
| `Float.MAX_VALUE` | `0x7f7fffff` | exponent hữu hạn lớn nhất, fraction toàn 1 |
| `Double.MIN_VALUE` | `0x0000000000000001` | exponent=0, fraction có bit thấp nhất |
| `Double.MIN_NORMAL` | `0x0010000000000000` | exponent lưu bằng 1, fraction=0 |
| `Double.MAX_VALUE` | `0x7fefffffffffffff` | exponent hữu hạn lớn nhất, fraction toàn 1 |

Trong Java:

```java
int fBits = Float.floatToRawIntBits(Float.MIN_NORMAL);
long dBits = Double.doubleToRawLongBits(Double.MIN_NORMAL);
System.out.printf("float bits = %08x%n", fBits);  // 00800000
System.out.printf("double bits = %016x%n", dBits); // 0010000000000000
```

Lưu ý: **raw bits** là cách mã hóa đủ bit dấu, exponent và fraction, còn `Double.toHexString` biểu diễn **giá trị toán học** theo phần trị hex và số mũ nhị phân. Hai dạng có mục đích khác nhau; không nhầm chúng là một chuỗi.

Dạng `Double.toHexString(Double.MIN_VALUE)` là `"0x0.0000000000001p-1022"`; đây là cùng giá trị với literal ngắn `0x1p-1074`. Chữ `0` dẫn trước dấu chấm biểu thị subnormal khi API định dạng theo exponent thấp nhất của normal.

## 12. Ví dụ Java 17+ biên dịch và chạy độc lập

Tạo tệp **`FloatingPointLimitsDemo.java`**:

```java
public class FloatingPointLimitsDemo {
    public static void main(String[] args) {
        System.out.println("Float.MIN_VALUE = " + Float.MIN_VALUE);
        System.out.println("Float.MIN_NORMAL = " + Float.MIN_NORMAL);
        System.out.println("Float.MAX_VALUE = " + Float.MAX_VALUE);

        System.out.println("Double.MIN_VALUE = " + Double.MIN_VALUE);
        System.out.println("Double.MIN_NORMAL = " + Double.MIN_NORMAL);
        System.out.println("Double.MAX_VALUE = " + Double.MAX_VALUE);

        System.out.println("Double.MIN_VALUE > 0 = "
                + (Double.MIN_VALUE > 0.0));
        System.out.println("Double.MIN_VALUE < Double.MIN_NORMAL = "
                + (Double.MIN_VALUE < Double.MIN_NORMAL));
        System.out.println("-MAX finite = "
                + Double.isFinite(-Double.MAX_VALUE));

        double subnormal = Double.MIN_NORMAL / 2.0;
        double zero = Double.MIN_VALUE / 2.0;
        double infinity = Double.MAX_VALUE * 2.0;

        System.out.println("normal / 2 is subnormal = "
                + (subnormal > 0.0 && subnormal < Double.MIN_NORMAL));
        System.out.println("MIN_VALUE / 2 = " + zero);
        System.out.println("MAX_VALUE * 2 = " + infinity);
        System.out.println("nextUp(0) = " + Math.nextUp(0.0));
        System.out.println("nextUp(MAX_VALUE) = "
                + Math.nextUp(Double.MAX_VALUE));

        System.out.println("float raw MIN_NORMAL = "
                + String.format("%08x",
                        Float.floatToRawIntBits(Float.MIN_NORMAL)));
        System.out.println("double raw MIN_VALUE = "
                + String.format("%016x",
                        Double.doubleToRawLongBits(Double.MIN_VALUE)));
        System.out.println("double MIN_VALUE hex = "
                + Double.toHexString(Double.MIN_VALUE));

        System.out.println("+0 == -0 = " + (0.0 == -0.0));
        System.out.println("1 / -0 = " + (1.0 / -0.0));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingPointLimitsDemo.java
java FloatingPointLimitsDemo
```

**Stdout dự kiến trong Java 17+:**

```text
Float.MIN_VALUE = 1.4E-45
Float.MIN_NORMAL = 1.17549435E-38
Float.MAX_VALUE = 3.4028235E38
Double.MIN_VALUE = 4.9E-324
Double.MIN_NORMAL = 2.2250738585072014E-308
Double.MAX_VALUE = 1.7976931348623157E308
Double.MIN_VALUE > 0 = true
Double.MIN_VALUE < Double.MIN_NORMAL = true
-MAX finite = true
normal / 2 is subnormal = true
MIN_VALUE / 2 = 0.0
MAX_VALUE * 2 = Infinity
nextUp(0) = 4.9E-324
nextUp(MAX_VALUE) = Infinity
float raw MIN_NORMAL = 00800000
double raw MIN_VALUE = 0000000000000001
double MIN_VALUE hex = 0x0.0000000000001p-1022
+0 == -0 = true
1 / -0 = -Infinity
```

Điểm quan sát:

1. Cả `Float.MIN_VALUE` và `Double.MIN_VALUE` đều dương, rất nhỏ và **nhỏ hơn `MIN_NORMAL`**.
2. Chia `MIN_NORMAL` cho 2 vẫn còn một số dương hữu hạn, nằm trong miền subnormal.
3. Chia `MIN_VALUE` cho 2 tạo số 0 vì underflow/làm tròn.
4. Nhân `MAX_VALUE` với 2 thành vô cực vì overflow.
5. Các hex raw bits xác nhận khác biệt exponent/fraction; `toHexString` cho biểu diễn giá trị dấu phẩy động.

## 13. Nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`Double.MIN_VALUE` là số âm nhỏ nhất” | Đây là số **dương khác 0 nhỏ nhất**; số âm hữu hạn có trị tuyệt đối lớn nhất là `-Double.MAX_VALUE` |
| “`MIN_NORMAL` và `MIN_VALUE` giống nhau” | `MIN_VALUE` là subnormal nhỏ nhất; `MIN_NORMAL` là normal nhỏ nhất |
| “Nhỏ hơn `MIN_NORMAL` là số 0” | Vẫn có nhiều số subnormal khác 0 |
| “Mọi giá trị nhỏ hơn `MIN_VALUE` đều bị từ chối khi chạy” | Phép toán có thể underflow và làm tròn thành 0; mặc định không ném ngoại lệ |
| “`MAX_VALUE` là Infinity” | `MAX_VALUE` còn hữu hạn; phép toán vượt biên có thể thành Infinity |
| “`MIN_VALUE` là epsilon để so sánh xấp xỉ” | Đây chỉ là độ lớn subnormal nhỏ nhất, quá nhỏ cho nhiều so sánh thực tế |
| “Toán tử `==` phân biệt `+0.0` và `-0.0`” | `+0.0 == -0.0` là true, dù raw bits và phép chia cho zero có thể khác |
| “`Double.toHexString` trả raw bits” | Nó trả phần trị hex và số mũ nhị phân của **giá trị**, khác bit field |
| “Subnormal giữ độ chính xác tương đối giống normal” | Số bit có nghĩa hiệu dụng giảm khi tiến sát 0 |
| “Dùng `Double.MIN_VALUE` để từ chối NaN” | NaN cần `Double.isNaN`; dùng `Double.isFinite` khi cần số hữu hạn |
| “`Float.MIN_VALUE` luôn nhỏ hơn `Double.MIN_VALUE` vì float ít bit hơn” | Ngược lại về **độ lớn**, `Float.MIN_VALUE` lớn hơn rất nhiều so với `Double.MIN_VALUE` |

## 14. Bài tập có lời giải

**Bài 1.** Hằng nào nhỏ hơn 0: `Double.MIN_VALUE` hay `-Double.MAX_VALUE`?  
**Lời giải:** chỉ `-Double.MAX_VALUE` nhỏ hơn 0. `Double.MIN_VALUE > 0`.

**Bài 2.** `Double.MIN_NORMAL / 2.0` có bằng 0 không?  
**Lời giải:** không; đây là một số dương **subnormal** biểu diễn được, nhỏ hơn `MIN_NORMAL`.

**Bài 3.** Viết dạng lũy thừa của 2 cho `Float.MIN_VALUE` và `Float.MIN_NORMAL`.  
**Lời giải:** lần lượt `2^-149` và `2^-126`. Chúng cách nhau rất nhiều bậc lũy thừa dù đều nhỏ.

**Bài 4.** Giá trị của `Math.nextUp(0.0)` là gì?  
**Lời giải:** `Double.MIN_VALUE`, số dương có thể biểu diễn ngay sau 0.

**Bài 5.** `Double.MAX_VALUE * 2.0` in gì?  
**Lời giải:** `Infinity` do overflow, không phải exception.

**Bài 6.** `Double.MIN_VALUE / 2.0` ra gì?  
**Lời giải:** `+0.0` vì kết quả quá nhỏ để biểu diễn dưới mặc định làm tròn về gần nhất; ngay tại nửa bước nhỏ nhất, quy tắc *ties to even* chọn 0.

**Bài 7.** Giá trị `double x = 1e-320;` là normal hay subnormal?  
**Lời giải:** là **subnormal dương**: vẫn lớn hơn `Double.MIN_VALUE` nhưng nhỏ hơn `Double.MIN_NORMAL ≈ 2.225e-308`.

**Bài 8.** `Float.MIN_VALUE` và `Double.MIN_VALUE`: hằng nào biểu diễn giá trị nhỏ hơn về độ lớn?  
**Lời giải:** `Double.MIN_VALUE` nhỏ hơn vì `2^-1074 < 2^-149`. Nhưng cả hai đều là những giá trị dương khác 0 nhỏ nhất **trong kiểu tương ứng**.

## 15. Checklist khi xử lý biên dấu phẩy động

1. **Chọn đúng khái niệm:** đang cần số dương khác 0 nhỏ nhất (`MIN_VALUE`), số normal nhỏ nhất (`MIN_NORMAL`) hay số hữu hạn lớn nhất (`MAX_VALUE`)?
2. **Không nhầm với số nguyên:** `Integer.MIN_VALUE` là âm, còn `Double.MIN_VALUE` là dương.
3. **Kiểm tra miền hữu hạn:** dùng `Double.isFinite(x)` hoặc `Float.isFinite(x)` nếu không muốn chấp nhận NaN/vô cực.
4. **Chú ý underflow:** phép tính có thể thành subnormal rồi ±0, không tự ném lỗi.
5. **Chú ý overflow:** phép toán có thể trả ±Infinity; kiểm tra kết quả nếu điều đó làm hỏng nghiệp vụ.
6. **Xác định nhu cầu chính xác:** subnormal có ít bit có nghĩa tương đối hơn; `Math.ulp`/`Math.nextUp` hữu ích để hiểu bước biểu diễn.
7. **Thiết kế so sánh:** không dùng `MIN_VALUE` làm epsilon chung; chọn dung sai từ bản chất dữ liệu.
8. **Nếu cần decimal exact:** `BigDecimal` từ chuỗi và quy tắc scale/rounding là một bài toán khác với miền IEEE 754 của `float`/`double`.

**Ghi nhớ:** Trong dấu phẩy động Java, `MIN_VALUE` là **số dương subnormal nhỏ nhất**, `MIN_NORMAL` là **số dương normal nhỏ nhất**, và `MAX_VALUE` là **số dương hữu hạn lớn nhất**. Ba hằng này mô tả ba biên khác nhau của biểu diễn IEEE 754; hiểu đúng chúng giúp kiểm soát underflow, overflow và độ chính xác gần số 0.
