# BigInteger.divideAndRemainder và kiểm tra chia hết trong Java

## 1. Mục tiêu và bài toán

Java cung cấp kiểu `java.math.BigInteger` để làm việc với số nguyên có độ lớn vượt miền `int` và `long`. Khi cần xác định một số lớn có chia hết cho số khác hay không, phép chia nguyên và phép lấy **số dư** là công cụ chính. Phương thức `divideAndRemainder(BigInteger divisor)` trả về **cả thương lẫn số dư** trong một lần gọi.

Sau bài học, bạn sẽ:

- Biết cách sử dụng `divideAndRemainder`, `divide` và `remainder` đúng hợp đồng.
- Đọc được `BigInteger[]` trả về: `result[0]` là thương, `result[1]` là số dư.
- Kiểm tra chia hết chính xác bằng điều kiện số dư bằng `BigInteger.ZERO`.
- Hiểu quy tắc với số âm: thương cắt về **0**, số dư cùng dấu với số bị chia nếu khác 0.
- Phân biệt `remainder` với `mod`: cùng làm việc với số dư, nhưng **quy tắc dấu và miền đối số không giống nhau**.
- Xử lý trường hợp chia cho 0, phép chia trong các bài toán đếm/lập lịch, dữ liệu nhập từ chuỗi và các phép tính trên số rất lớn.
- Biết khi nào nên lấy cả thương và số dư, và khi nào chỉ cần kiểm tra chia hết.

Ví dụ dùng **Java 17+**. Không cần thư viện bên ngoài hoặc tính năng preview.

## 2. BigInteger là gì và tại sao không dùng long?

`long` có dấu, chứa được các giá trị từ `-9223372036854775808` đến `9223372036854775807`. Nếu số cần tính vượt miền này, phép toán nguyên primitive có thể bị tràn, cho kết quả không còn đúng.

`BigInteger` biểu diễn số nguyên với độ chính xác tùy ý, chịu giới hạn bộ nhớ và khả năng xử lý thực tế của JVM. Nó là một **lớp bất biến (immutable)**: các phép toán trả về kết quả mới hoặc một instance hợp lệ khác, không sửa số nguồn.

~~~java
import java.math.BigInteger;

// Các lệnh sau đặt trong phương thức:
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger divisor = BigInteger.valueOf(9L);

BigInteger[] result = huge.divideAndRemainder(divisor);
System.out.println(result[0]); // Thương
System.out.println(result[1]); // Số dư
~~~

Chú ý cách tạo số lớn: ưu tiên `new BigInteger("...")` từ **chuỗi ký tự** khi giá trị vượt miền `long`. Không viết một literal nguyên quá lớn rồi đưa vào `BigInteger.valueOf(...)` vì literal đã không hợp lệ ở thời điểm biên dịch.

~~~java
BigInteger a = new BigInteger("1000000000000000000000000");
BigInteger b = BigInteger.valueOf(8);
~~~

Hai giá trị trên biểu diễn chính xác số nguyên, không chịu lỗi làm tròn nhị phân như `double`.

## 3. Quy tắc chia nguyên: a = q × b + r

Với hai số nguyên `a` và `b`, trong đó `b != 0`, Java định nghĩa thương và số dư thỏa:

\[
a = q \times b + r
\]

Trong BigInteger:

\[
q = a.\operatorname{divide}(b),\qquad
r = a.\operatorname{remainder}(b)
\]

Ngoài đẳng thức quan trọng trên, phép chia BigInteger có các tính chất:

1. **Thương `q` được cắt về 0** (*truncation toward zero*), không phải luôn làm tròn xuống theo `floor`.
2. **`|r| < |b|`**: độ lớn số dư luôn nhỏ hơn độ lớn của số chia khi `b` khác 0.
3. Nếu `r != 0`, dấu của `r` giống dấu của `a` (số bị chia).
4. Nếu `a` chia hết cho `b`, thì `r = 0`.

Ví dụ `17 / 5`:

\[
17 = 3\times5 + 2.
\]

Trong Java:

~~~java
BigInteger a = BigInteger.valueOf(17);
BigInteger b = BigInteger.valueOf(5);

BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // 3
System.out.println(qr[1]); // 2
~~~

Một phép chia nguyên có thể có **thương bằng 0** nhưng số dư vẫn khác 0: `3 / 5` có thương 0, dư 3. Vì vậy tuyệt đối không dùng `q.equals(BigInteger.ZERO)` để kết luận có chia hết.

## 4. Cách sử dụng BigInteger.divideAndRemainder

Chữ ký phương thức:

~~~java
public BigInteger[] divideAndRemainder(BigInteger val)
~~~

Phương thức là instance method của `BigInteger`. Nó trả một **mảng gồm hai phần tử** theo thứ tự cố định:

| Chỉ số | Ý nghĩa | Tương ứng |
| --- | --- | --- |
| `result[0]` | Thương nguyên | `a.divide(b)` |
| `result[1]` | Số dư nguyên | `a.remainder(b)` |

Ví dụ:

~~~java
BigInteger amount = new BigInteger("12345");
BigInteger groupSize = BigInteger.valueOf(100);

BigInteger[] qr = amount.divideAndRemainder(groupSize);

BigInteger fullGroups = qr[0];
BigInteger leftover = qr[1];

System.out.println(fullGroups); // 123
System.out.println(leftover);   // 45
~~~

Bạn cũng có thể xác minh phép chia:

~~~java
BigInteger reconstructed = fullGroups.multiply(groupSize)
        .add(leftover);

System.out.println(reconstructed.equals(amount)); // true
~~~

**Vì sao dùng `divideAndRemainder`?** Khi cần **cả thương lẫn số dư**, phương thức thể hiện mục đích trực tiếp và API cho phép tính hai kết quả cùng nhau. Nếu chỉ cần thương hoặc chỉ cần số dư, các phương thức `divide` và `remainder` thường diễn đạt mục đích rõ hơn. Không nên khẳng định rằng `divideAndRemainder` luôn nhanh hơn trong mọi JVM/dữ liệu mà không có đo kiểm phù hợp.

## 5. Kiểm tra chia hết bằng số dư bằng 0

Số nguyên `a` chia hết cho số nguyên khác 0 `b` khi và chỉ khi:

\[
a\bmod b=0
\]

Trong ngữ cảnh Java, nên phát biểu thực thi bằng `a.remainder(b).signum() == 0` hoặc `BigInteger.ZERO.equals(a.remainder(b))`. Cách kiểm tra này không mất độ chính xác, kể cả với số có hàng trăm hoặc hàng nghìn chữ số.

~~~java
BigInteger value = new BigInteger("1000000000000000000000000");
BigInteger divisor = BigInteger.valueOf(8);

boolean divisible = value.remainder(divisor).signum() == 0;
System.out.println(divisible); // true
~~~

Với kết quả `divideAndRemainder`:

~~~java
BigInteger[] qr = value.divideAndRemainder(divisor);
boolean divisible = qr[1].equals(BigInteger.ZERO);

System.out.println(divisible); // true
~~~

**Không dùng toán tử `%` với `BigInteger`:** đây là đối tượng, không phải primitive. `a % b` là cú pháp không hợp lệ nếu `a` và `b` là `BigInteger`. Thay vào đó, gọi `a.remainder(b)`.

**Không dùng `==` để kiểm tra số dư bằng BigInteger.ZERO:** `==` so sánh reference, không phải giá trị số. `equals` hoặc `signum() == 0` mới đúng mục đích.

### Hàm kiểm tra chia hết an toàn

~~~java
static boolean isDivisible(BigInteger dividend, BigInteger divisor) {
    if (dividend == null || divisor == null) {
        throw new IllegalArgumentException("Arguments must not be null");
    }
    if (divisor.signum() == 0) {
        throw new IllegalArgumentException("Divisor must be nonzero");
    }
    return dividend.remainder(divisor).signum() == 0;
}
~~~

Đây là **phương thức ở cấp lớp**; để chạy độc lập, hãy đặt nó trong một class Java và gọi từ `main`. Hàm trên cố ý báo lỗi khi đầu vào `null` hoặc chia cho 0, thay vì đánh đồng trường hợp dữ liệu sai với kết quả “không chia hết”.

## 6. Chia hết không phụ thuộc dấu của số chia

Đối với số nguyên, dấu của số chia không làm thay đổi tính chia hết:

- 20 chia hết cho 5.
- 20 chia hết cho −5.
- −20 chia hết cho 5.
- −20 chia hết cho −5.

~~~java
BigInteger twenty = BigInteger.valueOf(20);
BigInteger minusFive = BigInteger.valueOf(-5);

BigInteger[] qr = twenty.divideAndRemainder(minusFive);

System.out.println(qr[0]);                       // -4
System.out.println(qr[1]);                       // 0
System.out.println(qr[1].signum() == 0);          // true
~~~

Với số chia `-5`, thương là `-4`, số dư bằng 0 và đẳng thức `20 = (-4) × (-5) + 0` vẫn đúng.

Để so sánh số dư của các phép chia có dấu khác nhau, cần hiểu rõ hành vi `remainder`. Một số dư không bằng 0 có thể là số âm; **điều kiện chia hết vẫn chỉ là số dư bằng 0**, không quan tâm dấu của thương hay số chia.

## 7. Chia số âm: thương cắt về 0, dư theo số bị chia

Bảng dưới dùng `divideAndRemainder` với các số nhỏ để thấy rõ quy tắc dấu:

| `a` | `b` | Thương `q` | Số dư `r` | Kiểm chứng |
| ---: | ---: | ---: | ---: | --- |
| 17 | 5 | 3 | 2 | `17 = 3 × 5 + 2` |
| −17 | 5 | −3 | −2 | `−17 = −3 × 5 − 2` |
| 17 | −5 | −3 | 2 | `17 = −3 × (−5) + 2` |
| −17 | −5 | 3 | −2 | `−17 = 3 × (−5) − 2` |
| 15 | −5 | −3 | 0 | `15 = −3 × (−5)` |
| 3 | 5 | 0 | 3 | `3 = 0 × 5 + 3` |

Ví dụ chạy:

~~~java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);

BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // -3
System.out.println(qr[1]); // -2
~~~

Lưu ý `floor(-17 / 5)` theo số thực là −4, nhưng phép chia nguyên BigInteger trả −3, vì nó **cắt về 0**. Không tự thay thế phép chia BigInteger bằng công thức floor nếu bài toán cần đúng hợp đồng Java.

**Remainder âm không phải lỗi:** đó là kết quả hợp lệ của phép `remainder` với số bị chia âm. Nếu bài toán cần một phần dư không âm (ví dụ chỉ số vòng tròn hoặc phép toán đồng dư), hãy cân nhắc `mod` với modulus dương; xem phần tiếp theo.

## 8. Phân biệt remainder và mod

`BigInteger` cung cấp hai phương thức nhìn giống nhau:

- `a.remainder(b)`: phép lấy số dư đi kèm **thương cắt về 0**. Số chia `b` có thể âm, miễn khác 0. Số dư khác 0 mang dấu của **a**.
- `a.mod(m)`: cho **số dư không âm** với **modulus phải dương** (`m > 0`). Nếu `m <= 0`, Java ném `ArithmeticException`.

| Biểu thức | Kết quả |
| --- | ---: |
| `BigInteger.valueOf(17).remainder(BigInteger.valueOf(5))` | 2 |
| `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(5))` | −2 |
| `BigInteger.valueOf(-17).mod(BigInteger.valueOf(5))` | 3 |
| `BigInteger.valueOf(17).remainder(BigInteger.valueOf(-5))` | 2 |
| `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(-5))` | −2 |
| `BigInteger.valueOf(17).mod(BigInteger.valueOf(-5))` | **ArithmeticException** |

~~~java
BigInteger n = BigInteger.valueOf(-17);
BigInteger five = BigInteger.valueOf(5);

System.out.println(n.remainder(five)); // -2
System.out.println(n.mod(five));       // 3
~~~

Hai kết quả `−2` và `3` tương đương nhau **theo modulo 5**, nhưng không bằng nhau dưới dạng số nguyên. Vì `-17 = -4 × 5 + 3`, kết quả `mod(5)` chính là đại diện không âm 3.

### Khi nào dùng phương thức nào?

- **Kiểm tra chia hết:** `remainder(divisor).signum() == 0` là cách đơn giản, kể cả khi divisor âm. `mod` cũng kiểm tra được với divisor dương, nhưng không nhận số chia âm.
- **Muốn cả thương và dư:** `divideAndRemainder` trả cặp tuân quy tắc cắt về 0.
- **Chỉ số xoay vòng, lớp đồng dư, thuật toán số học modulo:** dùng `mod(m)` khi xác định `m > 0` để nhận kết quả trong `[0, m)`.
- **Cần thương kiểu floor với divisor dương:** `divideAndRemainder` không trực tiếp có cùng quy tắc khi dividend âm; phải tính theo yêu cầu toán học riêng.

Đừng dùng `remainder` và `mod` thay thế lẫn nhau chỉ vì các ví dụ số dương thường cho cùng kết quả.

## 9. Chia cho 0: một lỗi bắt buộc xử lý

Phép chia cho 0 không xác định. Với `BigInteger`, các lời gọi sau ném `ArithmeticException`:

~~~java
BigInteger ten = BigInteger.TEN;
BigInteger zero = BigInteger.ZERO;

// ten.divide(zero);             // ArithmeticException
// ten.remainder(zero);          // ArithmeticException
// ten.divideAndRemainder(zero); // ArithmeticException
// ten.mod(zero);                // ArithmeticException (modulus phải dương)
~~~

Nếu chuỗi dữ liệu đầu vào có thể chứa `"0"` cho số chia, nên kiểm tra sớm để báo lỗi có ngữ cảnh, thay vì để exception của phép toán xảy ra sâu trong xử lý:

~~~java
static BigInteger[] divideNonZero(BigInteger a, BigInteger b) {
    if (a == null || b == null) {
        throw new IllegalArgumentException("Missing operands");
    }
    if (b.signum() == 0) {
        throw new IllegalArgumentException("Division by zero");
    }
    return a.divideAndRemainder(b);
}
~~~

Đây là phương thức minh họa ở cấp lớp. **Không** trả một cặp thương/dư `[0, 0]` khi divisor bằng 0; như vậy là tạo kết quả giả và che lỗi nghiệp vụ.

Riêng số bị chia bằng 0 là hợp lệ nếu số chia khác 0: `0 / 7` có thương 0 và dư 0. Vì vậy `0` chia hết cho **mọi số nguyên khác 0**, còn `0 / 0` không được phép.

## 10. Chương trình Java 17+ hoàn chỉnh

Lưu vào file `BigIntegerDivisionDemo.java`:

~~~java
import java.math.BigInteger;

public class BigIntegerDivisionDemo {
    static boolean isDivisible(BigInteger a, BigInteger b) {
        if (a == null || b == null || b.signum() == 0) {
            throw new IllegalArgumentException("Invalid operands");
        }
        return a.remainder(b).signum() == 0;
    }

    static void showDivision(long a, long b) {
        BigInteger left = BigInteger.valueOf(a);
        BigInteger right = BigInteger.valueOf(b);
        BigInteger[] qr = left.divideAndRemainder(right);

        System.out.println(a + "/" + b +
                " => q=" + qr[0] + ", r=" + qr[1] +
                ", divisible=" + qr[1].equals(BigInteger.ZERO));
    }

    public static void main(String[] args) {
        showDivision(17, 5);
        showDivision(-17, 5);
        showDivision(17, -5);
        showDivision(-17, -5);
        showDivision(15, -5);
        showDivision(0, 7);

        BigInteger huge = new BigInteger("1000000000000000000000000");
        BigInteger eight = BigInteger.valueOf(8);
        BigInteger[] parts = huge.divideAndRemainder(eight);

        System.out.println("huge quotient=" + parts[0]);
        System.out.println("huge remainder=" + parts[1]);
        System.out.println("huge divisible=" + isDivisible(huge, eight));

        BigInteger negative = BigInteger.valueOf(-17);
        BigInteger five = BigInteger.valueOf(5);
        System.out.println("remainder=" + negative.remainder(five));
        System.out.println("mod=" + negative.mod(five));

        BigInteger reconstructed = parts[0].multiply(eight).add(parts[1]);
        System.out.println("reconstructed=" + reconstructed.equals(huge));

        try {
            huge.divideAndRemainder(BigInteger.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("divide by zero: ArithmeticException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 BigIntegerDivisionDemo.java
java BigIntegerDivisionDemo
~~~

Kết quả stdout:

~~~text
17/5 => q=3, r=2, divisible=false
-17/5 => q=-3, r=-2, divisible=false
17/-5 => q=-3, r=2, divisible=false
-17/-5 => q=3, r=-2, divisible=false
15/-5 => q=-3, r=0, divisible=true
0/7 => q=0, r=0, divisible=true
huge quotient=125000000000000000000000
huge remainder=0
huge divisible=true
remainder=-2
mod=3
reconstructed=true
divide by zero: ArithmeticException
~~~

Giải thích:

1. Bốn trường hợp của `±17 / ±5` có thương được cắt về 0 và số dư theo dấu của số bị chia.
2. `15 / -5` có số dư 0 nên chia hết, dù số chia âm.
3. `0 / 7` cũng chia hết, nhưng phép chia cho 0 là không hợp lệ.
4. `10²⁴ / 8` có thương nguyên chính xác `125000000000000000000000`. Số vượt miền `long` nhưng `BigInteger` vẫn xử lý được.
5. `-17.remainder(5)` theo nghĩa toán tử phương thức cho `-2`; `-17.mod(5)` cho `3` không âm.
6. `q.multiply(b).add(r).equals(a)` là phép đối chiếu đẳng thức thương–dư.
7. Chia cho `BigInteger.ZERO` ném `ArithmeticException`, được bắt và xử lý trong ví dụ.

## 11. Kiểm tra dữ liệu chuỗi trước khi thực hiện phép chia

Trong API và file dữ liệu, số thường được nhận dưới dạng chuỗi. `new BigInteger(text)` parse số nguyên thập phân hợp lệ; nếu không hợp lệ sẽ ném `NumberFormatException`. Một hàm cơ bản:

~~~java
static BigInteger parseRequiredInteger(String text, String fieldName) {
    if (text == null || text.isEmpty()) {
        throw new IllegalArgumentException(fieldName + " is required");
    }
    try {
        return new BigInteger(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                fieldName + " must be a decimal integer", ex);
    }
}
~~~

Đây là method minh họa đặt trong một lớp. Cách viết này nhận số nguyên theo cú pháp `BigInteger(String)`, không nhận số thực hay ký hiệu dấu phân cách grouping như `"1,000"`.

Tùy hợp đồng, ứng dụng có thể:

- Cho phép dấu `-` hoặc dấu `+` của số nguyên.
- Quy định whitespace được bỏ qua bằng bước chuẩn hóa rõ ràng.
- Dùng `new BigInteger(text, radix)` cho biểu diễn hệ 2, hệ 16 hoặc radix hợp lệ.
- Giới hạn số ký tự đầu vào để bảo vệ tài nguyên, vì `BigInteger` rất lớn có chi phí CPU/bộ nhớ.
- Kiểm tra số chia khác 0 và các giới hạn nghiệp vụ trước khi tính.

Không nên dùng `Double.parseDouble` để đọc một số nguyên lớn rồi cast/round; `double` có thể đã làm mất chữ số nguyên. Chuỗi decimal ban đầu nên được parse trực tiếp thành `BigInteger`.

## 12. BigInteger.ZERO, equals và signum

Ba cách kiểm tra số dư bằng 0 phổ biến:

~~~java
BigInteger remainder = BigInteger.valueOf(25)
        .remainder(BigInteger.valueOf(5));

boolean a = remainder.equals(BigInteger.ZERO);
boolean b = BigInteger.ZERO.equals(remainder);
boolean c = remainder.signum() == 0;

System.out.println(a && b && c); // true
~~~

Tất cả đều đúng khi `remainder` là một `BigInteger` khác null. Trong phép `divideAndRemainder` thành công, cả hai phần tử mảng không phải null. Với một nguồn có thể null từ bên ngoài, `BigInteger.ZERO.equals(value)` là cách so sánh an toàn trước null; `value.signum()` cần null guard.

**Sai lầm phổ biến:**

~~~java
// Sai mục đích: == so sánh identity của đối tượng BigInteger
// if (remainder == BigInteger.ZERO) { ... }
~~~

Một kết quả tình cờ cùng reference với `BigInteger.ZERO` không phải hợp đồng để xác định hai số có cùng giá trị. Hãy dùng `equals` hoặc `signum`.

### Vì sao signum hữu ích?

`signum()` trả:

- `-1` khi số âm;
- `0` khi số bằng 0;
- `1` khi số dương.

Nó kiểm tra dấu trên các số nguyên rất lớn mà không cần đổi sang `int` hay `long`. Một số dư bằng 0 sẽ có `signum()==0` bất kể số bị chia/số chia ban đầu có dấu gì.

## 13. So sánh cách dùng divideAndRemainder, divide và remainder

Cả ba API đều thực hiện phép chia nguyên, nhưng mục đích biểu đạt khác nhau.

~~~java
BigInteger a = new BigInteger("12345");
BigInteger b = BigInteger.valueOf(100);

// Cần cả hai:
BigInteger[] qr = a.divideAndRemainder(b);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];

// Chỉ cần thương:
BigInteger qOnly = a.divide(b);

// Chỉ cần dư:
BigInteger rOnly = a.remainder(b);
~~~

| Nhu cầu | API nên cân nhắc |
| --- | --- |
| Chia thành các nhóm đầy và số còn lại | `divideAndRemainder` |
| Lấy thương nguyên | `divide` |
| Kiểm tra chia hết | `remainder` rồi kiểm tra zero |
| Lấy số dư không âm với modulus dương | `mod` |
| Kiểm tra đồng dư trong mô hình modulo m > 0 | `mod` hoặc `subtract` + `mod` |

**Khi cần cả thương lẫn dư, hãy gọi `divideAndRemainder` một lần** để mã ngắn và thể hiện ý đồ. Khi chỉ muốn kiểm tra chia hết, chỉ lấy remainder là đủ; không cần tính hoặc giữ thương.

Không tự convert `BigInteger` sang `long` chỉ để dùng `%` primitive. Nếu giá trị vượt miền `long`, `longValue()` có thể cắt mất bit cao và cho dữ liệu sai. Khi bắt buộc chuyển kiểu, cân nhắc `longValueExact()` để phát hiện giá trị ngoài miền bằng `ArithmeticException`.

## 14. Chia thành các lô hàng hoặc nhóm

Giả sử có số lượng vật phẩm `items` và mỗi thùng chứa tối đa `capacity` món. Cần biết số thùng **đầy** và số vật phẩm **còn lại**:

~~~java
BigInteger items = new BigInteger("12345");
BigInteger capacity = BigInteger.valueOf(100);
BigInteger[] qr = items.divideAndRemainder(capacity);

BigInteger fullBoxes = qr[0];
BigInteger leftoverItems = qr[1];

System.out.println(fullBoxes);    // 123
System.out.println(leftoverItems); // 45
~~~

Nếu cần số thùng **tổng cộng**, bao gồm thùng cuối chưa đầy, và các giá trị đều **không âm** với `capacity > 0`:

~~~java
BigInteger boxesNeeded = qr[1].signum() == 0
        ? qr[0]
        : qr[0].add(BigInteger.ONE);

System.out.println(boxesNeeded); // 124
~~~

Mẫu này tương đương phép chia lấy **ceil** với `items >= 0` và `capacity > 0`. Không áp dụng nguyên xi cho số âm, nơi thương BigInteger cắt về 0 và khái niệm “thùng hàng” không còn phù hợp. Việc kiểm tra miền nghiệp vụ nên diễn ra trước khi tính.

## 15. Áp dụng cho chu kỳ, phân trang, hệ thống batch

Một tình huống thường gặp khác là phân chia một tổng công việc thành từng batch có kích thước cố định.

Ví dụ:

~~~java
BigInteger records = new BigInteger("1001");
BigInteger batchSize = BigInteger.valueOf(100);

BigInteger[] qr = records.divideAndRemainder(batchSize);
System.out.println("full batches=" + qr[0]); // full batches=10
System.out.println("remainder=" + qr[1]);    // remainder=1
~~~

Nếu câu hỏi là “có thể chia đều thành các batch cùng kích thước không?”, chỉ cần:

~~~java
boolean evenBatches = qr[1].signum() == 0;
System.out.println(evenBatches); // false
~~~

Khi làm phân trang hoặc đánh số vị trí từ 0, hãy chú ý yêu cầu rõ ràng của chỉ số (có âm hay không, kích thước trang có dương hay không). `remainder` âm với chỉ số âm có thể khiến việc truy cập mảng thất bại. Với yêu cầu **chỉ số vòng tròn không âm**, `mod` với modulus dương là cách phù hợp hơn.

## 16. Kiểm tra chia hết cho một số cụ thể

### Chẵn hay lẻ

Kiểm tra tính chẵn bằng số dư 2:

~~~java
BigInteger huge = new BigInteger("1000000000000000000000000");
boolean even = huge.remainder(BigInteger.TWO).signum() == 0;

System.out.println(even); // true
~~~

`BigInteger.TWO` có sẵn trong Java 17. Với phép toán bit, `!huge.testBit(0)` cũng kiểm tra bit thấp nhất bằng 0, nhưng sử dụng `remainder(BigInteger.TWO)` bộc lộ ý nghĩa chia hết dễ đọc cho người mới học.

### Chia hết cho một tích hoặc bội

Giả sử muốn kiểm tra `n` chia hết cho `12`:

~~~java
BigInteger n = new BigInteger("123456");
BigInteger twelve = BigInteger.valueOf(12);

System.out.println(n.remainder(twelve).signum() == 0); // true
~~~

Không nên tự thay một phép chia cho 12 bằng nhiều điều kiện số dư nếu không có lý do rõ ràng: một tiêu chí trực tiếp bằng `remainder(12)` là đầy đủ và chính xác. Các quy tắc toán học như “chia hết cho 3 và 4 thì chia hết cho 12” dựa trên quan hệ bội nguyên tố cùng nhau; nên chứng minh trước khi tối ưu theo chúng.

### Số bị chia bằng 0

~~~java
System.out.println(BigInteger.ZERO.remainder(BigInteger.TEN)); // 0
~~~

Số 0 chia hết cho mọi số khác 0. Nhưng **không thể chia cho 0**. Quy tắc này cần phân biệt trong validation, nhất là khi người dùng nhập một “ước số” vào form.

## 17. Những giới hạn và lỗi cần chú ý

| Trường hợp | Điều cần biết |
| --- | --- |
| `a.divideAndRemainder(BigInteger.ZERO)` | Ném `ArithmeticException` |
| `a.remainder(BigInteger.ZERO)` | Ném `ArithmeticException` |
| `a.mod(BigInteger.ZERO)` | Ném `ArithmeticException` vì modulus không dương |
| `a.mod(negative)` | Ném `ArithmeticException`, dù `remainder(negative)` hợp lệ |
| `a.divideAndRemainder(null)` | Đầu vào null không phải divisor hợp lệ; cần null guard |
| `result[0] == 0` | Thương bằng 0 không chứng minh phép chia hết |
| `result[1].signum() == 0` | Đúng điều kiện chia hết với divisor khác 0 |
| `result[1] == BigInteger.ZERO` | So sánh object identity, không dùng làm kiểm tra giá trị |
| `result[1].intValue()` | Có thể mất dữ liệu với số dư lớn; không cần thiết để kiểm tra zero |
| `BigInteger.valueOf(veryLargeLiteral)` | Literal/`long` có miền hữu hạn; parse chuỗi trực tiếp |
| `BigDecimal.divide` | Là phép chia decimal với quy tắc scale/rounding khác; không thay cho phép chia nguyên BigInteger |
| `a.mod(m)` và `a.remainder(m)` | Khác kết quả khi `a` âm và `m` dương |
| `a.divide(b)` so với `Math.floorDiv` | BigInteger cắt thương về 0; floor division primitive có quy tắc khác với số âm |

### BigInteger là immutable

Các lời gọi như `a.divide(b)`, `a.remainder(b)` hay `a.divideAndRemainder(b)` **không sửa `a` hoặc `b`**. Mảng trả về là một container bạn có thể gán lại phần tử, nhưng các đối tượng `BigInteger` trong mảng vẫn bất biến.

Ví dụ:

~~~java
BigInteger a = BigInteger.valueOf(17);
BigInteger b = BigInteger.valueOf(5);
BigInteger[] qr = a.divideAndRemainder(b);

qr[0] = BigInteger.ZERO; // Gán lại mảng, không sửa a hoặc b.
System.out.println(a);   // 17
~~~

Đừng suy rằng vì mảng có thể thay đổi nên bản thân số nguồn đã được thay đổi.

## 18. Kiểm chứng bằng tính chất toán học

Một cách kiểm thử tốt là đối chiếu **đồng thời** cả thương và số dư với định nghĩa. Với `b != 0`:

\[
a = q b + r,\qquad |r|<|b|
\]

và nếu `r != 0`, `sign(r) = sign(a)`.

Ví dụ phương thức kiểm thử:

~~~java
static boolean validQuotientRemainder(
        BigInteger a, BigInteger b, BigInteger[] qr) {
    if (a == null || b == null || b.signum() == 0
            || qr == null || qr.length != 2
            || qr[0] == null || qr[1] == null) {
        return false;
    }

    BigInteger q = qr[0];
    BigInteger r = qr[1];

    boolean equation = q.multiply(b).add(r).equals(a);
    boolean bounded = r.abs().compareTo(b.abs()) < 0;
    boolean signCorrect = r.signum() == 0
            || r.signum() == a.signum();

    return equation && bounded && signCorrect;
}
~~~

Đây là **phương thức minh họa cấp lớp**, có thể bổ sung vào các bài kiểm thử tự động. Các tính chất trên mạnh hơn việc chỉ kiểm tra một vài ví dụ dương và giúp phát hiện những giả định sai khi mở rộng thuật toán.

Có thể thử nhiều bộ đầu vào:

- Cả `a` và `b` dương.
- `a` âm, `b` dương.
- `a` dương, `b` âm.
- Cả hai âm.
- `a` bằng 0, `b` khác 0.
- `|a| < |b|`, thương bằng 0.
- `a` là bội của `b`, số dư bằng 0.
- Số có hàng trăm chữ số.
- `b` bằng 0: kiểm tra ngoại lệ, không tìm thương/dư.

## 19. Các câu hỏi tự kiểm tra

**Câu 1.** `BigInteger.valueOf(17).divideAndRemainder(BigInteger.valueOf(5))` trả gì?

**Đáp án:** Mảng `[3, 2]`, trong đó thương 3 và dư 2. Vì dư khác 0 nên 17 không chia hết cho 5.

**Câu 2.** `-17` chia cho `5` trong BigInteger có thương và dư nào?

**Đáp án:** Thương `-3`, dư `-2`; `−17 = (−3) × 5 + (−2)`. Không dùng `floor(-17/5)` để suy thương.

**Câu 3.** Kiểm tra chia hết bằng `qr[0].equals(BigInteger.ZERO)` có đúng không?

**Đáp án:** Không. Đó là kiểm tra thương bằng 0. Chia hết khi **`qr[1].signum() == 0`**, với divisor khác 0.

**Câu 4.** Tại sao `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(5))` bằng `-2`, còn `mod(BigInteger.valueOf(5))` bằng `3`?

**Đáp án:** `remainder` giữ quy tắc thương cắt về 0 và dư có dấu của số bị chia; `mod` chuẩn hóa kết quả về `[0, m)` khi `m > 0`.

**Câu 5.** `BigInteger.ZERO` có chia hết cho `BigInteger.valueOf(7)` không?

**Đáp án:** Có, vì `0 = 0 × 7 + 0`. Nhưng phép chia `0 / 0` không được định nghĩa.

**Câu 6.** Khi cần số thùng đầy **và** số món còn lại, nên dùng phương thức nào?

**Đáp án:** `divideAndRemainder`; phần tử `[0]` là thương/số thùng đầy, `[1]` là số còn lại. Kiểm tra số lượng không âm và sức chứa dương trước khi dùng công thức thùng hàng.

**Câu 7.** Nếu chỉ kiểm tra chia hết với một số rất lớn, có nên dùng `longValue()` để lấy `%` không?

**Đáp án:** Không. Chuyển `BigInteger` ngoài miền `long` có thể mất phần bit cao. Dùng `remainder` trực tiếp để đảm bảo chính xác.

**Câu 8.** Tại sao `BigInteger.mod` không cho modulus âm?

**Đáp án:** Hợp đồng của `mod` yêu cầu modulus **dương**, để số dư không âm trong `[0, m)`. Muốn lấy dư với divisor âm theo phép chia nguyên, dùng `remainder`.

## 20. Tóm tắt và tài liệu tham khảo

- **`divideAndRemainder(divisor)`** trả cặp `[quotient, remainder]`; cả hai chính xác trên `BigInteger`.
- Với divisor khác 0: `a = q.multiply(b).add(r)`, `|r| < |b|`; thương **cắt về 0**, dư mang dấu số bị chia nếu khác 0.
- **Kiểm tra chia hết:** `a.remainder(b).signum() == 0`, sau khi xác thực `b != 0`.
- Dùng **`equals` hoặc `signum`**, không dùng `==` cho giá trị của `BigInteger`.
- **`remainder` khác `mod`** khi số bị chia âm; `mod` yêu cầu modulus dương.
- **Chia cho 0 ném `ArithmeticException`**; đừng biến lỗi thành kết quả giả.
- Với số vượt miền `long`, tạo `BigInteger` từ chuỗi và tránh đổi sang primitive chỉ để tính toán.

Tài liệu chính thức:

- [BigInteger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): `divideAndRemainder`, `divide`, `remainder`, `mod`, `ZERO`, `signum` và quy tắc ngoại lệ.
- [Java Language Specification 17 — Integer Division](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): cơ sở đối chiếu quy tắc thương nguyên cắt về 0.
- [Java Language Specification 17 — Remainder Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): quan hệ thương/dư trong toán tử primitive để hiểu dấu số dư.
