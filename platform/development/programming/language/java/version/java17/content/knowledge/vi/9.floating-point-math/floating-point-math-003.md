# Giới hạn độ chính xác khi cộng, nhân và chia số thực trong Java 17

Trong Java, các kiểu số thực như `float` và `double` lưu giá trị theo dạng dấu phẩy động nhị phân (*binary floating-point*). Chúng có phạm vi biểu diễn rất rộng và tính toán nhanh, nhưng **không thể biểu diễn chính xác mọi số thập phân**. Vì vậy, kết quả của phép cộng, nhân hoặc chia có thể lệch một lượng rất nhỏ so với kết quả toán học mà ta mong đợi.

Ví dụ quen thuộc:

```java
double result = 0.1 + 0.2;
System.out.println(result);
System.out.println(result == 0.3);
```

Kết quả thường thấy:

```text
0.30000000000000004
false
```

Đây không phải lỗi ngẫu nhiên của Java. Nó xuất phát từ cách số thực nhị phân biểu diễn và làm tròn kết quả. Khi hiểu cơ chế này, bạn có thể chọn đúng kiểu dữ liệu, so sánh số thực hợp lý và dùng `BigDecimal` khi bài toán yêu cầu số thập phân chính xác.

## 1. Java biểu diễn số thực như thế nào?

Java có hai kiểu số thực nguyên thủy phổ biến:

| Kiểu | Định dạng | Độ chính xác nhị phân | Độ chính xác thập phân thường dùng |
| --- | --- | ---: | ---: |
| `float` | IEEE 754 binary32 | 24 bit significand (bao gồm bit ẩn của số chuẩn hóa) | Khoảng 6–9 chữ số có nghĩa |
| `double` | IEEE 754 binary64 | 53 bit significand (bao gồm bit ẩn của số chuẩn hóa) | Khoảng 15–17 chữ số có nghĩa |

Trong Java:

- Một literal thập phân như `1.25` mặc định có kiểu `double`.
- Thêm hậu tố `f` hoặc `F` để tạo literal kiểu `float`, ví dụ `1.25f`.
- Hậu tố `d` hoặc `D` có thể dùng để chỉ rõ `double`, nhưng thường không cần.
- `double` thường là lựa chọn mặc định cho phép tính số thực nếu không có yêu cầu khác.

Một giá trị dấu phẩy động được biểu diễn gần đúng theo dạng:

\[
(-1)^{sign} \times significand \times 2^{exponent}
\]

Phần significand có số bit hữu hạn. Vì thế, chỉ những phân số có thể biểu diễn bằng một tổng hữu hạn các lũy thừa của 2 mới có biểu diễn nhị phân hữu hạn. Các phân số như \(1/2\), \(1/4\), \(3/8\) biểu diễn chính xác; các phân số như \(1/10\), \(1/5\), \(1/3\) có chuỗi nhị phân vô hạn và phải được làm tròn.

### 1.1. Vì sao 0.1 không được biểu diễn chính xác?

Trong hệ thập phân, `0.1` có biểu diễn hữu hạn. Nhưng trong hệ nhị phân, giá trị đó có dạng lặp vô hạn, tương tự cách \(1/3\) có dạng `0.3333...` trong hệ thập phân.

Máy chỉ có một số bit hữu hạn để lưu significand, nên phải chọn giá trị nhị phân gần nhất có thể biểu diễn. Khi đọc lại hoặc in ra, Java chuyển giá trị đó thành chuỗi thập phân ngắn nhất có thể phân biệt với các giá trị dấu phẩy động lân cận.

Ví dụ:

```java
public class FloatingPointRepresentation {
    public static void main(String[] args) {
        double value = 0.1;
        System.out.printf("Default: %.17f%n", value);
        System.out.printf("Sum:     %.17f%n", 0.1 + 0.2);

        float floatValue = 0.1f;
        System.out.printf("float:   %.9f%n", floatValue);
    }
}
```

Đầu ra minh họa:

```text
Default: 0.10000000000000000
Sum:     0.30000000000000004
float:   0.100000001
```

Định dạng in có số chữ số sau dấu thập phân được chỉ định bởi `printf`. Nó giúp nhìn rõ sai số; không có nghĩa biến `value` thực sự chứa chuỗi thập phân được in ra.

### 1.2. Số nguyên lớn cũng có thể mất độ chính xác khi đổi sang double

`double` có 53 bit độ chính xác significand. Vì vậy, mọi số nguyên liên tiếp đều biểu diễn chính xác trong phạm vi đến \(2^{53}\); vượt qua mốc đó, khoảng cách giữa các giá trị biểu diễn được lớn hơn 1.

Ví dụ:

```java
public class IntegerPrecision {
    public static void main(String[] args) {
        double value = 9_007_199_254_740_992d; // 2^53

        System.out.println(value);
        System.out.println(value + 1.0);
        System.out.println(value == value + 1.0);
    }
}
```

Kết quả:

```text
9.007199254740992E15
9.007199254740992E15
true
```

Số nguyên \(2^{53}+1\) không thể được biểu diễn chính xác bằng `double`. Nếu cần lưu số nguyên lớn, hãy cân nhắc `long` hoặc `BigInteger` tùy phạm vi. Đổi một số nguyên lớn sang `double` chỉ để tính toán có thể làm mất đơn vị.

## 2. Phép cộng: sai số có thể tích lũy hoặc làm mất phần nhỏ

Khi cộng hai số dấu phẩy động, kết quả toán học thường được làm tròn về một giá trị `float` hoặc `double` gần nhất có thể biểu diễn. Sai số nhỏ của mỗi phép cộng có thể tích lũy khi lặp lại nhiều lần.

### 2.1. Cộng lặp lại không nhất thiết bằng phép nhân

Ví dụ:

```java
public class RepeatedAddition {
    public static void main(String[] args) {
        double sum = 0.0;

        for (int i = 0; i < 10; i++) {
            sum += 0.1;
        }

        System.out.printf("%.17f%n", sum);
        System.out.println(sum == 1.0);
    }
}
```

Kết quả có thể hiển thị:

```text
0.99999999999999990
false
```

Mỗi lần cộng đều làm tròn về giá trị biểu diễn được. Sai số nhỏ của nhiều bước có thể khiến kết quả cuối khác giá trị toán học chính xác.

### 2.2. Cộng số rất nhỏ vào số rất lớn

Giả sử:

```java
double large = 1e16;
double small = 1.0;

System.out.println(large + small == large);
```

Kết quả là `true` trên binary64. Ở độ lớn \(10^{16}\), khoảng cách giữa các giá trị `double` biểu diễn được đã lớn hơn 1; thêm 1 không làm kết quả thay đổi sau khi làm tròn.

Hiện tượng này thường được gọi là **absorption**: phần đóng góp nhỏ bị hấp thụ khi cộng với một giá trị lớn.

### 2.3. Phép cộng số thực không có tính kết hợp tuyệt đối

Trong toán học:

\[
(a+b)+c = a+(b+c)
\]

Nhưng với số thực dấu phẩy động, do mỗi bước có thể làm tròn, hai cách nhóm phép cộng có thể cho kết quả khác nhau:

```java
public class AdditionOrder {
    public static void main(String[] args) {
        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        System.out.println((a + b) + c);
        System.out.println(a + (b + c));
    }
}
```

Đầu ra minh họa:

```text
1.0
0.0
```

Ở biểu thức thứ hai, `b + c` làm mất phần `1.0` vì nó quá nhỏ so với độ lớn của `b`. Sau đó cộng `a` cho ra 0.

Vì vậy, **không nên tự ý thay đổi thứ tự nhóm phép tính số thực** với giả định rằng hai biểu thức luôn tương đương. Tối ưu hóa hoặc tái cấu trúc biểu thức có thể làm thay đổi kết quả dấu phẩy động.

### 2.4. Cộng dồn nhiều giá trị: kỹ thuật bù sai số

Khi cần cộng một lượng lớn giá trị dấu phẩy động, thuật toán Kahan (*compensated summation*) có thể giảm một số sai số do mất phần nhỏ:

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double adjusted = value - compensation;
        double next = sum + adjusted;
        compensation = (next - sum) - adjusted;
        sum = next;
    }

    return sum;
}
```

Biến `compensation` ghi nhận phần sai lệch bị mất trong lần cộng trước để bù vào lần tiếp theo. Kỹ thuật này hữu ích cho một số phép cộng dồn, nhưng **không biến `double` thành số chính xác tuyệt đối** và không thay thế việc chọn thuật toán phù hợp với dữ liệu.

## 3. Phép nhân: kết quả có thể cần nhiều bit hơn khả năng lưu trữ

Hai số có biểu diễn hữu hạn khi nhân với nhau có thể tạo ra một kết quả cần nhiều bit significand hơn số bit mà kiểu đích có thể giữ. Kết quả phải được làm tròn.

Ví dụ:

```java
public class MultiplicationPrecision {
    public static void main(String[] args) {
        double result = 0.1 * 0.1;
        System.out.printf("%.18f%n", result);
    }
}
```

Kết quả hiển thị thường là:

```text
0.010000000000000002
```

Giá trị toán học \(0.1 \times 0.1 = 0.01\), nhưng hai toán hạng đã được biểu diễn gần đúng; phép nhân và bước làm tròn tiếp tục tạo ra sai lệch.

### 3.1. Tràn số (*overflow*)

Nếu kết quả có độ lớn vượt phạm vi hữu hạn của kiểu, giá trị có thể trở thành vô cực dương hoặc âm.

```java
public class FloatingOverflow {
    public static void main(String[] args) {
        double value = Double.MAX_VALUE;
        double result = value * 2.0;

        System.out.println(result);
        System.out.println(Double.isInfinite(result));
    }
}
```

Đầu ra:

```text
Infinity
true
```

Đối với số thực, tràn số thường không ném `ArithmeticException` như phép chia số nguyên cho 0; kết quả có thể là `Infinity`. Nếu giá trị vô cực không hợp lệ trong nghiệp vụ, hãy kiểm tra bằng `Double.isFinite(value)` hoặc `Float.isFinite(value)` và xử lý phù hợp.

### 3.2. Nhân với số rất nhỏ và underflow

Ngược lại, nếu độ lớn kết quả quá nhỏ so với phạm vi biểu diễn, kết quả có thể tiến về 0. Đây là hiện tượng **underflow**.

IEEE 754 có vùng số dưới chuẩn hóa (*subnormal numbers*) để biểu diễn các giá trị dương rất nhỏ ngay dưới giá trị normal nhỏ nhất. Khi còn trong vùng này, độ chính xác tương đối giảm dần. Nếu nhỏ hơn khả năng biểu diễn, kết quả có thể làm tròn về 0.

Ví dụ:

```java
public class FloatingUnderflow {
    public static void main(String[] args) {
        double smallestPositive = Double.MIN_VALUE;

        System.out.println(smallestPositive);
        System.out.println(smallestPositive / 2.0);
        System.out.println(smallestPositive / 2.0 == 0.0);
    }
}
```

`Double.MIN_VALUE` là số dương nhỏ nhất khác 0 có thể biểu diễn bằng `double` (một số subnormal). Chia nó cho 2 có thể làm tròn về 0.

### 3.3. Tràn số nguyên và tràn số thực khác nhau

| Phép tính | Kết quả khi vượt phạm vi |
| --- | --- |
| `int` hoặc `long` cộng/nhân vượt phạm vi | Tràn theo biểu diễn số nguyên có dấu; thông thường không tự ném ngoại lệ. |
| `float` hoặc `double` vượt phạm vi hữu hạn | Có thể cho `Infinity` hoặc `-Infinity`. |
| `Math.addExact` / `Math.multiplyExact` với số nguyên vượt phạm vi | Ném `ArithmeticException`. |

Nếu nghiệp vụ yêu cầu phát hiện tràn số nguyên, hãy dùng các phương thức `Math.*Exact` phù hợp thay vì chờ giá trị tự quay vòng.

## 4. Phép chia: số thập phân lặp và chia cho 0

Nhiều kết quả phép chia không có biểu diễn nhị phân hữu hạn. Ví dụ:

```java
public class DivisionPrecision {
    public static void main(String[] args) {
        double oneThird = 1.0 / 3.0;
        double oneTenth = 1.0 / 10.0;

        System.out.printf("%.17f%n", oneThird);
        System.out.printf("%.17f%n", oneTenth);
    }
}
```

Kết quả minh họa:

```text
0.33333333333333330
0.10000000000000001
```

Đây là các giá trị dấu phẩy động gần nhất có thể biểu diễn, không phải phân số thập phân vô hạn được lưu đầy đủ.

### 4.1. Chia số nguyên và chia số thực có hành vi khác nhau

```java
System.out.println(1 / 2);       // 0
System.out.println(1.0 / 2.0);   // 0.5
```

`1 / 2` là phép chia số nguyên; phần thập phân bị bỏ. Khi ít nhất một toán hạng là số thực, phép chia diễn ra theo kiểu dấu phẩy động và kết quả có thể giữ phần lẻ gần đúng.

### 4.2. Chia số thực cho 0

Với `float` và `double`, chia cho số 0 tuân theo các quy tắc dấu phẩy động:

```java
public class FloatingDivisionByZero {
    public static void main(String[] args) {
        System.out.println(1.0 / 0.0);
        System.out.println(-1.0 / 0.0);
        System.out.println(0.0 / 0.0);

        System.out.println(Double.isInfinite(1.0 / 0.0));
        System.out.println(Double.isNaN(0.0 / 0.0));
    }
}
```

Kết quả:

```text
Infinity
-Infinity
NaN
true
true
```

Trong khi đó, chia số nguyên cho 0:

```java
int result = 1 / 0; // Ném ArithmeticException khi thực thi.
```

Đừng áp dụng quy tắc của phép chia số nguyên cho phép chia số thực.

### 4.3. NaN và vô cực ảnh hưởng đến so sánh

`NaN` (*Not a Number*) biểu thị một kết quả không phải số thực hữu hạn, ví dụ `0.0 / 0.0`. Các phép so sánh có hành vi đặc biệt:

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(value != value); // true
System.out.println(value < 1.0);    // false
System.out.println(value > 1.0);    // false
System.out.println(Double.isNaN(value)); // true
```

Vì vậy, không kiểm tra NaN bằng `value == Double.NaN`. Hãy dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

Nếu cần từ chối cả vô cực lẫn NaN:

```java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Value must be finite");
}
```

## 5. Số 0 có dấu trong floating-point

IEEE 754 có cả `+0.0` và `-0.0`. Trong phép so sánh thông thường của Java:

```java
System.out.println(+0.0 == -0.0); // true
```

Nhưng dấu của số 0 có thể ảnh hưởng đến một số phép tính:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Do đó, nếu ứng dụng cần phân biệt hai dạng zero, không thể chỉ dựa vào toán tử `==`. Có thể dùng `Double.doubleToRawLongBits(value)` hoặc `Double.compare(a, b)` tùy mục tiêu so sánh.

Trong phần lớn nghiệp vụ thông thường, hai số 0 được xem là bằng nhau. Nhưng trong một số phép tính khoa học, hình học hoặc xử lý dấu, dấu zero có thể mang thông tin có ý nghĩa.

## 6. Vì sao không nên so sánh kết quả số thực bằng `==`?

Nếu hai giá trị được tính qua các chuỗi phép toán khác nhau, sai số làm tròn có thể khiến chúng lệch nhau dù về toán học bạn kỳ vọng chúng bằng nhau.

Ví dụ:

```java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a == b); // false
```

Một cách thường dùng là so sánh với **dung sai** (*tolerance*):

\[
|a-b| \le \varepsilon
\]

Trong đó \(\varepsilon\) là sai số tối đa mà ứng dụng chấp nhận.

### 6.1. Dung sai tuyệt đối

```java
static boolean nearlyEqualAbsolute(
        double a, double b, double tolerance) {
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    return Math.abs(a - b) <= tolerance;
}
```

Ví dụ:

```java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(nearlyEqualAbsolute(a, b, 1e-12)); // true
```

Dung sai tuyệt đối phù hợp khi miền giá trị có thang đo tương đối ổn định, chẳng hạn tọa độ có đơn vị mét trong một phạm vi đã biết.

### 6.2. Dung sai tương đối kết hợp dung sai tuyệt đối

Nếu dữ liệu có độ lớn thay đổi rất nhiều, chỉ dùng một dung sai tuyệt đối có thể không phù hợp. Có thể kết hợp:

\[
|a-b| \le \max(\varepsilon_{abs},
              \varepsilon_{rel}\times\max(|a|,|b|))
\]

Ví dụ:

```java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0 || relativeTolerance < 0) {
        throw new IllegalArgumentException("Tolerance must be non-negative");
    }

    if (a == b) {
        return true; // Bao gồm hai số 0 có dấu và cùng một vô cực.
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double tolerance = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= tolerance;
}
```

Không có một giá trị `epsilon` phù hợp cho mọi bài toán. Dung sai phải xuất phát từ đơn vị, độ lớn, độ chính xác đầu vào và yêu cầu nghiệp vụ. Chọn một hằng số tùy ý rồi dùng cho mọi phép so sánh có thể che giấu lỗi hoặc từ chối các kết quả hợp lệ.

### 6.3. Khi nào so sánh chính xác vẫn phù hợp?

`==` vẫn phù hợp trong một số trường hợp:

- So sánh giá trị sentinel hoặc hằng số mà ứng dụng chủ động thiết kế.
- Kiểm tra `NaN` không phù hợp; phải dùng `isNaN`.
- So sánh giá trị được sao chép nguyên vẹn mà không qua phép tính.
- So sánh số nguyên hoặc kiểu dữ liệu có biểu diễn chính xác trong miền giá trị.

Với số thực tính toán, hãy xác định rõ ý nghĩa “bằng nhau” trong bài toán thay vì mặc định dùng `==`.

## 7. `BigDecimal`: khi cần số thập phân chính xác

`BigDecimal` thuộc `java.math` và biểu diễn số thập phân bằng một số nguyên không giới hạn độ dài kết hợp với scale. Nó phù hợp với các bài toán mà quy tắc thập phân và làm tròn cần được kiểm soát, chẳng hạn:

- Tiền tệ và hóa đơn.
- Thuế, chiết khấu, lãi suất theo quy tắc nghiệp vụ.
- Giá trị đo hoặc tỷ lệ yêu cầu số chữ số thập phân xác định.
- Trao đổi dữ liệu mà biểu diễn thập phân cần ổn định.

### 7.1. Tạo BigDecimal từ chuỗi

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

Chuỗi `"0.1"` biểu diễn chính xác số thập phân 0.1. Phép cộng `BigDecimal` chính xác nếu không yêu cầu làm tròn qua `MathContext`.

### 7.2. Vì sao không nên dùng new BigDecimal(double)?

Không nên viết:

```java
BigDecimal value = new BigDecimal(0.1);
System.out.println(value);
```

Vì `0.1` đã được biểu diễn gần đúng bằng `double` trước khi truyền vào constructor. `BigDecimal(double)` tạo giá trị thập phân chính xác tương ứng với giá trị nhị phân `double` đó, nên kết quả có nhiều chữ số:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Hãy ưu tiên:

```java
new BigDecimal("0.1")
```

Hoặc khi đã có một giá trị `double` và muốn chuyển chuỗi thập phân chuẩn mà `Double.toString` tạo ra:

```java
BigDecimal.valueOf(0.1)
```

`BigDecimal.valueOf(double)` thường phù hợp hơn `new BigDecimal(double)` trong trường hợp này, nhưng nó **không khôi phục được độ chính xác đã mất trước đó** nếu `double` là kết quả của nhiều phép tính sai số.

### 7.3. Cộng, trừ và nhân

```java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal discount = new BigDecimal("5.00");

BigDecimal subtotal = price.multiply(quantity);
BigDecimal total = subtotal.subtract(discount);

System.out.println(subtotal); // 59.70
System.out.println(total);    // 54.70
```

Các phép toán trả về đối tượng `BigDecimal` mới. `BigDecimal` là immutable, vì vậy nếu muốn lưu kết quả, phải gán lại:

```java
BigDecimal amount = new BigDecimal("10.00");
amount.add(new BigDecimal("2.00")); // Kết quả bị bỏ qua.
amount = amount.add(new BigDecimal("2.00"));
```

### 7.4. Chia và quy tắc làm tròn

Phép chia thập phân có thể tạo ra số chữ số vô hạn. Ví dụ \(1/3 = 0.3333...\). Vì thế:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(three); // ArithmeticException
```

Nếu thương có biểu diễn thập phân không kết thúc, `divide(divisor)` không thể tạo kết quả chính xác hữu hạn và ném `ArithmeticException`.

Bạn cần chỉ rõ scale và `RoundingMode`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        2,
        RoundingMode.HALF_UP);

System.out.println(result); // 0.33
```

Hoặc dùng `MathContext` để quy định độ chính xác theo **số chữ số có nghĩa**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(6, RoundingMode.HALF_EVEN);
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), context);

System.out.println(result); // 0.333333
```

Phân biệt:

| Cách chỉ định | Ý nghĩa |
| --- | --- |
| `divide(divisor, 2, mode)` | Kết quả có scale 2, tức 2 chữ số sau dấu thập phân. |
| `divide(divisor, new MathContext(6, mode))` | Kết quả được làm tròn theo 6 chữ số có nghĩa. |
| `setScale(2, mode)` | Chuẩn hóa giá trị hiện tại về scale 2 theo quy tắc làm tròn đã chọn. |

### 7.5. Các chế độ làm tròn thường gặp

`RoundingMode` cung cấp các quy tắc làm tròn rõ ràng:

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| `UP` | Làm tròn ra xa 0 nếu phải bỏ phần khác 0. |
| `DOWN` | Bỏ phần dư về phía 0. |
| `CEILING` | Làm tròn về phía dương vô cực. |
| `FLOOR` | Làm tròn về phía âm vô cực. |
| `HALF_UP` | Gần nhất; trường hợp đúng giữa hai giá trị thì làm tròn ra xa 0. |
| `HALF_DOWN` | Gần nhất; trường hợp đúng giữa thì làm tròn về phía 0. |
| `HALF_EVEN` | Gần nhất; trường hợp đúng giữa thì chọn chữ số cuối chẵn. |
| `UNNECESSARY` | Yêu cầu không được phát sinh làm tròn; nếu cần làm tròn thì ném ngoại lệ. |

Ví dụ:

```java
BigDecimal amount = new BigDecimal("2.345");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
```

Với `HALF_EVEN`, giá trị đúng giữa hai lựa chọn được làm tròn về kết quả có chữ số cuối cùng chẵn. Trong ví dụ này, 2.34 có chữ số cuối là 4 nên được chọn.

Không có một chế độ làm tròn đúng cho mọi ứng dụng. Hãy áp dụng quy tắc theo hợp đồng nghiệp vụ, tiêu chuẩn kế toán hoặc yêu cầu của hệ thống.

### 7.6. equals và compareTo của BigDecimal

Hai giá trị `BigDecimal` có cùng giá trị số nhưng khác scale có thể không bằng nhau theo `equals`:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b));   // 0
```

- `equals` xét cả giá trị và scale.
- `compareTo` so sánh giá trị số; trả 0 khi hai số có cùng giá trị về mặt số học.

Nếu kiểm tra hai khoản tiền có cùng giá trị, `compareTo(...) == 0` thường phù hợp hơn `equals` khi scale có thể khác nhau. Tuy nhiên, nếu scale là một phần của hợp đồng dữ liệu, bạn cần giữ sự phân biệt đó có chủ đích.

## 8. Lựa chọn kiểu dữ liệu theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Tính toán khoa học, đồ họa, mô phỏng, tọa độ | `double` | Chấp nhận sai số dấu phẩy động và xác định dung sai. |
| Dữ liệu số thực cần tiết kiệm bộ nhớ hoặc tương thích API yêu cầu float | `float` | Độ chính xác thấp hơn `double`. |
| Tiền tệ, hóa đơn, tỷ lệ thập phân theo quy tắc rõ ràng | `BigDecimal` | Dùng chuỗi khi tạo từ dữ liệu thập phân; chỉ định scale và chế độ làm tròn. |
| Số lượng nguyên, số đơn vị nhỏ nhất của tiền tệ | `long` | Kiểm tra nguy cơ tràn; có thể dùng `Math.*Exact`. |
| Số nguyên vượt phạm vi `long` | `BigInteger` | Phù hợp với số nguyên lớn tùy nhu cầu hiệu năng. |

### 8.1. Dùng long để lưu đơn vị nhỏ nhất

Với một số hệ thống tiền tệ hoặc miền có đơn vị nhỏ nhất cố định, có thể lưu số nguyên:

```java
long amountInCents = 1_999; // 19.99 nếu quy ước 100 cents = 1 unit
long feeInCents = 250;

long totalInCents = Math.addExact(amountInCents, feeInCents);
System.out.println(totalInCents);
```

Cách này tránh sai số nhị phân khi các phép toán phù hợp với đơn vị nhỏ nhất. Nhưng cần xác định số chữ số lẻ của từng loại tiền tệ, cách xử lý tỷ lệ/chia và kiểm tra tràn số. Không phải mọi nghiệp vụ đều chỉ có hai chữ số thập phân.

### 8.2. Ví dụ tính tiền với BigDecimal

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyCalculation {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.90");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal taxRate = new BigDecimal("0.10");

        BigDecimal subtotal = unitPrice.multiply(quantity);
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Tax:      " + tax);
        System.out.println("Total:    " + total);
    }
}
```

Đầu ra:

```text
Subtotal: 59.70
Tax:      5.97
Total:    65.67
```

Trong ứng dụng thực tế, phải xác định **thời điểm làm tròn**: làm tròn thuế trên từng dòng hay trên tổng hóa đơn có thể tạo ra kết quả khác nhau. BigDecimal giúp thực hiện đúng quy tắc được chọn, nhưng không tự quyết định quy tắc nghiệp vụ.

## 9. Java 17 và tính nhất quán của phép toán dấu phẩy động

Java 17 sử dụng ngữ nghĩa dấu phẩy động *always-strict* theo JEP 306. Các biểu thức floating-point tuân theo quy tắc nghiêm ngặt của Java/IEEE 754, thay vì có thể sử dụng tập giá trị trung gian mở rộng như một số chế độ cũ.

Điều này có ý nghĩa:

- Kết quả các phép toán cơ bản được quy định rõ hơn và nhất quán giữa các nền tảng Java phù hợp.
- Từ Java 17, từ khóa `strictfp` không còn cần thiết để buộc ngữ nghĩa nghiêm ngặt cho các phép toán dấu phẩy động.
- **Always-strict không loại bỏ sai số biểu diễn.** `0.1` vẫn không có biểu diễn nhị phân hữu hạn; phép cộng và nhân vẫn phải làm tròn theo định dạng.
- Tính nhất quán của phép toán cơ bản không đồng nghĩa mọi thuật toán hoặc hàm toán học đều cho cùng độ chính xác tuyệt đối trong mọi tình huống.

Nói cách khác, Java 17 làm cho quy tắc thực thi số thực rõ ràng và nhất quán hơn, nhưng lập trình viên vẫn phải thiết kế cách biểu diễn, tính toán và so sánh phù hợp.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `0.1 + 0.2 != 0.3` | Số thập phân không có biểu diễn nhị phân hữu hạn | Dùng tolerance cho so sánh số thực hoặc `BigDecimal` cho số thập phân chính xác. |
| Cộng lặp lại nhiều lần bị lệch | Sai số làm tròn tích lũy | Xem xét thuật toán cộng bù, cách nhóm phép cộng hoặc biểu diễn phù hợp. |
| Thêm 1 vào số rất lớn mà kết quả không đổi | Khoảng cách giữa các giá trị `double` biểu diễn được lớn hơn 1 | Dùng `long`/`BigInteger` nếu cần số nguyên chính xác. |
| Phép nhân tạo `Infinity` | Overflow | Kiểm tra miền giá trị và `Double.isFinite`; thiết kế giới hạn đầu vào. |
| Giá trị nhỏ trở thành 0 | Underflow và làm tròn | Đánh giá thang đo, đơn vị và kiểu dữ liệu cần thiết. |
| Chia `double` cho 0 cho `Infinity` hoặc `NaN` | Quy tắc IEEE 754 | Kiểm tra mẫu số và kết quả hữu hạn theo yêu cầu nghiệp vụ. |
| `new BigDecimal(0.1)` có nhiều chữ số lạ | Constructor nhận giá trị double đã gần đúng | Tạo từ chuỗi hoặc dùng `BigDecimal.valueOf` trong trường hợp thích hợp. |
| `BigDecimal.divide` ném `ArithmeticException` | Thương có biểu diễn thập phân không kết thúc nhưng không chỉ định làm tròn | Dùng scale và `RoundingMode` hoặc `MathContext`. |
| `BigDecimal.equals` trả false cho `2.0` và `2.00` | Scale khác nhau | Dùng `compareTo` khi cần so sánh giá trị số. |

## 11. Câu hỏi tự kiểm tra

**1. Vì sao `0.1 + 0.2` không nhất thiết bằng `0.3` trong Java?**  
Vì `float` và `double` dùng biểu diễn nhị phân hữu hạn; 0.1 và 0.2 không có biểu diễn nhị phân hữu hạn nên phải làm tròn.

**2. Kiểu `double` có bao nhiêu bit độ chính xác significand?**  
53 bit, bao gồm bit ẩn của số chuẩn hóa. Độ chính xác thập phân thường khoảng 15–17 chữ số có nghĩa.

**3. Vì sao thứ tự cộng số thực có thể làm thay đổi kết quả?**  
Mỗi phép toán có thể làm tròn. Nếu cộng số rất nhỏ với số rất lớn trước, phần nhỏ có thể bị mất.

**4. Nhân `Double.MAX_VALUE` với 2 có thể cho kết quả gì?**  
`Infinity` do overflow, thay vì tự động ném `ArithmeticException`.

**5. Chia `1.0 / 0.0` và `1 / 0` khác nhau ra sao?**  
Phép chia số thực cho vô cực; phép chia số nguyên cho 0 ném `ArithmeticException`.

**6. Có nên so sánh hai kết quả double bằng `==`?**  
Không nên mặc định như vậy với kết quả tính toán. Hãy chọn dung sai phù hợp với miền bài toán hoặc dùng biểu diễn chính xác nếu cần.

**7. Khi tính tiền nên ưu tiên kiểu nào?**  
Thường là `BigDecimal` với quy tắc scale/làm tròn được chỉ định, hoặc số nguyên theo đơn vị nhỏ nhất nếu mô hình nghiệp vụ phù hợp.

**8. Vì sao `new BigDecimal(0.1)` không tạo đúng chuỗi thập phân `0.1`?**  
Vì `0.1` đã được chuyển thành giá trị double gần đúng trước khi constructor nhận nó. Dùng `new BigDecimal("0.1")` để tạo đúng giá trị thập phân mong muốn.

**9. `BigDecimal.divide` cần điều gì khi kết quả là số thập phân vô hạn?**  
Chỉ định scale và `RoundingMode` hoặc `MathContext` để quy định độ chính xác/làm tròn.

**10. Java 17 có còn cần `strictfp` để bảo đảm phép toán cơ bản theo ngữ nghĩa nghiêm ngặt không?**  
Không. Java 17 áp dụng ngữ nghĩa always-strict cho floating-point; điều này không làm mất sai số biểu diễn vốn có.

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): định dạng, phạm vi và giá trị của `float`/`double`.
- [Java Language Specification, Java SE 17 — `15.4 FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): quy tắc đánh giá biểu thức dấu phẩy động.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): ngữ nghĩa dấu phẩy động luôn nghiêm ngặt từ Java 17.
- [Java SE 17 API — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác, phép toán, scale, `MathContext` và làm tròn.
- [Java SE 17 API — `java.math.RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): các quy tắc làm tròn.
- [Java SE 17 API — `java.lang.Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): hằng số, kiểm tra hữu hạn, NaN, vô cực và chuyển đổi bit.
