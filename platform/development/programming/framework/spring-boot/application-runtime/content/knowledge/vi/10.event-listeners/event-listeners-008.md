# Xử lý ngoại lệ từ listener trong lúc khởi động Spring Boot

## 1. Khi một startup listener ném ngoại lệ, chuyện gì xảy ra?

Trong Spring Boot, **application event** là cơ chế công bố các cột mốc vòng đời. Một listener có thể được đăng ký qua `SpringApplication.addListeners(...)`, triển khai `ApplicationListener<E>`, hoặc dùng `@EventListener` trên một bean của `ApplicationContext`. Nếu listener được gọi đồng bộ và ném exception chưa được xử lý, exception có thể lan ngược về thành phần đang phát event, làm `SpringApplication.run(...)` thất bại.

Theo cơ chế mặc định của Spring Framework, application events thường được multicast bằng `SimpleApplicationEventMulticaster` và listener chạy **đồng bộ trong cùng thread với publisher**. Spring Boot vì thế khuyến cáo không thực hiện tác vụ dài trong listener của quá trình startup. Khi ứng dụng thất bại trong giai đoạn khởi động, Boot có cơ chế công bố `ApplicationFailedEvent` để thông báo lỗi và thực hiện đường xử lý thất bại.

**Không được đồng nhất** ba tình huống:

| Tình huống | Điều xảy ra | Kết luận thực tế |
| --- | --- | --- |
| Listener đồng bộ ném `RuntimeException` mà không bắt | Lỗi thường lan đến publisher và có thể làm startup thất bại | Phải xử lý lỗi gốc, không chỉ ẩn log |
| Listener tự `catch` và tiếp tục | Publisher không nhận lỗi nếu listener đã nuốt hoàn toàn | Chỉ hợp lý với lỗi phụ trợ thật sự không thiết yếu |
| Listener chạy bất đồng bộ hoặc multicaster dùng `ErrorHandler` | Lỗi có thể được xử lý ở executor/handler, không lan như mặc định | Phải thiết kế rõ chính sách thất bại; không dùng để che các điều kiện startup bắt buộc |

**Phạm vi bài:** tập trung vào listener được kích hoạt trong tiến trình `SpringApplication.run(...)`, từ các event rất sớm đến `ApplicationStartedEvent` và `ApplicationReadyEvent`. Các event được phát ở runtime sau khi ứng dụng đã ready có cùng nền tảng event của Spring, nhưng hậu quả đối với trạng thái startup có thể khác.

## 2. Những mốc startup và listener có thể thất bại

Thứ tự chính trong Spring Boot 3.x:

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["ApplicationStartingEvent"]
    B --> C["ApplicationEnvironmentPreparedEvent"]
    C --> D["ApplicationContextInitializedEvent"]
    D --> E["ApplicationPreparedEvent"]
    E --> F["refresh ApplicationContext"]
    F --> G["ApplicationStartedEvent"]
    G --> H["AvailabilityChangeEvent: LivenessState.CORRECT"]
    H --> I["ApplicationRunner / CommandLineRunner"]
    I --> J["ApplicationReadyEvent"]
    J --> K["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]

    B -. "Nếu có lỗi khởi động" .-> X["ApplicationFailedEvent"]
    E -. "Nếu có lỗi khởi động" .-> X
    F -. "Nếu có lỗi khởi động" .-> X
    G -. "Nếu có lỗi khởi động" .-> X
    I -. "Nếu có lỗi khởi động" .-> X
    J -. "Nếu có lỗi khởi động" .-> X
~~~

Đây là sơ đồ tóm lược: event `ApplicationFailedEvent` được phát trong **đường xử lý khởi động thất bại**, không phải một bước bắt buộc sau mọi mốc; sơ đồ cũng không liệt kê `ContextRefreshedEvent`, web server events, bean post-processors và các bước nội bộ khác.

Các mốc cần nắm:

- `ApplicationStartingEvent`: rất sớm, trước khi xử lý thông thường bắt đầu, trừ việc đăng ký listener/initializer.
- `ApplicationEnvironmentPreparedEvent`: `Environment` đã được chuẩn bị cho context nhưng context chưa được tạo.
- `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent`: context được chuẩn bị và bean definitions được nạp theo từng bước, vẫn trước refresh.
- `ApplicationStartedEvent`: **sau khi context refresh** nhưng **trước** `ApplicationRunner` / `CommandLineRunner`.
- Sau started, Boot phát availability event đánh dấu `LivenessState.CORRECT`.
- `ApplicationReadyEvent`: **sau khi runners hoàn tất**; sau event này, Boot công bố `ReadinessState.ACCEPTING_TRAFFIC`.
- `ApplicationFailedEvent`: được phát khi một exception làm startup thất bại.

### Lỗi ở các mốc khác nhau có hậu quả khác nhau

| Vị trí lỗi | Có context đã refresh? | Điều không nên kỳ vọng |
| --- | --- | --- |
| Listener của `ApplicationStartingEvent` | Chưa | Không thể inject bean của context chưa tồn tại |
| Listener của `ApplicationEnvironmentPreparedEvent` | Chưa | Không thể dựa vào một `@Component` thường để bắt lỗi này |
| Listener của `ApplicationPreparedEvent` | Chưa hoàn tất refresh | Chưa thể coi bean và infrastructure đã sẵn sàng |
| `@EventListener` của `ContextRefreshedEvent` | Đang hoàn tất refresh | Không thể coi startup đã đến `ApplicationStartedEvent` |
| `@EventListener` của `ApplicationStartedEvent` | Đã refresh | Runners có thể chưa chạy, readiness chưa accepting |
| `ApplicationRunner` / `CommandLineRunner` | Đã refresh | Có thể đã live nhưng chưa ready |
| `@EventListener` của `ApplicationReadyEvent` | Đã refresh, runners hoàn tất | Readiness accepting event chuẩn chưa nhất thiết được phát nếu ready listener thất bại |

Một listener đồng bộ ném ngoại lệ ở mốc started có thể ngăn Boot chạy các runner sau đó. Một listener đồng bộ ném ngoại lệ ở mốc ready xảy ra sau khi runners đã chạy, nhưng vẫn có thể khiến `SpringApplication.run(...)` báo thất bại và ngăn đường công bố readiness accepting thông thường.

**Liveness và readiness là trạng thái khác nhau.** Khi lỗi xảy ra sau started, ứng dụng có thể đã công bố `LivenessState.CORRECT` nhưng chưa đạt `ReadinessState.ACCEPTING_TRAFFIC`. Không suy ra “đã live” đồng nghĩa “khởi động thành công trọn vẹn”.

## 3. Vì sao ngoại lệ thường lan ngược về SpringApplication?

Trong đường mặc định, publisher phát một event tới các listener hợp lệ. `SimpleApplicationEventMulticaster` có thể gọi từng listener cùng thread; nếu listener ném exception chưa được handler xử lý, call stack nhận lại exception.

~~~mermaid
sequenceDiagram
    participant Boot as SpringApplication
    participant Bus as ApplicationEventMulticaster
    participant L as StartupListener
    participant Fail as Startup failure handling

    Boot->>Bus: publish ApplicationStartedEvent
    Bus->>L: onApplicationEvent(event)
    L--xBus: throw IllegalStateException
    Bus--xBoot: exception propagates
    Boot->>Fail: handle startup failure
    Fail->>Bus: publish ApplicationFailedEvent (nếu có thể)
    Boot-->>Boot: run không kết thúc thành công
~~~

Đây là mô hình cho listener đồng bộ theo thiết lập mặc định, không phải mã nguồn thực thi từng phương thức của mọi phiên bản. Trong trường hợp dùng `ErrorHandler` tùy biến, `TaskExecutor`, `@Async`, hoặc cơ chế multicaster khác, hành vi truyền lỗi có thể thay đổi.

### Các ngoại lệ nên phân loại

- **`IllegalStateException` hoặc `IllegalArgumentException` của listener:** lỗi validation hoặc bất biến không đạt; có thể cho startup dừng một cách có chủ đích.
- **`BeansException`, ví dụ `BeanCreationException`:** dependency chưa thể tạo hoặc inject; cần tìm nested cause. Đừng mặc định mọi stack trace có `ApplicationEvent` đều bắt đầu từ listener.
- **IOException hoặc HTTP timeout do tác vụ listener tự gọi:** lỗi I/O có thể chỉ là lỗi của logging, audit, telemetry; đánh giá xem đó có thật sự là điều kiện để ứng dụng phục vụ hay không.
- **Lỗi nghiêm trọng như `OutOfMemoryError`:** không nên nuốt bằng `catch (Throwable)` để cố tiếp tục khởi động một tiến trình không còn tin cậy.

Java checked exception không tự biến thành một lỗi Spring Boot chung nhất: annotation listener/reflection có thể bọc ngoại lệ theo cách phụ thuộc API. Khi chẩn đoán hãy đi tới **root cause** trong chain thay vì dựa vào tên exception lớp ngoài.

### ApplicationFailedEvent dùng để quan sát, không phải để “sửa ngược” startup

`ApplicationFailedEvent` mang exception và ngữ cảnh có thể sẵn có tùy thời điểm thất bại. Nó hữu ích để ghi chẩn đoán hoặc gửi tín hiệu ngắn về failure. Nó **không** là hook cho phép đánh dấu ứng dụng thành công trở lại bằng cách nuốt ngoại lệ; trong đường thất bại, context có thể chưa tạo hoặc đã bắt đầu đóng.

Listener của event thất bại cần tối giản và an toàn, vì chính quá trình xử lý lỗi không nên gây thêm exception làm khó truy tìm nguyên nhân ban đầu. Ở mốc rất sớm, logger, bean hoặc resource mà bạn kỳ vọng có thể chưa được chuẩn bị.

## 4. Đăng ký listener nào ở thời điểm nào?

### A. Listener sớm: SpringApplication.addListeners

Một số event phát trước khi `ApplicationContext` tồn tại nên **không thể** trông chờ vào một bean `@Component` / `@Bean` để bắt chúng. Đăng ký programmatic là cách rõ ràng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

// Bên trong main():
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationFailedEvent>) event ->
        System.err.println("STARTUP_FAILED_EVENT"));
app.run(args);
~~~

Đây là snippet minh họa; `MyApplication` cần là class cấu hình khởi động thực tế của dự án, và đoạn code phải nằm trong method thích hợp. Listener được gắn **trước khi gọi `run`** nên có cơ hội quan sát failure kể cả khi context không khởi tạo hoàn chỉnh. Không inject bean vào anonymous listener này rồi giả định bean đã tồn tại trong mọi pha.

Có thể đăng ký listener sớm qua `SpringApplicationBuilder.listeners(...)` hoặc metadata `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener` để Boot tự nạp theo cơ chế được tài liệu hóa. Không tự ghi một bean definition rồi chờ nó nhận `ApplicationStartingEvent`.

### B. Listener của bean: @EventListener

Sau khi context được tạo, các method thuộc bean có thể bắt những sự kiện như `ApplicationStartedEvent`, `ApplicationReadyEvent` và phần lớn event runtime:

~~~java
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class StartupValidationListener {
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED_LISTENER_CALLED");
    }
}
~~~

Bean này sẽ được phát hiện bởi component scan nếu package nằm trong vùng scan. Không nên đánh dấu bean listener là `@Lazy` tùy tiện rồi kỳ vọng method `@EventListener` chắc chắn được đăng ký đúng mốc; Spring Framework lưu ý việc dùng lazy bean có thể khiến event listener không được thiết lập như mong đợi.

### C. ApplicationListener<E> và @EventListener khác gì?

`ApplicationListener<E>` là interface với `onApplicationEvent(E event)`. `@EventListener` đánh dấu một method, có thể có nhiều method trong một bean. Cả hai tham gia cơ chế publish event của Spring; **việc xử lý ngoại lệ phụ thuộc chế độ dispatch/handler**, không phụ thuộc duy nhất vào cú pháp listener.

### D. @Order không giải quyết lỗi startup

`@Order` hoặc `Ordered` giúp xác định thứ tự tương đối giữa các listener thích hợp. Nó không tự biến lỗi bắt buộc thành lỗi không quan trọng. Khi một listener đồng bộ ném exception mà không có handler bắt, không nên giả định các listener cùng event đứng sau nó sẽ được chạy.

## 5. Quy tắc chọn cách xử lý lỗi

Không phải mọi exception đều phải chặn startup. Cần phân biệt mục đích listener:

| Mục đích | Nếu thất bại | Chính sách phù hợp |
| --- | --- | --- |
| Kiểm tra cấu hình bắt buộc để app chạy đúng | Không đủ điều kiện phục vụ | Fail-fast với exception rõ nguyên nhân |
| Nạp state cốt lõi cần trước khi nhận traffic | Chưa được nạp | Chặn startup/ready bằng hook phù hợp và lỗi rõ |
| Gửi metric startup phụ trợ | Monitoring backend tạm lỗi | Log và bỏ qua khi thật sự không ảnh hưởng nghiệp vụ |
| Gửi thông báo audit không trọng yếu | Một notification thất bại | Best effort, có theo dõi retry riêng nếu cần |
| Ghi sự kiện compliance bắt buộc trước khi xử lý dữ liệu | Không thể ghi đúng yêu cầu | Có thể phải fail startup tùy đặc tả hệ thống |
| Làm warm-up có thể thực hiện sau ready | Warm-up chưa xong | Cân nhắc task bất đồng bộ có giám sát; tách khỏi startup path |
| Dọn resource khi startup thất bại | Cleanup không thành công | Ghi lỗi bổ sung nhưng giữ được root cause |

**Nguyên tắc:** nếu không đáp ứng điều kiện thì ứng dụng sẽ phục vụ sai hoặc gây rủi ro dữ liệu, không nên `catch` rồi in “warning” để tiếp tục. Nếu lỗi thực sự thuộc khả năng quan sát hoặc tiện ích phụ trợ, có thể xử lý ngay trong listener để tránh nó quyết định số phận startup.

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    try {
        telemetryClient.sendStartupNotice();
    } catch (RuntimeException ex) {
        logger.warn("Could not send optional startup notice", ex);
    }
}
~~~

Đây là **snippet**, không phải class đầy đủ: cần dependency `telemetryClient`, `logger` và import `@EventListener`/event tương ứng. Nó chỉ hợp lý khi notification không bắt buộc và có khả năng quan sát lỗi. Tránh `catch (Exception ignored) { }` vì sẽ che dấu lỗi mà không có bằng chứng vận hành.

### Lựa chọn hook phù hợp hơn cho việc dài

Spring Boot khuyến nghị dùng `ApplicationRunner` / `CommandLineRunner` cho tác vụ cần chạy trong quá trình startup, thay vì đặt tác vụ dài trong event listener. Runners chạy sau `ApplicationStartedEvent` và trước `ApplicationReadyEvent`. Nếu runner ném exception, startup vẫn có thể thất bại; đây là hành vi có chủ đích nếu công việc runner là điều kiện để ready.

Đối với yêu cầu trì hoãn readiness do tài nguyên ngoài, có thể xây quy trình kiểm soát `ApplicationAvailability` và health probes phù hợp; không nên cài một listener chạy chặn vô hạn rồi khiến tiến trình bị coi là treo.

## 6. Ví dụ đầy đủ Java 17+: listener thành công và listener làm startup thất bại

Ví dụ dùng Spring Boot 3.5.16, Java 17+, Maven, chỉ cần starter nền tảng. Không có web server để giảm nhiễu; các startup events vẫn xảy ra trong ứng dụng command-line. Chạy theo hai chế độ cho thấy sự khác biệt khi listener của `ApplicationStartedEvent` ném exception.

Cấu trúc:

~~~text
startup-listener-demo/
├── pom.xml
└── src/main/java/com/example/listener/
    ├── ListenerDemoApplication.java
    └── StartupGuardListener.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>startup-listener-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
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
~~~

**File `src/main/java/com/example/listener/ListenerDemoApplication.java`:**

~~~java
package com.example.listener;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ListenerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ListenerDemoApplication.class);

        // Listener được gắn trước run; không phụ thuộc vào @Component.
        app.addListeners((ApplicationListener<ApplicationFailedEvent>) event ->
                System.err.println("EVENT=FAILED"));

        app.run(args);
    }

    @Bean
    CommandLineRunner runner() {
        return args -> System.out.println("RUNNER=EXECUTED");
    }
}
~~~

**File `src/main/java/com/example/listener/StartupGuardListener.java`:**

~~~java
package com.example.listener;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupGuardListener {

    private final Environment environment;

    public StartupGuardListener(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT=STARTED");

        boolean fail = environment.getProperty(
                "demo.fail-on-started", Boolean.class, false);

        if (fail) {
            throw new IllegalStateException(
                    "DEMO_STARTUP_GUARD_REJECTED");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT=READY");
    }
}
~~~

Ở đây `StartupGuardListener` là bean được container tạo trước mốc started. `@EventListener` bắt `ApplicationStartedEvent`, kiểm tra cờ CLI qua `Environment`, rồi hoặc trả về bình thường hoặc cố tình ném `IllegalStateException`. Listener thất bại `ApplicationFailedEvent` được gắn bằng `SpringApplication.addListeners(...)` để có thể hoạt động cả trong những pha trước khi context sẵn sàng.

### Build và chạy bình thường

~~~bash
mvn -q -DskipTests package
java -jar target/startup-listener-demo-0.0.1-SNAPSHOT.jar
~~~

Các dòng **do ví dụ tự in**, theo thứ tự trong đường khởi động thành công:

~~~text
EVENT=STARTED
RUNNER=EXECUTED
EVENT=READY
~~~

Spring Boot có thể in thêm logging, kể cả banner và thông tin startup. Những dòng trên là output của listener/runner, không phải toàn bộ stdout.

### Tạo lỗi có chủ đích ở ApplicationStartedEvent

~~~bash
java -jar target/startup-listener-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail-on-started=true
~~~

Với listener đồng bộ mặc định, những dòng do ví dụ chủ động in trước/sau đường failure là:

~~~text
EVENT=STARTED
EVENT=FAILED
~~~

Spring Boot còn ghi stack trace lỗi khởi động, trong đó có thể tìm thấy thông điệp:

~~~text
DEMO_STARTUP_GUARD_REJECTED
~~~

**Kết quả mong đợi:** lần `SpringApplication.run(...)` này không kết thúc thành công; tiến trình Java chạy từ JAR thường thoát với exit code khác 0 sau khi Boot xử lý lỗi. `RUNNER=EXECUTED` và `EVENT=READY` không được in trong nhánh này vì listener ở `ApplicationStartedEvent` đã ngắt startup trước khi Boot gọi runner.

Không nên khẳng định toàn bộ stderr chỉ có một dòng `EVENT=FAILED` hoặc mọi bản Boot đều đóng gói root cause dưới cùng một loại wrapper exception. Điều cần kiểm chứng là **nguyên nhân ban đầu**, thứ tự event và việc nhánh ready không đạt được.

**Lưu ý lệnh shell:** ký tự `\` nối dòng dành cho Bash/Unix; trên PowerShell/cmd, đặt `java -jar ... --demo.fail-on-started=true` trên một dòng hoặc dùng cú pháp nối dòng phù hợp.

### Đọc output một cách đáng tin

Trong log lỗi, tìm thông điệp `DEMO_STARTUP_GUARD_REJECTED` và lớp `StartupGuardListener.onStarted`. Chúng xác định điểm phát sinh. Sau đó mới xem dòng framework bọc lỗi như `Application run failed`. Nếu thấy `EVENT=FAILED`, đó là dấu hiệu failure listener đã được gọi; nó không làm startup trở lại thành công.

## 7. Một thay đổi nhỏ, ba chính sách xử lý khác nhau

Giả sử `onStarted(...)` cần gọi một service phụ trợ:

~~~java
void sendNotification() {
    notificationService.notifyStartup();
}
~~~

Đây là snippet ý tưởng (cần `notificationService` hợp lệ), có thể đưa vào ba chính sách:

**Chính sách A — fail-fast:** notification là điều kiện bắt buộc để nhận traffic. Để exception có thông điệp rõ và lan ra startup; phải có khả năng operator biết nguyên nhân và sửa cấu hình/dịch vụ.

**Chính sách B — best effort:** notification chỉ là tiện ích phụ. Bắt exception riêng của tác vụ, log với context không nhạy cảm, báo metric/tracing và tiếp tục. Điều này không áp dụng cho lỗi kiểm tra bảo mật, schema hay dữ liệu cốt lõi.

**Chính sách C — chạy tách biệt:** notification có thể được xử lý sau startup trong executor hoặc queue. Khi đó cần xác định nơi lưu lỗi, retry/backoff, idempotency và giới hạn tài nguyên. Không chuyển một tác vụ bắt buộc sang async chỉ để “qua startup”; nếu cần bảo đảm trước khi nhận traffic, hãy điều phối readiness rõ ràng.

### Khi một listener tự nuốt exception

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    try {
        updateOptionalDashboard();
    } catch (Exception ex) {
        logger.warn("Optional dashboard update failed", ex);
    }
}
~~~

Snippet minh họa cần `logger` và `updateOptionalDashboard()` do ứng dụng cung cấp. Nếu lỗi dashboard là không thiết yếu, cách này chấp nhận được. Nếu lỗi có thể đến từ bất biến bắt buộc và bị bắt chung bởi `catch (Exception)`, ranh giới lỗi đã bị làm mờ. Nên bắt loại lỗi phù hợp, có log rõ và không vô tình giấu lỗi lập trình.

### Khi thêm custom ErrorHandler vào ApplicationEventMulticaster

Spring Framework hỗ trợ thay `ApplicationEventMulticaster` của context, chẳng hạn cung cấp bean tên `applicationEventMulticaster` và cấu hình `SimpleApplicationEventMulticaster.setErrorHandler(...)`. Handler có thể xử lý/log một exception thay vì cho lan về publisher.

Điều này hữu ích trong một số hệ thống event **nghiệp vụ**, nhưng là cơ chế ở mức infrastructure. Nó không nên được bật chung để “tất cả listener thất bại nhưng app vẫn chạy” khi listener chứa startup validation bắt buộc. Hơn nữa, **event rất sớm trước context** do cơ chế listener của `SpringApplication` xử lý, nên custom bean multicaster trong context không thể được xem là bảo đảm áp dụng với mọi sự kiện bootstrap.

Nếu cần xử lý lỗi phụ trợ, `try/catch` cục bộ tại listener thường rõ ràng hơn một handler toàn cục thay đổi semantics của cả ứng dụng.

## 8. Async listener: lỗi có thể không làm run() thất bại

Spring Framework hỗ trợ `@Async` trên một `@EventListener` khi ứng dụng đã bật async infrastructure phù hợp (chẳng hạn `@EnableAsync` và executor). Ví dụ minh họa:

~~~java
@Async
@EventListener
public void sendOptionalTelemetry(ApplicationStartedEvent event) {
    telemetryClient.sendStartupNotice();
}
~~~

Đoạn trên cần các import `org.springframework.scheduling.annotation.Async` và `org.springframework.context.event.EventListener`, cùng collaborator `telemetryClient`. Đây là ví dụ về **tác vụ phụ trợ**, không phải một startup guard.

Các hệ quả cần nắm:
1. Với event listener bất đồng bộ, exception từ worker thread **không tự lan** về caller đã phát event như listener đồng bộ mặc định.
2. Lỗi từ async method `void` cần được giám sát bằng `AsyncUncaughtExceptionHandler` và logging/observability tương ứng.
3. `ThreadLocal` và logging context không mặc định được truyền sang thread async; correlation/tracing cần cấu hình nếu cần.
4. Không dùng return value của method `@Async @EventListener` để publish event kế tiếp; muốn phát thêm event thì inject `ApplicationEventPublisher` và publish chủ động.
5. Không mặc định mọi event nền tảng và mọi listener đều có thể xử lý async theo cùng một cách; một số listener/event có quy tắc hỗ trợ thực thi đặc biệt, đặc biệt ở giai đoạn bootstrap.

**Bẫy startup:** nếu kiểm tra cấu hình bảo mật trong async listener, `SpringApplication.run(...)` có thể đạt ready trước khi check này xong hoặc trước khi lỗi được ghi nhận. Đối với điều kiện phải đạt trước khi nhận traffic, dùng validation đồng bộ hoặc một lifecycle/readiness gate được thiết kế rõ ràng.

## 9. Khi nào dùng ApplicationFailedEvent, FailureAnalyzer và exception trực tiếp?

| Cơ chế | Nên dùng cho | Không nên dùng để |
| --- | --- | --- |
| Ném exception từ listener/runner | Chặn startup khi tiền điều kiện quan trọng bị vi phạm | Kiểm soát logic retry dài bằng cách crash liên tục |
| `ApplicationFailedEvent` listener | Ghi/thu thập tín hiệu thất bại khởi động ngắn và an toàn | Coi event như một cơ hội phục hồi context đã hỏng |
| `FailureAnalyzer` | Trả thông báo chẩn đoán với description/action rõ ràng cho nhóm failure nhận diện được | Tự động sửa lỗi mà không xử lý root cause |
| `ApplicationAvailability` / readiness | Điều phối nhận traffic khi instance vẫn live | Thay thế việc báo lỗi startup bắt buộc |
| `ApplicationRunner` / `CommandLineRunner` | Công việc startup sau context refresh | Giải quyết event rất sớm trước context |

### ApplicationFailedEvent có thể bắt được lỗi khởi động nào?

Ví dụ lỗi do bean creation, refresh context, runner hoặc listener đồng bộ có thể đi vào đường xử lý failure của Boot. Một listener thất bại được đăng ký sớm có thể quan sát `ApplicationFailedEvent`, nhưng không nên phụ thuộc vào khả năng dùng tất cả bean/context ở thời điểm đó.

Nếu một listener của **chính `ApplicationFailedEvent`** ném exception, việc xử lý lỗi có thể thêm nhiễu hoặc làm khó phân tích. Do đó handler của failure event nên tránh gọi mạng bắt buộc, tránh lấy bean chưa chắc có và không nuốt root cause.

### FailureAnalyzer khác ApplicationFailedEvent ra sao?

`FailureAnalyzer` tập trung vào việc diễn giải một kiểu exception thành thông điệp có thể hành động, ví dụ “không bind được cổng vì đã có process khác dùng”. `ApplicationFailedEvent` cho biết startup thất bại và cung cấp exception; nó không tự sinh ra remediation chính xác. Dùng failure analyzer khi làm thư viện/framework có loại lỗi cấu hình lặp lại và muốn người dùng nhận thông báo tốt hơn.

## 10. Chẩn đoán lỗi listener trong thực tế

### Trường hợp A: Startup thất bại ở ApplicationEnvironmentPreparedEvent

**Dấu hiệu:** log báo exception khi bootstrapping Environment, chưa có bean/controller và các listener được khai báo bằng `@Component` không được gọi.

**Cách xử lý:** kiểm tra listener đăng ký bằng `addListeners` hoặc `spring.factories`, thứ tự PropertySources/config data và thao tác đọc property. Không yêu cầu `ApplicationContext.getBean(...)` khi context chưa tồn tại. Nếu cần cấu hình sớm, dùng hook được Boot hỗ trợ, không chuyển xử lý tùy ý vào một listener mà không hiểu thứ tự bootstrap.

### Trường hợp B: @EventListener của ApplicationStartedEvent làm runner không chạy

**Dấu hiệu:** thấy started rồi lỗi của listener, nhưng không có log runner hoặc ready.

**Cách xử lý:** xem stack trace của listener, phân loại exception là điều kiện bắt buộc hay lỗi phụ trợ. Nếu bắt buộc, sửa nguyên nhân và cho fail-fast. Nếu phụ trợ, đặt error handling tại ranh giới tác vụ đó; không lạm dụng global multicaster ErrorHandler.

### Trường hợp C: ApplicationReadyEvent listener ném lỗi

**Dấu hiệu:** runner đã chạy, có log ready event liên quan nhưng startup vẫn bị báo lỗi và readiness probe chưa chuyển accepting.

**Cách xử lý:** đọc stack trace listener `ApplicationReadyEvent`. Đừng nghĩ “ready đã phát” nghĩa là mọi callback ready đã thành công. Nếu công việc cần được làm trước khi ready, nên đặt ở runner/lifecycle hook phù hợp; nếu phụ trợ thì xử lý độc lập có giám sát.

### Trường hợp D: Exception xuất hiện trong log async nhưng startup vẫn thành công

**Dấu hiệu:** application sẵn sàng, lỗi xuất hiện ở thread executor sau đó.

**Cách xử lý:** kiểm tra `@Async`, executor, `AsyncUncaughtExceptionHandler` hoặc `ErrorHandler`. Tìm nơi lưu và quan sát lỗi; kiểm chứng tác vụ async có nên được đưa khỏi startup path hay không. Không kết luận Spring đã “nuốt” lỗi nếu chính ứng dụng cấu hình async/best effort.

### Trường hợp E: Có ApplicationFailedEvent nhưng log thiếu nguyên nhân gốc

**Dấu hiệu:** chỉ thấy thông báo chung `Application run failed` hoặc exception wrapper.

**Cách xử lý:** mở đầy đủ cause chain, tìm `Caused by` và method listener đầu tiên do ứng dụng sở hữu. `ApplicationFailedEvent.getException()` là điểm bắt đầu hợp lý nhưng có thể chứa wrapper; đừng chỉ in `getMessage()` rồi bỏ stack trace. Nếu config chứa credentials, log hạn chế các thông tin nhạy cảm.

### Trường hợp F: Một listener được gọi hai lần khi dùng context hierarchy

Trong Spring, event từ child context có thể được propagate lên parent, nên listener parent có thể thấy nhiều event cùng loại. Kiểm tra context của event so với context mà listener quản lý nếu cần lọc. Không coi mọi event lặp là do listener exception/ retry tự động.

### Trường hợp G: Exception từ listener không xuất hiện ở SpringApplication.run

Kiểm tra event có thực sự do startup publish hay không, listener đang chạy async không, custom multicaster có `ErrorHandler` hay không, và lỗi đã bị try/catch nội bộ giữ lại chưa. Nếu event phát **sau khi startup đã hoàn tất**, không nhất thiết còn một call stack `SpringApplication.run` để bubble lỗi trở về.

## 11. Khuyến nghị kiểm thử và vận hành

Các tình huống nên kiểm thử có chủ đích cho listener có khả năng chặn startup:

- **Happy path:** listener chạy bình thường; startup tiến qua runner và ready.
- **Fail-fast path:** bật một điều kiện lỗi xác định; kiểm tra exception/root cause, không xuất hiện mốc ready và build/deploy nhận tín hiệu startup thất bại.
- **Best-effort path:** dependency telemetry phụ trợ lỗi; ứng dụng vẫn ready, log/metric lỗi có thông tin đủ hành động.
- **Async path (nếu dùng):** lỗi được ghi bởi executor/handler; không đợi publisher đồng bộ bắt exception.
- **Early-failure path:** nếu có listener trước context, xác minh việc báo lỗi vẫn hoạt động khi bean/container chưa tồn tại.

Có thể dùng `@SpringBootTest` hoặc chạy `SpringApplication` trong integration test phù hợp để kiểm tra event và failure; nếu chỉ dùng `ApplicationContextRunner`, cần hiểu nó thử khởi tạo context theo cách riêng và **không mặc nhiên mô phỏng toàn bộ chuỗi sự kiện `SpringApplication.run`**. Để kiểm chứng chính xác `ApplicationStartedEvent` / `ApplicationFailedEvent` ở mức Boot, hãy dùng startup path thực tế hoặc một harness chạy `SpringApplication` có kiểm soát.

Trong môi trường triển khai:
- Phân biệt **exit code/startup failed** với **readiness unhealthy** và **liveness broken**.
- Cấu hình restart/backoff sao cho một lỗi cấu hình không gây vòng lặp khởi động dày đặc vô ích.
- Tránh logging bí mật từ `Environment` hoặc CLI arguments khi ghi chẩn đoán.
- Quan sát latency của startup listeners; tác vụ dài hoặc blocking I/O trên event thread có thể làm thời gian deploy và recovery tăng.
- Nếu dùng Spring Security/web server, một lỗi startup ở listener có thể làm context đóng sau khi web infrastructure đã khởi tạo một phần; đừng suy ra chỉ từ log server started rằng toàn bộ `run(...)` thành công.

## 12. Tổng hợp quyết định theo triệu chứng

| Quan sát | Câu hỏi đầu tiên | Hành động ưu tiên |
| --- | --- | --- |
| `ApplicationStartedEvent` listener ném lỗi | Lỗi có phải tiền điều kiện bắt buộc? | Fail-fast nếu có; sửa root cause |
| Runner không chạy | Có exception ở started event/earlier? | Đọc exception và vị trí listener |
| `ApplicationReadyEvent` xuất hiện nhưng app vẫn fail | Có ready listener ném exception? | Xác định callback lỗi; xem readiness cuối cùng |
| `ApplicationFailedEvent` được phát | Exception gốc là gì? | Theo cause chain và phân loại phase |
| Startup vẫn success dù listener lỗi | Async, ErrorHandler hay catch nội bộ? | Kiểm chứng chính sách dispatch và observability |
| Cần quan sát lỗi trước context | Listener đã đăng ký trước `run` chưa? | `SpringApplication.addListeners` / `spring.factories` |
| Có listener `@Component` cho `ApplicationStartingEvent` nhưng không chạy | Context đã tồn tại lúc event phát chưa? | Chuyển registration sang cơ chế sớm |
| Liveness CORRECT nhưng chưa nhận traffic | Runners/ready đã hoàn tất chưa? | Kiểm tra readiness, không suy từ liveness |
| Chạy listener lâu, startup chậm | Có network/blocking task trong listener không? | Di chuyển sang runner hoặc job có giám sát |
| Logger trong failure listener lại lỗi | Có dựa vào context chưa khởi tạo? | Giảm dependency của failure handler, giữ cause gốc |

## 13. Câu hỏi tự kiểm tra

**1. Listener `@EventListener(ApplicationStartedEvent)` đồng bộ ném `IllegalStateException` không được bắt. Boot có bắt buộc chạy các runner sau đó không?**  
Không. Ngoại lệ có thể ngăn startup trước bước runner, và Spring Boot chuyển qua đường xử lý failure.

**2. Tại sao không nên dùng bean `@Component` để bắt `ApplicationStartingEvent`?**  
Event này phát trước khi context tồn tại. Cần đăng ký listener với `SpringApplication`/metadata hỗ trợ trước `run`.

**3. `ApplicationFailedEvent` có tự khôi phục một context khởi động lỗi không?**  
Không. Nó phục vụ báo hiệu/quan sát failure. Khắc phục lỗi gốc rồi chạy lại startup theo quy trình.

**4. Nếu dùng `@Async @EventListener`, exception có tự ném ngược về thread phát event không?**  
Không theo cách đồng bộ mặc định; cần chính sách giám sát, handler hoặc xử lý future phù hợp.

**5. Có nên dùng global ErrorHandler để bỏ qua mọi exception của startup listener không?**  
Không. Có thể che tiền điều kiện bắt buộc; chỉ cân nhắc khi hiểu phạm vi và hậu quả trên event multicaster.

**6. Vì sao listener ở `ApplicationStartedEvent` có thể chạy khi readiness còn refusing?**  
Started phát sau refresh nhưng trước runners. Readiness accepting chuẩn chỉ được publish sau ready event.

**7. Một listener `ApplicationReadyEvent` ném exception có thể khiến readiness accepting không được phát không?**  
Có. Ready event được publish trước availability accepting; lỗi đồng bộ có thể làm đường startup thất bại.

**8. Cách tốt nhất để ghi một thông điệp failure dễ hành động cho loại exception của framework là gì?**  
Có thể triển khai `FailureAnalyzer` phù hợp; bản thân event failure chỉ cung cấp dữ kiện lỗi.

**9. Khi thấy một exception wrapper, bạn nên đọc gì?**  
Root cause, stack trace và method listener gốc, thay vì chỉ đọc dòng `Application run failed`.

**10. Khi telemetry startup lỗi nhưng không ảnh hưởng nghiệp vụ, nên làm gì?**  
Bắt/log lỗi tại ranh giới telemetry hoặc tách job có giám sát; ứng dụng không nhất thiết phải thất bại vì nhiệm vụ phụ trợ.

## Tài liệu tham khảo chính thức

- [Spring Boot — SpringApplication, Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — Application Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.startup-failure)
- [Spring Framework — ApplicationContext Events, @EventListener và Async Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Boot — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Boot — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html)
- [Maven Central — spring-boot-starter-parent 3.5.16](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16)

Các chi tiết về dispatcher, hỗ trợ async và error handler phụ thuộc phiên bản/cấu hình. Hãy đối chiếu đúng phiên bản Spring Boot/Spring Framework trong dependency tree trước khi thay đổi chính sách exception trong startup listener.