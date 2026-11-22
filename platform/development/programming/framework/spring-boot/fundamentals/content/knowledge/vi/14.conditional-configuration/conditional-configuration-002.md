# Condition, ConditionContext và dữ liệu dùng để đánh giá cấu hình

Spring Boot thường tạo bean dựa trên những gì ứng dụng có ở thời điểm khởi động: classpath có thư viện nào, property nào đang được bật, môi trường có phải web application hay không, và đã có bean nào được đăng ký trước đó. Cơ chế này được gọi là **conditional configuration** (cấu hình có điều kiện).

Ở tầng Spring Framework, một điều kiện được biểu diễn bằng interface `Condition`. Khi đánh giá, Spring cung cấp `ConditionContext` để điều kiện đọc môi trường và registry, đồng thời cung cấp `AnnotatedTypeMetadata` để điều kiện biết annotation nào đang được xử lý và các thuộc tính của annotation đó.

Ba thành phần cần phân biệt:

- **`Condition`** chứa quy tắc quyết định cấu hình có phù hợp hay không.
- **`ConditionContext`** cung cấp dữ liệu và các dịch vụ cần thiết để đánh giá quy tắc.
- **`AnnotatedTypeMetadata`** mô tả class hoặc method đang mang `@Conditional` và cung cấp metadata annotation.

Hiểu rõ chúng giúp bạn đọc được cách Spring Boot tự cấu hình ứng dụng, tự viết điều kiện cho thư viện nội bộ và chẩn đoán vì sao một bean được đăng ký hoặc bị bỏ qua.

## 1. Cấu hình có điều kiện là gì?

Không phải ứng dụng nào cũng cần cùng một tập bean. Ví dụ:

- Chỉ đăng ký `EmailSender` khi có property bật email.
- Chỉ tạo tích hợp Redis khi thư viện Redis có mặt trên classpath.
- Cung cấp `Clock` mặc định khi ứng dụng chưa tự khai báo một `Clock` khác.
- Chỉ tạo một controller hoặc service khi ứng dụng chạy trong môi trường web phù hợp.

Thay vì viết một cấu hình duy nhất cho mọi môi trường, Spring cho phép **đăng ký cấu hình hoặc bean khi điều kiện thỏa mãn**.

Luồng khái niệm:

```text
Đọc configuration class / @Bean method
                 |
                 v
       Phát hiện @Conditional
                 |
                 v
       Gọi Condition.matches(...)
                 |
                 v
      Đọc metadata + context data
                 |
                 v
          Điều kiện đúng?
             /       \
           Có         Không
           |            |
           v            v
  Tiếp tục xử lý     Bỏ qua cấu hình
  cấu hình/bean      hoặc bean tương ứng
```

Điều kiện thường được đánh giá trong quá trình xử lý cấu hình, **trước khi bean nghiệp vụ tương ứng được khởi tạo**. Vì vậy, điều kiện không nên phụ thuộc vào việc gọi một bean nghiệp vụ đã hoàn chỉnh.

## 2. `Condition` là gì?

`Condition` là interface trong package `org.springframework.context.annotation`. Nó yêu cầu triển khai phương thức:

```java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

Phương thức trả về:

- `true`: điều kiện phù hợp; Spring tiếp tục xử lý thành phần cấu hình đang được xét.
- `false`: điều kiện không phù hợp; thành phần cấu hình tương ứng bị loại khỏi quá trình xử lý.

Một implementation đơn giản:

```java
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class AlwaysEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

Điều kiện trên luôn trả về `true`, chỉ có ý nghĩa minh họa chữ ký API. Trong ứng dụng thật, `matches()` thường đọc property, classpath, resource, bean definition hoặc metadata annotation để đưa ra quyết định.

### 2.1. `Condition` không phải bean nghiệp vụ

Một condition class thường được Spring khởi tạo để đánh giá cấu hình. Nó không được sử dụng như một service bình thường và không nên có dependency nghiệp vụ cần inject qua constructor.

Ví dụ không nên thiết kế:

```java
// Không nên dùng condition như một service cần inject bean nghiệp vụ.
public class BadCondition implements Condition {

    private final AccountService accountService;

    public BadCondition(AccountService accountService) {
        this.accountService = accountService;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return accountService.hasAccounts();
    }
}
```

Lý do: condition được đánh giá khi Spring còn đang xử lý cấu hình và đăng ký bean definitions. `AccountService` có thể chưa được đăng ký hoặc khởi tạo. Gọi một bean nghiệp vụ ở giai đoạn này dễ tạo vòng phụ thuộc, khởi tạo quá sớm hoặc khiến kết quả điều kiện phụ thuộc trạng thái runtime không phù hợp.

Thay vào đó, condition nên dựa vào **metadata và trạng thái cấu hình có sẵn** trong `ConditionContext`.

## 3. `ConditionContext` cung cấp những dữ liệu nào?

`ConditionContext` là interface trong `org.springframework.context.annotation`. Nó cung cấp những đối tượng giúp condition đánh giá cấu hình mà không cần tự tạo hoặc tự tìm các dịch vụ hạ tầng.

Các phương thức quan trọng:

| Phương thức | Dữ liệu nhận được | Mục đích thường dùng |
| --- | --- | --- |
| `getRegistry()` | `BeanDefinitionRegistry` | Kiểm tra hoặc truy cập registry các bean definitions |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` | Xem thông tin bean factory và những khả năng cấu hình bean |
| `getEnvironment()` | `Environment` | Đọc property, profile và thông tin môi trường |
| `getResourceLoader()` | `ResourceLoader` | Tìm hoặc kiểm tra resource |
| `getClassLoader()` | `ClassLoader` | Kiểm tra sự hiện diện của class và hỗ trợ nạp kiểu |

Tùy thời điểm đánh giá, một số hạ tầng có thể chưa sẵn sàng hoặc chưa chứa toàn bộ bean definitions. Vì vậy, khi viết condition cần dùng đúng nguồn dữ liệu và không giả định application context đã hoàn tất.

### 3.1. `getEnvironment()`: đọc property và profile

`Environment` cho phép truy cập các property từ những nguồn cấu hình Spring đã thiết lập, ví dụ:

- `application.properties` hoặc `application.yml`.
- Biến môi trường hệ điều hành.
- Java system properties.
- Command-line arguments của Spring Boot.
- Những `PropertySource` được ứng dụng bổ sung.

Ví dụ:

```java
boolean enabled = context.getEnvironment()
        .getProperty("features.reports.enabled", Boolean.class, false);
```

Nếu property không tồn tại, ví dụ trên dùng giá trị mặc định `false`.

Bạn cũng có thể kiểm tra profile:

```java
boolean devActive = context.getEnvironment()
        .acceptsProfiles(Profiles.of("dev"));
```

Các profile đang active có thể ảnh hưởng đến việc đăng ký bean, nhưng `Condition` không tự kích hoạt profile. Nó chỉ đọc trạng thái mà `Environment` đang cung cấp.

### 3.2. `getRegistry()`: xem bean definitions đã đăng ký

`BeanDefinitionRegistry` cho phép truy cập danh sách bean definition. Ví dụ:

```java
boolean hasDefinition = context.getRegistry()
        .containsBeanDefinition("paymentGateway");
```

Điều này kiểm tra registry có bean definition với tên đó hay không. Nó không đồng nghĩa với việc đã có một object được khởi tạo. Registry là dữ liệu về định nghĩa; instance được tạo ở giai đoạn lifecycle tương ứng.

Nếu cần kiểm tra ứng viên theo kiểu, một số condition có thể dùng bean factory hoặc metadata tương ứng. Tuy nhiên, ở giai đoạn sớm, cần lưu ý bean factory có thể chưa chứa tất cả definitions sẽ xuất hiện sau đó.

### 3.3. `getBeanFactory()`: thông tin và khả năng của container

`getBeanFactory()` trả về `ConfigurableListableBeanFactory`, cho phép truy cập những thông tin như bean definition, alias, type và các thuộc tính của bean factory.

Ví dụ minh họa:

```java
ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();

boolean registered = beanFactory.containsBeanDefinition("appClock");
```

`getRegistry()` và `getBeanFactory()` phục vụ các mục đích gần nhau nhưng không đồng nhất:

- `BeanDefinitionRegistry` tập trung vào thao tác/tra cứu registry.
- `ConfigurableListableBeanFactory` cung cấp khả năng của bean factory và tra cứu định nghĩa.

Không nên gọi `getBean()` để khởi tạo service nghiệp vụ chỉ nhằm quyết định một condition có đúng hay không.

### 3.4. `getResourceLoader()`: kiểm tra resource

Một cấu hình có thể chỉ cần được đăng ký khi một file resource tồn tại:

```java
Resource resource = context.getResourceLoader()
        .getResource("classpath:features/report-template.json");

return resource.exists();
```

`ResourceLoader` giúp Spring xử lý những vị trí resource theo prefix như `classpath:`, `file:` hoặc URL phù hợp. Điều kiện cần xử lý trường hợp resource không tồn tại và không nên đọc/ghi file ngoài mục tiêu đánh giá.

### 3.5. `getClassLoader()`: kiểm tra thư viện trên classpath

Một thư viện tích hợp có thể chỉ hoạt động khi một class của thư viện tùy chọn có mặt. Dùng classloader giúp condition kiểm tra khả năng hiện diện:

```java
ClassLoader classLoader = context.getClassLoader();
boolean present = ClassUtils.isPresent(
        "com.example.optional.Client",
        classLoader
);
```

`ClassUtils.isPresent` thuộc Spring Core (`org.springframework.util.ClassUtils`). Cách kiểm tra này tránh phải trực tiếp khởi tạo class hoặc tạo client trong giai đoạn condition.

## 4. `AnnotatedTypeMetadata` cung cấp thông tin gì?

`AnnotatedTypeMetadata` nằm trong package `org.springframework.core.type`. Nó biểu diễn metadata annotation của một phần tử đang được xử lý, thường là:

- Một configuration class.
- Một method được khai báo trong configuration class, chẳng hạn method mang `@Bean`.

Metadata này cho phép condition đọc annotation và thuộc tính của annotation mà không cần dựa vào việc tạo bean instance.

Một số API quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isAnnotated(String annotationName)` | Kiểm tra metadata có annotation tương ứng |
| `getAnnotationAttributes(String annotationName)` | Lấy các thuộc tính annotation dưới dạng `Map` |
| `getAllAnnotationAttributes(String annotationName)` | Lấy tất cả giá trị thuộc tính khi annotation có thể xuất hiện theo nhiều đường |
| `hasAnnotation(String annotationName)` | Kiểm tra annotation trực tiếp theo API metadata |
| `hasMetaAnnotation(String metaAnnotationName)` | Kiểm tra metadata có meta-annotation tương ứng |
| `getAnnotations()` | Truy cập mô hình merged annotations |

`AnnotatedTypeMetadata` có thể mô tả class hoặc method; do đó, condition không nên giả định mọi metadata đều đại diện cho một class. Nếu condition được đặt trên một phương thức `@Bean`, metadata có thể là metadata của phương thức đó.

### 4.1. Đọc thuộc tính annotation

Giả sử một annotation tùy biến có thuộc tính `feature`:

```java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnFeature.class.getName()
        );

String feature = (String) attributes.get("value");
```

Condition dùng metadata để biết annotation đang yêu cầu feature nào. Cách này hữu ích khi một condition class có thể được tái sử dụng cho nhiều cấu hình.

### 4.2. Vì sao dùng metadata thay vì reflection trực tiếp?

Reflection trên class runtime thường yêu cầu class đã được nạp. Trong khi đó, Spring có thể đọc metadata từ class file trước khi tạo bean hoặc thậm chí trước khi khởi tạo class cấu hình đầy đủ.

`AnnotatedTypeMetadata` giúp condition hoạt động trên thông tin annotation mà Spring đã phân tích. Điều này hỗ trợ quá trình xử lý cấu hình có điều kiện, hạn chế việc buộc phải khởi tạo class không cần thiết.

Khi làm việc với annotation kết hợp (composed annotation), các API merged annotation của Spring cũng giúp đọc metadata qua quan hệ meta-annotation và alias theo quy tắc của framework.

## 5. Ví dụ tự viết `Condition` dựa trên property

Giả sử ứng dụng có một tính năng báo cáo. Chỉ khi `features.reports.enabled=true`, Spring mới đăng ký cấu hình cung cấp `ReportService`.

### 5.1. Tạo annotation `@ConditionalOnFeature`

```java
package com.example.demo.condition;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(FeatureEnabledCondition.class)
public @interface ConditionalOnFeature {
    String value();
}
```

Annotation này:

- Có thể đặt trên class hoặc method.
- Được giữ lại ở runtime.
- Kết nối với `FeatureEnabledCondition` qua `@Conditional`.
- Nhận tên feature qua thuộc tính `value`.

### 5.2. Viết condition

```java
package com.example.demo.condition;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        ConditionalOnFeature.class.getName()
                );

        if (attributes == null) {
            return false;
        }

        String feature = (String) attributes.get("value");
        String propertyName = "features." + feature + ".enabled";

        return context.getEnvironment().getProperty(
                propertyName,
                Boolean.class,
                false
        );
    }
}
```

Điều kiện thực hiện:

1. Đọc thuộc tính `value` từ annotation metadata.
2. Nếu không lấy được metadata phù hợp, trả về `false`.
3. Tạo property key theo tên feature.
4. Đọc giá trị Boolean từ `Environment`.
5. Chỉ trả về `true` khi property có giá trị `true`; nếu thiếu thì mặc định `false`.

Condition không cần gọi `ReportService`, không cần tạo object nghiệp vụ và cũng không sửa registry.

### 5.3. Dùng annotation trên configuration class

```java
package com.example.demo.report;

import com.example.demo.condition.ConditionalOnFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnFeature("reports")
public class ReportConfiguration {

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }
}
```

Khi điều kiện của configuration class không thỏa mãn, Spring bỏ qua configuration class trong quá trình xử lý phù hợp; method `reportService()` không được dùng để đăng ký bean từ cấu hình đó.

### 5.4. Hoặc dùng trên một `@Bean` method

```java
@Configuration(proxyBeanMethods = false)
public class OptionalFeatureConfiguration {

    @Bean
    @ConditionalOnFeature("reports")
    public ReportService reportService() {
        return new ReportService();
    }
}
```

Ở đây condition áp dụng cho riêng bean definition do phương thức `reportService()` cung cấp. Các cấu hình và bean method khác trong class vẫn có thể được xử lý.

### 5.5. Bật hoặc tắt feature

Trong `application.properties`:

```properties
features.reports.enabled=true
```

Khi bật:

```text
features.reports.enabled=true
        |
        v
FeatureEnabledCondition.matches() = true
        |
        v
ReportService được đăng ký
```

Khi tắt hoặc không khai báo:

```properties
features.reports.enabled=false
```

hoặc không có property tương ứng:

```text
Condition trả về false
        |
        v
ReportService không được đăng ký từ configuration này
```

Nếu một bean khác bắt buộc inject `ReportService` trong khi feature tắt, ứng dụng có thể báo thiếu bean. Khi đó, bean sử dụng feature cũng cần có điều kiện phù hợp, hoặc dependency phải được thiết kế optional qua `ObjectProvider`, `Optional` hoặc cơ chế khác.

## 6. Điều kiện có thể kiểm tra classpath

Một trường hợp phổ biến là chỉ đăng ký tích hợp khi thư viện bên ngoài có mặt.

Ví dụ:

```java
package com.example.demo.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public class OptionalClientPresentCondition implements Condition {

    private static final String CLIENT_CLASS =
            "com.example.optional.OptionalClient";

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return ClassUtils.isPresent(
                CLIENT_CLASS,
                context.getClassLoader()
        );
    }
}
```

Dùng condition:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(OptionalClientPresentCondition.class)
public class OptionalClientConfiguration {

    @Bean
    public OptionalClientAdapter optionalClientAdapter() {
        return new OptionalClientAdapter();
    }
}
```

Ý nghĩa:

- Nếu class `OptionalClient` có mặt trên classpath, condition có thể trả về `true`.
- Nếu thư viện tùy chọn không có mặt, cấu hình được bỏ qua.

Đây là một cách để xây dựng integration module tùy chọn. Trong Spring Boot, bạn thường có thể dùng `@ConditionalOnClass` thay vì tự viết condition cho trường hợp đơn giản này.

**Lưu ý quan trọng:** nếu configuration class có tham chiếu trực tiếp tới kiểu chỉ có trong thư viện tùy chọn, classloader có thể gặp vấn đề trước khi condition kịp bảo vệ cấu hình, tùy cách class được nạp và metadata được xử lý. Với auto-configuration dành cho thư viện tùy chọn, nên tổ chức cấu hình sao cho những class cần thư viện chỉ được nạp khi điều kiện classpath phù hợp, theo pattern auto-configuration mà phiên bản Spring Boot hỗ trợ.

## 7. Điều kiện dựa trên bean đã đăng ký

Một cấu hình mặc định thường cần nhường quyền nếu ứng dụng đã tự cung cấp bean.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

`@ConditionalOnMissingBean` là annotation của Spring Boot. Nó chỉ cho phép bean mặc định được đăng ký khi không tìm thấy bean phù hợp theo tiêu chí đã cấu hình tại thời điểm condition được đánh giá.

Ứng dụng có thể cung cấp bean riêng:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

Trong auto-configuration được sắp xếp đúng, default clock có thể “back off” khi đã có bean `Clock` do ứng dụng cung cấp. Đây là cách Spring Boot cho phép người dùng tùy biến default mà không cần bean definition overriding.

### 7.1. Thời điểm đánh giá có ý nghĩa

Condition kiểm tra bean hiện diện dựa trên những definitions có thể nhìn thấy tại thời điểm đánh giá. Nếu tự viết hai cấu hình người dùng và không xác định thứ tự xử lý, đừng giả định condition luôn nhìn thấy bean sẽ được đăng ký sau.

Spring Boot tổ chức auto-configuration với các cơ chế ordering và condition để hỗ trợ pattern “mặc định nếu người dùng chưa cấu hình”. Với custom auto-configuration, cần theo đúng cơ chế sắp xếp và đăng ký của phiên bản đang dùng.

### 7.2. Kiểm tra theo kiểu và theo tên khác nhau

Hai cách cấu hình sau không hoàn toàn tương đương:

```java
@ConditionalOnMissingBean(Clock.class)
```

và:

```java
@ConditionalOnMissingBean(name = "appClock")
```

Điều kiện đầu xem xét bean theo kiểu `Clock`; điều kiện thứ hai xem xét bean theo tên `appClock`. Khi ứng dụng có nhiều bean cùng kiểu nhưng tên khác nhau, lựa chọn điều kiện sẽ làm thay đổi kết quả.

## 8. Condition trong Spring Boot: các annotation có sẵn

Spring Boot cung cấp nhiều condition phổ biến để bạn không phải tự viết lại những quy tắc thường gặp.

| Annotation | Điều kiện điển hình | Trường hợp sử dụng |
| --- | --- | --- |
| `@ConditionalOnClass` | Một hoặc nhiều class có trên classpath | Tích hợp thư viện tùy chọn |
| `@ConditionalOnMissingClass` | Class được chỉ định không có trên classpath | Chọn cấu hình thay thế |
| `@ConditionalOnBean` | Có bean phù hợp đã được đăng ký | Cấu hình cần một dependency có sẵn |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp | Cung cấp bean mặc định |
| `@ConditionalOnSingleCandidate` | Có một ứng viên phù hợp để chọn theo quy tắc | Tự cấu hình khi dependency không mơ hồ |
| `@ConditionalOnProperty` | Property thỏa điều kiện | Bật/tắt feature bằng cấu hình |
| `@ConditionalOnResource` | Resource được chỉ định tồn tại | Bật cấu hình khi có file/resource |
| `@ConditionalOnWebApplication` | Ứng dụng có kiểu web phù hợp | Cấu hình dành riêng cho web |
| `@ConditionalOnNotWebApplication` | Ứng dụng không chạy trong môi trường web | Cấu hình cho command-line/background app |
| `@ConditionalOnExpression` | SpEL expression cho kết quả phù hợp | Điều kiện phức tạp cần expression |
| `@ConditionalOnJava` | Phiên bản Java phù hợp | Hỗ trợ khác nhau theo Java runtime |
| `@ConditionalOnJndi` | JNDI phù hợp có sẵn | Tích hợp container/JNDI |

Các annotation này thuộc `org.springframework.boot.autoconfigure.condition`. Danh sách và chi tiết thuộc tính phụ thuộc phiên bản Spring Boot; hãy dùng API của đúng phiên bản dự án.

### 8.1. `@ConditionalOnProperty`

Đây là lựa chọn thường gặp để bật/tắt một tính năng:

```java
@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    public MetricsPublisher metricsPublisher() {
        return new MetricsPublisher();
    }
}
```

Trong `application.properties`:

```properties
features.metrics.enabled=true
```

Giải thích:

- `prefix`: phần đầu của property key.
- `name`: phần tên property phía sau prefix.
- `havingValue`: giá trị cần khớp; ở đây là chuỗi `true`.
- `matchIfMissing`: nếu không có property thì có cho điều kiện khớp hay không; mặc định là `false`.

Với ví dụ này, bean chỉ được đăng ký khi `features.metrics.enabled=true`. Nếu property thiếu hoặc mang giá trị khác, method `metricsPublisher()` không tạo bean definition từ cấu hình đó.

### 8.2. `@ConditionalOnClass`

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.optional.OptionalClient")
public class OptionalIntegrationConfiguration {
    // Các bean tích hợp client tùy chọn
}
```

Dùng `name` dạng chuỗi có thể hữu ích khi kiểu được nhắc đến không có mặt trong classpath của mọi ứng dụng. Điều này giúp tránh tham chiếu trực tiếp đến class tùy chọn ngay trong annotation metadata của cấu hình bên ngoài.

### 8.3. `@ConditionalOnMissingBean`

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
public PaymentGateway defaultPaymentGateway() {
    return new DemoPaymentGateway();
}
```

Đây là pattern điển hình của auto-configuration: cung cấp implementation mặc định nếu ứng dụng chưa đăng ký một `PaymentGateway` phù hợp.

### 8.4. Kết hợp nhiều condition

Bạn có thể đặt nhiều annotation điều kiện trên một class hoặc method:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.optional.ReportClient")
@ConditionalOnProperty(
    prefix = "features.reports",
    name = "enabled",
    havingValue = "true"
)
public class ReportIntegrationConfiguration {
    // Cấu hình tích hợp báo cáo
}
```

Trong cách sử dụng thông thường, các condition cùng áp dụng phải thỏa mãn để cấu hình được xử lý. Nghĩa là thư viện phải có mặt **và** feature phải được bật.

## 9. `ConfigurationCondition` và thời điểm đánh giá

Một số điều kiện cần biết Spring đang ở giai đoạn nào của quá trình xử lý configuration. Spring cung cấp `ConfigurationCondition`, một interface mở rộng `Condition`.

Nó bổ sung:

```java
ConfigurationPhase getConfigurationPhase();
```

Hai phase:

| Phase | Ý nghĩa |
| --- | --- |
| `PARSE_CONFIGURATION` | Trong lúc Spring phân tích configuration classes |
| `REGISTER_BEAN` | Trong lúc Spring đăng ký bean definitions |

Ví dụ khái niệm:

```java
public class ParsePhaseCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

Với `PARSE_CONFIGURATION`, điều kiện được xét trong giai đoạn phân tích cấu hình. Với `REGISTER_BEAN`, điều kiện được xét khi Spring đang xử lý đăng ký bean definitions. Việc chọn phase ảnh hưởng dữ liệu nào có thể quan sát được tại thời điểm condition chạy.

### 9.1. Vì sao không nên giả định mọi bean đã tồn tại?

Ở phase parse, Spring có thể chưa đăng ký tất cả bean definitions từ các configuration classes khác. Một condition kiểm tra registry tại giai đoạn này có thể không thấy bean sẽ được đăng ký ở giai đoạn sau.

Nếu quy tắc cần đánh giá sự hiện diện của bean definitions, hãy chọn phase phù hợp và cân nhắc thứ tự xử lý. Đừng dùng condition ở phase sớm để phụ thuộc vào một bean chỉ được đăng ký sau.

### 9.2. Không nhầm phase với lifecycle khởi tạo object

`PARSE_CONFIGURATION` và `REGISTER_BEAN` là phase **xử lý metadata cấu hình**, không phải các phase `@PostConstruct`, `InitializingBean` hay callback khởi tạo instance.

Ví dụ:

```text
Phân tích configuration classes
          |
          v
Đánh giá điều kiện ở parse phase
          |
          v
Đăng ký bean definitions
          |
          v
Đánh giá điều kiện ở register-bean phase
          |
          v
Khởi tạo bean instances khi cần
          |
          v
Initialization callbacks
```

Đây là sơ đồ giản lược; Spring có các processor và bước nội bộ bổ sung.

## 10. `Condition` nên được thiết kế như thế nào?

Một condition tốt nên có những đặc điểm sau:

1. **Chỉ đọc dữ liệu cần thiết:** property, profile, classpath, resource, registry hoặc annotation metadata.
2. **Không tạo side effect:** không khởi động kết nối, ghi file, gửi request hoặc đăng ký bean trong `matches()`.
3. **Không phụ thuộc bean nghiệp vụ:** condition cần chạy khi container còn đang xử lý cấu hình.
4. **Có kết quả dễ dự đoán:** cùng metadata và môi trường thì nên đưa ra cùng quyết định.
5. **Xử lý trường hợp thiếu dữ liệu:** property không tồn tại, class không có hoặc resource không tìm thấy cần có hành vi rõ.
6. **Tách biệt logic:** condition chỉ quyết định có phù hợp hay không; việc tạo object nằm ở configuration hoặc factory method.

Ví dụ condition đọc một property:

```java
public class ExternalSearchEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        return context.getEnvironment().getProperty(
                "search.external.enabled",
                Boolean.class,
                false
        );
    }
}
```

Condition không nên làm như sau:

```java
// Không nên: gọi bean nghiệp vụ trong giai đoạn đánh giá condition.
SomeService service = context.getBeanFactory()
        .getBean(SomeService.class);
return service.isReady();
```

`getBeanFactory()` cung cấp bean factory, nhưng việc gọi `getBean()` có thể ép tạo object trong lúc cấu hình chưa hoàn tất. Điều đó có thể gây vòng phụ thuộc hoặc khởi tạo bean ở thời điểm không mong muốn.

## 11. Condition và auto-configuration trong Spring Boot

Spring Boot sử dụng điều kiện để chỉ áp dụng cấu hình khi các điều kiện cần thiết đã có.

Ví dụ khái niệm:

```text
Có spring-webmvc trên classpath?
          |
          v
Có môi trường servlet web?
          |
          v
Ứng dụng chưa tự cung cấp bean tương ứng?
          |
          v
Đăng ký cấu hình MVC mặc định phù hợp
```

Một auto-configuration thực tế có thể gồm nhiều condition và nhiều bean method. Nó có thể “back off” khi người dùng tự cấu hình bean hoặc property riêng.

### 11.1. Auto-configuration không phải component scan

Hai cơ chế có vai trò khác nhau:

| Cơ chế | Công việc |
| --- | --- |
| Component scanning | Tìm class ứng dụng được đánh dấu stereotype trong package được quét |
| Auto-configuration | Áp dụng cấu hình framework dựa trên classpath, environment, bean definitions và các điều kiện |

Ví dụ, `@Service` của bạn được phát hiện qua component scan. Một cấu hình mặc định của Spring Boot có thể được nhập thông qua cơ chế auto-configuration và chỉ đăng ký bean khi condition tương ứng khớp.

### 11.2. Auto-configuration có thể nhường quyền cho người dùng

Một starter thư viện thường cung cấp bean mặc định:

```java
@Configuration(proxyBeanMethods = false)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Ứng dụng có thể tự cung cấp:

```java
@Configuration(proxyBeanMethods = false)
public class CustomSearchConfiguration {

    @Bean
    public SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

Khi auto-configuration được xử lý đúng thứ tự, `SearchAutoConfiguration` thấy bean `SearchClient` do ứng dụng cung cấp và không đăng ký bean mặc định. Đây là một phần quan trọng của mô hình “convention over configuration” trong Spring Boot.

### 11.3. Condition có thể áp dụng trên class hoặc method

```java
@Configuration
@ConditionalOnProperty(
    prefix = "features",
    name = "audit",
    havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    public AuditWriter auditWriter() {
        return new AuditWriter();
    }

    @Bean
    public AuditReporter auditReporter() {
        return new AuditReporter();
    }
}
```

Condition trên class ảnh hưởng toàn bộ configuration class và các bean method của nó.

Nếu chỉ một bean cần điều kiện:

```java
@Configuration
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features",
        name = "audit",
        havingValue = "true"
    )
    public AuditWriter auditWriter() {
        return new AuditWriter();
    }

    @Bean
    public AuditReporter auditReporter() {
        return new AuditReporter();
    }
}
```

Trong ví dụ thứ hai, `AuditReporter` vẫn được định nghĩa từ configuration class dù property audit không bật. Nếu reporter bắt buộc cần `AuditWriter`, cần thiết kế condition hoặc dependency phù hợp để tránh thiếu bean.

## 12. Chẩn đoán condition không khớp

Khi một bean mong đợi không xuất hiện trong application context, nguyên nhân có thể là condition trả về `false`. Spring Boot cung cấp một số công cụ để xem quyết định auto-configuration.

### 12.1. Bật condition evaluation report

Khởi động ứng dụng với tham số:

```text
--debug
```

Hoặc đặt:

```properties
debug=true
```

Spring Boot có thể in **Conditions Evaluation Report**. Báo cáo cho biết auto-configuration nào được match, không match và lý do tương ứng.

Ví dụ dạng thông tin:

```text
Positive matches:
   SomeAutoConfiguration matched:
      - @ConditionalOnClass found required class ...

Negative matches:
   OtherAutoConfiguration:
      - @ConditionalOnProperty did not find property ...
```

Đây là đầu ra minh họa; tên condition và cách hiển thị phụ thuộc phiên bản Spring Boot.

### 12.2. Phân biệt condition không khớp và bean creation failure

| Hiện tượng | Diễn giải |
| --- | --- |
| Condition trả về `false` | Cấu hình/bean method tương ứng bị bỏ qua |
| Condition trả về `true`, nhưng tạo bean lỗi | Cấu hình được chọn nhưng constructor/factory/dependency hoặc lifecycle gặp lỗi |
| Bean definition không xuất hiện | Có thể condition không khớp, cấu hình không được import/scan hoặc bị loại bởi cơ chế khác |
| Bean tồn tại nhưng inject không được | Có thể sai kiểu, qualifier, primary hoặc nhiều ứng viên |
| Property đã đặt nhưng condition vẫn false | Kiểm tra key, nguồn property, profile, kiểu chuyển đổi và giá trị mong đợi |

Không nên sửa lỗi bean creation bằng cách đổi condition thành luôn `true`. Trước tiên xác định cấu hình bị bỏ qua hay bean được chọn nhưng thất bại khi tạo.

### 12.3. Kiểm tra property thực tế

Nếu condition phụ thuộc `Environment`, hãy kiểm tra:

- Tên property có đúng prefix và spelling không.
- File cấu hình có nằm trong classpath và được nạp không.
- Profile mong muốn đã active chưa.
- Biến môi trường hoặc command-line argument có ghi đè giá trị file không.
- `havingValue` có khớp đúng giá trị không.
- `matchIfMissing` đang là `true` hay `false`.

Ví dụ, với:

```java
@ConditionalOnProperty(
    prefix = "features.reports",
    name = "enabled",
    havingValue = "true"
)
```

property phù hợp là:

```properties
features.reports.enabled=true
```

`features.report.enabled=true` (thiếu chữ `s`) là một key khác nên condition có thể không khớp.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Condition là bean service bình thường.” | Condition được dùng trong quá trình xử lý cấu hình; không nên phụ thuộc bean nghiệp vụ |
| “`ConditionContext` đã chứa mọi bean instance.” | Context cung cấp hạ tầng đánh giá; registry/bean factory có thể chưa hoàn chỉnh |
| “`getRegistry().containsBeanDefinition()` chứng minh bean đã được khởi tạo.” | Nó chỉ xác nhận có bean definition với tên đó |
| “`AnnotatedTypeMetadata` luôn mô tả class.” | Nó có thể mô tả class hoặc method, tùy vị trí `@Conditional` |
| “Condition chỉ đọc application.properties.” | Có thể đọc environment, profile, classpath, resource, registry và metadata |
| “Condition đúng thì bean chắc chắn khởi tạo thành công.” | Condition chỉ cho phép tiếp tục đăng ký; việc tạo bean còn có thể thất bại |
| “`@ConditionalOnMissingBean` luôn thấy mọi bean sẽ được đăng ký sau.” | Nó đánh giá những definitions nhìn thấy tại thời điểm condition chạy |
| “`@Conditional` tự tạo bean.” | Nó chỉ quyết định có xử lý cấu hình/bean method hay không; bean được tạo bởi cơ chế cấu hình |
| “Mọi danh sách bean đều được đánh giá bằng condition.” | Condition áp dụng ở điểm cấu hình được chỉ định, không phải bộ lọc runtime chung cho mọi collection |

## 14. Bài thực hành

### Bài 1 — Bật/tắt feature bằng property

Tạo `@ConditionalOnFeature` và `FeatureEnabledCondition` như mục 5. Tạo `ReportConfiguration` cung cấp `ReportService`.

Chạy ứng dụng với:

```properties
features.reports.enabled=true
```

Sau đó đổi thành:

```properties
features.reports.enabled=false
```

Quan sát `ReportService` có được đăng ký hay không. Giải thích giá trị mặc định khi property bị bỏ trống.

### Bài 2 — Đọc profile từ `ConditionContext`

Viết một condition chỉ match khi profile `dev` active:

```java
return context.getEnvironment()
        .acceptsProfiles(Profiles.of("dev"));
```

Gắn condition lên một configuration class. Khởi động lần lượt với profile `dev` và `prod`, rồi quan sát bean.

### Bài 3 — Kiểm tra classpath

Viết condition dùng `ClassUtils.isPresent(...)` để kiểm tra một class thư viện tùy chọn. Chạy dự án khi dependency có mặt, sau đó loại dependency khỏi cấu hình build và quan sát kết quả. Giải thích vì sao condition cần tránh tham chiếu trực tiếp đến kiểu không có mặt.

### Bài 4 — Phân biệt registry và instance

Trong condition, dùng `getRegistry().containsBeanDefinition("appClock")` để kiểm tra definition. So sánh với việc tra cứu bean trong application context sau khi khởi động.

Giải thích vì sao registry có definition không đồng nghĩa instance đã được tạo.

### Bài 5 — Điều kiện theo metadata annotation

Tạo annotation có thuộc tính `value`, dùng `AnnotatedTypeMetadata.getAnnotationAttributes(...)` để đọc giá trị. Đặt annotation trên configuration class và trên một `@Bean` method. Quan sát metadata tương ứng trong `matches()`.

### Bài 6 — Dùng condition có sẵn của Spring Boot

Thử các annotation:

- `@ConditionalOnProperty`
- `@ConditionalOnClass`
- `@ConditionalOnMissingBean`

Với từng annotation, mô tả dữ liệu nào quyết định kết quả và điều gì xảy ra khi điều kiện không thỏa mãn.

### Bài 7 — Xem Condition Evaluation Report

Khởi động ứng dụng với `--debug`. Tìm một auto-configuration có positive match và một auto-configuration có negative match. Giải thích condition cụ thể nào đã quyết định kết quả.

## 15. Ghi nhớ

`Condition` chứa quy tắc trả lời câu hỏi **cấu hình này có phù hợp với môi trường hiện tại không?** `ConditionContext` cung cấp các dữ liệu như environment, registry, bean factory, resource loader và classloader. `AnnotatedTypeMetadata` cung cấp thông tin về class hoặc method đang mang annotation, giúp condition đọc thuộc tính và các metadata liên quan.

Spring Boot xây dựng nhiều auto-configuration dựa trên các condition này. Khi cần tùy biến, hãy ưu tiên annotation có sẵn như `@ConditionalOnProperty`, `@ConditionalOnClass` và `@ConditionalOnMissingBean`; chỉ viết `Condition` riêng khi quy tắc của ứng dụng thực sự cần thiết.

Một condition nên đọc metadata và trạng thái cấu hình, trả về kết quả rõ ràng, không tạo side effect và không gọi bean nghiệp vụ trong giai đoạn xử lý cấu hình. Nắm được cách dữ liệu được đánh giá sẽ giúp bạn hiểu vì sao Spring Boot đăng ký hoặc bỏ qua một bean, đồng thời xây dựng các starter và cấu hình tùy biến dễ dự đoán hơn.
