# Tích hợp LDAP hoặc nhà cung cấp OIDC trong môi trường thử nghiệm

> **Học phần:** Spring Security – authentication. **Nhóm:** Thực hành tổng hợp. Bài lab trình bày **hai lựa chọn độc lập**: A – xác thực tài khoản bằng LDAP bind với UnboundID nhúng, và B – đăng nhập OpenID Connect (OIDC) với Keycloak local. Có thể làm **một trong hai** để hoàn thành mục tiêu, hoặc làm cả hai để so sánh. Kỹ thuật dùng Java 17+, Spring Boot 3.x/Spring Security 6.5 trên Servlet MVC. Các mã cấu hình phải được ghép vào một project Boot có Gradle wrapper/parent hợp lệ; chương trình Java 17 độc lập ở cuối bài được ghi rõ. Không dùng test password, user, token hoặc IdP trong bài cho production.

## 1. Mục tiêu cần đạt

Sau khi thực hành, bạn có thể:

1. Phân biệt **LDAP bind** (ứng dụng nhận username/password và LDAP server xác minh) với **OIDC login** (người dùng đăng nhập ở IdP, client ứng dụng xử lý Authorization Code và xác minh ID Token).
2. Dựng server LDAP in-memory bằng UnboundID và data fixtures LDIF hoặc khởi động nhà cung cấp OIDC Keycloak trong container, không phụ thuộc tài khoản công ty thật.
3. Tạo project Spring Boot có `SecurityFilterChain` chỉ kích hoạt profile `ldap-lab` hoặc `oidc-lab`.
4. Hiểu `LdapBindAuthenticationManagerFactory`, `EmbeddedLdapServerContextSourceFactoryBean`, DN, search base và mapping groups/authorities.
5. Hiểu `ClientRegistration`, `issuer-uri`, callback `/login/oauth2/code/{registrationId}`, `state`, `nonce`, code exchange, ID Token claims và user session.
6. Thử luồng thành công và âm tính: password sai, user không tồn tại, LDAP bind lỗi; OIDC redirect mismatch, issuer/client-secret mismatch, claims và scope/roles.
7. Phân biệt test `@WithMockUser` hoặc `oidcLogin()` **đặt sẵn principal** với test đi qua verifier thực sự.
8. Kiểm soát TLS, secrets, cookies, CSRF, local-account identity mapping, account disable/revoke và tính đúng đắn authorization.
9. Ghi lại kết quả có thể kiểm chứng bằng `curl -i`, Browser DevTools đã che token, logs có redaction và test cases.
10. Dọn môi trường sau khi làm, không để development IdP, directory fixtures hoặc credentials còn mở trên mạng.

## 2. Hai cơ chế – không được đánh đồng

| Tiêu chí | LDAP bind | OIDC Authorization Code |
|---|---|---|
| Hệ thống xác minh danh tính | LDAP directory, ví dụ OpenLDAP/AD/UnboundID | OIDC Provider/Identity Provider (IdP), ví dụ Keycloak |
| Credential ban đầu | Username và password gửi tới app | Browser chuyển tới IdP để user nhập credential |
| Bước xác minh | Directory xác minh password qua bind | IdP xác minh credential/MFA, client xác minh token/protocol |
| App nhận sau login | LDAP Authentication/attributes/groups | OIDC principal/ID Token đã verify, (issuer, subject) |
| Bằng chứng login | Bind success | Code exchange, ID Token signature, iss/aud/expiry/nonce |
| Có redirect tới hệ thống khác? | Không bắt buộc | Có, theo Authorization Code flow |
| Cookie session của app | Có thể có sau form login | Thường có sau OIDC browser login |
| Nguồn quyền | LDAP groups/application policy | Claims IdP hoặc local authorization policy |
| Lỗ hổng cấu hình hay gặp | DN sai, LDAP injection, LDAP plaintext, service bind quá quyền | Redirect quá rộng, issuer sai, token nhầm loại, thiếu state/nonce |
| Tầng test thực | Bind/password thật qua LDAP provider | Browser/HTTP redirect tới test IdP, code, ID Token verification |

**Tình huống kết hợp:** nhiều tổ chức dùng Keycloak federation tới LDAP/AD. Khi đó **Spring app chỉ tích hợp OIDC**, còn Keycloak nói LDAP ở phía sau. Không gọi một ứng dụng có OIDC login là “đã bind LDAP trực tiếp” nếu nó không hề dùng LDAP provider.

### 2.1. LDAP bind không phải lấy mật khẩu từ LDAP về so sánh

Với bind authentication, Spring Security tạo LDAP authentication request, xác định DN, yêu cầu LDAP server kiểm tra username/password. Không nên trích `userPassword` của người dùng ra ứng dụng rồi tự so. Spring Security LDAP có `LdapAuthenticator`, hỗ trợ bind và password comparison như hai chiến lược khác nhau; bài lab dùng **bind**, không dùng `UserDetailsService`/`PasswordEncoder.matches` cho directory password.

### 2.2. ID Token khác Access Token

OIDC bổ sung lớp xác thực danh tính lên OAuth2. **ID Token** có `iss`/`sub`/`aud`/`exp` và các claim về login; **Access Token** dành cho resource API có audience/scopes. Dù cả hai có thể trông như JWT, **không** dùng arbitrary Access Token làm chứng minh user login và không coi ID Token là access token phù hợp cho API.

## 3. Kiến trúc lab

### 3.1. LDAP

```text
Browser hoặc curl -u user:password
          |
          v
Spring Security FilterChain
          |
  BasicAuthenticationFilter hoặc
  UsernamePasswordAuthenticationFilter
          |
          v
AuthenticationManager từ
LdapBindAuthenticationManagerFactory
          |
          | LDAP bind theo DN đã tìm
          v
UnboundID embedded LDAP (JVM)
          |
     success / failed credentials
          |
          v
SecurityContext / Authentication
          |
  Authentication có quyền? -> /whoami
```

### 3.2. OIDC

```text
Browser               Spring Boot client                  Keycloak IdP
   | GET /whoami              |                                  |
   |------------------------->|                                  |
   | 302 login / start OIDC   |                                  |
   |<-------------------------|                                  |
   | GET /oauth2/authorization/keycloak                          |
   |------------------------->|                                  |
   |           state, nonce, redirect_uri, client_id             |
   |<-------------------------|                                  |
   |----------------------------------------------------------->|
   |           User nhập credential tại trang IdP                |
   |<--------------------------------- 302 callback code+state   |
   | GET /login/oauth2/code/keycloak?code=...&state=...          |
   |------------------------->|                                  |
   |                          | POST /token + client auth       |
   |                          |--------------------------------->|
   |                          |<---------------------------------|
   |                          | ID Token & verify               |
   |  Session cookie, redirect|                                  |
   |<-------------------------|                                  |
   | GET /whoami với cookie   |                                  |
   |------------------------->|                                  |
   |                    200 principal name                       |
```

**Không** cho browser nhận `client_secret`; token exchange của confidential client thực hiện từ backend. Code và `state` trong callback là dữ liệu nhạy cảm; đừng sao chép URL chứa code vào báo cáo công khai.

## 4. Điều kiện thực hành, ranh giới an toàn

Bạn cần JDK 17+, Spring Boot project Gradle/Maven, IDE, terminal/curl, một browser và Docker/Podman nếu chọn OIDC. Cần hai cổng local: `8080` dành cho ứng dụng, `8180` dành cho Keycloak. Với LDAP nhúng, **không cần Docker**.

- Chỉ dùng user, password và realm thử nghiệm; không dùng AD/domain hay IdP production.
- Bind Keycloak container vào `127.0.0.1`, không publish ra Internet.
- HTTP cho localhost là ngoại lệ **chỉ trong lab**; ứng dụng thật phải dùng HTTPS và LDAP qua LDAPS/StartTLS.
- Ghim dependency/version theo **BOM tương thích**, không tự thêm Spring Security 7 vào Boot 3 để copy mẫu.
- Có thể làm một nhánh trước; hai cấu hình sử dụng `@Profile` nhằm không khởi động hai flow và tranh `SecurityFilterChain`.
- Không tắt CSRF, issuer validation hoặc TLS certificate validation để “cho demo chạy”.
- Dùng private browser session cho test lặp lại để session login cũ không che lỗi authentication.
- Không log Authorization header, Basic password, LDAP manager password, OAuth code, ID/access token hay cookie.

## 5. Cấu trúc project mẫu

```text
security-integration-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/
    ├── main/
    │   ├── java/lab/security/
    │   │   ├── SecurityLabApplication.java
    │   │   ├── WhoAmIController.java
    │   │   ├── LdapLabSecurity.java
    │   │   └── OidcLabSecurity.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-oidc-lab.yml
    │       └── users.ldif
    └── test/java/lab/security/
        └── LdapAuthenticationTests.java
```

Project khởi tạo có Spring Boot plugin/repositories/Gradle Wrapper và JDK 17. Nếu tạo project từ Spring Initializr, giữ cùng một nhánh Spring Boot 3.x; tài liệu [Spring Security LDAP 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html) là cơ sở cho các lớp LDAP dùng bên dưới.

### 5.1. Dependencies

Trích `dependencies` trong Gradle Groovy DSL – **không phải toàn bộ file build.gradle**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // LDAP lab
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
    runtimeOnly 'com.unboundid:unboundid-ldapsdk:6.0.11'

    // OIDC lab
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Tests
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`6.0.11` của UnboundID là bản được Spring Security 6.5 Reference minh họa; khi dùng thực tế vẫn phải kiểm version compatibility/advisories. Không cần `spring-boot-starter-oauth2-resource-server` để làm **OIDC browser login**; chỉ thêm nếu app còn nhận Bearer Access Token cho REST API.

### 5.2. application.yml chung

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

logging:
  level:
    root: INFO
```

Không bật full HTTP request/response debug tự động vì callback OIDC có `code`, session cookie và credentials có thể xuất hiện trong logs.

### 5.3. Main class

`src/main/java/lab/security/SecurityLabApplication.java`:

```java
package lab.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

### 5.4. Controller cho mọi profile

`src/main/java/lab/security/WhoAmIController.java`:

```java
package lab.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/")
    public String home() {
        return "Security lab: open /whoami after logging in";
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI(Authentication auth) {
        return Map.of("name", auth.getName());
    }
}
```

Controller **không xác minh** danh tính; nó chỉ sử dụng `Authentication` từ Spring Security. Với LDAP, tên có thể là `student`; với OIDC, `name` thường là một giá trị `sub`/principal claim theo mapping, không bảo đảm bằng `preferred_username` hay email.

## 6. Nhánh A – LDAP nhúng với UnboundID

### 6.1. Các khái niệm directory

- **Distinguished Name (DN):** đường định danh entry, ví dụ `uid=student,ou=people,dc=springframework,dc=org`.
- **Base DN:** gốc tìm kiếm `dc=springframework,dc=org`.
- **Organizational Unit (OU):** nhóm cây, `ou=people` chứa các user của demo.
- **uid:** login attribute trong lab; Microsoft AD còn có `sAMAccountName`, `userPrincipalName`, không mặc nhiên giống nhau.
- **Bind:** LDAP server xác minh credential.
- **Search filter:** xác định user DN khi directory có nhiều OU, cần đúng escaping và permission.
- **Groups/roles:** membership LDAP **không tự động là `ROLE_ADMIN`**; app cần mapping theo policy.

### 6.2. Tạo dữ liệu users.ldif

File `src/main/resources/users.ldif`:

```ldif
dn: ou=people,dc=springframework,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=student,ou=people,dc=springframework,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lab Student
sn: Student
uid: student
userPassword: lab-password-123

dn: uid=reader,ou=people,dc=springframework,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lab Reader
sn: Reader
uid: reader
userPassword: reader-password-123
```

Đây là fixture plaintext password **chỉ để khởi động in-memory server cục bộ**. Không đưa những credentials này vào một directory dùng chung hay production. Trong lab, embedded server quản lý root mặc định; không tự thêm entry root trùng nhau nếu implementation đã tạo root.

### 6.3. Cấu hình LDAP và form/Basic login

File `src/main/java/lab/security/LdapLabSecurity.java`:

```java
package lab.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.EmbeddedLdapServerContextSourceFactoryBean;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("ldap-lab")
public class LdapLabSecurity {

    @Bean
    EmbeddedLdapServerContextSourceFactoryBean embeddedLdap() {
        EmbeddedLdapServerContextSourceFactoryBean factory =
            EmbeddedLdapServerContextSourceFactoryBean
                .fromEmbeddedLdapServer();
        factory.setPort(0);
        factory.setRoot("dc=springframework,dc=org");
        factory.setLdif("classpath:users.ldif");
        return factory;
    }

    @Bean
    AuthenticationManager ldapManager(
            DefaultSpringSecurityContextSource source) {
        LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(source);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain ldapChain(
            HttpSecurity http,
            AuthenticationManager ldapManager) throws Exception {
        http
            .authenticationManager(ldapManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích:**

1. `@Profile("ldap-lab")` giúp beans chỉ tồn tại khi chọn đúng nhánh.
2. `EmbeddedLdapServerContextSourceFactoryBean` khởi tạo LDAP server từ LDIF; `setPort(0)` chọn cổng động, tránh collision giữa tests.
3. `setRoot`/`setLdif` là các methods xác nhận có trong Javadoc Spring Security 6.5.
4. `LdapBindAuthenticationManagerFactory` tạo AuthenticationManager xác minh username/password bằng **LDAP bind**, không dùng password hash local.
5. `userDnPatterns("uid={0},ou=people")` nối với root của ContextSource, tạo DN ví dụ đúng.
6. `http.authenticationManager(ldapManager)` đảm bảo các HTTP authentication filters trong chain này dùng đúng LDAP manager, không vô tình dùng provider khác.
7. `/` public; `/whoami` yêu cầu xác thực. `formLogin` cho browser, `httpBasic` cho curl/tests.
8. **Không** tắt CSRF ở form login hoặc tạo endpoint `/admin` permitAll.

Đây là mã **tích hợp vào project Spring Boot**; không biên dịch một mình bằng `javac`. Tùy bản patch của Spring Security và bean wiring, có thể dùng interface `BaseLdapPathContextSource` thay cho `DefaultSpringSecurityContextSource` trong constructor-injection. Kiểm Javadoc của bản dependency thực nếu IDE báo type/method không khớp.

### 6.4. Chạy LDAP lab

Dùng Gradle Wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=ldap-lab'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ldap-lab"
```

Không bật đồng thời `oidc-lab` trên cùng process. Nếu LDAP startup không đọc LDIF, kiểm classpath resource `src/main/resources/users.ldif`, DN/root/format dòng trống và dependency `unboundid-ldapsdk`.

### 6.5. Thử bằng curl

```bash
# Public
curl -i http://localhost:8080/

# LDAP bind đúng; chỉ dùng local lab
curl -i -H 'Accept: application/json' \
  -u student:lab-password-123 http://localhost:8080/whoami

# Password sai
curl -i -H 'Accept: application/json' \
  -u student:wrong http://localhost:8080/whoami

# User không tồn tại
curl -i -H 'Accept: application/json' \
  -u ghost:whatever http://localhost:8080/whoami
```

Dự kiến: public 200; đúng credential 200 với JSON principal; sai password và unknown username không được authenticated, thường HTTP 401 + Basic challenge. Do cấu hình có cả form + Basic, **browser redirect 302 vs Basic challenge 401 tùy request negotiation**; test Basic với Accept JSON như trên.

Không dùng password thật trên command line: nhiều hệ điều hành lưu lịch sử hoặc command process list. Chỉ thực hiện lệnh trên với tài khoản giả và trong môi trường test cô lập.

### 6.6. LDAP user search thay vì DN pattern

Nếu user nằm nhiều OU, dùng user search:

```java
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
```

Trong LDAP thật cần xác minh quyền search, schema và cơ chế escape input. **Không** viết raw filter `"(uid=" + userInput + ")"` dễ dẫn tới LDAP injection. Nơi directory chứa AD/LDAP referrals, nested groups hoặc account restrictions, cần test theo đặc thù directory thực và policy.

### 6.7. Nhóm/role mapping

Bind thành công **không** đồng nghĩa người dùng có `ROLE_ADMIN`. LDAP group membership có thể nằm trong `member`, `uniqueMember`, `memberOf` hoặc truy vấn nested groups. Mapping authorities cần xác định rõ:

```text
LDAP group: cn=readers,ou=groups,dc=example,dc=org
        |
        | trusted mapper (group lookup / cache policy)
        v
GrantedAuthority("ROLE_READER")
        |
        v
AuthorizationManager.hasRole("READER")
```

Trước khi bổ sung mapping, endpoint `/whoami` chỉ yêu cầu `authenticated()`. Nếu dùng `hasRole("ADMIN")` nhưng chưa map authorities, HTTP 403 là dấu hiệu **đã xác thực nhưng thiếu quyền**, không phải bind sai. Không sửa bằng cách gán `ROLE_ADMIN` cho mọi principal.

### 6.8. LDAP over TLS ở production

Với external LDAP/AD, kết nối app→directory phải có LDAPS/StartTLS với CA/hostname verification và timeouts. Nếu cần manager DN để search user, account đó chỉ có quyền đọc tối thiểu, secret từ vault. Browser→Spring cũng phải HTTPS; không có tác dụng bảo vệ password nếu backend LDAPS mà frontend form truyền qua HTTP công khai.

## 7. Kiểm thử tự động LDAP qua filter thật

File `src/test/java/lab/security/LdapAuthenticationTests.java`:

```java
package lab.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@ActiveProfiles("ldap-lab")
@AutoConfigureMockMvc(addFilters = true)
class LdapAuthenticationTests {

    @Autowired MockMvc mvc;

    @Test
    void correctPasswordUsesRealBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("student", "lab-password-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("student"));
    }

    @Test
    void wrongPasswordFailsBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("student", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserFailsBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test --tests lab.security.LdapAuthenticationTests
```

**Điều được chứng minh nếu các tests pass:** HTTP Basic filter nhận credential, AuthenticationManager chuyển sang LDAP bind và embedded server từ chối/nhận theo fixture. **Điều chưa được chứng minh:** LDAPS certificate, AD lockout/expired account, network failover, group mapping của tổ chức hoặc production identity proofing.

### 7.1. Mock principal không tương đương bind

```java
// Snippet trong MockMvc test với static import user().
mvc.perform(get("/whoami")
        .with(user("ghost").roles("USER")))
    .andExpect(status().isOk());
```

Dòng này có thể pass với principal `ghost` dù directory **không có user ghost**. `user()` là `RequestPostProcessor` cài sẵn Authentication giả cho test authorization. Không dùng nó để kết luận “LDAP password login chạy đúng”. Cần test credential thật như `httpBasic` hoặc `formLogin` và không mock verifier luôn thành công.

### 7.2. Ca LDAP âm tính nên mở rộng

| Input/sự kiện | Kỳ vọng |
|---|---|
| Password sai/empty | Không authenticated |
| User không tồn tại | Không authenticated, phản hồi trung tính |
| Password đúng nhưng user disabled theo AD policy | Login bị từ chối (cần directory test mô phỏng state thật) |
| User thuộc group thường, gọi admin route | 403 theo role mapping |
| Directory không có kết nối | Fail closed, không grant session mới |
| DN pattern không khớp | Không bind hoặc search đúng |
| Username có ký tự LDAP đặc biệt | Được escape/validate, không tiêm filter |
| Manager DN sai/quá quyền | Không silently fallback sang admin |
| LDAP kết nối plaintext trên network thật | Bị policy chặn, không gửi secret |
| LDAP search trả nhiều users | Không lấy bừa identity đầu tiên |
| Password đổi trong directory | Credential cũ không login mới, session cũ theo policy |
| Authentication thành công rồi logout | Session invalidation theo ứng dụng |
| Hai request khác session | Không tái sử dụng Authentication của test trước |
| Directory bị timeout | Có log lỗi vận hành đã redact, không giả “password sai” |

## 8. Nhánh B – Keycloak làm OpenID Provider cục bộ

### 8.1. Keycloak ở đâu trong kiến trúc?

Keycloak là IdP/Authorization Server. App Spring Boot là OAuth2 Client sử dụng `oauth2Login()` và browser redirect. Trong OIDC, **người dùng nhập password ở Keycloak**, không gửi username/password Keycloak vào controller Spring. Spring kiểm kết quả token/trusted metadata, tạo `OidcUser` và session.

Bạn có thể dùng bất kỳ OpenID Provider tuân chuẩn nào, nhưng Keycloak có Docker image và Admin Console phù hợp bài lab. Dùng realm riêng, client riêng, users riêng và không tái sử dụng credentials của hệ thống công ty.

### 8.2. Chạy Keycloak bằng Docker

Ví dụ từ Keycloak Docker Getting Started: image `quay.io/keycloak/keycloak:26.8.1` được công bố trong hướng dẫn ở thời điểm tra cứu. Để tránh chiếm cổng của Spring app `8080`, map Keycloak vào `localhost:8180`:

```bash
docker run --rm --name keycloak-lab \
  -p 127.0.0.1:8180:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=lab-admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-admin-only \
  quay.io/keycloak/keycloak:26.8.1 \
  start-dev --hostname=http://localhost:8180
```

**Đặc điểm:** `start-dev` cho phép HTTP và có security defaults chỉ phù hợp dev; chỉ publish loopback, không triển khai production. `--hostname` đặt public URL giúp `issuer` và endpoints do Keycloak công bố khớp URL browser/backend. Nếu bản Docker/Podman hoặc version khác xử lý hostname khác, đọc docs của chính Keycloak version đó và verify discovery thực tế. Không dùng `:latest` cho bài cần reproducibility.

Mở `http://localhost:8180`, chọn Admin Console; login `lab-admin` với test password. Container foreground: có thể dừng bằng Ctrl+C hoặc `docker stop keycloak-lab`; `--rm` xóa container sau khi dừng, nên realm test không được lưu bền trừ khi cấu hình volume/export.

### 8.3. Tạo realm và user

Trong Admin Console:

1. Tạo realm tên `spring-lab`, không dùng realm `master` cho ứng dụng.
2. Trong Users, tạo `student-oidc` và gán email test `student@lab.example`.
3. Đặt password riêng trong Credentials; chọn **Temporary OFF** nếu muốn login một bước trong lab.
4. Đảm bảo user được **Enabled** và không còn required action đang chờ (trừ khi đó là case muốn test).
5. Không dùng Keycloak admin làm tài khoản người dùng Spring.
6. Ghi cấu hình test user vào local tài liệu không kèm secrets.

Issuer:

```text
http://localhost:8180/realms/spring-lab
```

Metadata:

```bash
curl -i http://localhost:8180/realms/spring-lab/.well-known/openid-configuration
```

Kiểm `issuer` trong JSON khớp **nguyên văn** với URL trên; đọc `authorization_endpoint`, `token_endpoint` và `jwks_uri` từ discovery. Nếu trả 404, realm chưa tạo, hostname/port sai hoặc Keycloak chưa sẵn sàng.

### 8.4. Đăng ký OIDC client

Trong realm `spring-lab` → Clients → Create client, cấu hình:

| Thuộc tính | Giá trị bài lab | Mục đích |
|---|---|---|
| Client type | OpenID Connect | Có OIDC ID Token |
| Client ID | `spring-lab-client` | Khớp Spring registration |
| Client authentication | **ON** | Confidential web client có secret |
| Standard flow | **ON** | Authorization Code |
| Direct access grants | **OFF** nếu không cần | Không cho password grant |
| Valid redirect URIs | `http://localhost:8080/login/oauth2/code/keycloak` | Khớp Spring callback |
| Web origins | `http://localhost:8080` nếu cần | Không mở wildcard |
| Client secret | Copy từ Credentials | Lưu qua environment/secret store |

**Quan trọng:** redirect URI phải là exact callback, không dùng wildcard như `http://localhost:8080/*` chỉ để bypass lỗi. Khi chọn Client authentication ON, mặc định confidential client thường dùng secret tại token endpoint; phương thức ở Spring phải khớp client policy của Keycloak.

### 8.5. Giữ secret ngoài source code

Tạo biến môi trường `OIDC_CLIENT_SECRET` từ local secret manager/IDE configuration. Ví dụ lab trên Bash:

```bash
export OIDC_CLIENT_SECRET='YOUR_LOCAL_TEST_CLIENT_SECRET'
```

PowerShell:

```powershell
$env:OIDC_CLIENT_SECRET = "YOUR_LOCAL_TEST_CLIENT_SECRET"
```

Đây chỉ là placeholder cho **secret thử nghiệm** do Keycloak cấp. Không commit giá trị thật, không chụp màn hình client credentials, không xuất token/secret vào CI logs. Nếu lộ thì rotate.

### 8.6. Spring Boot OIDC client properties

File `src/main/resources/application-oidc-lab.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            provider: keycloak
            client-id: spring-lab-client
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          keycloak:
            issuer-uri: http://localhost:8180/realms/spring-lab
```

**Giải thích:**

- `registration.keycloak` là registration ID, nên URL bắt đầu login mặc định `/oauth2/authorization/keycloak`.
- `client-id` đúng với client đăng ký trong Keycloak.
- `client-secret` lấy từ environment, không cứng hóa trong YAML.
- `openid` yêu cầu OpenID Connect; `profile,email` chỉ là scopes tùy chọn.
- `redirect-uri` dùng placeholders được Spring OAuth2 Client hỗ trợ; khi Spring ở `localhost:8080`, callback thành `http://localhost:8080/login/oauth2/code/keycloak`.
- `issuer-uri` kích hoạt discovery, làm căn cứ xác minh issuer và endpoints/JWKs; **không** tùy tiện trộn `http://127.0.0.1:8180` với `http://localhost:8180` nếu metadata công bố khác.
- Cấu hình này **dành cho server-side confidential web client**, không phải SPA public client.

### 8.7. SecurityFilterChain cho OIDC profile

File `src/main/java/lab/security/OidcLabSecurity.java`:

```java
package lab.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("oidc-lab")
public class OidcLabSecurity {

    @Bean
    SecurityFilterChain oidcChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` kích hoạt client filter/protocol. Các request callback mặc định được filter Spring Security xử lý; **không tự viết `@GetMapping("/login/oauth2/code/keycloak")`**. Cấu hình giữ CSRF cho ứng dụng dựa vào browser session. Spring Boot cung cấp `ClientRegistrationRepository` từ properties nếu OAuth2 Client starter có mặt.

### 8.8. Chạy và kiểm bằng browser

Sau khi Keycloak chạy, realm/client và client secret sẵn sàng:

```bash
./gradlew bootRun --args='--spring.profiles.active=oidc-lab'
```

Các bước:

1. Browser mở `http://localhost:8080/` và nhận trang public.
2. Mở `http://localhost:8080/whoami` khi chưa login.
3. Spring redirect tới trang đăng nhập hoặc trực tiếp OAuth2 authorization; chọn liên kết “Keycloak”. Có thể chủ động mở `http://localhost:8080/oauth2/authorization/keycloak`.
4. Browser chuyển sang Keycloak `spring-lab`; đăng nhập `student-oidc` tại IdP.
5. Keycloak trả authorization `code` và `state` về callback của app.
6. Spring so `state`, trao đổi `code` ở token endpoint với client authentication và xác minh ID Token.
7. Spring lưu authenticated principal vào session; mở lại `/whoami` thấy response 200 và `name` của OIDC principal.

**Không đảm bảo `getName()` chính là `student-oidc`.** Nhiều cấu hình OIDC dùng subject `sub` ổn định làm principal name. Điều cần test là user đã được xác minh theo `(iss, sub)` và quyền được map từ nguồn tin cậy, không phải so tên hiển thị.

### 8.9. Vấn đề host/container

`localhost` bên trong Docker container **chỉ tới container đó**. Nếu app chạy trong container khác, `localhost:8180` không liên hệ được Keycloak, trong khi browser vẫn cần truy cập endpoint mà Keycloak công bố. Giải pháp là thiết kế **hostname/issuer canonical** có thể được cả browser và app JVM phân giải, cấu hình network/DNS/ingress và TLS tương ứng. Không tắt issuer verification để chữa lỗi DNS/hostname.

## 9. OIDC protocol: những kiểm tra không được bỏ qua

### 9.1. Authorization code và client authentication

Authorization Code được trả qua redirect tới đúng `redirect_uri`. Confidential client gửi code tới token endpoint qua **back-channel** và chứng minh client bằng secret hoặc phương thức cấu hình. Code phải short-lived, single-use và liên kết client + redirect/PKCE theo chính sách.

**Đừng** lấy code từ callback rồi gửi đến một IdP do browser tự chọn hoặc đưa client secret cho JavaScript frontend.

### 9.2. state và nonce

- `state` được OAuth2 client dùng liên kết authorization request và callback, giảm login CSRF/code injection.
- `nonce` liên kết ID Token với flow OIDC, cần được kiểm theo protocol/implementation tương ứng.
- Test hai browser sessions A/B không được tráo state/code để login vào session còn lại.
- Test đã dùng code một lần không thể bị replay để lấy session mới.
- Đừng dùng `state=123` cố định trong ứng dụng production hoặc tắt kiểm state để qua test.

### 9.3. ID Token validation

Một ID Token đáng tin cần được xử lý/kiểm tra:

| Field/điều kiện | Mục đích | Negative test |
|---|---|---|
| Signature + JWK/JWKS | Đúng khóa và thuật toán issuer tin cậy | Thay chữ ký/khóa của realm khác |
| `iss` | IdP issuer đã cấu hình | Token của realm khác |
| `aud` | Client ID phù hợp | Token cấp cho client khác |
| `azp` khi cần | Authorized party theo quy tắc OIDC | Multiple audiences sai azp |
| `exp`/`iat` | Thời hạn và time context | Token hết hạn/future vượt policy |
| `nonce` | Liên kết flow browser | Nonce sai hoặc replay |
| `sub` | Principal ID ổn định trong issuer | Missing/không hợp lệ |
| Token type/use | Không nhận access token làm ID Token | Chuyển nhầm loại token |
| `email_verified` | Email thuộc IdP có được xác minh? | Không link local account theo email chưa verified |

Spring Security và OIDC client library triển khai phần cốt lõi theo giao thức, nhưng **test cần dùng client config và issuer đúng**. Một bài unit test tự tạo `OidcUser` không chứng minh ID Token đã được verify.

### 9.4. PKCE, confidential client và redirect

PKCE bảo vệ Authorization Code trước rủi ro code interception. Với public clients, dùng PKCE là phần quan trọng của secure OAuth; với confidential server-side client, lựa chọn/bật PKCE phụ thuộc ClientRegistration/framework/IdP policy, **không tuyên bố “luôn bật” khi chưa kiểm**.

Redirect URI phải **chính xác** và không mở wildcard vô hạn. App không tự phản chiếu `next=https://evil.example` sau login. Với reverse proxy, base URL và forwarded headers phải tin cậy, tránh chuyển đến host lạ hoặc mất session cookie.

## 10. Nguồn sự thật của danh tính và quyền

### 10.1. LDAP identity

Directory namespace + stable entry ID/DN (và các thuộc tính định danh được quản trị) xác định account. Trong AD, `objectGUID` có thể hữu ích hơn `displayName` hoặc một `sAMAccountName` có thể đổi theo chính sách. Nếu link LDAP user với domain account, phải tính rename/move giữa OUs và account reuse; không phụ thuộc mỗi display name.

### 10.2. OIDC identity

OIDC cho phép xác định user bằng **cặp `(iss, sub)`**. Email/`preferred_username` có thể đổi, trùng hoặc chưa verified. Ví dụ ID Token claims mô phỏng:

```json
{
  "iss": "http://localhost:8180/realms/spring-lab",
  "sub": "subject-123",
  "aud": "spring-lab-client",
  "preferred_username": "student-oidc",
  "email": "student@lab.example",
  "email_verified": false
}
```

Đây là **JSON giải thích**, không phải token thật do Keycloak phát hoặc chữ ký đã kiểm. App không được auto-link một local account đã tồn tại chỉ bằng trường `email` khi `email_verified=false`. Ngoài verified email, một số hệ thống còn yêu cầu reauthentication của **local account** trước khi link IdP lần đầu.

### 10.3. Authorization độc lập

Một người dùng LDAP bind được hoặc OIDC login được vẫn **có thể không đủ quyền** xem `/admin` hoặc dữ liệu tenant khác. Mỗi nhánh cần có trusted authority mapping:

- LDAP: group search/membership, nested group, policy allowlist, prefix `ROLE_`.
- OIDC: token claims/realm roles/client roles được verify, hoặc local role repository.
- Domain: object ownership, tenant boundary, disabled account, permission freshness và revocation.
- Tests: role thấp → 403; role đủ nhưng sai owner → 403/404 theo policy.

**Không tự tin mọi Keycloak realm role sẽ xuất hiện dưới dạng `ROLE_ADMIN` trong Spring Security.** Cần mapper/test của chính ứng dụng. Cũng không gán `ROLE_ADMIN` cho mọi LDAP user vì họ thuộc một nhóm tùy ý.

## 11. Kiểm thử: mock fixture hay verifier thật?

| Bài test | Điều test kiểm được | Điều chưa được chứng minh |
|---|---|---|
| `@WithMockUser(username="student")` | Authorization/controller với Authentication giả | LDAP user tồn tại và password hợp lệ |
| `user("ghost")` trong MockMvc | Endpoint đối xử với principal cho trước | LDAP bind đã xảy ra |
| `@WithUserDetails` | UserDetailsService lookup và mapping theo bean dùng | PasswordEncoder/LDAP bind đã kiểm |
| `oidcLogin()` trong MockMvc | Controller xử lý `OidcUser`/claims đã cấp sẵn | Keycloak redirect, code, signature, issuer, nonce |
| `httpBasic("student","password")` + real LDAP manager | HTTP filter → LDAP bind thực trong lab | AD production/TLS/failover |
| Browser OIDC login với test Keycloak | Redirect, client auth, code exchange, verify ID Token, session | Tất cả multi-node/production IdP failure cases |
| Unit test custom mapper | Role/tenant policy cho claim/LDAP attributes giả | Claim/token có nguồn gốc tin cậy |
| E2E + negative crypto test | Stronger evidence cho protocol/verification | Không thay threat model và operations monitoring |

**Quy tắc:** nếu test vẫn pass khi LDAP/Keycloak đều tắt mà không có fake server được định nghĩa, test đó có thể chỉ thử principal giả. Điều này không sai nếu mục tiêu là authorization, nhưng **không** gọi đó là kiểm thử đăng nhập thực.

### 11.1. MockMvc oidcLogin() đúng vai trò

Snippet Spring Security Test:

```java
mvc.perform(get("/whoami").with(oidcLogin()))
    .andExpect(status().isOk());
```

Nó không gọi authorization endpoint/ID Token verifier của Keycloak. Một claim mock có thể được đưa vào:

```java
mvc.perform(get("/whoami")
        .with(oidcLogin().idToken(token ->
            token.claim("sub", "student-test-subject"))))
    .andExpect(status().isOk());
```

Cần static imports `oidcLogin`, `get`, `status` và một Spring MVC test context phù hợp. Không dùng đoạn đó để tuyên bố ứng dụng kiểm chữ ký JWT hay `state`.

### 11.2. LDAP MockMvc tests và browser OIDC E2E là hai mức độ khác nhau

Ở nhánh LDAP, `httpBasic` đi qua filter và thực hiện bind ngay trong JVM. Ở nhánh OIDC, một callback thật cần browser + IdP + client secret + token endpoint + JWKs. Có thể dùng browser automation/Testcontainers/WireMock với issuer/JWKS/signing keys thử nghiệm, nhưng một `oidcLogin()` mock **không thay thế** E2E.

Nếu dùng fake OIDC provider, phải chứng minh server phát **mã code có kiểm**, token thật có chữ ký và Spring decoder thực sự verify; không mock `OidcIdTokenDecoderFactory` trả success với mọi chuỗi rồi gọi là test crypto.

## 12. Ma trận kiểm thử tích hợp

### 12.1. LDAP

| Test | Setup | Expected |
|---|---|---|
| Bind đúng | User student, password đúng | 200 /whoami, name tương ứng |
| Sai password | Cùng user nhưng password sai | 401/nhánh form failure |
| User không tồn tại | DN ghost | 401, không tạo Authentication |
| Không có credential | New client/browser | 302 login hoặc Basic 401 theo Accept |
| Search base khác | User nằm OU khác | Không bind nếu pattern/search sai |
| LDAP filter injection | Username chứa wildcard/metachar | Escape hoặc reject theo policy |
| LDAP server down | Service unreachable | Không cấp session mới |
| Manager DN chỉ read-only | Search-before-bind | Không đọc quá cần thiết |
| LDAP group missing | Bind đúng nhưng thiếu group | 403 ở protected role |
| Account disabled | Directory test hỗ trợ flag | Bị chặn khi policy yêu cầu |
| Password rotated | Password cũ | Không login mới |
| Session logout | Browser đã login | Session cũ không truy cập resource |
| TLS invalid CA | External LDAPS test | Reject connection; không trust-all |
| Multi-node directory | Replica failover | Không fail open |

### 12.2. OIDC

| Test | Setup | Expected |
|---|---|---|
| Login hợp lệ | Keycloak realm/client/user đúng | Session app và principal |
| Redirect sai | Keycloak Valid redirect URI khác app | IdP từ chối |
| Client secret sai | Env secret không khớp Keycloak | Token exchange fail |
| issuer sai | `127.0.0.1` vs `localhost` hoặc realm khác | Không tin token/metadata |
| state sai | Callback thay state | Không tạo session |
| code replay | Dùng lại code | Reject |
| nonce mismatch | ID Token nonce không khớp flow | Reject |
| ID Token sai chữ ký | Test signed fixture key khác | Reject |
| ID Token sai aud | Token cấp client khác | Reject |
| ID Token hết hạn | Exp đã qua | Reject |
| User disabled tại IdP | Keycloak user disabled | Không login mới |
| Email chưa verified | `email_verified=false` | Không auto-link local account |
| Realm role không map | User thường login thành công | 403 ở admin route |
| Session logout | App logout | Local session invalid |
| IdP logout riêng | IdP SSO còn sống | Không giả định local logout = IdP logout |
| JWKS rotation | IdP rotate signing key | Client tin JWK mới theo policy |
| IdP outage | Không discovery/token response | Fail closed |
| Proxy hostname sai | Redirect base URL mismatch | Sửa canonical origin, không tắt check |

## 13. Java 17 độc lập: ranh giới bằng chứng

Chương trình này **chạy bằng JDK 17+ và không cần thư viện**, mô hình hóa hai **kết quả sau khi verifier đã hoạt động**. Nó KHÔNG thực hiện LDAP bind, ký/verify JWT hay gọi IdP. Các cờ `bindVerified`, `signatureVerified` và `nonceVerified` là **dữ liệu giả lập do test cung cấp**, không bao giờ được nhận từ JSON/header của client trong ứng dụng thật.

Lưu file `IdentityTrustBoundaryDemo.java`:

```java
import java.time.Instant;

public class IdentityTrustBoundaryDemo {

    record LdapEvidence(
        String directory, String dn,
        boolean bindVerified) {}

    record OidcEvidence(
        String issuer, String subject, String audience,
        boolean signatureVerified, boolean nonceVerified,
        Instant expiresAt) {}

    static boolean acceptLdap(LdapEvidence proof) {
        return proof.bindVerified()
            && proof.directory().equals("lab-directory")
            && proof.dn().equals(
                "uid=student,ou=people,dc=springframework,dc=org");
    }

    static boolean acceptOidc(OidcEvidence proof, Instant now) {
        return proof.signatureVerified()
            && proof.nonceVerified()
            && proof.issuer().equals(
                "http://localhost:8180/realms/spring-lab")
            && proof.audience().equals("spring-lab-client")
            && !proof.subject().isBlank()
            && now.isBefore(proof.expiresAt());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");

        LdapEvidence verifiedBind = new LdapEvidence(
            "lab-directory",
            "uid=student,ou=people,dc=springframework,dc=org", true);
        LdapEvidence falseBind = new LdapEvidence(
            "lab-directory",
            "uid=student,ou=people,dc=springframework,dc=org", false);

        OidcEvidence good = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", true, true,
            now.plusSeconds(120));
        OidcEvidence wrongIssuer = new OidcEvidence(
            "http://localhost:8180/realms/other",
            "subject-123", "spring-lab-client", true, true,
            now.plusSeconds(120));
        OidcEvidence wrongSignature = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", false, true,
            now.plusSeconds(120));
        OidcEvidence expired = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", true, true, now);

        System.out.println("LDAP verified bind: " +
            acceptLdap(verifiedBind));
        System.out.println("LDAP invalid bind: " +
            acceptLdap(falseBind));
        System.out.println("OIDC valid proof: " +
            acceptOidc(good, now));
        System.out.println("OIDC wrong issuer: " +
            acceptOidc(wrongIssuer, now));
        System.out.println("OIDC bad signature: " +
            acceptOidc(wrongSignature, now));
        System.out.println("OIDC expired: " +
            acceptOidc(expired, now));
        System.out.println("Different namespaces: " +
            !verifiedBind.dn().equals(good.subject()));
    }
}
```

Biên dịch và chạy:

```bash
javac IdentityTrustBoundaryDemo.java
java IdentityTrustBoundaryDemo
```

Stdout **chính xác**:

```text
LDAP verified bind: true
LDAP invalid bind: false
OIDC valid proof: true
OIDC wrong issuer: false
OIDC bad signature: false
OIDC expired: false
Different namespaces: true
```

**Ý nghĩa:** cùng một tài khoản hiển thị tên student không là bằng chứng login nếu LDAP bind thất bại; OIDC cần issuer, audience, chữ ký, nonce và expiry. Khi thiếu một điều kiện phải từ chối. Demo cũng làm rõ LDAP DN thuộc directory namespace và OIDC subject thuộc issuer namespace, không được hợp nhất account dựa vào một username string.

**Giới hạn:** mô hình chỉ kiểm booleans từ trusted verifier giả định; không có `state`, JWT JWK algorithm, `azp`, token endpoint/client authentication, clock-skew policy, issuer discovery, signature verification hoặc browser session. Không copy `acceptOidc` vào production thay cho Spring Security OIDC verifier. Các tests thật phải đi qua LDAP/OIDC integration bên trên.

## 14. Debug theo triệu chứng

### 14.1. LDAP bind thất bại dù password tưởng đúng

1. Kiểm có bật `ldap-lab` không; `LdapLabSecurity` có được load?
2. LDIF có thật trong classpath và khởi tạo thành công? Có log init error?
3. DN của user đúng `uid=student,ou=people,dc=springframework,dc=org`?
4. User-DN pattern có thêm root đúng, không bị lặp suffix?
5. Có vô tình tạo `AuthenticationManager` khác hoặc test mock provider?
6. Browser có đang gửi Basic credentials lưu từ session cũ không? Dùng fresh curl/browser.
7. LDAP là external thì kiểm DNS/LDAPS cert/connect/read timeout trước khi kết luận password sai.
8. Không thêm `permitAll("/whoami")` để che lỗi authentication.

### 14.2. LDAP user đúng nhưng không có quyền

Kiểm `DefaultLdapAuthoritiesPopulator`/group search config khi đã thêm mapping, schema thực của `member`/`memberOf`, nested groups, role prefix `ROLE_`, quyền service bind và cache. Đừng mặc định `ROLE_ADMIN` tồn tại chỉ vì account trong directory có group “admin” với naming khác.

### 14.3. OIDC "invalid_redirect_uri"

Callback Spring:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

Client Keycloak phải đăng ký đúng URI, bao gồm scheme, host, port và path. `localhost` khác `127.0.0.1` trong cấu hình exact URI. Không dùng wildcard để che sai cấu hình.

### 14.4. OIDC "invalid issuer"

Mở metadata, kiểm `issuer`; so nguyên chuỗi với `provider.keycloak.issuer-uri`. Nếu có reverse proxy/port map, cấu hình public hostname đúng. Không chuyển từ issuer check sang “chỉ kiểm chữ ký JWT” vì token của realm khác có thể bị tin nhầm.

### 14.5. OIDC "invalid_client"

Kiểm registration/client ID trong đúng realm, Client authentication ON, secret lấy từ client đúng, `client_secret_basic`, token endpoint metadata và secret rotation. Không đưa secret vào frontend hoặc logs.

### 14.6. OIDC browser login xong vẫn anonymous

Kiểm state callback, cookie domain/path/SameSite/Secure, HTTP vs HTTPS, session persistence/repository, reverse proxy forwarding, session fixation strategy. Khi Spring và IdP cùng host nhưng khác port, các cookies có domain/path và SameSite khác nhau theo bối cảnh; không tự tắt protections.

### 14.7. API trả 403 sau login

Xác thực thành công không tự cấp authority business. Kiểm method security, roles/scopes/tenant/ownership; đừng tắt JWT/ID Token signature validation để “fix 403”. Nếu app còn có Bearer resource server, tách API filter chain khỏi browser OAuth2 login.

## 15. Khi chuyển từ lab sang production

**LDAP:** sử dụng LDAPS/StartTLS end-to-end, trusted CA, service bind read-only, DN/filter escaping, rate limit, account lockout, directory replicas/referrals, group mapping, audit và đúng cơ chế account disable. Xem xét external LDAP server và cấu hình session/caches đúng nhu cầu thay vì embedded in-memory.

**OIDC:** dùng IdP production được quản trị, HTTPS, exact redirect URIs, trusted issuer/JWKS, client secret vault/rotation, state/nonce, authorization code single-use/PKCE policy, session fixation/CSRF, app logout vs IdP logout, signed claims, account linking qua `iss+sub`, role mapping và assurance/MFA requirements. Không tin email chưa được xác minh hoặc browser-supplied role.

**Cả hai:** auth và authorization là hai lớp khác nhau. Không xem 200 từ endpoint public là đăng nhập thành công; không dùng `@WithMockUser`/`oidcLogin()` làm chứng minh password/crypto thực. Test negative cases, lưu report có redaction, đo observability, bảo vệ secrets và theo dõi CVE trên Boot/Security/IdP/LDAP dependencies.

## 16. Checklist trước khi nộp bài

### 16.1. Nhánh LDAP

- [ ] Project chạy `ldap-lab`, nhánh OIDC không tự kích hoạt.
- [ ] LDIF user student/reader được nạp trong UnboundID server.
- [ ] `student` password đúng bind thành công qua HTTP Basic/form.
- [ ] Password sai và user ghost đều không tạo Authentication.
- [ ] Có test 401/302 và 403 với rule quyền khi bổ sung group.
- [ ] Không nhầm `user()` MockMvc với LDAP bind thực.
- [ ] Có phân biệt DN, search/filter và roles.
- [ ] Không gửi password thật hoặc dùng plaintext directory ngoài lab.
- [ ] Có kiểm cleanup session/logout và log redaction.

### 16.2. Nhánh OIDC

- [ ] Keycloak chỉ bind localhost, realm `spring-lab` riêng.
- [ ] User test và confidential client `spring-lab-client` tồn tại.
- [ ] Issuer metadata trả exact `http://localhost:8180/realms/spring-lab`.
- [ ] Keycloak redirect URI exact `http://localhost:8080/login/oauth2/code/keycloak`.
- [ ] Client secret được cung cấp từ env, không commit.
- [ ] Browser thực đi từ Spring → Keycloak → Spring callback.
- [ ] Spring tạo session sau code exchange và ID Token verification.
- [ ] `/whoami` có principal OIDC, không tự coi email là account ID.
- [ ] Có test state/nonce, wrong issuer, wrong secret, missing roles.
- [ ] Đã kiểm việc login IdP và logout local session là hai vòng đời riêng.
- [ ] Có cleanup container, browser session và secrets.

## 17. Câu hỏi tự đánh giá

**1. LDAP bind kiểm password ở đâu?**  
Directory server. Spring app dùng LDAP provider chuyển credential và nhận kết quả bind, không mặc định đọc password hash từ directory.

**2. Tại sao không cho rằng mọi LDAP user đều là admin?**  
Bind chỉ xác minh danh tính. Nhóm/roles/ownership cần mapping và authorization độc lập.

**3. OIDC có cần Spring app biết password Keycloak không?**  
Không. User nhập password tại IdP; client ứng dụng nhận code/ID Token qua flow được bảo vệ.

**4. OIDC callback mặc định của registration id keycloak là gì?**  
`/login/oauth2/code/keycloak`. Keycloak cần đăng ký full URL exact bao gồm host/port.

**5. ID Token và Access Token khác gì?**  
ID Token chứng minh login cho OIDC client, Access Token dành cho resource API theo audience/scope.

**6. Vì sao principal `getName()` sau OIDC có thể không là username?**  
Nó có thể là subject claim `sub`. Stable mapping dùng cặp `iss,sub`; email/username là thuộc tính có thể đổi.

**7. `oidcLogin()` trong MockMvc có chứng minh chữ ký token thật?**  
Không, nó là mock principal/claims. Cần browser/IdP integration với token có chữ ký và verifier thật.

**8. Tại sao LDAP embedded thành công không chứng minh LDAPS production an toàn?**  
In-memory local không kiểm CA, network attacker, AD restrictions, failover hay multi-node.

**9. Nếu token sai issuer, có nên tắt kiểm issuer?**  
Không. Sửa canonical hostname, realm và discovery metadata cho đúng.

**10. Nếu login thành công nhưng admin route trả 403?**  
Đó thường là lỗi/thiếu quyền authorization hoặc role mapper, không phải bằng chứng password/IdP login thất bại.

**11. Đổi role trong Keycloak có buộc mọi session Spring cập nhật ngay không?**  
Không bảo đảm. Phải thiết kế session lifetime/revocation và permission freshness.

**12. Điều gì chứng minh lab đã tích hợp thật?**  
Có request đi qua LDAP bind hoặc OIDC redirect/code exchange/ID Token verification và có negative tests với credential/protocol sai, không chỉ authenticated principal giả.

## Tài liệu tham khảo

- [Spring Security 6.5 – LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind, UnboundID/LDIF, manager và directory configuration.
- [Spring Security 6.5 – Embedded LDAP Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/EmbeddedLdapServerContextSourceFactoryBean.html): `setPort`, `setLdif`, `setRoot`.
- [Spring Security 6.5 – OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): OAuth2 Client, Authorization Code và login flow.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): request/redirect endpoints và customization.
- [Spring Boot 3.5 – OAuth2 Client Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): registration/client secret/provider issuer.
- [Spring Security – Testing OAuth2/OIDC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()` fixture và limitations.
- [Keycloak – Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): local IdP container, realm, users và clients.
- [Keycloak – Running in a Container](https://www.keycloak.org/server/containers): `start-dev`, bootstrap admin, hostname và ports.
- [Keycloak – Realm import/export](https://www.keycloak.org/server/importExport): tái lập test fixtures.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `iss`/`sub`/`aud`/`nonce` và ID Token verification.
- [RFC 6749 – OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html): Authorization Code và redirect/client authentication.
- [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier/challenge.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): controls và error handling.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): redirect, state/PKCE, token type và security.
