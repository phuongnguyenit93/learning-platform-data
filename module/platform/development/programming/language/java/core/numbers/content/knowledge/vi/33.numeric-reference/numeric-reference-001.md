# Bảng kích thước, miền giá trị và hằng của kiểu số trong Java

## 1. Phạm vi và cách dùng bảng tra cứu

Trong Java, kích thước và miền giá trị của **kiểu nguyên thủy** (*primitive type*) được đặc tả bởi ngôn ngữ, không thay đổi chỉ vì chạy trên Windows/Linux, JVM 32-bit/64-bit hay phần cứng khác. Khi cần tra cứu nhanh một giới hạn, nên dùng **hằng của lớp wrapper** như `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Double.MAX_VALUE` thay vì tự nhập lại con số dài.

Bài này tổng hợp:

- Các kiểu nguyên thủy biểu diễn giá trị số: `byte`, `short`, `int`, `long`, `float`, `double`; đồng thời giải thích `char` — kiểu tích phân không dấu 16-bit dùng cho **đơn vị mã UTF-16**.
- Số bit, số byte, giới hạn biểu diễn, giá trị nhỏ nhất/lớn nhất và hằng tiêu chuẩn từ các lớp wrapper.
- Khác biệt giữa số nguyên chính xác và dấu phẩy động gần đúng; các hằng `MIN_VALUE`, `MIN_NORMAL`, `MAX_EXPONENT`, `NaN`, `Infinity`.
- Vị trí của `BigInteger` và `BigDecimal` khi không có cận min/max cố định, cùng cách xem `precision()`, `scale()` và hằng thường dùng.
- Ví dụ Java 17+ có thể biên dịch và chạy để xác minh bảng bằng chính API thay vì ghi nhớ.

**Quy ước:** 1 byte trong các hằng `BYTES` ở đây là 8 bit. Bảng nói về **biểu diễn giá trị của kiểu**, không phải lượng RAM chiếm bởi một object wrapper, một mảng, một field trong object, hoặc một collection. Bộ nhớ thực tế còn có header, alignment, tham chiếu, cấu trúc dữ liệu và tối ưu JVM.

`boolean` không phải kiểu số; Java không quy định `boolean` có kích thước lưu trữ cố định theo cách áp dụng cho các kiểu số trong bảng dưới. Vì vậy không đưa `boolean` vào bảng số. `char` không phải loại dữ liệu số thường dùng để tính tiền/đếm nhưng là kiểu tích phân và có thể tham gia phép toán số thông qua numeric promotion; do đó được nêu riêng.

## 2. Bảng kiểu nguyên và char: kích thước, miền giá trị

| Kiểu Java | Bit | Byte | Có dấu? | Miền giá trị | Hằng lấy cận |
|---|---:|---:|---|---|---|
| `byte` | 8 | 1 | Có | `-128` đến `127` | `Byte.MIN_VALUE`, `Byte.MAX_VALUE` |
| `short` | 16 | 2 | Có | `-32768` đến `32767` | `Short.MIN_VALUE`, `Short.MAX_VALUE` |
| `int` | 32 | 4 | Có | `-2147483648` đến `2147483647` | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` |
| `long` | 64 | 8 | Có | `-9223372036854775808` đến `9223372036854775807` | `Long.MIN_VALUE`, `Long.MAX_VALUE` |
| `char` | 16 | 2 | Không dấu | `0` đến `65535`, tức `U+0000`–`U+FFFF` theo giá trị đơn vị mã | `Character.MIN_VALUE`, `Character.MAX_VALUE` |

Đối với `byte`, `short`, `int`, `long`, số có dấu dùng **two's complement (bù hai)**. Nếu kiểu có \(n\) bit, miền là:

\[
-2^{n-1} \le x \le 2^{n-1}-1.
\]

Ví dụ `int` có 32 bit nên miền là \(-2^{31}\) đến \(2^{31}-1\). Số âm nhỏ nhất có trị tuyệt đối lớn hơn số dương lớn nhất đúng 1 đơn vị. Do đó `Math.abs(Integer.MIN_VALUE)` vẫn âm vì `2147483648` không thể biểu diễn bằng `int`; điều này cần chú ý khi viết kiểm tra trị tuyệt đối.

Riêng `char` là giá trị nguyên không dấu trong đoạn \(0\) đến \(2^{16}-1\). Java dùng `char` để biểu diễn **một UTF-16 code unit**, **không bảo đảm một `char` là toàn bộ một ký tự Unicode**. Những ký tự ngoài BMP dùng hai code unit (*surrogate pair*), vì vậy xử lý ký tự Unicode đầy đủ có thể cần `String.codePoints()`, `Character.codePointAt(...)` và kiểu `int` cho code point.

### Hằng kích thước tương ứng

| Kiểu | Hằng số bit | Giá trị | Hằng số byte | Giá trị |
|---|---|---:|---|---:|
| `byte` | `Byte.SIZE` | `8` | `Byte.BYTES` | `1` |
| `short` | `Short.SIZE` | `16` | `Short.BYTES` | `2` |
| `int` | `Integer.SIZE` | `32` | `Integer.BYTES` | `4` |
| `long` | `Long.SIZE` | `64` | `Long.BYTES` | `8` |
| `char` | `Character.SIZE` | `16` | `Character.BYTES` | `2` |

Các trường `SIZE`, `BYTES` là hằng `static final` của lớp wrapper tương ứng. Ví dụ dùng `Integer.SIZE` thay vì nhập cứng `32` trong code kiểm tra độ rộng bit giúp làm rõ ý nghĩa, dù giá trị Java đã cố định.

### Dạng cơ số 16 để nhận diện cận và bit dấu

| Kiểu | Cận dương lớn nhất (hex) | Cận âm nhỏ nhất (hex, mẫu bù hai) |
|---|---|---|
| `byte` | `0x7F` | `0x80` |
| `short` | `0x7FFF` | `0x8000` |
| `int` | `0x7FFFFFFF` | `0x80000000` |
| `long` | `0x7FFFFFFFFFFFFFFF` | `0x8000000000000000` |

Các giá trị ở cột hex âm là **mẫu bit** của cận âm, không phải phép viết số dương bằng literal hex có ý nghĩa tùy tiện. Ví dụ `Integer.MIN_VALUE` có mẫu bit 32-bit là `0x80000000`. `Character.MAX_VALUE` tương ứng `0xFFFF` và không có bit dấu.

## 3. Số dấu phẩy động: float và double không có “mọi giá trị trong khoảng”

Java cung cấp hai kiểu số dấu phẩy động nhị phân theo IEEE 754:

| Thuộc tính | `float` | `double` |
|---|---|---|
| Kích thước | 32 bit = 4 byte | 64 bit = 8 byte |
| Bit dấu | 1 | 1 |
| Bit exponent lưu trữ | 8 | 11 |
| Bit fraction lưu trữ | 23 | 52 |
| Precision nhị phân hữu hiệu cho số chuẩn hóa | 24 bit | 53 bit |
| Độ chính xác thập phân xấp xỉ | khoảng 6–9 chữ số có nghĩa cho round-trip | khoảng 15–17 chữ số có nghĩa cho round-trip |
| Cận hữu hạn dương lớn nhất | `Float.MAX_VALUE` ≈ `3.4028235E38` | `Double.MAX_VALUE` ≈ `1.7976931348623157E308` |
| Cận hữu hạn âm thấp nhất | `-Float.MAX_VALUE` | `-Double.MAX_VALUE` |
| Số dương nhỏ nhất khác 0 | `Float.MIN_VALUE` = `1.4E-45` khi in với JDK 17 (JDK 19+ có thể in `1.1754944E-38`) | `Double.MIN_VALUE` = `4.9E-324` khi in mặc định |
| Số dương **normal** nhỏ nhất | `Float.MIN_NORMAL` = `1.17549435E-38` khi in mặc định | `Double.MIN_NORMAL` = `2.2250738585072014E-308` |
| `MIN_EXPONENT` của số normal | `-126` | `-1022` |
| `MAX_EXPONENT` của số normal | `127` | `1023` |

Các chuỗi ở bảng là **biểu diễn thập phân ngắn mà Java in** cho những hằng dấu phẩy động, không phải khai triển thập phân chính xác đầy đủ của các số nhị phân đó. Chẳng hạn `Float.MIN_NORMAL` có giá trị toán học nhị phân chính xác là \(2^{-126}\), trong khi `Float.toString` ở JDK 17 in `1.17549435E-38`. Từ JDK 19, thay đổi thuật toán chuyển số thực thành chuỗi có thể cho dạng ngắn hơn `1.1754944E-38`; giá trị nhị phân và bit của hằng số không đổi.

**Rất quan trọng:** khác với `Integer.MIN_VALUE`, `Float.MIN_VALUE` và `Double.MIN_VALUE` **không phải số âm nhỏ nhất**. Chúng là **số dương nhỏ nhất lớn hơn 0 và khác 0**, thuộc loại *subnormal*. Nếu cần cận dưới hữu hạn của các giá trị `float`/`double`, dùng `-Float.MAX_VALUE` và `-Double.MAX_VALUE`.

Các giá trị có thể biểu diễn được bằng `float` hoặc `double` là một **tập rời rạc**, không phải tất cả số thực trong đoạn từ cận âm tới cận dương. Khoảng cách giữa hai số biểu diễn được thay đổi tùy theo độ lớn; nhiều phân số thập phân như `0.1` không được lưu chính xác dưới dạng nhị phân.

### Normal, subnormal và exponent

- **Normal:** có phần significand chuẩn hóa, nhận precision hữu hiệu 24 bit (`float`) hoặc 53 bit (`double`).
- **Subnormal:** những giá trị rất gần 0, nhỏ hơn `MIN_NORMAL` về trị tuyệt đối; dùng cách mã hóa cho phép tiến dần xuống 0 với precision tương đối thấp hơn.
- **`MIN_EXPONENT` và `MAX_EXPONENT`:** liên quan đến exponent của **số hữu hạn normal**, không phải chỉ số mũ nhỏ/lớn nhất trong bất kỳ cách hiển thị thập phân nào. Đừng dùng chúng như ngưỡng toàn diện cho các chuỗi `E` hoặc cho subnormal.
- **Zero:** có hai mẫu bit `+0.0` và `-0.0`, cùng so sánh bằng nhau theo toán tử primitive `==`.
- **Infinity và NaN:** những giá trị IEEE 754 đặc biệt, không thuộc đoạn số hữu hạn.

### Hằng dành cho float và double

| Hằng `float` | Hằng `double` | Ý nghĩa |
|---|---|---|
| `Float.SIZE` | `Double.SIZE` | Số bit: 32 và 64 |
| `Float.BYTES` | `Double.BYTES` | Số byte: 4 và 8 |
| `Float.MIN_VALUE` | `Double.MIN_VALUE` | Số dương subnormal nhỏ nhất khác 0 |
| `Float.MIN_NORMAL` | `Double.MIN_NORMAL` | Số dương normal nhỏ nhất |
| `Float.MAX_VALUE` | `Double.MAX_VALUE` | Số dương hữu hạn lớn nhất |
| `Float.MIN_EXPONENT` | `Double.MIN_EXPONENT` | Số mũ nhị phân thấp nhất của normal |
| `Float.MAX_EXPONENT` | `Double.MAX_EXPONENT` | Số mũ nhị phân cao nhất của normal |
| `Float.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` | Dương vô cực |
| `Float.NEGATIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | Âm vô cực |
| `Float.NaN` | `Double.NaN` | Not-a-Number |

Có thể kiểm tra giá trị đặc biệt bằng `Float.isNaN(...)`, `Double.isNaN(...)`, `Float.isInfinite(...)`, `Double.isInfinite(...)` và `isFinite(...)` tương ứng. `NaN == NaN` là `false` theo toán tử `==`; không kiểm tra NaN bằng phép so sánh bằng trực tiếp.

Ví dụ, `Double.POSITIVE_INFINITY` **khác** `Double.MAX_VALUE`: hằng thứ nhất không hữu hạn, còn hằng thứ hai là số hữu hạn dương lớn nhất.

### Miền số nguyên biểu diễn chính xác trong float/double

- Mọi số nguyên trong đoạn từ \(-2^{24}\) tới \(2^{24}\), tức `-16_777_216` tới `16_777_216`, đều được `float` biểu diễn chính xác. Số `16_777_217` không được biểu diễn chính xác bằng `float` và có thể làm tròn về `16_777_216`.
- Mọi số nguyên trong đoạn từ \(-2^{53}\) tới \(2^{53}\), tức `-9_007_199_254_740_992L` tới `9_007_199_254_740_992L`, đều được `double` biểu diễn chính xác. Số `9_007_199_254_740_993L` không được biểu diễn chính xác khi ép sang `double`.

Những ngưỡng này không có nghĩa mọi số nguyên lớn hơn ngưỡng đều không biểu diễn được: chẳng hạn một số chẵn đủ lớn vẫn có thể biểu diễn chính xác, nhưng **không còn bảo đảm mọi số nguyên liên tiếp**.

## 4. Chương trình Java 17+ kiểm tra các hằng ngay trên JVM

Để tránh tự đoán giá trị các hằng, có thể chạy chương trình tra cứu sau. Đây là một chương trình độc lập, tên file khớp với tên `public class`.

Lưu file **`NumericTypeReference.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericTypeReference {
    public static void main(String[] args) {
        System.out.println("byte: " + Byte.SIZE + " bits, "
                + Byte.BYTES + " bytes; "
                + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short: " + Short.SIZE + " bits, "
                + Short.BYTES + " bytes; "
                + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int: " + Integer.SIZE + " bits, "
                + Integer.BYTES + " bytes; "
                + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long: " + Long.SIZE + " bits, "
                + Long.BYTES + " bytes; "
                + Long.MIN_VALUE + ".." + Long.MAX_VALUE);
        System.out.println("char: " + Character.SIZE + " bits, "
                + Character.BYTES + " bytes; "
                + (int) Character.MIN_VALUE + ".."
                + (int) Character.MAX_VALUE);

        System.out.println("float: " + Float.SIZE + " bits, "
                + Float.BYTES + " bytes");
        System.out.println("float MIN_VALUE: " + Float.MIN_VALUE);
        System.out.println("float MIN_NORMAL: " + Float.MIN_NORMAL);
        System.out.println("float MAX_VALUE: " + Float.MAX_VALUE);
        System.out.println("float MIN_EXPONENT / MAX_EXPONENT: "
                + Float.MIN_EXPONENT + " / " + Float.MAX_EXPONENT);

        System.out.println("double: " + Double.SIZE + " bits, "
                + Double.BYTES + " bytes");
        System.out.println("double MIN_VALUE: " + Double.MIN_VALUE);
        System.out.println("double MIN_NORMAL: " + Double.MIN_NORMAL);
        System.out.println("double MAX_VALUE: " + Double.MAX_VALUE);
        System.out.println("double MIN_EXPONENT / MAX_EXPONENT: "
                + Double.MIN_EXPONENT + " / " + Double.MAX_EXPONENT);

        System.out.println("float +infinity? "
                + Float.isInfinite(Float.POSITIVE_INFINITY));
        System.out.println("double NaN? "
                + Double.isNaN(Double.NaN));

        System.out.println("big constants: "
                + BigInteger.ZERO + ", " + BigInteger.ONE + ", "
                + BigInteger.TWO + ", " + BigInteger.TEN);
        System.out.println("decimal constants: "
                + BigDecimal.ZERO + ", " + BigDecimal.ONE + ", "
                + BigDecimal.TWO + ", " + BigDecimal.TEN);

        BigDecimal decimal = new BigDecimal("123.4500");
        System.out.println("BigDecimal precision/scale: "
                + decimal.precision() + "/" + decimal.scale());
        System.out.println("BigInteger digits for 10^40: "
                + BigInteger.TEN.pow(40).toString().length());

        System.out.println("float exact-int boundary: "
                + ((float) 16_777_217 == (float) 16_777_216));
        System.out.println("double exact-long boundary: "
                + ((double) 9_007_199_254_740_993L
                        == (double) 9_007_199_254_740_992L));
    }
}
```

Chạy:

```bash
javac NumericTypeReference.java
java NumericTypeReference
```

Kết quả tham khảo với JDK 17 (một số chuỗi float/double có thể khác trên JDK 19+):

```text
byte: 8 bits, 1 bytes; -128..127
short: 16 bits, 2 bytes; -32768..32767
int: 32 bits, 4 bytes; -2147483648..2147483647
long: 64 bits, 8 bytes; -9223372036854775808..9223372036854775807
char: 16 bits, 2 bytes; 0..65535
float: 32 bits, 4 bytes
float MIN_VALUE: 1.4E-45
float MIN_NORMAL: 1.17549435E-38
float MAX_VALUE: 3.4028235E38
float MIN_EXPONENT / MAX_EXPONENT: -126 / 127
double: 64 bits, 8 bytes
double MIN_VALUE: 4.9E-324
double MIN_NORMAL: 2.2250738585072014E-308
double MAX_VALUE: 1.7976931348623157E308
double MIN_EXPONENT / MAX_EXPONENT: -1022 / 1023
float +infinity? true
double NaN? true
big constants: 0, 1, 2, 10
decimal constants: 0, 1, 2, 10
BigDecimal precision/scale: 7/4
BigInteger digits for 10^40: 41
float exact-int boundary: true
double exact-long boundary: true
```

**Cách đọc các dòng chính:**

1. `Byte.SIZE`/`Byte.BYTES` cho `8`/`1`; tương tự với các kiểu khác. Đây là đặc tả giá trị, không phụ thuộc việc JVM 64-bit.
2. Dòng `char` ép hai hằng sang `int` để in ra **mã số** 0 và 65535; nếu in trực tiếp `Character.MIN_VALUE`/`MAX_VALUE`, chúng được diễn giải như ký tự và không cho một bảng số dễ đọc.
3. `Float.MIN_VALUE` và `Double.MIN_VALUE` được in là **số dương nhỏ**; `MIN_NORMAL` cho ngưỡng từ normal xuống subnormal.
4. `BigInteger.TEN.pow(40)` là \(10^{40}\), viết dạng thập phân có **41 chữ số**. Chương trình chỉ dùng số mũ nhỏ để minh họa, không khuyến khích gọi lũy thừa rất lớn mà không kiểm soát tài nguyên.
5. Các dòng `float exact-int boundary` và `double exact-long boundary` đều là `true`: hai số nguyên gần nhau khác giá trị chính xác có thể **trở nên bằng nhau sau khi ép sang floating point**. Kết quả này không phải `float`/`double` có phép so sánh đúng hơn; nó thể hiện **mất khả năng phân biệt hai số**.

Đây là đầu ra cố định của các hằng và phép toán được dùng. Các phương thức `Float.toString`/`Double.toString` của Java tạo biểu diễn thập phân đủ để đọc lại giá trị dấu phẩy động theo hợp đồng API; chúng không liệt kê toàn bộ chữ số thập phân của giá trị nhị phân chính xác.

## 5. BigInteger và BigDecimal: không có kích thước cố định như primitive

Hai lớp `java.math.BigInteger` và `java.math.BigDecimal` là **lớp tham chiếu bất biến** (*immutable reference classes*), không phải primitive. Chúng không có `SIZE`/`BYTES` mô tả số bit lưu trữ cố định tương ứng một giá trị số duy nhất, và không định nghĩa cặp `MIN_VALUE`/`MAX_VALUE` theo kiểu `Integer`.

| Thuộc tính | `BigInteger` | `BigDecimal` |
|---|---|---|
| Loại giá trị | Số nguyên có độ lớn tùy ý | Số thập phân có precision tùy ý |
| Cấu trúc khái niệm | Dữ liệu nguyên nhiều bit | Unscaled integer và `scale` |
| Kích thước bit cố định? | Không | Không, unscaled value có độ lớn tùy ý |
| Cận min/max cố định của giá trị? | Không có hằng cận kiểu primitive | Không có hằng cận kiểu primitive |
| Hằng hay dùng | `ZERO`, `ONE`, `TWO`, `TEN` | `ZERO`, `ONE`, `TWO`, `TEN` |
| Thuộc tính kích thước | `bitLength()`, biểu diễn cơ số tùy chọn | `precision()`, `scale()`, `unscaledValue()` |
| Khởi tạo an toàn cho số viết bằng thập phân | `new BigInteger("12345678901234567890")` | `new BigDecimal("123.4500")` |

`BigInteger.TWO` và `BigDecimal.TWO` có trong Java 17+. Cả hai lớp cũng có hằng `ZERO`, `ONE` và `TEN`. Không nhầm các hằng này với giới hạn miền giá trị: chúng là những **giá trị thường dùng**, không phải cận max/min.

### BigInteger

`BigInteger` không bị giới hạn vào 32 hoặc 64 bit. Ví dụ:

```java
BigInteger large = new BigInteger("9223372036854775808");
// Lớn hơn Long.MAX_VALUE đúng 1.

BigInteger value = BigInteger.TEN.pow(40);
System.out.println(value.toString().length()); // 41
System.out.println(value.signum());            // 1
```

`bitLength()` giúp hiểu độ lớn bit; `signum()` cho `-1`, `0` hoặc `1` theo dấu. Tuy nhiên, “tùy ý” không có nghĩa vô hạn: còn giới hạn bộ nhớ, CPU, độ dài mảng và cài đặt của thư viện. Trong hệ thống tiếp nhận dữ liệu bên ngoài, cần giới hạn số chữ số đầu vào và phép toán có thể phát sinh kết quả cực lớn.

### BigDecimal

`BigDecimal` biểu diễn giá trị bằng công thức:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}.
\]

Ví dụ `new BigDecimal("123.4500")` có unscaled value bằng `1234500`, `precision() == 7`, `scale() == 4`. Số 0 cuối có thể ảnh hưởng tới **scale** và biểu diễn, dù không ảnh hưởng tới giá trị toán học.

- **Precision** là số chữ số thập phân của unscaled value (giá trị 0 có precision 1), không phải độ rộng bit cố định.
- **Scale** là số nguyên kiểu `int` và có thể âm, bằng 0 hoặc dương. `"1E+3"` có scale `-3`; `"1.00"` có scale `2`.
- `MathContext` có thể quy định precision kết quả và `RoundingMode`; `setScale(...)` quy định scale của kết quả. Đây là **quy tắc tính/làm tròn**, không phải hằng cận giá trị nguyên thủy.
- `BigDecimal` có thể tính thập phân chính xác khi dữ liệu được dựng từ chuỗi và phép toán cho phép; một số phép chia cần precision/rounding policy.

Nếu đầu vào là số thập phân chính xác từ người dùng hoặc tài liệu, ưu tiên `new BigDecimal("0.1")` thay vì `new BigDecimal(0.1)`. Constructor nhận `double` phản ánh giá trị nhị phân gần đúng của `0.1` được cung cấp. `BigDecimal.valueOf(0.1)` dùng biểu diễn thập phân của `Double.toString`, nhưng không khôi phục dữ liệu đã mất trong các phép `double` trước đó.

## 6. Hằng số, literal và chuyển đổi liên quan tới miền giá trị

### Literal nguyên: int là mặc định, long dùng L

Trong Java, literal số nguyên thập phân không có hậu tố thường có kiểu `int` nếu giá trị biểu diễn được; thêm `L` để thể hiện literal `long`. Ví dụ:

```java
int size = 1_000_000;
long population = 9_000_000_000L;
long max = Long.MAX_VALUE;
```

`9_000_000_000` không hậu tố không phải literal thập phân `int` hợp lệ dù biến đích là `long`. Việc gán sau đó không biến một literal ngoài miền `int` thành hợp lệ. Có thể sử dụng dấu gạch dưới giữa các chữ số để dễ đọc.

### Literal floating point: double mặc định, float dùng F/f

`3.14` là literal `double`; `3.14f` hoặc `3.14F` là literal `float`. Với `float`, việc dùng hậu tố `f` cần thiết khi muốn biểu diễn literal dấu phẩy động bằng kiểu `float`:

```java
float f = 0.1f;
double d = 0.1;
```

Ngay cả khi chuỗi thập phân trông giống nhau, `f` và `d` dùng lượng bit khác nhau, nên giá trị được lưu có thể khác nhau. Không giả định ép một giá trị `double` sang `float` rồi nâng lại sang `double` sẽ phục hồi precision đã mất.

### Chuyển kiểu hẹp và tràn số

`int` chứa mọi giá trị `byte` và `short`, nhưng phép chuyển `int → byte`/`short` có thể làm mất bit:

```java
int number = 130;
byte narrowed = (byte) number;
System.out.println(narrowed); // -126
```

Khi cần chắc chắn giá trị nằm trong miền, hãy so sánh với `Byte.MIN_VALUE` và `Byte.MAX_VALUE` **trước khi ép**. Với phép toán `int` hoặc `long` có thể tràn, dùng `Math.addExact`, `Math.subtractExact` hoặc `Math.multiplyExact` khi cần báo lỗi thay vì âm thầm wrap. Lưu ý `Math.abs(Integer.MIN_VALUE)` cũng gây bất ngờ vì trị tuyệt đối toán học của cận âm không thể chứa trong `int`.

### Không có primitive unsigned int/long riêng

Java không có primitive `unsigned int` hoặc `unsigned long` theo kiểu C/C++. Tuy nhiên, từ Java 8 có các phương thức hỗ trợ **diễn giải unsigned** của các bit `int`/`long` như `Integer.toUnsignedString(...)`, `Integer.compareUnsigned(...)`, `Long.divideUnsigned(...)`; `Byte.toUnsignedInt(...)` và `Short.toUnsignedInt(...)` giúp đọc 8/16 bit như số không dấu.

Điều đó **không làm mở rộng miền lưu trữ** của `int`/`long`: các biến vẫn có mẫu bit và cách hiển thị signed của kiểu tương ứng, còn một số phép toán/helper diễn giải mẫu bit theo quy ước unsigned.

## 7. Khi nào chọn kiểu nào?

| Tình huống | Lựa chọn thường hợp lý | Điểm cần kiểm tra |
|---|---|---|
| Bộ đếm, chỉ số mảng, số nguyên trong miền 32-bit | `int` | Tràn, miền âm/dương, thao tác đồng thời |
| Số nguyên vượt miền `int` nhưng trong 64-bit | `long` | Literal `L`, tràn và chuyển `long → double` |
| Giao thức tệp/đệm có trường 8 hoặc 16 bit | `byte`, `short` | Signed interpretation, masking, endian ở cấp byte |
| UTF-16 code unit | `char` | Không đồng nhất với Unicode code point |
| Mô phỏng/số thực cần tiết kiệm bộ nhớ và chấp nhận precision thấp | `float` | Sai số và nhu cầu độ chính xác |
| Phép tính số thực phổ biến với precision nhị phân cao hơn | `double` | Làm tròn, NaN, infinity, phép so sánh gần bằng |
| Số nguyên vượt miền `long` | `BigInteger` | CPU, RAM, số chữ số, phép toán sinh kết quả lớn |
| Tiền/số thập phân chính xác có quy tắc làm tròn rõ | `BigDecimal` | Scale, precision, rounding mode, nguồn tạo số |

`byte` hoặc `short` không tự làm mọi phép toán nhanh hơn `int`; các phép toán số học với `byte`/`short` thường được nâng lên `int`. Chọn kiểu theo hợp đồng dữ liệu và yêu cầu lưu trữ, không chỉ theo mong muốn “giảm số bit”.

Với tiền tệ, `BigDecimal` hoặc một số nguyên `long` đại diện đơn vị nhỏ nhất có thể phù hợp tùy nghiệp vụ. Chỉ dùng `double` nếu ứng dụng **chấp nhận rõ** sai số binary floating point và có quy tắc làm tròn/so sánh thích hợp.

## 8. Các nhầm lẫn thường gặp khi tra bảng

### Nhầm Float.MIN_VALUE là số âm thấp nhất

`Float.MIN_VALUE` là khoảng `1.4E-45`, **dương và rất gần 0**. Nếu muốn số hữu hạn âm có độ lớn lớn nhất, dùng `-Float.MAX_VALUE`. Tương tự với `Double.MIN_VALUE` và `-Double.MAX_VALUE`.

### Nhầm kích thước kiểu với kích thước object

`Integer.SIZE == 32` và `Integer.BYTES == 4` không chứng minh một đối tượng `new Integer(...)` hay `Integer` boxing chiếm đúng 4 byte RAM. Một object có header và chi phí quản lý; mảng, tham chiếu, alignment và JVM còn tạo overhead. Ngoài ra, việc tạo wrapper bằng constructor đã không được khuyến nghị; dùng autoboxing hoặc `Integer.valueOf` khi cần wrapper.

### Nhầm char là ký tự Unicode đầy đủ

`char` có 16 bit, nhưng một Unicode code point ngoài BMP cần hai UTF-16 code unit. Với chuỗi có emoji hoặc ký tự bổ sung, `String.length()` đếm code unit, không nhất thiết bằng số Unicode code point hoặc số ký tự người dùng cảm nhận.

### Nhầm Float.MIN_EXPONENT với exponent thập phân nhỏ nhất

`MIN_EXPONENT` và `MAX_EXPONENT` nêu phạm vi exponent **nhị phân của normal**, không phải số mũ `E` trong `toString()`. Mẫu subnormal còn có số dương nhỏ hơn `MIN_NORMAL`, và ký pháp scientific của số thập phân là chuyện trình bày khác.

### Nhầm miền hữu hạn với độ chính xác thập phân

`Double.MAX_VALUE` rất lớn nhưng không có nghĩa `double` biểu diễn chính xác mọi số từ 0 đến giới hạn ấy. Giá trị dấu phẩy động là tập rời rạc. Khi độ lớn tăng, khoảng cách giữa các giá trị liên tiếp có thể vượt 1; đó là lý do nhiều số nguyên lớn gần nhau ép sang `double` có cùng kết quả.

### Nhầm BigDecimal không giới hạn gì

`BigDecimal` có unscaled value độ lớn tùy ý, nhưng scale vẫn có kiểu `int`; dữ liệu và phép toán phải phù hợp RAM/CPU và quy tắc của API. `MathContext` quy định precision kết quả, không biến các phép tính với đầu vào khổng lồ thành an toàn tài nguyên.

### Nhầm nguyên tắc “chỉ cần cast kết quả”

Nếu hai toán hạng `int` thực hiện phép nhân bị tràn trước khi gán vào `long`, viết `long answer = (long)(a*b)` không khôi phục giá trị đúng. Cần đưa `long` **vào trước phép nhân**, chẳng hạn `(long)a * b`. Tương tự, `double ratio = 5 / 2` vẫn nhận `2.0`; dùng `5 / 2.0` nếu muốn `2.5`.

## 9. Checklist tra cứu nhanh và tự kiểm tra

Khi cần kiểm tra một giá trị số trong code:

1. Xác định đúng kiểu **biểu thức đang tính**, không chỉ kiểu biến đích.
2. Với `byte`/`short`/`int`/`long`, lấy hằng `MIN_VALUE`, `MAX_VALUE`, `SIZE`, `BYTES` từ wrapper tương ứng.
3. Với `float`/`double`, phân biệt **miền hữu hạn**, **precision nhị phân**, **subnormal**, `NaN` và infinity.
4. Với `char`, phân biệt UTF-16 code unit với Unicode code point và chỉ ép sang `int` khi muốn in mã số.
5. Với `BigInteger`/`BigDecimal`, xác định giới hạn nghiệp vụ và tài nguyên; dùng `bitLength()`, `precision()`, `scale()` theo từng loại thay vì hỏi `SIZE` cố định.
6. Trước khi thu hẹp kiểu hoặc nhân/chia số nguyên, xác định có mất thông tin hoặc tràn hay không.
7. Viết một test ranh giới: giá trị đúng `MAX_VALUE`, đúng `MIN_VALUE`, sát 0, số ngay ngoài miền (nếu có), và các trường hợp floating point gần ranh giới precision.

**Tự kiểm tra 1:** Vì sao `Float.MIN_VALUE` là số dương nhưng `Integer.MIN_VALUE` là số âm? Vì hai hằng có nghĩa khác: với `Integer` là cận âm của số nguyên có dấu, còn với `Float` là giá trị dương khác 0 nhỏ nhất biểu diễn được của IEEE 754.

**Tự kiểm tra 2:** `char` có thể chứa số `65535` không, và điều đó có nghĩa nó chứa mọi ký tự Unicode không? Có thể chứa giá trị code unit `65535`; **không**, code point Unicode có thể nằm ngoài BMP và phải biểu diễn bằng một cặp surrogate trong UTF-16.

**Tự kiểm tra 3:** `long` có biểu diễn được mọi số nguyên từ `0` đến `9_007_199_254_740_993` không? **Có**, vì tất cả đều nằm trong miền `long`. Nhưng `double` **không thể biểu diễn chính xác mọi số nguyên** trong khoảng đó: `2^53 + 1` đã là một ví dụ mất thông tin khi ép.

**Tự kiểm tra 4:** `BigInteger` có `MAX_VALUE` giống `Long.MAX_VALUE` không? **Không**. `BigInteger` không có một cận số học cố định ở 64 bit; giới hạn thực tế nằm ở tài nguyên và triển khai. Hằng `BigInteger.TEN` chỉ là số 10.

**Tự kiểm tra 5:** Một `BigDecimal("123.4500")` có `precision = 7`, `scale = 4` có chiếm “7 byte” không? **Không**. Precision là số chữ số thập phân có nghĩa của unscaled value, không phải kích thước lưu trữ byte.

**Ghi nhớ:** `byte/short/int/long` có miền số nguyên signed cố định; `char` là code unit 16-bit không dấu; `float/double` có miền hữu hạn, precision nhị phân hữu hạn và các giá trị đặc biệt; `BigInteger/BigDecimal` có độ lớn/precision linh hoạt nhưng không miễn giới hạn tài nguyên. Luôn tra hằng theo **kiểu và ý nghĩa cụ thể**, đặc biệt lưu ý `Float.MIN_VALUE`/`Double.MIN_VALUE` không giống cách hiểu `MIN_VALUE` của số nguyên.
