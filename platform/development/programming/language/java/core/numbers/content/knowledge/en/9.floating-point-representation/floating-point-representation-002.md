# Bit dấu, phần mũ và phần trị trong biểu diễn dấu phẩy động Java

## 1. Mục tiêu: hiểu số `float`/`double` được lưu thế nào

`float` và `double` trong Java không lưu một số thập phân dưới dạng chuỗi chữ số như `"5.75"`. Chúng biểu diễn số theo dạng **dấu, phần mũ nhị phân và phần trị (significand)** với độ dài bit hữu hạn. Nắm được cấu trúc này giúp giải thích vì sao `0.1` không được biểu diễn chính xác, vì sao `-0.0` có thể khác `+0.0` ở mức bit, và vì sao một số phép tính cho `Infinity` hoặc `NaN`.

Bài này thuộc nhóm **Biểu diễn dấu phẩy động** của Java Core — Numbers. Sau khi học, bạn cần:

1. Chỉ được trường **sign**, **biased exponent** và **fraction field** trong một `float` 32 bit và `double` 64 bit.
2. Tính được phần mũ thực từ số mũ đã lưu bằng **bias 127** (binary32) hoặc **1023** (binary64).
3. Giải mã giá trị **normal** bằng bit `1` ngầm phía trước fraction; phân biệt với **subnormal** không có bit `1` ngầm.
4. Nhận diện đúng **±0.0**, **±Infinity**, **NaN** và ranh giới số hữu hạn.
5. Sử dụng `Float.floatToRawIntBits`, `Double.doubleToRawLongBits` và các bitmask để quan sát mẫu bit trong Java 17+.
6. Phân biệt **mẫu bit**, **giá trị toán học**, **cách in ra chuỗi** và **độ chính xác của phép tính**.

Kiến thức tiên quyết: nhị phân và lũy thừa 2, phép `&`, dịch phải `>>>`, literal hex `0x...`, kiểu `int`/`long` và `float`/`double`. Bài này dùng cấu trúc theo IEEE 754 binary32/binary64 và API Java SE 17.

## 2. Ba trường bit của một số dấu phẩy động

### 2.1. Tổng quan sơ đồ

**`float` (binary32)** có đúng 32 bit:

```text
bit index: 31 | 30................23 | 22..........................0
           S | E E E E E E E E    | F F F F F F F F F F F F F F F F F F F F F F F
width:     1 |        8           |                     23
```

**`double` (binary64)** có đúng 64 bit:

```text
bit index: 63 | 62................52 | 51...........................................0
           S  | E (11 bits)         | F (52 bits)
width:     1  |         11          |                    52
```

Trường `S` là **sign bit** (bit dấu); trường `E` là **stored/biased exponent** (mã số mũ); trường `F` là **fraction bits** hoặc **trailing significand field**. Thuật ngữ “mantissa” đôi khi được sử dụng trong tài liệu cũ, nhưng nên phân biệt rõ **fraction bits được lưu** với **significand thực** có thể bao gồm bit dẫn đầu ngầm định.

| Thuộc tính | `float` | `double` |
| --- | ---: | ---: |
| Độ dài toàn bộ | 32 bit | 64 bit |
| Bit dấu | 1 | 1 |
| Trường số mũ | 8 bit | 11 bit |
| Trường fraction | 23 bit | 52 bit |
| Bias | 127 | 1023 |
| Precision significand của số normal, kể cả bit đầu ngầm | 24 bit | 53 bit |
| Phần mũ không bias của số normal | −126 đến +127 | −1022 đến +1023 |
| Giá trị phần mũ lưu dành cho trường hợp đặc biệt | 0 và 255 | 0 và 2047 |

Dùng kiểu `int` để giữ toàn bộ bit của `float` và `long` để giữ toàn bộ bit của `double`. Nếu in những giá trị này theo **hệ 10 có dấu**, một mẫu bit có bit cao bật có thể trông thành số nguyên âm; muốn thấy rõ cấu trúc, hãy in hệ hex với độ rộng cố định.

### 2.2. Bit dấu có ý nghĩa gì?

Với các số hữu hạn khác 0 và vô cực:

- `S = 0` nghĩa là dấu dương;
- `S = 1` nghĩa là dấu âm.

Có thể hình dung hệ số dấu là `(-1)^S`. Ví dụ `+6.5` và `-6.5` có trường exponent/fraction giống nhau, nhưng bit dấu khác nhau.

**Lưu ý:** sign bit còn có trên `+0.0`, `-0.0` và các mẫu NaN. Không được coi dấu của NaN là “NaN âm có giá trị số âm” theo nghĩa so sánh số học thông thường; NaN không tham gia thứ tự số giống số hữu hạn.

## 3. Số normal: giải mã từ exponent và fraction

Khi trường số mũ lưu **không bằng 0 và cũng không toàn bit 1**, giá trị được gọi là **normal (normalized)**.

Công thức giá trị:

```text
normal = (-1)^S × (1 + F / 2^p) × 2^(E - bias)
```

Trong đó:

- `S`: bit dấu 0 hoặc 1.
- `E`: số nguyên không dấu thu được khi đọc toàn bộ trường exponent.
- `F`: số nguyên không dấu thu được khi đọc toàn bộ trường fraction.
- `p`: số bit fraction, bằng `23` với `float` và `52` với `double`.
- `bias`: `127` với `float`, `1023` với `double`.

**Ý nghĩa bit `1` ngầm:** với số normal, significand có dạng nhị phân `1.fraction_bits`. Bit `1` ở đầu không cần lưu trong trường fraction, giúp đạt 24 bit precision với 23 bit lưu ở `float`, hoặc 53 bit precision với 52 bit lưu ở `double`.

Ví dụ fraction nhị phân `0111000...` của `float` có nghĩa:

```text
1.0111₂ = 1 + 0/2 + 1/4 + 1/8 + 1/16 = 1.4375
```

Đừng đọc `E` là chính số mũ thật; phải **trừ bias**. Ví dụ `float` có `E = 129` thì số mũ thực là `129 - 127 = 2`. Với `double` có `E = 1025` thì số mũ thực là `1025 - 1023 = 2`.

### 3.1. Ví dụ giải mã `5.75f` từng bước

Đổi `5.75` sang nhị phân:

```text
5      = 101₂
0.75   = 0.11₂
5.75   = 101.11₂
       = 1.0111₂ × 2²
```

Trường sign bằng `0` vì số dương. Exponent thật `e = 2` nên exponent lưu của `float` là `2 + 127 = 129 = 10000001₂`. Fraction là các bit sau dấu chấm trong `1.0111₂`: `01110000000000000000000₂` (23 bit), bằng `0x380000`.

Ghép đủ 32 bit:

```text
sign       exponent       fraction
 0         10000001       01110000000000000000000
```

Chuỗi 32 bit bằng `0x40B80000`. Kiểm tra công thức:

```text
S = 0
E = 129
F / 2²³ = 0.4375
value = (+1) × (1 + 0.4375) × 2² = 5.75
```

Vì `0.75 = 3/4` có biểu diễn nhị phân hữu hạn, `5.75` được lưu chính xác ở đây.

### 3.2. Ví dụ giải mã `-6.5` ở kiểu `double`

`6.5 = 110.1₂ = 1.101₂ × 2²`.

- Sign `S = 1`.
- Unbiased exponent `e = 2`.
- Stored exponent `E = 2 + 1023 = 1025`.
- Fraction `.101₂ = 1/2 + 1/8 = 0.625`; 52 bit fraction tương đương số hex `0xA000000000000`.
- Toàn bộ mẫu bit `double`: `0xC01A000000000000`.

Kiểm tra: `(-1) × (1 + 0.625) × 4 = -6.5`.

## 4. Số exponent lưu không dùng tất cả các mã cho normal

Các trường số mũ `E = 0` và `E = toàn bit 1` được dành cho các ý nghĩa đặc biệt:

| Trường exponent | Trường fraction | Phân loại | Diễn giải |
| --- | --- | --- | --- |
| `0 < E < EmaxStored` | Bất kỳ | Normal | `1.fraction × 2^(E − bias)` với dấu |
| `E = 0` | `F = 0` | Zero | `+0.0` hay `-0.0` tùy sign |
| `E = 0` | `F != 0` | Subnormal | `0.fraction × 2^(1 − bias)` với dấu |
| `E = EmaxStored` | `F = 0` | Infinity | `+∞` hay `−∞` tùy sign |
| `E = EmaxStored` | `F != 0` | NaN | “Not a Number”, không phải một số có thứ tự |

Với `float`, `EmaxStored = 255`; với `double`, `EmaxStored = 2047`. Không nên nhầm **giá trị E lưu tối đa** với **unbiased normal exponent tối đa** (`127` hay `1023`).

Cũng không đúng khi nói “exponent 0 luôn là 2⁻¹²⁷” rồi thay vào công thức normal: khi `E=0`, cả số zero và subnormal dùng quy tắc riêng, được trình bày tiếp theo.

## 5. Subnormal: số quá nhỏ để biểu diễn ở dạng normal

Số **subnormal** (trước đây còn gọi denormal) dùng `E = 0` và `F != 0`. Nó không có bit `1` ngầm dẫn đầu; significand được hiểu là `0.fraction_bits`.

Công thức:

```text
subnormal = (-1)^S × (F / 2^p) × 2^(1 - bias)
```

Với `float`, `1 - bias = -126`; với `double` là `-1022`.

Tại sao cần subnormal? Giữa số normal dương nhỏ nhất và `+0.0` vẫn còn nhiều giá trị số dương có thể biểu diễn dưới dạng subnormal. Đây là cơ chế **gradual underflow** — độ chính xác giảm dần khi tiến gần zero, thay vì lập tức chuyển từ normal nhỏ nhất sang zero.

### 5.1. Các mốc `float`

- `Float.MIN_NORMAL` = `2⁻¹²⁶`, là **normal dương nhỏ nhất**: bit `0x00800000`.
- `Float.MIN_VALUE` = `2⁻¹⁴⁹`, là **subnormal dương nhỏ nhất**: bit `0x00000001`.
- Subnormal dương lớn nhất có bit `0x007FFFFF` và nằm ngay dưới `Float.MIN_NORMAL`.

**Tên `MIN_VALUE` dễ gây hiểu nhầm:** nó là giá trị **dương khác 0 nhỏ nhất**, không phải số âm nhỏ nhất; với số âm hữu hạn lớn về độ lớn, xem `-Float.MAX_VALUE`.

### 5.2. Các mốc `double`

- `Double.MIN_NORMAL` = `2⁻¹⁰²²`; bit `0x0010000000000000`.
- `Double.MIN_VALUE` = `2⁻¹⁰⁷⁴`; bit `0x0000000000000001`.
- Subnormal dương lớn nhất: `0x000FFFFFFFFFFFFF`.

**Điểm then chốt:** `MIN_NORMAL` và `MIN_VALUE` khác rất xa nhau về độ lớn; việc chỉ nhớ “double chính xác 15 chữ số” không đủ để hiểu underflow. Độ chính xác tương đối của subnormal kém hơn nhiều so với số normal, nhưng chúng vẫn biểu diễn đúng những mức rời rạc trong miền rất nhỏ.

### 5.3. Tính giá trị của subnormal nhỏ nhất

Với `float`, chọn `S=0`, `E=0`, `F=1`. Theo công thức:

```text
value = (1 / 2²³) × 2⁻¹²⁶
      = 2⁻¹⁴⁹
      = Float.MIN_VALUE
```

Không dùng `(1 + F / 2²³)` như với normal. Nếu có thêm bit `1` ngầm, giá trị sẽ không đúng tại `E = 0`.

## 6. Zero có bit dấu: `+0.0` và `-0.0`

Trong binary32:

```text
+0.0f = 0x00000000
-0.0f = 0x80000000
```

Trong binary64:

```text
+0.0  = 0x0000000000000000
-0.0  = 0x8000000000000000
```

Cả hai đều có `E = 0`, `F = 0`; chỉ khác `S`.

Trong phép so sánh số học:

```java
System.out.println(0.0 == -0.0); // true
```

Nhưng chúng vẫn là **hai mẫu bit khác nhau** và có thể tác động khác nhau tới một số phép toán:

```java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Vì vậy, cần xác định bạn đang so sánh **giá trị số**, **mẫu bit** hay **thứ tự toàn phần của wrapper**. `Double.compare(0.0, -0.0)` có kết quả dương (nó phân biệt dấu zero), trong khi `0.0 == -0.0` là `true`. Điều này không phải mâu thuẫn mà là hợp đồng so sánh khác nhau.

## 7. Infinity và NaN: khi exponent toàn bit 1

### 7.1. Vô cực

Với `float`, `E=255`, `F=0`:

```text
+Infinity  0x7F800000
-Infinity  0xFF800000
```

Với `double`, `E=2047`, `F=0`:

```text
+Infinity  0x7FF0000000000000
-Infinity  0xFFF0000000000000
```

`Float.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` là các hằng số API. Phép chia số thực như `1.0 / 0.0` cho vô cực, khác với `int` chia `0` ném `ArithmeticException`.

### 7.2. NaN

Với `E` toàn bit 1 **và** `F != 0`, mẫu bit biểu thị `NaN`.

- NaN có nhiều **bit pattern** khác nhau, không chỉ một chuỗi bit duy nhất.
- Sign bit có thể bằng 0 hoặc 1 nhưng không làm NaN trở thành một giá trị số âm/dương bình thường.
- `Double.NaN` và `Float.NaN` là hằng số có nghĩa NaN; không có primitive literal tên `NaN`.
- Theo phép so sánh floating-point `==`, `NaN == NaN` là `false`. Muốn kiểm tra, gọi `Float.isNaN` hoặc `Double.isNaN`.

`Float.floatToIntBits` và `Double.doubleToLongBits` **canonicalize NaN** khi xuất bit: các NaN được quy về một mẫu chuẩn (`0x7FC00000` cho `float` và `0x7FF8000000000000` cho `double`).

Nếu cần quan sát **raw bits** của NaN, dùng `Float.floatToRawIntBits` hoặc `Double.doubleToRawLongBits`. Tuy nhiên, một số NaN signaling có thể bị đổi thành quiet NaN khi truyền qua phần cứng hoặc phép toán; không nên hứa round trip bit tuyệt đối cho mọi payload NaN trên mọi nền tảng.

### 7.3. Phân loại chỉ từ E và F

Quy tắc phân loại có thể viết như sau:

```text
if E == 0:
    if F == 0: ZERO
    else:      SUBNORMAL
else if E == maximum exponent code:
    if F == 0: INFINITY
    else:      NaN
else:
    NORMAL
```

Đây là **pseudocode**, không phải Java độc lập. Ý nghĩa phụ thuộc đúng độ rộng trường exponent/fraction của `float` hay `double`.

## 8. Quan sát mẫu bit bằng Java thay vì đoán từ chuỗi

Các API chuẩn nên biết:

| Kiểu | Đọc bit | Dựng lại giá trị | Ghi chú |
| --- | --- | --- | --- |
| `float` | `Float.floatToRawIntBits(value)` | `Float.intBitsToFloat(bits)` | Trả/nhận `int` 32 bit |
| `float` | `Float.floatToIntBits(value)` | `Float.intBitsToFloat(bits)` | Chuẩn hóa NaN |
| `double` | `Double.doubleToRawLongBits(value)` | `Double.longBitsToDouble(bits)` | Trả/nhận `long` 64 bit |
| `double` | `Double.doubleToLongBits(value)` | `Double.longBitsToDouble(bits)` | Chuẩn hóa NaN |

**Không dùng cast primitive `(int) someFloat` để lấy bit!** Cast đó chuyển **giá trị số** sang số nguyên theo quy tắc narrowing, khác hoàn toàn việc tái diễn giải bit.

Ví dụ:

```java
float value = 5.75f;
int truncatedValue = (int) value;             // 5
int rawBits = Float.floatToRawIntBits(value); // 0x40B80000
```

Cùng một biến `float` nhưng hai giá trị `int` có nghĩa khác nhau: một số là kết quả chuyển giá trị, một số là **mã hóa bit**.

### 8.1. Ví dụ chạy được: tách sign/exponent/fraction của `float`

Lưu tệp **`FloatFields.java`**:

```java
public class FloatFields {
    public static void main(String[] args) {
        float value = 5.75f;
        int bits = Float.floatToRawIntBits(value);

        int sign = (bits >>> 31) & 1;
        int exponent = (bits >>> 23) & 0xFF;
        int fraction = bits & 0x7FFFFF;

        System.out.printf("%08X%n", bits);
        System.out.println(sign);
        System.out.println(exponent);
        System.out.printf("%06X%n", fraction);
        System.out.println(Float.intBitsToFloat(bits));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 FloatFields.java
java FloatFields
```

**Stdout chính xác:**

```text
40B80000
0
129
380000
5.75
```

Giải thích phép tách:

- `>>> 31` đưa bit dấu xuống cuối rồi `& 1` giữ một bit.
- `>>> 23` đưa 8 bit exponent về cuối rồi `& 0xFF` giữ đúng trường đó.
- `& 0x7FFFFF` giữ 23 bit fraction thấp.
- `printf("%08X%n", bits)` in 8 chữ số hex (32 bit); `%06X` in fraction tối thiểu 6 chữ số hex.
- `Float.intBitsToFloat(bits)` diễn giải lại đúng mẫu bit thành `5.75`.

Với `float`, dấu âm hay các mẫu NaN có thể khiến `bits` là số `int` âm khi đọc hệ 10. Đó là một **đặc điểm diễn giải số nguyên có dấu** của mẫu bit, không có nghĩa bản thân biến `float` bị ép về một giá trị nguyên âm có liên quan trực tiếp.

### 8.2. Ví dụ chạy được: tách trường của `double`

Lưu tệp **`DoubleFields.java`**:

```java
public class DoubleFields {
    public static void main(String[] args) {
        double value = -6.5;
        long bits = Double.doubleToRawLongBits(value);

        long sign = (bits >>> 63) & 1L;
        long exponent = (bits >>> 52) & 0x7FFL;
        long fraction = bits & 0x000F_FFFF_FFFF_FFFFL;

        System.out.printf("%016X%n", bits);
        System.out.println(sign);
        System.out.println(exponent);
        System.out.printf("%013X%n", fraction);
        System.out.println(Double.longBitsToDouble(bits));
    }
}
```

Chạy:

```bash
javac --release 17 DoubleFields.java
java DoubleFields
```

**Stdout chính xác:**

```text
C01A000000000000
1
1025
A000000000000
-6.5
```

Ở `double`, fraction có 52 bit = 13 chữ số hex; exponent 11 bit nên mask là `0x7FFL`. Tiền tố `L` của literal mask 64 bit thể hiện rõ phép toán `long`. Dù raw `bits` có dấu âm nếu đọc như `long`, dịch logic `>>>` và các mask vẫn trích đúng từng trường.

## 9. Ví dụ chạy được: các mẫu bit đặc biệt

Lưu thành **`SpecialFloatingBits.java`**:

```java
public class SpecialFloatingBits {
    public static void main(String[] args) {
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(-0.0f));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.MIN_VALUE));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.MIN_NORMAL));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.POSITIVE_INFINITY));

        System.out.printf("%016X%n",
                Double.doubleToRawLongBits(-0.0));
        System.out.println(0.0 == -0.0);
        System.out.println(Double.isNaN(0.0 / 0.0));
        System.out.println(Double.isInfinite(1.0 / 0.0));
        System.out.printf("%08X%n",
                Float.floatToIntBits(Float.intBitsToFloat(0x7FC01234)));
    }
}
```

Chạy:

```bash
javac --release 17 SpecialFloatingBits.java
java SpecialFloatingBits
```

**Stdout chính xác:**

```text
80000000
00000001
00800000
7F800000
8000000000000000
true
true
true
7FC00000
```

Bốn dòng `float` đầu là **−0.0**, **subnormal dương nhỏ nhất**, **normal dương nhỏ nhất**, **+Infinity**. Mẫu `double` tiếp theo là **−0.0**. Hai giá trị zero có so sánh `==` bằng nhau dù bit khác. Phép chia `0.0/0.0` tạo NaN; `1.0/0.0` tạo vô cực. Dòng cuối cho thấy `Float.floatToIntBits` quy nhiều bit pattern NaN về `0x7FC00000`.

Mã dùng `Float.intBitsToFloat(0x7FC01234)` để tạo một NaN theo bit; tránh diễn giải số nguyên `0x7FC01234` như một giá trị thập phân thực thông qua cast.

## 10. Precision: tại sao fraction field không đồng nghĩa đủ chữ số thập phân

Với số normal:

- `float`: **24 bit** precision cho significand (23 bit fraction lưu + 1 bit `1` ngầm).
- `double`: **53 bit** precision (52 bit fraction + 1 bit `1` ngầm).

Nghĩa là `float` phân biệt mọi số nguyên trong khoảng từ `-2²⁴` đến `+2²⁴` nếu chúng biểu diễn được chính xác; riêng `2²⁴ + 1` không có biểu diễn float khác `2²⁴` khi làm tròn theo round-to-nearest, ties-to-even. Tương tự, `double` biểu diễn chính xác mọi số nguyên có độ lớn đến `2⁵³`, nhưng không giữ tất cả các số nguyên lớn hơn mốc đó.

Ví dụ tự kiểm chứng:

```java
int bigFloatInt = 16_777_216; // 2^24
boolean floatEqual = (float) bigFloatInt
        == (float) (bigFloatInt + 1); // true

long bigDoubleLong = 9_007_199_254_740_992L; // 2^53
boolean doubleEqual = (double) bigDoubleLong
        == (double) (bigDoubleLong + 1); // true
```

Điều này không nói rằng `float` chỉ lưu được giá trị đến `2²⁴` hoặc `double` chỉ đến `2⁵³`: miền độ lớn của chúng còn rộng hơn nhiều nhờ exponent. Chỉ là **khoảng cách giữa các số biểu diễn được tăng lên khi exponent tăng**. Vì vậy:

- Trường exponent chủ yếu quyết định **thang độ lớn**.
- Trường significand/fraction quyết định **bước nhảy và độ chính xác tương đối** trong mỗi binade.
- Với số subnormal, precision tương đối giảm dần khi tiến tới 0.

### 10.1. Vì sao `0.1` bị làm tròn?

`0.1₁₀` có biểu diễn nhị phân vô hạn tuần hoàn. Vì số bit fraction hữu hạn, `float`/`double` lưu giá trị gần đúng sau khi làm tròn:

```java
double x = 0.1 + 0.2;
System.out.println(x);        // 0.30000000000000004
System.out.println(x == 0.3); // false
```

Đây là hệ quả cấu trúc sign/exponent/significand, không phải lỗi `println`. Nếu bài toán cần **thập phân chính xác theo nghiệp vụ** (ví dụ tiền tệ), cân nhắc `BigDecimal` khởi tạo từ chuỗi và quy tắc làm tròn rõ ràng; `BigDecimal` không dùng cấu trúc binary32/binary64 giống `float`/`double`.

### 10.2. Khoảng cách giữa số liên tiếp (ULP)

`Math.ulp(x)` trả về kích thước một **unit in the last place** của đối số ở định dạng floating point tương ứng. Ở gần `1.0f`, bước lên số float tiếp theo là `2⁻²³`; ở gần `1.0` kiểu `double`, bước lên thường là `2⁻⁵²`. Nhưng tại lân cận mốc lũy thừa 2, khoảng cách ở phía dưới có thể khác phía trên; không nên coi một epsilon cố định là đúng cho mọi thang giá trị.

`Math.nextUp(x)`/`Math.nextDown(x)` có thể dùng khi cần duyệt số floating-point biểu diễn kế cận. Chúng hữu ích cho kiểm thử ranh giới, nhưng không thay thế việc lựa chọn tiêu chí sai số phù hợp bài toán.

## 11. Từ hex floating-point literal quay lại ba trường bit

Java hỗ trợ literal có dạng `0x...p...`, trong đó `p` đánh dấu **số mũ cơ số 2**. Ví dụ:

```java
float a = 0x1.7p2f;    // 1.4375 × 2² = 5.75
double b = -0x1.ap2;   // -(1.625 × 2²) = -6.5
```

`0x1.7p2` có ý nghĩa số học trực tiếp gần với dạng normalized binary `1.0111₂ × 2²`. Có thể đối chiếu literal hex với `Float.toHexString` hoặc `Double.toHexString` khi cần đọc significand/exponent theo lũy thừa 2:

```java
System.out.println(Float.toHexString(5.75f)); // 0x1.7p2
System.out.println(Double.toHexString(-6.5)); // -0x1.ap2
```

**Quan trọng:** chuỗi do `toHexString` tạo ra là **biểu diễn giá trị**, không phải bản in trực tiếp từng trường raw bits. Với số subnormal, `toHexString` dùng cách thể hiện thích hợp cho miền dưới normal; muốn quan sát từng bit exponent/fraction, dùng API raw-bits và mask ở trên.

## 12. Phân biệt cấu trúc IEEE 754 với thứ tự byte trong bộ nhớ

Một `float` được định nghĩa có 32 bit giá trị; điều này không tự nói rằng bốn byte của nó xuất hiện theo thứ tự nào trong một file, gói tin hoặc `ByteBuffer`.

- **Bit layout** nói bit nào là sign/exponent/fraction khi xét mẫu 32/64 bit theo chỉ số.
- **Endianness** nói thứ tự các **byte** khi lưu cùng mẫu bit vào bộ nhớ/chuỗi byte. Big-endian và little-endian có thể cho thứ tự byte khác nhau, dù các trường dấu/phần mũ/phần trị của giá trị không thay đổi.
- `ByteBuffer` có chính sách byte order và có thể thiết lập qua `order(ByteOrder.BIG_ENDIAN)` hay `LITTLE_ENDIAN`.

Ví dụ mẫu `5.75f` là `0x40B80000`. Khi ghi 4 byte:

```text
big-endian:    40 B8 00 00
little-endian: 00 00 B8 40
```

Đây là ví dụ **thứ tự byte của cùng một mẫu bit**, không phải hai giá trị floating-point khác nhau. Khi trao đổi dữ liệu giữa các hệ thống, hợp đồng phải quy định cả định dạng số và byte order.

## 13. Những ngộ nhận và lỗi phổ biến

1. **“Fraction 23 bit nghĩa là float có 23 bit precision.”** Với normal, còn bit `1` ngầm, nên precision significand là **24 bit**.
2. **“Exponent lưu là exponent thật.”** Phải trừ **bias** cho normal; `E = 129` của float tương ứng `e = 2`.
3. **“Exponent 0 là một normal có số mũ -127.”** Sai. `E=0` được dành cho zero/subnormal và dùng công thức riêng với `1-bias`.
4. **“`Float.MIN_VALUE` là số âm nhỏ nhất.”** Sai. Đó là **số dương khác 0 nhỏ nhất**, một subnormal.
5. **“`~` hoặc cast `(int)` lấy đúng bit của số thực.”** Sai. Cast chuyển giá trị, không đọc bit encoding; dùng `Float.floatToRawIntBits`/`Double.doubleToRawLongBits`.
6. **“`-0.0` và `+0.0` giống hệt mọi thứ.”** Chúng bằng nhau khi so sánh `==`, nhưng có bit sign khác nhau và có thể dẫn tới dấu vô cực khác nhau khi chia.
7. **“Mỗi NaN luôn cùng một mẫu bit.”** Có nhiều NaN patterns; API `floatToIntBits`/`doubleToLongBits` sẽ canonicalize.
8. **“`0.1` được lưu chính xác do có nhiều chữ số thập phân hiển thị.”** Binary finite significand không thể biểu diễn chính xác 1/10; chuỗi hiển thị là lớp trình bày.
9. **“Exponent là số chữ số sau dấu chấm.”** Đây là lũy thừa **cơ số 2**, hoàn toàn khác scale thập phân của `BigDecimal`.
10. **“Bit layout quyết định byte order.”** Không. Cần quy định endianness nếu tuần tự hóa byte.
11. **“Số có bit sign bằng 1 luôn là số âm hữu hạn.”** Mẫu đó có thể là `-0.0`, `-Infinity` hoặc NaN.
12. **“Dạng normal và subnormal có cùng bit dẫn đầu ngầm.”** Với subnormal, significand là `0.fraction`, không phải `1.fraction`.

## 14. Bài luyện tập có đáp án

### Bài 1 — Vị trí từng trường

Hãy cho biết bit dấu, số bit exponent và số bit fraction của `float` và `double`.

**Đáp án:** `float` gồm `1 + 8 + 23 = 32` bit; `double` gồm `1 + 11 + 52 = 64` bit.

### Bài 2 — Bias

Với normal `float` có `E=130`, số mũ thật là bao nhiêu? Với normal `double` có `E=1025` thì sao?

**Đáp án:** `130−127=3` và `1025−1023=2`. Phải trừ bias tương ứng.

### Bài 3 — Giải mã `5.75f`

Biết mẫu bit là `0x40B80000`. Tách `S`, `E` và `F`, rồi tính lại giá trị.

**Đáp án:** `S=0`, `E=129`, `F=0x380000`. Fraction = `0.4375`; giá trị = `(1+0.4375)×2²=5.75`.

### Bài 4 — Phân biệt 0 và subnormal

Hai mẫu `0x00000000` và `0x00000001` (float) có cùng trường exponent. Chúng có giống nhau không?

**Đáp án:** không. `E=0,F=0` là `+0.0`; `E=0,F=1` là subnormal dương nhỏ nhất `2⁻¹⁴⁹`.

### Bài 5 — Nhận diện vô cực và NaN

Với `float`, `E=255`, `F=0` biểu thị gì? `E=255`, `F=1` biểu thị gì?

**Đáp án:** trường hợp thứ nhất là vô cực với dấu quyết định ±; trường hợp thứ hai là NaN vì fraction khác 0. Không gán NaN vào thứ tự số học thường.

### Bài 6 — Dấu zero

Vì sao `0.0 == -0.0` là true nhưng `Double.doubleToRawLongBits(0.0)` và `Double.doubleToRawLongBits(-0.0)` khác nhau?

**Đáp án:** quan hệ `==` là so sánh floating-point theo giá trị; raw bit bao gồm bit dấu. Hai zero có sign bit khác nhau.

### Bài 7 — Cast hay raw bits?

Cho `float f=5.75f`. `(int)f` và `Float.floatToRawIntBits(f)` cho gì?

**Đáp án:** cast cho `5`; raw-bits cho mẫu `0x40B80000` (nếu in như `int` thập phân, là một số nguyên lớn). Chúng có mục đích khác nhau.

### Bài 8 — Decimal vs binary precision

Vì sao `0.1 + 0.2 == 0.3` là false khi dùng `double`?

**Đáp án:** 1/10 và 1/5 có biểu diễn nhị phân tuần hoàn, được làm tròn về tập giá trị binary64; tổng làm tròn không nhất thiết khớp với mẫu binary64 của literal 0.3.

### Bài 9 — Đổi endian

Mẫu `float` `0x40B80000` tương ứng 4 byte nào ở big-endian và little-endian?

**Đáp án:** `40 B8 00 00` và `00 00 B8 40`. Giá trị float không thay đổi; chỉ thứ tự byte.

### Bài 10 — Số nguyên lớn và khoảng cách biểu diễn

Tại sao `(float)16_777_216` có thể bằng `(float)16_777_217` dù hai số `int` khác nhau?

**Đáp án:** binary32 có 24 bit precision significand, không có đủ bit để phân biệt tất cả số nguyên ở thang lớn hơn `2²⁴`; giá trị kế tiếp có thể được làm tròn về cùng mẫu.

## 15. Checklist và tài liệu chuẩn

- [ ] Tôi xác định đúng **bit sign/exponent/fraction** cho binary32 và binary64.
- [ ] Tôi không nhầm trường fraction lưu với toàn bộ significand normal.
- [ ] Tôi biết bias `127` và `1023`, và giới hạn unbiased exponent normal.
- [ ] Tôi viết được công thức giải mã **normal** và **subnormal**.
- [ ] Tôi phân biệt được zero, subnormal, normal, vô cực, NaN theo `E` và `F`.
- [ ] Tôi giải thích được `-0.0` khác `+0.0` ở raw bits, dù `==` là true.
- [ ] Tôi dùng được `floatToRawIntBits` và `doubleToRawLongBits`, không nhầm chúng với cast giá trị.
- [ ] Tôi hiểu NaN canonicalization và rủi ro round-trip signaling NaN.
- [ ] Tôi không suy luận độ chính xác từ số chữ số được `println` hiển thị.
- [ ] Tôi biết byte order là vấn đề riêng khi đọc/ghi các byte của mẫu bit.
- [ ] Tôi đã chạy ba chương trình và kiểm tra chính xác hex/giá trị đầu ra.

**Tài liệu chính thức cho Java 17:**

- [Java Language Specification, `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) — ngữ nghĩa floating point.
- [Java SE 17 Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) — bit layout, `floatToIntBits`, `floatToRawIntBits`, `intBitsToFloat`.
- [Java SE 17 Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) — `doubleToLongBits`, `doubleToRawLongBits`, `longBitsToDouble`.
- [Java SE 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) — `ulp`, `nextUp`, `nextDown`.
- [Java SE 17 ByteBuffer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — byte order và thao tác với dữ liệu nhị phân.

Cách đọc hiệu quả một số `float`/`double` là: **đọc sign, giải mã exponent, chọn công thức normal/subnormal hoặc nhận diện trường hợp đặc biệt, rồi diễn giải fraction theo cơ số 2**. Khi đã hiểu các trường này, nhiều hiện tượng “lạ” của số thực trở thành hệ quả có thể giải thích và kiểm chứng được.