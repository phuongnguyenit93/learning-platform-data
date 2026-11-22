# Đăng ký qua `spring.factories` trong mã cũ và chuyển sang `AutoConfiguration.imports`

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Tương thích phiên bản  
**Mục tiêu:** Hiểu cách Spring Boot khám phá auto-configuration ở các phiên bản cũ, chuyển registration sang `AutoConfiguration.imports`, duy trì tương thích giữa Boot 2.x và 3.x, và xác minh file registration thực sự được đóng gói và nạp trong ứng dụng.

## 1. Auto-configuration cần được đăng ký

Một class `@Configuration` hoặc `@AutoConfiguration` trong dependency JAR không tự động trở thành auto-configuration. Spring Boot cần danh sách các class ứng viên để đưa vào quá trình import.

Ứng dụng bật cơ chế này qua `@EnableAutoConfiguration`, thường được bao gồm trong `@SpringBootApplication`:

```java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Khi xử lý `@EnableAutoConfiguration`, Spring Boot tìm các class được thư viện công bố, sau đó đánh giá những condition như `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean`.

Trước Spring Boot 2.7, cách đăng ký phổ biến là dùng file `META-INF/spring.factories` với key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

Từ Boot 2.7, cơ chế đăng ký mới dùng:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Boot 2.7 hỗ trợ cả hai nguồn để tạo giai đoạn chuyển tiếp. Boot 3 loại bỏ việc đăng ký auto-configuration qua key cũ trong `spring.factories`. Thay đổi này ảnh hưởng đến quá trình **khám phá class**; logic bean và condition bên trong auto-configuration vẫn được áp dụng như trước.

## 2. Cách đăng ký cũ bằng `spring.factories`

Giả sử thư viện có class:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

Trước Boot 2.7, tạo file:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Khi có nhiều class, value là danh sách phân tách bằng dấu phẩy:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration,\
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration,\
com.acme.lib.autoconfigure.AcmeMetricsAutoConfiguration
```

Đây là file Java `Properties`:

- Key là tên đầy đủ của `EnableAutoConfiguration`.
- Value là tên đầy đủ của các auto-configuration class.
- Dấu phẩy ngăn cách nhiều class.
- Dấu `\` ở cuối dòng tiếp tục cùng một property sang dòng sau.

Một file `spring.factories` có thể chứa nhiều key để đăng ký các extension point khác của Spring Boot, chẳng hạn `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor` hoặc `FailureAnalyzer`. Khi migration, cần xử lý đúng key `EnableAutoConfiguration`; không xóa cả file nếu những key khác vẫn được sử dụng.

## 3. Định dạng mới `AutoConfiguration.imports`

Tạo file tại đúng đường dẫn:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng ghi một fully qualified class name:

```text
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration
com.acme.lib.autoconfigure.AcmeMetricsAutoConfiguration
```

Khác với `spring.factories`:

- Không có key `EnableAutoConfiguration=`.
- Không dùng dấu phẩy để phân cách class.
- Mỗi class nằm trên một dòng riêng.
- Có thể ghi chú bằng `#`.
- Tên class phải gồm đầy đủ package.

Ví dụ:

```text
# Core integration
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration

# Optional web integration
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration
```

Nếu class hiếm khi được khai báo lồng trong một class khác, dùng `$` để phân tách tên class:

```text
com.acme.lib.autoconfigure.AcmeConfiguration$NestedAutoConfiguration
```

Nên ưu tiên auto-configuration class cấp cao nhất, có tên rõ ràng và dễ kiểm tra.

Spring Boot tìm file này trong các JAR trên classpath. Do đó, file phải được đóng gói trong artifact mà consumer thực sự nhận được. Class `.class` có trong JAR nhưng thiếu registration resource vẫn chưa đủ để Spring Boot tự khám phá class đó.

## 4. Ma trận tương thích theo phiên bản

| Phiên bản | `spring.factories` với key `EnableAutoConfiguration` | `AutoConfiguration.imports` | Hành vi |
| --- | --- | --- | --- |
| Boot 2.6 và cũ hơn | Có hỗ trợ | Chưa hỗ trợ | Phải dùng cơ chế cũ |
| Boot 2.7 | Có hỗ trợ để tương thích ngược | Có hỗ trợ | Hai nguồn cùng liệt kê class sẽ được de-duplicate |
| Boot 3.x | Không còn dùng key này để đăng ký auto-configuration | Có hỗ trợ | Cần file imports |

### 4.1. Boot 2.7 là giai đoạn chuyển tiếp

Boot 2.7 giới thiệu file imports nhưng vẫn đọc các entry cũ trong `spring.factories`. Một class có thể được liệt kê trong cả hai file; Boot 2.7 de-duplicate các entry trùng nhau.

Điều này cho phép thư viện phát hành cả hai file để hỗ trợ:

- Boot cũ chỉ biết `spring.factories`.
- Boot 2.7 hiểu cả hai nguồn.
- Boot 3 dùng file imports mới.

Nếu thư viện chỉ hỗ trợ Boot 2.7 trở lên, có thể dùng imports làm nguồn registration chính. Nếu còn hỗ trợ Boot 2.6 hoặc cũ hơn, cần giữ entry cũ trong thời gian còn hỗ trợ các phiên bản đó.

### 4.2. Boot 3 loại bỏ key cũ, không loại bỏ toàn bộ `spring.factories`

Entry sau không còn đăng ký auto-configuration trên Boot 3:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Nếu thư viện chỉ giữ entry này, class vẫn có thể được biên dịch và đóng gói, nhưng Boot 3 không nạp nó qua cơ chế auto-configuration discovery. Hệ quả thường thấy là bean mặc định biến mất dù dependency vẫn có trên classpath.

Không nên hiểu thay đổi này là mọi chức năng của `spring.factories` đã bị loại bỏ. Boot 3 chỉ loại cơ chế đăng ký auto-configuration qua key `EnableAutoConfiguration`; các key khác vẫn có thể được Spring Boot sử dụng cho extension point tương ứng.

## 5. Chọn cách migration theo phiên bản thấp nhất cần hỗ trợ

### Trường hợp A: Chỉ hỗ trợ Boot 2.7+ và Boot 3.x

Dùng `@AutoConfiguration` và file imports:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

Nếu không còn hỗ trợ phiên bản trước 2.7, không cần giữ entry `EnableAutoConfiguration` cũ chỉ để đăng ký class này.

### Trường hợp B: Hỗ trợ cả Boot 2.6 và Boot 2.7/3.x

Giữ cả hai file:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ `spring.factories`:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Ví dụ imports:

```text
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Cần chú ý `@AutoConfiguration` chỉ có từ Boot 2.7. Nếu Boot 2.6 là runtime thấp nhất, class có annotation `@AutoConfiguration` có thể tham chiếu một annotation mà Boot 2.6 không có, dẫn đến lỗi nạp lớp như `NoClassDefFoundError`.

Một lựa chọn annotation chung là giữ `@Configuration(proxyBeanMethods = false)` và các annotation ordering có từ phiên bản cũ như `@AutoConfigureBefore`/`@AutoConfigureAfter`. Boot 3 vẫn có thể nạp class đó từ file imports:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfigureAfter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigureAfter(name = "com.acme.other.autoconfigure.OtherAutoConfiguration")
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

Hai file registration chỉ giải quyết discovery. Chúng không tự bảo đảm toàn bộ bytecode, Java baseline, Spring Framework API và dependency graph tương thích với mọi phiên bản. Nếu khác biệt giữa Boot 2 và Boot 3 quá lớn, hãy cân nhắc artifact/variant riêng và kiểm thử từng baseline.

### 5.1. Quy tắc chọn nhanh

- Chỉ Boot 3.x: dùng imports.
- Boot 2.7 và Boot 3.x: imports là cơ chế mới; có thể giữ cả hai file nếu cần hỗ trợ thêm phiên bản cũ.
- Boot 2.6 trở xuống: cần `spring.factories`.
- Boot 2.6 trở xuống cùng Boot 3.x: cần cả hai file và phải kiểm tra annotation/dependency compatibility.
- Không xóa những key `spring.factories` khác chỉ vì đã chuyển auto-configuration.

## 6. `@AutoConfiguration` và `@Configuration`

Boot 2.7 giới thiệu:

```java
org.springframework.boot.autoconfigure.AutoConfiguration
```

`@AutoConfiguration` là annotation chuyên biệt cho auto-configuration class. Nó được meta-annotate bằng `@Configuration(proxyBeanMethods = false)`, vì vậy auto-configuration không bật method proxy mặc định.

Dùng trên class cấp cao nhất:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
```

Các nested configuration vẫn dùng:

```java
@Configuration(proxyBeanMethods = false)
static class OptionalClientConfiguration {
}
```

Cần nhớ:

- `@AutoConfiguration` không tự đăng ký class; file imports vẫn phải liệt kê class đó.
- Annotation này không thay thế condition như `@ConditionalOnClass` hoặc `@ConditionalOnMissingBean`.
- Dùng `@AutoConfiguration` khi baseline từ Boot 2.7 trở lên.
- Nếu hỗ trợ Boot trước 2.7, xem lại annotation và dependency baseline; dùng `@Configuration` nếu cần một class tương thích chung.

## 7. Chuyển annotation ordering

Mã cũ thường dùng:

```java
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore(DataSourceAutoConfiguration.class)
@AutoConfigureAfter(HibernateJpaAutoConfiguration.class)
public class AcmePersistenceAutoConfiguration {
}
```

Với `@AutoConfiguration`, có thể biểu diễn ordering trực tiếp:

```java
@AutoConfiguration(
        before = DataSourceAutoConfiguration.class,
        after = HibernateJpaAutoConfiguration.class
)
public class AcmePersistenceAutoConfiguration {
}
```

Có thể dùng tên class khi không muốn phụ thuộc trực tiếp vào class khác:

```java
@AutoConfiguration(
        beforeName = "com.acme.other.autoconfigure.OtherAutoConfiguration",
        afterName = "com.acme.cache.autoconfigure.CacheAutoConfiguration"
)
public class AcmeClientAutoConfiguration {
}
```

Các annotation `@AutoConfigureBefore` và `@AutoConfigureAfter` vẫn có thể dùng. `@AutoConfigureOrder` hữu ích khi cần thứ tự tổng quát mà hai auto-configuration không cần tham chiếu trực tiếp lẫn nhau.

Ordering quyết định thứ tự áp dụng auto-configuration và đăng ký bean definition. Nó không quyết định thứ tự khởi tạo object cuối cùng; việc khởi tạo vẫn theo dependency graph và `@DependsOn`.

Không dựa vào thứ tự dòng trong imports file như một hợp đồng ordering. Hãy mô tả quan hệ trước/sau bằng annotation chuyên dụng.

## 8. Module nào phải chứa file imports?

Với thư viện có starter riêng, cấu trúc thường gặp:

```text
acme/
├── acme-core/
├── acme-spring-boot-autoconfigure/
│   ├── src/main/java/com/acme/lib/autoconfigure/
│   │   ├── AcmeClientAutoConfiguration.java
│   │   └── AcmeWebAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── acme-spring-boot-starter/
└── consumer-app/
```

File imports phải nằm trong JAR chứa auto-configuration class. Nếu starter chỉ là artifact tổng hợp dependency, resource thường nằm trong module `autoconfigure` mà starter kéo vào, không nhất thiết phải được chép lại vào JAR starter.

Một ứng dụng có thể nhận auto-configuration từ nhiều JAR. Spring Boot tìm các file imports trên classpath và tổng hợp các candidate.

Không đặt auto-configuration vào package mà component scan của ứng dụng quét. Auto-configuration nên được tìm qua registration file; các configuration hỗ trợ nên được nạp bằng `@Import`. Tránh dùng `@ComponentScan` trong auto-configuration để dò component tùy ý.

## 9. Merge resource khi tạo shaded/uber JAR

Khi dùng JAR library thông thường, resource imports được copy từ `src/main/resources` vào JAR. Nhưng khi tạo shaded/uber JAR, nhiều dependency có thể cùng chứa file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu công cụ đóng gói chỉ giữ file cuối cùng thay vì gộp nội dung, một số auto-configuration sẽ biến mất khỏi artifact cuối.

Với Maven Shade Plugin, có thể dùng `AppendingTransformer`:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

Với Gradle Shadow Plugin:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

Chỉ cần cấu hình này khi build thực sự merge dependency resources. Nếu vẫn giữ `spring.factories`, hãy bảo đảm plugin merge file properties đúng cách để key/value từ dependency khác không ghi đè nhau. Sau khi shade, kiểm tra nội dung file cuối cùng thay vì chỉ kiểm tra JAR của từng module.

## 10. Ví dụ chạy được: Boot 3.3.13 đăng ký bằng imports

Ví dụ dùng Java 17, Maven và Spring Boot 3.3.13. Integration test khởi động ứng dụng tối giản có `@EnableAutoConfiguration`, rồi xác nhận bean được tìm thấy nhờ file imports.

### 10.1. Cấu trúc

```text
acme-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── GreetingService.java
    │   │   └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/
        └── AutoConfigurationImportTest.java
```

### 10.2. `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>acme-autoconfigure-demo</artifactId>
    <version>1.0.0</version>

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
</project>
```

### 10.3. `GreetingService.java`

```java
package demo;

public record GreetingService(String message) {
}
```

### 10.4. `GreetingAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new GreetingService("hello from auto-configuration");
    }
}
```

`@ConditionalOnMissingBean` cho phép ứng dụng tự cung cấp `GreetingService`, khiến bean mặc định nhường chỗ.

### 10.5. File `AutoConfiguration.imports`

Nội dung:

```text
demo.autoconfigure.GreetingAutoConfiguration
```

Đường dẫn chính xác:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 10.6. Integration test

File `AutoConfigurationImportTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = AutoConfigurationImportTest.TestApplication.class)
class AutoConfigurationImportTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversAutoConfigurationFromImportsFile() {
        assertThat(context.getBeansOfType(GreetingService.class))
                .hasSize(1);

        assertThat(context.getBean(GreetingService.class).message())
                .isEqualTo("hello from auto-configuration");
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
```

Test dùng `@EnableAutoConfiguration` thật, nên Spring Boot phải tìm class từ file imports trên classpath. Test không gọi trực tiếp constructor của auto-configuration và không dùng `@Import` để bỏ qua quá trình discovery.

Chạy:

```bash
mvn test
```

Kết quả mong đợi:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Nếu test không tìm thấy `GreetingService`, kiểm tra resource path, package/class name và resource output. Nếu bean xuất hiện hai lần, kiểm tra class có đồng thời bị component scan hoặc cơ chế import khác đăng ký không.

## 11. Kiểm tra resource trong JAR cuối cùng

Build artifact:

```bash
mvn clean package
```

Liệt kê nội dung JAR:

```bash
jar tf target/acme-autoconfigure-demo-1.0.0.jar
```

Tìm resource trên Linux/macOS:

```bash
jar tf target/acme-autoconfigure-demo-1.0.0.jar |
    grep -F 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
```

Trên Windows PowerShell:

```powershell
jar tf target/acme-autoconfigure-demo-1.0.0.jar |
    Select-String 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
```

Đọc nội dung resource mà không giải nén toàn bộ JAR:

```bash
unzip -p target/acme-autoconfigure-demo-1.0.0.jar \
    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Kết quả cần chứa:

```text
demo.autoconfigure.GreetingAutoConfiguration
```

Nếu JAR không có resource, kiểm tra:

- File có nằm trong `src/main/resources` không.
- Tên file có đúng từng ký tự và chữ hoa/chữ thường không.
- Maven resource filtering/custom packaging có loại `META-INF/spring/**` không.
- Có đang kiểm tra đúng artifact/version không.
- Nếu dùng Shade/Shadow, cấu hình append/merge đã có hiệu lực chưa.

Class `.class` tồn tại trong JAR không chứng minh auto-configuration đã được đăng ký. Class và registration metadata là hai phần độc lập.

## 12. Kiểm thử compatibility theo từng dòng Boot

Với thư viện hỗ trợ nhiều phiên bản, tạo consumer test riêng cho từng baseline:

| Consumer | Registration cần có | Kết quả cần xác nhận |
| --- | --- | --- |
| Boot 2.6.x | `spring.factories` | Auto-configuration được tìm thấy qua key cũ |
| Boot 2.7.x | Cả hai file nếu cần hỗ trợ phiên bản cũ | Class được nạp đúng một lần |
| Boot 3.x | `AutoConfiguration.imports` | Auto-configuration được nạp dù key cũ không còn tác dụng |

Mỗi consumer test cần dùng đúng dependency version của dòng Boot đó. Không chỉ thay version property trong một test nếu dependency graph, Java baseline hoặc Spring Framework API đã khác nhau.

Nên kiểm tra:

1. Consumer khởi động qua `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.
2. Bean mặc định xuất hiện khi condition match.
3. Bean do ứng dụng cung cấp khiến `@ConditionalOnMissingBean` back off.
4. Optional class vắng mặt không gây lỗi class loading.
5. JAR publish có đúng registration file.
6. Shaded JAR giữ đủ các entry imports từ mọi dependency.
7. Boot 2.7 không đăng ký trùng class khi hai file cùng liệt kê.

### 12.1. Test logic khác test discovery

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(MyAutoConfiguration.class))` hữu ích để test condition, bean và property. Nhưng runner nhận class trực tiếp, nên không chứng minh file imports đã được đặt đúng hoặc đóng gói.

Muốn test discovery, hãy khởi động context có `@EnableAutoConfiguration` mà không import class thủ công, như integration test ở trên. Sau đó kiểm tra JAR cuối cùng để xác nhận publication.

## 13. Lỗi thường gặp

**Lỗi 1 — Đổi tên file nhưng giữ format cũ.**  
`AutoConfiguration.imports` không phải file Properties. Không có key `EnableAutoConfiguration=`, không dùng dấu phẩy; mỗi class một dòng.

**Lỗi 2 — Chỉ sửa `spring.factories` rồi quên imports.**  
Boot 3 không còn nạp auto-configuration qua key cũ. Class có trong JAR nhưng không được discovery.

**Lỗi 3 — Xóa toàn bộ `spring.factories`.**  
Các key khác có thể vẫn được Boot sử dụng. Chỉ loại entry auto-configuration cũ khi không còn cần tương thích phiên bản trước 2.7.

**Lỗi 4 — Dùng `@AutoConfiguration` nhưng vẫn hỗ trợ Boot trước 2.7.**  
Annotation này không có ở Boot 2.6. Khi runtime cũ cố đọc class, có thể gặp `NoClassDefFoundError`. Dùng annotation chung hoặc phát hành artifact phù hợp theo phiên bản.

**Lỗi 5 — Đặt imports trong module consumer không nhận được.**  
Resource phải nằm trong JAR trên classpath. Module build thành công nhưng không được starter kéo vào sẽ không đóng góp auto-configuration.

**Lỗi 6 — Đưa auto-configuration vào component scan.**  
Auto-configuration nên được tìm qua registration file. Giữ package chuyên biệt và dùng `@Import` cho configuration hỗ trợ.

**Lỗi 7 — Quên merge resource khi shade.**  
Nhiều dependency có thể cùng chứa imports file. Nếu plugin chỉ giữ một bản, các entry khác mất khỏi uber JAR.

**Lỗi 8 — Dựa vào thứ tự dòng trong imports.**  
Dùng `@AutoConfiguration(before/after)` hoặc annotation ordering chuyên dụng để mô tả quan hệ.

**Lỗi 9 — Dùng test import class trực tiếp để kết luận discovery đúng.**  
Test đó bỏ qua file registration. Cần integration test qua `@EnableAutoConfiguration`.

**Lỗi 10 — Chỉ kiểm tra JAR module con.**  
Artifact cuối cùng sau Shade/Shadow có thể mất resource. Kiểm tra đúng JAR mà consumer tải.

## 14. Checklist migration

1. Tìm mọi file `META-INF/spring.factories` trong các module.
2. Xác định entry `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.
3. Liệt kê đủ các class trong value, kể cả dấu phẩy và dấu `\` tiếp dòng.
4. Tạo `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
5. Chuyển mỗi class name thành một dòng riêng.
6. Nếu baseline từ Boot 2.7, cân nhắc dùng `@AutoConfiguration` cho class cấp cao nhất.
7. Nếu còn hỗ trợ trước Boot 2.7, giữ entry cũ và kiểm tra annotation/dependency baseline.
8. Giữ nguyên các key `spring.factories` khác.
9. Cấu hình merge resource nếu dùng Maven Shade hoặc Gradle Shadow.
10. Viết integration test qua `@EnableAutoConfiguration`.
11. Build JAR, dùng `jar tf` và đọc nội dung imports.
12. Chạy consumer test ở phiên bản Boot thấp nhất và cao nhất được công bố hỗ trợ.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Trước Boot 2.7, auto-configuration được đăng ký ở đâu?  
**Đáp án:** `META-INF/spring.factories`, dưới key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

**Câu 2.** File đăng ký mới nằm ở đâu?  
**Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Câu 3.** Định dạng của imports file là gì?  
**Đáp án:** Một fully qualified class name trên mỗi dòng; comment có thể bắt đầu bằng `#`.

**Câu 4.** Boot 2.7 xử lý class được liệt kê trong cả hai file thế nào?  
**Đáp án:** Hỗ trợ cả hai nguồn và de-duplicate entry trùng nhau.

**Câu 5.** Vì sao entry `EnableAutoConfiguration` cũ không còn hoạt động trong Boot 3?  
**Đáp án:** Boot 3 loại bỏ việc đăng ký auto-configuration qua key đó; phải dùng imports file.

**Câu 6.** Boot 3 có ngừng đọc mọi key trong `spring.factories` không?  
**Đáp án:** Không. Chỉ cơ chế auto-configuration qua key `EnableAutoConfiguration` bị loại bỏ; các key khác không bị ảnh hưởng bởi thay đổi này.

**Câu 7.** `@AutoConfiguration` có từ phiên bản nào?  
**Đáp án:** Spring Boot 2.7.0. Nếu hỗ trợ Boot cũ hơn, cần xem xét việc dùng annotation này trong bytecode.

**Câu 8.** Vì sao `AutoConfigurations.of(MyAutoConfiguration.class)` chưa chứng minh imports file đúng?  
**Đáp án:** Test truyền class trực tiếp vào runner, bỏ qua discovery qua `@EnableAutoConfiguration` và resource imports.

**Câu 9.** Vì sao phải append resource khi dùng Shadow hoặc Shade?  
**Đáp án:** Nhiều dependency có thể chứa cùng imports file; nếu không merge, artifact cuối có thể mất một số class registration.

**Câu 10.** `@AutoConfiguration(before = X.class)` có bảo đảm bean hiện tại được khởi tạo trước bean của X không?  
**Đáp án:** Không. Nó điều khiển thứ tự áp dụng auto-configuration/đăng ký bean definition; khởi tạo bean vẫn theo dependency graph và lifecycle.

## 16. Nguyên tắc cần nhớ

- Trước Boot 2.7: đăng ký qua `spring.factories` với key `EnableAutoConfiguration`.
- Boot 2.7: hỗ trợ cả hai file và de-duplicate entry trùng.
- Boot 3: dùng `AutoConfiguration.imports`; key auto-configuration cũ trong `spring.factories` không còn tác dụng.
- Những key `spring.factories` khác vẫn có thể được sử dụng.
- Imports file chứa một fully qualified class name trên mỗi dòng.
- `@AutoConfiguration` có từ Boot 2.7; nested configuration tiếp tục dùng `@Configuration`.
- Giữ cả hai registration file nếu cần hỗ trợ Boot trước 2.7, đồng thời kiểm tra annotation và dependency baseline.
- Dùng annotation ordering thay vì dựa vào thứ tự dòng trong resource.
- Merge resource khi tạo shaded/uber JAR và kiểm tra artifact cuối.
- Dùng integration test qua `@EnableAutoConfiguration` để xác nhận discovery thực sự.

### Tài liệu tham khảo chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 2.7 Reference — Locating Auto-configuration Candidates](https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/)
