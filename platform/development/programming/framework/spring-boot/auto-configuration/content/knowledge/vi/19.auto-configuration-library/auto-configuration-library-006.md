# Đăng ký thuộc tính thư viện và cung cấp giá trị mặc định có chủ đích

## 1. Hai việc cần làm trong một thư viện Spring Boot

Một thư viện tích hợp Spring Boot thường cần công bố các tùy chọn để ứng dụng sử dụng có thể cấu hình mà không sửa code thư viện. Ví dụ, thư viện báo cáo có thể cho phép bật/tắt tính năng, chọn kích thước batch và đặt timeout:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 25
    timeout: 3s
~~~

Để các key này có hiệu lực, thư viện cần giải quyết **hai việc độc lập**:

1. **Đăng ký properties:** đưa lớp `@ConfigurationProperties` vào ApplicationContext để Spring Boot bind giá trị từ Environment.
2. **Cung cấp default có chủ đích:** xác định giá trị dùng khi ứng dụng không khai báo property, đồng thời đồng bộ điều kiện tạo bean mặc định với cùng ngữ nghĩa.

Chỉ viết `@ConfigurationProperties` trên một class chưa chắc class đó đã trở thành bean. Tương tự, field initializer như `private int batchSize = 25` không tự bật/tắt một auto-configuration method có `@ConditionalOnProperty`; condition đọc property từ Environment, không đọc giá trị field Java.

Bài này dùng namespace minh họa **`acme.reports`**, Java 17 và Spring Boot 3.3.13. Các ví dụ có thể đặt trong một thư viện starter hoặc một project mô phỏng thư viện và ứng dụng tiêu thụ.

## 2. Thiết kế properties như một API công khai

Tên property, kiểu dữ liệu, default và ý nghĩa là contract giữa thư viện với ứng dụng. Người dùng có thể lưu key trong YAML, environment variables, ConfigMap, Helm chart, pipeline hoặc command-line arguments. Khi đã phát hành, đổi tên key có thể ảnh hưởng nhiều môi trường triển khai.

Một namespace tốt có dạng:

~~~text
<vendor>.<library-or-feature>.<property>
~~~

Ví dụ:

~~~properties
acme.reports.enabled=true
acme.reports.batch-size=25
acme.reports.timeout=3s
acme.reports.retry.max-attempts=3
~~~

Quy ước nên giữ:

- Dùng prefix riêng, có chủ sở hữu rõ ràng; tránh các key toàn cục như `enabled`, `timeout`, `url`.
- Dùng tên canonical lowercase kebab-case trong tài liệu và cấu hình.
- Nhóm các thuộc tính có cùng mục đích dưới prefix con như `http`, `retry`, `export`.
- Ghi rõ kiểu, đơn vị, default, phạm vi giá trị và tác động của từng key.
- Không đưa secret/token vào default; không tạo endpoint hoặc thông tin xác thực giả khiến ứng dụng kết nối nhầm.
- Giữ tên và ngữ nghĩa ổn định giữa các bản phát hành; migration key cũ cần kế hoạch riêng.

Một default tốt phải an toàn, dễ dự đoán, không gây tác dụng phụ bất ngờ và phù hợp với mục đích thư viện. Ví dụ, timeout 3 giây hoặc batch-size 25 có thể là default hợp lý cho thư viện báo cáo mẫu; thư viện thực tế phải chọn theo tải, tài nguyên và semantics API.

## 3. Đăng ký @ConfigurationProperties trong thư viện

Spring Boot có một số cách đăng ký properties bean. Với thư viện tự cấu hình, cách rõ ràng thường là dùng `@EnableConfigurationProperties` ngay trên auto-configuration của thư viện.

### 3.1. @EnableConfigurationProperties

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.config.ReportsProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {
}
~~~

`@EnableConfigurationProperties(ReportsProperties.class)` đăng ký bean properties và bật cơ chế bind cho class đó. Khi auto-configuration được nạp, ứng dụng có thể inject `ReportsProperties` vào các bean khác.

Ưu điểm đối với thư viện:

- Không yêu cầu người dùng thêm `@ConfigurationPropertiesScan` trong ứng dụng.
- Không phụ thuộc component scan của ứng dụng có quét package thư viện hay không.
- Tập trung việc đăng ký properties tại entry point auto-configuration.
- Có thể liệt kê tường minh các properties class mà module sở hữu.

Một auto-configuration có thể đăng ký nhiều lớp:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
        ReportsProperties.class,
        ReportsRetryProperties.class
})
public class ReportsAutoConfiguration {
}
~~~

Chỉ đăng ký những class mà module thực sự sở hữu; tránh đăng ký trùng cùng type qua nhiều cơ chế thiếu chủ đích.

### 3.2. @ConfigurationPropertiesScan

Ứng dụng có thể dùng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

Annotation này quét package của ứng dụng và các package con để tìm class `@ConfigurationProperties`. Cách này phù hợp khi **ứng dụng** sở hữu properties class của chính nó.

Đối với thư viện tái sử dụng, không nên buộc mọi ứng dụng phải scan package của thư viện. Nếu package thư viện nằm ngoài vùng scan, properties có thể không được đăng ký. Auto-configuration của thư viện nên tự đăng ký type qua `@EnableConfigurationProperties`.

### 3.3. @Bean + @ConfigurationProperties cho type bên thứ ba

Nếu cần bind property vào một class không do thư viện sở hữu hoặc không thể gắn annotation lên class đó, có thể khai báo:

~~~java
@Bean
@ConfigurationProperties(prefix = "acme.reports.client")
ThirdPartyClientSettings clientSettings() {
    return new ThirdPartyClientSettings();
}
~~~

Đây là method minh họa trong một class cấu hình. Spring Boot bind các key dưới prefix vào object trả về từ method. Cách này hữu ích với type bên thứ ba có setter phù hợp.

Không dùng nhiều cách đăng ký cùng một properties type nếu không có lý do rõ ràng. Một type được đăng ký hai lần có thể tạo bean instance không mong muốn hoặc làm người đọc khó xác định nguồn cấu hình.

## 4. Cung cấp default bằng JavaBean field initializer

Cách đơn giản và dễ hiểu là khởi tạo field với giá trị mặc định ngay trong class properties. Spring Boot bind các giá trị người dùng cung cấp lên object; property không xuất hiện sẽ giữ giá trị khởi tạo.

**ReportsProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
import jakarta.validation.Valid;
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

    @Valid
    private Retry retry = new Retry();

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

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        @Min(0)
        private int maxAttempts = 3;

        @NotNull
        private Duration backoff = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getBackoff() {
            return backoff;
        }

        public void setBackoff(Duration backoff) {
            this.backoff = backoff;
        }
    }
}
~~~

Giải thích:

- `enabled = true`: tính năng được bật mặc định theo contract của ví dụ.
- `batchSize = 25`: batch nhỏ, dễ dự đoán; giá trị tối thiểu là 1.
- `timeout = Duration.ofSeconds(3)`: timeout có đơn vị rõ ràng.
- `retry = new Retry()`: object nhóm retry tồn tại kể cả khi ứng dụng không khai báo key con.
- `@Valid` trên nested object kích hoạt validation cho các field bên trong `Retry`.
- `@Validated`, `@Min` và `@NotNull` giúp kiểm tra giá trị sau khi bind, khi ứng dụng có Bean Validation provider.

Với JavaBean binding, getter/setter cho phép binder gán giá trị từ Environment. Nếu property không có, initializer được giữ nguyên. Primitive Java tự có giá trị mặc định như `0` hoặc `false`; **đừng dựa vào default của ngôn ngữ** khi contract cần một giá trị khác. Hãy ghi rõ initializer.

### 4.1. Default của nested properties

Ví dụ YAML:

~~~yaml
acme:
  reports:
    retry:
      max-attempts: 5
~~~

Nếu chỉ khai báo `max-attempts`, field `backoff` vẫn giữ `250ms`. Nếu không khai báo cả nhóm `retry`, initializer `new Retry()` giữ hai giá trị `3` và `250ms`.

Nếu nested object là nullable và không được khởi tạo, không nên giả định binder luôn tạo object chỉ vì có property con. Hãy thiết kế object graph rõ ràng: khởi tạo nested bean, dùng constructor binding với default thích hợp hoặc kiểm thử trường hợp không có property con.

## 5. Default cho immutable properties và record

Nếu muốn properties bất biến, có thể dùng constructor binding. Với Java record trên Spring Boot 3.x, canonical constructor được dùng để bind. Annotation `@DefaultValue` cho phép công bố default ngay tại record component.

**ReportsRecordProperties.java**

~~~java
package com.example.lib.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.reports")
public record ReportsRecordProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("25") @Min(1) int batchSize,
        @DefaultValue("3s") @NotNull Duration timeout) {
}
~~~

Đây là **một phương án thay thế** cho JavaBean class ở mục 4; không đăng ký cả hai class cùng prefix trong một ứng dụng demo nếu chúng biểu diễn cùng contract.

Các điểm cần nhớ:

- `@DefaultValue("25")` cung cấp default khi property không có giá trị bind.
- `Duration` nhận chuỗi có đơn vị như `3s`, `500ms`, `1m`.
- Không cần setter vì record bất biến.
- Với class constructor-bound thông thường, cần constructor binding phù hợp; tránh gắn `@Autowired` vào constructor định dùng cho constructor binding.
- `@EnableConfigurationProperties` vẫn là cách đăng ký record properties rõ ràng trong auto-configuration.

Với nested record, có thể dùng `@DefaultValue` trên parameter tương ứng để yêu cầu tạo nested object khi không có property con, rồi đặt default cho các thành phần bên trong. Hãy kiểm tra bằng test vì null, empty và object chứa default là những trạng thái khác nhau.

## 6. Phân biệt default của property và default của bean

Đây là điểm dễ gây lỗi trong thư viện auto-configuration.

**Default property** là giá trị của một thuộc tính, ví dụ `acme.reports.batch-size=25` khi người dùng không cấu hình.

**Default bean** là một đối tượng Spring mà thư viện tạo sẵn, ví dụ `ReportClient`, nếu ứng dụng chưa cung cấp bean thay thế.

Hai việc này có thể liên quan nhưng không đồng nhất. Ví dụ:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(ReportsProperties.class)
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

Ở đây:

- `@EnableConfigurationProperties` đăng ký properties bean.
- `@ConditionalOnProperty` điều khiển default client theo cờ enabled.
- `@ConditionalOnMissingBean` cho phép ứng dụng tự cung cấp client.
- Default field trong `ReportsProperties` quyết định batch-size và timeout nếu người dùng không ghi đè.

### 6.1. matchIfMissing phải đồng bộ với default của enabled

Giả sử class properties có:

~~~java
private boolean enabled = true;
~~~

Nhưng bean method lại khai báo:

~~~java
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
~~~

Khi người dùng không khai báo property, object properties sẽ có `enabled=true`, nhưng condition vẫn **không khớp** vì property không có trong Environment và `matchIfMissing=false`.

Đây là hai cơ chế đọc dữ liệu khác nhau:

- Binder tạo object và giữ field initializer.
- `@ConditionalOnProperty` kiểm tra property trong Environment, không đọc field initializer của bean properties.

Nếu contract muốn tính năng bật mặc định, hãy đồng bộ:

~~~java
private boolean enabled = true;
~~~

với:

~~~java
matchIfMissing = true
~~~

Nếu contract muốn tắt mặc định:

~~~java
private boolean enabled = false;
~~~

và:

~~~java
matchIfMissing = false
~~~

Đây là quy tắc quan trọng để tránh tình huống log properties nói enabled=true nhưng default bean lại không được đăng ký.

### 6.2. @ConditionalOnMissingBean không phải default value

`@ConditionalOnMissingBean(ReportClient.class)` không gán giá trị mặc định cho property. Nó chỉ quyết định method tạo bean có được áp dụng khi chưa có bean phù hợp hay không.

Tương tự, `@Primary` chỉ ưu tiên bean khi inject một dependency đơn giá trị. Nếu mục tiêu là không tạo default client khi ứng dụng đã có client riêng, hãy dùng condition phù hợp; không dùng `@Primary` để thay thế.

## 7. Ví dụ project Maven hoàn chỉnh

Ví dụ dùng **Java 17+ và Spring Boot 3.3.13**. Ta đặt class ứng dụng và package thư viện mô phỏng ở hai package riêng để Spring Boot phát hiện auto-configuration qua resource chính thức.

### 7.1. Cây thư mục

~~~text
reports-defaults-demo/
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

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reports-defaults-demo</artifactId>
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

`spring-boot-configuration-processor` sinh metadata phục vụ gợi ý cấu hình trong IDE; nó không phải thành phần runtime thực hiện binding. `spring-boot-starter-validation` cung cấp Bean Validation implementation để các constraint như `@Min` hoạt động.

### 7.3. ReportsProperties.java

Tạo file **src/main/java/com/example/lib/config/ReportsProperties.java** bằng toàn bộ JavaBean class ở mục 4. Giữ đúng package `com.example.lib.config`.

### 7.4. ReportClient.java

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

import java.time.Duration;

public record ReportClient(int batchSize, Duration timeout) {
    public String describe() {
        return "batchSize=" + batchSize + ", timeout=" + timeout;
    }
}
~~~

Record này mô phỏng một bean client dùng cấu hình đã bind; không kết nối dịch vụ bên ngoài.

### 7.5. ReportsAutoConfiguration.java

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
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient(ReportsProperties properties) {
        return new ReportClient(
                properties.getBatchSize(),
                properties.getTimeout());
    }
}
~~~

Auto-configuration đăng ký properties kể cả khi feature bị tắt. Điều kiện enabled chỉ đặt trên bean method ReportClient, vì vậy người dùng vẫn có thể inject và kiểm tra `ReportsProperties` khi `enabled=false`.

### 7.6. AutoConfiguration.imports

Tạo resource:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

Spring Boot 3.x dùng resource này để phát hiện auto-configuration của thư viện. Trong dự án thật, resource được đóng gói bên trong JAR của module auto-configuration.

### 7.7. application.yml

**src/main/resources/application.yml**

~~~yaml
# Cố ý không khai báo acme.reports:
# ứng dụng sẽ dùng default trong ReportsProperties.
spring:
  application:
    name: reports-defaults-demo
~~~

Không nên đóng gói một `application.yml` chung trong JAR thư viện chỉ để cung cấp default cho người dùng. File application configuration thuộc ứng dụng và có thể gây xung đột khi nhiều thư viện cùng cung cấp resource cùng tên. Default của thư viện nên nằm trong typed properties hoặc cơ chế cấu hình được công bố rõ ràng.

### 7.8. ReportsDemoApplication.java

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
            System.out.println("retry.maxAttempts="
                    + properties.getRetry().getMaxAttempts());
            System.out.println("retry.backoff="
                    + properties.getRetry().getBackoff());
            System.out.println("client="
                    + (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

Dùng `ObjectProvider` để runner chạy được cả khi client có hoặc không có. Nếu inject ReportClient trực tiếp như dependency bắt buộc, trường hợp `enabled=false` sẽ khiến context lỗi vì không có bean phù hợp.

Chạy:

~~~bash
mvn spring-boot:run
~~~

Ngoài log khởi động, runner in:

~~~text
enabled=true
batchSize=25
timeout=PT3S
retry.maxAttempts=3
retry.backoff=PT0.25S
client=batchSize=25, timeout=PT3S
~~~

Đây là kết quả khi không khai báo property `acme.reports.*`: binder giữ các initializer và auto-configuration tạo default client vì `matchIfMissing=true`.

### 7.9. Override default bằng application.yml

Thay nội dung file bằng:

~~~yaml
acme:
  reports:
    enabled: true
    batch-size: 80
    timeout: 5s
    retry:
      max-attempts: 4
      backoff: 500ms
~~~

Chạy lại:

~~~bash
mvn spring-boot:run
~~~

Các dòng runner trở thành:

~~~text
enabled=true
batchSize=80
timeout=PT5S
retry.maxAttempts=4
retry.backoff=PT0.5S
client=batchSize=80, timeout=PT5S
~~~

Những field không được override vẫn giữ default của class. Ví dụ, nếu chỉ đặt `batch-size: 80`, timeout và retry backoff vẫn giữ giá trị ban đầu.

### 7.10. Override bằng command-line arguments

Không cần sửa YAML, có thể chạy:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--acme.reports.batch-size=90 --acme.reports.timeout=7s"
~~~

Lúc này batch-size là 90, timeout là 7 giây. Command-line property source có độ ưu tiên cao hơn application configuration thông thường, nên có thể override giá trị YAML.

Để tắt tính năng:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--acme.reports.enabled=false
~~~

Các dòng chính:

~~~text
enabled=false
batchSize=25
timeout=PT3S
client=absent
~~~

`ReportsProperties` vẫn tồn tại và giữ default/giá trị bind. Default `ReportClient` không được đăng ký vì condition property không khớp. Nếu ứng dụng tự khai báo ReportClient, condition missing-bean sẽ tiếp tục cho phép bean custom tồn tại.

## 8. Kiểm thử default, override, validation và back-off

Không nên chỉ kiểm tra qua log. Một thư viện nên kiểm thử contract cấu hình bằng `ApplicationContextRunner`, vì nó tạo context nhỏ, cho phép truyền property và xác nhận bean mà không cần khởi động cả ứng dụng.

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
    void bindsIntentionalDefaultsAndCreatesDefaultClient() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ReportsProperties.class);
            assertThat(context).hasSingleBean(ReportClient.class);

            ReportsProperties properties =
                    context.getBean(ReportsProperties.class);

            assertThat(properties.isEnabled()).isTrue();
            assertThat(properties.getBatchSize()).isEqualTo(25);
            assertThat(properties.getTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(properties.getRetry().getMaxAttempts()).isEqualTo(3);
            assertThat(properties.getRetry().getBackoff())
                    .isEqualTo(Duration.ofMillis(250));

            assertThat(context.getBean(ReportClient.class).describe())
                    .isEqualTo("batchSize=25, timeout=PT3S");
        });
    }

    @Test
    void bindsValuesThatOverrideDefaults() {
        runner.withPropertyValues(
                "acme.reports.batch-size=80",
                "acme.reports.timeout=5s",
                "acme.reports.retry.max-attempts=4",
                "acme.reports.retry.backoff=500ms")
                .run(context -> {
                    ReportsProperties properties =
                            context.getBean(ReportsProperties.class);

                    assertThat(properties.getBatchSize()).isEqualTo(80);
                    assertThat(properties.getTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.getRetry().getMaxAttempts())
                            .isEqualTo(4);
                    assertThat(properties.getRetry().getBackoff())
                            .isEqualTo(Duration.ofMillis(500));
                    assertThat(context.getBean(ReportClient.class).describe())
                            .isEqualTo("batchSize=80, timeout=PT5S");
                });
    }

    @Test
    void disabledFeatureKeepsPropertiesButDoesNotCreateDefaultClient() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportsProperties.class);
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(context.getBean(ReportsProperties.class)
                            .isEnabled()).isFalse();
                });
    }

    @Test
    void invalidBatchSizeFailsValidation() {
        runner.withPropertyValues("acme.reports.batch-size=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void applicationClientReplacesDefaultClient() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).describe())
                            .isEqualTo("batchSize=99, timeout=PT1S");
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

Kỳ vọng **năm test pass**:

1. Khi không có property, default được bind và default client được tạo.
2. Property người dùng cung cấp override các default.
3. Khi enabled=false, properties vẫn có nhưng default client không được tạo.
4. Batch-size không hợp lệ bị validation từ chối.
5. Bean do ứng dụng cung cấp khiến auto-configuration nhường chỗ.

Nếu test validation không fail như mong đợi, kiểm tra đã thêm `spring-boot-starter-validation`, class có `@Validated`, field có constraint và properties được đăng ký đúng chưa.

## 9. Thứ tự ưu tiên: default trong class và property sources

Field initializer chỉ là **giá trị fallback khi binder không nhận được giá trị khác**. Nếu property có mặt từ nguồn cấu hình, giá trị nguồn đó sẽ được bind theo cơ chế ưu tiên của Spring Environment.

Ví dụ class có:

~~~java
private int batchSize = 25;
~~~

File `application.yml`:

~~~yaml
acme:
  reports:
    batch-size: 50
~~~

Environment variable:

~~~text
ACME_REPORTS_BATCHSIZE=80
~~~

Command-line argument:

~~~bash
--acme.reports.batch-size=100
~~~

Khi nhiều nguồn cùng cung cấp một key, nguồn có độ ưu tiên cao hơn quyết định giá trị được bind. Trong Spring Boot thông thường, command-line arguments ưu tiên hơn environment variables và application config; environment variables ưu tiên hơn file application configuration. Chi tiết có thể phụ thuộc loại property source và cách ứng dụng khởi chạy.

**Default trong class không tham gia cuộc cạnh tranh ưu tiên này như một property source riêng.** Nó chỉ giữ nguyên khi không có giá trị nào được bind vào field đó.

Không nên dùng một default trong Java và một default khác trong YAML của ứng dụng demo rồi mong người dùng đoán giá trị nào là chuẩn. Hãy có một nguồn contract rõ ràng và test các override cần thiết.

## 10. Kiểu dữ liệu, collection và default lồng nhau

### 10.1. Duration và DataSize

Với timeout, dùng `Duration`:

~~~java
private Duration connectTimeout = Duration.ofSeconds(2);
~~~

Người dùng có thể cấu hình:

~~~yaml
acme:
  reports:
    connect-timeout: 500ms
~~~

Với kích thước bộ nhớ/dữ liệu, dùng `DataSize` thay vì số nguyên không đơn vị:

~~~java
private DataSize maxPayload = DataSize.ofMegabytes(10);
~~~

Cấu hình:

~~~yaml
acme:
  reports:
    max-payload: 20MB
~~~

Chọn kiểu dữ liệu diễn tả đúng đơn vị giúp tránh nhầm milliseconds với seconds hoặc bytes với kilobytes. Hãy công bố rõ đơn vị và giới hạn hợp lệ.

### 10.2. List và Map

Có thể khai báo:

~~~java
private List<String> supportedFormats =
        new ArrayList<>(List.of("csv", "json"));

private Map<String, String> headers = new LinkedHashMap<>();
~~~

Binder có quy tắc riêng khi nhiều property sources cung cấp collection. Đặc biệt, **list ở nguồn có ưu tiên cao hơn thường thay thế list trước đó**, không nên giả định các phần tử tự động được nối thêm. Map được bind theo key và có thể kết hợp dữ liệu từ nhiều nguồn. Nếu contract phụ thuộc vào merge/replace, hãy viết test cho trường hợp nhiều nguồn cấu hình.

Không dùng collection mutable được chia sẻ tĩnh giữa các application context. Mỗi properties bean nên sở hữu instance riêng, tránh state rò rỉ giữa test hoặc ứng dụng.

### 10.3. Null, empty và default

Ba trạng thái này có thể khác nhau:

- **Không khai báo property:** default trong class/constructor có thể được giữ.
- **Khai báo giá trị rỗng:** binder có thể xử lý theo converter và kiểu dữ liệu; không luôn tương đương với không khai báo.
- **Khai báo null trong YAML:** tùy kiểu và binder, có thể thành null hoặc giá trị khác; cần test thay vì suy đoán.

Nếu một property bắt buộc phải có giá trị, dùng validation như `@NotNull` và thông báo rõ cách cấu hình. Nếu default hợp lệ, khởi tạo tường minh để tránh null ngoài ý muốn.

## 11. Metadata và tài liệu cấu hình

Thư viện nên hỗ trợ IDE gợi ý property. Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Processor sinh metadata trong:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata có thể mô tả tên property, type, description, default value, deprecation và nhóm properties. Hãy kiểm tra file metadata được sinh và đóng gói trong artifact thực tế. Không nên giả định mọi field initializer phức tạp đều được processor suy ra hoàn hảo. Nếu cần, bổ sung:

~~~text
META-INF/additional-spring-configuration-metadata.json
~~~

Metadata giúp IDE/documentation, nhưng **không thực hiện binding, không validate và không tạo bean**. Default trong metadata phải thống nhất với default thật trong code.

Nếu đổi tên key, `@DeprecatedConfigurationProperty` có thể giúp công cụ nhận diện property cũ là deprecated. Annotation này **không tự tạo alias runtime** cho tên mới. Nếu vẫn cần hỗ trợ key cũ, hãy triển khai migration/alias có quy tắc ưu tiên và test cả hai trường hợp.

## 12. Đặt default an toàn và có chủ đích

Không phải mọi property đều nên có default. Hãy quyết định theo tác động:

| Loại property | Cân nhắc default |
| --- | --- |
| Feature flag | Quyết định rõ bật hay tắt mặc định; condition phải khớp cùng quyết định |
| Timeout | Dùng Duration có đơn vị; tránh vô hạn nếu có thể gây treo tài nguyên |
| Batch size | Chọn giá trị hữu hạn, kiểm soát memory/throughput |
| Retry attempts | Default vừa phải; tránh retry vô hạn hoặc khuếch đại tải |
| Endpoint | Chỉ đặt default nếu endpoint là service công khai ổn định; không trỏ nhầm môi trường |
| Username/password/token | Không cung cấp secret giả hoặc credential mặc định |
| TLS/SSL | Ưu tiên mặc định an toàn; không tắt xác thực certificate chỉ để dễ chạy |
| Collection | Xác định rõ empty list có nghĩa là không hỗ trợ, dùng default hay tắt chức năng |

Default phải được ghi trong tài liệu. Nếu giá trị mặc định có tác động tới chi phí, tải, network hoặc bảo mật, cần giải thích lý do và cách override.

Tránh các default gây hành động bên ngoài ngay khi context khởi động. Ví dụ, chỉ vì thư viện có endpoint mặc định không có nghĩa nên lập tức kết nối mạng hoặc tạo thread nền trong constructor của properties bean.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Inject properties bị lỗi không tìm thấy bean | Chỉ có `@ConfigurationProperties`, chưa đăng ký type | Dùng `@EnableConfigurationProperties` trong auto-configuration |
| Ứng dụng phải tự scan package thư viện | Thư viện phụ thuộc component scan của consumer | Đăng ký properties từ auto-configuration |
| Properties nói enabled=true nhưng default client không có | Field initializer không được `@ConditionalOnProperty` đọc | Đồng bộ field default với `matchIfMissing` |
| Bean default luôn được tạo dù user có custom bean | Thiếu `@ConditionalOnMissingBean` hoặc kiểm tra sai type | Thêm condition theo contract bean |
| Default primitive là 0/false ngoài mong đợi | Dựa vào default của Java thay vì contract | Khởi tạo field tường minh hoặc dùng `@DefaultValue` |
| Nested properties bị null | Không khởi tạo nested object hoặc thiết kế constructor chưa đúng | Khởi tạo nested bean/record và test khi không có key con |
| Giá trị timeout không rõ đơn vị | Dùng `long` hoặc `int` không quy ước | Dùng `Duration` |
| Validation không chạy | Thiếu validation provider hoặc thiếu `@Validated`/constraint | Thêm starter validation và test startup failure |
| enabled=false nhưng properties bean vẫn tồn tại | Condition chỉ đặt trên default service bean | Đây là hành vi bình thường; đặt condition ở properties registration nếu thật sự muốn bỏ properties |
| Đổi key cũ nhưng người dùng mất cấu hình | Nghĩ metadata deprecated tự alias runtime | Viết migration/alias và test |
| Nhiều thư viện có property trùng tên | Prefix quá chung | Thiết kế namespace riêng, có owner rõ |
| JAR thư viện chứa application.yml gây xung đột | Dùng file cấu hình ứng dụng làm default của library | Đặt default trong typed properties |

## 14. Checklist phát hành thư viện

Trước khi phát hành starter/autoconfigure, xác nhận:

1. Prefix thuộc sở hữu thư viện và dùng canonical kebab-case.
2. Mọi properties class đã được đăng ký bằng `@EnableConfigurationProperties` hoặc cơ chế được chọn rõ ràng.
3. Default trong Java/record phản ánh đúng contract đã tài liệu hóa.
4. `@ConditionalOnProperty.matchIfMissing` đồng bộ với default của feature flag.
5. Default bean có `@ConditionalOnMissingBean` nếu ứng dụng được phép thay thế.
6. Kiểu dữ liệu có đơn vị phù hợp: Duration, DataSize, enum, list/map.
7. Validation có provider, constraint và test.
8. Configuration metadata được tạo/đóng gói.
9. Không có secret hoặc endpoint nguy hiểm làm default.
10. Test default, override, disabled, invalid value và custom bean.
11. Có hướng dẫn migration nếu đổi property public.
12. Auto-configuration được công bố qua `AutoConfiguration.imports` trong Boot 3.x.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chỉ gắn `@ConfigurationProperties` chưa chắc có thể inject properties bean?  
**Đáp án:** Annotation mô tả cách bind, còn class vẫn phải được đăng ký. Thư viện thường dùng `@EnableConfigurationProperties(ReportsProperties.class)` trong auto-configuration.

**Câu 2.** Nếu field `enabled=true` nhưng `@ConditionalOnProperty(matchIfMissing=false)`, khi property vắng mặt điều gì xảy ra?  
**Đáp án:** Properties object có enabled=true nhưng condition không khớp vì property không tồn tại trong Environment. Hai cơ chế không đọc cùng một nguồn.

**Câu 3.** Khi muốn feature bật mặc định, cấu hình nào cần đồng bộ?  
**Đáp án:** Default trong properties là true và `matchIfMissing=true` trên condition đăng ký bean.

**Câu 4.** `@ConditionalOnMissingBean` có cung cấp default value cho batch-size không?  
**Đáp án:** Không. Nó quyết định default bean có được đăng ký không; giá trị batch-size thuộc `@ConfigurationProperties`.

**Câu 5.** Vì sao dùng `Duration` tốt hơn một số nguyên `timeout=3000`?  
**Đáp án:** Kiểu Duration biểu diễn đơn vị thời gian rõ ràng và hỗ trợ cấu hình như 500ms hoặc 3s.

**Câu 6.** Khi feature bị tắt, properties bean có nhất thiết biến mất không?  
**Đáp án:** Không. Nếu `@EnableConfigurationProperties` nằm ở cấp auto-configuration và condition chỉ đặt trên ReportClient method, properties vẫn tồn tại; chỉ default client bị bỏ qua.

**Câu 7.** `@DeprecatedConfigurationProperty` có tự bind tên property cũ sang field mới không?  
**Đáp án:** Không. Nó hỗ trợ metadata/deprecation; runtime alias cần được triển khai và kiểm thử riêng.

**Ghi nhớ:** Một thư viện Spring Boot tốt **tự đăng ký properties**, **công bố default rõ ràng** và **đồng bộ điều kiện tạo bean với default đó**. Dùng `@EnableConfigurationProperties` trong auto-configuration, field initializer hoặc `@DefaultValue` cho giá trị fallback, `@Validated` cho dữ liệu hợp lệ, `@ConditionalOnProperty` cho feature flag và `@ConditionalOnMissingBean` cho bean có thể được ứng dụng thay thế. Kiểm thử default, override và các nhánh điều kiện trước khi phát hành.
