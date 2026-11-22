# ApplicationFailedEvent và trường hợp chưa có ApplicationContext

Trong Spring Boot, thất bại khi khởi động không nhất thiết xảy ra sau khi ứng dụng đã tạo được `ApplicationContext`. Lỗi có thể xuất hiện ngay lúc chuẩn bị `Environment`, nạp config data hoặc chạy một listener bootstrap; khi đó **chưa có context để truy cập bean**. Một lỗi khác có thể xuất hiện muộn hơn khi tạo bean, refresh context, mở cổng HTTP hoặc chạy `ApplicationRunner`. Cả hai đều thuộc phạm vi **startup failure**, nhưng khả năng sử dụng context khác nhau.

`ApplicationFailedEvent` (package `org.springframework.boot.context.event`) là sự kiện Spring Boot phát khi một lần chạy `SpringApplication` thất bại. Hai điểm quan trọng nhất:

- `event.getException()` trả về nguyên nhân lỗi dưới dạng `Throwable`.
- `event.getApplicationContext()` có thể trả về **`null`**, vì Spring Boot có thể phát failure event khi chưa tạo được context. **Ngay cả khi khác `null`, context vẫn có thể chưa refresh thành công hoặc đang được dọn dẹp**.

Bài học sử dụng Java 17+ và Spring Boot 3.3.x, tập trung vào cách đăng ký listener đủ sớm, xử lý an toàn khi context vắng mặt, và phân biệt lỗi startup với lỗi runtime sau khi ứng dụng đã ready.

## 1. Vị trí của ApplicationFailedEvent trong chuỗi khởi động

Luồng chính của một lần khởi động bình thường:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |
    +-- Chuẩn bị Environment / config data
    |      |
    |      +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Tạo ApplicationContext
    |
    +-- ApplicationContextInitializedEvent
    |
    +-- Nạp bean definitions
    |
    +-- ApplicationPreparedEvent
    |
    +-- Refresh ApplicationContext
    |
    +-- ApplicationStartedEvent
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |
    +-- run() trả về context
~~~

Đây là sơ đồ các cột mốc Spring Boot, không phải bản sao từng lời gọi nội bộ. Trong lúc startup, nếu một exception đi qua cơ chế xử lý thất bại của `SpringApplication.run(...)`, Boot sẽ phát `ApplicationFailedEvent` cho những listener có thể nhận sự kiện ở thời điểm đó, đồng thời thực hiện xử lý thất bại và dọn dẹp thích hợp.

Ví dụ:

~~~text
Nhánh A: lỗi đọc cấu hình / xử lý Environment
         |
         +-- ApplicationFailedEvent
             getApplicationContext() == null

Nhánh B: tạo được context, nhưng refresh/tạo bean thất bại
         |
         +-- ApplicationFailedEvent
             getApplicationContext() != null
             (context chưa chắc active hoặc dùng được)

Nhánh C: context refresh xong, nhưng runner ném exception
         |
         +-- ApplicationFailedEvent
             (startup vẫn bị coi là thất bại)
~~~

**Không được suy ngược rằng có failure event thì chắc chắn có context.** Việc nhận `ApplicationFailedEvent` là tín hiệu về thất bại của *lần khởi động*, không phải bằng chứng ApplicationContext đã được tạo hoặc đã sẵn sàng sử dụng.

## 2. API cần biết

Các phương thức quan trọng:

| API | Ý nghĩa | Lưu ý |
|---|---|---|
| `ApplicationFailedEvent.getException()` | Trả về `Throwable` dẫn đến lỗi startup. | Có thể là exception bao ngoài; xem `getCause()` và stack trace để tìm lỗi gốc. |
| `ApplicationFailedEvent.getApplicationContext()` | Trả về `ConfigurableApplicationContext` đang khởi tạo, **hoặc `null`**. | Không gọi `getBean()` hay `getEnvironment()` trên kết quả trước khi kiểm tra `null`. |
| `ApplicationFailedEvent.getArgs()` | Trả về arguments của lần chạy `SpringApplication`. | Không ghi nguyên văn vào log nếu arguments có password/token. |
| `ApplicationFailedEvent.getSpringApplication()` | Cho biết `SpringApplication` phát event. | Hữu ích khi điều phối nhiều application/context. |
| `SpringApplication.addListeners(...)` | Đăng ký listener trước khi gọi `run()`. | Cách phù hợp để nhận những event xảy ra trước khi có bean. |
| `SpringApplicationBuilder.listeners(...)` | Đăng ký listener vào builder. | Hữu ích khi khởi động qua builder hoặc hierarchy. |

Constructor của `ApplicationFailedEvent` nhận application, arguments, context và exception; trong Javadoc, tham số context có thể là `null`.

Các kiểu cần import:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Không nhầm `ApplicationFailedEvent` với `ContextClosedEvent` hay `ContextRefreshedEvent`:

- `ApplicationFailedEvent`: một lần `SpringApplication` khởi động thất bại.
- `ContextClosedEvent`: một context được đóng; việc đóng bình thường **không** đồng nghĩa startup lỗi.
- `ContextRefreshedEvent`: context đã refresh; không phải tín hiệu toàn bộ startup runner của Boot đã hoàn tất.
- `ApplicationReadyEvent`: một lần startup bình thường đã vượt qua các runner và báo ready.

## 3. Vì sao đôi khi chưa có context?

Trước khi tạo `ApplicationContext`, Spring Boot còn phải khởi tạo cơ chế bootstrap, chuẩn bị `Environment`, xử lý các property sources và những cấu hình cần dùng ở giai đoạn sớm. Ví dụ lỗi có thể xảy ra khi:

- Một `EnvironmentPostProcessor` tự viết ném exception.
- Cấu hình config data hoặc nguồn cấu hình bắt buộc không hợp lệ, khiến quá trình chuẩn bị environment thất bại.
- Listener đăng ký sớm cho `ApplicationEnvironmentPreparedEvent` ném exception.
- Một thành phần bootstrap khác xảy ra lỗi trước khi code gọi tới bước tạo `ApplicationContext`.

Trong những trường hợp này, Spring Boot **chưa thể đưa ra context đã được tạo**. API vẫn giữ được thông tin về application, arguments và exception, nhưng `getApplicationContext() == null`.

Lưu ý: không phải *mọi lỗi xảy ra trên JVM* đều trở thành `ApplicationFailedEvent`. Nếu lỗi xuất hiện trước khi `SpringApplication.run(...)` thực sự bắt đầu (chẳng hạn code trong `main` ném exception trước lời gọi `run`, lỗi class initialization hoặc lỗi khởi tạo chính `SpringApplication`), cơ chế gửi failure event của `run(...)` có thể chưa được thiết lập. Các exception ở request, scheduler hay message listener **sau khi startup đã thành công** cũng không mặc nhiên phát sự kiện này.

Do đó, khi thiết kế giám sát, `ApplicationFailedEvent` là **một hook chẩn đoán lỗi startup**, không phải bộ bắt toàn bộ lỗi của process.

## 4. Đăng ký listener đủ sớm

### Cách đúng: đăng ký trước run()

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartupFailureListener());
app.run(args);
~~~

Đây là **đoạn sử dụng API**, không phải file Java độc lập: `MyApplication` và `StartupFailureListener` phải được định nghĩa như trong ứng dụng của bạn.

Listener muốn xử lý startup failure nên được đăng ký **trước** lời gọi `run()` để Boot đã biết listener ngay từ các pha bootstrap. Khi ứng dụng cần listener tự động bất kể ai gọi `SpringApplication.run(...)`, Spring Boot còn hỗ trợ đăng ký qua `META-INF/spring.factories` bằng khóa `org.springframework.context.ApplicationListener`.

### Cách dễ sai: chỉ tạo listener dưới dạng bean

~~~java
@Component
public class TooLateForEarlyFailure
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        System.err.println(event.getException());
    }
}
~~~

Đây là **minh họa một lớp có đầy đủ interface nhưng chưa khai báo imports**. Vấn đề không nằm ở khả năng nhận event sau khi bean được tạo: vấn đề là **bean này chưa thể tồn tại nếu failure xảy ra trước khi ApplicationContext được tạo hoặc trước lúc bean được đăng ký/khởi tạo**. Không nên dùng một `@Component`/`@Bean` đơn thuần làm **cơ chế duy nhất** để bắt lỗi bootstrap.

Tương tự, `@EventListener(ApplicationFailedEvent.class)` trên một bean không giải quyết được trường hợp chưa có context. Với các listener cần chạy thật sớm, hãy dùng registration ở mức `SpringApplication`, `SpringApplicationBuilder` hoặc cấu hình registration được Boot xử lý trước run.

## 5. Ví dụ chạy được: lỗi trước context và lỗi khi tạo bean

Dự án sau có **một listener được đăng ký ngay trước `run()`**. Nó tạo hai kịch bản bằng command-line argument:

- `--demo.fail-phase=environment`: chủ động ném exception trong listener của `ApplicationEnvironmentPreparedEvent`, trước khi Boot tạo context.
- `--demo.fail-phase=bean`: cho environment được chuẩn bị và context được tạo, rồi ném exception khi chạy factory method `@Bean` trong quá trình refresh.

### Cấu trúc dự án

~~~text
failed-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── failed/
                        └── FailedEventDemo.java
~~~

Tạo `pom.xml` tại root dự án:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>failed-event-demo</artifactId>
    <version>1.0.0</version>

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

Tạo `src/main/java/com/example/failed/FailedEventDemo.java`:

~~~java
package com.example.failed;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class FailedEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(FailedEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Quan trong: listener duoc dang ky TRUOC run().
        app.addListeners(new EarlyStartupListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("[main] STARTED");
        }
        catch (RuntimeException ex) {
            // Demo chu dong bat loi de hien thi cac moc de quan sat.
            System.out.println("[main] run() threw exception");
        }
    }

    @Bean
    DemoMarker demoMarker(@Value("${demo.fail-phase:none}") String phase) {
        if ("bean".equals(phase)) {
            throw new IllegalStateException("failure-in-bean");
        }
        return new DemoMarker();
    }

    static final class DemoMarker {
    }

    static final class EarlyStartupListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
                String phase = prepared.getEnvironment()
                        .getProperty("demo.fail-phase", "none");

                if ("environment".equals(phase)) {
                    System.out.println("[probe] fail before context");
                    throw new IllegalStateException("failure-before-context");
                }
            }
            else if (event instanceof ApplicationFailedEvent failed) {
                System.out.println("[failed] context-null="
                        + (failed.getApplicationContext() == null));
                System.out.println("[failed] root-message="
                        + rootMessage(failed.getException()));
            }
        }

        private String rootMessage(Throwable throwable) {
            Throwable root = throwable;
            while (root.getCause() != null && root.getCause() != root) {
                root = root.getCause();
            }
            return root.getMessage();
        }
    }
}
~~~

Trong ví dụ này:

1. Listener implement `ApplicationListener<ApplicationEvent>` và dùng `instanceof` để phân loại hai event, nên không phụ thuộc vào việc một bean listener được tạo đúng thời điểm.
2. `SpringApplication.addListeners(...)` được gọi **trước `run(...)`**. Listener có thể nhận sự kiện khi chưa có context.
3. Nhánh `environment` ném exception ngay khi `Environment` đã sẵn sàng nhưng **trước** bước tạo context.
4. Nhánh `bean` ném exception từ factory method `demoMarker(...)` khi Boot đã bắt đầu tạo/refresh context.
5. Nhánh `ApplicationFailedEvent` luôn kiểm tra context có `null` hay không, rồi mới diễn giải.
6. `rootMessage(...)` đi qua chuỗi `getCause()` để tìm message của nguyên nhân sâu nhất; trong hệ thống thực tế còn cần giữ stack trace và các exception liên quan để không mất ngữ cảnh.
7. `catch (RuntimeException)` ở `main` chỉ phục vụ bài thực hành. **Ứng dụng production không nên nuốt lỗi startup rồi thoát với trạng thái thành công**; cần để supervisor/orchestrator biết tiến trình khởi động thất bại.

Ví dụ dùng `WebApplicationType.NONE` để không phải xử lý web server và dùng `Banner.Mode.OFF` để output dễ quan sát. `spring-boot-starter` đủ cho Spring context, logging và các API dùng ở đây.

### Biên dịch và chạy

Cần JDK 17+ và Maven tương thích với dự án:

~~~bash
mvn package
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=environment
~~~

Trong Windows PowerShell có thể dùng cùng hai lệnh. Để kiểm tra lỗi xảy ra sau khi context đã được tạo:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=bean
~~~

Và để kiểm tra lần khởi động bình thường:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar
~~~

Đây là dự án Spring Boot đầy đủ về mã nguồn và dependency cần thiết; nó **không chạy độc lập chỉ bằng `javac FailedEventDemo.java`** khi chưa có Spring trên classpath.

### Kịch bản A: lỗi trước context

Lệnh:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=environment
~~~

Các **dòng do code bài thực hành tự in**, theo thứ tự:

~~~text
[probe] fail before context
[failed] context-null=true
[failed] root-message=failure-before-context
[main] run() threw exception
~~~

Các dòng log và stack trace do Spring Boot phát có thể xen vào giữa những mốc này, không có nội dung cố định theo timestamp/logger. Thông tin cần quan sát là **`context-null=true`** vì exception phát sinh ngay lúc xử lý `ApplicationEnvironmentPreparedEvent`, trước bước tạo context.

### Kịch bản B: lỗi sau khi context đã được tạo

Lệnh:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=bean
~~~

Các **dòng do code tự in**, theo thứ tự:

~~~text
[failed] context-null=false
[failed] root-message=failure-in-bean
[main] run() threw exception
~~~

Khi factory method `@Bean` ném `IllegalStateException`, Spring có thể bọc lỗi trong `BeanCreationException` hoặc các exception tạo bean khác. Tuy nhiên, thông điệp nguyên nhân sâu nhất do chương trình chủ động ném là `failure-in-bean`. Spring Boot đã tạo object context trước khi tiến hành refresh và tạo bean, vì vậy sự kiện thất bại có reference đến context (khác `null`).

**Không suy diễn `context-null=false` thành `context.isActive()==true`, và càng không suy diễn thành ứng dụng ready.** Context tại thời điểm lỗi có thể mới được tạo, đang refresh dở hoặc không thể tiếp tục sử dụng.

### Kịch bản C: khởi động thành công

Lệnh:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar
~~~

Dòng tự in từ `main`:

~~~text
[main] STARTED
~~~

Trong kịch bản này chương trình không cố ý ném exception; `ApplicationFailedEvent` không được phát. Sau khi in marker, khối `try-with-resources` chủ động đóng context để ứng dụng console kết thúc sạch.

## 6. Xử lý event an toàn khi context có thể null

Một mẫu xử lý thực tế nên:

1. **Luôn lấy exception trước**, vì nguyên nhân lỗi là dữ liệu chính của failure event.
2. **Xét context có null hay không**, thay vì giả định context luôn tồn tại.
3. **Không bắt buộc truy cập bean** để ghi nhận sự cố. Chọn một kênh báo lỗi đã có sẵn độc lập với Spring context.
4. **Không sử dụng context như thể đã refresh** ngay cả khi object khác `null`.
5. Giữ xử lý listener **nhanh, tối giản, ít gây lỗi thứ cấp**.

Ví dụ minh họa một listener chuyên trách (đặt ở lớp riêng và đăng ký qua `app.addListeners(...)`):

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

public final class StartupFailureLogger
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        ConfigurableApplicationContext context =
                event.getApplicationContext();

        System.err.println("Startup failed: "
                + failure.getClass().getName());

        if (context == null) {
            System.err.println("Phase: before context creation");
            return;
        }

        // Co context object, khong co nghia refresh da thanh cong.
        System.err.println("Context object exists; do not fetch beans");
    }
}
~~~

Đoạn trên mô tả **file Java `StartupFailureLogger.java`** trong một package do bạn lựa chọn; khi đưa vào dự án thật, thêm khai báo `package` phù hợp. Listener này không cần Spring bean để hoạt động, miễn bạn đăng ký instance của nó trước `run()`.

Có thể cân nhắc log lỗi một cách idempotent: Spring Boot vốn đã thực hiện báo cáo lỗi, nên listener tùy chỉnh không nhất thiết phải in full stack trace thêm một lần nữa. Nếu cần metric hoặc thông báo ra hệ thống ngoài, hãy đặt timeout ngắn, có fallback và tránh để lỗi gửi thông báo che mất root cause của startup failure.

### Tại sao không gọi getBean() trong ApplicationFailedEvent?

Đoạn sau **không an toàn**:

~~~java
ConfigurableApplicationContext context = event.getApplicationContext();
AlertService service = context.getBean(AlertService.class);
service.notifyFailure(event.getException());
~~~

Đây là mã phản ví dụ: `AlertService` giả sử là một service được Spring quản lý; không phải snippet runnable. Nó có thể ném `NullPointerException` nếu `context == null`, hoặc `IllegalStateException`/`BeanCreationException` nếu context có object nhưng chưa refresh thành công. Ngay cả khi bean lấy được, các dependency của nó cũng có thể đang ở trạng thái không dùng được.

Phương án an toàn hơn:

- Dùng một thành phần báo lỗi **được khởi tạo độc lập** trước khi Boot startup, với tài nguyên và lifecycle đã biết.
- Hoặc chỉ ghi lại cause, phase và correlation ID ở mức tối thiểu; để logging/observability agent của process thu thập.
- Nếu cần gửi alert sau startup failure, bên ngoài JVM (orchestrator, process supervisor, CI, deployment controller) thường là nơi ổn định hơn để quan sát exit status và log.

## 7. Lỗi sau khi tạo context nhưng trước ready

Trường hợp `context != null` có thể xuất hiện ở nhiều pha khác nhau:

| Vị trí lỗi | Context đã tồn tại? | Có thể dùng bean/context như bình thường? |
|---|---|---|
| Chuẩn bị config data hoặc environment | Chưa | Không. |
| Tạo `ApplicationContext` thất bại trước khi trả về object | Có thể chưa | Không. |
| Áp dụng `ApplicationContextInitializer` hoặc nạp bean definitions | Có thể đã | Không được giả định đã refresh. |
| Khởi tạo singleton, dependency injection, `@PostConstruct` | Đã | Container có thể ở trạng thái lỗi và sẽ được dọn dẹp. |
| Bind cổng web server trong refresh | Đã | Có thể chưa phục vụ HTTP thành công. |
| `ApplicationRunner` / `CommandLineRunner` ném lỗi | Đã, thường đã refresh | Vẫn là thất bại startup; không đồng nghĩa ready. |

Khi sự kiện được gửi và Boot xử lý thất bại, ứng dụng có thể đóng context lỗi để giải phóng tài nguyên. Do đó, **không giữ reference từ `ApplicationFailedEvent` để sử dụng lâu dài**, không chạy task trên bean đã lỗi và không cố gọi `refresh()` lại trong failure listener như một cách khôi phục tự động.

Nếu muốn thử lại, hãy có **chính sách retry ở tầng điều phối** (giới hạn số lần, backoff, cảnh báo, phân biệt lỗi cấu hình cố định và lỗi tạm thời). Chỉ retry khi nguyên nhân và việc cleanup trước đó đã được hiểu rõ.

## 8. ApplicationFailedEvent không thay thế exception handling toàn ứng dụng

Bảng phân biệt các cơ chế:

| Tình huống | Cơ chế phù hợp |
|---|---|
| Khởi động Boot thất bại trong `run(...)` | `ApplicationFailedEvent`; log, failure analysis, process exit status. |
| Lỗi request HTTP khi ứng dụng đang chạy | Exception handler của web framework, observability/logging. |
| Lỗi trong tác vụ `@Scheduled` sau ready | Error handler và monitoring của scheduler. |
| Listener message consumer ném lỗi khi đã chạy | Error handler/retry/DLQ của message framework. |
| Tắt context theo yêu cầu bình thường | `ContextClosedEvent` / lifecycle shutdown callback. |
| Muốn thông báo điều kiện khởi động không hợp lệ rõ nguyên nhân | `FailureAnalyzer` hoặc exception có thông điệp hữu ích. |

Ví dụ, log `APPLICATION FAILED TO START` mà Spring Boot có thể hiển thị nhờ `FailureAnalyzer` là thông tin chẩn đoán. Một `FailureAnalyzer` giúp biến exception đã biết thành phần “Description” và “Action” dễ hiểu; nó không có nghĩa ứng dụng đã có một context hoạt động. `ApplicationFailedEvent` thì cho phép listener nhận failure signal và exception để làm việc nhẹ như ghi metric hoặc audit.

Nếu cần custom failure reporting, tránh xử lý nặng trong `ApplicationFailedEvent`. Listener đang chạy trong một đường đi vốn đã thất bại; nếu nó ném exception tiếp, kết quả chẩn đoán có thể phức tạp hơn hoặc bị ghi log cảnh báo do lỗi listener.

## 9. Những bẫy thường gặp

**Bẫy 1 — Luôn gọi `event.getApplicationContext().getBean(...)`.**

Sai vì context có thể `null` hoặc chưa usable. Hãy lấy exception trước, kiểm tra null, và tránh trông cậy bean để báo lỗi bootstrap.

**Bẫy 2 — Chỉ đăng ký `@EventListener(ApplicationFailedEvent.class)` bên trong bean.**

Cách này không thể bảo đảm bắt lỗi trước lúc bean/context được tạo. Dùng `SpringApplication.addListeners(...)`, builder listener hoặc registration bootstrap có chủ đích.

**Bẫy 3 — Coi `context != null` là startup thành công.**

Không đúng: context có thể đang refresh dở hoặc đã rơi vào quy trình dọn dẹp. Không gọi bean nghiệp vụ và không coi nó là ready.

**Bẫy 4 — Coi mọi exception sau khi ứng dụng chạy đều phát ApplicationFailedEvent.**

Sự kiện này gắn với lỗi startup của `SpringApplication`. HTTP request, scheduled task và message consumer sau khi ứng dụng đã sẵn sàng có các cơ chế lỗi riêng.

**Bẫy 5 — Phản ứng bằng `System.exit(...)` bên trong listener.**

Điều này có thể cắt ngang failure analysis, cleanup context và flush log; ảnh hưởng toàn JVM, đặc biệt nguy hiểm nếu có nhiều Spring context. Hãy để Boot hoàn tất đường xử lý lỗi và để tầng điều phối quyết định khởi động lại.

**Bẫy 6 — Tưởng bắt exception trong `main` là đủ để Boot vẫn tiếp tục khởi động.**

Khi `run(...)` đã ném exception, không có một context hoạt động thành công được trả về. Nếu `main` bắt và nuốt lỗi, process có thể trả exit status 0 khiến hệ thống triển khai hiểu nhầm thành công. Không sử dụng mẫu catch của bài thực hành như chính sách production.

**Bẫy 7 — Log toàn bộ `getArgs()` lên hệ thống tập trung.**

Arguments có thể chứa secret, token, hostname nội bộ hoặc dữ liệu nhạy cảm. Redact dữ liệu và chỉ ghi metadata cần cho chẩn đoán.

**Bẫy 8 — Mặc định listener sẽ bắt được mọi lỗi dù lỗi trước `run()`.**

Không bảo đảm. Exception xảy ra trong code Java trước khi Boot chuẩn bị hệ thống listener nằm ngoài phạm vi `ApplicationFailedEvent`.

## 10. Checklist điều tra một lần startup failure

Khi nhận `ApplicationFailedEvent`, đặt câu hỏi theo thứ tự:

1. **Có bắt được event hay không?** Listener đã được đăng ký trước `run()` chưa? Lỗi có nằm trong quá trình Boot startup không?
2. **Context có `null` không?** Nếu có, ưu tiên điều tra config data, môi trường, listener/processor bootstrap và các bước trước context creation.
3. **Exception gốc là gì?** Đọc `getException()`, các `cause`, suppressed exceptions và stack trace; tránh chỉ chụp dòng “Application failed to start”.
4. **Nếu có context, đã tới pha nào?** Context được tạo không có nghĩa refresh hoàn tất. Tra cứu log về refresh, binding, bean creation và runner.
5. **Có lỗi thứ cấp trong listener không?** Failure listener nên không phụ thuộc vào bean; kiểm tra timeout và logging fallback.
6. **Vòng đời đã được dọn đúng chưa?** Không giữ reference đến context thất bại, không chạy task nền với bean chưa khởi tạo thành công.
7. **Process/CI/orchestrator có biết đó là lỗi không?** Exit status, restart policy, health probe và cảnh báo cần phản ánh kết quả startup thực tế.

### Tài liệu tham khảo

- Spring Boot 3.3 — `ApplicationFailedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
- Spring Boot 3.3 — `SpringApplicationRunListener.failed(...)`, tham số context có thể null: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot — Application Events and Listeners, Startup Failure: https://docs.spring.io/spring-boot/reference/features/spring-application.html

**Ghi nhớ:** `ApplicationFailedEvent` báo một lần startup Boot thất bại và luôn mang theo exception. **`getApplicationContext()` không bảo đảm khác `null`**, và context khác null cũng không chứng minh nó đã refresh thành công. Đăng ký failure listener **trước `SpringApplication.run(...)`**, xử lý lỗi độc lập với bean và để cơ chế thất bại/shutdown của Boot hoàn tất.
