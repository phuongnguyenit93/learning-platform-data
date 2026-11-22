# Chính sách mật khẩu và phản hồi kiểm tra dữ liệu đầu vào

Một ứng dụng quản lý tài khoản không thể bảo mật mật khẩu chỉ bằng regex “chữ hoa + số + ký tự đặc biệt”. Trong **vòng đời tài khoản**, cùng một bí mật xuất hiện ở bước đăng ký, thay đổi mật khẩu, khôi phục tài khoản và đăng nhập. Mỗi bước cần kết hợp **chính sách mật khẩu phù hợp**, **xác thực dữ liệu đầu vào**, **hash lưu trữ an toàn** và **phản hồi HTTP không làm lộ thông tin nhạy cảm**.

Bài học dành cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Trọng tâm là: chọn policy độ dài và blocklist, xử lý Unicode, dùng `PasswordEncoder`, kết hợp `@Valid`/Jakarta Validation với kiểm tra nghiệp vụ, xây phản hồi lỗi có mã ổn định, và phân biệt thông báo **đặt mật khẩu mới** với thông báo **đăng nhập/khôi phục** nhằm chống dò tài khoản.

## 1. Chính sách mật khẩu nằm ở đâu trong vòng đời tài khoản?

| Bước | Kiểm tra chính | Phản hồi an toàn |
| --- | --- | --- |
| **Đăng ký** | Username/email hợp lệ; mật khẩu mới đủ mạnh, không nằm trong blocklist; uniqueness ở DB; xác minh địa chỉ liên hệ | Giải thích lỗi *mật khẩu mới* nhưng tránh xác nhận email/tài khoản có tồn tại |
| **Đổi mật khẩu** | User đang xác thực; kiểm tra mật khẩu hiện tại hoặc step-up; mật khẩu mới đạt policy; update có transaction | Thông báo policy cụ thể cho chủ tài khoản; không đưa password/hash vào error |
| **Quên mật khẩu** | Reset token ngẫu nhiên, hạn ngắn, dùng một lần; xác minh kênh đã đăng ký; policy cho mật khẩu mới | Ở bước yêu cầu reset: “Nếu tài khoản phù hợp tồn tại, chúng tôi sẽ gửi hướng dẫn” |
| **Đăng nhập** | Dùng `PasswordEncoder.matches`; rate limit; account status; MFA/session policy | Thông báo **chung** khi sai username/password hoặc tài khoản không đăng nhập được |
| **Khóa tài khoản/đánh giá rủi ro** | Theo dõi tấn công, phát hiện credential compromise, yêu cầu đổi password khi có lý do | Tránh lộ trạng thái account ở endpoint công khai |
| **Xóa tài khoản** | Xác minh quyền, thu hồi session/token, xóa/xử lý password hash và dữ liệu liên quan theo chính sách | Không trả thông tin bí mật hoặc chi tiết nội bộ |

**Chính sách mật khẩu** chủ yếu kiểm tra **mật khẩu mới** khi tạo/đổi/reset. Còn tại **login**, hệ thống nên so sánh với hash hiện có và dùng luồng migration khi cần; đừng áp nguyên một password policy mới lên người dùng legacy rồi trả thông báo “mật khẩu của bạn có 10 ký tự” trước khi xác thực.

Phân biệt ba loại dữ liệu:

- **Password** là secret do người dùng nắm giữ; không log, không trả lại, không lưu plaintext.
- **Username/email** là định danh: thường có validation riêng và có thể cần chuẩn hóa để đảm bảo uniqueness.
- **Password hash** là dữ liệu nhạy cảm cần bảo vệ trong DB; không phải password mã hóa có thể giải ngược.

## 2. Tiêu chuẩn tham chiếu NIST SP 800-63B-4

NIST SP 800-63B-4 (xuất bản năm 2025) cập nhật các nguyên tắc cho **centrally verified passwords**. Đây là chuẩn tham chiếu; các hệ thống còn phải đáp ứng quy định ngành, yêu cầu hợp đồng và mức đảm bảo xác thực thực tế.

| Yêu cầu/khuyến nghị | Điều cần thực hiện |
| --- | --- |
| Password dùng như **yếu tố xác thực duy nhất** | Yêu cầu tối thiểu **15 ký tự** |
| Password chỉ dùng **trong quy trình MFA bắt buộc** | Có thể đặt ngưỡng thấp hơn nhưng vẫn **ít nhất 8 ký tự** |
| Độ dài tối đa được hỗ trợ | Nên cho phép **ít nhất 64 ký tự**, để người dùng đặt passphrase dài |
| Ký tự được chấp nhận | Cho phép ký tự in được, **khoảng trắng**, Unicode; hỗ trợ paste và password manager |
| Composition rules | **Không** ép tổ hợp chữ hoa, chữ thường, chữ số hay ký tự đặc biệt |
| Blocklist | Kiểm **toàn bộ password** với danh sách mật khẩu phổ biến, dễ đoán và từng bị rò rỉ |
| Đổi mật khẩu định kỳ | Không yêu cầu thay đổi tùy ý theo chu kỳ nếu không có bằng chứng compromised |
| Xác thực online | Phải giới hạn số lần đoán thử và có biện pháp chống brute force/stuffing |
| Unicode normalization | Nên dùng **NFC** nhất quán trước hashing và kiểm tra |

**Không nhầm điều kiện MFA:** việc ứng dụng *có tùy chọn bật MFA* không có nghĩa mọi lần đăng nhập đều bắt buộc hai yếu tố. Nếu user vẫn có đường login chỉ bằng password, hãy áp ngưỡng 15 ký tự cho trường hợp single-factor.

### 2.1. Vì sao không dùng regex bắt ký tự đặc biệt?

Mật khẩu `Password1!Password1!` có chữ hoa/số/ký tự đặc biệt và trông dài nhưng rất dễ dự đoán. Một câu bí mật dài chỉ gồm chữ thường và khoảng trắng có thể khó đoán hơn. Quy tắc composition còn khiến người dùng thêm ký tự theo thói quen như `!` ở cuối, làm password trở nên dễ đoán. Do đó:

1. Khuyến khích **passphrase dài, độc đáo, không dùng lại** trên nhiều dịch vụ.
2. So toàn bộ giá trị đã chuẩn hóa với **blocklist** có kiểm soát.
3. Cho phép password manager/autofill/paste.
4. Giới hạn số lần thử đăng nhập ở server.
5. Không buộc người dùng thay password mỗi 30/60/90 ngày nếu không có lý do bảo mật.

**Không dùng mật khẩu/username trong đoạn ví dụ như một bí mật production.** Mọi chuỗi minh họa đều có thể bị kẻ tấn công đoán.

### 2.2. Unicode, ký tự và số byte

Java `String.length()` đếm **UTF-16 code units**, không phải số Unicode code points; một emoji thường chiếm hai code units. `codePointCount(0, s.length())` đếm code points. `s.getBytes(StandardCharsets.UTF_8).length` đếm bytes. Với các ký tự gồm nhiều dấu kết hợp, số code points cũng không nhất thiết bằng số ký tự người dùng cảm nhận.

Trong ví dụ này quy tắc là **15–128 Unicode code points sau khi chuẩn hóa NFC**. Đây là một quy ước lập trình cần được mô tả rõ. Quan trọng hơn, phải dùng **chính cùng normalization** ở registration, change/reset và login `matches`.

**Không tùy tiện `trim()`, `strip()`, lowercase hoặc truncate password.** Những phép biến đổi đó có thể khiến hai giá trị bí mật khác nhau trở thành một. Còn username có thể có quy tắc trim/case normalization riêng nếu chính sách định danh quy định.

### 2.3. Giới hạn trên và thuật toán hashing

Khuyến nghị cho phép ít nhất 64 ký tự không có nghĩa phải chấp nhận body JSON dài hàng MB. Hãy đặt:

- max length ở password policy (ví dụ 128 code points);
- giới hạn HTTP request size trước khi server parse;
- giới hạn độ dài raw sớm trước khi chạy thuật toán hashing tốn tài nguyên;
- database column thích hợp cho **encoded hash** và metadata thuật toán.

Một số bản triển khai bcrypt xử lý tối đa **72 bytes đầu vào**, nên nếu cho phép Unicode/passphrase dài mà dùng bcrypt, phải biết giới hạn thực tế của thư viện và **không âm thầm cắt password**. Ví dụ Java bên dưới dùng PBKDF2. Với hệ thống dùng bcrypt legacy, cần đánh giá byte length, cách xử lý password dài và kế hoạch migration rõ ràng.

## 3. Blocklist và mật khẩu đã bị lộ

Độ dài 15 không đủ nếu người dùng chọn `passwordpassword` hoặc `123456789012345`. Blocklist phải chứa **giá trị password hoàn chỉnh**:

- Các chuỗi thông dụng, tuần tự/lặp, dễ đoán.
- Các giá trị từng có trong breach corpuses.
- Tên ứng dụng, tổ chức, username, domain và biến thể rõ ràng có thể đoán.

**Tránh regex cấm một từ con**. Một passphrase có từ `spring` ở giữa không tự động yếu chỉ vì từ ấy thuộc từ điển.

Spring Security 6.x cung cấp interface `CompromisedPasswordChecker` và `HaveIBeenPwnedRestApiPasswordChecker`; kết quả `CompromisedPasswordDecision#isCompromised()` có thể dùng khi người dùng **đặt password mới**. Ví dụ đoạn code đặt trong một service có `compromisedPasswordChecker` được inject:

~~~java
CompromisedPasswordDecision decision =
        compromisedPasswordChecker.check(proposedPassword);
if (decision.isCompromised()) {
    throw new IllegalArgumentException(
            "Choose a different, uncompromised password");
}
~~~

Đây chỉ là **snippet bên trong phương thức**; không nên dùng `IllegalArgumentException.getMessage()` trực tiếp làm HTTP error. Hãy chuyển thành mã lỗi như `COMMON_PASSWORD` và message đã whitelist.

Bài chạy local dưới đây dùng blocklist **ba chuỗi giả lập**, để test được mà không gọi Internet. Nó **không** đủ để đáp ứng blocklist production. Trong thực tế cần nguồn compromised passwords thích hợp, xử lý timeout/outage, chính sách riêng tư và cache. Không gửi plaintext password tới dịch vụ bên ngoài tùy tiện, không in password vào log khi checker thất bại.

**Lưu ý:** Spring Security có thể tích hợp `CompromisedPasswordChecker` ở một số cấu hình `DaoAuthenticationProvider` cho login; điều này **không tự động thêm kiểm tra** cho mọi endpoint `/register` do ứng dụng tự viết. Kiểm tra password mới vẫn phải được gọi ở service của registration/change/reset.

## 4. Lưu mật khẩu bằng PasswordEncoder

Phân biệt rõ:

~~~text
Mật khẩu mới nhập
   ├─ Input/DTO validation
   ├─ Domain password policy, breach blocklist
   ├─ Unicode normalization nhất quán
   ▼
PasswordEncoder.encode(...)
   ▼
Hash có salt + tham số thuật toán lưu trong DB

Đăng nhập:
password input → same normalization → PasswordEncoder.matches(...)
                                         │
                             so với hash đã lưu
                                         ▼
                   UserDetailsService / DaoAuthenticationProvider
                                         │
                   account status, MFA, authorization, session
~~~

`UserDetailsService`/`UserDetails` hỗ trợ nạp account cho Spring Security; `DaoAuthenticationProvider` thường dùng `PasswordEncoder` để xác minh password. Policy đặt mật khẩu mới là **logic nghiệp vụ khác**: không tự được Spring Security tạo ra chỉ bằng cách có UserDetailsService.

**Không** lưu password plaintext, mã Base64, hash nhanh MD5/SHA-256 thuần hoặc sử dụng `{noop}` cho production. Adaptive password hashing như PBKDF2, bcrypt, scrypt hoặc Argon2 cần salt, work factor và benchmark trên hạ tầng thật.

Ví dụ sử dụng API Spring Security 6.5:

~~~java
PasswordEncoder encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("Cau mat khau dai va rieng tu 2026");

System.out.println(encoder.matches(
        "Cau mat khau dai va rieng tu 2026", hash));
System.out.println(encoder.matches("Sai mat khau", hash));
~~~

Đây là **snippet trong phương thức** có import `PasswordEncoder` và `Pbkdf2PasswordEncoder`; stdout của hai dòng cuối là:

~~~text
true
false
~~~

Hash có salt nên giá trị `hash` không cố định. Không so `encoder.encode(input).equals(storedHash)`, vì encode thường dùng salt ngẫu nhiên.

### 4.1. DelegatingPasswordEncoder và migration

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder lưu hash dạng `{id}encodedPassword`. Mặc định nó có thể **encode bằng bcrypt**, dù hỗ trợ xác minh nhiều thuật toán; vì vậy cần xét trần 72 bytes khi ứng dụng cho phép passphrase dài. Khi muốn tạo hash mới bằng PBKDF2 nhưng vẫn đọc hash bcrypt cũ, có thể cấu hình:

~~~java
Map<String, PasswordEncoder> implementations = new HashMap<>();
implementations.put("pbkdf2@SpringSecurity_v5_8",
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
implementations.put("bcrypt", new BCryptPasswordEncoder());

PasswordEncoder encoder = new DelegatingPasswordEncoder(
        "pbkdf2@SpringSecurity_v5_8", implementations);
~~~

Đây là snippet: thêm imports từ `java.util.*` và `org.springframework.security.crypto.password.*`, đặt trong bean/config thích hợp. Kết quả hash mới có prefix `{pbkdf2@SpringSecurity_v5_8}`. Hash legacy thiếu `{id}` phải được migrate có kiểm soát; không đặt `NoOpPasswordEncoder` làm fallback chỉ để bỏ lỗi. Chi phí hash cũng cần được tune và giám sát trước khi triển khai.

## 5. Phản hồi validation: khi nào được nói chi tiết?

| Tình huống | HTTP thường gặp | Response phù hợp |
| --- | --- | --- |
| JSON lỗi cú pháp | 400 | `MALFORMED_JSON`, không trả parser stack trace |
| Username/password field thiếu hoặc sai định dạng | 400 | `INPUT_INVALID` + field/code/message có kiểm soát |
| **Password mới** chưa đủ dài | 400 hoặc 422 theo contract | `PASSWORD_POLICY_REJECTED` + `TOO_SHORT` |
| **Password mới** trong blocklist | 400 hoặc 422 | `COMMON_PASSWORD` + lời khuyên chọn bí mật khác |
| Đăng ký username/email đã có | Phụ thuộc chống user enumeration | Thông báo chung; không xác nhận account tồn tại |
| Login sai password/username | 401 | “Thông tin đăng nhập không hợp lệ.” |
| Không đủ quyền sau xác thực | 403 | “Bạn không có quyền thực hiện.” |
| CSRF sai khi app dùng cookie | 403 | Thông báo form/request cần làm mới |
| Rate limit | 429 | Hướng dẫn thử lại sau, không tiết lộ account state |
| Breach checker không truy cập được | Theo outage policy, có thể 503 | Không tự coi mật khẩu là an toàn |

**Được phép chi tiết về password mà người dùng đang chọn** khi lập tài khoản: chẳng hạn “Dùng ít nhất 15 ký tự.” Nhưng **không** hiển thị “user này tồn tại nhưng đang bị khóa” hoặc “đúng username, sai mật khẩu” cho yêu cầu login công khai.

Ví dụ phản hồi sử dụng **Problem Details (RFC 9457)**:

~~~json
{
  "type": "about:blank",
  "title": "Dữ liệu chưa hợp lệ",
  "status": 400,
  "detail": "Vui lòng kiểm tra các trường được đánh dấu.",
  "code": "PASSWORD_POLICY_REJECTED",
  "errors": [
    {
      "field": "password",
      "code": "TOO_SHORT",
      "message": "Hãy dùng ít nhất 15 ký tự."
    }
  ]
}
~~~

**Tuyệt đối không trả** `rejectedValue`, password plaintext, stored hash, exception stack trace, raw SQL constraint hoặc full request body. Validation framework thường có `FieldError.getRejectedValue()`: nếu serialize nguyên `BindingResult` hoặc log `MethodArgumentNotValidException`/request DTO, mật khẩu có thể bị ghi ra HTTP/log.

### 5.1. Các lớp validation của Spring MVC

- `@Valid @RequestBody RegisterRequest` + Jakarta Validation: kiểm tra DTO (trường bắt buộc, username pattern). Với lỗi thường phát sinh `MethodArgumentNotValidException`.
- `PasswordPolicy` ở service: kiểm tra độ dài theo Unicode codepoint, blocklist, max size; ném exception nghiệp vụ không chứa giá trị secret.
- Database: enforce uniqueness qua UNIQUE constraint và transaction, chống hai request concurrent đăng ký cùng username.
- Nếu controller có constraint **trực tiếp trên method parameter** (Spring MVC 6.1+), có thể phát sinh `HandlerMethodValidationException`; một API production cần mapping cả hai loại validation error.
- Dữ liệu JSON không parse được có thể tạo `HttpMessageNotReadableException`: xử lý 400 chung, không đưa nguyên parser error ra client.

Với password Unicode, `@Size(min=15)` dùng Java length semantics nên **không hẳn** tương đương quy tắc 15 Unicode code points. Vì vậy ví dụ dùng `@NotNull` cho password trong DTO, còn service tính code points sau NFC.

## 6. Ví dụ Spring Boot 3.5 / Spring Security 6.5 / Java 17+

Ví dụ tạo **một JSON registration endpoint** công khai, kiểm tra password policy, hash PBKDF2 và trả error code có cấu trúc. App lưu thử trong `ConcurrentHashMap` để minh họa và trả cùng `202 Accepted` dù username có sẵn hay chưa. **Chưa có hệ thống login, email confirmation, database production, rate limit hoặc session revocation**; không được copy nguyên vào production.

### 6.1. Dependencies

Trong Gradle project Spring Boot 3.5.x có plugin/BOM và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 6.2. Source file đầy đủ

Tệp `src/main/java/example/account/PasswordPolicyApplication.java`:

~~~java
package example.account;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class PasswordPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordPolicyApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class AccountSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/accounts/register")
                    .permitAll()
                .anyRequest().denyAll());

        // Chỉ exempt CSRF cho public JSON endpoint stateless của lab.
        // Không tắt CSRF cho form/session còn lại.
        http.csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/accounts/register"));

        return http.build();
    }
}

record RegisterRequest(
        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9._-]{3,40}")
        String username,
        @NotNull String password) {
}

record FieldIssue(String field, String code, String message) {
}

class PasswordRejectedException extends RuntimeException {
    private final List<FieldIssue> issues;

    PasswordRejectedException(List<FieldIssue> issues) {
        super("Password policy rejected");
        this.issues = List.copyOf(issues); // Không có raw password.
    }

    List<FieldIssue> issues() {
        return issues;
    }
}

@Component
class PasswordPolicy {
    private static final Set<String> DEMO_BLOCKLIST = Set.of(
            "passwordpassword",
            "123456789012345",
            "qwertyqwertyqwerty"
    );

    String normalizeAndValidate(String raw) {
        if (raw == null) {
            throw new PasswordRejectedException(List.of(
                    new FieldIssue("password", "REQUIRED",
                            "Mật khẩu không được bỏ trống.")));
        }

        // Chặn input quá lớn trước khi normalize/hash.
        if (raw.length() > 1024) {
            throw new PasswordRejectedException(List.of(
                    new FieldIssue("password", "TOO_LONG",
                            "Mật khẩu vượt giới hạn cho phép.")));
        }

        String value = Normalizer.normalize(raw, Normalizer.Form.NFC);
        int codePoints = value.codePointCount(0, value.length());
        List<FieldIssue> issues = new ArrayList<>();

        if (codePoints < 15) {
            issues.add(new FieldIssue("password", "TOO_SHORT",
                    "Hãy dùng ít nhất 15 ký tự."));
        }
        if (codePoints > 128) {
            issues.add(new FieldIssue("password", "TOO_LONG",
                    "Mật khẩu tối đa 128 ký tự."));
        }
        if (value.isBlank()
                || value.codePoints().anyMatch(Character::isISOControl)) {
            issues.add(new FieldIssue("password", "UNSUITABLE",
                    "Hãy chọn cụm từ bí mật có nội dung hợp lệ."));
        }

        // Lowercase chỉ để tra blocklist; không biến đổi secret khi hash.
        if (DEMO_BLOCKLIST.contains(value.toLowerCase(Locale.ROOT))) {
            issues.add(new FieldIssue("password", "COMMON_PASSWORD",
                    "Mật khẩu quá dễ đoán. Hãy chọn mật khẩu khác."));
        }

        if (!issues.isEmpty()) {
            throw new PasswordRejectedException(issues);
        }
        return value;
    }
}

@Component
class DemoAccountStore {
    private final Map<String, String> storedHashes =
            new ConcurrentHashMap<>();

    void insertIfAbsent(String username, String encodedHash) {
        storedHashes.putIfAbsent(username, encodedHash);
    }
}

@Service
class RegistrationService {
    private final PasswordPolicy policy;
    private final PasswordEncoder encoder;
    private final DemoAccountStore store;

    RegistrationService(PasswordPolicy policy,
                        PasswordEncoder encoder,
                        DemoAccountStore store) {
        this.policy = policy;
        this.encoder = encoder;
        this.store = store;
    }

    void register(RegisterRequest request) {
        String normalized = policy.normalizeAndValidate(
                request.password());
        String encoded = encoder.encode(normalized);
        store.insertIfAbsent(request.username(), encoded);
    }
}

@RestController
class RegistrationController {
    private final RegistrationService service;

    RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @PostMapping("/api/accounts/register")
    ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegisterRequest request) {
        service.register(request);
        // Không tiết lộ username đã tồn tại hay chưa.
        return ResponseEntity.accepted().body(Map.of(
                "status", "RECEIVED",
                "message", "Yêu cầu đã được ghi nhận."));
    }
}

@RestControllerAdvice
class SafeRegistrationErrors {

    @ExceptionHandler(PasswordRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(PasswordRejectedException e) {
        return ResponseEntity.badRequest().body(problem(
                "PASSWORD_POLICY_REJECTED", e.issues()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> badRequest(
            MethodArgumentNotValidException e) {
        Map<String, FieldIssue> unique = new LinkedHashMap<>();
        e.getBindingResult().getFieldErrors().forEach(error -> {
            String field = error.getField();
            unique.putIfAbsent(field, new FieldIssue(
                    field, "INVALID_FIELD",
                    "password".equals(field)
                            ? "Mật khẩu là trường bắt buộc."
                            : "Tên tài khoản không hợp lệ."));
        });
        // KHÔNG dùng error.getRejectedValue() hoặc e.getMessage().
        return ResponseEntity.badRequest().body(problem(
                "INPUT_INVALID", List.copyOf(unique.values())));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> malformed(
            HttpMessageNotReadableException ignored) {
        return ResponseEntity.badRequest().body(problem(
                "MALFORMED_JSON", List.of()));
    }

    private ProblemDetail problem(String code, List<FieldIssue> errors) {
        ProblemDetail value =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        value.setTitle("Dữ liệu chưa hợp lệ");
        value.setDetail("Vui lòng kiểm tra các trường được đánh dấu.");
        value.setProperty("code", code);
        value.setProperty("errors", errors);
        return value;
    }
}
~~~

**Phân tích mã:**

1. `RegisterRequest` kiểm tra `username` bằng Bean Validation, `password` phải không null. Ràng buộc regex áp dụng cho **username**, không vi phạm nguyên tắc không ép composition password.
2. `PasswordPolicy.normalizeAndValidate` chuẩn hóa NFC, đếm code points, kiểm max/min, control chars và blocklist giả lập. Cùng hàm phải được dùng khi tạo/đổi/reset password; khi login cũng phải normalize theo cùng quy tắc **trước** `PasswordEncoder.matches`.
3. `PasswordRejectedException` chỉ chứa `FieldIssue`, không chứa password người dùng nhập.
4. `Pbkdf2PasswordEncoder` hash password sau validation; `DemoAccountStore` chỉ giữ hash trong RAM để test, không là repository dùng thật. Production cần DB migration, unique constraints và account verification.
5. `RegistrationController` trả `202` giống nhau đối với username mới/đã có; không khẳng định account đã kích hoạt hoặc email đã gửi. Production cần thêm bước xác minh liên hệ và chống timing enumeration.
6. `SafeRegistrationErrors` chỉ trả các field/code/message đã whitelist. Không dùng `getRejectedValue()`, không trả Bean Validation object hoặc stack trace ra mạng.
7. `SecurityFilterChain` cho phép POST public register, chặn mọi route khác. Chỉ loại trừ CSRF cho endpoint **stateless/public của lab**; với ứng dụng browser dựa trên cookie/session, phải áp CSRF theo kiến trúc thật.
8. Không có `UserDetailsService` hoặc login controller trong demo vì mục tiêu là **policy + registration feedback**; production cần gắn kho account vào authentication provider và quản lý lifecycle đầy đủ.

### 6.3. Chạy thử

Trong project Spring Boot 3.5/JDK 17 có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows dùng `gradlew.bat bootRun`. Tạo file chỉ chứa dữ liệu lab `register-test.json`:

~~~json
{
  "username": "student-01",
  "password": "Cau mat khau dai va rieng tu 2026"
}
~~~

Gửi request tới localhost (chỉ demo; production dùng HTTPS và không lưu plaintext secret trên disk):

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @register-test.json \
  http://localhost:8080/api/accounts/register
~~~

Kết quả kỳ vọng khi project chạy đúng là **HTTP 202** và body:

~~~json
{
  "status": "RECEIVED",
  "message": "Yêu cầu đã được ghi nhận."
}
~~~

Đổi password trong file test thành `short` thì request phải bị từ chối với **HTTP 400**, trường `code=PASSWORD_POLICY_REJECTED` và một lỗi `password: TOO_SHORT`. Với JSON hỏng, mã lỗi là `MALFORMED_JSON`. Đừng dùng real password/token trong file demo hoặc access logs.

### 6.4. Unit test của policy

Tệp `src/test/java/example/account/PasswordPolicyTest.java`:

~~~java
package example.account;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PasswordPolicyTest {
    private final PasswordPolicy policy = new PasswordPolicy();

    @Test
    void rejectsShortPassword() {
        PasswordRejectedException e = assertThrows(
                PasswordRejectedException.class,
                () -> policy.normalizeAndValidate("short"));
        assertEquals("TOO_SHORT", e.issues().get(0).code());
    }

    @Test
    void rejectsCommonPassword() {
        PasswordRejectedException e = assertThrows(
                PasswordRejectedException.class,
                () -> policy.normalizeAndValidate(
                        "passwordpassword"));
        assertTrue(e.issues().stream().anyMatch(
                issue -> "COMMON_PASSWORD".equals(issue.code())));
    }

    @Test
    void acceptsLongPassphraseWithoutSpecialCharacters() {
        String value = "Mot cau bi mat dai va duy nhat";
        assertEquals(value, policy.normalizeAndValidate(value));
    }

    @Test
    void appliesNfcNormalization() {
        String decomposed = "Cafe\u0301 mot cau bi mat rat dai";
        String expected = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        assertEquals(expected, policy.normalizeAndValidate(decomposed));
    }
}
~~~

`\u0301` là combining acute accent trong mã Java; test bảo đảm chuỗi đầu vào được chuẩn hóa về NFC. Test dùng JUnit Jupiter từ starter-test, không cần khởi tạo Spring context.

### 6.5. HTTP test xác minh phản hồi an toàn

Tệp `src/test/java/example/account/RegistrationHttpTest.java`:

~~~java
package example.account;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void shortPasswordReturnsSafeFieldError() throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student-01","password":"short"}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("PASSWORD_POLICY_REJECTED"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("password"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("TOO_SHORT"));
    }

    @Test
    void missingPasswordReturnsInputInvalid() throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student-01"}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INPUT_INVALID"));
    }

    @Test
    void validRequestReturnsGenericAcknowledgement()
            throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username":"student-02",
                      "password":"Mot cau bi mat dai va duy nhat"
                    }
                    """))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("RECEIVED"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test \
  --tests example.account.PasswordPolicyTest \
  --tests example.account.RegistrationHttpTest
~~~

Kết quả kỳ vọng là **4 unit tests + 3 HTTP tests đều pass** trong project đủ dependencies. Output Gradle thay đổi theo phiên bản/build. Các test này **không thay thế** integration tests với DB, account uniqueness, reset token, CSRF ở app dùng session và dịch vụ blocklist thực.

## 7. Đổi mật khẩu và khôi phục: dùng cùng policy nhưng khác quyền truy cập

### 7.1. Đổi mật khẩu (authenticated session)

Quy trình an toàn:

1. Lấy tài khoản từ `Authentication.getName()`/principal đã được xác minh, **không lấy user ID tùy ý client gửi**.
2. Yêu cầu recent authentication, password hiện tại hoặc step-up phù hợp để chống attacker chiếm session.
3. Dùng `PasswordEncoder.matches(normalizedCurrent, currentStoredHash)`; không in current password.
4. Áp **chính sách password mới** + compromised blocklist cho `newPassword`. Có thể kiểm tra reuse bằng `matches(normalizedNew, currentHash)`, không so hai hash vì salt khác nhau.
5. Encode password mới; update DB theo account ID với transaction và version check, tránh race.
6. Thông báo bảo mật qua kênh đã xác minh; áp chính sách thu hồi session/refresh tokens đang tồn tại.
7. Audit loại sự kiện và request ID, không log password/hash.

### 7.2. Quên mật khẩu (public request + one-time reset link)

Bước một nhận email/username rồi **luôn trả phản hồi chung**. Server chỉ gửi hướng dẫn đến địa chỉ đã xác minh của một account hợp lệ. Token phải ngẫu nhiên đủ mạnh, lưu an toàn, hạn ngắn, **tiêu thụ atomic chỉ một lần**. Bước đặt lại password sẽ gọi cùng `PasswordPolicy`, encode và cập nhật; không tự biến reset token thành một session đăng nhập vô hạn.

Một lỗi thường gặp là gửi “mật khẩu mới tạm thời” hoặc “mật khẩu cũ” qua email. Cần gửi **link reset** chứa token không đoán được và không log. Sau reset nên thông báo thay đổi và xử lý các phiên đang mở theo threat model.

### 7.3. Đăng nhập: đừng trả policy hints trước khi xác thực

`DaoAuthenticationProvider` và `UserDetailsService` có thể xác thực account bằng `PasswordEncoder.matches`. Khi login thất bại, dùng thông báo chung cho **username không tồn tại, password sai hoặc trạng thái account không cho đăng nhập**, để tránh user enumeration. Cần rate limit, theo dõi credential stuffing và timing khác biệt có thể khai thác.

Nếu sau khi login thành công phát hiện password hash legacy hoặc password bị lộ, có thể chuyển người dùng vào **quy trình nâng cấp an toàn**, không biến bước login thành endpoint cho biết chính xác mật khẩu hiện tại yếu ở chỗ nào đối với unauthenticated caller.

## 8. Mã lỗi và UX

| Code | Trường | Lời nhắn gợi ý |
| --- | --- | --- |
| `INPUT_INVALID` | DTO | “Vui lòng kiểm tra thông tin đã nhập.” |
| `MALFORMED_JSON` | Request | “Dữ liệu yêu cầu chưa đúng định dạng.” |
| `PASSWORD_POLICY_REJECTED` | Password mới | “Mật khẩu chưa đáp ứng yêu cầu.” |
| `TOO_SHORT` | Password mới | “Hãy dùng ít nhất 15 ký tự.” |
| `TOO_LONG` | Password mới | “Mật khẩu vượt giới hạn.” |
| `COMMON_PASSWORD` | Password mới | “Mật khẩu này quá dễ đoán.” |
| `UNSUITABLE` | Password mới | “Hãy chọn một cụm từ bí mật hợp lệ.” |
| `INVALID_CREDENTIALS` | Login | “Thông tin đăng nhập không hợp lệ.” |
| `RATE_LIMITED` | Login/reset/register | “Bạn đã thử quá nhiều lần. Hãy thử lại sau.” |

Frontend nên hiển thị yêu cầu trước khi nhập, hỗ trợ password manager, paste, nút hiện/ẩn password và phản hồi theo field với accessibility. Backend vẫn là nguồn quyết định cuối; không tin JavaScript client-side validation để bảo vệ API.

**Không gửi** password, token, rejectedValue hoặc stored hash tới analytics/error tracking. Đối với endpoint đăng ký công khai, cần ngăn username/email enumeration qua status, body và **timing**, không chỉ ẩn một dòng message.

## 9. Ma trận test bảo mật

| ID | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| T01 | Password 14 Unicode code points | `TOO_SHORT` |
| T02 | Password 15+ code points, không có ký tự đặc biệt | Được chấp nhận nếu không nằm trong blocklist |
| T03 | Password 64 code points chứa dấu cách/Unicode | Không bị từ chối chỉ vì dài hoặc có dấu cách |
| T04 | Password 129 code points ở demo | `TOO_LONG` |
| T05 | Emoji và Unicode NFC/NFD | Đếm/normalize nhất quán |
| T06 | Password phổ biến bị lộ, nhưng dài | `COMMON_PASSWORD` |
| T07 | Passphrase có một từ thông dụng ở giữa | Không cấm chỉ vì một substring |
| T08 | Raw input cực lớn | Bị giới hạn trước hashing; hệ thống không DoS |
| T09 | Username sai định dạng | 400 `INPUT_INVALID` |
| T10 | Thiếu `password` | 400, error không lộ raw input |
| T11 | JSON hỏng | 400 `MALFORMED_JSON` |
| T12 | Username mới và đã tồn tại | Public response không lộ tình trạng tài khoản |
| T13 | Hai request đăng ký trùng cùng lúc | DB unique constraint chặn trùng |
| T14 | Encode hai lần cùng password | Hash khác do salt, `matches` đều đúng |
| T15 | Login user sai và password sai | Phản hồi chung, không lộ account |
| T16 | Thử login liên tục | Throttling/rate limit và logging sanitized |
| T17 | Change password không authenticated/step-up | Bị chặn |
| T18 | Gửi `userId` người khác để đổi password | Bị chặn IDOR |
| T19 | Reset token đã dùng/hết hạn | Bị từ chối, concurrent consume tối đa một lần |
| T20 | Blocklist checker outage | Hành vi theo security policy, không mặc nhiên cho qua |
| T21 | CSRF sai ở endpoint dùng cookie session | Bị chặn |
| T22 | Client-side JS bị bỏ qua | Backend vẫn validate đầy đủ |
| T23 | Validation exception được log | Không bao giờ chứa raw password |
| T24 | Password legacy cần migrate | Không bị âm thầm truncate/bypass; có lộ trình chuyển đổi |

### Lỗi dễ gặp

- **“@Size(min=15) là đủ”**: có thể lệch với code-point policy, không kiểm compromised.
- **“Dùng Base64/MD5/SHA-256 cho nhanh”**: không phải adaptive password hashing an toàn.
- **“Encode rồi so chuỗi hash”**: dùng `matches` vì salt tạo output khác.
- **“Dùng bcrypt và cho phép password rất dài nhưng không xem byte limit”**: có thể gặp truncation/collision không mong muốn.
- **“Chỉ có @Valid ở controller”**: không kiểm domain policy, unique DB và business rule.
- **“Trả toàn BindingResult”**: có thể lộ `rejectedValue` = password.
- **“Trả user bị khóa”**: có thể lộ sự tồn tại tài khoản.
- **“Không giới hạn số lần thử login”**: tạo điều kiện brute force và credential stuffing.
- **“Tắt toàn bộ CSRF để POST chạy”**: nguy hiểm khi app xác thực bằng cookie/session.
- **“Password reset gửi token có thể dùng lại”**: tạo lỗ hổng chiếm tài khoản.
- **“Đổi mật khẩu nhưng không làm gì với session cũ”**: có thể để kẻ tấn công duy trì truy cập.

## 10. Checklist triển khai

- [ ] Policy độ dài dựa trên mô hình MFA/single-factor rõ ràng; max hỗ trợ ít nhất 64 ký tự.
- [ ] Không composition regex; hỗ trợ Unicode/space/paste và normalization nhất quán.
- [ ] Có kiểm tra blocklist toàn password và outage policy cho checker.
- [ ] Có password hashing adaptive + salt, benchmark work factor, kiểm giới hạn bytes và migration.
- [ ] Registration/change/reset dùng chung policy cho password mới; login dùng `matches`.
- [ ] DTO validation và domain validation được phân lớp; DB enforce uniqueness/transaction.
- [ ] Response có field/code/message an toàn, không raw secret, rejectedValue, hash hay stack trace.
- [ ] Login/forgot-password trả thông báo chung, ngăn user enumeration cả timing/status.
- [ ] Có rate limit, request size limit, CSRF/session hardening, HTTPS, audit đã sanitize.
- [ ] Đổi password xác minh owner/current credential hoặc step-up, chống IDOR.
- [ ] Reset token ngẫu nhiên, có hạn, dùng một lần, thu hồi phiên phù hợp.
- [ ] Tests bao phủ độ dài/Unicode/breach, HTTP error, concurrency, privacy và recovery.

## 11. Tài liệu tham khảo

- [NIST SP 800-63B-4 — Passwords](https://pages.nist.gov/800-63-4/sp800-63b.html#passwords)
- [NIST FAQ — Password requirements](https://pages.nist.gov/800-63-4-Implementation-Resources/faqs/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [Spring Security 6.5 — Password Storage & Compromised Password Checking](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Cryptography / Pbkdf2PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
