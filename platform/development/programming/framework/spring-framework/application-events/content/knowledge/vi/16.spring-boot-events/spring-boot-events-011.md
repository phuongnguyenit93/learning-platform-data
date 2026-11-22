# SpringApplicationBuilder.listeners trong Spring Boot Application Events

## 1. Vấn đề mà listeners(...) giải quyết

Khi ứng dụng Spring Boot bắt đầu chạy, một số sự kiện được phát **trước khi `ApplicationContext` được tạo hoặc refresh**. Ví dụ, `ApplicationStartingEvent` được phát rất sớm và `ApplicationEnvironmentPreparedEvent` được phát khi `Environment` đã được chuẩn bị nhưng context chưa tồn tại. Nếu đăng ký listener chỉ dưới dạng bean `@Component`, `@Bean` hoặc phương thức `@EventListener`, các thành phần đó chưa được tạo/đăng ký kịp để nhận những sự kiện đầu tiên.

`SpringApplicationBuilder.listeners(ApplicationListener<?>... listeners)` giải quyết bài toán này bằng cách **gắn các đối tượng listener trực tiếp vào `SpringApplication` trước lời gọi `run(...)`**. Listener được Spring Boot dùng cho các sự kiện vòng đời ứng dụng và tiếp tục được đăng ký với `ApplicationContext` để có thể nhận sự kiện Spring thông thường khi context đã chạy.

Ví dụ ý tưởng:

~~~java
new SpringApplicationBuilder(AppConfig.class)
    .listeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
            System.out.println("The application is starting")
    )
    .run(args);
~~~

Đây là **đoạn minh họa**, cần các import Spring Boot liên quan. Với cách đăng ký trước `run(...)`, handler có thể nhận `ApplicationStartingEvent`; đăng ký listener bằng bean thông thường ở giai đoạn sau sẽ quá muộn.

Ba câu hỏi chính của bài học:

1. `listeners(...)` nhận đối tượng nào và tác động lên phần nào của quá trình khởi động?
2. Những sự kiện nào xảy ra trước và sau khi `ApplicationContext` sẵn sàng?
3. Làm sao viết, kiểm tra và vận hành listener khởi động sớm mà không tạo phụ thuộc vào bean chưa tồn tại?

## 2. API chính xác và các thành phần liên quan

Phương thức ở package `org.springframework.boot.builder`, dùng chữ ký:

~~~java
public SpringApplicationBuilder listeners(
        ApplicationListener<?>... listeners)
~~~

- **Tham số:** một hoặc nhiều đối tượng triển khai `org.springframework.context.ApplicationListener<?>`. Có thể truyền lớp listener tự viết hoặc lambda có kiểu `ApplicationListener<EventType>` cụ thể.
- **Giá trị trả về:** chính builder để tiếp tục cấu hình theo kiểu fluent API.
- **Tác dụng:** thêm listener vào ứng dụng đang được builder cấu hình. Javadoc chỉ rõ chúng nghe cả **SpringApplication events** và **regular Spring events** khi context chạy.
- **Thời điểm dùng:** trước `run(args)` để nhận được các sự kiện sớm nhất. Việc gọi sau khi một ứng dụng đã khởi động không thể “phát lại” những sự kiện đã xảy ra.
- **Đặc điểm bổ sung từ Javadoc Spring Boot 3.5:** nếu một listener đồng thời triển khai `ApplicationContextInitializer`, builder cũng đăng ký nó vào danh sách initializer. Hai callback có vai trò khác nhau; cần tránh khởi tạo trùng nếu một lớp làm cả hai nhiệm vụ.

Mối quan hệ:

~~~text
main(String[] args)
    |
    v
new SpringApplicationBuilder(AppConfig.class)
    | .web(WebApplicationType.NONE)
    | .properties(...)
    | .listeners(earlyListener, readyListener)
    | .run(args)
    v
SpringApplication
    |
    +--> phát sự kiện giai đoạn rất sớm
    |       +--> earlyListener nhận được
    |
    +--> tạo và refresh ApplicationContext
    |       +--> đăng ký listener với context
    |
    +--> phát sự kiện sau refresh / sau runners
            +--> readyListener nhận được
~~~

`SpringApplicationBuilder` là công cụ xây dựng/cấu hình `SpringApplication`. Bản thân `listeners(...)` **không tạo một event mới**, không trực tiếp gọi listener và không phải API phát sự kiện nghiệp vụ. Event được phát khi Spring Boot triển khai tiến trình khởi động hoặc khi context xử lý sự kiện.

## 3. Các mốc sự kiện Boot và dữ liệu có thể sử dụng

Những mốc chính trong Spring Boot 3.x có thể nhìn như sau:

| Sự kiện | Thời điểm tương đối | Có gì khả dụng và nên làm gì? |
|---|---|---|
| `ApplicationStartingEvent` | Khi `run` bắt đầu, trước phần lớn xử lý khởi tạo | Có thể ghi tín hiệu rất sớm; **chưa có Environment hay ApplicationContext** để đọc như bean |
| `ApplicationEnvironmentPreparedEvent` | `Environment` đã được tạo/chuẩn bị, trước context | Đọc hoặc điều chỉnh cấu hình môi trường phù hợp; chưa yêu cầu bean từ context |
| `ApplicationContextInitializedEvent` | Context đã được tạo và initializers đã được gọi, nhưng chưa nạp bean definitions | Thực hiện quan sát ở thời điểm context sơ khai; chưa thể giả định bean đã được khởi tạo |
| `ApplicationPreparedEvent` | Bean definitions đã được nạp, ngay trước refresh | Có context, nhưng nhiều singleton bean vẫn chưa khởi tạo |
| `ContextRefreshedEvent` | `ApplicationContext` refresh xong | Các thành phần của context sẵn sàng theo contract refresh; không đồng nghĩa mọi runner đã hoàn tất |
| `ApplicationStartedEvent` | Sau khi context refresh, **trước** `ApplicationRunner` và `CommandLineRunner` | Quan sát mốc context đã khởi động, chuẩn bị chạy runners |
| `AvailabilityChangeEvent` với `LivenessState.CORRECT` | Sau mốc started | Boot báo trạng thái liveness |
| `ApplicationReadyEvent` | Sau các application/command-line runners | Mốc Boot cho biết ứng dụng đã sẵn sàng phục vụ theo quá trình startup |
| `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` | Sau mốc ready | Trạng thái readiness được công bố |
| `ApplicationFailedEvent` | Nếu startup thất bại | Ghi nhận nguyên nhân lỗi; context có thể chưa tồn tại hoặc chưa usable |

Đây là **thứ tự khái niệm** của các sự kiện Boot chính; tùy ứng dụng còn có sự kiện web server, bean lifecycle, ứng dụng phân cấp và các event nghiệp vụ xen kẽ. `ContextRefreshedEvent` là sự kiện của Spring Framework, còn các `Application...Event` liệt kê là sự kiện vòng đời từ Spring Boot.

Vì những mốc đầu xảy ra trước khi context tồn tại, không được gọi:

~~~java
// Sai về tiền đề ở ApplicationStartingEvent:
ApplicationContext ctx = ...;      // Chưa có context để tiêm.
MyService service = ctx.getBean(MyService.class);
service.execute();
~~~

Mã trên là **phản ví dụ**. Nếu cần làm việc với bean đã khởi tạo hoặc phụ thuộc mạng/DB, hãy chọn mốc muộn hơn, ví dụ `ApplicationReadyEvent` hoặc dùng `ApplicationRunner` / `CommandLineRunner`.

### Phân biệt Started và Starting

Tên rất giống nhau nhưng thời điểm khác biệt lớn:

- `ApplicationStartingEvent`: phát sớm nhất; context chưa được tạo.
- `ApplicationStartedEvent`: sau refresh; context đã tồn tại, nhưng Boot chưa chạy `ApplicationRunner` / `CommandLineRunner`.
- `ApplicationReadyEvent`: sau runners; phù hợp quan sát mốc ứng dụng sẵn sàng.

Lỗi học API thường gặp là gắn listener vào `ApplicationStartedEvent` khi mục tiêu là ghi log ngay trước khi `Environment` hình thành.

## 4. Ví dụ Java 17 chạy độc lập với Spring Boot 3.5

Ví dụ sau dùng **Java 17+**, Spring Boot **3.5.16**, Maven, chạy ở chế độ **không có web server** để tập trung vào sự kiện. Chương trình đăng ký ba listener bằng `SpringApplicationBuilder.listeners(...)`, đọc một thuộc tính cấu hình khi môi trường đã chuẩn bị, rồi quan sát context active sau khi ready.

Cấu trúc dự án:

~~~text
builder-listeners-demo/
├── pom.xml
└── src/main/java/demo/BuilderListenersDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>builder-listeners-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/demo/BuilderListenersDemo.java`:

~~~java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

public class BuilderListenersDemo {

    public static void main(String[] args) {

        ApplicationListener<ApplicationStartingEvent> starting = event ->
            System.out.println("01 STARTING: context not created");

        ApplicationListener<ApplicationEnvironmentPreparedEvent> environment = event ->
            System.out.println("02 ENV: demo.mode=" +
                event.getEnvironment().getProperty("demo.mode"));

        ApplicationListener<ApplicationReadyEvent> ready = event ->
            System.out.println("03 READY: active=" +
                event.getApplicationContext().isActive());

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(Config.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .logStartupInfo(false)
                    .properties("demo.mode=demo")
                    .listeners(starting, environment, ready)
                    .run(args)) {

            System.out.println("04 MAIN: active=" + context.isActive());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        // Cấu hình tối thiểu; không cần controller, service hoặc web server.
    }
}
~~~

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.BuilderListenersDemo
~~~

Với lệnh trên **không thêm tham số cấu hình khác**, các dòng do code ứng dụng in, theo đúng thứ tự:

~~~text
01 STARTING: context not created
02 ENV: demo.mode=demo
03 READY: active=true
04 MAIN: active=true
~~~

Maven và Spring Boot có thể xuất thêm thông báo kỹ thuật tùy cấu hình logging, nhưng bốn dòng của chương trình vẫn thể hiện các mốc quan sát. Trong một phiên chạy duy nhất với ba loại event khác nhau, Boot phát `ApplicationStartingEvent` trước `ApplicationEnvironmentPreparedEvent`, còn `ApplicationReadyEvent` đến sau khi context refresh và các runners hoàn tất. Dòng thứ tư chạy sau khi `run(args)` trả về.

**Giải thích từng dòng:**

1. `starting` nhận event ngay lúc startup bắt đầu. Handler **không cố đọc `ApplicationContext`** vì context chưa tồn tại.
2. `environment` nhận `ApplicationEnvironmentPreparedEvent`; event cho phép đọc `getEnvironment()`. Thuộc tính `demo.mode` được builder đặt qua `properties(...)`, nên có giá trị `demo` khi không bị property source có độ ưu tiên cao hơn ghi đè.
3. `ready` nhận `ApplicationReadyEvent` và quan sát `ConfigurableApplicationContext` đã hoạt động.
4. `try-with-resources` đóng context khi khối `main` kết thúc. Vì chương trình không có web server, việc thoát main là điều được mong đợi.

Ví dụ dùng `@Configuration` làm nguồn cấu hình và chọn `WebApplicationType.NONE`, nên không cần trình điều khiển HTTP hoặc cơ sở dữ liệu. Không dùng `Thread.sleep(...)` để minh họa startup vì thứ tự event từ Spring Boot đủ để quan sát các mốc quan trọng.

### Thay lambda bằng lớp listener

Ở ứng dụng lớn, có thể viết listener thành class riêng:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

Đây là **lớp minh họa**. Nếu nó nằm trong package `demo` và import đầy đủ, đăng ký trong main:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new StartingTraceListener())
    .run(args);
~~~

Sử dụng Java object cụ thể thích hợp khi listener có nhiều nhánh logic, cần kiểm thử riêng hoặc cần khởi tạo với thông số đơn giản. **Không đặt phụ thuộc bắt buộc vào `@Autowired` trong constructor của listener khởi động sớm**: những bean đó chưa tồn tại tại thời điểm đăng ký.

## 5. Tại sao @Bean và @EventListener không thay thế được listeners(...) ở giai đoạn sớm?

Hai cách viết sau khác nhau về **vòng đời đăng ký**, không chỉ khác cú pháp.

**Đăng ký bằng builder trước run:**

~~~java
new SpringApplicationBuilder(AppConfig.class)
    .listeners(new StartingTraceListener())
    .run(args);
~~~

**Đăng ký bean qua context:**

~~~java
@Configuration
class AppConfig {
    @Bean
    ApplicationListener<ApplicationReadyEvent> readyBeanListener() {
        return event -> System.out.println("ready via bean");
    }
}
~~~

Bean `readyBeanListener` có thể nhận các event phát sau khi context đã được tạo và listener bean đã được đăng ký. Nhưng nó **không thể quay ngược thời gian** để nhận `ApplicationStartingEvent` vốn đã phát từ trước khi context được tạo.

Với phương thức `@EventListener`:

~~~java
@Component
class ReadyObserver {

    @EventListener
    void afterReady(ApplicationReadyEvent event) {
        System.out.println("context ready");
    }
}
~~~

Đây cũng là code tích hợp yêu cầu bean `ReadyObserver` được scan/đăng ký. Phương thức được Spring xử lý trong quá trình chuẩn bị bean và event listener adapter, vì thế nó phù hợp với sự kiện **sau** giai đoạn này.

Trong phần code minh họa ở trên, cần thêm các import `org.springframework.context.annotation.Bean`, `org.springframework.stereotype.Component` và `org.springframework.context.event.EventListener` theo cách đăng ký đã chọn. Các đoạn này độc lập với ví dụ `BuilderListenersDemo.java`, không phải mã cần dán liền nhau vào cùng file mà không bổ sung cấu hình.

| Cách đăng ký | Có thể bắt event trước khi context tồn tại? | Phụ thuộc bean của context? | Mục đích |
|---|---|---|---|
| `SpringApplicationBuilder.listeners(...)` | Có | Không nên, nhất là listener sớm | Hook vào vòng đời Boot từ trước `run` |
| `SpringApplication.addListeners(...)` | Có, nếu gọi trước `run` | Không nên | API tương đương khi không dùng builder |
| `META-INF/spring.factories` | Có, khi Boot tự nạp lúc startup | Tạo bởi hạ tầng Boot, cần thiết kế độc lập context | Đăng ký listener tự động khi thư viện được đưa vào classpath |
| `@Bean ApplicationListener<?>` | Không với event phát trước khi bean được tạo | Có | Đăng ký listener thông qua context |
| `@EventListener` trên bean | Không với event phát trước khi listener adapter hoạt động | Có | Xử lý event thông thường, cách viết gọn |

Cách chọn phụ thuộc **thời điểm bạn cần nhận event**. Dùng builder khi muốn cấu hình listener riêng cho lần chạy cụ thể, có thể truyền trực tiếp vào `main`; dùng bean khi listener cần service/DAO và chỉ xử lý khi context đã sẵn sàng.

## 6. ApplicationEnvironmentPreparedEvent và tùy chỉnh cấu hình sớm

`ApplicationEnvironmentPreparedEvent` cho phép quan sát hoặc tùy chỉnh một `ConfigurableEnvironment` trước khi context được dựng hoàn chỉnh. Ví dụ listener thêm một `PropertySource` có độ ưu tiên thấp khi chưa có key:

~~~java
import java.util.Map;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.MapPropertySource;

public final class BootstrapDefaults
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        var sources = event.getEnvironment().getPropertySources();
        sources.addLast(new MapPropertySource(
            "custom-bootstrap-defaults",
            Map.of("demo.audit.enabled", "true")
        ));
    }
}
~~~

Đây là **lớp tích hợp**. Đăng ký:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new BootstrapDefaults())
    .run(args);
~~~

`addLast` thêm nguồn thuộc tính vào cuối thứ tự ưu tiên hiện tại, nên những cấu hình có ưu tiên cao hơn có thể ghi đè giá trị `demo.audit.enabled`. Dùng cách này khi có lý do rõ ràng phải tác động vào `Environment` ở giai đoạn sớm; với giá trị mặc định đơn giản, `builder.properties("key=value")` thường dễ hiểu và ít gây tác dụng phụ hơn.

**Lưu ý:** thứ tự các `EnvironmentPostProcessor`, property source do Boot nạp và listener được điều phối bởi hạ tầng startup. Nếu phải kiểm soát cấu hình rất sớm cho mọi ứng dụng (ví dụ cấu hình logging hoặc nguồn cấu hình đặc biệt), hãy cân nhắc extension point chuyên dụng thay vì dựa vào việc listener chạy ở một thứ tự chưa được bảo đảm. Không log mật khẩu, token hoặc toàn bộ `Environment` ra stdout.

## 7. Bắt lỗi khởi động bằng ApplicationFailedEvent

Để quan sát startup thất bại, có thể đăng ký:

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class FailedStartupListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("Startup failed: " + failure.getClass().getName());

        // Có thể kiểm tra exception; tránh dereference context khi null.
    }
}
~~~

Đoạn này độc lập với ví dụ chạy thành công. `ApplicationFailedEvent` chỉ xuất hiện khi startup thất bại, vì thế không thể đưa một dòng output cố định từ nó vào ví dụ đường thành công.

Đăng ký trước `run`:

~~~java
new SpringApplicationBuilder(Config.class)
    .listeners(new FailedStartupListener())
    .run(args);
~~~

Những điểm cần chú ý:

- Startup có thể lỗi **trước khi context được tạo**, vì vậy không được giả định `event.getApplicationContext()` luôn khác `null`.
- Listener thất bại cũng có thể ném lỗi. Hãy giữ logger/handler ở mức tối thiểu, tránh logic phức tạp hoặc truy cập bean chưa sẵn sàng.
- Chỉ log thông tin kỹ thuật cần thiết, tránh tiết lộ dữ liệu nhạy cảm từ exception chain hoặc cấu hình.
- Sự kiện này không thay thế cơ chế giám sát tiến trình, exit code hoặc health check của môi trường chạy.

Khi cần xử lý tài nguyên sau khi ứng dụng đã chạy rồi đóng, đó là bài toán `ContextClosedEvent` và lifecycle/shutdown, khác với `ApplicationFailedEvent` khi **khởi động thất bại**.

## 8. So sánh listeners(...) với các API gần nhau

### SpringApplication.addListeners(...)

Nếu không dùng builder, cách tương đương để đăng ký trước startup là:

~~~java
SpringApplication app = new SpringApplication(Config.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.addListeners(new StartingTraceListener());
app.run(args);
~~~

Hai API cùng cung cấp khả năng đưa `ApplicationListener` vào SpringApplication trước khi chạy. `SpringApplicationBuilder` tiện khi cần fluent configuration, profiles, parent/child contexts hoặc muốn ghép nhiều tùy chọn trong một biểu thức.

### SpringApplicationBuilder.initializers(...)

`ApplicationContextInitializer<ConfigurableApplicationContext>` là callback **tùy biến context trước khi bean definitions được nạp**. Nó không phải event listener:

~~~java
ApplicationContextInitializer<ConfigurableApplicationContext> init =
    context -> context.getEnvironment()
        .setDefaultProfiles("demo");

new SpringApplicationBuilder(Config.class)
    .initializers(init)
    .run(args);
~~~

Đây là code minh họa với import `org.springframework.context.ApplicationContextInitializer` và `org.springframework.context.ConfigurableApplicationContext`. Dùng initializer khi muốn trực tiếp tùy chỉnh context ở mốc đã có context. Dùng listener khi cần quan sát một hoặc nhiều sự kiện cụ thể, đặc biệt event trước khi context tồn tại.

Điểm tinh tế: Javadoc của `SpringApplicationBuilder.listeners(...)` nêu rằng một đối tượng `ApplicationListener` đồng thời là `ApplicationContextInitializer` sẽ được thêm vào danh sách initializers. Khi xây extension kết hợp hai vai trò, không coi chúng là một callback; nếu thao tác có side effect, hãy đảm bảo logic idempotent và rõ thời điểm.

### META-INF/spring.factories

Một thư viện có thể muốn listener tự được phát hiện trong mọi ứng dụng sử dụng thư viện, dù ứng dụng đó gọi `SpringApplication.run` hay `SpringApplicationBuilder`. Có thể đặt file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

với nội dung:

~~~properties
org.springframework.context.ApplicationListener=demo.StartingTraceListener
~~~

Listener được đăng ký theo cơ chế factory loading của Spring Boot. Cần class ở đúng package, có thể được tạo theo cơ chế factory loader (thường dùng constructor không đối số), và JAR chứa resource trên classpath. Đăng ký này phù hợp cho thư viện/bootstrap integration; với logic riêng trong một `main`, `listeners(...)` trực tiếp rõ ràng hơn.

Chú ý file `spring.factories` để đăng ký `ApplicationListener` **khác** file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` dùng cho auto-configuration. Không thay một cơ chế bằng cơ chế còn lại một cách máy móc.

## 9. ApplicationContext phân cấp: vì sao listener có thể nhận event nhiều lần?

`SpringApplicationBuilder` còn hỗ trợ `parent(...)`, `child(...)` và `sibling(...)` để tạo các `ApplicationContext` trong một cây. Trong Spring Framework, event từ **child context** có thể được chuyển tiếp lên **parent context**. Vì vậy, khi đặt listener ở parent và có event từ child, listener của parent có thể nhận thêm những event cùng loại phát ở child.

Ví dụ cấu trúc (mã minh họa, cần hai lớp cấu hình và các import thích hợp):

~~~java
new SpringApplicationBuilder(ParentConfig.class)
    .web(WebApplicationType.NONE)
    .child(ChildConfig.class)
    .web(WebApplicationType.NONE)
    .run(args);
~~~

Trình tự context và cách forward event cụ thể tùy loại event, cách khởi động từng `SpringApplication` và cấu hình listener; **không khẳng định mọi event đều phát chính xác một lần trong toàn bộ cây**.

Nếu listener cần xử lý **chỉ event từ context của chính nó**, với event có `getApplicationContext()`, so sánh instance context thay vì chỉ so sánh loại:

~~~java
public void onApplicationEvent(ApplicationReadyEvent event) {
    if (event.getApplicationContext() == myContext) {
        // Xử lý sự kiện của context mong muốn.
    }
}
~~~

Đây là **đoạn điều kiện minh họa**; `myContext` phải được khởi tạo đúng, ví dụ context mà listener được liên kết tới, và việc xác định nó trong một listener khởi động sớm phải tính đến vòng đời context. Với `ApplicationStartingEvent`, chưa có context để dùng cách kiểm tra này: có thể cần nhận dạng `SpringApplication` nguồn hoặc chính sách đăng ký listener riêng theo ứng dụng.

Không đưa các tác vụ không idempotent như gửi email, ghi audit hoặc tạo job vào listener có khả năng bị gọi từ nhiều cấp context mà không có cơ chế phân biệt nguồn và chống trùng.

## 10. Thứ tự listener, @Order và hành vi lỗi

### Thứ tự handler

Nhiều listener cùng đăng ký cho một loại event có thể được sắp thứ tự theo `Ordered` hoặc `@Order`. Ví dụ:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;
import org.springframework.boot.context.event.ApplicationReadyEvent;

public final class PriorityReadyListener
        implements ApplicationListener<ApplicationReadyEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("high priority ready listener");
    }
}
~~~

Đây là một lớp minh họa có thể truyền qua `listeners(new PriorityReadyListener())`. Không nên dựa vào thứ tự mặc định của hai listener có cùng mức ưu tiên để thể hiện quan hệ nghiệp vụ bắt buộc. Nếu các bước cần phụ thuộc nhau, đặt chúng trong một workflow rõ thứ tự thay vì tách thành listener độc lập.

### Exception trong listener

Các event listener mặc định thường được gọi đồng bộ trong thread phát sự kiện. Listener chậm có thể làm startup chậm; listener ném exception ở giai đoạn sớm có thể làm startup thất bại hoặc thay đổi đường xử lý lỗi. Tùy giai đoạn và broadcaster, cách exception được thu gom hoặc truyền đi có thể khác nhau.

Không dùng listener khởi động sớm để thực hiện HTTP call dài, truy vấn DB, chờ queue hoặc chạy background task không có kiểm soát. Khi cần công việc sau khi ứng dụng sẵn sàng, có thể dùng `ApplicationRunner` hoặc `CommandLineRunner`. Khi cần công việc định kỳ, cân nhắc scheduler hoặc cơ chế điều phối riêng.

Đặt `@Async` trên phương thức của một object được truyền trực tiếp vào `listeners(...)` không bảo đảm có Spring proxy/async infrastructure tại các sự kiện rất sớm. Phải xem listener đó do ai tạo, có đi qua proxy không và `@EnableAsync` đã hoạt động chưa. Với listener sớm, giữ xử lý nhẹ và đồng bộ để dễ kiểm soát.

### Logging

Đối với `ApplicationStartingEvent`, hệ thống logging có thể chưa hoàn toàn được chuẩn bị. Các thành phần nội bộ Boot cũng cần xử lý những event này để cấu hình logging và environment. Vì vậy nếu mục tiêu chính là telemetry hoặc tracing production, hãy dùng extension point/observability integration phù hợp và kiểm tra thứ tự đăng ký; ví dụ `System.out.println` chỉ minh họa thời điểm event.

## 11. Kiểm tra bằng integration test thay vì giả định thứ tự

Một cách xác nhận thực tế rằng listener đã được đăng ký trước `run(...)` là tạo context trong test, ghi event vào collection thread-safe và assert **loại sự kiện** đã xuất hiện:

~~~java
List<String> observed = new CopyOnWriteArrayList<>();

ApplicationListener<ApplicationStartingEvent> starting =
    event -> observed.add("starting");

ApplicationListener<ApplicationReadyEvent> ready =
    event -> observed.add("ready");

try (ConfigurableApplicationContext context =
        new SpringApplicationBuilder(Config.class)
            .web(WebApplicationType.NONE)
            .bannerMode(Banner.Mode.OFF)
            .listeners(starting, ready)
            .run()) {

    if (!observed.equals(List.of("starting", "ready"))) {
        throw new AssertionError("Unexpected lifecycle: " + observed);
    }
}
~~~

Đoạn trên **minh họa cho test**; cần import `java.util.List`, `java.util.concurrent.CopyOnWriteArrayList` và các loại Spring như ở ví dụ main. Có thể đặt bên trong một test method hoặc chương trình mẫu đã cấu hình class `Config`. Vì chỉ ghi hai event được lọc kiểu cụ thể, kết quả mong đợi `[starting, ready]` không phụ thuộc vào các event khác phát ở giữa.

Kiểm thử thêm các trường hợp có ý nghĩa:

1. **Listener sớm:** đăng ký bằng builder phải quan sát `ApplicationStartingEvent`.
2. **Cấu hình môi trường:** listener môi trường chỉ đọc thuộc tính sau khi `Environment` đã chuẩn bị.
3. **Listener muộn:** handler `ApplicationReadyEvent` truy cập context active và các runner đã hoàn tất.
4. **Startup failure:** cố ý làm một bean hoặc runner ném exception, xác nhận listener `ApplicationFailedEvent` thấy lỗi mà không đòi context luôn khác null.
5. **Context phân cấp:** nếu ứng dụng dùng `child(...)`, xác minh các event từ child/parent được lọc phù hợp, tránh side effect trùng.
6. **Thời gian xử lý:** đặt giới hạn cho công việc trong listener startup để không làm tăng thời gian khởi động ngoài dự kiến.

Không nên cố kiểm thử bằng cách lấy một context đã chạy rồi mới gọi `context.addApplicationListener(...)` và kỳ vọng quan sát được `ApplicationStartingEvent`. Event đã phát không được replay bởi cơ chế này.

## 12. Những sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đăng ký `@Bean ApplicationListener<ApplicationStartingEvent>` | Bean chưa tồn tại khi early event đã phát | Dùng `SpringApplicationBuilder.listeners(...)` trước `run` |
| Nhầm `ApplicationStartedEvent` với `ApplicationStartingEvent` | Handler chạy sau refresh thay vì lúc startup bắt đầu | Chọn đúng event type và kiểm chứng mốc |
| Inject service/DAO bằng `@Autowired` vào early listener | Context/bean chưa sẵn sàng, dễ lỗi thiết kế | Chỉ dùng dữ liệu sẵn có tại event; dời logic sang mốc muộn |
| Coi `listeners(...)` là publisher của event | Code không phát event như mong đợi | Dùng `ApplicationEventPublisher.publishEvent(...)` để phát nghiệp vụ |
| Đọc bean trong `ApplicationEnvironmentPreparedEvent` | Chưa tạo context | Dùng `event.getEnvironment()`; bean đợi sau refresh |
| Làm I/O chậm trong early listener | Startup tăng latency hoặc thất bại | Giữ listener nhẹ; chuyển công việc sang runner/worker |
| Thêm listener sau `run(...)` | Bỏ lỡ early events | Đăng ký trước khi gọi run |
| Đăng ký cùng listener ở builder và bean | Có thể tạo side effect trùng hoặc khó theo dõi nguồn | Chọn một đường đăng ký hoặc thiết kế idempotent |
| Dựa vào listener order mặc định | Thứ tự không phải hợp đồng nghiệp vụ | Sử dụng `Ordered` khi cần, hoặc workflow tuần tự |
| Không lọc event trong context hierarchy | Xử lý trùng khi child event lan lên parent | So sánh context/event source và chống trùng |
| Giả định event lỗi luôn có context | `NullPointerException` trong handler lỗi | Kiểm tra null và log exception an toàn |
| Gắn `@Async` cho object chưa có Spring proxy | Handler vẫn chạy đồng bộ | Hiểu lifecycle/proxy; dùng async sau khi infrastructure sẵn sàng |

## 13. Khi nào nên chọn SpringApplicationBuilder.listeners?

Chọn `listeners(...)` khi:

- Muốn lắng nghe `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent`, vốn xảy ra trước khi bean của context sẵn sàng.
- Cần khai báo listener **cụ thể cho một lần khởi động** trong `main` hoặc trong một launch wrapper có fluent configuration.
- Cần kết hợp thiết lập profiles, properties, application type và listener trong một chuỗi builder rõ ràng.
- Muốn quan sát mốc readiness/startup để log, đo thời gian hoặc thực hiện cấu hình nhỏ không phụ thuộc vào bean.

Không cần dùng builder riêng chỉ vì một listener thông thường ở ứng dụng đã chạy. Với event nghiệp vụ và listener phụ thuộc Spring bean, `@EventListener` hoặc `ApplicationListener` bean thường đơn giản hơn. Với hành động một lần sau startup có phụ thuộc service, `ApplicationRunner` / `CommandLineRunner` có thể thể hiện luồng rõ ràng hơn. Với thư viện cần tự động nạp listener ở mọi ứng dụng, cân nhắc `META-INF/spring.factories`.

### Tài liệu chính thức tham khảo

- [Spring Boot 3.5 Javadoc — SpringApplicationBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html) — chữ ký và contract `listeners(...)`.
- [Spring Boot Reference — SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html) — các loại sự kiện, thứ tự và đăng ký listener sớm.
- [Spring Boot 3.5 Javadoc — SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html) — `addListeners(...)` và quản lý listener.
- [Spring Boot How-to — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html) — tùy chỉnh lúc bootstrap và `spring.factories`.

## 14. Tổng kết

`SpringApplicationBuilder.listeners(...)` thêm `ApplicationListener` **trước khi `SpringApplication.run(...)` bắt đầu**, nhờ đó listener có thể quan sát các sự kiện khởi động rất sớm mà bean `@Component`, `@Bean` hay phương thức `@EventListener` chưa kịp nhận. Listener được đăng ký cho SpringApplication và tiếp tục nhận các event của context khi context hoạt động. Hãy chọn event theo dữ liệu thực sự sẵn có tại từng mốc, giữ logic startup nhẹ, và đặc biệt lưu ý `ApplicationStartingEvent` khác `ApplicationStartedEvent`. Khi có cây context, lỗi startup hoặc nhu cầu order, xác nhận hành vi bằng integration test thay vì suy đoán.
