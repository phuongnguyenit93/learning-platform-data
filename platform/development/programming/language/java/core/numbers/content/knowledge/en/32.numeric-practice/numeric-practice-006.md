# Thực hành: tính giai thừa và dãy số lớn bằng BigInteger trong Java

## 1. Mục tiêu và bài toán

Các kiểu nguyên nguyên thủy của Java có giới hạn cố định: `int` dùng 32 bit có dấu, `long` dùng 64 bit có dấu. Khi tính các dãy tăng nhanh như **giai thừa** hoặc **Fibonacci**, kết quả sớm vượt những giới hạn đó. Nếu phép tính vẫn chạy trên `int` hoặc `long`, Java thường **tràn số (overflow) và cho kết quả sai**, chứ không tự nâng sang kiểu có nhiều bit hơn.

Bài thực hành sử dụng `java.math.BigInteger` để giải hai bài toán:

1. **Giai thừa**: tính `n! = 1 × 2 × ... × n`, với `0! = 1` và `n` nguyên không âm.
2. **Fibonacci**: tính `F(0) = 0`, `F(1) = 1` và `F(n) = F(n-1) + F(n-2)` khi `n ≥ 2`.

Kết thúc bài, bạn sẽ biết viết chương trình Java 17+ chạy được, sử dụng đúng API `BigInteger`, so sánh hai cách tính Fibonacci, xác thực đầu vào, kiểm tra kết quả, và hiểu vì sao “không tràn kiểu số” **không đồng nghĩa “không tốn tài nguyên”**.

## 2. Vì sao không dùng int hoặc long cho kết quả lớn?

### 2.1. Giai thừa vượt long rất sớm

Một số mốc:

| n | n! | Đánh giá |
|---|---|---|
| 0 | 1 | Định nghĩa giai thừa |
| 1 | 1 | Cơ sở |
| 5 | 120 | Vừa `int` |
| 12 | 479001600 | Còn vừa `int` |
| 13 | 6227020800 | **Vượt int** |
| 20 | 2432902008176640000 | Còn vừa `long` |
| 21 | 51090942171709440000 | **Vượt long** |
| 100 | Có 158 chữ số thập phân | Cần số nguyên tùy ý độ dài |

`Long.MAX_VALUE = 9223372036854775807`, nhỏ hơn `21!`. Bản thân việc gán kết quả đã overflow cho `BigInteger` sau đó **không sửa lại giá trị đúng**:

~~~java
long wrong = 1L;
for (int i = 2; i <= 21; i++) {
    wrong *= i; // long đã overflow trước khi có BigInteger nào tham gia
}
BigInteger tooLate = BigInteger.valueOf(wrong); // giữ giá trị sai
~~~

Đây là đoạn minh họa đặt trong một phương thức, có import `java.math.BigInteger`. Nếu cần chính xác, phải dùng phép nhân của `BigInteger` **ngay từ bước đầu**, không đợi tới khi có số lớn.

### 2.2. Fibonacci cũng vượt long

Dãy bắt đầu:

~~~text
n:     0  1  2  3  4  5  6  7  8  9  10
F(n):  0  1  1  2  3  5  8  13 21 34 55
~~~

Các mốc quan trọng:

- `F(50) = 12586269025`: vượt `int` nhưng còn vừa `long`.
- `F(92) = 7540113804746346429`: còn vừa `long`.
- `F(93) = 12200160415121876738`: vượt `Long.MAX_VALUE`.
- `F(100) = 354224848179261915075`: `BigInteger` biểu diễn được chính xác.

Không phải mọi bài toán cần BigInteger: nếu phạm vi n cố định rất nhỏ, `long` có thể đủ và thường nhẹ hơn. Khi phạm vi có thể lớn hoặc không thể chứng minh vừa kiểu cố định, `BigInteger` là lựa chọn phù hợp để giữ **số nguyên chính xác**.

## 3. Làm quen với API BigInteger

Import:

~~~java
import java.math.BigInteger;
~~~

Cách tạo:

~~~java
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger two = BigInteger.TWO; // Có trong Java 17
BigInteger small = BigInteger.valueOf(123L);
BigInteger large = new BigInteger("51090942171709440000");
~~~

Vì kết quả có thể lớn hơn `long`, chuỗi thập phân là cách nhập một hằng số lớn chính xác. Không viết `BigInteger.valueOf(51090942171709440000L)`: literal kiểu `long` đã vượt giới hạn và code không biên dịch.

`BigInteger` không hỗ trợ các toán tử số học thông thường kiểu `+`, `-`, `*` hoặc `/` dành cho primitive. Dùng các phương thức của nó:

| Phép toán | BigInteger |
|---|---|
| `a + b` | `a.add(b)` |
| `a - b` | `a.subtract(b)` |
| `a * b` | `a.multiply(b)` |
| `a / b` (thương nguyên) | `a.divide(b)` |
| `a % b` | `a.remainder(b)` |
| `a ^ n` theo nghĩa lũy thừa | `a.pow(n)` |
| So sánh lớn hơn | `a.compareTo(b) > 0` |
| Bằng nhau theo giá trị BigInteger | `a.equals(b)` |

BigInteger **bất biến (immutable)**: lời gọi `result.multiply(factor)` không tự thay đổi `result`. Cần lưu giá trị trả về:

~~~java
BigInteger result = BigInteger.ONE;
result.multiply(BigInteger.valueOf(5)); // Kết quả bị bỏ đi!
System.out.println(result);             // 1

result = result.multiply(BigInteger.valueOf(5));
System.out.println(result);             // 5
~~~

Đây là lý do trong vòng lặp ta luôn viết `result = result.multiply(...)` và `next = previous.add(current)`.

**Lưu ý:** `BigInteger` bảo đảm phép toán số nguyên chính xác trong phạm vi tài nguyên và giới hạn triển khai, nhưng không tạo bộ nhớ vô hạn. Các số lớn vẫn làm tăng chi phí CPU, vùng nhớ và lượng dữ liệu khi in/ghi.

## 4. Giải bài toán 1: giai thừa bằng vòng lặp

Với `n ≥ 0`:

\[
n! = \prod_{k=1}^{n} k,\qquad 0! = 1.
\]

Ý tưởng:

- Bắt đầu `result = BigInteger.ONE`, vì **phần tử trung hòa của phép nhân là 1**.
- Duyệt `k` từ 2 đến `n`.
- Mỗi bước tính `result = result.multiply(BigInteger.valueOf(k))`.
- Trả lại `result`. Nếu `n = 0` hoặc `n = 1`, vòng lặp không chạy và kết quả vẫn là 1.

Phiên bản method:

~~~java
static BigInteger factorial(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    BigInteger result = BigInteger.ONE;
    for (long k = 2; k <= n; k++) {
        result = result.multiply(BigInteger.valueOf(k));
    }
    return result;
}
~~~

Đây là **phương thức để đặt trong một class** có import `java.math.BigInteger`, không phải chương trình standalone. Dùng biến đếm `long k` để tránh trường hợp vòng lặp `int` tự overflow khi n ở cực trị `Integer.MAX_VALUE`; điều đó không có nghĩa là tính `Integer.MAX_VALUE!` khả thi trong bộ nhớ/thời gian thực tế. Ở ứng dụng thật, vẫn phải đặt giới hạn đầu vào.

**Bất biến vòng lặp:** sau khi xử lý xong số `k`, `result == k!`. Trước vòng đầu, `result = 1`, đúng cho `1!`. Nếu `result` đang bằng `(k-1)!` thì nhân với `k` cho `k!`. Do đó kết quả sau cùng là `n!`.

Có thể viết đệ quy:

~~~java
static BigInteger factorialRecursive(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    if (n <= 1) {
        return BigInteger.ONE;
    }
    return BigInteger.valueOf(n)
            .multiply(factorialRecursive(n - 1));
}
~~~

Đây cũng là một method trong class (có import BigInteger). Bản đệ quy phản ánh định nghĩa toán học, nhưng dùng **stack O(n)** và có thể `StackOverflowError` khi n lớn. Bản vòng lặp là lựa chọn mặc định dễ hiểu và vững hơn cho bài tập tính n! lớn. Đừng chọn đệ quy chỉ vì công thức n! thường được viết đệ quy.

## 5. Giải bài toán 2: Fibonacci bằng hai biến BigInteger

Một cách viết Fibonacci đệ quy ngây thơ:

~~~java
// CHỈ minh họa công thức; không phù hợp cho n lớn.
static BigInteger fibonacciSlow(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    if (n <= 1) {
        return BigInteger.valueOf(n);
    }
    return fibonacciSlow(n - 1).add(fibonacciSlow(n - 2));
}
~~~

Đoạn code có import BigInteger, nhưng **tính lại cùng giá trị rất nhiều lần**. Ví dụ khi tính `F(40)`, cả `F(38)` và nhiều giá trị nhỏ hơn xuất hiện lặp lại trong cây gọi. Số lời gọi tăng theo cấp số nhân; tăng bit-width bằng BigInteger **không sửa được thuật toán lãng phí đó**.

Giải pháp vòng lặp chỉ giữ hai giá trị gần nhất:

~~~java
static BigInteger fibonacci(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    BigInteger previous = BigInteger.ZERO; // F(0)
    BigInteger current = BigInteger.ONE;   // F(1)

    for (long k = 0; k < n; k++) {
        BigInteger next = previous.add(current);
        previous = current;
        current = next;
    }
    return previous;
}
~~~

Cách hiểu:

| n cần tính | Số vòng | `previous` khi trả về |
|---|---:|---|
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 10 | 10 | 55 |

**Bất biến:** tại đầu vòng lặp thứ k (đếm từ 0), `previous = F(k)` và `current = F(k+1)`. Gán `next = previous.add(current)` tạo `F(k+2)`, rồi dịch cặp thành `F(k+1), F(k+2)`. Vì thế sau n lần lặp, `previous = F(n)`.

Lưu ý thứ tự gán: nếu viết `previous = current; current = previous.add(current);` thì sau khi thay previous, bạn đã mất giá trị cũ cần dùng; công thức dãy sẽ sai. Biến `next` giúp tránh lỗi cập nhật trạng thái theo sai thứ tự.

Phương pháp này có **n bước cộng**, dùng một số lượng nhỏ tham chiếu BigInteger trong code; nó không lưu toàn bộ dãy trong bộ nhớ. Nếu cần **in cả dãy**, số dữ liệu đầu ra sẽ lớn hơn rất nhiều so với chỉ tìm một số hạng.

## 6. Chương trình hoàn chỉnh: factorial, Fibonacci và đối chiếu fast doubling

Phương pháp Fibonacci vòng lặp phù hợp để học nguyên lý. Nếu chỉ cần `F(n)` với n lớn, có một kỹ thuật ít bước hơn gọi là **fast doubling**:

\[
\begin{aligned}
F(2k) &= F(k)\,[2F(k+1)-F(k)],\\
F(2k+1) &= F(k)^2 + F(k+1)^2.
\end{aligned}
\]

Một hàm có thể trả đồng thời cặp `(F(n), F(n+1))`. Chia n làm đôi mỗi lần nên số **tầng đệ quy O(log n)**; tuy nhiên các phép nhân làm việc với BigInteger ngày càng dài, nên **không được suy ra tổng thời gian tính chỉ O(log n) theo bit**.

Lưu toàn bộ code sau vào **`BigIntegerSequenceDemo.java`**:

~~~java
import java.math.BigInteger;

public final class BigIntegerSequenceDemo {
    private BigIntegerSequenceDemo() {}

    private static void validate(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
    }

    public static BigInteger factorial(int n) {
        validate(n);
        BigInteger result = BigInteger.ONE;
        for (long k = 2; k <= n; k++) {
            result = result.multiply(BigInteger.valueOf(k));
        }
        return result;
    }

    public static BigInteger fibonacci(int n) {
        validate(n);
        BigInteger previous = BigInteger.ZERO;
        BigInteger current = BigInteger.ONE;
        for (long k = 0; k < n; k++) {
            BigInteger next = previous.add(current);
            previous = current;
            current = next;
        }
        return previous;
    }

    public static BigInteger fibonacciFast(int n) {
        validate(n);
        return fibPair(n)[0];
    }

    private static BigInteger[] fibPair(int n) {
        if (n == 0) {
            return new BigInteger[] {BigInteger.ZERO, BigInteger.ONE};
        }
        BigInteger[] half = fibPair(n / 2);
        BigInteger a = half[0];
        BigInteger b = half[1];
        BigInteger c = a.multiply(b.shiftLeft(1).subtract(a));
        BigInteger d = a.multiply(a).add(b.multiply(b));
        return (n % 2 == 0)
                ? new BigInteger[] {c, d}
                : new BigInteger[] {d, c.add(d)};
    }

    public static void main(String[] args) {
        System.out.println("0! = " + factorial(0));
        System.out.println("1! = " + factorial(1));
        System.out.println("5! = " + factorial(5));
        System.out.println("20! = " + factorial(20));
        System.out.println("21! = " + factorial(21));
        System.out.println("100! decimal digits = "
                + factorial(100).toString().length());

        System.out.println("F(0) = " + fibonacci(0));
        System.out.println("F(1) = " + fibonacci(1));
        System.out.println("F(10) = " + fibonacci(10));
        System.out.println("F(50) = " + fibonacci(50));
        System.out.println("F(100) = " + fibonacci(100));
        System.out.println("fast F(100) matches = "
                + fibonacci(100).equals(fibonacciFast(100)));

        boolean allMatch = true;
        for (int n = 0; n <= 100; n++) {
            if (!fibonacci(n).equals(fibonacciFast(n))) {
                allMatch = false;
                break;
            }
        }
        System.out.println("cross-check F(0..100) = " + allMatch);

        boolean negativeRejected = false;
        try {
            factorial(-1);
        } catch (IllegalArgumentException expected) {
            negativeRejected = true;
        }
        System.out.println(
                "negative factorial rejected = " + negativeRejected);
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac BigIntegerSequenceDemo.java
java BigIntegerSequenceDemo
~~~

**Kết quả stdout đã kiểm chứng bằng chạy chương trình:**

~~~text
0! = 1
1! = 1
5! = 120
20! = 2432902008176640000
21! = 51090942171709440000
100! decimal digits = 158
F(0) = 0
F(1) = 1
F(10) = 55
F(50) = 12586269025
F(100) = 354224848179261915075
fast F(100) matches = true
cross-check F(0..100) = true
negative factorial rejected = true
~~~

### Giải thích công thức fast doubling trong code

Giả sử lời gọi đệ quy trả `a = F(k)` và `b = F(k+1)`, trong đó `k = n / 2`. Ta tính:

- `c = a × (2b - a) = F(2k)`. Với BigInteger, `b.shiftLeft(1)` tương đương nhân b với 2.
- `d = a² + b² = F(2k+1)`.
- Nếu n chẵn (`n = 2k`), cặp cần trả là `(c, d)`.
- Nếu n lẻ (`n = 2k+1`), cặp cần trả là `(d, c+d)`.

Khi `n = 0`, trả `(F(0), F(1)) = (0, 1)`. Mỗi lần gọi giảm n còn `n/2`, nên độ sâu đệ quy tăng theo log n thay vì n. Thuật toán không yêu cầu memoize toàn bộ dãy và tránh chi phí cây đệ quy cấp số nhân của `fibonacciSlow`.

**Không nhầm tính đúng với độ nhanh tuyệt đối:** với n nhỏ, vòng lặp dễ đọc và có thể chạy nhanh hơn do không phải nhân BigInteger. Fast doubling thường đáng cân nhắc khi chỉ muốn số hạng ở chỉ số lớn.

## 7. So sánh thuật toán và độ phức tạp thực tế

Cần phân biệt **số lần thao tác ở mức thuật toán** với **chi phí tính toán mỗi thao tác BigInteger**.

| Cách tính | Số bước mức cao | Bộ nhớ giữ trạng thái | Đặc điểm |
|---|---|---|---|
| Giai thừa vòng lặp | n−1 phép nhân khi n≥2 | Ít biến BigInteger; kết quả lớn dần | Dễ hiểu, tránh sâu stack |
| Giai thừa đệ quy | n mức lời gọi | Stack O(n) | Không phù hợp n rất lớn |
| Fibonacci đệ quy ngây thơ | Tăng theo cấp số nhân | Stack O(n), tính lặp | Chỉ để dạy công thức, không dùng n lớn |
| Fibonacci vòng lặp | n phép cộng | Hai giá trị trạng thái chính | Đơn giản, không lưu toàn dãy |
| Fibonacci fast doubling | O(log n) tầng, mỗi tầng một số phép nhân/cộng BigInteger | Stack O(log n) và kết quả trung gian | Hiệu quả hơn về số bước cho chỉ số lớn |

BigInteger không phải phép cộng/nhân O(1) khi toán hạng có độ dài tăng. Với Fibonacci, độ dài bit của `F(n)` là Θ(n) khi n lớn; vì thế một phép cộng ở bước muộn tốn nhiều hơn ở bước đầu. Theo mô hình cộng số nhiều limb tuyến tính, n lần cộng trên các số tăng dần có tổng công việc xấp xỉ **O(n²) bit operations**; bảng “n phép cộng” không phải cam kết O(n) thời gian máy.

Với giai thừa, `n!` có độ dài bit Θ(n log n); mỗi lần nhân thêm một số có độ dài khoảng log n bit, còn tích trung gian lớn dần. Tổng thời gian tùy thuật toán nhân, phân bổ bộ nhớ và triển khai JDK; không nên mô tả mọi lời gọi `multiply` như một phép toán tốn cùng chi phí.

Bộ nhớ BigInteger cũng tăng theo kích thước **kết quả và các kết quả tạm**, dù chương trình chỉ giữ vài biến. Ví dụ `F(100000)` có hàng chục nghìn chữ số thập phân; nếu in toàn bộ mỗi bước, thời gian I/O và tạo chuỗi có thể chiếm ưu thế so với tính toán.

## 8. Đầu vào không hợp lệ, tài nguyên và giới hạn ứng dụng

Về định nghĩa giai thừa cơ bản, `n` phải là số nguyên không âm. Fibonacci trong bài này được định nghĩa cho chỉ số không âm. Do đó API minh họa từ chối `n < 0` bằng `IllegalArgumentException` thay vì lặng lẽ trả 1 hoặc 0.

Nhưng `n >= 0` **chưa đủ để một dịch vụ sản xuất an toàn**. Người dùng có thể gửi `n = 1_000_000_000`: kết quả giai thừa vô cùng lớn trong phạm vi thực tế, có thể tiêu hao bộ nhớ, CPU hoặc thời gian phản hồi. Một dịch vụ cần quy định rõ **giới hạn dựa trên quota và mục đích**:

~~~java
static final int MAX_FACTORIAL_N = 5_000;

static BigInteger factorialForApi(int n) {
    if (n < 0 || n > MAX_FACTORIAL_N) {
        throw new IllegalArgumentException("n out of allowed range");
    }
    return BigIntegerSequenceDemo.factorial(n);
}
~~~

Đoạn trên là **method minh họa của một class khác** có import BigInteger và quyền gọi `BigIntegerSequenceDemo` từ ví dụ hoàn chỉnh. Giá trị 5.000 chỉ là **chính sách ví dụ**, không phải giới hạn cố định của BigInteger. Muốn đặt quota thật, hãy đo và xác nhận trên môi trường chạy cụ thể.

Các giới hạn có thể cần xét đồng thời:

- Chỉ số n đầu vào, nguồn gốc và kiểu dữ liệu (không parse số tùy ý mà không giới hạn độ dài request).
- Số bit hoặc chữ số kết quả ước lượng trước khi bắt đầu.
- Thời gian CPU, heap/memory, thời gian chờ và số yêu cầu chạy đồng thời.
- Chi phí serialize và truyền dữ liệu qua mạng nếu API trả toàn bộ số nguyên khổng lồ.
- Việc lưu cache kết quả: cache nhiều BigInteger lớn có thể tiết kiệm CPU nhưng tốn heap đáng kể.

**Chỉ dùng `BigInteger` không làm thuật toán an toàn trước yêu cầu từ chối dịch vụ do input quá lớn.** BigInteger vẫn có giới hạn của JVM/array và tài nguyên máy.

## 9. Không dùng double làm lối tắt cho kết quả nguyên chính xác

Có thể thấy `double` có miền số mũ rất rộng, nhưng độ chính xác hữu hạn nên không biểu diễn chính xác mọi số nguyên lớn. Chuyển số nguyên lớn sang double hoặc tính gần đúng giai thừa bằng double có thể đánh mất chữ số.

~~~java
BigInteger exact = BigIntegerSequenceDemo.factorial(21);
double approximate = exact.doubleValue(); // Có thể không giữ đủ chữ số
~~~

Đoạn này nằm trong phương thức, có import BigInteger và phụ thuộc class ở phần 6. Khi mục tiêu là **số nguyên chính xác tuyệt đối**, không lấy `double` làm nguồn chân lý hay so sánh kết quả BigInteger bằng cách chuyển đôi bên sang double.

Ngay cả `BigDecimal` cũng không thay thế tự động cho BigInteger: BigDecimal phục vụ số thập phân tùy ý scale/precision; BigInteger đơn giản và trực tiếp hơn cho các dãy số nguyên rời rạc như giai thừa và Fibonacci. Chọn kiểu theo bài toán, không chỉ theo “số có thể lớn”.

## 10. Kiểm tra tính đúng bằng test bất biến

Một bộ test có ý nghĩa hơn kiểm tra một kết quả lớn được chép tay:

**Giai thừa:**

- `factorial(0) = 1` và `factorial(1) = 1`.
- `factorial(5) = 120`, `factorial(20)` khớp giá trị đã biết.
- Với `n ≥ 1`, `factorial(n) = factorial(n-1) × n`.
- Với `n < 0`, nhận `IllegalArgumentException`.
- `factorial(21)` lớn hơn `Long.MAX_VALUE`, không được quy về `long`.

**Fibonacci:**

- `F(0) = 0`, `F(1) = 1`.
- Với `n ≥ 2`, `F(n) = F(n-1) + F(n-2)`.
- Với n từ 0 đến 100, bản vòng lặp và bản fast doubling trả kết quả bằng nhau; ví dụ ở phần 6 đã làm việc này.
- `F(93)` vượt `Long.MAX_VALUE`; mọi lần cộng vẫn thực hiện bằng `BigInteger.add`.
- Với `n < 0`, API từ chối theo contract của bài.

Ví dụ các kiểm tra tự chạy được sau khi có class hoàn chỉnh, đặt trong thân method:

~~~java
if (!BigIntegerSequenceDemo.factorial(6)
        .equals(BigInteger.valueOf(720))) {
    throw new AssertionError("6! must equal 720");
}

if (!BigIntegerSequenceDemo.fibonacci(20)
        .equals(BigInteger.valueOf(6765))) {
    throw new AssertionError("F(20) must equal 6765");
}
~~~

Đây là code minh họa (có import BigInteger). Có thể chuyển những kiểm tra này sang JUnit; bài này không yêu cầu dependency ngoài Java 17 để chạy ví dụ chính.

### Kiểm thử thay vì chỉ in kết quả

- `System.out.println` giúp quan sát, nhưng tự động hóa nên dùng so sánh `equals` hoặc `compareTo` và ném lỗi nếu sai.
- Với BigInteger, **không dùng `==`** để so sánh giá trị số vì nó so sánh tham chiếu đối tượng.
- Khi test một hàm tối ưu (fast doubling), hãy đối chiếu với bản đơn giản đáng tin ở phạm vi nhỏ; với phạm vi lớn, kiểm tra công thức hoặc mốc đã biết và tiêu chí tài nguyên.
- Đối với ca n cực lớn, test riêng timeout, giới hạn request và xử lý lỗi thay vì chạy thật kết quả quá lớn trong bộ unit test nhanh.

## 11. Mở rộng sang một dãy số khác

Bài toán không chỉ áp dụng cho Fibonacci. Nhiều dãy có thể biểu diễn bằng recurrence:

\[
a_n = c_1a_{n-1} + c_2a_{n-2},\qquad n\ge 2.
\]

Nếu các hệ số và giá trị ban đầu là số nguyên, có thể dùng BigInteger cho mọi phép nhân/cộng để tránh overflow. Ví dụ **dãy Lucas** có `L(0) = 2`, `L(1) = 1`, `L(n) = L(n-1)+L(n-2)`:

~~~java
static BigInteger lucas(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    BigInteger previous = BigInteger.TWO;
    BigInteger current = BigInteger.ONE;
    for (long k = 0; k < n; k++) {
        BigInteger next = previous.add(current);
        previous = current;
        current = next;
    }
    return previous;
}
~~~

Đây là method (đặt trong class với import BigInteger) dùng cùng kỹ thuật dịch hai biến. Nó trả `L(0)=2`, `L(1)=1`, `L(2)=3`, `L(3)=4`, `L(4)=7`.

Khi cần toàn bộ dãy từ `a0` đến `an`, có thể lưu từng số vào list, nhưng phải tính chi phí bộ nhớ theo **tổng độ dài của tất cả các phần tử**. Nếu chỉ cần `an`, hai biến trạng thái thường phù hợp hơn. Với recurrence tuyến tính và n cực lớn, có thể nghiên cứu **lũy thừa ma trận** bằng BigInteger hoặc công thức đặc biệt; trước hết phải chứng minh công thức và xử lý hệ số âm/điều kiện đầu đúng.

## 12. Những lỗi phổ biến

| Lỗi | Điều xảy ra | Cách làm đúng |
|---|---|---|
| Dùng `int` cho `13!` | Tràn 32 bit | BigInteger ngay từ bước nhân đầu |
| Dùng `long` cho `21!` hoặc `F(93)` | Tràn 64 bit | `BigInteger.multiply/add` |
| Nhân bằng long rồi chuyển `valueOf` | Giá trị đã sai trước khi chuyển | Duy trì toàn bộ phép toán ở BigInteger |
| Viết `result.multiply(x)` mà không nhận kết quả | `result` không đổi | `result = result.multiply(x)` |
| Viết `a + b` cho hai BigInteger | Không biên dịch | `a.add(b)` |
| So sánh `a == b` để kiểm tra giá trị | So tham chiếu | `a.equals(b)` |
| Trả `0` cho `factorial(-1)` | Phá định nghĩa đầu vào | Ném lỗi rõ ràng |
| Viết Fibonacci đệ quy `F(n-1)+F(n-2)` cho n lớn | Tính trùng vô số lần | Vòng lặp hoặc fast doubling |
| Chọn đệ quy cho giai thừa cực lớn | Có thể tràn stack | Vòng lặp |
| Cho rằng có BigInteger thì vô hạn CPU/heap | Có thể treo/hết bộ nhớ | Giới hạn và kiểm tra tài nguyên |
| In mọi số khổng lồ khi benchmark | Format/I/O che chi phí thuật toán | Đo tách riêng, dùng JMH khi cần |
| Chuyển số lớn sang double để đối chiếu | Mất tính chính xác của số nguyên | So trực tiếp BigInteger |

## 13. Bài tập tự luyện

**Bài 1.** Viết hàm `factorial(30)` bằng BigInteger. Dự đoán vì sao một biến `long` không thể lưu được kết quả. Dùng `equals` để so sánh với chuỗi:

~~~text
265252859812191058636308480000000
~~~

**Bài 2.** Viết hàm trả `F(93)` theo vòng lặp, đối chiếu với:

~~~text
12200160415121876738
~~~

Vì sao giá trị này không vừa signed long?

**Bài 3.** Viết hàm tính **tổng từ F(0) đến F(n)** mà không xây một list toàn dãy. Bạn có thể dùng đẳng thức `F(0)+...+F(n)=F(n+2)-1` với n không âm, nhưng phải chứng minh trước khi sử dụng.

**Bài 4.** Phân tích khác biệt chi phí giữa “in toàn bộ F(0)..F(n)” và “chỉ trả về F(n)”, dù cả hai đều có thể chạy với BigInteger.

**Bài 5.** Sửa lỗi:

~~~java
BigInteger result = BigInteger.ONE;
for (int i = 2; i <= 30; i++) {
    result.multiply(BigInteger.valueOf(i));
}
System.out.println(result);
~~~

**Bài 6.** Viết một test gọi hai phiên bản Fibonacci cho mọi n từ 0 tới 1000, dừng khi thấy khác biệt. Giải thích vì sao test chéo thuật toán mạnh hơn chỉ test một giá trị `F(10)=55`.

### Đáp án/gợi ý

1. `30! = 265252859812191058636308480000000`, lớn hơn `Long.MAX_VALUE`. Code factorial phần 6 xử lý.
2. `F(93)` lớn hơn `9223372036854775807`; dùng `BigInteger` là phù hợp.
3. Có thể cộng dồn qua vòng lặp dùng `BigInteger.add`, hoặc dùng identity và `fibonacciFast(n+2).subtract(BigInteger.ONE)` khi chỉ số n+2 nằm trong miền int và input hợp lệ.
4. Lưu hoặc in mọi số hạng tốn dữ liệu I/O/bộ nhớ tỉ lệ tổng độ dài từng phần tử. Trả một số hạng chỉ giữ các giá trị trung gian cần thiết.
5. Gán lại `result = result.multiply(BigInteger.valueOf(i));` để không bỏ kết quả.
6. Mỗi n là một trường hợp gồm cả parity chẵn/lẻ, base case, công thức nhân và phép cộng; test chéo có thể phát hiện nhiều lỗi hơn một mốc đơn lẻ, dù không thay thế hoàn toàn chứng minh tính đúng.

## 14. Tài liệu chuẩn

- Java SE 17, `BigInteger` API (`add`, `multiply`, `pow`, `shiftLeft`, `bitLength`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html
- Java SE 17, `ArithmeticException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html
- Java SE 17, `IllegalArgumentException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html

**Ghi nhớ:** BigInteger giúp giữ kết quả **số nguyên chính xác** khi giai thừa hoặc dãy tăng vượt `int`/`long`. Tính đúng đến từ **công thức, điều kiện đầu, thứ tự cập nhật và việc dùng phép toán BigInteger ngay từ đầu**; tính khả thi đến từ lựa chọn thuật toán và giới hạn tài nguyên phù hợp.
