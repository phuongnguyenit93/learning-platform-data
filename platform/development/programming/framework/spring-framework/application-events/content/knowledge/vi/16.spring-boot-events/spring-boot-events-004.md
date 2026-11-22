# ApplicationContextInitializedEvent trong Spring Boot

`ApplicationContextInitializedEvent` là một **sự kiện khởi động sớm** của Spring Boot, thuộc nhóm `SpringApplicationEvent`. Spring Boot phát sự kiện này khi `ApplicationContext` đã được tạo và chuẩn bị, các `ApplicationContextInitializer` đã được gọi, **nhưng Spring Boot chưa nạp các bean definitions từ nguồn ứng dụng chính**.

Nó trả lời câu hỏi: **“Spring đã tạo và cấu hình sơ bộ context xong chưa, trước khi bắt đầu nạp định nghĩa bean của ứng dụng?”** Sự kiện này không có nghĩa là dependency injection đã hoàn tất, bean đã sẵn sàng, web server đã chạy hoặc ứng dụng đã nhận request được.

Đây là sự kiện của **Spring Boot**, với kiểu đầy đủ `org.springframework.boot.context.event.ApplicationContextInitializedEvent`. Nó khác các sự kiện vòng đời `ApplicationContext` thuần Spring Framework như `ContextRefreshedEvent`.

## 1. Vị trí chính xác trong quá trình khởi động

Đường đi tiêu biểu khi gọi `SpringApplication.run(...)`:

```text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  |     (bắt đầu; Environment và ApplicationContext chưa được chuẩn bị)
  |
  +-- Tạo/chuẩn bị Environment
  +-- ApplicationEnvironmentPreparedEvent
  |     (Environment đã có; ApplicationContext chưa được tạo)
  |
  +-- Tạo ApplicationContext
  +-- Gán Environment và chuẩn bị context
  +-- Gọi các ApplicationContextInitializer
  |
  +-- ApplicationContextInitializedEvent  <-- CHỦ ĐỀ BÀI NÀY
  |     (context đã khởi tạo sơ bộ; chưa load bean definitions ứng dụng)
  |
  +-- Nạp bean definitions từ nguồn cấu hình / ứng dụng
  +-- ApplicationPreparedEvent
  |     (đã load bean definitions, chưa refresh)
  |
  +-- Refresh ApplicationContext
  |     (xử lý các bean definitions, tạo các singleton cần thiết...)
  +-- ApplicationStartedEvent
  |     (refresh xong; chưa chạy ApplicationRunner / CommandLineRunner)
  |
  +-- Chạy ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
        (ứng dụng được coi là sẵn sàng nhận yêu cầu)
```

Các mốc có thể kèm thêm sự kiện nội bộ, trạng thái availability và sự kiện riêng của web server. Sơ đồ tập trung vào những mốc quan trọng để phân biệt thời điểm sử dụng.

| Sự kiện | Context đã tồn tại? | Định nghĩa bean từ nguồn ứng dụng đã được nạp? | Context đã refresh? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Chưa | Chưa | Chưa |
| `ApplicationEnvironmentPreparedEvent` | Chưa | Chưa | Chưa |
| **`ApplicationContextInitializedEvent`** | **Có** | **Chưa** | **Chưa** |
| `ApplicationPreparedEvent` | Có | Có | Chưa |
| `ApplicationStartedEvent` | Có | Có | Có |
| `ApplicationReadyEvent` | Có | Có | Có |

Cụm “chưa nạp bean definitions” ở đây nói về giai đoạn Spring Boot **chưa load các nguồn bean definitions thông thường của ứng dụng**. Không nên viết test theo giả định `getBeanDefinitionCount() == 0`: các bước chuẩn bị, initializer hoặc custom infrastructure vẫn có thể đăng ký một số định nghĩa trước thời điểm này.

## 2. Nội dung và API quan trọng của event

Kiểu `ApplicationContextInitializedEvent` kế thừa `SpringApplicationEvent` và cung cấp:

- `getApplicationContext()`: trả về `ConfigurableApplicationContext` đã được tạo và khởi tạo sơ bộ.
- `getSpringApplication()` (kế thừa): trả về `SpringApplication` đang thực hiện quá trình khởi động.
- `getArgs()` (kế thừa): trả về tham số dòng lệnh ban đầu dùng để khởi động.

Constructor được Spring Boot dùng có dạng:

```java
public ApplicationContextInitializedEvent(
        SpringApplication application,
        String[] args,
        ConfigurableApplicationContext context);
```

Đây là **chữ ký API minh họa**, không phải lệnh cần tạo event thủ công. Trong ứng dụng thông thường, Spring Boot chịu trách nhiệm phát sự kiện.

Ở giai đoạn này, listener có thể quan sát:

```java
ConfigurableApplicationContext context = event.getApplicationContext();
String appName = context.getEnvironment()
        .getProperty("spring.application.name");
boolean refreshed = context.isActive();
```

Đây là **đoạn mã minh họa**, giả định biến `event` được khai báo trong một listener đúng loại. `Environment` đã được gắn vào context, nên việc đọc các property đã chuẩn bị là hợp lý. `context.isActive()` thông thường vẫn là `false` ở mốc này, vì thao tác `refresh()` chưa diễn ra. Tuy nhiên, không nên cố sử dụng `context.getBean(...)` cho bean nghiệp vụ chưa được định nghĩa/tạo.

Một `ApplicationContextInitializer` là phần được **chạy trước** event. Nếu initializer thêm `PropertySource`, listener `ApplicationContextInitializedEvent` có thể thấy thay đổi đó. Đây là mối liên hệ hữu ích nhất giữa hai cơ chế.

## 3. Cách đăng ký listener để không bỏ lỡ sự kiện sớm

Vì event phát **trước khi Spring Boot load định nghĩa bean từ ứng dụng**, listener dựa trên bean do `@Component`, `@Bean` hoặc `@EventListener` tạo ra **thường chưa tồn tại để nhận event**. Cách phù hợp là đăng ký listener trực tiếp với `SpringApplication` **trước khi gọi `run()`**.

### 3.1. Đăng ký trực tiếp với `SpringApplication.addListeners(...)`

```java
SpringApplication app = new SpringApplication(MyBootApplication.class);
app.addListeners(new MyEarlyListener());
app.run(args);
```

`MyEarlyListener` phải triển khai `ApplicationListener<ApplicationContextInitializedEvent>`. Spring Boot thu nhận listener này trước khi bắt đầu chạy, nên nó có cơ hội nhận được các sự kiện khởi động sớm, trong đó có `ApplicationContextInitializedEvent`.

### 3.2. Dùng `SpringApplicationBuilder.listeners(...)`

```java
new SpringApplicationBuilder(MyBootApplication.class)
        .listeners(new MyEarlyListener())
        .run(args);
```

Đây là cách tương đương khi ứng dụng khởi động qua builder, thường hữu ích cho tùy chỉnh `SpringApplication` hoặc xây dựng context hierarchy.

### 3.3. Tự động đăng ký từ `META-INF/spring.factories`

Nếu tạo thư viện cần nhận event khởi động từ nhiều ứng dụng, có thể khai báo listener vào file:

```text
src/main/resources/META-INF/spring.factories
```

Ví dụ nội dung:

```properties
org.springframework.context.ApplicationListener=example.boot.events.MyEarlyListener
```

`example.boot.events.MyEarlyListener` ở đây là **tên lớp minh họa**; hãy thay bằng tên lớp thật có constructor phù hợp. Spring Boot có thể tải listener khai báo ở đây ngay từ giai đoạn xây dựng `SpringApplication`. Đây là cơ chế đăng ký early listener được Spring Boot tài liệu hóa; không nhầm nó với cơ chế import auto-configuration.

Nếu listener chỉ dành cho một ứng dụng, `addListeners(...)` thường đơn giản và dễ kiểm soát hơn.

### 3.4. Vì sao `@EventListener` trong `@Component` có thể không nhận?

Mã sau có thể trông hợp lý nhưng không phải cách phù hợp để theo dõi event sớm:

```java
@Component
class TooLateListener {
    @EventListener
    void initialized(ApplicationContextInitializedEvent event) {
        System.out.println("Context initialized");
    }
}
```

Đây là **đoạn mã minh họa**. `@EventListener` được xử lý trong vòng đời bean/context. Khi `ApplicationContextInitializedEvent` được phát, Spring Boot **chưa load cấu hình bean ứng dụng**, nên `TooLateListener` thường chưa được đăng ký làm listener cho sự kiện đó. Không nên diễn giải việc không thấy log là “Spring Boot không phát event”.

Lựa chọn đúng là tạo `ApplicationListener` độc lập và đăng ký sớm, hoặc chuyển sang sự kiện muộn hơn nếu logic cần bean đã khởi tạo.

## 4. Ví dụ Java 17+ có thể chạy: initializer chạy trước event

Ví dụ Spring Boot không có web server, tránh phụ thuộc database và không cần Spring MVC. Chương trình cố tình in các dòng đánh dấu ở thời điểm initializer/event và sau khi `run()` hoàn tất.

Cấu trúc dự án Maven:

```text
context-initialized-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── boot/
                    └── events/
                        └── ContextInitializedDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>context-initialized-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.boot.events.ContextInitializedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/boot/events/ContextInitializedDemo.java`:

```java
package example.boot.events;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication(proxyBeanMethods = false)
public class ContextInitializedDemo {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextInitializedDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
                context -> {
                    context.getEnvironment().getPropertySources().addFirst(
                            new MapPropertySource(
                                    "demo-initializer",
                                    Map.of("demo.stage", "initializer-ran")));
                    System.out.println("initializer: property added");
                };
        app.addInitializers(initializer);

        // Đăng ký trước run(), không đợi bean scanning.
        app.addListeners(new EarlyContextListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("after-run: active=" + context.isActive());
            System.out.println("after-run: property=" +
                    context.getEnvironment().getProperty("demo.stage"));
        }
    }

    public static final class EarlyContextListener
            implements ApplicationListener<ApplicationContextInitializedEvent> {

        @Override
        public void onApplicationEvent(ApplicationContextInitializedEvent event) {
            ConfigurableApplicationContext context = event.getApplicationContext();

            System.out.println("initialized: property=" +
                    context.getEnvironment().getProperty("demo.stage"));
            System.out.println("initialized: active=" + context.isActive());
        }
    }
}
```

Trong thư mục `context-initialized-demo`, chạy (cần JDK 17+, Maven và khả năng tải dependencies ở lần chạy đầu):

```bash
mvn -q compile exec:java
```

Các **dòng do chính chương trình in**, theo đúng thứ tự (bỏ qua log có thể xuất hiện từ Spring/SLF4J/Maven):

```text
initializer: property added
initialized: property=initializer-ran
initialized: active=false
after-run: active=true
after-run: property=initializer-ran
```

Phân tích:

1. `app.addInitializers(initializer)` thiết lập một `ApplicationContextInitializer` thêm property `demo.stage`. Khi Spring Boot gọi initializer, chương trình in dòng đầu tiên.
2. Ngay sau giai đoạn initializer, Spring Boot phát `ApplicationContextInitializedEvent`. `EarlyContextListener` đã được đăng ký qua `addListeners(...)` nên được gọi; nó đọc thấy `demo.stage=initializer-ran`.
3. `initialized: active=false` cho thấy context chưa được refresh tại thời điểm listener chạy. Nó đã có đối tượng context nhưng bean nghiệp vụ chưa ở trạng thái sẵn sàng.
4. Khi `app.run(args)` hoàn tất, context đã refresh; `after-run: active=true`. Property do initializer thêm vẫn truy cập được.

Ví dụ sử dụng lớp listener tĩnh triển khai interface với **kiểu event cụ thể**. Cách này giúp Spring nhận biết loại event cần lắng nghe và tránh vô tình xử lý các sự kiện khởi động khác không liên quan. Lớp listener không cần `@Component`.

## 5. `ApplicationContextInitializer` và `ApplicationContextInitializedEvent` khác nhau như thế nào?

Tên gần giống nhau nhưng vai trò khác biệt:

| Thành phần | Bản chất | Thời điểm | Dùng để |
| --- | --- | --- | --- |
| `ApplicationContextInitializer<ConfigurableApplicationContext>` | Callback cấu hình context | Được Spring Boot gọi khi chuẩn bị context | Chủ động thay đổi context sớm theo hợp đồng initializer |
| `ApplicationContextInitializedEvent` | Event báo mốc khởi tạo sơ bộ | **Sau** khi gọi initializers, trước khi load bean definitions từ ứng dụng | Quan sát, kiểm tra, ghi nhận thông tin sau bước initializer |
| `ApplicationPreparedEvent` | Event khởi động muộn hơn | Sau khi load bean definitions, trước refresh | Quan sát giai đoạn đã load definitions nhưng chưa instantiate đầy đủ |
| `ApplicationReadyEvent` | Event gần cuối startup | Sau refresh và các runner | Khởi chạy việc thực sự cần ứng dụng sẵn sàng |

**Khi cần chỉnh cấu hình context trước bước load bean**, `ApplicationContextInitializer` thường thể hiện ý định rõ nhất. Dù event listener có thể truy cập `ConfigurableApplicationContext`, không nên biến listener thành nơi thực hiện nhiều thao tác chỉnh sửa nội bộ khó kiểm soát.

Ví dụ cần kiểm tra một property do initializer vừa thêm thì `ApplicationContextInitializedEvent` rất phù hợp. Nếu muốn đăng ký bean definition chuyên biệt trước refresh, hãy cân nhắc API extension chính thức như `ApplicationContextInitializer`, `BeanDefinitionRegistryPostProcessor` hoặc auto-configuration phù hợp với loại tùy chỉnh; đừng dựa vào thứ tự tình cờ giữa các listener.

Nếu cần chạy logic phụ thuộc `@Autowired` service, database migration hoàn tất, hoặc endpoint bắt đầu phục vụ, hãy chọn một mốc muộn hơn như `ApplicationRunner`/`CommandLineRunner` hoặc `ApplicationReadyEvent` tùy nhu cầu. Event sớm không bảo đảm những dependency đó đã tồn tại.

## 6. Khi nào nên áp dụng?

Một số mục đích có giá trị của `ApplicationContextInitializedEvent`:

- **Kiểm tra trạng thái chuẩn bị context:** xác nhận initializer đã gắn một số property, profile hoặc marker như mong đợi.
- **Ghi log chẩn đoán startup sớm:** in context ID, loại context, tên ứng dụng hoặc property an toàn giúp tìm lỗi cấu hình trước bước refresh.
- **Ghi nhận mốc khởi động:** đo/chú thích một thời điểm trong startup lifecycle, miễn là callback đủ nhẹ và không dùng bean ứng dụng chưa sẵn sàng.
- **Phát hiện custom initializer đã có hiệu lực:** tách phần thay đổi context (initializer) và phần quan sát (listener).

Ví dụ đọc thông tin không phụ thuộc bean:

```java
@Override
public void onApplicationEvent(ApplicationContextInitializedEvent event) {
    ConfigurableApplicationContext context = event.getApplicationContext();

    String name = context.getEnvironment()
            .getProperty("spring.application.name", "(unnamed)");
    System.out.println("initializing: " + name);
}
```

Đây là **đoạn phương thức minh họa** đặt trong lớp triển khai `ApplicationListener<ApplicationContextInitializedEvent>`. Việc đọc property và in log là an toàn ở mức hợp đồng lifecycle. Không nên in password/token hoặc nội dung bí mật của `Environment` vào log.

## 7. Những giới hạn và lỗi thường gặp

### 7.1. Hiểu nhầm “initialized” là “refreshed” hoặc “ready”

Tên event chứa “Initialized”, nhưng đây **không phải** `ApplicationStartedEvent` và cũng không phải `ApplicationReadyEvent`. Ở thời điểm này, Spring Boot chưa load source bean definitions và chưa refresh context. Các bean từ `@Configuration`, `@ComponentScan` hoặc auto-configuration chưa được khởi tạo như khi ứng dụng đã chạy.

Nếu gọi `context.getBean(OrderService.class)` tại đây, có thể gặp `NoSuchBeanDefinitionException` hoặc lỗi do cố truy cập bean quá sớm. Không dựa vào sự hiện diện của một số bean infrastructure để kết luận toàn bộ ứng dụng đã sẵn sàng.

### 7.2. Đăng ký listener quá muộn

`@Component` chứa `@EventListener` chỉ được xử lý khi ứng dụng load/refresh bean definitions; vì vậy không phù hợp để bắt sự kiện rất sớm này.

Cách khắc phục: đăng ký một instance `ApplicationListener<ApplicationContextInitializedEvent>` bằng `SpringApplication.addListeners(...)` trước `run()`, qua `SpringApplicationBuilder.listeners(...)` hoặc qua `META-INF/spring.factories`.

### 7.3. Gây chậm hoặc làm thất bại startup

Các early listener thường chạy đồng bộ trong luồng khởi động. Tác vụ lâu, chờ network, truy cập file lớn hoặc vòng lặp chờ trong listener có thể làm startup kéo dài. Exception không được xử lý có thể làm `SpringApplication.run(...)` thất bại và dẫn đến xử lý `ApplicationFailedEvent`. Chỉ nên thực hiện thao tác ngắn, tất định, không phụ thuộc vào hệ thống chưa khởi tạo.

### 7.4. Nhầm thời điểm đọc `Environment`

Ở `ApplicationContextInitializedEvent`, `Environment` đã được chuẩn bị và gắn vào context. Nếu chỉ muốn can thiệp `Environment` trước khi context được tạo, `ApplicationEnvironmentPreparedEvent` là mốc sớm hơn. Nếu muốn kiểm tra giá trị được thêm bởi `ApplicationContextInitializer`, hãy dùng sự kiện initialized này.

### 7.5. Đếm bean definitions để suy ra toàn bộ lifecycle

Mô tả chính thức nói Spring Boot chưa load bean definitions từ nguồn ứng dụng, **không có nghĩa mọi registry ở thời điểm này luôn trống tuyệt đối**. Initializer hoặc một phần infrastructure có thể đăng ký bean definitions trước. Do đó, một phép kiểm tra `getBeanDefinitionCount()` có thể phụ thuộc cấu hình cụ thể và không phải điều kiện đúng/sai của event.

### 7.6. Nhận nhiều lần khi có context hierarchy

Nếu ứng dụng dùng nhiều `SpringApplication` hoặc cấu trúc parent/child context, một listener có thể nhận nhiều event cùng loại đến từ các context khác nhau. Đừng giả định một lần nhận event luôn tương đương một lần JVM khởi động. Có thể kiểm tra `event.getApplicationContext()`, context ID hoặc nguồn khởi động để phân biệt và tránh chạy tác vụ trùng.

### 7.7. Nhầm `ApplicationContextInitializedEvent` với sự kiện Spring Framework

`ContextRefreshedEvent` xuất hiện khi `ApplicationContext` đã refresh, có thể phát lại khi context refresh nhiều lần. `ApplicationContextInitializedEvent` là mốc **Spring Boot startup sớm**; nó không được phát chỉ vì một code tùy ý tạo và refresh một `AnnotationConfigApplicationContext` độc lập, không dùng `SpringApplication`.

### 7.8. Phụ thuộc vào thứ tự listener không được nêu rõ

Nếu nhiều early listener độc lập và cần thứ tự thực thi, phải xem xét cơ chế `Ordered` hoặc `@Order` của Spring ở nơi thích hợp; không nên dựa vào thứ tự tên lớp hoặc hành vi tình cờ. Khi một callback cần dữ liệu mà initializer tạo ra, nên đặt trách nhiệm cấu hình vào initializer, vì lifecycle đã bảo đảm **initializers chạy trước `ApplicationContextInitializedEvent`**.

## 8. Kiểm thử event đúng cách

Nên kiểm thử ở hai mức:

**Đơn vị:** tạo một `ApplicationContextInitializedEvent` giả lập với `SpringApplication` và `ConfigurableApplicationContext` để kiểm tra listener đọc property, ghi log hoặc cập nhật bộ đếm đúng. Cách này chỉ kiểm tra **logic listener**, chưa chứng minh Boot phát event tại thời điểm chính xác.

**Tích hợp startup:** khởi động `SpringApplication` nhỏ như ví dụ, đăng ký initializer và listener trước `run()`, rồi kiểm tra thứ tự:

1. Initializer chạy trước và tạo marker.
2. Listener nhận marker sau khi initializer chạy.
3. Ở event initialized, context chưa refresh.
4. Sau `run()`, context active và property vẫn tồn tại.

Nếu test bằng JUnit, có thể lưu các marker vào một danh sách rồi so sánh thứ tự thay cho khẳng định dựa trên log. Không cần `Thread.sleep(...)` vì các callback startup ví dụ ở đây được gọi đồng bộ.

Có thể tạo một lớp listener chỉ đếm `ApplicationContextInitializedEvent` để kiểm chứng rằng event được phát đúng **một lần cho một context/chu kỳ chạy** trong mẫu ứng dụng đơn giản. Với ứng dụng có context hierarchy, điều kiện “đúng một lần toàn ứng dụng” không còn phổ quát.

## 9. Tự đánh giá

1. **Khi listener nhận `ApplicationContextInitializedEvent`, có thể gọi bean nghiệp vụ bằng `context.getBean(...)` không?** Không nên, vì Spring Boot chưa load định nghĩa bean của ứng dụng và context chưa refresh.
2. **`ApplicationContextInitializer` chạy trước hay sau event?** Chạy **trước**. Event báo rằng giai đoạn initializer đã hoàn tất.
3. **Có thể dùng `@Component` với `@EventListener` để nhận chắc chắn event này không?** Không. Bean được đăng ký từ nguồn ứng dụng thường được xử lý muộn hơn.
4. **Muốn nhận event này nên đăng ký listener ở đâu?** Qua `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, hoặc `META-INF/spring.factories`.
5. **Sự kiện initialized có nghĩa là web server đã sẵn sàng không?** Không. Hãy xem các mốc sau refresh và `ApplicationReadyEvent` nếu cần biết ứng dụng sẵn sàng phục vụ.

## 10. Tài liệu tham khảo

- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.3 Javadoc — ApplicationContextInitializedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot Reference — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html#howto.application.customize-the-environment-or-application-context)
- [Spring Framework Javadoc — ApplicationContextInitializer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
