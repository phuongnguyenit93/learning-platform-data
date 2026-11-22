# `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` và `valueOf` trong Java

## 1. Tổng quan: số nguyên lớn và cách tạo giá trị

`java.math.BigInteger` biểu diễn **số nguyên có dấu với độ chính xác tùy ý** (*arbitrary-precision integer*). Khác với `int` (32 bit) và `long` (64 bit), số chữ số/bit của một `BigInteger` không bị cố định ở 32 hoặc 64 bit. Giới hạn thực tế đến từ bộ nhớ, phạm vi mà API/JVM hỗ trợ và tài nguyên tính toán.

Một `BigInteger` là **đối tượng bất biến** (*immutable*). Mọi thao tác như `add`, `multiply`, `pow` trả về giá trị kết quả mà không sửa giá trị ban đầu.

Để không phải tạo lại các số nguyên rất thường dùng, Java cung cấp sẵn các hằng `public static final`:

```java
import java.math.BigInteger;

BigInteger zero = BigInteger.ZERO; // 0
BigInteger one  = BigInteger.ONE;  // 1
BigInteger two  = BigInteger.TWO;  // 2
BigInteger ten  = BigInteger.TEN;  // 10
```

Với một số nguyên `long` khác, dùng:

```java
BigInteger n = BigInteger.valueOf(123456789L);
```

**Hai nguyên tắc cốt lõi:**

1. Dùng các hằng `ZERO`, `ONE`, `TWO`, `TEN` khi đúng giá trị và làm mã dễ đọc; dùng `valueOf(long)` khi đầu vào đã là một giá trị nguyên vừa miền `long`.
2. Không dùng toán tử `==` để kiểm tra **hai đối tượng `BigInteger` có bằng nhau về giá trị không**. Dùng `equals`, `compareTo` hoặc `signum` theo ý nghĩa bài toán.

Bài này tập trung vào **các hằng số và factory `valueOf`**, đồng thời trình bày đủ các phép thao tác và bẫy cần biết để dùng chúng chính xác.

## 2. Bốn hằng số có sẵn

| Hằng số | Giá trị toán học | Ứng dụng điển hình |
| --- | ---: | --- |
| `BigInteger.ZERO` | 0 | Khởi tạo tổng, kết quả rỗng, phần tử đơn vị của phép cộng, kiểm tra số 0 |
| `BigInteger.ONE` | 1 | Phần tử đơn vị của phép nhân, bắt đầu tích, tăng/giảm một đơn vị |
| `BigInteger.TWO` | 2 | Thuật toán nhị phân, tính lũy thừa cơ số hai, diễn đạt hệ số 2 |
| `BigInteger.TEN` | 10 | Lũy thừa 10, tính toán số nguyên theo cơ số thập phân, quy đổi đơn vị |

Ví dụ trong một phương thức Java:

```java
System.out.println(BigInteger.ZERO); // 0
System.out.println(BigInteger.ONE);  // 1
System.out.println(BigInteger.TWO);  // 2
System.out.println(BigInteger.TEN);  // 10
```

**Lưu ý về phiên bản:** `BigInteger.TWO` xuất hiện từ **Java 9**. Trong Java 17 trở lên, cả bốn hằng đều dùng được. Nếu buộc hỗ trợ Java 8, thay `TWO` bằng `BigInteger.valueOf(2)` hoặc biểu thức tương đương.

Mỗi hằng là một tham chiếu `public static final` tới giá trị `BigInteger` bất biến. `final` ở đây ngăn gán lại trường tĩnh; đặc tính **bất biến của chính `BigInteger`** ngăn sửa giá trị số bên trong.

Không được hiểu `ZERO`, `ONE` hay `TEN` giống biến toàn cục có thể cộng trừ trực tiếp:

```java
BigInteger sum = BigInteger.ZERO;
sum = sum.add(BigInteger.ONE); // sum mang giá trị 1

System.out.println(sum);             // 1
System.out.println(BigInteger.ZERO); // 0: hằng ban đầu không đổi
```

Biểu thức `sum.add(BigInteger.ONE)` tạo ra hoặc trả về một đối tượng biểu diễn kết quả tùy tối ưu của thư viện; dù cách triển khai nào, **giá trị `sum` ban đầu không bị sửa** cho đến khi ta gán lại biến `sum`.

### Hằng `ZERO` có giá trị khác tham chiếu `null`

```java
BigInteger count = BigInteger.ZERO; // Số 0 hợp lệ
BigInteger unknown = null;          // Không có đối tượng
```

`ZERO` là một giá trị số thật; `null` không phải số 0 và không gọi được phương thức trên nó. Ví dụ `unknown.add(BigInteger.ONE)` sẽ ném `NullPointerException`. Dùng `BigInteger.ZERO` làm mặc định chỉ khi nghiệp vụ cho phép coi dữ liệu thiếu là 0.

## 3. `BigInteger.valueOf(long)` là gì?

Chữ ký API:

```java
public static BigInteger valueOf(long val)
```

Phương thức nhận **một giá trị nguyên kiểu `long`**, rồi trả về `BigInteger` mang **chính xác giá trị đó**:

```java
BigInteger a = BigInteger.valueOf(0L);
BigInteger b = BigInteger.valueOf(42L);
BigInteger c = BigInteger.valueOf(-17L);
BigInteger d = BigInteger.valueOf(Long.MIN_VALUE);
```

`valueOf(long)` không ném overflow vì đầu vào đã là một `long` hợp lệ. **Mọi giá trị `long`**, kể cả `Long.MIN_VALUE` và `Long.MAX_VALUE`, đều biểu diễn chính xác bằng `BigInteger`.

Ví dụ:

```java
BigInteger min = BigInteger.valueOf(Long.MIN_VALUE);
BigInteger max = BigInteger.valueOf(Long.MAX_VALUE);

System.out.println(min); // -9223372036854775808
System.out.println(max); // 9223372036854775807
```

Lời gọi với literal `int` hợp lệ nhờ **widening primitive conversion** từ `int` sang `long`:

```java
BigInteger x = BigInteger.valueOf(100); // int literal được chuyển sang long
```

Không có overload `BigInteger.valueOf(double)` trong API này. Các ví dụ sau **không** được phép:

```java
// BigInteger.valueOf(3.14);  // Lỗi biên dịch: double không chuyển ngầm sang long
// BigInteger.valueOf("42");  // Lỗi biên dịch: String không phải long
```

Với chuỗi, dùng constructor `new BigInteger("42")`. Với decimal có phần lẻ hoặc đầu vào dấu phẩy động, cần chọn **chính sách làm tròn và tính chính xác** tường minh trước khi đổi sang số nguyên.

### Dùng `valueOf` để tận dụng tái sử dụng đối tượng

Tài liệu `valueOf` khuyến nghị static factory thay cho constructor nhận `long` vì nó **có thể tái sử dụng những `BigInteger` thường gặp**. Điều đó có nghĩa JVM/thư viện được tự do tối ưu cấp phát khi thích hợp.

Nhưng **không có nghĩa hai lần `BigInteger.valueOf(100)` luôn phải trả cùng tham chiếu trên mọi triển khai**. Điều cần dựa vào là **giá trị** của kết quả:

```java
BigInteger a = BigInteger.valueOf(100);
BigInteger b = BigInteger.valueOf(100);

System.out.println(a.equals(b)); // true
```

Không dựa vào `a == b`. Việc factory trả đúng instance của `BigInteger.ZERO`, `ONE` hoặc instance cache khác không phải hợp đồng so sánh giá trị nghiệp vụ.

### Khi nào nên dùng hằng, khi nào dùng `valueOf`?

- Nếu viết thuật toán với giá trị *cố định* `0`, `1`, `2`, `10`, các hằng thường sáng rõ và tránh lời gọi factory thừa.
- Nếu đầu vào là `long` (tham số hàm, dữ liệu từ parser nguyên có giới hạn hoặc phép tính không overflow), `BigInteger.valueOf(value)` là lựa chọn chuẩn.
- Nếu đầu vào là số nguyên thập phân **có thể vượt `long`**, phải parse từ chuỗi hoặc tính trực tiếp bằng `BigInteger` — **không** ép tạm về `long` rồi `valueOf`.
- Nếu cần kết quả sau phép toán `BigInteger`, dùng các phương thức `add`, `multiply`, `pow`... thay vì quay lại `long`.

## 4. Điều `valueOf` không làm được: mở rộng dữ liệu đã overflow

Cạm bẫy lớn nhất là làm toán bằng `long` trước rồi mới chuyển sang `BigInteger`:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1L;           // Tràn số nguyên long: trở thành Long.MIN_VALUE
BigInteger wrong = BigInteger.valueOf(overflowed);

System.out.println(wrong); // -9223372036854775808
```

`BigInteger.valueOf` đã thực hiện **đúng** việc chuyển giá trị `long` nhận được. Nó không biết giá trị trước phép cộng từng là `Long.MAX_VALUE`, và không khôi phục được bit đã mất.

Cách đúng là **nâng lên `BigInteger` trước khi phép cộng vượt miền**:

```java
BigInteger correct =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

System.out.println(correct); // 9223372036854775808
```

Nói cách khác:

\[
\operatorname{valueOf}(\text{phép toán long đã overflow})
\ne
\text{phép toán BigInteger trực tiếp}.
\]

Vấn đề tương tự xảy ra với phép nhân và lũy thừa:

```java
long a = 4_000_000_000L;
long b = 4_000_000_000L;

// long product = a * b; // Vượt Long.MAX_VALUE; overflow
BigInteger product = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));

System.out.println(product); // 16000000000000000000
```

Không có “overflow theo miền `long`” trong kết quả `BigInteger` hợp lệ; giới hạn vẫn tồn tại ở tài nguyên và hạn chế triển khai, nhưng không cố định 64 bit.

## 5. Số vượt miền `long`: dùng constructor từ chuỗi

`BigInteger.valueOf` chỉ nhận một `long`. Với số nguyên lớn hơn miền `long`, dùng:

```java
BigInteger huge = new BigInteger("100000000000000000000000000000000000000");
```

Constructor này đọc chuỗi thập phân (cơ số 10) với dấu tùy chọn và không ép qua `double` hoặc `long`.

Ví dụ:

```java
BigInteger beyondLong = new BigInteger("9223372036854775808");

System.out.println(beyondLong);
// 9223372036854775808
```

Với hệ cơ số khác, dùng `new BigInteger(text, radix)`:

```java
BigInteger hex = new BigInteger("FF", 16);
BigInteger binary = new BigInteger("1010", 2);

System.out.println(hex);    // 255
System.out.println(binary); // 10
```

`radix` phải trong phạm vi được hỗ trợ, thường là `Character.MIN_RADIX` (2) tới `Character.MAX_RADIX` (36). Dữ liệu sai cú pháp hoặc không hợp lệ theo radix gây `NumberFormatException`.

### Phân biệt parse và chuyển kiểu

| Đầu vào | API phù hợp | Chú ý |
| --- | --- | --- |
| `long` | `BigInteger.valueOf(long)` | Giữ chính xác toàn miền `long` |
| `int` | `BigInteger.valueOf(intValue)` | Java nâng `int` sang `long` |
| Chuỗi số nguyên thập phân | `new BigInteger(text)` | Không cần thông qua `long` |
| Chuỗi số nguyên hệ 16 | `new BigInteger(text, 16)` | Ví dụ `"FF"` → 255 |
| Giá trị `BigInteger` đã có | Dùng trực tiếp | Không tạo lại nếu không cần |
| Số decimal như `"1.5"` | `BigDecimal` trước, rồi chính sách nguyên hóa nếu cần | `new BigInteger("1.5")` không hợp lệ |
| `double` | Không dùng `BigInteger.valueOf(double)` | Cần xét mất chính xác và quy tắc làm tròn |

Nhập `"9223372036854775808"` bằng `Long.parseLong` sẽ thất bại vì vượt miền `long`, dù `BigInteger` vẫn đọc được. Đây là lý do không dùng `Long.parseLong` làm “bước đệm” cho dữ liệu nguyên lớn.

## 6. Bất biến và phép tính với `ZERO`, `ONE`, `TWO`, `TEN`

Các phương thức số học của `BigInteger` trả về kết quả mới về **mặt giá trị**, không sửa toán hạng:

```java
BigInteger x = BigInteger.TEN;
BigInteger y = x.add(BigInteger.ONE);

System.out.println(x); // 10
System.out.println(y); // 11
```

Một số phép thường dùng:

| Phép toán | Mã Java | Kết quả |
| --- | --- | --- |
| `7 + 1` | `BigInteger.valueOf(7).add(BigInteger.ONE)` | `8` |
| `7 - 1` | `BigInteger.valueOf(7).subtract(BigInteger.ONE)` | `6` |
| `7 × 2` | `BigInteger.valueOf(7).multiply(BigInteger.TWO)` | `14` |
| `7 × 10` | `BigInteger.valueOf(7).multiply(BigInteger.TEN)` | `70` |
| `2^10` | `BigInteger.TWO.pow(10)` | `1024` |
| `10^6` | `BigInteger.TEN.pow(6)` | `1000000` |
| Dịch trái 5 bit từ 1 | `BigInteger.ONE.shiftLeft(5)` | `32` |
| Đổi dấu của 10 | `BigInteger.TEN.negate()` | `-10` |
| Trị tuyệt đối của -10 | `BigInteger.TEN.negate().abs()` | `10` |

`ZERO` là phần tử trung hòa của phép cộng: \(n+0=n\). `ONE` là phần tử trung hòa của phép nhân: \(n\times1=n\). Nhưng không nên suy từ điều này ra đảm bảo **cùng tham chiếu** khi thư viện tối ưu trả về một trong hai toán hạng; quan hệ về số phải kiểm tra qua `equals`.

Ví dụ tích lũy:

```java
BigInteger sum = BigInteger.ZERO;

for (long value : new long[] { 1, 2, 3, 4 }) {
    sum = sum.add(BigInteger.valueOf(value));
}

System.out.println(sum); // 10
```

Cần có phép gán lại `sum = sum.add(...)`. Nếu chỉ gọi `sum.add(...)` mà không nhận kết quả, giá trị lưu trong `sum` không đổi.

### Lũy thừa và trường hợp `0^0`

`BigInteger.pow(int exponent)` nhận số mũ kiểu `int` **không âm**:

```java
System.out.println(BigInteger.TWO.pow(10)); // 1024
System.out.println(BigInteger.TEN.pow(6));  // 1000000
System.out.println(BigInteger.ZERO.pow(0)); // 1
```

Theo quy ước của API, `pow(0)` trả `ONE`, kể cả khi cơ số bằng `ZERO`. Đây là **quy ước lập trình của phép lũy thừa số nguyên**; trong các ngữ cảnh toán học, biểu thức `0^0` có thể được quy định khác hoặc để không xác định. Đừng áp dụng quy ước API mà không kiểm tra mô hình toán học của ứng dụng.

Nếu `exponent < 0`, `BigInteger.pow` ném `ArithmeticException`: không thể biểu diễn `2^-1` dưới dạng số nguyên `BigInteger`. Nếu số mũ quá lớn, phép tính có thể tốn nhiều bộ nhớ/thời gian; phải validate giới hạn công việc với đầu vào không tin cậy.

## 7. So sánh giá trị: `equals`, `compareTo`, `signum` thay vì `==`

**`BigInteger` là đối tượng tham chiếu**, không phải primitive wrapper có unboxing tự động sang `long`.

```java
BigInteger a = BigInteger.valueOf(10);
BigInteger b = BigInteger.TEN;

boolean equal = a.equals(b); // true
```

Đối với hai tham chiếu `BigInteger`:

- `a == b` kiểm tra **cùng đối tượng**.
- `a.equals(b)` kiểm tra **cùng giá trị số nguyên**.
- `a.compareTo(b)` trả số âm, 0, hoặc số dương tương ứng `a < b`, `a = b`, `a > b`.
- `a.signum()` trả `-1`, `0` hoặc `1` tùy dấu giá trị.

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(10);
BigInteger b = BigInteger.TEN;

System.out.println(a.equals(b));     // true
System.out.println(a.compareTo(b));  // 0
System.out.println(a.signum());      // 1
```

Không sử dụng `==` ngay cả khi một lần thử cho thấy `BigInteger.valueOf(10) == BigInteger.TEN` là `true` trong JVM đang chạy. Cache/reuse là lựa chọn triển khai, **không phải định nghĩa bằng nhau của số nguyên**.

### Kiểm tra 0 đúng cách

```java
BigInteger n = BigInteger.valueOf(0);

boolean isZero = n.signum() == 0;
boolean alsoZero = n.equals(BigInteger.ZERO);
```

Cả hai đều kiểm tra **giá trị** nếu `n` không `null`. Với `n == null`, gọi `signum()` hoặc `equals()` sẽ ném `NullPointerException`. Nếu phải xử lý nullable data:

```java
import java.util.Objects;

boolean zeroIfPresent = Objects.equals(n, BigInteger.ZERO);
```

Điều kiện này trả `false` khi `n == null`, và `true` khi `n` có giá trị số 0. Nếu nghiệp vụ cần phân biệt missing với zero, hãy kiểm tra `n == null` riêng.

### So sánh với primitive

Không có autounboxing từ `BigInteger` thành `long`:

```java
BigInteger n = BigInteger.TEN;

// boolean wrong = (n == 10); // Không biên dịch: BigInteger và int không tương thích

boolean right = n.equals(BigInteger.valueOf(10));
```

Khi cần so sánh một `BigInteger` với `long`, tạo `BigInteger.valueOf(long)` để so giá trị, hoặc dùng các phép kiểm tra miền/chuyển đổi chính xác thích hợp. Không tự ép `BigInteger` sang `double` rồi so nếu số rất lớn.

## 8. `valueOf` và tối ưu cấp phát: không nhầm với cache wrapper

Mục đích của `valueOf` là tạo một giá trị chính xác và **cho phép thư viện tái sử dụng đối tượng** thường gặp. Không được suy luận rằng `valueOf` luôn tạo mới hoặc luôn trả một instance duy nhất cho mọi số.

Ví dụ:

```java
BigInteger x = BigInteger.valueOf(7);
BigInteger y = BigInteger.valueOf(7);

System.out.println(x.equals(y)); // true
// Không xây dựng logic nghiệp vụ trên x == y.
```

Một vài lưu ý:

1. `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` là **các hằng có sẵn** để truy cập và biểu đạt ý nghĩa, không phải một cơ chế *interning* hoàn chỉnh cho tất cả số.
2. `BigInteger.valueOf(long)` có thể tối ưu tạo đối tượng; không thể dựa vào `==` để suy ra hai số khác nhau.
3. Cũng không nên dùng một `BigInteger` làm **monitor/khóa đồng bộ** với kỳ vọng mỗi lần gọi `valueOf` tạo một khóa độc lập: có thể chia sẻ instance. Hãy dùng một `new Object()` riêng do ứng dụng kiểm soát khi cần khóa.
4. Do `BigInteger` là bất biến, có thể chia sẻ hằng trong nhiều nơi mà không lo các phép `add`/`multiply` làm thay đổi chúng.
5. Hiệu năng của `BigInteger` khác phép toán `long`: số bit lớn hơn làm tăng công việc tính toán và có thể phát sinh đối tượng/áp lực GC. Sử dụng khi cần miền vượt primitive hoặc khi API yêu cầu.

Chọn `BigInteger` vì **tính đúng đắn và miền giá trị**, không vì tin rằng tham chiếu `valueOf` luôn cố định.

## 9. Chuyển từ `BigInteger` về primitive và vấn đề mất dữ liệu

`BigInteger` kế thừa `Number`, có các phương thức lấy primitive:

```java
BigInteger n = BigInteger.valueOf(42);

int asInt = n.intValue();
long asLong = n.longValue();
double asDouble = n.doubleValue();
```

Nhưng các phương thức `intValue()`/`longValue()` **không bảo đảm phát hiện vượt miền**; chúng có thể bỏ các bit cao khi chuyển sang kiểu số nguyên hẹp. `doubleValue()` còn có thể làm tròn hoặc trả vô cực nếu độ lớn quá lớn.

Ví dụ:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

long truncated = beyondLong.longValue();
System.out.println(truncated); // -9223372036854775808
```

Nếu cần **chắc chắn nguyên vẹn**, dùng:

```java
long exact = BigInteger.valueOf(42).longValueExact();
int exactInt = BigInteger.valueOf(42).intValueExact();
```

Với số vượt miền, các phương thức `longValueExact()`/`intValueExact()` ném `ArithmeticException`:

```java
BigInteger tooBig = BigInteger.TWO.pow(80);

// tooBig.longValueExact(); // ArithmeticException
```

Nên bắt hoặc để ngoại lệ phát ra theo hợp đồng của phương thức, thay vì âm thầm mất dữ liệu. Các API exact này đặc biệt quan trọng khi dữ liệu nguyên lớn phải đi vào giao thức hoặc DB chỉ hỗ trợ 64 bit.

**Một chiều chuyển đổi an toàn không bảo đảm chiều ngược lại an toàn:** `BigInteger.valueOf(long)` luôn chính xác, nhưng `someBigInteger.longValue()` có thể làm mất thông tin.

## 10. Demo Java 17 hoàn chỉnh

Lưu chương trình dưới tên `BigIntegerConstantsDemo.java`:

```java
import java.math.BigInteger;

public class BigIntegerConstantsDemo {
    public static void main(String[] args) {
        System.out.println("ZERO = " + BigInteger.ZERO);
        System.out.println("ONE = " + BigInteger.ONE);
        System.out.println("TWO = " + BigInteger.TWO);
        System.out.println("TEN = " + BigInteger.TEN);

        BigInteger fromLong = BigInteger.valueOf(-17L);
        BigInteger fromString = new BigInteger("9223372036854775808");

        System.out.println("valueOf(-17) = " + fromLong);
        System.out.println("string > long max = " + fromString);

        BigInteger next = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("max long + ONE = " + next);

        BigInteger ten = BigInteger.TEN;
        BigInteger eleven = ten.add(BigInteger.ONE);
        System.out.println("TEN after add = " + ten);
        System.out.println("TEN + ONE = " + eleven);

        System.out.println("TWO^10 = " + BigInteger.TWO.pow(10));
        System.out.println("TEN^6 = " + BigInteger.TEN.pow(6));
        System.out.println("TWO^100 = " + BigInteger.TWO.pow(100));
        System.out.println("ZERO^0 = " + BigInteger.ZERO.pow(0));

        BigInteger anotherZero = BigInteger.valueOf(0);
        System.out.println("zero equals = "
                + BigInteger.ZERO.equals(anotherZero));
        System.out.println("zero signum = " + anotherZero.signum());
        System.out.println("compare ZERO to ONE = "
                + BigInteger.ZERO.compareTo(BigInteger.ONE));

        System.out.println("hex FF = " + new BigInteger("FF", 16));

        try {
            BigInteger.TWO.pow(80).longValueExact();
            System.out.println("Unexpected successful narrowing");
        } catch (ArithmeticException ex) {
            System.out.println("longValueExact: ArithmeticException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac BigIntegerConstantsDemo.java
java BigIntegerConstantsDemo
```

Đầu ra:

```text
ZERO = 0
ONE = 1
TWO = 2
TEN = 10
valueOf(-17) = -17
string > long max = 9223372036854775808
max long + ONE = 9223372036854775808
TEN after add = 10
TEN + ONE = 11
TWO^10 = 1024
TEN^6 = 1000000
TWO^100 = 1267650600228229401496703205376
ZERO^0 = 1
zero equals = true
zero signum = 0
compare ZERO to ONE = -1
hex FF = 255
longValueExact: ArithmeticException
```

Đoạn demo không đưa ra giả định về `==` của các đối tượng `BigInteger`, không ép chuỗi số lớn qua `long`, và sử dụng `longValueExact()` để nhận biết dữ liệu không vừa miền khi chuyển ngược về primitive.

## 11. Tình huống thực tế: hằng số giúp code diễn đạt ý nghĩa

### Tính tổng không overflow

```java
BigInteger total = BigInteger.ZERO;

for (long item : new long[] { Long.MAX_VALUE, 1L, 2L }) {
    total = total.add(BigInteger.valueOf(item));
}

System.out.println(total); // 9223372036854775810
```

Ở đây phép cộng **được thực hiện hoàn toàn dưới dạng `BigInteger`**. Dùng `long total` để tích lũy trước rồi chuyển sau sẽ overflow.

### Đếm số cách theo quy luật nhân đôi

```java
BigInteger count = BigInteger.ONE;

for (int i = 0; i < 10; i++) {
    count = count.multiply(BigInteger.TWO);
}

System.out.println(count); // 1024
```

Với n nguyên không âm, `BigInteger.TWO.pow(n)` thường diễn đạt ngắn gọn hơn vòng lặp. Nhưng nhớ `pow` nhận số mũ kiểu `int`; nếu `n` cực lớn, kết quả có thể tốn tài nguyên đáng kể.

### Tạo lũy thừa cơ số 10 chính xác

```java
BigInteger million = BigInteger.TEN.pow(6);
System.out.println(million); // 1000000
```

Không nên thay bằng `(long) Math.pow(10, n)` cho mọi `n` khi muốn **số nguyên chính xác không giới hạn**: `Math.pow` làm việc với `double`, nên có miền/độ chính xác của số thực và phép ép kiểu có thể mất dữ liệu.

### Chuyển một giá trị nguyên theo đơn vị nhỏ nhất

Nếu có tổng số lượng dưới dạng `BigInteger`, có thể nhân chính xác với `TEN`, `TWO` hoặc các hằng khác:

```java
BigInteger units = BigInteger.valueOf(500);
BigInteger subunits = units.multiply(BigInteger.TEN);

System.out.println(subunits); // 5000
```

Với đơn vị đo hay tiền tệ, hệ số quy đổi phải đến từ quy định nghiệp vụ. `TEN` chỉ là số 10, không tự nói “đơn vị tiền nhỏ nhất” hay “đơn vị đo”.

## 12. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `BigInteger.valueOf("123")` | `valueOf` nhận `long`, không nhận `String` | `new BigInteger("123")` |
| Tạo số vượt `long` bằng `valueOf` | Không thể truyền nguyên giá trị vượt miền `long` | Parse từ chuỗi hoặc tính bằng `BigInteger` trước |
| `BigInteger.valueOf(Long.MAX_VALUE + 1L)` | Phép cộng tràn khi còn là `long` | `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` |
| `a == b` với hai `BigInteger` | So tham chiếu chứ không so giá trị | `a.equals(b)` hoặc `a.compareTo(b) == 0` |
| Nghĩ `ZERO` là `null` | `ZERO` là đối tượng mang số 0 | Xử lý trạng thái thiếu dữ liệu riêng |
| `sum.add(n);` không gán lại | `BigInteger` bất biến | `sum = sum.add(n);` |
| `new BigInteger("1.5")` | Constructor cần số nguyên theo radix | Dùng `BigDecimal` nếu có phần lẻ |
| Dùng `longValue()` cho giá trị bất kỳ | Có thể bỏ bit cao | `longValueExact()` để báo lỗi |
| Dùng `doubleValue()` khi cần giá trị nguyên chính xác | `double` có thể làm tròn nguyên lớn | Giữ `BigInteger` hoặc kiểm tra miền/độ chính xác |
| Dựa vào identity do `valueOf` cache | Tái sử dụng đối tượng không phải quy tắc bằng nhau | So sánh giá trị |
| Dùng `Math.pow` rồi ép sang `long` | Số thực có thể mất chữ số/tràn miền | `BigInteger.pow` với số mũ nguyên không âm |
| Mong toán tử `+`, `*` hoạt động với `BigInteger` | Đây không phải primitive số có hỗ trợ toán tử tương ứng | Gọi `add`, `multiply` |
| Dùng `BigInteger.TWO` trong Java 8 | `TWO` chưa có ở Java 8 | Java 9+, hoặc `valueOf(2)` |
| Coi số nguyên lớn là vô hạn tài nguyên | `BigInteger` vẫn có giới hạn bộ nhớ/thời gian | Kiểm tra kích thước đầu vào/số mũ |

### Thêm hai lưu ý về hiệu năng và API

**Không dùng `BigInteger` một cách máy móc cho mọi bộ đếm nhỏ.** Nếu miền giá trị đã biết nằm trọn trong `long` và phép tính có kiểm tra overflow phù hợp, primitive thường gọn và nhanh hơn. Dùng `BigInteger` khi cần miền rộng, tính chính xác vượt giới hạn primitive hoặc giao thức/API yêu cầu.

**Không dùng `BigInteger` làm monitor đồng bộ chia sẻ dựa vào factory.** Do `valueOf` có thể tái sử dụng instance, một đoạn mã khác có thể nhận cùng object; dùng khóa riêng do ứng dụng sở hữu nếu cần đồng bộ.

## 13. Bài tập và đáp án

**Câu 1.** Trong Java 17, bốn hằng `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` biểu diễn số nào? Hằng nào chưa có ở Java 8?

**Đáp án:** Lần lượt 0, 1, 2, 10. `BigInteger.TWO` có từ Java 9 nên không dùng trực tiếp được trên Java 8.

**Câu 2.** Cho:

```java
BigInteger n = BigInteger.TEN;
n.add(BigInteger.ONE);
System.out.println(n);
```

Kết quả là gì, vì sao?

**Đáp án:** `10`. `BigInteger` bất biến; lời gọi `add` trả kết quả nhưng không sửa `n`. Muốn `11`, gán `n = n.add(BigInteger.ONE)`.

**Câu 3.** Làm sao tính chính xác `Long.MAX_VALUE + 1` bằng `BigInteger`?

**Đáp án:**

```java
BigInteger result =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
```

Không thực hiện phép cộng kiểu `long` trước khi gọi `valueOf`.

**Câu 4.** `BigInteger.valueOf(10).equals(BigInteger.TEN)` là `true` hay `false`? Có cần so `==` để chắc chắn không?

**Đáp án:** `true`. `equals` so sánh giá trị nguyên; `==` không cần thiết và không phù hợp để xác định numeric equality.

**Câu 5.** Muốn đọc số `"123456789012345678901234567890"` thành `BigInteger`, dùng API nào?

**Đáp án:** `new BigInteger("123456789012345678901234567890")`; không dùng `Long.parseLong` hay `BigInteger.valueOf(String)`.

**Câu 6.** `BigInteger.TWO.pow(10)` và `BigInteger.TEN.pow(6)` trả gì?

**Đáp án:** Lần lượt `1024` và `1000000`, đều là đối tượng `BigInteger` mang giá trị nguyên chính xác.

**Câu 7.** `BigInteger.ZERO.pow(0)` trả gì theo API Java? Có được áp dụng không điều kiện vào mọi bài toán toán học không?

**Đáp án:** Trả `BigInteger.ONE` (giá trị 1) theo quy ước API. Một số ngữ cảnh toán học xem `0^0` là biểu thức không xác định; phải theo định nghĩa của bài toán.

**Câu 8.** Vì sao `BigInteger.TWO.pow(80).longValue()` không thích hợp nếu ứng dụng cần đủ giá trị? Phương thức thay thế là gì?

**Đáp án:** Giá trị `2^80` vượt miền `long`; `longValue()` có thể bỏ bit cao, gây mất dữ liệu. `longValueExact()` ném `ArithmeticException` để báo rằng không thể chuyển chính xác.

**Câu 9.** Một chương trình luôn gọi `BigInteger.valueOf(7)` rồi so tham chiếu để xác định “hai ID bằng nhau”. Sai ở đâu?

**Đáp án:** Giá trị số là ID có thể dùng được, nhưng so tham chiếu dựa vào tái sử dụng đối tượng là sai thiết kế. So bằng `equals`, hoặc định nghĩa một lớp ID với hợp đồng so sánh giá trị phù hợp.

**Câu 10.** `new BigInteger("FF", 16)` cho gì? `new BigInteger("FF")` có tương đương không?

**Đáp án:** Cái đầu cho `255` theo hệ 16. Cái sau dùng hệ 10 mặc định, nên `"FF"` không hợp lệ và ném `NumberFormatException`.

**Ghi nhớ:** `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` là các hằng số nguyên bất biến dễ đọc; `BigInteger.valueOf(long)` tạo giá trị chính xác từ `long` và cho phép tối ưu tái sử dụng. Đừng thực hiện phép toán `long` có thể overflow trước khi chuyển; đừng so `BigInteger` bằng `==`; và giữ dữ liệu dưới dạng `BigInteger` khi cần phân biệt các số nguyên vượt giới hạn primitive.