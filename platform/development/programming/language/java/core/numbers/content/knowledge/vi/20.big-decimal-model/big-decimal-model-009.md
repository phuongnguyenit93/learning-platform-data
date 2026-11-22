# BigDecimal không có NaN hoặc vô cực trong Java

`BigDecimal` và `double` đều biểu diễn số, nhưng **không có cùng tập giá trị**. Các kiểu dấu phẩy động nhị phân `double`/`float` theo IEEE 754 hỗ trợ ba loại giá trị đặc biệt: **NaN** (*Not a Number*), **dương vô cực** (`+Infinity`) và **âm vô cực** (`-Infinity`). `java.math.BigDecimal` **không có bất kỳ giá trị nào trong ba loại đó**; nó dùng số nguyên unscaled và scale để biểu diễn các **giá trị thập phân hữu hạn**, với miền độ lớn thực tế bị giới hạn bởi tài nguyên và kiểu `int` của scale.

Hậu quả quan trọng:

- Không tạo được một `BigDecimal` “chứa NaN” hoặc “chứa Infinity” bằng constructor hay `valueOf(double)`.
- Các phép `BigDecimal` không dùng vô cực để biểu diễn phép chia cho zero; chúng **ném `ArithmeticException`**.
- `BigDecimal` rất lớn/nhỏ vẫn hữu hạn trong mô hình decimal, nhưng khi gọi `doubleValue()` có thể bị chuyển thành `Infinity` hoặc `0.0` do giới hạn của binary64.
- Khi một API dùng `double` giao dữ liệu cho tầng `BigDecimal`, phải **xác thực số hữu hạn trước khi chuyển** và chọn chính sách lỗi rõ ràng.

Bài Knowledge thuộc nhóm **Mô hình BigDecimal** của Java Core, trình bày cơ chế và ví dụ Java 17+ kiểm chứng từng ranh giới.

## 1. Tập giá trị: BigDecimal so với double

Một đối tượng `BigDecimal` được mô tả bằng cặp `unscaledValue`, `scale`, với công thức:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Trong đó `unscaledValue` là một số nguyên `BigInteger` và `scale` là số nguyên `int`. Với một cặp hợp lệ và có thể xây được, kết quả là một số thập phân hữu hạn; **không có mã đặc biệt để biểu diễn NaN hoặc vô cực**.

| Thuộc tính | `double` / `float` | `BigDecimal` |
| --- | --- | --- |
| Biểu diễn | IEEE 754 binary64/binary32 | Decimal qua unscaled integer và scale |
| NaN | Có | **Không** |
| `+Infinity`, `-Infinity` | Có | **Không** |
| Số 0 có dấu `+0.0`/`-0.0` | Phân biệt được dấu ở biểu diễn bit | **Không giữ riêng negative zero** |
| Số hữu hạn rất lớn | Có giới hạn exponent và độ chính xác nhị phân | Không có giới hạn exponent kiểu binary64; vẫn chịu giới hạn scale `int` và bộ nhớ |
| `1.0 / 0.0` | `Infinity` | `divide(BigDecimal.ZERO)` ném `ArithmeticException` |
| `0.0 / 0.0` | `NaN` | `BigDecimal.ZERO.divide(BigDecimal.ZERO)` ném `ArithmeticException` |
| Giá trị 1/3 chính xác ở decimal hữu hạn | Không biểu diễn chính xác | `divide` không rounding ném lỗi; có thể tính xấp xỉ với chính sách |
| Kiểu dữ liệu kết quả | Primitive `double` hoặc `float` | Object `BigDecimal` bất biến |

Không thể suy ra rằng “BigDecimal chính xác hơn” nghĩa là nó hỗ trợ mọi trạng thái của IEEE 754. **Độ chính xác và tập giá trị là hai vấn đề khác nhau.** `BigDecimal` thường thích hợp với số tiền và decimal cố định; `double` thích hợp nhiều phép đo và tính toán số học cần dải exponent rộng, đồng thời mang các giá trị đặc biệt.

## 2. NaN và Infinity có thể xuất hiện trong double như thế nào?

Trong Java, các biểu thức dấu phẩy động có thể tạo ra giá trị không hữu hạn:

~~~java
double nan = 0.0 / 0.0;         // NaN
double positive = 1.0 / 0.0;    // Infinity
double negative = -1.0 / 0.0;   // -Infinity

System.out.println(Double.isNaN(nan));       // true
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isFinite(negative));   // false
~~~

NaN còn có thể xuất hiện từ `Math.sqrt(-1.0)` hoặc `Infinity - Infinity`. Infinity có thể xuất hiện khi phép tính `double` bị overflow. Đây là những kết quả hợp lệ theo ngữ nghĩa dấu phẩy động, **không nhất thiết là ngoại lệ Java được ném**.

Ba công cụ nên nhớ:

- `Double.isNaN(x)`: xác định NaN, thay vì `x == Double.NaN` (luôn false với NaN).
- `Double.isInfinite(x)`: xác định dương hoặc âm vô cực.
- `Double.isFinite(x)`: true nếu và chỉ nếu không phải NaN/vô cực.

Có API tương ứng trên `Float`. `Double.isFinite(-0.0)` vẫn là true: số 0, dù có dấu âm trong binary64, là một giá trị **hữu hạn**.

Không dùng `x != x` thay `isNaN` trong mã nghiệp vụ nếu có API trực tiếp; cách đó khó đọc và dễ khiến người bảo trì bỏ lỡ ý định xác thực.

## 3. Tạo BigDecimal từ NaN hoặc Infinity sẽ lỗi

Các cách tạo đối tượng không thể biến trạng thái không hữu hạn thành một giá trị `BigDecimal`:

~~~java
// Mỗi lời gọi sau ném NumberFormatException:
new BigDecimal(Double.NaN);
new BigDecimal(Double.POSITIVE_INFINITY);
BigDecimal.valueOf(Double.NaN);
BigDecimal.valueOf(Double.NEGATIVE_INFINITY);
new BigDecimal("NaN");
new BigDecimal("Infinity");
~~~

**`NumberFormatException`** trong các trường hợp này thể hiện rằng đầu vào không thể là một biểu diễn `BigDecimal` hợp lệ. Constructor `BigDecimal(double)` không chấp nhận NaN/Infinity; `BigDecimal.valueOf(double)` dùng `Double.toString(double)`, nhưng dạng chuỗi `"NaN"` hoặc `"Infinity"` cũng không được constructor chuỗi của `BigDecimal` chấp nhận.

Điểm phân biệt quan trọng:

~~~java
Double.parseDouble("NaN");         // Double.NaN
Double.parseDouble("Infinity");    // Double.POSITIVE_INFINITY

// new BigDecimal("NaN");      // NumberFormatException
// new BigDecimal("Infinity"); // NumberFormatException
~~~

**Cùng một văn bản không nhất thiết được hai parser chấp nhận.** `Double.parseDouble` phục vụ kiểu `double` với các giá trị đặc biệt; `BigDecimal(String)` yêu cầu cú pháp số thập phân hữu hạn hợp lệ. Không cố parse chuỗi đặc biệt thành decimal rồi giả định ngoại lệ đồng nghĩa giá trị bằng zero.

Cũng không phải `BigDecimal.valueOf(Double.MAX_VALUE)` là vô cực. `Double.MAX_VALUE` vẫn là giá trị **hữu hạn** (dù rất lớn) và có thể chuyển sang `BigDecimal`. Ngoại lệ chỉ xảy ra khi **giá trị double đầu vào đã là NaN hoặc ±Infinity** hoặc không thể chuyển đổi theo các giới hạn khác của API.

## 4. Chia cho zero: ArithmeticException thay vì Infinity hoặc NaN

So sánh phép chia cùng biểu thức toán học:

~~~java
double infinity = 1.0 / 0.0; // Infinity
double undefined = 0.0 / 0.0; // NaN

// BigDecimal.ONE.divide(BigDecimal.ZERO);  // ArithmeticException
// BigDecimal.ZERO.divide(BigDecimal.ZERO); // ArithmeticException
~~~

`BigDecimal` không có phần tử vô cực/NaN trong tập giá trị, nên không có một đối tượng hợp lệ để biểu diễn các kết quả ấy. Với phép chia cho zero, hành vi là **ném ngoại lệ**.

Với `BigDecimal.ZERO.divide(BigDecimal.ZERO)`, thông báo exception có thể khác trường hợp `BigDecimal.ONE.divide(BigDecimal.ZERO)`; không dùng `getMessage()` như một mã lỗi nghiệp vụ ổn định. Nên bắt theo **loại ngoại lệ** hoặc — tốt hơn — kiểm tra tiền điều kiện `divisor.signum() == 0` trước khi tính nếu cần thông báo dễ hiểu.

Ví dụ phương thức kiểm tra mẫu số:

~~~java
static BigDecimal safeDivide(
        BigDecimal numerator,
        BigDecimal denominator,
        int scale,
        RoundingMode mode) {
    if (denominator.signum() == 0) {
        throw new IllegalArgumentException("denominator must be nonzero");
    }
    return numerator.divide(denominator, scale, mode);
}
~~~

Đây là **phương thức minh họa trong một class**; caller cần kiểm tra null hoặc định nghĩa chính sách null phù hợp. Truyền `denominator = null` vào `denominator.signum()` vẫn sẽ ném `NullPointerException`; validation không thể tự động thay thế hợp đồng null.

**Một lỗi khác cùng lớp ngoại lệ:** phép chia **không có khai triển thập phân hữu hạn** cũng có thể ném `ArithmeticException` khi không chỉ định rounding. Ví dụ `BigDecimal.ONE.divide(new BigDecimal("3"))` không có nghiệm decimal hữu hạn; nó ném lỗi dù mẫu số khác zero.

~~~java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        5,
        RoundingMode.HALF_UP);
// third = 0.33333
~~~

Đặt scale và rounding mode phù hợp sẽ xử lý **kết quả chia lặp vô hạn về thập phân**, **không** khiến phép chia cho zero trở nên hợp lệ.

## 5. BigDecimal cực lớn vẫn hữu hạn — nhưng double có thể là Infinity

Một `BigDecimal` có thể biểu diễn `10^400` bằng:

~~~java
BigDecimal huge = new BigDecimal("1E+400");
System.out.println(huge); // 1E+400
~~~

Nó có một unscaled value hữu hạn và scale âm, nên là số thập phân hợp lệ. Nhưng kiểu `double` chỉ có dải exponent hữu hạn. Khi chuyển:

~~~java
double narrowed = huge.doubleValue();
System.out.println(narrowed);                 // Infinity
System.out.println(Double.isFinite(narrowed)); // false
~~~

**Không có mâu thuẫn** với tiêu đề bài: đối tượng `BigDecimal` vẫn giữ giá trị hữu hạn `1E+400`; chỉ có **kết quả của phép chuyển kiểu sang `double`** là Infinity vì vượt phạm vi số hữu hạn binary64.

Ngược lại, một decimal cực nhỏ cũng có thể làm mất thông tin khi chuyển sang binary64:

~~~java
BigDecimal tiny = new BigDecimal("1E-400");
double narrowed = tiny.doubleValue();
System.out.println(narrowed); // 0.0
~~~

Ở đây `tiny` khác zero về toán học, nhưng sau narrowing thành `double` nó underflow về 0.0. Một kết quả `double` **hữu hạn** (ví dụ 0.0) chưa chắc giữ nguyên giá trị decimal đầu vào.

`BigDecimal.floatValue()` cũng có nguy cơ tương tự, với dải hữu hạn còn hẹp hơn. Khi hợp đồng cần giữ giá trị decimal chính xác, hãy **tiếp tục tính toán bằng BigDecimal** và xuất dưới dạng decimal thích hợp thay vì ép sang `float`/`double`.

Không có `doubleValueExact()` như `intValueExact()` cho số nguyên. Nếu cần kiểm tra conversion decimal→double, bạn phải đặt tiêu chí phù hợp cho phạm vi, độ chính xác được phép mất và các trạng thái không hữu hạn.

## 6. Không đồng nhất “giá trị hữu hạn” với “giá trị chính xác khi qua double”

Có ba tình huống độc lập cần phân biệt:

1. **`double` hữu hạn nhưng xấp xỉ giá trị decimal mong đợi**, ví dụ literal `0.1` là một biểu diễn binary64 gần 1/10.
2. **`BigDecimal` hữu hạn và chính xác như chuỗi decimal**, ví dụ `new BigDecimal("0.1")` giữ đúng 1/10.
3. **`BigDecimal` hữu hạn nhưng chuyển sang `double` bị overflow/underflow/làm tròn**, ví dụ `1E+400` thành Infinity hoặc `1E-400` thành 0.0.

~~~java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal binaryExact = new BigDecimal(0.1);
BigDecimal canonical = BigDecimal.valueOf(0.1);
~~~

`exact` là 0.1 decimal chính xác; `binaryExact` giữ đúng giá trị binary64 của `double 0.1` nên có đuôi dài; `canonical` dựa trên dạng chuỗi round-trip của `Double.toString(0.1)`, thường là lựa chọn hợp lý khi dữ liệu bắt buộc đã đến dưới dạng `double` hữu hạn. Không có cách nào trong số đó “nâng” NaN hoặc Infinity thành một `BigDecimal` hợp lệ.

**Chú ý nguồn dữ liệu:** nếu một chuỗi đầu vào là `"1E+400"`, `new BigDecimal("1E+400")` biểu diễn số hữu hạn lớn trực tiếp. Nếu parse nó thành `double` trước, `Double.parseDouble("1E+400")` có thể trả Infinity, và bạn đã mất cơ hội chuyển tiếp giá trị decimal chính xác đó qua pipeline `double`.

## 7. Thiết kế ranh giới API an toàn

Khi một đầu vào `double` được phép chuyển sang `BigDecimal` **chỉ khi hữu hạn**, hãy kiểm tra ở ranh giới:

~~~java
static BigDecimal requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("value must be finite");
    }
    return BigDecimal.valueOf(value);
}
~~~

Phương thức trên thực sự tạo decimal khi giá trị `double` hữu hạn. Nó **không đảm bảo** decimal vừa tạo bằng giá trị thập phân con người dự định trước các phép tính `double`; cũng không bảo đảm decimal không sai số. Nó chỉ tránh trường hợp NaN/vô cực bị đưa vào constructor không hỗ trợ.

Khi đầu vào từ chuỗi, có thể tạo `new BigDecimal(text)` trực tiếp, sau khi xác thực null, cú pháp, độ dài, scale, số chữ số và miền nghiệp vụ. Việc parse chuỗi có thể ném `NumberFormatException` vì nhiều lý do, không chỉ NaN/vô cực.

Khi kết quả decimal sắp đi tới một API nhận `double`, hãy xem xét cả hai bước:

~~~java
BigDecimal amount = new BigDecimal("1E+400");
double output = amount.doubleValue();
if (!Double.isFinite(output)) {
    throw new IllegalArgumentException("result cannot fit in finite double");
}
~~~

Kiểm tra này phát hiện overflow ra Infinity, nhưng **không đủ** để loại các phép chuyển hữu hạn song mất precision hoặc underflow về 0.0. Nếu cần *exact round-trip*, hãy giữ một contract rõ về giá trị và biểu diễn; chẳng hạn chuyển lại và so sánh theo miền dữ liệu, trong đó phải lưu ý ngữ nghĩa scale và các giá trị đặc biệt.

Nếu tầng nhận dữ liệu vẫn cần biểu diễn NaN hoặc vô cực như một trạng thái nghiệp vụ, **đừng dùng BigDecimal làm “container” cho các trạng thái đó**. Tạo kiểu kết quả có phân biệt *giá trị hữu hạn*, *thiếu dữ liệu*, *không xác định* hoặc *vượt phạm vi*.

## 8. Chương trình Java 17+ có thể biên dịch và chạy

Tạo tệp `DecimalFiniteDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalFiniteDemo {
    static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " = OK");
        } catch (RuntimeException ex) {
            System.out.println(label + " = "
                    + ex.getClass().getSimpleName());
        }
    }

    static BigDecimal requireFinite(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("value must be finite");
        }
        return BigDecimal.valueOf(value);
    }

    public static void main(String[] args) {
        System.out.println("Double NaN detected = "
                + Double.isNaN(Double.NaN));
        System.out.println("Double +Infinity detected = "
                + Double.isInfinite(Double.POSITIVE_INFINITY));
        System.out.println("Double -Infinity finite = "
                + Double.isFinite(Double.NEGATIVE_INFINITY));
        System.out.println("finite decimal = "
                + new BigDecimal("12.50"));

        attempt("NaN double constructor",
                () -> new BigDecimal(Double.NaN));
        attempt("+Infinity double constructor",
                () -> new BigDecimal(Double.POSITIVE_INFINITY));
        attempt("NaN valueOf",
                () -> BigDecimal.valueOf(Double.NaN));
        attempt("-Infinity valueOf",
                () -> BigDecimal.valueOf(Double.NEGATIVE_INFINITY));
        attempt("NaN string", () -> new BigDecimal("NaN"));
        attempt("Infinity string", () -> new BigDecimal("Infinity"));

        System.out.println("double 1/0 = " + (1.0 / 0.0));
        System.out.println("double 0/0 is NaN = "
                + Double.isNaN(0.0 / 0.0));
        attempt("decimal 1/0",
                () -> BigDecimal.ONE.divide(BigDecimal.ZERO));
        attempt("decimal 0/0",
                () -> BigDecimal.ZERO.divide(BigDecimal.ZERO));
        attempt("decimal 1/3 exact",
                () -> BigDecimal.ONE.divide(BigDecimal.valueOf(3)));
        System.out.println("decimal 1/3 rounded = "
                + BigDecimal.ONE.divide(
                        BigDecimal.valueOf(3),
                        5, RoundingMode.HALF_UP));

        BigDecimal huge = new BigDecimal("1E+400");
        BigDecimal tiny = new BigDecimal("1E-400");
        System.out.println("huge BigDecimal = " + huge);
        System.out.println("huge to double = " + huge.doubleValue());
        System.out.println("huge to double is finite = "
                + Double.isFinite(huge.doubleValue()));
        System.out.println("tiny BigDecimal = " + tiny);
        System.out.println("tiny to double = " + tiny.doubleValue());
        System.out.println("tiny to double is finite = "
                + Double.isFinite(tiny.doubleValue()));

        System.out.println("negative zero decimal = "
                + new BigDecimal("-0.00"));
        System.out.println("negative zero decimal scale = "
                + new BigDecimal("-0.00").scale());
        System.out.println("finite guard 2.5 = " + requireFinite(2.5));
        attempt("finite guard Infinity",
                () -> requireFinite(Double.POSITIVE_INFINITY));
    }
}
~~~

Chạy trên Java 17 trở lên:

~~~bash
javac DecimalFiniteDemo.java
java DecimalFiniteDemo
~~~

Stdout chính xác:

~~~text
Double NaN detected = true
Double +Infinity detected = true
Double -Infinity finite = false
finite decimal = 12.50
NaN double constructor = NumberFormatException
+Infinity double constructor = NumberFormatException
NaN valueOf = NumberFormatException
-Infinity valueOf = NumberFormatException
NaN string = NumberFormatException
Infinity string = NumberFormatException
double 1/0 = Infinity
double 0/0 is NaN = true
decimal 1/0 = ArithmeticException
decimal 0/0 = ArithmeticException
decimal 1/3 exact = ArithmeticException
decimal 1/3 rounded = 0.33333
huge BigDecimal = 1E+400
huge to double = Infinity
huge to double is finite = false
tiny BigDecimal = 1E-400
tiny to double = 0.0
tiny to double is finite = true
negative zero decimal = 0.00
negative zero decimal scale = 2
finite guard 2.5 = 2.5
finite guard Infinity = IllegalArgumentException
~~~

Đọc output theo cơ chế:

- Các constructor/factory từ NaN và Infinity ném **`NumberFormatException`**, vì không có đối tượng `BigDecimal` tương ứng.
- Các phép chia `BigDecimal` không được phép theo ngữ nghĩa decimal hữu hạn ném **`ArithmeticException`**; một phép chia `1/3` với scale và rounding cụ thể có thể cho số decimal hữu hạn xấp xỉ.
- `huge` và `tiny` là **hai BigDecimal hợp lệ và hữu hạn**; vấn đề chỉ xuất hiện khi gọi `doubleValue()`. Trường hợp dưới 0 nhưng rất nhỏ chuyển thành 0.0 mà `Double.isFinite` vẫn true, cho thấy **finite check không đồng nghĩa exactness check**.
- `new BigDecimal("-0.00")` giữ scale hai chữ số nhưng giá trị in là `0.00`; không có mã negative-zero riêng theo IEEE 754.
- `requireFinite` chặn Infinity **trước** khi chọn `BigDecimal.valueOf`; trong ví dụ nó báo `IllegalArgumentException` do chính ứng dụng định nghĩa, không phải lỗi parser mặc định.

Hàm `attempt` bắt `RuntimeException` **chỉ để demo loại ngoại lệ một cách có kiểm soát**. Trong ứng dụng thật, không nên sử dụng catch quá rộng để nuốt lỗi hoặc mặc định trả 0; cần bắt có chủ đích ở biên giao tiếp, nêu rõ nguồn lỗi và giữ ngữ cảnh thích hợp.

## 9. Phân biệt lỗi NumberFormatException, ArithmeticException và validation error

| Tình huống | Loại kết quả/lỗi | Cách xử lý gợi ý |
| --- | --- | --- |
| `new BigDecimal(Double.NaN)` | `NumberFormatException` | Từ chối input non-finite |
| `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` | `NumberFormatException` | Kiểm tra `Double.isFinite` trước |
| `new BigDecimal("NaN")` hoặc `"Infinity"` | `NumberFormatException` | Báo cú pháp không hợp lệ cho decimal |
| `BigDecimal.ONE.divide(BigDecimal.ZERO)` | `ArithmeticException` | Kiểm tra mẫu số khác zero |
| `BigDecimal.ZERO.divide(BigDecimal.ZERO)` | `ArithmeticException` | Xử lý phép tính không xác định |
| `BigDecimal.ONE.divide(new BigDecimal("3"))` | `ArithmeticException` | Dùng overload có rounding nếu nghiệp vụ cho phép |
| `new BigDecimal("1E+400").doubleValue()` | `Infinity` dạng `double` | Kiểm tra overflow và thiết kế dữ liệu đầu ra |
| `new BigDecimal("1E-400").doubleValue()` | `0.0` dạng `double` | Kiểm tra mất precision/underflow nếu quan trọng |
| `requireFinite(Double.NaN)` trong ví dụ | `IllegalArgumentException` | Lỗi validation do ứng dụng định nghĩa |

**Điểm cần nhớ:** `NumberFormatException` nói đầu vào **không tạo được BigDecimal hợp lệ**; `ArithmeticException` nói **phép toán decimal đã yêu cầu không thực hiện được dưới hợp đồng hiện tại**. Đừng viết `catch (NumberFormatException)` và kỳ vọng bắt luôn phép chia cho zero. Ngược lại, không nên đánh đồng mọi `ArithmeticException` với chia cho zero: phép chia decimal vô hạn không rounding cũng có thể ném cùng loại.

Không dựa vào nội dung `getMessage()` như một mã phân loại ổn định. Khi cần xác định nghiệp vụ “chia cho 0”, hãy kiểm tra `denominator.signum() == 0` trước phép chia và chuyển thành lỗi rõ nghĩa.

## 10. Dữ liệu thiếu, NaN và các trạng thái không hợp lệ nên được mô hình hóa riêng

`null`, `NaN`, vô cực, và số 0 mang **những ý nghĩa khác nhau**. Không nên dùng một số decimal giả như `0` hoặc `-1` để đại diện đồng thời cho tất cả trạng thái này nếu chúng có thể là giá trị nghiệp vụ hợp lệ.

Một API trả kết quả tính toán có thể dùng một kiểu kết quả phân biệt:

~~~java
sealed interface AmountResult
        permits AmountResult.Finite,
                AmountResult.Missing,
                AmountResult.Invalid {
    record Finite(BigDecimal value) implements AmountResult {}
    record Missing() implements AmountResult {}
    record Invalid(String reason) implements AmountResult {}
}
~~~

Đây là **đoạn khai báo minh họa**, cần đặt trong tệp và ngữ cảnh class/package hợp lệ của ứng dụng Java 17+, không phải chương trình độc lập có `main`. Khi dùng trong hệ thống, đặt `BigDecimal` vào `Finite` **chỉ sau khi validation**, yêu cầu object không null (ví dụ kiểm tra `Objects.requireNonNull` trong constructor), và lựa chọn thêm trạng thái overflow/undefined nếu cần.

Có thể chọn `Optional<BigDecimal>` nếu chỉ cần “có giá trị hữu hạn hay không”, nhưng `Optional.empty()` **không nói nguyên nhân**. Với ứng dụng cần chẩn đoán dữ liệu không hợp lệ, một kiểu kết quả có thông tin lỗi thường tốt hơn.

Với API nhận `double`, lựa chọn thường là **từ chối mọi non-finite** (fail fast) trước khi tính decimal. Nếu bài toán khoa học cần lan truyền NaN/Infinity theo IEEE 754, có thể phải giữ pipeline ở kiểu `double` hoặc tạo mô hình trạng thái rõ ràng — `BigDecimal` không tự cung cấp phép lan truyền NaN.

## 11. Lưu và trao đổi dữ liệu giữa JSON, CSV, database và BigDecimal

Khi kết nối các hệ thống, cần xác định **hợp đồng biểu diễn**:

- Nếu trường là một số decimal hợp lệ, đọc trực tiếp dạng chuỗi decimal hoặc kiểu decimal chính xác thành `BigDecimal`; không ép qua `double` nếu cần giữ nguyên precision/scale.
- Nếu dữ liệu nguồn có thể là NaN/Infinity, chuẩn hóa thành **trạng thái riêng** hoặc báo lỗi theo hợp đồng, không giả vờ đó là một `BigDecimal`.
- JSON chuẩn có ngữ pháp số không bao gồm token NaN hoặc Infinity như số; nếu nhà cung cấp gửi chuỗi `"NaN"` hoặc `"Infinity"`, chuỗi đó vẫn không phải decimal hợp lệ và cần chính sách riêng. Một thư viện có thể hỗ trợ tiện ích ngoài chuẩn, nhưng không suy ra mọi parser đều như vậy.
- Trong CSV, giá trị trống, `"NaN"` và `"0"` phải được xử lý theo quy tắc dữ liệu — chúng không tự tương đương.
- Khi truy vấn database, cần phân biệt `NULL` với một số decimal 0; behavior của các kiểu số đặc biệt phụ thuộc hệ quản trị và kiểu cột, không nên suy luận từ Java.

Định dạng xuất `BigDecimal.toString()` có thể dùng ký pháp khoa học cho số rất lớn/nhỏ; `toPlainString()` tránh ký pháp khoa học nhưng có thể tạo chuỗi cực dài với scale lớn. Khi lưu dữ liệu số decimal, hãy giới hạn kích thước/scale theo nghiệp vụ để kiểm soát tài nguyên.

## 12. Các lỗi phổ biến cần tránh

1. **“BigDecimal chính xác hơn double nên phải có Infinity chính xác hơn.”** Sai: `BigDecimal` không biểu diễn Infinity/NaN.
2. **“BigDecimal chia cho zero sẽ tạo Infinity.”** Sai: ném `ArithmeticException`.
3. **“0/0 bằng 0 vì BigDecimal không có NaN.”** Sai: phép chia cho zero không hợp lệ, không được tự đổi thành 0.
4. **“BigDecimal.valueOf(NaN) trả null.”** Sai: ném `NumberFormatException`.
5. **“new BigDecimal("NaN") cho một số decimal đặc biệt.”** Sai: chuỗi không hợp lệ với parser decimal.
6. **“Mọi phép chia `BigDecimal` ném ArithmeticException đều do mẫu số 0.”** Sai: khai triển thập phân vô hạn không rounding cũng có thể gây lỗi.
7. **“Đặt rounding mode sẽ cho phép chia cho zero.”** Sai: rounding chỉ xử lý độ chính xác của phép chia hợp lệ, không tạo giá trị cho mẫu số 0.
8. **“BigDecimal hữu hạn thì doubleValue cũng hữu hạn.”** Sai: decimal lớn có thể bị overflow thành Infinity.
9. **“doubleValue hữu hạn nghĩa là không mất thông tin.”** Sai: nó có thể làm tròn hoặc underflow về 0.0.
10. **“Kết quả `Double.isFinite` true chứng minh decimal ban đầu đã được bảo toàn.”** Sai: một số decimal khác zero có thể chuyển thành 0.0 và vẫn finite.
11. **“Chuỗi số decimal rất lớn nhất định phải qua double trước.”** Sai: parse trực tiếp thành `BigDecimal` có thể giữ được dữ liệu decimal.
12. **“BigDecimal giữ được `-0.0` như double.”** Sai: BigDecimal không có mã negative zero riêng; nó vẫn có thể giữ scale của chuỗi `"-0.00"`.
13. **“NaN đồng nghĩa null/thiếu giá trị.”** Sai: các trạng thái mang ý nghĩa khác nhau; không gộp tùy tiện.
14. **“Bắt mọi exception rồi trả BigDecimal.ZERO là an toàn.”** Sai: làm mất tín hiệu lỗi, có thể khiến kết quả tài chính sai.
15. **“Không cần kiểm tra giới hạn đầu vào vì BigDecimal có độ chính xác tùy ý.”** Sai: unscaled integer, scale, tạo chuỗi và phép toán vẫn có giới hạn tài nguyên và đặc tả.
16. **“Có thể dùng BigDecimal để tự mô phỏng IEEE 754 decimal floating point đầy đủ.”** Sai: IEEE 754 decimal có thêm các lớp giá trị đặc biệt và các ràng buộc format/exponent không giống mô hình BigDecimal.

## 13. Checklist tích hợp an toàn

1. Xác định trường đầu vào là **decimal chính xác** hay `double` có thể chứa NaN/Infinity.
2. Nếu nguồn là `double`, kiểm tra `Double.isFinite` trước khi chuyển; chọn chính sách khi NaN/vô cực xuất hiện.
3. Nếu nguồn là chuỗi, parse trực tiếp thành `BigDecimal` sau khi kiểm tra cú pháp và giới hạn input; bắt `NumberFormatException` tại ranh giới.
4. Nếu tính phép chia decimal, xác minh mẫu số khác 0; chọn `scale`, `precision` và `RoundingMode` nếu kết quả không thể biểu diễn chính xác.
5. Không mặc định mọi `ArithmeticException` đều nghĩa là chia cho 0.
6. Trước khi xuất `BigDecimal` thành `double`/`float`, đánh giá khả năng overflow, underflow và mất chính xác.
7. Phân biệt null, dữ liệu sai, số 0, NaN và vô cực theo hợp đồng API; không dùng một sentinel mơ hồ.
8. Với tiền tệ và số liệu quan trọng, giữ phép tính ở `BigDecimal` đến tầng xuất thích hợp; không đi qua binary64 khi không cần.
9. Thiết kế kiểm thử ranh giới cho `NaN`, `±Infinity`, số 0, mẫu số 0, `1/3`, decimal rất lớn và rất nhỏ.
10. Khi báo lỗi cho người dùng, sử dụng thông điệp nghiệp vụ rõ ràng và tránh log thừa dữ liệu nhạy cảm.

## 14. Câu hỏi tự luyện

**Câu 1.** `new BigDecimal(Double.NaN)` trả gì? `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` thì sao?

**Đáp án:** Cả hai ném `NumberFormatException` vì `BigDecimal` không có giá trị tương ứng với NaN hoặc vô cực.

**Câu 2.** `BigDecimal.ONE.divide(BigDecimal.ZERO)` và `1.0/0.0` có hành vi tương tự không?

**Đáp án:** Không. BigDecimal ném `ArithmeticException`; `double` tạo dương Infinity.

**Câu 3.** Vì sao `BigDecimal.ONE.divide(new BigDecimal("3"))` có thể ném `ArithmeticException` dù mẫu số khác zero?

**Đáp án:** Thương 1/3 không có biểu diễn decimal hữu hạn; overload chia chính xác không cho phép tự làm tròn. Cần chỉ định precision/scale và rounding nếu nghiệp vụ cho phép xấp xỉ.

**Câu 4.** `new BigDecimal("1E+400")` là vô cực không? Còn kết quả `doubleValue()`?

**Đáp án:** BigDecimal là số hữu hạn hợp lệ; ép sang `double` có thể trở thành `Infinity` vì overflow binary64.

**Câu 5.** `new BigDecimal("1E-400").doubleValue()` có cho số hữu hạn không và có bảo toàn giá trị không?

**Đáp án:** Cho `0.0` hữu hạn trong ví dụ, nhưng không bảo toàn giá trị decimal 10^-400 khác zero.

**Câu 6.** Nếu một dịch vụ trả chuỗi `"NaN"` thay vì số tiền, có nên dùng `new BigDecimal("NaN")` hoặc tự thay bằng 0?

**Đáp án:** Không. Nên xác định trạng thái “dữ liệu không hợp lệ/không xác định” trong hợp đồng và xử lý riêng, thay vì gán một amount 0 không có cơ sở.

**Câu 7.** `Double.isFinite(amount.doubleValue())` true có đủ chứng minh conversion không mất chính xác không?

**Đáp án:** Không. Tính hữu hạn không kiểm tra round-trip chính xác; underflow và làm tròn vẫn có thể xảy ra.

## Tài liệu tham khảo

- [Oracle Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): mô hình unscaled/scale, khác biệt với IEEE 754 về NaN/vô cực/negative zero, lỗi khi chia 0, `doubleValue` và constructor.
- [Oracle Java SE 21 — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `isNaN`, `isInfinite`, `isFinite`, `parseDouble`.
- [Oracle Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): chính sách làm tròn khi tính số decimal.
- [Oracle Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision và rounding trong phép toán BigDecimal.
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): ngữ pháp JSON number không có NaN/Infinity.
