# Đăng ký lớp bằng `@Component` và các stereotype chuyên biệt trong Spring Core Container

## 1. Từ Java object đến Spring-managed bean

Trong Java thuần, tạo một đối tượng thường bắt đầu từ `new`:

```java
GreetingService service = new GreetingService(repository);
```

Người viết code phải quyết định khi nào khởi tạo, truyền dependency nào, giữ instance ở đâu và tự quản lý vòng đời của nó. Spring IoC Container chuyển trách nhiệm tạo và kết nối nhiều đối tượng sang container thông qua **bean definitions**. Một cách đăng ký bean là khai báo phương thức `@Bean`; cách khác là **đánh dấu lớp bằng stereotype annotation** và cho Spring quét classpath để phát hiện lớp đó.

Ví dụ:

```java
import org.springframework.stereotype.Component;

@Component
class TextFormatter {
    String format(String text) {
        return "[" + text + "]";
    }
}
```

Khi Spring quét đúng package chứa `TextFormatter`, lớp này có thể trở thành một bean với tên mặc định `textFormatter`. Sau đó bean khác có thể nhận `TextFormatter` qua constructor injection. **Annotation trên class không tự làm đối tượng xuất hiện trong container**: phải có một cơ chế đăng ký, ví dụ `@ComponentScan` hoặc component scanning do Spring Boot cấu hình.

Đặt tên đúng cho các vai trò rất quan trọng:

- **Class**: định nghĩa kiểu và hành vi trong mã nguồn Java.
- **Bean definition**: metadata mà container dùng để quản lý bean (class/factory, scope, tên, qualifiers, v.v.).
- **Spring bean**: đối tượng do Spring container tạo, cấu hình và quản lý theo bean definition.
- **Stereotype annotation**: nhãn trên lớp giúp nhận diện vai trò kiến trúc và, khi được scan, đăng ký bean.

Mục tiêu bài này là sử dụng đúng `@Component` và các chuyên biệt `@Service`, `@Repository`, `@Controller`, `@Configuration`; hiểu đăng ký qua scanning, tên bean, constructor injection, custom stereotype và những lỗi thường gặp.

## 2. `@Component` và các stereotype chuyên biệt

Ở góc nhìn **đăng ký bean**, `@Component` là stereotype tổng quát; các stereotype chuyên biệt phân loại vai trò của class nhưng đều được component scanner mặc định nhận diện qua meta-annotation `@Component`. Chọn annotation theo **trách nhiệm thực tế**, vì annotation không tự khởi động các cơ chế của layer.

| Annotation | Vai trò nên dùng | Điều kiện không được suy diễn |
| --- | --- | --- |
| `@Component` | Helper, adapter, formatter hoặc component kỹ thuật chung | Không phải mọi Java object đều cần làm bean |
| `@Service` | Business use case và điều phối nghiệp vụ | Không tự mở transaction, cache, retry hoặc AOP |
| `@Repository` | Repository/DAO, truy cập dữ liệu | Exception translation cần post-processor và translator phù hợp; `JdbcTemplate` có đường dịch lỗi riêng |
| `@Controller` | Presentation/web controller | Chưa có HTTP endpoint nếu thiếu web stack, handler mapping và route |
| `@Configuration` | Java configuration, thường chứa `@Bean` methods | Có semantics cấu hình riêng, gồm lựa chọn `proxyBeanMethods` |

Một bean utility có thể cần dependency injection hoặc vòng đời của Spring:

```java
import org.springframework.stereotype.Component;

@Component
class SlugGenerator {
    String slug(String text) {
        return text.trim().toLowerCase(java.util.Locale.ROOT)
                .replace(' ', '-');
    }
}
```

`SlugGenerator` được scanner phát hiện khi nằm trong đúng base package. Nếu chỉ cần hàm thuần, một utility Java không thuộc container vẫn có thể phù hợp.

`@Service` biểu đạt nghiệp vụ và hỗ trợ constructor injection như component khác:

```java
@Service
class CheckoutService {
    private final PaymentRepository payments;

    CheckoutService(PaymentRepository payments) {
        this.payments = payments;
    }

    String summary() { return payments.status(); }
}
```

Đây là snippet minh họa, giả định có interface/class `PaymentRepository` và bean tương ứng; với một constructor, Spring không bắt buộc `@Autowired` trên constructor. `@Service` không tự thiết lập giao dịch.

Tương tự, `@Repository` có thể đánh dấu bean cần được hạ tầng persistence exception translation xử lý, nhưng không tự đổi mọi ngoại lệ. `@Controller` có thể được scan vào một `ApplicationContext` không có HTTP server; chỉ khi Spring MVC/WebFlux phù hợp chạy mới có xử lý request. `@RestController` ghép `@Controller` và `@ResponseBody` trong Spring Web.

`@Configuration(proxyBeanMethods = false)` phù hợp khi các factory methods `@Bean` hoạt động độc lập. Nếu muốn gọi trực tiếp một `@Bean` method khác mà vẫn nhận semantics singleton của container, cần cân nhắc full configuration. Ví dụ chạy được ở mục 5 chứng minh năm stereotype, cách inject, tên bean và custom stereotype trong cùng một context.

## 3. Cơ chế quét và đăng ký component

Component scanning hoạt động theo lược đồ:

```text
Classpath/package được yêu cầu quét
               |
               v
Spring đọc metadata của các class ứng viên
               |
               v
Áp dụng stereotype mặc định và include/exclude filters
               |
               v
Tạo và đăng ký bean definitions cho ứng viên hợp lệ
               |
               v
Khi container cần/khởi tạo bean:
resolve dependency -> tạo instance -> inject -> lifecycle
```

Quan trọng: **quét class và tạo instance là hai giai đoạn khác nhau**. Scanner đăng ký bean definition; thời điểm instance được tạo còn phụ thuộc scope, lazy flag, dependency và quy trình khởi tạo context.

Mặc định, component scan phát hiện các class mang `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration`, hoặc annotation tự định nghĩa được meta-annotated bằng `@Component`. Có thể tùy chỉnh bộ lọc ứng viên với `includeFilters` và `excludeFilters` nếu cần.

### 3.1. Bật scan bằng `@ComponentScan`

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders")
class OrderConfiguration {
}
```

Đây là đoạn minh họa. Khi đăng ký `OrderConfiguration` với `AnnotationConfigApplicationContext`, Spring sẽ quét package `com.example.orders` và các subpackage của nó để tìm component candidates.

Biến thể an toàn hơn khi đổi tên package:

```java
@Configuration
@ComponentScan(basePackageClasses = OrderApplication.class)
class OrderConfiguration {
}
```

Ở đây `OrderApplication.class` chỉ đóng vai trò **type-safe marker** để xác định package; class marker bản thân không cần mang stereotype. Cần có `OrderApplication` trong package muốn quét.

Nếu để `@ComponentScan` không khai báo package, Spring mặc định sử dụng package của **configuration class khai báo annotation**, cùng các subpackage. Việc đặt class cấu hình trong package hẹp hoặc không đúng chỗ sẽ khiến component nằm ở package ngoài phạm vi bị bỏ sót.

### 3.2. Spring Boot và quét package mặc định

Trong dự án Spring Boot phổ biến:

```java
@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Đây là **đoạn minh họa ứng dụng Boot**, không phải dự án Spring Context thuần ở mục 5. `@SpringBootApplication` có tính năng tương đương sự kết hợp của `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Mặc định, component scanning bắt đầu từ package đặt class application. Vì vậy hãy đặt application class ở **root package** chứa các package con cần scan, ví dụ:

```text
com.example.orders/
├── OrderApplication.java
├── api/OrderController.java
├── service/OrderService.java
└── persistence/OrderRepository.java
```

Một class ở package ngang cấp hoặc ở package cha **ngoài** vùng scan có thể không được phát hiện, dù đã gắn `@Service`.

### 3.3. Candidate không đồng nghĩa mọi class đều được tạo

- Một **interface** có gắn stereotype không có constructor cụ thể để tự tạo instance; nên đánh dấu stereotype trên **implementation** muốn đăng ký. Các annotation/repository mechanisms đặc thù, ví dụ Spring Data repositories, có quy trình tạo proxy riêng.
- Một class **abstract** thường không trở thành bean thông thường có thể khởi tạo trực tiếp chỉ nhờ `@Component`. Nếu cần đăng ký một bean, cung cấp concrete implementation hoặc factory phù hợp.
- **Nested non-static class** mang implicit outer-instance dependency; không nên trông đợi scanner đăng ký như một independent component. Với nested class được scan, dùng `static` nếu thực sự cần.
- **Bean có điều kiện** (ví dụ profile không active) có thể bị bỏ qua; kiểu class có trên classpath chưa đủ để khẳng định bean đã có trong container.
- Một class có stereotype nhưng thiếu dependency ở constructor vẫn có thể được đăng ký thành bean definition rồi thất bại khi khởi tạo.

## 4. Đặt tên bean và phạm vi sử dụng

### 4.1. Tên mặc định của component

Spring thường dùng `AnnotationBeanNameGenerator` cho bean phát hiện qua scan. Nếu không đặt tên tường minh, tên mặc định được suy ra bằng cách bỏ viết hoa ký tự đầu của **tên class ngắn** theo quy tắc JavaBeans:

| Khai báo | Tên bean thông thường |
| --- | --- |
| `@Component class TextFormatter` | `textFormatter` |
| `@Service class CheckoutService` | `checkoutService` |
| `@Repository class OrderRepositoryImpl` | `orderRepositoryImpl` |
| `@Controller class OrderController` | `orderController` |

Có ngoại lệ với tên class bắt đầu bằng nhiều ký tự viết hoa (ví dụ `URLService`), nên đừng coi quy tắc mặc định đơn giản là luôn lowercase ký tự đầu tiên.

Có thể đặt tên rõ ràng:

```java
@Service("checkoutWorkflow")
class CheckoutService {
    // ...
}
```

Khi đó bean name mong đợi là `checkoutWorkflow`, không phải `checkoutService`. Tên bean cần duy nhất trong một container; hai component dùng cùng tên có thể gây lỗi đăng ký xung đột. Đừng giải quyết xung đột bằng cách âm thầm bật bean definition overriding nếu chưa hiểu tại sao hai bean có cùng tên.

### 4.2. Bean name, bean type và qualifier

Tên bean phục vụ nhận diện trong container; type phục vụ autowiring theo kiểu. Nếu constructor cần một interface và có hai bean implementation phù hợp, `@Service`/`@Repository` không tự chọn đúng một implementation. Có thể dùng `@Qualifier`, `@Primary` hoặc thiết kế lại dependency.

```java
// Đoạn minh họa: hai implementation đều được đăng ký.
@Service("localSender")
class LocalSender implements Sender { }

@Service("remoteSender")
class RemoteSender implements Sender { }

// Tại constructor của một bean khác:
NotificationService(@Qualifier("remoteSender") Sender sender) {
    this.sender = sender;
}
```

Đây không phải đoạn Java độc lập: cần định nghĩa `Sender`, `NotificationService` và imports. `@Qualifier("remoteSender")` hướng Spring đến ứng viên có qualifier hoặc bean name phù hợp; cụm này **không liên quan đến việc hai class có cùng stereotype**.

### 4.3. Scope và lifecycle

Component scan không cố định scope là prototype. Mặc định, một Spring bean được đăng ký bằng `@Component`, `@Service`, `@Repository` hoặc `@Controller` có scope **singleton trong phạm vi container**. Điều đó nghĩa là Spring thường cung cấp cùng một instance cho các lần lookup qua container:

```java
@Service
@Scope("prototype")
class ReportTask {
    // Mỗi lần container resolve prototype bean sẽ tạo instance mới.
}
```

Đây là đoạn minh họa; cần import `org.springframework.context.annotation.Scope`. Dùng scope phù hợp với lifecycle chứ không chọn prototype chỉ vì một method cần chạy nhiều lần. Với singleton, Spring có thể tạo instance sớm lúc refresh context; `@Lazy` thay đổi chính sách eager/lazy khi thích hợp, nhưng dependency khác cần bean đó vẫn có thể kích hoạt khởi tạo.

Bean được Spring quản lý có thể nhận dependency injection, các post-processor, initialization/destruction callbacks và proxy theo cấu hình. **Một object tạo bằng `new` không tự trở thành cùng bean mà scanner đăng ký**, dù class của nó có `@Component`.

## 5. Dự án Java 17+ chạy được: đăng ký năm loại stereotype

Ví dụ dưới đây dùng **Spring Framework 6.2.18**, không cần Spring Boot hoặc servlet container. Mọi file Java đều nằm trong cùng một package. Để giữ ví dụ dễ sao chép, các class không `public` được đặt chung với main class trong một file; compiler Java vẫn tạo từng `.class` độc lập và component scanner phát hiện các concrete top-level class phù hợp.

### 5.1. Cấu trúc tệp

```text
component-stereotypes-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/components/
    └── ComponentStereotypesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'component-stereotypes-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.components.ComponentStereotypesDemo'
}
```

`spring-context` kéo theo các module Spring Beans/Core cần thiết. Ví dụ không dùng servlet, HTTP hoặc database; `@Controller` và `@Repository` ở đây chỉ thể hiện vai trò và hành vi quét.

### 5.2. Mã Java hoàn chỉnh

`src/main/java/demo/components/ComponentStereotypesDemo.java`:

```java
package demo.components;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

public class ComponentStereotypesDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            System.out.println("component = " +
                    context.containsBean("textDecorator"));
            System.out.println("service = " +
                    context.containsBean("greetingService"));
            System.out.println("repository = " +
                    context.containsBean("inMemoryGreetingRepository"));
            System.out.println("controller = " +
                    context.containsBean("greetingController"));
            System.out.println("configuration = " +
                    context.containsBean("demoConfig"));
            System.out.println("custom = " +
                    context.containsBean("featureInfo"));

            GreetingController controller =
                    context.getBean(GreetingController.class);
            System.out.println("greeting = " + controller.render());

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);
            System.out.println("sameService = " + (first == second));
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)
class DemoConfig {
}

interface GreetingRepository {
    String load();
}

@Repository
class InMemoryGreetingRepository implements GreetingRepository {

    @Override
    public String load() {
        return "Xin chào từ repository";
    }
}

@Service
class GreetingService {

    private final GreetingRepository repository;

    GreetingService(GreetingRepository repository) {
        this.repository = repository;
    }

    String greeting() {
        return repository.load() + " qua service";
    }
}

@Component
class TextDecorator {

    String decorate(String input) {
        return "[" + input + "]";
    }
}

@Controller
class GreetingController {

    private final GreetingService service;
    private final TextDecorator decorator;

    GreetingController(GreetingService service, TextDecorator decorator) {
        this.service = service;
        this.decorator = decorator;
    }

    String render() {
        return decorator.decorate(service.greeting());
    }
}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
@interface Feature {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}

@Feature("featureInfo")
class FeatureInfo {
}
```

Trong một file Java, chỉ `ComponentStereotypesDemo` là top-level `public`; các class và annotation còn lại có package-private visibility, hợp lệ vì nằm trong cùng package và được trình biên dịch tạo thành các `.class` độc lập. Constructor của những class được scanner tạo bean ở đây có thể là package-private; Spring có thể truy cập phù hợp trong ứng dụng classpath thông thường. Khi dùng Java Platform Module System với `module-info.java`, cần xét riêng cấu hình `opens` cho reflection; ví dụ này không sử dụng module descriptor.

### 5.3. Lệnh chạy và output

Dùng JDK 17 trở lên và bản Gradle tương thích; tại thư mục dự án:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, sử dụng `./gradlew run --quiet` trên Linux/macOS hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell. Các dòng do chương trình in:

```text
component = true
service = true
repository = true
controller = true
configuration = true
custom = true
greeting = [Xin chào từ repository qua service]
sameService = true
```

`System.out.println` chỉ in những dòng trên; log của Spring hoặc Gradle, nếu môi trường cấu hình thêm logging, không phải output nghiệp vụ của chương trình.

### 5.4. Đọc cơ chế từng bước

1. `new AnnotationConfigApplicationContext(DemoConfig.class)` đăng ký configuration class và refresh context.
2. `@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)` yêu cầu scan package `demo.components`.
3. Spring phát hiện `InMemoryGreetingRepository`, `GreetingService`, `TextDecorator`, `GreetingController` và `FeatureInfo` nhờ các stereotype, đồng thời `DemoConfig` được đăng ký là configuration bean.
4. Container chọn `InMemoryGreetingRepository` để thỏa interface `GreetingRepository` vì ở đây chỉ có một implementation được đăng ký.
5. Container truyền `GreetingRepository` vào `GreetingService`, sau đó `GreetingService` và `TextDecorator` vào `GreetingController` qua constructor. Không cần `@Autowired` vì mỗi class chỉ có một constructor.
6. `@Feature("featureInfo")` được scan vì `@Feature` mang meta-annotation `@Component`. `@AliasFor` chuyển giá trị `value` của `@Feature` sang logical component name, nên bean có tên `featureInfo`.
7. `controller.render()` trả một chuỗi định dạng. Đây là lời gọi Java bình thường đến bean `@Controller`; **không có HTTP request**.
8. `first == second` trả `true` vì `GreetingService` có scope singleton mặc định trong cùng context.

Mỗi dòng output là một kiểm tra hẹp của behavior đã khai báo. Nếu xóa `@ComponentScan` nhưng vẫn đăng ký `DemoConfig`, scanner không còn được cấu hình để tìm các stereotype trong package, các bean như `GreetingService` không được tạo tự động.

## 6. Custom stereotype: mở rộng `@Component` đúng cách

Các dự án lớn thường cần stereotype riêng thể hiện mục đích kiến trúc như `@DomainService`, `@UseCase`, `@InboundAdapter`. Spring hỗ trợ điều này bằng cách **meta-annotate annotation tự định nghĩa với `@Component`**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

Đoạn này minh họa **nội dung file `DomainService.java`**, cần imports như ở mục 5. Annotation `@DomainService` dùng được trên class:

```java
@DomainService("orderUseCase")
public class OrderUseCase {
}
```

Đoạn thứ hai minh họa **file `OrderUseCase.java`** trong package được scan. Bean được đặt tên `orderUseCase` thông qua alias. Các quy tắc:

- `@Target(ElementType.TYPE)` cho phép gắn annotation trên class.
- `@Retention(RetentionPolicy.RUNTIME)` bảo đảm metadata annotation có thể được đọc lúc runtime.
- `@Component` trên annotation tự định nghĩa cho scanner biết đây là stereotype.
- `@AliasFor(annotation = Component.class, attribute = "value")` khai báo **alias tường minh** cho tên bean. Từ Spring 6.1, cách custom stereotype chỉ khai báo `String value()` dựa vào convention cũ đã bị deprecate; dùng `@AliasFor` giúp semantics rõ ràng và bền vững hơn.
- Nếu không cần đặt tên từ custom annotation, có thể chỉ định nghĩa stereotype marker đơn giản, không khai báo thuộc tính `value`; scanner vẫn suy ra tên mặc định từ class.

**Không nên custom quá nhiều stereotype** nếu chúng không mang ý nghĩa rõ ràng. Những nhãn chỉ lặp lại `@Service` bằng tên khác mà không có quy ước nào bổ sung có thể khiến code khó hiểu.

## 7. `@Component` khác `@Bean` như thế nào?

Cả hai đều có thể đăng ký bean nhưng **nguồn định nghĩa** khác nhau:

| Tiêu chí | Stereotype + component scanning | `@Bean` trong configuration |
| --- | --- | --- |
| Nơi khai báo | Trên class | Trên method của configuration class hoặc lớp cấu hình phù hợp |
| Đối tượng thường dùng | Class ứng dụng do team kiểm soát | Class thư viện, đối tượng cần factory logic, object tùy biến |
| Cơ chế đăng ký | Scanner tìm metadata trong package | Configuration processor đọc factory method |
| Bean name mặc định | Từ tên class, ví dụ `paymentService` | Từ tên method, ví dụ `paymentClient` |
| Injection | Có, do Spring container quản lý | Có, do Spring container quản lý |
| Scope mặc định | Singleton | Singleton |
| Có thể kết hợp? | Có | Có |

Ví dụ với class bên thứ ba không thể sửa source:

```java
@Configuration(proxyBeanMethods = false)
class ExternalConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient("endpoint");
    }
}
```

Đây là đoạn minh họa, thiếu định nghĩa `ExternalClient` và imports. `@Bean` dễ sử dụng hơn việc thêm `@Component` vào class thư viện mà bạn không kiểm soát.

Đừng vừa scan một class bằng `@Component` **vừa khai báo một `@Bean` tạo cùng instance/class** mà không có ý định rõ ràng; bạn có thể tạo ra hai bean cùng kiểu và khiến injection đơn bị mơ hồ. Một dự án có thể kết hợp hai cách đăng ký, nhưng mỗi bean cần vai trò, scope và tên có chủ đích.

## 8. Phạm vi scan, exclusions và hiệu năng khởi động

Component scanning xét các class có trên runtime classpath bên trong base package và các subpackage. Class mang `@Service` ở một package ngang cấp hoặc nằm ngoài root sẽ không được tìm thấy bởi lượt scan ấy. Với Spring Boot, `@SpringBootApplication` thường quét từ package đặt application class xuống các nhánh con.

Dùng `@ComponentScan(basePackages = "...")` hoặc `basePackageClasses = Marker.class` để xác định root, giữ phạm vi **đủ nhưng không quá rộng**. Bộ lọc `includeFilters` bổ sung tiêu chí nhận diện; `excludeFilters` loại ứng viên của một lượt scan; `useDefaultFilters=false` tắt quy tắc nhận diện stereotype mặc định. Một bean còn có thể được tạo qua `@Bean`, `@Import` hoặc config khác dù không được scan. Khi mở rộng vùng quét, xác minh classpath, ứng viên, cấu hình có điều kiện và xung đột tên trước khi đưa vào sản phẩm.

## 9. Những lỗi thường gặp

Các lỗi khi dùng stereotype thường nằm ở các pha **đăng ký**, **khởi tạo bean**, hoặc **hạ tầng tích hợp** khác nhau:

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Bean `@Service` không có dù class tồn tại | Runtime classpath, package root, include/exclude, `useDefaultFilters`, profile/condition |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng type, cần lựa chọn rõ qua `@Qualifier`, `@Primary` hoặc collection |
| Hai component khác package gây xung đột | Bean name mặc định giống nhau, explicit name hoặc naming generator |
| `@Repository` không dịch ngoại lệ | Có `PersistenceExceptionTranslationPostProcessor`, translator phù hợp và lời gọi qua proxy hay không |
| Controller có trong context nhưng HTTP trả 404 | MVC/web infrastructure, `DispatcherServlet`, mapping và HTTP path/method |
| `@Service` nhưng method không rollback | `@Transactional`, transaction manager, proxy/call path và self-invocation |
| Đối tượng tạo bằng `new` thiếu `@Autowired` | Object chưa đi qua bean registration và lifecycle của Spring |
| Bean definition có nhưng ứng dụng không khởi động | Constructor/dependency, circular dependency, lỗi factory hoặc cấu hình điều kiện |

**Debug theo thứ tự:** (1) xác minh package và classpath; (2) class configuration có được đăng ký không; (3) kiểm tra annotation/filter/condition; (4) đọc tên và kiểu bean bằng `containsBean`/`getBeanNamesForType`; (5) tìm root cause khởi tạo; (6) kiểm tra web/transaction/persistence hạ tầng phù hợp. Đừng mở scan toàn classpath chỉ để che lỗi dependency hoặc naming.

## 10. Bài tập tự thực hành

### Bài tập 1 — Đổi tên component

Đổi:

```java
@Component
class TextDecorator { /* ... */ }
```

thành:

```java
@Component("messageDecorator")
class TextDecorator { /* ... */ }
```

Trong đoạn kiểm tra thuộc mục 5, thay `containsBean("textDecorator")` thành `containsBean("messageDecorator")`. Hành vi dependency injection theo **type** vẫn có thể hoạt động nếu chỉ có một bean `TextDecorator`; tuy nhiên tên bean mặc định `textDecorator` không còn là tên đăng ký.

### Bài tập 2 — Thay stereotype theo vai trò

Nếu chuyển `GreetingService` từ `@Service` thành `@Component`, chương trình mục 5 còn hoạt động không? **Có**, miễn component vẫn được scan và không có cấu hình bổ sung dựa trên annotation `@Service`. Nhưng code không còn diễn đạt rõ layer nghiệp vụ, và tooling/aspect/filter tùy chỉnh nhắm vào `@Service` có thể thay đổi hành vi.

Nếu chuyển `InMemoryGreetingRepository` từ `@Repository` thành `@Component`, bean vẫn có thể được scan, nhưng metadata repository phục vụ exception translation và quy ước kiến trúc không còn nữa. Đây là lý do không nên thay mọi stereotype bằng `@Component` một cách máy móc.

### Bài tập 3 — Đổi package không quét

Chuyển `TextDecorator` sang package `demo.util` nhưng giữ `@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)` trong package `demo.components`. Dự đoán gì xảy ra? Spring sẽ không scan `demo.util`; khi tạo `GreetingController` sẽ thiếu dependency `TextDecorator`, trừ khi có cấu hình đăng ký bean khác. Hướng sửa là mở rộng đúng phạm vi scan hoặc đưa utility về package được scan.

### Bài tập 4 — Thêm repository thứ hai

Khai báo thêm `@Repository class RemoteGreetingRepository implements GreetingRepository`. Nếu cả hai bean đều hợp lệ và không có primary hoặc qualifier làm rõ lựa chọn, constructor `GreetingService(GreetingRepository repository)` có thể thất bại với `NoUniqueBeanDefinitionException` (thường xuất hiện trong chuỗi lỗi tạo context). Hướng sửa là gắn `@Qualifier` đúng vai trò hoặc lựa chọn primary có chủ đích.

### Bài tập 5 — Custom stereotype

Tạo annotation `@DomainService` theo ví dụ mục 6 rồi đánh dấu `@DomainService("invoiceUseCase")` lên một concrete class trong package được scan. Hãy xác nhận bean name bằng `containsBean("invoiceUseCase")` và giải thích vì sao `@AliasFor` quan trọng trên Spring Framework 6.1+.

### Bài tập 6 — Vòng đời

Gọi hai lần `context.getBean(GreetingService.class)` trên cùng context, rồi so sánh bằng `==`. Vì sao `true`? Vì `GreetingService` là singleton mặc định. Nếu bean được khai báo `@Scope("prototype")` và không bị giữ trong singleton khác, mỗi lời gọi resolve prototype có thể tạo instance khác nhau. Đừng suy luận rằng chỉ đổi scope của một dependency là mọi client đang giữ reference sẽ tự cập nhật nó.

## 11. Checklist trước khi thêm stereotype

- Lớp có **cần** được Spring quản lý không? Nếu có, trách nhiệm của nó thuộc `@Component`, `@Service`, `@Repository` hay `@Controller`?
- Package đã nằm trong đúng phạm vi `@ComponentScan` hoặc default scan của Spring Boot chưa?
- Có nhiều implementation của interface được inject không? Nếu có, selection policy đã rõ chưa?
- Bean name có ý nghĩa, có nguy cơ đụng tên với bean khác không?
- Có cần `@Bean` factory method vì không thể sửa class hoặc cần logic cấu hình không?
- Có phụ thuộc vào cơ chế web, transaction, exception translation, AOP hay scope mà stereotype **một mình không kích hoạt** không?
- Nếu dùng custom stereotype, đã meta-annotate `@Component` và khai báo alias tên bean bằng `@AliasFor` khi cần chưa?

## 12. Ghi nhớ

`@Component` và các stereotype chuyên biệt giúp Spring **phát hiện class và đăng ký bean definition qua component scanning**. `@Service` biểu đạt nghiệp vụ, `@Repository` biểu đạt truy cập dữ liệu, `@Controller` biểu đạt tầng web, còn `@Configuration` là component với semantics cấu hình. Custom stereotype có thể được tạo bằng meta-annotation `@Component`; khi muốn đặt bean name qua thuộc tính riêng, dùng `@AliasFor` tường minh. Dù sử dụng stereotype nào, bean chỉ có mặt khi **được scan hoặc được đăng ký bằng cơ chế phù hợp**; các annotation vai trò không tự bật web server, transaction hay exception translation.

### Tài liệu chính thức

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html).
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Framework — DAO Support and `@Repository`](https://docs.spring.io/spring-framework/reference/data-access/dao.html).
- [Spring Framework — Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/orm/general.html).
