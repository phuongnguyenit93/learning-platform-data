# Tạo auto-configuration có điều kiện và back-off khi có bean người dùng

> **Spring Boot Fundamentals · Thực hành tổng hợp**  
> Auto-configuration giúp Spring Boot và các starter tích hợp với ứng dụng mà người dùng không phải khai báo từng bean. Một thư viện có thể cung cấp implementation mặc định khi classpath và cấu hình phù hợp, đồng thời **tự rút lui (back-off) khi ứng dụng đã khai báo bean riêng**. Bài học này xây dựng một auto-configuration nhỏ, đăng ký nó theo cơ chế Spring Boot, kết hợp các condition phổ biến và kiểm thử cả đường dùng mặc định lẫn đường override.

## 1. Auto-configuration giải quyết vấn đề gì?

Giả sử một ứng dụng cần dịch vụ chào hỏi:

```java
public interface GreetingService {
    String greet(String name);
}
```

Nếu mọi ứng dụng đều phải tự tạo bean:

```java
@Configuration
public class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService("Hello");
    }
}
```

thì thư viện cung cấp `GreetingService` chưa thực sự giảm cấu hình. Mỗi ứng dụng phải biết class implementation nào cần tạo và khai báo nó ra sao.

Một thư viện có thể cung cấp auto-configuration để:

- Tạo `DefaultGreetingService` khi API cần thiết có trên classpath.
- Chỉ bật tính năng khi property được bật.
- Đăng ký `GreetingProperties` để bind cấu hình.
- Tạo bean mặc định khi chưa có `GreetingService` khác.
- Nhường quyền cho ứng dụng nếu người dùng khai báo bean riêng.

Ứng dụng consumer khi đó chỉ cần thêm dependency starter và khởi động Spring Boot:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Khi dependency chứa auto-configuration đã nằm trên classpath và các condition phù hợp, Spring Boot tự phát hiện cấu hình đó.

### 1.1. Auto-configuration không phải component scanning

| Cơ chế | Cách hoạt động | Mục đích thường gặp |
| --- | --- | --- |
| Component scanning | Quét package từ cấu hình ứng dụng để tìm `@Component`, `@Service`, `@Repository` | Phát hiện bean do ứng dụng khai báo |
| Auto-configuration | Đọc danh sách cấu hình tự động trong artifact, sau đó áp dụng condition | Cung cấp cấu hình mặc định từ framework/starter |
| `@Import` | Nhập cấu hình hoặc selector được chỉ định | Kết nối một configuration cụ thể |
| `@Bean` | Đăng ký object do method tạo ra | Khai báo bean tường minh |

Auto-configuration không cần nằm dưới package của class `@SpringBootApplication` để component scan tìm thấy. Nó được phát hiện qua metadata đăng ký auto-configuration.

### 1.2. Vì sao cần điều kiện?

Một auto-configuration tốt không nên tạo bean bất kể ứng dụng có cần hay không. Nó cần trả lời:

- Thư viện cần thiết đã có trên classpath chưa?
- Người dùng có bật feature qua property không?
- Bean phụ thuộc đã tồn tại chưa?
- Người dùng đã tự tạo bean thay thế chưa?
- Ứng dụng có đang chạy trong web environment phù hợp không?
- Có một candidate bean rõ ràng để inject không?

Các annotation `@ConditionalOn...` biểu diễn những điều kiện đó.

### 1.3. Back-off là hành vi quan trọng của starter

Giả sử auto-configuration cung cấp `DefaultGreetingService`. Nếu ứng dụng khai báo:

```java
@Bean
GreetingService greetingService() {
    return new CustomGreetingService();
}
```

auto-configuration nên **không tạo thêm bean mặc định cùng vai trò**. Khi đó ứng dụng sử dụng implementation của mình.

Đây là back-off: cấu hình mặc định tự rút lui khi người dùng đã cung cấp bean phù hợp.

Back-off không có nghĩa Spring xóa bean đã tạo, tự thay implementation tại runtime hoặc merge hai object. Đó là quyết định có đăng ký bean definition trong quá trình xây dựng ApplicationContext hay không.

## 2. Các annotation điều kiện thường gặp

Spring Boot cung cấp nhiều condition để auto-configuration chỉ hoạt động khi môi trường thỏa điều kiện.

| Annotation | Kiểm tra điều gì? | Ví dụ sử dụng |
| --- | --- | --- |
| `@ConditionalOnClass` | Một hoặc nhiều class có trên classpath | Chỉ cấu hình integration khi thư viện có mặt |
| `@ConditionalOnMissingClass` | Một hoặc nhiều class không có trên classpath | Chọn fallback khi class tùy chọn vắng mặt |
| `@ConditionalOnBean` | Bean phù hợp đã được đăng ký | Tạo adapter phụ thuộc service có sẵn |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp | Tạo bean mặc định và back-off khi user override |
| `@ConditionalOnSingleCandidate` | Có một candidate duy nhất hoặc một candidate được chọn rõ | Tạo bean cần collaborator không mơ hồ |
| `@ConditionalOnProperty` | Property thỏa tên/giá trị yêu cầu | Bật/tắt feature |
| `@ConditionalOnResource` | Resource cụ thể có thể tìm thấy | Chỉ bật integration khi có file cấu hình |
| `@ConditionalOnWebApplication` | Ứng dụng chạy trong web application type phù hợp | Cấu hình Servlet/Reactive integration |
| `@ConditionalOnNotWebApplication` | Ứng dụng không phải web application | Cấu hình batch/CLI |
| `@ConditionalOnJava` | Java runtime thỏa version condition | Chọn cấu hình theo Java version |
| `@ConditionalOnExpression` | Biểu thức SpEL đánh giá thành true | Điều kiện đặc biệt, dùng có kiểm soát |

Condition có thể đặt ở class hoặc method. Đặt ở class sẽ ảnh hưởng toàn bộ bean methods bên trong; đặt ở method chỉ ảnh hưởng bean method đó.

### 2.1. `@ConditionalOnClass`

Chỉ bật cấu hình khi dependency cần thiết có trên classpath:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.metrics.MeterRegistry")
public class MetricsAutoConfiguration {
    // Cấu hình integration cho metrics library.
}
```

Thuộc tính `name` cho phép khai báo tên class dưới dạng String. Điều này hữu ích khi class có thể không có trên runtime classpath.

Một dạng khác dùng class literal:

```java
@ConditionalOnClass(MeterRegistry.class)
```

Cách này tiện khi dependency có trên compile classpath của module auto-configuration. Tuy nhiên, nếu class optional vắng mặt ở runtime, cần cẩn thận với method signatures hoặc field references trực tiếp tới class đó. Có thể tách cấu hình phụ thuộc optional type vào nested configuration có điều kiện.

### 2.2. `@ConditionalOnMissingClass`

Dùng khi muốn bật fallback nếu một thư viện không có:

```java
@AutoConfiguration
@ConditionalOnMissingClass(
        "com.vendor.fastjson.FastJsonMapper")
public class DefaultJsonAutoConfiguration {
    // Cấu hình JSON fallback.
}
```

Condition này kiểm tra classpath, không kiểm tra bean. Một class có thể tồn tại trên classpath nhưng không có bean tương ứng trong ApplicationContext.

### 2.3. `@ConditionalOnProperty`

Chỉ bật cấu hình khi property có giá trị phù hợp:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {
}
```

Các thuộc tính:

- `prefix`: phần prefix của key.
- `name`: tên property hoặc danh sách tên.
- `havingValue`: giá trị cần khớp.
- `matchIfMissing`: nếu không có property thì condition có thể coi là match hay không.

Với ví dụ trên, feature mặc định bật nếu property bị thiếu, nhưng bị tắt khi:

```properties
acme.greeting.enabled=false
```

Nếu bỏ `havingValue`, cách đánh giá mặc định thường coi property tồn tại và khác chuỗi `false` là match. Khi cần semantics rõ ràng, khai báo `havingValue` tường minh.

### 2.4. `@ConditionalOnBean`

Chỉ tạo cấu hình khi bean phụ thuộc đã được đăng ký:

```java
@Bean
@ConditionalOnBean(PaymentClient.class)
PaymentHealthIndicator paymentHealthIndicator(
        PaymentClient client) {
    return new PaymentHealthIndicator(client);
}
```

Đây là cách diễn đạt “chỉ có health indicator khi ứng dụng đã có PaymentClient bean”.

Condition chỉ có thể xét những bean definitions đã được đăng ký ở thời điểm nó được đánh giá. Với auto-configuration, thứ tự xử lý rất quan trọng nếu một cấu hình phụ thuộc bean do cấu hình khác tạo ra.

### 2.5. `@ConditionalOnMissingBean`

Đây là condition quan trọng nhất của bài học:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

Nếu context chưa có bean phù hợp kiểu `GreetingService` khi condition được đánh giá, method tạo bean mặc định. Nếu đã có bean phù hợp, method bị bỏ qua.

Dùng condition theo **contract/interface** mà người dùng cần override, thay vì chỉ theo concrete implementation mặc định. Khi đó ứng dụng có thể cung cấp implementation khác nhưng vẫn thỏa contract.

### 2.6. `@ConditionalOnSingleCandidate`

Một auto-configuration có thể cần collaborator nhưng không muốn tạo bean nếu có nhiều candidate mơ hồ:

```java
@Bean
@ConditionalOnSingleCandidate(DataSource.class)
DatabaseInspector databaseInspector(DataSource dataSource) {
    return new DatabaseInspector(dataSource);
}
```

Condition có thể match khi chỉ có một candidate phù hợp hoặc có một candidate được đánh dấu primary để lựa chọn rõ. Điều này giúp tránh cấu hình integration trong context có nhiều datasource nhưng không có lựa chọn mặc định.

### 2.7. `@ConditionalOnResource`

Ví dụ chỉ bật cấu hình nếu file schema có mặt:

```java
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:/acme/schema.sql")
public class SchemaAutoConfiguration {
}
```

Resource được kiểm tra theo cơ chế resource lookup của Spring. Nếu resource được tạo ở build time, hãy bảo đảm nó thực sự được đóng gói vào artifact.

### 2.8. `@ConditionalOnWebApplication`

Ví dụ cấu hình chỉ áp dụng cho Servlet web application:

```java
@AutoConfiguration
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class GreetingWebAutoConfiguration {
}
```

Có thể chọn kiểu reactive khi integration dành cho WebFlux. Không dùng điều kiện web chỉ vì starter có REST endpoint nếu bean đó cũng có thể hữu ích trong batch/CLI.

## 3. Thiết kế auto-configuration theo contract

Trước khi viết annotation, xác định rõ:

1. Auto-configuration cung cấp bean nào?
2. Contract nào là điểm extension cho ứng dụng?
3. Dependency nào bắt buộc và dependency nào optional?
4. Property nào điều khiển feature?
5. User bean nào khiến default phải back-off?
6. Điều kiện nào khiến toàn bộ configuration không áp dụng?
7. Ai chịu trách nhiệm khởi tạo và đóng resource?

Ví dụ:

```text
Acme Greeting Auto-configuration
    |
    +-- Condition: GreetingService API available
    |
    +-- Condition: acme.greeting.enabled != false
    |
    +-- Enable GreetingProperties
    |
    +-- If no GreetingService bean:
    |       create DefaultGreetingService
    |
    +-- If user provides GreetingService:
            back off
```

Thiết kế contract trước giúp tránh việc condition phụ thuộc class nội bộ mà ứng dụng không thể thay thế.

## 4. Xây dựng ví dụ Greeting Auto-configuration

Ta sẽ tạo một auto-configuration cung cấp dịch vụ chào hỏi với prefix có thể cấu hình.

### 4.1. Cấu trúc module

Một module auto-configuration có thể có cấu trúc:

```text
acme-greeting-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/greeting/
    │   │   ├── GreetingService.java
    │   │   ├── DefaultGreetingService.java
    │   │   ├── GreetingProperties.java
    │   │   └── autoconfigure/
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/greeting/autoconfigure/
            └── GreetingAutoConfigurationTest.java
```

Trong dự án lớn, có thể tách API và implementation thành module riêng. Bài thực hành giữ một module để tập trung vào cơ chế auto-configuration.

### 4.2. Interface extension point

```java
package com.acme.greeting;

public interface GreetingService {

    String greet(String name);
}
```

Interface này là contract mà ứng dụng sử dụng và có thể tự triển khai.

### 4.3. Default implementation

```java
package com.acme.greeting;

public final class DefaultGreetingService
        implements GreetingService {

    private final String prefix;

    public DefaultGreetingService(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return prefix + ", " + name.trim();
    }
}
```

Class này là Java object thông thường. Nó không cần `@Component`, `@Service` hay import Spring. Auto-configuration sẽ quyết định khi nào tạo instance.

### 4.4. Configuration properties

```java
package com.acme.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    /**
     * Prefix used by the default greeting implementation.
     */
    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

Properties object giữ giá trị cấu hình. Default value `Hello` cho phép ứng dụng dùng starter mà không cần khai báo property.

Có thể bổ sung Bean Validation như `@NotBlank` nếu project có validation provider phù hợp. Khi đó cần quyết định rõ lỗi property rỗng được phát hiện lúc bind hay trong constructor/service.

### 4.5. Auto-configuration class

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingProperties;
import com.acme.greeting.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {

        return new DefaultGreetingService(
                properties.getPrefix());
    }
}
```

Các phần cần chú ý:

- `@AutoConfiguration` đánh dấu class là Boot auto-configuration.
- `@ConditionalOnClass` yêu cầu API của greeting có trên classpath.
- `@ConditionalOnProperty` điều khiển feature.
- `@EnableConfigurationProperties` đăng ký properties bean.
- `@Bean` tạo default service.
- `@ConditionalOnMissingBean(GreetingService.class)` giúp user override.

### 4.6. Đăng ký auto-configuration bằng imports file

Tạo file chính xác:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Mỗi dòng là fully qualified class name của một auto-configuration cần Spring Boot phát hiện.

Đây là cơ chế đăng ký auto-configuration tiêu chuẩn trong Spring Boot 3. Không cần thêm `@ComponentScan` cho package này.

### 4.7. Auto-configuration có cần `@Component` không?

Không. `@AutoConfiguration` đã đánh dấu configuration class phù hợp với cơ chế auto-configuration của Boot. Thêm `@Component` thường không cần thiết và có thể khiến class bị phát hiện qua component scan ngoài ý định nếu package nằm trong vùng scan.

Giữ package auto-configuration tách khỏi package ứng dụng để tránh phụ thuộc vào cách consumer tổ chức component scan.

## 5. Back-off khi ứng dụng cung cấp bean riêng

Bây giờ ứng dụng muốn dùng lời chào riêng:

```java
package com.example.demo;

import com.acme.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return name -> "Welcome, " + name + "!";
    }
}
```

Vì auto-configuration có:

```java
@ConditionalOnMissingBean(GreetingService.class)
```

nên khi bean của người dùng đã được đăng ký trước thời điểm auto-configuration condition được đánh giá, default bean không được tạo.

Kết quả mong muốn:

```text
ApplicationContext
    |
    +-- CustomGreetingConfiguration
    |       └── GreetingService (user implementation)
    |
    +-- GreetingAutoConfiguration
            └── GreetingService default: BACK OFF
```

### 5.1. Vì sao condition cần xét interface?

Giả sử default implementation là `DefaultGreetingService`, user implementation là `FriendlyGreetingService`. Nếu condition viết:

```java
@ConditionalOnMissingBean(DefaultGreetingService.class)
```

thì bean user kiểu `FriendlyGreetingService` không làm condition back-off, vì nó không phải `DefaultGreetingService`. Auto-configuration có thể tạo thêm default service và khiến injection theo `GreetingService` trở nên ambiguous.

Điều kiện nên xét contract:

```java
@ConditionalOnMissingBean(GreetingService.class)
```

### 5.2. Nên khai báo return type của @Bean rõ ràng

Ví dụ tốt:

```java
@Bean
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

Nếu khai báo return type là class quá cụ thể hoặc `Object`, một số condition/type prediction ở giai đoạn xử lý bean definition có thể không có đủ thông tin để nhận diện contract mong muốn.

Khi bean được tiêu thụ theo interface, khai báo return type interface và dùng condition theo interface giúp ý định rõ ràng.

### 5.3. Bean user có thể nằm ở package khác

Không cần user configuration cùng package với auto-configuration. Chỉ cần nó được đăng ký vào cùng ApplicationContext trước khi auto-configuration bean condition cần xét.

Đó là lý do auto-configuration được Boot xử lý theo cơ chế riêng, với ordering phù hợp sau các user configuration thông thường.

### 5.4. Không tạo hai bean cùng contract rồi trông chờ @Primary giải quyết

`@Primary` có thể chọn một bean khi inject theo type, nhưng nó không thay thế mục tiêu back-off. Nếu auto-configuration tạo default dù user đã cung cấp custom bean, context có thể vẫn chứa hai instance, làm behavior khác ý định và gây khó quan sát.

Dùng `@ConditionalOnMissingBean` để ngăn tạo default ngay từ đầu.

## 6. Back-off theo bean name hay bean type?

`@ConditionalOnMissingBean` có nhiều cách dùng.

### 6.1. Theo type

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

Cách này phổ biến nhất khi user có thể cung cấp bất kỳ implementation nào của contract.

### 6.2. Theo name

```java
@Bean
@ConditionalOnMissingBean(name = "customGreetingService")
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

Cách này phù hợp khi extension contract được định nghĩa bằng bean name, nhưng thường kém linh hoạt hơn type-based contract.

### 6.3. Kết hợp type và annotation

Condition có thể được cấu hình để xét những bean có annotation hoặc type cụ thể. Chỉ nên làm khi đó là contract có chủ đích.

Không nên tạo condition phức tạp dựa trên nhiều bean name bí mật. Người dùng starter cần biết họ có thể override bằng cách nào.

### 6.4. Search strategy

`@ConditionalOnMissingBean` có thể tìm trong context hiện tại hoặc xét cả ancestor context theo search strategy. Với ứng dụng có parent/child ApplicationContext, cần quyết định default bean có nên back-off khi bean tồn tại ở parent hay không.

Trong ứng dụng Boot thông thường chỉ có một context chính, default search behavior thường đủ. Chỉ tùy chỉnh khi kiến trúc thực sự dùng context hierarchy và có test tương ứng.

## 7. Condition ở class level và method level

### 7.1. Class-level condition

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true")
public class GreetingAutoConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService("Hello");
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Khi property không match, toàn bộ auto-configuration class không được áp dụng. Cả hai bean methods đều không tạo bean.

### 7.2. Method-level condition

```java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.greeting",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {
        return new DefaultGreetingService(
                properties.getPrefix());
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Ở đây property chỉ điều khiển bean `GreetingService`, còn `GreetingFormatter` vẫn được tạo.

### 7.3. Chọn scope condition theo dependency

Nếu toàn bộ feature không có ý nghĩa khi property tắt, đặt condition ở class level giúp tránh đăng ký các bean liên quan. Nếu chỉ một bean optional bị tắt nhưng các bean khác vẫn hữu ích, đặt condition trên method.

Không lặp cùng condition ở class và method nếu không tạo thêm ý nghĩa.

## 8. Condition evaluation và thứ tự auto-configuration

Một lỗi thiết kế phổ biến là cho rằng Spring chờ tất cả bean trong context được tạo xong rồi mới đánh giá `@ConditionalOnMissingBean`. Thực tế condition được đánh giá trong quá trình configuration parsing và bean definition registration.

### 8.1. Vì sao thứ tự quan trọng?

Giả sử auto-configuration A cần biết bean do auto-configuration B cung cấp. Nếu A được xử lý trước B, condition `@ConditionalOnBean` trong A có thể chưa thấy bean đó.

Spring Boot cho phép khai báo thứ tự auto-configuration:

- `@AutoConfigureBefore`.
- `@AutoConfigureAfter`.
- `@AutoConfigureOrder`.
- Các thuộc tính `before`/`after`/`beforeName`/`afterName` trên `@AutoConfiguration` ở các phiên bản hỗ trợ tương ứng.

Ví dụ:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseAuditAutoConfiguration {
}
```

Cấu hình này yêu cầu auto-configuration audit được xét sau DataSource auto-configuration.

### 8.2. Ordering không phải thứ tự khởi tạo singleton

`@AutoConfigureAfter` điều khiển thứ tự xử lý auto-configuration, không bảo đảm bean trong class đó được khởi tạo ngay sau bean trong class kia.

Bean singleton thường được tạo theo dependency graph và lifecycle của context. Nếu bean A cần bean B, thể hiện dependency qua method parameter/constructor thay vì dựa vào thứ tự khai báo configuration.

### 8.3. User configuration thường được xử lý trước auto-configuration

Spring Boot thiết kế auto-configuration để lùi sau cấu hình do ứng dụng khai báo. Nhờ đó `@ConditionalOnMissingBean` có thể nhìn thấy user bean và back-off.

Trong custom setup có nhiều configuration import, parent/child contexts hoặc ordering đặc biệt, cần kiểm tra condition report và test. Đừng dựa vào vị trí class trong source tree.

### 8.4. Không dùng @Order để thay thế dependency

Nếu `SecondConfiguration` cần bean từ `FirstConfiguration`, hãy inject bean đó hoặc dùng auto-configuration ordering phù hợp cho hai auto-configurations. `@Order` trên nhiều loại Spring components có semantics riêng và không phải công cụ tổng quát để điều khiển mọi bean creation.

## 9. Điều kiện theo classpath và optional dependencies

Starter thường có integration chỉ hoạt động nếu thư viện bên ngoài có mặt.

Ví dụ auto-configuration metrics chỉ được bật khi vendor metrics API có trên classpath.

### 9.1. Tách optional integration thành nested configuration

```java
@AutoConfiguration
public class AcmeMetricsAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.vendor.metrics.MeterRegistry")
    static class MetricsConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MetricsReporter metricsReporter(
                com.vendor.metrics.MeterRegistry registry) {
            return new VendorMetricsReporter(registry);
        }
    }
}
```

Ý tưởng là chỉ khi optional class có mặt, nested configuration mới được áp dụng. Việc tách này giúp tránh load các method signatures phụ thuộc optional type quá sớm.

Trong module compile, dependency vendor có thể cần ở compile classpath để biên dịch code, nhưng không nhất thiết phải được đóng gói như dependency bắt buộc cho mọi consumer. Cách khai báo optional/runtime scope phụ thuộc Maven/Gradle module design.

### 9.2. Dùng tên class trong condition khi dependency optional

```java
@ConditionalOnClass(
        name = "com.vendor.metrics.MeterRegistry")
```

String class name không yêu cầu JVM resolve class literal ở thời điểm đọc annotation. Đây là cách hữu ích khi muốn bảo đảm condition có thể đánh giá ngay cả khi optional class vắng mặt.

### 9.3. Không tham chiếu optional class ở outer configuration

Nếu outer auto-configuration có method parameter, field hoặc return type tham chiếu trực tiếp class optional, classloader có thể gặp lỗi khi class đó không tồn tại.

Hãy đặt mọi reference tới optional API bên trong nested configuration được bảo vệ bởi class condition. Điều này đặc biệt quan trọng khi starter hỗ trợ nhiều classpath combinations.

### 9.4. `@ConditionalOnClass` không thay thế dependency management

Condition chỉ quyết định có áp dụng cấu hình không. Nó không tải dependency, không chọn version và không sửa conflict.

Nếu class tồn tại nhưng version quá cũ, code vẫn có thể lỗi `NoSuchMethodError` hoặc `NoClassDefFoundError`. Có thể cần version condition hoặc kiểm tra compatibility theo contract của library.

## 10. Kết hợp nhiều condition

Auto-configuration thực tế thường có nhiều điều kiện cùng lúc.

```java
@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {
        return new DefaultGreetingService(
                properties.getPrefix());
    }
}
```

Các condition ở cùng class được kết hợp theo logic AND: tất cả phải match để class-level configuration áp dụng. Bean method còn có condition riêng của nó.

### 10.1. Ví dụ điều kiện theo property và bean

```java
@Bean
@ConditionalOnBean(PaymentClient.class)
@ConditionalOnMissingBean(PaymentHealthIndicator.class)
PaymentHealthIndicator paymentHealthIndicator(
        PaymentClient client) {
    return new PaymentHealthIndicator(client);
}
```

Ý nghĩa:

- Có `PaymentClient` bean.
- Chưa có `PaymentHealthIndicator` bean.
- Khi cả hai điều kiện thỏa, tạo health indicator mặc định.

### 10.2. Tránh condition dư thừa

Nếu bean method có parameter `PaymentClient` bắt buộc, Spring vốn cần bean đó khi tạo method. `@ConditionalOnBean` vẫn có giá trị để ngăn đăng ký bean definition khi dependency không tồn tại, giúp context behavior và condition report rõ hơn.

Nhưng không cần thêm mọi condition có thể nghĩ ra. Mỗi condition nên thể hiện một yêu cầu có ý nghĩa đối với người dùng starter.

### 10.3. Property condition và properties binding là hai bước khác nhau

`@ConditionalOnProperty` đọc Environment để quyết định cấu hình có được áp dụng hay không. `@EnableConfigurationProperties` đăng ký object để bind nhiều property thành bean có kiểu.

Condition không tự tạo properties bean. Properties bean cũng không tự bật/tắt auto-configuration trừ khi được dùng trong một điều kiện phù hợp.

## 11. Tạo starter module để người dùng chỉ cần thêm dependency

Trong một hệ sinh thái thư viện, thường tách:

- `acme-greeting-spring-boot-autoconfigure`: chứa auto-configuration, properties, default implementation.
- `acme-greeting-spring-boot-starter`: dependency aggregator kéo auto-config và các integration cần thiết.

Cấu trúc:

```text
acme-greeting/
├── acme-greeting-core/
├── acme-greeting-spring-boot-autoconfigure/
└── acme-greeting-spring-boot-starter/
```

### 11.1. Core module

Chứa contract và implementation thuần Java:

```text
acme-greeting-core
├── GreetingService.java
└── DefaultGreetingService.java
```

Core không nhất thiết phụ thuộc Spring Boot.

### 11.2. Auto-configure module

Chứa:

- `GreetingAutoConfiguration`.
- `GreetingProperties`.
- `AutoConfiguration.imports`.
- Configuration processor metadata nếu muốn IDE completion.
- Tests cho conditions/back-off.

Module này phụ thuộc Spring Boot autoconfigure và core API.

### 11.3. Starter module

Starter thường rất mỏng:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-greeting-spring-boot-autoconfigure</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Starter có thể thêm integration dependency phù hợp với mục tiêu. Không nhất thiết starter phải chứa source code.

### 11.4. Vì sao tách auto-config và starter?

Lợi ích:

- Người dùng thêm starter mà không phải tự liệt kê mọi dependency.
- Auto-config có thể được dùng riêng khi cần kiểm soát dependency.
- Core library có thể tái sử dụng ngoài Spring Boot.
- Có thể tạo nhiều starter khác nhau cho các integration khác nhau nhưng dùng chung core.

Với thư viện nhỏ, có thể gộp module để giảm complexity. Tách module khi nó tạo ra ranh giới build/reuse có ý nghĩa.

## 12. Dependency cần thiết trong auto-configuration module

Ví dụ Maven tối giản:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-greeting-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Spring Boot parent/BOM quản lý version tương thích. Nếu không dùng parent, import Boot dependency BOM hoặc khai báo version theo dependency management của project.

### 12.1. Configuration processor

`spring-boot-configuration-processor` hỗ trợ sinh metadata cho `@ConfigurationProperties` để IDE gợi ý property. Nó thường là dependency optional/annotation processor theo build tool.

Nó không phải runtime requirement để binding hoạt động. Runtime binding đến từ Spring Boot infrastructure.

### 12.2. Test dependencies

`spring-boot-starter-test` cung cấp các công cụ test phù hợp cho Spring Boot. Auto-configuration module có thể dùng `ApplicationContextRunner` để test nhanh từng điều kiện mà không phải khởi động cả ứng dụng demo.

### 12.3. Đừng đưa optional integration thành transitive bắt buộc

Nếu metrics library chỉ cần khi user bật metrics integration, cân nhắc khai báo nó optional hoặc tách integration module riêng. Một starter tốt không ép mọi consumer kéo tất cả client libraries không dùng.

## 13. Đăng ký auto-configuration trong Spring Boot 3

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Một entry mỗi dòng:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingMetricsAutoConfiguration
```

Spring Boot đọc metadata này để tìm auto-configuration classes.

### 13.1. Không dùng component scan làm discovery

Nếu auto-configuration được tìm thấy chỉ vì package nằm trong scan root của ứng dụng, starter sẽ hoạt động không ổn định khi consumer đặt application class ở package khác.

Đăng ký bằng imports metadata giúp starter được phát hiện độc lập với package của consumer.

### 13.2. Một auto-configuration có thể import configuration con

Có thể dùng nested configuration hoặc `@Import` để chia nhỏ cấu hình. Tuy nhiên, class cần optional dependency vẫn phải được bảo vệ để không bị load khi dependency vắng mặt.

### 13.3. Không đăng ký trùng một class theo nhiều cách

Nếu một auto-configuration vừa được liệt kê trong imports file vừa được component scan/explicit import theo cách khác, có thể gây configuration duplication hoặc khó đọc behavior.

Giữ một cơ chế discovery rõ ràng cho auto-configuration class.

### 13.4. Khác biệt với Spring Boot 2 cũ

Các dự án Spring Boot 2 đời trước thường đăng ký auto-configuration qua key `EnableAutoConfiguration` trong `META-INF/spring.factories`. Spring Boot 3 sử dụng `AutoConfiguration.imports` cho danh sách auto-configuration.

Khi nâng starter cũ, cần migration metadata registration theo version target. Không xóa mọi `spring.factories` file một cách máy móc nếu nó còn chứa các Spring factories khác ngoài auto-configuration.

## 14. Viết test bằng ApplicationContextRunner

`ApplicationContextRunner` là công cụ rất phù hợp để test auto-configuration. Nó tạo một context nhỏ, áp dụng configuration được chỉ định, cho phép cung cấp properties và kiểm tra bean outcome.

### 14.1. Test default bean

```java
package com.acme.greeting.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.acme.greeting.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void createsDefaultGreetingService() {
        contextRunner
                .withPropertyValues(
                        "acme.greeting.enabled=true",
                        "acme.greeting.prefix=Hi")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);

                    GreetingService service =
                            context.getBean(GreetingService.class);

                    assertThat(service.greet("Lan"))
                            .isEqualTo("Hi, Lan");
                });
    }
}
```

Test này kiểm tra:

- Auto-configuration được áp dụng.
- Property condition match.
- Properties được bind.
- Default bean được tạo.
- Default implementation dùng prefix đã cấu hình.

### 14.2. Test back-off khi user cung cấp bean

```java
@Test
void backsOffWhenUserProvidesGreetingService() {
    contextRunner
            .withUserConfiguration(
                    UserGreetingConfiguration.class)
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(GreetingService.class);

                GreetingService service =
                        context.getBean(GreetingService.class);

                assertThat(service.greet("Lan"))
                        .isEqualTo("Welcome, Lan!");
            });
}

@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Welcome, " + name + "!";
    }
}
```

Test quan trọng nhất của bài học: user bean đã tồn tại, auto-configuration phải back-off và context chỉ có một `GreetingService`.

### 14.3. Test property tắt feature

```java
@Test
void doesNotCreateGreetingServiceWhenDisabled() {
    contextRunner
            .withPropertyValues(
                    "acme.greeting.enabled=false")
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(GreetingService.class);
            });
}
```

Đây là test class-level property condition. Nếu property không match, configuration không được áp dụng.

### 14.4. Test property mặc định khi bị thiếu

Vì condition dùng `matchIfMissing = true`, cần kiểm tra cả trường hợp không khai báo `acme.greeting.enabled`:

```java
@Test
void enablesGreetingByDefault() {
    contextRunner.run(context -> {
        assertThat(context)
                .hasSingleBean(GreetingService.class);
    });
}
```

Test này xác nhận semantics default của feature. Nếu sau này đổi `matchIfMissing` thành false, test sẽ phát hiện thay đổi contract.

### 14.5. Test user bean vẫn hoạt động khi property không có

Nếu feature mặc định bật nhưng user cung cấp bean riêng, default bean phải back-off. Có thể test cả khi property không được khai báo và khi property bật tường minh.

Điều này giúp bảo đảm back-off không phụ thuộc vào một giá trị property cụ thể ngoài điều kiện class-level đã định nghĩa.

### 14.6. Context runner test không kiểm tra imports file

Trong ví dụ, `AutoConfigurations.of(GreetingAutoConfiguration.class)` chỉ định trực tiếp auto-configuration class. Nó kiểm tra condition và bean behavior, nhưng không chứng minh metadata file được đóng gói/đọc đúng.

Cần thêm smoke test consumer hoặc test artifact để xác nhận `AutoConfiguration.imports` có trong JAR và Spring Boot tự phát hiện nó.

## 15. Kiểm tra discovery qua application context thật

Tạo demo application phụ thuộc starter:

```java
@SpringBootApplication
public class GreetingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                GreetingDemoApplication.class, args);
    }
}
```

Controller:

```java
@RestController
public class GreetingController {

    private final GreetingService greetings;

    public GreetingController(GreetingService greetings) {
        this.greetings = greetings;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam String name) {
        return greetings.greet(name);
    }
}
```

Application config:

```yaml
acme:
  greeting:
    enabled: true
    prefix: Xin chào
```

Khi chạy, gọi:

```text
GET /greet?name=An
```

Kết quả dự kiến:

```text
Xin chào, An
```

Test này xác nhận auto-configuration được phát hiện qua imports metadata trong consumer classpath, không chỉ do test chỉ định class trực tiếp.

### 15.1. Kiểm tra consumer override

Thêm user configuration vào demo:

```java
@Configuration(proxyBeanMethods = false)
public class DemoGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return name -> "Chào mừng, " + name + "!";
    }
}
```

Endpoint phải trả behavior của user implementation. Nếu context báo hai bean cùng type, hãy kiểm tra `@ConditionalOnMissingBean` có xét đúng interface không và auto-configuration có được xử lý đúng thứ tự không.

## 16. Kiểm tra condition report

Khi bean không xuất hiện hoặc default bean không back-off, condition report giúp biết condition nào match hoặc không match.

Có thể chạy ứng dụng với debug:

```bash
java -jar greeting-demo.jar --debug
```

Hoặc đặt:

```properties
debug=true
```

Spring Boot có thể in Condition Evaluation Report, bao gồm positive matches và negative matches của auto-configuration.

### 16.1. Những điều cần tìm

Nếu default bean không được tạo, tìm:

- Auto-configuration class có được nhận diện không?
- `@ConditionalOnClass` có match không?
- `@ConditionalOnProperty` có match không?
- `@ConditionalOnMissingBean` có thấy user bean không?
- Có condition khác trên nested configuration/method không?
- Configuration class có bị exclude khỏi auto-configuration không?

### 16.2. Auto-configuration không được import

Nếu class không xuất hiện trong condition report:

1. Kiểm tra file imports path chính xác.
2. Kiểm tra nội dung FQCN.
3. Kiểm tra JAR artifact có chứa resource.
4. Kiểm tra dependency starter/autoconfigure có trên runtime classpath.
5. Kiểm tra class name và package đã đúng sau refactor.
6. Kiểm tra cấu hình exclude.

Đừng vội thêm `@ComponentScan` để che việc metadata không được đóng gói.

### 16.3. Condition report là công cụ chẩn đoán

Condition report cho biết quyết định của auto-configuration theo môi trường khởi động đó. Nó không tự chứng minh mọi method trong bean đã chạy đúng hoặc external service có kết nối thành công.

Kết hợp report với context test và assertion hành vi.

## 17. Các condition nâng cao và trường hợp sử dụng

### 17.1. `@ConditionalOnMissingBean` với nhiều bean

Giả sử ứng dụng có hai bean `GreetingService`:

```java
@Bean
@Primary
GreetingService primaryGreetingService() {
    return name -> "Primary " + name;
}

@Bean
GreetingService secondaryGreetingService() {
    return name -> "Secondary " + name;
}
```

Condition `@ConditionalOnMissingBean(GreetingService.class)` sẽ thấy bean phù hợp đã tồn tại và back-off. `@Primary` chỉ quyết định candidate khi injection theo type, không làm condition coi như không có bean.

### 17.2. `@ConditionalOnSingleCandidate` với nhiều DataSource

Nếu chỉ có một DataSource hoặc một DataSource được đánh dấu primary, condition có thể match. Nếu có nhiều DataSource không có candidate rõ ràng, bean phụ thuộc DataSource đơn lẻ sẽ không được tạo.

Điều này hữu ích cho auto-configuration cần chọn một datasource mặc định. Nếu integration hỗ trợ nhiều datasource, hãy thiết kế bean theo qualifier hoặc cấu hình rõ ràng thay vì ép một lựa chọn ngầm.

### 17.3. `@ConditionalOnBean` với loại bean cụ thể

Ví dụ chỉ tạo adapter khi user đã khai báo một client:

```java
@Bean
@ConditionalOnBean(Clock.class)
TimeAwareGreetingService timeAwareGreetingService(
        Clock clock) {
    return new TimeAwareGreetingService(clock);
}
```

Nếu Clock không có, bean không được tạo. Trong thực tế, nếu có default Clock phù hợp, auto-configuration có thể tạo Clock trước rồi các configuration sau sử dụng nó. Hãy thể hiện ordering và back-off rõ ràng.

### 17.4. `@ConditionalOnExpression`

Có thể dùng SpEL khi điều kiện cần biểu thức. Nhưng property condition chuyên biệt thường rõ hơn, dễ đọc hơn và có condition report dễ hiểu hơn. Tránh đưa logic phức tạp vào SpEL vì khó kiểm tra và dễ phụ thuộc type conversion.

### 17.5. `@ConditionalOnJava`

Có thể bật cấu hình theo Java runtime:

```java
@AutoConfiguration
@ConditionalOnJava(
        range = ConditionalOnJava.Range.EQUAL_OR_NEWER,
        value = JavaVersion.TWENTY_ONE)
public class Java21AutoConfiguration {
}
```

Chỉ dùng khi integration thực sự cần runtime version cụ thể. Không nên dùng condition để che một dependency không tương thích; tốt hơn là đặt baseline và version requirement rõ trong artifact metadata/documentation.

## 18. Ordering giữa nhiều auto-configuration

Giả sử một starter có hai cấu hình:

- `CoreAutoConfiguration` tạo core service.
- `WebAutoConfiguration` tạo web support cần core service.

Có thể khai báo:

```java
@AutoConfiguration
public class CoreAutoConfiguration {
    // Core beans.
}
```

```java
@AutoConfiguration(after = CoreAutoConfiguration.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class WebAutoConfiguration {
    // Web beans.
}
```

Nếu cần tham chiếu cấu hình của dependency optional, dùng name-based ordering phù hợp để tránh class literal khiến optional class phải được resolve sớm.

### 18.1. Ordering không sửa được dependency thiếu

Nếu Web configuration yêu cầu core bean nhưng Core configuration không match vì property tắt, chỉ đổi thứ tự không làm bean xuất hiện. Cần xác định condition logic có phù hợp hay không.

### 18.2. Không dựa vào thứ tự alphabet

Tên class hoặc thứ tự dòng trong imports file không phải API contract để sắp xếp bean. Dùng annotation ordering và dependency graph rõ ràng.

### 18.3. Tránh vòng condition

Nếu A chỉ tạo khi có bean B và B chỉ tạo khi có bean A, cả hai có thể không bao giờ được tạo. Đây là vòng phụ thuộc ở mức configuration condition.

Hãy tìm điểm khởi tạo độc lập hoặc gom các bean có quan hệ chặt vào một configuration có logic rõ ràng.

## 19. Auto-configuration properties và metadata cho IDE

Auto-configuration thường cung cấp `@ConfigurationProperties` để consumer cấu hình feature.

Ví dụ:

```yaml
acme:
  greeting:
    enabled: true
    prefix: Welcome
```

Properties class:

```java
@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

### 19.1. Đăng ký properties bean

Có thể dùng:

```java
@EnableConfigurationProperties(GreetingProperties.class)
```

trên auto-configuration class. Điều này bảo đảm properties type được đăng ký khi configuration áp dụng.

Nếu class properties được component scan/registered theo cách khác, có thể không cần thêm cơ chế đăng ký nữa, nhưng starter nên có một đường rõ ràng và nhất quán.

### 19.2. Metadata processor

`spring-boot-configuration-processor` hỗ trợ sinh metadata cho `@ConfigurationProperties` để IDE gợi ý property name, type, description và default value.

Metadata phục vụ developer experience. Nó không phải nguồn runtime truth và không thay thế validation/binding.

### 19.3. Viết description hữu ích

Javadoc trên property field hoặc metadata bổ sung có thể giải thích:

- Property có tác dụng gì.
- Default value.
- Giá trị hợp lệ.
- Khi nào cần bật/tắt.
- Có thể override bằng bean hay không.

Một starter dễ sử dụng cần tài liệu hóa cả property lẫn extension points.

## 20. Back-off không phải override mọi bean của starter

Nếu auto-configuration tạo nhiều bean:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() { ... }

@Bean
GreetingFormatter greetingFormatter() { ... }

@Bean
GreetingMetrics greetingMetrics() { ... }
```

User cung cấp `GreetingService` chỉ làm bean method đó back-off. `GreetingFormatter` và `GreetingMetrics` vẫn có thể được tạo.

Nếu các bean phụ thuộc trực tiếp vào default implementation, cần thiết kế để chúng phụ thuộc contract `GreetingService` thay vì `DefaultGreetingService`.

### 20.1. Dependency theo interface

Tốt:

```java
@Bean
GreetingFacade greetingFacade(GreetingService service) {
    return new GreetingFacade(service);
}
```

Kém linh hoạt:

```java
@Bean
GreetingFacade greetingFacade(
        DefaultGreetingService service) {
    return new GreetingFacade(service);
}
```

Khi user override service bằng implementation khác, bean thứ hai không thể inject được.

### 20.2. Condition theo bean người dùng cho cả nhóm

Nếu một nhóm bean mặc định chỉ có ý nghĩa khi chưa có extension interface tổng thể, có thể đặt condition ở configuration class hoặc từng bean tùy mục tiêu. Hãy kiểm tra behavior khi user override một bean nhưng vẫn muốn các bean phụ trợ khác.

Không đặt `@ConditionalOnMissingBean` trên cả configuration class nếu điều đó vô tình làm mất các bean infrastructure vẫn cần khi user cung cấp implementation riêng.

## 21. Những sai lầm thường gặp khi viết auto-configuration

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên `AutoConfiguration.imports` | Boot không phát hiện auto-config | Kiểm tra resource path và nội dung artifact |
| Dùng component scan làm discovery | Hoạt động phụ thuộc package consumer | Đăng ký qua imports metadata |
| Thiếu `@ConditionalOnMissingBean` | Tạo default trùng với user bean | Back-off theo contract interface |
| Condition theo concrete class | Custom implementation không làm back-off | Condition theo API type |
| Dùng `@ConditionalOnBean` sai thứ tự | Condition không thấy bean cần thiết | Xem auto-config ordering |
| Dùng `@ConditionalOnProperty` không rõ default | Feature bật/tắt bất ngờ | Khai báo `havingValue` và `matchIfMissing` |
| Optional class xuất hiện trong outer method signature | Lỗi class loading khi dependency thiếu | Tách nested configuration có class condition |
| Pin dependency version tùy tiện | Xung đột với Boot BOM | Dùng dependency management |
| Dùng `@Order` để điều khiển mọi bean | Hiểu sai semantics ordering | Dùng dependency injection và auto-config ordering |
| Tạo bean phụ thuộc concrete default implementation | User override không hoạt động | Phụ thuộc interface |
| Dùng `@Primary` thay back-off | Context có nhiều bean không cần thiết | Ngăn tạo default từ đầu |
| Condition vòng A cần B, B cần A | Không cấu hình nào được tạo | Xác định root condition |
| Test chỉ gọi class trực tiếp | Không kiểm tra Spring conditions | Dùng ApplicationContextRunner |
| Chỉ test context runner, không test imports file | Có thể metadata đóng gói bị thiếu | Thêm consumer smoke test |
| Đặt auto-config trong package component scan | Có thể bị đăng ký trùng | Tách package và dùng imports |
| Tạo quá nhiều condition | Starter khó dự đoán | Giữ condition tối thiểu có ý nghĩa |

## 22. Debug khi bean mặc định không back-off

Nếu context báo:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

hãy kiểm tra theo thứ tự:

1. User bean có thực sự được đăng ký vào cùng ApplicationContext không?
2. User bean có assignable từ interface condition đang xét không?
3. `@ConditionalOnMissingBean` có xét đúng type/name không?
4. Auto-configuration có được xử lý sau user configuration không?
5. Có auto-configuration khác cũng tạo bean cùng contract không?
6. Bean method có return type quá cụ thể/không đủ metadata không?
7. User configuration có bị condition/profile loại bỏ không?
8. Có parent/child context và search strategy khác mong đợi không?

### 22.1. Kiểm tra bean definitions

Trong test có thể xem:

```java
String[] names = context.getBeanNamesForType(
        GreetingService.class);

assertThat(names).hasSize(1);
```

Nếu có hai bean, in tên và implementation class để xác định nguồn đăng ký. Đừng chỉ thêm `@Primary` rồi bỏ qua nguyên nhân default bean không back-off.

### 22.2. Kiểm tra condition report

Chạy với `--debug` và tìm auto-configuration tương ứng. Nếu condition `@ConditionalOnMissingBean` được báo không match, xem message chỉ ra bean nào đã tồn tại hoặc type nào được xét.

Nếu condition lại match trong khi user bean đáng lẽ đã có, có thể ordering hoặc type prediction không như mong muốn.

### 22.3. Test bằng context runner

Một test nhỏ với `withUserConfiguration` thường cho câu trả lời nhanh hơn việc debug toàn bộ application. Khi runner test đúng nhưng consumer app sai, nghi ngờ discovery, package scanning, classpath hoặc context hierarchy.

## 23. Kiểm thử các biến thể classpath và property

Một auto-configuration có thể chạy trong nhiều tổ hợp môi trường. Hãy test các trường hợp đại diện.

| Kịch bản | Classpath | Property | User bean | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Default | Greeting API có | Thiếu enabled | Không | Tạo default |
| Explicit enabled | Có | enabled=true | Không | Tạo default |
| Disabled | Có | enabled=false | Không | Không tạo service |
| User override | Có | enabled=true | Có | Chỉ dùng user bean |
| Optional library missing | Optional API vắng | Feature phụ thuộc API | Không | Không tạo integration |
| Multiple candidates | Collaborator có nhiều bean | Feature bật | Nhiều bean | Chỉ tạo nếu condition/candidate phù hợp |
| Resource missing | Resource không có | Feature phụ thuộc resource | Không | Không tạo cấu hình |
| Wrong property value | API có | enabled=invalid | Không | Condition không match theo semantics đã định |

### 23.1. Kiểm thử class không có

Spring Boot Test cung cấp `FilteredClassLoader` để mô phỏng classpath thiếu một type/package:

```java
contextRunner
    .withClassLoader(
            new FilteredClassLoader(
                    OptionalMetricsApi.class))
    .run(context -> {
        assertThat(context)
                .doesNotHaveBean(MetricsReporter.class);
    });
```

Ví dụ này giả định auto-configuration optional đã được thiết kế để không tham chiếu optional type bên ngoài nested guarded configuration. Nếu class vẫn bị resolve sớm từ outer configuration, test sẽ giúp phát hiện vấn đề.

### 23.2. Kiểm tra resource thiếu

Có thể dùng classloader/resource setup phù hợp hoặc tách logic resource condition thành configuration riêng. Điều quan trọng là test đúng condition, không tạo file giả trong test classpath khiến condition luôn match.

### 23.3. Kiểm thử property không hợp lệ

Nếu condition yêu cầu `havingValue="true"`, giá trị `yes` hoặc `invalid` không được mặc định coi là true. Test explicit để ghi nhận semantics mà starter cam kết.

## 24. Bài thực hành: tạo auto-configuration và chứng minh back-off

### Mục tiêu

Tạo thư viện `acme-greeting-spring-boot-autoconfigure` có default service, properties, điều kiện classpath/property và khả năng user override.

### Bước 1 — Tạo module

Tạo module Maven/Gradle có dependency Spring Boot Autoconfigure và module core. Thiết lập version qua Boot BOM/plugin tương thích.

### Bước 2 — Tạo API

Tạo `GreetingService` với method `greet(String name)`. Giữ interface thuần Java.

### Bước 3 — Tạo default implementation

Tạo `DefaultGreetingService` nhận prefix qua constructor. Không đánh dấu `@Component`.

### Bước 4 — Tạo properties

Tạo `GreetingProperties` với prefix `acme.greeting` và field `prefix` default `Hello`. Bổ sung description/metadata nếu cần.

### Bước 5 — Tạo auto-configuration

Dùng:

- `@AutoConfiguration`.
- `@ConditionalOnClass`.
- `@ConditionalOnProperty` với `matchIfMissing` có chủ đích.
- `@EnableConfigurationProperties`.
- `@Bean`.
- `@ConditionalOnMissingBean(GreetingService.class)`.

### Bước 6 — Đăng ký imports

Tạo `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và ghi FQCN của auto-configuration.

### Bước 7 — Test default

Dùng `ApplicationContextRunner` và `AutoConfigurations.of(...)`. Kiểm tra default bean được tạo và prefix được bind.

### Bước 8 — Test user override

Tạo test configuration khai báo custom `GreetingService`. Assert chỉ có một bean theo interface và behavior thuộc user implementation.

### Bước 9 — Test property disabled

Đặt `acme.greeting.enabled=false`. Assert default service không được tạo.

### Bước 10 — Test property missing

Không truyền enabled property. Assert kết quả đúng với `matchIfMissing` đã chọn.

### Bước 11 — Test optional dependency

Tạo integration phụ thuộc class optional, bảo vệ bằng nested configuration và `@ConditionalOnClass(name=...)`. Dùng `FilteredClassLoader` để xác nhận context vẫn khởi tạo khi optional class vắng mặt.

### Bước 12 — Test discovery qua consumer

Tạo demo application chỉ thêm starter dependency, không explicit import auto-configuration. Khởi động context và gọi service. Kiểm tra JAR có imports resource.

### Bước 13 — Thử nhiều implementation

Đăng ký hai `GreetingService` user beans. Xác nhận auto-config back-off nhưng injection trở nên ambiguous nếu không có primary/qualifier. Ghi nhận rằng back-off chỉ ngăn default bean, không tự giải quyết nhiều bean do user tạo.

### Bước 14 — Đọc condition report

Chạy demo với `--debug`. Tìm positive/negative match và giải thích từng condition.

### Bước 15 — Kiểm tra artifact

Build JAR và inspect:

```bash
jar tf target/acme-greeting-spring-boot-autoconfigure-1.0.0.jar
```

Xác nhận file `AutoConfiguration.imports` có trong archive và class name trỏ đúng auto-configuration.

### Câu hỏi tự kiểm tra

1. Auto-configuration khác component scanning như thế nào?
2. Vì sao starter nên cung cấp default bean có back-off?
3. `@ConditionalOnClass` kiểm tra classpath hay bean registry?
4. `@ConditionalOnBean` và `@ConditionalOnMissingBean` khác nhau thế nào?
5. Vì sao condition nên xét interface contract thay vì concrete default class?
6. `matchIfMissing=true` thay đổi hành vi property condition ra sao?
7. Condition class-level khác method-level thế nào?
8. Vì sao `@ConditionalOnMissingBean` nhạy với ordering?
9. `@AutoConfigureAfter` có điều khiển singleton initialization order không?
10. Vì sao optional class nên được cô lập trong nested configuration?
11. Auto-configuration được đăng ký trong Spring Boot 3 bằng resource nào?
12. Spring Boot 2 cũ thường dùng metadata nào cho auto-configuration?
13. Vì sao `@Primary` không thay thế back-off?
14. `ApplicationContextRunner` kiểm tra được những gì?
15. Vì sao context runner test chưa chứng minh imports file được đóng gói?
16. Làm thế nào mô phỏng optional class không có bằng `FilteredClassLoader`?
17. Vì sao return type của `@Bean` method nên thể hiện contract?
18. Một user bean ở parent context có nên làm auto-configuration back-off không?
19. Khi nào dùng `@ConditionalOnSingleCandidate`?
20. Làm sao debug một bean default xuất hiện trùng với user bean?

## 25. Bảng ghi nhớ nhanh

| Thành phần | Vai trò |
| --- | --- |
| `@AutoConfiguration` | Đánh dấu Boot auto-configuration class |
| `AutoConfiguration.imports` | Đăng ký auto-configuration để Boot phát hiện |
| `@ConditionalOnClass` | Chỉ áp dụng khi class có trên classpath |
| `@ConditionalOnMissingClass` | Chỉ áp dụng khi class không có |
| `@ConditionalOnProperty` | Bật/tắt theo Environment property |
| `@ConditionalOnBean` | Yêu cầu bean đã được đăng ký |
| `@ConditionalOnMissingBean` | Tạo default khi chưa có bean phù hợp |
| `@ConditionalOnSingleCandidate` | Yêu cầu một candidate có thể chọn rõ |
| `@ConditionalOnResource` | Yêu cầu resource tồn tại |
| `@ConditionalOnWebApplication` | Giới hạn cho web application |
| `@EnableConfigurationProperties` | Đăng ký properties bean |
| `@Bean` | Tạo bean từ configuration method |
| Back-off | Auto-config không tạo default khi user bean phù hợp đã tồn tại |
| Interface contract | Điểm override ổn định cho ứng dụng |
| `@AutoConfigureBefore/After` | Điều khiển thứ tự xử lý auto-configurations |
| `@AutoConfigureOrder` | Khai báo order của auto-configuration |
| Nested configuration | Cô lập optional class references |
| `ApplicationContextRunner` | Test điều kiện và bean registration nhanh |
| `FilteredClassLoader` | Mô phỏng classpath thiếu class |
| Condition Evaluation Report | Giải thích positive/negative condition matches |
| Starter module | Gom dependency để consumer thêm thuận tiện |
| Auto-configure module | Chứa logic Spring Boot configuration |
| Core module | Chứa API/logic có thể độc lập Spring |

**Điểm cốt lõi:** Auto-configuration nên cung cấp **mặc định hữu ích, chỉ hoạt động khi điều kiện phù hợp và tôn trọng bean do ứng dụng khai báo**. Hãy đăng ký cấu hình qua `AutoConfiguration.imports`, dùng condition theo classpath/property/bean phù hợp, đặt `@ConditionalOnMissingBean` trên contract mà người dùng cần thay thế và kiểm chứng cả default path lẫn override path bằng `ApplicationContextRunner`. Khi thiết kế như vậy, starter có thể tự tích hợp với Spring Boot mà vẫn để ứng dụng kiểm soát behavior của chính nó.
