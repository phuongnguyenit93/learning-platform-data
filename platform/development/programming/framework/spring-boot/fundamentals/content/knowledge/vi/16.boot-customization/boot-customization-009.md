# Đăng ký cấu hình dùng chung mà không quét toàn bộ package thư viện

Khi xây dựng một thư viện dùng chung cho nhiều ứng dụng Spring Boot, thư viện có thể cung cấp những bean như HTTP client, bộ chuyển đổi dữ liệu, service tích hợp, validator hoặc cấu hình bảo mật. Tuy nhiên, chỉ thêm JAR vào dependency không có nghĩa Spring sẽ tự động phát hiện mọi class được đánh dấu `@Component` trong JAR đó.

Ứng dụng chủ thường đặt `@SpringBootApplication` trong package riêng, còn thư viện nằm ở một package hoặc module khác. Component scan mặc định chỉ bắt đầu từ package của lớp main và đi xuống các package con. Vì vậy, package thư viện nằm ngoài phạm vi này sẽ không được quét.

Một cách giải quyết có vẻ nhanh là quét toàn bộ package thư viện, nhưng điều đó có thể đăng ký nhiều component nội bộ không thuộc API công khai, gây xung đột bean name hoặc kích hoạt những tính năng ứng dụng không cần. Spring cung cấp các cơ chế tường minh hơn:

- `@Import` để nhập một hoặc một nhóm cấu hình/class đã biết.
- Annotation dạng `@Enable...` để ứng dụng chủ bật một module dùng chung bằng một khai báo.
- Auto-configuration của Spring Boot để starter tự đăng ký cấu hình theo classpath và điều kiện.
- `ImportSelector` hoặc `ImportBeanDefinitionRegistrar` khi thư viện thật sự cần lựa chọn hoặc đăng ký bean động.
- Component scan có phạm vi hẹp khi module có nhiều component cần phát hiện theo package.

Mục tiêu là công bố **một điểm vào cấu hình ổn định**, để ứng dụng chọn dùng module nào và Spring chỉ đăng ký những bean mà module đó chủ động cung cấp.

## 1. Vì sao dependency thư viện không tự tạo bean?

Giả sử ứng dụng có cấu trúc:

~~~text
com.example.orders
├── OrdersApplication.java
├── controller
├── service
└── repository

com.acme.sharedclient
├── SharedClient.java
├── SharedClientService.java
├── config
│   └── SharedClientConfiguration.java
└── internal
    ├── DefaultTokenProvider.java
    └── RetrySupport.java
~~~

Lớp khởi động:

~~~java
package com.example.orders;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Component scan mặc định xuất phát từ `com.example.orders` và đi xuống các package con như `com.example.orders.service`. Package `com.acme.sharedclient` là package khác, không nằm dưới package gốc của ứng dụng.

Ngay cả khi JAR thư viện đã có trên runtime classpath, Spring cũng không tự quét toàn bộ class trong JAR. Classpath chỉ cho phép JVM tải class; component scanning, `@Import` hoặc cơ chế đăng ký khác mới đưa bean definition vào Spring container.

Đây là ba việc riêng biệt:

| Việc | Ý nghĩa |
|---|---|
| Thêm dependency | Đưa thư viện và các dependency bắc cầu vào classpath theo scope |
| Phát hiện/đăng ký bean | Đưa bean definition vào BeanFactory bằng scan, import, auto-configuration hoặc đăng ký tường minh |
| Khởi tạo bean | Tạo instance, inject dependency và chạy lifecycle khi container cần |

Vì vậy, một thư viện có class `@Component` nhưng không nằm trong phạm vi scan và không được import có thể hoàn toàn không xuất hiện trong context.

## 2. Cách đơn giản nhất: import một lớp @Configuration

Thư viện có thể cung cấp một lớp cấu hình công khai:

~~~java
package com.acme.sharedclient.config;

import com.acme.sharedclient.DefaultSharedClient;
import com.acme.sharedclient.SharedClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SharedClientConfiguration {

    @Bean
    SharedClient sharedClient() {
        return new DefaultSharedClient();
    }
}
~~~

Ứng dụng chủ nhập cấu hình này:

~~~java
package com.example.orders;

import com.acme.sharedclient.config.SharedClientConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SharedClientConfiguration.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Khi Spring xử lý `OrdersApplication`, cấu hình `SharedClientConfiguration` được nhập vào cùng application context. Bean `SharedClient` có thể được inject vào service của ứng dụng:

~~~java
@Service
public class OrderSyncService {
    private final SharedClient sharedClient;

    public OrderSyncService(SharedClient sharedClient) {
        this.sharedClient = sharedClient;
    }
}
~~~

Không cần quét package `com.acme.sharedclient`. Spring đã biết chính xác class cấu hình nào cần xử lý và bean nào được khai báo trong đó.

`@Import` cũng có thể nhập nhiều class:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    SharedClientConfiguration.class,
    SharedJsonConfiguration.class,
    SharedRetryConfiguration.class
})
public class SharedIntegrationConfiguration {
}
~~~

Đây là cách phù hợp khi ứng dụng chủ biết rõ module nào cần bật. Các cấu hình được import tham gia vào cùng context; chúng không tạo một container riêng.

## 3. Đóng gói thành annotation @Enable...

Nếu thư viện muốn mang lại trải nghiệm sử dụng đơn giản, có thể tạo annotation công khai dạng `@EnableSharedClient`. Annotation này đóng vai trò một **điểm vào** cho toàn bộ cấu hình module.

### 3.1. Tạo annotation bật tính năng

~~~java
package com.acme.sharedclient;

import com.acme.sharedclient.config.SharedClientConfiguration;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(SharedClientConfiguration.class)
public @interface EnableSharedClient {
}
~~~

Ứng dụng chủ chỉ cần:

~~~java
@SpringBootApplication
@EnableSharedClient
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Annotation `@EnableSharedClient` không tự tạo bean. Nó nhập cấu hình mà thư viện công bố. Cấu hình có thể tiếp tục import các cấu hình con hoặc khai báo các bean liên quan.

### 3.2. Khi nào nên dùng @Enable...?

Mẫu này phù hợp khi:

- Thư viện có một tính năng tùy chọn, ứng dụng chỉ muốn bật khi chủ động khai báo.
- Module cần một API cấu hình công khai ổn định.
- Người dùng muốn biết rõ ứng dụng đang bật tích hợp nào.
- Cấu hình không cần tự động xuất hiện chỉ vì dependency có mặt.

Ví dụ thư viện có thể cung cấp:

~~~java
@EnableSharedClient
@EnablePartnerMessaging
@EnableTenantSupport
~~~

Mỗi annotation bật một nhóm cấu hình riêng. Cách này làm rõ ý định ở lớp ứng dụng và tránh việc một dependency kéo theo nhiều tính năng ngoài mong muốn.

### 3.3. Có thể nhận thuộc tính trong annotation

Annotation bật module đôi khi cần tham số:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(SharedClientConfiguration.class)
public @interface EnableSharedClient {
    String baseUrl() default "";
}
~~~

Các thuộc tính của annotation có thể được đọc từ metadata bởi cấu hình import hoặc một `ImportSelector`. Tuy nhiên, nếu cấu hình có nhiều property, profile và binding phức tạp, `@ConfigurationProperties` thường là lựa chọn dễ mở rộng hơn. Tránh biến annotation thành một bản sao của toàn bộ file cấu hình ứng dụng.

## 4. Chỉ import component cần thiết, không scan cả thư viện

`@Import` có thể nhập trực tiếp class component cụ thể, không nhất thiết phải import một lớp cấu hình chứa `@Bean`:

~~~java
package com.acme.sharedclient;

import org.springframework.stereotype.Component;

@Component
public class SharedTokenProvider {
    public String currentToken() {
        return "token";
    }
}
~~~

Ứng dụng hoặc cấu hình module có thể đăng ký class này bằng:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(SharedTokenProvider.class)
public class SharedClientConfiguration {
}
~~~

Spring đăng ký class được import như một bean candidate. Cách này hữu ích khi chỉ có một vài component công khai cần đưa vào context.

Nếu một component cần nhiều dependency, vẫn có thể inject qua constructor như bình thường. Các dependency đó cũng phải được đăng ký qua cấu hình/import/auto-configuration phù hợp.

### 4.1. Dùng @Bean khi muốn kiểm soát cách tạo object

Thay vì import class implementation, thư viện có thể khai báo bean qua factory method:

~~~java
@Configuration(proxyBeanMethods = false)
public class SharedClientConfiguration {

    @Bean
    SharedClient sharedClient(
            SharedTokenProvider tokenProvider,
            SharedClientProperties properties) {
        return new DefaultSharedClient(
                properties.getBaseUrl(),
                tokenProvider
        );
    }
}
~~~

Phương thức `@Bean` cho phép:

- Chọn implementation cụ thể nhưng chỉ công bố interface.
- Truyền property đã bind và dependency khác vào constructor.
- Đặt tên bean, scope, điều kiện hoặc lifecycle callback.
- Giữ implementation nội bộ không cần mang stereotype công khai.

Khi dùng `@Configuration(proxyBeanMethods = false)`, hãy inject dependency qua tham số phương thức `@Bean` như ví dụ. Không gọi trực tiếp một phương thức factory khác để mong Spring luôn trả lại singleton đã đăng ký; ở lite mode, lời gọi đó là lời gọi Java thông thường.

## 5. Khi thư viện có nhiều component: component scan hẹp

Đôi khi module có nhiều component cùng thuộc một package tính năng. Thay vì import từng class, có thể đặt `@ComponentScan` trong cấu hình module nhưng giới hạn package cụ thể.

~~~java
package com.acme.sharedclient.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.acme.sharedclient.client")
public class SharedClientConfiguration {
}
~~~

Ở đây chỉ package `com.acme.sharedclient.client` và các package con được quét. Các component nội bộ ở `com.acme.sharedclient.internal` không tự động được phát hiện nếu chúng nằm ngoài cây package đó.

### 5.1. Dùng marker class thay cho chuỗi package

Để tránh sai tên package khi refactor, có thể dùng `basePackageClasses`:

~~~java
package com.acme.sharedclient.client;

public interface SharedClientComponentMarker {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = SharedClientComponentMarker.class)
public class SharedClientConfiguration {
}
~~~

Spring dùng package chứa marker làm base package. Cách này an toàn hơn chuỗi literal khi package được đổi tên.

Marker không cần là bean và không cần chứa logic. Nên đặt marker ở đúng package gốc của nhóm component cần quét, không đặt ở package root của toàn bộ thư viện nếu mục tiêu là giới hạn phạm vi.

### 5.2. Khi nào scan hẹp vẫn chưa đủ?

Component scan vẫn phát hiện tất cả stereotype phù hợp trong package và các package con, trừ khi có filter loại trừ. Nếu package chứa nhiều implementation nội bộ hoặc component chỉ dùng trong một số ứng dụng, việc scan hẹp có thể vẫn đăng ký quá nhiều bean.

Trong trường hợp đó, lựa chọn tường minh bằng `@Bean` hoặc `@Import` từng class giúp API thư viện kiểm soát chính xác hơn. Component scan là tiện ích phát hiện theo package; nó không thay thế ranh giới module.

## 6. Dùng includeFilters và excludeFilters khi cần kiểm soát scan

Nếu cần scan một package nhưng chỉ muốn một nhóm component, có thể dùng filter:

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackages = "com.acme.sharedclient",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = {
                        SharedTokenProvider.class,
                        SharedClientMetrics.class
                }
        )
)
public class SharedClientConfiguration {
}
~~~

Với `useDefaultFilters = false`, các filter mặc định cho stereotype không còn được áp dụng; chỉ các filter được khai báo mới quyết định class được include. Ví dụ này chỉ chọn hai class theo kiểu assignable.

Có thể dùng các loại filter khác như annotation, regex, aspectJ hoặc custom filter tùy yêu cầu. Tuy nhiên, nếu chỉ có vài class, `@Import` thường dễ đọc và ít cấu hình hơn.

Không nên mở rộng base package lên namespace quá lớn như `com`, `org` hoặc package root chứa nhiều thư viện. Phạm vi scan càng rộng thì nguy cơ phát hiện component ngoài ý muốn, trùng tên bean và tăng thời gian khởi động càng cao.

## 7. Phân biệt @Import với auto-configuration của Spring Boot

`@Import` phù hợp khi ứng dụng **chủ động chọn** cấu hình. Một starter Spring Boot có thể cung cấp trải nghiệm khác: chỉ cần thêm dependency, Boot tự phát hiện auto-configuration và áp dụng nếu điều kiện phù hợp.

Hai cơ chế có mục tiêu khác nhau:

| Tiêu chí | `@Import` / `@Enable...` | Boot auto-configuration |
|---|---|---|
| Cách kích hoạt | Ứng dụng khai báo annotation/import | Boot khám phá class đã đăng ký trên classpath |
| Mức chủ động | Opt-in rõ ràng | Thường tự áp dụng khi có dependency và điều kiện phù hợp |
| Điều kiện | Có thể kết hợp `@Profile`/`@Conditional...` | Thường dùng nhiều condition theo classpath, property, bean |
| Mục tiêu | Ghép cấu hình module theo ý định ứng dụng | Cung cấp cấu hình mặc định thuận tiện cho starter |
| Khi muốn tắt | Bỏ annotation/import hoặc điều kiện tương ứng | Exclude auto-configuration hoặc làm condition không thỏa |

Một thư viện có thể cung cấp cả hai mô hình, nhưng nên có chủ đích:

- Core library: cung cấp API và các class cần thiết.
- Optional configuration module: cung cấp annotation `@EnableSharedClient` và lớp cấu hình được import.
- Boot starter: tự đăng ký auto-configuration cho ứng dụng muốn trải nghiệm tự động.

Không cần tạo starter auto-configuration nếu module chỉ dùng nội bộ trong một ứng dụng và việc bật bằng `@Import` đã đủ rõ.

## 8. Đăng ký auto-configuration trong Spring Boot 3.x

Với một thư viện starter dành cho Spring Boot 3.x, có thể tạo lớp:

~~~java
package com.acme.sharedclient.autoconfigure;

import com.acme.sharedclient.DefaultSharedClient;
import com.acme.sharedclient.SharedClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(SharedClient.class)
@EnableConfigurationProperties(SharedClientProperties.class)
@ConditionalOnProperty(
        prefix = "acme.shared-client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SharedClient sharedClient(SharedClientProperties properties) {
        return new DefaultSharedClient(properties.getBaseUrl());
    }
}
~~~

Các điều kiện có ý nghĩa:

- `@ConditionalOnClass` chỉ cho phép cấu hình khi class API cần thiết có mặt.
- `@EnableConfigurationProperties` đăng ký lớp property để Spring Boot bind cấu hình.
- `@ConditionalOnProperty` cho phép bật/tắt module bằng cấu hình.
- `@ConditionalOnMissingBean` để ứng dụng thay thế implementation mặc định bằng bean của mình.

`SharedClientProperties` là lớp property do thư viện định nghĩa. Ví dụ:

~~~java
package com.acme.sharedclient.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.shared-client")
public class SharedClientProperties {
    private String baseUrl;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Ứng dụng cấu hình:

~~~yaml
acme:
  shared-client:
    enabled: true
    base-url: https://api.example.test
~~~

### 8.1. Công bố auto-configuration bằng AutoConfiguration.imports

Trong JAR của thư viện, tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.sharedclient.autoconfigure.SharedClientAutoConfiguration
~~~

Spring Boot đọc danh sách này khi xử lý `@EnableAutoConfiguration`. Khi ứng dụng thêm starter vào classpath, cấu hình có thể được khám phá mà ứng dụng không cần component scan package thư viện hay viết `@Import` thủ công.

File này chứa tên đầy đủ của các auto-configuration class, mỗi dòng một class. Không đưa component/service thông thường vào đây như thể đó là danh sách component scan; hãy đăng ký cấu hình tự động, rồi để cấu hình đó khai báo bean hoặc import các thành phần cần thiết.

### 8.2. Vì sao không đặt @ComponentScan ở auto-configuration?

Một auto-configuration nên khai báo các bean nó quản lý qua `@Bean`, `@Import` hoặc một cơ chế có phạm vi rõ ràng. Đặt `@ComponentScan("com.acme.sharedclient")` ở package root của thư viện có thể quét cả cấu hình nội bộ, implementation phụ trợ hoặc component không thuộc tính năng đang bật.

Nếu thật sự cần scan, giới hạn base package và filter trong module cụ thể. Nhưng với starter công khai, khai báo bean tường minh thường giúp hành vi ổn định hơn và giảm rủi ro khi thư viện bổ sung class mới.

## 9. Khác biệt metadata giữa các dòng Spring Boot

Cơ chế đăng ký auto-configuration thay đổi theo thế hệ Spring Boot:

| Dòng Spring Boot | Cách công bố auto-configuration thường dùng |
|---|---|
| Boot 3.x | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Boot 2.7 | Hỗ trợ cơ chế `AutoConfiguration.imports`; cũng có thể gặp cơ chế cũ trong thư viện tương thích |
| Boot 2.6 trở xuống | Thường khai báo trong `META-INF/spring.factories` dưới key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` |

Ví dụ metadata legacy cho Boot 2.x cũ:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.sharedclient.autoconfigure.SharedClientAutoConfiguration
~~~

Đặt nội dung này trong `META-INF/spring.factories` của thư viện. Khi hỗ trợ nhiều dòng Boot, cần kiểm tra ma trận tương thích và cách đăng ký được phiên bản mục tiêu hỗ trợ; không giả định file metadata của Boot 3 sẽ thay thế mọi cơ chế legacy trong tất cả bản Boot 2.

Ngoài ra, Boot 3 sử dụng `@AutoConfiguration` cho auto-configuration class. Với Boot 2, thường dùng `@Configuration` cùng các annotation ordering/condition tương ứng. Hãy biên dịch thư viện với đúng baseline Spring Boot mà nó công bố hỗ trợ.

## 10. Dùng ImportSelector khi cần chọn cấu hình theo metadata

`ImportSelector` cho phép chọn danh sách class cần import tại thời điểm xử lý cấu hình:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class SharedClientImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
                "com.acme.sharedclient.config.SharedClientConfiguration",
                "com.acme.sharedclient.config.SharedJsonConfiguration"
        };
    }
}
~~~

Đưa selector vào annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(SharedClientImportSelector.class)
public @interface EnableSharedClient {
}
~~~

Selector có ích khi danh sách import cần thay đổi theo annotation metadata hoặc lựa chọn module. Ví dụ annotation có thuộc tính `mode` để chọn cấu hình HTTP client hoặc mock client. Khi cần đọc thuộc tính annotation, có thể dùng `AnnotationMetadata` và API Spring tương ứng để lấy attribute values.

Không nên dùng `ImportSelector` chỉ để trả về một class cố định. Với trường hợp đó, `@Import(SharedClientConfiguration.class)` ngắn hơn và dễ theo dõi hơn.

### DeferredImportSelector

`DeferredImportSelector` là biến thể trì hoãn việc lựa chọn import đến giai đoạn sau trong quá trình xử lý cấu hình. Spring Boot sử dụng cơ chế này trong quy trình auto-configuration để phối hợp với điều kiện và ordering.

Đây là extension point nâng cao. Chỉ dùng khi thư viện thực sự cần lựa chọn import ở giai đoạn deferred; không cần triển khai nó cho một module cấu hình thông thường.

## 11. ImportBeanDefinitionRegistrar dành cho đăng ký bean động

Khi cần tạo bean definitions dựa trên metadata, tên interface hoặc quy ước riêng, có thể triển khai `ImportBeanDefinitionRegistrar`:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class SharedClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(DefaultSharedClient.class);

        registry.registerBeanDefinition("sharedClient", definition);
    }
}
~~~

Đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(SharedClientRegistrar.class)
public class SharedClientModuleConfiguration {
}
~~~

Registrar làm việc ở cấp bean definition registry, nên có thể kiểm soát tên và metadata của bean. Nó hữu ích cho thư viện tạo nhiều client/proxy dựa trên annotation hoặc cấu hình khai báo.

Nhưng cần kiểm tra tên bean đã tồn tại, scope, dependency và điều kiện trước khi đăng ký. Nếu mục tiêu chỉ là cung cấp một bean mặc định, `@Bean` cùng `@ConditionalOnMissingBean` đơn giản và dễ bảo trì hơn.

## 12. Để ứng dụng thay thế bean mặc định

Một thư viện dùng chung nên tránh ép mọi ứng dụng phải dùng implementation nội bộ của nó. Hãy công bố interface và cho phép ứng dụng cung cấp bean thay thế:

~~~java
@AutoConfiguration
@ConditionalOnClass(SharedClient.class)
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SharedClient.class)
    SharedClient sharedClient(SharedClientProperties properties) {
        return new DefaultSharedClient(properties.getBaseUrl());
    }
}
~~~

Ứng dụng có thể tự khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomClientConfiguration {

    @Bean
    SharedClient sharedClient() {
        return new CustomSharedClient();
    }
}
~~~

Khi bean tùy chỉnh được đăng ký trước khi condition của auto-configuration được đánh giá, `@ConditionalOnMissingBean` cho phép cấu hình mặc định lùi lại. Điều này là một phần quan trọng trong thiết kế starter: cung cấp mặc định hữu ích nhưng vẫn tôn trọng cấu hình của ứng dụng.

Thứ tự xử lý auto-configuration và vị trí cấu hình người dùng có thể quan trọng với các điều kiện phụ thuộc bean. Boot sắp xếp auto-configuration theo cơ chế của nó để cấu hình ứng dụng thường có cơ hội được xử lý trước. Không nên dựa vào việc quét package thư viện để thay thế condition.

## 13. Tránh xung đột bean khi nhiều module dùng chung

Nếu nhiều thư viện cùng quét package rộng hoặc đăng ký bean với tên mặc định trùng nhau, context có thể gặp lỗi bean definition conflict hoặc ứng dụng không rõ implementation nào được inject.

Một số nguyên tắc:

- Dùng tên bean có ý nghĩa và namespace theo module khi cần bean name ổn định.
- Công bố interface, giữ implementation nội bộ package-private hoặc trong package internal nếu phù hợp.
- Dùng `@ConditionalOnMissingBean` cho bean mặc định có chủ đích.
- Dùng `@Qualifier` hoặc `@Primary` khi có nhiều implementation hợp lệ.
- Tránh component scan toàn bộ package root của thư viện.
- Không bật bean definition overriding chỉ để che giấu cấu hình trùng lặp.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(name = "sharedClient")
SharedClient sharedClient(SharedClientProperties properties) {
    return new DefaultSharedClient(properties.getBaseUrl());
}
~~~

Điều kiện theo tên hữu ích khi hợp đồng cấu hình dựa trên một bean name cụ thể. Nếu mục tiêu là cho phép thay thế bất kỳ implementation nào của interface, điều kiện theo kiểu `SharedClient.class` thường phù hợp hơn.

## 14. Tách core library, configuration module và starter

Với thư viện lớn hơn, có thể chia artifact theo vai trò:

~~~text
acme-shared-client-core
  ├── SharedClient interface
  ├── DTOs / exceptions
  └── API không phụ thuộc Spring Boot

acme-shared-client-spring
  ├── @EnableSharedClient
  ├── SharedClientConfiguration
  └── Spring integration beans

acme-shared-client-spring-boot-starter
  ├── dependency tới core và spring integration
  └── SharedClientAutoConfiguration + metadata
~~~

Ứng dụng có thể chọn:

- Chỉ dùng core API mà không cần Spring.
- Dùng integration module và bật bằng `@EnableSharedClient`.
- Dùng starter để auto-configuration tự hoạt động theo điều kiện.

Cách phân chia này tránh buộc mọi người dùng thư viện phải nhận tất cả dependency và hành vi tự động. Nó cũng giúp test và nâng cấp từng phần độc lập hơn.

Không nhất thiết dự án nhỏ nào cũng cần ba artifact. Chỉ tách module khi ranh giới dependency, khả năng tái sử dụng hoặc yêu cầu tương thích thực sự có ý nghĩa.

## 15. Kiểm thử cấu hình được import

Với cấu hình opt-in dùng `@Import`, có thể kiểm thử một context nhỏ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SharedClientConfigurationTest {

    @Test
    void registersSharedClient() {
        try (var context = new AnnotationConfigApplicationContext(
                SharedClientConfiguration.class)) {

            assertThat(context.getBean(SharedClient.class)).isNotNull();
        }
    }
}
~~~

Nếu cấu hình cần property hoặc dependency khác, hãy đăng ký chúng trong test context hoặc dùng context runner phù hợp.

Với auto-configuration của Boot, `ApplicationContextRunner` cho phép kiểm tra các điều kiện:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class SharedClientAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    SharedClientAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "acme.shared-client.enabled=true",
                        "acme.shared-client.base-url=https://example.test")
                .run(context ->
                        assertThat(context).hasSingleBean(SharedClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        contextRunner
                .withBean(SharedClient.class, CustomSharedClient::new)
                .run(context ->
                        assertThat(context).hasSingleBean(SharedClient.class));
    }
}
~~~

Ví dụ dùng các class `SharedClientProperties`, `CustomSharedClient` và constructor tương ứng do thư viện/test định nghĩa. Trong test thứ hai, nên xác nhận bean trả về là implementation tùy chỉnh, không chỉ kiểm tra số lượng bean.

Các kịch bản nên kiểm tra:

1. Dependency/class cần thiết có mặt.
2. Property bật và tắt.
3. Property bị thiếu có đúng default không.
4. Ứng dụng cung cấp bean thay thế thì auto-configuration có back off không.
5. Cấu hình không được bật thì bean tùy chọn có thực sự vắng mặt không.
6. Các component nội bộ không được đăng ký ngoài ý muốn.

Với component scan hẹp, có thể kiểm tra bean name/type trong context để xác nhận chỉ nhóm component mong muốn được phát hiện.

## 16. Chẩn đoán khi bean thư viện không xuất hiện

Nếu service của ứng dụng báo không tìm thấy bean từ thư viện, kiểm tra theo nguồn đăng ký:

| Cách thư viện dự kiến đăng ký | Điều cần kiểm tra |
|---|---|
| `@Import` | Class cấu hình có được import không? Có điều kiện/profile nào loại nó không? |
| `@Enable...` | Ứng dụng có gắn annotation enable lên configuration class được Spring xử lý không? |
| `@ComponentScan` | Base package và filter có bao phủ class cần thiết không? |
| Boot auto-configuration | Metadata imports có nằm trong JAR không? Auto-configuration có được khám phá và condition có match không? |
| `ImportSelector` | Selector có trả về tên class đúng và class có trên classpath không? |
| `ImportBeanDefinitionRegistrar` | Registrar có được import và có đăng ký đúng bean name/type không? |

### Xem dependency tree

Một class có thể không được tải vì JAR thư viện chưa nằm trên runtime classpath. Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Các lệnh trên chỉ giúp xác nhận dependency đã được phân giải. Dependency có mặt vẫn chưa chứng minh bean đã được đăng ký.

### Xem Condition Evaluation Report

Với Spring Boot, có thể bật `debug=true` hoặc chạy ứng dụng với `--debug` để xem điều kiện auto-configuration. Báo cáo cho biết cấu hình nào match, không match hoặc bị exclude.

Nếu cấu hình được import tường minh nhưng bean vẫn thiếu, kiểm tra condition/profile trên cấu hình hoặc phương thức `@Bean`, cũng như lỗi khi tạo dependency.

### Quan sát bean thực tế

Trong môi trường phát triển, có thể kiểm tra `ApplicationContext` bằng `getBeanNamesForType(...)` hoặc dùng Actuator endpoint `beans` nếu endpoint đã được bật và bảo vệ phù hợp. Không nên công khai endpoint chẩn đoán này ra bên ngoài nếu chưa kiểm soát quyền truy cập.

## 17. Các cách làm nên tránh

**Quét package root quá rộng:**

~~~java
@ComponentScan("com.acme")
~~~

Điều này có thể phát hiện component của nhiều module hoặc thư viện khác cùng namespace. Hãy giới hạn package tính năng hoặc import cấu hình công khai.

**Để mọi implementation nội bộ mang @Component rồi hy vọng ứng dụng tự tìm thấy:** việc đó làm API thư viện phụ thuộc vào phạm vi scan của từng ứng dụng. Tạo một cấu hình module để đăng ký bean có chủ đích.

**Dùng auto-configuration cho tính năng mà ứng dụng luôn muốn bật/tắt thủ công:** nếu module cần opt-in rõ ràng, annotation `@Enable...` và `@Import` thường diễn đạt ý định tốt hơn.

**Dùng @ImportSelector hoặc registrar cho một danh sách cố định:** extension point nâng cao làm tăng độ phức tạp. Dùng `@Import` trực tiếp khi biết class cần nạp.

**Đăng ký mọi implementation bằng bean name mặc định:** nhiều thư viện có thể có class tên ngắn giống nhau. Công bố interface và đặt tên rõ khi tên là một phần của hợp đồng.

**Bật bean overriding để che giấu xung đột:** hãy xác định bean definition nào trùng, vì sao được đăng ký hai lần và module nào sở hữu nó.

## 18. Cách chọn cơ chế phù hợp

| Tình huống | Cách nên chọn |
|---|---|
| Ứng dụng muốn bật một cấu hình cụ thể | `@Import(SharedConfiguration.class)` |
| Muốn API bật module dễ dùng | Annotation `@EnableSharedFeature` kết hợp `@Import` |
| Thư viện có vài component cần đăng ký | `@Import` từng class hoặc khai báo qua `@Bean` |
| Module có nhiều component cùng package hẹp | `@ComponentScan` với base package/marker cụ thể |
| Starter muốn tự cấu hình khi dependency có mặt | Boot auto-configuration và metadata imports |
| Cần chọn class cấu hình động theo metadata | `ImportSelector` hoặc `DeferredImportSelector` |
| Cần đăng ký bean definitions động theo quy ước | `ImportBeanDefinitionRegistrar` |
| Cần nạp cấu hình XML legacy | `@ImportResource` |

Một thiết kế thư viện dùng chung thường có một **cấu hình công khai** làm entry point. Cấu hình đó có thể khai báo bean qua `@Bean`, import một số component cần thiết và bind property qua `@ConfigurationProperties`. Ứng dụng chủ chỉ cần import entry point hoặc bật annotation `@Enable...`. Nếu thư viện được đóng gói thành starter, Boot auto-configuration có thể tự phát hiện cấu hình và áp dụng điều kiện.

Điểm quan trọng là đăng ký bean theo **ranh giới tính năng**: chỉ những bean thuộc module được bật mới xuất hiện trong context. Việc này giúp tránh quét toàn bộ package thư viện, giảm xung đột và giữ cho hành vi cấu hình có thể dự đoán khi ứng dụng thêm nhiều module dùng chung.
