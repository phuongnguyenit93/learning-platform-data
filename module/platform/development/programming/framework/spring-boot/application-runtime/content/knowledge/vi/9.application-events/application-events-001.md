# Bản đồ sự kiện SpringApplication theo tiến trình khởi động

## Mục tiêu

Spring Boot phát ra nhiều sự kiện (*application events*) trong lúc `SpringApplication.run(...)` chuẩn bị môi trường, tạo `ApplicationContext`, refresh bean container, chạy các runner, chuyển trạng thái availability và thông báo ready. Việc xác định **đúng mốc** giúp đặt listener, kiểm tra startup, ghi log, nạp cấu hình và quản lý readiness mà không truy cập nhầm một container chưa sẵn sàng.

Bài học thuộc **Spring Boot Application Runtime → Sự kiện ứng dụng**, sử dụng API và vòng đời của **Spring Boot 3.3.13 / Spring Framework 6.1**. Sau khi học, bạn có thể:

1. Đọc đúng thứ tự `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent`, `ApplicationPreparedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent` và nhánh `ApplicationFailedEvent`.
2. Đặt `ContextRefreshedEvent` và `WebServerInitializedEvent` vào đúng khoảng của tiến trình.
3. Phân biệt sự kiện SpringApplication với `AvailabilityChangeEvent` mang `LivenessState` hoặc `ReadinessState`.
4. Biết khi nào chưa có `Environment`, khi nào context đã tạo nhưng chưa refresh, và khi nào có thể truy cập bean một cách an toàn.
5. Đăng ký listener đủ sớm bằng `SpringApplication.addListeners(...)` hoặc `META-INF/spring.factories`; phân biệt với `@EventListener` trên bean.
6. Chạy một ví dụ Java 17+ để quan sát đường khởi động thành công và lỗi trong startup runner.

## 1. Vì sao phải có “bản đồ” sự kiện?

Không có một sự kiện duy nhất đại diện cho mọi ý nghĩa của “ứng dụng đã khởi động”. Trong một lần startup:

- `Environment` xuất hiện trước `ApplicationContext`.
- Context được tạo, chạy `ApplicationContextInitializer` và nạp bean definitions **trước** khi `refresh()`.
- Trong `refresh()`, Spring tạo nhiều singleton, khởi động hạ tầng và phát `ContextRefreshedEvent`.
- `ApplicationStartedEvent` xuất hiện **sau refresh** nhưng **trước** `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent` xuất hiện **sau khi** các runners chạy thành công.
- Availability có thông điệp riêng: **live** sau refresh và **ready to accept traffic** sau ready event.
- Nếu startup thất bại, `ApplicationFailedEvent` là **nhánh lỗi**, không phải sự kiện cuối của mọi lần khởi động.

Chọn nhầm mốc gây những lỗi như truy cập `getBean` khi bean definitions chưa nạp, chạy migration nặng trong listener sớm, đánh dấu ready trước khi chuẩn bị dữ liệu hoặc đăng ký một `@Bean` listener quá muộn để thấy sự kiện ban đầu.

**Nguyên tắc:** Sự kiện báo *mốc tiến trình* và quyền sử dụng API tương ứng. Sự kiện không có nghĩa mọi thành phần hay dịch vụ bên ngoài đều đã khỏe mạnh.

## 2. Timeline chuẩn trong Spring Boot 3.3

Một lần chạy thành công của `SpringApplication` thông thường có trình tự sau. Đây là thứ tự **được tài liệu Spring Boot công bố**, với hai sự kiện thuộc hệ thống Spring context/web được đặt vào khoảng refresh:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- 01. ApplicationStartingEvent
    |       (listeners/initializers được đăng ký; chưa có Environment)
    |
    +-- 02. ApplicationEnvironmentPreparedEvent
    |       (Environment đã có; chưa tạo ApplicationContext)
    |
    +-- Tạo context, gọi ApplicationContextInitializer
    |
    +-- 03. ApplicationContextInitializedEvent
    |       (context đã chuẩn bị; chưa nạp bean definitions)
    |
    +-- Nạp bean definitions / chuẩn bị context
    |
    +-- 04. ApplicationPreparedEvent
    |       (bean definitions đã nạp; chưa gọi refresh)
    |
    +-- ApplicationContext.refresh()
    |       |-- BeanFactoryPostProcessors, BeanPostProcessors
    |       |-- Khởi tạo singleton non-lazy / hạ tầng
    |       |-- [web] WebServerInitializedEvent
    |       +-- ContextRefreshedEvent
    |           (hai sự kiện web/context thuộc khoảng refresh;
    |            không dựa vào thứ tự tuyệt đối của mọi callback)
    |
    +-- 05. ApplicationStartedEvent
    |
    +-- 06. AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- 07. ApplicationReadyEvent
    |
    +-- 08. AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    +-- run(...) trả về ConfigurableApplicationContext
            |
            v
        Ứng dụng vận hành
~~~

Khi **startup ném exception**, có thêm nhánh:

~~~text
Một giai đoạn của SpringApplication.run(...)
    |
    +-- exception không thể phục hồi trong startup
            |
            v
        ApplicationFailedEvent
            |
            +-- Ghi lỗi / failure analysis / cleanup theo khả năng
            +-- run(...) kết thúc bằng exception, không đạt ready
~~~

`ApplicationFailedEvent` có thể xảy ra ở nhiều giai đoạn: trước khi context tồn tại, trong lúc refresh hoặc khi runner ném exception. Do đó đừng đặt nó như “bước thứ 9 chắc chắn xuất hiện sau ready”.

Trong bản đồ thành công, thứ tự 01–08 là **mốc nghiệp vụ chính**. Với ứng dụng non-web không có embedded HTTP server, **không có** `WebServerInitializedEvent` tương ứng. Với ứng dụng có nhiều context cha/con hoặc nhiều bootstrap run, phải xét mỗi lần chạy và mỗi context riêng.

## 3. Bảng tra nhanh: event, lúc phát và thứ đã sẵn sàng

| Event hoặc mốc | Thời điểm | Có thể dựa vào gì? | Chưa nên giả định |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Ngay đầu `run`, sau đăng ký listener/initializer | Thông tin `SpringApplication`, args cơ bản | Chưa có `Environment`/`ApplicationContext` |
| `ApplicationEnvironmentPreparedEvent` | `Environment` đã chuẩn bị lần đầu | `ConfigurableEnvironment` để đọc/tùy biến nguồn cấu hình phù hợp | Chưa có Spring application context |
| `ApplicationContextInitializedEvent` | Context được tạo, initializers đã chạy | `ConfigurableApplicationContext` đã chuẩn bị | Bean definitions của ứng dụng chưa nạp; chưa refresh |
| `ApplicationPreparedEvent` | Đã nạp bean definitions, ngay trước refresh | Context và các định nghĩa bean đã chuẩn bị | Không coi các singleton application đã khởi tạo |
| `ContextRefreshedEvent` | `ApplicationContext.refresh()` hoàn thành | BeanFactory/context đã refresh thành công | Boot runners có thể chưa chạy |
| `WebServerInitializedEvent` (web) | Server được khởi tạo trong startup web | Server đã khởi tạo, có thể lấy thông tin cổng | Không mặc nhiên chứng minh readiness của ứng dụng |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Context đã refresh | Chưa chạy xong startup runners |
| `AvailabilityChangeEvent(LivenessState.CORRECT)` | Ngay sau started event | Spring Boot xem context đã live | Không đồng nghĩa ready nhận traffic |
| `ApplicationReadyEvent` | Sau runners | Giai đoạn Boot startup chính đã hoàn tất | Availability readiness event được phát ngay **sau** mốc này |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Sau ready event | Boot cho biết instance sẵn sàng nhận traffic | Không bảo đảm dependency ngoài luôn khỏe |
| `ApplicationFailedEvent` | Khi có lỗi startup | Exception gây thất bại, context nếu đã có | Không luôn có context; không phải request error |

Bốn `Application...Event` đầu tiên đều phát **trước** `refresh()`. Sự khác nhau lớn nhất giữa chúng nằm ở **Environment có chưa, context có chưa và bean definitions đã nạp chưa**.

Các event `ApplicationStartingEvent` đến `ApplicationReadyEvent` và `ApplicationFailedEvent` là nhóm sự kiện đặc trưng của `SpringApplication` trong package `org.springframework.boot.context.event`. `ContextRefreshedEvent` là sự kiện của **Spring Framework** trong `org.springframework.context.event`; `AvailabilityChangeEvent` thuộc `org.springframework.boot.availability` và không phải một subclass của `SpringApplicationEvent`. Chúng vẫn có thể được quan sát bởi cơ chế Spring `ApplicationListener`.

## 4. Diễn giải từng giai đoạn

### 4.1. ApplicationStartingEvent: chưa có Environment

`ApplicationStartingEvent` được phát ở giai đoạn rất đầu của `SpringApplication.run(...)`, chỉ sau khi các listener và initializer cần thiết đã đăng ký. Chưa thể dùng `Environment.getProperty(...)` hoặc `ApplicationContext.getBean(...)` vì các thành phần đó chưa được tạo cho lần chạy.

Công việc thích hợp là ghi nhận mốc khởi động tối giản, tích hợp cơ chế bootstrap rất sớm hoặc chuẩn bị những thành phần không đòi hỏi bean application. Listener nên nhẹ và tránh phụ thuộc vào logging/bean initialization phức tạp ở thời điểm này.

Đây là lý do một listener được tạo bởi `@Bean` **không thể chắc chắn nhận** `ApplicationStartingEvent`: định nghĩa bean chỉ được xử lý ở giai đoạn sau.

### 4.2. ApplicationEnvironmentPreparedEvent: có Environment, chưa có context

Lúc này `ConfigurableEnvironment` đã tồn tại và được dùng cho application context, nhưng context chưa được tạo. Listener có thể đọc các property source đã có và bổ sung/điều chỉnh nguồn cấu hình trong phạm vi phù hợp.

Ví dụ **minh họa một phần**:

~~~java
if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
    String appName = prepared.getEnvironment()
            .getProperty("spring.application.name", "unnamed");
    System.out.println("Application name: " + appName);
}
~~~

Đoạn trên giả định `event` có kiểu `ApplicationEvent` và import `ApplicationEnvironmentPreparedEvent`. Lưu ý Config Data và thứ tự ưu tiên nguồn cấu hình có cơ chế riêng; **không nên thêm bí mật hay ghi đè property một cách tùy tiện** tại listener.

Không gọi `getApplicationContext()` trên event này: nó cấp environment, chưa cấp một application context.

### 4.3. ApplicationContextInitializedEvent: context có rồi, bean definitions chưa nạp

`ApplicationContextInitializedEvent` được phát sau khi Spring Boot đã tạo, chuẩn bị context và gọi các `ApplicationContextInitializer`. Đây là lúc biết context type (`SERVLET`, `REACTIVE` hoặc `NONE` đã dẫn đến implementation phù hợp) nhưng chưa thể giả định các `@Bean`/`@Component` của ứng dụng đã được nạp.

Sự khác nhau cần nhớ:

- `ApplicationContextInitializer`: callback **chỉnh sửa context** trong quá trình chuẩn bị.
- `ApplicationContextInitializedEvent`: sự kiện **báo rằng các initializers đã chạy**.

Hai cơ chế có liên quan nhưng không thể thay thế nhau tùy ý.

### 4.4. ApplicationPreparedEvent: bean definitions có, refresh chưa bắt đầu

Sau khi bean definitions được nạp, Spring Boot phát `ApplicationPreparedEvent` ngay trước refresh. `Environment` sẵn sàng; bean definitions đã có; nhiều singleton application vẫn chưa được khởi tạo. Thực hiện `context.getBean(...)` trong event sớm này có thể kích hoạt tạo bean sai thời điểm hoặc đi ngược vòng đời bình thường.

Nếu cần làm việc với bean sau khi container đã hoạt động, hãy dùng hook muộn hơn như `ContextRefreshedEvent`, `ApplicationStartedEvent` hoặc runner, tùy công việc.

### 4.5. ContextRefreshedEvent và WebServerInitializedEvent

`ContextRefreshedEvent` báo một `ApplicationContext` đã được refresh. Trong refresh, Spring chuẩn bị BeanFactory, xử lý post-processors, tạo singleton không lazy đủ điều kiện và khởi động phần hạ tầng phù hợp.

Với web application, `WebServerInitializedEvent` xuất hiện khi embedded web server đã sẵn sàng ở giai đoạn startup web, với biến thể `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent`. Tài liệu Spring Boot đặt các event này **sau Prepared và trước Started**; không nên dựa vào một thứ tự log tuyệt đối giữa mọi callback server và context mà không xét web server implementation.

Để xác định cổng server thật (đặc biệt `server.port=0`), sự kiện web server initialized là tín hiệu phù hợp hơn là đọc cổng cấu hình trước khi server bind. Nhưng web server đã khởi động **không đồng nghĩa** startup runner đã chạy xong hoặc readiness đã nhận traffic.

### 4.6. ApplicationStartedEvent và liveness

Sau khi refresh hoàn tất, Spring Boot phát `ApplicationStartedEvent`, rồi phát `AvailabilityChangeEvent` với `LivenessState.CORRECT`. Đây là cách Boot cho biết trạng thái nội bộ sau khi context startup thành công.

**Liveness ≠ readiness.** Liveness phản ánh việc tiến trình có thể hoạt động hợp lệ hay cần được khởi động lại; readiness phản ánh có nên định tuyến traffic đến instance lúc này hay không.

Điểm đáng chú ý: `ApplicationRunner` và `CommandLineRunner` **chưa được gọi tại thời điểm ApplicationStartedEvent**, nên không nên dùng event này để tuyên bố toàn bộ tác vụ startup của ứng dụng đã hoàn tất.

### 4.7. ApplicationReadyEvent và readiness

Sau `ApplicationStartedEvent` và liveness correct, Spring Boot chạy các bean `ApplicationRunner`/`CommandLineRunner` theo thứ tự được thiết lập (`@Order`/`Ordered` nếu cần). Khi các runners hoàn tất thành công, Boot phát `ApplicationReadyEvent`, sau đó phát `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC`.

Có thể sử dụng `ApplicationReadyEvent` để ghi log mốc hoàn tất startup, quan sát metrics hoặc thực hiện công việc thật ngắn. Nếu một tác vụ **phải hoàn tất trước khi ứng dụng đạt ready**, nên đặt nó vào runner thích hợp, có timeout và lỗi rõ ràng, thay vì tạo một vòng lặp nền kéo dài vô hạn bên trong listener ready.

Việc application ready theo Boot **không bảo đảm** một DB, cache hoặc downstream API bên ngoài luôn có thể đáp ứng. Nếu điều kiện định tuyến phụ thuộc hệ thống ngoài, cần thiết kế readiness/health policy phù hợp thay vì giả định mọi dependency đều khỏe vĩnh viễn.

### 4.8. ApplicationFailedEvent: nhánh lỗi khởi động

`ApplicationFailedEvent` được phát khi `SpringApplication` không khởi động thành công. Listener có thể xem `getException()` để chẩn đoán, và `getApplicationContext()` có thể chưa có giá trị hữu ích nếu lỗi xuất hiện trước bước tạo context.

Trường hợp xảy ra ở runner rất dễ thấy: context đã refresh và có thể đã phát `ApplicationStartedEvent` cùng liveness correct, nhưng runner ném exception nên **ApplicationReadyEvent** và **ReadinessState.ACCEPTING_TRAFFIC** sẽ không xuất hiện trong đường thành công bình thường.

`ApplicationFailedEvent` **không** phải event phát cho mọi HTTP 4xx/5xx, exception từ controller hoặc một request bị client hủy sau khi ứng dụng đã startup. Đó là các luồng xử lý khác, cần exception handling và telemetry riêng.

## 5. Vì sao đăng ký listener sớm lại quan trọng?

Có ba cách phổ biến.

### Cách A: SpringApplication.addListeners trước run

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new MyStartupListener());
application.run(args);
~~~

Đây là **minh họa một phần**; cần định nghĩa `DemoApplication` và `MyStartupListener`. Đây là phương án rõ ràng khi sở hữu `main`. Listener được đăng ký trước khi Boot phát các sự kiện đầu, nên có khả năng quan sát `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.

### Cách B: META-INF/spring.factories

Một thư viện hoặc ứng dụng muốn tự động đăng ký listener có thể khai báo:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.context.ApplicationListener=com.example.events.MyStartupListener
~~~

Trong Spring Boot 3.3, key dành cho listener là **`org.springframework.context.ApplicationListener`**. Class cần là một listener tạo được bởi cơ chế Spring factories, thường có constructor không đối số. Khi dùng cách này, không cần đăng ký lại cùng listener bằng `addListeners` chỉ để quan sát một startup, nếu không có chủ đích xử lý trùng.

`spring.factories` dành cho listener ở đây **không đồng nghĩa** với `AutoConfiguration.imports`, vốn là cơ chế khác cho auto-configuration.

### Cách C: bean @EventListener hoặc ApplicationListener do Spring quản lý

Khi application context đã nạp và khởi tạo bean, có thể viết:

~~~java
@Component
public class ReadyObserver {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("READY observer: beans are available");
    }
}
~~~

Đây là **mã minh họa một phần**; cần imports `Component`, `EventListener`, `ApplicationReadyEvent` và project Spring Boot hợp lệ. Bean listener phù hợp cho các event **muộn**, khi context đã được khởi tạo. Nó không thể tự quay lại để nhận những event khởi động đã phát trước khi bean của nó tồn tại.

| Nhu cầu | Điểm đăng ký phù hợp |
| --- | --- |
| Nhận `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` | `addListeners` trước `run` hoặc `spring.factories` |
| Quan sát `ApplicationPreparedEvent` từ lúc rất sớm | Listener đăng ký sớm |
| Quan sát `ContextRefreshedEvent`, started/ready khi bean đã sẵn sàng | `@EventListener` hoặc `ApplicationListener` do Spring quản lý |
| Chạy việc cần hoàn tất trước ready | `ApplicationRunner` / `CommandLineRunner` |
| Thay đổi bean/context trước refresh | `ApplicationContextInitializer`, đúng hợp đồng của context |
| Quan sát application availability | `AvailabilityChangeEvent` hoặc `ApplicationAvailability` |

Nếu listener cần quan sát mọi mốc từ đầu, chọn cách đăng ký sớm, không phụ thuộc vào bean container trong constructor của chính listener.

## 6. Ví dụ chạy được: log toàn bộ timeline và mô phỏng startup failure

Ví dụ dưới dùng **Java 17**, **Spring Boot 3.3.13** và **Gradle**. Ứng dụng **non-web** để tránh log và sự kiện của embedded server làm nhiễu; vẫn dùng đầy đủ `SpringApplication` và `ApplicationContext`. Ta đăng ký một `ApplicationListener<ApplicationEvent>` trước `run` để bắt các event sớm, context event và availability event.

### 6.1. Cấu trúc thư mục

~~~text
spring-events-timeline/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/events/
    ├── EventsTimelineApplication.java
    └── TimelineListener.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'spring-events-timeline'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.events.EventsTimelineApplication'
}
~~~

Project mẫu sử dụng `spring-boot-starter` và không có `spring-boot-starter-web`; kiểu non-web được đặt rõ trong code. Bản Gradle cài đặt phải tương thích với Spring Boot 3.3. Nếu dự án có Gradle Wrapper, có thể dùng wrapper thay lệnh `gradle`.

### 6.2. Lớp chính và runner

**Tệp `src/main/java/com/example/events/EventsTimelineApplication.java`:**

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EventsTimelineApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EventsTimelineApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Quan trọng: đăng ký trước khi gọi run().
        application.addListeners(new TimelineListener());

        // Callback này xảy ra trước ApplicationContextInitializedEvent.
        application.addInitializers(context ->
                System.out.println("INIT: context initializer"));

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner demonstrateRunner() {
        return args -> {
            System.out.println("RUNNER: executed");

            // Chỉ dùng để thử nhánh lỗi khi người chạy truyền --fail-demo.
            if (args.containsOption("fail-demo")) {
                throw new IllegalStateException(
                        "Intentional startup failure");
            }
        };
    }
}
~~~

`ApplicationRunner` nhận `ApplicationArguments`, cho phép kiểm tra option `--fail-demo`. Nếu không có option, runner kết thúc bình thường. `try-with-resources` chủ động đóng context khi `run` đã trả về và mã trong `try` xong; cấu trúc này dành cho **CLI demo**. Trong ứng dụng web chạy dài, không đóng context ngay khi startup hoàn tất.

### 6.3. Listener theo dõi nhiều loại event

**Tệp `src/main/java/com/example/events/TimelineListener.java`:**

~~~java
package com.example.events;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public final class TimelineListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {

        if (event instanceof ApplicationStartingEvent) {
            print("STARTING");

        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            print("ENVIRONMENT_PREPARED");

        } else if (event instanceof ApplicationContextInitializedEvent) {
            print("CONTEXT_INITIALIZED");

        } else if (event instanceof ApplicationPreparedEvent) {
            print("PREPARED");

        } else if (event instanceof ContextRefreshedEvent) {
            print("CONTEXT_REFRESHED");

        } else if (event instanceof ApplicationStartedEvent) {
            print("STARTED");

        } else if (event instanceof AvailabilityChangeEvent<?> availability) {
            Object state = availability.getState();
            if (state == LivenessState.CORRECT) {
                print("LIVENESS_CORRECT");
            } else if (state == ReadinessState.ACCEPTING_TRAFFIC) {
                print("READINESS_ACCEPTING");
            }

        } else if (event instanceof ApplicationReadyEvent) {
            print("READY");

        } else if (event instanceof ApplicationFailedEvent) {
            print("FAILED");
        }
    }

    private static void print(String value) {
        System.out.println("EVENT: " + value);
    }
}
~~~

Các chi tiết giúp ví dụ dễ kiểm chứng:

- Listener triển khai `ApplicationListener<ApplicationEvent>` nên có thể quan sát nhiều subtype của `ApplicationEvent`. Trên thực tế nên đăng ký các listener có type cụ thể nếu chỉ cần một hoặc hai loại event.
- `instanceof AvailabilityChangeEvent<?>` được hỗ trợ trong Java 17; `getState()` có thể chứa `LivenessState` hoặc `ReadinessState`. Ta chỉ in hai trạng thái minh họa để log startup gọn và tránh trộn với event shutdown.
- Vì code không dùng web starter, nó không phát `WebServerInitializedEvent`. Khi chuyển sang web application, có thể thêm nhánh nhận event web server, nếu cần.
- Mã cố ý **không** đọc `ApplicationContext` trong `STARTING` hay `ENVIRONMENT_PREPARED`; hai mốc này chưa bảo đảm một context.
- Listener không phải Spring bean; nó được thêm trực tiếp vào `SpringApplication` trước `run`, nên bắt được những event sớm mà bean listener không thể nhận từ đầu.

### 6.4. Chạy đường thành công

Tại thư mục `spring-events-timeline`:

~~~bash
gradle bootRun
~~~

Nếu project có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows.

Bỏ qua các log framework/Gradle có thể khác nhau, **các dòng do code Java in ra trong cấu hình demo** theo thứ tự mong đợi:

~~~text
EVENT: STARTING
EVENT: ENVIRONMENT_PREPARED
INIT: context initializer
EVENT: CONTEXT_INITIALIZED
EVENT: PREPARED
EVENT: CONTEXT_REFRESHED
EVENT: STARTED
EVENT: LIVENESS_CORRECT
RUNNER: executed
EVENT: READY
EVENT: READINESS_ACCEPTING
MAIN: run returned
MAIN: context closed
~~~

Dòng `INIT: context initializer` nằm giữa prepared environment và initialized context, khẳng định `ApplicationContextInitializedEvent` được phát **sau** khi các application context initializers chạy.

Nhìn hai dấu mốc `STARTED` và `READY`, bạn có thể thấy runner nằm **giữa chúng**, đồng thời trạng thái liveness correct đến trước runner, còn readiness accepting đến sau ready.

Chương trình CLI tự đóng context khi kết thúc, nên có thể có các event shutdown khác như `ContextClosedEvent`. `TimelineListener` không in chúng. Chúng không nằm trong danh sách startup ở trên.

### 6.5. Chạy nhánh lỗi trong ApplicationRunner

Truyền một option để runner chủ động ném exception:

~~~bash
gradle bootRun --args="--fail-demo"
~~~

Những dòng tự in **trước khi framework ghi exception**:

~~~text
EVENT: STARTING
EVENT: ENVIRONMENT_PREPARED
INIT: context initializer
EVENT: CONTEXT_INITIALIZED
EVENT: PREPARED
EVENT: CONTEXT_REFRESHED
EVENT: STARTED
EVENT: LIVENESS_CORRECT
RUNNER: executed
EVENT: FAILED
~~~

Sau đó Gradle/Boot có thể hiển thị startup failure và mã thoát khác 0. Vì `application.run(args)` đã ném exception trước khi trả context, code không đi vào thân `try`, nên **không** in `MAIN: run returned` hay `MAIN: context closed`. Đường lỗi này cũng **không** có `EVENT: READY` hoặc `EVENT: READINESS_ACCEPTING`.

Lưu ý: Dòng `FAILED` minh họa listener có mặt từ sớm nên được thông báo. Nếu lỗi xuất hiện ở thời điểm rất sớm, context có thể chưa tồn tại; listener phải tránh cố lấy bean để báo lỗi. Trong code thực tế nên ghi exception qua logging an toàn, giới hạn thông tin nhạy cảm và tránh ném exception thứ hai khi đang chẩn đoán.

### 6.6. Nếu chuyển sang ứng dụng web

Để quan sát thêm web server initialized, **tạo một biến thể của project** bằng cách thay dependency starter thành:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

và trong `main` bỏ dòng:

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

Ví dụ hai dòng trên là các thay đổi **một phần** trong project mục 6, không phải chương trình riêng. Khi chạy bản web, Tomcat được Spring Boot cấu hình theo dependency mặc định và listener có thể thấy `ServletWebServerInitializedEvent` nếu bổ sung nhánh in:

~~~java
if (event instanceof ServletWebServerInitializedEvent serverEvent) {
    System.out.println(
            "EVENT: WEB_SERVER_PORT=" + serverEvent.getWebServer().getPort());
}
~~~

Đây là **đoạn minh họa bổ sung**, cần import `org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent` và gắn vào `onApplicationEvent` ở vị trí phù hợp. Không thay đổi logic của sample non-web chỉ để buộc xuất hiện một web event. Với `spring-boot-starter-webflux`, sự kiện tương ứng là `ReactiveWebServerInitializedEvent` (nếu ứng dụng dùng web server reactive).

Web event có thể nằm xen giữa `PREPARED` và `STARTED`, ở giai đoạn context refresh; không coi nó là readiness signal. Nếu muốn xác định thực tế context nào phát event trong ứng dụng phân tầng, dùng thông tin context của event.

## 7. Ba “mốc sẵn sàng” dễ nhầm

### Context đã refresh

`ContextRefreshedEvent` cho biết context refresh thành công. Phần lớn singleton non-lazy và lifecycle của bean đã được xử lý theo hợp đồng container. Tuy nhiên Spring Boot **chưa nhất thiết** chạy xong các startup runners.

### Application đã started

`ApplicationStartedEvent` xuất hiện sau refresh nhưng trước runners. Sau mốc đó, Boot phát `LivenessState.CORRECT`. Liveness là trạng thái để hạ tầng quyết định instance có hoạt động hợp lệ ở mức nội bộ; nó **không** đại diện cho quyền nhận traffic.

### Application đã ready

`ApplicationReadyEvent` xuất hiện sau khi runner hoàn thành, rồi Boot phát `ReadinessState.ACCEPTING_TRAFFIC`. Đây là trình tự thường dùng để xác định instance đã qua startup hoàn chỉnh. Readiness có thể được thay đổi trong runtime khi ứng dụng quyết định ngừng nhận traffic, ví dụ trong maintenance hoặc khi tài nguyên trọng yếu tạm không đáp ứng.

| Tín hiệu | Câu hỏi trả lời |
| --- | --- |
| `ContextRefreshedEvent` | Spring context đã refresh xong chưa? |
| `ApplicationStartedEvent` | Boot đã qua refresh để bước vào runners chưa? |
| `LivenessState.CORRECT` | Boot đánh giá nội bộ instance đã live chưa? |
| `ApplicationReadyEvent` | Các startup runners của lần chạy này đã xong chưa? |
| `ReadinessState.ACCEPTING_TRAFFIC` | Boot đang thông báo instance có thể được định tuyến traffic chưa? |

Khi chạy trong Kubernetes, nếu dùng Spring Boot Actuator và probe được bật, có thể xem liveness/readiness qua health groups. Tuy nhiên bạn vẫn cần cấu hình readiness phù hợp các yêu cầu thực tế của ứng dụng. Không coi trạng thái liveness là “kiểm tra DB” mặc định; ghép các phụ thuộc ngoài vào liveness không cẩn thận có thể gây restart hàng loạt.

## 8. Listener đồng bộ, blocking và thứ tự sự kiện

Theo mặc định, Spring phát application events thông qua cơ chế listener đồng bộ; listener chạy trong thread phát event ở nhiều trường hợp thông thường. Nếu một listener thực hiện network I/O chậm hoặc `Thread.sleep` quá lâu, nó có thể **kéo dài startup**, thậm chí làm thời điểm ready đến muộn.

Do đó:

- Listener cho `ApplicationStartingEvent`/`ApplicationEnvironmentPreparedEvent` nên rất ngắn, không phụ thuộc vào bean container hoặc hệ thống ngoài không có timeout.
- Listener xử lý một event là một callback quan sát hoặc điều chỉnh có kiểm soát, **không** phải scheduler cho vòng lặp chạy vô hạn.
- Tác vụ bắt buộc trước ready: cân nhắc `ApplicationRunner`/`CommandLineRunner` có timeout và chính sách lỗi.
- Tác vụ chạy liên tục sau startup: dùng lifecycle và executor/consumer được thiết kế riêng; không khóa thread đang phát `ApplicationReadyEvent`.
- Nếu sử dụng listener bất đồng bộ thông qua cấu hình multicaster hoặc `@Async`, phải chấp nhận thứ tự xử lý hoàn tất không còn được đảm bảo như listener đồng bộ, và exception có thể được xử lý bởi kênh khác. Không áp dụng async chỉ để làm log “nhanh hơn” mà không phân tích hậu quả.

**Thứ tự event phát** không đồng nghĩa thứ tự hoàn thành của mọi việc do listener khởi tạo. Nếu callback tạo task chạy nền, task đó có thể chưa kết thúc khi Boot phát event tiếp theo.

### Không nhầm với @Order

`@Order`/`Ordered` có thể tác động thứ tự xử lý giữa các listener cho cùng một event hoặc thứ tự runner, tùy API. Nó **không** cho phép chuyển `ApplicationReadyEvent` về trước `ApplicationStartedEvent`. Với listener có dependency quan trọng, nên cấu hình quan hệ rõ ràng, tránh dựa vào tên class hay thứ tự khai báo ngẫu nhiên.

## 9. Event truyền qua context cha/con và khả năng nhận trùng

Trong hệ thống có context hierarchy, Spring Framework có cơ chế chuyển application event từ child context đến parent context. Vì vậy listener ở context cha có thể thấy event phát từ cả context con, tạo cảm giác event bị “gửi hai lần” dù thực chất đến từ **hai nguồn context**.

Cách xử lý:

1. Xác định ứng dụng có chạy nhiều `SpringApplication` hoặc `SpringApplicationBuilder.parent(...).child(...)` không.
2. Với event chứa `ApplicationContext`, so sánh `event.getApplicationContext()` với context mà listener thuộc về.
3. Không đơn giản đếm sự kiện theo type để kết luận mọi event phải xuất hiện đúng một lần trong toàn JVM.
4. Chú ý các listener được khai báo vừa qua `spring.factories` vừa qua `addListeners` hoặc đăng ký lại ở nhiều context.

Ví dụ **minh họa** cho một listener đã có tham chiếu tới context của nó:

~~~java
if (event instanceof ContextRefreshedEvent refreshed
        && refreshed.getApplicationContext() == myContext) {
    System.out.println("Refreshed my own context");
}
~~~

Đoạn này chưa độc lập: cần biến `myContext` có kiểu `ApplicationContext` phù hợp và import `ContextRefreshedEvent`. Khi listener được đăng ký ở pha rất sớm, đừng đòi inject `myContext` trong constructor vì context chưa tồn tại.

## 10. Ghi nhận thời gian startup và quan sát lỗi

### Đo mốc có ý nghĩa

Sự kiện có thể dùng để đo khoảng cách giữa các mốc, chẳng hạn sau environment prepared, sau refresh và sau runner. Tuy nhiên:

- `System.currentTimeMillis()` chịu tác động của thay đổi đồng hồ hệ thống; đo khoảng thời gian nên dùng `System.nanoTime()` hoặc công cụ đo startup/observation phù hợp.
- Một phần thời gian khởi động diễn ra **trước** khi listener bean tồn tại. Muốn đo đủ từ sớm, đăng ký listener trước `run`.
- `ApplicationStartedEvent` đánh dấu sau refresh; thời gian đến `ApplicationReadyEvent` có thể tăng đáng kể vì runner hoặc listener xử lý nặng.
- Thời gian log event chỉ là quan sát tại một callback, **không** thay thế hoàn toàn các công cụ như `ApplicationStartup`, Java Flight Recorder hoặc Actuator startup endpoint khi cần phân tích từng bước nội bộ.

### Chẩn đoán đúng phạm vi

| Biểu hiện | Xem mốc và nguồn lỗi |
| --- | --- |
| Không nhận `STARTING` | Listener có thật sự đăng ký trước `run`? Có chạy đúng `main`? |
| Có `STARTING` nhưng không có `ENVIRONMENT_PREPARED` | Lỗi hoặc gián đoạn rất sớm; xem bootstrap logs và exception |
| Có `ENVIRONMENT_PREPARED` nhưng không có `PREPARED` | Xem tạo context, initializers, config/bean definition loading |
| Có `PREPARED` nhưng không có `CONTEXT_REFRESHED` | Xem bean creation, auto-configuration, embedded server startup |
| Có `STARTED` nhưng không có `READY` | Kiểm tra startup runners và lỗi/timeout ở giữa |
| Có `READY` nhưng chưa thấy readiness accepting | Kiểm tra listener/availability publishing và log; không suy đoán hoàn toàn từ một dòng log |
| Có `FAILED` | Đọc nguyên nhân trong exception chain; không mặc định do controller |
| Có event web server nhưng traffic bị từ chối | Xem readiness, network, service routing, security và trạng thái ứng dụng |

Nếu listener của bạn ném exception, nó có thể **làm startup thất bại** hoặc che nguyên nhân ban đầu. Trong listener chẩn đoán, nên giới hạn I/O, xử lý lỗi ghi log hợp lý và không để mã quan sát làm hệ thống kém ổn định.

## 11. Những hiểu nhầm phổ biến

**1. “ApplicationStartingEvent có Environment.”**

Không. Spring Boot phát starting event trước khi có môi trường ứng dụng được chuẩn bị; dùng environment prepared event nếu cần truy cập `ConfigurableEnvironment`.

**2. “ApplicationContextInitializedEvent nghĩa là bean đã được khởi tạo.”**

Tên “initialized” ở đây đề cập **ApplicationContext đã được chuẩn bị và initializers đã chạy**, trước khi bean definitions ứng dụng được nạp. Không tự suy ra có thể inject mọi bean.

**3. “ApplicationPreparedEvent nghĩa là context refresh xong.”**

Prepared diễn ra trước refresh. `ContextRefreshedEvent` là mốc container sau refresh, còn started và ready là mốc Spring Boot sau đó.

**4. “ApplicationStartedEvent và ApplicationReadyEvent giống nhau.”**

Started đến trước runners; ready đến sau runners. Đây là khác biệt rất quan trọng với migration/initialization cần hoàn tất trước đưa traffic.

**5. “Liveness correct đồng nghĩa readiness accepting.”**

Không. Liveness và readiness trả lời hai câu hỏi vận hành khác nhau. Một ứng dụng có thể live nhưng tạm thời chưa nhận traffic.

**6. “ApplicationFailedEvent chạy sau mọi HTTP 500.”**

Không. Event này gắn với **lỗi khởi động `SpringApplication`**; xử lý lỗi request thuộc Servlet/WebFlux handler pipeline.

**7. “Đăng ký @EventListener là đủ để thấy mọi event từ đầu.”**

Bean listener chỉ tồn tại sau khi container xử lý bean. Muốn theo dõi event sớm, dùng `SpringApplication.addListeners` trước `run` hoặc `spring.factories`.

**8. “WebServerInitializedEvent có nghĩa server đã ready cho traffic production.”**

Event này cho biết server đã được khởi tạo; readiness startup còn chờ runners và mốc `ACCEPTING_TRAFFIC`.

**9. “Một listener luôn chạy async.”**

Mặc định nhiều listener chạy đồng bộ. Chạy việc lâu trong listener có thể trì hoãn startup hoặc tác động thread phát event. Async cần được cấu hình và thiết kế có chủ đích.

**10. “Một event type luôn chỉ phát đúng một lần trên toàn JVM.”**

Nhiều context, nhiều lần `run` hoặc event bubbling trong context hierarchy có thể khiến listener nhìn thấy nhiều event cùng loại. Hãy kiểm tra nguồn context.

**11. “Ready event đảm bảo mọi dependency ngoài không bao giờ lỗi.”**

Ready đánh dấu mốc startup thành công. DB/network/cache có thể thay đổi trạng thái sau đó; các probe và chính sách retry/circuit breaker cần xử lý trong runtime.

**12. “Có thể bắt đầu tạo bean bằng getBean() ở mọi listener.”**

Trong event sớm, context chưa tồn tại hoặc chưa refresh; việc truy cập bean có thể thất bại hoặc phá thứ tự lifecycle. Chỉ sử dụng container ở mốc mà API bảo đảm phù hợp.

## 12. Bài tập thực hành

1. Chạy project mục 6. Viết lại thứ tự đầy đủ của `STARTING`, `ENVIRONMENT_PREPARED`, `CONTEXT_INITIALIZED`, `PREPARED`, `CONTEXT_REFRESHED`, `STARTED` và `READY`. Đặt hai trạng thái availability đúng vị trí.
2. Xóa dòng `application.addListeners(new TimelineListener())`. Giải thích vì sao bạn không còn log của listener chương trình và điều này **không** có nghĩa Spring Boot ngừng phát events.
3. Đăng ký `TimelineListener` bằng `META-INF/spring.factories` thay cho lời gọi `addListeners`. Kiểm tra những event sớm vẫn được ghi nhận.
4. Tạo một bean `@EventListener(ApplicationReadyEvent.class)`. Vì sao bean này nhận ready event nhưng không thể mong nhận starting event?
5. Thử `--fail-demo`. Xác định event cuối cùng trên đường startup thành công đã đạt tới, những event không xuất hiện và lý do `run` ném exception.
6. Thêm `CommandLineRunner` có log và `@Order` để quan sát thứ tự runner. Giải thích mốc Boot started/ready ở hai bên các runner.
7. Thay project thành Servlet web starter; bổ sung listener cho `ServletWebServerInitializedEvent` và in cổng thực tế. Tại sao sự kiện này không thay thế readiness?
8. Dự đoán điều gì xảy ra nếu listener cho `ApplicationEnvironmentPreparedEvent` cố gọi một Spring bean: lúc đó bean container đã sẵn sàng chưa?
9. Với Spring Actuator, cấu hình và xem liveness/readiness probe. Giải thích lý do một lần chạy vẫn live trong khi runner đang chuẩn bị nghiệp vụ.
10. Giả sử một initializer ném exception trước khi context được tạo. Listener `ApplicationFailedEvent` nên được viết như thế nào để không truy cập context null?
11. Giả sử ứng dụng tạo context cha/con. Thiết kế cách đếm `ContextRefreshedEvent` không nhầm event từ context con với event của context cha.
12. Một nhóm muốn ghi metrics về thời gian đến refresh và đến ready. Bạn sẽ chọn listener sớm, timestamp đơn điệu hoặc `ApplicationStartup` ra sao để phép đo có ý nghĩa?

## Ghi nhớ

- Trục chính: **Starting → EnvironmentPrepared → ContextInitialized → Prepared → [refresh/context/web] → Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING_TRAFFIC**.
- `ApplicationFailedEvent` là **nhánh khi startup lỗi** ở một giai đoạn nào đó, không phải một bước của đường thành công.
- `Environment` có từ environment-prepared; `ApplicationContext` có từ context-initialized, nhưng bean definitions và trạng thái refresh đến sau.
- `ContextRefreshedEvent`, `ApplicationStartedEvent` và `ApplicationReadyEvent` là **ba mốc khác nhau**.
- Listener muốn nhận event đầu tiên phải đăng ký trước `run` hoặc qua `spring.factories`; bean listener chỉ thích hợp với event phát khi context đã sẵn sàng.
- `LivenessState.CORRECT` và `ReadinessState.ACCEPTING_TRAFFIC` phản ánh hai ý nghĩa khác nhau; server bind cổng không chứng minh instance ready.
- Listener nên nhẹ, có ý thức về đồng bộ và lifecycle, tránh làm gián đoạn startup chỉ vì một bước ghi log.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — SpringApplication, Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — ApplicationStartingEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html
- Spring Boot 3.3.13 — ApplicationEnvironmentPreparedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3.13 — ApplicationContextInitializedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
- Spring Boot 3.3.13 — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
- Spring Boot 3.3.13 — AvailabilityChangeEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — Application Availability and Readiness: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
