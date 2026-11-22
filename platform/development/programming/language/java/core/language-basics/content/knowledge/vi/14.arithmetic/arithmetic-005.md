# Chia số nguyên cho không gây ArithmeticException — Java 17+

## 1. Hiện tượng cần hiểu

Trong Java, **phép chia số nguyên bằng toán tử `/` với số chia bằng 0** ném `java.lang.ArithmeticException` khi biểu thức được đánh giá.

~~~java
int numerator = 10;
int denominator = 0;

// int result = numerator / denominator;
// Nếu chạy: ArithmeticException vì phép chia số nguyên cho 0.
~~~

Đây là **lỗi lúc chạy (runtime exception)**, không phải kết quả nguyên đặc biệt như `Infinity`. Không có giá trị `int` hay `long` nào đại diện cho thương của một phép chia nguyên cho 0.

Một ví dụ xử lý có kiểm soát:

~~~java
int numerator = 10;
int denominator = 0;

try {
    int quotient = numerator / denominator;
    System.out.println(quotient);
} catch (ArithmeticException ex) {
    System.out.println("Cannot divide integers by zero");
}
~~~

**Expected output:**

~~~text
Cannot divide integers by zero
~~~

**Kết luận chính:** phải **bảo đảm số chia khác 0 trước khi chia**, hoặc có hợp đồng xử lý lỗi rõ ràng. `try/catch` có thể xử lý ngoại lệ nhưng **không biến phép chia cho 0 thành phép tính hợp lệ**.

## 2. Kiểu số nguyên nào chịu quy tắc này?

Trong Java 17+, phép chia dùng kiểu toán hạng sau các quy tắc *binary numeric promotion*. Với các kiểu số nguyên, khi số chia bằng 0, phép `/` và `%` đều ném `ArithmeticException`.

| Trường hợp | Kiểu biểu thức | Số chia bằng 0 | Kết quả |
|---|---|---|---|
| `int / int` | `int` | `10 / 0` | `ArithmeticException` |
| `long / long` | `long` | `10L / 0L` | `ArithmeticException` |
| `byte / byte` | `int` | Hai `byte`, mẫu bằng 0 | `ArithmeticException` |
| `short / short` | `int` | Hai `short`, mẫu bằng 0 | `ArithmeticException` |
| `char / int` | `int` | Mẫu `int` bằng 0 | `ArithmeticException` |
| `int % int` | `int` | `10 % 0` | `ArithmeticException` |
| `long % long` | `long` | `10L % 0L` | `ArithmeticException` |

Ví dụ hợp lệ khi mẫu khác 0:

~~~java
byte a = 9;
byte b = 2;

int quotient = a / b; // byte được nâng thành int khi chia
int remainder = a % b;

System.out.println(quotient);  // 4
System.out.println(remainder); // 1
~~~

**Đừng lẫn nguyên nhân:** nếu compiler từ chối `byte result = a / b;`, đó là vấn đề **chuyển kiểu int về byte**. Nếu biểu thức `a / b` chạy với `b == 0`, đó mới là vấn đề **chia nguyên cho 0**.

## 3. Phép dư `%` cũng không chấp nhận số chia 0

Nhiều người chỉ kiểm tra toán tử `/` mà bỏ qua `%`:

~~~java
int count = 10;
int groupSize = 0;

// int quotient = count / groupSize;  // Ném ArithmeticException
// int remainder = count % groupSize; // Cũng ném ArithmeticException
~~~

Với mẫu số khác 0, hai phép toán liên quan nhau qua quy tắc thương và dư của Java. Ví dụ:

~~~java
System.out.println(10 / 3); // 3
System.out.println(10 % 3); // 1
~~~

Tuy nhiên, cả thương lẫn dư đều **không được định nghĩa là giá trị số nguyên bình thường khi mẫu bằng 0**.

Một hệ thống chia dữ liệu theo batch có thể cần đồng thời `items / batchSize` và `items % batchSize`. Hãy **validate `batchSize > 0` một lần ở ranh giới** trước cả hai phép toán; không đợi ngoại lệ xảy ra giữa chừng sau khi đã cập nhật trạng thái khác.

## 4. Khác hoàn toàn với phép chia dấu phẩy động

Nếu ít nhất một toán hạng là `float` hoặc `double`, phép chia sử dụng số học dấu phẩy động. Chia cho zero trong floating-point có thể trả **Infinity**, **-Infinity** hoặc **NaN**, không ném `ArithmeticException` chỉ vì mẫu bằng 0.

~~~java
System.out.println(10.0 / 0.0);  // Infinity
System.out.println(-10.0 / 0.0); // -Infinity
System.out.println(0.0 / 0.0);   // NaN
~~~

So sánh:

| Biểu thức | Quy tắc | Kết quả |
|---|---|---|
| `10 / 2` | Chia nguyên | `5` |
| `10 / 0` | Chia nguyên | `ArithmeticException` |
| `10L / 0L` | Chia `long` | `ArithmeticException` |
| `10.0 / 2.0` | Chia `double` | `5.0` |
| `10.0 / 0.0` | Chia `double` | `Infinity` |
| `-10.0 / 0.0` | Chia `double` | `-Infinity` |
| `0.0 / 0.0` | Chia `double` | `NaN` |

**Không “sửa” lỗi chia nguyên cho 0 bằng cách ép sang `double` một cách máy móc.** Một giá trị Infinity hoặc NaN có thể khiến kết quả downstream sai nghiêm trọng nếu nghiệp vụ yêu cầu giá trị hữu hạn.

Nếu kết quả cần hữu hạn, kiểm tra mẫu đầu vào và sau phép tính xem xét `Double.isFinite(result)` theo hợp đồng ứng dụng.

## 5. Kiểm tra mẫu số trước khi thực hiện phép chia

Cách dễ đọc nhất là một **guard clause**:

~~~java
static int divideNonZero(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

Ở đây `IllegalArgumentException` là một **quyết định thiết kế API** nhằm báo đầu vào không hợp lệ. Nếu bỏ kiểm tra và thực hiện phép chia, Java sẽ tự ném `ArithmeticException`.

Hai trường hợp có hợp đồng khác nhau:

- **Không hợp lệ do tham số:** chủ động ném `IllegalArgumentException`, giúp người gọi biết dữ liệu đầu vào đã bị từ chối.
- **Phép toán gặp điều kiện số học bất hợp lệ:** để `ArithmeticException` phát sinh, hoặc bắt ngoại lệ nếu có chính sách phục hồi.

Điều quan trọng là **nhất quán** và mô tả cho caller biết cần xử lý gì.

### Ví dụ không cần exception: chỉ thực hiện khi hợp lệ

~~~java
int numerator = 10;
int denominator = 0;

if (denominator != 0) {
    int quotient = numerator / denominator;
    System.out.println(quotient);
} else {
    System.out.println("No valid quotient");
}
~~~

**Expected output:**

~~~text
No valid quotient
~~~

Không có “thương mặc định” nào mà ngôn ngữ tự quyết giúp bạn. Nếu ứng dụng muốn trả giá trị dự phòng, phải **định nghĩa rõ** khi nào được dùng dự phòng và phân biệt nó với kết quả tính toán thật.

## 6. Không lấy `0` làm thương dự phòng nếu 0 là dữ liệu hợp lệ

Một API như sau dễ gây sai nghiệp vụ:

~~~java
static int unsafeFallback(int a, int b) {
    return b == 0 ? 0 : a / b;
}
~~~

Với `1 / 2`, thương nguyên **thật sự** cũng bằng 0. Vì vậy caller không thể phân biệt:

- `0` do kết quả phép chia hợp lệ `1 / 2`;
- `0` do phép chia bất hợp lệ `1 / 0` bị âm thầm thay thế.

Nếu việc không có thương là tình huống bình thường, có thể dùng `OptionalInt`:

~~~java
static java.util.OptionalInt tryDivide(int a, int b) {
    return b == 0
            ? java.util.OptionalInt.empty()
            : java.util.OptionalInt.of(a / b);
}
~~~

Cách sử dụng:

~~~java
System.out.println(tryDivide(1, 2).orElse(-1)); // 0
System.out.println(tryDivide(1, 0).isEmpty());  // true
~~~

`OptionalInt.empty()` diễn đạt **không có kết quả**, khác `OptionalInt.of(0)` biểu diễn thương bằng 0 hợp lệ.

**Lưu ý:** hàm `tryDivide` trên xử lý mẫu số 0, nhưng chưa yêu cầu phát hiện trường hợp tràn thương `Integer.MIN_VALUE / -1`. Nếu nghiệp vụ cần kết quả toán học chính xác trong miền int, thêm kiểm tra như phần dưới.

## 7. Tràn thương khác với chia cho 0

Trường hợp `Integer.MIN_VALUE / -1` trả `-2147483648` mà **không ném exception**, dù thương toán học là `2147483648` nằm ngoài miền `int`. Một guard chỉ kiểm tra `b == 0` **không bảo đảm** thương luôn chính xác.

~~~java
static int divideExactInt(int a, int b) {
    if (b == 0) throw new IllegalArgumentException("zero denominator");
    if (a == Integer.MIN_VALUE && b == -1)
        throw new ArithmeticException("int quotient overflow");
    return a / b;
}
~~~

Đây là chính sách nghiệp vụ tách **mẫu số không hợp lệ** và **thương vượt miền**. Bài tràn số xử lý tổng quát `Math.*Exact` và `BigInteger`; bài này tập trung vào hợp đồng lỗi khi chia.

## 8. `Math.floorDiv`, `Math.floorMod` cũng cần mẫu khác 0

Java có các phương thức:

~~~java
System.out.println(Math.floorDiv(-7, 2)); // -4
System.out.println(Math.floorMod(-7, 2)); // 1
~~~

Chúng khác `/` và `%` ở quy tắc thương/dư khi có số âm. Tuy nhiên, **không phương thức nào cho phép chia số nguyên cho 0**:

~~~java
int divisor = 0;
// Math.floorDiv(7, divisor); // ArithmeticException
// Math.floorMod(7, divisor); // ArithmeticException
~~~

`Math.floorDiv` không phải “phiên bản an toàn với zero” của `/`. Nếu dùng `floorDiv` cho xử lý timestamp, chia ô lưới hoặc chỉ số nhóm, vẫn phải validate mẫu đầu vào.

## 9. Short-circuit bảo vệ một biểu thức chia nguyên

Toán tử logic `&&` chỉ đánh giá vế phải nếu vế trái là `true`. Ta có thể tận dụng điều đó:

~~~java
int denominator = 0;
boolean largeQuotient = (denominator != 0)
        && (10 / denominator > 3);

System.out.println(largeQuotient); // false, không thực hiện phép chia
~~~

Vế trái false làm Java **bỏ qua** biểu thức `10 / denominator > 3`, nhờ vậy không có chia cho 0.

Tương tự, `||` có thể bỏ qua vế phải khi vế trái `true`:

~~~java
boolean invalidOrLarge = (denominator == 0)
        || (10 / denominator > 3);

System.out.println(invalidOrLarge); // true, không thực hiện phép chia
~~~

**Không nhầm `&&` với `&`, `||` với `|` trên boolean:** các toán tử `&` và `|` **đánh giá cả hai toán hạng**. Đổi `&&` thành `&` trong ví dụ guard có thể khiến phép chia bị thực hiện và ném lỗi.

Nếu logic quan trọng hoặc có nhiều thao tác, tách `if` rõ ràng thường dễ đọc hơn một biểu thức boolean lồng nhau.

## 10. Wrapper `Integer` có thể ném lỗi khác trước khi chia

Java cho phép dùng wrapper nhờ *auto-unboxing*:

~~~java
Integer boxedNumerator = 10;
Integer boxedDenominator = 2;

System.out.println(boxedNumerator / boxedDenominator); // 5
~~~

Nhưng nếu mẫu là `null`:

~~~java
Integer boxedDenominator = null;
// int value = 10 / boxedDenominator;
// Runtime: NullPointerException khi unbox null.
~~~

Đây là **`NullPointerException`**, không phải `ArithmeticException`. Do đó cần phân biệt:

| Dữ liệu mẫu | Khi tính `10 / boxedDenominator` |
|---|---|
| `Integer.valueOf(2)` | Trả `5` |
| `Integer.valueOf(0)` | Unbox thành 0 rồi ném `ArithmeticException` |
| `null` | Ném `NullPointerException` lúc unboxing |

Một chính sách nhập liệu đơn giản:

~~~java
static int divideNullable(int numerator, Integer denominator) {
    if (denominator == null) {
        throw new IllegalArgumentException("denominator is missing");
    }
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

Sau các guard, compiler vẫn tự unbox wrapper khi cần chia. Nhưng bạn đã phân biệt rõ **thiếu dữ liệu** và **giá trị 0**.

## 11. Khi exception xảy ra, tác dụng phụ trước đó không tự rollback

Java đánh giá các phần của biểu thức theo thứ tự được ngôn ngữ quy định. Một phép chia cho 0 có thể làm việc xử lý **dừng giữa chừng**:

~~~java
int count = 0;
int denominator = 0;

try {
    int value = (++count) / denominator;
    System.out.println(value);
} catch (ArithmeticException ex) {
    System.out.println("counter after failure=" + count);
}
~~~

**Expected output:**

~~~text
counter after failure=1
~~~

`++count` đã tăng bộ đếm trước khi phép chia gặp mẫu 0. `catch` **không khôi phục** `count` về 0.

Với dữ liệu quan trọng, hãy **validate tất cả đầu vào liên quan trước khi thực hiện thay đổi trạng thái**, hoặc dùng cơ chế giao dịch/rollback thích hợp. `try/catch` chỉ điều khiển luồng xử lý ngoại lệ, không tự biến một nhóm thao tác thành *atomic transaction*.

## 12. Chọn xử lý: kiểm tra trước, ném ngoại lệ hay trả trạng thái?

| Yêu cầu nghiệp vụ | Cách thường phù hợp |
|---|---|
| Mẫu số luôn bắt buộc khác 0 | Kiểm tra `b != 0` ở ranh giới; reject đầu vào sai |
| Đây là lỗi lập trình, không có đường phục hồi | Cho exception lan lên tầng có trách nhiệm xử lý |
| Người dùng nhập mẫu có thể sai | Validate, hiển thị lỗi có nghĩa và cho nhập lại |
| “Không có kết quả” là trạng thái hợp lệ | `OptionalInt` hoặc kiểu kết quả có trạng thái |
| Chỉ cần phép chia nguyên theo Java | `a / b`, sau khi bảo đảm `b != 0` |
| Cần thương int không được overflow | Kiểm tra thêm `a == MIN_VALUE && b == -1` |
| Muốn chia số thực | Chọn toán hạng `double`/`float`; vẫn kiểm tra tính hữu hạn khi cần |
| Muốn chia với quy tắc floor | `Math.floorDiv` và validate mẫu khác 0 |

**Không nên nuốt exception rồi âm thầm trả 0** trừ khi ứng dụng có một chính sách dự phòng rõ ràng, được tài liệu hóa và kiểm thử.

## 13. Chương trình Java 17 hoàn chỉnh — runnable

Lưu tệp đúng tên **`IntegerDivideByZeroDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.OptionalInt;

public final class IntegerDivideByZeroDemo {
    private IntegerDivideByZeroDemo() {}

    static int divideNonZero(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return a / b;
    }

    static int divideExactInt(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("zero denominator");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("int quotient overflow");
        }
        return a / b;
    }

    static OptionalInt tryDivide(int a, int b) {
        return b == 0 ? OptionalInt.empty() : OptionalInt.of(a / b);
    }

    static int divideNullable(int a, Integer b) {
        if (b == null) {
            throw new IllegalArgumentException("denominator is missing");
        }
        if (b == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return a / b;
    }

    public static void main(String[] args) {
        System.out.println("valid quotient=" + (10 / 3));
        System.out.println("valid remainder=" + (10 % 3));
        System.out.println("long quotient=" + (10L / 2L));

        byte small = 9;
        byte two = 2;
        System.out.println("byte division=" + (small / two));

        int zero = 0;
        try {
            int result = 10 / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("int / zero=ArithmeticException");
        }

        try {
            int result = 10 % zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("int % zero=ArithmeticException");
        }

        try {
            long result = 10L / (long) zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("long / zero=ArithmeticException");
        }

        try {
            System.out.println(Math.floorDiv(10, zero));
        } catch (ArithmeticException ex) {
            System.out.println("floorDiv zero=ArithmeticException");
        }

        System.out.println("floating positive=" + (10.0 / 0.0));
        System.out.println("floating negative=" + (-10.0 / 0.0));
        System.out.println("floating undefined=" + (0.0 / 0.0));

        System.out.println("guarded normal=" + divideNonZero(10, 2));
        try {
            divideNonZero(10, zero);
        } catch (IllegalArgumentException ex) {
            System.out.println("guarded invalid=" + ex.getMessage());
        }

        System.out.println("optional valid zero="
                + tryDivide(1, 2).orElse(-1));
        System.out.println("optional no result=" + tryDivide(1, 0).isEmpty());

        boolean safeAnd = (zero != 0) && (10 / zero > 2);
        boolean safeOr = (zero == 0) || (10 / zero > 2);
        System.out.println("short circuit and=" + safeAnd);
        System.out.println("short circuit or=" + safeOr);

        Integer boxedZero = Integer.valueOf(0);
        Integer missing = null;
        try {
            int result = 10 / boxedZero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("boxed zero=ArithmeticException");
        }
        try {
            int result = 10 / missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("boxed null=NullPointerException");
        }
        try {
            divideNullable(10, missing);
        } catch (IllegalArgumentException ex) {
            System.out.println("nullable rejected=" + ex.getMessage());
        }

        System.out.println("min / -1=" + (Integer.MIN_VALUE / -1));
        System.out.println("min widened="
                + (((long) Integer.MIN_VALUE) / -1));
        try {
            divideExactInt(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow=" + ex.getMessage());
        }
        BigInteger exact = BigInteger.valueOf(Long.MIN_VALUE)
                .divide(BigInteger.valueOf(-1));
        System.out.println("big exact=" + exact);

        int count = 0;
        try {
            int result = (++count) / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("counter after failure=" + count);
        }
    }
}
~~~

**Yêu cầu:** JDK 17+; terminal mở tại thư mục chứa file. Không cần Maven/Gradle hoặc thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerDivideByZeroDemo.java
java -cp . IntegerDivideByZeroDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerDivideByZeroDemo.java
java -cp . IntegerDivideByZeroDemo
~~~

**Exact expected output:**

~~~text
valid quotient=3
valid remainder=1
long quotient=5
byte division=4
int / zero=ArithmeticException
int % zero=ArithmeticException
long / zero=ArithmeticException
floorDiv zero=ArithmeticException
floating positive=Infinity
floating negative=-Infinity
floating undefined=NaN
guarded normal=5
guarded invalid=denominator must not be zero
optional valid zero=0
optional no result=true
short circuit and=false
short circuit or=true
boxed zero=ArithmeticException
boxed null=NullPointerException
nullable rejected=denominator is missing
min / -1=-2147483648
min widened=2147483648
checked overflow=int quotient overflow
big exact=9223372036854775808
counter after failure=1
~~~

### Giải thích kết quả chính

1. `10 / 3` và `10 % 3` bình thường vì mẫu bằng 3, kết quả là thương 3 và dư 1.
2. `byte` được nâng lên `int` khi chia; `9 / 2` cho 4.
3. Cả `int / zero`, `int % zero`, `long / zero` và `Math.floorDiv` đều phát sinh `ArithmeticException`.
4. `double` chia cho 0 trả Infinity/-Infinity/NaN; đó là ngữ nghĩa **khác kiểu nguyên**.
5. Guard chủ động ném `IllegalArgumentException` với thông báo xác định.
6. `OptionalInt` tách được thương nguyên hợp lệ bằng 0 khỏi trường hợp không có thương.
7. `&&` và `||` tránh đánh giá phép chia nhờ short-circuit.
8. Wrapper `Integer.valueOf(0)` gây lỗi chia cho 0; wrapper `null` gây lỗi unboxing trước khi chia.
9. `MIN_VALUE / -1` là trường hợp **tràn không tự ném lỗi**; dùng kiểm tra riêng hoặc kiểu đủ rộng.
10. Bộ đếm tăng trước khi phép chia thất bại; `catch` không rollback tác dụng phụ trước đó.

## 14. Các lỗi thường gặp

| Ngộ nhận / lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| `10 / 0` trả Infinity | Đó là quy tắc của floating-point, không phải integer | Kiểm tra mẫu khác 0 |
| `10 % 0` vẫn hợp lệ | Phép dư nguyên cũng không cho mẫu 0 | Validate trước cả `/` và `%` |
| `long a = 10L / 0L` an toàn vì `long` rộng | Rộng hơn không cho phép chia 0 | Cùng quy tắc ngoại lệ |
| `Math.floorDiv(10, 0)` an toàn | `floorDiv` không hỗ trợ mẫu 0 | Kiểm tra đầu vào |
| `10.0 / 0.0` là cách sửa chia nguyên | Kết quả Infinity có thể sai nghiệp vụ | Chỉ dùng floating-point khi đúng mô hình |
| `int result = 10 / boxed;` với boxed null | Unboxing null gây `NullPointerException` | Kiểm tra null riêng |
| Bắt mọi `RuntimeException` rồi trả 0 | Che cả lỗi khác, không phân biệt trường hợp | Bắt đúng loại hoặc validate |
| Dùng 0 để đại diện cả thương 0 và phép chia lỗi | Làm mất trạng thái “không có kết quả” | `OptionalInt`/error model rõ |
| Dùng `&&` như `&` | `&` đánh giá cả hai vế | Dùng `&&` khi cần guard |
| Cho rằng không exception luôn có thương chính xác | `MIN_VALUE/-1` tràn đặc biệt | Kiểm tra overflow |
| Bắt exception sẽ hoàn tác mọi side effect | `catch` không rollback | Validate trước hoặc giao dịch/rollback |
| Chia theo số lượng batch mà không kiểm tra `batchSize` | Batch size 0 sẽ gây lỗi | Yêu cầu `batchSize > 0` |

## 15. Bài tập và đáp án

### Bài A — hai toán tử cùng lỗi khi mẫu 0

~~~java
int numerator = 8;
int denominator = 0;
// System.out.println(numerator / denominator);
// System.out.println(numerator % denominator);
~~~

**Đáp án:** nếu chạy từng dòng, cả phép chia nguyên và phép dư nguyên đều ném `ArithmeticException`. Thực hiện `denominator != 0` trước.

### Bài B — cách bảo vệ bằng logic

~~~java
int b = 0;
boolean condition = (b != 0) && (12 / b > 2);
System.out.println(condition);
~~~

**Đáp án:** `false`; Java không đánh giá vế phải của `&&` vì vế trái false.

### Bài C — có nên tự trả 0?

Giả sử API trả kết quả `int` bằng 0 nếu mẫu bằng 0. Vì sao nguy hiểm?

**Đáp án:** `1 / 2` cũng có thương hợp lệ bằng 0. Caller không phân biệt được kết quả đúng và lỗi. Có thể reject input bằng exception hoặc trả kiểu có trạng thái như `OptionalInt`.

### Bài D — wrapper nullable

~~~java
Integer b = null;
// int result = 12 / b;
~~~

**Đáp án:** nếu chạy, có `NullPointerException` do auto-unboxing `null`, không phải `ArithmeticException` chia cho 0.

### Bài E — int overflow

~~~java
System.out.println(Integer.MIN_VALUE / -1);
~~~

**Đáp án:** `-2147483648`, **không** ném lỗi. Nếu không chấp nhận tràn, kiểm tra trường hợp này và dùng kiểu đủ rộng khi cần.

### Bài F — phân biệt floating-point

~~~java
System.out.println(5.0 / 0.0);
System.out.println(0.0 / 0.0);
~~~

**Đáp án:**

~~~text
Infinity
NaN
~~~

Chúng không phải những giá trị nguyên hợp lệ.

## 16. Checklist kết thúc

- [ ] Biết `int` và `long` chia cho 0 ném `ArithmeticException`.
- [ ] Biết `%` với mẫu 0 cũng ném `ArithmeticException`.
- [ ] Hiểu `byte`, `short`, `char` thường được nâng lên `int` khi chia.
- [ ] Phân biệt chia nguyên cho 0 với floating-point trả Infinity/NaN.
- [ ] Biết dùng `if (denominator == 0)` hoặc guard clause để reject input.
- [ ] Không dùng `0` làm giá trị dự phòng mơ hồ nếu 0 là kết quả hợp lệ.
- [ ] Biết `OptionalInt` khi kết quả có thể vắng mặt là điều bình thường.
- [ ] Biết `Math.floorDiv`/`Math.floorMod` cũng không hỗ trợ mẫu 0.
- [ ] Dùng `&&`/`||` đúng cách để tránh đánh giá phép chia không hợp lệ.
- [ ] Phân biệt wrapper 0 gây `ArithmeticException` với wrapper null gây `NullPointerException`.
- [ ] Hiểu ngoại lệ tràn đặc biệt `MIN_VALUE / -1`.
- [ ] Không giả định `catch` hoàn tác tác dụng phụ đã xảy ra.
- [ ] Chạy `IntegerDivideByZeroDemo.java` trên JDK 17+ và đối chiếu exact expected output.

**Kết luận:** Trong Java 17+, **chia hoặc lấy dư số nguyên với mẫu số 0** gây `ArithmeticException` tại thời điểm đánh giá; đó không phải Infinity. Thiết kế an toàn là **kiểm tra đầu vào sớm**, phân biệt dữ liệu thiếu với zero, chọn rõ hợp đồng lỗi/không có kết quả và tránh che giấu các trường hợp bất hợp lệ bằng giá trị dự phòng mơ hồ.