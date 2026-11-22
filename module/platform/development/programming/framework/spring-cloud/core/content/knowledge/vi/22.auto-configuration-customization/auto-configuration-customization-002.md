# @ConditionalOnClass, @ConditionalOnBean và @ConditionalOnMissingBean

> **Chương:** Tùy biến tự động cấu hình  
> **Module:** SPRING_CLOUD_CORE

Spring Boot và Spring Cloud dùng auto-configuration để tự tạo các bean tích hợp khi điều kiện môi trường phù hợp. Một cấu hình có thể chỉ nên hoạt động khi thư viện tùy chọn có trên classpath; một bean adapter chỉ có ý nghĩa khi một service khác đã tồn tại; và bean mặc định chỉ nên được tạo khi ứng dụng chưa cung cấp implementation riêng.

Ba annotation **`@ConditionalOnClass`**, **`@ConditionalOnBean`** và **`@ConditionalOnMissingBean`** giải quyết ba quyết định khác nhau đó. Chúng giúp auto-configuration thích ứng với dependency và bean thực tế trong ApplicationContext, đồng thời cho phép ứng dụng tùy biến mà không phải sửa mã nguồn thư viện tích hợp.

Bài này dùng ví dụ một module catalog trong hệ thống **SPRING_CLOUD_CORE** để giải thích điều kiện classpath, điều kiện bean, thứ tự xử lý auto-configuration, cách tạo fallback có thể ghi đè và cách kiểm thử từng nhánh điều kiện.

## 1. Auto-configuration và điều kiện kích hoạt

Auto-configuration là các cấu hình Spring được import tự động dựa trên classpath, bean hiện có và property. Một auto-configuration tốt không giả định mọi ứng dụng đều có cùng dependency hoặc cùng cách triển khai.

Ví dụ, module tích hợp catalog có thể cung cấp:

- Adapter `CatalogClient` khi SDK của nhà cung cấp có mặt.
- `CatalogHealthIndicator` khi một `CatalogClient` đã được tạo.
- Implementation mặc định của `CatalogClient` nếu ứng dụng chưa cung cấp implementation riêng.

Nếu tạo tất cả bean vô điều kiện, ứng dụng có thể gặp lỗi thiếu class, thiếu dependency hoặc xung đột bean khi người dùng tự cấu hình. Các condition annotation cho phép Spring chỉ áp dụng đúng phần cấu hình cần thiết.

~~~mermaid
flowchart TB
    A["Auto-configuration được import"]
    A --> B{"SDK có trên classpath?"}
    B -->|Không| X["Bỏ qua cấu hình tích hợp SDK"]
    B -->|Có| C{"CatalogClient đã có bean?"}
    C -->|Có| D["Giữ implementation của ứng dụng"]
    C -->|Không| E["Tạo CatalogClient mặc định"]
    D --> F{"Có CatalogClient trong context?"}
    E --> F
    F -->|Có| G["Tạo health indicator nếu chưa có"]
    F -->|Không| H["Không tạo health indicator"]
~~~

Các condition có thể đặt trên class cấu hình hoặc trên từng phương thức `@Bean`. Phạm vi đặt annotation quyết định Spring bỏ qua toàn bộ cấu hình hay chỉ bỏ qua một bean method.

## 2. @ConditionalOnClass: chỉ cấu hình khi class có trên classpath

`@ConditionalOnClass` kiểm tra một hoặc nhiều class có thể được tìm thấy bởi classloader của ứng dụng hay không. Điều kiện này hữu ích khi auto-configuration tích hợp thư viện tùy chọn.

Ví dụ, `CatalogSdk` chỉ có khi ứng dụng thêm SDK của nhà cung cấp. Module không nên cố tạo adapter nếu SDK đó không có.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
    // Các bean cần CatalogSdk được khai báo trong cấu hình này.
}
~~~

Thuộc tính `name` nhận tên class đầy đủ dưới dạng chuỗi. Cách này hữu ích khi muốn tránh tham chiếu trực tiếp đến class tùy chọn trong annotation.

### 2.1. Dùng value hoặc name

Có thể dùng class literal khi class có trong compile classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(CatalogSdk.class)
public class CatalogSdkAutoConfiguration {
}
~~~

Hoặc dùng tên class:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
}
~~~

Khác biệt thực tế:

| Thuộc tính | Kiểu | Khi phù hợp |
| --- | --- | --- |
| `value` | `Class<?>[]` | Class có sẵn trong compile classpath và annotation được đặt trực tiếp trên cấu hình |
| `name` | `String[]` | Muốn tham chiếu class tùy chọn bằng tên, đặc biệt trong meta-annotation hoặc khi tránh class literal |

Spring Boot đọc metadata của configuration class bằng ASM để có thể đánh giá điều kiện classpath mà không phải tải mọi kiểu được tham chiếu trong annotation. Tuy nhiên, nếu tự tạo annotation tổng hợp (meta-annotation), nên dùng `name` để tránh class tùy chọn bị tải quá sớm trong quá trình xử lý annotation.

### 2.2. Cẩn thận với kiểu trả về của @Bean

Một tình huống dễ gây lỗi là đặt điều kiện classpath trên bean method nhưng method có kiểu tham số hoặc kiểu trả về thuộc thư viện tùy chọn. Nếu class tùy chọn bị phân giải trước khi condition loại method, ứng dụng có thể gặp lỗi tải class.

Khi auto-configuration phụ thuộc class tùy chọn, cách an toàn là đặt bean methods tham chiếu class đó trong một nested configuration class có điều kiện classpath ở cấp class:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

Trong ví dụ, `CatalogSdk` được dùng trong nested configuration chỉ khi class đó hiện diện. Outer auto-configuration không cần khai báo kiểu SDK trong method signature của chính nó.

Cách tổ chức này cũng giúp gom các bean cùng phụ thuộc vào một thư viện tùy chọn vào một vùng cấu hình có điều kiện.

### 2.3. Điều kiện classpath không kiểm tra bean

Có class trên classpath không có nghĩa một bean dùng class đó đã được tạo. `@ConditionalOnClass` chỉ xác nhận khả năng tải class.

Ví dụ:

- SDK có trong dependency graph.
- Nhưng auto-configuration của SDK bị tắt bằng property.
- Hoặc ứng dụng không tạo bean SDK.
- Hoặc cấu hình SDK không hợp lệ.

Trong các trường hợp này, điều kiện classpath vẫn có thể match. Nếu bean adapter cần một bean khác, hãy kết hợp thêm `@ConditionalOnBean`.

## 3. @ConditionalOnBean: chỉ tạo cấu hình khi bean phụ thuộc đã tồn tại

`@ConditionalOnBean` kiểm tra ApplicationContext có bean theo kiểu, tên hoặc annotation được chỉ định hay không. Nó phù hợp khi một cấu hình chỉ có ý nghĩa nếu một thành phần khác đã được tạo.

Ví dụ, `CatalogHealthIndicator` cần `CatalogClient`. Nếu không có client, indicator không thể hoạt động và không nên được tạo.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {

    @Bean
    CatalogHealthIndicator catalogHealthIndicator(CatalogClient client) {
        return new CatalogHealthIndicator(client);
    }
}
~~~

Ở đây condition đặt trên class nên toàn bộ `CatalogHealthAutoConfiguration` chỉ được áp dụng khi bean `CatalogClient` đã hiện diện tại thời điểm Spring đánh giá điều kiện.

Có thể đặt condition trên method nếu chỉ một bean cần dependency đó:

~~~java
@Bean
@ConditionalOnBean(CatalogClient.class)
CatalogMetrics catalogMetrics(CatalogClient client) {
    return new CatalogMetrics(client);
}
~~~

### 3.1. Các cách chỉ định bean

Annotation hỗ trợ các thuộc tính để xác định bean cần tìm, thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Các kiểu bean cần có |
| `type` | Tên đầy đủ của kiểu bean dưới dạng chuỗi |
| `name` | Tên bean cần có |
| `annotation` | Annotation mà bean cần mang |

Dùng `value` khi kiểu đã có trong compile classpath. Dùng `type` khi muốn tham chiếu kiểu bằng tên chuỗi. Dùng `name` khi hợp đồng cấu hình dựa vào bean name cụ thể.

Không nên ràng buộc bằng bean name nếu ứng dụng có thể thay implementation mà vẫn giữ cùng contract. Kiểm tra theo interface thường tạo auto-configuration dễ mở rộng hơn.

### 3.2. @ConditionalOnBean không kiểm tra dịch vụ từ xa có khỏe không

Điều kiện bean chỉ kiểm tra bean definition trong ApplicationContext. Nó không gọi endpoint, không kiểm tra registry, không ping database và không xác nhận dependency từ xa có thể truy cập.

Ví dụ `CatalogClient` tồn tại nhưng DNS của catalog service đang lỗi. `@ConditionalOnBean(CatalogClient.class)` vẫn match. Muốn kiểm tra khả năng phục vụ, hãy dùng health indicator hoặc logic runtime phù hợp.

### 3.3. Thời điểm đánh giá điều kiện rất quan trọng

`@ConditionalOnBean` chỉ nhìn thấy bean definitions đã được xử lý tại thời điểm condition được đánh giá. Do đó, nó phù hợp nhất trong auto-configuration, nơi Spring Boot có thể sắp xếp các cấu hình theo thứ tự.

Nếu đặt condition trong một cấu hình component-scan thông thường, một bean nằm ở cấu hình được xử lý sau có thể chưa được nhìn thấy khi condition chạy. Kết quả có thể khác điều mà người viết cấu hình mong đợi.

Khi auto-configuration A cung cấp `CatalogClient` và auto-configuration B phụ thuộc vào client đó, hãy khai báo thứ tự để B được xử lý sau A.

~~~java
@AutoConfiguration(after = CatalogSdkAutoConfiguration.class)
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {
    // Bean chỉ phụ thuộc CatalogClient được khai báo tại đây.
}
~~~

`@AutoConfigureAfter` điều chỉnh thứ tự giữa các auto-configuration; nó không tạo bean còn thiếu và không bảo đảm một bean sẽ tồn tại. Condition vẫn phải được đánh giá dựa trên bean definitions thực tế.

## 4. @ConditionalOnMissingBean: tạo fallback khi ứng dụng chưa tự cung cấp bean

`@ConditionalOnMissingBean` kiểm tra chưa có bean phù hợp trong context. Đây là annotation quan trọng để tạo default bean có thể được ứng dụng ghi đè.

Ví dụ module cung cấp một implementation mặc định của `CatalogClient`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogSdk sdk) {
        return new SdkCatalogClient(sdk);
    }
}
~~~

Nếu ứng dụng không có bean `CatalogClient`, Spring tạo `SdkCatalogClient`. Nếu ứng dụng đã khai báo một bean triển khai `CatalogClient`, method mặc định bị bỏ qua và bean của ứng dụng được sử dụng.

### 4.1. Cho phép người dùng tùy biến implementation

Ứng dụng có thể cung cấp implementation riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CachedCatalogClient();
    }
}
~~~

Auto-configuration mặc định có `@ConditionalOnMissingBean(CatalogClient.class)` sẽ lùi lại khi bean tùy chỉnh đã được đăng ký.

Đây là một nguyên tắc thiết kế quan trọng của starter: cung cấp giá trị mặc định hữu ích nhưng không khóa người dùng vào implementation của thư viện.

### 4.2. Khai báo kiểu trả về đủ cụ thể

Hãy khai báo kiểu trả về của `@Bean` theo contract mà condition cần kiểm tra:

~~~java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogSdk sdk) {
    return new SdkCatalogClient(sdk);
}
~~~

Không nên khai báo method chỉ trả về `Object` nếu mục tiêu là để Spring nhận diện bean theo `CatalogClient`. Trong giai đoạn đánh giá điều kiện, Spring cần thông tin kiểu bean từ metadata và method signature; kiểu trả về quá chung có thể khiến điều kiện không nhận diện được bean như mong đợi.

Nếu có nhiều contract, khai báo kiểu trả về theo abstraction công khai phù hợp và đặt `@ConditionalOnMissingBean` với contract cụ thể.

### 4.3. Missing bean không đồng nghĩa missing implementation trên classpath

`@ConditionalOnMissingBean` hỏi ApplicationContext có bean phù hợp hay chưa. Nó không hỏi class implementation có nằm trong JAR hay không.

Một class `CustomCatalogClient` có thể có trên classpath nhưng nếu không được đăng ký thành bean, condition vẫn có thể match và tạo default bean. Ngược lại, một bean được tạo từ factory hoặc `@Bean` method có thể khiến fallback bị bỏ qua dù class implementation không được component-scan.

Phân biệt classpath với bean registry giúp chẩn đoán chính xác vì sao default bean được tạo hoặc bị bỏ qua.

## 5. Kết hợp ba condition trong một module

Một auto-configuration có thể kết hợp cả ba điều kiện để tạo ra hành vi linh hoạt:

1. Chỉ kích hoạt phần tích hợp nếu SDK có trên classpath.
2. Chỉ tạo default `CatalogClient` nếu ứng dụng chưa cung cấp bean riêng.
3. Chỉ tạo health indicator nếu `CatalogClient` thực sự tồn tại.

Có thể tách thành các auto-configuration để thể hiện thứ tự và trách nhiệm:

~~~java
@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

Auto-configuration phụ thuộc:

~~~java
@AutoConfiguration(after = CatalogSdkAutoConfiguration.class)
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogHealthIndicator.class)
    CatalogHealthIndicator catalogHealthIndicator(CatalogClient client) {
        return new CatalogHealthIndicator(client);
    }
}
~~~

Cấu trúc này cho phép ứng dụng thay `CatalogClient` hoặc `CatalogHealthIndicator` bằng bean riêng. Health auto-configuration chỉ hoạt động khi client contract có trong context.

Nếu SDK không có, `CatalogSdkAutoConfiguration` không tạo default client. Nếu ứng dụng tự cung cấp `CatalogClient` mà không dùng SDK, health auto-configuration vẫn có thể hoạt động vì nó chỉ phụ thuộc vào contract `CatalogClient`.

### 5.1. Đăng ký auto-configuration

Với Spring Boot 3, auto-configuration của thư viện thường được liệt kê trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung:

~~~text
com.example.catalog.CatalogSdkAutoConfiguration
com.example.catalog.CatalogHealthAutoConfiguration
~~~

Chỉ các auto-configuration được đăng ký mới được Spring Boot import tự động. Nếu class tồn tại nhưng không có trong imports file, ứng dụng có thể không bao giờ đánh giá các condition của nó.

Các dự án dùng Spring Boot phiên bản cũ hơn có thể sử dụng cơ chế đăng ký auto-configuration khác, chẳng hạn `spring.factories` trong các release tương ứng. Hãy đối chiếu cách đăng ký với phiên bản Spring Boot mà thư viện hỗ trợ.

## 6. Đặt condition ở cấp class hay cấp bean method?

Condition có thể áp dụng ở hai mức:

| Vị trí | Kết quả khi condition không match |
| --- | --- |
| Trên class `@Configuration` hoặc `@AutoConfiguration` | Toàn bộ cấu hình đó bị bỏ qua |
| Trên method `@Bean` | Chỉ bean method đó không được áp dụng |

Ví dụ condition ở cấp class:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
public class CatalogSdkAutoConfiguration {
    // Tất cả bean trong cấu hình đều cần SDK.
}
~~~

Ví dụ condition ở cấp method:

~~~java
@AutoConfiguration
public class OptionalCatalogMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(CatalogClient.class)
    CatalogMetrics catalogMetrics(CatalogClient client) {
        return new CatalogMetrics(client);
    }

    @Bean
    CatalogDiagnostics catalogDiagnostics() {
        return new CatalogDiagnostics();
    }
}
~~~

Trong ví dụ thứ hai, thiếu `CatalogClient` chỉ ngăn tạo `CatalogMetrics`; `CatalogDiagnostics` vẫn có thể được tạo.

Nên đặt condition ở cấp class khi toàn bộ cấu hình phụ thuộc cùng một điều kiện. Đặt ở method khi chỉ một số bean phụ thuộc vào điều kiện đó.

## 7. Các condition kết hợp với nhau như thế nào?

Khi nhiều condition được đặt trên cùng một cấu hình hoặc bean method, tất cả condition tương ứng phải match để bean được tạo.

Ví dụ:

~~~java
@AutoConfiguration
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class CatalogSdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogSdk sdk) {
            return new SdkCatalogClient(sdk);
        }
    }
}
~~~

Ý nghĩa:

- SDK class phải có trên classpath.
- Bean `CatalogSdk` phải tồn tại trong context.
- Chưa có bean `CatalogClient`.

Chỉ khi cả ba điều kiện match, bean mặc định mới được đăng ký.

Trong auto-configuration thực tế, có thể đặt classpath condition ở class cấu hình và bean conditions ở method để tránh tham chiếu class tùy chọn không an toàn. Ví dụ trên minh họa logic kết hợp; nếu `CatalogSdk` là dependency tùy chọn, hãy dùng nested configuration class như phần trước.

### 7.1. Condition không phải thứ tự thực thi nghiệp vụ

Condition quyết định cấu hình hoặc bean có được đăng ký hay không. Nó không phải callback để thực hiện công việc sau khi ứng dụng khởi động.

Không đặt thao tác kết nối mạng, tạo dữ liệu, gọi API từ xa hoặc side effect vào logic condition. Condition cần đánh giá nhanh, xác định và dựa trên metadata của classpath/bean registry.

Nếu cần kiểm tra dependency từ xa, hãy dùng health indicator hoặc startup validation có chủ đích thay vì condition bean.

## 8. Những lỗi thiết kế thường gặp

### 8.1. Dùng @ConditionalOnBean trong component scan thông thường

Nếu cấu hình phụ thuộc bean được tạo sau, condition có thể đánh giá trước khi bean đó được đăng ký. Hãy chuyển logic phụ thuộc sang auto-configuration và khai báo ordering phù hợp.

### 8.2. Dùng @ConditionalOnClass để kiểm tra bean

Class tồn tại không có nghĩa bean đã được tạo. Nếu bean dependency là điều kiện cần, dùng `@ConditionalOnBean`.

### 8.3. Dùng @ConditionalOnBean để kiểm tra classpath

Nếu class tùy chọn không có, việc tham chiếu trực tiếp vào method signature hoặc cấu hình có thể gây lỗi tải class trước khi bean condition có thể giúp. Dùng `@ConditionalOnClass` để bảo vệ phần cấu hình phụ thuộc class đó.

### 8.4. Quên @ConditionalOnMissingBean trên default bean

Nếu auto-configuration tạo bean mặc định vô điều kiện, ứng dụng cung cấp implementation riêng có thể gặp `NoUniqueBeanDefinitionException` hoặc phải dùng `@Primary` để né xung đột. Với bean được thiết kế để người dùng thay thế, nên có missing-bean condition.

### 8.5. Dùng return type quá chung

Nếu method `@Bean` khai báo kiểu trả về `Object`, Spring có thể không nhận diện contract cần thiết trong giai đoạn condition evaluation. Hãy dùng kiểu interface hoặc class cụ thể mà auto-configuration muốn công bố.

### 8.6. Khai báo điều kiện trên class quá rộng

Một condition không match ở cấp class làm toàn bộ bean trong cấu hình biến mất. Nếu chỉ một bean cần dependency tùy chọn, đặt condition ở method hoặc tách nested configuration phù hợp.

### 8.7. Cho rằng missing-bean condition là cơ chế bảo mật

`@ConditionalOnMissingBean` chỉ quyết định bean mặc định có được tạo hay không. Nó không ngăn code khác đăng ký bean, không phân quyền gọi service và không kiểm soát truy cập registry.

## 9. Kiểm thử auto-configuration với ApplicationContextRunner

Spring Boot cung cấp `ApplicationContextRunner` để kiểm thử auto-configuration trong một ApplicationContext nhỏ, nhanh và độc lập. Đây là cách phù hợp để kiểm tra từng nhánh condition mà không phải khởi động toàn bộ ứng dụng.

Ví dụ dưới đây giả định `CatalogSdkAutoConfiguration` và `CatalogHealthAutoConfiguration` được đăng ký đúng, `CatalogSdk` là kiểu từ SDK tùy chọn, còn các interface/client là kiểu của module.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CatalogSdkAutoConfiguration.class,
                            CatalogHealthAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenSdkAndSdkBeanExist() {
        contextRunner
                .withBean(CatalogSdk.class, FakeCatalogSdk::new)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).hasSingleBean(CatalogHealthIndicator.class);
                });
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        CachedCatalogClient customClient = new CachedCatalogClient();

        contextRunner
                .withBean(CatalogSdk.class, FakeCatalogSdk::new)
                .withBean(CatalogClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class))
                            .isSameAs(customClient);
                });
    }

    @Test
    void doesNotCreateClientWhenSdkBeanIsMissing() {
        contextRunner
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }

    @Test
    void doesNotCreateSdkIntegrationWhenSdkClassIsMissing() {
        contextRunner
                .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }

    @Test
    void doesNotCreateHealthIndicatorWithoutClient() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogHealthAutoConfiguration.class))
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(CatalogHealthIndicator.class);
                });
    }
}
~~~

Các class `FakeCatalogSdk`, `CachedCatalogClient` và `CatalogHealthIndicator` là fixture minh họa cần được cung cấp trong test source của dự án. Test `FilteredClassLoader` giả lập môi trường không có SDK để xác nhận nhánh classpath condition.

### 9.1. Ma trận kiểm thử

| SDK class | SDK bean | Custom CatalogClient | Kết quả mong đợi |
| --- | --- | --- | --- |
| Có | Có | Không | Tạo default client; tạo health indicator |
| Có | Có | Có | Dùng custom client; không tạo default client |
| Có | Không | Không | Không tạo default client nếu cấu hình yêu cầu SDK bean |
| Không | Không | Không | Bỏ qua SDK auto-configuration |
| Không | Không | Có | Có thể giữ custom client; health indicator phụ thuộc client contract |

Ma trận giúp kiểm tra độc lập classpath condition, bean condition và missing-bean fallback. Khi có nhiều auto-configuration, hãy kiểm tra thêm thứ tự và bean thực tế trong context.

## 10. Chẩn đoán condition evaluation

Khi một bean không xuất hiện, đừng vội kết luận dependency bị thiếu. Hãy xác định condition nào không match.

Các công cụ hữu ích:

- `ApplicationContextRunner` để tái tạo nhánh điều kiện trong test nhỏ.
- Actuator Conditions Endpoint hoặc condition evaluation report để xem auto-configuration match/negative match.
- Log khởi động ở chế độ debug để xem báo cáo condition.
- `ApplicationContext` bean inspection để xác nhận bean nào thực sự được đăng ký.
- Dependency tree để xác nhận class có trong runtime classpath.

Một số cách đọc triệu chứng:

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Auto-configuration không được import | Imports metadata hoặc điều kiện loại trừ auto-configuration |
| `@ConditionalOnClass` không match | Dependency có trong runtime classpath không; classloader có nhìn thấy class không |
| `@ConditionalOnBean` không match | Bean dependency có được tạo trước khi condition đánh giá không; đúng kiểu/name không |
| Default bean không xuất hiện | Có bean cùng contract đã tồn tại không; return type có đủ cụ thể không |
| Có hai implementation cùng contract | Default bean có thiếu `@ConditionalOnMissingBean` không; user bean có được phát hiện không |
| Condition hoạt động khác giữa profile | Property, profile và nguồn cấu hình có làm thay đổi bean/classpath không |

Trong Spring Boot, Actuator Conditions Endpoint thường được truy cập qua `GET /actuator/conditions` khi endpoint tương ứng đã được expose. Endpoint này cung cấp báo cáo condition, không tự sửa cấu hình.

## 11. Quy tắc thiết kế auto-configuration dễ mở rộng

Khi viết một starter hoặc module tích hợp trong hệ sinh thái Spring Cloud, nên áp dụng các nguyên tắc:

1. Bảo vệ integration tùy chọn bằng `@ConditionalOnClass`.
2. Dùng nested configuration khi class tùy chọn xuất hiện trong method signature.
3. Chỉ tạo adapter phụ thuộc khi bean contract cần thiết đã tồn tại bằng `@ConditionalOnBean`.
4. Cung cấp implementation mặc định bằng `@ConditionalOnMissingBean`.
5. Khai báo return type theo contract để condition có metadata rõ ràng.
6. Sắp xếp auto-configuration phụ thuộc bằng `@AutoConfigureAfter` hoặc before phù hợp.
7. Đặt condition ở class level nếu toàn bộ cấu hình phụ thuộc điều kiện; dùng method level nếu chỉ một bean cần nó.
8. Giữ condition thuần metadata, không gọi hệ thống từ xa hoặc tạo side effect.
9. Kiểm thử cả nhánh match và không match bằng `ApplicationContextRunner`.
10. Bảo đảm auto-configuration được đăng ký theo cơ chế đúng của phiên bản Spring Boot hỗ trợ.

Một starter tốt cung cấp default behavior có thể thay thế, không bắt buộc mọi ứng dụng phải dùng cùng một SDK hoặc cùng implementation.

## 12. Điểm cần ghi nhớ

`@ConditionalOnClass` kiểm tra class có trên classpath; `@ConditionalOnBean` kiểm tra bean dependency đã có trong ApplicationContext; `@ConditionalOnMissingBean` cho phép auto-configuration tạo fallback khi ứng dụng chưa cung cấp bean phù hợp.

Ba điều kiện này thường được kết hợp trong auto-configuration: classpath mở cổng cho integration tùy chọn, bean condition bảo đảm dependency trong context đã sẵn sàng, còn missing-bean condition giữ quyền tùy biến cho ứng dụng. Để kết quả ổn định, cần chú ý thứ tự auto-configuration, kiểu trả về của `@Bean`, vị trí đặt condition và kiểm thử cả trường hợp có lẫn không có dependency trong **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionalOnClass](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot API — ConditionalOnBean](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
