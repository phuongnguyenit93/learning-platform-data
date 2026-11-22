# Dùng BigInteger hoặc phép tính tham chiếu để phát hiện tràn trong Java

## 1. Tại sao cần kiểm thử tràn số?

Trong Java, `int` và `long` là số nguyên có dấu với độ rộng cố định:

| Kiểu | Độ rộng | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 bit | `-2147483648` | `2147483647` |
| `long` | 64 bit | `-9223372036854775808` | `9223372036854775807` |

Các phép cộng, trừ, nhân kiểu nguyên thông thường **không ném ngoại lệ khi tràn**. Kết quả chỉ giữ các bit thấp trong độ rộng tương ứng rồi được diễn giải theo số nguyên có dấu hai bù. Ví dụ:

~~~java
int x = Integer.MAX_VALUE;
int wrapped = x + 1; // -2147483648, không có exception
~~~

Kết quả toán học đúng phải là `2147483648`, lớn hơn `Integer.MAX_VALUE` một đơn vị. Nếu ứng dụng chỉ kiểm tra “không có exception”, lỗi có thể lọt vào số lượng hàng, tổng doanh thu biểu diễn theo đơn vị nhỏ nhất, timestamp, giới hạn bộ nhớ, kích thước mảng hoặc thuật toán so sánh.

**Chiến lược kiểm thử cốt lõi:** tính cùng phép toán bằng một biểu diễn có phạm vi đủ lớn để làm **kết quả tham chiếu (oracle)**, chẳng hạn `BigInteger`, rồi so kết quả đó với miền giá trị của kiểu đích. Đối với phép toán đang chạy trong sản phẩm, `Math.addExact`, `subtractExact`, `multiplyExact` và các API kiểm tra chính xác khác giúp phát hiện tràn ngay tại chỗ.

Có hai câu hỏi khác nhau:

1. **Kết quả toán học đúng bằng bao nhiêu?** Dùng `BigInteger` hoặc phép tính với kiểu rộng hơn khi đủ chắc chắn.
2. **Có thể biểu diễn kết quả chính xác bằng `int` hoặc `long` không?** So với `MIN_VALUE`/`MAX_VALUE`, hoặc dùng `intValueExact()`, `longValueExact()` và các hàm `Math.*Exact`.

Không nên dùng ngay kết quả đã tràn làm đáp án tham chiếu, vì không còn đủ thông tin để biết giá trị toán học ban đầu.

## 2. Cơ chế tràn số nguyên: hai bù và miền biểu diễn

Với số nguyên có dấu `n` bit, miền giá trị là:

\[
-2^{n-1} \le x \le 2^{n-1}-1.
\]

Khi một phép cộng/trừ/nhân nguyên thông thường vượt miền, Java giữ phần phù hợp với độ rộng 32/64 bit. Có thể hình dung kết quả được lấy theo modulo \(2^n\), sau đó diễn giải lại thành số có dấu.

Ví dụ `Integer.MAX_VALUE + 1`:

- Kết quả toán học: `2147483648 = 2^31`.
- Biểu diễn `int` 32 bit ứng với bit dấu bật và các bit còn lại 0.
- Giá trị `int` Java nhận được: `-2147483648`, tức `Integer.MIN_VALUE`.

Với `Long.MAX_VALUE * 2`:

- Kết quả toán học: `18446744073709551614`.
- Kết quả `long` thông thường: `-2`.

**Không có cờ overflow tự động trả về từ toán tử `+`, `-`, `*`.** Nếu ứng dụng cần từ chối tràn, phải chủ động dùng API exact hoặc kiểm tra với oracle.

Đây là hành vi **được Java định nghĩa**, không phải undefined behavior. Nhưng việc kết quả có tính xác định không làm nó đúng với yêu cầu nghiệp vụ.

### 2.1. Đừng nhầm tràn với mất độ chính xác dấu phẩy động

`float` và `double` hoạt động theo hệ số thực dấu phẩy động IEEE 754. Vượt giới hạn có thể dẫn đến `Infinity`, trong khi nhiều phép tính không tràn vẫn bị làm tròn vì precision hữu hạn. Chủ đề này tập trung vào **tràn `int`/`long`**, với `BigInteger` làm tham chiếu cho số học nguyên chính xác. Không dùng cùng một cách so sánh byte-for-byte cho số thực khi hợp đồng cho phép sai số xấp xỉ.

`BigDecimal` có thể hữu ích cho phép tính thập phân chính xác, nhưng nếu mục tiêu kiểm thử là phép toán nguyên `int`/`long`, `BigInteger` biểu đạt trực tiếp kết quả nguyên và thường là oracle rõ ràng hơn.

## 3. BigInteger làm oracle độc lập

`BigInteger` (gói `java.math`) biểu diễn số nguyên với độ chính xác tùy ý theo tài nguyên máy, không giới hạn trong 32 hoặc 64 bit.

~~~java
import java.math.BigInteger;

long a = Long.MAX_VALUE;
long b = 2L;

long actual = a * b; // -2, kết quả long bị tràn
BigInteger expected = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));
// 18446744073709551614: kết quả toán học chính xác
~~~

`BigInteger` bất biến. Các phép toán như `add`, `subtract`, `multiply`, `divide`, `remainder`, `pow`, `shiftLeft` trả đối tượng kết quả mới. Vì vậy các phép tham chiếu không chịu tràn kiểu `int`/`long` trong điều kiện bộ nhớ và giới hạn tài nguyên cho phép.

**Bẫy quan trọng:** phải chuyển **toán hạng gốc** sang `BigInteger` *trước* khi tính:

~~~java
long a = Long.MAX_VALUE;
long b = 2L;

BigInteger wrongOracle = BigInteger.valueOf(a * b);
// -2: phép nhân long đã tràn trước khi BigInteger xuất hiện!

BigInteger correctOracle = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));
// 18446744073709551614
~~~

Tương tự, `BigInteger.valueOf((long) (intA + intB))` **không an toàn** nếu phép cộng `int` đã được thực hiện trước khi ép kiểu.

### 3.1. Kiểm tra oracle có nằm trong phạm vi long/int không

~~~java
BigInteger exact = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

boolean fitsLong =
        exact.compareTo(BigInteger.valueOf(Long.MIN_VALUE)) >= 0
        && exact.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) <= 0;
// false
~~~

Với `int`, thay các cận bằng `Integer.MIN_VALUE` và `Integer.MAX_VALUE`. Đây là kiểm tra chính xác dựa trên toán học và không dựa vào kết quả primitive đã bị tràn.

Có lựa chọn ngắn hơn:

~~~java
try {
    long exactLong = exact.longValueExact();
} catch (ArithmeticException ex) {
    // Giá trị không nằm trong miền long
}
~~~

`intValueExact()` và `longValueExact()` của `BigInteger` ném `ArithmeticException` khi không thể biểu diễn chính xác trong kiểu đích.

**Không dùng** `exact.longValue()` hoặc `exact.intValue()` làm phép kiểm tra tràn: các phương thức chuyển đổi không có chữ `Exact` có thể bỏ bit cao và trả một giá trị đã bị thay đổi.

## 4. API Math.*Exact giúp phát hiện tràn tại phép toán

Java cung cấp những phương thức kiểm tra khi cần kết quả `int`/`long` chính xác:

| Nhu cầu | API | Khi vượt miền |
| --- | --- | --- |
| Cộng | `Math.addExact(a, b)` | Ném `ArithmeticException` |
| Trừ | `Math.subtractExact(a, b)` | Ném `ArithmeticException` |
| Nhân | `Math.multiplyExact(a, b)` | Ném `ArithmeticException` |
| Đổi dấu | `Math.negateExact(value)` | Ném `ArithmeticException` |
| Tăng/giảm một đơn vị | `Math.incrementExact(value)`, `Math.decrementExact(value)` | Ném `ArithmeticException` |
| Trị tuyệt đối của `int`/`long` | `Math.absExact(value)` | Ném khi là giá trị MIN tương ứng |
| Thu hẹp `long` xuống `int` | `Math.toIntExact(value)` | Ném nếu ngoài phạm vi int |

Các overload và phương thức cụ thể phải được chọn đúng kiểu. Chẳng hạn `Math.addExact(int,int)` trả `int`, còn `Math.addExact(long,long)` trả `long`. Khi hai toán hạng là `int` và mong muốn kết quả `long`, có thể chủ động mở rộng ít nhất một toán hạng **trước khi cộng**.

~~~java
int left = Integer.MAX_VALUE;
int right = 1;

long correct = (long) left + right;  // 2147483648
long wrong = (long) (left + right);  // -2147483648

// Nếu kết quả bắt buộc phải là int:
try {
    int checked = Math.addExact(left, right);
} catch (ArithmeticException ex) {
    // Vượt phạm vi int, xử lý lỗi theo hợp đồng nghiệp vụ
}
~~~

Trong biến thể `wrong`, dấu ngoặc buộc cộng `int` trước rồi mới ép kiểu `long`, nên không thể “sửa” tràn đã xảy ra. Trong biến thể `correct`, toán hạng trái thành `long` trước khi cộng, phép cộng được tính ở phạm vi 64 bit.

Với hai toán hạng `long`, mở rộng lên `long` lần nữa không giúp gì. Dùng `Math.*Exact` hoặc `BigInteger` để tính một kết quả lớn hơn miền 64 bit.

### 4.1. BigInteger và Math.*Exact bổ trợ nhau ra sao?

- **Trong logic ứng dụng:** dùng `Math.*Exact` nếu tràn là lỗi và cần phát hiện ngay khi thao tác.
- **Trong test:** dùng `BigInteger` độc lập để xác nhận phép toán trả đúng giá trị khi còn trong miền và báo lỗi khi vượt miền.
- **Khi dữ liệu hợp lệ thực sự có thể vượt long:** dùng `BigInteger` trong mô hình dữ liệu/kết quả thay vì chỉ bắt lỗi rồi tiếp tục lưu vào `long`.
- **Khi cần giá trị thay thế như saturating arithmetic:** định nghĩa rõ hợp đồng trả `MIN_VALUE`/`MAX_VALUE`, rồi kiểm tra với oracle. Không gọi đó là phép tính exact.

Một test chỉ gọi `Math.addExact` rồi tin nó đúng có thể hữu ích để kiểm tra API ứng dụng đã chọn. Nhưng kiểm tra độc lập bằng `BigInteger` giúp bắt lỗi ở cách gọi nhầm overload, ép kiểu sai thứ tự hoặc xử lý trường hợp biên thiếu nhất quán.

## 5. Những phép toán đặc biệt rất dễ bỏ sót

### 5.1. Phép chia `MIN_VALUE / -1`

Trong Java, phép chia nguyên có một trường hợp tràn đặc biệt:

~~~java
long wrapped = Long.MIN_VALUE / -1L;
// -9223372036854775808: không ném ArithmeticException
~~~

Kết quả toán học đúng là `9223372036854775808`, **lớn hơn `Long.MAX_VALUE`**. Tương tự, `Integer.MIN_VALUE / -1` trả lại `Integer.MIN_VALUE`.

`Math.addExact` hay `multiplyExact` không phải phép kiểm tra cho phép chia. Với Java 17, bạn có thể kiểm tra trường hợp ngoại lệ bằng điều kiện:

~~~java
static long divideChecked(long dividend, long divisor) {
    if (divisor == 0L) {
        throw new ArithmeticException("/ by zero");
    }
    if (dividend == Long.MIN_VALUE && divisor == -1L) {
        throw new ArithmeticException("long division overflow");
    }
    return dividend / divisor;
}
~~~

Đây là phương thức minh họa trong một lớp; nếu dùng phép chia BigInteger làm oracle, nhớ rằng `BigInteger.divide` cũng từ chối chia cho 0. Phép chia nguyên thông thường **cắt phần dư về 0**, không phải chia cho kết quả thực rồi làm tròn theo một rounding mode thập phân.

### 5.2. Phép đổi dấu và trị tuyệt đối của giá trị nhỏ nhất

~~~java
int x = Integer.MIN_VALUE;

int negated = -x;         // vẫn là Integer.MIN_VALUE
int magnitude = Math.abs(x); // vẫn là Integer.MIN_VALUE
~~~

Nguyên nhân: `2147483648` không nằm trong miền `int` dương. Muốn từ chối trường hợp này có `Math.negateExact(x)` và `Math.absExact(x)` (Java 17+). Nếu chỉ cần độ lớn và chấp nhận `long`, dùng:

~~~java
long exactAbs = Math.abs((long) Integer.MIN_VALUE);
// 2147483648
~~~

Ép sang `long` phải diễn ra **trước** phép lấy trị tuyệt đối. `Math.abs(Integer.MIN_VALUE)` có thể trả số âm, nên không được coi `Math.abs` là phép kiểm tra rằng giá trị chắc chắn không âm.

### 5.3. Nhân, bình phương và biểu thức trung gian

~~~java
int x = 50_000;

long wrongSquare = x * x;         // -1794967296 rồi nới sang long
long correctSquare = (long) x * x; // 2500000000
~~~

Đối với phép nhân hai `int`, `Math.multiplyFull(x, x)` trả kết quả `long` đầy đủ trong Java 17. Với phép nhân `long`, kết quả có thể vượt 64 bit; `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))` là oracle phù hợp.

`BigInteger` có `shiftLeft` để kiểm tra phép dịch cần giữ toàn bộ bit. Trong khi đó, toán tử `<<` trên primitive luôn giữ độ rộng kiểu và có thể bỏ bit cao; không nên dựa vào `Math.addExact` để phát hiện mất bit ở phép dịch.

### 5.4. Tích lũy trong vòng lặp và stream

~~~java
int sum = 0;
for (int value : values) {
    sum = Math.addExact(sum, value);
}
~~~

Đoạn mã trên nằm trong một phương thức có biến `int[] values`. Nó phát hiện tràn tại **từng bước tích lũy**.

Một oracle độc lập có thể dùng:

~~~java
BigInteger reference = BigInteger.ZERO;
for (int value : values) {
    reference = reference.add(BigInteger.valueOf(value));
}
~~~

Cần phân biệt hai mục tiêu:

- Nếu yêu cầu “không có bất kỳ phép cộng trung gian nào được phép tràn”, phép tính kiểm tra từng bước phù hợp.
- Nếu chỉ yêu cầu “**tổng toán học cuối cùng** nằm trong miền int”, việc tích lũy `int` có thể tràn ở giữa rồi quay về giá trị hợp lệ khi có số âm bù lại. Oracle `BigInteger` vẫn biết tổng thực cuối cùng. Tùy hợp đồng, một quy tắc có thể chặt hơn quy tắc kia.

Ví dụ mảng `{Integer.MAX_VALUE, 1, -1}` có tổng toán học cuối cùng bằng `Integer.MAX_VALUE`, nhưng cách cộng kiểm tra từng bước sẽ thất bại tại phần tử thứ hai. Cần xác định rõ ứng dụng phải ngăn tràn **trong mọi bước** hay chỉ chứng minh phạm vi của **kết quả cuối**.

`IntStream.sum()` trả `int` và có thể tràn. `mapToLong(x -> x).sum()` tăng phạm vi cho nguồn `int` nhưng tổng cực lớn vẫn có thể vượt `long`. Nếu cần tổng toán học tùy ý, tích lũy bằng `BigInteger`.

## 6. Ví dụ Java 17+ hoàn chỉnh: so sánh kết quả với oracle

Tạo file `OverflowOracleDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.Random;

public class OverflowOracleDemo {
    private static final BigInteger LONG_MIN =
            BigInteger.valueOf(Long.MIN_VALUE);
    private static final BigInteger LONG_MAX =
            BigInteger.valueOf(Long.MAX_VALUE);

    private static boolean fitsLong(BigInteger value) {
        return value.compareTo(LONG_MIN) >= 0
                && value.compareTo(LONG_MAX) <= 0;
    }

    private static void verifyRandomAdd() {
        Random rng = new Random(2026L);

        for (int i = 0; i < 10_000; i++) {
            long left = rng.nextLong();
            long right = rng.nextLong();
            BigInteger oracle = BigInteger.valueOf(left)
                    .add(BigInteger.valueOf(right));
            boolean fits = fitsLong(oracle);

            try {
                long got = Math.addExact(left, right);
                if (!fits || !BigInteger.valueOf(got).equals(oracle)) {
                    throw new AssertionError("undetected overflow");
                }
            } catch (ArithmeticException ex) {
                if (fits) {
                    throw new AssertionError("false overflow");
                }
            }
        }

        System.out.println("random additions: 10000 PASS");
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("int wrapped: " + (max + 1));
        System.out.println("int oracle: "
                + BigInteger.valueOf(max).add(BigInteger.ONE));

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.addExact: ArithmeticException");
        }

        System.out.println("widen after: " + (long) (max + 1));
        System.out.println("widen before: " + ((long) max + 1));

        long top = Long.MAX_VALUE;
        System.out.println("long wrapped multiply: " + (top * 2));
        System.out.println("long oracle multiply: "
                + BigInteger.valueOf(top).multiply(BigInteger.TWO));

        try {
            Math.multiplyExact(top, 2L);
        } catch (ArithmeticException ex) {
            System.out.println("Math.multiplyExact: ArithmeticException");
        }

        System.out.println("long MIN / -1: "
                + (Long.MIN_VALUE / -1L));
        System.out.println("BigInteger MIN / -1: "
                + BigInteger.valueOf(Long.MIN_VALUE).negate());

        verifyRandomAdd();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OverflowOracleDemo.java
java OverflowOracleDemo
~~~

Kết quả:

~~~text
int wrapped: -2147483648
int oracle: 2147483648
Math.addExact: ArithmeticException
widen after: -2147483648
widen before: 2147483648
long wrapped multiply: -2
long oracle multiply: 18446744073709551614
Math.multiplyExact: ArithmeticException
long MIN / -1: -9223372036854775808
BigInteger MIN / -1: 9223372036854775808
random additions: 10000 PASS
~~~

Cách đọc kết quả:

- `int wrapped` là kết quả primitive đã tràn; `int oracle` cho kết quả toán học đúng.
- `Math.addExact` phát hiện tràn thay vì trả số sai.
- `widen after` thực hiện mở rộng **sau** khi cộng `int`, nên quá muộn; `widen before` chuyển một toán hạng sang `long` trước khi tính.
- `long wrapped multiply` bằng `-2` dù kết quả thật dương rất lớn.
- `Long.MIN_VALUE / -1` chứng minh phép chia nguyên có một trường hợp tràn đặc biệt mà phép chia thông thường không báo.
- `verifyRandomAdd` tạo 10.000 cặp `long` từ seed cố định. Với từng cặp, oracle `BigInteger` quyết định kết quả có vừa long không; test yêu cầu `Math.addExact` trả đúng số khi vừa và ném ngoại lệ khi vượt miền. Dòng `PASS` chỉ được in sau khi toàn bộ vòng lặp kết thúc không có assertion thất bại.

Đây là **chương trình minh họa kiểm thử logic**, không phải benchmark tốc độ. `BigInteger` thường tốn tài nguyên hơn primitive, nhưng trong test nó ưu tiên sự chính xác và tính độc lập của oracle.

## 7. Kiểm thử biên trước, rồi mới kiểm thử ngẫu nhiên

Random testing có ích nhưng không thay thế kiểm thử ranh giới. Những giá trị gây tràn thường tập trung ở các mép của miền; một bộ kiểm thử nên bắt đầu bằng các case xác định được mong đợi.

| Biểu thức | Kết quả toán học | `int`/`long` thông thường | Kỳ vọng với phép kiểm tra exact |
| --- | --- | --- | --- |
| `Integer.MAX_VALUE + 1` | `2147483648` | `Integer.MIN_VALUE` | `Math.addExact` ném lỗi |
| `Integer.MIN_VALUE - 1` | `-2147483649` | `Integer.MAX_VALUE` | `Math.subtractExact` ném lỗi |
| `50_000 * 50_000` khi cả hai là int | `2500000000` | `-1794967296` | `Math.multiplyExact(int,int)` ném lỗi |
| `Long.MAX_VALUE + 1L` | `9223372036854775808` | `Long.MIN_VALUE` | `Math.addExact(long,long)` ném lỗi |
| `Long.MAX_VALUE * 2L` | `18446744073709551614` | `-2` | `Math.multiplyExact(long,long)` ném lỗi |
| `-Integer.MIN_VALUE` | `2147483648` | `Integer.MIN_VALUE` | `Math.negateExact` ném lỗi |
| `Long.MIN_VALUE / -1L` | `9223372036854775808` | `Long.MIN_VALUE` | Phải xử lý trường hợp đặc biệt hoặc kiểm bằng oracle |
| `Integer.MAX_VALUE + 0` | `2147483647` | Đúng | `Math.addExact` trả kết quả |
| `Long.MIN_VALUE * 1L` | `Long.MIN_VALUE` | Đúng | `Math.multiplyExact` trả kết quả |

Test thêm các cặp `MIN_VALUE`, `MAX_VALUE`, `-1`, `0`, `1`, `2`, số gần ranh giới, giá trị âm/dương đối xứng và số lớn. Với phép chia, phải phân biệt **chia cho 0** và **tràn `MIN_VALUE / -1`**, vì đây là hai điều kiện lỗi khác nhau.

### 7.1. Dùng property-based testing với BigInteger

Một thuộc tính (*property*) hữu ích cho hàm cộng long kiểm tra tràn:

> Với mọi `a` và `b`, gọi `BigInteger.valueOf(a).add(BigInteger.valueOf(b))` được oracle. Nếu oracle nằm trong khoảng `Long.MIN_VALUE..Long.MAX_VALUE`, hàm cần trả đúng oracle; nếu nằm ngoài, hàm phải báo tràn theo hợp đồng.

Áp dụng tương tự cho trừ/nhân. Có thể lấy dữ liệu bằng `Random` với seed cố định như chương trình mẫu để tái tạo lỗi. Tốt hơn nữa, kết hợp một tập giá trị biên được chọn thủ công; các cặp ngẫu nhiên `long` có thể gặp tràn cộng nhưng dễ bỏ qua một số tình huống quan trọng như `MIN_VALUE / -1` nếu không cố ý tạo.

Nếu dùng thư viện property-testing, mỗi phép thử thất bại cần ghi đủ toán hạng, operation, giá trị oracle và exception để dễ tái lập. Thu hẹp (*shrinking*) giúp tìm phản ví dụ đơn giản hơn, nhưng không làm mất ý nghĩa của kiểm thử biên.

### 7.2. Phải xác định hợp đồng trước khi test

Không phải ứng dụng nào cũng cần ném lỗi khi vượt miền:

- **Checked arithmetic:** tràn là lỗi; dùng `Math.*Exact` và kỳ vọng `ArithmeticException`.
- **Wraparound có chủ đích:** một số thuật toán hash/bit manipulation định nghĩa modulo \(2^{32}\) hoặc \(2^{64}\); oracle vẫn hữu ích nhưng cần so **bit thấp** theo đặc tả, thay vì luôn yêu cầu ném lỗi.
- **Saturating arithmetic:** kẹp kết quả ở min/max; oracle xác định trước khi kẹp rồi kiểm kết quả cuối.
- **Arbitrary precision:** giữ giá trị `BigInteger` hoặc kiểu thích hợp, không ép về `long`.

Việc so `long actual` với `BigInteger.longValue()` chỉ kiểm tra phần bit thấp và **không phát hiện tràn** nếu yêu cầu là số học chính xác. Cách so ấy chỉ hợp lệ khi contract thực sự là modulo/wraparound.

## 8. Phát hiện tràn khi ép kiểu và tổng hợp nhiều bước

### 8.1. Ép long xuống int

~~~java
long input = 2_147_483_648L;

int silent = (int) input; // -2147483648, bỏ bit cao

try {
    int checked = Math.toIntExact(input);
} catch (ArithmeticException ex) {
    // input nằm ngoài miền int
}
~~~

`Math.toIntExact` chỉ kiểm tra **chuyển `long` → `int`**. Nếu kết quả đã tràn khi tính trong `long` trước đó, nó không thể phục hồi giá trị gốc.

`BigInteger.intValueExact()` cũng phát hiện giá trị ngoài miền int:

~~~java
BigInteger large = BigInteger.valueOf(Integer.MAX_VALUE)
        .add(BigInteger.ONE);

large.intValue();      // -2147483648: mất bit
large.intValueExact(); // ArithmeticException
~~~

### 8.2. Tìm lỗi ở đâu trong chuỗi tính toán

Một quy trình chẩn đoán có thể đi theo các bước:

1. **Xác định kiểu của từng toán hạng ở thời điểm phép toán chạy**: hai `int` cộng trước khi gán vào `long` vẫn cộng theo `int`.
2. **Ghi lại toán hạng gốc trước phép toán nghi ngờ**, không chỉ giá trị đầu ra sau khi đã tràn.
3. **Tính oracle bằng BigInteger trên các toán hạng gốc**, tách khỏi mã sản phẩm đang kiểm thử.
4. **So cận kiểu đích** và xác định bước đầu tiên vượt miền.
5. **Thay toán tử bằng API exact hoặc đổi mô hình kiểu** nếu hợp đồng yêu cầu từ chối tràn.
6. **Thêm regression test** với bộ số gây lỗi và những giá trị sát biên.

Cẩn thận khi debug bằng log: nếu log chỉ in `sum` đã bị wrap, việc thấy số âm có thể gây hiểu nhầm rằng dữ liệu nguồn đã âm. Log toán hạng gốc và ngữ nghĩa đơn vị/range giúp truy ngược nguyên nhân.

### 8.3. Tính toán kích thước và chỉ số

Ví dụ sai kinh điển là:

~~~java
int mid = (left + right) / 2;
~~~

Khi `left` và `right` là chỉ số int rất lớn, phép cộng có thể tràn dù trung điểm toán học vẫn hợp lệ. Với `0 <= left <= right`, biểu thức:

~~~java
int mid = left + (right - left) / 2;
~~~

tránh phép cộng trực tiếp hai chỉ số lớn trong trường hợp điều kiện đã được giữ. Nhưng **đừng áp công thức này ngoài điều kiện** vì `right - left` cũng có thể tràn khi chỉ số có dấu khác thường. Nếu cần hỗ trợ mọi giá trị int, có thể nâng sang long trước:

~~~java
long midWide = ((long) left + (long) right) / 2;
~~~

Kết quả khi chia hai và làm tròn có thể khác nếu có số âm, nên định nghĩa lại hợp đồng trung điểm khi không còn dùng chỉ số không âm. Sửa overflow phải đi kèm bảo toàn **ngữ nghĩa tính toán**.

## 9. Các lỗi phổ biến khi tạo phép tính tham chiếu

1. **Chuyển sang BigInteger sau khi đã tràn:** `BigInteger.valueOf(a * b)` không còn là oracle cho tích chính xác nếu `a*b` chạy bằng long.
2. **Ép về long/int sau tính toán mà không dùng Exact:** `big.longValue()` và `big.intValue()` có thể mất bit cao.
3. **Cho rằng mọi phép cộng có thể sửa bằng cast ở cuối:** `(long)(a+b)` tính `a+b` bằng int trước khi cast.
4. **Chỉ kiểm tra số dương:** âm dưới `MIN_VALUE` cũng tràn, còn `MIN_VALUE` đổi dấu/trị tuyệt đối là trường hợp đặc biệt.
5. **Bỏ qua phép chia `MIN_VALUE / -1`:** kết quả primitive đã tràn mà không ném ngoại lệ.
6. **Nhầm overflow với rounding của float/double:** BigInteger oracle áp dụng cho số nguyên chính xác; số thực cần chiến lược test và sai số thích hợp.
7. **Dùng lại chính công thức bị kiểm thử làm oracle:** hai phía có cùng lỗi sẽ cùng sai. Tách đường tính tham chiếu, dùng kiểu rộng/độ chính xác độc lập.
8. **Random test mà không có case biên:** xác suất chạm đúng `Integer.MIN_VALUE`, `Long.MAX_VALUE` hoặc tổ hợp đặc biệt có thể rất nhỏ.
9. **Chỉ kiểm kết quả cuối khi hợp đồng cấm tràn trung gian:** tổng cuối có thể nằm trong miền sau khi các tổng từng bước từng vượt miền.
10. **Báo lỗi sau khi đã dùng giá trị hỏng:** kiểm tra tràn tại chỗ tạo giá trị, trước khi dùng làm chỉ số, kích thước, giới hạn hoặc thanh toán.
11. **Đổi sang BigInteger khắp production không có chủ đích:** cần đánh giá hiệu năng/bộ nhớ và khả năng tương tác. Nếu phạm vi dữ liệu luôn phải nằm trong long, phép tính exact thường đơn giản hơn.
12. **Ngộ nhận BigInteger tuyệt đối không có giới hạn thực tế:** nó không bị giới hạn 32/64 bit trong toán học thông thường, nhưng bộ nhớ, kích thước mảng và thời gian tính toán vẫn hữu hạn.

## 10. Tự kiểm tra

**Câu 1.** Vì sao `long result = Integer.MAX_VALUE + 1;` lại có thể nhận số âm?

**Đáp án:** Hai toán hạng được cộng theo `int` trước khi gán vào `long`. Cộng tràn rồi mới mở rộng. Viết `(long) Integer.MAX_VALUE + 1` để phép cộng chạy bằng long.

**Câu 2.** Kết quả của `BigInteger.valueOf(Long.MAX_VALUE * 2L)` có phải oracle đúng không?

**Đáp án:** Không. Phép nhân long đã tràn thành `-2` trước khi chuyển. Oracle đúng là `BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.TWO)`.

**Câu 3.** Khi nào `Math.addExact(a,b)` trả số, khi nào ném lỗi?

**Đáp án:** Trả chính xác kết quả nếu còn trong phạm vi kiểu của overload được gọi; ném `ArithmeticException` nếu phép cộng vượt phạm vi đó.

**Câu 4.** `Long.MIN_VALUE / -1L` có ném ngoại lệ không?

**Đáp án:** Không; toán tử phép chia long trả `Long.MIN_VALUE`. Kết quả toán học lớn hơn `Long.MAX_VALUE`, nên phải kiểm trường hợp này hoặc dùng BigInteger nếu cần tính chính xác.

**Câu 5.** Có thể dùng `BigInteger.longValue()` để phát hiện một số quá lớn cho long không?

**Đáp án:** Không. Dùng `longValueExact()` hoặc so với hai cận để phát hiện tràn; `longValue()` có thể bỏ bit cao.

**Câu 6.** Mảng `{Integer.MAX_VALUE, 1, -1}` có tổng toán học cuối là bao nhiêu và vì sao test dùng `Math.addExact` có thể thất bại?

**Đáp án:** Tổng chính xác cuối bằng `Integer.MAX_VALUE`, nhưng tổng trung gian sau phần tử thứ hai vượt phạm vi int. Test từ chối mọi tràn trung gian sẽ phát hiện ngay bước đó; test chỉ kiểm tổng toán học cuối cần một oracle khác.

**Câu 7.** Nếu yêu cầu thực sự là arithmetic modulo \(2^{32}\), oracle nên làm gì?

**Đáp án:** Tính kết quả nguyên chính xác bằng BigInteger, sau đó xác định 32 bit thấp theo hợp đồng. Khi hợp đồng cố ý wrap, việc `Math.addExact` ném lỗi không nhất thiết là hành vi mong muốn.

## 11. Tài liệu chính thức

- [`BigInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên chính xác tùy ý, `valueOf`, `add`, `multiply`, `intValueExact`, `longValueExact`.
- [`Math` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `absExact`, `negateExact`, `toIntExact`.
- [Java Language Specification 17, Integer Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): ngữ nghĩa toán tử số nguyên, chuyển kiểu, toán tử số học và trường hợp chia đặc biệt.
- [`Integer` và `Long` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): giới hạn kiểu số nguyên; xem thêm [`Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).

**Ghi nhớ:** Khi kiểm thử tràn `int`/`long`, tạo kết quả tham chiếu bằng `BigInteger` **trước khi tính**, xác minh miền kiểu đích và đối chiếu hành vi expected/actual. Trong logic sản phẩm, dùng `Math.*Exact` nếu muốn báo tràn ngay; khi giá trị hợp lệ vượt 64 bit thì giữ `BigInteger` thay vì ép về primitive. Kiểm thử các giá trị biên, phép chia `MIN_VALUE / -1` và lỗi “ép kiểu sau phép toán” để tránh những sai lệch âm thầm.
