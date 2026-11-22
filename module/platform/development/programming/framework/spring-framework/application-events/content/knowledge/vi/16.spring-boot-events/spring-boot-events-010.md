# SpringApplication.addListeners trong Spring Boot Application Events

## 1. Mục đích của SpringApplication.addListeners

`SpringApplication.addListeners(ApplicationListener<?>... listeners)` là API của Spring Boot để **đăng ký thêm một hoặc nhiều listener cho quá trình khởi động ứng dụng trước khi gọi `SpringApplication.run(...)`**. Các listener được thêm vào `SpringApplication` và sau đó được đăng ký với `ApplicationContext` khi context đã sẵn sàng.

Điểm khác biệt quan trọng nhất so với `@EventListener` hoặc `@Bean ApplicationListener` là **thời điểm đăng ký**:

- Trong lúc Boot bắt đầu chạy, những sự kiện như `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` xảy ra **trước khi `ApplicationContext` được tạo**.
- Các listener phụ thuộc vào Spring bean chưa tồn tại ở giai đoạn đó, nên không thể tin rằng `@EventListener` hay `@Bean` được quét và khởi tạo kịp để nhận những sự kiện sớm.
- Listener được truyền vào `app.addListeners(...)` **trước `app.run(...)`** đã được đăng ký với chính `SpringApplication`, nên có thể nhận các sự kiện khởi động sớm.
- Sau khi context được tạo và cấu hình, listener đó cũng được đăng ký với context và có thể tiếp tục nhận các sự kiện phù hợp do context phát.

Nói ngắn gọn: **`SpringApplication.addListeners` dùng khi cần quan sát hoặc phản ứng với các sự kiện vòng đời của Spring Boot ngay từ đầu quá trình bootstrap**, chứ không chỉ sau khi container bean hoàn tất.

Ví dụ đăng ký một listener ngay từ phương thức `main`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event ->
        System.out.println("Ứng dụng bắt đầu khởi động"));
app.run(args);
~~~

*Đây là đoạn minh họa, không phải chương trình độc lập; cần `MyApplication` cùng các import Spring Boot và Spring Context. Ví dụ đầy đủ, chạy được nằm ở phần 4.*

**Lưu ý:** `addListeners` chỉ đăng ký listener; nó **không tự khởi động ứng dụng, không tự tạo event và không trả về kết quả xử lý event**. Thao tác khởi động vẫn là `run(...)`.

## 2. API và các thành phần liên quan

Chữ ký chính trên lớp `org.springframework.boot.SpringApplication`:

~~~java
public void addListeners(ApplicationListener<?>... listeners);
~~~

`ApplicationListener<E>` là giao diện của Spring Framework, với phương thức nhận một event kiểu `E`:

~~~java
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
~~~

*Chữ ký được trình bày ở dạng rút gọn để học API; không cần tự khai báo lại interface của Spring.*

Bảng khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| `SpringApplication` | Đối tượng cấu hình, bootstrap và chạy Spring Boot. |
| `SpringApplication.addListeners(...)` | **Thêm** các listener trước khi `run(...)`; không thay cả tập listener hiện có. |
| `ApplicationListener<E>` | Giao diện nhận event kiểu `E extends ApplicationEvent`. |
| `SpringApplication.setListeners(...)` | **Thiết lập/thay thế** tập listener được cấu hình trên `SpringApplication`; cần thận trọng vì có thể ảnh hưởng listener nội bộ. |
| `SpringApplication.getListeners()` | Lấy tập listener hiện được cấu hình trên đối tượng `SpringApplication` (dạng chỉ đọc theo API). |
| `SpringApplicationBuilder.listeners(...)` | Cách đăng ký listener khi cấu hình ứng dụng qua builder. |
| `ApplicationContext.addApplicationListener(...)` | Đăng ký trực tiếp với một context đã có; không thể quay lại để nhận sự kiện phát trước khi context được tạo. |

Một điểm thực hành: `addListeners` nhận **đối tượng listener đã được tạo**. Nếu gọi `new MyListener()`, đối tượng này không tự nhiên có `@Autowired`, `@PostConstruct` hay những tính năng bean lifecycle như một Spring bean bình thường. Listener dùng cho bootstrap nên độc lập với DI hoặc chỉ phụ thuộc các thông tin sẵn có ngay ở thời điểm sự kiện.

## 3. Những sự kiện nào xuất hiện trong quá trình SpringApplication.run?

Spring Boot công bố những mốc vòng đời điển hình sau:

| Event | Thời điểm | Có `ApplicationContext` dùng để truy cập bean chưa? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Ngay đầu `run`, sau khi đăng ký listener/initializer và trước khi chuẩn bị environment. | **Chưa.** |
| `ApplicationEnvironmentPreparedEvent` | `Environment` đã được chuẩn bị nhưng context chưa được tạo. | **Chưa.** Có thể đọc/chỉnh `Environment` phù hợp. |
| `ApplicationContextInitializedEvent` | Context đã được tạo và `ApplicationContextInitializer` đã chạy, trước khi tải bean definitions. | Context có nhưng **chưa refresh**; chưa nên dùng như container bean hoàn chỉnh. |
| `ApplicationPreparedEvent` | Bean definitions đã được tải, ngay trước `refresh`. | Context có nhưng **chưa refresh** xong. |
| `ApplicationStartedEvent` | Context đã refresh xong, **trước** `ApplicationRunner` và `CommandLineRunner`. | Có. |
| `ApplicationReadyEvent` | Các runner đã hoàn tất, ứng dụng gần như ở trạng thái sẵn sàng phục vụ. | Có. |
| `ApplicationFailedEvent` | Boot phát khi quá trình startup thất bại. | Có thể **chưa** có context, hoặc context chưa hoàn thiện; phải kiểm tra `null` trước khi dùng. |

Spring Boot cũng phát các `AvailabilityChangeEvent` ở những thời điểm thích hợp, ví dụ `LivenessState.CORRECT` sau `ApplicationStartedEvent` và `ReadinessState.ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent`. Với ứng dụng web còn có `WebServerInitializedEvent` khi web server sẵn sàng, và Spring Framework có `ContextRefreshedEvent` sau refresh.

Các sự kiện **không phải thay thế trực tiếp cho nhau**:

- `ApplicationStartingEvent`: rất sớm, không có environment hoặc context.
- `ApplicationEnvironmentPreparedEvent`: có environment nhưng chưa có context, hữu ích để quan sát/chỉnh cấu hình khởi động.
- `ApplicationStartedEvent`: context refresh đã xong **nhưng runner chưa chạy**.
- `ApplicationReadyEvent`: runner đã chạy, phù hợp cho tác vụ quan sát thời điểm ứng dụng sẵn sàng.
- `ApplicationFailedEvent`: xử lý chẩn đoán khi startup hỏng; không bảo đảm mọi bean hay tài nguyên còn khả dụng.

`SpringApplication.addListeners` đặc biệt có giá trị ở **hai mốc đầu**, vì không thể sử dụng thông thường một `@Bean` hoặc `@EventListener` để nhận event đã xảy ra trước khi container bean tồn tại.

## 4. Ví dụ Java 17+ chạy được: quan sát toàn bộ chuỗi khởi động

Ví dụ dùng **Spring Boot 3.5.16**, Java 17+, Maven; đây là phiên bản có mặt trên Maven Central. Chương trình không chạy web server để đầu ra dễ kiểm soát. Nó đăng ký listener bằng `addListeners(...)` trước `run(...)`, tạo một `CommandLineRunner` để cho thấy sự khác biệt giữa `Started` và `Ready`, rồi đóng context để quan sát sự kiện `ContextClosedEvent`.

### 4.1. Cấu trúc

~~~text
spring-application-listeners-demo/
├── pom.xml
└── src/main/java/example/ListenerRegistrationDemo.java
~~~

Tệp `pom.xml`:

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
    <groupId>example</groupId>
    <artifactId>spring-application-listeners-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

Tệp `src/main/java/example/ListenerRegistrationDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;

@SpringBootApplication
public class ListenerRegistrationDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ListenerRegistrationDemo.class);

        // Các cấu hình giúp đầu ra minh họa gọn, ổn định.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.<String, Object>of(
                "demo.stage", "configured",
                "logging.level.root", "OFF"));

        // Đăng ký trước run(): bắt được cả event rất sớm.
        app.addListeners(
            (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("01 STARTING"),

            (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event ->
                System.out.println("02 ENV: "
                    + event.getEnvironment().getProperty("demo.stage")),

            (ApplicationListener<ApplicationContextInitializedEvent>) event ->
                System.out.println("03 CONTEXT_INITIALIZED"),

            (ApplicationListener<ApplicationPreparedEvent>) event ->
                System.out.println("04 PREPARED"),

            (ApplicationListener<ApplicationStartedEvent>) event ->
                System.out.println("05 STARTED"),

            (ApplicationListener<ApplicationReadyEvent>) event ->
                System.out.println("07 READY"),

            (ApplicationListener<ApplicationFailedEvent>) event ->
                System.out.println("FAILED: " + event.getException()
                    .getClass().getSimpleName()),

            (ApplicationListener<ContextClosedEvent>) event ->
                System.out.println("09 CLOSED")
        );

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("08 RUN_RETURNED");
        }
    }

    @Bean
    public CommandLineRunner demoRunner() {
        return args -> System.out.println("06 RUNNER");
    }
}
~~~

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

**Các dòng do chương trình in trên stdout khi startup thành công** (không tính log/build output phát sinh riêng của Maven/JVM):

~~~text
01 STARTING
02 ENV: configured
03 CONTEXT_INITIALIZED
04 PREPARED
05 STARTED
06 RUNNER
07 READY
08 RUN_RETURNED
09 CLOSED
~~~

### 4.2. Giải thích thứ tự

1. Trước `run`, ứng dụng khởi tạo `SpringApplication` và gọi `app.addListeners(...)`. Các lambda là những `ApplicationListener` riêng, mỗi listener khai báo kiểu event cụ thể.
2. `ApplicationStartingEvent` xảy ra khi chưa có environment/context. Vì listener được đưa vào `SpringApplication` trước lúc chạy nên in `01 STARTING`.
3. Khi `Environment` sẵn sàng, `ApplicationEnvironmentPreparedEvent` được phát. Giá trị mặc định `demo.stage=configured` đã thiết lập trên `SpringApplication` và có thể đọc từ event, nên in `02 ENV: configured`.
4. Context được khởi tạo rồi bean definitions được nạp; hai mốc `03 CONTEXT_INITIALIZED` và `04 PREPARED` xuất hiện trước khi context refresh.
5. Sau khi context refresh thành công, Boot phát `ApplicationStartedEvent`; listener in `05 STARTED`.
6. Spring Boot gọi bean `CommandLineRunner`; dòng `06 RUNNER` xuất hiện sau `STARTED` và trước `READY`.
7. Boot phát `ApplicationReadyEvent`; listener in `07 READY`. Khi `app.run(args)` trả về, chương trình in `08 RUN_RETURNED`.
8. Khối `try-with-resources` đóng context. Listener `ContextClosedEvent` đã được đăng ký với context nên in `09 CLOSED`. Đây là sự kiện của Spring Framework, không phải một mốc thuộc tập `SpringApplicationEvent`.

Dòng `FAILED` không xuất hiện vì ví dụ startup thành công. Không nên tự thêm `FAILED` vào stdout của luồng bình thường.

*Trong thực tế, ứng dụng còn có nhiều listener và event nội bộ khác; các dòng trong ví dụ chỉ là những thông điệp do các listener riêng của chương trình in ra. Cấu hình tắt banner và mức log giúp dễ đọc, không làm thay đổi thứ tự event lifecycle.*

## 5. Vì sao không dùng @Bean hoặc @EventListener cho event sớm?

Một cách khai báo listener quen thuộc:

~~~java
@Component
class ReadyObserver {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready to serve");
    }
}
~~~

*Đây là mã minh họa: cần import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener` và `ApplicationReadyEvent`.*

Phương thức trên hợp lý cho `ApplicationReadyEvent` vì đến thời điểm đó context đã refresh xong và bean được Spring quản lý. Nhưng thử nhận `ApplicationStartingEvent` như sau sẽ không đáng tin:

~~~java
@Component
class TooLateObserver {
    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // Khi processor đăng ký @EventListener, event này đã xảy ra.
    }
}
~~~

`@EventListener` dựa vào hạ tầng đăng ký phương thức event của `ApplicationContext`. Khi event `ApplicationStartingEvent` được phát, context còn chưa tồn tại, vì vậy bean không thể nhận lại sự kiện đã đi qua. `ApplicationEnvironmentPreparedEvent` cũng diễn ra trước khi context được tạo.

Thậm chí khi `ApplicationContext` đã được tạo (`ContextInitialized`/`Prepared`), nó vẫn có thể **chưa refresh**: không nên yêu cầu một bean listener đã hoàn tất lifecycle hoặc gọi tất cả bean services tại giai đoạn này.

Cách chọn đúng:

- Cần bắt **sự kiện trước khi context tồn tại** → đăng ký sớm bằng `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)` hoặc cơ chế `spring.factories`.
- Cần xử lý lúc context hoàn chỉnh → bean `@EventListener` hoặc `ApplicationListener` do Spring quản lý là cách tự nhiên hơn.
- Cần khởi tạo công việc nghiệp vụ sau startup → cân nhắc `ApplicationRunner` hoặc `CommandLineRunner` thay vì làm tác vụ nặng trong listener vòng đời.

## 6. Đăng ký listener bằng class riêng thay vì lambda

Lambda phù hợp cho ví dụ ngắn. Với ứng dụng lớn, class riêng dễ kiểm thử hơn:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        String name = event.getEnvironment()
                .getProperty("spring.application.name", "unknown");
        System.out.println("Bootstrap environment for: " + name);
    }
}
~~~

*Đoạn mã có thể đặt trong tệp `EarlyEnvironmentListener.java` riêng và thêm vào một ứng dụng Spring Boot; nó không phải chương trình độc lập.*

Đăng ký:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new EarlyEnvironmentListener());
application.run(args);
~~~

`Ordered` cho phép mô tả mức ưu tiên của listener so với những listener khác có hỗ trợ sắp xếp; chỉ số nhỏ hơn thường có độ ưu tiên cao hơn. Tuy nhiên, đừng phụ thuộc vào thứ tự tình cờ của hai listener nếu nghiệp vụ cần các bước thực thi có quan hệ phụ thuộc. Thứ tự **các loại event lifecycle** do Boot quyết định; `Ordered` dùng để ảnh hưởng thứ tự **listener của cùng lượt phát event**, không biến `ApplicationReadyEvent` thành sự kiện trước `ApplicationStartingEvent`.

## 7. addListeners, setListeners, builder và spring.factories

### 7.1. addListeners so với setListeners

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(first, second);
~~~

`addListeners` thêm listener mới vào tập listener cấu hình hiện có. Ngược lại, `setListeners(Collection<? extends ApplicationListener<?>>)` thiết lập danh sách mà `SpringApplication` dùng; có thể vô tình thay thế listener do Boot hoặc thư viện đăng ký trước đó. Vì vậy nếu chỉ cần mở rộng, **ưu tiên `addListeners`**.

### 7.2. SpringApplicationBuilder

Nếu xây ứng dụng bằng builder:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new EarlyEnvironmentListener())
        .run(args);
~~~

*Đây là đoạn minh họa, cần import `org.springframework.boot.builder.SpringApplicationBuilder` và khai báo lớp ứng dụng.*

Cách này phục vụ cùng nhu cầu đăng ký listener từ trước khi khởi động nhưng phù hợp khi ứng dụng có các bước tùy biến bootstrapping.

### 7.3. META-INF/spring.factories

Khi viết thư viện muốn listener tự được phát hiện **bất kể ứng dụng bên ngoài tạo `SpringApplication` bằng cách nào**, Spring Boot hỗ trợ đăng ký `ApplicationListener` qua `META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=example.EarlyEnvironmentListener
~~~

Listener từ `spring.factories` là thành phần được Boot nạp trong bootstrap, không phải một bean do component scanning tạo ra sau đó. Class phải có constructor/khả năng khởi tạo phù hợp với cơ chế tải của Spring Boot. Đây không phải cách thay thế chung cho mọi bean; chỉ dùng cho tích hợp bootstrap hoặc thư viện thật sự cần gắn listener rất sớm.

Một số cơ chế đăng ký tự động khác của Spring Boot (như auto-configuration imports) có mục đích khác. Không nên đặt một listener khởi động sớm trong cấu hình auto-configuration rồi hy vọng nó sẽ nhận lại những event đã xảy ra trước lúc cấu hình được nạp.

## 8. Tình huống thực tế: đọc và điều chỉnh Environment sớm

`ApplicationEnvironmentPreparedEvent` là lúc có thể quan sát `ConfigurableEnvironment` nhưng context chưa được tạo. Ví dụ gắn một `PropertySource` ưu tiên cao:

~~~java
public final class ExtraPropertiesListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        Map<String, Object> values = Map.of(
                "feature.bootstrap-check", true);
        event.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("bootstrapOverrides", values));
    }
}
~~~

*Đây là đoạn tích hợp minh họa. Import `java.util.Map`, `ApplicationListener`, `ApplicationEnvironmentPreparedEvent` và `org.springframework.core.env.MapPropertySource`; đặt class vào ứng dụng và đăng ký bằng `app.addListeners(new ExtraPropertiesListener())` trước `run`.*

Cần cân nhắc kỹ khi chỉnh `Environment` ở pha này:

- Listener sẽ chạy trong bootstrap, thường trên đường đi đồng bộ của startup; code nặng làm chậm khởi động.
- `addFirst(...)` đưa property source lên đầu, có thể ghi đè giá trị từ file cấu hình, biến môi trường hoặc command-line theo độ ưu tiên của nguồn. Chỉ làm như vậy khi đó là ý đồ rõ ràng.
- Nếu yêu cầu tải cấu hình bên ngoài phức tạp, cân nhắc cơ chế cấu hình chuyên dụng như `EnvironmentPostProcessor` hoặc Config Data thay vì tự viết một listener quá nhiều trách nhiệm.
- Không đọc dữ liệu bí mật từ event rồi log ra console. Tránh phụ thuộc vào bean repositories/services vì context chưa được khởi tạo.

## 9. Xử lý lỗi khi khởi động: ApplicationFailedEvent

Một listener được thêm sớm có thể nhận `ApplicationFailedEvent` ngay cả khi context không được refresh thành công:

~~~java
app.addListeners((ApplicationListener<ApplicationFailedEvent>) event -> {
    Throwable cause = event.getException();
    System.err.println("Startup failed: " + cause.getClass().getName());

    // event.getApplicationContext() có thể null hoặc chưa hoàn thiện:
    // đừng giả định mọi bean đã sẵn sàng.
});
~~~

*Đây là mã minh họa trong phương thức `main` có biến `app` là `SpringApplication`.*

Các lưu ý:

- Đây là **thông báo thất bại trong startup**, không phải handler tổng quát cho mọi exception sau khi ứng dụng sẵn sàng.
- `ApplicationFailedEvent` có thể xảy ra khi context chưa tồn tại hoặc đã bị phá hủy một phần. Xử lý chẩn đoán bằng thông tin chắc chắn có sẵn, không yêu cầu gọi bean/service chưa khởi tạo.
- Lỗi ném ra **trong chính listener startup** có thể làm quá trình khởi động thất bại; không dùng listener sớm để thực hiện thao tác không an toàn hay trì hoãn lâu.
- Không dùng listener `ApplicationFailedEvent` để nuốt hoặc tự ý biến lỗi startup thành thành công; nguyên nhân cần được báo cáo/ghi log phù hợp.

## 10. Bẫy quan trọng: tính đồng bộ, thứ tự, context hierarchy

### 10.1. Listener mặc định chạy đồng bộ

`ApplicationListener.onApplicationEvent(...)` thường được gọi đồng bộ bởi cơ chế phát event mặc định. Một listener gọi HTTP lâu, `Thread.sleep(...)` hoặc chạy truy vấn nặng ở `ApplicationEnvironmentPreparedEvent` sẽ chặn đường khởi động. Với tác vụ có thể trì hoãn, chọn runner, lịch trình hoặc executor được quản lý đúng vòng đời sau khi context sẵn sàng.

### 10.2. Không dùng dependency injection quá sớm

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new NeedsRepositoryListener());
application.run(args);
~~~

Listener truyền bằng `new` không phải bean do Spring quản lý. Đặc biệt, ở sự kiện rất sớm **chưa có container** để inject `@Autowired OrderRepository` hoặc gọi service phụ thuộc vào bean. Hãy tách logic bootstrap độc lập, hoặc dời công việc cần DI sang event muộn/runner.

### 10.3. Một event có thể tới nhiều context

Trong ứng dụng tạo cây parent/child `ApplicationContext` (ví dụ một số cấu hình `SpringApplicationBuilder`), event được phát lên ancestor context theo quy tắc event multicasting của Spring. Vì vậy một listener có thể nhận event của nhiều context, hoặc thấy lặp lại event cùng loại trong những cấu hình phức tạp. Nếu cần chỉ xử lý cho một context, so sánh `event.getApplicationContext()` với context mong muốn ở những event có context, thay vì cho rằng mỗi ứng dụng chỉ có một context.

### 10.4. Đừng thêm listener quá muộn

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
ConfigurableApplicationContext context = application.run(args);
application.addListeners(new EarlyEnvironmentListener()); // Quá muộn!
~~~

Listener vừa thêm không thể nhận lại `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` đã phát trước đó. Nếu muốn lắng nghe event khi context đã chạy, dùng cơ chế phù hợp của chính context, và nhớ rằng các event lifecycle trước đó không được phát lại tự động.

### 10.5. Không đánh đồng Spring Boot event với Spring Framework event

`ApplicationStartedEvent`, `ApplicationReadyEvent` và `ApplicationFailedEvent` do Boot phát cho quá trình `SpringApplication` chạy. `ContextRefreshedEvent` và `ContextClosedEvent` thuộc vòng đời `ApplicationContext` của Spring Framework. Cả hai có thể được xử lý bởi `ApplicationListener` phù hợp, nhưng ý nghĩa/thời điểm không như nhau.

## 11. Chọn API theo nhu cầu

| Yêu cầu | Nên chọn | Lý do |
| --- | --- | --- |
| Bắt `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` | `SpringApplication.addListeners(...)` trước `run` | Không phụ thuộc context hoặc bean chưa tồn tại. |
| Viết thư viện muốn listener tự nhận event sớm ở mọi ứng dụng dùng thư viện | Đăng ký `ApplicationListener` trong `spring.factories` | Bootstrap tự nạp listener, không bắt người dùng sửa `main`. |
| Chỉ cần phản ứng khi app đã startup xong | `@EventListener(ApplicationReadyEvent.class)` hoặc bean `ApplicationListener` | Spring bean đã sẵn sàng, dùng DI dễ dàng. |
| Thực hiện công việc khởi tạo nghiệp vụ trước khi Boot báo Ready | `ApplicationRunner` / `CommandLineRunner` | Mốc dành riêng cho logic chạy sau refresh. |
| Quan sát/shutdown của `ApplicationContext` | `@EventListener(ContextClosedEvent.class)` hoặc `ApplicationListener<ContextClosedEvent>` | Đây là event của context, không phải mốc Boot “ready”. |
| Cấu hình tài nguyên trước khi context refresh | `ApplicationContextInitializer` hoặc tích hợp cấu hình phù hợp | Đúng giai đoạn và nhiệm vụ hơn listener dùng như callback cấu hình tổng quát. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao một bean `@EventListener` không nhận được `ApplicationStartingEvent`?

**Đáp án:** Event xảy ra trước khi `ApplicationContext` được tạo. Bean và hạ tầng đăng ký `@EventListener` chưa tồn tại ở thời điểm đó.

**Câu 2.** Muốn quan sát `ApplicationEnvironmentPreparedEvent` trong phương thức `main`, cần đăng ký lúc nào?

**Đáp án:** Tạo `SpringApplication`, gọi `app.addListeners(...)` với `ApplicationListener<ApplicationEnvironmentPreparedEvent>`, **sau đó** mới gọi `app.run(args)`.

**Câu 3.** `ApplicationStartedEvent` và `ApplicationReadyEvent` khác nhau ở điểm nào quan trọng nhất?

**Đáp án:** `Started` xảy ra sau context refresh nhưng **trước** các `ApplicationRunner`/`CommandLineRunner`; `Ready` xảy ra **sau** khi các runner chạy xong.

**Câu 4.** Có nên dùng `setListeners(...)` khi chỉ muốn gắn thêm một listener không?

**Đáp án:** Thông thường không. `setListeners` thiết lập tập listener và có thể thay thế cấu hình cũ. `addListeners` được thiết kế cho mục đích bổ sung.

**Câu 5.** Khi listener nhận `ApplicationFailedEvent`, có thể gọi repository bean như lúc ứng dụng đang chạy bình thường không?

**Đáp án:** Không thể giả định như vậy. Context có thể chưa khởi tạo hoặc chỉ khởi tạo dở dang; chỉ dùng các thông tin thực sự còn sẵn có để chẩn đoán.

**Câu 6.** Vì sao ví dụ ở phần 4 in `05 STARTED`, rồi `06 RUNNER`, rồi `07 READY`?

**Đáp án:** Đó là thứ tự vòng đời chuẩn của Spring Boot: context refresh → sự kiện Started → runner → sự kiện Ready.

## Tài liệu tham khảo

- [Spring Boot 3.5 Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): các event theo thứ tự và cách đăng ký listener trước khi context tồn tại.
- [Spring Boot 3.5.16 Javadoc — SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): `addListeners`, `setListeners`, `getListeners`, `run`.
- [Spring Boot 3.5.16 API — Application Event Classes](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/package-summary.html): các event lifecycle của `SpringApplication`.
- [Spring Framework Javadoc — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html): giao diện `onApplicationEvent`.
- [Spring Boot 3.5 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): xử lý và ưu tiên các nguồn cấu hình `Environment`.
