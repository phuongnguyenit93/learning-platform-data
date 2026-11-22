# ApplicationContextInitializedEvent: sự kiện sau khi áp dụng ApplicationContextInitializer

## 1. Vị trí của sự kiện trong vòng đời Spring Boot

Một chương trình Spring Boot có thể đã **tạo được đối tượng `ApplicationContext`** nhưng vẫn chưa nạp các định nghĩa bean, chưa khởi tạo singleton và chưa sẵn sàng phục vụ request. Trước khi làm những việc đó, `SpringApplication` trao cho các `ApplicationContextInitializer` cơ hội tùy chỉnh context. **Ngay sau khi các initializer đã chạy**, Spring Boot phát `ApplicationContextInitializedEvent`.

Đây chính là ý nghĩa của tên sự kiện: **context đã được chuẩn bị và được áp dụng initializer**, chứ chưa phải toàn bộ ứng dụng đã “initialized” theo nghĩa có bean nghiệp vụ, database, controller và web server.

Hãy hình dung một phòng học:

- Spring Boot **chọn phòng** và mở cửa phòng: tạo `ApplicationContext`.
- Người phụ trách **sắp bàn ghế, đặt bảng hướng dẫn**: chạy `ApplicationContextInitializer`.
- Có người xác nhận **phòng đã được chuẩn bị**: `ApplicationContextInitializedEvent`.
- Sau đó mới **đưa danh sách thiết bị và học viên vào**: nạp bean definitions.
- Cuối cùng mới **lắp đặt và vận hành thiết bị**: `refresh()`, tạo bean và khởi động thành phần.
- Buổi học có thể bắt đầu sau khi mọi bước bắt buộc hoàn tất: application ready.

Bài này dùng API của **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. Ta sẽ giải thích sự kiện, vị trí của nó, API có thể dùng, cách đăng ký listener **đúng thời điểm**, những giới hạn quan trọng và một chương trình hoàn chỉnh để quan sát.

**Ý chính cần giữ:** `ApplicationContextInitializedEvent` là một **sự kiện khởi động sớm**, được phát **sau initializer và trước lúc nạp bean definitions của ứng dụng**. Nó không phải sự kiện bean được khởi tạo, không phải `ContextRefreshedEvent`, và không phải `ApplicationReadyEvent`.

## 2. Bản đồ thời gian: context có trước bean

Sơ đồ mô tả đường chạy phổ biến của `SpringApplication.run(...)`:

```text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       +-- ApplicationStartingEvent
       |
       +-- Chuẩn bị Environment, xử lý cấu hình khởi động
       +-- ApplicationEnvironmentPreparedEvent
       |
       +-- CHỌN / TẠO ConfigurableApplicationContext
       |
       +-- Gắn Environment, chuẩn bị context
       |
       +-- applyInitializers(context)
       |       |
       |       +-- initializer A.initialize(context)
       |       +-- initializer B.initialize(context)
       |       +-- ... theo thứ tự initializer đã sắp xếp
       |
       +-- ApplicationContextInitializedEvent   <=== TRỌNG TÂM BÀI
       |       |
       |       +-- Context đã có
       |       +-- Initializers đã chạy
       |       +-- Chưa load primary bean definitions
       |       +-- Chưa refresh
       |
       +-- Hoàn tất phần chuẩn bị bootstrap / nạp primary sources
       +-- ApplicationPreparedEvent
       |
       +-- context.refresh()
       |       |
       |       +-- BeanFactoryPostProcessor, BeanPostProcessor
       |       +-- Tạo singleton không lazy, tiêm phụ thuộc
       |       +-- Khởi tạo hạ tầng web nếu có
       |       +-- ContextRefreshedEvent
       |
       +-- ApplicationStartedEvent
       +-- LivenessState.CORRECT
       |
       +-- ApplicationRunner / CommandLineRunner
       |
       +-- ApplicationReadyEvent
       +-- ReadinessState.ACCEPTING_TRAFFIC
```

Sơ đồ tập trung vào **thứ tự các mốc chính của Spring Boot**. Một số hoạt động nội bộ về bootstrap, Environment, web server và listener có điểm móc chi tiết riêng; không nên coi sơ đồ là danh sách đầy đủ mọi hàm mà framework gọi.

### 2.1. Sự kiện này xảy ra trước `refresh()`

`ConfigurableApplicationContext.refresh()` là quá trình quan trọng để xử lý BeanFactory, bean definitions, post-processors và khởi tạo các singleton thông thường. `ApplicationContextInitializedEvent` được phát **trước** bước đó.

Với các `ApplicationContext` chuẩn dựa trên `AbstractApplicationContext`, khi bắt sự kiện này:

```text
context != null
context.isActive() == false
```

Đây là kết quả thông thường vì context chưa được `refresh()`. Không suy diễn rằng context có lỗi chỉ vì `isActive()` còn `false`. Cờ active sẽ có ý nghĩa khác sau refresh hoặc close.

### 2.2. “Chưa có bean definitions” phải hiểu chính xác

Tài liệu Spring Boot xác định thời điểm sự kiện là **trước khi bean definitions được nạp**. Điều này đặc biệt nói đến việc Boot chưa nạp các **primary sources**, `@SpringBootApplication`, `@Configuration`, `@ComponentScan` và các definitions của ứng dụng theo đường chạy thông thường.

Đừng viết phép kiểm tra rằng **`BeanFactory.getBeanDefinitionCount()` bắt buộc phải bằng số 0** trong mọi tình huống. Một context hay integration tùy chỉnh có thể đã thêm infrastructure metadata hoặc đăng ký thủ công trước đó. Điều ổn định cần nhớ là **chưa thể giả định toàn bộ bean definitions ứng dụng đã nạp và chưa thể gọi các bean nghiệp vụ như sau refresh**.

## 3. Khác nhau giữa tạo context, initializer, event và refresh

| Mốc | Đối tượng hoặc việc đã có | Việc chưa thể giả định |
| --- | --- | --- |
| Tạo context | Instance `ConfigurableApplicationContext` với kiểu phù hợp | Chưa có bean ứng dụng hoạt động |
| Áp dụng `ApplicationContextInitializer` | Có context để sửa cấu hình ban đầu | Chưa thực hiện `refresh()` |
| Phát `ApplicationContextInitializedEvent` | **Tất cả initializer của lượt startup đã được áp dụng theo thứ tự** | Chưa nạp primary bean definitions, chưa refresh |
| Phát `ApplicationPreparedEvent` | Bean definitions của primary sources đã được nạp | Chưa refresh và tạo singleton thông thường |
| `ContextRefreshedEvent` | `refresh()` đã hoàn thành đối với context | Chưa chắc Boot đã chạy xong runner |
| `ApplicationStartedEvent` | Spring Boot đã refresh context | `ApplicationRunner`/`CommandLineRunner` chưa được gọi |
| `ApplicationReadyEvent` | Các runner đã hoàn tất thành công | Không bảo đảm mọi dependency ngoài luôn khỏe mãi |

Vì vậy, việc code gặp chữ `Initialized` trong tên event không phải bằng chứng rằng toàn bộ ứng dụng đã sẵn sàng nhận lưu lượng.

## 4. `ApplicationContextInitializer` được áp dụng như thế nào?

Interface của Spring Framework có dạng rút gọn:

```java
@FunctionalInterface
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

Đây là **chữ ký minh họa contract**, không phải file Java cần tự định nghĩa: interface thật là `org.springframework.context.ApplicationContextInitializer`.

`SpringApplication` tập hợp các initializer được đăng ký trực tiếp hoặc thông qua cơ chế thư viện, sắp thứ tự theo `Ordered`/`@Order`, rồi gọi từng `initialize(context)` **trước khi nạp primary sources và refresh context**. Chúng được dùng khi cần tùy chỉnh sớm: thêm `PropertySource`, listener, BeanFactory post-processor hoặc cấu hình hợp lệ cho context.

Ví dụ initializer thêm một property mặc định:

```java
ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
        context -> {
            MapPropertySource defaults = new MapPropertySource(
                    "earlyDefaults",
                    Map.of("demo.label", "initialized-first"));
            context.getEnvironment()
                    .getPropertySources()
                    .addLast(defaults);
        };
```

Đây là một snippet nằm trong method `main` hoặc code cấu hình `SpringApplication`; cần import `ApplicationContextInitializer`, `ConfigurableApplicationContext`, `MapPropertySource` và `java.util.Map`. `addLast` thêm source ưu tiên thấp, để property từ nguồn cấu hình có độ ưu tiên cao hơn vẫn có thể ghi đè.

**Liên hệ với event:** sau khi đoạn `initialize(...)` chạy, listener nhận `ApplicationContextInitializedEvent` có thể đọc:

```java
String label = event.getApplicationContext()
        .getEnvironment()
        .getProperty("demo.label");
```

Nếu không có property source khác ghi đè, giá trị là `initialized-first`. Đây là một cách chứng minh rằng initializer đã được áp dụng **trước lúc event được phát**.

### 4.1. “Sau initializer” không có nghĩa “sau khi bean đã inject”

Initializer hoạt động khi application context mới tồn tại. Nó không được Boot tạo như một bean nghiệp vụ thông thường từ `@ComponentScan`. Tại đây, `context.getBean(MyService.class)`, `@Autowired` trong bean, `@PostConstruct` và các repository thông thường chưa được bảo đảm tồn tại.

Dùng initializer cho việc **chuẩn bị container**, dùng `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` để sửa metadata tại pha phù hợp, dùng `ApplicationRunner` hoặc lifecycle bean để thực hiện nghiệp vụ phụ thuộc bean đã sẵn sàng.

## 5. API của `ApplicationContextInitializedEvent`

Class chính là:

```java
org.springframework.boot.context.event.ApplicationContextInitializedEvent
```

Nó kế thừa `SpringApplicationEvent` và có thể truy xuất các thông tin sau:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `event.getApplicationContext()` | Lấy `ConfigurableApplicationContext` đang được chuẩn bị | Chưa refresh; có thể đọc Environment/đăng ký tùy chỉnh sớm |
| `event.getSpringApplication()` | Lấy `SpringApplication` phát sinh sự kiện | Không dùng để tự gọi `run()` lồng vào startup |
| `event.getArgs()` | Nhận mảng tham số truyền vào `SpringApplication.run(...)` | Có thể chứa thông tin nhạy cảm; tránh in nguyên văn |
| `event.getTimestamp()` | Mốc thời gian tạo event | Không phải tổng thời gian startup |
| `event.getSource()` | Nguồn event theo `ApplicationEvent` | Đừng thay `getApplicationContext()` bằng ép kiểu source sang context |

Constructor của `ApplicationContextInitializedEvent` nhận `SpringApplication`, `String[] args` và `ConfigurableApplicationContext`. Trong ứng dụng bình thường **không tự tạo rồi phát thủ công** sự kiện này: đó là một mốc do `SpringApplication` phát trong quá trình startup.

### 5.1. Context ở đây thuộc loại nào?

Với context factory mặc định, nó tùy `WebApplicationType`:

- `NONE`: thường là `AnnotationConfigApplicationContext`.
- `SERVLET`: thường là `AnnotationConfigServletWebServerApplicationContext`.
- `REACTIVE`: thường là `AnnotationConfigReactiveWebServerApplicationContext`.

Mọi trường hợp đều có `ConfigurableApplicationContext` để listener làm việc với các API chung. Có thể dùng factory tùy chỉnh, nên không nên ép kiểu context sang Servlet hoặc Reactive khi không kiểm tra.

### 5.2. Environment đã có, nhưng những lựa chọn sớm đã xảy ra

`SpringApplication` chuẩn bị `Environment` trước khi tạo context. Listener ở mốc này thường đọc được `spring.application.name`, profile, command-line properties và các property đã được chuẩn bị.

Tuy nhiên, việc **mới thêm một property** tại event không có nghĩa Boot quay lại tất cả các quyết định trước đó. Ví dụ Boot đã chọn và tạo loại context; đưa `spring.main.web-application-type=reactive` vào `Environment` tại đây **không tự thay thế** một context Servlet đã được tạo.

Tương tự, nếu một property phải ảnh hưởng tới **quá trình ConfigData đã hoàn tất**, hãy dùng cơ chế phù hợp **trước** pha tạo context, không chờ `ApplicationContextInitializedEvent`.

## 6. Cách bắt sự kiện đúng: đăng ký listener trước khi run

Đây là phần dễ sai nhất. Vì `ApplicationContextInitializedEvent` xảy ra **trước khi Spring dựng bean**, cách chắc chắn nhất để nhận được nó là đăng ký `ApplicationListener` với `SpringApplication` **trước `run(...)`**.

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationContextInitializedEvent> listener =
        event -> System.out.println(
                "Context type: "
                        + event.getApplicationContext()
                               .getClass()
                               .getSimpleName());

app.addListeners(listener);
app.run(args);
```

Đoạn trên là **mã minh họa trong `main`**, giả định `MyApplication` là class `@SpringBootApplication`, và cần import `SpringApplication`, `ApplicationListener`, `ApplicationContextInitializedEvent`.

### 6.1. Vì sao `@EventListener` trong một bean thường không bắt được?

Đoạn sau có thể biên dịch nhưng **không phải cách phù hợp để nhận event khởi động này**:

```java
@Component
class TooLateListener {

    @EventListener
    void observe(ApplicationContextInitializedEvent event) {
        System.out.println("I expect the early event");
    }
}
```

Đây là ví dụ **chỉ để giải thích lỗi về thời điểm**, cần import `@Component`, `@EventListener` và event class. Bean `TooLateListener` phải được Spring tạo và đăng ký adapter sự kiện trong lúc refresh, **sau khi `ApplicationContextInitializedEvent` đã được phát**. Vì vậy đừng dựa vào method đó để bắt sự kiện sớm trong lần startup hiện tại.

Điều tương tự áp dụng cho listener chỉ tồn tại dưới dạng `@Bean ApplicationListener<ApplicationContextInitializedEvent>` ở một `@Configuration` bình thường: bean đó cũng đến quá muộn.

### 6.2. Listener có thể đăng ký qua `SpringApplicationBuilder`

```java
new SpringApplicationBuilder(MyApplication.class)
        .listeners((ApplicationListener<ApplicationContextInitializedEvent>)
                event -> System.out.println("Context initialized"))
        .run(args);
```

Đây là một **snippet main** khác, không dùng đồng thời với `app.run(...)` ở trên. Cần import `SpringApplicationBuilder`, `ApplicationListener` và event class. `SpringApplicationBuilder.listeners(...)` giúp cấu hình ứng dụng nhiều cấp hoặc khi bạn muốn API dạng chuỗi.

### 6.3. Dùng `META-INF/spring.factories` khi viết thư viện

Nếu muốn listener được nạp ngay cả khi ứng dụng khác không sửa `main`, có thể đóng gói class listener vào JAR kèm:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.context.ApplicationListener=\
com.example.early.ContextInitializedLogger
```

Và class:

```java
package com.example.early;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public final class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        System.out.println("Early context: "
                + event.getApplicationContext().getClass().getSimpleName());
    }
}
```

Đây là **file Java hoàn chỉnh** tại `src/main/java/com/example/early/ContextInitializedLogger.java`; nó không có `main` riêng. Khi thư viện hiện diện trên classpath và Boot tải `ApplicationListener` bằng cơ chế factory, listener được đăng ký đủ sớm để bắt event.

**Lưu ý:** file `spring.factories` ở đây chứa key `org.springframework.context.ApplicationListener`. Không đánh đồng nó với file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` chuyên khai báo auto-configuration của Spring Boot 3.x.

Tránh đăng ký cùng listener lặp qua cả `spring.factories` và `addListeners(...)`, đặc biệt nếu listener tạo tác dụng phụ hoặc ghi tài nguyên.

## 7. Ví dụ thực hành hoàn chỉnh: chứng minh initializer chạy trước event

Ví dụ dùng **một chương trình Spring Boot duy nhất**, Java 17+, Spring Boot 3.3.x. Ta chủ động chọn `WebApplicationType.NONE` để không khởi động web server, tập trung vào thứ tự lifecycle.

**File:** `src/main/java/com/example/early/InitializedEventDemoApplication.java`

```java
package com.example.early;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class InitializedEventDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitializedEventDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
                context -> {
                    context.getEnvironment().getPropertySources().addLast(
                            new MapPropertySource(
                                    "demoInitializerDefaults",
                                    Map.of("demo.message", "from-initializer")));
                    System.out.println("1 INITIALIZER");
                };
        app.addInitializers(initializer);

        ApplicationListener<ApplicationContextInitializedEvent> initialized =
                event -> {
                    ConfigurableApplicationContext context =
                            event.getApplicationContext();
                    System.out.println("2 CONTEXT_INITIALIZED active="
                            + context.isActive());
                    System.out.println("3 CONTEXT_INITIALIZED message="
                            + context.getEnvironment().getProperty("demo.message"));
                };
        app.addListeners(initialized);

        ApplicationListener<ApplicationPreparedEvent> prepared =
                event -> System.out.println("4 PREPARED active="
                        + event.getApplicationContext().isActive());
        app.addListeners(prepared);

        ApplicationListener<ApplicationStartedEvent> started =
                event -> System.out.println("5 STARTED active="
                        + event.getApplicationContext().isActive());
        app.addListeners(started);

        ApplicationListener<ApplicationReadyEvent> ready =
                event -> System.out.println("7 READY active="
                        + event.getApplicationContext().isActive());
        app.addListeners(ready);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("8 RUN_RETURNED active="
                    + context.isActive());
        }
    }

    @Bean
    ApplicationRunner showMessage(Environment environment) {
        return arguments -> System.out.println(
                "6 RUNNER message=" + environment.getProperty("demo.message"));
    }
}
```

### 7.1. Cấu hình project

Giả sử dự án có Spring Boot Gradle plugin 3.3.x, dependency management phù hợp và Java 17+ đã cấu hình. Dependency tối thiểu:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Không cần `spring-boot-starter-web`, cơ sở dữ liệu hay HTTP endpoint. Nếu dự án có nhiều main class, chỉ rõ class `com.example.early.InitializedEventDemoApplication` cho `bootRun`/plugin để tránh khởi động nhầm.

### 7.2. Chạy chương trình

```bash
./gradlew bootRun
```

Trên Windows CMD dùng `gradlew.bat bootRun`; trên PowerShell dùng `.\gradlew.bat bootRun`.

Nếu dự án chỉ chứa main class của ví dụ, có thể dùng cấu hình Boot mặc định để xác định main. Log banner/INFO của Spring Boot có thể xen giữa các dòng dưới đây.

### 7.3. Kết quả quan sát khi khởi động thành công

Các dòng do chương trình tự in, theo thứ tự:

```text
1 INITIALIZER
2 CONTEXT_INITIALIZED active=false
3 CONTEXT_INITIALIZED message=from-initializer
4 PREPARED active=false
5 STARTED active=true
6 RUNNER message=from-initializer
7 READY active=true
8 RUN_RETURNED active=true
```

**Đối chiếu từng mốc:**

- Dòng **1**: initializer thêm `demoInitializerDefaults` vào `Environment`. Nó thực hiện trước event.
- Dòng **2**: `ApplicationContextInitializedEvent` đã được phát và context tồn tại nhưng chưa refresh (`active=false`).
- Dòng **3**: cùng listener đọc được property initializer thêm, chứng minh thay đổi sớm đã có hiệu lực trong `Environment`.
- Dòng **4**: `ApplicationPreparedEvent` nằm sau khi Boot nạp bean definitions, nhưng context vẫn chưa refresh.
- Dòng **5**: `ApplicationStartedEvent` nằm sau refresh, nên context đã active.
- Dòng **6**: `ApplicationRunner` là bean được tạo/tiêm dependency sau refresh; runner đọc lại cùng property.
- Dòng **7**: `ApplicationReadyEvent` xuất hiện sau runner.
- Dòng **8**: `app.run(args)` trả về context; `try` sẽ đóng context sau khi in dòng đó.

Thử thay property bằng tham số khởi động:

```bash
./gradlew bootRun --args='--demo.message=from-command-line'
```

Do `demoInitializerDefaults` được thêm bằng `addLast(...)`, dòng số 3 và 6 thường hiển thị `from-command-line`: command-line source có độ ưu tiên cao hơn. Dùng `gradlew.bat bootRun --args="--demo.message=from-command-line"` trong Windows CMD; cách dấu nháy phụ thuộc shell.

Ví dụ chỉ in trạng thái của **context**, không diễn giải `active=true` thành HTTP đã ready: đây là ứng dụng không mở HTTP server. Với ứng dụng web, readiness của Spring Boot có mốc riêng và cần health probes để kiểm tra đường request.

### 7.4. Vì sao dùng `try-with-resources`?

`ConfigurableApplicationContext` implement `AutoCloseable` nên có thể dùng `try (...)`. Khi ra khỏi `try`, context được đóng và bean/tài nguyên do nó quản lý được dọn dẹp theo lifecycle. Việc đóng sau `run` **không thay đổi** thứ tự của các event đã in.

Nếu chính `app.run(...)` ném lỗi trước khi trả về, `try` chưa tạo xong resource; Spring Boot có xử lý startup failure riêng. Không suy ra rằng mọi trường hợp crash JVM, `SIGKILL` hoặc mất điện đều chạy callback cleanup.

## 8. Ví dụ nâng cao: kiểm tra tất cả initializer đã chạy

Giả sử có hai initializer: một tạo property `demo.phase`, cái kia bổ sung một property khác. `ApplicationContextInitializedEvent` xảy ra sau khi Boot gọi **các initializer đã đăng ký cho lần chạy đó**, vì vậy listener có thể kiểm tra kết quả **kết hợp**.

```java
ApplicationContextInitializer<ConfigurableApplicationContext> first =
        context -> context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "firstDefaults", Map.of("demo.phase", "prepared")));

ApplicationContextInitializer<ConfigurableApplicationContext> second =
        context -> context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "secondDefaults", Map.of("demo.source", "custom")));

app.addInitializers(first, second);
```

Đây là snippet để thêm trong `main`; cần các import giống ví dụ hoàn chỉnh. Listener của `ApplicationContextInitializedEvent` có thể đọc `demo.phase` và `demo.source`. Tuy nhiên, **thứ tự chính xác giữa các initializer quan trọng** nếu initializer thứ hai cần đọc kết quả của initializer thứ nhất.

### 8.1. Dùng Ordered để mô tả quan hệ phụ thuộc

Một initializer ở dạng class có thể implement `Ordered`:

```java
package com.example.early;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public final class FirstInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("First initializer completed");
    }
}
```

Mã trên là **class hoàn chỉnh** nhưng chưa được dùng cho tới khi bạn đăng ký bằng `app.addInitializers(new FirstInitializer())` hoặc cơ chế tương ứng. Giá trị order nhỏ hơn được sắp trước. Có thể dùng `@Order` trên class; hãy tránh phụ thuộc vào thứ tự ngẫu nhiên giữa các initializer có cùng order.

Listener của `ApplicationContextInitializedEvent` không cần chạy giữa initializer 1 và 2: nó nằm **sau nhóm initializer**. Nếu thực sự cần điều kiện “sau initializer A nhưng trước initializer B”, hãy thiết kế thứ tự hoặc trừu tượng của chính các initializer, không dùng event này để chen giữa chúng.

## 9. Cần làm gì trong listener và nên tránh gì?

### 9.1. Việc có thể phù hợp

Ở mốc này, listener sớm có thể:

- Ghi nhận **loại context** (`NONE`/`SERVLET`/`REACTIVE` ở mức runtime class).
- Kiểm tra thuộc tính cấu hình đã được initializer thêm vào Environment.
- Kiểm tra kết quả chuẩn bị những metadata không nhạy cảm và báo lỗi sớm khi thiếu cấu hình cần thiết.
- Đăng ký thêm listener vào `ConfigurableApplicationContext` cho các sự kiện **sẽ xảy ra về sau**, nếu việc đó có lý do.
- Bổ sung metadata/BeanFactory post-processor theo contract phù hợp trước refresh.
- Ghi log chẩn đoán ngắn để xác minh thứ tự startup.

Ví dụ thêm listener cho một sự kiện tương lai:

```java
ApplicationListener<ApplicationContextInitializedEvent> early =
        event -> event.getApplicationContext()
                .addApplicationListener((ContextRefreshedEvent refreshed) ->
                        System.out.println("Context refreshed later"));
```

Đây là snippet cần import `ApplicationListener`, `ApplicationContextInitializedEvent` và `org.springframework.context.event.ContextRefreshedEvent`. Listener được đăng ký vào context **trước khi refresh**, nên có thể nhận `ContextRefreshedEvent` về sau. Nếu có nhiều context, nên xác minh identity của context phát event trước khi tạo hiệu ứng một lần.

### 9.2. Những việc không nên làm

**Không lấy bean nghiệp vụ:**

```java
MyService service = event.getApplicationContext().getBean(MyService.class);
```

Đây là ví dụ **không đúng thời điểm**, giả định `MyService` là bean do `@ComponentScan` tạo. Ở mốc này, definitions của ứng dụng chưa được nạp; lệnh lấy bean có thể thất bại và làm startup hỏng.

**Không gọi `refresh()` hoặc `close()` thủ công.** Spring Boot đang sở hữu trình tự startup. Gọi hai method này trong listener có thể phá vỡ quy trình nạp bean và trạng thái context.

**Không thực hiện mạng/đọc file lâu hoặc retry vô hạn.** Listener khởi động thông thường chạy đồng bộ theo đường phát event; một listener chặn sẽ chặn cả quá trình khởi động. Nghiệp vụ cần service sau refresh nên chuyển sang `ApplicationRunner` hoặc cơ chế lifecycle thích hợp.

**Không dùng event để lùi về quyết định khởi động trước đó.** Ví dụ thay đổi `spring.main.web-application-type` lúc này không tự xây lại context đã được tạo; đổi property phụ thuộc giai đoạn load config có thể đã quá muộn.

**Không in tham số chứa bí mật.** `event.getArgs()` có thể gồm tên người dùng, token, password hay endpoint nội bộ; nếu cần debug, chỉ ghi thông tin không nhạy cảm hoặc danh sách key đã lọc.

## 10. So sánh với các sự kiện gần kề

| Sự kiện | Đã tạo ApplicationContext? | Đã chạy initializer? | Đã nạp bean definitions chính? | Đã refresh? |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Chưa | Chưa | Chưa | Chưa |
| `ApplicationEnvironmentPreparedEvent` | Chưa | Chưa (initializer của application context) | Chưa | Chưa |
| **`ApplicationContextInitializedEvent`** | **Có** | **Có** | **Chưa** | **Chưa** |
| `ApplicationPreparedEvent` | Có | Có | Có | Chưa |
| `ContextRefreshedEvent` | Có | Có | Có | Có |
| `ApplicationStartedEvent` | Có | Có | Có | Có |
| `ApplicationReadyEvent` | Có | Có | Có | Có, runner cũng đã chạy |

Dòng `ApplicationEnvironmentPreparedEvent` nói về `ApplicationContextInitializer`; các **`BootstrapRegistryInitializer`** thuộc pha bootstrap khác và có thể đã chạy sớm hơn. Không đánh đồng hai loại initializer chỉ vì tên đều có chữ initializer.

### 10.1. `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent`

Đây là cặp dễ nhầm:

- **Initialized**: context đã được tạo, `ApplicationContextInitializer` đã chạy xong, **chưa** nạp bean definitions.
- **Prepared**: Boot đã nạp definitions của primary sources vào context, nhưng **chưa** `refresh()`.

Nếu mục tiêu chỉ là kiểm tra giá trị mà initializer đặt vào Environment, **Initialized** đã đủ. Nếu cần làm việc với **metadata bean definitions được nạp từ source**, **Prepared** hoặc các post-processor giai đoạn refresh phù hợp hơn.

### 10.2. `ApplicationContextInitializedEvent` và `ContextRefreshedEvent`

`ContextRefreshedEvent` là sự kiện của Spring Framework sau `refresh()`; nó phản ánh context đã dựng BeanFactory và khởi tạo các bean không lazy. `ApplicationContextInitializedEvent` đến **trước** bước đó, và thuộc chuỗi sự kiện khởi động riêng của Spring Boot.

Trong hệ thống parent/child contexts, một `ContextRefreshedEvent` có thể lan lên ancestor context, nên listener có thể nhìn thấy nhiều sự kiện. Cần kiểm tra context identity nếu logic chỉ áp dụng cho một context.

### 10.3. Sự kiện này và `BootstrapContextClosedEvent`

`BootstrapContextClosedEvent` đóng phạm vi **BootstrapRegistry/BootstrapContext** và có thể chuyển tài nguyên chuẩn bị sớm vào application context. Nó **khác** sự kiện Initialized, vốn nói rằng các `ApplicationContextInitializer` đã chạy.

Trong đường khởi động chuẩn của Spring Boot 3.3, phần đóng bootstrap diễn ra quanh giai đoạn context đã prepared nhưng trước khi nạp primary sources và refresh. Đừng suy luận “BootstrapContextClosedEvent nghĩa ApplicationContext đã đóng”: `ApplicationContext` đang chuẩn bị bước vào vòng đời của nó.

### 10.4. Initialized và readiness

Spring Boot đánh dấu `LivenessState.CORRECT` sau `ApplicationStartedEvent` và `ReadinessState.ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent`. `ApplicationContextInitializedEvent` đến trước cả hai mốc đó, nên không phải tín hiệu để load balancer đưa request vào instance.

## 11. Tùy chỉnh bean: chọn extension point hợp lý

Nhiều người muốn “thêm một bean thật sớm” rồi nghĩ phải làm trong `ApplicationContextInitializedEvent`. Cần phân biệt các mục đích:

| Mục đích | Cơ chế phù hợp | Vì sao |
| --- | --- | --- |
| Thêm thuộc tính cấu hình cho quá trình dựng context | `ApplicationContextInitializer` hoặc điểm xử lý Environment phù hợp | Có trước khi BeanFactory refresh |
| Quan sát initializer đã áp dụng thành công | `ApplicationContextInitializedEvent` | Xác nhận mốc ngay sau nhóm initializer |
| Đăng ký BeanFactory post-processor để chạy trong refresh | `ApplicationContextInitializer` + `addBeanFactoryPostProcessor(...)` | Chạy đúng pha metadata trước tạo singleton |
| Tạo/sửa bean definitions dựa trên metadata đã nạp | `BeanDefinitionRegistryPostProcessor` | Có contract để làm việc với definitions |
| Tùy biến bean instance hoặc proxy | `BeanPostProcessor` | Diễn ra quanh lifecycle của bean |
| Chạy logic sau khi bean đã sẵn sàng | `ApplicationRunner`/`CommandLineRunner` | Đã qua refresh |
| Bắt event toàn ứng dụng sau khi ready | Listener `ApplicationReadyEvent` | Sau runner |
| Kiểm soát kết thúc tài nguyên | `@PreDestroy`, `SmartLifecycle` hoặc destroy method | Đúng pha shutdown, không phải event Initialized |

### 11.1. Ví dụ đăng ký post-processor sớm

```java
ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
        context -> context.addBeanFactoryPostProcessor(beanFactory -> {
            System.out.println("Bean definitions in refresh phase: "
                    + beanFactory.getBeanDefinitionCount());
        });
```

Đây là snippet, cần import interface initializer và configurable context. Lệnh `addBeanFactoryPostProcessor(...)` ở đây **chỉ đăng ký** callback; hàm bên trong lambda sẽ được gọi **sau đó trong `refresh()`**, khi BeanFactory đang được xử lý. Đừng nhầm việc “đăng ký” với “thực thi ngay trong initializer”.

### 11.2. Vì sao không tự đăng ký bean nghiệp vụ theo cách tùy tiện?

Tại Initialized event, context chưa được refresh, nên có những API kỹ thuật cho đăng ký sớm nhưng chúng phụ thuộc kiểu context/BeanFactory. Nếu cần bean runtime thông thường, `@Bean`, `@Component`, auto-configuration hoặc một `BeanDefinitionRegistryPostProcessor` thường rõ ràng hơn và cho container quản lý lifecycle đúng cách.

Việc tạo đối tượng bên ngoài rồi `registerSingleton(...)` có thể bỏ qua những bước tạo bean như injection, post-processing và callback destroy của container. Chỉ dùng khi hiểu rõ ownership, thứ tự và tác động; sự kiện Initialized **không tự động tạo ra một bean hoàn chỉnh**.

## 12. Trật tự các listener và chi phí startup

`ApplicationContextInitializedEvent` là một `SpringApplicationEvent` sớm. Boot dùng cơ chế phát sự kiện khởi động trước khi application context đã refresh xong; listener đăng ký với `SpringApplication` có cơ hội nhận event.

Theo mặc định, listener thường chạy đồng bộ trên luồng phát sự kiện. Vì vậy:

- Listener làm việc nặng kéo dài thời gian startup.
- Exception không được xử lý có thể khiến `SpringApplication.run(...)` thất bại.
- Có nhiều listener cùng sự kiện thì thứ tự có thể được ảnh hưởng bởi `Ordered`/`@Order`; không nên dựa vào thứ tự ngẫu nhiên.
- Sự kiện không phải cơ chế queue bảo đảm retry, transactional delivery hoặc truyền dữ liệu lâu dài.
- Hãy dùng log ngắn, phép kiểm tra nhẹ và dành việc cần chạy lâu cho bước sau khi bean có thể sử dụng.

Nếu cần đo chính xác thời gian startup, hãy dùng cơ chế quan sát startup như `ApplicationStartup` hoặc metrics của framework, thay vì coi `event.getTimestamp()` là thời gian ứng dụng đã khởi động xong.

## 13. Khi startup lỗi thì sao?

Có ba nhóm lỗi khác nhau:

1. **Lỗi trong initializer:** `initialize(...)` ném exception nên quá trình có thể dừng **trước khi phát `ApplicationContextInitializedEvent`**. Listener của event này sẽ không nhận được mốc xác nhận.
2. **Lỗi trong listener Initialized:** exception có thể lan ngược vào chuỗi khởi động và Boot xử lý failure; không có bảo đảm đạt `ApplicationPreparedEvent` hay `ApplicationReadyEvent`.
3. **Lỗi lúc nạp bean/refresh/runner:** Initialized event có thể đã xảy ra thành công, nhưng ứng dụng vẫn khởi động thất bại về sau.

Do đó, **quan sát thấy `ApplicationContextInitializedEvent` không phải bằng chứng startup PASS**. Nếu cần xử lý lỗi chung cho startup, đăng ký sớm listener cho `ApplicationFailedEvent`. Tùy thời điểm lỗi, event failure có thể chứa context hoặc không; không truy cập bean một cách vô điều kiện.

Với lỗi cấu hình bắt buộc, fail fast có thông báo cụ thể thường tốt hơn việc âm thầm nuốt exception rồi để ứng dụng hoạt động với cấu hình sai. Đồng thời tránh in dữ liệu bí mật trong stack trace/diagnostics.

### 13.1. Ví dụ xác thực property nhẹ

```java
ApplicationListener<ApplicationContextInitializedEvent> validate =
        event -> {
            String name = event.getApplicationContext()
                    .getEnvironment()
                    .getProperty("spring.application.name");
            if (name == null || name.isBlank()) {
                throw new IllegalStateException(
                        "Missing required spring.application.name");
            }
        };
```

Đây là snippet có thể đặt trong `main` rồi đăng ký `app.addListeners(validate)`. Nó phù hợp **chỉ khi `spring.application.name` thực sự là yêu cầu bắt buộc do ứng dụng đề ra**; Spring Boot không bắt buộc mọi dự án phải cấu hình property này.

## 14. Một tiến trình có thể nhận event nhiều lần không?

Có thể có nhiều `SpringApplication` hoặc context trong cùng JVM, ví dụ cấu trúc parent/child, integration tests khởi tạo nhiều context hoặc module chạy nhiều ứng dụng. Mỗi lượt `SpringApplication.run(...)` có thể phát event riêng.

Vì vậy không nên viết listener giả định “cả tiến trình chỉ có đúng một `ApplicationContextInitializedEvent`”. Khi cần chỉ xử lý sự kiện thuộc context mục tiêu, có thể so sánh identity với tham chiếu context thích hợp hoặc phân biệt `event.getSpringApplication()` trong cơ chế orchestration mà bạn kiểm soát.

Nếu listener toàn cục được đăng ký theo `spring.factories`, cần kiểm soát tác dụng phụ để không gây trùng thao tác khi cùng thư viện có mặt ở nhiều application/context. Việc lưu `static boolean initialized` cho toàn JVM thường không phải giải pháp đúng nếu có nhiều lần chạy độc lập.

## 15. Câu hỏi và tình huống ứng dụng

### Tình huống A — Cần biết một property do initializer vừa thêm có hiện diện không

Đăng ký một `ApplicationContextInitializedEvent` listener sớm và đọc từ `event.getApplicationContext().getEnvironment()`. Nếu thuộc tính chỉ có thể đến từ initializer, phép kiểm tra giúp phát hiện initializer chưa được đăng ký hoặc chạy sai thứ tự.

**Không** dùng `@EventListener` trên bean runtime để bắt mốc quá sớm này.

### Tình huống B — Muốn dùng repository để kiểm tra dữ liệu thiết yếu

Không lấy repository trong listener Initialized. Container chưa refresh và bean chưa sẵn sàng. Đưa việc kiểm tra vào `ApplicationRunner`, hoặc lifecycle của một bean được thiết kế rõ ràng; Spring Boot chỉ phát ready khi runner hoàn tất thành công.

### Tình huống C — Muốn thay loại context từ Servlet sang Reactive

Đặt `WebApplicationType` bằng API `SpringApplication.setWebApplicationType(...)` hoặc cấu hình khởi động trước khi context được tạo. Listener Initialized đã nhận **một context cụ thể**; cập nhật property trong listener không làm Boot tự chọn lại loại context.

### Tình huống D — Muốn thay đổi một bean definition từ `@Configuration`

Đợi đến pha definitions đã được nạp hoặc dùng `BeanDefinitionRegistryPostProcessor`. Tại Initialized event, primary source chưa được load; việc tìm bean definition của service ở đó quá sớm.

### Tình huống E — Muốn biết ứng dụng có thể nhận HTTP request chưa

Kiểm tra `ApplicationReadyEvent` và readiness/health của hệ thống triển khai. `ApplicationContextInitializedEvent` chỉ chứng minh bước cấu hình context sớm đã chạy xong.

### Tình huống F — Muốn bắt event trong một thư viện mà không buộc các ứng dụng sửa main

Cài `ApplicationListener<ApplicationContextInitializedEvent>` bằng `META-INF/spring.factories`. Đảm bảo class có constructor phù hợp, có mặt trên runtime classpath và xử lý idempotent nếu được đăng ký trong nhiều context.

## 16. Lỗi hiểu nhầm và cách chẩn đoán

| Nhầm lẫn hoặc lỗi gặp phải | Giải thích đúng | Hướng xử lý |
| --- | --- | --- |
| “Tên Initialized nghĩa là các bean đã được tạo.” | Chỉ initializer của context đã chạy, trước load bean definitions. | So sánh với `ApplicationPreparedEvent` và `ContextRefreshedEvent`. |
| `@EventListener` trên `@Component` không nhận event. | Bean listener tạo quá muộn. | Dùng `app.addListeners(...)` hoặc `spring.factories`. |
| `getBean(MyService.class)` thất bại trong early listener. | Bean definitions chưa được nạp/refresh. | Di chuyển sang runner hoặc lifecycle phù hợp. |
| `isActive()` trả `false` trong callback. | Context chưa `refresh()`; đây là trạng thái hợp lệ. | Đừng coi false là startup failed tại mốc này. |
| Property do initializer thêm không xuất hiện. | Initializer chưa đăng ký, thứ tự sai hoặc source ưu tiên khác ghi đè. | Xác minh `addInitializers`, `Ordered`, property sources. |
| Property thay đổi nhưng loại context không đổi. | Boot đã chọn/tạo context trước event. | Cấu hình web type ở pha sớm hơn. |
| Thấy Initialized event nhưng app vẫn startup fail. | Lỗi có thể xảy ra ở bước nạp bean/refresh/runner về sau. | Kiểm tra ngoại lệ gốc và `ApplicationFailedEvent`. |
| Listener in raw `getArgs()` làm lộ token. | Tham số có thể mang bí mật. | Chỉ log thông tin đã lọc, không log toàn bộ args. |
| Lệnh chạy startup bị treo ở event. | Listener thực hiện I/O/retry lâu và chạy đồng bộ. | Đặt timeout và chuyển công việc nặng sang cơ chế phù hợp. |
| Đăng ký listener trong `@Bean` nhưng không thấy event. | `@Bean` được xử lý trong refresh, quá muộn. | Đăng ký listener trước `run`. |
| Thấy event nhiều lần và tưởng loop. | Có thể có nhiều `SpringApplication`/context hoặc đăng ký trùng listener. | Kiểm tra context identity, source đăng ký và lifecycle. |
| Listener gọi `context.refresh()` để lấy bean. | Gọi refresh sai pha phá chuỗi của Boot. | Để `SpringApplication` quản lý refresh. |

## 17. Checklist kiểm tra khi triển khai thực tế

1. Phân biệt đúng **context created**, **initializers applied**, **definitions loaded**, **context refreshed** và **application ready**.
2. Xác định listener đã được đăng ký **trước `SpringApplication.run(...)`**.
3. Nếu dựa vào property do initializer tạo, xác minh thứ tự initializer và ưu tiên `PropertySource`.
4. Không lấy bean nghiệp vụ trong `ApplicationContextInitializedEvent`.
5. Không xử lý I/O kéo dài hoặc retry vô hạn trong listener khởi động sớm.
6. Không coi `isActive()==false` tại mốc này là lỗi.
7. Không dùng Initialized event để thay đổi lựa chọn SpringApplication đã áp dụng từ trước.
8. Nếu chỉ cần metadata bean definitions, chọn mốc `ApplicationPreparedEvent` hoặc BeanFactory post-processor.
9. Nếu cần dùng repository/service, đợi refresh và dùng runner hoặc lifecycle bean phù hợp.
10. Khi startup fail, tìm exception gốc và phân biệt failure ở initializer, listener, load definitions, refresh hay runner.
11. Khi có nhiều context, xác minh event thuộc đúng `SpringApplication`/context.
12. Không in secret hoặc làm thay đổi business state trong listener chỉ dùng để chẩn đoán.
13. Với code ví dụ, xác nhận thứ tự `INITIALIZER → CONTEXT_INITIALIZED → PREPARED → STARTED → RUNNER → READY`.

## 18. Những điều cốt lõi

```text
TẠO Context
     |
ÁP DỤNG ApplicationContextInitializer
     |
ApplicationContextInitializedEvent   <-- nhìn thấy kết quả initializer
     |
NẠP Bean Definitions
     |
ApplicationPreparedEvent
     |
REFRESH Context
     |
ApplicationStartedEvent
     |
Runner
     |
ApplicationReadyEvent
```

`ApplicationContextInitializedEvent` là điểm kiểm chứng **một pha chuẩn bị sớm của container đã hoàn tất**. Nó có thể đọc `Environment` và thông tin context, nhưng **chưa có các bean nghiệp vụ để sử dụng**. Muốn bắt được sự kiện, hãy đăng ký listener ở phía `SpringApplication` trước lúc chạy. Muốn thực hiện việc phụ thuộc bean, hãy chọn extension point muộn hơn.

## Tài liệu đối chiếu (Spring Boot 3.3)

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationContextInitializedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot 3.3 — ApplicationPreparedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
