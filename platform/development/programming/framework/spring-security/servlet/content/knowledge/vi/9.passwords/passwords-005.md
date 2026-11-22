# Chi phí tính toán, giới hạn đầu vào và đo thời gian kiểm tra mật khẩu trong Spring Security Servlet

## 1. Vấn đề cần giải quyết

Đăng nhập bằng mật khẩu cần cân bằng ba mục tiêu có liên hệ với nhau:

1. **Kháng đoán mật khẩu ngoại tuyến:** nếu cơ sở dữ liệu hash bị lộ, mỗi lần thử một mật khẩu phải tốn tài nguyên đáng kể. Không dùng hash nhanh thông thường như SHA-256 đơn lẻ để lưu password.
2. **Thời gian phản hồi và khả năng chịu tải:** mỗi lần gọi `PasswordEncoder.matches(raw, storedHash)` tiêu tốn CPU, và một số thuật toán còn dùng nhiều bộ nhớ. Công việc đủ chậm với kẻ tấn công cũng làm server tốn công với request hợp lệ.
3. **Giới hạn đầu vào và quan sát thời gian:** password quá dài hoặc hàng loạt yêu cầu đăng nhập có thể gây quá tải. Phải đặt giới hạn có chủ đích, đo thực tế trên môi trường đại diện và không biến kết quả đo thành thông tin giúp dò tài khoản.

Trong Spring Security Servlet, việc xác minh mật khẩu của luồng username/password thường do `DaoAuthenticationProvider` phối hợp với `UserDetailsService` và `PasswordEncoder`. `UserDetailsService` tra cứu tài khoản/hash đã lưu; `PasswordEncoder.matches` kiểm tra mật khẩu ứng viên; provider quyết định authentication thành công hay thất bại. Những request dùng bearer token, OAuth2 hoặc provider khác có thể không đi qua bước kiểm tra mật khẩu này.

Bài học tập trung đúng phạm vi **chi phí tính toán, giới hạn đầu vào và đo thời gian kiểm tra mật khẩu**: cách chọn work factor, tránh chi phí ngoài dự kiến, thiết kế giới hạn an toàn và phương pháp đo không tự đánh lừa mình. Các con số minh họa ở đây **không phải cấu hình chuẩn cho mọi hệ thống**.

## 2. Vì sao phải dùng hàm dẫn xuất mật khẩu chậm?

Mật khẩu do con người chọn thường có entropy thấp hơn khóa ngẫu nhiên. Một hash nhanh thông thường cho phép thiết bị chuyên dụng thử số lượng ứng viên cực lớn khi hash bị lộ.

Password hashing có mục tiêu khác: **tăng chi phí mỗi lần đoán mật khẩu**, thường nhờ salt riêng và tham số chi phí có thể điều chỉnh. Các thuật toán hay gặp:

| Thuật toán | Tham số chi phí cần chú ý | Đặc điểm |
| --- | --- | --- |
| BCrypt | `strength` / `cost` / work factor | Tăng cost thêm một mức thường làm số vòng công việc tăng xấp xỉ gấp đôi. Có giới hạn độ dài đầu vào đáng lưu ý. |
| PBKDF2 | Số vòng lặp, PRF (ví dụ HMAC-SHA-256), độ dài kết quả | Chủ yếu tiêu tốn CPU; có trong hệ sinh thái Java/JCA; tăng iterations làm verify chậm hơn. |
| SCrypt | Các tham số công việc và bộ nhớ như `N`, `r`, `p` | Có mục tiêu tiêu tốn bộ nhớ; phải tính chi phí trên mỗi request đồng thời. |
| Argon2id | Bộ nhớ, số lần lặp, parallelism | Có mục tiêu memory-hard; cấu hình cần cân đối RAM/CPU và năng lực triển khai. |

BCrypt, PBKDF2, SCrypt và Argon2id đều có chỗ đứng tùy chính sách, dependency, nền tảng và yêu cầu tuân thủ. **Không có một con số cost tối ưu cho tất cả server**; khả năng chạy trên container nhỏ, thời gian đăng nhập mong muốn, yêu cầu an ninh và mức độ đồng thời phải được đánh giá cùng nhau.

### 2.1. Salt không phải work factor

**Salt** là giá trị ngẫu nhiên riêng cho mật khẩu, thường được tạo tự động khi encode, nhằm tránh hai password giống nhau có cùng dữ liệu hash hoàn toàn và làm việc dùng bảng hash tính trước trở nên kém hiệu quả. Salt không cần giữ bí mật và thường được lưu cùng kết quả encoded.

**Work factor** điều chỉnh mức tài nguyên mỗi phép hash/verify; salt không thay thế work factor. Ngược lại, work factor cao cũng không cho phép bỏ salt.

### 2.2. Encode khi lưu, matches khi đăng nhập

Vòng đời điển hình:

```text
Đăng ký / đổi mật khẩu:
  raw password
      |
      +--> kiểm tra giới hạn theo chính sách
      +--> PasswordEncoder.encode(raw)
      +--> lưu encoded password + metadata cần thiết

Đăng nhập:
  username + raw candidate
      |
      +--> giới hạn request/đầu vào phù hợp
      +--> tra cứu UserDetails + encoded hash
      +--> PasswordEncoder.matches(raw, encodedHash)
      +--> tiếp tục kiểm tra account status / tạo Authentication
```

Không encode password ứng viên rồi so sánh hai chuỗi hash bằng `equals`: với các encoder có salt ngẫu nhiên, hai lần encode cùng password thường sinh hai chuỗi khác nhau. `matches` là API thích hợp để xác minh.

**Không log raw password, hash, token hoặc session identifier** khi debug độ trễ. Nếu cần chẩn đoán, chỉ ghi tham số cấu hình không nhạy cảm (được kiểm soát), kết quả aggregate và thông tin hệ thống.

## 3. Work factor ảnh hưởng đến thời gian và tài nguyên ra sao?

### 3.1. BCrypt cost không phải số mili-giây cố định

Ví dụ Spring Security:

```java
PasswordEncoder encoder10 = new BCryptPasswordEncoder(10);
PasswordEncoder encoder12 = new BCryptPasswordEncoder(12);
```

Đây là **đoạn cấu hình**, cần import `org.springframework.security.crypto.password.PasswordEncoder` và `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`; không phải hai chương trình độc lập.

Con số `10` hoặc `12` là **tham số work factor**, không có nghĩa 10 ms hay 12 ms. Tăng từ 10 lên 12 tăng số vòng công việc theo cấp số hai, nên thời gian thường tăng khoảng bốn lần trong điều kiện so sánh tương tự; nhưng không khẳng định chính xác x4 trên mọi máy, JVM, phiên bản, tải hoặc môi trường container.

Cách đánh giá đúng là **đo `matches` thực tế trên phần cứng triển khai**, gồm cả lúc server có tải. Không sao chép “thời gian BCrypt trên laptop” thành SLA production.

### 3.2. Encode và verify đều tiêu tốn tài nguyên

Việc đăng ký và reset mật khẩu sử dụng `encode`; đăng nhập sử dụng `matches`. Cả hai có thể tốn tài nguyên theo tham số chi phí. Trong hoạt động thực tế, một endpoint đăng nhập có thể bị gọi nhiều lần bởi cùng người dùng hoặc bởi bot, nên **tải verify** đáng quan tâm hơn riêng chi phí encode lúc tạo tài khoản.

Nếu có yêu cầu đăng nhập với tần suất cao, phải tính tổng lượng phép hash chậm mỗi giây, không chỉ đo độ trễ một request đơn lẻ.

### 3.3. Tăng chi phí không đồng nghĩa bảo mật toàn diện

Work factor giúp chống đoán mật khẩu từ hash bị lộ, nhưng **không thay thế**:

- MFA ở những luồng thích hợp;
- HTTPS, cookie/session bảo vệ đúng cách;
- rate limiting, phát hiện abuse và chính sách chống brute-force trực tuyến;
- kiểm soát đăng nhập thất bại và thiết kế thông báo tránh lộ danh sách tài khoản;
- bảo vệ dữ liệu hash trong database/backup;
- kiểm soát việc reset mật khẩu và quản lý session.

Nếu đặt work factor quá cao mà không hạn chế số request xác minh, hệ thống có thể chịu **denial of service** bằng chính phép hash chậm.

## 4. Giới hạn password: phân biệt ký tự, code point và byte UTF-8

Đây là điểm dễ bị bỏ sót khi áp dụng `@Size` hoặc `String.length()`.

Trong Java:

- `String.length()` đếm **UTF-16 code units**, không phải luôn luôn là số ký tự người dùng nhìn thấy.
- `String.codePointCount(0, s.length())` đếm Unicode code points; một biểu tượng có thể vẫn gồm nhiều code points.
- `s.getBytes(StandardCharsets.UTF_8).length` là **số byte UTF-8**; độ dài này có thể khác xa số code points.
- “Ký tự người dùng nhìn thấy” theo grapheme cluster còn là một khái niệm khác, cần xử lý Unicode chuyên biệt nếu chính sách thực sự dựa vào đơn vị này.

Ví dụ minh họa:

| Password string | `length()` | Code points | Byte UTF-8 |
| --- | ---: | ---: | ---: |
| `password123` | 11 | 11 | 11 |
| `éééé` (mỗi ký tự là U+00E9) | 4 | 4 | 8 |
| `😀😀` | 4 | 2 | 8 |
| `a\u0301` (a + combining acute) | 2 | 2 | 3 |

Bảng giả định chuỗi chứa đúng code points đã nêu; Unicode có thể được nhập ở các dạng tương đương về hiển thị nhưng khác byte. **Không âm thầm `trim()`, lower-case hoặc normalize password** ở một điểm mà phía tạo hash không làm giống hệt, vì có thể khiến người dùng không đăng nhập được hoặc làm thay đổi bí mật đã chọn.

### 4.1. Vì sao BCrypt cần chính sách độ dài riêng?

Nhiều cài đặt BCrypt truyền thống chỉ xử lý tối đa khoảng **72 byte** đầu vào, không phải 72 ký tự Unicode. Cách xử lý vượt giới hạn có thể khác nhau giữa phiên bản/implementation; có nơi cắt ngắn, có nơi từ chối. Nếu hai password khác nhau chỉ ở phần bị cắt, điều đó có thể tạo rủi ro nghiêm trọng.

Với một ứng dụng chọn BCrypt trực tiếp, cần kiểm tra **implementation cụ thể** và thiết kế hành vi nhất quán khi đăng ký, đổi và xác minh mật khẩu. Một chính sách ví dụ dễ hiểu là **từ chối trước khi encode/verify nếu UTF-8 vượt 72 byte**. Đây là **chính sách bảo vệ ví dụ**, **không phải khuyến nghị giới hạn password cho mọi ứng dụng**. Một hệ thống cần hỗ trợ passphrase Unicode dài hơn phải lựa chọn thiết kế/thuật toán thích hợp, thay vì cắt ngắn bí mật một cách im lặng.

Không tự ghép `SHA-256(password)` rồi đưa vào BCrypt một cách tùy tiện. Những scheme pre-hash cần được thiết kế và đánh giá kỹ về định dạng, domain separation, Unicode, tương thích và migration.

### 4.2. Giới hạn tổng quát cho input quá lớn

Ngoài đặc thù BCrypt, bất kỳ password verifier nào cũng cần **giới hạn đầu vào thực tế** để tránh request vài MB/GB, làm tốn memory khi parse JSON/form, normalize, cấp phát `String` hoặc sinh buffer, và lặp lại điều đó dưới tải đồng thời.

Đặt giới hạn tại nhiều lớp hợp lý:

1. HTTP ingress/proxy/container: giới hạn kích thước body và số request, chặn dữ liệu bất thường trước khi ứng dụng cấp phát quá nhiều.
2. Validation trong ứng dụng: giới hạn password theo **đơn vị được chỉ định**, ví dụ byte UTF-8 nếu thuật toán có giới hạn byte; cần áp dụng nhất quán ở login/registration/password change.
3. Giới hạn tần suất: theo tài khoản, IP/nguồn tín hiệu phù hợp, kết hợp chính sách chống lạm dụng mà không mở kênh khóa tài khoản tùy ý.
4. Hạn mức tài nguyên: đặt năng lực CPU/RAM hợp lý và bảo vệ hệ thống trước số phép verify cùng lúc.

**Đừng mặc định giới hạn ngắn như 8–20 ký tự tối đa** chỉ vì giao diện đơn giản. Người dùng cần dùng password manager hoặc passphrase dài; giới hạn nên đủ rộng theo yêu cầu bảo mật, đồng thời phù hợp thuật toán đang chọn. Đối với BCrypt trực tiếp, phải giải quyết mâu thuẫn thực tế giữa hỗ trợ password dài và giới hạn 72 byte bằng một thiết kế rõ ràng.

### 4.3. Kiểm tra độ dài nhất quán ở đăng ký và đăng nhập

Nếu đăng ký từ chối >72 byte nhưng đăng nhập lại âm thầm cho qua, hoặc ngược lại, người dùng có thể gặp lỗi khó hiểu; nếu tài khoản legacy từng chứa hash theo chính sách cũ, phải có lộ trình migration phù hợp.

Lưu ý: `@Size(max=72)` với Bean Validation thường kiểm tra **độ dài của chuỗi**, không mặc nhiên là số byte UTF-8. Nếu bắt buộc giới hạn byte, phải có validator tương ứng và kiểm thử các chuỗi Unicode.

## 5. Thiết kế lựa chọn thông số an toàn

Không bắt đầu bằng câu hỏi “nên đặt BCrypt cost = bao nhiêu?” mà bắt đầu bằng **ngân sách tài nguyên và yêu cầu rủi ro**.

| Bước | Việc cần làm | Vì sao |
| --- | --- | --- |
| 1 | Chọn thuật toán/encoder phù hợp với hệ thống và policy bảo mật | Tránh dùng cơ chế hash nhanh hoặc scheme không kiểm chứng. |
| 2 | Xác định độ trễ xác minh cho phép ở tải đại diện | Chức năng login phải đáp ứng thời gian người dùng và SLA. |
| 3 | Chọn dải tham số cost thử nghiệm thay vì cố định ngay | Tăng chi phí bảo vệ nhưng không quá khả năng vận hành. |
| 4 | Đo `matches` cả lúc rảnh, lúc tải thực tế, và ở nhiều mức concurrency | Kết quả một luồng không phản ánh p95/p99 lúc contention. |
| 5 | Theo dõi CPU, GC, RAM, queue, timeout và tỉ lệ error | Thời gian wall-clock chưa nói hết nguyên nhân. |
| 6 | Kết hợp rate limiting/abuse controls trước khi nâng cost | Bảo vệ trước các đợt brute force online/DoS. |
| 7 | Ghi rõ phiên bản encoder, policy password, chiến lược upgrade/migration | Thay thuật toán có thể khiến hash cũ không được nhận diện. |

Với BCrypt, so sánh các mức thử nghiệm như `10` và `12` có ích để hiểu xu hướng, nhưng **không nên coi chúng là mức khuyến nghị cập nhật cho môi trường production**. Phần đo bên dưới chỉ dạy phương pháp; khi triển khai thật cần đối chiếu chính sách bảo mật hiện hành và đo trên máy thực tế.

Với Argon2id/SCrypt, cần theo dõi **bộ nhớ dùng cho mỗi phép verify**. Chẳng hạn nếu một phép hashing tạm cần nhiều MiB và hàng chục request chạy cùng lúc, chi phí RAM tổng có thể thành vấn đề dù CPU không đầy 100%.

## 6. Đo thời gian: đừng đo bằng một lần gọi nanoTime

Một phép benchmark cơ bản thường dùng:

```java
long started = System.nanoTime();
boolean ok = passwordEncoder.matches(rawPassword, storedHash);
long elapsedNanos = System.nanoTime() - started;
```

Đây là **mảnh code nằm trong một chương trình có các biến hợp lệ**, không phải benchmark đầy đủ. `System.nanoTime()` phù hợp để đo **khoảng thời gian tương đối** trong cùng JVM; nó không đại diện cho mốc thời gian thực (wall-clock timestamp).

Một phép đo duy nhất có thể bị tác động bởi:

- JIT compilation, nạp class, khởi tạo thư viện;
- JVM warm-up và garbage collection;
- OS scheduling, CPU frequency scaling, thermal throttling;
- tải của tiến trình khác, giới hạn CPU quota trong container;
- cache/JVM version/provider cụ thể và cấu hình VM;
- khoảng thời gian mạng/controller nếu đo ở HTTP layer thay vì quanh `matches`.

**Không khẳng định timing của encode và matches phải bằng nhau**, và không so sánh công bằng nếu hash test có cost khác nhau hoặc mẫu test bị thay đổi giữa các lượt.

### 6.1. Cách đo tối thiểu trong môi trường lab

1. Tạo một encoded hash **trước** vòng đo; nếu đo `matches` thì không gộp chi phí `encode` vào phép đo.
2. Làm nóng JVM/encoder với nhiều lần verify có kiểm soát.
3. Chạy nhiều lần trên cùng raw password/encoded hash và ghi duration từng phép.
4. Báo median, p95 và các phần trăm phân vị khác khi có đủ mẫu; với rất ít mẫu, p95 chỉ mang tính minh họa.
5. Lặp lại các vòng dưới mức tải đồng thời khác nhau; không trộn số đo của máy local với máy production như thể cùng điều kiện.
6. Tách metrics của request HTTP tổng thể với metrics riêng của `PasswordEncoder.matches`.
7. Không đo hoặc ghi bất kỳ password/hash thật nào vào log.

Một chương trình lab có thể đo 11 mẫu để minh họa **cách tính phân vị**, nhưng **không thể dùng 11 mẫu để phê duyệt SLA, p99 hoặc chống timing attack**. Với benchmark chuyên sâu, cân nhắc công cụ chuẩn như JMH cho microbenchmark và load test ở HTTP layer với số mẫu/tải đủ lớn.

### 6.2. Encode time, verify time và response time khác nhau

```text
t_response =
  network / proxy
  + parsing and request filters
  + user lookup/database/cache
  + password verification (matches)
  + success/failure handling
  + response serialization/network
  + scheduling/queueing delays
```

Thực tế các thành phần có thể chồng lấp hoặc không đơn giản cộng tuyến tính; công thức chỉ minh họa các nguồn thời gian cần tách. **Độ trễ cao của /login không tự chứng minh BCrypt cost quá cao.** Có thể do DB chậm, queue bận, GC, lock contention, cache miss hoặc network.

## 7. Ví dụ runnable Spring Security Crypto + Java 17: benchmark có giới hạn

Ví dụ chạy bằng Maven và Java 17. Nó đo `PasswordEncoder.matches` trên hash BCrypt đã tạo sẵn và dùng một chính sách **demo-only: từ 8 code points đến tối đa 72 byte UTF-8**. Đây không phải định nghĩa password policy bắt buộc. Đoạn mã không chứa credential người dùng thật.

### 7.1. Cấu trúc thư mục

```text
password-cost-lab/
  pom.xml
  src/
    main/java/demo/password/PasswordCostLab.java
    test/java/demo/password/PasswordCostLabTest.java
```

### 7.2. Maven dependencies

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>password-cost-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jcl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây Spring Boot parent chỉ quản lý versions và cấu hình build; lớp chạy là **`main` thuần Java** gọi thư viện Spring Security Crypto, không khởi động web server. `spring-jcl` được thêm tường minh để tránh thiếu thành phần logging khi chạy classpath tối giản.

### 7.3. Chương trình PasswordCostLab.java

File `src/main/java/demo/password/PasswordCostLab.java`:

```java
package demo.password;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordCostLab {

    // Quy tắc DEMO cho BCrypt trực tiếp; không phải chuẩn toàn cục.
    static final int MIN_CODE_POINTS = 8;
    static final int MAX_UTF8_BYTES = 72;

    private PasswordCostLab() {}

    static void validateCandidate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing password");
        }

        int codePoints = raw.codePointCount(0, raw.length());
        int utf8Bytes = raw.getBytes(StandardCharsets.UTF_8).length;

        if (codePoints < MIN_CODE_POINTS || utf8Bytes > MAX_UTF8_BYTES) {
            throw new IllegalArgumentException("Password length not allowed");
        }
    }

    static boolean verify(PasswordEncoder encoder,
                          String raw,
                          String storedEncoded) {
        validateCandidate(raw);
        return encoder.matches(raw, storedEncoded);
    }

    record Timing(long minNanos, long medianNanos, long p95Nanos) {

        double minMs() {
            return minNanos / 1_000_000.0;
        }

        double medianMs() {
            return medianNanos / 1_000_000.0;
        }

        double p95Ms() {
            return p95Nanos / 1_000_000.0;
        }
    }

    static Timing measureVerification(PasswordEncoder encoder,
                                      String raw,
                                      String storedEncoded,
                                      int warmup,
                                      int samples) {
        if (warmup < 0 || samples < 2) {
            throw new IllegalArgumentException("Invalid measurement sizes");
        }

        for (int i = 0; i < warmup; i++) {
            if (!verify(encoder, raw, storedEncoded)) {
                throw new IllegalStateException("Warmup verification failed");
            }
        }

        long[] elapsed = new long[samples];

        for (int i = 0; i < samples; i++) {
            long start = System.nanoTime();
            boolean matched = verify(encoder, raw, storedEncoded);
            elapsed[i] = System.nanoTime() - start;

            if (!matched) {
                throw new IllegalStateException("Verification failed");
            }
        }

        Arrays.sort(elapsed);

        int p95Index = (int) Math.ceil(samples * 0.95) - 1;
        return new Timing(
            elapsed[0],
            elapsed[(samples - 1) / 2],
            elapsed[p95Index]
        );
    }

    public static void main(String[] args) {
        String samplePassword = "Learning42!"; // Chỉ dữ liệu DEMO.
        validateCandidate(samplePassword);

        for (int workFactor : new int[] {10, 12}) {
            PasswordEncoder encoder = new BCryptPasswordEncoder(workFactor);

            // Encode một lần, KHÔNG tính encode vào thời gian matches.
            String storedEncoded = encoder.encode(samplePassword);

            boolean valid = verify(encoder, samplePassword, storedEncoded);
            boolean rejected = !verify(
                encoder, samplePassword + "x", storedEncoded
            );

            System.out.printf(
                "cost=%d valid=%b wrongRejected=%b%n",
                workFactor, valid, rejected
            );

            Timing time = measureVerification(
                encoder, samplePassword, storedEncoded, 3, 11
            );

            System.out.printf(
                "cost=%d verify_ms_min=%.1f median=%.1f p95=%.1f%n",
                workFactor, time.minMs(), time.medianMs(), time.p95Ms()
            );
        }
    }
}
```

Giải thích:

- `validateCandidate` sử dụng `codePointCount` và độ dài byte UTF-8, không chỉ `String.length()`.
- `BCryptPasswordEncoder(workFactor)` tạo hash với cost tương ứng; `storedEncoded` được tạo trước phép đo `matches`.
- `verify` kiểm tra giới hạn input rồi gọi đúng `matches`; mẫu wrong password có độ dài hợp lệ và bị từ chối.
- `warmup=3`, `samples=11` là số nhỏ để **quan sát cơ chế**, không đủ để chứng nhận production p95.
- `Arrays.sort` sắp xếp 11 durations, lấy min, median và chỉ số p95 minh họa. `System.nanoTime` đo elapsed time.
- Không in hash hoặc plaintext password. Chuỗi hardcoded chỉ có ý nghĩa dữ liệu demo; không đưa password thật vào source code.

### 7.4. Kiểm thử tính đúng đắn, không kiểm thử ngưỡng thời gian

File `src/test/java/demo/password/PasswordCostLabTest.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordCostLabTest {

    @Test
    void rightAndWrongPasswordsHaveDifferentResults() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);
        String encoded = encoder.encode("CorrectPass9!");

        assertTrue(PasswordCostLab.verify(
            encoder, "CorrectPass9!", encoded
        ));

        assertFalse(PasswordCostLab.verify(
            encoder, "IncorrectPass9!", encoded
        ));
    }

    @Test
    void rejectsTooShortCandidate() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);

        assertThrows(IllegalArgumentException.class, () ->
            PasswordCostLab.verify(encoder, "short", "not-used")
        );
    }

    @Test
    void rejectsUnicodeCandidateExceedingUtf8Limit() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);

        // 40 lần 'é' = 40 code points, 80 byte UTF-8.
        String tooLong = "é".repeat(40);

        assertThrows(IllegalArgumentException.class, () ->
            PasswordCostLab.verify(encoder, tooLong, "not-used")
        );
    }

    @Test
    void measuresSamplesWithoutTimingThresholdAssertion() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);
        String raw = "AnotherPass7!";
        String encoded = encoder.encode(raw);

        PasswordCostLab.Timing result =
            PasswordCostLab.measureVerification(
                encoder, raw, encoded, 1, 3
            );

        assertTrue(result.minNanos() >= 0);
        assertTrue(result.medianNanos() >= result.minNanos());
        assertTrue(result.p95Nanos() >= result.medianNanos());
    }
}
```

Các test không assert “phải chạy dưới 100 ms” vì thời gian trên CI có thể thay đổi lớn. Mục đích là xác nhận kiểm tra đúng/sai mật khẩu, giới hạn độ dài Unicode và cấu trúc thuật toán đo.

### 7.5. Lệnh chạy và kết quả

Trong thư mục `password-cost-lab`, cài JDK 17+ và Maven:

```bash
mvn test
mvn -q compile exec:java -Dexec.mainClass=demo.password.PasswordCostLab
```

`mvn test` dự kiến có **4 test pass** nếu dependencies và môi trường sẵn sàng. Với chương trình main, các dòng logic có dạng:

```text
cost=10 valid=true wrongRejected=true
cost=10 verify_ms_min=<số đo> median=<số đo> p95=<số đo>
cost=12 valid=true wrongRejected=true
cost=12 verify_ms_min=<số đo> median=<số đo> p95=<số đo>
```

Hai dòng chứa `<số đo>` ở trên là **mẫu format**, không phải stdout chính xác. Giá trị thực đo thay đổi theo môi trường; không được bịa một con số và gọi đó là kết quả benchmark. Dòng `valid=true wrongRejected=true` dự kiến ổn định nếu quá trình thực thi thành công.

**Lưu ý về hiệu năng khi chạy:** Work factor 12 có thể khiến lệnh hoàn thành chậm hơn 10 đáng kể. Chỉ chạy benchmark có kiểm soát, không chạy stress test không giới hạn trên server sản xuất.

## 8. Đo một request hay đo cả hệ thống? Load test mới trả lời năng lực vận hành

### 8.1. Thời gian CPU và thời gian response

Một phép `matches` có thể tiêu tốn nhiều CPU. Khi nhiều request cùng đến, thời gian chờ CPU/thread pool làm tăng response latency, dù một phép verify riêng lẻ vẫn có thời gian xử lý tương tự.

Có thể ước lượng tải **rất sơ bộ**:

```text
CPU-seconds per second ≈
  requests_verified_per_second × CPU_seconds_per_verification
```

Ví dụ **giả định** mỗi verify tiêu tốn 0,10 CPU-second và có 40 lần verify/giây, tổng nhu cầu là khoảng 4 CPU-seconds mỗi giây. Đây là phép tính ngân sách thô, **không đồng nghĩa chắc chắn cần đúng 4 vCPU**, vì còn context switching, CPU limits, worker concurrency, chi phí khác và chênh lệch giữa CPU time với elapsed time.

Một cách nhìn khác là định luật Little: ở trạng thái ổn định, số operation đang nằm trong hệ thống xấp xỉ tốc độ đến nhân thời gian chúng ở trong hệ thống. Nhưng phải dùng **tổng thời gian gồm chờ**, không nhầm nó với thời gian CPU của riêng BCrypt.

### 8.2. Mô hình tải nên kiểm thử

- **Đăng nhập bình thường:** một lượng nhỏ người dùng hợp lệ.
- **Sai mật khẩu nhiều lần:** nhiều verify thất bại vẫn tốn tài nguyên, nhằm cản brute force offline nhưng cần bảo vệ online.
- **Username không tồn tại:** đo riêng để phát hiện khác biệt đáng chú ý giữa lookup miss và password mismatch, không đo để tạo oracle cho client.
- **Burst:** số request tăng nhanh khi một sự kiện gây tải đột biến.
- **Tải phối hợp:** login + request ứng dụng + background job + DB, trên tài nguyên gần giống production.
- **Đa instance:** đo trên cùng loại container và CPU quota với kế hoạch mở rộng thực tế.
- **Tác vụ tốn RAM:** nếu dùng Argon2/SCrypt, theo dõi RSS, native memory, OOM và mức đồng thời.

Kết quả cần có: p50/p95/p99 **response latency**, thông lượng hoàn thành, error rate, CPU utilization, memory, GC, độ dài hàng đợi và tần suất throttling. Không chỉ báo trung bình.

### 8.3. Biện pháp chống lạm dụng

Với endpoint login, nên có rate limiting và cơ chế phát hiện abuse tại vị trí phù hợp để ngăn tài nguyên verify bị cạn kiệt. Các tiêu chí có thể kết hợp IP, account, thiết bị, rủi ro và tín hiệu khác; không dựa duy nhất vào một key dễ spoof hoặc dễ gây khóa tài khoản của người khác.

Không vô điều kiện tạo password hash mới cho mọi login sai để “cân bằng timing”: chi phí đó có thể giúp attacker làm hệ thống quá tải. Khi xử lý user không tồn tại, cần xem cơ chế giảm lộ timing của authentication provider và toàn bộ response pipeline, đồng thời thiết kế kiểm soát lưu lượng.

## 9. Timing side channel: đo hiệu năng không phải chứng minh constant-time

Cần phân biệt hai mối lo:

**Đo độ trễ vì hiệu năng:** muốn biết verify mất bao lâu khi đổi cost, tăng tải hoặc thay phần cứng.

**Rò rỉ thông tin qua thời gian:** nếu trường hợp “user tồn tại” và “user không tồn tại” luôn có đặc điểm thời gian khác biệt, kẻ tấn công có thể tìm cách suy luận thông tin. Còn có sự khác biệt do DB/cache, phản hồi HTTP, exception handling và network.

Nhiều phép so sánh mật mã cố gắng tránh khác biệt theo nội dung bí mật, nhưng không thể chỉ nhìn một đoạn code hoặc vài kết quả `System.nanoTime` rồi tuyên bố toàn bộ endpoint đăng nhập “constant-time”.

Thực hành hữu ích:

1. Trả thông báo lỗi chung phù hợp để không lộ “tên đăng nhập tồn tại”.
2. Tránh đường đi quá khác biệt giữa lookup thành công/thất bại nếu nó mở ra kênh dò tài khoản.
3. Sử dụng các cơ chế authentication/provider được hỗ trợ thay vì tự viết compare bằng `equals`.
4. Không so sánh thời gian hợp lệ/sai password rồi chủ quan kết luận an toàn từ 5 hoặc 10 mẫu.
5. Kết hợp giới hạn tốc độ, logging an toàn và monitoring; không dựa vào “sleep ngẫu nhiên” như giải pháp duy nhất.
6. Đánh giá side channel tại lớp có thể quan sát bởi kẻ tấn công (response cuối), không chỉ đo thời gian của hàm Java.

Thời gian xác minh **không bao giờ nên xuất thẳng ra response** để client đo dễ dàng hơn. Dữ liệu đo có thể đưa vào metrics nội bộ với tên metric và tags an toàn, giới hạn cardinality; không đưa password/username vào label của metric.

## 10. Chiến lược nâng work factor khi ứng dụng đã có user

Không nên đổi hash trong database bằng cách lấy chuỗi hash cũ rồi `encode(hashCu)`: việc đó tạo hash của hash, không có password gốc nên không tương thích với login thông thường.

Spring Security có khả năng nhận diện tham số/format thông qua encoder tương ứng và API `PasswordEncoder.upgradeEncoding(String encodedPassword)`. Khi thiết kế migration, có thể xem xét **rehash sau một lần xác thực thành công** bằng password gốc mà người dùng vừa cung cấp, nếu đã được xác minh và chính sách cho phép.

Quy trình khái niệm:

```text
User đăng nhập bằng password hợp lệ
      |
      v
Đọc hash/định dạng đã lưu
      |
      v
PasswordEncoder.matches(raw, storedHash)
      |
      +-- false -> từ chối, không thay hash
      |
      +-- true  -> nếu hash/cost cũ cần nâng cấp:
                       encode(raw) bằng cấu hình mới
                       lưu hash mới theo transaction phù hợp
                   rồi hoàn tất đăng nhập
```

**Đây là sơ đồ chính sách, không phải mặc định mọi provider đều tự cập nhật DB**. Khi dùng `DaoAuthenticationProvider`, có thể tích hợp `UserDetailsPasswordService` để cập nhật encoded password sau xác thực thành công tùy cấu hình. Trường hợp password cũ/định dạng legacy phải có chiến lược tương thích và kiểm thử cụ thể.

### 10.1. DelegatingPasswordEncoder và tiền tố id

Spring Security cung cấp `DelegatingPasswordEncoder` để chọn thuật toán dựa vào id trong chuỗi encoded, ví dụ `{bcrypt}...`. Đó là **định dạng nhận diện thuật toán**, không phải nơi chứa plaintext.

Một cách tạo encoder theo defaults của Spring Security:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

Đoạn này cần import `PasswordEncoder` và `PasswordEncoderFactories` từ `org.springframework.security.crypto.password`. Defaults thay đổi theo phiên bản; kiểm tra cấu hình encoder dùng để tạo mới hash và các id legacy được chấp nhận. Không giả định hash trần `$2a$...` sẽ tự được nhận diện bởi mọi `DelegatingPasswordEncoder` khi thiếu `{id}`.

### 10.2. Đừng nâng work factor không có kế hoạch

Tăng cost đột ngột có thể tạo đột biến CPU vào giờ cao điểm. Nên thử trên staging giống production, xem năng lực chịu tải, rollout từng bước, theo dõi failures/latency và chuẩn bị phương án xử lý các hash cũ.

Nếu dùng hashing memory-hard, ngoài CPU cần theo dõi RAM khi xác minh nhiều request đồng thời. “Encode lâu hơn” không nhất thiết đồng nghĩa “verify ổn định hơn” nếu tài nguyên bị tranh chấp.

## 11. Tích hợp chính sách giới hạn với Servlet/Spring Security

Trong ứng dụng Servlet, input có thể đến từ form login, JSON API đăng ký, hoặc controller đổi password. Cần phân biệt **validation của nghiệp vụ tài khoản** với **cơ chế xác thực của framework**.

### 11.1. Đăng ký và đổi mật khẩu

Controller/service đăng ký có thể gọi validator password đã thống nhất trước khi `PasswordEncoder.encode`. Điều quan trọng là kiểm tra:

- Không âm thầm cắt ngắn password.
- Không tự `trim` / lower-case password nếu không có chính sách nhất quán.
- Giới hạn byte phù hợp thuật toán, đặc biệt khi BCrypt trực tiếp.
- Không lưu plaintext hay phát tán hash tới client.
- Không quyết định work factor chỉ từ input của người dùng.
- Có rate limiting cho endpoint đăng ký/đổi mật khẩu nếu có thể bị spam.

### 11.2. Đăng nhập do UsernamePasswordAuthenticationFilter xử lý

Nếu dùng form login mặc định, request có thể được xử lý **trước controller** bởi `UsernamePasswordAuthenticationFilter`. Vì thế **validator đặt chỉ trong registration controller không tự bảo vệ login filter**. Để giới hạn một cách nhất quán cần thiết kế điểm kiểm tra trước khi hash verification, ví dụ cấu hình một authentication filter/converter phù hợp hoặc validator tại authentication boundary với chính sách rõ ràng.

Không viết một filter tự đọc request body hai lần mà làm hỏng Servlet input stream. Không thay `DaoAuthenticationProvider` bằng một lớp tự so sánh hash. Nếu có nhiều security chains, phải áp dụng policy ở đúng chain mà request login đi qua.

Đồng thời cần giữ chính sách HTTP body size ở proxy/container và hạn chế tần suất request; validator Java không thể tránh mọi chi phí đã xảy ra trước khi controller/filter chạm tới nó.

### 11.3. Không chặn passphrase hợp lệ bằng quy tắc thiếu cơ sở

Một tiêu chuẩn mật khẩu tốt thường ưu tiên password dài, password manager, kiểm tra password đã bị lộ và MFA phù hợp, thay vì ép đủ số ký tự đặc biệt. Với giới hạn thuật toán BCrypt, **phải giải thích rõ constraint và cân nhắc thuật toán khác** nếu yêu cầu nghiệp vụ phải hỗ trợ passphrase Unicode dài. Ví dụ giới hạn 72 byte trong bài chỉ là cách giữ demo nhất quán với giới hạn BCrypt truyền thống.

## 12. Phân tích các tình huống thực tế

| Tình huống | Nhận định đúng | Việc nên làm |
| --- | --- | --- |
| BCrypt cost tăng từ 10 lên 12; login chậm hơn | Số vòng công việc tăng theo cấp số hai, nhưng ms thực phụ thuộc máy và tải | Đo lại trên môi trường triển khai, theo dõi p95/p99 và CPU |
| Một password có 60 ký tự `é` vượt 72 byte | Độ dài ký tự và byte UTF-8 khác nhau | Kiểm tra byte, chọn policy/thuật toán nhất quán, không cắt ngắn im lặng |
| Người dùng nhập password 10 MB | Có thể gây cấp phát và hashing/parse quá mức | Giới hạn request body sớm, validate có giới hạn hợp lý, rate limit |
| `@Size(max=72)` pass nhưng BCrypt xử lý thiếu dữ liệu | Validator có thể đo độ dài `String`, không đo byte | Dùng byte-aware validator hoặc thiết kế khác phù hợp |
| BCrypt hash lại có salt khác | Đó thường là hành vi mong đợi | Dùng `matches`, không so sánh hai kết quả encode |
| Đo một verify trong local thấy 50 ms | Không chứng minh mức này tại tải cao | Warm-up, nhiều mẫu, benchmark dưới concurrency |
| Username không tồn tại nhanh hơn sai password | Có thể là kênh dò tài khoản | Kiểm tra provider/lookup, response, rate limit và thử nghiệm side-channel cẩn trọng |
| Hệ thống đăng nhập gặp 503 khi brute force | Chi phí xác minh có thể gây quá tải | Rate limiting, capacity planning, giám sát queue/resource |
| Migration cost tạo đột biến CPU | Hash mới đắt hơn, việc nâng cấp tập trung có thể làm tăng tải | Rollout từng bước, rehash khi phù hợp và đo/giới hạn |
| API dùng JWT nhưng nhóm vẫn benchmark BCrypt trên mọi request | Có thể không đúng đường xác thực thực tế | Xác định auth mechanism trước khi tối ưu |
| Argon2/SCrypt chạy ổn một request nhưng OOM khi 50 request | Memory-hard dùng bộ nhớ đáng kể | Đo peak RSS và concurrency, đặt quota an toàn |

## 13. Checklist review và chẩn đoán sự cố

Trước khi đưa policy mật khẩu lên production, trả lời được các câu hỏi sau:

**Thuật toán và lưu trữ**

- Đang dùng `PasswordEncoder` nào, version nào, tham số cost nào? Encoded string có đủ thông tin nhận diện thuật toán/cost không?
- Salt có được tạo theo encoder phù hợp không? Có đang dùng hash nhanh đơn thuần hoặc mật khẩu plaintext không?
- Khi đăng nhập có gọi `matches` trên hash đã lưu hay vô tình encode rồi so sánh chuỗi?
- Có chiến lược nâng cost/algorithm cho password cũ, mà không làm mất khả năng đăng nhập không?

**Giới hạn đầu vào**

- Có giới hạn request body trước khi cấp phát tốn kém không?
- Giới hạn password dùng **byte UTF-8**, code points hay kiểu khác? Đã ghi rõ đơn vị chưa?
- Chính sách nhập password Unicode dài và giới hạn BCrypt được xử lý thế nào?
- Đăng ký, login, đổi password và reset password có đồng nhất về cách nhận/validate password không?
- Có tránh tự cắt ngắn/`trim`/normalize password mà người dùng không hay biết không?

**Đo lường và vận hành**

- Thời gian đo là `matches`, encode, user lookup hay response HTTP cuối?
- Có JVM warm-up, đủ mẫu và đo lúc tải đồng thời không?
- Có theo dõi p50/p95/p99, CPU, RAM, GC, queue, throttling và error rate không?
- Có rate limiting và giám sát abuse cho login không?
- Có tránh đưa password, hash, token, username vào metrics/log không?
- Đã thử mất cân bằng thời gian giữa user-not-found và bad-password mà không tạo user-enumeration oracle chưa?

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao không nên lưu `SHA-256(password)` đơn thuần thay vì BCrypt/Argon2/PBKDF2/SCrypt có cấu hình phù hợp?

**Đáp án:** Hash nhanh làm thử nhiều password ứng viên rẻ hơn trong tình huống cơ sở dữ liệu bị lộ. Password hashing chuyên dụng đưa salt và chi phí tính toán/ghi nhớ vào phép dẫn xuất để tăng chi phí mỗi lần đoán.

**Câu 2.** BCrypt cost = 12 có phải verify đúng 12 ms không?

**Đáp án:** Không. Đó là work factor, không phải đơn vị thời gian. Cần đo trên máy và mức tải thực tế.

**Câu 3.** Hai password đều dài 50 ký tự có chắc có cùng số byte UTF-8?

**Đáp án:** Không. ASCII, ký tự có dấu và emoji thường có số byte khác nhau. Ngoài ra Java `String.length()` đếm UTF-16 code units.

**Câu 4.** Nếu password hợp lệ nhưng app chạy `encode(raw)` rồi so hash mới với hash DB bằng `equals`, điều gì có thể xảy ra?

**Đáp án:** Hai lần encode có thể dùng salt ngẫu nhiên khác nhau, dẫn đến chuỗi hash khác nhau dù raw giống nhau. Phải dùng `PasswordEncoder.matches(raw, storedHash)`.

**Câu 5.** Tại sao chỉ benchmark `matches` với một request duy nhất không đủ quyết định cost production?

**Đáp án:** Cần xét JVM/JIT, nhiều mẫu, CPU/RAM quota, các request cạnh tranh và end-to-end latency. Một request khi rảnh không đại diện cho throughput/p95/p99 khi tải.

**Câu 6.** Để tránh ảnh hưởng hiệu năng, có nên bỏ kiểm tra mật khẩu với username không tồn tại và trả lỗi tức thì không?

**Đáp án:** Phải xem tác động bảo mật; khác biệt timing có thể giúp dò tài khoản. Dùng provider/cơ chế được hỗ trợ, phản hồi lỗi thích hợp và giới hạn lưu lượng, không tự tạo đường đi tiết lộ thông tin.

**Câu 7.** Vì sao chỉ tăng cost không phải cách chống brute force online đầy đủ?

**Đáp án:** Kẻ tấn công có thể gửi nhiều request, gây tốn tài nguyên và DoS. Phải kết hợp rate limiting, monitoring, MFA và controls khác.

**Câu 8.** Có thể nâng hash từ work factor cũ lên mới mà không cần password gốc không?

**Đáp án:** Không thể tái tạo hash mới của password gốc chỉ từ hash cũ một cách đúng quy trình; thường cần lần đăng nhập hợp lệ để có password gốc tạm thời rồi rehash, hoặc một quy trình reset/password migration khác.

## 15. Ghi nhớ quan trọng

- `PasswordEncoder.matches` là bước kiểm tra mật khẩu điển hình của `DaoAuthenticationProvider`; cost bảo vệ trước đoán mật khẩu nhưng đồng thời tiêu hao tài nguyên server.
- Work factor **không phải milliseconds**. Các thông số của BCrypt, PBKDF2, SCrypt, Argon2id phải được chọn sau khi đo trên phần cứng và tải đại diện.
- Kiểm soát kích thước request và độ dài password **theo đơn vị chính sách thực sự yêu cầu**; với BCrypt trực tiếp đặc biệt chú ý giới hạn khoảng 72 byte UTF-8 trong nhiều implementation.
- Đừng âm thầm cắt ngắn, trim, đổi chữ hoa/thường hoặc normalize password không đồng nhất giữa đăng ký và xác minh.
- Đo `matches` sau warm-up bằng nhiều mẫu, nhìn median/p95/p99 cùng throughput, CPU và RAM. Độ trễ lab không tự chứng minh constant-time hay SLA.
- Kết hợp rate limiting và chống lạm dụng, tránh user enumeration/timing oracle; không ghi credential hoặc hash vào logs/metrics.
- Khi tăng cost/đổi thuật toán, lên kế hoạch versioning, rehash và capacity rollout; không encode lại chính chuỗi hash cũ.
