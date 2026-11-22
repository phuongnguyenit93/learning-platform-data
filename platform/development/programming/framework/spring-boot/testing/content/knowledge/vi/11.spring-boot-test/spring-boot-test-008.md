# Chọn classes, properties và các tùy chọn khởi động cần kiểm chứng với @SpringBootTest

## 1. Mục tiêu: biết chính xác ApplicationContext nào đã được khởi động

Trong Spring Boot testing, chỉ viết `@SpringBootTest` và kiểm tra `contextLoads()` chưa đủ để chứng minh ứng dụng được khởi động **đúng cấu hình**. Một context có thể load được với cấu hình mặc định nhưng không nạp profile QA, không chạy tùy chỉnh trong `main()`, không tạo bean theo feature flag, hoặc không có HTTP listener dù test tưởng đang kiểm tra network thực. Ngược lại, một test chỉ cần vài beans có thể vô tình load tất cả JDBC, Kafka, Redis, scheduler và exporter, dẫn đến lỗi do hạ tầng không liên quan mục tiêu.

`@SpringBootTest` cung cấp **năm nhóm tùy chọn cần hiểu rõ**:

1. `classes`: những class nào được dùng làm **nguồn cấu hình** để tạo context.
2. `properties`/`value`: những key-value nào được đưa vào Spring `Environment` trước startup.
3. `args`: những command-line arguments nào được chuyển cho `SpringApplication` và `ApplicationArguments`.
4. `webEnvironment`: tạo mock web context, non-web context, hay embedded HTTP server.
5. `useMainMethod`: có dùng phương thức `main(String[])` và các tùy chỉnh trong main không.

Ngoài ra còn có `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@TestConfiguration`, `@Import`, context caching và bean conditions ảnh hưởng hành vi cuối cùng.

Mục tiêu sau bài là người học có thể **chọn cấu hình với lý do rõ ràng** và viết assertions cho hiệu ứng thực tế: giá trị đã bind vào `@ConfigurationProperties`, bean có/không tồn tại, active profiles, CLI options, server port/HTTP response. Đây là bài Knowledge độc lập cho menu cha **`@SpringBootTest`** của Spring Boot testing, dùng **Java 17+, Spring Boot 3.5.x**, Gradle Groovy DSL và JUnit Jupiter.

## 2. Bảng thuộc tính cần nhớ

| Thuộc tính | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `classes` | `Class<?>[]` | Rỗng | Nguồn cấu hình tạo ApplicationContext; nếu không chỉ định thì dùng cơ chế phát hiện cấu hình |
| `properties` | `String[]` | Rỗng | Thêm test property `key=value` vào Environment |
| `value` | `String[]` | Rỗng | **Alias của `properties`**, không phải alias của `classes` |
| `args` | `String[]` | Rỗng | Các argument truyền vào SpringApplication |
| `webEnvironment` | `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE` | `MOCK` | Có tạo HTTP server thật hay không |
| `useMainMethod` | `NEVER`, `WHEN_AVAILABLE`, `ALWAYS` | `NEVER` | Chính sách gọi `main` của application |

Cú pháp minh họa:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    properties = {
        "demo.region=lab",
        "demo.batch-size=3"
    },
    args = {
        "--job.mode=validate",
        "input.csv"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER)
class ConfigurationExampleTest {
    // Chỉ là fragment; full tests ở phần thực hành.
}
```

Không cần đặt đủ mọi thuộc tính trong mỗi test. Hãy bắt đầu từ câu hỏi “mình đang muốn chứng minh **cấu hình và hành vi startup** nào?” rồi chọn tùy chọn tối thiểu.

```text
                           JUnit Jupiter
                                |
                        @SpringBootTest
                                |
             +------------------+------------------+
             |                  |                  |
         classes           properties,args       webEnvironment
             |                  |                  |
     Root configuration     Environment,       NONE / MOCK /
     and component scan   ApplicationArguments  RANDOM_PORT
             |                  |                  |
             +------------------+------------------+
                                |
                          SpringApplication
                       useMainMethod policy
                                |
                       ApplicationContext
                                |
            asserts về beans, effective properties,
              profile, CLI args, port và HTTP
```

## 3. `classes`: cấu hình khởi tạo, không phải danh sách bean cần assert

Khi không chỉ định `classes`, Spring Boot tìm một nested `@Configuration` phù hợp trước, rồi tìm `@SpringBootConfiguration` hoặc `@SpringBootApplication` khi đi lên package hierarchy từ package test. Một dự án đặt ứng dụng ở `com.example.bootlab.DemoApplication` và tests ở `com.example.bootlab` thường được cấu hình tự phát hiện.

### 3.1. Chọn rõ application root

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullBootConfigTest {
}
```

Ở đây `DemoApplication` có `@SpringBootApplication`, nên Boot vẫn có thể **component scan toàn base package của application**. `classes=DemoApplication.class` không có nghĩa context chỉ chứa một class hoặc một bean duy nhất; nó chỉ xác định nguồn cấu hình gốc.

### 3.2. Chọn context tối thiểu thực sự

```java
@SpringBootTest(
    classes = MinimalRoot.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MinimalContextTest {
    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class MinimalRoot {
        @Bean Marker marker() {
            return new Marker("test-only");
        }
    }
}
```

Fragment này cần khai báo `Marker` và các imports; phiên bản hoàn chỉnh ở mục thực hành. `MinimalRoot` không có `@ComponentScan`, nên các `@Service` của ứng dụng không tự được đưa vào. Nhưng có `@EnableAutoConfiguration`, vì vậy **vẫn có Boot infrastructure beans** tương ứng classpath; không nên tuyên bố context chỉ có đúng một bean.

Nếu bài test chỉ cần `@Configuration` rất nhỏ và không cần Boot semantics, `@ContextConfiguration` hoặc `ApplicationContextRunner` có thể nhẹ hơn.

### 3.3. `classes` và `@ContextConfiguration`

Spring TestContext cho phép `@ContextConfiguration(classes=...)`; `@SpringBootTest(classes=...)` cung cấp một đường khai báo ngắn hơn cùng mục tiêu chọn nguồn cấu hình dưới Boot test loader. Đừng khai báo hai bộ classes mâu thuẫn rồi đoán framework sẽ “cộng tất cả” theo thứ tự mình nghĩ. Với tests có yêu cầu rất cụ thể, chọn một đường cấu hình rõ và đọc actual bean graph.

### 3.4. Nested @Configuration và @TestConfiguration khác nhau

Một nested `@Configuration` có thể được dùng **thay** primary application configuration khi test không chỉ định classes. Ngược lại, nested `@TestConfiguration` thường là cấu hình **bổ sung** cho Boot application. Top-level `@TestConfiguration` không tự được component scan như `@Configuration` production; có thể dùng `@Import` để lựa chọn một cách tường minh.

Khi chỉ cần thêm một bean test (fake clock, diagnostic marker), dùng `@TestConfiguration` + `@Import`, **không** sửa `@SpringBootApplication` hoặc scan toàn bộ thư mục test. Nếu định override một bean thật, dùng chính sách `@MockitoBean`/`@TestBean` và xem bean overriding rules, không tự tạo trùng tên rồi mặc định nó sẽ replace.

## 4. `properties` và alias `value`: cấu hình được đưa vào trước startup

```java
@SpringBootTest(properties = {
    "demo.region=inline",
    "demo.batch-size=3",
    "demo.enabled=false"
})
```

cung cấp các key `key=value` cho context. `value` là alias:

```java
@SpringBootTest(value = "demo.region=alias")
```

tương đương:

```java
@SpringBootTest(properties = "demo.region=alias")
```

Hai annotation snippets này chỉ là các cách viết **thay thế**. Hãy dùng `properties` khi nhiều keys để làm rõ đây không phải `classes`.

### 4.1. Property string khác bean đã bind

Giả sử application config có:

```properties
demo.region=base
demo.batch-size=8
demo.enabled=true
demo.feature.enabled=false
```

Nếu Java record `@ConfigurationProperties(prefix="demo")` có các trường `region`, `batchSize`, `enabled`, test tốt nên kiểm:
- `Environment.getProperty("demo.region")` là `inline`.
- `RuntimeSettings.region()` cũng là `inline`.
- `RuntimeSettings.batchSize() == 3`, `enabled() == false`.
- Conditional bean dựa vào `demo.feature.enabled` có/không theo cấu hình startup.

Chỉ assert Environment key có giá trị không chứng minh `@ConfigurationProperties` đã được đăng ký/bind hoặc bean ứng dụng thực dùng giá trị đó. Một property sai type có thể khiến context **fail trước khi method @Test chạy**, khi binder không thể convert string thành `int`/Duration/enum.

### 4.2. Những tùy chọn có tác động sớm

- `spring.main.web-application-type=none`: yêu cầu non-web application type.
- `spring.main.web-application-type=reactive`: hữu ích nếu MVC và WebFlux cùng classpath nhưng bài test muốn reactive.
- `spring.main.lazy-initialization=true`: trì hoãn một số bean startup; có thể **che lỗi** nếu chỉ assert context load mà không truy cập bean.
- `spring.autoconfigure.exclude=...`: loại một auto-configuration, phải ghi rõ đó là **một startup mode khác** với production.
- `server.port=0`: yêu cầu server bind cổng random **khi có real server**.
- `logging.level...=DEBUG`: bật chẩn đoán, không thay thế business assertion.

Không `environment.getPropertySources().addFirst(...)` sau context refresh rồi mong `@ConditionalOnProperty` được đánh giá lại. Bean graph được quyết định trong startup; thay cấu hình cần một context run mới.

## 5. Thứ tự các property sources và tình huống đụng key

Spring Boot có Config Data từ `application.properties`/`application.yaml`, biến môi trường OS, JVM system properties, command-line options, test inline properties và các nguồn Spring TestContext.

Một số nguyên tắc kiểm chứng được:
- Test-inline `@SpringBootTest(properties=...)` ghi đè application defaults trong mẫu bài.
- `@TestPropertySource(properties=...)` có ưu tiên hơn **`@TestPropertySource(locations=...)`** với cùng key.
- `@DynamicPropertySource` đăng ký supplier để lấy giá trị runtime, rất phù hợp URL/port từ Testcontainers và mock servers.
- `args="--demo.region=cli"` thường đưa một command-line property vào `Environment`, đồng thời xuất hiện trong `ApplicationArguments`.
- `application-qa.properties` chỉ có hiệu lực khi profile `qa` active.
- Khi nhiều tầng test-specific properties cùng định nghĩa **một key**, hãy kiểm chính xác effective value trên Boot/Spring Framework version đang chạy; các tài liệu mô tả property source precedence ở các mức abstraction khác nhau. Cách dễ review nhất là tránh collisions không cần thiết.

**Không nên** dùng `System.setProperty("demo.region", "...")` ở test này rồi quên restore, vì đó là JVM global mutable state và gây flaky khi parallel. Dùng annotation/property registry per test configuration hoặc property injection rõ ràng.

### 5.1. @TestPropertySource file và inline values

```java
@SpringBootTest(properties = "demo.batch-size=2")
@TestPropertySource(
    locations = "classpath:custom-test.properties",
    properties = "demo.region=test-inline")
class SourceExample {
}
```

File `custom-test.properties` có `demo.region=file-value`, `demo.enabled=false`; inline test property ghi đè region trong file; `demo.batch-size` được đưa qua `@SpringBootTest` bằng **key khác**, không phụ thuộc thứ tự ưu tiên giữa hai annotation systems cho cùng key.

`@TestPropertySource` đọc resource properties theo TestContext, **không trực tiếp parse YAML** theo Boot Config Data. Nếu cần config YAML đa profile, nên dùng `application-qa.yaml` + `@ActiveProfiles("qa")` hoặc cơ chế `spring.config.import` rõ ràng.

`@TestPropertySource` trống có một cơ chế tự tìm file mặc định theo tên test class/package, **không** có nghĩa sẽ tự chọn `application-test.properties`. Để dễ hiểu, ghi rõ `locations` hoặc dùng `@ActiveProfiles`.

### 5.2. @DynamicPropertySource cho cấu hình tạo trong test

```java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("demo.external-uri",
            () -> "stub://local-service");
}
```

Static method trên đăng ký một supplier, không phải một plain string constant. Với Testcontainers, supplier có thể lấy `postgres::getJdbcUrl`, `getMappedPort(5432)` hoặc địa chỉ một mock HTTP server sau khi resource đã được khởi tạo. Phải quản lý lifecycle cho resource thực; **không** dùng endpoint cũ từ run khác. Mẫu `stub://` trong bài chỉ minh họa cách đọc Environment, không tạo kết nối network.

Nếu nhiều test classes/subclasses chia sẻ cached context nhưng dynamic property suppliers cuối cùng trả giá trị khác, có thể cần context isolation hoặc `@DirtiesContext`; không giả định thay giá trị static sẽ rebuild beans đã tạo.

## 6. @ActiveProfiles: profile dùng để nạp Config Data riêng

```java
@ActiveProfiles("qa")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QaProfileTest {
}
```

Khi profile `qa` được bật, Boot tìm `application-qa.properties` ngoài application defaults. Ví dụ:
- `application.properties`: `demo.region=base`, `demo.batch-size=8`, `demo.enabled=true`.
- `application-qa.properties`: `demo.region=qa-profile`, `demo.batch-size=12`.
- Bound record có `region=qa-profile`, `batchSize=12`, `enabled=true`.

Đừng chỉ assert `environment.getActiveProfiles()` chứa `qa`; test nên assert **bean đã bind** các giá trị QA. Đừng tự nạp profile production trên CI nếu profile đó kích hoạt remote services/credentials thực.

Nếu test có `@ActiveProfiles("qa")` và một `properties="demo.region=inline"`, hãy xem cái nào là nguồn contract cần kiểm. Không thể suy rằng chỉ vì profile active thì mọi property trong profile file chắc chắn thắng test inline override.

## 7. `args`: CLI startup contract, không phải alias của properties

```java
@SpringBootTest(
    args = {
        "--job.mode=dry-run",
        "input.csv",
        "--demo.region=from-cli"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CommandLineArgumentsTest {
}
```

Với `ApplicationArguments`:
- `getOptionNames()` chứa `job.mode` và `demo.region`.
- `getOptionValues("job.mode")` trả `["dry-run"]`.
- `getNonOptionArgs()` chứa `input.csv`.
- Theo mặc định `--demo.region=from-cli` cũng được SpringApplication đưa vào Environment.

| Cách khai báo | Environment | ApplicationArguments |
|---|---|---|
| `properties="job.mode=dry-run"` | Có | Không tự tạo option |
| `args="--job.mode=dry-run"` | Có, theo cơ chế CLI mặc định | Có option `job.mode` |
| `args="input.csv"` | Không tạo property `input.csv` | Có non-option argument |
| `@ActiveProfiles("qa")` | Active profile và profile config | Không tự thêm CLI argument |

Nếu application có `ApplicationRunner` hoặc `CommandLineRunner` xử lý flags như `--dry-run`, dùng `args` để test CLI integration. Nhưng runner thực có thể gửi messages hay thay đổi DB; cần fake/local dependencies phù hợp. Việc option tồn tại **không chứng minh runner đã thực thi đúng side effect**.

## 8. webEnvironment: đúng cấp web mà đề bài muốn kiểm

| Mode | Khởi động server? | Có gì để assert? | Phù hợp |
|---|---|---|---|
| `MOCK` (mặc định) | Không bind socket; mock web context nếu web stack có trên classpath | MVC mapping/filters qua MockMvc khi bật `@AutoConfigureMockMvc` | HTTP contract qua Spring MVC nhưng không cần TCP |
| `NONE` | Không có web environment | Context beans, profiles, binding, startup options | Service/config/CLI |
| `RANDOM_PORT` | **Có**, OS cấp cổng ngẫu nhiên | `@LocalServerPort`, HTTP client response thật | Servlet/Netty server integration |
| `DEFINED_PORT` | **Có**, `server.port` hoặc mặc định 8080 | Fixed-port server startup | Ít dùng CI parallel vì port collision |

**Phân biệt quan trọng:** `MOCK` không có nghĩa repositories/services đều mock. `@SpringBootTest(MOCK)` là **full application context** với web environment giả lập; muốn mock service thì phải thay nó một cách tường minh. Với Servlet MVC, cần `@AutoConfigureMockMvc` nếu muốn inject `MockMvc`; `@WebMvcTest` là slice annotation khác và đã auto-configure MockMvc.

`RANDOM_PORT` tự khởi động real HTTP server, test có thể dùng `@LocalServerPort` và `TestRestTemplate` trên classpath Boot test. `server.port=0` chỉ là cấu hình bind; giá trị **port thực** được biết sau startup. `DEFINED_PORT` có nguy cơ `BindException` khi nhiều CI workers chạy cùng project trên host; ví dụ bài tập tránh fixed port.

Với `@SpringBootTest(RANDOM_PORT)`, client và servlet server xử lý trên **threads khác nhau**. `@Transactional` của JUnit test thread mặc định rollback phần transaction được test manager quản lý ở thread đó; server HTTP request có transaction riêng và có thể commit. Khi có DB cần cleanup/data isolation thay vì cho rằng `@Transactional` rollback HTTP writes.

Nếu cả Spring MVC và WebFlux nằm trên classpath, Boot thường ưu tiên MVC. Muốn test ứng dụng reactive dùng `spring.main.web-application-type=reactive` đúng lúc và `WebTestClient`; đừng coi mọi `@SpringBootTest(MOCK)` là một reactive context.

## 9. useMainMethod: main() có tùy chỉnh không?

Mặc định `@SpringBootTest(useMainMethod=NEVER)` **không gọi phương thức main**, mà bootstrap thông qua SpringApplication với configuration source được chọn. Điều này thường tương đương khi main chỉ:

```java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);
}
```

Nhưng nếu main thay đổi banner, additional profiles, application listeners hoặc những thuộc tính quan trọng, một test có thể không nhìn thấy tùy chỉnh đó.

```java
public static void main(String[] args) {
    SpringApplication app =
            new SpringApplication(DemoApplication.class);
    app.setAdditionalProfiles("main-mode");
    app.run(args);
}
```

Khi đó:
- `UseMainMethod.NEVER` (**default**): không chạy đoạn tùy chỉnh trên.
- `UseMainMethod.WHEN_AVAILABLE`: chạy main khi có, nếu không có thì fallback thông thường.
- `UseMainMethod.ALWAYS`: bắt buộc có và chạy main, nếu không tìm được thì test fail startup.

Test `ALWAYS` cần assert **hệ quả thật** như profile `main-mode` active và property từ `application-main-mode.properties` được bind. Nếu chính test cũng gắn `@ActiveProfiles("main-mode")`, nó có thể pass dù main không chạy — như vậy đã làm yếu mục tiêu. Mẫu code dưới đây không làm điều đó.

Đừng dùng `main` để gọi hệ thống production ngoài ý muốn hoặc `System.exit` trong test; đưa side effects vào các runner/beans có thể kiểm soát bằng profile.

## 10. Dự án chạy được: Gradle + Java 17 + Spring Boot 3.5.8

Dự án cố ý nhỏ, không có DB/Docker/broker. Các test khác nhau ở **boot configuration**, không khác nhau ở business logic.

```text
settings.gradle
build.gradle
src/main/java/com/example/bootlab/
    DemoApplication.java
    RuntimeSettings.java
    SettingsReporter.java
    FeatureFlagService.java
    ProbeController.java
src/main/resources/
    application.properties
src/test/resources/
    application-qa.properties
    application-main-mode.properties
    custom-test.properties
src/test/java/com/example/bootlab/
    DefaultConfigurationTest.java
    ExplicitConfigurationTest.java
    InlinePropertiesTest.java
    AliasPropertyTest.java
    QaProfileTest.java
    CommandLineArgumentsTest.java
    TestPropertySourceTest.java
    DynamicPropertySourceTest.java
    AdditionalTestConfigurationTest.java
    MainNeverTest.java
    MainAlwaysTest.java
    MockWebEnvironmentTest.java
    RandomPortEnvironmentTest.java
    NoneWebEnvironmentTest.java
    StartupFailureRunnerTest.java
```

### 10.1. settings.gradle

```groovy
rootProject.name = 'boot-startup-config-lab'
```

### 10.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

Spring Boot dependency management đồng bộ Spring Framework/JUnit/Mockito và Jackson. Project cần một Gradle wrapper tương thích hoặc cài Gradle; `build.gradle` không tự tạo `gradlew`.

### 10.3. application.properties

Tệp `src/main/resources/application.properties`:

```properties
demo.region=base
demo.batch-size=8
demo.enabled=true
demo.feature.enabled=false
```

### 10.4. DemoApplication.java

```java
package com.example.bootlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(RuntimeSettings.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);
        application.setAdditionalProfiles("main-mode");
        application.run(args);
    }
}
```

Main thêm profile chỉ khi được dùng. Không đặt `System.setProperty` hoặc tạo singleton mutable global trong main, tránh test state rò rỉ giữa test classes. `@EnableConfigurationProperties` đăng ký immutable record bên dưới.

### 10.5. RuntimeSettings.java

```java
package com.example.bootlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record RuntimeSettings(
        String region,
        int batchSize,
        boolean enabled) {
}
```

Record dùng constructor binding theo Spring Boot, không cần setters. Không đánh dấu thêm `@Component` rồi mong Boot xử lý constructor binding theo cùng đường; `@EnableConfigurationProperties` trên DemoApplication là nơi đăng ký bean.

### 10.6. SettingsReporter.java

```java
package com.example.bootlab;

import org.springframework.stereotype.Service;

@Service
public class SettingsReporter {

    private final RuntimeSettings settings;

    public SettingsReporter(RuntimeSettings settings) {
        this.settings = settings;
    }

    public RuntimeSettings settings() {
        return settings;
    }

    public String summary() {
        return settings.region() + "|"
                + settings.batchSize() + "|"
                + settings.enabled();
    }
}
```

Với properties mặc định, `summary()` là `base|8|true`. Khi inline overrides, nó trở thành `inline|3|false`. Đây là **bean-level proof** rằng config đã được bind và sử dụng.

### 10.7. FeatureFlagService.java

```java
package com.example.bootlab;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true")
public class FeatureFlagService {

    public String status() {
        return "feature-enabled";
    }
}
```

Với `demo.feature.enabled=false`, Spring không tạo bean này. Khi test đặt `true` **trước startup**, bean tồn tại. Điều này phân biệt property lookup với **conditional bean graph**.

### 10.8. ProbeController.java

```java
package com.example.bootlab;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final SettingsReporter reporter;

    public ProbeController(SettingsReporter reporter) {
        this.reporter = reporter;
    }

    @GetMapping(
        path = "/probe",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return reporter.summary();
    }
}
```

Một endpoint trả text thuần đủ cho hai modes `MOCK` và `RANDOM_PORT`. Khi test non-web, vẫn có thể tạo Controller bean qua component scan nhưng **không có HTTP listener**, nên không gọi `/probe`.

### 10.9. Test resource files

Tệp `src/test/resources/application-qa.properties`:

```properties
demo.region=qa-profile
demo.batch-size=12
```

Tệp `src/test/resources/application-main-mode.properties`:

```properties
demo.region=from-main-profile
```

Tệp `src/test/resources/custom-test.properties`:

```properties
demo.region=from-custom-file
demo.enabled=false
```

Các file trên tách biệt mục đích:
- `qa` được bật bằng `@ActiveProfiles("qa")`.
- `main-mode` được thêm bởi `DemoApplication.main` **chỉ khi useMainMethod tương ứng**.
- `custom-test.properties` được nạp tường minh qua `@TestPropertySource`.

Không đặt `spring.profiles.active=qa` trong main resources để ép tất cả tests cùng dùng QA; cần mỗi test nêu chính sách riêng.

## 11. JUnit kiểm chứng classes: tự discovery và gốc tối thiểu

### 11.1. DefaultConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DefaultConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    SettingsReporter reporter;

    @Test
    void discoversAppAndBindsDefaults() {
        assertThat(context.getBean(DemoApplication.class))
                .isNotNull();
        assertThat(reporter.summary())
                .isEqualTo("base|8|true");
    }

    @Test
    void disabledFlagDoesNotCreateFeatureBean() {
        assertThat(context.getBeanNamesForType(
                FeatureFlagService.class))
                .isEmpty();
    }
}
```

Hai tests đầu sử dụng package-based discovery. Assert `DemoApplication` và `SettingsReporter` tồn tại cùng default values; assert conditional feature bean **không** tồn tại.

### 11.2. ExplicitConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ExplicitConfigurationTest.MinimalRoot.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ExplicitConfigurationTest {

    record Marker(String value) {}

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class MinimalRoot {
        @Bean
        Marker marker() {
            return new Marker("minimal");
        }
    }

    @Autowired
    ApplicationContext context;

    @Test
    void usesSelectedConfigurationRoot() {
        assertThat(context.getBean(Marker.class).value())
                .isEqualTo("minimal");
    }

    @Test
    void doesNotScanFullApplicationServices() {
        assertThat(context.getBeanNamesForType(
                SettingsReporter.class))
                .isEmpty();
    }
}
```

Hai tests kiểm tra `classes` thực sự giới hạn nguồn cấu hình. `MinimalRoot` không có component scan, nên `SettingsReporter` không hiện diện dù code nằm cùng package. Đây là ví dụ **narrow Boot context**, không phải full application integration.

## 12. JUnit kiểm chứng properties, value alias và feature flag

### 12.1. InlinePropertiesTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "demo.region=inline",
        "demo.batch-size=3",
        "demo.enabled=false",
        "demo.feature.enabled=true"
    })
class InlinePropertiesTest {

    @Autowired
    SettingsReporter reporter;

    @Autowired
    ApplicationContext context;

    @Test
    void inlinePropertiesChangeBoundSettings() {
        assertThat(reporter.summary())
                .isEqualTo("inline|3|false");
        assertThat(reporter.settings().batchSize())
                .isEqualTo(3);
    }

    @Test
    void flagEnablesConditionalBeanAtStartup() {
        assertThat(context.getBean(
                FeatureFlagService.class).status())
                .isEqualTo("feature-enabled");
    }
}
```

Hai tests assert **hệ quả** của properties: record binding và conditional bean registration. Đây là một context riêng so với test dùng defaults; Spring TestContext không “thay properties đang sống” trên context cũ.

### 12.2. AliasPropertyTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    value = "demo.region=alias",
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AliasPropertyTest {

    @Autowired
    RuntimeSettings settings;

    @Test
    void valueMeansPropertiesNotClasses() {
        assertThat(settings.region()).isEqualTo("alias");
        assertThat(settings.batchSize()).isEqualTo(8);
    }
}
```

Một test minh họa alias `value`. Khi reviewer thấy `@SpringBootTest(value=...)`, phải hiểu đó là **property override**, không phải một entry point configuration class.

## 13. JUnit kiểm chứng profile và command-line arguments

### 13.1. QaProfileTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("qa")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QaProfileTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void profileSpecificConfigDataIsBound() {
        assertThat(environment.getActiveProfiles())
                .contains("qa");

        assertThat(settings.region())
                .isEqualTo("qa-profile");
        assertThat(settings.batchSize()).isEqualTo(12);
        assertThat(settings.enabled()).isTrue();
    }
}
```

Một test không chỉ đọc active profile mà còn assert `application-qa.properties` đã điều chỉnh bound properties. `contains("qa")` thích hợp hơn `containsExactly("qa")` khi environment có thêm profiles có chủ đích.

### 13.2. CommandLineArgumentsTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    args = {
        "--job.mode=dry-run",
        "input.csv",
        "--demo.region=from-cli"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CommandLineArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void exposesOptionsAndNonOptions() {
        assertThat(arguments.getOptionNames())
                .contains("job.mode", "demo.region");
        assertThat(arguments.getOptionValues("job.mode"))
                .containsExactly("dry-run");
        assertThat(arguments.getNonOptionArgs())
                .containsExactly("input.csv");
    }

    @Test
    void cliPropertyOverridesBaseConfig() {
        assertThat(environment.getProperty("demo.region"))
                .isEqualTo("from-cli");
        assertThat(settings.region())
                .isEqualTo("from-cli");
    }
}
```

Hai tests kiểm tra cả `ApplicationArguments` và bound property. Nếu test chỉ có `properties="job.mode=dry-run"`, `ApplicationArguments` sẽ **không** tự có option `job.mode`. Tránh trộn `args` và `properties` cho **cùng key** chỉ để “xem cái nào thắng”; bài mẫu phân tách mục tiêu.

## 14. JUnit: @TestPropertySource và @DynamicPropertySource

### 14.1. TestPropertySourceTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "demo.batch-size=2")
@TestPropertySource(
    locations = "classpath:custom-test.properties",
    properties = "demo.region=from-test-inline")
class TestPropertySourceTest {

    @Autowired
    RuntimeSettings settings;

    @Test
    void fileAndInlineTestSourcesAreApplied() {
        assertThat(settings.region())
                .isEqualTo("from-test-inline");
        assertThat(settings.batchSize()).isEqualTo(2);
        assertThat(settings.enabled()).isFalse();
    }
}
```

Một test chứng minh file riêng cung cấp `demo.enabled=false`, inline `@TestPropertySource` ghi đè `demo.region` của file, còn `@SpringBootTest` cung cấp **key khác** `demo.batch-size=2`.

### 14.2. DynamicPropertySourceTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DynamicPropertySourceTest {

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("demo.external-uri",
            () -> "stub://local-service");
    }

    @Autowired
    Environment environment;

    @Test
    void readsValueFromRegisteredSupplier() {
        assertThat(environment.getProperty(
                "demo.external-uri"))
                .isEqualTo("stub://local-service");
    }
}
```

Một test khẳng định property supplier được đăng ký trước khi context dùng nó. URI `stub://local-service` chỉ là **giá trị minh họa**, không có remote service được mở hay gọi. Với Testcontainers, supplier có thể sử dụng `container::getJdbcUrl`; không được suy rằng static container của một JVM là resource chung cho nhiều Gradle forks.

## 15. JUnit: @TestConfiguration bổ sung chứ không thay ứng dụng

### AdditionalTestConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(AdditionalTestConfigurationTest.Extras.class)
class AdditionalTestConfigurationTest {

    record TestMarker(String text) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class Extras {
        @Bean
        TestMarker marker() {
            return new TestMarker("additional");
        }
    }

    @Autowired
    TestMarker marker;

    @Autowired
    SettingsReporter reporter;

    @Test
    void addsTestBeanAndKeepsProductionWiring() {
        assertThat(marker.text()).isEqualTo("additional");
        assertThat(reporter.summary())
                .isEqualTo("base|8|true");
    }
}
```

Một test minh họa cấu hình phụ được `@Import` tường minh. Context vẫn có `SettingsReporter` của app đầy đủ. So sánh với `ExplicitConfigurationTest`: ở đó root được chọn **không scan app service**; hai trường hợp không nên trộn lẫn.

## 16. JUnit: useMainMethod NEVER vs ALWAYS

### 16.1. MainNeverTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    properties = "demo.test-marker=never",
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER)
class MainNeverTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void skipsMainCustomization() {
        assertThat(settings.region()).isEqualTo("base");
        assertThat(environment.getActiveProfiles())
                .doesNotContain("main-mode");
    }
}
```

Một test cho default policy `NEVER`. `demo.test-marker` chỉ tách cache key rõ ràng với test `ALWAYS`; nó không ảnh hưởng app logic. Test giả định CI không chủ động bật profile `main-mode` từ bên ngoài; khi chạy project thực cần kiểm soát active profiles.

### 16.2. MainAlwaysTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    properties = "demo.test-marker=always",
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainAlwaysTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void mainAddsProfileAndLoadsItsSettings() {
        assertThat(environment.getActiveProfiles())
                .contains("main-mode");
        assertThat(settings.region())
                .isEqualTo("from-main-profile");
        assertThat(settings.batchSize()).isEqualTo(8);
    }
}
```

Một test bắt buộc dùng main method; main thêm `main-mode`, Config Data nạp file profile và bind record. Nếu MainAlwaysTest cũng dùng `@ActiveProfiles("main-mode")`, nó có thể pass dù main không chạy; sample **tránh điều đó**. `WHEN_AVAILABLE` có thể test riêng bằng cùng mẫu nếu muốn đảm bảo fallback khi không có main method phù hợp.

## 17. JUnit: lựa chọn môi trường web

### 17.1. MockWebEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "demo.region=mock")
@AutoConfigureMockMvc
class MockWebEnvironmentTest {

    @Autowired
    MockMvc mvc;

    @Test
    void checksMvcWiringWithoutTcpPort() throws Exception {
        mvc.perform(get("/probe"))
            .andExpect(status().isOk())
            .andExpect(content().string("mock|8|true"));
    }
}
```

Đây là một **full application context test dùng mock Servlet request**. Nó kiểm mapping/controller/service thật nhưng **không** kiểm embedded Tomcat bind socket. Không nhầm với `@WebMvcTest`: annotation đó nạp web slice và thường mock service.

### 17.2. RandomPortEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "demo.region=socket")
class RandomPortEnvironmentTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void realServerBindsRandomPortAndResponds() {
        assertThat(port).isGreaterThan(0);
        assertThat(client.getForObject(
                "/probe", String.class))
                .isEqualTo("socket|8|true");
    }
}
```

`TestRestTemplate` do Boot cấu hình cho `RANDOM_PORT` có root URI tới local server; `getForObject("/probe", ...)` được resolve tới port của test. Không hard-code port 8080. Đây là một test HTTP thực qua loopback, **không** phải external service.

### 17.3. NoneWebEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NoneWebEnvironmentTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    RuntimeSettings settings;

    @Test
    void hasBeansButNoServletWebServerContext() {
        assertThat(context).isNotInstanceOf(
                ServletWebServerApplicationContext.class);
        assertThat(settings.region()).isEqualTo("base");
    }
}
```

`NONE` tạo non-web context và vẫn có bound business/configuration beans. Không gọi `@LocalServerPort` trong mode này. `DEFINED_PORT` không có runnable test riêng ở đây để tránh chiếm fixed port khi nhiều CI jobs chạy song song; nếu phải test một port chính xác, cấp môi trường/port lease độc quyền.

## 18. Startup failure là một hợp đồng âm cần test riêng

Một cấu hình sai (thiếu property bắt buộc, trùng bean, không bind được integer) có thể làm `@SpringBootTest` fail **trước khi JUnit @Test method chạy**. Để kiểm “context phải fail với cấu hình không hợp lệ” mà vẫn giữ suite chính có thể hoàn tất, dùng `ApplicationContextRunner` thử từng cấu hình độc lập.

### StartupFailureRunnerTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

class StartupFailureRunnerTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GuardConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    static class GuardConfiguration {
        @Bean
        String startupGuard(Environment env) {
            boolean shouldFail = env.getProperty(
                "demo.force-startup-failure",
                Boolean.class, false);

            if (shouldFail) {
                throw new IllegalStateException(
                    "intentional test-only failure");
            }
            return "ready";
        }
    }

    @Test
    void validSettingsAllowBeanCreation() {
        runner.withPropertyValues(
                "demo.force-startup-failure=false")
            .run(ctx -> {
                assertThat(ctx).hasNotFailed();
                assertThat(ctx).hasBean("startupGuard");
                assertThat(ctx.getBean("startupGuard"))
                    .isEqualTo("ready");
            });
    }

    @Test
    void invalidSettingsFailStartupAsExpected() {
        runner.withPropertyValues(
                "demo.force-startup-failure=true")
            .run(ctx -> {
                assertThat(ctx).hasFailed();
                assertThat(ctx.getStartupFailure())
                    .isNotNull();
            });
    }
}
```

Hai tests này chỉ kiểm **GuardConfiguration** nhỏ trong `ApplicationContextRunner`, không khởi động full Boot application hay web server. Positive run có bean, negative run có startup failure. Đừng dùng `ApplicationContextRunner` rồi khẳng định đã kiểm TCP port, full JPA auto-configuration hoặc main method customization; những contract đó thuộc `@SpringBootTest` đúng mode.

## 19. Ma trận số tests và phạm vi

| JUnit class | Thứ được kiểm chứng | `@Test` |
|---|---|---:|
| DefaultConfigurationTest | Boot root detection, defaults, feature absent | 2 |
| ExplicitConfigurationTest | Narrow configuration classes, no component scan | 2 |
| InlinePropertiesTest | Bound record, conditional bean | 2 |
| AliasPropertyTest | `value` alias cho properties | 1 |
| QaProfileTest | Active profile và file QA | 1 |
| CommandLineArgumentsTest | CLI options/non-options, CLI property | 2 |
| TestPropertySourceTest | Inline properties override file ở cùng annotation | 1 |
| DynamicPropertySourceTest | Dynamic supplier property | 1 |
| AdditionalTestConfigurationTest | Test-only bean thêm vào full config | 1 |
| MainNeverTest | Không dùng main | 1 |
| MainAlwaysTest | Main thêm profile | 1 |
| MockWebEnvironmentTest | MockMvc không mở TCP socket | 1 |
| RandomPortEnvironmentTest | Real HTTP trên port động | 1 |
| NoneWebEnvironmentTest | Non-web context | 1 |
| StartupFailureRunnerTest | Positive + negative config startup | 2 |
| **Tổng** | **15 classes** | **20 methods** |

Các số trên là **số methods được viết/expected discovery từ source**, không phải runtime test result. Dự án chưa chạy Gradle/JUnit tại thời điểm soạn nội dung. Khi thực thi phải đọc reports và task state để xác định executed, failed, skipped hoặc cached tests.

## 20. Chạy đúng task Gradle, đọc đúng kết quả

Với Gradle wrapper đã có trong project:

```bash
./gradlew test
./gradlew test --tests "com.example.bootlab.DefaultConfigurationTest"
./gradlew test --tests "com.example.bootlab.ExplicitConfigurationTest"
./gradlew test --tests "com.example.bootlab.InlinePropertiesTest"
./gradlew test --tests "com.example.bootlab.CommandLineArgumentsTest"
./gradlew test --tests "com.example.bootlab.MainAlwaysTest"
./gradlew test --tests "com.example.bootlab.RandomPortEnvironmentTest"
./gradlew test --tests "com.example.bootlab.StartupFailureRunnerTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.bootlab.InlinePropertiesTest"
.\gradlew.bat test --tests "com.example.bootlab.RandomPortEnvironmentTest"
```

Gradle `--tests` lọc tên class/method, **không** quyết định `@SpringBootTest` classes/properties. Các annotations vẫn điều khiển context startup của những tests được chọn.

Kiểm reports:
- `build/reports/tests/test/index.html`: HTML report.
- `build/test-results/test/`: JUnit XML.
- Console `--info` và root exception cho context startup issues.
- Trạng thái `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc `SKIPPED`.
- Khi cần chắc chắn test được chạy mới, có thể dùng `--rerun-tasks` rồi đọc report.

Nếu gọi `./gradlew test --tests "com.example.bootlab.MainAlwaysTest"`, JUnit chỉ chạy class đã chọn; **main method policy** vẫn được Boot áp dụng cho context. `BUILD SUCCESSFUL` có task cached không phải bằng chứng mọi method vừa được chạy lại trong lần build hiện tại.

### 20.1. Kỳ vọng từ code, không phải stdout đã đo

| Startup scenario | Kết quả thiết kế |
|---|---|
| Default NONE | `base|8|true` |
| Inline properties | `inline|3|false` |
| Feature default | `FeatureFlagService` không tồn tại |
| Feature bật inline | `FeatureFlagService` tồn tại |
| Alias `value` | region `alias` |
| `@ActiveProfiles("qa")` | region `qa-profile`, batchSize 12 |
| Args `--demo.region=from-cli` | bound region `from-cli` |
| `@TestPropertySource` | region `from-test-inline`, enabled false |
| Dynamic source | `demo.external-uri=stub://local-service` |
| `UseMainMethod.NEVER` | region `base` |
| `UseMainMethod.ALWAYS` | region `from-main-profile` |
| MOCK MVC | GET /probe body `mock|8|true` |
| RANDOM_PORT | GET /probe body `socket|8|true` |
| NONE | Không có ServletWebServerApplicationContext |
| ContextRunner invalid | `hasFailed()` |

Nếu một expected value khác khi chạy thực tế, kiểm tra external profiles/CI variables, property-source ordering và context cache thay vì đổi assert một cách tùy tiện.

## 21. Context caching, parallel và chi phí startup

Spring TestContext cache `ApplicationContext` khi context key tương đương: configuration classes, property sources, active profiles, context customizers (bao gồm `@DynamicPropertySource`, bean overrides), context loader và các yếu tố liên quan. Các tests trong bài có chủ đích dùng nhiều context variants để chứng minh `classes/properties/webEnvironment` thay đổi hiệu quả startup.

Hệ quả vận hành:
- Một cached context **không tự rebind** singleton properties hay đánh giá lại conditional beans nếu bạn thay một property bằng cách mutate Environment sau startup.
- `@DirtiesContext` có thể loại context khỏi cache; chỉ dùng khi thực sự có shared state cần reset, vì nó làm tốn bootstrap và có thể ảnh hưởng tests concurrent.
- Gradle `maxParallelForks>1` tạo JVM test processes riêng; context cache **không chia sẻ xuyên JVM**, nhưng external DB/Redis/file paths có thể vẫn chung.
- `@MockitoBean` trong context bị dùng đồng thời có thể có race khi nhiều tests stubbing/reset cùng mock.
- `webEnvironment=RANDOM_PORT` tạo embedded server và có thể tốn tài nguyên hơn `NONE`; nhiều forks có thể làm CPU/RAM/network resources tăng.
- Bật `spring.main.lazy-initialization=true` có thể trì hoãn bean failures, nên không dùng làm cách “sửa” contextLoads khi muốn khẳng định đầy đủ Boot startup.

Một bộ test tối ưu không cần khởi động full context cho từng phép tính. Với pure service method không phụ thuộc Spring, dùng JUnit thuần. Với web mapping, `@WebMvcTest`; với conditional auto-config, `ApplicationContextRunner`; với full Boot wiring và server, `@SpringBootTest` đúng tùy chọn.

## 22. Chẩn đoán khi Spring context không load

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `Unable to find a @SpringBootConfiguration` | Test ngoài package tree hoặc thiếu root | Chỉ rõ `classes=DemoApplication.class`, sửa cấu trúc package |
| Có nhiều Boot configuration candidates | Nhiều main classes | Chọn explicit source |
| Bean app biến mất | Nested `@Configuration` thay root, hoặc `classes` quá hẹp | Dùng full root hoặc `@TestConfiguration` để bổ sung |
| NoSuchBeanDefinitionException RuntimeSettings | Chưa bật configuration properties binding | Kiểm `@EnableConfigurationProperties`/`@ConfigurationPropertiesScan` |
| Binding error ở batchSize | Property không convert thành int | Sửa key/giá trị, assert negative startup riêng |
| Conditional bean không có | Feature off, scan thiếu, condition khác | Check effective config và `ConditionEvaluationReport` |
| `application-qa.properties` không có tác dụng | QA chưa active | `@ActiveProfiles("qa")` |
| Test chính sách main không thấy main-mode | `useMainMethod=NEVER` | Chọn `ALWAYS` nếu thật sự cần kiểm main |
| `ALWAYS` fail startup | Không tìm được main phù hợp | Đúng entry point hoặc refactor startup |
| AppArgs rỗng | Đặt `properties` thay `args` | Đặt `args={"--key=value"}` |
| `@TestPropertySource` file không tồn tại | Đường dẫn sai | Dùng resource path cụ thể |
| Dynamic URL sai port | Resource chưa ready, supplier lấy endpoint cũ | Quản lý startup/lifecycle |
| MockMvc không inject | `@SpringBootTest` thiếu `@AutoConfigureMockMvc` | Bật MockMvc cho mock web mode |
| `@LocalServerPort` không có | MOCK/NONE không bind server | Dùng RANDOM_PORT khi cần network |
| `BindException` HTTP port | Dùng DEFINED_PORT/fixed port | Dùng RANDOM_PORT hoặc cấp port độc quyền |
| Test @Transactional không rollback HTTP writes | HTTP server thread khác JUnit test thread | Explicit cleanup/data isolation |
| Test chạy quá chậm | Full context nạp external dependencies | Dùng slice/runner/fake phù hợp |
| Fail trước @Test method | Bean startup/condition/binding lỗi | Đọc full root cause, test negative bằng runner |
| Chỉ fail khi parallel | Context/mock/static/resource state dùng chung | Giảm concurrency để tìm race, tách tài nguyên |
| Context cache dùng sai cấu hình | Profiles/customizers không như nghĩ | Kiểm context key, tránh shared mutable state |
| Gradle báo thành công nhưng 0 tests | Test discovery/filter/cache | Đọc task status và HTML/XML reports |

### 22.1. Trình tự điều tra có bằng chứng

1. Lấy **root cause** bên dưới `Failed to load ApplicationContext`.
2. Ghi lại exact test class và annotation: `classes`, `webEnvironment`, `useMainMethod`, `args`, `properties`.
3. Xác định active profiles và source của giá trị bất thường.
4. Nếu bean thiếu, kiểm component scan và condition evaluation.
5. Kiểm actual bound `RuntimeSettings`, không chỉ mở file `application.properties`.
6. Nếu random port, kiểm `@LocalServerPort`; nếu fixed port fail, kiểm process khác dùng port.
7. Nếu tests liên quan DB/HTTP thread, xác định transaction ownership, rollback/cleanup.
8. Nếu lỗi chỉ xuất hiện trên CI, kiểm environment variables, Java/Gradle version, forks, remote services.
9. Tách minimal context hoặc dùng `ApplicationContextRunner` để tái hiện một property condition.
10. Sửa root cause và chạy lại đúng Test task, đối chiếu reports.

## 23. Checklist QA cho bài thực hành

- [ ] Hiểu `classes` xác định configuration sources, không phải danh sách beans duy nhất.
- [ ] Hiểu cơ chế Boot tự tìm `@SpringBootConfiguration`/ `@SpringBootApplication`.
- [ ] Không để nested `@Configuration` vô tình thay root.
- [ ] Dùng `@TestConfiguration` + `@Import` khi cần thêm bean.
- [ ] Dùng `properties`/`value` đúng alias và đúng key.
- [ ] Check bound `@ConfigurationProperties` cùng actual bean graph.
- [ ] `@ConditionalOnProperty` được kiểm bằng bean có/không.
- [ ] `@ActiveProfiles` được dùng khi cần profile-specific config.
- [ ] Test không truy cập production endpoints/credentials.
- [ ] `@TestPropertySource` file và inline values đúng thứ tự.
- [ ] `@DynamicPropertySource` lấy resource endpoint đúng lifecycle.
- [ ] `args` dùng để kiểm `ApplicationArguments`, không nhầm `properties`.
- [ ] Không dùng collisions cùng key giữa nhiều property sources thiếu lý do.
- [ ] Chọn `webEnvironment=NONE` cho non-web startup.
- [ ] Chọn `MOCK` + MockMvc cho full MVC mock exchange.
- [ ] Chọn `RANDOM_PORT` khi cần embedded server thực.
- [ ] Tránh `DEFINED_PORT` trong CI song song nếu không có port lease.
- [ ] Hiểu `@Transactional` test thread không rollback writes của HTTP server thread.
- [ ] Chọn `useMainMethod=ALWAYS` khi kiểm tùy chỉnh main; assert hiệu ứng thật.
- [ ] Không tùy tiện đặt `@ActiveProfiles` trùng với profile do main kích hoạt trong test chính sách main.
- [ ] Dùng `ApplicationContextRunner` cho startup failure có chủ đích.
- [ ] Context cache, `@DirtiesContext`, Mockito mocks và Gradle forks được kiểm soát.
- [ ] Không coi `contextLoads()` là kiểm chứng đủ của startup options.
- [ ] Gradle/JUnit reports xác nhận tests đã chạy trước khi báo runtime PASS.

## 24. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment`, `useMainMethod`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): Boot context discovery, main, arguments và web modes.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): property source ordering, profile files và type-safe binding.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `ApplicationArguments` và startup features.
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html): conditional bean report.
- [Spring Framework — @TestPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): test property locations/inline syntax.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): dynamic registered property suppliers.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context cache keys, reuse, isolation.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, reports và test filtering.

**Kết luận:** `@SpringBootTest` không chỉ kiểm tra context có load được. `classes` chọn **bean graph** có thể hình thành; `properties`, `@ActiveProfiles` và dynamic test sources chọn **cấu hình**; `args` kiểm **CLI behavior**; `webEnvironment` quyết định **mock hay real HTTP server**; `useMainMethod` kiểm **tùy chỉnh trong main()**. Một test tốt phải quan sát hệ quả thật sau startup — bound settings, conditional bean, active profile, arguments, port, HTTP response — với dữ liệu và tài nguyên độc lập, không chỉ đưa annotation vào rồi hy vọng bootstrap đúng.