# Kiểm thử run thực tế bằng SpringApplication với WebApplicationType.NONE

## Mục tiêu học tập

Khi kiểm thử vòng đời một ứng dụng Spring Boot, nhiều lỗi chỉ lộ ra khi chạy **đường khởi động thật**: xử lý `Environment`, tạo và refresh `ApplicationContext`, khởi tạo singleton beans, gọi lifecycle callbacks, chạy `ApplicationRunner`/`CommandLineRunner`, phát `ApplicationReadyEvent` hoặc `ApplicationFailedEvent`, rồi đóng context và giải phóng tài nguyên. Một unit test chỉ gọi constructor hoặc một method service không thể chứng minh toàn bộ luồng này.

Tuy nhiên, **kiểm thử vòng đời thực tế không bắt buộc mở HTTP server**. `SpringApplication.setWebApplicationType(WebApplicationType.NONE)` buộc Spring Boot dùng môi trường **non-web** theo cấu hình context mặc định, ngay cả khi Spring MVC/Tomcat có mặt trên classpath. Đây là cách hữu ích để chạy integration test cho application runtime mà không cần chiếm port.

Bài học thuộc **Spring Boot Application Runtime → Kiểm thử vòng đời**. Các ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.13**, **Spring Framework 6.1.x**, **JUnit 5**, **Gradle**.

Sau khi học, bạn có thể:

1. Giải thích sự khác biệt giữa một **real SpringApplication.run** và các test chỉ tạo bean hoặc mock service.
2. Hiểu chính xác `WebApplicationType.NONE` vô hiệu hóa việc tạo web application context và embedded web server, **không vô hiệu hóa Spring Boot lifecycle**.
3. Khởi động một `SpringApplication` mới trong mỗi test, cấu hình `NONE`, truyền arguments và properties riêng, rồi đóng context bằng `try-with-resources`.
4. Kiểm tra thứ tự `ApplicationStartedEvent → ApplicationRunner → ApplicationReadyEvent` trên đường startup thành công.
5. Kiểm tra lỗi từ `ApplicationRunner`: `SpringApplication.run` throw, có `ApplicationFailedEvent` và **không có** ready event trên đường thành công.
6. Quan sát `ContextClosedEvent` và xác minh cleanup sau khi đóng context.
7. Đăng ký listener **trước khi gọi run** để nhận sự kiện rất sớm hoặc failure event, thay vì chỉ dựa vào bean `@EventListener`.
8. So sánh `@SpringBootTest(webEnvironment = NONE)`, `@SpringBootTest(webEnvironment = MOCK)` và `ApplicationContextRunner`.
9. Tránh rò rỉ test contexts, thread pools, scheduler và cổng mạng; giữ test độc lập với thứ tự chạy.
10. Viết test có assertion về **bất biến vòng đời thực sự**, không dựa vào `Thread.sleep`, log tùy ý hoặc hành vi tình cờ.

## 1. “Run thực tế” nghĩa là gì?

`SpringApplication` là entry point trung tâm của Spring Boot. Với cách gọi:

~~~java
ConfigurableApplicationContext context =
        new SpringApplication(MyApp.class).run(args);
~~~

Spring Boot vẫn thực hiện các công việc thực tế của application startup:

- Tạo `SpringApplicationRunListeners` và phát các Boot startup events.
- Chuẩn bị `Environment` từ properties, command-line arguments, profiles và sources thích hợp.
- Tạo `ApplicationContext`, đăng ký configuration/bean definitions.
- Refresh context: bean instantiation, dependency injection, BeanPostProcessors, `@PostConstruct` và các khâu lifecycle phù hợp.
- Cho `SmartLifecycle` auto-start tham gia quá trình refresh.
- Phát `ApplicationStartedEvent` sau refresh.
- Chạy `ApplicationRunner` và `CommandLineRunner`.
- Phát `ApplicationReadyEvent` khi các runners đã hoàn tất thành công.
- Trả context cho caller, hoặc chuyển sang startup-failure handling nếu có lỗi.

**Khác biệt với unit test:** Những thành phần này không chỉ được “giả lập” bằng mock. BeanFactory, configuration class processing, auto-configuration conditions, event publication và runner callbacks đều được thực thi trong một `ApplicationContext` thật.

**Khác biệt với end-to-end HTTP test:** Test này **không** kiểm tra socket listener, embedded Tomcat startup, HTTP filters, servlet routing, request/response hoặc network traffic vì môi trường web bị tắt có chủ đích.

### Những mức kiểm thử thường gặp

| Kỹ thuật | Có real SpringApplication startup? | Có HTTP server? | Trọng tâm |
| --- | --- | --- | --- |
| JUnit thuần + mock dependencies | Không | Không | Logic của class/method |
| `AnnotationConfigApplicationContext` tự tạo | Có Spring bean lifecycle, nhưng không đầy đủ SpringApplication path | Không | Spring Framework bean lifecycle |
| `ApplicationContextRunner` | Có context test tập trung; không phải toàn bộ đường Boot application run | Không mặc định | Auto-configuration, conditions, bean definitions |
| `@SpringBootTest(webEnvironment = NONE)` | Có; test framework dùng SpringApplication | Không | Full application context non-web |
| **Tạo `SpringApplication` rồi gọi `run` trực tiếp** | **Có; caller chủ động điều khiển toàn bộ run và close** | Không nếu set `NONE` | Boot events, runner, startup failure, shutdown |
| `@SpringBootTest(webEnvironment = MOCK)` | Có | Không mở embedded server, nhưng có mock web environment khi web trên classpath | Spring MVC/WebFlux test context |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Có | Có, bind port ngẫu nhiên | HTTP integration thật |

Việc chọn test phụ thuộc mục tiêu. Nếu muốn kiểm tra **main lifecycle** và tác động của `SpringApplication`, cách gọi `run(...)` trực tiếp thường rõ hơn một annotation test được framework quản lý ngầm.

## 2. WebApplicationType.NONE làm gì và không làm gì?

Spring Boot có enum `org.springframework.boot.WebApplicationType` với các mode chính:

- `SERVLET`: tạo servlet-web application context phù hợp, có thể khởi động embedded web server.
- `REACTIVE`: tạo reactive-web application context.
- `NONE`: tạo non-web `ApplicationContext`.

Khi không cấu hình, Spring Boot suy ra loại web dựa trên classpath. Nếu Spring MVC xuất hiện, Boot thường suy ra `SERVLET`. Trong test lifecycle, ta có thể override tường minh:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context = app.run(args)) {
    // Kiểm thử context thật, không có HTTP server.
}
~~~

Trong thiết lập mặc định của Spring Boot 3.3, `NONE` tạo `AnnotationConfigApplicationContext` thay vì `AnnotationConfigServletWebServerApplicationContext`. Vì vậy không cần truyền `server.port=0` chỉ để tránh xung đột port: **không có embedded web server được tạo để bind port**.

### NONE không có nghĩa “không có Spring”

`NONE` **không** có nghĩa:

- Chỉ tạo object Java mà bỏ BeanFactory.
- Bỏ `@Configuration`, `@Bean`, auto-configuration hoặc dependency injection.
- Bỏ `@PostConstruct`, `SmartLifecycle` hay bean destroy callbacks.
- Bỏ `ApplicationRunner`, `CommandLineRunner` hoặc `ApplicationReadyEvent`.
- Bỏ `ApplicationFailedEvent` khi startup fail.
- Tự động mock database, filesystem, message broker hoặc cloud service.
- Tự động tắt `@Scheduled`, `@Async`, background consumers hoặc custom threads do ứng dụng tạo.
- Bỏ hết mọi web-related class trên classpath.

Nó chỉ thay **kiểu ứng dụng/context và hành vi web runtime**. Những dependency ngoài như DB/Redis/Kafka vẫn có thể được auto-configure hoặc kết nối nếu cấu hình và các conditions cho phép.

### Test mạnh hơn: cố ý giữ web starter

Để chứng minh `NONE` là một quyết định **tường minh** chứ không chỉ hệ quả vì thiếu servlet classes, project ví dụ sẽ có `spring-boot-starter-web` trên classpath nhưng vẫn ép `WebApplicationType.NONE`.

Nếu bỏ lời gọi `setWebApplicationType(NONE)`, `SpringApplication` có thể tự phát hiện `SERVLET` và khởi động Tomcat. Vì vậy **giữ lời gọi này ở cùng factory method được cả main và tests sử dụng**.

## 3. Điều gì được bảo đảm trong vòng đời Boot 3.3?

Theo Spring Boot 3.3, thứ tự event cốt lõi có thể tóm tắt:

~~~text
ApplicationStartingEvent
          |
ApplicationEnvironmentPreparedEvent
          |
ApplicationContextInitializedEvent
          |
ApplicationPreparedEvent
          |
     context refresh
          |
ApplicationStartedEvent
          |
LivenessState.CORRECT
          |
ApplicationRunner / CommandLineRunner
          |
ApplicationReadyEvent
          |
ReadinessState.ACCEPTING_TRAFFIC
          |
SpringApplication.run returns context
~~~

Những event này áp dụng cho **SpringApplication**, dù `WebApplicationType` là `NONE`. Khi không có web server, **không có WebServerInitializedEvent của một embedded server thực sự** trong quá trình khởi động non-web đó.

### Một số phân biệt rất quan trọng

- `ApplicationStartedEvent` được phát **sau refresh** và **trước runners**.
- `ApplicationReadyEvent` được phát **sau các runners** hoàn tất thành công.
- `ApplicationFailedEvent` là sự kiện của **nhánh startup failure**.
- `ContextClosedEvent` là sự kiện Spring Framework khi một context được đóng; nó không đồng nghĩa với Boot ready/failed.
- `ApplicationReadyEvent` không bảo đảm mọi **lazy bean** đã được tạo, mọi network dependency còn khỏe sau này hoặc mọi async task đã hoàn thành.
- Nếu một runner throw, `SpringApplication.run` không trả context như đường thành công; framework thực hiện failure path và cleanup khi có thể.

Trong test, nên assert các **mốc được hợp đồng bảo đảm**, không cố gắng assert từng dòng log do Spring Boot nội bộ in ra.

### Không ghép thứ tự log của tất cả bean thành một “hợp đồng”

Hai bean độc lập cùng lifecycle phase có thể có thứ tự init/start tùy implementation. Một test lifecycle thực tế không nên bắt chúng theo A-Z nếu không có dependency/phase tương ứng. Ví dụ sẽ assert thứ tự:

~~~text
started → runner → ready → context close
~~~

Đây là thứ tự từ các **mốc Boot và hoạt động test điều khiển**, không phải khẳng định mọi bean trong context có thứ tự init duy nhất.

## 4. Khi nào dùng new SpringApplication thay vì static run?

Hai cách gọi đều tạo application:

~~~java
SpringApplication.run(MyApp.class, args);
~~~

và:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

Cách thứ hai cho phép cấu hình **trước khi run**:

- `setWebApplicationType(WebApplicationType.NONE)`.
- `setBannerMode(Banner.Mode.OFF)` để giảm output không liên quan.
- `setLogStartupInfo(false)` để giảm log khởi động thông tin.
- `setAdditionalProfiles(...)` nếu kiểm thử theo profile.
- `setDefaultProperties(...)` cho những property defaults của một lần chạy.
- `addListeners(...)` để bắt event từ giai đoạn rất sớm.
- `addInitializers(...)` để thay đổi context **trước refresh** khi test yêu cầu.

**Quan trọng:** Truyền command-line args vào `run(args)` là cách thuận tiện để tách các kịch bản, chẳng hạn `--demo.fail`. Không cần thay đổi toàn cục `System.setProperty(...)` cho mỗi test.

Cũng có thể dùng `SpringApplicationBuilder(...).web(WebApplicationType.NONE)`, nhưng project chọn API `SpringApplication` trực tiếp để bám sát đề bài.

## 5. Thiết kế bộ test sao cho vừa “thật” vừa quyết định được kết quả

Bộ test sẽ kiểm tra bốn bất biến chính:

1. **Web context:** Context khởi tạo là `AnnotationConfigApplicationContext`, kể cả khi có `spring-boot-starter-web`.
2. **Successful lifecycle:** Thứ tự do code ghi nhận là `started → runner → ready`; khi caller đóng context, có thêm `closed`.
3. **Startup failure:** Runner được gọi nhưng ném exception; ứng dụng phát `ApplicationFailedEvent` và không phát `ApplicationReadyEvent` trên đường thành công.
4. **Early registration:** Một listener đã gắn bằng `app.addListeners(...)` trước `run(...)` nhìn thấy `ApplicationStartingEvent` dù lúc đó Spring beans chưa tồn tại.

### Tránh biến dữ liệu test thành global state

Không dùng một biến `static List<String> events` chung cho toàn bộ test suite. Nó có thể giữ dữ liệu qua các context và khiến JUnit fail khi chạy toàn bộ suite nhưng pass nếu chạy một test riêng.

Thay vào đó, mỗi `SpringApplication.run(...)` tạo một `StartupTrace` bean mới; mỗi test giữ tham chiếu riêng. Với event xảy ra trước context initialization hoặc khi run failure, test truyền một list riêng cho `app.addListeners(...)`.

### Dùng try-with-resources để đóng context

~~~java
try (ConfigurableApplicationContext context = app.run()) {
    // Assertions khi context active.
}
// context.close() đã được gọi.
~~~

`ConfigurableApplicationContext` implement `Closeable` nên dùng được trong `try-with-resources`. Đóng context rất quan trọng trong test vì một context không đóng có thể còn giữ thread pool, scheduled tasks, connection pool, shutdown callbacks hoặc tài nguyên test.

**Không đóng context rồi gọi `context.getBean(...)` để kiểm thử tiếp.** Nếu cần kiểm tra dấu vết sau close, lấy một reference tới object theo dõi riêng **trước khi đóng**, rồi đọc snapshot của object đó sau khi đóng.

## 6. Project runnable: Java 17 / Spring Boot 3.3.13 / JUnit 5

Project có hai file Java chính: ứng dụng và test gọi `SpringApplication.run(...)` thật. Build thêm web starter **để chứng minh NONE override auto-detection**, nhưng không mở HTTP server.

### 6.1. Cấu trúc thư mục

~~~text
real-spring-run-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/realrun/
    │   └── RealRunApplication.java
    └── test/java/com/example/realrun/
        └── RealRunApplicationTests.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'real-spring-run-test'
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
    // Cố ý có Spring MVC/Tomcat trên classpath.
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.realrun.RealRunApplication'
}
~~~

**Yêu cầu:** Java 17+ và Gradle tương thích với Spring Boot 3.3.x; Maven Central có thể cần mạng để lấy dependency ở lần build đầu. Project không bao gồm Gradle Wrapper; nếu có wrapper hãy dùng wrapper thay `gradle`.

### 6.2. Ứng dụng thật, trace bean và runner

**Tệp `src/main/java/com/example/realrun/RealRunApplication.java`:**

~~~java
package com.example.realrun;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RealRunApplication {

    public static void main(String[] args) {
        SpringApplication app = newNonWebApplication();

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "MAIN: active=" + context.isActive());
        }

        System.out.println("MAIN: context closed");
    }

    public static SpringApplication newNonWebApplication() {
        SpringApplication app =
                new SpringApplication(RealRunApplication.class);

        // Override cả khi spring-boot-starter-web có mặt.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        return app;
    }

    @Bean
    StartupTrace startupTrace() {
        return new StartupTrace();
    }

    @Bean
    ApplicationRunner demoRunner(StartupTrace trace) {
        return arguments -> {
            trace.record("runner");

            if (arguments.containsOption("demo.fail")) {
                throw new IllegalStateException(
                        "intentional runner failure");
            }
        };
    }

    public static final class StartupTrace {

        private final List<String> events =
                new CopyOnWriteArrayList<>();

        public void record(String event) {
            events.add(event);
            System.out.println("TRACE: " + event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            record("started");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            record("ready");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            record("closed");
        }
    }
}
~~~

**Giải thích từng quyết định:**

- `newNonWebApplication()` dùng chung cho `main` và test. Nếu main thay đổi cấu hình `WebApplicationType`, test sẽ kiểm tra cùng **đường khởi tạo** này thay vì một cấu hình khác.
- `setWebApplicationType(NONE)` có trước `run` nên Boot không tạo servlet web server dù web starter hiện diện.
- `@Bean StartupTrace` là một bean mới theo context. `CopyOnWriteArrayList` giúp việc snapshot thread-safe nếu một callback khác đọc trace.
- Ba method `@EventListener` quan sát sự kiện từ **context đã khởi tạo**: Started, Ready và ContextClosed.
- `ApplicationRunner` được Boot gọi đúng vị trí vòng đời. Nó in `runner` sau Started và trước Ready.
- Command-line flag `--demo.fail` được `ApplicationArguments.containsOption("demo.fail")` nhận diện. Khi có flag, runner throw exception có chủ đích.
- Dùng một runner duy nhất và một trace bean nên ví dụ không phụ thuộc vào thứ tự tùy ý giữa nhiều runners hoặc nhiều lifecycle peers.
- `main` in `active=true` **sau khi `run` trả về**. Nó không tự mở cổng hay chạy HTTP server; ngay sau đó context được đóng có chủ đích vì đây là CLI demo.

Trong ứng dụng web chạy dài hạn, bạn **không** nên tự đóng context ngay khi run trả về như demo, vì mục đích là phục vụ traffic; cách đóng ngay ở đây giúp quan sát shutdown trong test CLI.

### 6.3. JUnit test gọi SpringApplication.run thật

**Tệp `src/test/java/com/example/realrun/RealRunApplicationTests.java`:**

~~~java
package com.example.realrun;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealRunApplicationTests {

    @Test
    void realRunIsNonWebAndClosesInLifecycleOrder() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        RealRunApplication.StartupTrace trace;

        try (ConfigurableApplicationContext context = app.run()) {
            assertInstanceOf(
                    AnnotationConfigApplicationContext.class, context);
            assertTrue(context.isActive());

            trace = context.getBean(
                    RealRunApplication.StartupTrace.class);

            assertEquals(
                    List.of("started", "runner", "ready"),
                    trace.snapshot());
        }

        assertEquals(
                List.of("started", "runner", "ready", "closed"),
                trace.snapshot());
    }

    @Test
    void runnerFailureEmitsFailedEventWithoutReadyEvent() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        List<String> signals = new CopyOnWriteArrayList<>();

        app.addListeners(
                (ApplicationListener<ApplicationStartedEvent>)
                        event -> signals.add("started"),
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> signals.add("ready"),
                (ApplicationListener<ApplicationFailedEvent>)
                        event -> signals.add("failed"));

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run("--demo.fail"));

        assertTrue(
                hasMessageInCauseChain(
                        thrown, "intentional runner failure"));

        assertTrue(signals.contains("started"));
        assertTrue(signals.contains("failed"));
        assertFalse(signals.contains("ready"));
    }

    @Test
    void listenerRegisteredBeforeRunReceivesStartingEvent() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        List<String> signals = new CopyOnWriteArrayList<>();

        app.addListeners(
                (ApplicationListener<ApplicationStartingEvent>)
                        event -> signals.add("starting"));

        try (ConfigurableApplicationContext context = app.run()) {
            assertTrue(context.isActive());
        }

        assertEquals(List.of("starting"), signals);
    }

    private static boolean hasMessageInCauseChain(
            Throwable original, String fragment) {

        for (Throwable cursor = original;
                cursor != null;
                cursor = cursor.getCause()) {

            String message = cursor.getMessage();

            if (message != null && message.contains(fragment)) {
                return true;
            }
        }

        return false;
    }
}
~~~

**Điều đáng chú ý:** Đây là test gọi **`SpringApplication.run(...)` thật**, không có `@MockBean` cho runner và không chỉ tạo `AnnotationConfigApplicationContext` thủ công. Test bắt đầu Boot lifecycle và kiểm tra các điểm mốc chính thức.

### 6.4. Vì sao mỗi test được tách độc lập?

Test thứ nhất dùng một `SpringApplication` và một `StartupTrace` riêng, đóng context trong `try-with-resources`, sau đó giữ reference `trace` để kiểm tra event đóng.

Test thứ hai tạo một `SpringApplication` **mới**, đăng ký application listeners **trước** `run`, cố ý truyền `--demo.fail`. Vì `run` throw, không có context thành công để đưa vào `try-with-resources`; Spring Boot xử lý failure path của chính nó. Test chỉ cần quan sát exception và application events bên ngoài.

Test thứ ba cũng tạo app mới, chỉ ghi nhận `ApplicationStartingEvent`, một event xảy ra **trước khi có bean**. Không dùng bean `@EventListener` để bắt nó.

**Không có static mutable trace** và không phụ thuộc thứ tự chạy JUnit. Điều này cho phép chạy từng test, cả class hoặc song song theo cấu hình phù hợp mà không trộn dữ liệu từ các context.

## 7. Chạy test và chạy main

### 7.1. Chạy JUnit 5

Từ thư mục `real-spring-run-test`:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Dự án mẫu **không tạo wrapper**; dùng `gradle test` khi chỉ có Gradle đã cài.

Các test mong đợi **đều PASS**:

~~~text
RealRunApplicationTests
  realRunIsNonWebAndClosesInLifecycleOrder()       PASS
  runnerFailureEmitsFailedEventWithoutReadyEvent() PASS
  listenerRegisteredBeforeRunReceivesStartingEvent() PASS
~~~

Đây là **danh sách kỳ vọng về kết quả test**, không phải lời khẳng định Gradle in đúng định dạng trên console: Gradle/JUnit versions khác nhau có thể hiển thị phần tổng kết và stdout theo cách khác nhau. Trường hợp runner fail chủ đích có thể tạo log stack trace từ Boot nhưng **test vẫn PASS** vì dùng `assertThrows`.

**QA cần phân biệt:** `assertThrows` bắt exception trong JVM test, nên đây **không phải** test mã thoát của một Java process riêng. Muốn xác minh OS exit code, phải spawn một JVM con hoặc chạy executable JAR từ shell.

### 7.2. Chạy main theo đường thành công

~~~bash
gradle bootRun
~~~

Các dòng do **mã của project** in theo thứ tự, bỏ qua Spring Boot/Gradle logs:

~~~text
TRACE: started
TRACE: runner
TRACE: ready
MAIN: active=true
TRACE: closed
MAIN: context closed
~~~

Giải thích:

1. Context đã refresh → `ApplicationStartedEvent` → trace ghi `started`.
2. `ApplicationRunner` chạy → ghi `runner`.
3. Runner hoàn tất → `ApplicationReadyEvent` → ghi `ready`.
4. `SpringApplication.run` trả về → main ghi `active=true`.
5. Thoát `try-with-resources` → context đóng → `ContextClosedEvent` ghi `closed`.
6. Main tiếp tục → `MAIN: context closed`.

Không có dòng “Tomcat started on port ...” từ ứng dụng demo, dù `spring-boot-starter-web` có trong dependencies, bởi Boot được ép sang `NONE`.

### 7.3. Chạy main với runner failure

~~~bash
gradle bootRun --args="--demo.fail"
~~~

Những dòng **do trace của application** in ở đường lỗi thông thường:

~~~text
TRACE: started
TRACE: runner
TRACE: closed
~~~

Không có `TRACE: ready`, `MAIN: active=true` hoặc `MAIN: context closed` vì `app.run(...)` throw trước khi trả context cho main. Spring Boot có thể in thêm exception, error report hoặc stack trace; Gradle có thể đánh dấu `bootRun` fail vì process Java thoát lỗi.

**Lưu ý:** `ContextClosedEvent` được quan sát trong trường hợp runner fail **sau khi context đã refresh và có thể đóng**. Nếu lỗi xảy ra rất sớm trước khi context tồn tại, đừng mong có đúng ba dòng trên hoặc event đóng.

### 7.4. Không cần dùng server.port=0

Đặt `server.port=0` trong một **SERVLET** app yêu cầu server chọn port ngẫu nhiên; nó **vẫn mở socket**. Trong `NONE`, không có embedded web server nên việc đặt port ngẫu nhiên không có ý nghĩa kiểm thử network.

Nếu mục tiêu là **HTTP integration thực**, hãy dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc trực tiếp tạo servlet app với port phù hợp, thay vì `NONE`.

## 8. Các assertion nên có và không nên có

### Assertion mạnh

~~~java
assertInstanceOf(
        AnnotationConfigApplicationContext.class, context);

assertTrue(context.isActive());

assertEquals(
        List.of("started", "runner", "ready"),
        trace.snapshot());
~~~

Đây là các assertion nằm trong project đầy đủ. Chúng kiểm tra **context thật** và **thứ tự Boot event/runner**; không cần giả định tốc độ hoặc số mili giây giữa events.

### Assertion khi context đóng

~~~java
assertEquals(
        List.of("started", "runner", "ready", "closed"),
        trace.snapshot());
~~~

Dòng `closed` chỉ xuất hiện khi context thực sự đã đóng. Có thể thêm một bean có `@PreDestroy` với counter để kiểm tra destruction callbacks nếu nội dung bài học cần.

### Assertion về failure path

~~~java
assertTrue(signals.contains("started"));
assertTrue(signals.contains("failed"));
assertFalse(signals.contains("ready"));
~~~

Đây là mức kiểm tra ổn định hơn việc hardcode toàn bộ error log hoặc stack trace do Boot in ra. Test cố ý làm runner throw, không cần giả định error report tiếng Anh/Việt hay stack trace format.

### Những assertion dễ sai

Không nên:

- Assert chính xác mọi dòng Spring Boot startup log; log level và phiên bản thay đổi.
- Assert fixed duration “context phải start trong 200 ms” trên mọi máy CI.
- Assert mọi `SmartLifecycle` bean cùng phase start theo tên hoặc thứ tự source.
- Dựa vào `Thread.sleep(1000)` rồi giả định một event đã phát; dùng listener/latch/actual state.
- Assert HTTP port 8080 trả response, vì mode `NONE` không có HTTP server.
- Lấy một bean sau khi context đã đóng nếu bean cần BeanFactory còn active.
- Kết luận `ready` đồng nghĩa mọi dependency ngoài đã khỏe vĩnh viễn.

## 9. Tại sao @SpringBootTest(NONE) giống mà vẫn khác test tự gọi run?

Trong Spring Boot Test:

~~~java
@SpringBootTest(
        classes = RealRunApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextOnlyTest {
    // @Autowired ApplicationContext, @Test methods...
}
~~~

Đây là **snippet minh họa**, không thêm vào project runnable vì không có test body/imports đầy đủ. `@SpringBootTest(webEnvironment = NONE)` cũng tạo một context bằng `SpringApplication` và không cung cấp mock hoặc real web environment.

### Khác biệt về ownership của context

| Tiêu chí | Tự tạo SpringApplication + run | @SpringBootTest(webEnvironment = NONE) |
| --- | --- | --- |
| Ai gọi run? | Test trực tiếp | Spring TestContext framework |
| Ai đóng context? | Test trực tiếp, thường qua try-with-resources | Spring TestContext/cache lifecycle |
| Context cache giữa test methods | Không nếu mỗi test tạo app mới | Có thể cache cùng cấu hình |
| Tùy biến app trước run | Trực tiếp qua setters/listeners/initializers | Qua annotation, properties, context customizers hoặc useMainMethod |
| Quan sát event trước context creation | Dễ qua `app.addListeners` | Cần cơ chế listener phù hợp với TestContext |
| Test failure của `SpringApplication.run` | Dễ với `assertThrows` | Context load fail do framework quản lý, cần chiến lược test khác |
| Test shutdown ngay trong method | Dễ vì chủ động `close()` | Không mặc định đóng context sau từng test method |
| Có real web server | Không khi NONE | Không khi NONE |

**Lưu ý về main method:** `@SpringBootTest` không nên được hiểu là luôn gọi mã trong `public static void main` của ứng dụng. Nếu cấu hình `NONE` chỉ nằm trong main qua một setter, test dùng `@SpringBootTest` có thể cần property `spring.main.web-application-type=none` hoặc cấu hình `useMainMethod` phù hợp. Điều này đặc biệt quan trọng nếu muốn bảo đảm test chạy đúng tùy biến nằm trong entrypoint sản phẩm.

### NONE và MOCK khác nhau dù cả hai không mở port

- `MOCK` (mặc định `@SpringBootTest`) có thể tạo **mock web application context** nếu classpath hỗ trợ.
- `NONE` không có web environment, kể cả mock.
- `RANDOM_PORT` tạo web application context với embedded server thực, bind port ngẫu nhiên.
- Không dùng “không có real port” để suy luận tất cả các mode giống nhau.

### Khi nên chọn @SpringBootTest

Nếu mục tiêu là test injection, service composition và configuration với cache để test suite nhanh, `@SpringBootTest(webEnvironment = NONE)` thường đủ và đơn giản. Nếu muốn kiểm tra **failure path cụ thể của SpringApplication**, hoặc thứ tự event/close trong **một lần run riêng biệt**, cách gọi trực tiếp của bài này cho phép kiểm soát tốt hơn.

## 10. ApplicationContextRunner phù hợp với phạm vi nào?

Spring Boot test cung cấp `ApplicationContextRunner` để test auto-configuration/conditions/bean definitions theo môi trường gọn.

Snippet minh họa:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
        });
~~~

Đây là **snippet AssertJ/Spring Boot Test**, cần config và service definitions, imports. Nó hữu ích khi muốn hỏi:

- Có bean nào được tạo khi property bật?
- Một auto-configuration có lùi lại khi user bean có sẵn không?
- ConditionalOnClass/ConditionalOnProperty có đúng không?
- Một bean definition có bị lỗi khi binding không?

Nhưng **đừng nhầm** `ApplicationContextRunner` với một lần `SpringApplication.run` đầy đủ có toàn bộ Boot startup-runner and application-event path. Nếu đề bài là **“kiểm thử run thực tế bằng SpringApplication”**, hãy dùng đường run trực tiếp như project mục 6.

## 11. Ghi nhận sự kiện xảy ra rất sớm: addListeners trước run

Một bean như:

~~~java
@Component
class EarlyListener {

    @EventListener
    public void starting(ApplicationStartingEvent event) {
        System.out.println("starting");
    }
}
~~~

Đây là **mẫu không phù hợp để bắt event rất sớm**; cần imports. `ApplicationStartingEvent` phát trước khi context và beans được tạo. Bean `EarlyListener` chưa có khả năng được Spring khởi tạo để xử lý event đó.

Đúng hơn:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);

app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>)
                event -> earlyEvents.add("starting"));

app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

Đây là **snippet minh họa**, cần `MyApp`, `earlyEvents` và imports. Listener được đưa vào Boot **trước** khi startup bắt đầu; vì vậy có thể nhận `ApplicationStartingEvent`.

### ApplicationFailedEvent cũng cần cân nhắc giai đoạn

Nếu failure xảy ra trước khi context refresh xong, một `@EventListener` bean chưa chắc được tạo. Với test cố ý làm `ApplicationContextInitializer` throw, listener đăng ký sớm bằng `addListeners(...)` là cách phù hợp để quan sát failure.

Các sự kiện được publish đồng bộ theo mặc định, nhưng nếu ứng dụng cấu hình multicaster bất đồng bộ hoặc có nhiều contexts trong một hierarchy, assumptions về thread/thứ tự cần được xem lại. Với test đơn giản và default settings ở project, event trace theo thứ tự đã nêu là phù hợp.

## 12. Kiểm thử ApplicationRunner thật thay vì gọi trực tiếp method run

Nếu test chỉ thực hiện:

~~~java
new MyRunner().run(arguments);
~~~

thì mới chứng minh logic của runner. Nó không xác minh:

- Bean `ApplicationRunner` được Spring đăng ký chính xác.
- Dependency injection cho runner có thành công.
- Context refresh trước khi runner chạy.
- Boot có gọi runner tại startup không.
- `ApplicationReadyEvent` chỉ phát sau runner.
- Exception runner được đưa vào Boot startup-failure flow.
- Context được cleanup sau lỗi.

Đó là lý do ví dụ dùng `@Bean ApplicationRunner` và để `SpringApplication.run` gọi nó thật.

### Khi nào direct unit test vẫn nên tồn tại?

Nếu runner xử lý thuật toán phức tạp, nên tách logic vào service và unit test nhiều trường hợp với fake collaborators. Sau đó dùng **một số integration tests** kiểu này để xác minh wiring và contract lifecycle. Đừng biến mọi test nghiệp vụ nhỏ thành một lần khởi động full context không cần thiết.

## 13. Kiểm thử ContextClosedEvent và cleanup thực sự

Trong ví dụ, trace nhận `ContextClosedEvent`. Đây là tín hiệu Spring context đang đóng, **không tự chứng minh mọi tài nguyên đã release thành công**.

Để test một resource thật sự, có thể bổ sung bean:

~~~java
@Bean
CloseableResource resource() {
    return new CloseableResource();
}
~~~

Và:

~~~java
final class CloseableResource implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        closed.set(true);
    }

    boolean isClosed() {
        return closed.get();
    }
}
~~~

Đây là **hai snippets minh họa**, cần class, imports và destroy method thích hợp. Khi dùng làm bean, có thể khai báo `@Bean(destroyMethod = "close")` để cho Spring gọi close ở destruction. Test lấy reference trước `context.close()`, sau đó assert `isClosed() == true`.

**Chú ý thứ tự:** `ContextClosedEvent` được phát khi đóng context; nó không có nghĩa mọi `@PreDestroy`/destroy method đã hoàn tất ở ngay thời điểm listener chạy. Nếu cần assert destroy callback thực thi, hãy **đọc trạng thái sau khi `context.close()` trả về**, không chỉ trong listener.

### Cleanup khi startup fail

Với runner fail **sau refresh**, Boot có cơ chế đóng context khi xử lý startup failure, nên bean hoàn chỉnh có thể nhận destroy callback. Nhưng nếu lỗi xảy ra trong constructor/factory/`@PostConstruct` **trước khi bean init thành công**, tài nguyên do code mở một phần vẫn cần tự cleanup; không trông chờ Spring tự dọn local resource mà nó không biết tới.

### Không dùng System.exit() trong JUnit

`System.exit(code)` có thể kết thúc toàn bộ JVM đang chạy test suite. Nếu muốn kiểm tra exit code thật, khởi chạy một JVM con bằng `ProcessBuilder`; nếu chỉ muốn kiểm tra SpringApplication failure path, dùng `assertThrows(...)`.

## 14. Đảm bảo test không ảnh hưởng lẫn nhau

### Mỗi test tạo app và context mới

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

try (ConfigurableApplicationContext context = app.run()) {
    // Assertions riêng của test này.
}
~~~

Đây là cách đơn giản để không phụ thuộc vào cache giữa tests. Bất lợi: khởi động full context có thể tốn thời gian; test suite lớn nên cân bằng với `@SpringBootTest` caching hoặc test slices.

### Tránh System properties toàn cục

Nếu test A gọi:

~~~java
System.setProperty("demo.fail", "true");
~~~

rồi quên restore, test B có thể bị ảnh hưởng. Ưu tiên command-line arguments của **một lần run** hoặc `setDefaultProperties` trên chính `SpringApplication` của test.

### Chú ý các tác nhân còn sống ngoài context

- Thread tự tạo bằng `new Thread` có thể không được Spring dừng.
- Executor do bean quản lý cần stop/destroy hook phù hợp.
- Scheduler `@Scheduled` có thể tạo công việc ngoài ý muốn.
- Kafka/RabbitMQ listeners có thể tự mở kết nối nếu app thật có dependency và config.
- Flyway/Liquibase hoặc initializer có thể tự kết nối DB.
- Static caches, singleton ngoài Spring và global registries có thể rò state giữa các lần run.

`NONE` **không tự mock hay tắt** các hành vi trên. Hãy cấp fake/test beans hoặc profiles phù hợp, nhưng không thay thế chính đối tượng lifecycle bạn muốn kiểm thử.

### Tránh chạy full context nhiều lần không cần thiết

Nếu có hàng trăm logic-only tests, dùng JUnit thuần hoặc `ApplicationContextRunner` cho phần lớn và dành một số test `SpringApplication.run` cho các hợp đồng vòng đời chính. Đây là trade-off giữa tính thực tế và tốc độ CI.

## 15. Test dữ liệu properties, args và profiles trong NONE

### Command-line options

Với runner:

~~~java
if (arguments.containsOption("demo.fail")) {
    throw new IllegalStateException("intentional runner failure");
}
~~~

Tham số `--demo.fail` được parse bởi `ApplicationArguments`. Test không cần viết resource file hay thay state global.

### Set default properties trên app của test

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

app.setDefaultProperties(
        Map.of("demo.feature.enabled", "true"));
~~~

Đây là snippet, cần `java.util.Map`. Default properties có độ ưu tiên thấp hơn một số property sources khác; nếu test cần override chắc chắn, chọn command-line option hoặc cơ chế test property phù hợp.

### Profiles

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

app.setAdditionalProfiles("test");
~~~

Đây là snippet sử dụng SpringApplication API. Profile ảnh hưởng bean conditions và configuration; không cần biến toàn JVM để bật profile. Nhưng phải hiểu ứng dụng thật có thể dùng `@Profile`/conditional beans cần giả lập resource.

### Environment và readiness

Một assert property chỉ cho thấy `Environment` nhận dữ liệu, không chứng minh một dependency ngoài hoạt động. Nếu cần startup gate thật, tạo một runner hoặc lifecycle component kiểm tra điều kiện và assert sự kiện ready/failure theo contract.

## 16. Một số tình huống test cần tách

### Tình huống A — Test bean init fail

Một bean có `@PostConstruct` ném exception trước refresh kết thúc. Khi đó **không nên** assert đã có `ApplicationStartedEvent`; Boot có thể phát `ApplicationFailedEvent` rất sớm. Đăng ký listener bằng `app.addListeners(...)` trước run.

### Tình huống B — Runner fail sau refresh

Đây chính là mode `--demo.fail` của project. `ApplicationStartedEvent` đã xảy ra nhưng `ApplicationReadyEvent` chưa xảy ra, và run sẽ throw. Test có thể assert dấu hiệu này.

### Tình huống C — Một bean `SmartLifecycle.start()` fail

Nếu auto-start trong refresh ném exception, context có thể chưa hoàn tất `refresh`. Vì vậy đường event khác với runner fail. Bean cần rollback những resource đã mở trong `start()`; không chỉ dựa vào shutdown callback sau đó.

### Tình huống D — Runtime failure sau ready

Khi `SpringApplication.run` đã trả context, một HTTP handler hoặc message consumer throw ở runtime **không tự động** đi qua startup-failure path. Nếu muốn test những lỗi đó, cần test error handlers, retry/DLQ, availability hoặc service logic theo technology tương ứng.

### Tình huống E — CLI kết thúc ngay sau startup

Một non-web CLI có thể chạy runner rồi main đóng context và thoát. Không nên diễn giải việc “thoát ngay” là startup failure nếu exit code 0 và các nhiệm vụ cần thiết đã hoàn tất.

## 17. Khi cần kiểm tra SmartLifecycle trong cùng project

`SmartLifecycle` cho phép một bean auto-start trong refresh và stop khi context đóng.

Một class minh họa:

~~~java
final class ProbeLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là **snippet class minh họa**, cần import `org.springframework.context.SmartLifecycle`. Trong Spring Framework 6.1, `SmartLifecycle` có default implementations phù hợp cho các method còn lại, nhưng production component nên xử lý `stop(Runnable callback)` đúng contract khi shutdown có công việc bất đồng bộ.

Nếu thêm bean lifecycle vào project, có thể kiểm tra `start` xảy ra trước Boot `ApplicationStartedEvent` và `stop` xảy ra trước khi context close hoàn tất. Tuy nhiên, **không** assert thứ tự tuyệt đối giữa hai bean độc lập có cùng phase; phase/dependency mới định nghĩa ràng buộc.

**Một giới hạn:** Một component đặt `running=true` ngay khi submit một kết nối async chưa chắc đã sẵn sàng nghiệp vụ. Kiểm thử lifecycle “start được gọi” khác kiểm thử “remote dependency thật sự ready”.

## 18. Troubleshooting: những dấu hiệu test không đúng mục tiêu

### Tomcat được khởi động dù test kỳ vọng NONE

Kiểm tra:

1. Test có thật sự gọi `newNonWebApplication()` không?
2. Có tạo một `SpringApplication.run(MyApp.class)` **khác** không dùng setter không?
3. Test đã dùng `@SpringBootTest` với cấu hình web default thay vì NONE?
4. Có một application context factory/custom bootstrap thay đổi semantics không?
5. Classpath có Spring MVC nên Boot auto-detect SERVLET khi quên `setWebApplicationType`?

### Test bị treo sau khi assertions kết thúc

Có thể còn thread không daemon, timer, executor hoặc context chưa đóng. Kiểm tra:

- `try-with-resources` có chạy đến close không?
- Bean nào mở thread riêng?
- `@Scheduled` hoặc consumer nào còn hoạt động?
- `SmartLifecycle.stop(Runnable)` có gọi callback khi hoàn tất không?
- Có task không phản hồi interrupt không?
- Có context thứ hai bị tạo và chưa đóng không?

`NONE` không đảm bảo JVM sẽ thoát nếu bạn tự tạo non-daemon thread không được quản lý.

### Context thất bại vì database dù test không dùng database

Nếu dependency/configuration kích hoạt DB auto-configuration, context có thể cần DataSource, credentials hoặc migration. `NONE` chỉ bỏ web runtime; nó không loại trừ DB conditions. Test nên:

- Dùng test profile/config cụ thể.
- Cấp fake in-memory database nếu mục tiêu là lifecycle.
- Dùng các auto-configuration exclusions có chủ đích khi DB nằm ngoài phạm vi test.
- Không tắt ngẫu nhiên mọi phần init khiến test trở thành một context khác hẳn ứng dụng thật.

### Test thấy Started nhưng không thấy Ready

Kiểm tra startup runners, lỗi trong runner hoặc một runner bị chặn vô hạn. `ApplicationStartedEvent` xuất hiện **trước** runner. Nếu runner throw, không có ready event thành công.

### Test failure không có ContextClosedEvent

Nếu lỗi quá sớm và context chưa được tạo/refresh, event đóng có thể không phát như trong runner failure. Đừng assert sự kiện không được hợp đồng bảo đảm cho mọi vị trí lỗi.

### Test pass khi chạy riêng nhưng fail khi chạy cả suite

Thường liên quan static mutable state, system properties, context cache, port dùng chung, parallel tests, file fixtures hoặc resource leaks. Mẫu test này giữ trace theo từng context, không mở web port và không yêu cầu thứ tự test.

### Test không thấy ApplicationStartingEvent ở bean

Đó là hành vi hợp lý: event xảy ra trước bean creation. Hãy dùng `app.addListeners(...)` hoặc registration mechanism hỗ trợ sớm.

### Test dùng @SpringBootTest và không thấy main customizations

Spring TestContext không nhất thiết gọi method `main` của ứng dụng theo cách bạn viết. Dùng `@SpringBootTest(useMainMethod = ...)` khi có nhu cầu/phiên bản hỗ trợ, cấu hình property `spring.main.web-application-type=none`, hoặc tạo `SpringApplication` và gọi `run` trực tiếp như đề bài.

## 19. Kiểm thử sau khi context.close trả về

Một test vòng đời chất lượng không chỉ thấy event `closed` mà còn cần xác minh tài nguyên được giải phóng.

Ví dụ kiểm tra resource bean:

~~~java
CloseableProbe resource;

try (ConfigurableApplicationContext context = app.run()) {
    resource = context.getBean(CloseableProbe.class);
    assertFalse(resource.isClosed());
}

assertTrue(resource.isClosed());
~~~

Đây là **snippet test minh họa**, cần khai báo bean `CloseableProbe` với destroy method và import assertions. Nó phân biệt:

- **Event đã phát:** context bắt đầu đóng.
- **Destroy callback đã chạy:** bean tự dọn.
- **Resource bên ngoài thật sự release:** cần logic hoặc quan sát API tương ứng, không chỉ boolean.

Nếu cần chứng minh không còn task pending hoặc thread sống, hãy dùng `CountDownLatch`, `Future`/`awaitTermination` với timeout; không dùng `Thread.sleep` rồi suy từ thời gian.

## 20. Những lỗi phổ biến

**1. “WebApplicationType.NONE bỏ toàn bộ Boot lifecycle.”** Sai; chỉ tắt web runtime, vẫn chạy context/beans/events/runners.

**2. “Có spring-boot-starter-web thì bắt buộc khởi động Tomcat.”** Sai khi `SpringApplication` được đặt `NONE` tường minh.

**3. “Không mở port nghĩa là không tạo SpringApplication thật.”** Sai; SpringApplication có thể chạy full non-web lifecycle.

**4. “@SpringBootTest mặc định luôn tạo web server thật.”** Sai; default `MOCK` không mở embedded server nhưng có thể tạo mock web environment.

**5. “@SpringBootTest NONE và MOCK giống nhau.”** Sai; NONE không tạo web environment, MOCK có thể tạo mock web context.

**6. “Chỉ gọi runner.run() là test được SpringApplication lifecycle.”** Không; nó bỏ BeanFactory, Boot event order, failure handling và context close.

**7. “ApplicationStartedEvent chứng minh runner đã chạy xong.”** Sai; runner xảy ra **sau** Started.

**8. “ApplicationReadyEvent được phát ngay cả khi runner throw.”** Không trong đường startup thành công của Boot.

**9. “ApplicationFailedEvent chỉ có nếu HTTP server không bind được port.”** Sai; nhiều startup exceptions khác có thể gây failure.

**10. “Bean @EventListener nhận được ApplicationStartingEvent.”** Không đáng tin, vì sự kiện phát trước bean được tạo.

**11. “Không cần đóng context trong JUnit.”** Sai; context có thể giữ thread/pool/files/listeners.

**12. “ContextClosedEvent đồng nghĩa @PreDestroy đã hoàn tất ngay tại thời điểm event.”** Sai; lifecycle destruction tiếp tục sau event.

**13. “NONE tự mock database, Kafka và cloud SDK.”** Không; các dependencies khác vẫn có thể init thực.

**14. “setWebApplicationType(NONE) có nghĩa mọi bean web tự bị xóa.”** Không; chỉ các auto-configurations phụ thuộc web conditions được xử lý theo non-web; user beans vẫn theo cấu hình của chúng.

**15. “server.port=0 tương đương NONE.”** Không; port 0 là mở một embedded server ở port ngẫu nhiên khi là web app.

**16. “Lần run thứ hai dùng chung trace của lần đầu là bình thường.”** Không nếu test mong context độc lập; tránh static state và global registries.

**17. “Chỉ cần test expected stack trace text.”** Dễ brittle; assert event, exception type/cause và trạng thái.

**18. “assertThrows trong test nghĩa là OS nhận exit code khác 0.”** Không; JUnit bắt exception trong JVM test, không tạo exit code của process riêng.

**19. “@SpringBootTest luôn gọi main method.”** Không mặc định; cần xem `useMainMethod`/entrypoint policy.

**20. “Có Ready nghĩa là mọi lazy bean đều hợp lệ.”** Không; bean lazy có thể fail ở lần sử dụng đầu.

**21. “Test @Scheduled trong NONE sẽ tự tắt.”** Không; scheduler có thể hoạt động nếu enabled và bean được đăng ký.

**22. “Chỉ thấy ContextClosedEvent là chứng minh executor terminated.”** Không; cần kiểm tra task shutdown/callback.

**23. “Log thứ tự hai bean cùng phase là API contract.”** Không; chỉ assert phase/dependency được bảo đảm.

**24. “Thread.sleep trong JUnit làm test lifecycle ổn định.”** Không; dùng listener/latch/timeout-aware assertions.

**25. “Test run thật luôn tốt hơn unit test ở mọi cấp.”** Không; test full context nặng hơn, nên kết hợp nhiều cấp kiểm thử.

## 21. Bài tập thực hành

1. Tại sao `WebApplicationType.NONE` vẫn cho phép `ApplicationRunner` chạy?
2. Có `spring-boot-starter-web` trên classpath, vì sao project mẫu vẫn tạo non-web `AnnotationConfigApplicationContext`?
3. Phân biệt `NONE` và `server.port=0`.
4. Giải thích thứ tự `started → runner → ready` trong trace.
5. Vì sao `ContextClosedEvent` chỉ được test sau khi thoát `try-with-resources`?
6. Chạy `gradle test`. Ba test cùng kiểm tra những hợp đồng nào và có phụ thuộc thứ tự JUnit không?
7. Chạy `gradle bootRun`. Vì sao main in `active=true` sau trace ready?
8. Chạy `gradle bootRun --args="--demo.fail"`. Vì sao không xuất hiện ready hoặc main success?
9. Đăng ký listener `ApplicationFailedEvent` trước run. Tại sao cách này quan sát được failure cả khi bean listener chưa được khởi tạo?
10. Thêm một `ApplicationContextInitializer` cố ý throw. So sánh các events với runner failure.
11. Tại sao một listener `@EventListener(ApplicationStartingEvent.class)` có thể không bao giờ được gọi?
12. Tạo một bean có `@PostConstruct` ghi trace và kiểm tra nó trước `ApplicationStartedEvent`.
13. Tạo một `SmartLifecycle`, assert start trước Started, stop trước context close trả về.
14. Nếu hai bean cùng phase, có nên assert thứ tự chúng theo tên không? Khi cần thứ tự, dùng cơ chế nào?
15. Thêm `CloseableProbe` bean có `destroyMethod="close"`; assert trạng thái trước/sau `context.close`.
16. Thay `NONE` bằng `SERVLET` và đặt `server.port=0` trong sandbox. Loại context và hành vi bind cổng khác thế nào?
17. Dùng `@SpringBootTest(webEnvironment = NONE)` thay direct run. Ai sở hữu context và khi nào close?
18. Vì sao `@SpringBootTest(MOCK)` không thay thế bài test non-web khi mục tiêu là không có web environment?
19. Dùng `ApplicationContextRunner` để test `@ConditionalOnProperty`; vì sao không dùng nó làm bằng chứng toàn bộ Boot event order?
20. Tạo hai lần `SpringApplication.run` trong một test, đóng từng context, assert trace instances khác nhau.
21. Test một bean cần database nhưng DB không có. `NONE` có tự giải quyết lỗi dependency đó không?
22. Khi test có external thread, assert thế nào để không leak task sau close?
23. Vì sao không nên gọi `System.exit` từ runner khi chạy JUnit?
24. Nếu cần đo process exit code của startup failure, hãy thiết kế test dùng `ProcessBuilder` tạo JVM con.
25. Viết một integration test không phụ thuộc logs, kiểm tra event order từ trace và sự kiện failure bằng listeners.
26. Nếu bật lazy initialization, một bean lỗi có thể vẫn không được tạo trước ready không?
27. Một app chỉ cần test logic service. Khi nào unit test thuần hữu ích hơn full `SpringApplication.run`?
28. Tại sao test class có static mutable events list dễ fail khi test suite chạy song song?
29. Thêm một property bằng `app.setDefaultProperties(...)` trong test riêng, xác minh không làm thay đổi test khác.
30. Nêu checklist để chứng minh “run thực tế, non-web, có startup và cleanup đầy đủ” cho một Spring Boot CLI application.

## Ghi nhớ

- `SpringApplication.setWebApplicationType(WebApplicationType.NONE)` **tắt web application runtime**, không tắt Spring Boot context, beans, lifecycle events hoặc runners.
- **Real run test** gọi `SpringApplication.run(...)`, nhận `ConfigurableApplicationContext` thật, assert khi active và **đóng context** có chủ đích.
- Trong Spring Boot 3.3: **Started → runners → Ready** trên startup thành công; runner throw dẫn đến startup failure và không có Ready theo đường thành công.
- Muốn quan sát event **trước khi context tồn tại**, đăng ký bằng `app.addListeners(...)` trước `run`.
- `@SpringBootTest(webEnvironment = NONE)` cũng là non-web Boot test, nhưng context thường do Spring TestContext quản lý và có thể được cache, khác việc tự tạo/đóng context trong từng method.
- `NONE` không tự mock DB, Kafka, schedulers, external APIs, thread pools hoặc security/validation.
- `ContextClosedEvent` là một mốc đóng context, **không phải bằng chứng mọi external resource đã dừng**; test destroy callbacks và termination khi cần.
- Không dùng `System.exit` trong JUnit hoặc `Thread.sleep` để suy đoán event order.
- Kết hợp full run integration tests với unit tests, context-runner tests và HTTP integration tests đúng phạm vi.

### Tài liệu tham khảo

- Spring Boot 3.3 — SpringApplication, Web Environment, Application Events and Runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Testing Spring Boot Applications, WebEnvironment NONE/MOCK/RANDOM_PORT: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — SpringApplication Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — WebApplicationType Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 — ApplicationArguments Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — SpringBootTest Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Framework 6.1 — ConfigurableApplicationContext: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework 6.1 — AnnotationConfigApplicationContext: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html
- Spring Framework 6.1 — ContextClosedEvent: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/ContextClosedEvent.html
- JUnit 5 — User Guide: https://junit.org/junit5/docs/current/user-guide/
