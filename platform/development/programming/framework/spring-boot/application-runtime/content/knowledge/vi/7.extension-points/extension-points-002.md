# ApplicationContextInitializer và thao tác trước refresh

## 1. Khi nào cần can thiệp trước lúc Spring refresh context?

Một ứng dụng Spring Boot không tạo toàn bộ bean ngay khi JVM bắt đầu. `SpringApplication` chuẩn bị `Environment`, tạo `ApplicationContext`, nạp nguồn cấu hình và bean definition, rồi gọi `refresh()` để thực hiện các bước thiết lập container và khởi tạo những bean cần thiết.

Nếu phải **cấu hình một context đã được tạo nhưng chưa refresh**, Spring Framework cung cấp callback `ApplicationContextInitializer`. Spring Boot biết cách gọi callback này trong giai đoạn bootstrap trước khi nạp các primary sources và trước khi gọi `refresh()`.

Các nhu cầu phù hợp bao gồm:

- Thêm một nguồn property để các bean được tạo sau đó có thể đọc.
- Gán ID hoặc cấu hình một thuộc tính của context trước khi refresh.
- Đăng ký bean definition bằng code, trong loại context hỗ trợ.
- Gắn `BeanFactoryPostProcessor` để Spring gọi vào đúng giai đoạn xử lý bean factory.
- Tạo một điểm tích hợp bootstrap cho thư viện cần cung cấp thông tin trước khi ứng dụng dựng các bean.

**Nguyên tắc:** initializer làm việc ở **pha cấu hình container**. Nó không phải nơi sử dụng repository, HTTP client, bean đã inject hay chạy tác vụ nghiệp vụ sau startup.

Nội dung áp dụng cho **Spring Boot 3.3.x**, **Spring Framework 6.1.x** và **Java 17+**. Tên class, thời điểm event và API nên được đối chiếu khi nâng major version.

## 2. Hợp đồng API và ý nghĩa của “trước refresh”

Interface chính:

```java
package org.springframework.context;

@FunctionalInterface
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

Đây là **chữ ký rút gọn để học**, không phải một file cần tự định nghĩa lại trong dự án. Spring đã cung cấp interface này. Tham số `C` là một loại `ConfigurableApplicationContext`; callback `initialize(C)` nhận context đã được tạo và chuẩn bị, **chưa được refresh**.

`ConfigurableApplicationContext` cho phép truy cập `ConfigurableEnvironment`, đặt context ID, thêm post-processor, điều chỉnh một số thành phần hạ tầng. Với loại `GenericApplicationContext`, có thể gọi `registerBean(...)` để đăng ký bean definition sớm.

**Không đồng nghĩa** với các điều sau:

- Context đã `isActive() == true`: chưa, trong initializer thông thường là `false`.
- Tất cả bean definitions đã được nạp: chưa; primary sources của Boot được nạp **sau** các initializer.
- Bean được tạo và `@PostConstruct` đã chạy: chưa; phần lớn xử lý bean xảy ra trong refresh.
- `ApplicationRunner` đã chạy: chưa; runner nằm sau refresh và `ApplicationStartedEvent`.
- Web server đang nhận request: chưa thể suy ra từ thời điểm này.

Nếu initializer gọi `context.getBean(SomeService.class)`, thao tác có thể thất bại vì context chưa refresh/bean chưa có. Nên **đăng ký định nghĩa** để Spring tạo bean ở bước sau thay vì tạo dependency graph quá sớm.

## 3. Vị trí chính xác trong chuỗi khởi động Spring Boot 3.3

```text
main() -> new SpringApplication(MyApp.class)
         -> addInitializers(...) / addListeners(...)
         -> run(args)
              |
              +--> ApplicationStartingEvent
              +--> chuẩn bị Environment, ConfigData, command-line options
              +--> ApplicationEnvironmentPreparedEvent
              +--> tạo ApplicationContext phù hợp
              +--> gắn Environment vào context
              |
              +--> ApplicationContextInitializer.initialize(context)
              |      ^ context đã tạo, chưa refresh
              |
              +--> ApplicationContextInitializedEvent
              |      ^ initializer đã chạy, primary sources chưa nạp
              |
              +--> nạp primary bean definitions / sources
              +--> ApplicationPreparedEvent
              |      ^ sources đã nạp, context chưa refresh
              |
              +--> refresh(context)
              |      +--> bean factory/registry post-processors
              |      +--> wiring, tạo singleton, lifecycle callbacks
              |      +--> web server setup nếu có
              |
              +--> ApplicationStartedEvent
              +--> ApplicationRunner / CommandLineRunner
              +--> ApplicationReadyEvent
              +--> return ApplicationContext
```

Từ sơ đồ cần phân biệt **ba trạng thái**: context đã tồn tại, definitions đã được nạp, và context đã được refresh. `ApplicationContextInitializer` hoạt động ở trạng thái thứ nhất. `ApplicationPreparedEvent` thuộc trạng thái thứ hai. `ApplicationStartedEvent` thuộc trạng thái thứ ba.

Spring Boot có thể thêm sự kiện/processor khác giữa các mốc, nhất là với ứng dụng web hoặc nhiều context. Nhưng thứ tự tương đối trên là hợp đồng quan trọng cho Boot 3.3.x.

### 3.1. Vì sao ApplicationContextInitializedEvent không có nghĩa là đã có bean?

`ApplicationContextInitializedEvent` được Boot phát **sau khi gọi toàn bộ initializer nhưng trước khi nạp bean definitions chính**. Tên “Initialized” ở đây mô tả giai đoạn chuẩn bị context, không mang nghĩa singleton đã khởi tạo.

`ApplicationPreparedEvent` là mốc khác: nó xuất hiện **sau khi bean definitions đã được nạp nhưng trước refresh**. Nếu cần tác động lên definitions đã có, thường dùng post-processor hoặc sự kiện phù hợp thay vì giả định initializer thấy đủ definitions.

### 3.2. Environment đã sẵn sàng nhưng đã xử lý bước sớm

Đến lúc initializer được gọi, `Environment` đã được chuẩn bị và gắn vào context. Một số quyết định như nạp config data, profile-specific configuration và chọn loại context đã xảy ra trước đó. Vì vậy “trước refresh” **không** đồng nghĩa với “có thể thay đổi mọi cấu hình bootstrap”.

## 4. Những thao tác phù hợp trong initializer

| Thao tác | Có nên thực hiện? | Lý do |
| --- | --- | --- |
| Đọc `context.getEnvironment().getProperty(...)` | Có | Environment đã tồn tại |
| Thêm `PropertySource` | Có | Giá trị có thể được đọc trong quá trình tạo bean tiếp theo |
| `context.setId("...")` | Có khi cần | Đặt định danh context trước refresh |
| `context.addBeanFactoryPostProcessor(...)` | Có | Đăng ký processor được gọi trong refresh |
| `GenericApplicationContext.registerBean(...)` | Có, khi context thuộc loại này | Đăng ký định nghĩa bean, không sử dụng bean quá sớm |
| Gọi `getBean(OrderService.class)` | Không nên | Bean factory và singleton chưa ở trạng thái dùng bình thường |
| Tự gọi `context.refresh()` | Không | Boot chịu trách nhiệm refresh và lifecycle |
| Đợi `@Autowired` inject service vào initializer | Không mặc định | Initializer thường do bootstrap tạo từ trước, không phải một Spring bean |
| Gọi database để preload dữ liệu bằng repository bean | Không phù hợp | Repository cần context hoàn chỉnh; dùng runner sau refresh |
| Đổi web application type ngay lúc này | Không đáng tin | Loại context đã được chọn và tạo trước initializer |
| Thay active profiles để Boot đọc lại toàn bộ ConfigData | Không đáng tin | Việc xử lý ConfigData theo profile có thể đã hoàn tất |

**Điều kiện type:** `ApplicationContextInitializer<ConfigurableApplicationContext>` làm việc với abstraction chung. Chỉ dùng API của `GenericApplicationContext` sau khi kiểm tra `instanceof`, vì các loại context hoặc context factory tùy biến có thể khác nhau.

## 5. Ví dụ chạy được: initializer thay đổi Environment và đăng ký bean

Mục tiêu thí nghiệm: in thứ tự sự kiện, xác nhận `isActive()` còn false trong initializer, đăng ký một bean không có `@Component`, rồi chứng minh một `ApplicationRunner` sau refresh nhận được bean và property.

### 5.1. Cấu hình dự án Java 17 / Spring Boot 3.3

Tạo dự án Gradle Groovy có Gradle Wrapper và `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`settings.gradle`:

```groovy
rootProject.name = 'context-initializer-lab'
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Dùng non-web context để thí nghiệm không phụ thuộc HTTP server và dễ xem thứ tự log.

### 5.2. Một file Java đầy đủ

Tạo file **`src/main/java/com/example/initializer/InitializerLabApplication.java`**:

```java
package com.example.initializer;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class InitializerLabApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitializerLabApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Đăng ký initializer từ bootstrap, không cần @Component.
        app.addInitializers(new EarlySetup());

        // Early events: đăng ký listener trực tiếp với SpringApplication.
        app.addListeners(
                (ApplicationListener<ApplicationContextInitializedEvent>) event ->
                        System.out.println("02 ContextInitializedEvent"));
        app.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event ->
                        System.out.println("03 ApplicationPreparedEvent"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("07 main after run: " + context.isActive());
        }
    }

    static final class EarlySetup
            implements ApplicationContextInitializer<ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            System.out.println("01 initializer active: " + context.isActive());

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "initializer-demo",
                            Map.<String, Object>of(
                                    "demo.message", "Xin chào từ initializer")));

            if (!(context instanceof GenericApplicationContext generic)) {
                throw new IllegalStateException(
                        "Bài thực hành cần GenericApplicationContext");
            }

            // Chỉ đăng ký định nghĩa bean, không gọi getBean().
            generic.registerBean(StartupMarker.class, StartupMarker::new);
        }
    }

    // Không có @Component: chỉ do initializer đăng ký.
    static final class StartupMarker {
        String label() {
            return "bean đã đăng ký sớm";
        }
    }

    @Bean
    ApplicationRunner demoRunner(
            StartupMarker marker,
            @Value("${demo.message}") String message) {
        return args -> System.out.println(
                "05 runner: " + message + " | " + marker.label());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("04 ApplicationStartedEvent");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("06 ApplicationReadyEvent");
    }
}
```

Đây là **một chương trình hoàn chỉnh trong một file** với các class lồng nhau; không cần tạo file riêng cho initializer/marker. `@SpringBootApplication` làm primary source.

**Vì sao chương trình chứng minh đúng vòng đời?**

1. `EarlySetup` được truyền trực tiếp cho `SpringApplication` trước `run(...)` nên nó chạy dù **không có `@Component`**.
2. Khi initializer chạy, context chưa active: `isActive()` in `false`.
3. `MapPropertySource` thêm key `demo.message` vào Environment. Cú pháp `Map.<String,Object>of(...)` giúp đúng generic type mà constructor `MapPropertySource` yêu cầu.
4. `GenericApplicationContext.registerBean(...)` lưu định nghĩa cho `StartupMarker`. Đây không phải hành động lấy bean bằng `getBean(...)`.
5. Sau khi refresh, Spring inject `StartupMarker` và giá trị `demo.message` vào bean `ApplicationRunner`.
6. Listener cho `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent` được đăng ký **trực tiếp từ bootstrap**. Chúng đến quá sớm để trông chờ một bean listener chỉ có `@EventListener`.
7. Hai phương thức `@EventListener` trên class ứng dụng nghe `ApplicationStartedEvent` và `ApplicationReadyEvent` sau khi context đã refresh.

### 5.3. Lệnh chạy và output

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Các dòng do **mã Java chủ động in ra** theo thứ tự khi không truyền tham số:

```text
01 initializer active: false
02 ContextInitializedEvent
03 ApplicationPreparedEvent
04 ApplicationStartedEvent
05 runner: Xin chào từ initializer | bean đã đăng ký sớm
06 ApplicationReadyEvent
07 main after run: true
```

Gradle có thể xuất thêm thông báo build. Các thuộc tính trong ví dụ tắt banner và log startup INFO để dễ theo dõi; lỗi cấu hình hoặc các công cụ xung quanh có thể sinh thêm output.

**Mốc kiểm chứng:** Dòng 01 có `false`; dòng 02 đến sau initializer; dòng 03 trước refresh; dòng 04 và 05 sau refresh; dòng 06 sau runner; dòng 07 xuất hiện sau khi `SpringApplication.run(...)` trả về.

### 5.4. Thử thay đổi để hiểu nguyên nhân

- **Xóa `app.addInitializers(new EarlySetup())`:** `StartupMarker` không còn được đăng ký bằng initializer và `demo.message` không còn nguồn trong ví dụ; quá trình dựng runner có thể thất bại vì thiếu dependency hoặc placeholder.
- **Bỏ riêng `registerBean(...)`:** phương thức `@Bean demoRunner` đòi hỏi `StartupMarker` mà container không có; startup thất bại.
- **Đổi property ở `MapPropertySource`:** dòng 05 đổi thông điệp mà code `demoRunner` không thay đổi.
- **Di chuyển `context.getBean(StartupMarker.class)` vào `initialize(...)`:** không còn bảo đảm vì context chưa refresh; đây là phản ví dụ về truy cập quá sớm.
- **Chỉ thêm `@Component` cho class `EarlySetup` rồi bỏ `addInitializers`:** component scanning đến quá muộn để callback được Boot tự gọi; cơ chế đã thay đổi.
- **Đổi sang ứng dụng Servlet/Reactive:** cần dependency web phù hợp và phải kiểm tra loại context khi dùng `registerBean(...)`. Thời điểm initializer vẫn trước refresh.

## 6. Đăng ký initializer vào Spring Boot bằng cách nào?

### 6.1. addInitializers trên SpringApplication

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addInitializers(new MyInitializer());
application.run(args);
```

Đây là **đoạn minh họa**, không phải file Java độc lập; cần class `MyApplication` và `MyInitializer` có thật. `addInitializers(...)` thêm callback. `setInitializers(collection)` thiết lập lại tập callback của đối tượng `SpringApplication`; không dùng bừa nếu mục đích chỉ là bổ sung.

### 6.2. SpringApplicationBuilder

```java
new SpringApplicationBuilder(MyApplication.class)
        .initializers(new MyInitializer())
        .run(args);
```

Cần import `org.springframework.boot.builder.SpringApplicationBuilder`. Builder tiện khi có nhiều tùy chọn bootstrap hoặc context hierarchy; initializer được gắn với cấu hình bootstrap chứ không đợi DI.

### 6.3. META-INF/spring.factories

Với Spring Boot 3.x, một thư viện có thể công bố `ApplicationContextInitializer` để Spring Boot phát hiện qua `META-INF/spring.factories`.

File `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.initializer.ExtraInitializer
```

`ExtraInitializer` là **tên class minh họa**, phải được bạn tự triển khai với constructor thích hợp để Boot tạo. Không dán cấu hình nếu class chưa có thật. Cách này hữu ích cho integration/library khởi tạo sớm, nhưng cũng dễ ảnh hưởng nhiều ứng dụng dùng chung dependency.

**Không thể chỉ gắn `@Component` vào initializer rồi kỳ vọng Spring Boot tìm ra nó trước refresh.** Component scanning và tạo bean thuộc giai đoạn sau.

## 7. Thứ tự nhiều initializer và khả năng chạy lặp

Spring Boot áp dụng ordering cho các initializer, hỗ trợ `Ordered` hoặc `@Order`.

```java
public class ExampleInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("example-context");
    }
}
```

Đây là **đoạn class minh họa**: cần import `Ordered`, `ApplicationContextInitializer`, `ConfigurableApplicationContext` nếu dùng riêng.

- Giá trị order nhỏ hơn thường có độ ưu tiên cao hơn.
- Nếu hai initializer thay đổi cùng `PropertySource` hoặc đăng ký cùng bean name, phải thiết kế xung đột rõ ràng; đừng giả định có thể trộn bất kỳ thứ tự nào.
- Một initializer có thể được áp dụng cho nhiều context hoặc nhiều lần chạy. Hãy viết logic có thể lặp lại an toàn và tránh lưu `ApplicationContext` vào biến `static`.
- Chỉ kiểm tra kiểu context khi thật cần API riêng; đừng giả định mọi context là Servlet web context.

## 8. PropertySource, precedence và giới hạn thời điểm

`ConfigurableEnvironment` giữ tập `PropertySource` theo thứ tự ưu tiên. Ví dụ:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "early-config",
                Map.<String, Object>of("feature.mode", "strict")));
```

`addFirst` đặt nguồn ở **ưu tiên rất cao**. Nếu key trùng với giá trị mà người vận hành truyền từ command line, property source này có thể che override đó. Hãy chọn `addFirst(...)`, `addLast(...)` hoặc vị trí cụ thể dựa trên nhu cầu precedence và khả năng vận hành, không mặc định dùng addFirst mọi lúc.

Đối với cấu hình quan trọng đã được Boot dùng sớm, initializer có giới hạn:

- `Environment` và ConfigData đã được chuẩn bị ở bước trước. Sửa `spring.profiles.active` hoặc `spring.config.import` lúc này có thể **quá muộn** để nạp lại các file cấu hình tương ứng.
- `SpringApplication` đã chọn/tạo loại `ApplicationContext` trước khi gọi initializer; thay `spring.main.web-application-type` ở đây không bảo đảm đổi loại context.
- Một số thuộc tính `spring.main.*` đã được bind vào `SpringApplication` trước initializer. Cần cấu hình chúng từ giai đoạn bootstrap thích hợp.

**Chọn điểm mở rộng sớm hơn** như `EnvironmentPostProcessor` nếu yêu cầu thay đổi cách Boot hình thành Environment, nạp config data hoặc quyết định bootstrap. Initializer thích hợp hơn cho cấu hình sẽ được sử dụng **trong bước xây dựng bean về sau**.

## 9. So sánh với các điểm mở rộng dễ nhầm

| Điểm mở rộng | Thời điểm | Mục đích phù hợp |
| --- | --- | --- |
| `BootstrapRegistryInitializer` | Khi chuẩn bị bootstrap registry của Boot | Cung cấp đối tượng trợ giúp giai đoạn bootstrap |
| `EnvironmentPostProcessor` | Trong quá trình chuẩn bị Environment, trước context | Thay nguồn cấu hình sớm |
| **`ApplicationContextInitializer`** | Context đã tạo, trước nạp primary sources và refresh | Thêm property source, cấu hình context, đăng ký bean sớm |
| `ApplicationContextInitializedEvent` listener | Sau initializer, trước nạp primary sources | Quan sát/sửa ở mốc sớm; listener phải đăng ký từ bootstrap |
| `ApplicationPreparedEvent` listener | Bean definitions đã nạp, trước refresh | Quan sát context đã được chuẩn bị đầy đủ |
| `BeanDefinitionRegistryPostProcessor` | Trong refresh, lúc xử lý registry | Bổ sung/chỉnh bean definitions khi registry đã có |
| `BeanFactoryPostProcessor` | Trong refresh, trước tạo nhiều singleton | Thay metadata bean factory/definitions |
| `@PostConstruct` | Khi bean cụ thể được tạo | Chuẩn bị trạng thái nội bộ một bean |
| `ApplicationStartedEvent` | Sau refresh, trước runner | Quan sát startup đã tới mốc started |
| `ApplicationRunner` / `CommandLineRunner` | Sau started, trước ready | Tác vụ một lần dùng bean đã được inject |
| `ApplicationReadyEvent` | Sau runner | Quan sát ứng dụng đã qua startup thành công |

**Tình huống thực tế:** Nếu cần chỉnh một giá trị dùng để dựng bean, initializer hoặc config source sớm là ứng viên. Nếu cần dùng `JdbcTemplate`/repository để preload dữ liệu, chọn runner hoặc cơ chế startup sau refresh. Nếu cần can thiệp bean definitions đã được scan, chọn registry/factory post-processor.

## 10. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không thấy `initialize(...)` chạy | Chỉ dùng `@Component`, chưa đăng ký callback bootstrap | Dùng `addInitializers`, builder hoặc `spring.factories` |
| `getBean(...)` thất bại trong initializer | Context chưa refresh; bean chưa sẵn sàng | Chuyển sang đăng ký definition hoặc đợi giai đoạn sau refresh |
| `ClassCastException` khi ép context | Chọn nhầm loại context (NONE/Servlet/Reactive/custom) | Kiểm tra `instanceof`, dùng API chung khi có thể |
| Property từ command line bị bỏ qua | `MapPropertySource.addFirst` che nguồn khác | Xem thứ tự `Environment.getPropertySources()` |
| Thay web type trong initializer nhưng context không đổi | Loại context đã được tạo trước callback | Chọn type trước khi `run(...)` hoặc qua config chuẩn |
| Đổi profile nhưng config profile khác không nạp | ConfigData đã được xử lý trước initializer | Dùng cấu hình từ bootstrap hoặc `EnvironmentPostProcessor` |
| `NoSuchBeanDefinitionException` khi refresh | Đăng ký bean definition thiếu/sai hoặc dependency chưa hợp lệ | Kiểm tra registry và root cause |
| Đăng ký bean trùng tên | Nhiều initializer hoặc scan và đăng ký thủ công cùng bean | Thiết kế tên/điều kiện rõ, tránh lặp |
| `ApplicationContextInitializedEvent` không đến `@EventListener` | Bean listener chưa được tạo tại mốc đó | `SpringApplication.addListeners(...)` từ bootstrap |
| Startup treo khi initializer gọi API ngoài | I/O nặng/blocking quá sớm | Giảm side effect, chuyển tác vụ cần bean sang runner |
| Initializer lỗi thì vẫn mong có ReadyEvent | Startup thất bại trước refresh | Đọc exception gốc; `ApplicationReadyEvent` sẽ không được phát |

Một số sự kiện được gửi **trước khi các listener bean tồn tại**, nên khi muốn quan sát hoặc xử lý lỗi bootstrap rất sớm, hãy dùng cơ chế listener được đăng ký với `SpringApplication` trước khi chạy.

Để debug, có thể log **tên initializer, mốc event, context ID, kiểu context và key property không nhạy cảm**. Không in password, token hoặc nguyên văn toàn bộ Environment.

## 11. Câu hỏi tự kiểm tra

1. **Initializer chạy trước hay sau khi tạo context?** Sau khi context được tạo, trước refresh.
2. **Tại sao `isActive()` có thể là false trong initializer?** Vì `refresh()` chưa được thực hiện.
3. **Có thể đọc `Environment` ở thời điểm này không?** Có, Environment đã được chuẩn bị và gắn vào context.
4. **Có nên lấy repository bean trong initializer không?** Không; bean definition/instance chưa sẵn sàng như sau refresh.
5. **`ApplicationContextInitializedEvent` khác `ApplicationPreparedEvent` ra sao?** Event đầu sau initializer nhưng trước nạp primary sources; event sau khi sources đã được nạp nhưng trước refresh.
6. **Gắn `@Component` cho initializer là đủ không?** Không; phải đăng ký từ giai đoạn bootstrap.
7. **Muốn đăng ký bean trước refresh bằng code nên dùng gì?** Có thể dùng `GenericApplicationContext.registerBean(...)` nếu context phù hợp, rồi để container khởi tạo bean theo lifecycle.
8. **Muốn thay config data/profile từ rất sớm nên dùng gì?** Cân nhắc `EnvironmentPostProcessor` hoặc cấu hình bootstrap chính thức, không phụ thuộc initializer chạy quá muộn.
9. **Initializer có thể gọi `refresh()` thủ công không?** Không nên; Spring Boot quản lý refresh và thứ tự event.
10. **Muốn chạy tác vụ dùng bean sau refresh nên dùng gì?** `ApplicationRunner` hoặc `CommandLineRunner`, tùy nhiệm vụ.

## 12. Ghi nhớ và nguồn tham khảo

- `ApplicationContextInitializer<C extends ConfigurableApplicationContext>` là hook cấu hình **context đã tạo nhưng chưa refresh**.
- Spring Boot 3.3.x gọi initializer **trước khi nạp primary bean definitions**, sau đó phát `ApplicationContextInitializedEvent`; nạp sources, phát `ApplicationPreparedEvent` rồi refresh.
- Trong initializer có thể sửa `Environment`, cấu hình context và đăng ký definition khi context hỗ trợ. **Chưa lấy bean nghiệp vụ để dùng**.
- Đăng ký qua `SpringApplication.addInitializers`, `SpringApplicationBuilder.initializers` hoặc `META-INF/spring.factories`; riêng `@Component` không đủ.
- Các thuộc tính bootstrap có thể đã được xử lý. Chọn `EnvironmentPostProcessor` nếu cần sớm hơn; dùng runner nếu cần làm việc sau refresh.

Tài liệu chính thức:

- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), đặc biệt chuỗi event.
- [Spring Boot 3.3.13 API — SpringApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html), `addInitializers(...)`, `applyInitializers(...)`.
- [Spring Boot 3.3.13 API — ApplicationPreparedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html).
- [Spring Framework — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html).

Muốn đọc đúng một lỗi startup, hãy xác định nó xảy ra **trước khi context được tạo, trong initializer, khi nạp bean definitions, trong refresh hay sau refresh**. Các mốc này tương ứng với những điểm mở rộng và cách xử lý khác nhau.
