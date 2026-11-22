# `ApplicationRunner`, `CommandLineRunner` và tác động khi `@SpringBootTest` tải ứng dụng

## 1. Vấn đề thực tế

Một test chỉ có ý định xác minh service hoặc repository:

```java
@SpringBootTest
class OrderServiceTest {
    @Autowired OrderService service;

    @Test
    void calculatesTotal() {
        // Kiểm tra logic đơn hàng.
    }
}
```

Nhưng lúc test khởi động, chương trình có thể tự chạy **khởi tạo dữ liệu**, **đồng bộ catalog**, **mở job**, **gọi API**, **xóa cache** hoặc **gửi email**, dù nội dung `@Test` chưa bắt đầu. Nguyên nhân có thể là một bean triển khai `ApplicationRunner` hoặc `CommandLineRunner`.

Đây là điểm then chốt: **`@SpringBootTest` tạo `ApplicationContext` bằng cơ chế `SpringApplication`. Nếu runner là bean trong context ấy và không bị vô hiệu hóa, Spring Boot gọi `run(...)` của runner ở giai đoạn khởi động — trước khi các phương thức test bắt đầu.** `webEnvironment = NONE` chỉ tắt web environment, **không tự tắt startup runners**.

Với code production có side effect, điều này có thể gây:

- Ghi hoặc xóa dữ liệu ngoài fixture của test; dữ liệu seed bị chạy nhiều lần.
- Gọi các đối tác HTTP, message broker hoặc database không có sẵn trong CI.
- Test fail tại bước `Failed to load ApplicationContext`, trước khi một assertion được thực hiện.
- Suite chậm do import dữ liệu, rebuild index hoặc warm-up chạy khi tạo context.
- Kết quả test không ổn định vì Spring TestContext **cache context**, không chạy runner theo từng method test.
- Dữ liệu được ghi khi startup không được rollback bởi `@Transactional` trên test method.

Bài học này giải thích thời điểm và cơ chế gọi runner, sự khác nhau giữa hai interface, cách kiểm thử hành vi thật, cách tắt side effect một cách có chủ đích và những lựa chọn thiết kế an toàn cho Spring Boot.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết `ApplicationRunner`/`CommandLineRunner` đúng API, biết chúng là **bean** được Spring Boot tìm và gọi.
2. Phân biệt `ApplicationArguments` đã parse option với `String... args` nguyên bản.
3. Xác định chính xác thứ tự quan trọng: **context refresh → `ApplicationStartedEvent` → runners → `ApplicationReadyEvent`**.
4. Giải thích vì sao `@SpringBootTest` có thể chạy startup code trước `@BeforeEach` hoặc `@Test`, dù không gọi `main` của ứng dụng.
5. Kiểm soát runner bằng `@ConditionalOnProperty`, `@Profile` hoặc thiết kế `@Bean`/port có chủ đích; không dựa vào mẹo test dễ vỡ.
6. Kiểm tra runner riêng như một Java component và kiểm tra tích hợp khi `SpringApplication` thật khởi động.
7. Nhận biết rủi ro transaction, context cache, database, HTTP, message broker, ordering, retry/idempotency và lỗi khởi động.
8. Dựng được bài mẫu Java 17 + Spring Boot 3.3 + JUnit Jupiter với cả trường hợp **runner bật** và **runner tắt**.

## 3. Hai interface: giống và khác

Cả hai thuộc package `org.springframework.boot` và có một phương thức `run`:

```java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

Đây là **chữ ký API được rút gọn để giải thích**, không phải hai interface cần tự định nghĩa trong dự án. Các interface thật được Spring Boot cung cấp.

| Đặc điểm | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Chữ ký | `run(ApplicationArguments args)` | `run(String... args)` |
| Dữ liệu truyền vào | Đối tượng chứa raw args và các nhóm đã parse | Mảng chuỗi đối số nguyên bản |
| Đọc `--mode=verify` | `args.getOptionValues("mode")` | Tự xử lý chuỗi hoặc truyền cho parser riêng |
| Đọc non-option `seed.csv` | `args.getNonOptionArgs()` | Tìm trong `String[]` theo cú pháp chương trình |
| Dùng khi | Cần tách option/non-option rõ ràng | Muốn xử lý đối số raw, CLI đơn giản |
| Cách được gọi | Spring Boot gọi bean khi startup | Spring Boot gọi bean khi startup |
| Sắp thứ tự | `@Order` hoặc `Ordered` | `@Order` hoặc `Ordered` |
| Trả kết quả | `void`, có thể ném exception | `void`, có thể ném exception |

Một số chức năng của `ApplicationArguments`:

- `getSourceArgs()`: mảng đối số gốc được truyền vào `SpringApplication.run`.
- `containsOption("mode")`: có option tên `mode` hay không.
- `getOptionValues("mode")`: danh sách giá trị của option, có thể trả `null` khi option không tồn tại; kiểm tra trước khi dùng.
- `getOptionNames()`: tập tên option.
- `getNonOptionArgs()`: danh sách đối số không thuộc option.

Ví dụ với `{"--mode=verify", "seed.csv"}`, option `mode` có giá trị `verify`, còn non-option là `seed.csv`. `CommandLineRunner` thấy lần lượt chuỗi `"--mode=verify"` và `"seed.csv"`. Đừng nhầm raw arguments với giá trị properties; `SpringApplication` có thể chuyển command-line options thành nguồn property trong `Environment`, nhưng đó là cơ chế liên quan, không phải định nghĩa của runner.

### 3.1. Khai báo runner như một Spring bean

Có hai cách thông dụng:

**Cách A — class có `@Component`:**

```java
@Component
class StartupReporter implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Startup reporter called");
    }
}
```

**Cách B — bean factory method:**

```java
@Configuration(proxyBeanMethods = false)
class RunnerConfiguration {
    @Bean
    CommandLineRunner reportOnStartup() {
        return args -> System.out.println("Startup command called");
    }
}
```

Hai đoạn là **mẫu minh họa độc lập**; muốn chạy cần imports Spring tương ứng và đặt trong context được scan/import. Với cách B, runner là một **bean trả về từ `@Bean`**, không cần thêm `@Component` trên lambda.

Nếu chỉ tạo `new StartupReporter()` ở đâu đó ngoài Spring và không đăng ký nó làm bean, Spring Boot **không tự tìm thấy** object đó để gọi `run`. Ngược lại, nếu chỉ gọi `new AnnotationConfigApplicationContext(...)` bằng Spring Framework thuần, việc bean implement runner tồn tại **không có nghĩa** context loader đó sẽ gọi runner; hành vi call runners nằm trong `SpringApplication`.

## 4. Timeline startup: khi nào runner được gọi?

Trong luồng `SpringApplication.run(...)` thông thường:

```text
SpringApplication.run(...)
     |
     +--> chuẩn bị Environment, đọc args / profiles / properties
     |
     +--> tạo và refresh ApplicationContext
     |      +--> bean definitions / DI
     |      +--> @PostConstruct, init callbacks của bean
     |      +--> @EventListener(ContextRefreshedEvent)
     |
     +--> ApplicationStartedEvent
     |      +--> LivenessState.CORRECT
     |
     +--> CALL RUNNERS
     |      +--> ApplicationRunner.run(ApplicationArguments)
     |      +--> CommandLineRunner.run(String...)
     |      +--> gọi theo thứ tự Ordered/@Order khi được quy định
     |
     +--> ApplicationReadyEvent
     |      +--> ReadinessState.ACCEPTING_TRAFFIC
     |
     +--> SpringApplication.run(...) hoàn tất
```

Thứ tự trên là chuỗi mốc quan trọng theo tài liệu Spring Boot, không phải toàn bộ event/listener nội bộ. Một web server có thể **đã được tạo/mở cổng** trong quá trình refresh trước `ApplicationReadyEvent`; không được hiểu “ready event chưa phát” là “không thể có request TCP”. Khi deploy, readiness probe và cổng ngoài cần được tổ chức đúng chính sách.

**So với ba điểm khác:**

| Điểm mở rộng | Mốc chạy | Ý nghĩa |
| --- | --- | --- |
| Constructor/`@PostConstruct` của singleton bean | Khi bean được tạo, thường trong refresh | Khởi tạo nội bộ bean, không phải nơi lý tưởng cho network job dài |
| `ApplicationStartedEvent` | Sau refresh, trước runner | Biết context đã refresh nhưng runner chưa được gọi |
| `ApplicationRunner`/`CommandLineRunner` | Sau started, trước ready | Startup task có thể dùng các bean đã được khởi tạo |
| `ApplicationReadyEvent` | Sau runners hoàn thành | Thông báo boot đã hoàn tất startup tasks thành công |
| `@BeforeEach` của JUnit | Chuẩn bị từng test method | Với `@SpringBootTest`, thường **sau** startup runners của context |
| `@Test` | Thực thi assertion/luồng test | Không phải mốc bật runner |

Nếu runner **ném exception** không được xử lý trong giai đoạn này, SpringApplication có thể báo startup failed, phát `ApplicationFailedEvent` và test `@SpringBootTest` fail khi tạo context. `ApplicationReadyEvent` không được phát như một lần khởi động thành công.

### 4.1. Có phải hai loại runner được chạy theo hai đợt?

Không nên giả định Spring Boot **luôn gọi tất cả `ApplicationRunner` trước rồi mới đến tất cả `CommandLineRunner`**. Framework tập hợp runner beans và áp dụng ordering cho các đối tượng thuộc cả hai interface. Dùng `@Order` hoặc `Ordered` để yêu cầu một thứ tự cụ thể; nếu hai runner không có thứ tự được quy định, đừng dựa vào tên class, thứ tự quét package hay thứ tự xuất hiện trong tệp.

```java
@Order(10)
@Component
class FirstRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // chạy trước runner @Order(20) nếu cả hai có mặt.
    }
}

@Order(20)
@Component
class SecondRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // chạy sau FirstRunner.
    }
}
```

Đây là **đoạn minh họa**, không phải hai runner cần copy vào bài mẫu ở mục 6. Nếu hai tác vụ có quan hệ bắt buộc theo nghiệp vụ, cân nhắc điều phối chúng qua **một orchestrator** hoặc dependency rõ ràng; chỉ dựa vào số `@Order` có thể khó bảo trì.

## 5. Tại sao `@SpringBootTest` lại có thể kích hoạt runners?

`@SpringBootTest` sử dụng Boot test bootstrap để tạo context qua `SpringApplication`. Khi SpringApplication chạy, nó thu thập các bean implement `ApplicationRunner`/`CommandLineRunner` và gọi chúng trong luồng startup thông thường.

**Hệ quả:** Một test chỉ cần Spring context cũng có thể:

- Chạy seed data trước khi `@Test` bắt đầu.
- Kéo repository vào database test ở startup.
- Gây outbound HTTP request từ startup job.
- Mở nhiều workflow không được test case yêu cầu.
- Fail trước khi JUnit chuẩn bị fixture trong `@BeforeEach`.

Điều này đúng về mặt cơ chế ngay cả khi bạn chọn:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ServiceContextTest {
}
```

`NONE` **không tắt SpringApplication**; nó tắt web environment. Vì vậy không dùng `webEnvironment=NONE` như một “công tắc ngắt mọi startup effect”.

### 5.1. `useMainMethod = NEVER` không tắt runner

Mặc định trong Spring Boot 3.3, `@SpringBootTest` **không gọi trực tiếp phương thức `public static void main(String[] args)`** của application class. Nó dùng class cấu hình để tạo context qua `SpringApplication`. Đây là `useMainMethod = NEVER` mặc định.

```java
@SpringBootTest(
    classes = DemoApplication.class,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER
)
class BootstrapTest {
}
```

Dù `main` không được gọi, **SpringApplication vẫn được chạy để tạo context, và runner beans hợp lệ vẫn được gọi**. Nếu production main thực hiện cấu hình quan trọng như set additional profiles/banners, có thể chọn `useMainMethod=WHEN_AVAILABLE` hoặc `ALWAYS` theo tài liệu, nhưng nó phục vụ việc chạy custom main, **không phải** cách bật/tắt runner.

| Thiết lập | Có gọi `main`? | Runners của context? |
| --- | --- | --- |
| `@SpringBootTest` mặc định | Không gọi main trực tiếp | Có, nếu bean đủ điều kiện và bootstrap thành công |
| `useMainMethod=ALWAYS` | Yêu cầu main method và gọi nó | Có trong run thông thường |
| `webEnvironment=NONE` | Không quyết định main | Vẫn có, không có web environment |
| `@ContextConfiguration` bằng Spring Framework loader thuần | Không tự gọi Boot main | Không tự có cơ chế `SpringApplication.callRunners` |
| `@WebMvcTest` | Nạp slice MVC, không phải full Boot startup | Runner thường ngoài slice, trừ khi được import/đăng ký đặc biệt |

**Lưu ý với slice tests:** Đừng suy ra `@WebMvcTest` bảo đảm runner không bao giờ có mặt. Nếu tự `@Import` một configuration chứa runner hoặc thay đổi component scan, kết quả phụ thuộc context loader và scope cụ thể. Tốt nhất tránh để runner tham gia các slice không cần nó và kiểm tra cấu hình được nạp.

### 5.2. `@Test` không được phép giả định startup vừa xảy ra

TestContext cache giúp tái sử dụng cùng `ApplicationContext` cho nhiều class/method có cùng cấu hình. Runner thường chạy khi **SpringApplication dựng context mới**, không phải cứ JUnit chạy một test method lại gọi runner.

Vì thế:

- Với một context cache hit, runner có thể **đã chạy từ test class trước đó**.
- Với cache key khác do profile/properties/mocks, một context mới có thể khởi động và runner **chạy thêm lần nữa**.
- Với `@DirtiesContext` hoặc JVM fork khác, context có thể phải load lại.
- Một test có `@Transactional` không tự tạo giao dịch bao quanh startup runner chỉ vì tên test có chữ integration.

Không viết test dựa vào “runner chạy đúng một lần trong cả suite”. Hãy thiết kế runner **idempotent** nếu side effect cần bảo đảm duy nhất và dùng dữ liệu test cô lập.

## 6. Ví dụ đầy đủ: Java 17, Spring Boot 3.3.0, JUnit Jupiter

Ví dụ tập trung vào **startup runner và tác động khi nạp ứng dụng**. Hai runner không gọi database/network; chúng ghi vào một bean audit in-memory để test quan sát được thứ tự và arguments. Tất cả runner được **bật theo property**; khi tắt, chúng không được đăng ký thành bean.

**Điểm thiết kế an toàn:** `app.startup.enabled` phải là `true` thì hai runner mới tồn tại. Nếu property không được khai báo, chúng không chạy. Điều này tránh vô tình chạy tác vụ trong CI hoặc local test khi chưa chủ động bật.

### 6.1. Cấu trúc file

```text
runner-test-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── RunnerDemoApplication.java
    │   ├── StartupAudit.java
    │   ├── ArgsStartupRunner.java
    │   └── CliStartupRunner.java
    └── test/java/example/
        ├── ArgsStartupRunnerUnitTest.java
        ├── CliStartupRunnerUnitTest.java
        ├── RunnersEnabledBootTest.java
        └── RunnersDisabledBootTest.java
```

### 6.2. Gradle build

**`settings.gradle`:**

```groovy
rootProject.name = 'runner-test-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là một build đầy đủ cho ví dụ. Spring Boot 3.3.0 là mốc cố định để tránh trộn APIs giữa các dòng. Trong dự án thực, dùng bản vá Spring Boot đã được duyệt và Gradle wrapper tương thích. Không cần `spring-boot-starter-web`, H2, database hoặc Docker.

### 6.3. Main application

**`src/main/java/example/RunnerDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RunnerDemoApplication.class, args);
    }
}
```

`main` dùng `SpringApplication.run` để khởi động ứng dụng. Spring Boot test ở phần dưới không nhất thiết gọi `main`, nhưng vẫn dùng cơ chế SpringApplication để tạo context.

### 6.4. Bean dùng ghi lại thứ tự một cách an toàn

**`src/main/java/example/StartupAudit.java`:**

```java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class StartupAudit {
    private final CopyOnWriteArrayList<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

Audit nằm trong memory của mỗi context, không ghi file/DB và không gọi dịch vụ ngoài. `CopyOnWriteArrayList` giúp thao tác thêm và đọc snapshot ổn định trong demo; nó không phải giải pháp thay thế transactional/outbox logging trong ứng dụng production.

### 6.5. `ApplicationRunner` đọc arguments đã parse

**`src/main/java/example/ArgsStartupRunner.java`:**

```java
package example;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
@ConditionalOnProperty(
        prefix = "app.startup",
        name = "enabled",
        havingValue = "true"
)
public class ArgsStartupRunner implements ApplicationRunner {
    private final StartupAudit audit;

    public ArgsStartupRunner(StartupAudit audit) {
        this.audit = audit;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> values = args.getOptionValues("mode");
        String mode = values == null || values.isEmpty()
                ? "none" : values.get(0);

        String files = String.join(",", args.getNonOptionArgs());
        audit.record("application:mode=" + mode + ";files=" + files);
    }
}
```

Khi Spring nhận đối số `--mode=verify seed.csv`, `ApplicationArguments` phân tích:

- `getOptionValues("mode")` → danh sách chứa `"verify"`.
- `getNonOptionArgs()` → `["seed.csv"]`.
- Audit ghi `application:mode=verify;files=seed.csv`.

Không khai báo `matchIfMissing=true`, nên property vắng mặt sẽ **không thỏa** điều kiện `havingValue="true"`. Cách này là **opt-in**: chỉ chạy startup task khi bật rõ ràng.

### 6.6. `CommandLineRunner` nhận raw args

**`src/main/java/example/CliStartupRunner.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
@ConditionalOnProperty(
        prefix = "app.startup",
        name = "enabled",
        havingValue = "true"
)
public class CliStartupRunner implements CommandLineRunner {
    private final StartupAudit audit;

    public CliStartupRunner(StartupAudit audit) {
        this.audit = audit;
    }

    @Override
    public void run(String... args) {
        audit.record("command:args=" + String.join("|", args));
    }
}
```

Với cùng args, audit ghi `command:args=--mode=verify|seed.csv`. `@Order(20)` kết hợp `@Order(10)` của runner trước giúp assert thứ tự có căn cứ. **Hai loại runner được Spring Boot sắp chung theo ordering**, không phải vì ApplicationRunner luôn ưu tiên hơn CommandLineRunner.

### 6.7. Unit test: gọi `ApplicationRunner.run` mà không cần Spring

**`src/test/java/example/ArgsStartupRunnerUnitTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ArgsStartupRunnerUnitTest {
    @Test
    void parsesOptionAndNonOptionArgs() {
        StartupAudit audit = new StartupAudit();
        ArgsStartupRunner runner = new ArgsStartupRunner(audit);

        runner.run(new DefaultApplicationArguments(
                "--mode=verify", "seed.csv"));

        assertEquals(
                List.of("application:mode=verify;files=seed.csv"),
                audit.snapshot());
    }
}
```

Ở đây `new` tạo runner và audit; **không có `@SpringBootTest`, không có IoC container, không có auto startup**. Test chủ động gọi `runner.run`; nó chứng minh parse arguments và kết quả audit của runner nhưng **không** chứng minh SpringApplication đã gọi runner lúc bootstrap.

### 6.8. Unit test: kiểm tra raw arguments

**`src/test/java/example/CliStartupRunnerUnitTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CliStartupRunnerUnitTest {
    @Test
    void receivesRawCommandLineArguments() {
        StartupAudit audit = new StartupAudit();
        CliStartupRunner runner = new CliStartupRunner(audit);

        runner.run("--mode=verify", "seed.csv");

        assertEquals(
                List.of("command:args=--mode=verify|seed.csv"),
                audit.snapshot());
    }
}
```

Test thuần này không quan tâm Spring có tìm thấy `@Component` hay property bật/tắt; nó chỉ kiểm tra code trong phương thức `run`. Đó là lớp bằng chứng khác với integration test sau.

### 6.9. `@SpringBootTest` với runner được bật

**`src/test/java/example/RunnersEnabledBootTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = RunnerDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.startup.enabled=true",
        args = {"--mode=verify", "seed.csv"}
)
class RunnersEnabledBootTest {
    @Autowired
    StartupAudit audit;

    @Test
    void executesBothRunnersDuringContextStartupInOrder() {
        assertEquals(
                List.of(
                        "application:mode=verify;files=seed.csv",
                        "command:args=--mode=verify|seed.csv"
                ),
                audit.snapshot());
    }
}
```

Đây là test quan trọng của chủ đề:

1. Khi JUnit chuẩn bị Spring test context, Boot dùng `SpringApplication`.
2. Property `app.startup.enabled=true` khiến hai runner trở thành beans.
3. Boot gọi các runner ở startup, theo order 10 rồi 20.
4. Khi phương thức `@Test` bắt đầu, audit **đã chứa hai bản ghi**.
5. Assertion kiểm tra chính xác các tác động quan sát được, **không gọi `runner.run(...)` lần thứ hai trong test**.

Test này không mở cổng HTTP vì `webEnvironment=NONE`. Nếu ai đó nghĩ `NONE` tắt runners, test sẽ giúp sửa hiểu lầm đó.

### 6.10. `@SpringBootTest` với runner được tắt

**`src/test/java/example/RunnersDisabledBootTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
        classes = RunnerDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.startup.enabled=false",
        args = {"--mode=verify", "seed.csv"}
)
class RunnersDisabledBootTest {
    @Autowired
    StartupAudit audit;

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotCreateOrRunDisabledRunnerBeans() {
        assertEquals(List.of(), audit.snapshot());
        assertFalse(context.containsBean("argsStartupRunner"));
        assertFalse(context.containsBean("cliStartupRunner"));
    }
}
```

Khi property = false, `@ConditionalOnProperty` **không đăng ký bean runner**. Vì vậy `SpringApplication` không tìm thấy hai runner này để gọi. Test chứng minh không có tác động startup trong `StartupAudit` và bean names tương ứng không nằm trong context.

Chú ý khác nhau giữa:

- **Không tạo bean runner** do condition/profile: SpringApplication không thể gọi nó.
- **Tạo runner nhưng tự `return` sớm trong `run`**: bean vẫn được tạo, phương thức `run` vẫn được gọi, chỉ bỏ qua tác động phần thân.
- **Mock bean runner**: SpringApplication có thể vẫn gọi `run` của mock (no-op) tại startup, tùy bean override; không giống việc condition loại bỏ bean.

### 6.11. Chạy ví dụ

Sau khi có Gradle Wrapper phù hợp với Boot 3.3 và Java 17:

```bash
./gradlew test
./gradlew test --tests example.ArgsStartupRunnerUnitTest
./gradlew test --tests example.CliStartupRunnerUnitTest
./gradlew test --tests example.RunnersEnabledBootTest
./gradlew test --tests example.RunnersDisabledBootTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.RunnersEnabledBootTest
```

Kết quả mong đợi: **4 test methods pass**, gồm 2 unit và 2 Boot integration tests. Build tool có thể in `BUILD SUCCESSFUL` khi không còn task lỗi; không có stdout do business code chủ động tạo ra (audit nằm trong memory), dù Spring Boot có thể in startup logs tùy cấu hình.

**Lưu ý cache:** Hai Boot tests đặt hai giá trị `app.startup.enabled` khác nhau, nên chúng dùng cấu hình context khác và không chia sẻ cùng một cache key. Vì vậy test enabled quan sát hai startup events, test disabled thấy audit rỗng, không phụ thuộc thứ tự chạy class.

## 7. Các cách kiểm soát runner trong test

### 7.1. Cách ưu tiên cho side effect lớn: opt-in property

Nếu runner có thể ghi dữ liệu hoặc gọi dịch vụ ngoài, nên cấu hình hoạt động **rõ ràng**:

```java
@Component
@ConditionalOnProperty(
        prefix = "app.import",
        name = "enabled",
        havingValue = "true"
)
class CatalogImportRunner implements ApplicationRunner {
    // Chỉ được đăng ký nếu app.import.enabled=true.
}
```

Trong production deployment thực sự muốn chạy job, thiết lập `app.import.enabled=true`. Trong test không cần job, để mặc định absent/false hoặc đặt rõ:

```java
@SpringBootTest(
        properties = "app.import.enabled=false"
)
class CatalogServiceTest {
    // ...
}
```

Nếu production mặc định **phải bật** vì yêu cầu hệ thống, có thể chọn `matchIfMissing=true`, nhưng khi đó **mọi test không đặt flag sẽ có nguy cơ chạy runner**. Bản production/test contract phải được quyết định có chủ ý, không áp dụng một thiết lập cho mọi dự án.

### 7.2. Dùng profile khi môi trường test đã được chuẩn hóa

```java
@Component
@Profile("!test")
class StartupJob implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Công việc chỉ chạy khi profile test không active.
    }
}
```

Và ở test:

```java
@SpringBootTest
@ActiveProfiles("test")
class ServiceTest {
}
```

Đây là **hai mảnh cấu hình minh họa**. `@Profile("!test")` chỉ đánh giá **active profiles**, không biết code đang được thực thi bởi JUnit hay CI. Nếu test quên `@ActiveProfiles("test")`, runner vẫn có thể chạy; nếu production vô tình bật profile `test`, runner bị loại bỏ. Một số test chuyên biệt muốn **test chính runner** phải bật điều kiện cho nó bằng cấu hình khác.

**Khi nào chọn property hay profile?**

| Tình huống | Cách hay dùng |
| --- | --- |
| Một job có thể bật/tắt độc lập | `@ConditionalOnProperty` |
| Cả nhóm component chỉ thuộc môi trường nhất định | `@Profile` |
| Test cần chủ động bật runner | Explicit test properties |
| Runner nguy hiểm khi khởi động không chủ ý | Opt-in flag và kiểm tra deployment |
| Cần test runner mà không nạp Spring | Unit test gọi `run` thủ công |
| Cần chứng minh Boot gọi runner | `@SpringBootTest` bật flag và quan sát effect |

### 7.3. Điều kiện ngay tại `@Bean`

Runner cũng có thể được cung cấp qua một configuration method:

```java
@Configuration(proxyBeanMethods = false)
class JobConfiguration {
    @Bean
    @ConditionalOnProperty(
            name = "app.jobs.rebuild-index",
            havingValue = "true"
    )
    ApplicationRunner rebuildIndex(IndexService service) {
        return args -> service.rebuild();
    }
}
```

Đây là **đoạn minh họa**, cần định nghĩa `IndexService` và imports. Quan trọng là conditional đặt ngay trên **bean definition**, không cần constructor của runner tạo ra side effect. Nếu `IndexService` có startup side effect ở constructor/`@PostConstruct`, chỉ tắt runner chưa chắc tắt việc bean khác được tạo; phải kiểm soát đúng nơi tác động xảy ra.

### 7.4. Guard bên trong `run`: có thể dùng nhưng không giống tắt bean

Một cách khác là inject property và return:

```java
@Override
public void run(ApplicationArguments args) {
    if (!enabled) {
        return;
    }
    performJob();
}
```

Đây chỉ là **mã minh họa rút gọn**, cần field `enabled` và method `performJob()`. Cách này vẫn khiến bean được khởi tạo và `run` được gọi; nếu constructor hay init callback làm việc nguy hiểm, guard quá muộn. Với job không cần thiết trong test, loại bean bằng condition/profile thường rõ hơn.

### 7.5. Mock runner có làm nó ngừng chạy không?

Ở Spring Boot 3.x, có thể thấy test dùng `@MockBean` để thay concrete runner bằng mock. Điều này có thể khiến `run` của mock là no-op, nhưng có các hạn chế:

- Bean nào được replace phụ thuộc type/name/qualifier; nếu có nhiều runner, vẫn còn runner khác.
- SpringApplication vẫn có thể **gọi mock runner**; chỉ là mock không thực thi code gốc.
- Thêm mock/spy ảnh hưởng Spring TestContext cache key và có thể tạo nhiều context.
- Stubbing trong `@BeforeEach` hoặc `@Test` thường đến **sau** khi startup runner đã được gọi; không thể điều khiển lời gọi đã xảy ra.
- Spring Boot 3.4+ có hướng dùng `@MockitoBean` của Framework thay cho annotation legacy, còn Boot 4 bỏ API cũ.

Vì vậy, **đừng coi bean mocking là công tắc toàn cục tắt startup jobs**. Property/profile/thiết kế startup job riêng thường dễ hiểu và đáng tin hơn.

## 8. Kiểm thử runner theo ba cấp độ

### 8.1. Unit test logic `run`

Tạo runner bằng constructor, cấp fake dependency và gọi `run` thủ công:

```java
StartupAudit audit = new StartupAudit();
ApplicationRunner runner = new ArgsStartupRunner(audit);

runner.run(new DefaultApplicationArguments(
        "--mode=verify", "seed.csv"));

assertEquals(
        List.of("application:mode=verify;files=seed.csv"),
        audit.snapshot());
```

Đoạn trên có đầy đủ định nghĩa class trong mục 6; trong dự án cần imports JUnit/Boot tương ứng. Nó kiểm tra **logic parsing và tác động của runner**, không xác minh SpringApplication có tìm thấy bean.

### 8.2. Boot integration test cho startup

Dùng `@SpringBootTest` với flag enabled và audit độc lập như `RunnersEnabledBootTest`. Test phải assert effect **đã xảy ra trong bootstrap**. Không cần gọi `run` lại ở phần Act — nếu gọi lại sẽ kiểm tra một hành vi khác và có thể tạo double side effect.

### 8.3. Integration test với database/message broker

Nếu runner thật import dữ liệu vào DB hoặc publish event, audit in-memory **không đủ**. Tùy hợp đồng, dùng:

- Testcontainers với database cùng loại production để assert bản ghi/constraint/transaction.
- Embedded/test broker hoặc message broker trong container để assert event/payload và idempotency.
- HTTP mock server cho outbound request để khẳng định method/path/header/body.
- Fake port tại unit test để xác minh command gửi đi, cùng test integration ở protocol boundary khi cần.

Cẩn thận thứ tự setup: data seeding bằng `@BeforeEach`, `@Sql` mặc định ở before-test-method hoặc stubs trong `@Test` đều có thể **quá muộn** để runner dùng trong **context bootstrap**. Hãy chuẩn bị dữ liệu cần cho startup runner **trước context load** bằng migrations, test configuration, container initialization hoặc thiết lập fixture thích hợp.

## 9. Khi có nhiều runner: ordering và dependency thật

Spring Boot hỗ trợ `@Order` và `Ordered`. Nếu cùng muốn thực thi:

1. Load reference data.
2. Build search index.
3. Publish ready report.

Có thể viết ba runners và dùng các order khác nhau, nhưng phải cân nhắc:

- Cần gì nếu runner thứ nhất fail? Runner sau không thể giả định dữ liệu tồn tại.
- Nếu có retry hoặc nhiều replica, thứ tự trong một process không bảo đảm toàn hệ thống chỉ chạy một lần.
- `@Order` chỉ nói **thứ tự gọi trong startup process**, không nói transaction hoặc điều phối phân tán.
- Nếu muốn một chuỗi nghiệp vụ atomic hoặc có checkpoint, một **orchestrator runner duy nhất** gọi các step rõ ràng dễ test hơn.
- Không dựa vào thứ tự cho hai bean có `@Order` bằng nhau; hãy gán order khác hoặc không coi thứ tự là contract.
- `@DependsOn` ảnh hưởng thứ tự **khởi tạo bean**, không phải cơ chế chung thay thế việc `@Order` sắp runner callbacks.

Một biểu diễn rõ ràng:

```java
@Component
class StartupOrchestrator implements ApplicationRunner {
    private final ReferenceLoader loader;
    private final IndexBuilder index;
    private final StartupPublisher publisher;

    StartupOrchestrator(
            ReferenceLoader loader,
            IndexBuilder index,
            StartupPublisher publisher) {
        this.loader = loader;
        this.index = index;
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        loader.load();
        index.rebuild();
        publisher.published();
    }
}
```

Đây là **skeleton minh họa**, cần các interface và beans tương ứng; không phải phần của dự án runnable ở mục 6. Test orchestration có thể dùng mock/fake các port để assert thứ tự và kết quả, trong khi Boot integration test xác minh orchestrator được gọi đúng thời điểm.

## 10. Context cache: vì sao runner đôi khi chạy một lần, đôi khi nhiều lần?

Spring TestContext có **context cache tĩnh theo JVM**. Khi hai test có cấu hình giống nhau, Spring có thể tái sử dụng `ApplicationContext`. Khi đó runner **không được SpringApplication gọi lần nữa chỉ vì JUnit bắt đầu class hoặc method mới**.

Một mô hình:

```text
Test A: @SpringBootTest(properties="app.startup.enabled=true")
     |
     +--> cache miss -> dựng context A -> runners chạy

Test B: @SpringBootTest(properties="app.startup.enabled=true")
     |
     +--> cache hit  -> dùng lại context A -> runner không chạy lại

Test C: @SpringBootTest(properties="app.startup.enabled=false")
     |
     +--> cache key khác -> dựng context B -> runners không tồn tại

Test D: @DirtiesContext hoặc fork JVM khác
     |
     +--> có thể dựng context mới -> runner bật thì chạy lần nữa
```

Các thành phần có thể đổi cache key: application/configuration classes, active profiles, inline properties, context customizers (mocks/dynamic properties), initializers, context loader và context hierarchy.

**Không suy diễn số lần runner được gọi từ số phương thức `@Test`.** Trong suite lớn, runner có thể chạy nhiều lần vì context keys khác nhau. Khi side effect liên quan dữ liệu chung, điều đó gây duplicate rows, duplicate events hoặc trùng charges nếu code không có idempotency.

### 10.1. Test riêng xanh nhưng chạy suite đỏ

Trường hợp điển hình:

- Test A dựng context, runner import dữ liệu.
- Test B dùng lại context, tưởng runner vừa chạy nhưng thay đổi state đã bị test A xóa.
- Test C bật properties khác, dựng context mới và import dữ liệu lần nữa vào DB chung.
- Test D chạy ở JVM fork khác, context cache không chia sẻ, runner lại chạy.

Cách sửa: dùng fixture test độc lập, job idempotent, DB/schema riêng, property guard rõ ràng và assertion đúng ranh giới. Đừng “chữa” bằng cách ép mọi test `@DirtiesContext`, vì điều ấy còn làm runner được gọi **nhiều hơn**.

### 10.2. `@DirtiesContext` không phải lệnh rollback

`@DirtiesContext` đóng/loại context khỏi cache. Nó không xóa các bản ghi đã commit vào database và không hoàn tác email/event đã gửi. Với runner có side effect, annotation này còn tăng rủi ro chạy lại job khi context được tái tạo.

## 11. Transaction và dữ liệu bị thay đổi trước test

`@Transactional` trên một `@SpringBootTest` thường tạo **test-managed transaction** quanh test method với transaction manager phù hợp; mặc định transaction đó rollback. Nhưng runner chạy lúc `SpringApplication` startup, **trước khi transaction của method test được mở**.

Ví dụ sai về giả định:

```java
@SpringBootTest
@Transactional
class ImportJobTest {
    @Test
    void testImport() {
        // Không thể mặc định toàn bộ import lúc startup
        // sẽ rollback cùng transaction của method này.
    }
}
```

Đây là **đoạn minh họa**, cần application có transaction manager và imports. Nếu runner gọi repository/service có `@Transactional` riêng, việc ghi có thể commit trong transaction của chính startup operation. Rollback của test method **không đảo ngược** giao dịch ấy.

Tương tự, với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP server chạy ở thread/transaction khác. Ngay cả khi test method rollback, transaction phía server cũng không tự rollback.

**Giải pháp thực tế:**

1. Runner không được viết vào production DB từ test: dùng profile/property và datasource test riêng.
2. Nếu cần kiểm chứng runner ghi DB, chuẩn bị DB ephemeral, chạy startup một lần trong context mới và assert dữ liệu.
3. Dùng idempotency key/unique constraint/upsert có nghĩa nghiệp vụ để tránh duplicate trên lần chạy sau.
4. Cleanup với transaction/script có ý thức; không giả định test-managed rollback bao phủ startup.
5. Đừng để test này chạy song song trên cùng database/shared resource nếu chưa có isolation tương ứng.

### 11.1. Lỗi `@Sql` đến quá muộn

`@Sql` có thể tạo fixture trước test method. Nhưng runner đã đọc DB ở context bootstrap thì fixture này có thể chưa tồn tại. Phải thiết kế pre-startup data preparation đúng mốc: migrations, database image/init scripts, Testcontainers setup hoặc bean test configuration có thứ tự rõ. Không đặt một SQL script ở `@BeforeEach` rồi mong startup runner đã chạy trước đó đọc được.

## 12. Mock và stubbing: phải phân biệt lúc setup với lúc khởi động

Một lỗi rất hay gặp khi startup runner dùng remote gateway:

```java
@SpringBootTest
class StartupTest {
    @MockBean RemoteGateway gateway;

    @BeforeEach
    void stub() {
        when(gateway.fetch()).thenReturn("ok");
    }
}
```

Đây là **skeleton minh họa với Spring Boot 3.x**, thiếu `RemoteGateway` và `@Test`. Nếu runner gọi `gateway.fetch()` **trong quá trình startup**, stub tại `@BeforeEach` được thiết lập **sau** startup, không có tác dụng đối với lời gọi đã diễn ra. Mockito mock có thể trả default `null` và làm context fail.

Điều tương tự áp dụng cho `@MockitoBean` ở dòng Framework mới: bean được thay thế trước khi test chạy nhưng **stubbing từ test method không thể quay ngược thời gian**.

Cách đúng phụ thuộc mục tiêu:

- Nếu không cần runner: **loại runner khỏi context** bằng property/`@Profile`.
- Nếu muốn kiểm tra runner: **unit test** logic `run(...)` với fake/mock thiết lập trước lời gọi.
- Nếu bắt buộc kiểm tra bootstrap có dùng remote stub: cung cấp một test bean/mock **đã cấu hình trước khi context refresh/run** hoặc một HTTP mock server đã khởi động và cấp endpoint từ sớm; kiểm tra thứ tự initialization cẩn thận.
- Nếu runner gọi service bên ngoài trong constructor/`@PostConstruct`: condition chỉ đặt trên runner có thể chưa đủ nếu side effect nằm ở bean khác cũng được khởi tạo.

**Không dùng `Thread.sleep(...)` trong test để chữa lỗi “stub quá muộn”.** Đây là lỗi ranh giới vòng đời, không phải độ trễ hệ thống.

## 13. Đọc lỗi khi `@SpringBootTest` fail do runner

Nếu `ApplicationRunner.run(...)` ném exception, console có thể hiển thị:

```text
Failed to load ApplicationContext
...
Caused by: java.lang.IllegalStateException: import failed
    at ...StartupRunner.run(...)
```

Đây là **ví dụ cấu trúc log**, stack trace thật phụ thuộc ứng dụng. Hướng điều tra:

1. Tìm **root cause đầu tiên** ở cuối chuỗi `Caused by`, không chỉ dòng `Failed to load ApplicationContext`.
2. Kiểm tra call stack có `SpringApplication.callRunners`, `ApplicationRunner.run` hoặc `CommandLineRunner.run` không.
3. Kiểm tra bean runner nào được đăng ký: `@Component`/`@Bean`, `@ConditionalOnProperty`, `@Profile` và test properties.
4. Xác nhận runner chạy từ startup, không phải một lời gọi trong `@Test`.
5. Tìm external dependency thật: DB URL, credentials, network, message broker, file path hoặc API client.
6. Nếu runner phải chạy, fix side effect ở môi trường test và test idempotency; nếu không thuộc mục tiêu, vô hiệu hóa đúng condition.
7. Chạy lại **một test class nhỏ** để thấy root cause, rồi chạy suite để phát hiện vấn đề cache và dữ liệu dùng chung.

| Triệu chứng | Giả thuyết | Việc kiểm tra |
| --- | --- | --- |
| Test fail trước `@Test` | Startup runner ném exception | Stack trace `run(...)` và external dependency |
| Startup gọi HTTP thật | Runner không bị guard, hoặc client init side effect | Bean condition và profile test |
| `@BeforeEach` stub không có hiệu lực | Runner chạy trước callback | Đưa stub vào giai đoạn sớm hoặc tắt runner |
| Test riêng pass, suite fail | Cache/context reload hoặc shared DB state | Cache key, idempotency, cleanup |
| Startup import lặp nhiều lần | Mỗi context mới gọi runner | `@DirtiesContext`, properties, JVM forks, retries |
| `webEnvironment=NONE` vẫn seed DB | NONE không tắt SpringApplication runners | Property condition/profile |
| `@Transactional` không rollback seed | Runner chạy ngoài test transaction | Transaction boundary và database riêng |
| Runner order thay đổi | Không có `@Order`/`Ordered` rõ ràng | Gán order, hoặc thiết kế orchestrator |
| Test “không thấy runner chạy” | Cache hit, condition off, slice không chứa runner | Bean presence và cache configuration |
| `ApplicationReadyEvent` không tới | Runner chưa xong hoặc thất bại | Log startup, exception và thời gian tác vụ |
| Boot test khác app thật | Test không gọi custom `main` mặc định | `useMainMethod` và configuration |

### 13.1. Context failure threshold

Từ Spring Framework 6.1, khi một context cache key đã load thất bại, các lần cố load tương tự có thể bị bỏ qua theo **failure threshold** (mặc định 1). Những test sau có thể chỉ in thông báo threshold chứ không in lại lỗi runner ban đầu. Hãy xác định **lần thất bại đầu tiên**, thay vì quy mọi test cho một lỗi mới.

## 14. Thực thi đúng một lần và idempotency

Một runner không nên được dùng như một đảm bảo **“chỉ chạy một lần trong toàn hệ thống”**. Nó chạy **trong mỗi tiến trình `SpringApplication` khởi động**, với những bean được đăng ký ở tiến trình đó. Trong production có nhiều replica, triển khai lại pod, restart khi crash hoặc blue-green deployment, cùng job có thể chạy nhiều lần; test context reload cũng tương tự.

Các lựa chọn khi side effect cần kiểm soát:

- **Idempotent data seed:** dùng upsert/unique key và trạng thái đã áp dụng, không insert trùng mỗi lần.
- **Distributed lock/leader election:** khi thật sự chỉ một replica được phép chạy tác vụ.
- **Migration tool:** với thay đổi schema, dùng Flyway/Liquibase đúng trách nhiệm thay vì tùy tiện đặt vào runner.
- **Batch/scheduler riêng:** tác vụ dài hoặc định kỳ có thể phù hợp với Spring Batch, scheduled job hoặc một deployment job, không chặn startup của mọi service instance.
- **Outbox/idempotency key:** khi runner phát event hoặc gọi API có thể retry.
- **Startup flags:** cho phép bật job có chủ đích, và có môi trường test tách biệt.
- **Observability:** ghi job ID, thời gian, số bản ghi xử lý, kết quả và nguyên nhân thất bại (không log secrets).

**Transaction không thay thế idempotency.** Dù mỗi lần chạy nằm trong một transaction, một transaction commit hoàn toàn có thể tạo dữ liệu trùng ở lần startup kế tiếp nếu không có ràng buộc nghiệp vụ.

## 15. Performance, readiness và tác vụ mất nhiều thời gian

Vì runner được gọi **trước `ApplicationReadyEvent`**, một runner chậm có thể kéo dài startup. Trong môi trường orchestrator, readiness probe thường được thiết kế để chỉ routing traffic khi ứng dụng ready.

Nhưng cần phân biệt:

- `ApplicationStartedEvent`: context đã refresh, runner chưa chạy.
- Web server socket có thể đã lắng nghe trước ready; không nên suy luận một request mạng không thể đến.
- `ApplicationReadyEvent`: runner đã hoàn tất thành công và Boot công bố readiness transition.
- Với runner chạy bất đồng bộ, nếu `run` chỉ submit task rồi trả ngay, `ApplicationReadyEvent` có thể đến **trước khi background task hoàn tất**.

Nếu startup work là **bắt buộc để service hoạt động đúng**, phải quyết định rõ cơ chế đồng bộ/readiness. Nếu việc chạy lâu không phải điều kiện sẵn sàng, có thể tách thành async/batch workflow có giám sát riêng; đừng khởi động thread không quản lý rồi gọi đó là “an toàn”.

Trong CI, runner có thể tăng thời gian tạo context từ vài giây lên nhiều phút, dù test chỉ có một assertion. Tắt những công việc ngoài phạm vi kiểm thử là cách cải thiện lớn hơn việc tối ưu mỗi assertion.

## 16. Những khác biệt cần lưu ý theo phiên bản Spring Boot

Bài mẫu dùng Spring Boot 3.3.0. Các API `ApplicationRunner`, `CommandLineRunner`, `ApplicationArguments`, `@Order` và `@ConditionalOnProperty` là cơ chế lâu đời của Boot; tuy vậy **cách tổ chức starter, package test và các annotation mock thay bean có thể đổi giữa các dòng**.

| Phần | Spring Boot 2.x | Spring Boot 3.0–3.3 | Spring Boot 3.4–3.5 / 4.x |
| --- | --- | --- | --- |
| Startup runners | Có | Có | Có |
| Boot test tạo context qua `SpringApplication` | Có | Có | Có |
| `@SpringBootTest(args=...)` | Có ở các dòng 2.x hỗ trợ thuộc tính này | Có | Có, kiểm tra API minor thực tế |
| `@SpringBootTest(useMainMethod=...)` | Kiểm tra phiên bản 2.x cụ thể | Có | Có ở những dòng được tài liệu hỗ trợ |
| Cách mock bean trong test | `@MockBean` legacy | `@MockBean` legacy | Boot 3.4+ có `@MockitoBean`; Boot 4 loại legacy |
| Cách điều khiển runner | Property, profile, bean definition | Tương tự | Tương tự, với version-specific test imports |

**Đừng dùng sự khác biệt của `@MockBean` để suy ra runner không được gọi.** SpringApplication startup runner mechanism không phụ thuộc Mockito. Khi nâng major, kiểm tra starter test, imports và cách Boot test bootstrap, sau đó dùng test enabled/disabled như mục 6 để phát hiện thay đổi thực tế.

### 16.1. Test không gọi custom `main` mặc định

Nếu production main thực hiện setup:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(RunnerDemoApplication.class);
    application.setAdditionalProfiles("production-setup");
    application.run(args);
}
```

và test dùng `@SpringBootTest` mặc định, code tùy chỉnh trong `main` không được gọi trực tiếp. Runner vẫn có thể được gọi bởi SpringApplication của test, **nhưng có thể nhận cấu hình profile khác production**.

Nếu mục tiêu là kiểm chứng chính những tùy chỉnh trong main, dùng `useMainMethod = ALWAYS`/`WHEN_AVAILABLE` theo tài liệu phù hợp và giữ môi trường test an toàn. Nếu không, cấu hình startup nên đặt ở bean/extension được test chủ động kiểm soát thay vì ẩn trong main.

## 17. Checklist thiết kế và kiểm thử startup runner

- [ ] Tôi biết tất cả các bean implement `ApplicationRunner`/`CommandLineRunner` được import vào context đang test.
- [ ] Tôi hiểu `@SpringBootTest` có thể gọi chúng ngay khi load context.
- [ ] Tôi biết `webEnvironment=NONE` không tắt runners.
- [ ] Tôi phân biệt không gọi `main` trực tiếp với không chạy `SpringApplication`.
- [ ] Runner có side effect ngoài được bật theo flag/profile rõ ràng và chỉ ở môi trường cần thiết.
- [ ] Nếu dùng `@ConditionalOnProperty`, tôi đã kiểm tra `havingValue` và `matchIfMissing` thực sự tạo ra trạng thái mong muốn.
- [ ] Tôi không kỳ vọng stub trong `@BeforeEach` có tác dụng với lời gọi runner đã xảy ra lúc bootstrap.
- [ ] Unit test gọi `run` để kiểm tra logic; Boot test dùng context load để xác nhận runner tự chạy.
- [ ] Tôi không gọi lại `run` trong Boot test nếu mục tiêu là tác động startup.
- [ ] Test disabled chứng minh runner không tồn tại hoặc không gây effect như contract.
- [ ] Các runner có `@Order`/`Ordered` rõ ràng nếu thứ tự quan trọng.
- [ ] Tôi không dùng `@DependsOn` thay cho việc sắp thứ tự startup runner callbacks.
- [ ] Side effect DB/event có cơ chế idempotency khi restart/multi-replica.
- [ ] Dữ liệu runner ghi lúc startup không được giả định rollback bởi transaction của test method.
- [ ] Test fixtures cần cho runner phải có trước context load.
- [ ] Tôi hiểu context cache hit, `@DirtiesContext` và JVM forks có thể thay đổi số lần gọi.
- [ ] Runner dài hạn/async không làm sai trạng thái readiness.
- [ ] Khi gặp `Failed to load ApplicationContext`, tôi kiểm tra root cause và stack `run(...)`.

## 18. Bài tập thực hành có đáp án định hướng

### Bài 1 — Chứng minh `NONE` không tắt runner

Chạy `RunnersEnabledBootTest` ở mục 6. Test dùng `webEnvironment=NONE` nhưng audit đã có cả hai event. Giải thích: Boot context được tạo qua `SpringApplication`, runner có property enabled và được gọi trước `@Test`. Đổi `NONE` sang web mode khác không phải cách đúng để vô hiệu hóa runner.

### Bài 2 — Đổi thứ tự và quan sát assertion

Đổi `@Order(10)` ở `ArgsStartupRunner` thành `@Order(30)`, giữ CLI runner order 20. Chạy enabled test. Thứ tự audit thay đổi, assertion `List.of(...)` phải đỏ. Khôi phục order. Kết luận: chỉ assert order nếu thứ tự đó là contract.

### Bài 3 — Tắt runner bằng property

Đặt `app.startup.enabled=false` trong enabled test (tạm thời trên nhánh thử nghiệm). Context không đăng ký runner, audit rỗng; assertion đòi hai event phải đỏ. Khôi phục true. Giải thích sự khác nhau giữa **bean bị loại bởi condition** và **runner tồn tại nhưng return sớm**.

### Bài 4 — Phân biệt startup với test method

Trong một bản sao test, thêm dòng `new ArgsStartupRunner(audit).run(...)` vào `@Test`. Audit giờ có event thêm lần nữa; test không còn xác minh đơn thuần startup nữa. Bỏ dòng. Trả lời: tại sao runner không nên được gọi thủ công trong test integration của cơ chế bootstrap?

### Bài 5 — Dữ liệu và rollback

Thiết kế một `ApplicationRunner` giả ghi record vào database test. Test class có `@Transactional` và query lại record. Dự đoán: nếu startup operation đã commit trong transaction riêng, rollback sau method test **không xóa** record đó. Chọn DB test riêng và cleanup/transaction/idempotency có căn cứ.

### Bài 6 — Cache và duplicate effects

Hai test classes dùng cùng `@SpringBootTest(properties="app.startup.enabled=true")`. Khi cache hit, runner chỉ chạy trong lần context load đầu. Thêm inline property khác ở class thứ hai hoặc đánh dấu context dirty trong sandbox: có thể khởi tạo context mới và runner chạy thêm lần nữa. Thiết kế một invariant “không tạo bản ghi trùng” để bắt lỗi lặp startup.

### Bài 7 — Mock quá muộn

Giả sử runner gọi `RemoteGateway.fetch()` khi startup. Test có `@MockBean RemoteGateway` và `when(...).thenReturn(...)` tại `@BeforeEach`. Hãy giải thích vì sao stub đến quá muộn, rồi thiết kế một trong hai phương án: tắt runner cho test service thường, hoặc cung cấp fake đã chuẩn bị **trước context load** để test riêng startup flow.

### Bài 8 — Chọn API arguments

Với đối số `--mode=verify seed.csv`, viết expected:

- `ApplicationArguments.getOptionValues("mode")` → `["verify"]`.
- `ApplicationArguments.getNonOptionArgs()` → `["seed.csv"]`.
- `CommandLineRunner.run(String... args)` → `["--mode=verify", "seed.csv"]`.

Dùng unit tests của mục 6 để chứng minh, không cần nạp Spring.

## 19. Tổng kết

`ApplicationRunner` và `CommandLineRunner` là **entry points chạy khi `SpringApplication` đã refresh context nhưng trước khi công bố ứng dụng ready**. Hai loại khác nhau ở cách nhận arguments; thứ tự có thể được định nghĩa bằng `@Order`/`Ordered`. Chúng được Spring Boot gọi **vì là bean trong context**, chứ không phải vì JUnit gọi trực tiếp `run`.

Với `@SpringBootTest`, điều nguy hiểm nhất là **side effect xảy ra trước test method**: stubbing và fixture chuẩn bị trong `@BeforeEach` có thể đến quá muộn; test transaction không tự rollback dữ liệu đã ghi lúc startup; context cache và nhiều JVM/restarts có thể làm runner chạy số lần khác dự kiến.

Chiến lược đáng tin: **biến startup job thành hành vi được bật có chủ đích**, thiết kế side effect idempotent, dùng unit test cho logic `run` và một Boot integration test cho chính việc gọi runner lúc bootstrap. Đó là cách giữ test nhanh, an toàn và phản ánh đúng hợp đồng khởi động.

## 20. Tài liệu chính thức theo phiên bản

- Spring Boot — SpringApplication: runners, ordering, startup events: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — `ApplicationRunner` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot — `CommandLineRunner` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot — `ApplicationArguments` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot — `ConditionalOnProperty` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework — TestContext context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test-managed transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
