# Bảo vệ credentials, khóa ký, client secret và cấu hình theo môi trường

> **Bối cảnh:** Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet stack. Đây là hướng dẫn vận hành: secret là gì, bảo vệ password và credential, quản lý khóa ký JWT và OAuth2/OIDC client secret, cấu hình ứng dụng theo môi trường, rotation, kiểm thử và ứng phó khi secret lộ. Các credential trong ví dụ chỉ là dữ liệu local/test giả lập, không dùng được cho production.

## 1. Mục tiêu và ranh giới bảo mật

Một ứng dụng có `SecurityFilterChain` đúng vẫn có thể bị xâm nhập nếu client secret bị commit, private key nằm trong image, password production bị log hoặc staging sử dụng chung signing key với production. Bảo mật xác thực cần cả **code đúng** và **vòng đời bí mật được kiểm soát**.

```text
Người dùng / ứng dụng khách
           |
       HTTPS/TLS
           |
     Spring Security Servlet
       +-- Form/Basic login: kiểm chứng password hash
       +-- OAuth2 Login: confidential client dùng client secret
       +-- JWT resource server: dùng public key của trusted issuer
       +-- Authorization: áp dụng roles/scopes/claims sau xác thực
           |
           v
     Dữ liệu nghiệp vụ

Tầng vận hành:
  Vault/Secret Manager + IAM workload
  KMS/HSM/PKI + lifecycle keys
  Config riêng cho dev/test/staging/prod
  CI/CD + secret scanning + logging policy + audit
```

Phân biệt ba câu hỏi: **bí mật nào cần giữ kín?**; **bên nào thực sự được phép dùng nó?**; **khi nào và bằng cách nào có thể thu hồi/thay nó?** Đừng đánh đồng một giá trị có chữ “key” với private key có quyền ký hoặc với public verification key.

| Đối tượng | Vai trò | Cần giữ bí mật? | Ai nên nắm giữ? |
|---|---|---|---|
| Password người dùng | Bằng chứng đăng nhập | Có | Người dùng; backend chỉ lưu salted adaptive hash, không lưu raw |
| Password service / API key | Credential máy, DB, LDAP bind, đối tác | Có | Workload được cấp quyền tối thiểu qua secret store |
| OAuth2 `client_id` | Nhận diện client | Thường không | Client registration và cấu hình ứng dụng |
| OAuth2 `client_secret` | Xác thực **confidential client** | Có | Server backend, không gửi browser |
| JWT private signing key | Ký token của issuer | **Rất nhạy cảm** | Authorization Server/IdP hoặc KMS/HSM có quyền ký |
| JWT public verification key | Xác minh token ký bất đối xứng | Không cần giấu | Resource server lấy từ trusted JWKS/issuer |
| HMAC signing secret | Vừa ký vừa xác minh HMAC JWT | Có | Chỉ các bên được tin như một issuer |
| TLS private key | Chứng minh danh tính TLS endpoint | Có | TLS terminator/keystore/PKI vận hành |
| OIDC issuer/JWKS URL | Định nghĩa nguồn tin cậy | Không nhất thiết bí mật | Cấu hình đã được duyệt, không lấy tùy tiện từ token |

**JWT có chữ ký không phải JWT được mã hóa.** Payload JWT thông thường có thể decode và đọc được; không chứa password, access key, secret hoặc PII không cần thiết trong claims. Xác minh chữ ký cũng chưa đủ nếu bỏ kiểm tra issuer, audience, thời hạn và quyền.

## 2. Mô hình đe dọa: bí mật có thể lộ ở những đâu?

| Bề mặt | Lỗi phổ biến | Kiểm soát cần có |
|---|---|---|
| Git và pull request | Commit file `.env` hoặc `application-prod.yml` chứa mật khẩu, private key | Không lưu raw secret, secret scanning, thu hồi khi phát hiện |
| CI/CD | `echo $TOKEN`, debug shell tracing hoặc artifact có config đã resolve | Secret scoping và masking, không in credentials |
| Docker image | `COPY private-key.pem` hoặc `ENV PASSWORD=...` | Runtime injection/secret mount, không bake vào layers |
| Kubernetes | Secret chỉ được Base64 encoding; service account đọc rộng | RBAC, mã hóa at rest theo cấu hình, audit, quyền mount chặt |
| Runtime memory | Heap dump, thread dump, actuator `env`/`configprops` | Giới hạn diagnostics, retention, quyền đọc dump |
| Access log | Header `Authorization`, `Cookie`, body login, query chứa token | Redaction tại proxy/app/tracing/client |
| Developer laptop | Shell history, command args, file config backup | Local secret manager, không dùng production credential |
| Staging/test | Copy DB, IdP registration hoặc signing key production | Secret, issuer, key, dữ liệu và tài khoản tách riêng |
| Network | HTTP Basic không TLS, LDAP simple bind plaintext | TLS được kiểm tra và vùng tin cậy được giới hạn |
| SPA/mobile | Client secret nằm trong JavaScript hay binary | Public OAuth client + Authorization Code/PKCE, không embedded secret |

Lưu ý một secret có thể tồn tại cùng lúc trong Git history, CI caches, image layers, logs và bản sao máy developer. **Xóa secret khỏi file hiện tại không thu hồi nó.** Nếu đã lộ, phải revoke/rotate tại nguồn cấp và kiểm tra các bản sao.

## 3. Vòng đời secret và trách nhiệm của người vận hành

```text
Tạo bằng nguồn mật mã an toàn
         |
Gán owner + purpose + environment + hạn sử dụng
         |
Lưu trong vault/KMS/HSM hoặc cơ chế có kiểm soát
         |
Cấp cho workload theo identity và least privilege
         |
Sử dụng trong memory, không log/echo
         |
Audit và phát hiện sai lệch
         |
Rotation với rollback/overlap khi được phép
         |
Thu hồi key cũ và kiểm tra client còn sử dụng
         |
Kết thúc vòng đời, xóa bản sao và cập nhật inventory
```

Một inventory tối thiểu cần có secret name/reference, loại, scope, environment, owner, nơi cấp, ứng dụng sử dụng, cơ chế access, thời hạn/rotation, quy trình revoke và người liên hệ sự cố. **Không lưu giá trị secret trong inventory.**

Các nguyên tắc:

1. **Least privilege.** Tài khoản DB của ứng dụng không có quyền DBA; account tra LDAP không được đổi mật khẩu người khác; CI job chỉ có secret đúng environment.
2. **Không chia sẻ giữa ranh giới tin cậy.** Staging không dùng cùng production signing private key, OAuth client secret hoặc DB password.
3. **Fail closed.** Thiếu secret hoặc vault không truy cập được phải gây startup/connect/authentication failure an toàn, không fallback sang `demo123` hoặc `admin/admin`.
4. **Ưu tiên short-lived identity.** Dùng workload identity/OIDC federation hoặc managed identity cho KMS/DB khi hệ thống hỗ trợ; giảm static long-lived keys.
5. **Rotation được diễn tập.** Có secret mới nhưng không có quy trình reload/cache/restart và revoke secret cũ chưa phải hoàn tất.
6. **Tách trách nhiệm.** Code cấu hình cơ chế, platform cấp secret, owner phê duyệt scope, vận hành quản lý audit/incident.
7. **Không coi env var là vault.** Env vars tiện nhưng có thể lộ qua process/container inspection, crash dump, debug tools.

## 4. Bảo vệ password người dùng

### 4.1. Hash chậm có salt, không lưu dạng phục hồi

Password đăng nhập thường chỉ cần **verify**, không cần giải mã. Dùng thuật toán password hashing có salt và cost như Argon2id, scrypt, bcrypt hoặc PBKDF2 theo chính sách/tài nguyên cụ thể; chọn cost có đo hiệu năng, kiểm tra độ dài input và quy trình migrate.

Không dùng `SHA-256(password)` trần, MD5, Base64 hoặc AES reversible như cách lưu password mặc định. Salt giảm khả năng dùng bảng hash precomputed; thuật toán password hashing tăng chi phí brute force offline.

Spring Security cung cấp `PasswordEncoder` và `DelegatingPasswordEncoder`. Ví dụ bean thích hợp khi muốn lưu prefix thuật toán như `{bcrypt}` để phục vụ migration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class PasswordHashConfig {
    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

Đây là một **đoạn cấu hình Spring**, không phải chương trình standalone. Trong ứng dụng thực tế, `UserDetailsService`/data access sẽ trả **stored hash**; authentication provider dùng `encoder.matches(raw, stored)` để kiểm tra.

Ví dụ phép kiểm tra với fixture:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
String saved = encoder.encode("local-test-password-only");

boolean correct = encoder.matches("local-test-password-only", saved);
boolean incorrect = encoder.matches("wrong-password", saved);

// correct == true; incorrect == false
// Không assert hash là một chuỗi cố định vì salt thay đổi mỗi lần.
```

Bcrypt có giới hạn độ dài tính theo byte cần xem xét với chính sách password dài và Unicode; đừng tự cắt, tự hash trước hoặc thay encoding mà không có thiết kế rõ. Với password hash migration, giữ khả năng xác minh hash cũ trong giai đoạn chuyển đổi, rồi nâng hash an toàn khi người dùng xác thực hợp lệ.

### 4.2. Chăm sóc credential khi đăng nhập

- Chỉ nhận password trên HTTPS; không đưa password vào URL/query, redirect, audit hoặc exception.
- HTTP Basic dùng Base64, **không mã hóa mật khẩu**; chỉ dùng trên kết nối TLS tin cậy.
- Không log `Authorization`, `Cookie`, `Set-Cookie`, form password, authorization code, refresh/access token, session ID.
- Giới hạn thử đăng nhập, chống credential stuffing, xử lý account lockout và reset an toàn. Những thứ này không được `PasswordEncoder` tự làm thay.
- MFA và step-up phải dựa trên chính sách; user có password đúng chưa chắc được phê duyệt giao dịch.
- Không có tài khoản admin production với password generated/demo hoặc password hardcoded làm fallback.

Nếu có LDAP bind, credential người dùng đi qua kết nối LDAPS/StartTLS đúng cách và account/service bind có quyền tối thiểu. Nếu có SSO, backend thường không cần nhận password của IdP; dùng OIDC/SAML và giữ ranh giới credential tại IdP.

## 5. OAuth2/OIDC client secret: server-side only

`client_id` là định danh client; `client_secret` là credential của **confidential client** khi giao thức và IdP sử dụng phương thức client authentication này. Nó **không** phải password người dùng, access token hay signing key JWT.

| Loại ứng dụng | Có thể giữ secret? | Cách tích hợp |
|---|---|---|
| Spring MVC server-side web app | Có nếu secret nằm trên backend | OIDC Authorization Code và client authentication theo IdP |
| Backend service-to-service | Có thể, tùy workload platform | Client credentials hoặc workload identity/mTLS/private_key_jwt khi phù hợp |
| SPA JavaScript trong browser | Không | Public client Authorization Code + PKCE |
| Native/mobile client | Không thể coi embedded secret là bí mật | Public client + PKCE, redirect URI bảo vệ |

Bất kỳ secret nhúng trong JS bundle, source map hoặc mobile binary đều có thể bị trích xuất. Minification/obfuscation không thay đổi ranh giới này.

### 5.1. Cấu hình OIDC Spring Boot lấy secret từ runtime

Với `spring-boot-starter-oauth2-client`, một confidential client server-side có thể cấu hình trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Đây là cấu hình **minh họa**, yêu cầu IdP OIDC có issuer, client registration/redirect URI và secret thật. Không thể chạy đăng nhập nếu chưa có IdP. Mỗi environment dùng registration riêng; không đặt secret thật vào YAML rồi commit.

`OIDC_CLIENT_ID` và issuer URI không nhất thiết là secret nhưng vẫn phải là **giá trị quản trị đáng tin**. `OIDC_CLIENT_SECRET` chỉ được cấp cho server backend; không trả qua REST response, template hoặc static resources. Khi cấu hình cần secret, không đặt default giả trong production.

### 5.2. Không trộn các loại token

- `client_secret`: xác thực danh tính confidential client ở token endpoint khi cấu hình.
- `authorization_code`: bằng chứng ngắn hạn trong callback; không log query callback có code.
- `access_token`: bearer credential cấp quyền tới API; không log hay gửi sai đối tượng.
- `refresh_token`: giúp lấy token mới; yêu cầu lưu trữ, rotation/revocation và scope chặt.
- `id_token`: assertion danh tính OIDC, không thay access token để gọi API tùy tiện.

Lộ client secret có thể cho phép giả mạo client trong các luồng và điều kiện nhất định; mức ảnh hưởng phụ thuộc grant, scopes, redirect URI và client authentication. Rotation phải thực hiện **ở phía IdP/authorization server** lẫn trong app config, không chỉ đổi một env var.

## 6. Khóa ký JWT và phân tách issuer với verifier

### 6.1. Key pair bất đối xứng

`RS256`/`ES256` và các thuật toán ký bất đối xứng cho phép issuer giữ private signing key, resource server chỉ cần public verification key:

```text
Authorization Server / IdP:
  PRIVATE SIGNING KEY
  +-- ký JWT có kid/alg
            |
            v
       Signed JWT
            |
            v
Spring Security Resource Server:
  Trusted issuer + JWKS public keys
  +-- verify chữ ký
  +-- validate iss/exp/nbf/aud và contract token
  +-- map scope/roles -> authorities
            |
            v
       API authorization
```

**Resource server chỉ xác minh token không cần private key của IdP.** Đừng copy private signing key vào mọi microservice. Nếu ứng dụng cũng là authorization server, nó cần mô hình key ownership, cấp quyền dùng key, HSM/KMS khi phù hợp, audit và rotation.

Với HMAC (ví dụ HS256), cùng một symmetric secret vừa dùng để ký vừa để verify; mọi bên được chia sẻ secret đều có khả năng phát hành chữ ký hợp lệ. Hãy chọn theo threat model, không chỉ theo sự tiện lợi.

### 6.2. JWKS, kid, alg và claims

- `kid` dùng để chọn key trong trusted JWKS; bản thân `kid` **không phải bằng chứng tin cậy**.
- Không lấy tùy ý địa chỉ JWKS/`jku` do token do client gửi rồi tải private/public key từ Internet.
- Chỉ chấp nhận thuật toán `alg` nằm trong allowlist server; không tin alg trong header như policy động.
- `iss` phải đúng trusted issuer; `aud` phải chứa audience dành cho API; `exp`/`nbf` kiểm tra thời hạn và clock skew có giới hạn.
- Mapping scopes/claims sang `GrantedAuthority` phải có policy riêng; token signature hợp lệ không tự cấp quyền admin.
- JWT ký có thể bị đọc payload; không bỏ bí mật vào claims.

Ví dụ `application.yml` với resource server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER_URI}
```

Cấu hình này cần `spring-boot-starter-oauth2-resource-server` và issuer hợp lệ có JWKS/metadata. Spring Security có thể validate signature và các default claims, nhưng **chỉ cấu hình issuer-uri chưa tự chứng minh audience của API đã được kiểm tra theo hợp đồng**. Hãy cấu hình audience validator phù hợp version/deployment.

### 6.3. Rotation khóa ký JWT

Planned rotation điển hình:

1. Tạo key pair mới trong KMS/HSM hoặc cơ chế phát khóa mật mã an toàn, gán `kid` mới.
2. Công bố public key mới trong JWKS trong khi vẫn giữ public key cũ.
3. Bắt đầu ký JWT mới bằng private key mới; kiểm tra resource servers verify được.
4. Giữ public key cũ trong khoảng cần thiết theo token TTL, clock skew và JWKS cache; tránh ngắt token đang hợp lệ.
5. Sau khi token cũ hết hạn/không còn được chấp nhận, gỡ key cũ và thu hồi private key cũ đúng quy trình.
6. Audit signing uses, errors, key version và kế hoạch rollback.

Đây là **planned rotation**. Nếu private key cũ **nghi bị lộ**, phải ưu tiên emergency revocation/invalidating tokens theo incident policy, dù có thể gây đăng nhập lại hoặc gián đoạn ngắn; không kéo dài key lộ chỉ để giữ zero-downtime.

TLS private key và JWT signing key có mục đích khác nhau; không dùng một private key cho nhiều purpose khi không có thiết kế/đánh giá chuyên biệt.

## 7. Cấu hình theo môi trường của Spring Boot

### 7.1. Những gì được lưu trong Git

Nên giữ trong repository:

- Property names và cấu trúc `application.yml`, không chứa secret thật.
- `application-dev.yml`/`application-staging.yml`/`application-prod.yml` chỉ chứa non-secret settings, endpoints đã duyệt hoặc **references** tới runtime secret.
- Mô tả secret cần cấp, owner và quyền, không chứa giá trị.
- Test fixture sử dụng password/key giả, đánh dấu rõ local/test only.
- Test để đảm bảo thiếu secret làm deployment fail.

Không commit raw `.env`, production `.p12`/PEM private keys, client secret, DB/LDAP password, access/refresh tokens, backup key, resolved `Environment` hoặc dump chứa credential. `.gitignore` giúp phòng nhầm nhưng không xóa Git history. Nếu secret đã lên remote, **revoke/rotate** và rà soát clones/artifacts.

### 7.2. Property placeholders và fail closed

Mẫu cấu hình service tích hợp:

```yaml
app:
  outbound:
    base-url: ${PARTNER_API_BASE_URL}
    api-key: ${PARTNER_API_KEY}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Đây là **mẫu**, không phải ứng dụng Spring Boot chạy độc lập nếu không có datasource/client tương ứng. Biến được cấp từ runtime/Vault. Không thêm fallback kiểu `${DB_PASSWORD:admin}` để “giúp production không lỗi khởi động”. Thiếu secret cần dừng có kiểm soát, không tự hạ mức bảo mật.

Spring profile không phải security boundary: tên file `application-prod.yml` không bảo đảm file bí mật. Property có precedence theo Boot giữa file, profile, env vars, command-line, config import và test properties; phải kiểm tra **giá trị hiệu lực và nguồn** bằng công cụ có phân quyền/không in secret.

### 7.3. Secret Manager, env vars và configtree

Các nguồn cấp phổ biến: cloud secret manager, Vault, KMS/HSM, platform workload identity, runtime mounted files và environment variables. Env vars tiện nhưng không tự là vault; có thể lộ trong process inspection, crash dump, CI output hoặc diagnostics.

Spring Boot có `configtree` để đọc tên file trong một thư mục thành property keys:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Nếu orchestrator mount file `/run/secrets/app.security.client-secret`, ứng dụng có thể bind property `app.security.client-secret`. File mount phải có quyền đọc giới hạn; configtree **không mã hóa** nội dung. Với local, `optional:configtree:/run/secrets/` có thể phù hợp khi thư mục vắng mặt; với production cần yêu cầu secret bắt buộc và fail closed nếu không có.

Với Kubernetes, `Secret.data` được biểu diễn Base64 **không phải encryption**. RBAC, namespace boundaries, encryption-at-rest, audit và quyền mount mới quyết định mức bảo vệ. Không cho mọi service account có quyền đọc mọi secret.

**Java `String` chứa secret không thể xóa chắc chắn khỏi memory.** Không khẳng định `char[]` đủ bảo vệ nếu secret đã sao chép sang String, log hoặc các thư viện. Giảm số bản sao, hạn thời gian tồn tại, tránh dump và kiểm soát quyền.

## 8. Ví dụ Spring Boot 3.3.5 + Java 17: credential runtime, không hardcode

Ví dụ học tập này sử dụng Spring Security Servlet + HTTP Basic, một user in-memory với password được cấp qua **runtime property**, hash BCrypt trong memory và một endpoint private. Nó **không phải cách quản lý tài khoản production**; production dùng user store/IdP, credential rotation, MFA/rate limit phù hợp.

Không có password mặc định trong source; thiếu property sẽ khiến Spring không resolve được và **không startup**. Không dùng tài khoản/mật khẩu test ở môi trường thật.

### 8.1. Gradle

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các tệp:

```text
src/main/java/demo/runtime/
  RuntimeSecretsApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/demo/runtime/
  RuntimeSecretsTest.java
```

### 8.2. Spring Boot application

`src/main/java/demo/runtime/RuntimeSecretsApplication.java`:

```java
package demo.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeSecretsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeSecretsApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: BCrypt, externalized password và deny by default

`src/main/java/demo/runtime/SecurityConfig.java`:

```java
package demo.runtime;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${DEMO_USERNAME}") String username,
            @Value("${DEMO_PASSWORD}") String password) {
        if (username.isBlank() || password.length() < 12) {
            throw new IllegalStateException(
                "Required local demo identity configuration is invalid");
        }
        UserDetails user = User.withUsername(username)
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/private").hasRole("USER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Không log username/password hoặc cả đối tượng `UserDetails` trong cấu hình. Password raw từ environment chỉ dùng để tạo hash **cho local demo**; trong production, lưu hash ở database và xác thực qua provider/IdP, không nạp mọi password người dùng vào environment variables.

### 8.4. Controller không trả secret

`src/main/java/demo/runtime/DemoController.java`:

```java
package demo.runtime;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String publicResource() {
        return "public";
    }

    @GetMapping("/private")
    public Map<String, String> privateResource(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "message", "private fixture"
        );
    }
}
```

Endpoint `/private` chỉ minh họa security context. Username có thể là dữ liệu cá nhân trong ứng dụng thật; phải có authorization và mục đích sử dụng hợp lệ khi trả thông tin này.

### 8.5. Khởi chạy với dữ liệu local giả

Trong Bash:

```bash
export DEMO_USERNAME=learner
export DEMO_PASSWORD='local-fixture-password'
./gradlew bootRun
```

Trên PowerShell, dùng cú pháp biến môi trường của PowerShell. Không dùng credential production trên máy developer hoặc để vào shell history. Truy cập:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
```

Body của request đầu là `public`; request thứ hai không có credentials được HTTP Basic challenge (401). Để nhập password tương tác **không đặt password trong argument của tiến trình**:

```bash
curl --user learner http://localhost:8080/private
```

`curl` có thể yêu cầu bạn nhập password. Với credential demo chính xác, ứng dụng trả JSON có `"user":"learner"`; thứ tự field JSON không cố định. HTTP thuần chỉ dành cho `localhost` thử nghiệm; bất kỳ kết nối mạng thực nào nhận HTTP Basic credential đều cần TLS.

## 9. Kiểm thử credential qua filter thật, không chỉ mock user

`src/test/java/demo/runtime/RuntimeSecretsTest.java`:

```java
package demo.runtime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_USERNAME=learner",
    "DEMO_PASSWORD=test-only-long-password"
})
@AutoConfigureMockMvc
class RuntimeSecretsTest {
    @Autowired MockMvc mvc;
    @Autowired UserDetailsService users;
    @Autowired PasswordEncoder encoder;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialUsesAuthenticationProvider() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("learner", "test-only-long-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("learner", "invalid-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userStoreContainsHashInsteadOfRawPassword() {
        String stored = users.loadUserByUsername("learner").getPassword();
        assertFalse(stored.equals("test-only-long-password"));
        assertTrue(encoder.matches("test-only-long-password", stored));
    }
}
```

Chạy:

```bash
./gradlew test
```

`httpBasic(...)` chỉ gửi HTTP Basic header; `BasicAuthenticationFilter` của Spring Security mới thực sự gọi `AuthenticationManager`/provider. Khác với `@WithMockUser`, test này có thể phát hiện password sai. Test fixture trong code **không phải** production secret; không sử dụng secret thật để thử CI.

### 9.1. Điều test này chưa chứng minh

- Không kiểm tra TLS/reverse proxy hay HTTP headers qua network thật.
- Không kiểm tra OIDC client secret/IdP/JWKS, vì demo dùng Basic thay vì OAuth2.
- Không chứng minh toàn bộ secret manager permissions, container mounts, backup và rotation.
- Không kiểm tra MFA, account recovery, brute-force protection hoặc database persistence.
- Không đảm bảo env vars an toàn trước process inspection; đó là bài toán deployment.

Một test bổ sung trên pipeline nên cố tình khởi động app không có `DEMO_PASSWORD` để kiểm tra **fail startup**. Nếu secret được cấp qua vault/configtree, cần test secret sai/bị revoke và kế hoạch reload/restart tại môi trường staging. Khi log lỗi, chỉ in trạng thái **missing/config invalid**, không in secret.

## 10. Phân tách dev, CI, staging và production

| Yếu tố | Local/Dev | CI | Staging | Production |
|---|---|---|---|---|
| Secret source | Local manager hoặc fixture giả | Job-scoped secret hoặc fixture | Staging vault | Production vault/KMS/HSM |
| OIDC client | Dev registration | Test registration | Staging registration | Prod registration |
| JWT signing keys | Dev-only/ephemeral | Test keys | Staging key pair | Production key pair |
| Database/LDAP | Local/test only | Isolated fixtures | Staging services | Production services |
| Identity/data | User giả | User test | QA user + data scrub | Dữ liệu thật, quyền hạn thật |
| Logs/debug | Debug có redaction | Không echo secret | Production-like redaction | Minimize diagnostics, audit access |
| Access control | Developer only | Scoped CI identity | QA/Ops least privilege | Prod approvals và break-glass audit |

**Staging tuyệt đối không nên dùng production client secret/private signing key/DB password**. Một cấu hình staging trỏ nhầm `issuer-uri` production có thể làm token của môi trường không đáng tin được production chấp nhận hoặc vô tình ảnh hưởng dữ liệu thật.

Cần có deployment guard để kiểm tra: expected issuer/hostname/redirect URI, active Spring profile, DB endpoint, secret reference, role/namespace, audience, TLS trust store và khả năng rollback. Không dùng `spring.profiles.active=dev` cho production dù ứng dụng có password mạnh.

Config tree và environment variable đều chịu **thứ tự ưu tiên property sources** của Spring Boot. Khi chẩn đoán override, kiểm tra nguồn config với tooling có quyền hạn, **không dump toàn bộ effective config có secret** ra log/ticket.

## 11. Docker, Kubernetes, CI/CD và observability

### 11.1. Đừng bake secret vào Docker image

Ví dụ **không an toàn**:

```dockerfile
# Không dùng kiểu này với secret thật:
ARG CLIENT_SECRET
ENV CLIENT_SECRET=$CLIENT_SECRET
COPY production-private-key.pem /app/private-key.pem
```

Lý do: image layers, metadata, build cache/registry/artifacts có thể giữ secret kể cả khi xóa file ở một bước build sau. Cấp secret **tại runtime** qua workload identity, external vault, scoped secret volume hoặc mount phù hợp; container image chỉ chứa code và config không bí mật.

### 11.2. Kubernetes Secret và quyền đọc

Kubernetes `Secret.data` lưu representation Base64, không phải encryption. Bảo vệ còn phụ thuộc encryption-at-rest, RBAC, pod/service account permissions, network policy, audit, cách CI/GitOps quản lý manifest và quyền host/cluster.

Đừng cho mọi service account đọc mọi secret. Đừng dùng `kubectl get secret -o yaml` rồi dán output vào ticket, hay in `env` trong build log. Khi secret volume được cập nhật, ứng dụng có thể cần reload hoặc restart tùy thư viện, connection pool và cơ chế cache; phải test thay vì giả định tự đổi.

### 11.3. Log, tracing và Actuator

**Nên log**: request ID, thời điểm, route không nhạy cảm, loại cơ chế authentication, result code, issuer ID hoặc `kid` nếu phục vụ rotation, duration. **Không log**: `Authorization`, `Cookie`, `Set-Cookie`, password, full JWT, client secret, private key, ID/access/refresh token hoặc auth code.

Kiểm tra redaction ở proxy, servlet filters, exception handlers, HTTP clients, tracing/observability agents và log aggregators. Đừng dựa hoàn toàn vào masking mặc định của `/actuator/env` hoặc `/actuator/configprops`; giới hạn exposure, xác minh dữ liệu phiên bản thật và bảo vệ network/roles.

Heap dumps, thread dumps, memory diagnostics, HAR files và screenshot cũng có thể chứa secret. Quyền truy cập/retention của artifact debug phải chặt, không đưa lên chat/ticket mở.

### 11.4. CI/CD

- Scope secret theo environment/branch và các job có quyền; PR không tin cậy không được lấy production secret.
- Dùng OIDC workload federation của CI nếu nền tảng hỗ trợ, giảm static long-lived deployment credentials.
- Không bật `set -x`/echo secret, dump env hoặc chạy test với private key thật.
- Dùng secret scanning trên commit, Git history khi phù hợp và container artifacts; khi phát hiện **revoke/rotate** chứ không chỉ xóa dòng.
- Tách quyền deploy, quyền đọc secret và quyền thay signing key; production yêu cầu audit/approval theo policy.
- Không lưu file `.p12`, PEM private key, OAuth client secret hoặc token production vào test report và code coverage artifacts.

## 12. Rotation và kế hoạch thay secret không ngắt dịch vụ

### 12.1. Password/API key/DB credential

Quy trình planned rotation thường gồm:

1. Kiểm kê client/connection pool dùng credential cũ.
2. Tạo credential mới với scope không rộng hơn mức cần thiết.
3. Nếu hệ thống hỗ trợ, cho hai credential hoạt động tạm thời, có deadline revoke.
4. Cập nhật secret manager và deploy/reload service; test **new connections**.
5. Khi xác nhận mọi client chuyển sang credential mới, revoke credential cũ và quan sát attempted use.
6. Dọn cache/backup/pipeline variables không còn dùng; cập nhật inventory.

Nếu không thể có hai credential đồng thời, cần cutover có kế hoạch; không hứa zero-downtime khi upstream không hỗ trợ. Với DB pool, các connection đang mở có thể tồn tại sau khi password đã đổi, nên test reconnect/new connections.

### 12.2. OAuth client secret

Thực hiện thay secret tại IdP/authorization server, cập nhật vault, reload/redeploy app, test authorization code exchange/client authentication rồi revoke secret cũ. Một số IdP cho phép **hai secret active** trong cửa sổ overlap, một số chỉ cho thay ngay; xác nhận capability.

Đổi env var trên server mà chưa thu hồi secret cũ tại IdP **không hoàn tất rotation**. Đánh giá token/session đã phát hành và mức độ ảnh hưởng khi secret từng bị lộ.

### 12.3. Signing private key

Giữ overlap **public verification keys** trong JWKS theo token lifetime/cache khi planned rotation. Nhưng khi key bị lộ, ưu tiên emergency revoke và invalidating tokens theo threat model, kể cả cần yêu cầu đăng nhập lại. Không giữ compromised private key active vô thời hạn vì sợ gián đoạn.

## 13. Incident response: khi có nghi vấn lộ secret

Đặt tình huống: log của CI đã vô tình in OIDC client secret. Các bước tối thiểu:

1. **Xác định loại secret và phạm vi**: môi trường, hệ thống cấp, quyền được trao, người và hệ thống có thể truy cập log/artifact.
2. **Containment**: giới hạn truy cập, thu hồi/rotate credential **tại nguồn phát hành**, không chỉ xóa log.
3. **Tìm bản sao**: Git, CI cache, container layers, backup, dashboard, ticket, chat, máy developer và log retention.
4. **Đánh giá token/phiên**: client secret lộ có thể liên quan tokens; signing private key lộ có thể tạo token giả; DB credential lộ cần audit truy vấn.
5. **Triển khai phiên bản an toàn**: secret mới, workload permissions đúng, config environment đúng, validate key/issuer/audience.
6. **Giám sát và phản hồi**: anomalous login, token failures, API activity, sử dụng credential cũ, key signing events.
7. **Cải tiến**: secret scanning, giảm TTL/permissions, tránh bản sao static secret, diễn tập rotation và cập nhật runbook.

| Sự cố | Hành động ưu tiên | Điều cần xét thêm |
|---|---|---|
| Password user bị lộ | Reset password, revoke sessions nếu cần, MFA/monitoring | Credential reuse và account takeover |
| OAuth client secret lộ | Revoke và cấp mới tại IdP, cập nhật backend | Tokens đã cấp, abuse và scope |
| JWT private key lộ | Revoke/rotate key, cập nhật trust và token policy | JWT giả mạo, cached keys và token đang hiệu lực |
| TLS private key lộ | Thay key/certificate và đánh giá revocation | Copy tại proxy/CDN/backup |
| DB/API key lộ | Rotate account/key và audit access | Connection pool, permissions, logs |

Không đính kèm **giá trị secret** vào ticket incident. Dùng một secret reference không nhạy cảm, thời gian và thông tin trạng thái. Không xuất hash/fingerprint của secret chỉ để chứng minh đã rotate nếu không có nhu cầu và đánh giá rủi ro.

## 14. Các lỗi thường gặp

**Lỗi 1.** Đưa `client-secret` vào `application-prod.yml` rồi commit. Tên file không tạo security boundary; phải dùng runtime secret store và rotate nếu đã lộ.

**Lỗi 2.** Cho staging dùng signing private key của production. Một environment yếu làm lộ quyền issuer sản xuất; phải tách khóa/issuer.

**Lỗi 3.** Đặt secret trong Docker `ARG`/`ENV` hoặc copy PEM vào build image. Cache và layer có thể giữ bí mật. Chỉ inject runtime khi cần.

**Lỗi 4.** Chọn HS256 vì dễ cho mọi service verify. Với HMAC, các service giữ key cũng có thể ký; phải xét mô hình quyền phát hành token.

**Lỗi 5.** Coi JWT signature hợp lệ là đủ. Còn issuer, audience, expiry, algorithm policy, scopes và quyền tài nguyên.

**Lỗi 6.** Tin `kid`/`jku` trong JWT để tải key tùy ý. JWKS nguồn phải được chọn từ cấu hình đáng tin, không từ input của client.

**Lỗi 7.** Chỉ hash password bằng SHA-256. Password cần adaptive hash có salt, cost và migration policy.

**Lỗi 8.** Dùng secret trong SPA vì đã minify bundle. Browser vẫn có thể trích xuất; dùng public client/PKCE.

**Lỗi 9.** Đặt fallback `DB_PASSWORD:admin` trong production. Khi vault lỗi, app có thể dùng credential yếu. Fail closed.

**Lỗi 10.** Chỉ thêm `.gitignore` sau khi commit secret. Secret còn trong lịch sử/clones; revoke/rotate mới là bước quyết định.

**Lỗi 11.** Tắt Spring Security/HTTP logs redaction để debug login. Token, cookie hoặc credential có thể vào log retention. Dùng diagnostics đã scrub.

**Lỗi 12.** Đổi secret store nhưng không redeploy/reload consumer hoặc revoke phiên bản cũ. Rotation phải xác minh new path và old secret không còn dùng.

**Lỗi 13.** Cấp production secret cho CI workflow từ PR không tin cậy. Giới hạn theo branch/environment, workload identity và approvals.

**Lỗi 14.** Đánh đồng signed JWT với encrypted payload. Signature không che nội dung; không mang bí mật trong claim.

## 15. Ma trận test và checklist nghiệm thu

| Mục tiêu | Test cần chạy | PASS khi |
|---|---|---|
| Không secret trong source | Secret scanner repo/image | Không lộ production secret |
| Fail-fast | Thiếu DB/OIDC/DEMO_PASSWORD | Startup không fallback credential demo |
| User hash | `PasswordEncoder.matches` | Hash khác plaintext, đúng pass true, sai pass false |
| HTTP auth | MockMvc Basic với đúng/sai credential | Filter thật trả 200/401 phù hợp |
| Environment isolation | Staging tokens/DB/client | Không truy cập/giả danh production |
| JWT validation | Token đúng/sai signature, issuer, audience, expiry | Token ngoài trust policy bị từ chối |
| Rotation client secret | Key mới có thể auth với IdP | Client cũ bị revoke đúng thời điểm |
| Signing key | JWKS rollover/caching | Token mới verify, token cũ theo overlap policy |
| Runtime permissions | Pod/CI/job khác thử đọc secret | Bị từ chối bởi RBAC/IAM |
| Logging | Request có dummy credentials | Không lộ raw password/token/Authorization |
| Actuator/diagnostics | Kiểm tra endpoint và role access | Không lộ config có secret |
| DB credential | Rotate rồi reconnect | New connections thành công; old secret bị reject |

Checklist phát hành:

- [ ] Secret có owner, purpose, environment, scope, nguồn cấp, rotation và revoke plan.
- [ ] User password dùng adaptive salted hash; không lưu plaintext/reversible encryption.
- [ ] Client secret chỉ trên confidential backend, không trong SPA/mobile.
- [ ] JWT signing private key chỉ ở issuer/HSM/KMS, resource server dùng trusted public JWKS.
- [ ] Issuer, audience, algorithm allowlist, key rotation và claim mapping được kiểm thử.
- [ ] Môi trường dev/CI/staging/prod có secret/issuer/DB/client registration riêng.
- [ ] Không có secret trong Git, image layers, CI artifact, logs, metrics hoặc dumps.
- [ ] Secret được inject runtime theo workload identity/least privilege; TLS bảo vệ các chặng cần thiết.
- [ ] Thiếu secret gây fail closed, không có default admin password.
- [ ] Đã thử rotation/revocation, new connection và token/key overlap.
- [ ] Các endpoint Actuator/config/diagnostics được giới hạn và kiểm tra sanitization.
- [ ] Có kế hoạch incident response, không gửi secret qua chat/ticket.

**Tóm tắt:** Spring Security có thể xác thực password, OAuth2 Login và JWT resource server, nhưng việc **giữ bí mật credentials, bảo vệ private signing key/client secret, cấu hình đúng từng môi trường, cấp quyền tối thiểu, không log secrets và rotate/revoke** thuộc trách nhiệm thiết kế–vận hành toàn hệ thống. Cần chứng minh các điều đó bằng test và runbook thực tế, không chỉ bằng một property file hay một filter đã bật.