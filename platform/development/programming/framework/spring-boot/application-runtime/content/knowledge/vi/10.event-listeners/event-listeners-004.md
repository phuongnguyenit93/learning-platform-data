# Đăng ký listener qua `SpringApplicationBuilder` hoặc `spring.factories`

Trong Spring Boot, một **`ApplicationListener`** có thể phản ứng với các sự kiện của quá trình khởi động: ứng dụng vừa bắt đầu, `Environment` đã được chuẩn bị, `ApplicationContext` đã được tạo, context refresh xong, runners hoàn tất, hoặc quá trình khởi động thất bại.

Vấn đề quan trọng là **thời điểm đăng ký listener**. Một số sự kiện đầu tiên được phát **trước khi Spring tạo `ApplicationContext` và bean của ứng dụng**. Vì vậy, một listener chỉ được phát hiện thông qua `@Component` hay `@Bean` trong context không thể quan sát đáng tin cậy các sự kiện quá sớm đó. Khi cần đăng ký trước lúc `run()` bắt đầu, Spring Boot cung cấp hai cơ chế phù hợp:

1. **`SpringApplicationBuilder.listeners(...)`:** đăng ký bằng mã Java cho lần khởi chạy đang xây dựng.
2. **`META-INF/spring.factories`:** khai báo tên lớp listener để Spring Boot tự tải từ classpath, kể cả khi điểm vào ứng dụng không tự gọi `listeners(...)`.

Bài học sử dụng Spring Boot **3.3.x**, Spring Framework 6.1 và **Java 17+**. Các ví dụ minh họa có thể dùng trong dự án Gradle của Spring Boot, đồng thời phân biệt rõ listener ở giai đoạn rất sớm với listener được tạo làm bean.

## 1. Listener là gì trong ngữ cảnh Spring Boot?

`ApplicationListener<E>` là giao diện của Spring Framework:

~~~java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {
    void onApplicationEvent(E event);
}
~~~

Đây là **chữ ký rút gọn để giải thích API**, không phải toàn bộ mã nguồn giao diện. Với ví dụ thực tế, ta triển khai một event cụ thể:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyNoticeListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Listener: SpringApplication has started");
    }
}
~~~

Đoạn trên là **một lớp Java hoàn chỉnh khi nằm trong dự án có Spring Boot trên classpath**. Nó chỉ chạy khi một `SpringApplication` hoặc context thích hợp thực sự đăng ký listener và phát `ApplicationStartingEvent`. Việc có class trong source code không có nghĩa listener đã được kích hoạt.

Spring Boot phát các sự kiện liên quan đến `SpringApplication` theo các mốc chính:

| Sự kiện | Khi nào xuất hiện? | Đã có gì để dùng? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Rất sớm ngay khi một lần `run` bắt đầu, sau khi đăng ký listener/initializer | **Chưa có** `Environment` hay `ApplicationContext` |
| `ApplicationEnvironmentPreparedEvent` | `Environment` đã chuẩn bị, nhưng context chưa được tạo | Có thể truy cập `Environment` qua event |
| `ApplicationContextInitializedEvent` | Context đã được chuẩn bị và initializer đã chạy; trước khi nạp bean definitions | Có context nhưng chưa refresh |
| `ApplicationPreparedEvent` | Các nguồn/bean definitions đã được nạp; trước refresh | Có context đang chuẩn bị; không giả định mọi bean đã tạo |
| `ApplicationStartedEvent` | Sau refresh thành công, **trước** `ApplicationRunner`/`CommandLineRunner` | Context đã refresh |
| `ApplicationReadyEvent` | Sau khi runners hoàn tất | Vòng đời startup đã đạt mốc sẵn sàng |
| `ApplicationFailedEvent` | Nếu một lần khởi động thất bại | Mức độ sẵn có của environment/context phụ thuộc lỗi xảy ra khi nào |

Ngoài bảng trên còn có `ContextRefreshedEvent`, `WebServerInitializedEvent` và `AvailabilityChangeEvent`. Chúng không đồng nghĩa với mọi sự kiện `SpringApplication` trong bảng. Listener được đăng ký sớm có thể tiếp tục nhận những event phù hợp khi context đã hoạt động.

**Điều cần nhớ:** `ApplicationStartingEvent` không phải `ApplicationStartedEvent`. Sự kiện thứ nhất xuất hiện đầu tiên; sự kiện thứ hai xuất hiện khi context đã refresh xong.

## 2. Vì sao cần đăng ký listener trước khi tạo bean?

Nếu chỉ viết:

~~~java
@Component
public class StartupLogger
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Application starting");
    }
}
~~~

thì lớp trên chỉ trở thành listener thông qua cơ chế đăng ký bean của context. Nhưng ở thời điểm `ApplicationStartingEvent` được phát, context và bean `StartupLogger` **chưa được tạo**. Vì thế, cách đăng ký như bean này **không bắt được sự kiện đầu tiên trong quá trình khởi chạy thông thường**.

Tương tự, chỉ khai báo `@EventListener` trên một phương thức của bean cũng không biến nó thành listener được đăng ký trước khi context hình thành.

Để quan sát event sớm, cần một đối tượng listener đã được Spring Boot biết tới **trước hoặc ngay khi `run()` bắt đầu**. Cụ thể:

- **`SpringApplication.addListeners(...)`:** tạo đối tượng `SpringApplication`, đăng ký listener trước lời gọi `run`.
- **`SpringApplicationBuilder.listeners(...)`:** dùng fluent builder để thêm listener trước `run`.
- **`META-INF/spring.factories`:** đưa tên triển khai vào một resource mà cơ chế tải factories của Spring Boot tìm trên classpath.

Ba cách trên phục vụ cùng nhu cầu đăng ký sớm, nhưng có khác biệt về phạm vi cấu hình và khả năng tái sử dụng.

## 3. Cách A — Đăng ký bằng `SpringApplicationBuilder.listeners(...)`

`SpringApplicationBuilder` cung cấp API dạng chuỗi để cấu hình `SpringApplication` và, nếu cần, xây dựng quan hệ parent/child giữa các context. Phương thức:

~~~java
SpringApplicationBuilder listeners(ApplicationListener<?>... listeners)
~~~

nhận một hay nhiều đối tượng listener đã được tạo. Phần tiếp theo của fluent API sẽ gọi `run(args)` để khởi chạy ứng dụng.

Ví dụ về điểm vào:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class BuilderExample {

    public static void main(String[] args) {
        new SpringApplicationBuilder(BuilderExample.class)
                .listeners(new MyEarlyListener())
                .run(args);
    }

    public static final class MyEarlyListener
            implements ApplicationListener<ApplicationStartingEvent> {

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            System.out.println("BUILDER: starting");
        }
    }
}
~~~

Đây là **minh họa cơ chế builder**; để dùng làm ứng dụng Spring Boot hoàn chỉnh cần cấu hình nguồn bean chính, phụ thuộc và entrypoint thích hợp như ví dụ thực hành ở phần 7. Trong mã thực tế, builder phải chứa class cấu hình chính và listener được tạo **trước `run`**.

### Điều gì diễn ra?

~~~text
main()
  |
  v
new SpringApplicationBuilder(MainConfig.class)
  |
  v
.listeners(new MyEarlyListener())
  |   Lưu listener cho SpringApplication đang xây dựng
  v
.run(args)
  |   Spring Boot bắt đầu chu kỳ startup
  |   Phát ApplicationStartingEvent
  +--> MyEarlyListener.onApplicationEvent(...)
  |
  v
Chuẩn bị Environment -> Tạo/refresh Context -> Started -> Runners -> Ready
~~~

Điểm cần nhấn mạnh: builder không phải một event bus riêng. Nó là cách **cấu hình `SpringApplication`**, rồi Spring Boot dùng cơ chế phát event của framework.

### Khi nào nên dùng builder?

Chọn builder khi:

- Bạn **quản lý điểm vào `main`** và muốn biết listener nào được gắn cho lần chạy này.
- Bạn đã dùng fluent API để thiết lập `profiles(...)`, `properties(...)`, `bannerMode(...)`, `web(...)` hoặc hierarchy.
- Cần cấu hình listener khác nhau theo môi trường kiểm thử hoặc theo từng entrypoint.
- Không muốn một thư viện tự đăng ký listener vào mọi ứng dụng chỉ vì có mặt trên classpath.

Ví dụ builder có thể đăng ký nhiều listener:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(
                new StartingListener(),
                new EnvironmentListener())
        .run(args);
~~~

Hai lớp `StartingListener` và `EnvironmentListener` ở đoạn trên là **tên minh họa**, phải được định nghĩa với `ApplicationListener` và kiểu event tương ứng trong dự án. Không cần dùng builder chỉ để đăng ký listener: `SpringApplication.addListeners(...)` cũng thực hiện việc đó.

### So sánh với `SpringApplication.addListeners(...)`

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.addListeners(new StartingListener());
application.run(args);
~~~

Phương án trên có ý nghĩa tương tự khi chỉ cần khởi chạy một ứng dụng. Cả hai cách đều yêu cầu gọi **trước `run`**. Cố thêm listener sau khi `ApplicationStartingEvent` đã phát **không khiến sự kiện đã qua được phát lại**.

**Chú ý:** `SpringApplicationBuilder.listeners(...)` nhận **instance listener**, không nhận tên class `String`. Điều này cho phép bạn chủ động khởi tạo listener, truyền các tham số cấu hình riêng và kiểm soát phạm vi đăng ký.

## 4. Cách B — Tự đăng ký bằng `META-INF/spring.factories`

Trong Spring Boot 3.3, một thư viện hoặc ứng dụng có thể đặt tệp:

~~~text
src/main/resources/META-INF/spring.factories
~~~

với nội dung:

~~~properties
org.springframework.context.ApplicationListener=com.example.runtime.EarlyStartupListener
~~~

Trong đó:

- **Key** là tên đầy đủ của giao diện `org.springframework.context.ApplicationListener`.
- **Value** là tên đầy đủ của lớp triển khai, bao gồm package.
- Spring Boot tìm các tệp `META-INF/spring.factories` có trên **classpath** và tải các listener được khai báo theo key thích hợp.
- Listener có thể được tải dù mã `main` chỉ gọi `SpringApplication.run(MyApplication.class, args)` và **không hề gọi `addListeners` hoặc `builder.listeners`**.

Một tệp `spring.factories` có thể khai báo nhiều listener bằng dấu phẩy:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.runtime.FirstListener,\
com.example.runtime.SecondListener
~~~

Dấu `\` ở cuối dòng biểu thị **tiếp tục dòng** trong định dạng Java `.properties`. Có thể viết toàn bộ danh sách trên một dòng để tránh sai cú pháp.

### Cần phân biệt với Spring bean

Một lớp listener khai báo trong `spring.factories` được cơ chế bootstrap **tạo độc lập với bean của `ApplicationContext`**. Vì thế, ví dụ an toàn là một class `public` có constructor không tham số, không yêu cầu constructor injection từ Spring:

~~~java
package com.example.runtime;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public EarlyStartupListener() {
        // Constructor không đòi một Spring bean.
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("FACTORIES listener invoked");
    }
}
~~~

Khi tải từ `spring.factories`, Spring Boot không đợi container tạo bean rồi mới khởi tạo listener. Đừng viết:

~~~java
public EarlyStartupListener(MyRepository repository) {
    // Không có bảo đảm MyRepository là bean đã tồn tại ở đây.
}
~~~

rồi kỳ vọng hệ thống tự thực hiện `@Autowired` như với một `@Component` thông thường. Với listener ở giai đoạn rất sớm, cần sử dụng dữ liệu có sẵn từ event hoặc cấu hình không phụ thuộc vào bean ứng dụng. Một constructor không phù hợp có thể khiến việc tải listener thất bại và làm ứng dụng không khởi chạy được.

### Thư viện dùng chung

Đây là trường hợp `spring.factories` đặc biệt hữu ích. Nếu một JAR của thư viện chứa:

~~~text
META-INF/spring.factories
com/example/runtime/EarlyStartupListener.class
~~~

và JAR đó được thêm vào runtime classpath của ứng dụng, listener có thể được Spring Boot tự phát hiện. Tính năng đó thuận tiện để đóng gói các listener của một thư viện hạ tầng, nhưng cũng có nghĩa chúng có thể chạy trong **mọi Spring Boot application có thư viện trên classpath**. Vì vậy, nên thiết kế listener có tác động phụ hạn chế, tránh giả định một loại context cụ thể nếu thư viện dùng cho nhiều ứng dụng.

**Giới hạn phạm vi:** `spring.factories` không làm listener tự chạy khi chỉ có Java thông thường; cần có tiến trình Spring Boot/Spring phù hợp thực sự gọi cơ chế tải factories và phát event. Không được nhầm “tự phát hiện từ classpath” với “đăng ký toàn cục cho mọi JVM”.

## 5. Spring Boot 3.x: `spring.factories` còn dùng để đăng ký listener không?

**Có.** Spring Boot 3.3 vẫn hỗ trợ khai báo `ApplicationListener` trong `META-INF/spring.factories`. Quy tắc này được nêu trong tài liệu SpringApplication 3.3.

Một nhầm lẫn thường gặp là: “Spring Boot 3.x đã chuyển hết nội dung từ `spring.factories` sang `AutoConfiguration.imports`, nên đăng ký listener bằng `spring.factories` không còn hoạt động”. Nhận định đó **sai nếu áp dụng cho `ApplicationListener`**.

Hai loại đăng ký khác nhau:

| Mục đích | Vị trí/khai báo trong Spring Boot 3.3 |
| --- | --- |
| Đăng ký `ApplicationListener` để tải từ bootstrap | `META-INF/spring.factories`, key `org.springframework.context.ApplicationListener` |
| Đăng ký `ApplicationContextInitializer` theo cơ chế tương tự | `META-INF/spring.factories`, key dành cho initializer |
| Liệt kê các lớp auto-configuration cho cơ chế Spring Boot hiện đại | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Đăng ký bean trong context | `@Component`, `@Bean`, auto-configuration và cơ chế BeanDefinition |

**Không đặt tên listener trong `AutoConfiguration.imports` để thay cho key `ApplicationListener`.** Tệp auto-configuration imports dành cho việc tải các lớp cấu hình tự động, không phải cách bắt một `ApplicationStartingEvent` sớm.

Tương tự, thuộc tính `spring.main.*` không phải bản thay thế tổng quát cho cơ chế đăng ký listener; nó chủ yếu cấu hình hoạt động của `SpringApplication`.

## 6. So sánh hai cách đăng ký

| Tiêu chí | `SpringApplicationBuilder.listeners(...)` | `META-INF/spring.factories` |
| --- | --- | --- |
| Nơi cấu hình | Mã Java ở điểm khởi chạy | Resource tệp `.properties` trên classpath |
| Đầu vào | Đối tượng `ApplicationListener` đã tạo | Tên lớp listener đầy đủ |
| Thời điểm được biết tới | Trước `builder.run(args)` | Trong quá trình bootstrap, khi Spring Boot tải các listener từ classpath |
| Bắt sự kiện sớm như `ApplicationStartingEvent` | Có | Có |
| Cần là Spring bean | Không | Không |
| Thích hợp khi | Điều khiển trực tiếp một entrypoint, cấu hình tùy biến | Thư viện chia sẻ hoặc listener muốn tự đăng ký qua classpath |
| Có thể truyền tham số constructor thủ công | Có | Không theo cách bean injection thông thường |
| Có thể tái sử dụng trong nhiều ứng dụng | Mỗi entrypoint cần đăng ký hoặc tái sử dụng builder | Có nếu thư viện/tệp nằm trên classpath |
| Rủi ro thường gặp | Quên gọi `listeners` trước `run`; đăng ký lặp | Sai path, key, package, constructor, resource không được đóng gói |
| Khả năng cấu hình theo lần chạy | Rõ ràng, linh hoạt | Thường theo nội dung classpath; muốn thay đổi hành vi phải thiết kế cấu hình bên trong listener |

Chúng **không loại trừ nhau**. Một ứng dụng có thể đồng thời có listener do builder đăng ký và listener do `spring.factories` tự tải. Nhưng cần tránh đăng ký **cùng một logic nhiều lần** mà không kiểm soát tác động lặp lại.

## 7. Ví dụ thực hành chạy được: quan sát cả hai cơ chế

Ta tạo một ứng dụng Spring Boot chạy **không có web server**. Bản demo cố ý có hai listener khác nhau:

- **`BuilderStartingListener`** nghe `ApplicationStartingEvent`, được đăng ký bằng `SpringApplicationBuilder.listeners(...)`.
- **`FactoriesEnvironmentListener`** nghe `ApplicationEnvironmentPreparedEvent`, được đăng ký bằng `META-INF/spring.factories`.

Dùng hai loại event khác nhau để kết quả dễ phân biệt và không tạo log trùng. `ApplicationRunner` trong context in một dòng sau khi refresh, chứng minh listener sớm chạy trước bean runner.

### 7.1. Cấu trúc thư mục

~~~text
early-listeners-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/earlyevents/
    │   ├── EarlyListenersDemoApplication.java
    │   ├── BuilderStartingListener.java
    │   └── FactoriesEnvironmentListener.java
    └── resources/META-INF/spring.factories
~~~

### 7.2. Khai báo Gradle

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'early-listeners-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Spring Boot BOM cung cấp version cho các dependency thuộc hệ sinh thái Boot.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Điểm QA quan trọng: do sử dụng Gradle native BOM, dependency `spring-boot-starter` không có version riêng vẫn được phân giải hợp lệ. Nếu dự án đã dùng plugin `io.spring.dependency-management` hoặc một BOM đồng bộ khác, hãy giữ một cơ chế quản lý phiên bản nhất quán thay vì sao chép cấu hình trùng.

Yêu cầu môi trường: JDK 17 trở lên và Gradle tương thích với Spring Boot 3.3. Ví dụ không có phụ thuộc web, nên không khởi động Tomcat.

### 7.3. Điểm vào dùng `SpringApplicationBuilder`

Tệp `src/main/java/com/example/earlyevents/EarlyListenersDemoApplication.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyListenersDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        EarlyListenersDemoApplication.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .listeners(new BuilderStartingListener())
                    .run(args)) {
            System.out.println("MAIN contextActive=" + context.isActive());
        }
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("RUNNER");
    }
}
~~~

Giải thích:

1. Builder nhận lớp cấu hình chính có `@SpringBootApplication`.
2. `web(WebApplicationType.NONE)` chọn ứng dụng console không có HTTP server.
3. `bannerMode(Banner.Mode.OFF)` ẩn banner; không ảnh hưởng đến listener.
4. `listeners(new BuilderStartingListener())` đăng ký đối tượng trước khi `run(args)` bắt đầu.
5. `run(args)` trả về `ConfigurableApplicationContext` nếu khởi động thành công.
6. `ApplicationRunner` là bean của context, nên chỉ được chạy sau khi giai đoạn refresh đã hoàn thành.
7. `try-with-resources` đóng context khi thoát khối lệnh.

### 7.4. Listener đăng ký bằng builder

Tệp `src/main/java/com/example/earlyevents/BuilderStartingListener.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class BuilderStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("BUILDER ApplicationStartingEvent");
    }
}
~~~

Lớp này không có `@Component` và không cần được tạo làm bean. Builder tạo instance bằng `new` và đưa nó vào danh sách listener trước khi Spring Boot phát sự kiện sớm.

Ở mốc `ApplicationStartingEvent`, **không sử dụng `@Autowired` hoặc cố lấy `ApplicationContext`**: context chưa tồn tại.

### 7.5. Listener tự tải từ `spring.factories`

Tệp `src/main/java/com/example/earlyevents/FactoriesEnvironmentListener.java`:

~~~java
package com.example.earlyevents;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class FactoriesEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    public FactoriesEnvironmentListener() {
        // Không cần bean injection: listener được tạo rất sớm.
    }

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String tag = event.getEnvironment()
                .getProperty("demo.tag", "unset");
        System.out.println(
                "FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=" + tag);
    }
}
~~~

Tệp `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=com.example.earlyevents.FactoriesEnvironmentListener
~~~

**Tên package và class phải khớp chính xác.** Tệp resource phải nằm trong `src/main/resources/META-INF/`, không đặt tại `src/main/java/` và không nhầm với `application.properties`. Gradle đưa resource này lên runtime classpath của ứng dụng theo quy tắc build Java thông thường.

`demo.tag` được lấy từ `Environment` của event. Chúng ta sẽ truyền bằng đối số ứng dụng để nó đã có ở giai đoạn chuẩn bị môi trường. `ApplicationEnvironmentPreparedEvent` được phát trước khi có context, nên cách dùng `event.getEnvironment()` phù hợp hơn cố lấy một bean `Environment` đã inject từ container.

### 7.6. Chạy và đối chiếu kết quả

Trong thư mục dự án có Gradle Wrapper tương thích:

~~~bash
./gradlew bootRun --args="--demo.tag=hello"
~~~

Trên PowerShell Windows:

~~~powershell
.\gradlew.bat bootRun --args="--demo.tag=hello"
~~~

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp:

~~~bash
gradle bootRun --args="--demo.tag=hello"
~~~

Trong một lần chạy thành công, **các dòng do mã của ví dụ in ra** xuất hiện theo thứ tự:

~~~text
BUILDER ApplicationStartingEvent
FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=hello
RUNNER
MAIN contextActive=true
~~~

Đây là tập con các dòng `System.out.println` của demo, **không phải toàn bộ stdout**. Logger Spring Boot và thông báo Gradle có thể in thêm các dòng tùy cấu hình. Điều quan trọng là thứ tự tương đối của bốn dòng trên:

- **BUILDER** xuất hiện đầu tiên do `ApplicationStartingEvent` là event rất sớm.
- **FACTORIES** xuất hiện sau khi `Environment` đã chuẩn bị, chứng minh listener được nạp từ resource và đọc được đối số `--demo.tag=hello`.
- **RUNNER** xuất hiện sau refresh vì đây là bean `ApplicationRunner`.
- **MAIN** xuất hiện sau khi `run(args)` trả về context đang hoạt động.

Nếu chạy không truyền `--demo.tag=hello`, dòng FACTORIES có thể ghi `demo.tag=unset` khi không có nguồn cấu hình khác cung cấp `demo.tag`. Phần còn lại của chuỗi giữ nguyên ý nghĩa.

### 7.7. Ba thử nghiệm kiểm chứng tính độc lập

**Thử A — Không đăng ký builder listener:** xóa riêng dòng `.listeners(new BuilderStartingListener())` trong điểm vào rồi chạy lại. Dòng **BUILDER** sẽ biến mất, còn dòng **FACTORIES** vẫn xuất hiện vì resource `spring.factories` còn nằm trên classpath.

**Thử B — Không đăng ký qua `spring.factories`:** khôi phục builder listener, rồi tạm thời bỏ khai báo `org.springframework.context.ApplicationListener=...` trong resource. Dòng **FACTORIES** không xuất hiện nữa, nhưng dòng **BUILDER** vẫn có. Cần rebuild/chạy lại với resource đã thay đổi để kiểm tra.

**Thử C — Dùng `SpringApplication.run(...)` thông thường:** thay `main` bằng:

~~~java
public static void main(String[] args) {
    try (org.springframework.context.ConfigurableApplicationContext context =
            org.springframework.boot.SpringApplication.run(
                    EarlyListenersDemoApplication.class, args)) {
        System.out.println("MAIN contextActive=" + context.isActive());
    }
}
~~~

Đây là **biến thể thay thế toàn bộ `main`, không chạy song song với builder**. Khi `spring.factories` vẫn còn, listener FACTORIES tiếp tục được tải tự động; listener BUILDER không được đăng ký, vì entrypoint mới không gọi `listeners(...)`. Sẽ có các log/banner mặc định khác, nhưng nguyên tắc đăng ký không đổi.

Sau mỗi thử nghiệm, khôi phục phiên bản gốc nếu muốn tiếp tục kiểm tra đầy đủ cả hai cơ chế.

## 8. Tải listener từ classpath hoạt động ra sao?

Ở mức ý tưởng, một lần bootstrap Spring Boot có chuỗi:

~~~text
Runtime classpath:
    app classes + resources + dependent JARs
        |
        v
Spring Boot / SpringFactoriesLoader
    Tìm META-INF/spring.factories từ các classpath entries
        |
        v
Đọc key org.springframework.context.ApplicationListener
    Lấy các tên lớp triển khai
        |
        v
Tạo và đăng ký listener thích hợp trong bootstrap
        |
        +----------------------+
        |                      |
        v                      v
ApplicationStartingEvent    ApplicationEnvironmentPreparedEvent
        |                      |
        v                      v
Gọi listener phù hợp        Gọi listener phù hợp
        |
        v
Tiếp tục các bước tạo và refresh ApplicationContext
~~~

Sơ đồ này giải thích **vì sao không cần tạo bean** cho listener nằm trong `spring.factories`. Đây không phải mô hình nói rằng Spring sẽ cố gọi **mọi** listener trên **mọi** event: generic type/event filtering vẫn áp dụng.

Một ứng dụng có thể phụ thuộc vào nhiều JAR, mỗi JAR có `META-INF/spring.factories` riêng. Cơ chế factories có thể đọc những resource phù hợp trên classpath; không phải chỉ có một tệp duy nhất trong cả tiến trình. Khi đóng gói thư viện, kiểm tra resource thực sự được giữ lại sau build/shading; một quy trình đóng gói ghi đè/loại bỏ `spring.factories` sẽ khiến listener “biến mất”.

### Đăng ký listener thuộc thư viện

Trong thư viện `runtime-observer.jar`, có thể cung cấp:

~~~text
runtime-observer.jar
    ├── META-INF/spring.factories
    └── com/example/observer/StartupObserver.class
~~~

Nội dung:

~~~properties
org.springframework.context.ApplicationListener=com.example.observer.StartupObserver
~~~

Ứng dụng sử dụng thư viện chỉ cần thêm JAR vào runtime classpath. **Cần cẩn trọng tác động toàn cục theo classpath**: một module phụ thuộc vào thư viện ở nhiều dự án có thể vô tình kích hoạt listener ở các ứng dụng không dự định dùng. Vì thế nên thiết kế listener có thể vô hiệu hóa bằng cấu hình an toàn và không phụ thuộc cứng vào bean nghiệp vụ.

Đối với Spring Boot fat JAR, đường dẫn resource có thể được đóng gói bên dưới `BOOT-INF/classes/META-INF/spring.factories` (ứng dụng) hoặc bên trong JAR phụ thuộc ở `BOOT-INF/lib`. Đây là vị trí **đóng gói**, còn đường dẫn classpath logic để `SpringFactoriesLoader` tìm vẫn là `META-INF/spring.factories`.

## 9. Thứ tự nhiều listener và `@Order`

Nếu nhiều listener nghe **cùng một event**, cần cân nhắc thứ tự thực thi. Spring Framework hỗ trợ giao diện `Ordered` và annotation `@Order` để thể hiện độ ưu tiên:

~~~java
import org.springframework.core.Ordered;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class PriorityStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 100;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Priority listener");
    }
}
~~~

Đây là một lớp có thể biên dịch trong dự án Spring Boot; nó chỉ chạy nếu được đăng ký theo một trong các cơ chế đã học. Giá trị order **nhỏ hơn** thường được ưu tiên chạy sớm hơn khi cơ chế phát sự kiện có sắp xếp listener.

Nhưng không nên suy diễn các điều sau:

- Thứ tự các dòng trong `spring.factories` **không phải** hợp đồng để điều phối logic nghiệp vụ giữa các listener.
- Hai listener có cùng giá trị order không có một quan hệ thứ tự ổn định mà bạn nên phụ thuộc vào.
- `@Order` cho listener **không thay thế** việc kiểm soát thứ tự `ApplicationRunner` hoặc `SmartLifecycle`; đây là các cơ chế vòng đời khác.
- Listener nhận những event khác nhau có thứ tự theo **thời điểm event được phát**, không phải chỉ theo order của class.

Nếu listener A bắt buộc phải chuẩn bị dữ liệu cho B, đôi khi giải pháp đúng là đưa logic vào một thành phần chung rõ ràng hơn, thay vì dựa vào thứ tự ngầm giữa các listener.

## 10. Những event nào có thể truy cập những tài nguyên nào?

| Event | `Environment` | `ApplicationContext` | Bean ứng dụng |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Chưa sẵn sàng | Chưa tồn tại | Chưa có |
| `ApplicationEnvironmentPreparedEvent` | Có, qua event | Chưa tồn tại | Chưa có |
| `ApplicationContextInitializedEvent` | Có qua context/event | Đã tạo nhưng chưa nạp định nghĩa ứng dụng đầy đủ | Không được giả định đã có |
| `ApplicationPreparedEvent` | Có | Context đã chuẩn bị, chưa refresh | Không được giả định đã khởi tạo hết |
| `ApplicationStartedEvent` | Có | Đã refresh | Các singleton non-lazy thông thường đã tạo, nhưng lazy vẫn có thể chưa |
| `ApplicationReadyEvent` | Có | Đã refresh và qua runners | Bean vẫn có thể lazy hoặc thuộc scope tạo sau |

Điều này quyết định listener nên làm gì:

- **Rất sớm:** in một marker, ghi nhận thông tin độc lập với context, thiết lập một số thành phần bootstrap nếu có API hỗ trợ.
- **Environment prepared:** đọc/điều chỉnh các `PropertySource` theo nhu cầu và API tương ứng; tránh truy cập bean.
- **Context initialized/prepared:** dùng đúng API của context khi nó chưa refresh; không tạo/đọc bean tùy tiện.
- **Started/ready:** phù hợp hơn để quan sát bean và điều phối hành động theo trạng thái vòng đời, nhưng không nên chặn vô hạn trong listener.

Nếu một listener `ApplicationStartingEvent` cố lấy `event.getApplicationContext()` thì đó là lỗi khái niệm: **loại event này không cung cấp context**. Tương tự, `ApplicationEnvironmentPreparedEvent` cho phép đọc `getEnvironment()` nhưng **không** bảo đảm đối tượng `ApplicationContext` đã tồn tại.

## 11. Chọn listener bean, `@EventListener` hay đăng ký sớm?

Có ba tình huống thực tế:

### A. Chỉ cần phản ứng khi ứng dụng đã có context

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY");
    }
}
~~~

Đây là một bean Spring bình thường. Nó thích hợp vì `ApplicationReadyEvent` được phát sau khi context được tạo và refresh. Không cần dùng `spring.factories` chỉ để nghe event này.

### B. Bắt buộc quan sát event đầu tiên

Dùng builder hoặc `spring.factories` để đăng ký `ApplicationListener<ApplicationStartingEvent>` từ trước `run`. Không dùng `@Component` là cơ chế duy nhất và không gọi bean ứng dụng ở thời điểm này.

### C. Muốn tự động áp dụng cho các ứng dụng dùng một thư viện

Dùng resource `META-INF/spring.factories` khi cần gắn listener ở bootstrap mà không sửa entrypoint của từng ứng dụng. Đặc biệt thận trọng với code chạy trong mọi ứng dụng có thư viện trên classpath, và áp dụng điều kiện/cấu hình để hạn chế tác động ngoài ý muốn.

**Quy tắc lựa chọn:** cần event sớm + kiểm soát entrypoint → builder; cần event sớm + tự nạp từ classpath → `spring.factories`; chỉ nghe event sau khi context đã hoạt động → bean listener hoặc `@EventListener` thường đơn giản hơn.

## 12. Phân biệt `ApplicationListener` và `SpringApplicationRunListener`

Hai tên rất dễ nhầm nhưng **không cùng một giao diện**:

| Thành phần | Vai trò | Thông thường dùng khi |
| --- | --- | --- |
| `ApplicationListener<E>` | Nhận `ApplicationEvent` từ Spring event publishing | Phản ứng với startup event hoặc event trong context |
| `SpringApplicationRunListener` | Callback chuyên biệt để Spring Boot điều phối từng giai đoạn của một lần `SpringApplication.run` | Tích hợp hạ tầng cấp thấp vào bootstrap Spring Boot |

Trong bài này, key chính xác là:

~~~properties
org.springframework.context.ApplicationListener=com.example.runtime.EarlyStartupListener
~~~

**Không** thay bằng:

~~~properties
org.springframework.boot.SpringApplicationRunListener=com.example.runtime.EarlyStartupListener
~~~

vì class `EarlyStartupListener` trong ví dụ **không triển khai `SpringApplicationRunListener`** và hợp đồng khởi tạo của `SpringApplicationRunListener` khác. Việc đăng ký sai key có thể khiến listener không được tìm thấy theo kiểu mong muốn hoặc gây lỗi tải.

Tương tự, đừng nhầm `SpringApplicationBuilder.listeners(...)` với `ApplicationContextInitializer`: initializer dùng để tùy chỉnh context trong giai đoạn chuẩn bị; listener phản ứng với sự kiện được phát. Một class có thể thực hiện nhiều vai trò, nhưng hợp đồng của chúng vẫn khác nhau.

## 13. Cần chú ý với context cha/con

`SpringApplicationBuilder` có `parent(...)` và `child(...)` để xây dựng context hierarchy. Khi một event được publish từ **context con**, cơ chế event của Spring có thể truyền sự kiện lên **context cha**, khiến listener đăng ký tại context cha nhận được thêm event của context con.

Do đó, nếu listener xử lý theo ngữ cảnh cụ thể, đừng mặc định “mỗi loại event chỉ được nhận đúng một lần trong toàn bộ ứng dụng có context hierarchy”.

Trong trường hợp event cung cấp context, có thể nhận diện context phát event và so sánh với context mà listener đang quản lý. Với listener được đăng ký ở bootstrap rất sớm, context còn chưa tồn tại, nên giải pháp lọc phải dựa vào thuộc tính thật sự được cung cấp tại mốc đó.

Ngoài context hierarchy, việc vô tình vừa khai báo cùng class trong `spring.factories` vừa tạo một instance khác qua `builder.listeners(...)` có thể khiến logic được gọi nhiều lần. Tránh dùng listener để thực hiện tác vụ **không idempotent** như gửi tiền, xóa dữ liệu hoặc commit giao dịch theo giả định “event chỉ chạy một lần”.

## 14. Những lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy `ApplicationStartingEvent` khi dùng `@Component` | Listener bean được tạo sau event | Chuyển sang `builder.listeners` hoặc `spring.factories` |
| Dùng builder nhưng không nhận event | Quên đăng ký trước `run` hoặc tạo builder khác để chạy | Kiểm tra đúng instance builder và vị trí `listeners(...)` |
| `spring.factories` không có hiệu lực | Sai path, tên key, tên class hoặc resource không nằm trên classpath | Kiểm tra `src/main/resources/META-INF/spring.factories`, package và file đóng gói |
| Tải listener báo lỗi constructor | Factory listener đòi dependency chỉ có trong container | Dùng constructor phù hợp ở giai đoạn bootstrap, bỏ phụ thuộc vào bean |
| Listener chạy hai lần | Cùng logic được đăng ký từ nhiều nguồn, hoặc context hierarchy | Kiểm tra cách đăng ký và context của event |
| `event.getEnvironment()` trả thuộc tính khác kỳ vọng | Nguồn cấu hình/độ ưu tiên khác, hoặc listener chạy trước một số bước bổ sung nguồn | Xem nguồn thuộc tính đã khả dụng tại **đúng mốc event**, ưu tiên kiểm thử với command-line argument |
| Listener `ApplicationStartedEvent` không in dù startup có log ban đầu | Refresh context thất bại trước sự kiện started | Xem root cause, event `ApplicationFailedEvent` và stack trace |
| Listener `ApplicationReadyEvent` không chạy | Runner thất bại hoặc bị chặn, hoặc listener chưa đăng ký | Kiểm tra runner và điểm đăng ký event |
| Listener làm startup chậm | Callback thực hiện I/O nặng hoặc chờ đồng bộ | Chuyển công việc vào runner/dịch vụ thích hợp, tránh chặn giai đoạn sớm |
| Chuyển listener sang `AutoConfiguration.imports` | Nhầm metadata auto-config với metadata ApplicationListener | Dùng key `org.springframework.context.ApplicationListener` trong `spring.factories` |
| `@Autowired` là null trong factory listener | Đối tượng không được tạo như bean của context | Không inject bean ứng dụng vào listener sớm; dùng event, API bootstrap hoặc cơ chế sau refresh |
| Sai thứ tự nhiều listener | Dựa vào thứ tự khai báo thay vì mức ưu tiên | Dùng `Ordered`/`@Order` và thiết kế độc lập thứ tự khi có thể |

### Cách kiểm tra nhanh resource trong JAR

Sau khi build JAR Spring Boot bằng:

~~~bash
./gradlew bootJar
~~~

có thể xem nội dung JAR bằng lệnh `jar` của JDK (thay tên JAR bằng tên thực tế do build tạo):

~~~bash
jar tf build/libs/early-listeners-demo-1.0.0.jar
~~~

Tìm mục `BOOT-INF/classes/META-INF/spring.factories` trong danh sách của executable JAR nếu đây là resource của chính ứng dụng. Nếu thư viện chứa `spring.factories`, nó có thể nằm bên trong một JAR ở `BOOT-INF/lib`. Sự hiện diện của resource giúp loại trừ lỗi đóng gói, nhưng **không tự bảo đảm class listener được khởi tạo thành công**; vẫn cần kiểm tra tên class, constructor và log.

## 15. Lưu ý vận hành và kiểm thử

Một listener được gọi sớm có ảnh hưởng lớn đến khả năng ứng dụng khởi động. Vì thế:

1. **Giữ listener sớm gọn và nhanh.** Spring Boot mặc định gọi listener trong thread khởi động cho nhiều mốc; xử lý chặn có thể trì hoãn toàn bộ `run`.
2. **Không giả định bean đã sẵn sàng.** Giai đoạn starting/environment trước context; hãy lấy thông tin từ event nếu có.
3. **Không ghi dữ liệu nhạy cảm từ `Environment` ra log.** Có thể chứa mật khẩu, token, chuỗi kết nối. Ví dụ `demo.tag` là một giá trị không nhạy cảm.
4. **Tránh side effect không idempotent.** Có thể có nhiều context, nhiều lần chạy test hoặc đăng ký lặp.
5. **Phân biệt lỗi listener với lỗi bean.** Exception trong callback có thể làm `SpringApplication.run` thất bại trước khi context refresh.
6. **Kiểm thử cả hai cách đăng ký.** Test classpath có resource `spring.factories` cần được đóng gói/khả dụng tương tự môi trường chạy; test builder cần dùng đúng entrypoint.
7. **Phân tách nhiệm vụ.** Nếu mục đích là chạy logic một lần sau khi container có bean, `ApplicationRunner` thường thích hợp hơn listener cực sớm.

### Một bài tập mở rộng

Hãy triển khai listener thứ ba nghe `ApplicationReadyEvent` bằng `@EventListener` trên một bean trong context. Chạy lại demo và quan sát:

~~~text
BUILDER ApplicationStartingEvent
FACTORIES ApplicationEnvironmentPreparedEvent demo.tag=hello
RUNNER
READY
MAIN contextActive=true
~~~

Dòng `READY` chỉ xuất hiện sau khi bean listener được định nghĩa thật và runner hoàn tất thành công. Bài tập này minh họa **hai cơ chế đăng ký sớm** và **một cơ chế đăng ký bean muộn** cùng tồn tại trong một ứng dụng.

## 16. Câu hỏi tự kiểm tra

1. **Có thể dùng riêng `@Component` để bắt `ApplicationStartingEvent` không?** Không trên luồng bootstrap thông thường, vì event xuất hiện trước khi context tạo bean.
2. **`SpringApplicationBuilder.listeners(...)` cần được gọi trước hay sau `run`?** Trước.
3. **Tham số của `listeners(...)` là tên lớp hay đối tượng listener?** Các đối tượng triển khai `ApplicationListener`.
4. **Tệp factories của ứng dụng đặt ở đâu?** `src/main/resources/META-INF/spring.factories`.
5. **Key cần dùng để tự đăng ký `ApplicationListener` là gì?** `org.springframework.context.ApplicationListener`.
6. **Một listener trong `spring.factories` có cần gắn `@Component` không?** Không; nó được tải bởi cơ chế bootstrap.
7. **Một factory listener có thể yêu cầu constructor injection của repository do context tạo không?** Không nên; context chưa sẵn sàng ở các event đầu tiên.
8. **Spring Boot 3.3 có còn dùng `spring.factories` cho `ApplicationListener` không?** Có.
9. **`AutoConfiguration.imports` có thay `spring.factories` cho mọi mục đích không?** Không; đây là metadata auto-configuration.
10. **Hai listener cùng nghe một event có thứ tự theo vị trí khai báo không?** Không nên phụ thuộc vào vị trí; dùng cơ chế order thích hợp.
11. **Một thư viện chứa `spring.factories` có ảnh hưởng đến ứng dụng dùng thư viện không?** Có thể, nếu resource và class của listener nằm trên classpath.
12. **Vì sao ví dụ in `RUNNER` sau `FACTORIES`?** Runner là bean chạy sau refresh, còn factory listener bắt event environment trước khi có context.
13. **Nếu dùng `SpringApplication.run(...)` thường mà giữ `spring.factories`, listener nào vẫn tự được nạp?** Listener đăng ký bằng `spring.factories`.
14. **Nếu thấy `ApplicationReadyEvent`, có thể kết luận listener starting sẽ chạy lại không?** Không. Event đã qua không tự phát lại; mỗi event có thời điểm riêng.
15. **Nếu cùng một listener được đăng ký cả builder và factories, có nên dựa vào việc nó chỉ nhận event một lần không?** Không; tránh đăng ký lặp logic và thiết kế callback chịu được lặp.

**Kết luận:** `SpringApplicationBuilder.listeners(...)` và `META-INF/spring.factories` đều đưa `ApplicationListener` vào tiến trình khởi động **trước khi context tạo bean**. Builder phù hợp khi muốn kiểm soát tường minh tại entrypoint; factories phù hợp khi muốn tự phát hiện từ classpath. Trong Spring Boot 3.3, `spring.factories` vẫn đúng cho listener, mặc dù danh sách auto-configuration đã sử dụng metadata riêng. Muốn chọn cách đăng ký đúng, hãy bắt đầu từ **event cần nghe** và **mốc mà event xuất hiện**, không chỉ từ cú pháp annotation.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — `SpringApplication`, phần **Fluent Builder API** và **Application Events and Listeners**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — API `SpringApplicationBuilder`, `listeners(ApplicationListener<?>...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot 3.3 — API `SpringApplication`, `addListeners(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — API `ApplicationListener`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.1 — `SpringFactoriesLoader`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html
- Spring Boot 3.3 — Managing Dependencies with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
