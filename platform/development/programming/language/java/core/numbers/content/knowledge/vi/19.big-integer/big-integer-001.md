# BigInteger: Số nguyên độ chính xác tùy ý và tính bất biến trong Java

`java.math.BigInteger` là lớp biểu diễn **số nguyên có dấu với độ chính xác tùy ý** (*arbitrary-precision signed integer*) trong Java. Khác với `int` có 32 bit và `long` có 64 bit, `BigInteger` không buộc giá trị vào độ rộng cố định đó. Khi cộng, nhân hoặc dịch bit để tạo một số lớn hơn, thư viện có thể mở rộng biểu diễn nội bộ thay vì tự động cho kết quả tràn theo bù hai 32/64 bit.

Đồng thời, `BigInteger` là **bất biến** (*immutable*): sau khi một đối tượng được tạo, **giá trị của chính đối tượng đó không đổi**. Các phép toán như `add`, `multiply`, `subtract`, `pow` tạo/trả một đối tượng đại diện cho kết quả; biến tham chiếu phải được gán lại nếu muốn tiếp tục dùng kết quả mới.

```java
import java.math.BigInteger;

BigInteger original = BigInteger.valueOf(Integer.MAX_VALUE);
BigInteger next = original.add(BigInteger.ONE);

System.out.println(original); // 2147483647
System.out.println(next);     // 2147483648
```

Ở đây `original` **không** bị sửa. Kết quả `next` vượt `Integer.MAX_VALUE` mà vẫn chính xác. Tuy nhiên “tùy ý” không có nghĩa vô hạn tài nguyên: bộ nhớ, kích thước đối tượng, thời gian tính toán và các giới hạn triển khai vẫn tồn tại.

## 1. Vì sao cần `BigInteger` khi Java đã có `int` và `long`?

Các primitive nguyên có miền giá trị cố định:

| Kiểu | Số bit | Miền giá trị có dấu |
| --- | ---: | --- |
| `byte` | 8 | −128 đến 127 |
| `short` | 16 | −32.768 đến 32.767 |
| `int` | 32 | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `BigInteger` | Không có một độ rộng 32/64 bit cố định | Số nguyên âm, 0 và dương rất lớn, giới hạn bởi triển khai/tài nguyên |

Với phép cộng `int` thông thường, khi kết quả vượt miền, Java giữ kết quả theo quy tắc tràn số nguyên:

```java
int a = Integer.MAX_VALUE;
System.out.println(a + 1); // -2147483648: overflow.
```

`BigInteger` tránh tràn **theo giới hạn primitive** bằng cách dùng cấu trúc biểu diễn có thể mở rộng:

```java
BigInteger a = BigInteger.valueOf(Integer.MAX_VALUE);
System.out.println(a.add(BigInteger.ONE)); // 2147483648.
```

Một số lớn vượt cả `long` cũng được biểu diễn bằng `BigInteger`:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
System.out.println(beyondLong); // 9223372036854775808.
```

**Quan trọng:** `BigInteger` vẫn là **số nguyên**. Nó không có phần thập phân; `1 / 2` bằng 0 theo phép chia nguyên của lớp này. Nếu bài toán đòi hỏi thập phân chính xác và scale, xem `BigDecimal`. Nếu chỉ cần số đếm trong miền `int`/`long`, không nên mặc định chọn `BigInteger` bởi nó có thêm chi phí bộ nhớ, đối tượng và phép toán.

## 2. Bản chất và quan hệ kiểu của `BigInteger`

`BigInteger` thuộc package `java.math`; khác `Integer` và `Long` trong `java.lang`, bạn cần `import java.math.BigInteger;` hoặc dùng tên đầy đủ.

Nó là một **lớp tham chiếu**:
- Kế thừa `Number`, do đó có `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`.
- Triển khai `Comparable<BigInteger>`, nên có `compareTo`.
- Là **immutable** và có API toán học trên đối tượng.
- Không có toán tử cộng/trừ/nhân/chia được overload trên các đối tượng như ở một số ngôn ngữ khác.

```java
BigInteger x = BigInteger.valueOf(12);
BigInteger y = BigInteger.valueOf(5);

// BigInteger z = x + y; // Không biên dịch.
BigInteger z = x.add(y); // 17.
```

Đừng nhầm `BigInteger` với `Integer`:
- `Integer` là wrapper bất biến của primitive `int` 32 bit.
- `BigInteger` lưu một số nguyên không bị giới hạn về chính xác ở 32 bit và có nhiều phương thức tính toán.
- `BigInteger` không phải subtype của `Integer`, và `BigInteger` cũng không tự unbox thành `int`.

Việc hai kiểu cùng kế thừa `Number` không đồng nghĩa có thể ép tham chiếu tùy ý giữa chúng.

## 3. Tạo đối tượng `BigInteger` đúng cách

### 3.1. Từ `long` với `valueOf`

```java
BigInteger a = BigInteger.valueOf(42);
BigInteger b = BigInteger.valueOf(-17);
BigInteger c = BigInteger.valueOf(Long.MAX_VALUE);
```

`BigInteger.valueOf(long)` nhận **giá trị `long`**. Nó phù hợp khi đầu vào vốn nằm trong miền 64 bit.

```java
// BigInteger wrong = BigInteger.valueOf(99999999999999999999999L);
// Literal long quá lớn: lỗi biên dịch, BigInteger không thể cứu trước đó.
```

Nếu giá trị **vượt `long`**, tạo trực tiếp từ chuỗi chữ số có kiểm soát.

### 3.2. Từ chuỗi decimal bằng constructor

```java
BigInteger population =
        new BigInteger("123456789012345678901234567890");

BigInteger negative = new BigInteger("-12345678901234567890");
BigInteger zero = new BigInteger("0");
```

`new BigInteger(String)` mặc định parse thập phân, có thể xử lý dấu `+` hoặc `-` đầu chuỗi hợp lệ. Nếu văn bản không hợp lệ, constructor ném `NumberFormatException`:

```java
// new BigInteger("12.5");      // Sai: có phần thập phân.
// new BigInteger("1_000");     // Sai: underscore không được nhận như literal.
// new BigInteger(" 100 ");     // Sai: có khoảng trắng chưa xử lý.
// new BigInteger("0xFF");      // Sai: không tự đoán tiền tố hex.
```

Các lời gọi trên được **chú thích** vì cố ý minh họa lỗi, không phải mã cần chạy liên tiếp.

### 3.3. Từ chuỗi ở cơ số 2–36

```java
BigInteger hex = new BigInteger("ff", 16);     // 255.
BigInteger binary = new BigInteger("1010", 2); // 10.
BigInteger signed = new BigInteger("-ff", 16); // -255.
```

Tham số `radix` nêu cơ số. Constructor `BigInteger(String,int)` không mặc định hiểu `0x`/`0b`; chuỗi phải chứa chữ số phù hợp cơ số và dấu hợp lệ. `toString(int radix)` thực hiện chiều ngược lại:

```java
System.out.println(hex.toString(16)); // ff.
System.out.println(binary.toString(2)); // 1010.
```

Nếu đầu vào là một **mã định danh** có số 0 đầu cần giữ nguyên, đừng tự chuyển sang `BigInteger` khi không cần số học: giá trị nguyên không lưu lại độ rộng hay cách nhóm chữ số của chuỗi gốc.

### 3.4. Các hằng số hữu ích

JDK cung cấp:

```java
BigInteger.ZERO
BigInteger.ONE
BigInteger.TWO
BigInteger.TEN
```

Trong Java 17, các hằng trên có sẵn (ví dụ `BigInteger.TWO` từ Java 9). Chúng là các **đối tượng bất biến có thể dùng chung**.

```java
BigInteger count = BigInteger.ZERO;
count = count.add(BigInteger.ONE);
```

Dùng `BigInteger.ZERO` giúp rõ nghĩa hơn `new BigInteger("0")`. Tuy nhiên không giả định các kết quả phép toán khác nhau luôn là cùng object khi bằng giá trị; dùng `equals` cho so sánh giá trị.

## 4. Tính bất biến: các phép toán không sửa đối tượng gốc

Một ví dụ sai thường gặp:

```java
BigInteger total = BigInteger.ZERO;
total.add(BigInteger.TEN);
System.out.println(total); // 0, không phải 10!
```

`add` đã tạo/trả **kết quả**, nhưng chương trình không lưu kết quả. Để cập nhật biến `total`, gán lại:

```java
BigInteger total = BigInteger.ZERO;
total = total.add(BigInteger.TEN);
System.out.println(total); // 10.
```

Điều này không làm đối tượng cũ đổi giá trị. Java chỉ đổi **tham chiếu đang nằm trong biến `total`**.

### Hình dung bằng hai biến cùng tham chiếu

```java
BigInteger a = new BigInteger("100");
BigInteger alias = a;
a = a.add(BigInteger.ONE);

System.out.println(a);     // 101.
System.out.println(alias); // 100.
```

Ban đầu hai biến `a` và `alias` tham chiếu cùng một `BigInteger(100)`. Sau phép gán lại, `a` tham chiếu kết quả 101; `alias` vẫn thấy đối tượng giá trị 100 không đổi.

### Lợi ích của immutable

1. **Ít hiệu ứng phụ:** hàm nhận `BigInteger` không thể làm thay giá trị nội tại của đối tượng mà caller đang giữ.
2. **Dễ chia sẻ:** cùng một giá trị có thể được nhiều nơi giữ tham chiếu mà không bị sửa trạng thái số.
3. **Thuận tiện làm key:** `BigInteger` cung cấp `equals` và `hashCode` theo giá trị, phù hợp cho `HashMap` hoặc `HashSet`.
4. **Đơn giản hóa luồng đồng thời:** một đối tượng `BigInteger` đã được công bố an toàn có thể được nhiều luồng đọc mà không cần khóa để ngăn sửa giá trị đó.
5. **Dễ lập luận:** biểu thức `a.add(b)` trả kết quả và giữ `a`, `b` nguyên vẹn.

**Giới hạn của nhận định về thread safety:** tính bất biến của `BigInteger` **không làm phép gán lại một biến dùng chung trở thành atomic**. Chẳng hạn `counter = counter.add(ONE)` trên một biến dùng chung có thể mất cập nhật khi nhiều luồng đồng thời đọc/gán. Với bộ đếm đồng thời, cần đồng bộ phù hợp hoặc công cụ atomic cho bài toán tương ứng.

### Không có `++` và `+=` trên `BigInteger`

```java
BigInteger n = BigInteger.ZERO;
// n++;       // Không biên dịch.
// n += 1;    // Không biên dịch.
n = n.add(BigInteger.ONE); // Đúng.
```

Việc cần tạo giá trị mới là một phần **mô hình API**, không phải một chi tiết riêng của `add`. `multiply`, `subtract`, `negate`, `abs`, `shiftLeft`... đều không biến đối tượng nhận lời gọi thành giá trị khác.

## 5. Các phép toán số học thường dùng

| Phương thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `a.add(b)` | `a + b` | `12 + 5 = 17` |
| `a.subtract(b)` | `a - b` | `12 - 5 = 7` |
| `a.multiply(b)` | `a × b` | `12 × 5 = 60` |
| `a.divide(b)` | Thương nguyên, cắt về 0 | `12 / 5 = 2` |
| `a.remainder(b)` | Phần dư theo phép chia nguyên | `12 % 5 = 2` |
| `a.divideAndRemainder(b)` | Trả mảng hai phần tử [thương, dư] | `[2, 2]` |
| `a.pow(n)` | Lũy thừa với số mũ nguyên `int` không âm | `12^2 = 144` |
| `a.negate()` | Đổi dấu | `-12` |
| `a.abs()` | Giá trị tuyệt đối | `12` |
| `a.gcd(b)` | Ước chung lớn nhất không âm | `gcd(54,24) = 6` |
| `a.signum()` | Dấu của số | −1, 0 hoặc 1 |
| `a.min(b)` / `a.max(b)` | Giá trị nhỏ/lớn hơn | So sánh hai BigInteger |

```java
BigInteger a = BigInteger.valueOf(12);
BigInteger b = BigInteger.valueOf(5);

System.out.println(a.add(b));      // 17
System.out.println(a.subtract(b)); // 7
System.out.println(a.multiply(b)); // 60
System.out.println(a.divide(b));   // 2
System.out.println(a.remainder(b)); // 2
```

Các phép toán trên **không phải overload toán tử Java**. Ví dụ `a.multiply(b)` trả một `BigInteger`, không thay `a`. `divide` và `remainder` ném `ArithmeticException` khi số chia bằng 0.

### Phép cộng vào biến kết quả trong vòng lặp

```java
BigInteger sum = BigInteger.ZERO;

for (int i = 1; i <= 100; i++) {
    sum = sum.add(BigInteger.valueOf(i));
}
System.out.println(sum); // 5050.
```

Nếu bỏ `sum =` ở bên trái, kết quả sẽ vẫn là 0. Đây là lỗi **bỏ quên reassignment** do quen với đối tượng mutable.

## 6. Chia nguyên, `remainder` và `mod` khác nhau

`BigInteger.divide(b)` lấy thương nguyên **cắt về 0**; `remainder(b)` là phần dư tương ứng và có thể âm. Với `a=-17,b=5`, thương bằng `-3` và dư bằng `-2`, thỏa `a=q*b+r`. Nếu cần một phần dư không âm, `mod(m)` chọn đại diện trong `[0,m)` nhưng **đòi `m>0`**. Các phép chia cho zero báo `ArithmeticException`. Cách lấy đồng thời thương và dư, kiểm tra chia hết sẽ được thực hành riêng.

## 7. Lũy thừa, dịch bit, GCD và modular arithmetic

`pow(int)` tính lũy thừa nguyên với số mũ không âm; `sqrt()` lấy căn bậc hai nguyên của giá trị không âm; `gcd(b)` lấy ước chung lớn nhất không âm. `shiftLeft(n)` làm việc với bit của số nguyên có dấu, khác biểu diễn một word 32/64 bit cố định. Trong số học đồng dư, `modPow(e,m)` tính lũy thừa modulo hiệu quả, còn `modInverse(m)` chỉ tồn tại khi giá trị và modulus nguyên tố cùng nhau. Đây là những API có các điều kiện đầu vào riêng, được giải thích cùng bài tập cụ thể ở các bài chuyên sâu.

## 8. Chuyển đổi sang `int`, `long` và bẫy mất dữ liệu

`intValue()` và `longValue()` có thể **cắt bit cao**, chẳng hạn `BigInteger.ONE.shiftLeft(32).intValue()` bằng 0. Nếu hợp đồng API cần giữ đúng giá trị, dùng `intValueExact()` hoặc `longValueExact()` và xử lý `ArithmeticException` khi không vừa miền signed tương ứng. Chuyển kiểu nên đặt ở ranh giới mà ứng dụng thật sự cần primitive, không thực hiện sớm trong phép tính lớn.

## 9. So sánh, equality và thứ tự

`a.compareTo(b)` xác định quan hệ nhỏ/bằng/lớn từ dấu số trả về; `a.equals(b)` so cùng giá trị `BigInteger`; `a == b` chỉ so tham chiếu. `signum()` trả -1, 0 hoặc 1; `abs()` và `negate()` thao tác độ lớn hoặc số đối và vẫn giữ đối tượng nguồn bất biến. Những quy tắc này quan trọng cho mã sắp xếp, kiểm tra biên và khóa collection.

## 10. Hai cách hiểu khác nhau của mảng byte

`new BigInteger(bytes)` giải mã **signed two's complement big-endian**, nên một byte `FF` là `-1`. `new BigInteger(1,bytes)` nhận magnitude unsigned với dấu dương riêng, nên byte `FF` là `+255`. `toByteArray()` xuất signed two's complement tối thiểu; số dương 128 cần `00 80` để giữ bit dấu 0. Khi giao thức đòi fixed-width hoặc unsigned, cần định rõ width, padding và kiểm tra miền thay vì bỏ byte đầu tùy tiện.

## 11. Bit operations không có giới hạn 32/64 bit mặc định

`and`, `or`, `xor`, `not`, `shiftLeft`, `shiftRight`, `testBit` và `setBit` tuân mô hình bù hai **mở rộng dấu**. Vì thế `BigInteger.valueOf(5).not()` là -6 thay vì giá trị 250 của phép đảo **8 bit unsigned**. Nếu phải mô phỏng word có độ rộng `w`, cần đặt mask `2^w - 1` phù hợp. Chi tiết bitLength, bitCount và thao tác vị trí bit được tách thành bài học riêng.

## 12. Giới hạn thật của “độ chính xác tùy ý”

“Arbitrary precision” nghĩa là **không bị buộc vào độ rộng primitive cố định**, không có nghĩa hệ thống có bộ nhớ hay thời gian vô hạn.

Các giới hạn thực tế gồm:

1. **Bộ nhớ heap:** một số với hàng triệu chữ số cần bộ nhớ lớn để lưu và thao tác.
2. **Thời gian tính toán:** nhân/chia/GCD/modPow trên số có hàng triệu bit tốn nhiều hơn phép toán primitive.
3. **Giới hạn kích thước và implementation:** JDK có các giới hạn nội bộ cho số bit hoặc độ dài mảng; không thể tạo tùy ý đến vô tận.
4. **Đầu vào không tin cậy:** chuỗi số dài khổng lồ, số mũ `pow` lớn hoặc lời gọi xây số ngẫu nhiên có thể gây tiêu thụ tài nguyên ngoài dự kiến.
5. **Chuyển đổi ra kiểu cố định:** khi gọi `intValue`, `longValue` hay `doubleValue`, bạn lại chịu giới hạn của kiểu đích.
6. **Truyền tải và định dạng:** một số rất lớn thành chuỗi decimal có thể dài hàng MB, kéo theo phí ghi log, JSON, CSV hay database.

**Không đặt `BigInteger` vào vòng lặp nóng chỉ vì “an toàn hơn int” nếu bài toán chỉ cần số nhỏ.** Đối với phép cộng hàng triệu phần tử trong miền `long`, `long` có thể đơn giản và hiệu quả hơn. Khi cần phát hiện tràn primitive, có thể dùng `Math.addExact`/`multiplyExact` hoặc nâng cấp lên `BigInteger` theo yêu cầu cụ thể.

### Lưu ý với thuật toán giai thừa

Giai thừa tăng rất nhanh. `20!` nằm trong miền `long`, nhưng `21!` đã vượt miền `long` signed. Với `BigInteger`:

```java
static BigInteger factorial(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }
    BigInteger result = BigInteger.ONE;
    for (int i = 2; i <= n; i++) {
        result = result.multiply(BigInteger.valueOf(i));
    }
    return result;
}
```

Đây là **phương thức minh họa**, cần đặt trong class. Nó vẫn cần **giới hạn `n`** khi nhận input từ người dùng để tránh yêu cầu tài nguyên quá lớn. `BigInteger` cho độ chính xác, không tự tạo quota tính toán.

### “Exact arithmetic” không đồng nghĩa “kết quả mọi phép toán có thể biểu diễn”

Cộng, trừ, nhân số nguyên phù hợp trong miền được JDK hỗ trợ đều là phép toán chính xác, không có sai số làm tròn dấu phẩy động. Nhưng phép **chia nguyên** vẫn bỏ phần phân số vì kiểu kết quả là số nguyên. `BigInteger.ONE.divide(BigInteger.TWO)` trả 0; muốn biểu diễn `1/2` phải chọn phân số gồm tử/mẫu BigInteger hoặc một mô hình decimal có chính sách rounding.

## 13. Ngẫu nhiên, số nguyên tố và mật mã: cần thêm hợp đồng

`BigInteger` có một số API sinh số lớn/ngẫu nhiên và làm việc với số nguyên tố, chẳng hạn `probablePrime`, `isProbablePrime`, `nextProbablePrime` và các phép modular. Đây là API toán học rất hữu ích, nhưng cần hiểu phạm vi:

- `isProbablePrime(certainty)` liên quan đến kiểm tra nguyên tố xác suất với mức chắc chắn theo hợp đồng API, **không** nên tùy tiện đọc là phép chứng minh toán học tuyệt đối.
- Nếu tạo tham số cho mật mã, nguồn ngẫu nhiên và cách chọn tham số phải đúng chuẩn; `java.util.Random` không phải lựa chọn mặc định cho bí mật.
- `BigInteger` không cam kết mọi thao tác là **constant-time**; đừng tự chế primitive mật mã rồi cho rằng “số học BigInteger chính xác” đồng nghĩa an toàn trước side-channel.
- Với khóa, chữ ký, mã hóa, hãy dùng các API `java.security`/`javax.crypto` và chuẩn giao thức phù hợp thay vì tự ghép những phép BigInteger riêng.

Trong bài học nhập môn, xem modular arithmetic và nguyên tố như **khả năng bổ sung**, không làm lu mờ hai thuộc tính chính: **độ chính xác tùy ý** và **tính bất biến**.

## 14. Xử lý đầu vào và dữ liệu trao đổi

Khi nhận số nguyên rất lớn từ người dùng, file hoặc API:

```java
String text = "123456789012345678901234567890";
BigInteger value = new BigInteger(text);
```

Nên có quy trình:

1. Xác định schema: signed/unsigned, radix, cho phép dấu +/− hay không, có nhóm chữ số hay không.
2. Giới hạn độ dài chuỗi và miền giá trị **trước** khi tạo đối tượng rất lớn.
3. Không suy đoán prefix `0x` hoặc underscore trong runtime `String`: `new BigInteger("0xFF")` không tự parse hex như compiler.
4. Bắt `NumberFormatException` ở ranh giới dữ liệu và trả lỗi có ngữ cảnh.
5. Định nghĩa cách serialize: decimal string, radix cụ thể, hoặc bytes signed/unsigned, với độ rộng và byte order rõ ràng.
6. Nếu bên nhận dùng JavaScript `Number`, lưu ý các số nguyên vượt `2^53` có thể mất chính xác; **decimal string theo schema** thường phù hợp cho ID lớn và số cần chính xác tuyệt đối.
7. Không gửi kết quả `doubleValue` rồi xem đó là bản sao hoàn hảo của BigInteger ban đầu.

`BigInteger.toString()` tạo chuỗi thập phân không có grouping locale:

```java
BigInteger big = new BigInteger("12345678901234567890");
String wireText = big.toString(); // "12345678901234567890".
```

Đây là cách biểu diễn tốt nếu giao thức **đã quy định decimal string**. Nếu schema dùng JSON number, việc dùng một thư viện JSON có kiểu thích hợp cũng có thể hợp lý, nhưng cần đánh giá toàn bộ bên nhận và yêu cầu precision. Không tự đánh đồng `toString` với một serializer JSON đầy đủ.

## 15. Chương trình Java 17+ chạy độc lập

Lưu tệp `BigIntegerBasicsDemo.java`:

```java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerBasicsDemo {
    static BigInteger factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        BigInteger result = BigInteger.ONE;
        for (int i = 2; i <= n; i++) {
            result = result.multiply(BigInteger.valueOf(i));
        }
        return result;
    }

    public static void main(String[] args) {
        int wrapped = Integer.MAX_VALUE + 1;
        BigInteger base = BigInteger.valueOf(Integer.MAX_VALUE);
        BigInteger next = base.add(BigInteger.ONE);

        System.out.println("int overflow: " + wrapped);
        System.out.println("BigInteger result: " + next);
        System.out.println("Original unchanged: " + base);
        System.out.println("2^100: " + BigInteger.ONE.shiftLeft(100));
        System.out.println("20!: " + factorial(20));

        BigInteger negative = BigInteger.valueOf(-17);
        BigInteger five = BigInteger.valueOf(5);
        System.out.println("divide (-17,5): " + negative.divide(five));
        System.out.println("remainder (-17,5): " + negative.remainder(five));
        System.out.println("mod (-17,5): " + negative.mod(five));
        System.out.println("gcd(54,24): "
                + BigInteger.valueOf(54).gcd(BigInteger.valueOf(24)));
        System.out.println("2^10: " + BigInteger.TWO.pow(10));
        System.out.println("sqrt(1000): "
                + new BigInteger("1000").sqrt());

        System.out.println("hex ff: " + new BigInteger("ff", 16));
        System.out.println("255 in hex: "
                + BigInteger.valueOf(255).toString(16));

        System.out.println("negative one bytes: "
                + Arrays.toString(BigInteger.valueOf(-1).toByteArray()));
        System.out.println("unsigned ff byte: "
                + new BigInteger(1, new byte[] {(byte) 0xff}));

        System.out.println("intValue overflow: " + next.intValue());
        try {
            next.intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("intValueExact: rejected");
        }
        System.out.println("long max + 1: "
                + BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        System.out.println("equals same value: "
                + new BigInteger("42").equals(BigInteger.valueOf(42)));
        System.out.println("compare 99 vs 100: "
                + BigInteger.valueOf(99).compareTo(BigInteger.valueOf(100)));
        System.out.println("modPow(3,13,7): "
                + BigInteger.valueOf(3).modPow(
                        BigInteger.valueOf(13), BigInteger.valueOf(7)));
        System.out.println("signum(-17): " + negative.signum());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 BigIntegerBasicsDemo.java
java BigIntegerBasicsDemo
```

Stdout:

```text
int overflow: -2147483648
BigInteger result: 2147483648
Original unchanged: 2147483647
2^100: 1267650600228229401496703205376
20!: 2432902008176640000
divide (-17,5): -3
remainder (-17,5): -2
mod (-17,5): 3
gcd(54,24): 6
2^10: 1024
sqrt(1000): 31
hex ff: 255
255 in hex: ff
negative one bytes: [-1]
unsigned ff byte: 255
intValue overflow: -2147483648
intValueExact: rejected
long max + 1: 9223372036854775808
equals same value: true
compare 99 vs 100: -1
modPow(3,13,7): 3
signum(-17): -1
```

Các dòng minh họa lần lượt: primitive overflow; cộng BigInteger không sửa đối tượng gốc; số vượt 64 bit; tính toán chính xác; chia nguyên và sự khác nhau giữa `remainder`/`mod`; chuyển radix; signed/unsigned byte; ép xuống `int` không kiểm tra so với `intValueExact`; và các phép modular.

## 16. Chọn `int`, `long`, `BigInteger` hay `BigDecimal`?

| Nhu cầu | Kiểu thường phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Chỉ số mảng, số đếm vừa 32 bit | `int` | Truy cập API tự nhiên, nhẹ; kiểm tra overflow khi cần |
| Timestamp, số lượng, ID số vừa 64 bit | `long` | Độ rộng cố định; tránh làm mất precision ở client binary64 |
| Số nguyên rất lớn, giai thừa, lũy thừa, tính toán exact | `BigInteger` | Immutable; phép toán qua method và tốn tài nguyên tùy độ lớn |
| Số thập phân cần tính chính xác, tiền, giá trị có scale | `BigDecimal` | Cần chính sách rounding/scale |
| Đo lường liên tục cho phép sai số binary64 | `double` | Không biểu diễn chính xác mọi phân số decimal |
| Kết quả tính gần đúng với trọng tâm bộ nhớ thấp | `float` nếu sai số chấp nhận được | Độ chính xác thấp hơn double |
| Bộ đếm thay đổi đồng thời trong miền int/long | `AtomicInteger`/`AtomicLong` hoặc đồng bộ | Immutable BigInteger không tự tạo atomic update |
| Số vượt mọi primitive và cần truyền chính xác | `BigInteger` + schema text/binary | Quy định signedness, radix, độ rộng, client support |

Đừng chọn `BigInteger` chỉ vì input có vẻ “nhiều chữ số” nếu thực chất là mã định danh không dùng số học: nhiều loại dữ liệu cần giữ ký tự `0` đầu, dấu phân cách hoặc định dạng gốc, nên `String` có thể đúng ngữ nghĩa hơn.

## 17. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `+`, `-`, `*` trên hai `BigInteger` | Không biên dịch | `add`, `subtract`, `multiply` |
| Gọi `a.add(b)` mà không lưu kết quả | `a` không đổi | `a = a.add(b)` hoặc dùng biến kết quả |
| Cho rằng `BigInteger` làm mọi phép tính thành “exact decimal” | Chỉ là kiểu số **nguyên** | Dùng `BigDecimal` hoặc Rational khi có phân số |
| Chuyển số lớn về `long` trước khi tính | Có thể mất bit trước khi dùng `BigInteger` | Tạo trực tiếp từ chuỗi hoặc giữ BigInteger |
| Dùng `intValue()`/`longValue()` như phép chuyển có kiểm tra | Có thể mất bit/đổi dấu | `intValueExact()`/`longValueExact()` |
| Tin `doubleValue()` không mất chữ số | Binary64 có 53 bit significand | Giữ BigInteger nếu cần đủ chữ số |
| Dùng `a == b` để so sánh hai BigInteger | So object identity, không phải giá trị | `a.equals(b)` |
| Dùng `a > b` | Không có toán tử trên object | `a.compareTo(b) > 0` |
| Nhầm `remainder` với `mod` cho số âm | Một kết quả có thể âm, một kết quả không âm | Đọc hợp đồng và chọn đúng API |
| Gọi `mod` với modulus 0 hoặc âm | `ArithmeticException` | Kiểm tra modulus dương |
| Tưởng `divide` tạo phần số sau dấu phẩy | Chia nguyên, cắt phần lẻ | Chọn mô hình phân số hoặc BigDecimal |
| Tưởng `BigInteger.valueOf` nhận số bất kỳ ngoài long | Phương thức nhận `long` | `new BigInteger(decimalText)` |
| Parse `"0xFF"` trực tiếp với constructor decimal | `NumberFormatException` | `new BigInteger("FF",16)` hoặc normalize |
| Dùng `new BigInteger(new byte[]{(byte)0xff})` để lấy 255 | Trả −1 vì signed two's complement | `new BigInteger(1,magnitude)` |
| Tưởng mọi mảng byte tạo ra là fixed width | `toByteArray` có độ dài theo signed representation | Codec padding/width theo schema |
| Tin biến cập nhật `counter = counter.add(ONE)` là atomic | Nhiều luồng có thể ghi đè kết quả | Cơ chế đồng bộ/atomic update phù hợp |
| Dùng exponent hoặc input độ dài không giới hạn | Có thể cạn CPU/heap | Áp dụng quota và validate input |
| Tự dựng mật mã chỉ bằng `modPow` | Thiếu chuẩn bảo mật, random, side-channel | Dùng thư viện crypto và giao thức đã kiểm chứng |

## 18. Câu hỏi tự kiểm tra

1. Vì sao `Integer.MAX_VALUE + 1` cho số âm, còn `BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE)` cho 2147483648?
2. `BigInteger` “độ chính xác tùy ý” có nghĩa mọi phép toán đều miễn giới hạn bộ nhớ và thời gian không?
3. `BigInteger a = BigInteger.ZERO; a.add(ONE);` làm `a` thay đổi không? Viết lại để `a` thực sự tham chiếu giá trị 1.
4. Hai biến cùng trỏ đến `BigInteger("100")`; sau khi một biến gán kết quả `add(ONE)`, biến kia còn thấy giá trị gì? Vì sao?
5. Vì sao `BigInteger` không dùng `+` như `int`? Những phương thức tương đương là gì?
6. `new BigInteger("ff",16)` và `new BigInteger("0xff")` khác nhau như thế nào?
7. So sánh `divide`, `remainder` và `mod` khi số bị chia là −17 và số chia/modulus là 5.
8. Khi nào `intValue`/`longValue` có thể làm mất dữ liệu? Vì sao các phiên bản `Exact` an toàn hơn?
9. Mảng một byte `0xff` sẽ trở thành giá trị gì nếu gọi `new BigInteger(bytes)`? Nếu muốn số dương 255 thì làm sao?
10. Vì sao `BigInteger.valueOf(Long.MAX_VALUE).add(ONE)` hợp lệ nhưng `BigInteger.valueOf(9223372036854775808L)` không phải literal `long` hợp lệ?
11. Khi nào nên dùng `equals` và khi nào dùng `compareTo` với `BigInteger`? Vì sao không dùng `==` để so giá trị?
12. Vì sao `BigInteger.ONE.divide(BigInteger.TWO)` không cho 0.5? Cách nào biểu diễn phân số chính xác?
13. Chia sẻ một `BigInteger` cho nhiều luồng có an toàn không? Điều gì vẫn không an toàn khi nhiều luồng **cập nhật biến tham chiếu chung**?
14. Khi truyền một BigInteger rất lớn cho client JavaScript sử dụng `Number`, điều gì có thể xảy ra? Schema trao đổi nên quyết định gì?
15. Vì sao số mũ `pow` cực lớn vẫn cần giới hạn input dù dùng arbitrary precision?
16. Khi nào dùng `BigInteger.modPow` thay vì tính `pow` rồi `mod`? Điều đó có tự động tạo một hệ mật mã an toàn không?

## 19. Tài liệu chính thức

- [Java SE 17 — `java.math.BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): API tạo giá trị, số học, tính bất biến, exact conversion, modular arithmetic, byte representation và giới hạn triển khai.
- [Java SE 17 — `java.lang.Number`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): các phương thức chuyển đổi `intValue`, `longValue`, `floatValue`, `doubleValue` và khả năng mất thông tin.
- [Java SE 17 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác với scale và chính sách rounding, dùng khi dữ liệu không còn thuần số nguyên.
- [Java Language Specification `4.2.1–`4.2.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): miền primitive nguyên và phép toán nguyên.
- [Java SE 17 — `Math` exact methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact` và lựa chọn checked arithmetic khi vẫn dùng primitive.

**Ghi nhớ:** `BigInteger` biểu diễn **số nguyên có dấu với độ chính xác tùy ý trong giới hạn tài nguyên**, và là **immutable**. `add`, `multiply`, `pow` và các phương thức khác trả giá trị mới; muốn dùng kết quả phải nhận/gán lại. Mọi chuyển đổi xuống `int`/`long` hoặc `double` là một ranh giới có thể mất dữ liệu; chọn `...ValueExact()` khi cần bảo toàn. Phân biệt `remainder` và `mod`, chú ý signed bytes và thiết kế schema dữ liệu, và đừng lầm tính bất biến của giá trị số với việc cập nhật một biến chung là atomic.