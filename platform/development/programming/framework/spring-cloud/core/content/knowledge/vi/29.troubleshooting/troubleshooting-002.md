# Không tìm thấy bean dù đã thêm starter

> **Chương:** Chẩn đoán sự cố
> **Module:** `SPRING_CLOUD_CORE` — hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình bên ngoài và tương thích phiên bản với Spring Boot. Người học tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử, vận hành các abstraction chung.
> **Trọng tâm:** Thêm một starter vào build chưa bảo đảm bean sẽ xuất hiện trong ApplicationContext. Bài học hướng dẫn lần theo dependency runtime, cơ chế phát hiện auto-configuration, điều kiện tạo bean, component scanning, profile và tương thích phiên bản; sau đó dùng ConditionEvaluationReport, Actuator conditions và test context nhỏ để xác định chính xác vì sao bean không được đăng ký.

## 1. Hiểu đúng lỗi không tìm thấy bean

Một ứng dụng Spring Boot có thể biên dịch thành công sau khi thêm starter nhưng vẫn thất bại lúc chạy:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.PaymentClient' available
```

Hoặc exception có thể được bọc trong UnsatisfiedDependencyException khi Spring đang tạo một bean khác.

Điều này không nhất thiết có nghĩa dependency chưa được tải. Có thể thư viện đã nằm trên classpath nhưng Spring không tạo bean vì auto-configuration chưa được nạp, điều kiện không khớp, cấu hình người dùng nằm ngoài phạm vi scan hoặc một property/profile đang tắt tính năng.

Cần phân biệt ba lớp:

1. **Dependency có trên runtime classpath:** JVM có thể tải class cần thiết.
2. **Configuration được Spring phát hiện:** auto-configuration hoặc user configuration được đưa vào quá trình tạo ApplicationContext.
3. **Bean được đăng ký:** các điều kiện của configuration/bean method đều thỏa mãn và không có cơ chế khác khiến bean bị loại.

Một starter chủ yếu đóng gói các dependency thường dùng. Auto-configuration mới định nghĩa cách tạo bean và những điều kiện cần thiết. Với Spring Cloud, starter của một abstraction chung cũng có thể chưa phải starter của implementation cụ thể mà ứng dụng mong muốn.

### Kết quả học tập

Sau bài này, người học có thể:

1. phân biệt bean không tồn tại với lỗi không tìm thấy dependency ở runtime;
2. kiểm tra dependency thực tế trong runtime classpath;
3. hiểu vai trò của starter, auto-configuration và file đăng ký auto-configuration;
4. đọc các điều kiện Conditional làm bean không được tạo;
5. kiểm tra component scanning và ConfigurationPropertiesScan;
6. phân biệt abstraction Spring Cloud với implementation của Eureka, Consul hoặc provider khác;
7. nhận diện auto-configuration bị exclude hoặc back off;
8. kiểm tra profile, property và web application type;
9. chẩn đoán xung đột phiên bản Spring Boot/Spring Cloud;
10. dùng ConditionEvaluationReport và ApplicationContextRunner để tái hiện lỗi.

## 2. Phân biệt các loại lỗi

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với kiểu hoặc tên được yêu cầu | Bean definition, component scan, auto-configuration và conditions |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp nhưng không xác định được bean cần dùng | Primary, Qualifier, tên bean và các implementation |
| `UnsatisfiedDependencyException` | Một bean không thể được tạo vì dependency của nó không được giải quyết | Đọc nguyên nhân gốc bên trong exception |
| `BeanCreationException` | Bean đã được chọn tạo nhưng lỗi trong quá trình khởi tạo | Constructor, Bean method, lifecycle và nested cause |
| `ClassNotFoundException` | Class không có trong class loader tại thời điểm gọi | Runtime dependency, scope, packaging và classpath |
| `NoClassDefFoundError` | JVM không thể định nghĩa hoặc liên kết class cần thiết | Dependency runtime, lỗi static initializer và nguyên nhân đầu tiên |
| `BeanCurrentlyInCreationException` | Có chu trình phụ thuộc hoặc tham chiếu bean trong lúc tạo chưa hoàn tất | Dependency cycle và cách chia nhỏ cấu hình |

NoUniqueBeanDefinitionException không phải lỗi thiếu bean. Thêm một starter nữa có thể làm số implementation tăng lên và khiến lỗi trở nên rõ hơn. Hãy đọc exception sâu nhất và xem bean nào đang được yêu cầu.

## 3. Bean được tạo trong Spring Boot theo đường nào?

Khi gọi SpringApplication.run(...), Spring Boot chuẩn bị Environment, đọc cấu hình, xác định nguồn configuration và tạo ApplicationContext. Trong quá trình xử lý configuration, Spring đăng ký user configuration và auto-configuration phù hợp. Sau đó BeanFactory tạo bean theo dependency graph và lifecycle.

Có hai con đường phổ biến để bean đi vào context:

- **User configuration:** ứng dụng khai báo class Configuration, Component, Service, Repository hoặc method Bean. Những class này phải được import hoặc nằm trong phạm vi component scan.
- **Auto-configuration:** thư viện cung cấp configuration class, Spring Boot phát hiện class đó qua metadata đăng ký auto-configuration, rồi các điều kiện quyết định có áp dụng configuration hoặc từng bean method hay không.

Thêm dependency chỉ làm cho class có thể xuất hiện trên classpath. Nó không bảo đảm configuration được phát hiện hoặc điều kiện bean được tạo.

### 3.1. Starter và auto-configuration là hai vai trò

Với một thư viện tự xây dựng, cấu trúc thường tách thành:

```text
my-client/
├── my-client-core/
├── my-client-spring-boot-autoconfigure/
└── my-client-spring-boot-starter/
```

- core chứa client và logic độc lập với Spring Boot;
- autoconfigure chứa AutoConfiguration, Bean, Conditional và metadata;
- starter gom các dependency thường cần để người dùng thêm một dependency duy nhất.

Theo hướng dẫn Spring Boot, starter thường là JAR gần như rỗng, mục đích chính là cung cấp dependency phù hợp. Auto-configuration được đóng gói trong module riêng. Nếu starter không kéo theo module auto-configuration, ứng dụng có thể có client class nhưng không có bean tự động.

### 3.2. Auto-configuration không được tìm bằng component scan

Với Spring Boot hiện đại, auto-configuration class được liệt kê trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một auto-configuration class. Spring Boot đọc file này để tìm ứng viên auto-configuration.

Với Spring Boot 3.x và 4.x, hãy kiểm tra file AutoConfiguration.imports trong JAR. Các dự án cũ có thể dùng cơ chế đăng ký trước đây; khi nâng cấp, cần theo hướng dẫn của phiên bản Spring Boot tương ứng.

Auto-configuration class không nên phụ thuộc vào việc bị component scan quét trúng. Nó được nạp qua metadata auto-configuration và thường dùng Import để đưa các configuration cụ thể vào context.

### 3.3. Kiểm tra JAR có metadata không

Nếu đang phát triển starter nội bộ, hãy kiểm tra JAR đã publish có file AutoConfiguration.imports và file đó liệt kê đúng tên class. Nếu file không tồn tại, sai đường dẫn, sai tên class hoặc bị mất trong quá trình đóng gói/shading, Spring Boot sẽ không tìm thấy auto-configuration.

Nếu JAR được tạo bằng công cụ shading hoặc assembly, kiểm tra quy tắc merge resource. Một số plugin có thể ghi đè file metadata cùng tên thay vì gộp các dòng từ nhiều dependency.

## 4. Kiểm tra dependency runtime

### 4.1. Build thành công không đồng nghĩa runtime có dependency

Một dependency có thể xuất hiện trong compile classpath nhưng bị loại khỏi runtime do:

- Maven dùng scope provided hoặc test;
- Gradle khai báo compileOnly thay vì implementation/runtimeOnly;
- dependency được đánh dấu optional và không được kéo theo;
- dependency bị loại bằng exclusions;
- starter nằm trong module khác, không nằm trong executable application;
- dependency conflict chọn một version không tương thích;
- packaging tạo JAR/image thiếu thư viện cần thiết.

Với Spring Boot executable JAR, thư viện thường nằm trong BOOT-INF/lib. Nếu class có lúc compile nhưng runtime báo ClassNotFoundException, hãy kiểm tra chính artifact được deploy thay vì chỉ xem IDE.

### 4.2. Maven dependency tree

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Kiểm tra starter, module auto-configuration, implementation provider, dependency bị omitted for conflict hoặc exclude và version các module Spring Cloud có thống nhất theo BOM không.

### 4.3. Gradle dependency insight

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-context --configuration runtimeClasspath
```

Thay spring-cloud-context bằng artifact mà bean cần, ví dụ module chứa implementation của discovery client hoặc auto-configuration.

Không chỉ xem cấu hình implementation trong một subproject. Hãy kiểm tra runtimeClasspath của đúng module tạo executable JAR.

### 4.4. Kiểm tra nội dung executable JAR

```bash
jar tf target/application.jar
```

Tìm BOOT-INF/lib chứa dependency, BOOT-INF/classes chứa class ứng dụng và metadata AutoConfiguration.imports trong thư viện phù hợp.

Nếu dùng layered container image, hãy kiểm tra lớp dependency được đưa vào image. Artifact local và artifact đang chạy có thể khác nhau do cache build hoặc pipeline deploy.

## 5. Xác nhận auto-configuration có được bật

### 5.1. Ứng dụng phải opt-in auto-configuration

Thông thường, class main có:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

@SpringBootApplication bao gồm @EnableAutoConfiguration và @ComponentScan cùng các cấu hình mặc định liên quan.

Nếu ứng dụng chỉ tạo AnnotationConfigApplicationContext trực tiếp và đăng ký một configuration class, auto-configuration của Spring Boot có thể không được chạy như khi khởi động bằng SpringApplication.

Trong test, @SpringBootTest tạo context thông qua Spring Boot và phù hợp khi muốn kiểm tra hành vi auto-configuration thực tế. Một test chỉ dùng @ContextConfiguration có thể không cài đặt đầy đủ các tính năng mà SpringApplication cung cấp.

### 5.2. Không khai báo auto-configuration nhiều lần tùy tiện

Spring Boot khuyến nghị chỉ có một @SpringBootApplication hoặc @EnableAutoConfiguration trên primary configuration class.

Nếu nhiều module cùng khai báo auto-configuration hoặc nhiều context được tạo riêng, bean có thể nằm ở context khác với nơi đang inject. Hãy xác định đúng ApplicationContext đang xử lý request hoặc tạo service.

### 5.3. Kiểm tra exclusions

Auto-configuration có thể bị loại bằng annotation:

```java
@SpringBootApplication(
    exclude = PaymentClientAutoConfiguration.class
)
public class OrdersApplication {
}
```

Hoặc bằng property:

```properties
spring.autoconfigure.exclude=com.acme.payment.autoconfigure.PaymentClientAutoConfiguration
```

Tìm cả hai nơi, bao gồm cấu hình theo profile và biến môi trường được chuyển thành property. Nếu auto-configuration đã bị exclude, starter vẫn có thể nằm trên classpath nhưng bean sẽ không được tạo.

## 6. Đọc các điều kiện @Conditional

Auto-configuration thường chỉ tạo bean khi điều kiện phù hợp. Một bean không xuất hiện có thể là hành vi có chủ đích.

| Điều kiện | Ý nghĩa | Ví dụ nguyên nhân không khớp |
| --- | --- | --- |
| `@ConditionalOnClass` | Class cần thiết có trên classpath | Thiếu module implementation hoặc dependency bị exclude |
| `@ConditionalOnMissingClass` | Một class không được có mặt | Dependency khác làm nhánh cấu hình bị tắt |
| `@ConditionalOnBean` | Bean phụ thuộc đã tồn tại | Chưa có bean nền tảng hoặc auto-configuration được sắp xếp sai thứ tự |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp để auto-configuration cung cấp mặc định | Ứng dụng đã khai báo bean cùng loại nên cấu hình mặc định back off |
| `@ConditionalOnProperty` | Property có giá trị thỏa điều kiện | Property đặt false, sai tên hoặc profile chưa active |
| `@ConditionalOnResource` | Resource cần thiết có thể tìm thấy | File cấu hình hoặc resource không nằm trong classpath |
| `@ConditionalOnWebApplication` | Ứng dụng có loại web context phù hợp | App đang chạy non-web hoặc dùng reactive thay cho servlet |
| `@ConditionalOnExpression` | Biểu thức SpEL trả về true | Placeholder thiếu hoặc biểu thức trả false |

### 6.1. ConditionalOnClass

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class PaymentAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(PaymentSdk.class)
    static class PaymentSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PaymentClient paymentClient(PaymentSdk sdk) {
            return new PaymentClient(sdk);
        }
    }
}
```

Nếu PaymentSdk không có trong runtime classpath, configuration lồng bên trong không được áp dụng. Tách nhánh phụ thuộc class tùy chọn ra configuration riêng giúp tránh JVM phải xử lý method signature tham chiếu tới class không tồn tại. Thêm một starter có tên gần giống nhưng không chứa SDK thực tế không giải quyết được điều kiện này.

### 6.2. ConditionalOnProperty

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.payment",
    name = "enabled",
    havingValue = "true"
)
public class PaymentAutoConfiguration {
    // Bean methods
}
```

Cấu hình:

```yaml
acme:
  payment:
    enabled: true
```

Nếu property bị đặt false, sai prefix hoặc profile chứa property chưa được kích hoạt, configuration sẽ không match. Hãy xem effective value trong Environment; đừng chỉ đọc file application.yml mặc định.

Nếu annotation dùng matchIfMissing = true, việc không khai báo property có thể vẫn được xem là match. Nếu không đặt, hãy kiểm tra semantics của @ConditionalOnProperty.

### 6.3. ConditionalOnBean và thứ tự auto-configuration

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;

@AutoConfiguration
@ConditionalOnBean(PaymentTransport.class)
public class PaymentClientAutoConfiguration {
    // ...
}
```

Nếu PaymentTransport chưa được đăng ký tại thời điểm condition được đánh giá, configuration có thể không được áp dụng. Với custom auto-configuration, hãy kiểm tra thứ tự bằng AutoConfigureAfter, AutoConfigureBefore hoặc chia configuration theo dependency.

Spring Boot khuyến nghị dùng bean conditions trên @Bean method khi phù hợp vì các user bean definitions đã được đăng ký trước khi auto-configuration được áp dụng. Cũng cần khai báo kiểu trả về cụ thể của @Bean method để điều kiện theo type có đủ thông tin.

### 6.4. ConditionalOnMissingBean là cơ chế back off

```java
@Bean
@ConditionalOnMissingBean(PaymentClient.class)
PaymentClient paymentClient() {
    return new DefaultPaymentClient();
}
```

Nếu ứng dụng đã có một PaymentClient bean, auto-configuration sẽ không tạo bean mặc định. Đây là hành vi thay thế có chủ đích.

Nếu muốn biết bean nào đang làm auto-configuration back off, kiểm tra danh sách bean theo type và condition report. Không xóa bean tùy tiện trước khi xác định nó có đang được module khác sử dụng hay không.

## 7. Phân biệt component scanning và auto-configuration

### 7.1. Component nằm ngoài package gốc

Ví dụ cấu trúc:

```text
com.acme.orders
├── OrdersApplication.java
├── service
│   └── OrderService.java
└── payment
    └── PaymentClient.java
com.acme.shared.payment
└── PaymentConfiguration.java
```

Nếu OrdersApplication nằm ở com.acme.orders, component scan mặc định không tự quét package sibling com.acme.shared.payment.

Cách rõ ràng nhất là import configuration cần thiết:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(PaymentConfiguration.class)
public class OrdersApplication {
}
```

Hoặc mở rộng scan có chủ đích:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.acme.orders",
        "com.acme.shared.payment"
    }
)
public class OrdersApplication {
}
```

Ưu tiên scanBasePackageClasses hoặc @Import theo class khi có thể để tránh phụ thuộc chuỗi package.

### 7.2. Đặt main class ở root package

Spring Boot khuyến nghị đặt class @SpringBootApplication trong package gốc phía trên các package con của ứng dụng. Cách này giúp component scan chỉ quét phạm vi dự án và tránh phải khai báo danh sách package dài.

Không đặt class ứng dụng trong default package. Điều đó có thể khiến scan đọc class từ nhiều JAR và gây vấn đề hiệu năng hoặc phát hiện ngoài ý muốn.

### 7.3. @ConfigurationProperties không tự trở thành bean

Một class chỉ có @ConfigurationProperties không tự động được component scan như một @Component thông thường.

Có thể đăng ký bằng:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
```

Hoặc khai báo rõ:

```java
@Configuration
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
```

Nếu thiếu hai cơ chế đăng ký này, @ConfigurationProperties bean có thể không tồn tại dù class và property đều có trên classpath.

### 7.4. @Bean method phải thuộc configuration được nạp

Một method @Bean không được đăng ký chỉ vì class chứa nó nằm trong JAR. Class đó phải được import, component scan hoặc auto-configuration metadata phát hiện.

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentClient paymentClient(PaymentProperties properties) {
        return new DefaultPaymentClient(properties);
    }
}
```

Nếu PaymentConfiguration nằm ngoài scan và không được @Import, method không chạy. Kiểm tra nguồn configuration trong context thay vì chỉ tìm class trong source code.

## 8. Starter Spring Cloud không đồng nghĩa với provider implementation

Spring Cloud cung cấp nhiều abstraction chung. Một số bean chỉ có khi provider cụ thể được đưa vào classpath.

### 8.1. DiscoveryClient và DiscoveryClient theo provider

DiscoveryClient là abstraction để tìm service instance. Spring Cloud Commons cung cấp abstraction và các cơ chế mặc định, nhưng implementation gắn với registry cần module provider tương ứng.

| Nhu cầu | Dependency cần kiểm tra |
| --- | --- |
| Abstraction discovery chung | spring-cloud-commons |
| Eureka DiscoveryClient | spring-cloud-starter-netflix-eureka-client |
| Consul DiscoveryClient | spring-cloud-starter-consul-discovery |
| Zookeeper DiscoveryClient | Starter discovery của Spring Cloud Zookeeper |

Tên artifact và version phải theo release train đang dùng. Đưa đúng provider starter vào runtime classpath rồi kiểm tra auto-configuration của provider có match hay không.

Spring Cloud Commons có thể cung cấp SimpleDiscoveryClient nếu không có discovery client dựa trên service registry trong classpath. Simple client đọc danh sách instance từ property, không kết nối Eureka hoặc Consul.

Do đó, inject được DiscoveryClient chưa chứng minh Eureka/Consul đã hoạt động. Cần xác minh implementation bean thực tế.

### 8.2. EnableDiscoveryClient không tạo provider implementation

Trong Spring Cloud hiện hành, EnableDiscoveryClient không còn bắt buộc nếu implementation DiscoveryClient tương ứng đã có trên classpath. Annotation này không tự tải Eureka hoặc Consul dependency và không thể thay thế provider starter.

Discovery provider cũng có cơ chế đăng ký riêng của Spring Cloud: tài liệu Commons mô tả implementation DiscoveryClient được phát hiện qua META-INF/spring.factories với key org.springframework.cloud.client.discovery.EnableDiscoveryClient. Đây là metadata mở rộng của Spring Cloud; đừng nhầm nó với file AutoConfiguration.imports mà Spring Boot dùng để liệt kê auto-configuration class.

### 8.3. ServiceRegistry cần provider phù hợp

ServiceRegistry là abstraction cho đăng ký/hủy đăng ký service. Các implementation có thể là EurekaServiceRegistry, ConsulServiceRegistry hoặc ZookeeperServiceRegistry.

Nếu ứng dụng inject ServiceRegistry nhưng chỉ thêm Commons, có thể không có provider bean mong muốn. Hãy kiểm tra provider dependency và điều kiện auto-configuration. Đồng thời phân biệt lỗi không có bean với lỗi bean có mặt nhưng registry endpoint không truy cập được.

### 8.4. RefreshScope thuộc Spring Cloud Context

RefreshScope, ContextRefresher và các thành phần refresh thuộc Spring Cloud Context. Nếu một ứng dụng cần các API này, hãy xác nhận module chứa chúng có trong runtime classpath.

Một starter dành cho discovery hoặc load balancing không nên được giả định sẽ kéo mọi tính năng Context/refresh vào ứng dụng. Chọn dependency theo chức năng thực sự cần dùng.

## 9. Profile, property và application type

### 9.1. Profile chưa active

Một bean có thể được đánh dấu:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfiguration {
    // ...
}
```

Nếu production không nằm trong active profiles, configuration không được nạp. Kiểm tra spring.profiles.active, biến môi trường, tham số command line và profile được thêm bằng code.

Có thể bật log profiles lúc startup hoặc xem Actuator env/configprops nếu các endpoint đã được bảo vệ phù hợp.

### 9.2. Property có thể bị nguồn khác ghi đè

Giả sử file local khai báo:

```yaml
acme:
  payment:
    enabled: true
```

Nhưng deployment environment đặt ACME_PAYMENT_ENABLED=false. Khi đó condition có thể không match dù file local trông đúng.

Kiểm tra giá trị cuối cùng trong Environment và nguồn property có precedence cao hơn. Tránh suy luận chỉ từ một file cấu hình.

### 9.3. Web application type không phù hợp

Một auto-configuration có thể yêu cầu servlet web application:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
```

Nếu ứng dụng được cấu hình spring.main.web-application-type=reactive hoặc none, condition không match.

Nếu cả Spring MVC và WebFlux đều có trên classpath, Spring Boot có thể chọn MVC theo quy tắc phát hiện mặc định. Khi cần reactive context, hãy cấu hình rõ application type và kiểm tra dependency không vô tình kéo MVC vào.

### 9.4. Configuration theo profile test

Một test slice như WebMvcTest chỉ tải một phần cấu hình. Bean service hoặc auto-configuration không thuộc slice có thể vắng mặt theo thiết kế.

Nếu cần kiểm tra toàn bộ ứng dụng, dùng SpringBootTest. Nếu chỉ muốn test một configuration, dùng Import hoặc ImportAutoConfiguration có chủ đích.

## 10. Kiểm tra tương thích phiên bản Spring Boot và Spring Cloud

Spring Cloud release train được phát hành để tương thích với một số dòng Spring Boot nhất định. Kết hợp ngẫu nhiên version của từng module có thể dẫn tới:

- API hoặc class đã thay đổi;
- auto-configuration không còn cùng tên hoặc cùng package;
- dependency conflict;
- condition không match vì một class không có;
- lỗi linkage hoặc NoSuchMethodError;
- ứng dụng fail ở bước compatibility verification.

Dùng Spring Cloud BOM để quản lý version đồng bộ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó khai báo starter mà không tự chỉ định version riêng:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Với Gradle, có thể import BOM qua platform:

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    implementation "org.springframework.cloud:spring-cloud-starter-netflix-eureka-client"
}
```

Không trộn các module Spring Cloud từ nhiều release train hoặc tự override một dependency nền tảng chỉ để build qua.

### 10.1. Compatibility verifier

Spring Cloud Commons cung cấp cơ chế kiểm tra tương thích Spring Boot. Có thể bật bằng:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Khi được bật và version Boot không nằm trong tập được release train chấp nhận, ứng dụng có thể fail startup kèm thông báo version không tương thích.

Theo configuration properties của Spring Cloud Commons 5.0.4, verifier mặc định đang tắt. Bật nó trong CI/staging hoặc production nếu muốn phát hiện sớm tổ hợp version không được hỗ trợ; đừng nhầm trạng thái mặc định này với khuyến nghị bỏ qua kiểm tra tương thích.

Property spring.cloud.compatibility-verifier.compatible-boot-versions cho phép khai báo dải version được chấp nhận trong trường hợp có lý do kỹ thuật rõ ràng. Không nên tắt verifier hoặc mở rộng dải version để che giấu việc dùng sai release train.

### 10.2. Cách xác định version cần dùng

1. Xác định Spring Boot version thực tế trong runtime dependency tree.
2. Xác định Spring Cloud BOM version được import.
3. Mở bảng release train compatibility trên trang Spring Cloud.
4. Chọn một release train hỗ trợ Boot version đó.
5. Bỏ version riêng ở từng starter/module Spring Cloud để BOM quản lý.
6. Kiểm tra dependency tree sau khi build.
7. Chạy ứng dụng và xem compatibility verifier nếu đã bật.

Không dùng một bảng version cũ trong blog hoặc câu trả lời nhiều năm trước cho dự án hiện tại.

## 11. Đọc ConditionEvaluationReport để biết vì sao bean vắng mặt

### 11.1. Bật debug khi startup

Cách nhanh nhất:

```bash
java -jar application.jar --debug
```

Hoặc dùng JVM/system property -Ddebug. Spring Boot in ConditionEvaluationReport ra log, cho biết auto-configuration nào match và không match.

Tập trung vào các nhóm Positive matches, Negative matches, Exclusions và Unconditional classes. Tên nhóm và format có thể khác giữa các phiên bản, nhưng báo cáo vẫn cho biết lý do condition.

### 11.2. Actuator conditions endpoint

Nếu ứng dụng có Actuator, endpoint conditions cung cấp ConditionEvaluationReport dưới dạng JSON:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Có thể truy cập /actuator/conditions trên management interface. Bảo vệ endpoint này vì báo cáo có thể tiết lộ dependency, cấu hình và cấu trúc nội bộ của ứng dụng.

Không expose conditions công khai trong production. Dùng management port hoặc môi trường debug được giới hạn quyền truy cập.

### 11.3. Đọc đúng condition thay vì chỉ tìm tên bean

Ví dụ report cho biết PaymentClientAutoConfiguration không match vì PaymentSdk không có trên classpath. Điều đó khác với trường hợp auto-configuration match nhưng ConditionalOnProperty của bean method không match.

Đi theo từng cấp:

1. Auto-configuration có xuất hiện trong report không?
2. Nếu có, class-level conditions có match không?
3. Bean method có được xử lý không?
4. Method-level conditions có match không?
5. Có bean khác khiến ConditionalOnMissingBean back off không?
6. Bean có được tạo nhưng lỗi ở constructor hoặc dependency không?

Đừng sửa property hoặc thêm dependency khi chưa biết condition nào đang thất bại.

## 12. Kiểm tra bean registry trực tiếp

Nếu context đã khởi động, có thể xem bean theo type:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInventory {

    public BeanInventory(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(PaymentClient.class);

        for (String name : names) {
            System.out.println("PaymentClient bean: " + name);
        }
    }
}
```

Hoặc kiểm tra trực tiếp trong debugger:

- getBeanNamesForType(PaymentClient.class);
- getBeansOfType(PaymentClient.class);
- containsBean("paymentClient");
- getBeanDefinitionNames().

Nếu có parent/child ApplicationContext, hãy xác định bean nằm ở context nào. Bean ở parent có thể được child context sử dụng theo quy tắc tra cứu; ngược lại bean chỉ nằm trong child không có sẵn ở parent. Đừng so sánh hai context khác nhau rồi kết luận bean đã mất.

Không log toàn bộ bean registry ở production nếu output chứa thông tin nội bộ không cần thiết.

## 13. Kiểm thử auto-configuration bằng ApplicationContextRunner

ApplicationContextRunner tạo một context nhỏ với cấu hình và property do test chỉ định. Nó phù hợp để xác minh một auto-configuration có tạo bean trong từng tổ hợp điều kiện hay không.

### 13.1. Test bean được tạo khi điều kiện thỏa

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues("acme.payment.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(PaymentClient.class)
                );
    }

    @Test
    void backsOffWhenDisabled() {
        runner.withPropertyValues("acme.payment.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(PaymentClient.class)
                );
    }
}
```

Test này xác minh condition theo property. Nếu auto-configuration cần thêm classpath dependency hoặc bean nền tảng, hãy đưa đúng dependency/configuration vào runner.

### 13.2. Test khi thiếu class trên classpath

Spring Boot cung cấp FilteredClassLoader để mô phỏng trường hợp dependency không tồn tại:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void doesNotCreateClientWhenSdkIsMissing() {
    runner.withClassLoader(new FilteredClassLoader(PaymentSdk.class))
            .run(context ->
                    assertThat(context).doesNotHaveBean(PaymentClient.class)
            );
}
```

Test này giúp xác nhận auto-configuration tắt an toàn khi optional class không có. Trong dự án thực tế, test cần sử dụng đúng classloader và module dependency tương ứng.

### 13.3. In condition report trong test

Có thể thêm initializer:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

@Test
void printsConditionReport() {
    runner.withInitializer(
            ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    ).run(context -> {
        assertThat(context).hasNotFailed();
    });
}
```

Khi test fail, report giúp thấy condition nào không thỏa ngay trong test run.

### 13.4. Khi nào cần SpringBootTest?

Dùng ApplicationContextRunner để test auto-configuration nhỏ, có kiểm soát. Dùng SpringBootTest khi cần xác minh:

- application class thật có được phát hiện không;
- profile và external configuration có được nạp không;
- dependency graph đầy đủ của ứng dụng có tạo bean không;
- Spring Cloud provider auto-configuration hoạt động trong context thực tế.

Không thay một integration test bằng runner nếu lỗi chỉ xuất hiện do cấu hình hoặc dependency ở cấp toàn ứng dụng.

## 14. Ví dụ chẩn đoán: cần EurekaDiscoveryClient nhưng chỉ thêm Commons

Giả sử service có đoạn:

```java
@Service
public class CatalogLookupService {

    private final DiscoveryClient discoveryClient;

    public CatalogLookupService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }
}
```

Ứng dụng thêm spring-cloud-commons và inject được một DiscoveryClient, nhưng người phát triển mong muốn instance được lấy từ Eureka.

Có thể xảy ra hai trường hợp:

**Trường hợp A — chỉ có SimpleDiscoveryClient:** Spring Cloud Commons cung cấp client đơn giản đọc instance từ property. Bean abstraction có tồn tại, nhưng nó không hỏi Eureka.

**Trường hợp B — không có DiscoveryClient phù hợp:** dependency bị thiếu, discovery bị disable, hoặc context/condition của implementation không match.

Quy trình xử lý:

1. Kiểm tra runtime dependency tree.
2. Xác nhận spring-cloud-starter-netflix-eureka-client có trong module chạy ứng dụng.
3. Xác nhận version do Spring Cloud BOM quản lý.
4. Bật --debug và tìm Eureka auto-configuration trong report.
5. Kiểm tra spring.cloud.discovery.enabled không bị đặt false.
6. Xác minh bean implementation bằng getBeansOfType(DiscoveryClient.class).
7. Kiểm tra Eureka client có kết nối registry và nhận danh sách instance không.

EnableDiscoveryClient không thay thế dependency Eureka. Với Spring Cloud hiện hành, annotation này không cần thiết nếu provider implementation đã có trên classpath.

## 15. Ví dụ chẩn đoán: ConfigurationProperties không được đăng ký

Một class có annotation:

```java
@ConfigurationProperties(prefix = "client.remote")
public class RemoteClientProperties {

    private URI endpoint;

    // getters and setters
}
```

Nhưng constructor injection báo không tìm thấy RemoteClientProperties.

Nguyên nhân có thể là class này không được đăng ký bằng ConfigurationPropertiesScan hoặc EnableConfigurationProperties.

Cách xử lý:

```java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = RemoteClientProperties.class)
public class OrdersApplication {
}
```

Hoặc:

```java
@Configuration
@EnableConfigurationProperties(RemoteClientProperties.class)
public class RemoteClientConfiguration {
}
```

Sau đó xác minh property binding riêng. Bean tồn tại không có nghĩa client.remote.endpoint đã có giá trị hợp lệ.

## 16. Runbook chẩn đoán theo thứ tự

Khi nhận lỗi "đã thêm starter nhưng không tìm thấy bean", thực hiện lần lượt:

1. Đọc exception sâu nhất và xác định type bean đang được yêu cầu.
2. Phân biệt NoSuchBeanDefinitionException với NoUniqueBeanDefinitionException, ClassNotFoundException và lỗi khởi tạo bean.
3. Xác định đúng module tạo executable application.
4. Kiểm tra dependency tree của runtime classpath.
5. Xác nhận dependency chứa implementation class và auto-configuration module.
6. Kiểm tra artifact deploy có chứa dependency và metadata cần thiết.
7. Xác nhận ứng dụng chạy bằng SpringApplication với SpringBootApplication hoặc EnableAutoConfiguration.
8. Bật --debug và đọc ConditionEvaluationReport.
9. Kiểm tra class-level và method-level conditions.
10. Kiểm tra property, profile và web application type.
11. Kiểm tra component scan, Import và configuration properties registration.
12. Kiểm tra auto-configuration exclusions và ConditionalOnMissingBean.
13. Xác nhận version Spring Boot/Spring Cloud tương thích.
14. Viết test context nhỏ tái hiện condition thất bại.
15. Chỉ sửa nguyên nhân đã xác định, rồi chạy lại test context và integration test phù hợp.

Nếu bean có trong context nhưng injection vẫn thất bại, kiểm tra qualifier, generic type, bean name, parent/child context và kiểu bean proxy trước khi thay đổi dependency.

## 17. Bảng triệu chứng và cách xử lý nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Thêm starter nhưng không có auto-config | Starter không kéo module autoconfigure hoặc metadata thiếu | Dependency tree và AutoConfiguration.imports |
| Auto-config có trong JAR nhưng không có trong report | Auto-configuration chưa được đăng ký hoặc không được bật | --debug, kiểm tra metadata và EnableAutoConfiguration |
| Negative match vì missing class | Dependency implementation thiếu ở runtime | dependencyInsight, runtimeClasspath, BOOT-INF/lib |
| Negative match vì property | Property false, sai tên hoặc profile chưa active | Environment và config report |
| Component Service không được tìm thấy | Package nằm ngoài component scan | Package main class, scanBasePackages, Import |
| ConfigurationProperties không tồn tại | Thiếu scan hoặc EnableConfigurationProperties | Kiểm tra cấu hình đăng ký properties |
| Bean mặc định không được tạo | User bean cùng type làm ConditionalOnMissingBean back off | getBeansOfType và condition report |
| DiscoveryClient tồn tại nhưng không dùng Eureka | Chỉ có SimpleDiscoveryClient hoặc thiếu provider | Kiểm tra implementation bean và Eureka starter |
| Chỉ lỗi trong test slice | Slice không nạp cấu hình hoặc auto-config cần thiết | Dùng ImportAutoConfiguration hoặc SpringBootTest |
| Startup fail với compatibility message | Spring Boot không nằm trong dải tương thích release train | Kiểm tra BOM và release train |
| NoSuchBeanDefinitionException nhưng có bean cùng tên ở context khác | Parent/child context hoặc test tạo context riêng | Xem đúng BeanFactory đang inject |
| NoUniqueBeanDefinitionException | Có nhiều implementation cùng type | Primary, Qualifier và danh sách bean |

## 18. Checklist trước khi kết luận starter bị lỗi

- [ ] Starter nằm trong đúng module tạo ứng dụng.
- [ ] Dependency có trong runtimeClasspath.
- [ ] Module chứa implementation class có mặt.
- [ ] Module auto-configuration có mặt nếu starter dựa vào auto-configuration.
- [ ] File AutoConfiguration.imports có entry đúng với custom starter.
- [ ] Ứng dụng bật auto-configuration qua SpringBootApplication hoặc EnableAutoConfiguration.
- [ ] Không có exclude trong annotation hoặc spring.autoconfigure.exclude.
- [ ] Class-level conditions và bean-method conditions đều match.
- [ ] Property và active profile đúng.
- [ ] Component nằm trong scan scope hoặc đã được import.
- [ ] ConfigurationProperties được đăng ký đúng cách.
- [ ] Provider starter đúng với abstraction cần dùng.
- [ ] Spring Boot và Spring Cloud version tương thích.
- [ ] Condition report đã được đọc trước khi thêm dependency ngẫu nhiên.
- [ ] Test đã tái hiện được condition tạo bean.

## 19. Bài tập vận dụng

### Bài tập 1 — Starter có mặt nhưng auto-configuration không xuất hiện

Một custom starter chứa PaymentClientAutoConfiguration, nhưng ứng dụng không có bean PaymentClient.

Hãy kiểm tra dependency tree, module autoconfigure và file META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports. Giải thích vì sao component scan không phải cách đăng ký auto-configuration chuẩn.

### Bài tập 2 — Component nằm ngoài package gốc

Main class ở com.acme.orders, còn FraudDetectionService ở com.acme.shared.fraud.

Hãy giải thích vì sao bean không được scan và viết hai cách đưa configuration vào context bằng Import hoặc scan package có chủ đích.

### Bài tập 3 — Property condition không match

Auto-configuration dùng ConditionalOnProperty(prefix = "acme.cache", name = "enabled", havingValue = "true"). File local đặt true nhưng production vẫn không có bean.

Hãy liệt kê các nguồn property có thể ghi đè, cách kiểm tra active profile và cách đọc ConditionEvaluationReport.

### Bài tập 4 — Có DiscoveryClient nhưng không có Eureka

Ứng dụng inject thành công DiscoveryClient nhưng chỉ nhận instance khai báo trong property.

Hãy giải thích SimpleDiscoveryClient, provider starter và cách xác minh implementation bean thực tế.

### Bài tập 5 — Auto-configuration back off

Ứng dụng khai báo một PaymentClient bean tùy chỉnh. Sau đó bean mặc định của starter không xuất hiện.

Hãy giải thích ConditionalOnMissingBean, cách kiểm tra bean đang tồn tại và vì sao đây có thể là hành vi đúng.

### Bài tập 6 — Dependency conflict giữa Spring Boot và Spring Cloud

Sau khi nâng Spring Boot, ứng dụng không tạo được một số bean Spring Cloud và startup có lỗi linkage.

Hãy đề xuất quy trình kiểm tra release train, BOM, dependency tree và compatibility verifier. Nêu vì sao tắt verifier không phải cách sửa nguyên nhân.

## 20. Tự kiểm tra nhanh

1. Thêm starter có bảo đảm bean được tạo không? **Không, còn phụ thuộc auto-configuration và conditions.**
2. Starter và auto-configuration có cùng vai trò không? **Không; starter gom dependency, auto-configuration định nghĩa cách tạo bean.**
3. Auto-configuration hiện đại được liệt kê ở đâu? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.**
4. SpringBootApplication có bao gồm auto-configuration không? **Có, thông qua EnableAutoConfiguration.**
5. ConditionalOnClass không match thường có nghĩa gì? **Class cần thiết không có trên classpath phù hợp.**
6. ConditionalOnMissingBean làm gì? **Cho phép auto-configuration bỏ qua bean mặc định khi đã có bean thay thế.**
7. ConfigurationProperties tự tạo bean chỉ bằng annotation không? **Không, cần scan hoặc đăng ký rõ ràng.**
8. Có cần EnableDiscoveryClient khi provider implementation đã có trên classpath không? **Không bắt buộc trong Spring Cloud hiện hành.**
9. SimpleDiscoveryClient có đồng nghĩa Eureka đang hoạt động không? **Không.**
10. Lệnh nào bật ConditionEvaluationReport lúc startup? **java -jar application.jar --debug.**
11. Endpoint Actuator nào hiển thị conditions? **/actuator/conditions, nếu đã expose và bảo vệ.**
12. Vì sao nên dùng Spring Cloud BOM? **Để giữ các module cùng release train và tương thích với Spring Boot.**
13. ApplicationContextRunner hữu ích cho điều gì? **Kiểm thử auto-configuration theo từng tổ hợp classpath, bean và property.**
14. Nếu có bean cùng type nhưng injection báo không tìm thấy, cần kiểm tra gì? **Context đang inject, qualifier, generic type và parent/child context.**

**Thông điệp cốt lõi:** Khi bean không xuất hiện dù đã thêm starter, hãy truy vết từ runtime classpath đến auto-configuration metadata, conditions và quá trình đăng ký bean. Phân biệt abstraction Spring Cloud với provider implementation, kiểm tra component scan và version compatibility, rồi dùng ConditionEvaluationReport hoặc ApplicationContextRunner để chứng minh nguyên nhân. Chỉ khi biết chính xác điều kiện nào không thỏa, bạn mới có thể sửa lỗi mà không làm classpath phình to hoặc vô tình bật thêm những tính năng không cần thiết.

**Tài liệu tham khảo:**

- [Spring Boot 4.1 — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot 4.1 — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html)
- [Spring Boot 4.1 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud Commons 5.0.4 — Common Abstractions and DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.0.4 — Configuration Properties and Compatibility Verifier](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud#overview)

Tên class, package, artifact và điều kiện auto-configuration có thể thay đổi theo release. Hãy dùng tài liệu của Spring Boot/Spring Cloud release train đang chạy và kiểm tra runtime dependency tree của chính ứng dụng.
