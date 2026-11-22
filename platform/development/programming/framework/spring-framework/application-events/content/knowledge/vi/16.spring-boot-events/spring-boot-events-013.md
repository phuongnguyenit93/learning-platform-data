# Phân biệt event của Spring Boot và event của ApplicationContext

## 1. Mục tiêu và câu trả lời cốt lõi

Trong một ứng dụng Spring Boot, bạn có thể gặp các tên rất giống nhau như `ApplicationStartedEvent`, `ContextStartedEvent`, `ApplicationReadyEvent` và `ContextRefreshedEvent`. Chúng **không phải những tên khác nhau của cùng một sự kiện**.

Có hai nhóm lifecycle chính:

1. **Spring Boot application events**: các sự kiện do quá trình `SpringApplication.run(...)` tạo ra để mô tả tiến trình **khởi động ứng dụng Boot**, từ lúc vừa bắt đầu đến lúc chuẩn bị xong, chạy runner, sẵn sàng phục vụ hoặc thất bại.
2. **Spring Framework ApplicationContext events**: các sự kiện phản ánh vòng đời của **một `ApplicationContext`**, chẳng hạn context đã refresh, được gọi `start()`, `stop()` hay `close()`. Chúng không yêu cầu Spring Boot; một ứng dụng Spring Framework thuần cũng có thể phát các event này.

Điểm dễ nhầm thứ ba: cụm “event của context” đôi khi được dùng để chỉ **bất kỳ event nào được `ApplicationContext.publishEvent(...)` phân phối**, bao gồm cả event nghiệp vụ tự tạo và một số Boot event. Trong bài này, khi nói đến **`ApplicationContextEvent`**, ta đang nói đến **họ class cụ thể** ở package `org.springframework.context.event`.

Sau bài này, bạn sẽ biết phân biệt dựa vào **nguồn phát, kiểu class, mốc thời gian, cách đăng ký listener, độ sẵn sàng của bean/context và mục đích sử dụng**; tự chạy một ví dụ Java 17+ để quan sát sự khác nhau.

## 2. Ba tầng cần tách biệt: nguồn gốc, kiểu và cơ chế phân phối

### 2.1. Boot và Spring Framework dùng chung hạ tầng event

Spring Framework có:

- `ApplicationEvent`: lớp nền cho event có source.
- `ApplicationEventPublisher`: API phát event; `ApplicationContext` cũng triển khai giao diện này.
- `ApplicationListener<E>` và `@EventListener`: hai cách tiếp nhận event.
- `ApplicationEventMulticaster`: chiến lược phân phối event đến listener thích hợp.

Spring Boot **dùng chính hạ tầng này** để công bố sự kiện lifecycle riêng. Vì vậy, “event của Boot” không hàm ý một event bus hoàn toàn khác. Boot có cơ chế phát một số event sớm khi context chưa có và dùng cơ chế context ở những giai đoạn về sau.

### 2.2. Hệ phân cấp class

~~~text
java.util.EventObject
└── org.springframework.context.ApplicationEvent
    ├── org.springframework.boot.context.event.SpringApplicationEvent
    │   ├── ApplicationStartingEvent
    │   ├── ApplicationEnvironmentPreparedEvent
    │   ├── ApplicationContextInitializedEvent
    │   ├── ApplicationPreparedEvent
    │   ├── ApplicationStartedEvent
    │   ├── ApplicationReadyEvent
    │   └── ApplicationFailedEvent
    │
    └── org.springframework.context.event.ApplicationContextEvent
        ├── ContextRefreshedEvent
        ├── ContextStartedEvent
        ├── ContextStoppedEvent
        └── ContextClosedEvent
~~~

Sơ đồ liệt kê các class lifecycle tiêu biểu trong Spring Boot 3.3.x và Spring Framework 6.1.x. Nó **không phải toàn bộ** các loại event trong Spring; ví dụ, `AvailabilityChangeEvent` và `WebServerInitializedEvent` cũng tồn tại trong Boot nhưng không nên coi mọi event mang package `org.springframework.boot` đều là subclass trực tiếp của `SpringApplicationEvent`.

**Quy tắc phân biệt:** `ApplicationStartedEvent` thuộc **Boot**; `ContextStartedEvent` thuộc **Framework**. Cả hai đều là `ApplicationEvent`, nhưng **không kế thừa lẫn nhau**.

### 2.3. So sánh theo tiêu chí

| Tiêu chí | Spring Boot application events | Framework ApplicationContext events |
| --- | --- | --- |
| Nguồn gốc | Quá trình chạy `SpringApplication` của Boot | Vòng đời `ApplicationContext` |
| Package điển hình | `org.springframework.boot.context.event` | `org.springframework.context.event` |
| Base class | `SpringApplicationEvent` cho nhóm lifecycle Boot chính | `ApplicationContextEvent` |
| Điều kiện tồn tại | Ứng dụng khởi động qua Boot | Bất kỳ Spring `ApplicationContext` phù hợp |
| Có event trước khi context hình thành? | **Có**, ví dụ `ApplicationStartingEvent` | **Không**, vì cần một context làm source |
| `@EventListener` dạng bean luôn bắt được? | Không, nhất là các event Boot phát sớm | Thường được với event xảy ra sau khi bean listener được đăng ký |
| Ý nghĩa “started” | Boot đã refresh context, **chưa chạy runners** | `ConfigurableApplicationContext.start()` được gọi tường minh |
| Ý nghĩa “ready” | Boot hoàn tất runners, tiến tới trạng thái sẵn sàng | Không có `ContextReadyEvent` tương đương trong họ context |
| Event khi đóng | Boot không có một `ApplicationStoppedEvent` chung tương đương | `ContextClosedEvent` khi context đóng |

Đừng suy diễn tên class mà hãy xem **package** và **thời điểm phát**.

## 3. Chuỗi sự kiện Spring Boot khi khởi động

Theo Spring Boot 3.3.x, trong một lần khởi động thành công thông thường, các mốc chính được phát theo trình tự:

| Thứ tự | Boot event / mốc | Context và bean lúc đó | Cần dùng khi |
| --- | --- | --- | --- |
| 1 | `ApplicationStartingEvent` | Chưa có `Environment` hay `ApplicationContext` hoàn chỉnh | Quan sát rất sớm quá trình Boot bắt đầu |
| 2 | `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị; context chưa tạo | Đọc/tác động Environment trước lúc tạo context (nếu có nhu cầu hợp lệ) |
| 3 | `ApplicationContextInitializedEvent` | Context đã chuẩn bị, initializer đã chạy; bean definitions chưa nạp | Quan sát mốc context được khởi tạo |
| 4 | `ApplicationPreparedEvent` | Bean definitions đã nạp, **context chưa refresh** | Can thiệp/quan sát giai đoạn trước refresh với giới hạn vòng đời phù hợp |
| 5 | `ContextRefreshedEvent` của Framework (mốc xen giữa) | Context được refresh thành công | Quan sát context đã sẵn sàng ở cấp Spring Framework |
| 6 | `ApplicationStartedEvent` | Context đã refresh, **chưa chạy `ApplicationRunner` / `CommandLineRunner`** | Công việc sau refresh và trước runners |
| 7 | `AvailabilityChangeEvent` với `LivenessState.CORRECT` | Boot báo trạng thái sống | Theo dõi liveness |
| 8 | `ApplicationRunner` và `CommandLineRunner` được gọi | Context đã refresh | Tác vụ chạy khi khởi động |
| 9 | `ApplicationReadyEvent` | Các runners đã hoàn thành | Quan sát mốc Boot hoàn tất startup và có thể phục vụ |
| 10 | `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` | Boot báo readiness | Theo dõi khả năng nhận traffic |

Một `WebServerInitializedEvent` còn có thể xuất hiện trong ứng dụng web khi web server được khởi tạo, trước `ApplicationStartedEvent`. Với ứng dụng **không dùng web server**, không có lý do kỳ vọng mốc này.

Nếu startup thất bại, Boot phát **`ApplicationFailedEvent`** thay cho việc khẳng định đã sẵn sàng. Event failure có thể xảy ra **trước khi có ApplicationContext**, và `getApplicationContext()` của nó có thể trả `null`.

Những mốc này cho thấy:

- `ApplicationStartingEvent` khác hoàn toàn `ApplicationStartedEvent`: từ “Starting” là **bắt đầu khởi động**, “Started” là **sau refresh**.
- `ApplicationStartedEvent` **không đồng nghĩa ứng dụng sẵn sàng phục vụ**. Runners chưa chạy vào thời điểm này.
- `ApplicationReadyEvent` là mốc muộn hơn. Nếu runner thất bại, quá trình chạy có thể phát `ApplicationFailedEvent` mà không tới `ApplicationReadyEvent`.
- `ContextRefreshedEvent` xuất hiện trong quá trình khởi động Boot, nhưng do **Framework context refresh** phát ra; nó không biến thành một `SpringApplicationEvent`.

Không dùng dãy trên làm lịch biểu cho mọi ứng dụng: child contexts, chạy lại, refresh bổ sung, failure, shutdown và sự kiện availability được phát riêng có thể tạo thêm event trong thực tế.

## 4. Vòng đời ApplicationContext trong Spring Framework

Họ `ApplicationContextEvent` không phụ thuộc vào class `SpringApplication`:

### 4.1. `ContextRefreshedEvent`

Được phát khi context **khởi tạo hoặc refresh thành công**. Với cấu hình thích hợp, đây thường là thời điểm các bean đã được tạo và xử lý qua các post-processor. Một context hỗ trợ refresh nhiều lần có thể phát event này nhiều lần; một số implementation không cho refresh lần hai.

Trong Spring Boot, `ContextRefreshedEvent` thường xảy ra trong quá trình `SpringApplication.run(...)` **trước** `ApplicationStartedEvent`. Nhưng listener `ContextRefreshedEvent` **không phải cách chuẩn để biết runner đã hoàn tất**.

### 4.2. `ContextStartedEvent`

Được phát khi gọi **`ConfigurableApplicationContext.start()`**. Nó liên quan tới lifecycle start của context và các bean `Lifecycle`, **không được tự động phát chỉ vì Spring Boot bắt đầu chạy**.

Không viết mã “đợi `ContextStartedEvent` để biết Spring Boot startup xong” trừ khi ứng dụng thực sự có lệnh `context.start()` được thiết kế rõ ràng.

### 4.3. `ContextStoppedEvent`

Được phát khi gọi **`ConfigurableApplicationContext.stop()`**. Nó mô tả stop context theo hợp đồng lifecycle; không đồng nghĩa với việc đã đóng tài nguyên hoàn toàn hay JVM đã dừng. Sau khi `stop()`, context vẫn có thể tồn tại và được start lại theo hợp đồng phù hợp.

### 4.4. `ContextClosedEvent`

Được phát khi context được **đóng** bằng `close()` hoặc qua shutdown hook. Đây là mốc đóng context ở Spring Framework; ứng dụng Boot cũng nhận được nó khi context của Boot bị đóng.

Không dùng `ContextClosedEvent` để suy luận nguyên nhân “startup failed”: một context có thể đóng do shutdown bình thường, do test kết thúc hoặc sau một lỗi, nên phải phân biệt với `ApplicationFailedEvent`.

~~~text
Spring Framework context thuần:
    new AnnotationConfigApplicationContext()
              |
              +--> refresh() --> ContextRefreshedEvent
              +--> start()   --> ContextStartedEvent
              +--> stop()    --> ContextStoppedEvent
              +--> close()   --> ContextClosedEvent

Spring Boot chạy thông thường:
    SpringApplication.run()
              |
              +--> tạo/refresh context --> ContextRefreshedEvent
              +--> ApplicationStartedEvent
              +--> runners
              +--> ApplicationReadyEvent

    (Không có yêu cầu tự động gọi context.start() khi Boot started.)
~~~

## 5. Bảng “tên giống, nghĩa khác”

| Cặp thường bị nhầm | Khác biệt chính |
| --- | --- |
| `ApplicationStartingEvent` vs `ApplicationStartedEvent` | Boot **đang bắt đầu** so với Boot **đã refresh context** |
| `ApplicationStartedEvent` vs `ContextStartedEvent` | **Boot trước runners** so với **Framework khi gọi `context.start()`** |
| `ApplicationReadyEvent` vs `ContextRefreshedEvent` | Boot **sau runners** so với Framework **sau refresh** |
| `ApplicationFailedEvent` vs `ContextClosedEvent` | Boot **khởi động thất bại** so với Framework **đóng context** (có thể hoàn toàn bình thường) |
| `ApplicationPreparedEvent` vs `ContextRefreshedEvent` | Boot **trước refresh**, bean definitions đã nạp, so với Framework **sau refresh** |
| `ApplicationContextInitializedEvent` vs `ContextRefreshedEvent` | Boot mới qua bước initializer, **chưa nạp bean definitions**, so với context **đã refresh** |
| `AvailabilityChangeEvent` vs `ApplicationReadyEvent` | Availability mô tả **state** (liveness/readiness), có thể thay đổi; Ready mô tả một **mốc startup** |
| Event do `ApplicationContext.publishEvent(...)` vs subclass `ApplicationContextEvent` | Cái đầu là **cơ chế phát** mọi loại event; cái sau là **một họ kiểu** chuyên cho lifecycle context |

Một số tên chứa chữ `Application` nhưng vẫn khác nhau cả về package, thời điểm, event source và đối tượng chịu trách nhiệm phát.

## 6. Đăng ký listener: @EventListener, ApplicationListener và event đến quá sớm

### 6.1. Listener là Spring bean

Với event xảy ra **sau khi context refresh**, có thể dùng bean:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleObservers {

    @EventListener
    public void onContextRefresh(ContextRefreshedEvent event) {
        // Framework context đã refresh.
    }

    @EventListener
    public void onBootReady(ApplicationReadyEvent event) {
        // Spring Boot đã chạy xong các runners.
    }
}
~~~

Đây là **đoạn mã tích hợp**, chưa phải chương trình độc lập. Khi class được component scan và bean listener đã đăng ký, hai phương thức nhận đúng kiểu event. Nên ưu tiên phương thức có tham số kiểu cụ thể thay vì nhận `ApplicationEvent` chung rồi đoán tên.

### 6.2. Listener cần nhận event Boot rất sớm

`ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` đến **trước khi Spring tạo bean của context**. Khi đó, một phương thức `@EventListener` trong bean **chưa tồn tại**, nên không thể nhận các event sớm này theo cách thông thường.

Đăng ký một `ApplicationListener` trực tiếp **trước khi chạy** `SpringApplication`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event ->
        System.out.println("Boot starting"),
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
        System.out.println("Environment prepared")
);

app.run(args);
~~~

Đây là đoạn minh họa cần các import và class `DemoApplication`; ví dụ hoàn chỉnh ở mục 7.

Có thể đăng ký bằng `SpringApplicationBuilder.listeners(...)` hoặc qua file `META-INF/spring.factories` để Boot tự tìm listener theo key:

~~~properties
org.springframework.context.ApplicationListener=example.BootEarlyListener
~~~

`BootEarlyListener` cần là class triển khai `ApplicationListener` với kiểu event phù hợp, có constructor mà cơ chế load có thể tạo được. Đây là **một dòng cấu hình minh họa**; không cần tạo `spring.factories` cho bài chạy đầy đủ bên dưới vì đã dùng `addListeners(...)`.

**Giới hạn:** listener chạy sớm không được giả định có `@Autowired` bean ứng dụng, repository hoặc transaction. Chỉ sử dụng những thông tin đã tồn tại tại thời điểm event đó (ví dụ, `Environment` ở `ApplicationEnvironmentPreparedEvent`), và giữ tác vụ nhẹ.

### 6.3. Listener sau refresh

`ApplicationStartedEvent`, `ApplicationReadyEvent` và `ContextRefreshedEvent` thường đến khi bean listener đã được nhận diện. `@EventListener` có thể xử lý những event này.

`ApplicationFailedEvent` là trường hợp đặc biệt: lỗi startup có thể xảy ra **trước khi bean tồn tại**, nên nếu cần theo dõi lỗi từ mọi giai đoạn startup, hãy dùng listener được đăng ký sớm bằng `addListeners(...)` hoặc cơ chế tương đương; không dựa duy nhất vào bean `@EventListener`.

## 7. Ví dụ Java 17+ chạy được: nhìn thấy hai loại event trong một lần Boot run

Ví dụ bên dưới chạy **Spring Boot 3.3.13**, dùng `WebApplicationType.NONE` nên không cần web server. Nó đăng ký hai listener Boot sớm bằng `SpringApplication.addListeners(...)`; đồng thời tạo một Spring bean chứa listener cho `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, `ContextStartedEvent`, `ContextStoppedEvent` và `ContextClosedEvent`. Sau khi Boot ready, mã **chủ động** gọi `context.start()`, `stop()` và `close()` để đối chiếu đúng ý nghĩa các context event.

### 7.1. Cấu trúc thư mục

~~~text
boot-context-events-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── BootVsContextEventsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'boot-context-events-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

`spring-boot-starter` đưa Spring Framework context và Boot autoconfiguration vào classpath; Boot BOM giúp các dependency có phiên bản tương thích. Gradle plugin 3.3.13 hỗ trợ Java 17 và Gradle 7.5+ hoặc Gradle 8.x.

### 7.2. Mã nguồn hoàn chỉnh

`src/main/java/example/BootVsContextEventsDemo.java`:

~~~java
package example;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class BootVsContextEventsDemo {

    @Bean
    public LifecycleObservers lifecycleObservers() {
        return new LifecycleObservers();
    }

    @Bean
    public CommandLineRunner runner() {
        return args -> System.out.println("runner: executed");
    }

    public static final class LifecycleObservers {

        @EventListener
        public void onContextRefreshed(ContextRefreshedEvent event) {
            System.out.println("context: refreshed");
        }

        @EventListener
        public void onBootStarted(ApplicationStartedEvent event) {
            System.out.println("boot: started");
        }

        @EventListener
        public void onBootReady(ApplicationReadyEvent event) {
            System.out.println("boot: ready");
        }

        @EventListener
        public void onContextStarted(ContextStartedEvent event) {
            System.out.println("context: started (explicit)");
        }

        @EventListener
        public void onContextStopped(ContextStoppedEvent event) {
            System.out.println("context: stopped (explicit)");
        }

        @EventListener
        public void onContextClosed(ContextClosedEvent event) {
            System.out.println("context: closed");
        }
    }

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BootVsContextEventsDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Đăng ký trước khi run(): nhận được Boot event rất sớm.
        application.addListeners(
            (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("boot: starting"),
            (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
                System.out.println("boot: environment prepared")
        );

        ConfigurableApplicationContext context = application.run(args);

        // Ba thao tác sau được gọi tường minh để kích hoạt context events.
        context.start();
        context.stop();
        context.close();
    }
}
~~~

### 7.3. Chạy chương trình

Tại thư mục `boot-context-events-demo`, với JDK 17+ và Gradle đã cài:

~~~bash
gradle bootRun
~~~

Hoặc dùng Gradle Wrapper nếu dự án đã thiết lập: `./gradlew bootRun` trên Linux/macOS hay `gradlew.bat bootRun` trên Windows.

Các dòng **do những lệnh `System.out.println(...)` trong mã nguồn chủ động in ra**, theo thứ tự:

~~~text
boot: starting
boot: environment prepared
context: refreshed
boot: started
runner: executed
boot: ready
context: started (explicit)
context: stopped (explicit)
context: closed
~~~

Log của Gradle, thư viện logging và framework có thể xuất hiện xen kẽ tùy môi trường. Vì vậy, bảng trên không khẳng định toàn bộ stdout của một lần chạy chỉ gồm chín dòng, mà là **thứ tự các dòng demo cần quan sát**.

### 7.4. Vì sao kết quả thể hiện đúng sự khác biệt?

- Hai dòng `boot: starting` và `boot: environment prepared` xuất hiện vì listener được đăng ký trực tiếp vào `SpringApplication` **trước khi context được tạo**, không phải bằng bean.
- `context: refreshed` đến trước `boot: started` vì Framework refresh context trước, rồi Boot mới thông báo đã started.
- `boot: started` đến **trước** `runner: executed`; điều này phù hợp với hợp đồng `ApplicationStartedEvent`.
- `boot: ready` đến **sau** `runner: executed`, nên rõ ràng không thể thay `ApplicationReadyEvent` bằng `ContextRefreshedEvent`.
- `context: started (explicit)` và `context: stopped (explicit)` chỉ có vì chính phương thức `main` gọi `context.start()`, `context.stop()`. Boot tự khởi động **không mặc nhiên phát các event này**.
- `context: closed` thể hiện context đóng sau khi main gọi `close()`, không phải startup thất bại.

Nếu bạn xóa ba lời gọi cuối `start()`, `stop()`, `close()`, chương trình sẽ không còn phát hai context event start/stop theo đường đi này. Shutdown hook vẫn có thể đóng context khi JVM kết thúc và tạo `ContextClosedEvent`; thời điểm đóng lúc đó khác với thao tác tường minh của demo.

## 8. ApplicationContext thuần vẫn có context events, không cần Boot

Đây là mã minh họa dùng **Spring Framework** và đăng ký listener trước khi refresh:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;

AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.addApplicationListener(
        (ApplicationListener<ContextRefreshedEvent>) event ->
                System.out.println("framework: refreshed"));

context.addApplicationListener(
        (ApplicationListener<ContextClosedEvent>) event ->
                System.out.println("framework: closed"));

context.refresh();
context.close();
~~~

Đây là **đoạn code minh họa cần đặt trong phương thức Java và có dependency `spring-context`**, chưa phải chương trình độc lập. Nó thể hiện rằng `ContextRefreshedEvent` và `ContextClosedEvent` có thể hoạt động khi **không có bất kỳ `SpringApplication` nào**. Vì vậy sẽ không có `ApplicationStartingEvent`, `ApplicationStartedEvent` hay `ApplicationReadyEvent` trong ví dụ context thuần này.

Spring Boot chỉ là một cách xây dựng và chạy Spring application; lifecycle context cơ bản vẫn do Spring Framework thực hiện.

## 9. Lấy thông tin gì từ mỗi event?

### 9.1. Boot event

Các event thuộc `SpringApplicationEvent` có thể cho biết đối tượng `SpringApplication` và tham số chạy qua `getSpringApplication()`, `getArgs()`. Mỗi subclass có thể cung cấp thêm thông tin:

- `ApplicationEnvironmentPreparedEvent#getEnvironment()`: `Environment` đã sẵn sàng, nhưng context chưa được tạo.
- `ApplicationContextInitializedEvent#getApplicationContext()`: context đã được initializer xử lý nhưng chưa nạp bean definitions.
- `ApplicationPreparedEvent#getApplicationContext()`: context đã chuẩn bị, chưa refresh.
- `ApplicationStartedEvent#getApplicationContext()`: context đã refresh.
- `ApplicationReadyEvent#getApplicationContext()`: context sau runners.
- `ApplicationFailedEvent#getException()`: nguyên nhân lỗi. `getApplicationContext()` **có thể null** nếu thất bại quá sớm.

Không gọi `getBean(...)` khi event đang ở giai đoạn context chưa refresh nếu không có yêu cầu và hiểu rõ hạn chế. Một context object **đã tồn tại** không có nghĩa toàn bộ bean đã khởi tạo xong.

### 9.2. Context event

`ApplicationContextEvent` có phương thức `getApplicationContext()` trả về context nguồn; các subclass như `ContextRefreshedEvent` cũng có method này.

Khi có **parent/child context**, context event từ child có thể được phát lên parent. Một listener ở parent vì thế có thể nhìn thấy nhiều event cùng kiểu nhưng thuộc context khác nhau.

Nếu listener cần phân biệt context:

~~~java
@EventListener
public void onRefresh(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != this.applicationContext) {
        return; // Bỏ qua event từ context con.
    }

    // Xử lý event do chính context hiện tại phát.
}
~~~

Đây là **đoạn minh họa**, giả định class listener đã được inject một trường `applicationContext` đúng kiểu `ApplicationContext`. Chỉ dùng so sánh identity khi cần loại bỏ event từ context con; không tự động lọc mọi event vì ứng dụng một context không có vấn đề trùng đó.

## 10. Chọn sự kiện nào cho từng nhu cầu?

| Nhu cầu thực tế | Chọn event/cơ chế |
| --- | --- |
| Đọc/điều chỉnh `Environment` rất sớm | `ApplicationEnvironmentPreparedEvent`, đăng ký listener trước `run()` |
| Thao tác với initializer / giai đoạn chưa nạp bean definitions | `ApplicationContextInitializedEvent` và cơ chế initializer phù hợp |
| Quan sát context hoàn tất refresh | `ContextRefreshedEvent` |
| Làm việc sau refresh nhưng trước runners | `ApplicationStartedEvent` |
| Chạy một tác vụ có thứ tự rõ khi startup | `ApplicationRunner` hoặc `CommandLineRunner` |
| Quan sát Boot chạy xong runners | `ApplicationReadyEvent` |
| Kiểm tra khả năng nhận traffic của service | `AvailabilityChangeEvent` / `ApplicationAvailability` và readiness state |
| Khởi động/dừng các bean theo lifecycle tường minh | `ContextStartedEvent`/`ContextStoppedEvent` khi thực sự dùng `start()`/`stop()` |
| Giải phóng tài nguyên lúc context đóng | `ContextClosedEvent` hoặc lifecycle callback phù hợp như `@PreDestroy` |
| Thu thập mọi lỗi startup kể cả trước khi có bean | Listener `ApplicationFailedEvent` đăng ký sớm |
| Truyền sự kiện nghiệp vụ “đơn hàng đã tạo” | Event nghiệp vụ riêng qua `ApplicationEventPublisher`; không lạm dụng Boot lifecycle event |

Lưu ý: công việc startup dài trong listener có thể **chặn thread khởi động** nếu cơ chế phân phối đồng bộ. Không biến `ApplicationReadyEvent` thành nơi xử lý những tác vụ lâu đến mức ứng dụng mất nhiều thời gian mới hoàn thành startup. Với yêu cầu orchestration cụ thể, runners, lifecycle components hoặc một scheduler/worker chuyên dụng có thể rõ hơn.

## 11. Trường hợp lỗi và những ngộ nhận thường gặp

| Ngộ nhận / lỗi | Cách hiểu đúng |
| --- | --- |
| `ApplicationStartedEvent` tương đương `ContextStartedEvent` | Hai lớp khác package và semantics: Boot sau refresh trước runners; context event khi `start()` |
| `ContextRefreshedEvent` nghĩa là Boot đã sẵn sàng nhận request | Không, Boot runner còn có thể đang chờ; kiểm tra `ApplicationReadyEvent` và readiness |
| Thêm `@EventListener(ApplicationStartingEvent.class)` vào bean là bắt được event sớm | Bean chưa được tạo ở thời điểm đó; dùng `SpringApplication.addListeners(...)` hoặc `spring.factories` |
| `ApplicationPreparedEvent` đến sau refresh | Nó đến **trước** refresh |
| `ApplicationContextInitializedEvent` nghĩa là toàn bộ bean đã khởi tạo | Chưa; bean definitions chưa được nạp |
| `ApplicationReadyEvent` luôn được phát dù startup lỗi | Không; nếu startup thất bại Boot có thể phát `ApplicationFailedEvent` |
| `ApplicationFailedEvent#getApplicationContext()` luôn không null | Có thể null nếu lỗi trước khi tạo context |
| Mọi `ApplicationEvent` đều là `ApplicationContextEvent` | Sai; `SpringApplicationEvent` và event nghiệp vụ có thể là các nhánh khác |
| Boot có event chung `ApplicationStoppedEvent` cho mọi lần dừng | Không có event chuẩn tương đương trong bộ lifecycle cơ bản này; dùng context close/stop khi phù hợp |
| `ContextStartedEvent` tự động phát mỗi khi JVM chạy Boot | Chỉ khi context nhận lời gọi `start()` theo hợp đồng Framework |
| `@Order` làm Boot ready trước Context refresh | `@Order` chỉ ảnh hưởng thứ tự listener cho **cùng sự kiện**, không đảo lifecycle |
| Event listener bảo đảm xử lý bất đồng bộ | Mặc định event listeners thường chạy đồng bộ; phải cấu hình async nếu cần và hiểu thứ tự hoàn tất |
| Một event nhận được hai lần chắc chắn là bug | Có thể do parent/child context, nhiều context hoặc nhiều run; kiểm tra `getApplicationContext()` và nguồn event |
| Event listener có thể thay cho messaging bền vững | Spring application events chủ yếu là cơ chế nội bộ; không bảo đảm lưu event qua restart hay retry như broker/outbox |

### Exception trong listener

Với cơ chế multicast đồng bộ mặc định, exception chưa xử lý từ listener có thể truyền ngược về phía phát event và ảnh hưởng quá trình startup. Vì vậy:

- Listener của `ApplicationReadyEvent` vẫn có thể khiến quá trình startup báo lỗi nếu nó ném exception trong cùng lời gọi phát.
- Listener rất sớm không nên làm tác vụ dễ thất bại hoặc phụ thuộc bean chưa tồn tại.
- Nếu cấu hình multicaster chạy async, thứ tự hoàn tất và đường đi của lỗi thay đổi; **không suy luận Boot đã hoàn thành một tác vụ async chỉ vì event đã được phát**.

## 12. Chẩn đoán khi listener không chạy

Kiểm tra lần lượt:

1. **Bạn thực sự lắng nghe event nào?** Xem full class name và import; `ApplicationStartedEvent` của Boot khác `ContextStartedEvent` của Framework.
2. **Event xảy ra trước hay sau khi bean listener được tạo?** Với event sớm, đăng ký trực tiếp bằng `addListeners(...)`.
3. **Ứng dụng chạy qua `SpringApplication.run(...)`?** Một context Spring Framework thuần không phát toàn bộ Boot startup events.
4. **Bạn đã gọi `context.start()` hoặc `context.stop()`?** Nếu chưa, không mong `ContextStartedEvent`/`ContextStoppedEvent` tự xảy ra.
5. **Có runner chặn hoặc ném lỗi?** Khi ấy có thể có `ApplicationStartedEvent` nhưng chưa có `ApplicationReadyEvent`.
6. **Có parent/child contexts?** Event được chuyển lên parent có thể khiến listener nhận nhiều lần.
7. **Listener có phải bean/được đăng ký đúng không?** `@EventListener` phải thuộc bean được Spring phát hiện, còn `ApplicationListener` sớm phải đăng ký trước `run()`.
8. **Có bất đồng bộ không?** Dòng log từ nhiều thread không nhất thiết bảo toàn thứ tự hoàn thành dù lifecycle event có thứ tự phát.
9. **Ứng dụng có bị đóng ngay?** Xác định thời điểm context close và runner before/after event để tránh hiểu sai.

Để quan sát hành vi, log cả **tên event, context ID (nếu có), tên thread và thời điểm**. Hạn chế ghi dữ liệu nhạy cảm từ Environment/command-line arguments vào log.

## 13. Cách kiểm thử thứ tự một cách đáng tin cậy

Với ứng dụng Boot, một integration test muốn chứng minh thứ tự phải thật sự **chạy `SpringApplication`** với listener được đăng ký trước startup. Không nên khởi tạo `ApplicationContext` rồi tự gọi trực tiếp `onBootReady(...)`, vì làm vậy không kiểm tra Boot phát event vào đúng lifecycle.

Có thể dùng một collector thread-safe:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

List<String> trace = new CopyOnWriteArrayList<>();

SpringApplication application = new SpringApplication(DemoApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event ->
        trace.add("starting"),
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
        trace.add("environment")
);
~~~

Đây là **đoạn minh họa cho cách thu thập bằng chứng**, cần class `DemoApplication`/imports và một lần gọi `application.run(...)` để thực thi. Để đo `ContextRefreshedEvent` và `ApplicationReadyEvent` bằng bean, phải cùng dùng collector đã được truyền vào/đăng ký từ cấu hình phù hợp. Đừng đưa hai collector độc lập vào rồi chỉ so hai log không có mốc chung.

Các phép thử thiết yếu:

- Đăng ký trước `run()` rồi khẳng định có `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`.
- Dùng listener bean nhận `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`; khẳng định relative order: **refreshed → started → runner → ready**.
- Không gọi `context.start()` thì **không kỳ vọng** `ContextStartedEvent` chỉ vì Boot startup.
- Chủ động gọi `start()`, `stop()`, `close()` để khẳng định các event tương ứng.
- Tạo một runner ném exception có kiểm soát trong test riêng để khẳng định có `ApplicationFailedEvent` và không tới `ApplicationReadyEvent`; test phải xử lý/đóng context an toàn.
- Khi dùng contexts cha–con, khẳng định listener lọc theo context identity nếu đó là yêu cầu.

**Lưu ý với `@SpringBootTest`:** test context có thể được cache và hoạt động khởi tạo do framework test điều phối. Nếu mục tiêu là kiểm tra **event sớm trước khi bean được tạo**, một test chỉ autowire listener vào test class sau lúc startup khó làm oracle cho event đã xảy ra. Hãy đăng ký listener trước khi gọi `SpringApplication.run(...)` trong test tích hợp có kiểm soát, hoặc dùng thiết bị ghi nhận startup được khởi tạo đúng thời điểm.

## 14. Các câu hỏi tự kiểm tra

**Câu 1.** `ApplicationStartedEvent` và `ContextStartedEvent` có cùng phát khi Spring Boot ứng dụng mở lên không?

**Đáp án:** Không. Boot phát `ApplicationStartedEvent` sau refresh, trước runners; `ContextStartedEvent` chỉ xuất hiện nếu `ConfigurableApplicationContext.start()` được gọi.

**Câu 2.** Muốn thực thi một đoạn code sau khi tất cả `CommandLineRunner` hoàn tất thì theo dõi event nào?

**Đáp án:** `ApplicationReadyEvent`. Tuy vậy, nếu đoạn code đó là bước startup nghiệp vụ có thứ tự hoặc cần retry, có thể chọn cơ chế runner/workflow riêng phù hợp.

**Câu 3.** `ContextRefreshedEvent` có xuất hiện trong ứng dụng Spring Framework không sử dụng Boot không?

**Đáp án:** Có. Event do vòng đời context phát ra; không yêu cầu `SpringApplication`.

**Câu 4.** Có thể bắt `ApplicationEnvironmentPreparedEvent` bằng phương thức `@EventListener` trên một bean component thông thường không?

**Đáp án:** Không theo cách thông thường vì event này xảy ra trước khi context/bean được tạo; cần đăng ký `ApplicationListener` sớm qua `addListeners(...)`, builder hoặc `spring.factories`.

**Câu 5.** Một runner ném exception trước khi hoàn tất. Có thể đã có `ApplicationStartedEvent` nhưng không có `ApplicationReadyEvent` không?

**Đáp án:** Có. Started xảy ra trước runners, Ready sau runners; failure có thể được phát khi startup lỗi.

**Câu 6.** Trong `ContextRefreshedEvent`, method nào cho biết context thực sự là source?

**Đáp án:** `event.getApplicationContext()`. Có thể dùng để kiểm tra identity khi ứng dụng có nhiều context.

**Câu 7.** Boot có cùng chia sẻ `ApplicationEventPublisher` và listener mechanism của Spring Framework không?

**Đáp án:** Có. Sự khác nhau chủ yếu nằm ở nguồn gốc/mốc lifecycle và class, không phải mọi Boot event được truyền qua một bus hoàn toàn khác.

## 15. Tài liệu tham khảo

- Spring Boot 3.3 — Application Events and Listeners (lifecycle và cách đăng ký sớm): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Package `org.springframework.boot.context.event`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/package-summary.html
- Spring Boot 3.3 — `ApplicationStartedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3 — `ApplicationReadyEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 — `ApplicationFailedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
- Spring Boot 3.3 — Gradle plugin và Java requirements: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Framework 6.1 — `ApplicationContextEvent` và các subclass: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html
- Spring Framework — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
