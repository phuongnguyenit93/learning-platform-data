# Nhập lớp cấu hình bằng `@Import` trong Spring Core Container

## 1. Vấn đề: một ứng dụng cần nhiều Java configuration classes

Một ứng dụng Spring nhỏ có thể đặt tất cả factory methods trong một class `@Configuration`. Khi hệ thống lớn dần, code thường được tách theo trách nhiệm: repository, nghiệp vụ, hạ tầng, tính năng tùy chọn. Khi khởi tạo `ApplicationContext`, làm thế nào ghép các cấu hình mà không phải đăng ký thủ công từng class ở mọi điểm khởi động?

Spring hỗ trợ annotation `org.springframework.context.annotation.Import`. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {
    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {
    @Bean
    CustomerService customerService(CustomerRepository repository) {
        return new CustomerService(repository);
    }
}
```

Đây là **đoạn mã minh họa**, chưa phải file Java chạy độc lập: `CustomerRepository`, `InMemoryCustomerRepository` và `CustomerService` là các kiểu ứng dụng cần định nghĩa. Khi đăng ký `ServiceConfig` vào Spring container, `@Import(RepositoryConfig.class)` khiến Spring **xử lý cả `RepositoryConfig`**, bao gồm bean definition của `customerRepository()`. Tham số factory method `CustomerRepository repository` được container giải quyết theo quy tắc dependency injection.

Điểm cốt lõi: `@Import` **ghép các nguồn cấu hình một cách tường minh**. Nó không có nghĩa “gọi constructor của một class ngay lập tức”, cũng không phải “quét tất cả class trong package được nhập”.

Bài học này tập trung vào:

1. Cú pháp `@Import` với một hoặc nhiều configuration classes và cách tạo entry-point duy nhất.
2. Bean definition, quan hệ phụ thuộc và việc import bắc cầu.
3. Import các **regular component classes**, không chỉ `@Configuration`.
4. Khác biệt giữa `@Import`, `@ComponentScan`, `@Bean`, `@ImportResource` và `@Enable...`.
5. Mở rộng import với `ImportSelector`, `DeferredImportSelector` và `ImportBeanDefinitionRegistrar`.
6. Cách dùng trong ứng dụng phân mô-đun, tính năng có điều kiện, kiểm thử và xử lý lỗi.
7. Dự án Java 17+ chạy được trên Spring Framework 6.2, có cấu trúc Gradle và stdout dự kiến.

## 2. `@Import` là gì?

`@Import` là annotation được khai báo ở **type level**. Nó nhận một mảng `Class<?>`, có thể viết một class hoặc nhiều class:

```java
@Import(DatabaseConfig.class)
```

```java
@Import({DatabaseConfig.class, ServiceConfig.class, MetricsConfig.class})
```

Khi cấu hình mang `@Import` được Spring xử lý, các import candidates được bổ sung vào quá trình xử lý configuration classes và đăng ký bean definitions. Trong Spring Framework 6.2, `@Import` hỗ trợ bốn nhóm phổ biến:

| Đối tượng đưa vào `@Import` | Điều Spring làm | Mục đích |
| --- | --- | --- |
| Class `@Configuration` | Xử lý class cấu hình, đăng ký các `@Bean` methods và các metadata liên quan | Ghép các cấu hình khai báo tĩnh |
| Regular component class | Đăng ký class như một component/bean definition phù hợp mà không cần component scanning | Chọn rõ những class ứng dụng muốn đưa vào container |
| Implementation của `ImportSelector` | Gọi selector để xác định các class cần import dựa trên metadata/cấu hình | Chọn cấu hình theo điều kiện hoặc annotation attributes |
| Implementation của `ImportBeanDefinitionRegistrar` | Cho phép đăng ký bean definitions bằng code trên `BeanDefinitionRegistry` | Extension point hạ tầng cần quyền kiểm soát mức registry |

Kể từ Spring Framework 4.2, `@Import` có thể nhập **regular component classes**, tương tự ý tưởng đăng ký một class qua `AnnotationConfigApplicationContext.register(...)`. Vì vậy, đối tượng import không bắt buộc luôn là `@Configuration`.

**Điều không thuộc chức năng trực tiếp của `@Import`:** nhập tài nguyên XML dưới dạng bean definitions. Với XML hoặc những resource bean definitions khác được hỗ trợ, cơ chế liên quan là `@ImportResource`. Cũng không thể truyền một chuỗi package vào `@Import`: đây là annotation yêu cầu các `Class<?>` cụ thể.

### 2.1. `@Import` là ghép cấu hình, không phải Java `import` statement

Hai cú pháp cùng có từ “import” nhưng vai trò khác nhau:

```java
import com.example.storage.StorageConfig;  // Java compiler: dùng tên class.

@Import(StorageConfig.class)               // Spring: đưa config vào container.
```

Lệnh Java `import` ở đầu source chỉ giúp trình biên dịch giải quyết tên kiểu; nó **không đăng ký bean**. Spring `@Import` thực sự tham gia vào giai đoạn phân tích bean definitions của container.

### 2.2. Khi nào quá trình import diễn ra?

Một luồng tổng quát:

```text
new AnnotationConfigApplicationContext(AppConfig.class)
                         |
                         v
           Đăng ký AppConfig làm đầu vào
                         |
                         v
        Xử lý @Configuration và @Import
                         |
          +--------------+--------------+
          |                             |
          v                             v
     @Bean của AppConfig          Import classes
                                        |
                     +------------------+--------------------+
                     |                  |                    |
                     v                  v                    v
                @Configuration     ImportSelector    Regular component
                     |                  |                    |
                     v                  v                    v
                  @Bean defs      Config candidates      Bean definition
                     |
                     +------------------+--------------------+
                                        |
                                        v
                           BeanFactory/registry
                                        |
                                        v
                        DI, instantiation, lifecycle
```

Spring giải quyết việc import và tạo **bean definitions** trong lúc xử lý cấu hình. Sau đó bean instances mới được tạo theo scope/lazy rules và dependency graph. Không nên kết luận rằng thứ tự các class trong mảng `@Import` là thứ tự khởi tạo bean, hoặc rằng mọi constructor của class import đã được gọi ngay khi đọc annotation.

## 3. Ghép hai configuration classes và khai báo dependency xuyên cấu hình

Xét hai lớp cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class PersistenceConfig {

    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(PersistenceConfig.class)
class ApplicationConfig {

    @Bean
    InventoryService inventoryService(InventoryRepository repository) {
        return new InventoryService(repository);
    }
}
```

Các kiểu domain trong trích đoạn được định nghĩa ở ứng dụng thực tế. Chỉ cần đưa `ApplicationConfig` vào `AnnotationConfigApplicationContext`; `PersistenceConfig` sẽ được xử lý nhờ `@Import`.

**Quan hệ dependency được Spring giải quyết qua factory-method parameter**, không qua lời gọi Java `inventoryRepository()` ở config khác. `InventoryService` có thể dùng một singleton repository được Spring quản lý; không cần injection chính `PersistenceConfig` vào `ApplicationConfig`.

Phương pháp này hữu ích với `@Configuration(proxyBeanMethods = false)`. Ở lite mode, một lời gọi Java trực tiếp tới một `@Bean` method không có cơ chế CGLIB inter-bean interception; còn dependency parameter vẫn được BeanFactory resolve đúng theo container semantics.

### 3.1. Mỗi bean có tên và scope riêng

`@Import` không biến tất cả factory methods của các class khác nhau thành “một bean”. Mỗi `@Bean` method được xử lý thành một bean definition riêng với bean name/qualifier/scope tùy cấu hình. Tên mặc định của bean do `@Bean` method tạo thường chính là **tên method**, ví dụ `inventoryRepository`.

Khi context tồn tại:

```java
InventoryRepository repository = context.getBean(InventoryRepository.class);
InventoryService service = context.getBean(InventoryService.class);
```

Đây là trích đoạn minh họa khi `context` đã được tạo. Với singleton scope mặc định, Spring thường trả cùng instance mỗi lần resolve theo bean name/type trong cùng BeanFactory.

### 3.2. Import bắc cầu

Class đã import có thể tiếp tục mang `@Import`:

```java
@Configuration
@Import(PersistenceConfig.class)
class ServiceConfig {
}

@Configuration
@Import(ServiceConfig.class)
class MainConfig {
}
```

Đây là mã minh họa. Đăng ký `MainConfig` khiến Spring xử lý cấu trúc import đi qua `ServiceConfig` tới `PersistenceConfig`. Điều đó giúp tổ chức các **tập cấu hình có chủ đích**, thay vì bắt application main biết từng config chi tiết.

Không nên tạo vòng import A → B → A. Spring configuration processor có cơ chế phát hiện vòng nhập không hợp lệ và có thể báo lỗi; sự phức tạp khi import vòng cũng làm ownership của module mơ hồ. Nếu hai module cần nhau, ưu tiên trích phần chung hoặc điều chỉnh chiều phụ thuộc.

### 3.3. Nhập một configuration class nhiều lần

Một config có thể được tham chiếu từ nhiều điểm của đồ thị import. Spring configuration processing có cơ chế xử lý candidates trùng nhằm tránh đăng ký lại cùng configuration một cách vô nghĩa trong các trường hợp bình thường. **Không dùng import lặp để mong tạo hai singleton instances.** Nếu muốn hai bean cấu hình khác nhau từ cùng implementation, nên khai báo hai bean definitions khác tên/parameters có chủ đích.

Cũng cần tránh trùng tên `@Bean` giữa các configuration classes không tương thích. Dù hai class khác nhau, cùng method `@Bean service()` mặc định cùng bean name `service`; chính sách bean overriding có thể khiến definition bị thay thế hoặc gây lỗi. Hãy đặt tên rõ khi trách nhiệm khác nhau và kiểm thử registry.

## 4. `@Import` và `@ComponentScan`: lựa chọn theo ranh giới

Hai annotation đều có thể dẫn đến việc Spring có thêm bean definitions, nhưng chúng giải quyết hai bài toán khác nhau.

| Tiêu chí | `@Import` | `@ComponentScan` |
| --- | --- | --- |
| Khai báo đầu vào | Các class cụ thể, selectors hoặc registrars | Một/một số base packages cùng filters |
| Cần biết từng class? | Với import tĩnh, có | Không cần liệt kê từng component |
| Tự mở toàn bộ package? | Không | Có, xét cả subpackages |
| Hợp với thư viện/điểm tích hợp | Có, configuration entry point công khai | Có nếu ứng dụng chủ ý quản lý toàn bộ package |
| Tác động khi thêm class `@Component` mới trong package | Không tự có bean mới trừ khi được đăng ký qua nguồn khác | Class mới có thể được quét và đăng ký |
| Điều kiện/selector động | `ImportSelector` / conditional metadata | Filters/conditions và những cơ chế khác |
| Có thể kết hợp | Có | Có |

Ví dụ chọn **cụ thể** một component:

```java
@Configuration
@Import(EmailGateway.class)
class MessagingConfig {
}
```

Nếu `EmailGateway` là regular class có constructor phù hợp, Spring có thể đăng ký nó nhờ `@Import` mà không quét cả package chứa gateway. `EmailGateway` không nhất thiết phải được đánh dấu `@Component`; xem ví dụ chạy ở mục 9.

Với quét package:

```java
@Configuration
@ComponentScan(basePackages = "com.example.messaging")
class MessagingConfig {
}
```

Scanner sẽ xem các component candidates trong `com.example.messaging` và subpackages, không chỉ một `EmailGateway`.

### 4.1. Trong ứng dụng nhiều mô-đun

Một cấu trúc hợp lý:

```text
app/
  AppConfig.java               -> @Import({StorageModuleConfig, OrderModuleConfig})
storage/
  StorageModuleConfig.java     -> công bố các beans của storage
  internal/...
orders/
  OrderModuleConfig.java       -> công bố các beans của orders
  internal/...
```

`@Import` hỗ trợ kiến trúc trong đó **mỗi module cung cấp một configuration entry point** và application chọn module nào tham gia container. Điều này tránh quét vô tình toàn bộ package của library chỉ vì JAR nằm trên classpath.

Tuy nhiên, import một configuration class có `@ComponentScan` bên trong **vẫn có thể kích hoạt chính lượt scan đó**. Vì thế `@Import` không tự giới hạn những bean mà config được import đăng ký. Cần đọc cấu hình được nhập để biết phạm vi thực tế.

### 4.2. Component scan không thay thế import module rõ ràng

Trong Spring Boot, đặt `@SpringBootApplication` ở root package có thể quét các component bên dưới. Nhưng không phải thư viện nào cũng muốn người dùng scan package nội bộ. Một library có thể dùng cấu hình do ứng dụng `@Import`, hoặc cung cấp Spring Boot auto-configuration theo quy ước riêng.

**Không đồng nhất component scanning với Spring Data repository scanning hoặc JPA entity scanning.** Các hệ thống này có extension points và vùng scan khác nhau. `@Import` một configuration class có thể kích hoạt `@EnableJpaRepositories`, nhưng bản thân `@Import` không tự biến mọi interface `Repository` trong project thành repository proxy.

## 5. Import regular component class

Javadoc `@Import` của Spring Framework 6.2 cho phép nhập regular component class, không nhất thiết là `@Configuration`. Điều này tạo lối đăng ký tường minh:

```java
class HealthProbe {
    String status() {
        return "ok";
    }
}

@Configuration
@Import(HealthProbe.class)
class AppConfig {
}
```

Đây là đoạn minh họa. Khi đăng ký `AppConfig`, Spring có thể tạo bean `HealthProbe` dù không có `@ComponentScan` và `HealthProbe` không mang stereotype. Miễn class có thể khởi tạo và các dependency hợp lệ, caller có thể:

```java
HealthProbe probe = context.getBean(HealthProbe.class);
```

Tên bean của class được import theo loại registration và `BeanNameGenerator` của configuration processor; đừng mặc định tên chính luôn là `healthProbe` giống default component scanner. Nếu không có nhu cầu tên tường minh, **lookup theo type** thường ít ràng buộc hơn.

### 5.1. Một interface không tự trở thành implementation

`@Import(MyPort.class)` với `MyPort` là interface thuần không tạo ra một implementation hữu dụng. Phải nhập concrete implementation hoặc một configuration/factory/registrar tạo object phù hợp. Một abstract class cũng không thể được container khởi tạo thông thường chỉ vì nó xuất hiện trong `@Import`.

### 5.2. Import class có constructor dependency

Spring có thể phân giải constructor injection cho regular component class được nhập, theo khả năng bean creation của container. Ví dụ:

```java
public class AuditReporter {
    private final AuditStorage storage;

    public AuditReporter(AuditStorage storage) {
        this.storage = storage;
    }
}
```

Nếu `@Import(AuditReporter.class)` được dùng và có một bean `AuditStorage` phù hợp, container có thể inject tham số. Nếu thiếu dependency, bạn vẫn nhận lỗi tạo bean; `@Import` không tự cung cấp các type chưa được đăng ký.

### 5.3. Import không có nghĩa bao gồm toàn bộ package

Giả sử `EmailGateway` và `SmsGateway` nằm cùng package. `@Import(EmailGateway.class)` không tự đăng ký `SmsGateway`. Nếu một `@Configuration` được import lại bật `@ComponentScan` trên package đó, lúc ấy việc phát hiện thêm bean là kết quả của **component scan trong configuration**, không phải vì `@Import` tự quét package.

## 6. `ImportSelector`: chọn configuration động

Với một class selector implement `org.springframework.context.annotation.ImportSelector`, Spring gọi:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

Selector nhận metadata của class khai báo `@Import` và trả **mảng tên class đầy đủ** sẽ được nhập. Nó giúp tạo annotation bật tính năng và quyết định cấu hình theo attributes/environment hoặc quy tắc hạ tầng.

Ví dụ:

```java
public class StorageSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { InMemoryStorageConfig.class.getName() };
    }
}
```

Đây là snippet minh họa, cần import `ImportSelector`, `AnnotationMetadata` và tồn tại `InMemoryStorageConfig`. Khi dùng:

```java
@Configuration
@Import(StorageSelector.class)
class AppConfig {
}
```

Spring xử lý selector và nhập configuration được selector trả về. Trong chương trình ở mục 9, `PromotionSelector` sẽ nhập `PromotionConfig` tương tự.

### 6.1. Metadata cho phép xây annotation cấu hình cấp cao

Một annotation tự định nghĩa có thể dùng `@Import` ở dạng **meta-annotation**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(StorageSelector.class)
public @interface EnableStorage {
}
```

Đây là đoạn minh họa: cần imports `java.lang.annotation.*` cùng `@Import`. Ở chỗ khác:

```java
@Configuration
@EnableStorage
class AppConfig {
}
```

Sau đó selector có thể đọc thông tin của importing configuration/annotation để quyết định class cần import. Đây là nền tảng để viết những annotation `@Enable...` có hành vi được quản lý qua configuration import.

Cần phân biệt **bật một module bằng annotation** với **component scanning**; annotation `@EnableStorage` ở ví dụ chỉ nhập selector/config do nó khai báo, không tự quét package ngoài những bước được cấu hình tiếp.

### 6.2. `DeferredImportSelector`

`DeferredImportSelector` kế thừa `ImportSelector` và cho phép trì hoãn thời điểm lựa chọn imports đến giai đoạn sau khi các configuration classes thông thường được xử lý. Đây là extension point nâng cao hữu ích cho các tình huống chọn cấu hình dựa trên bối cảnh rộng hơn, nổi bật trong cách tổ chức auto-configuration.

Không cần `DeferredImportSelector` chỉ để ghép hai configuration classes cố định. `@Import({AConfig.class, BConfig.class})` trực tiếp dễ hiểu hơn và tránh phức tạp trong vòng đời xử lý cấu hình.

### 6.3. Selector không phải bean nghiệp vụ thông thường

`ImportSelector` là hạ tầng configuration processing. Đừng giả định nó được đăng ký dưới một bean name thông thường để injection vào service giống một `@Component`. Mục đích của nó là **chọn class nào cần import**, không phải tạo object nghiệp vụ bằng các method trên selector.

## 7. `ImportBeanDefinitionRegistrar`: đăng ký bean definitions bằng code

Nếu muốn thao tác ở mức thấp hơn `@Bean`, Spring cho phép class implement `org.springframework.context.annotation.ImportBeanDefinitionRegistrar`. Một method liên quan:

```java
void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry
);
```

Một implementation có thể phân tích annotation metadata, tạo `BeanDefinition` và đăng ký nó vào registry. Ví dụ:

```java
public class DiagnosticsRegistrar implements ImportBeanDefinitionRegistrar {
    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(DiagnosticsClient.class);
        registry.registerBeanDefinition("diagnosticsClient", definition);
    }
}
```

Đây là snippet minh họa, cần các imports:

```java
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;
```

Và cần class `DiagnosticsClient` có constructor/metadata hợp lệ. Trong ứng dụng:

```java
@Configuration
@Import(DiagnosticsRegistrar.class)
class AppConfig {
}
```

Spring có thể đăng ký bean definition `diagnosticsClient`. Registrar cho phép khai báo bean dựa trên metadata mà không cần tạo mỗi factory method cố định ở source.

**Giới hạn lifecycle quan trọng:** theo Javadoc Spring 6.2, không đăng ký `BeanDefinitionRegistryPostProcessor` types qua `ImportBeanDefinitionRegistrar` theo cách tùy ý vì có ràng buộc vòng đời của configuration class processing. Khi cần infrastructure post-processor, chọn cơ chế đăng ký hạ tầng được framework khuyến nghị.

### Khi nào nên dùng registrar?

- Framework/library xây abstraction cấu hình bằng annotation riêng.
- Cần đăng ký số lượng bean definitions phụ thuộc metadata.
- Muốn tự quyết định bean names, implementation types, constructor/factory metadata hoặc các điều kiện ở mức registry.

**Không ưu tiên registrar cho hai object cụ thể.** Nếu chỉ cần `Repository` và `Service`, `@Configuration` với `@Bean` methods rõ ràng thường dễ đọc, dễ debug và dễ kiểm thử hơn.

### 7.1. Sự khác biệt với selector

| Cơ chế | Kết quả chính |
| --- | --- |
| `@Import(SomeConfig.class)` | Nhập trực tiếp class cấu hình |
| `ImportSelector` | Trả class names để Spring tiếp tục xử lý import |
| `DeferredImportSelector` | Chọn import ở giai đoạn trì hoãn |
| `ImportBeanDefinitionRegistrar` | Đăng ký trực tiếp bean definitions trong registry |

Selector trả **tên class cần import**; registrar làm việc với **định nghĩa bean**. Tránh viết một selector mà cố trả bean name thay cho class name; Spring cần class names hợp lệ để xử lý.

## 8. Ví dụ chạy được: Java 17+, Spring 6.2 và một entry-point `@Import`

Dự án hoàn chỉnh dưới đây chỉ đăng ký **một** configuration class vào `AnnotationConfigApplicationContext`. Spring sẽ xử lý:

- `@Import` đưa vào hai configuration classes: `RepositoryConfig` và `BusinessConfig`.
- `@Import` đưa vào một regular class `HealthProbe` dù class đó không có `@Component`.
- `PromotionSelector` thực thi `ImportSelector` và chọn `PromotionConfig`.
- `BusinessConfig` tạo `CheckoutService` từ các bean do những cấu hình khác cung cấp.
- Một class `UnscannedHelper` có `@Component` nhưng **không được import và không nằm trong scan nào**, nên không xuất hiện trong context.

Ví dụ không cần Spring Boot, web server, XML hoặc database.

### 8.1. Cấu trúc file

```text
spring-import-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ImportCompositionDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-import-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ImportCompositionDemo'
}
```

Dùng JDK 17 trở lên và phiên bản Gradle tương thích với JDK. `spring-context` kéo theo những module Spring Beans/Core cần thiết; không cần thêm `spring-boot` để dùng `@Import`.

### 8.2. Mã Java đầy đủ

Lưu vào `src/main/java/ImportCompositionDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.stereotype.Component;

public class ImportCompositionDemo {

    public record CatalogRepository(String source) {
        String find() {
            return source;
        }
    }

    public record DiscountPolicy(int percent) {
    }

    public record CheckoutService(
            CatalogRepository repository,
            DiscountPolicy discountPolicy) {

        int total(int price) {
            return price - price * discountPolicy.percent() / 100;
        }

        String summary() {
            return repository.find() + ":" +
                    discountPolicy.percent() + "%";
        }
    }

    public record AppTag(String text) {
    }

    // Regular class, không có @Component.
    public static class HealthProbe {
        public HealthProbe() {
        }

        String status() {
            return "ok";
        }
    }

    // Có @Component, nhưng không được scan hoặc import.
    @Component
    public static class UnscannedHelper {
    }

    @Configuration(proxyBeanMethods = false)
    public static class RepositoryConfig {
        @Bean
        CatalogRepository catalogRepository() {
            return new CatalogRepository("catalog");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PromotionConfig {
        @Bean
        DiscountPolicy discountPolicy() {
            return new DiscountPolicy(10);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BusinessConfig {
        @Bean
        CheckoutService checkoutService(
                CatalogRepository repository,
                DiscountPolicy discountPolicy) {
            return new CheckoutService(repository, discountPolicy);
        }
    }

    public static class PromotionSelector implements ImportSelector {
        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {
            return new String[] { PromotionConfig.class.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
            RepositoryConfig.class,
            BusinessConfig.class,
            HealthProbe.class,
            PromotionSelector.class
    })
    public static class AppConfig {
        @Bean
        AppTag appTag() {
            return new AppTag("imported-composition");
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            AppTag tag = context.getBean(AppTag.class);
            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);
            DiscountPolicy policy =
                    context.getBean(DiscountPolicy.class);
            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            HealthProbe probe = context.getBean(HealthProbe.class);

            System.out.println("tag = " + tag.text());
            System.out.println("repository = " + repository.find());
            System.out.println("discount = " + policy.percent() + "%");
            System.out.println("total200 = " + checkout.total(200));
            System.out.println("summary = " + checkout.summary());
            System.out.println("probe = " + probe.status());
            System.out.println("unscannedCandidates = " +
                    context.getBeanNamesForType(UnscannedHelper.class).length);
            System.out.println("sameRepository = " +
                    (repository == checkout.repository()));
        }
    }
}
```

Đây là chương trình Java đầy đủ: chỉ có một top-level public class `ImportCompositionDemo`; các kiểu domain dùng Java record, còn các cấu hình/selector/probe là static nested classes. `AppConfig` đóng vai trò composition root.

### 8.3. Lệnh chạy và stdout

Trong thư mục `spring-import-demo`:

```bash
gradle run --quiet
```

Nếu sử dụng Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Các dòng do `System.out.println` trong chương trình tạo ra:

```text
tag = imported-composition
repository = catalog
discount = 10%
total200 = 180
summary = catalog:10%
probe = ok
unscannedCandidates = 0
sameRepository = true
```

Lưu ý: ví dụ xác định những dòng **chương trình** in ra; Gradle hay hệ thống logging có thể in thêm thông báo không thuộc `System.out.println`.

### 8.4. Giải thích từng kết quả

**`tag = imported-composition`**: `AppConfig` được đăng ký trực tiếp. Method `@Bean appTag()` của nó tạo bean `AppTag`.

**`repository = catalog`**: `RepositoryConfig` được import tĩnh, nên bean `catalogRepository` tồn tại; không cần `@ComponentScan`.

**`discount = 10%`**: `PromotionSelector` được import và trả tên class `PromotionConfig`. Bean `discountPolicy` của configuration do selector chọn có thể được resolve.

**`total200 = 180`**: `BusinessConfig` được import; Spring inject `CatalogRepository` và `DiscountPolicy` vào factory method. Giá 200 giảm 10% thành 180. Không cần `BusinessConfig` gọi trực tiếp method của `RepositoryConfig` hay `PromotionConfig`.

**`summary = catalog:10%`**: instance `CheckoutService` giữ chính hai dependency đã được BeanFactory chọn; record method trả chuỗi kết hợp thông tin từ repository và discount policy.

**`probe = ok`**: `HealthProbe` là regular class không có `@Component`. Nó tồn tại vì được **liệt kê tường minh trong `@Import`**, không phải nhờ quét package.

**`unscannedCandidates = 0`**: `UnscannedHelper` tuy có `@Component` nhưng không được scan/import. Đánh dấu stereotype trên source không tự đưa class thành bean.

**`sameRepository = true`**: repository có singleton scope mặc định trong context, nên bean lấy trực tiếp và reference mà `CheckoutService` nhận đều là cùng managed instance.

### 8.5. Bốn thay đổi nhỏ để luyện tập

**Thử A:** Xóa `RepositoryConfig.class` khỏi `@Import`. Nếu không có nguồn registration khác, `BusinessConfig.checkoutService(...)` không resolve được `CatalogRepository`. Context thường thất bại khi refresh do dependency bắt buộc không có; không thể tiếp tục đến stdout bình thường.

**Thử B:** Xóa `PromotionSelector.class` khỏi `@Import` nhưng không import `PromotionConfig` trực tiếp. `DiscountPolicy` không còn bean; tạo `CheckoutService` sẽ thất bại.

**Thử C:** Thay selector bằng `PromotionConfig.class` trong danh sách `@Import`. Output vẫn giữ nguyên vì bean `DiscountPolicy` được đăng ký trực tiếp từ một cấu hình thay vì thông qua selector.

**Thử D:** Thêm `UnscannedHelper.class` vào `@Import`. Trong context mới, số lượng tên bean kiểu `UnscannedHelper` sẽ trở thành 1 (nếu không có một đường registration khác tạo thêm). Đây là bằng chứng `@Import` cho phép đăng ký một regular component cụ thể mà không phải mở component scan.

## 9. `@Import` trong cấu hình nhiều module và các cấp truy cập

Trong dự án nhiều Gradle/Maven modules, một module có thể công bố configuration class như một **điểm vào công khai**:

```text
order-app
  -> @Import({OrdersModuleConfig.class, PaymentsModuleConfig.class})

orders-module
  -> OrdersModuleConfig (công bố các @Bean cần thiết)
  -> internal package (không cần scan toàn bộ)

payments-module
  -> PaymentsModuleConfig (công bố payment beans)
  -> internal package (không cần scan toàn bộ)
```

### 9.1. Module phải có trên runtime classpath

`@Import(PaymentsModuleConfig.class)` là một tham chiếu Java `Class<?>`. Build project phải có dependency tới module chứa type này. Nếu không compile được class hoặc module vắng khỏi runtime classpath, Spring không thể tự “tìm module ở đâu đó” chỉ từ tên annotation.

Ví dụ Gradle multi-project:

```groovy
dependencies {
    implementation project(':orders-module')
    implementation project(':payments-module')
}
```

Đây là đoạn minh họa cho build có hai subprojects đã được khai báo. Dependency đảm bảo classpath phù hợp; `@Import`/các cơ chế khác mới quyết định bean definitions nào tham gia container.

### 9.2. Không expose quá nhiều bean nội bộ

Một module library có thể công bố một `@Configuration` chứa các `@Bean` methods cho những services public, trong khi các implementation class private/internal không gắn stereotype hoặc không được scan rộng. Nhờ đó application biết entry-point cấu hình nhưng không cần biết tất cả implementation types.

Nếu imported config tự quét package nội bộ bằng `@ComponentScan`, phạm vi thực tế vẫn có thể rộng. Hãy xem composition root, import graph và filters để tránh đưa nhầm bean, profiles/test helpers hoặc alternate adapters vào ứng dụng.

### 9.3. Scope và vòng đời vẫn quyết định bởi BeanFactory

Import không thay đổi mặc định singleton của các `@Bean` methods, không tự kích hoạt lazy initialization, không tự tạo proxy AOP hoặc bật transaction. Nếu bean `A` được import và cần bean `B`, quan hệ phải được DI resolution đáp ứng đúng như mọi bean trong container. Cấu hình sẽ thất bại nếu dependency bắt buộc thiếu hoặc nếu có nhiều ứng viên mà không có một lựa chọn rõ.

### 9.4. Java Platform Module System (JPMS)

Nếu chạy theo `module-info.java` thay vì classpath thông thường, phản chiếu (reflection), constructor access hoặc CGLIB configuration enhancement có thể đòi `exports`/`opens` phù hợp. Lỗi `InaccessibleObjectException` khi instantiate một bean được import **khác** với tình huống bean definition không được nhập. Phân biệt việc import thành công với việc tạo bean thất bại.

## 10. Import có điều kiện và profiles

Một configuration class được nhập có thể mang `@Profile` hoặc `@Conditional`:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevStorageConfig {

    @Bean
    Storage storage() {
        return new InMemoryStorage();
    }
}
```

Đây là đoạn minh họa cần định nghĩa `Storage`, `InMemoryStorage` và import `@Profile`. Nếu class được nhập nhưng profile `dev` không active, Spring có thể bỏ qua bean definitions của class theo quy tắc profile. `@Import` **không ép** mọi bean bên trong xuất hiện bất chấp các conditions.

Với một tập cấu hình cố định, cấu hình điều kiện trực tiếp trên imported configuration thường đơn giản hơn tự viết `ImportSelector`. Selector hợp lý khi cần đọc metadata annotation tùy chỉnh, chọn nhiều module implementation hoặc xây library/framework reusable.

### 10.1. `@Import` không xác lập thứ tự khởi tạo

`@Import({AConfig.class, BConfig.class})` không có nghĩa “hãy khởi tạo tất cả beans A rồi tới B”. BeanFactory vẫn tạo beans dựa trên dependency graph, scopes, lazy flags và lifecycle rules. Nếu service trong B cần repository của A, khai báo dependency bằng tham số `@Bean` hoặc constructor; nếu chỉ có side-effect order requirement, xem `@DependsOn` trong tình huống phù hợp.

### 10.2. Không nhầm `@Conditional` với exception handling

Nếu một imported bean không thỏa `@Conditional`, nó có thể không được đăng ký. Nếu một bean khác đang bắt buộc inject nó, container vẫn có thể báo lỗi thiếu dependency. `@Import` không tự cung cấp fallback; muốn optional module, bạn phải thiết kế `Optional<T>`, `ObjectProvider<T>`, conditional consumer bean hoặc fallback configuration phù hợp.

## 11. `@ImportResource`, XML và annotation `@Enable...`

### 11.1. Nhập bean definitions từ XML

`@ImportResource` hỗ trợ khai báo đường dẫn đến XML hoặc nguồn bean definition tương thích theo cơ chế tương ứng:

```java
@Configuration
@ImportResource("classpath:/legacy-services.xml")
class LegacyBridgeConfig {
}
```

Đây là đoạn minh họa, cần file `legacy-services.xml` hợp lệ và import `org.springframework.context.annotation.ImportResource`. **Không viết `@Import("classpath:/legacy-services.xml")`**, bởi `@Import` nhận class tokens, không nhận đường dẫn string resource.

### 11.2. Các annotation `@Enable...` thường dùng `@Import`

Trong nhiều extension của Spring, một annotation cấp cao bật hành vi bằng một hoặc nhiều imported configurations/selectors/registrars. Ví dụ `@EnableTransactionManagement`, `@EnableCaching` và `@EnableAsync` liên quan những infrastructure configurations khác nhau. Khi thấy một annotation `@EnableXxx`, có thể kiểm tra metadata `@Import` hoặc implementation extension để hiểu các bean definitions hạ tầng được kích hoạt.

**Điều này không có nghĩa** `@Import` tự mở transactions hoặc caching. Các annotation `@Enable...`, beans/aspects, proxies và điều kiện tương ứng mới phối hợp tạo hành vi.

### 11.3. `@Import` trên custom annotation

`@Import` cũng được hỗ trợ như một meta-annotation. Có thể định nghĩa:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(PaymentsModuleConfig.class)
public @interface EnablePayments {
}
```

Đây là đoạn minh họa: cần imports từ `java.lang.annotation`, `@Import` và một `PaymentsModuleConfig` tồn tại. Consumer chỉ viết:

```java
@Configuration
@EnablePayments
class AppConfig {
}
```

Cách làm này tạo một **public API dạng annotation** cho module. Nếu chỉ có một điểm dùng nội bộ, `@Import(PaymentsModuleConfig.class)` trực tiếp có thể ít ceremony hơn.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` với bean tưởng đã import | Imported config không được xử lý, bị `@Profile`/`@Conditional` bỏ qua hoặc không có `@Bean` phù hợp | Kiểm tra entry-point context, import graph, profiles, conditions |
| `ClassNotFoundException`/compile error cho config được import | Module dependency/classpath sai | Kiểm tra build/runtime dependencies, class/package names |
| Imported config có mặt nhưng service tạo thất bại | Factory method cần dependency mà context không có | Xem chữ ký `@Bean`, qualifier và nguồn bean definition |
| Hai `@Bean` methods của hai configs trùng tên `service` | Bean names xung đột hoặc bị override | Đặt tên tường minh khác nhau, rà soát module ownership |
| Có nhiều bean cùng type sau khi import module thứ hai | Dependency đơn không thể chọn ứng viên duy nhất | Dùng `@Qualifier`/`@Primary` hoặc thiết kế injection tập hợp |
| `@Import(SomeClass.class)` không kéo toàn bộ package | `@Import` đăng ký class cụ thể; không scan package | Dùng `@ComponentScan` nếu thực sự muốn quét nhóm class |
| `@Component` không tự xuất hiện khi thiếu scan | Chưa import hoặc scan component | Import class cụ thể, hoặc bật component scanning đúng root |
| Dùng `@Import("config.xml")` bị lỗi cú pháp | `@Import` yêu cầu `Class<?>` | Dùng `@ImportResource` cho XML |
| Selector không nhập được class | `selectImports` trả bean name thay vì FQ class name | Trả tên class đầy đủ (`SomeConfig.class.getName()`) |
| Conditional imported config bị bỏ qua | Profile/condition không phù hợp | Kiểm tra active profile và `@Conditional` |
| Dùng `@Import` rồi chờ A tạo trước B theo thứ tự mảng | Nhầm import order với dependency order | Dùng tham số factory/constructor, `@DependsOn` khi phù hợp |
| Registrar tạo bean name trùng | Registrations đang tranh một registry key | Kiểm tra registry name, generation policy, duplication |
| Registry post-processor được đăng ký sai giai đoạn | Lạm dụng `ImportBeanDefinitionRegistrar` cho `BeanDefinitionRegistryPostProcessor` | Dùng lifecycle extension point đúng theo tài liệu Spring |
| Gọi `otherConfig.bean()` tạo instance ngoài quản lý | Gọi method Java trực tiếp, đặc biệt lite `@Configuration` | Truyền dependency qua factory-method parameters |
| Classpath chứa module nhưng bean vắng mặt | JAR hiện diện không đồng nghĩa bean được import/scan | Import configuration entry point, scan đúng package hoặc auto-config |
| Test module A chạy, app thực không có bean A | Hai contexts có entry-points/import graphs khác nhau | Kiểm tra từng context và cấu hình test thực sự dùng |

### 12.1. Quy trình debug thực dụng

**Bước 1 — Kiểm tra configuration entry point.** Một class `@Configuration` có `@Import` phải thực sự được đăng ký, quét hoặc nhập bởi một configuration khác. Annotation nằm trên một class không bao giờ được Spring biết đến sẽ không có tác dụng.

**Bước 2 — Vẽ import graph.** Ghi rõ từ `AppConfig` đi tới class cấu hình nào, selector trả class nào, registrar có tạo definitions nào. Phân biệt imports trực tiếp và imports bắc cầu.

**Bước 3 — Kiểm tra bean type/name.** Nếu context chạy được:

```java
String[] names = context.getBeanNamesForType(CheckoutService.class);
System.out.println(java.util.Arrays.toString(names));
```

Đây là đoạn minh họa khi `context` và `CheckoutService` có sẵn. Tránh đoán tên imported configuration class: bean names được tạo bởi configuration registration mechanism, có thể khác component scan naming.

**Bước 4 — Kiểm tra điều kiện và lifecycle.** Bean có thể bị profile/condition loại trước khi đăng ký, hoặc được đăng ký rồi lỗi khi tạo. Đọc root cause của `BeanCreationException`/`UnsatisfiedDependencyException` để xác định giai đoạn.

**Bước 5 — Kiểm tra xung đột.** Nếu thêm module làm context lỗi, tìm những bean names trùng hoặc interface injection trước đây chỉ có một bean nhưng nay có hai. Đừng bật bean definition overriding toàn cục chỉ để che xung đột chưa hiểu.

**Bước 6 — Dùng test context nhỏ.** Như mục 8, đăng ký chỉ `AppConfig.class` và xác minh từng bean theo type. Dùng điều kiện/profiles giống môi trường mục tiêu khi behavior phụ thuộc chúng.

## 13. Bài tập thực hành kèm đáp án

### Bài 1 — Một hay hai configuration classes khi khởi động?

Cho `@Configuration @Import(StorageConfig.class) class AppConfig` và `@Configuration class StorageConfig` có một `@Bean Storage storage()`. Khi khởi tạo context bằng `new AnnotationConfigApplicationContext(AppConfig.class)`, có cần truyền thêm `StorageConfig.class` không?

**Đáp án:** Không. `AppConfig` đã import `StorageConfig`. Spring xử lý bean definitions do `StorageConfig` cung cấp.

### Bài 2 — Import một regular class

Một class `HealthCheck` không có `@Component`, có public no-arg constructor. `@Configuration @Import(HealthCheck.class) class AppConfig` được đăng ký. Có thể lookup `HealthCheck` theo type không?

**Đáp án:** Có, khi quá trình import và bean creation thành công. Spring 6.2 hỗ trợ import regular component classes mà không bắt buộc có component scanner.

### Bài 3 — Component bên cạnh class được import

`EmailGateway` và `SmsGateway` ở cùng package; chỉ có `@Import(EmailGateway.class)`, không có scanner. `SmsGateway` có trở thành bean vì nằm cùng package không?

**Đáp án:** Không qua import đó. `@Import` đăng ký những class/cấu hình nêu cụ thể, không quét sibling classes.

### Bài 4 — Phụ thuộc xuyên config

`ServiceConfig` có `@Bean OrderService orderService(OrderRepository repository)`, còn `RepositoryConfig` có `@Bean OrderRepository orderRepository()`. Cần gọi method `repositoryConfig.orderRepository()` trực tiếp không?

**Đáp án:** Không. Import/register cả hai config trong cùng context và để Spring giải quyết tham số `OrderRepository` bằng BeanFactory.

### Bài 5 — ImportSelector trả gì?

`ImportSelector.selectImports(...)` trả `new String[]{"paymentService"}`, trong đó `paymentService` chỉ là bean name, không phải class FQCN. Có đúng không?

**Đáp án:** Không. Selector cần trả các tên class import candidates hợp lệ; ví dụ `new String[]{PaymentsConfig.class.getName()}`.

### Bài 6 — @Bean trùng tên

Module A và B đều khai báo `@Bean PaymentClient client()`, có import cả hai. Điều gì đáng lo?

**Đáp án:** Hai bean definitions mặc định cùng tên `client`. Tùy chính sách registry, có thể đụng tên/ghi đè hoặc khởi tạo sai mong đợi. Đặt tên có chủ đích và tránh đăng ký chồng chéo.

### Bài 7 — Profile chưa active

`@Import(DevMailConfig.class)` nhưng `DevMailConfig` có `@Profile("dev")`, môi trường hiện tại chỉ active profile `prod`. Có chắc các `@Bean` của config vẫn tồn tại không?

**Đáp án:** Không. `@Profile` có thể khiến config bị bỏ qua. Import không vô hiệu hóa profile conditions.

### Bài 8 — XML config

Một ứng dụng legacy còn file `services.xml`. Dùng `@Import(services.xml)` hay `@ImportResource("classpath:/services.xml")`?

**Đáp án:** Dùng `@ImportResource` cho resource XML. `@Import` dành cho Java class candidates/selectors/registrars.

### Bài 9 — Import trùng để tạo hai bean

Hai cấu hình cùng import một `StorageConfig` chứa singleton `StorageClient`. Có thể dùng điều đó để tạo hai `StorageClient` độc lập không?

**Đáp án:** Không nên và không thể dựa vào đó. Spring xử lý configuration candidates trong registry; muốn hai clients cần hai bean definitions khác nhau (ví dụ hai `@Bean` methods với tên/parameters khác).

### Bài 10 — Thử thay selector trong demo

Trong mục 8, xóa `PromotionSelector.class` và thêm `PromotionConfig.class` vào `@Import`. Đầu ra `discount = 10%` và `total200 = 180` có thay đổi không?

**Đáp án:** Không trong cấu hình demo, vì cả hai đường đều nhập `PromotionConfig`. Selector chỉ thêm logic lựa chọn, không thay đổi bean contract của `DiscountPolicy`.

### Bài 11 — Registrar hay @Bean?

Một application cần chính xác hai beans `Clock` và `ReceiptFormatter` với implementations cố định. Có nhất thiết viết `ImportBeanDefinitionRegistrar`?

**Đáp án:** Không. Một `@Configuration` với hai `@Bean` methods rõ ràng đơn giản, minh bạch hơn. Registrar nên dành cho hạ tầng tạo definitions dựa trên metadata/quy tắc động.

### Bài 12 — Thay component scanning bằng module API

Một library có 50 implementation classes, app chỉ cần 3 beans public mà library config đã công bố. Nên mở rộng `@ComponentScan` sang toàn bộ package nội bộ hay nhập configuration public?

**Đáp án:** Khi library đã thiết kế entry-point đúng, nhập configuration public thường rõ ranh giới hơn. Tuy nhiên phải kiểm tra configuration đó có quét tiếp package nội bộ hay import auto-config nào khác không.

## 14. Checklist thiết kế `@Import` an toàn

- Cấu hình root/entry-point có **thực sự được context đăng ký** chưa?
- Có thể liệt kê rõ những module configurations cần tham gia không? Nếu có, `@Import({AConfig.class, BConfig.class})` thường đủ.
- Imported class là `@Configuration`, regular component, selector hay registrar? Đừng nhầm cơ chế mỗi loại.
- Các `@Bean` methods của nhiều configurations có **trùng bean name/type** không?
- Dependency xuyên config đã được thể hiện bằng factory-method parameters hoặc constructors chưa?
- Imported configuration có `@ComponentScan`, `@Import` bắc cầu, `@Profile`, `@Conditional` hoặc lifecycle extension đáng chú ý không?
- Nếu dùng selector, đã trả **tên class đầy đủ** và kiểm tra các điều kiện/annotation attributes hợp lệ chưa?
- Nếu dùng registrar, đã kiểm soát bean names và không vi phạm hạn chế lifecycle của `BeanDefinitionRegistryPostProcessor` chưa?
- Có đang cần XML? Nếu có, dùng `@ImportResource` thay vì ép resource vào `@Import`.
- Module thực sự có trên runtime classpath không? Với JPMS, đã xử lý access/reflection khi cần chưa?
- Test integration tạo context từ **một composition root** đã kiểm tra được những bean được import và những bean cố ý không đăng ký chưa?

## 15. Tổng kết

`@Import` là công cụ quan trọng để **ghép Java-based configurations một cách tường minh** trong Spring Core Container. Bạn có thể nhập một/một số `@Configuration` classes, regular component classes hoặc các extension points `ImportSelector` và `ImportBeanDefinitionRegistrar`. Spring xử lý metadata/import graph để đăng ký bean definitions; BeanFactory vẫn quyết định dependency injection, scope và lifecycle.

Nên dùng `@Import` khi muốn composition root rõ ràng, phân mô-đun và chỉ kích hoạt những cấu hình cần thiết. Với nhiều component ứng dụng cần tự phát hiện theo package, `@ComponentScan` có thể phù hợp hơn. Với cấu hình XML, chọn `@ImportResource`. Khi bean A cần bean B từ config khác, ưu tiên **method-parameter injection** thay vì gọi `@Bean` method trực tiếp và phụ thuộc vào proxy mode.

**Quy tắc ghi nhớ:** import chọn *nguồn bean definitions*, không tự quét package, không bảo đảm bean creation order và không vượt qua profile/conditional/dependency rules. Một đồ thị import gọn và có test sẽ dễ bảo trì hơn việc scan thật rộng rồi xử lý các bean ngoài ý muốn.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework 6.2 — `@ImportResource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportResource.html).
- [Spring Framework — Creating an ApplicationContext with Annotation-based Config](https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html).
