# Đăng ký initializer và listener trước khi khởi động — Spring Boot 3.3

## 1. Vì sao cần hook trước khi SpringApplication chạy?

Trong Spring Boot, lệnh `SpringApplication.run(...)` không chỉ gọi hàm `main`: nó chuẩn bị `Environment`, tạo `ApplicationContext`, nạp cấu hình và bean definitions, refresh context, rồi mới chạy các `ApplicationRunner`/`CommandLineRunner`. Một số nhu cầu phải được xử lý **trước** khi các bean thường được tạo:

- Bổ sung cấu hình hoặc đăng ký thành phần vào context trước khi refresh.
- Quan sát sự kiện ứng dụng vừa bắt đầu hoặc `Environment` mới được chuẩn bị.
- Ghi lại lỗi nếu startup thất bại, kể cả khi context chưa hoàn tất.
- Đóng gói hook dùng chung để tự áp dụng khi một ứng dụng Spring Boot khởi động.

Hai extension point liên quan trực tiếp là:

| Hook | Interface | Mục đích | Thời điểm |
| --- | --- | --- | --- |
| **Initializer** | `ApplicationContextInitializer<ConfigurableApplicationContext>` | Tùy biến context, đăng ký thông tin/cấu hình cần có trước refresh | Sau khi context được tạo, **trước khi refresh** |
| **Listener** | `ApplicationListener<E extends ApplicationEvent>` | Nhận event tương ứng và phản ứng theo từng mốc lifecycle | Khi event phát; có thể **trước cả khi context tồn tại** nếu đăng ký từ sớm |

Initializer và listener **không đồng nghĩa**. Initializer có callback `initialize(context)`, được áp dụng khi chuẩn bị một context. Listener có callback `onApplicationEvent(event)`, có thể chạy nhiều lần khi những sự kiện phù hợp xuất hiện. Cả hai cần được **đăng ký trước khi gọi `run(args)`** nếu muốn kiểm soát giai đoạn khởi động ban đầu.

## 2. Hiểu thứ tự khởi động trước khi viết code

Mốc chính của một lần startup thành công trong Spring Boot 3.3:

```text
main()
  │
  ├── new SpringApplication(App.class)
  ├── addInitializers(...) / addListeners(...)    ← đăng ký hook trước
  │
  └── run(args)
       ├── ApplicationStartingEvent               ← chưa tạo context
       ├── chuẩn bị Environment
       ├── ApplicationEnvironmentPreparedEvent    ← chưa tạo context
       ├── tạo ApplicationContext
       ├── gọi các ApplicationContextInitializer
       ├── ApplicationContextInitializedEvent     ← initializer đã chạy
       ├── nạp bean definitions
       ├── ApplicationPreparedEvent               ← chưa refresh
       ├── refresh context, tạo bean, khởi động web server nếu có
       ├── ContextRefreshedEvent                   ← event của Spring Framework
       ├── ApplicationStartedEvent                ← trước runner
       ├── LivenessState.CORRECT
       ├── ApplicationRunner / CommandLineRunner
       ├── ApplicationReadyEvent                  ← sau runner
       └── ReadinessState.ACCEPTING_TRAFFIC
```

Đây là **sơ đồ khái niệm**, đã lược bỏ các bước nội bộ và những event bổ sung như `WebServerInitializedEvent`. Nếu startup bị lỗi, Spring Boot phát `ApplicationFailedEvent`; lỗi xảy ra càng sớm thì càng ít thành phần đã tồn tại.

Hiểu ba ranh giới:

1. **Trước khi tạo context:** sự kiện `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` đã có thể xảy ra; không thể lấy Spring bean thông thường.
2. **Đã tạo context nhưng chưa refresh:** `ApplicationContextInitializer` nhận `ConfigurableApplicationContext`, có thể chuẩn bị thông tin cần dùng khi context refresh; các service/repository chưa chắc đã được tạo.
3. **Sau khi refresh:** bean thông thường đã có thể hoạt động, runner được gọi sau `ApplicationStartedEvent`, và `ApplicationReadyEvent` được phát sau runner.

Một `@Component` hoặc `@Bean` triển khai `ApplicationListener` chỉ được tạo khi container xử lý bean, nên **không nhận lại các event đã phát trước đó**. Với event cực sớm, phải đăng ký listener trực tiếp qua `SpringApplication` hoặc một cơ chế tự đăng ký ở bootstrap.

## 3. Cách đăng ký trực tiếp vào SpringApplication

Lời gọi tĩnh thông thường:

```java
SpringApplication.run(App.class, args);
```

khởi động ngay nên không có đoạn cấu hình `SpringApplication` trước khi chạy. Hãy tạo instance:

```java
SpringApplication app = new SpringApplication(App.class);
app.addInitializers(new MyContextInitializer());
app.addListeners(new MyEarlyListener());
app.run(args);
```

`MyContextInitializer` và `MyEarlyListener` trong đoạn ngắn trên là **tên tượng trưng**, cần được định nghĩa. Cả `addInitializers(...)` và `addListeners(...)` nhận một hoặc nhiều đối tượng hook. Phải dùng **chính instance đã được cấu hình** để gọi `run(args)`; nếu vô tình gọi thêm `SpringApplication.run(App.class, args)` ở nơi khác thì các hook không được truyền cho lần chạy mới.

Đừng đợi sau `run(args)` mới gọi `addListeners` hoặc `addInitializers`: lúc đó những mốc bootstrap quan trọng đã đi qua, hoặc `run` có thể đã ném exception.

## 4. Dự án Maven chạy được trên Java 21 và Spring Boot 3.3

Ví dụ sau khởi chạy **ứng dụng non-web** để dễ quan sát sự kiện. Initializer thêm một giá trị cấu hình mặc định với ưu tiên thấp; listener quan sát lúc `Environment` đã chuẩn bị; runner in giá trị được Spring đọc sau khi context refresh.

Cấu trúc:

```text
startup-hooks/
├── pom.xml
└── src/main/java/com/example/hooks/
    ├── HooksApplication.java
    ├── DefaultMessageInitializer.java
    └── EnvironmentReadyListener.java
```

### 4.1. Maven pom.xml

**Tệp `pom.xml`**:

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
    <artifactId>startup-hooks</artifactId>
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

`spring-boot-starter` đủ cho ví dụ CLI; không cần `spring-boot-starter-web` vì không có HTTP endpoint. Parent Boot quản lý phiên bản thư viện tương thích. Dòng 3.3 có yêu cầu tối thiểu Java 17, nhưng bài dùng JDK 21 để thống nhất môi trường thực hành.

### 4.2. ApplicationContextInitializer: chuẩn bị context trước refresh

**Tệp `src/main/java/com/example/hooks/DefaultMessageInitializer.java`**:

```java
package com.example.hooks;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class DefaultMessageInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        MapPropertySource defaults = new MapPropertySource(
                "hookDemoDefaults",
                Map.<String, Object>of("demo.message", "Xin chào từ initializer"));

        // addLast: cho phép nguồn cấu hình ưu tiên cao hơn ghi đè giá trị này.
        context.getEnvironment().getPropertySources().addLast(defaults);

        System.out.println("initializer: context created, before refresh");
    }
}
```

Giải thích:

- `initialize(...)` là phương thức do `SpringApplication` gọi trước refresh.
- `ConfigurableApplicationContext` cho phép truy cập `Environment` của context.
- `MapPropertySource` đại diện nguồn thuộc tính đặt tên `hookDemoDefaults`.
- `addLast` làm nguồn này có độ ưu tiên thấp so với các property sources hiện có, thuận tiện làm fallback.
- Thời điểm này thích hợp để **chuẩn bị thông tin cho bean creation**, nhưng **không phù hợp để tìm một service bean đã hoàn chỉnh bằng `context.getBean(...)`**.

Nếu mục tiêu chỉ là khai báo default properties, `SpringApplication.setDefaultProperties(Map)` thường gọn hơn. Ở đây chủ ý dùng initializer để học lifecycle.

### 4.3. ApplicationListener: bắt event trước khi context tồn tại

**Tệp `src/main/java/com/example/hooks/EnvironmentReadyListener.java`**:

```java
package com.example.hooks;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentReadyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("listener: environment prepared");
    }
}
```

`ApplicationEnvironmentPreparedEvent` xảy ra khi Spring Boot đã chuẩn bị `Environment`, **trước khi tạo `ApplicationContext`**. Có thể truy cập `event.getEnvironment()` để đọc cấu hình tại thời điểm đó; không thể trông chờ một controller hay service bean đã tồn tại. Cách dùng generic giúp nhận đúng loại sự kiện được quan tâm.

### 4.4. Lớp main: đăng ký trước khi gọi run

**Tệp `src/main/java/com/example/hooks/HooksApplication.java`**:

```java
package com.example.hooks;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class HooksApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(HooksApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Quan trọng: đăng ký hook TRƯỚC run(args).
        app.addInitializers(new DefaultMessageInitializer());
        app.addListeners(new EnvironmentReadyListener());

        app.run(args);
    }

    @Bean
    ApplicationRunner showMessage(Environment environment) {
        return arguments -> System.out.println(
                "runner: " + environment.getProperty("demo.message"));
    }
}
```

`@SpringBootApplication` giúp Spring Boot tìm các cấu hình/bean dưới package `com.example.hooks`. `@Bean ApplicationRunner` được khởi tạo sau khi context refresh và chạy sau `ApplicationStartedEvent`. Vì vậy, runner đọc được `demo.message` do initializer bổ sung trước đó.

### 4.5. Biên dịch, chạy và kiểm chứng

Trong thư mục `startup-hooks`, dùng JDK 21 và Maven:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Lọc riêng ba dòng `System.out.println` do ví dụ in; thứ tự là:

```text
listener: environment prepared
initializer: context created, before refresh
runner: Xin chào từ initializer
```

Console có thể còn log do Spring Boot in xen giữa; không coi khối trên là toàn bộ stdout. Thứ tự ba dòng là điều quan trọng: **listener chạy ở sự kiện trước context**, **initializer chạy khi context đã tạo**, **runner chạy sau refresh**.

Đóng gói JAR thực thi:

```bash
mvn package
java -jar target/startup-hooks-0.0.1-SNAPSHOT.jar
```

Thử nguồn cấu hình có độ ưu tiên cao hơn:

```bash
java -jar target/startup-hooks-0.0.1-SNAPSHOT.jar --demo.message=From-CLI
```

Dòng runner lúc này:

```text
runner: From-CLI
```

Vì command-line argument được Spring Boot đưa vào `Environment` với độ ưu tiên cao hơn nguồn `hookDemoDefaults` thêm bằng `addLast`. Trong ví dụ non-web, JVM thường kết thúc sau runner nếu không còn non-daemon thread giữ tiến trình chạy.

## 5. Đăng ký bằng SpringApplicationBuilder

`SpringApplicationBuilder` cung cấp API fluent với cùng ý nghĩa:

```java
package com.example.hooks;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class BuilderLauncher {
    public static void main(String[] args) {
        new SpringApplicationBuilder(HooksApplication.class)
                .web(WebApplicationType.NONE)
                .initializers(new DefaultMessageInitializer())
                .listeners(new EnvironmentReadyListener())
                .run(args);
    }
}
```

Đây là **launcher thay thế** cho `HooksApplication.main`, không cần chạy cả hai. Class cấu hình vẫn là `HooksApplication` nên bean `showMessage` vẫn được đăng ký. Nếu dùng builder, cần gắn `initializers(...)`/`listeners(...)` trước `run(args)` tương tự cách dùng instance.

Builder đặc biệt tiện khi quản lý nhiều `ApplicationContext` có quan hệ cha–con. Trong hierarchy, sự kiện có thể lan đến parent context; listener có thể nhận nhiều event cùng loại từ các context khác nhau, nên đừng mặc định mỗi loại event chỉ phát đúng một lần trên toàn hệ thống.

## 6. Tự đăng ký bằng META-INF/spring.factories

Với hook đóng gói trong thư viện hoặc được dùng lại ở nhiều ứng dụng, Spring Boot có thể tìm initializer/listener từ metadata classpath.

Tạo **tệp `src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.context.ApplicationContextInitializer=com.example.hooks.DefaultMessageInitializer
org.springframework.context.ApplicationListener=com.example.hooks.EnvironmentReadyListener
```

Hai khóa trên là tên interface đầy đủ của Spring Framework. Khi `spring.factories` nằm trên classpath, Spring Boot 3.3 có thể tự nạp các implementation trong quá trình bootstrap, không cần biết mã `main` khởi tạo `SpringApplication` theo cách nào.

**Thực hành một lần theo một cách:** để kiểm chứng `spring.factories`, hãy bỏ hai lời gọi `app.addInitializers(...)` và `app.addListeners(...)` khỏi `main`, rồi chạy lại. Nếu vừa đăng ký thủ công vừa dùng metadata, các instance hook có thể bị thêm trùng và tạo tác dụng phụ/lần gọi lặp ngoài ý muốn.

Lớp cần được tạo rất sớm, do đó nên có constructor không tham số có thể truy cập và không đòi hỏi constructor injection của Spring bean. Hai lớp trong ví dụ đáp ứng yêu cầu này.

**Không nhầm với cơ chế auto-configuration của Boot 3:** danh sách class auto-configuration được khai báo qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; nó **khác** với đăng ký listener/initializer qua các khóa `spring.factories` ở trên.

## 7. Các event quan trọng và cách chọn đúng hook

| Event / hook | Thời điểm | Cách sử dụng |
| --- | --- | --- |
| `ApplicationStartingEvent` | Ngay sau khi `run` bắt đầu, chưa có Environment hoàn chỉnh | Listener đăng ký rất sớm; không truy cập bean |
| `ApplicationEnvironmentPreparedEvent` | Environment sẵn sàng, chưa có context | Quan sát cấu hình và một số can thiệp ban đầu |
| `ApplicationContextInitializer.initialize` | Context vừa tạo, chưa refresh | Tùy biến context trước khi khởi tạo bean |
| `ApplicationContextInitializedEvent` | Sau initializer, trước nạp bean definitions | Theo dõi điểm hoàn tất initializer |
| `ApplicationPreparedEvent` | Definitions đã nạp, sắp refresh | Quan sát bước chuẩn bị context |
| `ApplicationStartedEvent` | Context đã refresh, trước runner | Theo dõi thời điểm startup gần hoàn tất |
| `ApplicationReadyEvent` | Runner đã được gọi | Thông báo ứng dụng đã ready |
| `ApplicationFailedEvent` | Startup ném lỗi | Ghi nhận cause; context có thể chưa tồn tại |

Phân biệt hook với các cơ chế liên quan:

- **`@EventListener` hoặc `ApplicationListener` bean:** phù hợp event xảy ra sau khi context quản lý bean đã sẵn sàng; không thay thế listener khởi tạo rất sớm.
- **`ApplicationRunner`/`CommandLineRunner`:** phù hợp tác vụ sau refresh nhưng trước ready, ví dụ kiểm tra dữ liệu ban đầu hoặc một bước khởi tạo hữu hạn.
- **`EnvironmentPostProcessor`:** phù hợp tùy biến `Environment` ở bootstrap sớm, đặc biệt khi thời điểm config loading có ý nghĩa. Đăng ký theo cơ chế Boot tương ứng; khác với context initializer.
- **`SpringApplication.setDefaultProperties(...)`:** lựa chọn đơn giản cho giá trị mặc định, không cần xây một initializer chỉ để thêm một property.
- **`BootstrapRegistryInitializer`:** hook giai đoạn bootstrap registry nâng cao, không đồng nghĩa với `ApplicationContextInitializer`.

Vì listener thường được gọi đồng bộ trên luồng phát event, tránh thực thi tác vụ nặng, tải mạng lâu, ghi dữ liệu lớn hoặc thao tác có thể khóa vô thời hạn trong các event startup. Logic dài nên chuyển sang lifecycle component hoặc runner được thiết kế rõ ràng với timeout và xử lý lỗi.

## 8. Bắt startup failure và sắp xếp thứ tự hook

Một listener có thể chuyên nhận `ApplicationFailedEvent` để ghi nhận lỗi **ngay cả khi context không khởi động thành công**.

**Tệp bổ sung `src/main/java/com/example/hooks/StartupFailureListener.java`**:

```java
package com.example.hooks;

import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("startup failed: " + failure.getClass().getSimpleName());
    }
}
```

Đăng ký **trước** lệnh `app.run(args)` trong `HooksApplication.main`:

```java
app.addListeners(new StartupFailureListener());
```

Listener này không in gì khi startup thành công. Nếu có exception, callback in tên kiểu exception ở mức nguyên nhân nhận được; cần đọc thêm stack trace và `Caused by` để xác định gốc lỗi. `ApplicationFailedEvent.getApplicationContext()` có thể trả `null` nếu context chưa được tạo; không dựa vào bean lúc xử lý lỗi rất sớm.

Khi một nhóm initializer/listener có phụ thuộc thứ tự, có thể triển khai `Ordered` hoặc dùng `@Order`. Ví dụ logic của một initializer cần chạy ưu tiên:

```java
// Minh họa phương thức bên trong class implements Ordered:
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

Đoạn trên **không phải file Java độc lập**. Để sử dụng phải import `org.springframework.core.Ordered` và thêm `Ordered` vào implements của class. `@Order`/`Ordered` chỉ quy định thứ tự xử lý giữa các hook phù hợp; không thay đổi thứ tự framework phát các event lifecycle.

## 9. Sự cố thường gặp

### 9.1. Listener có @Component nhưng không nhận event sớm

**Nguyên nhân:** Spring chưa tạo bean khi `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` được phát.

**Giải pháp:** chuyển sang đăng ký qua `SpringApplication.addListeners(...)`, builder hoặc `spring.factories`. Đảm bảo kiểu generic hoặc phương thức listener khớp đúng event.

### 9.2. Initializer không được gọi

Kiểm tra đã gọi `addInitializers` trước `run` chưa; có dùng đúng instance `SpringApplication` không; class có triển khai đúng `ApplicationContextInitializer` không; nếu dùng `spring.factories`, file và FQCN đã đúng chưa. Đừng thử đọc vùng cấu hình quá sớm rồi kết luận initializer “không hoạt động”: có thể property đã bị nguồn ưu tiên cao hơn ghi đè.

### 9.3. Gọi getBean trong initializer gây lỗi

**Nguyên nhân:** context chưa refresh; singleton/service có thể chưa tồn tại.

**Giải pháp:** chỉ chuẩn bị cấu hình, bean definition hoặc context ở hook này; đưa công việc cần bean sang giai đoạn sau refresh, ví dụ runner hoặc một bean lifecycle thích hợp.

### 9.4. Hook chạy hai lần

**Nguyên nhân:** cùng lớp được đăng ký trong cả `main` lẫn `spring.factories`, hoặc ứng dụng có nhiều context. **Giải pháp:** xác định một nguồn đăng ký; nếu dùng context hierarchy, phân biệt context nào phát event.

### 9.5. Thay đổi cấu hình không ảnh hưởng log/bootstrap

**Nguyên nhân:** initializer thực thi sau giai đoạn chuẩn bị `Environment`, trong khi một số cấu hình đã được Boot xử lý. **Giải pháp:** chọn `EnvironmentPostProcessor` hoặc listener EnvironmentPrepared nếu thật sự cần can thiệp trước context; dùng `setDefaultProperties` cho mặc định đơn giản.

### 9.6. Startup bị treo hoặc lỗi do listener

**Nguyên nhân:** listener gọi network mà không có timeout, chạy logic nặng hoặc ném exception. **Giải pháp:** hook phải ngắn, có logging và xử lý lỗi; chuyển công việc cần chạy sau refresh sang runner với giới hạn tài nguyên rõ ràng.

### 9.7. Nhầm Started và Ready

`ApplicationStartedEvent` đến sau refresh **trước** runner; `ApplicationReadyEvent` đến **sau** runner. Đừng báo đã hoàn tất tác vụ runner ngay khi chỉ mới nhận `ApplicationStartedEvent`.

## 10. Bài tập tự kiểm tra

1. Giải thích vì sao ba dòng trong ví dụ mục 4 có thứ tự listener → initializer → runner, dù initializer và listener được đăng ký trước `run`.
2. Nếu đổi `EnvironmentReadyListener` sang `@Component` mà bỏ `addListeners`, callback `ApplicationEnvironmentPreparedEvent` còn được gọi không? Vì sao?
3. Chạy ứng dụng với `--demo.message=From-CLI`. Xác định giá trị runner nhận và vai trò của `addLast`.
4. Đăng ký thêm listener cho `ApplicationContextInitializedEvent`; đối chiếu thời điểm nó xuất hiện với initializer.
5. Chuyển hook sang `META-INF/spring.factories`, bỏ lệnh đăng ký trong `main` và kiểm tra lại chuỗi startup.
6. Viết một `StartupFailureListener`, tạo lỗi startup có kiểm soát để quan sát lỗi; không giả định context tồn tại trong callback.
7. Chọn hook phù hợp cho ba tình huống: bổ sung default property, tùy biến context trước refresh, và thực hiện tác vụ cần một service bean đã được khởi tạo.
8. Vì sao `@Order` không khiến `ApplicationReadyEvent` xảy ra trước `ApplicationStartedEvent`?

Sau bài này, cần đạt được khả năng **đăng ký initializer/listener trước khi khởi động**, xác định sự khác biệt giữa event sớm, pre-refresh và post-refresh, cùng cách tìm lỗi khi hook không được gọi.

## 11. Tài liệu chính thức

- Spring Boot 3.3.13 — SpringApplication và thứ tự application events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — API SpringApplication (`addInitializers`, `addListeners`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework 6.1 — IoC container và lifecycle: https://docs.spring.io/spring-framework/reference/core/beans.html
