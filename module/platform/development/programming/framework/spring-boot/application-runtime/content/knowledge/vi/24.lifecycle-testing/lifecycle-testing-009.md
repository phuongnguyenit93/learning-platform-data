# Kiểm thử khởi động thất bại và FailureAnalyzer trong Spring Boot

## 1. Mục tiêu của bài

Một ứng dụng Spring Boot không chỉ cần khởi động thành công trong điều kiện bình thường, mà còn phải **thất bại đúng cách** khi cấu hình sai, dependency thiếu, một bean ném exception hoặc một tác vụ startup bị từ chối. Viết test cho các tình huống này khác đáng kể so với test một controller hay service đang hoạt động.

Một quy trình kiểm thử lỗi khởi động đáng tin cần trả lời đồng thời:

1. **Có thất bại thật không?** Context hoặc tiến trình phải từ chối khởi động, thay vì ghi log rồi vẫn được coi là ready.
2. **Lỗi xuất hiện ở giai đoạn nào?** Trước context, trong `refresh()`, trong `ApplicationRunner` hay sau `ApplicationReadyEvent`?
3. **Nguyên nhân được xác định đúng không?** Test cần tìm đúng exception sâu trong cause chain; không chỉ dò một thông điệp mơ hồ.
4. **`FailureAnalyzer` có phân tích đúng không?** Nó nhận diện lỗi được hỗ trợ, tạo `FailureAnalysis` với phần mô tả và hành động sửa chữa có ích, nhưng không “nuốt” lỗi.
5. **Analyzer đã được đăng ký đúng chưa?** Một unit test gọi trực tiếp analyzer không đủ chứng minh Boot nạp nó trong lần bootstrap thật.
6. **Mã thoát và tài nguyên thế nào?** Process phải báo thất bại; những singleton đã hoàn tất tạo cần được đóng theo hợp đồng lifecycle, trong khi tài nguyên mở dở phải có cleanup riêng.
7. **Test có cô lập và ổn định không?** Không làm chết JVM chạy JUnit; không phụ thuộc port đang rảnh, độ trễ bất định, thứ tự log, ANSI hoặc profile máy phát triển.

Trọng tâm: **Spring Boot 3.3.x, Java 17+, JUnit Jupiter 5, AssertJ, `ApplicationContextRunner` và `FailureAnalyzer`**. Phần ví dụ sử dụng Gradle và có mã nguồn đủ để chạy; các snippet ngoài dự án được đánh dấu là minh họa.

### Kết luận cần nhớ ngay

**Không có một test harness nào phù hợp cho mọi loại lỗi khởi động.**

- **Unit test:** xác minh logic validator/exception/analyzer mà không cần Spring context.
- **`ApplicationContextRunner`:** tạo một context nhỏ, kiểm thử cấu hình bean và lỗi `refresh()`, dễ kiểm soát và được tự đóng.
- **Boot integration test bằng `SpringApplication.run(...)`:** kiểm thử quy trình khởi động có runners/events thực sự.
- **Process-level test bằng `java -jar`:** kiểm tra output của `FailureAnalysisReporter`, mã thoát thực tế và hành vi khi JVM kết thúc.

Lựa chọn tầng nhỏ nhất có thể chứng minh yêu cầu, rồi bổ sung một vài test end-to-end cho phần wiring mà test nhỏ không bao phủ.

## 2. Vòng đời startup và nơi có thể phát sinh lỗi

Một Spring Boot application đi qua nhiều bước. Lỗi trong mỗi bước dẫn đến sự khác nhau về bean đã tồn tại, event đã phát và khả năng cleanup.

```text
main(args)
  |
  v
SpringApplication chuẩn bị Environment
  |          \-- có thể lỗi config data / property
  v
Tạo ApplicationContext
  |          \-- có thể lỗi context initializer
  v
Nạp bean definitions rồi refresh()
  |          +-- tạo singleton eager
  |          +-- bind và validate properties
  |          +-- @PostConstruct / init methods
  |          +-- SmartLifecycle auto-start
  |          \-- có thể lỗi dependency / constructor / init
  v
ApplicationStartedEvent
  |
  v
ApplicationRunner / CommandLineRunner
  |          \-- có thể ném exception
  v
ApplicationReadyEvent
  |
  v
Ứng dụng ready, SpringApplication.run(...) trả context

Nếu startup lỗi:
  → Spring Boot kích hoạt xử lý failure
  → Các FailureAnalyzer được đăng ký có cơ hội phân tích
  → FailureAnalysisReporter có thể hiển thị description/action
  → Context được đóng nếu đã tạo; refresh có cleanup riêng
  → Exception vẫn được đẩy lên
  → Process launcher/JVM báo trạng thái thất bại phù hợp
```

Sơ đồ rút gọn thứ tự và không bao gồm mọi hook nội bộ. Các analyzer/reporters liên quan **chẩn đoán**, không thay thế cơ chế đóng context. Lỗi ở background job **sau** khi `SpringApplication.run(...)` trả về không tự động biến thành `ApplicationFailedEvent` của lần startup trước đó.

### Bảng chọn công cụ kiểm thử

| Tình huống | Tầng test nên ưu tiên | Điều cần xác minh |
| --- | --- | --- |
| Validator từ chối giá trị sai | Unit test thuần | Loại lỗi và policy |
| `@Bean` factory ném lỗi | `ApplicationContextRunner` | Context không refresh thành công, root cause |
| `@ConfigurationProperties` validation thất bại | `ApplicationContextRunner` hoặc slice test phù hợp | Binding/validation và cause chain |
| Thiếu dependency bắt buộc | Context runner | `NoSuchBeanDefinitionException` trong cause chain |
| Bean tạo xong trước đó cần destroy | Context runner với resource recorder | Callback đóng được gọi |
| `ApplicationRunner` ném lỗi | `SpringApplication.run` / process test | Runner thật sự được gọi; startup fail |
| Custom analyzer xử lý exception | Unit test analyzer | `FailureAnalysis` description/action/cause |
| Custom analyzer được Boot tìm thấy | Process-level integration | Có report của analyzer trong output |
| Reporter in đúng hướng dẫn | Process-level hoặc reporter unit | Output có nội dung an toàn, ổn định |
| Exit code khác 0 | Chạy JAR bằng tiến trình riêng | OS process status, không phải log |
| Lỗi ở port HTTP đang bị chiếm | Integration có tài nguyên kiểm soát, ít dùng trong unit | Failure đúng không phụ thuộc máy đang chạy |
| Lỗi config rất sớm | Process/integration có listener sớm | Có thể chưa có application context |
| Lỗi sau khi service ready | Runtime failure test riêng | Không nhầm với boot failure |

## 3. FailureAnalyzer thực sự làm gì?

Spring Boot định nghĩa interface:

```java
package org.springframework.boot.diagnostics;

public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

Đây là chữ ký **rút gọn để học**, không phải file bạn phải tự định nghĩa. Trong ứng dụng, import interface sẵn có của Spring Boot.

- Đầu vào: một `Throwable` có thể là exception wrapper với nhiều lớp nguyên nhân.
- Kết quả nếu nhận diện được: một `FailureAnalysis`.
- Kết quả nếu không nhận diện được: **`null`**, để analyzer khác có cơ hội xử lý.
- Analyzer **không sửa cấu hình**, không restart ứng dụng và không biến một lỗi thành thành công.
- Analyzer cũng **không quyết định trực tiếp exit code**; muốn mã thoát cụ thể có `ExitCodeGenerator` / cơ chế exit riêng.

`FailureAnalysis` có ba dữ liệu quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getDescription()` | Giải thích điều gì đã thất bại |
| `getAction()` | Hướng dẫn cụ thể người vận hành nên sửa gì |
| `getCause()` | Exception làm căn cứ phân tích |

Constructor có dạng:

```java
new FailureAnalysis(description, action, cause)
```

Khi Boot không thể tạo analysis từ các analyzer phù hợp, reporter riêng cho failure analysis không nhất thiết có report mô tả ngắn; Boot thường vẫn báo lỗi startup thông thường.

### 3.1. Phân tách analyzer và reporter

Có hai hợp đồng:

```text
Throwable từ startup
       |
       v
FailureAnalyzer.analyze(Throwable)
       |
       +-- null -> analyzer khác có thể thử
       |
       +-- FailureAnalysis(description, action, cause)
                         |
                         v
FailureAnalysisReporter.report(FailureAnalysis)
                         |
                         v
Log / console / cơ chế reporting tương ứng
```

Spring Boot cung cấp `LoggingFailureAnalysisReporter` mặc định để log một báo cáo như:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

The demonstration bootstrap mode is invalid.

Action:

Set demo.bootstrap.mode=ok and restart.
```

Đây là **bố cục minh họa**. Đừng assert toàn bộ ký tự trống, tiền tố timestamp, ANSI colors hoặc stack trace giống nhau ở mọi logging backend.

**Không nhầm:** `FailureAnalyzer` trả data; `FailureAnalysisReporter` trình bày data. Cả hai không thay đổi việc exception vẫn làm lần khởi động thất bại.

### 3.2. AbstractFailureAnalyzer<T>

Spring Boot có:

```java
AbstractFailureAnalyzer<T extends Throwable>
```

Base class này giúp tìm một exception loại `T` trong cause chain, sau đó gọi phương thức phân tích:

```java
protected FailureAnalysis analyze(Throwable rootFailure, T cause)
```

Ưu điểm:

- Không phải tự duyệt cause chain trong mọi analyzer.
- Cho phép test trường hợp exception bị `BeanCreationException` / `BeanInstantiationException` bọc.
- Giúp analyzer chỉ nhận diện đúng exception mình phụ trách.
- Nếu không thể diễn giải, có thể trả `null` để analyzer khác xử lý.

## 4. Đăng ký FailureAnalyzer đúng với Spring Boot 3.3

Một lỗi đặc biệt phổ biến là viết:

```java
@Component
class MyFailureAnalyzer implements FailureAnalyzer {
    // ...
}
```

rồi nghĩ rằng Boot chắc chắn phát hiện nó trong **mọi lỗi trước khi context tạo thành công**.

Với custom `FailureAnalyzer` cho bootstrap, hướng dẫn chính thức của Spring Boot yêu cầu **đăng ký qua `META-INF/spring.factories`**. Lý do: analyzer có thể cần làm việc ngay khi application context chưa hoàn tất hoặc hoàn toàn chưa tồn tại; chỉ dùng component scanning là không đủ để đáp ứng hợp đồng này.

File:

```text
src/main/resources/META-INF/spring.factories
```

Ví dụ:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
demo.startupcheck.StartupPolicyFailureAnalyzer
```

- Key là **fully qualified interface name**.
- Value là **fully qualified class name** của analyzer có thể tạo được.
- Dấu `\` ở cuối dòng properties cho phép tiếp tục giá trị trên dòng sau.
- File phải có mặt trong **runtime classpath**, kể cả trong JAR đã đóng gói.
- Class analyzer cần có constructor được loader tạo đúng (đơn giản nhất là public no-arg constructor), và không phụ thuộc bắt buộc vào bean chưa tồn tại.
- Khi phát triển starter hoặc thư viện, file `spring.factories` của dependency có thể được nạp cùng các files của ứng dụng.

**Không chuyển đăng ký FailureAnalyzer sang file `AutoConfiguration.imports`.** File `AutoConfiguration.imports` phục vụ registration auto-configuration trong Boot hiện đại, còn failure analyzer dùng key `org.springframework.boot.diagnostics.FailureAnalyzer` trong `spring.factories` theo hợp đồng chính thức của Boot 3.3.

### 4.1. Không dùng bean injection một cách mù quáng trong analyzer

Spring Boot có thể hỗ trợ tạo analyzer dùng `BeanFactory` hoặc `Environment` nếu chúng khả dụng, nhưng một lỗi cực sớm có thể xảy ra **trước khi context đã sẵn sàng**.

Để analyzer đáng tin:

- Giữ analyzer đơn giản và không có side effect.
- Không truy vấn repository/database hay các bean nghiệp vụ.
- Không giả định mọi property đều đã bind.
- Không ném exception thứ hai từ analyzer khi cố đọc dữ liệu lỗi.
- Tránh lấy raw value của secret hoặc token để đưa vào description/action.

## 5. Dự án ví dụ hoàn chỉnh

Ta xây một ứng dụng nhỏ có **hai đường thất bại chủ động**:

1. `demo.bootstrap.mode` sai: bean `StartupMarker` không được tạo thành công, context **fail trong refresh**.
2. `demo.runner.fail=true`: context refresh thành công, nhưng `ApplicationRunner` ném exception; Boot **fail trong giai đoạn runner**.

Cả hai dùng một exception nghiệp vụ có hai lý do khác nhau. Custom analyzer chuyển mỗi lý do thành description/action riêng, không cần in giá trị đầu vào thô.

### 5.1. Cấu trúc project

```text
startup-check-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          startupcheck/
            StartupCheckApplication.java
            StartupGuardConfiguration.java
            StartupMarker.java
            StartupPolicyException.java
            StartupPolicyFailureAnalyzer.java
      resources/
        application.properties
        META-INF/
          spring.factories
    test/
      java/
        demo/
          startupcheck/
            StartupGuardContextTests.java
            StartupPolicyFailureAnalyzerTests.java
            ContextCleanupTests.java
```

### 5.2. Gradle: Java 17 và Spring Boot 3.3.x

`settings.gradle`:

```groovy
rootProject.name = 'startup-check-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.13 được chọn để minh họa API của nhánh 3.3, không phải khuyến nghị sử dụng một phiên bản cũ trong hệ thống production mới. Project cần JDK 17+ và Gradle/Gradle wrapper tương thích. File `build.gradle` **không tự tạo** `gradlew`; nếu chưa có wrapper, hãy dùng Gradle đã cài để tạo `gradle wrapper`.

`src/main/resources/application.properties`:

```properties
spring.application.name=startup-check-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

demo.bootstrap.mode=ok
demo.runner.fail=false
```

App chạy dạng non-web để test startup không cần port HTTP; hai property mặc định hợp lệ.

### 5.3. StartupMarker.java

```java
package demo.startupcheck;

public record StartupMarker(String mode) {
}
```

`record` hợp lệ trên Java 17+. Nó biểu diễn một bean được tạo **chỉ khi config hợp lệ**. Không kết nối DB, file hoặc network để test có tính tất định.

### 5.4. StartupPolicyException.java

```java
package demo.startupcheck;

public final class StartupPolicyException
        extends RuntimeException {

    public enum Problem {
        INVALID_MODE,
        RUNNER_BLOCKED
    }

    private final Problem problem;

    public StartupPolicyException(Problem problem) {
        super("Startup policy rejected an operation.");
        this.problem = problem;
    }

    public Problem problem() {
        return problem;
    }
}
```

Ta không ghép giá trị input thật vào exception message. `problem` là một enum mà code kiểm soát, thuận tiện cho analyzer và test.

### 5.5. StartupGuardConfiguration.java

```java
package demo.startupcheck;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupGuardConfiguration {

    @Bean
    StartupMarker startupMarker(
            @Value("${demo.bootstrap.mode:ok}") String mode) {

        if (!"ok".equals(mode)) {
            throw new StartupPolicyException(
                    StartupPolicyException.Problem.INVALID_MODE);
        }

        return new StartupMarker("ok");
    }
}
```

Lỗi được ném **trong `@Bean` factory method**. Khi container cần tạo singleton eager này trong `refresh()`, Spring có thể bọc `StartupPolicyException` bằng `BeanCreationException` và các exception khác.

Test **không được đòi exception ngoài cùng chính xác là `StartupPolicyException`**. Cần tìm root cause hoặc phân tích chain.

### 5.6. StartupCheckApplication.java

```java
package demo.startupcheck;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupCheckApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupCheckApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner(
            StartupMarker marker,
            @Value("${demo.runner.fail:false}") boolean shouldFail) {

        return arguments -> {
            if (shouldFail) {
                throw new StartupPolicyException(
                        StartupPolicyException.Problem.RUNNER_BLOCKED);
            }

            System.out.println("runner.ok=" + marker.mode());
        };
    }
}
```

Ở đường thành công, marker do code in ra là:

```text
runner.ok=ok
```

Ở đường `demo.bootstrap.mode=invalid`, Spring không tạo được `StartupMarker` nên runner không thể chạy thành công. Ở đường `demo.runner.fail=true`, context đã refresh xong, runner được gọi rồi cố tình ném exception.

**Chú ý:** `ApplicationRunner` được gọi bởi `SpringApplication` sau refresh; `ApplicationContextRunner` chỉ thử tạo/refresh context và **không tự gọi** runner. Ta sẽ kiểm thử khác nhau cho hai đường lỗi.

### 5.7. StartupPolicyFailureAnalyzer.java

```java
package demo.startupcheck;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class StartupPolicyFailureAnalyzer
        extends AbstractFailureAnalyzer<StartupPolicyException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, StartupPolicyException cause) {

        String description = switch (cause.problem()) {
            case INVALID_MODE ->
                    "The demonstration bootstrap mode is invalid.";
            case RUNNER_BLOCKED ->
                    "The demonstration startup runner was blocked.";
        };

        String action = switch (cause.problem()) {
            case INVALID_MODE ->
                    "Set demo.bootstrap.mode=ok and restart.";
            case RUNNER_BLOCKED ->
                    "Set demo.runner.fail=false and restart.";
        };

        return new FailureAnalysis(description, action, cause);
    }
}
```

`AbstractFailureAnalyzer` tìm `StartupPolicyException` trong cause chain, kể cả khi Spring bọc nó trong các exception hạ tầng.

**Tại sao không đưa toàn bộ `cause.getMessage()` vào report?** Vì trong ứng dụng thực, exception message có thể chứa giá trị cấu hình, token, connection URL hoặc dữ liệu nhạy cảm. Ở đây mô tả và action dựa trên enum đã biết, nên report ổn định và an toàn hơn.

### 5.8. META-INF/spring.factories

File `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
demo.startupcheck.StartupPolicyFailureAnalyzer
```

File này **bắt buộc cho đường kiểm thử integration** của custom analyzer. Một test trực tiếp `new StartupPolicyFailureAnalyzer()` sẽ thành công ngay cả khi file sai/mất; vì vậy cần test cả chuyện đăng ký.

### 5.9. Chạy ứng dụng thành công

Với Gradle wrapper:

```bash
./gradlew bootRun
```

Marker do code ứng dụng in ra:

```text
runner.ok=ok
```

Gradle và Spring Boot có thể in thêm output. Không có báo cáo failure vì hai property hợp lệ.

### 5.10. Lỗi refresh: cấu hình mode sai

```bash
./gradlew bootRun --args='--demo.bootstrap.mode=invalid'
```

Các dòng chính trong report, nếu Boot nạp analyzer và logging reporter hoạt động:

```text
APPLICATION FAILED TO START

Description:

The demonstration bootstrap mode is invalid.

Action:

Set demo.bootstrap.mode=ok and restart.
```

**Đây là trích đoạn quan trọng**, không phải toàn bộ stdout/stderr. Logger có thể thêm header, timestamp, stack trace và phần kết luận task của Gradle. `runner.ok=ok` **không được xuất hiện** vì bean khởi tạo thất bại trước khi runner được gọi.

### 5.11. Lỗi runner: context refresh đã thành công

```bash
./gradlew bootRun --args='--demo.runner.fail=true'
```

Báo cáo được mong đợi:

```text
APPLICATION FAILED TO START

Description:

The demonstration startup runner was blocked.

Action:

Set demo.runner.fail=false and restart.
```

Lỗi xảy ra **sau refresh**, nhưng vẫn trong đường `SpringApplication.run(...)`. Nó vẫn được xem là startup failure, và `ApplicationReadyEvent` không biểu thị một lần khởi động thành công.

**Hai thử nghiệm không tương đương:** dùng context runner để kiểm thử lỗi refresh; muốn kiểm thử runner fail thực sự, phải chạy `SpringApplication.run` hoặc tiến trình Boot tương ứng.

## 6. Unit test FailureAnalyzer: kiểm thử logic không cần context

File `src/test/java/demo/startupcheck/StartupPolicyFailureAnalyzerTests.java`:

```java
package demo.startupcheck;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class StartupPolicyFailureAnalyzerTests {

    private final StartupPolicyFailureAnalyzer analyzer =
            new StartupPolicyFailureAnalyzer();

    @Test
    void analyzesInvalidModeNestedInsideAnotherException() {
        Throwable failure = new IllegalStateException(
                "Framework wrapper",
                new StartupPolicyException(
                        StartupPolicyException.Problem.INVALID_MODE));

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .isEqualTo(
                        "The demonstration bootstrap mode is invalid.");
        assertThat(analysis.getAction())
                .isEqualTo(
                        "Set demo.bootstrap.mode=ok and restart.");
        assertThat(analysis.getCause())
                .isInstanceOf(StartupPolicyException.class);
    }

    @Test
    void analyzesRunnerFailureWithDifferentAction() {
        Throwable failure = new StartupPolicyException(
                StartupPolicyException.Problem.RUNNER_BLOCKED);

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .isEqualTo(
                        "The demonstration startup runner was blocked.");
        assertThat(analysis.getAction())
                .isEqualTo(
                        "Set demo.runner.fail=false and restart.");
    }

    @Test
    void returnsNullForUnrelatedException() {
        FailureAnalysis analysis =
                analyzer.analyze(new IllegalArgumentException("other"));

        assertThat(analysis).isNull();
    }
}
```

Ba test độc lập minh chứng:

1. Analyzer xử lý được **exception nằm sâu trong cause chain**.
2. Một exception type có thể tạo action khác nhau theo **loại lỗi nghiệp vụ**.
3. Analyzer trả `null` cho lỗi không nhận diện, để analyzer khác có thể thử.

**Giới hạn quan trọng:** ba test này **không chứng minh** file `spring.factories` tồn tại, Boot đã nạp analyzer, default reporter có in ra output hay process thoát non-zero. Chúng chỉ xác minh **logic của một object analyzer**.

### 6.1. Tại sao kiểm tra cả description và action?

Một analyzer chất lượng cần báo:

- **Description:** biểu hiện lỗi thuộc chính sách nào, không chỉ lặp `IllegalStateException`.
- **Action:** người sử dụng có thể thay đổi property, bổ sung dependency, sửa port hoặc thực hiện một hành động cụ thể.
- **Cause:** giữ exception làm bằng chứng.

Một test chỉ assert `analysis != null` có thể bỏ sót việc analyzer báo action sai, không an toàn hoặc quá chung.

### 6.2. Kiểm thử null path là hợp đồng công khai

Với `FailureAnalyzer`, `null` **không có nghĩa test hỏng**. Nó có nghĩa analyzer này không hỗ trợ exception hiện tại. Việc trả một `FailureAnalysis` giả cho **mọi** lỗi có thể cướp cơ hội của analyzer chuyên dụng hơn.

Do đó test negative path là bắt buộc với analyzer dùng chung.

## 7. ApplicationContextRunner: kiểm thử lỗi refresh có kiểm soát

`org.springframework.boot.test.context.runner.ApplicationContextRunner` hỗ trợ chạy một application context nhỏ với bean configuration xác định. Nó rất phù hợp để thử:

- Có hoặc thiếu bean.
- Property binding.
- Điều kiện `@ConditionalOnProperty`.
- Lỗi constructor hoặc `@Bean` factory.
- Exception trong `@PostConstruct`.
- Cleanup của singleton khi refresh thất bại.

**Không đồng nghĩa với chạy toàn bộ SpringApplication startup.** Nó tạo một context thử nghiệm, không phát đủ bộ Boot `ApplicationStartedEvent`/`ApplicationReadyEvent` và **không tự gọi `ApplicationRunner`**.

### 7.1. Test context thành công và thất bại

File `src/test/java/demo/startupcheck/StartupGuardContextTests.java`:

```java
package demo.startupcheck;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class StartupGuardContextTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            StartupGuardConfiguration.class);

    @Test
    void startsWithValidMode() {
        runner.withPropertyValues("demo.bootstrap.mode=ok")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(StartupMarker.class);
                    assertThat(context.getBean(StartupMarker.class).mode())
                            .isEqualTo("ok");
                });
    }

    @Test
    void failsDuringRefreshWithInvalidMode() {
        runner.withPropertyValues(
                "demo.bootstrap.mode=invalid")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    StartupPolicyException.class);
                });
    }
}
```

Đây là test JUnit 5/AssertJ đầy đủ trong môi trường Gradle đã cấu hình.

- `withUserConfiguration` chỉ đăng ký `StartupGuardConfiguration`.
- `withPropertyValues` chèn property vào context thử nghiệm.
- `run(context -> ...)` cung cấp một **AssertableApplicationContext** cho callback.
- Khi refresh thất bại, callback **vẫn được gọi** với trạng thái failed để assert.
- Khi callback kết thúc, runner dọn context phù hợp.
- `getStartupFailure()` cho biết exception phát sinh trong quá trình khởi tạo context.
- `hasRootCauseInstanceOf` kiểm tra nguyên nhân sâu nhất, giúp test không phụ thuộc vào số lớp exception wrapper của Spring.

**Đừng dùng `context.getBean(...)` trong nhánh failure** để dò bean một cách tùy tiện: context không được refresh thành công và thao tác này có thể ném lỗi khác, che assertion chính.

### 7.2. Vì sao assert root cause chứ không assert một message đầy đủ?

Một `@Bean` factory ném:

```text
StartupPolicyException
```

có thể được framework bọc thành:

```text
BeanCreationException
    |
    +-- BeanInstantiationException
              |
              +-- StartupPolicyException
```

Thứ tự/loại wrapper có thể thay đổi tùy version hoặc điểm tạo bean. Việc assert nguyên văn một message lớn như:

```text
Error creating bean with name ... defined in class path ...
```

làm test yếu trước những thay đổi không ảnh hưởng đến hành vi.

**Tốt hơn:** assert exception type ở cause chain và kiểm tra một vài thông tin có ý nghĩa nghiệp vụ, không khóa test vào full stack trace.

### 7.3. Runner là API bất biến theo từng lượt

`ApplicationContextRunner` có các method dạng `withPropertyValues`/`withUserConfiguration` trả đối tượng cấu hình chạy mới theo phong cách builder. Không cần sửa field chung giữa các tests để chuyển từ success sang failure. Điều này giảm ảnh hưởng chéo khi test chạy theo thứ tự khác nhau.

### 7.4. Vì sao context runner không test được FailureAnalyzer wiring?

`ApplicationContextRunner` chạy `ApplicationContext` test, **không phải đường `SpringApplication.run(...)` mặc định với các `SpringBootExceptionReporter` được nạp cho lần startup**. Vì vậy một test context failure có thể pass mà `META-INF/spring.factories` chứa tên analyzer sai.

Hãy coi nó là **test context behavior**, không phải test toàn bộ startup diagnostics. Test analyzer riêng, rồi chạy JAR để xác nhận wiring/report cuối cùng.

## 8. Kiểm thử cleanup khi context refresh thất bại

Một lỗi khởi động có thể xảy ra **sau khi đã có một số singleton được tạo thành công**. Test nên chứng minh những resource đã được container sở hữu được dọn, nhưng không khẳng định destructor chạy cho một object chưa hoàn tất tạo.

File `src/test/java/demo/startupcheck/ContextCleanupTests.java`:

```java
package demo.startupcheck;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ContextCleanupTests {

    @Test
    void closesCompletedSingletonWhenLaterBeanCreationFails() {
        CleanupConfiguration.CLOSE_COUNT.set(0);

        new ApplicationContextRunner()
                .withUserConfiguration(CleanupConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    StartupPolicyException.class);
                });

        assertThat(CleanupConfiguration.CLOSE_COUNT.get())
                .isEqualTo(1);
    }

    @Configuration(proxyBeanMethods = false)
    static class CleanupConfiguration {

        static final AtomicInteger CLOSE_COUNT =
                new AtomicInteger();

        @Bean(destroyMethod = "close")
        TrackedResource trackedResource() {
            return new TrackedResource(CLOSE_COUNT);
        }

        @Bean
        String failingBean(TrackedResource alreadyCreated) {
            throw new StartupPolicyException(
                    StartupPolicyException.Problem.INVALID_MODE);
        }
    }

    static final class TrackedResource implements AutoCloseable {

        private final AtomicInteger closeCount;

        TrackedResource(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }
}
```

**Vì sao test này có ý nghĩa:**

- `failingBean(TrackedResource alreadyCreated)` bắt Spring tạo `TrackedResource` **trước** khi gọi factory method gây lỗi.
- `TrackedResource` được trả về bean factory thành công và đăng ký custom destructor `close`.
- Khi refresh thất bại ở bean tiếp theo, Spring có đường hủy các singleton đã tạo.
- `CLOSE_COUNT` cho phép test xác nhận cơ chế cleanup mà không cần mở socket/file thật.
- Không phụ thuộc vào độ trễ hoặc process termination.

### 8.1. Lưu ý với static recorder trong test

`CLOSE_COUNT` là static field để minh họa quan sát. Trong test suite lớn có parallel execution, static mutable state có thể gây tranh chấp. Với production-grade tests, cân nhắc:

- Một recorder instance độc lập được cung cấp qua cấu hình test.
- Không chạy song song những tests dùng cùng static recorder.
- Reset state ở đầu test và đo chính xác sau context close.
- Dùng unique resource owner thay vì một singleton recorder dùng chung mọi context.

Ví dụ chọn AtomicInteger chỉ nhằm đơn giản hóa file chạy được và không liên quan DB.

### 8.2. Cái gì không được đảm bảo cleanup?

Trường hợp nguy hiểm:

```java
@Bean(destroyMethod = "close")
SocketClient socketClient() throws Exception {
    SocketClient client = new SocketClient();
    client.connect(); // Nếu lỗi trước return?
    return client;
}
```

Đây là **snippet minh họa**, cần class `SocketClient` có `connect/close`. Nếu `connect()` đã cấp tài nguyên rồi ném exception, bean chưa được bàn giao cho Spring. **Không dựa vào `destroyMethod` của bean chưa return** để dọn tài nguyên local.

Trong factory thực, bắt lỗi tại điểm cấp phát và đóng resource trước khi ném lại lỗi; dùng `try-with-resources` hoặc `try/catch` với suppressed exception phù hợp.

### 8.3. Prototype và bean lazy

- Prototype bean không được Spring tự quản lý destruction giống singleton.
- Bean lazy chưa từng được tạo không có destructor instance để gọi.
- `ApplicationContextRunner` thử context với đúng các bean bạn đăng ký; nếu khác cấu hình production, đừng suy ra kết quả cleanup của mọi resource thực.
- `@PostConstruct` ném lỗi trước khi bean hoàn tất initialization có thể khiến destructor của chính instance đó chưa được đăng ký.
- Nếu có `SmartLifecycle`, việc stop theo phase khi refresh lỗi rất sớm không đồng nghĩa một lần shutdown bình thường hoàn chỉnh.

## 9. Kiểm thử ApplicationRunner thất bại: cần SpringApplication thật

Xem bean `demoRunner` trong ứng dụng mục 5. Nó được **tạo trong refresh**, nhưng method `run(ApplicationArguments)` chỉ được Boot gọi trong các bước sau refresh.

### 9.1. Vì sao một ApplicationContextRunner test có thể pass dù runner sẽ ném lỗi?

Giả sử context runner đăng ký một `ApplicationRunner`:

```java
@Bean
ApplicationRunner alwaysFailingRunner() {
    return arguments -> {
        throw new IllegalStateException("runner failed");
    };
}
```

Đây là snippet trong `@Configuration`, cần import `Bean` và `ApplicationRunner`.

`ApplicationContextRunner` có thể refresh context **thành công**, vì nó không tự gọi callback `run(...)` của bean này. Test:

```java
assertThat(context).hasNotFailed();
```

không nói gì về việc khi `SpringApplication.run(...)` gọi runner thì có lỗi hay không.

### 9.2. Đường kiểm thử tích hợp

Để xác thực lỗi runner:

- Khởi chạy ứng dụng qua `SpringApplication.run(StartupCheckApplication.class, args)` trong môi trường test phù hợp, hoặc
- Chạy `java -jar ... --demo.runner.fail=true` như tiến trình riêng.

Khi startup Boot thực sự gọi `demoRunner`, nó ném `StartupPolicyException(RUNNER_BLOCKED)`. `FailureAnalyzer` custom phải trả đúng action `demo.runner.fail=false`.

**Khuyến nghị:** process test là đường đơn giản, đáng tin nhất để cùng lúc xác minh failure analysis report, việc đăng ký qua `spring.factories` và exit code ngoài JVM test.

### 9.3. ApplicationStartedEvent khác ApplicationReadyEvent

Trong chu trình Boot 3.3:

```text
context refresh
       |
       v
ApplicationStartedEvent
       |
       v
ApplicationRunner / CommandLineRunner
       |
       +-- có lỗi → failure path
       |
       v
ApplicationReadyEvent (chỉ nếu runners hoàn tất)
```

Vì vậy khi runner ném lỗi, một listener cho `ApplicationStartedEvent` có thể đã chạy, còn `ApplicationReadyEvent` không được phát theo đường khởi động thành công.

Nếu muốn test readiness, hãy kiểm tra đúng event/state thay vì chỉ dựa vào log “Started …” ở mốc trước runner.

## 10. Process-level test: kiểm tra FailureAnalyzer registration và exit code

Đây là phần mà unit test và `ApplicationContextRunner` **không thay thế được**: chạy Boot như tiến trình Java độc lập.

### 10.1. Build JAR

```bash
./gradlew clean test bootJar
```

Với cấu hình `settings.gradle` và `version=1.0.0` trong ví dụ, JAR dự kiến:

```text
build/libs/startup-check-demo-1.0.0.jar
```

Nếu thay tên dự án hoặc cấu hình archive, lấy tên JAR thực tế thay vì đoán.

### 10.2. Lỗi refresh: chạy JAR trực tiếp

Trên Linux/macOS hoặc shell POSIX, thực hiện:

```bash
set +e
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=invalid \
  > startup-refresh-fail.log 2>&1
status=$?
set -e

printf 'exit=%s\n' "$status"
test "$status" -ne 0
grep -F 'The demonstration bootstrap mode is invalid.' \
  startup-refresh-fail.log
grep -F 'Set demo.bootstrap.mode=ok and restart.' \
  startup-refresh-fail.log
```

Đoạn này chạy trong shell POSIX; `set +e` giúp lệnh cố ý lỗi không cắt ngang script nếu bên ngoài bật `errexit`, còn `status=$?` phải lấy **ngay sau tiến trình Java**. `grep` dùng để kiểm tra hai chuỗi có ý nghĩa; không so nguyên file log.

Kỳ vọng:

- Java process kết thúc khác 0.
- Log có description và action của custom analyzer.
- Không có marker `runner.ok=ok`.
- Không cần assert chính xác text của stack trace/ANSI hay timestamp.

**Không tuyên bố exit code phải là một con số cụ thể** chỉ vì đã đăng ký `FailureAnalyzer`. Analyzer giúp chẩn đoán; exit status phụ thuộc exception/failure handling và launcher. Nếu ứng dụng cần mã cố định như 2/23/64, hãy thiết kế riêng bằng `ExitCodeGenerator`/policy và test tiến trình.

### 10.3. Lỗi runner: chạy JAR riêng

```bash
set +e
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.runner.fail=true \
  > startup-runner-fail.log 2>&1
status=$?
set -e

printf 'exit=%s\n' "$status"
test "$status" -ne 0
grep -F 'The demonstration startup runner was blocked.' \
  startup-runner-fail.log
grep -F 'Set demo.runner.fail=false and restart.' \
  startup-runner-fail.log
```

Đây là phép thử **hai tầng integration thực sự khác nhau**: một thất bại trong refresh, một thất bại sau refresh ở runner. Cả hai đều chứng minh analyzer được nạp và reporter được gọi trong đường startup failure phù hợp.

### 10.4. Đường thành công

```bash
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=ok \
  --demo.runner.fail=false

printf 'exit=%s\n' "$?"
```

Marker chính:

```text
runner.ok=ok
```

Một CLI non-web đơn giản không có tác vụ nền giữ JVM và chạy thành công thường kết thúc với exit status 0. Nếu process không thoát, hãy tìm background executor/daemon policy; không vội đổ lỗi cho analyzer.

### 10.5. PowerShell trên Windows

```powershell
java -jar build/libs/startup-check-demo-1.0.0.jar --demo.runner.fail=true
$exitCode = $LASTEXITCODE
Write-Output ("exit=" + $exitCode)
```

Ở PowerShell, dùng `$LASTEXITCODE` để lấy exit status của `java`. Đừng dùng `$?` như thể nó luôn chứa mã nguyên của native process.

### 10.6. Vì sao không chỉ dùng ./gradlew bootRun?

Gradle có thể báo mã thất bại của **task/wrapper**, không nhất thiết bằng mã thoát thực của Java process. Ngoài ra Gradle/IDE có thể thêm log hoặc chuyển tiếp exception theo quy tắc riêng.

Muốn chứng minh Java/JVM process báo status nào, hãy **chạy JAR trực tiếp** hoặc tạo process con và kiểm tra exit value. Tầng test này cũng tránh chuyện test JUnit tự gọi `System.exit` và làm chết toàn bộ runner.

## 11. Có thể tự động hóa process test bằng ProcessBuilder không?

Có. Trong một integration test cô lập, `ProcessBuilder` cho phép tạo tiến trình Java con, đưa tham số cố định và chờ process kết thúc với timeout.

Mẫu Java 17 minh họa:

```java
import java.io.File;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ChildProcessProbe {

    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(
                System.getProperty("java.home"),
                "bin",
                isWindows() ? "java.exe" : "java"
        ).toString();

        Process process = new ProcessBuilder(
                javaBinary,
                "-jar",
                "build/libs/startup-check-demo-1.0.0.jar",
                "--demo.bootstrap.mode=invalid")
                .redirectErrorStream(true)
                .redirectOutput(new File("probe-output.log"))
                .start();

        try {
            if (!process.waitFor(20, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
                throw new IllegalStateException(
                        "Child process exceeded timeout.");
            }

            int exit = process.exitValue();
            System.out.println("childFailed=" + (exit != 0));
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
    }
}
```

Đây là Java 17 standalone, cần JAR đã được build ở đúng đường dẫn và file output có thể ghi được. Nó có thể biên dịch:

```bash
javac ChildProcessProbe.java
java ChildProcessProbe
```

Nếu JAR tồn tại và start failure diễn ra như thiết kế, stdout của code probe:

```text
childFailed=true
```

File `probe-output.log` chứa output từ Java process con, không phải stdout của probe. Trước khi chạy test, cần xác minh JAR và working directory theo CI; đừng phụ thuộc một relative path mà JUnit runner có thể đổi.

### 11.1. Những điểm production-grade cần bổ sung cho ProcessBuilder test

- Dùng temporary directory/log file riêng cho từng test.
- Không ghi đè cùng `probe-output.log` nếu test chạy song song.
- Đặt timeout đủ cho CI chậm nhưng không vô hạn.
- Đảm bảo process tree con được dọn; `destroyForcibly()` không tự kill mọi subprocess cháu.
- Tránh deadlock vì pipe stdout/stderr đầy: redirect ra file hoặc đọc stream song song.
- Dùng Java binary từ runtime mong muốn; Gradle toolchain và JUnit JVM có thể khác nhau.
- Chỉ thực thi một artifact đã build xong trước integration test.
- Kiểm tra exit code và nội dung report theo các marker ổn định.
- Không dùng dữ liệu nhạy cảm thật trong args hoặc log test.

## 12. Tránh @SpringBootTest cho kỳ vọng context phải fail ngay

Một cách viết dễ sai:

```java
@SpringBootTest(properties = "demo.bootstrap.mode=invalid")
class BrokenStartupTest {

    @Test
    void testFailure() {
        // Method này có thể KHÔNG BAO GIỜ được thực thi.
    }
}
```

Đây là **phản ví dụ**.

`@SpringBootTest` yêu cầu Spring TestContext Framework load application context **trước khi chạy method test**. Nếu context fail, JUnit có thể báo lỗi chuẩn bị test thay vì cho test method cơ hội assert cause.

Với Boot 3.3, không nên dùng `@SpringBootTest` như phương án mặc định để “mong application context không tạo được” nếu bạn cần đọc và kiểm tra exception từ một context đã fail.

**Chọn `ApplicationContextRunner`** khi kiểm tra bean refresh failure. Chọn **process-level test** hoặc một harness gọi `SpringApplication.run` trong scope được kiểm soát khi cần kiểm tra toàn bộ bootstrap.

### 12.1. @SpringBootTest phù hợp cho điều gì?

Nó phù hợp để xác nhận **ứng dụng khởi động thành công** với cấu hình dự kiến, autoconfiguration và các beans chạy được; cũng hữu ích cho web integration tests. Khi mục tiêu của test là **khởi động thất bại có chủ đích**, context runner giúp nhận đối tượng báo lỗi như dữ liệu để assert thay vì biến setup failure thành lỗi framework.

## 13. FailureAnalyzer unit test khác gì kiểm thử reporter?

Ba tầng khác nhau:

| Tầng | Cách thử | Nó chứng minh được |
| --- | --- | --- |
| Analyzer logic | `new Analyzer().analyze(exception)` | Mapping exception → analysis |
| Reporter formatting | `LoggingFailureAnalysisReporter.report(analysis)` hoặc reporter tùy chỉnh | Analysis → output/log |
| Boot wiring/integration | `java -jar app.jar` và capture log | Registration + exception trigger + analyzer + reporter |

Nếu chỉ có unit test analyzer, file `spring.factories` có thể bị lỗi tên package và **production không bao giờ hiện report**.

Nếu chỉ chụp log, logic analyzer có thể sai nhưng test pass do stack trace ngẫu nhiên cũng chứa một chuỗi giống description. Vì vậy test end-to-end nên tìm **action riêng biệt có trong analyzer** và test logic nên assert `FailureAnalysis.getAction()` chính xác.

### 13.1. Nếu muốn test custom FailureAnalysisReporter

`FailureAnalysisReporter` có một method:

```java
void report(FailureAnalysis analysis);
```

Một reporter production có thể ghi structured log hoặc gửi dữ liệu tới hệ thống giám sát. Unit test reporter nên:

1. Tạo `FailureAnalysis` giả, không cần startup thật.
2. Gọi `report`.
3. Kiểm tra payload đã được sanitize.
4. Không gửi network thật trong unit test.
5. Không yêu cầu context phải được refresh.
6. Nếu dùng nhiều reporters, kiểm tra thực sự được đăng ký bằng integration test.

**Lưu ý đăng ký:** Reporter SPI cũng có registration riêng; không nhầm `FailureAnalyzer` với `FailureAnalysisReporter` chỉ vì chúng cùng thuộc package `org.springframework.boot.diagnostics`.

### 13.2. Lỗi quen thuộc: assert cả banner/ANSI

Không nên:

```java
assertThat(output).isEqualTo("...full 200-line startup log...");
```

Nên assert các marker có ý nghĩa:

```java
assertThat(output)
        .contains("APPLICATION FAILED TO START")
        .contains("The demonstration bootstrap mode is invalid.")
        .contains("Set demo.bootstrap.mode=ok and restart.");
```

Đây là **snippet** với biến `output` kiểu chuỗi đã capture. Nó không biên dịch độc lập nếu chưa định nghĩa `output`, nhưng thể hiện nguyên tắc viết assertion bền với thay đổi formatting.

## 14. Kiểm thử khi analyzer không nhận diện được lỗi

Một analyzer có thể cố tình trả null:

```java
FailureAnalysis result =
        analyzer.analyze(new IllegalStateException("not mine"));
```

Kết quả `null` là hành vi hợp lệ. Khi chạy Boot thật, một analyzer khác vẫn có thể nhận diện lỗi; nếu không analyzer nào xử lý được, Boot vẫn có cơ chế report exception khởi động.

Không tạo fallback analyzer “xử lý tất cả Throwable” bằng một message quá chung trừ khi bạn có policy rõ ràng. Nếu fallback chạy trước analyzer chuyên biệt, nó có thể che report hữu ích hơn.

### 14.1. Test priority khi có nhiều analyzer

Spring Boot nạp nhiều analyzer từ classpath. Khi có nhiều ứng viên, thứ tự có thể bị ảnh hưởng bởi `Ordered`/`@Order` và factory ordering. Nếu một exception có thể được nhiều analyzer xử lý:

- Xác định analyzer nào **phải** xử lý.
- Viết unit test cho các loại exception cạnh tranh.
- Đăng ký order rõ nếu API và cách nạp hỗ trợ.
- Kiểm tra integration output trong cấu hình có tất cả analyzers.
- Tránh dựa vào thứ tự xuất hiện tình cờ của JAR trên classpath.

**Không thiết kế hệ thống dựa vào số thứ tự ngẫu nhiên** trong `spring.factories` rồi coi đó là contract giữa các thư viện khác nhau.

## 15. Lỗi Boot có sẵn FailureAnalyzer: cách xây test

Spring Boot có các analyzer cho nhiều lỗi phổ biến, ví dụ:

- Cổng web server đang bị chiếm.
- Thiếu bean hoặc có nhiều ứng viên phù hợp.
- Lỗi bind/validate configuration properties.
- Một số lỗi auto-configuration và classpath không tương thích.
- Bean definition override không được phép.

Đừng tự viết analyzer cho từng lỗi mà Boot đã có report phù hợp. Tuy nhiên cần hiểu **tầng kiểm thử**.

### 15.1. Thiếu bean

Một bean phụ thuộc vào interface không có implementation:

```java
@Configuration(proxyBeanMethods = false)
class MissingDependencyConfig {

    @Bean
    ServiceA serviceA(MissingClient client) {
        return new ServiceA(client);
    }
}
```

Đây là snippet yêu cầu các kiểu `ServiceA` và `MissingClient` được định nghĩa, cùng các import `Configuration`, `Bean`.

Test context runner có thể assert failure/cause liên quan missing bean. Nếu muốn kiểm thử output của analyzer Boot mặc định, chạy Boot full/process với config thật; **context runner không tự chuyển error thành report startup kiểu `APPLICATION FAILED TO START`**.

### 15.2. Port đã được sử dụng

Đây là tình huống dễ viết test **flaky**:

```text
server.port=8080
expect startup failure because 8080 is busy
```

Trên máy developer, port 8080 có thể đang rảnh; trên CI, nó có thể đang bị service khác chiếm. Không nên viết test phụ thuộc trạng thái ngoài ý muốn.

Nếu bắt buộc kiểm tra port conflict:

- Chủ động chiếm một port bằng resource riêng của test theo cơ chế OS phù hợp.
- Đảm bảo server thử kết nối đúng port/socket đang bị giữ.
- Có timeout và cleanup port resource trong `finally`.
- Không dùng port phổ biến cố định nếu test chạy song song.
- Không chỉ assert message của embedded server mà không xác nhận failure cause.
- Cân nhắc test analyzer của lỗi bind độc lập nếu mục tiêu chỉ là formatting của report.

Đối với phần lớn ứng dụng, một test custom analyzer ổn định như demo đáng giá hơn một test chiếm cổng mạng không kiểm soát.

### 15.3. Binding validation failure

Với `@ConfigurationProperties` và Jakarta Bean Validation:

- Đăng ký properties bean (`@ConfigurationPropertiesScan` / `@EnableConfigurationProperties`).
- Có provider validation khi cần, thường từ `spring-boot-starter-validation`.
- Đưa property sai vào `ApplicationContextRunner.withPropertyValues`.
- Kiểm tra root cause hoặc cause chain phù hợp; đôi khi lỗi là `BindValidationException` bị bọc.
- Đừng mong một `@NotBlank` tự phát hiện sai nếu không có provider/binding đúng.
- Nếu test report cụ thể của Boot, bổ sung process/integration test.

## 16. Kiểm thử ApplicationFailedEvent

Spring Boot phát `ApplicationFailedEvent` khi đường khởi động `SpringApplication` thất bại. Event có thể chứa:

- Exception startup.
- Application context, **có thể là null nếu lỗi quá sớm**.

Một Spring bean listener không chắc tồn tại khi lỗi trước context creation; muốn quan sát lỗi từ giai đoạn đầu, đăng ký listener trực tiếp trước `run`.

### 16.1. Listener sớm

```java
SpringApplication application =
        new SpringApplication(StartupCheckApplication.class);

application.addListeners(
        (ApplicationListener<ApplicationFailedEvent>) event -> {
            System.out.println("failed="
                    + event.getException().getClass().getSimpleName());
        });

application.run(args);
```

Đây là snippet **đặt trong một phương thức có `args`**, cần import `SpringApplication`, `ApplicationListener`, `ApplicationFailedEvent` và class ứng dụng của demo. Nó minh họa cách đăng ký listener, không phải yêu cầu thay đổi main của project đang chạy.

Nó không tự đặt exit code hay dọn resource. Trong unit/integration test, tránh để listener gọi repository hoặc `event.getApplicationContext().getBean(...)` mà không xét context có thể chưa tồn tại hoặc đã lỗi.

### 16.2. Test event khác test analysis

- **Event test:** exception có được thông báo đến listener đúng thời điểm không?
- **Analyzer test:** exception có được biến thành description/action hữu ích không?
- **Cleanup test:** những resource đã được sở hữu có được đóng không?
- **Process test:** tiến trình có báo failure và exit status hợp lệ không?

Một test event pass không chứng minh analyzer được đăng ký hoặc reporter hiển thị output.

### 16.3. Event có thể được phát trước context cleanup xong

`ApplicationFailedEvent` không có nghĩa tất cả `@PreDestroy` callback đã chạy. Trong failure handler, event/logging/close context có các mốc riêng. Nếu test cần biết resource đã được đóng, ghi nhận trực tiếp trong resource owner hoặc đọc trạng thái từ process/test harness sau khi `run` trả lỗi, không suy luận từ sự kiện failure.

## 17. Chứng minh FailureAnalyzer không được phép che lỗi

Giả sử analyzer nhận biết một lỗi mode:

```java
FailureAnalysis analysis =
        analyzer.analyze(new StartupPolicyException(
                StartupPolicyException.Problem.INVALID_MODE));
```

Ngay cả khi `analysis` khác `null`, ứng dụng **vẫn thất bại** nếu exception tiếp tục phát ra trong startup.

Đó là hợp đồng tốt:

```text
FailureAnalyzer: "Tôi giúp hiểu lỗi và cách sửa."
FailureReporter: "Tôi trình bày phân tích."
SpringApplication: "Lỗi bootstrap vẫn là lỗi; phải xử lý failure."
Process launcher: "Tôi báo exit status cho OS."
```

Không tạo analyzer tự gọi `System.exit`, không sửa bean, không retry HTTP request hoặc reset database trong `analyze`. Analyzer là **bước chẩn đoán**, cần hoạt động an toàn ngay cả khi hệ thống đang ở trạng thái hỏng.

## 18. Exit code: quan hệ với FailureAnalyzer

Một số người tưởng custom `FailureAnalyzer` có thể làm lỗi nhẹ trở thành exit 0 hoặc quyết định mã 42. Không đúng.

Spring Boot có `ExitCodeGenerator` và `ExitCodeExceptionMapper` phục vụ chính sách mã thoát. Có thể dùng:

```java
public final class InvalidStartupException
        extends RuntimeException implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 42;
    }
}
```

Đây là snippet class Java yêu cầu import `org.springframework.boot.ExitCodeGenerator`. Nó không nằm trong project demo và không phải phần bắt buộc của `StartupPolicyFailureAnalyzer`.

Khi startup thất bại, Boot có đường xác định exit code từ exception hoặc mapper nếu được cấu hình; để biết chính xác **process** trả gì, cần test `java -jar`.

### 18.1. Không dùng System.exit trong test JUnit

`System.exit(42)` gọi ngay trong test process có thể giết cả JUnit/Gradle worker. Việc đó không chứng minh đúng cleanup hay registration.

Thay thế:

- Unit test `getExitCode()` của một exception.
- Integration test Boot không gọi `System.exit` trong process JUnit.
- Process-level test với `ProcessBuilder` hoặc `java -jar` để quan sát exit value.

### 18.2. SpringApplication.exit(context) dùng khi nào?

`SpringApplication.exit(context)` phù hợp khi `SpringApplication.run(...)` **đã trả về context thành công**, rồi ứng dụng muốn tính mã thoát/đóng context có chủ đích.

Nếu `run` ném exception trong refresh/runner, biến context do nó trả về **không tồn tại** ở caller; không thể chỉ gọi `SpringApplication.exit(context)` sau lệnh fail. Đừng tạo context mới chỉ để gọi exit, vì nó có thể tạo thêm resource và gây lỗi mới.

## 19. Capture logs an toàn

Spring Boot test có `OutputCaptureExtension` để capture stdout/stderr ở những test phù hợp.

Ví dụ **snippet** trong test JUnit:

```java
@ExtendWith(OutputCaptureExtension.class)
class OutputCaptureExample {

    @Test
    void capturesText(CapturedOutput output) {
        System.out.println("marker");
        assertThat(output.getOut()).contains("marker");
    }
}
```

Đoạn này cần import `ExtendWith`, `OutputCaptureExtension`, `CapturedOutput`, `Test`, `assertThat`, đặt trong một test source. Nó chỉ chứng minh output capture, **không tự chạy toàn bộ SpringApplication failure path**.

### 19.1. Các rủi ro khi assert logging

- Log format thay đổi theo logging backend/profile/version.
- Stack trace có class và line numbers khác nhau.
- ANSI có thể bật/tắt theo terminal.
- Một số logger async ghi sau thời điểm assertion.
- Nếu đổi `logging.level`, reporter log có thể thay đổi.
- Khi chạy tests song song, stdout/stderr là tài nguyên gần như toàn cục.

Để kiểm thử `FailureAnalysisReporter` cuối cùng, process test redirect file riêng thường rõ ràng hơn và không làm nhiễu logging của test JVM.

### 19.2. Không để secret giả lộ vào báo cáo

Thử bằng một giá trị giả, ví dụ `DUMMY_SECRET_987`, không phải credential thật. Nếu exception message có chứa raw config value, analyzer có thể vô tình phát lại.

Trong custom analyzer của demo, description/action **không đưa mode value thực tế** vào report. Có thể thêm test assert:

```java
assertThat(analysis.getDescription())
        .doesNotContain("DUMMY_SECRET_987");
assertThat(analysis.getAction())
        .doesNotContain("DUMMY_SECRET_987");
```

Đây là snippet bổ sung trong method test có `analysis` phù hợp. Test output có thể phát hiện leak ở analyzer, nhưng vẫn cần kiểm tra stack trace, exception messages, launcher logs và CI logs.

## 20. Debug khi không thấy FailureAnalyzer của mình xuất hiện

Khi ứng dụng fail nhưng chỉ hiện stack trace chung:

1. **Xác nhận exception thực tế**: lỗi có phải loại analyzer xử lý không? Có nằm trong cause chain?
2. **Unit test analyzer**: gọi `analyze(failure)` xem trả `FailureAnalysis` hay `null`.
3. **Kiểm tra vị trí registration file**: phải là `src/main/resources/META-INF/spring.factories`, không phải một tên tương tự.
4. **Kiểm tra key**: phải chính xác `org.springframework.boot.diagnostics.FailureAnalyzer`.
5. **Kiểm tra tên class**: fully qualified class name đúng package, có thể instantiate.
6. **Kiểm tra JAR artifact**: `META-INF/spring.factories` có được đưa vào build output không?
7. **Kiểm tra test launcher**: đang chạy `java -jar`, `bootRun`, IDE hay một context runner? Các đường có độ bao phủ khác nhau.
8. **Kiểm tra reporter/logging**: có thể analysis được tạo nhưng output không hiện như kỳ vọng.
9. **Kiểm tra analyzer khác**: có analyzer nào nhận diện lỗi trước và chiếm đường report không?
10. **Kiểm tra version**: bảo đảm API/registration thuộc Spring Boot bạn chạy, không áp hướng dẫn version mới mà chưa xác minh.
11. **Kiểm tra input error an toàn**: analyzer không nên ném exception thứ hai khi xử lý.
12. **So process test trước/sau sửa** thay vì chỉ thêm debug logs vào analyzer.

### 20.1. Kiểm tra spring.factories nằm trong JAR

Với JDK có lệnh `jar`:

```bash
jar tf build/libs/startup-check-demo-1.0.0.jar \
  | grep 'spring.factories'
```

Vì đây là **Spring Boot executable JAR**, resources ứng dụng thường nằm bên trong `BOOT-INF/classes/META-INF/spring.factories`. `jar tf` chỉ liệt kê archive entries, không chứng minh analyzer được khởi tạo đúng hoặc report được in.

Kết hợp kiểm tra artifact với process test `--demo.bootstrap.mode=invalid` mới chứng minh đủ wiring.

### 20.2. Trình tự chẩn đoán có ý nghĩa

```text
Analyzer unit test PASS?
        |
        +-- NO -> sửa logic analyzer/cause recognition
        |
        +-- YES
             |
             v
File spring.factories có trong runtime artifact?
        |
        +-- NO -> sửa packaging/registration
        |
        +-- YES
             |
             v
java -jar failure scenario có report/action?
        |
        +-- NO -> kiểm tra analyzer order, logging, failure stage
        |
        +-- YES -> wiring FailureAnalyzer/Reporter đã được xác nhận
```

Đây là một flow debug thực dụng: từng bước thu hẹp nguyên nhân, thay vì thay đổi nhiều lớp cấu hình cùng lúc.

## 21. Kiểm thử nhiều loại lỗi có cùng tên exception nhưng nguyên nhân khác

Một exception loại `IllegalStateException` có thể biểu diễn rất nhiều tình huống. Viết analyzer nhận mọi `IllegalStateException` rồi hướng dẫn “thêm database URL” có thể sai khi nguyên nhân thực tế là job runner.

Trong demo, `StartupPolicyException` chứa `Problem` enum. Đó là một cách giữ **thông tin nghiệp vụ có cấu trúc** mà không gắn raw secrets vào message.

Một analyzer khác có thể kiểm tra:

- Type của exception trong cause chain.
- Error code do domain quản lý.
- Tên property không nhạy cảm.
- Những metadata có sẵn và đáng tin.
- Điều kiện môi trường khi chắc chắn đã được chuẩn bị.

Tránh kiểm tra message bằng `contains("password")` như điều kiện duy nhất: đổi ngôn ngữ/format log sẽ làm analyzer hỏng, và việc parse message thô có thể dẫn tới leak.

## 22. Những điểm cần cẩn thận với @ConfigurationProperties validation

Một application dùng:

```java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public record ClientProperties(
        @NotBlank String endpoint) {
}
```

Đây là **snippet**, cần import `ConfigurationProperties`, `Validated`, `jakarta.validation.constraints.NotBlank` và đăng ký properties bean/provider phù hợp. Nó chỉ là ví dụ khác với dự án đầy đủ.

Khi cấu hình thiếu endpoint:

- Context có thể fail trong binding/validation.
- Exception ngoài cùng thường không phải chính `ConstraintViolationException`.
- Boot có built-in analyzer cho một số trường hợp bind/validation.
- Test context runner cần add configuration và validation provider.
- Test nên assert root/cause và property path thích hợp, không đóng đinh một full error message 200 dòng.

**Quan trọng:** thiếu `spring-boot-starter-validation` trong project có thể làm validation không diễn ra như bạn nghĩ. Test phải dựng cấu hình giống production ở phần validation cần thiết.

### 22.1. @Value không giống validation annotation

Demo chính dùng `@Value("${demo.bootstrap.mode:ok}")` và validator thủ công trong `@Bean`, để không cần thêm starter-validation.

Nếu một dự án dùng `@ConfigurationProperties` và Bean Validation thật, hãy test chính cơ chế binding/validation, không suy luận từ kết quả demo `@Value`.

## 23. Hạn chế của các harness test

| Công cụ | Thế mạnh | Không chứng minh được nếu dùng một mình |
| --- | --- | --- |
| Unit test JUnit | Nhanh, test logic analyzer/validator | Spring Boot registration, context cleanup |
| `ApplicationContextRunner` | Tạo context nhỏ, assert refresh failure | Runner invocation, full SpringApplication report/exit |
| `@SpringBootTest` | Full context success, integration | Không tiện assert startup failure vì test setup fail |
| `SpringApplication.run` trong test JVM | Kiểm thử callbacks/events/runner thật | Process exit status nếu không chạy tiến trình con |
| `OutputCaptureExtension` | Assert stdout/stderr trong cùng JVM | Không tự bảo đảm logger async, exit code |
| `ProcessBuilder` | Exit status, log của Java process, wiring | Test chậm hơn; phải quản lý timeout/working directory |
| Manual `java -jar` | Reproduce production-like startup | Không tự chạy lại trong CI nếu chưa script hóa |

Một test suite hiệu quả thường gồm **nhiều unit/context tests nhanh** và **vài integration/process tests có chủ đích**, không cần hàng trăm lần khởi động một Spring Boot process chỉ để kiểm tra từng if branch.

## 24. Những lỗi test phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@SpringBootTest` fail trước khi vào `@Test` | Context lỗi ở test setup | Dùng context runner cho expected failure |
| Context runner báo PASS dù runner sẽ ném | Context runner không gọi `ApplicationRunner` | Dùng `SpringApplication.run`/process test |
| Unit analyzer pass nhưng runtime không báo description | Sai/mất `META-INF/spring.factories` | Kiểm tra artifact + process test |
| Analyzer luôn trả một report chung | Không phân loại exception đúng | Trả `null` khi không hỗ trợ; test negative path |
| Test assert exact BeanCreationException message hay thay đổi | Wrapper và vị trí source khác | Assert root cause/cause chain |
| OutputCapture không thấy report | Logger config/async/capture timing khác | Process test redirect output; marker ổn định |
| Test chết cả JVM | Gọi `System.exit` từ unit test | Chạy app như child process |
| Exit code từ Gradle là 1 dù app có policy 42 | Wrapper trả status riêng | Chạy `java -jar` trực tiếp |
| Test port-in-use lúc pass lúc fail | Port phụ thuộc máy khác | Kiểm soát socket resource hoặc dùng lỗi ổn định |
| Resource đóng chưa đủ một lần | Bean chưa được Spring tạo xong, destructor không có | Cleanup partial initialization riêng |
| Cleanup test thỉnh thoảng có count=2 | Static recorder/context cache hoặc parallel tests | Cô lập state, không dùng context shared |
| Test startup fail làm tests khác ảnh hưởng | Dùng same JVM với global properties/listeners/threads | Dùng process isolation và cleanup |
| Analyzer báo action sai khi nhiều lý do | Không kiểm tra domain error code | Dùng enum/error type và unit test từng nhánh |
| Debug flags làm lộ secret | Condition/config report quá chi tiết | Dùng dữ liệu giả, kiểm soát log sanitization |
| Test có `@Lazy` nên bean lỗi không được tạo | Khởi tạo lười hoãn validation | Ép tạo bean cần test hoặc tắt lazy trong harness |
| Bean bị loại do `@Conditional*` | Test không bật property/profile cần thiết | Bổ sung `withPropertyValues` hoặc user config |
| Test dùng mocks che mất dependency lỗi | Mock đăng ký thay bean thiếu | Test với candidate/condition tương đương production |
| Reporter bị đăng ký hai lần | Trùng metadata hoặc registration | Kiểm tra classpath và cấu hình reporters |
| CI timeout khi process fail | Child process block hoặc stdout pipe đầy | Redirect streams, timeout, destroy child process |

## 25. Chiến lược test cho startup thất bại theo giai đoạn

### 25.1. Lỗi trước ApplicationContext

Ví dụ Config Data loader không đọc được cấu hình bắt buộc. Context có thể chưa tồn tại; một `@Component` observer thông thường không chắc được đăng ký.

Tầng kiểm thử:

- Process test với cấu hình cụ thể, không phụ thuộc biến môi trường thật.
- Listener sớm được đăng ký qua `SpringApplication.addListeners` nếu cần đo `ApplicationFailedEvent`.
- Analyzer tách khỏi container nếu cần nhận diện lỗi rất sớm.
- Không dùng context runner để suy ra mọi hành vi của Config Data bootstrap.

### 25.2. Lỗi trong refresh

Ví dụ bean constructor ném exception hoặc validation thất bại.

Tầng kiểm thử:

- `ApplicationContextRunner` cho config tối thiểu.
- Assert root cause chính xác.
- Kiểm tra dependency đã tạo được cleanup.
- Unit test analyzer của exception liên quan.
- Một process test nếu cần xác nhận reporter cuối cùng.

### 25.3. Lỗi trong runners

Ví dụ `ApplicationRunner` ném exception do check dữ liệu startup không đạt.

Tầng kiểm thử:

- Unit test logic runner bằng fake `ApplicationArguments` nếu có thể.
- Tích hợp `SpringApplication.run` để xác nhận runner thật sự được gọi.
- Process test để xem failure report và non-zero status.
- Kiểm tra `ApplicationReadyEvent` không được phát theo đường thành công.

### 25.4. Lỗi trong @PostConstruct

Nếu `@PostConstruct` tạo resource rồi ném, context failure không đồng nghĩa destructor của chính bean đang fail đã được đăng ký. Cần test cleanup ngay tại method/constructor.

### 25.5. Lỗi sau ready

Request/job lỗi sau khi process đã ready là runtime failure, không tự chạy `FailureAnalyzer` của startup. Cần test exception handling, retry/transaction, readiness/liveness và shutdown policy riêng; không trộn nó với kiểm thử khởi động.

## 26. Viết acceptance criteria cho một startup failure

Thay vì “khi config sai thì app fail”, đặt tiêu chí kiểm tra được:

**Ví dụ yêu cầu:** khi `demo.bootstrap.mode` khác `ok`:

1. Context không refresh thành công.
2. Root cause là `StartupPolicyException` với problem `INVALID_MODE`.
3. Không thực thi runner nghiệp vụ.
4. Analyzer tạo description mô tả mode invalid.
5. Action hướng dẫn `demo.bootstrap.mode=ok`.
6. Reporter in analysis khi chạy JAR với Boot.
7. Process trả non-zero exit status.
8. Không in giá trị mode không tin cậy lên report.
9. Những bean tài nguyên đã được tạo hoàn chỉnh được dọn theo lifecycle.
10. Thử nghiệm không phụ thuộc network port, DB hoặc clock.

Sau khi có acceptance criteria, các tầng test mới được chia hợp lý:

- 1, 2 → context runner.
- 4, 5, 8 → unit analyzer.
- 3, 6, 7 → process-level.
- 9 → context cleanup test.
- 10 → quy tắc test design xuyên suốt.

Không cố ép một test duy nhất xác minh tất cả tiêu chí.

## 27. Checklist QA trước khi merge thay đổi startup diagnostics

- [ ] Exception biểu diễn được domain failure rõ ràng và không chứa secret.
- [ ] Unit tests cho từng loại lỗi analyzer nhận diện.
- [ ] Test unrelated exception trả `null`.
- [ ] Description/action cụ thể, có ích và ổn định.
- [ ] Analyzer không tạo side effect hoặc yêu cầu bean chưa chắc đã có.
- [ ] Custom analyzer được khai báo trong `META-INF/spring.factories`.
- [ ] Class analyzer có thể instantiate từ runtime.
- [ ] File registration có mặt trong output JAR.
- [ ] Test context failure bằng `ApplicationContextRunner`.
- [ ] Assert root cause thay vì full exception stack trace.
- [ ] Test runner failure bằng SpringApplication thật.
- [ ] Không dùng `@SpringBootTest` để kỳ vọng context load fail rồi vào test method.
- [ ] Có test cleanup cho singleton hoàn tất khởi tạo.
- [ ] Có test xử lý resource mở dở trong constructor/factory nếu liên quan.
- [ ] Không dùng `System.exit` trong JUnit process.
- [ ] Có process-level test cho report và status.
- [ ] Child process có timeout, stream redirection và cleanup.
- [ ] Không phụ thuộc một port cố định bên ngoài.
- [ ] Logging assertions dựa vào marker, không dựa vào timestamp/ANSI.
- [ ] Kiểm tra success path để không làm hỏng khởi động hợp lệ.
- [ ] Kiểm tra behavior sau `ApplicationRunner` và mốc readiness.
- [ ] Cân nhắc lazy initialization có làm test bỏ qua bean lỗi không.
- [ ] Không nhầm FailureAnalyzer với ExitCodeGenerator hay FailureAnalysisReporter.
- [ ] Tài liệu hướng dẫn sửa lỗi không yêu cầu cung cấp secret qua CLI.
- [ ] Test không để file, process hoặc resource giả lưu lại sau khi hoàn thành.

## 28. Bài tập thực hành có đáp án

### Bài 1: thay đổi action theo lỗi

Sửa `StartupPolicyFailureAnalyzer` để `RUNNER_BLOCKED` đưa action khác, ví dụ yêu cầu kiểm tra một feature flag cụ thể. Viết unit test xác nhận exact action string và đảm bảo `INVALID_MODE` không bị ảnh hưởng.

**Đáp án cốt lõi:** viết hai assertion riêng theo `Problem`; không phân loại bằng cách parse exception message.

### Bài 2: xóa spring.factories

Xóa file registration (trong bản sao project demo), chạy:

```bash
./gradlew test bootJar
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=invalid
```

Tại sao unit analyzer có thể vẫn pass, nhưng báo cáo `Description/Action` đặc thù không xuất hiện?

**Đáp án:** test unit tạo trực tiếp analyzer, còn Boot chỉ có thể tự nạp custom analyzer khi registration ở runtime đúng. Lỗi startup vẫn xảy ra, nhưng con đường báo cáo có thể quay về generic failure report.

### Bài 3: lỗi runner với context runner

Tạo một bean `ApplicationRunner` luôn throw, đưa vào `ApplicationContextRunner` rồi assert `context.hasNotFailed()`. Giải thích kết quả.

**Đáp án:** context runner không tự gọi `ApplicationRunner.run(...)`; runner chỉ được gọi bởi `SpringApplication` trong startup.

### Bài 4: kiểm tra cleanup

Trong `ContextCleanupTests`, thay `@Bean(destroyMethod = "close")` bằng `@Bean(destroyMethod = "")` và quan sát hành vi khi resource implements `AutoCloseable`. Vì sao test cleanup có thể đổi kết quả?

**Đáp án:** khi disable destroy method suy luận/đăng ký, Spring không tự gọi method đó theo cách trước. Đây chỉ là thí nghiệm; đừng dùng nó làm mẫu production.

### Bài 5: thêm một lớp wrapper

Bọc `StartupPolicyException` bằng hai lớp exception trước khi gọi analyzer:

```java
Throwable failure = new IllegalStateException(
        "outer",
        new RuntimeException(
                "inner",
                new StartupPolicyException(
                        StartupPolicyException.Problem.INVALID_MODE)));
```

`AbstractFailureAnalyzer` còn nhận diện được problem không?

**Đáp án:** có, vì nó tìm type trong cause chain; unit test nên chứng minh analysis khác null và action đúng.

### Bài 6: test port conflict không flaky

Viết test web server fail khi port bị chiếm nhưng **không dùng 8080 cố định**. Thiết kế cách giữ socket của test có timeout/cleanup và xác nhận port thực sự bị chiếm trước khi bootstrap.

**Đáp án cốt lõi:** ownership của port resource phải nằm trong test; không giả định máy CI có sẵn một process chiếm cổng.

### Bài 7: kiểm thử exit code

Thêm một exception implements `ExitCodeGenerator` trả 29, rồi chạy JAR như process con. Vì sao assert `getExitCode()==29` trong unit test chưa đủ?

**Đáp án:** unit test chỉ kiểm tra phương thức; process status còn phụ thuộc failure handler/launcher và những thao tác trong `main`.

### Bài 8: test khi cleanup lỗi

Trong một test riêng, tạo resource `close()` ném exception trong lúc một bean khác fail startup. Kiểm tra root cause có còn là lỗi bootstrap không và cleanup failure được ghi nhận thế nào. Không ép test assert một log stack trace cố định khi framework có thể wrap exceptions theo nhiều kiểu.

### Bài 9: test khi bật lazy initialization

Bật `spring.main.lazy-initialization=true` trong process demo. Vì sao `StartupMarker` có thể chưa được tạo trong refresh ở một cấu hình mà không bean nào cần nó? Điều gì xảy ra nếu runner phụ thuộc trực tiếp marker?

**Đáp án:** lazy có thể trì hoãn bean; nhưng runner được Boot yêu cầu và injection của runner có thể làm marker được tạo trước khi hoàn tất startup. Phải kiểm tra giai đoạn thực tế thay vì áp kỳ vọng context runner một cách máy móc.

### Bài 10: rà soát secret trong failure report

Đưa một giá trị giả kiểu `DUMMY_SECRET_987` vào mode invalid, chạy JAR và kiểm tra analysis description/action **không echo input**. Nếu stack trace/framework log vẫn chứa giá trị, cần xem nguồn exception message và các logging formatter; không chỉ sửa một assertion của analyzer.

## 29. Những ngộ nhận cần loại bỏ

**Ngộ nhận 1:** “`FailureAnalyzer` làm ứng dụng khởi động thành công nếu xử lý được lỗi.”

Sai. Nó tạo phân tích và hành động gợi ý, không nuốt exception.

**Ngộ nhận 2:** “`@Component` đủ để custom analyzer luôn có mặt ở lỗi sớm.”

Sai theo hướng dẫn registration của Spring Boot 3.3: cần `META-INF/spring.factories` để nạp analyzer vào bootstrap reporting.

**Ngộ nhận 3:** “Test analyzer trực tiếp là đã test luôn console report.”

Sai. Unit analyzer không kiểm tra runtime registration hoặc reporter.

**Ngộ nhận 4:** “ApplicationContextRunner có thể kiểm tra mọi lỗi của `SpringApplication.run`.”

Sai. Context runner không gọi runner và không tái hiện toàn bộ application lifecycle của Boot.

**Ngộ nhận 5:** “Nếu test `@SpringBootTest` fail trước khi vào method thì ta đã có một test expected failure tốt.”

Chưa hẳn. Test setup failure không phải một assertion có chủ đích về cause và action.

**Ngộ nhận 6:** “Chỉ cần grep `APPLICATION FAILED TO START` thì integration đã hoàn chỉnh.”

Chưa đủ. Cần xác minh description/action đặc thù, exit status và nguồn lỗi.

**Ngộ nhận 7:** “Có lỗi startup thì mọi resource chắc chắn được @PreDestroy.”

Sai. Bean chưa hoàn tất tạo hoặc resource ngoài Spring có thể không được quản lý.

**Ngộ nhận 8:** “Một port số cố định sẽ luôn bị chiếm trên máy test.”

Sai. Test sẽ flaky nếu phụ thuộc trạng thái OS ngoài phạm vi test.

**Ngộ nhận 9:** “ExitCodeGenerator nằm trong FailureAnalyzer.”

Sai. Đây là hai cơ chế khác nhau: chẩn đoán và báo mã thoát.

**Ngộ nhận 10:** “In đủ stack trace là đủ; không cần action.”

Sai với trải nghiệm vận hành: một report có hướng dẫn cụ thể thường giúp sửa cấu hình nhanh hơn, miễn là không tiết lộ thông tin nhạy cảm.

## 30. Tổng kết

Một chiến lược kiểm thử startup thất bại tốt trong Spring Boot 3.3 gồm:

1. **Dùng `ApplicationContextRunner`** để kiểm thử những lỗi xảy ra khi tạo/refresh context. Assert context failed và root cause, kiểm tra cleanup của singleton đã tạo.
2. **Dùng unit test cho `FailureAnalyzer`**: lỗi được nhận diện, `FailureAnalysis.getDescription()` / `getAction()` đúng, `getCause()` hợp lý, lỗi không liên quan trả `null`.
3. **Đăng ký analyzer bằng `META-INF/spring.factories`**, không chỉ dựa vào component scanning.
4. **Chạy JAR thật** để xác minh Boot đã nạp analyzer, reporter hiển thị action và process trả non-zero khi startup fail.
5. **Kiểm thử runner failure bằng SpringApplication thật**: context runner không gọi `ApplicationRunner`.
6. **Giữ các test ổn định**: không phụ thuộc port cố định, logging layout, thứ tự startup log hoặc raw exception message.
7. **Bảo vệ JVM test**: không gọi `System.exit` trực tiếp trong JUnit; dùng process con để quan sát status.
8. **Tách cleanup khỏi reporting**: `FailureAnalyzer` không đóng resource; các tài nguyên chưa được Spring sở hữu cần cleanup ngay tại nơi cấp phát.
9. **Kiểm tra cả đường thành công**, để analyzer/test policy không làm ứng dụng từ chối mọi cấu hình.
10. **Kiểm thử không rò rỉ bí mật** trong description, action, exception, báo cáo startup và log pipeline.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): failure reporting, events và vòng đời startup.
- [Spring Boot 3.3 — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html): `AbstractFailureAnalyzer` và `META-INF/spring.factories`.
- [Spring Boot 3.3.13 — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html): `analyze(Throwable)` trả `FailureAnalysis` hoặc `null`.
- [Spring Boot 3.3.13 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): description, action và cause.
- [Spring Boot 3.3.13 — AbstractFailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html): nhận diện nested exception.
- [Spring Boot 3.3.13 — FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html): reporting contract.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): tạo context thử nghiệm và failed context assertions.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): test slices, Spring Boot Test và JUnit.
- [Spring Framework 6.1 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): bean creation, initialization, destruction.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter test lifecycle và assertions.
