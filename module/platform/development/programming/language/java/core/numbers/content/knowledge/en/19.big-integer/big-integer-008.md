# BigInteger: mod, modPow, modInverse và các điều kiện đầu vào

## 1. Học đúng ba phép toán — không chỉ nhớ tên method

Trong Java, `java.math.BigInteger` hỗ trợ số nguyên có độ chính xác tùy ý và ba phép toán modulo rất quan trọng:

```java
BigInteger r = a.mod(m);
BigInteger p = a.modPow(exponent, m);
BigInteger inverse = a.modInverse(m);
```

Chúng phục vụ các bài toán khác nhau:

- **`a.mod(m)`**: trả **phần dư modulo không âm** của `a` theo `m`.
- **`a.modPow(e,m)`**: trả `a^e mod m`, được triển khai cho lũy thừa modulo lớn **mà không cần tạo toàn bộ `a^e`**.
- **`a.modInverse(m)`**: tìm `x` sao cho `a*x ≡ 1 (mod m)`, **nếu nghịch đảo tồn tại**.

Điểm cốt lõi của bài **Java Core — Numbers / BigInteger** là *điều kiện đầu vào*. Cả ba đòi **modulus `m > 0`**. `modInverse` còn đòi `gcd(a,m) = 1`; `modPow` có **số mũ âm được phép** trong Java, nhưng khi ấy cũng đòi cơ số khả nghịch modulo `m`.

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(-13);
BigInteger m = BigInteger.valueOf(5);

System.out.println(a.remainder(m)); // -3
System.out.println(a.mod(m));       // 2
```

`remainder` có thể âm; `mod` với modulus dương luôn trả một giá trị trong `[0,m−1]`. Đây là khác biệt đáng nhớ trong mọi thuật toán chu kỳ, hash, đồng dư hay mật mã mô-đun.

**Mục tiêu:** đọc đúng hợp đồng Java 17, biết tự kiểm tra precondition, dự đoán kết quả/ngoại lệ cho cả giá trị âm/0/1, hiểu nghịch đảo và số mũ âm, dùng được các ví dụ Java 17+ với đầu ra kiểm chứng được.

## 2. Chuẩn bị: tạo và so sánh BigInteger

`BigInteger` là **class immutable**, không phải primitive. Các phép toán trả một giá trị `BigInteger` mới hoặc một đối tượng có thể tái sử dụng; chúng **không thay đổi receiver**.

```java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(17);
BigInteger c = a.add(b);

System.out.println(a); // a không đổi
```

Mảnh code cần đặt trong class/method nếu muốn chạy. Với số nằm trong miền `long`, `BigInteger.valueOf(long)` thuận tiện; với số rất dài, dùng `new BigInteger(String)` để parse từ decimal chính xác. Không truyền một literal `long` quá lớn vượt `Long.MAX_VALUE` rồi hy vọng `BigInteger.valueOf` sửa được: lỗi đã xảy ra ở **literal hoặc phép tính primitive** trước khi chuyển.

Các hằng số chuẩn:

```java
BigInteger.ZERO
BigInteger.ONE
BigInteger.TWO   // có từ Java 9
BigInteger.TEN
```

Các cách kiểm tra:

- `m.signum() > 0`: `m` là số dương.
- `m.compareTo(BigInteger.ZERO) > 0`: một cách khác kiểm tra `m` dương.
- `a.equals(b)`: so **giá trị** hai `BigInteger`.
- `a.gcd(m).equals(BigInteger.ONE)`: `a` và `m` **nguyên tố cùng nhau**.

**Không dùng `a == b` để so giá trị hai object `BigInteger`.** `==` giữa hai reference kiểm tra chúng có cùng object hay không, và sẽ không đáp ứng yêu cầu equality cho các giá trị được tạo độc lập.

### 2.1. Chữ ký các method

```text
BigInteger mod(BigInteger m)
BigInteger modPow(BigInteger exponent, BigInteger m)
BigInteger modInverse(BigInteger m)

BigInteger remainder(BigInteger val)
BigInteger pow(int exponent)
BigInteger gcd(BigInteger val)
```

Các dòng trên là **chữ ký minh họa**, không phải khai báo source Java độc lập. Lưu ý `modPow` nhận số mũ dưới dạng **`BigInteger`**, còn `pow` nhận **`int`** và tính lũy thừa nguyên *không* lấy modulo. Chọn nhầm API có thể dẫn đến chi phí bộ nhớ rất lớn hoặc ngoại lệ khi số mũ âm.

## 3. Đồng dư và lớp phần dư

Hai số nguyên `a` và `b` được gọi là **đồng dư modulo m** nếu hiệu `a−b` chia hết cho `m`:

```text
a ≡ b (mod m)
⇔ tồn tại k nguyên sao cho a - b = k*m.
```

Ví dụ:

```text
-13 ≡ 2 (mod 5), vì -13 - 2 = -15 = -3*5.
17 ≡ 2 (mod 5), vì 17 - 2 = 15 = 3*5.
```

Với `m > 0`, ta chọn một **đại diện chuẩn** trong khoảng `0≤r<m`. Phương thức `BigInteger.mod(m)` trả đại diện chuẩn đó, cho dù `a` dương, âm hay bằng 0.

| `a` | `m` | `a.mod(m)` | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 13 | 5 | 3 | 13 = 2×5+3 |
| −13 | 5 | 2 | −13 = −3×5+2 |
| 0 | 5 | 0 | Zero thuộc lớp 0 |
| 10 | 5 | 0 | Chia hết |
| 5 | 5 | 0 | Đại diện của m là 0 |
| 5 | 1 | 0 | Chỉ có một lớp modulo 1 |

Hãy phân biệt **`a.mod(m)`** (tính kết quả) với **`a.equals(b)`** (so giá trị object). Một cặp số có thể không bằng nhau theo `equals` nhưng cùng kết quả modulo.

### 3.1. Vì sao modulus phải dương?

`BigInteger.mod(m)` định nghĩa đầu ra trong `0..m−1`. Nếu `m=0` thì khái niệm lớp phần dư theo modulus 0 không phù hợp hợp đồng API. Nếu `m<0`, khoảng đại diện `[0,m−1]` không có ý nghĩa ở dạng đã quy định.

Vì vậy, **`mod` ném `ArithmeticException` khi `m≤0`**. Không được suy rằng `mod(-5)` “tự lấy trị tuyệt đối” thành `mod(5)`. Nếu một domain thực sự có cách hiểu modulus âm, bạn cần tự thiết kế chính sách chuẩn hóa `m.abs()` *trước* khi gọi và giải thích rõ ý nghĩa; đừng âm thầm đổi dấu dữ liệu đầu vào.

## 4. `remainder` và `mod`: nguồn gốc nhiều lỗi âm

`BigInteger.remainder(m)` mô phỏng phép `%` số nguyên Java: thương được cắt về 0 và phần dư có thể **cùng dấu với số bị chia** (hoặc bằng 0). `BigInteger.mod(m)` lại luôn trả kết quả **không âm** khi `m>0`.

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(-13);
BigInteger five = BigInteger.valueOf(5);

System.out.println(a.remainder(five)); // -3
System.out.println(a.mod(five));       // 2
```

Hai kết quả vẫn đại diện cùng lớp đồng dư vì `−3 ≡ 2 (mod 5)`. Nhưng chúng **không cùng giá trị nguyên** và có thể cho hệ quả khác trong lập trình.

| Biểu thức | Kết quả | Ghi chú |
| --- | ---: | --- |
| `BigInteger.valueOf(-13).remainder(BigInteger.valueOf(5))` | −3 | Dấu âm từ số bị chia |
| `BigInteger.valueOf(-13).mod(BigInteger.valueOf(5))` | 2 | Chuẩn hóa không âm |
| `BigInteger.valueOf(13).remainder(BigInteger.valueOf(-5))` | 3 | `remainder` cho phép divisor âm khác 0 |
| `BigInteger.valueOf(13).mod(BigInteger.valueOf(-5))` | Ném `ArithmeticException` | `mod` từ chối modulus âm |
| `BigInteger.valueOf(13).remainder(BigInteger.ZERO)` | Ném `ArithmeticException` | Chia cho zero |

**Điều kiện:** `remainder` chỉ cấm divisor bằng zero; `mod` cấm modulus **không dương**. Không tự suy “`remainder` và `mod` là hai tên gọi cho cùng method” chỉ từ một vài ví dụ có số dương.

### 4.1. Chuẩn hóa phần dư thủ công

Nếu đã có `r = a.remainder(m)` với `m>0`, có thể biến thành đại diện chuẩn:

```java
BigInteger r = a.remainder(m);
if (r.signum() < 0) {
    r = r.add(m);
}
```

Với modulus dương, `remainder` có độ lớn nhỏ hơn modulus, nên chỉ cần cộng `m` **một lần** khi r âm. Nhưng **cách trực tiếp và rõ nhất** vẫn là `a.mod(m)`.

Công thức đôi khi gặp ở các ngôn ngữ khác là `((a % m) + m) % m`. Nó có thể giúp chuẩn hóa phần dư âm, nhưng với `BigInteger` nên dùng `mod` để diễn đạt đúng chủ đích và tránh nhầm với `remainder`.

## 5. Chương trình Java A — phân biệt phần dư và modulo

Tạo file **`ModVsRemainder.java`**:

```java
import java.math.BigInteger;

public class ModVsRemainder {
    public static void main(String[] args) {
        BigInteger minus13 = BigInteger.valueOf(-13);
        BigInteger five = BigInteger.valueOf(5);

        System.out.println(minus13.remainder(five));
        System.out.println(minus13.mod(five));

        System.out.println(BigInteger.valueOf(13).mod(five));
        System.out.println(BigInteger.ZERO.mod(five));
        System.out.println(BigInteger.valueOf(10).mod(five));
        System.out.println(BigInteger.valueOf(99).mod(BigInteger.ONE));

        System.out.println(BigInteger.valueOf(13)
                .remainder(BigInteger.valueOf(-5)));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 ModVsRemainder.java
java ModVsRemainder
```

**Stdout chính xác:**

```text
-3
2
3
0
0
0
3
```

Sau khi chạy, hãy kiểm tra từng kết quả có thỏa `0≤a.mod(m)<m` với `m>0`. `mod(BigInteger.ONE)` luôn trả 0, bất kể receiver là giá trị nguyên nào.

## 6. `modPow(exponent,m)` — lũy thừa modulo

`a.modPow(e,m)` tính phần dư chuẩn của `a^e` theo `m`. Với `e≥0`, ý nghĩa toán học:

```text
result = a^e mod m,  m > 0, e >= 0.
```

Đầu ra nằm trong khoảng `[0,m−1]`. Khác `pow(int)`, phương thức này **không cần tạo toàn bộ số a^e trước rồi mới chia lấy dư**. Đây là yếu tố sống còn khi số mũ lớn.

Ví dụ kinh điển:

```text
4^13 mod 497 = 445.
```

Java:

```java
BigInteger result = BigInteger.valueOf(4)
        .modPow(BigInteger.valueOf(13),
                BigInteger.valueOf(497));

System.out.println(result); // 445
```

Kết quả `445` luôn không âm và nhỏ hơn `497`. Cơ số `a` có thể âm: `(−2)^5 mod 13 = 7`, vì `−32 ≡ 7 (mod 13)`.

### 6.1. Lặp bình phương — trực giác thuật toán

Một phương pháp cơ bản để tính `a^e mod m` với `e≥0` là **binary exponentiation** (lũy thừa nhị phân/lặp bình phương):

1. Đặt `result = 1 mod m` và `base = a mod m`.
2. Với mỗi bit của `e` từ thấp lên cao, nếu bit lẻ đang xét bằng 1 thì `result = (result*base) mod m`.
3. Bình phương `base = base*base mod m` rồi chuyển `e` sang phải một bit.
4. Khi `e` bằng 0, trả `result`.

Phép nhân được giảm modulo sau mỗi bước nên các giá trị trung gian không tăng theo kích thước khổng lồ của `a^e`. Số vòng lặp tỷ lệ với **số bit của số mũ**, không phải giá trị số mũ. Chi phí thực tế còn phụ thuộc số bit của modulus, thuật toán nhân/số học lớn và implementation JDK.

### 6.2. Code minh họa lặp bình phương (không thay API chuẩn)

```java
static BigInteger repeatedSquaring(
        BigInteger a, BigInteger e, BigInteger m) {
    if (m.signum() <= 0 || e.signum() < 0) {
        throw new IllegalArgumentException("Require m>0, e>=0");
    }

    BigInteger result = BigInteger.ONE.mod(m);
    BigInteger base = a.mod(m);
    BigInteger power = e;

    while (power.signum() > 0) {
        if (power.testBit(0)) {
            result = result.multiply(base).mod(m);
        }
        power = power.shiftRight(1);
        if (power.signum() > 0) {
            base = base.multiply(base).mod(m);
        }
    }
    return result;
}
```

Đây là **phương thức minh họa**, cần import `java.math.BigInteger` và đặt trong class; nó chỉ nhận `e≥0`. Điều kiện `m>0` phải được kiểm tra **trước** khi gọi `ONE.mod(m)`. Phép bit `testBit(0)` xác định bit thấp, tương đương kiểm tra số mũ lẻ.

Hàm minh họa giúp hiểu thuật toán; khi viết ứng dụng Java thông thường hãy ưu tiên `BigInteger.modPow` đã được tối ưu và kiểm thử rộng rãi. Không tự dùng bản minh họa cho mật mã nhạy cảm: thời gian thực thi có thể phụ thuộc các bit của số mũ và làm lộ thông tin nhạy cảm qua kênh phụ.

## 7. `modPow` và `pow` không giống nhau

| Tính năng | `a.pow(int e)` | `a.modPow(BigInteger e, BigInteger m)` |
| --- | --- | --- |
| Kết quả | `a^e` nguyên đầy đủ | Đại diện của `a^e` modulo `m` |
| Modulus | Không có | Bắt buộc `m>0` |
| Kiểu exponent | `int` | `BigInteger` |
| Exponent âm | **Không được**, ném `ArithmeticException` | **Được phép nếu `a` khả nghịch modulo `m`** |
| Kích thước kết quả | Có thể khổng lồ | Số bit không vượt quá kích thước đại diện dưới `m` |
| Ứng dụng | Lũy thừa nguyên thông thường | Đồng dư/lũy thừa modulo |

Ví dụ có thể gây nhầm:

```java
BigInteger a = BigInteger.valueOf(2);

System.out.println(a.pow(10)); // 1024
System.out.println(a.modPow(
        BigInteger.TEN, BigInteger.valueOf(17))); // 4
```

Vì `1024 mod 17 = 4`. Nhưng với số mũ dài hàng nghìn bit, tạo `a.pow(...)` trước khi modulo thường không khả thi, trong khi `modPow` xử lý theo kỹ thuật modular exponentiation.

**Lưu ý quan trọng:** `BigInteger.pow(-1)` ném `ArithmeticException`. **Không** suy từ đó rằng `BigInteger.modPow(BigInteger.valueOf(-1),m)` cũng bắt buộc ném; API `modPow` cho phép số mũ âm khi tồn tại nghịch đảo.

## 8. Điều kiện đầu vào của `modPow` — kể cả exponent âm

Hợp đồng Java 17:

- `m` phải **dương**; `m≤0` ⇒ `ArithmeticException`.
- `exponent` có thể **âm, zero hoặc dương**.
- Nếu `exponent<0`, cơ số phải **nguyên tố cùng nhau với modulus**, tương đương `gcd(a,m)=1`. Nếu không, `ArithmeticException`.
- Nếu `exponent≥0`, **không cần** `gcd(a,m)=1`. Chẳng hạn `6.modPow(2,15)` vẫn xác định.
- Các tham số object bằng `null` gây `NullPointerException` theo quy tắc chung của `BigInteger`; không xem null như zero.

| Cơ số | e | m | Kết quả/hành vi |
| ---: | ---: | ---: | --- |
| 4 | 13 | 497 | 445 |
| 2 | 10 | 17 | 4 |
| −2 | 5 | 13 | 7 |
| 3 | −1 | 11 | 4 |
| 3 | −2 | 11 | 5 |
| 6 | 2 | 15 | 6 |
| 6 | −1 | 15 | `ArithmeticException`: không có nghịch đảo |
| 2 | 10 | 0 | `ArithmeticException`: modulus không dương |
| 2 | 10 | −7 | `ArithmeticException`: modulus không dương |
| 2 | 0 | 7 | 1 |
| 0 | 0 | 7 | 1 |
| 0 | 5 | 7 | 0 |
| 99 | 0 | 1 | 0 |

Với hàng `6^2 mod 15`: `36 mod 15=6`, không đòi 6 và 15 nguyên tố cùng nhau vì số mũ không âm.

### 8.1. Số mũ zero và 0^0 trong BigInteger

`a.modPow(BigInteger.ZERO, m)` trả `1 mod m` khi `m>0`. Do đó:

- Nếu `m>1`, kết quả là `1`, kể cả cơ số `a=0`.
- Nếu `m=1`, kết quả là `0` vì mọi giá trị modulo 1 đều đại diện bằng 0.

Java xác định trường hợp `0.modPow(0,m)` bằng ngữ nghĩa API, không yêu cầu người học tự tranh luận định nghĩa `0^0` trong giải tích. Cũng tương tự, `BigInteger.ZERO.pow(0)` trả `BigInteger.ONE`.

### 8.2. Vì sao exponent âm là một trường hợp hợp lệ?

Với `e<0`, diễn giải lũy thừa modulo dựa trên **nghịch đảo nhân**:

```text
a^(-1) mod m = inverse(a) mod m
a^(-k) mod m = (inverse(a))^k mod m, k>0
```

Ví dụ `3 mod 11` có nghịch đảo 4 vì `3×4=12 ≡ 1 (mod 11)`. Vì vậy:

```text
3^(-1) mod 11 = 4
3^(-2) mod 11 = 4^2 mod 11 = 16 mod 11 = 5.
```

Trong Java:

```java
BigInteger a = BigInteger.valueOf(3);
BigInteger m = BigInteger.valueOf(11);

System.out.println(a.modPow(BigInteger.valueOf(-1), m)); // 4
System.out.println(a.modPow(BigInteger.valueOf(-2), m)); // 5
```

Không được hiểu `e<0` là tạo một số hữu tỉ kiểu `BigDecimal` bằng phép `1/a^k`. Đó là **nghịch đảo trong cấu trúc số dư modulo**; nếu không tồn tại nghịch đảo, biểu thức không có giá trị modulo và Java báo lỗi.

## 9. Chương trình Java B — modPow và điều kiện số mũ

Tạo file **`ModularExponentiation.java`**:

```java
import java.math.BigInteger;

public class ModularExponentiation {
    private static BigInteger bi(long n) {
        return BigInteger.valueOf(n);
    }

    public static void main(String[] args) {
        System.out.println(bi(4).modPow(bi(13), bi(497)));
        System.out.println(bi(2).modPow(bi(10), bi(17)));
        System.out.println(bi(-2).modPow(bi(5), bi(13)));

        System.out.println(bi(3).modPow(bi(-1), bi(11)));
        System.out.println(bi(3).modPow(bi(-2), bi(11)));

        System.out.println(bi(2).modPow(bi(0), bi(7)));
        System.out.println(bi(0).modPow(bi(0), bi(7)));
        System.out.println(bi(99).modPow(bi(0), bi(1)));
    }
}
```

Chạy:

```bash
javac --release 17 ModularExponentiation.java
java ModularExponentiation
```

**Stdout chính xác:**

```text
445
4
7
4
5
1
1
0
```

Dòng thứ tư và thứ năm xác nhận **số mũ âm được hỗ trợ** khi `gcd(a,m)=1`. Dòng cuối xác nhận modulus 1 có lớp phần dư duy nhất là 0.

## 10. `modInverse(m)` — nghịch đảo nhân trong modulo

Trong số học thực, người học có thể quen nghịch đảo của 3 là `1/3`. Trong modulo 11, nghịch đảo của 3 là **4**, bởi:

```text
3 × 4 = 12
12 mod 11 = 1
⇒ 3 × 4 ≡ 1 (mod 11).
```

Java hỗ trợ trực tiếp:

```java
BigInteger three = BigInteger.valueOf(3);
BigInteger eleven = BigInteger.valueOf(11);
BigInteger inv = three.modInverse(eleven);

System.out.println(inv); // 4
```

Đây là một **số nguyên đại diện chuẩn** trong khoảng `[0, m−1]`, không phải `double`/`BigDecimal` hoặc phân số thông thường. Nếu kết quả là `x`, bạn có thể kiểm chứng:

```java
System.out.println(
        three.multiply(inv).mod(eleven)); // 1
```

### 10.1. Điều kiện tồn tại nghịch đảo

Với modulus `m>1`, nghịch đảo của `a` tồn tại **khi và chỉ khi**:

```text
gcd(a,m) = 1.
```

Đây là định lý quan trọng nhất của bài. **Modulus không bắt buộc là số nguyên tố**. Chẳng hạn:

- `3` có nghịch đảo modulo `10` vì `gcd(3,10)=1`; kết quả `7` vì `3×7=21 ≡1 (mod 10)`.
- `3` có nghịch đảo modulo `11` vì `gcd(3,11)=1`; kết quả `4`.
- `6` **không** có nghịch đảo modulo `15` vì `gcd(6,15)=3`.
- `2` **không** có nghịch đảo modulo `4` vì `gcd(2,4)=2`.
- `0` **không** có nghịch đảo modulo `m>1` vì `gcd(0,m)=m≠1`.

`BigInteger.modInverse(m)` ném `ArithmeticException` nếu `m≤0` hoặc không tồn tại nghịch đảo. `m=1` là một trường hợp đại số **suy biến**, sẽ được giải thích riêng; tránh xây thuật toán yêu cầu “1 là phần tử khác 0” rồi giả định modulus 1 bình thường như modulus lớn.

### 10.2. Số âm vẫn có thể có nghịch đảo

Cơ số âm **không tự khiến modInverse lỗi**. Ví dụ `−3 ≡ 8 (mod 11)`. Nghịch đảo của `−3` modulo 11 là `7`, vì:

```text
(-3)*7 = -21
-21 ≡ 1 (mod 11).
```

Java:

```java
System.out.println(BigInteger.valueOf(-3)
        .modInverse(BigInteger.valueOf(11))); // 7
```

Do tính chất lớp đồng dư, `a.modInverse(m)` và `a.mod(m).modInverse(m)` cho cùng lớp nghiệm với `m>0` khi nghịch đảo tồn tại.

## 11. gcd và thuật toán Euclid mở rộng

`BigInteger.gcd(BigInteger)` trả **ước chung lớn nhất không âm** của hai số (với `gcd(0,0)=0` theo API). Khi muốn kiểm tra trước `modInverse`, dùng:

```java
BigInteger g = a.gcd(m);
boolean invertible = g.equals(BigInteger.ONE);
```

Ví dụ:

```java
System.out.println(BigInteger.valueOf(6)
        .gcd(BigInteger.valueOf(15))); // 3
```

### 11.1. Vì sao gcd=1 bảo đảm có nghịch đảo?

Định lý Bézout phát biểu: tồn tại hai số nguyên `x,y` sao cho:

```text
a*x + m*y = gcd(a,m).
```

Nếu `gcd(a,m)=1` thì:

```text
a*x + m*y = 1
⇒ a*x ≡ 1 (mod m).
```

Vậy `x` là một nghịch đảo modulo `m`. Thuật toán Euclid mở rộng tìm các hệ số `x,y` đó và là nền tảng toán học quen thuộc để tính nghịch đảo.

Ví dụ `a=3,m=11`:

```text
3*4 + 11*(-1) = 1
⇒ x = 4 là nghịch đảo của 3 modulo 11.
```

Ví dụ `a=6,m=15`: mọi tổ hợp `6x+15y` đều chia hết cho 3, nên không thể bằng 1. Không tồn tại `x` thỏa `6x ≡ 1 (mod 15)`.

### 11.2. Không dùng x/y thông thường thay cho modInverse

Nếu có `a*x ≡ b (mod m)`, đôi khi ta muốn “chia cho a” để tìm `x`. Điều đó chỉ hợp lệ theo cách dùng nghịch đảo khi `a` **khả nghịch modulo m**:

```text
x ≡ b * inverse(a) (mod m), nếu gcd(a,m)=1.
```

Nếu `gcd(a,m)>1`, phép chia modulo không đơn giản như số thực. Đồng dư `a*x ≡ b (mod m)` có thể **không có nghiệm** hoặc **nhiều nghiệm khác nhau**; cần thuật toán giải đồng dư tuyến tính riêng và kiểm tra `gcd(a,m)` có chia `b` hay không. Đừng cứ bắt exception rồi thay bằng phép chia `BigInteger.divide`.

## 12. Chương trình Java C — nghịch đảo, gcd và ngoại lệ

Tạo file **`ModularInverseDemo.java`**:

```java
import java.math.BigInteger;

public class ModularInverseDemo {
    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    public static void main(String[] args) {
        BigInteger three = bi(3);
        BigInteger eleven = bi(11);

        BigInteger inverse = three.modInverse(eleven);
        System.out.println(inverse);
        System.out.println(three.multiply(inverse).mod(eleven));

        System.out.println(bi(-3).modInverse(eleven));
        System.out.println(bi(3).modInverse(bi(10)));

        System.out.println(bi(6).gcd(bi(15)));

        try {
            System.out.println(bi(6).modInverse(bi(15)));
        } catch (ArithmeticException ex) {
            System.out.println("No inverse for 6 mod 15");
        }

        try {
            System.out.println(bi(6).modPow(bi(-1), bi(15)));
        } catch (ArithmeticException ex) {
            System.out.println("Negative exponent needs inverse");
        }
    }
}
```

Chạy:

```bash
javac --release 17 ModularInverseDemo.java
java ModularInverseDemo
```

**Stdout chính xác:**

```text
4
1
7
7
3
No inverse for 6 mod 15
Negative exponent needs inverse
```

Cách xử lý exception ở đây để **biểu diễn điều kiện toán học** cho người học, không có nghĩa ứng dụng nên im lặng bỏ qua lỗi. Trong code nghiệp vụ, nên xác thực đầu vào, phân biệt “modulus sai” và “không có nghịch đảo”, và trả thông báo/trạng thái phù hợp.

## 13. Bảng điều kiện đầu vào và lỗi cho ba phương thức

| Phép toán | Modulus hợp lệ | Điều kiện khác | Lỗi đáng chú ý |
| --- | --- | --- | --- |
| `a.mod(m)` | `m > 0` | `a` bất kỳ số nguyên | `ArithmeticException` nếu `m≤0` |
| `a.modPow(e,m)` | `m > 0` | Với `e<0` phải có `gcd(a,m)=1` | `ArithmeticException` nếu `m≤0` hoặc mũ âm mà không khả nghịch |
| `a.modInverse(m)` | `m > 0` | Phải khả nghịch modulo `m`: `gcd(a,m)=1` | `ArithmeticException` nếu `m≤0` hoặc không có nghịch đảo |
| `a.remainder(m)` | `m ≠ 0` | `m` có thể âm | `ArithmeticException` nếu `m=0` |
| `a.pow(int e)` | Không có modulus | `e ≥ 0` | `ArithmeticException` nếu `e<0` |

**Null:** các method `BigInteger` khi được truyền tham số object null sẽ ném `NullPointerException` theo quy tắc chung; nếu receiver `a` null thì gọi bất kỳ method instance nào cũng ném NPE. Không dùng null làm “giá trị modulo zero”.

**Sức chứa tài nguyên:** dù `BigInteger` cung cấp độ chính xác tùy ý, implementation có giới hạn tài nguyên/bộ nhớ và hỗ trợ số bit tối đa. Các thao tác lớn có thể dùng nhiều CPU/bộ nhớ; `BigInteger` có thể ném `ArithmeticException` khi kết quả nằm ngoài miền được hỗ trợ, bên cạnh những điều kiện lỗi nêu trong bảng.

### 13.1. Không có điều kiện “m phải nguyên tố” cho modPow

`modPow(e,m)` chạy với **modulus hợp số** như `497` hoặc `15` miễn là `m>0` và các điều kiện về số mũ âm được đáp ứng. Nghịch đảo `modInverse` cũng **không yêu cầu modulus nguyên tố**, mà yêu cầu `gcd(a,m)=1`.

Một modulus nguyên tố `p` làm mọi lớp khác zero có nghịch đảo, nhưng đó là tính chất **trường hữu hạn** của `Z/pZ`, không phải điều kiện do Java ép vào API.

## 14. Những trường hợp biên: m=1, a=0, e=0, số âm

### 14.1. Modulus bằng 1

`m=1` **hợp lệ** vì `m>0`. Mọi số nguyên đều đồng dư 0 modulo 1:

```java
System.out.println(BigInteger.valueOf(99)
        .mod(BigInteger.ONE)); // 0

System.out.println(BigInteger.valueOf(5)
        .modPow(BigInteger.ZERO, BigInteger.ONE)); // 0
```

Trên JDK Java 17, `BigInteger.valueOf(2).modInverse(BigInteger.ONE)` trả `0`. Đây là trường hợp suy biến có duy nhất một lớp đồng dư `0=1` modulo 1 theo phép đồng dư, **không phải** nghịch đảo số học thông thường. Cùng logic đó, `a.modPow(e,ONE)` trả 0 cho các số mũ, kể cả những trường hợp mũ âm được JDK chấp nhận.

**Khuyến nghị:** nếu thiết kế nghiệp vụ dùng nghịch đảo, nhóm nhân hay mật mã yêu cầu modulus không suy biến, hãy đặt precondition mạnh hơn: **`m>1`**. Đây là ràng buộc **nghiệp vụ bổ sung**, không phải ràng buộc chung của `BigInteger.mod`.

### 14.2. Cơ số zero

- `0.mod(m)` bằng 0 cho mọi `m>0`.
- `0.modPow(e,m)` bằng 0 với `e>0` và `m>1`.
- `0.modPow(0,m)` bằng `1 mod m`.
- `0.modInverse(m)` **không tồn tại** nếu `m>1` vì `gcd(0,m)=m`.
- `0.modPow(e<0,m)` ném `ArithmeticException` nếu `m>1` vì thiếu nghịch đảo.

Không được suy từ “`0^0` gây tranh cãi trong toán học” rằng Java không có giá trị xác định cho `modPow(0,m)`: API trả kết quả quy định.

### 14.3. Cơ số âm

Cơ số âm vẫn được phép. `mod` chuẩn hóa phần dư thành không âm, `modPow` tính lớp đồng dư chính xác, `modInverse` hoạt động nếu `gcd=1`.

Ví dụ:

```java
System.out.println(BigInteger.valueOf(-13)
        .mod(BigInteger.valueOf(5))); // 2
System.out.println(BigInteger.valueOf(-2)
        .modPow(BigInteger.valueOf(5),
                BigInteger.valueOf(13))); // 7
```

**Không dùng phép `abs()` thay `mod()`**: `abs(-13)=13`, không phải kết quả đồng dư chuẩn của `-13 mod5`. Một phép biến đổi dấu không bảo toàn mọi lớp đồng dư.

### 14.4. Modulus bằng zero hoặc âm

`a.mod(BigInteger.ZERO)`, `a.modPow(e,BigInteger.ZERO)`, `a.modInverse(BigInteger.ZERO)` đều ném `ArithmeticException`. Tương tự với modulus âm. Trong ứng dụng nhập dữ liệu, kiểm tra `m.signum()>0` trước khi tính và cung cấp thông báo rõ.

## 15. Chương trình Java D — kiểm tra input có chủ đích

Tạo file **`CheckedModularArithmetic.java`**:

```java
import java.math.BigInteger;
import java.util.Objects;

public class CheckedModularArithmetic {
    static BigInteger modularPower(
            BigInteger base,
            BigInteger exponent,
            BigInteger modulus) {

        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(exponent, "exponent");
        Objects.requireNonNull(modulus, "modulus");

        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException("modulus must be positive");
        }

        if (exponent.signum() < 0
                && !base.gcd(modulus).equals(BigInteger.ONE)) {
            throw new IllegalArgumentException(
                    "negative exponent requires inverse");
        }

        return base.modPow(exponent, modulus);
    }

    public static void main(String[] args) {
        System.out.println(modularPower(
                BigInteger.valueOf(2),
                BigInteger.TEN,
                BigInteger.valueOf(17)));

        System.out.println(modularPower(
                BigInteger.valueOf(3),
                BigInteger.valueOf(-1),
                BigInteger.valueOf(11)));

        try {
            modularPower(BigInteger.TWO,
                    BigInteger.TEN, BigInteger.ZERO);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            modularPower(BigInteger.valueOf(6),
                    BigInteger.valueOf(-1),
                    BigInteger.valueOf(15));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 CheckedModularArithmetic.java
java CheckedModularArithmetic
```

**Stdout chính xác:**

```text
4
4
modulus must be positive
negative exponent requires inverse
```

Ứng dụng có thể chọn để `BigInteger` tự ném `ArithmeticException`, hoặc validate sớm để đưa thông báo nghiệp vụ. Việc validate `gcd` có thể **tăng chi phí** vì `modPow` với exponent âm cũng phải xử lý khả nghịch; không nhất thiết tính gcd trước trong mọi đường chạy. Nhưng validation tường minh hữu ích khi cần phân loại lỗi đầu vào.

Trong công việc liên quan dữ liệu **không đáng tin cậy**, còn phải giới hạn độ dài chuỗi `BigInteger`, bit length của cơ số/modulus và exponent, thời gian tính, bộ nhớ, cũng như chính sách logging. `m>0` không đồng nghĩa mọi phép tính có chi phí chấp nhận được.

## 16. Các định lý giúp kiểm chứng kết quả

Khi làm modulo, có những đẳng thức toán học hữu ích cho `m>0`:

```text
(a + b) mod m = ((a mod m) + (b mod m)) mod m

(a * b) mod m = ((a mod m) * (b mod m)) mod m

a^e mod m = (a mod m)^e mod m, với e >= 0

Nếu gcd(a,m)=1:
a * modInverse(a,m) mod m = 1 mod m.
```

Trong Java `BigInteger`:

```java
BigInteger left = a.multiply(b).mod(m);
BigInteger right = a.mod(m)
        .multiply(b.mod(m)).mod(m);

boolean equal = left.equals(right);
```

Đây là mảnh code cần khai báo `a`, `b`, `m` dương và khác null trước khi chạy. Nó là một **property test** tốt cho các phép modulo, miễn là đầu vào thuộc miền được phép.

### 16.1. Không “rút gọn” một nhân tử khi nó không khả nghịch

Từ:

```text
a*x ≡ a*y (mod m)
```

không phải lúc nào cũng suy ra `x≡y (mod m)`. Phép rút gọn `a` chỉ hợp lệ nếu `gcd(a,m)=1`.

Ví dụ:

```text
2*1 ≡ 2*3 (mod 4)  vì 2 ≡ 6 (mod 4),
nhưng 1 không đồng dư 3 (mod 4).
```

Đây là lý do “chia hai vế” hoặc gọi `modInverse` **không được** nếu `a` thiếu nghịch đảo modulo m.

### 16.2. Không đồng nhất kết quả modulo với bằng nhau số nguyên

`a.mod(m).equals(b.mod(m))` đúng khi `a` và `b` cùng lớp đồng dư modulo `m`; nhưng không có nghĩa `a.equals(b)`. Ví dụ `-13` và `2` khác giá trị số, nhưng đồng dư modulo 5.

Khi làm khóa dữ liệu theo lớp đồng dư, bạn có thể dùng `a.mod(m)` làm **canonical key**, miễn là modulus đã được xác định và nhất quán. Không tự thay đổi modulus cho một khóa đã chèn vào map/set mà không định nghĩa cách phân nhóm lại.

## 17. Chương trình Java E — ví dụ toán học minh họa RSA

Lũy thừa modulo và nghịch đảo modulo được dùng trong nhiều cấu trúc toán học, trong đó có hệ mật mã RSA. Ví dụ nhỏ sau **chỉ để học**, tuyệt đối không dùng cho bảo mật thực tế.

Ta chọn các số nguyên tố rất nhỏ:

```text
p = 61
q = 53
n = p*q = 3233
φ(n) = (p-1)*(q-1) = 3120
e = 17
d = e^(-1) mod 3120 = 2753
message = 65
cipher = message^e mod n = 2790
decoded = cipher^d mod n = 65
```

Tạo file **`ToyRsaMath.java`**:

```java
import java.math.BigInteger;

public class ToyRsaMath {
    public static void main(String[] args) {
        BigInteger p = BigInteger.valueOf(61);
        BigInteger q = BigInteger.valueOf(53);
        BigInteger n = p.multiply(q);

        BigInteger phi = p.subtract(BigInteger.ONE)
                .multiply(q.subtract(BigInteger.ONE));

        BigInteger e = BigInteger.valueOf(17);
        BigInteger d = e.modInverse(phi);

        BigInteger message = BigInteger.valueOf(65);
        BigInteger cipher = message.modPow(e, n);
        BigInteger decoded = cipher.modPow(d, n);

        System.out.println(n);
        System.out.println(phi);
        System.out.println(d);
        System.out.println(cipher);
        System.out.println(decoded);
    }
}
```

Chạy:

```bash
javac --release 17 ToyRsaMath.java
java ToyRsaMath
```

**Stdout chính xác:**

```text
3233
3120
2753
2790
65
```

Ý nghĩa: `modInverse` tìm `d` khi `gcd(e,φ(n))=1`; `modPow` thực hiện lũy thừa modulo mà không tính các số nguyên khổng lồ. Bộ số nhỏ cho phép bạn kiểm tra các công thức bằng tay.

**Cảnh báo về an toàn:** RSA thực tế yêu cầu sinh khóa đúng chuẩn, padding an toàn (ví dụ OAEP cho mã hóa và PSS cho chữ ký), randomness thích hợp, quản lý khóa, thiết kế tránh timing/power side channels và dùng API/provider mật mã đã được kiểm định. `BigInteger.modPow` là một phép toán số học, **không phải** API RSA hoàn chỉnh hay cam kết thời gian hằng. Không dùng ví dụ ở đây để mã hóa/chữ ký dữ liệu thật.

## 18. Sai lầm thường gặp

1. **“`mod` giống hệt `remainder`.”** Sai với số âm. `(-13).remainder(5)=-3`, `(-13).mod(5)=2`.
2. **“modulus âm được tự chuẩn hóa.”** Sai: `mod`, `modPow`, `modInverse` yêu cầu `m>0`, ngược lại ném `ArithmeticException`.
3. **“modulus phải là số nguyên tố.”** Sai: modulus hợp số vẫn được, miễn thỏa điều kiện từng phép.
4. **“`modInverse` luôn tồn tại khi `m>0`.”** Sai: cần `gcd(a,m)=1` (trường hợp m=1 suy biến).
5. **“`modPow` không cho phép exponent âm.”** Sai: đây là một khác biệt lớn với `pow(int)`.
6. **“Exponent âm trong modPow tạo phân số thông thường.”** Sai: đó là nghịch đảo modulo, chỉ có khi khả nghịch.
7. **“`a.pow(e).mod(m)` luôn là cách tốt nhất.”** Sai: `pow` có thể tạo số cực lớn; dùng `modPow`.
8. **“`a.pow(-1)` có nghĩa là nghịch đảo.”** Sai: `pow(int)` từ chối mũ âm.
9. **“`BigInteger.ZERO.modPow(BigInteger.ZERO,m)` phải lỗi.”** Sai: với `m>1`, Java trả 1 theo hợp đồng.
10. **“`m=1` bị cấm vì quá nhỏ.”** Sai theo API; `m=1` là modulus dương, kết quả modulo luôn 0.
11. **“Kết quả `modInverse` là decimal 1/a.”** Sai: nó là đại diện nguyên của nghịch đảo trong lớp đồng dư.
12. **“Nếu `a*x ≡ a*y` thì luôn có thể rút a.”** Sai nếu `gcd(a,m)>1`.
13. **“Dùng `==` để so hai `BigInteger` cùng số.”** Sai: nó so identity tham chiếu; dùng `equals`.
14. **“BigInteger là vô hạn tài nguyên, không cần giới hạn input.”** Sai: tài nguyên và miền implementation hữu hạn.
15. **“`BigInteger.modPow` đủ để viết RSA production.”** Sai: RSA còn yêu cầu padding, randomness, quản lý khóa và chống kênh phụ.
16. **“`BigInteger.mod` làm thay đổi receiver.”** Sai: đối tượng BigInteger bất biến.
17. **“Bắt `ArithmeticException` rồi trả 0 cho mọi trường hợp là an toàn.”** Sai: có thể che giấu modulus sai hoặc nghịch đảo không tồn tại; 0 là một kết quả hợp lệ cho nhiều phép.
18. **“`gcd(0,m)` luôn bằng 0.”** Sai: với `m>0`, `gcd(0,m)=m`.

## 19. Bài tập có đáp án

### Bài 1 — remainder và mod

Tính `BigInteger.valueOf(-13).remainder(BigInteger.valueOf(5))` và `.mod(BigInteger.valueOf(5))`.

**Đáp án:** `-3` và `2`. Cả hai cùng lớp đồng dư nhưng `mod` chọn đại diện không âm.

### Bài 2 — modulus âm

`BigInteger.valueOf(13).mod(BigInteger.valueOf(-5))` có trả 3 hoặc -2 không?

**Đáp án:** không. API ném `ArithmeticException` vì modulus không dương.

### Bài 3 — modulus bằng 1

`BigInteger.valueOf(-123456).mod(BigInteger.ONE)` bằng mấy?

**Đáp án:** `0`. Modulo 1 chỉ có một đại diện là 0.

### Bài 4 — modPow cơ bản

Tính `4^13 mod 497` bằng `BigInteger.modPow`.

**Đáp án:** `445`: `BigInteger.valueOf(4).modPow(BigInteger.valueOf(13), BigInteger.valueOf(497))`.

### Bài 5 — so sánh pow và modPow

`BigInteger.TWO.pow(10)` khác `BigInteger.TWO.modPow(BigInteger.TEN,BigInteger.valueOf(17))` thế nào?

**Đáp án:** `1024` và `4`. `pow` tính lũy thừa đầy đủ; `modPow` cho kết quả modulo.

### Bài 6 — số mũ âm

`BigInteger.valueOf(3).modPow(BigInteger.valueOf(-1), BigInteger.valueOf(11))` trả gì?

**Đáp án:** `4`, vì `3×4≡1 (mod11)`. Đây là nghịch đảo, không phải số thực 1/3.

### Bài 7 — số mũ âm thứ hai

`3^(-2) mod 11` có giá trị gì?

**Đáp án:** `5` vì nghịch đảo của 3 là 4, và `4² mod 11 =16 mod 11=5`.

### Bài 8 — điều kiện nghịch đảo

`6.modInverse(15)` thành công không? Vì sao?

**Đáp án:** không, ném `ArithmeticException` vì `gcd(6,15)=3≠1`.

### Bài 9 — modulus không nguyên tố

`3.modInverse(10)` bằng bao nhiêu?

**Đáp án:** `7` vì `3×7=21≡1 (mod10)`. Modulus hợp số 10 vẫn cho phép nghịch đảo của 3.

### Bài 10 — cơ số âm

`(-2)^5 mod 13` trả giá trị nào qua `modPow`?

**Đáp án:** `7`, vì `-32 ≡7 (mod13)`. Cơ số âm hợp lệ.

### Bài 11 — số mũ bằng zero

`0.modPow(0,7)` và `0.modPow(0,1)` trả gì?

**Đáp án:** `1` và `0`. Quy tắc là `1 mod m` khi exponent bằng zero.

### Bài 12 — điều kiện mũ âm

`6.modPow(-1,15)` có được phép không?

**Đáp án:** cú pháp method nhận exponent âm, nhưng phép tính ném `ArithmeticException` vì cơ số không khả nghịch modulo 15.

### Bài 13 — giải đồng dư

Giải `3*x ≡ 5 (mod 11)` bằng modInverse.

**Đáp án:** `inverse(3)=4`, nên `x≡5×4≡20≡9 (mod11)`. Có thể viết `bi(5).multiply(bi(3).modInverse(bi(11))).mod(bi(11))`, với `bi(long)` là helper tạo BigInteger.

### Bài 14 — kiểm tra đồng dư

`-13` và `2` có bằng nhau qua `BigInteger.equals` không? Có đồng dư mod 5 không?

**Đáp án:** không bằng nhau theo `equals`, nhưng `(-13).mod(5)=2.mod(5)=2` nên đồng dư.

### Bài 15 — so sánh hai giá trị khi làm khóa modulo

Khi cần nhóm số nguyên theo lớp đồng dư modulo `m>0`, có nên dùng `a` trực tiếp hay `a.mod(m)`?

**Đáp án:** dùng `a.mod(m)` làm canonical key nếu yêu cầu nhóm theo lớp dư. Cùng lớp dư có thể chứa nhiều số nguyên khác nhau.

### Bài 16 — kiểm tra modulus

Một hàm nghiệp vụ yêu cầu `m>1` và cơ số khả nghịch nếu e âm. Nên validate theo thứ tự nào?

**Đáp án:** kiểm tra non-null; kiểm tra `m.compareTo(BigInteger.ONE)>0`; nếu `e.signum()<0` thì kiểm tra `a.gcd(m).equals(ONE)`; sau đó gọi `a.modPow(e,m)`. `m>1` là ràng buộc nghiệp vụ mạnh hơn `m>0` của API.

### Bài 17 — khái niệm rút gọn

Tại sao `2*x ≡ 2*y (mod4)` không suy ra `x≡y (mod4)`?

**Đáp án:** `2` không khả nghịch modulo `4` vì `gcd(2,4)=2`. Ví dụ `x=1,y=3` phản chứng.

### Bài 18 — ứng dụng RSA

Trong ví dụ nhỏ, `e=17` và `φ(n)=3120`, tính `d=e.modInverse(phi)` và `65^e mod 3233`.

**Đáp án:** `d=2753` và ciphertext `2790`; `2790^2753 mod 3233=65`. Chỉ là bài toán minh họa, không dùng bảo mật thật.

## 20. Checklist trước khi sử dụng trong dự án

- [ ] Tôi biết `mod` trả đại diện **không âm** với modulus dương, khác `remainder` khi receiver âm.
- [ ] Tôi kiểm tra `m.signum()>0` trước `mod`/`modPow`/`modInverse`.
- [ ] Tôi biết `m=1` hợp lệ theo API nhưng có thể bị nghiệp vụ cấm.
- [ ] Tôi dùng `modPow` cho lũy thừa modulo lớn, thay vì `pow` rồi `mod`.
- [ ] Tôi phân biệt kiểu tham số exponent của `pow(int)` và `modPow(BigInteger,BigInteger)`.
- [ ] Tôi biết `modPow` **cho phép exponent âm** nếu cơ số có nghịch đảo modulo m.
- [ ] Tôi dùng `gcd(a,m)=1` để xác định tồn tại `modInverse`, không đòi modulus nguyên tố một cách không cần thiết.
- [ ] Tôi phân biệt nghịch đảo modulo với phép chia số nguyên hoặc phân số thông thường.
- [ ] Tôi không rút gọn nhân tử không khả nghịch trong đồng dư.
- [ ] Tôi biết cách nhận diện ngoại lệ `ArithmeticException` cho modulus không dương hoặc thiếu nghịch đảo.
- [ ] Tôi biết null gây `NullPointerException` và BigInteger immutable.
- [ ] Tôi xét trường hợp biên: 0, 1, số âm, exponent 0 và exponent âm.
- [ ] Tôi kiểm tra kết quả nghịch đảo bằng `a.multiply(inv).mod(m).equals(BigInteger.ONE.mod(m))`.
- [ ] Tôi tránh nhầm reference `==` với equality theo giá trị `equals`.
- [ ] Tôi giới hạn kích thước input nếu phép toán có thể bị lạm dụng làm tiêu hao CPU/RAM.
- [ ] Tôi không sử dụng các chương trình minh họa modular arithmetic làm hệ thống bảo mật thực tế.
- [ ] Tôi đã biên dịch/chạy năm chương trình mẫu và so sánh stdout.

## 21. Tài liệu chuẩn và nguồn đọc tiếp

- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html) — hợp đồng `mod`, `remainder`, `modPow`, `modInverse`, `pow`, `gcd` và ngoại lệ.
- [Java SE 17 — ArithmeticException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html) — ngoại lệ cho các phép toán số học không hợp lệ.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — lớp khác phục vụ số thập phân, **không phải** công cụ thay thế đồng dư nguyên.
- [JLS 17, `4.2.2 Integer Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.2) — phép chia và phần dư của integer primitives để so sánh với `BigInteger.remainder`.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html) — API mật mã mức cao; minh họa toán học `modPow` không thay nó.
- [Java SE 17 — Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — API chữ ký số mức cao; không dùng raw modular exponentiation tự chế để ký.

**Kết luận:** ba API có phạm vi riêng rõ ràng: **`mod`** chuẩn hóa phần dư trong `[0,m−1]`, **`modPow`** tính lũy thừa modulo hiệu quả và hỗ trợ exponent âm khi khả nghịch, còn **`modInverse`** tìm nghiệm nghịch đảo chỉ khi `gcd(a,m)=1`. Phần lớn lỗi không đến từ cú pháp Java mà đến từ **quên kiểm tra modulus, tính khả nghịch và trường hợp biên**.