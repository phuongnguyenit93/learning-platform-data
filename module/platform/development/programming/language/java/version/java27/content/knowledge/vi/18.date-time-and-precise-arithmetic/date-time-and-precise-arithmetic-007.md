# BigInteger, Math và lựa chọn bộ sinh số ngẫu nhiên trong Java 27

Khi lập trình Java 27, ba nhóm nhu cầu trông có vẻ giống “làm việc với số” nhưng yêu cầu kỹ thuật rất khác nhau:

1. **Số nguyên vượt giới hạn `long`**: dùng `java.math.BigInteger` để tính toán số nguyên với độ chính xác tùy ý trong phạm vi tài nguyên cho phép.
2. **Phép toán số học trên kiểu nguyên thủy**: dùng `java.lang.Math` để tính hàm số học và phát hiện tràn số bằng nhóm `...Exact` khi cần.
3. **Sinh số ngẫu nhiên**: chọn thuật toán phù hợp giữa `java.util.random.RandomGenerator`, `ThreadLocalRandom`, `SplittableRandom` và `java.security.SecureRandom` theo yêu cầu về tốc độ, khả năng tái lập, đa luồng và bảo mật.

Đây đều là API Java SE còn được hỗ trợ trong **Java 27**. Nội dung chỉ sử dụng cú pháp chính thức, không cần `--enable-preview` và không khuyến khích các mẫu tạo số ngẫu nhiên không phù hợp trong ngữ cảnh an ninh.

## 1. Chọn đúng kiểu số và đúng generator trước khi viết code

| Nhu cầu | Lựa chọn chính | Vì sao |
| --- | --- | --- |
| Chỉ số đếm và phép tính nằm chắc trong phạm vi 32-bit | `int` và `Math.addExact(...)` khi cần chặn overflow | Gọn, ít cấp phát |
| Số nguyên có thể lớn hơn `int` nhưng vừa `long` | `long` và `Math.multiplyExact(...)` hoặc các phép toán exact khác | 64-bit, kiểm soát tràn số |
| Số nguyên không giới hạn bởi 64-bit | `BigInteger` | Tính chính xác theo giá trị nguyên |
| Tiền tệ, tỷ lệ thập phân cần quy tắc làm tròn | `BigDecimal` và `RoundingMode` | Không dùng `BigInteger` để biểu diễn trực tiếp phần thập phân |
| Hàm lượng giác, logarit, căn bậc hai | `Math` với `double`/`float` | Phép tính gần đúng dấu phẩy động theo quy tắc Java |
| Dữ liệu thử nghiệm cần cùng seed để tái lập | `RandomGeneratorFactory` + tên thuật toán cố định + seed | Có thể tái tạo chuỗi theo generator đã chọn |
| Random số thường trong luồng công việc đơn giản | `RandomGenerator` hoặc `ThreadLocalRandom.current()` | API chọn số trong miền xác định |
| Nhiều tác vụ tính toán cần generator riêng | `SplittableRandom` hoặc loại `SplittableGenerator` phù hợp | Dùng `split()` để tách trạng thái thay vì chia sẻ một object |
| Mã khôi phục, token, giá trị khó đoán | `SecureRandom` | Bộ sinh ngẫu nhiên có bảo đảm an toàn mật mã |

**Đừng dùng `double` để lưu số nguyên cực lớn** chỉ vì `double` có thể biểu diễn một số với biên độ rất cao; `double` chỉ giữ chính xác hữu hạn chữ số nhị phân và có thể làm tròn. Ngược lại, `BigInteger` **không** thay thế mọi tính toán dấu phẩy động.

## 2. BigInteger: số nguyên chính xác với độ dài tùy ý

`BigInteger` là lớp **immutable** (*bất biến*) trong package `java.math`. Giá trị số nguyên của nó có thể có nhiều chữ số hơn `long`, miễn bộ nhớ, thời gian chạy và giới hạn triển khai cho phép. Mọi phép toán như `add`, `multiply` hay `pow` đều trả về **một giá trị `BigInteger` mới** (hoặc có thể tái sử dụng instance theo cách triển khai), chứ không sửa giá trị của toán hạng.

### 2.1. Tạo BigInteger đúng cách

```java
import java.math.BigInteger;

BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger ten = BigInteger.TEN;

BigInteger fromLong = BigInteger.valueOf(2_000_000_000L);
BigInteger fromText = new BigInteger("123456789012345678901234567890");
BigInteger binary = new BigInteger("101101", 2); // 45
```

- `BigInteger.valueOf(long)` phù hợp với dữ liệu đã là `long`.
- `new BigInteger(String)` phù hợp với chuỗi thập phân quá lớn cho `long`.
- `new BigInteger(String, radix)` phù hợp với cách biểu diễn ở cơ số 2–36.
- Các hằng `ZERO`, `ONE`, `TWO`, `TEN` tiện cho phép toán thường gặp.
- Chuỗi số không hợp lệ gây `NumberFormatException`. Không nên nhận chuỗi số dài không kiểm soát từ client rồi parse vô hạn vì có thể gây tải CPU/bộ nhớ lớn.

**Không truyền một số quá lớn dưới dạng literal `long` trước khi chuyển đổi**:

```java
// Sai: literal đã vượt miền long trước khi gọi valueOf
// BigInteger bad = BigInteger.valueOf(123456789012345678901234567890L);

// Đúng:
BigInteger good = new BigInteger("123456789012345678901234567890");
```

### 2.2. Toán tử Java không thay thế method BigInteger

Với kiểu primitive, ta viết `a + b`, `a * b` và `a % b`. Với `BigInteger`, cần gọi method:

| Phép toán | BigInteger | Ví dụ |
| --- | --- | --- |
| Cộng | `a.add(b)` | `a + b` theo số nguyên |
| Trừ | `a.subtract(b)` | `a - b` |
| Nhân | `a.multiply(b)` | `a × b` |
| Chia lấy thương | `a.divide(b)` | Chia nguyên, làm tròn về 0 |
| Lấy dư | `a.remainder(b)` | Dư mang dấu của số bị chia nếu khác 0 |
| Chia lấy cả thương và dư | `a.divideAndRemainder(b)` | Mảng hai phần tử `[quotient, remainder]` |
| Trị tuyệt đối | `a.abs()` | Giá trị không âm |
| Lũy thừa | `a.pow(nonNegativeInt)` | Số mũ là `int` không âm |
| Ước chung lớn nhất | `a.gcd(b)` | GCD không âm |
| So sánh | `a.compareTo(b)` | Âm / 0 / dương |
| Min / max | `a.min(b)` / `a.max(b)` | Chọn giá trị |
| Số bit của độ lớn | `a.bitLength()` | Phục vụ thuật toán bit |

Ví dụ đầy đủ:

```java
// File: BigIntegerBasicsDemo.java
import java.math.BigInteger;

public class BigIntegerBasicsDemo {
    public static void main(String[] args) {
        BigInteger a = new BigInteger("98765432109876543210");
        BigInteger b = new BigInteger("12345678901234567890");

        System.out.println(a.add(b));       // 111111111011111111100
        System.out.println(a.subtract(b));  // 86419753208641975320
        System.out.println(a.gcd(b));       // 900000000090
        System.out.println(a.compareTo(b) > 0); // true

        BigInteger power = BigInteger.TEN.pow(30);
        System.out.println(power); // 1 và 30 chữ số 0
    }
}
```

Lưu ý `a.add(b);` **không** làm `a` tăng lên. Muốn cập nhật biến đang giữ tổng, dùng `a = a.add(b);`. Bất biến giúp chia sẻ một giá trị `BigInteger` không cần lo thao tác cộng trên reference khác làm nó thay đổi.

### 2.3. So sánh nội dung, không so sánh reference

```java
BigInteger left = new BigInteger("1000000000000000000");
BigInteger right = new BigInteger("1000000000000000000");

System.out.println(left.equals(right));       // true
System.out.println(left.compareTo(right) == 0); // true

// Không dùng left == right để so sánh giá trị.
```

Dùng `equals` khi cần bằng nhau và `compareTo` khi cần nhỏ/lớn. `BigInteger` là kiểu bất biến, nhưng việc JVM có thể tái sử dụng một số instance không thay đổi quy tắc: `==` chỉ so sánh tham chiếu object.

## 3. Phép chia, phần dư và số âm

Số nguyên âm rất dễ gây nhầm lẫn giữa **dư theo phép chia nguyên** và **modulo không âm**.

```java
BigInteger negative = BigInteger.valueOf(-17);
BigInteger modulus = BigInteger.valueOf(5);

System.out.println(negative.divide(modulus));     // -3
System.out.println(negative.remainder(modulus));  // -2
System.out.println(negative.mod(modulus));        // 3

System.out.println(-17 / 5);                // -3
System.out.println(-17 % 5);                // -2
System.out.println(Math.floorDiv(-17, 5));  // -4
System.out.println(Math.floorMod(-17, 5));  // 3
```

Vì sao khác nhau?

- `BigInteger.divide` làm tròn thương **về 0**, tương tự toán tử nguyên `/`.
- `BigInteger.remainder` trả dư theo quy tắc của `%`; khi số bị chia âm, dư khác 0 cũng âm.
- `BigInteger.mod` trả phần dư **không âm** từ `0` đến `m − 1`, nhưng yêu cầu `m > 0`.
- `Math.floorDiv` làm tròn thương về âm vô cực. `Math.floorMod` có dấu cùng số chia (hoặc bằng 0); với số chia dương, kết quả ở `[0, m)`.

Bảng phân biệt:

| Nhu cầu | Chọn |
| --- | --- |
| Phép chia nguyên giống kiểu `long` | `a.divide(b)` |
| Cần cả thương và dư một lượt | `a.divideAndRemainder(b)` |
| Dư theo Java `%` | `a.remainder(b)` |
| Modulo theo số học với mô-đun dương | `a.mod(positiveModulus)` |
| Chia nguyên kiểu primitive làm tròn xuống | `Math.floorDiv(x,y)` |
| Đưa index âm về miền `0..n-1` với `n > 0` | `Math.floorMod(index,n)` |

Chia cho 0 gây `ArithmeticException`. `BigInteger.mod(m)` và các phép toán modulo như `modPow`, `modInverse` yêu cầu mô-đun dương theo điều kiện API; kiểm tra trước khi gọi.

## 4. Lũy thừa, modulo và số nguyên tố

`BigInteger` hỗ trợ nhiều phép toán quan trọng cho thuật toán số nguyên lớn:

```java
BigInteger base = BigInteger.valueOf(7);
BigInteger exponent = BigInteger.valueOf(100);
BigInteger modulus = BigInteger.valueOf(13);

BigInteger result = base.modPow(exponent, modulus);
System.out.println(result); // 9: 7^100 mod 13

BigInteger g = BigInteger.valueOf(48).gcd(BigInteger.valueOf(18));
System.out.println(g); // 6

BigInteger inverse = BigInteger.valueOf(3)
        .modInverse(BigInteger.valueOf(11));
System.out.println(inverse); // 4, vì 3 * 4 mod 11 = 1
```

`modPow` tính lũy thừa modulo mà không cần tạo trước toàn bộ số `base.pow(exponent)` khổng lồ, phù hợp với các thuật toán số học modular. `modInverse` chỉ tồn tại nếu phần tử và mô-đun nguyên tố cùng nhau (và mô-đun dương); khi không có nghịch đảo, Java ném `ArithmeticException`.

### 4.1. Thử tính nguyên tố là phép thử xác suất

```java
BigInteger candidate = new BigInteger("32416190071");
System.out.println(candidate.isProbablePrime(100)); // true

BigInteger composite = BigInteger.valueOf(91);
System.out.println(composite.isProbablePrime(100)); // false
```

`isProbablePrime(certainty)` kiểm tra tính **có lẽ nguyên tố**, không phải chứng minh nguyên tố tuyệt đối trong mọi trường hợp. Với `certainty` phù hợp, xác suất sai bị giới hạn theo đặc tả; `false` cho biết composite, `true` có nghĩa rất có khả năng nguyên tố. Nếu giải thuật yêu cầu chứng minh nguyên tố, cần quy trình/chứng cứ chuyên biệt ngoài một lời gọi kiểm tra xác suất.

`BigInteger.probablePrime(bitLength, random)` có thể tạo số nguyên tố xác suất với độ dài bit chỉ định. **Không nên tự lắp ghép hệ mật mã** bằng `modPow` và một vài số nguyên tố tự sinh; để tạo khóa/chữ ký/trao đổi khóa, ưu tiên API mật mã được kiểm tra như `KeyPairGenerator` và thư viện bảo mật phù hợp. `BigInteger` chỉ cung cấp toán học nền tảng, không cung cấp toàn bộ bảo đảm an ninh của một giao thức.

### 4.2. Bit và chuyển kiểu

`BigInteger` cũng có `testBit`, `setBit`, `clearBit`, `shiftLeft` và `shiftRight`. Không có `unsigned right shift` tương đương `>>>` vì kích thước biểu diễn không cố định.

```java
BigInteger flags = BigInteger.ZERO.setBit(5);
System.out.println(flags);            // 32
System.out.println(flags.testBit(5)); // true
System.out.println(flags.clearBit(5));// 0

BigInteger huge = BigInteger.ONE.shiftLeft(100);
System.out.println(huge.bitLength()); // 101
```

Các phương thức chuyển về primitive như `intValue()` hoặc `longValue()` **có thể mất thông tin** nếu giá trị vượt miền đích. Khi cần bảo vệ tính đúng đắn, dùng `intValueExact()` hoặc `longValueExact()` để ném `ArithmeticException` nếu không biểu diễn được.

```java
BigInteger huge = BigInteger.TEN.pow(40);

// long unsafe = huge.longValue();       // Có thể mất các bit cao
// long safe = huge.longValueExact();     // ArithmeticException
long safe = BigInteger.valueOf(2026).longValueExact();
System.out.println(safe); // 2026
```

## 5. Ví dụ ứng dụng: giai thừa bằng BigInteger

Với `n! = 1 × 2 × ... × n`, kiểu `long` chỉ biểu diễn chính xác đến `20!`; từ `21!` đã vượt `Long.MAX_VALUE`. Dùng `BigInteger`:

```java
// File: FactorialDemo.java
import java.math.BigInteger;

public class FactorialDemo {
    static BigInteger factorial(int n) {
        if (n < 0 || n > 5_000) {
            throw new IllegalArgumentException("n must be 0..5000");
        }

        BigInteger result = BigInteger.ONE;
        for (int i = 2; i <= n; i++) {
            result = result.multiply(BigInteger.valueOf(i));
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(factorial(5));   // 120
        System.out.println(factorial(21));  // 51090942171709440000
        System.out.println(factorial(0));   // 1
    }
}
```

**Giới hạn `5_000` chỉ là chính sách bảo vệ tài nguyên cho ví dụ**, không phải giới hạn của bản thân `BigInteger`. Trong dịch vụ nhận dữ liệu từ người dùng, cần giới hạn độ lớn đầu vào, thời gian CPU, mức dùng bộ nhớ, độ dài chuỗi kết quả và số request. `BigInteger` không biến mọi phép tính trở thành “vô hạn” về tài nguyên.

## 6. Math: số học primitive, overflow và phép toán dấu phẩy động

Lớp `Math` chứa các phương thức `static`, không có instance cần tạo. Một số hàm hoạt động trên `int`/`long`, những hàm khác trên `float`/`double`.

### 6.1. Tràn số nguyên: im lặng hay báo lỗi?

Toán tử `+`, `-`, `*` trên `int`/`long` có thể **overflow** mà không ném exception:

```java
int wrapped = Integer.MAX_VALUE + 1;
System.out.println(wrapped); // -2147483648
```

Nếu nghiệp vụ không chấp nhận kết quả bị cuộn vòng, dùng nhóm API exact:

```java
int sum = Math.addExact(1_500_000_000, 500_000_000);
long product = Math.multiplyExact(2_000_000_000L, 3L);
int value = Math.toIntExact(2026L);

System.out.println(sum);     // 2000000000
System.out.println(product); // 6000000000
System.out.println(value);   // 2026

// Math.addExact(Integer.MAX_VALUE, 1); // ArithmeticException
// Math.absExact(Integer.MIN_VALUE);     // ArithmeticException
// Math.toIntExact(Long.MAX_VALUE);      // ArithmeticException
```

| Method | Mục đích |
| --- | --- |
| `addExact(x,y)` | Cộng, báo lỗi khi tràn |
| `subtractExact(x,y)` | Trừ, báo lỗi khi tràn |
| `multiplyExact(x,y)` | Nhân, báo lỗi khi tràn |
| `incrementExact(x)`, `decrementExact(x)` | Cộng/trừ 1 có kiểm tra |
| `negateExact(x)`, `absExact(x)` | Đổi dấu/lấy trị tuyệt đối và kiểm tra trường hợp giá trị nhỏ nhất |
| `toIntExact(longValue)` | Đổi `long` sang `int` không mất dữ liệu |
| `divideExact(x,y)` | Chia nguyên có kiểm tra `MIN_VALUE / -1` và chia 0 |
| `floorDiv(x,y)`, `floorMod(x,y)` | Thương làm tròn xuống và modulo theo floor division |
| `floorDivExact(x,y)` | Kết hợp floor division và kiểm tra overflow |
| `powExact(x, exponent)` | Lũy thừa nguyên với kiểm tra overflow, theo overload hiện hành của Java 27 |

**Phạm vi:** các method `...Exact` không tự chuyển kết quả vượt `int`/`long` sang `BigInteger`; chúng **ném lỗi**. Nếu số thực sự cần vượt phạm vi cố định, sử dụng `BigInteger` từ đầu. `Math.abs(Integer.MIN_VALUE)` trả lại chính số âm nhỏ nhất do không có trị tuyệt đối dương biểu diễn được; `Math.absExact` giúp phát hiện tình huống này.

### 6.2. Các phép chia cần làm tròn

```java
System.out.println(-7 / 3);               // -2
System.out.println(Math.floorDiv(-7, 3));  // -3
System.out.println(Math.floorMod(-7, 3));  // 2

System.out.println(Math.ceilDiv(7, 3));    // 3
System.out.println(Math.ceilDiv(-7, 3));   // -2
```

Dùng `floorDiv`/`floorMod` khi nghiệp vụ yêu cầu modulo với miền dương hoặc chỉ số vòng lặp; dùng `ceilDiv` khi cần số lượng “ô chứa” cho một nhóm phần tử `(7 phần tử, 3 phần tử mỗi ô → 3 ô)`. Không tự viết `(n + d - 1) / d` một cách máy móc vì có thể overflow và không đúng với một số giá trị âm.

### 6.3. Math với double không phải số học thập phân chính xác

```java
System.out.println(0.1 + 0.2 == 0.3); // false
System.out.println(Math.sqrt(81.0));  // 9.0
System.out.println(Math.hypot(3.0, 4.0)); // 5.0
```

`double` biểu diễn nhị phân với độ chính xác hữu hạn; nhiều phân số thập phân không được biểu diễn chính xác. `Math.sqrt`, `log`, `sin`, `pow` là các phép toán trên floating-point; chúng không biến dữ liệu thành số thập phân chính xác.

- `Math.pow(double,double)` trả `double`, **không phù hợp** để tạo số nguyên lớn chính xác rồi ép kiểu.
- `Math.hypot(x,y)` tính `sqrt(x² + y²)` theo phương pháp tránh overflow/underflow trung gian tốt hơn cách trực tiếp.
- `Math.fma(a,b,c)` tính tích cộng rồi làm tròn **một lần**, có thể cải thiện chất lượng tính toán floating-point; nó không giải quyết nhu cầu số tiền thập phân chính xác.
- Khi cần làm tròn số thập phân theo quy tắc tài chính, dùng `BigDecimal` và `RoundingMode` theo hợp đồng nghiệp vụ.

### 6.4. So sánh các họ API toán học

| API | Miền số | Bảo đảm phù hợp |
| --- | --- | --- |
| Toán tử nguyên primitive | `int`/`long` | Nhanh, không tự báo overflow |
| `Math.*Exact` | `int`/`long` | Báo overflow bằng `ArithmeticException` |
| `BigInteger` | Số nguyên tùy ý | Tính đúng giá trị nguyên, có chi phí bộ nhớ/CPU |
| `Math` trên `double` | Dấu phẩy động nhị phân | Hàm toán học gần đúng, chịu quy tắc floating-point |
| `BigDecimal` | Thập phân tùy ý theo precision/scale | Tính thập phân và làm tròn có kiểm soát |

Cụm từ **“chính xác”** phụ thuộc yêu cầu: muốn biết có overflow hay không thì `Math.addExact`; muốn kết quả vượt `long` thì `BigInteger`; muốn tính `12.35 × 7.5` theo tiền tệ thì `BigDecimal`; còn phép đo vật lý thường dùng `double` với sai số phù hợp.

## 7. Sinh ngẫu nhiên: phân biệt yêu cầu thống kê và an ninh

Giá trị *pseudorandom* được sinh từ trạng thái của một thuật toán. Cùng thuật toán và cùng trạng thái khởi tạo có thể tạo cùng chuỗi, rất hữu ích khi chạy mô phỏng hoặc kiểm thử. Nhưng tính chất đó cũng có nghĩa **không nên dùng PRNG thống kê để tạo token bảo mật**.

Java 27 có API `java.util.random.RandomGenerator` làm **hợp đồng chung** cho nhiều bộ sinh số. Các lớp `java.util.Random`, `SplittableRandom`, `ThreadLocalRandom`, `SecureRandom` đều triển khai interface này, nhưng **bảo đảm bảo mật không giống nhau**.

### 7.1. Bảng quyết định

| Tình huống | Công cụ | Seed / concurrency | Có dùng cho bí mật? |
| --- | --- | --- | --- |
| Tính toán/simulation không yêu cầu thuật toán cụ thể | `RandomGenerator` tạo qua factory | Chọn implementation, seed khi cần | Không |
| Test cần kết quả lặp lại | `RandomGeneratorFactory.of(name).create(seed)` | Cố định tên thuật toán, seed và trình tự gọi | Không |
| Mỗi thread cần random thông thường ít tranh chấp | `ThreadLocalRandom.current()` | Trạng thái theo thread, không cho set seed tùy ý | Không |
| Tác vụ có thể tách thành nhiều công việc con | `SplittableRandom.split()` hoặc `SplittableGenerator` | Generator riêng cho mỗi nhiệm vụ | Không |
| Token truy cập, mã khôi phục bí mật, IV/nonce có yêu cầu khó đoán | `SecureRandom` và API mật mã phù hợp | Để provider tự cấp entropy, quản lý vòng đời đúng | **Có** |
| Một số thực `[0.0,1.0)` thật nhanh trong mã không nhạy cảm | `Math.random()` | Không chỉ định seed trực tiếp qua Math | Không |

`Math.random()` là API có sẵn để sinh `double` giả ngẫu nhiên, nhưng không có khả năng cấu hình rõ thuật toán/seed và không phù hợp cho bảo mật. Trong mã mới, `RandomGenerator` giúp khai báo ý định thiết kế rõ hơn và dễ tiêm generator vào các thành phần cần test.

## 8. RandomGenerator: API thống nhất cho PRNG thông thường

`RandomGenerator` hỗ trợ `nextInt()`, `nextInt(bound)`, `nextInt(origin,bound)`, `nextLong`, `nextDouble`, `nextBoolean`, tạo stream số ngẫu nhiên và nhiều phép lấy mẫu khác.

Một ví dụ dùng thuật toán được đặt tên:

```java
// File: RandomRangesDemo.java
import java.util.random.RandomGenerator;

public class RandomRangesDemo {
    public static void main(String[] args) {
        RandomGenerator rng = RandomGenerator.of("L64X128MixRandom");

        int die = rng.nextInt(1, 7);       // 1..6
        int position = rng.nextInt(10);    // 0..9
        long identifier = rng.nextLong(100L, 200L); // 100..199
        double sample = rng.nextDouble(); // [0.0, 1.0)

        System.out.println("Die = " + die);
        System.out.println("Position = " + position);
        System.out.println("Identifier = " + identifier);
        System.out.println("Sample = " + sample);
    }
}
```

Với `nextInt(origin,bound)`, **origin bao gồm**, **bound không bao gồm**. Nếu `origin >= bound` hoặc `bound <= 0` ở các overload liên quan, API ném `IllegalArgumentException`. Không viết `(int)(Math.random() * range)` khi đã có `nextInt(range)`: phương thức bounded thể hiện biên rõ ràng và có thuật toán tránh các sai lệch thường gặp khi tự lấy phần dư.

### 8.1. Seed cố định để tái lập kiểm thử

```java
// File: ReproducibleRandomDemo.java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ReproducibleRandomDemo {
    public static void main(String[] args) {
        var factory = RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(2027L);
        RandomGenerator again = factory.create(2027L);

        boolean same = true;
        for (int i = 0; i < 10; i++) {
            if (first.nextInt(1_000_000) != again.nextInt(1_000_000)) {
                same = false;
            }
        }

        System.out.println("Same sequence = " + same); // true
    }
}
```

Để tái lập một lần chạy, cần lưu **thuật toán, seed, phiên bản môi trường khi cần, thứ tự và số lượng lời gọi**, không chỉ seed. Một lần gọi `nextLong` thừa ở một nhánh chương trình có thể thay đổi toàn bộ chuỗi tiếp theo. Khi tách tác vụ song song, thời điểm lấy mẫu giữa các thread cũng có thể thay đổi, nên **không chia sẻ một generator mutable** rồi kỳ vọng thứ tự kết quả giống nhau giữa các lần chạy.

`RandomGeneratorFactory.getDefault()` và `RandomGenerator.getDefault()` tiện cho ứng dụng không ràng buộc thuật toán; **không** nên dựa vào mặc định đó để giữ một chuỗi số cố định khi chuyển JDK. Cần ghi rõ tên thuật toán trong cấu hình/kiểm thử.

### 8.2. Chọn generator bằng factory

`RandomGeneratorFactory` cho phép xem danh sách implementation khả dụng và metadata như tên thuật toán, nhóm thuật toán, period, khả năng split/jump và thông tin deprecation.

```java
import java.util.Comparator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory.all()
    .filter(f -> !f.isDeprecated())
    .sorted(Comparator.comparing(RandomGeneratorFactory::name))
    .forEach(f -> System.out.println(f.name()));
```

Đây là mảnh ví dụ đặt trong một method (ví dụ `main`). Tên thuật toán khả dụng có thể thay đổi theo JDK/provider. Không có một thuật toán luôn tốt nhất cho mọi mục đích; đừng chọn “an toàn mật mã” chỉ dựa vào `stateBits()` hoặc period rất dài. Những chỉ số này không tự tạo bảo đảm bảo mật.

**LXM** như `"L64X128MixRandom"` là một lựa chọn PRNG thống kê phù hợp nhiều mô phỏng/thử nghiệm; **không** phải lựa chọn tạo secret. Nếu cần tương thích giữa môi trường, xác nhận thuật toán được hỗ trợ và có chính sách kiểm thử nhất quán.

## 9. ThreadLocalRandom và SplittableRandom trong môi trường đa luồng

### 9.1. ThreadLocalRandom: không chia sẻ một Random object

Trong đoạn xử lý đồng thời, `ThreadLocalRandom.current()` cung cấp generator gắn với thread hiện tại:

```java
import java.util.concurrent.ThreadLocalRandom;

static int chooseWorkerSlot(int count) {
    if (count <= 0) {
        throw new IllegalArgumentException("count must be positive");
    }
    return ThreadLocalRandom.current().nextInt(count);
}
```

Nên gọi `ThreadLocalRandom.current()` tại **thread đang chạy tác vụ**, không cất instance để chuyển qua thread khác. `ThreadLocalRandom` được thiết kế giảm contention trong nhiều tình huống multi-threaded và không hỗ trợ `setSeed` của người gọi.

Nếu cần mỗi bài test tái lập đúng một chuỗi theo seed, `ThreadLocalRandom` không phải công cụ thuận tiện. Tránh dùng nó cho token, reset password hoặc mọi thứ cần khó đoán.

### 9.2. SplittableRandom: tách nguồn số cho nhiều tác vụ

`SplittableRandom` có `split()` tạo generator mới có trạng thái độc lập để dùng trong nhánh xử lý riêng:

```java
// File: SplitRandomDemo.java
import java.util.SplittableRandom;

public class SplitRandomDemo {
    public static void main(String[] args) {
        SplittableRandom parent = new SplittableRandom(42L);
        SplittableRandom taskA = parent.split();
        SplittableRandom taskB = parent.split();

        int a = taskA.nextInt(100);
        int b = taskB.nextInt(100);

        System.out.println("Task A sample = " + a);
        System.out.println("Task B sample = " + b);
    }
}
```

`SplittableRandom` **không thread-safe** và được thiết kế để **split, không phải để chia sẻ** một instance giữa nhiều thread. Khi dùng mỗi instance trong một tác vụ, tính toán tránh việc các thread cùng sửa trạng thái generator.

Nếu cần định nghĩa rõ giao diện hơn là class cụ thể, `RandomGenerator.SplittableGenerator` biểu diễn các generator hỗ trợ khả năng này. Tính tái lập khi chạy song song còn phụ thuộc **cách phân chia luồng nhiệm vụ và lịch gọi split**. Với yêu cầu determinism nghiêm ngặt, dùng lịch cấp seed/nhánh rõ ràng, không trông vào thứ tự scheduling.

### 9.3. Vì sao không coi Java PRNG là “cryptographically secure”?

Một thuật toán giả ngẫu nhiên có thể có chu kỳ rất dài, phân phối thống kê tốt, chạy nhanh và tái lập được; điều đó **không chứng minh khó dự đoán** khi đối thủ biết một phần đầu ra. `RandomGenerator` là interface chung, **không** tự gắn tiêu chuẩn bảo mật cho mọi implementation. Với giá trị bí mật, cần một nguồn bảo đảm mật mã và quy trình sinh/quản lý secret phù hợp.

## 10. SecureRandom: tạo giá trị khó dự đoán

`java.security.SecureRandom` cung cấp nguồn sinh số có mức bảo đảm mật mã theo các provider của nền tảng. Ví dụ dưới đây tạo token 32 byte, rồi mã hóa Base64 URL-safe để có thể truyền qua API:

```java
// File: SecureTokenDemo.java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    static String newToken() {
        byte[] bytes = new byte[32]; // 256 bit dữ liệu đầu ra
        SECURE_RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        String token = newToken();
        System.out.println("Generated token length = " + token.length());
        // Không in hoặc ghi log token thật trong production.
    }
}
```

Đầu ra Base64 URL-safe của 32 byte **không padding** thường dài **43 ký tự**. Mẫu ví dụ chỉ in độ dài, không làm lộ nội dung token. Trong ứng dụng thực tế, token cần chính sách thời hạn, lưu trữ/phê chuẩn/revoke và chống lộ qua log/URL; việc sinh đủ ngẫu nhiên **chưa** là một hệ thống xác thực hoàn chỉnh.

Một số nguyên tắc quan trọng:

- `new SecureRandom()` cho phép provider khởi tạo seed từ nguồn entropy thích hợp. **Không** dùng `new SecureRandom(new byte[]{1,2,3})` hoặc seed cố định cho secret.
- `SecureRandom.getInstanceStrong()` chọn thuật toán theo cấu hình bảo mật; không có nghĩa mọi chương trình phải gọi nó. Một số provider/thiết lập có thể **block** khi lấy entropy.
- Tốc độ, tên thuật toán, cách tạo seed và các đặc tính có thể phụ thuộc provider/hệ điều hành.
- Không tự chuyển `SecureRandom.nextLong()` thành token dạng số rồi đoán rằng nó có 256 bit entropy. Dùng đủ số **byte** theo chính sách bảo mật, hoặc API mật mã chuyên trách.
- `SecureRandom` còn kế thừa các phương thức bounded từ `Random`/`RandomGenerator`, nhưng vẫn cần thiết kế đúng miền số, xác suất và độ khó đoán của token.

### 10.1. Sinh BigInteger ngẫu nhiên trong miền cho trước

Khi cần một số nguyên ngẫu nhiên phân phối đều trong đoạn `[0, upperExclusive)` với `upperExclusive > 0`, không dùng phép `randomBigInteger.mod(limit)` tùy tiện vì có thể gây *modulo bias* nếu kích thước miền mẫu không chia hết cho giới hạn.

Cách đơn giản dùng **rejection sampling**:

```java
import java.math.BigInteger;
import java.security.SecureRandom;

static BigInteger secureBelow(BigInteger upperExclusive, SecureRandom random) {
    if (upperExclusive.signum() <= 0) {
        throw new IllegalArgumentException("upperExclusive must be positive");
    }

    BigInteger candidate;
    do {
        candidate = new BigInteger(upperExclusive.bitLength(), random);
    } while (candidate.compareTo(upperExclusive) >= 0);

    return candidate;
}
```

Constructor `BigInteger(numBits, Random)` tạo số nguyên không âm sử dụng nguồn `Random` truyền vào; `SecureRandom` là subclass của `Random` nên có thể dùng ở đây. Mỗi ứng viên nằm trong đoạn `[0, 2^bits)`; thuật toán loại các ứng viên ngoài miền và trả một giá trị **không âm, nhỏ hơn giới hạn**. Khi nguồn bit là ngẫu nhiên thích hợp, việc loại mẫu tránh sai lệch phân phối do lấy dư.

Đây là ví dụ về **lấy mẫu số nguyên**, không phải một thiết kế giao thức mật mã hoàn chỉnh. Với yêu cầu bảo mật cao, cần đánh giá các yếu tố như timing, chính sách entropy, API domain-specific và cách sử dụng kết quả.

### 10.2. Ví dụ lựa chọn sai: Math.random cho secret

```java
// KHÔNG DÙNG CHO BẢO MẬT:
// int resetCode = (int) (Math.random() * 1_000_000);
```

Giá trị theo mẫu trên có miền nhỏ, độ khó đoán hạn chế và dùng PRNG không được cam kết an toàn mật mã. Ngay cả khi thay bằng `SecureRandom.nextInt(1_000_000)`, mã gồm 6 chữ số chỉ có một triệu khả năng; nếu dùng làm mã OTP, còn cần giới hạn số lần thử, thời hạn hết hiệu lực, khóa tạm thời và các biện pháp ứng dụng khác. Token session cần miền giá trị lớn hơn đáng kể.

## 11. Kết hợp Math và BigInteger với ngẫu nhiên: mô phỏng có thể tái lập

Một mô phỏng thường cần cả phép đếm chính xác và random không nhạy cảm. Hãy **tiêm `RandomGenerator` vào hàm**, để caller quyết định thuật toán và seed:

```java
// File: DiceSimulationDemo.java
import java.math.BigInteger;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class DiceSimulationDemo {
    static BigInteger countSixes(RandomGenerator rng, int trials) {
        if (trials < 0) {
            throw new IllegalArgumentException("trials must be non-negative");
        }

        BigInteger sixes = BigInteger.ZERO;
        for (int i = 0; i < trials; i++) {
            if (rng.nextInt(1, 7) == 6) {
                sixes = sixes.add(BigInteger.ONE);
            }
        }
        return sixes;
    }

    public static void main(String[] args) {
        var factory = RandomGeneratorFactory.of("L64X128MixRandom");

        BigInteger first = countSixes(factory.create(2027L), 100_000);
        BigInteger repeat = countSixes(factory.create(2027L), 100_000);

        System.out.println("Reproduced = " + first.equals(repeat)); // true
        System.out.println("Sixes: " + first);
    }
}
```

`BigInteger` ở đây minh họa cách dùng bộ đếm chính xác và immutable, dù `100_000` lần thử hoàn toàn có thể đếm bằng `int`. Trong chương trình thực tế, hãy chọn `long` hoặc `Math.addExact` nếu đủ giới hạn, thay vì tự động dùng `BigInteger` cho mọi biến đếm.

Tiêm generator vào method giúp:

- Viết test có seed cố định.
- Thay thuật toán mà không sửa thuật toán mô phỏng.
- Tránh lẫn lộn PRNG thống kê với `SecureRandom` ở nơi tạo secret.
- Định nghĩa rõ generator thuộc về một tác vụ hay một luồng, giảm rủi ro chia sẻ trạng thái không đúng.

## 12. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `long` tính giai thừa cho số lớn bị âm/sai | Overflow của kiểu 64-bit | Dùng `BigInteger` hoặc chặn phạm vi qua `Math.*Exact` |
| Tạo BigInteger từ literal `123...L` không biên dịch | Literal đã vượt miền `long` | Dùng `new BigInteger("...")` |
| `a.add(b)` xong nhưng `a` không đổi | `BigInteger` bất biến | Viết `a = a.add(b)` hoặc lưu kết quả vào biến mới |
| So sánh hai BigInteger bằng `==` ra false | `==` so reference | Dùng `equals` hoặc `compareTo` |
| `remainder` trả số âm, khác modulo kỳ vọng | Quy tắc Java `%`/`remainder` | Dùng `mod(m)` với `m > 0` |
| `modInverse` ném `ArithmeticException` | Không có nghịch đảo modulo hoặc mô-đun không hợp lệ | Kiểm tra `gcd(a,m) == 1` và `m > 0` |
| Chuyển từ BigInteger sang `long` bị sai | `longValue()` có thể mất dữ liệu | Dùng `longValueExact()` |
| `Math.abs(Integer.MIN_VALUE)` vẫn âm | Trị tuyệt đối dương không biểu diễn được | Dùng `Math.absExact` để báo lỗi hoặc nâng kiểu trước khi tính |
| `Math.pow` rồi ép `long` gây sai | `Math.pow` tính `double`, có rounding | Dùng `BigInteger.pow` hoặc `Math.powExact` khi phạm vi đủ |
| `0.1 + 0.2 != 0.3` | Sai số biểu diễn nhị phân | Dùng `BigDecimal` khi cần giá trị thập phân chính xác |
| `nextInt(1, 6)` không bao giờ cho 6 | Bound là **exclusive** | Dùng `nextInt(1, 7)` |
| Hai test khác nhau dù dùng cùng seed | Khác thuật toán hoặc khác thứ tự lời gọi | Cố định thuật toán, seed và thứ tự lấy mẫu |
| Test không tái lập với `ThreadLocalRandom` | Không điều khiển seed cá nhân theo cách dùng thông thường | Tiêm `RandomGenerator` có seed cố định |
| Kết quả ngẫu nhiên thay đổi ở parallel run | Chia sẻ trạng thái mutable và lịch chạy không xác định | Split/cấp generator riêng theo chính sách ổn định |
| Token sinh từ `Math.random()` có thể dự đoán | PRNG không phải CSPRNG | Dùng `SecureRandom` và đủ byte |
| Sinh `random % bound` bị lệch | Miền gốc có thể không chia hết cho `bound` | Dùng `nextInt(bound)` hoặc rejection sampling |
| Dùng BigInteger trên input rất dài khiến máy quá tải | Tính toán arbitrary precision tiêu tốn tài nguyên | Giới hạn đầu vào, độ lớn exponent và chi phí xử lý |

## 13. Checklist ra quyết định cho Java 27

1. **Xác định yêu cầu chính xác:** số nguyên vượt `long` thì chọn `BigInteger`; phép tính còn trong `long` nhưng không được overflow thì chọn `Math.*Exact`.
2. **Xác định loại số:** số nguyên và thập phân là hai bài toán khác nhau; tiền tệ với phần thập phân cần `BigDecimal`.
3. **Không dùng literal đã overflow:** đọc số nguyên lớn từ chuỗi và giới hạn kích thước đầu vào.
4. **Hiểu quy tắc dấu:** `remainder` khác `mod`; `/` khác `floorDiv` với số âm.
5. **Dùng chuyển đổi có kiểm tra:** `longValueExact`/`intValueExact` khi phải hạ từ BigInteger về primitive.
6. **Không xem Math floating-point là tính tiền chính xác:** tính sai số, miền và làm tròn rõ ràng.
7. **Chọn ngẫu nhiên theo nhu cầu:** giả ngẫu nhiên thống kê cho mô phỏng; `SecureRandom` cho secret.
8. **Nếu cần tái lập, cố định thuật toán và seed:** ghi nhận cả trình tự gọi cùng các thông số thí nghiệm.
9. **Nếu đa luồng, quản lý ownership generator:** `ThreadLocalRandom` theo thread; `SplittableRandom` tách instance theo task; không chia sẻ generator mutable không được thiết kế cho concurrency.
10. **Dùng bounded method:** `nextInt(origin,bound)` rõ biên và tránh tự xử lý phép dư sai.
11. **Bảo vệ thông tin bí mật:** không seed cố định cho `SecureRandom`, không ghi log token, thêm chính sách hạn dùng/chống brute force.
12. **Giới hạn độ phức tạp:** BigInteger lũy thừa/factorial, sinh số nguyên tố hoặc sinh chuỗi random dài vẫn cần giới hạn CPU, bộ nhớ và thời gian.
13. **Đọc hợp đồng Javadoc:** thuật toán factory, deprecation, period, khả năng chia tách và provider có thể ảnh hưởng thiết kế; đừng suy đoán từ tên lớp.

## Tài liệu tham khảo chính thức (Java SE 27)

- [`BigInteger` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html) — số nguyên tùy ý, phép chia/dư, modulo, kiểm tra nguyên tố, chuyển kiểu exact, bit operations.
- [`Math` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html) — hàm toán học, overflow checking, floor/ceil division, dấu phẩy động.
- [`BigDecimal` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html) — số thập phân chính xác theo scale/rounding, đối chiếu với BigInteger.
- [`RandomGenerator` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/random/RandomGenerator.html) — giao diện generator và các hàm `nextInt`, `nextLong`, `nextDouble`.
- [`RandomGeneratorFactory` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/random/RandomGeneratorFactory.html) — chọn thuật toán, tạo generator theo seed và metadata.
- [`java.util.random` — Java SE 27 package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/random/package-summary.html) — hướng dẫn chọn PRNG cho các loại workload.
- [`SplittableRandom` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SplittableRandom.html) — `split()` và cách dùng không chia sẻ mutable state.
- [`ThreadLocalRandom` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html) — generator dành cho thread hiện tại.
- [`SecureRandom` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/SecureRandom.html) — nguồn CSPRNG, provider/entropy và khả năng blocking.
