# Phân biệt RunListener với ApplicationListener và runner trong Spring Boot 3.3

## 1. Mục tiêu

Trong Spring Boot, từ “listener” và “runner” dễ gây nhầm lẫn vì đều liên quan đến `SpringApplication.run(...)`. Tuy nhiên, ba nhóm điểm mở rộng này giải quyết **ba loại nhu cầu khác nhau**:

1. **`SpringApplicationRunListener`** theo dõi chính chuỗi gọi `SpringApplication.run(...)`, từ những bước bootstrap đầu tiên cho tới thành công hoặc thất bại.
2. **`ApplicationListener<E>`** phản ứng với **sự kiện Spring** cụ thể; tùy cách đăng ký, nó có thể nhận sự kiện rất sớm hoặc sự kiện phát sinh khi ứng dụng đang chạy.
3. **`ApplicationRunner` / `CommandLineRunner`** là các **Spring bean được Boot gọi để thực hiện công việc sau khi context đã refresh**, trước mốc ứng dụng được báo sẵn sàng.

Bài này dùng **Spring Boot 3.3 và Java 21** để phân biệt chính xác API, thời điểm, cách đăng ký, dữ liệu nhận được, khả năng dùng dependency injection (DI), cách xử lý lỗi và các tình huống lựa chọn. Cuối bài có ví dụ Maven hoàn chỉnh chạy được.

**Câu hỏi định hướng:** Bạn cần theo dõi **toàn bộ quá trình `run()`**, nhận **một loại application event**, hay **thực hiện một tác vụ khởi tạo cần Spring bean**? Trả lời câu hỏi này sẽ giúp chọn đúng extension point.

## 2. So sánh tổng quan

| Tiêu chí | `SpringApplicationRunListener` | `ApplicationListener<E>` | `ApplicationRunner` / `CommandLineRunner` |
| --- | --- | --- | --- |
| Bản chất | SPI quan sát các pha của `SpringApplication.run()` | Listener trong cơ chế Spring application events | Bean có callback `run(...)` để thực hiện startup task |
| Phương thức chính | `starting`, `environmentPrepared`, `contextPrepared`, `contextLoaded`, `started`, `ready`, `failed` | `onApplicationEvent(E event)` | `run(ApplicationArguments)` hoặc `run(String... args)` |
| Thời điểm | Nhiều mốc từ rất sớm đến cuối startup | Khi event phù hợp được phát; tùy registration | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` |
| Phụ thuộc vào bean container? | Không được giả định container đã sẵn sàng | Listener đăng ký sớm không cần bean; listener dạng bean chỉ có khi container tạo bean | Có; runner là bean do Spring quản lý |
| Cách đăng ký phổ biến | `META-INF/spring.factories`, khóa `org.springframework.boot.SpringApplicationRunListener` | `SpringApplication.addListeners(...)`, `spring.factories`, hoặc bean/`@EventListener` cho event muộn | `@Component` hoặc `@Bean` trả về runner |
| Có nhận tham số CLI? | Constructor `(SpringApplication, String[])` | Một số `SpringApplicationEvent` cung cấp `getArgs()` | `ApplicationArguments` có cấu trúc hoặc `String...` thô |
| Dùng khi nào? | Tích hợp bootstrap cấp framework/infrastructure, đo các pha khởi động | Quan sát sự kiện/lifecycle, xử lý event ứng dụng | Warm-up có kiểm soát, kiểm tra dữ liệu, khởi tạo sau refresh |
| Lỗi ném ra | Có thể khiến bootstrap thất bại | Có thể lan truyền và ảnh hưởng pha phát event | Lỗi runner làm startup thất bại, không đến ready bình thường |

**Quy tắc thực hành:** Ứng dụng nghiệp vụ thường dùng **runner** cho tác vụ khởi tạo và **ApplicationListener** cho sự kiện. Chỉ dùng **SpringApplicationRunListener** khi thật sự cần hook sâu vào quá trình `SpringApplication.run()` hoặc đang viết một thư viện tích hợp hạ tầng.

## 3. Trục thời gian chung của Spring Boot 3.3

Sơ đồ sau ghép ba cơ chế trên vào một lần startup thành công:

```text
main(String[] args)
  |
  +-- new SpringApplication(App.class)
  +-- app.addListeners(...)                 [đăng ký ApplicationListener sớm]
  |
  +-- app.run(args)
       |
       +-- SpringApplicationRunListener.starting(...)
       |     +-- ApplicationStartingEvent
       |
       +-- Chuẩn bị Environment
       +-- RunListener.environmentPrepared(...)
       |     +-- ApplicationEnvironmentPreparedEvent
       |
       +-- Tạo ApplicationContext, chạy initializers
       +-- RunListener.contextPrepared(...)
       |     +-- ApplicationContextInitializedEvent
       |
       +-- Nạp các nguồn bean definition ban đầu
       +-- RunListener.contextLoaded(...)
       |     +-- ApplicationPreparedEvent
       |
       +-- refresh ApplicationContext
       |     +-- xử lý cấu hình, DI, tạo singleton non-lazy
       |     +-- ContextRefreshedEvent (Spring Framework)
       |
       +-- RunListener.started(...)
       |     +-- ApplicationStartedEvent
       |     +-- LivenessState.CORRECT
       |
       +-- Gọi ApplicationRunner / CommandLineRunner
       |
       +-- RunListener.ready(...)
       |     +-- ApplicationReadyEvent
       |     +-- ReadinessState.ACCEPTING_TRAFFIC
       |
       +-- SpringApplication.run(...) trả ApplicationContext
```

Ở mỗi mốc, **run listener callback và sự kiện do Boot phát là hai cách nhìn cùng một pha**. Mặc định Spring Boot có `EventPublishingRunListener` làm cầu nối để phát các application events. Không nên suy diễn rằng mọi custom `RunListener` luôn chạy trước hoặc sau mọi `ApplicationListener` ở cùng mốc: thứ tự cụ thể giữa các listener phụ thuộc cơ chế sắp xếp và đăng ký.

Nếu startup lỗi, Boot gọi `SpringApplicationRunListener.failed(context, exception)` và phát `ApplicationFailedEvent` khi thực hiện luồng xử lý lỗi. `context` có thể là `null` nếu lỗi đến trước khi tạo context. Một startup thất bại trước runners sẽ không có `ApplicationReadyEvent` thành công.

Các mốc cần nhớ:

- **`ApplicationStartingEvent`**: trước khi `Environment` và `ApplicationContext` sẵn sàng.
- **`ApplicationEnvironmentPreparedEvent`**: đã chuẩn bị `Environment`, chưa tạo context.
- **`ApplicationContextInitializedEvent`**: context đã qua initializers, trước khi nạp primary bean definitions.
- **`ApplicationPreparedEvent`**: nguồn bean definitions ban đầu đã nạp, trước refresh.
- **`ApplicationStartedEvent`**: sau refresh, trước khi gọi runners.
- **`ApplicationReadyEvent`**: sau khi các runners đã được gọi.
- Ngoài ra còn có sự kiện của Spring Framework như `ContextRefreshedEvent`, và availability change events.

Vì vậy không được gọi runner là “chạy trước khi tạo context”, hoặc hiểu `ApplicationStartedEvent` là lúc đã hoàn thành mọi runner.

## 4. SpringApplicationRunListener: hook cấp chuỗi khởi động

### 4.1. Hợp đồng và ý nghĩa

`org.springframework.boot.SpringApplicationRunListener` là interface mà Spring Boot tìm bằng `SpringFactoriesLoader`. **Mỗi lần `SpringApplication.run(...)` sẽ có một instance mới** theo cơ chế khởi tạo của Boot. Trong Boot 3.3, implementation được tải qua `META-INF/spring.factories` và cần constructor public có **hai tham số `(SpringApplication, String[])`**.

Các callback (phương thức `default` nên chỉ cần override những mốc cần thiết):

| Callback | Thời điểm |
| --- | --- |
| `starting(ConfigurableBootstrapContext)` | Ngay lúc `run()` bắt đầu; chưa có `Environment` hoàn chỉnh |
| `environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment)` | `Environment` đã chuẩn bị, trước khi tạo context |
| `contextPrepared(ConfigurableApplicationContext)` | Context đã tạo, được chuẩn bị và chạy initializers; nguồn cấu hình ban đầu chưa nạp |
| `contextLoaded(ConfigurableApplicationContext)` | Sources đã được nạp vào context, trước refresh |
| `started(ConfigurableApplicationContext, Duration)` | Context đã refresh, runner chưa được gọi |
| `ready(ConfigurableApplicationContext, Duration)` | Các runner đã được gọi; `run()` sắp kết thúc |
| `failed(ConfigurableApplicationContext, Throwable)` | `run()` thất bại; context có thể `null` |

`Duration timeTaken` ở `started` và `ready` có thể là `null` trong một số đường gọi. Nếu dùng để ghi metrics, xử lý trường hợp không có giá trị; không tự giả định mọi lần khởi động luôn có thời gian đo được.

### 4.2. Cách đăng ký

Tệp **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
```

Khóa ở đây là **`org.springframework.boot.SpringApplicationRunListener`**, không phải `org.springframework.context.ApplicationListener`. Chỉ thêm `@Component` vào `TraceRunListener` không phải cách đăng ký SPI này. `SpringApplication.addListeners(...)` cũng nhận `ApplicationListener`, **không nhận `SpringApplicationRunListener`**.

**Đừng nhầm `spring.factories` với file `AutoConfiguration.imports`.** Trong Boot 3, cơ chế khai báo lớp auto-configuration dùng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; đó là một mục đích khác với đăng ký `SpringApplicationRunListener`.

### 4.3. Đặc điểm quan trọng

- RunListener được tạo **trước khi các service bean thông thường sẵn sàng**; constructor của nó không phải một điểm constructor injection dành cho Spring application beans.
- Các callback rất sớm không nên lấy `context.getBean(...)`, vì context có thể chưa tồn tại hoặc chưa refresh.
- Callback lỗi phải hoạt động được khi `context == null`.
- Không nên thực hiện I/O nặng hoặc công việc nghiệp vụ kéo dài trong SPI này vì có thể chặn startup.
- Nếu cần theo dõi nhiều mốc bootstrap một cách thống nhất trong thư viện nền tảng, RunListener phù hợp hơn một loạt runner rời rạc.

## 5. ApplicationListener: lắng nghe các sự kiện

### 5.1. Hợp đồng

Một listener thường triển khai interface generic:

```java
public final class StartingOnlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("ApplicationStartingEvent observed");
    }
}
```

**Đây là đoạn minh họa trong dự án Spring**, cần import `org.springframework.context.ApplicationListener` và `org.springframework.boot.context.event.ApplicationStartingEvent`. Generic parameter xác định event mà listener quan tâm.

Nếu cần nghe nhiều loại event Boot, có thể triển khai `ApplicationListener<SpringApplicationEvent>` và dùng `instanceof` để chọn nhánh. Với sự kiện nghiệp vụ riêng, cũng có thể dùng bean `@EventListener` hoặc `ApplicationListener` cho event loại đó.

### 5.2. Đăng ký sớm và đăng ký dưới dạng bean

**Cách 1 — đăng ký trước `run()`:**

```java
SpringApplication app = new SpringApplication(App.class);
app.addListeners(new StartingOnlyListener());
app.run(args);
```

`App` là class main giả định. Đây là cách có thể nhận `ApplicationStartingEvent` khi context chưa được tạo.

**Cách 2 — tự động đăng ký từ `spring.factories`:**

```properties
org.springframework.context.ApplicationListener=com.example.lifecycle.StartingOnlyListener
```

Listener được nạp qua cấu hình classpath khi SpringApplication khởi động, nên có thể bắt các event sớm nếu triển khai phù hợp. Lớp được tạo ở bootstrap không nên phụ thuộc vào DI của bean ứng dụng.

**Cách 3 — dưới dạng Spring bean:**

```java
@Component
class ReadyAudit {
    @EventListener
    void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready event received");
    }
}
```

Đoạn trên cần import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener` và `org.springframework.boot.context.event.ApplicationReadyEvent`; đây là ví dụ bean trong ứng dụng Spring. Nó phù hợp với event **sau khi bean đã được tạo**, và có thể dùng constructor injection để nhận service.

**Giới hạn then chốt:** một listener chỉ tồn tại dưới dạng `@Bean`, `@Component` hoặc `@EventListener` sẽ không nhận ngược những event rất sớm đã phát trước khi bean được tạo. Muốn nhận `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent`, phải đăng ký trước `run` hoặc qua cơ chế bootstrap thích hợp.

### 5.3. Về thứ tự, lỗi và nhiều context

- Khi có nhiều listener, có thể dùng `@Order` hoặc `Ordered` khi thực sự cần xác định thứ tự xử lý trong cùng một event.
- Event listeners mặc định thường được gọi đồng bộ trong luồng phát event; một listener làm việc nặng hoặc ném exception có thể chậm hoặc phá hỏng startup.
- Với application context hierarchy, sự kiện ở child có thể được chuyển đến parent; một listener có thể quan sát nhiều sự kiện cùng loại. Để phân biệt, so sánh context nguồn trong event với context mà listener thuộc về.
- `ApplicationListener` không có cơ chế tự lặp lại lịch sử sự kiện đã phát trước lúc nó được đăng ký.

## 6. ApplicationRunner và CommandLineRunner: thực hiện việc sau refresh

### 6.1. Hợp đồng

Hai interface thuộc `org.springframework.boot`, đều có một phương thức `run`:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Hai chữ ký trên trình bày **hợp đồng phương thức**, không phải định nghĩa lại các interface thư viện trong source code ứng dụng.

Khác biệt lớn nhất là kiểu dữ liệu đầu vào:

- `ApplicationRunner` nhận `ApplicationArguments`: phân loại option như `--mode=demo` và các đối số không phải option, cho phép gọi `containsOption("mode")`, `getOptionValues("mode")`, `getNonOptionArgs()`, `getSourceArgs()`.
- `CommandLineRunner` nhận chính mảng chuỗi CLI thô (`String...`), nên nếu muốn phân tích option phải tự xử lý hoặc dùng cơ chế khác.

Runners là **Spring beans** (được đăng ký qua `@Component` hoặc `@Bean`). Chúng chạy **sau khi context refresh**. Có thể constructor-inject service/repository để làm warm-up, kiểm tra trạng thái, hoặc tác vụ khởi tạo có giới hạn rõ ràng.

Nếu có nhiều runner, có thể dùng `@Order` hoặc `Ordered`; Boot sẽ sắp xếp `ApplicationRunner` và `CommandLineRunner` theo thứ tự trước khi gọi. Không nên dựa vào thứ tự quét classpath mặc định.

### 6.2. Có phải runner chạy sau ApplicationReadyEvent?

**Không.** Trình tự bình thường là:

```text
refresh context
  -> ApplicationStartedEvent
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
```

Vì thế nếu runner ném exception, startup có thể đi vào nhánh thất bại, và `ApplicationReadyEvent` thành công sẽ không được phát. Đây là lý do runner thích hợp cho tác vụ **cần hoàn tất trước khi ứng dụng được xem là ready**.

Runner cũng không phải scheduler: nó được Boot gọi theo vòng đời startup, không tự động chạy định kỳ hoặc mỗi HTTP request. Để chạy tác vụ theo lịch, dùng scheduler/job framework đúng mục đích.

## 7. Ví dụ hoàn chỉnh: cùng một ứng dụng dùng cả ba loại

Ứng dụng sau dùng **Java 21**, **Spring Boot 3.3.13** và Maven. Nó không mở HTTP server, giúp tập trung quan sát startup. Ví dụ minh họa:

- RunListener được nạp từ `spring.factories`.
- ApplicationListener được đăng ký trực tiếp vào `SpringApplication` trước `run(args)`.
- `ApplicationRunner` và `CommandLineRunner` là hai `@Component` với thứ tự rõ ràng.
- Các dòng log cho thấy runner diễn ra **sau started** và **trước ready**.

### 7.1. Cấu trúc dự án

```text
lifecycle-hooks-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/lifecycle/
        │   ├── LifecycleDemoApplication.java
        │   ├── TraceRunListener.java
        │   ├── TraceApplicationEvents.java
        │   ├── StructuredArgsRunner.java
        │   └── RawArgsRunner.java
        └── resources/META-INF/
            └── spring.factories
```

### 7.2. Maven

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-hooks-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` cung cấp các thành phần khởi động cơ bản; không cần `spring-boot-starter-web`. Dùng `java.version` 21 nhất quán với JDK thực thi.

### 7.3. RunListener triển khai đầy đủ callback

**Tệp `src/main/java/com/example/lifecycle/TraceRunListener.java`:**

```java
package com.example.lifecycle;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

public final class TraceRunListener implements SpringApplicationRunListener {

    // SpringFactoriesLoader cần constructor public đúng chữ ký này.
    public TraceRunListener(SpringApplication application, String[] args) {
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("RUN starting");
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        System.out.println("RUN environmentPrepared");
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("RUN contextPrepared");
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("RUN contextLoaded");
    }

    @Override
    public void started(ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN started");
    }

    @Override
    public void ready(ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN ready");
    }

    @Override
    public void failed(ConfigurableApplicationContext context, Throwable exception) {
        System.err.println("RUN failed: " + exception.getClass().getSimpleName());
    }
}
```

**Tệp `src/main/resources/META-INF/spring.factories`:**

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
```

Constructor được yêu cầu dù trong demo không dùng hai tham số. Đây là API SPI của Boot, **không phải Spring bean cần `@Component`**. Các callback `starting` đến `ready` chạy theo pha tương ứng; `failed` chỉ được gọi trên đường lỗi.

### 7.4. ApplicationListener nhận các event bootstrap

**Tệp `src/main/java/com/example/lifecycle/TraceApplicationEvents.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class TraceApplicationEvents
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("EVENT starting");
        }
        else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            System.out.println("EVENT environmentPrepared");
        }
        else if (event instanceof ApplicationStartedEvent) {
            System.out.println("EVENT started");
        }
        else if (event instanceof ApplicationReadyEvent) {
            System.out.println("EVENT ready");
        }
        else if (event instanceof ApplicationFailedEvent) {
            System.err.println("EVENT failed");
        }
    }
}
```

Listener này nhận các event `SpringApplicationEvent` rồi chọn vài loại để in. Nó **không in toàn bộ event**; chẳng hạn `ApplicationContextInitializedEvent` hoặc `ApplicationPreparedEvent` có thể vẫn được gửi nhưng demo bỏ qua bằng điều kiện. `AvailabilityChangeEvent` là loại sự kiện khác; đừng cho rằng việc không in availability nghĩa là không có thay đổi liveness/readiness.

### 7.5. Hai runner để so sánh đối số

**Tệp `src/main/java/com/example/lifecycle/StructuredArgsRunner.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public final class StructuredArgsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("APP RUNNER mode=" + args.getOptionValues("mode")
                + "; free=" + args.getNonOptionArgs());
    }
}
```

**Tệp `src/main/java/com/example/lifecycle/RawArgsRunner.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public final class RawArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("CLI RUNNER args=" + String.join("|", args));
    }
}
```

`@Order(10)` và `@Order(20)` giúp runner có thứ tự dự đoán được: `StructuredArgsRunner` trước `RawArgsRunner`. `@Order` **không thay đổi** lúc Boot phát `ApplicationStartedEvent` hay `ApplicationReadyEvent`.

### 7.6. Lớp main đăng ký ApplicationListener trước khi chạy

**Tệp `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // ApplicationListener được đăng ký trước run để nhận event rất sớm.
        application.addListeners(new TraceApplicationEvents());

        // TraceRunListener được Boot tìm qua META-INF/spring.factories.
        application.run(args);
    }
}
```

Khi chạy `main`, không cần `new TraceRunListener(...)` và cũng không thêm `@Component` cho lớp đó. Boot tự tìm RunListener qua `spring.factories`, còn `TraceApplicationEvents` được thêm trực tiếp vào `SpringApplication`. Hai runner được component scan phát hiện rồi gọi sau refresh.

### 7.7. Chạy và kiểm tra kết quả

Điều kiện: JDK 21, Maven và dependency truy cập được.

```bash
java -version
mvn -version
mvn package
java -jar target/lifecycle-hooks-demo-0.0.1-SNAPSHOT.jar --mode=demo alpha beta
```

`mvn package` tạo executable JAR do plugin của Boot đóng gói. Dòng `--mode=demo` là **option**, còn `alpha` và `beta` là **non-option arguments**.

Các dòng của hai runner phải xuất hiện đúng như sau:

```text
APP RUNNER mode=[demo]; free=[alpha, beta]
CLI RUNNER args=--mode=demo|alpha|beta
```

Đối với RunListener, các dòng sau có thứ tự tương đối:

```text
RUN starting
RUN environmentPrepared
RUN contextPrepared
RUN contextLoaded
RUN started
RUN ready
```

Đối với ApplicationListener đã chọn, các dòng sau có thứ tự tương đối:

```text
EVENT starting
EVENT environmentPrepared
EVENT started
EVENT ready
```

**Không ghép ba khối trên thành một stdout duy nhất theo thứ tự khối.** Log Spring Boot có thể xen giữa; và các callback `RUN` với `EVENT` của cùng một giai đoạn có thể xen kẽ. Hai quan hệ chắc chắn cần kiểm chứng là:

- Cả `RUN started` và `EVENT started` đều ứng với giai đoạn **trước** hai runner.
- Cả `RUN ready` và `EVENT ready` đều ứng với giai đoạn **sau** hai runner.
- Hai runner có thứ tự `APP RUNNER` rồi `CLI RUNNER` do `@Order`.

Nếu chạy ứng dụng **không truyền `--mode`**, `getOptionValues("mode")` có thể trả `null`; ví dụ chỉ in giá trị nên không ném lỗi, nhưng logic thực tế phải kiểm tra option trước khi sử dụng.

## 8. Thí nghiệm thay đổi: dùng @EventListener bean

Để quan sát sự khác biệt của listener được Spring quản lý, có thể thêm bean sau trong package `com.example.lifecycle`:

**Tệp bổ sung `ReadyBeanListener.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class ReadyBeanListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("BEAN EVENT ready");
    }
}
```

Bean này có thể nhận `ApplicationReadyEvent` vì container đã refresh và tạo listener bean trước mốc ready. Nếu đổi tham số thành `ApplicationStartingEvent`, **không thể mong đợi** nó nhận event đầu tiên: khi đó bean còn chưa tồn tại.

Một bean listener có thể dùng constructor injection và tác động đến các service sẵn có, nhưng vẫn nên tránh công việc kéo dài trong callback mặc định. Nếu công việc phải hoàn tất trước ready thì runner thường diễn đạt mục đích rõ hơn.

## 9. Lựa chọn theo tình huống

| Yêu cầu thực tế | Nên dùng | Giải thích |
| --- | --- | --- |
| Ghi mốc `run()` từ lúc rất sớm đến khi hoàn thành để đo startup framework | `SpringApplicationRunListener` | Được gọi theo các callback bootstrap |
| Thư viện tích hợp cần quan sát lúc `Environment` sẵn sàng trước context | `SpringApplicationRunListener.environmentPrepared` hoặc early `ApplicationListener` | Đều có thể hoạt động trước khi có bean |
| Chỉ muốn log `ApplicationReadyEvent` | `@EventListener` bean hoặc `ApplicationListener<ApplicationReadyEvent>` | Không cần SPI cấp thấp |
| Cần ghi `ApplicationFailedEvent` kể cả lỗi rất sớm | `ApplicationListener` đăng ký trước `run` hoặc RunListener `failed` | Context có thể chưa tồn tại |
| Cần đọc option CLI `--mode=sync` và inject service | `ApplicationRunner` | Nhận `ApplicationArguments` đã phân loại |
| Cần nhận chuỗi đối số thô và inject service | `CommandLineRunner` | Nhận `String... args` |
| Cần seed dữ liệu trước khi ứng dụng nhận traffic | Runner phù hợp, có kiểm soát và idempotency | Chạy trước ready |
| Cần thực hiện tác vụ lặp theo lịch | Scheduler/job framework | Ba hook trên không phải scheduler |
| Cần xử lý domain event sau khi app hoạt động | `ApplicationListener` bean/`@EventListener` | Sự kiện có thể phát nhiều lần trong runtime |
| Cần thay đổi cấu hình `Environment` rất sớm | `EnvironmentPostProcessor` hoặc hook bootstrap phù hợp | Đây là vấn đề cấu hình sớm, không thuộc trách nhiệm runner |

**Ví dụ quyết định:** nếu cần kết nối vào service sau DI, đọc danh sách khách hàng và tạo cache trước khi nhận request, chọn `ApplicationRunner`. Nếu muốn báo rằng ứng dụng đã ready, chọn `ApplicationReadyEvent`. Nếu đang xây một starter cần instrument mốc `contextPrepared` và `contextLoaded` của `SpringApplication` ở nhiều dự án, xem xét `SpringApplicationRunListener`.

## 10. Các lỗi phổ biến và cách sửa

### 10.1. Đăng ký RunListener bằng @Component

**Sai cách:** thêm `@Component` cho một class triển khai `SpringApplicationRunListener` rồi kỳ vọng Boot gọi `starting(...)`.

**Vì sao sai:** Spring Boot tìm SPI RunListener từ cơ chế `SpringFactoriesLoader`, trước khi xử lý Spring beans.

**Cách đúng:** tạo constructor public `(SpringApplication, String[])`, khai báo trong `META-INF/spring.factories` với khóa `org.springframework.boot.SpringApplicationRunListener`, đóng gói resource trong classpath.

### 10.2. Nhầm khóa spring.factories

Hai dòng dưới đây có **hai ý nghĩa khác nhau**:

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
org.springframework.context.ApplicationListener=com.example.lifecycle.TraceApplicationEvents
```

Dùng dòng thứ hai nếu muốn **tự đăng ký sớm** `TraceApplicationEvents` qua metadata, thay cho `application.addListeners(...)`. Không dùng cả hai cơ chế đăng ký **cho cùng một listener** khi không có lý do, vì có thể quan sát callback lặp. Không tự thay thế Boot's `EventPublishingRunListener` mặc định.

### 10.3. ApplicationListener không bắt được event rất sớm

**Triệu chứng:** `@EventListener(ApplicationStartingEvent.class)` trong bean không chạy.

**Nguyên nhân:** `ApplicationStartingEvent` được phát trước khi Spring tạo context và các bean listener.

**Cách sửa:** tạo listener và đăng ký bằng `SpringApplication.addListeners(...)` trước `run(args)`, hoặc qua `spring.factories`.

### 10.4. Runner không được gọi

Kiểm tra bean có thực sự được đăng ký qua `@Component`/`@Bean` không, package có nằm trong component scan không, và startup đã vượt qua bước refresh chưa. Nếu refresh thất bại, runner chưa được gọi là điều bình thường. Nếu tạo `new MyRunner()` bằng tay mà không đăng ký làm bean, Boot không tự tìm đối tượng đó.

### 10.5. Kết quả thứ tự không như mong đợi

Đừng giả định `ApplicationRunner` luôn trước `CommandLineRunner` **chỉ vì tên interface**. Dùng `@Order`/`Ordered` khi cần thứ tự xác định. Giữa các callbacks cùng một pha như RunListener và ApplicationListener, tránh dựa vào trình tự logging nếu không có hợp đồng thứ tự rõ ràng.

### 10.6. Lỗi runner làm ứng dụng không ready

Nếu `run(...)` của runner ném exception, Boot có thể xử lý như một startup failure: ghi log lỗi, gọi failure callbacks và không phát `ApplicationReadyEvent` theo luồng thành công. Với tác vụ khởi tạo quan trọng, cần xác định rõ khi nào được phép fail startup; với tác vụ không bắt buộc, cần xử lý lỗi/timeout thích hợp thay vì gây restart liên tục.

### 10.7. Callback sớm gọi getBean

`starting(...)` hoặc `environmentPrepared(...)` chạy khi chưa có `ApplicationContext`; ngay cả `contextPrepared(...)` vẫn trước refresh. Không dùng các callback ấy để tìm service/repository/transaction manager thông thường. Nếu cần bean đã được inject, hãy chọn runner hoặc event muộn.

### 10.8. Xử lý event quá lâu

Application event listeners chạy đồng bộ theo mặc định trong nhiều tình huống. Một callback làm I/O chậm có thể kéo dài khởi động hoặc xử lý request. Không làm các tác vụ nặng trong listener khởi động; dùng runner với timeout, hoặc hệ thống background/job phù hợp khi không có yêu cầu chặn readiness.

### 10.9. Thấy event lặp trong parent-child context

Với `ApplicationContext` hierarchy, event từ child có thể được publish lên parent, nên listener của parent có thể nhận nhiều event loại giống nhau. Kiểm tra context nguồn qua event, thêm điều kiện lọc khi phù hợp; không mặc định mỗi loại event chỉ xảy ra một lần trên toàn bộ cấu trúc.

## 11. Câu hỏi và bài tập

1. Nêu khác biệt giữa `SpringApplicationRunListener`, `ApplicationListener<E>` và `ApplicationRunner`: đối tượng nào gọi chúng, khi nào, và dữ liệu nhận được?
2. Vì sao `TraceRunListener` cần constructor `(SpringApplication, String[])` dù không dùng DI?
3. Nếu bỏ file `META-INF/spring.factories`, những dòng `RUN ...` của ví dụ còn xuất hiện không? Vì sao?
4. Vì sao listener được `addListeners(...)` có thể bắt `ApplicationStartingEvent`, còn listener chỉ mang `@Component` thường không?
5. Trình bày thứ tự của `ApplicationStartedEvent`, `StructuredArgsRunner`, `RawArgsRunner`, `ApplicationReadyEvent`.
6. Chạy ứng dụng với `--mode=demo alpha beta`. So sánh cách `ApplicationRunner` và `CommandLineRunner` nhìn thấy args.
7. Đổi `@Order` giữa hai runner. Quan sát sự đổi thứ tự; xem event `started` và `ready` có đổi vị trí theo runner hay không.
8. Thêm `ApplicationPreparedEvent` vào `TraceApplicationEvents` và in tên event; xác định nó xảy ra trước hay sau `refresh`.
9. Cho `RawArgsRunner` ném `IllegalStateException("demo failure")`. Dự đoán `RUN failed`, `EVENT failed` và vì sao không có `ready` thành công.
10. Nếu cần dùng một `DataSource` bean để kiểm tra dữ liệu khởi tạo, nên đặt logic ở RunListener `environmentPrepared`, `ApplicationListener<ApplicationStartingEvent>` hay `ApplicationRunner`? Giải thích.
11. Nếu cần quan sát application event do nghiệp vụ publish **sau khi ứng dụng đã sẵn sàng**, dùng RunListener có hợp lý không?
12. Giải thích vì sao `@Order` của runner không thể làm `ApplicationReadyEvent` phát trước `ApplicationStartedEvent`.

**Tự đánh giá đạt yêu cầu** khi có thể chạy ví dụ bằng Maven/JDK 21, nhìn ra `RUN` là callback của SPI, `EVENT` là thông báo sự kiện, `APP RUNNER` và `CLI RUNNER` là công việc từ bean, và lý giải được sự khác biệt giữa **đã refresh**, **đã gọi runners**, **đã ready**.

## 12. Tài liệu chính thức

- Spring Boot 3.3.13 — `SpringApplicationRunListener` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot 3.3.13 — `SpringApplication` và Application Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationRunner` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — `CommandLineRunner` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Framework 6.1 — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
