# upgradeEncoding và thời điểm thay đổi tham số băm

> **Phạm vi:** Spring Security – authentication, phần **Nâng cấp mật khẩu**. Bài này đi sâu vào **quyết định lúc nào thay đổi thuật toán hoặc tham số băm mật khẩu**, cách `PasswordEncoder.upgradeEncoding` nhận biết hash lạc hậu, và cách triển khai thay đổi mà không phá đăng nhập, không hạ cấp độ an toàn và không ghi đè một lần đổi mật khẩu đồng thời. Ví dụ sử dụng Java 17+ và Spring Boot Servlet. Các tham số số học nêu trong ví dụ chỉ dùng để quan sát hành vi, **không phải cấu hình khuyến nghị cho mọi hệ thống production**.

## 1. Vấn đề không phải chỉ là tăng một con số

Giả sử ứng dụng đang lưu password bằng BCrypt cost 10. Sau một thời gian vận hành, nhóm bảo mật đo được rằng phần cứng hiện tại có thể chịu cost 12, và quyết định cập nhật chính sách băm cho **password mới** và **password đã lưu**. Nếu chỉ sửa:

```java
// Trước
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

// Sau
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
```

thì chuyện gì xảy ra?

- Một password mới được `encode` theo encoder mới sẽ có BCrypt cost 12.
- Một hash BCrypt cost 10 đã lưu vẫn có thể được `matches` xác minh bằng encoder cost 12, vì hash mang thông tin cost/salt của chính nó.
- **Hash cũ trong database không tự thay đổi** khi bạn deploy mã mới.
- `upgradeEncoding(oldHash)` có thể báo `true`, nhưng nó **không đọc mật khẩu thô và không ghi database**.
- Để rehash password cũ, ứng dụng cần có raw password **đã được xác minh hợp lệ** và một writer cập nhật hash an toàn.
- Người không đăng nhập trong thời gian dài có thể vẫn giữ hash cost 10 đến lúc đổi/reset password hoặc đi qua quy trình migration phù hợp.

Vì vậy cần phân biệt **thời điểm chính sách có hiệu lực với password mới**, **thời điểm hash hiện có được nâng cấp**, và **thời điểm chính sách cũ không còn được phép dùng để xác minh**.

### Ba mốc thời gian khác nhau

```text
T0: Policy hiện tại là BCrypt cost 10.
        |
T1: Deploy chính sách mới, encode password MỚI ở cost 12.
        |  DB vẫn có nhiều hash cost 10.
        |
T2: User đăng nhập đúng -> có raw password đã xác minh.
        |  upgradeEncoding(hash cũ) == true
        |  encode(raw) theo cost 12, cập nhật hash có điều kiện.
        |
T3: Hầu hết hash đã chuyển; xử lý những tài khoản chưa quay lại.
        |
T4: Đánh giá ngừng hỗ trợ các thuật toán/format legacy theo policy.
```

T1, T2, T3 và T4 thường không xảy ra cùng lúc. Nếu nhầm chúng là một sự kiện, có thể gây lỗi đăng nhập hàng loạt hoặc đánh giá sai mức độ hoàn thành của chương trình nâng cấp password.

## 2. Hợp đồng PasswordEncoder.upgradeEncoding

Interface `org.springframework.security.crypto.password.PasswordEncoder` cung cấp:

```java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

default boolean upgradeEncoding(String encodedPassword) {
    return false;
}
```

Đây là **chữ ký rút gọn** để đọc hiểu API, không phải file Java cần tự implement. Tùy phiên bản có các annotation nullability bổ sung.

| Method | Ý nghĩa | Có raw password? | Có tự ghi DB? |
| --- | --- | --- | --- |
| `encode(raw)` | Tạo hash mới theo policy của encoder | Có | Không |
| `matches(raw, stored)` | Kiểm tra raw password với hash đang lưu | Có | Không |
| `upgradeEncoding(stored)` | Đánh giá hash đã lưu có cần rehash không | **Không** | **Không** |

Đặc điểm cần nhớ:

1. `upgradeEncoding` chỉ xem **hash đã lưu** và policy bên trong encoder; nó **không xác thực** người gọi.
2. Implementation mặc định của interface trả `false`. Một custom encoder không override sẽ không đánh dấu gì cần nâng cấp, kể cả khi tổ chức mới thay đổi chính sách.
3. `true` là **đề xuất nâng cấp**, không phải lệnh cập nhật dữ liệu và không phải dấu hiệu password đã đúng.
4. `false` chỉ có nghĩa “encoder này không yêu cầu upgrade theo kiểm tra hiện tại”; không phải chứng nhận bảo mật tuyệt đối cho hash.
5. Với format không hợp lệ, implementation có thể từ chối hoặc ném lỗi. Đừng dùng `upgradeEncoding` như một parser để đoán thuật toán tùy ý.
6. Nếu password null/không có, phải tuân hợp đồng implementation/version; không dùng giá trị null để mở một đường bypass authentication.

**Phân biệt quan trọng:** Hệ thống có thể buộc tất cả user đổi password theo chính sách sự cố mà không cần `upgradeEncoding==true`. Ngược lại, `upgradeEncoding==true` không tự động có nghĩa cần yêu cầu user nhập password mới; thường chỉ cần rehash bằng password cũ đã được xác minh tại lần login tiếp theo.

## 3. Tham số băm là những gì?

“Tham số băm” không chỉ là cost BCrypt. Tùy thuật toán, có thể là:

- **BCrypt:** strength/log rounds, salt ngẫu nhiên và định dạng/version như `$2a$`, `$2b$`, `$2y$`.
- **PBKDF2:** số iterations, thuật toán PRF, độ dài salt và khóa dẫn xuất, các lựa chọn phiên bản encoder.
- **scrypt:** các tham số công việc/bộ nhớ và parallelization, salt, output length.
- **Argon2:** memory cost, iterations, parallelism, salt, output length, version.
- **DelegatingPasswordEncoder:** id của encoder dùng để tạo password **mới**, cùng mapping của những id legacy được phép xác minh.
- **Chính sách ứng dụng:** thời điểm rehash, điều kiện rollback, độ trễ tối đa, bảo vệ đồng thời và thời hạn buộc reset.

Không phải encoder nào cũng biểu diễn đủ mọi tham số trong cùng một chuỗi. Không phải implementation `upgradeEncoding` nào cũng kiểm tra **mọi thuộc tính** mà nhóm bảo mật quan tâm. Khi thay đổi version hoặc thuật toán, cần đọc contract encoder cụ thể và kiểm chứng bằng test trên hash thật.

### BCrypt có cost nằm trong hash

Một chuỗi BCrypt hợp lệ thường bắt đầu theo dạng:

```text
$2a$10$...
$2a$12$...
```

Những dấu `...` trong khối này **không phải hash hợp lệ**, chỉ minh họa vị trí cost. Số `10` và `12` là log rounds. Vì hash mang cost/salt, encoder được cấu hình cost 12 vẫn có thể xác minh hash BCrypt cost 10 mà không cần biết salt ngoài chuỗi đã lưu.

Đây là lý do có thể đổi cấu hình **tạo hash mới** trước, sau đó nâng dần các hash cũ khi user đăng nhập.

### Tham số càng cao chưa chắc hệ thống càng an toàn toàn diện

Tăng work factor làm mỗi lần hash/verify đắt hơn. Nhưng hệ thống có thể bị quá tải CPU nếu nhiều login đồng thời, nhất là HTTP Basic gửi password mỗi request. Độ trễ tăng quá mức còn có thể khuyến khích người vận hành bỏ bớt bước xác thực. **Cần benchmark và threat model**, thay vì chọn mức lớn nhất có thể cấu hình.

## 4. Khi nào nên thay đổi tham số băm?

Không có một lịch cố định kiểu “cứ sáu tháng tăng BCrypt cost một lần” phù hợp với mọi hệ thống. Những tín hiệu hợp lý để **xem xét** thay đổi gồm:

1. **Khuyến cáo mới về thuật toán/cost** từ nguồn bảo mật đáng tin hoặc yêu cầu tuân thủ.
2. **Năng lực phần cứng thay đổi:** CPU, RAM, kiến trúc máy và tải trung bình cho phép tăng chi phí hashing.
3. **Rủi ro ngoại tuyến tăng:** threat model cho rằng hash có thể bị lộ, mật khẩu yếu dễ bị đoán, hoặc thuật toán legacy không còn đáp ứng mục tiêu.
4. **Thay đổi hạ tầng:** chuyển sang nhiều node, công suất authentication cao hơn, giới hạn container CPU, thay đổi latency budget.
5. **Khả năng khai thác/phiên bản thư viện:** cảnh báo bảo mật liên quan thuật toán hoặc implementation.
6. **Đã đo được chi phí thực tế:** benchmark p50/p95/p99 trong điều kiện tải và số login đồng thời gần với production.
7. **Có kế hoạch nâng cấp dữ liệu:** storage format, fallback read path, writer, telemetry và rollback được kiểm thử.
8. **Có phương án hỗ trợ tài khoản không quay lại:** reset password, notification có kiểm soát hoặc migration có xác minh.

Một thay đổi cost nên được ghi nhận như một **quyết định chính sách có phiên bản**: ví dụ `bcrypt-policy-v2`, ngày áp dụng, thuật toán được phép, tham số, lý do, hiệu năng dự kiến, cách rollout, và quy tắc xử lý hash tồn đọng.

### Khi chưa nên rollout ngay

- Database writer chưa có hoặc ghi được nhưng không chống race với password reset.
- Encoder mới không thể xác minh những hash legacy hiện đang có.
- Thời gian xác minh trên phần cứng production vượt ngân sách p95/p99 hoặc tạo nguy cơ DoS.
- Hệ thống có nhiều instance nhưng việc hỗ trợ format mới/cũ không đồng bộ.
- Chưa có canary, telemetry hoặc đường khôi phục khi login thất bại.
- Chưa kiểm tra policy đối với SSO, tài khoản kỹ thuật, user vô hiệu hóa và user không đăng nhập lâu ngày.

Đừng vì một phép benchmark đơn lẻ trên laptop mà ép toàn bộ lưu lượng production sang cost mới.

## 5. Phân biệt lúc cấu hình đổi và lúc hash dữ liệu đổi

Một thay đổi trong code:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

chỉ xác định encoder **đang được cấu hình**. Nó không chạy một migration SQL trên bảng tài khoản. `PasswordEncoder` là một đối tượng mã hóa/đối chiếu, không biết repository user.

Cũng cần tách:

- **Write policy:** mật khẩu mới từ đăng ký/đổi/reset sẽ được tạo bằng encoder/cost nào?
- **Verify compatibility:** những hash cũ nào còn được chấp nhận để xác minh?
- **Upgrade eligibility:** trong một authentication thành công, hash nào nên được nâng?
- **Persistence:** lưu hash mới như thế nào mà không phá trạng thái account?
- **Retirement policy:** khi nào ngừng chấp nhận format cũ và hướng user chưa migrate qua kênh reset?

Có thể nâng **write policy** ngay ở T1 và giữ **verify compatibility** trong giai đoạn T1–T4. Cần tránh hai thái cực: tắt verify cũ quá sớm làm user không đăng nhập được; hoặc giữ verify cho thuật toán không còn an toàn vô thời hạn mà không có kế hoạch xử lý.

## 6. Ví dụ quyết định upgrade với BCrypt

Giả sử policy cũ có cost 10; policy mới cost 12:

```java
PasswordEncoder legacy = new BCryptPasswordEncoder(10);
PasswordEncoder current = new BCryptPasswordEncoder(12);

String stored = legacy.encode("demo-password");

System.out.println(current.matches("demo-password", stored)); // true
System.out.println(current.upgradeEncoding(stored));           // true

String upgraded = current.encode("demo-password");

System.out.println(current.matches("demo-password", upgraded)); // true
System.out.println(current.upgradeEncoding(upgraded));          // false
```

Đây là **mảnh Java trong method**, với import `PasswordEncoder` và `BCryptPasswordEncoder`, không phải file đầy đủ có `main`. Kết quả boolean ổn định với hash BCrypt hợp lệ.

### Không hạ cấp nếu policy bị rollback

Nếu có hash cost 12 nhưng một instance tạm dùng encoder cost 10:

```java
PasswordEncoder lowerPolicy = new BCryptPasswordEncoder(10);
String strongHash = new BCryptPasswordEncoder(12)
        .encode("demo-password");

System.out.println(lowerPolicy.matches("demo-password", strongHash)); // true
System.out.println(lowerPolicy.upgradeEncoding(strongHash));          // false
```

Điều này minh họa rằng BCrypt encoder cost thấp hơn **không đánh dấu hash cost cao hơn là cần upgrade chỉ vì khác cost**. Tuy nhiên, khi rollback cấu hình tạo hash mới, password mới trên instance cũ có thể được tạo ở cost thấp hơn. Do đó, một **rollback code** phải có chính sách write riêng để tránh tự hạ cấp mức bảo vệ vừa triển khai.

### upgradeEncoding không tự so sánh password

Thứ tự này sai:

```java
// SAI: không được dùng input chưa xác minh để đổi password.
if (encoder.upgradeEncoding(storedHash)) {
    repository.save(encoder.encode(passwordFromUntrustedRequest));
}
```

Các biến và repository là minh họa. Đoạn sai đã bỏ qua `matches` và account checks; nó có thể cho attacker đổi password chỉ qua một request đăng nhập sai.

## 7. Lộ trình rollout an toàn theo nhiều giai đoạn

Một kế hoạch mẫu gồm các pha sau. Các giai đoạn **có thể điều chỉnh theo hạ tầng**; không phải chuẩn bắt buộc của Spring Security.

### Pha A — Thống kê và chuẩn bị

- Thống kê phân bố thuật toán, id và cost hiện có **không lấy mẫu raw password**.
- Đánh giá mức an toàn được chấp nhận và thời hạn loại bỏ thuật toán quá cũ.
- Benchmark encoder mới trên hạ tầng giống production; đo CPU, memory, p95/p99.
- Kiểm tra khả năng xác minh mọi format đang tồn tại bằng cấu hình mới.
- Viết `UserDetailsPasswordService`/writer hoặc một flow migration có quyền ghi hợp lệ.
- Kiểm thử thất bại, replay, concurrency, password reset, DB outage và cache.
- Định nghĩa fallback/rollback **không tự hạ cấp** hash đã nâng.

### Pha B — Canary và đổi chính sách ghi

- Triển khai decoder/verification hỗ trợ cả hash cũ và mới lên các instance trước khi tạo lượng lớn hash theo format mới.
- Sau khi tương thích được xác nhận, bật encoder mới cho đăng ký/đổi/reset password.
- Bật lazy upgrade trên một nhóm nhỏ user hoặc một phần instance **chỉ khi backend writer đã đúng**.
- Theo dõi login failures, error type, latency, CPU, số lượng update và xung đột concurrent password changes.
- Bảo đảm mọi instance có thể xác minh hash do instance khác tạo.

### Pha C — Tăng dần rehash on login

- Khi user đăng nhập thành công với hash cũ, `upgradeEncoding` quyết định cần rehash.
- `PasswordEncoder.encode(raw đã xác minh)` tạo hash mới theo policy.
- Writer cập nhật hash có điều kiện, tránh ghi đè password reset.
- Cache/replia được invalidate hoặc xử lý theo consistency contract.
- Không dùng worker nền có quyền lấy plaintext password; plaintext không nên được lưu lại để chờ xử lý sau.

### Pha D — Xử lý tài khoản chưa di trú

- Lọc những account còn hash cũ sau một khoảng thời gian.
- Với hash còn chấp nhận được, có thể tiếp tục lazy migration theo policy.
- Với hash quá cũ/không được phép xác minh, buộc reset password qua một kênh xác minh đáng tin.
- Không gửi raw password, hash hoặc token reset trong log/analytics.
- Chỉ ngừng hỗ trợ legacy format khi đã có đường khôi phục cho account còn tồn.

### Pha E — Đóng chương trình nâng cấp

- Kiểm tra thống kê còn lại theo algorithm/cost.
- Xóa mapping legacy không còn cần, cập nhật runbook/recovery.
- Đánh giá latency/CPU sau migration.
- Giữ lịch đánh giá định kỳ chính sách băm và những advisory mới.

**Lưu ý:** Đổi cost và nâng hàng triệu tài khoản không nên chạy đồng loạt chỉ bằng một cron job cố “rehash hash cũ” — không có raw password thì job không tạo ra hash của password gốc được.

## 8. Tích hợp trong DaoAuthenticationProvider

Với Spring Security Servlet username/password, `DaoAuthenticationProvider` có các điểm tích hợp chính:

1. `UserDetailsService.loadUserByUsername` trả hồ sơ gồm encoded password, trạng thái account và authorities.
2. `PasswordEncoder.matches` xác minh credential.
3. Các điều kiện xác thực cần thiết được kiểm tra; thất bại không được cấp authenticated `Authentication`.
4. Ở đường thành công, provider có thể đánh giá `PasswordEncoder.upgradeEncoding(storedHash)`.
5. Nếu cần nâng và đã cấu hình `UserDetailsPasswordService`, provider băm lại raw password hợp lệ rồi gọi `updatePassword(user, newEncodedPassword)`.
6. Writer phải lưu encoded hash mới đúng account và trả `UserDetails` đã cập nhật.

Các API cần chú ý:

```java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(userDetailsService);

provider.setPasswordEncoder(passwordEncoder);
provider.setUserDetailsPasswordService(passwordWriter);
```

Đây là **mảnh cấu hình minh họa**, các biến `userDetailsService`, `passwordEncoder` và `passwordWriter` phải là bean/instance phù hợp.

**Nếu không cung cấp writer**, `upgradeEncoding` là tín hiệu không đủ để thay dữ liệu. Nếu custom provider tự viết, không thể mặc định Spring Security tự thực hiện lazy rehash; phải thiết kế và kiểm thử riêng.

### UserDetailsPasswordService nhận encoded, không nhận plaintext

Hợp đồng:

```java
UserDetails updatePassword(UserDetails user, String newPassword);
```

Tên `newPassword` trong API dùng để chỉ **password đã được encoded** khi `DaoAuthenticationProvider` gọi. Writer không được encode lại chuỗi này. Hệ thống dùng JPA hoặc kho nghiệp vụ phải có transaction/compare-and-set đúng, rồi trả `UserDetails` phù hợp.

### Không lấy credential từ Authentication sau login

`ProviderManager` có cơ chế xóa credentials khỏi kết quả đã xác thực. Lazy rehash cần diễn ra tại điểm provider còn có raw password đã được trình bày, trước khi credential bị loại bỏ. Không tìm plaintext trong `SecurityContext` hoặc session rồi tái băm về sau.

## 9. Ví dụ Spring Boot Java 17+: mô phỏng thời điểm nâng cost

Ví dụ là một ứng dụng Spring Boot Servlet có **Spring Web/MVC** và **Spring Security**, sử dụng một user in-memory nhưng mô hình hóa writer bằng compare-and-set. Mục tiêu là thấy rõ:

- Hash đã lưu ban đầu ở cost 10.
- Policy hiện tại yêu cầu cost 12.
- Đăng nhập sai **không thay hash**.
- Đăng nhập đúng → `DaoAuthenticationProvider` gọi `UserDetailsPasswordService` và thay hash an toàn.
- Lần đăng nhập đúng tiếp theo **không rehash nữa**.
- Đầu ra chỉ gồm boolean/cost, không in password hash hoặc credential.

**Chuẩn bị:** Tạo project Java 17+ từ Spring Initializr với Spring Boot Servlet, dependencies Spring Web (trên Spring Boot 4 có starter `spring-boot-starter-webmvc`) và Spring Security. Chọn phiên bản Spring Boot còn được hỗ trợ. Tạo file duy nhất **`src/main/java/com/example/policychange/PolicyChangeApplication.java`**.

```java
package com.example.policychange;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PolicyChangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(PolicyChangeApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            PolicyAccountStore store,
            PasswordEncoder currentEncoder,
            AuthenticationManager manager) {

        return args -> {
            String before = store.storedHash();

            System.out.println("stored-cost-before="
                    + before.substring(4, 6));
            System.out.println("needs-upgrade-before="
                    + currentEncoder.upgradeEncoding(before));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "an", "wrong"));
            } catch (BadCredentialsException ex) {
                System.out.println("wrong-login=REJECTED");
            }

            System.out.println("unchanged-after-wrong="
                    + before.equals(store.storedHash()));

            Authentication authenticated = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "an", "training-password"));

            String after = store.storedHash();
            System.out.println("authenticated="
                    + authenticated.isAuthenticated());
            System.out.println("stored-cost-after="
                    + after.substring(4, 6));
            System.out.println("needs-upgrade-after="
                    + currentEncoder.upgradeEncoding(after));
            System.out.println("password-still-matches="
                    + currentEncoder.matches("training-password", after));

            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "an", "training-password"));

            System.out.println("no-repeat-update="
                    + after.equals(store.storedHash()));
        };
    }
}

// Một account dùng AtomicReference để minh họa cập nhật có điều kiện.
// Trong production, thay bằng DB transaction / optimistic lock / CAS.
final class PolicyAccountStore
        implements UserDetailsService, UserDetailsPasswordService {

    private final AtomicReference<String> currentHash;

    PolicyAccountStore() {
        PasswordEncoder previous = new BCryptPasswordEncoder(10);
        this.currentHash = new AtomicReference<>(
                previous.encode("training-password"));
    }

    String storedHash() {
        return currentHash.get();
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (!"an".equals(username)) {
            throw new UsernameNotFoundException("Unknown account");
        }

        return User.withUsername("an")
                .password(currentHash.get())
                .authorities("ROLE_USER")
                .build();
    }

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newEncodedPassword) {

        // Writer nhận hash mới, không encode lại lần thứ hai.
        boolean updated = currentHash.compareAndSet(
                user.getPassword(), newEncodedPassword);

        if (!updated) {
            throw new IllegalStateException(
                    "Password was changed by another request");
        }

        return User.withUsername(user.getUsername())
                .password(newEncodedPassword)
                .authorities(user.getAuthorities())
                .build();
    }
}

@Configuration(proxyBeanMethods = false)
class PolicySecurityConfiguration {

    @Bean
    PolicyAccountStore accountStore() {
        return new PolicyAccountStore();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    AuthenticationManager authenticationManager(
            PolicyAccountStore store, PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(store);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class PolicyDemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }
}
```

### Vì sao ví dụ tách các trách nhiệm?

**`PolicyAccountStore`** là kho user giả lập. Nó nạp `UserDetails` cho `DaoAuthenticationProvider` và cung cấp `updatePassword` để đổi hash. `AtomicReference.compareAndSet(oldHash, newHash)` minh họa rằng writer **không ghi đè nếu stored hash đã bị thay đổi**. Đây chỉ là một account và một JVM; production phải có transaction/CAS ở nguồn dữ liệu thực và quy tắc xử lý xung đột.

**`PasswordEncoder`** hiện tại là BCrypt cost 12. Nó xác minh được hash cost 10 nhưng đánh dấu cần upgrade. Kết quả rehash có salt ngẫu nhiên và không nên xuất ra log.

**`DaoAuthenticationProvider`** được gắn cả reader, encoder và writer. Nếu chỉ tạo `new BCryptPasswordEncoder(12)` mà không cấu hình `setUserDetailsPasswordService`, bản ghi cũ không tự biến thành cost 12.

**`ProviderManager`** thực thi authentication; ở lần password sai nó ném `BadCredentialsException`. Một authentication thành công còn phụ thuộc các account checks; demo tạo user active để tập trung vào thay đổi tham số băm.

**`CommandLineRunner`** kiểm tra trước–sau ngay lúc startup để người học có kết quả xác định, tránh phải đọc raw hash. Khi server sẵn sàng nhận HTTP, store đã được nâng cấp cost 12. Vì data in-memory, restart sẽ tạo lại hash cost 10 rồi nâng cấp lại.

### Chạy bằng build tool

Với project Maven được Spring Initializr tạo:

```bash
./mvnw spring-boot:run
```

Hoặc Gradle:

```bash
./gradlew bootRun
```

Trên PowerShell, dùng `.\mvnw.cmd spring-boot:run` hoặc `.\gradlew.bat bootRun`. Mã nguồn có import Spring nên không thể biên dịch bằng một lệnh `javac` đơn lẻ nếu thiếu classpath/dependencies.

Các dòng do `CommandLineRunner` in ra (ngoài log Spring Boot) có kết quả dự kiến:

```text
stored-cost-before=10
needs-upgrade-before=true
wrong-login=REJECTED
unchanged-after-wrong=true
authenticated=true
stored-cost-after=12
needs-upgrade-after=false
password-still-matches=true
no-repeat-update=true
```

**Không có một chuỗi hash cố định trong output** vì BCrypt tạo salt ngẫu nhiên. Các boolean và cost mới là thứ demo kiểm tra.

Thử thêm HTTP Basic sau khi ứng dụng khởi động:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:training-password http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i http://localhost:8080/me
```

Hai body thành công lần lượt:

```text
pong
principal=an
```

Hai request sau thường nhận HTTP **401** theo cơ chế Basic. Header/body lỗi phụ thuộc version/configuration; Basic thường có `WWW-Authenticate` challenge. Basic dùng Base64, không mã hóa bí mật; production phải sử dụng HTTPS và không có password hardcode.

## 10. Vì sao writer phải chống ghi đè password mới?

Một nguy cơ nghiêm trọng của lazy rehash là **một request đăng nhập cũ ghi đè thao tác đổi/reset password vừa hoàn thành**.

Diễn biến:

```text
Thời điểm  | Login L                      | Reset password R
-----------|------------------------------|----------------------
t0         | Đọc hash H1                  |
t1         | Xác minh password cũ         |
t2         |                              | User reset -> lưu H2
t3         | Rehash password cũ -> H3     |
t4         | Ghi mù quáng H3              |
           |                              | H2 bị ghi đè: nguy hiểm
```

Nếu H3 ghi đè H2, password mà user vừa reset có thể không còn hiệu lực, còn password cũ lại hợp lệ. Vì vậy writer phải bảo đảm **chỉ cập nhật nếu hash nguồn vẫn là hash đã được xác minh**, hoặc dùng cơ chế khóa/phiên bản tương đương.

Ví dụ SQL cập nhật có điều kiện:

```sql
UPDATE accounts
SET password_hash = :new_encoded_hash,
    version = version + 1
WHERE account_id = :account_id
  AND password_hash = :old_verified_hash;
```

Đây là SQL minh họa, không phải câu lệnh mặc định của Spring Data. Cần kiểm tra số hàng update. Nếu 0, hash đã thay đổi giữa lúc đọc và lúc ghi; không cố update lại bằng H3. Khi dùng JPA, có thể dùng `@Version`/optimistic locking hoặc row lock phù hợp transaction và isolation.

### Không dùng username do request khai để quyết định bản ghi cần ghi

`UserDetailsPasswordService.updatePassword` nhận một `UserDetails` được provider sử dụng. Với hệ thống có user ID bất biến, writer nên map tới **internal account ID đáng tin**, không nhận `userId` từ query/header rồi cập nhật hash. Multi-tenant cần kiểm tra đúng phạm vi danh tính; một username có thể chỉ duy nhất trong một tenant.

### Không băm hai lần encoded value

`newEncodedPassword` đã là hash do encoder tạo. Sai:

```java
// SAI khi newEncodedPassword đã được encode:
account.setPasswordHash(encoder.encode(newEncodedPassword));
```

Làm vậy hash chính chuỗi hash, khiến password thật không khớp. Cần giữ hợp đồng rõ: trong luồng đổi password do user chọn, `encode(rawNewPassword)`; trong `UserDetailsPasswordService`, **lưu newEncodedPassword được cung cấp**.

## 11. Đổi thuật toán hoặc format: DelegatingPasswordEncoder

Một hệ thống có thể từng dùng nhiều thuật toán hoặc phiên bản encoder. `DelegatingPasswordEncoder` chọn encoder từ prefix **`{id}`**:

```text
{id}encodedPassword

Ví dụ hình dạng:
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

Các dấu `...` chỉ minh họa định dạng. Không dùng giá trị đó như hash thật.

`idForEncode` xác định format tạo hash **mới**. `matches` dùng id có trong stored hash để tìm encoder tương ứng. Nhờ vậy có thể triển khai khả năng **đọc hash cũ** trước khi bắt đầu ghi hash mới.

Một cấu hình minh họa:

```java
PasswordEncoder delegating = new DelegatingPasswordEncoder(
        "bcrypt-v2",
        Map.of(
                "bcrypt-v1", new BCryptPasswordEncoder(10),
                "bcrypt-v2", new BCryptPasswordEncoder(12)));
```

Đây là **mảnh code** cần import `PasswordEncoder`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder` và `java.util.Map`. Nếu dữ liệu cũ có prefix `{bcrypt-v1}`, mapping cho phép xác minh nó; hash mới sẽ bắt đầu bằng `{bcrypt-v2}`. Những id này là **quy ước minh họa của ứng dụng**, không phải id mặc định của Spring Security. Bạn cũng có thể dùng cùng id `bcrypt` và thay strength encoder con, khi đó `upgradeEncoding` của BCrypt con xét cost.

### Vì sao cần rollout decoder trước encoder?

Nếu server A bắt đầu tạo `{bcrypt-v2}` nhưng server B vẫn chỉ biết `{bcrypt-v1}`, người dùng có thể login thành công ở A rồi thất bại ở B do format không được nhận diện. Khi dùng rolling deployment hoặc blue/green, nên bảo đảm mọi instance đang phục vụ traffic đều có **khả năng verify mới/cũ** trước khi bắt đầu ghi format mới.

### Hash không có {id} thì sao?

Một database cũ có thể lưu `$2a$10$...` trực tiếp. `DelegatingPasswordEncoder` không tự biết id nếu thiếu prefix; mặc định có thể ném `IllegalArgumentException` khi `matches` không tìm được mapping. Có thể lập kế hoạch gắn prefix với **hash đã xác nhận đúng format** hoặc một decoder legacy giới hạn, có thời hạn loại bỏ. Không mặc định coi chuỗi không prefix là plaintext.

### Không bật fallback yếu để cứu đăng nhập

Mở rộng decoder để “nếu không nhận được id thì so sánh plaintext” có thể tạo lỗ hổng nghiêm trọng. Không dùng `NoOpPasswordEncoder` cho dữ liệu production không có migration được phê duyệt. Nếu một thuật toán legacy không còn an toàn, đôi khi **buộc reset password** là lựa chọn đúng hơn tiếp tục chấp nhận mọi hash cũ.

## 12. Khi nào upgradeEncoding không phản ánh toàn bộ policy?

`upgradeEncoding` là API hữu ích nhưng có giới hạn phạm vi:

- Encoder hiện tại có thể chỉ đánh giá **work factor** mà không quyết định mọi chính sách bảo mật.
- Một việc kiểm tra credential bị lộ hoặc yêu cầu MFA không thuộc trách nhiệm `upgradeEncoding`.
- Một user bị disabled/locked không được coi là đủ điều kiện login chỉ vì hash cần upgrade.
- Một policy yêu cầu reset password do nghi ngờ tài khoản bị lộ là quy trình riêng, không phải chỉ tăng cost.
- Hash mạnh hơn về cost nhưng tạo bởi thuật toán/implementation không còn được chấp nhận cần được đánh giá theo tiêu chí khác.
- Một custom encoder có default `upgradeEncoding=false` có thể bỏ sót nhu cầu migration nếu không override.

Vì thế nên định nghĩa **source of truth của password hashing policy** ở cấu hình có version, cùng những bài test đầu vào hash cũ/mới và những trường hợp bắt buộc reset. Đừng chỉ dựa trên số lượng `upgradeEncoding=true` để khẳng định mọi password đã đáp ứng yêu cầu tổ chức.

## 13. Benchmark trước khi đổi tham số

Một nhóm vận hành nên đo xác thực password trên phần cứng gần với production, với loại workload đúng:

| Hạng mục | Cần đo/kiểm soát |
| --- | --- |
| Độ trễ verify/hash | Trung bình, p95, p99 theo cost/algorithm |
| Tải đồng thời | Số login cùng lúc, CPU, memory, queue depth |
| HTTP Basic vs session | Basic có thể verify password trên nhiều request |
| Token/SSO | Không phải request nào cũng cần password hashing |
| Chi phí lazy rehash | Một login nâng cấp có thể tốn **verify cũ + encode mới** |
| Scaling | Giới hạn CPU/container và cold starts |
| Rate limiting | Ngăn attacker gây CPU exhaustion |
| Database writes | Update hash, lock/transaction, cache invalidation |
| User experience | Thời gian login và lỗi ngắt phiên |
| Rollback | Có thể tiếp tục verify hash đã nâng cấp không |

**Độ trễ ở lần login cần upgrade khác lần login bình thường.** Nếu rehash được thực hiện đồng bộ trong authentication, lần đầu user đăng nhập sau rollout có thể tốn thêm chi phí encode mới và ghi DB. Nên đo tần suất các login như vậy ở canary.

Để xác định cost, không cần đăng 10.000 raw password ra log hoặc chạy benchmark ngay trên tài khoản production. Dùng dữ liệu test, đo riêng hashing workload và thận trọng với môi trường đa tenant/nhiều CPU architecture.

### Có nên làm rehash bất đồng bộ?

Không nên chỉ “ném raw password vào queue” để nâng cấp sau; plaintext có thể bị lưu lâu hơn, bị log hoặc đi qua service không đủ bảo vệ. Luồng mặc định an toàn hơn thường là rehash tại điểm authentication còn có raw password đã xác minh, ghi trong transaction/operation có kiểm soát. Nếu chọn một thiết kế async đặc biệt, phải có đánh giá security, lifecycle secrets, ordering và điều kiện cập nhật không ghi đè reset mới.

## 14. Đo tiến độ migration mà không làm lộ hash

Một chương trình nâng cấp cần biết:

- Tỷ lệ account theo thuật toán/prefix/cost trước và sau rollout.
- Số lần `upgradeEncoding=true` **trong một authentication thành công**.
- Số lần writer update thành công, xung đột CAS và lỗi database.
- Số lần login bị từ chối do hash không tương thích.
- Latency verify + upgrade và tỷ lệ timeout.
- Tỷ lệ account không login trong thời gian dài vẫn còn hash legacy.
- Lượng password reset bắt buộc và tỷ lệ hỗ trợ thành công.

Để đo, chỉ cần metadata thuật toán/cost hoặc tên policy, không cần đưa **raw password hoặc hash đầy đủ** vào log analytics. Không log Basic Authorization header, session cookie hoặc bearer token. Hash đã băm vẫn là dữ liệu nhạy cảm vì có thể dùng để tấn công offline khi bị lộ.

Một mẫu log khái niệm an toàn hơn:

```json
{
  "event": "password_hash_upgrade",
  "policy_from": "bcrypt-cost-10",
  "policy_to": "bcrypt-cost-12",
  "result": "updated",
  "request_id": "correlation-id"
}
```

Đây là **mẫu cấu trúc**, không phải một log bắt buộc; `correlation-id` phải được tạo từ cơ chế tracing phù hợp. Audit chi tiết theo account ID chỉ trong hệ thống có kiểm soát truy cập. Cần cân nhắc retention của dữ liệu bảo mật.

### Phân biệt các kết quả writer

| Kết quả | Ý nghĩa | Xử lý phù hợp |
| --- | --- | --- |
| `updated` | Hash được cập nhật từ expected-old sang new | Success, invalidate cache nếu cần |
| `not_needed` | Hash đã đạt policy | Không ghi |
| `concurrent_change` | Hash đã thay đổi giữa đọc và ghi | Không ghi đè, phân loại/điều tra |
| `storage_unavailable` | DB không khả dụng | Không báo đã nâng cấp, xử lý authentication theo policy |
| `unsupported_hash` | Format/thuật toán không được hỗ trợ | Không fallback yếu, hướng tới reset/migration |
| `auth_failed` | Password hoặc điều kiện authentication thất bại | **Không rehash** |

Đừng trộn `auth_failed` và `storage_unavailable` thành cùng loại “password sai” trong telemetry nội bộ, dù response public cần tránh lộ chi tiết tài khoản.

## 15. Rollback và tính tương thích giữa các phiên bản

Rollback code không nên có nghĩa **rollback password hash** hoặc hạ cấp cost. Khi cần quay lại phiên bản ứng dụng trước, phải bảo đảm phiên bản ấy vẫn đọc được hash do rollout mới tạo.

### Những kịch bản cần kiểm thử

**Kịch bản A — BCrypt chỉ tăng cost:** một instance cũ có encoder BCrypt cost 10 thường vẫn `matches` được stored hash cost 12. Nhưng nếu instance cũ vẫn cho phép tạo password mới ở cost 10, cần chặn ghi hạ cấp hoặc áp một policy write độc lập.

**Kịch bản B — Thay đổi {id}:** phiên bản cũ không có mapping cho `{bcrypt-v2}` sẽ không matches hash mới. Phải triển khai decode compatibility trước, hoặc rollback sang một phiên bản cũ **có hỗ trợ decoder mới**.

**Kịch bản C — Chuyển hẳn thuật toán:** không thể giả định decoder cũ hỗ trợ Argon2/PBKDF2 mới. Cần test dữ liệu tương thích, tiến trình rollout và cách khôi phục bằng password reset nếu thiếu support.

**Kịch bản D — Đồng thời thay đổi password và rehash:** writer cũ không có CAS có thể ghi đè password reset. Không bật rehash trên instance chưa có concurrency guard.

**Kịch bản E — Cache stale:** một instance đọc hash cũ từ replica/cache trong khi hash đã được nâng ở primary. Nếu rehash lại không cần thiết, nó có thể gây thêm ghi, xung đột hoặc tạo lỗ hổng đồng thời. Có chiến lược invalidation và read consistency rõ ràng.

### Những thứ không nên làm lúc rollback

- Đặt cost encoder thấp hơn rồi **rehash toàn bộ hash mạnh thành yếu**.
- Xóa prefix `{id}` một cách bừa bãi, làm decoder không nhận biết thuật toán.
- Tắt `PasswordEncoder.matches` và dùng so sánh plaintext “tạm thời”.
- Vô hiệu hóa account status hoặc MFA để khắc phục lỗi login.
- Đổi password user bằng password mặc định hoặc lưu raw để có thể khôi phục.
- Tiếp tục ghi hash format mới khi một phần fleet chưa thể xác minh nó.

## 16. Người dùng nào có thể không nâng cấp qua login?

Không phải mọi account đều có cơ hội cung cấp raw password:

- **Tài khoản lâu không đăng nhập:** hash cũ sẽ còn cho đến khi user login/reset.
- **Tài khoản đang disabled/locked:** một lần login bị từ chối không nên được dùng để cấp phiên hoặc cập nhật hash như thể authentication thành công.
- **Tài khoản dùng SSO/OIDC:** ứng dụng có thể không sở hữu password; identity provider chịu trách nhiệm hashing của họ.
- **Tài khoản có API token:** request bearer token không chứa password người dùng, nên không có raw password để rehash.
- **Tài khoản service:** có thể dùng client secret/certificate thay password thường; cần policy credential riêng.
- **Tài khoản có hash legacy quá yếu/không đọc được:** phải có chương trình reset được xác minh.
- **User vừa reset password:** password mới thường đã được encode theo policy hiện tại; không cần upgrade hash cũ.
- **Multi-tenant:** mức độ ưu tiên migration và tính hợp lệ thuật toán có thể thay đổi theo tenant, nhưng không được chuyển quyền/khóa user sai phạm vi.

Đừng viết một batch job đọc oldHash rồi gọi `encode(oldHash)` để “nâng cấp tất cả”; nó tạo ra hash của **chuỗi hash cũ**, không phải hash của password người dùng. Khi không có raw password hợp lệ, phải dựa vào lần login tương lai hoặc quy trình reset/cấp credential mới.

## 17. Ma trận kiểm thử khi đổi chính sách

| Test | Setup | Kết quả mong đợi |
| --- | --- | --- |
| Tương thích BCrypt | Stored cost 10, verifier cost 12 | `matches(raw, oldHash)=true` |
| Dấu hiệu upgrade | Stored cost 10, policy cost 12 | `upgradeEncoding(oldHash)=true` |
| Đã nâng | Stored cost 12, policy cost 12 | `upgradeEncoding(newHash)=false` |
| Password sai | Raw password khác | Không xác thực, **không ghi hash mới** |
| Password đúng + writer | Old hash hợp lệ | Rehash và lưu hash cost 12 |
| Login đúng lần sau | Stored đã cost 12 | Không lặp update |
| Không có writer | Provider chỉ có encoder | Không thể giả định hash được lưu mới |
| Account locked | Password có thể đúng | Không cấp phiên; không nâng qua login bị từ chối |
| Reset đồng thời | Reset ghi H2 trước lazy rehash H3 | Không ghi đè H2 |
| CAS thất bại | Hash nguồn thay đổi | Không retry bằng old raw một cách mù quáng |
| Fleet hỗn hợp | New instance tạo format mới | Mọi instance phục vụ traffic phải verify được |
| Hash không có {id} | Delegating không có fallback | Không tự chấp nhận plaintext |
| Unknown algorithm | Stored id không được mapping | Fail closed/khôi phục hợp lệ |
| DB writer lỗi | Xác thực đúng nhưng update không được | Không báo update thành công, xử lý theo policy |
| User lâu không đăng nhập | Hash cũ còn tồn | Kế hoạch reset/inactive account rõ |
| JWT-only request | Không có raw password | Không rehash tự động |
| Cost cao dưới tải | Nhiều login đồng thời | Latency/CPU trong giới hạn hoặc rollback an toàn |
| Username/email đổi | Account ID bất biến | Writer cập nhật đúng account không dựa vào input tự khai |
| Test log | Có sự kiện nâng cấp | Không ghi password/hash/token |
| Security review | Dependency thay đổi | Kiểm tra API/advisory tương ứng |

### Bài thử đơn giản không cần khởi động web server

Đây là mảnh code Java cần import `PasswordEncoder`/`BCryptPasswordEncoder` và đặt trong một method; có thể chạy trong test project có Spring Security Crypto:

```java
PasswordEncoder v1 = new BCryptPasswordEncoder(10);
PasswordEncoder v2 = new BCryptPasswordEncoder(12);

String oldHash = v1.encode("pass");
boolean valid = v2.matches("pass", oldHash);
boolean needsUpgrade = v2.upgradeEncoding(oldHash);

String newHash = v2.encode("pass");
boolean upgradedMatches = v2.matches("pass", newHash);
boolean stillNeedsUpgrade = v2.upgradeEncoding(newHash);

System.out.println(valid);
System.out.println(needsUpgrade);
System.out.println(upgradedMatches);
System.out.println(stillNeedsUpgrade);
```

Output có thể kiểm chứng:

```text
true
true
true
false
```

Không so sánh raw hash với một string cố định vì salt được sinh ngẫu nhiên. Với integration test cần xác minh cả đường provider/writer và cập nhật bền vững trong kho user.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đổi cost trong bean rồi coi toàn bộ DB đã nâng | Hash cũ vẫn tồn | Lazy rehash/writer và metrics |
| Gọi `upgradeEncoding` là đã nâng password | Không cập nhật gì | `encode(raw đã xác minh)` + writer |
| Rehash password input trước khi matches | Attacker có thể thay password người khác | Chỉ update sau authentication hợp lệ |
| Encode hash cũ để chuyển thuật toán | Hash của hash, password gốc không matches | Rehash bằng raw đã xác minh hoặc reset |
| Dùng `encode(raw).equals(stored)` | Salt làm so sánh sai | Dùng `matches(raw, stored)` |
| Tự chọn cost tối đa không benchmark | CPU nghẽn, login chậm/DoS | Đo p95/p99 và tài nguyên |
| Đổi format mới trước khi fleet có decoder | Một số instance không verify được | Decode-first deployment |
| Không có `UserDetailsPasswordService` | Không lưu lazy upgrade | Cấu hình writer đúng |
| Writer encode lại newEncodedPassword | Password bị băm hai lần | Lưu encoded string nguyên vẹn |
| Ghi mù quáng khi reset đồng thời | Password reset mới bị ghi đè | Transaction/CAS/optimistic lock |
| Coi `upgradeEncoding=false` là chuẩn an toàn tuyệt đối | Bỏ sót policy/advisory | Security review và policy version |
| Custom encoder không override upgrade | Luôn không nâng | Implement/test rõ |
| Để fallback plaintext/NoOp trên production | Mở đường yếu/bypass | Migration có giới hạn hoặc reset |
| Rollback cost làm hash mới bị hạ cấp | Giảm mức bảo vệ | Rollback code có write policy không downgrade |
| Quên account không login lâu | Một phần hash cũ tồn mãi | Reset có xác minh hoặc deadline |
| Log password/hash vì cần telemetry | Rò thông tin nhạy cảm | Chỉ log metadata, metrics tổng hợp |
| Tin JWT request tự nâng hash | Không có raw password | Login/password reset là thời điểm phù hợp |
| Dùng username query để update hash | Sai account/tenant, có thể lộ dữ liệu | Internal ID tin cậy |
| Tắt khóa tài khoản để rehash | Vượt authentication policy | Không upgrade qua login bị từ chối |
| Không test hash malformed | Lỗi runtime hoặc fallback nguy hiểm | Validate format, fail closed |

## 19. Tự kiểm tra kiến thức

**Câu 1.** Khi thay `new BCryptPasswordEncoder(10)` bằng `new BCryptPasswordEncoder(12)`, tất cả hash trong DB đã thành cost 12 chưa?  
**Trả lời:** Chưa. Password mới sẽ theo policy mới, còn hash cũ cần rehash trong lần login hợp lệ hoặc reset/migration phù hợp.

**Câu 2.** Vì sao encoder cost 12 vẫn `matches` được BCrypt hash cost 10?  
**Trả lời:** BCrypt hash lưu thông tin salt và cost, giúp verifier tính theo cấu hình của hash cũ.

**Câu 3.** `upgradeEncoding(oldHash)==true` có xác minh password user đúng không?  
**Trả lời:** Không. Method không nhận raw password; nó chỉ đánh giá hash theo policy.

**Câu 4.** Khi nào mới có raw password hợp lệ để rehash?  
**Trả lời:** Trong luồng authentication thành công hoặc đổi/reset password đã được xác minh quyền thực hiện.

**Câu 5.** Vì sao không thể chạy batch `encode(oldHash)`?  
**Trả lời:** Vì nó tạo hash của chuỗi oldHash, không phải password gốc; user sẽ không đăng nhập bằng password cũ.

**Câu 6.** Nếu không cấu hình `UserDetailsPasswordService`, chỉ bật `upgradeEncoding` có lưu hash mới không?  
**Trả lời:** Không. Cần writer hoặc một cơ chế lưu bền vững tương ứng.

**Câu 7.** Vì sao nên triển khai decoder hiểu hash mới trước khi bắt đầu ghi format mới trên một fleet?  
**Trả lời:** Để tất cả instance đều xác minh được hash sinh ra bởi instance mới, tránh login lúc được lúc không.

**Câu 8.** Vì sao CAS/optimistic lock quan trọng khi rehash?  
**Trả lời:** Để không ghi đè password reset mới bằng một rehash từ login đọc hash cũ.

**Câu 9.** Có nên tăng cost mỗi tháng không?  
**Trả lời:** Không có lịch áp dụng chung; thay khi đánh giá bảo mật, benchmark và kế hoạch rollout cho thấy phù hợp.

**Câu 10.** Hash cost 12 gặp instance tạm chạy encoder cost 10 thì phải giảm xuống cost 10 không?  
**Trả lời:** Không. Verify được hash mạnh hơn thường không đòi rehash; rollback cần tránh tạo mới hash yếu.

**Câu 11.** Vì sao một tài khoản chỉ đăng nhập qua OIDC không tự được nâng hash nội bộ?  
**Trả lời:** Ứng dụng không có raw password để rehash; password storage thuộc identity provider nếu provider quản lý credential.

**Câu 12.** Tại sao lần login đầu sau rollout có thể chậm hơn?  
**Trả lời:** Nó có thể phải verify hash cũ, encode raw password theo cost mới và ghi dữ liệu; cần đo latency/capacity.

**Câu 13.** Với `DelegatingPasswordEncoder`, `{id}` ảnh hưởng gì?  
**Trả lời:** Id quyết định decoder của stored hash; `idForEncode` quyết định encoder dùng cho hash mới.

**Câu 14.** `upgradeEncoding=false` có thay thế việc xem xét advisory và chính sách mật khẩu không?  
**Trả lời:** Không. Nó chỉ thể hiện kết quả logic của encoder hiện tại.

## Kết luận

`upgradeEncoding` là **cầu nối giữa chính sách băm hiện tại và những hash đã lưu theo chính sách cũ**, nhưng chỉ trả một quyết định; nó không băm, không xác thực người gọi và không ghi DB. “Thời điểm thay đổi tham số băm” cần được nhìn theo nhiều mốc: lúc chọn chính sách mới, lúc mở compatibility, lúc tạo hash mới, lúc user đăng nhập hợp lệ để rehash, và lúc nghỉ hưu thuật toán cũ.

Một rollout đúng bao gồm **đánh giá mức bảo vệ và hiệu năng**, **giữ khả năng xác minh hash cũ trong thời gian cần thiết**, **rehash chỉ với raw password đã xác minh**, **writer cập nhật có điều kiện**, **đo tiến độ và rollback không downgrade**, cùng phương án reset cho account chưa bao giờ quay lại đăng nhập.

**Quy tắc nhớ:** *Đổi encoder không đồng nghĩa đổi dữ liệu; `upgradeEncoding` chỉ báo cần đổi; chỉ một luồng authentication hợp lệ và writer an toàn mới biến hash cũ thành hash mới.*

### Tài liệu tham khảo chính thức

- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
