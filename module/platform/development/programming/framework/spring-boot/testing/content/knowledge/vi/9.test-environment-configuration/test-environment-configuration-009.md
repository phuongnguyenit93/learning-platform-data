# Tách cấu hình kiểm thử khỏi secret và dịch vụ production trong Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm kiến thức:** Cấu hình môi trường test  
> **Trọng tâm:** Test phải dùng cấu hình có thể kiểm soát, dữ liệu giả và hạ tầng cô lập. Không để một lần chạy JUnit vô tình gọi API production, sửa database thật hoặc làm lộ credentials.

## 1. Vì sao tách môi trường test là yêu cầu an toàn, không chỉ là tiện lợi?

Một bài test có thể “xanh” nhưng vẫn gây tác hại nếu nó dùng nhầm môi trường:

- `@SpringBootTest` nạp toàn bộ `ApplicationContext` rồi khởi tạo client sử dụng URL production do environment variable kế thừa từ máy lập trình viên.
- Một integration test gọi `repository.deleteAll()` trên database thật vì dùng chung `spring.datasource.url`.
- Test gửi email/SMS thanh toán tới khách hàng thật vì gateway được tạo từ cấu hình của ứng dụng đang chạy.
- CI xuất giá trị `API_TOKEN` hoặc JDBC password vào test report, assertion failure, log HTTP hoặc artifact.
- Test phụ thuộc dịch vụ production nên chậm, lúc pass lúc fail, bị rate-limit hoặc tạo tài nguyên mất tiền.
- Developer bật profile `test` nhưng một component đọc `System.getenv("PROD_API_URL")` trực tiếp, bỏ qua mọi cấu hình Spring.

**Mục tiêu đúng:** test phải **mặc định an toàn** (*fail closed*), chạy với tài nguyên cô lập và secrets giả/credential chỉ dành cho môi trường test. Khi cần tương tác dịch vụ thật, đó là bài kiểm thử riêng trên **sandbox/staging** với quyền, account và dữ liệu riêng; không dùng production làm nơi thử lỗi.

Ba trục cần tách đồng thời:

| Trục | Test nên sử dụng | Production sử dụng | Nếu không tách |
| --- | --- | --- | --- |
| **Cấu hình** | Profile `test`, properties trong `src/test/resources`, overrides tường minh | Profile `prod`, external config riêng | Test nạp sai URL/timeout/flag |
| **Bí mật** | Không có secret thật, hoặc test-only secret giới hạn quyền và TTL | Secret store, IAM role, vault/secret manager | Lộ key hoặc test có quyền production |
| **Dịch vụ và dữ liệu** | Mockito fake, mock HTTP, DB in-memory, Testcontainers, sandbox account | DB thật, payment/email/broker/live API | Test tạo/sửa/xóa dữ liệu thật |

**Chỉ chọn `@ActiveProfiles("test")` là chưa đủ để đảm bảo an toàn tuyệt đối.** Nó giúp chọn bean và config theo profile, nhưng không thay thế kiểm soát egress, least privilege, test-safe defaults, dependency injection và kiểm tra endpoint được sử dụng.

## 2. Hiểu các lớp cấu hình Spring Boot

Spring Boot hỗ trợ cấu hình ngoài mã nguồn (*externalized configuration*) qua `application.yml`, `application-{profile}.yml`, environment variables, JVM system properties, command-line arguments và cơ chế test properties.

Ví dụ cách tổ chức hợp lý:

```text
src/
├── main/
│   ├── java/                          # Mã được đóng gói vào ứng dụng
│   └── resources/
│       ├── application.yml            # Chỉ giá trị mặc định an toàn/chung
│       └── application-prod.yml       # Tên property + placeholder secret
└── test/
    ├── java/                          # Test, fake, @TestConfiguration
    └── resources/
        └── application-test.yml       # Test-only, không có secret production
```

### 2.1. Vai trò của từng file

- **`application.yml`:** tên ứng dụng, cấu hình chung không nhạy cảm, không có URL production hoặc mật khẩu. Nếu chưa biết môi trường nào hợp lệ, **không đặt production làm mặc định**.
- **`application-prod.yml`:** các property chỉ áp dụng khi profile `prod` được kích hoạt, nên chứa **tham chiếu** tới biến môi trường/secret manager, không chứa giá trị bí mật thật.
- **`src/test/resources/application-test.yml`:** cấu hình dành cho test classpath; ưu tiên in-memory/ephemeral services, fake client hoặc test-only endpoints. File này không đi vào build artifact chính theo cấu hình Maven/Gradle chuẩn.
- **`@ActiveProfiles("test")`:** chọn profile `test` khi Spring TestContext nạp context cho test class.
- **`@TestConfiguration`, `@Import`, `@MockitoBean`:** thay dependency ngoài bằng test double rõ ràng. `@ActiveProfiles` chọn config; test doubles **thực sự ngăn code gọi production adapter**.

**Điểm cần nhớ:** Profile quyết định **cấu hình và bean nào được chọn**; không quyết định mạng có bị chặn hay không. Một bean vẫn có thể gọi địa chỉ ngoài nếu cấu hình của nó cho phép.

### 2.2. Tác dụng của `@ActiveProfiles`

```java
@SpringBootTest
@ActiveProfiles("test")
class ExampleIntegrationTest {
    // Context dùng profile test theo Spring TestContext.
}
```

Đoạn trên minh họa annotation trong một test class, cần imports tương ứng và một Spring Boot application hợp lệ để chạy. Khi sử dụng `@ActiveProfiles("test")`, Spring TestContext xác định active profiles từ annotation (và quy tắc inheritance/resolver của nó). **`SPRING_PROFILES_ACTIVE` không tự thay thế giá trị annotation này** trong cách phân giải profile mặc định của TestContext; nhưng các nguồn cấu hình khác, profile include/group và custom resolver vẫn cần được kiểm tra theo ứng dụng.

Nếu người dùng **chủ động** kích hoạt nhiều profile, ví dụ `test,prod`, những bean `@Profile("prod")` có thể được tạo. Đừng coi tên file test là cơ chế chặn mọi trường hợp phối hợp profile.

### 2.3. Tránh nhầm thứ tự ưu tiên properties

Các property sources có quy tắc ưu tiên; **giá trị từ nguồn ưu tiên cao hơn có thể override file YAML**. Ví dụ command-line arguments hoặc cấu hình test chuyên biệt có thể ghi đè một property lấy từ `application.yml`. Vì vậy:

- Đừng cố tình để `application.yml` trỏ tới production rồi hy vọng `application-test.yml` luôn override.
- Trong integration test, có thể dùng `@SpringBootTest(properties = "...")` hoặc `@TestPropertySource` cho giá trị test-only cục bộ.
- `@DynamicPropertySource` phù hợp khi địa chỉ/port chỉ được biết sau khi container hoặc mock server được khởi động.
- Luôn quan sát **effective URL/bean type** trong test khi an toàn của kết nối là yêu cầu trọng yếu; không dựa vào việc file có tên `application-test.yml`.
- Tránh ghi `spring.profiles.active` bên trong chính file `application-test.yml`/`application-prod.yml`: Spring Boot yêu cầu active/default profile chỉ được khai báo ở các tài liệu **không đặc thù profile**.

Phần tiếp theo xây một dự án mẫu mà test **không biết production token** và không thể gọi production HTTP adapter qua cổng nghiệp vụ.

## 3. Dự án Java 17 / Spring Boot 3.5: thay adapter thật bằng fake trong test

Bối cảnh: `RegistrationService` đăng ký email và phải yêu cầu gửi tin nhắn chào mừng qua `NotificationGateway`.

- Trong production, adapter HTTP gửi request với bearer token.
- Trong local, adapter no-op, không phát sinh mạng.
- Trong integration test, ta import **recording fake** từ `src/test/java`.
- **Không có** production endpoint/token trong default hoặc test config.
- Khi chạy ứng dụng mà **không chọn profile phù hợp**, startup thất bại vì thiếu `NotificationGateway`. Đây là lựa chọn **fail-closed có chủ đích**, không phải lỗi cấu hình cần chữa bằng cách bật `prod` trong test.

### 3.1. Cấu trúc thư mục

```text
safe-test-environment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safeconfig/
    │   │   ├── SafeConfigApplication.java
    │   │   ├── NotificationGateway.java
    │   │   ├── RegistrationService.java
    │   │   ├── RegistrationRequest.java
    │   │   ├── RegistrationResult.java
    │   │   ├── RegistrationController.java
    │   │   ├── LocalNotificationGateway.java
    │   │   └── HttpNotificationGateway.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/
        ├── java/com/example/safeconfig/
        │   ├── RecordingNotificationGateway.java
        │   ├── SafeTestConfiguration.java
        │   ├── RegistrationServiceTest.java
        │   ├── RegistrationIsolationTest.java
        │   └── HttpNotificationGatewayTest.java
        └── resources/
            └── application-test.yml
```

Tất cả `package` trong ví dụ là `com.example.safeconfig`; đặt từng `public class`/`public record`/`public interface` đúng tên tệp. Dùng **Java 17 trở lên**, Maven và kết nối Internet chỉ để lấy Maven dependencies ban đầu. Test không gọi dịch vụ bên ngoài.

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-test-environment</artifactId>
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

`spring-boot-starter-web` cung cấp MVC/Jackson/`RestClient` cho adapter. `spring-boot-starter-test` ở Maven `scope=test` cung cấp JUnit Jupiter, Mockito, Spring Test và `MockRestServiceServer` cho các tệp test. BOM từ parent quản lý các phiên bản tương thích.

### 3.3. Main application và hợp đồng nội bộ

```java
// src/main/java/com/example/safeconfig/SafeConfigApplication.java
package com.example.safeconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeConfigApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/safeconfig/NotificationGateway.java
package com.example.safeconfig;

public interface NotificationGateway {
    void send(String recipient, String message);
}
```

```java
// src/main/java/com/example/safeconfig/RegistrationService.java
package com.example.safeconfig;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationGateway gateway;

    public RegistrationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    public String register(String rawEmail) {
        if (rawEmail == null || rawEmail.isBlank()) {
            throw new IllegalArgumentException("Email must not be blank");
        }
        String email = rawEmail.trim().toLowerCase(Locale.ROOT);
        gateway.send(email, "Welcome!");
        return email;
    }
}
```

```java
// src/main/java/com/example/safeconfig/RegistrationRequest.java
package com.example.safeconfig;

public record RegistrationRequest(String email) {}
```

```java
// src/main/java/com/example/safeconfig/RegistrationResult.java
package com.example.safeconfig;

public record RegistrationResult(String email) {}
```

```java
// src/main/java/com/example/safeconfig/RegistrationController.java
package com.example.safeconfig;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {
    private final RegistrationService service;

    public RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @PostMapping("/register")
    public ResponseEntity<RegistrationResult> register(
            @RequestBody RegistrationRequest request) {
        String normalized = service.register(request.email());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new RegistrationResult(normalized));
    }
}
```

`RegistrationService` chỉ biết cổng `NotificationGateway`, không biết domain, token, URL hoặc HTTP client. Đó là điểm giúp test thay adapter mà không phải đọc secret. Ví dụ tối giản chưa định nghĩa exception handler HTTP cho input rỗng; test input invalid ở tầng service để tránh suy diễn mã status trong ví dụ.

### 3.4. Adapter production chỉ xuất hiện khi chủ động chọn `prod`

```java
// src/main/java/com/example/safeconfig/HttpNotificationGateway.java
package com.example.safeconfig;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
@Profile("prod")
public class HttpNotificationGateway implements NotificationGateway {
    private final RestClient client;
    private final String token;

    public HttpNotificationGateway(
            RestClient.Builder builder,
            @Value("${app.notification.base-url}") String baseUrl,
            @Value("${app.notification.token}") String token) {
        URI uri = URI.create(baseUrl);

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                    "Production notification URL must use HTTPS");
        }
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException(
                    "Notification token must be configured");
        }

        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    @Override
    public void send(String recipient, String message) {
        client.post()
                .uri("/messages")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .body(new Payload(recipient, message))
                .retrieve()
                .toBodilessEntity();
    }

    public record Payload(String recipient, String message) {}
}
```

Có hai lớp bảo vệ:

1. `@Profile("prod")` loại adapter này khỏi các context chỉ chạy profile `test` hoặc `local`.
2. Giá trị URL/token bắt buộc và URL phải dùng HTTPS khi bean được tạo. Không có default production URL/token trong code hoặc `application.yml`.

**Giới hạn thực tế:** yêu cầu HTTPS **không phải** một allowlist hostname; nếu runtime cấp sai URL HTTPS, adapter vẫn có thể gửi tới host sai. Với hệ thống quan trọng, bổ sung DNS/network egress allowlist, IAM/service account riêng, TLS trust policy, certificate pinning khi có yêu cầu và chính sách deployment. Không coi `@Profile` hay kiểm tra scheme là lớp bảo vệ duy nhất.

### 3.5. Adapter an toàn cho chạy local

```java
// src/main/java/com/example/safeconfig/LocalNotificationGateway.java
package com.example.safeconfig;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalNotificationGateway implements NotificationGateway {
    @Override
    public void send(String recipient, String message) {
        // Chỉ dành cho local: không thực hiện HTTP/email/SMS.
    }
}
```

Profile `local` cho phép developer chạy ứng dụng thủ công mà không có secret và không gửi thông báo thật. Test tự động không phụ thuộc adapter local: nó sẽ dùng recording fake riêng. Không nên đưa local no-op thành **fallback** cho production: nếu profile prod bị cấu hình thiếu, nên khởi động thất bại chứ không âm thầm làm mất thông báo.

### 3.6. Các tệp cấu hình không chứa secret thật

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: safe-test-environment
```

```yaml
# src/main/resources/application-prod.yml
app:
  notification:
    base-url: ${NOTIFICATION_BASE_URL}
    token: ${NOTIFICATION_TOKEN}
```

```yaml
# src/test/resources/application-test.yml
spring:
  main:
    banner-mode: "off"
app:
  safety:
    environment: isolated-test
```

Khi test kích hoạt `test`:

- `application-test.yml` cung cấp marker `app.safety.environment=isolated-test` để xác nhận profile-specific config đã được nạp.
- Không có production URL hoặc token nào cần cho `RegistrationService` vì production gateway **không được tạo**.
- Test fake được import qua `@TestConfiguration`, không thông qua giá trị property bật/tắt production gửi email.
- Một test chỉ kiểm tra `app.safety.environment` là chưa đủ để đảm bảo không có outbound network; test còn phải kiểm tra loại gateway và chính sách mạng khi cần.

Khi app chạy với `prod`, Spring Boot mới đọc `application-prod.yml` và cần các biến `NOTIFICATION_BASE_URL` và `NOTIFICATION_TOKEN` từ runtime **chính thức**. Hai chuỗi `${...}` trên là placeholder của Spring Boot, không phải giá trị bí mật. Không nên đưa token thật vào Git, unit test, snapshot hoặc các câu lệnh minh họa.

## 4. Test-only fake sống trong `src/test/java`

Thay vì tạo fake trong `src/main/java` rồi vô tình đóng gói nó vào production artifact, định nghĩa **recording fake** ở test source set.

```java
// src/test/java/com/example/safeconfig/RecordingNotificationGateway.java
package com.example.safeconfig;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class RecordingNotificationGateway implements NotificationGateway {
    record Sent(String recipient, String message) {}

    private final List<Sent> messages = new CopyOnWriteArrayList<>();

    @Override
    public void send(String recipient, String message) {
        messages.add(new Sent(recipient, message));
    }

    List<Sent> messages() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}
```

```java
// src/test/java/com/example/safeconfig/SafeTestConfiguration.java
package com.example.safeconfig;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class SafeTestConfiguration {
    @Bean
    RecordingNotificationGateway recordingNotificationGateway() {
        return new RecordingNotificationGateway();
    }
}
```

`@TestConfiguration` là cấu hình dành cho test; ta dùng `@Import(SafeTestConfiguration.class)` để khai báo **rõ ràng** test context cần fake này. Vì fake ở `src/test/java`, build `jar`/`bootJar` chính theo chuẩn sẽ không chứa nó. Sự cô lập classpath giúp giảm khả năng test helper trở thành production bean.

Dùng recording fake có lợi hơn `@Mock` trong integration test khi cần kiểm tra đầy đủ payload sau một request. Nó không tạo HTTP request và không phụ thuộc service bên ngoài. Với unit test thuần, Mockito mock vẫn rất phù hợp.

## 5. Hai tầng kiểm thử: unit không Spring context và integration có profile test

### 5.1. Unit test JUnit + Mockito không động tới Spring context

```java
// src/test/java/com/example/safeconfig/RegistrationServiceTest.java
package com.example.safeconfig;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {
    @Mock
    NotificationGateway gateway;

    @InjectMocks
    RegistrationService service;

    @Test
    void normalizesEmailBeforeSending() {
        String registered = service.register(" Alice@Example.Test ");

        assertEquals("alice@example.test", registered);
        verify(gateway).send("alice@example.test", "Welcome!");
    }

    @Test
    void rejectsBlankInputWithoutSending() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.register("   "));
        verifyNoInteractions(gateway);
    }
}
```

Unit test chạy `RegistrationService` thật và Mockito gateway, nên **không cần mở Spring ApplicationContext**, không resolve `application-prod.yml` và không thực hiện network I/O. Bản thân Mockito mock còn giúp assert thông tin được gửi ra, thay vì chỉ assert không xảy ra lỗi.

Một lỗ hổng cần tránh: nếu code nghiệp vụ tự tạo `new RestClient(...)` hoặc gọi static client theo `System.getenv`, việc mock `NotificationGateway` sẽ không thay thế được các lời gọi nằm ngoài abstraction. Thiết kế dependency injection là điều kiện quan trọng để có thể cách ly test.

### 5.2. Integration test với `@ActiveProfiles("test")` và fake

```java
// src/test/java/com/example/safeconfig/RegistrationIsolationTest.java
package com.example.safeconfig;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(SafeTestConfiguration.class)
class RegistrationIsolationTest {

    @Autowired
    Environment environment;

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RecordingNotificationGateway gateway;

    @BeforeEach
    void resetFake() {
        gateway.clear();
    }

    @Test
    void hasTestProfileAndNoProdProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertFalse(environment.acceptsProfiles(Profiles.of("prod")));
        assertEquals("isolated-test",
                environment.getProperty("app.safety.environment"));
    }

    @Test
    void postRequestUsesOnlyRecordingGateway() throws Exception {
        mockMvc.perform(post("/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":" Alice@Example.Test "}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email")
                        .value("alice@example.test"));

        assertEquals(
                List.of(new RecordingNotificationGateway.Sent(
                        "alice@example.test", "Welcome!")),
                gateway.messages());
    }
}
```

Điểm kiểm tra được:

- Test context nạp profile `test` và property marker từ `application-test.yml`.
- Không có profile `prod` trong environment đang được kiểm tra.
- Controller nhận JSON qua `MockMvc`, service thật chuẩn hóa email và chuyển lệnh tới **recording fake**.
- Fake ghi nhận đúng dữ liệu outbound, không mở network tới notification API.
- `MockMvc` kiểm tra Spring MVC **không mở HTTP socket** cho request vào; nó không tự cấm mọi HTTP outbound do những bean khác thực hiện. Ở đây sự bảo vệ outbound đến từ việc thay `NotificationGateway`.

Không được suy ra rằng chỉ assertion `!prod` có thể chặn một client tự gọi URL production từ bean khác. Một test context có thể được tạo trước khi các assertion trong method chạy. Vì vậy production adapter phải được **loại khỏi bean graph trước khi khởi tạo**, và CI nên chặn network/credentials production độc lập.

### 5.3. Test HTTP adapter mà không gửi request ra ngoài

Nếu chỉ mock toàn bộ `NotificationGateway`, ta chưa kiểm tra JSON, header và HTTP method do adapter tạo. Spring Test có `MockRestServiceServer` để chặn lời gọi của `RestClient.Builder` và trả response giả mà **không cần HTTP server thật**.

```java
// src/test/java/com/example/safeconfig/HttpNotificationGatewayTest.java
package com.example.safeconfig;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class HttpNotificationGatewayTest {

    @Test
    void buildsCorrectHttpRequestWithoutRealNetwork() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(
                    "https://notify.example.test/messages"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header(HttpHeaders.AUTHORIZATION,
                        "Bearer fake-test-token"))
                .andExpect(content().json("""
                        {"recipient":"alice@example.test",
                         "message":"Welcome!"}
                        """))
                .andRespond(withSuccess());

        HttpNotificationGateway adapter =
                new HttpNotificationGateway(
                        builder,
                        "https://notify.example.test",
                        "fake-test-token");

        adapter.send("alice@example.test", "Welcome!");
        server.verify();
    }

    @Test
    void rejectsNonHttpsConfiguration() {
        assertThrows(IllegalArgumentException.class,
                () -> new HttpNotificationGateway(
                        RestClient.builder(),
                        "http://notify.example.test",
                        "fake-test-token"));
    }
}
```

Khi tự tạo object bằng `new` trong unit test adapter, `@Profile("prod")` **không được Spring xét** — điều đó bình thường; annotation chỉ áp dụng khi Spring tạo bean. Test này không nạp production properties và không cần token thật. `MockRestServiceServer` thay request factory của builder đã truyền vào, nên request được đối chiếu trong bộ nhớ thay vì gửi tới `notify.example.test`.

`notify.example.test` là domain ví dụ dành cho kiểm thử, không phải production host. Token `fake-test-token` là chuỗi giả. Bộ test này xác nhận adapter dựng đúng request, **không** chứng minh TLS handshake, DNS, retry, proxy, timeout hoặc network thật. Khi cần kiểm tra transport, sử dụng HTTP stub server/WireMock/MockWebServer trên loopback với port ngẫu nhiên và thiết lập test-only rõ ràng.

### 5.4. Lệnh chạy

Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=RegistrationServiceTest test
mvn -Dtest=RegistrationIsolationTest test
mvn -Dtest=HttpNotificationGatewayTest test
```

Cần JDK 17+, Maven và quyền tải thư viện lúc thiết lập build. Các test không yêu cầu DB, broker hay Internet ở thời điểm thực thi; Maven chỉ có thể cần mạng nếu dependencies chưa nằm trong cache. Log Maven/Spring thay đổi theo môi trường, nên **không đưa ra stdout cố định**; mỗi assertion xác nhận kết quả cụ thể.

Để chạy ứng dụng **local an toàn** (không có notification HTTP):

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

Khi chạy mặc định **không chọn profile**, ứng dụng cố ý thiếu `NotificationGateway` và startup thất bại. Cách xử lý đúng là chọn `local` cho thao tác phát triển. **Không chọn `prod` để “cho app chạy được”** và không cấp secret production trên máy test chỉ để chữa một lỗi injection.

## 6. Bảo vệ test khỏi database production

HTTP gateway chỉ là một kiểu rủi ro. Database nguy hiểm hơn vì test thường tạo/sửa/xóa nhiều bản ghi.

**Không nên làm:**

```yaml
# Cấu hình sai hướng, ví dụ minh họa:
spring:
  datasource:
    url: jdbc:postgresql://production-db.internal:5432/app
```

Nếu giá trị trên nằm trong `application.yml`, một test repository không override kịp sẽ có thể trỏ tới DB thật. Test chạy trong transaction cũng không đủ bảo vệ khi có DDL, thao tác ngoài transaction, listener, async job hoặc cấu hình rollback khác.

**Nên làm:** không chứa production URL trong cấu hình mặc định; profile test dùng DB riêng được cấp cho test, credential với quyền tối thiểu và tự dọn, tốt nhất ephemeral.

### 6.1. H2 in-memory cho test đơn giản

Đây là **công thức bổ sung cho dự án dùng Spring Data JPA**, không thuộc `pom.xml` mẫu ở phần 3 vì ví dụ notification không dùng database. Trong dự án JPA, khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>test</scope>
</dependency>
```

Và trong `src/test/resources/application-test.yml` của dự án JPA:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:isolatedtests;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

H2 nằm ở test classpath, không cần mật khẩu production, và DB chạy trong process test. Có thể dùng tên DB riêng cho từng test context để tránh rò rỉ dữ liệu. `DB_CLOSE_DELAY=-1` giữ DB tồn tại tới khi JVM kết thúc, nên **không mặc nhiên bảo đảm mỗi test method được reset**; dùng transaction rollback, cleanup dữ liệu và tách context/DB khi cần.

**Giới hạn:** H2 không luôn giống PostgreSQL/MySQL về SQL dialect, JSON, locking, index, transaction isolation, migration và constraint. Nếu những điểm ấy là hợp đồng cần bảo vệ, dùng đúng database engine trong môi trường cô lập.

### 6.2. Testcontainers cho database giống production nhưng cô lập

Một lựa chọn khác: chạy PostgreSQL trong Docker/container ephemeral, **không kết nối PostgreSQL production**. Với Spring Boot 3.5 và Testcontainers phù hợp có thể dùng `@ServiceConnection` hoặc `@DynamicPropertySource`.

Dependency bổ sung trong một **dự án JPA/PostgreSQL**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Minh họa integration test container (cần repository/entity thật trong project JPA và Docker đang chạy; **không phải test độc lập trong ví dụ notification**):

```java
@Testcontainers
@SpringBootTest
@ActiveProfiles("test")
class RepositoryContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CustomerRepository repository;

    @Test
    void writesOnlyToEphemeralDatabase() {
        Customer saved = repository.save(
                new Customer("alice@example.test"));
        assertEquals("alice@example.test",
                repository.findById(saved.getId())
                        .orElseThrow().getEmail());
    }
}
```

Đoạn này **minh họa pattern**, giả định `CustomerRepository`/`Customer` và imports được định nghĩa trong dự án JPA. Cần Docker và dependency/driver PostgreSQL phù hợp, cùng Flyway/Liquibase/schema nếu có. `@ServiceConnection` giúp Spring Boot nhận JDBC connection details của container. Bản thân container dùng port/credential tạm, tránh copy URL/username/password từ production.

Nếu dùng `@DynamicPropertySource` thay `@ServiceConnection`, đưa URL/username/password của container vào context:

```java
@DynamicPropertySource
static void containerProps(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Chỉ dùng đoạn này khi `postgres` là container đã khai báo đúng vòng đời và không dùng đồng thời hai cơ chế cho cùng một connection nếu không có lý do. **Không trộn** testcontainer credentials với production secret. Tách network/project/container, không mount production backup chứa dữ liệu thật vào test.

### 6.3. Thói quen an toàn với dữ liệu test

- Ưu tiên dữ liệu giả/synthetic, không dùng dữ liệu khách hàng thật để kiểm thử chức năng.
- Tạo schema/DB riêng, user test riêng, không cấp `DROP DATABASE` hoặc quyền production.
- Dùng cleanup/rollback rõ ràng; biết `@Transactional` rollback ở test có giới hạn đối với request chạy trong thread/transaction khác.
- Khi test có parallel execution, tránh dùng chung DB name/fixture hoặc dùng strategy cô lập.
- Nếu sử dụng DB test được host riêng, xác nhận host thuộc allowlist của tổ chức và credential chỉ có quyền test.
- Không chạy lệnh hủy dữ liệu từ CI nếu target URL chưa được kiểm chứng; pipeline nên có guard từ trước khi test khởi động.

## 7. Ngăn gửi email, SMS, payment, Kafka và HTTP tới production

Ngoài datasource, nhiều thư viện có thể tự mở kết nối qua auto-configuration hoặc lifecycle hooks:

| Tài nguyên | Test an toàn | Điều không nên làm |
| --- | --- | --- |
| Email/SMTP | Fake `MailSender`, in-memory mailbox, SMTP test server | Gửi email tới mailbox khách hàng thật |
| SMS/push | Mock gateway, sandbox account và fake phone number | Dùng token/recipient production |
| Payment gateway | Fake/contract test với sandbox credentials | Thực hiện charge/refund trên account live |
| REST/gRPC outbound | Mockito port, `MockRestServiceServer`, WireMock/MockWebServer loopback | Đọc base URL production trực tiếp |
| Kafka/RabbitMQ | Embedded/mock producer cho unit; ephemeral broker cho integration | Publish lên topic/queue production |
| Object storage | Local emulator, bucket test riêng và object prefix test | Ghi/xóa bucket production |
| Search/cache | Container hoặc service test riêng, namespace cô lập | Flush/clear cache production |
| OAuth/OIDC | Fake token/key pair hoặc local authorization server | Dùng client secret production trong test |

Khi test dùng **sandbox thật** của nhà cung cấp, sandbox cũng có thể có chi phí, quota và thông tin nhạy cảm. Cần đánh dấu test suite là external integration, dùng account/key riêng, giới hạn rate, timeout, phạm vi dữ liệu và cleanup.

**Chỉ thay `@ActiveProfiles` không thay được một thư viện chủ động dùng `System.getenv`/static singleton.** Hãy ưu tiên cổng interface được inject, cấu hình client qua một nơi, và không gọi external endpoint trong constructor hoặc `@PostConstruct`. Bean init càng ít side effect càng dễ kiểm soát.

## 8. Nguyên tắc quản lý secrets

### 8.1. Không được đưa secret vào đâu?

Không đặt **giá trị bí mật thật** trong:

- `application.yml`, `application-test.yml`, `application-prod.yml` hoặc file được commit.
- Code test, fixture, snapshot, hard-coded `@Value`, default `${TOKEN:real-token}`.
- GitHub Actions/GitLab CI YAML dưới dạng chuỗi thô.
- Log được in khi Spring bind properties, HTTP request/response interceptor, exception stack trace, test failure message.
- Artifact Surefire, report, screenshot, build scan hoặc cache nếu có thể chứa payload secret.
- Dòng lệnh CLI truyền trực tiếp token trong môi trường nhiều user, vì process list/shell history có thể lưu lại.

**Test secret thật** (nếu bài kiểm thử external sandbox buộc phải có) phải là credential **riêng**, phạm vi tối thiểu, vòng đời ngắn khi có thể, được cấp thông qua CI secret manager hoặc workload identity và không được chia sẻ với production. Không phải tất cả test đều cần secret; unit và phần lớn test HTTP mock nên chạy với **không có secret**.

### 8.2. Biến môi trường là nguồn cấp, không tự biến dữ liệu thành an toàn

Ví dụ tốt về cách **tham chiếu** giá trị (không chứa dữ liệu thật):

```yaml
# application-prod.yml — không commit giá trị thực
app:
  notification:
    base-url: ${NOTIFICATION_BASE_URL}
    token: ${NOTIFICATION_TOKEN}
```

Trong production runtime, giá trị đến từ secret manager/CI/CD deployment và được cấp cho đúng ứng dụng. Nhưng **một biến môi trường vẫn có thể bị rò rỉ** nếu log, test harness, process dump hoặc CI job khác đọc nó. Không tự động forward toàn bộ environment variables production sang job test.

Nếu một secret từng được commit, việc xóa dòng ở commit sau **không xóa lịch sử**. Cần **revoke/rotate** secret, kiểm tra sử dụng bất thường và xử lý lịch sử repository theo quy trình bảo mật; không chỉ thêm vào `.gitignore` rồi coi như xong.

### 8.3. File local và `.gitignore`

Những tệp local tùy chọn như `.env.local`, `secrets.local.yml` không nên commit. Có thể cấu hình:

```gitignore
.env
.env.*
!.env.example
secrets.local.yml
*.pem
```

Chỉ dùng `.env.example` chứa **tên biến và giá trị giả**, không chứa production credential. Nhưng `.gitignore` **không ngăn file đã được Git track trước đó** và không thay thế secret scanning. Một số project cần commit certificate công khai hoặc test key giả; điều này phải được đánh giá riêng thay vì cấm mọi `*.pem` một cách máy móc.

### 8.4. Vì sao fake token trong unit test vẫn hữu ích?

Trong `HttpNotificationGatewayTest`, `fake-test-token` chỉ là chuỗi xác định để so sánh header. Nó kiểm tra code xây request đúng định dạng, **không trao quyền** lên provider thật. Token giả không cần nằm trong secret manager và không được tái sử dụng làm credentials hoạt động ở môi trường khác.

## 9. CI/CD: chặn nhầm production từ tầng hạ tầng

Một pipeline tốt không dựa vào mỗi annotation Java. Trước khi chạy test, áp dụng thêm các kiểm soát:

1. **Job unit/slice** không được cấp secrets, service account hay network route tới production; chỉ tải dependencies.
2. **Job integration** dùng container hoặc sandbox tài khoản riêng; không mount production secrets.
3. **Job staging/e2e** tách riêng, chạy sau deployment staging, có thủ tục cleanup và quyền tối thiểu.
4. **Job production deployment** sử dụng quyền/cơ chế approve khác; không để test job thường thừa hưởng production credentials.
5. Chặn outbound egress tới dải mạng/internal DNS production nếu CI platform hỗ trợ; dùng allowlist.
6. Validate target trước khi test bắt đầu; fail nếu config chứa host/namespace không được phép.
7. Không in environment dump (ví dụ `printenv` toàn bộ) hoặc Maven debug log chứa Authorization header.
8. Tách role IAM, database user, bucket, queue, và network policy giữa test/staging/prod.

### 9.1. Ví dụ kiểm tra guard của CI (shell, không phải secret checker hoàn chỉnh)

Ví dụ này **chỉ chặn một trường hợp cấu hình sai cụ thể**, không được xem là biện pháp bảo mật duy nhất:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "${SPRING_PROFILES_ACTIVE:-}" == *"prod"* ]]; then
  echo "Blocked: prod profile is not allowed in unit-test job" >&2
  exit 1
fi

if [[ -n "${NOTIFICATION_TOKEN:-}" ]]; then
  echo "Blocked: notification credential must not exist in unit tests" >&2
  exit 1
fi

mvn -B test
```

**Giới hạn:** kiểm tra chuỗi `*prod*` ở đây có thể false positive/false negative đối với tên profile phức tạp hoặc profile group; biến môi trường khác vẫn có thể chứa secret; test annotation có thể override một số profile flags. Do đó dùng biện pháp cấu hình CI chính thức để **không cấp secrets production** ngay từ đầu. Một test framework không nên là lớp duy nhất thực thi ranh giới bảo mật.

Nếu CI chạy trên shared runner, kiểm tra quyền đọc các biến masked/protected, cách xử lý fork PR, job artifacts, build caches và retention. Đừng làm lộ secret qua assertion thất bại của client HTTP có in toàn bộ request.

### 9.2. Tách stage theo mục tiêu test

| Stage | Loại test | Quyền/tài nguyên |
| --- | --- | --- |
| Pull request | Unit, MVC slice, contract test dùng fake | Không có production credential, egress giới hạn |
| Merge/main | Integration với Testcontainers | Docker test runner, mạng riêng, secret test nếu cần |
| Staging deploy | API/E2E smoke | Account sandbox/staging, test user, rate limit |
| Release/production deploy | Deploy và kiểm tra quan sát an toàn | Quyền deploy tách riêng, không chạy destructive test lên prod |

Không đưa test có `deleteAll`, reset schema hoặc tạo giao dịch giả vào production sau deploy. Nếu cần health check production, đó là probe không phá dữ liệu và chỉ với quyền tối thiểu.

## 10. Các kỹ thuật cấu hình test bổ trợ

### 10.1. `@SpringBootTest(properties = ...)` cho override cụ thể

Nếu cần kiểm tra một feature flag hoặc timeout riêng trong một class:

```java
@SpringBootTest(properties = {
        "app.retry.max-attempts=1",
        "app.client.read-timeout=250ms"
})
@ActiveProfiles("test")
class RetryPolicyIntegrationTest {
    // Minh họa: test thực cần beans và assertions tương ứng.
}
```

Đoạn trên là **mẫu annotation**, không phải tệp runnable độc lập. Nó có thể phù hợp cho property test-specific; không dùng để ghi đè production secret trong một context vốn đã trỏ tới production. Cách an toàn hơn là **đừng tạo production client trong context test**.

### 10.2. `@TestPropertySource`

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.feature.experimental=false"
})
class FeatureFlagTest {
    // Minh họa thêm property cục bộ cho test.
}
```

`@TestPropertySource` thường dùng với Spring TestContext để thêm property cho test. Nếu property đủ chung và nhiều test dùng, đặt vào `application-test.yml` để tránh lặp và tránh các context cache cấu hình khác nhau không cần thiết.

### 10.3. `@DynamicPropertySource`

Dùng khi endpoint/port được cấp **tại runtime** bởi Testcontainers hoặc mock HTTP server, ví dụ:

```java
@DynamicPropertySource
static void externalServiceProperties(DynamicPropertyRegistry registry) {
    registry.add("app.remote.base-url", testServer::baseUrl);
}
```

Đây là **mẫu minh họa** chỉ có nghĩa khi `testServer` đã được khởi động theo vòng đời test và `baseUrl()` thực sự trả URL của sandbox server đó. `@DynamicPropertySource` không có tác dụng bảo mật đặc biệt: nếu bạn đăng ký URL production thì chính nó sẽ đưa production URL vào test context.

### 10.4. `@MockitoBean` thay collaborator khi nạp context

Với Spring Framework 6.2/Spring Boot 3.5, có thể khai báo:

```java
@SpringBootTest
@ActiveProfiles("test")
class MockedGatewayIntegrationTest {
    @MockitoBean
    NotificationGateway gateway;
}
```

Đây là **đoạn minh họa**: cần imports cho `SpringBootTest`, `ActiveProfiles`, `MockitoBean` và một application context tương thích. `@MockitoBean` tạo/ghi đè bean bằng Mockito mock, nên cách dùng khác `@Mock` thông thường (chỉ tạo Java mock ngoài Spring). Khi có nhiều bean cùng loại/qualifier cần xử lý chính xác. Đừng đặt `@MockitoBean` cho dependency muốn kiểm tra là thật, hoặc dùng nó để kết luận adapter thật không có lỗi mapping.

Với project hoàn chỉnh ở phần 3–5, ta chọn `@TestConfiguration` + recording fake để dễ quan sát event đã gửi; không cần thêm `@MockitoBean` vào test đó.

### 10.5. Dùng một profile test chung hay nhiều profile?

Có thể tách `unit`, `integration`, `staging` theo mục đích, nhưng không nên tạo một chuỗi profile khó đoán. Nếu có nhiều group, ghi rõ những bean/dịch vụ được bật trong từng group. Phân nhóm bằng JUnit `@Tag("integration")` **không tự đổi** Spring profile; annotation tag là metadata lọc test. Runner phải cấu hình stage và profile/tài nguyên tương ứng.

## 11. Các lỗi thường gặp và cách khắc phục

### Lỗi 1. Test dùng production URL từ cấu hình base

**Triệu chứng:** Test nạp Spring context, log nói đã gọi host nội bộ production; DB/table thật bị ảnh hưởng.

**Nguyên nhân:** URL trong `application.yml` hoặc một env var cao ưu tiên; không có guard. **Khắc phục:** loại production endpoint khỏi base, sử dụng `application-prod.yml` + runtime placeholders; chuyển test qua fake/container, chặn egress và phân quyền. Đừng chỉ thêm assert sau khi Spring context đã khởi động.

### Lỗi 2. Test profile đúng nhưng bean vẫn mở socket

**Nguyên nhân:** bean không được quản lý theo profile, tự xây client trong constructor/`@PostConstruct` hoặc code gọi static client ngoài dependency injection.

**Khắc phục:** đưa external call sau abstraction, khởi tạo client không có side effect, cấu hình adapter với `@Profile("prod")` hoặc `@ConditionalOnProperty` thật rõ, thay bằng fake trong test. Bổ sung kiểm tra network policy của CI.

### Lỗi 3. Copy production secret vào `application-test.yml` để test chạy

**Nguyên nhân:** test quá phụ thuộc vào production service hoặc adapter, người viết “chữa” bằng credential thật.

**Khắc phục:** mock dependency, container hoặc sandbox test credential có quyền tối thiểu. Nếu credential thật từng được commit, phải rotate/revoke ngay theo quy trình và đánh giá log/history/artifacts.

### Lỗi 4. Chỉ đổi `server.port=0` rồi tưởng mọi kết nối đã cô lập

`server.port=0` (hoặc `webEnvironment=RANDOM_PORT`) chỉ giải quyết **inbound server port**. Outbound database/HTTP/Kafka vẫn dùng URL/credentials riêng. Thay thế các cổng outbound và kiểm soát URL đích mới là phần chính của cô lập test.

### Lỗi 5. Dùng `localhost` nhưng chạy trên runner/container khác

`localhost` bên trong Docker/Kubernetes/CI container chỉ về **chính namespace mạng của process đó**, không nhất thiết là máy host hoặc container khác. Dùng URL được cấp bởi test infrastructure, container network hostname/port mapping hoặc `@DynamicPropertySource`. Không fallback sang URL production khi không kết nối localhost được.

### Lỗi 6. Đặt fake trong `src/main/java` và cấu hình fallback cho mọi profile

Khi deploy production sai biến môi trường, ứng dụng có thể dùng fake và âm thầm không gửi sự kiện thật. Ưu tiên fake chỉ trong test source set, còn `local` profile phải được bật tường minh. Production thiếu config nên **fail startup**, không fallback âm thầm.

### Lỗi 7. Test chạy lại làm hỏng dữ liệu của test khác

Dùng chung DB test cố định, topic/bucket hoặc fixture không cleanup khiến test phụ thuộc thứ tự và dễ flaky. Phân vùng namespace, dùng database/container riêng, rollback/cleanup chắc chắn và chú ý parallel execution.

### Lỗi 8. Quên rằng test report/log có thể chứa secret

HTTP interceptor hoặc assertion có thể in toàn bộ Authorization header. Chỉ log status/code/ID giả phù hợp; redact token/password; cấu hình framework logging phù hợp. Không “debug” bằng cách in hết properties/environment lên CI.

### Lỗi 9. Giả định `@ActiveProfiles("test")` là sandbox hoàn chỉnh

Annotation chỉ giúp chọn active profiles cho TestContext. Nó không tự chặn một SDK đọc env var trực tiếp, không ngăn network access và không cung cấp credentials test. Cần kết hợp **fake/adapter isolation, sandbox data, network egress policy, IAM tối thiểu**.

### Lỗi 10. Dùng `@DataJpaTest` nhưng test vẫn chạm DB ngoài

Repository slice test có thể thay datasource bằng embedded database khi phù hợp, nhưng còn phụ thuộc database dependencies và `@AutoConfigureTestDatabase` config. Nếu test dùng DB đặc thù mà không có embedded replacement, nó có thể kết nối URL đã cấu hình. Luôn xác nhận effective datasource; chọn H2/testcontainers rõ ràng, không tin rằng mọi `@DataJpaTest` tự an toàn tuyệt đối.

### Lỗi 11. Bật profile prod trong IDE để tránh thiếu bean

Đó là dấu hiệu thiết kế default unsafe hoặc developer thiếu local adapter. Không dùng production profile/secret cho unit test. Hãy có explicit `local` profile, fake adapters và hướng dẫn chạy dev, hoặc giữ fail-closed như mẫu này.

### Lỗi 12. Đưa production hostname vào expected của test

Khi test adapter, nếu chỉ muốn kiểm tra path/method/body/header, dùng domain reserved như `notify.example.test` và mock request factory. Nếu phải dùng host cố định để kiểm tra routing, nó phải là hostname **test-only**, không có khả năng giải quyết tới production.

## 12. Checklist review và câu hỏi tự kiểm tra

### 12.1. Checklist trước khi merge

- [ ] `application.yml` không chứa production endpoint, API key, password hoặc fallback nguy hiểm.
- [ ] Production properties chỉ là tên property/tham chiếu secret store hoặc env var có quản lý.
- [ ] Test context dùng `@ActiveProfiles("test")` (hoặc cấu hình rõ tương đương), không kích hoạt `prod` ngoài ý muốn.
- [ ] Fake/Mockito/HTTP stub được inject **trước** khi code có thể gọi outbound gateway.
- [ ] Integration test xác nhận không có production adapter trong đường chạy cần kiểm tra.
- [ ] HTTP client test không cần DNS/network thật; test transport sử dụng stub server trên loopback.
- [ ] Database test dùng H2 phù hợp hoặc PostgreSQL/MySQL Testcontainers/sandbox riêng, không dùng production URL.
- [ ] Test account/fixture không chứa dữ liệu khách hàng thật; cleanup/rollback và parallel execution có kế hoạch.
- [ ] CI test jobs **không nhận** production secrets và không có quyền network/database production.
- [ ] Không in token vào log, assertion failure, build scan hoặc test artifact.
- [ ] Secret đã lộ được revoke/rotate, không chỉ xóa khỏi HEAD của Git.
- [ ] Nếu test kết nối sandbox ngoài thật, đó là stage riêng có credentials test-only và giới hạn chi phí/tài nguyên.
- [ ] Khi thiếu dependency test, build **fail rõ ràng** thay vì fallback qua production.

### 12.2. Câu hỏi tự kiểm tra

**Câu 1.** Có `@ActiveProfiles("test")` thì `@SpringBootTest` chắc chắn không gọi production HTTP?

**Trả lời:** Không. Nó chọn profile/config, nhưng bean không được cô lập hoặc SDK tự đọc env var vẫn có thể gọi production. Cần fake/conditional bean, test-only URL và network policy.

**Câu 2.** Tại sao không ghi API token thật vào `application-test.yml` dù repository private?

**Trả lời:** Token có thể bị lộ qua lịch sử Git, fork, CI artifacts, backups, copy/paste hoặc log. Unit test không cần production token. Khi cần kiểm thử sandbox, dùng credential test-only từ secret manager và quyền tối thiểu.

**Câu 3.** `@Profile("prod")` trên HTTP gateway khác gì `@ActiveProfiles("test")` trên test?

**Trả lời:** `@Profile` đặt điều kiện để Spring **đăng ký bean** khi profile phù hợp; `@ActiveProfiles` yêu cầu TestContext **kích hoạt profile** khi nạp context. Hai annotation phối hợp để production adapter không xuất hiện trong test context.

**Câu 4.** Trong ví dụ, tại sao request MockMvc không gửi email thật?

**Trả lời:** Context test import `RecordingNotificationGateway` thay cho production adapter. `MockMvc` chỉ xử lý request inbound trong Spring MVC test infrastructure; outbound bị chặn tại cổng `NotificationGateway`, không phải do riêng MockMvc.

**Câu 5.** Vì sao test adapter HTTP vẫn kiểm tra được Authorization header mà không cần token thật?

**Trả lời:** Dùng `fake-test-token` và `MockRestServiceServer` để đối chiếu request trong bộ nhớ. Nó xác nhận format header/body/path, không thử xác thực với provider live.

**Câu 6.** Khi nào H2 không đủ?

**Trả lời:** Khi test phụ thuộc SQL dialect/constraint/transaction/locking hoặc type riêng của database production. Lúc đó dùng container cùng engine hoặc một database sandbox có quyền tách biệt.

**Câu 7.** Nếu production secret đã được commit rồi xóa, đã an toàn chưa?

**Trả lời:** Chưa. Secret có thể tồn tại trong Git history, clone, cache hoặc log. Cần revoke/rotate và kiểm tra phạm vi lộ lọt.

**Câu 8.** Nếu `mvn test` trên CI vẫn có quyền truy cập production DB, có vấn đề không dù tests đang dùng fake?

**Trả lời:** Vẫn có rủi ro khi test được thêm/sửa hoặc config bị override. Theo nguyên tắc phòng vệ nhiều lớp, job test không nên có quyền hoặc network route tới production ngay từ đầu.

## 13. Nguồn tài liệu chính thức

- Spring Boot 3.5 – [Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html): profile-specific files, `@Profile`, `spring.profiles.active`, profile groups.
- Spring Boot 3.5 – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): cấu hình ngoài code, property sources và mức ưu tiên.
- Spring Framework – [`@ActiveProfiles`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html): active profiles của Spring TestContext.
- Spring Boot 3.5 – [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, MockMvc và test properties.
- Spring Framework 6.2 – [Testing Client Applications](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html): `MockRestServiceServer`, mock HTTP client và giới hạn so với HTTP mock server.
- Spring Boot 3.5 – [Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và kết nối tới container.
- OWASP – [Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lifecycle, access control, rotation và thực hành quản lý secret.

**Kết luận:** Mục tiêu không phải “test dùng file cấu hình khác” mà là “test **không thể gây tác động lên hệ thống production trong kịch bản lỗi có thể dự liệu**”. Để đạt được điều đó, hãy phối hợp **profile tường minh + test-only beans/clients + secret tách quyền + database/service cô lập + CI/network guard + assertions kiểm tra cấu hình hiệu lực**.