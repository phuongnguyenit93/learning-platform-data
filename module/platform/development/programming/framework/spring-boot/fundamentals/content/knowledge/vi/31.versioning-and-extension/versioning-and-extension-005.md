# Thay đổi cách đăng ký auto-configuration qua các dòng Spring Boot

Spring Boot auto-configuration giúp một thư viện tự cấu hình các bean cần thiết khi ứng dụng có dependency phù hợp trên classpath. Thay vì yêu cầu mọi ứng dụng phải import một configuration class bằng tay, Spring Boot tìm các lớp auto-configuration đã được thư viện công bố, đánh giá các điều kiện và đăng ký bean khi những điều kiện đó thỏa mãn.

Cơ chế **đăng ký auto-configuration đã thay đổi theo các dòng Spring Boot**. Nếu bạn duy trì starter hoặc nâng cấp ứng dụng từ Boot 2.x lên 3.x/4.x, cần biết file nào được framework đọc, annotation nào phù hợp và cách duy trì tương thích.

Mốc chuyển đổi quan trọng:

- **Spring Boot 1.x đến 2.6:** đăng ký auto-configuration bằng key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `META-INF/spring.factories`.
- **Spring Boot 2.7:** giới thiệu `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và annotation `@AutoConfiguration`. Cơ chế cũ vẫn được hỗ trợ để chuyển tiếp, nhưng đã deprecated.
- **Spring Boot 3.0 trở lên:** bỏ việc đăng ký auto-configuration bằng key `EnableAutoConfiguration` trong `spring.factories`. File `AutoConfiguration.imports` là cơ chế cần dùng. Những SPI khác vẫn có thể tiếp tục dùng `spring.factories`.
- **Spring Boot 4.x:** tiếp tục dùng `AutoConfiguration.imports`. Khi nâng cấp starter, cần chú ý modularization và thay đổi package/module của Boot 4; không quay lại cơ chế đăng ký cũ.

Bài học đi từ lịch sử, cấu trúc file, ví dụ tạo auto-configuration, migration tương thích nhiều phiên bản, kiểm thử, đóng gói JAR và cách chẩn đoán khi auto-configuration không được nạp.

## 1. Auto-configuration làm nhiệm vụ gì?

Một thư viện có thể cần tạo client, converter, template hoặc service mặc định. Ví dụ thư viện Acme cung cấp SDK để gọi dịch vụ catalog. Khi ứng dụng thêm SDK vào classpath, starter có thể tự đăng ký:

- `AcmeClient` để gọi dịch vụ.
- `AcmeClientProperties` để bind URL và timeout.
- `AcmeHealthIndicator` nếu có integration health.
- Các converter hoặc customizer liên quan.

Auto-configuration là configuration class do thư viện cung cấp. Spring Boot phát hiện class này, sau đó xử lý các điều kiện như:

- Thư viện cần thiết có trên classpath hay không.
- Ứng dụng đã tự khai báo bean tương ứng chưa.
- Property bật/tắt tính năng có giá trị gì.
- Ứng dụng có phải web application hay không.
- Một resource hoặc class cụ thể có tồn tại không.

Ví dụ, thư viện chỉ muốn tạo client khi SDK có mặt và ứng dụng chưa tự cung cấp client:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeSdk.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
```

Khi auto-configuration được nạp, điều kiện được đánh giá. Nếu phù hợp, bean definition được đăng ký. Việc đăng ký lớp auto-configuration **không có nghĩa tất cả bean của nó chắc chắn được tạo**; các condition vẫn quyết định từng cấu hình/bean method có áp dụng hay không.

## 2. Giai đoạn Spring Boot 1.x đến 2.6: spring.factories

Trong các dòng Boot cũ, auto-configuration được đăng ký qua file:

```text
META-INF/spring.factories
```

Trong file, dùng key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` và danh sách fully qualified class name.

Ví dụ:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeClientAutoConfiguration,\
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

Các class được liệt kê sẽ trở thành candidate cho quá trình auto-configuration khi ứng dụng bật `@EnableAutoConfiguration` hoặc dùng `@SpringBootApplication`.

### 2.1. Vì sao file có tên spring.factories?

`spring.factories` là cơ chế đăng ký nhiều loại extension point của Spring Boot và Spring Framework, không chỉ auto-configuration. Một file có thể chứa nhiều key, mỗi key ánh xạ tới một hoặc nhiều implementation class.

Ví dụ minh họa một số SPI từng được đăng ký qua file này:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeClientAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.bootstrap.AcmeEnvironmentPostProcessor

org.springframework.boot.diagnostics.FailureAnalyzer=\
com.acme.diagnostics.AcmeFailureAnalyzer
```

Không nên hiểu rằng khi Boot 3 bỏ key auto-configuration thì toàn bộ file `spring.factories` bị loại bỏ. Thay đổi tập trung vào **key đăng ký auto-configuration**.

### 2.2. @EnableAutoConfiguration kích hoạt quá trình tìm candidate

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Annotation này kích hoạt cơ chế selector để tìm danh sách auto-configuration candidate từ các thư viện trên classpath.

Trong các dòng cũ, danh sách candidate được lấy từ key `EnableAutoConfiguration` của `spring.factories`. Sau đó Spring Boot xử lý exclusion, condition và thứ tự cấu hình.

Ứng dụng thông thường không cần tự liệt kê từng auto-configuration class. Starter hoặc thư viện chịu trách nhiệm công bố chúng.

## 3. Spring Boot 2.7: giai đoạn chuyển tiếp

Spring Boot 2.7 giới thiệu file mới:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng chứa một fully qualified class name:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

File mới có các điểm đáng chú ý:

- Không dùng một key Properties dài như `spring.factories`.
- Mỗi auto-configuration class nằm trên một dòng riêng.
- Có thể thêm comment bằng ký tự `#`.
- Framework đọc file từ các JAR trên classpath.
- Boot 2.7 vẫn đọc registration cũ để hỗ trợ thư viện chưa migration.
- Nếu cùng một class được liệt kê ở cả hai nơi, Boot 2.7 loại bỏ candidate trùng lặp.

### 3.1. Đường dẫn phải chính xác

Đường dẫn mới là:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đây là resource nằm trong JAR của module auto-configuration. Một số tài liệu milestone sớm từng có đường dẫn thử nghiệm khác; khi migration theo Boot 2.7 stable và các dòng mới, dùng đúng đường dẫn `META-INF/spring/...` ở trên.

### 3.2. Annotation @AutoConfiguration được giới thiệu

Boot 2.7 giới thiệu `@AutoConfiguration` dành cho class auto-configuration cấp cao nhất:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
```

Annotation này là meta-annotation của `@Configuration(proxyBeanMethods = false)`, đồng thời cung cấp thuộc tính để khai báo thứ tự auto-configuration.

Vì vậy, class top-level thường dùng `@AutoConfiguration` thay cho `@Configuration` khi baseline hỗ trợ Boot 2.7 trở lên.

Các configuration class được import hoặc lồng bên trong auto-configuration vẫn có thể tiếp tục dùng `@Configuration` theo vai trò thông thường.

### 3.3. Boot 2.7 vẫn hỗ trợ spring.factories cho tương thích

Trong giai đoạn 2.7, thư viện có thể công bố cùng auto-configuration class ở cả hai file:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đây là cầu nối hữu ích khi một thư viện cần hỗ trợ cả Boot 2.6 và Boot 2.7:

- Boot 2.6 chỉ hiểu registration cũ.
- Boot 2.7 hiểu cả registration cũ và mới.
- Boot 2.7 deduplicate class xuất hiện ở cả hai nguồn.

Tuy nhiên, việc duy trì hai file chỉ nên phục vụ ma trận version thật sự cần hỗ trợ. Nếu baseline của thư viện đã là Boot 2.7+, có thể dùng file imports mới và loại registration auto-configuration cũ.

## 4. Spring Boot 3.0: bỏ key EnableAutoConfiguration khỏi spring.factories

Boot 3.0 bỏ hỗ trợ đăng ký auto-configuration qua key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

trong `META-INF/spring.factories`.

Thay vào đó, framework sử dụng:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ registration dành cho Boot 3:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

### 4.1. spring.factories không biến mất hoàn toàn

Các entry khác trong `spring.factories` vẫn được giữ theo SPI tương ứng. Ví dụ, một thư viện có thể vẫn đăng ký `FailureAnalyzer` hoặc `EnvironmentPostProcessor` bằng key phù hợp.

Do đó, migration đúng là:

- Xóa **entry auto-configuration** cũ khỏi `spring.factories` khi không còn cần tương thích Boot 2.6.
- Giữ các entry SPI khác nếu chúng vẫn được phiên bản đang dùng hỗ trợ.
- Chuyển danh sách auto-configuration class sang file `AutoConfiguration.imports`.

Đừng xóa toàn bộ `spring.factories` một cách máy móc nếu thư viện còn dùng extension point khác.

### 4.2. Một thư viện hỗ trợ Boot 2.x và Boot 3.x

Nếu cùng một artifact cần hỗ trợ Boot 2.6 và Boot 3.x, có thể đóng gói cả hai resource registration:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Trong `spring.factories`, giữ entry `EnableAutoConfiguration` để Boot 2.6 tìm thấy class. Trong file imports, công bố class để Boot 2.7/3.x tìm thấy.

Boot 2.7 hỗ trợ cả hai nguồn và loại candidate trùng. Boot 3.x bỏ qua key auto-configuration cũ và dùng file imports.

Ngoài resource registration, cần kiểm tra **binary/API compatibility** của class. Nếu class dùng annotation hoặc API chỉ tồn tại từ Boot 2.7, nó có thể không chạy được trên Boot 2.6 dù registration file cũ vẫn còn. Hãy chọn baseline compile phù hợp hoặc phát hành artifact/variant riêng.

### 4.3. @AutoConfiguration và compatibility với Boot 2.6

`@AutoConfiguration` được giới thiệu trong Boot 2.7. Nếu một binary phải chạy với Boot 2.6, không thể mặc định rằng class tham chiếu annotation này sẽ hoạt động trên runtime 2.6.

Các lựa chọn:

- Nếu baseline tối thiểu là Boot 2.7, dùng `@AutoConfiguration`.
- Nếu cần cùng một binary chạy trên Boot 2.6 và Boot 3, cân nhắc dùng `@Configuration` cùng các ordering annotation có mặt trong baseline, rồi đăng ký qua file cũ và mới.
- Nếu cần tận dụng API mới riêng của Boot 3, phát hành artifact/variant phù hợp thay vì cố ép một binary duy nhất hỗ trợ mọi generation.

Boot 3 không yêu cầu xóa các configuration class chỉ vì chúng dùng `@Configuration`; điều quan trọng là class được đăng ký và có cấu hình phù hợp. Tuy nhiên, với code mới chỉ hỗ trợ Boot 2.7+, `@AutoConfiguration` là lựa chọn được khuyến nghị.

## 5. Dòng Spring Boot 4.x

Spring Boot 4 tiếp tục sử dụng cơ chế `AutoConfiguration.imports` cho auto-configuration. Không có sự quay lại đăng ký auto-configuration bằng key `EnableAutoConfiguration` trong `spring.factories`.

Khi nâng cấp thư viện/starter lên Boot 4, cần chú ý thêm:

- Boot 4 modularize các phần của framework; package và module chứa một số API/auto-configuration có thể thay đổi.
- Starter artifact và dependency có thể được tổ chức lại theo module mới.
- Các class được tham chiếu trong `before`/`after`, exclusion và replacement cần được cập nhật nếu package thay đổi.
- Một số SPI còn dùng `spring.factories` có thể thay đổi package/class key; ví dụ `EnvironmentPostProcessor` được chuyển package trong Boot 4, nên cả import code lẫn key đăng ký phải khớp API mới.
- Hướng dẫn migration Boot 4 khuyến nghị không cố hỗ trợ Boot 3 và Boot 4 trong cùng một artifact starter nếu có thể phát hành các dòng tương thích riêng.

Điều này không thay đổi nguyên tắc cốt lõi của registration: auto-configuration vẫn được công bố qua resource imports. Phần cần rà soát ở Boot 4 là module, package, dependency và SPI mà auto-configuration sử dụng.

## 6. Bảng so sánh các dòng Spring Boot

| Dòng Spring Boot | Cách đăng ký auto-configuration | Annotation top-level khuyến nghị | Ghi chú |
|---|---|---|---|
| 1.x | `spring.factories` với key `EnableAutoConfiguration` | `@Configuration` | Cơ chế truyền thống |
| 2.0–2.6 | `spring.factories` với key `EnableAutoConfiguration` | `@Configuration` | Tiếp tục cơ chế cũ |
| 2.7 | `AutoConfiguration.imports`; vẫn hỗ trợ `spring.factories` để tương thích | `@AutoConfiguration` | Bắt đầu migration, có de-dup |
| 3.x | `AutoConfiguration.imports` | `@AutoConfiguration` | Bỏ key `EnableAutoConfiguration` khỏi `spring.factories` |
| 4.x | `AutoConfiguration.imports` | `@AutoConfiguration` | Tiếp tục imports; lưu ý modularization và package migration |

Nhớ rằng bảng nói về **đăng ký auto-configuration**. Các SPI khác có thể có cơ chế hoặc key riêng và không nên suy luận rằng mọi entry trong `spring.factories` đều đã bị xóa.

## 7. Cấu trúc module starter hiện đại

Một thư viện có thể tách module như sau:

```text
acme-spring-boot/
├── acme-spring-boot-autoconfigure/
│   ├── src/main/java/com/acme/autoconfigure/
│   │   ├── AcmeClientAutoConfiguration.java
│   │   └── AcmeClientProperties.java
│   └── src/main/resources/
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-spring-boot-starter/
    └── build configuration / dependency declarations
```

Vai trò:

- **autoconfigure module:** chứa auto-configuration class, properties class và code cần để tích hợp thư viện.
- **starter module:** gom các dependency cần thiết để ứng dụng thêm một dependency starter là đủ.

Nếu thư viện đơn giản, có thể gộp thành một module. Tách module hữu ích khi người dùng muốn tự chọn dependency nhưng vẫn dùng auto-configuration.

### 7.1. Đừng đặt tên module như một starter chính thức của Spring

Starter của bên thứ ba nên dùng namespace riêng, ví dụ `acme-spring-boot-starter`. Không nên tự đặt tên module bắt đầu bằng `spring-boot-` nếu không thuộc dự án Spring Boot chính thức.

Configuration keys cũng nên có namespace riêng, ví dụ `acme.client`, tránh chiếm namespace lõi như `spring`, `server` hoặc `management`.

## 8. Tạo một auto-configuration hoàn chỉnh

Giả sử thư viện Acme có client:

```java
package com.acme.client;

public class AcmeClient {

    private final String baseUrl;
    private final Duration timeout;

    public AcmeClient(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public String baseUrl() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Properties:

```java
package com.acme.autoconfigure;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        String baseUrl,
        Duration timeout
) {
}
```

Auto-configuration:

```java
package com.acme.autoconfigure;

import com.acme.client.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
```

Ví dụ giả định dependency SDK có mặt khi auto-configuration được dùng. Ứng dụng thật nên xác định rõ default và validation cho các property bắt buộc.

### 8.1. Đăng ký trong AutoConfiguration.imports

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
```

Khi build JAR, resource phải nằm đúng path bên trong archive. Nếu source file đúng nhưng resource không được đóng gói, Spring Boot không tìm thấy auto-configuration.

### 8.2. Cấu hình ứng dụng sử dụng starter

Ví dụ `application.yml`:

```yaml
acme:
  client:
    enabled: true
    base-url: https://api.acme.example
    timeout: 3s
```

Ứng dụng chỉ cần thêm starter tương ứng vào dependency. Nếu class SDK có trên classpath, property cho phép và không có bean tùy chỉnh thay thế, auto-configuration sẽ tạo `AcmeClient`.

## 9. Điều kiện quan trọng trong auto-configuration

Đăng ký class chỉ làm nó trở thành candidate. Conditions quyết định cấu hình có được áp dụng hay không.

### 9.1. @ConditionalOnClass

Dùng khi tính năng chỉ hoạt động nếu dependency/class cụ thể có trên classpath:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeClientAutoConfiguration {
}
```

Đặt condition ở cấp configuration class giúp Boot kiểm tra metadata trước khi xử lý cấu hình phụ thuộc class đó.

Nếu dùng class optional trong return type của `@Bean` method, hãy cẩn thận: JVM có thể cần load method signature trước khi condition trên method được đánh giá. Khi dependency thực sự optional, nên cô lập phần cấu hình phụ thuộc class đó trong một configuration class riêng có `@ConditionalOnClass` ở cấp class.

### 9.2. @ConditionalOnMissingBean

Cho phép ứng dụng cung cấp bean riêng:

```java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
    );
}
```

Nếu người dùng đã khai báo một bean `AcmeClient`, auto-configuration không tạo default bean.

Điều kiện bean nên được dùng trong auto-configuration vì auto-configuration được xử lý sau các bean definition do ứng dụng khai báo. Tránh dựa vào thứ tự tình cờ giữa các configuration thông thường.

### 9.3. @ConditionalOnProperty

Dùng để bật/tắt tính năng:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
    );
}
```

Nếu muốn mặc định tắt, bỏ `matchIfMissing = true` và yêu cầu property bật tường minh.

### 9.4. Các condition khác

Spring Boot còn có condition cho:

- Class có/không có trên classpath.
- Bean type hoặc bean name.
- Property value.
- Resource có tồn tại.
- Web application hoặc loại web application.
- Expression SpEL.

Hãy dùng condition mô tả chính xác điều kiện tích hợp, thay vì tạo bean rồi kiểm tra thủ công trong constructor.

## 10. Thứ tự auto-configuration

Một số auto-configuration cần được xử lý trước hoặc sau cấu hình khác. Ví dụ, cấu hình web mở rộng có thể cần được áp dụng sau auto-configuration của MVC.

Với `@AutoConfiguration`:

```java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class AcmeWebAutoConfiguration {
}
```

Hoặc dùng tên class:

```java
@AutoConfiguration(afterName =
        "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration")
public class AcmeWebAutoConfiguration {
}
```

Các annotation chuyên biệt cũng được hỗ trợ:

```java
@AutoConfigureAfter(WebMvcAutoConfiguration.class)
@AutoConfigureBefore(SomeOtherAutoConfiguration.class)
@AutoConfigureOrder(100)
```

### 10.1. Thứ tự đăng ký không phải thứ tự tạo bean

Ordering quyết định thứ tự các auto-configuration class/bean definition được xử lý. Nó **không** có nghĩa mọi bean trong class chạy constructor theo cùng thứ tự đó.

Việc tạo bean vẫn phụ thuộc dependency graph, scope, lazy initialization, `@DependsOn` và các cơ chế lifecycle khác.

Không dùng ordering để giải quyết một dependency không được khai báo. Nếu bean B cần bean A, hãy thể hiện dependency qua constructor hoặc cơ chế phù hợp.

## 11. Auto-configuration không nên được component scan

Auto-configuration nên được nạp qua file imports. Đừng đặt nó trong package mà component scan của ứng dụng vô tình phát hiện, và đừng dùng component scan bên trong auto-configuration để quét thêm class.

Thay vì:

```java
@AutoConfiguration
@ComponentScan("com.acme")
public class AcmeAutoConfiguration {
}
```

hãy import rõ configuration cần thiết:

```java
@AutoConfiguration
@Import({
        AcmeClientConfiguration.class,
        AcmeMetricsConfiguration.class
})
public class AcmeAutoConfiguration {
}
```

Lợi ích:

- Phạm vi class được đăng ký rõ ràng.
- Không vô tình kéo thêm component không liên quan.
- Dễ kiểm tra điều kiện và thứ tự.
- Giảm rủi ro cấu hình bị nạp hai lần qua imports và component scan.

Đặt auto-configuration trong package riêng như `com.acme.autoconfigure`, ngoài phạm vi component scan thông thường của ứng dụng nếu có thể.

## 12. Exclude auto-configuration khi ứng dụng không cần

Ứng dụng có thể loại một auto-configuration bằng class:

```java
@SpringBootApplication(
        exclude = AcmeClientAutoConfiguration.class
)
public class Application {
}
```

Hoặc dùng tên class:

```java
@SpringBootApplication(
        excludeName = "com.acme.autoconfigure.AcmeClientAutoConfiguration"
)
public class Application {
}
```

Hoặc property:

```properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeClientAutoConfiguration
```

Đây là cơ chế dành cho application muốn tắt auto-configuration. Khi viết starter, hãy thiết kế condition và property để người dùng có thể tùy chỉnh mà không cần exclude toàn bộ nếu chỉ muốn đổi một bean.

## 13. File AutoConfiguration.replacements khi đổi tên class

Khi thư viện đổi package hoặc đổi tên auto-configuration class, class cũ có thể đã được các cấu hình khác tham chiếu trong `before`/`after` hoặc exclusion.

Tài liệu hiện hành của Spring Boot hỗ trợ file replacement:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Ví dụ nội dung:

```properties
com.acme.autoconfigure.AcmeClientAutoConfiguration=com.acme.autoconfigure.client.AcmeClientAutoConfiguration
```

Sau khi khai báo replacement:

- File `AutoConfiguration.imports` chỉ nên liệt kê class thay thế.
- Mapping cho Spring Boot biết tên class cũ được thay bằng class mới trong các metadata auto-configuration có liên quan.
- Những cấu hình ordering/exclusion dùng tên cũ có thể được xử lý theo replacement mapping.

Đây là tính năng hữu ích khi refactor public auto-configuration class đã được module khác tham chiếu. Nếu chỉ đổi tên một class nội bộ chưa được công bố, thường không cần thêm replacement file.

## 14. Kiểm thử auto-configuration bằng ApplicationContextRunner

Không nên chỉ kiểm tra rằng JAR có file imports. Cần xác nhận condition và bean behavior.

`ApplicationContextRunner` cho phép tạo context nhỏ, thêm auto-configuration cụ thể và kiểm tra kết quả.

Ví dụ:

```java
class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    )
                    .withPropertyValues(
                            "acme.client.enabled=true",
                            "acme.client.base-url=https://api.test",
                            "acme.client.timeout=2s"
                    );

    @Test
    void createsClientWhenEnabled() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
```

Test trên giả định dependency SDK hiện diện trong test classpath.

### 14.1. Kiểm tra user bean được ưu tiên

```java
@Configuration(proxyBeanMethods = false)
static class UserConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient(
                "https://custom.test",
                Duration.ofSeconds(7)
        );
    }
}
```

Thêm user configuration:

```java
contextRunner
        .withUserConfiguration(UserConfiguration.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).baseUrl())
                    .isEqualTo("https://custom.test");
        });
```

Test này chứng minh `@ConditionalOnMissingBean` lùi lại khi ứng dụng đã cung cấp bean riêng.

### 14.2. Kiểm tra property tắt tính năng

```java
contextRunner
        .withPropertyValues("acme.client.enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
```

### 14.3. Kiểm tra dependency không có trên classpath

Có thể dùng `FilteredClassLoader` trong test để mô phỏng classpath thiếu SDK:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(AcmeSdk.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
```

Nếu auto-configuration class có method signature trực tiếp tham chiếu type optional, hãy cô lập cấu hình theo cách phù hợp để class không bị load trước khi class condition được áp dụng.

### 14.4. Kiểm tra context thực tế

`ApplicationContextRunner` hữu ích để test từng auto-configuration. Bên cạnh đó, một integration test với application context đầy đủ giúp xác nhận:

- Resource imports thực sự được đóng gói và phát hiện.
- Component scan không vô tình nạp auto-configuration.
- Các auto-configuration khác phối hợp đúng.
- Exclusion và property từ ứng dụng được áp dụng như mong đợi.

## 15. Đóng gói JAR và resource merging

Một lỗi thường gặp sau migration: file `AutoConfiguration.imports` có trong source nhưng biến mất hoặc chỉ còn một phần trong executable/uber JAR.

Nguyên nhân có thể là build tool đóng gói nhiều dependency JAR vào một archive và **ghi đè resource cùng đường dẫn** thay vì nối nội dung của chúng.

Ví dụ:

```text
dependency-a.jar:
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    com.acme.autoconfigure.AcmeAutoConfiguration

dependency-b.jar:
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    com.example.metrics.MetricsAutoConfiguration
```

Nếu quá trình shading chỉ giữ một resource, một nhóm auto-configuration có thể biến mất.

### 15.1. Maven Shade Plugin

Cấu hình transformer để append resource:

```xml
<transformer implementation=
    "org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>
        META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    </resource>
</transformer>
```

Cấu hình đầy đủ nằm bên trong phần `transformers` của Maven Shade Plugin.

### 15.2. Gradle Shadow Plugin

Với Shadow plugin, cần append resource imports:

```kotlin
tasks.shadowJar {
    append(
        "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
    )
}
```

Cú pháp cụ thể có thể thay đổi theo version plugin; kiểm tra DSL của plugin đang dùng.

### 15.3. Kiểm tra resource bên trong artifact

Sau build, xem nội dung JAR:

```bash
jar tf build/libs/acme-app.jar
```

Có thể trích file imports để xác nhận:

```bash
jar xf build/libs/acme-app.jar \
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu là executable Spring Boot JAR thông thường, resource từ dependency có thể nằm trong nested JAR ở `BOOT-INF/lib` thay vì được merge vào root. Cần kiểm tra đúng loại artifact và cách build đang sử dụng.

Với shaded/uber JAR, kiểm tra resource cuối cùng phải chứa đầy đủ candidate từ các dependency cần thiết.

## 16. Chẩn đoán khi auto-configuration không được nạp

Triệu chứng thường gặp:

- Starter đã thêm vào build nhưng bean không xuất hiện.
- Ứng dụng không lỗi nhưng client không được tạo.
- Property đã cấu hình nhưng condition không match.
- Auto-configuration class có trong source nhưng không có trong JAR.
- Chạy bằng IDE được nhưng shaded JAR thiếu một số bean.

Kiểm tra theo thứ tự:

1. Dependency starter/autoconfigure có thật sự nằm trên runtime classpath?
2. Resource imports có đúng path và được đóng gói?
3. Tên class trong file có fully qualified name chính xác?
4. Class có bị component scan hoặc import thủ công ngoài ý muốn?
5. Condition nào không match?
6. Property prefix/name/value có đúng?
7. Dependency optional có thực sự hiện diện?
8. Có exclusion qua annotation hoặc property không?
9. Resource có bị ghi đè trong shaded JAR không?
10. Boot version có hỗ trợ cơ chế registration mà artifact đang dùng không?

### 16.1. Bật debug condition report

Có thể chạy:

```bash
java -jar app.jar --debug
```

Spring Boot in condition evaluation report, giúp thấy auto-configuration nào match và điều kiện nào không match.

Đây là cách tốt để phân biệt:

- Class không được phát hiện.
- Class được phát hiện nhưng bị condition loại.
- Một bean khác khiến `@ConditionalOnMissingBean` lùi lại.
- Property condition không thỏa.

Nếu auto-configuration class hoàn toàn không xuất hiện trong report, kiểm tra resource registration và classpath trước.

### 16.2. Kiểm tra file imports trong dependency

Nếu dùng Maven, có thể xem nội dung JAR dependency bằng:

```bash
jar tf ~/.m2/repository/com/acme/acme-spring-boot-autoconfigure/1.0.0/acme-spring-boot-autoconfigure-1.0.0.jar
```

Với Gradle, tìm artifact trong cache dependency tương ứng. Không chỉ kiểm tra file source trong IDE; resource có thể bị bỏ sót trong quá trình publish module.

## 17. Các lỗi migration thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Boot 3 không tạo bean từ thư viện cũ | Chỉ đăng ký qua key EnableAutoConfiguration trong spring.factories | Chuyển sang AutoConfiguration.imports |
| Boot 2.6 không tìm thấy auto-config mới | Chỉ có file imports | Giữ spring.factories nếu còn hỗ trợ 2.6 |
| Boot 2.7 nạp candidate trùng | Cùng class có ở cả hai file | Boot 2.7 de-duplicate; kiểm tra resource và class thực tế |
| Annotation @AutoConfiguration không tồn tại | Runtime/baseline Boot thấp hơn 2.7 | Dùng @Configuration tương thích hoặc nâng baseline |
| Auto-config được đăng ký nhưng bean không xuất hiện | Condition không match | Bật --debug và kiểm tra property/classpath |
| Auto-config bị nạp hai lần | Vừa imports vừa component scan/@Import thủ công | Loại component scan/import dư |
| Shaded JAR thiếu một số auto-config | Resource cùng path bị ghi đè | Cấu hình resource append/merge |
| Boot 4 compile lỗi package | Module/API đã được modularize hoặc chuyển package | Cập nhật dependency và import theo Boot 4 |
| EnvironmentPostProcessor không được phát hiện sau nâng cấp | SPI key/package không khớp dòng Boot | Cập nhật class và spring.factories entry tương ứng |
| Custom auto-config không nhường bean của ứng dụng | Thiếu hoặc đặt sai @ConditionalOnMissingBean | Đưa condition vào auto-configuration phù hợp |

## 18. Chiến lược migration theo phiên bản đích

### 18.1. Project chỉ hỗ trợ Boot 2.6 trở xuống

- Dùng `META-INF/spring.factories`.
- Đăng ký class dưới key `EnableAutoConfiguration`.
- Dùng `@Configuration` và ordering annotation có trong version baseline.
- Không tham chiếu `@AutoConfiguration` nếu runtime thấp nhất là Boot 2.6.

### 18.2. Project hỗ trợ Boot 2.7

- Tạo `AutoConfiguration.imports`.
- Chuyển class top-level sang `@AutoConfiguration`.
- Có thể giữ entry `spring.factories` để hỗ trợ Boot 2.6.
- Boot 2.7 hỗ trợ cả hai và de-duplicate.
- Kiểm thử trên đúng version thấp nhất được công bố hỗ trợ.

### 18.3. Project chỉ hỗ trợ Boot 3.x

- Dùng `AutoConfiguration.imports`.
- Dùng `@AutoConfiguration`.
- Xóa key `EnableAutoConfiguration` khỏi `spring.factories`.
- Giữ các SPI entry khác còn cần.
- Cập nhật namespace Jakarta, Java baseline và dependency phù hợp khi nâng từ Boot 2.x.

### 18.4. Project hỗ trợ Boot 4.x

- Tiếp tục dùng `AutoConfiguration.imports`.
- Rà soát module dependency và package của Boot 4.
- Kiểm tra các class được tham chiếu trong condition, ordering và exclusion.
- Kiểm tra các SPI còn dùng `spring.factories` và key/package tương ứng.
- Cân nhắc phát hành starter line riêng cho Boot 3 và Boot 4 theo khuyến nghị migration.

## 19. Quy trình migration thực tế

Khi nâng một starter từ Boot 2.6 lên 3.x, có thể thực hiện:

### Bước 1. Liệt kê auto-configuration hiện có

Tìm entry:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

trong mọi `META-INF/spring.factories` của module.

Ghi lại toàn bộ class được liệt kê, bao gồm class đến từ module con.

### Bước 2. Tạo imports file mới

Tạo resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đưa từng class auto-configuration vào một dòng.

### Bước 3. Chuyển annotation

Nếu baseline là Boot 2.7+, dùng `@AutoConfiguration` cho class top-level. Giữ `@Configuration` cho nested/imported configuration thông thường.

Nếu phải duy trì binary tương thích Boot 2.6, xem xét annotation/API thực sự có mặt ở runtime thấp nhất.

### Bước 4. Giữ hoặc bỏ registration cũ theo ma trận hỗ trợ

- Còn hỗ trợ 2.6: giữ key cũ trong spring.factories.
- Chỉ hỗ trợ 2.7+: có thể loại key cũ.
- Hỗ trợ 2.6 và 3.x: giữ cả hai resource, đồng thời kiểm tra binary compatibility.
- Hỗ trợ Boot 3/4: dùng imports và kiểm tra package/module riêng cho từng dòng.

### Bước 5. Kiểm tra các SPI khác

Không xóa `spring.factories` nếu còn `FailureAnalyzer`, `EnvironmentPostProcessor` hoặc extension point khác đang được đăng ký ở đó.

### Bước 6. Kiểm tra artifact cuối

Mở JAR đã publish/build, xác nhận resource imports có mặt và nội dung đúng. Nếu shade/uber JAR, xác nhận resource được append.

### Bước 7. Kiểm thử theo version matrix

Chạy test context trên version thấp nhất và cao nhất mà thư viện tuyên bố hỗ trợ. Test registration, condition, custom bean back-off và optional dependency.

## 20. Những hiểu lầm thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| Boot 3 xóa toàn bộ spring.factories | **Sai** | Chỉ bỏ key đăng ký auto-configuration; SPI khác vẫn có thể dùng |
| Boot 2.7 đã không còn hỗ trợ spring.factories | **Sai** | Vẫn hỗ trợ để chuyển tiếp, nhưng deprecated |
| AutoConfiguration.imports là một file properties | **Sai** | Mỗi dòng là một class name; không dùng key=value |
| Một dòng chứa danh sách comma-separated | **Sai** | Mỗi class name nằm trên dòng riêng |
| @AutoConfiguration tồn tại ở Boot 2.6 | **Sai** | Annotation được giới thiệu ở Boot 2.7 |
| Đăng ký class đồng nghĩa bean chắc chắn được tạo | **Sai** | Condition vẫn có thể loại configuration/bean |
| @AutoConfiguration thay thế mọi @Configuration | **Sai** | Nó dành cho top-level auto-config; configuration thường vẫn dùng @Configuration |
| @AutoConfigureAfter quyết định constructor bean chạy trước | **Sai** | Nó điều khiển thứ tự auto-configuration definition |
| Có thể component scan auto-config thay vì imports | **Không nên** | Auto-config nên được nạp qua imports và không là target của component scan |
| @ConditionalOnMissingBean giống @Primary | **Sai** | Conditional quyết định đăng ký bean; Primary chọn candidate |
| Boot 2.7 tự de-duplicate hai file | **Đúng** | Nếu cùng class xuất hiện ở cả registration cũ và mới |
| Boot 4 quay lại spring.factories cho auto-config | **Sai** | Imports tiếp tục là cơ chế đăng ký auto-configuration |

## 21. Bài tập thực hành

### Bài 1. Chuyển registration từ Boot 2.6 sang 2.7

Một thư viện có file:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration
```

**Yêu cầu:**

1. Tạo file `AutoConfiguration.imports`.
2. Thêm class FQCN vào một dòng.
3. Đổi top-level class sang `@AutoConfiguration` nếu baseline từ 2.7.
4. Chạy trên Boot 2.7.
5. Xác nhận bean xuất hiện đúng một lần.

**Câu hỏi:** Vì sao có thể giữ cả hai file trong thời gian chuyển tiếp?

**Đáp án:** Boot 2.7 hỗ trợ cả registration cũ và mới, đồng thời loại candidate trùng lặp.

### Bài 2. Chuyển sang Boot 3

**Yêu cầu:**

1. Xóa key `EnableAutoConfiguration` khỏi `spring.factories`.
2. Giữ file `AutoConfiguration.imports`.
3. Giữ SPI key khác nếu còn sử dụng.
4. Chạy application context test trên Boot 3.

**Tiêu chí đạt:** auto-configuration vẫn được phát hiện; không dựa vào registration cũ.

### Bài 3. Kiểm tra @ConditionalOnMissingBean

Tạo auto-configuration cung cấp `AcmeClient` mặc định. Tạo user configuration cung cấp client tùy chỉnh.

**Yêu cầu:** test hai trường hợp:

- Không có user bean: default client được tạo.
- Có user bean: default client lùi lại và bean tùy chỉnh được sử dụng.

### Bài 4. Kiểm tra shaded JAR

Tạo hai module đều có resource imports riêng. Đóng gói vào một uber JAR.

**Câu hỏi:** Vì sao chỉ một auto-configuration xuất hiện?

**Đáp án:** Build tool có thể ghi đè resource trùng path. Cấu hình append/merge cho file imports.

### Bài 5. Migration Boot 4

Dùng một starter Boot 3 và kiểm tra:

- Package của các auto-configuration class.
- Module chứa condition và properties API.
- Dependency starter.
- SPI key trong `spring.factories`.
- Resource imports.
- Version matrix test.

Không chỉ đổi version parent/plugin; cần rà soát module và API mà starter phụ thuộc.

## 22. Ghi nhớ

- Boot 1.x–2.6 đăng ký auto-configuration qua `META-INF/spring.factories` với key `EnableAutoConfiguration`.
- Boot 2.7 giới thiệu `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, hỗ trợ cả cơ chế cũ và mới, đồng thời de-duplicate candidate.
- `@AutoConfiguration` được giới thiệu trong Boot 2.7 để đánh dấu top-level auto-configuration.
- Boot 3 bỏ key `EnableAutoConfiguration` khỏi `spring.factories`; các SPI key khác không tự động bị xóa.
- Boot 4 tiếp tục dùng imports; cần chú ý module/package migration và dependency starter.
- Mỗi dòng trong `AutoConfiguration.imports` là một fully qualified class name.
- Auto-configuration nên được nạp qua imports, không dựa vào component scan.
- `@ConditionalOnClass`, `@ConditionalOnMissingBean` và `@ConditionalOnProperty` quyết định khi nào cấu hình áp dụng.
- `@AutoConfiguration(before/after)` và ordering annotation điều khiển thứ tự xử lý auto-configuration, không quyết định constructor bean chạy trước.
- Khi đổi tên auto-configuration class đã được tham chiếu, cân nhắc `AutoConfiguration.replacements`.
- Nếu build uber/shaded JAR, phải merge resource imports từ các dependency.
- Dùng `ApplicationContextRunner` để kiểm tra auto-configuration, condition, user override và optional classpath.
- Khi migration, giữ `spring.factories` cho SPI còn cần; đừng xóa file chỉ vì chuyển registration auto-configuration.
- Kiểm thử trên version thấp nhất và cao nhất mà starter công bố hỗ trợ.

Khi nâng cấp auto-configuration, hãy xác định rõ **Boot version thấp nhất cần hỗ trợ, file registration mà version đó đọc, annotation/API có mặt ở runtime, và resource có thực sự nằm trong artifact cuối hay không**. Bốn điểm này quyết định starter có được Spring Boot phát hiện và cấu hình đúng trên từng dòng phiên bản hay không.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
