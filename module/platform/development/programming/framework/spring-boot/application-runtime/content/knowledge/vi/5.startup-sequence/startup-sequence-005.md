# Tạo ApplicationContext và áp dụng Initializer trong chuỗi khởi động Spring Boot

## 1. Mô hình tổng thể: có “vỏ chứa” trước, có bean sau

Khi gọi `SpringApplication.run(...)`, Spring Boot phải chuẩn bị một **`ApplicationContext`**: nơi quản lý bean, cấu hình, sự kiện và tài nguyên ứng dụng. Một câu hỏi rất quan trọng là: nếu muốn tùy chỉnh context *trước khi các bean ứng dụng được tạo*, ta can thiệp ở đâu?

Spring Boot cung cấp `ApplicationContextInitializer` để làm việc đó. Nó nhận **context vừa được tạo và đã được chuẩn bị sơ bộ, nhưng chưa `refresh()`**, cho phép thay đổi cấu hình khởi tạo trước khi quá trình nạp và xây dựng bean hoàn tất.

Hãy hình dung việc mở một xưởng:

- **`SpringApplication`** là người điều phối việc mở xưởng.
- **`ApplicationContext`** là mặt bằng và hệ thống quản lý tài nguyên của xưởng.
- **`ApplicationContextInitializer`** là bước chuẩn bị mặt bằng trước khi đưa máy móc và công nhân vào.
- **Bean definitions** là bản mô tả những thành phần cần có và cách tạo chúng.
- **`refresh()`** là giai đoạn dựng và kích hoạt các thành phần theo cấu hình.
- **`ApplicationRunner`** là công việc chạy sau khi context đã sẵn sàng vận hành.

Nếu cần đặt một `PropertySource` chung trước khi Spring xử lý các bean, initializer có thể phù hợp. Nếu muốn dùng một `UserService` đã tiêm dependency để tải dữ liệu từ database, initializer thường **quá sớm**.

Bài học sử dụng API Spring Boot **3.3.x**, Spring Framework 6.x và Java **17+**. Các ví dụ dùng ứng dụng không mở HTTP server để quan sát thứ tự dễ hơn; cơ chế initializer vẫn áp dụng cho Servlet và Reactive.

## 2. Context được tạo ở đâu trong toàn bộ chuỗi khởi động?

Một chuỗi khởi động điển hình:

```text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- Chuẩn bị listeners / bootstrap / Environment
    |       |
    |       +-- ApplicationStartingEvent
    |       +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Xác định kiểu context và TẠO đối tượng ApplicationContext
    |       |
    |       +-- Gắn Environment; chuẩn bị cấu hình của context
    |       +-- applyInitializers(context)
    |       |       |
    |       |       +-- initializer.initialize(context)  [chưa refresh]
    |       |
    |       +-- ApplicationContextInitializedEvent
    |
    +-- Nạp nguồn cấu hình / bean definitions của ứng dụng
    |       |
    |       +-- ApplicationPreparedEvent
    |
    +-- context.refresh()
    |       |
    |       +-- BeanFactoryPostProcessor / BeanPostProcessor
    |       +-- Tạo các singleton không lazy, tiêm dependency
    |       +-- Khởi động hạ tầng web nếu có
    |       +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
```

Sơ đồ là **trật tự các mốc chính**, không mô tả hết mọi callback nội bộ. Các sự kiện như `WebServerInitializedEvent` chỉ có khi dùng môi trường web thích hợp và có thể xuất hiện trong giai đoạn `refresh()`.

Bốn mốc nên nhớ:

1. **`ApplicationEnvironmentPreparedEvent`**: `Environment` đã được chuẩn bị, nhưng chưa có context ứng dụng.
2. **Initializer chạy**: context đã tồn tại và được gắn `Environment`; bean definitions ứng dụng chưa được nạp theo chuỗi `SpringApplication` thông thường.
3. **`ApplicationContextInitializedEvent`**: các `ApplicationContextInitializer` đã chạy xong, ngay trước bước nạp bean definitions.
4. **`ApplicationPreparedEvent`**: bean definitions đã được nạp, nhưng `refresh()` chưa bắt đầu.

Đến `ApplicationStartedEvent`, context đã refresh xong; đến `ApplicationReadyEvent`, các runner cũng đã chạy. Vì vậy, **“context được tạo”, “context được khởi tạo bằng initializer”, “context được refresh” và “ứng dụng ready” là bốn ý khác nhau**.

## 3. Spring Boot chọn và tạo loại ApplicationContext nào?

`ApplicationContext` là một interface quản lý vòng đời và truy cập bean. `ConfigurableApplicationContext` mở thêm các thao tác phục vụ giai đoạn cấu hình như `setEnvironment(...)`, `addApplicationListener(...)`, `addBeanFactoryPostProcessor(...)`, `refresh()` và `close()`.

Thông thường bạn không tự viết `new AnnotationConfigApplicationContext()` trong ứng dụng Boot. `SpringApplication` dùng `ApplicationContextFactory` để tạo kiểu context thích hợp theo `WebApplicationType` và classpath:

| `WebApplicationType` | Context thường được tạo | Ý nghĩa |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Chứa bean và cấu hình; không tự mở web server. |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Hỗ trợ Servlet web server và hạ tầng Spring MVC. |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Hỗ trợ reactive web server và Spring WebFlux. |

Ví dụ:

- Công cụ CLI chỉ dùng `spring-boot-starter` thường tạo non-web context.
- REST API với `spring-boot-starter-web` thường tạo Servlet context.
- WebFlux server chỉ dùng `spring-boot-starter-webflux` thường tạo Reactive context.

Đây là mặc định của Spring Boot 3.3; `setApplicationContextFactory(...)` có thể thay cơ chế tạo context khi thật sự có yêu cầu đặc biệt.

**Sự khác nhau giữa tạo đối tượng và refresh:** `ApplicationContextFactory` chọn **lớp/instance context**; initializer tùy chỉnh **instance đó trước refresh**; `refresh()` mới kích hoạt công việc dựng bean và hạ tầng của context. Một initializer không tự đổi Servlet context thành Reactive context bằng cách thêm một property sau khi instance đã được chọn.

## 4. `ApplicationContextInitializer` là gì?

Interface được định nghĩa về mặt ý nghĩa như sau:

```java
@FunctionalInterface
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

Đây là chữ ký rút gọn để giải thích contract; hãy sử dụng interface thật `org.springframework.context.ApplicationContextInitializer` của Spring Framework.

`initialize(...)` được gọi **trước `refresh()`**. Không cần và không được tự gọi `refresh()` bên trong initializer của Boot. Tham số context là chính instance mà Boot sẽ tiếp tục nạp cấu hình, refresh và trả về sau khi khởi động thành công.

Initializer thường phù hợp để:

- Bổ sung `PropertySource` có chủ đích vào `Environment` của context.
- Đăng ký một `ApplicationListener` cần có trước khi context refresh.
- Đăng ký `BeanFactoryPostProcessor` để nó chạy ở đúng giai đoạn của `refresh()`.
- Cấu hình một số hành vi khởi tạo context hoặc tích hợp framework/library ở mức thấp.

Các phương thức an toàn, có contract rõ ràng gồm:

```java
context.getEnvironment().getPropertySources().addLast(propertySource);
context.addApplicationListener(listener);
context.addBeanFactoryPostProcessor(postProcessor);
```

Ba dòng là **minh họa các lệnh có thể gọi trong `initialize(...)`**, không phải file Java độc lập. Các biến `propertySource`, `listener` và `postProcessor` cần được tạo bằng các loại tương ứng trước khi dùng.

**Điều chưa nên làm trong initializer:** gọi `context.getBean(...)` để lấy bean nghiệp vụ, giả định `@Autowired` đã thực hiện, truy cập bean đã qua `@PostConstruct`, hoặc phục vụ HTTP request. Ở đây, context mới được cấu hình sơ bộ; quá trình đăng ký/khởi tạo bean đầy đủ chưa hoàn thành.

Một `ApplicationContextInitializer` được đăng ký sớm thường do Spring Boot tạo hoặc nhận trực tiếp như **đối tượng cấu hình khởi động**. Đừng cho rằng chỉ cần gắn `@Component`/`@Bean` lên class initializer là Boot sẽ tự tìm thấy và gọi nó đúng ở pha này: quét bean diễn ra quá muộn để thay thế cơ chế đăng ký initializer.

## 5. Vì sao Environment có sẵn trước khi các bean được tạo?

`Environment` biểu diễn các nguồn thuộc tính cấu hình và profile. Spring Boot chuẩn bị nó **trước khi tạo context**: kết hợp thông tin từ hệ điều hành, tham số dòng lệnh, cấu hình ứng dụng và các cơ chế cấu hình khác.

Khi `ApplicationContextInitializer.initialize(context)` chạy, thường có thể dùng:

```java
ConfigurableEnvironment env = context.getEnvironment();
String value = env.getProperty("demo.mode");
boolean active = env.acceptsProfiles(Profiles.of("dev"));
```

Đây là snippet bên trong initializer, cần import `ConfigurableEnvironment` và `Profiles`. Nó đọc thuộc tính và trạng thái profile của `Environment`. Tuy nhiên, việc thêm property trong initializer không làm cho *mọi* bước khởi động trước đó chạy lại.

Ví dụ, nếu kiểu `WebApplicationType` đã được Boot xác định và context đã được tạo, việc mới thêm `spring.main.web-application-type=reactive` ở đây **không thể quay ngược thời gian** để thay đúng instance context đã chọn. Những tùy chỉnh bắt buộc xảy ra **trước khi context tồn tại** cần được cấu hình ở `SpringApplication`, nguồn config khởi động hoặc extension point sớm hơn.

### 5.1. Thứ tự ưu tiên của PropertySource

`MutablePropertySources` có các thao tác như:

- `addFirst(...)`: thêm nguồn với độ ưu tiên cao trong tập nguồn hiện hành.
- `addLast(...)`: thêm nguồn với độ ưu tiên thấp.
- `addBefore(name, source)` / `addAfter(name, source)`: đặt tương đối với một nguồn được đặt tên.

Cần tránh vô tình dùng `addFirst` để ghi đè tham số dòng lệnh, biến môi trường hoặc cấu hình ngoài mà người vận hành cần được quyền đổi. Với **giá trị mặc định**, `addLast` thường phù hợp hơn; với **chính sách ưu tiên riêng**, phải nêu rõ thứ tự và thử trong tình huống trùng key.

Không đưa mật khẩu, token, dữ liệu nhạy cảm hoặc toàn bộ `Environment` vào log chẩn đoán. Dù initializer chạy trước bean, nó vẫn có thể nhìn thấy các property đã được chuẩn bị cho quá trình startup.

## 6. Ví dụ chạy được: thêm property rồi quan sát đúng ba mốc

Ví dụ sau gồm **một file Java hoàn chỉnh**. Để đơn giản và cho kết quả lặp lại, ta dùng `WebApplicationType.NONE`, không mở HTTP server.

**Yêu cầu:** dự án Gradle đã được tạo với Spring Boot 3.3.x, Java 17+ và dependency `spring-boot-starter`. Đặt file tại `src/main/java/com/example/bootstrap/ContextInitializerDemoApplication.java`.

```java
package com.example.bootstrap;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class ContextInitializerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextInitializerDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.addInitializers(new DefaultMessageInitializer());

        ApplicationListener<ApplicationContextInitializedEvent> listener =
                event -> System.out.println(
                        "2 EVENT context active="
                                + event.getApplicationContext().isActive());
        app.addListeners(listener);

        app.run(args);
    }

    public static class DefaultMessageInitializer
            implements ApplicationContextInitializer<ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            MapPropertySource defaults = new MapPropertySource(
                    "demoInitializerDefaults",
                    Map.of("demo.message", "Xin chao tu initializer")
            );

            context.getEnvironment()
                    .getPropertySources()
                    .addLast(defaults);

            System.out.println(
                    "1 INITIALIZER context active=" + context.isActive()
            );
        }
    }

    @Bean
    ApplicationRunner printMessage(Environment environment) {
        return args -> System.out.println(
                "3 RUNNER message=" + environment.getProperty("demo.message")
        );
    }
}
```

**Vì sao mã hợp lệ?**

1. `new SpringApplication(...)` cho phép đăng ký initializer và listener **trước** `run`.
2. `app.setWebApplicationType(NONE)` giữ ví dụ ở context không có HTTP server.
3. `DefaultMessageInitializer` implement đúng generic `ApplicationContextInitializer<ConfigurableApplicationContext>`; `MapPropertySource` cung cấp property mặc định.
4. `ApplicationContextInitializedEvent` được listener đăng ký sớm nhận sau khi initializer đã chạy, nhưng trước khi nạp bean definitions.
5. Phương thức `@Bean printMessage` chỉ được Spring xử lý trong giai đoạn cấu hình/refresh; `ApplicationRunner` của nó được gọi **sau khi refresh hoàn tất**.

### 6.1. Dependency tối thiểu

Trong một dự án đã có Spring Boot Gradle plugin 3.3.x và dependency management tương ứng, phần dependency đủ cho ví dụ là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Không cần `spring-boot-starter-web`. Đối với ví dụ non-web, không dùng `curl` để thử vì không có server HTTP nào được mở.

### 6.2. Chạy và đọc kết quả

```bash
./gradlew bootRun
```

Trên Windows CMD dùng `gradlew.bat bootRun`; trong PowerShell có thể dùng `.\gradlew.bat bootRun`.

Bỏ qua banner và các dòng log Spring Boot xen kẽ. Ba dòng từ chính ví dụ, theo thứ tự, là:

```text
1 INITIALIZER context active=false
2 EVENT context active=false
3 RUNNER message=Xin chao tu initializer
```

Giải thích stdout:

- Hai dòng đầu in `false` vì ở thời điểm initializer và `ApplicationContextInitializedEvent`, context **chưa refresh** nên chưa active.
- Dòng thứ ba in sau khi context đã refresh và bean `ApplicationRunner` đã được tạo.
- Đây là **thứ tự các log do chương trình tự in**, không cam kết toàn bộ log framework không xen vào giữa.
- Với ứng dụng `NONE` không có thread nền giữ JVM, tiến trình có thể thoát sau khi hoàn tất startup/runner.

Nếu chạy với property từ dòng lệnh:

```bash
./gradlew bootRun --args='--demo.message=Tu tham so dong lenh'
```

Dòng runner dự kiến trở thành `3 RUNNER message=Tu tham so dong lenh` vì nguồn `demoInitializerDefaults` được thêm bằng `addLast`. Với Windows CMD, cách trích dẫn tham số có thể khác; có thể đặt property ở `application.properties` để kiểm tra ưu tiên một cách đơn giản.

**Bài học:** initializer có thể sửa môi trường cấu hình trước bean; nó không phải nơi xử lý công việc nghiệp vụ sau khi ứng dụng ready.

## 7. Các cách đăng ký ApplicationContextInitializer

### 7.1. Đăng ký tường minh trong `main`

Đây là phương pháp dễ đọc nhất khi initializer thuộc một ứng dụng cụ thể:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addInitializers(new MyInitializer());
app.run(args);
```

Ba dòng là snippet ở trong method `main` của class `MyApplication`; `MyInitializer` phải implements `ApplicationContextInitializer`. `addInitializers(...)` thêm initializer vào tập các initializer đã có, bao gồm các initializer Boot đăng ký.

Có thể thay bằng `app.setInitializers(...)` khi thật sự muốn **thay toàn bộ tập initializer**; thao tác thay thế có thể làm mất initializer mà Boot hoặc thư viện cần, vì vậy đừng dùng như phép “thêm” thông thường.

### 7.2. `SpringApplicationBuilder`

Khi cần fluent API hoặc có nhiều cấu hình khởi động:

```java
new SpringApplicationBuilder(MyApplication.class)
        .initializers(new MyInitializer())
        .web(WebApplicationType.NONE)
        .run(args);
```

Đây cũng là snippet trong `main`, cần import `SpringApplicationBuilder` và `WebApplicationType`; `MyApplication`/`MyInitializer` là class do ứng dụng định nghĩa. Về bản chất, initializer vẫn chạy **sau khi context được tạo và trước `refresh()`**.

### 7.3. Tự động đăng ký qua `META-INF/spring.factories`

Phù hợp khi bạn phát triển thư viện dùng chung, và nhiều ứng dụng Boot cần cùng bước tùy chỉnh sớm. Trong artifact JAR, thêm file:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.TraceInitializer
```

Class được chỉ định phải triển khai `ApplicationContextInitializer` và có thể được tạo bởi cơ chế factory loading. Ví dụ class độc lập:

**`src/main/java/com/example/bootstrap/TraceInitializer.java`**

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class TraceInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    public TraceInitializer() {
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("TraceInitializer before refresh");
    }
}
```

Boot phát hiện initializer từ `META-INF/spring.factories` trên classpath lúc khởi tạo `SpringApplication`. **Đây là phương án thay thế** cho đăng ký thủ công; không cần vừa khai báo cùng class trong `spring.factories` vừa thêm thủ công nếu không muốn nguy cơ chạy lặp.

Lưu ý: không nhầm `META-INF/spring.factories` dùng cho initializer/listener với cơ chế khai báo **auto-configuration classes** đã thay đổi ở Spring Boot 3.x. Chúng là các nhu cầu đăng ký khác nhau.

## 8. Thứ tự khi có nhiều initializer

Một ứng dụng có thể nhận initializer từ Spring Boot, thư viện phụ trợ và chính mã ứng dụng. Khi thứ tự có ý nghĩa, nên dùng `org.springframework.core.Ordered` hoặc annotation `@Order`.

Ví dụ lớp initializer ở project có thể khai báo:

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public class FirstInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("Initializer first");
    }
}
```

Phần còn lại của ứng dụng cần **đăng ký** `FirstInitializer` bằng một trong những cách đã nêu. `getOrder()` trả về số nhỏ hơn thì được ưu tiên chạy sớm hơn theo cơ chế sắp xếp của Boot. Tránh phụ thuộc vào thứ tự ngẫu nhiên giữa các initializer có cùng giá trị order.

**Tình huống có thứ tự phụ thuộc:** initializer A cần đặt một `PropertySource`, initializer B đọc property đó. Nếu A và B không được sắp thứ tự rõ ràng, B có thể chạy khi property chưa xuất hiện. Hãy mô tả dependency giữa chúng và kiểm tra thứ tự thật bằng log/test.

Đừng nhầm thứ tự initializer với thứ tự bean initialization (`@DependsOn`, `@Order` của danh sách bean, `SmartLifecycle`): đó là các tầng lifecycle khác nhau.

## 9. Phân biệt với các cơ chế khởi tạo khác

| Cơ chế | Khi nào hoạt động | Dùng vào việc gì? | Có thể lấy bean nghiệp vụ thông thường? |
| --- | --- | --- | --- |
| `BootstrapRegistryInitializer` | Trong giai đoạn bootstrap trước khi có context hoàn chỉnh | Đăng ký đối tượng/hạ tầng tạm cho bootstrap | Không nên phụ thuộc bean của context. |
| `EnvironmentPostProcessor` | Chuẩn bị `Environment` sớm | Nguồn cấu hình, property trước khi context được tạo | Chưa có bean của context. |
| `ApplicationContextInitializer` | Context đã được tạo, **trước nạp bean definitions/refresh** | Tùy chỉnh context/environment, đăng ký post-processor/listener | Chưa. |
| `BeanDefinitionRegistryPostProcessor` | Khi xử lý các bean definitions trong `refresh()` | Thêm/sửa bean definitions trước khi bean được khởi tạo | Không nên phụ thuộc singleton nghiệp vụ. |
| `BeanFactoryPostProcessor` | Trong `refresh()`, trước khi tạo singleton thông thường | Thay đổi metadata/cấu hình BeanFactory | Không nên tạo bean nghiệp vụ sớm. |
| `BeanPostProcessor` | Bao quanh quá trình khởi tạo từng bean | Tùy biến bean instance, proxy, callback | Làm việc với bean đang được tạo. |
| `@PostConstruct` | Khi một bean cụ thể được khởi tạo | Hoàn tất cấu hình nội bộ của bean | Những dependency đã được tiêm theo vòng đời bean. |
| `ApplicationRunner`/`CommandLineRunner` | **Sau khi context refresh** | Công việc khởi động cần bean/hạ tầng | Có. |
| `ApplicationReadyEvent` | Sau runners | Ghi nhận mốc Boot hoàn tất khởi động | Có. |

Chọn extension point theo **thời điểm bạn thật sự cần**. Nếu cần nạp cache từ repository thì nên dùng runner hoặc một service có lifecycle rõ ràng; không nên đưa truy vấn database nặng vào initializer. Nếu cần thêm config cho chính quá trình dựng bean thì initializer có thể thích hợp, nhưng nếu phải ảnh hưởng sớm tới **config-loading** hay **quyết định loại context**, dùng cơ chế sớm hơn.

### 9.1. Initializer không phải `@PostConstruct` của toàn ứng dụng

`@PostConstruct` chỉ chạy sau khi một bean riêng lẻ được tạo và dependency đã được tiêm. Một initializer có thể chạy khi **chưa tồn tại bean ứng dụng nào**. Không được dùng `@PostConstruct` để giả lập việc chuẩn bị context trước bean definitions.

### 9.2. Initializer không phải `ApplicationListener`

- Initializer nhận trực tiếp `ConfigurableApplicationContext` và được Boot gọi để tùy chỉnh nó trước refresh.
- Listener phản ứng với một `ApplicationEvent` cụ thể, ví dụ `ApplicationContextInitializedEvent` hoặc `ApplicationReadyEvent`.
- `ApplicationContextInitializedEvent` **được phát sau khi toàn bộ initializer đã áp dụng**; listener của nó không thay thế vị trí khởi tạo sớm của initializer.

Đặc biệt, listener nhận các sự kiện rất sớm phải được đăng ký trước `run` (qua `addListeners(...)` hoặc cơ chế đăng ký sớm phù hợp). Một `@EventListener` trong bean ứng dụng sẽ được tạo quá muộn để bắt `ApplicationStartingEvent` hay `ApplicationContextInitializedEvent` trong đợt khởi động đó.

## 10. Tình huống sử dụng thực tế và lựa chọn đúng chỗ

### Tình huống A — Thêm giá trị mặc định cho thư viện nội bộ

Một thư viện có property `acme.feature.mode`; ứng dụng có thể override bằng biến môi trường hoặc config riêng. Initializer của thư viện thêm `MapPropertySource` với `addLast(...)`. Các bean tạo sau đó có thể đọc giá trị mặc định, nhưng cấu hình của người vận hành vẫn có thể ghi đè.

**Cần kiểm tra:** source name không trùng ngoài ý muốn, đúng thứ tự ưu tiên, không đặt giá trị nhạy cảm vào source, và không vô tình áp dụng hai lần nếu vừa đăng ký thủ công vừa qua `spring.factories`.

### Tình huống B — Đăng ký post-processor trước refresh

Bạn cần tác động tới BeanFactory trong khi các bean definitions đã được nạp, nhưng muốn quyết định việc đó lúc bootstrap:

```java
@Override
public void initialize(ConfigurableApplicationContext context) {
    context.addBeanFactoryPostProcessor(beanFactory ->
            System.out.println("Bean definitions loaded: "
                    + beanFactory.getBeanDefinitionCount()));
}
```

Đây là **method minh họa** bên trong một class implements `ApplicationContextInitializer<ConfigurableApplicationContext>`. Callback đăng ký tại initializer sẽ được gọi trong `refresh()`, sau khi các definitions đã được nạp, thay vì chạy ngay trong `initialize(...)`. Không dùng callback như một cách tùy tiện để khởi tạo các bean nghiệp vụ sớm.

### Tình huống C — Phải quyết định WebApplicationType

Nếu mục tiêu là chạy CLI không có web server, hãy cấu hình trước khi tạo context:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
```

Đừng thêm property đổi web type vào một initializer với hy vọng Boot sẽ hủy context đã tạo rồi tạo lại loại khác. `WebApplicationType` và `ApplicationContextFactory` điều khiển bước **tạo context**, tức là xảy ra trước initializer.

### Tình huống D — Kiểm tra phụ thuộc sống/chết hoặc nạp dữ liệu ban đầu

Dùng một `ApplicationRunner` có tiêm service/repository và xử lý lỗi rõ ràng. Với service web, tác vụ runner kết thúc trước `ApplicationReadyEvent`; nếu cần sẵn sàng nhận traffic sau bước khởi tạo, readiness nên phản ánh trạng thái đó. Initializer không phải vị trí thích hợp để mở kết nối kéo dài, tải hàng triệu bản ghi hoặc chờ hệ thống ngoài vô thời hạn.

### Tình huống E — Dùng chung một initializer trong nhiều ứng dụng

Đóng gói thành thư viện và đăng ký qua `spring.factories`. Thiết kế phải không phụ thuộc loại context cụ thể nếu muốn dùng chung cho `NONE`, `SERVLET` và `REACTIVE`. Nếu initializer cần API riêng của Servlet/Reactive, chỉ áp dụng khi instance tương thích và kiểm thử cho từng mode.

## 11. Lỗi thường gặp khi tạo context/áp dụng initializer

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Không thấy `initialize(...)` được gọi | Chỉ gắn `@Component`, chưa đăng ký với `SpringApplication`/`spring.factories` | Đăng ký sớm bằng `addInitializers(...)` hoặc factory metadata. |
| `getBean(...)` không lấy được service tại initializer | Context chưa refresh; singleton chưa được tạo | Chuyển sang runner/bean lifecycle hoặc đăng ký post-processor cho đúng pha. |
| `ApplicationContextInitializedEvent` không đến `@EventListener` | Bean listener được tạo sau mốc sự kiện | Đăng ký listener sớm qua `addListeners(...)`. |
| Property thêm trong initializer không đổi kiểu web | `WebApplicationType` đã được chọn và context đã được tạo | Đặt web type trước `run` bằng API hoặc cấu hình khởi động thích hợp. |
| Property mặc định vô tình ghi đè giá trị vận hành | Dùng `addFirst(...)` cho source cần ưu tiên thấp | Chọn `addLast(...)`, kiểm tra thứ tự property sources và kết quả override. |
| Mã chạy hai lần hoặc log initializer lặp | Initializer được đăng ký ở nhiều nơi, hoặc có nhiều context khởi động | Kiểm tra `spring.factories`, `main`, context hierarchy/test configuration. |
| Thứ tự hai initializer sai | Không dùng `Ordered`/`@Order` hoặc cùng order | Đặt thứ tự rõ ràng và kiểm tra dependency. |
| Startup dừng trước `ApplicationPreparedEvent` | Initializer ném exception hoặc có lỗi cấu hình trước refresh | Xem stack trace gốc, listener `ApplicationFailedEvent` đăng ký sớm, property source. |
| Ứng dụng chậm startup bất thường | Initializer làm network I/O, đọc quá nhiều dữ liệu hoặc chờ vô hạn | Chuyển công việc nặng sang runner/service và dùng timeout, log có chọn lọc. |
| Chạy được JVM mode này nhưng thất bại mode khác | Ép initializer sang subtype context không phù hợp | Dùng `ConfigurableApplicationContext` khi có thể, kiểm tra class trước khi cast. |

### 11.1. Vì sao không nên gọi `refresh()` hoặc `close()` từ initializer?

`SpringApplication` đang điều khiển chuỗi lifecycle. Gọi `context.refresh()` quá sớm có thể làm bean được tạo trước khi Boot nạp đủ nguồn cấu hình và đăng ký listener/post-processor. Gọi `context.close()` làm hỏng tiến trình bootstrap. Hãy để Boot quản lý hai mốc đó; initializer chỉ thực hiện các tùy chỉnh đã được thiết kế cho pha trước refresh.

### 11.2. Nếu initializer ném exception thì sao?

Lỗi khởi động có thể xuất hiện trước khi các bean thường được tạo. Boot xử lý lỗi trong chuỗi startup và có thể phát `ApplicationFailedEvent`; không có `ApplicationReadyEvent` khi khởi động thất bại. Nếu cần ghi nhận lỗi rất sớm, listener cũng phải đăng ký sớm. Tránh nuốt exception rồi để ứng dụng tiếp tục với cấu hình sai; khi thật sự có thể dùng fallback an toàn, hãy định nghĩa rõ điều kiện và cách quan sát fallback.

### 11.3. Có thể có nhiều ApplicationContext không?

Có. Một ứng dụng đơn giản thường chỉ có một context chính; hệ thống có cấu trúc parent/child, nhiều `SpringApplication` hay một số bài test có thể tạo nhiều context. Cần xác định initializer gắn vào **SpringApplication nào**, và nhớ rằng event từ child context có thể được phát tới ancestor listener. Không nên xây chính sách dựa trên giả định initializer hoặc listener của toàn tiến trình chắc chắn chỉ chạy một lần.

## 12. Quy trình QA khi thay đổi initializer

Khi sửa một initializer thực sự được dùng trong dự án, thực hiện kiểm tra theo **hành vi**:

1. Ghi nhận `ApplicationContext` thực tế được tạo cho `NONE`, `SERVLET` hoặc `REACTIVE`.
2. Xác nhận initializer chạy trước `ApplicationContextInitializedEvent` và trước `refresh()`; tránh lấy bean.
3. Kiểm tra property sources khi có trùng key: giá trị từ config/CLI có override đúng chủ đích không?
4. Kiểm tra `Ordered` nếu có hơn một initializer phụ thuộc nhau.
5. Kiểm tra luồng lỗi: khi initializer thất bại, ứng dụng không công bố ready sai.
6. Kiểm tra lại chế độ chạy thực tế cùng các integration/test profile liên quan; đừng suy luận từ log của một môi trường duy nhất.
7. Không đưa token và dữ liệu nhạy cảm vào log để chứng minh hoạt động.

Một phép thử đơn giản cho ví dụ ở `6 là thay đổi giá trị `demo.message` từ config ngoài và xác nhận log của runner nhận giá trị mới; các log `INITIALIZER` và `EVENT` vẫn phải xảy ra **trước** log `RUNNER`.

## 13. Những điều cần nhớ

- **Tạo context** = dựng đối tượng `ConfigurableApplicationContext` đúng kiểu để Boot tiếp tục cấu hình.
- **Áp dụng initializer** = gọi `initialize(context)` trên các `ApplicationContextInitializer` đã đăng ký, **trước `refresh()`**.
- **`ApplicationContextInitializedEvent`** xác nhận initializer đã chạy và việc nạp bean definitions theo chuỗi khởi động chính còn ở phía sau.
- **`ApplicationPreparedEvent`** xảy ra sau khi bean definitions được nạp, ngay trước refresh.
- **`refresh()`** thực hiện phần cốt lõi của việc dựng bean, post-processor, vòng đời singleton và (nếu có) web infrastructure.
- **`ApplicationRunner`** chạy sau refresh; thích hợp cho công việc cần dùng bean nghiệp vụ.
- **`SpringApplication`** quản lý toàn bộ thứ tự. Chọn đúng extension point và không tự thúc ép một giai đoạn lifecycle sớm hơn mức framework hỗ trợ.

## 14. Tài liệu Spring chính thức

- [Spring Boot 3.3 — `SpringApplication`: application events và thứ tự khởi động](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — `SpringApplication` API: createApplicationContext, setApplicationContextFactory, addInitializers, applyInitializers](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Framework 6.1 — `ApplicationContextInitializer` API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — `ConfigurableApplicationContext` API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
