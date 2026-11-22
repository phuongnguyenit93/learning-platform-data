# Phân biệt component scanning với xử lý annotation trên bean đã có trong Spring Core Container

## 1. Mục tiêu học tập

Spring Framework sử dụng annotation ở nhiều thời điểm khác nhau. Hai quá trình thường bị nhầm lẫn nhất là:

1. **Component scanning:** tìm các class đủ điều kiện trên classpath và **đăng ký bean definition** vào IoC Container.
2. **Xử lý annotation trên bean đã được đăng ký:** khi bean được tạo và quản lý, các thành phần hạ tầng đọc annotation để **tiêm dependency, chạy callback vòng đời hoặc áp dụng hành vi bổ sung**.

Hai việc liên hệ nhưng **không phải một**. Một class có `@Component` mà chưa được scan hoặc đăng ký bằng cách khác thì không tự nhiên trở thành bean. Ngược lại, một bean được khai báo bằng `@Bean` hoặc XML vẫn có thể được xử lý `@Autowired`, `@PostConstruct` và nhiều annotation khác nếu có hạ tầng tương ứng.

Sau bài này, bạn có thể:

- Phân biệt **bean definition discovery/registration** với **bean instance processing**.
- Giải thích tại sao `@ComponentScan` và `@Autowired` giải quyết hai vấn đề khác nhau.
- Nhận diện vai trò của `ConfigurationClassPostProcessor`, `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor` và các `BeanPostProcessor` khác.
- Chạy ví dụ Java 17+ minh họa một bean được đăng ký qua `@Bean`, có field `@Autowired` và callback `@PostConstruct`/`@PreDestroy` dù không có `@ComponentScan`.
- Xác định chính xác nguyên nhân một annotation không có tác dụng: **chưa có bean**, **chưa đăng ký post-processor**, **không có hạ tầng tích hợp**, hoặc **lời gọi không đi qua proxy**.
- Đọc đúng log và kiểm tra bean definition thay vì suy đoán rằng cứ thấy annotation là Spring tự xử lý.

**Ngữ cảnh:** nội dung nằm trong nhóm **Quét thành phần** của Spring Core Container, nhưng có liên hệ với lifecycle và các extension point của IoC Container. Những ví dụ transaction, caching, web mapping chỉ dùng để xác định ranh giới cơ chế.

## 2. Hai câu hỏi độc lập: “bean từ đâu ra?” và “Spring làm gì với bean ấy?”

Một lớp Java không tự là Spring bean chỉ vì classpath chứa nó:

```java
import org.springframework.stereotype.Component;

@Component
public class GreetingService {
    public String greet() {
        return "hello";
    }
}
```

Đây là class biên dịch được khi có Spring Context trên classpath, nhưng để lấy được `GreetingService` qua `ApplicationContext`, trước hết phải có **bean definition** tương ứng hoặc một cơ chế đăng ký khác.

**Câu hỏi thứ nhất — Đăng ký bean:** Bean definition được đưa vào registry bằng cách nào? Ví dụ: `@ComponentScan`, `@Bean` trong configuration, `@Import`, XML, đăng ký chương trình hoặc cơ chế autoconfiguration.

**Câu hỏi thứ hai — Xử lý bean:** Khi container tạo instance từ bean definition, nó có tiêm field/method `@Autowired`, gọi `@PostConstruct`, chạy init callback, tạo proxy AOP hoặc đăng ký các metadata liên quan không? Việc này cần các post-processor và hạ tầng thích hợp.

Sơ đồ tư duy:

```text
                         CLASS / METADATA
                                |
                     Các cách đăng ký bean
                    /           |           \
          @ComponentScan      @Bean        XML / @Import / ...
                    \           |           /
                     \          v          /
                         BeanDefinition
                               |
                Spring BeanFactory / ApplicationContext
                               |
                   tạo và cấu hình bean instance
                               |
                các BeanPostProcessor phù hợp
                   /           |            \
            @Autowired   @PostConstruct    AOP proxy ...
                               |
                        bean sẵn sàng dùng
```

Không nên diễn giải hình này rằng Spring luôn thực thi các bộ xử lý đúng một thứ tự đơn giản cho tất cả annotation. Một số thành phần hoạt động **trên bean definition trước khi instance tồn tại**, một số can thiệp trước/sau khởi tạo và một số thuộc hạ tầng runtime khác. Phần sau phân tích từng nhóm.

## 3. Component scanning thực sự làm gì?

### 3.1. Tìm class candidate trong phạm vi cấu hình

Trong cấu hình Spring thuần:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "com.example.catalog")
public class CatalogConfig {
}
```

`@ComponentScan` hướng dẫn Spring quét package `com.example.catalog` và package con, áp dụng các bộ lọc nhận diện ứng viên (mặc định gồm `@Component` và các stereotype như `@Service`, `@Repository`, `@Controller`), rồi đăng ký bean definition.

**Nó không có nghĩa** Spring tự quét mọi package, và cũng không có nghĩa scanner lập tức tạo tất cả instance ngay khi đọc class file.

Ví dụ:

```text
com.example.catalog
  ├── CatalogConfig       @Configuration + @ComponentScan
  ├── CatalogService      @Service
  ├── CatalogRepository   @Repository
  └── Helper              class thuần, không có marker

com.example.external
  └── ExternalService     @Service
```

Với cấu hình trên và không có registration khác, scanner có thể phát hiện `CatalogService`, `CatalogRepository` ở package mục tiêu; `Helper` không có marker mặc định, còn `ExternalService` nằm ngoài phạm vi scan. `CatalogConfig` được đưa vào context theo cách bạn nạp nó hoặc scan phù hợp.

### 3.2. Điều kiện được scan không đồng nghĩa có thể tạo thành công

Sau khi class được chọn, Spring còn phải đáp ứng các điều kiện bean definition, tên bean, scope, constructor, dependency, conditional metadata và hạ tầng khởi tạo. Một candidate có thể bị loại theo filter/condition, hoặc bean có thể khởi tạo thất bại vì thiếu dependency.

```text
Tìm thấy class trên classpath
        !=
Class khớp component-scan filter
        !=
Đăng ký bean definition thành công
        !=
Khởi tạo bean instance thành công
        !=
Có mọi hành vi runtime đã mong đợi
```

Đây là các tầng cần kiểm tra riêng.

### 3.3. Những gì component scanner không tự làm

- Không tự tiêm `@Autowired` vào một object mà bạn tự tạo bằng `new` ngoài container.
- Không bắt buộc phải tồn tại thì `@Bean` mới hoạt động.
- Không khiến mỗi class có annotation bất kỳ thành bean; default scanner chỉ nhận diện các annotation theo bộ lọc của nó.
- Không tự mở cổng HTTP, bắt đầu transaction hoặc đăng ký caching.
- Không thể bảo đảm một bean không xuất hiện nếu cùng bean đó được đăng ký qua `@Bean` hay cấu hình khác.

**Ghi nhớ:** component scanning chủ yếu phục vụ **khám phá và đăng ký bean definition**.

## 4. Xử lý annotation trên bean đã có là gì?

Giả sử một bean được đăng ký trực tiếp bằng Java configuration:

```java
@Configuration
class AppConfig {
    @Bean
    ReportService reportService() {
        return new ReportService();
    }

    @Bean
    ReportRepository reportRepository() {
        return new ReportRepository();
    }
}
```

Đây là ví dụ cấu trúc; trong ứng dụng thực cần khai báo/import `@Configuration`, `@Bean` và hai class. Không có `@ComponentScan` trong cấu hình này, nhưng container vẫn có bean `reportService` và `reportRepository` do factory methods `@Bean` đăng ký.

Nếu `ReportService` có:

```java
import org.springframework.beans.factory.annotation.Autowired;

class ReportService {
    @Autowired
    private ReportRepository repository;

    public String run() {
        return repository.read();
    }
}
```

thì khi Spring tạo bean từ `@Bean` và có `AutowiredAnnotationBeanPostProcessor` hoạt động, field có thể được tiêm trước lúc sử dụng.

**Cơ chế thực tế không phải component scan tìm thấy field `@Autowired` để đăng ký ReportService.** ReportService đã được đăng ký bằng `@Bean`; post-processor sau đó xử lý metadata injection trên instance đang được tạo.

Tương tự, `@PostConstruct` yêu cầu hạ tầng lifecycle annotation xử lý bean được quản lý. Đối tượng tạo thủ công:

```java
ReportService ordinaryObject = new ReportService();
```

không tự được Spring tiêm `@Autowired` hay gọi `@PostConstruct` chỉ vì source code mang annotation. **Về mặt Java**, annotation là metadata; phải có một framework hay công cụ thực sự đọc và thực thi metadata đó.

## 5. Hai nhóm extension point cần phân biệt

Spring có các extension point xử lý **định nghĩa** và **instance** ở những pha khác nhau.

| Nhóm | Đối tượng tác động | Thời điểm chính | Ví dụ và vai trò |
| --- | --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Registry các bean definition | Trước khi instantiate các bean nghiệp vụ thông thường | Có thể đăng ký thêm definition; `ConfigurationClassPostProcessor` xử lý cấu hình class, `@Bean`, `@ComponentScan`. |
| `BeanFactoryPostProcessor` | Metadata của bean definition | Trước khi tạo các bean thông thường | Thay đổi/cấu hình metadata, ví dụ placeholder/property settings. |
| `BeanPostProcessor` | Instance của bean được quản lý | Trong quá trình tạo/khởi tạo bean | Xử lý annotation injection/lifecycle, áp dụng proxy hoặc custom initialization logic. |
| Hạ tầng bên ngoài bean creation | Bean metadata và/hoặc runtime request/call | Khi context setup hoặc ứng dụng chạy | MVC handler mappings, scheduled task registration, AOP advisor/interceptor. |

`BeanDefinitionRegistryPostProcessor` mở rộng `BeanFactoryPostProcessor`, nhưng có giai đoạn làm việc trên **registry**. `ConfigurationClassPostProcessor` có nhiệm vụ phân tích cấu hình annotation, từ đó việc quét class và việc đăng ký `@Bean` có thể diễn ra ở cùng quá trình xử lý metadata trước khi các bean ứng dụng được tạo.

`BeanPostProcessor` có hai callback cơ bản:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

Đây là chữ ký ý tưởng của interface `org.springframework.beans.factory.config.BeanPostProcessor` (API thực còn có default implementation). Processor có thể trả chính instance hoặc instance đã được thay thế/wrap. Spring AOP thường tạo proxy thông qua hạ tầng post-processing, nhưng **không phải mọi BeanPostProcessor đều là proxy**.

**Điểm mấu chốt:** một bean đã tồn tại trong definition registry sẽ được xem xét trong vòng đời bean creation. Việc scan package không phải là điều kiện để các BeanPostProcessor này chạy.

## 6. Ai xử lý những annotation thường gặp?

| Annotation / metadata | Giai đoạn hoặc hạ tầng thường liên quan | Điều kiện cần nhớ |
| --- | --- | --- |
| `@Component`, `@Service`, `@Repository`, `@Controller` | Component scan / bean definition registration | Có scan đúng package/filter, hoặc bean được đăng ký qua đường khác. |
| `@Configuration` và `@Bean` | `ConfigurationClassPostProcessor` | Configuration class phải được đưa vào context qua một đường đăng ký hợp lệ. |
| `@Autowired`, `@Value`, Jakarta `@Inject` | `AutowiredAnnotationBeanPostProcessor` và cơ chế resolve dependency/value | Bean được Spring quản lý; processor phải được đăng ký. |
| Jakarta `@Resource`, `@PostConstruct`, `@PreDestroy` | `CommonAnnotationBeanPostProcessor` / lifecycle support | Processor và Jakarta Annotation API phải hiện diện đúng. |
| `@Transactional` | Transaction annotation source, AOP/interceptor, transaction manager | Không tự bật transaction chỉ vì bean có annotation. |
| `@Async` | Hạ tầng async, thường `AsyncAnnotationBeanPostProcessor` | Cần bật async support, executor và lời gọi phù hợp. |
| `@Cacheable` | Hạ tầng caching/AOP | Cần bật caching và cấu hình cache manager phù hợp. |
| `@Scheduled` | `ScheduledAnnotationBeanPostProcessor` / scheduling infrastructure | Cần kích hoạt scheduling và phù hợp execution context. |
| `@RequestMapping`, `@GetMapping` trên controller | Spring MVC handler mapping/adapter | Phải có web application context và MVC infrastructure thích hợp. |

Một annotation có thể được nhiều thành phần đọc hoặc dùng metadata ở nhiều pha; bảng thể hiện **đầu mối chính** để phân tích, không khẳng định tất cả annotation chỉ có một processor hoặc luôn hoạt động như nhau trong mọi ứng dụng.

### 6.1. @Autowired không phải “cơ chế quét class”

Khi Spring có một bean definition của class `A` và đang tạo `A`, `AutowiredAnnotationBeanPostProcessor` có thể phân tích constructor, field hoặc method mang `@Autowired` để hỗ trợ lựa chọn constructor và inject dependency. Tùy kiểu đăng ký và thời điểm, chi tiết injection khác nhau.

Ví dụ class được đăng ký bằng `@Bean` có constructor được **gọi trực tiếp bên trong factory method**: container không tự chọn lại constructor cho đối tượng `new A()` đó. Tuy nhiên, field/method `@Autowired` của instance trả về vẫn có thể được post-process. Ngược lại, bean được tạo trực tiếp theo bean class có thể được processor hỗ trợ chọn constructor mang `@Autowired`.

### 6.2. @PostConstruct chạy sau injection, trước khi bean sẵn sàng dùng

Với processor được cấu hình đúng, callback `@PostConstruct` thường chạy khi instance đã được inject dependency cơ bản, trong giai đoạn khởi tạo bean, trước khi bean hoàn tất quá trình startup.

`@PreDestroy` chạy trong vòng đời hủy bean do Spring quản lý, thường khi đóng context đối với singleton. Container **không tự quản lý toàn bộ destruction callback của prototype sau khi cấp instance**; vì vậy đừng suy luận prototype luôn nhận `@PreDestroy` khi xử lý xong.

## 7. Ví dụ chạy được: KHÔNG component scan nhưng annotation vẫn hoạt động

Đây là bài thực hành quan trọng nhất. Chúng ta cố ý **không khai báo `@ComponentScan`**, nhưng vẫn:

- Đăng ký `Formatter` và `ManualService` qua hai factory methods `@Bean`.
- Dùng `@Autowired` để tiêm field `Formatter` vào bean `ManualService`.
- Dùng `@PostConstruct` để in trạng thái injection trước khi logic chính chạy.
- Dùng `@PreDestroy` để in sự kiện hủy khi đóng `ApplicationContext`.
- Đặt `@Service` trên `ManualService` để chứng minh class có stereotype nhưng **được đăng ký nhờ `@Bean`**.
- Đặt `@Component("unscannedComponent")` trên một class khác nhưng không hề đăng ký nó, để chứng minh **annotation không tự biến class thành bean**.

### 7.1. Tạo dự án

Cấu trúc:

```text
annotation-processing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── AnnotationProcessingDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'annotation-processing-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AnnotationProcessingDemo'
}
```

Spring Framework 6.2.x yêu cầu Java 17+. Đặt Jakarta Annotation API trực tiếp trong dependencies để project biên dịch ổn định các import `jakarta.annotation.PostConstruct` và `jakarta.annotation.PreDestroy`. Không dùng `javax.annotation` của Java EE cũ với Spring 6.

**`src/main/java/demo/AnnotationProcessingDemo.java`**

```java
package demo;

import java.util.Locale;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

public class AnnotationProcessingDemo {

    public static class Formatter {
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    @Service
    public static class ManualService {
        // Chủ đích dùng field injection để quan sát annotation processing.
        // Trong thiết kế production, thường nên ưu tiên constructor injection.
        @Autowired
        private Formatter formatter;

        @PostConstruct
        void afterInjection() {
            System.out.println("post-construct=" + (formatter != null));
        }

        public String work(String input) {
            return formatter.format(input);
        }

        @PreDestroy
        void beforeDestroy() {
            System.out.println("pre-destroy");
        }
    }

    @Component("unscannedComponent")
    public static class UnscannedComponent {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Formatter formatter() {
            return new Formatter();
        }

        @Bean
        ManualService manualService() {
            return new ManualService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("context-ready");
            System.out.println("manual-service="
                    + context.containsBean("manualService"));
            System.out.println("unscanned-component="
                    + context.containsBean("unscannedComponent"));

            ManualService service = context.getBean(ManualService.class);
            System.out.println("work=" + service.work("hello"));
        }
    }
}
```

**Chạy** trong thư mục gốc của dự án:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS, hoặc `gradlew.bat run --quiet` trên Windows. Lệnh `javac AnnotationProcessingDemo.java` riêng lẻ không đủ nếu không khai báo classpath Spring/Jakarta; Gradle sẽ biên dịch và chạy với dependencies.

**Các dòng được chương trình in ra (stdout):**

```text
post-construct=true
context-ready
manual-service=true
unscanned-component=false
work=HELLO
pre-destroy
```

Các công cụ build có thể ghi log khác tùy môi trường; các dòng trên là kết quả từ `System.out.println` của chương trình.

### 7.2. Vì sao kết quả như vậy?

1. `new AnnotationConfigApplicationContext(Config.class)` đăng ký class cấu hình `Config` và refresh context. `Config` có `@Configuration`, **không có `@ComponentScan`**.
2. `ConfigurationClassPostProcessor` xử lý phương thức `@Bean`, tạo bean definitions cho `formatter` và `manualService`.
3. Container tạo bean `ManualService` từ factory method `manualService()`. Trong factory method, đối tượng được dựng bởi `new ManualService()`; việc gọi `new` này xảy ra **trong cơ chế tạo bean do Spring kiểm soát**.
4. Bean instance trả về được các post-processor liên quan xử lý. `AutowiredAnnotationBeanPostProcessor` tìm field `formatter` và inject bean `Formatter` từ context.
5. `CommonAnnotationBeanPostProcessor` nhận callback `@PostConstruct`; lúc đó `formatter != null` nên in `post-construct=true` **trước** `context-ready`.
6. `@Service` trên `ManualService` không phải nguyên nhân bean xuất hiện trong ví dụ. `@Bean` mới là đường đăng ký thực tế, nhưng điều này không cản các processor xử lý instance.
7. `UnscannedComponent` có `@Component` nhưng không được đăng ký trực tiếp và không có component scan, vì vậy `containsBean("unscannedComponent")` trả `false`.
8. `try-with-resources` đóng `AnnotationConfigApplicationContext`. Callback `@PreDestroy` của singleton `ManualService` chạy và in `pre-destroy`.

Bài thực hành chứng minh hai sự kiện riêng:

- **Có bean definition không cần component scan:** `manualService=true`.
- **Annotation trên bean đã có vẫn được xử lý:** `post-construct=true` và `work=HELLO`, dù không có `@ComponentScan`.

Nó cũng chứng minh chiều ngược lại: **`@Component` tự đứng trên class chưa tạo bean** nếu class không được scan/đăng ký.

### 7.3. Điều gì xảy ra nếu tự new ngoài container?

Xét đoạn độc lập:

```java
AnnotationProcessingDemo.ManualService manual =
        new AnnotationProcessingDemo.ManualService();
manual.work("hello");
```

Đây không phải cách tạo Spring bean: field `formatter` vẫn là `null`, do đó `work` sẽ ném `NullPointerException` tại `formatter.format(...)`. Không có tự động `@PostConstruct` hoặc `@PreDestroy`. Đừng chạy biến thể này như một test mong đợi thành công.

**Điểm tinh tế:** `@Bean` có thể trả về đối tượng được tạo bằng `new` và **vẫn** được Spring xử lý vì factory method nằm trong vòng đời container. Việc “có từ khóa `new`” không đủ để kết luận Spring có quản lý bean hay không; phải xem đối tượng ấy được đưa vào container bằng cơ chế nào.

## 8. So sánh với component scan bằng ví dụ đối chiếu

Từ chương trình trước, nếu muốn tự động nhận diện các class có stereotype, có thể tạo một context cấu hình scan:

```java
@Configuration
@ComponentScan(basePackageClasses = AnnotationProcessingDemo.class)
class ScanConfig {
}
```

Đoạn này là **minh họa cấu hình riêng**, không thay thế trực tiếp trong demo mà không xem lại package. Nếu scan toàn bộ package `demo` chứa cả `Config` có `@Bean`, Spring cũng có thể nhận `Config`; các bean được khai báo thủ công có thể xuất hiện đồng thời với bean scan cùng type và gây trùng tên, nhiều candidate hoặc xung đột định nghĩa. Khi thử nghiệm, nên tách package fixture scan và package cấu hình thủ công hoặc exclude/import đúng mục đích.

Một bài test scan độc lập có thể dùng:

```java
@Configuration
@ComponentScan(basePackages = "com.example.scandemo")
class ScanOnlyConfig {
}
```

Giả sử package `com.example.scandemo` chứa `@Service OrderService` và `@Component AuditSink` cùng dependencies hợp lệ. Scanner sẽ phát hiện chúng và đăng ký definitions. Sau đó, **cùng hệ thống post-processor** vẫn có thể tiêm `@Autowired` và xử lý lifecycle trên các instance được tạo.

### Hai luồng dẫn đến một cơ chế bean creation

```text
Luồng A:
@Component trên class
     |
@ComponentScan đúng package
     |
BeanDefinition
     |
Container tạo bean
     |
BeanPostProcessor: @Autowired, @PostConstruct, ...

Luồng B:
@Configuration + @Bean
     |
ConfigurationClassPostProcessor
     |
BeanDefinition
     |
Container tạo bean
     |
BeanPostProcessor: @Autowired, @PostConstruct, ...
```

Khác nhau ở **đường đăng ký bean definition**; giai đoạn xử lý instance dùng cơ sở hạ tầng chung của container. Đôi khi cách tạo object cụ thể khác nhau (constructor do container chọn so với factory method tạo object), nên không khẳng định mọi annotation áp dụng giống hệt cho mọi đường đăng ký.

## 9. BeanFactory và ApplicationContext khác gì trong câu chuyện này?

**`BeanFactory`** là giao diện nền tảng để truy xuất/quản lý bean; một số triển khai cấp thấp không tự đăng ký mọi annotation post-processor. **`ApplicationContext`** là giao diện mức cao, thường tự phát hiện và đăng ký `BeanFactoryPostProcessor`, `BeanPostProcessor` thích hợp trong chu trình refresh.

`AnnotationConfigApplicationContext` đặc biệt thuận tiện cho Java annotation configuration: nó đăng ký các annotation config processor thông dụng khi khởi tạo, nên ví dụ ở mục 7 hoạt động mà không cần tự viết `@Bean` cho `AutowiredAnnotationBeanPostProcessor`.

Phân biệt các môi trường:

| Môi trường | Bean registration | Annotation processing |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` | Đọc configuration class và `@Bean`; chỉ scan nếu được yêu cầu | Đã chuẩn bị sẵn nhiều annotation processor cốt lõi. |
| `new ClassPathXmlApplicationContext("beans.xml")` | Đọc XML bean definitions | Thường khai báo `<context:annotation-config/>` hoặc `<context:component-scan/>` khi muốn bật annotation processing tương ứng trong cấu hình XML. |
| `new DefaultListableBeanFactory()` độc lập | Có thể đăng ký definitions bằng API | Không mặc nhiên tương đương đầy đủ hạ tầng annotation của `AnnotationConfigApplicationContext`; cần thiết lập thích hợp. |
| Spring Boot application context | Auto-configuration, Java configuration, component scanning mặc định theo package setup | Boot thường tự lắp hạ tầng cần thiết, nhưng mỗi tính năng có điều kiện kích hoạt riêng. |

Bảng mô tả hành vi thông dụng; cấu hình tùy chỉnh, module/classpath hoặc extension point có thể thay đổi.

### 9.1. <context:annotation-config/> và <context:component-scan/> trong XML

Ví dụ XML annotation processing cho bean **đã khai báo**:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="formatter" class="com.example.Formatter"/>
    <bean id="reportService" class="com.example.ReportService"/>
</beans>
```

Nếu `ReportService` có `@Autowired Formatter` và có processor phù hợp, bean XML vẫn được tiêm. `<context:annotation-config/>` **không thực hiện component scan**; chỉ khai báo post-processor cho annotation trên các bean được đăng ký trong cùng context.

Ngược lại, XML:

```xml
<context:component-scan base-package="com.example"/>
```

kích hoạt scan trong package và cũng **bao hàm kích hoạt annotation-config processors thông dụng** theo mặc định. Vì vậy trong nhiều cấu hình XML có `<context:component-scan/>`, không cần thêm `<context:annotation-config/>` riêng chỉ để tiêm `@Autowired`.

**Ngữ cảnh quan trọng:** các post-processor thường có hiệu lực trong **chính context** được khai báo; ở ứng dụng nhiều context (root/child web context), không tự suy ra mọi processor ở child sẽ xử lý bean của parent.

## 10. BeanDefinitionRegistryPostProcessor khác BeanPostProcessor ở đâu?

### 10.1. Cấu hình metadata trước khi tạo instance

`ConfigurationClassPostProcessor` là một ví dụ hạ tầng quan trọng, có khả năng xử lý `@Configuration`, `@ComponentScan`, `@Bean`, `@Import` và đăng ký các definitions/điều kiện liên quan. Nó hoạt động **trước phần lớn việc tạo bean ứng dụng**.

Điều này giải thích vì sao `@Bean` khai báo trong class cấu hình vẫn được Spring đọc dù không có component scanning. ApplicationContext đã biết class cấu hình vì bạn truyền nó vào constructor hoặc đăng ký class đó bằng cách khác.

Một `BeanFactoryPostProcessor` tự viết thường dùng để đọc hoặc chỉnh sửa `BeanDefinition` trước khi tạo instance, chứ không phải nơi sửa object đã được tạo:

```java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetadataConfig {
    @Bean
    static BeanFactoryPostProcessor inspectDefinitions() {
        return beanFactory -> {
            if (beanFactory.containsBeanDefinition("exampleBean")) {
                var definition =
                        beanFactory.getBeanDefinition("exampleBean");
                System.out.println("scope=" + definition.getScope());
            }
        };
    }
}
```

Đây là ví dụ minh họa, chỉ in kết quả nếu có bean definition `exampleBean`. `getScope()` có thể trả chuỗi rỗng khi bean dùng scope mặc định, không nhất thiết in `singleton`. Với `BeanFactoryPostProcessor` khai báo từ `@Bean`, phương thức `static` giúp tránh phải khởi tạo sớm configuration instance.

### 10.2. Xử lý instance khi container tạo bean

Một `BeanPostProcessor` tùy chỉnh có thể quan sát bean được đăng ký từ cả component scan lẫn `@Bean`:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TraceConfig {
    @Bean
    static BeanPostProcessor traceProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String name) {
                if (name.equals("exampleBean")) {
                    System.out.println("initialized=" + name);
                }
                return bean;
            }
        };
    }
}
```

Đây là snippet chỉ được chạy khi có bean tên `exampleBean` trong cùng context và processor được đăng ký đủ sớm. `postProcessAfterInitialization` không quyết định scanner chọn class nào; nó nhận **instance được Spring tạo** và trả về object để container tiếp tục sử dụng.

**Lưu ý sớm-muộn:** Một `BeanPostProcessor` tự tạo cũng là bean đặc biệt, được dựng sớm. Nếu nó kéo theo nhiều bean ứng dụng lúc khởi tạo, những bean ấy có thể không được hưởng đầy đủ mọi post-processor, đặc biệt auto-proxying. Khi tự khai báo `@Bean` trả `BeanPostProcessor`/`BeanFactoryPostProcessor`, nên cân nhắc `static` và hạn chế dependencies theo hướng dẫn framework.

## 11. @Autowired, @PostConstruct và vòng đời bean

Sơ đồ đơn giản cho một singleton thông thường:

```text
BeanDefinition tồn tại
        |
Container xác định cách tạo đối tượng
        |
Tạo instance (constructor / factory method)
        |
Property/field/method injection thích hợp
        |
BeanPostProcessor trước khởi tạo
        |
@PostConstruct và callback init theo cấu hình/thứ tự phù hợp
        |
BeanPostProcessor sau khởi tạo (có thể tạo proxy)
        |
Bean sẵn sàng sử dụng
        |
Context đóng / scope kết thúc với destruction support
        |
@PreDestroy, DisposableBean, destroy callback tương ứng
```

Sơ đồ là mô hình học tập: `@PostConstruct` có thể được một `BeanPostProcessor` xử lý trong giai đoạn trước các callback init khác, và hạ tầng AOP/creation có nhiều biến thể. Không dùng sơ đồ như một hợp đồng thứ tự cho mọi extension point trong tất cả phiên bản.

### 11.1. Tiêm dependency trong @Bean-created object

Đối tượng do `@Bean` factory method trả về vẫn được container đưa qua các bước property population và initialization thông thường. Điều này giải thích ví dụ có:

```java
@Bean
SomeService service() {
    return new SomeService();
}
```

trong khi `SomeService` có field `@Autowired`. Nếu field injection processor có mặt, field được xử lý sau khi object đã được factory method tạo.

### 11.2. Constructor injection vẫn là lựa chọn ưu tiên

Ví dụ trước dùng field injection để cho thấy *annotation processing trên instance*. Trong thiết kế production, constructor injection thường giúp dependency bắt buộc được khai báo rõ và object dễ test:

```java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout() {
        return gateway.pay();
    }
}
```

Đây là ví dụ cấu trúc với `PaymentGateway` là interface nghiệp vụ giả định. Với class được scan và một constructor, Spring có thể resolve dependency khi tạo bean. Nếu class được tạo trong `@Bean` bằng `new CheckoutService(gateway)`, factory method chịu trách nhiệm cấp argument; Spring không thay constructor call đã thực hiện.

### 11.3. Lưu ý bean prototype

Spring thường gọi callback khởi tạo như `@PostConstruct` cho prototype khi tạo nó, nhưng sau khi cấp prototype cho caller, container không quản lý trọn destruction của instance giống singleton. Nếu prototype nắm tài nguyên, caller phải có kế hoạch cleanup phù hợp.

## 12. Không phải annotation nào cũng do BeanPostProcessor xử lý

Đây là phân biệt sâu hơn giúp tránh học thuộc sai:

### 12.1. @Transactional cần AOP và transaction management

Một class có `@Service` hay được tạo bởi `@Bean` đều có thể tham gia transaction nếu hạ tầng transaction được bật đúng, annotation được nhận diện và lời gọi đi qua interceptor/proxy thích hợp:

```java
@Service
public class MoneyTransferService {
    @org.springframework.transaction.annotation.Transactional
    public void transfer(long from, long to, long amount) {
        // Nghiệp vụ và persistence thật được triển khai tại đây.
    }
}
```

Đoạn này minh họa class; không phải chương trình đầy đủ. `@Transactional` không hoạt động chỉ vì scanner nhận `@Service` hoặc vì `@Bean` đăng ký class. Cần transaction manager, transaction attribute source/advisor/interceptor và điều kiện proxy/AspectJ phù hợp. Trong proxy mode thường gặp, **self-invocation** (method trong cùng bean gọi trực tiếp method khác của chính nó) không đi qua transaction proxy.

### 12.2. @RequestMapping thuộc hạ tầng web

Một controller có thể là Spring bean hợp lệ nhưng chưa có HTTP endpoint:

```java
@Controller
class HelloController {
    @GetMapping("/hello")
    @ResponseBody
    String hello() {
        return "hello";
    }
}
```

Đây là snippet web MVC cần import annotation, web application context và servlet/handler mapping tương ứng. Component scan chỉ đưa controller vào registry; Spring MVC `RequestMappingHandlerMapping` cần xem bean controller, tìm mapping và gắn với dispatcher. Một `AnnotationConfigApplicationContext` thuần không tự biến `@GetMapping` thành HTTP endpoint.

### 12.3. @Scheduled cần scheduling infrastructure

`@Scheduled` trên bean đã có cũng không chạy theo thời gian nếu không có scheduling support phù hợp. Trong cấu hình thông thường dùng `@EnableScheduling` (hoặc hạ tầng tương đương) để đăng ký processor cần thiết. Đăng ký bean thông qua scan hay `@Bean` là một chuyện; scheduling processor mới nhận diện lịch và thực thi.

### 12.4. @Repository và exception translation

`@Repository` là specialization của `@Component`, nhưng hành vi dịch persistence exception không được bảo đảm chỉ bằng marker. Khi `PersistenceExceptionTranslationPostProcessor` và `PersistenceExceptionTranslator` phù hợp có mặt, Spring có thể tạo interceptor/proxy thích hợp và chuyển exception sang họ `DataAccessException`. Một số công nghệ như `JdbcTemplate` cũng có cơ chế dịch ngoại lệ riêng. Cần phân biệt marker, post-processor và công nghệ data access.

**Nguyên tắc chung:** muốn biết một annotation có tác dụng hay không, luôn xác định **ai đọc annotation ấy**, **đọc lúc nào** và **cần điều kiện hạ tầng nào**.

## 13. Bảng so sánh có thể dùng khi debug

| Câu hỏi | Component scanning | Xử lý annotation trên bean |
| --- | --- | --- |
| Trả lời vấn đề gì? | Class nào có bean definition được tự động đăng ký? | Bean instance/metadata đã đăng ký được cấu hình và vận hành ra sao? |
| Đầu vào cốt lõi | Classpath, base package, metadata, include/exclude filter | Bean definition/instance đang được container quản lý, annotation trên class/field/method |
| Cơ chế tiêu biểu | `@ComponentScan`, `ClassPathBeanDefinitionScanner` | `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor` và processor tích hợp khác |
| Pha điển hình | Trước tạo bean, khi đăng ký definitions | Khi tạo bean hoặc khi hạ tầng xử lý runtime |
| Kết quả | BeanDefinition và tên/scope metadata | Dependency được inject, callback được gọi, proxy/hành vi được lắp |
| Có bắt buộc lẫn nhau? | Không; scan tạo definitions nhưng không thay thế BPP | Không; BPP xử lý bean từ `@Bean`, XML và các đường đăng ký khác |
| Áp dụng với object tạo bởi `new` ngoài container? | Không | Không tự động |
| Tất cả annotation được xử lý ở cùng một chỗ? | Không | Không; có BFPP, BPP và web/AOP/runtime infrastructure |

### Ma trận tình huống

| Tình huống | Có bean? | `@Autowired` / `@PostConstruct` có thể chạy? |
| --- | --- | --- |
| `@Component` ở package không được scan, không đăng ký cách khác | Không | Không |
| `@Component` được scan và đăng ký đúng, annotation processor hoạt động | Có | Có |
| Class không mang `@Component`, được đăng ký qua `@Bean`, processor hoạt động | Có | Có |
| Class mang `@Component`, được đăng ký qua `@Bean`, không bật scan | Có | Có |
| Class được đăng ký XML, khai báo processor tương ứng | Có | Có |
| Object được code nghiệp vụ `new` mà không giao cho container | Không phải Spring bean | Không tự động |
| Bean có trong context nhưng thiếu annotation processor tương ứng | Có | Một phần annotation có thể không được xử lý |
| Controller bean có `@GetMapping` nhưng không có Spring MVC infrastructure | Có | Không có HTTP endpoint chỉ nhờ controller bean |

Từ “có thể” ở cột cuối nhằm nhấn mạnh **phải có post-processor đúng** và dependency/callback hợp lệ; không phải bảo đảm mọi bean luôn được xử lý thành công.

## 14. Các hiểu lầm phổ biến

### 14.1. “@Autowired chỉ có tác dụng với class được scan”

Sai. `@Autowired` được xử lý trên bean do Spring quản lý nếu processor được đăng ký; bean có thể được tạo từ `@Bean` hoặc XML. Ví dụ chạy được đã chứng minh trường hợp này.

### 14.2. “Có @Component nhưng getBean không tìm thấy nghĩa là @Component hỏng”

Chưa chắc. Kiểm tra package scan, include/exclude, profile/condition, cấu hình có được load, bean name và lỗi đăng ký. Nếu class không nằm trong vùng scan và không được đăng ký ở nơi khác, việc nó vắng mặt là đúng.

### 14.3. “Bật @ComponentScan là tất cả annotation đều hoạt động”

Sai. Component scan giúp đăng ký bean và trong nhiều ngữ cảnh cũng kích hoạt processor cốt lõi, nhưng annotation như `@Transactional`, `@Cacheable`, `@Async`, `@Scheduled` hay `@RequestMapping` cần hạ tầng chuyên biệt.

### 14.4. “Thêm @PostConstruct cho một object tự new sẽ gọi callback”

Sai. Nếu code tự tạo object ngoài container, annotation không tự chạy. Hãy để container quản lý instance hoặc tự gọi logic init do ứng dụng kiểm soát; không trông chờ vào callback Spring.

### 14.5. “@Bean sẽ bỏ qua mọi annotation trên class được trả về”

Sai. Object `@Bean` trả về được xử lý như Spring-managed bean, bao gồm post-processors thông thường. Nhưng constructor invocation đã diễn ra trong factory method nên không thể suy diễn rằng Spring chọn constructor `@Autowired` thay cho lời gọi `new` của method ấy.

### 14.6. “BeanFactoryPostProcessor và BeanPostProcessor giống nhau”

Sai. `BeanFactoryPostProcessor` xử lý **metadata/definitions** trước khi tạo bean thông thường; `BeanPostProcessor` xử lý **instance** trong chu trình khởi tạo. Làm bean creation quá sớm trong BFPP có thể bỏ qua một số BPP.

### 14.7. “@Service được scan rồi thì @Transactional chạy chắc chắn”

Sai. Transaction cần transaction manager và AOP/interceptor thích hợp. Có bean không đồng nghĩa có transaction boundary. Self-invocation cũng có thể bỏ qua proxy trong chế độ thông thường.

### 14.8. “Có BeanPostProcessor là mọi object trong JVM đều được xử lý”

Sai. Processor được đăng ký trong phạm vi **container cụ thể** và được áp dụng cho bean do container quản lý. Object tự tạo hoặc bean trong context khác không tự được xử lý bởi processor ấy.

### 14.9. “@ComponentScan loại class thì @Bean không thể tạo instance class đó”

Sai. Exclude filter chỉ chặn một đường khám phá. `@Bean` hoặc cấu hình khác vẫn có thể đăng ký class tương ứng.

### 14.10. “@PostConstruct và @PreDestroy luôn xuất hiện theo cùng một lịch trong mọi scope”

Không đúng. Callback khởi tạo của prototype có thể được chạy khi bean được tạo, nhưng container không tự quản lý toàn bộ destruction như singleton. Các context có shutdown không đúng cách cũng có thể khiến callback hủy không được gọi như dự kiến.

## 15. Phương pháp chẩn đoán theo từng tầng

Khi một annotation có vẻ “không hoạt động”, đừng sửa bằng cách thêm `@ComponentScan` vào mọi configuration. Hãy lần lượt tách ba câu hỏi.

### 15.1. Tầng thứ nhất: bean definition có tồn tại?

Trong một `AnnotationConfigApplicationContext` hoặc context có API tương ứng:

```java
System.out.println(context.containsBeanDefinition("manualService"));
System.out.println(context.containsBean("manualService"));
```

Đoạn này dựa trên biến `context` ở ví dụ mục 7. `containsBeanDefinition` tra **definition trực tiếp trong factory hiện tại**, còn `containsBean` có thể phản ánh bean có sẵn và trong một số bối cảnh tìm qua parent factory. Khi điều tra context phân cấp, cần hiểu sự khác nhau này.

Nếu bean không tồn tại, kiểm tra đường đăng ký: `@ComponentScan`, `@Bean`, `@Import`, XML, profile hoặc filter. **Đừng debug field injection khi class còn chưa là bean.**

### 15.2. Tầng thứ hai: instance đã được xử lý chưa?

Nếu bean tồn tại nhưng field `@Autowired` bị `null`, kiểm tra:

- Có phải object thực sự nhận từ container, hay caller tự `new` một instance khác?
- Context có đăng ký `AutowiredAnnotationBeanPostProcessor` không?
- Field/method injection có phù hợp, dependency bean có tồn tại, có đủ candidate duy nhất không?
- Bean có bị khởi tạo sớm trong lúc post-processor chưa sẵn sàng không?
- Trong trường hợp `@Bean`, phần nào được tạo bởi factory method và phần nào do post-processor xử lý?

Với callback `@PostConstruct`, kiểm tra có Jakarta Annotation API và `CommonAnnotationBeanPostProcessor` phù hợp, callback signature/lifecycle có hợp lệ không.

### 15.3. Tầng thứ ba: hạ tầng riêng có được bật?

Nếu `@Transactional` không hoạt động, kiểm tra transaction manager, transaction advisor, proxy và call path. Nếu `@GetMapping` không có route, kiểm tra web application context và handler mapping. Nếu `@Scheduled` không chạy, kiểm tra scheduling infrastructure. Đây không phải lỗi component scan nếu bean đã được đăng ký và nhìn thấy từ context.

### 15.4. Đọc bean definition để biết đường đăng ký

```java
var factory = context.getBeanFactory();
var definition = factory.getBeanDefinition("manualService");

System.out.println(definition.getFactoryMethodName());
System.out.println(definition.getResourceDescription());
```

Đặt snippet này trong scope của `context` ở mục 7. Với bean định nghĩa bằng `@Bean`, `getFactoryMethodName()` thường trả `manualService`. `getResourceDescription()` có thể mô tả nguồn class/configuration; giá trị chính xác thay đổi theo cách đăng ký, không nên khẳng định stdout cố định cho mọi environment.

Với bean được component scan, bean definition thường liên quan đến class source/resource của ứng viên, chứ không phải một `@Bean` factory method. Khi xem thông tin này, kết hợp với danh sách post-processor để biết tại sao một annotation được hoặc không được xử lý.

## 16. Kiểm thử để khẳng định sự khác biệt

### 16.1. Kiểm thử registration

Dựng context chỉ với `Config` ở mục 7:

- `containsBean("manualService")` phải là `true`.
- `containsBean("unscannedComponent")` phải là `false`.

Đây là phép thử **đường đăng ký**. Nó không đủ để khẳng định injection hoặc callback lifecycle đã hoạt động.

### 16.2. Kiểm thử injection và lifecycle

Dùng bean từ context:

```java
var service = context.getBean(AnnotationProcessingDemo.ManualService.class);
String result = service.work("hello");
if (!"HELLO".equals(result)) {
    throw new AssertionError("Annotation injection failed: " + result);
}
```

Đây là snippet dựa trên `context` từ chương trình đầy đủ; nó chứng minh dependency `Formatter` đã sẵn sàng khi `work` chạy. Có thể dùng JUnit assertions trong dự án có test dependency tương ứng. Để kiểm tra `@PostConstruct` và `@PreDestroy` tự động, có thể ghi callback vào một recorder/test fixture và assert trước/sau khi close context, tránh test phụ thuộc chặt vào stdout.

### 16.3. Kiểm thử bằng hai context tách biệt

Có thể tạo hai fixture:

- **Fixture A:** chỉ `@Bean`, không có `@ComponentScan`; assert bean được đăng ký và xử lý annotation.
- **Fixture B:** cấu hình `@ComponentScan` đúng một package chứa các stereotype; assert scanner đăng ký class tương ứng, rồi post-processor xử lý chúng.

Nếu muốn test tác động khi thiếu processor, sử dụng một `BeanFactory` cấp thấp với registration rõ ràng. Tuy nhiên, đừng giả định một `AnnotationConfigApplicationContext` đã tắt component scan cũng đồng thời tắt `AutowiredAnnotationBeanPostProcessor`: hai điều đó là độc lập.

### 16.4. Kiểm thử proxy behavior

Khi test `@Transactional` hoặc `@Async`, việc `containsBean` trả `true` và injection hoạt động không chứng minh interceptor/async đã kích hoạt. Cần test observable behavior của transaction/async và đường gọi thực sự đi qua Spring-managed proxy hoặc mode phù hợp.

## 17. Bài tập tình huống

**Tình huống 1.** Class `EmailSender` có `@Component` nhưng nằm ngoài tất cả base package được scan. Một `@Bean` khác trong configuration trả về `new EmailSender()`. Class có trở thành bean không?

**Đáp:** Có, nếu configuration chứa `@Bean` được xử lý và tạo bean thành công. Nó xuất hiện từ factory method; `@Component` không phải nguyên nhân trực tiếp.

**Tình huống 2.** `EmailSender` ở trên có field `@Autowired Client client`. Có component scan hay không quyết định injection?

**Đáp:** Không trực tiếp. Nếu `EmailSender` là Spring-managed bean và `AutowiredAnnotationBeanPostProcessor` hoạt động, field injection vẫn có thể xảy ra. Dependency `Client` phải có bean phù hợp.

**Tình huống 3.** Một class `@Service` được quét thành bean nhưng method `@Scheduled` không chạy. Cần kiểm tra ở đâu trước?

**Đáp:** Tầng scheduling infrastructure: `@EnableScheduling`/processor tương ứng, cấu hình scheduler và method hợp lệ; component scan đã hoàn thành nhiệm vụ nếu bean thực sự tồn tại.

**Tình huống 4.** Developer thêm `@PostConstruct` vào một object tạo thủ công bằng `new` trong một method của service. Callback sẽ tự chạy chứ?

**Đáp:** Không. Đây là instance ngoài vòng đời bean của container. Chỉ annotation trên class không làm Spring tự xử lý object đó.

**Tình huống 5.** `@Controller` được Spring tạo thành bean, nhưng `GET /hello` trả 404. Có chắc lỗi do component scan không?

**Đáp:** Không. Cần kiểm tra web stack, handler mapping, mapping annotation, HTTP method/path và context chứa controller. Có bean chỉ chứng minh registration/creation, không chứng minh routing.

**Tình huống 6.** `@Autowired` không hoạt động trên object được factory method `@Bean` trả về. Những yếu tố cần kiểm tra?

**Đáp:** Processor được đăng ký chưa, object nhận có đúng instance container quản lý không, injection metadata hợp lệ không, dependency có giải quyết được không, hoặc bean có bị khởi tạo sớm trước khi BPP hoạt động đầy đủ không.

**Tình huống 7.** `@Bean SomeService service() { return new SomeService(); }` tạo bean, trong khi `SomeService` có constructor `@Autowired SomeService(A a)` mà không có no-arg constructor. Spring có tự thay câu lệnh `new SomeService()` không?

**Đáp:** Không. Câu lệnh Java ở factory method phải biên dịch được; Spring không thay constructor call trong method. Có thể khai báo `@Bean SomeService service(A a) { return new SomeService(a); }` để container resolve `A` và chuyển vào factory method.

**Tình huống 8.** Một `BeanFactoryPostProcessor` gọi `getBean()` để lấy service quá sớm, sau đó service không được AOP auto-proxy. Vì sao?

**Đáp:** Bởi bean được instantiate trước giai đoạn đăng ký đầy đủ các `BeanPostProcessor`/auto-proxy creators, nên có thể không đủ điều kiện được xử lý. BFPP chủ yếu nên thao tác metadata thay vì yêu cầu bean instance nghiệp vụ quá sớm.

## 18. Checklist kiến thức và thực hành

Khi nhìn thấy annotation trong Spring, hãy trả lời theo thứ tự:

1. **Đang nói đến class hay bean instance?** Class có trên classpath không đồng nghĩa bean definition đã đăng ký.
2. **Bean đăng ký bằng đường nào?** `@ComponentScan`, `@Bean`, XML, `@Import` hay cơ chế khác?
3. **Processor nào chịu trách nhiệm?** Configuration parser/registry processor, autowiring/lifecycle BPP, AOP advisor, MVC handler mapping hay scheduler?
4. **Processor hoạt động lúc nào?** Trước bean creation, lúc injection/initialization, hay khi runtime request/method call diễn ra?
5. **Thiếu điều kiện gì?** Package scan, post-processor, dependency bean, transaction manager, web infrastructure, scope, proxy path hoặc callback lifecycle?
6. **Có bằng chứng quan sát được không?** Bean definition tồn tại, field đã inject, callback đã chạy, proxy thực thi, request mapping hoạt động hoặc transaction rollback thực tế?
7. **Có đường đăng ký khác không?** Loại khỏi component scan không loại khỏi `@Bean`/`@Import`.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): nền tảng annotation injection, `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor` và `<context:annotation-config/>`.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): phát hiện candidate class, stereotype, đăng ký bean definition và `@ComponentScan`.
- [Spring Framework 6.2 — Container Extension Points](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): phân biệt `BeanFactoryPostProcessor` và `BeanPostProcessor`, thời điểm chạy và lưu ý early initialization.
- [Spring Framework 6.2 — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html): điều kiện lifecycle callback và `CommonAnnotationBeanPostProcessor`.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definition và metadata.
- [Spring Framework 6.2 — ConfigurationClassPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ConfigurationClassPostProcessor.html): đăng ký và xử lý metadata của configuration class.

**Ghi nhớ:** **Component scanning** trả lời câu hỏi “Spring tự tìm và đăng ký class nào thành bean?”. **Annotation processing** trả lời câu hỏi “Khi đã có bean, hạ tầng Spring đọc metadata nào và làm gì với bean ấy?”. Một bean từ `@Bean` vẫn được xử lý injection/lifecycle, còn một class có `@Component` nằm ngoài mọi đường đăng ký vẫn không phải Spring bean.
