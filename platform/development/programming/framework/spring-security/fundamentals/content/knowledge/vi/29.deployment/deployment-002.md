# Loại bỏ tài khoản, mật khẩu và cấu hình minh họa trước khi triển khai Spring Security

> **Ngữ cảnh:** Spring Security trên Spring Boot 3.x / Servlet MVC, Java 17+. Thuộc nhóm **Triển khai**. Bài học tập trung vào việc biến một ứng dụng học tập hoặc proof of concept thành bản triển khai có **cơ chế danh tính thực**, **không còn tài khoản/mật khẩu/khóa mẫu**, **không còn quy tắc bảo mật chỉ dành cho demo**, có các lớp kiểm tra trong mã nguồn, cấu hình, CI/CD và môi trường chạy.

## 1. Vì sao đây là một bước triển khai riêng?

Trong bài học, những đoạn cấu hình sau thường giúp thử chức năng nhanh:

- `InMemoryUserDetailsManager` chứa user `admin`, `demo` hoặc `test` với mật khẩu cố định.
- `spring.security.user.name=admin`, `spring.security.user.password=123456` trong `application.properties`.
- `User.withDefaultPasswordEncoder()`, `NoOpPasswordEncoder` hoặc mật khẩu dạng `{noop}password`.
- `http.csrf(csrf -> csrf.disable())`, `requestMatchers("/**").permitAll()` hoặc `anyRequest().permitAll()` để “gỡ lỗi”.
- Khóa HMAC/RSA, JWT, API key, client secret, database password và đường kết nối mẫu nằm trong source.
- H2 console, actuator endpoints, Swagger UI, test controller, `/debug/**`, `/dev-login` hoặc test data được mở công khai.
- `@Profile("dev")` hoặc cờ `app.demo.enabled=true` nhưng profile/cờ đó vẫn có thể bật trong production.
- Debug/TRACE của Spring Security và các filter in `Authorization`, `Cookie`, mật khẩu hoặc token.

Những thành phần này **không chỉ là code thừa**. Chúng có thể trở thành một **đường xác thực thứ hai** mà không ai quản trị, một bí mật công khai đã bị lộ qua Git history, hoặc một endpoint được bỏ qua mọi bước phân quyền.

**Mục tiêu đúng không phải chỉ là thay `password=demo` thành chuỗi khó đoán hơn.** Phải kiểm tra cả các hướng truy cập khác, nguồn credential, quyền, key/token, dữ liệu có sẵn và cách startup khi thiếu cấu hình.

### Kết quả cần đạt trước go-live

1. Không còn tài khoản demo hoặc mật khẩu mẫu có thể đăng nhập trong artifact/môi trường production.
2. Không còn signing secret, private key, API key, refresh token, database password hoặc client secret mẫu dùng cho dịch vụ thật.
3. Không còn security bypass dành cho demo: `permitAll` rộng, filter bị bỏ qua, CSRF/CORS bị tắt sai mô hình, endpoint debug/H2 công khai.
4. Đường xác thực production được chọn **tường minh**: IdP/OIDC/OAuth2 Resource Server, LDAP hoặc cơ chế user store production được quản lý.
5. Nếu thiếu một cấu hình bắt buộc hoặc phát hiện cờ demo nguy hiểm, hệ thống **không được âm thầm mở quyền truy cập**.
6. CI/CD kiểm tra **source, cấu hình đã merge, Docker image/JAR và môi trường deploy**, không chỉ chạy test thành công.
7. Có kế hoạch **rotate/revoke** cho bất kỳ bí mật hoặc tài khoản demo nào từng được đưa vào repository, tài liệu, logs hoặc môi trường có người khác truy cập.

## 2. Kiểm kê theo bề mặt tấn công

Không chỉ tìm trong một `SecurityConfig.java`. Kiểm kê **mọi nơi có thể tạo credential hoặc thay đổi policy**:

| Vị trí | Dấu hiệu cần rà soát | Rủi ro nếu còn |
| --- | --- | --- |
| `src/main/java` | `User.withUsername("admin")`, `InMemoryUserDetailsManager`, `AuthenticationProvider` mẫu, login controller tự xây | Tài khoản bí mật tồn tại trong build |
| `src/main/resources` | `spring.security.user.*`, issuer giả, CORS `*`, `spring.h2.console.enabled=true`, profile `local` | Cấu hình dev được đóng gói và kích hoạt |
| `src/test/**` | Test fixtures, fake key, `@WithMockUser` | Thường được phép trong **test scope**; cần chắc chắn chúng không bị package hoặc copy sang main |
| `Dockerfile` / Helm / manifests | `ENV ADMIN_PASSWORD=...`, default secrets, args, init containers tạo user | Bí mật nằm trong image layer hoặc deploy manifest |
| CI/CD | Variables, pipeline echo, build args, artifact, release notes | Credential bị log hoặc nhân bản sang các môi trường |
| Database | Seed migration tạo `admin/admin`, bảng user demo, dữ liệu PII mẫu | User còn đăng nhập được dù Java code đã xóa |
| Identity provider | Test realm, OAuth2 clients, admin user, client credentials, redirect URI mẫu | Đường xác thực ngoài ứng dụng còn mở |
| Reverse proxy / gateway | Route `/debug`, bypass auth, `X-User` hoặc `X-Roles` tin client | Vượt kiểm tra Spring Security từ biên |
| Observability | DEBUG/TRACE, exception dump, HAR, request body/header logging | Password, JWT, session ID rơi vào log |
| Documentation / support | README chứa mật khẩu dùng được thật, ảnh chụp token, runbook | Bí mật bị chia sẻ lại ngoài kiểm soát |
| Object storage / backups | File cấu hình cũ, DB dump, export chứa secret | Xóa ở HEAD không có nghĩa dữ liệu đã biến mất ở nơi khác |

**Quy tắc:** đánh dấu trạng thái từng mục: **đã xóa khỏi runtime**, **chỉ có trong test**, **đã rotate/revoke nếu từng bị lộ**, **đã kiểm tra artifact và môi trường**. Chỉ xóa một dòng code mà không kiểm tra DB/IdP/image là chưa hoàn tất.

## 3. Phân biệt tài khoản mặc định, tài khoản mẫu và tài khoản production

### 3.1. Tài khoản mặc định của Spring Boot

Khi Spring Security trên classpath và ứng dụng chưa tự cung cấp cơ chế xác thực thích hợp, Spring Boot có thể tự cấu hình một user mặc định tên `user` và mật khẩu ngẫu nhiên được in ở log lúc khởi động (phù hợp cho phát triển, **không phải danh tính production**). Giá trị `spring.security.user.name`/`spring.security.user.password` cho phép thay đổi mặc định đó.

Điểm dễ nhầm:

- Thêm bean `SecurityFilterChain` có thể thay **web security mặc định** nhưng không nhất thiết tự xóa `UserDetailsService` do auto-configuration tạo.
- Một bean `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager` có thể khiến user mặc định không được tạo. Một số module như OAuth2 Resource Server/OAuth2 Client cũng ảnh hưởng điều kiện auto-configuration. Cần kiểm tra **bean và cơ chế thực tế** theo dependency/version, không chỉ đoán từ log.
- “Password generated random” không có nghĩa app đã tích hợp user store có kiểm soát danh tính, phân quyền, MFA, offboarding hay audit.
- Nếu production bất ngờ in “Using generated security password”, đó là **tín hiệu cần điều tra cấu hình authentication**; không dùng password ấy để vận hành.

Không coi `spring.security.user.password=RANDOM_SECRET_FROM_ENV` là giải pháp hoàn chỉnh cho một sản phẩm nhiều người dùng. Nó vẫn tạo một account chia sẻ không có lifecycle hoặc quản trị quyền thích hợp nếu dùng sai.

### 3.2. `InMemoryUserDetailsManager` chỉ phù hợp khi nào?

Ví dụ thường gặp:

```java
// MINH HỌA KHÔNG ĐƯỢC ĐƯA VÀO PRODUCTION:
@Bean
UserDetailsService demoUsers() {
    UserDetails user = User.withUsername("admin")
        .password("{noop}admin123")
        .roles("ADMIN")
        .build();
    return new InMemoryUserDetailsManager(user);
}
```

Đoạn trên chỉ là minh họa **cấu hình nguy hiểm để nhận diện**, không phải file được sử dụng trong ví dụ production phía sau.

Nhược điểm:

- Username/password có sẵn cho bất cứ ai đọc mã hoặc artifact.
- `{noop}` cho phép so sánh mật khẩu không băm; một người đọc source có thể biết credential ngay.
- Không có quy trình tạo/khóa/thu hồi account, MFA, reset mật khẩu, kiểm toán theo từng người.
- Có thể tồn tại song song với IdP nếu app bổ sung provider không kiểm soát; đây là **backdoor bằng chính cấu hình**.

Trong test, dùng `@WithMockUser`, `with(user(...))`, security test fixtures hoặc user store test **tách hẳn khỏi build production**. Nếu cần người dùng local để demo UI, ưu tiên môi trường/scope riêng, không đóng gói config đó vào artifact phát hành.

### 3.3. Không dùng `User.withDefaultPasswordEncoder()` hoặc `NoOpPasswordEncoder` để lưu mật khẩu thật

Các đoạn dùng encoder đơn giản giúp minh họa nhưng không đáp ứng yêu cầu quản lý password production. Với hệ thống tự quản user/password, dùng `PasswordEncoder` chuẩn và chính sách cập nhật thuật toán, ví dụ `DelegatingPasswordEncoder` với `bcrypt`/`argon2` theo cấu hình hỗ trợ, quản lý migration và kiểm soát brute-force/credential stuffing.

```java
// MINH HỌA thành phần có thể dùng trong user store tự quản:
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Import cần thiết:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
```

**Có encoder đúng không đủ.** Bạn vẫn cần user provisioning, unique username/identity, password policy, MFA nếu cần, locking/rate limiting, reset flow, audit, role lifecycle và kiểm tra data-level authorization. Nếu công ty đã có OIDC/SSO, không nên tự xây password store chỉ vì một demo Spring Security đã có form login.

## 4. Quy trình 5 lớp loại bỏ cấu hình minh họa

### Lớp 1 — Loại bỏ cơ chế không được phép

- Xóa `InMemoryUserDetailsManager` dùng trong `src/main` và mọi provider chấp nhận credentials demo.
- Xóa `/test-login`, `/generate-token`, `/debug-auth` và các controller/filters dùng để bỏ qua xác thực.
- Rà soát `@Profile`: chỉ có `@Profile("dev")` **không phải bằng chứng đủ**, vì profile có thể được bật sai trên production. Tốt nhất không đóng gói lớp demo vào artifact production.
- Loại bỏ account seed trong migration hoặc đảm bảo migration production không bao giờ chạy bước tạo tài khoản demo.
- Đối với IdP, khóa/xóa user/client credentials demo ngoài ứng dụng.

### Lớp 2 — Thay authentication bằng nguồn chính thức

Tùy hệ thống:

- **API**: OAuth2 Resource Server xác minh access token từ issuer tin cậy với `iss`/`aud`/`exp`/signature/scope.
- **Web**: `oauth2Login` qua IdP và session cookie được quản lý, hoặc user store thật với `PasswordEncoder` phù hợp.
- **Machine-to-machine**: client credentials/workload identity, scope/audience rõ ràng, secret/certificate/key rotation.
- **Hybrid**: nhiều `SecurityFilterChain` phân tách session web và Bearer API, hoặc BFF.

Không thay một tài khoản demo bằng một “admin” dùng chung toàn tổ chức. Mỗi người dùng hoặc service principal cần nhận diện, cấp quyền tối thiểu và có thể offboard.

### Lớp 3 — Đưa bí mật ra khỏi source và quản lý vòng đời

- Dùng secret manager, secret mount với quyền truy cập thích hợp, hoặc cơ chế cấu hình được tổ chức phê duyệt.
- Cấp secrets theo môi trường và danh tính workload; không dùng cùng secret giữa local, staging và production.
- Có **owner**, mục đích, phạm vi truy cập, rotation schedule, dấu vết truy xuất, expiry/revocation policy.
- Không in bí mật trong application logs, command-line arguments, shell history, stack traces, test reports, metric labels hoặc error response.
- Không cho CI/CD echo đầy đủ biến môi trường hoặc file secrets.
- Nếu bí mật từng commit lên Git, coi như **đã có khả năng lộ**; rotate/revoke, không chỉ xóa dòng và force-push.

### Lớp 4 — Xóa bypass và debug exposure

- Rà `authorizeHttpRequests` cho mọi method/route; ưu tiên **deny by default** cho endpoint chưa được khai báo.
- Rà `web.ignoring()`/`permitAll()`, thứ tự matcher và toàn bộ `SecurityFilterChain`; kiểm tra các route như `/api/admin`, `/actuator/**`, `/h2-console`, `/swagger-ui/**`, `/v3/api-docs`, `/error`, file export/attachment.
- Xem lại `csrf.disable()` theo credential model. API token-only header có thể miễn CSRF; web/BFF dùng cookie thường không.
- Không dùng CORS `*` cho credentials và không coi CORS là authorization.
- Tắt H2 console, debug actuator exposure, test controller, profiler endpoint và test dữ liệu trong môi trường triển khai.
- Đưa DEBUG/TRACE security xuống mức production phù hợp, có redaction/correlation IDs.

### Lớp 5 — Chặn lỗi bằng test và release gate

- Unit/integration tests xác minh anonymous không vào private endpoints; user thiếu quyền không vào admin.
- Có test cho token invalid/expired/wrong audience, CSRF, session logout hoặc user store phù hợp với mô hình.
- Có **static/secret scan** trên nguồn và commit history, **artifact scan** sau build, kiểm tra deploy manifest, secret references và live smoke tests.
- Deployment bị block khi phát hiện cờ demo, secret hard-coded, env bắt buộc thiếu, sample principal còn hiệu lực hoặc endpoint debug công khai.
- Có change review, record bằng chứng, rollback plan và rotation playbook.

## 5. Trước/sau: từ cấu hình học tập đến cấu hình triển khai

### 5.1. Mẫu rủi ro trước khi dọn

```java
// VÍ DỤ KHÔNG AN TOÀN — chỉ để chỉ ra lỗi cần xóa.
@Configuration
public class DemoSecurityConfig {

    @Bean
    UserDetailsService users() {
        var admin = User.withUsername("admin")
            .password("{noop}admin")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/debug/**").permitAll()
                .anyRequest().permitAll()
            );
        return http.build();
    }
}
```

Lỗi: account demo có mật khẩu rõ, không có khâu provisioning, CSRF bị tắt không dựa trên threat model, `/debug/**` công khai và `anyRequest().permitAll()` cho phép mọi URL. Chỉ đổi password không khắc phục authorization bypass.

### 5.2. Thiết kế production baseline minh họa

Bài này chọn **API chỉ nhận Bearer access token**; resource server dùng OAuth2 issuer do tổ chức quản lý. Đây là **một lựa chọn minh họa cụ thể**, không phải giải pháp cho mọi browser session. Nếu ứng dụng là web form dùng cookie, phải cấu hình web chain/session/CSRF riêng thay vì sao chép `STATELESS` hoặc `csrf.disable()`.

Mục tiêu của baseline:

- Không có `InMemoryUserDetailsManager`, user `admin` hay mật khẩu trong source chính.
- App không tự mint JWT, không dùng HMAC secret mẫu.
- JWT phải có issuer/audience từ môi trường, authority `SCOPE_items.read`/`SCOPE_items.write`.
- Các route không được liệt kê bị `denyAll()`; chỉ health check công khai nếu deployment policy cho phép.
- Có guard phát hiện một số **cờ demo cụ thể**; static scan/kiểm duyệt vẫn cần để phát hiện bypass không được guard biết.
- Test security dùng `spring-security-test` trong **test scope**, không tạo credential runtime.

## 6. Mẫu dự án Spring Boot 3.x / Java 17+

Cấu trúc:

```text
production-security-baseline/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.yml
    │   └── java/com/example/deploysecure/
    │       ├── SecureApplication.java
    │       ├── SecurityConfig.java
    │       ├── DeploymentGuard.java
    │       ├── ItemService.java
    │       └── ItemController.java
    └── test/java/com/example/deploysecure/
        ├── SecurityBoundaryTest.java
        └── DeploymentGuardTest.java
```

**Phạm vi runnable:** các tệp Java tương ứng có thể compile trong một Spring Boot Gradle project khi dependency và config được cung cấp. Startup thật cần **issuer OAuth2 hợp lệ**, audience chính thức và môi trường/network phù hợp; test có mock `JwtDecoder` để không phụ thuộc IdP bên ngoài. Đây không phải mẫu tự tạo tài khoản hay phát token để production có thể dùng ngay.

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'production-security-baseline'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Version của bài là **mốc lab cho API Boot 3.3/Security 6**, không phải phiên bản production được khuyên dùng vào mọi thời điểm. Khi triển khai thật, nâng lên bản đang được hỗ trợ và vá các CVE trong chính nhánh version đã chọn; chạy dependency/SBOM/vulnerability scan.

### 6.3. `application.yml` — chỉ giữ các tham chiếu an toàn

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}
          audiences:
            - ${API_AUDIENCE}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never

logging:
  level:
    org.springframework.security: INFO
```

**Điểm quan trọng:**

- `OIDC_ISSUER_URI` và `API_AUDIENCE` được inject từ môi trường/hệ thống cấu hình được quản trị. Không hard-code URL IdP giả vào production để “cho khởi động”.
- Không có `spring.security.user.name/password`, `app.demo.user` hoặc token/password mẫu.
- `management.endpoints.web.exposure.include` giới hạn **exposed endpoints**; bảo mật chúng còn phụ thuộc `SecurityFilterChain` và mạng triển khai. Chỉ `health` được cho phép public ở ví dụ; `info` vẫn có thể bị authorization chặn.
- Không bật `spring.h2.console.enabled`, không cấu hình debug logging hay actuator wildcard.
- Không lưu `spring.profiles.active=dev` trong artifact, không đưa tệp `application-dev.yml` có credential vào production image.
- Nếu chưa có issuer/audience, cấu hình bắt buộc sẽ không được resolve/khởi tạo phù hợp. Trong hệ thống thật, nên có bước **config validation trước traffic** và health/readiness tách biệt.

**Lưu ý phiên bản:** `spring.security.oauth2.resourceserver.jwt.audiences` là thuộc tính của Boot phục vụ kiểm tra `aud` ở những dòng Boot có hỗ trợ. Với bản khác hoặc custom `JwtDecoder`, cần đảm bảo validator audience **thật sự được gắn**, không chỉ đặt YAML và giả định. Kiểm tra bằng JWT có chữ ký hợp lệ nhưng sai audience trong integration test.

### 6.4. `SecureApplication.java`

```java
package com.example.deploysecure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureApplication.class, args);
    }
}
```

### 6.5. `SecurityConfig.java` — không tài khoản mẫu, không authentication bypass

```java
package com.example.deploysecure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items")
                    .hasAuthority("SCOPE_items.read")
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasAuthority("SCOPE_items.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Chỉ đúng với API Bearer-only, không dùng cookie tự gửi.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Giải thích các điểm dễ hiểu sai:

- `@EnableMethodSecurity` giúp `@PreAuthorize` hoạt động trên Spring-managed beans được gọi qua proxy; rule service bổ sung, không thay cho authorization ở URL.
- `requestMatchers("/actuator/health").permitAll()` là **một quyết định có chủ đích cho health probe**. Nếu chính sách tổ chức không cho health công khai, đưa sau network policy/gateway hoặc thay bằng rule tương ứng. Không dùng `/actuator/**.permitAll()`.
- `GET` cần `SCOPE_items.read`, `POST` cần `SCOPE_items.write`. Không có `hasRole("ADMIN")` mặc định hoặc `permitAll` cho mọi user.
- `anyRequest().denyAll()` fail-closed cho endpoint chưa được khai báo. Tùy yêu cầu quản lý lỗi, kiểm tra riêng `ERROR` dispatcher để tránh chặn render error; **không tự mở mọi route** chỉ vì muốn thấy lỗi đẹp.
- `STATELESS` và `csrf.disable()` trong ví dụ là **lựa chọn riêng của Bearer-header-only API**. Nếu app thêm session cookie hoặc BFF vào cùng chain, phải review lại, không sao chép mù.
- `oauth2ResourceServer().jwt()` lấy decoder do Boot cấu hình qua issuer/audience, không tự đọc secret HMAC trong source.
- Vì có OAuth2 Resource Server dependency, Spring Boot có điều kiện auto-configuration liên quan default `UserDetailsService`; **vẫn cần kiểm tra runtime bean/filter chain** và không dựa vào việc “không thấy password generated” là đủ.
- Bảo mật thực tế còn cần HTTPS, token issuance policy, JWKS key rotation, logging, rate limit, data authorization và gateway.

### 6.6. `DeploymentGuard.java` — từ chối một số cờ nguy hiểm lúc startup

Chỉ xóa account mẫu chưa đủ nếu deploy pipeline vẫn có thể cung cấp `spring.security.user.password` hoặc bật console/debug. Một guard nhỏ giúp phát hiện các config **đã biết**, không thay thế static scan hoặc pentest:

```java
package com.example.deploysecure;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public final class DeploymentGuard implements InitializingBean {

    private final Environment environment;

    public DeploymentGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void afterPropertiesSet() {
        // Không cho cấu hình single-user authentication mẫu ở mọi môi trường.
        rejectIfSet("spring.security.user.name");
        rejectIfSet("spring.security.user.password");

        // Các property app.demo.* là quy ước ví dụ của dự án,
        // KHÔNG phải thuộc tính mặc định của Spring Security.
        rejectIfTrue("app.demo.enabled");
        rejectIfTrue("app.auth.bypass.enabled");

        // Không đưa H2 console ra bất kỳ môi trường triển khai nào
        // dùng artifact production này.
        rejectIfTrue("spring.h2.console.enabled");
    }

    private void rejectIfSet(String name) {
        if (environment.containsProperty(name)) {
            throw new IllegalStateException(
                "Disallowed legacy account configuration: " + name
            );
        }
    }

    private void rejectIfTrue(String name) {
        if (Boolean.parseBoolean(
                environment.getProperty(name, "false"))) {
            throw new IllegalStateException(
                "Unsafe demo configuration is enabled: " + name
            );
        }
    }
}
```

**Tại sao guard này hữu ích?**

- Đặt policy “không cho tài khoản mẫu” ngay trong runtime, tránh phụ thuộc duy nhất vào con người nhớ xóa một property.
- Từ chối cấu hình sai thay vì âm thầm cho ứng dụng phục vụ request với bypass.
- Chỉ ghi **tên property**, không in giá trị password hoặc secret vào exception/log.
- `InitializingBean.afterPropertiesSet()` thực hiện trong quá trình khởi tạo bean; lỗi sẽ làm ApplicationContext không khởi tạo thành công theo đường thông thường.

**Giới hạn bắt buộc:** guard này chỉ biết các property đã liệt kê. Nó **không** phát hiện một controller `/debug/login` hard-coded, `permitAll()` viết tay, một account seed trong DB hay token trong Docker layer. Nó cũng không thay thế kiểm soát môi trường startup từ deployment platform. Test guard và static scans đều cần thiết.

Với hệ thống có cả môi trường local thật sự dùng config `spring.security.user.*`, **đừng tắt guard bằng profile prod** rồi coi xong; hãy dùng artifact lab/test riêng, không chứa guard/production code hoặc không triển khai artifact đó. Ứng dụng production nên luôn có baseline không phụ thuộc cờ “prod” dễ bị thiếu.

### 6.7. `ItemService.java` — quyền ở use case

```java
package com.example.deploysecure;

import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ItemService {

    @PreAuthorize("hasAuthority('SCOPE_items.read')")
    public List<ItemView> list() {
        return List.of(new ItemView("sample-1", "Non-sensitive example"));
    }

    @PreAuthorize("hasAuthority('SCOPE_items.write')")
    public ItemView create(String title) {
        return new ItemView("preview-only", title);
    }

    public record ItemView(String id, String title) {
    }
}
```

Đây là **use case giả lập không lưu DB** để kiểm tra auth. Đừng dùng ID `preview-only` hoặc response của bài học như kết quả tạo dữ liệu thật. Trong sản phẩm thật, service phải kiểm tra tenant, owner, trạng thái bản ghi, transaction và giới hạn field, rồi ghi DB thông qua repository phù hợp.

### 6.8. `ItemController.java` — DTO input thay entity

```java
package com.example.deploysecure;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping
    public List<ItemService.ItemView> list() {
        return service.list();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ItemService.ItemView create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request.title());
    }

    public record CreateItemRequest(
        @NotBlank @Size(max = 120) String title
    ) {
    }
}
```

Controller không nhận `ownerId` hoặc `tenantId` tùy ý từ client rồi coi là quyền. Đó là yêu cầu riêng về authorization object-level, không thể “giải quyết” chỉ bằng việc loại bỏ demo accounts. JSON body test hợp lệ cần `Content-Type: application/json`.

## 7. Kiểm thử baseline trước phát hành

Cần chứng minh cả **chạy được khi cấu hình đúng** và **bị chặn khi cấu hình sai**. Dưới đây là test cho code lab mục 6; dùng `spring-security-test` để kiểm tra quyền mà không yêu cầu một issuer sống trong unit/integration test.

### 7.1. `SecurityBoundaryTest.java`

```java
package com.example.deploysecure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "OIDC_ISSUER_URI=https://idp.example.invalid/issuer",
    "API_AUDIENCE=business-api"
})
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    // Boot 3.3 dùng @MockBean; ở Boot mới có API @MockitoBean.
    // Mock JwtDecoder để test không phải gọi IdP ngoài.
    @MockBean
    JwtDecoder decoder;

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadPrivateItems() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanRead() throws Exception {
        mvc.perform(get("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.read")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value("sample-1"));
    }

    @Test
    void wrongScopeCannotRead() throws Exception {
        mvc.perform(get("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.write")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanPost() throws Exception {
        mvc.perform(post("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.write")
                ))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Example\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Example"));
    }

    @Test
    void readerCannotPost() throws Exception {
        mvc.perform(post("/api/items")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_items.read")
                ))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Denied\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownEndpointIsNotPublic() throws Exception {
        // Không ràng buộc cụ thể 403/404 nếu error dispatch thay đổi,
        // nhưng API không được trả một business response thành công.
        mvc.perform(get("/api/debug").with(jwt()))
            .andExpect(result -> {
                int status = result.getResponse().getStatus();
                org.junit.jupiter.api.Assertions.assertTrue(
                    status == 403 || status == 404
                );
            });
    }
}
```

Giải thích kết quả: `@SpringBootTest` + `@AutoConfigureMockMvc` tích hợp Servlet/Spring Security filters; `jwt()` tạo security principal test. `@MockBean JwtDecoder` làm test không liên hệ IdP/JWKS thật, nên **test này không chứng minh chữ ký, issuer và audience đã được xác minh đúng**. Phải có test khác đi qua `BearerTokenAuthenticationFilter` với JWT có chữ ký thật và JWKS mock/IdP staging.

Với API `oauth2ResourceServer`, request anonymous thường 401; token hợp lệ nhưng thiếu `SCOPE_items.read` thường 403. Test theo code mẫu chỉ đánh giá các rule trong app và service. Đừng gọi nó là pentest hoặc audit production hoàn chỉnh.

### 7.2. `DeploymentGuardTest.java`

```java
package com.example.deploysecure;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DeploymentGuardTest {

    @Test
    void cleanPropertiesPass() {
        DeploymentGuard guard = new DeploymentGuard(new MockEnvironment());
        assertDoesNotThrow(guard::afterPropertiesSet);
    }

    @Test
    void legacyPasswordPropertyFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("spring.security.user.password", "dummy-for-test");

        DeploymentGuard guard = new DeploymentGuard(environment);
        assertThrows(IllegalStateException.class,
            guard::afterPropertiesSet);
    }

    @Test
    void demoEnabledFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("app.demo.enabled", "true");

        assertThrows(IllegalStateException.class,
            () -> new DeploymentGuard(environment).afterPropertiesSet());
    }

    @Test
    void h2ConsoleEnabledFails() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("spring.h2.console.enabled", "true");

        assertThrows(IllegalStateException.class,
            () -> new DeploymentGuard(environment).afterPropertiesSet());
    }
}
```

Giá trị `dummy-for-test` chỉ là chuỗi thử trong `src/test`, **không phải tài khoản hoạt động** và không được phát hành. Test này xác minh hành vi fail-closed cho các property đã biết, không quét toàn bộ codebase.

### 7.3. Lệnh chạy

```bash
# Khi project có Gradle wrapper phù hợp:
./gradlew clean test

# Kiểm tra dependency runtime và tạo release artifact.
./gradlew dependencies --configuration runtimeClasspath
./gradlew bootJar
```

Với project mới chưa có Gradle wrapper, chạy bằng Gradle tương thích hoặc tạo wrapper theo quy trình chuẩn của tổ chức. Không có stdout cố định; JUnit/Gradle quyết định pass/fail. **Chưa thể coi sẵn sàng triển khai chỉ vì `test` pass**: còn cần scanner, kiểm tra artifact và kiểm thử IdP/HTTPS thật.

### 7.4. Bài test âm tính không được bỏ qua

Bên cạnh test trên, integration test cấp release nên có:

- JWT có chữ ký sai, thuật toán không tin cậy, `iss` sai, `aud` sai, token hết hạn, thiếu scope.
- `Authorization: Basic ...` và cookie session không được chấp nhận cho API token-only.
- Không có tài khoản `user` mặc định/`demo`/`admin` đăng nhập được qua bất kỳ route nào, trừ danh tính thật đã được provisioning.
- `/h2-console`, `/debug/**`, `/internal/**`, Swagger và actuator endpoints đều theo policy deploy.
- Không có `permitAll()` quá rộng hoặc bypass filters.
- CORS/CSRF đúng với kiểu client; đừng tắt CSRF trong web session test.
- Query theo tenant/owner không làm lộ dữ liệu dù user có token hợp lệ.
- Sau khi tắt một account hoặc revoke token, request tiếp theo được xử lý theo thời hạn và policy đã công bố.
- Missing issuer/secret/cấu hình bắt buộc không làm app fallback sang user demo hoặc `permitAll`.
- Docker/JAR image và deploy manifest thực tế đã không chứa credential mẫu.

## 8. Secret management: di chuyển không đồng nghĩa đã an toàn

### 8.1. Nên đặt bí mật ở đâu?

Mỗi môi trường nên có nơi cấp bí mật được kiểm soát:

```text
Source code + build artifact
   |
   | Chỉ chứa TÊN cấu hình / secret reference
   v
Deployment configuration / workload identity
   |
   v
Secret manager hoặc secret mount có ACL
   |
   v
Process nhận credential tại runtime
   |
   +-- Sử dụng qua JDBC/IdP/SMTP/third-party API
   +-- Không in vào log, crash report hoặc HTTP error
```

Các phương án có tính chất khác nhau:

- **Secret manager** có IAM, audit, version, rotation và phân quyền theo workload thường tốt hơn password trong YAML.
- **Environment variables** tiện nhưng có thể xuất hiện ở process inspection, debug dump hoặc công cụ vận hành; cần hạn chế ai có quyền đọc và không echo chúng.
- **Mounted secret file** cho phép quản lý file permission/rotation, nhưng phải bảo vệ đường dẫn, cache, backup và việc app reload.
- **Kubernetes Secret** là đối tượng chứa secret; Base64 encoding **không phải encryption**. Cần bảo vệ etcd, RBAC, encryption-at-rest và admission policy theo cluster.
- **CI/CD variable** không nên echo hoặc đổ vào artifact. Build-time secret khác runtime secret; đừng dùng Docker `ARG`/`ENV` để đóng gói credential trong image layer.

Với JWT resource server dùng asymmetric signing, **public key/JWKS không phải private signing key**; resource server thường chỉ cần public verification key/issuer config. Đừng sao chép private signing key của authorization server vào mỗi API.

### 8.2. Nếu secret từng bị commit thì làm gì?

Quy trình xử lý:

1. Phân loại secret: DB credential, OAuth client secret, JWT signing key, access token, API key, user password, session secret.
2. **Rotate/revoke tại nguồn cấp** hoặc vô hiệu hóa account/token. Xóa khỏi Git không thu hồi khả năng sử dụng của secret cũ.
3. Xác định log/artifact/CI backups/registry/documentation nào có thể đã chứa secret.
4. Cập nhật secret manager/workloads bằng phiên bản mới và kiểm tra dịch vụ chạy bằng secret mới.
5. Quan sát truy cập bất thường trước và sau rotation; phối hợp nhóm an ninh/incident response nếu exposure có rủi ro thực.
6. Chỉ khi đã vô hiệu hóa secret, mới xử lý việc loại khỏi branch/history/ảnh chụp/tài liệu theo chính sách, không tự ý force-push làm mất lịch sử/ảnh hưởng team.
7. Đặt detection rule để ngăn tái xuất hiện.

**Khi signing key JWT đã lộ, đổi key cần tính cả token đang lưu hành.** Có thể phải revoke phiên/token, đổi `kid`/JWKS, phối hợp thời gian chuyển đổi và bảo vệ các key cũ. Không mặc định key rotation là thao tác “chỉ thay biến” mà không ảnh hưởng người dùng.

### 8.3. Tránh dữ liệu nhạy cảm trong logs

Đặc biệt rà:

```text
Authorization
Cookie / Set-Cookie / JSESSIONID
access_token / refresh_token / id_token
password / client_secret / api_key
Authorization Code, OTP, reset-password token
JWT signing key, database password
CSRF token
```

Dùng request ID, route template, user ID được giảm thiểu và mã lỗi đã chuẩn hóa, **không ghi raw headers/body**. Spring Security DEBUG/TRACE có thể hỗ trợ debug trong staging nhưng không nên bật bừa ở production; thiết lập logger ở mức phù hợp và redaction policy.

## 9. Kiểm tra CI/CD trước khi phát hành

### 9.1. Static scan có thể tự động hóa — nhưng không thay review

Dùng một script tìm **dấu hiệu** demo trong resource/config. Ví dụ dưới đây chỉ quét đường dẫn có trong Git; nó in **tên file**, không in dòng chứa password:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Chạy ở root repository có src/main/resources.
# Chỉ kiểm tra một nhóm pattern trong resource text;
# secret scanner/SAST khác phải kiểm tra Java, IaC, history, artifacts.
if git grep -I -l -E \
  'spring\.security\.user\.(name|password)|\{noop\}|app\.demo\.enabled[=: ]+true' \
  -- src/main/resources; then
  echo "BLOCKED: demo credential/config marker in main resources" >&2
  exit 1
fi

echo "No simple demo markers found in main resources"
```

**Giới hạn:** script chỉ bắt pattern cụ thể (và có thể có false positive), không hiểu YAML lồng nhiều dòng, không quét Java/Helm/DB, không phát hiện mọi password/key. Thực hiện **secrets scanning**, SAST, dependency/IaC scan và code review ở các bước riêng. Đặt allowlist rõ ràng cho fixtures `src/test/**`, nhưng đừng để allowlist che đường copy fixture vào artifact.

Có thể dùng secret scanners như Gitleaks/TruffleHog theo chuẩn tổ chức. Chạy trên **working tree, commits liên quan và history khi cần**, với detection rules được duy trì, không chỉ kiểm tra `HEAD`. Không vô hiệu hóa CI khi scanner có false positive; tạo exception có owner, lý do và thời hạn.

### 9.2. Quét các đường Java có rủi ro

Những pattern cần *xem xét*, không nhất thiết mọi lần xuất hiện đều là lỗi:

```text
InMemoryUserDetailsManager
User.withUsername(...)
withDefaultPasswordEncoder()
NoOpPasswordEncoder
{noop}
spring.security.user.name
spring.security.user.password
anyRequest().permitAll()
web.ignoring()
csrf.disable()
cors.configurationSource(...)
spring.h2.console.enabled
management.endpoints.web.exposure.include=*
/debug/**
/test-login
/issue-token
@Profile("dev")
System.out.println(...token...)
```

**Không tự động kết luận mọi `csrf.disable()` đều sai.** Một API Bearer-header-only stateless có threat model rõ có thể dùng. Ngược lại, `csrf.disable()` toàn cục cho web session có thể là rủi ro nghiêm trọng. `permitAll()` cho `/login`/public health có thể đúng; `anyRequest().permitAll()` trong chain production thường đáng chặn.

Chính sách CI nên gắn *ngữ cảnh*: file nào là production, route nào được phép public, security exception nào đã được review, secret nào do test scope cung cấp. Rất hữu ích khi có test tự động kiểm tra route inventory và quyền.

### 9.3. Kiểm tra binary artifact, không chỉ repository

Bản build phát hành có thể mang:

- `application-dev.yml`, `application-local.properties`, `data.sql`, H2 database, test data do copy task sai.
- Class `DemoAuthenticationProvider`, `DevSecurityConfig`, endpoint `/debug/**` vẫn nằm trong JAR dù có `@Profile("dev")`.
- Tệp PEM/private key, credential JSON, cert bundle có private key hoặc seed credential.
- Docker image layer từng chứa secret, dù lệnh sau đã `rm` file.
- Java agent/debug port hoặc Docker entrypoint bật debug mode.

**Một `@Profile("dev")` chỉ quyết định bean có được load trong Spring context; không khiến class/resource biến mất khỏi JAR.** Nếu artifact production có thể bật profile này do deploy config, vẫn có nguy cơ. Tách demo code/fixtures ra khỏi production build hoặc bảo đảm việc package có policy xác minh được; đừng dựa chỉ vào tên profile.

Một chuỗi QA hợp lý:

```text
git commit
   -> secret scan + SAST + dependency / IaC scan
   -> compile + unit/integration security tests
   -> package release JAR
   -> inspect packaged resources/classes
   -> build container image (no secret build args)
   -> image/SBOM/vulnerability scan
   -> deploy to staging with prod-like config
   -> smoke tests auth, permission, health, debug denial
   -> approval / progressive rollout / monitoring
```

### 9.4. Đừng tin các “bằng chứng” không đủ

- **`git grep` không tìm thấy `admin123`:** vẫn có thể có account seed trong database hoặc IdP.
- **`/api/private` trả 401:** có thể còn một `/debug/admin` cho phép không cần auth.
- **Không thấy generated password trong startup logs:** có thể do logger WARN bị ẩn hoặc app có user store khác nhưng sai.
- **Các test với `@WithMockUser` pass:** không chứng minh mật khẩu/JWT thật đã được xác minh.
- **Đã xóa YAML khỏi Git:** release image/JAR trước đó vẫn có secret.
- **`@Profile("dev")` không active trong local:** chưa chứng minh profile ấy không thể active trong production.
- **Token JWT ký đúng:** chưa chứng minh đúng issuer, audience, scope và quyền theo đối tượng.

## 10. Runtime smoke tests sau deploy

Sau khi deploy staging/pre-production bằng artifact cuối cùng, thử ở **đường HTTP giống production**: TLS, ingress, DNS, proxy, cookies và auth provider tương ứng.

| Thao tác | Kỳ vọng trong API Bearer-only | Bằng chứng |
| --- | --- | --- |
| Anonymous `GET /api/items` | 401, Bearer challenge thích hợp | Response status/header, request ID |
| Token hợp lệ có `items.read` | 200 | Không lộ dữ liệu ngoài scope |
| Token hợp lệ thiếu `items.read` | 403 | Scope rule đúng |
| JWT sai signature/`iss`/`aud`/expired | 401 | Decoder từ chối |
| Cookie session hoặc Basic credentials đơn lẻ | Không cấp API access | Không có fallback account |
| `POST /api/items` với READ scope | 403 | Không dùng quyền READ cho WRITE |
| `GET /actuator/health` | Theo policy health check đã phê duyệt | Không lộ details/secret |
| `/h2-console`/`/debug/**` | Không có quyền truy cập tính năng debug | Không có endpoint công khai |
| Bật property demo trong staging startup | App từ chối khởi động hoặc deployment gate chặn | Thông điệp **tên property**, không lộ giá trị |
| Mất issuer/audience config | Không có fallback permissive login | Fail closed / readiness fail |
| Deploy image mới không mang fixtures | Không có file/user/key demo | Artifact scan + runtime checks |

Các smoke tests phải xác minh **body/data side effects**, không chỉ status. Với update/delete không đủ quyền, DB không được thay đổi. Với export, file không được chứa dữ liệu ngoài tenant. Lưu bằng chứng đã redacted trong release ticket.

### Ví dụ curl không mang bí mật thật

```bash
# Không có Authorization -> thường là 401 Bearer.
curl -i https://api.example.org/api/items

# Token do IdP chính thức phát hành; không ghi token thật vào ticket.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.org/api/items

# Endpoint debug không được trả tính năng/test credential.
curl -i https://api.example.org/debug/login
```

Đường URL chỉ là **mẫu**, không phải địa chỉ dịch vụ đang chạy. Hạn chế dùng `curl -v` với credential thật vì verbose output có thể chứa header Authorization. Thực hiện test ở môi trường được phép và che token trong log.

## 11. Kế hoạch chuyển đổi không làm gián đoạn hệ thống

### Giai đoạn 1 — Inventory và dependency mapping

Tìm user demo, security filters, dev endpoints, secrets và tài khoản IdP. Xác định ai đang **thực sự phụ thuộc** vào những credential đó (tự động hóa, batch jobs, support tools). Không vội xóa rồi phát hiện hệ thống đang có một integration production sử dụng user demo.

### Giai đoạn 2 — Cung cấp danh tính thật

- Provision user/service principals chính thức qua IdP hoặc store được quản lý.
- Gán scopes/roles tối thiểu; review owner/tenant policy.
- Chuyển clients sang flow đúng, ví dụ OAuth2 client credentials cho machine-to-machine thay shared admin password.
- Thay đổi deployment secrets để không dùng key/password bị lộ.

### Giai đoạn 3 — Chặn phát sinh mới

- Code review rule chặn new `InMemoryUserDetailsManager`/`{noop}` trong `src/main`.
- Static/secrets scan trên branch và IaC.
- CI kiểm tra permission boundary, JWT validation, no public debug.
- Guard fail-closed cho demo toggles đặc thù.
- Lưu lại ngoại lệ có owner, lý do, thời hạn nếu vì môi trường lab cần một fixture.

### Giai đoạn 4 — Xóa/vô hiệu hóa đường cũ

- Xóa demo accounts tại app user store và IdP.
- Revoke tokens, refresh tokens, client secrets và key nếu từng sử dụng/đã có khả năng lộ.
- Xóa seed scripts và endpoints; kiểm tra tài khoản cũ **không đăng nhập được** bằng đường HTTP thực.
- Nếu không thể vô hiệu hóa tức thời vì dependency, đặt kế hoạch và kiểm soát bù trừ theo quyết định rủi ro được duyệt; không âm thầm để account cũ.

### Giai đoạn 5 — Release gate và theo dõi

- Test staging với artifact cuối, kiểm tra config đã merge từ platform.
- Kiểm tra `SecurityFilterChain` đang chạy, auth providers, endpoint mappings và scope permissions.
- Progressive rollout, audit lỗi 401/403, số lần login, các request tới endpoint demo cũ.
- Theo dõi lịch trình rotate và đóng các exception tạm thời.
- Xác nhận có rollback an toàn **không phục hồi lại secret hoặc account demo bị thu hồi**.

## 12. Rủi ro khi dùng Spring Profiles

Spring Profiles tách cấu hình cho từng môi trường nhưng **không phải security boundary**:

```java
@Configuration
@Profile("dev")
class LocalOnlyUsers {

    @Bean
    UserDetailsService users() {
        // User demo nếu class này có mặt trong JAR.
        return new InMemoryUserDetailsManager();
    }
}
```

Đoạn này là **ví dụ cảnh báo**, không phải thành phần của baseline. Dù bean không được tạo khi profile khác `dev`, bytecode vẫn có thể nằm trong JAR và chỉ cần deploy bật `dev` nhầm là nó xuất hiện. Thêm nữa, một `SecurityFilterChain` khác có thể ghi đè các rule khác tùy order/matcher.

Phương án có độ an toàn cao hơn:

- Test data và mock authentication nằm trong `src/test`.
- Local fake IdP hoặc dev-only module được **tách khỏi production artifact**.
- Production baseline từ chối demo toggles và không có “fallback to demo” nếu thiếu config.
- Release pipeline kiểm tra profile thực tế, property sources và artifact contents.
- Lệnh deploy không tự bật `dev`/`local` khi env thiếu; dùng cấu hình explicit có validation.

Nếu tổ chức **buộc** giữ một dev-only class trong artifact, phải có threat review, activation guard độc lập, scanner, kiểm tra artifact, quyền deploy và monitoring; chỉ ghi `@Profile("dev")` không đủ.

## 13. Cấu hình web session cần kiểm tra khác API Bearer

Bài mẫu ở mục 6 **không có web session**. Nếu dự án thực dùng browser login, cần các bước riêng:

- User đăng nhập bằng IdP/OIDC hoặc store đã được quản lý, không phải `admin/admin`.
- `formLogin`/`oauth2Login`, success/failure/logout handlers được cấu hình đúng URL.
- Cookie session có `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` và timeout phù hợp.
- `CsrfFilter` bảo vệ các HTTP methods làm thay đổi trạng thái. Nếu SPA dùng cookie, có cơ chế cấp và refresh CSRF token sau login/logout.
- Logout dọn session, context, remember-me, CSRF; với SSO cần phân biệt local logout và IdP logout.
- Không dùng `SessionCreationPolicy.STATELESS` cho toàn ứng dụng web rồi giả định login vẫn được lưu.
- Không mở `/login` bằng `web.ignoring()` khi `permitAll()` là lựa chọn phù hợp; giữ security headers/filter behavior.
- Có integration test POST login đúng/sai, session persistence, CSRF, logout, user bị vô hiệu hóa, redirect và role.

**Chuyển từ demo Basic/in-memory sang OIDC không chỉ là thêm một dependency.** Cần cấu hình redirect URI, cookie during cross-site flow, issuer/client ID, client secret lưu ở secret manager, scope mapping, logout và test browser/proxy thật.

## 14. Review từng loại cấu hình minh họa thường sót

### 14.1. `permitAll` quá rộng

Sai:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
)
```

An toàn hơn khi có danh sách route tường minh:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/items")
        .hasAuthority("SCOPE_items.read")
    .anyRequest().denyAll()
)
```

**Không phải mọi `permitAll` đều sai**; trang login, resource public và health check có thể cần được phép. Nhưng phải liệt kê chính xác mục đích và kiểm tra rằng filter chain khác không bao phủ/chuyển hướng bất ngờ.

### 14.2. `web.ignoring` và nhiều SecurityFilterChain

`web.ignoring()` làm request bỏ qua Spring Security filters cho path đó. Với nhiều URL public, `permitAll()` trong chain thích hợp vẫn duy trì security headers. Nếu có nhiều `SecurityFilterChain`, kiểm tra `securityMatcher` của chain đầu tiên và `@Order`; rule “đúng” ở chain không được chọn không có tác dụng.

### 14.3. CSRF/CORS copy từ demo

- Không tắt CSRF toàn hệ thống chỉ vì demo Postman không gửi token. Với cookie session, có thể tạo rủi ro CSRF.
- Không dùng CORS wildcard với credentialed requests.
- Bearer API không tự an toàn khi token nằm trong cookie/browser auto-send.
- CORS không phải authentication hay data authorization; server-to-server clients không bị hạn chế như browser JavaScript.

### 14.4. Debug endpoints và actuator

Không để `/h2-console`, `/debug/**`, `/dev/**`, `/test-login` hoặc `/mint-token` mở công khai trong production. Actuator health/metrics/env/heapdump/loggers có độ nhạy khác nhau; quản lý cả exposure và authorization/network. Không cấu hình `management.endpoints.web.exposure.include=*` cho internet-facing service mà chưa có security design được duyệt.

### 14.5. HTTP Basic, form login và password storage

Đừng giữ HTTP Basic account cố định để “dự phòng khẩn cấp” nếu không có chính sách break-glass được kiểm soát chặt (MFA khi khả thi, quản lý bí mật, phê duyệt và audit). Shared break-glass account là chủ đề threat review riêng, **không nên sinh ra từ user demo**.

### 14.6. JWT signing key demo

Một string `jwt.secret=secret123` hoặc RSA private key mẫu trong resource là credential nghiêm trọng, không chỉ là cấu hình. Nâng lên prod cần issuer/AS chính thức, JWT validation và rotation. Chú ý từng phiên bản Spring Security có khác biệt ở JWT decoder builder; có các advisory về việc **không tự động kiểm tra issuer khi dùng một số builder/version**. Dùng auto-configuration/validator phù hợp, test wrong issuer và cập nhật bản vá.

### 14.7. PasswordEncoder giả

`NoOpPasswordEncoder`, `{noop}`, `withDefaultPasswordEncoder()` trong đường production không phù hợp. Tuy nhiên đừng xóa các test fixture theo kiểu làm mọi unit test không còn kiểm chứng login flow; giữ chúng **chỉ trong test scope** và đảm bảo không thể xuất hiện trong artifact/môi trường thật.

## 15. Mẫu biên bản xác nhận cho người review release

| Hạng mục | Bằng chứng kỳ vọng | Người chịu trách nhiệm |
| --- | --- | --- |
| Demo users | Không tồn tại trong app runtime, DB/IdP, secret store | Backend + Identity |
| Seed password/key | Đã xóa khỏi artifact, rotate/revoke nếu từng dùng | Security/Platform |
| Auth mechanism | Chỉ chain/provider đã phê duyệt đang hoạt động | Backend |
| URL authorization | Mỗi route có quyền/matcher; fallback deny | Backend |
| CSRF/CORS | Đúng loại client, browser test nếu cần | Backend + Frontend |
| Data scope | Tenant/owner/action-level tests | Backend/QA |
| Security configs | Không có flag demo/H2/debug/TRACE nguy hiểm | Platform + Backend |
| Secrets | Secret manager/ACL/rotation/audit | Platform/SRE |
| Tests | CI + staging smoke tests âm tính và dương tính | QA/Backend |
| Artifact | JAR/image/IaC được scan; không package fixtures | DevOps |
| IdP | Issuer/audience/scopes/client credentials chính thức | Identity |
| Incident readiness | Kế hoạch rotate/revoke/rollback | Security + Operations |

Khi ký duyệt, không chỉ điền “Done”. Lưu đường dẫn tới kết quả CI, artifact digest, deploy manifest version, test run và ngày rotate (không đính kèm mật khẩu hoặc token).

## 16. Checklist cuối cùng trước go-live

- [ ] Không còn account demo có thể dùng được: trong app, database, IdP và hệ thống tích hợp.
- [ ] Không còn `spring.security.user.name/password` hoặc `InMemoryUserDetailsManager` demo trong production path.
- [ ] Không còn `{noop}`/`NoOpPasswordEncoder`/`withDefaultPasswordEncoder()` dùng cho mật khẩu thật.
- [ ] Không còn khóa ký JWT, client secret, DB password hoặc token được hard-code/đóng gói.
- [ ] Mọi credential từng lộ trong Git/CI/docs đã được đánh giá và rotate/revoke.
- [ ] Cơ chế identity production có owner, provisioning/offboarding, MFA khi cần, least privilege.
- [ ] JWT Resource Server validate issuer/audience/expiry/signature/scopes; không nhận ID token thay access token.
- [ ] Không còn `anyRequest().permitAll()`, `web.ignoring()` hoặc debug bypass không được phê duyệt.
- [ ] CSRF của session web/BFF không bị tắt khi còn credential tự gửi.
- [ ] H2 console/test endpoints/actuator nhạy cảm không exposed cho client không được phép.
- [ ] Log không in password, Authorization, Cookie, CSRF token hoặc private keys.
- [ ] CI scan source, history, secret, IaC, dependencies và artifact cuối.
- [ ] Staging test login/auth/permission với issuer và gateway gần production.
- [ ] Unknown route và không có credential đều bị deny; không có login fallback.
- [ ] Production artifact không chứa test data/config demo có thể kích hoạt lại.
- [ ] Runtime config được validate; thiếu/không hợp lệ không làm app mở quyền.
- [ ] Có runbook xử lý secret exposure, rollback không phục hồi đường demo.
- [ ] Reviewer đã xác minh bằng chứng, không chỉ tin lời nhắc trong checklist.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ xóa `password=admin` trong `application.yml` chưa chắc đã loại bỏ tài khoản demo?
2. Khi nào Spring Boot có thể tạo `user` và generated password; vì sao không dùng nó làm identity production?
3. `SecurityFilterChain` custom có luôn xóa `UserDetailsService` mặc định không?
4. Vì sao `{noop}` nguy hiểm với mật khẩu thật, và `PasswordEncoder` nào thích hợp hơn?
5. Tại sao `@Profile("dev")` không phải bằng chứng dev account không nằm trong JAR production?
6. Nếu secret từng commit vào Git rồi được xóa ở commit mới, bước bắt buộc tiếp theo là gì?
7. `csrf.disable()` có thể hợp lý cho API loại nào và không hợp lý cho ứng dụng nào?
8. Vì sao `with(jwt())` không chứng minh JWT issuer/audience/signature được xác minh?
9. Vì sao secret injection qua env vẫn cần bảo vệ quyền xem process và logs?
10. Một actuator health public có đồng nghĩa toàn bộ actuator có thể public không?
11. Vì sao test `/api/private` trả 401 chưa chứng minh toàn bộ hệ thống không còn backdoor?
12. Deploy script phải làm gì khi thiếu issuer/DB secret thay vì tự bật demo fallback?

**Gợi ý:** (1) Java user store, DB seed/IdP/image vẫn có thể tồn tại; (2) fallback development user không có lifecycle production; (3) không nhất thiết, phụ thuộc auto-configuration/dependencies; (4) không có hash, dùng encoder có salt/work factor và lifecycle đúng; (5) profile chỉ quyết định load bean; (6) revoke/rotate và truy vết nơi secret bị sao chép; (7) header-only Bearer vs cookie session; (8) principal mock bypass decoder; (9) env vẫn có bề mặt lộ; (10) không, cần exposure/auth độc lập; (11) còn route bypass khác; (12) fail closed, alert, không dùng password mặc định.

## Tài liệu tham khảo

- Spring Boot — Spring Security auto-configuration và user mặc định: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Boot — Profiles và profile-specific configuration: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Actuator endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Security — Authorization for Servlet Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP — CI/CD Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html
