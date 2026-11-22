# ThreadLocalRandom: Phân biệt nhu cầu ngẫu nhiên thông thường với ngẫu nhiên mật mã

## 1. Vì sao chọn sai bộ sinh số ngẫu nhiên có thể thành lỗ hổng?

Java có nhiều API tạo giá trị ngẫu nhiên, nhưng **không phải mọi bộ sinh ngẫu nhiên đều phù hợp để tạo bí mật**. Một con số trông khó đoán khi in ra màn hình chưa đủ để ngăn kẻ tấn công suy đoán những giá trị tiếp theo. Ngược lại, dùng một bộ sinh mật mã cho mỗi lựa chọn UI nhỏ có thể gây chi phí và độ phức tạp không cần thiết.

Bài **“Phân biệt nhu cầu ngẫu nhiên thông thường với ngẫu nhiên mật mã”** thuộc chủ đề **`ThreadLocalRandom`** của module Java 7. Các khái niệm và API chính vẫn còn hiệu lực trên **Java 17+**:

- **Ngẫu nhiên thông thường:** dữ liệu giả ngẫu nhiên phục vụ load balancing trong thuật toán, mô phỏng, sample không nhạy cảm, số xúc xắc trong game không đặt cược, thời điểm jitter cho retry.
- **Ngẫu nhiên mật mã:** dữ liệu phải khó dự đoán đối với đối thủ có khả năng quan sát hệ thống, dùng cho access/reset tokens, session secrets, OTP, nonce/IV khi một giao thức bảo mật yêu cầu, và các bí mật tương tự.
- **`ThreadLocalRandom`:** nhanh và tránh tranh chấp khi nhiều threads cùng cần ngẫu nhiên thông thường; **không an toàn về mật mã**.
- **`SecureRandom`:** API Java cho bộ sinh số ngẫu nhiên mạnh về mật mã; lựa chọn mặc định khi tạo những giá trị **phải chống dự đoán**.

**Nguyên tắc quyết định:** hãy hỏi “nếu người ngoài dự đoán được giá trị kế tiếp thì có dẫn tới truy cập trái phép, giả mạo hoặc lợi ích tài chính không?”. Nếu có, yêu cầu là **security-sensitive**, không dùng `ThreadLocalRandom`, `Random`, `Math.random` hoặc `SplittableRandom` làm nguồn bí mật.

## 2. PRNG thông thường và CSPRNG khác nhau như thế nào?

### 2.1. Pseudorandom Number Generator (PRNG)

Bộ sinh giả ngẫu nhiên (PRNG) tạo một dãy số từ trạng thái/seed nội bộ theo một thuật toán xác định. Các giá trị có thể phân bố đủ tốt cho những công việc thống kê hoặc phân phối tải. Nhưng:

- Tính phân bố hợp lý **không** tự chứng minh độ khó dự đoán.
- Một thuật toán PRNG thông thường có thể để lộ trạng thái hoặc chuỗi tiếp theo nếu một phần output bị quan sát.
- Có seed khởi tạo “trông ngẫu nhiên” không tự biến thuật toán thành CSPRNG.
- Tốc độ và contention khi nhiều threads dùng chung một instance có thể khác nhau giữa API.

### 2.2. Cryptographically Secure PRNG (CSPRNG)

CSPRNG được thiết kế cho yêu cầu dự đoán khó ngay cả khi đối thủ biết thuật toán và có thể quan sát outputs. Nó còn cần nguồn entropy/seed phù hợp, thiết kế thuật toán và cơ chế thực thi đúng.

Trong Java, `java.security.SecureRandom` là API tiêu chuẩn cho nhu cầu này. Việc dùng nó **không tự giải quyết** các yếu tố khác: độ dài token, cách mã hóa, lưu token, expiration, rate limiting, chống replay, quản lý phiên, bảo vệ logs và quyền của người dùng.

### 2.3. Không lấy “đẹp về thống kê” làm chứng chỉ an toàn

Một dãy xúc xắc hiển thị tỷ lệ 1..6 gần nhau qua hàng triệu mẫu **không nói lên** người ngoài có thể dự đoán chính xác giá trị kế tiếp hay không. Kiểm thử tần suất phân bố không thay thế đánh giá mật mã.

**Cặp khái niệm cần nhớ:**

| Thuộc tính | PRNG thông thường | CSPRNG |
| --- | --- | --- |
| Mục tiêu chủ đạo | Hiệu quả, phân bố phù hợp với ứng dụng | Khó đoán cho mục đích bảo mật |
| Đầu ra nhìn ngẫu nhiên | Có | Có |
| Được thiết kế chống dự đoán bởi đối thủ | Không nhất thiết | Có |
| Dùng tạo reset/session token | **Không** | **Có, với thiết kế bổ sung phù hợp** |
| Seed có thể điều khiển trong test | Tùy implementation | Không nên gắn test security vào seed cố định |
| Chọn trong Java | `ThreadLocalRandom`, `Random`, `SplittableRandom` tùy bài toán | `SecureRandom` |

## 3. `ThreadLocalRandom`: lợi thế và giới hạn

### 3.1. Mục đích chính

`java.util.concurrent.ThreadLocalRandom` được đưa vào Java 7 và vẫn còn hiệu lực. Javadoc Java 17 mô tả nó là một bộ sinh ngẫu nhiên được **cô lập theo thread hiện tại**. Trong một chương trình nhiều threads, cách gọi điển hình:

```java
int slot = ThreadLocalRandom.current().nextInt(0, 8);
long delayMs = ThreadLocalRandom.current().nextLong(100, 500);
double sample = ThreadLocalRandom.current().nextDouble();
```

Đây là snippet trong method có import `java.util.concurrent.ThreadLocalRandom`; không có stdout cố định vì kết quả là ngẫu nhiên.

Các range ở trên là:
- `nextInt(0,8)`: nhận giá trị nguyên 0..7, **8 bị loại trừ**.
- `nextLong(100,500)`: 100..499, **500 bị loại trừ**.
- `nextDouble()`: thuộc [0,1).

Java API cũng cung cấp overloads `nextInt(bound)`, `nextLong(bound)`, `nextDouble(origin,bound)` và các lựa chọn tương ứng. Dùng đúng semantics **inclusive origin, exclusive bound**.

### 3.2. Vì sao `current()`?

`ThreadLocalRandom.current()` lấy generator của **thread đang chạy lời gọi**. Khi dùng `current().nextX(...)` ở ngay vị trí cần số ngẫu nhiên, các threads có thể sinh số mà không cùng tranh chấp một seed của `Random` được chia sẻ.

**Không truyền một instance `ThreadLocalRandom` lấy từ thread A sang thread B** rồi sử dụng trực tiếp. Javadoc nói các methods của instance phải được gọi bởi thread hiện tại; nên lấy `current()` tại chỗ sử dụng.

### 3.3. Không đặt seed thủ công

Theo Javadoc Java 17, phương thức:

```java
ThreadLocalRandom.current().setSeed(42L);
```

**luôn ném `UnsupportedOperationException`.** `ThreadLocalRandom` khởi tạo seed bằng cơ chế nội bộ, không hỗ trợ việc đặt seed của thread để chạy lại cùng chuỗi. Đây không phải lỗi của JDK, không phải dấu hiệu nên sử dụng reflection truy cập field private.

Nếu muốn test logic theo một chuỗi cố định, giải pháp hiện hành là **tách phần random source thành dependency** rồi dùng một generator/fake deterministic trong unit test, không “cưỡng ép seed” trên `ThreadLocalRandom`.

### 3.4. Không có bảo đảm mật mã

Oracle Java 17 nói rõ `ThreadLocalRandom` **không an toàn về mật mã**. Ngay cả khi cấu hình một system property liên quan đến seed bảo mật, **đừng nhầm seed của một PRNG thông thường với sự bảo đảm CSPRNG**. Giá trị do `ThreadLocalRandom` phát ra không được dùng làm bí mật.

## 4. `SecureRandom`: dành cho các giá trị phải khó đoán

`java.security.SecureRandom` là API Java cho bộ sinh ngẫu nhiên mạnh về mật mã.

Ví dụ tạo token:

```java
SecureRandom secure = new SecureRandom();
byte[] tokenBytes = new byte[32]; // 256 bits
secure.nextBytes(tokenBytes);

String token = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(tokenBytes);
```

Đây là snippet có import `java.security.SecureRandom` và `java.util.Base64`. Chuỗi Base64 URL-safe không padding của 32 bytes có **43 ký tự**, nhưng **không được in token vào log** trong hệ thống thật. Độ dài 32 bytes cung cấp **256 bit dữ liệu đầu vào ngẫu nhiên**; tính an toàn thực tế còn phụ thuộc entropy, hệ thống và protocol, không tự được quyết định chỉ bởi số bit.

### 4.1. OTP dạng sáu chữ số

```java
int codeNumber = secure.nextInt(1_000_000);
String sixDigits = String.format("%06d", codeNumber);
```

Có đúng 1.000.000 khả năng từ `000000` đến `999999`. Dùng `String.format("%06d", ...)` giữ các số 0 đầu. Mã sáu chữ số **không đủ mạnh để dùng như một bearer token dài hạn**: phải có thời hạn ngắn, giới hạn số lần nhập/rate limit, ràng buộc người dùng/giao dịch và chống replay.

### 4.2. Nonce, salt, IV không phải cùng một thứ

- **Session/reset token:** cần khó đoán, đủ entropy, lifecycle hạn chế và lưu/so sánh an toàn.
- **Salt của password hashing:** thường cần độc nhất/không lặp cho mỗi giá trị và không phải bí mật; vẫn thường được tạo ngẫu nhiên bằng nguồn an toàn, rồi lưu cùng hash.
- **Nonce/IV cho encryption:** yêu cầu **phụ thuộc thuật toán/mode**, đôi khi đòi **uniqueness** hơn là chỉ “khó đoán”. Ví dụ AES-GCM không được tái sử dụng cùng nonce với cùng key; phải tuân thủ đặc tả protocol và thư viện crypto chứ không chỉ gọi `nextBytes` rồi suy rằng mọi xác suất va chạm đã bị loại bỏ.
- **Signing keys / encryption keys:** dùng API tạo khóa của `KeyGenerator`/`KeyPairGenerator` với provider/algorithm đúng, không tự cắt số từ `ThreadLocalRandom`.

### 4.3. Provider/entropy và hiệu năng

`new SecureRandom()` chọn một implementation của provider được cấu hình theo runtime. `SecureRandom.getInstanceStrong()` chọn theo chính sách strong algorithms của nền tảng, nhưng **có thể chậm hoặc block hơn tùy nguồn entropy/provider**; không mặc định dùng nó cho mọi UI effect.

Hãy đánh giá cấu hình crypto/provider thực tế và nhu cầu độ trễ thay vì chọn theo tên method. Tránh tự đặt seed thấp entropy bằng hằng số, PID hoặc timestamp để “giúp bảo mật”; hãy để `SecureRandom` tự khởi tạo an toàn theo provider, trừ khi hệ thống có quy trình entropy chuyên biệt được thẩm định.

## 5. Ma trận chọn API đúng mục đích

| Nhu cầu thực tế | Lựa chọn thông dụng | Vì sao |
| --- | --- | --- |
| Demo xúc xắc không cược | `ThreadLocalRandom.current().nextInt(1,7)` | Nhanh, bounded, không bí mật |
| Chọn thứ tự xử lý task nội bộ | `ThreadLocalRandom` | Tránh contention giữa workers |
| Jitter cho retry và backoff | `ThreadLocalRandom` | Thường chỉ cần random hóa để tránh đồng bộ tải |
| Sample dữ liệu không nhạy cảm | `ThreadLocalRandom`/`RandomGenerator` | Cần phân bố và performance |
| Mô phỏng có khả năng tái lập | `Random(seed)` hoặc generator định seed được | Chủ động tái chạy cùng case |
| Random generator tách thành dependency | `RandomGenerator` (Java 17+) | Testability, thuật toán có thể đổi |
| Session/access token | `SecureRandom` | Phải chống dự đoán |
| Reset password / account verification secret | `SecureRandom` | Kẻ tấn công có động cơ đoán token |
| OTP sáu chữ số | `SecureRandom` + rate limiting/TTL | CSPRNG nhưng không làm OTP đủ mạnh một mình |
| Nonce cho encryption | Crypto API + quy tắc nonce của mode | **Tính uniqueness và scope key** rất quan trọng |
| Khóa đối xứng/bất đối xứng | `KeyGenerator`/`KeyPairGenerator` | Dùng API thiết kế cho thuật toán |
| Random từ user input không tin cậy | Validate input trước | Đầu ra random không thay validation |

**Không có API ngẫu nhiên duy nhất tốt nhất cho mọi bài toán.** Bắt đầu từ threat model và tính đúng nghiệp vụ, sau đó mới xét performance.

## 6. Vì sao `Random`, `Math.random` và `SplittableRandom` không thay `SecureRandom`?

`Random` có thể được khởi tạo bằng seed để tạo dãy xác định; Java SE 17 ghi rõ nó không an toàn về mật mã. `Math.random()` cũng dùng generator thông thường, phù hợp cho nhu cầu không bảo mật. `SplittableRandom` hữu ích khi muốn chia các nguồn random riêng cho xử lý song song/mô phỏng; cũng **không** tự trở thành CSPRNG.

`java.util.random.RandomGenerator` là **giao diện** được thêm trong Java 17 để thống nhất API nhiều thuật toán. **Chỉ vì một object implements `RandomGenerator` không có nghĩa đó là CSPRNG**. Nguồn được truyền vào phải được chọn theo yêu cầu: deterministic seedable generator cho test/mô phỏng; `SecureRandom` hoặc crypto API phù hợp khi bảo mật.

### 6.1. Một mẫu anti-pattern

```java
// SAI cho token đặt lại mật khẩu:
long resetToken = ThreadLocalRandom.current().nextLong();
```

Một số `long` rộng 64 bit và trông ngẫu nhiên vẫn không thể thay cho một CSPRNG được thiết kế cho threat model. Không nên dựa vào việc “người ngoài không biết seed” như bằng chứng bảo mật.

### 6.2. UUID có giải quyết tất cả không?

`UUID.randomUUID()` là cách tạo UUID v4 ngẫu nhiên và trong Java SE 17 dùng một nguồn ngẫu nhiên mạnh về mật mã theo mô tả API; tuy nhiên **UUID còn là identifier với định dạng và số bit không hoàn toàn dành cho secrets**. Chọn token có entropy, định dạng, scope và lifecycle theo yêu cầu bảo mật thay vì dùng “UUID” như một nhãn bảo đảm. Tránh tiết lộ cấu trúc/ID dùng để phân quyền: một ID có dạng ngẫu nhiên không thay authorization checks.

## 7. Bounded random đúng cách

### 7.1. Không dùng modulo tùy ý cho bảo mật

Cách dễ sai:

```java
int value = Math.abs(random.nextInt()) % 6;
```

Đây là **phản ví dụ**. `Math.abs(Integer.MIN_VALUE)` vẫn âm, và phép modulo có thể tạo phân bố không đều khi range không chia hết kích thước không gian đầu ra. Trong crypto, modulo bias có thể làm giảm security margin hoặc tạo thông tin có ích cho tấn công.

Hãy dùng API bounded có sẵn:

```java
int dice = ThreadLocalRandom.current().nextInt(1, 7);
int otp = new SecureRandom().nextInt(1_000_000);
```

Trong service thật có thể tái sử dụng `SecureRandom` được quản lý phù hợp thay vì tạo object mới trên mỗi request nếu provider và concurrency design cho phép.

### 7.2. Bound là exclusive

Đối với `nextInt(origin, bound)`:
- `origin` **được bao gồm**.
- `bound` **không được bao gồm**.
- `origin >= bound` là input không hợp lệ và có thể ném `IllegalArgumentException`.
- `nextInt(bound)` yêu cầu `bound > 0`.

Test contract kiểm tra dải, không khẳng định một output ngẫu nhiên cụ thể.

### 7.3. Tránh phép toán overflows

Tự viết `int range = max - min + 1` có thể overflow nếu min/max rất rộng. Dùng API overloads của JDK cho origin/bound và validate input; nếu range không hợp lệ, fail rõ chứ không dùng modulo trên giá trị âm.

## 8. Ví dụ Java 17+ biên dịch và chạy: thông thường và bảo mật

Chương trình dưới đây **không in token, salt hoặc OTP thật**. Thay vào đó nó in các đặc điểm có thể kiểm tra ổn định: giá trị trong giới hạn, số lượng mẫu, việc `setSeed` không được hỗ trợ, độ dài token, và định dạng OTP.

Lưu toàn bộ file **`RandomPurposeDemo.java`**:

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RandomPurposeDemo {
    static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
    }

    static void ordinaryRandom() throws Exception {
        int bounded = ThreadLocalRandom.current().nextInt(10, 20);
        check(bounded >= 10 && bounded < 20, "exclusive bound");
        System.out.println("ordinary.boundValid=true");
        AtomicBoolean good = new AtomicBoolean(true);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            Future<?>[] results = new Future<?>[4];
            for (int i = 0; i < results.length; i++) {
                results[i] = pool.submit(() -> {
                    for (int j = 0; j < 1_000; j++) {
                        int dice = ThreadLocalRandom.current().nextInt(1, 7);
                        if (dice < 1 || dice > 6) good.set(false);
                    }
                });
            }
            for (Future<?> result : results) result.get(5, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS), "pool shutdown");
        }
        check(good.get(), "invalid sample");
        System.out.println("ordinary.parallelSamples=4000");
        System.out.println("ordinary.parallelBoundsValid=true");

        boolean unsupported = false;
        try {
            ThreadLocalRandom.current().setSeed(42L);
        } catch (UnsupportedOperationException expected) {
            unsupported = true;
        }
        check(unsupported, "setSeed should be unsupported");
        System.out.println("ordinary.setSeedUnsupported=true");
    }

    static void securityRandom() {
        SecureRandom secure = new SecureRandom();
        byte[] bytes = new byte[32];
        secure.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
        check(bytes.length == 32, "token bytes");
        check(token.matches("[A-Za-z0-9_-]{43}"), "token encoding");
        System.out.println("security.tokenBytes=32");
        System.out.println("security.tokenUrlSafeLength=43");

        int otp = secure.nextInt(1_000_000);
        String sixDigits = String.format("%06d", otp);
        check(sixDigits.matches("[0-9]{6}"), "otp digits");
        System.out.println("security.otpSixDigits=true");

        byte[] salt = new byte[16];
        secure.nextBytes(salt);
        check(salt.length == 16, "salt length");
        System.out.println("security.saltBytes=16");
    }

    public static void main(String[] args) throws Exception {
        ordinaryRandom();
        securityRandom();
        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 RandomPurposeDemo.java
java RandomPurposeDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
ordinary.boundValid=true
ordinary.parallelSamples=4000
ordinary.parallelBoundsValid=true
ordinary.setSeedUnsupported=true
security.tokenBytes=32
security.tokenUrlSafeLength=43
security.otpSixDigits=true
security.saltBytes=16
checks=PASS
```

### 8.1. Đọc đúng ý nghĩa kết quả

- `ordinary.boundValid=true`: một giá trị có random origin 10, bound 20 thỏa `10 <= x < 20`.
- `ordinary.parallelSamples=4000`: bốn workers mỗi worker tạo 1.000 giá trị; `Future.get` bảo đảm main chờ từng worker hoàn tất hoặc báo exception.
- `ordinary.parallelBoundsValid=true`: tất cả giá trị trong range 1..6 theo contract; **không chứng minh chúng khó dự đoán**.
- `ordinary.setSeedUnsupported=true`: `ThreadLocalRandom.current().setSeed(42)` ném `UnsupportedOperationException` như Javadoc.
- `security.tokenBytes=32`: buffer CSPRNG được điền với 32 bytes, còn token string Base64URL có 43 ký tự; actual bytes/token thay đổi theo lần chạy.
- `security.otpSixDigits=true`: mã có đúng sáu chữ số, kể cả zero đầu; **không in OTP thật**.
- `security.saltBytes=16`: buffer salt 16 bytes được tạo; không thể suy từ đó rằng protocol hash password bất kỳ đã an toàn.
- `checks=PASS`: chương trình kiểm tra các contracts được nêu; **không phải chứng nhận security audit**.

### 8.2. Vì sao không assert giá trị random cố định?

`ThreadLocalRandom` không cho set seed và `SecureRandom` cũng không nên có test dựa vào một chuỗi bí mật cố định. Unit test nên kiểm tra **range, length, format, exception behavior, thread-safety contract và logic tiêu thụ random**, không yêu cầu `nextInt` trả đúng con số cụ thể.

Nếu logic cần deterministic branch coverage, **inject một random source có thể điều khiển trong test**. Đây là vấn đề testability riêng; tránh cố hack seed nội bộ của `ThreadLocalRandom`.

## 9. Tách nguồn random khỏi logic nghiệp vụ

### 9.1. Wrapper dùng cho mục đích thông thường

```java
import java.util.function.IntUnaryOperator;
import java.util.concurrent.ThreadLocalRandom;

public final class SimpleChooser {
    static int pickIndex(int size, IntUnaryOperator nextBoundedInt) {
        if (size <= 0) throw new IllegalArgumentException("empty");
        return nextBoundedInt.applyAsInt(size);
    }

    public static int pickProduction(int size) {
        return pickIndex(
                size, bound -> ThreadLocalRandom.current().nextInt(bound));
    }
}
```

Đây là class ví dụ độc lập nhưng không có `main`, nên không có stdout cố định. Khi unit test, truyền stub `bound -> 0` hoặc `bound -> bound - 1` để kiểm tra first/last branch **mà không điều khiển seed**. Trong production phải tin nguồn đáp ứng contract hoặc validate kết quả khi nhận dependency không tin cậy.

Đối với Java 17+, `RandomGenerator` có thể là abstraction giàu API hơn `IntUnaryOperator`. Dùng factory/supplier phù hợp để không chia sẻ sai đối tượng `ThreadLocalRandom` giữa threads.

### 9.2. Đối với security, không tùy tiện inject PRNG yếu

Nếu tạo access token, type signatures nên thể hiện rõ dependency `SecureRandom` hoặc một **crypto random abstraction có yêu cầu security**. Một interface chung cho phép truyền `new Random(1)` vào quá trình tạo reset token sẽ làm hệ thống dễ bị cấu hình sai.

Có thể mock/test một crypto-random boundary ở tầng unit, nhưng **production wiring phải bắt buộc nguồn CSPRNG**. Test security quan trọng nên chạy qua `SecureRandom` thật và đánh giá policy/protocol, không chỉ qua deterministic fake.

## 10. Những hiểu nhầm cần loại bỏ

| Hiểu nhầm | Thực tế |
| --- | --- |
| “`ThreadLocalRandom` có chữ ThreadLocal nên output khó đoán hơn về mật mã.” | Nó hướng đến hiệu quả khi chạy đa luồng, **không phải CSPRNG** |
| “Seed được tạo tự động nên an toàn cho password reset.” | Seed khác crypto unpredictability; không dùng làm token |
| “`setSeed` giúp unit test ThreadLocalRandom.” | Javadoc nêu `UnsupportedOperationException` |
| “Cứ tạo `Random(System.nanoTime())` sẽ bảo mật.” | Timestamp không tạo CSPRNG |
| “`Math.random()` đủ tốt vì output nhìn ngẫu nhiên.” | Không bảo đảm chống dự đoán |
| “`SplittableRandom` là crypto vì có splittable.” | Không phải API sinh bí mật |
| “`RandomGenerator` tên chung nghĩa an toàn cho mọi use case.” | Interface không bảo đảm tính mật mã |
| “`SecureRandom` bảo đảm token không bao giờ va chạm.” | Va chạm vẫn có xác suất, cần xử lý uniqueness nếu protocol đòi |
| “`SecureRandom.getInstanceStrong` luôn nhanh hơn hoặc tốt hơn cho mọi app.” | Phụ thuộc provider, entropy, latency và policy |
| “Token 6 chữ số đủ mạnh nếu sinh bằng SecureRandom.” | Không; cần rate limiting, TTL, binding và chống replay |
| “Một UUID random thay thế được authorization.” | ID format không tự cấp quyền |
| “Dùng modulo sau `nextInt` luôn công bằng.” | Có thể modulo bias và lỗi `Integer.MIN_VALUE` |
| “Nếu test chi-square pass thì bảo mật đã đạt.” | Test phân bố không chứng minh unpredictability |
| “In token để debug có sao đâu?” | Log token có thể tiết lộ quyền truy cập |
| “Một seed cố định giúp tính random trở nên thật sự ngẫu nhiên.” | Seed cố định tạo tính tái lập, không phải security |

## 11. Câu hỏi thường gặp

**1. Khi nào dùng `ThreadLocalRandom.current()`?**  
Khi mỗi worker trong chương trình đa luồng cần random thông thường, không phải bí mật.

**2. Khi nào buộc dùng `SecureRandom`?**  
Khi đối thủ có thể lợi dụng việc đoán giá trị: session/reset/access token, OTP, secret nonce/IV theo protocol hoặc các bí mật tương đương.

**3. Nếu chỉ random hóa UI hoặc tần suất retry thì sao?**  
`ThreadLocalRandom` thường phù hợp; không cần tạo token mật mã cho jitter thông thường.

**4. `ThreadLocalRandom` có cho gọi `setSeed` không?**  
Không; method ném `UnsupportedOperationException`.

**5. Có thể kiểm thử kết quả ngẫu nhiên thông thường bằng exact expected values không?**  
Không nên với `ThreadLocalRandom`. Tách nguồn random khỏi logic và inject deterministic source vào unit test.

**6. Ngẫu nhiên có phân bố tốt thì có an toàn mật mã không?**  
Không. Phân bố chỉ là một phần của yêu cầu, không bảo đảm khó dự đoán khi có đối thủ.

**7. `SecureRandom` có tạo token độc nhất tuyệt đối không?**  
Không. Nếu cần uniqueness mạnh, thêm kiểm tra tồn tại/giao thức uniqueness ở hệ thống sử dụng.

**8. Token được Base64URL hóa có tăng entropy không?**  
Không. Encoding chỉ đổi cách biểu diễn, không tự tăng entropy của bytes đầu vào.

**9. Vì sao OTP sáu chữ số không thể là session token dài hạn?**  
Chỉ có một triệu khả năng; phải giới hạn đoán, có TTL và bind đúng ngữ cảnh.

**10. Có dùng `SecureRandom.nextInt(bound)` được không?**  
Có. Khi cần một số bí mật trong range, dùng bounded API thay vì modulo tự chế.

**11. Có nên log actual reset token để điều tra không?**  
Không. Ghi id/correlation metadata phù hợp; bảo vệ secrets khỏi logs.

**12. Một seed “cryptographic” của ThreadLocalRandom có làm class thành CSPRNG?**  
Không. Javadoc vẫn nói instance không an toàn về mật mã.

**13. Có thể dùng `Random` với fixed seed để chạy mô phỏng?**  
Có, khi tính tái lập là yêu cầu và không có threat model bí mật.

**14. `SecureRandom` có thay thế được kiểm tra quyền truy cập không?**  
Không. Secrets chỉ là một phần của authentication/authorization protocol.

**15. Gọi `current()` trước ở main rồi chia cho threads khác có đúng không?**  
Không phải mẫu nên dùng. Gọi `ThreadLocalRandom.current()` từ chính thread cần random.

## 12. Checklist lựa chọn trong dự án

- [ ] Xác định ai có thể quan sát output và hậu quả nếu dự đoán được.
- [ ] Với dữ liệu không nhạy cảm, xem `ThreadLocalRandom` và random generator phù hợp.
- [ ] Với secret/security-sensitive, chọn `SecureRandom` hoặc crypto API tương ứng.
- [ ] Không dùng `Math.random`, `Random`, `SplittableRandom` làm reset/session token.
- [ ] Không thử `setSeed` trên `ThreadLocalRandom` để ép tính tái lập.
- [ ] Không chia sẻ instance `ThreadLocalRandom` giữa threads; gọi `current` tại nơi dùng.
- [ ] Xác nhận origin inclusive, bound exclusive.
- [ ] Không dùng `Math.abs(nextInt()) % n` cho random bounded.
- [ ] Không nhầm `SecureRandom` với guarantee chống duplicate tuyệt đối.
- [ ] Nếu tạo OTP, có TTL, rate limit và replay protection.
- [ ] Nếu tạo nonce/IV, tuân thủ uniqueness/size theo algorithm và key.
- [ ] Không ghi giá trị token/OTP thực vào stdout, metrics hoặc logs.
- [ ] Đánh giá entropy/provider/config của hệ thống deploy.
- [ ] Tách nguồn random để test logic, không hard-code chuỗi ThreadLocalRandom.
- [ ] Không biến một test distribution thành bằng chứng security.
- [ ] Giữ error handling và processing của values riêng khỏi nguồn random.
- [ ] Java 17+ examples được biên dịch và kiểm tra bằng `javac/java`.

## 13. Kết luận và tài liệu chính thức

**`ThreadLocalRandom` giải quyết nhu cầu random hiệu quả cho ứng dụng đa luồng, không giải quyết nhu cầu tạo bí mật.** Khi sự an toàn phụ thuộc vào việc người ngoài không thể đoán output, dùng **`SecureRandom`** và quản lý đầy đủ entropy, độ dài, thời hạn, giới hạn đoán, reuse/uniqueness và logs theo đúng protocol.

Đừng lấy các đặc điểm **đẹp về phân bố**, **không trùng trong một lần chạy**, **thread-local**, **seed tự động** hay **tên API có chữ random** làm chứng chỉ an toàn mật mã. Mục tiêu bảo vệ và threat model quyết định phương thức sinh ngẫu nhiên.

Tài liệu chính thức Java SE 17:

- [`ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `current()`, `setSeed` luôn bị từ chối, bounded APIs và cảnh báo không an toàn mật mã.
- [`SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographically strong random number generator, `nextBytes`, provider và seeding.
- [`Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): PRNG thông thường và khả năng dùng seed để test.
- [`RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface random mới trong Java 17.
- [`SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): nguồn PRNG dùng cho mô phỏng/parallel split.
- [`UUID`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): random v4 UUID và các giới hạn khi dùng identifiers.
- [`Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): URL-safe/no-padding encoding.
