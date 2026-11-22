# Dùng BigInteger khi miền giá trị không có giới hạn phù hợp

> **Java core – numbers · Tràn và kiểm tra biên**  
> Mục tiêu: nhận biết lúc `int`/`long` không đáp ứng miền dữ liệu, chuyển sang `BigInteger` trước khi tràn, tính toán số nguyên chính xác, chuyển đổi an toàn và kiểm soát rủi ro bộ nhớ/hiệu năng.

## 1. Khi nào `long` là chưa đủ?

Các kiểu nguyên primitive của Java có **miền giá trị cố định**:

| Kiểu | Miền có dấu | Độ rộng |
| --- | --- | --- |
| `byte` | −128 đến 127 | 8 bit |
| `short` | −32.768 đến 32.767 | 16 bit |
| `int` | −2.147.483.648 đến 2.147.483.647 | 32 bit |
| `long` | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | 64 bit |

Khi tính tổng, tích hoặc lũy thừa vượt giới hạn, phép số học nguyên `int`/`long` thông thường không tự mở rộng số bit. Kết quả có thể **tràn (overflow)** và quay vòng theo biểu diễn bù hai.

Ví dụ:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1;
System.out.println(overflowed); // -9223372036854775808
```

Kết quả toán học mong muốn là **9.223.372.036.854.775.808**, nhưng giá trị này lớn hơn `Long.MAX_VALUE`. Nếu nghiệp vụ cần giữ đúng con số đó, `long` không còn phù hợp.

**`java.math.BigInteger` là lựa chọn để lưu và tính số nguyên chính xác vượt miền của các primitive.** “Độ chính xác tùy ý” (*arbitrary precision*) nghĩa là số bit có thể tăng theo độ lớn của số, thay vì bị chốt ở 32 hoặc 64 bit. Điều đó **không có nghĩa là vô hạn về tài nguyên**: dung lượng bộ nhớ, thời gian xử lý và giới hạn triển khai vẫn hữu hạn.

## 2. Đừng chờ tràn rồi mới chuyển sang BigInteger

Sai lầm hay gặp nhất là tính bằng `long` trước, sau đó mới “cứu” bằng cách tạo `BigInteger`:

```java
long a = Long.MAX_VALUE;
long bad = a + 1;                      // đã tràn
BigInteger tooLate = BigInteger.valueOf(bad); // giữ giá trị âm đã sai
```

Phải **chuyển trước phép toán có nguy cơ tràn**:

```java
import java.math.BigInteger;

long a = Long.MAX_VALUE;
BigInteger correct = BigInteger.valueOf(a).add(BigInteger.ONE);
System.out.println(correct); // 9223372036854775808
```

Với phép nhân, quy tắc hoàn toàn tương tự:

```java
long x = 5_000_000_000L;
long y = 5_000_000_000L;

// long bad = x * y; // sẽ tràn long
BigInteger product = BigInteger.valueOf(x)
        .multiply(BigInteger.valueOf(y));
// product = 25000000000000000000
```

Tránh `new BigInteger(String.valueOf(x * y))`: phần `x * y` đã chạy bằng `long` và có thể tràn. Chuyển **toán hạng** trước, không chuyển **kết quả đã hỏng**.

Nếu yêu cầu là “vẫn dùng primitive nhưng phải biết khi nào tràn”, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` và `Math.negateExact` với `int`/`long`; các phương thức này ném `ArithmeticException` khi phép toán không vừa kiểu đích. Chúng **phát hiện tràn** chứ không tạo thêm độ rộng bit.

## 3. Chọn BigInteger dựa trên miền giá trị và yêu cầu nghiệp vụ

Các tình huống thường đáng dùng `BigInteger`:

- **Bộ đếm, lượng giao dịch hoặc số lượng tổ hợp** có miền tăng trưởng mà `long` không đủ để cam kết an toàn.
- **Giai thừa, tổ hợp, lũy thừa nguyên**: giá trị tăng rất nhanh, ngay cả khi đầu vào không lớn.
- **Thuật toán số học nguyên** cần phép chia lấy thương, GCD, phần dư, lũy thừa modulo hoặc các số lớn.
- **Giá trị nguyên từ hệ thống bên ngoài** dài hơn 64 bit cần giữ nguyên mọi chữ số.
- **Bài toán miền giá trị mở**: chưa có cận trên khả dụng hoặc giới hạn kinh doanh không đủ để bảo đảm `long` an toàn.

Không nên thay mọi `int` và `long` bằng `BigInteger` theo thói quen. Một chỉ số mảng, số thứ tự nhỏ, timestamp ở miền đã xác định hay bộ đếm bảo đảm không vượt `long` thường phù hợp với primitive hơn. Ngược lại, **không chọn kiểu từ giá trị mẫu hiện tại**: cần xét giá trị lớn nhất có thể xuất hiện khi hệ thống vận hành thực tế.

**Ví dụ từ giai thừa:**

```text
20! = 2432902008176640000    (còn vừa long)
21! = 51090942171709440000   (vượt Long.MAX_VALUE)
```

Đây là bằng chứng rõ ràng rằng `long` không thích hợp nếu chương trình cần tính giai thừa cho `n >= 21` và giữ kết quả chính xác. Chọn `BigInteger` ngay từ đầu vòng lặp:

```java
BigInteger result = BigInteger.ONE;
for (int i = 2; i <= 21; i++) {
    result = result.multiply(BigInteger.valueOf(i));
}
System.out.println(result); // 51090942171709440000
```

Lưu ý `BigInteger` không tự ngăn chương trình nhận đầu vào quá lớn như hàng triệu chữ số hay mũ khổng lồ. Bên cạnh chọn kiểu đúng vẫn phải có **giới hạn đầu vào** và **ngân sách tài nguyên**.

## 4. Khởi tạo BigInteger đúng cách

`BigInteger` thuộc gói `java.math`, là lớp bất biến (*immutable*) kế thừa `Number`. Nó không có cú pháp literal riêng như `123L`.

### 4.1. Từ long đã nằm trong miền

```java
BigInteger small = BigInteger.valueOf(123L);
BigInteger negative = BigInteger.valueOf(-45L);
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger ten = BigInteger.TEN;
```

Trong Java 17+ còn có `BigInteger.TWO`. Dùng các hằng chuẩn này khi phù hợp, tránh tạo lại đối tượng không cần thiết.

### 4.2. Từ chuỗi thập phân hoặc cơ số khác

Khi giá trị vượt miền `long`, cách dễ hiểu là truyền **chuỗi đầy đủ các chữ số**:

```java
BigInteger huge = new BigInteger("9223372036854775808");
BigInteger belowZero = new BigInteger("-999999999999999999999");
BigInteger hex = new BigInteger("FF", 16); // 255
BigInteger binary = new BigInteger("1010", 2); // 10
```

Constructor `new BigInteger(String, radix)` chấp nhận cơ số từ 2 đến 36. **Không** truyền tiền tố `0x` khi parse chuỗi cơ số 16 kiểu này:

```java
BigInteger hex = new BigInteger("FF", 16);   // đúng
// new BigInteger("0xFF", 16);               // NumberFormatException
```

Chuỗi không hợp lệ ném `NumberFormatException`; dữ liệu từ người dùng phải được validate và giới hạn độ dài trước khi parse.

### 4.3. Sai lầm: dùng literal long vượt miền

```java
// Không biên dịch: literal số nguyên này không vừa long
// BigInteger bad = BigInteger.valueOf(9223372036854775808L);

BigInteger good = new BigInteger("9223372036854775808");
```

Dấu phân cách `_` được cho phép trong **numeric literals của mã Java**, nhưng không được hiểu như dấu phân cách trong chuỗi thập phân đưa vào `new BigInteger("...")`.

## 5. BigInteger là immutable: phương thức trả về đối tượng mới

Khác với primitive có toán tử `+`, `-`, `*`, `/`, các phép tính thông thường trên `BigInteger` được gọi bằng **phương thức**:

| Nhu cầu | Phương thức `BigInteger` |
| --- | --- |
| Cộng | `a.add(b)` |
| Trừ | `a.subtract(b)` |
| Nhân | `a.multiply(b)` |
| Chia lấy thương nguyên | `a.divide(b)` |
| Chia lấy thương và số dư | `a.divideAndRemainder(b)` |
| Số dư theo phép chia nguyên | `a.remainder(b)` |
| Modulo với môđun dương | `a.mod(m)` |
| Đối dấu | `a.negate()` |
| Trị tuyệt đối | `a.abs()` |
| Lũy thừa nguyên | `a.pow(exponent)` |
| Ước số chung lớn nhất | `a.gcd(b)` |
| Dịch bit trái/phải | `a.shiftLeft(n)`, `a.shiftRight(n)` |

Vì **không thể sửa trực tiếp** đối tượng sau khi tạo, phải giữ giá trị trả về:

```java
BigInteger count = BigInteger.TEN;
count.add(BigInteger.ONE);         // trả về 11 nhưng bị bỏ
System.out.println(count);       // 10

count = count.add(BigInteger.ONE);
System.out.println(count);       // 11
```

Không thể viết `count++` hoặc `count += BigInteger.ONE`: Java không overload các toán tử số học cho `BigInteger`. Trong các phép tính liên tiếp, mã cần lưu kết quả một cách tường minh.

## 6. Phép chia và số dư: đặc biệt chú ý số âm

`BigInteger.divide()` trả **thương nguyên làm tròn về 0**, giống phép chia nguyên primitive của Java. Nếu số chia bằng 0, `ArithmeticException` được ném.

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);

System.out.println(a.divide(b));    // -3
System.out.println(a.remainder(b)); // -2
System.out.println(a.mod(b));       // 3
```

Sự khác nhau giữa `remainder` và `mod`:

- `a.remainder(b)` có số dư theo phép chia lấy thương hướng về 0; số dư khác 0 có **cùng dấu với số bị chia**.
- `a.mod(m)` yêu cầu **môđun dương** và trả phần dư **không âm** từ 0 đến `m - 1`.
- Dùng `divideAndRemainder(b)` khi cần cả thương và số dư cùng một lần tính.

```java
BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // -3
System.out.println(qr[1]); // -2
```

Chọn quy tắc số dư phù hợp bài toán. Với vòng đệm chỉ số tuần hoàn hoặc số học modulo, `mod(positiveModulus)` thường hợp lý hơn `remainder` khi số đầu vào có thể âm.

## 7. So sánh, dấu, và chuyển đổi chính xác

### 7.1. Không dùng toán tử so sánh primitive cho BigInteger

```java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = new BigInteger("99999999999999999999");

System.out.println(a.compareTo(b) > 0); // true
System.out.println(a.equals(b));        // false
```

`compareTo` trả giá trị âm, 0 hoặc dương tùy `a < b`, `a == b` hay `a > b`. `equals` so sánh giá trị số nguyên của hai `BigInteger`; khác với `BigDecimal`, `BigInteger` **không có scale** làm ảnh hưởng `equals`.

- `signum()`: trả `-1`, `0`, `1` tương ứng âm, bằng 0, dương.
- `min` và `max`: chọn giá trị nhỏ/lớn theo thứ tự.
- `bitLength()`: hỗ trợ ước lượng độ lớn nhị phân; đây không phải số chữ số thập phân.

Nếu có tham chiếu có thể `null`, xử lý `null` trước khi gọi các phương thức.

### 7.2. Phân biệt chuyển đổi mất dữ liệu và exact

Các phương thức kế thừa từ `Number`, như `intValue()` và `longValue()`, **không bảo đảm giữ nguyên giá trị** nếu giá trị vượt miền. Khi chuyển sang `long`, những bit cao có thể bị mất.

```java
BigInteger overLong = new BigInteger("9223372036854775808");
System.out.println(overLong.longValue()); // -9223372036854775808

// long bad = overLong.longValueExact(); // ném ArithmeticException
```

Nếu dữ liệu phải chính xác, ưu tiên `intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()`. Chúng ném `ArithmeticException` nếu giá trị không thể biểu diễn chính xác trong kiểu đích.

Các kiểm tra nên thực hiện tại **ranh giới API**: chuyển đối tượng BigInteger sang kiểu của database/JSON/SDK bên ngoài, trả kết quả cho module dùng `long`, hoặc ghi vào giao thức có giới hạn số bit. Dữ liệu đúng bên trong `BigInteger` vẫn có thể sai sau khi chuyển sang kiểu hẹp.

## 8. Tính toán với số lớn: tổ hợp và lũy thừa

`BigInteger` hữu ích khi số chữ số của kết quả tăng nhanh.

### 8.1. Lũy thừa nguyên

```java
BigInteger power = BigInteger.TWO.pow(100);
System.out.println(power);
// 1267650600228229401496703205376
```

`pow(exponent)` nhận số mũ kiểu `int` không âm. Nó tạo ra **số nguyên chính xác** nếu hoàn thành thành công, nhưng có thể dùng rất nhiều bộ nhớ với số mũ lớn. Các dạng `BigInteger` không biểu diễn phần thập phân: phép `divide` là chia nguyên, không phải chia chính xác cho một số hữu tỉ bất kỳ.

### 8.2. Đếm tổ hợp

Công thức `n!` tăng nhanh. Với hệ thống cần `n!`, `C(n,k)` hoặc các số đếm tổ hợp, các phép nhân trung gian cũng có thể vượt `long`.

Ví dụ cách tính `C(n,k)` mà không tạo ba giai thừa rất lớn:

```java
import java.math.BigInteger;

public static BigInteger choose(int n, int k) {
    if (n < 0 || k < 0 || k > n) {
        throw new IllegalArgumentException("Require 0 <= k <= n");
    }

    k = Math.min(k, n - k);
    BigInteger result = BigInteger.ONE;
    for (int i = 1; i <= k; i++) {
        // Mỗi bước chia hết theo tính chất của hệ số tổ hợp.
        result = result.multiply(BigInteger.valueOf((long) n - k + i))
                       .divide(BigInteger.valueOf(i));
    }
    return result;
}
```

Đây là **phương thức minh họa** cần đặt trong một lớp Java để chạy; nó không phải chương trình hoàn chỉnh. Kiểu `long` ở `(long) n - k + i` giúp phép tính tạo thừa số tránh tràn `int` trong các giá trị biên. Mỗi bước là số nguyên vì tích lũy công thức tổ hợp được chia hết cho `i`.

## 9. Kiểm tra overflow trước hay dùng BigInteger từ đầu?

Một số hệ thống đặt yêu cầu khác nhau:

| Yêu cầu | Hướng giải quyết |
| --- | --- |
| Biết chắc miền trong `int`/`long` | Dùng primitive, kiểm tra đầu vào nếu cần |
| Cần giữ primitive nhưng phải chặn phép toán vượt miền | Dùng `Math.*Exact`; xử lý `ArithmeticException` |
| Phép toán có thể vượt `long`, kết quả phải là số nguyên chính xác | Chuyển các toán hạng sang `BigInteger` **trước** phép tính |
| Kết quả lớn, nhưng cổng xuất chỉ nhận `long` | Giữ `BigInteger` ở lõi, kiểm tra biên/ `longValueExact()` tại cổng xuất |
| Số liệu có phần thập phân và cần làm tròn theo quy tắc nghiệp vụ | Dùng `BigDecimal`, không dùng `BigInteger` trực tiếp |

Ví dụ một phép cộng đòi **báo lỗi** khi vượt `long`:

```java
long total = Math.addExact(current, incoming);
```

Nếu cùng phép cộng đòi **lưu lại kết quả chính xác dù vượt `long`**:

```java
BigInteger total = BigInteger.valueOf(current)
        .add(BigInteger.valueOf(incoming));
```

Chọn theo **hợp đồng dữ liệu**. Đừng nuốt ngoại lệ từ `Math.addExact` rồi âm thầm ghi giá trị đã quay vòng; cũng đừng tự tiện trả một chuỗi BigInteger cho API vốn bắt buộc kiểu 64 bit mà chưa định nghĩa cách trao đổi giá trị.

## 10. BigInteger và biểu diễn nhị phân có dấu/không dấu

`BigInteger` là số nguyên **có dấu**. Bạn có thể parse chuỗi thập phân dương rất lớn, nhưng khi đọc **mảng byte**, cách diễn giải dấu phải được chọn rõ.

Ví dụ hai byte `FF 00`:

```java
byte[] bytes = {(byte) 0xFF, 0x00};

BigInteger signed = new BigInteger(bytes);
BigInteger unsigned = new BigInteger(1, bytes);

System.out.println(signed);   // -256
System.out.println(unsigned); // 65280
```

Constructor `new BigInteger(byte[])` xem các byte theo bù hai, thứ tự byte lớn trước (*big-endian*). Constructor `new BigInteger(signum, magnitude)` dùng một dấu riêng và phần độ lớn không dấu. **Không mặc định mọi byte[] là số dương** nếu byte cao nhất có bit dấu 1.

Khi xuất byte bằng `toByteArray()`, kết quả là biểu diễn bù hai theo thứ tự big-endian với số byte đủ để bảo toàn dấu; một số dương có bit cao nhất bằng 1 có thể cần byte `00` dẫn đầu. Nếu giao thức đòi chiều dài byte cố định hoặc unsigned, phải kiểm tra độ dài, dấu và padding trước khi ghi.

Với một mẫu 64 bit muốn diễn giải theo **unsigned long**:

```java
long bits = -1L; // 64 bit đều là 1
BigInteger unsigned64 =
        new BigInteger(Long.toUnsignedString(bits));
System.out.println(unsigned64); // 18446744073709551615
```

`BigInteger.valueOf(bits)` sẽ là `-1` vì nó giữ **giá trị signed long**, không đổi sang unsigned. Dùng `Long.toUnsignedString` (hoặc chuyển bằng xử lý bit đã kiểm chứng) khi đặc tả nguồn định nghĩa 64 bit không dấu.

## 11. Bộ nhớ, hiệu năng và giới hạn an toàn

Mỗi `BigInteger` là một đối tượng, chứa dữ liệu cho độ lớn số nguyên. Số càng nhiều bit thì các phép toán càng tiêu tốn thời gian và bộ nhớ. Phép nhân các số rất lớn, `pow` với mũ lớn, chuyển đổi sang chuỗi thập phân hoặc parse hàng triệu chữ số có thể tốn nhiều tài nguyên.

**Các nguyên tắc thực hành:**

1. Giới hạn độ dài chuỗi đầu vào, miền của số mũ, số vòng lặp và số chữ số kết quả **theo yêu cầu sản phẩm**.
2. Nếu cần số nguyên có nhiều chữ số nhưng lại phải chạy trong luồng xử lý thời gian thực, đo hiệu năng với cỡ dữ liệu thực tế.
3. Tránh tạo chuỗi kết quả cực dài chỉ để log; giới hạn log và kiểm tra thông tin cần thiết.
4. Với tính toán số lượng lớn, định rõ yêu cầu thời gian và bộ nhớ; không giả định `BigInteger` bảo đảm hoàn thành cho mọi giá trị.
5. Không dùng `BigInteger` làm phương án giải quyết bài toán cần **số thực**: `divide` vẫn là chia nguyên. Với tiền và số thập phân chính xác cần scale/rounding, chọn `BigDecimal`.

Đừng áp dụng “`BigInteger` luôn tốt hơn vì không tràn” cho mọi trường hợp. Nó giúp **giữ đúng giá trị nguyên** khi miền lớn nhưng cần thiết kế giới hạn chi phí rõ ràng.

## 12. Chương trình Java 17+ chạy độc lập

Tạo file **`BigIntegerOverflowDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerOverflowDemo {
    public static void main(String[] args) {
        long max = Long.MAX_VALUE;
        System.out.println("long overflow = " + (max + 1));

        BigInteger safe = BigInteger.valueOf(max).add(BigInteger.ONE);
        System.out.println("long max + 1 = " + safe);

        BigInteger factorial = BigInteger.ONE;
        for (int i = 2; i <= 21; i++) {
            factorial = factorial.multiply(BigInteger.valueOf(i));
        }
        System.out.println("21! = " + factorial);
        System.out.println("21! exceeds long = "
                + (factorial.compareTo(BigInteger.valueOf(max)) > 0));

        try {
            factorial.longValueExact();
            System.out.println("21! fits long");
        } catch (ArithmeticException ex) {
            System.out.println("21! cannot fit in long");
        }

        BigInteger a = BigInteger.valueOf(-17);
        BigInteger b = BigInteger.valueOf(5);
        System.out.println("-17 / 5 = " + a.divide(b));
        System.out.println("-17 remainder 5 = " + a.remainder(b));
        System.out.println("-17 mod 5 = " + a.mod(b));

        byte[] bytes = {(byte) 0xFF, 0x00};
        System.out.println("FF00 signed = " + new BigInteger(bytes));
        System.out.println("FF00 unsigned = " + new BigInteger(1, bytes));

        BigInteger original = BigInteger.TEN;
        BigInteger changed = original.add(BigInteger.ONE);
        System.out.println("immutable: " + original + ", " + changed);
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```bash
javac BigIntegerOverflowDemo.java
java BigIntegerOverflowDemo
```

**Kết quả chuẩn:**

```text
long overflow = -9223372036854775808
long max + 1 = 9223372036854775808
21! = 51090942171709440000
21! exceeds long = true
21! cannot fit in long
-17 / 5 = -3
-17 remainder 5 = -2
-17 mod 5 = 3
FF00 signed = -256
FF00 unsigned = 65280
immutable: 10, 11
```

Chương trình cho thấy điểm khác biệt giữa **tràn primitive** và **tính số nguyên chính xác**, giữa **chuyển kiểu có thể mất dữ liệu** và **chuyển kiểu exact**, giữa **remainder** và **mod**, cũng như ý nghĩa dấu của byte và tính bất biến của `BigInteger`.

## 13. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Tính `long * long` rồi mới bọc vào BigInteger | Tích có thể đã tràn trước khi bọc | Chuyển toán hạng bằng `valueOf` trước `multiply` |
| Gõ số vượt `long` như literal có hậu tố `L` | Không biên dịch | Dùng `new BigInteger("...")` |
| Viết `value + BigInteger.ONE` | Không có overload toán tử `+` cho BigInteger | Dùng `value.add(BigInteger.ONE)` |
| Gọi `count.add(ONE)` mà không gán | Đối tượng cũ không đổi | `count = count.add(ONE)` |
| Dùng `longValue()` khi cần chính xác | Có thể mất bit cao và tạo số âm ngoài ý muốn | Dùng `longValueExact()` |
| Dùng `==` để so sánh hai BigInteger | So sánh tham chiếu, không phải giá trị | Dùng `equals` hoặc `compareTo` |
| Nghĩ `divide` giữ cả phần thập phân | Thương nguyên cắt phần lẻ | Dùng BigDecimal nếu thực sự cần số thập phân |
| Nghĩ `remainder` luôn không âm | Với số bị chia âm, phần dư có thể âm | Xác định rõ cần `remainder` hay `mod` |
| Đọc byte có bit cao là 1 mà mặc định unsigned | Giá trị có thể thành số âm | Xác định signedness, dùng constructor phù hợp |
| Tin rằng độ chính xác tùy ý là tài nguyên vô hạn | Có thể hết bộ nhớ, tốn CPU | Giới hạn đầu vào/mũ/đầu ra theo hệ thống |

## 14. Bài tập và lời giải

**Bài 1.** Vì sao `BigInteger.valueOf(Long.MAX_VALUE + 1)` **không** phải cách tính đúng `Long.MAX_VALUE + 1`?  
**Lời giải:** phép cộng chạy theo `long`, đã tràn thành `Long.MIN_VALUE`. Cách đúng: `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)`.

**Bài 2.** Giai thừa `20!` và `21!` có vừa `long` không?  
**Lời giải:** `20! = 2432902008176640000` còn vừa; `21! = 51090942171709440000` vượt `Long.MAX_VALUE`. Chọn `BigInteger` nếu cần `21!` chính xác.

**Bài 3.** `new BigInteger("9223372036854775808").longValueExact()` làm gì?  
**Lời giải:** ném `ArithmeticException` vì số lớn hơn miền dương của `long`. Gọi `longValue()` lại có thể trả giá trị âm sai với ý định, nên `Exact` phù hợp khi hợp đồng yêu cầu giữ nguyên số.

**Bài 4.** Với `a = -17` và `b = 5`, `a.remainder(b)` và `a.mod(b)` bằng mấy?  
**Lời giải:** lần lượt **−2** và **3**; `mod` yêu cầu môđun dương và kết quả không âm.

**Bài 5.** Có thể dùng `BigInteger` thay `BigDecimal` để cộng chính xác `0.10 + 0.20` trực tiếp không?  
**Lời giải:** không theo nghĩa số thập phân trực tiếp; `BigInteger` biểu diễn **số nguyên**. Có thể quy đổi sang đơn vị nguyên nhỏ nhất nếu nghiệp vụ đã xác định thang đo, nhưng nếu cần phép tính thập phân có scale và rounding, sử dụng `BigDecimal` thường rõ ràng hơn.

**Bài 6.** Hai byte `FF 00` được đọc bằng `new BigInteger(bytes)` và `new BigInteger(1, bytes)` cho giá trị nào?  
**Lời giải:** lần lượt **−256** và **65280**; constructor đầu dùng bù hai có dấu, constructor sau đặt dấu dương và diễn giải magnitude không dấu.

**Bài 7.** Một hệ thống lưu số lượng sản phẩm tối đa 1 triệu và không thực hiện phép nhân gây tràn. Có cần `BigInteger` không?  
**Lời giải:** thường không; `int` có miền đủ lớn. Tính đúng phụ thuộc cả phép tính trung gian và ràng buộc dữ liệu, nên cần kiểm tra tổng/tích nếu nghiệp vụ sử dụng chúng.

## 15. Checklist trước khi quyết định dùng BigInteger

1. **Miền giá trị:** có cận dưới/trên đáng tin hay có thể vượt `long`?
2. **Phép tính trung gian:** ngay cả khi đầu vào vừa `long`, tích, giai thừa hoặc tổng nhiều giá trị có thể vượt ngưỡng không?
3. **Yêu cầu lỗi:** cần báo tràn bằng `Math.*Exact` hay cần tiếp tục tính với số nguyên lớn chính xác?
4. **Nguồn đầu vào:** là `long` đã hợp lệ, chuỗi chữ số rất dài, hay mảng byte cần xác định signedness?
5. **Cổng ra:** có thể lưu/xuất giá trị lớn hay sẽ phải chuyển về `int`/`long`? Nếu chuyển, có dùng `*ValueExact()` không?
6. **Ý nghĩa phép chia:** đang cần thương nguyên, số dư, modulo hay số thập phân chính xác?
7. **Chi phí:** đã có giới hạn độ dài đầu vào, số mũ, số vòng lặp và kích thước kết quả chưa?

**Ghi nhớ:** Khi `int`/`long` không đủ miền biểu diễn nhưng vẫn cần **số nguyên chính xác**, đưa toán hạng vào `BigInteger` **trước phép tính**, dùng phương thức thay toán tử số học, giữ giá trị trả về vì đối tượng bất biến, và kiểm tra biên khi chuyển ra kiểu hữu hạn. “Tùy ý độ chính xác” giải quyết bài toán **giới hạn số bit**, đồng thời đòi hỏi quản lý **giới hạn tài nguyên**.
