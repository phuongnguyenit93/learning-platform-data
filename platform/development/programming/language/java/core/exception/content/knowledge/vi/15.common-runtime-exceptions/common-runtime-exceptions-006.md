# Phân biệt chia số thực cho 0 với chia số nguyên cho 0 trong Java

## 1. Mục tiêu học tập

Trong Java, cùng là ký hiệu chia `/` và cùng nhìn thấy mẫu số bằng `0`, nhưng kết quả có thể **hoàn toàn khác nhau tùy kiểu toán hạng**:

- **Phép chia số nguyên** với số chia bằng 0 (như `int` hoặc `long`) sẽ **ném `ArithmeticException` tại runtime**.
- **Phép chia số thực dấu phẩy động** với `float` hoặc `double` không tự ném `ArithmeticException` chỉ vì số chia bằng 0. Theo ngữ nghĩa IEEE 754 được Java quy định, kết quả có thể là **`Infinity`, `-Infinity` hoặc `NaN`**.
- **`%` (chia lấy dư)** cũng có sự khác biệt: số nguyên lấy dư với 0 ném `ArithmeticException`; phép lấy dư dấu phẩy động với 0 sinh `NaN`.
- Một phép toán có cả số nguyên và số thực có thể được **numeric promotion** sang `float`/`double`, nên không thể đoán chỉ từ kiểu của tử số.
- Một đối tượng kiểu `BigDecimal` không dùng quy tắc chia của `float`/`double` nguyên thủy: chia cho `BigDecimal.ZERO` ném `ArithmeticException`.

Bài học thuộc chủ đề **Java core — exception / Ngoại lệ runtime**, nên ngoài việc dự đoán kết quả, bạn cần biết *khi nào có ngoại lệ để bắt*, *khi nào không có ngoại lệ nhưng vẫn nhận kết quả không hữu hạn*, và *cách kiểm tra đúng trước khi dùng kết quả*.

Sau bài này, bạn sẽ phân biệt được kiểu toán hạng, dấu của zero, quy tắc lan truyền `NaN`, phép lấy dư, kiểm tra bằng `Double.isFinite`/`isNaN`, và các lỗi thường gặp khi viết `try/catch` cho phép chia.

Ví dụ dùng Java 17+; mỗi chương trình hoàn chỉnh có tên tệp, lệnh `javac`/`java` và `stdout` xác định. Những đoạn mã chỉ minh họa được ghi rõ.

## 2. Quy tắc nền tảng trong một bảng

| Biểu thức | Loại phép toán | Kết quả khi chạy |
| --- | --- | --- |
| `7 / 0` | Chia số nguyên `int` | Ném `ArithmeticException` |
| `7L / 0L` | Chia số nguyên `long` | Ném `ArithmeticException` |
| `7 % 0` | Chia lấy dư `int` | Ném `ArithmeticException` |
| `7.0 / 0.0` | Chia `double` | `Infinity` |
| `-7.0 / 0.0` | Chia `double` | `-Infinity` |
| `7.0 / -0.0` | Chia `double` | `-Infinity` |
| `0.0 / 0.0` | Chia `double` | `NaN` |
| `0.0f / 0.0f` | Chia `float` | `NaN` |
| `7.0 % 0.0` | Chia lấy dư `double` | `NaN` |
| `7 / 0.0` | Chia `double` sau promotion | `Infinity` |
| `7.0 / 0` | Chia `double` sau promotion | `Infinity` |
| `7 / 2` | Chia số nguyên | `3`, phần thập phân bị bỏ |
| `7 / 2.0` | Chia `double` | `3.5` |

**Điểm chính:** Java quyết định ngữ nghĩa phép chia theo **kiểu toán hạng sau binary numeric promotion**. Không phải “mẫu số viết 0 nên chắc chắn có `ArithmeticException`”.

Cụm “chia số thực” trong bài chỉ các toán hạng kiểu nguyên thủy **`float` và `double`** (floating-point), không ngụ ý tất cả lớp biểu diễn số thập phân như `BigDecimal` đều có cùng hành vi.

## 3. Chia nguyên cho 0: `ArithmeticException`

`int` và `long` có phép chia số nguyên. Theo JLS, nếu **toán hạng phải sau chuyển kiểu có giá trị nguyên bằng 0**, phép `/` ném `ArithmeticException`. Cùng nguyên tắc áp dụng cho `%` nguyên.

Ví dụ:

```java
int numerator = 10;
int denominator = 0;
int value = numerator / denominator; // Ném ArithmeticException.
```

Đây là mảnh mã minh họa. `value` không nhận giá trị vì biểu thức ở bên phải không hoàn thành bình thường.

### Chương trình chạy được: các trường hợp chia nguyên

Tạo tệp **`IntegerZeroDivisionDemo.java`**:

```java
public class IntegerZeroDivisionDemo {
    static void divideInt(int numerator, int denominator) {
        try {
            System.out.println("int=" + (numerator / denominator));
        } catch (ArithmeticException failure) {
            System.out.println("int error=" + failure.getMessage());
        }
    }

    static void divideLong(long numerator, long denominator) {
        try {
            System.out.println("long=" + (numerator / denominator));
        } catch (ArithmeticException failure) {
            System.out.println("long error=" + failure.getMessage());
        }
    }

    static void remainderInt(int numerator, int denominator) {
        try {
            System.out.println("remainder=" + (numerator % denominator));
        } catch (ArithmeticException failure) {
            System.out.println("remainder error=" + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        divideInt(10, 2);
        divideInt(10, 0);
        divideLong(10L, 0L);
        remainderInt(10, 0);
    }
}
```

Biên dịch và chạy:

```bash
javac IntegerZeroDivisionDemo.java
java IntegerZeroDivisionDemo
```

`stdout`:

```text
int=5
int error=/ by zero
long error=/ by zero
remainder error=/ by zero
```

**Giải thích:**

1. `10 / 2` cho kết quả `5`.
2. Khi gọi `divideInt(10, 0)`, phép chia số nguyên không có kết quả hợp lệ; `catch (ArithmeticException)` chạy.
3. `long` cũng chịu quy tắc chia nguyên cho 0, không có giá trị “infinity” dành cho số nguyên.
4. `10 % 0` cũng ném `ArithmeticException`. Nó **không** cho kết quả `0` hoặc `NaN` như toán tử `%` dấu phẩy động.
5. `failure.getMessage()` với phép chia nguyên cho 0 được JDK dùng trong ví dụ là `/ by zero`. Không xây logic nghiệp vụ dựa vào chuỗi message; hãy dựa vào kiểu exception và dữ liệu đầu vào.

### `ArithmeticException` là checked hay unchecked?

`ArithmeticException` kế thừa `RuntimeException`, nên là **unchecked exception**. Không bắt buộc khai báo `throws ArithmeticException` trong phương thức đang thực hiện phép chia nguyên:

```java
static int divide(int a, int b) {
    return a / b;
}
```

Đây là phương thức Java hợp lệ. Nếu `b == 0`, nó vẫn ném tại runtime. “Unchecked” **không** có nghĩa “không thể xảy ra”; nó chỉ nói compiler không yêu cầu `try/catch` hoặc `throws`.

### Tràn số nguyên khác với chia cho 0

Một trường hợp đặc biệt:

```java
int value = Integer.MIN_VALUE / -1;
System.out.println(value);
```

Đây là mảnh mã hợp lệ; kết quả là `-2147483648` do quy tắc tràn số của phép chia nguyên có trường hợp đặc biệt. Nó **không** ném `ArithmeticException` chỉ vì kết quả toán học vượt phạm vi `int`. Đừng đánh đồng tràn số nguyên với phép chia cho 0.

## 4. Chia `float`/`double` cho 0: kết quả đặc biệt, không ném tự động

Java dùng ngữ nghĩa dấu phẩy động tương thích IEEE 754 cho các kiểu nguyên thủy `float`/`double`. Với phép chia dấu phẩy động:

- Tử số **khác 0 và hữu hạn** chia cho zero tạo ra vô cực có dấu thích hợp.
- Zero chia cho zero tạo ra `NaN` (*Not a Number*).
- Các phép toán liên quan `NaN` hoặc vô cực còn tuân theo các quy tắc đặc biệt khác.
- Java **không ném ngoại lệ tại phép `/` dấu phẩy động** chỉ vì phát sinh vô cực hoặc `NaN`.

### Chương trình chạy được: các kết quả dấu phẩy động

Tạo tệp **`FloatingZeroDivisionDemo.java`**:

```java
public class FloatingZeroDivisionDemo {
    public static void main(String[] args) {
        double positive = 7.0 / 0.0;
        double negative = -7.0 / 0.0;
        double negativeZero = 7.0 / -0.0;
        double undefined = 0.0 / 0.0;
        float singlePrecision = 7.0f / 0.0f;

        System.out.println("positive=" + positive);
        System.out.println("negative=" + negative);
        System.out.println("negative zero=" + negativeZero);
        System.out.println("zero over zero=" + undefined);
        System.out.println("float=" + singlePrecision);

        System.out.println("isInfinite="
                + Double.isInfinite(positive));
        System.out.println("isNaN="
                + Double.isNaN(undefined));
    }
}
```

```bash
javac FloatingZeroDivisionDemo.java
java FloatingZeroDivisionDemo
```

`stdout`:

```text
positive=Infinity
negative=-Infinity
negative zero=-Infinity
zero over zero=NaN
float=Infinity
isInfinite=true
isNaN=true
```

Tất cả phép chia trong chương trình đều hoàn thành mà **không tự ném `ArithmeticException`**. Java tạo ra những giá trị đặc biệt của kiểu `double` hoặc `float`.

### Vì sao lại có `Infinity` và `NaN`?

Theo ngữ nghĩa floating-point:

- `7.0 / +0.0` → `+Infinity`.
- `-7.0 / +0.0` → `-Infinity`.
- `7.0 / -0.0` → `-Infinity`.
- `0.0 / 0.0` → `NaN`.
- `-0.0 / -0.0` cũng là `NaN`.

`Infinity` không phải kiểu dữ liệu mới: nó là **một giá trị đặc biệt của `double` hoặc `float`**. Tương tự, `NaN` không phải exception mà là một giá trị dấu phẩy động đặc biệt.

Có thể dùng `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY`, `Double.NaN` và các hằng tương ứng của `Float` để biểu diễn các giá trị này rõ ràng.

**Đừng tự dựa vào việc kiểm tra `result == Double.NaN`** để phát hiện NaN; phép so sánh bằng với NaN luôn trả `false`. Dùng `Double.isNaN(result)` hoặc `Float.isNaN(result)`.

## 5. Số 0 âm (`-0.0`) làm kết quả đổi dấu

Kiểu nguyên Java không có một giá trị `-0` tách biệt với `0`. Với số nguyên:

```java
int zero = -0;
System.out.println(zero == 0);
```

Đây là mảnh mã hợp lệ và in `true`.

Nhưng `float` và `double` có **+0.0** và **-0.0** phân biệt ở mức biểu diễn. Mặc dù `0.0 == -0.0` trả `true` trong phép so sánh số thông thường, dấu của zero ảnh hưởng đến phép chia.

### Chương trình chạy được: dấu của zero

Tạo tệp **`SignedZeroDemo.java`**:

```java
public class SignedZeroDemo {
    public static void main(String[] args) {
        double plusZero = 0.0;
        double minusZero = -0.0;

        System.out.println("zero equal="
                + (plusZero == minusZero));
        System.out.println("1/+0="
                + (1.0 / plusZero));
        System.out.println("1/-0="
                + (1.0 / minusZero));
        System.out.println("-1/-0="
                + (-1.0 / minusZero));
        System.out.println("Double.compare="
                + Double.compare(minusZero, plusZero));
    }
}
```

```bash
javac SignedZeroDemo.java
java SignedZeroDemo
```

`stdout`:

```text
zero equal=true
1/+0=Infinity
1/-0=-Infinity
-1/-0=Infinity
Double.compare=-1
```

- `==` coi hai zero bằng nhau trong phép so sánh dấu phẩy động.
- `1.0 / +0.0` và `1.0 / -0.0` có kết quả khác dấu.
- `Double.compare(-0.0, +0.0)` có quy tắc so sánh nhất quán cho các giá trị đặc biệt và trả số âm (cụ thể `-1` trong chương trình).
- Dấu zero có thể hình thành qua phép tính, underflow hoặc từ một literal. Không giả định mọi biểu thức có giá trị so sánh bằng 0 đều biểu diễn `+0.0`.

Nếu thuật toán không có nhu cầu phân biệt dấu zero, có thể kiểm tra mẫu số bằng `denominator == 0.0` để bắt cả `+0.0` lẫn `-0.0`. Nếu dấu zero có ý nghĩa vật lý hay số học, cần thiết kế chính sách khác.

## 6. Toán tử `/` quyết định theo **numeric promotion**, không chỉ theo literal

Một lỗi phổ biến là nhìn thấy tử số `int` và kết luận “đây là phép chia nguyên”. Java trước tiên thực hiện **binary numeric promotion** cho các toán hạng số học.

Tóm tắt hữu ích:

1. Nếu có toán hạng kiểu `double`, cả hai được dùng như `double`.
2. Nếu không có `double` nhưng có `float`, cả hai được dùng như `float`.
3. Nếu không có `double`/`float` nhưng có `long`, cả hai được dùng như `long`.
4. Trường hợp còn lại (các số nguyên nhỏ hơn như `byte`, `short`, `char`) dùng `int`.

Vì vậy:

```java
int a = 7;
int b = 0;

double first = a / b;       // VẪN là phép chia int -> ArithmeticException.
double second = a / 0.0;   // Phép chia double -> Infinity.
double third = (double) a / b; // Phép chia double -> Infinity.
```

Đây là **mảnh mã minh họa**. Phép gán kết quả vào biến `double` **không thể thay đổi cách biểu thức `a / b` đã được đánh giá**. Để buộc phép chia thực, ít nhất một toán hạng phải được chuyển sang `float`/`double` *trước phép chia*.

### Chương trình chạy được: kiểm chứng kiểu toán hạng

Tạo tệp **`NumericPromotionDemo.java`**:

```java
public class NumericPromotionDemo {
    public static void main(String[] args) {
        int seven = 7;
        int two = 2;
        int zero = 0;

        double assignedAfterIntegerDivide = seven / two;
        double floatingDivide = seven / 2.0;
        double castBeforeDivide = (double) seven / two;

        System.out.println("int into double="
                + assignedAfterIntegerDivide);
        System.out.println("with double="
                + floatingDivide);
        System.out.println("cast before="
                + castBeforeDivide);

        try {
            double invalid = seven / zero;
            System.out.println(invalid);
        } catch (ArithmeticException failure) {
            System.out.println("int denominator zero: exception");
        }

        System.out.println("double denominator zero="
                + (seven / 0.0));
        System.out.println("float denominator zero="
                + (seven / 0.0f));
    }
}
```

```bash
javac NumericPromotionDemo.java
java NumericPromotionDemo
```

`stdout`:

```text
int into double=3.0
with double=3.5
cast before=3.5
int denominator zero: exception
double denominator zero=Infinity
float denominator zero=Infinity
```

Phân tích hai dòng dễ nhầm:

- `double assignedAfterIntegerDivide = seven / two;`: vì cả hai toán hạng là `int` nên kết quả `3` trước, sau đó mới chuyển thành `3.0` để gán cho `double`.
- `double floatingDivide = seven / 2.0;`: `2.0` là `double`, nên `seven` được promotion; kết quả là `3.5`.

Tương tự, `(double) (seven / two)` cho `3.0` vì ép kiểu **sau phép chia nguyên**; `((double) seven) / two` mới là chia thực. Vị trí ép kiểu rất quan trọng.

### `byte`/`short`/`char` và `long`

- `byte`, `short`, `char` được promotion lên `int` khi dùng `/` hoặc `%` với nhau (trừ khi có kiểu rộng hơn), vì vậy chia cho zero vẫn ném.
- `long` chia cho `long` zero vẫn ném `ArithmeticException`.
- `long` chia cho `0.0` trở thành phép chia `double` và tạo infinity tùy dấu.
- Kiểu của literal quan trọng: `0` là `int`, `0L` là `long`, `0.0` mặc định là `double`, `0.0f` là `float`.

Không lẫn `0.0f` với `0`: giá trị toán học “zero” giống nhau nhưng **loại phép toán và khả năng phát sinh ngoại lệ** khác nhau.

## 7. Toán tử lấy dư `%`: cùng quy tắc phân biệt kiểu

`%` không chỉ áp dụng cho số nguyên. Java hỗ trợ cả phép lấy dư dấu phẩy động; nhưng hành vi với số chia bằng 0 vẫn chia làm hai nhóm.

- `int % 0`, `long % 0L` → ném `ArithmeticException`.
- `double % 0.0`, `float % 0.0f` → `NaN`.
- Với giá trị dấu phẩy động, toán tử `%` Java dùng quy tắc tính remainder riêng; nó **không đồng nhất** với hàm `Math.IEEEremainder`.

### Chương trình chạy được: `%` với zero

Tạo tệp **`RemainderZeroDemo.java`**:

```java
public class RemainderZeroDemo {
    public static void main(String[] args) {
        try {
            int result = 5 % 0;
            System.out.println(result);
        } catch (ArithmeticException failure) {
            System.out.println("integer remainder: exception");
        }

        double floatingRemainder = 5.0 % 0.0;
        float floatRemainder = 5.0f % 0.0f;

        System.out.println("double remainder="
                + floatingRemainder);
        System.out.println("float remainder="
                + floatRemainder);
        System.out.println("isNaN="
                + Double.isNaN(floatingRemainder));

        System.out.println("finite percent infinity="
                + (5.0 % Double.POSITIVE_INFINITY));
    }
}
```

```bash
javac RemainderZeroDemo.java
java RemainderZeroDemo
```

`stdout`:

```text
integer remainder: exception
double remainder=NaN
float remainder=NaN
isNaN=true
finite percent infinity=5.0
```

Một quy tắc khác: toán tử `%` dấu phẩy động với **số chia vô cực** và số bị chia hữu hạn trả về số bị chia đó; nhưng khi số chia bằng **zero**, nó trả `NaN`. Đừng áp máy móc kiến thức `%` nguyên sang kiểu `double`.

### `Math.IEEEremainder` khác `%`

Java có `Math.IEEEremainder(double f1, double f2)`. Nó dùng quy tắc chọn thương nguyên gần nhất theo IEEE (ties to even), trong khi `%` theo quy tắc remainder gắn với chia và truncation. Chúng có thể trả kết quả khác nhau với cùng hai số thông thường.

Ví dụ `5.0 % 3.0` là `2.0`, nhưng `Math.IEEEremainder(5.0, 3.0)` là `-1.0`. Cả hai không biến phép chia nguyên cho zero thành hợp lệ; đây là các phép toán dấu phẩy động khác nhau.

## 8. `NaN` không phải ngoại lệ, và so sánh với `NaN` dễ sai

`NaN` là một giá trị đặc biệt của `float`/`double` dùng cho những phép tính dấu phẩy động không có kết quả số thông thường, chẳng hạn `0.0 / 0.0`.

Các phép so sánh:

- `Double.NaN == Double.NaN` → `false`.
- `Double.NaN != Double.NaN` → `true`.
- `Double.NaN < 1.0`, `Double.NaN > 1.0` và `Double.NaN == 1.0` → đều `false`.
- `Double.isNaN(value)` là API đúng để phát hiện `NaN`.

### Chương trình chạy được: so sánh và API kiểm tra

Tạo tệp **`NaNInfinityChecksDemo.java`**:

```java
public class NaNInfinityChecksDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double undefined = 0.0 / 0.0;
        double ordinary = 5.0 / 2.0;

        System.out.println("NaN == NaN: "
                + (undefined == undefined));
        System.out.println("NaN != NaN: "
                + (undefined != undefined));
        System.out.println("NaN > 1: " + (undefined > 1.0));

        System.out.println("isNaN=" + Double.isNaN(undefined));
        System.out.println("isInfinite="
                + Double.isInfinite(positiveInfinity));

        System.out.println("infinity finite="
                + Double.isFinite(positiveInfinity));
        System.out.println("NaN finite="
                + Double.isFinite(undefined));
        System.out.println("ordinary finite="
                + Double.isFinite(ordinary));
    }
}
```

```bash
javac NaNInfinityChecksDemo.java
java NaNInfinityChecksDemo
```

`stdout`:

```text
NaN == NaN: false
NaN != NaN: true
NaN > 1: false
isNaN=true
isInfinite=true
infinity finite=false
NaN finite=false
ordinary finite=true
```

`Double.isFinite(x)` chỉ trả `true` khi `x` **không** phải vô cực và **không** phải `NaN`. Đây là phép kiểm tra gọn khi ứng dụng chỉ chấp nhận kết quả số thực hữu hạn.

Các API tương ứng `Float.isNaN`, `Float.isInfinite` và `Float.isFinite` phù hợp với kiểu `float`.

### Tại sao không dùng `try/catch (ArithmeticException)` để phát hiện NaN?

Vì **không có `ArithmeticException` phát sinh từ phép `/` dấu phẩy động với zero**, nên handler đó không chạy. Phát hiện giá trị bất thường bằng API kiểm tra `NaN`/infinity và **quy định chính sách riêng** của ứng dụng, không dựa trên một ngoại lệ Java không tự ném.

## 9. Khi nào vô cực xuất hiện dù **không** chia cho 0?

Không nên kết luận “thấy `Infinity` có nghĩa chắc chắn mẫu số bằng 0”. Số thực có **giới hạn biểu diễn**; các phép tính có thể tràn phạm vi hữu hạn.

Ví dụ:

```java
double overflow = Double.MAX_VALUE * 2.0;
double veryLargeQuotient =
        Double.MAX_VALUE / Double.MIN_VALUE;

System.out.println(overflow);
System.out.println(veryLargeQuotient);
```

Đây là mảnh Java hợp lệ, in:

```text
Infinity
Infinity
```

`Double.MIN_VALUE` là **giá trị `double` dương nhỏ nhất khác 0** (subnormal), không phải số âm hữu hạn có độ lớn tuyệt đối lớn nhất. Vì thế mẫu số ở phép chia thứ hai **không bằng 0**, nhưng kết quả toán học quá lớn để biểu diễn bằng `double` hữu hạn.

Tương tự:

- `Math.sqrt(-1.0)` tạo `NaN` dù không hề dùng phép chia cho zero.
- Một số phép toán với vô cực có thể tạo `NaN`, ví dụ `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`.
- Tích `0.0 * Double.POSITIVE_INFINITY` là `NaN`.

Khi một kết quả số thực quan trọng cho nghiệp vụ, hãy kiểm tra **cả tính hợp lệ của đầu vào** và **kết quả cuối**. Chỉ kiểm tra mẫu số có bằng 0 hay không là chưa đủ để bảo đảm kết quả hữu hạn.

## 10. Kiểm tra mẫu số bằng `== 0.0` có đủ không?

Nếu mục tiêu là **chặn chính xác +0.0 và -0.0**, kiểm tra:

```java
if (denominator == 0.0) {
    throw new IllegalArgumentException("denominator must not be zero");
}
```

Đây là mảnh minh họa với biến `denominator` kiểu `double`. Vì `+0.0 == -0.0` là `true`, cả hai dấu đều được chặn.

Nhưng có các giới hạn:

- `denominator = Double.NaN`: biểu thức `denominator == 0.0` là `false`, nhưng phép chia thường tạo NaN.
- `denominator = Double.POSITIVE_INFINITY`: không bằng zero; có thể cho kết quả zero hữu hạn trong một số phép chia.
- `numerator` đã là `NaN` hoặc infinity: kết quả có thể không hữu hạn.
- `denominator` cực nhỏ nhưng **khác 0**: phép chia có thể overflow thành infinity.
- Kiểm tra `Math.abs(denominator) < epsilon` là **một chính sách ngưỡng số học**, không tương đương chính xác với “chia cho zero”. Ngưỡng phải dựa trên kích thước dữ liệu và yêu cầu ứng dụng.

Vì vậy, nếu bài toán yêu cầu **không bao giờ trả NaN hoặc infinity**, hãy kiểm tra `Double.isFinite(...)` của cả đầu vào và kết quả.

## 11. Tự chọn ném ngoại lệ cho phép chia dấu phẩy động khi nghiệp vụ cần

Java không tự ném với phép chia thực cho zero, nhưng **ứng dụng có thể cố ý ném** một ngoại lệ để biểu diễn hợp đồng của mình.

Ví dụ phương thức sau từ chối mọi đầu vào không hữu hạn, mọi mẫu số zero và mọi kết quả không hữu hạn.

Tạo tệp **`FiniteDivisionDemo.java`**:

```java
public class FiniteDivisionDemo {
    static double divideFinite(double numerator, double denominator) {
        if (!Double.isFinite(numerator)
                || !Double.isFinite(denominator)) {
            throw new IllegalArgumentException(
                    "inputs must be finite");
        }
        if (denominator == 0.0) {
            throw new ArithmeticException(
                    "floating denominator is zero");
        }

        double result = numerator / denominator;
        if (!Double.isFinite(result)) {
            throw new ArithmeticException(
                    "floating result is not finite");
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("valid="
                + divideFinite(5.0, 2.0));

        try {
            divideFinite(1.0, 0.0);
        } catch (ArithmeticException failure) {
            System.out.println("zero="
                    + failure.getMessage());
        }

        try {
            divideFinite(Double.MAX_VALUE, Double.MIN_VALUE);
        } catch (ArithmeticException failure) {
            System.out.println("overflow="
                    + failure.getMessage());
        }

        try {
            divideFinite(Double.NaN, 2.0);
        } catch (IllegalArgumentException failure) {
            System.out.println("invalid="
                    + failure.getMessage());
        }
    }
}
```

```bash
javac FiniteDivisionDemo.java
java FiniteDivisionDemo
```

`stdout`:

```text
valid=2.5
zero=floating denominator is zero
overflow=floating result is not finite
invalid=inputs must be finite
```

**Điểm phân biệt bắt buộc:** `ArithmeticException` ở đây được ném **bởi mã kiểm tra do lập trình viên tự viết**. Nó không phải ngoại lệ mà toán tử `double / double` tự động tạo. Một thư viện khác có thể chọn `IllegalArgumentException`, đối tượng kết quả chuyên dụng, hoặc trả giá trị IEEE; đó là hợp đồng thiết kế API.

### Nên chọn kiểm tra kiểu nào?

| Yêu cầu | Kiểm tra phù hợp |
| --- | --- |
| Không cho mẫu số bằng zero, chấp nhận các kết quả IEEE khác | `denominator == 0.0` |
| Không cho đầu vào `NaN` hoặc infinity | `Double.isFinite(numerator)` và `Double.isFinite(denominator)` |
| Yêu cầu kết quả cuối phải hữu hạn | `Double.isFinite(result)` |
| Muốn phân biệt zero âm/dương | Kiểm tra dấu bằng `Math.copySign` hoặc raw bits khi thật sự cần |
| Muốn tính gần zero theo thang giá trị nghiệp vụ | Ngưỡng tương đối/tuyệt đối được thiết kế và kiểm thử |
| Tính tiền với độ chính xác thập phân và chính sách làm tròn | Cân nhắc `BigDecimal` với `MathContext`/`RoundingMode` thích hợp |

Việc chọn exception, thông điệp, kiểu giá trị trả về và ngưỡng không thể chỉ dựa vào toán tử. Nó là phần hợp đồng của API và yêu cầu chính xác số học.

## 12. `BigDecimal` và `BigInteger`: không áp quy tắc infinity của `double`

Người mới học dễ nghĩ “số thập phân” là một nhóm duy nhất. Thực tế **`BigDecimal` là class số học thập phân chính xác theo thang chia**, không phải kiểu dấu phẩy động nhị phân `double`.

Ví dụ:

```java
java.math.BigDecimal.ONE.divide(java.math.BigDecimal.ZERO);
```

Đây là mảnh Java; nó ném `ArithmeticException`. Nó **không** trả `BigDecimal` biểu diễn infinity, vì API `BigDecimal` không có cùng tập giá trị infinity/NaN như `double`.

Tương tự `BigInteger.ONE.divide(BigInteger.ZERO)` ném `ArithmeticException`.

### Chương trình chạy được: so sánh với `BigDecimal`

Tạo tệp **`BigDecimalDivisionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigDecimalDivisionDemo {
    public static void main(String[] args) {
        try {
            System.out.println(
                    BigDecimal.ONE.divide(BigDecimal.ZERO));
        } catch (ArithmeticException failure) {
            System.out.println("BigDecimal divide zero: exception");
        }

        try {
            System.out.println(
                    BigInteger.ONE.divide(BigInteger.ZERO));
        } catch (ArithmeticException failure) {
            System.out.println("BigInteger divide zero: exception");
        }

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");

        System.out.println("rounded="
                + one.divide(three, 2, RoundingMode.HALF_UP));
        System.out.println("double="
                + (1.0 / 0.0));
    }
}
```

```bash
javac BigDecimalDivisionDemo.java
java BigDecimalDivisionDemo
```

`stdout`:

```text
BigDecimal divide zero: exception
BigInteger divide zero: exception
rounded=0.33
double=Infinity
```

**Lưu ý khác của `BigDecimal`:** `BigDecimal.ONE.divide(new BigDecimal("3"))` **cũng có thể ném `ArithmeticException`** nếu dùng overload yêu cầu biểu diễn thập phân chính xác mà không có kết quả hữu hạn. Khi cần chia `1/3`, phải chọn chính sách làm tròn như `RoundingMode` hoặc `MathContext`. Trường hợp này là **không thể biểu diễn chính xác bằng số chữ số thập phân hữu hạn**, khác hoàn toàn chia cho 0.

Không dùng `BigDecimal` với hy vọng nó “tự tạo NaN” khi chia cho 0. Hãy quyết định chính sách nghiệp vụ và bắt/kiểm tra lỗi đúng API.

## 13. `try/catch` đúng cách cho hai họ phép chia

Chia nguyên:

```java
static int integerDivide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
```

Đây là phương thức hợp lệ. Bạn có thể chặn bằng guard trước hoặc để `ArithmeticException` từ phép chia phát sinh rồi xử lý ở ranh giới phù hợp. Dùng guard có thể tạo thông điệp miền cụ thể; không nhất thiết phải bắt mọi `ArithmeticException` vì nó cũng có thể xuất hiện từ thao tác khác.

Chia thực:

```java
static double floatingDivide(double numerator, double denominator) {
    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("result is not finite");
    }
    return result;
}
```

Đây là một **chính sách ứng dụng** chọn ném khi kết quả không hữu hạn. Khác với `integerDivide`, bản thân biểu thức `numerator / denominator` không tạo `ArithmeticException` do mẫu số zero.

Nếu chỉ cần chuẩn IEEE để tính toán khoa học, có thể **cố ý cho phép** infinity/NaN và xử lý chúng ở tầng toán học. Trong hệ thống tính tiền, báo cáo số liệu hoặc validation đầu vào, thường cần từ chối giá trị không hữu hạn và có chiến lược làm tròn/chính xác riêng.

### Vì sao bắt `ArithmeticException` xung quanh `1.0 / 0.0` thường vô ích?

```java
try {
    double result = 1.0 / 0.0;
    System.out.println(result);
} catch (ArithmeticException failure) {
    System.out.println("caught");
}
```

Đây là mảnh hợp lệ. Nó in `Infinity`, **không in `caught`**. Catch được phép có mặt về cú pháp vì `ArithmeticException` là unchecked, nhưng điều đó không khiến `/` dấu phẩy động bắt đầu ném ngoại lệ.

Ngược lại, với `int numerator = 1; int denominator = 0;`, câu lệnh `numerator / denominator` sẽ đi vào nhánh catch nếu có.

## 14. `Double.NaN` trong điều kiện và vòng lặp

Một thuật toán dùng kiểm tra như:

```java
if (value > threshold) {
    // ...
}
```

có thể bỏ qua giá trị NaN không phải vì giá trị “an toàn”, mà bởi phép so sánh `>` với NaN trả `false`. Tương tự:

```java
if (value <= threshold) {
    // ...
}
```

cũng có thể trả `false` với NaN. Hai điều kiện không bao phủ tất cả các giá trị floating-point, dù theo suy nghĩ về số thực thông thường bạn có thể kỳ vọng một trong hai đúng.

Nếu đầu vào đến từ dữ liệu bên ngoài, cảm biến hoặc phép chia trước đó, hãy **xử lý NaN một cách tường minh** trước khi áp dụng ngưỡng nếu yêu cầu nghiệp vụ cần phân loại đủ mọi trạng thái.

Ví dụ mảnh mã:

```java
if (Double.isNaN(value)) {
    throw new IllegalArgumentException("measurement is NaN");
}
if (Double.isInfinite(value)) {
    throw new IllegalArgumentException("measurement is infinite");
}
```

Điều này đặc biệt quan trọng ở những hệ thống validation: nếu chỉ kiểm tra `value < min || value > max`, NaN có thể lọt qua bởi cả hai phép so sánh đều false. Dùng `Double.isFinite(value)` thường là một cổng kiểm tra phù hợp trước khi so sánh ngưỡng.

## 15. Sai lầm do ép kiểu và thứ tự tính toán

Một số tình huống cần phân biệt:

```java
int numerator = 1;
int denominator = 0;

// A: integer division trước, sau đó mới cast -> ném ArithmeticException.
double a = (double) (numerator / denominator);

// B: chuyển tử số sang double trước phép chia -> Infinity.
double b = (double) numerator / denominator;

// C: chuyển mẫu số sang double trước phép chia -> Infinity.
double c = numerator / (double) denominator;
```

Đây là **mảnh minh họa**: câu lệnh A ném và ngăn những câu lệnh tiếp theo chạy nếu không có handler. Dạng B/C chỉ có kết quả Infinity khi thực sự được chạy.

Nếu viết:

```java
int result = (int) (1.0 / 0.0);
System.out.println(result);
```

Đây là mảnh hợp lệ và in `2147483647` (`Integer.MAX_VALUE`) theo quy tắc **narrowing primitive conversion** từ `+Infinity` sang `int`. Nó **không** tự tạo `ArithmeticException`. Chuyển `NaN` sang `int` cho 0 theo quy tắc chuyển kiểu.

Điểm học tập: *một phép chia đã được thực hiện dưới kiểu `double` thì việc cast kết quả sang `int` về sau không biến nó thành phép chia nguyên*. Tuy vậy, narrowing có thể làm mất độ chính xác hoặc bão hòa về giới hạn kiểu nguyên, rất nguy hiểm nếu ứng dụng tưởng giá trị còn hợp lệ.

### Chương trình chạy được: cast sau khi chia thực

Tạo tệp **`FloatingCastDemo.java`**:

```java
public class FloatingCastDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double notANumber = 0.0 / 0.0;

        System.out.println("double positive=" + positiveInfinity);
        System.out.println("to int positive=" + (int) positiveInfinity);
        System.out.println("to int negative=" + (int) negativeInfinity);
        System.out.println("to int NaN=" + (int) notANumber);
    }
}
```

```bash
javac FloatingCastDemo.java
java FloatingCastDemo
```

`stdout`:

```text
double positive=Infinity
to int positive=2147483647
to int negative=-2147483648
to int NaN=0
```

Những kết quả cast này **không chứng minh phép chia ban đầu hợp lệ về nghiệp vụ**. Nếu cần chặn infinity/NaN, nên kiểm tra trước khi convert sang số nguyên để tránh che dấu tình trạng không hữu hạn.

## 16. Lỗi thường gặp và cách sửa

**“Bất cứ phép chia cho 0 nào trong Java cũng ném `ArithmeticException`.”** Sai. Chỉ có quy tắc ném của phép chia/lấy dư **số nguyên** và của một số API riêng (ví dụ BigDecimal); toán tử `/` floating-point dùng infinity/NaN.

**“`1.0 / 0.0` luôn ném vì mẫu số 0.”** Sai. Nó cho `Infinity`.

**“`0.0 / 0.0` là 0.”** Sai. Nó cho `NaN`.

**“`0 / 0` cũng trả NaN.”** Sai. Hai toán hạng là `int` nên ném `ArithmeticException`.

**“`1 / 0.0` có tử số là int nên ném.”** Sai. Có `double` ở toán hạng phải nên promotion sang `double`; kết quả `Infinity`.

**“Gán `double x = intA / intB` sẽ tự chia số thực.”** Sai. Phép chia `int` chạy **trước** khi chuyển kiểu để gán.

**“Số 0 âm và 0 dương là một trong mọi phép toán double.”** Sai. `==` xem chúng bằng nhau, nhưng `1.0 / -0.0` và `1.0 / +0.0` khác dấu.

**“`try/catch (ArithmeticException)` sẽ bắt kết quả NaN.”** Sai. NaN là giá trị, không phải throwable.

**“`Double.NaN == Double.NaN` là true vì hai vế giống nhau.”** Sai. Equality với NaN theo số học floating-point trả false.

**“Có thể kiểm tra NaN bằng `value == Double.NaN`.”** Sai. Dùng `Double.isNaN(value)`.

**“`Infinity` chỉ xuất hiện khi chia cho zero.”** Sai. Floating-point overflow cũng tạo infinity.

**“Kiểm tra `denominator != 0.0` đủ bảo đảm kết quả hữu hạn.”** Sai. NaN, infinity và overflow có thể xảy ra từ những đầu vào khác.

**“`BigDecimal` là kiểu số thực nên chia BigDecimal.ZERO sẽ cho Infinity.”** Sai. `BigDecimal.divide` ném `ArithmeticException` khi chia cho zero.

**“`BigDecimal.divide` chỉ ném khi chia cho zero.”** Sai. Một phép chia không kết thúc thập phân mà không có rounding phù hợp cũng có thể ném.

**“`int` chia cho 0 là checked exception nên phải ghi `throws ArithmeticException`.”** Sai. `ArithmeticException` là unchecked.

**“`5.0 % 0.0` ném `ArithmeticException` giống `5 % 0`.”** Sai. Dạng dấu phẩy động cho NaN.

**“`(double) (1 / 0)` tránh được lỗi chia nguyên.”** Sai. Phép chia nguyên thực hiện trước cast.

**“Ép Infinity sang int sẽ ném ngoại lệ chia cho 0.”** Sai. Chuyển kiểu thực sang nguyên có quy tắc riêng, có thể cho giá trị biên hoặc 0.

**“`Double.MIN_VALUE` là số âm nhỏ nhất.”** Sai. Nó là số `double` dương nhỏ nhất khác 0; phân biệt với `-Double.MAX_VALUE`.

## 17. Bài tập tự kiểm tra

### Bài 1: Xác định loại phép chia

Dự đoán:

```java
int a = 6;
int b = 0;
double x = a / b;
```

**Đáp án:** ném `ArithmeticException`, vì `a / b` là phép chia `int`. Khai báo `x` là `double` không đổi loại phép chia đã xảy ra.

### Bài 2: Thêm literal `.0`

```java
int a = 6;
double x = a / 0.0;
```

**Đáp án:** `Infinity` do promotion sang `double`.

### Bài 3: Zero chia zero

```java
double x = 0.0 / -0.0;
```

**Đáp án:** `NaN`, không ném ngoại lệ.

### Bài 4: Dấu zero

```java
double x = -6.0 / -0.0;
```

**Đáp án:** `Infinity`.

### Bài 5: Integer remainder

```java
int remainder = 6 % 0;
```

**Đáp án:** `ArithmeticException`.

### Bài 6: Floating remainder

```java
double remainder = 6.0 % 0.0;
```

**Đáp án:** `NaN`.

### Bài 7: Cast trước hay sau?

```java
int a = 1;
int b = 2;
System.out.println((double) (a / b));
System.out.println((double) a / b);
```

**Đáp án:** dòng đầu in `0.0`, dòng sau in `0.5`.

### Bài 8: Kiểm tra NaN

```java
double x = 0.0 / 0.0;
System.out.println(x == x);
System.out.println(Double.isNaN(x));
```

**Đáp án:** `false` rồi `true`.

### Bài 9: Infinity không do zero

```java
double x = Double.MAX_VALUE * 2.0;
```

**Đáp án:** `Infinity`, dù không có phép chia.

### Bài 10: BigDecimal

```java
java.math.BigDecimal.ONE.divide(java.math.BigDecimal.ZERO);
```

**Đáp án:** `ArithmeticException`, không phải infinity.

### Bài 11: Chuyển kiểu kết quả đặc biệt

```java
System.out.println((int) (0.0 / 0.0));
```

**Đáp án:** `0`. Đây là kết quả narrowing từ NaN sang int, không phải kết quả phép chia thực.

### Bài 12: API cần hữu hạn

Nếu yêu cầu “không được trả infinity hay NaN”, kiểm tra mẫu số bằng `denominator == 0.0` **đã đủ chưa?** **Chưa.** Kiểm tra tính hữu hạn của đầu vào và kết quả, đồng thời chọn chính sách phù hợp cho tràn/underflow.

### Bài 13: Checked hay unchecked?

`ArithmeticException` thuộc checked hay unchecked? **Unchecked**, vì kế thừa `RuntimeException`.

### Bài 14: Dấu zero

`0.0 == -0.0` là `true`. Vậy `1.0 / 0.0` và `1.0 / -0.0` có giống nhau không? **Không**: một kết quả `Infinity`, kết quả còn lại `-Infinity`.

### Bài 15: Chặn NaN khỏi kiểm tra ngưỡng

Với `double value = Double.NaN`, biểu thức `value < 0 || value > 100` có phát hiện giá trị không hợp lệ không? **Không**, hai so sánh đều false. Nên dùng thêm `Double.isFinite(value)` khi yêu cầu chỉ chấp nhận số hữu hạn.

## 18. Tài liệu chính thức Java 17

- [Java Language Specification 17 — `15.17.2 Division Operator /](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): chia nguyên, chia floating-point và zero.
- [Java Language Specification 17 — `15.17.3 Remainder Operator %](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): lấy dư nguyên và floating-point.
- [Java Language Specification 17 — `5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): numeric promotion và kiểu toán hạng.
- [Java Language Specification 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): infinity, NaN, signed zero và giá trị floating-point.
- [Java Language Specification 17 — `5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3): chuyển NaN/infinity từ float/double sang kiểu nguyên.
- [Java SE 17 — ArithmeticException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html): unchecked exception của các điều kiện số học bất hợp lệ.
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `isNaN`, `isInfinite`, `isFinite` và các hằng số đặc biệt.
- [Java SE 17 — Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): kiểm tra và biểu diễn giá trị float.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): divide, rounding và lỗi `ArithmeticException`.
- [Java SE 17 — Math.IEEEremainder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#IEEEremainder(double,double)): so sánh với toán tử `%`.

**Ghi nhớ:** Với toán tử `/` và `%` của **kiểu nguyên** Java, mẫu số bằng 0 gây `ArithmeticException` (unchecked). Với `float`/`double`, phép toán dùng ngữ nghĩa IEEE 754 nên có thể trả `Infinity`, `-Infinity` hoặc `NaN` **mà không ném ngoại lệ**. Hãy xét kiểu toán hạng sau numeric promotion, không chỉ xét literal `0`; dùng `Double.isNaN`/`Double.isInfinite`/`Double.isFinite` và chính sách validation rõ ràng nếu ứng dụng không chấp nhận các giá trị đặc biệt.
