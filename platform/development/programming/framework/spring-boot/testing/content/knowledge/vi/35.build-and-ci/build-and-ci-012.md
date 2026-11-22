# Bảo vệ secret, dữ liệu thật và đích kết nối trong môi trường CI

Một lệnh `mvn test` không chỉ chạy các assertions. Khi `@SpringBootTest` khởi tạo `ApplicationContext`, Spring Boot có thể tạo `DataSource`, HTTP clients, Kafka/Redis connections, cloud SDK, schedulers, listeners và chạy script/migrations. Nếu môi trường CI nhận nhầm `SPRING_DATASOURCE_URL`, API key hoặc cloud identity từ môi trường thật, tests có thể **đọc dữ liệu khách hàng, gửi yêu cầu thanh toán/email thật, ghi vào database production hoặc phá schema**. Một build xanh không đủ chứng minh môi trường đã an toàn.

Chủ đề **Bảo vệ secret, dữ liệu thật và đích kết nối trong môi trường CI** thuộc nhóm **Build và CI** của **Spring Boot - testing**. Bài này hướng dẫn tách vùng tin cậy, dùng test-only data và credentials, hiểu precedence của Spring configuration, thiết kế **fail-closed connection allowlist**, kiểm actual connection target, cô lập outbound gateway, quản lý quyền GitHub Actions và viết negative tests. Ví dụ hoàn chỉnh **Java 17 + Spring Boot 3.5.0 + Maven + H2 + JUnit Jupiter** gồm **20 bài `@Test`**; không cần Docker, network hoặc secret thật.

**Nguyên tắc:** không cấp cho test runner những quyền/đích mà nó không cần. Profile `ci` là một lớp cấu hình, **không** phải sandbox chống mọi kết nối. Muốn bảo vệ CI cần đồng thời có **runner isolation, least privilege, data minimization, endpoint allowlist, network egress controls và xác minh runtime**.

## 1. Threat model: tài sản và hành vi cần ngăn

| Loại tài sản | Ví dụ | Rủi ro trong CI |
|---|---|---|
| **Secrets** | DB password, OAuth token, API key, signing key, cloud secret, private certificate | Lộ trong repo, logs, test reports, artifacts, caches, stack trace, HTTP captures |
| **Dữ liệu thật** | PII, giao dịch thanh toán, dữ liệu đơn hàng production, file đính kèm, log khách hàng | Được copy vào fixtures hoặc bị test đọc/sửa, vi phạm quyền riêng tư |
| **Đích kết nối** | JDBC/R2DBC URL, Redis host, Kafka bootstrap servers, HTTP base URL, SMTP, S3 bucket | Test trỏ sai và tác động hệ thống thật |
| **Runner identity** | `GITHUB_TOKEN`, OIDC credentials, IAM role, VPC access, service account | Mã PR chưa review có thể thao tác tài nguyên vượt quyền |
| **Build pipeline** | Maven plugins, GitHub actions, downloaded dependencies, caches | Untrusted code/script có thể đọc secrets hoặc kết nối ra ngoài |

Các lỗi phổ biến:
- Đặt `@ActiveProfiles("ci")` nhưng để `SPRING_DATASOURCE_URL` từ CI runner override `application-ci.properties`.
- Test dùng `@SpringBootTest` nhưng một `@Bean` tự tạo `DataSource`/`HttpClient` không tuân test config.
- Dùng `spring.sql.init.mode=always` hoặc Flyway trên một DB không được nhận diện đúng.
- Trong `pull_request_target`, checkout và chạy mã PR không đáng tin với token có quyền ghi hoặc secrets.
- Test API thanh toán bằng request thật rồi chỉ nhận 200 như một “success”.
- Một bản sao staging có chứa dữ liệu production; tên server khác nhưng tính nhạy cảm của dữ liệu không thay đổi.
- In `System.getenv()`/full HTTP headers/JDBC URL trong log để debug lỗi CI.
- Một số tests có H2, nhưng Kafka producer/email sender vẫn trỏ production.

### Tách ranh giới tin cậy

```text
PR source code (untrusted)
        |
        v
CI job (read-only token; no cloud/prod secrets)
        |
        +-- Spring TestContext with ci profile
        |       |
        |       +-- effective target/credential policy
        |       +-- DataSource: disposable in-memory H2
        |       +-- PartnerGateway: in-memory fake
        |
        +-- JUnit asserts actual beans and JDBC metadata
        +-- synthetic fixtures + scoped cleanup
        |
        v
Network policy: deny production network/metadata/egress
        |
        v
No direct path to production data or credentials
```

**Defense in depth:** guard Java kiểm được **những properties nó biết**, nhưng một dependency mới có thể mở connection qua cấu hình khác; network ACL và absence of credentials cần tồn tại **độc lập** với Spring code.

## 2. Quản lý secret trong build và test

### 2.1. Không lưu secret thật trong repository

Không đưa passwords/API keys vào:
- `src/test/resources/application-test.yml`/`application-ci.properties`.
- `pom.xml`, Maven `settings.xml` đã commit, Dockerfile, Compose, Gradle properties.
- `.github/workflows/*.yml`, hardcoded Java constants, comments, test snapshots.
- Fake customer records, JSON payloads, SQL fixtures và HTTP recordings.
- CLI command có token thực (có thể hiện trong process listing/CI logs).
- `System.out.println(System.getenv())`, `--debug` logs và exception message.

Chỉ mã hóa `Base64` hay chia secret thành vài string literals không biến nó thành an toàn. `.gitignore` chỉ ngăn file chưa tracked; credential đã vào Git history phải được **rotate/revoke**, xem lại logs/artifacts/forks và xử lý incident. Nếu người dùng tải artifact về, việc xóa một file ở commit mới không xóa bản cũ khỏi nơi khác.

### 2.2. Các loại job có quyền khác nhau

| Job | Code được tin? | Quyền nên có |
|---|---|---|
| PR từ fork | Không | Không repo/cloud/prod secrets; `GITHUB_TOKEN` quyền đọc tối thiểu |
| PR từ nhánh nội bộ | Vẫn cần review vì PR có thể sửa test/plugin | Không production secrets; cô lập mạng |
| Push vào protected branch | Tùy chính sách review | Credentials riêng cho tác vụ thực sự cần |
| Deployment approved environment | Trusted sau approval | Short-lived OIDC/cloud identity, scope vào đích riêng |
| Sandbox integration được duyệt | Trusted job, isolated environment | Credentials test-only với TTL, quota, audit |

GitHub Actions `pull_request` từ fork theo default không cấp repository secrets; nhưng không kết luận mọi PR ở mọi repository đều không thể thấy secrets, vì event và thiết lập quyền khác nhau. **Tránh chạy untrusted PR head trong `pull_request_target` có secret hoặc write token**: ngay lệnh `mvn test` có thể chạy mã do PR sửa, bao gồm plugins/scripts/tests. Tách workflow chạy mã chưa được review khỏi workflow privileged.

### 2.3. Chỉ inject credentials khi thực sự cần

Khi cần external sandbox (không có production data), sử dụng:
1. service account/test tenant riêng và **least-privilege**;
2. OIDC/workload identity ngắn hạn có ràng buộc repo/ref/environment và audience;
3. approval/protected environment cho job cần credentials;
4. token expiry/rotation, audit danh tính job;
5. chỉ các host/ports được phép trong network policy;
6. synthetic input và cleanup theo test-run ID;
7. cấm artifact/caches chứa token.

Masking chỉ là **giảm rủi ro hiển thị**: GitHub Actions masking không bảo đảm che secret sau khi bị split, encode, hash hoặc transform. Không đưa secrets vào nơi untrusted code có thể đọc rồi dựa vào mask để ngăn exfiltration.

## 3. Externalized configuration của Spring Boot: vì sao profile không khóa target?

Spring Boot nhận config từ nhiều nguồn: `application.properties/yaml`, profile-specific configs, JVM `-D` system properties, OS environment variables, `SPRING_APPLICATION_JSON`, command-line arguments, `@TestPropertySource`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource` và các custom property sources.

Ví dụ:

```properties
# src/test/resources/application-ci.properties
spring.datasource.url=jdbc:h2:mem:ci_safety;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
app.partner.base-url=http://127.0.0.1:9
```

Nhưng một runner có thể đặt:

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://db.example.invalid:5432/production
```

**OS environment variables thường có precedence cao hơn Config Data**. Bật `@ActiveProfiles("ci")` không ngăn property bị override. Cũng phải xét `spring.datasource.hikari.jdbc-url`, custom `DataSource`, `spring.r2dbc.url`, `spring.kafka.bootstrap-servers`, `spring.data.redis.host`, HTTP client config và cloud SDK configuration. **Không có một property duy nhất thể hiện mọi network destination**.

### 3.1. Những cơ chế test dễ tạo context khác dự kiến

| Cơ chế | Mục đích | Điểm cần kiểm |
|---|---|---|
| `@ActiveProfiles("ci")` | Chọn profile | Không ngăn nguồn property ưu tiên cao override URL |
| `@SpringBootTest(properties=...)` | Đặt test-specific properties | Có thể khác cấu hình trong file; kiểm context thực |
| `@TestPropertySource` | Thay nguồn properties test | Không dùng URL thật cho convenience |
| `@DynamicPropertySource` | Lấy port/URL động (ví dụ Testcontainers) | Lifecycle container và nguồn URL thật |
| `@ServiceConnection` | Tạo `ConnectionDetails` từ container | ConnectionDetails có thể thắng connection properties |
| `@MockitoBean`/test fake | Thay outbound dependency bean | Không chặn code khác tự tạo HTTP client |
| `@Profile("ci")` | Chọn Spring beans theo environment | Phải test bean thực được inject |
| `@ConditionalOnProperty` | Bật/tắt component | Không giả định disabled component đã không gọi bên ngoài qua code khác |

Spring Boot 3.5 có `@ServiceConnection` cho Testcontainers: theo tài liệu, connection details mà nó cung cấp **được ưu tiên hơn** các connection-related properties. Một guard chỉ đọc `spring.datasource.url` **không đủ** nếu ứng dụng dùng đường khác. Với custom `DataSource` hoặc nhiều DB clients, hãy kiểm actual datasource/container/broker identity và chặn outbound network từ runner.

### 3.2. Log lỗi policy phải được sanitize

Không làm:

```java
System.out.println(
    "DB password: " + environment.getProperty(
        "spring.datasource.password"));
```

Đó là snippet anti-pattern, không nằm trong project runnable. Thay vào đó, kiểm policy và ném lỗi cố định:

```java
if (unsafe) {
    throw new IllegalStateException(
            "CI database target rejected");
}
```

Không chèn raw JDBC URL, username/password, token hoặc HTTP Authorization header vào failure message. Khi điều tra incident, log **nhóm config bị từ chối**, job identifier và policy version, không log giá trị bí mật. Assertions có thể vô tình in actual values trong diff, nên với target nhạy cảm phải tránh assert trực tiếp raw string.

## 4. Bảo vệ dữ liệu thật

### 4.1. Chỉ dùng synthetic fixtures

Nên tạo dữ liệu rõ ràng là giả:
- `FAKE-...` làm marker/test-run ID; `UUID` để tránh collision.
- Domains reserved `example.invalid`/`example.test`; không gửi email thật.
- `Clock.fixed(...)`, seeded random hoặc data factories khi cần kết quả deterministic.
- H2 in-memory hoặc Testcontainers database mới và isolated.
- Tenant/account/sandbox riêng, schema/bucket/topic dùng cho test.
- Không lưu dữ liệu nhận dạng cá nhân thật trong Surefire XML, snapshots hoặc traces.

**Pseudonymization không đồng nghĩa anonymization.** Việc thay display name nhưng giữ email, phone, địa chỉ, free-text, internal account ID hoặc liên kết transaction có thể cho phép tái định danh. Một staging server có dữ liệu sao chép từ production vẫn là dữ liệu nhạy cảm. Nếu thực sự cần dữ liệu gần thật, phải có phê duyệt, minimization, redaction được đánh giá, data retention/TTL và quyền truy cập theo tổ chức.

### 4.2. Startup scripts và migrations cũng có thể phá dữ liệu

Các cấu hình nguy hiểm nếu nhầm target:
- Hibernate `spring.jpa.hibernate.ddl-auto=create`, `create-drop` hoặc `update`.
- `spring.sql.init.mode=always` với `schema.sql`/`data.sql`.
- Flyway hoặc Liquibase chạy migrations lúc ApplicationContext refresh.
- Seed scripts/cleanup `TRUNCATE` hoặc `DELETE` không có `WHERE`.
- Scheduler hoặc startup listener tự tạo side effects.

**`spring.sql.init.mode=never` chỉ tắt Spring Boot script-based initialization**, không tự tắt Hibernate schema action, Flyway, Liquibase hoặc business SQL. Đừng lấy một switch đó làm cơ chế chống phá DB thật. Luôn tạo disposable database trước, xác minh target, chỉ sau đó mới chạy migrations/test writes.

### 4.3. Cleanup đúng phạm vi

Test ghi rows nên gắn `run_id`, `reference` giả hoặc tenant key của invocation hiện tại. Query và delete theo `WHERE run_id = ?`, thực thi trong `finally`/`@AfterEach`, và không âm thầm nuốt lỗi cleanup. `@Transactional` có thể rollback khi cùng transaction/thread, nhưng `REQUIRES_NEW`, `@Async`, server thread và external side effects có thể commit độc lập. `@DirtiesContext` không xóa data đã commit ở DB ngoài.

## 5. Bảo vệ các connection targets

| Hệ | Đích có thể vô tình dùng | CI-safe replacement |
|---|---|---|
| JDBC | `spring.datasource.url` | H2 `jdbc:h2:mem` hoặc DB container disposable |
| R2DBC | `spring.r2dbc.url` | Reactive DB container riêng hoặc fake adapter |
| Redis | `spring.data.redis.host/port` | Isolated Redis container/fake |
| Kafka | `spring.kafka.bootstrap-servers` | Testcontainers/embedded broker hoặc fake producer |
| RabbitMQ | `spring.rabbitmq.addresses` | Disposable RabbitMQ/fake |
| SMTP | `spring.mail.host` | Mail capture server hoặc fake sender |
| HTTP APIs | `app.partner.base-url` | In-process fake hoặc mock server trên loopback |
| Cloud SDK | Bucket/account/region/endpoint | Test-only account và short-lived identity |

**Không coi `localhost` tự động là sandbox**: nó có thể là port của dịch vụ khác trong shared runner hoặc container namespace. Nếu dùng network mock, khởi tạo mock server và inject đúng port/identity. Trong project mẫu dưới đây, `http://127.0.0.1:9` chỉ là **sentinel chưa được gọi**; CI profile sử dụng fake bean không có HTTP client. Không dựa vào việc port 9 thường không mở để “bảo vệ” hệ thống.

## 6. Project runnable: Java 17 + Spring Boot 3.5 + JUnit

Thiết kế mẫu:
1. `application-ci.properties` chỉ trong `src/test/resources`, kết nối H2 in-memory.
2. `CiDestinationPolicy` nhận **resolved values** và kiểm exact allowlist cho database/partner/credentials.
3. `CiStartupGuard` là `BeanFactoryPostProcessor` dưới profile `ci`, fail closed **trước khi khởi tạo datasource singleton thông thường** trong sample.
4. `FakePartnerGateway` được chọn trong CI; `HttpPartnerGateway` chỉ có khi `!ci`.
5. `CiProbeService` chỉ cho phép markers `FAKE-...` và ghi bảng test `ci_probe`.
6. Pure unit tests kiểm guard negative cases; integration tests xác nhận **actual JDBC metadata**, bean selection, data fake và cleanup.

### 6.1. Cây thư mục

```text
ci-safety-demo/
├── pom.xml
├── .github/workflows/safe-ci.yml
└── src/
    ├── main/java/com/example/cisafety/
    │   ├── CiSafetyApplication.java
    │   ├── CiDestinationPolicy.java
    │   ├── CiStartupGuard.java
    │   ├── PartnerGateway.java
    │   ├── FakePartnerGateway.java
    │   ├── HttpPartnerGateway.java
    │   ├── ProbeReceipt.java
    │   └── CiProbeService.java
    └── test/
        ├── java/com/example/cisafety/
        │   ├── CiDestinationPolicyTest.java
        │   └── CiSafetyIntegrationTest.java
        └── resources/
            ├── application-ci.properties
            └── schema-ci.sql
```

Ngoài profile `ci`, deployment cần cung cấp credentials/data source theo chính sách production, không có mật khẩu/host thật trong source. Mẫu `HttpPartnerGateway` được biên dịch, nhưng không được tạo trong CI tests.

### 6.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>ci-safety-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <!-- H2 dùng trong test; không package vào production runtime. -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
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
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate`, DataSource và HikariCP; H2 `test` scope chỉ có trong test classpath. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và Spring TestContext. Spring Boot parent quản lý các phiên bản tương thích. Sample không cần Docker hoặc internet khi các dependencies đã được Maven tải.

### 6.3. Boot application

File **`src/main/java/com/example/cisafety/CiSafetyApplication.java`**:

```java
package com.example.cisafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiSafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiSafetyApplication.class, args);
    }
}
```

### 6.4. Destination policy với lỗi đã redact

File **`src/main/java/com/example/cisafety/CiDestinationPolicy.java`**:

```java
package com.example.cisafety;

public final class CiDestinationPolicy {

    public static final String CI_DB_URL =
            "jdbc:h2:mem:ci_safety;"
            + "DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE";

    public static final String CI_PARTNER_URL =
            "http://127.0.0.1:9";

    private CiDestinationPolicy() {
    }

    public static void verify(
            String jdbcUrl,
            String username,
            String password,
            String partnerUrl,
            String partnerApiKey) {

        if (!CI_DB_URL.equals(jdbcUrl)) {
            throw new IllegalStateException(
                    "CI database target rejected");
        }

        if (!"sa".equals(username)
                || password == null
                || !password.isEmpty()) {
            throw new IllegalStateException(
                    "CI database credentials rejected");
        }

        if (!CI_PARTNER_URL.equals(partnerUrl)) {
            throw new IllegalStateException(
                    "CI outbound target rejected");
        }

        if (partnerApiKey != null
                && !partnerApiKey.isBlank()) {
            throw new IllegalStateException(
                    "CI external credential rejected");
        }
    }
}
```

**Vì sao exact allowlist?** Chỉ kiểm `jdbcUrl.startsWith("jdbc:h2:mem:")` có thể bỏ qua URL H2 khác tùy chọn `INIT`. Mẫu chỉ chấp nhận đúng một JDBC URL, username `sa`/password rỗng, partner sentinel và **không có** API key. PostgreSQL/MySQL, H2 file/TCP và mọi biến thể ngoài allowlist đều bị reject. Trong app có nhiều containers/DBs hợp lệ, policy phải định nghĩa **nhóm đích được cấp phép** thay vì chỉ hardcode một URL; vẫn phải giữ fail closed.

Exception messages của policy chỉ nói **nhóm config**, không in chuỗi URL, username, password hay token được đưa vào. Đây là một yêu cầu thực tế khi xét log bảo mật.

### 6.5. Kiểm effective properties trước khi khởi tạo singleton DataSource

File **`src/main/java/com/example/cisafety/CiStartupGuard.java`**:

```java
package com.example.cisafety;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
@Profile("ci")
public class CiStartupGuard {

    @Bean
    static BeanFactoryPostProcessor requireSafeCiTargets() {
        return beanFactory -> {
            Environment env = beanFactory.getBean(Environment.class);

            CiDestinationPolicy.verify(
                    env.getProperty("spring.datasource.url"),
                    env.getProperty("spring.datasource.username"),
                    env.getProperty("spring.datasource.password"),
                    env.getProperty("app.partner.base-url"),
                    env.getProperty("app.partner.api-key"));
        };
    }
}
```

`BeanFactoryPostProcessor` được Spring chạy khi xử lý bean definitions trước việc tạo application singletons thông thường. Static `@Bean` tránh instantiate configuration class quá sớm. Khi CI environment chứa `SPRING_DATASOURCE_URL` sai hoặc `APP_PARTNER_APIKEY` không rỗng, context phải **FAIL** thay vì tiếp tục tạo DataSource của mẫu.

**Giới hạn rõ ràng:** một custom BeanFactoryPostProcessor, `DataSource` tự xây, Testcontainers `@ServiceConnection` hoặc outbound call trước giai đoạn này có thể nằm ngoài guard. Không suy đây là sandbox cho một Spring application bất kỳ; cần chặn egress và không cấp production secrets ở cấp runner. Integration test còn phải kiểm **actual connection** để phát hiện cấu hình bị thay thế.

### 6.6. Gateway interface và fake implementation

File **`src/main/java/com/example/cisafety/PartnerGateway.java`**:

```java
package com.example.cisafety;

public interface PartnerGateway {
    String acknowledge(String marker);
}
```

File **`src/main/java/com/example/cisafety/FakePartnerGateway.java`**:

```java
package com.example.cisafety;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("ci")
public class FakePartnerGateway implements PartnerGateway {

    @Override
    public String acknowledge(String marker) {
        return "SIMULATED:" + marker;
    }
}
```

Fake `@Profile("ci")` **không có HTTP client**. Khi unit/integration tests gọi business service, kết quả được tạo trong JVM, không có đường code gửi request tới server bên ngoài. Cách này an toàn hơn việc dùng production implementation nhưng trỏ về một host lỗi, vì production implementation có thể redirect/retry/resolve DNS ngoài ý muốn.

### 6.7. HTTP gateway ở chế độ không-CI

File **`src/main/java/com/example/cisafety/HttpPartnerGateway.java`**:

```java
package com.example.cisafety;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("!ci")
public class HttpPartnerGateway implements PartnerGateway {

    private final HttpClient client = HttpClient.newHttpClient();
    private final URI endpoint;
    private final String apiKey;

    public HttpPartnerGateway(
            @Value("${app.partner.base-url}") String baseUrl,
            @Value("${app.partner.api-key}") String apiKey) {
        this.endpoint = URI.create(baseUrl);
        this.apiKey = apiKey;

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null
                || endpoint.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Partner endpoint must use HTTPS host");
        }
    }

    @Override
    public String acknowledge(String marker) {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(3))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "text/plain")
                .POST(HttpRequest.BodyPublishers.ofString(
                        marker, StandardCharsets.UTF_8))
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                        "Partner returned non-success status");
            }
            return response.body();
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Partner request failed", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Partner request interrupted", ex);
        }
    }
}
```

Lớp này chỉ xuất hiện khi **không có profile ci**. Nó cho thấy secrets phải đến từ **external configuration**, không hardcode; khi thiếu `app.partner.api-key`, ứng dụng non-ci không nên âm thầm thay bằng key mặc định. Trong production phải thêm TLS/server identity, host allowlist, DNS/redirect/SSRF policy, retry và token management phù hợp; check `https` ở đây **chưa đủ** để cho phép kết nối mọi host. CI tests xác nhận bean này **không được đăng ký**.

### 6.8. Test-only probe và receipt

File **`src/main/java/com/example/cisafety/ProbeReceipt.java`**:

```java
package com.example.cisafety;

public record ProbeReceipt(String id, String acknowledgment) {
}
```

File **`src/main/java/com/example/cisafety/CiProbeService.java`**:

```java
package com.example.cisafety;

import java.util.UUID;

import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
@Profile("ci")
public class CiProbeService {

    private final JdbcTemplate jdbc;
    private final PartnerGateway partner;

    public CiProbeService(
            JdbcTemplate jdbc, PartnerGateway partner) {
        this.jdbc = jdbc;
        this.partner = partner;
    }

    public ProbeReceipt recordSynthetic(String marker) {
        if (marker == null
                || !marker.matches("FAKE-[A-Z0-9-]{1,40}")) {
            throw new IllegalArgumentException(
                    "Synthetic marker required");
        }

        String id = "ci-" + UUID.randomUUID();
        jdbc.update(
                "INSERT INTO ci_probe (id, marker) VALUES (?, ?)",
                id, marker);

        return new ProbeReceipt(id, partner.acknowledge(marker));
    }
}
```

Service chỉ hiện diện trong CI profile; input phải bắt đầu `FAKE-`. Nó ghi bảng `ci_probe` và gọi fake `PartnerGateway`. Mã được dùng để kiểm **synthetic data + scoped cleanup**, không phải chức năng giao dịch production.

### 6.9. Test-only properties và schema

File **`src/test/resources/application-ci.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:ci_safety;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema-ci.sql

# Chỉ là sentinel, FakePartnerGateway không gọi network.
app.partner.base-url=http://127.0.0.1:9
```

File **`src/test/resources/schema-ci.sql`**:

```sql
CREATE TABLE ci_probe (
    id VARCHAR(80) PRIMARY KEY,
    marker VARCHAR(80) NOT NULL
);

CREATE INDEX idx_ci_probe_marker
    ON ci_probe(marker);
```

Dữ liệu và script chỉ có trên test classpath. `spring.sql.init.mode=always` an toàn **trong mẫu có target guard H2**, nhưng chính property này là rủi ro nếu copy sang context trỏ tới DB thật. Đừng dùng `@DirtiesContext` như cách cleanup database ngoài. Với nhiều tests/contexts có cùng H2 name, cần quản lý lifecycle và isolate DB names, hoặc dùng Testcontainers disposable.

### 6.10. Pure unit tests: từ chối URL và credentials lạ

File **`src/test/java/com/example/cisafety/CiDestinationPolicyTest.java`**:

```java
package com.example.cisafety;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CiDestinationPolicyTest {

    private static void check(
            String db, String user, String password,
            String partner, String apiKey) {
        CiDestinationPolicy.verify(
                db, user, password, partner, apiKey);
    }

    @Test
    void exactCiTargetsWithoutSecretAreAccepted() {
        assertThatCode(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .doesNotThrowAnyException();
    }

    @Test
    void missingDatabaseUrlIsRejected() {
        assertThatThrownBy(() -> check(
                null, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected");
    }

    @Test
    void postgresUrlIsRejectedBeforeConnecting() {
        assertThatThrownBy(() -> check(
                "jdbc:postgresql://db.example.invalid:5432/prod",
                "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected");
    }

    @Test
    void fileBasedH2IsRejected() {
        assertThatThrownBy(() -> check(
                "jdbc:h2:file:./test-db",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void tcpH2ServerIsRejected() {
        assertThatThrownBy(() -> check(
                "jdbc:h2:tcp://127.0.0.1:9092/testdb",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void additionalH2InitOptionsAreRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL
                    + ";INIT=CREATE SCHEMA X",
                "sa", "", CiDestinationPolicy.CI_PARTNER_URL,
                null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void unexpectedDatabaseUsernameIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "not-sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database credentials rejected");
    }

    @Test
    void nonemptyDatabasePasswordIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "dummy-secret",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database credentials rejected");
    }

    @Test
    void remotePartnerUrlIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                "https://api.example.invalid", null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI outbound target rejected");
    }

    @Test
    void differentLoopbackPortIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                "http://127.0.0.1:8080", null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void unexpectedPartnerApiKeyIsRejected() {
        assertThatThrownBy(() -> check(
                CiDestinationPolicy.CI_DB_URL, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL,
                "synthetic-token"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI external credential rejected");
    }

    @Test
    void errorDoesNotPrintConnectionString() {
        String suspicious =
                "jdbc:postgresql://db.example.invalid/sensitive";
        assertThatThrownBy(() -> check(
                suspicious, "sa", "",
                CiDestinationPolicy.CI_PARTNER_URL, null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("CI database target rejected")
                .hasMessageNotContaining("sensitive");
    }
}
```

**12 `@Test`**: một positive path và negative tests cho missing URL, Postgres/H2 file/H2 TCP, H2 extra init options, user/password lạ, remote endpoint, port khác, injected token và sanitized error message. Các URLs/keys trong test đều giả, không có tên host hay credential thật.

### 6.11. Spring integration tests: actual DataSource, fake và cleanup

File **`src/test/java/com/example/cisafety/CiSafetyIntegrationTest.java`**:

```java
package com.example.cisafety;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.Locale;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("ci")
class CiSafetyIntegrationTest {

    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private PartnerGateway partner;

    @Autowired
    private CiProbeService probe;

    @Test
    void ciProfileIsActive() {
        assertThat(environment.acceptsProfiles(
                Profiles.of("ci"))).isTrue();
    }

    @Test
    void actualConnectionPointsToH2Memory()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .startsWith("jdbc:h2:mem:ci_safety");
            assertThat(connection.getMetaData()
                    .getDatabaseProductName()).isEqualTo("H2");
        }
    }

    @Test
    void fakeGatewayIsTheOnlySelectedImplementation() {
        assertThat(partner)
                .isInstanceOf(FakePartnerGateway.class);
        assertThat(partner.acknowledge("FAKE-OK"))
                .isEqualTo("SIMULATED:FAKE-OK");
    }

    @Test
    void productionHttpGatewayIsAbsent() {
        assertThat(context.getBeansOfType(
                HttpPartnerGateway.class)).isEmpty();
    }

    @Test
    void resolvedSettingsAreVerified() {
        CiDestinationPolicy.verify(
                environment.getProperty("spring.datasource.url"),
                environment.getProperty("spring.datasource.username"),
                environment.getProperty("spring.datasource.password"),
                environment.getProperty("app.partner.base-url"),
                environment.getProperty("app.partner.api-key"));
    }

    @Test
    void syntheticRowIsInsertedAndCleaned() {
        String marker = "FAKE-"
                + UUID.randomUUID().toString()
                    .replace("-", "")
                    .substring(0, 12)
                    .toUpperCase(Locale.ROOT);
        try {
            ProbeReceipt receipt = probe.recordSynthetic(marker);
            assertThat(receipt.id()).startsWith("ci-");
            assertThat(receipt.acknowledgment())
                    .isEqualTo("SIMULATED:" + marker);

            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker);
            assertThat(count).isEqualTo(1L);
        } finally {
            jdbc.update(
                "DELETE FROM ci_probe WHERE marker = ?",
                marker);
        }
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker)).isZero();
    }

    @Test
    void nonSyntheticMarkerCannotInsert() {
        String marker = "person@example.invalid";
        assertThatThrownBy(() ->
                probe.recordSynthetic(marker))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_probe WHERE marker = ?",
                Long.class, marker)).isZero();
    }

    @Test
    void apiKeyIsAbsentFromCiEnvironment() {
        assertThat(environment.getProperty(
                "app.partner.api-key")).isNull();
    }
}
```

**8 `@Test`**: profile, actual JDBC URL + DB engine, fake bean, absence of production HTTP bean, resolved settings, synthetic insert/cleanup, nonfake marker rejected và API key absent. **12 unit + 8 integration = 20 tests**.

Ở demo, actual JDBC URL là synthetic H2 nên test có thể assert trực tiếp. Trong dự án có secret hoặc hostname nhạy cảm, assertion frameworks có thể hiển thị actual values khi fail: viết helper so boolean/đưa **sanitized failure reason**, không in connection URL hoặc credentials vào CI logs. **Kiểm actual connection chỉ khi runner đã bị cô lập và guard đã cho phép**; không mở network tới production rồi mới xác định rằng nó là production.

### 6.12. GitHub Actions workflow không nhận production secret

File **`.github/workflows/safe-ci.yml`**:

```yaml
name: Isolated Spring tests

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SPRING_PROFILES_ACTIVE: ci
      MAVEN_OPTS: -Dfile.encoding=UTF-8

    steps:
      - name: Checkout without persistent credentials
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run isolated tests
        run: mvn --batch-mode --no-transfer-progress test
```

Job không tham chiếu `secrets.*`, không xin `id-token: write`, không dùng `pull_request_target`, không deploy và không có migration command tới database thật. `GITHUB_TOKEN` ở mức `contents: read`. **YAML không tự tạo sandbox network**: GitHub-hosted runners nói chung có thể truy cập Internet; production network/identity cần bị cấm độc lập. Self-hosted runners càng cần ephemeral isolation, không giữ credentials/containers từ job khác và không đứng trực tiếp trong VPC production khi chạy untrusted PR.

`actions/checkout@v4`/`actions/setup-java@v4` trong snippet là major-version tags phục vụ bài học, không phải commit SHA pinning. CI production nên dùng các versions còn được duy trì và pin actions vào SHA đã review khi chính sách yêu cầu, đồng thời kiểm Maven plugins/dependencies.

### 6.13. Chạy Maven, điều mong đợi

Từ thư mục chứa POM, với JDK 17+ và Maven:

```bash
mvn --batch-mode --no-transfer-progress test
mvn -Dtest=CiDestinationPolicyTest test
mvn -Dtest=CiSafetyIntegrationTest test
```

Kỳ vọng **20 JUnit tests PASS** trong môi trường không có override ngoài ý muốn. Không cần Docker hay endpoint HTTP. Khi CI runner chứa `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_PASSWORD`, `APP_PARTNER_BASEURL` hoặc `APP_PARTNER_APIKEY` lạ, guard **cố tình từ chối startup**; đó là tín hiệu để sửa cấu hình/quyền runner, **không xóa guard cho build xanh**.

Ví dụ được rà soát theo Spring Boot 3.5 và Java 17, **không phải khẳng định đã thực thi Maven**. Không có stdout cố định vì Maven/Spring logs thay đổi theo môi trường. Khi áp dụng vào hệ thống thật, mở rộng policy cho mọi datasource, cloud SDK, Kafka/Redis, HTTP/SMTP destinations và thử trên runner không có production network/credentials.

## 7. Những phép kiểm bổ sung không có trong sample

### 7.1. Production credentials không xuất hiện trong runner

Đừng chỉ test một property `app.partner.api-key` rồi tuyên bố mọi secret đã biến mất. Những credentials khác có thể có tên `AWS_SECRET_ACCESS_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, kubeconfig, Maven registry tokens, file credentials hoặc instance metadata endpoint. Chính sách runner cần **không gắn secret mounts/role** cho job PR, chặn đường đến metadata endpoints và hạn chế quyền cloud IAM.

### 7.2. Kiểm external data store và broker

Nếu application có:
- Kafka producer: dùng fake/embedded broker/Testcontainers; kiểm `bootstrap.servers`, topic prefix và credentials.
- Redis: test-only Redis container, namespace key theo run ID, TTL và cleanup.
- Email: fake `JavaMailSender` hoặc mail capture server; không gửi tới khách hàng thật.
- HTTP: WireMock/MockWebServer hoặc fake gateway; kiểm request payload và **no outbound real host**.
- R2DBC: kiểm `ConnectionFactory` thực sự trỏ đúng container/H2 reactive target khi có.
- Object storage: disposable bucket/account, không cho phép production delete/list bucket.
- Scheduled jobs: vô hiệu ở CI nếu không phục vụ test, vì có thể chạy **khi context startup**, trước body JUnit test.

Mock `@MockitoBean` chỉ thay **một Spring bean cụ thể**: không ngăn code khác tự tạo `HttpClient`/`new KafkaProducer`. Dùng egress deny ngoài JVM để hỗ trợ.

### 7.3. Testcontainers và @ServiceConnection

Khi cần SQL semantics PostgreSQL thật, dùng container disposable:

```java
// Snippet thiết kế: cần Testcontainers dependencies, Docker,
// imports và assertions phù hợp; không thuộc runnable demo.
@Testcontainers
@SpringBootTest
class PostgresSandboxTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot 3.5 yêu cầu `spring-boot-testcontainers` để sử dụng `@ServiceConnection`; đồng thời cần modules Testcontainers PostgreSQL, JUnit integration và PostgreSQL JDBC driver. Không dùng production URL/credentials để tiện chạy test. `@ServiceConnection` có thể được ưu tiên hơn connection-related properties, nên kiểm **container identity/actual connection**. Nếu container không chạy hoặc dùng sai image/tag, test nên fail, không fallback sang DB ngoài.

Container lifecycle phải phù hợp Spring TestContext cache; không dùng container đã stop với cached DataSource. Pin image version/digest theo supply-chain policy khi triển khai CI.

### 7.4. Không để test reports thành kênh leak

Các file có thể lộ secrets/data thật: Maven Surefire XML, screenshots, logs, request/response snapshots, heap dumps, HTTP recordings, SQL debug và cloud traces. Dùng synthetic data, hạn chế logging, không upload artifacts chứa secrets, áp retention ngắn, kiểm quyền tải artifacts và audit. Đừng dùng GitHub masking như biện pháp duy nhất khi assertion failure có thể hiển thị cả string đã bị encode/transform.

## 8. Khi cần integration với sandbox bên ngoài

Có test không thể thay bằng H2 hoặc mock: PostgreSQL locks/index behavior, TLS/mTLS, IAM permissions, Kafka partition ordering, provider-specific APIs. Nhưng **không cần production data/secret** nếu thiết kế đúng:

1. Sandbox/test account tách biệt, không chứa dữ liệu khách hàng.
2. Resource names theo `test-run-id`/namespace với TTL.
3. Job chỉ chạy từ code đã review, có protected environment/approval khi cần credential.
4. OIDC short-lived credentials, least privilege, network allowlist theo sandbox identity.
5. Test synthetic input và test users; không gửi email/tiền thật.
6. Timeout, retry bounds, idempotency key, explicit cleanup và audit.
7. Verify target không chỉ bằng URL mà bằng **account/project/tenant/namespace identity**.
8. Không dùng shared staging có production snapshot để chạy destructive migrations.
9. Giới hạn quota/rate để không gây tải hoặc chi phí ngoài dự kiến.
10. Tách smoke test read-only khỏi data-changing contract tests.

Staging là **một môi trường**, không phải khẳng định dữ liệu ở đó đã được anonymize. Một host staging vẫn có thể chứa production PII, backups hoặc copied tokens.

## 9. Ma trận các lỗi và hành động

| Trường hợp | Dấu hiệu | Cách xử lý |
|---|---|---|
| CI thấy `SPRING_DATASOURCE_URL` lạ | Guard báo database target rejected | Loại override, kiểm secret injection, không thử connect |
| H2 file hoặc TCP thay H2 mem | URL không match exact allowlist | Dùng in-memory disposable hoặc container test |
| Test SQL startup chạy schema thật | DDL/migration bị áp ở sai DB | Verify before init, network/permission deny, isolated DB |
| Partner API key được injected vào PR job | Guard báo credential rejected | Thu hồi quyền secret ở untrusted job |
| `HttpPartnerGateway` được nạp trong ci profile | Bean selection test FAIL | Kiểm profiles/component scan, fake config |
| Có H2 nhưng Kafka vẫn phát đi | Broker config ngoài policy | Fake/isolated broker và egress deny |
| `@ServiceConnection` đổi actual DataSource | Property check PASS nhưng metadata khác | Verify ConnectionDetails/actual engine/identity |
| Test chỉ PASS khi có production network | Unit fixture sai/thiếu fake | Chuyển sang sandbox/test double |
| JDBC rollback không dọn data | `REQUIRES_NEW`, async hoặc server thread | Scoped cleanup/isolated DB |
| Surefire logs chứa headers/token | CI artifact leak | Sanitize, revoke exposed tokens, hạn chế upload |
| PR job dùng `pull_request_target` + untrusted checkout | Privilege boundary bị phá | Chuyển sang pull_request; tách privileged job |
| Runner self-hosted giữ credentials | Mã untrusted có thể lấy identity | Ephemeral isolation, remove mounts, no prod VPC |
| Secret được xóa khỏi HEAD nhưng vẫn trong history | Credential vẫn có thể dùng được | Rotate/revoke và incident review |
| Production JDBC URL bị in trong assertion diff | Lộ host/tên DB | Chỉ log sanitized policy code |
| Bật mọi Actuator endpoint trong CI để debug | Có thể lộ env/credentials | Allowlist exposure và role |
| Dùng Docker `latest` không pin | Build khó tái lập/supply chain risk | Pin version/digest và review |
| Bật `@DirtiesContext` sau mỗi test | Tốn thời gian, không xóa external data | Cleanup theo run ID, proper fixture lifecycle |

## 10. Checklist bảo vệ CI

- [ ] Tôi đã liệt kê mọi secrets, real-data sources và network destinations của app.
- [ ] Job chạy mã PR không nhận production secrets, write token hoặc cloud identity.
- [ ] CI workflow có least-privilege permissions và không chạy untrusted code trong `pull_request_target` privileged workflow.
- [ ] Không hardcode credential/hostname production trong Java, YAML, POM hoặc test resources.
- [ ] Không copy production data vào snapshots/fixtures/traces.
- [ ] `application-ci.properties` chỉ chứa synthetic H2 và sentinel endpoint.
- [ ] Tôi hiểu Spring configuration precedence: environment/system/test/dynamic sources có thể override file.
- [ ] Guard chạy trước creation của DataSource thông thường và fail closed với URL/credentials lạ.
- [ ] Exception/failure message không echo secrets/raw URLs.
- [ ] Test xác minh actual JDBC engine/URL **trên môi trường đã cô lập**.
- [ ] Test bean gateway fake được inject và production outbound gateway không xuất hiện trong CI.
- [ ] Không quên Kafka, Redis, R2DBC, email, cloud SDK hoặc startup schedulers.
- [ ] H2 không dùng file/TCP/extra INIT trừ khi đã được policy duyệt.
- [ ] Flyway/Liquibase/JPA DDL và SQL scripts chỉ chạy trên disposable DB.
- [ ] Test inputs/rows đều synthetic; cleanup chỉ xóa dữ liệu của test.
- [ ] Parallel tests không dùng global truncate hoặc shared mutable state.
- [ ] `@Transactional` không được coi là rollback tất cả external operations.
- [ ] Testcontainers dùng test-only resources, không fallback production credentials.
- [ ] `@ServiceConnection`/custom DataSource/ConnectionFactory được kiểm actual endpoint/identity.
- [ ] Network egress firewall/runner isolation cấm production access độc lập với Java guard.
- [ ] Không dùng logs và masking làm biện pháp bảo vệ credential duy nhất.
- [ ] CI artifacts, Surefire XML, caches và captures được kiểm dữ liệu nhạy cảm/retention.
- [ ] Privileged sandbox integration chạy riêng với approval, short-lived OIDC identity và audit.
- [ ] Test chạy lại nhiều lần không để residue hoặc side effects ở external systems.
- [ ] Khi guard fail, sửa cấu hình/secret scope thay vì xóa test hoặc bypass policy.

**Kết luận:** bảo vệ CI cần chặn cả **bí mật**, **dữ liệu thật** và **đích kết nối**. Hãy dùng data tổng hợp, DB/container disposable, fake outbound services, policy xác nhận resolved config, integration assertions về actual clients, và runner/network không có đường tới production. **Một test FAIL trước khi kết nối sai là kết quả bảo vệ đúng đắn.** Không đánh đổi chính sách này để nhận một build xanh giả.

### Nguồn tham khảo chính thức

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — Testcontainers and @ServiceConnection](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [GitHub Actions — Secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [GitHub Actions — Compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners)
