# Nạp nguồn định nghĩa bean trước khi refresh — Spring Boot 3.3

## 1. Mục tiêu bài học

Trong chuỗi khởi động Spring Boot, `SpringApplication` cần nạp **nguồn cấu hình ban đầu** vào `ApplicationContext` trước khi gọi `refresh()`. Các nguồn này giúp Spring biết những lớp cấu hình nào cần phân tích để tiếp tục tìm `@Component`, xử lý `@Bean`, `@Import` và auto-configuration.

Sau bài này, bạn cần:

- Phân biệt **configuration source**, **BeanDefinition** và **bean instance**.
- Giải thích vị trí của bước `SpringApplication.load(context, sources)` trong quá trình khởi động.
- Hiểu tại sao `@SpringBootApplication` được nạp trước refresh, nhưng một `@Service` có thể chỉ được phát hiện khi refresh.
- Biết cách truyền thêm source, đăng ký definition ở giai đoạn pre-refresh và quan sát kết quả an toàn.
- Chạy ví dụ Java 21/Spring Boot 3.3; nhận biết các lỗi do thiếu source, scan sai package, điều kiện cấu hình hoặc tạo bean thất bại.

**Điểm cần nhớ:** nạp nguồn trước refresh **không có nghĩa mọi bean đã tồn tại**. Bước nạp đưa định nghĩa gốc vào registry; việc phân tích annotation, phát hiện components và tạo instances còn được Spring thực hiện trong giai đoạn refresh.

## 2. Phân biệt nguồn, định nghĩa và đối tượng

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **Source** | Đầu vào để nạp cấu hình | `App.class`, `ExtraConfiguration.class` |
| **BeanDefinition** | Metadata mô tả cách Spring tạo/quản lý bean: tên, kiểu, scope, factory method, lazy, phụ thuộc... | Definition tên `greetingService` |
| **Bean instance** | Đối tượng Java thật đã được khởi tạo và quản lý bởi container | Instance `GreetingService` |
| **BeanDefinitionRegistry** | Thành phần cho phép đăng ký và tra cứu bean definitions | Registry của `ApplicationContext` phù hợp |
| **ApplicationContext** | Container Spring quản lý definitions, instances, môi trường và lifecycle | Context của ứng dụng non-web hoặc web |

Có ba bước khác nhau:

1. **Khai báo source:** `new SpringApplication(App.class)` xác định class cấu hình gốc.
2. **Đăng ký BeanDefinition:** trong quá trình chuẩn bị context và xử lý configuration, Spring biết cách tạo các bean.
3. **Khởi tạo bean:** trong refresh (đối với singleton non-lazy thông thường), Spring gọi factory/constructor, inject phụ thuộc và chạy các callback cần thiết.

Một BeanDefinition có thể đã tồn tại dù bean chưa được tạo. Với bean `@Lazy`, instance có thể chỉ được khởi tạo khi được yêu cầu sau đó. Ngược lại, việc class mang `@Component` tồn tại trong source code chưa chứng minh Spring đã tìm thấy class ấy: nó còn phải nằm trong phạm vi scan hoặc được đăng ký theo cơ chế khác.

Ví dụ:

```java
@SpringBootApplication
class DemoApplication { }

@Service
class GreetingService { }
```

`DemoApplication.class` là source; `GreetingService.class` là component cần được tìm thấy qua `@ComponentScan`. Spring Boot có thể nạp definition của `DemoApplication` trước refresh, còn definition cho `GreetingService` được đăng ký khi configuration processing diễn ra trong refresh.

## 3. Thứ tự các bước liên quan trong SpringApplication

Sơ đồ sau là trình tự **khái niệm** cho một lần startup thành công trên Spring Boot 3.3:

```text
main(args)
  |
  +-- new SpringApplication(DemoApplication.class)
  |     +-- Ghi nhận primary source(s)
  |
  +-- application.run(args)
        |
        +-- ApplicationStartingEvent
        +-- Chuẩn bị Environment, profiles, cấu hình ngoài
        +-- ApplicationEnvironmentPreparedEvent
        +-- Tạo ApplicationContext
        |
        +-- prepareContext(...)
        |     +-- Gắn Environment vào context
        |     +-- Chạy ApplicationContextInitializer
        |     +-- ApplicationContextInitializedEvent
        |     +-- Đăng ký các bean hạ tầng ban đầu
        |     +-- load(context, sources)          <-- NẠP NGUỒN GỐC
        |     +-- ApplicationPreparedEvent
        |
        +-- refreshContext(context)
        |     +-- BeanDefinitionRegistryPostProcessor
        |     |     +-- ConfigurationClassPostProcessor
        |     |           +-- Xử lý @Configuration, @ComponentScan
        |     |           +-- Xử lý @Import, @Bean, auto-configuration
        |     +-- BeanFactoryPostProcessor
        |     +-- Đăng ký BeanPostProcessor
        |     +-- Khởi tạo singleton non-lazy thông thường
        |     +-- Hoàn tất refresh
        |
        +-- ApplicationStartedEvent
        +-- Chạy ApplicationRunner / CommandLineRunner
        +-- ApplicationReadyEvent
```

Thứ tự trên đã lược bỏ một số callback nội bộ, nhưng phản ánh những ranh giới cần biết:

- `ApplicationContextInitializer.initialize(context)` chạy khi context **đã được tạo nhưng chưa refresh và trước khi primary sources được load**. Tại thời điểm này không thể mặc định mọi definition từ source chính đã có.
- `SpringApplication.load(context, sources)` nạp các **nguồn gốc** vào registry, thường thông qua cơ chế cho annotated class. Bước này thuộc `prepareContext(...)`.
- `ApplicationPreparedEvent` được phát **sau khi load sources và trước refresh**. Đây là điểm quan sát thích hợp nếu muốn xác nhận source chính đã được đăng ký.
- `refreshContext(context)` kích hoạt xử lý configuration classes, component scan, bean factory post-processors, khởi tạo singleton thông thường, cùng các phần lifecycle còn lại.
- `ApplicationStartedEvent` đến sau khi context refresh; `ApplicationReadyEvent` đến sau khi các runner được gọi.

**Không nhầm `ApplicationContextInitializedEvent` với `ApplicationPreparedEvent`.** Event đầu tiên diễn ra sau initializers nhưng trước load primary sources. Event thứ hai diễn ra khi sources đã được load và context đang chuẩn bị refresh.

## 4. Spring Boot nạp những nguồn nào?

### 4.1. Class khởi động là primary source

Một ứng dụng thường viết:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`DemoApplication.class` là **primary source**. Annotation `@SpringBootApplication` kết hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration`, `@ComponentScan`.

Nạp source không đồng nghĩa Spring đã thực thi ngay mọi annotation. Trong refresh, `ConfigurationClassPostProcessor` xử lý cấu hình Java và đăng ký definitions phát sinh, trong đó có kết quả của component scan và các phương thức `@Bean`.

### 4.2. Truyền nhiều primary sources

Có thể đưa thêm configuration classes trực tiếp:

```java
SpringApplication application = new SpringApplication(
        DemoApplication.class,
        ExtraConfiguration.class);
application.run(args);
```

Đây là **đoạn minh họa**, giả định hai class trên tồn tại. Spring Boot nhận cả hai như sources. Nếu `ExtraConfiguration` có `@Configuration`, definition của configuration class có thể đã có ở mốc prepared; các `@Bean` methods bên trong vẫn được xử lý trong refresh.

Ngoài class, cơ chế nạp của Spring Boot còn hỗ trợ một số dạng source thích hợp như package name và resource cấu hình. Tuy nhiên, trong dự án Boot 3.3 dùng Java configuration, các class cấu hình rõ ràng cùng `@Import`/`@ComponentScan` thường dễ kiểm soát hơn.

### 4.3. Định nghĩa phát sinh từ source

- **`@ComponentScan`:** tìm các class mang `@Component`, `@Service`, `@Repository`, `@Controller` trong phạm vi cấu hình, sau đó đăng ký BeanDefinition.
- **`@Import`:** đưa thêm configuration class hoặc các thành phần import khác vào quá trình phân tích.
- **`@Bean`:** đánh dấu factory method tạo một bean; bean definition được đăng ký qua configuration processing.
- **`@EnableAutoConfiguration`:** kích hoạt auto-configurations có điều kiện theo classpath, properties, profiles và các bean hiện có.
- **`@Conditional` và `@Profile`:** có thể khiến một số định nghĩa không được đăng ký dù configuration source đã được nạp.

Vì thế không được suy luận rằng một `ApplicationPreparedEvent` listener sẽ nhìn thấy đầy đủ các service, repository hoặc bean do auto-configuration tạo ra. Nhiều phần chỉ được xử lý sau đó trong refresh.

## 5. Dự án thực hành Java 21 + Spring Boot 3.3

Ứng dụng sau chạy ở chế độ **non-web** để tập trung vào bootstrap. Nó kiểm tra ba mốc: initializer trước source load, listener prepared sau source load, runner sau refresh.

### 5.1. Cấu trúc tệp

```text
bean-source-demo/
├── pom.xml
└── src/main/java/com/example/startup/
    ├── BeanSourceApplication.java
    └── GreetingService.java
```

### 5.2. Maven pom.xml

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bean-source-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 yêu cầu tối thiểu Java 17; ở đây cấu hình dùng JDK 21. `spring-boot-starter` chứa các thành phần cơ bản và không cần thêm starter web cho ví dụ CLI.

### 5.3. Service được quét trong refresh

Tệp `src/main/java/com/example/startup/GreetingService.java`:

```java
package com.example.startup;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String message() {
        return "Xin chào từ service";
    }
}
```

Spring tìm thấy class này qua component scan mặc định của `@SpringBootApplication` khi refresh xử lý cấu hình. Chỉ việc có annotation `@Service` trong file Java không khiến bean được tạo ngay khi chương trình bắt đầu.

### 5.4. Main class với ba điểm quan sát

Tệp `src/main/java/com/example/startup/BeanSourceApplication.java`:

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanSourceApplication {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(BeanSourceApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // Đã có context, primary source chưa load.
        application.addInitializers(context -> {
            boolean present = context.containsBeanDefinition("beanSourceApplication");
            System.out.println("1. initializer: source definition = " + present);
        });

        // Sau khi load primary source, trước refresh.
        application.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event -> {
                    var context = event.getApplicationContext();

                    boolean source = context.containsBeanDefinition("beanSourceApplication");
                    boolean service = context.containsBeanDefinition("greetingService");

                    System.out.println("2. prepared: source definition = " + source);
                    System.out.println("3. prepared: service definition = " + service);
                });

        application.run(args);
    }

    @Bean
    ApplicationRunner inspectAfterRefresh(
            ApplicationContext context,
            GreetingService service) {

        return args -> {
            System.out.println("4. runner: service available = "
                    + context.containsBean("greetingService"));
            System.out.println("5. runner: " + service.message());
        };
    }
}
```

**Giải thích từng điểm quan sát:**

1. `new SpringApplication(BeanSourceApplication.class)` ghi nhận source nhưng chưa tạo context.
2. Initializer chạy trước `load(context, sources)`, vì vậy `containsBeanDefinition("beanSourceApplication")` trả `false`.
3. Khi `ApplicationPreparedEvent` phát, Boot đã đăng ký definition của class main, với tên mặc định `beanSourceApplication`. Vì vậy kết quả là `true`.
4. Component scan được xử lý trong refresh. Ở prepared event, `greetingService` chưa được phát hiện từ annotation `@Service`, nên `containsBeanDefinition("greetingService")` là `false`.
5. Sau refresh, Spring đã xử lý service và phương thức `@Bean inspectAfterRefresh`; runner được tiêm `GreetingService` và chạy sau `ApplicationStartedEvent`.

`containsBeanDefinition(...)` kiểm tra **metadata của definition**. `containsBean(...)` cho biết tên bean có trong container, không có nghĩa mọi `@Lazy` bean đều đã được tạo. Không gọi `getBean(GreetingService.class)` trong initializer hoặc prepared listener để buộc bean xuất hiện sớm; lúc đó context chưa hoàn tất refresh.

### 5.5. Biên dịch, chạy, xem stdout

Trong thư mục `bean-source-demo`, sử dụng JDK 21 và Maven:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Năm dòng do mã ví dụ chủ động in có thứ tự và nội dung:

```text
1. initializer: source definition = false
2. prepared: source definition = true
3. prepared: service definition = false
4. runner: service available = true
5. runner: Xin chào từ service
```

Console thật còn có Spring Boot banner và logging nên có thể xuất hiện các dòng khác xen giữa. Đầu ra trên mô tả **riêng các dòng `System.out.println`**, không phải toàn bộ stdout.

Đóng gói và chạy JAR:

```bash
mvn package
java -jar target/bean-source-demo-0.0.1-SNAPSHOT.jar
```

Vì đã chọn `WebApplicationType.NONE`, ứng dụng không mở cổng HTTP. Khi runner hoàn tất và không có non-daemon thread khác giữ JVM, tiến trình sẽ kết thúc.

### 5.6. Thí nghiệm: source class ở ngoài component scan

Tạo configuration ở package `com.example.extra`, bên ngoài phạm vi scan mặc định của `com.example.startup`.

Tệp `src/main/java/com/example/extra/FeatureConfiguration.java`:

```java
package com.example.extra;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    public String featureMessage() {
        return "Feature từ nguồn bổ sung";
    }
}
```

Thay dòng tạo application trong `BeanSourceApplication.main()` bằng:

```java
// Cần import com.example.extra.FeatureConfiguration.
SpringApplication application = new SpringApplication(
        BeanSourceApplication.class,
        FeatureConfiguration.class);
```

Đây là **đoạn thay thế trong class main**, không phải chương trình độc lập. Vì `FeatureConfiguration.class` được truyền trực tiếp làm source, definition của class có mặt sau `load(context, sources)` ngay cả khi nằm ngoài package được scan.

Trong listener prepared, có thể bổ sung:

```java
System.out.println("prepared: feature config = "
        + context.containsBeanDefinition("featureConfiguration"));
System.out.println("prepared: featureMessage = "
        + context.containsBeanDefinition("featureMessage"));
```

Kỳ vọng `true` cho source class và `false` cho bean từ `@Bean` method ở mốc prepared. Khi refresh xử lý cấu hình, definition cho `featureMessage` được thêm và bean có thể được tạo theo lifecycle.

## 6. Các cơ chế bổ sung: trước refresh và trong refresh

### 6.1. Cách thông dụng: @Configuration và @Bean

Trong hầu hết dự án, nên dùng `@Configuration`, `@Bean`, `@Import` và `@ComponentScan` để Spring quản lý phụ thuộc và vòng đời rõ ràng. Ví dụ một bean của thư viện Java chuẩn:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Đây là **lớp bổ sung cần nằm trong dự án Spring** và package phù hợp hoặc được import; không phải chương trình Java độc lập. Spring đăng ký definition cho `clock` khi xử lý cấu hình trong refresh.

### 6.2. Programmatic BeanDefinition trong initializer

Với hạ tầng cần chuẩn bị một definition rất sớm, có thể dùng `ApplicationContextInitializer` với `BeanDefinitionRegistry`.

Ví dụ **đoạn bổ sung trong `main`** sau khi đã tạo biến `application`, trước `application.run(args)`:

```java
// Các import đặt ở đầu file:
// import java.time.Clock;
// import org.springframework.beans.factory.support.BeanDefinitionBuilder;
// import org.springframework.beans.factory.support.BeanDefinitionRegistry;

application.addInitializers(context -> {
    if (!(context instanceof BeanDefinitionRegistry registry)) {
        throw new IllegalStateException("No BeanDefinitionRegistry");
    }

    registry.registerBeanDefinition(
            "bootClock",
            BeanDefinitionBuilder.genericBeanDefinition(
                    Clock.class, Clock::systemUTC).getBeanDefinition());
});
```

Đoạn này **không biên dịch độc lập**; cần các import đã liệt kê, các dependency của Spring và biến `application` từ main. Với các context Spring Boot thông dụng, registry sẵn có. Với context tùy chỉnh, kiểm tra interface trước như ví dụ. Definition `bootClock` được đưa vào registry trước refresh; lúc refresh Spring có thể dùng supplier `Clock::systemUTC` để tạo instance.

**Ưu tiên `@Bean Clock clock()` nếu không cần hook cấp thấp.** Đăng ký dynamic làm code khó kiểm tra và có nguy cơ trùng tên bean.

### 6.3. Phân biệt các post-processor

| Cơ chế | Thời điểm | Tác dụng |
| --- | --- | --- |
| `ApplicationContextInitializer` | Trước khi load primary sources, trước refresh | Tùy biến context, có thể đăng ký metadata ban đầu |
| `SpringApplication.load(...)` | Sau initializer, trước refresh | Nạp primary sources vào registry |
| `BeanDefinitionRegistryPostProcessor` | Trong refresh | Bổ sung hoặc sửa bean definitions trước tạo bean |
| `ConfigurationClassPostProcessor` | Trong refresh, là registry post-processor | Phân tích configuration, scan, import, `@Bean` |
| `BeanFactoryPostProcessor` | Trong refresh, trước khi khởi tạo singleton thông thường | Thay đổi metadata/config của BeanFactory |
| `BeanPostProcessor` | Khi tạo bean instances | Can thiệp quá trình initialization, hỗ trợ cơ chế như proxy |

Đừng tự gọi `context.refresh()` trong initializer hoặc event prepared: `SpringApplication` sở hữu trình tự bootstrap. Cũng đừng dùng `BeanPostProcessor` như công cụ nạp primary sources, vì nó hoạt động ở giai đoạn bean instances.

## 7. Khắc phục lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Bean chưa được đăng ký, package không được scan, điều kiện `@Profile`/`@Conditional` không thỏa | Kiểm tra primary source, package, `@Import`, config và điều kiện |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng kiểu cần inject | Dùng `@Qualifier`, `@Primary` hoặc thiết kế lại interface |
| `BeanDefinitionOverrideException` | Nhiều definitions trùng tên khi không cho phép override | Tìm chỗ đăng ký lặp, đổi tên hoặc bỏ nguồn trùng |
| `BeanCreationException` | Definition có nhưng constructor, injection hay factory method thất bại | Đọc `Caused by` trong stack trace |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu dependency hoặc phiên bản thư viện không tương thích | Xem Maven dependency tree/BOM, kiểm tra Java version |
| `@Service` chưa thấy ở prepared event | Component scan chưa được xử lý vì chưa refresh | Quan sát sau refresh thay vì ép tạo bean sớm |
| `@Bean` method không chạy ngay | Bean là lazy hoặc chỉ có definition, instance chưa được yêu cầu | Phân biệt đăng ký definition với khởi tạo instance |
| Auto-configuration thiếu bean | `@ConditionalOnClass`, `@ConditionalOnMissingBean` hoặc properties không khớp | Xem condition evaluation report, thử `--debug` |
| Initializer gọi `getBean` rồi thất bại | Context chưa refresh, dependency graph chưa hoàn tất | Dời công việc cần bean sang runner/bean lifecycle |

Để debug có hệ thống:

1. Kiểm tra class truyền cho `SpringApplication.run(...)` hoặc constructor `SpringApplication`.
2. Kiểm tra package của main class so với các `@Component`/`@Service`.
3. Kiểm tra `@Configuration`, `@Import`, `@Bean`, profiles và conditional annotations.
4. Xác định thời điểm đang quan sát: initializer, prepared event, trong refresh hay runner.
5. Đọc nguyên nhân gốc (`Caused by`) của lỗi; không thêm annotation/dependency ngẫu nhiên.
6. Với auto-configuration, dùng tham số `--debug` để xem các điều kiện match/no-match.
7. Nếu gặp thư viện cũ, kiểm tra sự tương thích với Spring Framework 6/Boot 3 và namespace Jakarta nơi áp dụng.

### Về bean overriding

Spring Boot mặc định tránh ghi đè bean definition trùng tên. Thuộc tính `spring.main.allow-bean-definition-overriding` có thể thay đổi điều này nhưng không nên bật chỉ để che giấu cấu hình trùng. Hãy sửa nguồn đăng ký đúng cách.

### Về lazy initialization

`@Lazy` ảnh hưởng thời điểm **tạo instance**, không đồng nghĩa definition chưa được đăng ký. `containsBeanDefinition("someBean")` có thể trả `true` trong khi constructor chưa từng chạy.

### Về source ngoài package

Nếu một class nằm ngoài phạm vi scan, chỉ đổi tên package hoặc thêm dependency chưa đủ. Cần chỉ định cách đăng ký hợp lệ: import configuration, truyền primary source bổ sung hoặc cấu hình lại phạm vi scan có chủ đích.

## 8. Bài tập kiểm tra

1. Giải thích source, BeanDefinition và instance bằng ví dụ của `GreetingService`.
2. Vì sao initializer thấy `beanSourceApplication = false`, nhưng prepared listener thấy `true`?
3. Vì sao `greetingService` chưa xuất hiện trong prepared event? Thành phần nào của Spring sẽ tìm nó?
4. Bỏ `@Service` khỏi `GreetingService`, chạy lại và xác định lỗi; khắc phục bằng cấu hình `@Bean`.
5. Chuyển service ra ngoài package `com.example.startup` và giải thích vì sao nó không được scan.
6. Thêm `FeatureConfiguration` làm primary source rồi so sánh thời điểm definition class và `@Bean featureMessage` xuất hiện.
7. Phân biệt `ApplicationContextInitializer` với `BeanDefinitionRegistryPostProcessor` và `BeanPostProcessor`.
8. Vì sao `context.getBean(...)` hoặc tự gọi `refresh()` từ initializer có thể gây lỗi?
9. Giải thích một trường hợp BeanDefinition có nhưng instance chưa được tạo.
10. Vẽ lại chuỗi `source -> load -> prepared -> refresh -> started -> runners -> ready` và đánh dấu lúc `@ComponentScan` được xử lý.

**Đạt yêu cầu** khi tự chạy được ví dụ Maven với năm dòng kết quả theo đúng thứ tự, hiểu vì sao các boolean lần lượt là `false`, `true`, `false`, `true`, và phân biệt rõ **nạp nguồn ban đầu trước refresh** với **phân tích cấu hình và tạo bean trong refresh**.

## 9. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — API SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework — BeanFactory Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
