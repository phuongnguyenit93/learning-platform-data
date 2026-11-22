# Số thực trong Java 17: `NaN`, vô cực và số không có dấu

Java có hai kiểu số thực nguyên thủy thường dùng: **`float`** (độ chính xác đơn, 32 bit) và **`double`** (độ chính xác kép, 64 bit). Chúng biểu diễn số theo chuẩn dấu phẩy động IEEE 754, vì vậy miền giá trị không chỉ có số hữu hạn. Một giá trị `float` hoặc `double` còn có thể là **NaN** (Not a Number), **dương vô cực**, **âm vô cực**, **dương không** (`+0.0`) hoặc **âm không** (`-0.0`).

Các giá trị đặc biệt này có thể xuất hiện trong phép tính, phép chia, hàm toán học, dữ liệu đọc từ chuỗi hoặc kết quả trung gian. Nếu chương trình chỉ kiểm tra `value < 0` hay `value == 0`, nó có thể bỏ sót `NaN`, vô cực hoặc dấu của số không. Bài học này giải thích cách các giá trị đó hoạt động trong Java 17, cách nhận biết chúng và cách xử lý phù hợp trong chương trình.

## 1. Các giá trị đặc biệt của `float` và `double`

Java cung cấp các hằng số trong hai lớp wrapper `Float` và `Double`:

| Giá trị | `double` | `float` | Ý nghĩa |
| --- | --- | --- | --- |
| NaN | `Double.NaN` | `Float.NaN` | Kết quả không phải một số thực có nghĩa theo phép toán IEEE 754. |
| Dương vô cực | `Double.POSITIVE_INFINITY` | `Float.POSITIVE_INFINITY` | Vô cực mang dấu dương. |
| Âm vô cực | `Double.NEGATIVE_INFINITY` | `Float.NEGATIVE_INFINITY` | Vô cực mang dấu âm. |
| Dương không | `+0.0` hoặc `0.0` | `+0.0f` hoặc `0.0f` | Giá trị zero có bit dấu dương. |
| Âm không | `-0.0` | `-0.0f` | Giá trị zero có bit dấu âm. |

Các hằng số `NaN` và vô cực là giá trị kiểu số thực, không phải `null`, không phải chuỗi `"NaN"` và cũng không phải ngoại lệ. Ví dụ:

```java
double notANumber = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;
double positiveZero = 0.0;
double negativeZero = -0.0;
```

`float` có các giá trị đặc biệt tương tự nhưng độ chính xác và miền số hữu hạn nhỏ hơn `double`. Trong các phép tính có số thực, Java có thể thực hiện chuyển đổi số học giữa `float` và `double`; hãy chú ý kiểu của toán hạng và kiểu kết quả.

## 2. `NaN` là gì?

`NaN` là viết tắt của **Not a Number**. Nó biểu diễn kết quả không phải một số thực hợp lệ theo phép toán dấu phẩy động, chẳng hạn:

- `0.0 / 0.0`;
- `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`;
- `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY`;
- `0.0 * Double.POSITIVE_INFINITY`;
- `Math.sqrt(-1.0)`.

Ví dụ:

```java
public class NaNDemo {
    public static void main(String[] args) {
        double a = 0.0 / 0.0;
        double b = Math.sqrt(-1.0);

        System.out.println(a); // NaN
        System.out.println(b); // NaN
        System.out.println(Double.isNaN(a)); // true
        System.out.println(Double.isNaN(b)); // true
    }
}
```

Phép toán tạo ra `NaN` **không nhất thiết ném ngoại lệ**. Chương trình vẫn tiếp tục và có thể mang giá trị này qua nhiều phép tính sau đó. Vì vậy, nếu một kết quả `NaN` không được xử lý, nó có thể lan truyền đến điểm hiển thị, lưu trữ hoặc quyết định nghiệp vụ.

### 2.1. Các phép so sánh với `NaN`

Đây là đặc tính rất quan trọng: **`NaN` không bằng chính nó và mọi phép so sánh thứ tự với `NaN` đều trả về `false`**. Cụ thể, `==`, `<`, `>`, `<=` và `>=` trả `false`; toán tử `!=` trả `true`.

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(value != value); // true
System.out.println(value < 0.0);    // false
System.out.println(value > 0.0);    // false
System.out.println(value <= 0.0);   // false
System.out.println(value >= 0.0);   // false
```

Do đó, không thể dùng `value == Double.NaN` để kiểm tra NaN:

```java
double result = 0.0 / 0.0;

if (result == Double.NaN) {
    System.out.println("NaN"); // Không chạy
}
```

Hãy dùng phương thức chuyên dụng:

```java
if (Double.isNaN(result)) {
    System.out.println("Kết quả là NaN");
}
```

Với `float`, dùng `Float.isNaN(value)`.

### 2.2. `NaN` có thể lan truyền qua phép tính

Trong phần lớn phép toán số học dấu phẩy động, nếu một toán hạng là `NaN`, kết quả tiếp tục là `NaN`:

```java
double invalid = Double.NaN;

System.out.println(invalid + 10);       // NaN
System.out.println(invalid * 2);        // NaN
System.out.println(Math.abs(invalid));  // NaN
System.out.println(Math.max(5.0, invalid)); // NaN
```

Một khi giá trị không hợp lệ đã xuất hiện, các phép tính tiếp theo thường không thể tự khôi phục số hữu hạn. Cần xác định điểm phát sinh và chính sách xử lý thay vì chỉ kiểm tra ở cuối chương trình.

### 2.3. `NaN` không phải là dấu hiệu duy nhất của dữ liệu lỗi

Một giá trị `NaN` có thể có nghĩa phép tính không xác định, dữ liệu thiếu được biểu diễn theo quy ước, hoặc đầu vào số đã bị lỗi. Ngược lại, một giá trị hữu hạn vẫn có thể sai về mặt nghiệp vụ, ví dụ nhiệt độ `-500.0` hoặc tỷ lệ `1.7` trong miền chỉ cho phép từ 0 đến 1.

Vì vậy, nên phân biệt:

- **Tính hợp lệ số học:** có phải NaN/vô cực hay không?
- **Tính hợp lệ miền nghiệp vụ:** giá trị có nằm trong miền mà ứng dụng cho phép không?
- **Tính hiện diện của dữ liệu:** có dữ liệu hay đang thiếu? Không nên tự động dùng `NaN` thay cho mọi trường hợp thiếu.

## 3. Vô cực: dương vô cực và âm vô cực

Số thực trong Java có thể nhận hai giá trị vô cực:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

System.out.println(positive); // Infinity
System.out.println(negative); // -Infinity
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isInfinite(negative)); // true
```

Vô cực có thể xuất hiện khi phép toán vượt quá miền biểu diễn hữu hạn (overflow), hoặc khi chia một số thực khác zero cho zero có dấu:

```java
double a = 1.0 / 0.0;
double b = -1.0 / 0.0;
double c = 1.0 / -0.0;

System.out.println(a); // Infinity
System.out.println(b); // -Infinity
System.out.println(c); // -Infinity
```

Với phép toán dấu phẩy động, chia cho zero **không giống** chia số nguyên cho zero. Phép chia số nguyên sẽ được giải thích ở mục 5.

### 3.1. Kiểm tra vô cực

Dùng `Double.isInfinite()` hoặc `Float.isInfinite()`:

```java
double value = 1.0 / 0.0;

if (Double.isInfinite(value)) {
    System.out.println("Giá trị vô cực");
}
```

Nếu chỉ cần biết giá trị có phải số hữu hạn hay không, có thể dùng `Double.isFinite()` hoặc `Float.isFinite()`:

```java
double[] values = {
        12.5,
        Double.NaN,
        Double.POSITIVE_INFINITY,
        Double.NEGATIVE_INFINITY
};

for (double value : values) {
    System.out.println(value + " -> " + Double.isFinite(value));
}
```

`isFinite` trả về `true` cho số hữu hạn, bao gồm cả `+0.0` và `-0.0`; trả về `false` cho NaN và hai giá trị vô cực. Đây thường là cách kiểm tra đầu vào gọn nếu thuật toán chỉ chấp nhận số hữu hạn.

### 3.2. Một số phép toán với vô cực

| Biểu thức | Kết quả |
| --- | --- |
| `Double.POSITIVE_INFINITY + 100.0` | `Infinity` |
| `Double.NEGATIVE_INFINITY - 100.0` | `-Infinity` |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY * 2.0` | `Infinity` |
| `Double.POSITIVE_INFINITY * -2.0` | `-Infinity` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY / 2.0` | `Infinity` |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` |
| `2.0 / Double.POSITIVE_INFINITY` | `+0.0` |
| `-2.0 / Double.POSITIVE_INFINITY` | `-0.0` |

Không nên suy luận mọi phép toán có vô cực đều cho vô cực. Một số tổ hợp là **không xác định** theo số học dấu phẩy động và trả về NaN.

### 3.3. So sánh vô cực với số hữu hạn

Vô cực có thứ tự so sánh theo trực giác:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

System.out.println(positive > Double.MAX_VALUE); // true
System.out.println(negative < -Double.MAX_VALUE); // true
System.out.println(positive > 1.0e300); // true
```

Nhưng cần nhớ NaN không tham gia thứ tự này theo các toán tử `<`, `>` thông thường. Ví dụ `Double.NaN < Double.POSITIVE_INFINITY` vẫn là `false`.

## 4. Số không có dấu: `+0.0` và `-0.0`

Một điểm đặc biệt của IEEE 754 là có **hai biểu diễn zero khác nhau về bit dấu**:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(positiveZero < negativeZero);  // false
System.out.println(positiveZero > negativeZero);  // false
```

Theo toán tử `==`, hai giá trị này bằng nhau. Tuy nhiên, chúng **không giống nhau ở mọi phép toán**. Dấu của zero có thể ảnh hưởng đến hướng vô cực khi dùng làm mẫu số, và được giữ trong một số phép toán toán học.

### 4.1. Phép chia làm lộ dấu của zero

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
System.out.println(-1.0 / positiveZero); // -Infinity
System.out.println(-1.0 / negativeZero); // Infinity
```

Vì vậy, dấu của zero không chỉ là cách hiển thị. Nó có thể mang thông tin về **hướng tiến tới zero** trong tính toán số học và thuật toán số.

### 4.2. Số không có dấu có thể xuất hiện như thế nào?

Ngoài literal `-0.0`, âm zero có thể xuất hiện từ kết quả của phép toán:

```java
double a = -1.0 / Double.POSITIVE_INFINITY;
double b = -0.0 * 2.0;
double c = -1.0e-300 * 1.0e-300; // Underflow về -0.0

System.out.println(a); // -0.0
System.out.println(b); // -0.0
System.out.println(c); // -0.0
```

Khi một kết quả có độ lớn quá nhỏ để biểu diễn khác zero, nó có thể **underflow** thành zero có dấu. Dấu được giữ theo quy tắc của phép toán.

### 4.3. Kiểm tra dấu của zero

Không dùng `value == 0.0` để phân biệt hai zero vì cả hai đều bằng nhau theo toán tử này. Một cách kiểm tra rõ ràng là so sánh bit:

```java
static boolean isNegativeZero(double value) {
    return Double.doubleToRawLongBits(value)
            == Double.doubleToRawLongBits(-0.0d);
}

static boolean isPositiveZero(double value) {
    return Double.doubleToRawLongBits(value)
            == Double.doubleToRawLongBits(+0.0d);
}

public static void main(String[] args) {
    System.out.println(isNegativeZero(-0.0)); // true
    System.out.println(isNegativeZero(+0.0)); // false
    System.out.println(isPositiveZero(+0.0)); // true
}
```

`Double.doubleToRawLongBits()` trả về mẫu bit thô, giữ cả thông tin payload của NaN. `Double.doubleToLongBits()` thì chuẩn hóa mọi NaN thành một biểu diễn NaN chuẩn, nhưng vẫn phân biệt `+0.0` với `-0.0`. Với mục tiêu phân biệt dấu zero, cả hai phương thức đều có thể dùng; tên `raw` nhấn mạnh việc không chuẩn hóa NaN.

Một cách khác để quan sát dấu là:

```java
System.out.println(Math.copySign(1.0, +0.0)); // 1.0
System.out.println(Math.copySign(1.0, -0.0)); // -1.0
```

`Math.copySign(magnitude, sign)` lấy độ lớn từ đối số đầu và dấu từ đối số thứ hai.

## 5. Phân biệt phép chia số thực và phép chia số nguyên

Đây là một khác biệt thực tế dễ gây lỗi:

```java
double floatingResult = 10.0 / 0.0;
System.out.println(floatingResult); // Infinity

int integerResult = 10 / 0;
// ArithmeticException: / by zero
```

Phép chia giữa các toán hạng số thực tuân theo quy tắc IEEE 754: kết quả có thể là vô cực hoặc NaN. Phép chia số nguyên trong Java không có giá trị vô cực; chia cho zero ném `ArithmeticException`.

Nếu hai toán hạng là số nguyên, việc gán kết quả vào `double` **không biến phép chia thành phép chia số thực**:

```java
double wrong = 1 / 2;   // 0.0: phép chia int thực hiện trước
double correct = 1.0 / 2; // 0.5: có toán hạng double

System.out.println(wrong);
System.out.println(correct);
```

Tương tự:

```java
double result = (double) 1 / 0; // Infinity
```

Phép ép kiểu một toán hạng sang `double` trước khi chia làm phép toán trở thành phép chia số thực. Nếu viết `double result = (double) (1 / 0);`, phép chia nguyên xảy ra trước và vẫn ném ngoại lệ.

## 6. So sánh primitive với `equals()` và `compare()`

Một nguồn nhầm lẫn khác là phép so sánh toán tử `==` của `double`/`float` có hành vi khác với `equals()` của lớp wrapper.

### 6.1. Primitive `==` và wrapper `equals`

```java
double nan1 = Double.NaN;
double nan2 = Double.NaN;

System.out.println(nan1 == nan2); // false
System.out.println(Double.valueOf(nan1).equals(Double.valueOf(nan2))); // true

double plusZero = +0.0;
double minusZero = -0.0;

System.out.println(plusZero == minusZero); // true
System.out.println(Double.valueOf(plusZero).equals(Double.valueOf(minusZero))); // false
```

Khác biệt:

| Trường hợp | Primitive `==` | `Double.equals()` |
| --- | --- | --- |
| `NaN` so với `NaN` | `false` | `true` |
| `+0.0` so với `-0.0` | `true` | `false` |
| Hai số hữu hạn cùng giá trị | `true` | `true` |

`Float.equals()` có quy tắc tương tự. Vì vậy, khi dùng `Double` làm khóa trong `HashMap` hoặc phần tử của `HashSet`, hành vi bằng nhau là hành vi của wrapper, không phải toán tử `==` trên primitive.

### 6.2. `Double.compare()` tạo thứ tự tổng quát

Khi cần sắp xếp hoặc so sánh theo một thứ tự có quy tắc cả với giá trị đặc biệt, dùng `Double.compare(a, b)`:

```java
System.out.println(Double.compare(-0.0, +0.0)); // số âm
System.out.println(Double.compare(+0.0, -0.0)); // số dương
System.out.println(Double.compare(Double.NaN, Double.POSITIVE_INFINITY)); // số dương
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
```

Các điểm cần nhớ:

- `Double.compare()` xem `-0.0` nhỏ hơn `+0.0`.
- NaN được xem là bằng NaN trong thứ tự so sánh của wrapper.
- NaN được xếp sau dương vô cực.
- Với các giá trị hữu hạn thông thường, thứ tự theo số học.

Đây là lý do các phương thức sắp xếp và comparator có thể xử lý những giá trị đặc biệt theo thứ tự xác định. Nếu nghiệp vụ không chấp nhận NaN hoặc vô cực, hãy lọc hoặc từ chối chúng **trước khi sắp xếp**, thay vì dựa vào thứ tự mặc định để diễn đạt quy tắc nghiệp vụ.

### 6.3. Hệ quả với `hashCode()`

Hợp đồng của `equals()` yêu cầu hai đối tượng bằng nhau phải có cùng `hashCode()`. `Double` và `Float` được thiết kế để đáp ứng điều này:

- Các NaN được chuẩn hóa khi tính hash, nhất quán với việc wrapper `equals()` xem NaN bằng NaN.
- `+0.0` và `-0.0` có mã băm khác nhau, nhất quán với wrapper `equals()` xem chúng khác nhau.

Không nên dùng `hashCode()` để kiểm tra hai số có cùng giá trị. Va chạm hash vẫn có thể xảy ra và mã băm không phải định danh duy nhất.

## 7. Kiểm tra và xử lý giá trị số thực an toàn

Các phương thức thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `Double.isNaN(value)` | Kiểm tra NaN. |
| `Double.isInfinite(value)` | Kiểm tra dương hoặc âm vô cực. |
| `Double.isFinite(value)` | Kiểm tra giá trị hữu hạn, gồm cả hai zero có dấu. |
| `Float.isNaN(value)` | Kiểm tra NaN của `float`. |
| `Float.isInfinite(value)` | Kiểm tra vô cực của `float`. |
| `Float.isFinite(value)` | Kiểm tra giá trị hữu hạn của `float`. |
| `Math.copySign(magnitude, sign)` | Tạo giá trị có độ lớn từ đối số đầu và dấu từ đối số thứ hai. |
| `Math.signum(value)` | Trả về dấu theo quy tắc của hàm, giữ NaN và dấu của zero. |

### 7.1. Chỉ chấp nhận số hữu hạn

Nếu một phương thức tính toán không thể xử lý NaN hoặc vô cực, hãy kiểm tra trước:

```java
static double calculateRatio(double numerator, double denominator) {
    if (!Double.isFinite(numerator)
            || !Double.isFinite(denominator)) {
        throw new IllegalArgumentException("Đầu vào phải là số hữu hạn");
    }

    if (denominator == 0.0) {
        throw new IllegalArgumentException("Mẫu số không được bằng zero");
    }

    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Kết quả không hữu hạn");
    }
    return result;
}
```

Lưu ý `denominator == 0.0` nhận diện **cả `+0.0` lẫn `-0.0`**. Đây là lựa chọn phù hợp nếu cả hai đều không được chấp nhận làm mẫu số theo nghiệp vụ.

Việc kiểm tra kết quả sau phép chia cũng quan trọng: hai toán hạng hữu hạn vẫn có thể tạo ra kết quả vô cực do overflow, hoặc giá trị rất nhỏ có thể underflow về zero.

### 7.2. Phân biệt dữ liệu thiếu với kết quả NaN

Không nên mặc định dùng `Double.NaN` làm giá trị thay thế cho mọi trường hợp không có dữ liệu. Có thể biểu diễn riêng:

```java
import java.util.OptionalDouble;

static OptionalDouble average(double[] values) {
    if (values.length == 0) {
        return OptionalDouble.empty();
    }

    double total = 0.0;
    for (double value : values) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Có phần tử không hữu hạn");
        }
        total += value;
    }

    return OptionalDouble.of(total / values.length);
}
```

`OptionalDouble.empty()` diễn tả **không có kết quả**, còn một `OptionalDouble` chứa NaN (nếu thuật toán chủ động tạo ra và cho phép) sẽ diễn tả một giá trị số đặc biệt. Phân biệt hai ý nghĩa này giúp API dễ sử dụng hơn.

Trong một số hệ thống, có thể dùng kiểu kết quả riêng với trạng thái `MISSING`, `INVALID`, `FINITE` hoặc các trạng thái miền nghiệp vụ khác thay vì dùng một số đặc biệt làm sentinel.

### 7.3. Không kiểm tra dữ liệu chỉ bằng `<`, `>` hoặc `==`

Ví dụ kiểm tra giá trị trong khoảng:

```java
static boolean isValidPercentage(double value) {
    return Double.isFinite(value)
            && value >= 0.0
            && value <= 100.0;
}
```

Nếu thiếu `Double.isFinite`, NaN vẫn làm cả hai phép so sánh khoảng trả về `false`, nên ví dụ này tình cờ cũng từ chối NaN; tuy nhiên kiểm tra hữu hạn tường minh làm rõ hợp đồng và tránh vô tình chấp nhận giá trị đặc biệt ở những biểu thức phức tạp hơn. Vô cực cũng không nằm trong khoảng 0 đến 100.

Nếu chỉ kiểm tra `value != 0.0`, NaN trả về `true` vì NaN khác mọi giá trị theo `==`. Đó là lý do nên kiểm tra hữu hạn hoặc NaN riêng, thay vì suy luận từ một phép so sánh đơn lẻ.

## 8. Đọc và ghi NaN, vô cực từ chuỗi

Các phương thức parse số thực của Java có thể nhận các biểu diễn đặc biệt:

```java
double a = Double.parseDouble("NaN");
double b = Double.parseDouble("Infinity");
double c = Double.parseDouble("-Infinity");

System.out.println(Double.isNaN(a)); // true
System.out.println(Double.isInfinite(b)); // true
System.out.println(c); // -Infinity
```

Các dạng tương ứng cũng có ở `Float.parseFloat()`. Chuỗi không phải biểu diễn số được chấp nhận sẽ gây `NumberFormatException`:

```java
try {
    double value = Double.parseDouble("not-a-number");
} catch (NumberFormatException ex) {
    System.out.println("Chuỗi không phải số hợp lệ");
}
```

Không nhầm hai tình huống:

- `"NaN"` là chuỗi mà parser nhận ra và chuyển thành giá trị `Double.NaN`.
- `"not-a-number"` là chuỗi không hợp lệ và parser ném `NumberFormatException`.

Sau khi parse, nếu nghiệp vụ chỉ cho phép số hữu hạn, hãy kiểm tra `Double.isFinite(value)` trước khi dùng.

### 8.1. Khi xuất dữ liệu ra JSON hoặc hệ thống khác

Chuẩn JSON phổ biến **không định nghĩa** các token số `NaN`, `Infinity` hoặc `-Infinity` như giá trị number hợp lệ. Một số thư viện có thể từ chối, biến đổi hoặc cho phép xuất các giá trị đó theo chế độ mở rộng riêng. Vì vậy:

- Không giả định mọi JSON parser/client đều chấp nhận `NaN` hoặc vô cực.
- Chọn quy ước rõ ràng như `null`, chuỗi `"NaN"` hoặc một object có trường trạng thái nếu hợp đồng dữ liệu cho phép.
- Không đổi giá trị đặc biệt thành `null` một cách âm thầm nếu điều đó làm mất thông tin nghiệp vụ.
- Kiểm tra cấu hình serializer và kiểm thử định dạng thực tế được gửi đi.

Nếu dữ liệu là số đo, nên cân nhắc truyền cả **trạng thái đo** và **giá trị** để phân biệt chưa có kết quả, thiết bị lỗi, vượt thang đo hoặc kết quả không xác định.

## 9. `double` và độ chính xác: giá trị đặc biệt không giải quyết sai số làm tròn

`NaN`, vô cực và signed zero là những giá trị hợp lệ của hệ thống dấu phẩy động; chúng không phải lời giải cho mọi vấn đề số học. `float` và `double` có độ chính xác hữu hạn, vì thế nhiều số thập phân không được biểu diễn chính xác bằng nhị phân:

```java
double result = 0.1 + 0.2;
System.out.println(result); // thường hiển thị 0.30000000000000004
```

Kết quả trên là số **hữu hạn**, không phải NaN. Khi so sánh số thực trong bài toán có sai số đo hoặc tính toán, có thể cần ngưỡng sai số:

```java
static boolean approximatelyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return Double.compare(a, b) == 0;
    }
    return Math.abs(a - b) <= epsilon;
}
```

Hàm minh họa này cần chọn `epsilon` theo đơn vị và quy mô của bài toán. Trong hệ thống tài chính cần số thập phân chính xác theo quy tắc nghiệp vụ, hãy xem xét `BigDecimal`; `BigDecimal` không biểu diễn NaN hay vô cực như `double`.

### 9.1. Overflow và underflow

Một phép toán trên các giá trị hữu hạn có thể tạo ra kết quả ngoài miền biểu diễn:

```java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = -Double.MIN_VALUE / 2.0;

System.out.println(overflow); // Infinity
System.out.println(underflow); // -0.0
```

`Double.MAX_VALUE` là số hữu hạn dương lớn nhất. `Double.MIN_VALUE` là **số dương khác zero nhỏ nhất** có thể biểu diễn, không phải số âm nhỏ nhất. Với các số rất nhỏ, kết quả có thể là subnormal (số dưới chuẩn) trước khi underflow thành zero.

Không nhầm `Double.MIN_VALUE` với `-Double.MAX_VALUE`; hai hằng số nói về hai đầu miền giá trị khác nhau.

## 10. Hành vi số thực trong Java 17

Từ Java 17, JEP 306 khôi phục ngữ nghĩa dấu phẩy động luôn nghiêm ngặt (always-strict floating-point semantics). Các biểu thức số thực được đánh giá theo ngữ nghĩa nhất quán của IEEE 754, không còn chế độ tính toán mở rộng khác nhau tùy nền tảng như lịch sử trước đó.

Vì vậy, trong mã Java 17 mới, không cần thêm `strictfp` để yêu cầu hành vi số thực nghiêm ngặt. Từ khóa này vẫn tồn tại vì lý do tương thích ngôn ngữ, nhưng không làm thay đổi kết quả số học trong Java 17. Khi đọc tài liệu hoặc mã cũ nhắc đến việc dùng `strictfp` để đảm bảo tính nhất quán giữa nền tảng, hãy hiểu bối cảnh lịch sử đó; không cần áp dụng như một bước cấu hình mới.

## 11. Chương trình minh họa tổng hợp

Tạo tệp `SpecialFloatingPointDemo.java`:

```java
public class SpecialFloatingPointDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println("NaN: " + nan);
        System.out.println("isNaN: " + Double.isNaN(nan));
        System.out.println("isFinite(NaN): " + Double.isFinite(nan));

        System.out.println("Positive infinity: " + positiveInfinity);
        System.out.println("Negative infinity: " + negativeInfinity);
        System.out.println("isInfinite: "
                + Double.isInfinite(positiveInfinity));

        System.out.println("Positive zero == negative zero: "
                + (positiveZero == negativeZero));
        System.out.println("1 / positive zero: " + (1.0 / positiveZero));
        System.out.println("1 / negative zero: " + (1.0 / negativeZero));

        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("Double.equals NaN: "
                + Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));
        System.out.println("Double.compare(+0, -0): "
                + Double.compare(+0.0, -0.0));

        double[] values = {
                12.5,
                nan,
                positiveInfinity,
                negativeInfinity,
                positiveZero,
                negativeZero
        };

        for (double value : values) {
            System.out.println(value + " -> finite: "
                    + Double.isFinite(value));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac SpecialFloatingPointDemo.java
java SpecialFloatingPointDemo
```

Các dòng kết quả quan trọng:

```text
NaN: NaN
isNaN: true
isFinite(NaN): false
Positive infinity: Infinity
Negative infinity: -Infinity
isInfinite: true
Positive zero == negative zero: true
1 / positive zero: Infinity
1 / negative zero: -Infinity
NaN == NaN: false
Double.equals NaN: true
Double.compare(+0, -0): 1
```

Các giá trị `true`/`false`, dấu vô cực và thứ tự của `Double.compare` cho thấy vì sao phải chọn đúng phép kiểm tra theo mục tiêu: so sánh toán học, kiểm tra giá trị đặc biệt, hoặc so sánh đối tượng wrapper.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `value == Double.NaN` luôn `false` | Theo quy tắc IEEE 754, NaN không bằng bất kỳ giá trị nào, kể cả chính nó. | Dùng `Double.isNaN(value)`. |
| Giá trị vô cực xuất hiện dù không có exception | Phép toán `float`/`double` có thể trả vô cực theo IEEE 754. | Dùng `isInfinite` hoặc `isFinite`; kiểm tra overflow và miền đầu vào. |
| Chia số thực cho zero không ném lỗi | Phép chia số thực trả vô cực hoặc NaN tùy tử số và dấu zero. | Nếu nghiệp vụ cấm mẫu số zero, kiểm tra cả `+0.0` và `-0.0` trước phép chia. |
| Chia số nguyên cho zero ném `ArithmeticException` | Phép chia nguyên không có giá trị vô cực. | Kiểm tra mẫu số hoặc chuyển phép toán sang số thực nếu đúng mục đích. |
| `+0.0 == -0.0` là `true` nhưng phép chia cho kết quả khác nhau | Toán tử `==` không phân biệt dấu zero; IEEE 754 vẫn giữ bit dấu. | Dùng phép kiểm tra bit hoặc `Math.copySign` khi dấu zero có ý nghĩa. |
| `Double.equals` khác với `==` | Wrapper có hợp đồng bằng nhau dành cho object và hash collection. | Phân biệt primitive comparison với wrapper equality; dùng `Double.compare` khi cần thứ tự. |
| Giá trị trung gian thành NaN rồi lan truyền | Một phép toán không xác định đã tạo NaN. | Kiểm tra dữ liệu và các bước toán học ngay tại nguồn phát sinh. |
| Parser nhận `"NaN"` nhưng từ chối chuỗi khác | `"NaN"` là token số thực đặc biệt hợp lệ của parser; chuỗi tùy ý không phải số. | Bắt `NumberFormatException`, sau đó kiểm tra `isFinite` theo hợp đồng. |
| Serializer JSON từ chối Infinity hoặc NaN | JSON tiêu chuẩn không có token số này. | Chọn biểu diễn trao đổi rõ ràng và cấu hình serializer phù hợp. |
| `Double.MIN_VALUE` không phải số âm lớn nhất | Hằng số này là số dương khác zero nhỏ nhất. | Dùng `-Double.MAX_VALUE` nếu cần số hữu hạn âm nhỏ nhất. |

## 13. Bài tập tự luyện

### Bài 1 — Dự đoán kết quả

```java
double a = 0.0 / 0.0;
double b = 5.0 / 0.0;
double c = -5.0 / 0.0;

System.out.println(a == a);
System.out.println(Double.isNaN(a));
System.out.println(Double.isInfinite(b));
System.out.println(b > Double.MAX_VALUE);
System.out.println(c < -Double.MAX_VALUE);
```

Hãy tự dự đoán năm kết quả trước khi chạy chương trình.

**Đáp án:** `false`, `true`, `true`, `true`, `true`.

### Bài 2 — Phân biệt hai zero

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);
System.out.println(1.0 / positiveZero);
System.out.println(1.0 / negativeZero);
System.out.println(Double.compare(positiveZero, negativeZero));
```

**Đáp án:** `true`, `Infinity`, `-Infinity`, một số dương. Toán tử `==` xem hai zero bằng nhau, nhưng phép chia và `Double.compare` phân biệt dấu.

### Bài 3 — Kiểm tra đầu vào

Viết phương thức nhận một `double` và chỉ trả về `true` nếu giá trị là số hữu hạn trong khoảng từ 0 đến 1, bao gồm cả hai đầu mút. Thử với `0.0`, `-0.0`, `0.5`, `1.0`, `Double.NaN`, `Double.POSITIVE_INFINITY`.

Gợi ý:

```java
static boolean validRate(double rate) {
    return Double.isFinite(rate)
            && rate >= 0.0
            && rate <= 1.0;
}
```

Hãy quyết định xem nghiệp vụ có chấp nhận `-0.0` như zero hay cần từ chối riêng dấu âm.

### Bài 4 — Chia số nguyên hay số thực?

Giải thích kết quả và cách sửa:

```java
double ratio1 = 1 / 4;
double ratio2 = 1.0 / 4;
```

**Đáp án:** `ratio1` là `0.0` vì phép chia nguyên diễn ra trước khi gán; `ratio2` là `0.25` vì có toán hạng `double`.

### Bài 5 — Wrapper và primitive

So sánh:

```java
Double x = Double.NaN;
Double y = Double.NaN;

System.out.println(x == y);
System.out.println(x.equals(y));
System.out.println(Double.compare(x, y));
```

Giải thích vì sao kết quả của so sánh tham chiếu, `equals()` và `compare()` không nhất thiết giống nhau. Gợi ý: `x == y` khi cả hai là wrapper sẽ so sánh **tham chiếu** (không nên dựa vào một kết quả cố định khi hai wrapper được tạo riêng); `equals()` so sánh giá trị wrapper, còn `compare()` tạo thứ tự cho giá trị số. Với hai NaN, `equals()` là `true` và `compare()` trả `0`.

## 14. Ghi nhớ khi sử dụng số thực

- `NaN` là giá trị đặc biệt, không bằng chính nó theo toán tử `==`; kiểm tra bằng `Double.isNaN()` hoặc `Float.isNaN()`.
- `+Infinity` và `-Infinity` là giá trị dấu phẩy động hợp lệ; kiểm tra bằng `isInfinite()` hoặc từ chối mọi giá trị không hữu hạn bằng `isFinite()`.
- `+0.0` và `-0.0` bằng nhau theo primitive `==`, nhưng có bit dấu khác nhau và có thể tạo kết quả khác nhau khi chia.
- Chia số thực cho zero có thể trả vô cực hoặc NaN; chia số nguyên cho zero ném `ArithmeticException`.
- `Double.equals()` và `Double.compare()` có quy tắc riêng với NaN và signed zero; không đồng nhất chúng với `==` của primitive.
- Text parser có thể đọc `"NaN"` và `"Infinity"`, nhưng dữ liệu trao đổi như JSON cần quy ước riêng cho các giá trị này.
- Kiểm tra đặc biệt số học không thay thế kiểm tra miền nghiệp vụ; một số hữu hạn vẫn có thể không hợp lệ đối với ứng dụng.

### Tài liệu tham khảo

- [Java SE 17 API — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) — hằng số, phương thức kiểm tra, chuyển đổi bit, so sánh và parse của `double`.
- [Java SE 17 API — `Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) — hằng số và phương thức tương ứng cho `float`.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) — các phép toán và hàm toán học.
- [JLS Java SE 17 — §4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) — miền giá trị và định dạng dấu phẩy động.
- [JLS Java SE 17 — §15.17.2 Division Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2) — quy tắc phép chia số nguyên và số thực.
- [JEP 306: Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306) — thay đổi ngữ nghĩa số thực có hiệu lực từ Java 17.
