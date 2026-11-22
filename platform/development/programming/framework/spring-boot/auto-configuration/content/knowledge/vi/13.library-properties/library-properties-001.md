# Thiết kế namespace riêng cho @ConfigurationProperties của thư viện

## 1. Vì sao thư viện phải có namespace cấu hình riêng?

Khi nhiều thư viện được dùng trong cùng một Spring Boot application, tất cả đều đọc cấu hình qua **Spring Environment**. Nếu thư viện A và B cùng đặt key `timeout`, `client.url` hoặc `enabled`, ứng dụng rất khó biết giá trị nào dành cho thành phần nào. Một thay đổi môi trường có thể vô tình ảnh hưởng thư viện khác.

Giải pháp là thiết kế **một prefix ổn định, thuộc quyền sở hữu của thư viện**, rồi đặt các tùy chọn của thư viện bên dưới prefix đó. Ví dụ, với thư viện báo cáo giả định của tổ chức Acme:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 50
    timeout: 5s
~~~

Ba key đầy đủ là `acme.reports.enabled`, `acme.reports.batch-size` và `acme.reports.timeout`. Annotation trong mã Java sẽ dùng đúng root:

~~~java
@ConfigurationProperties(prefix = "acme.reports")
~~~

**Namespace ở đây là namespace của property keys**, không phải package Java, tên class, tên Spring bean hoặc tên Maven artifact. Package `com.example.lib` có thể đổi khi refactor mà namespace public `acme.reports` vẫn giữ nguyên.

Mục tiêu của prefix riêng:

- **Tránh va chạm** với cấu hình của Spring Boot, ứng dụng hoặc thư viện khác.
- **Dễ khám phá**: người vận hành biết key thuộc hệ thống con nào.
- **Dễ mở rộng**: thêm `acme.reports.retry.*` hoặc `acme.reports.http.*` mà không làm rối các key khác.
- **Dễ kiểm thử và nâng cấp**: typed properties, validation, tài liệu và metadata đều có cùng phạm vi sở hữu.

Prefix không tự làm dữ liệu trở nên riêng tư hay bảo mật: giá trị vẫn được lấy từ các property sources của Spring Environment theo thứ tự ưu tiên cấu hình.

## 2. Quy tắc thiết kế prefix

Mẫu gợi ý cho một thư viện tái sử dụng:

~~~text
<vendor-or-product>.<module-or-feature>[.<subgroup>].<property>
~~~

Ví dụ:

| Key hoặc prefix | Đánh giá |
| --- | --- |
| `acme.reports` | Root tương đối riêng cho thư viện báo cáo |
| `acme.reports.http.connect-timeout` | Tham số HTTP đặt trong nhóm chức năng cụ thể |
| `acme.reports.retry.max-attempts` | Mô tả rõ điều được cấu hình |
| `client.timeout` | Dễ trùng nếu có nhiều HTTP client |
| `app.enabled` | Quá chung khi thư viện nhúng vào nhiều ứng dụng |
| `spring.reports`, `management.reports` | Không nên tự ý chiếm namespace thuộc hệ sinh thái Spring Boot |

`acme` là tên giả định; hãy dùng root đúng với vendor hoặc sản phẩm của thư viện thực tế. Root nên **đủ đặc trưng nhưng không quá gắn với implementation**, chẳng hạn tránh đưa class name, package path hoặc số phiên bản không cần thiết vào prefix.

Quy tắc đặt tên:

1. Dùng **chữ thường** và **kebab-case** cho mỗi phần của tên thuộc tính, các phần phân cấp cách nhau bằng dấu chấm: `acme.reports.batch-size`.
2. Đặt group theo chức năng: `acme.reports.http.*`, `acme.reports.retry.*`, `acme.reports.export.*`.
3. Tên phải thể hiện ý nghĩa/đơn vị: `connect-timeout` tốt hơn `time`; `max-attempts` tốt hơn `count`.
4. Không dùng key toàn cục như `enabled`, `url`, `timeout` cho API cấu hình của thư viện.
5. Hai thư viện độc lập không chia sẻ một root chỉ vì chức năng tương tự. Nếu chúng cùng nhà cung cấp, mỗi thư viện vẫn cần nhóm con rõ ràng, như `acme.reports` và `acme.billing`.
6. Chọn mặc định và ngữ nghĩa của mỗi key trước khi phát hành. Khi đã được người dùng đưa vào YAML, Helm chart hoặc biến môi trường, key trở thành một phần **public configuration contract**.

Namespace không bắt buộc phải trùng groupId Maven/Gradle. Có thể chọn `acme.reports` ngay cả khi groupId thư viện là `com.example.infrastructure`, miễn tên public được công bố nhất quán.

## 3. Canonical key và relaxed binding

Trong Spring Boot, class `@ConfigurationProperties` nhận giá trị qua binder. Cách viết key được khuyến nghị trong tài liệu là **lowercase kebab-case**:

~~~properties
acme.reports.enabled=true
acme.reports.batch-size=50
acme.reports.timeout=5s
~~~

Binding tương ứng:

| Trong Java | Trong YAML/properties | Environment variable theo quy tắc canonical |
| --- | --- | --- |
| `boolean enabled` | `acme.reports.enabled` | `ACME_REPORTS_ENABLED` |
| `int batchSize` | `acme.reports.batch-size` | `ACME_REPORTS_BATCHSIZE` |
| `Duration timeout` | `acme.reports.timeout` | `ACME_REPORTS_TIMEOUT` |

Quy tắc chuyển từ tên canonical sang environment variable: **thay dấu chấm bằng underscore, bỏ dấu gạch ngang, rồi viết hoa**. Vì vậy dạng chuẩn của `batch-size` là `ACME_REPORTS_BATCHSIZE`. Spring Boot hỗ trợ relaxed binding, nhưng đừng thiết kế tài liệu và triển khai phụ thuộc vào một tập tên tự chế khác chuẩn.

Ví dụ CLI override một property:

~~~bash
java -jar reports-demo.jar --acme.reports.batch-size=80
~~~

`--acme.reports.batch-size` và `ACME_REPORTS_BATCHSIZE` vẫn là các biểu diễn của **cùng một thuộc tính logic**. Khi hai property sources cùng cung cấp giá trị, Spring Boot dùng cơ chế ưu tiên nguồn cấu hình. Prefix riêng giúp xác định *thuộc tính của ai*, không tự quy định *nguồn nào thắng*.

Một số nguyên tắc tránh lỗi:

- Annotation dùng `@ConfigurationProperties(prefix = "acme.reports")`; không dùng dạng camelCase như `acmeReports` cho prefix.
- Field `batchSize` bind từ `batch-size`; không nhất thiết đặt field Java có dấu gạch ngang.
- Nếu cấu hình YAML bị viết nhầm thành `acme.report.batch-size`, giá trị có thể không được bind; `@ConfigurationProperties` **mặc định có thể bỏ qua unknown fields**, nên cần test các key công khai.
- Properties bind từ nhiều nguồn khác nhau, không riêng `application.yml`. Khi chẩn đoán hãy kiểm tra cả command-line args, environment variables và property sources khác.

## 4. Dùng typed @ConfigurationProperties thay vì rải @Value

Với một thư viện có nhiều tham số, gom thành một class properties giúp kiểm soát contract, kiểu dữ liệu và validation.

**src/main/java/com/example/lib/config/ReportsProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.reports")
public class ReportsProperties {

    private boolean enabled = true;

    @Min(1)
    private int batchSize = 25;

    @NotNull
    private Duration timeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Giải thích:

- `@ConfigurationProperties(prefix = "acme.reports")` quyết định root duy nhất được bind vào class.
- Đây là JavaBean binding với getter/setter. Thư viện cũng có thể dùng immutable constructor binding/record, miễn phù hợp với cơ chế đăng ký và phiên bản Spring Boot mục tiêu.
- Field `batchSize` là `int`, giá trị `acme.reports.batch-size=50` được convert và bind vào field này.
- Dùng `Duration` giúp người dùng viết `500ms`, `5s`, `1m` thay vì một số nguyên mơ hồ về đơn vị.
- Defaults `enabled=true`, `batchSize=25`, `timeout=3s` có ý nghĩa khi user không cấu hình key tương ứng. Không thay đổi mặc định bất ngờ giữa các bản phát hành.
- `@Min(1)` ngăn batch-size bằng 0 hoặc âm; `@NotNull` tránh timeout null. `@Validated` kích hoạt Bean Validation cho object properties, khi ứng dụng có Bean Validation provider trên classpath (ví dụ `spring-boot-starter-validation`).
- Không nên vô tình in credential/token qua `toString()` của properties. Các secret vẫn cần phương án cấp phát và che dữ liệu phù hợp.

**Điểm rất quan trọng:** Viết `@ConfigurationProperties` trên class **chưa đủ để tự động có một Spring bean properties**. Thư viện cần đăng ký class đó bằng một cơ chế rõ ràng.

## 5. Thư viện tự đăng ký properties qua auto-configuration

Với Spring Boot 3.x, thư viện nên chủ động đăng ký properties trong auto-configuration, để ứng dụng tiêu thụ không phải thêm annotation thủ công.

**src/main/java/com/example/lib/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;
import com.example.lib.config.ReportsProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

Ở đây có ba khái niệm riêng:

1. `@EnableConfigurationProperties(ReportsProperties.class)` đăng ký **bean properties**, rồi binder lấy dữ liệu từ namespace `acme.reports`.
2. `@ConditionalOnProperty(prefix = "acme.reports", name = "enabled", havingValue = "true", matchIfMissing = true)` quyết định **có đăng ký default ReportClient hay không**. Dùng lại đúng prefix của thư viện, không dùng một cờ toàn cục `enabled`.
3. `@ConditionalOnMissingBean(ReportClient.class)` cho phép ứng dụng cung cấp ReportClient tùy chỉnh; auto-configuration sẽ nhường chỗ, không tạo thêm default cùng kiểu.

`matchIfMissing=true` phù hợp với default `enabled=true` trong `ReportsProperties`. Nếu muốn tính năng mặc định tắt, có thể chọn `enabled=false` cùng `matchIfMissing=false`, nhưng cần thiết kế contract nhất quán.

**Khi `acme.reports.enabled=false`:** bean `ReportsProperties` vẫn có thể tồn tại và được bind/validate; chỉ `ReportClient` do method có điều kiện trên không được đăng ký. Nếu ứng dụng tự khai báo `ReportClient`, điều kiện ở trên không xóa bean custom đó. Namespace, điều kiện đăng ký và dependency injection là ba cơ chế khác nhau.

Để Spring Boot phát hiện auto-configuration của thư viện, tạo resource chính xác:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

Mỗi dòng liệt kê tên class auto-configuration đầy đủ. Đây là cơ chế discovery của Spring Boot 3.x; không đặt tên file là `AutoConfiguration.imports.txt` và không dựa vào component scan để tìm class auto-configuration.

Không cần gắn `@Component` vào `ReportsProperties` khi đã dùng `@EnableConfigurationProperties`. Việc kết hợp tùy tiện component scanning, properties scanning và explicit registration có thể sinh duplicate bean/khó kiểm soát lifecycle. Với thư viện, đăng ký rõ ràng trên auto-configuration dễ hiểu và dễ kiểm thử.

## 6. Ví dụ Spring Boot 3.3.5, Java 17 chạy được

Đây là một dự án Maven nhỏ, với một **ứng dụng** sử dụng một **thư viện giả lập** nằm trong package riêng. `ReportClient` chỉ giữ config trong memory, không gọi HTTP thật nên ví dụ chạy độc lập.

### 6.1. Cây thư mục

~~~text
reports-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/ReportsDemoApplication.java
    │   │   └── lib/
    │   │       ├── ReportClient.java
    │   │       ├── config/ReportsProperties.java
    │   │       └── autoconfigure/ReportsAutoConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── ReportsAutoConfigurationTest.java
~~~

Ứng dụng ở package `com.example.app`; thư viện giả lập ở `com.example.lib`. Mặc định `@SpringBootApplication` chỉ component scan từ package ứng dụng xuống, nên các class auto-configuration nằm ngoài vùng scan và được nạp qua `AutoConfiguration.imports`. Trong hệ thống thật, hai phần này thường được đóng gói thành các JAR khác nhau.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reports-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-configuration-processor` sinh metadata gợi ý key cho IDE; nó không trực tiếp thực hiện việc bind tại runtime. Trong thư viện phát hành thật, nên đảm bảo metadata được tạo và đóng gói cùng artifact tương ứng.

### 6.3. Hai class đã được viết đầy đủ

Tạo `ReportsProperties.java` đúng nội dung mục 4 và `ReportsAutoConfiguration.java` đúng mục 5, giữ nguyên package, import và đường dẫn. Hai class ở trên đều là class hoàn chỉnh, có thể đặt vào file Java theo cây thư mục mục 6.1.

### 6.4. ReportClient.java

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

import java.time.Duration;

public final class ReportClient {
    private final int batchSize;
    private final Duration timeout;

    public ReportClient(int batchSize, Duration timeout) {
        this.batchSize = batchSize;
        this.timeout = timeout;
    }

    public String describe() {
        return "batchSize=" + batchSize + ", timeout=" + timeout;
    }
}
~~~

### 6.5. application.yml

**src/main/resources/application.yml**

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 50
    timeout: 5s
~~~

File `AutoConfiguration.imports` theo mục 5 chứa một dòng `com.example.lib.autoconfigure.ReportsAutoConfiguration`.

### 6.6. ReportsDemoApplication.java

**src/main/java/com/example/app/ReportsDemoApplication.java**

~~~java
package com.example.app;

import com.example.lib.ReportClient;
import com.example.lib.config.ReportsProperties;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReportsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner inspect(
            ReportsProperties properties,
            ObjectProvider<ReportClient> clientProvider) {
        return args -> {
            ReportClient client = clientProvider.getIfAvailable();
            System.out.println("enabled=" + properties.isEnabled());
            System.out.println("batchSize=" + properties.getBatchSize());
            System.out.println("timeout=" + properties.getTimeout());
            System.out.println(
                    "client=" + (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bên cạnh log Spring Boot, các dòng do runner in ra chính xác là:

~~~text
enabled=true
batchSize=50
timeout=PT5S
client=batchSize=50, timeout=PT5S
~~~

`Duration.toString()` biểu diễn 5 giây thành `PT5S`. Có thể quan sát `batch-size` bind thành `batchSize` và bean `ReportClient` nhận cùng cấu hình.

Để override một key:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.batch-size=80
~~~

Khi chạy lệnh riêng này, dòng `batchSize=50` đổi thành `batchSize=80` và client báo `batchSize=80`. Đó là override qua property source, không phải đổi code thư viện.

Để thử condition:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.enabled=false
~~~

Ngoài log, runner in:

~~~text
enabled=false
batchSize=50
timeout=PT5S
client=absent
~~~

`ReportsProperties` vẫn được bind, còn default client không được đăng ký. Hai lệnh trên là **hai lần chạy độc lập**, không dùng đồng thời hai giá trị override trong cùng một lệnh.

## 7. Kiểm thử namespace và điều kiện bằng ApplicationContextRunner

Một thư viện tốt cần kiểm thử rằng prefix của mình chỉ đọc đúng các key có liên quan và các điều kiện hoạt động như contract. Tạo:

**src/test/java/com/example/app/ReportsAutoConfigurationTest.java**

~~~java
package com.example.app;

import java.time.Duration;
import com.example.lib.ReportClient;
import com.example.lib.autoconfigure.ReportsAutoConfiguration;
import com.example.lib.config.ReportsProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void bindsPropertiesFromOwnedNamespace() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.batch-size=50",
                "acme.reports.timeout=5s")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .getBatchSize()).isEqualTo(50);
                    assertThat(context.getBean(ReportClient.class)
                            .describe()).isEqualTo(
                                    "batchSize=50, timeout=PT5S");
                });
    }

    @Test
    void disabledFeatureHasNoDefaultClient() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Test
    void unrelatedNamespaceDoesNotChangeOwnedSettings() {
        runner.withPropertyValues("other.reports.batch-size=900")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .getBatchSize()).isEqualTo(25);
                });
    }

    @Test
    void rejectsInvalidBatchSize() {
        runner.withPropertyValues("acme.reports.batch-size=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void userCanOverrideDefaultClient() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class)
                            .describe()).isEqualTo(
                                    "batchSize=99, timeout=PT1S");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {
        @Bean
        ReportClient customReportClient() {
            return new ReportClient(99, Duration.ofSeconds(1));
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kết quả mong đợi là **cả năm test đều pass**. Các assertion lần lượt kiểm tra binding đúng, tắt default bean, không bị namespace khác tác động, validation của `batch-size` và custom bean làm auto-configuration nhường chỗ.

Nếu thêm nhiều starter thật vào một ứng dụng, nên chạy thêm integration test để phát hiện va chạm property và bean không có trong bộ test cô lập. `ApplicationContextRunner` đặc biệt phù hợp để kiểm tra contract của một auto-configuration mà không cần khởi động cả ứng dụng.

## 8. Mở rộng namespace theo nhóm mà không phá contract

Giả sử thư viện báo cáo bổ sung export, HTTP và retry:

~~~yaml
acme:
  reports:
    enabled: true
    export:
      format: pdf
      output-directory: ./reports
    http:
      connect-timeout: 2s
      read-timeout: 10s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

Contract bao gồm:

~~~text
acme.reports.enabled
acme.reports.export.format
acme.reports.export.output-directory
acme.reports.http.connect-timeout
acme.reports.http.read-timeout
acme.reports.retry.max-attempts
acme.reports.retry.backoff
~~~

Có hai cách tổ chức typed properties:

- **Một class gốc có nested properties**, ví dụ `ReportsProperties.Export`, `ReportsProperties.Http`, `ReportsProperties.Retry`. Phù hợp khi các tùy chọn thường dùng chung và cùng vòng đời.
- **Nhiều class chuyên trách cùng một root**, ví dụ `@ConfigurationProperties("acme.reports.http")` và `@ConfigurationProperties("acme.reports.retry")`. Phù hợp khi các thành phần sử dụng cấu hình khác nhau và cần đăng ký rõ ràng từng type.

Minh họa class chuyên trách (đoạn này chỉ phác họa contract, không phải file Java chạy độc lập):

~~~java
@ConfigurationProperties(prefix = "acme.reports.retry")
public class ReportsRetryProperties {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(500);

    // Cần thêm getter/setter hoặc constructor binding tương ứng.
}
~~~

Nếu có nested custom object, metadata processor có thể cần `@NestedConfigurationProperty` trong một số cấu trúc để mô tả nhóm thuộc tính. Annotation này phục vụ **metadata**, không thay thế cách Spring Boot bind hoặc đăng ký bean.

Không đưa cấu hình thư viện vào `server.*`, `spring.*` hoặc `management.*` chỉ vì thư viện liên quan đến server, Spring hay giám sát. Các root đó đã có semantics của platform. Nếu thư viện cần đọc một property chuẩn của Spring Boot, hãy sử dụng **đúng contract chuẩn đó**; đừng chiếm key chuẩn làm API riêng.

## 9. Tính tương thích khi đổi tên key

Namespace là API công khai. Khi đổi key `acme.reports.batch-size` thành `acme.reports.max-batch-size`, các nơi triển khai có thể phải thay cả YAML, biến môi trường, command-line args, ConfigMap, deployment manifests, tài liệu và test.

Cách làm có kiểm soát:

1. Xác định vì sao cần đổi và ảnh hưởng tới người dùng.
2. Nếu cần giai đoạn hỗ trợ song song key cũ/mới, **thiết kế alias/migration ở runtime** và quy định ưu tiên rõ nếu cả hai cùng xuất hiện.
3. Đánh dấu deprecated trong metadata, ghi release notes, hướng dẫn đổi tên env var và lịch ngừng hỗ trợ.
4. Test riêng trường hợp chỉ có key cũ, chỉ có key mới, có cả hai và không có key nào.
5. Không đổi root prefix do rename Java package, di chuyển class nội bộ hoặc đổi Maven artifact.

**Cảnh báo:** `@DeprecatedConfigurationProperty` của Spring Boot chỉ giúp metadata và công cụ tài liệu hiểu thuộc tính deprecated; nó **không tự động bind tên cũ sang field tên mới** nếu bạn không xây cơ chế tương thích.

Nếu chưa có lý do mạnh, hãy giữ `acme.reports` ổn định và thêm nhóm con mới. Tính ổn định của tên cấu hình thường quan trọng hơn việc tên đó phản chiếu chính xác cấu trúc class hiện tại.

## 10. Metadata và tài liệu cho người sử dụng

Vì namespace là điểm tiếp xúc trực tiếp của người dùng thư viện, cần công bố:

| Key | Java type | Default | Ý nghĩa / giới hạn |
| --- | --- | --- | --- |
| `acme.reports.enabled` | `boolean` | `true` | Bật đăng ký default ReportClient của auto-configuration |
| `acme.reports.batch-size` | `int` | `25` | Phải >= 1 do `@Min(1)` |
| `acme.reports.timeout` | `Duration` | `3s` | Timeout có đơn vị, không được null |

Để IDE có thể gợi ý key khi người dùng soạn YAML/properties, thêm `spring-boot-configuration-processor` và kiểm tra file metadata trong JAR: `META-INF/spring-configuration-metadata.json`. Có thể bổ sung `META-INF/additional-spring-configuration-metadata.json` khi annotation processor không diễn đạt đủ thông tin.

Metadata giúp discovery/documentation nhưng **không thay thế việc bind, validate hoặc fallback**. Default trong metadata cũng phải thống nhất với default trong code. Với password/token, tránh in thông tin nhạy cảm qua logger, `toString()`, Actuator hoặc thông báo lỗi tùy biến; namespace không tự che dữ liệu.

Lưu ý `ReportsProperties` vẫn được đăng ký và validate khi `enabled=false` trong thiết kế ở trên. Nếu người dùng đặt `batch-size=0` cùng `enabled=false`, validation của properties bean vẫn có thể làm startup thất bại. Đó là ngữ nghĩa cần được tài liệu hóa hoặc thiết kế lại khi có yêu cầu chỉ validate lúc tính năng bật.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| YAML có `batch-size: 50` nhưng code vẫn nhận 25 | Key thiếu `acme.reports` hoặc class chưa được bind | Kiểm tra key đầy đủ và `@EnableConfigurationProperties` |
| Hai thư viện cùng đổi theo `timeout` toàn cục | Không có root rõ ràng | Tách prefix cho từng thư viện |
| `@ConfigurationProperties` không inject được | Chỉ annotate class, chưa đăng ký bean | Đăng ký trong auto-configuration bằng `@EnableConfigurationProperties` |
| IDE không gợi ý `acme.reports.*` | Thiếu metadata trong artifact | Kiểm tra configuration processor và đóng gói JAR |
| `enabled=false` mà properties bean vẫn có | Điều kiện chỉ đặt trên ReportClient | Phân biệt properties bean với bean dịch vụ |
| `enabled=false` mà có custom ReportClient | Custom bean do ứng dụng sở hữu | Condition trên default `@Bean` không xóa bean custom |
| Đổi prefix làm bản cũ nhận default thay vì cấu hình | Contract public đã thay đổi | Có lộ trình migration và test với các key cũ |
| Tưởng deprecated metadata tự tạo alias | Metadata không đổi binder runtime | Viết hỗ trợ key cũ/mới có chủ đích |
| Property cấu hình sai nhưng không báo lỗi | Unknown fields có thể bị bỏ qua | Test contract, validate field quan trọng, cân nhắc chính sách unknown keys |
| Secret bị lộ trong startup log | Log toàn bộ object properties | Che các field nhạy cảm, không in raw configuration |

Để chẩn đoán, ưu tiên kiểm tra bean `ReportsProperties` trong test và điều kiện tạo client. Spring Boot Actuator có thể cung cấp `/actuator/configprops` khi module và endpoint được cấu hình/expose, nhưng cần kiểm soát quyền truy cập và che thông tin nhạy cảm.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao thư viện báo cáo không nên đặt `timeout` ở root?  
**Đáp án:** Một thư viện khác cũng có thể cần timeout; `acme.reports.timeout` xác định rõ owner và ý nghĩa.

**Câu 2.** Property canonical của field `batchSize` trong class mang prefix `acme.reports` là gì?  
**Đáp án:** `acme.reports.batch-size`; môi trường có thể dùng `ACME_REPORTS_BATCHSIZE`.

**Câu 3.** Chỉ đặt `@ConfigurationProperties` lên class có đủ để ứng dụng inject nó không?  
**Đáp án:** Không. Phải đăng ký class bằng cơ chế phù hợp, ví dụ `@EnableConfigurationProperties` trên auto-configuration của thư viện.

**Câu 4.** Vì sao `acme.reports.enabled=false` vẫn có thể có bean `ReportsProperties`?  
**Đáp án:** Trong ví dụ, điều kiện tắt chỉ đặt trên method tạo default `ReportClient`. Properties được đăng ký độc lập để bind và validate.

**Câu 5.** Nếu đổi tên property public, `@DeprecatedConfigurationProperty` có bảo đảm runtime tiếp tục hiểu tên cũ không?  
**Đáp án:** Không. Cần chủ động triển khai alias/migration và kiểm thử.

**Câu 6.** Dùng phương pháp nào để xác minh thư viện không bị `other.reports.batch-size` thay đổi?  
**Đáp án:** `ApplicationContextRunner` set key của namespace khác rồi assert `ReportsProperties.batchSize` vẫn giữ default 25.

## 13. Áp dụng vào thư viện thực tế

Trước khi phát hành một library starter, hãy xác nhận các quyết định: root namespace thuộc đúng tổ chức/tính năng; các key có tên canonical và có đơn vị rõ; typed `@ConfigurationProperties` được đăng ký từ auto-configuration; điều kiện `@ConditionalOnProperty` dùng đúng prefix; defaults và validation nhất quán; metadata được phát hành; tài liệu có YAML và env var examples; tests chứng minh cấu hình khác namespace không can thiệp và custom bean có thể thay default.

**Ghi nhớ:** `@ConfigurationProperties` là giao diện cấu hình công khai của thư viện. Namespace riêng như `acme.reports` khiến hệ thống nhiều starter vẫn rõ ràng về **thuộc tính nào thuộc thư viện nào**, tránh va chạm tên, hỗ trợ kiểm thử và giúp người dùng nâng cấp an toàn.
