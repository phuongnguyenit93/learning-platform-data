# Khởi tạo logging sớm và hiển thị banner trong Spring Boot

Khi chạy ứng dụng Spring Boot, bạn thường thấy logo Spring Boot (banner), sau đó là những dòng log “Starting ...”, active profile, thông tin web server và cuối cùng là thông báo startup. Tuy nhiên, **thứ tự hiển thị trên terminal không phải thứ tự tạo bean**. Logging được chuẩn bị từ rất sớm để ghi nhận lỗi bootstrap, trong khi banner được in sau khi `Environment` đã được chuẩn bị và trước khi `ApplicationContext` hoàn tất khởi tạo.

Bài học giải thích logging sớm hoạt động thế nào, vì sao một số property chưa có hiệu lực ở thời điểm đầu, cách điều khiển banner và cách tự kiểm tra trình tự khởi động. Mã minh họa dùng **Java 17+ và Spring Boot 3.3.x**; quy trình cũng hữu ích cho các ứng dụng Boot 3.x khác.

## 1. Logging cần sẵn sàng trước khi có bean

Mọi chương trình Java đều bắt đầu từ `main(String[] args)`. Nhưng khi gọi `SpringApplication.run(...)`, Spring Boot còn phải đọc cấu hình, xác định profile, chuẩn bị môi trường, tạo context, đọc bean definition, khởi tạo dependency injection và có thể mở HTTP server. **Lỗi có thể xảy ra ở bất kỳ bước nào**.

Nếu đợi bean `@Configuration`, `@Service` hoặc `CommandLineRunner` hoạt động rồi mới thiết lập logging, hệ thống sẽ không ghi được những lỗi xảy ra trước đó. Vì vậy Boot có một bước khởi tạo logging thuộc **bootstrap**.

Ba khái niệm cần phân biệt:

| Thành phần | Trách nhiệm |
|---|---|
| Logging API, thường là SLF4J | Cung cấp những lệnh như `log.info(...)` và `log.error(...)` để gửi thông điệp. |
| Logging backend, thường là Logback | Quyết định mức log, format, appender, file hoặc console. |
| `LoggingSystem` của Spring Boot | Điều phối backend theo classpath và cấu hình đã biết ở giai đoạn startup. |

Với starter mặc định, Spring Boot thường đưa `spring-boot-starter-logging` vào classpath và sử dụng Logback. Nếu ứng dụng thay sang Log4j2, phải cấu hình dependency tương ứng; không nên giữ hai backend và nhiều binding logging mâu thuẫn trên classpath.

**“Logging được khởi tạo sớm” không có nghĩa cấu hình cuối cùng đã tồn tại ngay trước lời gọi `run`.** Một logger được tạo trong static field có thể tồn tại trước bootstrap. Các lệnh log chạy quá sớm có thể bị ảnh hưởng bởi cấu hình backend mặc định, trước khi properties của Spring Boot được áp dụng.

## 2. Logging nằm ở đâu trong chuỗi khởi động?

Đây là trình tự khái niệm của một lần startup thành công:

~~~mermaid
flowchart TD
    A["JVM vào main()"] --> B["SpringApplication.run(args)"]
    B --> C["ApplicationStartingEvent"]
    C --> D["Chuẩn bị Environment và nguồn cấu hình"]
    D --> E["ApplicationEnvironmentPreparedEvent"]
    E --> F["Hoàn thiện cấu hình logging theo Environment"]
    F --> G["In banner nếu được bật"]
    G --> H["Tạo/chuẩn bị ApplicationContext"]
    H --> I["Refresh context, tạo bean và server nếu cần"]
    I --> J["ApplicationStartedEvent"]
    J --> K["ApplicationRunner / CommandLineRunner"]
    K --> L["ApplicationReadyEvent"]
    L --> M["run() trả về context"]
~~~

Lưu ý đây là **sơ đồ các cột mốc**, không phải mã nguồn từng lệnh của Spring Boot.

Trong quá trình này:

1. `ApplicationStartingEvent` xảy ra rất sớm, khi chưa có `ApplicationContext` hay `Environment` hoàn chỉnh. Những listener bootstrap của Boot, trong đó có thành phần phụ trách logging, có thể xử lý bước ban đầu ở đây.
2. Boot chuẩn bị `Environment` từ các nguồn cấu hình phù hợp như file config data, system properties, environment variables và command-line arguments.
3. Khi `ApplicationEnvironmentPreparedEvent` được phát, các listener liên quan có thể dùng cấu hình đã biết để thiết lập logging chi tiết hơn.
4. Spring Boot chọn và in banner theo chế độ đã cấu hình.
5. Context được tạo và refresh; bean, runner, web server và các lifecycle event lần lượt được xử lý.

Đối với startup bình thường, **banner xuất hiện trước khi ứng dụng ready**. Banner đã in không chứng minh bean đã tạo xong, server đã nhận request hay ứng dụng đã phục vụ được traffic.

Dòng log “Started ... in ... seconds” cũng không nên bị đồng nhất với `ApplicationReadyEvent`: runner còn có thể thực thi sau dòng “Started”, và một runner ném lỗi vẫn có thể khiến lần startup đó thất bại.

## 3. Cấu hình logging đủ sớm bằng `application.properties`

Trong dự án Spring Boot thông thường, các file `application.properties` và `application.yml` được xử lý như config data trong giai đoạn chuẩn bị `Environment`. Ví dụ:

~~~properties
spring.application.name=boot-startup-demo
spring.main.banner-mode=console

logging.level.root=INFO
logging.level.com.example.startup=DEBUG
logging.level.org.springframework=INFO
~~~

Giải thích:

- `logging.level.root=INFO` áp dụng INFO cho root logger; thông điệp DEBUG từ những package không có thiết lập riêng thường không hiển thị.
- `logging.level.com.example.startup=DEBUG` cho phép log DEBUG từ code nằm trong package này và các logger phù hợp.
- `logging.level.org.springframework=INFO` giữ log framework ở mức INFO.
- `spring.application.name` xác định tên ứng dụng, cũng có thể được chèn vào banner.
- `spring.main.banner-mode=console` yêu cầu banner hiển thị ra console.

Nếu chỉ cần thay đổi mức log, phần lớn trường hợp không phải tạo file `logback-spring.xml`.

Có thể truyền cấu hình từ command line, ví dụ với Gradle Boot plugin:

~~~bash
./gradlew bootRun --args='--logging.level.com.example.startup=TRACE'
~~~

Từ Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--logging.level.com.example.startup=TRACE"
~~~

Các lệnh này chạy trong thư mục dự án đã có Gradle wrapper và `bootRun`. Tham số sau `--args` được truyền cho **ứng dụng Java**, nhờ đó có thể ghi đè giá trị tương ứng trong `application.properties` theo quy tắc thứ tự ưu tiên của Spring Boot.

### Vì sao `@PropertySource` có thể không tác dụng đối với logging sớm?

Giả sử một lớp cấu hình chứa:

~~~java
@Configuration
@PropertySource("classpath:extra-logging.properties")
public class ExtraConfiguration {
}
~~~

Đoạn trên **chỉ là ví dụ khai báo**, đòi hỏi các import `org.springframework.context.annotation.Configuration` và `PropertySource` cùng một file cấu hình tương ứng. Khi Boot thiết lập logging ban đầu, lớp `ExtraConfiguration` thường chưa được container xử lý, nên `logging.level.*` đặt trong `extra-logging.properties` có thể xuất hiện quá muộn. Hãy chuyển cấu hình logging sớm sang config data của Boot, command-line hoặc JVM system properties thích hợp.

Tương tự, một bean `@EventListener(ApplicationStartingEvent.class)` không phải cách đáng tin để bắt sự kiện cực sớm: bean đó chưa được tạo vào thời điểm event phát đi. Nếu cần quan sát bootstrap, đăng ký listener trực tiếp vào `SpringApplication` **trước** khi gọi `run`.

## 4. Ví dụ Java chạy được: quan sát logging, banner và context

Tạo ứng dụng Spring Boot 3.3.x với `spring-boot-starter`. Đặt lớp sau trong tệp `src/main/java/com/example/startup/StartupLoggingDemo.java`:

~~~java
package com.example.startup;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupLoggingDemo {

    private static final Logger log =
            LoggerFactory.getLogger(StartupLoggingDemo.class);

    public static void main(String[] args) {
        System.out.println("[1] main: truoc run()");

        SpringApplication application =
                new SpringApplication(StartupLoggingDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // Listener nay duoc dang ky truoc khi co context.
        application.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> System.out.println(
                                "[2] environment: "
                                        + event.getEnvironment().getProperty(
                                                "spring.application.name", "unknown")
                        )
        );

        ConfigurableApplicationContext context = application.run(args);

        System.out.println("[4] after run: " + context.isActive());
        context.close();
    }

    @Bean
    CommandLineRunner startupRunner() {
        return args -> {
            log.info("INFO tu startup runner");
            log.debug("DEBUG tu startup runner");
            System.out.println("[3] runner: da chay");
        };
    }
}
~~~

Để tránh tác động của HTTP server lên kết quả, mã dùng `WebApplicationType.NONE`. Lớp `@SpringBootApplication` vẫn khởi tạo Spring context, auto-configuration và bean runner như bình thường.

Đặt `src/main/resources/application.properties`:

~~~properties
spring.application.name=boot-startup-demo
spring.main.banner-mode=console
logging.level.root=INFO
logging.level.com.example.startup=DEBUG
~~~

Đặt `src/main/resources/banner.txt`:

~~~text
=========================================
 STARTUP APP: ${spring.application.name}
 SPRING BOOT: ${spring-boot.version}
=========================================
~~~

Chạy bằng `./gradlew bootRun` hoặc `.\gradlew.bat bootRun`. Với một dự án Maven có Spring Boot Maven plugin, bạn có thể chạy `./mvnw spring-boot:run` và chỉ định main class phù hợp.

**Các dòng mốc do chính ví dụ in ra**, theo thứ tự tương đối, là:

~~~text
[1] main: truoc run()
[2] environment: boot-startup-demo
... banner co chu STARTUP APP ...
... cac dong log INFO/DEBUG cua Spring va runner ...
[3] runner: da chay
[4] after run: true
~~~

Các dòng có dấu `...` là **ghi chú diễn giải**, không phải stdout nguyên văn. Trong chạy thực tế, banner sẽ chèn tên `boot-startup-demo` và phiên bản Spring Boot cụ thể; log có timestamp, PID và các trường khác. Spring Boot có thể xen thêm log ở nhiều điểm. Điều được kiểm chứng là:

- Mốc `[1]` chạy trước `run()`.
- Mốc `[2]` nhận được tên ứng dụng từ `Environment` và xảy ra trước khi banner được in.
- Banner mặc định mode `console` được xử lý trước khi context hoàn tất khởi tạo.
- Bean runner chạy sau bước refresh context, trước khi `run()` trả về.
- Dòng `[4]` chạy khi `run()` đã trả về một context còn active; chương trình sau đó đóng context chủ động để kết thúc gọn gàng.

Lệnh `log.info` và `log.debug` trong runner dùng SLF4J để kiểm chứng rằng cấu hình log cho `com.example.startup` được áp dụng. Việc cố tình dùng `System.out.println` ở hai mốc bootstrap giúp quan sát thứ tự mà không phụ thuộc vào việc logger đã hoàn thiện cấu hình hay chưa.

## 5. Banner được tìm và xử lý thế nào?

Nếu không tắt banner, Spring Boot có banner chữ mặc định. Muốn thay đổi nội dung, đặt file `banner.txt` ở root classpath:

~~~text
src/main/resources/
├── application.properties
└── banner.txt
~~~

Đây là các file nằm trong mã nguồn của dự án. Tùy cấu hình build, chúng sẽ được đưa lên runtime classpath khi chạy `bootRun` hoặc đóng gói JAR.

Một banner có thể dùng những placeholder như:

| Placeholder | Công dụng |
|---|---|
| `${spring.application.name}` | Tên ứng dụng nếu property đã có trong `Environment`. |
| `${spring-boot.version}` | Phiên bản Spring Boot đang chạy. |
| `${spring-boot.formatted-version}` | Phiên bản Spring Boot dưới dạng hiển thị đã định dạng. |
| `${application.version}` | Version từ package/manifest khi launcher và metadata hỗ trợ. |
| `${AnsiColor.GREEN}` | Mã màu ANSI nếu đầu ra hỗ trợ. |

Lưu ý biến liên quan `application.version`, `application.title` có thể không được giải quyết trong mọi kiểu chạy từ IDE/Gradle; giá trị này gắn với thông tin manifest và cách khởi chạy. Nếu chỉ muốn tên dịch vụ luôn xuất hiện, đặt trực tiếp `spring.application.name` thường dễ kiểm soát hơn.

Đổi vị trí banner bằng:

~~~properties
spring.banner.location=classpath:banners/project-banner.txt
~~~

Khi ấy lưu file tại `src/main/resources/banners/project-banner.txt`. Nếu dùng chữ tiếng Việt, nên lưu UTF-8, phù hợp với `spring.banner.charset` mặc định; hãy kiểm tra font và encoding thực tế của terminal nếu ký tự bị lỗi.

Banner nên chứa tên, phiên bản và thông tin nhận diện không nhạy cảm. Không đưa secret, token, password hay dữ liệu cá nhân vào banner vì terminal, build log hoặc hệ thống thu thập log có thể lưu lại nội dung đó.

## 6. Ba chế độ banner: `console`, `log`, `off`

Cấu hình `spring.main.banner-mode` điều khiển **banner**, không phải toàn bộ logging:

| Giá trị | Hành vi |
|---|---|
| `console` | In banner ra `System.out`, đây là hành vi mặc định. |
| `log` | Gửi banner qua hệ thống logging, chịu ảnh hưởng của logger, level, appender và filter. |
| `off` | Không in banner. |

Thí dụ:

~~~properties
spring.main.banner-mode=off
~~~

Có thể thay đổi trong lúc chạy:

~~~bash
./gradlew bootRun --args='--spring.main.banner-mode=log'
~~~

Hoặc cấu hình bằng Java trước khi khởi chạy:

~~~java
SpringApplication application =
        new SpringApplication(StartupLoggingDemo.class);
application.setBannerMode(org.springframework.boot.Banner.Mode.OFF);
application.run(args);
~~~

Đoạn trên **minh họa thay thế phần cấu hình trong phương thức `main`**, không phải chương trình độc lập. Nếu dùng nhiều nguồn đặt banner mode, cần áp dụng thứ tự ưu tiên cấu hình thực tế để tránh hiểu nhầm một giá trị đã được ghi đè.

**Hai nhầm lẫn phổ biến:**

- `spring.main.banner-mode=off` **không** tắt log INFO/WARN/ERROR. Nó chỉ tắt banner.
- `logging.level.root=OFF` không nhất thiết làm mất banner ở `console` mode, vì banner được in trực tiếp qua `System.out` chứ không qua một logger thông thường.

Khi banner chuyển sang `log` mode, nó có thể đi vào log file hoặc bị ẩn bởi cấu hình logging. Khi chọn `console`, banner có thể xuất hiện trên terminal dù bạn chỉ ghi các thông điệp logger vào file.

## 7. Điều khiển các dòng log startup

Spring Boot thường có những dòng log chứa tên main class, phiên bản Java, active profile, web server và thời gian khởi động. Mẫu minh họa:

~~~text
2026-01-01T10:00:00.000+07:00  INFO 1234 --- [boot-startup-demo] [main] c.e.startup.StartupLoggingDemo : Starting StartupLoggingDemo
~~~

Đây là **ví dụ định dạng**, không phải kết quả cố định. Timestamp, PID, thread và pattern phụ thuộc phiên bản Boot và cấu hình backend.

Muốn giảm bớt thông báo startup do chính `SpringApplication` ghi, có thể đặt:

~~~properties
spring.main.log-startup-info=false
spring.main.banner-mode=console
~~~

`spring.main.log-startup-info=false` tắt một nhóm thông tin startup của `SpringApplication`, bao gồm log về active profile. Nó **không tắt mọi logger**, không vô hiệu hóa log lỗi, cũng không tự tắt banner.

### Chế độ `--debug` không giống `logging.level.root=DEBUG`

- `--debug` hoặc `debug=true` tăng chi tiết cho **một nhóm** logger lõi liên quan Boot/embedded server và có thể giúp xem condition evaluation report.
- `logging.level.root=DEBUG` bật DEBUG ở root logger, khiến lượng thông điệp từ thư viện tăng rất nhiều.
- `logging.level.com.example.startup=DEBUG` chỉ nhắm mục tiêu package được chỉ định, phù hợp hơn khi debug code startup của chính mình.

Khi sự cố cần điều tra, hãy ưu tiên bật DEBUG có chọn lọc. Bật toàn bộ root logger ở DEBUG/TRACE trong thời gian dài có thể tạo log rất lớn và dễ đưa dữ liệu nhạy cảm vào hệ thống ghi log.

### Ghi log ra file

Khi dùng cấu hình mặc định của Spring Boot với Logback:

~~~properties
logging.file.name=logs/boot-startup-demo.log
spring.main.banner-mode=console
~~~

`logging.file.name` yêu cầu log được ghi ra file, thông thường vẫn giữ console output. Nhưng banner ở mode `console` đi trực tiếp ra stdout nên **không nhất thiết** có trong file log. Nếu muốn banner đi qua logger, xem xét `banner-mode=log` và kiểm tra appender/filter thực tế.

## 8. Khi nào dùng `logback-spring.xml`?

Nếu chỉ cần đặt mức log, `application.properties` đủ đơn giản và rõ ràng. Khi cần thay pattern, nhiều appender, rolling policy, format phức tạp hoặc điều kiện theo profile, hãy dùng cấu hình native của Logback.

Với Spring Boot 3.3, nên ưu tiên `logback-spring.xml` khi cần extension của Boot. File `logback.xml` tiêu chuẩn có thể bị Logback tự xử lý **rất sớm**, trước khi Boot hỗ trợ các extension như `<springProfile>` hoặc `<springProperty>`. Ngược lại, `logback-spring.xml` được Spring Boot điều phối khi môi trường thích hợp đã sẵn sàng.

Ví dụ tại `src/main/resources/logback-spring.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <springProfile name="dev">
        <logger name="com.example.startup" level="DEBUG"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đoạn này giả định dự án đang sử dụng **Logback với cấu trúc include chuẩn của Spring Boot 3.3**. Khi bật profile `dev`, logger của package ứng dụng có level DEBUG; root tiếp tục INFO. Nếu dự án đã có file cấu hình backend khác, cần hợp nhất thay vì giữ nhiều file cấu hình cạnh tranh.

Khi sử dụng file native ở vị trí không mặc định, có thể đặt:

~~~properties
logging.config=classpath:logging/custom-logback-spring.xml
~~~

Đồng thời bảo đảm file thực sự nằm ở `src/main/resources/logging/custom-logback-spring.xml`. Khi đổi sang Log4j2, phải dùng cấu hình và starter tương ứng; file Logback không có tác dụng cho backend khác.

Một ý quan trọng: **cấu hình native không làm thay đổi thứ tự bootstrap**. Nó chỉ định cách logging backend hoạt động tại những mốc mà Spring Boot có thể áp dụng cấu hình ấy.

## 9. Phân biệt banner, log và trạng thái ready

| Dấu hiệu | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| Banner xuất hiện | Bootstrap đã đi đến bước in banner. | Bean đã khởi tạo hoàn toàn hay server đã nhận request. |
| Log “Starting ...” | Phần startup đang chạy và logger đã ghi thông điệp. | Startup sẽ thành công. |
| Log “Started ...” | Context đã vượt qua các bước khởi tạo chính. | Các runner đã hoàn tất. |
| `ApplicationReadyEvent` | Luồng startup bình thường đã kết thúc các runner. | Mọi dependency bên ngoài luôn hoạt động khỏe. |
| Readiness probe thành công | Ứng dụng đang báo sẵn sàng theo kiểm tra của hệ thống tại thời điểm đó. | Mọi request trong tương lai đều thành công. |

Nếu ứng dụng lỗi sau khi banner xuất hiện, hãy tìm root cause của exception trong log. Nếu lỗi xảy ra **trước khi chuẩn bị xong environment hoặc trước khi in banner**, có thể không có banner và một phần cấu hình logging chưa được áp dụng hoàn chỉnh.

Thông báo `APPLICATION FAILED TO START` do failure analysis của Spring Boot cung cấp là thông tin **chẩn đoán lỗi khởi động**, không phải banner nhận diện ứng dụng được đọc từ `banner.txt`.

## 10. Gỡ lỗi khi banner hoặc log không như mong đợi

**Không thấy banner**

- Kiểm tra `spring.main.banner-mode`; một property từ command line có thể ghi đè cấu hình trong file.
- Xác nhận `banner.txt` nằm trên runtime classpath hoặc `spring.banner.location` chỉ đúng file.
- Nếu mode là `log`, kiểm tra logger, appender và log file. Nội dung có thể đi vào file thay vì terminal.
- Kiểm tra ứng dụng có thất bại quá sớm hay không. Không phải lần startup lỗi nào cũng đi đến bước in banner.
- Nếu banner sai dấu tiếng Việt hoặc màu, kiểm tra UTF-8, font và khả năng ANSI của terminal.

**Không thấy DEBUG/INFO**

- Kiểm tra backend đang dùng là Logback hay thư viện khác, và dependency trên classpath.
- So sánh logging level của root, package, từng logger; kiểm tra filter/appender.
- Xác nhận cấu hình nằm trong nguồn được tải **đủ sớm**; `@PropertySource` không thay thế config data bootstrap.
- Nếu dùng file native, kiểm tra `logback-spring.xml` hay `logging.config` đã được tìm thấy.
- Nếu chỉ ghi file, đừng suy ra “logger không chạy” chỉ vì terminal không hiển thị.
- Không nhầm `--debug` của Boot với việc bật DEBUG cho mọi logger.

**Log trước `run()` không tuân theo property**

Đó là điều có thể xảy ra vì Boot chưa hoàn thiện logging. Chỉ dựa vào cấu hình được nạp **sau khi `run()` bắt đầu** để định dạng những dòng đã phát trước đó là không hợp lý. Nếu cần chẩn đoán mã rất sớm, thiết kế logger/bootstrap tối giản và biết rõ backend đang ở trạng thái nào.

**Muốn xem thứ tự startup mà không bị log nhiễu**

Bắt đầu từ ví dụ mục 4. Đặt breakpoint ở `main`, listener `ApplicationEnvironmentPreparedEvent`, runner và dòng sau `run`. Dùng `System.out.println` chỉ cho các dấu mốc thực hành; trong ứng dụng thực tế hãy dùng logging API và level có chọn lọc.

## 11. Bài tập nhỏ tự kiểm chứng

1. Chạy ví dụ với `spring.main.banner-mode=console` và kiểm tra banner xuất hiện giữa dấu mốc environment và runner.
2. Đổi sang `off`. Banner mất đi, nhưng runner và các dòng log vẫn hoạt động.
3. Đổi sang `log`, quan sát banner dưới format logger hoặc trong file log nếu bạn đã cấu hình ghi file.
4. Đổi `logging.level.com.example.startup=INFO`, so sánh việc có/không có dòng `log.debug(...)` trong runner.
5. Bật `spring.main.log-startup-info=false` rồi so sánh các dòng startup của `SpringApplication`; xác nhận banner vẫn hiển thị khi mode là `console`.

### Tài liệu tham khảo theo Spring Boot 3.3

- Logging: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- SpringApplication và banner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Ghi nhớ:** logging cần được chuẩn bị từ bootstrap để có thông tin khi ứng dụng lỗi trước khi context được tạo. Banner là bước hiển thị nhận diện trong bootstrap, được điều khiển bởi `spring.main.banner-mode`. Banner, log “Started ...”, việc runner hoàn thành và trạng thái ready là **những mốc khác nhau**; phân biệt chúng giúp bạn cấu hình và chẩn đoán startup chính xác.
