# Dùng ApplicationContextRunner và hiểu các mốc SpringApplication không được thực thi

## 1. Câu hỏi trọng tâm: context đã refresh có nghĩa ứng dụng đã chạy xong startup chưa?

**Không.** Đây là sự phân biệt quan trọng khi kiểm thử vòng đời Spring Boot.

`ApplicationContextRunner` thuộc package `org.springframework.boot.test.context.runner`, cung cấp một cách dựng, refresh, kiểm tra và tự đóng **một `ApplicationContext` tối giản** trong test. Nó đặc biệt hữu ích để xác minh một nhóm bean, các điều kiện `@Conditional...`, thứ tự khởi tạo/hủy và cấu hình auto-configuration theo những property khác nhau.

`SpringApplication.run(...)` lại là **bộ điều phối khởi động Spring Boot**: ngoài việc tạo và refresh context, nó chuẩn bị environment/arguments, phát các `SpringApplicationEvent`, gọi `ApplicationRunner`/`CommandLineRunner`, cập nhật availability liveness/readiness và xử lý startup failure qua các cơ chế Boot.

Vì `ApplicationContextRunner` **không gọi `SpringApplication.run(...)`**, nhiều mốc cấp SpringApplication **không tự xảy ra**, cho dù bên trong test đã có một context active, bean đã được injected và các `SmartLifecycle` component đã start.

Một câu phân biệt đúng:

> **ApplicationContextRunner kiểm chứng ngữ nghĩa của một ApplicationContext được refresh; nó không mô phỏng toàn bộ quy trình SpringApplication khởi động ứng dụng.**

Mục tiêu bài này: chỉ rõ **mốc nào có**, **mốc nào không**, vì sao không được suy diễn `ApplicationReadyEvent` từ `ContextRefreshedEvent`, cách viết test Java 17+ Spring Boot 3.3.13 thực thi được, cách tạo startup failure có kiểm soát, và tiêu chí khi nào cần chuyển từ context-runner test sang integration test.

Phạm vi ví dụ: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, JUnit Jupiter 5, AssertJ, Gradle**. Bài không sử dụng lịch sử nội dung bài khác; các ví dụ tự chứa đủ cấu hình và class để thử nghiệm.

## 2. Hai cơ chế “run” trùng tên nhưng không cùng nhiệm vụ

### 2.1. ApplicationContextRunner.run(consumer)

Mã test điển hình:

```java
new ApplicationContextRunner()
        .withUserConfiguration(DemoConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoService.class);
        });
```

Đây là **đoạn minh họa**, chưa phải file biên dịch độc lập vì cần `DemoConfiguration`, `DemoService` và imports. Phương thức `run` ở đây:

1. Tạo **một context mới** từ cấu hình của runner.
2. Đăng ký bean definitions, property sources, initializers và auto-configurations mà test chỉ định.
3. Gọi quá trình **refresh context**.
4. Đưa một `AssertableApplicationContext` vào lambda để test đọc bean và assertion.
5. **Tự đóng context sau khi callback hoàn tất**, kể cả khi phải xử lý cleanup tương ứng.

Theo API Spring Boot 3.3, `new ApplicationContextRunner()` mặc định sử dụng `AnnotationConfigApplicationContext`, tức **context không phải web** và không phải một lời gọi `SpringApplication.run`. Nó không tự component-scan toàn project hoặc kích hoạt tất cả auto-configurations nếu không được yêu cầu.

### 2.2. SpringApplication.run(...)

Mã application chính:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);
```

Đoạn này cũng chỉ minh họa. `SpringApplication.run` chịu trách nhiệm chuẩn bị nhiều phần **ngoài bản thân context refresh**:

- Bootstrapping environment và command-line arguments theo quy tắc Boot.
- Chọn loại `ApplicationContext` phù hợp với web classpath/cấu hình.
- Đăng ký initializers/listeners ở giai đoạn trước khi bean definitions được load.
- Phát các `SpringApplicationEvent` đặc thù trước và sau context refresh.
- Gọi `ApplicationRunner` và `CommandLineRunner` sau refresh.
- Phát `ApplicationStartedEvent`, `ApplicationReadyEvent`, các `AvailabilityChangeEvent` liên quan.
- Chuyển các startup failure vào đường xử lý lỗi tương ứng.
- Trả về context còn chạy để ứng dụng tiếp tục phục vụ hoặc do caller tự đóng.

**Không phải mọi bước trên được kích hoạt chỉ bằng `context.refresh()`.** Spring Framework và Spring Boot dùng các hook khác nhau.

### 2.3. Bảng phân biệt nhanh

| Hành vi / điểm quan sát | `ApplicationContextRunner.run` mặc định | `SpringApplication.run` bình thường |
| --- | --- | --- |
| Tạo `ApplicationContext` | **Có** | **Có** |
| Đăng ký bean và inject dependency | **Có**, theo cấu hình test | **Có**, theo application sources/auto-config |
| `@PostConstruct`, `InitializingBean` của bean được tạo | **Có** | **Có** |
| `BeanFactoryPostProcessor` / `BeanPostProcessor` | **Có**, nếu thuộc context | **Có** |
| `SmartLifecycle.start()` trong refresh nếu auto-start | **Có** | **Có** |
| Spring Framework `ContextRefreshedEvent` | **Có** trên refresh thành công | **Có** trên refresh thành công |
| Spring Boot `ApplicationStartingEvent` | **Không tự phát** | **Có** |
| `ApplicationEnvironmentPreparedEvent` và `ApplicationPreparedEvent` | **Không tự phát** | **Có** |
| Spring Boot `ApplicationStartedEvent` | **Không tự phát** | **Có**, sau refresh |
| `ApplicationRunner.run` / `CommandLineRunner.run` | **Không tự gọi** | **Có**, trước ready |
| `ApplicationReadyEvent` | **Không tự phát** | **Có**, sau runners thành công |
| Liveness/readiness events do SpringApplication phát | **Không tự phát** | **Có**, theo Boot startup sequence |
| `ContextClosedEvent` khi context đóng bình thường | **Có** ở cuối test `run` | **Có** khi đóng context |
| `SmartLifecycle.stop` và singleton `@PreDestroy` | **Có** khi runner đóng context bình thường | **Có** khi context đóng bình thường |
| `ApplicationFailedEvent` khi refresh test lỗi | **Không tự phát theo cơ chế SpringApplication** | **Có thể phát** trên startup failure |
| `FailureAnalyzer`/Boot startup failure reporting | Không được tự suy là đã chạy | Thuộc failure handling của `SpringApplication` |
| JVM process exit / exit code | **Không** | `SpringApplication.run` cũng không tự đồng nghĩa `System.exit` |

Cột context runner phản ánh **runner chuẩn** không có custom code tự phát Boot events. Nếu người dùng cố ý gọi `context.publishEvent(new ...)` hoặc cài một custom initializer, hành vi có thể khác; đó không phải các mốc **tự động** của SpringApplication.

## 3. Timeline: refresh context khác hoàn tất Spring Boot startup

### 3.1. ApplicationContextRunner

```text
JUnit @Test
   |
   +--> new ApplicationContextRunner()
   +--> withUserConfiguration(...), withPropertyValues(...)
   +--> runner.run(callback)
          |
          +--> tạo AnnotationConfigApplicationContext
          +--> chuẩn bị/đăng ký bean definitions
          +--> refresh()
          |      +--> BeanFactoryPostProcessors / BeanPostProcessors
          |      +--> tạo non-lazy singleton
          |      +--> dependency injection, @PostConstruct
          |      +--> LifecycleProcessor.onRefresh()
          |      |      +--> SmartLifecycle auto-start
          |      +--> ContextRefreshedEvent
          |
          +--> callback nhận AssertableApplicationContext
          |      +--> assert bean/config/lifecycle state
          |      +--> ApplicationRunner vẫn CHƯA được Boot gọi
          |      +--> ApplicationReadyEvent CHƯA được Boot phát
          |
          +--> runner tự close context
                 +--> ContextClosedEvent
                 +--> LifecycleProcessor.onClose()
                 +--> @PreDestroy / destroy bean callbacks
   |
   +--> test method tiếp tục/hoàn tất
```

Chú ý: từ “`run`” trong `runner.run(callback)` chỉ có nghĩa **thực hiện một lần chạy thử context**. Nó không có nghĩa “chạy các Spring Boot startup runner beans”.

### 3.2. SpringApplication.run

```text
SpringApplication.run(...)
   |
   +--> ApplicationStartingEvent
   +--> chuẩn bị Environment
   +--> ApplicationEnvironmentPreparedEvent
   +--> ApplicationContextInitializedEvent
   +--> load bean definitions
   +--> ApplicationPreparedEvent
   +--> context.refresh()
   |      +--> @PostConstruct / bean initialization
   |      +--> SmartLifecycle auto-start
   |      +--> ContextRefreshedEvent
   |
   +--> ApplicationStartedEvent
   +--> AvailabilityChangeEvent(LivenessState.CORRECT)
   +--> ApplicationRunner / CommandLineRunner
   +--> ApplicationReadyEvent
   +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   +--> return running context
```

Đây là timeline **startup thành công** của Spring Boot 3.3. Nó rút gọn các bước nội bộ và **không** khẳng định một `@EventListener` bean có thể bắt mọi early event: các event rất sớm xuất hiện trước khi bean listener được tạo, nên phải đăng ký listener vào `SpringApplication`/`spring.factories` nếu cần quan sát chúng.

Ở đường thất bại, `ApplicationFailedEvent` có thể được gửi và cleanup được thực hiện trong khả năng hiện có. Không phải đường thành công nào trong sơ đồ cũng sẽ chạy.

### 3.3. Điều dễ nhầm nhất: ContextRefreshedEvent không phải ApplicationReadyEvent

`ContextRefreshedEvent` nói rằng quá trình **refresh của một context** đã hoàn tất theo hợp đồng Framework. Nhưng trong Spring Boot 3.3, `ApplicationStartedEvent` đến **sau refresh**, rồi Boot mới gọi các runners, rồi mới phát `ApplicationReadyEvent` và trạng thái `ReadinessState.ACCEPTING_TRAFFIC`.

Vì vậy, trong test:

```java
assertThat(context.isActive()).isTrue();
```

**không đủ** để kết luận:

```text
Boot đã phát ApplicationReadyEvent
mọi ApplicationRunner đã chạy
readiness đã chuyển ACCEPTING_TRAFFIC
web server đã mở cổng và phục vụ HTTP thật
```

Đây là các kết luận khác cấp lifecycle. Muốn khẳng định chúng, phải dùng loại test và assertion tương ứng.

## 4. Mốc nào thật sự hoạt động trong ApplicationContextRunner?

### 4.1. @PostConstruct và bean initialization

`AnnotationConfigApplicationContext.refresh()` vẫn là Spring Framework refresh. Các non-lazy singleton được tạo và nhận lifecycle initialization callbacks như `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()` khi phù hợp.

Điều này có nghĩa `ApplicationContextRunner` phù hợp để thử:

- Constructor injection có đủ dependency không.
- BeanPostProcessor có xử lý annotation đúng không.
- Bean được tạo theo conditional/property nào.
- `@PostConstruct` chạy và xác minh nội bộ dữ liệu đầu vào.
- Một bean lỗi khi init có khiến **context startup failure** được ghi nhận không.

Nhưng không nên viết test có side effect ngoài lớn trong `@PostConstruct` nếu mục tiêu chỉ là unit/auto-config test; mỗi `runner.run` có thể tạo/destroy context riêng.

### 4.2. SmartLifecycle.start() và stop() vẫn được gọi

`LifecycleProcessor` là một phần của Spring Framework context refresh/close. Bean `SmartLifecycle` với `isAutoStartup() == true` được khởi động khi refresh; khi context đóng bình thường, các lifecycle beans đang running được dừng theo thứ tự phase, có thể dùng `stop(Runnable callback)`.

Điều này **không đòi hỏi `SpringApplication.run`**. Một test `ApplicationContextRunner` có thể quan sát:

```text
@PostConstruct
SmartLifecycle.start
ContextRefreshedEvent
... callback assertions ...
ContextClosedEvent
SmartLifecycle.stop
@PreDestroy
```

Nhưng start/stop ở đây là **mốc của context/component**, không phải việc Boot đã qua started/ready.

### 4.3. ContextRefreshedEvent và ContextClosedEvent

Đây là `ApplicationContextEvent` của **Spring Framework**, phát bởi chính context. Một `@EventListener` bean được đăng ký đúng có thể nhận các sự kiện này trong test context runner bình thường.

Khi lambda của `runner.run(...)` return, runner tự đóng context. Vì vậy `ContextClosedEvent`, `SmartLifecycle.stop` và destruction callbacks thuộc **giai đoạn sau callback**. Nếu muốn assert chúng, giữ một collector ở ngoài test context rồi assert **sau khi `run` return**. Đừng đặt assertion “`@PreDestroy` đã chạy” ngay **bên trong** callback khi context còn sống.

### 4.4. Có thể tùy biến context nhưng không tự biến nó thành SpringApplication

Runner có các công cụ:

- `withUserConfiguration(...)` thêm configuration classes do người dùng chọn.
- `withConfiguration(AutoConfigurations.of(...))` thêm auto-configuration classes chủ đích.
- `withPropertyValues("x=y")` tùy biến Environment cho từng testcase.
- `withBean(...)` thêm một bean test nhỏ, kể cả supplier trả collector/mock.
- `withInitializer(...)` thêm `ApplicationContextInitializer` chạy **trong quá trình dựng context thử**.
- `withClassLoader(...)` mô phỏng classpath bị lọc để kiểm `@ConditionalOnClass`.
- `withParent(...)` cung cấp parent context khi thực sự cần kiểm tra điều kiện hierarchy.
- `withSystemProperties(...)` điều chỉnh test system properties theo contract runner.

**Không nhầm `withInitializer(...)` với việc Boot tự phát `ApplicationContextInitializedEvent`.** Initializer được gọi theo cơ chế test runner, nhưng không có nguyên một `SpringApplication` instance đi qua Boot event pipeline.

## 5. Những mốc SpringApplication KHÔNG tự chạy

### 5.1. Các sự kiện sớm

Trong Boot 3.3 có các sự kiện cấp SpringApplication:

1. `ApplicationStartingEvent`.
2. `ApplicationEnvironmentPreparedEvent`.
3. `ApplicationContextInitializedEvent`.
4. `ApplicationPreparedEvent`.

Chúng được phát khi `SpringApplication` chuẩn bị bootstrap, không phải là sản phẩm tất yếu của một `AnnotationConfigApplicationContext.refresh()`. Vì vậy `ApplicationContextRunner` không tự phát chúng.

Nếu muốn kiểm tra một `ApplicationListener<ApplicationStartingEvent>`, cần đăng ký listener **trước khi SpringApplication chạy**. Chỉ tạo bean listener trong context là quá muộn để bắt nhiều early events.

### 5.2. ApplicationStartedEvent không tự phát

`ApplicationStartedEvent` được Boot phát sau context refresh, trước runners. `ApplicationContextRunner` chỉ gọi refresh theo thiết lập test nên không có thành phần Boot gọi event này.

Một test có thể pass mọi assertion về bean và `SmartLifecycle` mà vẫn **không chứng minh** listener cho `ApplicationStartedEvent` sẽ chạy đúng khi ứng dụng được khởi động thực.

### 5.3. ApplicationRunner và CommandLineRunner không tự được gọi

Cả hai đều là Spring beans; context runner có thể **tạo và inject** chúng. Nhưng phương thức `run(...)` tương ứng không phải callback mặc định của Spring Framework `refresh()`.

Spring Boot có bước riêng trong `SpringApplication.run(...)`:

```java
// Chữ ký của Spring Boot interface, không phải code phải tự viết.
void run(ApplicationArguments args) throws Exception;
void run(String... args) throws Exception;
```

Đoạn trên lần lượt diễn giải `ApplicationRunner` và `CommandLineRunner`. Container chỉ tạo object; **SpringApplication** mới điều phối gọi method của chúng trong startup thành công.

Trong test context runner, bean runner vẫn có thể tồn tại:

```java
assertThat(context).hasSingleBean(ApplicationRunner.class);
```

nhưng body `ApplicationRunner.run` chưa được gọi bởi Boot. Một assertion kiểm tra bean tồn tại **không phải** assertion kiểm tra code khởi động bên trong runner.

### 5.4. ApplicationReadyEvent và readiness không tự xảy ra

Boot phát `ApplicationReadyEvent` **sau khi** các runners hoàn tất bình thường, rồi phát `AvailabilityChangeEvent<ReadinessState>` biểu diễn `ACCEPTING_TRAFFIC`. `ApplicationContextRunner` không chạy chuỗi đó.

Không tự cho rằng:

- `ApplicationAvailability.getReadinessState() == ACCEPTING_TRAFFIC`;
- readiness probe/Actuator health group đã chuyển ready;
- container readiness orchestration đã được cập nhật;
- listener `@EventListener(ApplicationReadyEvent.class)` đã chạy.

Không nên assert “readiness == REFUSING_TRAFFIC” bằng cách vô điều kiện chỉ vì runner không phát ready, bởi **bản thân `ApplicationAvailability` có thể chưa được đăng ký trong context thử tối giản**. Đây là giới hạn về thành phần có mặt trong context, không phải một trạng thái Boot đã công bố.

### 5.5. ApplicationFailedEvent và FailureAnalyzer không tự chạy

Nếu `ApplicationContextRunner` refresh một bean lỗi, nó có thể trả một **failed context** vào callback cùng thông tin `getStartupFailure()`. Điều đó **không có nghĩa** Boot đi qua `SpringApplication.handleRunFailure(...)` để phát `ApplicationFailedEvent` và gọi `FailureAnalyzer`/`FailureAnalysisReporter`.

Phân biệt hai thứ:

- **Runner test failure**: failure nằm ở việc dựng/refresh test context, test trực tiếp assert `getStartupFailure()`.
- **Boot startup failure**: `SpringApplication.run` thực hiện pipeline xử lý startup failure riêng; trong điều kiện phù hợp có thể phát `ApplicationFailedEvent` và trình bày analysis.

Nếu cần kiểm chứng **thông điệp failure analysis** hoặc việc reporter được đăng ký bằng `spring.factories`, hãy thiết kế test khởi động bằng `SpringApplication` thật thay vì chỉ xem context runner có failure.

### 5.6. WebServerInitializedEvent và việc mở port

`new ApplicationContextRunner()` dùng context non-web. Nó không tự mở embedded Tomcat/Netty và không có `WebServerInitializedEvent` do web server startup.

`WebApplicationContextRunner` / `ReactiveWebApplicationContextRunner` phù hợp để mô phỏng **web application context** và kiểm auto-configuration web, nhưng chúng cũng **không phải một HTTP end-to-end test tự mở port thực theo mặc định**. Muốn assert socket binding, web server ready, actual HTTP request hay SSL, hãy dùng test web/integration tương ứng.

## 6. Khi nào ApplicationContextRunner là lựa chọn tốt nhất?

| Mục tiêu test | Context runner có phù hợp? | Nên kiểm điều gì? |
| --- | --- | --- |
| `@ConditionalOnProperty` tạo/không tạo bean | **Rất phù hợp** | Bean presence/absence theo property |
| `@ConditionalOnMissingBean` nhường user bean | **Rất phù hợp** | Default bean backed off |
| ConfigurationProperties binding và validation | Phù hợp nếu đăng ký binder/annotations cần thiết | Bean properties và startup failure |
| `@PostConstruct` hay init method | Phù hợp | State ngay sau refresh |
| `SmartLifecycle.start/stop` và `ContextRefreshedEvent` | Phù hợp | Quan hệ lifecycle context |
| `@PreDestroy` và close order | Phù hợp | Assert collector sau run callback |
| `ApplicationRunner.run` chạy đúng trong SpringApplication | **Không đủ** | Integration test qua `SpringApplication.run` |
| `ApplicationStartedEvent`/`ApplicationReadyEvent` | **Không đủ** | Boot event listener thực khi startup |
| Readiness / liveness state transitions | **Không đủ** nếu không chạy Boot pipeline | Test `ApplicationAvailability` trong Boot app |
| Embedded web server bind port/HTTP thật | **Không đủ** | `@SpringBootTest(webEnvironment=RANDOM_PORT)` hoặc process test |
| `FailureAnalysisReporter` trên startup failure | Không đủ | Boot failure path/launcher test |
| Startup dependency graph nhỏ, failure context | **Phù hợp** | `getStartupFailure()` |
| Toàn bộ application packages, scan và auto config thật | Không mặc định | Test slice/full integration tùy yêu cầu |

Mục tiêu không phải làm càng nhiều test full Boot càng tốt. Cần **test nhỏ đúng phạm vi**, rồi thêm **một số test Boot startup thật** cho những mốc cấp ứng dụng. Context runner đặc biệt nhanh và rõ khi muốn thử nhiều tổ hợp property/classpath mà không mở database/server.

## 7. Ví dụ hoàn chỉnh: bốn bài test Java 17+ về ranh giới lifecycle

Ví dụ có hai dòng kiểm chứng quan trọng:

- **Test A:** context runner refresh và đóng context; thấy init/start/refreshed/closed/stop/destroy nhưng **không** thấy các event/runner thuộc Boot.
- **Test B:** dùng `SpringApplication.run(...)` trong test riêng; thấy các event Boot và cả hai runner được thực thi, đồng thời vẫn thấy lifecycle context.
- **Test C:** dùng context runner kiểm property-based bean graph mà không bootstrap cả app.
- **Test D:** cố tạo một bean lỗi trong refresh, kiểm `getStartupFailure()` mà không nhầm với `ApplicationFailedEvent`.

Các test **không phụ thuộc số mili-giây, Thread.sleep hoặc thứ tự bean không được contract bảo đảm**. Phép thử dùng một bộ thu sự kiện được truyền vào context để quan sát thứ tự chính.

### 7.1. Cấu trúc project

```text
context-runner-lifecycle-lab/
├── build.gradle
├── settings.gradle
└── src/
    └── test/
        └── java/com/example/lifecycle/
            └── LifecycleBoundaryTest.java
```

Chỉ có một file Java test chứa các cấu hình/bean nhỏ dạng nested static class. Chúng ta **không cần file `@SpringBootApplication` thật** cho test này, vì `SpringApplication` chấp nhận một `@Configuration` làm source; các bean trong ví dụ tự đủ.

### 7.2. build.gradle

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` cung cấp Spring Boot Test, JUnit Jupiter, AssertJ và các công cụ test liên quan. Vì `ApplicationContextRunner` thuộc `spring-boot-test`, chỉ dựa vào `spring-boot-starter` runtime sẽ **không** có API này trên compile classpath của code production. Giữ code context runner trong `src/test/java`.

File `settings.gradle`:

```groovy
rootProject.name = 'context-runner-lifecycle-lab'
```

### 7.3. Toàn bộ file LifecycleBoundaryTest.java

Tạo file **`src/test/java/com/example/lifecycle/LifecycleBoundaryTest.java`**:

```java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.junit.jupiter.api.Test;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleBoundaryTest {

    @Test
    void contextRunnerRefreshesButSkipsBootOnlyMilestones() {
        Timeline timeline = new Timeline();

        new ApplicationContextRunner()
                .withBean(Timeline.class, () -> timeline)
                .withUserConfiguration(ProbeConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ObservedComponent.class);
                    assertThat(context).hasSingleBean(ApplicationRunner.class);
                    assertThat(context).hasSingleBean(CommandLineRunner.class);
                    assertThat(context.getBean(ObservedComponent.class).isRunning())
                            .isTrue();

                    // Đã qua refresh và SmartLifecycle.start,
                    // nhưng chưa qua SpringApplication.start/ready/runners.
                    assertThat(timeline.snapshot()).containsExactly(
                            "bean.init",
                            "smart.start",
                            "context.refreshed");
                });

        // ApplicationContextRunner tự đóng context sau callback.
        assertThat(timeline.snapshot()).containsExactly(
                "bean.init",
                "smart.start",
                "context.refreshed",
                "context.closed",
                "smart.stop",
                "bean.destroy");
    }

    @Test
    void actualSpringApplicationInvokesBootRunnersAndEvents() {
        Timeline timeline = new Timeline();

        SpringApplication app = new SpringApplication(ProbeConfiguration.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Đăng ký một singleton trước khi config beans được khởi tạo.
        app.addInitializers(context ->
                context.getBeanFactory().registerSingleton(
                        "timeline", timeline));

        try (ConfigurableApplicationContext context = app.run()) {
            assertThat(context.isActive()).isTrue();

            List<String> events = timeline.snapshot();

            assertThat(events).contains(
                    "bean.init",
                    "smart.start",
                    "context.refreshed",
                    "boot.started",
                    "boot.applicationRunner",
                    "boot.commandLineRunner",
                    "boot.ready");

            // Không giả định thứ tự giữa hai runner cùng order.
            assertThat(events.indexOf("context.refreshed"))
                    .isLessThan(events.indexOf("boot.started"));
            assertThat(events.indexOf("boot.started"))
                    .isLessThan(events.indexOf("boot.applicationRunner"));
            assertThat(events.indexOf("boot.started"))
                    .isLessThan(events.indexOf("boot.commandLineRunner"));
            assertThat(events.indexOf("boot.applicationRunner"))
                    .isLessThan(events.indexOf("boot.ready"));
            assertThat(events.indexOf("boot.commandLineRunner"))
                    .isLessThan(events.indexOf("boot.ready"));
        }

        assertThat(timeline.snapshot()).contains(
                "context.closed",
                "smart.stop",
                "bean.destroy");
    }

    @Test
    void contextRunnerCanTestPropertyDrivenBeanGraphs() {
        ApplicationContextRunner runner = new ApplicationContextRunner()
                .withUserConfiguration(ConditionalFeatureConfiguration.class);

        runner.withPropertyValues("feature.enabled=true").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(Feature.class);
            assertThat(context.getBean(Feature.class).name())
                    .isEqualTo("ENABLED");
        });

        runner.withPropertyValues("feature.enabled=false").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(Feature.class);
        });
    }

    @Test
    void failedContextIsInspectableWithoutBootFailureEvent() {
        new ApplicationContextRunner()
                .withUserConfiguration(BrokenConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }

    static final class Timeline {
        private final List<String> steps = new CopyOnWriteArrayList<>();

        void add(String value) {
            steps.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(steps);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ProbeConfiguration {

        @Bean
        ObservedComponent observedComponent(Timeline timeline) {
            return new ObservedComponent(timeline);
        }

        @Bean
        EventProbe eventProbe(Timeline timeline) {
            return new EventProbe(timeline);
        }

        @Bean
        ApplicationRunner applicationRunner(Timeline timeline) {
            return args -> timeline.add("boot.applicationRunner");
        }

        @Bean
        CommandLineRunner commandLineRunner(Timeline timeline) {
            return args -> timeline.add("boot.commandLineRunner");
        }
    }

    static final class ObservedComponent implements SmartLifecycle {
        private final Timeline timeline;
        private volatile boolean running;

        ObservedComponent(Timeline timeline) {
            this.timeline = timeline;
        }

        @PostConstruct
        public void init() {
            timeline.add("bean.init");
        }

        @Override
        public void start() {
            running = true;
            timeline.add("smart.start");
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                timeline.add("smart.stop");
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
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
            return 100;
        }

        @PreDestroy
        public void destroy() {
            timeline.add("bean.destroy");
        }
    }

    static final class EventProbe {
        private final Timeline timeline;

        EventProbe(Timeline timeline) {
            this.timeline = timeline;
        }

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            timeline.add("context.refreshed");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            timeline.add("context.closed");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            timeline.add("boot.started");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            timeline.add("boot.ready");
        }
    }

    record Feature(String name) {
    }

    @Configuration(proxyBeanMethods = false)
    static class ConditionalFeatureConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "feature",
                name = "enabled",
                havingValue = "true")
        Feature feature() {
            return new Feature("ENABLED");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfiguration {

        @Bean
        Object brokenBean() {
            throw new IllegalStateException("intentional refresh failure");
        }
    }
}
```

### 7.4. Vì sao test A kiểm chứng đúng ranh giới?

Phần đầu test A truyền một `Timeline` object từ **ngoài context** vào bằng `withBean(Timeline.class, () -> timeline)`. Nhờ giữ reference ở test, ta còn đọc được các dấu mốc **sau khi context runner đã tự đóng context**.

Trong refresh thành công:

1. `ObservedComponent` được tạo và gọi `@PostConstruct` → `bean.init`.
2. `DefaultLifecycleProcessor.onRefresh()` gọi `SmartLifecycle.start()` → `smart.start`.
3. Spring Framework phát `ContextRefreshedEvent` → `context.refreshed`.
4. Callback `runner.run(context -> ...)` được gọi; hai bean `ApplicationRunner`/`CommandLineRunner` **tồn tại** nhưng body của chúng **chưa được Boot gọi**.
5. Không có `ApplicationStartedEvent`/`ApplicationReadyEvent`, vì không có `SpringApplication.run`.

Vì vậy `timeline.snapshot()` ngay **trong** callback có nội dung mong đợi:

```text
[bean.init, smart.start, context.refreshed]
```

Sau khi callback return, runner đóng context:

1. `ContextClosedEvent` → `context.closed`.
2. `SmartLifecycle.stop(Runnable)` → `smart.stop`, callback được báo.
3. Spring destroy singleton → `@PreDestroy` → `bean.destroy`.

Snapshot lúc đó:

```text
[bean.init, smart.start, context.refreshed, context.closed, smart.stop, bean.destroy]
```

Hai danh sách này là **giá trị assertion của collector**, không phải stdout mà chương trình Java tự in. File test không gọi `System.out.println`, do đó **không được hứa Gradle console sẽ in hai danh sách**. Điều có thể kiểm chứng là JUnit assertions pass khi runtime/framework phù hợp.

### 7.5. Vì sao test B không khẳng định thứ tự hai runner?

Test B **cố ý gọi một `SpringApplication` thực** với `ProbeConfiguration`. Nó không dùng `new ApplicationContextRunner()`. Khi startup:

```text
bean.init
smart.start
context.refreshed
boot.started
boot.applicationRunner / boot.commandLineRunner (thứ tự tương đối không ép)
boot.ready
```

Hai runner đều có **order mặc định**, nên test **chỉ assert cả hai chạy sau started và trước ready**. Không assertion “ApplicationRunner luôn trước CommandLineRunner” khi không có `@Order`/`Ordered` rõ ràng.

`ApplicationContextInitializer` ở test B đăng ký `Timeline` vào bean factory **trước khi tạo các config beans**, để cả runner và event probe cùng dùng một collector ngoài context. Đây là một cách đưa dependency vào integration test, **không nên hiểu** initializer trên test B giống với việc gọi `withInitializer(...)` trong context runner có đủ Boot lifecycle.

Khi test B ra khỏi `try-with-resources`, context được đóng và các mốc `context.closed`, `smart.stop`, `bean.destroy` có thể được quan sát theo đường shutdown bình thường.

### 7.6. Vì sao test C quan trọng?

`@ConditionalOnProperty` chạy ở mức bean definition/condition evaluation trong quá trình refresh. Vì vậy:

```java
runner.withPropertyValues("feature.enabled=true")
        .run(context -> assertThat(context).hasSingleBean(Feature.class));
```

là cách **đúng cấp** để test điều kiện tạo bean, không cần phát `ApplicationReadyEvent`. Test `false` kiểm rằng bean không được tạo.

Đây là một trong những công dụng chính thức mà Spring Boot khuyến nghị đối với `ApplicationContextRunner`: khảo sát những tổ hợp property và user configurations của auto-configuration.

### 7.7. Vì sao test D dùng getStartupFailure?

Với `BrokenConfiguration`, bean factory cố tạo `brokenBean` trong refresh và method `@Bean` ném `IllegalStateException`. Spring có thể bọc nó trong `BeanCreationException`, nên test assert **root cause type** thay vì assert top-level class là chính xác một loại exception.

`ApplicationContextRunner` giữ failure để callback kiểm:

```java
assertThat(context).hasFailed();
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(IllegalStateException.class);
```

Đây là **đoạn trích từ file test đầy đủ**. Nó kiểm failure ở **context refresh**, không kiểm `ApplicationFailedEvent` của `SpringApplication`. Sự khác biệt này cần giữ rõ trong tên test và báo cáo QA.

### 7.8. Chạy test

Cần Gradle Wrapper tương thích Java 17. Từ thư mục dự án:

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Để chỉ chạy một file test:

```bash
./gradlew test --tests "com.example.lifecycle.LifecycleBoundaryTest"
```

Nếu project được cấu hình đúng và tất cả assertions pass, Gradle báo test task thành công. **Không đưa stdout cố định kiểu “4 tests passed” như một output của Java**, vì định dạng Gradle test report phụ thuộc cấu hình/phiên bản launcher. Xem chi tiết trong `build/reports/tests/test/index.html` nếu test runner tạo HTML report ở vị trí mặc định.

### 7.9. Giới hạn của ví dụ

- Đây là **một dự án test**; class `LifecycleBoundaryTest` nằm ở `src/test/java`.
- `ProbeConfiguration` có các bean tối thiểu, không kích hoạt toàn bộ `@SpringBootApplication` auto-configuration.
- Test B vẫn dùng `SpringApplication` thật để xác minh phân biệt lifecycle, nhưng cố ý chọn `WebApplicationType.NONE` để không tạo web server/port.
- Test A có thể xác nhận các mốc Spring Framework context; nó **không thể thay** test Boot startup/ready event.
- Khi người dùng thêm executor, listener bất đồng bộ hoặc bean auto-config khác, thứ tự callback cụ thể phải được kiểm lại theo dependency và thread policy.


## 8. Test auto-configuration thực tế bằng ApplicationContextRunner

Ví dụ trước dùng `withUserConfiguration(...)`. Trong auto-configuration library hoặc starter, pattern thông dụng là:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyFeatureAutoConfiguration.class));
```

Đây là **đoạn minh họa**, cần import `org.springframework.boot.autoconfigure.AutoConfigurations`, `ApplicationContextRunner` và một class `MyFeatureAutoConfiguration` thật. `AutoConfigurations.of(...)` dùng để đưa auto-configuration classes **được chỉ định** vào test theo quy tắc ordering phù hợp; không tự scan toàn bộ classpath.

Với một auto-configuration cung cấp default bean:

```java
runner.run(context -> {
    assertThat(context).hasSingleBean(MyService.class);
});

runner.withUserConfiguration(UserOverrideConfiguration.class)
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
            assertThat(context.getBean(MyService.class))
                    .isSameAs(context.getBean("customMyService"));
        });
```

Các đoạn trên là **snippet minh họa**; cần class definitions tương ứng. Mục tiêu là kiểm `@ConditionalOnMissingBean` back-off khi user định nghĩa bean riêng.

### 8.1. Lợi ích của runner bất biến theo các customization

Các method `with...` thường tạo **một runner có cấu hình bổ sung** để tái sử dụng an toàn giữa testcases. Nên đặt một `private final ApplicationContextRunner baseRunner` và viết từng test bằng `baseRunner.withPropertyValues(...)`. Đừng viết code phụ thuộc vào việc thay property trong test A làm test B đổi theo.

Trong test C, `runner.withPropertyValues("feature.enabled=true")` và `...false` tạo hai ngữ cảnh thử **độc lập**. Mỗi `run` có refresh/close riêng; không dùng cùng context từ test trước để tránh state leak.

### 8.2. withPropertyValues không mô phỏng toàn bộ config data pipeline

`withPropertyValues("feature.enabled=true")` thêm property cho test Environment. Nó phù hợp với `@ConditionalOnProperty`/binding, nhưng không nên suy rằng nó chứng minh:

- Toàn bộ profile activation giống production.
- Config Data API đã nạp đủ file `application.yml`, environment variables, cloud config và secret manager.
- Command-line arguments đã được `SpringApplication` parse đầy đủ.
- Placeholder resolution từ mọi nguồn ngoài được thực thi đúng như process deploy.
- System property có thể bị override không đúng thứ tự trong một bootstrap custom.

Nếu lỗi liên quan **Config Data loading/profile activation/command-line precedence**, dùng integration test có `SpringApplication` thật hoặc process test với đúng config sources.

### 8.3. withBean hỗ trợ thay dependency thật trong test

Một lớp auto-config có thể cần `Clock`, `DataSource`, một client service hoặc `SomeProperties`. Với runner, có thể cung cấp bean test:

```java
new ApplicationContextRunner()
        .withBean(Clock.class, () -> Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC))
        .withUserConfiguration(MyConfiguration.class)
        .run(context -> {
            // Assert bean cần Clock hoạt động theo thời gian cố định.
        });
```

Đây là **snippet**, cần imports `java.time.Clock`, `Instant`, `ZoneOffset` và class `MyConfiguration`. Nó cho thấy cách kiểm test deterministic, không phải một công cụ để mô phỏng SpringApplication Ready event.

### 8.4. withClassLoader để giả lập thiếu dependency

`FilteredClassLoader` có thể làm một số class/package biến mất khỏi góc nhìn test context để kiểm `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass`.

```java
new ApplicationContextRunner()
        .withClassLoader(new FilteredClassLoader(
                "com.example.optional"))
        .withConfiguration(AutoConfigurations.of(
                MyFeatureAutoConfiguration.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(OptionalFeature.class);
        });
```

Đây là **snippet minh họa** cần các class tương ứng và import `org.springframework.boot.test.context.FilteredClassLoader`. Có thể dùng khi kiểm một auto-config thư viện tùy chọn, nhưng không đồng nghĩa chạy một Java process với classpath thật đã bị cắt dependency; những integration startup quan trọng vẫn cần process/classpath test phù hợp.

### 8.5. ConditionEvaluationReport và diagnostic conditions

Khi bean không xuất hiện, đừng vội kết luận lỗi test runner. Kiểm `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và thứ tự import auto-config.

Spring Boot cho phép thêm một initializer dùng để log condition evaluation report:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(
                MyFeatureAutoConfiguration.class))
        .run(context -> {
            // Đọc kết quả condition và bean khi refresh.
        });
```

Đây là **snippet** dựa trên tài liệu chính thức, cần import `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` và `org.springframework.boot.logging.LogLevel`. Quan sát report giúp hiểu auto-config conditions nhưng **không làm xuất hiện các SpringApplication started/ready events**.

### 8.6. Hạn chế khi chạy native image

Tài liệu Spring Boot 3.3 nói rõ `ApplicationContextRunner` **không hoạt động khi chạy các tests trong native image**. Nếu dự án phải kiểm GraalVM native executable, chọn chiến lược test riêng cho native image, AOT processing và runtime; đừng giả định test context runner sẽ phản ánh đầy đủ native startup.

## 9. WebApplicationContextRunner và ReactiveWebApplicationContextRunner

Ngoài runner non-web mặc định, Spring Boot Test có:

- `WebApplicationContextRunner`: dựng servlet web application context trong test.
- `ReactiveWebApplicationContextRunner`: dựng reactive web application context.
- `ApplicationContextRunner`: context thường, non-web.

Ví dụ dùng web context runner:

```java
new WebApplicationContextRunner()
        .withUserConfiguration(MyMvcConfiguration.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            // Kiểm bean web MVC hoặc auto-configuration có trong context.
        });
```

Đây là **snippet**; cần dependency web và configuration phù hợp. Nó không tự có một HTTP server production-like, không tự gửi `ServletWebServerInitializedEvent` như một test embedded server thực sự và **không tự gọi `SpringApplication.run`**.

### 9.1. Khi cần kiểm listener cho WebServerInitializedEvent

`WebServerInitializedEvent` gắn với embedded web server khởi tạo thành công, không phải một dấu mốc bắt buộc của mọi context được refresh. Nếu một bean cần biết port động hoặc actual web server, dùng:

- `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`.
- `TestRestTemplate` hoặc `WebTestClient` theo web stack/phạm vi test.
- Hoặc process integration test khởi chạy JAR thật rồi gửi HTTP request.

Cần phân biệt **mock MVC context** và **socket thực sự LISTEN**. Cả hai hữu ích nhưng kiểm chứng các claim khác nhau.

### 9.2. ApplicationReadyEvent và web server binding

Trong Spring Boot 3.3, web server có thể được khởi tạo trong context refresh, còn `ApplicationReadyEvent` đến sau khi runners hoàn tất. Một server đã bind port **không tự chứng minh readiness của toàn ứng dụng**. Test ApplicationContextRunner không chứng minh cả port binding lẫn Boot ready event nếu không thiết kế test lớn hơn.

## 10. Kiểm chứng startup failure ở đúng tầng

Một ứng dụng có thể thất bại tại nhiều điểm khác nhau:

| Nơi lỗi | Context runner có thể bắt? | Cần Boot startup thật khi kiểm gì? |
| --- | --- | --- |
| `@Bean` factory method throw trong refresh | Có: `getStartupFailure()` | FailureAnalyzer/boot failure event/exit semantics |
| `@PostConstruct` throw | Có: refresh failure | Thông báo lỗi startup toàn Boot |
| `SmartLifecycle.start()` throw | Có: refresh failure | Các Boot event sau refresh bị chặn như thế nào |
| `ApplicationRunner.run()` throw | **Không tự gọi runner**, nên không tạo lỗi này | **Có**: SpringApplication xử lý runner failure |
| `ApplicationReadyEvent` listener throw | Runner không tự phát sự kiện | **Có**, nếu test cần kiểm đường lỗi khi ready |
| Servlet port bind collision | Non-web runner không mô phỏng | **Có**: embedded server/port thực |
| Config Data import/profile lỗi trước refresh | Không đầy đủ theo Boot pipeline | **Có**: SpringApplication environment preparation |
| Missing class auto-config condition | Có thể kiểm điều kiện bằng FilteredClassLoader | Process/classpath runtime nếu cần xác minh packaging |
| Exception tại @Scheduled sau khi app ready | Không phải startup failure | Runtime async error/monitoring test |

### 10.1. Failed context không phải ApplicationFailedEvent

Nếu test dùng:

```java
new ApplicationContextRunner()
        .withUserConfiguration(BrokenConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
```

đây là assertion **context refresh đã thất bại**. Không có cơ sở để assert `ApplicationFailedEvent`, `ExitCodeGenerator` hoặc `FailureAnalysisReporter` của Boot được gọi chỉ từ code này. Muốn các behavior ấy, cần test SpringApplication failure path hoặc process startup thật.

### 10.2. Không cố gọi runner bean thủ công rồi xem là đã kiểm Boot lifecycle

Một anti-pattern:

```java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .run(context -> {
            ApplicationRunner runner =
                    context.getBean(ApplicationRunner.class);

            runner.run(new DefaultApplicationArguments(new String[0]));
        });
```

Đây là **snippet minh họa** cần imports/classes và callback có khả năng ném exception; không độc lập. Nó có thể kiểm **logic của runner bean** với một `ApplicationArguments` giả lập. Nhưng:

- Không chứng minh Boot đã phát `ApplicationStartedEvent` trước đó.
- Không chứng minh cách Boot sắp tất cả runner beans theo `@Order`.
- Không chứng minh `ApplicationReadyEvent` được phát sau khi runner hoàn tất.
- Không chứng minh Boot xử lý exception của runner và đổi readiness như production.

Nếu chỉ cần unit test logic trong `ApplicationRunner.run`, có thể gọi trực tiếp; nhưng **không gọi đó là integration test SpringApplication lifecycle**.

### 10.3. Cẩn thận với side effects của SmartLifecycle

`ApplicationContextRunner` vẫn thực sự gọi `SmartLifecycle.start()` khi auto-start. Một message consumer có `start` kết nối tới broker thật có thể gây side effects hoặc treo test. Đây là **điểm đáng lưu ý** khi bạn tưởng context runner “chỉ build bean definitions”.

Biện pháp:

- Override/inject fake client bean bằng `withBean`.
- Dùng `isAutoStartup=false` trong config test nếu test không cần worker active.
- Giới hạn timeout I/O và đảm bảo stop callback kết thúc.
- Không dựa vào production credentials trong unit tests.
- Nếu đang kiểm startup protocol của consumer, dùng integration test với dependency giả lập/container phù hợp.

## 11. Lưu ý khi dùng @SpringBootTest làm bước kiểm chứng cao hơn

`@SpringBootTest` dùng hạ tầng Spring Boot Test để tạo một application context gần hơn với ứng dụng thật. Nó thường dùng `SpringApplication` để load ứng dụng và có thể thực hiện nhiều bước Boot startup, kể cả các runners khi context được khởi tạo theo đường chuẩn. Nhưng cần hiểu:

- Có context caching giữa tests; **không chắc `SpringApplication.run` chạy lại cho mỗi test method**.
- Mock beans, active profiles và test properties có thể làm startup khác production.
- `webEnvironment=MOCK` không nhất thiết tạo web server bind port thật.
- Các SpringApplication events quá sớm có thể xuất hiện **trước** khi những listener beans thông thường sẵn sàng.
- `@RecordApplicationEvents`/`ApplicationEvents` giúp test application events nhưng phải kiểm event capture scope và thời điểm đăng ký; không suy rằng một listener bean có thể quan sát event trước khi chính nó được tạo.

Nếu một yêu cầu cần chứng minh đầy đủ trình tự `ApplicationStartedEvent → runners → ApplicationReadyEvent`, **test B trong ví dụ là một cách rõ**: tự tạo `SpringApplication`, đăng ký collector và chỉ định application source tối thiểu, rồi gọi `run` thật. Với yêu cầu HTTP/production packaging, thêm integration test ở mức cao hơn tương ứng.

### 11.1. Không so sánh latency runner với production startup time

`ApplicationContextRunner` không load toàn bộ auto-configuration hay external integrations theo mặc định, và bỏ qua một phần SpringApplication bootstrap. Test chạy nhanh hơn **không chứng minh** rằng production startup cũng nhanh.

Nếu cần đo startup performance, dùng `ApplicationStartup`, `BufferingApplicationStartup`, Actuator startup endpoint hoặc profiling/test process thật, không lấy thời gian một context runner test làm thước đo tuyệt đối.

## 12. Các lỗi thường gặp và cách sửa

| Ngộ nhận/triệu chứng | Lý do | Cách xử lý |
| --- | --- | --- |
| “Runner `run` giống `SpringApplication.run`” | Hai API khác mục đích | Phân biệt context refresh và Boot bootstrap |
| “Context active = Boot ready” | Runners/availability xảy ra sau refresh | Kiểm `ApplicationReadyEvent` trong Boot test |
| “`ContextRefreshedEvent` = `ApplicationStartedEvent`” | Khác publisher và thời điểm | Chọn đúng event |
| “Có ApplicationRunner bean là runner đã chạy” | Bean chỉ được tạo/inject | Assert body ở Boot test, không chỉ presence |
| “Context runner refresh không chạy `@PostConstruct`” | Refresh vẫn gọi bean init | Test state after init |
| “SmartLifecycle không start vì không có SpringApplication” | LifecycleProcessor thuộc Framework context | Kiểm `isAutoStartup` và running state |
| “Runner tự giữ context sống sau callback” | Runner tự close khi callback return | Assert @PreDestroy sau `run` |
| “Context runner lỗi thì chắc có `ApplicationFailedEvent`” | Không qua Boot failure pipeline | Assert `getStartupFailure`; test Boot riêng |
| “`@EventListener(ApplicationReadyEvent)` trong context runner phải được gọi” | Không có Boot ready event | Gọi Boot startup thật |
| “Chỉ cần `withInitializer` là đã qua ApplicationContextInitializedEvent” | Customizer không phát Boot event | Phân biệt initializer callback và Boot event |
| “`withPropertyValues` giả lập đủ toàn bộ Config Data API” | Không phải full environment bootstrap | Dùng integration test theo nguồn config thật |
| “WebApplicationContextRunner mở port thật” | Web test context không tương đương embedded server | Dùng RANDOM_PORT/process HTTP |
| “ApplicationAvailability bắt buộc có trong runner” | Boot availability bean không được tự đảm bảo | Chỉ assert khi đăng ký/có đúng bean |
| “Runner mặc định scan toàn application và auto configs” | Chỉ config được nạp | `withConfiguration`/`withUserConfiguration` rõ ràng |
| “Tất cả auto-config đều phải được test bằng full `@SpringBootTest`” | Test nặng và khó cô lập conditions | Dùng context runner cho combinatorial tests |
| “Đã có Spring Boot test dependency nghĩa test chạy native image được” | Runner có hạn chế native image | Chọn native-specific testing |
| “Thứ tự giữa hai CommandLineRunner không cần @Order vẫn cố định” | Default tie không hứa business order | `@Order` hoặc `Ordered` |
| “Test failure phải assert top-level IllegalStateException” | Bean factory có thể wrap | Assert root cause |
| “Callback runner đóng context trước khi assert bên trong” | Context vẫn mở trong callback | Assert shutdown sau callback |
| “Test Boot full một lần = mọi test đều startup lại” | Context cache có thể tái sử dụng | Hiểu cache scope, dùng @DirtiesContext khi thật cần |
| “Có thể mở network và không đóng worker trong runner test” | SmartLifecycle auto-start thực | Fake resource, timeout, cleanup |
| “SpringApplication.run tự luôn gọi System.exit” | Boot run không đồng nghĩa JVM exit | Process exit code là trách nhiệm khác |

### 12.1. Checklist kiểm thử một milestone Spring Boot

1. Milestone muốn xác nhận thuộc **Spring Framework context** hay **SpringApplication**?
2. Nếu là bean init/`ContextRefreshedEvent`/`SmartLifecycle`, context runner có đủ.
3. Nếu là Boot started/ready/runner/availability, hãy dùng `SpringApplication.run`/integration test.
4. Xác định listener được đăng ký **trước hay sau** event; early events cần listener ngoài context.
5. Kiểm bean cần test thực sự được nạp qua `withUserConfiguration`/`withConfiguration`.
6. Dùng `withPropertyValues` cho conditional logic, nhưng nhớ scope test environment.
7. Nếu context failed, assert `getStartupFailure`; không cố lấy bean khi refresh fail.
8. Với close/destroy, ghi dấu trong collector nằm ngoài context rồi assert sau callback.
9. Nếu `SmartLifecycle` start một task async, chờ completion/cleanup đúng cách; không dùng sleep đoán timing.
10. Không assert thứ tự giữa các bean/runner không có contract `@Order`/phase/dependency.
11. Không lấy `ContextRefreshedEvent` làm bằng chứng Boot đã công bố readiness.
12. Khi cần socket/network thật, đổi sang web server integration test.
13. Đọc root cause/condition evaluation report khi bean không có như dự kiến.
14. Nếu test khác local/native image, kiểm giới hạn framework/test tool.
15. Không đưa secrets/production systems vào context runner test chỉ vì nó “nhanh”.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `ApplicationContextRunner.run` có gọi `SpringApplication.run` không?

**Đáp:** Không. Nó tạo/refresh một context được cấu hình cho test rồi tự close; do đó không tự chạy Boot startup pipeline.

**Câu 2.** `ContextRefreshedEvent` có được phát khi runner refresh thành công?

**Đáp:** Có, đây là Spring Framework context event.

**Câu 3.** Một bean `SmartLifecycle(isAutoStartup=true)` có được start trong context runner không?

**Đáp:** Có, vì `LifecycleProcessor.onRefresh` thuộc cơ chế context refresh.

**Câu 4.** `@PostConstruct` có chạy trong context runner không?

**Đáp:** Có khi bean được Spring khởi tạo theo cơ chế thích hợp, như non-lazy singleton trong ví dụ.

**Câu 5.** Bean `ApplicationRunner` tồn tại nghĩa body `run(ApplicationArguments)` đã được gọi?

**Đáp:** Không. Trong context runner, SpringApplication không tự điều phối gọi startup runners.

**Câu 6.** `ApplicationStartedEvent` có tự được phát bởi context runner sau refresh?

**Đáp:** Không. Event này thuộc pipeline `SpringApplication`.

**Câu 7.** `ApplicationReadyEvent` có tự được phát khi callback runner bắt đầu?

**Đáp:** Không. Callback test không phải Boot readiness event.

**Câu 8.** Vì sao không nên assert `ReadinessState.ACCEPTING_TRAFFIC` từ một context active?

**Đáp:** Vì Boot công bố readiness sau runner/ready event; context runner không tự đi qua các mốc đó, thậm chí có thể không có bean `ApplicationAvailability`.

**Câu 9.** Nếu một `@Bean` factory throw khi context runner refresh, dùng API nào?

**Đáp:** `context.getStartupFailure()` và AssertJ assertions về startup failure/root cause.

**Câu 10.** Runner test tự phát `ApplicationFailedEvent` khi context refresh fail không?

**Đáp:** Không theo contract SpringApplication; đó là failure của test context.

**Câu 11.** Khi nào `ContextClosedEvent` trong test được phát?

**Đáp:** Khi runner close context sau callback, trên đường đóng bình thường.

**Câu 12.** Làm sao kiểm `@PreDestroy` mà không phụ thuộc trạng thái context đã bị đóng?

**Đáp:** Dùng collector bên ngoài rồi assert sau lời gọi `runner.run(...)` return.

**Câu 13.** Làm sao kiểm `@ConditionalOnProperty` với hai giá trị mà không load toàn ứng dụng?

**Đáp:** Tạo một base ApplicationContextRunner, dùng `withPropertyValues` cho từng trường hợp và assert bean graph.

**Câu 14.** Nếu cần kiểm HTTP server mở port nào, dùng runner nào?

**Đáp:** Cần web integration test với embedded server thực, ví dụ `@SpringBootTest(webEnvironment=RANDOM_PORT)`, không dựa chỉ vào ApplicationContextRunner.

**Câu 15.** `withInitializer` có làm `ApplicationContextInitializedEvent` tự phát không?

**Đáp:** Không. Một custom context initializer có thể chạy nhưng không thay thế pipeline event Boot.

**Câu 16.** Vì sao không assert thứ tự hai runner cùng order mặc định?

**Đáp:** Spring Boot điều phối qua comparator/ordering, nhưng tie không phải hợp đồng business; đặt `@Order` hoặc `Ordered` nếu thứ tự quan trọng.

**Câu 17.** `ApplicationContextRunner` có phù hợp test trong native image theo Boot 3.3 không?

**Đáp:** Không theo giới hạn được tài liệu Boot 3.3 nêu; cần chiến lược native test riêng.

**Câu 18.** Muốn chứng minh `ApplicationStartedEvent` đến trước runner và `ApplicationReadyEvent` sau runner, chọn cách nào?

**Đáp:** Khởi động một `SpringApplication` thật với listener/collector được đăng ký phù hợp, assert thứ tự các mốc, như test B.

## 14. Tóm tắt và nguồn tham khảo

Các kết luận cốt lõi:

1. **`ApplicationContextRunner` là công cụ test ở tầng context**: dựng context nhỏ, refresh, cho callback assert và tự close.
2. **Context lifecycle vẫn chạy thật**: tạo bean, injection, `@PostConstruct`, `SmartLifecycle.start()`, `ContextRefreshedEvent`, và các callback close/stop/destroy khi runner đóng context.
3. **SpringApplication milestones không tự chạy**: `ApplicationStartingEvent`, `ApplicationStartedEvent`, `ApplicationRunner`/`CommandLineRunner`, `ApplicationReadyEvent`, các availability events và `ApplicationFailedEvent` của Boot.
4. **`ContextRefreshedEvent ≠ ApplicationReadyEvent`**. Context active không chứng minh app ready hoặc runners đã hoàn tất.
5. **Context failure khác Boot startup failure**: `getStartupFailure()` trong runner không tự kích hoạt Boot `FailureAnalyzer`/`FailureAnalysisReporter`.
6. **Tách lớp kiểm thử**: dùng context runner cho conditions/bean/lifecycle context, rồi thêm `SpringApplication.run`/`@SpringBootTest`/process test cho event, runner, HTTP, availability và startup failure thực.
7. **Test tự đóng context** sau callback; assert stop/destruction ở ngoài callback bằng collector. Đừng để background worker thật chạy/treo trong context runner.
8. **Đúng dependency**: `ApplicationContextRunner` thuộc `spring-boot-test`, thường nằm trong `spring-boot-starter-test` ở `testImplementation`.

Tài liệu chính thức tương ứng Spring Boot 3.3.13:

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner`, `AutoConfigurations.of`, properties, user config, FilteredClassLoader; lưu ý native image.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): context non-web và default `AnnotationConfigApplicationContext`.
- [Spring Boot 3.3.13 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `run`/`prepare`, `withBean`, `withConfiguration`, `withUserConfiguration`, `withPropertyValues` và auto-close.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): Boot events, started/ready, runners, availability và startup failure.
- [Spring Boot 3.3.13 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): bootstrapping, context refresh và `CommandLineRunner` callback.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, web environment và test context cache.
- [Spring Framework 6.1 — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh/close, `ContextRefreshedEvent`, `ContextClosedEvent` và lifecycle processor.

**Kết luận:** Khi đọc tên `ApplicationContextRunner.run`, đừng hiểu chữ “run” theo nghĩa `SpringApplication.run`. Nó chứng minh **context có thể refresh và các bean thực hiện đúng contract nội bộ**; muốn chứng minh **ứng dụng Boot đã started, chạy runner, ready, công bố availability hoặc báo startup failure** thì phải chạy bộ điều phối `SpringApplication` trong một test phù hợp.
