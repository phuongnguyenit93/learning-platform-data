# Chuẩn hóa tên đăng nhập và tránh làm lộ sự tồn tại của tài khoản

> **Module:** Spring Security - reactive  
> **Chủ đề cha:** Người dùng và mật khẩu  
> **Mục tiêu:** Xây dựng một khóa tên đăng nhập nhất quán khi đăng ký/đăng nhập/khôi phục, đồng thời tránh lộ tài khoản có tồn tại hay không qua response, mã HTTP, thời gian và các luồng phụ. Bài có Java 17+, Spring WebFlux/Spring Security, WebTestClient và bài kiểm tra an toàn.

## 1. Hai vấn đề phải giải quyết cùng lúc

Một người đăng ký dưới tên `Alice`, đăng nhập bằng `alice`, quên mật khẩu bằng ` ALICE `. Nếu ba nơi chuẩn hóa khác nhau, hệ thống có thể tra cứu sai hoặc cho tạo tài khoản logic trùng nhau. Với Unicode, `ＡＬＩＣＥ` (chữ Latin dạng fullwidth) còn có thể có vẻ giống `Alice`.

Một kẻ tấn công thử lần lượt `alice`, `admin`, `bob` ở màn hình đăng nhập hoặc quên mật khẩu. Nếu API trả “Không có người dùng” cho tên lạ nhưng “Sai mật khẩu” cho tên có thật, họ đã có danh sách tài khoản để làm credential stuffing, password spraying và phishing.

**Chuẩn hóa username** nhằm tạo định danh logic ổn định. **Chống account enumeration** nhằm không tiết lộ kết quả tra cứu tài khoản cho người chưa xác thực. Hai kỹ thuật cần đi cùng nhau nhưng giải quyết các vấn đề khác nhau.

Sau bài này, người học phải:

1. Đề xuất được một chính sách `username_key` rõ ràng, cùng cách xử lý Unicode và chữ hoa/chữ thường.
2. Chỉ ra vì sao lưu khóa canonical riêng và unique constraint ở database cần thiết.
3. Phân biệt username normalization với email normalization và password verification.
4. Xây được một đường đăng nhập Spring WebFlux giữ kết quả thất bại **cùng một loại lỗi** khi user không tồn tại, password sai hoặc tài khoản disabled.
5. Giảm chênh lệch thời gian bằng so khớp password với hash giả cho trường hợp không tồn tại, đồng thời hiểu không thể cam kết mọi HTTP request “constant time”.
6. Thiết kế quên mật khẩu/đăng ký không trở thành công cụ dò tài khoản, có rate limit và kiểm thử âm tính.

## 2. Dữ liệu người dùng: ID, tên hiển thị, khóa đăng nhập

Không nên dùng một chuỗi username duy nhất cho mọi mục đích.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `user_id` | Định danh nội bộ bất biến | UUID |
| `username_display` | Tên hiển thị cho người dùng | Alice |
| `username_key` | Khóa chuẩn hóa để tra cứu/kiểm tra trùng | alice |
| `password_hash` | Hash có salt/work factor; không lưu password gốc | `{bcrypt}...` |
| `status` | Trạng thái nội bộ | ACTIVE, DISABLED, LOCKED |
| `verified_email` | Kênh liên hệ đã chứng minh quyền sở hữu | Địa chỉ đã xác minh |

**Dùng `user_id` cho khóa ngoại, ownership, audit và liên kết dữ liệu**, vì username có thể đổi. `username_key` phục vụ đăng nhập và kiểm tra định danh logic; `username_display` không nên là khóa database. Khi username thay đổi, user ID vẫn giữ nguyên.

DDL minh họa (cú pháp điều chỉnh theo database):

~~~sql
CREATE TABLE accounts (
    user_id          UUID PRIMARY KEY,
    username_display VARCHAR(128) NOT NULL,
    username_key     VARCHAR(32) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    enabled          BOOLEAN NOT NULL,
    CONSTRAINT uq_username_key UNIQUE (username_key)
);
~~~

**UNIQUE ở database là bắt buộc.** Kiểm tra `SELECT ... WHERE username_key=...` trước khi INSERT không tránh race condition: hai request song song cùng thấy “chưa có” rồi cùng INSERT. DB unique constraint là lớp bảo đảm cuối cùng. Cũng phải kiểm soát collation/so sánh chuỗi của DB: nếu DB coi một cặp ký tự bằng nhau nhưng canonicalizer không coi bằng nhau, unique key có thể sinh va chạm bất ngờ. Không âm thầm dựa vào collation để thay chức năng chuẩn hóa ở ứng dụng.

## 3. Chọn một chính sách canonicalization rõ ràng

Không có một chính sách duy nhất phù hợp cho mọi tên người dùng. Đối với **username tự đặt** trong bài lab, chọn chính sách chủ động giới hạn ASCII:

1. Nhận chuỗi thô và kiểm tra giá trị null.
2. Chuẩn hóa Unicode dạng **NFKC**.
3. Bỏ whitespace đầu/cuối bằng `strip()`.
4. Đổi về chữ thường bằng `toLowerCase(Locale.ROOT)` để không phụ thuộc locale của JVM.
5. Chỉ nhận khóa cuối cùng thỏa `[a-z0-9][a-z0-9._-]{2,31}` — 3 đến 32 ký tự ASCII.
6. Dùng đúng khóa cuối cùng cho đăng ký, login, khôi phục, đổi tên và tra cứu repository.

| Input | Kết quả theo policy lab | Lý do |
| --- | --- | --- |
| `Alice` | `alice` | Lowercase |
| `  ALICE  ` | `alice` | Strip + lowercase |
| `ＡＬＩＣＥ` | `alice` | NFKC tương thích fullwidth |
| `alice` | `alice` | Đã canonical |
| `al ice` | Từ chối | Không cho whitespace trong khóa |
| `al​ice` có zero-width | Từ chối | Regex ASCII không nhận ký tự ẩn |
| `a` | Từ chối | Dưới 3 ký tự |
| `tênngười` | Từ chối **trong ví dụ ASCII này** | Muốn hỗ trợ tiếng Việt cần thiết kế Unicode khác |

**NFKC là một quyết định chính sách, không phải quy tắc bắt buộc cho mọi sản phẩm.** Nó gộp một số ký tự tương thích nhưng không loại được mọi trường hợp visually confusable, ví dụ ký tự từ bảng Cyrillic trông giống Latin. Unicode UTS #39 đưa ra các cơ chế nhận diện confusables và script restrictions. Nếu hỗ trợ username quốc tế, cần xây policy cho tập ký tự, normal form, script, hiển thị, version Unicode và xử lý collision. Chính sách ASCII trong lab đơn giản để có thể kiểm chứng được bằng test; không được áp dụng máy móc lên hệ thống có yêu cầu tên đa ngôn ngữ.

**Vì sao `Locale.ROOT`?** `toLowerCase()` không truyền locale có thể phụ thuộc môi trường máy; xử lý chữ `I` trong một số locale có khác biệt. Khóa định danh cần ổn định xuyên server/deployment. Cũng cần hiểu lowercase của Java **không hoàn toàn tương đương Unicode full case folding**; regex ASCII sau chuẩn hóa giới hạn kết quả của ví dụ.

**Idempotency:** `canonicalize(canonicalize(x)) = canonicalize(x)` với mọi x hợp lệ. **Collision:** Hai tên thô khác nhau có cùng key là **một định danh logic**; không được tạo hai tài khoản. **Stability:** Đổi policy hoặc phiên bản Unicode khi đã có user phải audit va chạm, giải quyết alias và migration có kiểm soát.

## 4. Username khác email và khác password

Email có quy tắc khác username: phần **domain** có liên quan đến case-insensitive DNS và IDNA; **local-part** có quy tắc phức tạp và có thể phụ thuộc nhà cung cấp. Không tự lowercase toàn bộ local-part, loại dấu chấm, xóa hậu tố `+tag` hoặc giả định mọi provider coi email tương đương như một dịch vụ phổ biến. Đăng nhập bằng email cần chính sách riêng, xác minh quyền sở hữu và định nghĩa key/email uniqueness nhất quán.

Mật khẩu là **bí mật**, không phải username. **Không** dùng `strip()`, `toLowerCase(Locale.ROOT)` hoặc NFKC của username để sửa password tùy tiện: việc đó có thể thay đổi bí mật và giảm entropy. Nếu hỗ trợ password Unicode, NIST SP 800-63B khuyến nghị **NFC ổn định** trước khi hash/verify; phải công bố và áp dụng nhất quán ở cả đăng ký và đăng nhập, không âm thầm thay đổi với user cũ. Mật khẩu phải được xác minh **toàn bộ**, không cắt cụt. Lựa chọn PasswordEncoder và giới hạn byte của thuật toán phải được kiểm tra rõ.

Tách ba khái niệm: **username canonicalization** để tìm account; **email verification** để chứng minh kênh liên lạc; **password hashing** để bảo vệ secret. Không dùng một hàm “normalizeAllStrings” cho cả ba.

## 5. Account enumeration: các kênh rò rỉ

Kẻ tấn công có thể dò tài khoản qua các khác biệt dưới đây:

| Kênh | Rò rỉ thường gặp | Cách giảm |
| --- | --- | --- |
| Thông báo UI | “Không có user” vs “Sai mật khẩu” | Một thông báo generic |
| HTTP status | 404 cho user lạ, 401 cho mật khẩu sai | Cùng loại status cho nhánh auth thất bại |
| Response body | Khác JSON field, code, độ dài | Schema/body nhất quán |
| Header/redirect | URL login lỗi, cookie, challenge khác | Kiểm tra phản hồi thực của toàn stack |
| Thời gian | User lạ trả nhanh, user thật chạy bcrypt/Argon2 | Dummy hash verify và kiểm soát scheduling |
| Quên mật khẩu | “Email đã được gửi” vs “Không có địa chỉ” | Thông báo giả định “nếu tài khoản tồn tại...” |
| Đăng ký | `username_exists=true` công khai không giới hạn | Đánh giá UX, xác minh ngoài băng, giới hạn tần suất |
| MFA/SSO | Hiện bước MFA hoặc provider cho tên có thật | Thiết kế luồng challenge không lộ sớm |
| Email/side effect | Chỉ known user tạo job đồng bộ và response chậm | Xử lý công việc nền, response chung |
| Khóa tài khoản | Known user có phản hồi khóa riêng | Không lộ trạng thái qua login public |

Thông báo lỗi công khai nên tương đương khi **user không tồn tại, password sai, account disabled hoặc locked**, theo OWASP Authentication Cheat Sheet. Với form login hoặc API, có thể dùng “Tên đăng nhập hoặc mật khẩu không hợp lệ”. Đối với HTTP Basic, một challenge 401 thống nhất có thể là hành vi phù hợp.

Không bắt mọi lỗi HTTP thành 401: request sai cấu trúc có thể 400; user đã xác thực nhưng không được phép một tài nguyên là 403. Mục tiêu là **không phân biệt các nhánh tồn tại tài khoản trong cùng thao tác kiểm tra credential**.

## 6. Tấn công đo thời gian và cách giảm chênh lệch

Đoạn pseudo-code sau có lỗi timing:

~~~text
account = repository.findByKey(usernameKey)
if account is missing:
    return 401            # Không có password hash verification
if !passwordEncoder.matches(password, account.passwordHash):
    return 401            # Có bcrypt/Argon2 tốn tài nguyên
~~~

Dù cả hai trả 401, kẻ tấn công có thể đo nhiều mẫu và suy ra nhóm tên nào phải chạy password hash. Không sử dụng `Thread.sleep(100)` cố định để “sửa”: có thể chặn event-loop, tạo độ lệch mới và tăng nguy cơ DoS.

**Quy trình tốt hơn:**

~~~text
canonicalKey = normalize(identifier) hoặc đánh dấu invalid
account = lookup(canonicalKey) hoặc empty
selectedHash = account.exists ? realHash : precomputedDummyHash
matches = passwordEncoder.matches(rawPassword, selectedHash)
if account.exists && account.enabled && matches:
    authenticated
else:
    generic BadCredentialsException
~~~

Mọi nhánh đều tốn một vòng password verification với hash đã được tạo bằng cùng kiểu thuật toán và work factor trong demo. Dummy hash tạo **một lần khi khởi động**, không tạo lại theo mỗi request. Nhánh disabled phải đi qua kiểm tra hash rồi mới trở về cùng lỗi generic.

**Không bảo đảm constant-time trên toàn HTTP.** Truy vấn DB, cache, index, work factor của hash cũ, scheduler, GC, gateway, network và độ dài username vẫn có thể làm phân phối thời gian khác nhau. Dummy verify chỉ giảm một kênh khác biệt rất rõ; cần đo thực tế, rate limiting, chống automation và quản lý tài nguyên. Hash password trên event-loop là rủi ro trong WebFlux; phải đưa sang scheduler phù hợp hoặc dùng authentication manager chuẩn đã xử lý tác vụ CPU-bound.

## 7. Vòng đời tài khoản phải dùng chung canonicalizer

~~~mermaid
flowchart TD
    A["Username đầu vào"] --> B["Canonicalization duy nhất"]
    B --> C{"Key hợp lệ?"}
    C -->|"Không"| D["Không lưu / luồng auth thất bại generic"]
    C -->|"Có"| E["username_key"]
    E --> F["Registration → DB UNIQUE"]
    E --> G["Login → repository lookup"]
    E --> H["Forgot password → lookup kín"]
    E --> I["Rename → kiểm tra collision + transaction"]
    F --> J["user_id bất biến"]
    G --> J
    H --> J
    I --> J
~~~

Đừng để controller đăng ký dùng lowercase, auth manager chỉ trim và reset-password lại tìm theo raw input. Đăng ký/đổi tên phải kiểm tra collision dựa trên khóa cuối cùng; login và reset không được xây khóa khác. Khi đổi username, ownership dữ liệu vẫn gắn theo `user_id`. Nếu hệ thống có SSO và identity linking, khóa từ IdP và username hiển thị không được tự đồng nhất với nhau.

## 8. Dự án Java 17+ để kiểm chứng hành vi

Bài mẫu dùng Spring Boot **3.3.13** và Spring Security 6.x cho lab WebFlux. Spring Boot 3.3 đã kết thúc hỗ trợ OSS; dự án production mới cần chọn phiên bản còn được hỗ trợ và điều chỉnh API theo phiên bản đó. Chạy được với JDK 17+, Maven và localhost:8080.

Ứng dụng dùng **HTTP Basic chỉ để trình diễn username/password authentication**. Không phát JWT hay tạo phiên đăng nhập sau khi nhập mật khẩu. Ngoài localhost, Basic phải đi qua **HTTPS** vì Base64 không mã hóa credential. Dự án thật cần policy mật khẩu, MFA, rate limit, audit, session/OAuth2/CSRF theo kiến trúc.

Cấu trúc:

~~~text
reactive-username-security/
├── pom.xml
└── src/
    ├── main/java/example/auth/
    │   ├── AuthApplication.java
    │   ├── UsernameKey.java
    │   ├── DemoAccountStore.java
    │   ├── CanonicalAuthenticationManager.java
    │   ├── SecurityConfig.java
    │   └── AccountController.java
    └── test/java/example/auth/
        └── AuthenticationPolicyTest.java
~~~

### 8.1. Maven

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-username-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chỉ dùng `spring-boot-starter-webflux`, không thêm `spring-boot-starter-web` trong lab.

### 8.2. Spring Boot application

File `src/main/java/example/auth/AuthApplication.java`:

~~~java
package example.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthApplication.class, args);
    }
}
~~~

## 9. Viết UsernameKey theo một chính sách cụ thể

File `src/main/java/example/auth/UsernameKey.java`:

~~~java
package example.auth;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public final class UsernameKey {

    private static final Pattern ALLOWED =
        Pattern.compile("[a-z0-9][a-z0-9._-]{2,31}");

    private UsernameKey() {
    }

    public static String of(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Invalid username");
        }

        String key = Normalizer
            .normalize(raw, Normalizer.Form.NFKC)
            .strip()
            .toLowerCase(Locale.ROOT);

        if (!ALLOWED.matcher(key).matches()) {
            throw new IllegalArgumentException("Invalid username");
        }

        return key;
    }
}
~~~

Hàm này **không truy vấn DB**, chỉ xác định khóa logic. `NFKC` và `Locale.ROOT` tránh một số biến thể nhập, regex hạn chế tập ký tự. Nó từ chối zero-width và control vì khóa cuối không thuộc ASCII hợp lệ. Đối với login, `IllegalArgumentException` phải được chuyển thành **authentication failure generic**; ở form chọn username mới có thể công bố điều kiện hợp lệ mà không tiết lộ tên nào đang có tài khoản.

## 10. Kho người dùng minh họa không blocking

File `src/main/java/example/auth/DemoAccountStore.java`:

~~~java
package example.auth;

import java.util.Map;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

record DemoAccount(
    String usernameKey,
    String passwordHash,
    boolean enabled
) {}

@Component
public class DemoAccountStore {

    private final Map<String, DemoAccount> byKey;

    public DemoAccountStore(PasswordEncoder encoder) {
        this.byKey = Map.of(
            "alice", new DemoAccount(
                "alice", encoder.encode("DemoPassword123!"), true),
            "bob", new DemoAccount(
                "bob", encoder.encode("BobPassword123!"), false)
        );
    }

    public Mono<DemoAccount> findByKey(String key) {
        return Mono.justOrEmpty(byKey.get(key));
    }
}
~~~

Hai account dùng để thử: Alice enabled, Bob disabled. Password demo xuất hiện trong source nên **không dùng trong sản phẩm thật**. In-memory Map là mô hình truy vấn không blocking để đơn giản hóa lab. Production dùng DB reactive có unique key, password hash và trạng thái nội bộ; nếu dùng JDBC blocking, phải xử lý ranh giới blocking đúng cách thay vì gọi trên event-loop.

## 11. ReactiveAuthenticationManager: cùng một lỗi công khai

File `src/main/java/example/auth/CanonicalAuthenticationManager.java`:

~~~java
package example.auth;

import java.util.List;
import java.util.UUID;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class CanonicalAuthenticationManager
        implements ReactiveAuthenticationManager {

    private record Candidate(DemoAccount account, String hash) {}

    private final DemoAccountStore accounts;
    private final PasswordEncoder encoder;
    private final String dummyHash;

    public CanonicalAuthenticationManager(
            DemoAccountStore accounts,
            PasswordEncoder encoder) {
        this.accounts = accounts;
        this.encoder = encoder;
        this.dummyHash = encoder.encode(UUID.randomUUID().toString());
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return Mono.empty();
        }

        String password = request.getCredentials() instanceof String text
            ? text : "";

        Mono<DemoAccount> lookup;
        try {
            lookup = accounts.findByKey(UsernameKey.of(request.getName()));
        } catch (IllegalArgumentException invalidName) {
            lookup = Mono.empty();
        }

        return lookup
            .map(account -> new Candidate(account, account.passwordHash()))
            .switchIfEmpty(Mono.just(new Candidate(null, dummyHash)))
            .flatMap(candidate -> Mono.fromCallable(() -> {
                // Chạy cùng phép kiểm tra password cho known/unknown.
                boolean validPassword =
                    encoder.matches(password, candidate.hash());

                DemoAccount account = candidate.account();
                if (!validPassword
                        || account == null
                        || !account.enabled()) {
                    throw new BadCredentialsException(
                        "Invalid username or password");
                }

                return (Authentication)
                    UsernamePasswordAuthenticationToken.authenticated(
                        account.usernameKey(),
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                    );
            }).subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

**Vì sao thiết kế như vậy?**

- Chuẩn hóa trước lookup. Tên sai định dạng và tên không tồn tại cùng đi qua `dummyHash` để không trả về ngay.
- Dummy hash được encode **một lần** trong constructor cùng thuật toán và cost với hash thật của lab. Nếu encode mới theo từng request có thể gây tiêu thụ CPU rất lớn.
- Hash thật và hash giả đều được kiểm chứng bằng `PasswordEncoder.matches(...)`. Account disabled cũng chỉ bị đánh giá **sau** phép kiểm tra mật khẩu, cuối cùng nhận cùng `BadCredentialsException`.
- `subscribeOn(Schedulers.boundedElastic())` tránh chạy bcrypt nặng trực tiếp trên event-loop. Cần benchmark scheduler và giới hạn số login đồng thời; trong hệ thống thật, một manager chuẩn Spring Security có thể phù hợp hơn tùy cơ chế xác thực.
- Khi thành công, tạo `Authentication` với principal canonical, credentials `null` và role demo. Không trả password, không log credential.
- Việc có dummy hash giảm timing discrepancy nhưng **không xóa hết** khác biệt DB/cache/scheduler/transport. Đây là ví dụ minh họa một lớp phòng vệ, không phải giải pháp authentication production đầy đủ.

## 12. SecurityWebFilterChain dùng manager tùy chỉnh

File `src/main/java/example/auth/SecurityConfig.java`:

~~~java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CanonicalAuthenticationManager manager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
~~~

`BCryptPasswordEncoder(10)` chỉ là cấu hình lab có cost không quá nặng để chạy test. Trong hệ thống mới, OWASP ưu tiên **Argon2id** khi phù hợp; chọn thuật toán/cost bằng benchmark, cơ chế nâng cấp hash và giới hạn tài nguyên. BCrypt thường giới hạn input thực tế ở **72 byte**, nên hệ thống dùng bcrypt phải bảo đảm không cắt mật khẩu ngầm và có policy độ dài phù hợp. NIST yêu cầu kiểm tra password đầy đủ.

HTTP Basic ở đây dùng để đưa username/password vào ReactiveAuthenticationManager. `authenticated()` không tự cấp quyền dữ liệu; endpoint nghiệp vụ thật còn phải kiểm tra role, owner/tenant, trạng thái tài nguyên. Spring WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, không dùng `HttpSecurity` của Servlet MVC.

## 13. Endpoint riêng tư và principal chuẩn hóa

File `src/main/java/example/auth/AccountController.java`:

~~~java
package example.auth;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "username", ctx.getAuthentication().getName()
            ));
    }
}
~~~

Khi gửi username `ALICE` với password đúng, manager ánh xạ tới `alice` và controller trả JSON:

~~~json
{"username":"alice"}
~~~

Đây là key nội bộ của ví dụ, **không phải display name**. Ứng dụng thật nên dùng user ID làm chủ thể ổn định cho mọi authorization dữ liệu.

## 14. Kiểm thử WebTestClient: các nhánh giống nhau

File `src/test/java/example/auth/AuthenticationPolicyTest.java`:

~~~java
package example.auth;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void keyNormalizesCaseWidthAndWhitespace() {
        assertEquals("alice", UsernameKey.of("Alice"));
        assertEquals("alice", UsernameKey.of("  ＡＬＩＣＥ  "));
        assertEquals("alice", UsernameKey.of("alice"));
        assertEquals("alice", UsernameKey.of(UsernameKey.of("Alice")));
    }

    @Test
    void invalidAndInvisibleUsernamesAreRejected() {
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("al\u200Bice"));
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("al ice"));
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("a"));
    }

    @Test
    void uppercaseAsciiUsernameLogsIntoCanonicalAccount() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("ALICE", "DemoPassword123!"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void anonymousIsRejected() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    private EntityExchangeResult<byte[]> rejected(
            String username, String password) {
        return client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(username, password))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .returnResult();
    }

    @Test
    void unknownWrongPasswordAndDisabledHaveEquivalentResponses() {
        EntityExchangeResult<byte[]> unknown =
            rejected("nobody", "wrong-pass");
        EntityExchangeResult<byte[]> wrong =
            rejected("alice", "wrong-pass");
        EntityExchangeResult<byte[]> disabled =
            rejected("bob", "BobPassword123!");

        // Cả ba đã được xác nhận status 401 ở helper rejected.
        assertArrayEquals(unknown.getResponseBody(),
                          wrong.getResponseBody());
        assertArrayEquals(unknown.getResponseBody(),
                          disabled.getResponseBody());

        String challenge = unknown.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE);
        assertEquals(challenge, wrong.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, disabled.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void invalidUsernameAtLoginStillUsesGeneric401() {
        rejected("a", "wrong-pass");
    }
}
~~~

Các kiểm thử xác minh canonicalizer idempotent, NFKC, chặn zero-width, HTTP Basic login với uppercase ASCII, và **cùng mã 401/body/challenge** cho unknown, wrong password, disabled. Nếu production dùng login JSON/form hay API Gateway, phải kiểm tra response schema, redirect, cookie, error page và cache headers trên **stack thật**.

**Lưu ý Unicode với HTTP Basic:** các API `setBasicAuth` có quy tắc charset riêng; không nên giả định truyền username fullwidth qua Basic luôn tương thích. Test NFKC được chạy trực tiếp trên `UsernameKey`, test HTTP dùng ASCII `ALICE`. Nếu cần Unicode username qua HTTP, chọn protocol/charset được hỗ trợ, test end-to-end và cân nhắc form JSON.

## 15. Chạy thử và đọc kết quả

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Gửi yêu cầu (`curl -u username` sẽ hỏi password, tránh lưu password trong command history):

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u ALICE http://localhost:8080/api/me
curl -i -u nobody http://localhost:8080/api/me
curl -i -u alice http://localhost:8080/api/me
curl -i -u bob http://localhost:8080/api/me
~~~

| Username | Password người dùng nhập | Kỳ vọng |
| --- | --- | --- |
| Không gửi Authorization | Không có | **401 Unauthorized** |
| ALICE | `DemoPassword123!` | **200 OK**, body `{"username":"alice"}` |
| nobody | Bất kỳ password sai | **401 Unauthorized** |
| alice | Một password sai | **401 Unauthorized** |
| bob | `BobPassword123!` | **401 Unauthorized** vì disabled, không công bố trạng thái |
| a | Một password bất kỳ | **401 Unauthorized**, lỗi định dạng không tiết lộ nhánh account |

Không khẳng định body mặc định của 401 luôn giống một JSON cụ thể. HTTP Basic thường trả challenge qua `WWW-Authenticate`; phần test kiểm tra dữ liệu thực của server.

## 16. Quên mật khẩu: phản hồi generic và công việc ngoài băng

Một endpoint quên mật khẩu không được nói “email không đăng ký” với người chưa xác thực. Trả cùng thông báo, ví dụ:

> Nếu thông tin khớp với một tài khoản, hướng dẫn khôi phục sẽ được gửi đến kênh liên hệ đã xác minh.

Với luồng reset:

1. Nhận username/email và chuẩn hóa bằng **policy đúng loại identifier**.
2. Trả status/body công khai nhất quán cho known/unknown account. Đừng trả masked email hoặc tên người dùng trước khi chứng minh quyền sở hữu.
3. Có thể tiếp nhận yêu cầu vào hàng đợi chống spam với phản hồi nhanh; phía xử lý kín tra cứu account và chỉ gửi khi đủ điều kiện. Tránh để việc “có gửi mail đồng bộ” làm thay đổi thời gian HTTP response rõ rệt.
4. Reset token phải được tạo ngẫu nhiên bằng nguồn mật mã, đủ mạnh, thời hạn ngắn, một lần dùng; lưu theo chính sách an toàn và gửi tới **kênh đã xác minh**.
5. Không khóa tài khoản hoặc đổi password chỉ vì ai đó gửi yêu cầu reset; cần xác thực token/challenge hợp lệ trước khi tác động đến account.
6. Bảo vệ endpoint khỏi spam và abuse bằng rate limit/quota theo nhiều chiều; không đưa reset token vào log, referrer hoặc analytics.

Pseudocode minh họa, **không phải chương trình Java độc lập**:

~~~text
POST /forgot-password { identifier }
    → kiểm tra shape và canonicalize
    → tiếp nhận yêu cầu với giới hạn tốc độ
    → trả response chung cho known/unknown

worker xử lý kín:
    → tra account
    → nếu đủ điều kiện: tạo single-use expiring token
    → gửi tới verified channel
    → audit outcome trong hệ thống nội bộ
~~~

Tránh suy luận rằng một câu trả lời chung tự làm thời gian bằng nhau. Việc tra DB, queue, mail provider, cache và rate limiting cũng có thể làm lộ sự khác biệt nếu diễn ra trong đường phản hồi.

## 17. Đăng ký: UNIQUE key và đánh đổi UX

Đăng ký cần tính `username_key` trước, sau đó INSERT theo unique constraint. Nếu hai người cùng gửi `Alice` và `ＡＬＩＣＥ`, cả hai thành `alice` và DB chỉ cho tồn tại một user. Một quy trình `SELECT trước rồi INSERT` không đủ để chống race khi có nhiều request đồng thời.

Với chức năng kiểm tra tên có sẵn công khai, việc cho biết username đã bị chiếm có thể giúp người dùng chọn tên, **đồng thời** cho kẻ xấu oracle dò tài khoản. Tùy threat model, có thể dùng xác minh email ngoài băng, hạn chế tần suất, CAPTCHA khi có dấu hiệu abuse, hoặc chấp nhận một mức lộ có kiểm soát. Không tuyên bố có thể che hoàn toàn account existence trong một workflow buộc phải hiển thị tên nào còn dùng được.

Nếu đổi chính sách canonicalizer cho hệ thống cũ, phải **kiểm kê collision và migration**. Không tự gộp account hay chuyển owner data khi hai username khác nhau đột nhiên có cùng key theo thuật toán mới. Dùng user ID bất biến giúp bảo toàn quan hệ dữ liệu.

## 18. Rate limiting, khóa tài khoản và chống brute force

Một giả hash bcrypt vẫn tốn CPU; attacker có thể làm nghẽn service bằng cách gửi rất nhiều request sai. Hệ thống production cần:

- Rate limit theo **IP/subnet, thiết bị/session, tenant, canonical identifier đã pseudonym hóa** và tổng tài nguyên server, thay vì chỉ khóa theo một username.
- Phát hiện password spraying (một password trên nhiều user), credential stuffing (nhiều cặp user/pass) và brute force trên một tài khoản.
- Throttle tăng dần, CAPTCHA/challenge khi phù hợp; không để quy tắc phản hồi của challenge vô tình tiết lộ account có thật.
- Tránh cơ chế khóa account tức thời chỉ do username bị thử nhiều, vì có thể gây **denial-of-service** cho user thật.
- Giới hạn độ dài input/request body, lượng hash verification đồng thời, CPU/scheduler và queue; chọn cost hash theo khả năng hệ thống.
- Audit kín, có correlation ID và dấu hiệu abuse; không in raw password, Authorization header, reset token hoặc identifier cá nhân khi không cần. Hash trần của email/username trong log có thể bị dò bằng từ điển; cần pseudonym có khóa/quyền truy cập và retention phù hợp.
- MFA/step-up phù hợp sau xác thực và theo chính sách, tránh hiển thị account/thiết lập MFA trước khi người dùng chứng minh đủ điều kiện.

Generic error và dummy hash **không thay thế rate limiting**. Một phản hồi 429 theo policy anti-abuse không được biến thành một tín hiệu tiết lộ chỉ user có thật; đo cả trường hợp bật throttle.

## 19. Kiểm thử timing và bề mặt phản hồi

Không viết assert `responseTime<100ms` để chứng minh chống enumeration. Với môi trường staging hợp lệ, dùng dữ liệu test, không dò tài khoản bên ngoài:

1. Warm up JVM/JIT, connection pool, password encoder và cache.
2. Tạo tập username known/unknown có độ dài và kiểu tương tự; request password **sai** cho cả hai, thêm trạng thái disabled.
3. Gửi request theo thứ tự ngẫu nhiên, thu đủ mẫu trong các mức tải khác nhau.
4. So sánh phân phối latency (median, p95, p99), response status, body bytes, headers, redirect, cookies và gateway behavior.
5. Kiểm tra hash cũ/mới khác work factor, cache hit/miss, rate limit, user bị khóa, login/reset/register, mail queue.
6. Nếu có sai khác đáng kể, điều tra từng tầng thay vì thêm sleep cố định rồi kết luận an toàn.

Không có bảo đảm “constant-time HTTP” tuyệt đối do network và scheduling. Đánh giá mức rủi ro thống kê, khả năng khai thác ở quy mô thực và các lớp phòng vệ tích hợp.

## 20. Những lỗi thực tế dễ mắc

1. **Chuẩn hóa chỉ ở đăng nhập:** signup tạo `Alice` còn login tìm `alice` → lỗi tra cứu hoặc duplicate.
2. **Thiếu Locale.ROOT:** cách đổi chữ có thể đổi theo locale server.
3. **Tin NFKC chặn mọi confusable:** các hệ chữ khác nhau vẫn có ký tự trông giống; cần Unicode policy phù hợp.
4. **Dùng username rule cho email/password:** có thể gộp nhầm hộp thư hoặc giảm entropy của secret.
5. **SELECT kiểm tra trùng nhưng thiếu UNIQUE:** race condition tạo tài khoản logic trùng.
6. **Hiển thị “user không tồn tại”:** lộ danh sách tài khoản.
7. **Body giống nhau nhưng status/header khác:** vẫn là oracle.
8. **Early return cho unknown:** user có thật chạy bcrypt, tạo timing signal.
9. **Tạo dummy hash mỗi request:** có thể gây DoS CPU.
10. **Gọi bcrypt trực tiếp trên event-loop:** tăng latency cho request khác trong WebFlux.
11. **Gọi Thread.sleep() để cân bằng thời gian:** blocking và không bảo đảm response tương đương.
12. **Quên mật khẩu gửi tên/email đã che sau lookup:** vẫn có thể lộ account.
13. **Tự khóa user khi có reset request:** attacker dễ gây gián đoạn.
14. **Đổi canonicalization policy sau khi có data mà không kiểm tra collision:** hai account khác nhau có thể bị gộp key.
15. **Log credential và email/username đầy đủ:** gây rủi ro lộ thông tin và phục vụ attacker.
16. **Chỉ test login thành công:** không chứng minh khả năng chống enumeration.

## 21. Bài tập vận dụng

**Bài A — bảng canonicalization:** tự tạo 12 tên gồm mixed case, fullwidth, whitespace, zero-width, dấu tiếng Việt, tên quá ngắn/quá dài. Chứng minh output hoặc lỗi của `UsernameKey` và idempotency.

**Bài B — account uniqueness:** thiết kế database có UNIQUE trên username_key. Gửi hai đăng ký đồng thời cho `Alice` và `ＡＬＩＣＥ`, chứng minh chỉ một bản ghi được lưu. Ghi rõ vì sao SELECT pre-check không bảo đảm duy nhất.

**Bài C — bề mặt lỗi đồng nhất:** chạy ba request unknown/wrong password/disabled qua WebTestClient và so sánh 401, body, challenge. Trong lab, thử sửa một nhánh thành 404 để thấy test phát hiện, rồi khôi phục.

**Bài D — timing:** thử loại bỏ dummy hash verification trong bản sao môi trường lab, đo phân phối thời gian known/unknown, giải thích sự khác biệt. Khôi phục dummy verification và rate limits.

**Bài E — reset password:** thiết kế sequence trả thông báo chung, xử lý email ngoài băng, token một lần, audit kín và chống spam. Viết test khi account tồn tại/không tồn tại đều không lộ qua response.

**Bài F — Unicode đa ngôn ngữ:** nếu muốn cho username tiếng Việt, thay chính sách ASCII như thế nào? Trình bày normalization, script restriction/UTS #39, test confusables, migration và collision.

### Checklist hoàn thành

- [ ] Phân biệt `user_id`, `username_display` và `username_key`.
- [ ] Chọn chính sách canonicalization và dùng thống nhất trong mọi luồng.
- [ ] Biết NFKC, Locale.ROOT và Unicode confusables; không tự gộp email/password như username.
- [ ] UNIQUE constraint ở DB bảo vệ khỏi race/collision.
- [ ] Unknown user, wrong password, disabled/locked đều trả thông báo đăng nhập công khai tương đương.
- [ ] Cả known và unknown đều trải qua phép kiểm tra password hash phù hợp.
- [ ] Không coi dummy hash là constant-time tuyệt đối; có rate limiting và timing test.
- [ ] PasswordEncoder đúng thuật toán/cost; không blocking event-loop.
- [ ] Quên mật khẩu, mời người dùng và đăng ký không lộ account qua response ngoài ý muốn.
- [ ] Có test âm tính và kiểm soát log/credential/rate limiting.

## 22. Câu hỏi tự kiểm tra

1. Vì sao cần cả username_display, username_key và user_id?
2. `Alice` với `ＡＬＩＣＥ` cùng key thì có nên cho tạo hai account không?
3. NFKC có giải quyết toàn bộ Unicode spoofing không?
4. Vì sao username ASCII của lab có thể không phù hợp cho sản phẩm nhiều ngôn ngữ?
5. Vì sao email local-part không thể tùy tiện lowercase/xóa dấu chấm?
6. Generic error message có đủ chống enumeration không? Nêu ba kênh khác.
7. Vì sao unknown user trả 401 nhanh có thể vẫn làm lộ tài khoản?
8. Vì sao hash giả nên được tạo một lần, rồi dùng `matches` ở nhánh unknown?
9. Khi disabled user nhập đúng password, phản hồi public nên xử lý ra sao?
10. Trong WebFlux, vì sao password hash CPU-bound không nên chạy trên event-loop?
11. Quên mật khẩu có nên làm đổi trạng thái tài khoản trước khi người dùng chứng minh token reset?
12. Khi đổi policy canonicalization trên database cũ, những va chạm nào cần giải quyết?

## 23. Tài liệu tham khảo chính thức

- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic message, discrepancy factors, account enumeration và chống tự động hóa.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): response nhất quán, reset token một lần, email ngoài băng.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id/bcrypt/PBKDF2, hash/cost và giới hạn input.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): WebFlux chain, HTTP Basic, reactive security configuration.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`.
- [Spring Security — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): giao diện xác thực Reactive.
- [Unicode — UAX #15](https://www.unicode.org/reports/tr15/): các normalization form, NFKC/NFC.
- [Unicode — UTS #39](https://www.unicode.org/reports/tr39/): identifier confusables và script restriction.
- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html): password verifier, Unicode và xác minh đầy đủ secret.

**Thông điệp cốt lõi:** Một hệ thống đăng nhập phải tính **một khóa username chuẩn ổn định**, ràng buộc **UNIQUE tại database**, rồi xác thực mà không tiết lộ công khai tài khoản có thật hay không. Trong Spring WebFlux, gộp các nhánh thất bại thành cùng một kết quả, tránh fast exit bằng dummy password verification, giữ tác vụ hash ngoài event-loop, giới hạn tần suất và kiểm thử cả response lẫn sai khác thời gian.