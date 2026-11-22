# ApplicationReadyEvent sau khi các runner đã hoàn tất — Spring Boot 3.3

## 1. Mục tiêu bài học

`ApplicationReadyEvent` là một mốc quan trọng trong **vòng đời khởi động ứng dụng Spring Boot**. Sự kiện này được Spring Boot phát **rất muộn trong quá trình `SpringApplication.run(...)`**, sau khi `ApplicationContext` đã refresh và **sau khi Boot đã gọi xong tất cả `ApplicationRunner` và `CommandLineRunner`** theo luồng khởi động thành công.

Sau khi học bài này, bạn cần:

1. Mô tả đúng vị trí `ApplicationReadyEvent` so với `ApplicationStartedEvent`, `ApplicationRunner`, `CommandLineRunner` và `ApplicationFailedEvent`.
2. Đăng ký được listener bằng `@EventListener` hoặc `ApplicationListener<ApplicationReadyEvent>`.
3. Hiểu “runner hoàn tất” có nghĩa gì, đặc biệt khi runner chỉ **khởi phát công việc bất đồng bộ** rồi trả về.
4. Chọn đúng callback cho startup task bắt buộc, thông báo sau startup và readiness/liveness.
5. Chạy được ví dụ Java 21 + Spring Boot 3.3 và lý giải đầu ra, bao gồm trường hợp runner ném exception.

**Thông điệp chính:** `ApplicationReadyEvent` xảy ra **sau khi các callback `run(...)` của các runner kết thúc bình thường**, nhưng không tự chứng minh rằng mọi tác vụ nền, kết nối bên ngoài, message consumer hay dịch vụ phụ thuộc đã thật sự sẵn sàng.

## 2. Vị trí trong chuỗi khởi động

Một lần khởi động **thành công** của Spring Boot 3.3 có luồng khái niệm sau:

```text
main(String[] args)
   |
   +-- SpringApplication.run(args)
         |
         +-- ApplicationStartingEvent
         +-- Chuẩn bị Environment
         +-- ApplicationEnvironmentPreparedEvent
         +-- Tạo ApplicationContext, chạy initializers
         +-- ApplicationContextInitializedEvent
         +-- Nạp primary sources/bean definitions
         +-- ApplicationPreparedEvent
         |
         +-- refresh ApplicationContext
         |     +-- Xử lý cấu hình và bean definitions
         |     +-- Tạo/inject singleton non-lazy thông thường
         |     +-- Khởi động web server nếu có
         |
         +-- ApplicationStartedEvent
         +-- AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         +-- ApplicationRunner.run(ApplicationArguments)
         +-- CommandLineRunner.run(String... args)
         |     +-- Tất cả runners được sắp xếp theo order phù hợp
         |     +-- Kết thúc bình thường, không ném exception
         |
         +-- ApplicationReadyEvent                 <-- trọng tâm bài
         +-- AvailabilityChangeEvent(
         |       ReadinessState.ACCEPTING_TRAFFIC)
         |
         +-- run(...) trả về ApplicationContext
```

Sơ đồ lược bỏ các callback nội bộ, ứng xử đặc thù của các context và các sự kiện phụ. Những điểm cần phân biệt:

- **`ContextRefreshedEvent`** là sự kiện của Spring Framework, xảy ra khi context refresh; đó **không phải** mốc runner hoàn tất.
- **`ApplicationStartedEvent`** được Boot phát **sau refresh nhưng trước runners**. Tên “Started” không có nghĩa mọi startup task đã hoàn thành.
- **`ApplicationReadyEvent`** được Boot phát **sau khi runners đã chạy và trả về**. Đó là mốc gần cuối mà Boot dùng để thông báo ứng dụng đã sẵn sàng.
- **`ReadinessState.ACCEPTING_TRAFFIC`** được công bố **sau** khi `ApplicationReadyEvent` được phát trong luồng thông thường. Đừng nhầm `ApplicationReadyEvent` với availability event; nếu đọc readiness ngay **bên trong** ready listener, có thể vẫn quan sát trạng thái trước khi Boot công bố accepting traffic.
- **`ApplicationFailedEvent`** thuộc đường khởi động thất bại. Nếu runner ném exception, luồng thành công không đi đến `ApplicationReadyEvent`.

### 2.1. Bốn mốc dễ nhầm

| Mốc | Context đã refresh? | Runners đã hoàn tất? | Ý nghĩa |
| --- | --- | --- | --- |
| `ApplicationPreparedEvent` | Chưa | Chưa | Sources ban đầu đã nạp, chuẩn bị refresh |
| `ApplicationStartedEvent` | Có | Chưa | Refresh thành công; sắp gọi runners |
| `ApplicationReadyEvent` | Có | Có, theo nghĩa runner callbacks đã trả về bình thường | Thông báo giai đoạn startup gần hoàn tất |
| `ReadinessState.ACCEPTING_TRAFFIC` | Có | Có | Boot công bố trạng thái readiness chấp nhận traffic |

Khác biệt quan trọng nhất là **`Started` → `runners` → `Ready`**, không phải `Started` và `Ready` đồng thời.

## 3. ApplicationRunner và CommandLineRunner chạy ở đâu?

Spring Boot tìm các bean thuộc hai interface:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Đây là **chữ ký hợp đồng** để minh họa; không chép lại thành hai interface do ứng dụng tự định nghĩa. Cả hai là các interface thật trong package `org.springframework.boot`.

- **`ApplicationRunner`** nhận `ApplicationArguments` để truy xuất cấu trúc đối số: `containsOption`, `getOptionValues`, `getNonOptionArgs`, `getSourceArgs`.
- **`CommandLineRunner`** nhận trực tiếp các chuỗi command-line ở dạng `String... args`.
- Hai loại runner là **Spring beans**: đăng ký qua `@Component`, `@Bean` hoặc một hình thức bean registration hợp lệ. Chúng có thể được inject service/repository vì context đã refresh.
- Khi có nhiều runner, Spring Boot dùng ordering semantics (`@Order` hoặc `Ordered`) để sắp **thứ tự gọi `run(...)`**. `@Order` không nói rằng constructor của mọi runner/bean cũng được gọi cùng thứ tự.
- Không có quy tắc “mọi ApplicationRunner chạy trước mọi CommandLineRunner”; thứ tự khi sử dụng nhiều runner được xác định bởi cơ chế sắp xếp của Boot.

**Một runner chỉ được xem là hoàn tất khi phương thức `run(...)` của nó trả về bình thường.** Nếu nó khởi chạy một thread, `CompletableFuture`, `@Async` method hoặc đưa message vào queue rồi trả về, Boot không mặc nhiên đợi tác vụ phía sau hoàn tất. Điều đó ảnh hưởng trực tiếp đến cách hiểu `ApplicationReadyEvent`.

## 4. ApplicationReadyEvent là sự kiện gì?

`org.springframework.boot.context.event.ApplicationReadyEvent` là một `SpringApplicationEvent`. Nó được công bố gần cuối startup để biểu thị ứng dụng đã hoàn thành các bước do `SpringApplication` quản lý và sẵn sàng xử lý công việc theo contract Boot.

Các API thường dùng:

- **`getApplicationContext()`**: trả về `ConfigurableApplicationContext` của lần khởi động.
- **`getSpringApplication()`**: đối tượng `SpringApplication` tạo event, thông qua lớp cha `SpringApplicationEvent`.
- **`getArgs()`**: mảng đối số nguồn dùng ở startup, thông qua lớp cha.
- **`getTimeTaken()`**: thời lượng đo quá trình khởi động khi có; có thể là `null`, nên phải kiểm tra trước khi sử dụng.

**Không nên dùng `getTimeTaken()` như một SLA cho toàn bộ hệ thống bên ngoài.** Nó phản ánh thời gian Boot đo ở vòng đời startup, không nhất thiết bao gồm mọi quá trình background vẫn đang tiếp tục.

Một listener nhận ready event là điểm thích hợp để:

- Ghi log hoặc publish metric cho thời điểm startup hoàn tất.
- Thông báo cho hệ thống quan sát về một instance mới đã đạt mốc ready.
- Kích hoạt một tác vụ **không bắt buộc phải hoàn thành trước readiness**, nếu được thiết kế không chặn startup và có xử lý lỗi thích hợp.

Ngược lại, nếu phải **kiểm tra cấu hình, migrate dữ liệu, chuẩn bị cache bắt buộc** trước khi hệ thống được coi là ready, nên đặt công việc tại một runner hoặc cơ chế startup/lifecycle được thiết kế cho yêu cầu đó, thay vì phát ready xong mới bắt đầu làm.

## 5. Đăng ký listener để nhận ApplicationReadyEvent

### 5.1. Dùng @EventListener trong Spring bean

Ví dụ:

```java
@Component
public class ReadyObserver {

    @EventListener
    public void whenReady(ApplicationReadyEvent event) {
        System.out.println("ApplicationReadyEvent received");
    }
}
```

Đoạn này là **minh họa**, cần import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener` và `org.springframework.boot.context.event.ApplicationReadyEvent`.

Khi context đã refresh, bean `ReadyObserver` đã được Spring quản lý và phương thức mang `@EventListener` có thể nhận sự kiện. Với `ApplicationReadyEvent`, **không bắt buộc** phải đăng ký listener từ trước khi tạo context.

### 5.2. Triển khai ApplicationListener

Một cách thay thế:

```java
@Component
public class ReadyApplicationListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready event from ApplicationListener");
    }
}
```

Đoạn này cần import `org.springframework.context.ApplicationListener`, `org.springframework.stereotype.Component`, `org.springframework.boot.context.event.ApplicationReadyEvent`.

Đây cũng là **Spring bean listener**; trong ví dụ app bình thường, nó được đăng ký khi container xây dựng bean. Có thể dùng constructor injection như các bean khác.

**Chỉ nên chọn một cách** cho cùng một hành vi để tránh log/tác dụng phụ bị thực hiện lặp. `@EventListener` và `ApplicationListener` đều xử lý application events, khác nhau ở cách khai báo.

### 5.3. Đăng ký trực tiếp trước run có cần thiết không?

Có thể gọi:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new ReadyApplicationListener());
application.run(args);
```

Đây là **đoạn minh họa**; cần class ứng dụng và listener phù hợp. Cách này cần thiết khi muốn bắt các event cực sớm như `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent`. Với ready event, cách đăng ký **dưới dạng bean** đã đủ vì sự kiện chỉ xảy ra sau refresh.

Không nên vừa gắn `@Component` cho cùng listener, vừa thêm instance của listener đó vào `addListeners(...)`: sẽ có hai đối tượng hoặc đường đăng ký và callback có thể xảy ra lặp ngoài ý muốn.

### 5.4. @EventListener và @TransactionalEventListener

`ApplicationReadyEvent` không mặc nhiên nằm trong một transaction đang active. `@TransactionalEventListener` mặc định liên kết callback với pha transaction; dùng nó chỉ để bắt application ready có thể khiến listener không chạy như mong đợi nếu không có transaction.

Nếu mục đích chỉ là theo dõi startup, **`@EventListener` thông thường** là phù hợp. Transactional listener nên được dùng cho các sự kiện nghiệp vụ thực sự gắn với vòng đời commit/rollback của transaction.

## 6. Ví dụ hoàn chỉnh — Java 21 và Spring Boot 3.3.13

Chương trình sau dùng **ứng dụng non-web** để đầu ra tập trung vào vòng đời startup, không cần database, controller hay cổng HTTP.

Nó có:

1. Một listener in dấu mốc `ApplicationStartedEvent` và `ApplicationReadyEvent`.
2. Một `ApplicationRunner` được sắp trước, có thể chủ động gây lỗi để thử nhánh failure.
3. Một `CommandLineRunner` được sắp sau.
4. Lớp main tạo và chạy `SpringApplication`.

### 6.1. Cấu trúc thư mục

```text
ready-event-demo/
├── pom.xml
└── src/main/java/com/example/ready/
    ├── ReadyEventApplication.java
    ├── FirstRunner.java
    ├── SecondRunner.java
    └── StartupEvents.java
```

### 6.2. pom.xml

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
    <artifactId>ready-event-demo</artifactId>
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

Spring Boot 3.3 hỗ trợ Java 21; cấu hình parent quản lý phiên bản các dependency. Starter cơ bản đủ dùng cho ví dụ command-line, không cần `spring-boot-starter-web`.

### 6.3. Lớp ứng dụng

**Tệp `src/main/java/com/example/ready/ReadyEventApplication.java`:**

```java
package com.example.ready;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReadyEventApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ReadyEventApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

`@SpringBootApplication` tại package `com.example.ready` giúp component scan tìm các runner và listener trong cùng package. Chế độ `WebApplicationType.NONE` giúp ứng dụng không mở cổng HTTP.

### 6.4. ApplicationRunner được gọi trước

**Tệp `src/main/java/com/example/ready/FirstRunner.java`:**

```java
package com.example.ready;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class FirstRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER first");

        if (args.containsOption("fail-runner")) {
            throw new IllegalStateException("demo runner failed");
        }
    }
}
```

`ApplicationArguments.containsOption("fail-runner")` cho phép dùng cờ `--fail-runner`. Trong đường chạy bình thường, phương thức chỉ in một dòng rồi trả về. Trong đường lỗi, nó ném `IllegalStateException`, khiến quá trình startup **không tiếp tục thành công**.

### 6.5. CommandLineRunner được gọi sau

**Tệp `src/main/java/com/example/ready/SecondRunner.java`:**

```java
package com.example.ready;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class SecondRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("RUNNER second");
    }
}
```

`@Order(10)` và `@Order(20)` định nghĩa thứ tự **gọi các runners** trong ví dụ này. Không được suy diễn hai annotation đó cố định thứ tự tạo constructor của tất cả Spring beans.

### 6.6. Listener cho started và ready

**Tệp `src/main/java/com/example/ready/StartupEvents.java`:**

```java
package com.example.ready;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEvents {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ready");
        System.out.println("CONTEXT active="
                + event.getApplicationContext().isActive());
    }
}
```

Tại `ApplicationStartedEvent`, Spring Boot đã refresh context nhưng **chưa gọi runner**. Tại `ApplicationReadyEvent`, cả hai runner đã trả về thành công. `event.getApplicationContext().isActive()` trả `true` trong luồng startup bình thường của ví dụ; điều này xác nhận context đang active, không phải là health check toàn bộ dịch vụ bên ngoài.

### 6.7. Build và chạy

Cần **JDK 21**, Maven và dependency có thể tải từ repository đã cấu hình.

```bash
java -version
mvn -version
mvn package
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar
```

**Các dòng do chương trình chủ động in** theo thứ tự là:

```text
EVENT started
RUNNER first
RUNNER second
EVENT ready
CONTEXT active=true
```

Đây **không phải toàn bộ stdout**: console còn có banner, logging Spring Boot và những thông báo tùy môi trường. Nhưng thứ tự năm dòng do chương trình in phản ánh đúng lifecycle:

1. Context được refresh xong thì phát `ApplicationStartedEvent`.
2. Boot gọi runner có `@Order(10)`.
3. Boot gọi runner có `@Order(20)`.
4. Khi tất cả runners đã trả về bình thường, Boot phát `ApplicationReadyEvent`.
5. Context vẫn active khi event được xử lý.

Non-web app thường kết thúc sau startup nếu không còn non-daemon thread giữ JVM hoạt động; điều đó **không có nghĩa `ApplicationReadyEvent` không được phát**.

### 6.8. Thử trường hợp runner thất bại

Chạy cùng JAR với cờ:

```bash
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar --fail-runner
```

Những dòng do chương trình in **trước lỗi** sẽ gồm:

```text
EVENT started
RUNNER first
```

Sau đó có stack trace/log lỗi startup của Boot; nội dung log có thể khác nhau. **Không có** `RUNNER second`, `EVENT ready` hoặc `CONTEXT active=true` trong đường chạy lỗi bình thường này, vì runner thứ nhất ném exception trước khi Boot gọi runner tiếp theo.

Spring Boot có thể công bố `ApplicationFailedEvent` khi xử lý lỗi startup. Không nên giả định chỉ cần context refresh thành công là ứng dụng chắc chắn đạt mốc ready.

### 6.9. Đo thời gian startup từ ApplicationReadyEvent

Bạn có thể thêm logic sau trong `StartupEvents.onReady(...)`:

```java
java.time.Duration duration = event.getTimeTaken();
if (duration != null) {
    System.out.println("STARTUP durationMs=" + duration.toMillis());
}
```

Đây là **đoạn bổ sung trong phương thức listener**, không phải chương trình độc lập. Số milliseconds phụ thuộc vào máy, tải CPU, classpath và môi trường chạy, vì vậy không đưa ra một stdout cố định cho dòng này.

Dữ liệu `getTimeTaken()` mô tả thời gian startup Boot đo được; nếu một runner chỉ giao việc cho background worker rồi trả về, giá trị này không đại diện cho toàn bộ thời gian hoàn tất background worker.

## 7. Khi runner có công việc bất đồng bộ: hiểu đúng “hoàn tất”

Một trong những lỗi kiến trúc phổ biến nhất là xem việc gọi `run(...)` xong đồng nghĩa toàn bộ nghiệp vụ khởi tạo đã xong.

Ví dụ **minh họa lỗi**:

```java
@Component
public class BadWarmup implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        CompletableFuture.runAsync(() -> {
            // Ví dụ: tải cache lớn từ mạng.
            warmUpCache();
        });
    }

    private void warmUpCache() {
        // Minh họa: logic cần triển khai trong ứng dụng thật.
    }
}
```

Đoạn trên là **code minh họa**, cần imports cho `CompletableFuture`, `ApplicationRunner`, `ApplicationArguments`, `@Component`. Callback `run` trả về ngay sau khi lịch chạy `CompletableFuture`; nó **không đợi** `warmUpCache()` hoàn thành. Vì vậy Boot có thể công bố `ApplicationReadyEvent` trong khi cache vẫn đang tải.

### 7.1. Nếu công việc bắt buộc phải hoàn tất trước ready

Làm đồng bộ hoặc chờ tác vụ có timeout, xử lý interruption và exception rõ ràng. Ví dụ minh họa:

```java
@Component
public class RequiredWarmup implements ApplicationRunner {

    private final CacheService cacheService;

    public RequiredWarmup(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        cacheService.warmUpBlocking();
    }
}
```

Đây là **mẫu kiến trúc, không phải chương trình độc lập**: cần định nghĩa `CacheService` và các imports tương ứng. `warmUpBlocking()` phải thật sự đợi công việc hoàn tất hoặc ném lỗi; nếu nó chỉ tạo task background, contract chưa được đáp ứng. Với I/O bên ngoài, thiết lập timeout, retry hữu hạn, cleanup và chính sách fail startup.

Có những tác vụ không nên nhét vào runner tùy tiện: database schema migration có thể dùng Flyway/Liquibase; việc điều phối start/stop cho message consumers có thể phù hợp `SmartLifecycle`; một job định kỳ nên dùng scheduler/job framework. Điều cần bảo đảm là **readiness phản ánh điều kiện phục vụ thật của ứng dụng**, không chỉ sự kiện Bootstrap đã xảy ra.

### 7.2. Nếu công việc không bắt buộc để nhận traffic

Có thể thực hiện sau ready, nhưng không nên chặn synchronous event listener quá lâu. Cân nhắc một executor/job queue có quản lý vòng đời, logging, metric và shutdown behavior. Khi dùng `@Async` hoặc `CompletableFuture`, phải xử lý lỗi và trạng thái hoàn tất: Boot không tự đợi các công việc đó chỉ vì chúng được bắt đầu trong listener.

Không dùng `CompletableFuture.join()` không timeout trong luồng startup nếu phụ thuộc mạng không đáng tin cậy. Việc chặn vô thời hạn khiến ứng dụng không bao giờ hoàn tất startup.

## 8. Ready event và availability/readiness

Spring Boot có khái niệm availability:

- **`LivenessState`**: ứng dụng còn có khả năng hoạt động hay đã ở trạng thái hỏng cần can thiệp.
- **`ReadinessState`**: ứng dụng có đang **sẵn sàng nhận traffic** hay tạm từ chối để hoàn tất startup/điều chỉnh trạng thái.

Trong luồng thông thường, Boot công bố `LivenessState.CORRECT` sau `ApplicationStartedEvent` và `ReadinessState.ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent`.

**Điểm tinh tế:** `ApplicationReadyEvent` và `ReadinessState.ACCEPTING_TRAFFIC` không phải một event. Khi một ready listener đang chạy, Boot có thể **chưa công bố** trạng thái readiness accepting traffic vì việc công bố đó theo sau ready event trong callback lifecycle.

Nếu cần xử lý đúng thời điểm readiness state thay đổi, theo dõi `AvailabilityChangeEvent` với `ReadinessState`, hoặc sử dụng availability API thích hợp thay vì tự đánh đồng hai sự kiện. Đối với service cần xác định readiness HTTP/Kubernetes, cân nhắc Spring Boot Actuator và readiness probes được cấu hình phù hợp môi trường triển khai.

### 8.1. ApplicationReadyEvent không phải phép kiểm chứng hệ thống ngoài

Ứng dụng có thể phát ready event trong khi:

- Một cache chỉ đang được tải bởi background task.
- Một kết nối tới external API chỉ vừa được khởi tạo, chưa có request thử thành công.
- Một message consumer còn đang chờ phân vùng hoặc broker.
- Dịch vụ bên ngoài đã thay đổi trạng thái sau khi app startup.

Do đó, readiness production có thể cần health indicators, checks và lifecycle coordination riêng. Không dùng việc nhận một event để kết luận mọi dependency bên ngoài đều healthy vĩnh viễn.

### 8.2. Ready event không phải sự kiện định kỳ

`ApplicationReadyEvent` là một phần của **mỗi lần khởi động `SpringApplication` thành công**. Nó không tự chạy lại cho mỗi HTTP request, mỗi health check hoặc mỗi lần network reconnect. Nếu ứng dụng có nhiều application contexts hay startup độc lập trong test, có thể quan sát nhiều event tương ứng; không giả định đúng một event cho toàn bộ JVM trong mọi cấu trúc.

## 9. Đồng bộ, lỗi listener và thứ tự @Order

### 9.1. Listener mặc định thường đồng bộ

Với multicaster mặc định, application event listeners thường được thực thi **đồng bộ** trong luồng phát sự kiện. Vì thế nếu `@EventListener(ApplicationReadyEvent.class)` làm I/O chậm hoặc ném exception, nó có thể trì hoãn hoặc ảnh hưởng kết quả startup. Một ready listener **không phải** chỗ phù hợp để chạy một vòng lặp vô hạn hoặc gọi API không timeout.

Nếu cấu hình event multicaster dùng executor bất đồng bộ, callback có thể không hoàn tất khi Spring Boot tiếp tục các bước startup. Vì vậy không dựa vào thứ tự hoàn tất của asynchronous listeners để xác nhận readiness.

### 9.2. @Order không đảo thứ tự Started và Ready

Có thể áp dụng `@Order` cho runners để điều khiển thứ tự gọi các runner beans. Với nhiều listener cùng nhận ready event, ordering có thể ảnh hưởng thứ tự callback khi event multicaster hỗ trợ. Tuy nhiên, `@Order` **không làm `ApplicationReadyEvent` phát trước `ApplicationStartedEvent`**, và cũng không khiến một runner được gọi trước khi context refresh.

Thứ tự event được xác định bởi Spring Boot startup lifecycle; thứ tự giữa các callbacks **cùng loại sự kiện** là bài toán riêng.

### 9.3. Lỗi runner và lỗi ready listener

Phân biệt:

- **Runner ném exception**: Boot dừng thực thi chuỗi runner ở chỗ lỗi; trong đường chạy thông thường không công bố ready thành công.
- **Ready listener đồng bộ ném exception**: lỗi có thể lan ra khỏi quá trình publish event, khiến `run(...)` được xử lý như startup thất bại. Đừng nghĩ chỉ cần đã gọi `ApplicationReadyEvent` là không còn khả năng fail startup.
- **Ready listener async ném exception**: kết quả phụ thuộc executor và cơ chế xử lý lỗi async. Phải quan sát, ghi nhận và quản lý lỗi riêng; không mặc định lỗi đó sẽ làm thất bại startup.
- **Runner bắt và nuốt exception**: Boot có thể tiếp tục và phát ready dù tác vụ khởi tạo đã không đạt yêu cầu. Nếu công việc thiết yếu, hãy thể hiện failure bằng exception rõ ràng.

### 9.4. Cần sự kiện bắt lỗi rất sớm?

Một bean `@EventListener(ApplicationFailedEvent.class)` có thể không tồn tại nếu startup lỗi **trước khi context tạo xong**. Nếu muốn quan sát lỗi ở cả giai đoạn đầu bootstrap, hãy đăng ký `ApplicationListener<ApplicationFailedEvent>` **trước `SpringApplication.run(...)`** hoặc qua cơ chế bootstrap thích hợp. Đây là khác biệt quan trọng so với `ApplicationReadyEvent`, xảy ra đủ muộn để một bean listener có thể nhận được.

## 10. Kiểm thử thời điểm ApplicationReadyEvent

### 10.1. Kiểm thử bằng chương trình chạy thật

Có thể dùng hai lệnh sau để xác thực nhánh thành công và thất bại:

```bash
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar --fail-runner
```

Trong luồng thành công, thứ tự các dòng phải là `EVENT started` → `RUNNER first` → `RUNNER second` → `EVENT ready`. Trong nhánh thất bại có chủ đích, `EVENT ready` không được in.

Khi viết test automation, nên kiểm tra **sự tồn tại và thứ tự các dấu mốc cụ thể** thay vì so toàn bộ log Spring Boot (vốn có thể thay đổi theo phiên bản, PID, thời gian và cấu hình log).

### 10.2. Phân biệt test Spring context với test SpringApplication startup

`ApplicationReadyEvent` gắn với **chuỗi `SpringApplication.run(...)`**. Một test chỉ tạo `AnnotationConfigApplicationContext` và gọi `refresh()` không tự động thực thi chuỗi SpringApplication, các runners hoặc phát ready event của Boot. Muốn test timing thật, phải khởi động qua cơ chế Spring Boot tương ứng hoặc gọi `SpringApplication` thật.

Nếu test tác vụ khởi tạo có side effect, thiết kế runner có khả năng **idempotent**, tránh ghi dữ liệu thật từ mỗi lượt test hoặc mỗi lần restart. Có thể vô hiệu hóa tác vụ trong profile test bằng điều kiện phù hợp, nhưng phải bảo đảm test timing vẫn có ít nhất một runner để quan sát chuỗi.

### 10.3. Những assertion có ý nghĩa

- Event `ApplicationStartedEvent` xuất hiện **trước** các log từ runners.
- Với các runners được ordering rõ ràng, callback của runner có order nhỏ được gọi trước callback có order lớn.
- `ApplicationReadyEvent` xuất hiện **sau** khi mọi runner hoàn thành bình thường.
- Nếu runner throw, không có `ApplicationReadyEvent` trong đường thành công.
- Nếu runner khởi chạy async task rồi trả về, hãy kiểm thử trạng thái hoàn tất **của async task** riêng, không dùng việc ready event đã phát làm bằng chứng task đã xong.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Ready listener không được gọi | Startup thất bại; runner throw; bean listener không được scan/đăng ký | Kiểm tra `ApplicationFailedEvent`, stack trace, package component scan và registration |
| Có `ApplicationStartedEvent` nhưng không có ready | Runner thất bại hoặc quá trình sau refresh bị chặn | Kiểm tra runners, timeout, exception và log startup |
| Ready event đến khi cache còn đang tải | Runner chỉ scheduling async rồi trả về | Nếu cache thiết yếu, chờ hoàn tất trong runner với giới hạn thời gian |
| `@EventListener` trên class không được gọi | Class không phải Spring bean hoặc method signature/import sai | Đặt class trong component scan, đăng ký `@Bean` hoặc dùng `ApplicationListener` |
| `@Order` không làm thay đổi mốc ready | Nó chỉ sắp callback/runner, không đổi các pha lifecycle | Dựa vào contract started → runners → ready |
| Truy cập readiness trong ready listener thấy chưa accepting | Boot công bố readiness accepting sau ready event | Quan sát availability change event thay vì suy luận hai mốc là một |
| Gọi external API lâu trong ready listener | Event processing có thể đồng bộ và chặn startup | Chuyển việc nặng sang runner nếu bắt buộc hoặc async job có quản lý nếu không bắt buộc |
| Ứng dụng báo ready dù một runner log error | Runner đã bắt/nuốt exception và trả về | Làm rõ failure policy, ném exception khi khởi tạo thiết yếu thất bại |
| Thử `ApplicationReadyEvent` bằng context `refresh()` đơn thuần | Không dùng SpringApplication startup lifecycle | Khởi động bằng Spring Boot integration test hoặc `SpringApplication` |
| Ready event nhận nhiều lần | Nhiều contexts/runs hoặc đăng ký listener trùng | Kiểm tra source context và các đường đăng ký |

**Checklist điều tra:** (1) `SpringApplication` có chạy không; (2) context có refresh xong không; (3) runner bean nào được đăng ký; (4) thứ tự runner và exception; (5) listener có là bean hợp lệ không; (6) tác vụ là đồng bộ hay bất đồng bộ; (7) readiness của external dependencies có tiêu chí kiểm tra thực tế chưa.

## 12. Bài tập thực hành

1. Vẽ lại timeline từ `ApplicationPreparedEvent` đến `ApplicationReadyEvent`. Đánh dấu điểm refresh hoàn tất và vị trí runners.
2. Giải thích vì sao `ApplicationStartedEvent` **không** bảo đảm các runners đã chạy.
3. Trong ví dụ, vì sao `EVENT ready` nằm sau cả `RUNNER first` và `RUNNER second`?
4. Đổi `@Order(10)` trên `FirstRunner` thành `@Order(30)` và dự đoán thứ tự của hai dòng runner, không làm thay đổi thứ tự started/ready.
5. Chạy với `--fail-runner`. Vì sao không còn `RUNNER second` hoặc `EVENT ready`?
6. Thử thêm một ready listener sử dụng `getTimeTaken()` với kiểm tra `null`, ghi thời gian đo mà không hard-code giá trị.
7. Nếu `FirstRunner` gọi `CompletableFuture.runAsync(...)` rồi lập tức trả về, có chắc dữ liệu đã sẵn sàng tại `ApplicationReadyEvent` không? Đề xuất hai cách thiết kế tùy mức độ bắt buộc của công việc.
8. Viết `@EventListener` nhận `ApplicationReadyEvent` và in `getApplicationContext().isActive()`. Điều này chứng minh gì và **không** chứng minh gì?
9. Vì sao `@TransactionalEventListener` không phải lựa chọn mặc định cho ready event?
10. So sánh ready event với `ReadinessState.ACCEPTING_TRAFFIC`: mốc nào thường được công bố sau?
11. Khi nào cần `ApplicationListener<ApplicationFailedEvent>` đăng ký từ trước `run` thay vì chỉ `@EventListener` trên bean?
12. Giải thích vì sao việc không thấy ready event trong một test `AnnotationConfigApplicationContext.refresh()` đơn thuần không đồng nghĩa ứng dụng Spring Boot ngoài thực tế bị lỗi.
13. Thiết kế một startup cache thiết yếu: nếu cache server trả lỗi timeout, ứng dụng có nên báo ready không? Cách kiểm tra và xử lý lỗi nằm ở đâu?
14. Trong ứng dụng nhiều contexts hoặc lặp lại nhiều lần `SpringApplication.run`, vì sao không nên dùng một biến static để mặc định đếm đúng một ready event cho cả JVM?

**Tiêu chí đạt:** chạy được dự án Maven, quan sát đúng thứ tự started → runner 1 → runner 2 → ready; biết trường hợp runner throw sẽ chặn ready theo luồng thành công và không nhầm **runner callback đã trả về** với **tác vụ async thực sự đã hoàn tất**.

## 13. Tài liệu chính thức

- Spring Boot 3.3 — SpringApplication, events, runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 API — ApplicationReadyEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 API — ApplicationRunner: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 API — CommandLineRunner: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3 — Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Framework — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
