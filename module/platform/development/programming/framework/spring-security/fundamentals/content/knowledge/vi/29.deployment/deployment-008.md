# Hiệu năng băm mật khẩu và độ trễ của các dịch vụ xác thực ngoài

## 1. Đăng nhập chậm không nhất thiết do cùng một nguyên nhân

Khi triển khai ứng dụng Java với Spring Security, một request xác thực có thể chậm do **chi phí băm mật khẩu được chủ đích thiết kế cao**, hoặc do **chờ mạng và dịch vụ xác thực bên ngoài**. Hai loại độ trễ này có bản chất và cách xử lý khác nhau:

- Băm mật khẩu bằng `bcrypt`, `PBKDF2`, `scrypt` hoặc `Argon2` tiêu tốn CPU và/hoặc bộ nhớ **để tăng chi phí đoán mật khẩu khi dữ liệu hash bị lộ**. Không được thay bằng hash nhanh hoặc mật khẩu plaintext chỉ vì login chậm.
- Gọi LDAP, OIDC token endpoint, IdP, OAuth2 opaque-token introspection hoặc dịch vụ thông tin người dùng có thể mất thời gian do DNS, TLS, mạng, kết nối, hàng đợi, tải ở IdP, cache hoặc retry. Đó là **độ trễ phụ thuộc hệ thống khác**.
- API xác minh JWT ký số thường có thể **kiểm tra token cục bộ** nhờ khóa công khai đã cache. Không nên mặc định mọi request Bearer đều phải gọi IdP.
- Ứng dụng dùng **session sau form login** thường không băm password trên từng request; password được kiểm tra khi người dùng thực hiện login hoặc re-authentication. Điều này là lý do session/token ngắn hạn có thể giảm rất nhiều tải băm so với HTTP Basic được xác thực ở mỗi request.

Mục tiêu học tập:

1. Đo và phân tích chi phí `PasswordEncoder.encode` / `matches` trên hạ tầng thật.
2. Chọn **work factor** đủ mạnh trong giới hạn an toàn vận hành, không chạy đua theo một con số cứng.
3. Ước lượng tải đồng thời và tránh tạo điểm nghẽn CPU/bộ nhớ hoặc tự gây DoS ở endpoint login.
4. Phân biệt độ trễ OIDC login, JWT validation, remote introspection và LDAP.
5. Đặt timeout, giới hạn concurrency, circuit breaker, retry và cache **không làm yếu quy tắc xác thực/thu hồi**.
6. Dùng metrics, tracing đã loại bỏ dữ liệu bí mật và test tải để tối ưu mà vẫn bảo vệ tài khoản.

Phạm vi ví dụ: **Java 17+, Spring Boot 3.x, Spring Security 6.x**. Với Spring Boot/Security phiên bản major mới hơn, đối chiếu lại API và defaults. Mọi thời gian trong các bảng bên dưới chỉ là **dữ liệu minh họa hoặc công thức**, không phải kết quả benchmark trên thiết bị của bạn.

## 2. Vẽ đúng luồng trước khi đo

### 2.1. Ứng dụng xác thực mật khẩu cục bộ

```text
Client -> POST /login
    -> network/TLS/web filter
    -> query account ở DB/cache
    -> PasswordEncoder.matches(rawPassword, storedHash)
    -> kiểm tra account locked/disabled và chính sách khác
    -> tạo Authentication và session/token hợp lệ
    -> trả response/redirect
```

Tổng thời gian người dùng cảm nhận có thể được mô tả bằng:

```text
T_login ≈ T_network + T_queue + T_db + T_password_match
        + T_policy + T_session + T_response
```

Đây là cách **phân rã để đo** chứ không phải phép cộng hoàn toàn chính xác trong một hệ thống có các bước song song. Nếu `T_password_match` lớn, giảm số lần query DB không nhất thiết làm login nhanh đáng kể. Nếu CPU còn rảnh nhưng response vẫn chậm, hãy đo queue, database hoặc network trước khi thay work factor.

### 2.2. Web đăng nhập qua OIDC

```text
Browser -> Spring Security OAuth2 Login client
       -> redirect tới IdP (DNS, TLS, network)
       -> user nhập credential/MFA hoặc SSO session tại IdP
       -> browser chuyển về app với authorization code
       -> app gọi token endpoint và kiểm tra response/ID token
       -> app ánh xạ danh tính -> account, quyền và session
       -> browser nhận response
```

Thời gian ở đây bao gồm **thời gian tương tác của người dùng** và nhiều kết nối giữa browser, IdP, ứng dụng. Không được đo login OIDC chỉ bằng một lần HTTP call đến endpoint nội bộ rồi kết luận độ trễ end-to-end.

### 2.3. API xác minh Bearer token

```text
JWT access token:
  Client -> API -> parse/verify JWT + validate claims
                -> dùng public key từ JWKS cache khi khả dụng
                -> authorization -> response

Opaque token qua introspection:
  Client -> API -> HTTPS tới IdP introspection endpoint
                -> kiểm tra token active, scopes/claims
                -> authorization -> response
```

Điểm khác biệt lớn: JWT validation thông thường **không cần remote introspection mỗi request** sau khi có key phù hợp; opaque-token introspection theo cấu hình mặc định của Spring Security **gọi endpoint bên ngoài để xác minh Bearer token**. Cấu hình có cache hoặc provider chuyên dụng có thể thay đổi mô hình, nhưng không được giả định đã có cache khi chưa kiểm tra.

## 3. Vì sao password hashing phải cố ý tốn tài nguyên?

Mật khẩu không nên lưu nguyên văn và không nên chỉ `SHA-256(password)`. Thuật toán hash nhanh dùng cho tính toàn vẹn có thể cho phép kẻ tấn công thử số lượng candidate rất lớn khi database chứa hash bị đánh cắp.

Các password-hashing function được thiết kế thích ứng: tăng **work factor** làm mỗi lần kiểm tra một candidate tốn tài nguyên hơn. Điều này bất tiện cho server thật khi login, nhưng cũng làm tấn công đoán mật khẩu offline đắt đỏ hơn.

| Thuật toán | Đặc tính chính | Những điều cần chú ý khi triển khai |
| --- | --- | --- |
| `bcrypt` | Hash mật khẩu thích ứng, chi phí phụ thuộc cost/strength | Cần benchmark cost trên CPU thật; lưu ý giới hạn đầu vào bcrypt/Unicode khi thiết kế password policy |
| `PBKDF2` | Nhiều vòng lặp hàm dẫn xuất khóa; được hỗ trợ rộng | Cần chọn iteration/PRF và chính sách tương ứng; phù hợp một số ràng buộc tuân thủ |
| `scrypt` | Được thiết kế tiêu tốn cả bộ nhớ | Cần dự tính RAM theo số phép kiểm tra đồng thời |
| `Argon2id` / `Argon2` | Hướng đến đề kháng tốt hơn với tấn công trên phần cứng song song; tham số thời gian/bộ nhớ/song song | Cần đo **cả CPU và RAM**; phiên bản Spring Security/implementation có dependency và tham số riêng |

Không tự triển khai thuật toán hash hoặc salt ngẫu nhiên ở mức thấp khi framework đã cung cấp `PasswordEncoder`. Mỗi password hash thông thường phải mang salt/ngẫu nhiên phù hợp do encoder quản lý; **hai lần hash cùng mật khẩu không nên mặc định cho ra cùng chuỗi**.

### Work factor không phải "mật khẩu mạnh hay yếu"

Mật khẩu dài/khó đoán, chống mật khẩu rò rỉ, MFA và tốc độ thử trên endpoint là các lớp phòng vệ riêng. Một hash tốn 1 giây không cứu được tài khoản có mật khẩu đơn giản trước online guessing nếu API không giới hạn tốc độ; đồng thời MFA không thay thế lưu hash đúng cách.

Tài liệu Spring Security 6.5 khuyến nghị **hiệu chỉnh work factor để việc verify mật khẩu mất khoảng một giây trên hệ thống của bạn** như điểm tham chiếu bảo mật, không phải một SLA bắt buộc cho mọi tổ chức. Cần cân bằng khuyến nghị đó với cấu hình máy, RAM, mức tải thực, p95/p99, khả năng phục hồi và chính sách hiện hành. Bắt đầu bằng benchmark trong môi trường tương đương production, không chép một giá trị cost duy nhất từ máy phát triển.

### Vì sao hash càng chậm không phải lúc nào càng tốt?

Nếu một lần `matches` tốn gần hết CPU core trong một giây, 10–20 request login cùng lúc có thể gây hàng đợi dài, timeout, làm cạn tài nguyên API hoặc khiến người dùng hợp lệ không đăng nhập được. Với scrypt/Argon2, còn có giới hạn **RAM trên số verify đồng thời**. Tăng work factor phải đi cùng capacity planning và bảo vệ login trước lưu lượng bất thường.

## 4. Spring Security PasswordEncoder và định dạng hash

Một cấu hình phổ biến:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Đây là **snippet cho class @Configuration** của ứng dụng Spring, cần import `PasswordEncoder`, `PasswordEncoderFactories` và `@Bean`. `DelegatingPasswordEncoder` cho phép lưu hash với một ID thuật toán ở đầu, ví dụ:

```text
{bcrypt}$2a$...hash...
{pbkdf2@SpringSecurity_v5_8}...hash...
{scrypt@SpringSecurity_v5_8}...hash...
```

Các chuỗi trên là **hình dạng minh họa, không phải hash hợp lệ để đăng nhập**. ID cho biết decoder nào được dùng khi `matches`; khi ứng dụng nâng cấp chính sách, có thể vẫn xác minh hash cũ và nâng cấp khi điều kiện cho phép.

Lưu ý:

- `DelegatingPasswordEncoder` **không tự động làm cho BCrypt rẻ hơn**; từng thuật toán có chi phí thật.
- `new BCryptPasswordEncoder(11)` dùng strength 11, **không phải đề xuất rằng 11 luôn đủ hoặc luôn nhanh**. Cost 10 là mặc định tham chiếu ở nhiều bản Spring Security 6.x; cần kiểm tra phiên bản đang chạy.
- Mỗi lần `encode` khi tạo/đổi mật khẩu có chi phí; mỗi lần `matches` khi login cũng tốn công tính toán. **Không mã hóa lại mật khẩu của tất cả user khi ứng dụng khởi động.**
- Không so sánh hai chuỗi hash bằng `storedHash.equals(encoder.encode(rawPassword))` vì salt khiến kết quả khác. Dùng `encoder.matches(rawPassword, storedHash)`.
- Đừng sửa lỗi hash không có `{id}` bằng cách để `NoOpPasswordEncoder` làm fallback production. Cần kế hoạch migration hash legacy có giới hạn và được kiểm thử.
- Khi nâng work factor, dùng cơ chế nâng cấp mật khẩu được kiểm soát (ví dụ `PasswordEncoder.upgradeEncoding` kết hợp `UserDetailsPasswordService` khi phù hợp) thay vì buộc user phải cung cấp plaintext của mọi tài khoản để hash lại hàng loạt.

## 5. Ví dụ Java 17+ chạy được: đo thời gian encode và matches

Ta tạo **một ứng dụng command-line Spring Boot** không mở web server để đo đúng một phần thuật toán, tránh API benchmark công khai dễ bị lạm dụng.

Khởi tạo dự án Spring Boot 3.x, Java 17+, Gradle bằng Spring Initializr; có thể chọn starter cốt lõi, rồi bổ sung Spring Security Crypto. Trong `build.gradle` đã có plugin Spring Boot/dependency management từ Initializr, bảo đảm các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.security:spring-security-crypto'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu Initializr đã tạo dependency trùng tên, **giữ một khai báo**. Đây là khối `dependencies`/`test` chứ không phải toàn bộ build script.

Tệp Java đầy đủ:

```text
src/main/java/demo/hashbench/PasswordHashBenchApplication.java
```

```java
package demo.hashbench;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordHashBenchApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordHashBenchApplication.class, args);
    }

    @Bean
    ApplicationRunner runHashBenchmark() {
        return args -> {
            // Không dùng mật khẩu thật; chỉ là fixture cục bộ.
            String samplePassword = "local-test-password-only!";

            // Strength=11 chỉ phục vụ bài đo, phải tune lại.
            PasswordEncoder encoder = new BCryptPasswordEncoder(11);
            String initialHash = encoder.encode(samplePassword);

            boolean right = encoder.matches(
                samplePassword, initialHash
            );
            boolean wrong = encoder.matches(
                "not-the-password", initialHash
            );

            // Warm-up để giảm nhiễu khởi tạo JVM/thư viện.
            for (int i = 0; i < 2; i++) {
                encoder.matches(samplePassword, initialHash);
            }

            List<Long> encodeNanoseconds = new ArrayList<>();
            List<Long> verifyNanoseconds = new ArrayList<>();

            for (int i = 0; i < 12; i++) {
                long encodeStart = System.nanoTime();
                String hash = encoder.encode(samplePassword);
                long encodeEnd = System.nanoTime();

                long verifyStart = System.nanoTime();
                boolean matches = encoder.matches(
                    samplePassword, hash
                );
                long verifyEnd = System.nanoTime();

                if (!matches) {
                    throw new IllegalStateException(
                        "Hash verify did not match!"
                    );
                }

                encodeNanoseconds.add(
                    encodeEnd - encodeStart
                );
                verifyNanoseconds.add(
                    verifyEnd - verifyStart
                );
            }

            Collections.sort(encodeNanoseconds);
            Collections.sort(verifyNanoseconds);

            System.out.println("algorithm=bcrypt");
            System.out.println("strength=11");
            System.out.println("correctMatches=" + right);
            System.out.println("wrongMatches=" + wrong);
            printStats("encode", encodeNanoseconds);
            printStats("verify", verifyNanoseconds);
        };
    }

    private static void printStats(
            String phase, List<Long> sorted) {

        System.out.printf(
            Locale.ROOT,
            "%s_p50_ms=%.1f%n",
            phase,
            percentileMilliseconds(sorted, 0.50)
        );
        System.out.printf(
            Locale.ROOT,
            "%s_p95_ms=%.1f%n",
            phase,
            percentileMilliseconds(sorted, 0.95)
        );
    }

    private static double percentileMilliseconds(
            List<Long> sorted, double fraction) {

        int index = Math.max(
            0, (int) Math.ceil(fraction * sorted.size()) - 1
        );

        // Số liệu đo bằng nanosecond, đổi sang millisecond.
        return sorted.get(index) / 1_000_000.0;
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.application.name=password-hash-bench
```

Chạy ở root project Gradle:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

Các dòng **có giá trị xác định** của chương trình khi encoder hoạt động đúng:

```text
algorithm=bcrypt
strength=11
correctMatches=true
wrongMatches=false
```

Ngoài các dòng đó, ứng dụng còn có log khởi động Spring Boot và bốn dòng đo `encode_p50_ms`, `encode_p95_ms`, `verify_p50_ms`, `verify_p95_ms`. **Không có một stdout thời gian cố định** vì phụ thuộc CPU, máy ảo, JIT, tải concurrent và môi trường. Ví dụ hình thức:

```text
encode_p50_ms=<giá trị đo thực tế>
encode_p95_ms=<giá trị đo thực tế>
verify_p50_ms=<giá trị đo thực tế>
verify_p95_ms=<giá trị đo thực tế>
```

Đây chỉ là placeholder giải thích kiểu output, **không phải số đã đo**. Bài benchmark dùng 12 mẫu để dễ học, **không đủ để kết luận p95 hoặc p99 production đáng tin cậy**. Muốn công bố số liệu năng lực phải có nhiều mẫu, warm-up phù hợp, nhiều lượt chạy và tải đồng thời theo mô hình thực tế.

### Vì sao phải đo encode và verify riêng?

- `encode` thường chạy khi tạo account, đổi mật khẩu hoặc nâng cấp hash; chi phí ảnh hưởng throughput của những chức năng này.
- `matches` chạy lúc xác thực password; chi phí tác động trực tiếp tới thời gian login và tải CPU.
- Với thuật toán/hash hiện tại, cả hai có thể cùng bậc chi phí, nhưng **đừng chỉ lấy một lần encode để dự đoán mọi lần matches**. Lưu hash có tham số khác nhau, phần cứng khác nhau hoặc nhiều request đồng thời sẽ thay đổi kết quả.

**Không chạy benchmark có password thật** và không log hash/credential. Trong sản phẩm, không thêm endpoint `/benchmark-password` public; kẻ tấn công có thể biến nó thành tài nguyên DoS.

## 6. Từ phép đo đơn lẻ đến năng lực xử lý đồng thời

Một thời gian xác minh mật khẩu ở máy rảnh không phải năng lực phục vụ toàn hệ thống. Hãy nhìn các thành phần:

- Số **vCPU thực sự được cấp** trong container/VM (quota/limit có thể thấp hơn cấu hình host).
- Chi phí CPU của một lần verify; thuật toán memory-hard còn tiêu thụ RAM.
- Số request login đồng thời và mức sử dụng CPU của các endpoint/DB khác.
- Kích thước thread pool và hàng đợi, connection pool DB và headroom cho GC.
- Trường hợp tấn công credential stuffing làm tăng login attempts nhưng **không tăng số người dùng hợp lệ**.

### Ước lượng CPU theo công thức

Nếu phép verify chủ yếu chiếm CPU khoảng `T_cpu` giây và incoming rate là `lambda` lần verify/giây, tải CPU tương đương xấp xỉ:

```text
CPU core-seconds per second ≈ lambda * T_cpu

Ví dụ MINH HỌA:
  lambda = 20 xác minh mật khẩu / giây
  T_cpu  = 0.25 giây CPU / xác minh
  demand = 20 * 0.25 = 5 CPU core-seconds / giây

Một instance chỉ có 4 vCPU không thể bền vững đáp ứng
đồng thời 5 core-seconds/giây cho riêng password verify
mà không có tối ưu kiến trúc, chia tải hoặc giảm traffic.
```

Đây chỉ là mô hình gần đúng, không tính overhead, memory bottleneck, context switching và các công việc khác. Nếu `matches` tốn 1 giây CPU thì 20 lần/giây tương đương nhu cầu 20 CPU core-seconds mỗi giây. Cần tăng số instance/tài nguyên, giảm các lần verify không cần thiết hoặc thiết kế lại luồng; **không tự hạ work factor đến mức không còn đáp ứng chính sách mật khẩu**.

### Little's Law khi chờ dịch vụ bên ngoài

Với tốc độ request `lambda` và thời gian ở trạng thái đang xử lý/chờ `W`, số request in-flight trung bình gần đúng:

```text
L = lambda * W

Ví dụ:
  100 lần gọi introspection/giây
  mỗi lần trung bình chờ 0.15 giây
  L ≈ 100 * 0.15 = 15 calls đang chờ

Nếu p99 tăng 2 giây trong lúc sự cố,
in-flight và queue có thể tăng rất nhanh,
đặc biệt khi client không đặt timeout/limit.
```

**Phân biệt CPU saturation và network wait:** 15 remote calls đang chờ không tương đương 15 core CPU bận. Chúng vẫn chiếm connection, memory, request slots và có thể chiếm thread nếu HTTP client blocking. Phải đo đủ CPU, thread, connection pool và queue.

### Hai kiểu hàng đợi nguy hiểm

1. **Hash verification CPU-bound:** mở thread pool vô hạn không làm CPU tính hash nhanh hơn. Nó làm nhiều task tranh CPU và tăng latency tail.
2. **External authentication I/O-bound:** mở quá nhiều connection hoặc retry không giới hạn có thể quá tải IdP và chính ứng dụng, gây cascading failure.

Hệ thống thực tế cần bounded concurrency, queue có giới hạn, admission control và rate limiting. Khi quá tải, trả lỗi/giới hạn rõ ràng theo chính sách tốt hơn để request chờ vô hạn rồi hết hạn đồng loạt.

## 7. Work factor và khả năng nâng cấp hash

Tăng cost là thay đổi **chính sách bảo mật lẫn hiệu năng**, không chỉ đổi một giá trị:

```java
// Minh họa cách cấu hình encoder riêng, không phải
// chương trình độc lập.
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

Nếu chuyển từ cost 10 sang 12, bcrypt tăng đáng kể công việc tính toán theo cấp số nhân của cost; **không thể dự đoán thời gian ms chính xác** mà không benchmark. Với thuật toán memory-hard, thay đổi tham số bộ nhớ/parallelism còn có thể khiến container hết RAM dưới concurrency.

Quy trình thay đổi nên là:

1. Ghi phiên bản policy, thuật toán/hash format và cost hiện hành.
2. Benchmark trên phần cứng/staging gần production, trong cả điều kiện tải bình thường và tải cao.
3. Xác định login p50/p95/p99, CPU/RAM, queue depth, error rate, khả năng auto-scale.
4. Chạy load test có giới hạn an toàn và kiểm tra các tình huống không có user, mật khẩu sai, credential stuffing.
5. Triển khai theo đợt; theo dõi bùng CPU/latency và có kế hoạch rollback cấu hình **mà không làm mất khả năng xác minh hash đã nâng cấp**.
6. Tận dụng prefix `{id}` của `DelegatingPasswordEncoder` / khả năng `upgradeEncoding` cùng cơ chế lưu lại hash mới **sau khi người dùng chứng minh mật khẩu đúng**, nếu ứng dụng hỗ trợ.
7. Không lưu password plaintext để “rehash sau”, không bật `NoOpPasswordEncoder` tạm thời, không cắt bớt bước authentication trong lúc quá tải.

### Lưu ý về quá trình nâng cấp

Nếu hash cũ vẫn hợp lệ nhưng dùng work factor thấp, ứng dụng có thể kiểm chứng hash cũ theo format cũ rồi nâng cấp sau lần đăng nhập thành công. Để tránh race, cần cập nhật hash an toàn khi có nhiều request concurrent và khi user đổi password ở một phiên khác.

Không thể nâng cấp hash an toàn từ hash cũ mà không có nguyên liệu phù hợp: không có password plaintext thì không thể chỉ "băm lại hash" để biến thành hash password tương đương. `UserDetailsPasswordService` có thể hỗ trợ lưu password hash đã nâng cấp khi Spring Security thực hiện workflow tương ứng; cần xác minh cách provider thật của dự án sử dụng interface đó.

### Đo với tài khoản không tồn tại

Nếu server trả "user không tồn tại" ngay mà không chạy bất kỳ phép verify tương đương nào, kẻ tấn công có thể dùng chênh lệch timing để đoán sự tồn tại của username. Một số authentication provider có biện pháp giảm timing differences, nhưng không được mặc định custom code đã có. Thiết kế thông điệp lỗi chung và phương pháp giảm user enumeration; lưu ý thực hiện dummy hash verification cũng làm tăng CPU cost và phải nằm trong capacity plan.

## 8. Chỉ trả chi phí password hash ở những thời điểm thật sự cần

Tài liệu Spring Security nhấn mạnh rằng việc xác minh password đắt đỏ **trên mọi request** làm suy giảm hiệu năng. Sau khi chứng minh long-term credential, web app có thể phát **HTTP session** hoặc token ngắn hạn có cơ chế xác thực thích hợp.

| Cách request được xác thực | Password hash có chạy mỗi request không? | Lưu ý |
| --- | --- | --- |
| Form login với session | Thường **không**; khi login/re-auth mới verify | Session validation, expiry, CSRF, cookies và revocation vẫn phải bảo vệ |
| HTTP Basic cho mỗi API request | Có thể **có**, tùy provider và caching | Nếu mỗi request gọi UserDetailsService và matches, chi phí rất cao; chỉ dùng theo hợp đồng phù hợp |
| API JWT access token | Thường không băm password; verify token bằng public key/HMAC tương ứng | Phải kiểm tra chữ ký, issuer, audience, expiry, scope và chính sách resource |
| Opaque token introspection | Không băm password ở API; thường gọi IdP qua mạng | Chi phí chuyển sang remote validation/introspection |
| OIDC browser login + app session | Password (nếu có) được xử lý ở IdP, app nhận kết quả hợp lệ | Callback/token endpoint/session và quyền nghiệp vụ vẫn cần kiểm tra |
| API key riêng | Không mặc định giống password login | Cần cơ chế token/API key validation, bảo vệ secret, scope và rate limiting riêng |

**Không coi session/token ngắn hạn là "mở xác thực".** Session ID phải khó đoán và được bảo vệ bằng cookie; token phải xác minh đúng; quyền trên tài nguyên vẫn phải được kiểm tra. Tối ưu là giảm **số lần xử lý long-term credential**, không giảm các ràng buộc bảo mật.

## 9. Độ trễ khi tích hợp dịch vụ xác thực ngoài

Một kiến trúc có thể kết nối:

- LDAP/Active Directory để tìm account hoặc xác thực credential.
- IdP OIDC/OAuth2 cho redirect login, đổi authorization code hoặc lấy thông tin user khi cần.
- OAuth2 introspection endpoint để xác minh opaque token.
- JWKS endpoint để lấy public keys phục vụ JWT validation.
- UserInfo endpoint hoặc hệ thống mapping group/membership.
- Dịch vụ MFA, fraud/risk assessment, device posture hoặc directory đồng bộ.

Mỗi loại tạo độ trễ khác nhau. Không nên gộp mọi thứ thành một metric `login.duration` rồi tối ưu ngẫu nhiên.

| Tích hợp | Khi nào gọi? | Độ trễ chính | Tác động khi IdP lỗi |
| --- | --- | --- | --- |
| OIDC interactive login | Khi bắt đầu/hoàn thành login, hoặc re-auth | Browser redirect, thời gian người dùng, token exchange, key/claim validation | Login mới có thể không hoàn tất; session cũ phụ thuộc chính sách |
| LDAP bind/search | Khi dùng LDAP authentication hoặc lookup | Network, TLS, directory search, server load | Không xác thực/tra account mới được nếu không có cơ chế thay thế hợp lệ |
| JWT resource server | Mỗi request: crypto verify/claims; key fetch khi cần | CPU verify nhỏ hơn password hash; JWKS/cache miss là network | Các request cần khóa chưa có có thể lỗi; key cached hợp lệ có thể tiếp tục |
| Opaque-token introspection | Thường mỗi Bearer request cần validation | Remote network/IdP latency trên request path | API có thể không xác thực được token; phải fail closed |
| UserInfo/profile/group lookup | Khi app thật sự cần dữ liệu ngoài | Remote I/O, rate limits, cache staleness | Có thể ảnh hưởng login hoặc authorization tùy chính sách |
| Token refresh | Khi refresh token hết hạn/đến hạn đổi | Remote token endpoint | Không đổi được token; refresh token phải bảo vệ |

**JWT không phải "miễn phí".** Crypto verification và JSON parsing có chi phí CPU, nhất là dưới tải lớn. Nhưng nó thường tránh một round-trip đến IdP trên mỗi request sau khi các public key cần thiết đã sẵn sàng. Cần đánh giá cả validation đúng audience, algorithm, issuer và key rotation.

## 10. Spring Security Resource Server: JWT và opaque introspection

Trong API Spring Boot 3.x / Security 6.x dùng Servlet, thêm dependency `spring-boot-starter-oauth2-resource-server` để cấu hình Bearer token. Không tự xây bộ xác minh JWT bằng cách Base64 decode payload mà bỏ qua chữ ký.

### 10.1. JWT access token được xác minh cục bộ

`src/main/resources/application-jwt.properties`, thay URL bằng issuer thật được phép tin:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/realms/demo
```

Một Spring Security chain trong API có thể cấu hình:

```java
// Snippet bên trong lớp @Configuration của API.
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

Đây là **đoạn cấu hình**, không phải chương trình Spring Boot hoàn chỉnh. Cần imports `Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và OAuth2 Resource Server starter.

Theo tài liệu Spring Security 6.5, cấu hình issuer có thể khám phá metadata và JWKS **ở lần yêu cầu JWT đầu tiên** trong cấu hình phù hợp; không nên khẳng định mọi phiên bản sẽ gọi IdP ở startup. Sau khi có khóa hợp lệ trong cache, các request tiếp theo thường xác minh JWT cục bộ. Khi khóa đổi, hệ thống phải tải JWKS mới và xử lý refresh/cache đúng cách.

Để khai báo JWKS URI rõ ràng mà vẫn giữ issuer validation, có thể cung cấp **cả hai** thuộc tính:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/realms/demo
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.test/realms/demo/protocol/openid-connect/certs
```

Theo cơ chế được tài liệu Spring Security 6.5 mô tả, cấu hình `jwk-set-uri` giúp resource server không cần gọi discovery endpoint IdP lúc startup, còn `issuer-uri` vẫn kiểm tra claim `iss`. **Địa chỉ JWKS ở trên chỉ là ví dụ của một loại IdP**; phải lấy URI thực từ metadata/tài liệu của nhà phát hành.

Đừng dựa vào cache JWKS để bỏ qua token đã hết hạn, issuer sai, scope/authority thiếu hoặc audience không khớp. **Cấu hình issuer không tự bảo đảm audience đúng với API của bạn**; cần thêm `aud` validator và test theo hợp đồng token. TTL cache của key và chiến lược rotation cũng cần được thử: một key mới xuất hiện khi IdP quay vòng có thể làm tăng p99 do key miss/fetch, không phải vì CPU hash password.

### 10.2. Opaque-token introspection thực hiện remote call

Khi API nhận opaque Bearer token, một cấu hình Spring Boot 3.x có thể là:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
```

`${...}` được thay theo cú pháp biến môi trường Spring Boot khi copy; không nhập client secret thật vào Git. Với OAuth2 Resource Server starter và cấu hình phù hợp, Spring Security dùng introspection endpoint để kiểm tra token đang active và lấy scope/authority; **đây là điểm phát sinh network latency trên đường request**.

Cần phân biệt:

- Token được IdP trả `active=false` là **không hợp lệ**: reject theo xác thực.
- Introspection không trả về vì network timeout/503 là **không thể xác minh**: **không được xem token là hợp lệ**. Đừng mặc định chuyển sang `permitAll()`, bỏ qua kiểm chứng hoặc lấy user ID từ header.
- Token hợp lệ nhưng thiếu quyền truy cập resource vẫn bị từ chối ở authorization, dù introspection thành công.
- Introspection là nguồn sự thật theo chính sách về trạng thái token; nếu cache kết quả "active", bạn đang chấp nhận độ trễ thu hồi tương ứng. Cần quyết định rõ ràng và đánh giá rủi ro.

Việc retry introspection phải cẩn trọng: retry ngay mọi lỗi có thể nhân lưu lượng và gây sập IdP đúng lúc IdP đã quá tải. Chỉ thử lại một số lỗi transient có chủ đích khi ngân sách thời gian và tính idempotent của request cho phép; dùng backoff/jitter, giới hạn tổng số lần, circuit breaker và concurrency cap.

### 10.3. So sánh JWT và introspection một cách chính xác

| Tiêu chí | JWT local validation | Opaque introspection |
| --- | --- | --- |
| Request API có bắt buộc gọi IdP không? | Không phải mỗi lần, nếu key hợp lệ đã có | Thường có remote call cho mỗi token-bearing request |
| Độ trễ phổ biến | CPU ký số/parse/claim + JWKS miss theo lúc | Network/TLS + IdP xử lý + queue |
| IdP downtime | Cached key có thể tiếp tục xác minh token đã phát hành nếu policy cho phép | Có thể không xác minh được, dẫn tới request bị từ chối/thất bại |
| Thu hồi gần thời gian thực | Cần TTL ngắn, denylist hoặc cơ chế bổ sung | Có thể phản ánh trạng thái token qua introspection |
| Scale throughput | Tập trung ở API CPU và phân phối public key | Cần tính throughput/quota của IdP và client pool |
| Rủi ro cache | Key stale/rotation, claim stale theo TTL token | Cache active token kéo dài cửa sổ revocation |
| Chính sách chung | Kiểm tra signature, exp/nbf, iss, aud, scope, tenant | Kiểm tra response active, client auth, scope, resource authorization |

Không chọn JWT **chỉ vì nhanh** nếu sản phẩm đòi hỏi thu hồi token tức thời hoặc access policy phức tạp; cũng không chọn introspection **chỉ vì dễ lập trình** nếu IdP không đáp ứng được throughput và latency của API. Quyết định thuộc kiến trúc bảo mật và yêu cầu vận hành.

## 11. Timeout, retry, circuit breaker và connection pool

### 11.1. Đặt ngân sách thời gian từ request ở ngoài vào

Ví dụ một API có SLO p95 500 ms. Nếu nó gọi ba dependency tuần tự và mỗi dependency có timeout 2 giây, **ngân sách request bị phá vỡ ngay khi sự cố xảy ra**. Cần xây từ mục tiêu end-to-end xuống từng bước.

```text
User/API request budget = T_total

T_total phải bao gồm:
  routing + TLS/proxy + auth validation
  + business processing + data store
  + response serialization + network

Ví dụ minh họa (không phải cấu hình chung):
  API deadline tổng 1000 ms
  auth dependency budget tối đa 300 ms
  DB/business/response dùng phần còn lại + headroom

Nếu IdP không đáp ứng kịp deadline, không kéo dài
request vô hạn và không bỏ qua authentication.
```

**Không áp dụng cùng deadline cho login OIDC tương tác với người dùng.** Người dùng có thể mất thời gian hoàn thành MFA; authorization request/session ở IdP có timeout riêng theo giao thức. Các HTTP client-to-IdP calls như token exchange và introspection mới là nơi đặt connect/read/response timeout phù hợp.

### 11.2. Phân biệt timeout của từng lớp

- **Connect timeout:** không tạo được TCP connection tới endpoint.
- **TLS handshake timeout:** kết nối TCP có nhưng TLS không hoàn tất.
- **Response/read timeout:** gửi request thành công nhưng không nhận đủ response trong thời gian cho phép.
- **Connection pool acquisition timeout:** chờ một connection sẵn có do pool đã đầy.
- **Overall deadline:** thời gian tối đa cho toàn bộ bước xác thực gồm queue, connect, retry, response và xử lý.

Không chỉ đặt read timeout 5 giây mà quên queue/pool; một request có thể mất lâu hơn nhiều trước khi bắt đầu đọc. Phải quan sát timeout nào đang được kích hoạt và liệu retry có nhân số request tới IdP không.

### 11.3. Retry không phải luôn tăng tính sẵn sàng

Giả sử 100 request/s tới introspection; nếu tất cả đều retry thêm 3 lần khi IdP 503, IdP có thể nhận **400 request/s** đúng lúc không chịu nổi tải. Giới hạn retry, backoff có jitter và ưu tiên giảm tải khi upstream lỗi. Không retry 401/invalid token chỉ để “đoán” token sẽ tự hợp lệ; đó thường là kết quả xác thực, không phải transient network failure.

Circuit breaker có thể ngừng gửi request tới IdP khi upstream lỗi nặng, bảo vệ tài nguyên. Nhưng **circuit mở không được cấp quyền cho mọi request**. Cách phản hồi là từ chối/đánh dấu authentication dependency unavailable theo chính sách; API có thể chọn 503 khi phân biệt được lỗi upstream, nhưng status cụ thể phụ thuộc exception handler/framework. Không nên tuyên bố Spring Security mặc định luôn trả 503 cho introspection timeout.

### 11.4. HTTPS kết nối tới IdP

Mỗi request introspection không nên tạo TLS connection mới nếu HTTP client và hạ tầng cho phép giữ connection/pooling hợp lệ. Connection reuse giúp giảm network overhead; **không** giảm yêu cầu verify token hay cho phép bỏ qua TLS certificate. Khi chọn HTTP client, giới hạn tổng connections, pending acquisitions, thời gian sống connection, DNS TTL và TLS validation theo policy. Một client custom thiếu truststore hoặc vô hiệu hostname verification là lỗ hổng nghiêm trọng.

## 12. Cache làm giảm latency nhưng phải quản lý thời gian tin cậy

Cùng chữ “cache” có thể mang ý nghĩa rất khác:

| Cache | Có thể có ích gì? | Cảnh báo bảo mật |
| --- | --- | --- |
| JWKS public keys | Giảm network calls, cho phép JWT verify cục bộ | Phải refresh khi key rotation, TTL hợp lý, không nhận key không tin cậy |
| OIDC discovery metadata | Giảm lookup issuer/endpoints | Phải xử lý config/key thay đổi có kiểm soát |
| Directory profile/group | Giảm LDAP/UserInfo remote calls | Dữ liệu role/membership có thể bị thu hồi, cần TTL/invalidation |
| Token introspection result | Giảm remote validation | Cache `active=true` kéo dài thời gian token bị thu hồi vẫn dùng được |
| HTTP session | Không băm password mỗi request, giữ trạng thái login | Bảo vệ session ID, cookie, expiry, fixation, revocation |
| User details | Giảm truy vấn user DB | Account disabled/lock/role change phải phản ánh theo SLA |
| Password verification result | Có thể làm giảm phép hash | **Không tùy tiện cache "raw password đúng"**, dễ tạo rủi ro lưu credential/credential-equivalent; ưu tiên session/token đã thiết kế |

**Không cache nguyên Bearer token ở log, URL, label metrics hoặc plaintext database** để tăng tốc. Nếu cần cache token introspection, phải thiết kế key bảo vệ (có thể dùng giá trị dẫn xuất khóa/HMAC thay vì raw token trong key/log), TTL không vượt chính sách `exp`/revocation, giới hạn kích thước và kiểm soát quyền truy cập bộ nhớ/cache. Token và kết quả "active" đều có thể là dữ liệu nhạy cảm.

### Cache key của JWKS và xoay khóa

Một key mới từ issuer có `kid` khác key trong cache. Việc fetch JWKS có thể tăng latency/timeout khi load hoặc IdP outage. Theo dõi số lần cache miss/refresh/failure; kiểm tra trước các kịch bản key rotation. Không cho phép ký JWT bằng thuật toán tùy ý dựa trên header token chưa tin cậy; chỉ accept algorithms được cấu hình đáng tin.

### Cache kết quả policy và quyền

Một user có JWT hợp lệ nhưng vừa bị thu hồi quyền ADMIN. Nếu app chỉ tin claim roles cũ trong token suốt thời gian token còn hiệu lực, **độ trễ thu hồi quyền** có thể dài bằng TTL token. Đây không phải lỗi performance thuần túy; phải xác định yêu cầu nghiệp vụ về near-real-time revocation và cách kiểm tra trạng thái account/tenant phù hợp.

## 13. Ứng dụng WebFlux: đừng băm password trên event loop

Trong WebFlux, Netty event loop cần phục vụ nhiều kết nối. `PasswordEncoder.matches` là phép toán CPU-bound/synchronous; chạy trực tiếp trong các callback reactive trên event loop có thể tăng response latency của **mọi request chia sẻ event loop**.

Đoạn minh họa **một phương thức service reactive**, giả định encoder và scheduler đã được inject/configure:

```java
public Mono<Boolean> verifyPassword(
        String rawPassword, String storedHash) {

    return Mono.fromCallable(
            () -> passwordEncoder.matches(
                rawPassword, storedHash
            )
        )
        .subscribeOn(passwordHashScheduler);
}
```

Một bean Scheduler có giới hạn (minh họa, **không phải cấu hình mặc định cho mọi máy**) có thể là:

```java
@Bean(destroyMethod = "dispose")
Scheduler passwordHashScheduler() {
    return Schedulers.newBoundedElastic(
        4,    // số thread tối đa trong demo
        100,  // số task chờ tối đa theo scheduler
        "password-hash"
    );
}
```

Các snippet này cần nằm trong dự án có Reactor, Spring Beans và import `Mono`, `Scheduler`, `Schedulers` phù hợp; **không là chương trình biên dịch độc lập**. Chuyển tác vụ sang scheduler giúp không chặn event loop nhưng **không làm phép hash nhẹ CPU**. Bốn thread có thể vẫn quá nhiều nếu Argon2 dùng nhiều RAM; 100 task đang chờ có thể tạo latency tail lớn. Hãy đo và chọn số thread/queue theo CPU/memory budget và tốc độ tải, không dùng các con số trong demo làm chuẩn.

Nếu dùng Spring Security reactive authentication provider riêng, kiểm tra provider thật chạy thế nào; **đừng tạo Mono với từ khóa "reactive" nhưng bên trong gọi blocking password encoder trên event loop**. Với Servlet/MVC, hashing cũng tốn CPU dù thread model khác; chỉ tăng Tomcat threads không tăng số CPU cores.

## 14. Theo dõi thực tế bằng metrics và tracing

### 14.1. Tách metrics theo giai đoạn

Các tín hiệu cần đo:

| Metric/nhóm | Ý nghĩa |
| --- | --- |
| `auth_password_verify_duration_seconds` | p50/p95/p99 verify hash ở từng instance/algorithm |
| `auth_login_total{outcome}` | Tần suất login success/failure/rate-limited mà không chứa username |
| `auth_queue_depth` / `auth_queue_wait_seconds` | Backpressure và số task hashing đang chờ |
| CPU throttling, usage, load | Hash CPU-bound hoặc container bị giới hạn quota |
| Heap/non-heap/RSS, GC | Memory pressure đặc biệt với memory-hard hashing và concurrency |
| `auth_external_call_duration_seconds{operation,provider}` | Độ trễ LDAP/token/introspection/UserInfo/JWKS |
| External timeout/5xx/429 counts | Provider lỗi hay API caller lỗi |
| Connection pool utilization / pending | Cạn connections hoặc đợi queue |
| JWT JWKS cache hit/miss/refresh | Các đột biến khi rotate key |
| Session/token issuance, refresh failure | Tác động lên trải nghiệm đăng nhập và renew |
| Login end-to-end/browser timing | Tách chờ người dùng MFA khỏi HTTP backend calls |

Những tên metric trên là **ví dụ cho hệ thống quan sát do bạn xây**; Spring Boot không tự tạo tất cả các meter này chỉ bằng cách bật `Actuator`. Khi dùng Micrometer/Observability, chọn tên, đơn vị và tags có cardinality thấp theo quy ước của tổ chức.

**Không dùng username, email, client IP gốc, access token, session ID hoặc nguyên exception message làm label metrics.** Có thể dùng operation cố định `password_verify`/`introspect`/`jwks_fetch`, outcome `success`/`invalid`/`timeout`/`dependency_error` và tên provider đã định nghĩa trước.

### 14.2. Đo đúng nơi, không vô tình đo cả network

Nếu đặt timer quanh controller `POST /login`, timer bao gồm parsing request, query DB, password matching, session và response. Muốn biết **work factor** có gây chậm không, đặt một metric riêng quanh `PasswordEncoder.matches` trong authentication provider hoặc thành phần tương ứng (không log raw password). Tương tự, muốn phân biệt network với server IdP, đặt timer cho remote call và quan sát client connection/acquisition/tls/response phases nếu thư viện hỗ trợ.

Một snippet Java minh họa khi đã có `MeterRegistry registry` và `PasswordEncoder encoder`:

```java
boolean verifyAndMeasure(
        String rawPassword,
        String storedHash,
        MeterRegistry registry,
        PasswordEncoder encoder) {

    Timer.Sample sample = Timer.start(registry);
    boolean ok = false;

    try {
        ok = encoder.matches(rawPassword, storedHash);
        return ok;
    } finally {
        sample.stop(
            registry.timer(
                "auth.password.verify",
                "outcome", ok ? "matched" : "not_matched"
            )
        );
    }
}
```

Đây là **snippet phương thức**, cần dependency Micrometer, import `MeterRegistry` và `Timer`; không phải class tự chạy. Nó chỉ dùng label outcome cố định và không ghi mật khẩu/hash. Đối với exception (ví dụ hash format không hợp lệ), nhãn `not_matched` trong snippet có thể gộp cả lỗi và sai password; sản phẩm nên phân biệt `error` nếu yêu cầu quan sát chính xác. Quan trọng hơn, lỗi exception **phải được xử lý/đưa lên** theo chính sách xác thực, không biến thành “login success”.

### 14.3. Theo dõi p95/p99, không chỉ average

Khi dependency chậm ngẫu nhiên, p50 có thể vẫn đẹp nhưng p99 tăng cao và làm login thất bại theo đợt. Đo p95/p99 theo cửa sổ đủ mẫu, phân biệt request mới, cache hit/miss và provider. Một mẫu p99 với 12 lần đo ở bài thực hành không có ý nghĩa thống kê; cần tải mô phỏng đủ lâu và đúng phân phối.

Traces có thể giúp xác định một request đi qua account lookup, password verify, token exchange và business authorization, nhưng **không đặt access token, password, ID token, Cookie hoặc body chứa PII vào spans/baggage**. Request ID và sampling strategy phải được quản lý để không lộ danh tính.

## 15. Thiết kế kiểm thử hiệu năng và độ tin cậy

Một kế hoạch load test có ích phải tách **đo thuật toán** và **đo hệ thống**.

### 15.1. Test password hash riêng

- Chạy benchmark trên instance/container có CPU quota và RAM tương đương production.
- Warm-up JVM/JIT phù hợp, đủ mẫu; đo encode và matches, nhiều strength/work-factor.
- Đo một request đơn lẻ lúc máy rảnh để lấy baseline.
- Đo khi có concurrency 2, 4, 8... trong mức được phép; quan sát saturation thay vì mặc định nhiều thread luôn tốt.
- Với Argon2/scrypt, đo RSS/heap pressure và nguy cơ memory exhaustion.
- Chạy cả test password đúng và sai; logic authentication thật có thể khác ở username không tồn tại.
- Kết thúc bằng work factor phù hợp với mục tiêu security, throughput, SLO và headroom vận hành.

### 15.2. Test API login cục bộ

Dùng tài khoản **test riêng** và request hợp lệ, giới hạn RPS rõ, trong môi trường staging được phép. Kiểm tra:

| Scenario | Mục tiêu |
| --- | --- |
| Login một user hợp lệ | Baseline end-to-end và verify time |
| Sai password | Error không lộ account và không quá tải bất thường |
| User không tồn tại | Giảm khác biệt timing không cần thiết; không tự mở enumeration |
| Burst ngắn | Rate limiter, bounded queue và tài nguyên CPU |
| Sustained load | CPU, p95, p99, retries, login errors |
| Account locked/disabled | Không tạo session/token cho tài khoản không đủ điều kiện |
| Password policy upgrade | Tải hash mới và tương thích hash cũ |
| Cancel/timeout | Không rò request context, thread hoặc password vào log |

Tránh chạy thử credential stuffing trên hệ thống của người khác. Trong bài học, dùng traffic generator nội bộ được cấp quyền và tài khoản giả, không dùng password/credential thật.

### 15.3. Test dependency latency

Dùng **IdP giả lập hoặc môi trường integration được phép** để chủ động tạo các tình huống:

```text
Case A: IdP response bình thường, ví dụ 100 ms
Case B: IdP response chậm bất thường, ví dụ 1500 ms
Case C: TCP connect timeout / TLS handshake lỗi
Case D: IdP HTTP 503 hoặc 429
Case E: Introspection trả active=false
Case F: JWT có kid chưa có trong cache / JWKS refresh
Case G: IdP quay vòng key và resource server nhận key mới
Case H: IdP unreachable khi web đang có session hợp lệ
```

Thời gian và status trong bảng là **giá trị test tự đặt**, không phải latency của một nhà cung cấp. Xác minh ứng dụng:

- Không tự cho qua token không xác minh được.
- Không retry vô hạn, không tạo connection/task queue vô hạn.
- Phân biệt invalid credential với dependency unavailable trong log/metric và HTTP response theo policy.
- Giữ p95/p99 và khả năng phục hồi của các chức năng không phụ thuộc IdP trong giới hạn được thiết kế.
- Đảm bảo session hiện có và token có key cached hành xử đúng chính sách khi IdP outage; không khẳng định mọi request đều thành công hay mọi request đều phải thất bại.
- Có alert và runbook khi external auth trở thành bottleneck.

### 15.4. Kiểm tra kết quả bằng dữ liệu thay vì suy diễn

Ví dụ kết quả **minh họa, không phải phép đo**:

| Thay đổi | Dữ liệu cần xem | Giải thích có thể |
| --- | --- | --- |
| Tăng bcrypt cost | Verify p50/p95, CPU util, login RPS | An toàn offline tăng nhưng số core cần thiết cũng tăng |
| Tăng thread pool bcrypt | CPU, queue wait, GC, p99 | Có thể không tăng throughput khi CPU đã bão hòa |
| Giảm số lần Basic password verify | Login frequency, session/token safety, RPS | Giảm tải hash nếu thiết kế session/token đúng |
| Dùng JWT thay introspection | IdP RPS, JWT validation latency, revocation freshness | Giảm remote validation nhưng đổi mô hình thu hồi |
| Bật JWKS caching hợp lý | Cache hits/miss, key rotation, 401 spike | Giảm network mà vẫn phải refresh đúng |
| Bật caching introspection | IdP RPS, cache TTL, revoke test | Giảm độ trễ nhưng có thể kéo dài quyền của token bị thu hồi |
| Set timeout đúng budget | Request p99, dependency timeout/errors | Không giữ thread mãi; phải fail closed |
| Giới hạn concurrency | Queue length, 429/503, success SLO | Chấp nhận từ chối có kiểm soát thay vì sập toàn hệ thống |

## 16. Các lỗi thường gặp khi tối ưu authentication

### 16.1. Hạ bcrypt work factor chỉ để login nhanh hơn

Tác dụng phụ: chi phí crack hash offline giảm. Cách làm phù hợp là benchmark, sizing, cải thiện rate limiting, giảm số lần băm không cần thiết, tách worker/tài nguyên và đánh giá chính sách hash; nếu cần thay cost vì vận hành, phải có phê duyệt rủi ro và lộ trình nâng cấp.

### 16.2. Dùng SHA-256 hoặc NoOpPasswordEncoder để tăng throughput

**Không được.** Hash nhanh hoặc plaintext không phải password storage an toàn. `DelegatingPasswordEncoder` hỗ trợ migration nhưng không nên cho phép fallback `noop` chỉ để "khỏi lỗi" ở production.

### 16.3. Coi mọi request chậm là do bcrypt

Nếu user đăng nhập qua IdP, ứng dụng Spring có thể không thực hiện hash password; latency có thể nằm ở IdP, MFA, token exchange, JWKS, database account mapping hoặc browser redirect. Đo từng bước thay vì chỉnh encoder vô ích.

### 16.4. Kiểm tra user details và hash password ở mỗi API GET

Với API dùng long-term credential trực tiếp ở mỗi request, throughput sẽ bị giới hạn bởi phép hash. Cân nhắc session/token ngắn hạn được quản lý bảo mật phù hợp, không tự tạo cookie "userId" plaintext.

### 16.5. Chạy BCrypt trực tiếp trên Netty event loop

Gây block event loop. Chuyển công việc CPU/synchronous sang Scheduler/Executor có giới hạn, nhưng phải biết rằng CPU cost vẫn còn và phải giới hạn concurrency/queue.

### 16.6. Cache kết quả "mật khẩu này đúng" không có kiểm soát

Password verification cache có thể trở thành credential-equivalent, làm tăng rủi ro lộ secret, xử lý revoke sai và cache key chứa raw password. Ưu tiên thiết kế session/token đúng thay vì tạo một password-match cache tự phát.

### 16.7. Retry mọi introspection failure

Nhân tải vào IdP khi upstream không khỏe, kéo dài request và tạo queue. Chỉ retry một số lỗi có thể phục hồi theo ngân sách thời gian, không retry invalid token.

### 16.8. Cho phép token khi IdP không trả lời

Đó là **fail open** và phá vỡ authentication boundary. Nếu không xác minh được token theo chính sách, không được cấp quyền. Đặt status/alert thích hợp và runbook phục hồi.

### 16.9. Tin JWT là luôn không cần network

JWKS/issuer metadata có thể cần lấy hoặc refresh. Một key `kid` mới có thể kích hoạt fetch đúng lúc IdP outage. Chạy test key rotation và failure; không bỏ signature validation khi key không tồn tại trong cache.

### 16.10. Chấp nhận mọi JWT vì đã có chữ ký hợp lệ

Phải kiểm tra issuer, audience/recipient, expiration, not-before, scope/authority, token type khi cần; ký số hợp lệ không tự cấp quyền đọc tài liệu của người khác.

### 16.11. Đếm số thread bằng số vCPU một cách máy móc

Password hashing và remote HTTP calls có mô hình tài nguyên khác nhau. Thread budget phải theo CPU/memory/queue và khả năng của runtime. Đồng thời container quota, CPU throttling và hạ tầng chia sẻ ảnh hưởng benchmark rất lớn.

### 16.12. Dùng lỗi 401 cho mọi sự cố mà không quan sát nguyên nhân

Invalid credentials/token là lỗi xác thực; IdP timeout là lỗi dependency. Spring Security/default handler có thể chuyển thành các status khác nhau, nhưng metrics/runbook phải biết nguồn. Không ghi lỗi upstream thành login sai và kích hoạt khóa tài khoản hàng loạt nếu đó là chính sách sai.

## 17. Runbook điều tra khi latency authentication tăng đột ngột

1. **Xác định đường xác thực:** local hash, HTTP Basic, form session, OIDC, JWT hoặc introspection. Đừng bắt đầu bằng thay work factor.
2. **So sánh các nhóm:** login mới với session hiện có, cache hit với miss, endpoint công khai với endpoint Bearer.
3. **Đo triệu chứng:** p50/p95/p99, RPS, 401/403/429/5xx, timeout, queue depth, CPU throttling, RAM/GC.
4. **Nếu CPU tăng cùng password verification:** xem có burst login, rate-limit chưa đủ, hash cost mới hoặc nhiều Basic requests không.
5. **Nếu CPU thấp nhưng auth chậm:** xem DNS/TLS, HTTP client pool, connection reuse, IdP response, LDAP query, retry và timeouts.
6. **Nếu chỉ JWT mới fail:** kiểm tra JWKS endpoint/cache miss/key rotation, issuer/audience và clock skew.
7. **Nếu chỉ opaque token chậm:** đo introspection p95, IdP RPS/429, số client connections, retry amplification và khả năng cache theo chính sách.
8. **Nếu OIDC login chậm nhưng API request thường nhanh:** tách browser redirect/MFA/idp session khỏi token exchange và app account lookup.
9. **Nếu có 401/403 không mong đợi:** đừng bỏ validation; xem token type/expiry/scope, session và policy resource/tenant.
10. **Sau khi giảm sự cố:** kiểm thử lại các trường hợp âm tính, cập nhật cảnh báo và capacity plan, giảm debug logs chứa dữ liệu nhạy cảm.

### Dữ liệu cần lưu và không cần lưu khi điều tra

**Nên lưu:** request ID không nhạy cảm, operation mã cố định, provider/route từ allowlist, latency, status class, loại lỗi và trạng thái cache/queue. **Không nên lưu:** password, hash password trong log, access/refresh/ID token, Authorization header, session cookie, MFA code, raw response IdP chứa PII hoặc client secret.

Việc băm/mã hóa user ID trong log không tự làm dữ liệu thành vô danh; đánh giá mục đích, quyền xem và thời hạn giữ audit theo chính sách dữ liệu.

## 18. Checklist triển khai hệ thống xác thực có hiệu năng và bảo mật

- [ ] Xác định rõ những thời điểm phải kiểm chứng password và những request chỉ cần session/token.
- [ ] Dùng password-hashing adaptive đáng tin; không lưu plaintext/hash nhanh.
- [ ] Benchmark encoder trên CPU/RAM/quota tương đương production; so sánh encode/matches.
- [ ] Tune work factor theo hướng dẫn bảo mật, SLO thực tế và headroom; không chép một số "chuẩn" vô điều kiện.
- [ ] Tính capacity từ login RPS, CPU-seconds/verify, memory per verification và concurrency.
- [ ] Có rate limit, bounded executor/queue, monitoring credential stuffing và fallback vận hành an toàn.
- [ ] Không chạy blocking password hashing trên WebFlux event loop.
- [ ] Phân biệt OIDC web login, JWT resource server, opaque introspection, LDAP và UserInfo calls.
- [ ] Với JWT: xác minh chữ ký, issuer, audience, expiry, scope và JWK rotation; cache keys theo policy.
- [ ] Với introspection: đặt timeout, connection pool, retry budget, circuit breaker và fail-closed policy.
- [ ] Không cache raw credentials/token tùy tiện; đánh giá TTL và độ trễ revocation khi cache kết quả auth.
- [ ] Định nghĩa SLO riêng cho login mới, API authentication và IdP dependency.
- [ ] Quan sát p95/p99, RPS, timeouts, CPU, RAM, queue, cache miss và IdP 429/5xx.
- [ ] Test invalid credentials/token, account disabled, JWKS key rotation, IdP outage và overload.
- [ ] Không log password/token/cookie/client secret hoặc payload IdP nhạy cảm.
- [ ] Sau tối ưu phải kiểm tra lại quyền trên tài nguyên, CSRF/session và các negative security tests.

**Kết luận:** password hashing **cần chậm có chủ đích** để bảo vệ credential khi hash bị lộ, còn remote authentication **không nên chậm ngoài ngân sách** do kết nối, queue hay retry không kiểm soát. Hệ thống an toàn không “tăng tốc” bằng cách bỏ hash hoặc bỏ kiểm tra token; hệ thống an toàn **đo đúng bước, giảm phép xác thực dài hạn không cần thiết, lựa chọn mô hình token/session, giới hạn tài nguyên và xử lý phụ thuộc ngoài theo nguyên tắc fail closed**.

### Tài liệu chính thức và tham khảo

- [Spring Security 6.5 — Password Storage, Adaptive Work Factor và DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Servlet OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Reactive Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
