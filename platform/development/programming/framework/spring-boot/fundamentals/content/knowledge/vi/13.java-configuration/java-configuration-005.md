# @Import và chia cấu hình theo trách nhiệm

Khi ứng dụng Spring Boot lớn dần, một lớp cấu hình duy nhất có thể chứa quá nhiều thứ: khai báo bean dùng chung, tích hợp database, cấu hình HTTP client, bảo mật, xử lý message và các tính năng riêng của từng module. Một lớp như vậy khó đọc, khó kiểm thử độc lập và dễ tạo ra những thay đổi ngoài ý muốn khi thêm một tính năng.

Spring Framework cung cấp annotation **`@Import`** để ghép các lớp cấu hình thành một application context. Ta có thể tách cấu hình theo trách nhiệm vào những class nhỏ, sau đó khai báo rõ lớp nào cần nạp lớp nào. Cách tổ chức này giữ được tính tường minh của cấu hình Java, đồng thời tránh phải gom tất cả bean vào một file.

Ý tưởng chính:

~~~text
                 ApplicationConfiguration
                           |
                 @Import các cấu hình
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   DataConfiguration  WebConfiguration  SecurityConfiguration
          |                |                |
       DataSource       Web client       Security rules
       Repositories     MVC/WebFlux      Filter chains
          |
          v
   Các bean được đăng ký trong cùng ApplicationContext
~~~

`@Import` không tạo một container riêng cho mỗi lớp cấu hình. Các cấu hình được import tham gia vào quá trình xây dựng **cùng application context**, nên bean ở cấu hình này có thể được inject vào bean ở cấu hình khác nếu các điều kiện đăng ký phù hợp.

## 1. Vấn đề khi dồn mọi cấu hình vào một lớp

Một lớp cấu hình có thể bắt đầu đơn giản:

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    RestClient externalRestClient() {
        return RestClient.builder().build();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }
}
~~~

Khi số bean tăng lên, lớp này phải biết quá nhiều chi tiết của nhiều khu vực. Một thay đổi ở cấu hình tích hợp ngoài có thể làm người đọc phải rà lại cả phần bảo mật và nghiệp vụ đơn hàng. Các bean cũng khó được nhóm theo điều kiện hoặc profile riêng.

Ta có thể chia theo trách nhiệm:

~~~text
config/
├── ApplicationConfiguration.java
├── TimeConfiguration.java
├── SecurityConfiguration.java
├── ExternalClientConfiguration.java
└── OrderConfiguration.java
~~~

Mỗi class mô tả một nhóm cấu hình có liên quan. Lớp gốc chỉ có nhiệm vụ kết hợp các nhóm cần thiết:

~~~java
@Configuration
@Import({
    TimeConfiguration.class,
    SecurityConfiguration.class,
    ExternalClientConfiguration.class,
    OrderConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

Nhờ đó, mỗi nhóm cấu hình có thể được đọc và kiểm thử tập trung. Tuy nhiên, không nên tách mỗi bean thành một class chỉ để giảm số dòng; một lớp cấu hình nên đại diện cho **một trách nhiệm hoặc một ranh giới cấu hình có ý nghĩa**.

## 2. Cú pháp cơ bản của @Import

`@Import` thuộc package `org.springframework.context.annotation`:

~~~java
import org.springframework.context.annotation.Import;
~~~

Annotation nhận một hoặc nhiều class:

~~~java
@Configuration
@Import({
    DatabaseConfiguration.class,
    MessagingConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

Khi Spring xử lý `ApplicationConfiguration`, nó cũng xử lý các cấu hình được chỉ định trong `@Import`. Những lớp cấu hình này có thể tiếp tục import cấu hình khác, tạo thành một đồ thị cấu hình:

~~~text
ApplicationConfiguration
  ├── DatabaseConfiguration
  │     └── JpaConfiguration
  └── MessagingConfiguration
        └── RetryConfiguration
~~~

Ta không cần đặt các lớp được import trong cùng package với lớp gốc. Chúng cần nằm trên classpath và được chỉ định đúng class. Việc import là **tường minh theo class**, không phải tự động quét tất cả package con.

### 2.1. Dùng @Import trực tiếp trên lớp khởi động Spring Boot

Vì `@SpringBootApplication` đã là một nguồn cấu hình, ta có thể đặt `@Import` ngay trên lớp main:

~~~java
package com.example.orders;

import com.example.orders.config.PersistenceConfiguration;
import com.example.orders.config.SecurityConfiguration;
import com.example.orders.config.TimeConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import({
    PersistenceConfiguration.class,
    SecurityConfiguration.class,
    TimeConfiguration.class
})
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Cách này phù hợp khi danh sách cấu hình bổ sung nhỏ và lớp main vẫn dễ đọc. Nếu danh sách import dài, có thể tạo một lớp tổng hợp như `OrdersModuleConfiguration` để giữ lớp main gọn.

### 2.2. Lớp được import cần khai báo cấu hình như thế nào?

Thông thường, lớp được import là một lớp `@Configuration`:

~~~java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

`@Configuration` đánh dấu class là nguồn cấu hình Spring. Các phương thức `@Bean` bên trong được xử lý để đăng ký bean definition.

`@Import` cũng có thể nhập các thành phần thông thường và hỗ trợ những extension point như `ImportSelector` hoặc `ImportBeanDefinitionRegistrar`. Với cấu hình ứng dụng thông thường, ưu tiên import một class `@Configuration` để ý định rõ ràng và dễ hiểu.

## 3. Ví dụ chia cấu hình theo trách nhiệm

Giả sử ứng dụng quản lý đơn hàng có ba nhóm hạ tầng: thời gian hệ thống, HTTP client và chính sách đơn hàng.

### 3.1. Cấu hình thời gian

~~~java
package com.example.orders.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Các service cần thời gian có thể inject `Clock`. Việc dùng bean giúp kiểm thử bằng một clock cố định mà không phụ thuộc trực tiếp vào `Instant.now()` trong logic nghiệp vụ.

### 3.2. Cấu hình HTTP client

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient() {
        return RestClient.builder()
                .baseUrl("https://partner.example")
                .build();
    }
}
~~~

Trong dự án thực tế, base URL nên lấy từ externalized configuration, chẳng hạn `@ConfigurationProperties`, thay vì hard-code địa chỉ môi trường. Ví dụ chỉ tập trung minh họa vị trí khai báo bean.

### 3.3. Cấu hình chính sách đơn hàng

~~~java
package com.example.orders.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    OrderPolicy orderPolicy(Clock applicationClock) {
        return new OrderPolicy(applicationClock);
    }
}
~~~

Tham số `applicationClock` được Spring phân giải từ bean do `TimeConfiguration` cung cấp. Đây là cách thể hiện dependency giữa các cấu hình và bean: không cần gọi trực tiếp phương thức factory của lớp cấu hình khác.

### 3.4. Kết hợp các nhóm cấu hình

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    TimeConfiguration.class,
    PartnerClientConfiguration.class,
    OrderConfiguration.class
})
public class OrdersModuleConfiguration {
}
~~~

Và lớp main:

~~~java
package com.example.orders;

import com.example.orders.config.OrdersModuleConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(OrdersModuleConfiguration.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Khi khởi động, các cấu hình đã import được xử lý trong application context. Bean `applicationClock`, `partnerRestClient` và `orderPolicy` có thể được các bean khác inject nếu không có điều kiện hoặc cấu hình loại trừ chúng.

Trong ví dụ, các class `OrderPolicy` và các kiểu liên quan được giả định là những class do ứng dụng định nghĩa. Các đoạn cấu hình minh họa có thể được đặt trong các file riêng theo package tương ứng.

## 4. @Import khác @ComponentScan như thế nào?

Hai annotation đều có thể góp phần làm bean xuất hiện trong context, nhưng cách chọn class khác nhau.

| Tiêu chí | `@ComponentScan` | `@Import` |
|---|---|---|
| Cách chọn thành phần | Tìm class có stereotype trong package và package con theo phạm vi scan | Chỉ định trực tiếp class hoặc cơ chế chọn class |
| Phạm vi | Theo package, filter và scan configuration | Theo danh sách class/selector |
| Phù hợp với | Tự động phát hiện controller, service, repository và component | Kết hợp các module cấu hình đã biết |
| Có quét package con không? | Có, theo base package | Không; import class không đồng nghĩa scan package của class đó |
| Tính tường minh | Phạm vi package quyết định nhiều class được phát hiện | Danh sách import cho thấy module cấu hình nào được ghép |

Ví dụ:

~~~java
@Configuration
@ComponentScan("com.example.orders.feature")
public class FeatureScanConfiguration {
}
~~~

Spring sẽ quét package `com.example.orders.feature` và các package con để tìm component phù hợp.

Trong khi đó:

~~~java
@Configuration
@Import(FeatureConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Spring xử lý class `FeatureConfiguration` đã chỉ định. Nó không vì thế mà tự quét mọi `@Service` hoặc `@Component` nằm cạnh class đó.

Hai cơ chế có thể kết hợp: một cấu hình import một module configuration, còn module configuration đó tự khai báo component scan có giới hạn nếu đó là thiết kế của module. Hãy chọn rõ ranh giới để tránh quét lặp hoặc vô tình đăng ký component ngoài ý muốn.

## 5. @Import không phải @ImportResource

Spring hỗ trợ nhiều cách ghép cấu hình:

- `@Import`: ghép cấu hình Java hoặc nhập thành phần qua selector/registrar.
- `@ImportResource`: nạp định nghĩa bean từ tài nguyên cấu hình XML.
- `@ComponentScan`: tự động phát hiện component theo package.

Ví dụ import XML:

~~~java
@Configuration
@ImportResource("classpath:/legacy/legacy-beans.xml")
public class LegacyIntegrationConfiguration {
}
~~~

`@ImportResource` phù hợp khi tích hợp một hệ thống cũ còn XML bean definitions. Với cấu hình Java mới, `@Import` thường là cách trực tiếp và dễ refactor hơn.

Không dùng `@ImportResource` chỉ vì tên annotation có chữ “Import”; nó xử lý loại tài nguyên khác với `@Import`.

## 6. Tách cấu hình theo trách nhiệm và ranh giới module

Chia cấu hình nên phản ánh ranh giới kỹ thuật hoặc nghiệp vụ có ý nghĩa. Ví dụ:

~~~text
com.example.orders
├── OrdersApplication.java
├── config
│   ├── OrdersModuleConfiguration.java
│   ├── PersistenceConfiguration.java
│   ├── PartnerClientConfiguration.java
│   └── SecurityConfiguration.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   └── OrderRepository.java
└── customer
    ├── CustomerController.java
    ├── CustomerService.java
    └── CustomerRepository.java
~~~

Một số ranh giới có thể cân nhắc:

| Nhóm cấu hình | Nội dung thường thuộc về |
|---|---|
| Persistence | Data source, entity manager, repository scanning, transaction manager khi cần cấu hình riêng |
| External clients | HTTP client, message client, timeout/retry policy |
| Security | Filter chain, authentication provider, method security |
| Serialization | JSON mapper, message converter hoặc serializer đặc thù |
| Scheduling | Scheduler, task executor và cấu hình lịch chạy |
| Feature/module | Bean chỉ phục vụ một tính năng hoặc một module nghiệp vụ |

Không phải tất cả nhóm đều cần lớp cấu hình riêng. Nếu Spring Boot đã auto-configure đúng và ứng dụng không cần tùy chỉnh, không cần tạo một lớp cấu hình chỉ để lặp lại cấu hình mặc định.

### 6.1. Module tự mô tả cấu hình cần thiết

Một module có thể cung cấp một lớp cấu hình tổng hợp:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    OrderDomainConfiguration.class,
    OrderPersistenceConfiguration.class,
    OrderIntegrationConfiguration.class
})
public class OrderModuleConfiguration {
}
~~~

Ứng dụng chủ có thể import module này:

~~~java
@SpringBootApplication
@Import(OrderModuleConfiguration.class)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Nhờ đó, ứng dụng biết cách bật module thông qua một entry point cấu hình rõ ràng. Module cũng có thể tách các chi tiết nội bộ thành những class cấu hình nhỏ hơn mà ứng dụng chủ không cần import từng class.

Nếu module là một thư viện dùng lại cho nhiều ứng dụng, cần xác định API cấu hình công khai của module. Đừng buộc ứng dụng chủ phải import các class nội bộ mà module có thể thay đổi tùy ý.

## 7. @Import và @Bean: tránh gọi nhầm phương thức factory

Một điểm cần hiểu khi chia cấu hình là cách Spring xử lý lời gọi giữa các phương thức `@Bean`.

### 7.1. Full @Configuration mode

Mặc định, `@Configuration` có `proxyBeanMethods = true`. Spring tạo cơ chế proxy/subclass để khi một phương thức `@Bean` trong cùng lớp cấu hình gọi một phương thức `@Bean` khác, lời gọi được điều phối qua container nhằm trả về bean được quản lý thay vì tạo object mới ngoài container.

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(applicationClock());
    }
}
~~~

Trong full configuration mode, lời gọi `applicationClock()` từ `orderPolicy()` được proxy xử lý như một yêu cầu bean, nên nhận bean `Clock` đã đăng ký. Đây là behavior đặc biệt của cấu hình được proxy, không phải semantics của một lời gọi Java thông thường.

### 7.2. Lite mode với proxyBeanMethods = false

Nếu đặt:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(applicationClock());
    }
}
~~~

thì lời gọi `applicationClock()` bên trong `orderPolicy()` là **lời gọi Java thông thường**. Nó có thể tạo một `Clock` khác, thay vì lấy bean đã đăng ký từ context. Điều này có thể làm sai kỳ vọng về identity, scope hoặc lifecycle.

Cách viết an toàn và rõ ràng hơn:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy(Clock applicationClock) {
        return new OrderPolicy(applicationClock);
    }
}
~~~

Spring tự phân giải tham số `Clock applicationClock` và truyền bean phù hợp vào phương thức factory. Cách này hoạt động rõ ràng trong cả full và lite configuration mode, đồng thời thể hiện dependency qua chữ ký phương thức.

Khi tách cấu hình thành nhiều class và import chúng, **ưu tiên method parameter injection** giữa các bean thay vì gọi trực tiếp phương thức `@Bean` của class khác.

## 8. Kết hợp @Import với profile và điều kiện

Không phải module cấu hình nào cũng được nạp trong mọi môi trường. Có thể gắn điều kiện vào class cấu hình được import.

### 8.1. @Profile

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("development")
public class DevelopmentToolsConfiguration {

    @Bean
    DemoDataLoader demoDataLoader() {
        return new DemoDataLoader();
    }
}
~~~

Ứng dụng có thể import class này:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(DevelopmentToolsConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Nếu profile `development` không active, cấu hình đó không đóng góp bean của nó vào context. Nếu active, bean phù hợp được đăng ký.

### 8.2. Điều kiện của Spring Boot

Với ứng dụng Boot, có thể dùng `@ConditionalOnProperty` để bật module theo cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

Trong `application.yml`:

~~~yaml
feature:
  audit:
    enabled: true
~~~

Điều kiện được đánh giá trong quá trình xây dựng context. Nếu property không thỏa, bean `auditPublisher` không được đăng ký từ cấu hình đó.

### 8.3. Conditional không thay thế ranh giới import

`@Import` quyết định cấu hình nào được đưa vào quá trình xử lý; `@Profile` hoặc `@Conditional...` quyết định cấu hình/bean có thỏa điều kiện để được đăng ký hay không. Hai cơ chế bổ sung nhau:

~~~text
ApplicationConfiguration
       |
       +-- @Import(AuditConfiguration)
                     |
                     v
          Đánh giá @ConditionalOnProperty
                /             \
              Đúng             Sai
               |                |
               v                v
          Đăng ký bean      Bỏ qua bean
~~~

Không nên dùng import tường minh như một cách bỏ qua các điều kiện cấu hình; điều kiện vẫn có ý nghĩa trong quá trình xử lý.

## 9. ImportSelector và DeferredImportSelector

Khi danh sách cấu hình cần import phụ thuộc vào metadata hoặc một quyết định động, Spring cung cấp `ImportSelector`:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
                "com.example.storage.JpaStorageConfiguration"
        };
    }
}
~~~

Sử dụng selector:

~~~java
@Configuration
@Import(StorageImportSelector.class)
public class StorageModuleConfiguration {
}
~~~

Selector trả về tên class cần import. Trong ví dụ, nó luôn chọn cấu hình JPA; một implementation thực tế có thể đọc annotation metadata của class đang import hoặc quyết định theo một cơ chế phù hợp.

`DeferredImportSelector` là biến thể trì hoãn việc chọn import đến giai đoạn sau trong quá trình phân tích cấu hình. Nó được sử dụng trong các cơ chế auto-configuration của Spring Boot, nơi thứ tự xử lý và điều kiện của các cấu hình quan trọng.

Không cần tự viết selector chỉ để thay một danh sách import cố định. Với vài cấu hình đã biết, `@Import({A.class, B.class})` đơn giản và dễ đọc hơn.

## 10. ImportBeanDefinitionRegistrar dùng khi nào?

`ImportBeanDefinitionRegistrar` là extension point thấp hơn, cho phép đăng ký bean definition trực tiếp vào registry trong giai đoạn xử lý cấu hình:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class ClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(GeneratedClient.class);

        registry.registerBeanDefinition("generatedClient", definition);
    }
}
~~~

Đăng ký registrar:

~~~java
@Configuration
@Import(ClientRegistrar.class)
public class ClientModuleConfiguration {
}
~~~

Ví dụ minh họa cách đăng ký một bean definition theo tên. Trong thực tế, registrar thường dùng khi thư viện cần tạo nhiều bean theo metadata, annotation, interface hoặc quy ước riêng. Phải kiểm tra tên bean đã tồn tại và các điều kiện registry để tránh xung đột.

`ImportBeanDefinitionRegistrar` mạnh hơn khai báo `@Bean` thông thường, nhưng cũng làm cấu hình phức tạp hơn. Chỉ dùng khi việc đăng ký động ở cấp bean definition thực sự cần thiết; với cấu hình ứng dụng, `@Configuration` + `@Bean` + `@Import` thường đủ.

## 11. @Import và auto-configuration của Spring Boot

Spring Boot sử dụng cơ chế import để ghép các cấu hình tự động. Các thư viện có thể công bố danh sách auto-configuration class trong tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Khi `@EnableAutoConfiguration` (được bao gồm trong `@SpringBootApplication`) hoạt động, Boot tìm các cấu hình được đăng ký theo cơ chế của nó, sau đó đánh giá các điều kiện như:

- `@ConditionalOnClass`: class cần thiết có trên classpath.
- `@ConditionalOnMissingBean`: ứng dụng chưa cung cấp bean tương ứng.
- `@ConditionalOnProperty`: property phù hợp.
- `@ConditionalOnWebApplication`: loại ứng dụng web phù hợp.

Đây là cách starter và thư viện tích hợp cung cấp cấu hình mặc định có điều kiện. **Không đồng nhất việc import cấu hình ứng dụng bằng `@Import` với cơ chế khám phá auto-configuration của Boot**: hai cơ chế có liên quan ở nền tảng xử lý configuration class nhưng mục tiêu và quy ước đăng ký khác nhau.

Nếu chỉ muốn ghép `SecurityConfiguration` do ứng dụng viết, dùng `@Import(SecurityConfiguration.class)` là đủ. Không cần tạo file `AutoConfiguration.imports` cho một cấu hình nội bộ chỉ được dùng bởi một ứng dụng.

## 12. Tổ chức thứ tự và quan hệ phụ thuộc giữa các cấu hình

Thứ tự liệt kê class trong `@Import` không nên được dùng như một cơ chế điều phối vòng đời bean. Spring xử lý cấu hình theo quy trình phân tích và đăng ký bean definition; thời điểm khởi tạo instance còn phụ thuộc dependency, lazy/eager initialization và lifecycle.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    DatabaseConfiguration.class,
    OrderConfiguration.class
})
class ApplicationConfiguration {
}
~~~

Không nên giả định chỉ vì `DatabaseConfiguration.class` đứng trước, mọi bean database sẽ được khởi tạo trước tất cả bean trong `OrderConfiguration`. Nếu `OrderPolicy` cần `DataSource` hoặc một repository, hãy thể hiện dependency đó trong phương thức `@Bean` hoặc constructor của bean.

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

Spring sẽ phân giải dependency và đảm bảo bean cần thiết được cung cấp theo đồ thị phụ thuộc. Nếu thật sự có một yêu cầu thứ tự khởi tạo đặc biệt không thể diễn đạt bằng dependency, xem xét cơ chế lifecycle phù hợp như `@DependsOn`, nhưng không dùng nó để thay thế dependency injection.

### Tránh vòng phụ thuộc giữa cấu hình

Nếu `AConfiguration` import `BConfiguration` và `BConfiguration` lại import `AConfiguration`, cấu trúc trở nên khó hiểu và có thể gây vấn đề khi phân tích cấu hình. Tốt hơn hãy xác định một cấu hình cấp cao hơn làm composition root:

~~~text
ApplicationConfiguration
  ├── AConfiguration
  └── BConfiguration
~~~

Nếu hai module thật sự cần dùng chung bean, chuyển bean đó vào một cấu hình nền tảng hoặc module dùng chung có ranh giới rõ ràng, rồi để hai module phụ thuộc vào abstraction chung.

## 13. Kiểm thử cấu hình đã import

Vì các cấu hình import được xử lý trong cùng context, có thể kiểm thử composition root bằng Spring test hoặc một context nhỏ.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class OrdersModuleConfigurationTest {

    @Test
    void importsModuleBeans() {
        try (var context = new AnnotationConfigApplicationContext(
                OrdersModuleConfiguration.class)) {

            assertThat(context.getBean(Clock.class)).isNotNull();
            assertThat(context.getBean(OrderPolicy.class)).isNotNull();
        }
    }
}
~~~

Test này giả định các cấu hình đã khai báo đúng các bean và mọi dependency cần thiết đều có thể được tạo. `AnnotationConfigApplicationContext` giúp kiểm thử cấu hình Java mà không cần khởi chạy toàn bộ web server.

Với một ứng dụng Boot, có thể dùng `@SpringBootTest` để xác nhận composition root tích hợp với auto-configuration và các thành phần khác:

~~~java
@SpringBootTest
class OrdersApplicationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void moduleConfigurationIsLoaded() {
        assertThat(context.getBean(Clock.class)).isNotNull();
    }
}
~~~

Trong test thực tế, cần dùng assertion phù hợp và bảo đảm cấu hình database, security, external client không phụ thuộc môi trường ngoài ngoài ý muốn. Không nên khởi động kết nối production chỉ để kiểm tra rằng một class cấu hình đã được import.

### Kiểm tra cấu hình theo điều kiện

Nếu cấu hình có `@Profile` hoặc `@ConditionalOnProperty`, nên có test cho cả nhánh bật và tắt:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Profile bật | Các bean thuộc cấu hình được đăng ký |
| Profile tắt | Các bean tùy chọn không xuất hiện |
| Property bật | Tính năng được kích hoạt |
| Property tắt/thiếu | Tính năng được bỏ qua theo semantics đã khai báo |
| Bean tùy chỉnh đã tồn tại | Auto-configuration hoặc cấu hình mặc định có back off đúng như thiết kế |

## 14. Các lỗi thường gặp khi dùng @Import

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bean trong class cấu hình không xuất hiện | Class chưa được import, không phải configuration candidate phù hợp hoặc điều kiện không thỏa | Kiểm tra import, annotation và condition/profile |
| Import class báo không tìm thấy | Class không có trên compile/runtime classpath hoặc sai package | Kiểm tra dependency và fully qualified class |
| Bean bị trùng tên | Hai cấu hình đăng ký bean cùng tên | Đặt tên rõ ràng, bỏ cấu hình dư hoặc dùng điều kiện phù hợp |
| Gọi một phương thức @Bean tạo object mới ngoài ý muốn | Cấu hình dùng lite mode hoặc lời gọi qua class khác không đi qua proxy | Inject bean qua tham số phương thức/constructor |
| Thay đổi thứ tự @Import nhưng thứ tự khởi tạo không như mong muốn | Nhầm thứ tự import với dependency/lifecycle order | Khai báo dependency rõ ràng; chỉ dùng @DependsOn khi thật sự cần |
| Cấu hình import vòng nhau | Ranh giới module không rõ, phụ thuộc hai chiều | Tạo composition root hoặc module dùng chung |
| Tưởng @Import quét toàn package | Nhầm với @ComponentScan | Import class cụ thể hoặc khai báo component scan có base package rõ |
| XML không được nạp | Dùng @Import cho tài nguyên XML | Dùng @ImportResource |

Khi cần biết vì sao một auto-configuration của Boot được bật hoặc bỏ qua, bật condition evaluation report bằng `debug=true` hoặc `--debug`. Khi cần biết bean nào thực sự có trong context, có thể quan sát `ApplicationContext` hoặc Actuator endpoint `beans` nếu đã bật và bảo vệ phù hợp. Những công cụ này giúp phân biệt vấn đề import, component scan, condition và dependency.

## 15. Nguyên tắc chia cấu hình dễ bảo trì

**Tách theo trách nhiệm, không tách theo số lượng bean.** Một cấu hình database có thể chứa nhiều bean liên quan chặt chẽ; một bean đơn lẻ cũng có thể cần class riêng nếu nó đại diện một module tùy chọn có ranh giới rõ.

**Giữ composition root dễ nhìn.** Lớp gốc như `OrdersModuleConfiguration` cho biết ứng dụng đang ghép những nhóm cấu hình nào. Khi danh sách import quá dài, tạo nhóm cấu hình cấp module.

**Ưu tiên dependency injection giữa các bean.** Dùng tham số constructor hoặc tham số phương thức `@Bean` thay vì gọi trực tiếp factory method của class cấu hình khác.

**Giới hạn component scan.** Dùng `@Import` cho cấu hình module đã biết; dùng `@ComponentScan` khi thực sự muốn phát hiện stereotype theo package. Không mở rộng scan tới namespace quá rộng chỉ để làm một bean xuất hiện.

**Để điều kiện nằm cạnh tính năng.** `@Profile` hoặc `@ConditionalOnProperty` nên mô tả rõ khi nào module/cấu hình được bật. Tránh để lớp composition root phải chứa nhiều nhánh điều kiện chi tiết của mọi module.

**Không phụ thuộc thứ tự import để điều khiển khởi tạo.** Hãy biểu diễn quan hệ cần thiết bằng dependency graph của Spring.

**Chỉ dùng extension point nâng cao khi cần.** `ImportSelector` phù hợp khi lựa chọn cấu hình động; `DeferredImportSelector` cho lựa chọn trì hoãn; `ImportBeanDefinitionRegistrar` cho đăng ký bean definition ở mức thấp. Với danh sách cố định, annotation `@Import` thông thường là đủ.

`@Import` giúp xây dựng cấu hình Java theo kiểu composition: mỗi class chịu trách nhiệm cho một nhóm bean, còn lớp cấp cao kết hợp những nhóm cần thiết vào cùng application context. Khi kết hợp đúng với component scan, điều kiện cấu hình và dependency injection, ứng dụng Spring Boot có thể phát triển thành nhiều module mà cấu hình vẫn rõ ràng, dễ kiểm thử và dễ thay đổi.
