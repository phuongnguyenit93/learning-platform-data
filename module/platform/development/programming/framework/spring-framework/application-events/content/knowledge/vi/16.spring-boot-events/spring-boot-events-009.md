# Event trước khi ApplicationContext tồn tại trong Spring Boot

Spring Boot phát một số **application event ngay từ giai đoạn bootstrap**, trước cả khi tạo `ApplicationContext`. Hai sự kiện cần nhận biết rõ nhất là `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`. Chúng giúp ứng dụng hoặc thư viện can thiệp rất sớm vào vòng đời khởi động, chẳng hạn ghi dấu quá trình bootstrap hoặc bổ sung cấu hình môi trường trước khi tạo context.

Điểm quan trọng: **listener được khai báo bằng `@Component`, `@Bean` hoặc method `@EventListener` chỉ được Spring quản lý sau khi quá trình tạo context diễn ra**. Chúng không phải cơ chế phù hợp để nhận những event đã phát trước khi context tồn tại. Muốn nhận event sớm, phải đăng ký listener với `SpringApplication` trước khi gọi `run()` hoặc cho Spring Boot tải listener qua `META-INF/spring.factories`.

Bài này giải thích thứ tự các mốc khởi động, những dữ liệu có thể dùng ở từng mốc, cách cài đặt listener sớm trong Java 17+, cách kiểm thử thật bằng JUnit 5 và các sai lầm về lifecycle.

## 1. “Trước khi ApplicationContext tồn tại” có nghĩa chính xác là gì?

`SpringApplication.run(...)` không lập tức trả về một context đã khởi tạo. Nó thực hiện nhiều bước theo thứ tự: chuẩn bị listener và initializer, phát event bắt đầu, tạo và chuẩn bị `Environment`, tạo context, load bean definitions, refresh context, rồi chạy các `ApplicationRunner`/`CommandLineRunner`.

Tại một số bước đầu, Spring Boot đã có **cơ chế phát startup events**, nhưng chưa có **container quản lý bean** hoàn chỉnh:

~~~text
SpringApplication.run()
   |
   +-- Đăng ký listener và initializer với SpringApplication
   |
   +-- ApplicationStartingEvent                 [chưa có Environment; chưa có Context]
   |
   +-- Chuẩn bị Environment
   +-- ApplicationEnvironmentPreparedEvent      [có Environment; chưa có Context]
   |
   +-- Tạo ApplicationContext
   +-- Gọi ApplicationContextInitializer
   +-- ApplicationContextInitializedEvent       [đã có Context; chưa load bean definitions]
   |
   +-- Load bean definitions
   +-- ApplicationPreparedEvent                 [có Context; chưa refresh]
   |
   +-- Refresh ApplicationContext
   +-- ApplicationStartedEvent                  [refresh xong; trước runner]
   |
   +-- Chạy ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent                    [đã qua runner; sẵn sàng phục vụ]
   |
   +-- ApplicationFailedEvent nếu khởi động thất bại tại một điểm thích hợp
~~~

Đây là sơ đồ khái niệm cho trình tự startup thông thường. Một số event khác như `ContextRefreshedEvent`, `WebServerInitializedEvent` và `AvailabilityChangeEvent` xuất hiện ở các giai đoạn tương ứng; chúng không làm thay đổi ranh giới **chưa có context** đang xét.

| Event | Mốc phát | `Environment` đã có? | `ApplicationContext` đã có? | Tác dụng phù hợp |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Rất sớm, sau khi listener/initializer được đăng ký | **Chưa** | **Chưa** | Ghi nhận điểm bắt đầu, chuẩn bị công việc rất nhẹ không phụ thuộc DI |
| `ApplicationEnvironmentPreparedEvent` | Khi Environment đã được chuẩn bị, trước khi tạo context | **Có** | **Chưa** | Đọc hoặc bổ sung property sources, kiểm tra cấu hình bootstrap |
| `ApplicationContextInitializedEvent` | Context đã tạo và initializer đã chạy | Có | **Có, chưa có bean definitions** | Theo dõi việc khởi tạo context, không giả định bean sẵn sàng |
| `ApplicationPreparedEvent` | Bean definitions đã load, trước refresh | Có | **Có, chưa refresh** | Quan sát giai đoạn chuẩn bị |
| `ApplicationStartedEvent` | Sau refresh, trước runner | Có | **Có, đã refresh** | Công việc sau khi context bắt đầu nhưng trước runner |
| `ApplicationReadyEvent` | Sau các runner | Có | **Có** | Tác vụ chỉ nên chạy khi startup đã đi đến giai đoạn ready |

**Không được gộp `ApplicationContextInitializedEvent` với hai event đầu.** Khi `ApplicationContextInitializedEvent` được phát, đối tượng context **đã tồn tại** nhưng chưa được refresh và chưa có bean definitions được load ở mốc đó. Cụm “event trước khi context tồn tại” chỉ đúng về mặt thời gian với `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.

## 2. Vì sao @Component, @Bean và @EventListener không nhận được hai early event?

Một listener Spring Framework quen thuộc:

~~~java
@Component
class StartingBeanListener {
    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("started");
    }
}
~~~

Đây chỉ là **trích đoạn** minh họa điều không nên làm khi cần nhận `ApplicationStartingEvent`: method này chỉ được phát hiện sau khi quá trình dựng bean và xử lý annotation diễn ra, trong khi startup event đầu tiên đã được phát từ trước. Điều đó không có nghĩa phương thức không hợp lệ về cú pháp, mà là **nó đăng ký quá muộn cho event cụ thể này**.

Tương tự, định nghĩa một `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` không làm Spring Boot “phát lại” sự kiện môi trường đã xảy ra. Event startup không phải một hàng đợi replay lưu lịch sử để bean tạo sau nhận lại.

Cơ chế đúng là **đăng ký trước `SpringApplication.run()`** theo một trong ba cách:

1. `SpringApplication.addListeners(...)` khi chủ động xây dựng ứng dụng trong `main`.
2. `SpringApplicationBuilder.listeners(...)` khi khởi tạo bằng builder.
3. `META-INF/spring.factories` với khóa `org.springframework.context.ApplicationListener` để Boot tự nạp listener rất sớm, kể cả khi thư viện không kiểm soát `main`.

Listener sớm nên là một lớp Java độc lập, tự tạo được, thường **không dựa vào autowiring**. Nó có thể đọc event và những API thực sự đã sẵn sàng ở thời điểm đó, nhưng không được giả định repository, data source, `@ConfigurationProperties` bean, scheduler hay context đã tồn tại.

## 3. Ví dụ Java 17+: nhận ApplicationStartingEvent và ApplicationEnvironmentPreparedEvent

Ví dụ là một ứng dụng Spring Boot tối thiểu có hai listener được **đăng ký trước khi `run()`**. Listener đầu ghi dấu mốc bắt đầu; listener thứ hai bổ sung một property vào `Environment` trước khi context được tạo. Để dễ kiểm thử, cả hai nhận một `Consumer<String>` dùng làm nơi ghi sự kiện.

### 3.1. Cấu hình Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'early-boot-events'
~~~

`build.gradle` (Java 17, Spring Boot 3.5.x):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu đã có project Spring Boot được quản lý bởi BOM/plugin của tổ chức, hãy dùng phiên bản đồng bộ với project đó, không chèn thêm một phiên bản Spring Framework độc lập. Ví dụ chạy trên nhánh Spring Boot 3.5 có hỗ trợ Java 17+.

### 3.2. File src/main/java/example/boot/EarlyEventsApplication.java

~~~java
package example.boot;

import java.util.Map;
import java.util.function.Consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
            EarlyEventsApplication.class
        );
        app.addListeners(
            new StartingListener(System.out::println),
            new EnvironmentListener(System.out::println)
        );
        app.run(args);
    }

    public static final class StartingListener
            implements ApplicationListener<ApplicationStartingEvent> {

        private final Consumer<String> sink;

        public StartingListener(Consumer<String> sink) {
            this.sink = sink;
        }

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            sink.accept("starting");
        }
    }

    public static final class EnvironmentListener
            implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

        private final Consumer<String> sink;

        public EnvironmentListener(Consumer<String> sink) {
            this.sink = sink;
        }

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {
            event.getEnvironment()
                .getPropertySources()
                .addFirst(new MapPropertySource(
                    "early-demo",
                    Map.of("demo.phase", "bootstrap")
                ));

            sink.accept("environment-prepared");
        }
    }
}
~~~

**Điều cần quan sát:**

- `StartingListener` dùng `ApplicationStartingEvent`. Ở mốc đó, chưa thể gọi `event.getEnvironment()` vì event này không cung cấp API đó; càng không thể lấy bean từ context chưa được tạo.
- `EnvironmentListener` có thể gọi `event.getEnvironment()` vì event môi trường cung cấp `ConfigurableEnvironment`, dù chưa có `ApplicationContext`.
- `MapPropertySource` được thêm bằng `addFirst`, nên `demo.phase=bootstrap` có độ ưu tiên cao hơn nhiều nguồn khác. Đây là ví dụ minh họa cấu hình bootstrap; không nên dùng `addFirst` tùy tiện để ghi đè cấu hình bảo mật hoặc cấu hình người dùng.
- Hai listener là **đối tượng được tạo trong `main`**, không có `@Component`. Spring Boot biết đến chúng trước khi có context.

Trong project có Gradle wrapper, chạy ứng dụng bằng:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng `./gradlew.bat bootRun`. Trong stdout có thể thấy hai dòng do listener in ra theo thứ tự:

~~~text
starting
environment-prepared
~~~

Spring Boot cũng có thể in log startup, banner và thông điệp framework khác. Hai dòng trên là **phần output do hai listener tạo ra**, không phải cam kết toàn bộ stdout chỉ có hai dòng.

## 4. Kiểm thử event sớm bằng SpringApplication thật

Với các event trước khi context được tạo, không nên dùng một test chỉ gọi method listener bằng tay để kết luận Boot đã đăng ký listener đủ sớm. Cũng không nên cho rằng một `@SpringBootTest` bean tự động ghi lại được `ApplicationStartingEvent`: bean đó chỉ xuất hiện ở giai đoạn muộn hơn.

Hãy tạo `SpringApplication` thật, thêm listener vào application trước `run()`, rồi xác nhận sự kiện đến đúng thứ tự và property đã được gắn vào context về sau.

File `src/test/java/example/boot/EarlyEventsApplicationTest.java`:

~~~java
package example.boot;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

class EarlyEventsApplicationTest {

    @Test
    void earlyListenersRunBeforeApplicationContextIsReady() {
        List<String> observed = new ArrayList<>();

        SpringApplication app = new SpringApplication(
            EarlyEventsApplication.class
        );
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.addListeners(
            new EarlyEventsApplication.StartingListener(observed::add),
            new EarlyEventsApplication.EnvironmentListener(observed::add)
        );

        try (ConfigurableApplicationContext context = app.run()) {
            assertEquals(
                List.of("starting", "environment-prepared"),
                observed
            );
            assertEquals(
                "bootstrap",
                context.getEnvironment().getProperty("demo.phase")
            );
        }
    }
}
~~~

Chạy test:

~~~bash
./gradlew test --tests "example.boot.EarlyEventsApplicationTest"
~~~

Từ Windows PowerShell dùng `./gradlew.bat test --tests "example.boot.EarlyEventsApplicationTest"`.

**Vì sao test này đáng tin?**

1. `SpringApplication` nhận listener **trước** khi khởi động; test không tự gọi hai method `onApplicationEvent`.
2. Spring Boot chạy lifecycle thật. Nếu một listener không được đăng ký kịp thời, chuỗi `observed` thiếu phần tử và assertion sẽ fail.
3. Kết quả `demo.phase` được kiểm tra **sau khi `run()` trả về context**, chứng minh listener môi trường đã sửa đúng đối tượng `Environment` được dùng trong context.
4. `WebApplicationType.NONE` tránh mở web server, giúp test tập trung vào startup events. `try-with-resources` đóng context sau assertion.

Test không cần tạo repository hoặc service; việc kiểm thử hai early events chỉ đòi hỏi lifecycle của Boot và `Environment`. Nếu muốn kiểm tra thất bại khởi động hoặc bắt event ở module thư viện, tạo test riêng để kiểm tra `ApplicationFailedEvent` hoặc phương thức đăng ký tự động tương ứng.

## 5. Đăng ký listener tự động bằng META-INF/spring.factories

Khi xây thư viện starter hoặc tích hợp mà không kiểm soát `main`, cách gắn listener ở giai đoạn sớm là file:

`src/main/resources/META-INF/spring.factories`

~~~properties
org.springframework.context.ApplicationListener=example.boot.StartupTraceListener
~~~

Lớp listener phải có thể được Spring Boot tạo **trước khi context tồn tại**. Ví dụ độc lập (file `src/main/java/example/boot/StartupTraceListener.java`):

~~~java
package example.boot;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartupTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public StartupTraceListener() {
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("starter: beginning startup");
    }
}
~~~

Khi class này và `spring.factories` nằm trên runtime classpath, Boot có thể nạp listener thông qua factory discovery ngay đầu quá trình khởi động. Không bắt buộc chỉnh sửa `main`. Nếu đã đăng ký **cùng listener** bằng `addListeners` và qua `spring.factories`, hãy kiểm tra tránh hiệu ứng trùng lặp; mỗi đăng ký có thể tạo một instance riêng.

**Chú ý:** cú pháp `spring.factories` ở đây dành riêng cho đăng ký `ApplicationListener`. Đừng nhầm nó với cơ chế đăng ký auto-configuration của Spring Boot đời mới (`AutoConfiguration.imports`), vì hai loại extension point có mục đích khác nhau.

### SpringApplicationBuilder

Nếu ứng dụng đã dùng `SpringApplicationBuilder`, có thể đăng ký sớm bằng phương thức `listeners(...)` trước `run(...)`:

~~~java
new SpringApplicationBuilder(EarlyEventsApplication.class)
    .listeners(new EarlyEventsApplication.StartingListener(
        System.out::println
    ))
    .run(args);
~~~

Đoạn này là **trích đoạn**, cần import `org.springframework.boot.builder.SpringApplicationBuilder` và có `args` từ `main`. Hãy chọn một cách đăng ký tương ứng với cơ chế khởi tạo ứng dụng, tránh thêm listener hai lần chỉ để bảo đảm nhận event.

## 6. Những gì có thể và không thể làm tại hai mốc sớm

| Hành động | `ApplicationStartingEvent` | `ApplicationEnvironmentPreparedEvent` |
| --- | --- | --- |
| Ghi dấu mốc startup bằng mã Java độc lập | Có | Có |
| Dùng giá trị command-line `getArgs()` từ startup event, khi thích hợp | Có | Có |
| Đọc hoặc điều chỉnh `ConfigurableEnvironment` | Chưa | Có |
| Lấy bean qua `ApplicationContext.getBean(...)` | Không | Không |
| Gọi service/repository đã inject `@Autowired` | Không | Không |
| Điều chỉnh property sources trước khi tạo context | Chưa có Environment | Có |
| Chờ đến khi web server sẵn sàng | Không | Không |
| Chạy migration phụ thuộc database bean | Không phù hợp | Không phù hợp |

Nếu mục đích chỉ là “làm việc khi ứng dụng đã chạy”, dùng `ApplicationRunner`, `CommandLineRunner`, `ApplicationStartedEvent` hoặc `ApplicationReadyEvent` theo nhu cầu. Không gắn công việc dài, thao tác I/O nặng hoặc retry vô hạn vào listener rất sớm: mặc định startup listeners chạy đồng bộ, khiến toàn bộ quá trình khởi động bị chặn hoặc thất bại khi listener ném exception.

Ví dụ: với yêu cầu đưa property nguồn bên ngoài vào `Environment` rất sớm, cần cân nhắc **Config Data API** hoặc `EnvironmentPostProcessor` do Boot cung cấp nếu đó mới là extension point phù hợp cho quản lý cấu hình. `ApplicationEnvironmentPreparedEvent` có thể thêm property source nhưng không phải lúc nào cũng là nơi chuẩn để triển khai hệ thống cấu hình lớn.

### Không nhầm event phát trước Context với event phát trước refresh

`ApplicationContextInitializedEvent` được phát khi đối tượng context đã có, sau khi `ApplicationContextInitializer` chạy, nhưng trước khi load bean definitions. `ApplicationPreparedEvent` còn muộn hơn: bean definitions đã được load nhưng refresh chưa bắt đầu. **Có context không có nghĩa toàn bộ bean sẵn sàng**.

Đặc biệt, khi `ApplicationFailedEvent` xảy ra, giai đoạn lỗi quyết định context đã tồn tại hay chưa. Nếu xử lý thất bại khởi động, không được giả định `getApplicationContext()` luôn khác `null`; listener cần kiểm tra null, đồng thời tránh truy cập bean của context đã bị lỗi.

## 7. Các lỗi thường gặp và cách sửa

**Lỗi 1 – Đặt `@EventListener(ApplicationStartingEvent.class)` trên một bean và chờ nó nhận early event.** Bean được tạo quá muộn. Đăng ký `ApplicationListener<ApplicationStartingEvent>` với `SpringApplication` trước `run()`, hoặc khai báo trong `spring.factories`.

**Lỗi 2 – Cho rằng `ApplicationEnvironmentPreparedEvent` đã có context.** Nó chỉ bảo đảm `Environment` đã chuẩn bị; context sẽ được tạo ở bước sau. Không gọi `getBean()` hoặc dùng autowired service tại mốc này.

**Lỗi 3 – Đợi `ApplicationReadyEvent` để thay đổi property cần lúc tạo bean.** Khi ready, cấu hình đã được dùng để dựng nhiều bean; việc đổi nguồn property không khiến tất cả bean tự cấu hình lại. Hãy chọn extension point trước tạo context.

**Lỗi 4 – Nhầm `ApplicationStartedEvent` với `ApplicationStartingEvent`.** `ApplicationStartingEvent` xuất hiện rất sớm; `ApplicationStartedEvent` xuất hiện **sau refresh** nhưng trước runner. Hai tên gần giống nhau nhưng vòng đời và dữ liệu khả dụng rất khác.

**Lỗi 5 – Không phân biệt đăng ký listener khi startup với đăng ký bean listener.** Listener dùng `addListeners` là đối tượng cung cấp cho `SpringApplication`; không cần Spring khởi tạo bean. Nếu nó phụ thuộc vào DI, cơ chế đăng ký sớm sẽ không đáp ứng được giả định đó.

**Lỗi 6 – Khởi động logic lâu hoặc lỗi trong listener sớm.** Listener thường chạy trên startup thread; exception không được xử lý có thể khiến ứng dụng dừng. Chỉ thực hiện các công việc nhẹ, nhanh, và có mục đích bootstrap rõ ràng; log và chủ động xử lý lỗi khi thích hợp.

**Lỗi 7 – Dùng test chỉ gọi method `onApplicationEvent`.** Test như vậy chứng minh phương thức xử lý đúng nhưng không chứng minh lifecycle Boot đã dispatch event. Với mục đích kiểm tra đăng ký sớm, hãy cho `SpringApplication` chạy thật trong test.

**Lỗi 8 – Dựa vào số lần event trong hierarchy nhiều context.** Ứng dụng có context cha/con có thể nhận nhiều lần một số application event do cơ chế lan truyền event lên ancestor. Nếu áp dụng hierarchy, hãy lọc context nguồn và thiết kế listener đủ idempotent; không suy từ ví dụ một context sang mọi topology.

## 8. Checklist và câu hỏi tự kiểm tra

- Xác định chính xác cần can thiệp **trước khi context được tạo**, hay chỉ trước refresh/runner.
- Với `ApplicationStartingEvent`, không kỳ vọng `Environment` hay `ApplicationContext`.
- Với `ApplicationEnvironmentPreparedEvent`, dùng `event.getEnvironment()`, không gọi bean.
- Đăng ký bằng `addListeners`/`SpringApplicationBuilder.listeners` hoặc `spring.factories` trước khi start.
- Viết listener độc lập với DI và giữ xử lý nhanh, không block startup vô cớ.
- Kiểm thử thực bằng `SpringApplication.run()`, kiểm tra thứ tự và một hiệu ứng quan sát được.
- Nếu mục đích thay đổi cấu hình quy mô lớn, cân nhắc `EnvironmentPostProcessor`/Config Data thay vì một listener tùy tiện.

**Câu hỏi 1:** Vì sao `@Component` listener không thể nhận `ApplicationStartingEvent` từ lần startup đó?

Vì container chưa tạo bean tại thời điểm event được phát; Spring không lưu và phát lại early event cho các bean được tạo sau.

**Câu hỏi 2:** Hai event nào xảy ra trước khi `ApplicationContext` tồn tại?

`ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`. `ApplicationContextInitializedEvent` xuất hiện sau khi context đã được tạo.

**Câu hỏi 3:** Khi nào có thể đọc hoặc bổ sung property source trước khi context được tạo?

Khi nhận `ApplicationEnvironmentPreparedEvent`, lấy `event.getEnvironment().getPropertySources()` và thao tác đúng nhu cầu.

**Câu hỏi 4:** Viết listener trong `spring.factories` có cần constructor không tham số không?

Một listener do Boot tự tạo trong bootstrap phải có cách khởi tạo thích hợp mà không dựa vào bean injection; constructor công khai không tham số là lựa chọn minh bạch, đơn giản cho ví dụ này.

**Câu hỏi 5:** Khi nào nên dùng `ApplicationRunner` thay listener sớm?

Khi tác vụ cần các bean, cấu hình đã hoàn tất, hoặc một context đã refresh; nếu tác vụ cần chạy trước khi thông báo ready, runner là một điểm mở rộng phù hợp.

**Ghi nhớ:** `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` là sự kiện của **SpringApplication bootstrap**, được phát trước khi `ApplicationContext` tồn tại. Đăng ký listener **trước khi gọi `run()`** và chỉ sử dụng những thành phần đã sẵn sàng ở từng mốc. Đây là ranh giới làm cho early startup events khác với các application events được xử lý bởi bean trong một context đã dựng.

## Tài liệu tham khảo

- [Spring Boot Reference – SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot API – org.springframework.boot.context.event](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html)
- [Spring Boot API – SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot API – ApplicationEnvironmentPreparedEvent](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html)
