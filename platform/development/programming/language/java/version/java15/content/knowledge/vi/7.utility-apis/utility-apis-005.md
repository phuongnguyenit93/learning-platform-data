# Math.absExact cho int, long — phát hiện tràn số khi lấy giá trị tuyệt đối

## 1. `Math.absExact` giải quyết vấn đề gì?

Trong Java, giá trị tuyệt đối của một số nguyên `x` là `|x|`: nếu `x` âm thì đổi dấu; nếu không âm thì giữ nguyên. Với `int` và `long`, phép đổi dấu **không luôn biểu diễn được** trong chính kiểu dữ liệu đó.

Kể từ **Java 15**, lớp `java.lang.Math` có hai overload vẫn được hỗ trợ trong các bản Java hiện hành:

~~~java
public static int absExact(int a)
public static long absExact(long a)
~~~

- Nếu giá trị tuyệt đối **biểu diễn được** trong kiểu đầu vào, phương thức trả về giá trị đó.
- Nếu `a == Integer.MIN_VALUE` (overload `int`) hoặc `a == Long.MIN_VALUE` (overload `long`), phương thức ném `ArithmeticException` vì kết quả dương bị tràn miền biểu diễn.
- Ngoại trừ trường hợp tràn, kết quả là số **không âm** cùng kiểu với tham số (`int` hoặc `long`).

`Math.absExact` là một API thông thường, ổn định từ Java 15, không cần flag thử nghiệm. Phương thức phù hợp khi logic nghiệp vụ yêu cầu hoặc nhận **giá trị tuyệt đối chính xác**, hoặc phải được báo lỗi nếu không thể biểu diễn kết quả.

## 2. Tại sao số nguyên nhỏ nhất lại đặc biệt?

Java dùng biểu diễn số nguyên có dấu **two's complement (bù hai)**:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất | Giá trị tuyệt đối của MIN_VALUE |
| --- | ---: | ---: | ---: |
| `int`, 32 bit | `-2147483648` | `2147483647` | `2147483648` — vượt `int` |
| `long`, 64 bit | `-9223372036854775808` | `9223372036854775807` | `9223372036854775808` — vượt `long` |

Miền âm có nhiều hơn miền dương một giá trị. Do đó:

~~~text
Integer.MIN_VALUE = -2^31
Integer.MAX_VALUE =  2^31 - 1

Long.MIN_VALUE    = -2^63
Long.MAX_VALUE    =  2^63 - 1
~~~

Chẳng hạn, `|-2147483648| = 2147483648` nhưng kiểu `int` chỉ giữ tới `2147483647`. Khi dùng phép toán số nguyên thông thường, kết quả có thể bị **overflow** và quay về giá trị âm. `absExact` báo lỗi thay vì trả về một kết quả có vẻ hợp lệ nhưng sai ý nghĩa toán học.

## 3. So sánh `Math.abs` và `Math.absExact`

Hai hàm có kết quả giống nhau đối với mọi `int` và `long` **trừ giá trị nhỏ nhất của từng kiểu**.

| Đầu vào | `Math.abs` | `Math.absExact` |
| --- | --- | --- |
| `23` (`int`) | `23` | `23` |
| `-23` (`int`) | `23` | `23` |
| `0` (`int`) | `0` | `0` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE` | `-2147483648` (vẫn âm) | Ném `ArithmeticException` |
| `-23L` (`long`) | `23L` | `23L` |
| `Long.MAX_VALUE` | `9223372036854775807L` | Cùng giá trị |
| `Long.MIN_VALUE` | `-9223372036854775808L` (vẫn âm) | Ném `ArithmeticException` |

Ví dụ:

~~~java
int n = Integer.MIN_VALUE;

System.out.println(Math.abs(n));      // -2147483648
// Math.absExact(n);                   // Ném ArithmeticException
~~~

Vì `Math.abs(Integer.MIN_VALUE)` vẫn âm, không nên mặc định biểu thức `Math.abs(n) >= 0` luôn đúng với `int` hoặc `long`. Trong các thuật toán cần chỉ số, khoảng cách, hạn mức hoặc số lượng không âm, giả định sai này có thể làm phát sinh lỗi tiếp theo.

**Khi nào chọn phương thức nào?**

- Chọn `Math.absExact` nếu kiểu kết quả vẫn phải là `int`/`long` và tràn số cần được phát hiện rõ ràng.
- Chọn `Math.abs` khi đã chứng minh đầu vào không thể là `MIN_VALUE`, hoặc trường hợp đó đã được xử lý theo quy tắc riêng.
- Nếu giá trị tuyệt đối toán học của `MIN_VALUE` cũng phải được tính thành công, cần **kiểu có miền rộng hơn**, được trình bày ở mục 5.

## 4. Cú pháp, overload và cách bắt lỗi

### 4.1. `int`: overload trả về `int`

~~~java
int a = -15;
int magnitude = Math.absExact(a); // 15
~~~

Trong trường hợp `int` nhỏ nhất, phương thức phát sinh **unchecked exception**:

~~~java
try {
    int magnitude = Math.absExact(Integer.MIN_VALUE);
    System.out.println(magnitude);
} catch (ArithmeticException ex) {
    System.out.println("Không thể biểu diễn độ lớn bằng int");
}
~~~

Kết quả:

~~~text
Không thể biểu diễn độ lớn bằng int
~~~

### 4.2. `long`: overload trả về `long`

~~~java
long a = -15L;
long magnitude = Math.absExact(a); // 15L
~~~

Với `Long.MIN_VALUE`, cũng ném `ArithmeticException`. Hậu tố `L` giúp mã nguồn cho thấy rõ literal thuộc kiểu `long`; cũng có thể dùng biến `long` hoặc chuyển kiểu có chủ đích.

### 4.3. Những khác biệt dễ nhầm

- Hai overload nguyên thủy ở đây chỉ nhận `int` và `long`. Không có `Math.absExact(float)` hoặc `Math.absExact(double)`; các kiểu dấu phẩy động dùng `Math.abs(float/double)` theo ngữ nghĩa riêng.
- Với biểu thức kiểu `byte` hoặc `short`, Java có thể **nâng kiểu lên `int`** để gọi overload `absExact(int)`. Chẳng hạn `Math.absExact((byte) -128)` trả về `int` có giá trị `128`: giá trị nhỏ nhất của `byte` không phải `Integer.MIN_VALUE`.
- Không cần khai báo `throws ArithmeticException` trên phương thức gọi vì `ArithmeticException` là unchecked. Tuy nhiên, nên có xử lý lỗi ở ranh giới nghiệp vụ khi lỗi tràn số có thể xảy ra từ dữ liệu nhập.
- Tránh dựa vào nguyên văn `ex.getMessage()` vì thông điệp có thể khác nhau giữa các cài đặt. Kiểm tra **kiểu exception** và hành vi mong đợi là chắc chắn hơn.

## 5. Khi cần độ lớn thực sự của `MIN_VALUE`

`absExact` cố ý ném lỗi vì không thể trả kết quả dương trong cùng kiểu. Nếu ứng dụng thực sự cần con số đó, phải chọn cách biểu diễn phù hợp.

### 5.1. Đầu vào `int`: nâng lên `long` **trước khi** lấy trị tuyệt đối

~~~java
int value = Integer.MIN_VALUE;
long magnitude = Math.abs((long) value);

System.out.println(magnitude); // 2147483648
~~~

Lý do: `long` biểu diễn được mọi giá trị `int` và cả độ lớn `2147483648`. Chuyển sang `long` **trước** khi gọi `Math.abs`. Viết ngược `(long) Math.abs(value)` là sai trong trường hợp này: phép `abs` đã bị tràn ở `int`, việc chuyển kiểu sau đó không sửa được.

Có thể viết `Math.absExact((long) value)` cũng được vì giá trị `Integer.MIN_VALUE` nằm trong miền an toàn của `long`; điểm quan trọng vẫn là **nâng kiểu trước phép toán**.

### 5.2. Đầu vào `long`: dùng `BigInteger` khi cần độ lớn đầy đủ

~~~java
long value = Long.MIN_VALUE;
java.math.BigInteger magnitude =
        java.math.BigInteger.valueOf(value).abs();

System.out.println(magnitude); // 9223372036854775808
~~~

Không có kiểu số nguyên nguyên thủy có dấu nào của Java rộng hơn `long`. `BigInteger` biểu diễn số nguyên với độ chính xác tùy ý theo bộ nhớ khả dụng, nên trả về đúng trị tuyệt đối của `Long.MIN_VALUE`.

**Không dùng** `Math.abs((double) Long.MIN_VALUE)` để thay thế nếu cần **giá trị nguyên chính xác** nói chung: `double` không biểu diễn chính xác mọi số nguyên 64 bit, nên một số đầu vào có thể bị làm tròn.

## 6. Lưu ý quan trọng: `absExact` không sửa được phép tính đã tràn trước đó

`Math.absExact(x)` chỉ kiểm tra **giá trị `x` mà nó nhận vào**. Nếu biểu thức đối số đã bị overflow, phương thức không thể khôi phục kết quả toán học ban đầu.

Ví dụ: muốn tính khoảng cách tuyệt đối giữa hai số `int`:

~~~java
int left = Integer.MAX_VALUE; //  2147483647
int right = -2;

// SAI: phép left - right được tính bằng int trước,
// overflow thành -2147483647, rồi absExact trả 2147483647.
int wrongDistance = Math.absExact(left - right);

// ĐÚNG: nâng hai toán hạng lên long trước phép trừ.
long correctDistance = Math.abs((long) left - right);
// 2147483649
~~~

Giá trị toán học `2147483647 - (-2) = 2147483649` không nằm trong `int`. `left - right` tràn thành `-2147483647`; `absExact` thấy đây là một `int` hợp lệ khác `Integer.MIN_VALUE`, nên không thể tự biết phép trừ trước đó sai.

Nếu ứng dụng **bắt buộc trả `int`**, nên kiểm soát cả phép trừ:

~~~java
try {
    int distance = Math.absExact(Math.subtractExact(left, right));
    System.out.println(distance);
} catch (ArithmeticException ex) {
    System.out.println("Khoảng cách vượt miền int");
}
~~~

`Math.subtractExact(left, right)` báo lỗi ngay khi phép trừ không biểu diễn được trong `int`. `Math.absExact` tiếp tục kiểm tra trường hợp giá trị tuyệt đối không biểu diễn được nếu phép trừ thành công. Với ví dụ đang xét, lỗi xảy ra ở **`subtractExact`**.

**Nguyên tắc cho công thức nhiều bước:** một hàm `Exact` bảo đảm bước mà nó thực hiện, chứ không thể bảo đảm những phép toán số nguyên thông thường đã thực hiện trước nó. Với các đầu vào `long` có thể tạo hiệu số vượt miền `long`, cân nhắc `BigInteger.valueOf(a).subtract(BigInteger.valueOf(b)).abs()` để tính độ lớn toán học đầy đủ.

## 7. Chương trình Java 17+ hoàn chỉnh — kết quả kiểm chứng

Lưu chương trình dưới tên chính xác **`AbsExactDemo.java`**. Các `try/catch` chỉ dùng để quan sát tình huống tràn số; những trường hợp hợp lệ vẫn chạy bình thường.

~~~java
import java.math.BigInteger;

public class AbsExactDemo {
    public static void main(String[] args) {
        System.out.println("intPositive=" + Math.absExact(23));
        System.out.println("intNegative=" + Math.absExact(-23));
        System.out.println("intZero=" + Math.absExact(0));
        System.out.println("intMax=" + Math.absExact(Integer.MAX_VALUE));
        System.out.println("longNegative=" + Math.absExact(-23L));
        System.out.println("longMax=" + Math.absExact(Long.MAX_VALUE));

        System.out.println("absIntMin=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("absLongMin=" + Math.abs(Long.MIN_VALUE));

        try {
            Math.absExact(Integer.MIN_VALUE);
            System.out.println("intMin=unexpected");
        } catch (ArithmeticException expected) {
            System.out.println("intMin=ArithmeticException");
        }

        try {
            Math.absExact(Long.MIN_VALUE);
            System.out.println("longMin=unexpected");
        } catch (ArithmeticException expected) {
            System.out.println("longMin=ArithmeticException");
        }

        long intMinMagnitude = Math.abs((long) Integer.MIN_VALUE);
        BigInteger longMinMagnitude = BigInteger.valueOf(Long.MIN_VALUE).abs();
        System.out.println("intMinMagnitude=" + intMinMagnitude);
        System.out.println("longMinMagnitude=" + longMinMagnitude);

        int left = Integer.MAX_VALUE;
        int right = -2;
        int wrongDistance = Math.absExact(left - right);
        long correctDistance = Math.abs((long) left - right);
        System.out.println("wrongDistance=" + wrongDistance);
        System.out.println("correctDistance=" + correctDistance);

        try {
            Math.subtractExact(left, right);
            System.out.println("subtractExact=unexpected");
        } catch (ArithmeticException expected) {
            System.out.println("subtractExact=ArithmeticException");
        }

        System.out.println("checks=" + (
                Math.absExact(-23) == 23
                && Math.absExact(-23L) == 23L
                && intMinMagnitude == 2_147_483_648L
                && longMinMagnitude.equals(new BigInteger("9223372036854775808"))
                && wrongDistance == 2_147_483_647
                && correctDistance == 2_147_483_649L));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AbsExactDemo.java
java AbsExactDemo
~~~

`Math.absExact` đã có từ Java 15; ví dụ được biên dịch thành công cả với `--release 15` và `--release 17` trên JDK 24. Đầu ra **chính xác** là:

~~~text
intPositive=23
intNegative=23
intZero=0
intMax=2147483647
longNegative=23
longMax=9223372036854775807
absIntMin=-2147483648
absLongMin=-9223372036854775808
intMin=ArithmeticException
longMin=ArithmeticException
intMinMagnitude=2147483648
longMinMagnitude=9223372036854775808
wrongDistance=2147483647
correctDistance=2147483649
subtractExact=ArithmeticException
checks=true
~~~

Chú ý `wrongDistance` minh họa **kết quả sai nhưng không ném exception**: phép trừ đã overflow trước lời gọi `absExact`. `checks=true` xác minh các giá trị quan trọng đã được trình bày, kể cả kết quả sai có chủ đích để đối chiếu.

## 8. Áp dụng an toàn và lỗi phổ biến

1. **Giả định `Math.abs(n)` luôn không âm:** sai đúng tại `Integer.MIN_VALUE` và `Long.MIN_VALUE`. Khi kết quả âm là không hợp lệ, có thể dùng `Math.absExact` để phát hiện thay vì lặng lẽ giữ số âm.
2. **Chuyển kiểu sau khi tính:** `(long) Math.abs(Integer.MIN_VALUE)` vẫn là số âm. Hãy chuyển trước: `Math.abs((long) value)`.
3. **Tin `absExact` bảo vệ toàn bộ công thức:** `Math.absExact(a - b)` vẫn có thể cho kết quả sai nếu phép trừ `a - b` đã overflow. Dùng `Math.subtractExact` khi muốn phát hiện lỗi theo kiểu gốc, hoặc nâng kiểu trước để tính kết quả lớn hơn.
4. **Lấy `Long.MIN_VALUE` rồi lưu độ lớn lại vào `long`:** không thể biểu diễn đúng số `9223372036854775808` bằng `long` có dấu. Dùng `BigInteger` nếu bắt buộc cần giá trị đó.
5. **Bắt exception rồi tự động thay bằng số 0:** điều này có thể che giấu lỗi nghiệp vụ. Quyết định thông báo lỗi, từ chối dữ liệu hay dùng kiểu lớn hơn phải dựa trên ý nghĩa dữ liệu.
6. **Nhầm `absExact` với `Math.abs` cho số thực:** `Math.absExact` chỉ có overload `int` và `long`. `float` và `double` có những vấn đề riêng như `NaN`, vô cực, và âm zero.
7. **Bỏ qua biên số nhỏ nhất trong kiểm thử:** nên có bộ thử với `0`, `-1`, `1`, `MIN_VALUE + 1`, `MIN_VALUE`, `MAX_VALUE`, cùng các biểu thức trung gian có thể overflow.

### Quy tắc tự kiểm tra

Với một số `long n` lấy từ dữ liệu bên ngoài, nếu cần `|n|` **phải nằm trong `long`**, hãy gọi `Math.absExact(n)` và có chiến lược xử lý `ArithmeticException`. Nếu cần luôn trả về đúng độ lớn kể cả `Long.MIN_VALUE`, hãy dùng `BigInteger.valueOf(n).abs()`.

## Tài liệu chính thức

- Oracle Java SE 26 API, `Math.absExact(int)` và `Math.absExact(long)` (ghi `Since: 15`): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html
- Oracle Java SE 26 API, `BigInteger.abs()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html
- Java Language Specification, `4.2.1 Integral Types and Values`: https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.1