# Quản lý mật khẩu, client secret và khóa bằng cấu hình bí mật bên ngoài mã nguồn

> **Ngữ cảnh:** Spring Security — fundamentals / Triển khai. Bài này hướng dẫn bảo vệ **password, OAuth2 client secret, API key, JWT signing key và encryption key** khi xây dựng và triển khai ứng dụng Java 17+, Spring Boot 3.x/Spring Security 6.x. Trọng tâm là tách bí mật khỏi source code, phân phối qua cấu hình hoặc secret manager, giới hạn người đọc, tránh lộ qua log/CI và **xoay vòng/thu hồi không gián đoạn**. Ví dụ chính dùng Spring Boot **3.5.0**, Java 17 và Maven.

## 1. Vấn đề: đưa bí mật vào Git biến lỗi nhỏ thành sự cố lâu dài

Ví dụ nguy hiểm:

~~~java
// SAI: mật khẩu và khóa được nhúng vào source.
String databasePassword = "HardcodedDatabasePassword";
String clientSecret = "HardcodedOAuthClientSecret";
byte[] signingKey = "HardcodedShortSigningKey".getBytes();
~~~

Hoặc cấu hình được commit cùng repository:

~~~properties
# SAI: lưu giá trị bí mật thật vào file version-controlled.
spring.datasource.password=real-database-password
spring.security.oauth2.client.registration.billing.client-secret=real-client-secret
app.jwt.signing-key=real-signing-key
~~~

Một developer, CI runner hoặc service thứ ba có quyền đọc code/artifact có thể thấy credential. Khi bí mật nằm trong Git, xóa ở commit mới **không tự xóa khỏi lịch sử, fork, clone, cache, log và build artifacts cũ**. Khi đó phải coi credential bị lộ và **rotate/revoke**, không chỉ sửa file.

**Nguyên tắc thiết kế:** source code chỉ mô tả *tên cấu hình, schema và cách dùng*. **Giá trị bí mật thật** đến từ một kênh triển khai được quản trị — environment injection có kiểm soát, file mount được cấp quyền, secrets manager hoặc workload identity. Không dùng Base64/obfuscation như một hình thức mã hóa bảo mật.

Bảo vệ bí mật còn bao gồm **lúc nó đang được truyền, nằm trong RAM, xuất hiện trong process/container và khi được luân chuyển**. “Không có trong Git” là điều kiện cần, chưa đủ.

### Tình huống thường gặp

- Dev chạy ứng dụng với tài khoản thử và phải giữ mật khẩu ngoài repo.
- CI/CD triển khai vào staging/production, mỗi môi trường có credential riêng.
- Spring Security OAuth2 Client dùng `client_credentials` gọi đối tác bằng `client_id` và `client_secret`.
- Resource Server kiểm tra JWT bằng **public key/JWKS**; phía issuer ký bằng **private key** hoặc HMAC secret.
- Ứng dụng cần khóa AES/GCM để mã hóa dữ liệu nhạy cảm, có yêu cầu rotate và phục hồi.
- Nhiều pod hoặc instance cùng đọc secret từ hệ thống quản lý bí mật mà không in secret vào log.

## 2. Phân loại chính xác: mật khẩu, password hash, client secret và khóa

| Loại dữ liệu | Mục đích | Cách xử lý khuyến nghị |
|---|---|---|
| **Mật khẩu người dùng (raw password)** | Người dùng chứng minh danh tính | Chỉ xử lý lúc login, truyền qua HTTPS, không log; lưu **password hash có salt với thuật toán thích hợp** trong user store, không lưu plaintext |
| **Password hash (verifier)** | Kiểm mật khẩu khi login, ví dụ `{bcrypt}$2b$...` | Thường lưu ở user database; với **bootstrap account** có thể cấp qua cấu hình secret; vẫn giới hạn truy cập và hỗ trợ rotate |
| **Mật khẩu DB / service account** | App kết nối dịch vụ khác | Ưu tiên workload identity/short-lived credentials; nếu cần mật khẩu tĩnh, quản lý trong secret manager |
| **OAuth2 client secret** | Xác thực *confidential client* với authorization server | Chỉ giữ ở backend/secure runtime, **không bao giờ nhúng vào SPA/mobile public client** |
| **API key** | Gọi API hoặc nhận diện client, tùy thiết kế | Cấp quyền hẹp, hạn sử dụng, rotate, không ghi vào source/URL/log |
| **JWT HMAC key (HS256/HS512)** | Chia sẻ secret để ký và xác minh JWT | Khóa ngẫu nhiên đủ entropy, phân phối tối thiểu; bất kỳ bên nào biết khóa cũng **có thể ký** token |
| **Asymmetric private key (RSA/EC)** | Ký JWT/chữ ký số | Chỉ issuer/signing service được sở hữu; dùng KMS/HSM khi phù hợp |
| **Asymmetric public key/JWKS** | Xác minh chữ ký | Về bản chất không cần bí mật; vẫn phải lấy từ nguồn tin cậy, xác minh issuer/audience/algorithm và quản lý thay đổi |
| **Encryption key (AES-GCM)** | Mã hóa/giải mã dữ liệu | Khóa không nằm trong database ciphertext cùng phạm vi truy cập; dùng KMS/envelope encryption, key version, nonce ngẫu nhiên/duy nhất |
| **TLS private key** | Chứng minh danh tính endpoint TLS | Quản lý ở ingress/server/KMS, giới hạn quyền đọc; certificate công khai không phải bí mật nhưng private key là bí mật |

**Không nhầm “hash” với “encryption”:** password hash là verifier một chiều, nên ứng dụng không cần giải mã password gốc. Encryption key cần dùng để khôi phục plaintext, nên lifecycle/backup và phân quyền khác password hash. **OAuth2 client secret** cũng không phải access token của end user; nó là credential của một ứng dụng.

**Không dùng mật khẩu dễ nhớ làm khóa HMAC/AES.** Những khóa này cần entropy từ CSPRNG và độ dài tương ứng thuật toán. Ví dụ, HMAC-SHA-256 nên dùng secret ngẫu nhiên **ít nhất 32 byte** trong mẫu này; AES-256 dùng khóa đúng 32 byte cùng nonce/IV được quản lý đúng.

## 3. Kiến trúc tách code khỏi secret value

~~~mermaid
flowchart LR
    A["Git / source code<br/>chỉ tên property và schema"] --> B["Build artifact<br/>JAR / container image"]
    C["Secret manager / KMS / Vault<br/>phân quyền, audit, rotation"] --> D["Runtime injection<br/>env / secret file / configtree / SDK"]
    B --> E["Spring Boot application"]
    D --> E
    E --> F["PasswordEncoder / OAuth2 client / JWT signer / DB"]
    E --> G["Log và response<br/>KHÔNG chứa secrets"]
~~~

Ranh giới tin cậy: chỉ workload được cấp đúng identity và quyền mới lấy được những secrets nó cần. Build artifact được đóng gói **một lần** và chạy ở dev/staging/prod với cấu hình bí mật riêng từng môi trường.

Các kênh phân phối thường thấy:

1. **Environment variables:** đơn giản, Spring Boot hỗ trợ tốt; phù hợp demo và môi trường được bảo vệ. Tuy nhiên environment có thể lộ qua process inspection, debugging, crash report, container inspect, CI job, telemetry.
2. **Secret file mounted ở runtime:** Kubernetes Secret volume, Docker secret mount, CSI driver hoặc agent Vault. Giảm nguy cơ xuất hiện trong environment; cần quản lý file owner/mode/ACL, lifecycle và đồng bộ sau rotate.
3. **Secret manager qua identity của workload:** AWS Secrets Manager, Azure Key Vault, Google Secret Manager, HashiCorp Vault hoặc nền tảng tương đương. Có audit, role, phiên bản, rotate; cần kiểm cache, retry, availability, quota và startup failure.
4. **Dynamic/short-lived credential:** database IAM authentication, cloud managed identity, federation OIDC, mTLS identity, Vault dynamic secrets. Thường tốt hơn credential dài hạn khi hệ thống có hỗ trợ.
5. **KMS/HSM:** cho phép thực hiện signing/decryption bằng API mà ứng dụng không nhất thiết nhận private key thô; giảm bề mặt rò khóa. Vẫn cần bảo vệ quyền gọi KMS và log.

**Trade-off:** environment variables dễ dùng nhưng không mặc định an toàn hơn secret file; mounted file cũng không an toàn nếu mọi process trong pod có quyền đọc hoặc file được copy vào image. Security đến từ **quyền truy cập, môi trường thực thi, chính sách rotate và giám sát**, không phải tên kênh.

## 4. Spring Boot Externalized Configuration: chỉ định tên bí mật, không ghi giá trị

Spring Boot có thể cấu hình qua `application.yml`, biến môi trường, command-line arguments, ConfigData imports và các property sources do integration bổ sung. Với một runtime secret, file version-controlled chỉ nên chứa **property name và placeholder**, không có secret value.

Ví dụ:

~~~yaml
# src/main/resources/application.yml — được phép commit vì không có bí mật.
spring:
  application:
    name: external-secrets-demo

app:
  auth:
    operator-username: ${APP_OPERATOR_USERNAME}
    operator-password-hash: ${APP_OPERATOR_PASSWORD_HASH}
~~~

Giá trị `APP_OPERATOR_PASSWORD_HASH` được cung cấp **ở runtime**. Không khai báo fallback như `${APP_OPERATOR_PASSWORD_HASH:changeme}` cho production, vì app có thể vô tình khởi chạy với credential cố định. Không log giá trị resolved configuration.

Spring Boot có relaxed binding, nhưng khi dùng placeholder explicit như trên, tên env var cần đúng chính xác. Nếu dùng quy tắc env mapping trực tiếp, ví dụ một property `app.auth.operator-password-hash` thường tương ứng `APP_AUTH_OPERATORPASSWORDHASH` theo quy tắc chuyển tên Spring Boot; hãy xác minh quy tắc của phiên bản Boot đang chạy. Để giảm sai khác, bài demo dùng **placeholder env explicit**.

### Fail fast khi thiếu cấu hình

Ứng dụng production nên từ chối startup nếu thiếu credential bắt buộc hoặc định dạng không hợp lệ, thay vì chạy “anonymous”, dùng hardcoded default hoặc silently skip authentication.

Một bản config chỉ có tên property là chưa đủ nếu code vẫn bỏ qua secret khi null. Dùng `@ConfigurationProperties` với validation và kiểm định dạng để phát hiện sớm. **Không đưa toàn bộ property value vào exception message**, vì startup log cũng là nơi dễ rò secrets.

### Secret value khác tên/đường dẫn secret

- `APP_OPERATOR_PASSWORD_HASH`: có thể là bí mật hoặc dữ liệu nhạy cảm; không in/log.
- `SIGNING_KEY_FILE=/run/secrets/private-key.pem`: **đường dẫn** không nhất thiết bí mật; được phép cấu hình.
- `billing-client-secret`: **tên key** trong secret manager không phải secret value; cũng không nên công khai metadata cơ sở hạ tầng hơn mức cần.
- `Secret Version ID` hoặc fingerprint không thay thế authentication; có thể dùng làm telemetry nếu đã cân nhắc rò metadata.

## 5. Ví dụ Spring Security chạy được: cấp password hash ngoài mã nguồn

Trong nhiều hệ thống, password hash của người dùng nằm trong database quản lý danh tính. Tuy nhiên một **tài khoản bootstrap/operator hạn chế quyền** là bài học tốt để minh họa external secret config. Ví dụ sau **không lưu raw password**, chỉ nhận password hash ở runtime; không nhúng hash, username hoặc secret thật vào JAR.

**Yêu cầu:** JDK 17+, Maven 3.9+, Spring Boot 3.5.0 và Spring Security 6.x. Hash có dạng `{bcrypt}$2a$...` hoặc `{bcrypt}$2b$...` theo `DelegatingPasswordEncoder`. Bcrypt trong demo không thay thế yêu cầu identity provider, audit, MFA và quyền hạn ở production.

Cấu trúc:

~~~text
external-secrets-demo/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/com/example/secrets/
│   ├── ExternalSecretsApplication.java
│   ├── OperatorSecrets.java
│   ├── SecurityConfig.java
│   └── AccountController.java
└── src/test/java/com/example/secrets/
    └── ExternalSecretsSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>external-secrets-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

### 5.2. application.yml

~~~yaml
spring:
  application:
    name: external-secrets-demo

app:
  auth:
    operator-username: ${APP_OPERATOR_USERNAME}
    operator-password-hash: ${APP_OPERATOR_PASSWORD_HASH}
~~~

Tệp YAML này **có thể lưu trong repository**, vì nó chứa tên biến, không chứa giá trị. Đừng gửi secret qua command line kiểu `--app.auth.operator-password-hash=...` vì command arguments có thể bị đọc từ process listing, shell history hoặc log.

### 5.3. ExternalSecretsApplication.java

~~~java
package com.example.secrets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExternalSecretsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalSecretsApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm record config ở phần kế tiếp. Không cần tự gọi `System.getenv(...)` rải rác trong các controller.

### 5.4. OperatorSecrets.java

~~~java
package com.example.secrets;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.auth")
public record OperatorSecrets(
    @NotBlank String operatorUsername,
    @NotBlank String operatorPasswordHash
) {}
~~~

**Giải thích:** Spring Boot bind `operator-username` vào `operatorUsername` và `operator-password-hash` vào `operatorPasswordHash`. `@NotBlank` ngăn giá trị null/blank lúc startup. App không tự thay giá trị thiếu bằng mật khẩu mặc định.

`String` trong JVM là immutable và không thể xóa sạch bằng `Arrays.fill`; do đó cần hạn chế sao chép/ghi lại secret, thu hẹp thời gian tồn tại, kiểm soát heap dump và process diagnostics. Password hash cũng nên được xử lý như dữ liệu có quyền truy cập hạn chế.

### 5.5. SecurityConfig.java

~~~java
package com.example.secrets;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(OperatorSecrets properties) {
        String storedHash = properties.operatorPasswordHash();

        // Chỉ chấp nhận định dạng bcrypt theo policy của ví dụ.
        if (!storedHash.startsWith("{bcrypt}$2")) {
            throw new IllegalStateException(
                "Operator password hash must use bcrypt encoding");
        }

        return new InMemoryUserDetailsManager(
            User.withUsername(properties.operatorUsername())
                .password(storedHash)
                .roles("OPS")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/ops/status")
                    .hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }
}
~~~

Ở đây:

1. **Không có mật khẩu thật/hardcoded hash** trong Java. Hash được truyền qua `OperatorSecrets` từ Spring configuration ở runtime.
2. `DelegatingPasswordEncoder` hiểu prefix `{bcrypt}`; không dùng `NoOpPasswordEncoder` hoặc `{noop}` cho tài khoản thật.
3. `UserDetailsService` trong ví dụ chỉ có một tài khoản OPS có scope nhỏ. Với người dùng bình thường, dùng database/identity provider quản lý hash, chính sách MFA và lifecycle người dùng.
4. Spring Security xác thực HTTP Basic mỗi request, không lưu login vào session. Điều này độc lập với việc hash nằm trong secret store.
5. `/api/me` và `/api/ops/status` không trả giá trị hash/secret. Các endpoint khác bị `denyAll`. Rule method chỉ cho phép GET theo hợp đồng.
6. Ví dụ chỉ có các request `GET`; giữ CSRF protection mặc định. Khi thêm POST/PUT/PATCH/DELETE cho browser, cần quyết định chiến lược CSRF, không tắt chỉ vì dùng Basic/STATELESS.
7. Message fail-fast chỉ nói định dạng sai, **không** nối value thực vào exception.
8. Với production, nên kiểm thêm kích thước/cost bcrypt đúng policy, tài khoản/rate-limit và quản trị rotation. Không coi `startsWith` là validator đầy đủ của mọi hash; nó giúp phát hiện lỗi cấu hình đơn giản trong demo.

### 5.6. AccountController.java

~~~java
package com.example.secrets;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/me")
    public Me me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new Me(authentication.getName(), roles);
    }

    @GetMapping("/api/ops/status")
    public Status status() {
        return new Status("ready");
    }

    public record Me(String username, List<String> roles) {}
    public record Status(String status) {}
}
~~~

DTO chỉ trả tên principal, authorities và trạng thái vô hại. **Không** viết endpoint `/api/debug/config` trả `OperatorSecrets` — record này chứa verifier nhạy cảm. Khi cần health check, chỉ trả boolean/trạng thái, không trả tên secret, key length, credential hoặc fingerprint tùy tiện.

### 5.7. ExternalSecretsSecurityTest.java

Test tự cấp một **password hash được sinh tại runtime cho tài khoản thử**, không dùng secret của staging/production, không ghi hash ra repo:

~~~java
package com.example.secrets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExternalSecretsSecurityTest {

    private static final String TEST_PASSWORD =
        "local-test-only-password-123";

    private static final String TEST_HASH = "{bcrypt}" +
        new BCryptPasswordEncoder(10).encode(TEST_PASSWORD);

    @DynamicPropertySource
    static void testSecrets(DynamicPropertyRegistry registry) {
        registry.add("app.auth.operator-username",
            () -> "operator-test");
        registry.add("app.auth.operator-password-hash",
            () -> TEST_HASH);
    }

    @Autowired
    MockMvc mvc;

    @Test
    void correctExternalHashAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("operator-test", TEST_PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("operator-test"))
            .andExpect(jsonPath("$.roles[0]").value("ROLE_OPS"));
    }

    @Test
    void badPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("operator-test", "not-the-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousIs401() throws Exception {
        mvc.perform(get("/api/ops/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedStatusContainsNoPasswordHash() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic("operator-test", TEST_PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ready"));
    }
}
~~~

Các test dùng `@DynamicPropertySource` để đặt giá trị property **chỉ cho test**; chúng không cần và không được truy cập production secret manager. Password `local-test-only-password-123` là chuỗi test công khai và không có quyền ở môi trường khác. Khi chạy thật, username/password của deployment được provision riêng.

**Giới hạn:** Test chứng minh Spring Boot bind property và Spring Security xác thực bằng hash được cấp từ ngoài class cấu hình; nó **không tự chứng minh** permissions của Vault/Kubernetes/CI, hay vòng đời rotate production. Những phần đó cần deployment/infrastructure test.

### 5.8. Chạy thử

Ở thư mục dự án:

~~~bash
mvn test
~~~

Nếu Maven/JDK và dependencies phù hợp, các test dự kiến pass; bài này **không khẳng định đã thực thi Maven**. Chạy ứng dụng bằng `mvn spring-boot:run` cần provision **cả** `APP_OPERATOR_USERNAME` và `APP_OPERATOR_PASSWORD_HASH` trước, nếu thiếu thì startup phải thất bại thay vì tự chọn mật khẩu yếu.

Ví dụ bash để nhập cấu hình **không ghi trực tiếp hash vào shell command history**:

~~~bash
export APP_OPERATOR_USERNAME=operator
read -r -s -p "Enter provisioned {bcrypt} hash: " APP_OPERATOR_PASSWORD_HASH
echo
export APP_OPERATOR_PASSWORD_HASH
mvn spring-boot:run
~~~

Giá trị hash phải được tạo/đưa vào từ một quy trình provisioning tin cậy. Nếu dùng bash trên máy local, không copy giá trị hash vào shell history và tránh chụp màn hình log. Dù nhập qua `read -s`, biến môi trường **vẫn có thể bị lộ qua process inspection**; đây là ví dụ đơn giản, production nên dùng secret manager/mounted file theo chính sách.

Một request thành công cần kèm **raw password tương ứng hash** mà operator nhập lúc tạo credential:

~~~bash
curl -i -u operator http://localhost:8080/api/me
~~~

Với `curl -u operator` (không nhập `:password` trên dòng lệnh), curl sẽ **hỏi password tương tác**, giảm rủi ro lộ password qua shell history/process arguments. `GET /api/ops/status` cũng chỉ thành công khi credentials hợp lệ. Nếu không có credentials, HTTP Basic cho API bảo vệ thường trả `401`; với credentials hợp lệ, `/api/me` trả username và role OPS.

Sau khi thử:

~~~bash
unset APP_OPERATOR_PASSWORD_HASH
unset APP_OPERATOR_USERNAME
~~~

Lệnh `unset` xóa biến khỏi shell hiện hành, **không thu hồi** credential đã dùng; cần revoke/rotate nếu nghi đã lộ.

## 6. Password hashing: bí mật thô không thuộc source, verifier không nên lộ

Spring Security khuyến nghị dùng một `PasswordEncoder` phù hợp với khả năng tính toán và yêu cầu của hệ thống. Với `DelegatingPasswordEncoder`, một hash có prefix `{bcrypt}` được giao cho `BCryptPasswordEncoder`. Mỗi lần encode bcrypt sinh salt ngẫu nhiên trong hash; hai hash của cùng một password **thường khác nhau**, vẫn cùng matches.

Ví dụ sử dụng API (mảnh minh họa không phải class độc lập):

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode(rawPasswordFromSafeInput);
boolean match = encoder.matches(candidatePassword, storedHash);

// KHÔNG ghi storedHash hoặc rawPassword vào log/HTTP response.
~~~

Đoạn này cần import `PasswordEncoder` và `PasswordEncoderFactories`; với hệ thống thật, raw password đến từ một request được bảo vệ qua TLS, không lấy từ hardcoded constant. `encode` không dùng khi **so sánh** một password với hash đã có; hãy dùng `matches`, bởi vì salt ngẫu nhiên khiến `encode(candidate)` tạo ra kết quả khác.

**Chi phí bcrypt** cần được hiệu chỉnh theo hạ tầng và mục tiêu tốc độ login, không đặt quá thấp để tấn công đoán password rẻ hoặc quá cao đến mức bị denial-of-service. Những ứng dụng mới cũng có thể cân nhắc Argon2id/PBKDF2/scrypt tùy môi trường và chính sách. Không tự xây thuật toán hash bằng `MessageDigest.getInstance("SHA-256")` một lượt rồi lưu làm password verifier.

**Phạm vi áp dụng secret manager cho password:**

- Password hash của hàng triệu end users: lưu trong **identity/user database** có access control và backup phù hợp.
- Một bootstrap credential hạn chế quyền: có thể inject hash qua secret manager, nhưng tốt hơn nếu không cần tài khoản cố định.
- Database password, partner client secret, API key: thường là các secrets thực sự cần cấp qua deployment/secret manager.
- Không gửi password qua config để “tạo admin mặc định” trên mọi replica mà không có quy trình rotate/revoke.

## 7. OAuth2 confidential client: client secret chỉ thuộc backend

Spring Security OAuth2 Client dùng `client_id` và `client_secret` khi một backend là **confidential client**, ví dụ lấy token theo `client_credentials` để gọi API đối tác. `client_id` thường là identifier không bí mật; `client_secret` là credential.

**Đây là ví dụ cấu hình bổ sung, không phải phần của ứng dụng runnable mục 5.** Nếu triển khai OAuth2 Client trong project khác, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: invoices.read
        provider:
          billing:
            token-uri: https://auth.example.test/oauth2/token
~~~

`https://auth.example.test/oauth2/token` là URL **minh họa**, phải thay bằng token endpoint thật do nhà cung cấp xác nhận. Tài liệu này không yêu cầu và không thực hiện kết nối tới một provider thật.

Những điểm bảo mật:

1. Không ghi `client-secret` thực vào `application.yml` trong Git, Maven POM, JAR, Dockerfile `ENV` hoặc frontend bundle.
2. Mỗi environment/đối tác nên có credential riêng, scope tối thiểu, expiration và owner rõ ràng.
3. `client_secret_basic` gửi credential theo cơ chế HTTP Basic ở kết nối HTTPS tới token endpoint; không log `Authorization` hoặc form `client_secret`.
4. Đối với **SPA, mobile/native app hoặc desktop public client**, không giả định có thể giữ `client_secret` an toàn trong binary/frontend. Chúng nên dùng thiết kế public client như Authorization Code + PKCE và chính sách của authorization server.
5. Access token nhận về cũng là dữ liệu nhạy cảm: không log/đưa vào URL, bảo vệ cache/token store, refresh theo hạn và scope.
6. Khi có lựa chọn, cân nhắc `private_key_jwt`, mTLS, managed identity hoặc workload federation để tránh shared static secret; nhưng private key/identity permission vẫn phải được quản lý.
7. Rotation OAuth2 client secret cần phối hợp với provider, có thể cần giai đoạn overlap giữa secret cũ và mới theo khả năng nhà cung cấp.

### Vì sao không đưa secret vào frontend?

~~~javascript
// SAI: mọi người tải web bundle đều có thể đọc secret.
const oauthClientSecret = "NOT_A_SECRET_IF_IN_BROWSER";
~~~

Dù minify/obfuscate, chuỗi vẫn đi tới trình duyệt. Nếu frontend cần đăng nhập qua OAuth2, dùng flow phù hợp cho public client, không biến frontend thành confidential client bằng việc gắn `client_secret`.

## 8. Signing key và encryption key: ranh giới quyền cao hơn một password

### JWT/JWS với asymmetric signing

Một kiến trúc phổ biến:

~~~text
Token issuer / authorization server:
  - Có private key RSA/EC hoặc quyền ký qua KMS/HSM
  - Ký JWT, gắn key ID (kid) phù hợp

Resource servers:
  - Chỉ nhận public key/JWKS từ nguồn tin cậy
  - Verify signature + issuer + audience + expiry + algorithm policy
  - KHÔNG cần private signing key
~~~

**Private key là secret**; public key không cần được giữ bí mật, nhưng phải được lấy từ issuer/JWKS URI tin cậy qua kênh đã xác minh. Không cho mọi microservice cùng cầm private key chỉ để verify, vì bất kỳ service bị xâm nhập nào cũng có thể phát hành token giả.

Trong Spring Security Resource Server, thường cấu hình issuer URI đáng tin hoặc JWK Set URI theo hướng dẫn của hệ thống danh tính:

~~~yaml
# Ví dụ resource server; KHÔNG thuộc demo HTTP Basic ở mục 5.
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

Cần dependency `spring-boot-starter-oauth2-resource-server` và cấu hình xác minh audience khi ứng dụng yêu cầu. URI này là địa chỉ minh họa. Sự có mặt của `issuer-uri` không tự cấu hình mọi audience restriction trong mọi hệ thống; cần xác minh hợp đồng token. Không chấp nhận thuật toán/issuer tùy ý từ token header mà không đối chiếu policy server.

### HMAC symmetric signing

Với HS256, issuer và verifier cùng giữ **một** HMAC key; mọi verifier có key đều có khả năng tạo MAC hợp lệ, nên phạm vi phân phối rộng sẽ tăng rủi ro. Sử dụng key ngẫu nhiên đủ entropy và rotate theo `kid`/version khi hệ thống hỗ trợ.

Sinh secret thử nghiệm **không in ra Git** (bash với OpenSSL):

~~~bash
# Chỉ để tạo key demo; stdout chứa SECRET, không chụp/log/commit.
openssl rand -base64 32
~~~

Output là secret thật của lần gọi đó; nó **không phải một chuỗi public mẫu để copy vào code**. Trong production, secret manager/KMS nên tạo, lưu, phân phối và kiểm soát key. Nếu dùng Base64 để vận chuyển byte key, **Base64 không mã hóa**; nội dung chỉ được encode.

### Encryption key khác JWT signing key

Khóa AES-GCM dùng cho confidentiality/integrity của ciphertext. Cần nonce/IV **duy nhất theo mỗi key**, thường 12 byte được tạo thích hợp, cùng AAD/metadata khi áp dụng. Không tái sử dụng cùng key cho nhiều mục đích (JWT signing, mã hóa database, CSRF, API authentication); domain separation và lifecycle rõ ràng giúp giảm nguy cơ tác động chéo.

Nếu dữ liệu lâu dài được mã hóa bằng key đã rotate, cần chiến lược **key versioning, decrypt bằng key cũ trong giai đoạn chuyển đổi, re-encrypt/rewrap**, backup và disaster recovery. Việc thay giá trị env key đột ngột có thể khiến dữ liệu cũ không giải mã được.

### File mount riêng cho private key

Ví dụ cấu hình đường dẫn:

~~~yaml
app:
  crypto:
    signing-private-key-path: ${SIGNING_KEY_PATH:/run/secrets/jwt-signing-key.pem}
~~~

`SIGNING_KEY_PATH` là đường dẫn, không phải nội dung PEM. Signing service mới cần đọc private key; resource server verify nên dùng **public key/JWKS** thay vì mount key riêng tư. Khi đọc PEM/PKCS#8 phải kiểm định thuật toán, format, quyền đọc, size và chống ghi log key; không tự parse/mã hóa dựa vào chuỗi `replace` thiếu kiểm tra.

## 9. Secret file mount và Spring Boot Config Tree

Một lựa chọn hiệu quả là đưa mỗi secret vào file chỉ đọc do runtime mount, thay vì nhúng vào image hoặc Git. Spring Boot có **Config Data config tree** đọc tên tệp làm property name.

Ví dụ trong môi trường có thư mục `/run/secrets/`:

~~~text
/run/secrets/
├── app.auth.operator-username
├── app.auth.operator-password-hash
└── billing.client-secret
~~~

Nội dung từng file là **giá trị property**, không phải YAML. File name `app.auth.operator-password-hash` đại diện key property; content phải được provision bởi hệ thống bí mật. Quyền filesystem cần cho phép **chỉ app identity hoặc agent được phép** đọc. Đừng mount bí mật vào đường public/web root hoặc mọi container không cần thiết.

Một cấu hình khác trong môi trường file-mount, **thay cho env-placeholder strategy** ở mục 5:

~~~properties
# application-prod.properties — chỉ import đường dẫn, không chứa secret.
spring.config.import=configtree:/run/secrets/
~~~

Khi đó `app.auth.operator-password-hash` có thể được bind trực tiếp từ file cùng tên. Cần bảo đảm thứ tự/độ ưu tiên property sources tương ứng với cấu hình khác của môi trường; **không nên đồng thời duy trì một placeholder env bắt buộc không được cấp** nếu nó khiến quá trình bind/resolve sai. Chọn một nguồn runtime rõ ràng và thử startup với cấu hình production thật.

Nếu muốn cho thư mục không tồn tại ở local-only, Spring Boot có dạng `optional:configtree:/run/secrets/`; production thường nên **fail fast** khi secret mount bắt buộc bị thiếu, không đặt `optional:` chỉ để tránh lỗi khởi động.

### So sánh env và mount

| Tiêu chí | Environment variables | Secret file / configtree |
|---|---|---|
| Bind trong Spring | Placeholders/relaxed binding | `spring.config.import=configtree:...` |
| Rủi ro | Process env, debug tools, CI/export, child process | File permissions, mount scope, backups, accidental copy |
| Rotation | Thường cần restart/rollout để process nhận env mới | File có thể thay đổi, nhưng **Spring không tự bảo đảm mọi bean đã nạp secret sẽ reload** |
| Phân quyền | Theo quyền đọc process/deployment env | Theo service account/volume và filesystem ACL |
| Hỗ trợ key PEM nhiều dòng | Khó quản lý escaping | File mount thường tự nhiên hơn |
| Vận hành | Dễ với demo/local | Tốt cho key/cert và secret lớn, phụ thuộc secret delivery |

**Không đồng nhất “file được cập nhật” với “client đang dùng key mới”.** Nhiều bean Spring được tạo một lần khi khởi động và giữ bản copy credential; cần cơ chế refresh chính thức hoặc rollout ứng dụng có kiểm thử. Với JWT key rotation, còn phải xử lý xác minh token cũ và key IDs.

## 10. Docker và Kubernetes: runtime injection, không đóng bí mật vào image

### Docker

**Không** đặt:

~~~dockerfile
# SAI: secret sẽ nằm trong image layer/build history.
ENV DATABASE_PASSWORD=real-secret
~~~

Cũng không đưa secret vào `ARG` rồi nghĩ sẽ an toàn: build args có thể xuất hiện trong metadata/history/log/cache tùy quá trình build. Ưu tiên secret mounts của BuildKit cho **những bước build thực sự cần** secret, và secret runtime injection cho dịch vụ.

Ở runtime, Docker secrets (khi được hỗ trợ bởi chế độ orchestration tương ứng) thường xuất hiện dưới dạng file; application có thể đọc file qua property/configtree. Kiểm container permissions, file mode và việc secrets không bị copy vào image. Một image đã chứa secret phải được coi là artifact bị lộ, không “sửa” chỉ bằng cách xóa ở layer sau.

### Kubernetes Secret không tự đồng nghĩa mã hóa an toàn

Một manifest workload chỉ tham chiếu đến **tên Secret** do cluster operator/external-secrets controller provision:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: secure-app
  template:
    metadata:
      labels:
        app: secure-app
    spec:
      serviceAccountName: secure-app-sa
      containers:
        - name: app
          image: registry.example.test/secure-app:1.0.0
          env:
            - name: APP_OPERATOR_USERNAME
              value: "operator"
            - name: APP_OPERATOR_PASSWORD_HASH
              valueFrom:
                secretKeyRef:
                  name: secure-app-runtime
                  key: operator-password-hash
          ports:
            - containerPort: 8080
~~~

Đây là **manifest triển khai minh họa**: cần namespace, image thật, imagePullPolicy, probes, resources, policy admission, network và service phù hợp trước production. Manifest không chứa secret value. `APP_OPERATOR_PASSWORD_HASH` trong env cần được tạo bởi secret manager/controller; pod thường phải được restart/rollout để nhận **giá trị env cập nhật**.

**Kubernetes Secret `data:` dùng Base64 encoding, không phải encryption.** Bảo mật thực tế phụ thuộc RBAC, encryption at rest của etcd, secret distribution, audit, quyền của service account, admission controls và isolation container. Không commit manifest Secret có `data:` thật hoặc `stringData:` thật vào Git công khai/nội bộ rộng.

Với private signing key, nên mount Secret/CSI volume read-only và file permissions hạn chế, thay vì inject PEM vào env. Không mount toàn bộ kho bí mật tới mỗi pod. Hạn chế quyền `get/list/watch secrets` cho service account; ứng dụng thường chỉ cần đọc đúng secret đã mount, **không cần** tự có quyền liệt kê mọi Secret trong namespace.

### Vì sao secret volume có thể tốt hơn env đối với private key?

- PEM nhiều dòng không phải escape sang chuỗi env.
- Có thể đặt file mode/owner/readOnly và tham chiếu đường dẫn.
- Dễ tách key của issuer khỏi resource servers.
- Có thể kết hợp CSI driver/KMS theo quy trình hiện hành.

Nhưng mounted private key vẫn tồn tại trong filesystem của pod và có thể bị đọc bởi process bị compromise; KMS/HSM signing API có thể giảm rủi ro không cần xuất raw private key.

## 11. CI/CD: bí mật không nên xuất hiện trong build/test log

### Chia trách nhiệm theo pipeline

| Giai đoạn | Nên có | Không nên có |
|---|---|---|
| Source review | Property names, schema, test fixtures giả | Raw credentials, .env thật, private PEM |
| Compile/unit test | Fake/generated test secret trong process test | Production DB password, partner client secret |
| Package | Image/JAR không chứa secret | `COPY .env`, PEM, secret file vào image |
| Deploy | Identity của deployer có quyền ghi/tham chiếu secret đúng môi trường | Echo secret, truyền qua command-line arguments, share artifact credential |
| Runtime | Pod/app identity đọc đúng secret được cấp | Một superuser key dùng chung mọi dịch vụ |
| Observability | Status/metric và correlation IDs đã ẩn danh | `Authorization`, `Cookie`, token, passwords, private keys |

Ưu tiên **OIDC workload federation** từ CI đến cloud khi được hỗ trợ để lấy credential ngắn hạn, tránh lưu cloud access key dài hạn trong CI secrets. GitHub Actions/GitLab CI/Azure Pipelines đều có cơ chế quản lý secret, nhưng mỗi hệ thống có giới hạn/điều kiện riêng; kiểm chính sách masking và script output trước khi in log.

**Đừng giả định log masking tuyệt đối.** Giá trị secret có thể bị biến đổi (Base64, URL encode, JSON escape, cắt chuỗi) khiến bộ lọc không nhận ra. Script có `set -x`, shell trace, debug logs, `env`, `printenv`, `docker inspect`, `kubectl describe` hoặc test failure dumps có thể tạo rò dữ liệu.

Một file `.gitignore` hữu ích:

~~~gitignore
# File local chỉ chứa secrets; dùng template không có giá trị.
.env
.env.*
!.env.example
secrets/
*.key
*.p12
*.pfx
*.pem
~~~

**Lưu ý:** `.gitignore` không xóa file đã được Git theo dõi trước đó; cũng không thay việc xoay vòng secret bị lộ. Quy tắc `*.pem` có thể chặn cả public certificates cần được lưu — điều chỉnh có chủ đích; private key phải luôn được bảo vệ.

Một `.env.example` có thể chứa:

~~~dotenv
# TÊN biến / cú pháp ví dụ, không có giá trị bí mật.
APP_OPERATOR_USERNAME=
APP_OPERATOR_PASSWORD_HASH=
BILLING_CLIENT_ID=
BILLING_CLIENT_SECRET=
SIGNING_KEY_PATH=/run/secrets/jwt-signing-key.pem
~~~

Không dùng giá trị “real-looking” trong `.env.example` rồi hy vọng chúng vô hại. Nếu có cần local mock credentials, làm rõ đó là tài khoản không có quyền thật và bị giới hạn ở môi trường test.

## 12. Ngăn secret leakage qua Actuator, error, log và debug endpoint

Các vị trí rò phổ biến:

- In nguyên đối tượng `@ConfigurationProperties` với `toString()` (record mặc định sinh `toString` có cả fields).
- Log `Environment`, headers HTTP, request body login, `OAuth2ClientCredentialsGrantRequest`, token response hoặc exception nội bộ chứa credential.
- Đưa thuộc tính nhạy cảm vào `/actuator/env`, `/actuator/configprops`, thread dump, heap dump, build reports hoặc diagnostics.
- Trả response “debug config” từ controller; serialize bean/config tự động.
- Đính credentials trong URL query, redirect, exception message hoặc client-side monitoring.
- Đưa secret vào Docker image, layer, OCI labels, CI cache, artifacts, source maps, Sentry breadcrumbs.

**Spring Boot có cơ chế sanitize một số keys trong Actuator**, nhưng không được dựa vào đó làm bảo vệ duy nhất: custom property names, transformations và endpoints tự viết vẫn có thể rò. Giới hạn quyền mở Actuator và không public các endpoint nhạy cảm; kiểm thử response thật của environment đang chạy.

Tránh:

~~~java
// SAI: record OperatorSecrets chứa password hash.
log.info("Loaded config: {}", operatorSecrets);
~~~

Thay bằng telemetry không chứa dữ liệu bí mật:

~~~java
// Minh họa: chỉ ghi trạng thái, không ghi secret/fingerprint.
log.info("Required authentication configuration loaded successfully");
~~~

Khi fail fast, thông báo nên ghi **tên property**/loại cấu hình cần cấp, không nối giá trị. Khi cần trace, dùng correlation ID và cờ `present/absent` đã đánh giá không rò metadata nhạy cảm.

**Giới hạn quyền heap dump, debugger, profiler và `/proc`** tương đương quyền đọc secret. Một người có quyền attach debugger hoặc dump memory của process thường có thể xem credential dù secret được cấp qua Vault.

## 13. Xoay vòng (rotation) và thu hồi (revocation) đúng cách

“Tách secret khỏi source” chỉ có ý nghĩa dài hạn khi có lịch và thao tác **rotate/revoke**. Thiết kế một quy trình có owner, thời hạn, rollback và bằng chứng sau rotate.

### Quy trình chung

1. **Inventory:** bí mật nào, dùng ở workloads nào, nguồn cấp, phạm vi quyền, ngày hết hạn, người chịu trách nhiệm và tác động khi revoke.
2. **Tạo phiên bản mới** qua CSPRNG/KMS/provider; không tái sử dụng secret từ môi trường khác.
3. **Provision** secret mới vào kho được quản lý, kiểm ACL/authorization, hạn dùng, audit.
4. **Triển khai** workload dần dần; nếu provider cho phép đồng thời secret cũ và mới, dùng khoảng overlap có giới hạn.
5. **Smoke/integration test** bằng workload mới và metric lỗi auth/5xx/latency ở canary; tránh ghi secret trong telemetry.
6. **Chuyển toàn bộ clients**, xác nhận không còn request bằng secret cũ.
7. **Revoke/disable** secret cũ ở provider, không chỉ xóa file/env trên một instance.
8. **Giám sát và ghi biên bản**: version được triển khai, thời gian kết thúc overlap, kết quả kiểm và người phê duyệt.
9. **Rollback có chủ đích**: không tái bật secret đã xác định bị compromise. Nếu credential bị lộ, cần phương án khẩn cấp không có overlap cũ.

### Password / bootstrap operator

Nếu password/hash bị nghi lộ, đổi raw password, tạo hash mới, provision hash mới, loại bỏ phiên hiện hành khi chính sách yêu cầu và kiểm hoạt động. Không phải chỉ đổi `{bcrypt}` prefix là rotate. Nếu bootstrap user không cần thiết nữa, loại bỏ và vô hiệu credential.

### OAuth2 client secret

Provider có thể cho tạo secret thứ hai trong thời gian chuyển tiếp. Thay secret trong runtime, test lấy token mới, theo dõi client authentication errors, sau đó revoke secret cũ. **Không** cho rằng toàn bộ provider hỗ trợ nhiều secret đồng thời: kiểm tài liệu nhà cung cấp và phối hợp downtime/window nếu cần.

### JWT signing keys

Với asymmetric signing, công bố **public key mới** trong JWKS (gắn `kid`), chuyển issuer sang ký bằng private key mới, giữ public key cũ đủ lâu cho token cũ chưa hết hạn (trừ trường hợp phải revoke khẩn cấp), rồi gỡ key cũ. Client cần validate issuer, audience, algorithm, expiry và cache-refresh JWKS hợp lý. Private key cũ nghi compromise có thể buộc revoke sớm, chấp nhận invalidation token.

Với HMAC key chia sẻ, phải điều phối đồng thời signer/verifiers; giữ cả phiên bản cũ và mới có kiểm soát nếu token còn hợp lệ. Không mặc định sửa một env var ở một node là tất cả node đã rotate.

### Encryption keys

Rotate key mã hóa cần kế hoạch **giải mã dữ liệu cũ** và rewrap/re-encrypt. Nếu dùng envelope encryption, thay KEK (key encryption key) có thể được thực hiện bằng rewrap DEK (data encryption key) mà không cần decrypt toàn bộ dữ liệu tùy thiết kế. Không xóa key cũ trước khi xác minh dữ liệu/backups đã được migrate hoặc có chiến lược phục hồi.

## 14. Khi nghi secret đã bị commit hoặc gửi nhầm

Quy trình ứng phó không được chỉ dừng ở “xóa file”:

1. **Xác định** secret loại nào, nguồn lộ (Git, CI log, artifact, chat, ticket, image, crash dump), thời gian và phạm vi bị truy cập.
2. **Hạn chế truy cập ngay**, revoke/rotate credential ưu tiên trước; với key ký bị lộ cân nhắc thu hồi token và điều tra token giả.
3. **Kiểm audit** đăng nhập, token issuance, DB access, KMS operations và dấu hiệu lạm dụng.
4. **Sửa điểm rò** trong build/log/config; xóa khỏi source hiện tại và artifacts/log được phép xử lý.
5. **Làm sạch lịch sử** (khi tổ chức cho phép) để giảm lộ tiếp diễn, nhưng đừng tin rewrite Git history đủ để vô hiệu secret đã bị sao chép.
6. **Mở rộng điều tra** tới forks/clones/cache/mirror và các tài nguyên dùng chung credential.
7. **Bổ sung kiểm soát**: secret scanning pre-commit/CI, review cấu hình, least privilege, TTL và rotation automation.

Không dùng `git filter-repo` hoặc lệnh rewrite history tùy tiện trên repository nhiều người đang dùng mà không phối hợp; xử lý lịch sử có thể phá đồng bộ của collaborators. **Rotate/revoke là hành động bắt buộc khi bí mật đã lộ**, kể cả sau khi xóa lịch sử.

## 15. Kiểm thử cấu hình bí mật và deployment

Một test suite tốt không cần biết production credentials. Có thể dùng **fake/test-only secrets** và mock secret manager, rồi thực hiện smoke test với workload identity khi deploy.

| Case | Cách thử | Expected |
|---|---|---|
| App không được cấp `APP_OPERATOR_PASSWORD_HASH` | Chạy profile runtime thiếu env/mount | Startup thất bại rõ ràng, không dùng default password |
| Hash sai format | Cấp một chuỗi không có `{bcrypt}` | Fail fast, không ghi giá trị vào log |
| Password hợp lệ | MockMvc HTTP Basic với hash test runtime | 200 và `ROLE_OPS`, không trả hash |
| Password sai / anonymous | Gọi API bảo vệ | 401, không lộ secret |
| Secret file permission denied | Giả lập mount thiếu quyền đọc | Startup fail, metric cảnh báo; không fallback hardcoded |
| Env và secret file conflict | Cấp cả hai cấu hình trong thử nghiệm | Xác định rõ priority, từ chối hoặc chọn nguồn chủ động theo policy |
| CI log/artifact scan | Quét biến/credential markers trong artifact | Không có secret value; false positives được review |
| Container image scan | Kiểm layer/build history | Không có `.env`, `*.key`, raw secret hoặc credentials trong history |
| Rotation OAuth client | Cấp version mới, test token endpoint, revoke cũ | Workload dùng secret mới, không còn sử dụng secret cũ |
| JWT key rollover | Issuer ký key mới, verifier dùng JWKS với `kid` | Token đúng được verify, key sai bị từ chối, không dùng private key ở verifier |
| Multi-instance rollout | Pod A/B dùng version khác theo kế hoạch | Không gián đoạn ngoài mức đã duyệt; có kết thúc overlap |
| Revocation khẩn cấp | Credential nghi lộ bị khóa | Request bằng credential cũ thất bại; logs audit ghi sự kiện không lộ secret |

Bộ test Spring Boot ở mục 5 là một phần của bảng: nó chứng minh app bind hash từ property test và xác thực đúng/sai. Những trường hợp hạ tầng cần test/chaos/smoke trong môi trường được phép; **không cố tình revoke production key để thử** mà thiếu change plan.

### Quy tắc QA nội dung bí mật

- Scan source, test fixture, Git history theo chính sách tổ chức; kiểm cả source maps, Docker build layers và CI artifacts.
- Không đưa production secret vào snapshot test hoặc golden file.
- Tạo secrets ngẫu nhiên qua CSPRNG và cấp theo môi trường; demo có thể dùng dữ liệu công khai **chỉ nếu không trùng bất kỳ hệ thống thật**.
- Kiểm rằng app không khởi động khi thiếu secret bắt buộc; failure message không lộ raw secret.
- Kiểm log và error body không chứa password hash, OAuth2 client secret, private key, JWT/Bearer token hoặc API key.
- Kiểm chính sách phiên/expiry, auditing, scope và rotation; không chỉ đánh giá tính bí mật lúc build.

## 16. Sự cố triển khai thường gặp và hướng chẩn đoán

### App báo unresolved placeholder

Ví dụ lỗi ở `app.auth.operator-password-hash`. Kiểm tên biến có đúng, deployment đã inject vào **đúng container/process**, case-sensitivity, YAML quoting và thời điểm khởi động. Không sửa bằng cách thêm default credential yếu. Có thể xem `printenv` **chỉ cho tên biến** bằng cơ chế an toàn; không dump giá trị ra CI log.

### Spring Security trả 401 dù env có giá trị

Có thể hash chưa có prefix `{bcrypt}`, raw password không khớp verifier, tài khoản bị khóa hoặc provider sai. Kiểm ở log an toàn mức boolean: user lookup thành công? hash encoding recognized? password `matches`? Không gửi hash/PasswordEncoder internals ra client. Một bcrypt hash phải được so bằng `matches`, không encode lại candidate rồi so string.

### OAuth2 token endpoint trả invalid_client

Kiểm `client-id`, client-authentication-method, secret version, token URI, encoding, clock/expiry policy và network/TLS. Không in Authorization header hoặc response chứa token. Nếu provider vừa rotate secret, kiểm đồng bộ deployment và khả năng giữ song song credentials cũ/mới.

### JWT signature verification thất bại sau rotate

Kiểm `kid`, JWKS cache, issuer, audience, algorithm, clock skew và thời điểm token phát hành. Resource servers verify bằng public key/JWKS đáng tin; không chia private key chỉ để khắc phục lỗi verify. Nếu dùng symmetric signing, kiểm đúng key version ở tất cả nodes.

### Secret mount tồn tại nhưng app vẫn dùng giá trị cũ

Environment variables không tự đổi trong process khi K8s Secret được cập nhật. File mount cũng không bảo đảm Spring bean tự rebind. Xác định cơ chế rollout/refresh của integration, thời gian cache, lifecycle bean/client và version đang dùng; không thử in key để đối chiếu.

### Khóa giải mã cũ bị mất

Nếu ciphertext được tạo bằng key đã bị xóa, ứng dụng không thể giải mã dù có key mới. Tìm backup/previous key version theo chính sách KMS và khôi phục qua quy trình kiểm soát; đừng chạy script tự thử key dựa trên dữ liệu production không được phép.

## 17. Danh sách kiểm tra trước khi lên production

1. **Inventory:** từng password/client secret/API key/private key/encryption key có owner, scope, môi trường, expiry và rotation plan.
2. **Không hardcode:** repo, history, JAR, image, Dockerfile, frontend bundle, Helm values, CI cache và logs đã được rà soát.
3. **Secret source:** ứng dụng nhận cấu hình từ runtime store/mount/identity; không chứa fallback credential thật hoặc mặc định yếu.
4. **Least privilege:** service account chỉ đọc secret cần dùng, không có quyền list toàn bộ vault/namespace nếu không cần.
5. **TLS/transport:** HTTPS/mTLS đúng bối cảnh; không gửi secrets trong URL/query hoặc insecure channel.
6. **Storage:** secret manager encrypt at rest và có audit; private keys do KMS/HSM quản lý khi phù hợp; backup/restore có kiểm soát.
7. **Validation:** app fail fast với secret thiếu/sai format, exception chỉ báo tên property/loại lỗi.
8. **Authentication:** raw user password không lưu; verifier dùng PasswordEncoder đúng thuật toán/cost; OAuth2 client secret không đi tới browser.
9. **Cryptography:** asymmetric public/private phân biệt đúng; HMAC/AES key đủ entropy; `kid`, audience, issuer, nonce và key version được xử lý.
10. **Rotation:** có overlap/rollout/revoke/rollback, test canary, xử lý tokens/ciphertext cũ và sự cố compromise.
11. **Observability:** logs/Actuator/crash dumps/trace không lộ secrets, error messages không in values, debug access được hạn chế.
12. **CI/CD:** test dùng secrets giả; deploy workload identity hoặc OIDC federation, không ghi credentials vào shell history/artifacts.
13. **Infra:** Kubernetes RBAC, encryption at rest, filesystem permissions, network policies và secret injection được kiểm.
14. **Testing:** các test thiếu secret/credential sai/rotate/permissions/side effects đã có và được chạy qua đường triển khai thực tế.

## 18. Bài tập thực hành và câu hỏi tự kiểm tra

1. Vì sao xóa mật khẩu khỏi commit mới mà **không rotate** credential bị lộ là chưa đủ?
2. Vì sao `{bcrypt}$2b$...` trong user database không đồng nghĩa ứng dụng cần giữ raw password?
3. Tại sao `client-secret` của một OAuth2 confidential client không bao giờ được nhúng trong SPA?
4. Nếu app chạy được ở local nhưng startup thất bại ở Kubernetes vì `APP_OPERATOR_PASSWORD_HASH` không tồn tại, hướng sửa nào bảo mật hơn: cấp secret đúng hay thêm default `changeme`?
5. Với Spring Boot, điểm khác biệt giữa placeholder env, configtree file mount và secret manager SDK là gì? Cái nào tự cập nhật giá trị vào bean đang chạy?
6. Nếu resource server chỉ cần verify RS256 JWT, nó nên có private hay public key? Vì sao?
7. Base64 encoding có đủ để bảo vệ `Kubernetes Secret.data` không? Cần biện pháp nào thêm?
8. Trong app multi-tenant, tại sao mỗi tenant/service nên có credential và scope riêng?
9. Khi rotate JWT signing key, tại sao thường cần giữ public key cũ trong JWKS một thời gian?
10. Với AES-GCM key dùng cho dữ liệu lâu dài, vì sao thay key mới ngay mà xóa key cũ có thể làm mất dữ liệu?
11. Đọc một stack trace cho thấy `invalid_client` nhưng hệ thống đang log raw token response. Cần sửa đồng thời những phần nào?
12. Nếu một Secret volume được cập nhật, vì sao Spring Boot bean có thể vẫn dùng secret cũ cho đến rollout/refresh?
13. Làm sao tạo test chứng minh app fail fast khi thiếu cấu hình mà không đưa production secret vào CI?
14. Vì sao `.gitignore` không bảo vệ file credential đã được Git track trước đó?
15. Nếu hệ thống có KMS signing API, lợi ích nào đến từ việc app không nhận raw private key? Quyền gọi KMS vẫn cần bảo vệ thế nào?

**Kết luận:** không “đưa bí mật vào file cấu hình” rồi coi là xong. Hãy giữ **giá trị bí mật ngoài source và artifact**, nhận qua runtime identity/secret manager hoặc secret mount có quyền hạn, bind/validate qua Spring Boot, ngăn lộ qua log/HTTP/CI, kiểm đúng loại credential và duy trì rotation/revocation. Source code chỉ chứa hợp đồng cấu hình; deployment quyết định **ai được lấy secret nào, lúc nào và bằng cách nào**.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Encryption at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
