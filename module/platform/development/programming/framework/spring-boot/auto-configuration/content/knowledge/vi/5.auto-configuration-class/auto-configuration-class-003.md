# Tách cấu hình theo chức năng thay vì gom mọi tích hợp vào một lớp

> **Ngữ cảnh:** Spring Boot 3.3.x, Java 17+, trong phần **Lớp tự cấu hình**. Bài này giải thích cách thiết kế nhiều auto-configuration có phạm vi hẹp, độc lập và có điều kiện rõ ràng. Ví dụ dùng Spring Boot 3.3.13 với Maven để bạn có thể tự chạy và quan sát từng tính năng.

## 1. Vấn đề: một lớp cấu hình làm tất cả

Khi bắt đầu phát triển một thư viện cho nhiều ứng dụng Spring Boot, ta dễ viết một lớp duy nhất:

```java
// Mã minh họa thiết kế cần cải thiện; các type chưa khai báo ở đây.
@AutoConfiguration
class EverythingAutoConfiguration {
    @Bean AuditService auditService() { /* ... */ }
    @Bean NotificationService notificationService() { /* ... */ }
    @Bean MetricsBridge metricsBridge() { /* ... */ }
    @Bean VendorClient vendorClient() { /* ... */ }
}
```

Ban đầu việc gom chung có vẻ tiện: ít tệp, một nơi để tìm. Nhưng khi audit, notification, metrics và tích hợp vendor có vòng đời, classpath và điều kiện kích hoạt khác nhau, lớp này dần tạo ra **phụ thuộc không cần thiết**.

Ví dụ, bạn đặt điều kiện trên cả lớp:

```java
// Mã minh họa: điều kiện vendor áp lên TOÀN BỘ lớp.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.OptionalClient")
class EverythingAutoConfiguration {
    // Tất cả @Bean, kể cả audit thuần Java,
    // đều chỉ được xét khi OptionalClient hiện diện.
}
```

Kết quả: ứng dụng không dùng vendor cũng mất luôn tính năng audit. Đó là lỗi đặt ranh giới điều kiện, không phải lỗi của `@ConditionalOnClass`.

**Mục tiêu của tách cấu hình:** một tính năng bị tắt, thiếu dependency hoặc bị ứng dụng thay thế thì các tính năng độc lập khác vẫn có thể hoạt động bình thường.

## 2. Nguyên tắc chia theo chức năng

Thay vì chia theo số lượng dòng code, hãy hỏi: **“Tính năng này có thể được kích hoạt, cấu hình, kiểm thử và thay thế độc lập không?”**

Ví dụ thư viện dùng chung có hai tính năng:
- **Audit:** tạo chuỗi bản ghi nghiệp vụ khi một sự kiện xảy ra.
- **Notification:** tạo thông báo cho sự kiện.

Hai tính năng có API, property và chính sách bật/tắt riêng; do đó hợp lý hơn khi viết:

```text
AuditAutoConfiguration
  -> @ConditionalOnProperty(demo.audit.enabled)
  -> @Bean @ConditionalOnMissingBean(AuditService)

NotificationAutoConfiguration
  -> @ConditionalOnProperty(demo.notification.enabled)
  -> @Bean @ConditionalOnMissingBean(NotificationService)
```

Sau này, nếu có tích hợp metrics thực sự tùy chọn, bạn có thể bổ sung `MetricsAutoConfiguration` có `@ConditionalOnClass` riêng mà không ép Audit và Notification cũng cần thư viện metrics.

### 2.1. Dấu hiệu nên tách

| Dấu hiệu | Vì sao nên tách |
| --- | --- |
| Mỗi nhóm có dependency hoặc classpath condition khác nhau | Thiếu một thư viện tùy chọn không nên làm mất nhóm còn lại |
| Có property enable/disable riêng | Bật/tắt chức năng A không nên thay đổi B |
| Ứng dụng có thể override bean riêng của từng nhóm | `@ConditionalOnMissingBean` nên xét theo hợp đồng cụ thể |
| Có lifecycle hoặc nguồn tài nguyên riêng | Shutdown/initialization/errors cần quản lý theo phụ thuộc thật |
| Có nhóm test riêng, lịch phát hành/tương thích riêng | Lỗi hoặc nâng cấp một adapter dễ được cô lập |
| Một nhóm chỉ chạy trong Servlet/Reactive/Batch context | Web condition không nên bao phủ logic trung tính |
| Một nhóm dùng SDK trả phí hoặc hạ tầng bên ngoài | Tránh vô tình bật integration ngoài mong đợi |

Ngược lại, **đừng tách một logic hoàn toàn đồng nhất thành hàng chục auto-configuration chỉ vì mỗi class đang dài 100 dòng**. Có thể để nhiều `@Bean` thực sự thuộc cùng một tính năng trong một lớp; nếu các phần dùng cùng điều kiện và cùng vòng đời, việc gom lại vẫn dễ hiểu.

### 2.2. Chọn đúng đơn vị phân chia

Một đơn vị thiết kế tốt thường có:
1. Một **trách nhiệm có thể diễn đạt ngắn gọn** (ví dụ “cung cấp audit client mặc định”).
2. Một tập **điều kiện kích hoạt** nhất quán (classpath, property, môi trường chạy).
3. Một **hợp đồng tùy biến** (đổi bean, config property, disable/exclude).
4. Một tập **test độc lập**.
5. Một tập dependency bắt buộc và tùy chọn được xác định rõ.

Trong Spring Boot, một tệp `AutoConfiguration.imports` có thể liệt kê **nhiều** class auto-configuration. Không cần một starter hoặc một imports file mới cho mỗi tính năng nếu chúng cùng thuộc một thư viện; mức chia module phụ thuộc nhu cầu phát hành.

## 3. Hiểu đúng ba cấp tổ chức

Đừng nhầm **feature**, **configuration class** và **artifact**:

| Cấp | Ví dụ | Vai trò |
| --- | --- | --- |
| API/core | `AuditService`, `NotificationService` | Định nghĩa chức năng, có thể tránh phụ thuộc Spring |
| Auto-configuration class | `AuditAutoConfiguration`, `NotificationAutoConfiguration` | Đăng ký bean mặc định có điều kiện cho từng feature |
| Artifact | `example-autoconfigure.jar`, `example-spring-boot-starter.jar` | Đóng gói class/metadata và thuận tiện thêm dependency |

Với một thư viện nhỏ, nhiều auto-configuration classes có thể nằm **chung** trong một artifact `autoconfigure`. Với một SDK lớn, các nhóm độc lập có thể tách artifact, starter hoặc cả repository; quyết định theo cách người dùng tiêu thụ dependency, không theo ý thích có nhiều tệp.

### 3.1. Cấu trúc thường dùng khi xuất bản thư viện

```text
feature-core/
  AuditService.java
  NotificationService.java

feature-autoconfigure/
  AuditAutoConfiguration.java
  NotificationAutoConfiguration.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

feature-spring-boot-starter/
  build.gradle hoặc pom.xml
  (chủ yếu khai báo dependencies)
```

Core chứa hợp đồng và logic độc lập; autoconfigure chỉ nối core vào ApplicationContext khi phù hợp; starter giúp consumer kéo các dependency cần thiết.

**Không mặc định starter luôn cần thiết.** Nếu ứng dụng của bạn chỉ dùng một module nhỏ nội bộ, `@Configuration` thông thường có thể là đủ. Auto-configuration có giá trị nhất khi bạn cung cấp một hành vi mặc định để **nhiều ứng dụng tiêu thụ** mà không phải `@Import` thủ công.

## 4. Cơ chế Spring Boot: tách lớp không làm mất tính tự động

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Cơ chế import của Boot đọc danh sách candidate auto-configurations từ những tệp:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Bạn có thể công bố:

```text
com.example.features.autoconfigure.AuditAutoConfiguration
com.example.features.autoconfigure.NotificationAutoConfiguration
```

Spring Boot lần lượt xét các điều kiện tương ứng của từng configuration class. Danh sách này công bố **configuration candidates**, không phải danh sách các bean chắc chắn sẽ tồn tại.

```text
@EnableAutoConfiguration
        |
        v
AutoConfiguration.imports
        |
        +------ AuditAutoConfiguration
        |          |
        |          +-- audit enabled?
        |          +-- missing AuditService bean?
        |          +-- register default AuditService if eligible
        |
        +------ NotificationAutoConfiguration
                   |
                   +-- notification enabled?
                   +-- missing NotificationService bean?
                   +-- register default NotificationService if eligible
```

Tách thành hai class mang lại khả năng **đánh giá condition ở phạm vi hẹp**. Khi audit bị disable, NotificationAutoConfiguration vẫn được xét bình thường nếu không có dependency giữa hai nhóm.

### 4.1. Không dựa vào component scanning của ứng dụng

Thư viện auto-configuration cần được Boot phát hiện qua imports file; **không đặt `@ComponentScan` bao trùm package ứng dụng và package thư viện** chỉ để làm cấu hình “tự chạy”. Cách đó có thể lôi cả những bean nội bộ/condition không mong muốn vào context, gây khác biệt khi consumer đổi base package.

Trong ví dụ hoàn chỉnh ở phần sau, `DemoApplication` nằm ở `com.example.app`, còn auto-configuration nằm ở `com.example.features.autoconfigure`. Hai nhánh package ngang cấp khiến component scan của ứng dụng không tự nhặt các class autoconfigure; imports file là đường kích hoạt chính.

### 4.2. Vì sao vẫn cần @ConditionalOnMissingBean?

Mỗi feature cần nhường quyền quyết định cho ứng dụng:

```java
@Bean
@ConditionalOnMissingBean(AuditService.class)
AuditService auditService() {
    return event -> "audit:" + event;
}
```

Đây là fragment nằm trong auto-configuration, không phải tệp Java độc lập. Khi ứng dụng đã khai báo bean phù hợp cùng type, Boot không đăng ký bean mặc định tương ứng.

**Sự tách biệt quan trọng:** bean của tính năng A chỉ nên kiểm tra các điều kiện liên quan A. Không dùng một điều kiện “không có bất cứ bean nào của thư viện” để vô tình cấm cả B.

Lưu ý `@ConditionalOnMissingBean` nhìn bean definitions đã được xử lý tới thời điểm condition đánh giá. Auto-configuration được xử lý sau cấu hình ứng dụng trong cơ chế deferred import, phù hợp mô hình back-off. Khi hai auto-configurations **cùng** cạnh tranh một bean type, có thể cần thứ tự rõ ràng; khi chúng tạo hai type độc lập, thường không cần ép thứ tự.

## 5. Demo chạy được: hai auto-configuration độc lập

Phần này dùng một Maven project duy nhất để dễ chạy. Khi phát hành thật có thể tách core/autoconfigure/starter như mục 3. Các file được nêu dưới đây tạo thành một ứng dụng Spring Boot hoàn chỉnh.

### 5.1. Cấu trúc project

```text
feature-split-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── features/
    │   │       ├── AuditService.java
    │   │       ├── NotificationService.java
    │   │       └── autoconfigure/
    │   │           ├── AuditAutoConfiguration.java
    │   │           └── NotificationAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/features/autoconfigure/
            └── FeatureAutoConfigurationTest.java
```

### 5.2. Maven POM

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>feature-split-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

Parent quản lý phiên bản thư viện Spring tương thích với nhánh Boot 3.3; `java.version` đặt ngôn ngữ biên dịch ở Java 17. Cần có JDK 17+ và Maven 3.x.

### 5.3. API thuần Java của từng chức năng

Tạo `src/main/java/com/example/features/AuditService.java`:

```java
package com.example.features;

@FunctionalInterface
public interface AuditService {
    String record(String event);
}
```

Tạo `src/main/java/com/example/features/NotificationService.java`:

```java
package com.example.features;

@FunctionalInterface
public interface NotificationService {
    String send(String message);
}
```

Hai interface độc lập và không import Spring. Cả hai đều chỉ là API nhỏ cho demo, không đại diện cho hệ thống audit hoặc notification production (vốn có thể cần bất đồng bộ, persist, retry, bảo mật và giám sát lỗi).

### 5.4. Cấu hình audit

Tạo `src/main/java/com/example/features/autoconfigure/AuditAutoConfiguration.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService() {
        return event -> "audit:" + event;
    }
}
```

Audit có property riêng `demo.audit.enabled`. Khi key không tồn tại, `matchIfMissing=true` cho phép tạo bean mặc định. Khi key bằng `false`, toàn bộ cấu hình audit bị bỏ qua. Nếu app đã tự tạo `AuditService`, bean audit mặc định nhường chỗ.

### 5.5. Cấu hình notification

Tạo `src/main/java/com/example/features/autoconfigure/NotificationAutoConfiguration.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.NotificationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notification",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationService.class)
    NotificationService notificationService() {
        return message -> "sent:" + message;
    }
}
```

Notification không phụ thuộc audit. Nó không inject `AuditService`, không check `demo.audit.enabled` và không được che bởi điều kiện audit. Hai feature vẫn có thể được cung cấp bởi cùng một starter mà không bị khóa vận hành chung.

### 5.6. Công bố cả hai configuration trong một imports file

Tạo file chính xác ở:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.features.autoconfigure.AuditAutoConfiguration
com.example.features.autoconfigure.NotificationAutoConfiguration
```

Đây là phần bắt buộc cho việc khám phá auto-configuration theo quy ước Spring Boot 3.x. Nếu quên thêm một class vào imports file, class đó có thể compile bình thường nhưng **không được tự động import** trong ứng dụng tiêu thụ.

Đừng khai báo package của thư viện dưới component scan app chỉ để “sửa” lỗi quên imports. Hãy sửa resource registration đúng nguồn.

### 5.7. Ứng dụng nhận hai bean mà không import cấu hình thủ công

Tạo `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.features.AuditService;
import com.example.features.NotificationService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showFeatures(
            ObjectProvider<AuditService> audits,
            ObjectProvider<NotificationService> notifications) {
        return args -> {
            AuditService audit = audits.getIfAvailable();
            NotificationService notification = notifications.getIfAvailable();

            System.out.println(audit == null
                    ? "AUDIT=ABSENT"
                    : "AUDIT=" + audit.record("checkout"));
            System.out.println(notification == null
                    ? "NOTIFY=ABSENT"
                    : "NOTIFY=" + notification.send("checkout"));
        };
    }
}
```

`ObjectProvider` cho phép mỗi feature vắng mặt mà ứng dụng vẫn chạy; như vậy có thể quan sát tác động bật/tắt độc lập. Trong ứng dụng thật, caller sử dụng tính năng nên chọn xử lý rõ trường hợp optional thay vì giả định bean luôn tồn tại.

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Với mặc định cả hai feature bật, **hai dòng do `ApplicationRunner` in ra** là:

```text
AUDIT=audit:checkout
NOTIFY=sent:checkout
```

Maven và Spring Boot còn ghi startup logs; đây không phải toàn bộ stdout.

### 5.8. Tắt một chức năng, giữ chức năng còn lại

Chạy audit disabled:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.audit.enabled=false
```

Dòng output của runner:

```text
AUDIT=ABSENT
NOTIFY=sent:checkout
```

Chạy notification disabled:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.notification.enabled=false
```

Dòng output:

```text
AUDIT=audit:checkout
NOTIFY=ABSENT
```

Kết quả cho thấy một property không kéo theo feature kia. Nếu dùng một `EverythingAutoConfiguration` có class-level `@ConditionalOnProperty(prefix="demo.audit",...)`, điều kiện audit có thể che cả notification — chính là lỗi mô hình mà việc tách lớp giải quyết.

### 5.9. Ứng dụng thay thế riêng bean audit

Bổ sung **vào bên trong `DemoApplication`** method sau:

```java
@Bean
AuditService customAuditService() {
    return event -> "custom-audit:" + event;
}
```

Đây là **fragment thêm vào class**, không phải file Java độc lập. Chạy với mặc định, runner in:

```text
AUDIT=custom-audit:checkout
NOTIFY=sent:checkout
```

Nhờ `@ConditionalOnMissingBean(AuditService.class)`, bean audit mặc định không được tạo, còn notification vẫn giữ cấu hình của mình. Đây là bài kiểm tra quan trọng cho API dùng chung: consumer có thể tùy biến từng phần.

Để tiếp tục các bài test nguyên bản ở mục sau, **chưa thêm method tùy biến**, hoặc xóa nó sau khi thí nghiệm vì test mặc định giả định audit tạo chuỗi `audit:checkout`.

## 6. Kiểm thử độc lập bằng ApplicationContextRunner

Test cần chứng minh tính cô lập, không chỉ chứng minh cả hai bean có mặt khi mặc định.

Tạo `src/test/java/com/example/features/autoconfigure/FeatureAutoConfigurationTest.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.AuditService;
import com.example.features.NotificationService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class,
                            NotificationAutoConfiguration.class));

    @Test
    void bothEnabledByDefault() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditService.class);
            assertThat(context).hasSingleBean(NotificationService.class);
            assertThat(context.getBean(AuditService.class)
                    .record("checkout")).isEqualTo("audit:checkout");
            assertThat(context.getBean(NotificationService.class)
                    .send("checkout")).isEqualTo("sent:checkout");
        });
    }

    @Test
    void disablingAuditLeavesNotification() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditService.class);
                    assertThat(context).hasSingleBean(NotificationService.class);
                });
    }

    @Test
    void disablingNotificationLeavesAudit() {
        runner.withPropertyValues("demo.notification.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(NotificationService.class);
                });
    }

    @Test
    void consumerAuditBeanOnlyOverridesAuditDefault() {
        runner.withUserConfiguration(CustomAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context.getBean(AuditService.class)
                            .record("checkout"))
                            .isEqualTo("custom-audit:checkout");
                    assertThat(context).hasSingleBean(NotificationService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomAuditConfiguration {

        @Bean
        AuditService customAuditService() {
            return event -> "custom-audit:" + event;
        }
    }
}
```

Chạy:

```bash
mvn test
```

Bốn test kiểm tra:
- Mặc định có đủ hai bean;
- Tắt audit chỉ làm mất audit;
- Tắt notification chỉ làm mất notification;
- App override audit mà notification không bị ảnh hưởng.

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` **cấp trực tiếp hai class**, rất phù hợp kiểm thử logic điều kiện. Nó chưa chứng minh file `AutoConfiguration.imports` trong JAR được đóng gói đúng. Để kiểm tra khám phá thực tế, hãy chạy `DemoApplication` hoặc tạo một consumer integration test.

### 6.1. Kiểm tra resource khi đóng gói

Chạy:

```bash
mvn package
jar tf target/feature-split-demo-0.0.1-SNAPSHOT.jar
```

Trong executable JAR do Boot Maven plugin tạo, bạn cần thấy resource dưới:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Còn trong thư viện JAR thông thường, đường dẫn của resource bắt đầu ngay tại `META-INF/spring/...`. Nếu consumer không nhận bean dù các test runner đều pass, kiểm tra metadata khám phá candidate này trước khi nghi ngờ code trong `@Bean`.

## 7. Cách tách khi một số tích hợp là optional

Hai tính năng trong demo đều chỉ dùng API lõi. Trong thư viện thực tế, mỗi feature có thể phụ thuộc SDK bên ngoài khác nhau:

```text
AuditAutoConfiguration
  -> chỉ cần feature-core

MailAutoConfiguration
  -> cần mail API/implementation

MetricsAutoConfiguration
  -> cần Micrometer MeterRegistry

WebServletAutoConfiguration
  -> chỉ chạy trong Servlet application

WebReactiveAutoConfiguration
  -> chỉ chạy trong Reactive application
```

Thiết kế **sai**:

```java
// Minh họa lỗi: thiếu mail SDK có thể chặn cả audit.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
class AllFeaturesAutoConfiguration {
    // tạo audit, metrics, notification, mail...
}
```

Thiết kế đúng phạm vi hơn:

```java
@AutoConfiguration
public class AuditAutoConfiguration {
    // Chỉ các bean audit thuần, điều kiện riêng của audit.
}
```

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
public class MailAutoConfiguration {
    // Chỉ phần tích hợp mail trong module biên dịch với mail SDK.
}
```

**Hai fragment trên chỉ minh họa cấu trúc**, không phải các file Java compile độc lập: method/package/import được lược bỏ và `com.vendor.mail.MailClient` là tên giả định.

Khi tích hợp thực sự optional, nên cân nhắc:

1. Giữ các **API lõi** mà consumer phải dùng không phụ thuộc vào SDK optional.
2. Dùng `@ConditionalOnClass` tại **configuration class** hoặc nested static configuration để tránh JVM phân giải chữ ký `@Bean` chứa optional type quá sớm.
3. Phân biệt compile-only/optional dependency của module autoconfigure với dependency runtime của consumer. Maven `optional=true` ngăn truyền transitive qua cạnh optional; Gradle `compileOnly` không đưa dependency vào runtime từ cạnh đó.
4. Thêm **test classpath vắng mặt** bằng `FilteredClassLoader` để chứng minh thiếu SDK không làm hỏng feature khác.
5. Không đặt tên class SDK optional vào superclass, interface hoặc signature không được bảo vệ của class auto-configuration luôn bị nạp.
6. Quy định rõ feature default-on hay opt-in. Tích hợp có side effect (gửi email, kết nối hệ thống, lịch job) thường nên cân nhắc cấu hình kích hoạt có chủ đích.

### 7.1. Lớp lồng hay auto-configuration riêng?

Có hai cách tách:

**A. Tách thành nhiều `@AutoConfiguration` độc lập**: hợp lý khi tính năng có quyền bật/tắt, dependency, vòng đời và ranh giới public rõ ràng; từng class được liệt kê trong imports.

**B. Một `@AutoConfiguration` chứa nhiều static nested `@Configuration(proxyBeanMethods=false)` được guard riêng**: hợp lý khi đó là **các biến thể triển khai của cùng một feature** có chung hợp đồng API, chẳng hạn client Servlet/Reactive hoặc hai implementation dựa trên classpath.

Mẫu hình B:

```java
@AutoConfiguration
public class DataClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sql.SqlClient")
    static class SqlClientConfiguration {
        // @Bean method chỉ dùng type của SQL SDK.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.nosql.NoSqlClient")
    static class NoSqlClientConfiguration {
        // @Bean method chỉ dùng type của NoSQL SDK.
    }
}
```

Đây là **mã minh họa không độc lập biên dịch**: import và method thật được rút gọn, SDK giả định. Trong hệ thống thật, phải quyết định nếu hai SDK cùng có mặt thì dùng một hay hai bean; có thể cần `@ConditionalOnMissingBean`, property lựa chọn hoặc phân tách auto-configuration.

**Quy tắc chọn:** nếu hai nhánh đại diện cho **hai chức năng công khai độc lập**, ưu tiên hai auto-configurations. Nếu chỉ là **hai cách thực thi của một chức năng**, một auto-configuration với nested configurations có thể sáng sủa hơn.

## 8. Điều kiện và ranh giới cấu hình

Tách lớp chỉ thực sự có ích khi điều kiện cũng được đặt đúng chỗ.

| Condition | Nên đặt ở đâu | Cảnh báo |
| --- | --- | --- |
| `@ConditionalOnClass` | Class auto-configuration của adapter hoặc nested config riêng | Đặt trên class quá rộng có thể làm mất feature độc lập khác |
| `@ConditionalOnProperty` | Class feature nếu cả feature cùng bật/tắt; method nếu chỉ một bean optional | Cần tài liệu cho giá trị mặc định và trường hợp property thiếu |
| `@ConditionalOnMissingBean` | Bean mặc định của feature, theo type/name/hợp đồng phù hợp | Không gom mọi feature vào cùng một điều kiện “missing” |
| `@ConditionalOnBean` | Tích hợp thực sự yêu cầu bean hiện hữu | Đừng tạo dependency giả giữa hai feature độc lập |
| `@ConditionalOnWebApplication` | Config chỉ có ý nghĩa trong web context | Tách Servlet/Reactive khi API hoặc điều kiện khác nhau |
| `@ConditionalOnResource` | Feature thực sự yêu cầu resource tương ứng | Kiểm tra deployment thật có resource không |

### 8.1. Property key nên được đặt tên theo feature

Nên dùng namespace riêng:

```properties
demo.audit.enabled=true
demo.notification.enabled=false
demo.metrics.enabled=false
```

Điều này cho phép consumer chỉnh từng nhánh; tài liệu cấu hình không phải liệt kê một biến `demo.enabled` chi phối tất cả ngoài ý muốn.

Nếu một feature có nhiều tham số hơn enable flag, có thể tạo một lớp `@ConfigurationProperties(prefix = "demo.audit")` cho riêng feature đó, đăng ký qua `@EnableConfigurationProperties` hoặc cơ chế tương ứng. Không nên dùng một class properties khổng lồ chứa mọi secret, retry, endpoint và mode của mọi adapter nếu chúng vận hành độc lập.

### 8.2. Khi nào cần thứ tự auto-configuration?

Với hai feature không có phụ thuộc, đừng khai báo quan hệ thứ tự tùy tiện. Nếu `NotificationAutoConfiguration` thật sự phụ thuộc bean mà `AuditAutoConfiguration` tạo, xem lại kiến trúc: quan hệ đó có phải bắt buộc về nghiệp vụ không? Nếu có, mới cân nhắc `@AutoConfiguration(after = AuditAutoConfiguration.class)` hoặc điều kiện `@ConditionalOnBean` thích hợp.

`@AutoConfiguration(before/after)` chi phối thứ tự **áp dụng auto-configuration/đăng ký bean definitions**, không bảo đảm thứ tự instance initialization. Thứ tự tạo bean phụ thuộc dependency injection và Spring lifecycle.

Nếu hai auto-configurations đều `@ConditionalOnMissingBean(SomeClient.class)` và muốn cung cấp fallback khác nhau, quan hệ before/after có thể ảnh hưởng ai tạo bean mặc định. Nên thiết kế một cấu hình ưu tiên rõ ràng, test các tổ hợp có/không có bean do app cấp.

## 9. Khi nhiều auto-configuration dùng chung một tài nguyên

Một số thư viện có phần chung như HTTP transport, connection pool, credential provider. Tách feature **không có nghĩa nhân đôi tài nguyên**.

Cấu trúc phù hợp có thể là:

```text
TransportAutoConfiguration
  -> cung cấp Transport mặc định (nếu cần, nếu chưa có bean)

AuditAutoConfiguration
  -> sử dụng Transport khi feature audit thật sự cần

NotificationAutoConfiguration
  -> sử dụng Transport khi feature notification thật sự cần
```

Các feature cùng inject một `Transport` được quản lý ở context, thay vì mỗi feature tạo một pool hoặc socket khác. Nhưng cần tránh một vấn đề đối nghịch: nếu `TransportAutoConfiguration` luôn khởi tạo kết nối ngay cả khi tất cả feature đều tắt, người dùng vẫn trả chi phí startup và tài nguyên không cần thiết.

Cần quyết định rõ:
- Transport luôn là thành phần công khai của starter hay chỉ được tạo khi ít nhất một feature cần?
- Các consumer có thể tự cung cấp transport bean không?
- Có cần lazy initialization, condition trên bean, hay đăng ký từng nhánh theo feature?
- Đóng transport ở đâu và có vô tình đóng hai lần nếu chia sẻ instance không?
- Lỗi kết nối của một adapter có nên làm toàn ứng dụng fail fast hay degrade theo policy?

Câu trả lời phụ thuộc hợp đồng thư viện. Đặc biệt, **không dùng `@ConditionalOnBean` tùy tiện để chặn tính năng vì một bean phụ thuộc được đăng ký sau**; điều kiện bean phụ thuộc thứ tự xử lý definitions.

## 10. Từ monolith sang nhiều auto-configuration: quy trình chuyển đổi

Giả sử trước đây có:

```text
EverythingAutoConfiguration
  -> audit bean
  -> notification bean
  -> metrics bean
  -> vendor bean
```

Quy trình thay đổi nên diễn ra theo các bước rõ ràng:

### Bước 1. Chốt hợp đồng hiện tại

Ghi lại các public bean types/names, property keys, chế độ enable mặc định, behavior khi SDK optional vắng mặt, thứ tự/condition thực tế, đường đăng ký imports và cách ứng dụng override bean.

Nếu người tiêu thụ đã exclude một auto-configuration cũ bằng FQCN, việc đổi class name có thể làm cơ chế loại trừ của họ thay đổi. Đây là thay đổi tương thích API cấu hình, cần được xem như thay đổi có thể ảnh hưởng consumer.

### Bước 2. Xác định các ranh giới chức năng

Lập bảng từng nhóm:

| Nhóm | Dependency | Flag | Default bean | Consumer override |
| --- | --- | --- | --- | --- |
| Audit | core | `demo.audit.enabled` | `AuditService` | `@Bean AuditService` |
| Notification | core | `demo.notification.enabled` | `NotificationService` | `@Bean NotificationService` |
| Metrics | Micrometer optional | `demo.metrics.enabled` | adapter/bridge | bean tương ứng |
| Vendor | SDK optional | `demo.vendor.enabled` | client adapter | client/adapter riêng |

Tính năng nào chỉ là helper nội bộ có thể giữ trong package/private configuration của nhóm tương ứng, không nhất thiết phải trở thành public auto-configuration candidate.

### Bước 3. Chuyển các bean vào lớp đúng trách nhiệm

Tạo mỗi `@AutoConfiguration` có tên và mục tiêu rõ ràng. Đặt class-level conditions chung cho feature; đặt method-level conditions cho bean có ngoại lệ. Kiểm tra các dependency injection không cần thiết giữa feature groups; loại bỏ các field/static initializer có tác dụng phụ trong class cấu hình.

### Bước 4. Cập nhật AutoConfiguration.imports

Công bố từng candidate mới theo tên đầy đủ. **Tránh đồng thời công bố lớp monolith cũ và các lớp mới nếu cả hai còn đăng ký cùng bean**, trừ khi đã có một cơ chế tương thích được thiết kế/test rõ ràng.

Nếu thay tên auto-configuration đã phát hành, Spring Boot có hỗ trợ metadata `AutoConfiguration.replacements` để biểu diễn đổi tên cấu hình cho một số mục đích như exclusions/ordering. Tuy vậy, **tách một class cũ thành nhiều class mới không phải ánh xạ đổi tên 1:1 đơn giản**: phải thiết kế chính sách migration cho từng exclusion và bean, kiểm tra tài liệu phiên bản và test consumer. Không giả định một dòng rename sẽ bảo toàn toàn bộ behavior của monolith khi đổi thành nhiều feature độc lập.

### Bước 5. Viết test ma trận

Đừng chỉ chạy mặc định. Tối thiểu kiểm thử:
- Cả hai feature bật mặc định;
- Tắt A thì B còn, tắt B thì A còn;
- Tắt cả hai thì không còn default beans;
- Consumer tự tạo bean A thì B không đổi;
- SDK optional của C vắng mặt vẫn không làm A/B lỗi;
- Exclude một auto-configuration class mới chỉ ảnh hưởng feature đó;
- Imports/resource đóng gói đầy đủ;
- Upgrade từ version cũ không làm đổi public property/bean names ngoài kế hoạch.

### Bước 6. Kiểm tra consumer ứng dụng thật

`ApplicationContextRunner` cho feedback nhanh về bean conditions, nhưng test gán trực tiếp `AutoConfigurations.of(...)` **không chứng minh** candidate discovery từ imports. Dùng thêm một integration test khởi động ứng dụng tiêu thụ hoặc inspect JAR packaging, để bắt lỗi thiếu resource hoặc sai FQCN.

### Bước 7. Xóa đường đăng ký cũ đã hết tác dụng

Sau khi consumer compatibility đã rõ, bỏ đường import/scan cũ, các method trùng và điều kiện toàn cục vô tình chi phối mọi feature. Giữ một đường đăng ký chuẩn để tránh bean definition conflict.

## 11. Những gì cần kiểm tra sau khi chia cấu hình

### 11.1. Condition report

Khi chạy demo hoặc consumer, bật report:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Ở báo cáo điều kiện, tìm từng class:
- `AuditAutoConfiguration` có khớp điều kiện audit không?
- `NotificationAutoConfiguration` có khớp điều kiện notification không?
- Có bean riêng khiến `@ConditionalOnMissingBean` back off không?
- Candidate có bị loại khỏi danh sách trước khi được xử lý không?

Dùng `--debug` cho điều tra. Report có thể có nhiều cấu hình không liên quan từ dependency khác; không nên dựa vào một mẩu log chung chung để suy ra nguyên nhân.

### 11.2. Bài kiểm tra đóng gói

Ví dụ Maven:

```bash
mvn package
jar tf target/feature-split-demo-0.0.1-SNAPSHOT.jar
```

Tìm resource imports và cả hai `.class` tương ứng trong JAR. Khi tách artifact autoconfigure, kiểm tra imports nằm trong chính JAR cung cấp các class cấu hình.

### 11.3. Không có startup side effect bất ngờ

Tách lớp không giải quyết được lỗi khi factory method tự kết nối network, thực thi migration hoặc gửi thông báo không kiểm soát. Với từng feature, kiểm tra:
- Khi feature tắt, có bean/client nào còn khởi tạo không?
- Khi SDK optional thiếu, class chứa type đó có bị JVM tải sớm không?
- Khi app override bean, default adapter có ngừng được tạo không?
- Khi có lỗi cấu hình, message có chỉ rõ feature và property liên quan không?
- Khi teardown, tài nguyên được đóng đúng theo quyền sở hữu không?

### 11.4. Đặt tên và phạm vi public API

Tên `AuditAutoConfiguration` có nghĩa khi đọc condition report. Tránh `UtilsAutoConfiguration`, `EverythingAutoConfiguration` hoặc tên chỉ phản ánh vị trí thư mục thay vì hành vi.

Trong code thư viện, các bean/helper chỉ phục vụ cấu hình nội bộ nên giữ package và visibility tối thiểu phù hợp. Tránh để class auto-configuration bị component scan của ứng dụng nhận nhầm. Quan trọng nhất là **hợp đồng public mà consumer nhìn thấy** (bean type/name, properties, feature flag, cách exclude) phải ổn định hoặc có migration rõ.

## 12. Khi nào không cần tách thành nhiều AutoConfiguration?

**Trường hợp 1 — một feature gồm nhiều bean gắn bó:** Một HTTP client có builder, codec và interceptor cùng bật/tắt, cùng classpath và cùng vòng đời. Có thể giữ chúng trong một `HttpClientAutoConfiguration`, chia method hoặc nested configuration để code rõ hơn.

**Trường hợp 2 — chỉ khác cách triển khai:** Một feature hỗ trợ hai implementation cho cùng API (ví dụ JSON A/JSON B) nhưng người dùng chỉ chọn một. Có thể dùng nested `@Configuration` có điều kiện bên trong một auto-configuration, thay vì tạo hai public features độc lập.

**Trường hợp 3 — cấu hình không tái sử dụng ngoài ứng dụng:** Nếu code chỉ thuộc một ứng dụng, `@Configuration` / `@Bean` nội bộ thường đã đủ. Không bắt buộc làm starter hoặc imports file chỉ để có nhiều class.

**Trường hợp 4 — tách tạo dependency cycle:** Nếu mỗi cấu hình phải inject bean từ cấu hình kia mới chạy được, hãy làm rõ ranh giới nghiệp vụ và kéo phần chung về một API/service chung, hoặc xem có thật sự là hai feature không. Không nên bẻ cấu trúc bằng thứ tự `@AutoConfiguration(after=...)` tùy tiện để che lỗi vòng phụ thuộc.

## 13. Các lỗi điển hình và hướng sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Một class-level `@ConditionalOnClass` của vendor bọc mọi feature | Thiếu vendor SDK làm cả feature không liên quan biến mất | Chuyển điều kiện sang cấu hình adapter vendor |
| Chỉ một flag `library.enabled` điều khiển mọi feature | Consumer khó tắt riêng chức năng tốn tài nguyên | Đặt flag theo feature, chỉ dùng global flag khi có yêu cầu thật |
| Dùng một `@ConditionalOnMissingBean` chung cho nhiều type | Có bean A làm B không được tạo ngoài ý muốn | Mỗi default bean có condition theo hợp đồng type phù hợp |
| Dùng `@ComponentScan` cho package thư viện | Bean được quét ngoài vòng imports/condition | Công bố auto-configuration bằng imports |
| Không khai báo class mới trong `AutoConfiguration.imports` | Class compile nhưng consumer không thấy default bean | Sửa resource đúng tên đầy đủ |
| Công bố class monolith cũ và class mới cùng đăng ký một bean | Trùng bean, order-dependent back-off hoặc xung đột | Chỉ giữ một đường đăng ký hoặc migration kiểm soát |
| Tự tạo transport/pool cho mọi feature | Tốn tài nguyên, duplicate connection, khó đóng | Chia sẻ bean hạ tầng có quyền sở hữu rõ |
| Đặt optional SDK type ở signature config luôn load | Thiếu SDK có thể gây lỗi linkage trước khi condition chạy | Guard ở class-level/nested configuration |
| Ép thứ tự giữa hai nhóm độc lập | Tạo coupling vô nghĩa, khó nâng cấp | Chỉ khai báo before/after cho dependency thật |
| Test mặc định pass rồi dừng | Không thấy lỗi khi disable/override/missing class | Thêm test ma trận điều kiện và consumer integration |
| Đổi tên cấu hình mà không xét exclusions cũ | Consumer upgrade có behavior khác | Lập compatibility plan, dùng metadata migration khi phù hợp |
| Tách một nhóm nhỏ thành quá nhiều candidates | Khó tìm feature, tốn công quản trị docs/tests | Gộp các bean cùng hợp đồng kích hoạt trong một feature config |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Audit và notification dùng chung starter nhưng có hai property flag khác nhau. `demo.audit.enabled=false` có làm notification mất không?

**Đáp án:** Không, nếu condition của notification chỉ phụ thuộc chính feature đó và không có dependency nghiệp vụ bắt buộc vào audit. Đây là lợi ích chính của tách auto-configuration.

**Câu 2.** Lớp `EverythingAutoConfiguration` có `@ConditionalOnClass(OptionalMetrics.class)`; trong đó có cả audit bean thuần Java. Nếu Metrics SDK không nằm trên classpath thì sao?

**Đáp án:** Điều kiện class-level không match, nên toàn bộ lớp auto-configuration không được áp dụng, gồm cả audit. Hãy chuyển metrics integration sang configuration riêng được bảo vệ theo classpath.

**Câu 3.** Vì sao cùng một `AutoConfiguration.imports` có thể khai báo nhiều class?

**Đáp án:** Imports file là danh sách candidate class names, không phải “một tệp cho một feature” hay “một JAR chỉ có một auto-configuration”. Một artifact có thể công bố nhiều auto-configurations độc lập.

**Câu 4.** Khi consumer tự tạo `AuditService`, có cần tắt cả audit để không còn duplicate bean không?

**Đáp án:** Thường không. Nếu default bean có `@ConditionalOnMissingBean(AuditService.class)`, nó sẽ nhường chỗ cho bean consumer; notification không bị ảnh hưởng.

**Câu 5.** Có nên dùng `@AutoConfiguration(after = AuditAutoConfiguration.class)` cho Notification chỉ vì tên class Notification đứng sau Audit trong danh sách imports?

**Đáp án:** Không. Thứ tự chỉ nên diễn đạt dependency thật hoặc quy tắc ưu tiên, không được dùng như hình thức sắp xếp tệp.

**Câu 6.** Test `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` chứng minh điều gì và chưa chứng minh điều gì?

**Đáp án:** Nó kiểm tra cấu hình bean/conditions với các class được chỉ định, nhưng chưa kiểm tra phần discovery qua resource imports trong artifact cuối. Cần thử ứng dụng consumer hoặc JAR packaging.

**Câu 7.** Có nên làm một auto-configuration riêng cho mọi `@Bean` không?

**Đáp án:** Không. Nên chia theo **tính năng và hợp đồng kích hoạt**. Nhiều bean thực sự là một phần của một feature có thể cùng nằm trong một auto-configuration.

## 15. Ghi nhớ và tài liệu tra cứu

Tách cấu hình tốt nghĩa là **chia đúng theo chức năng mà người tiêu thụ có quyền điều khiển độc lập**. Mỗi feature nên có điều kiện classpath/property riêng, default bean có back-off, test độc lập, diagnostics rõ và tên trong imports chính xác. Không có quy tắc bắt buộc mỗi class chỉ một `@Bean` hay mỗi starter chỉ một auto-configuration.

Mẫu tư duy cần nhớ:

```text
Tính năng A -> điều kiện A -> bean mặc định A
Tính năng B -> điều kiện B -> bean mặc định B
Tính năng C -> SDK optional C -> condition C -> bean C

Một nhóm bị tắt / thiếu SDK / custom bean
              |
              v
      Các nhóm độc lập còn hoạt động
```

**Tài liệu chính thức:**

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Condition Annotations: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Javadoc — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
