# ApplicationEnvironmentPreparedEvent khi Environment đã được chuẩn bị trong Spring Boot

## 1. Sự kiện này báo hiệu điều gì?

**ApplicationEnvironmentPreparedEvent** là sự kiện thuộc quá trình khởi động **SpringApplication**. Spring Boot phát sự kiện khi **Environment sẽ dùng cho ứng dụng đã tồn tại và có thể được đọc/chỉnh sửa, nhưng ApplicationContext chưa được tạo**.

Đây là một mốc bootstrap sớm, không phải sự kiện báo ứng dụng đã chạy xong. Người viết listener có thể đọc các nguồn thuộc tính đã có ở thời điểm listener được gọi, kiểm tra một số giá trị cấu hình, hoặc thêm **PropertySource** nếu thật sự cần. Tuy nhiên, **không được giả định mọi bean đã được tạo**: thậm chí context cũng chưa tồn tại tại mốc này.

Trong Spring Boot 3.3.x:

- Lớp sự kiện: **org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent**.
- Kiểu cha: **SpringApplicationEvent**.
- **getEnvironment()** trả về **ConfigurableEnvironment** của lần khởi động đang diễn ra.
- Các API kế thừa gồm **getSpringApplication()** và **getArgs()**.
- **getBootstrapContext()** cung cấp **ConfigurableBootstrapContext** cho nhu cầu chia sẻ tài nguyên bootstrap nâng cao.

**Từ “prepared” cần hiểu đúng:** SpringApplication đã tạo và cấu hình Environment ban đầu để phát sự kiện; **một số EnvironmentPostProcessor tiếp tục bổ sung/biến đổi nguồn cấu hình ngay trong quá trình dispatch sự kiện**. Vì vậy việc một listener có nhìn thấy nội dung Config Data hay chưa còn phụ thuộc **thứ tự listener**. Không nên khẳng định mọi cấu hình đã hoàn tất ở thời điểm *bắt đầu* phát sự kiện.

Bài sử dụng mốc **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**. Khi chuyển sang nhánh framework khác, cần đối chiếu API và cơ chế đăng ký listener tương ứng.

## 2. Vị trí trong chuỗi sự kiện khởi động

Một lần Spring Boot startup thành công có trình tự khái quát:

~~~text
main() gọi SpringApplication.run(...)
    |
    +-- ApplicationStartingEvent
    |
    +-- SpringApplication tạo/chuẩn bị Environment
    |      |
    |      +-- ApplicationEnvironmentPreparedEvent  <--- BÀI NÀY
    |      |      +-- listener xử lý Environment
    |      |      +-- EnvironmentPostProcessor có thể chạy
    |      |      +-- Config Data có thể được nạp tại đây
    |      |
    |      +-- bind các thuộc tính spring.main.* thích hợp
    |
    +-- In banner (nếu bật)
    +-- Tạo ApplicationContext
    +-- Áp dụng ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent
    +-- Nạp bean definitions / sources
    +-- ApplicationPreparedEvent
    |
    +-- ApplicationContext.refresh()
    |      +-- BeanFactoryPostProcessor
    |      +-- BeanPostProcessor
    |      +-- Khởi tạo các singleton thông thường
    |      +-- Web server (nếu có) được khởi tạo/start
    |
    +-- ApplicationStartedEvent
    +-- AvailabilityChangeEvent (LivenessState.CORRECT)
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)
    +-- SpringApplication.run(...) trả về context
~~~

Đây là sơ đồ tóm lược, không liệt kê mọi bước trong **SpringApplication.prepareEnvironment**, **refresh** hoặc xử lý Config Data. Khi startup thất bại, Boot có thể phát **ApplicationFailedEvent** thay vì đi hết các mốc thành công.

### 2.1. So sánh với những sự kiện dễ nhầm

| Sự kiện | Context đã được tạo? | Ý nghĩa |
| --- | --- | --- |
| **ApplicationStartingEvent** | Chưa | Bắt đầu lần chạy, trước phần lớn hoạt động chuẩn bị |
| **ApplicationEnvironmentPreparedEvent** | **Chưa** | Environment đã có để các listener sớm đọc/chỉnh |
| **ApplicationContextInitializedEvent** | Có, chưa nạp các bean definitions ứng dụng | Các ApplicationContextInitializer đã được gọi |
| **ApplicationPreparedEvent** | Có, đã nạp nguồn cấu hình/bean definitions, chưa refresh | Chuẩn bị gọi refresh |
| **ApplicationStartedEvent** | Có, đã refresh | Trước ApplicationRunner/CommandLineRunner |
| **ApplicationReadyEvent** | Có, đã chạy các runner | Mốc ứng dụng đã hoàn tất chuỗi startup thông thường |
| **ApplicationFailedEvent** | Có thể có hoặc chưa có | Lỗi khi startup; tùy lỗi xuất hiện ở pha nào |

Như vậy, **EnvironmentPrepared** không có nghĩa **ContextPrepared**, cũng không có nghĩa web server đã mở cổng hoặc ứng dụng sẵn sàng nhận traffic.

**Không dùng ApplicationEnvironmentPreparedEvent để lấy một @Service hay @Repository.** Tại thời điểm sự kiện này được gửi, SpringApplication còn chưa tạo ApplicationContext để chứa các bean đó.

## 3. Environment gồm những gì và có thể thao tác ra sao?

**Environment** là abstraction để đọc thuộc tính theo tên, xác định active profiles và quản lý các nguồn cấu hình. Với **ConfigurableEnvironment**, ứng dụng có thể thao tác trên:

- **PropertySources**: tập hợp các nguồn như Java system properties, OS environment variables, command-line arguments và Config Data (khi đã nạp).
- **getProperty("key")**: đọc giá trị thuộc tính theo thứ tự ưu tiên các nguồn đã có.
- **getRequiredProperty("key")**: yêu cầu phải có thuộc tính; nếu vắng mặt, việc đọc ném exception.
- **getActiveProfiles()**: xem các profile hiện được active trong Environment ở thời điểm đọc.
- **getPropertySources().addFirst/addLast/addBefore/addAfter(...)**: chèn nguồn cấu hình với vị trí ưu tiên có chủ đích.

Ví dụ về việc đọc và thêm nguồn mặc định trong một listener:

~~~java
ConfigurableEnvironment environment = event.getEnvironment();
String mode = environment.getProperty("demo.mode", "standard");

if (!environment.getPropertySources().contains("demo-defaults")) {
    environment.getPropertySources().addLast(
        new MapPropertySource(
            "demo-defaults",
            Map.of("demo.greeting", "Hello from defaults")));
}
~~~

Đây là **snippet bên trong callback**, giả định có các import **ConfigurableEnvironment**, **MapPropertySource**, **Map**, và biến **event** là một **ApplicationEnvironmentPreparedEvent**. **addLast** đặt PropertySource ở mức ưu tiên thấp hơn các nguồn hiện hữu: cấu hình người vận hành có thể thắng fallback này.

### 3.1. PropertySources và thứ tự ưu tiên

**MutablePropertySources** duyệt các nguồn theo thứ tự. Với cùng khóa, nguồn có ưu tiên cao hơn thường thắng trong **Environment.getProperty(...)**:

~~~text
Nguồn ưu tiên cao
    -> "demo.greeting" = "set by CLI"
    -> "demo.greeting" = "set in application.properties"
    -> "demo.greeting" = "fallback" (addLast)
Nguồn ưu tiên thấp
~~~

Kết quả là giá trị ở nguồn cao nhất có khóa phù hợp, trong ví dụ trên là **set by CLI**. Spring Boot có nhiều quy tắc thứ tự khác cho từng loại nguồn và môi trường chạy; khi debug cần nhìn **nguồn thực tế** chứ không chỉ nhìn file application.properties.

Không nên dùng **addFirst(...)** để áp đặt giá trị mặc định, vì thao tác này có thể vô tình ghi đè CLI, secrets hoặc cấu hình production. **addFirst(...)** chỉ phù hợp khi yêu cầu thiết kế thật sự là ưu tiên một nguồn mới lên trên các nguồn khác, và phải hiểu hệ quả.

### 3.2. Active profiles và Config Data

**spring.profiles.active** và các cấu hình theo profile ảnh hưởng nguồn Config Data được nạp. Nhưng việc đọc **getActiveProfiles()** trong một listener chạy rất sớm có thể xảy ra **trước hoặc sau** các EnvironmentPostProcessor chịu trách nhiệm xử lý Config Data.

Nếu listener cần quan sát profile cuối của cấu hình chuẩn, hãy bảo đảm listener chạy **sau** bộ xử lý Config Data ở trình tự startup đang dùng. Nếu cần quyết định *cách* tìm và nạp Config Data, nên chọn cơ chế bootstrap dành riêng cho Config Data thay vì chèn tùy tiện một PropertySource sau khi việc nạp đã diễn ra.

### 3.3. Một số API trên sự kiện

~~~java
ConfigurableEnvironment env = event.getEnvironment();
SpringApplication application = event.getSpringApplication();
String[] arguments = event.getArgs();
ConfigurableBootstrapContext bootstrap = event.getBootstrapContext();
~~~

**getEnvironment()** là API sử dụng thường xuyên nhất. **getArgs()** trả về các đối số truyền vào SpringApplication; không dùng việc in toàn bộ đối số làm log mặc định vì chúng có thể chứa dữ liệu nhạy cảm. **getBootstrapContext()** phục vụ những trường hợp cần chia sẻ đối tượng trong pha bootstrap và phải tuân theo vòng đời bootstrap context.

**Không có ApplicationContext sẵn trên sự kiện này.** Nếu bài toán của bạn cần **ConfigurableApplicationContext**, hãy chuyển sang **ApplicationContextInitializer** hoặc một mốc muộn hơn.

## 4. Chi tiết quan trọng: event được phát trong lúc các processor còn hoạt động

Đây là điểm dễ hiểu nhầm nhất về tên **ApplicationEnvironmentPreparedEvent**.

Trong Spring Boot 3.3, SpringApplication chuẩn bị Environment rồi phát sự kiện. Spring Boot cũng có **EnvironmentPostProcessorApplicationListener**: listener hạ tầng này phản ứng với sự kiện sớm và kích hoạt các **EnvironmentPostProcessor** đăng ký qua **META-INF/spring.factories**.

Một processor quan trọng là **ConfigDataEnvironmentPostProcessor**, chịu trách nhiệm **nạp và áp dụng Config Data** vào Environment: **application.properties**, **application.yaml**, cấu hình theo profile, import và các nguồn cấu hình được hỗ trợ.

Dòng xử lý giản lược:

~~~text
SpringApplication.prepareEnvironment(...)
    |
    +-- Tạo/lấy ConfigurableEnvironment
    +-- Thêm các nguồn sớm: arguments, system, env...
    |
    +-- Publish ApplicationEnvironmentPreparedEvent
           |
           +-- EnvironmentPostProcessorApplicationListener
           |      +-- ConfigDataEnvironmentPostProcessor
           |      +-- các EnvironmentPostProcessor khác
           |
           +-- Các listener được đăng ký bởi ứng dụng
                  +-- đọc/chỉnh Environment
    |
    +-- SpringApplication tiếp tục hoàn tất prepareEnvironment(...)
    +-- bind spring.main.* từ Environment
    +-- tạo ApplicationContext ở bước tiếp theo
~~~

**Thứ tự hai nhánh listener trong sơ đồ không phải lời hứa tuyệt đối đối với mọi listener tùy chỉnh.** Spring sắp xếp dựa vào **Ordered/@Order**, cùng các cơ chế đăng ký có liên quan. Nếu một listener tùy chỉnh chạy trước **EnvironmentPostProcessorApplicationListener**, nó **không nên kỳ vọng** thấy mọi giá trị từ application.properties. Nếu chạy sau bộ xử lý này ở cấu hình thông thường, nó có thể đọc Config Data đã nạp.

Điều này lý giải vì sao cùng một lớp listener, việc thay **@Order** hoặc triển khai **Ordered** có thể làm giá trị **getProperty(...)** khác nhau.

### 4.1. Chọn order cho listener muốn đọc Config Data

Với mục tiêu **quan sát** cấu hình đã được Boot nạp, có thể cho listener mức ưu tiên thấp, chẳng hạn:

~~~java
@Override
public int getOrder() {
    return Ordered.LOWEST_PRECEDENCE;
}
~~~

Trong một ứng dụng Boot 3.3 thông thường, thứ tự này đặt listener tùy chỉnh sau listener xử lý EnvironmentPostProcessor mặc định. Khi đó việc đọc **application.properties** ở callback sẽ có kết quả đáng tin hơn.

Tuy nhiên, **LOWEST_PRECEDENCE không có nghĩa “mọi việc trong Environment đã xong mãi mãi”**. Một listener khác có cùng mức ưu tiên hoặc chạy muộn hơn vẫn có thể chỉnh Environment; ngoài ra SpringApplication còn tiếp tục các bước khác sau khi sự kiện kết thúc.

### 4.2. Khi nên viết EnvironmentPostProcessor thay vì event listener?

Nếu mục đích chính là **đưa thêm nguồn thuộc tính vào Environment**, đặc biệt muốn điều khiển thứ tự so với **ConfigDataEnvironmentPostProcessor**, hãy cân nhắc **EnvironmentPostProcessor**. Interface này thiết kế trực tiếp cho việc chỉnh Environment trước refresh và hỗ trợ **Ordered**.

Một listener **ApplicationEnvironmentPreparedEvent** thích hợp khi muốn **quan sát mốc sự kiện** hoặc thực hiện điều chỉnh nhỏ, rõ ràng, có thể đảm bảo thứ tự. Một **EnvironmentPostProcessor** thường dễ diễn đạt hơn khi yêu cầu thuộc loại **xử lý cấu hình bootstrap**.

Đừng dùng listener chạy muộn rồi cho rằng nó có thể thay đổi được quyết định nạp file cấu hình đã xảy ra trước đó.

## 5. Đăng ký listener đúng cách: phải có mặt trước khi event được phát

Spring Boot phát **ApplicationEnvironmentPreparedEvent trước khi ApplicationContext tồn tại**, nên **không thể dựa vào bean discovery thông thường** để nhận sự kiện của chính lần khởi động ấy.

### 5.1. Cách trực tiếp: SpringApplication.addListeners(...)

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyPreparedEnvironmentListener());
app.run(args);
~~~

Trong snippet này, **MyApplication** và **MyPreparedEnvironmentListener** là lớp đã được định nghĩa trong dự án. **addListeners(...)** phải được gọi **trước run(args)**. Đây là cách minh bạch khi bạn kiểm soát phương thức **main**.

Có thể đăng ký bằng **SpringApplicationBuilder.listeners(...)** nếu dự án dùng builder và hierarchy các context.

### 5.2. Cách tự động: META-INF/spring.factories

Nếu viết thư viện tích hợp cần listener được nạp dù ứng dụng gọi SpringApplication theo cách nào, Spring Boot 3.3 hỗ trợ đăng ký listener qua:

**src/main/resources/META-INF/spring.factories**

~~~properties
org.springframework.context.ApplicationListener=\
com.example.runtime.MyPreparedEnvironmentListener
~~~

Lớp được nêu phải là một **ApplicationListener** hợp lệ và được Spring Boot có thể khởi tạo theo cơ chế đăng ký sớm. Không kỳ vọng constructor injection một **@Service** vào listener này, vì context chứa các bean chưa tồn tại.

**Trong ứng dụng mẫu ở mục 6, chỉ dùng addListeners; không đăng ký đồng thời cùng listener bằng spring.factories**, tránh tạo hai instance và xử lý callback trùng.

### 5.3. Các cách thường bị dùng sai

~~~java
@Component
class WrongListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        // Không được bảo đảm nhận event bootstrap sớm này!
    }
}
~~~

**@Component** chỉ được quét và đăng ký khi container xử lý bean definitions. Tương tự, một method có **@EventListener(ApplicationEnvironmentPreparedEvent.class)** trên bean thông thường được phát hiện quá muộn để nhận event sớm đã phát.

**Quy tắc:** listener cần nhận sự kiện **trước khi có context** phải được đăng ký qua **SpringApplication**, **SpringApplicationBuilder** hoặc cơ chế bootstrap tự động tương ứng. Không chuyển nó thành @Bean/@Component rồi hy vọng Spring “phát lại” sự kiện đã qua.

## 6. Ví dụ hoàn chỉnh Java 17+: đọc Config Data và thêm fallback

Mục tiêu của ví dụ:

1. Đăng ký listener trước khi **run** bắt đầu.
2. Listener nhận **ApplicationEnvironmentPreparedEvent** và đọc **demo.mode** từ file cấu hình.
3. Listener thêm **demo.greeting** ở PropertySource ưu tiên thấp nếu chưa có nguồn cùng tên.
4. **ApplicationRunner** đọc kết quả sau khi context đã refresh.
5. Mã **main** xác nhận **run(...)** đã trả về context active.

Yêu cầu: **Java 17+**, **Spring Boot 3.3.x**, dependency **spring-boot-starter**, dự án Gradle/Maven có cấu hình plugin Spring Boot. Ví dụ không cần HTTP server.

Tạo file **src/main/java/com/example/runtime/EarlyEnvironmentDemo.java**:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class EarlyEnvironmentDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(EarlyEnvironmentDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Phải đăng ký listener TRƯỚC khi run bắt đầu.
        app.addListeners(new PreparedEnvironmentListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Bean
    ApplicationRunner inspectConfiguration(Environment environment) {
        return args -> {
            System.out.println(
                    "RUNNER | mode=" + environment.getProperty("demo.mode"));

            System.out.println(
                    "RUNNER | greeting="
                            + environment.getProperty("demo.greeting"));
        };
    }

    static final class PreparedEnvironmentListener
            implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                       Ordered {

        @Override
        public int getOrder() {
            // Đọc sau các EnvironmentPostProcessor mặc định.
            return Ordered.LOWEST_PRECEDENCE;
        }

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {

            ConfigurableEnvironment environment = event.getEnvironment();

            System.out.println(
                    "EVENT | mode="
                            + environment.getProperty("demo.mode", "missing"));

            LessonDefaults.register(environment);
        }
    }

    static final class LessonDefaults {

        private static final String NAME = "lesson-defaults";

        static void register(ConfigurableEnvironment environment) {
            if (!environment.getPropertySources().contains(NAME)) {
                environment.getPropertySources().addLast(
                        new MapPropertySource(NAME, Map.of(
                                "demo.greeting", "Hello from early listener")));
            }
        }
    }
}
~~~

**src/main/resources/application.properties**:

~~~properties
demo.mode=from-file
~~~

Chạy trên Linux/macOS từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Các dòng do chính chương trình in, theo thứ tự kỳ vọng ở cấu hình ví dụ:**

~~~text
EVENT | mode=from-file
RUNNER | mode=from-file
RUNNER | greeting=Hello from early listener
MAIN | active=true
~~~

Log của framework hoặc build tool có thể xen giữa các dòng này. Ví dụ cố tình dùng **WebApplicationType.NONE** để không cần start web server; context được đóng bằng **try-with-resources** sau khi in kết quả.

### 6.1. Tại sao EVENT đã thấy demo.mode từ application.properties?

**PreparedEnvironmentListener** trả về **Ordered.LOWEST_PRECEDENCE**. Trong Boot 3.3 thông thường, listener hạ tầng kích hoạt **ConfigDataEnvironmentPostProcessor** có ưu tiên cao hơn, nên nó đã nạp file **application.properties** trước khi listener của chúng ta đọc **demo.mode**.

Nếu tự đặt listener ở mức **HIGHEST_PRECEDENCE**, kết quả có thể khác: listener có thể được gọi trước khi Config Data được xử lý. Không nên dựa vào nội dung file cấu hình mà không xét thứ tự.

### 6.2. Tại sao không dùng @Bean để đăng ký listener?

Khi sự kiện phát, context chưa được tạo nên **@Bean PreparedEnvironmentListener** không thể nhận sự kiện này từ cơ chế bean event listener thông thường. Ví dụ đã tạo trực tiếp listener bằng **new PreparedEnvironmentListener()** và đăng ký qua **app.addListeners(...)** trước run.

Lớp listener không inject **Environment** trong constructor, cũng không truy cập service bean: nó nhận đúng **ConfigurableEnvironment** có sẵn từ **event.getEnvironment()**.

### 6.3. Tại sao dùng addLast thay vì addFirst?

**LessonDefaults.register** thêm nguồn **lesson-defaults** ở cuối để thiết lập fallback. Nếu operator cung cấp giá trị **demo.greeting** từ command line, system property, environment variable hoặc Config Data ở nguồn ưu tiên cao hơn, giá trị của operator được giữ nguyên.

Ví dụ chạy với một override:

~~~bash
./gradlew bootRun --args="--demo.greeting=Hello-from-CLI"
~~~

Lúc này, trong ứng dụng mẫu, các dòng in liên quan sẽ là:

~~~text
EVENT | mode=from-file
RUNNER | mode=from-file
RUNNER | greeting=Hello-from-CLI
MAIN | active=true
~~~

Listener vẫn có thể đăng ký **lesson-defaults**, nhưng **Environment.getProperty("demo.greeting")** chọn giá trị từ argument ưu tiên cao hơn.

### 6.4. Vì sao event đứng trước runner và main?

Listener chạy trong **prepareEnvironment**, trước việc tạo context. **ApplicationRunner** chỉ chạy sau khi context refresh thành công. **main** in dòng **MAIN** sau khi **SpringApplication.run(...)** trả về.

Các dòng đó phản ánh **thứ tự bootstrap thực**, không phải do Spring sắp xếp source file hay thứ tự khai báo các lớp nested class.

## 7. Kiểm thử riêng logic chỉnh PropertySources

Một listener sớm nên giữ logic nhỏ để kiểm thử mà không cần khởi động cả ứng dụng. Trong ví dụ, **LessonDefaults.register** chỉ thao tác với **ConfigurableEnvironment**, không cần bean nghiệp vụ hay web server.

Với dependency **spring-boot-starter-test** (JUnit Jupiter và spring-test), tạo file:

**src/test/java/com/example/runtime/LessonDefaultsTest.java**

~~~java
package com.example.runtime;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LessonDefaultsTest {

    @Test
    void addsFallbackWhenPropertyMissing() {
        MockEnvironment environment = new MockEnvironment();

        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertEquals(
                "Hello from early listener",
                environment.getProperty("demo.greeting"));
    }

    @Test
    void neverOverridesHigherPriorityValue() {
        MockEnvironment environment = new MockEnvironment();
        environment.setProperty("demo.greeting", "from-operator");

        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertEquals(
                "from-operator",
                environment.getProperty("demo.greeting"));
    }

    @Test
    void repeatedRegistrationKeepsSingleNamedSource() {
        MockEnvironment environment = new MockEnvironment();

        EarlyEnvironmentDemo.LessonDefaults.register(environment);
        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertNotNull(
                environment.getPropertySources().get("lesson-defaults"));
        assertEquals(
                "Hello from early listener",
                environment.getProperty("demo.greeting"));
    }
}
~~~

Chạy test với Gradle Wrapper:

~~~bash
./gradlew test
~~~

Các test xác minh **giá trị fallback**, **khả năng override** và **không đăng ký cùng tên PropertySource nhiều lần**. Chúng không chứng minh rằng SpringApplication đã phát sự kiện đúng thời điểm: việc đó cần **integration/startup test** dùng SpringApplication thật.

**Lưu ý:** tên nested class **LessonDefaults** không khai báo **private**, để test trong cùng package truy cập được. Test không cần mock ApplicationEnvironmentPreparedEvent, không khởi động ApplicationContext và không mở cổng HTTP.

### 7.1. Kiểm thử event thật khi nào?

Nếu muốn xác minh listener thực sự đọc file sau Config Data, có thể dùng một **SpringApplication** nhỏ đăng ký listener, chạy với **WebApplicationType.NONE**, capture kết quả từ callback rồi đóng context. Test này cần kiểm soát các nguồn thuộc tính ngoài để tránh giá trị environment của máy CI ghi đè kỳ vọng.

Nếu mục tiêu chỉ là kiểm tra thuật toán thêm fallback, unit test ở trên nhanh và ổn định hơn. Không nên dùng **@SpringBootTest** cho mọi phép gán MapPropertySource đơn giản.

## 8. Phân biệt listener event và EnvironmentPostProcessor

Cả hai có thể tác động lên Environment, nhưng vai trò thiết kế khác nhau:

| Tiêu chí | ApplicationListener<ApplicationEnvironmentPreparedEvent> | EnvironmentPostProcessor |
| --- | --- | --- |
| Ý nghĩa chính | Phản ứng với một mốc sự kiện bootstrap | Biến đổi/cung cấp cấu hình Environment |
| Cách nhận Environment | **event.getEnvironment()** | **postProcessEnvironment(environment, application)** |
| Đăng ký | **SpringApplication.addListeners**, builder hoặc **spring.factories** | **META-INF/spring.factories** |
| Có thể điều chỉnh thứ tự? | **Ordered/@Order** hoặc cơ chế sắp xếp listener | **Ordered/@Order** |
| Có thể inject @Service không? | Không nên; chưa có context | Không; dùng API bootstrap và dependency thích hợp |
| Khi dùng tốt nhất | Quan sát mốc, logging có chọn lọc, kiểm tra hoặc bổ sung cấu hình đơn giản | Nạp/thay đổi PropertySource có trách nhiệm, tích hợp bootstrap config |

Một EnvironmentPostProcessor tối giản:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class ExtraDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        if (!environment.getPropertySources().contains("extra-defaults")) {
            environment.getPropertySources().addLast(
                    new MapPropertySource(
                            "extra-defaults",
                            Map.of("demo.extra", "enabled")));
        }
    }
}
~~~

Để Boot 3.3 phát hiện processor tự động, thêm vào:

**src/main/resources/META-INF/spring.factories**

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.runtime.ExtraDefaultsEnvironmentPostProcessor
~~~

Đây là **ví dụ thay thế để minh họa cơ chế EnvironmentPostProcessor**; không phải bước bắt buộc của chương trình ở mục 6. Nếu chạy cả hai, chúng chỉnh **các khóa khác nhau**. Trong trường hợp processor cần đọc Config Data đã nạp, phải lựa chọn thứ tự phù hợp với **ConfigDataEnvironmentPostProcessor** thay vì tự đoán.

**Điểm khác nữa:** EnvironmentPostProcessor được Boot nạp bằng cơ chế bootstrap và có thể tùy chọn nhận **DeferredLogFactory** hoặc **ConfigurableBootstrapContext** trong constructor theo API hỗ trợ. Nó không phải service bean thông thường.

## 9. Những thuộc tính nào có thể chỉnh ở thời điểm này?

Một điểm mạnh của sự kiện là nó xuất hiện **trước khi SpringApplication tạo context và bind một số cấu hình launch từ Environment**. Nhưng **không có nghĩa mọi loại cấu hình còn thay đổi được một cách an toàn**.

### 9.1. Thuộc tính thuộc ứng dụng

Một listener chạy đúng thứ tự có thể thêm PropertySource chứa **demo.mode**, **feature.enabled** hoặc các khóa dùng trong **@ConfigurationProperties**. Khi bean được tạo sau đó, các giá trị này có thể được bind bình thường theo thứ tự ưu tiên.

Điều kiện là cấu hình chưa bị một logic bootstrap sớm khác tiêu thụ theo cách không thể quay lại. Nên dùng fallback có tên rõ ràng và mức ưu tiên thấp nếu chỉ muốn cung cấp mặc định.

### 9.2. spring.main.*

Các thuộc tính **spring.main.*** được liên kết vào **SpringApplication** trong quá trình prepareEnvironment. Vì vậy một thay đổi được đưa vào Environment trước bước bind có thể ảnh hưởng tới startup. Ví dụ **spring.main.banner-mode** hoặc **spring.main.lazy-initialization**.

Tuy nhiên, những giá trị đã được **tính/đọc ở bước sớm hơn** hoặc được cấu hình trực tiếp bằng API đặc biệt cần xét riêng. Không coi EnvironmentPreparedEvent là cơ chế ghi đè tùy ý mọi quyết định của SpringApplication.

### 9.3. spring.config.* và profile selection

Các thuộc tính như **spring.config.name**, **spring.config.location**, **spring.config.additional-location** dùng để định hướng quá trình **tìm và nạp Config Data**. Nếu listener chạy **sau** ConfigDataEnvironmentPostProcessor, việc bổ sung chúng lúc ấy **không khiến Boot quay lại tìm file từ đầu**.

Khi cần thay đổi nơi đọc cấu hình, cung cấp các giá trị đó từ nguồn đủ sớm như **CLI**, **system property** hoặc **OS environment variable**, hoặc viết extension bootstrap có thứ tự được thiết kế riêng. Đây là ví dụ quan trọng cho nguyên tắc **thời điểm một giá trị xuất hiện phải trước lúc nó được tiêu thụ**.

### 9.4. logging.*

Spring Boot cũng có listener hạ tầng cấu hình logging trong giai đoạn rất sớm. Thêm **logging.level.*** vào Environment **sau khi hệ thống logging đã được cấu hình** không có nghĩa cấu hình logging tự chạy lại đầy đủ.

Nếu cần ảnh hưởng logging bootstrap, phải xem thứ tự listener và cơ chế logging Boot hỗ trợ. Không nên dùng một listener cuối danh sách rồi coi nó là nguồn cấu hình logging sớm.

## 10. Các lỗi thường gặp và cách chẩn đoán

### 10.1. Dùng @Component hoặc @EventListener nhưng callback không chạy

Nguyên nhân: context chưa tồn tại khi event được phát. Sửa bằng **SpringApplication.addListeners(...)**, builder listener hoặc **spring.factories** trước khi bắt đầu run.

### 10.2. Listener đọc application.properties nhưng nhận null

Nguyên nhân có thể là listener có độ ưu tiên rất cao và chạy **trước** EnvironmentPostProcessorApplicationListener nạp Config Data, hoặc file/property không được nạp theo profile/vị trí hiện tại. Kiểm tra order, nguồn cấu hình và CLI. Với listener chỉ dùng để quan sát, một mức order muộn như **LOWEST_PRECEDENCE** thường dễ hiểu hơn.

### 10.3. Cố lấy @Repository bằng applicationContext.getBean(...)

Ở mốc EnvironmentPrepared, **ApplicationContext chưa được tạo**, nên không có bean application context để tra cứu. Chuyển việc cần bean sang **ApplicationRunner**, một service thông thường hoặc event muộn phù hợp.

### 10.4. Thêm PropertySource ở đầu danh sách và đè cấu hình production

**addFirst** có thể thắng nguồn do operator thiết lập. Nếu dữ liệu chỉ là default, dùng **addLast**; kiểm tra tên nguồn trùng và bảo đảm không phát sinh hiệu ứng ngoài dự kiến.

### 10.5. Đặt spring.config.location trong listener quá muộn

Nếu Config Data đã được xử lý trước callback, giá trị mới không tự khởi động lại quá trình import/tìm kiếm. Đưa các thuộc tính chỉ đường nạp Config Data vào nguồn bootstrap sớm và kiểm tra thứ tự thật.

### 10.6. Gọi network/database trong callback

Sự kiện được xử lý trong lúc startup. I/O kéo dài hoặc exception chưa xử lý có thể kéo dài hoặc làm thất bại khởi động, trong khi các bean application chưa sẵn sàng. Tách việc tải cấu hình bootstrap thật sự cần thiết khỏi tác vụ nghiệp vụ; dùng timeout/chính sách lỗi, hoặc dời công việc sang mốc muộn.

### 10.7. In toàn bộ Environment hay command-line args để debug

PropertySources và args có thể chứa password, token hoặc thông tin nội bộ. Log những **tên khóa an toàn** và giá trị đã che nhạy cảm. Không dump environment/args thô vào production logs.

### 10.8. Kỳ vọng event chỉ xảy ra một lần trên cả JVM

Mỗi lần **SpringApplication** chạy có thể phát event tương ứng. Ứng dụng có nhiều context, test tạo lại context hoặc chạy nhiều SpringApplication trong cùng tiến trình có thể kích hoạt listener nhiều lần. Side effect cần có tên nguồn duy nhất, kiểm tra trùng và quản lý vòng đời theo **từng lần chạy**, không dùng biến static toàn cục tùy tiện.

### 10.9. Listener ném exception và vẫn mong ApplicationReadyEvent

Exception trong callback sớm có thể làm quá trình khởi động thất bại; Spring Boot có thể phát **ApplicationFailedEvent**. Không có bảo đảm context được tạo, runner thực thi hay ready event xuất hiện sau lỗi. Chỉ chặn startup nếu đó thực sự là điều kiện bắt buộc; với tác vụ quan sát không thiết yếu, xử lý lỗi theo chính sách phù hợp.

### 10.10. Dùng @Order nhưng kết quả vẫn không như dự kiến

Hệ thống listener có cả các listener hạ tầng của Boot và của thư viện. Xác định **Order** của listener liên quan (đặc biệt bộ xử lý Config Data và logging), điểm đăng ký và khả năng một listener khác chỉnh cùng khóa sau đó. Cách debug thực tế là in **tên PropertySource** và giá trị của **một khóa được phép**, thay vì dựa vào giả định “event đã chuẩn bị xong nên tất cả đều cố định”.

## 11. Checklist thiết kế một listener sớm chất lượng

Trước khi đưa listener vào dự án, nên xác nhận:

- [ ] Listener đã được đăng ký **trước SpringApplication.run(...)**.
- [ ] Không phụ thuộc **ApplicationContext/@Service/@Repository** ở thời điểm event.
- [ ] Chỉ xử lý các khóa cấu hình thật sự liên quan và có thể đọc ở pha này.
- [ ] Xác định thứ tự so với **EnvironmentPostProcessorApplicationListener** nếu cần Config Data.
- [ ] Nguồn mặc định dùng mức ưu tiên thấp, không ghi đè cấu hình người vận hành.
- [ ] Không kỳ vọng thay đổi **spring.config.*** muộn sẽ chạy lại Config Data.
- [ ] Không giả định thay đổi **logging.*** sau logging listener sẽ có hiệu lực hồi tố.
- [ ] Có biện pháp tránh đăng ký trùng PropertySource hoặc side effect lặp.
- [ ] Callback nhanh, không I/O nghiệp vụ nặng, không ghi dữ liệu nhạy cảm vào log.
- [ ] Logic xử lý PropertySource có unit test độc lập.
- [ ] Nếu cần test thứ tự event thực tế, có startup test với **SpringApplication** thật.
- [ ] Phân biệt **EnvironmentPrepared**, **ApplicationPrepared**, **Started** và **Ready**.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** ApplicationEnvironmentPreparedEvent được gửi trước hay sau khi Spring tạo ApplicationContext?

**Đáp án:** **Trước**. Environment đã có để đọc/chỉnh, nhưng ApplicationContext chưa được tạo.

**Câu 2.** Một listener khai báo bằng @Component có được bảo đảm nhận event này trong lần SpringApplication.run đầu tiên?

**Đáp án:** **Không**. Bean được tạo/phát hiện sau mốc sự kiện. Listener cho event sớm cần đăng ký trước run hoặc bằng cơ chế bootstrap phù hợp.

**Câu 3.** Tại sao hai listener cùng xử lý ApplicationEnvironmentPreparedEvent lại có thể đọc được những PropertySources khác nhau?

**Đáp án:** Vì các listener có thứ tự. **EnvironmentPostProcessorApplicationListener** có thể nạp Config Data trong khi dispatch event; một listener chạy trước và một listener chạy sau sẽ thấy trạng thái Environment khác nhau.

**Câu 4.** Trong ví dụ, nếu thêm **--demo.greeting=Hello-from-CLI** thì giá trị fallback còn là giá trị được đọc không?

**Đáp án:** Không. Fallback được thêm bằng **addLast**, còn giá trị CLI nằm ở nguồn có ưu tiên cao hơn, nên runner đọc **Hello-from-CLI**.

**Câu 5.** Có thể đưa **spring.config.location** vào một listener chạy sau ConfigDataEnvironmentPostProcessor rồi yêu cầu Boot tự tìm thêm file ngay lập tức không?

**Đáp án:** Không. Không có cơ chế tự động chạy lại toàn bộ quá trình tìm/nạp Config Data chỉ vì listener thêm khóa muộn.

**Câu 6.** Sự kiện này có bảo đảm mọi bean đã được inject, mọi runner đã chạy và HTTP server đã sẵn sàng chưa?

**Đáp án:** Không. Đây là sự kiện bootstrap trước khi tạo context; các bước refresh, runners và readiness còn ở phía sau.

**Câu 7.** Khi cần triển khai một bộ nạp cấu hình tùy chỉnh, vì sao nên cân nhắc EnvironmentPostProcessor?

**Đáp án:** Vì nó có hợp đồng chuyên biệt để chỉnh Environment trước refresh, hỗ trợ đăng ký qua spring.factories và điều khiển thứ tự xử lý khi cần.

**Câu 8.** Một listener chỉ quan sát cấu hình nên dùng **getBean(MyService.class)** để lấy tên ứng dụng từ database chứ?

**Đáp án:** Không. Bean nghiệp vụ chưa tồn tại ở mốc này. Nếu cần database và service DI, dùng callback muộn hoặc một kiến trúc nạp bootstrap thực sự có thiết kế riêng.

## 13. Tổng kết và tài liệu chính thức

**ApplicationEnvironmentPreparedEvent** là tín hiệu sớm cho biết **Environment đã có thể được đọc và điều chỉnh trước khi ApplicationContext được tạo**. Nó nằm giữa **ApplicationStartingEvent** và **ApplicationContextInitializedEvent**. Bản thân Environment vẫn có thể được các EnvironmentPostProcessor và listener khác tiếp tục hoàn thiện **trong cùng lượt dispatch sự kiện**; vì vậy **thứ tự listener** là nội dung bắt buộc phải hiểu.

Một listener đúng vòng đời được đăng ký **trước run**, không phụ thuộc bean application, chỉ thêm PropertySource khi cần và kiểm soát ưu tiên. Nếu mục đích là nạp cấu hình bootstrap chuyên biệt, **EnvironmentPostProcessor** thường là extension point thích hợp hơn. Cấu hình đã bị tiêu thụ ở pha trước không tự được xử lý lại chỉ vì Environment được chỉnh sau đó.

Tài liệu chính thức theo Spring Boot 3.3:

- **ApplicationEnvironmentPreparedEvent API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- **Application events and listeners:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **EnvironmentPostProcessorApplicationListener API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
- **ConfigDataEnvironmentPostProcessor API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- **EnvironmentPostProcessor API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- **Externalized Configuration:** https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html