# In mẫu bit, kiểu biểu thức và precision để điều tra kết quả bất ngờ trong Java

## 1. Tại sao một biểu thức số cho kết quả “không đúng như nhìn thấy”?

Khi điều tra lỗi liên quan đến số trong Java, việc chỉ in ra giá trị cuối bằng `System.out.println(result)` thường không đủ. Cùng một kết quả bất ngờ có thể đến từ các nguyên nhân khác nhau:

- **Kiểu biểu thức sai với kỳ vọng:** `5 / 2` là phép chia giữa hai `int`, kết quả `2`, dù sau đó được gán sang `double`.
- **Tràn số trước khi mở rộng kiểu:** `int * int` được tính bằng `int`, có thể tràn rồi mới gán vào biến `long`.
- **Biểu diễn nhị phân gần đúng:** `0.1` và `0.2` không có biểu diễn hữu hạn chính xác trong IEEE 754 nhị phân, nên tổng `double` có thể in thành `0.30000000000000004`.
- **Chuyển kiểu làm mất bit có nghĩa:** `long` đủ chứa một số nguyên lớn nhưng `double` không chứa chính xác mọi số nguyên trong cùng miền giá trị.
- **Nhầm precision với scale:** `BigDecimal("1.2300")` có precision bằng `5`, scale bằng `4`; việc bỏ số 0 cuối hoặc làm tròn thay đổi cách biểu diễn.
- **Nhầm giá trị và mẫu bit:** `+0.0` và `-0.0` so sánh `==` là bằng nhau nhưng có mẫu bit khác nhau.

Để tìm nguyên nhân, hãy thu thập **giá trị + kiểu của biểu thức + mẫu bit/biểu diễn + độ chính xác và thời điểm chuyển đổi**. Đây là quy trình chẩn đoán, không phải yêu cầu mọi phép tính đều phải tự phân tích bit.

## 2. Đọc đúng kiểu biểu thức trước khi xem giá trị

Java xác định **kiểu của một biểu thức ở thời điểm biên dịch** theo quy tắc chuyển đổi và *numeric promotion*. Kiểu của biến nhận kết quả không nhất thiết thay đổi loại phép toán đã thực hiện trước đó.

Ví dụ:

```java
double a = 5 / 2;    // Phép chia int / int => int 2, sau đó thành double 2.0.
double b = 5 / 2.0;  // Có toán hạng double => chia double => 2.5.

int x = 50_000;
int y = 50_000;
long wrong = x * y;        // int * int bị tràn trước khi gán long.
long right = (long) x * y; // Ép x sang long TRƯỚC phép nhân.
```

Kết quả tương ứng:

| Biểu thức | Kiểu tính toán | Kết quả |
|---|---|---|
| `5 / 2` | `int` | `2` |
| `(double) (5 / 2)` | `int` khi chia; đổi thành `double` sau đó | `2.0` |
| `5 / 2.0` | `double` | `2.5` |
| `x * y` với cả hai `int = 50_000` | `int` | `-1794967296` (tràn) |
| `(long) x * y` | `long` | `2500000000` |
| `Integer.MAX_VALUE + 1` | `int` | `-2147483648` (tràn vòng) |

Các phép toán số nguyên nhị phân thông thường áp dụng **binary numeric promotion**: `byte`, `short` và `char` thường được nâng lên `int`; nếu có `long` thì nhiều phép sẽ tính bằng `long`; nếu có `float` hoặc `double`, phép toán tương ứng có kiểu đó theo thứ tự nâng kiểu. Đừng suy luận chỉ từ kiểu khai báo của toán hạng nhỏ.

Ví dụ `byte left = 10; byte right = 20;` nhưng `left + right` có kiểu biểu thức **`int`**, không phải `byte`. Và `var total = left + right;` suy diễn `total` là `int` vì `var` nhận kiểu biểu thức lúc biên dịch.

### Chẩn đoán kiểu bằng overload

Primitive như `int`/`double` không có `getClass()`. Nếu ép sang `Object` rồi gọi `getClass()`, quá trình **boxing** tạo `Integer`/`Double`, nghĩa là ta đang thấy lớp của wrapper, không trực tiếp thấy kiểu primitive ban đầu. Một cách dạy và kiểm tra hiệu quả là dùng overload:

```java
static String kind(int value)    { return "int"; }
static String kind(long value)   { return "long"; }
static String kind(double value) { return "double"; }

// kind(5 / 2) => "int"
// kind(5 / 2.0) => "double"
// kind(left + right), với hai byte => "int"
```

Đây là **đoạn minh họa đặt trong lớp**, chưa phải chương trình độc lập. Trình biên dịch chọn overload theo kiểu biểu thức khi gọi; vì vậy có thể dùng cách này trong một đoạn thử nhỏ để xác nhận dự đoán kiểu.

Cần nhớ: kiểu của biến khi gán, kiểu của biểu thức con và kiểu sau một phép ép có thể khác nhau. Hãy nhìn từ **biểu thức gây mất thông tin đầu tiên**, không chỉ biến được in ở cuối.

## 3. In mẫu bit của số nguyên: hai bù và độ rộng cố định

`int` là số nguyên có dấu 32-bit; `long` là số nguyên có dấu 64-bit. Java dùng biểu diễn **two's complement (bù hai)** cho số nguyên có dấu. Khi chẩn đoán overflow, in số ở hệ 16 hoặc hệ 2 cho phép xem trực tiếp những bit đang được lưu:

```java
int n = -1;
System.out.printf("%08X%n", n); // FFFFFFFF
System.out.println(Integer.toBinaryString(n));
// 11111111111111111111111111111111
```

`%08X` in `int` thành chuỗi hex có độ rộng tối thiểu 8 ký tự; `%016X` phù hợp để quan sát đầy đủ 16 chữ số hex của giá trị `long` 64-bit. Dấu `X` dùng chữ cái hex viết hoa, `%n` xuống dòng theo môi trường.

Với một giá trị `int`, `Integer.toHexString(n)` và `Integer.toBinaryString(n)` cũng hữu ích, nhưng có thể không tự chèn số 0 ở đầu cho số dương, nên cần định dạng nếu muốn so sánh từng vị trí bit.

Ví dụ `Integer.MAX_VALUE` là `0x7FFFFFFF`. Sau phép cộng `1` trên `int`, chuỗi bit trở thành `0x80000000`, được hiểu là `Integer.MIN_VALUE`. Đây là tràn theo miền 32-bit, **không phải lỗi in số**.

Để **phát hiện overflow thay vì âm thầm nhận kết quả vòng**, có thể dùng `Math.addExact(int,int)` hoặc `Math.multiplyExact(int,int)`. Các phương thức này ném `ArithmeticException` khi kết quả toán học không biểu diễn được trong kiểu mục tiêu. Nếu cần miền lớn hơn, dùng phép mở rộng sang `long` **trước khi tính** hoặc `BigInteger` tùy yêu cầu. Ép kiểu sau khi phép `int` đã tràn không khôi phục được những bit đã mất.

### Lưu ý với số nguyên không giới hạn độ lớn

`BigInteger` không bị cố định ở 32 hoặc 64 bit. `big.toString(2)` in chuỗi giá trị cơ số 2, nhưng với giá trị âm nó dùng dấu trừ phía trước; đây **không phải** bản dump hai bù với một độ rộng máy cố định. Khi cần quan sát hai bù 32-bit/64-bit, hãy làm trên `int`/`long` hoặc tự định nghĩa rõ độ rộng bit mong muốn.

`BigInteger.bitLength()` cho biết độ dài bit tối thiểu theo quy tắc API; nó khác với việc in toàn bộ chuỗi bit cố định của một từ máy.

## 4. Floating point: nhìn giá trị thập phân và mẫu bit IEEE 754 cùng lúc

`float` trong Java dùng định dạng IEEE 754 binary32 (32 bit); `double` dùng binary64 (64 bit). Mẫu bit gồm:

| Kiểu | Bit dấu | Bit exponent | Bit fraction lưu trữ | Precision nhị phân hữu hiệu của số chuẩn hóa |
|---|---:|---:|---:|---:|
| `float` | 1 | 8 | 23 | 24 bit |
| `double` | 1 | 11 | 52 | 53 bit |

Đối với số hữu hạn chuẩn hóa (*normal*), có một bit có nghĩa đứng đầu được ngầm định; vì vậy precision hữu hiệu lớn hơn số bit fraction lưu trữ. Giá trị subnormal có cơ chế khác và độ chính xác tương đối thấp hơn gần số 0.

Những phân số thập phân như `0.1` và `0.2` có khai triển vô hạn trong hệ nhị phân. JVM lưu giá trị nhị phân gần nhất có thể biểu diễn theo định dạng đã chọn. Khi cộng các số xấp xỉ và làm tròn về `double`, kết quả có thể không trùng đúng `0.3`.

Cách xem mẫu bit mà không làm thay đổi giá trị:

```java
double value = 0.1;
long bits = Double.doubleToRawLongBits(value);
System.out.printf("0.1 double bits: %016X%n", bits);

float small = 0.1f;
int floatBits = Float.floatToRawIntBits(small);
System.out.printf("0.1f float bits: %08X%n", floatBits);
```

`Double.doubleToRawLongBits` trả **mẫu 64 bit thực** của `double` dưới dạng `long`; `Float.floatToRawIntBits` trả **mẫu 32 bit thực** của `float` dưới dạng `int`. Dù giá trị `long` có thể mang dấu khi xem theo số nguyên, các bit vẫn giữ nguyên, nên định dạng hex giúp quan sát thuận tiện.

Hai phương thức không có chữ `Raw` — `Double.doubleToLongBits` và `Float.floatToIntBits` — **chuẩn hóa các dạng NaN** về mẫu NaN canonical; nếu đang điều tra payload bit của NaN, cần phân biệt rõ phương thức raw và non-raw. Đối với số hữu hạn thông thường, kết quả trùng nhau.

**Cần phân biệt:** mẫu bit IEEE 754 là thứ tự **vị trí bit trong giá trị**, không trực tiếp là thứ tự các **byte trong bộ nhớ**. Endianness khi tuần tự hóa byte là một vấn đề khác.

### Bit thập phân cho thấy điều gì?

Trong ví dụ cụ thể:

- `0.1` có mẫu `3FB999999999999A`.
- `0.2` có mẫu `3FC999999999999A`.
- `0.1 + 0.2` có mẫu `3FD3333333333334`, và `Double.toString` biểu diễn nó bằng `0.30000000000000004`.

Sự khác biệt trong mẫu bit giải thích vì sao `sum == 0.3` có thể trả `false` dù hai kết quả hiển thị gần như giống nhau. `Double.toString` lựa chọn chuỗi thập phân ngắn đủ để tái lập giá trị `double`, **không phải phép đo số chữ số đúng của giá trị toán học**.

Khi debug, hãy in đồng thời `Double.toString(value)`, mẫu bit raw, và nếu cần, hiệu số so với giá trị kỳ vọng. Đừng ép một chuỗi bit bất kỳ thành lời giải thích dựa trên chữ số thập phân mà chưa xét định dạng nhị phân.

### Hai số 0 có dấu

`+0.0` và `-0.0` so sánh bằng `==` là `true`, nhưng có bit dấu khác nhau:

```text
+0.0 bits: 0000000000000000
-0.0 bits: 8000000000000000
```

Vì vậy, việc chỉ kiểm tra `a == b` không đủ khi cần điều tra dấu của zero. Hai zero còn có thể dẫn đến kết quả khác nhau trong một số phép toán, ví dụ phép chia `1.0 / +0.0` cho dương vô cực và `1.0 / -0.0` cho âm vô cực.

Tương tự, `Double.NaN == Double.NaN` là `false`; dùng `Double.isNaN(value)` để nhận biết NaN và `Double.isFinite(value)` khi muốn yêu cầu số hữu hạn. Khi ghi log mẫu bit NaN, lưu ý phép toán trung gian có thể làm biến đổi payload NaN, và API canonical có thể làm mất sự khác biệt giữa các payload.

## 5. Precision, ULP và độ chính xác của số thực

Không nên mô tả chung rằng `double` “có 16 chữ số thập phân chính xác” rồi cho rằng tất cả số 16 chữ số đều biểu diễn được. Binary64 có **53 bit precision nhị phân**, thường tương ứng khoảng 15–17 chữ số thập phân có nghĩa tùy phép chuyển đổi và bài toán. Binary32 có **24 bit precision nhị phân**, thường vào khoảng 6–9 chữ số thập phân. Precision và khoảng cách giữa các số có thể biểu diễn **phụ thuộc độ lớn**.

**ULP** (*unit in the last place*) là đơn vị bước tại vị trí bit có nghĩa cuối trong vùng giá trị đang xét. Trong Java:

```java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
```

Ngay trên `1.0`, khoảng cách tới số `double` biểu diễn tiếp theo là \(2^{-52}\), bằng khoảng `2.22 × 10^-16`. Với số có độ lớn khác, ULP thay đổi. Vì vậy một epsilon tuyệt đối duy nhất không phù hợp cho mọi phép so sánh `double` trên các thang đo rất khác nhau.

Khi cần so sánh số thực theo sai số cho phép, định nghĩa dung sai từ **yêu cầu bài toán** rồi cân nhắc độ lớn và trường hợp biên, ví dụ:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absTol, double relTol) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return a == b; // +Infinity/-Infinity tự so sánh theo ==; NaN false.
    }
    double delta = Math.abs(a - b);
    return delta <= Math.max(absTol,
            relTol * Math.max(Math.abs(a), Math.abs(b)));
}
```

Đây là **hàm minh họa**, dùng khi phạm vi dữ liệu và các tolerance đã được chọn theo yêu cầu; với số cực lớn, phép trừ `a-b` có thể tràn thành vô cực dù hai toán hạng hữu hạn. Một thuật toán so sánh dùng trong sản phẩm phải xử lý các biên đó, zero, NaN, infinity và nghiệp vụ cụ thể. Không chọn `1e-9` một cách máy móc cho mọi đại lượng.

### Số nguyên long rất lớn đi qua double

Một `double` có 53 bit precision nên biểu diễn được chính xác mọi số nguyên có trị tuyệt đối **không quá \(2^{53}\)**; nhưng không phải mọi số nguyên lớn hơn ngưỡng này đều biểu diễn chính xác được. Ví dụ:

```java
long exact = 9_007_199_254_740_993L;   // 2^53 + 1
long after = (long) (double) exact;      // 9007199254740992
```

Ở đây ép `long → double` làm tròn giá trị xuống số nguyên biểu diễn được gần nhất rồi ép về `long`, gây sai lệch 1. Việc in chính xác bit `double` hoặc so sánh lại với `long` sẽ bộc lộ chỗ mất thông tin. Nếu thuật toán đòi số nguyên chính xác, đừng đi qua `float`/`double` khi không có lý do rõ ràng.

### float được nâng lên double không tăng lại precision đã mất

`float f = 0.1f` lưu một xấp xỉ binary32. Khi ép `(double) f`, giá trị binary32 ấy được biểu diễn **chính xác dưới dạng double**, nhưng phần thông tin so với thập phân `0.1` đã mất khi gán vào `float` thì không được “phục hồi”. Vì vậy:

- `Float.toString(0.1f)` thường in `0.1`.
- `Double.toString((double) 0.1f)` in `0.10000000149011612`.
- Bit float của `0.1f` là `3DCCCCCD`.

Khi điều tra, in cả **kiểu nguồn, thời điểm chuyển kiểu và mẫu bit**, không chỉ in biến cuối cùng là `double`.

## 6. BigDecimal: decimal precision khác với bit precision

`BigDecimal` giữ một **unscaled value** nguyên và một `scale`; giá trị số học là:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`precision()` ở đây là **số chữ số thập phân của unscaled value** (giá trị 0 có precision 1), **không phải 53 bit của double**. Ví dụ:

```java
BigDecimal number = new BigDecimal("1.2300");

System.out.println(number.precision()); // 5
System.out.println(number.scale());     // 4
```

`"1.2300"` có unscaled value `12300` và scale `4`; vì thế precision bằng `5`. Nếu dùng `stripTrailingZeros()`, kết quả `1.23` có precision `3`, scale `2`: giá trị số học vẫn bằng nhau nhưng cách biểu diễn/scale khác.

Khi cần tìm nguyên nhân kết quả `BigDecimal` bất ngờ, in ra:

- `toString()` hoặc `toPlainString()` để xem cách viết số hiện tại.
- `precision()` và `scale()` để biết giới hạn và vị trí dấu thập phân.
- `unscaledValue()` nếu cần xác minh giá trị nguyên phía sau biểu diễn.
- `MathContext` hoặc `RoundingMode` đã sử dụng trong phép tính: số chữ số có nghĩa cần giữ và quy tắc làm tròn.

Một `MathContext(3, RoundingMode.HALF_EVEN)` yêu cầu **3 chữ số có nghĩa**, khác với `setScale(3, ...)` yêu cầu **3 chữ số sau dấu thập phân**. Ví dụ `new BigDecimal("12.35").round(new MathContext(3, HALF_EVEN))` cho `12.4`. Đừng gọi cả hai khái niệm đơn giản là “3 chữ số precision” mà không nói rõ đây là digits có nghĩa hay chữ số sau dấu chấm.

### BigDecimal tạo từ double có thể kế thừa sai số nhị phân

`new BigDecimal(0.1)` biểu diễn chính xác **giá trị nhị phân thực tế** của double `0.1`, vốn khác số thập phân `0.1` toán học. `new BigDecimal("0.1")` biểu diễn chính xác thập phân `0.1`. Do đó:

```java
BigDecimal fromBinary = new BigDecimal(0.1);
BigDecimal fromDecimal = new BigDecimal("0.1");

System.out.println(fromBinary.equals(fromDecimal)); // false
System.out.println(BigDecimal.valueOf(0.1));        // 0.1
```

`BigDecimal.valueOf(double)` dùng biểu diễn thập phân qua `Double.toString` và thường phù hợp hơn constructor nhận trực tiếp `double` nếu đã có một giá trị double. Nhưng nó **không khôi phục dữ liệu chính xác** đã mất từ các phép toán double trước đó. Khi nguồn dữ liệu là chuỗi số thập phân có ý nghĩa nghiệp vụ, ưu tiên tạo `BigDecimal` trực tiếp từ chuỗi.

Kiểm tra ví dụ làm tròn:

```java
BigDecimal precise = new BigDecimal("1.005");
System.out.println(precise.setScale(2, RoundingMode.HALF_UP));
// 1.01
```

Nếu thay chuỗi bằng double literal rồi dùng constructor `new BigDecimal(1.005)`, giá trị nhị phân xấp xỉ thực tế có thể làm kết quả khác. Phải điều tra **nguồn số và điểm chuyển đổi trước khi nhìn vào chế độ làm tròn**.

## 7. Ví dụ Java 17+ độc lập: in kiểu, bit và precision

Bài thực hành sau cố ý chọn các giá trị dễ tái hiện để kết quả không phụ thuộc lịch đa luồng hay nguồn ngẫu nhiên. Lưu chương trình dưới tên **`NumericDiagnostics.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class NumericDiagnostics {
    static String kind(int x)    { return "int"; }
    static String kind(long x)   { return "long"; }
    static String kind(double x) { return "double"; }

    public static void main(String[] args) {
        byte left = 10;
        byte right = 20;
        System.out.println("byte + byte expression: " + kind(left + right));
        System.out.println("5 / 2 expression: " + kind(5 / 2));
        System.out.println("5 / 2 = " + (5 / 2));
        System.out.println("double assigned 5 / 2 = " + (double) (5 / 2));
        System.out.println("5 / 2.0 = " + (5 / 2.0));

        int a = 50_000;
        int b = 50_000;
        long wrong = a * b;
        long rightResult = (long) a * b;
        System.out.println("int multiplication assigned to long: " + wrong);
        System.out.println("cast before multiplication: " + rightResult);
        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        System.out.printf("minus one int bits: %08X%n", -1);
        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException e) {
            System.out.println("multiplyExact: overflow detected");
        }

        double p = 0.1;
        double q = 0.2;
        double sum = p + q;
        System.out.println("0.1 + 0.2 = " + sum);
        System.out.printf("0.1 double bits: %016X%n",
                Double.doubleToRawLongBits(p));
        System.out.printf("0.2 double bits: %016X%n",
                Double.doubleToRawLongBits(q));
        System.out.printf("sum double bits: %016X%n",
                Double.doubleToRawLongBits(sum));
        System.out.printf("+0.0 bits: %016X%n",
                Double.doubleToRawLongBits(+0.0));
        System.out.printf("-0.0 bits: %016X%n",
                Double.doubleToRawLongBits(-0.0));
        System.out.println("+0.0 == -0.0: " + (+0.0 == -0.0));
        System.out.println("Math.ulp(1.0): " + Math.ulp(1.0));

        float f = 0.1f;
        System.out.printf("0.1f float bits: %08X%n",
                Float.floatToRawIntBits(f));
        System.out.println("0.1f promoted to double: " + (double) f);

        long exact = 9_007_199_254_740_993L;
        System.out.println("long after double roundtrip: "
                + (long) (double) exact);

        BigDecimal value = new BigDecimal("1.2300");
        System.out.println("BigDecimal 1.2300 precision/scale: "
                + value.precision() + "/" + value.scale());
        System.out.println("stripTrailingZeros precision/scale: "
                + value.stripTrailingZeros().precision() + "/"
                + value.stripTrailingZeros().scale());
        System.out.println("new BigDecimal(0.1) equals decimal 0.1: "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("BigDecimal.valueOf(0.1): "
                + BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("HALF_UP 1.005 to scale 2: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("MathContext precision 3 for 12.35: "
                + new BigDecimal("12.35").round(
                        new MathContext(3, RoundingMode.HALF_EVEN)));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac NumericDiagnostics.java
java NumericDiagnostics
```

Đầu ra:

```text
byte + byte expression: int
5 / 2 expression: int
5 / 2 = 2
double assigned 5 / 2 = 2.0
5 / 2.0 = 2.5
int multiplication assigned to long: -1794967296
cast before multiplication: 2500000000
int overflow: -2147483648
minus one int bits: FFFFFFFF
multiplyExact: overflow detected
0.1 + 0.2 = 0.30000000000000004
0.1 double bits: 3FB999999999999A
0.2 double bits: 3FC999999999999A
sum double bits: 3FD3333333333334
+0.0 bits: 0000000000000000
-0.0 bits: 8000000000000000
+0.0 == -0.0: true
Math.ulp(1.0): 2.220446049250313E-16
0.1f float bits: 3DCCCCCD
0.1f promoted to double: 0.10000000149011612
long after double roundtrip: 9007199254740992
BigDecimal 1.2300 precision/scale: 5/4
stripTrailingZeros precision/scale: 3/2
new BigDecimal(0.1) equals decimal 0.1: false
BigDecimal.valueOf(0.1): 0.1
HALF_UP 1.005 to scale 2: 1.01
MathContext precision 3 for 12.35: 12.4
```

Đọc kết quả theo nhóm:

1. **Kiểu:** `byte + byte` trở thành `int`; `5 / 2` là `int`. Khi cast sau phép chia, giá trị đã bị cắt phần dư nên chỉ thành `2.0`; dùng `2.0` ngay trong biểu thức mới cho `2.5`.
2. **Overflow:** `a*b` được tính theo `int` và tràn thành `-1794967296` trước khi gán vào `long`. Ép `a` trước phép nhân cho `2500000000`. `Math.multiplyExact` phát hiện thay vì âm thầm tràn.
3. **IEEE 754:** tổng `0.1+0.2` cho ra `0.30000000000000004` và mẫu bit khác với biểu diễn thập phân `0.3` mà người đọc kỳ vọng. Bit dấu của hai zero khác nhau dù toán tử `==` coi chúng bằng nhau.
4. **Precision:** `Math.ulp(1.0)` cung cấp bước gần 1; khi `float 0.1f` được nâng sang `double`, chữ số thập phân của giá trị thực lưu trong float lộ rõ.
5. **BigDecimal:** `precision/scale` của `1.2300` là `5/4`; bỏ trailing zeros đổi thành `3/2`. Tạo từ chuỗi thập phân và dùng đúng `MathContext`/`RoundingMode` giúp chẩn đoán khác biệt làm tròn.

## 8. Quy trình điều tra một kết quả số bất ngờ

Một checklist thực tế để đi từ triệu chứng đến nguyên nhân:

1. **Ghi lại đầu vào gốc trước khi chuyển kiểu.** Có phải chuỗi, số nguyên, JSON number, `float` hay `double`? Nếu nguồn là thập phân, ghi rõ dấu, chữ số và scale mong đợi.
2. **Viết rõ biểu thức con, kiểu của từng toán hạng và kiểu của phép toán.** Xem quy tắc chia nguyên, numeric promotion, `var`, overload, kiểu literal như `2` so với `2.0` hoặc `2L`.
3. **Kiểm tra điểm tràn trước phép gán.** Nếu là `int/long`, đối chiếu miền giá trị, in hex hoặc dùng `Math.addExact`/`Math.multiplyExact` khi cần phát hiện.
4. **Nếu là floating point, in giá trị cùng raw bits.** Với `float` dùng `Float.floatToRawIntBits`; với `double` dùng `Double.doubleToRawLongBits`. Kiểm tra NaN/infinity, signed zero và ULP gần vùng quan tâm.
5. **Nếu có chuyển kiểu, in cả giá trị trước và sau.** Đặc biệt chú ý `long → double`, `double → float`, các phép toán `int` được gán `long`, hoặc tạo `BigDecimal` từ `double`.
6. **Nếu là BigDecimal, in precision, scale, unscaledValue, MathContext và RoundingMode.** Phân biệt làm tròn theo số chữ số có nghĩa với làm tròn theo số chữ số sau dấu thập phân.
7. **Tạo ca kiểm thử nhỏ nhất tái hiện được.** Ưu tiên kết quả xác định, có assert/giá trị mong đợi rõ. Kiểm tra các giá trị biên: lớn nhất, nhỏ nhất, dấu âm, zero, nửa bước làm tròn và giá trị sát ranh giới representable.
8. **Quyết định cách sửa theo hợp đồng dữ liệu**, không chỉ đổi định dạng đầu ra để “trông đẹp hơn”. Ví dụ sửa bằng cách ép `long` trước phép nhân; dùng `BigDecimal(String)` cho dữ liệu thập phân chính xác; hoặc thiết kế tolerance phù hợp nếu bài toán cho phép sai số nhị phân.

### Biết lúc nào không nên in toàn bộ số

Với `BigInteger` hoặc `BigDecimal` cực lớn, `toString()` và đặc biệt `toPlainString()` có thể tạo chuỗi rất dài. Trong hệ thống thật, đặt giới hạn log/đầu ra; có thể ghi có kiểm soát `signum`, `bitLength`, `precision`, `scale` và một phần đầu/cuối chuỗi đã được kiểm tra kích thước. Tuy nhiên, không nên in cả payload không tin cậy chỉ để debug. Những phép toán kiểm tra cũng tiêu tốn tài nguyên nếu đối tượng ban đầu đã quá lớn; giới hạn từ lớp nhập vẫn cần thiết.

## 9. Những lỗi chẩn đoán phổ biến

### Chỉ tăng số chữ số khi printf rồi cho rằng đã sửa sai số

`System.out.printf("%.17f", value)` có thể hiện thêm chữ số giúp nhìn rõ giá trị binary64 đã được xấp xỉ. Nó **không thay đổi các bit** của `value` và không tạo lại độ chính xác đã mất. Hiển thị ít chữ số hơn cũng không sửa lỗi phép toán. Khi cần hiểu chính xác, in raw bits hoặc biểu diễn thập phân đủ để round-trip.

### Nghĩ biến đích quyết định kiểu của phép nhân/chia

`long product = x*y` khi `x` và `y` là `int` vẫn nhân dưới dạng `int`. `double ratio = 5/2` vẫn chia nguyên. Cần đưa kiểu đúng vào **trong biểu thức trước phép toán**, không cast kết quả sau khi đã mất thông tin.

### Hiểu nhầm signed zero và NaN

`+0.0 == -0.0` đúng nhưng bit khác; `NaN == NaN` sai. Đừng dùng riêng toán tử `==` để kiểm tra mọi tính chất floating point. Dùng `Double.isNaN`, `isFinite` và raw bits theo mục tiêu.

### Cho rằng BigDecimal luôn không có sai số

`BigDecimal` có thể biểu diễn thập phân chính xác, nhưng nếu dựng từ một giá trị `double` đã xấp xỉ, đối tượng sẽ phản ánh giá trị được cung cấp. Phép chia còn có thể cần `MathContext` hoặc `RoundingMode`. Độ chính xác của cấu trúc lưu trữ không tự sửa sai sót ở **nguồn giá trị và chính sách tính toán**.

### Dùng equals để so sánh mọi BigDecimal

`BigDecimal.equals` xét cả giá trị và scale; `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả `false`, trong khi `compareTo` trả `0` vì giá trị số học như nhau. Nếu điều tra lý do so sánh thất bại, hãy in cả `scale()` và phân biệt hợp đồng so sánh giá trị với so sánh biểu diễn.

### Dùng so sánh epsilon không theo miền dữ liệu

Một ngưỡng sai số tuyệt đối duy nhất có thể quá chặt với số rất lớn và quá lỏng với số rất nhỏ. Xem ULP và đơn vị của bài toán, xử lý riêng NaN/infinity, và xây phép kiểm thử sát biên. Không tự động thay tất cả `==` bằng một phép so sánh gần đúng mà chưa xác định yêu cầu.

## 10. Tự kiểm tra

**Câu 1:** Tại sao `long result = 50_000 * 50_000;` cho giá trị âm, nhưng `long result = 50_000L * 50_000;` cho `2500000000`? Vì hai literal `int` khiến phép nhân đầu chạy trong `int` và tràn; hậu tố `L` ở toán hạng đầu làm phép nhân bằng `long` ngay từ đầu.

**Câu 2:** Nếu `double result = 7 / 2;` thì `result` bằng bao nhiêu? **`3.0`**. Muốn kết quả `3.5`, dùng `7 / 2.0` hoặc `(double) 7 / 2`.

**Câu 3:** `0.1f` in ra `0.1` nhưng ép sang `double` in `0.10000000149011612`. Có phải ép kiểu làm hỏng số không? **Không**. Giá trị đã được làm tròn khi lưu trong `float`; ép sang `double` lưu lại chính xác giá trị float ấy và biểu diễn thập phân của nó có thể dài hơn.

**Câu 4:** `new BigDecimal("1.2300")` có precision 5, scale 4. Sau `stripTrailingZeros()` thành precision 3, scale 2; điều này có làm giá trị số học đổi không? **Không**, chỉ thay đổi biểu diễn và số 0 sau dấu chấm.

**Câu 5:** Một bộ so sánh kiểm tra `0.1 + 0.2 == 0.3` trả `false`. Nên kiểm tra gì? In mẫu bit và giá trị `double` thực của hai phía, xác định số sai lệch có được bài toán chấp nhận không, rồi dùng chính sách so sánh phù hợp; nếu cần thập phân chính xác như tiền tệ, cân nhắc `BigDecimal` dựng từ chuỗi.

**Ghi nhớ:** Khi kết quả số gây bất ngờ, hãy kiểm tra **kiểu biểu thức trước khi phép toán xảy ra**, **mẫu bit sau khi tính**, và **precision/scale cùng nguồn giá trị**. Chẩn đoán theo từng bước sẽ phân biệt tràn số nguyên, mất dữ liệu khi chuyển kiểu, sai số IEEE 754 và làm tròn thập phân, từ đó chọn cách sửa đúng nguyên nhân.
