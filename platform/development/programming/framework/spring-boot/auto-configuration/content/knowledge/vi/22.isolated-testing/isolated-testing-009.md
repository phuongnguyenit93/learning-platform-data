# Kiểm tra startup failure và nguyên nhân gốc khi cấu hình không hợp lệ

## 1. Mục tiêu: tìm nguyên nhân khiến Spring Boot không khởi động

Một ứng dụng Spring Boot có thể dừng trước khi nhận request vì cấu hình sai, dependency thiếu, bean không tạo được, điều kiện auto-configuration không khớp với dependency graph hoặc embedded server không khởi động. Log thường hiển thị nhiều lớp exception lồng nhau. Exception ngoài cùng cho biết **giai đoạn nào thất bại**, còn cause bên trong thường chỉ ra **điều gì đã kích hoạt lỗi**.

Ví dụ:

- `ConfigurationPropertiesBindException` có thể bao ngoài lỗi bind hoặc validation của property.
- `UnsatisfiedDependencyException` thường chỉ ra bean nào không thể được inject; nguyên nhân sâu hơn có thể là `NoSuchBeanDefinitionException` hoặc bean dependency tạo lỗi.
- `BeanCreationException` thường bao quanh exception phát sinh từ constructor, factory method, `@PostConstruct` hoặc khởi tạo bean.
- `ApplicationContextException` có thể bao quanh lỗi khởi động web server.
- `NoSuchMethodError` hoặc `NoClassDefFoundError` thường hướng đến classpath/version không tương thích.
- `PortInUseException` hoặc lỗi bind socket có thể chỉ ra port đã bị process khác chiếm.

Mục tiêu của bài:

1. Phân biệt các giai đoạn startup và nhóm lỗi tương ứng.
2. Đọc exception chain, xác định root cause và giữ lại ngữ cảnh của exception bao ngoài.
3. Dùng log startup, `--debug` và `ConditionEvaluationReport` đúng mục đích.
4. Kiểm tra cấu hình bằng `@ConfigurationProperties`, validation và `ApplicationContextRunner`.
5. Tạo `FailureAnalyzer` để chuyển một lỗi đặc thù thành thông báo có mô tả và hành động sửa cụ thể.
6. Xây dựng test chứng minh context khởi động thành công hoặc thất bại vì đúng nguyên nhân dự kiến.

Ví dụ dùng **Java 17+ và Spring Boot 3.3.13**.

## 2. Startup diễn ra qua những giai đoạn nào?

Không phải mọi lỗi xuất hiện trong lúc chạy `SpringApplication.run` đều có cùng nguyên nhân. Xác định giai đoạn giúp chọn đúng công cụ:

| Giai đoạn | Việc Spring Boot thực hiện | Lỗi thường gặp |
|---|---|---|
| Đọc cấu hình ban đầu | Đọc config data, profile, import, environment và command-line | YAML sai cú pháp, file config bắt buộc không tồn tại, placeholder không resolve |
| Chuẩn bị `Environment` | Nạp và hợp nhất property sources | Sai tên key, giá trị bị profile hoặc biến môi trường ghi đè |
| Nạp configuration và auto-configuration | Đọc configuration classes, đánh giá conditions, đăng ký bean definitions | Classpath condition không khớp, auto-configuration bị exclude, bean điều kiện không được đăng ký |
| Refresh `ApplicationContext` | Tạo singleton, inject dependency, bind `@ConfigurationProperties`, chạy lifecycle callbacks | Binding/validation thất bại, thiếu bean, circular dependency, constructor hoặc factory method ném exception |
| Khởi động web server | Tạo và khởi động embedded server | Port đang được dùng, TLS/certificate sai, connector không bind được |
| Chạy application/command-line runners | Gọi `ApplicationRunner` và `CommandLineRunner` | Startup task, migration hoặc kiểm tra cấu hình ném exception |
| Hoàn tất startup | Phát sự kiện ready và chuyển trạng thái readiness | Một lỗi xảy ra trước khi runner hoàn tất có thể khiến ứng dụng chưa sẵn sàng |

Một số lỗi xảy ra **trước khi `ApplicationContext` tồn tại**, ví dụ config data không đọc được. Khi đó không thể mong đợi một bean trong context xử lý lỗi ấy.

Một số lỗi xảy ra khi context refresh, ví dụ bean dependency thiếu. Lỗi có thể bị bao trong nhiều lớp exception.

Một số lỗi xảy ra sau khi context đã refresh nhưng trước khi `SpringApplication.run` hoàn tất, chẳng hạn `ApplicationRunner` ném exception. Vì vậy log có thể cho thấy context đã khởi tạo nhưng ứng dụng vẫn báo startup failure.

## 3. Phân biệt exception bên ngoài và nguyên nhân gốc

### 3.1. Đọc từ ngoài vào trong

Ví dụ một bean không tạo được:

~~~text
BeanCreationException: Error creating bean with name 'workerPool'
    at ...
Caused by: InvalidPoolConfigurationException:
    app.pool.threads=128 exceeds supported maximum 64
    at ...
~~~

Đọc theo hai lớp:

- `BeanCreationException` cho biết bean `workerPool` thất bại trong quá trình tạo.
- `InvalidPoolConfigurationException` chỉ ra điều kiện cấu hình cụ thể khiến factory method dừng lại.

Nếu chỉ sửa `BeanCreationException` mà không tìm cause bên trong, ta chưa biết cần đổi property, dependency hay code tạo bean.

Một ví dụ khác:

~~~text
UnsatisfiedDependencyException:
    Error creating bean with name 'auditStartupCheck'
Caused by: NoSuchBeanDefinitionException:
    No qualifying bean of type 'AuditClient' available
~~~

Ở đây, bean `auditStartupCheck` yêu cầu `AuditClient`, nhưng context không có bean phù hợp. Có thể một `@ConditionalOnProperty` đã không khớp nên `AuditClient` không được đăng ký. Exception sâu nhất chỉ cho biết bean thiếu; cần xem condition report và property hiệu lực để tìm lý do.

### 3.2. Root cause không thay thế ngữ cảnh

Khi điều tra, ghi lại cả:

- Exception ngoài cùng và bean/resource đang được xử lý.
- Cause chain, đặc biệt exception sâu nhất có ý nghĩa.
- Message, property key, bean name, profile và class liên quan.
- Stack frame đầu tiên thuộc code ứng dụng hoặc thư viện đang dùng.
- Các suppressed exceptions nếu có; một số lỗi tổng hợp có nhiều nguyên nhân phụ.

Không phải lúc nào dòng cuối cùng của stack trace cũng là lời giải đầy đủ. Root cause có thể là lỗi hệ điều hành hoặc thư viện nền, trong khi wrapper bên ngoài cho biết request, bean hoặc cấu hình nào đã kích hoạt nó.

### 3.3. Bảng nhận diện nhanh

| Exception thường gặp | Điều nó gợi ý | Việc cần kiểm tra tiếp |
|---|---|---|
| `ConfigDataLocationNotFoundException` | Config location/import bắt buộc không tồn tại | Đường dẫn, tên file, `optional:` và môi trường deploy |
| `ConfigurationPropertiesBindException` | Không bind được một properties bean | Property prefix, kiểu dữ liệu, conversion và validation |
| `BindValidationException` | Giá trị đã bind nhưng không vượt qua validation | Constraint, giá trị thực tế và nguồn property |
| `UnsatisfiedDependencyException` | Không inject được dependency cho bean | Bean nào đang cần dependency, condition và bean definition |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp trong context | Component scan, auto-configuration, condition, profile và qualifier |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp nhưng không chọn được | `@Primary`, `@Qualifier` và thiết kế bean |
| `BeanCreationException` | Bean thất bại khi tạo/khởi tạo | Đọc cause, constructor, factory method và lifecycle callback |
| `BeanCurrentlyInCreationException` | Có thể có circular dependency | Dependency graph và thiết kế vòng phụ thuộc |
| `NoClassDefFoundError` | Class cần thiết không thể được nạp lúc runtime | Runtime classpath, scope, packaging và classloader |
| `NoSuchMethodError` | Class được nạp không có method mà bytecode đang gọi | Dependency version conflict và dependency tree |
| `PortInUseException` / bind exception | Server không bind được địa chỉ/port | Process đang giữ port, `server.port`, `server.address` và container mapping |
| Exception từ `ApplicationRunner` | Context có thể đã refresh nhưng startup chưa hoàn tất | Startup task, dữ liệu đầu vào và dependency mà runner gọi |

Bảng chỉ định hướng. Hãy xác nhận bằng cause chain và trạng thái runtime trước khi thay đổi cấu hình.

## 4. Đọc log và condition report đúng cách

### 4.1. Chạy với `--debug`

Với executable JAR:

~~~bash
java -jar app.jar --debug
~~~

Với Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Với Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

`--debug` bật một tập logger chẩn đoán được Spring Boot lựa chọn, trong đó có thông tin condition evaluation. Nó **không** có nghĩa toàn bộ logger của ứng dụng và mọi thư viện đều chuyển sang DEBUG.

Có thể cấu hình logger cụ thể trong `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.context.annotation: DEBUG
~~~

Chỉ bật logger sâu trong thời gian điều tra nếu log volume lớn. Khi dùng môi trường production, cần tránh ghi secret, token, password hoặc dữ liệu cá nhân vào log.

### 4.2. `ConditionEvaluationReport` dùng để làm gì?

`ConditionEvaluationReport` lưu kết quả match/no-match của các condition liên quan đến auto-configuration. Report giúp trả lời:

- Auto-configuration nào được áp dụng?
- Auto-configuration nào bị bỏ qua?
- Condition nào không khớp?
- Lý do là classpath, property, bean hay application type?

Ví dụ: `AuditAutoConfiguration#auditClient` không match vì `app.audit.enabled` không bằng `true`. Đây là bằng chứng về **quyết định đăng ký bean**, không phải root cause chung cho mọi startup failure.

Nếu không có `FailureAnalyzer` nào xử lý exception, Spring Boot có thể in condition report khi bật `--debug` hoặc logger `ConditionEvaluationReportLoggingListener` ở mức DEBUG.

### 4.3. Khi nào condition report không đủ?

Condition report không thay thế:

- Cause chain của `BeanCreationException`.
- Lỗi parse YAML hoặc load config data.
- Chi tiết validation trong `BindValidationException`.
- Lỗi classloader hoặc linkage như `NoSuchMethodError`.
- Lỗi bind port của embedded server.
- Exception ném ra từ `ApplicationRunner`.

Dùng report để hiểu **vì sao một nhánh cấu hình được hoặc không được đăng ký**. Dùng stack trace, property source và log của thành phần liên quan để xác định **vì sao thao tác cụ thể thất bại**.

Nếu ứng dụng có Actuator, endpoint `conditions` cũng có thể cung cấp condition report dạng JSON khi được expose. Endpoint này cần được bảo vệ vì nó có thể tiết lộ classpath và cấu trúc cấu hình nội bộ; không mở public chỉ để debug.

## 5. Kiểm tra giá trị cấu hình thực tế

### 5.1. Đừng chỉ đọc `application.yml`

Property có thể đến từ nhiều nguồn: default properties, file trong JAR, file ngoài JAR, profile-specific config, config import, environment variables, system properties và command-line arguments. Các nguồn có thứ tự ưu tiên khác nhau; nguồn có ưu tiên cao hơn có thể ghi đè giá trị trong YAML.

Ví dụ file:

~~~yaml
app:
  pool:
    threads: 8
~~~

Nhưng môi trường triển khai đặt:

~~~bash
APP_POOL_THREADS=0
~~~

Ứng dụng có thể nhận giá trị `0` thay vì `8`. Khi chẩn đoán, cần ghi **effective value** và nguồn cung cấp, không chỉ ghi nội dung file.

Có thể kiểm tra trong debugger hoặc log có kiểm soát:

~~~java
String threads = environment.getProperty("app.pool.threads");
String activeProfiles = String.join(",", environment.getActiveProfiles());
~~~

Không in toàn bộ `Environment` ra log vì có thể chứa bí mật. Chỉ log key liên quan, giá trị đã mask nếu cần và nguồn property phù hợp.

### 5.2. Dùng `@ConfigurationProperties` và validation

Với cấu hình nhiều key, dùng properties class có kiểu dữ liệu rõ ràng và constraint:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.pool")
@Validated
public class PoolProperties {

    @Min(1)
    private int threads = 8;

    public int getThreads() {
        return threads;
    }

    public void setThreads(int threads) {
        this.threads = threads;
    }
}
~~~

`@Min(1)` yêu cầu số thread tối thiểu là 1. Nếu property được bind thành `0`, validation sẽ làm context khởi động thất bại. Để các constraint Jakarta Validation hoạt động, cần có implementation validation trên classpath, thường qua `spring-boot-starter-validation`.

Đăng ký properties và dùng trong bean:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PoolProperties.class)
public class PoolConfiguration {

    @Bean
    WorkerPool workerPool(PoolProperties properties) {
        return new WorkerPool(properties.getThreads());
    }
}
~~~

Ví dụ trên dùng `WorkerPool` là class ứng dụng có constructor nhận số thread. Nếu `app.pool.threads` sai kiểu, binder có thể báo lỗi conversion/binding. Nếu giá trị chuyển đổi được nhưng vi phạm constraint, lỗi validation sẽ xuất hiện trong cause chain.

### 5.3. Phân biệt property sai với condition không khớp

Giả sử bean chỉ được đăng ký khi:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "app.audit",
    name = "enabled",
    havingValue = "true"
)
AuditClient auditClient() {
    return new AuditClient();
}
~~~

Nếu `app.audit.enabled` thiếu hoặc không bằng `true`, `AuditClient` không được đăng ký. Bản thân condition không khớp **không nhất thiết là startup failure**. Context vẫn có thể khởi động bình thường nếu không bean nào bắt buộc `AuditClient`.

Nếu một bean khác bắt buộc inject `AuditClient`, context có thể thất bại với `UnsatisfiedDependencyException` và `NoSuchBeanDefinitionException`. Khi đó cần kiểm tra property condition, giá trị hiệu lực, `matchIfMissing`, active profile và bean phụ thuộc.

## 6. `FailureAnalyzer`: biến exception thành hướng dẫn sửa lỗi

### 6.1. Ba thành phần

Spring Boot cung cấp cơ chế phân tích lỗi startup:

- `FailureAnalyzer` nhận exception và trả về một `FailureAnalysis`, hoặc `null` nếu không thể xử lý.
- `FailureAnalysis` chứa `description`, `action` và `cause`.
- `FailureAnalysisReporter` hiển thị kết quả cho người dùng. Reporter mặc định ghi phân tích ra log/console.

Một lỗi port đã bị chiếm có thể được trình bày theo cấu trúc:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Embedded servlet container failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that is listening on port 8080
or configure this application to listen on another port.
~~~

Thông báo này dễ hành động hơn một stack trace dài. Nó không làm ứng dụng tự sửa cấu hình; nó giải thích lỗi và gợi ý thao tác tiếp theo.

### 6.2. Khi nào nên viết analyzer riêng?

Viết `FailureAnalyzer` khi thư viện/ứng dụng có một exception đặc thù mà developer thường gặp và có thể đưa ra hướng sửa rõ ràng. Ví dụ:

- Một giới hạn cấu hình của pool bị vượt.
- Hai tùy chọn cấu hình loại trừ nhau.
- Một file bắt buộc có tồn tại nhưng sai định dạng riêng của ứng dụng.
- Một integration yêu cầu credential hoặc endpoint mà ứng dụng chưa cung cấp.

Không viết analyzer chỉ để đổi tên một exception chung chung. Nếu không có thông tin hành động cụ thể hơn, stack trace và analyzer có sẵn của Spring Boot có thể đã đủ.

### 6.3. Ví dụ custom exception

Tệp `src/main/java/com/example/config/InvalidPoolConfigurationException.java`:

~~~java
package com.example.config;

public class InvalidPoolConfigurationException extends RuntimeException {

    private final int requestedThreads;

    public InvalidPoolConfigurationException(int requestedThreads) {
        super("app.pool.threads=" + requestedThreads
                + " exceeds the supported maximum of 64");
        this.requestedThreads = requestedThreads;
    }

    public int getRequestedThreads() {
        return requestedThreads;
    }
}
~~~

Factory method có thể ném exception này khi cấu hình vượt giới hạn vận hành:

~~~java
@Bean
WorkerPool workerPool(PoolProperties properties) {
    int threads = properties.getThreads();

    if (threads > 64) {
        throw new InvalidPoolConfigurationException(threads);
    }

    return new WorkerPool(threads);
}
~~~

Đây là lỗi cấu hình có ngữ nghĩa riêng của ứng dụng. Spring sẽ bao exception trong lỗi tạo bean, nhưng analyzer có thể tìm thấy exception đặc thù trong cause chain.

### 6.4. Viết `FailureAnalyzer`

Tệp `src/main/java/com/example/config/InvalidPoolConfigurationFailureAnalyzer.java`:

~~~java
package com.example.config;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public class InvalidPoolConfigurationFailureAnalyzer
        extends AbstractFailureAnalyzer<InvalidPoolConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            InvalidPoolConfigurationException cause) {

        String description = "The worker pool configuration requests "
                + cause.getRequestedThreads()
                + " threads, but this application supports at most 64.";

        String action = "Set app.pool.threads to a value between 1 and 64, "
                + "then restart the application.";

        return new FailureAnalysis(description, action, cause);
    }
}
~~~

`AbstractFailureAnalyzer<T>` tìm exception có kiểu `T` trong cause chain rồi gọi method `analyze(rootFailure, cause)`. Nếu analyzer không thể xử lý một exception, implementation có thể trả `null` để analyzer khác có cơ hội xử lý.

Không nên truy cập bean ứng dụng đang khởi tạo trong analyzer. Nếu cần `Environment` hoặc `BeanFactory`, hãy dùng cơ chế constructor argument mà Spring Boot hỗ trợ cho failure analyzers; tránh phụ thuộc vào bean nghiệp vụ chưa được tạo.

### 6.5. Đăng ký analyzer trong artifact

Tạo file:

`src/main/resources/META-INF/spring.factories`

Nội dung:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.config.InvalidPoolConfigurationFailureAnalyzer
~~~

Spring Boot 3.3 vẫn dùng `META-INF/spring.factories` cho SPI `FailureAnalyzer`. Đây là cơ chế đăng ký failure analyzer, **khác với** file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` dùng để đăng ký auto-configuration candidates.

Khi đóng gói ứng dụng/thư viện, kiểm tra JAR có cả class analyzer và resource `META-INF/spring.factories`. Nếu thiếu resource hoặc tên class sai, analyzer tùy chỉnh sẽ không được Spring Boot phát hiện.

### 6.6. Kiểm tra nội dung phân tích của analyzer

Có thể test analyzer trực tiếp bằng unit test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.BeanCreationException;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class InvalidPoolConfigurationFailureAnalyzerTests {

    @Test
    void explainsUnsupportedThreadCount() {
        InvalidPoolConfigurationException cause =
                new InvalidPoolConfigurationException(128);

        Throwable startupFailure =
                new BeanCreationException("workerPool", cause);

        FailureAnalysis analysis =
                new InvalidPoolConfigurationFailureAnalyzer()
                        .analyze(startupFailure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription()).contains("128");
        assertThat(analysis.getAction()).contains("1 and 64");
        assertThat(analysis.getCause()).isSameAs(cause);
    }
}
~~~

Test này xác nhận analyzer nhận ra cause nằm bên trong `BeanCreationException` và tạo đúng description/action. Nó không kiểm tra việc SpringApplication tự nạp analyzer từ JAR. Muốn xác minh đăng ký end-to-end, chạy ứng dụng thật với `app.pool.threads=128` và kiểm tra phần `Description`/`Action` trong output startup failure.

## 7. Ví dụ kiểm thử độc lập với `ApplicationContextRunner`

`ApplicationContextRunner` tạo một context nhỏ, độc lập cho từng scenario. Nó hữu ích để kiểm tra cấu hình hợp lệ, binding/validation failure, bean creation failure và condition mismatch mà không phải chạy toàn bộ ứng dụng.

**Lưu ý:** `ApplicationContextRunner` không khởi động ứng dụng bằng `SpringApplication`, nên nó không chạy chuỗi `FailureAnalyzer`/`FailureAnalysisReporter` của startup. Nó giữ startup exception để test có thể kiểm tra. Test analyzer ở phần trước kiểm tra logic phân tích; integration test qua `SpringApplication` mới xác nhận reporter hiển thị kết quả.

### 7.1. Dependency test

Với Maven và Spring Boot 3.3.13:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
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
</dependencies>
~~~

Spring Boot parent/BOM quản lý version dependency. Đặt `java.version` là `17` trong project properties.

### 7.2. Test đầy đủ các failure scenario

Tệp `src/test/java/com/example/config/StartupFailureTests.java`:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class StartupFailureTests {

    private final ApplicationContextRunner poolRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PoolTestConfiguration.class);

    @Test
    void validConfigurationStartsSuccessfully() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=8")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WorkerPool.class);
                    assertThat(context.getBean(WorkerPool.class).threads())
                            .isEqualTo(8);
                });
    }

    @Test
    void validationFailureIdentifiesInvalidProperty() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    org.springframework.boot.context.properties
                                            .bind.validation.BindValidationException.class);
                });
    }

    @Test
    void applicationSpecificLimitHasItsOwnRootCause() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=128")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    InvalidPoolConfigurationException.class);
                });
    }

    @Test
    void unmatchedConditionCanCauseMissingDependency() {
        new ApplicationContextRunner()
                .withUserConfiguration(AuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    org.springframework.beans.factory
                                            .NoSuchBeanDefinitionException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PoolProperties.class)
    static class PoolTestConfiguration {

        @Bean
        WorkerPool workerPool(PoolProperties properties) {
            int threads = properties.getThreads();

            if (threads > 64) {
                throw new InvalidPoolConfigurationException(threads);
            }

            return new WorkerPool(threads);
        }
    }

    @ConfigurationProperties(prefix = "app.pool")
    @Validated
    public static class PoolProperties {

        @Min(1)
        private int threads = 8;

        public int getThreads() {
            return threads;
        }

        public void setThreads(int threads) {
            this.threads = threads;
        }
    }

    static class WorkerPool {
        private final int threads;

        WorkerPool(int threads) {
            this.threads = threads;
        }

        int threads() {
            return threads;
        }
    }

    static class AuditClient {
    }

    static class AuditStartupCheck {
        AuditStartupCheck(AuditClient client) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.audit",
                name = "enabled",
                havingValue = "true"
        )
        AuditClient auditClient() {
            return new AuditClient();
        }

        @Bean
        AuditStartupCheck auditStartupCheck(AuditClient client) {
            return new AuditStartupCheck(client);
        }
    }
}
~~~

Bốn scenario xác nhận bốn kết quả khác nhau:

| Test | Đầu vào | Kết quả mong đợi |
|---|---|---|
| `validConfigurationStartsSuccessfully` | `app.pool.threads=8` | Context chạy, có `WorkerPool` |
| `validationFailureIdentifiesInvalidProperty` | `app.pool.threads=0` | Context thất bại, root cause là `BindValidationException` |
| `applicationSpecificLimitHasItsOwnRootCause` | `app.pool.threads=128` | Context thất bại, root cause là `InvalidPoolConfigurationException` |
| `unmatchedConditionCanCauseMissingDependency` | Không bật `app.audit.enabled` | `AuditClient` không được đăng ký; bean phụ thuộc bắt buộc làm context thất bại |

Test cuối minh họa một điểm quan trọng: condition không khớp tự nó không nhất thiết là lỗi. Startup failure xảy ra vì một bean khác vẫn bắt buộc inject bean đã bị condition loại bỏ. Nếu bean tiêu thụ cũng phải tùy chọn, nó nên dùng condition phù hợp hoặc `ObjectProvider` thay vì yêu cầu dependency bắt buộc.

### 7.3. Chạy test

Maven:

~~~bash
./mvnw -Dtest=StartupFailureTests,InvalidPoolConfigurationFailureAnalyzerTests test
~~~

Gradle:

~~~bash
./gradlew test --tests com.example.config.StartupFailureTests
./gradlew test --tests com.example.config.InvalidPoolConfigurationFailureAnalyzerTests
~~~

Kết quả mong đợi: các test PASS. `ApplicationContextRunner` kiểm tra context failure và root cause; unit test riêng kiểm tra nội dung `FailureAnalysis`.

## 8. Điều tra lỗi cấu hình theo một trình tự cố định

### Bước 1: xác định thời điểm thất bại

Đọc các log cuối cùng trước `APPLICATION FAILED TO START`. Xác định lỗi xảy ra khi đọc config, tạo bean, khởi động server hay chạy runner. Nếu có log context đã refresh nhưng chưa có readiness, kiểm tra runner và lifecycle event.

### Bước 2: ghi exception ngoài cùng

Ghi tên exception, message và bean/property đang được xử lý. Ví dụ `Error creating bean with name 'dataSource'` cho biết bean cần kiểm tra đầu tiên.

### Bước 3: lần theo cause chain

Tìm `Caused by` liên quan. Ghi root cause có ý nghĩa và stack frame đầu tiên thuộc code ứng dụng/thư viện. Nếu có suppressed exception, đọc riêng các nhánh đó.

### Bước 4: kiểm tra effective configuration

Ghi key, giá trị runtime, nguồn property, active profile và config import. So sánh với default và constraint của `@ConfigurationProperties`. Tránh đưa secret vào báo cáo.

### Bước 5: kiểm tra conditions và bean graph

Nếu bean không xuất hiện, bật `--debug`, đọc positive/negative matches, exclusions và bean method. Xác định `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean` có khớp không. Kiểm tra qualifier, primary candidate và dependency của bean tiêu thụ.

### Bước 6: kiểm tra runtime dependencies

Nếu cause là `NoClassDefFoundError` hoặc `NoSuchMethodError`, xem runtime dependency tree, version conflict, classloader và artifact đã đóng gói. Build thành công không chứng minh runtime classpath giống môi trường chạy.

### Bước 7: tái hiện bằng test nhỏ

Dùng `ApplicationContextRunner` với đúng property, user configuration và classpath. Thay đổi từng đầu vào để xác nhận giả thuyết. Nếu lỗi chỉ xuất hiện trong config data loading hoặc web server, cần integration test dùng `SpringApplication` hoặc `RANDOM_PORT` phù hợp.

### Bước 8: sửa nguyên nhân, giữ thông tin lỗi

Sửa property, dependency, condition hoặc bean design gây lỗi. Không bắt exception rồi chỉ log một message chung, trả về `null`, hoặc bỏ qua validation để ứng dụng khởi động trong trạng thái không hợp lệ.

### Bước 9: xác nhận lại đường khởi động

Chạy test liên quan, sau đó khởi động ứng dụng với cùng profile và cấu hình triển khai. Xác nhận log `Started ...`, runner hoàn tất, server mở đúng port và readiness được chuyển sang trạng thái nhận traffic.

## 9. Các nhóm lỗi cấu hình thường gặp

### 9.1. YAML hoặc Config Data sai

Triệu chứng: lỗi parse YAML, file import bắt buộc không tồn tại hoặc profile không được kích hoạt.

Kiểm tra:

- Thụt lề và kiểu dữ liệu YAML.
- `spring.config.import`, `spring.config.location` và đường dẫn tương đối.
- Tên profile thực tế và file `application-{profile}.yml`.
- File có được đóng gói hoặc mount vào container không.
- Nếu resource thực sự tùy chọn, xem xét prefix `optional:` thay vì tắt toàn bộ kiểm tra config.

### 9.2. Binding và validation

Triệu chứng: `ConfigurationPropertiesBindException`, `BindException` hoặc `BindValidationException`.

Kiểm tra:

- Prefix và canonical property name.
- Kiểu dữ liệu có chuyển đổi được không.
- Giá trị thực tế có vượt constraint `@Min`, `@NotNull`, `@NotBlank` không.
- Bean properties đã được đăng ký bằng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` chưa.
- Validation implementation có trên classpath không.
- Property source nào đã ghi đè giá trị mong đợi.

### 9.3. Condition không khớp

Triệu chứng: một bean mặc định không xuất hiện hoặc dependency bị thiếu.

Kiểm tra:

- Class có thật trên runtime classpath không.
- Property condition có `havingValue` và `matchIfMissing` đúng không.
- User bean có khiến `@ConditionalOnMissingBean` back off không.
- Auto-configuration có bị exclude không.
- Bean condition có được đánh giá sau bean definition mà nó phụ thuộc không.
- Có nhiều bean cùng type, qualifier sai hoặc thiếu `@Primary` không.

### 9.4. Bean creation và dependency graph

Triệu chứng: `BeanCreationException`, `UnsatisfiedDependencyException`, circular dependency.

Kiểm tra:

- Constructor/factory method có ném exception không.
- `@PostConstruct`, `InitializingBean` hoặc init method có lỗi không.
- Dependency có được tạo đúng thứ tự không.
- Có circular dependency giữa service/repository/configuration không.
- Bean có cần thiết phải khởi tạo sớm hay có thể thiết kế dependency ít liên kết hơn.
- Lazy initialization có đang trì hoãn lỗi đến lần dùng đầu tiên không.

### 9.5. Classpath và version conflict

Triệu chứng: `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, `LinkageError`.

Kiểm tra:

~~~bash
./mvnw dependency:tree
~~~

Hoặc:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

So sánh version thực tế của Spring Boot, Spring Framework, driver và SDK bên thứ ba. Dùng dependency management/BOM tương thích; không ép một module Spring Framework version riêng mà không xét toàn bộ graph.

### 9.6. Embedded server và port

Triệu chứng: server factory khởi tạo nhưng connector không bind được.

Kiểm tra:

- Port đang được process khác sử dụng không.
- `server.port`, `server.address`, container port mapping và network policy.
- TLS keystore/certificate, password, protocol và certificate chain.
- Server-specific property có đúng implementation Tomcat/Jetty/Undertow không.

### 9.7. Runner và startup task

Triệu chứng: context đã refresh nhưng `SpringApplication.run` vẫn ném exception.

Kiểm tra:

- `ApplicationRunner`/`CommandLineRunner` nào đang chạy.
- Migration, seed data, cache warm-up hoặc kết nối downstream nào thất bại.
- Task có idempotent và có timeout hợp lý không.
- Có đang thực hiện công việc dài trong callback lifecycle không phù hợp không.

## 10. Các lỗi thường gặp khi xử lý startup failure

- **Chỉ đọc exception ngoài cùng:** wrapper thường không nói rõ nguyên nhân; cần đọc cause chain.
- **Chỉ lấy root cause rồi bỏ wrapper:** mất thông tin bean, property hoặc giai đoạn đang thất bại; cần giữ cả hai.
- **Nhầm condition mismatch với lỗi condition:** condition không khớp có thể là hành vi dự kiến; chỉ trở thành lỗi khi dependency bắt buộc không được cung cấp.
- **Dùng `--debug` và nghĩ mọi thứ đã được log:** debug mode chỉ bật một tập logger chọn lọc; cần bật logger cụ thể khi có lý do.
- **Dùng condition report để tìm lỗi binding:** report giải thích auto-configuration conditions, không thay stack trace và validation errors.
- **Chỉ kiểm tra YAML:** environment variable, system property, profile và command line có thể ghi đè giá trị.
- **Tắt validation để ứng dụng khởi động:** lỗi cấu hình có thể chuyển thành lỗi runtime nguy hiểm hơn; sửa giá trị hoặc constraint.
- **Thêm `@Lazy` để che startup failure:** lazy initialization có thể trì hoãn phát hiện lỗi đến lần sử dụng đầu tiên.
- **Bắt `Exception` rồi bỏ qua:** context có thể khởi động nhưng bean ở trạng thái không hợp lệ.
- **Dùng `@Primary` để sửa mọi `NoSuchBeanDefinitionException`:** `@Primary` giải quyết nhiều candidate, không tạo bean còn thiếu.
- **Dùng `@Import` hoặc component scan rộng để che condition sai:** cần xác định vì sao auto-configuration không được đăng ký và sửa đúng điều kiện.
- **Viết analyzer bắt quá rộng:** một analyzer cho `RuntimeException` có thể che mất analyzer chuyên biệt; dùng exception type riêng và trả `null` khi không xử lý được.
- **Đăng ký analyzer bằng `AutoConfiguration.imports`:** analyzer dùng SPI `META-INF/spring.factories`; imports dành cho auto-configuration.
- **Test analyzer bằng `ApplicationContextRunner` rồi cho rằng đã kiểm tra reporter:** runner không dùng `SpringApplication` failure handling; cần unit test analyzer và integration startup riêng.
- **Chỉ test context thành công:** cần test cả invalid values, missing beans, condition mismatch và root cause dự kiến.
- **Không xác nhận lại bằng profile triển khai:** một test với property tĩnh không chứng minh môi trường production đang nạp cùng config.

## 11. Checklist điều tra có thể dùng trong incident

| Câu hỏi | Bằng chứng cần ghi |
|---|---|
| Startup dừng ở giai đoạn nào? | Log cuối cùng, event hoặc bean đang tạo |
| Exception ngoài cùng là gì? | Class và message |
| Root cause có ý nghĩa là gì? | Cause chain và stack frame liên quan |
| Property hiệu lực là gì? | Key, value đã mask, property source, profile |
| Condition nào không khớp? | Positive/negative match và message |
| Bean nào thiếu hoặc tạo lỗi? | Bean name, type, dependency và factory method |
| Runtime dependency có đúng không? | Maven/Gradle dependency tree và artifact version |
| Lỗi có tái hiện độc lập không? | ApplicationContextRunner hoặc integration test |
| Có cần FailureAnalyzer riêng không? | Exception đặc thù, description và action |
| Sau khi sửa, điều gì chứng minh đã ổn? | Test PASS, startup log, runner completion, readiness |

## 12. Câu hỏi tự kiểm tra

1. `BeanCreationException` luôn là root cause không? **Không.** Nó thường là wrapper cho lỗi constructor, factory method, binding hoặc lifecycle.
2. `@ConditionalOnProperty` không khớp có luôn làm ứng dụng fail không? **Không.** Chỉ khi một dependency bắt buộc không được cung cấp hoặc có logic khác yêu cầu bean đó.
3. `BindValidationException` gợi ý điều gì? **Giá trị đã bind nhưng vi phạm constraint validation** của configuration properties.
4. Vì sao phải ghi property source? **Để xác định giá trị runtime thật**, không chỉ giá trị trong YAML.
5. `--debug` có bật toàn bộ log DEBUG không? **Không.** Nó bật một tập logger chẩn đoán được lựa chọn và condition report.
6. `ConditionEvaluationReport` có thay thế stack trace không? **Không.** Nó giải thích điều kiện auto-configuration, không thay cause chain của lỗi bean/binding.
7. `FailureAnalysis` có những phần chính nào? **Description, Action và Cause.**
8. Custom `FailureAnalyzer` được đăng ký bằng file nào trong Spring Boot 3.3? **`META-INF/spring.factories`**, với key `org.springframework.boot.diagnostics.FailureAnalyzer`.
9. `ApplicationContextRunner` có chạy `FailureAnalysisReporter` như `SpringApplication` không? **Không.** Runner lưu startup failure để test; reporter thuộc startup failure handling của SpringApplication.
10. Test nào xác nhận validation của property? **Đặt giá trị vi phạm constraint và assert context failed với root cause `BindValidationException`.**
11. Khi nào `NoSuchBeanDefinitionException` có thể đến từ condition? **Khi condition loại bean nhưng bean khác vẫn yêu cầu inject bean đó.**
12. Vì sao không nên bật lazy initialization để che startup failure? **Lỗi có thể chỉ xuất hiện khi bean được dùng lần đầu, làm sự cố chuyển sang runtime.**
13. `NoSuchMethodError` thường cần kiểm tra gì? **Dependency version conflict và class được nạp thực tế.**
14. Nếu context refresh thành công nhưng runner ném exception, ứng dụng có thể báo startup failure không? **Có.** Runners được gọi trước khi `SpringApplication.run` hoàn tất và trước khi ứng dụng chuyển sang readiness.

## 13. Tài liệu tham khảo chính thức (Spring Boot 3.3.13)

- [SpringApplication — Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): failure analysis, `--debug`, startup lifecycle và application events.
- [Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html): cách viết và đăng ký `FailureAnalyzer` trong `META-INF/spring.factories`.
- [FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html): hợp đồng phân tích exception và trả `FailureAnalysis`.
- [AbstractFailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html): tìm cause theo kiểu exception và xây dựng analyzer chuyên biệt.
- [FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): description, action và cause.
- [FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html): báo cáo kết quả phân tích.
- [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): property source precedence, config data, profiles, binding và validation.
- [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test context và startup behavior.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context nhỏ để kiểm tra condition và startup failure.
