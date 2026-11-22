# ApplicationStartingEvent trước khi có Environment và context hoàn chỉnh

## 1. Mục tiêu

`ApplicationStartingEvent` là một trong những tín hiệu sớm nhất của vòng đời khởi động Spring Boot. Spring Boot phát sự kiện này **ngay sau khi bắt đầu `SpringApplication.run(...)`, sau bước đăng ký các listener/initializer, nhưng trước khi `Environment` và `ApplicationContext` sẵn sàng**. Nó hữu ích để quan sát thời điểm Spring Boot thực sự bắt đầu bootstrap và triển khai một số tích hợp hạ tầng cần có rất sớm.

Điểm khó của bài không nằm ở cú pháp listener mà ở **ranh giới vòng đời**:

- Khi event được phát, đã có một đối tượng `SpringApplication`, các đối số chạy và một bootstrap context dành cho giai đoạn sớm.
- Lúc đó **chưa có `ConfigurableEnvironment` hoàn chỉnh để đọc profile/property theo cơ chế Spring Boot**.
- **Chưa có `ApplicationContext` hoàn chỉnh** để tra cứu bean, inject `@Autowired`, chạy `@Bean` hay truy cập web server.
- Do đó listener muốn nhận event này phải được đăng ký **trước lời gọi `run()`**, hoặc thông qua cơ chế nạp listener từ `META-INF/spring.factories`; khai báo listener như một bean thông thường là quá muộn.

Một câu hỏi thực tế: vì sao đặt `@EventListener(ApplicationStartingEvent.class)` trong một `@Component` không thấy sự kiện? Vì `@Component` chỉ trở thành bean sau khi context được xây dựng và các định nghĩa bean được xử lý; `ApplicationStartingEvent` đã xảy ra trước đó.

## 2. ApplicationStartingEvent nằm ở mốc nào?

Từ thời điểm Java chạy `main()` đến khi Spring Boot báo sẵn sàng, có nhiều cột mốc độc lập. Với một lần chạy `SpringApplication` điển hình, thứ tự sự kiện chủ chốt là:

~~~text
JVM gọi main(String[] args)
   |
   +-- new SpringApplication(YourApplication.class)
   +-- Đăng ký ApplicationListener, initializer ...
   |
   +-- application.run(args)
         |
         +-- ApplicationStartingEvent                <== TRỌNG TÂM
         |      Environment CHƯA sẵn sàng
         |      ApplicationContext CHƯA sẵn sàng
         |
         +-- Chuẩn bị ConfigurableEnvironment
         +-- ApplicationEnvironmentPreparedEvent
         |      Environment đã có, context chưa tạo
         |
         +-- Tạo ApplicationContext
         +-- Chạy ApplicationContextInitializer
         +-- ApplicationContextInitializedEvent
         |      Context đã tạo/chỉnh ban đầu; chưa nạp bean definitions
         |
         +-- Nạp các bean definition
         +-- ApplicationPreparedEvent
         |      Định nghĩa bean đã nạp; context chưa refresh
         |
         +-- ApplicationContext.refresh()
         |      BeanFactoryPostProcessor, BeanPostProcessor,
         |      khởi tạo bean, có thể khởi động web server ...
         |
         +-- ApplicationStartedEvent
         |      Context đã refresh; runner chưa chạy
         |
         +-- ApplicationRunner và CommandLineRunner
         |
         +-- ApplicationReadyEvent
         +-- ReadinessState.ACCEPTING_TRAFFIC
         |
         v
       run(...) thành công
~~~

Đây là sơ đồ khái quát theo Spring Boot 3.5. Trong một ứng dụng web còn có `WebServerInitializedEvent` và sự kiện refresh của Spring Framework. Nếu startup gặp lỗi, `ApplicationFailedEvent` có thể được công bố thay vì tiếp tục tới trạng thái ready.

**Không nhầm** thời điểm event được phát với lúc Java `main()` bắt đầu: nếu bạn có lệnh Java trước `application.run(args)`, lệnh đó thực thi trước `ApplicationStartingEvent`. Đây là một sự kiện *của SpringApplication*, không phải callback đầu tiên của toàn JVM.

## 3. Thông tin nào có thể lấy ngay từ ApplicationStartingEvent?

Trong Spring Boot 3.5, `ApplicationStartingEvent` thuộc package `org.springframework.boot.context.event` và kế thừa `SpringApplicationEvent`.

| API | Ý nghĩa | Giới hạn cần biết |
| --- | --- | --- |
| `event.getSpringApplication()` | Đối tượng `SpringApplication` đang được chạy | Trạng thái nội bộ có thể còn thay đổi; không giả định mọi cấu hình đã ổn định |
| `event.getArgs()` | Mảng đối số `String[]` của lần gọi `run(args)` | Đây là đối số thô; chưa phải hệ thống properties đã được xử lý |
| `event.getBootstrapContext()` | `ConfigurableBootstrapContext` phục vụ các dependency của giai đoạn bootstrap | Không phải `ApplicationContext` hay kho bean runtime |
| `event.getTimestamp()` | Thời điểm tạo event (từ `ApplicationEvent`) | Không phải thời điểm toàn ứng dụng sẵn sàng |
| `event.getSource()` | Đối tượng nguồn sự kiện, trong trường hợp này liên quan đến `SpringApplication` | Không thay thế API truy cập context |

Với `getArgs()`, mã sau là hợp lệ bên trong listener:

~~~java
String[] args = event.getArgs();
int count = args.length;
~~~

Đây là một đoạn minh họa trong listener đã nhận `ApplicationStartingEvent`, chưa phải chương trình độc lập.

**Cảnh báo thực hành:** đối số dòng lệnh có thể chứa mật khẩu, access token, URI nhạy cảm hoặc thông tin riêng. Ví dụ ở đây chỉ in **số lượng đối số**, không in toàn bộ nội dung. Ở production, không nên log `Arrays.toString(event.getArgs())` nếu chưa có bước loại bỏ dữ liệu nhạy cảm.

### Chưa có Environment không có nghĩa Java không có bất kỳ cấu hình nào

`System.getenv("NAME")` và `System.getProperty("name")` là các API của Java; chúng có thể được gọi trước khi Spring Boot bắt đầu. Tuy nhiên, chúng **không tương đương** với `Environment.getProperty(...)`, vốn có thứ tự `PropertySource`, profile, đối số lệnh và nhiều cơ chế hợp nhất khác của Spring.

Chẳng hạn, đối số `--demo.flag=on` có thể đã xuất hiện trong `event.getArgs()` nhưng tại `ApplicationStartingEvent` bạn chưa nên giả định rằng nó có thể đọc qua một `Environment` cuối cùng. Khi `ApplicationEnvironmentPreparedEvent` được phát, `event.getEnvironment()` mới là API thích hợp để xem các property đã được chuẩn bị cho lần khởi động này.

### Có bootstrap context nhưng chưa có bean thông thường

Từ Spring Boot 2.4, sự kiện có `getBootstrapContext()`. Bootstrap context cho phép một số tích hợp khởi động đăng ký/lấy dependency theo type mà chưa cần `ApplicationContext`. Đây là cơ chế phù hợp với các nhu cầu cực sớm như tích hợp Config Data.

Tuy nhiên, **bootstrap registry không phải BeanFactory**. Khi bạn có:

~~~java
var bootstrap = event.getBootstrapContext();
boolean available = bootstrap.isRegistered(EarlyDependency.class);
~~~

thì `EarlyDependency` là kiểu giả định và đoạn này chỉ để minh họa API. Không được suy từ `isRegistered(...)` rằng Spring bean cùng type đã tồn tại, hay toàn bộ cấu hình ứng dụng đã sẵn sàng. Nếu cần một dependency được tạo từ bootstrap context, hãy đăng ký nó bằng `BootstrapRegistryInitializer` đúng giai đoạn; đừng tự ý đòi truy cập `@Autowired` tại đây.

## 4. Đăng ký listener đúng lúc

### 4.1. SpringApplication.addListeners(...) — cách phổ biến khi sở hữu main()

Muốn bắt `ApplicationStartingEvent`, tạo `SpringApplication` rồi thêm listener **trước khi gọi `run()`**:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        System.out.println("Đã nhận event khởi động sớm");
    }
);
application.run(args);
~~~

Đây là **đoạn minh họa trong `main()`**, không phải chương trình chạy độc lập: cần lớp `MyApplication` cùng import `SpringApplication`, `ApplicationListener`, `ApplicationStartingEvent`. Ví dụ chạy đầy đủ nằm ở mục 6.

Nếu dùng `SpringApplicationBuilder`, có thể cấu hình listener thông qua phương thức `listeners(...)` của builder trước khi khởi chạy. Hai cách đều dựa trên nguyên tắc **đăng ký trước khi sự kiện đầu tiên được phát**.

Lời gọi tiện lợi:

~~~java
SpringApplication.run(MyApplication.class, args);
~~~

vẫn khởi động ứng dụng bình thường, nhưng nó không cho phép chèn một listener lập trình ngay trước `run` nếu bạn không chủ động tạo `SpringApplication` trước. Có thể dùng đăng ký qua `spring.factories` khi không sở hữu entry point.

### 4.2. META-INF/spring.factories — cách cho tích hợp được nạp tự động

Nếu viết thư viện cần listener được đăng ký ngay cả khi ứng dụng khác dùng `SpringApplication.run(...)` dạng static, Spring Boot hỗ trợ đăng ký thông qua tệp trên classpath:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung ví dụ:

~~~properties
org.springframework.context.ApplicationListener=com.example.early.EarlyStartingListener
~~~

Lớp `com.example.early.EarlyStartingListener` phải thực thi `ApplicationListener<ApplicationStartingEvent>`, có thể được trình nạp tạo instance và không phụ thuộc constructor injection vào bean ứng dụng. Tên package/class trong cấu hình là **ví dụ**, phải thay bằng lớp thực tế.

Ví dụ lớp Java cho tệp đó:

~~~java
package com.example.early;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("EARLY_LISTENER_RECEIVED");
    }
}
~~~

Đây là một **tệp Java đầy đủ về mặt cú pháp**, nhưng chỉ chạy khi nằm trong một ứng dụng Spring Boot có `spring-boot` dependency và đã được đăng ký bằng `spring.factories` hoặc cách tương đương. Nó không có `main()`.

Chỉ sử dụng cả `spring.factories` và `addListeners(...)` cho cùng một instance khi bạn hiểu rõ cơ chế đăng ký, tránh các xử lý lặp ngoài ý muốn. Đừng nhầm key `org.springframework.context.ApplicationListener` với cơ chế `AutoConfiguration.imports` dành cho auto-configuration.

### 4.3. Vì sao @Component và @EventListener không phù hợp?

Hai cách sau **không đáng tin để nhận `ApplicationStartingEvent`**:

~~~java
@Component
class LateListener {
    @EventListener
    void onStart(ApplicationStartingEvent event) {
        System.out.println("QUÁ MUỘN");
    }
}
~~~

Đây là **đoạn minh họa, không độc lập** (cần import annotation/class). `@Component` và `@EventListener` được xử lý khi container đã có thể quét và tạo bean. `ApplicationStartingEvent` xảy ra trước khi context tồn tại, vì thế listener đăng ký từ bean không thể quay ngược thời gian để nhận nó.

Tương tự, không nên kỳ vọng:

~~~java
@Bean
ApplicationListener<ApplicationStartingEvent> myListener() {
    return event -> System.out.println("too late");
}
~~~

được gọi cho sự kiện khởi động sớm. Đoạn này minh họa một listener **được khai báo làm bean sau khi event đã xảy ra**. Một listener là bean vẫn có thể phù hợp cho các sự kiện đến muộn hơn, nhưng không cho mốc đầu tiên.

## 5. Phân biệt rõ các sự kiện có tên gần nhau

| Sự kiện | Mốc phát | Có Environment? | Có ApplicationContext? | Các tác vụ đã hoàn tất? |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Bắt đầu `run`, listener/initializer đã đăng ký | Chưa | Chưa | Chưa xử lý startup chính |
| `ApplicationEnvironmentPreparedEvent` | Environment đã chuẩn bị | Có, qua event | Chưa | Property sources bước đầu đã được chuẩn bị |
| `ApplicationContextInitializedEvent` | Context đã tạo và initializer được gọi | Có | Có, chưa nạp định nghĩa bean | Khởi tạo context ban đầu |
| `ApplicationPreparedEvent` | Bean definitions đã nạp, trước refresh | Có | Có, chưa refresh | Chuẩn bị bean definitions |
| `ApplicationStartedEvent` | Context refresh thành công | Có | Có, đã refresh | Runner chưa thực thi |
| `ApplicationReadyEvent` | Runner đã chạy thành công | Có | Có | Giai đoạn startup do Boot quản lý đã hoàn tất |
| `ApplicationFailedEvent` | Startup thất bại | Tùy giai đoạn lỗi | Có thể chưa có | Không đảm bảo chạy tiếp các mốc bình thường |

Những sự kiện này không phải các tên thay thế nhau. Một lỗi hay gặp là đọc chữ “Starting” rồi nghĩ `ApplicationStartingEvent` tương đương `ApplicationStartedEvent` hoặc `ApplicationReadyEvent`.

- **Starting**: mới bắt đầu, chưa có Spring `Environment` và context.
- **Started**: context đã refresh nhưng runner chưa chạy.
- **Ready**: runner đã hoàn tất và Boot chuyển sang trạng thái sẵn sàng theo lifecycle thông thường.

Trong ứng dụng Servlet/Reactive, một log “web server started” cũng không đồng nghĩa với `ApplicationStartingEvent`. Server nhúng chỉ có thể khởi động trong giai đoạn context web được chuẩn bị/refresh, tức muộn hơn rất nhiều so với event đầu tiên.

### ContextStartedEvent không phải ApplicationStartedEvent

Spring Framework có `ContextStartedEvent` được phát bởi cơ chế `ApplicationContext.start()`. Nó **không đồng nghĩa** với `ApplicationStartedEvent` của Spring Boot. Đừng thiết kế listener dựa vào tên gần giống; hãy xem event thuộc package nào và do cơ chế nào phát ra.

### @PostConstruct và runner cũng là mốc muộn

`@PostConstruct` được xử lý khi một bean được khởi tạo, tức là `ApplicationContext` đã bắt đầu xây dựng bean. `ApplicationRunner` và `CommandLineRunner` chạy sau khi context refresh. Cả hai đều không phù hợp nếu mục tiêu của bạn là nhận chính `ApplicationStartingEvent`.

## 6. Ví dụ đầy đủ Java 17+ chạy được: ghi lại chuỗi sự kiện

Mục tiêu của ví dụ là quan sát **thứ tự các event**, đồng thời chứng minh sự khác biệt giữa lúc chưa có `Environment` và khi `Environment` đã sẵn sàng. Mã dùng Spring Boot 3.5.x và Java 17+, không mở HTTP server để stdout dễ đọc.

### 6.1. Tạo dự án Maven

Dùng Maven và JDK 17 hoặc mới hơn tương thích với Spring Boot 3.5. Tạo cấu trúc:

~~~text
early-event-demo/
├─ pom.xml
└─ src/main/java/com/example/earlyevent/
   └─ EarlyEventApplication.java
~~~

**Tệp `pom.xml`:**

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>early-event-demo</artifactId>
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

Để ví dụ có import ổn định, `pom.xml` chỉ định một phiên bản Spring Boot 3.5.x cụ thể. Nếu dự án của bạn đang dùng version khác, kiểm tra API và dependency tương ứng, nhất là khi dùng Spring Boot 4.

### 6.2. Tệp Java hoàn chỉnh

**Tệp `src/main/java/com/example/earlyevent/EarlyEventApplication.java`:**

~~~java
package com.example.earlyevent;

import org.springframework.boot.ApplicationRunner;
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
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyEventApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyEventApplication.class);

        // Một ứng dụng không phải web: không mở server/port.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Bắt buộc đăng ký trước khi run() phát Starting event.
        application.addListeners(new TimelineListener());

        application.run(args);
    }

    @Bean
    ApplicationRunner sampleRunner() {
        return args -> System.out.println("06_RUNNER");
    }

    static final class TimelineListener
            implements ApplicationListener<SpringApplicationEvent> {

        @Override
        public void onApplicationEvent(SpringApplicationEvent event) {

            if (event instanceof ApplicationStartingEvent starting) {
                System.out.println(
                        "01_STARTING args=" + starting.getArgs().length
                        + " bootstrap="
                        + (starting.getBootstrapContext() != null));

            } else if (event instanceof ApplicationEnvironmentPreparedEvent env) {
                String flag = env.getEnvironment()
                        .getProperty("demo.flag", "unset");
                System.out.println("02_ENVIRONMENT flag=" + flag);

            } else if (event instanceof ApplicationContextInitializedEvent) {
                System.out.println("03_CONTEXT_INITIALIZED");

            } else if (event instanceof ApplicationPreparedEvent) {
                System.out.println("04_CONTEXT_PREPARED");

            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("05_APPLICATION_STARTED");

            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("07_APPLICATION_READY");

            } else if (event instanceof ApplicationFailedEvent) {
                System.out.println("APPLICATION_FAILED");
            }
        }
    }
}
~~~

Đây là **một tệp Java độc lập trong dự án Spring Boot Maven nói trên**; các import cần thiết đã có. Sử dụng pattern matching `instanceof` có từ Java 16 nên Java 17 biên dịch được.

`TimelineListener` được viết để nhận `SpringApplicationEvent` và phân nhánh theo subtype. Nhờ tạo listener bằng Java trước `run()`, không cần bean injection để listener hoạt động. `@Bean sampleRunner()` nằm trong cấu hình chính và chỉ chạy lúc runner phase, sau khi `ApplicationStartedEvent` đã được phát.

**Lưu ý về `bootstrap=true`:** lệnh in chỉ cho biết `getBootstrapContext()` trả về một reference khác null. Điều đó **không** đồng nghĩa Spring đã tạo đầy đủ `ApplicationContext` hoặc bean nghiệp vụ.

### 6.3. Biên dịch và chạy

Trong thư mục `early-event-demo` chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Có thể build archive thực thi:

~~~bash
mvn package
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu project được tạo qua Spring Initializr và có Maven Wrapper, Linux/macOS dùng `./mvnw spring-boot:run`, Windows PowerShell dùng `.\\mvnw.cmd spring-boot:run`.

**Các dòng do chính mã ví dụ tạo ra**, khi chạy không truyền đối số lệnh, xuất hiện theo thứ tự sau:

~~~text
01_STARTING args=0 bootstrap=true
02_ENVIRONMENT flag=unset
03_CONTEXT_INITIALIZED
04_CONTEXT_PREPARED
05_APPLICATION_STARTED
06_RUNNER
07_APPLICATION_READY
~~~

Đây là **thứ tự các dòng riêng của ví dụ**, không phải toàn bộ console output: banner, thông báo Maven và log nội bộ có thể xen giữa. `ApplicationFailedEvent` không xuất hiện trong lần chạy thành công. Với `WebApplicationType.NONE`, tiến trình có thể thoát sau khi runner hoàn thành.

Nếu chạy JAR với một tham số:

~~~bash
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar --demo.flag=on
~~~

thì hai dòng đầu do code tạo sẽ thay đổi thành:

~~~text
01_STARTING args=1 bootstrap=true
02_ENVIRONMENT flag=on
~~~

Các dòng `03`–`07` giữ nguyên thứ tự. Đó là quan sát quan trọng: **event đầu tiên thấy một đối số thô**, còn ở `ApplicationEnvironmentPreparedEvent`, Spring đã thiết lập được property `demo.flag` vào `Environment`.

### 6.4. Giải thích từng mốc của ví dụ

1. **`01_STARTING`**: listener đã được đăng ký trực tiếp với `SpringApplication`. Sự kiện đầu tiên xảy ra khi chưa có môi trường cấu hình và context chính; chỉ có các thông tin bootstrap tương ứng.
2. **`02_ENVIRONMENT`**: Spring Boot đã tạo và cấu hình `Environment` ban đầu; có thể đọc thuộc tính qua `env.getEnvironment()`.
3. **`03_CONTEXT_INITIALIZED`**: context đã được tạo và các `ApplicationContextInitializer` đã được gọi, nhưng chưa nạp các bean definition.
4. **`04_CONTEXT_PREPARED`**: bean definitions đã nạp nhưng context chưa refresh; chưa thể suy ra singleton nghiệp vụ đã khởi tạo.
5. **`05_APPLICATION_STARTED`**: Spring Boot hoàn tất refresh context nhưng chưa chạy các runner.
6. **`06_RUNNER`**: phương thức từ bean `ApplicationRunner` chạy trong giai đoạn sau refresh.
7. **`07_APPLICATION_READY`**: Boot phát sự kiện khi runner hoàn tất; ngay sau đó nó thông báo readiness accepting theo lifecycle thông thường.

Mục tiêu của bài **không** phải ghi log startup bằng mọi giá. Ví dụ sử dụng `System.out` để minh họa vì cơ chế logging của Spring Boot cũng đang ở giai đoạn cấu hình sớm tại `ApplicationStartingEvent`. Trong hệ thống thực, hãy dùng API logging/instrumentation phù hợp với chính giai đoạn đang chạy, tránh phụ thuộc vào property hoặc bean logger chưa tồn tại.

## 7. Những việc nên và không nên thực hiện tại ApplicationStartingEvent

Sự kiện được phát rất sớm và listener chạy **đồng bộ theo cơ chế mặc định**. Nếu listener bị treo, toàn bộ startup có thể bị trì hoãn.

| Nhu cầu | Phù hợp tại StartingEvent? | Cách thực hiện |
| --- | --- | --- |
| Đánh dấu thời điểm bắt đầu startup | Có | Ghi marker nhẹ hoặc đo thời gian không chứa dữ liệu nhạy cảm |
| Quan sát số lượng đối số chạy | Có | `event.getArgs().length`; không log trực tiếp secrets |
| Truy cập thuộc tính theo `ConfigurableEnvironment` | Chưa | Đợi `ApplicationEnvironmentPreparedEvent` hoặc dùng `EnvironmentPostProcessor` |
| Dùng `ApplicationContext.getBean()` | Không | Đợi context và các bean cần thiết được tạo |
| Dùng `@Autowired` vào listener này | Không nên phụ thuộc | Khởi tạo listener bằng Java, chỉ lấy dependency rất sớm từ API bootstrap được hỗ trợ |
| Tạo HTTP endpoint hoặc kiểm tra cổng web đã lắng nghe | Không | Chờ web context refresh / web server event |
| Chạy migration database, khởi tạo cache nghiệp vụ | Không phải vị trí mặc định | Dùng cơ chế migration/lifecycle hoặc runner phù hợp |
| Đăng ký dependency khởi động trước `Environment` | Có cơ chế riêng | Dùng `BootstrapRegistryInitializer` và bootstrap context |
| Truy cập Spring profile đã hợp nhất | Chưa | Đợi sự kiện Environment prepared |
| Gọi mạng không có timeout hoặc block lâu | Rủi ro cao | Tách bước khởi tạo và đặt chính sách timeout/failure rõ ràng |

**Quy tắc:** listener cho sự kiện sớm nên làm công việc ngắn, ít dependency, không tạo hiệu ứng phụ phức tạp. Nếu xử lý có thể kéo dài hoặc cần bean, chọn điểm mở rộng muộn hơn và đúng lifecycle.

### Có nên sửa SpringApplication ngay từ listener?

`event.getSpringApplication()` trả về đối tượng `SpringApplication`. Nhưng Javadoc cảnh báo trạng thái nội bộ của đối tượng có thể thay đổi về sau. Nếu cần cấu hình startup, hãy **cấu hình `SpringApplication` tường minh trước `run()`** khi có thể; đừng dựa vào việc chạm trạng thái chưa ổn định trong event đầu tiên.

Tương tự, không nên gán lại static global state mỗi khi thấy `ApplicationStartingEvent`: trong test hoặc một tiến trình có thể có nhiều lần chạy application/context, khiến callback phát nhiều lần và gây rò rỉ dữ liệu giữa các lần chạy.

## 8. Tương tác với bootstrap context và EnvironmentPostProcessor

Một số tích hợp cấu hình cần dependency **trước khi có Environment**. Spring Boot hỗ trợ `BootstrapRegistryInitializer` đăng ký supplier trước khi code chuẩn bị Environment cần dùng nó. Event đầu tiên có thể truy cập `ConfigurableBootstrapContext`.

Ví dụ minh họa (đặt trong `main()`, giả định class `EarlyResource` đã tồn tại):

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addBootstrapRegistryInitializer(registry ->
    registry.registerIfAbsent(
        EarlyResource.class,
        context -> new EarlyResource()
    )
);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        boolean registered = event.getBootstrapContext()
                .isRegistered(EarlyResource.class);
        System.out.println("registered=" + registered);
    }
);

app.run(args);
~~~

Đây là **đoạn minh họa không độc lập**: `MyApplication`, `EarlyResource` và import chưa được định nghĩa. Nó cho thấy **bootstrap registry là kênh riêng** có thể được dùng sớm, không có nghĩa `EarlyResource` đã là bean trong `ApplicationContext`.

`EnvironmentPostProcessor` là điểm mở rộng phù hợp để sửa/đưa thêm các `PropertySource` trong quá trình chuẩn bị `Environment`. Viết listener `ApplicationStartingEvent` rồi tự tái hiện cơ chế xử lý property sources bằng tay thường khiến thứ tự precedence, profile và config-data bị sai.

Tương tự, nếu cần tùy biến context sau khi nó được tạo nhưng trước refresh, dùng `ApplicationContextInitializer`; nếu cần code chạy sau khi context hoàn tất, dùng runner. Mỗi extension point có vị trí riêng, không nên cố biến StartingEvent thành nơi giải quyết mọi công việc của ứng dụng.

### Phân biệt sự kiện sớm và bootstrap dependency

- **`ApplicationStartingEvent`** nói “lần chạy SpringApplication đã bắt đầu”, cho listener biết có một mốc startup.
- **`BootstrapRegistryInitializer`** nói “đăng ký dependency/supplier dành cho giai đoạn bootstrap”.
- **`ApplicationEnvironmentPreparedEvent`** nói “Environment đã chuẩn bị và có thể được truy cập/chỉnh theo API”.
- **`ApplicationContextInitializer`** nói “context đã được tạo và có thể tùy chỉnh trước refresh”.

Sự kiện và điểm mở rộng không thay thế nhau; một thứ dùng để **quan sát mốc**, thứ kia cung cấp **hợp đồng thay đổi trạng thái** vào thời điểm hợp lý.

## 9. Điều gì xảy ra nếu listener gặp lỗi?

Một listener được gọi sớm là một phần của đường đi startup. Nếu nó ném exception không được xử lý, `SpringApplication.run()` có thể thất bại ngay khi chưa tạo được context chính. Spring Boot có thể phát `ApplicationFailedEvent`, nhưng không nên giả định ở mọi trường hợp lỗi cực sớm đều có đầy đủ `ApplicationContext` hoặc khả năng dọn dẹp từ bean lifecycle.

Ví dụ anti-pattern:

~~~java
app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        remoteService.connectWithoutTimeout();
    }
);
~~~

Đây là **pseudocode**, không độc lập: `app` và `remoteService` chỉ là đối tượng giả định. Nó cho thấy nguy cơ trực tiếp: thao tác network có thể block startup; service lại có thể còn cần `Environment` chưa tồn tại để biết URL/credential.

Nếu một hoạt động là bắt buộc trước khi ứng dụng phục vụ traffic, hãy xác định rõ:

1. Tài nguyên có thể được tạo ở giai đoạn nào mà không cần bean hoặc Environment?
2. Có cơ chế extension point chính thức cho nhu cầu này không?
3. Nếu thao tác thất bại, nên fail startup, retry có giới hạn hay giảm chức năng?
4. Tài nguyên được giải phóng thế nào nếu bootstrap thất bại trước refresh?
5. Có vô tình log secret hoặc tạo side effect lặp khi test/restart không?

Những câu hỏi này giúp chọn đúng lifecycle hook thay vì nhét khởi tạo nghiệp vụ vào event đầu tiên.

## 10. Kiểm thử và quan sát thực tế

### 10.1. Quan sát đúng sự kiện

Nếu log không thấy `ApplicationStartingEvent`, kiểm tra đăng ký listener trước tiên:

- Với `addListeners`, lệnh gọi phải nằm **trước `application.run(args)`**.
- Với `spring.factories`, file phải nằm đúng `META-INF/spring.factories`, key `org.springframework.context.ApplicationListener`, giá trị là class đã biên dịch có thể được nạp.
- Với `@Component` hoặc `@EventListener`, đừng kỳ vọng nhận event đầu tiên vì bean xuất hiện quá muộn.
- Nếu ứng dụng có nhiều `SpringApplication`/context hoặc chạy lại nhiều lần trong test, có thể thấy nhiều event; phân biệt các lần chạy trước khi xem đó là lỗi.
- Nếu console output có log của Spring Boot chen vào, lọc đúng marker của ứng dụng để đánh giá trình tự, không cần các dòng nằm liền kề.

### 10.2. Phân biệt sự kiện xảy ra và trạng thái ứng dụng

Một ứng dụng có thể phát `ApplicationStartingEvent`, sau đó thất bại ngay trong khi chuẩn bị `Environment`. Điều đó **không** chứng minh ứng dụng đã khởi chạy thành công hoặc đã mở cổng web.

Chỉ sau `ApplicationStartedEvent` mới có bảo đảm theo lifecycle rằng context đã refresh. `ApplicationReadyEvent` xảy ra muộn hơn sau runner. Với hệ thống nhận traffic, nên dùng readiness probe/phương pháp giám sát phù hợp thay vì lấy marker StartingEvent làm trạng thái sống hoặc sẵn sàng.

### 10.3. Bài thử thay đổi đối số

Chạy hai lần:

~~~bash
mvn spring-boot:run
~~~

Sau đó tạo JAR và thử:

~~~bash
mvn package
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar --demo.flag=on
~~~

Giải thích sự thay đổi từ `args=0` sang `args=1`, và từ `flag=unset` sang `flag=on`. Thứ tự event vẫn đúng vì loại sự kiện phản ánh các pha trong `run`, còn giá trị property phản ánh input của từng lần chạy.

Khi dùng plugin Maven `spring-boot:run` và cần chuyển đối số ứng dụng, có thể dùng cấu hình run arguments của plugin tương ứng, nhưng lệnh `java -jar ... --demo.flag=on` trong ví dụ tránh khác biệt cách quote ở từng hệ điều hành.

## 11. Các lỗi thường gặp và cách sửa

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener bean không nhận `ApplicationStartingEvent` | Bean được khởi tạo sau event | Đăng ký bằng `SpringApplication.addListeners`, builder hoặc `spring.factories` |
| `@EventListener` không chạy ở giai đoạn sớm | Annotation cần xử lý của Spring container | Chuyển sang `ApplicationListener<ApplicationStartingEvent>` đăng ký trước run |
| Cố gọi `event.getApplicationContext()` | `ApplicationStartingEvent` không có context chính | Chọn event muộn hơn có accessor context, ví dụ `ApplicationContextInitializedEvent` |
| `@Autowired` của listener sớm là null/không có | Listener được tạo trước cơ chế bean injection | Tránh injection bean, dùng giá trị đơn giản hoặc bootstrap registry đúng phạm vi |
| Đọc `Environment` từ StartingEvent | `Environment` chưa được chuẩn bị | Đợi `ApplicationEnvironmentPreparedEvent` |
| Ghi log toàn bộ args làm lộ bí mật | `getArgs()` chứa input thô có thể nhạy cảm | Chỉ đo metadata an toàn hoặc redaction trước log |
| Lấy `getBootstrapContext()` rồi gọi `getBean()` | Bootstrap context không phải BeanFactory | Dùng registry/context theo type hoặc đợi Spring context |
| Cho listener thực hiện I/O kéo dài | Listener chạy trên đường startup đồng bộ theo mặc định | Giữ xử lý nhẹ; dùng lifecycle hook thích hợp với timeout |
| Gặp nhiều event hơn dự đoán | Nhiều `SpringApplication`, parent/child context hoặc listener đăng ký trùng | Phân biệt nguồn event và cách đăng ký |
| Coi `ApplicationStartedEvent` là kết thúc runner | Event này đến trước runner | Đợi `ApplicationReadyEvent` để xác định startup hoàn tất |
| Coi StartingEvent là liveness/readiness | Event chỉ cho biết bắt đầu quá trình chạy | Quan sát health/readiness sau khi context phát triển |
| Nhầm `ContextStartedEvent` với `ApplicationStartedEvent` | Sự kiện Framework và Boot có hợp đồng khác | Kiểm tra package/type và lifecycle theo Javadoc |

## 12. Câu hỏi ôn tập và bài tập

**Câu hỏi 1.** Tại sao Spring Boot có thể phát `ApplicationStartingEvent` khi chưa có `Environment`?

**Đáp án:** Boot có thể tạo `SpringApplication`, đăng ký listener/initializer và phát event sớm bằng cơ chế startup của chính nó. `Environment` và `ApplicationContext` được chuẩn bị ở các bước tiếp theo.

**Câu hỏi 2.** `event.getArgs()` có thể được dùng để đọc `--server.port=9090` không?

**Đáp án:** Có thể quan sát đối số thô dưới dạng `String[]`, nhưng lúc đó chưa có toàn bộ cơ chế `Environment`/property-source precedence. Không nên tự suy ra cổng web thực tế từ chuỗi nếu còn cấu hình khác ảnh hưởng; hãy dùng các API/mốc muộn thích hợp.

**Câu hỏi 3.** Vì sao `@Component` chứa `@EventListener(ApplicationStartingEvent.class)` không nhận được event đầu tiên?

**Đáp án:** Context chưa tồn tại để component scan và tạo bean, nên listener kiểu bean được đăng ký quá muộn.

**Câu hỏi 4.** `getBootstrapContext()` trả về đối tượng khác null, vậy `ApplicationContext` đã sẵn sàng chưa?

**Đáp án:** Chưa. Bootstrap context là registry/dependency container riêng dành cho startup sớm, không phải Spring ApplicationContext.

**Câu hỏi 5.** `ApplicationStartingEvent` và `ApplicationStartedEvent` khác nhau ở đâu?

**Đáp án:** Starting được phát cực sớm trước Environment/context; Started được phát sau khi context refresh thành công và trước các runner.

**Câu hỏi 6.** Nếu listener sớm ném exception, có thể tin rằng `@PreDestroy` của bean nghiệp vụ sẽ dọn mọi tài nguyên không?

**Đáp án:** Không. Bean chưa được tạo có thể chưa có callback dọn dẹp; tài nguyên tự cấp phát ở giai đoạn sớm cần chính sách quản lý và cleanup phù hợp.

**Bài tập A — thay đổi cách đăng ký:** Chuyển listener ở mục 6 thành một class top-level riêng, đăng ký qua `META-INF/spring.factories`, rồi dùng lại `SpringApplication.run(EarlyEventApplication.class, args)` trong `main`. Kiểm tra `01_STARTING` vẫn xuất hiện. Đảm bảo chỉ giữ một phương án đăng ký để tránh khó phân tích output.

**Bài tập B — phân biệt Environment và args:** Cho chương trình chạy với `--demo.flag=on` và quan sát số đối số tại StartingEvent, giá trị thuộc tính tại EnvironmentPreparedEvent. Thử bỏ tham số để xem giá trị mặc định.

**Bài tập C — xử lý lỗi:** Cố ý cho một `ApplicationRunner` ném exception, rồi theo dõi event nào đã xuất hiện và event nào không. Kết luận vì sao Starting/Started không thể thay cho Ready.

**Bài tập D — bootstrap dependency:** Đăng ký một supplier nhẹ bằng `addBootstrapRegistryInitializer`, dùng `getBootstrapContext().isRegistered(Type.class)` trong StartingEvent. Giải thích vì sao type có registration nhưng bean cùng type chưa tồn tại.

## 13. Tài liệu chính thức và ghi nhớ

Tài liệu nên tra cứu theo phiên bản Spring Boot thực dùng:

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).
- [Spring Boot 3.5 — ApplicationStartingEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html).
- [Spring Boot 3.5 — SpringApplicationEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/SpringApplicationEvent.html).
- [Spring Boot 3.5 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html).
- [Spring Framework — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html).

**Những ý cần nhớ:**

1. `ApplicationStartingEvent` là tín hiệu rất sớm **sau đăng ký listener/initializer**, **trước khi Environment và ApplicationContext có sẵn**.
2. `SpringApplication`, `String[] args` và `ConfigurableBootstrapContext` có thể được tham chiếu ở thời điểm này; không đồng nghĩa các bean runtime đã tồn tại.
3. Muốn bắt event sớm phải **đăng ký listener trước `run()`** hoặc qua `META-INF/spring.factories`; listener là bean không bắt được sự kiện này.
4. Cần properties đã chuẩn bị? Dùng `ApplicationEnvironmentPreparedEvent`. Cần context? Dùng mốc context tương ứng. Cần code sau refresh? Dùng runner hoặc event muộn.
5. Đừng nhầm Starting, Started và Ready: chúng thuộc các giai đoạn khác nhau và trả lời những câu hỏi vận hành khác nhau.
6. Listener sớm nên nhẹ, ít phụ thuộc, không log secret và không tạo I/O có thể treo startup.
7. Với bootstrap dependency thực sự, ưu tiên `BootstrapRegistryInitializer` và cơ chế bootstrap được hỗ trợ, không ép Spring bean injection diễn ra sớm.
