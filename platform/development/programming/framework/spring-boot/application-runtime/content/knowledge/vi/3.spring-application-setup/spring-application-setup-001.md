# Thiết lập SpringApplication trước run và giới hạn thay đổi khi ứng dụng đã khởi động

## 1. Vấn đề cần hiểu

`SpringApplication` là đối tượng điều phối quá trình khởi động Spring Boot. Một ứng dụng thường tạo đối tượng này, thiết lập lựa chọn bootstrap, rồi gọi `run(args)`:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.setDefaultProperties(Map.<String, Object>of("demo.mode", "training"));
application.run(args);
~~~

**Điểm mấu chốt:** Các phương thức `set...` của `SpringApplication` chủ yếu mô tả **cách một `ApplicationContext` sẽ được tạo và khởi động**. Sau khi `run` hoàn tất, context, nhiều singleton bean và các tài nguyên được khởi tạo đã có trạng thái của riêng chúng. Đổi một trường cấu hình trên đối tượng `SpringApplication` lúc này **không tự động cấu hình lại context đang hoạt động**.

Cần tách ba loại việc:

1. **Cấu hình bootstrap trước `run`:** Chọn loại ứng dụng, banner, chính sách tạo bean, default properties, profile, listeners và initializers.
2. **Cấu hình được Spring Boot nạp trong lúc khởi động:** `application.properties`/`application.yml`, biến môi trường, tham số dòng lệnh, `spring.main.*`, v.v. Chúng tham gia vào cơ chế thứ tự ưu tiên cấu hình; một số thiết lập cần có từ rất sớm.
3. **Trạng thái runtime sau khi `run`:** Các bean, kết nối, HTTP server và tác vụ có thể tiếp tục hoạt động. Một vài giá trị có thể thay đổi thông qua API runtime được thiết kế riêng, nhưng nhiều lựa chọn bootstrap muốn thay đổi phải **tạo context mới hoặc khởi động lại**.

Không nên nhầm “đối tượng `SpringApplication` vẫn tồn tại” với “đối tượng đó vẫn điều khiển được mọi thứ của context vừa khởi chạy”.

## 2. Mốc thời gian: vì sao phải cấu hình trước run?

Một tiến trình khởi động điển hình có các giai đoạn khái niệm:

~~~text
main(String[] args)
    |
    v
new SpringApplication(Main.class)
    |
    +-- setBannerMode(...)
    +-- setWebApplicationType(...)
    +-- setDefaultProperties(...)
    +-- setAdditionalProfiles(...)
    +-- addInitializers(...) / addListeners(...)
    |
    v
application.run(args)
    |
    +-- Chuẩn bị Environment và cấu hình ngoài
    +-- Tạo ApplicationContext phù hợp
    +-- Áp dụng ApplicationContextInitializer
    +-- Đăng ký cấu hình, quét bean, auto-configuration
    +-- refresh context; khởi tạo singleton cần thiết
    +-- Chạy ApplicationRunner / CommandLineRunner
    +-- Phát tín hiệu ứng dụng sẵn sàng
    |
    v
run(...) trả về ConfigurableApplicationContext
    |
    v
Ứng dụng tiếp tục phục vụ request / xử lý công việc
~~~

Đây là **mô hình học tập**, không phải danh sách đầy đủ mọi callback nội bộ. Một vài sự kiện như `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` xảy ra rất sớm, trước khi một context thông thường có thể xử lý chúng. `ApplicationStartedEvent` xảy ra sau khi context được refresh nhưng trước runners; `ApplicationReadyEvent` sau runners.

Một lựa chọn được sử dụng trong bước khởi động có thể không còn “điểm áp dụng” sau đó:

- **Loại ứng dụng:** `setWebApplicationType(WebApplicationType.NONE)` giúp chọn kiểu context non-web trước khi tạo context. Đổi `webApplicationType` ở `SpringApplication` sau `run` không biến context hiện tại thành web/non-web context khác.
- **Khởi tạo bean:** `setLazyInitialization(true)` tác động đến cách Spring xử lý bean khi tạo context. Đổi tùy chọn sau khi các singleton đã được tạo không thể hoàn tác các lần khởi tạo đó.
- **Banner và startup log:** Banner được in trong lúc khởi động; `setBannerMode(Banner.Mode.OFF)` sau `run` không thể thu hồi banner đã in. `setLogStartupInfo(false)` chỉ liên quan thông tin startup do SpringApplication ghi, không vô hiệu hóa toàn bộ logger.
- **Profile:** `setAdditionalProfiles("demo")` được xét khi chuẩn bị môi trường và nạp cấu hình. Bổ sung profile vào `SpringApplication` sau khi context đã refresh không tự động tạo thêm bean `@Profile("demo")` hay nạp lại cấu hình có điều kiện.
- **Listener/initializer:** Nếu cần quan sát các sự kiện khởi động sớm, hãy đăng ký listener **trước** `run`. `ApplicationContextInitializer` chỉ được gọi trong quá trình chuẩn bị context, không phải một lệnh “khởi tạo lại” để gọi bất kỳ lúc nào.

## 3. Những thiết lập phổ biến trước run

| API trên SpringApplication | Ý nghĩa | Điều cần cân nhắc |
| --- | --- | --- |
| `setWebApplicationType(WebApplicationType.NONE)` | Chọn ứng dụng không chạy embedded web server. | Dùng cho CLI, tác vụ nền, batch; API HTTP cần kiểu web tương ứng. |
| `setBannerMode(Banner.Mode.OFF)` | Không in banner mặc định khi startup. | Không tắt toàn bộ log hay exceptions. |
| `setLogStartupInfo(false)` | Giảm thông tin startup do SpringApplication ghi. | Các logger khác vẫn có thể in log. |
| `setDefaultProperties(Map...)` | Tạo giá trị dự phòng trong `Environment`. | Mức ưu tiên thấp; cấu hình ngoài/đối số có thể ghi đè. |
| `setAdditionalProfiles("dev")` | Thêm profile vào các profile được cấu hình sẵn. | Có thể thay đổi những file cấu hình/bean được chọn khi khởi động. |
| `setAddCommandLineProperties(false)` | Không ánh xạ các đối số `--key=value` thành property trong `Environment`. | Không đồng nghĩa với xóa `args` đầu vào của runner. |
| `setLazyInitialization(true)` | Bật chế độ khởi tạo trễ cho nhiều bean. | Có thể trì hoãn việc phát hiện lỗi cho đến lần sử dụng đầu tiên. |
| `setAllowBeanDefinitionOverriding(true)` | Cho phép khai báo bean definition cùng tên ghi đè nhau. | Nên giải quyết xung đột bean rõ ràng; không tùy tiện bật để che lỗi. |
| `addInitializers(...)` | Chạy logic trên context ở giai đoạn chuẩn bị. | Không được dùng để sửa bean đã sử dụng lúc runtime. |
| `addListeners(...)` | Đăng ký `ApplicationListener` cho sự kiện lifecycle. | Listener cho sự kiện sớm phải đăng ký sớm; tránh chạy tác vụ nặng trong callback. |

Đối với ứng dụng thông thường, có thể dùng `SpringApplication.run(Main.class, args)` mà không cần tạo đối tượng tùy biến. Một lớp cấu hình có `@SpringBootApplication` không tự bắt buộc phải gọi nhiều setter.

**Không mặc định setter “thắng” mọi nguồn khác:** Spring Boot còn đọc các property như `spring.main.*` từ `Environment` và bind chúng vào cấu hình khởi động. Cách thiết lập hiệu lực phụ thuộc **thời điểm** và **nguồn giá trị**. Nếu có cấu hình trùng trong file, environment variables hoặc đối số, phải kiểm tra thứ tự ưu tiên và giá trị thực tế thay vì giả định lời gọi setter luôn cao nhất.

### Giá trị mặc định khác giá trị bắt buộc

~~~java
application.setDefaultProperties(
        Map.<String, Object>of("demo.mode", "default-value"));
~~~

Ví dụ `demo.mode` có thể bị ghi đè bằng:

~~~bash
gradle bootRun --args="--demo.mode=from-cli"
~~~

`setDefaultProperties` hữu ích khi muốn ứng dụng có mặc định hợp lý nhưng vẫn cho phép môi trường triển khai thay đổi giá trị. Khi muốn cố định một quy tắc nghiệp vụ quan trọng, cần kiểm tra và xác thực riêng thay vì dựa vào việc đặt default property.

## 4. Thực hành: chứng minh ranh giới trước và sau run

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.3.13** và Gradle. Đây là ứng dụng console (non-web) đầy đủ. Nó minh họa đồng thời:

1. Một property mặc định được thiết lập **trước** `run`.
2. Đổi `SpringApplication.setDefaultProperties(...)` **sau** `run` không cấu hình lại `Environment` đã gắn vào context.
3. Chủ động thêm một `PropertySource` mới có thể làm kết quả đọc `Environment` lúc runtime thay đổi.
4. Một bean đã lưu giá trị cũ không tự nhận giá trị mới từ `Environment`. Muốn thay đổi trạng thái của bean, ứng dụng phải thực hiện thao tác riêng.

### Cấu trúc dự án

~~~text
spring-runtime-boundary/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── boundary/
                        └── BootstrapBoundaryApplication.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'spring-runtime-boundary'
~~~

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.boundary.BootstrapBoundaryApplication'
}
~~~

**Tệp `src/main/java/com/example/boundary/BootstrapBoundaryApplication.java`:**

~~~java
package com.example.boundary;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class BootstrapBoundaryApplication {

    public static void main(String[] args) {
        // 1. Cấu hình SpringApplication TRƯỚC run.
        SpringApplication application =
                new SpringApplication(BootstrapBoundaryApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(
                Map.<String, Object>of("demo.mode", "bootstrap-default"));
        application.setAdditionalProfiles("training");

        // 2. run tạo context, nạp cấu hình và khởi tạo bean.
        try (ConfigurableApplicationContext context = application.run(args)) {
            ConfigurableEnvironment environment = context.getEnvironment();
            RuntimeSwitch runtimeSwitch = context.getBean(RuntimeSwitch.class);

            System.out.println("env.start=" +
                    environment.getProperty("demo.mode"));
            System.out.println("bean.start=" + runtimeSwitch.mode());

            // 3. Setter của SpringApplication không cập nhật context cũ.
            application.setDefaultProperties(
                    Map.<String, Object>of("demo.mode", "late-default"));
            application.setBannerMode(Banner.Mode.CONSOLE);
            System.out.println("env.after-setter=" +
                    environment.getProperty("demo.mode"));

            // 4. Đây là thay đổi trực tiếp Environment (để THÍ NGHIỆM).
            environment.getPropertySources().addFirst(
                    new MapPropertySource(
                            "manualRuntimeOverride",
                            Map.<String, Object>of(
                                    "demo.mode", "runtime-source")));

            System.out.println("env.after-source=" +
                    environment.getProperty("demo.mode"));
            System.out.println("bean.after-source=" + runtimeSwitch.mode());

            // 5. Thay đổi trạng thái bean thông qua API đã thiết kế.
            runtimeSwitch.changeMode("manual-update");
            System.out.println("bean.after-update=" + runtimeSwitch.mode());
        }
    }

    @Bean
    RuntimeSwitch runtimeSwitch(ConfigurableEnvironment environment) {
        // Bean này lấy giá trị tại thời điểm được tạo.
        return new RuntimeSwitch(
                environment.getProperty("demo.mode", "fallback"));
    }

    public static final class RuntimeSwitch {
        private final AtomicReference<String> currentMode;

        public RuntimeSwitch(String initialMode) {
            this.currentMode = new AtomicReference<>(initialMode);
        }

        public String mode() {
            return currentMode.get();
        }

        public void changeMode(String newMode) {
            currentMode.set(newMode);
        }
    }
}
~~~

**Giải thích vì sao chương trình hoạt động như vậy:**

- `SpringApplication` được tạo bằng chính lớp `BootstrapBoundaryApplication.class`, dùng làm nguồn cấu hình Spring Boot.
- `WebApplicationType.NONE` cho ví dụ console không mở cổng HTTP. `Banner.Mode.OFF` và `setLogStartupInfo(false)` giúp dễ đọc các dòng thí nghiệm, nhưng không cam kết im lặng tất cả logger.
- `@Bean` tạo một `RuntimeSwitch` với giá trị `demo.mode` **lúc bean được xây dựng**. `AtomicReference` là một cơ chế Java an toàn cho thao tác đọc/đặt lại *một giá trị tham chiếu* từ nhiều luồng; ví dụ không cố giải quyết mọi tình huống thay đổi cấu hình phức tạp.
- Sau `application.run(args)`, việc gọi `application.setDefaultProperties(...)` chỉ thay đổi cấu hình được lưu trên đối tượng bootstrap; `Environment` của context đang chạy vẫn giữ các property source đã chuẩn bị trước đó.
- `environment.getPropertySources().addFirst(...)` là thao tác **trực tiếp lên `Environment` đang chạy**. Nó làm giá trị đọc mới của `demo.mode` thay đổi vì property source mới đứng đầu danh sách. **Nó không tái tạo bean**, nên `RuntimeSwitch` vẫn giữ giá trị đã nhận khi khởi tạo.
- `runtimeSwitch.changeMode(...)` thay đổi chính trạng thái bean. Các thành phần gọi `mode()` sau đó mới thấy trạng thái mới; nó không đồng nghĩa với thay đổi cấu hình global của Spring Boot.
- `try (ConfigurableApplicationContext context = ...)` đóng context khi thí nghiệm kết thúc. Chỉ làm vậy với chương trình ngắn hạn; ứng dụng web phải giữ context hoạt động trong thời gian phục vụ request.

### Cách chạy và đối chiếu

Trong thư mục chứa `build.gradle`, với Gradle tương thích đã cài:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper trong dự án, có thể chạy `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows.

Khi **không có** nguồn cấu hình khác đặt `demo.mode`, những dòng do mã Java tự in ra có nội dung đúng như sau (các dòng log framework có thể thêm vào):

~~~text
env.start=bootstrap-default
bean.start=bootstrap-default
env.after-setter=bootstrap-default
env.after-source=runtime-source
bean.after-source=bootstrap-default
bean.after-update=manual-update
~~~

Đối chiếu:

| Mốc | `Environment` | `RuntimeSwitch` | Vì sao? |
| --- | --- | --- | --- |
| Sau `run` | `bootstrap-default` | `bootstrap-default` | Cả hai nhận giá trị đã có khi khởi động. |
| Sau `application.setDefaultProperties` | Vẫn `bootstrap-default` | Vẫn `bootstrap-default` | Setter trễ không thay property source đã gắn vào context. |
| Sau `addFirst(new MapPropertySource(...))` | `runtime-source` | Vẫn `bootstrap-default` | Lookup mới thấy nguồn ưu tiên cao; bean không tự bind lại. |
| Sau `runtimeSwitch.changeMode(...)` | `runtime-source` | `manual-update` | API nghiệp vụ cập nhật trạng thái bean riêng. |

Chạy thử với một tham số dòng lệnh:

~~~bash
gradle bootRun --args="--demo.mode=from-cli"
~~~

Với nguồn property đầu vào khác giữ nguyên, **ba dòng đầu** sẽ là:

~~~text
env.start=from-cli
bean.start=from-cli
env.after-setter=from-cli
~~~

Sau đó lệnh `addFirst(...)` trong chương trình vẫn ưu tiên nguồn `manualRuntimeOverride` cho lookup `Environment`, còn bean giữ giá trị `from-cli` cho đến khi được gọi `changeMode(...)`.

**Giới hạn của thí nghiệm:** Việc tự chèn `MapPropertySource` sau khi đã khởi động chỉ nhằm minh họa ranh giới giữa property lookup và bean state. Nó không phải khuyến nghị cập nhật cấu hình toàn hệ thống trong production; các bean tiêu thụ cấu hình có thể có vòng đời, cache và yêu cầu đồng bộ khác nhau.

## 5. Những gì có thể và không thể thay đổi sau khi khởi động

Khái niệm “ứng dụng đã khởi động” nên hiểu là context đã refresh, bean phụ thuộc đã được tạo và `run` đã hoàn tất. Sau đó:

| Nhu cầu | Cách xử lý phù hợp | Có tự xảy ra khi gọi setter SpringApplication trễ? |
| --- | --- | --- |
| Đổi banner đã in hoặc các dòng startup log quá khứ | Thay cấu hình trước lần startup tiếp theo. | **Không** |
| Chuyển context non-web thành web và mở embedded server | Khởi động context với kiểu web và dependencies tương thích. | **Không** |
| Thay profile để đăng ký bean `@Profile` mới | Khởi động lại hoặc dùng cơ chế quản lý context/bean được thiết kế rõ ràng. | **Không** |
| Thay default property để bean đã tạo nhận giá trị mới | Dùng cơ chế reload/rebind có chủ đích hoặc khởi động lại; tùy loại bean. | **Không** |
| Điều chỉnh giá trị logic nghiệp vụ còn sống | Gọi API của bean được thiết kế cho thay đổi runtime; bảo đảm kiểm soát đồng thời. | **Không, cần thao tác nghiệp vụ** |
| Đọc một property mới được chèn vào `ConfigurableEnvironment` | Thao tác trực tiếp property sources có thể làm lookup sau đó thấy giá trị mới. | **Không, setter trễ khác với sửa Environment** |
| Dừng ứng dụng và giải phóng tài nguyên | Dùng lifecycle thích hợp, ví dụ đóng context có chủ đích hoặc quy trình shutdown. | **Không liên quan đến setter bootstrap** |

**Phân biệt ba mức “giá trị mới”**:

1. **`Environment.getProperty(...)`** thường đọc các `PropertySource` tại thời điểm được gọi. Nếu nguồn thực sự đổi và nguồn đó có ưu tiên phù hợp, lần đọc mới có thể khác lần trước.
2. **`@Value`, `@ConfigurationProperties` và constructor injection** thường cấp giá trị cho bean khi được tạo hoặc bind. Thay nguồn property không đồng nghĩa với tự động gán lại field của mọi bean đã chạy.
3. **Hạ tầng đã khởi tạo** như embedded server, pool kết nối, executor, scheduler còn có resource/lifecycle riêng. Việc đổi property string không tự thay đổi cổng nghe, kết nối đang mở hoặc thread đang chạy.

Một số hệ sinh thái có giải pháp refresh động, chẳng hạn Spring Cloud Context với những tính năng và điều kiện tương ứng. Không nên suy ra rằng **Spring Boot thuần** sẽ tự reload mọi bean mỗi khi sửa một tệp YAML hoặc property source. Nếu kiến trúc có hỗ trợ refresh, cần xác nhận chính xác bean nào refresh được, trạng thái nào bị thay thế và cách kiểm tra nhất quán.

## 6. Vị trí của file cấu hình và các giới hạn thời điểm

Không phải tất cả cấu hình đều được đọc ở cùng một thời điểm.

- **Cấu hình rất sớm:** Các khóa như `spring.config.name`, `spring.config.location` và `spring.config.additional-location` quyết định Spring Boot tìm file ở đâu. Chúng phải có từ nguồn `Environment` phù hợp khi quy trình nạp config data chạy (ví dụ biến môi trường, JVM system property hoặc command-line argument).
- **Cấu hình runtime bootstrap:** `spring.main.*` liên quan đến khởi tạo `SpringApplication`/context. Không thể trông đợi `@PropertySource` trên một lớp `@Configuration` có mặt đủ sớm cho mọi lựa chọn, vì nguồn này chỉ được thêm khi context đang refresh.
- **Cấu hình bean:** Một property gán cho `@ConfigurationProperties` thường được bind khi bean được dựng. Nội dung file thay đổi trên ổ đĩa sau đó không tự làm bean bind lại.
- **Đối số dòng lệnh:** Với mặc định `setAddCommandLineProperties(true)`, đối số dạng `--demo.mode=value` được Spring Boot đưa vào `Environment` và có thể ghi đè default properties. Nếu gọi `setAddCommandLineProperties(false)` trước `run`, đối số vẫn tồn tại trong `String[] args` và `ApplicationArguments`, nhưng không được bổ sung như command-line property source theo cách mặc định.

Đặc biệt, **chỉnh `application.yml` rồi mong cấu hình tự có hiệu lực** là một nhầm lẫn phổ biến. Trong ứng dụng không có cơ chế refresh, hãy triển khai lại/khởi động lại có kiểm soát, hoặc xây một giao diện quản trị runtime riêng cho đúng tham số có thể điều chỉnh an toàn.

## 7. Chọn điểm mở rộng phù hợp

Có ba lựa chọn hay bị nhầm lẫn:

### 7.1. Setter và initializer trước run

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("local");
app.addInitializers(context -> {
    // Thao tác với context ở giai đoạn chuẩn bị.
    // Không giả định bean đã được tạo đầy đủ ở đây.
});
app.run(args);
~~~

Đây là **minh họa một phần**, không phải chương trình chạy độc lập. Initializer thích hợp với chuẩn bị context, không thích hợp với thao tác trên bean vốn cần sau refresh. Với listener cho sự kiện bắt đầu rất sớm, phải đăng ký qua cách thức đủ sớm (`addListeners` hoặc cơ chế đăng ký tương ứng).

### 7.2. Chạy sau khi bean đã sẵn sàng

~~~java
@Bean
ApplicationRunner initializeBusinessData(MyService service) {
    return arguments -> service.initialize();
}
~~~

Đây cũng là **đoạn minh họa**, giả sử dự án đã có `MyService` và import `ApplicationRunner`/`Bean`. `ApplicationRunner` và `CommandLineRunner` được Spring Boot gọi như một phần của `run` sau khi context refresh. Chúng phù hợp để kiểm tra dữ liệu, thực hiện khởi tạo logic nghiệp vụ, nhưng **quá muộn** để thay đổi loại `ApplicationContext` được chọn.

### 7.3. Thay đổi trong lúc ứng dụng đang chạy

Nếu yêu cầu có tính chất “đổi ngưỡng cảnh báo mà không restart”, hãy thiết kế một bean chứa cấu hình runtime được xác thực và cập nhật qua phương thức chuyên dụng. Cần tính đến quyền gọi, validation, concurrency, trạng thái đang xử lý và việc ghi nhận thay đổi. Ví dụ `AtomicReference` ở mục 4 chỉ mô phỏng giá trị đơn; đối với nhiều property liên quan, nên cập nhật **một cấu hình bất biến tổng thể** theo cách nguyên tử, thay vì đổi từng field rời rạc dẫn đến trạng thái nửa cũ nửa mới.

## 8. Lỗi thường gặp

**Lỗi 1 — Gọi setter sau run rồi chờ context tự đổi**

~~~java
ConfigurableApplicationContext context = app.run(args);
app.setWebApplicationType(WebApplicationType.NONE); // Không chuyển context cũ.
~~~

Muốn chọn non-web, đặt `setWebApplicationType` **trước** `run`. Đối với kiểu context đã được tạo, không có thao tác đổi loại tại chỗ bằng setter này.

**Lỗi 2 — Chạy run lần nữa để “apply lại cấu hình”**

~~~java
app.run(args);
app.run(args);
~~~

Mỗi lần `run` là một lần khởi động một context mới, không phải thao tác refresh context cũ. Có thể dẫn tới bean/runner được chạy hai lần, tranh chấp cổng, tài nguyên hoặc trạng thái dùng chung. Nếu có chủ đích quản lý nhiều context thì cần thiết kế vòng đời rõ ràng; không dùng hai lời gọi `run` như mẹo reload.

**Lỗi 3 — Cho rằng mọi property đều cập nhật động**

~~~java
// Sửa file application.properties trên đĩa khi JVM đang chạy
// không bảo đảm @Value/@ConfigurationProperties đã khởi tạo đổi theo.
~~~

Đây là lời chú thích, không phải lệnh làm thay đổi cấu hình. Cần biết rõ cơ chế nạp lại nào đã được thiết lập trước khi khẳng định một property thay đổi động.

**Lỗi 4 — Dùng @PropertySource cho cấu hình quá sớm**

~~~java
@PropertySource("classpath:my-startup.properties")
@Configuration
class ExtraConfig {
}
~~~

Đoạn trên chỉ minh họa và cần import tương ứng. `@PropertySource` bổ sung nguồn khi refresh context nên có thể quá muộn với các cài đặt như `logging.*` và `spring.main.*`. Dùng nguồn startup mà Spring Boot đọc đúng giai đoạn chuẩn bị môi trường.

**Lỗi 5 — Đóng context ngay sau run trong ứng dụng web**

~~~java
try (ConfigurableApplicationContext context = app.run(args)) {
    // ...
} // Context bị đóng tại đây.
~~~

Cấu trúc này phù hợp cho CLI/thí nghiệm ngắn hạn như mục 4; đối với REST API/consumer chạy dài hạn, việc đóng context khiến ứng dụng ngừng phục vụ.

**Lỗi 6 — Đổi bean trực tiếp nhưng không kiểm tra đồng thời**

Thay một field được nhiều thread truy cập mà không có đồng bộ có thể làm các request khác nhau thấy trạng thái thiếu nhất quán. Hãy chọn cơ chế cập nhật an toàn, validation và audit theo nhu cầu thực tế; đừng trông chờ setter của `SpringApplication` giải quyết concurrency cho bean.

## 9. Tự kiểm tra kiến thức

1. Vì sao `setBannerMode(OFF)` sau `run` không có tác dụng với banner của lần khởi động vừa qua?
2. Một ứng dụng non-web đã khởi động có thể thành web server chỉ bằng `setWebApplicationType(SERVLET)` sau `run` không? Giải thích liên quan đến lựa chọn `ApplicationContext`.
3. Trong ví dụ mục 4, vì sao `env.after-source` khác `bean.after-source`?
4. Hãy chạy cùng chương trình với và không có `--demo.mode=from-cli`. Xác định nguồn property nào đang thắng trước thao tác `addFirst`.
5. Nếu cần cho người vận hành điều chỉnh ngưỡng retry của một service đang chạy, bạn sẽ thiết kế API cập nhật và validation ra sao? Khi nào nên yêu cầu restart?
6. Nếu một `ApplicationListener` cần nhận `ApplicationStartingEvent`, nó phải được đăng ký vào thời điểm nào? Vì sao bean chỉ được tìm thấy sau refresh thường không phù hợp cho event rất sớm?

## Ghi nhớ

**Đặt cấu hình quyết định quá trình tạo context lên `SpringApplication` trước `run(args)`.** Khi `run` đã tạo và refresh context, thay đổi setter trên đối tượng bootstrap không tự làm lại vòng đời vừa xảy ra. `Environment` có thể hỗ trợ tra cứu property động trong một số tình huống, nhưng bean đã bind và hạ tầng đã dựng cần cơ chế cập nhật riêng hoặc khởi động lại.

### Tài liệu tham khảo

- Spring Boot 3.3 — `SpringApplication` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners
