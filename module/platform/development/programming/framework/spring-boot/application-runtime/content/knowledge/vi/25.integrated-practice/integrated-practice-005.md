# Mô phỏng runner lỗi và tạo FailureAnalyzer cho lỗi khởi động riêng trong Spring Boot

## 1. Mục tiêu bài thực hành

Spring Boot có thể tạo xong ApplicationContext nhưng vẫn **khởi động thất bại** nếu ApplicationRunner hoặc CommandLineRunner ném exception. Đây là ranh giới quan trọng: bean đã được instantiate và ApplicationStartedEvent có thể đã phát, nhưng ApplicationReadyEvent chưa xuất hiện, ứng dụng chưa sẵn sàng nhận công việc nghiệp vụ.

Khi runner thất bại vì một chính sách riêng, ví dụ vùng triển khai không được chấp nhận, stack trace chung thường khó hiểu với người vận hành. Ta sẽ tạo **FailureAnalyzer** để biến exception nghiệp vụ thành báo cáo rõ ràng với **Description** và **Action**, trong khi vẫn giữ nguyên kết quả startup thất bại.

Mục tiêu cụ thể:

1. Nắm thứ tự ApplicationStartedEvent, ApplicationRunner, ApplicationReadyEvent và ApplicationFailedEvent.
2. Viết hai runner có @Order để xác minh runner phía sau không chạy khi runner trước fail.
3. Ném StartupPolicyException có thông tin cấu trúc thay vì exception mơ hồ.
4. Viết StartupPolicyFailureAnalyzer nhận Throwable, tìm cause gốc, tạo FailureAnalysis.
5. Đăng ký analyzer bằng META-INF/spring.factories và chứng minh Spring Boot thực sự load.
6. Thử nhánh hợp lệ, nhánh lỗi, xem báo cáo người dùng và exit status.
7. Viết unit test JUnit 5 cho analyzer với exception đã bị SpringApplication bọc.
8. Phân biệt FailureAnalyzer trong startup với các error handler dùng sau Ready.

Phiên bản nhất quán: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, Gradle**. Ví dụ dùng ứng dụng **non-web** để dễ thấy kết quả khi CLI kết thúc.

## 2. Vị trí của runner trong lifecycle

~~~text
SpringApplication.run(args)
       |
       +-- Environment va tao ApplicationContext
       +-- Refresh context
       |     +-- Register / instantiate beans
       |     +-- Dependency injection
       |     +-- @PostConstruct, init callbacks
       |     +-- SmartLifecycle.start
       |
       +-- ApplicationStartedEvent
       +-- LivenessState.CORRECT
       |
       +-- ApplicationRunner / CommandLineRunner
       |     +-- Runner thu nhat
       |     |     +-- Neu throw exception -> failure handling
       |     +-- Runner tiep theo neu truoc thanh cong
       |
       +-- ApplicationReadyEvent neu runners thanh cong
       +-- ReadinessState.ACCEPTING_TRAFFIC
       |
       +-- run() returns
~~~

**Started khác Ready.** ApplicationStartedEvent đến sau refresh nhưng trước runners. ApplicationReadyEvent chỉ xuất hiện sau runners trên đường khởi động thành công. Khi runner ném exception, Boot chuyển sang failure handling, phát ApplicationFailedEvent cho listener phù hợp và báo nguyên nhân.

| API | Thời điểm | Vai trò |
| --- | --- | --- |
| @PostConstruct | Bean initialization trong context refresh | Init tài nguyên của một bean |
| ApplicationStartedEvent | Sau context refresh, trước runners | Quan sát mốc started |
| ApplicationRunner | Sau Started, trước Ready | Thực thi startup policy/job có kiểm soát |
| CommandLineRunner | Cùng giai đoạn runners | Giống ApplicationRunner nhưng nhận String... |
| ApplicationReadyEvent | Sau khi mọi runner hoàn tất | Quan sát mốc ready |
| ApplicationFailedEvent | Lúc SpringApplication.run thất bại | Quan sát startup failure |
| FailureAnalyzer | Trong cơ chế phân tích startup failure | Tạo báo cáo lỗi dễ hiểu |

**ApplicationRunner** nhận ApplicationArguments gồm options và non-options đã phân tích. **CommandLineRunner** nhận String... args nguyên bản. Cả hai có thể triển khai Ordered hoặc dùng @Order để chỉ định thứ tự.

Không nhầm runner với một worker tự động chạy background. SpringApplication thông thường gọi runner đồng bộ. Nếu runner chỉ submit tác vụ rồi return, Boot có thể đi tới Ready trong khi tác vụ async chưa kết thúc.

## 3. FailureAnalyzer là gì?

Trong Spring Boot, FailureAnalyzer là API phân tích một Throwable do startup failure và có thể trả FailureAnalysis:

~~~java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
~~~

Đây là chữ ký minh họa của API, không phải source cần tự định nghĩa. Import thực là **org.springframework.boot.diagnostics.FailureAnalyzer**.

FailureAnalysis có constructor:

~~~java
new FailureAnalysis(description, action, cause)
~~~

- **Description**: mô tả sự cố, cấu hình/bước nào không hợp lệ.
- **Action**: hướng dẫn người vận hành sửa được ngay.
- **Cause**: Throwable gốc phù hợp với báo cáo.

Nếu analyzer **không nhận diện** được lỗi, phải trả **null** để nhường cho analyzer khác. Một analyzer tốt không bắt toàn bộ RuntimeException rồi gắn sai cùng một thông báo.

Spring Boot có **FailureAnalysisReporter** mặc định để log kết quả; analyzer **không tự cứu ứng dụng**, không làm runner tiếp tục, không sửa config, không quyết định readiness hay exit code nghiệp vụ.

~~~text
Runner.run()
   |
   +-- throw StartupPolicyException
   |
SpringApplication runner caller
   |
   +-- Co the boc loi boi IllegalStateException
   |
SpringApplication startup failure handling
   |
   +-- FailureAnalyzers tu spring.factories
   |     |
   |     +-- StartupPolicyFailureAnalyzer
   |          |
   |          +-- Find StartupPolicyException in cause chain
   |          +-- FailureAnalysis(description, action, cause)
   |
LoggingFailureAnalysisReporter
   |
APPLICATION FAILED TO START
   |
run() fails and Ready not reached
~~~

### Tại sao phải tìm cause sâu?

Spring Boot có thể bọc lỗi runner:

~~~text
IllegalStateException: Failed to execute ApplicationRunner
    Caused by: StartupPolicyException:
      Unsupported startup region: moon-base
~~~

Đây là **mẫu ý nghĩa**, stack trace từng dòng phụ thuộc phiên bản. Nếu analyzer chỉ xét đối tượng Throwable ngoài cùng, nó có thể không thấy StartupPolicyException. Có hai hướng:

- Implement FailureAnalyzer và duyệt Throwable.getCause(), như project này.
- Extend AbstractFailureAnalyzer<StartupPolicyException> để base class tìm type trong cause chain.

Với mã có package do người dùng tạo, ngoại lệ riêng nên chứa **tên key và giá trị không nhạy cảm** để báo đúng. Không đưa secrets, access token, password hoặc connection string có credential vào lỗi.

## 4. Kịch bản nghiệp vụ của lab

Ứng dụng chỉ cho phép hai giá trị cấu hình **demo.startup.region**:

- ap-southeast-1: hợp lệ, là default.
- ap-northeast-1: hợp lệ thứ hai.
- moon-base: invalid, dùng để kích hoạt lỗi có chủ đích.

**RegionValidationRunner** có @Order(10): in region và ném StartupPolicyException nếu không thuộc allowlist.

**StartupAuditRunner** có @Order(20): in RUNNER_AUDIT. Khi runner đầu thất bại, runner này không được gọi trong đường startup thành công.

**StartupEventLog**: in EVENT_STARTED và EVENT_READY.

Listener ApplicationFailedEvent được đăng ký trực tiếp vào SpringApplication **trước run** để quan sát lỗi ngay cả nếu context chưa tạo xong.

**StartupPolicyFailureAnalyzer**: tìm đúng exception nghiệp vụ xuyên cause chain; tạo Description và Action, không bắt lỗi không liên quan.

## 5. Cấu trúc project

~~~text
runner-failure-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          RunnerFailureLab.java
          events/
            StartupEventLog.java
          startup/
            StartupPolicyException.java
            RegionValidationRunner.java
            StartupAuditRunner.java
          diagnostics/
            StartupPolicyFailureAnalyzer.java
      resources/
        application.properties
        META-INF/
          spring.factories
    test/
      java/
        demo/
          diagnostics/
            StartupPolicyFailureAnalyzerTest.java
~~~

**Điểm không được sai:** file discovery phải ở đúng **src/main/resources/META-INF/spring.factories**. Đây là cơ chế Spring Boot dùng để tìm custom FailureAnalyzer. Nó không nằm trong root source Java, không phải application.properties, và không phải AutoConfiguration.imports.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'runner-failure-lab'
~~~

### 5.2. build.gradle

~~~groovy
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
~~~

spring-boot-starter là đủ cho một CLI chạy ApplicationRunner. Không cần Tomcat hay servlet container, nên kết quả Ready và failure rõ hơn. spring-boot-starter-test cung cấp JUnit 5 và AssertJ.

Cần JDK 17+, Gradle tương thích, quyền tải dependencies/plugins hoặc cache chứa chúng. Nếu project có wrapper, sử dụng gradlew; nếu chưa có, sử dụng Gradle đã cài.

### 5.3. application.properties

~~~properties
spring.application.name=runner-failure-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false

demo.startup.region=ap-southeast-1
~~~

Command-line option có thể override vùng mặc định. Không bật web server vì lab kiểm tra runner/failure chứ không cần endpoint. Hai property banner/log-startup-info giúp ít noise, nhưng Gradle, logger và JVM vẫn có thể in thêm log.

## 6. Main và ứng dụng quan sát events

### 6.1. RunnerFailureLab.java

Tệp **src/main/java/demo/RunnerFailureLab.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class RunnerFailureLab {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(RunnerFailureLab.class);

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("EVENT_FAILED"));

        app.run(args);
    }
}
~~~

**Tại sao addListeners trực tiếp?** ApplicationFailedEvent có thể phát khi context tạo dở hoặc chưa được refresh; một @Component listener chưa chắc đã tồn tại đủ sớm. Đăng ký với SpringApplication trước run giúp nhận sự kiện này trong mô phỏng lỗi runner.

**Không bắt exception rồi chỉ log trong main.** Nếu một chính sách bắt buộc sai, để run thất bại thực sự. Khi lỗi thoát ra main non-web, JVM thường trả exit status khác 0; Gradle bootRun cũng có thể báo task thất bại. Không hardcode status cụ thể khi dùng wrapper vì công cụ và OS có thể khác.

### 6.2. StartupEventLog.java

Tệp **src/main/java/demo/events/StartupEventLog.java**:

~~~java
package demo.events;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventLog {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
    }
}
~~~

Lớp được scan vì nằm trong subpackage của demo. Chỉ ghi hai mốc; ApplicationFailedEvent đã có listener gắn vào SpringApplication. Trong nhánh lỗi runner, ta kỳ vọng EVENT_STARTED rồi EVENT_FAILED nhưng không có EVENT_READY.

## 7. Exception nghiệp vụ chuyên biệt

Tệp **src/main/java/demo/startup/StartupPolicyException.java**:

~~~java
package demo.startup;

public final class StartupPolicyException extends RuntimeException {

    private final String propertyName;
    private final String rejectedValue;

    public StartupPolicyException(String propertyName,
                                  String rejectedValue) {
        super("Unsupported startup region: " + rejectedValue);
        this.propertyName = propertyName;
        this.rejectedValue = rejectedValue;
    }

    public String getPropertyName() {
        return propertyName;
    }

    public String getRejectedValue() {
        return rejectedValue;
    }
}
~~~

Trong lab này, rejectedValue là region không nhạy cảm. Trong ứng dụng thật, nếu validation liên quan password, API secret, kết nối DB hoặc bearer token, không ghi raw giá trị vào exception message và FailureAnalysis. Dùng key/nguồn cấu hình và action bảo mật hơn.

**RuntimeException** phù hợp để biểu thị một điều kiện khởi động không thể tiếp tục. Nếu exception phát sinh từ một lỗi khác, nên giữ cause gốc khi chuyển sang custom exception thay vì bỏ mất stack trace.

## 8. ApplicationRunner được sắp thứ tự

### 8.1. RegionValidationRunner.java

Tệp **src/main/java/demo/startup/RegionValidationRunner.java**:

~~~java
package demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class RegionValidationRunner implements ApplicationRunner {

    private final Environment environment;

    public RegionValidationRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String region = environment.getProperty(
                "demo.startup.region", "ap-southeast-1");

        System.out.println("RUNNER_VALIDATE=" + region);

        boolean valid = "ap-southeast-1".equals(region)
                || "ap-northeast-1".equals(region);

        if (!valid) {
            throw new StartupPolicyException(
                    "demo.startup.region", region);
        }

        System.out.println("RUNNER_VALIDATED");
    }
}
~~~

Ở đây **Environment** được dùng để đọc từ application.properties hoặc command-line arguments theo thứ tự property sources của Spring Boot. ApplicationArguments trong method signature hợp lệ nhưng không cần dùng cho bài lab; nếu chỉ muốn options của command line, có thể truy cập getOptionValues.

Đặt validation trong run thay vì constructor để chứng minh lỗi sau Started: bean có thể tạo thành công, ApplicationContext refresh đã hoàn tất, chỉ đến khi runner thực thi mới phát hiện region không hợp lệ.

@Order(10) không sắp mọi bean constructor hay @PostConstruct; nó chỉ áp dụng theo ngữ cảnh sắp xếp runner và các component khác có Ordered semantics.

### 8.2. StartupAuditRunner.java

Tệp **src/main/java/demo/startup/StartupAuditRunner.java**:

~~~java
package demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class StartupAuditRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER_AUDIT");
    }
}
~~~

Với region đúng, có RUNNER_VALIDATED rồi RUNNER_AUDIT. Nếu runner @Order(10) ném exception, đường thực thi runner thường dừng tại lỗi đó và **RUNNER_AUDIT không xuất hiện**.

Nếu runner tự submit background tasks thì failure không tự hủy mọi task đã submit. Cần thiết kế ownership, timeout và cleanup cho mọi task/connection đã cấp phát.


## 9. Custom FailureAnalyzer và registration

### 9.1. StartupPolicyFailureAnalyzer.java

Tệp **src/main/java/demo/diagnostics/StartupPolicyFailureAnalyzer.java**:

~~~java
package demo.diagnostics;

import demo.startup.StartupPolicyException;
import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalyzer;

public final class StartupPolicyFailureAnalyzer
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof StartupPolicyException problem) {
                String description =
                        "Startup policy rejected "
                        + problem.getPropertyName()
                        + "=" + problem.getRejectedValue()
                        + ". Allowed regions: ap-southeast-1, "
                        + "ap-northeast-1.";

                String action =
                        "Set --demo.startup.region=ap-southeast-1 "
                        + "or --demo.startup.region=ap-northeast-1; "
                        + "then restart. Check active profiles "
                        + "and deployment configuration.";

                return new FailureAnalysis(
                        description, action, problem);
            }

            current = current.getCause();
        }

        return null;
    }
}
~~~

**Các điểm kỹ thuật đã được xác định:**

1. Interface FailureAnalyzer của Spring Boot 3.3 có method analyze(Throwable) trả FailureAnalysis hoặc null.
2. Constructor FailureAnalysis(String description, String action, Throwable cause) là API có thật.
3. Java 17 hỗ trợ pattern matching instanceof để bắt StartupPolicyException.
4. Vòng while duyệt cause chain nên vẫn tìm được lỗi bên trong IllegalStateException do SpringApplication bọc.
5. Trả null nếu không thấy StartupPolicyException, tránh che analyzer có sẵn của Boot.
6. Analyzer là public class với constructor no-arg mặc định; phù hợp cơ chế tạo instance qua factory discovery.
7. Analyzer không cần @Component/@Bean vì có thể được gọi khi ApplicationContext chưa refresh xong.
8. Nội dung mô tả dễ hành động nhưng không tự giải quyết lỗi hoặc đặt exit status.

Nếu project có nhiều loại startup policy, hãy tách enum/error code hoặc structured exception fields; đừng phân loại chỉ bằng một đoạn text tiếng Anh trong exception.getMessage() dễ thay đổi.

### 9.2. META-INF/spring.factories

Tệp **src/main/resources/META-INF/spring.factories** phải có chính xác:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=demo.diagnostics.StartupPolicyFailureAnalyzer
~~~

Spring Boot How-to yêu cầu đăng ký custom FailureAnalyzer bằng **spring.factories**. Cơ chế này cho phép Bootstrap tìm thấy analyzer khi context chưa đủ khả năng component scan đầy đủ.

Không thay thế bằng:

- @Component đặt trên StartupPolicyFailureAnalyzer.
- @Bean method trong @Configuration.
- Một dòng trong application.properties.
- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports, vì đây là cơ chế dành cho auto-configuration, không phải custom FailureAnalyzer registration theo Boot 3.3.
- Một file spring.factories ở root project nhưng không nằm trên runtime classpath.

Nếu tên package class thay đổi, phải sửa fully qualified class name trong spring.factories và rebuild để resource mới nằm trong classpath.

### 9.3. Vì sao cần Description và Action riêng?

| Trường | Ví dụ | Giá trị vận hành |
| --- | --- | --- |
| Description | Startup policy rejected demo.startup.region=moon-base | Chỉ rõ lỗi vừa xảy ra |
| Description | Allowed regions: ap-southeast-1, ap-northeast-1 | Nêu hợp đồng cho phép |
| Action | Set --demo.startup.region=ap-southeast-1 | Lệnh có thể thực hiện |
| Action | Check active profiles and deployment configuration | Gợi ý nguồn sai thường gặp |
| Cause | StartupPolicyException | Vẫn biết Throwable gốc |

Không dùng một thông điệp mơ hồ như “Application error, contact support” khi đã có thể nêu key và phương án sửa. Không bao giờ đưa secret thực vào description, action hoặc Throwable.getMessage().

### 9.4. FailureAnalysisReporter và logging

Spring Boot có LoggingFailureAnalysisReporter dùng để in khối **APPLICATION FAILED TO START / Description / Action**. Trong bài này không cần tự tạo reporter. Analyzer tạo **dữ liệu chẩn đoán**, reporter quyết định cách hiển thị.

Ngay cả khi custom report được in, JVM/Gradle vẫn có thể in stack trace gốc vào stderr. Đây không có nghĩa analyzer bị gọi sai; hai kênh báo cáo phục vụ người đọc khác nhau.

## 10. Chạy thành công

Nếu project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper nhưng Gradle được cài phù hợp:

~~~bash
gradle bootRun
~~~

Với default **demo.startup.region=ap-southeast-1**, các dòng do mã demo in theo thứ tự:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=ap-southeast-1
RUNNER_VALIDATED
RUNNER_AUDIT
EVENT_READY
~~~

Log của Gradle, Boot hoặc JVM có thể xen giữa; các dòng trên là **subset marker của demo**, không phải toàn bộ stdout.

Để thử region hợp lệ thứ hai:

~~~bash
./gradlew bootRun --args="--demo.startup.region=ap-northeast-1"
~~~

Marker dự kiến:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=ap-northeast-1
RUNNER_VALIDATED
RUNNER_AUDIT
EVENT_READY
~~~

Các marker có ý nghĩa:

- EVENT_STARTED: SpringApplication đã qua context.refresh và tới mốc started.
- RUNNER_VALIDATE: runner đầu bắt đầu.
- RUNNER_VALIDATED: allowlist hợp lệ.
- RUNNER_AUDIT: runner sau thực sự chạy.
- EVENT_READY: toàn bộ runners hoàn tất.

App non-web không giữ Tomcat, nên có thể thoát tự nhiên sau khi run kết thúc và không còn non-daemon threads khác. Không thêm System.exit(0) vào demo, vì như vậy có thể làm kết quả test phụ thuộc vào cách kết thúc process.

## 11. Chạy lỗi khởi động do runner

Chạy:

~~~bash
./gradlew bootRun --args="--demo.startup.region=moon-base"
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun --args="--demo.startup.region=moon-base"
~~~

Marker do demo in theo thứ tự:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=moon-base
EVENT_FAILED
~~~

**Không có** RUNNER_VALIDATED, RUNNER_AUDIT, EVENT_READY trên nhánh startup thành công. Nguyên nhân là runner @Order(10) ném StartupPolicyException, Boot xử lý failure trước khi gọi runner @Order(20).

Nếu spring.factories được packaging và class đúng, khối báo cáo thường có nội dung tương đương:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Startup policy rejected demo.startup.region=moon-base.
Allowed regions: ap-southeast-1, ap-northeast-1.

Action:

Set --demo.startup.region=ap-southeast-1
or --demo.startup.region=ap-northeast-1;
then restart. Check active profiles
and deployment configuration.
~~~

**Đây là trích đoạn đã xuống dòng để đọc dễ hơn**, không phải toàn bộ console output cố định. Logger có thể wrap câu trên ít/nhiều dòng, thêm ANSI color, timestamp, stack trace và báo lỗi Gradle. QA cần kiểm tra **nội dung ổn định** của Description/Action và event markers, không assert toàn bộ log từng dòng.

### Chuyện gì xảy ra sau exception?

1. Context đã refresh; EVENT_STARTED in.
2. RegionValidationRunner ném StartupPolicyException.
3. SpringApplication có thể bọc lỗi trong IllegalStateException có thông điệp Failed to execute ApplicationRunner.
4. SpringApplication đi vào startup failure handling; ApplicationFailedEvent được phát cho listener đã đăng ký, in EVENT_FAILED.
5. Custom FailureAnalyzer tìm StartupPolicyException trong chuỗi cause.
6. LoggingFailureAnalysisReporter xuất Description và Action.
7. SpringApplication.run không trả về context thành công; ứng dụng non-web thường kết thúc với non-zero status.

**FailureAnalyzer không làm exception biến mất** và không tự tạo exit code cụ thể. Nếu cần mã thoát nghiệp vụ, dùng ExitCodeGenerator hoặc ExitCodeExceptionMapper theo hợp đồng riêng.

### Thử executable JAR

~~~bash
./gradlew bootJar
java -jar build/libs/runner-failure-lab-1.0.0.jar --demo.startup.region=moon-base
~~~

Để xem thành phần được đóng gói:

~~~bash
jar tf build/libs/runner-failure-lab-1.0.0.jar
~~~

Trong executable JAR cần có **BOOT-INF/classes/META-INF/spring.factories** và class demo/diagnostics/StartupPolicyFailureAnalyzer.class. Nếu resource bị loại khỏi build, startup vẫn fail vì runner nhưng có thể chỉ còn stack trace chung, không có custom Description/Action.

## 12. Unit test thực hành

Tệp **src/test/java/demo/diagnostics/StartupPolicyFailureAnalyzerTest.java**:

~~~java
package demo.diagnostics;

import demo.startup.StartupPolicyException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class StartupPolicyFailureAnalyzerTest {

    private final StartupPolicyFailureAnalyzer analyzer =
            new StartupPolicyFailureAnalyzer();

    @Test
    void describesWrappedStartupPolicyViolation() {
        StartupPolicyException cause =
                new StartupPolicyException(
                        "demo.startup.region", "moon-base");

        IllegalStateException wrapper =
                new IllegalStateException(
                        "Failed to execute ApplicationRunner", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .contains("demo.startup.region=moon-base")
                .contains("ap-southeast-1");
        assertThat(analysis.getAction())
                .contains("--demo.startup.region=ap-southeast-1");
        assertThat(analysis.getCause()).isSameAs(cause);
    }

    @Test
    void returnsNullWhenFailureIsNotOurs() {
        FailureAnalysis analysis = analyzer.analyze(
                new IllegalStateException("Unrelated startup failure"));

        assertThat(analysis).isNull();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Hai unit tests này kiểm tra analyzer có nhận ra **cause bên trong wrapper** và không chiếm lỗi thuộc module khác. JUnit/Gradle output có thể khác theo phiên bản nên không assert một stdout duy nhất, chỉ assert test pass.

**Unit test gọi trực tiếp analyzer chưa đủ để chứng minh spring.factories được phát hiện**. Cần chạy bootRun hoặc java -jar nhánh moon-base để xác minh end-to-end failure analysis.

### Ý tưởng integration test

Dùng một process Java tách biệt có timeout, thu stdout/stderr và exit code:

1. Chạy với default: marker EVENT_READY và exit code success.
2. Chạy moon-base: marker EVENT_FAILED, custom Description/Action, không có EVENT_READY, exit code non-zero.
3. Chạy với một bản đóng gói cố ý bỏ spring.factories ở môi trường thử: lỗi runner vẫn xảy ra nhưng không còn custom action.
4. Chạy một lỗi không liên quan StartupPolicyException để chắc custom analyzer trả null.

Không dùng ApplicationContextRunner như test **duy nhất** cho ApplicationRunner: ApplicationContextRunner tạo/refresh context để test cấu hình, không nhất thiết thực hiện **SpringApplication.run -> callRunners** giống đường startup toàn ứng dụng. Cần end-to-end test thực sự chạy SpringApplication.



## 13. AbstractFailureAnalyzer là lựa chọn thay thế

Spring Boot có **AbstractFailureAnalyzer<T extends Throwable>**, một base class giúp tìm exception cụ thể trong chain trước khi gọi analyze(rootFailure, cause). Mẫu minh họa:

~~~java
final class AlternativeAnalyzer
        extends AbstractFailureAnalyzer<StartupPolicyException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, StartupPolicyException cause) {
        return new FailureAnalysis(
                "Invalid region: " + cause.getRejectedValue(),
                "Choose ap-southeast-1 or ap-northeast-1.",
                cause);
    }
}
~~~

Đây là **đoạn minh họa không phải tệp runnable độc lập**: cần imports, package, type StartupPolicyException và lựa chọn cách đăng ký. Dùng **một trong hai** analyzer cho cùng exception để tránh báo cáo không nhất quán.

Khi trực tiếp implements FailureAnalyzer như project chính, có trách nhiệm duyệt chain hoặc nhận diện wrapper. Khi extend AbstractFailureAnalyzer, có thể bỏ vòng while thủ công. Nếu không xử lý được, base class/implementation nên trả null để analyzer khác xử lý.

## 14. Phân biệt startup failure với runtime failure

| Vị trí lỗi | SpringApplication startup failure? | FailureAnalyzer dùng tự động? | Phương án bổ sung |
| --- | --- | --- | --- |
| Bean constructor trong refresh | Có | Có thể | Fix bean/config, cleanup cấp phát dở |
| @PostConstruct trong refresh | Có | Có thể | Fix init, timeout, resource |
| ApplicationRunner trước Ready | Có | Có, như lab | Custom type + FailureAnalyzer |
| CommandLineRunner trước Ready | Có | Có thể | Cùng cơ chế |
| ApplicationReadyEvent listener ném exception | Có thể ảnh hưởng run khi event synchronous | Phụ thuộc đường xử lý failure | Không đặt validation bắt buộc ở listener tùy tiện |
| HTTP controller sau Ready | Không mặc nhiên | Không phải đường startup | @ControllerAdvice, HTTP status |
| @Async task sau Ready | Không mặc nhiên | Không phải đường startup | Future/error handler/metrics |
| Scheduler sau Ready | Không mặc nhiên | Không phải đường startup | Scheduler ErrorHandler, retry |
| Kafka/RabbitMQ listener runtime | Không mặc nhiên | Không phải đường startup | Container error handler/ack/backoff |

**ApplicationFailedEvent không phải event cho mọi exception**. Nó thể hiện lỗi trong quá trình khởi động SpringApplication. Một lỗi xảy ra trong request sau Ready thường không làm cả JVM dừng, không tự phát ApplicationFailedEvent và không gọi custom FailureAnalyzer như startup.

## 15. Rủi ro vận hành và thiết kế đúng

### Runner fail-fast hay degraded mode?

Nếu chính sách bắt buộc để ứng dụng phục vụ an toàn, **fail-fast** đúng hơn việc ghi warning rồi phát Ready. Nhưng nếu một remote service tạm thời unavailable mà ứng dụng vẫn có khả năng phục vụ một phần, có thể dùng readiness degradation, health indicator, circuit breaker hoặc retry bounded thay vì chặn startup vô hạn.

### Không dùng runner cho tác vụ không idempotent một cách vô ý

Một Pod restart nhiều lần có thể chạy runner nhiều lần. Nếu runner gửi payment, publish message hoặc migration không an toàn, side effects có thể lặp dù FailureAnalyzer báo lỗi rõ. Cần checkpoint, leader election, idempotency, transaction và outbox theo use case.

### Cleanup tài nguyên khi lỗi

StartupFailure có thể khiến Spring Boot cố đóng ApplicationContext đã tạo. Nhưng không bảo đảm mọi file, socket hoặc remote resource được mở dở trong constructor/factory đã đóng hoàn toàn. Thiết kế try/finally và managed lifecycle rõ ràng. FailureAnalyzer chỉ báo nguyên nhân, **không hoàn tác side effects**.

### ExitCodeGenerator khác FailureAnalyzer

- **FailureAnalyzer:** người vận hành đọc Description và Action.
- **ExitCodeGenerator/ExitCodeExceptionMapper:** chọn exit status theo hợp đồng ứng dụng.
- **ApplicationFailedEvent:** quan sát sự kiện lỗi khởi động.
- **FailureAnalysisReporter:** trình bày FailureAnalysis.
- **ReadinessState:** cho biết ứng dụng có nhận traffic hay không; không phải exception reporter.

Có thể phối hợp các cơ chế nhưng không coi chúng thay thế nhau. Một analyzer không tự bảo đảm đúng exit code hoặc xử lý retry.

### Bảo mật của Description/Action

Thông báo phải có thể hành động nhưng không lộ secret. Trong lab, region moon-base không nhạy cảm. Với credential, report chỉ nêu key cấu hình/nguồn vault và cách nạp đúng, không in rejectedValue. Không gửi toàn bộ stack trace production có secrets lên log công khai.

## 16. Troubleshooting theo dấu hiệu

| Triệu chứng | Nghi ngờ | Cách kiểm tra |
| --- | --- | --- |
| Runner fail nhưng không thấy Action riêng | spring.factories sai path/key | src/main/resources/META-INF/spring.factories và packaged JAR |
| Analyzer unit test pass nhưng app chỉ in stack trace | Unit test không xác minh discovery | Chạy bootRun moon-base |
| Analyzer luôn trả null | Không tìm thấy custom type trong getCause | Kiểm tra wrapper, package, exception type |
| Class analyzer không load được | FQCN sai, không có public constructor hoặc missing dependency | Package/class name và runtime classpath |
| @Component nhưng không được gọi | Component scan không phải cách registration đáng tin | spring.factories |
| Chỉ EVENT_STARTED rồi failed | Lỗi trong runner trước Ready | Đọc RUNNER_VALIDATE và cause |
| Không có EVENT_FAILED | Không đăng ký listener đủ sớm hoặc lỗi trước event pipeline | app.addListeners trước app.run |
| Có RUNNER_AUDIT khi region sai | @Order/config không như dự kiến | @Order trên class, active profile, runner beans |
| moon-base không fail | Property khác override hoặc code chạy bản cũ | In value resolve từ Environment |
| JAR khác bootRun | Resource/class chưa packaged hoặc profile khác | jar tf, deployment args |
| Console nhiều stack trace | Gradle/JVM in exception ra stderr | Kiểm tra Description/Action thay vì yêu cầu không còn stack |
| Exit status 0 dù lỗi | Main bắt và nuốt exception hoặc wrapper thay status | Không catch-silent, kiểm tra OS process status |

### Conditions report không thay FailureAnalyzer

Spring Boot có thể bật debug conditions report:

~~~bash
./gradlew bootRun --args="--demo.startup.region=moon-base --debug"
~~~

Report này hữu ích cho auto-configuration, @Conditional, missing beans nhưng **không tự hiểu chính sách region allowlist**. FailureAnalyzer mới là nơi mô tả lỗi nghiệp vụ của bài.

### Có lỗi trong bean trước runners

Nếu @PostConstruct hoặc constructor ném exception, EVENT_STARTED thường chưa xuất hiện theo đường khởi động thành công. Không vội kết luận custom analyzer bị lỗi; có thể exception khác mà analyzer chính trả null đúng thiết kế.

## 17. Câu hỏi tự kiểm tra

**1. ApplicationRunner chạy trước hay sau ApplicationStartedEvent?** Sau Started, trước Ready.

**2. Runner đầu ném exception thì runner tiếp theo có chạy không?** Không trên đường startup bình thường khi exception không bị nuốt.

**3. ApplicationReadyEvent có phát khi runner bị lỗi không?** Không trên đường startup thành công.

**4. Vì sao cần đi qua getCause?** SpringApplication có thể bọc custom exception của runner.

**5. FailureAnalysis có ba thành phần nào?** Description, Action, Cause.

**6. Nếu analyzer không xử lý được exception thì trả gì?** null để analyzer khác có cơ hội.

**7. File đăng ký custom FailureAnalyzer ở đâu?** src/main/resources/META-INF/spring.factories.

**8. @Component trên class analyzer có thay thế được discovery không?** Không theo cách đăng ký Boot 3.3 hướng dẫn.

**9. Đăng ký trong AutoConfiguration.imports thay spring.factories có đúng không?** Không; hai cơ chế có mục đích khác nhau.

**10. Chỉ có unit test analyze() pass thì đã đủ chưa?** Chưa; cần integration test bootRun/java -jar xác minh discovery và reporter.

**11. FailureAnalyzer có tự đổi exit code không?** Không, exit code là cơ chế khác.

**12. ApplicationFailedEvent có phát cho mọi exception sau Ready không?** Không, nó thuộc đường startup.

**13. Nếu exception chứa password thì có nên in vào Description không?** Không; redact secrets.

**14. Dùng @PostConstruct thay runner có làm sự kiện Started xảy ra trước validation không?** Không; @PostConstruct thuộc giai đoạn init bean trước Started.

**15. Khi nào nên dùng AbstractFailureAnalyzer?** Khi muốn base class tìm exception type trong cause chain và giảm code duyệt lỗi.

**16. Vì sao không retry vô hạn trong runner?** Có thể làm startup treo, giữ Not Ready, tăng tải lên downstream và che nguyên nhân lỗi.

## 18. Checklist QA của bài lab

- [ ] Spring Boot 3.3.13, Java 17+, Gradle tương thích.
- [ ] Main @SpringBootApplication nằm ở package demo để scan subpackages.
- [ ] Có hai runners @Order(10) và @Order(20) thực sự được đăng ký.
- [ ] Exception riêng giữ tên key và rejected value không nhạy cảm.
- [ ] Main đăng ký ApplicationFailedEvent listener trước run.
- [ ] StartupEventLog nhận Started/Ready và in marker đúng vị trí.
- [ ] Analyzer implements FailureAnalyzer, duyệt getCause, trả FailureAnalysis hoặc null.
- [ ] Description nêu nguyên nhân và Action đưa ra cách sửa cụ thể.
- [ ] spring.factories đúng key, FQCN và đường dẫn resources.
- [ ] Unit tests chạy pass với wrapped exception và unrelated exception.
- [ ] Chạy default và ap-northeast-1 có EVENT_READY.
- [ ] Chạy moon-base có EVENT_FAILED, custom report và không có EVENT_READY.
- [ ] Không có RUNNER_AUDIT khi validation fail.
- [ ] Packaged JAR có META-INF/spring.factories ở BOOT-INF/classes.
- [ ] Không giả định stack trace/logs phải giống từng ký tự.
- [ ] Không nuốt exception rồi cho ứng dụng Ready sai.
- [ ] Không in secrets và không tạo side effects không idempotent.
- [ ] Phân biệt startup diagnostics, runtime error handling, readiness và exit status.

## 19. Kết luận

Trong Spring Boot, **runner có thể thất bại sau khi context refresh và ApplicationStartedEvent đã phát, nhưng trước ApplicationReadyEvent**. Để biến lỗi nghiệp vụ từ runner thành thông điệp có thể hành động, hãy ném **exception riêng**, tạo **FailureAnalyzer** trả **FailureAnalysis(description, action, cause)**, xử lý **chuỗi cause** vì framework có thể bọc exception, và **đăng ký tại META-INF/spring.factories**.

Một bài thực hành đúng cần chứng minh cả nhánh thành công, nhánh lỗi, thứ tự runner, startup events, logic analyzer và quá trình **discovery + reporting** thực tế. FailureAnalyzer **chỉ chẩn đoán startup**; không tự sửa lỗi, thay thế transaction, retry, exit code, readiness hay error handling của request/runtime.

### Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication và Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot 3.3.13 API — ApplicationRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3.13 API — FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html)
- [Spring Boot 3.3.13 API — FailureAnalysis](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html)
