# ApplicationStartingEvent trong Spring Boot Application Events

## 1. ApplicationStartingEvent là gì?

`ApplicationStartingEvent` là event vòng đời **rất sớm** do `SpringApplication` phát khi bắt đầu một lần chạy ứng dụng Spring Boot. Nó nằm trong package:

```java
org.springframework.boot.context.event.ApplicationStartingEvent
```

Sự kiện được phát **sau khi các `ApplicationListener` và initializer cần thiết đã được đăng ký**, nhưng **trước khi `Environment` và `ApplicationContext` được tạo hoặc chuẩn bị để sử dụng**. Vì vậy nó cho phép ghi nhận mốc bắt đầu bootstrap hoặc cài đặt một số hỗ trợ thật sớm, nhưng chưa phải nơi thao tác với bean/service, đọc `@ConfigurationProperties` đã bind, truy vấn repository hoặc kiểm tra HTTP server đã sẵn sàng.

Cần phân biệt ba tên dễ nhầm:

- **`ApplicationStartingEvent`**: Spring Boot vừa bắt đầu chu trình `SpringApplication.run(...)`. Context chưa sẵn sàng, environment chưa được chuẩn bị.
- **`ApplicationStartedEvent`**: context đã `refresh()` thành công và còn **chưa chạy** `ApplicationRunner`/`CommandLineRunner`.
- **`ContextStartedEvent`**: thuộc **Spring Framework**, phát bởi lời gọi `ConfigurableApplicationContext.start()`. Nó là một thao tác riêng trên `Lifecycle` beans, không phải “bản rút gọn” của hai event Boot trên.

Nếu viết listener cho `ApplicationStartingEvent` trong một class `@Component` hoặc bằng phương thức `@EventListener` của một bean thông thường, đa số trường hợp **listener đó sẽ không thấy sự kiện**: khi Boot phát event, bean còn chưa được tạo và chưa được đăng ký vào multicaster của context.

**Cách dùng cốt lõi:** đăng ký listener với chính `SpringApplication` trước lời gọi `run(...)`, hoặc khai báo listener startup ở nơi Boot có thể nạp từ classpath trước khi tạo context.

## 2. Event xuất hiện ở đâu trong trình tự khởi động?

Với Spring Boot 3.3, các mốc chính trong vòng đời `SpringApplication.run(...)` có thể hình dung như sau:

```text
main(String[] args)
    |
    | new SpringApplication(App.class)
    | register listeners / initializers
    v
SpringApplication.run(args)
    |
    +--> ApplicationStartingEvent            <-- Environment chưa sẵn sàng
    |
    +--> chuẩn bị ConfigurableEnvironment
    +--> ApplicationEnvironmentPreparedEvent
    |
    +--> tạo ApplicationContext
    +--> chạy ApplicationContextInitializer
    +--> ApplicationContextInitializedEvent
    |
    +--> nạp bean definitions
    +--> ApplicationPreparedEvent
    |
    +--> refresh ApplicationContext
    |       +--> ContextRefreshedEvent
    |       +--> WebServerInitializedEvent (nếu có web server)
    |
    +--> ApplicationStartedEvent
    +--> AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +--> ApplicationRunner / CommandLineRunner
    |
    +--> ApplicationReadyEvent
    +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    v
SpringApplication.run(...) trả về ConfigurableApplicationContext
```

Đây là trình tự khái quát khi startup thành công. Không phải ứng dụng nào cũng có web server; event liên quan web server chỉ phát khi tồn tại server phù hợp. `ApplicationFailedEvent` có thể được phát khi startup thất bại và không nên đặt vào một vị trí cố định trong nhánh thành công.

| Event | Có `Environment` dùng được? | Có `ApplicationContext` dùng được? | Ý nghĩa học tập |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | **Chưa** | **Chưa** | Điểm bắt đầu sớm nhất của một lượt `run` |
| `ApplicationEnvironmentPreparedEvent` | **Có**, đã chuẩn bị | Chưa | Quan sát/chỉnh environment trước khi tạo context |
| `ApplicationContextInitializedEvent` | Có | Có, vừa khởi tạo | Initializers đã chạy, definitions chưa nạp |
| `ApplicationPreparedEvent` | Có | Có, chưa refresh | Definitions đã nạp, chuẩn bị refresh |
| `ApplicationStartedEvent` | Có | Có, đã refresh | Trước startup runners |
| `ApplicationReadyEvent` | Có | Có | Sau runners, mốc ứng dụng được xem là ready |

Từ “started” ở đây chỉ **mốc trong vòng đời Boot**; nó không bảo đảm database, message broker hoặc mọi hệ thống ngoài đã healthy. Muốn biết ứng dụng sẵn sàng nhận traffic, hãy dựa trên readiness và kiểm tra sức khỏe phù hợp, không suy ra điều đó từ `ApplicationStartingEvent`.

## 3. Những dữ liệu thực sự có trong ApplicationStartingEvent

Trong Spring Boot 3.3, `ApplicationStartingEvent` kế thừa `SpringApplicationEvent`, và qua đó kế thừa `ApplicationEvent`. Những API hữu ích gồm:

| API | Giá trị/ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `getSpringApplication()` | Đối tượng `SpringApplication` đang bootstrap | Trạng thái bên trong còn có thể đổi khi startup tiến triển |
| `getArgs()` | `String[]` raw arguments được truyền vào `run(...)` | Chưa phải `ApplicationArguments` bean; có thể chứa dữ liệu nhạy cảm |
| `getBootstrapContext()` | `ConfigurableBootstrapContext` dành cho quá trình bootstrap | **Không phải** `ApplicationContext`; lifecycle khác |
| `getSource()` | Nguồn của event, thông thường là `SpringApplication` | Không phải bean hay context |
| `getTimestamp()` | Thời điểm event object được tạo | Không phải số liệu đo toàn bộ startup |

Ví dụ phương thức listener:

```java
import java.util.Arrays;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingObserver
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("BOOT STARTING");
        System.out.println(
                "ARG_COUNT=" + event.getArgs().length);
        System.out.println(
                "HAS_BOOTSTRAP_CONTEXT=" + (event.getBootstrapContext() != null));
    }
}
```

Đây là class listener Java hoàn chỉnh về cú pháp; để **Spring Boot gọi được**, cần đăng ký sớm bằng một trong các cách ở phần 4. Nó không tự được kích hoạt chỉ vì file Java tồn tại.

### Không nhầm hai “context”

- `ConfigurableBootstrapContext`: registry/bối cảnh hỗ trợ việc bootstrap sớm; có thể lưu những đối tượng phục vụ giai đoạn này theo hợp đồng bootstrap. Nó không quản lý toàn bộ bean như `ApplicationContext`.
- `ConfigurableApplicationContext`: Spring IoC container được tạo **sau** event starting; quản lý bean definitions, singleton, event listeners của context, lifecycle, dependency injection.

Do đó đoạn sau **không hợp lệ về mặt thời điểm**:

```java
// Sai về thiết kế: event không cung cấp ApplicationContext đã sẵn sàng.
public void onApplicationEvent(ApplicationStartingEvent event) {
    // Không có event.getApplicationContext() ở loại event này.
    // Không thể autowire repository/service của context vào listener sớm
    // rồi kỳ vọng chúng đã được khởi tạo ở mốc STARTING.
}
```

Nếu nhu cầu cần `Environment`, chuyển sang `ApplicationEnvironmentPreparedEvent`; nếu cần context đã refresh, chọn mốc startup muộn hơn.

## 4. Ba cách đăng ký listener đủ sớm

### 4.1. SpringApplication.addListeners(...) — phù hợp nhất với một entrypoint

```java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new StartingObserver());
application.run(args);
```

Đây là đoạn minh họa, giả định `DemoApplication` là class cấu hình Boot và `StartingObserver` như trên. Đăng ký **trước** khi `run(...)` là điều kiện then chốt.

Ưu điểm: rõ ràng tại entrypoint, dễ debug và test, không ảnh hưởng đến các ứng dụng khác chỉ vì dùng cùng dependency.

### 4.2. SpringApplicationBuilder.listeners(...) — phù hợp khi sử dụng builder

```java
new SpringApplicationBuilder(DemoApplication.class)
        .listeners(new StartingObserver())
        .run(args);
```

Cần import `org.springframework.boot.builder.SpringApplicationBuilder`. Cách này cũng đăng ký listener ở phía `SpringApplication` trước khi Boot tạo context.

### 4.3. META-INF/spring.factories — nạp sớm từ thư viện/module

Một starter hoặc thư viện muốn listener được nạp tự động có thể đặt file:

```text
src/main/resources/META-INF/spring.factories
```

Ví dụ nội dung:

```properties
org.springframework.context.ApplicationListener=\
demo.StartingObserver
```

Class listener cần có cách khởi tạo phù hợp để Boot tạo instance từ classpath; constructor không tham số như `StartingObserver` là phương án đơn giản. Nếu có nhiều listener, liệt kê đầy đủ tên class theo cú pháp của file factories.

**Không nhầm cơ chế này với đăng ký auto-configuration**: trong các đời Spring Boot mới, việc liệt kê auto-configuration chuyển qua `AutoConfiguration.imports`, nhưng khả năng khai báo **ApplicationListener** bằng `spring.factories` vẫn là một trường hợp được tài liệu Boot hướng dẫn. Hai loại metadata có mục đích khác nhau.

### Tại sao @Component / @Bean / @EventListener không phù hợp?

```java
@Component
class TooLateObserver {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // Không nhận event startup sớm bằng cách này trong luồng Boot bình thường.
    }
}
```

Spring chỉ quét/khởi tạo component và đăng ký phương thức `@EventListener` khi context đang được tạo/refresh, **sau** mốc starting. Tương tự, một `@Bean ApplicationListener<ApplicationStartingEvent>` được tạo từ context thông thường cũng quá muộn để nhận sự kiện đã phát.

Điều này không nói rằng `@EventListener` không dùng được cho **mọi** Spring Boot event: các event sau khi context đã refresh, như `ApplicationReadyEvent`, có thể được xử lý bằng bean listener bình thường.

## 5. Ví dụ Maven chạy được với Java 17 và Spring Boot 3.3

Ví dụ này minh họa rõ ba mốc:

1. Early listener được gắn vào `SpringApplication` trước `run(...)`.
2. `ApplicationRunner` chạy sau khi context đã refresh.
3. Một phương thức `@EventListener` trong bean nhận `ApplicationReadyEvent`.

Nó cố tình dùng `WebApplicationType.NONE` để không cần web server, database hay controller; các dòng in ra do chương trình có thứ tự rõ ràng. Phiên bản minh họa: **Java 17+ và Spring Boot 3.3.13**.

Cấu trúc:

```text
boot-starting-event/
├── pom.xml
└── src/main/java/demo/StartingEventDemo.java
```

File `pom.xml`:

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

    <groupId>demo</groupId>
    <artifactId>boot-starting-event</artifactId>
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
```

File `src/main/java/demo/StartingEventDemo.java`:

```java
package demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class StartingEventDemo {

    @Bean
    ApplicationRunner runner() {
        return args -> System.out.println("RUNNER");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY");
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartingEventDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event -> {
                    System.out.println("STARTING");
                    System.out.println(
                            "ARGS=" + Arrays.toString(event.getArgs()));
                    System.out.println(
                            "HAS_BOOTSTRAP=" + (event.getBootstrapContext() != null));
                    System.out.println(
                            "SAME_APP=" + (event.getSpringApplication() == application));
                });

        try (ConfigurableApplicationContext context =
                     application.run("--sample=ok")) {
            System.out.println("CONTEXT_ACTIVE=" + context.isActive());
        }
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

Các dòng **do chương trình tự in** theo thứ tự (không tính các thông báo hệ thống/logging phụ thuộc môi trường):

```text
STARTING
ARGS=[--sample=ok]
HAS_BOOTSTRAP=true
SAME_APP=true
RUNNER
READY
CONTEXT_ACTIVE=true
```

Giải thích:

1. `SpringApplication` được tạo và cấu hình **trước** khi gọi `run`; listener được thêm vào danh sách early listeners của chính application này.
2. Khi `application.run("--sample=ok")` bắt đầu, Boot phát `ApplicationStartingEvent`. `Environment` và context chưa có; listener đọc `getArgs()`, `getBootstrapContext()`, `getSpringApplication()` mà không cần bean.
3. `getArgs()` trả raw arguments, nên `Arrays.toString(...)` in `[--sample=ok]`. `SAME_APP=true` chứng minh event thuộc chính instance đang chạy.
4. Sau khi context được refresh, Boot chạy `ApplicationRunner` bean và in `RUNNER`.
5. Boot phát `ApplicationReadyEvent` sau khi các runner hoàn thành. Bean chứa `@EventListener` đã được đăng ký, nên in `READY`.
6. `run(...)` trả về context đang active. Ví dụ in `CONTEXT_ACTIVE=true`, rồi khối `try-with-resources` đóng context.

Không cần `@EnableAsync` trong ví dụ. Các listener chạy đồng bộ theo cơ chế mặc định, giúp quan sát thứ tự mốc. Trong ứng dụng thực tế, cấu hình logging và instrumentation có thể tạo thêm dòng log; hãy phân biệt chúng với dòng do đoạn mã trên in.

**Một điều cần nhớ:** `@EventListener(ApplicationReadyEvent)` nhận được event vì đó là mốc **muộn**, không chứng minh bean có thể nhận event `ApplicationStartingEvent` sớm.

## 6. So sánh các event “Starting”, “Started”, “Ready” và ContextStarted

Đây là nguồn nhầm lẫn lớn vì tên gần nhau nhưng thời điểm khác hẳn.

| Event | Nơi khai báo | Điều gì vừa xảy ra? | Có thể dùng bean/repository? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | `org.springframework.boot.context.event` | `SpringApplication.run` vừa bắt đầu, trước chuẩn bị environment | **Chưa** có context |
| `ApplicationEnvironmentPreparedEvent` | Spring Boot | Environment đã chuẩn bị; trước context | Chưa có bean |
| `ApplicationStartedEvent` | Spring Boot | Context đã refresh; trước runners | Context đã sẵn sàng về bean, nhưng app chưa hoàn tất runners |
| `ApplicationReadyEvent` | Spring Boot | Runners đã hoàn tất; ứng dụng được xem là ready | Có thể truy cập beans trong context |
| `ContextStartedEvent` | `org.springframework.context.event` | Có lời gọi `ConfigurableApplicationContext.start()` | Thuộc vòng đời container, độc lập startup event của Boot |

Nếu cần đọc cấu hình từ profile hoặc property sources sau khi Boot đã gom dữ liệu từ môi trường, **đừng** cố lấy ở `ApplicationStartingEvent`. Nếu cần khởi tạo dữ liệu thông qua service, ưu tiên `ApplicationRunner`/`CommandLineRunner` hoặc mốc phù hợp sau context refresh. Nếu cần đánh dấu hoàn tất startup và sẵn sàng nhận traffic, dựa vào `ApplicationReadyEvent` hoặc cơ chế availability/readiness.

### ApplicationStartingEvent không phải ContextStartedEvent

Hai dòng này không thay thế nhau:

```java
// Boot tự phát ApplicationStartingEvent trong SpringApplication.run(...).
SpringApplication.run(DemoApplication.class, args);

// Spring Framework phát ContextStartedEvent khi có lời gọi start tường minh.
configurableApplicationContext.start();
```

Đoạn mã chỉ minh họa hai đường gọi; `DemoApplication` và `configurableApplicationContext` phải được định nghĩa trong ứng dụng để biên dịch. Boot không cần gọi `ConfigurableApplicationContext.start()` tường minh để phát `ApplicationStartingEvent`.

## 7. Những tình huống hợp lý để dùng ApplicationStartingEvent

### 7.1. Đánh dấu mốc đầu của một lượt bootstrap

Listener có thể ghi một mốc đo sớm ở bộ nhớ trong tiến trình:

```java
public final class StartupMarker
        implements ApplicationListener<ApplicationStartingEvent> {

    private volatile long startNanos;

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        startNanos = System.nanoTime();
    }

    public long getStartNanos() {
        return startNanos;
    }
}
```

Đây là class helper; cần giữ **chính instance** listener nếu muốn đọc mốc sau này, hoặc thiết kế chỗ lưu/đường chuyển state phù hợp. `System.nanoTime()` chỉ dùng đo **thời gian trôi trong cùng JVM**, không dùng như timestamp lịch để trao đổi giữa tiến trình. Nó ghi thời điểm listener được gọi, không phải lúc JVM process bắt đầu hay thời điểm class loader tải lớp chính.

Nếu muốn đo startup có cấu trúc và quan sát các giai đoạn, xem xét `ApplicationStartup` / `BufferingApplicationStartup` hoặc công cụ tracing, thay vì tự ghép các timestamp từ nhiều hook mà chưa định nghĩa chính xác.

### 7.2. Chuẩn bị hỗ trợ bootstrap độc lập với Spring beans

Một số thư viện hạ tầng cần tham gia sớm để chuẩn bị bootstrap registry hoặc ghi nhận trạng thái. `ApplicationStartingEvent.getBootstrapContext()` cho phép tiếp cận `ConfigurableBootstrapContext` từ rất sớm. Tuy nhiên cần tuân thủ vòng đời bootstrap registry và tránh coi những đối tượng đăng ký sớm là beans đã khởi tạo.

Nếu mục tiêu duy nhất là **đăng ký đối tượng bootstrap**, API chuyên biệt như `BootstrapRegistryInitializer` thường thể hiện ý định tốt hơn; không cần lạm dụng listener cho mọi tùy biến.

### 7.3. Quan sát thông số đầu vào tối thiểu

Có thể dùng `event.getArgs()` để đếm tham số, phân loại chế độ khởi chạy theo một cờ kỹ thuật đã xác định hoặc gắn correlation ID khởi động. Tuy nhiên:

- Raw CLI args có thể chứa đường dẫn, token hoặc dữ liệu nhạy cảm; **không in nguyên văn arguments trong log production**.
- Đây chưa phải `Environment`: property sources, biến môi trường, config files và profiles chưa được Boot chuẩn bị đầy đủ.
- Nếu logic cần biết giá trị cuối cùng sau precedence/config binding, chờ `ApplicationEnvironmentPreparedEvent` hoặc một bean sau context refresh.

Ví dụ trong phần 5 cố tình dùng `--sample=ok` để an toàn và minh họa dữ liệu không nhạy cảm.

### 7.4. Listener dùng chung trong một thư viện startup

Với `META-INF/spring.factories`, một thư viện có thể tự đăng ký early listener cho các ứng dụng dùng nó. Đây là trường hợp hợp lý khi công việc thật sự cần mốc rất sớm, chẳng hạn thiết lập quan sát bootstrap. Nếu listener có side effect, phải mô tả rõ trong tài liệu thư viện và tránh thay đổi state toàn cục một cách bất ngờ.

## 8. Giới hạn quan trọng ở giai đoạn chưa có Environment và ApplicationContext

### 8.1. Dependency injection chưa khả dụng theo cách thông thường

`@Autowired`, `@Value`, `@ConfigurationProperties`, `@Transactional`, repository và các service bean đều dựa trên context, hoặc ít nhất là hạ tầng được khởi tạo ở các mốc muộn hơn.

Một early listener do bạn tạo thủ công:

```java
application.addListeners(new StartingObserver());
```

là một đối tượng Java được cung cấp trực tiếp cho `SpringApplication`. Nó không tự động biến thành một bean được inject dependencies tại thời điểm starting. Nếu nó dùng một trường `@Autowired` chưa được gán thì có thể gặp `null`.

**Giải pháp:** chỉ truyền dependency thật sự có thể tạo sớm bằng constructor, hoặc đổi sang mốc lifecycle khác. Tránh tự gọi `SpringApplication.run` một ứng dụng thứ hai trong listener chỉ để có context.

### 8.2. Hạ tầng logging còn đang được cấu hình

Spring Boot dùng các listener khởi động riêng để khởi tạo và cấu hình logging theo giai đoạn. Ở `ApplicationStartingEvent`, logging có thể đang được thiết lập, chưa áp dụng đầy đủ cấu hình đến từ environment.

Nếu cần thông điệp rất sớm, chỉ ghi lượng nhỏ dữ liệu; không phụ thuộc vào profile, level hay appender sẽ được đọc từ `application.yml` về sau. `System.out.println` chỉ phù hợp minh họa, không phải giải pháp logging hoàn chỉnh.

### 8.3. Listener phải chạy nhanh

Startup events mặc định được gửi trên luồng đang khởi chạy ứng dụng. Một listener thực hiện I/O lâu, truy vấn mạng hoặc chờ lock có thể làm **toàn bộ startup chậm hoặc treo**, trước khi context và Actuator sẵn sàng để chẩn đoán.

Nếu công việc có thể chạy sau khi ứng dụng sẵn sàng, hãy chuyển sang runner, ready listener hoặc background task được quản lý. Không tạo executor thủ công ở mốc starting nếu chưa có kế hoạch shutdown, quan sát lỗi và truyền context.

### 8.4. Exception ở listener có thể làm hỏng startup

Nếu listener sớm ném exception, exception có thể phá luồng khởi động và Boot có thể báo thất bại. Không nên dùng event này để chạy một công việc dễ lỗi nhưng không thiết yếu, vì ở thời điểm đó hệ thống vẫn chưa có những cơ chế recovery hoặc health endpoint thông thường.

Nếu cần chặn khởi động do **cấu hình không hợp lệ**, hãy chọn extension point có semantics phù hợp, ghi rõ lỗi và thử nghiệm cơ chế phát hiện thất bại. Không cần đưa tất cả validation vào `ApplicationStartingEvent` khi những thông tin cần kiểm tra chưa tồn tại.

## 9. SpringApplicationEvent và cách chọn lọc event

`ApplicationStartingEvent` là subtype của `SpringApplicationEvent`. Khi viết một listener bao quát nhiều startup events, có thể đăng ký `ApplicationListener<SpringApplicationEvent>` ngay từ đầu và phân nhánh theo runtime type.

Ví dụ minh họa:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootLifecycleObserver
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("starting");
        } else if (event instanceof ApplicationReadyEvent) {
            System.out.println("ready");
        }
    }
}
```

Đây là class listener đơn lẻ, nhưng nó cần được đăng ký sớm để nhận được tất cả mốc mong muốn. Nếu không cần nghe nhiều event, **ưu tiên listener được gõ kiểu cụ thể**:

```java
ApplicationListener<ApplicationStartingEvent>
```

Listener rộng phải kiểm tra subtype cho từng lần gọi. Không nên coi thứ tự callback từ nhiều ứng dụng con/cha hoặc nhiều lượt startup là một chuỗi toàn cục duy nhất nếu không có thiết kế định danh từng `SpringApplication`.

### Nguồn event là SpringApplication

`getSpringApplication()` cho phép phân biệt đối tượng đang chạy ở mức bootstrap. Một listener dùng chung có thể kiểm tra định danh instance nếu cần, nhưng tránh dựa vào state chưa ổn định của đối tượng `SpringApplication`. Javadoc nhấn mạnh rằng state nội bộ của application có thể còn thay đổi trong những giai đoạn tiếp theo.

Không nên dựa vào `ApplicationContext.getId()` ở bước này vì context chưa được tạo.

## 10. Bảo mật và độ tin cậy trong listener khởi động sớm

Các nguyên tắc thực hành quan trọng:

1. **Không log secret**: command-line arguments có thể chứa password, access token, URL nội bộ; nếu cần đo, hãy log số lượng hoặc tên cờ đã qua allowlist.
2. **Tránh side effect không idempotent**: một JVM có thể gọi `SpringApplication.run(...)` nhiều lần trong test hoặc chạy nhiều context; không suy ra listener chỉ chạy đúng một lần trong toàn JVM.
3. **Không gọi HTTP/database bắt buộc**: chưa có bean quản lý kết nối, circuit breaker hoặc transaction context đáng tin cậy.
4. **Không đọc Environment trước khi nó được chuẩn bị**: việc tự tạo `StandardEnvironment` riêng có thể cho giá trị khác với môi trường cuối cùng của Boot.
5. **Không làm đổi ý nghĩa failure**: exception ở mốc sớm có thể chặn startup nhưng không đảm bảo mọi thành phần hạ tầng đã được cleanup như một context hoàn chỉnh.
6. **Cẩn thận khi dùng global static state**: startup nhiều context có thể đè dấu mốc hoặc dữ liệu của nhau; ưu tiên state gắn với một `SpringApplication`/bootstrap.
7. **Giữ callback nhanh và xác định**: event này phù hợp với một mốc ghi nhận hoặc thay đổi rất nhỏ, không phải giai đoạn chạy migration nặng.
8. **Kiểm chứng theo đúng phiên bản Spring Boot**: constructor và bootstrap APIs có thể đổi qua các đời Boot; ví dụ dùng API 3.3 và Java 17.

## 11. Kiểm thử ApplicationStartingEvent

Vì listener xuất hiện trước context, test chỉ dùng `@SpringBootTest` rồi tìm bean `ApplicationListener<ApplicationStartingEvent>` sau startup là không đủ để chứng minh listener đã nhận event. Cần đăng ký listener trước khi chạy ứng dụng trong test, hoặc dùng listener từ `spring.factories` và một cách lưu kết quả có thể quan sát.

Ví dụ test chiến lược, không cần một web server:

```java
AtomicInteger startingCount = new AtomicInteger();

SpringApplication app = new SpringApplication(StartingEventDemo.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.setBannerMode(Banner.Mode.OFF);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event ->
        startingCount.incrementAndGet());

try (ConfigurableApplicationContext context = app.run()) {
    assertEquals(1, startingCount.get());
}
```

Đây là **đoạn minh họa trong một bài kiểm thử JUnit**, cần import `AtomicInteger`, `SpringApplication`, `WebApplicationType`, `Banner`, `ApplicationListener`, `ApplicationStartingEvent`, `ConfigurableApplicationContext`, `assertEquals` và có class cấu hình `StartingEventDemo`. Nó không phải chương trình độc lập của mục 5.

Các test case đáng có:

| Tình huống | Dữ liệu/thiết lập | Kỳ vọng |
| --- | --- | --- |
| Listener đăng ký trước run | `app.addListeners(listener)` trước `app.run(...)` | Nhận đúng một mốc STARTING cho một lần run bình thường |
| Không đăng ký sớm | Chỉ định nghĩa listener như một bean | Bean không bắt được event đã phát trước khi context được tạo |
| Truyền tham số | `app.run("--sample=ok")` | `getArgs()` chứa đúng raw string `--sample=ok` |
| Có bootstrap context | `event.getBootstrapContext()` | Không null ở phiên bản API đang dùng |
| Context chưa sẵn sàng | Callback ngay STARTING | Không thể lấy context qua API `ApplicationStartingEvent` |
| Mốc muộn hơn | Có runner + ready listener | RUNNER trước READY |
| Test startup nhiều lần | Hai lần tạo/chạy SpringApplication | Listener theo lượt chạy có thể được gọi ở mỗi lần run |
| Listener ném exception | Exception có chủ ý | Startup thất bại theo đường exception của Boot; quan sát kết quả thay vì chỉ log |
| Có listeners từ classpath | `spring.factories` | Class listener được phát hiện đủ sớm khi runtime bootstrap |

Không nên kiểm tra đúng toàn bộ output của Spring Boot log, vì logo/banner/log level có thể đổi theo dependency và môi trường. Với ví dụ ở mục 5, hãy kiểm tra **các dòng do code in ra** và thứ tự của chúng.

## 12. Những lỗi thường gặp

1. **Đăng ký listener bằng `@EventListener` trên `@Component`** rồi thắc mắc không nhận STARTING: quá sớm để context tạo bean.
2. **Nhầm với `ApplicationStartedEvent`**: STARTED đã refresh context, còn STARTING chưa có context hoặc prepared environment.
3. **Nhầm với `ContextStartedEvent`**: event Framework này gắn với `ConfigurableApplicationContext.start()` tường minh.
4. **Dùng `ApplicationStartingEvent` để báo “ready”**: event xảy ra ở đầu startup, trước runners, server và readiness.
5. **Đọc `application.yml` và profiles qua bean ở STARTING**: `Environment` chưa được chuẩn bị để dùng qua event.
6. **Autowire repository vào một early listener tạo thủ công**: instance chưa qua dependency injection thông thường.
7. **Log toàn bộ `getArgs()` ở production**: vô tình làm lộ secrets từ command line.
8. **Khởi động tác vụ dài trên luồng startup**: làm chậm hoặc treo quá trình tạo context.
9. **Coi `getBootstrapContext()` là `ApplicationContext`**: hai loại context có vòng đời và vai trò khác nhau.
10. **Dùng `spring.factories` để khai báo auto-configuration và listener như cùng một khóa**: cơ chế nạp auto-configuration và listener khác nhau.
11. **Cho rằng static run + một `@Bean` sớm sẽ hoạt động giống `addListeners`**: bean được tạo sau mốc STARTING.
12. **Nhầm timestamp event với toàn bộ startup duration**: cần hai mốc đo và xác định chính xác điểm bắt đầu/kết thúc.
13. **Cho rằng mỗi JVM chỉ có một lần run**: test, công cụ CLI hoặc context hierarchy có thể có nhiều lượt.
14. **Không test với bản Boot đang chạy thật**: thay đổi API/registration across versions có thể khiến giả định cũ không phù hợp.

## 13. Checklist thiết kế

Trước khi dùng `ApplicationStartingEvent`, hãy xác nhận:

- Có thực sự cần làm việc **trước cả Environment** không, hay có thể chờ mốc sau?
- Công việc có cần bean, repository, configuration binding, transaction hoặc web server không? Nếu có, nên đổi event.
- Listener được đăng ký trước `run(...)` bằng `addListeners`, builder hay `spring.factories` chưa?
- Có đang nhầm tên với `ApplicationStartedEvent`/`ContextStartedEvent` không?
- Có đang ghi log raw CLI args chứa thông tin nhạy cảm không?
- Thao tác ở listener có đủ nhanh và an toàn khi startup thất bại không?
- Nếu muốn đo thời gian, đã xác định “bắt đầu” và “sẵn sàng” là hai mốc nào chưa?
- Có phân biệt `BootstrapContext` với `ApplicationContext` không?
- Có kiểm thử listener nhận STARTING với một `SpringApplication` thực sự và xác minh thứ tự RUNNER/READY không?
- Có dùng các API của đúng phiên bản Boot đang triển khai không?

**Ghi nhớ:** `ApplicationStartingEvent` là tín hiệu mở đầu chu trình `SpringApplication.run(...)`, được phát trước khi Spring chuẩn bị environment và tạo context. Đăng ký listener sớm và giữ xử lý nhẹ, độc lập với IoC; chuyển những công việc cần context hoặc readiness sang các mốc phù hợp hơn.

## Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.3 — ApplicationStartingEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html)
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationStartedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
