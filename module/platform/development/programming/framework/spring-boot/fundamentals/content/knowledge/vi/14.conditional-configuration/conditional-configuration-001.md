# @Conditional và thời điểm quyết định một cấu hình có được đăng ký

Spring Boot thường có nhiều cấu hình chỉ nên được áp dụng khi một điều kiện nhất định được thỏa mãn. Ví dụ: chỉ tạo bean gửi email khi thư viện email có trên classpath; chỉ cấu hình database khi driver phù hợp có mặt; hoặc chỉ tạo bean mặc định khi ứng dụng chưa tự cung cấp bean thay thế.

Spring thực hiện việc này bằng **conditional configuration**. Annotation nền tảng là `@Conditional` của Spring Framework. Spring Boot xây dựng nhiều annotation chuyên biệt trên cơ chế đó, chẳng hạn `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và `@ConditionalOnWebApplication`.

Điểm quan trọng không chỉ là biết viết annotation điều kiện, mà còn hiểu **khi nào Spring đánh giá điều kiện**. Condition được kiểm tra trong quá trình phân tích cấu hình hoặc đăng ký bean definition, trước khi bean instance tương ứng được tạo. Nó không phải biểu thức chạy lại mỗi lần có request và cũng không tự thay đổi sau khi ứng dụng đã khởi động.

Bài học thuộc chương **Cấu hình theo điều kiện** của **Spring Boot Fundamentals**. Chúng ta sẽ tìm hiểu cơ chế `@Conditional`, các giai đoạn xử lý cấu hình, cách Spring Boot dùng điều kiện trong auto-configuration, cách tự viết condition và cách chẩn đoán vì sao một bean được hoặc không được đăng ký.

## 1. Vì sao cần cấu hình theo điều kiện?

Giả sử ứng dụng có interface gửi thông báo:

```java
package com.example.demo.notification;

public interface NotificationSender {
    void send(String message);
}
```

Có thể có nhiều cách gửi:

```java
package com.example.demo.notification;

public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

```java
package com.example.demo.notification;

public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        System.out.println("Console: " + message);
    }
}
```

Trong môi trường phát triển, ta có thể muốn dùng console sender. Trong production, ta có thể muốn dùng email sender nếu thư viện email đã được cấu hình. Nếu luôn đăng ký cả hai bean, service inject một `NotificationSender` duy nhất có thể gặp nhập nhằng.

Một giải pháp là chỉ đăng ký bean phù hợp với điều kiện của môi trường:

```text
                    Đọc cấu hình ứng dụng
                             │
                             ▼
                Điều kiện "notification.mode"
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
             mode=console             mode=email
                 │                       │
                 ▼                       ▼
       Đăng ký ConsoleSender    Đăng ký EmailSender
                 │                       │
                 └───────────┬───────────┘
                             ▼
                   ApplicationContext
```

Conditional configuration hữu ích khi feature là tùy chọn, ứng dụng chạy trên nhiều môi trường, thư viện tích hợp chỉ có mặt trong một số bản build, người dùng có thể thay bean mặc định, hoặc cấu hình chỉ nên hoạt động khi một property hay bean khác tồn tại.

## 2. `@Conditional` của Spring Framework

Annotation nền tảng nằm trong package:

```java
import org.springframework.context.annotation.Conditional;
```

`@Conditional` nhận một hoặc nhiều class triển khai interface `Condition`:

```java
@FunctionalInterface
public interface Condition {

    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    );
}
```

Một condition trả về `true` khi điều kiện khớp; trả về `false` khi thành phần đang xét cần bị loại khỏi quá trình đăng ký tương ứng.

`ConditionContext` cung cấp thông tin về môi trường xử lý, chẳng hạn registry, bean factory, environment, resource loader và class loader. `AnnotatedTypeMetadata` cho phép đọc annotation metadata của class hoặc method đang được kiểm tra.

### 2.1. Ví dụ condition tự viết

Giả sử chỉ muốn đăng ký cấu hình khi property `feature.audit-enabled` có giá trị `true`.

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AuditEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        String value = context.getEnvironment()
                .getProperty("feature.audit-enabled");

        return Boolean.parseBoolean(value);
    }
}
```

Dùng condition:

```java
package com.example.demo.audit;

import com.example.demo.condition.AuditEnabledCondition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Conditional;

@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Cấu hình:

```yaml
feature:
  audit-enabled: true
```

Khi property có giá trị `true`, condition trả về `true` và `AuditConfiguration` được chấp nhận để xử lý. Khi property không tồn tại hoặc có giá trị không được `Boolean.parseBoolean` xem là true, condition trả về `false`.

Condition ở đây gắn trên **lớp configuration**. Nếu không khớp, Spring bỏ qua cấu hình đó và các bean definitions được khai báo bên trong lớp.

### 2.2. Condition không phải bean nghiệp vụ thông thường

Class triển khai `Condition` được framework khởi tạo để đánh giá điều kiện. Không nên xem condition như một service nghiệp vụ được inject tùy ý vào application context.

Condition nên có logic nhỏ, xác định và dễ kiểm tra; dựa trên dữ liệu có sẵn ở giai đoạn đánh giá; không có side effect; không tạo kết nối mạng hoặc thực hiện thao tác nghiệp vụ; và không phụ thuộc vào bean instance của ứng dụng chưa được tạo.

Đặc biệt, không nên inject một service thông thường vào condition rồi gọi nó để quyết định có đăng ký service đó hay không. Condition có thể được đánh giá trước khi những bean như vậy tồn tại.

## 3. Hai vị trí phổ biến để đặt `@Conditional`

Spring cho phép điều kiện áp dụng lên một lớp configuration hoặc một phương thức `@Bean`.

### 3.1. Điều kiện trên class configuration

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }

    @Bean
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
```

Nếu condition không khớp, toàn bộ configuration class bị bỏ qua. Cả hai bean definition bên trong đều không được đăng ký từ cấu hình này.

Cách này phù hợp khi nhiều bean tạo thành một nhóm cấu hình và cùng phụ thuộc vào một điều kiện.

### 3.2. Điều kiện trên một phương thức `@Bean`

Nếu chỉ một bean phụ thuộc điều kiện, đặt annotation ngay trên factory method:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Conditional(AuditEnabledCondition.class)
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }

    @Bean
    public NotificationService notificationService() {
        return new NotificationService();
    }
}
```

Condition chỉ áp dụng cho bean definition từ `auditPublisher()`. `notificationService` vẫn có thể được đăng ký.

Tuy nhiên, nếu `NotificationService` yêu cầu `AuditPublisher` qua constructor mà bean publisher không được đăng ký, service đó có thể khiến context khởi động thất bại. Conditional configuration phải được thiết kế cùng dependency graph, không chỉ nhìn riêng annotation trên một method.

### 3.3. So sánh phạm vi

| Vị trí annotation | Phạm vi bị ảnh hưởng khi condition không khớp |
|---|---|
| Trên `@Configuration` class | Cấu hình class và các bean definitions được khai báo trong đó |
| Trên method `@Bean` | Bean definition do method đó cung cấp |
| Trên component class | Component đó không được đăng ký qua component scanning nếu condition không khớp |
| Trên cấu hình được import | Nhánh cấu hình được import có thể bị loại theo cơ chế tương ứng |

Một condition class-level không tự động loại bỏ các component độc lập khác ở package lân cận. Nó chỉ tác động đến cấu hình/component mà annotation được gắn vào và các thành phần nằm trong phạm vi xử lý của nó.

## 4. Thời điểm đánh giá condition: parse và register

Đây là phần cốt lõi của bài học.

Spring không đợi đến khi một bean được gọi lần đầu mới quyết định có đăng ký bean hay không. Condition được đánh giá trong quá trình xử lý cấu hình và bean definitions.

Spring Framework có interface `ConfigurationCondition` mở rộng `Condition` để condition chỉ rõ giai đoạn cần được đánh giá:

```java
public interface ConfigurationCondition extends Condition {

    ConfigurationPhase getConfigurationPhase();

    enum ConfigurationPhase {
        PARSE_CONFIGURATION,
        REGISTER_BEAN
    }
}
```

Hai phase có ý nghĩa:

- `PARSE_CONFIGURATION`: điều kiện được xét trong lúc Spring phân tích configuration classes. Nếu không khớp, class configuration không được xử lý tiếp như một nguồn cấu hình.
- `REGISTER_BEAN`: điều kiện được xét ở giai đoạn đăng ký bean definitions. Giai đoạn này phù hợp với condition cần quan sát registry hoặc những bean definitions đã được đăng ký trước đó.

Với condition chỉ implement `Condition` mà không chỉ định phase qua `ConfigurationCondition`, Spring xử lý theo quy tắc mặc định của quá trình đánh giá condition, thường ở phase đăng ký bean. Các condition chuyên biệt có thể chọn phase khác.

### 4.1. Sơ đồ thời gian đơn giản

```text
Khởi động Spring / refresh ApplicationContext
                   │
                   ▼
       Đọc và xử lý nguồn configuration
                   │
                   ▼
       PARSE_CONFIGURATION phase
       - Xét điều kiện class-level cần parse
       - Xử lý @Import và cấu hình liên quan
                   │
                   ▼
       REGISTER_BEAN phase
       - Đăng ký các bean definitions
       - Xét điều kiện bean/method tương ứng
       - Quan sát registry theo thời điểm xử lý
                   │
                   ▼
       Hoàn tất đăng ký cấu hình
                   │
                   ▼
       Tạo singleton eager và inject dependency
                   │
                   ▼
       Initialization callbacks
                   │
                   ▼
       ApplicationContext sẵn sàng
```

Sơ đồ mô tả các giai đoạn chính, không phải toàn bộ thứ tự nội bộ của mọi post-processor. Spring có nhiều bước xử lý metadata, import selector, registrar và bean factory post-processor.

Điểm cần nhớ: **condition quyết định việc đăng ký cấu hình/bean definition trước khi bean instance tương ứng được tạo**.

### 4.2. Condition trên configuration class được xét sớm

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditEnabledCondition.class)
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Spring cần biết `AuditConfiguration` có được chấp nhận hay không trước khi phân tích các khai báo cấu hình bên trong. Nếu condition không khớp ở phase parse, configuration class bị bỏ qua.

Điều này quan trọng nếu class có `@Import`, `@ComponentScan` hoặc nhiều khai báo `@Bean`: bỏ qua class có thể loại bỏ toàn bộ nhánh cấu hình do class đó cung cấp.

### 4.3. Condition trên `@Bean` method được xét khi đăng ký bean definition

```java
@Configuration(proxyBeanMethods = false)
public class OptionalFeatureConfiguration {

    @Bean
    @Conditional(AuditEnabledCondition.class)
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Spring phân tích configuration class, sau đó khi đăng ký bean definition từ `auditService()` mới xét điều kiện tương ứng. Nếu không khớp, bean definition đó không được đăng ký.

Không nên diễn giải rằng Spring đã tạo `AuditService` rồi mới kiểm tra condition. Điều kiện được dùng để quyết định **có đăng ký định nghĩa tạo bean hay không**.

## 5. Viết condition cần dữ liệu gì ở mỗi phase?

`ConditionContext` cho phép truy cập một số thông tin khác nhau tùy thời điểm:

| API | Dữ liệu có thể dùng |
|---|---|
| `getEnvironment()` | Properties, profiles và PropertySources đã được nạp |
| `getRegistry()` | Registry chứa bean definitions đã đăng ký tới thời điểm hiện tại |
| `getBeanFactory()` | BeanFactory nếu đã sẵn sàng trong giai đoạn tương ứng |
| `getResourceLoader()` | Cơ chế tải resource |
| `getClassLoader()` | Class loader để kiểm tra class/resource |

Không phải mọi API đều có thể được sử dụng với cùng mức độ an toàn ở mọi phase. Đặc biệt, khi condition chạy sớm, không nên giả định toàn bộ bean definitions hoặc bean instances của ứng dụng đã tồn tại.

### 5.1. Vì sao không gọi `getBean()` để quyết định condition?

Một condition như sau là thiết kế không phù hợp:

```java
@Override
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
) {
    SomeService service =
            context.getBeanFactory().getBean(SomeService.class);

    return service.isEnabled();
}
```

Lý do:

- Condition có thể chạy trước khi `SomeService` được tạo.
- `SomeService` có thể phụ thuộc vào cấu hình mà condition đang quyết định.
- Việc tạo bean sớm trong lúc đăng ký cấu hình có thể làm lifecycle bị đảo lộn.
- Condition trở nên phụ thuộc vào side effect và trạng thái runtime không ổn định.

Hãy dùng properties, classpath, bean definitions hoặc metadata phù hợp với phase thay vì gọi business bean.

### 5.2. Bean definition khác bean instance

Condition dựa trên registry thường kiểm tra **định nghĩa bean đã được đăng ký**, không nhất thiết là instance đã được tạo.

Ví dụ, một condition có thể thấy bean definition của `Clock` dù singleton `Clock` chưa được instantiate. Đây là điểm quan trọng khi dùng điều kiện theo sự tồn tại của bean.

Không nên nói `@ConditionalOnBean` luôn kiểm tra “object đã chạy” hoặc “bean đã được khởi tạo”. Cơ chế chủ yếu làm việc với thông tin container có thể xác định ở thời điểm đăng ký.

## 6. `ConfigurationCondition`: chọn phase tường minh

Nếu custom condition phụ thuộc vào thời điểm xử lý configuration, có thể implement `ConfigurationCondition`.

Ví dụ condition cần xem registry trong giai đoạn đăng ký bean:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AuditRegistryCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        return context.getRegistry()
                .containsBeanDefinition("auditInfrastructure");
    }
}
```

Dùng:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AuditRegistryCondition.class)
public class AuditExtensionConfiguration {

    @Bean
    public AuditExtension auditExtension() {
        return new AuditExtension();
    }
}
```

Trong ví dụ, condition chỉ khớp khi registry đã có bean definition tên `auditInfrastructure` ở thời điểm condition được đánh giá.

Cần lưu ý: việc một definition có mặt **trước** hay **sau** còn phụ thuộc thứ tự đăng ký cấu hình. Nếu configuration chứa `auditInfrastructure` chưa được xử lý tại thời điểm condition chạy, condition có thể trả về false dù definition đó sẽ được đăng ký về sau.

### 6.1. Khi nào chọn PARSE_CONFIGURATION?

Dùng phase parse khi quyết định có nên xử lý cả configuration class hay không và condition không cần dựa vào các bean definitions được đăng ký ở giai đoạn sau.

Ví dụ một cấu hình chỉ phù hợp với classpath hoặc môi trường cụ thể. Các condition class-level có thể được đánh giá sớm để bỏ qua một nhánh cấu hình không cần thiết.

### 6.2. Khi nào chọn REGISTER_BEAN?

Dùng phase register khi điều kiện phụ thuộc vào registry hoặc trạng thái bean definitions đã được đăng ký trước đó.

Ví dụ:

- Một bean mặc định chỉ nên đăng ký nếu chưa có bean khác.
- Một cấu hình bổ sung chỉ áp dụng khi hạ tầng cần thiết đã có definition.
- Một condition cần phân tích thông tin bean factory ở giai đoạn đăng ký.

Không dùng phase register để bảo đảm mọi bean của ứng dụng đã tồn tại; nó chỉ cho phép condition quan sát trạng thái registry tại thời điểm thực thi.

## 7. Spring Boot cung cấp các condition chuyên biệt

Spring Boot xây dựng nhiều annotation dựa trên `@Conditional` để xử lý những tình huống thường gặp. Chúng giúp configuration dễ đọc hơn và giảm nhu cầu tự viết condition cho từng feature.

| Annotation | Điều kiện chính |
|---|---|
| `@ConditionalOnClass` | Class được chỉ định có trên classpath |
| `@ConditionalOnMissingClass` | Class được chỉ định không có trên classpath |
| `@ConditionalOnBean` | Có bean phù hợp đã được đăng ký |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp đã được đăng ký |
| `@ConditionalOnSingleCandidate` | Có một ứng viên phù hợp duy nhất hoặc một ứng viên ưu tiên rõ ràng |
| `@ConditionalOnProperty` | Property có giá trị thỏa điều kiện |
| `@ConditionalOnResource` | Resource được chỉ định tồn tại |
| `@ConditionalOnWebApplication` | Ứng dụng được nhận diện là web application theo loại chỉ định |
| `@ConditionalOnNotWebApplication` | Ứng dụng không phải web application |
| `@ConditionalOnExpression` | SpEL expression trả về điều kiện phù hợp |
| `@ConditionalOnJava` | Phiên bản Java thỏa range |
| `@Profile` | Profile được kích hoạt |

Các annotation này thường được đặt trên configuration class hoặc bean method. Chúng là cách khai báo điều kiện cho dễ đọc; nền tảng vẫn là quá trình đánh giá condition của Spring.

## 8. `@ConditionalOnClass` và `@ConditionalOnMissingClass`

### 8.1. Chỉ cấu hình khi thư viện có trên classpath

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.mail.MailClient")
public class MailClientConfiguration {

    @Bean
    public MailNotificationSender mailNotificationSender() {
        return new MailNotificationSender();
    }
}
```

Nếu class `com.example.mail.MailClient` có thể được tìm thấy trên classpath, condition khớp và cấu hình được chấp nhận.

Nếu thư viện mail không được thêm vào dependency, cấu hình bị bỏ qua thay vì cố tạo bean phụ thuộc vào một class không tồn tại.

Có thể sử dụng class literal:

```java
@ConditionalOnClass(MailClient.class)
```

hoặc tên class dạng chuỗi:

```java
@ConditionalOnClass(name = "com.example.mail.MailClient")
```

Tên class dạng chuỗi hữu ích khi muốn tránh việc JVM phải resolve kiểu optional ngay lúc nạp lớp cấu hình. Đặc biệt trong thư viện auto-configuration, nên cân nhắc cách tổ chức class để class có tham chiếu tới optional type không bị load khi dependency vắng mặt.

### 8.2. Chỉ cấu hình khi class không tồn tại

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.example.legacy.LegacyClient")
public class DefaultClientConfiguration {

    @Bean
    public Client defaultClient() {
        return new DefaultClient();
    }
}
```

Cấu hình chỉ được xử lý khi class được chỉ định không có trên classpath.

Điều này hữu ích khi thư viện có nhiều integration và muốn chọn implementation theo những dependency hiện diện trong bản build.

### 8.3. Có dependency không đồng nghĩa đã có bean

`@ConditionalOnClass` chỉ kiểm tra classpath. Nó không khẳng định thư viện đã được cấu hình đúng, một bean của thư viện đã được tạo, kết nối tới dịch vụ bên ngoài thành công hoặc tính năng nghiệp vụ có thể sử dụng được.

Nếu cần kiểm tra một bean đã được đăng ký, hãy xem `@ConditionalOnBean` hoặc điều kiện phù hợp. Nếu cần kiểm tra trạng thái kết nối, đó là bài toán health/readiness hoặc startup validation, không nên nhét vào classpath condition.

## 9. `@ConditionalOnProperty`: điều kiện theo cấu hình

Đây là một trong những condition thường gặp nhất trong Spring Boot.

Ví dụ:

```yaml
app:
  notification:
    enabled: true
    mode: email
```

Configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true"
)
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new EmailNotificationSender();
    }
}
```

Khi `app.notification.enabled=true`, bean được đăng ký. Khi property có giá trị khác, điều kiện không khớp.

### 9.1. Ý nghĩa của các thuộc tính

| Thuộc tính | Ý nghĩa |
|---|---|
| `prefix` | Tiền tố chung của property |
| `name` | Tên property cần kiểm tra |
| `havingValue` | Giá trị cụ thể cần khớp |
| `matchIfMissing` | Có khớp nếu property không tồn tại hay không |

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "enabled",
        matchIfMissing = false
)
```

Condition chỉ khớp khi property có giá trị `enabled`; nếu không có property, condition không khớp.

Nếu không chỉ định `havingValue`, quy tắc mặc định của `@ConditionalOnProperty` là property phải tồn tại và giá trị của nó không phải chuỗi `false` (không phân biệt chữ hoa/thường theo quy tắc so sánh). Vì vậy, nếu property có giá trị `anything`, condition mặc định vẫn có thể khớp. Khi muốn boolean rõ ràng, hãy đặt `havingValue = "true"`.

### 9.2. Ví dụ bật/tắt feature

```yaml
app:
  feature:
    audit: true
```

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.feature",
            name = "audit",
            havingValue = "true"
    )
    public AuditService auditService() {
        return new AuditService();
    }
}
```

Có thể bật/tắt bằng command line:

```bash
java -jar demo.jar --app.feature.audit=true
```

Hoặc qua biến môi trường trên Linux/macOS:

```bash
APP_FEATURE_AUDIT=true java -jar demo.jar
```

### 9.3. Lưu ý với property dạng collection

`@ConditionalOnProperty` không phù hợp để kiểm tra sự tồn tại của một property dạng indexed collection, ví dụ `app.servers[0]`. Trong những tình huống đó, property có thể được bind nhưng condition không phát hiện theo cách người viết mong đợi. Nếu cần kiểm tra collection phức tạp, hãy dùng custom condition hoặc một cơ chế binding/validation phù hợp.

## 10. `@ConditionalOnBean`, `@ConditionalOnMissingBean` và `@ConditionalOnSingleCandidate`

Nhóm condition này đặc biệt quan trọng trong auto-configuration.

### 10.1. Chỉ đăng ký khi đã có bean phù hợp

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(DataSource.class)
public class JdbcFeatureConfiguration {

    @Bean
    public JdbcReportRepository jdbcReportRepository(DataSource dataSource) {
        return new JdbcReportRepository(dataSource);
    }
}
```

Cấu hình chỉ khớp nếu container có bean phù hợp với `DataSource` ở thời điểm điều kiện được đánh giá.

Điều kiện này xét thông tin bean definitions có thể quan sát tại thời điểm xử lý, không có nghĩa Spring phải khởi tạo và kết nối database thành công trước khi condition khớp.

### 10.2. Chỉ đăng ký bean mặc định nếu chưa có bean của người dùng

```java
@Configuration(proxyBeanMethods = false)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

Nếu ứng dụng đã đăng ký một bean phù hợp type `Clock` trước khi condition được đánh giá, bean mặc định không được đăng ký. Nếu chưa có bean phù hợp, Spring có thể đăng ký `systemClock`.

Đây là mẫu phổ biến của Spring Boot auto-configuration: **cung cấp mặc định nhưng cho phép ứng dụng thay thế bằng bean riêng**.

### 10.3. Điều kiện single candidate

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnSingleCandidate(DataSource.class)
public class SingleDataSourceConfiguration {

    @Bean
    public DatabaseInspector databaseInspector(DataSource dataSource) {
        return new DatabaseInspector(dataSource);
    }
}
```

Điều kiện này khớp khi có một candidate phù hợp duy nhất, hoặc có một ứng viên được ưu tiên theo quy tắc tương ứng (chẳng hạn primary) để lựa chọn không mơ hồ.

Nó hữu ích khi một cấu hình cần một dependency đơn lẻ và muốn chỉ hoạt động khi có thể xác định ứng viên thích hợp.

### 10.4. Thời điểm và thứ tự đăng ký rất quan trọng

Giả sử hai configuration:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class CustomClockConfiguration {

    @Bean
    public Clock customClock() {
        return Clock.systemDefaultZone();
    }
}
```

Nếu condition của default configuration được đánh giá **trước khi** custom bean definition được đăng ký, nó có thể thấy chưa có `Clock` và đăng ký bean mặc định. Khi custom definition xuất hiện sau đó, ứng dụng có thể có hai bean cùng type và injection đơn lẻ trở nên nhập nhằng.

Đây là lý do auto-configuration của Spring Boot có quy tắc sắp xếp và các điều kiện cần được dùng đúng ngữ cảnh. `@ConditionalOnMissingBean` được thiết kế chủ yếu cho auto-configuration, nơi user configuration được xử lý trước auto-configuration theo cơ chế bootstrap thông thường.

Không nên đặt điều kiện theo bean một cách tùy tiện trong các configuration độc lập rồi giả định mọi bean của toàn ứng dụng đã được đăng ký.

## 11. `@Profile` cũng là một conditional

`@Profile` cho phép giới hạn bean/configuration theo profile đang active.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DevelopmentConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new EmailNotificationSender();
    }
}
```

Khi profile `dev` active, cấu hình phát triển được đăng ký. Khi profile `prod` active, cấu hình production được đăng ký.

Kích hoạt profile:

```bash
java -jar demo.jar --spring.profiles.active=dev
```

Hoặc qua biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
```

Một ứng dụng có thể có nhiều profile cùng active. Nếu `dev` và `prod` cùng active, cả hai configuration có thể cùng được xử lý; nếu chúng đăng ký cùng bean name, có thể phát sinh đụng tên. Profile không mặc định bảo đảm chỉ có đúng một profile hoạt động.

`@Profile` được triển khai dựa trên cơ chế `@Conditional`. Nó là cách khai báo điều kiện theo profile, không phải lifecycle callback.

## 12. `@ConditionalOnWebApplication` và điều kiện môi trường

Spring Boot có thể phân biệt ứng dụng web với ứng dụng không phải web.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication
public class WebFeatureConfiguration {

    @Bean
    public RequestAuditFilter requestAuditFilter() {
        return new RequestAuditFilter();
    }
}
```

Cấu hình chỉ được áp dụng khi Spring Boot nhận diện môi trường là web application phù hợp.

Nếu muốn chỉ áp dụng trong ứng dụng không phải web:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class ConsoleFeatureConfiguration {

    @Bean
    public ConsoleReporter consoleReporter() {
        return new ConsoleReporter();
    }
}
```

Một số annotation liên quan:

- `@ConditionalOnWebApplication(type = ...)`: phân biệt các loại môi trường web được hỗ trợ.
- `@ConditionalOnNotWebApplication`: không phải web application.
- `@ConditionalOnJava`: giới hạn theo Java version.
- `@ConditionalOnResource`: kiểm tra resource.
- `@ConditionalOnExpression`: dùng SpEL expression.
- `@ConditionalOnCloudPlatform`: điều kiện theo nền tảng cloud được nhận diện.

Điều kiện môi trường dựa trên thông tin có sẵn trong quá trình bootstrap. Nó không thay thế việc kiểm tra readiness của server hoặc health của một dịch vụ bên ngoài sau khi ứng dụng đã chạy.

## 13. `@ConditionalOnExpression` và khi nào nên tránh

Có thể dùng SpEL:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
public class ExpressionAuditConfiguration {
    // ...
}
```

Annotation này hữu ích khi biểu thức cần kết hợp một số giá trị cấu hình hoặc biểu thức đơn giản.

Tuy nhiên, đừng dùng SpEL cho mọi condition. Nếu chỉ kiểm tra một property boolean, `@ConditionalOnProperty` dễ đọc và dễ chẩn đoán hơn.

SpEL expression có thể được đánh giá trong giai đoạn cấu hình khi nhiều bean chưa được tạo. Không nên viết expression giả định business bean đã sẵn sàng hoặc gây side effect.

## 14. Auto-configuration của Spring Boot dùng condition như thế nào?

Spring Boot auto-configuration là tập hợp cấu hình có điều kiện nhằm giảm lượng cấu hình thủ công.

Ví dụ, khi dependency web phù hợp có trên classpath và ứng dụng là web application, Boot có thể tự động đăng ký các bean nền tảng cần thiết cho web stack. Khi người dùng đã tự khai báo một bean thay thế, auto-configuration tương ứng có thể lùi lại.

Một configuration minh họa:

```java
@AutoConfiguration
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(properties.host(), properties.port());
    }
}
```

Ví dụ mô tả một auto-configuration tự viết. Để dùng được, project cần có class `MailClient` và cơ chế đăng ký auto-configuration phù hợp với phiên bản Spring Boot. Trong một thư viện Boot 3, lớp auto-configuration thường được liệt kê trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File đó chứa tên fully qualified của các auto-configuration class, mỗi dòng một class:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Spring Boot sử dụng import selector để phát hiện các auto-configuration được khai báo, rồi xử lý các condition tương ứng.

### 14.1. Ba loại điều kiện thường kết hợp

Một auto-configuration có thể kết hợp:

```java
@AutoConfiguration
@ConditionalOnClass(MailClient.class)
@ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailClient.class)
    public MailClient mailClient() {
        return new MailClient();
    }
}
```

Ý nghĩa:

1. Chỉ xét cấu hình khi class thư viện mail có trên classpath.
2. Chỉ bật feature nếu property cho phép; trong ví dụ, property không có vẫn khớp do `matchIfMissing = true`.
3. Chỉ tạo bean mặc định khi chưa có bean `MailClient` phù hợp.

Các condition trên class và method có phạm vi khác nhau. Nếu condition trên class không khớp, toàn bộ auto-configuration bị bỏ qua. Nếu class condition khớp nhưng method condition không khớp, chỉ bean method tương ứng không được đăng ký.

### 14.2. Vì sao auto-configuration phải có điều kiện?

Nếu Boot luôn đăng ký mọi bean mặc định bất kể ứng dụng đã có gì, người dùng sẽ khó thay thế các thành phần framework. Conditional auto-configuration tạo một hợp đồng:

- Framework cung cấp cấu hình mặc định.
- Ứng dụng có thể tùy chỉnh hoặc thay thế.
- Dependency optional không bắt buộc phải có trong mọi bản build.
- Cấu hình chỉ xuất hiện khi classpath, property và bean registry phù hợp.

Đây là nền tảng giúp Spring Boot hoạt động theo kiểu convention-over-configuration mà vẫn cho phép mở rộng.

## 15. Thứ tự auto-configuration và điều kiện theo bean

Điều kiện theo classpath hoặc property thường ít phụ thuộc vào thứ tự đăng ký bean. Nhưng điều kiện theo bean registry có thể phụ thuộc rõ rệt vào thứ tự.

Spring Boot cung cấp các annotation để sắp xếp auto-configuration:

- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`

Ví dụ:

```java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class JdbcAuditAutoConfiguration {
    // ...
}
```

Annotation này yêu cầu auto-configuration được sắp xếp sau configuration được chỉ định theo cơ chế ordering của Boot.

### 15.1. Ordering không giống thứ tự khởi tạo bean

| Khái niệm | Điều khiển điều gì? |
|---|---|
| Auto-configuration ordering | Thứ tự xử lý các auto-configuration classes |
| Bean definition registration | Thời điểm definition được thêm vào registry |
| Dependency graph | Bean nào cần được tạo trước bean nào |
| `@Order` trên bean | Thứ tự trong các tình huống collection/order-aware tương ứng |
| Singleton initialization | Quá trình tạo instance khi context refresh |

`@AutoConfigureAfter` không có nghĩa mọi bean của configuration kia chắc chắn đã được instantiate. Nó sắp xếp xử lý configuration, hỗ trợ các điều kiện theo bean quan sát được definitions phù hợp.

### 15.2. Vì sao `@ConditionalOnMissingBean` cần được dùng cẩn thận?

Giả sử custom auto-configuration muốn cung cấp bean mặc định nếu người dùng chưa có bean:

```java
@Bean
@ConditionalOnMissingBean(Clock.class)
Clock applicationClock() {
    return Clock.systemUTC();
}
```

Đây là pattern hợp lý trong auto-configuration. Nhưng nếu nhiều configuration tùy chỉnh độc lập đều dùng điều kiện này, kết quả có thể phụ thuộc thứ tự đăng ký và những definition đã có tại thời điểm kiểm tra.

Hãy ưu tiên thiết kế auto-configuration theo convention của Boot và kiểm tra ordering khi condition phụ thuộc vào bean.

## 16. Condition không phải cơ chế bật/tắt bean liên tục

Một nhầm lẫn phổ biến là nghĩ rằng `@ConditionalOnProperty` sẽ tự động tạo hoặc hủy bean mỗi khi property đổi.

Ví dụ:

```yaml
app:
  feature:
    audit: false
```

Nếu condition không khớp khi application context được refresh, bean `AuditService` không được đăng ký từ configuration đó.

Sau đó, nếu một thành phần nào đó thay đổi property thành `true` trong lúc ứng dụng đang chạy, Spring **không tự động đánh giá lại condition để đăng ký bean mới**.

Condition là một quyết định trong quá trình cấu hình/đăng ký, không phải feature flag runtime tự động.

Nếu cần bật/tắt hành vi theo request hoặc theo trạng thái runtime, hãy dùng một cơ chế runtime phù hợp:

- Đọc property có thể thay đổi qua service quản lý cấu hình.
- Dùng feature flag client.
- Dùng strategy/service có sẵn và quyết định tại thời điểm xử lý.
- Dùng event hoặc cơ chế refresh chuyên biệt nếu kiến trúc có hỗ trợ và đã thiết kế vòng đời bean tương ứng.

Không dùng `@Conditional` để thay thế feature flag cần thay đổi liên tục sau startup.

## 17. Ví dụ hoàn chỉnh: bật feature theo property và cho phép thay bean mặc định

Ta tạo feature audit có thể bật/tắt bằng property, đồng thời cho phép ứng dụng tự cung cấp implementation.

### 17.1. Interface

```java
package com.example.demo.audit;

public interface AuditService {
    void record(String action);
}
```

### 17.2. Implementation mặc định

```java
package com.example.demo.audit;

public class ConsoleAuditService implements AuditService {

    @Override
    public void record(String action) {
        System.out.println("[AUDIT] " + action);
    }
}
```

### 17.3. Auto-configuration

```java
package com.example.demo.audit.autoconfigure;

import com.example.demo.audit.AuditService;
import com.example.demo.audit.ConsoleAuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new ConsoleAuditService();
    }
}
```

### 17.4. Đăng ký auto-configuration

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.example.demo.audit.autoconfigure.AuditAutoConfiguration
```

Đây là cách đăng ký auto-configuration trong hệ sinh thái Spring Boot 3. Nếu chỉ viết class `@AutoConfiguration` nhưng không đưa nó vào cơ chế import phù hợp, Boot sẽ không tự biết phải nạp class đó.

### 17.5. Bật feature

```yaml
app:
  audit:
    enabled: true
```

Khi điều kiện property khớp và ứng dụng chưa có bean `AuditService`, Boot đăng ký `ConsoleAuditService` dưới dạng bean `AuditService`.

### 17.6. Ứng dụng thay implementation mặc định

Ứng dụng có thể tự cung cấp:

```java
package com.example.demo.config;

import com.example.demo.audit.AuditService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomAuditConfiguration {

    @Bean
    public AuditService auditService() {
        return action -> System.out.println("CUSTOM AUDIT: " + action);
    }
}
```

Vì custom bean được đăng ký từ user configuration theo quy trình thông thường trước auto-configuration, `@ConditionalOnMissingBean(AuditService.class)` trong auto-configuration sẽ thấy bean phù hợp và bỏ qua bean mặc định.

Custom bean có thể dùng tên khác với tên method mặc định, vì condition đang xét theo **type `AuditService`**, không chỉ theo tên.

## 18. Custom condition: đọc property và metadata annotation

Khi các annotation có sẵn không đáp ứng yêu cầu, bạn có thể viết condition tùy chỉnh.

Ví dụ condition kiểm tra một property và một class:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AdvancedFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        boolean enabled = context.getEnvironment()
                .getProperty("app.advanced.enabled", Boolean.class, false);

        if (!enabled) {
            return false;
        }

        try {
            context.getClassLoader()
                    .loadClass("com.example.advanced.AdvancedClient");
            return true;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
```

Dùng:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(AdvancedFeatureCondition.class)
public class AdvancedFeatureConfiguration {
    // ...
}
```

Trong ứng dụng thực tế, nếu chỉ cần kiểm tra property và classpath, hãy dùng `@ConditionalOnProperty` và `@ConditionalOnClass` thay vì viết lại logic. Custom condition phù hợp khi cần kết hợp nhiều tiêu chí hoặc kiểm tra metadata đặc thù.

### 18.1. Đọc annotation attributes

`AnnotatedTypeMetadata` cho phép đọc metadata annotation của class hoặc method đang được kiểm tra.

Ví dụ condition có thể kiểm tra một custom annotation attribute:

```java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(FeatureFlag.class.getName());

if (attributes == null) {
    return false;
}

String featureName = (String) attributes.get("value");
```

Sau đó dùng `featureName` để tra property tương ứng. Cách này giúp một condition tái sử dụng cho nhiều configuration class, thay vì hard-code tên feature trong từng condition.

Khi viết custom annotation, cần bảo đảm metadata được đặt đúng target và retention phù hợp để Spring đọc được lúc runtime.

## 19. Condition evaluation report: vì sao cấu hình được bật hoặc bị bỏ qua?

Khi một auto-configuration không tạo bean như mong đợi, chỉ nhìn vào `application.yml` thường chưa đủ. Spring Boot có thể cung cấp **Condition Evaluation Report** để cho biết các condition nào khớp hoặc không khớp.

Chạy ứng dụng với debug:

```bash
java -jar demo.jar --debug
```

Hoặc khi chạy Gradle:

```bash
./gradlew bootRun --args='--debug'
```

Tùy phiên bản và cách chạy, log có thể chứa phần báo cáo auto-configuration với các nhóm:

- **Positive matches:** cấu hình hoặc condition đã khớp.
- **Negative matches:** cấu hình không khớp; kèm lý do.
- **Exclusions:** các auto-configuration bị loại trừ.
- **Unconditional classes:** các cấu hình không phụ thuộc condition thông thường.

Ví dụ minh họa:

```text
Positive matches:
   MailAutoConfiguration matched:
      - @ConditionalOnClass found required class 'MailClient'

Negative matches:
   AuditAutoConfiguration:
      - @ConditionalOnProperty (app.audit.enabled=true)
        did not find property 'enabled'
```

Thông báo cụ thể phụ thuộc phiên bản và condition. Hãy đọc lý do được report thay vì suy luận từ tên class.

### 19.1. Các câu hỏi chẩn đoán

Khi một bean không xuất hiện, hỏi:

1. Configuration class có được import hoặc component scan không?
2. Condition class-level có khớp không?
3. Property đã được nạp đúng nguồn, đúng tên và đúng profile chưa?
4. Dependency class có thực sự nằm trên runtime classpath không?
5. Condition theo bean có thấy definition cần thiết tại thời điểm đánh giá không?
6. Auto-configuration có bị exclude không?
7. Bean method condition có khớp riêng hay không?
8. Có nhiều bean cùng type hoặc đụng tên khiến startup thất bại sau khi đăng ký không?

Một condition không khớp có thể là hành vi đúng theo thiết kế. Không phải mọi negative match đều là lỗi.

## 20. Các nguồn cấu hình ảnh hưởng điều kiện

Condition theo property phụ thuộc vào Environment. Giá trị cuối cùng có thể đến từ:

- `application.yml` hoặc `application.properties`.
- File cấu hình theo profile.
- File cấu hình bên ngoài JAR.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Các PropertySource do ứng dụng hoặc framework bổ sung.

Ví dụ:

```yaml
# application.yml
app:
  audit:
    enabled: false
```

Command line:

```bash
java -jar demo.jar --app.audit.enabled=true
```

Trong cấu hình Spring Boot thông thường, command-line property có độ ưu tiên cao hơn config data nên condition có thể nhìn thấy giá trị `true`.

Nếu IDE chạy với profile `dev` còn JAR chạy profile `prod`, hai cách chạy có thể nạp property khác nhau. Hãy kiểm tra active profile và property sources thực tế khi kết quả condition khác nhau.

### 20.1. Placeholder và property mặc định

Cấu hình:

```yaml
app:
  audit:
    enabled: ${APP_AUDIT_ENABLED:false}
```

Nếu biến môi trường không tồn tại, placeholder cung cấp `false`. Vì vậy condition:

```java
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
```

không khớp nếu không có giá trị true.

Đây là cách tạo default rõ ràng cho feature flag. Hãy phân biệt default của placeholder với thuộc tính `matchIfMissing` của condition: một cái cung cấp giá trị property, cái kia quy định cách condition phản ứng khi property không tồn tại.

## 21. Những lỗi và hiểu lầm thường gặp

| Hiện tượng hoặc suy nghĩ | Điều thực sự xảy ra | Cách xử lý |
|---|---|---|
| Property đổi sau startup nhưng bean không xuất hiện | Condition không tự chạy lại liên tục | Dùng cơ chế runtime feature flag hoặc refresh architecture phù hợp |
| `@ConditionalOnMissingBean` vẫn tạo bean mặc định dù user có bean | Definition user chưa được đăng ký tại thời điểm condition đánh giá, hoặc type/qualifier không khớp | Xem ordering, auto-configuration và bean type |
| `@ConditionalOnClass` khớp nhưng không kết nối được dịch vụ | Classpath chỉ chứng minh class có mặt, không chứng minh dịch vụ hoạt động | Kiểm tra cấu hình và connectivity riêng |
| Bean method không được gọi | Condition không khớp nên bean definition không được đăng ký | Đọc Condition Evaluation Report |
| Class-level condition false làm mất nhiều bean | Toàn bộ configuration class bị bỏ qua | Đặt condition ở bean method nếu chỉ muốn điều kiện một bean |
| Dùng condition gọi business service | Bean có thể chưa được tạo và gây vòng phụ thuộc/side effect | Dùng environment, metadata, registry hoặc condition chuyên biệt |
| Hai profile cùng active gây trùng bean | Cả hai configuration đều được đăng ký | Thiết kế profile loại trừ nhau hoặc dùng tên/selection phù hợp |
| `@ConditionalOnProperty` không nhận diện indexed collection | Annotation không phù hợp để kiểm tra collection indexed | Dùng custom condition hoặc binding logic phù hợp |
| Auto-configuration không được phát hiện | Chưa đăng ký imports file hoặc package/module không có trên classpath | Kiểm tra AutoConfiguration.imports và artifact |
| Bật `allow-bean-definition-overriding` để sửa condition | Chỉ ảnh hưởng đăng ký trùng tên, không sửa logic điều kiện | Xác định condition và bean definitions thực tế |

### 21.1. Condition false không phải lúc nào cũng là lỗi

Nếu feature audit được cấu hình mặc định là false, việc `AuditConfiguration` không được đăng ký là kết quả đúng. Chỉ khi ứng dụng kỳ vọng audit hoạt động mà condition vẫn false thì mới cần điều tra property hoặc phase.

### 21.2. Condition true không bảo đảm startup thành công

Condition chỉ quyết định cấu hình/bean definition có được chấp nhận. Bean vẫn có thể thất bại sau đó vì constructor ném exception, dependency khác không tồn tại, nhiều bean cùng type gây nhập nhằng, init callback thất bại, cấu hình bên ngoài không hợp lệ hoặc dịch vụ phụ thuộc không sẵn sàng.

Do đó, phân biệt **condition match**, **bean definition registration**, **bean instantiation** và **application readiness**.

## 22. Quy trình thiết kế và chẩn đoán condition

Khi thêm một cấu hình có điều kiện, có thể đi theo các bước:

### Bước 1 — Xác định điều kiện thuộc loại nào

- Classpath: `@ConditionalOnClass` / `@ConditionalOnMissingClass`.
- Property: `@ConditionalOnProperty`.
- Bean registry: `@ConditionalOnBean` / `@ConditionalOnMissingBean`.
- Profile: `@Profile`.
- Web/environment: các condition chuyên biệt tương ứng.
- Logic đặc thù: custom `Condition`.

### Bước 2 — Xác định phạm vi

Điều kiện áp dụng cho cả configuration class hay chỉ một bean method? Nếu cả nhóm bean cùng phụ thuộc điều kiện, đặt trên class. Nếu chỉ một bean tùy chọn, đặt ở method.

### Bước 3 — Xác định phase

Condition cần chạy khi parse configuration hay khi đăng ký bean? Nếu cần chọn phase rõ ràng, implement `ConfigurationCondition`. Tránh giả định registry đã có mọi bean khi condition được gọi.

### Bước 4 — Kiểm tra dependency graph

Nếu condition bỏ một bean, các bean khác có yêu cầu nó qua constructor hay không? Có thể cần đặt condition tương ứng trên nhóm bean phụ thuộc, hoặc thiết kế một implementation mặc định khác.

### Bước 5 — Kiểm tra ordering

Nếu dùng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` trong auto-configuration, bảo đảm user configuration và auto-configuration được xử lý theo quy ước phù hợp. Xem `@AutoConfigureBefore`, `@AutoConfigureAfter` khi cần.

### Bước 6 — Quan sát report và registry

Dùng `--debug` để xem condition report. Nếu cần, kiểm tra bean names/types sau khi context khởi tạo thành công. Không gọi business bean trong condition để chẩn đoán.

### Bước 7 — Phân biệt đăng ký với runtime behavior

Nếu feature cần bật/tắt trong lúc ứng dụng chạy, condition không phải công cụ phù hợp. Chọn một cơ chế runtime có thể thay đổi hành vi mà không trông đợi Spring đăng ký lại bean definitions.

## 23. Bài thực hành

### Bài 1 — Condition theo property

Tạo `AuditConfiguration` với `@ConditionalOnProperty`. Chạy ứng dụng khi `app.audit.enabled` lần lượt là `true`, `false` và không được khai báo. Quan sát bean có xuất hiện trong context không.

### Bài 2 — Condition trên class và method

Đặt một condition trên toàn bộ `@Configuration` có hai `@Bean`, sau đó chuyển condition xuống chỉ một method. So sánh số bean definitions được đăng ký khi điều kiện false.

### Bài 3 — Kiểm tra classpath

Tạo configuration dùng `@ConditionalOnClass` với một class từ dependency optional. Chạy với dependency có và không có trong runtime classpath. Quan sát condition report.

### Bài 4 — Default bean và custom bean

Tạo `@ConditionalOnMissingBean(Clock.class)` cho bean mặc định. Sau đó thêm user configuration cung cấp một bean `Clock`. Quan sát auto-configuration lùi lại khi custom definition được đăng ký đúng thứ tự.

### Bài 5 — Condition theo bean registry

Viết một `ConfigurationCondition` ở phase `REGISTER_BEAN` kiểm tra một bean definition có tên cụ thể. Thử đổi thứ tự xử lý cấu hình và quan sát vì sao registry tại thời điểm condition chạy ảnh hưởng kết quả.

### Bài 6 — Profile

Tạo hai configuration cho `dev` và `prod`. Chạy với từng profile và sau đó bật cả hai. Giải thích vì sao profile không mặc định loại trừ lẫn nhau.

### Bài 7 — Đọc condition report

Chạy ứng dụng với `--debug`. Tìm một positive match và một negative match. Viết lại lý do condition khớp hoặc không khớp bằng ngôn ngữ của bạn.

### Bài 8 — Phân biệt condition với feature flag runtime

Tạo một bean chỉ đăng ký khi `app.feature.audit=true`. Sau khi context đã khởi động, thay đổi giá trị property trong một object Java và quan sát bean definition có tự xuất hiện không. Sau đó thiết kế một service đọc trạng thái feature runtime để so sánh hai cơ chế.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — Condition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Condition.html): hợp đồng đánh giá điều kiện.
- [Spring Framework Javadoc — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): các phase parse và register.
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): cấu hình Java và đăng ký bean.
- [Spring Boot Reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): cách xây dựng auto-configuration và dùng condition.
- [Spring Boot Reference — Auto-configuration classes](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): đăng ký và sắp xếp auto-configuration.

Điều cốt lõi là `@Conditional` quyết định một cấu hình hoặc bean definition có được đưa vào container trong quá trình bootstrap hay không. `PARSE_CONFIGURATION` và `REGISTER_BEAN` xác định thời điểm condition có thể quan sát metadata/registry; sau khi bean definition đã được đăng ký và context đi vào runtime, condition không tự chạy lại mỗi khi property hay trạng thái ứng dụng thay đổi. Hiểu đúng thời điểm này giúp bạn viết auto-configuration có thể mở rộng, tránh phụ thuộc thứ tự đăng ký ngoài ý muốn và chẩn đoán chính xác vì sao một bean có hoặc không có trong Spring Boot.
