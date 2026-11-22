# `BigInteger`: `add`, `subtract`, `multiply`, `divide` và `remainder`

`java.math.BigInteger` biểu diễn số nguyên **có độ chính xác tùy ý**. Khi phép cộng, trừ, nhân vượt giới hạn `int` hoặc `long`, `BigInteger` vẫn giữ được kết quả nguyên chính xác, miễn còn đủ bộ nhớ và tài nguyên tính toán. Đây là kiểu số **nguyên**, khác với `BigDecimal` (thập phân) và `double` (dấu phẩy động gần đúng).

| Phương thức | Phép toán | Kết quả |
|---|---|---|
| `a.add(b)` | `a + b` | Tổng nguyên chính xác |
| `a.subtract(b)` | `a - b` | Hiệu nguyên chính xác |
| `a.multiply(b)` | `a × b` | Tích nguyên chính xác |
| `a.divide(b)` | Chia nguyên, làm tròn thương về 0 | Thương `BigInteger` |
| `a.remainder(b)` | Phần dư ứng với thương nguyên | Dư `BigInteger` |

Cả năm phương thức nhận đối số kiểu `BigInteger` và trả về `BigInteger`. `divide` và `remainder` không chấp nhận số chia bằng 0. Phần quan trọng nhất khi học hai phép cuối là **`a = q × b + r`**, trong đó `q = a.divide(b)`, `r = a.remainder(b)` và `b != 0`.

## 1. Tạo giá trị và hiểu tính bất biến

```java
import java.math.BigInteger;

BigInteger a = new BigInteger("12345678901234567890");
BigInteger b = BigInteger.valueOf(97);
BigInteger negative = new BigInteger("-17");
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
```

Đây là các câu lệnh minh họa dùng bên trong phương thức hoặc JShell, chưa phải tệp Java chạy độc lập.

- `new BigInteger("...")` phân tích chuỗi số nguyên, phù hợp cả khi số vượt phạm vi `long`.
- `BigInteger.valueOf(long)` dùng khi đầu vào đã nằm trong miền số `long`. Viết literal lớn hơn miền `long` rồi truyền vào `valueOf` sẽ không biên dịch.
- `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` là các hằng tiện dụng.
- Chuỗi `"12.34"` không phải số nguyên hợp lệ cho `new BigInteger(...)` và gây `NumberFormatException`.
- `BigInteger` bất biến: kết quả phép toán không thay đổi số ban đầu. Không nên suy luận rằng kết quả luôn là instance mới vì thư viện có thể tái sử dụng đối tượng trong một số trường hợp.

```java
BigInteger x = BigInteger.valueOf(100);
BigInteger y = BigInteger.valueOf(5);

x.add(y);                 // Tính 105 nhưng bỏ kết quả.
System.out.println(x);    // 100
x = x.add(y);
System.out.println(x);    // 105
```

Java không hỗ trợ `x + y`, `x - y`, `x * y`, `x / y` hoặc `x % y` khi hai biến là `BigInteger`: phải gọi phương thức. Hai đối tượng `BigInteger` so sánh giá trị bằng `equals` hoặc thứ tự bằng `compareTo`; `==` chỉ so sánh tham chiếu.

## 2. `add`: cộng số nguyên

```java
BigInteger large = new BigInteger("999999999999999999999");
BigInteger sum = large.add(BigInteger.ONE);
// sum = 1000000000000000000000
```

`add` cộng chính xác theo quy tắc dấu: `5 + (-8) = -3`, `(-5) + (-8) = -13` và cộng 0 giữ nguyên giá trị số. Nó không bị tràn như `int`/`long` chỉ vì vượt giới hạn độ rộng cố định.

Tích lũy phải tái gán vì đối tượng bất biến:

```java
BigInteger total = BigInteger.ZERO;
for (int i = 1; i <= 100; i++) {
    total = total.add(BigInteger.valueOf(i));
}
// total có giá trị 5050
```

Nếu chỉ gọi `total.add(...)`, giá trị `total` không đổi. Để kiểm tra trong Java, dùng `total.equals(BigInteger.valueOf(5050))`.

## 3. `subtract`: trừ có dấu

```java
BigInteger a = BigInteger.valueOf(25);
BigInteger b = BigInteger.valueOf(40);

BigInteger difference = a.subtract(b); // -15
```

Phép trừ trả đúng giá trị `a - b`, kể cả khi âm. Nếu muốn **khoảng cách không âm**, có thể dùng `a.subtract(b).abs()`; nếu cần **chênh lệch có dấu**, giữ nguyên kết quả. Các tính chất:

- `a.subtract(b)` bằng `a.add(b.negate())` theo giá trị.
- `a.subtract(BigInteger.ZERO)` bằng `a`.
- `a.subtract(a)` bằng 0.
- `a.subtract(b).add(b)` trở lại `a`.

`BigInteger` không tự quy định số dư tài khoản, tồn kho hoặc điểm số có được âm hay không. Các ràng buộc như thế thuộc logic nghiệp vụ.

## 4. `multiply`: nhân số nguyên lớn

```java
BigInteger factor = new BigInteger("100000000000000000000");
BigInteger product = factor.multiply(BigInteger.valueOf(12));
// product = 1200000000000000000000
```

Nhân hai số cùng dấu cho kết quả dương; khác dấu cho kết quả âm; nếu có thừa số 0 thì tích bằng 0. Với số nguyên đầu vào hợp lệ, kết quả toán học được tính chính xác và không làm tròn.

```java
BigInteger factorial = BigInteger.ONE;
for (int i = 2; i <= 6; i++) {
    factorial = factorial.multiply(BigInteger.valueOf(i));
}
// factorial = 720
```

Lỗi dễ gặp là tạo `BigInteger.valueOf(x * y)` khi `x` và `y` là `long`: phép `x*y` đã tính theo kiểu `long` **trước khi** chuyển sang `BigInteger` và có thể tràn. Hãy dùng `BigInteger.valueOf(x).multiply(BigInteger.valueOf(y))`.

Dù không bị giới hạn 64 bit, phép nhân số cực lớn vẫn có chi phí CPU/RAM. Với đầu vào từ hệ thống bên ngoài, giới hạn độ dài số theo yêu cầu ứng dụng.

## 5. `divide`: lấy thương nguyên, cắt về 0

`a.divide(b)` không trả phân số hoặc thập phân. Nó trả thương nguyên bằng cách **cắt phần phân số theo hướng về 0**, còn gọi là *truncation toward zero*.

| `a` | `b` | `a.divide(b)` | Diễn giải |
|---:|---:|---:|---|
| 17 | 5 | 3 | 17 / 5 = 3,4 |
| -17 | 5 | -3 | -17 / 5 = -3,4; cắt về 0 |
| 17 | -5 | -3 | 17 / -5 = -3,4 |
| -17 | -5 | 3 | Hai dấu âm triệt tiêu |
| 15 | 5 | 3 | Chia hết |
| 0 | 5 | 0 | Tử số bằng 0 |

**Không nhầm chia về 0 với chia sàn.** `BigInteger.valueOf(-17).divide(BigInteger.valueOf(5))` cho `-3`, chứ không phải `-4`. Với số dương, hai cách đôi khi cùng kết quả nên kiểm thử chỉ với số dương sẽ bỏ sót lỗi.

```java
BigInteger numerator = BigInteger.valueOf(7);
BigInteger denominator = BigInteger.valueOf(2);
BigInteger quotient = numerator.divide(denominator);
// quotient = 3, không phải 3.5
```

Nếu muốn tính tỷ lệ thập phân, dùng `BigDecimal` với độ chính xác, scale và quy tắc làm tròn rõ ràng, hoặc biểu diễn phân số bằng cặp tử số/mẫu số. Chia `BigInteger` không tự động biến sang `BigDecimal`.

### Chia cho 0

`a.divide(BigInteger.ZERO)` ném `ArithmeticException`. Nếu số chia đến từ người dùng, kiểm tra `b.signum() == 0` hay `b.equals(BigInteger.ZERO)` và báo lỗi thích hợp. Phép chia nguyên này không tự tạo `Infinity` hoặc `NaN` như một số phép chia dấu phẩy động.

## 6. `remainder`: phần dư theo phép chia nguyên

Đặt:

\[
q = a.divide(b),\qquad r = a.remainder(b),\qquad b \ne 0.
\]

Thì:

\[
a = q \times b + r,\qquad |r| < |b|.
\]

Ngoài ra, `r == 0` hoặc phần dư `r` có **cùng dấu với số bị chia `a`**. Dấu của số chia không quyết định dấu phần dư.

| `a` | `b` | `divide` | `remainder` | Đẳng thức |
|---:|---:|---:|---:|---|
| 17 | 5 | 3 | 2 | `17 = 3*5+2` |
| -17 | 5 | -3 | -2 | `-17 = (-3)*5+(-2)` |
| 17 | -5 | -3 | 2 | `17 = (-3)*(-5)+2` |
| -17 | -5 | 3 | -2 | `-17 = 3*(-5)+(-2)` |
| 15 | 5 | 3 | 0 | `15 = 3*5` |
| 3 | 5 | 0 | 3 | `3 = 0*5+3` |

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);
BigInteger q = a.divide(b);     // -3
BigInteger r = a.remainder(b);  // -2
boolean valid = q.multiply(b).add(r).equals(a); // true
```

Vì vậy, **`remainder` có thể trả kết quả âm** nếu số bị chia âm; đây không phải lúc nào cũng là kết quả không âm như phần dư trong số học mô-đun. `remainder(BigInteger.ZERO)` ném `ArithmeticException`.

### `remainder` khác `mod`

`BigInteger.mod(m)` dành cho mô-đun **dương** và luôn trả phần dư không âm trong `[0, m)`. Trong khi đó `remainder(m)` cho phép `m` âm miễn khác 0, và dấu phần dư theo số bị chia:

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger m = BigInteger.valueOf(5);

a.remainder(m); // -2
a.mod(m);       // 3
```

Gọi `a.mod(BigInteger.valueOf(-5))` hoặc `a.mod(BigInteger.ZERO)` sẽ ném `ArithmeticException` vì mô-đun không dương. Phải phân biệt hai kết quả khi tính chỉ số chu kỳ, lịch quay vòng hoặc phép đồng dư.

Quan trọng: `a.divide(b) * b + a.remainder(b) = a` theo giá trị, nhưng không thể thay `remainder` bằng `mod` và giữ nguyên thương trong mọi trường hợp. Với `a=-17`, `b=5`, cặp thương/dư theo `divide` và `remainder` là `(-3, -2)`; để dùng phần dư mô-đun `3`, thương tương ứng phải là `-4`: `-17 = (-4)*5+3`.

## 7. `divideAndRemainder`: lấy thương và dư đồng thời

Nếu cần cả hai giá trị cho cùng một phép chia, dùng:

```java
BigInteger a = new BigInteger("12345678901234567890");
BigInteger b = BigInteger.valueOf(97);

BigInteger[] qr = a.divideAndRemainder(b);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];
boolean valid = quotient.multiply(b).add(remainder).equals(a);
```

Mảng luôn chứa **hai phần tử**: `qr[0]` là thương bằng `divide(b)`, `qr[1]` là dư bằng `remainder(b)`. Khi cần cả hai, cách gọi này thường hiệu quả hơn thực hiện hai phép chia riêng rẽ. Nếu `b` bằng 0 thì cũng ném `ArithmeticException`.

Ví dụ chia thời lượng **không âm** thành phút và giây:

```java
BigInteger seconds = BigInteger.valueOf(125);
BigInteger[] qr = seconds.divideAndRemainder(BigInteger.valueOf(60));
// qr[0] = 2 phút; qr[1] = 5 giây
```

Với thời lượng âm, phải thiết kế quy tắc biểu diễn cụ thể vì phần dư có thể âm.

## 8. Chương trình Java 17+ chạy độc lập

Lưu vào tệp **`BigIntegerArithmeticDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerArithmeticDemo {
    public static void main(String[] args) {
        BigInteger a = new BigInteger("12345678901234567890");
        BigInteger b = BigInteger.valueOf(97);

        System.out.println("add: " + a.add(b));
        System.out.println("subtract: " + a.subtract(b));
        System.out.println("multiply: " + a.multiply(b));
        System.out.println("divide: " + a.divide(b));
        System.out.println("remainder: " + a.remainder(b));

        BigInteger[] pair = a.divideAndRemainder(b);
        System.out.println("q*r + remainder == a: "
                + pair[0].multiply(b).add(pair[1]).equals(a));
        System.out.println("a unchanged: " + a);

        BigInteger minus17 = BigInteger.valueOf(-17);
        BigInteger plus5 = BigInteger.valueOf(5);
        BigInteger minus5 = BigInteger.valueOf(-5);
        System.out.println("-17 / 5 = " + minus17.divide(plus5));
        System.out.println("-17 remainder 5 = " + minus17.remainder(plus5));
        System.out.println("-17 mod 5 = " + minus17.mod(plus5));
        System.out.println("17 / -5 = " + BigInteger.valueOf(17).divide(minus5));
        System.out.println("17 remainder -5 = "
                + BigInteger.valueOf(17).remainder(minus5));
        System.out.println("-17 / -5 = " + minus17.divide(minus5));
        System.out.println("-17 remainder -5 = " + minus17.remainder(minus5));

        try {
            a.divide(BigInteger.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("division by zero: ArithmeticException");
        }
        try {
            minus17.mod(minus5);
        } catch (ArithmeticException ex) {
            System.out.println("nonpositive modulus: ArithmeticException");
        }
    }
}
```

Lệnh biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 BigIntegerArithmeticDemo.java
java BigIntegerArithmeticDemo
```

Kết quả stdout đã xác minh bằng cách biên dịch và chạy Java:

```text
add: 12345678901234567987
subtract: 12345678901234567793
multiply: 1197530853419753085330
divide: 127275040218913071
remainder: 3
q*r + remainder == a: true
a unchanged: 12345678901234567890
-17 / 5 = -3
-17 remainder 5 = -2
-17 mod 5 = 3
17 / -5 = -3
17 remainder -5 = 2
-17 / -5 = 3
-17 remainder -5 = -2
division by zero: ArithmeticException
nonpositive modulus: ArithmeticException
```

Dòng `q*r + remainder == a: true` kiểm chứng phương trình phép chia nguyên. Dòng `a unchanged` thể hiện `BigInteger` bất biến. Bốn tổ hợp dấu cho thấy thương lấy về 0 và phần dư theo dấu **số bị chia**. Hai khối `try/catch` trình bày lỗi chia cho 0 và mô-đun không dương mà không khiến chương trình dừng.

## 9. Kiểm thử bằng tính chất đại số

Với những biến `BigInteger a`, `b`, ta có thể kiểm tra:

```java
a.add(b).subtract(b).equals(a);               // true
a.subtract(b).add(b).equals(a);               // true
a.multiply(BigInteger.ONE).equals(a);         // true
a.multiply(BigInteger.ZERO).equals(BigInteger.ZERO); // true
```

Nếu `b.signum() != 0`, gọi `BigInteger[] qr = a.divideAndRemainder(b);` rồi kiểm tra:

```java
qr[0].multiply(b).add(qr[1]).equals(a);
qr[1].abs().compareTo(b.abs()) < 0;
qr[1].signum() == 0 || qr[1].signum() == a.signum();
```

Đây là các biểu thức kiểm thử minh họa, giả định các biến đã tồn tại. Dùng `compareTo` để so sánh những số lớn mà không cần ép xuống `long`. Nên kiểm thử chia hết, không chia hết, số âm ở cả hai vị trí, số 0, số rất lớn và chia cho 0.

## 10. Lỗi phổ biến

1. **Sử dụng toán tử nguyên thủy:** `a + b` và `a % b` không hợp lệ khi `a`, `b` là `BigInteger`. Dùng `add`, `remainder`.
2. **Không nhận kết quả:** `a.add(b)` không chỉnh sửa `a`; dùng `a = a.add(b)` hoặc biến mới.
3. **Tràn trước khi chuyển kiểu:** `BigInteger.valueOf(x * y)` có thể nhận giá trị đã tràn kiểu `long`. Hãy chuyển từng toán hạng trước rồi `multiply`.
4. **Hiểu nhầm `divide`:** `7/2` là `3` dưới dạng `BigInteger`, không phải `3.5`.
5. **Nhầm hướng làm tròn:** `-17 / 5` cho `-3`, không phải `-4`.
6. **Cho rằng phần dư luôn không âm:** `remainder` của `-17` với `5` là `-2`; `mod(5)` mới cho `3`.
7. **Bỏ qua số chia 0:** cả `divide`, `remainder` và `divideAndRemainder` đều ném `ArithmeticException`.
8. **Dùng `==` để so giá trị:** dùng `equals`; `==` kiểm tra cùng tham chiếu.
9. **Ép về số nhỏ:** `longValue()` có thể làm mất các bit bậc cao khi số lớn; dùng `longValueExact()` để yêu cầu chuyển chính xác (ném `ArithmeticException` nếu không thể).
10. **Không giới hạn kích thước đầu vào:** số nguyên tùy ý độ dài vẫn có chi phí CPU/RAM; ứng dụng cần chính sách xử lý phù hợp.

## 11. Bài tập có lời giải

| Biểu thức Java | Kết quả |
|---|---|
| `BigInteger.valueOf(8).add(BigInteger.valueOf(-3))` | `5` |
| `BigInteger.valueOf(8).subtract(BigInteger.valueOf(13))` | `-5` |
| `BigInteger.valueOf(-4).multiply(BigInteger.valueOf(-6))` | `24` |
| `BigInteger.valueOf(-23).divide(BigInteger.valueOf(7))` | `-3` |
| `BigInteger.valueOf(-23).remainder(BigInteger.valueOf(7))` | `-2` |
| `BigInteger.valueOf(-23).mod(BigInteger.valueOf(7))` | `5` |
| `BigInteger.ZERO.remainder(BigInteger.valueOf(17))` | `0` |
| `BigInteger.ONE.divide(BigInteger.ZERO)` | `ArithmeticException` |

Giải thích trường hợp `-23`: `-23 = (-3)*7 + (-2)` với thương chia về 0. Nếu chọn phần dư mô-đun không âm là `5`, thương tương ứng phải là `-4` để có `-23 = (-4)*7 + 5`.

## Ghi nhớ

`BigInteger` lưu số nguyên tùy ý độ dài, các giá trị **bất biến**. `add`, `subtract` và `multiply` cho kết quả nguyên chính xác. `divide` trả thương nguyên cắt về 0, `remainder` có thể âm theo dấu số bị chia, và cặp thương–phần dư thỏa `a = q*b + r` khi `b != 0`. Dùng `mod(m)` nếu muốn phần dư không âm với `m > 0`. Nếu cần cả thương lẫn dư, `divideAndRemainder` trả `[quotient, remainder]`. Luôn kiểm tra số chia 0 và dùng `equals` để so sánh giá trị.