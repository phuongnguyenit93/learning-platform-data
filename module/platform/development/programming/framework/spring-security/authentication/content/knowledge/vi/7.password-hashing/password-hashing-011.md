# Đo chi phí xác minh, giới hạn đầu vào và phòng ngừa cạn tài nguyên

> **Phạm vi:** Spring Security Authentication — **Băm mật khẩu**. Bài này giải thích cách đo chi phí `PasswordEncoder.matches(...)`, chọn work factor của BCrypt/Argon2id theo năng lực thật, kiểm soát kích thước và tính hợp lệ của password, ngăn CPU/RAM/thread pool bị cạn bởi nhiều phép xác minh đồng thời, và thiết kế benchmark, rate limiting, admission control cùng kiểm thử. Ví dụ Java 17+ sử dụng Spring Security Crypto **6.5.11**, chạy bằng Gradle. Các số thời gian trong ví dụ **được đo tại runtime**, không được bịa hoặc xem là hằng số áp dụng mọi máy.

## 1. Tại sao xác minh mật khẩu có thể làm nghẽn hệ thống?

Một password-hashing function như **bcrypt, Argon2id, scrypt hoặc PBKDF2** cố ý tiêu tốn tài nguyên. Mục đích là làm việc thử đoán password hàng loạt trên dữ liệu hash bị rò rỉ trở nên tốn kém. Tuy nhiên người dùng hợp lệ và attacker đều có thể tạo request yêu cầu backend xác minh password.

```text
POST /login
   |
   v
Gateway / HTTP server
   |  request-size limit + network rate limit
   v
Authentication endpoint
   |  input validation + per-account quota + admission control
   v
UserDetailsService / credential store
   |  lấy hash và trạng thái account
   v
PasswordEncoder.matches(rawPassword, storedHash)
   |  CPU time và/hoặc RAM tùy thuật toán
   v
Authentication success / failure / overload response
```

Một endpoint login không có cơ chế hạn chế có thể nhận hàng trăm hoặc hàng nghìn yêu cầu sai password. **Mật khẩu sai vẫn có thể khiến server chạy hash đắt đỏ.** Khi CPU bận, các request hợp lệ xếp hàng, p95/p99 latency tăng và có thể timeout. Với thuật toán memory-hard, nhiều phép hash song song còn có nguy cơ vượt giới hạn RAM.

Ba câu hỏi độc lập:

1. **Chi phí một lần verify là bao nhiêu?** Đo `matches(...)` và toàn bộ luồng authentication trên phần cứng thật.
2. **Input nào được phép đi vào verify?** Validate kích thước request, password length/UTF-8 bytes, malformed Unicode và định dạng hash; không biến một chuỗi khổng lồ thành tác vụ tốn CPU/RAM.
3. **Bao nhiêu yêu cầu được phép thực hiện đồng thời hoặc theo thời gian?** Kết hợp rate limiting theo account/nguồn, concurrency cap, queue bounded, timeout, MFA/risk signal và điều phối admission.

**Không giải quyết được bằng cách duy nhất tăng BCrypt cost.** Cost cao hơn làm tấn công offline đắt hơn nhưng đồng thời làm server chậm hơn trước lưu lượng login. Ngược lại, giảm cost để chống quá tải thường làm suy yếu khả năng chống đoán mật khẩu offline.

## 2. Đo đúng bước trong Spring Security

Trong flow form login hoặc HTTP Basic, luồng phổ biến:

```text
Authentication filter
  -> UsernamePasswordAuthenticationToken (chưa xác thực)
  -> AuthenticationManager / ProviderManager
  -> DaoAuthenticationProvider
      |-> UserDetailsService.loadUserByUsername(username)
      |      -> password hash, status, GrantedAuthority
      |-> PasswordEncoder.matches(rawPassword, storedHash)
  -> Authentication thành công hoặc AuthenticationException
```

Phân biệt:

| Thao tác | Khi nào dùng | Điều cần đo |
| --- | --- | --- |
| `encode(raw)` | Đăng ký, reset/đổi password, rehash sau verify | Thời gian tạo password hash, salt và tài nguyên |
| **`matches(raw, encodedHash)`** | Login, xác minh lại password | **Chi phí xác minh**; dùng hash **đã tạo trước vùng đo** |
| `loadUserByUsername(...)` | Provider tải user | DB latency, connection pool, truy vấn quyền/nhóm |
| Authentication end-to-end | Filter → manager → provider → response | p50/p95/p99 HTTP, queue wait, error rate, CPU/RAM |

Không chạy `encode` và `matches` trong cùng đoạn đo rồi gọi kết quả là “verify time”: `encode` tạo một password hash mới, thường với salt mới. `matches` sử dụng hash đã lưu.

```java
// Snippet benchmark; encoder, raw, storedHash và samples đã được tạo.
for (int i = 0; i < samples; i++) {
    long started = System.nanoTime();
    boolean ok = encoder.matches(raw, storedHash);
    long elapsedNanos = System.nanoTime() - started;
    if (!ok) {
        throw new IllegalStateException("Test password must match");
    }
    durations[i] = elapsedNanos;
}
```

`System.nanoTime()` dùng đo elapsed time tốt hơn `System.currentTimeMillis()`. Không in console, ghi log SQL, tạo `SecureRandom` hoặc gọi mạng trong mỗi vòng đo vì sẽ làm nhiễu kết quả.

### Work factor ở đâu?

Với BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
String storedHash = encoder.encode("demo-secret");
boolean ok = encoder.matches("demo-secret", storedHash);
```

Đây là snippet cần imports và method/class bao quanh; không phải chương trình chạy độc lập. BCrypt hash trực tiếp thường dài 60 ký tự, chứa version, salt và **cost**:

```text
$2a$12$...phần salt và kết quả hash...
    ^^
    cost được lưu trong hash
```

- `new BCryptPasswordEncoder()` mặc định dùng cost **10** ở nhánh Spring Security 6.5.
- Cost tăng từ 10 lên 11 thường khiến lượng công việc thuật toán gần gấp đôi; **milliseconds thực tế** chịu ảnh hưởng phần cứng và tải đồng thời.
- Đổi bean sang cost 12 không tự biến mọi hash cũ cost 10 trong DB thành hash cost 12. `matches` kiểm tra theo tham số của **stored hash**.
- `upgradeEncoding(storedHash)` có thể báo hash nên được nâng cấp; không tự thay đổi DB. Chỉ rehash từ **raw password đã xác minh đúng**, không hash lại chính chuỗi hash.
- Với `DelegatingPasswordEncoder`, tiền tố như `{bcrypt}` chọn thuật toán; có thể phải đo riêng bcrypt cost 10/12 và Argon2id đang tồn tại trong cùng DB.

### BCrypt và Argon2id không tiêu hao tài nguyên giống nhau

| Thuật toán | Khả năng tiêu hao nổi bật | Tham số phải benchmark |
| --- | --- | --- |
| BCrypt | Chủ yếu CPU | cost/strength, request concurrency |
| Argon2id | CPU và bộ nhớ | memory cost, iterations, parallelism, số hash đồng thời |
| scrypt | CPU và bộ nhớ | N, r, p, native/heap memory |
| PBKDF2 | Chủ yếu CPU | iterations, PRF, giới hạn input |

Argon2id được OWASP ưu tiên cho hệ thống mới, nhưng **tăng memory cost đồng thời tăng số tác vụ** có thể làm OOM trước khi CPU đạt 100%. Đừng chỉ xem thời gian một phép verify rồi bỏ qua lượng RAM cho các phép đang chạy.

## 3. Đo percentile, throughput và thời gian chờ

Một lần gọi `matches` nhanh hay chậm không đủ cho kết luận về capacity:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `p50` | 50% số verify kết thúc không chậm hơn giá trị này |
| `p95` | 95% số verify kết thúc không chậm hơn giá trị này |
| `p99` | Đuôi 1% request chậm nhất; đặc biệt quan trọng khi quá tải |
| `verify/sec` | Số phép hash server xử lý ổn định mỗi giây |
| `in-flight` | Số phép hash hiện đang chạy |
| `queue-wait` | Thời gian chờ được cấp tài nguyên trước khi hash |
| CPU và CPU throttling | Có vượt core quota hoặc bị container giới hạn CPU? |
| Heap/native RAM, GC | Có áp lực nhớ từ Argon2/scrypt, parser, queue? |
| Error/rejection | Bad password, invalid input, rate limited và overload được tách rõ? |
| HTTP login p95/p99 | Thời gian người dùng chờ từ lúc gửi đến khi có response |

Cần **tách thời gian verify khỏi thời gian request**:

```text
T_login ≈ T_queue + T_request_processing
T_request_processing gồm:
    parse/validate request
    load user từ DB/cache
    PasswordEncoder.matches
    status/authorization-related checks
    response/security handling
```

Nhiều nguyên nhân như CPU contention, GC, connection pool và network làm các thành phần biến đổi nên không suy ra thời gian bcrypt bằng phép trừ bừa. Hãy instrument riêng từng chặng.

Một benchmark tin cậy phải có warmup JVM, nhiều samples, các cost khác nhau, giới hạn tải và mô tả phần cứng/JVM. Với JMH, có thể so sánh microbenchmark; sau đó cần **load test HTTP trên staging** để kiểm tra hệ thống thật. Không lấy p99 từ 10 mẫu và kết luận đáp ứng SLO sản phẩm.

## 4. Kiểm tra password trước khi hash: giới hạn byte và kích thước request

### 4.1. Giới hạn 72 **byte UTF-8** của BCrypt

BCrypt truyền thống có giới hạn đầu vào phổ biến **72 byte**. Đây không phải 72 ký tự Unicode, cũng không phải `String.length() == 72` của Java.

| Password test | `String.length()` | UTF-8 bytes | So với giới hạn 72 byte |
| --- | ---: | ---: | --- |
| `"A".repeat(72)` | 72 | 72 | Vừa ngưỡng |
| `"A".repeat(73)` | 73 | 73 | Vượt |
| `"界".repeat(24)` | 24 | 72 | Vừa ngưỡng |
| `"界".repeat(25)` | 25 | 75 | Vượt |
| `"😀".repeat(18)` | 36 | 72 | Vừa ngưỡng |
| `"😀".repeat(19)` | 38 | 76 | Vượt |
| `"é"` dạng dựng sẵn | 1 | 2 | Khác dạng Unicode ghép dấu |
| `"e\u0301"` dạng ghép dấu | 2 | 3 | Khác bytes nếu không có normalization policy |

`String.length()` đếm **UTF-16 code units**. Emoji có thể chiếm hai code units và bốn UTF-8 bytes. Code points cũng không nhất thiết tương đương ký tự người dùng nhìn thấy, nhất là chuỗi dấu kết hợp/emoji nối nhiều code points.

OWASP khuyến nghị giới hạn password dành cho bcrypt ở **72 byte hoặc thấp hơn nếu implementation có giới hạn chặt hơn**. Một số phiên bản cũ có rủi ro xử lý phần đuôi sau giới hạn; Spring Security đã có advisory **CVE-2025-22228** liên quan việc kiểm tra đầu vào quá dài. Hãy dùng phiên bản đã vá và **từ chối** password vượt giới hạn, không tự cắt.

**Không làm**:

```java
// Anti-pattern: thay đổi bí mật người dùng, lại đếm ký tự thay vì bytes.
String shortened = rawPassword.substring(
        0, Math.min(rawPassword.length(), 72));
```

Điều này có thể làm hai password vốn khác nhau thành cùng một tiền tố. Không trim, lowercase, bỏ dấu hoặc normalize password một cách âm thầm: việc đăng ký và đăng nhập phải dùng cùng phép biến đổi đã được quy định rõ, và không được phá các hash đã lưu.

### 4.2. Kiểm tra ở nhiều lớp

```text
Client / API caller
    |
    v
Proxy + web server:
  request-body cap; header cap; timeout; rate limit
    |
    v
Request binding/validation:
  null, rỗng, max UTF-8 bytes, Unicode hợp lệ, password policy
    |
    v
Authentication admission:
  per-account/per-IP quota; số phép hash đồng thời
    |
    v
PasswordEncoder.matches(...)
```

Frontend `maxlength` hỗ trợ UX nhưng **không phải security control**. Bean Validation `@Size(max=72)` thường đếm ký tự, không đảm bảo giới hạn byte. Backend phải kiểm tra trước khi gọi thuật toán đắt đỏ, và áp dụng thống nhất cho **đăng ký, login, đổi password, khôi phục password, admin-set-password**.

Chặn body cực lớn ở gateway hoặc container **trước** khi parser cấp phát chuỗi. Một password hàng chục MB có thể làm cạn memory trong HTTP/JSON parsing hoặc kiểm tra regex ngay cả khi encoder cuối cùng từ chối.

Tránh regex có **catastrophic backtracking** khi kiểm tra password policy. Nếu password-strength service ngoài bị chậm, cần timeout/circuit breaker; không giữ thread đăng nhập vô hạn.

### 4.3. Không dùng một chính sách chung sai cho nhiều thuật toán

Nếu sản phẩm lưu cả BCrypt và Argon2id trong `DelegatingPasswordEncoder`, một password dài >72 byte có thể hợp lệ với thuật toán mới nhưng không hợp lệ với bcrypt. Chính sách cần xét **thuật toán của hash đang verify** và **thuật toán dùng tạo hash mới**, có kế hoạch migration và UX rõ. Không dùng một wrapper 72-byte phủ tất cả encoder chỉ vì hệ thống trước kia dùng bcrypt.

## 5. Ví dụ Java 17+ chạy được: đo BCrypt và hạn chế verify

Ví dụ độc lập dùng `spring-security-crypto:6.5.11`, không cần Spring Boot web server. Nó:

1. Kiểm tra password theo byte UTF-8 và từ chối malformed UTF-16.
2. Tạo BCrypt hash **ngoài** vòng đo `matches`, thực hiện warmup rồi ghi p50/p95 cho cost 10 và 11.
3. Mô phỏng `Semaphore` giới hạn số phép xác minh đồng thời: khi slot đang bị chiếm, trả **BUSY** chứ không coi mật khẩu là sai.

### 5.1. File project

```text
password-verification-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/PasswordVerificationDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'password-verification-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PasswordVerificationDemo'
}
```

### 5.2. Chương trình hoàn chỉnh

Tạo `src/main/java/demo/PasswordVerificationDemo.java`:

```java
package demo;

import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.Semaphore;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordVerificationDemo {
    private static final int MAX_BCRYPT_BYTES = 72;

    public static void main(String[] args) throws InterruptedException {
        String raw = "demo-passphrase-123";
        PasswordEncoder cost10 = new BCryptPasswordEncoder(10);
        String storedHash = cost10.encode(raw);

        System.out.println("match-good="
                + cost10.matches(raw, storedHash));
        System.out.println("match-wrong="
                + cost10.matches("wrong-password", storedHash));
        System.out.println("ascii72-valid="
                + bcryptInputValid("A".repeat(72)));
        System.out.println("ascii73-valid="
                + bcryptInputValid("A".repeat(73)));
        System.out.println("unicode24-valid="
                + bcryptInputValid("界".repeat(24)));
        System.out.println("unicode25-valid="
                + bcryptInputValid("界".repeat(25)));
        System.out.println("emoji18-valid="
                + bcryptInputValid("😀".repeat(18)));
        System.out.println("emoji19-valid="
                + bcryptInputValid("😀".repeat(19)));

        String invalidUtf16 = String.valueOf((char) 0xD800);
        System.out.println("invalid-unicode-valid="
                + bcryptInputValid(invalidUtf16));

        Semaphore slots = new Semaphore(1);
        GatedVerifier gated = new GatedVerifier(cost10, slots);
        slots.acquire();
        try {
            System.out.println("when-busy="
                    + gated.verify(raw, storedHash));
        } finally {
            slots.release();
        }
        System.out.println("after-release="
                + gated.verify(raw, storedHash));

        for (int cost : new int[] {10, 11}) {
            PasswordEncoder encoder = new BCryptPasswordEncoder(cost);
            Measurement result = measure(encoder, raw, 3, 12);
            System.out.printf(Locale.ROOT,
                    "cost=%d samples=%d p50-ms=%.2f p95-ms=%.2f%n",
                    cost, result.samples(),
                    result.p50Millis(), result.p95Millis());
        }
    }

    private static boolean bcryptInputValid(String input) {
        if (input == null || input.isEmpty()
                || input.length() > MAX_BCRYPT_BYTES) {
            return false;
        }

        try {
            int bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(input))
                    .remaining();

            return bytes <= MAX_BCRYPT_BYTES;
        } catch (CharacterCodingException invalidInput) {
            return false;
        }
    }

    private static Measurement measure(
            PasswordEncoder encoder, String raw,
            int warmup, int iterations) {
        if (!bcryptInputValid(raw) || iterations <= 0) {
            throw new IllegalArgumentException("Invalid benchmark setup");
        }

        String storedHash = encoder.encode(raw); // NGOÀI vùng đo

        for (int i = 0; i < warmup; i++) {
            if (!encoder.matches(raw, storedHash)) {
                throw new IllegalStateException("Warmup failed");
            }
        }

        long[] measurements = new long[iterations];
        for (int i = 0; i < iterations; i++) {
            long start = System.nanoTime();
            boolean ok = encoder.matches(raw, storedHash);
            measurements[i] = System.nanoTime() - start;
            if (!ok) {
                throw new IllegalStateException("Verification failed");
            }
        }

        Arrays.sort(measurements);
        return new Measurement(
                iterations,
                percentileMs(measurements, 0.50),
                percentileMs(measurements, 0.95));
    }

    private static double percentileMs(long[] sortedNanos, double p) {
        int index = Math.max(0, Math.min(sortedNanos.length - 1,
                (int) Math.ceil(p * sortedNanos.length) - 1));
        return sortedNanos[index] / 1_000_000.0;
    }

    private record Measurement(
            int samples, double p50Millis, double p95Millis) {}

    private enum Outcome {
        MATCH, MISMATCH, BUSY, INVALID_INPUT
    }

    private static final class GatedVerifier {
        private final PasswordEncoder encoder;
        private final Semaphore permits;

        GatedVerifier(PasswordEncoder encoder, Semaphore permits) {
            this.encoder = encoder;
            this.permits = permits;
        }

        Outcome verify(String raw, String storedHash) {
            if (!bcryptInputValid(raw)) {
                return Outcome.INVALID_INPUT;
            }
            if (!permits.tryAcquire()) {
                return Outcome.BUSY;
            }

            try {
                return encoder.matches(raw, storedHash)
                        ? Outcome.MATCH
                        : Outcome.MISMATCH;
            } finally {
                permits.release();
            }
        }
    }
}
```

Chạy trong thư mục project bằng Gradle và JDK 17+:

```bash
gradle run
```

Với Gradle Wrapper, sử dụng `./gradlew run` trên macOS/Linux hoặc `gradlew.bat run` trên Windows.

### 5.3. Output có thể kiểm chứng

Các dòng cố định của chương trình:

```text
match-good=true
match-wrong=false
ascii72-valid=true
ascii73-valid=false
unicode24-valid=true
unicode25-valid=false
emoji18-valid=true
emoji19-valid=false
invalid-unicode-valid=false
when-busy=BUSY
after-release=MATCH
```

Sau đó chương trình in **hai dòng đo thực tế** bắt đầu bằng `cost=10 samples=12` và `cost=11 samples=12`, mỗi dòng có `p50-ms` và `p95-ms`. **Không có một giá trị milliseconds đúng cố định**, vì máy, OS, JVM và tải nền khác nhau.

Giải thích:

- `"A"` một byte UTF-8; `界` ba byte; `😀` bốn byte và hai UTF-16 code units. Đó là lý do `unicode25-valid=false` dù Java String chỉ dài 25.
- `invalid-unicode-valid=false` do `CharsetEncoder` dùng `REPORT` thay vì âm thầm đổi surrogate lỗi thành dấu hỏi.
- `when-busy=BUSY` là **mô phỏng** giữ sẵn permit; nó chứng minh gate không gọi bcrypt khi hết slot, **không phải load test concurrency**.
- `after-release=MATCH` chứng minh permit được trả trong `finally` và verifier vẫn hoạt động.
- Hàm `measure(...)` tạo hash trước thời gian đo; vòng lặp chỉ đo `matches(...)`. Với 12 mẫu, số p95 chỉ để học cách đo, **không đủ** quyết định SLO/capacity production.
- `GatedVerifier` chưa phải Spring Security filter/provider và không có rate limit theo account/IP. Nó minh họa ranh giới giữa **password sai** và **server bận**.

Cách kiểm tra `input.length() > 72` là **chặn sớm**, vì một UTF-16 code unit hợp lệ không thể cần ít hơn một UTF-8 byte. Nhưng ngược lại `input.length() <= 72` không bảo đảm password <=72 byte; cần chạy `CharsetEncoder`.

## 6. Phòng ngừa cạn tài nguyên: các lớp kiểm soát phải bổ sung nhau

### 6.1. Rate limiting: số lần thử theo thời gian

Thực tế nên có ít nhất các loại quota:

- **Theo account/username đã chuẩn hóa**, độc lập nguồn IP: hạn chế một tài khoản bị brute force từ mạng phân tán.
- **Theo IP/nguồn/endpoint**, độc lập username: hạn chế một nguồn thử password trên rất nhiều tài khoản.
- **Toàn endpoint/hệ thống** khi có spike hoặc dấu hiệu tự động hóa; có thể thêm risk signals, MFA/passkey.
- **Theo hành động**: đăng nhập, đổi mật khẩu, yêu cầu recovery, verify OTP, tạo password mới có chi phí và hậu quả khác nhau.

Tránh một bucket duy nhất theo **cặp IP + username**: attacker có thể tạo cặp mới liên tục và nhận quota mới. Sử dụng Redis/gateway cho bộ đếm phân tán, có TTL và chính sách khi dependency limit bị sự cố.

Rate limiting theo account nếu không thiết kế kỹ có thể bị dùng để **cố ý khóa tài khoản**. Cân nhắc delay tăng dần, challenge và chính sách mở khóa, không vĩnh viễn lock mọi account sau vài lần sai. CAPTCHA chỉ là một lớp hỗ trợ, không thay thế quota.

### 6.2. Concurrency cap: số phép hash chạy **ngay lúc này**

`Semaphore` hoặc bounded worker pool kiểm soát các phép `matches` đồng thời:

```text
requests đã qua quota
     |
     v
Admission gate (K slots)
     |                 \
     | có permit        \ hết permit
     v                   v
PasswordEncoder        BUSY / 429 hoặc 503 theo chính sách
.matches(...)           KHÔNG gọi bcrypt
     |
     v
release permit trong finally
```

**Điểm cốt lõi:** khi bận, không được trả `false` trực tiếp từ `PasswordEncoder.matches(...)` để giả làm mật khẩu sai. Làm vậy dễ khiến `DaoAuthenticationProvider` coi hệ thống quá tải là `BadCredentialsException`, đếm sai lần đăng nhập, kích hoạt lockout và đánh lừa audit.

Gate nên đặt ở tầng HTTP/authentication service **trước** khi gọi `AuthenticationManager.authenticate(...)`, được tích hợp với failure/entry point đúng ngữ nghĩa. Trả overload có kiểm soát như 429/503, có retry/backoff phù hợp. Không “fail open” cho request chưa xác thực.

**Giới hạn của Semaphore trong demo:** nó chỉ giới hạn **một JVM instance**, không chia sẻ quota toàn cụm. Cần rate limiter phân tán hoặc admission upstream để tránh N instance đồng thời tiêu thụ vượt CPU/memory tổng.

### 6.3. Bounded queue, timeout và load shedding

Khi K slots đều bận, thêm queue **vô hạn** khiến request tích tụ, tăng RAM và latency; khi tới lượt xử lý, nhiều client đã timeout. Nên dùng:

- Queue có độ dài tối đa hoặc **fail fast**.
- Thời gian chờ slot hữu hạn; không chờ vô hạn tại request thread.
- Giới hạn HTTP concurrent requests, connection pool và server worker hợp lý.
- Timeout downstream DB/IdP và circuit breaker nếu có service ngoài.
- Response overload khác authentication failure; client retry với exponential backoff + jitter.
- Release permit trong `finally` ngay cả khi exception; không tin `Thread.interrupt` sẽ hủy một thuật toán hashing đã bắt đầu ngay lập tức.

Khi đặt admission sau DB lookup, request bị từ chối vẫn có thể làm truy vấn DB. Cân nhắc kiểm tra early tại endpoint trước DB/hash, nhưng tránh tạo khác biệt thông báo theo việc username có tồn tại.

### 6.4. CPU và RAM cần tính riêng

Giả sử **ví dụ số học**, không phải benchmark:

- `30 phép xác minh/giây` đã qua rate limiter.
- Mỗi phép dùng trung bình `0,2 CPU-second`.
- Nhu cầu tính toán lý tưởng: `30 × 0,2 = 6 CPU-core-seconds mỗi giây`, chưa tính DB/HTTP/GC.

Một pod chỉ có 4 core không thể duy trì workload CPU như vậy vô hạn nếu không scale/tối ưu chính sách. Khi bão hòa, queue wait tăng nên p95/p99 có thể tăng rất nhanh.

Với thuật toán memory-hard, nếu mỗi phép cần 64 MiB RAM và cho 16 phép chạy đồng thời thì riêng hashing đã có thể cần khoảng **1 GiB**, chưa tính heap, request buffers, thread stacks và overhead. Các số 64 MiB/16 chỉ để minh họa phép tính, không phải mặc định Argon2id cho mọi sản phẩm.

Theo Little's law trong trạng thái ổn định:

```text
Average in-flight ≈ request rate × average time in system

Ví dụ:
20 request/s × 0,25 s = 5 request trung bình đang trong hệ thống
```

Đây **không** là công thức tự chọn ngay `Semaphore(5)`. Queue time, CPU quota, DB, thời gian peak và mục tiêu headroom đều phải được đo.

## 7. Chọn BCrypt cost bằng benchmark có kiểm soát

Quy trình thực hiện:

1. Chọn cost ứng viên phù hợp security policy (ví dụ 10, 11, 12) và encoder version đã vá.
2. Chuẩn bị account/hash test, không dùng password hoặc hash production.
3. Warm up JVM rồi đo `matches` với hash **đã tạo**, ghi p50/p95/p99, số mẫu và khoảng thời gian.
4. Chạy thử ở các mức concurrency tăng dần trong **staging được phép** để tìm điểm CPU saturation.
5. Đo HTTP end-to-end với authentication filter, DB, rate limiter, network và logging thật. Tách CPU hash với DB wait.
6. Kiểm tra hash legacy **nhiều cost**, password đúng/sai, username không tồn tại, input dài và đường failure.
7. Đánh giá throughput, CPU throttling, heap/native RAM, GC, queue time, error rate, p95/p99 và SLO.
8. Chọn cost và K in-flight có dự phòng cho peak/bot spike/autoscaling. Lưu lại cấu hình benchmark (JDK, CPU, pod limit, algorithm, samples, load).
9. Sau khi nâng JDK/Spring Security/hardware, benchmark lại; không giả định kết quả cũ còn đúng.

Spring Security dùng mốc **khoảng một giây xác minh** làm gợi ý điều chỉnh work factor. OWASP cũng nhấn mạnh phải tránh phép hash quá lâu gây DoS; không có con số ms bắt buộc cho mọi hệ thống. Thiết kế cuối phải dựa trên risk và capacity thực, không mặc định cost cao nhất.

**`upgradeEncoding(...)` và migration:** tăng cost mới chỉ ảnh hưởng hash mới. Với hash cũ, verify trước rồi rehash từ password đã được xác minh bằng cost mới khi chính sách và transaction cho phép; không `encode(storedHash)`. Với `DelegatingPasswordEncoder`, kiểm tra `{id}`/cost để không báo một latency gộp vô nghĩa.

## 8. Khi nào không nên hash lại mật khẩu?

Spring Security hướng dẫn rằng mật khẩu là **long-term credential**, còn xác minh password là thao tác tốn tài nguyên. Không nên bắt người dùng gửi và xác minh password trên **mọi API request** nếu ứng dụng có thể dùng session hoặc token ngắn hạn an toàn:

- Form login với `SecurityContext`/session: sau xác thực, request có session hợp lệ không nhất thiết chạy bcrypt lại.
- OAuth2/OIDC và token: token được xác minh bằng cơ chế của nó, không tự gọi `UserDetails.isCredentialsNonExpired` hoặc BCrypt trên mọi request.
- HTTP Basic stateless: nhiều request có thể phải kiểm tra password; cân nhắc mô hình credential phù hợp hơn cho API tần suất cao.
- Với MFA/passkey, vẫn cần quota và admission cho các verification paths khác, không chỉ password.

**Không cache raw password, không cache kết quả `matches` theo plaintext, không lưu password trong session để lần sau tự xác minh.** Nếu cache `UserDetails` có hash, cần hiểu credential erasure, invalidation và TTL. Cache user khác với lưu `Authentication` đã xác thực trong session.

### Username không tồn tại và timing

Đường “username không tồn tại” nếu trả ngay còn user có thật thì chạy bcrypt có thể tạo khác biệt thời gian giúp dò account. Một số provider có cơ chế **dummy password hash** để giảm timing discrepancy; nhưng nó cũng làm unknown-user attempts tốn CPU.

Cần chống enumeration **đồng thời** với rate limiting/admission; không tự bỏ timing defense để tăng throughput. Trả thông báo generic cho credential sai, đồng thời giữ lỗi overload, DB outage và invalid input được phân loại nội bộ cho vận hành.

## 9. Kiểm thử đầy đủ: boundary, concurrency và failure

### 9.1. Ma trận tối thiểu

| Điều kiện | Kết quả cần chứng minh |
| --- | --- |
| Password đúng/sai | Kết quả authentication đúng, không lộ hash |
| 72/73 ASCII bytes | Đúng ngưỡng nhận; vượt ngưỡng chặn |
| 24/25 chữ `界` | 72/75 UTF-8 bytes, không dựa `String.length()` |
| 18/19 emoji `😀` | 72/76 bytes |
| Unpaired surrogate UTF-16 | Bị từ chối |
| Password rỗng/null hoặc cực dài | Không chạy thuật toán tốn CPU; body cap ở HTTP layer |
| Old/new bcrypt cost | Verify theo cost của encoded hash, không phải chỉ theo bean |
| Hash sai định dạng | Từ chối an toàn, không plaintext fallback |
| Chạy hết `Semaphore` slot | Trả BUSY/overload, không tính thành bad credentials |
| Exception trong verifier | Slot được trả lại qua `finally` |
| Một IP thử nhiều username | Per-IP quota chặn được |
| Nhiều IP thử một username | Per-account quota chặn được |
| Burst vượt năng lực | Queue bounded, phản hồi sớm, không treo vô hạn |
| DB/IdP chậm hoặc lỗi | Timeout/circuit breaker/độ ưu tiên rõ |
| Session/token hợp lệ | Không hash password lặp vô ích |

Với Spring Security HTTP, dùng integration test qua `MockMvc` hoặc client thật; test bằng `@WithMockUser` **không chứng minh** BCrypt hay `DaoAuthenticationProvider` đã được gọi, vì nó tạo sẵn security context.

### 9.2. Benchmark concurrency phải đo trong staging

- Cold vs warm JVM, một vs nhiều pod, chạy đủ lâu để thấy GC/CPU throttling.
- Tăng tải theo bước, ghi p50/p95/p99, throughput, error rate và queue wait; dừng khi chạm ngưỡng an toàn.
- Phân tách unknown username, wrong password, valid password, legacy hash; đừng trộn vào một histogram rồi kết luận “BCrypt mất X ms”.
- Dùng JMH cho microbenchmark; load test HTTP ở staging bằng công cụ thích hợp. Không chạy thử tải phá hoại trên production.
- Test overload và recovery sau spike: khi tải giảm, queue phải rút và số permit không bị rò rỉ.

### 9.3. Metrics và audit

Nên có histogram `password_verify_duration_seconds` theo algorithm/cost (với số label hữu hạn), gauge `hash_inflight`, `auth_queue_wait_seconds`, CPU throttling, memory/GC, `auth_attempts_total` theo outcome, rate-limit hits, 429/503 và HTTP login p95/p99.

**Không** đưa raw password, stored hash, Authorization header, session cookie, username, email hoặc IP vào **metric labels**. Các chi tiết điều tra có thể lưu ở hệ thống audit có phân quyền, redaction và retention rõ. Phân biệt `bad_credentials` với `capacity_rejected` để tránh khóa account sai.

## 10. Những sai lầm thường gặp

1. **Đo mỗi một lần bcrypt verify** rồi công bố con số cố định.
2. **Đo encode+matches** mà gọi là login verify latency.
3. **Không warmup JVM**, không ghi samples/p95/p99/concurrency.
4. **Tăng cost liên tục** dù CPU/queue đang bão hòa.
5. **Tưởng bean cost mới đã nâng toàn bộ hash cũ.**
6. **Dùng `String.length() <= 72`** để cho phép bcrypt password Unicode.
7. **Chỉ kiểm tra frontend**, không kiểm tra ở backend/login.
8. **Tự truncate password dài** làm mất phần bí mật mà user chọn.
9. **Để body/JSON/password không có limit** khiến parser/memory bị cạn trước khi hash.
10. **Viết regex password phức tạp** có catastrophic backtracking.
11. **Chỉ per-IP limiter** và bỏ per-account quota.
12. **Chỉ per-account limiter** khiến một IP thử vô số username.
13. **Chỉ bucket theo IP+username** để mỗi cặp được cấp quota mới.
14. **Không giới hạn in-flight hashing** dù rate limiter vẫn cho phép burst lớn.
15. **Queue vô hạn hoặc semaphore chờ vô hạn** khiến thread/memory bị giữ.
16. **Trả false khi máy chủ BUSY**, biến overload thành bad password và gây lockout sai.
17. **Quên release permit trong finally**, làm hệ thống suy thoái dần.
18. **Chọn Argon2id memory cost lớn mà không tính concurrent memory.**
19. **Hash mật khẩu ở mọi request** dù đã có session/token hợp lệ.
20. **Bỏ timing/anti-enumeration defense chỉ để tiết kiệm CPU.**
21. **Dùng CAPTCHA là phòng tuyến duy nhất** cho login abuse.
22. **Gắn username/IP vào metric labels** gây cardinality lớn và rò rỉ thông tin.
23. **Load test bằng production credential**, gây rủi ro bảo mật/availability.
24. **Không test overload, DB timeout, unknown users, legacy hash.**
25. **Không xem security advisory** của thư viện password encoder khi nâng cấp.

## 11. Bài tập củng cố

**Bài A:** chạy demo cost 10 và 11, ghi số p50/p95 đo được và môi trường JDK/CPU. Lặp vài lần để thấy biến thiên. Không biến một lần đo thành SLO production.

**Bài B:** thay password test bằng 72 ASCII bytes, 24 chữ `界`, 18 emoji `😀`, 25 chữ `界` và một surrogate lỗi. Viết unit test giải thích ngưỡng UTF-8 bytes.

**Bài C:** dùng JMH để đo riêng `matches`, sau đó chạy load test staging với concurrency 1/4/8/16; so sánh p95/p99 và CPU utilization.

**Bài D:** giả sử 50 verify/s và 0,15 CPU-second cho một verify. Tính nhu cầu CPU lý tưởng và giải thích vì sao phải cộng headroom/DB/GC trước khi chọn số pod.

**Bài E:** mở rộng `GatedVerifier` để đếm các outcome MATCH/MISMATCH/BUSY; verify rằng BUSY không tăng bad-credentials counter. Thử ném exception và kiểm tra permit được trả.

**Bài F:** thiết kế hai quota độc lập per-account/per-IP. Giải thích cách chống một IP thử nhiều user và nhiều IP thử một user.

**Bài G:** có bcrypt cost 10 và cost 12 trong cùng DB, encoder bean hiện dùng cost 12. Đo verify từng tài khoản, đề xuất verify-then-rehash an toàn.

**Bài H:** với Argon2id giả định 64 MiB/hash, tính memory demand cho 2/8/16 verify đồng thời. Nêu giới hạn của phép tính và metrics cần đo.

**Bài I:** trong incident CPU 100%, p99 login tăng, nhận diện bot traffic. Lập runbook: quota/admission, queue, DB, throttling, autoscaling, audit và recovery sau spike. Không tắt xác thực hoặc dùng `NoOpPasswordEncoder` để “giảm tải”.

### Tiêu chí hoàn thành

Người học giải thích được **chi phí verify**, giới hạn **72 UTF-8 bytes** khi dùng bcrypt, sự khác nhau giữa per-account rate limit và concurrency cap, lý do overload không phải wrong password, cách tính CPU/RAM budget, cách benchmark đáng tin và cách tránh hash password vô ích trên mọi HTTP request.

## 12. Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): adaptive hashing, work factor, vì sao không xác minh password trên mỗi request.
- [Spring Security 6.5.11 — BCryptPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): `matches`, `encode`, `upgradeEncoding` và cost.
- [Spring Security 6.5.11 — DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): `{id}` và migration.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): work factor, BCrypt 72-byte limit, Argon2id và nguy cơ exhaustion.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login throttling, generic errors, account lockout, MFA.
- [OWASP — Credential Stuffing Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): bảo vệ trước lưu lượng thử credential tự động.
- [Spring Security — CVE-2025-22228](https://spring.io/security/cve-2025-22228/): vấn đề kiểm tra bcrypt password quá dài trong các bản cũ.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm tra Unicode bằng `CodingErrorAction.REPORT`.
- [OpenJDK JMH](https://github.com/openjdk/jmh): framework microbenchmark JVM.

Các số đo trong ví dụ phải lấy từ **lệnh chạy thật trên môi trường của bạn**; bài không khẳng định đã benchmark production. Với Spring Security 7 hoặc password encoder tùy chỉnh, xác minh API và giới hạn đầu vào của đúng implementation trước khi áp dụng.