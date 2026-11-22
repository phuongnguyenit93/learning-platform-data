# spring-boot-autoconfigure-processor và spring-autoconfigure-metadata.properties

> **Mục tiêu:** Hiểu cách Spring Boot dùng annotation processor trong lúc biên dịch để tạo file `META-INF/spring-autoconfigure-metadata.properties`, nhờ đó lọc sớm một số auto-configuration không thể áp dụng. Bài học tập trung vào artifact `spring-boot-autoconfigure-processor`, cách cấu hình Maven/Gradle, nội dung metadata được tạo, cách Boot sử dụng nó và cách kiểm tra file trong JAR phát hành.

Nội dung theo Spring Boot 3.3.x, dùng Java 17+. Đây là metadata phục vụ **tối ưu quá trình xử lý auto-configuration**. Nó khác với metadata của `@ConfigurationProperties` dùng cho IDE gợi ý khóa cấu hình; hai loại có processor, mục tiêu và tên file khác nhau.

## 1. Vì sao Spring Boot cần metadata cho auto-configuration?

Một ứng dụng Spring Boot có thể nhận hàng trăm auto-configuration từ các starter trên classpath. Nhiều cấu hình sẽ không bao giờ được áp dụng vì thiếu thư viện tùy chọn, sai loại ứng dụng hoặc không thỏa điều kiện cần thiết.

Nếu Boot phải tải và phân tích từng class auto-configuration trước khi biết class đó không thể dùng, startup sẽ phải thực hiện thêm công việc. Spring Boot cung cấp `spring-boot-autoconfigure-processor` để đọc trước một số annotation trong **giai đoạn compile**, sau đó ghi các thông tin có thể dùng để lọc sớm vào:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Khi ứng dụng khởi động, Boot có thể đọc metadata này và loại sớm những auto-configuration không phù hợp. Những class còn lại tiếp tục đi qua quy trình xử lý cấu hình và condition thông thường.

Có thể hình dung hai giai đoạn:

~~~text
BUILD / COMPILE
AutoConfiguration source
        |
        v
spring-boot-autoconfigure-processor
        |
        v
META-INF/spring-autoconfigure-metadata.properties
        |
        v
Đóng gói metadata vào autoconfigure JAR

RUNTIME / APPLICATION STARTUP
AutoConfiguration.imports
        |
        v
Tập candidate auto-configuration
        |
        v
Đọc metadata để lọc sớm candidate không phù hợp
        |
        v
Phân tích các candidate còn lại
        |
        v
Đánh giá đầy đủ các @Conditional
        |
        v
Đăng ký bean definition và tạo bean
~~~

Đây là cơ chế tối ưu startup. Metadata không tạo bean, không thay thế imports file và không thay thế việc đánh giá condition ở runtime.

## 2. Hai thành phần phải phân biệt

### 2.1. Annotation processor

Artifact cần cấu hình là:

~~~text
org.springframework.boot:spring-boot-autoconfigure-processor
~~~

Processor chạy trong lúc Java compiler xử lý source code của module chứa auto-configuration. Nó đọc metadata của các annotation mà nó hỗ trợ, trích xuất những giá trị phù hợp và ghi file properties vào output của lần compile.

Processor này thường chỉ cần trong **module autoconfigure** của thư viện. Nếu dự án tách thành:

~~~text
acme/
├── acme-autoconfigure/
│   ├── AutoConfiguration classes
│   └── META-INF/spring/...
└── acme-starter/
    └── dependency declarations
~~~

thì cấu hình annotation processor ở `acme-autoconfigure`, nơi source auto-configuration thực sự được biên dịch. Starter chỉ tập hợp dependency cho ứng dụng tiêu thụ; không cần thêm processor vào module starter nếu module đó không chứa các class auto-configuration.

### 2.2. File metadata được tạo

Đường dẫn chính xác:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Đây là file **được sinh ra**, không phải file mà người phát triển cần tự viết từng dòng. Với Maven, output thường nằm tại:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

Với Gradle Java plugin, file thường nằm trong output classes của source set main:

~~~text
build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties
~~~

Khi đóng gói JAR, resource phải xuất hiện tại đúng đường dẫn `META-INF/` ở bên trong JAR. Không đặt file này dưới `META-INF/spring/`; thư mục đó được dùng cho các resource khác như `AutoConfiguration.imports`.

## 3. Processor ghi những thông tin gì?

Processor chỉ thu thập **một tập con có chọn lọc** của metadata auto-configuration. Các thông tin thường được ghi gồm:

- Điều kiện classpath bằng `@ConditionalOnClass`.
- Điều kiện bean bằng `@ConditionalOnBean`.
- Điều kiện single-candidate bằng `@ConditionalOnSingleCandidate`.
- Kiểu ứng dụng bằng `@ConditionalOnWebApplication`.
- Thứ tự cấu hình qua `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder`.
- Thứ tự tương ứng được khai báo trực tiếp qua các thuộc tính `before`, `beforeName`, `after`, `afterName` của `@AutoConfiguration`.

**Không giả định mọi annotation `@Conditional` đều có bản ghi trong file này.** Ví dụ `@ConditionalOnMissingBean` và `@ConditionalOnProperty` vẫn được đánh giá bởi cơ chế condition thông thường khi cấu hình được xử lý; không nên trông đợi processor tạo một dòng metadata tương ứng cho mọi annotation đó.

| Annotation/nhóm | Vai trò của processor metadata | Khi nào vẫn được đánh giá? |
| --- | --- | --- |
| `@ConditionalOnClass` | Ghi tên class cần kiểm tra để hỗ trợ lọc sớm | Condition vẫn có ý nghĩa trong quy trình xử lý cấu hình |
| `@ConditionalOnBean` | Có thể ghi type bean cần có để hỗ trợ lọc candidate | Khi Boot đánh giá condition của cấu hình |
| `@ConditionalOnSingleCandidate` | Ghi thông tin type cần xét | Trong quy trình condition tương ứng |
| `@ConditionalOnWebApplication` | Ghi kiểu ứng dụng yêu cầu | Khi Boot xác định loại application context |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Ghi quan hệ thứ tự | Khi Boot sắp xếp auto-configuration |
| `@AutoConfigureOrder` | Ghi thứ tự ưu tiên | Khi Boot sắp xếp auto-configuration |
| `@ConditionalOnMissingBean` | Không dựa vào file metadata này để thay thế condition | Khi bean definitions đã được xử lý tới thời điểm đánh giá |
| `@ConditionalOnProperty` | Không phải mọi property condition đều được đưa vào metadata này | Khi Boot đánh giá property từ Environment |
| `@ConditionalOnResource` / `@ConditionalOnExpression` | Không nên giả định processor lưu đầy đủ các biểu thức này | Khi condition tương ứng chạy ở runtime |

Điểm cần nhớ: file metadata **không phải bản sao đầy đủ của annotation trên class**. Nó chứa thông tin mà Boot có thể sử dụng cho các bước tối ưu hoặc sắp xếp trước khi đánh giá đầy đủ cấu hình.

## 4. Hình dạng của file properties

Ví dụ một auto-configuration:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
@ConditionalOnClass(AuditClient.class)
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new AuditService("auto");
    }
}
~~~

Giả sử processor nhận diện class và các metadata được hỗ trợ, file sinh ra có thể có hình dạng minh họa:

~~~properties
com.acme.audit.autoconfigure.AuditAutoConfiguration=
com.acme.audit.autoconfigure.AuditAutoConfiguration.ConditionalOnClass=com.acme.audit.AuditClient
com.acme.audit.autoconfigure.AuditAutoConfiguration.AutoConfigureAfter=com.acme.core.autoconfigure.CoreAutoConfiguration
~~~

Đây là **ví dụ minh họa cấu trúc**, không phải nội dung output cố định cho mọi source. Processor ghi tên class làm key và thêm các key theo loại metadata mà nó hỗ trợ. Các giá trị nhiều phần tử có thể được biểu diễn dưới dạng danh sách phân cách bằng dấu phẩy.

Trong ví dụ trên:

- `ConditionalOnClass` được ghi vì đây là loại condition processor hỗ trợ.
- `AutoConfigureAfter` phản ánh thuộc tính `afterName` trên `@AutoConfiguration`.
- `ConditionalOnProperty` không được đưa vào ví dụ metadata; nó vẫn được đọc từ annotation và đánh giá khi Boot xử lý condition.
- `ConditionalOnMissingBean` cũng không được thay thế bằng metadata này; Boot vẫn cần xét bean definitions thực tế.

Không tự sửa hoặc chép file properties minh họa vào source resources. Hãy để compiler processor tạo file dựa trên source thật của module.

## 5. Cấu hình với Maven

Với Maven, dùng `maven-compiler-plugin` phiên bản 3.12.0 trở lên và khai báo processor trong `annotationProcessorPaths`. Ví dụ sau dùng Java 17 và Spring Boot 3.3.13:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-boot.version>${spring-boot.version}</spring-boot.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
        <version>${spring-boot.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Các điểm cần chú ý:

1. `spring-boot-autoconfigure-processor` nằm trong `annotationProcessorPaths`, vì đây là dependency dành cho compile-time annotation processing.
2. Version processor nên khớp với Spring Boot version mà module sử dụng.
3. Dùng compiler plugin đủ mới theo hướng dẫn Spring Boot 3.3.
4. Nếu dự án đã dùng Lombok hoặc annotation processor khác, thêm các processor cần thiết vào cùng `annotationProcessorPaths`. Khi cấu hình processor path riêng, đừng vô tình bỏ mất processor đang dùng.
5. Đặt cấu hình trong module có source `@AutoConfiguration`, không chỉ trong module starter tập hợp dependency.

Nếu dự án dùng Spring Boot parent/BOM, có thể kế thừa version đã quản lý thay vì lặp lại version ở nhiều chỗ; điều quan trọng là processor và các artifact Boot phải tương thích cùng dòng release.

Chạy compile sạch:

~~~bash
mvn clean compile
~~~

Sau compile, kiểm tra:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

Sau khi package, metadata phải nằm trong JAR phát hành.

## 6. Cấu hình với Gradle

Với Gradle Java plugin, khai báo processor ở configuration `annotationProcessor`:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13'

    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

`annotationProcessor` là configuration chuyên dụng cho các processor được gọi trong compile task. Không khai báo processor như dependency runtime chỉ để mong nó tự chạy.

Chạy compile sạch:

~~~bash
./gradlew clean compileJava
~~~

Kiểm tra output classes:

~~~text
build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties
~~~

Đường dẫn cụ thể có thể thay đổi nếu dự án tùy chỉnh source set hoặc output directory. Cách xác nhận chắc chắn nhất là kiểm tra artifact JAR sau khi build.

## 7. Phân biệt hai loại processor và hai file metadata

Đây là điểm dễ nhầm nhất khi phát triển starter. Spring Boot có hai processor khác nhau với mục tiêu khác nhau:

| Nội dung | Auto-configuration metadata | Configuration properties metadata |
| --- | --- | --- |
| Processor | `spring-boot-autoconfigure-processor` | `spring-boot-configuration-processor` |
| File được tạo | `META-INF/spring-autoconfigure-metadata.properties` | `META-INF/spring-configuration-metadata.json` |
| Dữ liệu chính | Một số condition và thông tin thứ tự của auto-configuration | Tên property, kiểu dữ liệu, description, default value và hint |
| Mục tiêu | Hỗ trợ Boot lọc sớm và sắp xếp auto-configuration | Hỗ trợ IDE autocomplete, documentation và gợi ý cấu hình |
| Thời điểm chạy | Java compile | Java compile |
| Annotation liên quan | `@AutoConfiguration` và các condition/order được hỗ trợ | `@ConfigurationProperties` và các thành phần metadata cấu hình |

Ví dụ một thư viện có:

~~~java
@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    /**
     * Whether audit integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Timeout for the audit request.
     */
    private Duration timeout = Duration.ofSeconds(3);

    // Getters and setters
}
~~~

`spring-boot-configuration-processor` giúp tạo metadata để IDE có thể gợi ý `acme.audit.enabled` và `acme.audit.timeout`. Processor đó **không thay thế** `spring-boot-autoconfigure-processor`.

Một module có thể cần cả hai processor nếu vừa cung cấp auto-configuration vừa công bố các khóa `@ConfigurationProperties`:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'
}
~~~

Hai file được tạo phục vụ hai nhu cầu khác nhau; đừng nhầm tên hoặc chỉ kiểm tra một file rồi kết luận cả hai loại metadata đã được sinh.

## 8. Metadata được sử dụng ở runtime như thế nào?

Khi ứng dụng chạy, `@EnableAutoConfiguration` tìm danh sách auto-configuration candidates thông qua resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Sau khi có danh sách candidate, Boot có thể đọc `spring-autoconfigure-metadata.properties` để các filter kiểm tra nhanh một số điều kiện mà không cần phân tích đầy đủ từng class ngay từ đầu.

Ví dụ, một auto-configuration yêu cầu `com.acme.audit.AuditClient` trên classpath. Nếu class đó không có, metadata cung cấp tên class để filter loại candidate sớm. Candidate bị loại sẽ không cần đi qua các bước xử lý sâu hơn của cấu hình đó.

Các candidate còn lại vẫn được Spring xử lý bình thường:

- Class-level condition được đánh giá theo môi trường và classpath thực tế.
- Bean condition kiểm tra các bean definitions đã được xử lý tới thời điểm đó.
- Property condition đọc giá trị từ `Environment`.
- Các method `@Bean` có condition riêng được xét khi cấu hình được xử lý.
- Sau khi bean definition được đăng ký, Spring mới tạo object theo dependency graph.

**Metadata không quyết định thay runtime condition.** Nó chỉ giúp Boot bỏ qua sớm những candidate mà metadata cho phép xác định chắc chắn là không phù hợp. Điều kiện cần phụ thuộc trạng thái thực tế của context vẫn phải được đánh giá trong quá trình khởi động.

Nếu file metadata không có mặt, Boot vẫn có thể xử lý auto-configuration bằng cách đọc class metadata và đánh giá condition theo quy trình thông thường. Hệ quả chủ yếu là mất bước tối ưu lọc sớm; không có nghĩa ứng dụng phải thất bại chỉ vì thiếu file này.

## 9. Hai resource không thể thay thế nhau

Một module autoconfigure thường có cả hai resource sau:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

và file metadata được sinh trong output compile:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Vai trò:

- `AutoConfiguration.imports` **đăng ký candidate** để Boot biết class nào cần xem xét.
- `spring-autoconfigure-metadata.properties` **hỗ trợ lọc/sắp xếp candidate** bằng thông tin được thu thập trước lúc chạy.

Nếu chỉ có metadata nhưng không có imports resource, file metadata không tự biến class thành candidate. Nếu có imports resource nhưng không có metadata, Boot vẫn có thể tìm thấy và xử lý candidate, chỉ mất tối ưu metadata tương ứng.

Không ghi danh sách class auto-configuration vào `spring-autoconfigure-metadata.properties`; danh sách discovery thuộc imports file.

## 10. Kiểm tra metadata đã được tạo và đóng gói

### 10.1. Kiểm tra sau compile

Với Maven:

~~~bash
mvn clean compile
~~~

Kiểm tra file:

~~~powershell
Test-Path "target/classes/META-INF/spring-autoconfigure-metadata.properties"
Get-Content "target/classes/META-INF/spring-autoconfigure-metadata.properties"
~~~

Với Gradle:

~~~bash
./gradlew clean compileJava
~~~

Kiểm tra file:

~~~powershell
Test-Path "build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties"
Get-Content "build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties"
~~~

Nếu dự án dùng source set/output tùy chỉnh, điều chỉnh đường dẫn theo output của source set main.

### 10.2. Kiểm tra JAR phát hành

Với Maven:

~~~bash
mvn clean package
~~~

Liệt kê nội dung JAR:

~~~powershell
jar tf target/acme-audit-autoconfigure-1.0.0.jar |
    Select-String "spring-autoconfigure-metadata.properties"
~~~

Để đọc nội dung bên trong JAR:

~~~powershell
jar xf target/acme-audit-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content "META-INF/spring-autoconfigure-metadata.properties"
~~~

Trong output, phải có:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Đồng thời kiểm tra riêng imports resource:

~~~powershell
jar tf target/acme-audit-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

Hai kiểm tra này xác nhận hai resource độc lập đã được đóng gói. Việc JAR chứa metadata không chứng minh các condition đều đúng; hãy kiểm thử runtime condition riêng.

## 11. Ví dụ hoàn chỉnh để kiểm thử auto-configuration

Ví dụ sau mô phỏng một thư viện audit. Nó dùng `@ConditionalOnClass` để chỉ áp dụng khi marker class có mặt, `@ConditionalOnProperty` để bật/tắt integration, và `@ConditionalOnMissingBean` để cho ứng dụng thay default.

### 11.1. Marker class và service

**`src/main/java/com/acme/audit/AuditClient.java`**

~~~java
package com.acme.audit;

public final class AuditClient {
}
~~~

**`src/main/java/com/acme/audit/AuditService.java`**

~~~java
package com.acme.audit;

public record AuditService(String source) {
}
~~~

### 11.2. Auto-configuration

**`src/main/java/com/acme/audit/autoconfigure/AuditAutoConfiguration.java`**

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
@ConditionalOnClass(AuditClient.class)
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new AuditService("auto");
    }
}
~~~

Trong class này, processor có thể tạo metadata cho `@ConditionalOnClass` và quan hệ thứ tự. `@ConditionalOnProperty` và `@ConditionalOnMissingBean` vẫn được đánh giá bởi condition runtime.

### 11.3. Imports resource

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Đây là resource discovery cần có khi JAR được ứng dụng tiêu thụ dùng qua `@EnableAutoConfiguration`. Metadata properties không thay thế resource này.

### 11.4. Kiểm thử với ApplicationContextRunner

**`src/test/java/com/acme/audit/autoconfigure/AuditAutoConfigurationTests.java`**

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void defaultServiceIsCreatedWhenConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AuditService.class);
            assertThat(context.getBean(AuditService.class).source())
                    .isEqualTo("auto");
        });
    }

    @Test
    void disabledPropertySkipsAutoConfiguration() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context.getBean(AuditService.class).source())
                            .isEqualTo("user");
                    assertThat(context).doesNotHaveBean("auditService");
                });
    }

    @Test
    void missingOptionalClientSkipsAutoConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditService customAuditService() {
            return new AuditService("user");
        }
    }
}
~~~

Dependency test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Chạy:

~~~bash
mvn -Dtest=AuditAutoConfigurationTests test
~~~

Hoặc:

~~~bash
./gradlew test --tests com.acme.audit.autoconfigure.AuditAutoConfigurationTests
~~~

**Kết quả mong đợi:** 4 test PASS khi module đã cấu hình Spring Boot 3.3.x, JUnit Jupiter và AssertJ. Các test dùng `AutoConfigurations.of(...)` để nạp class trực tiếp, do đó chúng kiểm tra condition/runtime behavior chứ không chứng minh imports resource đã được phát hiện. Việc kiểm tra metadata compile-time vẫn phải thực hiện qua output/JAR như phần 10.

## 12. Lỗi thường gặp và cách xử lý

### Không có file spring-autoconfigure-metadata.properties

Nguyên nhân thường gặp:

- Processor được khai báo trong module starter nhưng class auto-configuration nằm ở module khác.
- Chỉ khai báo processor trong runtime/implementation dependency thay vì processor path.
- Maven compiler plugin quá cũ hoặc cấu hình annotation processor không được áp dụng.
- Gradle khai báo sai configuration, chẳng hạn `implementation` thay vì `annotationProcessor`.
- Build đang dùng output cũ; chưa chạy clean compile.
- Một plugin build tùy chỉnh vô hiệu hóa annotation processing.
- Source không chứa annotation nào mà processor có thể ghi metadata.

Cách kiểm tra: xác nhận đúng module, cấu hình processor path, chạy `clean compile`, sau đó xem output của source set main.

### File có nhưng không có key như mong đợi

Đừng mặc định rằng mọi annotation phải xuất hiện. Kiểm tra:

1. Annotation có thuộc nhóm mà processor hỗ trợ không?
2. Annotation được đặt ở class/method nào và processor có thu thập element đó không?
3. Giá trị condition có nằm trong thuộc tính được trích xuất không?
4. Bạn có đang nhìn đúng file của module/JAR chứa source đó không?

Ví dụ, không thấy `@ConditionalOnProperty` trong file metadata không chứng minh annotation bị bỏ qua ở runtime. Nó chỉ cho thấy không có bản ghi prefilter tương ứng trong metadata này.

### Ứng dụng vẫn chạy khi không có file metadata

Đây là hành vi bình thường. Metadata được dùng để tối ưu quá trình lọc sớm. Nếu file không có, Boot vẫn có thể đọc class metadata và đánh giá condition đầy đủ; startup có thể phải làm nhiều việc hơn.

### Có file trong target/classes nhưng không có trong JAR

Kiểm tra resource packaging, module artifact thực sự được publish và cấu hình build có loại trừ `META-INF` hay không. Đừng chỉ xác nhận file trong IDE; ứng dụng tiêu thụ đọc resource từ JAR trên runtime classpath.

### Nhầm với imports file

`AutoConfiguration.imports` liệt kê class candidate. `spring-autoconfigure-metadata.properties` lưu một số thông tin condition/order để hỗ trợ filter và sorting. Hai file có mục đích khác nhau, phải kiểm tra riêng.

### Nhầm với configuration properties metadata

`spring-configuration-metadata.json` phục vụ IDE và documentation cho các property. Nó không phải file lọc auto-configuration. Nếu muốn cả autocomplete property và prefilter auto-configuration, hãy cấu hình cả hai processor phù hợp.

## 13. Thực hành kiểm chứng theo từng bước

Một quy trình ngắn để xác nhận module đã cấu hình đúng:

1. Tạo một class `@AutoConfiguration` có `@ConditionalOnClass` và một thuộc tính ordering.
2. Đặt processor trong Maven `annotationProcessorPaths` hoặc Gradle `annotationProcessor` ở module autoconfigure.
3. Chạy clean compile.
4. Mở file `META-INF/spring-autoconfigure-metadata.properties` trong output classes.
5. Tìm FQCN của class và các key condition/order mà processor hỗ trợ.
6. Package JAR và kiểm tra file metadata có trong artifact.
7. Kiểm tra `AutoConfiguration.imports` cũng có trong JAR.
8. Dùng `ApplicationContextRunner` để kiểm tra condition thật khi class có/không có, property bật/tắt và user bean override.
9. Chạy một ứng dụng tiêu thụ starter để xác nhận toàn bộ discovery và runtime flow.

Không cần tự viết file metadata để test. Hãy kiểm tra artifact do compiler tạo ra, vì đó chính là file ứng dụng tiêu thụ sẽ đọc.

## 14. Câu hỏi tự kiểm tra

1. `spring-boot-autoconfigure-processor` chạy ở giai đoạn nào?  
   **Đáp án:** Trong lúc compile source Java của module chứa auto-configuration, thông qua annotation processing.

2. File được tạo có tên chính xác là gì?  
   **Đáp án:** `META-INF/spring-autoconfigure-metadata.properties`.

3. File này có thay thế `AutoConfiguration.imports` không?  
   **Đáp án:** Không. Imports file liệt kê candidate; metadata hỗ trợ lọc/sắp xếp một số candidate.

4. `@ConditionalOnProperty` không xuất hiện trong metadata có nghĩa runtime bỏ qua annotation đó không?  
   **Đáp án:** Không. Condition vẫn được đánh giá trong quy trình runtime thông thường.

5. Vì sao processor nên được cấu hình trong module autoconfigure?  
   **Đáp án:** Vì module đó chứa source auto-configuration cần xử lý và là nơi sinh metadata được đóng gói cùng JAR.

6. Khác biệt giữa `spring-boot-autoconfigure-processor` và `spring-boot-configuration-processor` là gì?  
   **Đáp án:** Processor thứ nhất tạo metadata condition/order để tối ưu auto-configuration; processor thứ hai tạo metadata property cho IDE và documentation.

7. Nếu thiếu file metadata, ứng dụng có nhất thiết không khởi động được không?  
   **Đáp án:** Không. File là tối ưu startup; Boot vẫn có thể xử lý condition bình thường mà không có metadata này.

8. Vì sao cần kiểm tra JAR sau khi build?  
   **Đáp án:** Vì file trong output classes chưa bảo đảm resource đã được đóng gói và phát hành cùng artifact.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): mục autoconfigure module, vai trò metadata, Maven compiler plugin và Gradle annotation processor.
- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): các thuộc tính thứ tự `before`, `beforeName`, `after`, `afterName`.
- [Spring Boot — Configuration Metadata: Generating Your Own Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): processor riêng cho `@ConfigurationProperties` và file `spring-configuration-metadata.json`.
- [Spring Boot source — AutoConfigureAnnotationProcessor](https://github.com/spring-projects/spring-boot/tree/v3.3.13/spring-boot-project/spring-boot-tools/spring-boot-autoconfigure-processor): mã nguồn processor của dòng Spring Boot 3.3.

**Ghi nhớ:** `spring-boot-autoconfigure-processor` tạo metadata compile-time để Boot lọc sớm một số auto-configuration và tối ưu startup. `spring-autoconfigure-metadata.properties` không đăng ký class, không thay thế condition runtime và không thay thế `spring-configuration-metadata.json`. Hãy cấu hình processor trong đúng module, kiểm tra file sau compile và xác nhận resource đã nằm trong JAR phát hành.
