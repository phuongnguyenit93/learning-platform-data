# `copySign`, `scalb` và `getExponent` trong Java: dấu, lũy thừa của 2 và số mũ IEEE 754

`java.lang.Math` và `java.lang.StrictMath` có ba nhóm phương thức thường xuất hiện khi cần làm việc **gần với cách biểu diễn nhị phân của `float`/`double`**:

- **`copySign(magnitude, sign)`**: lấy độ lớn của đối số thứ nhất nhưng gắn **dấu của đối số thứ hai**, bao gồm dấu của zero âm.
- **`scalb(value, scaleFactor)`**: nhân giá trị với **\(2^{scaleFactor}\)** theo quy tắc làm tròn dấu phẩy động, rất hữu ích khi điều chỉnh thang đo nhị phân.
- **`getExponent(value)`**: trả về **số mũ không có bias của trường exponent** trong biểu diễn dấu phẩy động, đồng thời quy định các giá trị sentinel riêng cho zero, subnormal, NaN và infinity.

```java
double signed = Math.copySign(3.5, -0.0); // -3.5
double scaled = Math.scalb(1.5, 3);       // 12.0 = 1.5 × 2^3
int exponent = Math.getExponent(8.0);     // 3
```

Ba hàm này **không thay thế lẫn nhau**: `copySign` thay đổi bit dấu mà giữ độ lớn; `scalb` thay đổi thang độ lớn và có thể overflow/underflow; `getExponent` quan sát thông tin số mũ **chứ không tính một logarit tổng quát**. Bài này tập trung vào semantics của Java 17+, những giá trị IEEE 754 đặc biệt, ví dụ chạy được và cách dùng an toàn.

## 1. Nhắc lại mô hình biểu diễn `float` và `double`

Hai kiểu dấu phẩy động cơ bản của Java dùng định dạng nhị phân IEEE 754. Một số **normal** hữu hạn khác zero được biểu diễn bằng bit dấu, số mũ có bias và fraction; về ý tưởng có dạng:

\[
(-1)^{sign}\times (1.fraction)_2 \times 2^{exponent}
\]

| Thành phần | `float` / binary32 | `double` / binary64 |
| --- | ---: | ---: |
| Tổng bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit exponent | 8 | 11 |
| Bit fraction | 23 | 52 |
| Exponent của **normal** nhỏ nhất | `Float.MIN_EXPONENT = -126` | `Double.MIN_EXPONENT = -1022` |
| Exponent của **normal** lớn nhất | `Float.MAX_EXPONENT = 127` | `Double.MAX_EXPONENT = 1023` |
| Số hữu hạn **normal** dương nhỏ nhất | `Float.MIN_NORMAL` | `Double.MIN_NORMAL` |
| Số dương nhỏ nhất, kể cả **subnormal** | `Float.MIN_VALUE` | `Double.MIN_VALUE` |

Số **subnormal** có trường exponent bằng 0 và không dùng bit 1 ẩn ở đầu phần trị như số normal. Nhờ subnormal, Java biểu diễn được những số dương nhỏ hơn `MIN_NORMAL`, với độ chính xác giảm dần.

Ngoài số hữu hạn còn có `+0.0`, `-0.0`, `+Infinity`, `-Infinity` và **NaN**. Những giá trị này khiến các hàm thao tác dấu, scale hoặc exponent cần quy tắc đặc biệt.

**Nhầm lẫn cần tránh:** `Double.MIN_VALUE` là **số dương subnormal nhỏ nhất**, **không phải số `double` âm nhất**. Tương tự, `Math.getExponent(Double.MIN_VALUE)` không cho exponent toán học `-1074` của riêng giá trị subnormal đó; nó trả sentinel theo quy tắc API.

## 2. `Math.copySign`: lấy độ lớn từ một số và dấu từ số khác

Chữ ký overload:

```java
static double Math.copySign(double magnitude, double sign)
static float Math.copySign(float magnitude, float sign)
```

Có phương thức tương ứng trong `StrictMath`. Hai đối số phải phù hợp overload kiểu `double` hoặc `float`; hàm không tạo kiểu wrapper mới và không đọc chuỗi văn bản.

Ví dụ:

```java
Math.copySign(3.5, -2.0);        // -3.5
Math.copySign(-3.5, 2.0);        // 3.5
Math.copySign(0.0, -1.0);        // -0.0
Math.copySign(-0.0, +1.0);       // +0.0
Math.copySign(Double.POSITIVE_INFINITY, -1.0);
// -Infinity
```

Đối số đầu cung cấp **magnitude**. Nếu nó đã âm, `copySign` có thể chuyển thành dương khi đối số thứ hai mang dấu dương. Đây không phải phép cộng hai giá trị, cũng không phải lấy tích hay kiểm tra `sign > 0`.

### Dấu của `-0.0`: vì sao `sign < 0` không đủ?

Trong so sánh dấu phẩy động primitive:

```java
-0.0 == +0.0      // true
-0.0 < 0.0        // false
```

Nhưng chúng có **bit dấu khác nhau**. `Math.copySign(3.5, -0.0)` trả **`-3.5`**, vì đọc **dấu của zero âm**, không kiểm tra `-0.0 < 0`. Tương tự:

```java
double negativeZero = Math.copySign(0.0, -1.0);
boolean sameValue = negativeZero == 0.0; // true
long rawBits = Double.doubleToRawLongBits(negativeZero);
// 0x8000000000000000L
```

Nếu nghiệp vụ cần phát hiện zero âm, có thể kiểm tra bit dấu bằng `Double.doubleToRawLongBits` hoặc quan sát `1.0 / negativeZero` là `-Infinity`. Không dùng phép so sánh `value < 0` làm cách nhận diện tổng quát bit dấu.

### Dấu của vô cực

`copySign` giữ độ lớn vô cực và thay dấu:

```java
double result = Math.copySign(
    Double.POSITIVE_INFINITY, -1.0
);
// -Infinity
```

Nếu `magnitude` bằng `0.0`, hàm vẫn trả zero có dấu tương ứng; nếu `magnitude` là vô cực, hàm trả vô cực cùng dấu với `sign`.

### Trường hợp `NaN` và khác biệt với `StrictMath`

**Quan trọng về đặc tả Java 17:** Với đối số **`sign` là NaN**, `StrictMath.copySign` **luôn coi NaN đó có dấu dương**. Trong khi đó, `Math.copySign` **không bắt buộc** xử lý mọi NaN sign như dương; các triển khai được phép dùng bit dấu của một số mẫu NaN để tối ưu.

Vì vậy không nên viết logic nghiệp vụ dựa trên dấu của `NaN` rồi mong `Math.copySign` và `StrictMath.copySign` cho kết quả giống nhau trên mọi JVM.

Nếu `magnitude` là NaN, kết quả tiếp tục là NaN; **không dùng phép toán này như giao thức bảo toàn mọi bit payload NaN**. Nếu thực sự cần giữ nguyên mọi mẫu bit vào/ra (kể cả signaling NaN), làm việc với `int`/`long` chứa mẫu bit hay byte thô, vì quá trình đưa signaling NaN qua giá trị dấu phẩy động có thể quiet hóa.

**Khi nào dùng `copySign`?** Ví dụ dựng đáp số theo độ lớn đã biết nhưng cần duy trì dấu của phần tử gốc, giữ signed zero trong xử lý dấu phẩy động, hoặc thực hiện biến đổi biểu diễn có chủ đích. Nó không dùng để “chuẩn hóa giá trị” mà bỏ qua NaN.

## 3. `Math.scalb`: nhân chính xác theo một lũy thừa 2 khi có thể biểu diễn

Chữ ký:

```java
static double Math.scalb(double value, int scaleFactor)
static float Math.scalb(float value, int scaleFactor)
```

Hàm tính ý nghĩa toán học **\(value\times 2^{scaleFactor}\)** và trả kết quả dấu phẩy động với quy tắc làm tròn được định nghĩa. Ví dụ:

```java
Math.scalb(1.5, 3);   // 12.0
Math.scalb(3.0, -1);  // 1.5
Math.scalb(1.0, 10);  // 1024.0
Math.scalb(0.5f, 2);  // 2.0f
```

Khác với phép nhân một số `double` bất kỳ, nhân với lũy thừa 2 về cơ bản **dịch thang của exponent trong hệ nhị phân**. Với đầu vào normal phù hợp và kết quả vẫn ở miền normal có thể biểu diễn, phép scale có thể chính xác. Đây là lý do `scalb` hữu ích trong thuật toán số hoặc chuyển scale nhị phân.

Tuy nhiên, **không được tuyên bố mọi `scalb` đều không làm tròn**:

- Khi kết quả **subnormal**, có thể mất các bit chính xác ở phần trị.
- Khi kết quả quá lớn, có thể **overflow thành `±Infinity`**.
- Khi kết quả quá nhỏ, có thể **underflow thành `±0.0`**, vẫn giữ dấu.
- NaN vẫn là NaN; ±Infinity vẫn là vô cực cùng dấu; zero vẫn là zero cùng dấu.

`scalb` thực hiện scale theo hàm số học dấu phẩy động; **không đổi bit bằng cách tự ý cộng thẳng vào exponent raw**, vốn dễ sai với subnormal, NaN, Infinity và tràn số.

### Vì sao không luôn viết `x * Math.pow(2, n)`?

Công thức toán học giống nhau, nhưng:

```java
double a = Math.scalb(x, n);
// double b = x * Math.pow(2.0, n);
```

Dòng thứ hai tạo **kết quả trung gian `Math.pow(2.0, n)`** có thể overflow hoặc underflow trước khi nhân với `x`, và có thể làm tròn ở những điểm khác. `Math.scalb` nhằm thực hiện thao tác scale theo lũy thừa 2 với đặc tả kết quả riêng, tránh việc xây dựng hệ số trung gian không cần thiết.

Ví dụ, nếu `x` là một số rất nhỏ nhưng `2^n` lớn vượt miền `double`, `Math.pow(2, n)` có thể thành Infinity, còn tích lý tưởng vẫn hữu hạn. `Math.scalb(x, n)` là công cụ phù hợp hơn khi đây thực sự là phép scale cơ số 2.

Không nhầm `scalb` với `Math.pow(value, exponent)`: `scalb(value, n)` nhân `value` với `2^n`, **không** tính `value^n`.

## 4. Độ lớn cực trị: overflow, underflow và subnormal

Trong Java, một `double` có exponent normal tối đa 1023. Tăng scale quá mức có thể tạo vô cực:

```java
Math.scalb(Double.MAX_VALUE, 1);
// Infinity
```

Ở đầu nhỏ, `Double.MIN_VALUE` là subnormal dương nhỏ nhất:

```java
Math.scalb(Double.MIN_VALUE, -1); // 0.0 (underflow)
```

Khi đặt dấu âm cho giá trị nhỏ rồi scale xuống tiếp, dấu có thể vẫn tồn tại trong zero âm:

```java
double x = Math.scalb(-Double.MIN_VALUE, -1);
// -0.0; raw bits 0x8000000000000000
```

**Subnormal không phải lúc nào cũng bằng zero.** Ví dụ:

```java
double half = Math.scalb(Double.MIN_NORMAL, -1);
// Số subnormal dương, mẫu bit 0x0008000000000000L
```

Nó nhỏ hơn `Double.MIN_NORMAL` nhưng khác 0. Điều này giúp giải thích tại sao API `getExponent` ở phần sau trả **cùng một sentinel** cho nhiều giá trị subnormal rất khác nhau, chứ không phải exponent toán học riêng của từng giá trị.

**Không dùng `scalb` để bỏ qua kiểm tra miền:** Nếu đầu vào có thể là NaN/Infinity hoặc scale quá lớn, hãy đặt chính sách xác thực. Nếu tính toán yêu cầu kết quả hữu hạn, kiểm tra `Double.isFinite(result)` (hoặc `Float.isFinite`) sau phép scale và đánh giá khả năng underflow về zero khi đó là lỗi nghiệp vụ.

### Dấu của zero khi scale

`Math.scalb(-0.0, 1000)` vẫn cho **`-0.0`**. Không có gì để tăng lên thành số khác zero: scale chỉ nhân giá trị zero với một hệ số lũy thừa 2 dương về ý nghĩa, không đổi dấu bit zero.

Hàm không sửa đối số gốc, không có side effect trên biến `double` và không cần cấp phát wrapper để trả primitive.

## 5. `Math.getExponent`: xem trường exponent không bias

Chữ ký:

```java
static int Math.getExponent(double value)
static int Math.getExponent(float value)
```

Giá trị trả về là **`int`**, biểu diễn exponent không bias liên quan đến trường exponent IEEE 754. Đối với số **normal hữu hạn khác zero**, kết quả có thể hiểu như số mũ `e` sao cho độ lớn nằm trong khoảng:

\[
2^e \le |value| < 2^{e+1}
\]

Ví dụ:

```java
Math.getExponent(8.0);   // 3, vì 8 = 1 × 2^3
Math.getExponent(0.75);  // -1, vì 0.75 = 1.5 × 2^-1
Math.getExponent(-16.0); // 4; dấu không làm đổi exponent
```

**Nhưng với zero, subnormal, NaN hoặc vô cực, `getExponent` trả sentinel được API định nghĩa chứ không thực hiện `floor(log2(abs(value)))` theo nghĩa toán học.**

### Bảng kết quả `double`

| Đối số | `Math.getExponent(double)` | Giải thích |
| --- | ---: | --- |
| `8.0` | `3` | Normal, exponent 3 |
| `0.75` | `-1` | Normal, 0.75 = 1.5 × 2^-1 |
| `Double.MIN_NORMAL` | `-1022` | Normal nhỏ nhất |
| `Double.MAX_VALUE` | `1023` | Normal lớn nhất |
| `+0.0` hoặc `-0.0` | `-1023` | `Double.MIN_EXPONENT - 1` |
| `Double.MIN_VALUE` (subnormal) | `-1023` | Cùng sentinel với mọi subnormal |
| `Double.NaN` | `1024` | `Double.MAX_EXPONENT + 1` |
| `±Infinity` | `1024` | Cùng sentinel với NaN |

Với `float`, hai giá trị sentinel tương ứng là:

- Zero và subnormal: **`Float.MIN_EXPONENT - 1 = -127`**.
- NaN và ±Infinity: **`Float.MAX_EXPONENT + 1 = 128`**.

Ví dụ:

```java
Math.getExponent(0.0f);                      // -127
Math.getExponent(Float.MIN_VALUE);           // -127
Math.getExponent(Float.MIN_NORMAL);          // -126
Math.getExponent(Float.POSITIVE_INFINITY);   // 128
```

`Float.MIN_VALUE` có giá trị toán học `2^-149`, nhưng `Math.getExponent(Float.MIN_VALUE)` vẫn trả `-127`. `Double.MIN_VALUE` có giá trị toán học `2^-1074`, nhưng `Math.getExponent(Double.MIN_VALUE)` vẫn trả `-1023`. **Không đọc kết quả sentinel như log2 của subnormal.**

## 6. Vì sao `getExponent` không thay được `log2`?

Trong miền normal, ta có thể dùng kết quả exponent để biết **bậc độ lớn theo cơ số 2**. Nhưng:

- `getExponent(8.0)` là 3, không trả fraction/mantissa.
- `getExponent(12.0)` cũng là 3 vì `12 = 1.5 × 2^3`.
- `getExponent(0.0)` là `-1023`; không phải logarit của zero.
- `getExponent(Double.MIN_VALUE)` là `-1023`; trong khi exponent lũy thừa 2 của nó theo giá trị toán học là `-1074`.
- `getExponent(Double.NaN)` và `getExponent(Double.POSITIVE_INFINITY)` đều 1024; số sentinel không cho biết đối số là NaN hay vô cực.

Nếu cần logarithm thực của một giá trị dương hữu hạn, có thể cân nhắc `Math.log(value) / Math.log(2.0)` (có sai số dấu phẩy động), nhưng **không lấy nó làm phép bit-exact thay thế `getExponent`**. Với giải mã exponent raw và logic xử lý subnormal chuyên sâu, cần hiểu format và xây thuật toán riêng.

### Làm sao phân biệt trường hợp đặc biệt?

```java
double x = Double.MIN_VALUE;
int e = Math.getExponent(x);

if (Double.isNaN(x)) {
    // NaN: không dùng e như exponent của số hữu hạn
} else if (Double.isInfinite(x)) {
    // Infinity
} else if (x == 0.0) {
    // +0.0 hoặc -0.0
} else if (e == Double.MIN_EXPONENT - 1) {
    // x là subnormal khác zero
} else {
    // x là số normal hữu hạn khác zero
}
```

Đây là **đoạn mã minh họa**, cần đặt trong một phương thức/class khi sử dụng. Thứ tự kiểm tra có chủ đích: `e == Double.MIN_EXPONENT - 1` tự nó **không phân biệt** zero và subnormal; `e == Double.MAX_EXPONENT + 1` tự nó **không phân biệt** NaN và vô cực.

Cách kiểm tra trên phù hợp khi thuật toán cần tách trường hợp normal/subnormal. Nhiều ứng dụng thông thường chỉ cần `Double.isFinite`, kiểm tra zero và xử lý ngoại lệ input; không cần thao tác exponent bit-level.

## 7. Phối hợp ba hàm mà không làm sai ý nghĩa

Ba API rất hữu ích khi có thuật toán xử lý **dấu tách biệt**, **scale riêng** và **exponent riêng**.

Ví dụ một pipeline ý tưởng:

```java
double input = -12.0;
int e = Math.getExponent(input);     // 3
double base = Math.scalb(input, -e); // -1.5
double positiveBase = Math.copySign(base, +1.0); // 1.5
```

Đối với số normal hữu hạn khác zero, `base` thường có độ lớn từ `1` đến dưới `2`, vì ta chia giá trị cho `2^e`. `copySign` sau đó chuyển sang độ lớn dương mà vẫn dùng semantics của dấu bit.

**Caveat:** Đừng áp dụng pipeline “chuẩn hóa” trên vào mọi giá trị:

- `input == 0.0`: `getExponent` trả sentinel, không phải exponent hữu ích để chuẩn hóa số 0.
- `input` subnormal: sentinel của `getExponent` không phải exponent thực tương ứng từng giá trị; `scalb(input, -e)` chưa chắc có phần trị chuẩn hóa như mong muốn.
- `input` NaN/Infinity: phải xử lý riêng, nếu không kết quả chuẩn hóa không đại diện số hữu hạn.
- Scale có thể overflow/underflow hoặc giảm độ chính xác với giá trị cực trị.

Nếu thuật toán yêu cầu chuẩn hóa số thực chính xác hơn, hãy xây dựng quy tắc miền và bộ kiểm thử riêng thay vì chỉ ghép ba hàm theo cảm giác.

## 8. `Math` và `StrictMath`: khác biệt thực tế

Cả hai class đều có overload `copySign`, `scalb` và `getExponent` cho `float`/`double` tương ứng. Chúng là **static methods**, không tạo đối tượng `Math` hoặc `StrictMath`.

| Vấn đề | `Math` | `StrictMath` |
| --- | --- | --- |
| `copySign` với dấu hữu hạn (kể cả zero) | Lấy dấu bit từ đối số `sign` | Cùng ngữ nghĩa |
| `copySign` khi **`sign` là NaN** | Được phép không luôn coi NaN là dấu dương | **Bắt buộc coi NaN sign là dương** |
| `scalb` | Nhân với lũy thừa 2 theo đặc tả scale/rounding | Cùng đặc tả số học cho hàm tương ứng |
| `getExponent` | Trả exponent không bias và sentinel | Cùng bảng sentinel |
| Kiểu giá trị trả | `copySign/scalb`: `float` hoặc `double`; `getExponent`: `int` | Tương ứng |

Không suy luận từ tên `StrictMath` rằng mọi hàm trong class này luôn cho giá trị khác `Math`. Trong các trường hợp hữu hạn thông thường, kết quả thường giống nhau. Điểm khác cụ thể, quan trọng của nhóm API bài này là **xử lý đối số dấu NaN của `copySign`** theo cam kết trong tài liệu Java.

Khi cần kết quả dự đoán được ở trường hợp NaN sign theo API, dùng `StrictMath.copySign` và xác định quy tắc xử lý NaN ngay từ thiết kế. Khi các tham số đều hữu hạn phù hợp, `Math` thường là API trực tiếp thuận tiện.

## 9. Chương trình hoàn chỉnh Java 17+ để tự kiểm tra

Tạo tệp `FloatingScaleDemo.java`:

```java
public class FloatingScaleDemo {
    static String hex(double x) {
        return String.format("%016x", Double.doubleToRawLongBits(x));
    }

    public static void main(String[] args) {
        System.out.println("copySign(3.5, -0.0): "
            + Math.copySign(3.5, -0.0));
        System.out.println("copySign(-3.5, +0.0): "
            + Math.copySign(-3.5, +0.0));
        System.out.println("copySign(infinity, -1): "
            + Math.copySign(Double.POSITIVE_INFINITY, -1.0));
        System.out.println("copySign(+0.0, -1.0) raw: "
            + hex(Math.copySign(0.0, -1.0)));
        System.out.println("float copySign: "
            + Math.copySign(2.5f, -0.0f));
        System.out.println("strict copySign: "
            + StrictMath.copySign(3.5, -1.0));

        System.out.println("scalb(1.5,3): " + Math.scalb(1.5, 3));
        System.out.println("scalb(3,-1): " + Math.scalb(3.0, -1));
        System.out.println("scalb zero raw: "
            + hex(Math.scalb(-0.0, 1000)));
        System.out.println("scalb underflow: "
            + Math.scalb(Double.MIN_VALUE, -1));
        System.out.println("scalb negative underflow raw: "
            + hex(Math.scalb(-Double.MIN_VALUE, -1)));
        System.out.println("scalb overflow: "
            + Math.scalb(Double.MAX_VALUE, 1));
        System.out.println("scalb min-normal/2 raw: "
            + hex(Math.scalb(Double.MIN_NORMAL, -1)));
        System.out.println("strict scalb: "
            + StrictMath.scalb(1.5, 3));

        System.out.println("exp(8.0): " + Math.getExponent(8.0));
        System.out.println("exp(0.75): " + Math.getExponent(0.75));
        System.out.println("exp(0.0): " + Math.getExponent(0.0));
        System.out.println("exp(min subnormal): "
            + Math.getExponent(Double.MIN_VALUE));
        System.out.println("exp(min normal): "
            + Math.getExponent(Double.MIN_NORMAL));
        System.out.println("exp(max): "
            + Math.getExponent(Double.MAX_VALUE));
        System.out.println("exp(NaN): "
            + Math.getExponent(Double.NaN));
        System.out.println("exp(infinity): "
            + Math.getExponent(Double.POSITIVE_INFINITY));

        System.out.println("float exp(zero): "
            + Math.getExponent(0.0f));
        System.out.println("float exp(min normal): "
            + Math.getExponent(Float.MIN_NORMAL));
        System.out.println("float exp(infinity): "
            + Math.getExponent(Float.POSITIVE_INFINITY));
        System.out.println("strict getExponent: "
            + StrictMath.getExponent(8.0));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingScaleDemo.java
java FloatingScaleDemo
```

Stdout từ chương trình (đã đối chiếu với JDK):

```text
copySign(3.5, -0.0): -3.5
copySign(-3.5, +0.0): 3.5
copySign(infinity, -1): -Infinity
copySign(+0.0, -1.0) raw: 8000000000000000
float copySign: -2.5
strict copySign: -3.5
scalb(1.5,3): 12.0
scalb(3,-1): 1.5
scalb zero raw: 8000000000000000
scalb underflow: 0.0
scalb negative underflow raw: 8000000000000000
scalb overflow: Infinity
scalb min-normal/2 raw: 0008000000000000
strict scalb: 12.0
exp(8.0): 3
exp(0.75): -1
exp(0.0): -1023
exp(min subnormal): -1023
exp(min normal): -1022
exp(max): 1023
exp(NaN): 1024
exp(infinity): 1024
float exp(zero): -127
float exp(min normal): -126
float exp(infinity): 128
strict getExponent: 3
```

**Hướng dẫn đọc output:**

- Sáu dòng `copySign` cho thấy dấu của zero âm có ý nghĩa, kể cả khi giá trị so sánh bằng zero dương. `StrictMath` với đối số bình thường trả cùng kết quả.
- Tám dòng `scalb` chứng minh tăng/giảm lũy thừa của 2, dấu zero, overflow thành infinity và underflow thành zero/subnormal.
- Các dòng `getExponent` phân biệt normal với các sentinel: `double` zero/subnormal là `-1023`, NaN/infinity là `1024`; `float` tương ứng `-127` và `128`.
- Hàm `hex` dùng **mẫu bit raw** để phân biệt zero âm/dương; số hiển thị dạng hexa đã pad đủ 16 ký tự cho `double`.

## 10. Khi nào nên dùng ba API này?

| Nhu cầu | API nên chọn | Lưu ý |
| --- | --- | --- |
| Gắn dấu từ một giá trị tham chiếu | `Math.copySign` | Nhận cả dấu của `-0.0` |
| Yêu cầu NaN sign luôn được coi dương | `StrictMath.copySign` | Khác cam kết `Math.copySign` với NaN sign |
| Nhân/chia theo lũy thừa 2 | `Math.scalb` | Theo dõi overflow/underflow |
| Điều chỉnh scale cho số `float` | `Math.scalb(float, int)` | Kết quả vẫn là `float` |
| Quan sát bậc exponent của số normal | `Math.getExponent` | Không phải logarit tổng quát |
| Phân loại zero/subnormal/special | `getExponent` kết hợp `isNaN`/`isInfinite`/kiểm tra zero | Sentinel một mình chưa đủ |
| Xem mẫu bit thật | `Double.doubleToRawLongBits`/`Float.floatToRawIntBits` | Không nhầm API quan sát bit với numeric scaling |
| Kiểm tra giá trị hữu hạn | `Double.isFinite`/`Float.isFinite` | Phải dùng rõ ràng nếu hợp đồng yêu cầu |

Ví dụ xử lý dữ liệu khoa học, biểu diễn số trong thuật toán chuẩn hóa, giải mã tín hiệu hoặc thống kê có miền độ lớn trải rộng thường cần các hàm trên. Nhưng đừng dùng chúng chỉ vì tưởng rằng hàm cấp thấp luôn “chính xác hơn”: **lựa chọn bắt nguồn từ thao tác mong muốn và giới hạn biểu diễn**.

## 11. Các nhầm lẫn thường gặp

1. **“`copySign(x, y)` tính `x * y`.”** Sai: nó lấy độ lớn của `x` và dấu của `y`.
2. **“`copySign` với `-0.0` giống với dấu dương vì `-0.0 == 0.0`.”** Sai: bit dấu được giữ và được áp dụng.
3. **“`Math.copySign` và `StrictMath.copySign` có cam kết hoàn toàn giống nhau với NaN sign.”** Sai: `StrictMath` coi NaN sign là dương; `Math` được phép khác.
4. **“`scalb(x, n)` là `Math.pow(x, n)`.”** Sai: `scalb` tính `x × 2^n`.
5. **“`scalb` luôn chính xác đến mọi bit, kể cả subnormal.”** Sai: underflow/rounding có thể mất độ chính xác hoặc tạo zero.
6. **“Tính `x * Math.pow(2,n)` luôn an toàn tương đương `scalb`.”** Sai: biểu thức có kết quả trung gian có thể overflow/underflow trước khi nhân.
7. **“`getExponent(x)` luôn trả `floor(log2(abs(x)))`.”** Sai với zero, subnormal, NaN và Infinity.
8. **“`Math.getExponent(Double.MIN_VALUE) == -1074`.”** Sai: API trả `-1023` cho mọi subnormal `double`.
9. **“`Math.getExponent(0.0)` và `Math.getExponent(Double.MIN_VALUE)` khác nhau.”** Sai: đều `-1023`.
10. **“`getExponent` trả `Double.MIN_EXPONENT` khi zero.”** Sai: trả `Double.MIN_EXPONENT - 1`.
11. **“`getExponent` trả NaN nếu đầu vào là NaN.”** Sai: return type là `int` và trả sentinel `MAX_EXPONENT + 1`.
12. **“`getExponent` phân biệt NaN với vô cực chỉ từ kết quả.”** Sai: chúng có cùng sentinel.
13. **“`Double.MIN_VALUE` là giá trị âm nhỏ nhất của `double`.”** Sai: đó là số dương subnormal nhỏ nhất.
14. **“`scalb(-0.0, k)` trở thành `+0.0` vì nhân với lũy thừa 2 dương.”** Sai: dấu zero được giữ.
15. **“`copySign` có thể thay mọi thao tác chuyển dấu của NaN mà vẫn bảo toàn payload.”** Sai: không coi đây là giao thức bit-perfect cho mọi dạng NaN.

## 12. Tự kiểm tra

**1. `Math.copySign(5.0, -0.0)` trả gì?** → `-5.0`, vì `-0.0` mang dấu âm.

**2. `Math.copySign(-5.0, +0.0)` trả gì?** → `5.0`, vì độ lớn 5 mang dấu dương mới.

**3. `Math.scalb(1.25, 3)` trả gì?** → `10.0`, do `1.25 × 2^3`.

**4. `Math.scalb(3.0, -1)` trả gì?** → `1.5`.

**5. `Math.scalb(Double.MAX_VALUE, 1)` trả gì?** → `Infinity` vì overflow.

**6. `Math.scalb(-Double.MIN_VALUE, -1)` có dấu gì?** → `-0.0`; bit dấu âm được bảo toàn.

**7. `Math.getExponent(0.75)` là bao nhiêu?** → `-1`.

**8. `Math.getExponent(Double.MIN_NORMAL)` và `Math.getExponent(Double.MIN_VALUE)` có bằng nhau không?** → Không: lần lượt `-1022` và `-1023`.

**9. `Math.getExponent(Double.NaN)` so với `Math.getExponent(Double.POSITIVE_INFINITY)`?** → Đều `1024`, nên phải dùng API phân loại riêng nếu cần phân biệt.

**10. `Math.getExponent(Float.MIN_VALUE)` có bằng `-149` không?** → Không: trả `-127` sentinel cho subnormal.

**11. `Math.copySign` và `StrictMath.copySign` có gì khác nếu sign là NaN?** → `StrictMath` luôn coi NaN sign như dấu dương; `Math` được phép xử lý dấu một số NaN khác nhau theo triển khai.

**Ghi nhớ:** `copySign` làm việc với **dấu bit**; `scalb` thay đổi **thang lũy thừa 2** với quy tắc làm tròn/overflow/underflow; `getExponent` đọc **số mũ không bias** của biểu diễn và trả sentinel cho **zero, subnormal, NaN, infinity**. Khi dùng trong thuật toán, hãy phân loại giá trị đặc biệt, giữ đúng kiểu `float`/`double` và không nhầm kết quả bit-level với logarit hoặc số học chính xác vô hạn.
