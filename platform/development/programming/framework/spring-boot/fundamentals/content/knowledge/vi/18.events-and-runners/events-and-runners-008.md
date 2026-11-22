# Listener trước khi context tồn tại không thể chỉ khai báo như bean thông thường

Khi khởi động một ứng dụng Spring Boot, chúng ta có thể muốn quan sát thời điểm ứng dụng bắt đầu chạy, đọc môi trường cấu hình sớm, hoặc xử lý một lỗi khởi động. Spring Boot phát ra những **application event** cho các mốc này. Tuy nhiên, một số event xuất hiện **trước khi `ApplicationContext` được tạo**. Khi đó chưa có Spring container hoàn chỉnh để quét `@Component`, gọi phương thức `@Bean` hoặc đăng ký phương thức `@EventListener`.

Vì vậy, một listener cần nhận những event rất sớm **không thể chỉ được khai báo như một Spring bean thông thường**. Nó phải được đăng ký trực tiếp với `SpringApplication`, thông qua `SpringApplicationBuilder` hoặc bằng cơ chế tự khám phá listener được Spring Boot hỗ trợ.

Bài học phân biệt những thời điểm khởi động, cách đăng ký listener đúng lúc và trường hợp nên dùng một cơ chế khác như `ApplicationContextInitializer`, `EnvironmentPostProcessor` hoặc `ApplicationRunner`.

## 1. Hai vòng đời cần phân biệt

Spring Boot điều phối quá trình khởi động bằng `SpringApplication`. Trong quá trình đó, nó tạo `Environment`, xây dựng `ApplicationContext`, đăng ký bean definitions, refresh context và chạy các runner.

Từ góc nhìn event listener, có hai giai đoạn:

1. **Trước khi context được tạo hoặc sẵn sàng:** `SpringApplication` đã hoạt động, nhưng các bean của ứng dụng chưa thể được sử dụng như những dependency thông thường.
2. **Sau khi context đã khởi tạo và refresh:** các bean đã được tạo theo quy tắc lifecycle, nên listener là Spring bean có thể tham gia vào những sự kiện phù hợp.

Sơ đồ khái quát:

~~~text
main(String[] args)
         |
         v
SpringApplication.run(...)
         |
         v
ApplicationStartingEvent            <-- Context chưa tồn tại
         |
         v
Chuẩn bị Environment
         |
         v
ApplicationEnvironmentPreparedEvent <-- Context chưa tồn tại
         |
         v
Tạo ApplicationContext
         |
         v
ApplicationContextInitializedEvent   <-- Context tồn tại, chưa nạp xong cấu hình
         |
         v
Nạp nguồn cấu hình và bean definitions
         |
         v
ApplicationPreparedEvent             <-- Context chưa refresh xong
         |
         v
Refresh ApplicationContext
         |
         v
ApplicationStartedEvent              <-- Context đã refresh
         |
         v
Chạy ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent                <-- Boot đã hoàn tất quá trình khởi động
~~~

`ApplicationFailedEvent` có thể xuất hiện nếu quá trình khởi động thất bại. Tùy thời điểm lỗi, application context **có thể chưa được tạo**, đã tạo nhưng chưa refresh xong, hoặc đã tồn tại. Vì vậy, listener cần nhận lỗi ở mọi giai đoạn cũng nên được đăng ký sớm.

Đây là trình tự mức khái niệm của những sự kiện thông dụng; Spring Boot còn có các bước bootstrap, log và availability event chi tiết tùy phiên bản.

## 2. Các event khởi động quan trọng

Spring Boot cung cấp nhiều loại event trong `org.springframework.boot.context.event`:

| Event | Thời điểm khái quát | Có thể chỉ trông vào bean listener không? |
|---|---|---|
| `ApplicationStartingEvent` | Ngay đầu quá trình chạy, trước khi chuẩn bị Environment/context | **Không** |
| `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị để sử dụng nhưng context chưa tạo | **Không** |
| `ApplicationContextInitializedEvent` | Context được tạo và các initializer đã chạy, trước khi nạp đầy đủ cấu hình | Không nên phụ thuộc vào bean listener |
| `ApplicationPreparedEvent` | Context có mặt, các nguồn cấu hình đã được nạp nhưng chưa refresh | Không nên phụ thuộc vào bean listener |
| `ApplicationStartedEvent` | Context refresh xong, trước khi các runner chạy | Có thể dùng Spring bean listener |
| `ApplicationReadyEvent` | Sau khi các runner hoàn tất | Có thể dùng Spring bean listener |
| `ApplicationFailedEvent` | Khi startup thất bại | Đăng ký sớm để bao phủ cả lỗi trước context |

Với `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`, lý do rất rõ: **chưa có context để bean trong ứng dụng nhận event**. Với các event ngay sau khi context vừa được tạo, bean listener cũng chưa chắc được nạp hoặc đăng ký đúng thời điểm. Phần lớn trường hợp cần theo dõi các mốc này nên dùng listener đã đăng ký với `SpringApplication` từ đầu.

Không nên nhầm `ApplicationStartedEvent` với `ApplicationReadyEvent`: event thứ nhất diễn ra khi context đã refresh nhưng runner chưa thực thi; event thứ hai diễn ra sau khi Boot chạy xong các runner.

## 3. Vì sao @Component hoặc @Bean không đủ cho event quá sớm?

Một cách thường gặp để đăng ký listener là đánh dấu class bằng `@Component`:

~~~java
package com.example.catalog.startup;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

Cách này phù hợp với `ApplicationReadyEvent`. Spring phát hiện `ReadyListener` khi xử lý cấu hình, tạo bean và đăng ký nó để nhận event sau khi context đã sẵn sàng.

Nhưng nếu đổi sang:

~~~java
@Component
public class TooLateListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Application is starting");
    }
}
~~~

thì class chỉ được tạo thành bean **khi context xử lý component scan**, trong khi `ApplicationStartingEvent` đã được phát trước đó. Event không đợi bean được tạo rồi phát lại cho bean này.

Tương tự, khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
class ListenerConfiguration {

    @Bean
    ApplicationListener<ApplicationEnvironmentPreparedEvent> earlyListener() {
        return event -> System.out.println("Environment prepared");
    }
}
~~~

không giải quyết được sự cố. Phương thức `@Bean` chỉ được Spring xử lý khi context bắt đầu nạp cấu hình, sau thời điểm event môi trường sớm đã xảy ra.

Với phương thức `@EventListener` cũng có giới hạn tương tự:

~~~java
@Component
class EarlyEventMethods {

    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        System.out.println("Starting");
    }
}
~~~

`@EventListener` được xử lý thông qua hạ tầng Spring bean sau khi context được xây dựng. Nó không tự đăng ký phương thức này vào bộ phát event ban đầu của `SpringApplication` trước khi context tồn tại.

**Quy tắc:** Nếu event có thể xảy ra trước khi Spring tạo bean listener, hãy đăng ký listener với cơ chế tồn tại trước context.

## 4. Cách 1: SpringApplication.addListeners(...)

Cách trực tiếp nhất là tạo listener bằng Java và đăng ký nó trước khi gọi `run()`.

Giả sử ứng dụng cần quan sát `ApplicationEnvironmentPreparedEvent`.

### 4.1. Viết listener

~~~java
package com.example.catalog.startup;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {

        String appName = event.getEnvironment()
                .getProperty("spring.application.name", "unnamed");

        System.out.println("Preparing application: " + appName);
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Listener sử dụng `Environment` có sẵn từ event. Nó không cần `@Component` và không yêu cầu Spring tiêm dependency.

### 4.2. Đăng ký trước run()

~~~java
package com.example.catalog;

import com.example.catalog.startup.EarlyEnvironmentListener;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CatalogApplication.class);

        application.addListeners(new EarlyEnvironmentListener());
        application.run(args);
    }
}
~~~

Trình tự lúc này:

~~~text
new SpringApplication(CatalogApplication.class)
             |
             v
addListeners(new EarlyEnvironmentListener())
             |
             v
run(args)
             |
             v
SpringApplication phát ApplicationEnvironmentPreparedEvent
             |
             v
EarlyEnvironmentListener đã có sẵn -> nhận event
             |
             v
Sau đó mới tiếp tục tạo ApplicationContext
~~~

Đây là khác biệt then chốt: listener đã tồn tại **trước khi `run()` bắt đầu các bước startup**, nên có thể nhận event dù context chưa có.

### 4.3. Vì sao không cần @Autowired?

Đối tượng được tạo bằng:

~~~java
new EarlyEnvironmentListener()
~~~

là một Java object thông thường đã được đưa vào danh sách listener của `SpringApplication`. Nó không trở thành bean chỉ vì được đăng ký theo cách này.

Do đó, không thiết kế nó như sau:

~~~java
public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Autowired
    private AuditService auditService; // Không được inject chỉ nhờ addListeners.

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        auditService.recordStartup();
    }
}
~~~

`auditService` sẽ không tự được inject vào đối tượng tạo bằng `new`; hơn nữa, ở thời điểm `ApplicationStartingEvent`, bean `AuditService` còn chưa được tạo.

Với listener sớm, hãy dùng dữ liệu event cung cấp, các Java dependency đơn giản được truyền tường minh vào constructor hoặc những dịch vụ bootstrap được thiết kế cho giai đoạn đó. Không cố tìm business service bằng `ApplicationContext.getBean(...)` khi context chưa tồn tại.

## 5. Cách 2: SpringApplicationBuilder.listeners(...)

Nếu ứng dụng sử dụng `SpringApplicationBuilder` để cấu hình khởi động, có thể đăng ký listener ngay trong chuỗi builder:

~~~java
import com.example.catalog.startup.EarlyEnvironmentListener;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class CatalogLauncher {

    public static void main(String[] args) {
        new SpringApplicationBuilder(CatalogApplication.class)
                .listeners(new EarlyEnvironmentListener())
                .run(args);
    }
}
~~~

`listeners(...)` cho phép listener được đưa vào `SpringApplication` trong lúc builder thiết lập ứng dụng, trước quá trình chạy.

Phương án này hữu ích khi chương trình đã dùng builder để cấu hình profile, source, web application type hoặc context hierarchy.

**Không nhầm với `@Bean`:** Builder listener được đăng ký ở cấp bootstrap. Một bean listener khai báo trong `@Configuration` vẫn được khởi tạo theo lifecycle của context.

Nếu ứng dụng xây nhiều context bằng builder, hãy xác định listener được đăng ký cho application nào và event phát ra từ context nào. Các event startup có thể liên quan tới nhiều context, vì vậy listener không nên mặc định giả định chỉ có đúng một startup event cho toàn bộ JVM.

## 6. Cách 3: Tự động đăng ký listener bằng META-INF/spring.factories

Đối với thư viện hoặc starter không kiểm soát `main()` của ứng dụng chủ, yêu cầu người dùng viết `application.addListeners(...)` trong mọi dự án có thể bất tiện.

Spring Boot hỗ trợ khám phá một số listener từ tài nguyên `META-INF/spring.factories` trong JAR. Có thể đăng ký bằng key `org.springframework.context.ApplicationListener`.

Ví dụ cấu trúc thư viện:

~~~text
shared-startup-library/
└── src/main/
    ├── java/
    │   └── com/example/startup/
    │       └── StartupDiagnosticsListener.java
    └── resources/
        └── META-INF/
            └── spring.factories
~~~

Listener:

~~~java
package com.example.startup;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartupDiagnosticsListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public StartupDiagnosticsListener() {
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Spring Boot startup has begun");
    }
}
~~~

Nội dung `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupDiagnosticsListener
~~~

Khi JAR chứa tài nguyên này nằm trên runtime classpath, Boot có thể tải listener thông qua cơ chế factory loading của nó và đăng ký đủ sớm cho các application event tương ứng.

Nếu có nhiều listener, có thể khai báo các tên class được phân tách bằng dấu phẩy trong thuộc tính đó:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupDiagnosticsListener,\
com.example.startup.EarlyEnvironmentListener
~~~

Những class được khai báo phải có cách khởi tạo phù hợp với cơ chế factory loader; public no-args constructor là lựa chọn đơn giản, dễ tương thích cho ví dụ này. Đừng kỳ vọng chúng sẽ nhận constructor injection như bean thông thường.

### 6.1. spring.factories khác AutoConfiguration.imports

Trong Spring Boot hiện đại, auto-configuration của thư viện có thể được đăng ký qua:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nhưng file đó dùng để công bố **auto-configuration classes**. Nó không thay cho việc đăng ký `ApplicationListener` sớm qua `spring.factories`.

| Tài nguyên | Vai trò |
|---|---|
| `META-INF/spring.factories`, key `org.springframework.context.ApplicationListener` | Đăng ký listener ở cấp bootstrap |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Công bố các auto-configuration class để Boot xử lý |
| `@Component` trên listener | Đăng ký bean listener khi context/component scan hoạt động |

Nếu thư viện cần quan sát `ApplicationStartingEvent`, không thể chỉ khai báo một auto-configuration với phương thức `@Bean` tạo listener rồi chờ event đầu tiên: auto-configuration đó cũng được xử lý sau khi startup đã bắt đầu.

## 7. Ví dụ listener cho ApplicationStartingEvent

`ApplicationStartingEvent` xảy ra rất sớm. Ở thời điểm này không có `ApplicationContext`, và chưa có `Environment` đã chuẩn bị đầy đủ để tra cứu property như ở giai đoạn sau.

Một listener phù hợp chỉ nên làm những việc đơn giản:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        String[] args = event.getArgs();

        System.out.println(
                "Spring Boot is starting; argument count = " + args.length
        );
    }
}
~~~

Đăng ký:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new EarlyStartupListener());
app.run(args);
~~~

Không nên truy cập cơ sở dữ liệu, gọi API từ xa, tìm service bean hoặc dùng đối tượng context ở đây.

Nếu cần đưa hành vi vào hạ tầng logging sớm, hãy xem cơ chế logging/bootstrap của Spring Boot thay vì cố sử dụng một bean logger hoặc service chưa có. Cũng không nên in toàn bộ command-line arguments nếu có khả năng chứa token, mật khẩu hoặc thông tin bí mật.

## 8. Ví dụ listener cho ApplicationEnvironmentPreparedEvent

`ApplicationEnvironmentPreparedEvent` có ích khi cần quan sát `ConfigurableEnvironment` trước khi application context được tạo.

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentInspectionListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {

        var environment = event.getEnvironment();

        boolean featureEnabled = environment.getProperty(
                "app.feature.enabled",
                Boolean.class,
                false
        );

        System.out.println("Feature enabled: " + featureEnabled);
    }
}
~~~

Đăng ký listener trước `run()` tương tự ví dụ trước.

### 8.1. Phân biệt Environment hiện có với Environment đã hoàn tất mọi bước xử lý

Event cho biết `Environment` đã tồn tại, nhưng **thứ tự giữa các listener và các bước xử lý cấu hình vẫn quan trọng**. Tùy phiên bản, nguồn cấu hình và thứ tự event listener, một property source có thể chưa được nạp hoặc chưa được bổ sung ở đúng thời điểm listener của bạn chạy.

Nếu listener cần nhìn thấy các property do một bước xử lý Environment khác cung cấp, hãy kiểm tra thứ tự thực thi và thiết kế bootstrap tương ứng. Không nên khẳng định rằng tất cả `application.yml`, remote configuration hoặc property source tùy chỉnh đã chắc chắn sẵn sàng tại mọi mốc event và mọi giá trị order.

Để chỉ quan sát cấu hình, ưu tiên logic không có side effect. Nếu phải bổ sung một property source vào Environment, `EnvironmentPostProcessor` thường diễn đạt trách nhiệm đó rõ ràng hơn một listener chung.

## 9. Listener sớm có thể nhận ApplicationFailedEvent

`ApplicationFailedEvent` được phát khi Boot gặp lỗi trong quá trình chạy. Nếu muốn ghi nhận cả lỗi xảy ra trước khi context được tạo, cần listener đã đăng ký từ trước startup:

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        System.err.println(
                "Application failed: " + failure.getClass().getSimpleName()
        );
    }
}
~~~

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new StartupFailureListener());
app.run(args);
~~~

Tùy giai đoạn thất bại, `event.getApplicationContext()` có thể là `null` hoặc tham chiếu một context chưa sẵn sàng. Không dựa vào việc lấy bean từ context để xử lý lỗi startup sớm.

Listener ghi nhận thất bại không thay thế cơ chế bắt lỗi khởi động và xử lý exit code của Spring Boot. Một listener cũng có thể phát sinh lỗi riêng; do đó, phần xử lý trong failure listener nên đơn giản, tránh tiếp tục ném exception làm che khuất nguyên nhân gốc.

## 10. Các cách đăng ký listener và thời điểm chúng có tác dụng

| Cách đăng ký | Có trước khi tạo context? | Phù hợp với |
|---|---|---|
| `SpringApplication.addListeners(listener)` trước `run()` | Có | Event rất sớm, launcher do ứng dụng kiểm soát |
| `SpringApplicationBuilder.listeners(listener)` | Có, khi builder thiết lập application | App dùng builder hoặc nhiều context |
| `META-INF/spring.factories` với `ApplicationListener` | Có, qua Boot factory loading | Thư viện/starter cần tự đăng ký listener |
| `@Component` implements `ApplicationListener<E>` | Không | Event sau khi bean đã được đăng ký |
| `@Bean` trả `ApplicationListener<E>` | Không | Event khi context đã được cấu hình phù hợp |
| Phương thức `@EventListener` trên bean | Không | Event được phát sau khi hạ tầng listener của context hoạt động |

Một event đã được phát trước khi listener bean tồn tại sẽ không tự động được phát lại chỉ vì bean được đăng ký sau đó.

Nếu cùng một listener class vừa được công bố trong `spring.factories` vừa được đăng ký bằng `@Component` hoặc `@Bean`, có thể tạo nhiều listener instance và làm hành vi khó dự đoán. Hãy chọn mô hình đăng ký phù hợp, tránh vô tình xử lý cùng một event nhiều lần.

## 11. Thứ tự thực thi listener: Ordered và @Order

Khi nhiều listener nhận cùng một event, thứ tự có thể quan trọng. Spring hỗ trợ `Ordered` và `@Order` trong những cơ chế event multicasting phù hợp.

Ví dụ:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class AuditEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Inspecting prepared environment");
    }
}
~~~

Theo quy ước `Ordered`, giá trị nhỏ hơn có mức ưu tiên đứng trước giá trị lớn hơn. `Ordered.HIGHEST_PRECEDENCE` biểu thị mức ưu tiên rất cao, còn `Ordered.LOWEST_PRECEDENCE` là mức thấp.

Hãy lưu ý:

- Ordering áp dụng cho trình tự gọi listener của một event multicaster có hỗ trợ sắp xếp; nó không làm một bean listener tồn tại trước khi context được tạo.
- Không nên tự ý chọn mức ưu tiên cực cao nếu listener cần kết quả từ những listener/processor khác.
- Boot có các listener nội bộ quan trọng cho việc chuẩn bị Environment và logging; đăng ký listener tùy chỉnh cần thận trọng với thứ tự nếu phụ thuộc vào các bước đó.
- Event listener khởi động thông thường được gọi đồng bộ trong quá trình phát event; công việc nặng có thể làm chậm startup.

Nếu cần dữ liệu ở một mốc lifecycle muộn hơn, chuyển sang event phù hợp thay vì cố điều chỉnh `@Order` để lấy bean chưa tồn tại.

## 12. ApplicationContextInitializer: context đã tồn tại nhưng chưa refresh

Có tình huống cần can thiệp **sau khi context được tạo nhưng trước khi refresh**. Khi đó, `ApplicationContextInitializer` là một công cụ phù hợp hơn `ApplicationStartingEvent`.

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public final class CatalogContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String appName = context.getEnvironment()
                .getProperty("spring.application.name", "catalog");

        System.out.println("Initializing context for " + appName);
    }
}
~~~

Đăng ký trước run:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addInitializers(new CatalogContextInitializer());
app.run(args);
~~~

Khi initializer được gọi, đã có context object. Tuy nhiên, context **chưa hoàn thành refresh**, nên không nên sử dụng nó như container đầy đủ rồi yêu cầu mọi service/repository bean đã sẵn sàng.

So sánh:

| Điểm mở rộng | Thời điểm | Nguồn dữ liệu phù hợp |
|---|---|---|
| `ApplicationStartingEvent` listener | Rất sớm, chưa có Environment/context hoàn chỉnh | Arguments và metadata startup có sẵn |
| `ApplicationEnvironmentPreparedEvent` listener | Có Environment, chưa có context | Environment và bootstrap metadata |
| `ApplicationContextInitializer` | Đã tạo context, chưa refresh | Context object, Environment, bean factory metadata phù hợp |
| Spring bean `@EventListener` | Sau khi listener bean đã được đăng ký | Bean dependencies và event tương ứng |

`ApplicationContextInitializer` cũng có thể được đăng ký bằng các cơ chế bootstrap do Boot hỗ trợ. Tuy nhiên, một bean `@Component` implements initializer sẽ không tự động thay thế cho initializer phải chạy trước khi component scan diễn ra.

## 13. EnvironmentPostProcessor: khi cần thay đổi nguồn cấu hình từ rất sớm

Nếu yêu cầu là bổ sung hoặc điều chỉnh property source trước khi tạo context, Spring Boot có `EnvironmentPostProcessor`.

Ví dụ minh họa một property source chứa giá trị mặc định của module:

~~~java
package com.example.catalog.startup;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class CatalogDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> defaults = Map.of(
                "app.catalog.enabled", "true"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogDefaults", defaults)
        );
    }
}
~~~

Đăng ký trong `META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.catalog.startup.CatalogDefaultsEnvironmentPostProcessor
~~~

`addLast` đặt property source ở mức ưu tiên thấp hơn các source đứng trước, phù hợp cho một tập default. Đây là ví dụ thiết lập đơn giản; trong thực tế, phải kiểm soát thứ tự EnvironmentPostProcessor và tác động lên hệ thống cấu hình.

Mục đích của `EnvironmentPostProcessor` là xử lý cấu hình của Environment. Nếu chỉ muốn ghi nhận một mốc startup, `ApplicationListener` có thể đơn giản hơn. Nếu chỉ muốn kiểm tra bean đã sẵn sàng sau khi ứng dụng chạy, sử dụng listener hoặc runner ở giai đoạn muộn hơn.

## 14. Phân biệt event listener với runner

`ApplicationRunner` và `CommandLineRunner` được Boot gọi **sau khi context refresh hoàn tất**, nhưng **trước `ApplicationReadyEvent`**.

Ví dụ:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Running startup data task");
    }
}
~~~

Runner là Spring bean bình thường, vì vậy constructor injection hoạt động như dự kiến:

~~~java
@Component
public class StartupDataLoader implements ApplicationRunner {

    private final CatalogService catalogService;

    public StartupDataLoader(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.initializeReferenceData();
    }
}
~~~

Đây là lựa chọn phù hợp khi cần thao tác nghiệp vụ dựa trên bean đã được tạo. Nó không thể nhận thay `ApplicationStartingEvent` vì runner được gọi ở mốc muộn hơn rất nhiều.

Bảng lựa chọn:

| Nhu cầu | Công cụ thường phù hợp |
|---|---|
| Biết lúc `SpringApplication` bắt đầu chạy | Listener đăng ký sớm cho `ApplicationStartingEvent` |
| Đọc Environment trước khi context được tạo | Listener cho `ApplicationEnvironmentPreparedEvent` |
| Bổ sung property source từ bootstrap | `EnvironmentPostProcessor` |
| Tùy chỉnh context ngay sau khi tạo, trước refresh | `ApplicationContextInitializer` |
| Thực hiện tác vụ dùng Spring service/repository sau refresh | `ApplicationRunner` hoặc `CommandLineRunner` |
| Biết Boot đã hoàn thành các runner | Listener cho `ApplicationReadyEvent` |
| Theo dõi thất bại ngay cả khi chưa có context | Listener `ApplicationFailedEvent` đăng ký sớm |

Không có một listener duy nhất phù hợp cho mọi loại công việc startup. Mỗi extension point nằm ở một mốc khác nhau trong lifecycle.

## 15. Vấn đề với logging, I/O và lỗi trong early listener

Một listener sớm chạy khi ứng dụng đang ở giai đoạn bootstrap. Vì vậy, không nên giả định:

- Logger và cấu hình logging đã hoàn tất như khi ứng dụng sẵn sàng.
- Tất cả property sources đã có giá trị cuối cùng.
- Cơ chế AOP như `@Transactional` hoặc `@Async` đã hoạt động cho listener.
- Database, HTTP clients hoặc repositories có thể được inject từ context.
- Listener sẽ có một transaction hoặc request scope mặc định.
- Có thể chặn startup bằng một lệnh gọi mạng kéo dài mà không ảnh hưởng readiness.

Nếu listener ném exception trong một giai đoạn startup quan trọng, quá trình khởi động có thể bị gián đoạn. Chỉ thực hiện logic đủ nhẹ, idempotent khi cần và có chính sách lỗi rõ ràng.

Ngoài ra, tránh ghi trực tiếp secrets, access token, mật khẩu hoặc toàn bộ Environment/command-line arguments vào log. Khi cần chẩn đoán startup, chỉ ghi metadata không nhạy cảm.

### Ví dụ nên tránh

~~~java
public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
    // Không nên dùng một early listener để chạy nghiệp vụ phụ thuộc DB.
    // orderRepository.deleteAll();
    // remoteService.warmUp();
}
~~~

Hai dependency kia chưa chắc đã tồn tại ở thời điểm event này. Nếu cần warm-up hoặc thực thi migration, hãy sử dụng cơ chế phù hợp sau khi container có đủ bean và dependency.

## 16. Event của nhiều context và hiện tượng listener chạy nhiều lần

Trong ứng dụng có parent–child context hoặc sử dụng `SpringApplicationBuilder` tạo nhiều application, các application event có thể liên quan đến nhiều context khác nhau.

Spring `ApplicationContext` có cơ chế chuyển tiếp event từ child lên parent. Nếu một listener được đăng ký ở cả parent và child, hoặc một listener toàn cục được gắn vào nhiều `SpringApplication`, một sự kiện có thể được quan sát nhiều lần tùy kiến trúc.

Khi xử lý listener ở môi trường nhiều context:

1. Xác định launcher hoặc `SpringApplication` nào sở hữu listener.
2. Xem event có thuộc context mà listener quan tâm không.
3. Tránh khởi tạo cùng tài nguyên dùng chung nhiều lần khi nhận event trùng.
4. Nếu listener xử lý `ContextRefreshedEvent` hoặc `ApplicationReadyEvent`, đừng mặc định JVM chỉ phát đúng một event cho mọi context.

Nếu cần một hành động startup duy nhất ở cấp ứng dụng, nên chọn nơi đăng ký và lifecycle rõ ràng, và có cơ chế idempotence khi phù hợp.

## 17. Kiểm thử listener trước khi context tồn tại

Một unit test gọi trực tiếp `onApplicationEvent(...)` chỉ kiểm tra logic xử lý khi đã có event object. Nó không chứng minh listener thật sự được đăng ký đúng thời điểm bootstrap.

Để xác nhận cơ chế đăng ký sớm, có thể chạy một ứng dụng Spring Boot tối thiểu trong test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

class EarlyListenerRegistrationTest {

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfiguration {
    }

    @Test
    void programmaticListenerReceivesEnvironmentEvent() {
        AtomicInteger received = new AtomicInteger();

        SpringApplication app =
                new SpringApplication(MinimalConfiguration.class);

        app.setWebApplicationType(WebApplicationType.NONE);

        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> received.incrementAndGet()
        );

        try (ConfigurableApplicationContext context = app.run()) {
            assertThat(received.get()).isEqualTo(1);
        }
    }
}
~~~

Bài kiểm thử sử dụng context không có web server để giảm phụ thuộc. Listener được đăng ký trước `app.run()`, và assertion xác nhận đã nhận `ApplicationEnvironmentPreparedEvent`.

Để kiểm thử cơ chế `spring.factories`, cần chắc chắn resource nằm trên test runtime classpath và class listener thực sự được Boot factory loading khám phá. Có thể viết một test khởi động ứng dụng tối thiểu và kiểm tra một dấu hiệu quan sát được của listener. Không nên kết luận file `spring.factories` đúng chỉ vì class listener tự biên dịch được.

### Những tình huống nên kiểm tra

- Listener qua `addListeners` nhận `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.
- Listener chỉ là bean `@Component` không bị kỳ vọng nhận các event xảy ra trước context.
- Listener đăng ký từ `spring.factories` hoạt động khi thư viện ở runtime classpath.
- `ApplicationReadyEvent` chạy sau runner như dự kiến.
- Failure listener xử lý được lỗi xảy ra trước context khi phù hợp.
- Nếu thứ tự listener có ý nghĩa, kiểm tra bằng các event/bootstrap setup thật thay vì suy đoán từ `@Order`.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `ApplicationStartingEvent` listener gắn `@Component` nhưng không chạy | Bean được tạo sau khi event đã phát | Đăng ký bằng `addListeners`, builder hoặc `spring.factories` |
| Phương thức `@EventListener` không thấy event môi trường sớm | Hạ tầng annotation listener chưa hoạt động | Dùng `ApplicationListener<E>` được đăng ký trước run |
| Listener có `@Autowired` nhưng field `null` | Đối tượng được tạo bằng `new` và không do Spring quản lý | Dùng event data hoặc chuyển logic phụ thuộc bean sang giai đoạn muộn |
| Listener thư viện không chạy | `spring.factories` sai key/path, resource không được đóng gói hoặc thiếu JAR runtime | Kiểm tra metadata, package và runtime classpath |
| AutoConfiguration.imports không giúp nhận event đầu tiên | Auto-configuration là cơ chế nạp cấu hình khi context đang được xây dựng | Dùng metadata `ApplicationListener` trong `spring.factories` |
| Listener đọc property nhưng thiếu giá trị | Property source chưa được nạp hoặc thứ tự xử lý chưa phù hợp | Kiểm tra phase và listener ordering; cân nhắc `EnvironmentPostProcessor` |
| Listener xử lý lặp lại | Đăng ký nhiều lần hoặc có nhiều context/event propagation | Kiểm tra vị trí đăng ký và event source |
| Startup thất bại khi listener chạy | Exception hoặc I/O sớm làm gián đoạn bootstrap | Giảm side effects, xử lý lỗi có chủ đích |
| Listener muốn dùng repository nhưng không tìm được | Repository bean chưa tồn tại trong startup phase | Dùng runner, ready listener hoặc lifecycle muộn hơn |

## 19. Nguyên tắc thiết kế

**Chọn đúng thời điểm.** Nếu chỉ cần biết lúc ứng dụng bắt đầu hoặc lúc Environment được chuẩn bị, dùng listener đã đăng ký trước `run()`. Nếu cần thao tác service/repository, đợi đến giai đoạn context đã refresh.

**Không dùng bean registry trước khi nó tồn tại.** `@Component`, `@Bean` và `@EventListener` phát huy tác dụng khi Spring xử lý bean của context; chúng không tự giải quyết các event xảy ra trước đó.

**Đăng ký listener ở cấp thích hợp.** Ứng dụng kiểm soát `main()` có thể dùng `SpringApplication.addListeners`; ứng dụng dùng builder có thể dùng `listeners(...)`; thư viện/starter có thể dùng `spring.factories`.

**Giữ listener sớm nhỏ và độc lập.** Chỉ dùng thông tin event cung cấp và các dependency bootstrap an toàn. Tránh business service, I/O nặng hoặc assumptions về proxy, transaction và request scope.

**Dùng đúng extension point cho đúng việc.** `EnvironmentPostProcessor` cho property sources, `ApplicationContextInitializer` cho context trước refresh, runner cho công việc sau refresh, `ApplicationReadyEvent` cho dấu mốc ứng dụng sẵn sàng.

**Kiểm thử bằng quy trình startup thật.** Việc listener tự tạo và chạy được trong unit test chưa chứng minh nó đã được đăng ký đúng giai đoạn.

Điểm cần ghi nhớ là **`SpringApplication` bắt đầu phát event trước khi có `ApplicationContext` và Spring bean**. Vì vậy, listener cần nhận `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` phải có mặt từ giai đoạn bootstrap. Hãy đăng ký nó bằng `addListeners`, `SpringApplicationBuilder.listeners` hoặc `spring.factories`. Listener là bean thông thường vẫn phù hợp với các sự kiện muộn hơn, khi container đã có khả năng tạo, quản lý và đăng ký bean đó.
