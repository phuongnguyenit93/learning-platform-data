# Chia hoặc lấy dư cho 0 với số nguyên trong Java

## 1. Quy tắc cốt lõi

Với các kiểu số nguyên trong Java, **mẫu số (toán hạng bên phải) bằng `0` trong phép chia `/` hoặc phép lấy dư `%` luôn gây `ArithmeticException` khi phép toán được thực thi**. Java không đưa ra một thương hoặc số dư hợp lệ cho những biểu thức này.

```java
int a = 12;
int zero = 0;

// Hai phép tính sau đều ném ArithmeticException khi chạy:
// int quotient = a / zero;
// int remainder = a % zero;
```

Những điểm cần nhớ ngay:

- `12 / 0` **không** trả về số vô cực với số nguyên; phép tính thất bại.
- `12 % 0` **không** trả về `0` hay `12`; phép tính cũng thất bại.
- `0 / 0` và `0 % 0` **đều** gây lỗi. Tử số bằng `0` không cứu được phép toán.
- Kiểm tra **toán hạng bên phải** (`divisor == 0`), không chỉ kiểm tra tử số.
- `ArithmeticException` là **unchecked exception** (lớp con của `RuntimeException`). Không bắt buộc khai báo `throws` hoặc `catch`, nhưng chương trình phải xác định cách xử lý đầu vào có thể bằng `0`.

Đây là quy tắc đối với **integer arithmetic** của Java, bao gồm phép chia/lấy dư thực hiện theo kiểu `int` hoặc `long` sau khi áp dụng quy tắc nâng kiểu số (*numeric promotion*). Không nên suy ra kết quả cho số nguyên từ hành vi của `double`/`float`.

## 2. Tại sao phép chia và phép lấy dư cho 0 không xác định?

Với số nguyên `a` và `b != 0`, Java định nghĩa thương nguyên `q = a / b` bằng phép chia làm tròn về **0**. Số dư `r = a % b` đi cùng thương và thỏa mãn hệ thức (theo số học nguyên Java):

```text
a = b * q + r
q = a / b
r = a % b
```

Ví dụ:

```java
System.out.println(17 / 5);    // 3
System.out.println(17 % 5);    // 2
System.out.println(-17 / 5);   // -3
System.out.println(-17 % 5);   // -2
```

Ở đây `17 = 5 * 3 + 2`, còn `-17 = 5 * (-3) + (-2)`. Với `%` trên số nguyên, số dư khác `0` có cùng dấu với **tử số** (số bị chia), không nhất thiết dương.

Nếu `b = 0`, không thể xác định thương nguyên duy nhất theo ý nghĩa phép chia. Công thức `a = b * q + r` không còn cung cấp một phép chia có nghĩa thông thường; Java **chủ động từ chối cả `/` và `%` khi mẫu số bằng 0**. Vì vậy, việc tính `a % 0` không phải một cách “an toàn hơn” để xử lý `a / 0`.

Không cần ghi nhớ một thông báo lỗi văn bản cố định: ý nghĩa đáng tin cậy là **loại ngoại lệ `java.lang.ArithmeticException`**; chi tiết nội dung message do triển khai đưa ra.

## 3. Khi nào lỗi xảy ra và ảnh hưởng đến luồng chương trình ra sao?

Ngoại lệ xảy ra **khi JVM thực thi phép chia/lấy dư nguyên với mẫu số thực tế bằng 0**. Ví dụ, tham số hoặc phép tính trung gian có thể trở thành 0:

```java
static int averagePerGroup(int total, int groups) {
    return total / groups; // groups == 0 -> ArithmeticException.
}
```

Nếu ngoại lệ không được bắt ở nơi phù hợp, luồng thực thi bình thường bị ngắt và ngoại lệ được truyền lên trên chuỗi gọi. Khi không có nơi xử lý, luồng thực thi kết thúc với lỗi; ứng dụng không nhận được một giá trị “thương mặc định”.

Phép tính **không được thực thi** thì không thể phát sinh ngoại lệ do chính phép tính đó. Ví dụ:

```java
int divisor = 0;
if (divisor != 0) {
    int q = 10 / divisor; // Không được chạy trong trường hợp hiện tại.
}
```

Một điều kiện ngắn mạch giúp bảo vệ phép toán nếu đặt đúng thứ tự:

```java
int divisor = 0;
boolean valid = divisor != 0 && 100 / divisor > 5;
// valid == false; vế 100 / divisor bị bỏ qua.
```

Ở đây `&&` chỉ đánh giá vế phải khi vế trái `true`. Nếu thay bằng `&` với hai toán hạng boolean, **cả hai vế** được đánh giá và phép chia có thể ném ngoại lệ. Cũng cần tránh đảo thứ tự thành `100 / divisor > 5 && divisor != 0`: phép chia đã chạy trước khi kiểm tra mẫu số.

Các biểu thức điều kiện chỉ an toàn nếu **mẫu số được kiểm tra là đúng mẫu số dùng trong phép tính** và không thể thay đổi bất ngờ giữa lúc kiểm tra và sử dụng. Với giá trị số cục bộ, hãy chụp giá trị cần dùng vào cùng một biến nếu phép tính ban đầu đọc từ một nguồn có thể thay đổi.

## 4. Những kiểu số nguyên nào chịu quy tắc này?

Các phép toán số nguyên với `byte`, `short`, `char` và `int` thường được *numeric promotion* lên `int`; nếu có toán hạng `long` (không có số thực tham gia), phép tính diễn ra ở `long`. Cả phép chia/lấy dư kiểu `int` và `long` đều ném `ArithmeticException` nếu mẫu số bằng `0`.

```java
byte a = 12;
byte b = 0;
long big = 12L;
long longZero = 0L;

// int x = a / b;       // ArithmeticException khi thực thi (chia bằng int).
// int y = a % b;       // ArithmeticException khi thực thi (lấy dư bằng int).
// long z = big / longZero; // ArithmeticException (chia bằng long).
// long r = big % longZero; // ArithmeticException (lấy dư bằng long).
```

Toán tử ghép gán cũng không được miễn trừ:

```java
int count = 10;
int zero = 0;

// count /= zero; // ArithmeticException; count không nhận được thương hợp lệ.
// count %= zero; // ArithmeticException; không nhận được số dư hợp lệ.
```

Ngoài các toán tử, những API thực hiện phép chia/lấy dư nguyên như `Math.floorDiv(a, b)`, `Math.floorMod(a, b)`, `Integer.divideUnsigned(a, b)` và `Integer.remainderUnsigned(a, b)` cũng không chấp nhận mẫu số bằng 0. Với `BigInteger`, `divide(BigInteger.ZERO)` và `remainder(BigInteger.ZERO)` cũng ném `ArithmeticException`. **Độ rộng lớn hơn hoặc khả năng biểu diễn số nguyên rất lớn không làm cho phép chia cho 0 có nghĩa.**

Lưu ý nhỏ nhưng hữu ích: các hàm `Math.floorDiv`/`Math.floorMod` có quy tắc làm tròn và dấu khác chia nguyên thông thường đối với một số toán hạng âm, nhưng điều kiện mẫu số khác 0 **vẫn bắt buộc**.

## 5. Phân biệt phép chia cho 0 kiểu số nguyên và kiểu dấu phẩy động

Cùng ký hiệu `/` hoặc `%`, hành vi có thể khác khi biểu thức được tính bằng `double` hoặc `float`. Đối với phép toán dấu phẩy động Java theo chuẩn IEEE 754:

| Biểu thức | Kiểu phép toán | Kết quả |
| --- | --- | --- |
| `10 / 0` | Số nguyên (`int`) | `ArithmeticException` khi chạy |
| `10L / 0L` | Số nguyên (`long`) | `ArithmeticException` khi chạy |
| `10 % 0` | Lấy dư nguyên | `ArithmeticException` khi chạy |
| `0 / 0` | Số nguyên | `ArithmeticException` khi chạy |
| `10.0 / 0` | Dấu phẩy động (`double`) | `Infinity` |
| `-10.0 / 0.0` | Dấu phẩy động | `-Infinity` |
| `0.0 / 0.0` | Dấu phẩy động | `NaN` |
| `10.0 % 0` | Lấy dư dấu phẩy động | `NaN` |

Trong `10.0 / 0`, toán hạng `10.0` có kiểu `double`, nên `0` được nâng lên `double` và phép chia thuộc ngữ nghĩa số thực. Ngược lại, `10 / 0` chỉ có toán hạng nguyên nên không tự chuyển sang phép chia số thực.

```java
System.out.println(Double.isInfinite(10.0 / 0)); // true
System.out.println(Double.isNaN(0.0 / 0.0));     // true
System.out.println(Double.isNaN(10.0 % 0));      // true
```

**Không sử dụng phép chuyển sang `double` chỉ để tránh ngoại lệ** nếu bài toán yêu cầu số nguyên chính xác. `Infinity` hoặc `NaN` có thể tiếp tục lan truyền vào tính toán sau và làm kết quả sai về ý nghĩa nghiệp vụ. Nếu quy tắc là “số nhóm phải lớn hơn 0”, hãy kiểm tra quy tắc đó thay vì chuyển kiểu.

## 6. Cách xử lý đúng trong ứng dụng

### 6.1. Kiểm tra mẫu số trước khi tính

Nếu `0` là dữ liệu đầu vào **không hợp lệ**, hãy từ chối sớm bằng thông báo rõ ràng:

```java
static int dividePositiveGroups(int total, int groups) {
    if (groups <= 0) {
        throw new IllegalArgumentException("groups must be positive");
    }
    return total / groups;
}
```

Ở đây kiểm tra `<= 0` vì **quy tắc nghiệp vụ** yêu cầu số nhóm dương; riêng để phòng lỗi chia cho 0 về mặt ngôn ngữ chỉ cần `groups == 0`. Số âm là mẫu số hợp lệ trong phép chia nguyên Java, nhưng có thể không hợp lệ trong bài toán đếm nhóm.

Nếu cần tính cả thương và số dư, chỉ tính sau khi xác nhận mẫu số:

```java
static String describeDivision(int total, int groups) {
    if (groups == 0) {
        return "Không thể chia khi số nhóm bằng 0";
    }
    int quotient = total / groups;
    int remainder = total % groups;
    return "Thương=" + quotient + ", dư=" + remainder;
}
```

Giá trị trả về ở trường hợp `groups == 0` là **quyết định thiết kế của ứng dụng**, không phải kết quả số học mặc định của Java. Các hệ thống khác có thể chọn báo lỗi, yêu cầu nhập lại, hoặc dùng kiểu trả về thể hiện phép tính không có kết quả.

### 6.2. Bắt ngoại lệ tại ranh giới xử lý phù hợp

Khi mẫu số có thể đến từ dữ liệu bên ngoài hoặc một thành phần khác, có thể bắt `ArithmeticException` tại điểm ứng dụng biết cách thông báo và phục hồi:

```java
int total = 10;
int groups = 0;
try {
    int perGroup = total / groups;
    System.out.println(perGroup);
} catch (ArithmeticException ex) {
    System.out.println("Không thể chia cho 0");
}
```

Nếu có thể kiểm tra đầu vào sớm, giải pháp kiểm tra trước thường dễ đọc hơn. **Không nên bắt `ArithmeticException` quá rộng rồi bỏ qua** vì còn có những trường hợp số học khác, khiến lỗi lập trình bị che khuất. Khi không thể khôi phục hợp lệ, để ngoại lệ lan lên tầng xử lý lỗi là lựa chọn phù hợp hơn việc tự gán một giá trị giả như `0`.

### 6.3. Tránh mất an toàn do mẫu số được tính động

Mẫu số có thể phát sinh từ phép tính trung gian:

```java
int users = 8;
int activeUsers = 8;
int inactiveUsers = users - activeUsers; // 0

if (inactiveUsers != 0) {
    int average = 100 / inactiveUsers;
    System.out.println(average);
}
```

Khi nguồn dữ liệu có thể thay đổi đồng thời, lấy mẫu số một lần, kiểm tra, rồi dùng **chính giá trị đó**:

```java
int currentDivisor = getCurrentDivisor();
if (currentDivisor != 0) {
    int result = 100 / currentDivisor;
    System.out.println(result);
}
```

`getCurrentDivisor()` trong đoạn ngắn thứ hai là **hàm minh họa do ứng dụng định nghĩa**, không phải API chuẩn của Java. Nếu gọi nguồn dữ liệu thêm lần nữa trong phép chia, giá trị có thể đã đổi thành 0. Với chương trình song song, còn cần thiết kế đồng bộ khi những dữ liệu liên quan phải nhất quán theo một thao tác.

## 7. Ví dụ Java 17+ chạy độc lập và kết quả chính xác

Tạo tệp **`IntegerDivisionByZeroDemo.java`**:

```java
public class IntegerDivisionByZeroDemo {
    public static void main(String[] args) {
        int numerator = 10;
        int validDivisor = 3;
        int zero = 0;

        System.out.println("10 / 3 = " + (numerator / validDivisor));
        System.out.println("10 % 3 = " + (numerator % validDivisor));

        try {
            int quotient = numerator / zero;
            System.out.println(quotient);
        } catch (ArithmeticException ex) {
            System.out.println("10 / 0 -> ArithmeticException");
        }

        try {
            int remainder = numerator % zero;
            System.out.println(remainder);
        } catch (ArithmeticException ex) {
            System.out.println("10 % 0 -> ArithmeticException");
        }

        try {
            int zeroOverZero = zero / zero;
            System.out.println(zeroOverZero);
        } catch (ArithmeticException ex) {
            System.out.println("0 / 0 -> ArithmeticException");
        }

        boolean canDivide = zero != 0;
        System.out.println("valid divisor? " + canDivide);
        System.out.println("floating / zero infinite = "
                + Double.isInfinite(10.0 / zero));
        System.out.println("floating % zero NaN = "
                + Double.isNaN(10.0 % zero));
    }
}
```

Biên dịch và chạy:

```bash
javac IntegerDivisionByZeroDemo.java
java IntegerDivisionByZeroDemo
```

Kết quả:

```text
10 / 3 = 3
10 % 3 = 1
10 / 0 -> ArithmeticException
10 % 0 -> ArithmeticException
0 / 0 -> ArithmeticException
valid divisor? false
floating / zero infinite = true
floating % zero NaN = true
```

Vì đoạn chương trình **bắt riêng từng ngoại lệ**, các ví dụ sau vẫn tiếp tục thực thi. Đây chỉ là ví dụ giải thích sự khác nhau giữa phép toán nguyên và phép toán dấu phẩy động. Trong code nghiệp vụ, kiểm tra miền dữ liệu và báo lỗi theo yêu cầu thực tế là lựa chọn thường rõ ràng hơn.

## 8. Những hiểu lầm phổ biến

1. **“Chỉ chia cho 0 mới lỗi; lấy dư cho 0 thì trả lại tử số.”** Sai: với số nguyên, cả `/ 0` lẫn `% 0` đều ném `ArithmeticException`.
2. **“Nếu tử số bằng 0, `0 / 0` sẽ bằng 0.”** Sai: mẫu số vẫn bằng 0, nên phép chia không hợp lệ.
3. **“Java tự trả về `Infinity` khi có lỗi chia cho 0.”** Chỉ có hành vi `Infinity`/`NaN` liên quan tới phép toán dấu phẩy động; phép chia nguyên ném ngoại lệ.
4. **“Đổi biến nhận kết quả thành `double` là đủ.”** Sai: `double x = 10 / zero;` vẫn đánh giá `10 / zero` theo kiểu `int` trước khi gán, nên ngoại lệ vẫn xảy ra. Phải có toán hạng dấu phẩy động ngay **trong biểu thức** mới dùng ngữ nghĩa số thực.
5. **“Đã kiểm tra `divisor != 0` ở vế sau của `&&` thì an toàn.”** Sai nếu phép chia đứng trước; thứ tự đánh giá quyết định phép chia có chạy hay không.
6. **“`Math.floorMod(a, 0)` hoặc `BigInteger.divide(BigInteger.ZERO)` tự xử lý được.”** Sai: các API chia/lấy dư nguyên cũng từ chối mẫu số bằng 0.
7. **“Catch mọi `ArithmeticException` rồi trả về `0` là xử lý xong.”** Không có kết quả thương/số dư mặc định bằng 0. Trả về một giá trị thay thế phải là quy tắc được xác định rõ của hệ thống.

**Ghi nhớ:** Với phép tính nguyên trong Java, hãy xác nhận **mẫu số khác 0 trước khi thực hiện cả `/` và `%`**. Nếu mẫu số 0 là dữ liệu không hợp lệ, xử lý nó như một lỗi đầu vào hoặc tình huống không có kết quả. Số thực có `Infinity`/`NaN` theo quy tắc khác, nhưng không thay đổi tính không hợp lệ của phép chia nguyên cho 0.

**Tài liệu đặc tả:** [JLS §15.17.2 — Division Operator /](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17.2), [JLS §15.17.3 — Remainder Operator %](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17.3), [Java SE 21 — ArithmeticException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ArithmeticException.html).
