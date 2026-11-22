# Kiểm thử initializer hoặc listener mà không cần chạy toàn ứng dụng Spring Boot

## 1. Mục tiêu: kiểm chứng hành vi vòng đời với phạm vi nhỏ nhất

Một ứng dụng Spring Boot thường có code can thiệp vào vòng đời khởi động và dừng, chẳng hạn:

- `ApplicationContextInitializer` đặt default properties, profiles hoặc đăng ký infrastructure trước `refresh()`.
- `ApplicationListener<ApplicationReadyEvent>` ghi log, cập nhật một trạng thái nội bộ hoặc thông báo khi Boot phát event ready.
- `ApplicationListener<ContextRefreshedEvent>` phản ứng khi một Spring context được refresh.
- `@EventListener` khai báo method nhận sự kiện thông qua Spring event infrastructure.
- Listener đăng ký rất sớm qua `SpringApplication.addListeners(...)` để nhận những `SpringApplicationEvent` phát trước khi bean container sẵn sàng.

Một phản xạ dễ gặp là viết `@SpringBootTest` cho tất cả các tình huống. Điều đó thường tạo nhiều beans, đọc configuration của ứng dụng, kích hoạt auto-configuration, đôi khi kết nối database hoặc network, làm test chậm và có nhiều nguyên nhân lỗi không liên quan đến initializer/listener đang kiểm tra.

**Không phải mọi kiểm thử lifecycle đều cần gọi `SpringApplication.run()`.** Nên tách:

1. **Unit test thuần:** tạo initializer/listener như object Java và gọi method trực tiếp.
2. **Kiểm thử context tối giản:** dùng `GenericApplicationContext` hoặc `AnnotationConfigApplicationContext` để kiểm tra `refresh`, event multicaster, dependency injection và cleanup.
3. **ApplicationContextRunner:** tạo một context nhỏ có cấu hình được kiểm soát, gọi initializer, ghi đè properties, kiểm tra startup failure rồi tự đóng context.
4. **Integration test đầy đủ:** chỉ khi phải chứng minh chính Spring Boot phát event đúng thứ tự, chạy runner, auto-configuration, web server, readiness hoặc startup failure thật.

Bài học sử dụng **Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x**. Có ví dụ Gradle hoàn chỉnh, một chương trình chỉ dựng context nhỏ và các bài kiểm thử JUnit 5 dùng AssertJ. Các ví dụ chính **không gọi `SpringApplication.run()` hoặc `@SpringBootTest`**.

## 2. Phân biệt đối tượng kiểm thử với hạ tầng phát sự kiện

Đối tượng cần test có thể là:

```java
public final class ModeInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        // Tùy chỉnh Environment trước refresh.
    }
}
```

hoặc:

```java
public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // Phản ứng khi có event tương ứng.
    }
}
```

Hai đoạn trên là **skeleton**, không chạy độc lập vì thiếu nội dung method và imports. Các class hoàn chỉnh sẽ có ở mục 9.

Bài kiểm thử phải trả lời chính xác **muốn chứng minh điều gì**:

| Câu hỏi | Mức test phù hợp |
| --- | --- |
| Initializer có thêm property mặc định không? | Gọi `initialize(context)` trên context chưa refresh |
| Initializer có không ghi đè property đã cấu hình? | Unit test với `MapPropertySource` và thứ tự ưu tiên |
| Initializer có từ chối cấu hình sai? | Unit test exception hoặc `ApplicationContextRunner` |
| Listener biến event thành đúng thông điệp không? | Gọi `onApplicationEvent(event)` trực tiếp |
| Spring event bus có chuyển event tới listener đã đăng ký? | `GenericApplicationContext`, `publishEvent` |
| Method có `@EventListener` có được phát hiện không? | `AnnotationConfigApplicationContext` đã `refresh` |
| Boot có tự phát `ApplicationReadyEvent` sau runners không? | Integration test có `SpringApplication` |
| Listener đăng ký trước context có nhận event rất sớm không? | Test đường đăng ký của `SpringApplication`, không chỉ gọi method |
| Web readiness/health endpoint hoạt động đúng không? | Test slice hoặc integration web phù hợp |

**Tránh khẳng định quá mức:** unit test một listener nhận event **không chứng minh** Boot thực tế sẽ đăng ký và phát event đó trong production. Ngược lại, test integration đầy đủ thường không cần thiết nếu chỉ muốn chứng minh một chuỗi property được thêm đúng.

## 3. Lifecycle của Spring Boot và thời điểm của initializer/listener

Spring Boot 3.3 phát các mốc chính theo trình tự tổng quát:

```text
SpringApplication.run(...)
        |
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
Tạo ConfigurableApplicationContext
        |
ApplicationContextInitializer.initialize(context)
        |
ApplicationContextInitializedEvent
        |
Nạp bean definitions
        |
ApplicationPreparedEvent
        |
ApplicationContext.refresh()
        |
ContextRefreshedEvent
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
SpringApplication.run(...) trả context

Nếu startup lỗi:
        |
ApplicationFailedEvent theo failure path
```

Các mốc này không có nghĩa tất cả đều được `GenericApplicationContext.refresh()` tự phát.

### 3.1. ApplicationContextInitializer chạy trước refresh

`ApplicationContextInitializer<C extends ConfigurableApplicationContext>` có method:

```java
void initialize(C applicationContext);
```

Initializer được dùng để cấu hình context **trước khi `refresh()`**, ví dụ thêm `PropertySource`, bật profile, đăng ký definitions khi loại context hỗ trợ.

Ở thời điểm đó, **không nên đòi hỏi mọi singleton đã được tạo** hoặc dùng `context.getBean(MyService.class)` như thể app đang ready. Một unit test tốt có thể kiểm tra behavior mà **không refresh context**, thậm chí không có bean definition nào.

### 3.2. @EventListener và ApplicationListener không giống nhau về đăng ký

- Một object implement `ApplicationListener<E>` có thể nhận event nếu bạn gọi `onApplicationEvent` trực tiếp, hoặc nếu đăng ký nó với `context.addApplicationListener(listener)` trước khi `publishEvent`.
- Một method được gắn `@EventListener` cần event-listener method processor của Spring nhận diện sau khi bean được đưa vào một context phù hợp và context đã xử lý annotation configuration. Tạo object bằng `new` rồi gọi `context.publishEvent(...)` **không tự đăng ký method đó**.
- Những early Boot events có thể được phát **trước khi context được tạo**, nên một bean `@Component` hoặc `@EventListener` chưa tồn tại để nhận. Cần đăng ký sớm bằng `SpringApplication.addListeners(...)`/`SpringApplicationBuilder.listeners(...)` hoặc cơ chế `spring.factories` khi cần bảo đảm wiring từ lúc bắt đầu.

### 3.3. Simulate event không làm Boot thực sự ready

Bạn có thể tạo `ApplicationReadyEvent` trực tiếp bằng constructor Spring Boot 3.3:

```java
new ApplicationReadyEvent(
        new SpringApplication(DemoClass.class),
        new String[0],
        context,
        Duration.ofMillis(10));
```

Đây là **snippet** với `context` là `ConfigurableApplicationContext` có thật, `DemoClass` là class Java tùy dự án. Nó phục vụ kiểm tra listener; nó **không chạy runners, không khởi động web server, không phát availability state do Boot quản lý và không chứng minh readiness thực tế**.

Đây là ranh giới quan trọng nhất giữa **test handler** và **test lifecycle orchestration**.

## 4. Unit test initializer bằng GenericApplicationContext

`GenericApplicationContext` thuộc Spring Framework và có thể được tạo bằng `new`. Trước khi gọi `refresh()`, bạn đã có một context object và có thể thao tác `Environment`.

Ví dụ initializer đặt một default configuration:

```java
@Override
public void initialize(ConfigurableApplicationContext context) {
    context.getEnvironment().getPropertySources().addLast(
            new MapPropertySource(
                    "demo-defaults",
                    Map.of("demo.mode", "safe")));
}
```

Đây là method minh họa trong class initializer. `addLast` đặt property source ở mức ưu tiên thấp; một property được khai báo sớm hơn trong các sources (ví dụ cấu hình dành cho test) vẫn có thể thắng.

### 4.1. Test không refresh

```java
try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    new ModeInitializer().initialize(context);

    assertThat(context.getEnvironment()
            .getProperty("demo.mode")).isEqualTo("safe");
    assertThat(context.isActive()).isFalse();
}
```

Đây là snippet trong JUnit test với imports phù hợp. Mấu chốt là **`initialize` được gọi trực tiếp và context chưa refresh**, nên không có việc boot cả ứng dụng.

Để kiểm tra **precedence**, tạo một `MapPropertySource` với giá trị đã được cung cấp trước:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "test-override",
                Map.of("demo.mode", "fast")));

new ModeInitializer().initialize(context);

// Kỳ vọng: fast, không bị default safe ghi đè.
```

Ở đây `addFirst` đặt source của test lên ưu tiên cao. Nếu initializer lại dùng `addFirst` và ghi cùng tên property, nó có thể vô ý phá vỡ quy tắc “chỉ cung cấp default”.

### 4.2. Test lỗi cấu hình

Nếu initializer có contract không chấp nhận giá trị khác `safe` hoặc `fast`, unit test nên assert:

- Đúng **loại exception**.
- Thông báo lỗi hữu ích nhưng không lộ secret.
- Context **chưa refresh**.
- Không có side effect mở database/socket hoặc tạo executor.

Đừng ép test phải khởi động web server để kiểm tra một `IllegalArgumentException` phát ra bởi initializer.

### 4.3. Initializer và bean registration

Một số initializer gọi `context.getBeanFactory()` hoặc đăng ký bean definitions khi context phù hợp. Có thể test với `GenericApplicationContext` hoặc `AnnotationConfigApplicationContext`, nhưng **đừng giả định mọi subtype context có thể refresh nhiều lần**. `GenericApplicationContext` thường chỉ refresh một lần; nếu test cần một lần chạy mới, tạo instance mới và đóng instance cũ.

## 5. ApplicationContextRunner cho cấu hình có kiểm soát

Spring Boot cung cấp `org.springframework.boot.test.context.runner.ApplicationContextRunner` trong `spring-boot-test`.

Nó giúp:

- Tạo một **context nhỏ**, mặc định non-web.
- Đưa vào initializer bằng `withInitializer(...)`.
- Đưa properties bằng `withPropertyValues(...)`.
- Đăng ký vài beans/configuration cần thiết thay vì scan toàn project.
- Chạy callback `run(context -> ...)` sau khi refresh.
- **Tự đóng** context sau callback.
- Xem startup failure nếu initializer/configuration ném exception.

Ví dụ:

```java
new ApplicationContextRunner()
        .withInitializer(new ModeInitializer())
        .withPropertyValues("demo.mode=fast")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        });
```

Đây là snippet JUnit/AssertJ; phần mã hoàn chỉnh ở mục 9.

### 5.1. run không bằng SpringApplication.run

`ApplicationContextRunner.run(...)` tạo và **refresh** một context, nhưng không thực hiện toàn bộ orchestration của `SpringApplication.run(...)`: không tự chạy mọi Boot auto-configuration, runners, web server hay publish `ApplicationReadyEvent`. Nó chỉ đưa vào những configurations và beans bạn đã đăng ký với runner.

Điều này là **ưu điểm cho test cô lập**, nhưng giới hạn kết luận phải được nêu chính xác.

### 5.2. prepare thay cho run khi chưa muốn refresh

Spring Boot 3.3 cũng có `ApplicationContextRunner.prepare(...)`. Khác với `run(...)`, `prepare(...)` **chưa refresh** context đã chuẩn bị. Nó phù hợp khi bạn chỉ muốn quan sát state trước refresh, với điều kiện đối tượng test không cần BeanFactory lifecycle hoàn chỉnh.

Cũng như `run`, runner quản lý đóng context khi callback kết thúc. Đừng lưu reference context của callback rồi tiếp tục gọi `getBean` sau đó.

### 5.3. Test initializer thất bại

Một initializer có thể ném exception vì cấu hình không hợp lệ. Khi dùng runner, test có thể kiểm tra:

```java
new ApplicationContextRunner()
        .withPropertyValues("demo.mode=broken")
        .withInitializer(new ModeInitializer())
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasMessageContaining(
                            "demo.mode must be safe or fast");
        });
```

Đây là **snippet minh họa**, phụ thuộc error-handling của runner, AssertJ và ModeInitializer trong ví dụ. Nếu bạn chỉ cần test contract ném exception, gọi `initialize` trực tiếp thường đơn giản và dễ hiểu hơn. Không được suy luận từ context runner failure rằng `ApplicationFailedEvent` của Spring Boot đã được phát: runner không chạy `SpringApplication`.

### 5.4. Khi cần web context nhưng không chạy server

Spring Boot còn có `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` cho auto-configuration phụ thuộc loại web context. Chúng vẫn là công cụ **test context nhỏ**, không đồng nghĩa khởi chạy embedded web server đầy đủ.

Đối với initializer thuần `Environment`, nên dùng `GenericApplicationContext` hoặc `ApplicationContextRunner` trước; không chọn web runner chỉ vì application thực tế là REST service.

## 6. Unit test một ApplicationListener mà không có Spring container

Một listener chỉ chuyển đổi event thành hành động đơn giản có thể nhận dependencies qua constructor:

```java
public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    private final Consumer<String> sink;

    public ReadySummaryListener(Consumer<String> sink) {
        this.sink = sink;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        String mode = event.getApplicationContext()
                .getEnvironment()
                .getProperty("demo.mode", "unset");
        sink.accept("READY_MODE=" + mode);
    }
}
```

Đây là class minh họa đầy đủ phần logic nhưng cần imports và package; mã hoàn chỉnh ở mục 9. `Consumer<String>` cho phép test truyền `List::add`, không cần gửi HTTP, mở database hoặc khởi động LoggingSystem.

Unit test:

```java
List<String> reports = new ArrayList<>();
ReadySummaryListener listener =
        new ReadySummaryListener(reports::add);

listener.onApplicationEvent(syntheticReadyEvent(context));

assertThat(reports).containsExactly("READY_MODE=safe");
```

Đây là snippet có `context` đã được tạo/refreshed; helper `syntheticReadyEvent` được định nghĩa trong test hoàn chỉnh. Trong kiểm thử này, bạn **gọi listener trực tiếp**, vì vậy chỉ khẳng định handler xử lý dữ liệu đúng.

### 6.1. Không dùng mock phức tạp nếu chỉ cần Java object đơn giản

Nếu listener chỉ đọc một property của context, có thể dựng context thật rất nhỏ. Nếu cần xác minh tương tác với dependency, có thể inject fake `Consumer`, fake interface hoặc Mockito mock. Tránh mock cả SpringApplication lifecycle khi mục tiêu chỉ là so sánh một string.

### 6.2. Đừng gọi System.exit trong listener test

Một listener thuộc ứng dụng không nên tùy tiện gọi `System.exit(...)`. Trong JVM chạy JUnit, hành vi đó có thể làm dừng cả test process. Khi thực sự cần test entrypoint trả process exit status, hãy chạy ứng dụng trong **subprocess** và quan sát exit code; đó không còn là unit test thuần của listener.

## 7. Kiểm thử Spring event dispatcher với context nhỏ

Để kiểm tra listener có nhận event **qua Spring event bus**, không gọi method trực tiếp nữa. Thay bằng:

```java
try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    new ModeInitializer().initialize(context);

    List<String> reports = new ArrayList<>();
    context.addApplicationListener(
            new ReadySummaryListener(reports::add));

    context.refresh();
    assertThat(reports).isEmpty();

    context.publishEvent(syntheticReadyEvent(context));
    assertThat(reports).containsExactly("READY_MODE=safe");
}
```

Đây là snippet trong JUnit class có helper ở mục 9.

**Điều chứng minh được:**

- Listener đã được đăng ký trực tiếp với `GenericApplicationContext`.
- Event dispatcher của Spring phân phối đúng loại `ApplicationReadyEvent`.
- Handler biến event thành kết quả mong muốn.
- Không cần `SpringApplication.run`.

**Điều chưa chứng minh:** Spring Boot có thật sự phát `ApplicationReadyEvent` khi hoàn tất runners hay không. Event trong test được **tự tạo và publish bằng tay**.

### 7.1. ContextRefreshedEvent được phát thực sự bởi refresh()

Một trường hợp có event **thật do context nhỏ phát**:

```java
AtomicInteger seen = new AtomicInteger();

try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    context.addApplicationListener(
            (ApplicationListener<ContextRefreshedEvent>)
                    event -> seen.incrementAndGet());

    context.refresh();
    assertThat(seen.get()).isEqualTo(1);
}
```

`context.refresh()` phát `ContextRefreshedEvent` khi refresh hoàn tất. Nó là một **Spring Framework context event**, khác với `ApplicationStartedEvent` hay `ApplicationReadyEvent` do Spring Boot phát.

### 7.2. Synchronous event dispatch và async listeners

Theo cấu hình thông thường, Spring event multicaster dùng dispatch **đồng bộ**. Vì vậy trong ví dụ trên, ngay sau `publishEvent(...)` trả về, `reports` đã có message.

Nếu ứng dụng tự cấu hình `ApplicationEventMulticaster` bất đồng bộ hoặc listener dùng `@Async`, assertion ngay sau publish có thể race. Khi đó cần test đồng bộ qua fake executor hoặc đợi bounded bằng `Awaitility`/`CountDownLatch`, không dùng `Thread.sleep(2000)` theo cảm tính.

### 7.3. Generic type và filter event

`ApplicationListener<ApplicationReadyEvent>` không phải listener cho mọi `ApplicationEvent`. Spring event bus dùng generic event type phù hợp để dispatch. Nếu tự viết listener kiểu raw `ApplicationListener` hoặc cấu hình generic không đúng, có thể nhận hoặc bỏ sót event ngoài ý muốn.

Trong bài test, constructor của listener và generic type được khai báo tường minh để giảm nguy cơ xử lý sai loại.

## 8. Test @EventListener bằng AnnotationConfigApplicationContext

`@EventListener` trên một method cần annotation method processing. Một test chỉ tạo:

```java
AnnotatedObserver observer = new AnnotatedObserver();
// Chưa đăng ký vào Spring context.
```

**không thể** chứng minh Spring phát hiện method đã được annotate.

Thay vào đó, dùng `AnnotationConfigApplicationContext`:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext()) {

    context.registerBean(AnnotatedObserver.class);
    context.refresh();

    context.publishEvent(syntheticReadyEvent(context));

    assertThat(context.getBean(AnnotatedObserver.class)
            .getCount()).isEqualTo(1);
}
```

Đây là snippet; class `AnnotatedObserver` và helper `syntheticReadyEvent` có trong test đầy đủ ở mục 9.

Điểm khác biệt:

- `AnnotationConfigApplicationContext` đăng ký các annotation configuration processors.
- `registerBean(...)` thêm bean cần test, không scan toàn package.
- `refresh()` kích hoạt event listener method processor.
- `publishEvent(...)` làm event bus gọi method `@EventListener`.
- Vẫn không hề chạy `SpringApplication.run(...)`.

### 8.1. Không nhầm @EventListener với listener đăng ký cực sớm

Một bean `@EventListener(ApplicationStartingEvent.class)` thông thường không được tạo trước khi context có. Để bắt event khởi động cực sớm, dùng `SpringApplication.addListeners(...)` hoặc `META-INF/spring.factories` theo contract Spring Boot. Unit test method xử lý event vẫn hữu ích, nhưng **không chứng minh registration timing**.

## 9. Dự án Java 17+ runnable: initializer và listeners không chạy SpringApplication.run

Dự án dùng **Spring Boot 3.3.13**, Spring Framework 6.1 và JUnit Jupiter. Nó có:

- `ModeInitializer`: xác minh `demo.mode`, cung cấp default `safe` bằng low-precedence property source.
- `ReadySummaryListener`: nhận `ApplicationReadyEvent`, ghi một thông điệp qua `Consumer`.
- `LifecycleProbe`: chương trình Java dựng `GenericApplicationContext`, tự refresh và publish **event synthetic**; không chạy Boot application lifecycle.
- `LifecycleComponentsTest`: các test direct initializer, precedence, invalid config, `ApplicationContextRunner`, listener direct, event dispatch, `ContextRefreshedEvent` và `@EventListener` annotation processing.

### 9.1. Cấu trúc project

```text
lifecycle-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/lifecycle/
    ModeInitializer.java
    ReadySummaryListener.java
    LifecycleProbe.java
  src/test/java/com/example/lifecycle/
    LifecycleComponentsTest.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'lifecycle-unit-tests'
```

### 9.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'application'
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

application {
    mainClass = 'com.example.lifecycle.LifecycleProbe'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` kéo JUnit Jupiter, AssertJ và các test dependencies phù hợp; `ApplicationContextRunner` thuộc `spring-boot-test` trong scope test. `application` plugin cho phép `./gradlew run` thực thi `LifecycleProbe.main()` **mà không chạy `SpringApplication.run`**.

Chỉ dùng `./gradlew test` và `./gradlew run` cho bài học; không yêu cầu khởi tạo một REST server, DataSource hoặc message broker.

### 9.4. ModeInitializer.java

```java
package com.example.lifecycle;

import java.util.Map;
import java.util.Set;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class ModeInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String mode = context.getEnvironment()
                .getProperty("demo.mode");

        if (mode != null
                && !Set.of("safe", "fast").contains(mode)) {
            throw new IllegalArgumentException(
                    "demo.mode must be safe or fast");
        }

        // Chỉ thêm default với độ ưu tiên thấp.
        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "lesson-mode-defaults",
                        Map.of("demo.mode", "safe")));
    }
}
```

Đây là **file hoàn chỉnh**, không cần BeanFactory được refresh. Nó không truy cập database, không tạo executor và không gọi `getBean`.

Nếu đã có property `demo.mode=fast` ở source ưu tiên cao, default `safe` không ghi đè; nếu được cấp `broken`, initializer ném exception ngay. Đây là hai contract quan trọng để kiểm tra bằng unit test.

### 9.5. ReadySummaryListener.java

```java
package com.example.lifecycle;

import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    private final Consumer<String> sink;

    public ReadySummaryListener(Consumer<String> sink) {
        this.sink = Objects.requireNonNull(sink);
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        String mode = event.getApplicationContext()
                .getEnvironment()
                .getProperty("demo.mode", "unset");

        sink.accept("READY_MODE=" + mode);
    }
}
```

Đây là **file hoàn chỉnh**. Nó không phải `@Component`; trong test, ta chủ động đăng ký listener hoặc gọi trực tiếp. Trong một ứng dụng thật, nếu muốn Boot gửi event khi ready, cần đăng ký listener đúng đường và thời điểm.

`Consumer<String>` giúp test thay nơi gửi log/event bằng `ArrayList::add`, không làm side effect ngoài JVM.

### 9.6. LifecycleProbe.java

```java
package com.example.lifecycle;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.support.GenericApplicationContext;

public final class LifecycleProbe {

    public static void main(String[] args) {
        List<String> reports = new ArrayList<>();
        AtomicInteger refreshEvents = new AtomicInteger();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);

            context.addApplicationListener(
                    (ApplicationListener<ContextRefreshedEvent>)
                            event -> refreshEvents.incrementAndGet());

            context.addApplicationListener(
                    new ReadySummaryListener(reports::add));

            // Đây là Spring Framework refresh, không phải Boot run.
            context.refresh();

            // Event này do test code tạo, Boot không tự phát.
            ApplicationReadyEvent syntheticReady =
                    new ApplicationReadyEvent(
                            new SpringApplication(LifecycleProbe.class),
                            new String[0],
                            context,
                            Duration.ofMillis(42));

            context.publishEvent(syntheticReady);

            System.out.println("MODE="
                    + context.getEnvironment()
                            .getProperty("demo.mode"));
            System.out.println("REFRESH_EVENTS="
                    + refreshEvents.get());
            System.out.println("READY_REPORTS=" + reports);
        }
    }
}
```

Đây là **file Java hoàn chỉnh**. Chương trình chỉ tạo `GenericApplicationContext`, thêm listener, gọi `refresh` và publish một event test. `new SpringApplication(LifecycleProbe.class)` chỉ tạo object làm **source** của event; **không** gọi `SpringApplication.run`.

Với `GenericApplicationContext` không có bean nghiệp vụ nào, `refresh()` tạo infrastructure tối thiểu và phát đúng một `ContextRefreshedEvent` trong đường chạy bình thường.

### 9.7. Lệnh chạy chương trình minh họa

Từ thư mục project có Gradle Wrapper:

```bash
./gradlew run
```

Windows CMD:

```bat
gradlew.bat run
```

Windows PowerShell:

```powershell
.\gradlew.bat run
```

Các dòng **do chính `LifecycleProbe` in ra** trong đường thành công theo thứ tự:

```text
MODE=safe
REFRESH_EVENTS=1
READY_REPORTS=[READY_MODE=safe]
```

Gradle có thể in thêm progress và thông báo build, nhưng ba dòng do code tự in không phụ thuộc thời gian máy chạy. Dòng `READY_REPORTS` xuất hiện vì test **tự publish** `ApplicationReadyEvent`, không phải Boot thực sự đến readiness accepting.

### 9.8. LifecycleComponentsTest.java

```java
package com.example.lifecycle;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LifecycleComponentsTest {

    @Test
    void initializerWorksBeforeRefresh() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("safe");
            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void initializerDoesNotOverrideConfiguredValue() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-override",
                            Map.of("demo.mode", "fast")));

            new ModeInitializer().initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        }
    }

    @Test
    void initializerRejectsUnknownMode() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-bad-mode",
                            Map.of("demo.mode", "broken")));

            assertThatThrownBy(
                    () -> new ModeInitializer().initialize(context))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessage("demo.mode must be safe or fast");

            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void runnerExecutesInitializerWithSelectedProperties() {
        new ApplicationContextRunner()
                .withPropertyValues("demo.mode=fast")
                .withInitializer(new ModeInitializer())
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("demo.mode")).isEqualTo("fast");
                });
    }

    @Test
    void readyListenerCanBeTestedDirectly() {
        List<String> observed = new ArrayList<>();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);
            context.refresh();

            ReadySummaryListener listener =
                    new ReadySummaryListener(observed::add);

            listener.onApplicationEvent(readyEvent(context));

            assertThat(observed)
                    .containsExactly("READY_MODE=safe");
        }
    }

    @Test
    void contextDispatcherRoutesSyntheticReadyEvent() {
        List<String> observed = new ArrayList<>();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);
            context.addApplicationListener(
                    new ReadySummaryListener(observed::add));

            context.refresh();
            assertThat(observed).isEmpty();

            context.publishEvent(readyEvent(context));
            assertThat(observed)
                    .containsExactly("READY_MODE=safe");
        }
    }

    @Test
    void refreshPublishesContextRefreshedEvent() {
        AtomicInteger count = new AtomicInteger();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.addApplicationListener(
                    (ApplicationListener<ContextRefreshedEvent>)
                            event -> count.incrementAndGet());

            context.refresh();
            assertThat(count.get()).isEqualTo(1);

            // Publish thủ công một event cùng type để kiểm tra dispatch.
            context.publishEvent(new ContextRefreshedEvent(context));
            assertThat(count.get()).isEqualTo(2);
        }
    }

    @Test
    void annotationListenerWorksInMinimalAnnotationContext() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(AnnotatedReadyObserver.class);
            context.refresh();

            context.publishEvent(readyEvent(context));

            assertThat(context.getBean(AnnotatedReadyObserver.class)
                    .getCount()).isEqualTo(1);
        }
    }

    private static ApplicationReadyEvent readyEvent(
            GenericApplicationContext context) {

        return new ApplicationReadyEvent(
                new SpringApplication(LifecycleProbe.class),
                new String[0],
                context,
                Duration.ofMillis(42));
    }

    public static final class AnnotatedReadyObserver {

        private final AtomicInteger count = new AtomicInteger();

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            count.incrementAndGet();
        }

        public int getCount() {
            return count.get();
        }
    }
}
```

**Đây là test file hoàn chỉnh**, có tám test methods. Các tests không gọi `SpringApplication.run`, không dùng `@SpringBootTest` và không mở HTTP port.

Những gì mỗi test chứng minh:

| Test | Phạm vi |
| --- | --- |
| `initializerWorksBeforeRefresh` | Đặt default property trước refresh |
| `initializerDoesNotOverrideConfiguredValue` | Precedence của property source được giữ |
| `initializerRejectsUnknownMode` | Validation và exception path của initializer |
| `runnerExecutesInitializerWithSelectedProperties` | `ApplicationContextRunner.withInitializer` dùng đúng properties |
| `readyListenerCanBeTestedDirectly` | Logic handler nhận event |
| `contextDispatcherRoutesSyntheticReadyEvent` | Event multicaster chuyển đúng event tới listener |
| `refreshPublishesContextRefreshedEvent` | Context refresh thực sự phát event Spring Framework |
| `annotationListenerWorksInMinimalAnnotationContext` | `@EventListener` được annotation processors đăng ký |

### 9.9. Chạy JUnit tests

```bash
./gradlew test
```

Windows CMD: `gradlew.bat test`; PowerShell: `.\gradlew.bat test`.

Khi test chạy thành công, Gradle sẽ báo `BUILD SUCCESSFUL` (chi tiết output và thời gian phụ thuộc Gradle). Bản báo cáo HTML chuẩn thường ở:

```text
build/reports/tests/test/index.html
```

Bài học mong đợi **8 tests thành công** trong môi trường tương thích. Không dự đoán số giây hoặc toàn bộ log của Gradle/Spring, vì phụ thuộc máy và cache.

### 9.10. Vì sao bài demo không có @SpringBootApplication?

Ta chỉ kiểm tra thành phần lifecycle nhỏ; không cần tạo toàn bộ application class, component scanning, auto-configuration hay embedded server. `LifecycleProbe` là một Java entrypoint thông thường, có thể tạo `SpringApplication` để xây dựng **một synthetic event**, nhưng không gọi `run(...)`.

Nếu sau này chuyển listener/initializer vào một ứng dụng thực tế, vẫn phải kiểm tra cách đăng ký chúng ở SpringApplication và hành vi khi khởi động đầy đủ. Test nhỏ này **không thay thế** một integration test đại diện cho deployment path.

## 10. Kiểm thử thứ tự nhiều initializer

Spring Boot áp dụng các initializers theo thứ tự, có hỗ trợ `Ordered` và `@Order`. Một initializer có thể ghi default property, initializer khác đọc property đó. Nếu logic phụ thuộc thứ tự, hãy kiểm tra **đúng tầng**:

- **Unit test**: gọi `first.initialize(context)` và `second.initialize(context)` theo thứ tự tường minh; chỉ chứng minh logic khi được gọi theo thứ tự đó.
- **Test danh sách sắp xếp**: dùng Spring `AnnotationAwareOrderComparator`/`Ordered` để kiểm tra thứ tự mong muốn của một collection.
- **Integration test của SpringApplication**: cần khi muốn khẳng định Boot áp dụng những initializers được đăng ký từ code, properties hoặc `spring.factories` theo thứ tự thực tế.

Ví dụ pseudo-test được gắn nhãn minh họa:

```java
List<String> calls = new ArrayList<>();

ApplicationContextInitializer<ConfigurableApplicationContext> first =
        context -> calls.add("first");

ApplicationContextInitializer<ConfigurableApplicationContext> second =
        context -> calls.add("second");

try (GenericApplicationContext context =
             new GenericApplicationContext()) {
    first.initialize(context);
    second.initialize(context);
}

assertThat(calls).containsExactly("first", "second");
```

Đây là **snippet**, cần imports và assertions; nó chỉ chứng minh thứ tự do **test code tự gọi**, không chứng minh `SpringApplication` đã sort theo `Ordered`.

**Lưu ý:** giá trị order thấp hơn thường có ưu tiên cao hơn. Nếu hai initializers có cùng order, không dựa vào thứ tự đăng ký tình cờ cho logic quan trọng.

## 11. Test @ContextConfiguration(initializers=...) khi cần Spring TestContext

Spring Framework TestContext cho phép đăng ký initializers cho một test context được dựng bởi framework:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = SmallTestConfiguration.class,
        initializers = ModeInitializer.class)
class WithInitializerTest {

    @Autowired
    Environment environment;

    @Test
    void defaultModeIsVisible() {
        assertThat(environment.getProperty("demo.mode"))
                .isEqualTo("safe");
    }
}
```

Đây là **snippet**, cần các imports từ JUnit, Spring Test, AssertJ và một class cấu hình `SmallTestConfiguration`. Không phải file chạy độc lập vì class cấu hình chưa được định nghĩa ở đoạn minh họa.

Mô hình này phù hợp khi cần Spring TestContext quản lý:

- Injection bằng `@Autowired`.
- Configuration classes tối thiểu.
- Vòng đời test context và các test execution listeners.
- Một số post-processors mà unit test thuần không có.

Nhưng nó **không tự chạy SpringApplication.run**, và test context caching có thể tái sử dụng context. Đừng đóng context Spring TestContext đang cache bằng cách gọi `close()` thủ công trong test nếu không có chủ đích; dùng context riêng hoặc `@DirtiesContext` đúng trường hợp.

### 11.1. Khi nào chọn ApplicationContextRunner thay vì @ContextConfiguration?

`ApplicationContextRunner` thường gọn hơn nếu muốn thử nhiều combinations:

```text
demo.mode=missing  -> initializer chọn default safe
demo.mode=fast     -> giữ nguyên fast
demo.mode=broken   -> validation failure
```

Nó tạo/đóng từng context trong callback. `@ContextConfiguration` thuận tiện khi cần SpringExtension, injection và reuse cùng cấu hình trong nhiều test methods.

Đây là lựa chọn về **chi phí và mức độ xác minh**, không phải công cụ nào “tốt tuyệt đối”.

## 12. Early SpringApplication events: những giới hạn khi mock

Một số sự kiện xảy ra **trước khi ApplicationContext tồn tại**:

- `ApplicationStartingEvent` được phát rất sớm.
- `ApplicationEnvironmentPreparedEvent` xuất hiện sau khi Environment sẵn sàng nhưng trước khi tạo context.
- `ApplicationContextInitializedEvent` xuất hiện sau các initializers nhưng trước khi load bean definitions.
- `ApplicationPreparedEvent` xuất hiện sau load definitions và trước refresh.

Một listener nhận `ApplicationEnvironmentPreparedEvent` có thể muốn thay property source của `ConfigurableEnvironment`. Bạn có thể **unit test handler** bằng cách tạo một `StandardEnvironment` và dựng event với **constructor đúng của Spring Boot 3.3**, bao gồm `ConfigurableBootstrapContext` nếu được yêu cầu.

**Không copy constructor của Boot 2.x hoặc một version khác** rồi kỳ vọng code 3.3 compile. JavaDoc Boot 3.3 định nghĩa constructor:

```java
ApplicationEnvironmentPreparedEvent(
        ConfigurableBootstrapContext bootstrapContext,
        SpringApplication application,
        String[] args,
        ConfigurableEnvironment environment)
```

Đây là mô tả chữ ký API, không phải lệnh gọi file độc lập. Trong test có thể fake/mock bootstrap context đúng interface khi handler thật sự cần; nếu handler chỉ xử lý Environment, tách logic thuần ra khỏi adapter nhận event để dễ unit test.

### 12.1. Tách business logic khỏi adapter sự kiện

Một thiết kế dễ test:

```text
ApplicationEnvironmentPreparedEvent
          |
EarlyEnvironmentListener.onApplicationEvent(event)
          |
EnvironmentPolicy.apply(environment)
          |
PropertySource / profile thay đổi
```

Unit test `EnvironmentPolicy` với `StandardEnvironment` rất nhanh. Test adapter listener riêng bằng synthetic event. Cuối cùng, chỉ cần một integration test nhỏ để chắc registration của listener qua `SpringApplication.addListeners`/`spring.factories` thực sự hoạt động đúng thời điểm.

**Không** bắt mọi test phải chạy startup hoàn chỉnh chỉ vì listener nhận một Boot event.

### 12.2. Test một early listener được đăng ký thật là bài khác

Nếu chỉ gọi:

```java
listener.onApplicationEvent(event);
```

thì test **không thể chứng minh** `META-INF/spring.factories` đúng path, class có public no-arg constructor, hoặc `SpringApplication.addListeners(...)` được gọi trước `run`.

Khi muốn chứng minh phần wiring, có thể có một test hạn chế khởi động `SpringApplication` theo `WebApplicationType.NONE` với số beans tối thiểu. Đây là một **integration test riêng**, không phải lý do đổi tất cả unit tests thành `@SpringBootTest`.

## 13. Listener trong parent/child ApplicationContext

Spring Framework có cơ chế event propagation từ **child context lên ancestor contexts**. Một listener đăng ký ở parent có thể quan sát events từ child, nên:

- Một `ContextRefreshedEvent` của child có thể đến listener parent.
- Nếu listener muốn chỉ xử lý event của chính context, hãy so sánh `event.getApplicationContext()` với context mà listener được gắn.
- Unit test trực tiếp event handler không chứng minh propagation behavior.
- Một test context hierarchy nhỏ có thể được dựng để xác minh; không cần start web server.

Với `ApplicationReadyEvent`, source là SpringApplication nhưng event còn có `getApplicationContext()`. Không suy luận mọi ready events trong hierarchy là sự kiện của cùng một context.

**Không để listener tự đóng DataSource/executor của parent chỉ vì child context phát event shutdown.** Ownership và context identity phải được xét.

## 14. Thử lỗi và tác dụng phụ một cách có kiểm soát

### 14.1. Exceptions từ initializer

Nếu initializer ném exception trước refresh, một unit test direct nên assert exception chính xác. `ApplicationContextRunner` có thể cho biết startup failure của mini-context. Nhưng **không được khẳng định** Spring Boot `ApplicationFailedEvent` đã phát nếu bạn không gọi `SpringApplication.run`.

### 14.2. Exceptions từ listener

Trong event multicaster đồng bộ thông thường, exception của listener có thể lan về publisher, trừ khi bạn cấu hình error handler hoặc executor khác. Một unit test trực tiếp có thể assert exception. Một mini-context test có thể assert cách publisher nhận lỗi.

Tuy nhiên nếu listener được gắn `@Async` hoặc `ApplicationEventMulticaster` dùng executor bất đồng bộ, lỗi có thể đi theo contract khác; không dùng `assertThrows` trên `publishEvent` và nghĩ chắc chắn bắt được exception ở thread khác.

### 14.3. Tránh network và threads trong test nhỏ

Nếu listener chỉ gửi notification, thay client bằng fake in-memory sink. Nếu initializer chỉ validate properties, đừng tạo database thật. Nếu handler tự tạo executor, test cần dừng executor để tránh giữ JUnit process. Mục tiêu của bài là **isolation**, không phải tái hiện toàn bộ hạ tầng production.

### 14.4. Cleanup contexts

`GenericApplicationContext` và `AnnotationConfigApplicationContext` là `AutoCloseable` qua Spring context contract; ví dụ dùng try-with-resources. `ApplicationContextRunner` tự đóng sau callback.

Không tạo hàng trăm contexts rồi để mở: ngay cả một context nhỏ vẫn có lifecycle và có thể chứa beans cần destroy. Tránh static/shared context mutable giữa tests nếu logic của initializer có thể thay đổi Environment hoặc listener state.

## 15. Những điều unit test không thể chứng minh

| Kiểm thử đã làm | Điều **chưa** chứng minh |
| --- | --- |
| Gọi `initialize(context)` trực tiếp | Boot đã register initializer và gọi nó đúng phase |
| Gọi `listener.onApplicationEvent(event)` | Spring event multicaster biết listener này |
| `context.publishEvent(syntheticReady)` thành công | Boot đã chạy runners hoặc readiness accepting |
| `context.refresh()` phát ContextRefreshedEvent | Boot đã phát ApplicationStartedEvent/ReadyEvent |
| `ApplicationContextRunner.run` thành công | Full Boot auto-configuration và web server sẽ thành công |
| `@EventListener` nhận event trong context nhỏ | Bean sẽ được scan từ package production |
| Đặt `@Order` trên test classes | Production registration/ordering đã hoạt động |
| Fake callback thông báo thành công | Remote notification thật hoặc auth/timeout đã đúng |
| Test không có database vẫn pass | Datasource production được tạo và kết nối thật |
| Test handler không ném exception | Listener có thể chạy đúng trong mọi concurrency/deployment scenario |

Phân biệt ranh giới này trong tên test, comment hoặc tài liệu test. Một số đội đặt tên `onReadyFormatsReport` cho unit test, và `bootPublishesReadyAfterRunners` cho integration test; hai test kiểm tra hai hợp đồng khác nhau.

## 16. Khi nào cần một test integration thật sự?

Tăng cấp lên `@SpringBootTest` hoặc một `SpringApplication` tối giản chạy thật khi câu hỏi bao gồm:

- Listener có được đăng ký đúng qua `META-INF/spring.factories` hoặc `addListeners` không?
- Thứ tự initializers được Boot apply thực tế như thế nào?
- ConfigData, profiles, property binding và auto-configuration thực tế có ảnh hưởng đúng không?
- `ApplicationStartedEvent`, `ApplicationReadyEvent` và `AvailabilityChangeEvent` xảy ra đúng trình tự sau runner?
- Runner fail có dẫn đến `ApplicationFailedEvent` và cleanup context đúng không?
- Bean được tạo trước/không trước refresh hoặc Spring lifecycle callback dừng đúng thứ tự không?
- Event listener có phụ thuộc tới embedded web server/security/health endpoint không?
- Native image, AOT hoặc `@EventListener` reflection hints có thay đổi behavior không?

**Chọn số ít integration tests có ý nghĩa**, không dùng full application test cho mọi nhánh property đơn giản. Nếu một listener cần kiểm chứng readiness probe qua HTTP, đó rõ ràng không còn là unit test synthetic event.

### 16.1. @SpringBootTest không nhất thiết mở TCP server

`@SpringBootTest` mặc định có `webEnvironment = MOCK` đối với web app, nên nó có thể dựng mock web environment mà không mở real socket. Tuy nhiên nó vẫn có thể load nhiều cấu hình/beans và mất thời gian. Không gắn nhãn “không cần chạy server” đồng nghĩa “không cần chạy toàn ứng dụng” mà không xét bean graph thực sự được load.

### 16.2. ApplicationContextRunner còn có hạn chế riêng

Theo tài liệu Spring Boot 3.3, `ApplicationContextRunner` phù hợp kiểm thử auto-configuration trong JVM thông thường nhưng **không dùng được khi chạy tests như native image**. Nếu dự án có native-test pipeline, cần giải pháp test tương ứng; đừng giả định code chạy với runner ở JVM sẽ chứng minh native AOT configuration đã đúng.

## 17. Kịch bản học tập: từ unit tới integration có chủ đích

### A. Initializer đặt property source mặc định

**Đầu tiên:** unit test với `GenericApplicationContext` chưa refresh, kiểm tra default và precedence.

**Tiếp theo khi cần:** `ApplicationContextRunner.withInitializer` với các property combinations.

**Chỉ nếu có rủi ro registration:** test `SpringApplication.addInitializers` hoặc cấu hình registration thật.

### B. Listener nhận ApplicationReadyEvent ghi log

**Đầu tiên:** tạo synthetic `ApplicationReadyEvent` và gọi listener trực tiếp; inject fake `Consumer`.

**Sau đó:** publish event trong `GenericApplicationContext` đã đăng ký listener, xác minh dispatch.

**Cuối cùng nếu cần:** test thật sự Boot event sau runners, không dùng synthetic event để tuyên bố ready.

### C. Method @EventListener được component scan

**Đầu tiên:** test logic của method như Java method độc lập nếu không cần Spring behavior.

**Sau đó:** dùng `AnnotationConfigApplicationContext` và `registerBean(...)` để xác minh annotation processing.

**Cuối cùng:** test package scanning thực tế nếu từng xảy ra lỗi cấu hình scan.

### D. Early environment listener phải chạy trước context creation

**Đầu tiên:** tách logic xử lý `Environment`, unit test bằng `StandardEnvironment`.

**Sau đó:** unit test adapter nhận event với constructor đúng Boot version.

**Cuối cùng:** một integration test xác minh listener được đăng ký qua `addListeners`/`spring.factories` trước `run`.

### E. Listener có @Async

**Đầu tiên:** test logic synchronously qua direct call và mock dependency.

**Sau đó:** mini-context test có `@EnableAsync` và test executor nếu cần xác minh proxying.

**Cuối cùng:** integration test bounded wait và error handling nếu liên quan concurrency thật.

### F. Initializer đăng ký infrastructure bean

**Đầu tiên:** kiểm tra bean definition đã được đăng ký trước refresh.

**Sau đó:** refresh một `GenericApplicationContext` tối giản để kiểm tra singleton được tạo đúng.

**Cuối cùng:** một integration test nếu bean được tạo qua Boot auto-configuration/conditions phức tạp.

## 18. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách thay |
| --- | --- | --- |
| Dùng `@SpringBootTest` cho mọi nhánh if | Test chậm, nhiều dependencies không liên quan | Unit test direct trước |
| Gọi `context.getBean(...)` trong initializer trước refresh | BeanFactory chưa ở pha sử dụng như ứng dụng ready | Chỉ cấu hình context/definitions |
| Gọi initializer sau refresh rồi kết luận đúng production | Sai phase của contract initializer | Gọi trước `refresh` |
| Dùng synthetic ApplicationReadyEvent để chứng minh Boot ready | Event do test tự tạo | Integration test mốc Boot nếu cần |
| Tạo `@EventListener` object bằng new và không register | Spring không quét object tùy ý | AnnotationConfigApplicationContext + registerBean |
| Gắn `@Component` để bắt ApplicationStartingEvent | Bean chưa tạo khi early event được phát | Early registration qua SpringApplication |
| Không đóng context test | Resource leak giữa các tests | try-with-resources hoặc runner callback |
| Gọi `GenericApplicationContext.refresh` hai lần | Generic context không dành cho refresh lặp | Tạo context mới |
| Assert ngay sau async event publish | Race/flaky khi dispatch không đồng bộ | Fake synchronous executor hoặc bounded await |
| Ngầm dựa vào event order không được kiểm tra | Khi có nhiều listeners order có thể quan trọng | Ordered/@Order và test đúng tầng |
| Dùng listener đọc DB trong unit test | Phụ thuộc ngoại vi làm test chậm | Fake dependency/Consumer |
| Nghĩ ApplicationContextRunner là full SpringApplication | Không chạy full Boot lifecycle | Integration test riêng |
| Truyền giá trị property bằng addFirst để làm default | Có thể ghi đè override của user | addLast hoặc precedence rõ |
| Test listener trực tiếp rồi nghĩ đã đăng ký qua event bus | Không có framework dispatch trong test | publishEvent trong mini-context |
| @SpringBootTest cache context bị close trong test | Làm test khác hỏng | Không close cached context tùy tiện |
| Unit test gọi System.exit | Kết thúc JUnit runner | Subprocess/process-level test |
| Test dùng Thread.sleep để chờ @Async | Dễ flaky/không có timeout policy | CountDownLatch/Awaitility có deadline |
| Không phân biệt ContextRefreshedEvent và ApplicationReadyEvent | Một do Framework refresh, một do Boot | Test đúng event publisher |
| Mock API của Boot 2.x trong project 3.3 | Constructor/generics thay đổi | Đối chiếu đúng JavaDoc 3.3 |
| Coi test context nhỏ là bằng chứng web server hoạt động | Không có web server thật | Test slice/web integration khi cần |

## 19. Checklist chọn test phù hợp

1. Viết rõ event/initializer contract muốn test.
2. Nếu chỉ có logic thuần, gọi method trực tiếp.
3. Dùng `GenericApplicationContext` chưa refresh cho initializer properties.
4. Đặt default ở property source có precedence đúng.
5. Test invalid config với exception cụ thể.
6. Khi cần nhiều property combinations, dùng `ApplicationContextRunner`.
7. Khi cần event dispatch, `addApplicationListener` và `publishEvent`.
8. Khi cần `@EventListener` method processing, dùng `AnnotationConfigApplicationContext`.
9. Phân biệt event synthetic với event do Boot tự phát.
10. Không dùng `SpringApplication.run` nếu không cần chứng minh Boot lifecycle.
11. Nếu cần early listener registration thật, test đường `addListeners`/`spring.factories`.
12. Không phụ thuộc network/DB/threads thật khi có thể fake.
13. Dùng JUnit/AssertJ assertion rõ nội dung, count và exception.
14. Xác định sync/async event delivery trước khi assert.
15. Ghi rõ environment property precedence và profile expectations.
16. Không refresh GenericApplicationContext lặp lại.
17. Đóng context nhỏ, đừng giữ bean sau callback runner.
18. Không đóng shared cached `@SpringBootTest` context tùy tiện.
19. Kiểm thử failure path của initializer riêng.
20. Dùng integration test chỉ cho wiring/lifecycle cần xác minh.
21. Khi test early event, dùng đúng constructor Boot 3.3.
22. Nếu có parent/child contexts, kiểm tra event source/context identity.
23. Không kết luận readiness chỉ từ một event tự publish.
24. Với native/AOT, không suy luận rằng ApplicationContextRunner đã test đúng native runtime.

## 20. Câu hỏi tự kiểm tra

**1. Có thể gọi initialize(context) khi context chưa refresh không?**

Có. Đây chính là giai đoạn dành cho `ApplicationContextInitializer`; unit test direct là lựa chọn tự nhiên.

**2. Vì sao dùng GenericApplicationContext thay vì @SpringBootTest?**

Để tránh tạo toàn bộ bean graph/auto-configuration khi chỉ kiểm tra property source hoặc callback đơn giản.

**3. ApplicationContextRunner.run() có chạy SpringApplication.run() không?**

Không. Nó tạo và refresh một context phục vụ test, không thực thi toàn bộ Spring Boot lifecycle.

**4. Test gọi listener.onApplicationEvent(event) chứng minh gì?**

Chứng minh logic listener khi nhận event. Nó chưa chứng minh listener được đăng ký và nhận event qua event bus.

**5. Làm sao kiểm tra Spring event dispatcher?**

Đăng ký listener bằng `context.addApplicationListener(...)`, refresh context rồi `context.publishEvent(...)`.

**6. Gọi publishEvent(new ApplicationReadyEvent(...)) có làm app ready không?**

Không. Nó chỉ phát object event do test tạo, không chạy runners hay thay thế lifecycle/availability của Boot.

**7. @EventListener có hoạt động nếu tạo object bằng new rồi không đăng ký?**

Không tự động. Cần một context hỗ trợ annotation event listener processing hoặc gọi method trực tiếp.

**8. ContextRefreshedEvent được phát bởi thành phần nào?**

Spring Framework phát khi `ApplicationContext.refresh()` hoàn tất. Nó khác `ApplicationReadyEvent` của Spring Boot.

**9. Early listener @Component có luôn bắt ApplicationStartingEvent không?**

Không. Event có thể phát trước khi Spring bean được tạo; phải đăng ký đủ sớm.

**10. Có thể test initializer throw mà không mở web server không?**

Có, với `assertThatThrownBy(() -> initializer.initialize(context))` hoặc context runner.

**11. Khi nào nên dùng @ContextConfiguration(initializers=...)?**

Khi muốn Spring TestContext, dependency injection và cấu hình context nhỏ có initializer, nhưng không cần full Boot application.

**12. Unit test có thay thế hoàn toàn integration test không?**

Không. Unit test chứng minh logic; wiring, event order của Boot, scanning và readiness thật cần integration test có phạm vi thích hợp.

## 21. Sơ đồ quyết định và kết luận

```text
Bạn cần test gì?
      |
      +-- Initializer thay Environment/PropertySources?
      |       |
      |       +--> GenericApplicationContext + initialize()
      |       +--> ApplicationContextRunner.withInitializer()
      |
      +-- Listener xử lý event đúng dữ liệu?
      |       |
      |       +--> new Listener(...), gọi onApplicationEvent()
      |
      +-- Event dispatcher chuyển event tới listener?
      |       |
      |       +--> context.addApplicationListener()
      |       +--> context.refresh() + publishEvent()
      |
      +-- @EventListener annotation được phát hiện?
      |       |
      |       +--> AnnotationConfigApplicationContext
      |       +--> registerBean + refresh + publishEvent
      |
      +-- Boot tự phát event theo thứ tự/runners/readiness?
              |
              +--> Integration test SpringApplication

TEST SYNTHETIC EVENT != FULL BOOT LIFECYCLE
TEST INITIALIZER TRỰC TIẾP != XÁC MINH PRODUCTION REGISTRATION
```

**Nguyên tắc cốt lõi:** test initializer hoặc listener ở **tầng nhỏ nhất đủ để chứng minh hành vi**. Dùng Java object và `GenericApplicationContext` cho unit/component tests, `ApplicationContextRunner` cho nhiều tổ hợp cấu hình, `AnnotationConfigApplicationContext` cho `@EventListener`, và chỉ dùng full `SpringApplication` khi cần xác minh wiring hoặc event lifecycle thật. Kết quả nhanh hơn, lỗi test tập trung hơn, và ranh giới giữa **logic đã kiểm thử** với **hành vi production cần xác nhận** sẽ rõ ràng hơn.

## Tài liệu chính thức

- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — GenericApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/support/GenericApplicationContext.html)
- [Spring Framework — Application Events và event listener model](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Framework — TestContext: Context Configuration with Context Initializers](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/initializers.html)
- [Spring Framework — TestContext: Recording Application Events](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/application-events.html)
- [Spring Boot 3.3 — SpringApplication events and listener registration](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — ApplicationReadyEvent constructor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 — ApplicationEnvironmentPreparedEvent constructor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html)
