# Kiểm tra dependency, persistence và phiên bản trước khi bật OTT hoặc WebAuthn

## 1. Mục tiêu: đừng chỉ bật DSL rồi coi là hoàn tất

Spring Security cung cấp hai cơ chế đăng nhập hiện đại:

- **One-Time Token Login (OTT):** máy chủ phát một token dùng một lần, thường gửi qua email/SMS dưới dạng magic link. Người nhận nộp token trở lại để xác thực.
- **WebAuthn / Passkeys:** trình duyệt dùng Web Authentication API và một authenticator để đăng ký credential rồi ký assertion xác thực bằng khóa riêng; server lưu và kiểm chứng credential khóa công khai.

Cả hai đều có cấu hình trông rất ngắn:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
http.webAuthn(Customizer.withDefaults());
```

Nhưng **cấu hình biên dịch được không đồng nghĩa hệ thống sẵn sàng cho production**. OTT cần gửi token an toàn và dùng một kho token dùng một lần phù hợp khi có nhiều node. WebAuthn cần library đúng với phiên bản, kho credential tồn tại sau restart, xử lý challenge qua các request, cấu hình RP ID/origin/HTTPS và session serialization phù hợp. Bản vá bảo mật còn phụ thuộc phiên bản Spring Security cụ thể.

Bài này thuộc nhóm **Phiên bản**, tập trung vào quy trình kiểm tra trước khi bật tính năng, tránh hai lỗi phổ biến:

1. Sao chép một snippet cho Spring Security 7.x vào dự án 6.5 và không hiểu vì sao dependency/API biến mất.
2. Bật một giao diện đăng nhập chạy được trên localhost nhưng mất token/credential khi restart, lỗi khi qua load balancer, hoặc cho phép một đường đăng nhập yếu hơn chính sách bảo mật.

### Kết quả cần đạt

Sau bài học bạn phải tự trả lời được:
- Đang chạy **Spring Boot, Spring Security, Spring Framework, Java** phiên bản nào? Có một hay nhiều phiên bản Security cùng trên runtime classpath?
- OTT và WebAuthn được hỗ trợ từ bản nào, những dependency nào đúng **theo nhánh phiên bản**?
- Store nào đang giữ **OTT**, **WebAuthn registered credentials**, **WebAuthn user entity**, **registration/authentication options và challenge**, cùng **SecurityContext/session**?
- Khi restart hoặc đổi node, điều gì còn tồn tại, điều gì phải hết hiệu lực?
- Có HTTPS, RP ID, origin, session/CSRF và chính sách MFA phù hợp không?
- Có thể chạy test **one-time, expiry, credential persistence, multi-node, session round-trip và negative security cases** trước khi mở cho người dùng không?

Phạm vi chính: Java 17+, Spring Security Servlet / Spring MVC, đặc biệt Spring Security 6.5 và 7.x. WebFlux có API riêng được phân biệt ở phần sau. Ví dụ Java có ghi rõ cái nào độc lập và cái nào là cấu hình cần lắp vào ứng dụng.

## 2. Ma trận phiên bản: việc đầu tiên phải lập

| Hạng mục | Spring Security 6.3 trở về trước | 6.4 | 6.5 | 7.x |
| --- | --- | --- | --- | --- |
| Built-in `oneTimeTokenLogin` | Không có như DSL chuẩn 6.4+ | **Có** | Có, mở rộng cách cấu hình | Có; xem API/Javadoc nhánh đang chạy |
| Built-in `webAuthn`/Passkeys | Không có như DSL chuẩn 6.4+ | **Có** | Có | Có |
| WebAuthn dependency theo guide | Không áp dụng | WebAuthn4J phù hợp bản | **`spring-security-web` + `webauthn4j-core`** | **`spring-security-webauthn`** |
| WebAuthn credential repositories | Tự xây hoặc dùng thư viện khác | Map/in-memory; xem bản cụ thể | **JDBC repositories được bổ sung** | JDBC/custom tiếp tục được hỗ trợ |
| OTT default token store | Không áp dụng | In-memory | In-memory | In-memory nếu không chỉ định khác |
| OTT JDBC store | Không áp dụng | `JdbcOneTimeTokenService` | Có | Có |
| Tích hợp MFA bằng factor authorities | Không phải mô hình được đề cập ở đây | Không | Không có `FactorGrantedAuthority` 7.x | **Có** cơ chế MFA mới |
| Spring Boot điển hình | Các dòng cũ | Boot 3.x tương thích | Boot 3.x tương thích | Boot 4.x tương thích |

**Đây là ma trận năng lực, không phải bảng tương thích chính thức cho mọi patch.** Chọn Boot BOM/security BOM và đối chiếu Spring Boot compatibility matrix cụ thể. Không tự ghép Spring Boot 3 + một vài module Spring Security 7 rồi kỳ vọng chạy được.

Một thay đổi đặc biệt quan trọng: trong **guide Spring Security 6.5**, WebAuthn yêu cầu `webauthn4j-core` bên cạnh `spring-security-web`; trong **guide Spring Security 7.0+**, dùng **module riêng** `spring-security-webauthn`. Vì vậy, cách cài dependency **không được copy qua lại giữa hai nhánh**.

Ngoài tính năng, còn phải kiểm tra **bản vá bảo mật**. Chẳng hạn advisory **CVE-2026-47841 (20/08/2026)** ảnh hưởng WebAuthn với yêu cầu user verification `REQUIRED` và distributed HTTP session serialization trong những phiên bản được công bố. Bảng kiểm chi tiết ở mục 18.

## 3. Thứ tự quyết định trước khi chạm `SecurityFilterChain`

Áp dụng chuỗi sau cho ứng dụng thật:

```text
1. Ghi lại Boot / Security / Framework / Java version
              |
              v
2. Dependency tree sạch, đúng BOM và đúng WebAuthn module
              |
              v
3. Kiểm tra security advisories + chọn patch đã sửa lỗi
              |
              v
4. Quyết định Servlet hay WebFlux / SecurityFilterChain nào xử lý route
              |
              v
5. Chọn persistence cho OTT + WebAuthn + challenge + session
              |
              v
6. Chuẩn bị database schema, secret, TLS, origin, RP ID
              |
              v
7. Tạo delivery handler OTT và credential enrollment WebAuthn
              |
              v
8. Kiểm thử chức năng, bảo mật, restart, multi-node, rollback
              |
              v
9. Bật feature flag theo nhóm nhỏ, theo dõi, mở rộng dần
```

Nếu bất kỳ bước **dependency/persistence/patch/security** chưa đạt, không nên mở tính năng chỉ vì demo trên localhost chạy thành công. Thứ tự trên giúp chẩn đoán đúng nguyên nhân thay vì thử ngẫu nhiên các `@Bean` và các URL.

## 4. Kiểm tra dependency thực tế bằng Gradle

Trong dự án có Gradle wrapper (lệnh không đọc mã nguồn khi được dùng trong project bình thường):

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency webauthn4j-core --configuration runtimeClasspath
```

Nếu dùng Spring Security 7.x, kiểm tra thêm:

```bash
./gradlew dependencyInsight --dependency spring-security-webauthn --configuration runtimeClasspath
```

**Cần ghi nhận:**
- `spring-security-config`, `spring-security-core`, `spring-security-web`, `spring-security-crypto`, `spring-security-oauth2-*` có được resolve nhất quán không?
- Có module `spring-security-webauthn` trên nhánh 7.x không?
- 6.5 có `webauthn4j-core` từ bản được guide/BOM tương thích đề xuất không?
- Có dependency transitively kéo một bản `webauthn4j` khác vào classpath không?
- Có build override thủ công bằng `resolutionStrategy.force`, Gradle constraints, `ext['spring-security.version']` hay dependency trực tiếp pin khác BOM không?
- Artifact thực chạy trong container có giống classpath của CI không? `compileClasspath` sạch nhưng `runtimeClasspath` sai vẫn gây lỗi.

`dependencyInsight` chỉ hiện dependency **có trong graph của project**; nếu trả “no dependencies matching”, có thể tính năng chưa được khai báo. Không giải quyết bằng cách thêm ngẫu nhiên từng JAR tới khi IDE hết lỗi.

### Gradle configuration theo nhánh 6.5

**Snippet** cho `build.gradle` của một project Spring Boot 3.x đã có plugins và BOM phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    // Theo guide Spring Security 6.5: chọn version tương thích.
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

**Không** tự đưa `spring-security-webauthn` của 7.x vào dependency block này. Các `spring-security-*` được Boot BOM quản lý; version WebAuthn4J trong snippet là phiên bản được **guide 6.5** minh họa, **không phải lời khẳng định nó luôn mới nhất/an toàn nhất**. Kiểm tra tương thích và CVE theo bản patch đang triển khai.

Nếu chỉ thử **OTT** trên nhánh 6.5, không cần thêm WebAuthn4J. Ngược lại, chỉ WebAuthn không bắt buộc SMTP nếu không dùng OTT, nhưng phải có cơ chế recovery/enrollment phù hợp.

### Gradle configuration theo nhánh 7.x

**Snippet riêng** cho dự án Spring Boot 4.x và Spring Security 7.x tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-webauthn'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Để BOM giải quyết version `spring-security-webauthn` theo cùng họ Spring Security. Không thêm một bản `webauthn4j-core` theo hướng dẫn 6.5 chỉ vì nhìn thấy tên WebAuthn: dependency và library sẽ theo module/version 7.x được hỗ trợ, trừ khi tài liệu tương ứng yêu cầu khác.

**Các đoạn Gradle trên là danh sách dependencies**, không phải file build hoàn chỉnh: cần plugins/version Spring Boot tương thích, repository và cấu hình toolchain Java của dự án.

## 5. Nếu dùng Maven: xác minh `dependencyManagement`

Với Maven wrapper:

```bash
./mvnw --version
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=com.webauthn4j
./mvnw help:effective-pom
```

Trên PowerShell có thể dùng `.\mvnw.cmd` thay cho `./mvnw` khi project có Maven Wrapper cho Windows.

Đối chiếu `spring-boot-starter-parent` hoặc `spring-boot-dependencies` BOM. Nếu thấy `spring-security-web:6.5.x` bên cạnh `spring-security-config:7.x`, dừng lại. Các API Java có thể vẫn xuất hiện ở compile classpath, nhưng runtime có thể ném `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi khởi tạo filter chain.

**Không** dựa vào một dòng version trong IDE. Cần biết dependency được resolve sau toàn bộ parent, BOM, transitive constraints, profiles và cách đóng gói image thực tế.

## 6. Bật OTT cần những gì ngoài dependency?

Spring Security `oneTimeTokenLogin()` về mặt nghiệp vụ gồm hai giao dịch:

```text
User nhập định danh tại /ott/generate
                  |
                  v
GenerateOneTimeTokenFilter
                  |
                  v
OneTimeTokenService.generate(request)
                  |
                  v
Token có username, giá trị ngẫu nhiên, thời hạn
                  |
                  v
OneTimeTokenGenerationSuccessHandler
                  |
                  v
Gửi magic link/email/SMS đến kênh đã được xác minh
                  |
                  v
User nộp token /login/ott
                  |
                  v
OneTimeTokenService.consume(...)
                  |
                  v
OneTimeTokenAuthenticationProvider
                  |
                  v
Authentication thành công nếu chính sách cho phép
```

**Checklist cần có:**
- Có `UserDetailsService`/nguồn account phù hợp.
- Có kênh giao token **đáng tin** và `OneTimeTokenGenerationSuccessHandler` thật.
- Có store `OneTimeTokenService` có TTL, kiểm soát dùng một lần, dọn hết hạn.
- Có giới hạn request, audit và chống dò sự tồn tại account.
- Có HTTPS/đường link và reverse-proxy URL đúng (không lấy host header tùy tiện để tạo phishing link).
- Có CSRF/session policy; recovery/login không bypass account locked/disabled hoặc yêu cầu MFA theo chính sách.
- Nếu chạy cluster, token được tạo trên node A phải được consume trên node B.
- Có fallback nếu kênh email/SMS không sẵn sàng; không log hoặc trả token raw ra HTTP response.

**OTT không phải TOTP/HOTP.** Server phát một token dùng một lần, gửi tới kênh được chọn. TOTP/HOTP dựa trên secret chung đã enroll và bộ đếm/thời gian. Bật `oneTimeTokenLogin()` không tự tích hợp ứng dụng Authenticator để xác minh mã TOTP.

## 7. OTT persistence: mặc định in-memory dùng khi nào?

Nếu không cung cấp custom `OneTimeTokenService`, Spring Security dùng `InMemoryOneTimeTokenService`. Đây là triển khai hữu ích để thử tính năng:

- Đơn giản, không cần bảng DB.
- Phù hợp demo local, test độc lập và môi trường một instance ngắn hạn.
- Token biến mất khi process restart; không chia sẻ giữa JVM khác.
- Không tự đủ cho deployment nhiều replicas sau load balancer.
- Không giải quyết recovery email delivery/monitoring.

Tình huống thất bại thực tế:

```text
POST /ott/generate  -> node A -> in-memory Map trên A
Email chứa token x
POST /login/ott     -> node B -> Map trên B không có x
                       -> authentication failed
```

**Giải pháp production điển hình:** `JdbcOneTimeTokenService` hoặc `OneTimeTokenService` tùy chỉnh dùng kho tập trung, có chiến lược consume một lần đáng tin. Không dùng session stickiness thay cho token persistence bền vững khi yêu cầu failover/restart.

## 8. OTT persistence qua JDBC: dependency và schema

Spring Security cung cấp `org.springframework.security.authentication.ott.JdbcOneTimeTokenService`, khởi tạo bằng `JdbcOperations`:

```java
@Bean
OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
    return new JdbcOneTimeTokenService(jdbc);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;
```

Đây là **snippet cho `@Configuration` class**. Cần `spring-boot-starter-jdbc`, `DataSource` được cấu hình đúng, database driver, migration script và quyền DB phù hợp. Bean này có thể được DSL `oneTimeTokenLogin` nhận tự động; nếu có **nhiều `SecurityFilterChain`** hay nhiều token services thì xác minh chain nào dùng bean nào.

**Schema resource chính thức** được Javadoc `JdbcOneTimeTokenService` 6.5 chỉ rõ:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

Nó **phải được tạo trong database trước khi dùng service**. Đừng suy rằng chỉ thêm dependency JDBC thì Spring Boot sẽ tự triển khai schema trong production.

### Schema test khác schema production

Ví dụ trong một **test profile dùng embedded H2** có thể nạp resource chính thức:

```java
DataSource dataSource = new EmbeddedDatabaseBuilder()
    .setType(EmbeddedDatabaseType.H2)
    .addScript(
        "classpath:org/springframework/security/core/ott/jdbc/"
        + "one-time-tokens-schema.sql"
    )
    .build();
```

Imports cần:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
```

Đây là **snippet chạy trong unit/integration test**; không copy thẳng cấu hình `EmbeddedDatabaseBuilder` vào production.

Với PostgreSQL/MySQL/Oracle:
1. Đọc **resource DDL của đúng JAR/version**.
2. Chuyển cú pháp SQL cho dialect của bạn nếu cần.
3. Tạo migration có version bằng Flyway/Liquibase.
4. Đặt index, ràng buộc và quyền DB phù hợp.
5. Chạy migration trước rollout ứng dụng.
6. Test được dùng một lần, hết hạn và cleanup.
7. Theo dõi bảng/token volume và DB health.

Không tạo câu SQL đoán tên cột rồi chạy trên production. Tên resource là nguồn tin cậy nhất vì schema có thể thay đổi theo phiên bản.

## 9. OTT: sự khác biệt giữa phát token, lưu token và gửi token

Ba việc sau tách biệt:

| Bước | Framework làm gì? | Bạn phải làm gì? |
| --- | --- | --- |
| Generate | `OneTimeTokenService.generate(...)` tạo token | Chọn TTL/policy và store đáng tin |
| Persist | In-memory hoặc JDBC/custom store | Chuẩn bị schema, cleanup, cluster, concurrency |
| Deliver | Hook `OneTimeTokenGenerationSuccessHandler` | Giao đến email/SMS **đã xác minh**, retry và chống abuse |
| Consume | `OneTimeTokenService.consume(...)` tìm và dùng token | Test single-use, expiry, transaction/atomicity dưới tải |
| Authenticate | Provider tạo Authentication theo cấu hình | Kiểm tra account status, role, MFA, session/cookie policy |

Nếu trong môi trường phát triển bạn **in token lên stdout** rồi nhập bằng tay, đó là tiện ích thử nghiệm chứ **không** phải delivery handler an toàn. Token có thể bị rò qua log shipping, tracing, screenshot hoặc history.

Nếu dùng magic link, đặt base URL server-side từ cấu hình tin cậy thay vì tự xây bằng `Host`/`Forwarded` header chưa được proxy kiểm soát. Một URL đúng khi chạy `localhost:8080` có thể thành `http://internal-service:8080` sau reverse proxy nếu không thiết kế forwarded headers và public hostname.

### Một đoạn cấu hình OTT 6.5 tối thiểu

File ví dụ `src/main/java/example/auth/OttSecurityConfig.java` trong dự án Servlet Spring Boot 3.x:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OttSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .oneTimeTokenLogin(withDefaults());

        return http.build();
    }

    @Bean
    OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
        return new JdbcOneTimeTokenService(jdbc);
    }
}
```

**Giới hạn rõ:** file trên có thể **biên dịch** với dependencies 6.5 phù hợp và JDBC, nhưng **chưa phải một ứng dụng OTT production tự vận hành**. Còn phải cấu hình `UserDetailsService`, database/schema, `OneTimeTokenGenerationSuccessHandler` giao token an toàn, gửi email/SMS thực và các security controls. Phần cấu hình filter mặc định tạo login UI/submit page; nếu app có login page tùy chỉnh phải kiểm tra sự khác biệt.

Nếu bạn đang có `SecurityFilterChain` hiện hữu, **gộp** snippet vào chain đúng thay vì tạo chain thứ hai với `anyRequest()` trùng khớp rồi vô tình chiếm route của chain cũ.

## 10. OTT token TTL và điều kiện dùng một lần

`GenerateOneTimeTokenRequest` có constructor nhận username và `Duration`, ví dụ:

```java
GenerateOneTimeTokenRequest request =
    new GenerateOneTimeTokenRequest(
        "alice",
        java.time.Duration.ofMinutes(5)
    );

OneTimeToken token = service.generate(request);
```

Imports:

```java
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.OneTimeToken;
```

Đây là **snippet trong test/service code** với `OneTimeTokenService service` đã có; không phải controller phục vụ request công khai.

Các hành vi cần test:

1. Token hợp lệ được consume **một lần**.
2. Cùng token gọi lần hai phải thất bại.
3. Token đã quá `expiresAt` phải bị từ chối.
4. Hai requests **đồng thời** consume cùng token chỉ được có một lần thành công, kể cả qua hai node/connection DB.
5. Token sinh ở A được consume ở B khi cùng shared store.
6. Token không thể dùng cho account/transaction khác nếu chính sách yêu cầu ràng buộc.
7. Token không xuất hiện trong log, metrics tags, URL analytics/referrer bên ngoài.
8. Xóa dữ liệu hết hạn và retry cleanup không hủy token còn hợp lệ.
9. Dữ liệu token không tồn tại vĩnh viễn sau logout/disable/password reset nếu chính sách yêu cầu thu hồi.

**Chú ý:** chỉ test hai lời gọi tuần tự không chứng minh nguyên tử khi hai requests chạy đồng thời. Với custom JDBC implementation cần có transaction/delete/update conditions đủ mạnh; dù dùng JDBC tích hợp, vẫn nên integration-test trên database/dialect thật.

`JdbcOneTimeTokenService` có `setCleanupCron(...)`, `cleanupExpiredTokens()` và clock cho test; mặc định cleanup khoảng **mỗi giờ** theo Javadoc 6.5. Dọn bản ghi hết hạn là chuyện riêng với việc **từ chối dùng token đã hết hạn**.

## 11. OTT không tự giải quyết trạng thái tài khoản và MFA

Một số quy tắc phải được test độc lập:

- Tài khoản bị khóa, disabled, expired có được phép đăng nhập bằng OTT không?
- Có route password-only hoặc magic-link-only vẫn cho vào khu vực bắt buộc MFA không?
- Nếu reset email hoặc account recovery, token đang lưu có bị thu hồi không?
- Nếu một email bị chiếm, kẻ tấn công có thể dùng magic link để lấy quyền tương đương admin không?
- OTT có được coi là factor độc lập với một factor khác theo chính sách thực tế không?

Không tự giả định `OneTimeTokenAuthenticationProvider` luôn thực hiện **toàn bộ** account status checks giống `DaoAuthenticationProvider`. Kiểm tra Javadoc và cấu hình provider **của đúng phiên bản**; với 7.x có tùy chọn `UserDetailsChecker`, còn bản 6.x cần rà behavior trước khi chốt. Bài test account disabled qua mỗi đường đăng nhập là quan trọng hơn suy đoán dựa vào tên class.

Spring Security 7.x có mô hình MFA qua `FactorGrantedAuthority` và authorization manager, nhưng **bật thêm OTT và WebAuthn không tự bắt mọi tài khoản phải dùng cả hai**. Xác định chính sách theo tài nguyên: password + OTT, WebAuthn user-verifying, hoặc những tổ hợp được phê duyệt.

## 12. WebAuthn: cần hai giai đoạn, không chỉ một nút “Đăng nhập bằng passkey”

WebAuthn có hai nghi thức lớn:

```text
ENROLL / REGISTRATION
User đã được nhận diện
   |
   v
Server tạo PublicKeyCredentialCreationOptions + challenge
   |
   v
Browser navigator.credentials.create(...)
   |
   v
Authenticator tạo credential key pair
   |
   v
Browser gửi attestation/credential response
   |
   v
Server kiểm tra challenge, origin, RP ID, policy
   |
   v
LƯU user entity + public key credential liên kết account

AUTHENTICATION
Browser yêu cầu challenge từ server
   |
   v
navigator.credentials.get(...)
   |
   v
Authenticator ký assertion bằng private key
   |
   v
Server kiểm tra challenge, signature, origin, RP ID,
UP/UV, credential record, status và replay
   |
   v
Authentication thành công nếu policy cho phép
```

**Private key không được đưa vào database server.** Database cần giữ public key, credential identifier và metadata đủ để xác minh assertion; phần dữ liệu chính xác do các repository/version quyết định.

**Đăng ký credential và xác thực assertion là hai endpoint/flow khác nhau**. Việc navigator trả về credential chưa đủ; server phải kiểm chứng ceremony. Nếu chưa có credential đã đăng ký, login passkey không có gì để verify, trừ khi có cơ chế federated/registration riêng được thiết kế.

## 13. WebAuthn persistence có tối thiểu hai loại repository

Trong Spring Security 6.5, tài liệu mô tả:

| Repository | Dữ liệu đảm nhiệm | Triển khai tích hợp |
| --- | --- | --- |
| `PublicKeyCredentialUserEntityRepository` | User entity/handle WebAuthn liên kết danh tính | Map/in-memory hoặc **`JdbcPublicKeyCredentialUserEntityRepository`** |
| `UserCredentialRepository` | Credential records: id, public key, liên kết user, metadata | Map/in-memory hoặc **`JdbcUserCredentialRepository`** |
| `PublicKeyCredentialCreationOptionsRepository` | Options/challenge registration giữa các request | Mặc định qua **`HttpSession`**; có thể customize |
| Authentication request/challenge state | Options dùng verify assertion và session/correlation tương ứng | Kiểm tra implementation/phiên bản và cấu hình session |
| `SecurityContextRepository` | Authentication sau khi login | Theo mô hình session/security context đã chọn |

**Không gộp hai ý “credential persistence” và “challenge persistence”.** Credential đăng ký phải tồn tại lâu dài để lần sau user đăng nhập. Challenge/options thường **ngắn hạn**, ràng buộc một ceremony và có thể được lưu trong session. Dù credential đã lưu bền, nếu challenge mất khi qua node khác, đăng ký hoặc xác thực vẫn thất bại.

Default repository in-memory phù hợp demo; **restart JVM có thể làm mất passkey registrations**. Trước rollout production phải chọn JDBC/custom shared repository và thiết kế backup, schema migrations, ownership và audit.

### JDBC repository beans cho WebAuthn 6.5

File ví dụ `src/main/java/example/auth/WebAuthnRepositoryConfig.java`:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.web.webauthn.management
    .JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management
    .JdbcUserCredentialRepository;

@Configuration
public class WebAuthnRepositoryConfig {

    @Bean
    JdbcPublicKeyCredentialUserEntityRepository userEntityRepository(
            JdbcOperations jdbc) {
        return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
    }

    @Bean
    JdbcUserCredentialRepository userCredentialRepository(
            JdbcOperations jdbc) {
        return new JdbcUserCredentialRepository(jdbc);
    }
}
```

**Lưu ý khi copy vào IDE:** `import` Java **phải nằm trên một dòng**, ví dụ:

```java
import org.springframework.security.web.webauthn.management.JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.JdbcUserCredentialRepository;
```

Trong file chạy thật, dùng **hai dòng import đầy đủ phía dưới** thay cho các dòng import đã ngắt để trình bày. Cần Spring Security 6.5 có JDBC WebAuthn support, `JdbcOperations`, tables đã migrate và dependency WebAuthn4J đúng version.

Nếu muốn custom storage (MongoDB/SQL không chuẩn), implement đúng hai interfaces và kiểm tra concurrency/ownership/uniqueness/replay, không chỉ override một method `save`.

## 14. WebAuthn JDBC schema theo resource chính thức

Javadoc Spring Security 6.5 về hai JDBC repositories chỉ rõ hai resource:

```text
classpath:org/springframework/security/user-entities-schema.sql
classpath:org/springframework/security/user-credentials-schema.sql
```

**Đây là schema WebAuthn**, khác với:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

của OTT.

Không chạy script `users.ddl` dành cho JDBC `UserDetailsManager` rồi nghĩ nó tự tạo WebAuthn credentials. **Cùng chữ "user" nhưng là bảng/đối tượng khác nhau**.

Trình tự migration khuyến nghị:
1. Xác định Spring Security patch version trong artifact production.
2. Mở **DDL resource trong JAR đúng phiên bản** để biết tên bảng/cột/index/FK.
3. Chuyển DDL thành Flyway/Liquibase migration cho RDBMS mục tiêu.
4. Có ràng buộc duy nhất credential ID và user handle theo mô hình repository.
5. Xem xét quan hệ giữa WebAuthn user entity và account database: đổi username không được làm mất credential mapping; user handle nên ổn định.
6. Rà `signCount`, transports, discoverability/backup metadata, label và cột cần cập nhật khi authenticating.
7. Quyền `SELECT/INSERT/UPDATE/DELETE` chỉ cấp cho service thích hợp.
8. Backup/restore; test old registered credential sau restart/restore.
9. Thử đăng ký cùng credential đồng thời để kiểm tra uniqueness.
10. Kiểm tra không một user quản lý/delete credential của account khác.

**Không** lưu raw private key người dùng trong database server. Không log public-key credential response toàn phần nếu chứa định danh hoặc metadata nhạy cảm không cần thiết.

## 15. Hai ví dụ bật WebAuthn theo đúng nhánh

### 15.1. Spring Security 6.5 (Spring Boot 3.x)

**Snippet** gắn vào `SecurityFilterChain` đã có:

```java
http
    .formLogin(withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("login.example.com")
        .allowedOrigins("https://login.example.com")
    );
```

Imports:

```java
import static org.springframework.security.config.Customizer.withDefaults;
```

Nếu ứng dụng triển khai tại `https://login.example.com`, RP ID có thể là `login.example.com` theo chính sách domain hợp lệ, và `allowedOrigins` phải chứa **origin thực** (scheme + host + cổng nếu không mặc định). Những giá trị trên là **ví dụ domain**, không phải cấu hình chung nên sao chép.

Dự án 6.5 cần `webauthn4j-core`, các repository JDBC nếu muốn persistence, HTTPS và browser hỗ trợ Web Authentication. Khi dùng default registration page, cần bảo vệ thao tác thêm/xóa credential theo policy; không cho một remember-me session yếu tự đăng ký passkey rồi chiếm account.

### 15.2. Spring Security 7.x (Spring Boot 4.x)

DSL cũng có dạng:

```java
http
    .formLogin(withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("login.example.com")
        .allowedOrigins("https://login.example.com")
    );
```

**Nhưng dependency khác:** module `org.springframework.security:spring-security-webauthn`. Đặc biệt, sau major upgrade phải kiểm tra imports, API của repositories, serialization, nullability/Jackson và patch advisory chứ không dùng việc “DSL nhìn giống” làm bằng chứng binary compatibility.

**Không** đặt `@EnableMultiFactorAuthentication` của 7.x vào nhánh 6.5. Nếu dùng MFA policy, xem hệ thống đang lưu factor authorities và yêu cầu factor nào trên các protected routes. Bật WebAuthn không tự biến mọi request vào hệ thống thành user-verifying WebAuthn.

## 16. RP ID, origin, TLS, trình duyệt và reverse proxy

Trước khi bật WebAuthn, kiểm tra:

- **Secure context:** trình duyệt thường chỉ cho Web Authentication API trên HTTPS (localhost có ngoại lệ phát triển).
- **RP ID:** domain ID của relying party mà authenticator gắn credential; nó phải hợp lệ với origin hiện tại theo tiêu chuẩn WebAuthn.
- **Allowed origins:** tập origin hợp lệ *đúng* protocol, hostname, port. `https://example.com` không giống `https://login.example.com`, và không giống `http://login.example.com`.
- **Public hostname qua proxy:** khi TLS terminate ở load balancer, Spring app phía sau có thể thấy internal HTTP host nếu cấu hình forwarded headers sai.
- **Không lấy RP ID/origin từ input client tùy tiện.** Kênh `Host`/`X-Forwarded-*` phải qua trusted proxy và allowlist.
- **Credential portability:** thay hostname hoặc RP ID sau khi user đã enroll có thể làm credential cũ không dùng được ở domain mới. Phải có migration/transition strategy.
- **Browser và authenticator:** test platform passkey, roaming security key, desktop/mobile và các browser được hỗ trợ thực.
- **User verification policy:** `preferred`, `required` và `discouraged` khác nhau; nếu server thực sự yêu cầu UV, phải enforce đúng ở verification, không chỉ trong UI.
- **Authenticator device loss:** trước rollout phải có ít nhất một recovery mechanism được review, không reset factor bằng một link yếu hơn.
- **Username-less login:** user handle và credential mapping phải ổn định/duy nhất, không suy user từ email field trước khi assertion được kiểm chứng.

Kiểm thử một passkey tạo từ Chrome/Windows trên localhost **không** chứng minh production reverse proxy và hostname đúng.

## 17. Challenge, options và session: bền lâu hay ngắn hạn?

WebAuthn yêu cầu challenge không đoán được và được server kiểm chứng, gắn với một ceremony. Trong Spring Security 6.5, `PublicKeyCredentialCreationOptionsRepository` mặc định persist creation options qua **`HttpSession`**; vì vậy flow đăng ký có thể phụ thuộc session giữa:

```text
POST /webauthn/register/options    -> cấp challenge, lưu options
navigator.credentials.create(...)   -> browser + authenticator
POST /webauthn/register             -> đọc options/challenge, verify
```

Tương tự authentication:

```text
POST /webauthn/authenticate/options
navigator.credentials.get(...)
POST /login/webauthn
```

Tại đây:
- **Credential record** cần bền vững nhiều tháng/năm theo lifecycle account.
- **Challenge/options** chỉ cần tồn tại đủ lâu để hoàn thành ceremony, rồi phải được quản lý chống replay.
- **Session/SecurityContext** có lifecycle login khác nữa.

Nếu options nằm trong session cục bộ node A, request hoàn tất ceremony đi node B có thể mất dữ liệu. Cần quy hoạch **Spring Session Redis/JDBC**, tương đương shared session, hoặc repository options phù hợp; load balancer stickiness có thể là giải pháp tạm hạn chế nhưng không đảm bảo failover.

### Khi dùng Redis/JDBC sessions

Kiểm tra:
1. Objects trong `SecurityContext` và options có serialize/deserialize theo serializer thực tế không?
2. Session cookie có được browser gửi xuyên các bước không (SameSite, Secure, domain, Path)?
3. CSRF token có được tạo/gửi đúng khi POST options/register không?
4. Session có hiệu lực đủ lâu cho thao tác, nhưng không mở quá rộng?
5. Khi user đăng nhập hoặc đăng ký passkey, session rotation/CSRF/state có được xử lý?
6. App nhiều nodes có cùng Spring Security jars, serializers, secrets và RP policy?
7. Sau restart/node switch, options/challenge có được khôi phục đúng?
8. Sau consume, ceremony tương tự không dùng lại challenge được nếu policy yêu cầu?
9. Không ghi raw challenge hoặc assertion nhạy cảm vào log/bộ nhớ cache công khai.

**Điểm rất quan trọng:** persistence của credential records và persistence của challenge/options là **hai bài toán riêng**. Một JDBC user credential repository không tự chữa lỗi session serialization.

## 18. Bản vá bảo mật WebAuthn và phiên bản 2026 cần kiểm tra

Theo advisory chính thức **Spring Security CVE-2026-47841**, công bố ngày **20/08/2026**: trong điều kiện WebAuthn có `userVerification=REQUIRED` và distributed HTTP session store (Redis/JDBC/Hazelcast), quá trình deserialize một `UserVerificationRequirement` có thể khiến kiểm tra identity sai và yêu cầu UV bị bỏ qua ở những phiên bản bị ảnh hưởng.

Phạm vi được công bố:

| Nhánh | Phiên bản bị ảnh hưởng | Phiên bản sửa / kênh cung cấp theo advisory |
| --- | --- | --- |
| Spring Security 7.1 | 7.1.0 | **7.1.1** (OSS) |
| Spring Security 7.0 | 7.0.0–7.0.6 | **7.0.7** (OSS) |
| Spring Security 6.5 | 6.5.0–6.5.11 | **6.5.12** (Enterprise Support) |
| Spring Security 6.4 | 6.4.0–6.4.18 | **6.4.19** (Enterprise Support) |

**Diễn giải đúng:** đây là một advisory theo điều kiện cụ thể; không khẳng định mọi ứng dụng WebAuthn dùng session đều bị bypass. Nhưng nếu ứng dụng thuộc tập điều kiện đó, **không nên rollout** một bản bị ảnh hưởng. Chọn một patch được hỗ trợ/có bản sửa, kiểm tra advisory và test session serialization/UV thực tế.

Tham khảo: https://spring.io/security/cve-2026-47841/

Ngoài advisory này, phải kiểm tra **các security advisories mới hơn** theo thời điểm release thật: Spring Security, Spring Framework, WebAuthn4J, Spring Session, Jackson, JDBC driver, và Boot. Một checklist tĩnh không thể thay thế SCA/CVE scan trong CI.

### Lỗi serialization khác nhưng cũng cần test

Khi lưu WebAuthn Authentication/options qua Spring Session JDBC/Redis, những phiên bản cũ có thể gặp serialization incompatibility. Có tài liệu hỗ trợ Broadcom mô tả cải tiến serializability ở nhánh 7.1. Đây là **loại lỗi vận hành khác** với vulnerability bypass UV. Test phải phân biệt:
- `NotSerializableException` hoặc deserialize failure → login flow hỏng.
- Session round-trip thành công nhưng policy UV bị bỏ qua → **lỗi bảo mật** nghiêm trọng.
- Credential không tìm được trong repository → persistence/mapping.
- `Origin`/`RP ID` không khớp → cấu hình WebAuthn.

Không “fix” bằng cách hạ `userVerification` từ `required` xuống `preferred` để bỏ lỗi. Chọn patch và policy phù hợp.

## 19. Bảo vệ luồng registration/enrollment

Khi user vừa đăng nhập một yếu tố, có nên cho `POST /webauthn/register` để thêm một passkey mới không? Đây là quyết định bảo mật quan trọng.

Một passkey mới có thể trở thành **phương pháp đăng nhập lâu dài**. Vì vậy cần:
- Xác thực danh tính current user từ SecurityContext **được server kiểm chứng**.
- Reauthentication/step-up mới cho thao tác thêm/xóa factor theo risk level.
- CSRF protection cho các POST registration/options qua cookie session.
- Ngăn user A đăng ký credential vào account B qua body/path parameter.
- Unique credential ID và user handle ổn định.
- Không tự cấp quyền cao từ metadata label tự nhập.
- Giới hạn số credentials/thiết bị hợp lý; xử lý race khi hai tab enroll.
- Audit/notification khi thêm/xóa passkey hoặc đổi email recovery.
- Có quy trình mất authenticator và thu hồi credential kịp thời.
- Tài khoản `disabled` hoặc `locked` không được bypass qua đường passkey/OTT nếu policy không cho.

WebAuthn bảo vệ bằng crypto mạnh nhưng **không tự bảo vệ toàn bộ account management endpoints**.

## 20. `SecurityContext` persistence khác token/credential persistence

Một app có thể lưu OTT bằng JDBC và WebAuthn credentials bằng JDBC nhưng sau authentication, **session không được lưu đúng** hoặc bị xóa khi node switch. Spring Security 6.x dùng `SecurityContextRepository` để lưu/khôi phục Authentication trong các Servlet request; custom login phải lưu context rõ ràng.

Hình dung ba kho:

```text
OTT token DB
    -> Chỉ tồn tại đến khi consume/expire.

WebAuthn Credential DB
    -> Tồn tại lâu dài cho nhiều lần login.

Spring SecurityContext / HTTP session
    -> Lưu Authentication của browser giữa các request.
```

Chúng có thể dùng cùng PostgreSQL instance nhưng **bảng và lifecycle khác**. `JdbcOneTimeTokenService` không thay `HttpSessionSecurityContextRepository`, và `JdbcUserCredentialRepository` không đồng nghĩa có shared Spring Session.

Trong ứng dụng **stateless JWT**, sau login kết quả có thể chuyển thành access token; đó là cơ chế persistence khác. Cookie login thường cần session hoặc một authentication repository phù hợp.

### Cảnh báo custom login

Nếu bạn tự viết controller sau khi xác thực:

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(
    context, request, response
);
```

**Đây là snippet**, chỉ hợp lệ khi `authentication` đã được `AuthenticationManager`/provider xác thực; có `SecurityContextRepository`, Servlet request/response và session strategy phù hợp. Không tạo `Authentication` authenticated từ username tùy ý để “làm cho login hoạt động”.

## 21. Java 17 độc lập: minh họa readiness gate

Chương trình này là **mô hình học tập bằng JDK**, không gọi Spring Security và không thể thay thế dependency tree, CVE scan, browser hoặc integration tests. Nó giúp định nghĩa một **tiêu chí triển khai rõ** thay vì nói mơ hồ “bật là được”.

Tạo file `AuthFeatureReadinessDemo.java`:

```java
public class AuthFeatureReadinessDemo {

    record Environment(
        boolean versionsAligned,
        boolean patchApproved,
        boolean httpsAndOriginCorrect,
        boolean ottSharedStore,
        boolean ottDeliveryReady,
        boolean webAuthnCredentialStore,
        boolean webAuthnChallengeRoundTrip,
        boolean recoveryReady) {}

    static String ott(Environment env) {
        boolean ready =
            env.versionsAligned()
            && env.patchApproved()
            && env.ottSharedStore()
            && env.ottDeliveryReady()
            && env.recoveryReady();
        return ready ? "READY" : "BLOCK";
    }

    static String webAuthn(Environment env) {
        boolean ready =
            env.versionsAligned()
            && env.patchApproved()
            && env.httpsAndOriginCorrect()
            && env.webAuthnCredentialStore()
            && env.webAuthnChallengeRoundTrip()
            && env.recoveryReady();
        return ready ? "READY" : "BLOCK";
    }

    static void show(String name, Environment env) {
        System.out.println(
            name + ": OTT=" + ott(env)
                + ", WebAuthn=" + webAuthn(env)
        );
    }

    public static void main(String[] args) {
        Environment localDemo = new Environment(
            true, true, false, false, false, false, false, false
        );

        Environment production = new Environment(
            true, true, true, true, true, true, true, true
        );

        Environment missingChallengeState = new Environment(
            true, true, true, true, true, true, false, true
        );

        show("local", localDemo);
        show("production", production);
        show("no-session-roundtrip", missingChallengeState);
    }
}
```

Chạy:

```bash
javac AuthFeatureReadinessDemo.java
java AuthFeatureReadinessDemo
```

**stdout chính xác dự kiến:**

```text
local: OTT=BLOCK, WebAuthn=BLOCK
production: OTT=READY, WebAuthn=READY
no-session-roundtrip: OTT=READY, WebAuthn=BLOCK
```

`production=READY` chỉ có nghĩa **các boolean giả định đã được người kiểm thử đánh dấu true**, không phải chứng chỉ bảo mật. Trong ứng dụng thật, mỗi boolean cần bằng chứng: Gradle dependency report, patch report, deployment config, DB migration test, SMTP integration test, WebAuthn browser ceremony và multi-node/serialization test.

### Tại sao có `recoveryReady` trong gate?

Nếu user mất device hoặc mất quyền truy cập email, sản phẩm cần một con đường lấy lại tài khoản được phê duyệt. **Không thiết kế recovery từ đầu** dễ dẫn đến quy trình help desk tắt MFA hoặc đăng ký passkey mới chỉ bằng email/password yếu, tạo đường vòng so với phương thức đăng nhập chính.

## 22. JUnit 5: test thực `JdbcOneTimeTokenService` với H2

Ví dụ này có giá trị khi kiểm tra **JDBC schema đúng và consume dùng một lần**. Nó không cần gửi email, không chạy HTTP server. Phạm vi là component test, không phải kiểm tra toàn bộ OTT login.

Cần các dependencies Spring Security 6.5, `spring-jdbc`, H2 và JUnit 5 từ test starter. Tạo file `src/test/java/example/auth/JdbcOttStoreTest.java`:

```java
package example.auth;

import java.time.Duration;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class JdbcOttStoreTest {

    private EmbeddedDatabase database;
    private JdbcOneTimeTokenService service;

    @BeforeEach
    void setUp() {
        database = new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript(
                "classpath:org/springframework/security/core/ott/jdbc/"
                    + "one-time-tokens-schema.sql"
            )
            .build();

        service = new JdbcOneTimeTokenService(
            new JdbcTemplate(database)
        );
    }

    @AfterEach
    void tearDown() throws Exception {
        if (service != null) {
            service.destroy();
        }
        if (database != null) {
            database.shutdown();
        }
    }

    @Test
    void tokenCanBeConsumedOnlyOnce() {
        OneTimeToken token = service.generate(
            new GenerateOneTimeTokenRequest(
                "alice", Duration.ofMinutes(5)
            )
        );

        OneTimeToken first = service.consume(
            new OneTimeTokenAuthenticationToken(
                token.getTokenValue()
            )
        );

        OneTimeToken second = service.consume(
            new OneTimeTokenAuthenticationToken(
                token.getTokenValue()
            )
        );

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }
}
```

Chạy:

```bash
./gradlew test --tests example.auth.JdbcOttStoreTest
```

**Kỳ vọng** theo contract `OneTimeTokenService`: consume lần đầu trả token hợp lệ, lần sau trả `null`. Nếu DDL resource/dialect không tương thích với H2 version trong project, kiểm tra chính xác SQL script và dependency tree; không “fix” bằng cách bỏ table hoặc dùng in-memory rồi tuyên bố JDBC đã được test.

Để có mức tin cậy production, lặp lại test bằng **Testcontainers với PostgreSQL/MySQL thực**, chạy schema migrations thật, test token sinh trên repository instance A được consume ở B và hai concurrent consumers cùng token. Test này **không** xác minh SMTP, CSRF, account status hoặc session login.

## 23. WebAuthn integration test phải có browser/authenticator

Một unit test mock `Authentication` hoặc mock `UserCredentialRepository` có thể hữu ích, nhưng không chứng minh passkey có thể đăng nhập thật. Tối thiểu, staging cần:

1. Chạy HTTPS tại **hostname/RP ID giống production** hoặc một origin staging được phép.
2. Đăng nhập bằng phương thức enrollment đã được phê duyệt.
3. Lấy registration options có challenge, CSRF và session đúng.
4. `navigator.credentials.create(...)` với browser/authenticator test được kiểm soát.
5. Gửi kết quả về `POST /webauthn/register`.
6. Đọc lại credential record từ JDBC và user entity tương ứng.
7. Restart app, bảo đảm record vẫn còn.
8. Từ node khác, nhận authentication options rồi `navigator.credentials.get(...)`.
9. Gửi `POST /login/webauthn`, assert principal/authorities đúng user và đúng flags.
10. Thử sai origin/RP ID/challenge/signature, user verification không đủ và credential đã bị thu hồi; phải từ chối.
11. Thử hai users, nhiều browser sessions, user handle, backup/synced passkeys.
12. Thử distributed session serialization/deserialize khi policy userVerification `REQUIRED`, với patch đã được chứng minh sửa advisory.

**Không tạo giả một chữ ký WebAuthn bằng cách tự đặt `authenticated=true` trong test fixture rồi coi là integration test.** Kết quả authentication phải đến từ verifier hợp lệ, với challenge được phát và liên kết đúng.

### Kiểm tra sau restore dữ liệu

Mỗi credential đã đăng ký chứa quan hệ với account ổn định. Sau restore hoặc migrate:
- User handle/credential IDs phải giữ nguyên.
- Public key và metadata cần thiết vẫn còn.
- Không đảo account của Alice/Bob.
- `signCount` và các thuộc tính backup state được xử lý theo WebAuthn rules của thư viện.
- Credential bị revoke trước backup không được “hồi sinh” trái chính sách sau restore.
- Chỉ account owner có quyền xóa/rename credential của mình.

## 24. Ma trận QA trước release

| Mục kiểm tra | OTT | WebAuthn |
| --- | --- | --- |
| Dependency đúng version/BOM | Core/web Security 6.4+ | 6.5 WebAuthn4J hoặc 7.x module riêng |
| Application khởi động | `oneTimeTokenLogin()` nhận service đúng | `webAuthn()` nhận verifier/deps đúng |
| Persistence production | JDBC/custom shared token store | JDBC/custom **user + credential repositories** |
| Data schema migration | OTT schema | User entity + user credential schemas |
| Restart node | Token hợp lệ theo TTL vẫn consume được | Credential đã enroll vẫn tồn tại |
| Giao nhiều node | Generate A, consume B | Options/challenge A, ceremony B |
| Session/challenge | Session/CSRF theo login policy | Registration/auth options round-trip và CSRF |
| Network | Email/SMS/magic-link public URL tin cậy | TLS, RP ID, allowed origins đúng |
| Security events | Generate/consume/fail/rate limit | Register/assert/delete/fail/recovery |
| Replay | Token không consume được lần hai | Challenge/signature/counter theo verifier |
| Account status | Disabled/locked không bypass | Disabled/locked không bypass |
| Authorization | Không coi OTT tự là MFA | Không coi WebAuthn tự thỏa mọi policy |
| Recovery | Mất mailbox/SMS có quy trình an toàn | Mất authenticator có quy trình an toàn |
| Bản vá | Scan các Security/OTT advisories | **CVE-2026-47841** và advisories hiện hành |
| Rollback | Token còn hạn xử lý ra sao | Credential cũ còn dùng được không |
| Audit | Không log raw token | Không log private key/assertions nhạy cảm |

**Definition of Done thực tế:** các test staging phải có kết quả **pass/fail được lưu** theo đúng version/deployment target. Một test trên H2 và localhost không thay được test trên RDBMS thật, reverse proxy thật hoặc shared session store.

## 25. Rủi ro khi có nhiều `SecurityFilterChain`

Spring Security Servlet có thể có:
- Chain API `/api/**` dùng Bearer tokens.
- Chain browser `/**` dùng form, OTT, WebAuthn.
- Chain admin `/admin/**` có MFA policy riêng.

Nếu cấu hình OTT/WebAuthn trong một chain **không match route login**, tính năng có thể không hoạt động. Nguy hiểm hơn: một chain yếu hơn có thể cho vào tài nguyên đáng lẽ cần factor.

Checklist:
1. Kiểm tra `@Order` và `securityMatcher(...)` của các chains.
2. `POST /ott/generate`, `POST /login/ott`, các WebAuthn options/register/login endpoints có đi qua chain mong muốn không?
3. CSRF có đúng cho các POST? Không blanket `.csrf().disable()` chỉ để demo dễ chạy.
4. Với browser login, SessionCreationPolicy có phải stateless khiến challenge/SecurityContext không được khôi phục không?
5. Role/permission được mapping đúng sau OTT/WebAuthn authentication không?
6. Protected routes cần MFA có áp policy cho **cả** form, bearer, remember-me, recovery hoặc login API cũ không?
7. CORS/proxy chính sách có cho browser gửi cookie, CSRF và yêu cầu liên quan đúng không?
8. Có endpoint login mới trả `200` nhưng không lưu Authentication/session không?
9. Test cả method GET/POST và reverse-proxy prefix/context path.
10. Không tạo hai bean `SecurityFilterChain` cùng matcher chung mà không hiểu thứ tự ưu tiên.

**Trong WebFlux**, tên cấu hình là `ServerHttpSecurity` và `SecurityWebFilterChain`; không dùng `HttpSecurity`/Servlet filters rồi suy là tương đương. WebFlux OTT sử dụng các handler giao token có chữ `Server...`; đọc reference reactive theo phiên bản. Đối với WebAuthn, xác nhận tính năng tương ứng có thật trong **nhánh reactive** đang chạy trước khi thêm dependency Servlet.

## 26. Dấu hiệu lỗi và cách chẩn đoán

| Triệu chứng | Nghi ngờ đầu tiên | Cách kiểm tra |
| --- | --- | --- |
| IDE không tìm `webAuthn()` | Spring Security cũ hoặc import nhầm | `dependencyInsight`, `HttpSecurity` servlet đúng |
| Runtime `NoClassDefFoundError` WebAuthn4J | Thiếu/chồng chéo WebAuthn dependency | Runtime graph, BOM, artifact image |
| Spring 7 không thấy module WebAuthn | Chưa có `spring-security-webauthn` | Thêm đúng module của 7.x |
| 6.5 không thấy JDBC WebAuthn repository | Chạy patch cũ, nhầm package | Đối chiếu 6.5 Javadoc, dependency |
| `BadSqlGrammarException` khi OTT generate | Chưa chạy OTT schema/mismatch dialect | Migrations và classpath SQL resource |
| Đăng ký passkey thành công nhưng restart mất hết | Map/in-memory credentials repository | JDBC/custom persistent repositories |
| Token gửi mail nhưng nhập ở node khác bị invalid | In-memory token store trên node A | Shared JDBC/custom store, test A→B |
| `POST /webauthn/register` báo mất challenge | Session/options bị mất hoặc cookie sai | Session repo, sticky/shared, CSRF, challenge |
| Authenticator báo RP/origin mismatch | Proxy/TLS/domain sai | Browser origin và server rpId/allowedOrigins |
| Sau load balancer có lỗi `NotSerializableException` | Session store serializer không hợp WebAuthn objects | Patch release, Spring Session round-trip test |
| UV được cấu hình REQUIRED nhưng không enforced | Có thể thuộc advisory 2026 với session serialization | Kiểm tra CVE-2026-47841 + bản vá và test |
| `/ott/generate` trả token thô trong response | Demo/debug handler bị đưa lên production | Dùng delivery handler an toàn, không log token |
| Token hết hạn vẫn có trong DB | Cleanup chưa chạy hoặc chưa có policy | `cleanupExpiredTokens`, cron, clock/test expiry |
| Account disabled vẫn login OTT | Provider/status policy riêng không kiểm tra | Test từng provider và userDetailsChecker phù hợp |
| `403` sau login passkey dù credential đúng | Auth thành công nhưng role/factor policy chưa đạt | Log an toàn class/authorities, policy, session |
| Thêm passkey ở browser A, B không thấy | Cache/repo/local state hoặc session mismatch | JDBC, user handle, multi-node |
| “MFA đã bật” nhưng Basic/legacy vẫn vào admin | Policy chỉ ở UI / chain khác | Kiểm thử mọi authentication path |
| SQL migration thành công nhưng user entities trùng | Thiếu uniqueness/mapping tenant | Schema constraints, test concurrent registration |
| Cập nhật Spring Security xong login page lỗi | DSL endpoint/deprecation thay đổi | Đọc migration guide/Javadoc đúng phiên bản |
| Admin UI trả “có passkey” nhưng đăng nhập không được | Metadata UI cache stale, credential repo khác | Đối chiếu credential IDs/user entity thật |

**Phân nhóm lỗi trước khi sửa:** build-time API, dependency runtime, persistence schema, challenge/session, origin/HTTPS, verification/authorization, bản vá bảo mật. Không thử vô hiệu hóa CSRF, hạ UV policy hoặc tắt session serialization như một “fix” không được review.

## 27. Rollout và rollback an toàn

### Trước rollout

- Chốt một **version BOM và patch** cho cả cluster.
- Quét CVE, xác minh các điều kiện ảnh hưởng và bản vá được cấp phép/sẵn có.
- Chạy DB migrations **tương thích ngược** trước khi deploy binary.
- Nếu WebAuthn credential schema khác phiên bản cũ, chuẩn bị dữ liệu/backup.
- Bật tính năng qua feature flag nội bộ trước, rồi nhóm pilot.
- Test email delivery/SMTP, public URL, TTL, load balancing.
- Test authenticator enrollment, browser support, session persistence và challenge.
- Có dashboard: generate success, delivery errors, consume success/replay, register/assert success/fail, DB errors, node switch.
- Có runbook mất thiết bị/mất mailbox, hỗ trợ account recovery không làm giảm assurance.

### Khi rollout theo nhiều nodes

- **Không trộn patch không tương thích** trên những node phải đọc chung token/credential schema hoặc serialized session.
- Version skew có thể khiến một node ghi objects mà node khác không deserialize được.
- Rolling deployment phải kiểm tra thật khả năng đọc/ghi hai phiên bản theo hướng dẫn migration.
- Giữ client/browser flows hoạt động khi load balancer đưa hai bước vào hai nodes.
- Không ghi raw token/signature để “debug dễ”.
- Khi thử failover, thu thập correlation IDs, node/version và trạng thái DB/session **không chứa secrets**.

### Nếu phải rollback

1. Feature flag ngăn **enrollment mới** trước khi thay schema/phiên bản.
2. Không xóa WebAuthn credentials đã đăng ký chỉ vì ứng dụng mới lỗi.
3. Kiểm tra binary cũ còn đọc được DB records/serialized sessions mới không.
4. Với OTT, xác định token đã gửi mà chưa consume sẽ được xử lý thế nào.
5. Giữ recovery path cho người dùng, không để họ bị lock out.
6. Có thể buộc re-login/clear session theo policy nếu format thay đổi, nhưng phải thông báo và kiểm soát tác động.
7. Nếu rollback tạo ra phiên bản **có CVE đã biết**, không nên dùng nó như phương án an toàn để duy trì WebAuthn public.
8. Sau sự cố, tạo regression test cho trường hợp thực đã khiến rollout thất bại.

## 28. Checklist kiểm duyệt trước khi bật feature flag

### Dependencies và phiên bản

- [ ] Đã lưu output `java -version`, `./gradlew dependencies`, `dependencyInsight` cho các Spring Security modules.
- [ ] Spring Boot/Security/Framework/Java tương thích; không pha trộn major versions.
- [ ] Spring Security đủ version có OTT/WebAuthn (`6.4+` trong Servlet).
- [ ] WebAuthn dependency đúng nhánh: 6.5 WebAuthn4J; 7.x module `spring-security-webauthn`.
- [ ] Build/runtime classpath không có hai version/library không tương thích.
- [ ] Có SBOM/security advisory review, đặc biệt CVE-2026-47841 nếu chạy WebAuthn distributed sessions.
- [ ] Các phiên bản deploy trên nhiều nodes không phá serialization/schema.

### OTT

- [ ] Có `OneTimeTokenGenerationSuccessHandler` giao token an toàn đến kênh đã xác minh.
- [ ] Dùng JDBC/custom shared `OneTimeTokenService` nếu production đa node/restart.
- [ ] DDL resource OTT đã được chuyển thành migration và áp dụng đúng database.
- [ ] Token có entropy, TTL, single-use và chống concurrent replay theo test.
- [ ] Link dùng hostname HTTPS đáng tin; không lộ token trong logs, analytics hoặc redirect ngoại domain.
- [ ] Có rate limit, chống account enumeration, audit và xử lý delivery failure.
- [ ] Account state và MFA/authorization policy áp dụng cho OTT login.
- [ ] Test generate A → consume B, expiry, retry và cleanup.

### WebAuthn

- [ ] Có hai repository user entity/credential bền vững; không dựa map memory trên production.
- [ ] Hai DDL resource WebAuthn đã được migrate phù hợp dialect.
- [ ] Stable user handle/credential ID gắn account đúng, revoke và backup/restore hoạt động.
- [ ] RP ID và allowed origins trùng domain thực; HTTPS, reverse-proxy config đã được kiểm tra.
- [ ] Registration/authentication options/challenge tồn tại và được ràng buộc đúng session/ceremony.
- [ ] Khi dùng distributed session, có integration test serialization/UV với patch an toàn.
- [ ] CSRF, account ownership, role/MFA policy bảo vệ enroll/delete passkey.
- [ ] Test authenticator/browser thật, negative signature/origin/challenge/UV cases.
- [ ] Recovery và quy trình thay authenticator đã được review.
- [ ] Restart, multi-node, rollback không làm mất credentials.

### Vận hành

- [ ] Có readiness criteria định lượng, người chịu trách nhiệm và kết quả test staging.
- [ ] Monitoring có error rates, latency, token volume, registration/auth success, node identifiers.
- [ ] Không log password, magic token, private key, cookie/session/JWT raw.
- [ ] Rollout canary, feature flag và rollback path đã thử.
- [ ] Security review bao gồm API/legacy/remember-me/SSO, không chỉ trang login.
- [ ] Có alert nếu DB/cache/session unavailable hoặc phát hiện credential replay/abuse.
- [ ] Mọi thay đổi version đi qua regression suite trước khi production.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Một dự án Spring Boot 3/Security 6.5 thêm `spring-security-webauthn` từ tài liệu 7.x và gặp lỗi dependency. Nên làm gì?

**Trả lời:** Xác định nhánh dependency chính xác. Guide 6.5 dùng `spring-security-web` + `webauthn4j-core` tương thích; 7.x dùng module `spring-security-webauthn`. Không pha major Security modules.

**Câu 2.** OTT chạy local một node nhưng khi scale 2 replicas nhiều user nhận token “invalid”. Vì sao?

**Trả lời:** Có thể `InMemoryOneTimeTokenService` mỗi JVM giữ token riêng. Dùng shared JDBC/custom store và test generate A → consume B, đồng thời kiểm tra session/URL/TTL.

**Câu 3.** WebAuthn credential đã lưu bằng JDBC nhưng bước `POST /webauthn/register` mất challenge khi qua node B. Đã đủ persistence chưa?

**Trả lời:** Chưa. JDBC credential repository bảo vệ bản ghi dài hạn; challenge/options lại phụ thuộc session/repository riêng. Kiểm tra session cookie, shared session/serializer, CSRF và ceremony lifecycle.

**Câu 4.** Có thể copy `users.ddl` của `JdbcUserDetailsManager` để tạo đủ OTT và WebAuthn tables không?

**Trả lời:** Không. OTT và WebAuthn có DDL resources riêng, được liệt kê trong bài. Phải migration đúng schema của từng repository, trên dialect đang dùng.

**Câu 5.** Bật `oneTimeTokenLogin()` và `webAuthn()` có tự tạo chính sách “password + một yếu tố thứ hai” không?

**Trả lời:** Không. Đó là các cơ chế authentication. MFA enforcement cần chính sách factor/assurance trên tài nguyên, đặc biệt trong Spring Security 7.x.

**Câu 6.** Nên dùng `userVerification=preferred` để “né” lỗi UV ở distributed session của 6.5.11 không?

**Trả lời:** Không. Nếu policy yêu cầu `REQUIRED`, hạ xuống preferred làm yếu security. Kiểm tra advisory CVE-2026-47841 và nâng cấp bản được sửa/hỗ trợ.

**Câu 7.** Vì sao passkey không đăng nhập được sau khi đổi domain sản phẩm?

**Trả lời:** Credential WebAuthn gắn với RP ID/origin rules. Đổi hostname/RP ID có thể làm credential cũ không được chấp nhận. Cần migration/domain strategy và re-enrollment phù hợp.

**Câu 8.** Một JDBC token test consume tuần tự hai lần thành công/thất bại đúng như yêu cầu. Đã chứng minh single-use tuyệt đối trên cluster chưa?

**Trả lời:** Chưa. Phải test hai consumer **đồng thời** trên DB thực và các node thực, kiểm tra transaction/atomicity.

**Câu 9.** Tại sao một instance vẫn thấy `NotSerializableException` dù credential records lưu ở PostgreSQL?

**Trả lời:** Credential record persistence và session/challenge serialization là hai lớp khác. Kiểm tra Spring Session/Jackson serializer, SecurityContext/Auth objects và version compatibility.

**Câu 10.** Đăng ký passkey thành công có nghĩa request đổi MFA factor không cần step-up?

**Trả lời:** Không. Enrollment tạo một cách đăng nhập mới có thể tồn tại lâu dài; phải kiểm soát account owner, CSRF, reauthentication/freshness và notification.

## 30. Tổng kết

Bật OTT hoặc WebAuthn an toàn là một công việc **kiểm tra phiên bản + dependency + persistence + chính sách security + tích hợp vận hành**, không chỉ một method trong DSL.

- **Version:** 6.4 giới thiệu OTT/WebAuthn Servlet; 6.5 bổ sung JDBC persistence cho WebAuthn; 7.x có module `spring-security-webauthn` và cơ chế MFA mở rộng. Phải chọn patch đã sửa advisory liên quan.
- **Dependency:** dùng BOM nhất quán; guide 6.5 yêu cầu WebAuthn4J, guide 7.x yêu cầu module WebAuthn riêng.
- **OTT store:** tránh in-memory trong cluster; triển khai `JdbcOneTimeTokenService`, chuẩn bị schema riêng, delivery handler an toàn, TTL và single-use.
- **WebAuthn store:** có cả user entity và credential repositories bền vững, cùng challenge/options/session persistence phù hợp.
- **Browser security:** HTTPS, RP ID, origin, CSRF và policy UV phải khớp.
- **Assurance:** bật một login mechanism không tự áp MFA cho các API/đường đăng nhập khác.
- **QA:** thử restart, multi-node, session serialization, account disabled, credential revoke và token replay.
- **Release:** không phát hành nếu dependency mismatch, chưa có migrations, thiếu recovery hay đang nằm trong phiên bản bị ảnh hưởng bởi advisory phù hợp threat model.

Định nghĩa “sẵn sàng” nên có bằng chứng kiểm thử thực tế trên **đúng binary và deployment topology** sắp dùng. Bài Java 17 và JUnit JDBC minh họa cách biến giả định thành phép kiểm tra, nhưng không thay thế verification ở browser/authenticator và production-like environment.

## 31. Tài liệu tham khảo chính thức

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 6.5 — Passkeys / WebAuthn dependencies and JDBC repositories: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 6.5 — What's New (JDBC persistence WebAuthn): https://docs.spring.io/spring-security/reference/6.5/whats-new.html
- Spring Security 7.0 — Passkeys (dedicated `spring-security-webauthn`): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security 7.x — One-Time Token Login and MFA: https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- Spring Security 7.x — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Javadoc Spring Security 6.5 — `JdbcOneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html
- Javadoc Spring Security 6.5 — `JdbcUserCredentialRepository`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/webauthn/management/JdbcUserCredentialRepository.html
- Javadoc Spring Security 6.5 — `JdbcPublicKeyCredentialUserEntityRepository`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/webauthn/management/JdbcPublicKeyCredentialUserEntityRepository.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security security advisory **CVE-2026-47841** (20/08/2026): https://spring.io/security/cve-2026-47841/
- Broadcom knowledge article — Passkeys and Spring Session serialization: https://knowledge.broadcom.com/external/article/432996/using-passkey-with-spring-security-autho.html
- W3C Web Authentication specification: https://www.w3.org/TR/webauthn-3/
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
