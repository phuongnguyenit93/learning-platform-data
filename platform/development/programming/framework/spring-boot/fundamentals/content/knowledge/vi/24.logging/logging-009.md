# Logging khởi tạo sớm và vì sao một số nguồn cấu hình đến quá muộn

Logging là một trong những hạ tầng được Spring Boot chuẩn bị **rất sớm** trong quá trình khởi động. Điều này cần thiết vì nếu ứng dụng lỗi ngay khi đọc cấu hình, tạo `ApplicationContext` hoặc đăng ký bean, ta vẫn cần có log để biết chuyện gì xảy ra.

Tuy nhiên, hệ quả quan trọng là **không phải nguồn cấu hình nào cũng có mặt khi hệ thống logging bắt đầu hoạt động**. Một property được khai báo trong `@PropertySource`, một bean `@Configuration`, hoặc một đoạn code trong `@PostConstruct` có thể xuất hiện quá muộn để ảnh hưởng đến những dòng log đầu tiên. Đôi khi nó thậm chí quá muộn để cấu hình lại logging theo cách Spring Boot hỗ trợ.

Bài học giải thích trình tự khởi tạo logging, phân biệt các nguồn cấu hình xuất hiện sớm và muộn, cách sử dụng `logging.*`, `logback-spring.xml` và những extension point phù hợp, đồng thời nêu cách chẩn đoán khi logging không chạy như mong đợi.

## 1. Logging phải hoạt động trước cả ứng dụng

Một ứng dụng Spring Boot thông thường:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Bên trong `SpringApplication.run(...)` có nhiều công việc diễn ra **trước** khi các bean `@Component` hoặc `@Service` được tạo:

- Chuẩn bị listeners và các bước bootstrap.
- Tạo, chuẩn bị và bổ sung nguồn dữ liệu vào `Environment`.
- Xác định cấu hình logging ban đầu.
- Tạo `ApplicationContext` và nạp bean definitions.
- Refresh context, xử lý BeanPostProcessor và khởi tạo singleton.
- Chạy các runner và phát sự kiện ứng dụng đã sẵn sàng.

Nếu lỗi xảy ra ở một trong các bước đầu tiên, ứng dụng chưa có `ApplicationContext` hoàn chỉnh. Vì vậy, Spring Boot phải khởi tạo logging bằng cơ chế **ngoài vòng đời bean thông thường**, thay vì chờ một `@Bean LoggingService` được tạo.

### Sơ đồ hai mốc quan trọng

~~~text
main()
  |
  v
SpringApplication.run(...)
  |
  v
ApplicationStartingEvent
  |             Chưa có Environment đã chuẩn bị đầy đủ
  |             Chưa có ApplicationContext
  |             Logging có thể ở chế độ khởi tạo rất sớm
  v
Chuẩn bị Environment và configuration data
  |
  v
ApplicationEnvironmentPreparedEvent
  |             Environment đã sẵn sàng cho bước này
  |             Logging được cấu hình theo Environment
  |             Context vẫn chưa được tạo hoàn chỉnh
  v
Tạo và chuẩn bị ApplicationContext
  |
  v
Nạp @Configuration / @PropertySource / bean definitions
  |
  v
Refresh context, tạo bean, @PostConstruct
  |
  v
ApplicationStartedEvent, runners, ApplicationReadyEvent
~~~

Đây là sơ đồ khái quát. Spring Boot có các bước xử lý Environment và listener nội bộ với thứ tự cụ thể theo từng phiên bản; điều cần ghi nhớ là logging đã bắt đầu hoạt động **trước khi các bean ứng dụng được khởi tạo**.

## 2. Phân biệt khởi tạo logging ban đầu với cấu hình logging theo Environment

Trong quá trình bootstrap, có thể thấy hai giai đoạn có tính chất khác nhau:

1. **Khởi tạo rất sớm:** hệ thống cần có khả năng ghi các thông báo ban đầu, ngay cả khi Environment chưa được xử lý đầy đủ.
2. **Cấu hình theo Environment:** khi các property sources phù hợp đã được chuẩn bị, Spring Boot có thể áp dụng level, pattern, output file và cấu hình logging framework từ những giá trị đã biết.

Trong Spring Boot, `LoggingApplicationListener` là một thành phần quan trọng tham gia các giai đoạn này. Nó lắng nghe những event sớm của `SpringApplication`, sử dụng `LoggingSystem` tương ứng với hạ tầng logging có mặt, và thiết lập logging dựa trên thông tin có tại thời điểm đó.

Có thể hình dung:

~~~text
     Bootstrap logging
             |
             | nhận nguồn cấu hình phù hợp
             v
     Environment-based logging
             |
             | application context được tạo sau đó
             v
     Log của service/repository/controller
~~~

Không nên suy luận rằng tất cả các dòng log trong startup bắt buộc dùng cùng một pattern hoặc level. Những thông báo được phát **trước khi cấu hình cuối cùng được áp dụng** không thể được “định dạng lại” hay lọc lại về sau.

### 2.1. Tại sao cần biết hai giai đoạn?

Giả sử ứng dụng muốn bật debug cho package của mình:

~~~properties
logging.level.com.example.catalog=DEBUG
~~~

Nếu property này được đọc trong quá trình chuẩn bị Environment đúng lúc, những thông báo sau khi LoggingSystem nhận cấu hình sẽ dùng level mới. Nhưng nếu một log `DEBUG` đã bị lọc ra **trước** thời điểm ấy, nó sẽ không xuất hiện lại chỉ vì cấu hình sau đó đổi thành `DEBUG`.

Tương tự, khi đổi console pattern sau startup, những dòng đã in ra console không thể tự được in lại theo pattern mới.

## 3. Spring Boot dùng logging framework nào?

Spring Boot cung cấp abstraction `LoggingSystem` để làm việc với các backend logging phù hợp. Trong ứng dụng dùng `spring-boot-starter` và `spring-boot-starter-logging` mặc định, backend phổ biến là **Logback**, cùng với SLF4J làm API logging trong code ứng dụng.

Ví dụ service:

~~~java
package com.example.catalog.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogService.class);

    public void refreshCatalog() {
        log.info("Refreshing catalog");
    }
}
~~~

Service không cần biết cấu hình Logback cụ thể đang nằm trong file nào. Nó gọi SLF4J, còn hệ thống logging đang được cấu hình quyết định level, pattern, appender và đích xuất log.

Các dự án có thể thay backend sang **Log4j2** hoặc dùng cấu hình Java Util Logging tùy dependency. Tên file cấu hình native và khả năng tích hợp phụ thuộc backend đã chọn. Các ví dụ XML trong bài chủ yếu dùng Logback.

**Điểm cốt lõi:** Spring Boot quản lý logging rất sớm, chứ không chờ bean `CatalogService` hay một bean logger bất kỳ xuất hiện.

## 4. Các nhóm nguồn cấu hình theo thời điểm xuất hiện

Không phải nguồn property nào cũng được xử lý ở cùng một thời điểm.

| Nguồn cấu hình | Thời điểm liên quan | Dùng để cấu hình logging lúc Boot chuẩn bị Environment? |
|---|---|---|
| JVM system properties được truyền lúc khởi chạy | Có từ khi JVM bắt đầu | Thường có thể |
| Biến môi trường của process | Có trước khi ứng dụng chạy | Thường có thể |
| Command-line arguments của `SpringApplication` | Được đưa vào Environment trong bootstrap | Thường có thể |
| `application.properties` / `application.yml` theo Config Data | Được xử lý trong bước chuẩn bị Environment | Có, cho giai đoạn logging theo Environment |
| `application-{profile}.yml` | Được xử lý theo profile trong configuration data | Có, nếu profile được xác định đúng lúc |
| Config import được Boot hỗ trợ | Được xử lý trong Config Data bootstrap | Có, tùy nguồn và cách tích hợp |
| `EnvironmentPostProcessor` được đăng ký sớm | Tham gia xử lý Environment | Có thể, nếu được áp dụng trước khi logging lấy cấu hình |
| `@PropertySource` trên `@Configuration` | Khi context xử lý configuration classes | **Quá muộn cho logging bootstrap** |
| Bean `@ConfigurationProperties` | Khi bean binding/creation hoạt động | **Quá muộn cho logging bootstrap** |
| `@Bean` / `@PostConstruct` | Trong lifecycle tạo bean | **Quá muộn cho những log đã phát** |
| Thay đổi property lúc runtime | Sau khi context chạy | Không tự phát lại log cũ hay tự đồng bộ mọi backend |

Bảng nói về **cơ chế khởi tạo logging của Spring Boot**, không phải về việc một nguồn property có thể được bean sử dụng về sau hay không. Một `@PropertySource` đến muộn vẫn có thể hữu ích cho các bean thông thường; nó chỉ không phải công cụ đúng để quyết định logging từ những giai đoạn đầu.

## 5. Cấu hình logging thông thường bằng application.yml

Với hầu hết ứng dụng, `application.yml` hoặc `application.properties` là lựa chọn tự nhiên cho các thiết lập logging phổ biến:

~~~yaml
spring:
  application:
    name: catalog-service

logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
    org.springframework.web: WARN
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n"
~~~

Ý nghĩa:

- `logging.level.root`: level mặc định của root logger.
- `logging.level.com.example.catalog`: level cho logger/package liên quan.
- `logging.level.org.springframework.web`: giảm hoặc thay đổi mức ghi log của một khu vực framework.
- `logging.pattern.console`: thay pattern hiển thị console khi backend/logging configuration hỗ trợ property này.

Phiên bản `application.properties` tương ứng:

~~~properties
logging.level.root=INFO
logging.level.com.example.catalog=DEBUG
logging.level.org.springframework.web=WARN
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
~~~

Những property này được Boot đọc trong bước cấu hình logging dựa trên `Environment`, trước khi các singleton bean ứng dụng thông thường được sử dụng.

### 5.1. Nếu logging đã bắt đầu trước khi application.yml được đọc?

Các thông báo rất sớm có thể xuất hiện trước khi toàn bộ Config Data được xử lý. Vì vậy, có sự khác biệt giữa:

- Log từ lúc `SpringApplication` vừa bắt đầu.
- Log sau khi Environment đã được chuẩn bị và LoggingSystem nhận cấu hình.

Việc đặt `logging.level.*` trong `application.yml` là cách được Spring Boot hỗ trợ cho logging của ứng dụng, nhưng **không bảo đảm tác động ngược trở lại lên log đã phát trước thời điểm áp dụng cấu hình**.

## 6. Vì sao @PropertySource đến quá muộn?

Đây là một trường hợp quan trọng.

Giả sử bạn tạo file `src/main/resources/custom-logging.properties`:

~~~properties
logging.level.com.example.catalog=DEBUG
logging.pattern.console=%d{HH:mm:ss} %-5level %logger - %msg%n
~~~

Và import nó qua class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:custom-logging.properties")
public class CatalogConfiguration {
}
~~~

Lúc nào Spring xử lý `@PropertySource`? Trong quá trình phân tích `@Configuration` của application context, tức là **sau khi SpringApplication đã bắt đầu chuẩn bị logging**.

~~~text
SpringApplication khởi tạo logging
             |
             v
Environment-based logging setup
             |
             v
Tạo ApplicationContext
             |
             v
Phân tích CatalogConfiguration
             |
             v
Xử lý @PropertySource
             |
             v
custom-logging.properties được thêm vào Environment
             |
             v
Các bean khác có thể đọc property
~~~

Vì vậy, mặc dù một bean sau đó có thể nhìn thấy property `logging.level.com.example.catalog` từ Environment, **hệ thống logging đã bỏ qua mốc đọc cấu hình liên quan**.

### 6.1. Dấu hiệu nhận biết

Một tình huống thường thấy:

~~~java
@Component
class Diagnostics {

    private final Environment environment;

    Diagnostics(Environment environment) {
        this.environment = environment;
    }

    @PostConstruct
    void show() {
        System.out.println(
                environment.getProperty(
                        "logging.level.com.example.catalog"
                )
        ); // Có thể in ra DEBUG
    }
}
~~~

Nhưng log `DEBUG` của ứng dụng vẫn không xuất hiện. Hai sự thật có thể đồng thời đúng:

1. Property đã tồn tại trong Environment **ở thời điểm bean Diagnostics chạy**.
2. LoggingSystem đã được cấu hình **trước khi property đó được thêm vào**.

Đó là vấn đề **thời điểm cấu hình**, không nhất thiết là vấn đề binder hay tên property sai.

### 6.2. Đừng dùng @PropertySource để sửa logging sớm

Một cách làm sai hướng là thêm nhiều `@Import` hoặc đổi thứ tự `@Configuration` để hy vọng `@PropertySource` được xử lý trước LoggingSystem. Việc ấy không di chuyển được quá trình tạo bean/configuration class về trước các bootstrap event.

Cách đúng thường là chuyển property logging sang `application.yml`, biến môi trường, JVM system property hoặc nguồn Config Data được nạp trong bootstrap.

## 7. @ConfigurationProperties cũng đến quá muộn cho bootstrap logging

`@ConfigurationProperties` rất phù hợp để tổ chức cấu hình nghiệp vụ thành object Java, nhưng class này được bind khi Spring quản lý bean của ứng dụng.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.monitoring")
public record MonitoringProperties(boolean detailedLogs) {
}
~~~

~~~yaml
app:
  monitoring:
    detailed-logs: true
~~~

Không nên viết một bean trong `@PostConstruct` để sử dụng `MonitoringProperties` rồi mong nó điều khiển được các log đã phát khi Boot đang tải cấu hình:

~~~java
@Component
class LoggingInitializer {

    private final MonitoringProperties properties;

    LoggingInitializer(MonitoringProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    void initialize() {
        if (properties.detailedLogs()) {
            // Muộn để quyết định những log đã phát trước đó.
        }
    }
}
~~~

Property binding và logging bootstrap phục vụ hai giai đoạn khác nhau.

Nếu muốn đưa một giá trị `app.monitoring.detailed-logs` vào quyết định logging sớm, phải thiết kế cơ chế lấy giá trị **trực tiếp từ Environment hoặc Config Data ở giai đoạn bootstrap phù hợp**, không đi qua properties bean được tạo sau này.

## 8. Vì sao @Bean, CommandLineRunner và ApplicationReadyEvent không đủ sớm?

Một bean khai báo trong `@Configuration`:

~~~java
@Configuration(proxyBeanMethods = false)
class LoggingConfiguration {

    @Bean
    StartupLogConfigurer startupLogConfigurer() {
        return new StartupLogConfigurer();
    }
}
~~~

được xử lý sau khi context có mặt. `@PostConstruct` chạy trong lifecycle khởi tạo bean. `CommandLineRunner` và `ApplicationRunner` còn muộn hơn: chúng chạy sau khi context refresh hoàn tất.

Có thể hình dung:

~~~text
LoggingSystem được chuẩn bị
           |
           v
Spring context được tạo
           |
           v
@Bean / @PostConstruct
           |
           v
ApplicationStartedEvent
           |
           v
ApplicationRunner / CommandLineRunner
           |
           v
ApplicationReadyEvent
~~~

Một runner có thể gọi API để **thay đổi level từ thời điểm hiện tại trở đi**, nhưng không thể phục hồi log đã bị lọc trong các bước bootstrap. Với nhu cầu ghi log sau khi ứng dụng đã sẵn sàng, runner và event listener vẫn rất hữu ích; chỉ không phù hợp để cấu hình mọi thông báo từ đầu startup.

## 9. Chọn nguồn xuất hiện đủ sớm

Để các property `logging.*` có mặt khi Spring Boot áp dụng cấu hình dựa trên Environment, có thể chọn nguồn phù hợp.

### 9.1. JVM system property

Ví dụ:

~~~bash
java -Dlogging.level.root=DEBUG -jar catalog.jar
~~~

`-Dlogging.level.root=DEBUG` được JVM thiết lập trước khi `main()` chạy. Cần đặt `-D...` **trước** `-jar` để Java launcher nhận là JVM option.

### 9.2. Environment variable

Ví dụ trong shell POSIX:

~~~bash
export LOGGING_LEVEL_ROOT=DEBUG
java -jar catalog.jar
~~~

Ví dụ PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = 'DEBUG'
java -jar catalog.jar
~~~

Spring Boot hỗ trợ relaxed binding cho nhiều dạng property name. Đối với logging level theo package, một biến như:

~~~text
LOGGING_LEVEL_COM_EXAMPLE_CATALOG=DEBUG
~~~

có thể biểu diễn `logging.level.com.example.catalog`.

**Cẩn thận với logger theo tên class:** hệ thống environment-variable mapping thường chuyển tên về chữ thường, nên không phải lúc nào cũng giữ chính xác dạng chữ hoa/chữ thường của fully qualified class name. Nếu cần cấu hình một class logger cụ thể, `SPRING_APPLICATION_JSON` hoặc một property source giữ nguyên tên có thể phù hợp hơn.

### 9.3. Command-line argument của SpringApplication

~~~bash
java -jar catalog.jar --logging.level.com.example.catalog=DEBUG
~~~

Argument được Spring Boot đưa vào Environment theo cơ chế thông thường, phù hợp cho giai đoạn cấu hình logging theo Environment. Nhưng argument này vẫn không làm thay đổi log đã xảy ra trước khi Environment được xử lý.

### 9.4. application.yml

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
~~~

Cách này thường đơn giản nhất để version-control chính sách logging không nhạy cảm cùng ứng dụng.

### 9.5. Chọn nguồn đúng với yêu cầu

| Nhu cầu | Nguồn nên cân nhắc |
|---|---|
| Chính sách log mặc định của ứng dụng | `application.yml` hoặc `application.properties` |
| Override theo deployment | Environment variable / config ngoài artifact |
| Kiểm tra nhanh khi chạy local | Command-line argument |
| Giá trị cần tồn tại từ khi JVM bắt đầu | JVM system property / environment trước startup |
| Config Data tùy chỉnh cần nạp sớm | `spring.config.import` hoặc EnvironmentPostProcessor phù hợp |
| Điều chỉnh level sau khi chạy | LoggingSystem hoặc Actuator loggers, không phải cấu hình bootstrap |

Không nên dùng bean hoặc `@PropertySource` làm kênh đưa cấu hình logging tới bước đã diễn ra trước khi chúng được xử lý.

## 10. logging.config: xác định file cấu hình logging

Khi nhu cầu vượt quá `logging.level.*` hoặc `logging.pattern.*`, ứng dụng có thể sử dụng file cấu hình của backend logging.

Ví dụ với Logback:

~~~properties
logging.config=classpath:logback-spring.xml
~~~

Hoặc:

~~~yaml
logging:
  config: classpath:logback-spring.xml
~~~

`logging.config` được Boot sử dụng để xác định vị trí configuration file trong quá trình cấu hình LoggingSystem.

Có thể cung cấp giá trị bằng environment:

~~~bash
export LOGGING_CONFIG=file:/etc/catalog/logback-spring.xml
java -jar catalog.jar
~~~

Để startup thành công, resource được chỉ định phải có thể truy cập tại thời điểm LoggingSystem đọc file. Đừng đặt đường dẫn trong một bean sẽ chỉ tạo sau khi application context refresh.

### 10.1. logback.xml khác logback-spring.xml

Với Logback:

- `logback.xml` là tên file native mà Logback có thể tự phát hiện trong cơ chế khởi tạo riêng.
- `logback-spring.xml` là biến thể Spring Boot có thể kiểm soát việc tải và hỗ trợ các phần mở rộng Spring-specific.

Ví dụ Spring Boot extension:

~~~xml
<configuration>
    <springProperty
            scope="context"
            name="serviceName"
            source="spring.application.name"
            defaultValue="catalog"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%property{serviceName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <logger name="com.example.catalog" level="DEBUG"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đặt file là:

~~~text
src/main/resources/logback-spring.xml
~~~

Các thẻ `<springProperty>` và `<springProfile>` là phần mở rộng Spring Boot cho Logback. Khi muốn dùng chúng, nên để Boot điều phối việc tải file qua `logback-spring.xml` hoặc cấu hình LoggingSystem phù hợp.

Nếu đổi nguyên ví dụ sang `logback.xml` để Logback native tự đọc rất sớm, các extension Spring có thể không được nhận diện ở thời điểm đó.

### 10.2. Vì sao logback.xml có thể “đến trước” Spring Boot?

Một backend logging có thể tự khởi tạo khi code gọi SLF4J/Logback trước lúc Spring Boot chuẩn bị Environment. Khi đó:

~~~text
Logback native thấy logback.xml
            |
            v
Logback tự cấu hình
            |
            v
Spring Boot mới bắt đầu chuẩn bị Environment
            |
            v
Các giá trị Spring Environment chưa sẵn sàng cho native config ban đầu
~~~

Vì vậy, **càng khởi tạo sớm, càng ít dữ liệu Spring-specific có thể sử dụng**. `logback-spring.xml` giúp Boot kiểm soát quá trình load để hỗ trợ các extension phụ thuộc Environment.

Không phải `logback.xml` luôn sai. File native vẫn hữu ích nếu chỉ sử dụng cú pháp Logback chuẩn. Vấn đề nảy sinh khi ta kỳ vọng nó đọc Spring profile, Spring property hoặc các tính năng cần Boot extension trước khi môi trường sẵn sàng.

### 10.3. Lưu ý về Logback auto-scan

Spring Boot không hỗ trợ việc sử dụng an toàn mọi Spring-specific extension với cơ chế cấu hình lại tự động (`scan`) của Logback. Nếu Logback tự reload file rồi parse các thẻ `<springProfile>` hoặc `<springProperty>` ngoài bước Boot quản lý, có thể gặp lỗi nhận diện thẻ.

Khi dùng extension của Spring Boot trong `logback-spring.xml`, tránh bật Logback `scan="true"` một cách tùy tiện. Nếu cần thay đổi log level lúc runtime, xem xét API được hỗ trợ hoặc Actuator thay vì chỉ dựa vào native auto-scan.

## 11. Logback native substitution và Spring placeholder không giống nhau

Spring Environment và Logback có cách xử lý property riêng. Ví dụ trong `application.yml`, Spring placeholder thường có dạng:

~~~yaml
app:
  log-directory: ${APP_LOG_DIRECTORY:/var/log/catalog}
~~~

Trong Logback XML, việc tham chiếu property dùng semantics của Logback hoặc phần mở rộng `<springProperty>` tương ứng.

### 11.1. springProperty đọc từ Environment

~~~xml
<springProperty
        scope="context"
        name="logDir"
        source="app.log-directory"
        defaultValue="./logs"/>
~~~

Sau đó file có thể dùng property `logDir` trong cú pháp Logback tại chỗ phù hợp.

### 11.2. Không thay bằng @Value trong bean

Một bean như:

~~~java
@Value("${app.log-directory}")
String logDirectory;
~~~

chỉ được inject khi bean đã được tạo. Nó không cung cấp sớm giá trị cho Logback nếu hệ thống logging đã cấu hình file appender trước đó.

### 11.3. Cách ghi default và property name phải đúng cú pháp của từng hệ thống

Spring placeholder, Logback variable substitution và Spring Boot `springProperty` không hoàn toàn cùng parser. Đừng copy nguyên một cú pháp default từ YAML sang XML mà không kiểm tra tài liệu của công cụ đang đọc chuỗi đó.

## 12. Logging ra file: chọn cấu hình đúng thời điểm

Spring Boot hỗ trợ những property phổ biến cho log file như:

~~~properties
logging.file.name=logs/catalog.log
~~~

hoặc:

~~~properties
logging.file.path=logs
~~~

Theo cơ chế Boot, `logging.file.name` chỉ định file cụ thể; `logging.file.path` chỉ định thư mục (với tên file mặc định theo convention khi không đặt tên riêng). Nếu cùng được khai báo, cách ưu tiên phụ thuộc semantics của Boot; với cấu hình thông thường, tên file cụ thể thường được ưu tiên.

### 12.1. Cấu hình volume phải có trước lúc logging mở file

Một appender có thể cần mở file trong giai đoạn logging initialization. Nếu thư mục mount chưa tồn tại, thiếu quyền hoặc disk đầy, lỗi có thể xảy ra **trước khi bean khởi tạo xong**.

Ví dụ container deployment phải mount volume và thiết lập permission từ trước:

~~~text
Container start
      |
      v
Filesystem / mounted log directory available
      |
      v
JVM và Spring Boot khởi động
      |
      v
Logging backend mở file
      |
      v
ApplicationContext được tạo
~~~

Không nên có `@PostConstruct` tạo thư mục log rồi cho rằng nó luôn chạy trước FileAppender. Nếu cần một đường dẫn logging, hãy chuẩn bị filesystem từ deployment hoặc bootstrap process trước thời điểm LoggingSystem dùng đường dẫn đó.

Trong container, ghi log ra stdout/stderr để hệ thống thu thập thường đơn giản hơn quản lý file appender trong từng instance, trừ khi có yêu cầu vận hành cụ thể.

## 13. Profile-specific logging có thể cấu hình từ Config Data

Ví dụ:

`application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

`application-dev.yml`:

~~~yaml
logging:
  level:
    com.example.catalog: DEBUG
~~~

`application-prod.yml`:

~~~yaml
logging:
  level:
    root: WARN
    com.example.catalog: INFO
~~~

Khi profile `dev` hoặc `prod` được xác định trong quá trình chuẩn bị Environment, Boot có thể nạp configuration data tương ứng trước khi áp dụng logging theo Environment.

Cách chỉ định profile ngoài ứng dụng:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

Hoặc:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog.jar
~~~

### 13.1. Vì sao @Profile trên @Configuration không giải quyết log khởi tạo sớm?

~~~java
@Configuration
@Profile("dev")
class DebugLoggingConfiguration {
    // ...
}
~~~

Class `DebugLoggingConfiguration` vẫn được xét khi Spring context xử lý configuration classes. Nó không làm logging của `ApplicationStartingEvent` hoặc những bước trước đó thay đổi.

Hãy dùng `application-dev.yml` hoặc Logback `<springProfile>` trong file được Boot load đúng giai đoạn, thay vì cố cấu hình logging sớm bằng `@Profile` + `@Bean`.

### 13.2. Profile có thể xuất hiện quá muộn trong code

Nếu một bean cố gọi một API để thêm active profile sau khi context refresh, việc đó không làm Spring Boot tự đọc lại toàn bộ Config Data và tái cấu hình logging như một startup mới.

Profile cần được cấp/định trước ở giai đoạn Boot chuẩn bị Environment nếu muốn nó ảnh hưởng đến config data và logging bootstrap.

## 14. EnvironmentPostProcessor: bổ sung property trước khi logging dùng Environment

Khi ứng dụng/thư viện cần bổ sung một `PropertySource` **trong bootstrap**, Spring Boot có `EnvironmentPostProcessor`.

Ví dụ tạo những giá trị mặc định không nhạy cảm cho logging:

~~~java
package com.example.catalog.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class LoggingDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> defaults = Map.of(
                "logging.level.com.example.catalog", "INFO"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogLoggingDefaults", defaults)
        );
    }
}
~~~

Trong JAR của ứng dụng/thư viện, đăng ký processor qua:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.catalog.boot.LoggingDefaultsEnvironmentPostProcessor
~~~

Spring Boot nhận diện processor đăng ký đúng cách và chạy nó trong giai đoạn xử lý Environment.

### 14.1. Vì sao addLast?

`addLast` đưa property source này xuống mức ưu tiên thấp hơn những source đã có trong Environment. Điều này phù hợp cho **default**, để environment variable, command-line argument hoặc config do người vận hành cung cấp không bị ghi đè ngoài ý muốn.

Nếu muốn override những source khác, phải cân nhắc rõ chính sách ưu tiên và vị trí chèn source. Không nên đặt source tự tạo lên đầu chỉ vì muốn một debug level luôn thắng cấu hình production.

### 14.2. EnvironmentPostProcessor vẫn có thời điểm của nó

EnvironmentPostProcessor được thiết kế cho giai đoạn Environment và có thể ảnh hưởng đến cấu hình logging được áp dụng sau đó, khi được đăng ký/ordered đúng. Nó **không nhất thiết thay đổi những thông báo xuất hiện trước khi Environment xử lý**, chẳng hạn log từ bước bootstrap cực sớm.

Nếu cần chạy trước/sau một EnvironmentPostProcessor khác, xem xét ordering và phụ thuộc giữa các bước bootstrap. Không dựa vào component scanning hoặc `@Component` để đăng ký processor này, vì component scanning đến muộn.

### 14.3. Không gọi logger/bean phức tạp trong processor quá sớm

Một EnvironmentPostProcessor không nên yêu cầu repository/service bean. Ngay cả việc ghi log cũng cần cẩn thận vì logging có thể chưa được cấu hình cuối cùng. Giữ processor nhỏ, deterministic, không phụ thuộc AOP hoặc database.

Nếu logic yêu cầu đọc remote config, nó có thể kéo dài hoặc làm startup thất bại; cần có chính sách timeout/failure phù hợp thay vì coi environment processing như nơi chạy nghiệp vụ.

## 15. spring.config.import và nguồn cấu hình external

Từ Spring Boot 2.4, cơ chế Config Data cho phép sử dụng `spring.config.import` để nạp thêm configuration data từ các vị trí được hỗ trợ.

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/catalog/logging-extra.properties"
~~~

Nếu file tồn tại và được nạp đúng trong giai đoạn Config Data, các property như:

~~~properties
logging.level.com.example.catalog=DEBUG
~~~

có thể có mặt trước khi LoggingSystem áp dụng phần cấu hình theo Environment.

### 15.1. “optional” không phải công cụ bảo mật hoặc bảo đảm cấu hình

Tiền tố `optional:` cho phép vị trí import vắng mặt theo semantics của Config Data. Nếu cấu hình logging bên ngoài là bắt buộc theo chính sách vận hành, nên cân nhắc loại bỏ `optional:` hoặc có kiểm tra triển khai tương ứng.

### 15.2. Custom config source phải tham gia đúng bootstrap phase

Nếu thư viện định nghĩa một vị trí config import đặc biệt hoặc remote configuration, nó phải tích hợp với Config Data/Environment processing ở thời điểm phù hợp. Một bean xuất hiện sau refresh rồi thêm property vào Environment không thể đóng vai trò tương đương với một Config Data source đã được nạp trong bootstrap.

## 16. Vì sao thay đổi Environment sau startup không tự áp dụng logging?

Giả sử sau khi ứng dụng đã chạy:

~~~java
ConfigurableEnvironment environment = ...;

environment.getPropertySources().addFirst(
        new MapPropertySource(
                "runtimeOverride",
                Map.of("logging.level.com.example.catalog", "TRACE")
        )
);
~~~

Lệnh trên thay đổi những property mà `Environment` trả về sau thời điểm đó. Nhưng **LoggingSystem không tự động đăng ký một watcher cho mọi thay đổi property sources của Environment** rồi cấu hình lại backend mỗi khi giá trị đổi.

Do đó:

~~~text
Environment value được thay đổi
            |
            v
Environment.getProperty(...) trả về giá trị mới
            |
            X
Không tự động buộc LoggingSystem reinitialize
            |
            v
Logger level thực tế có thể giữ giá trị cũ
~~~

Một cách đúng khi cần thay level động là gọi API quản lý logging phù hợp hoặc sử dụng Spring Boot Actuator nếu ứng dụng cho phép.

### 16.1. LoggingSystem.setLogLevel(...)

Ví dụ minh họa thay đổi mức log trong lúc ứng dụng chạy:

~~~java
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.logging.LoggingSystem;

public class RuntimeLogLevelManager {

    private final LoggingSystem loggingSystem;

    public RuntimeLogLevelManager(LoggingSystem loggingSystem) {
        this.loggingSystem = loggingSystem;
    }

    public void enableDebug() {
        loggingSystem.setLogLevel(
                "com.example.catalog",
                LogLevel.DEBUG
        );
    }
}
~~~

Đây là API quản lý level của hệ thống logging; nó **tác động từ lúc được gọi trở đi**, không phục hồi những dòng log đã bị lọc trong quá khứ. Cách cung cấp instance `LoggingSystem` phụ thuộc vào cấu hình/framework; ví dụ trên minh họa việc dùng API sau khi đã có đối tượng phù hợp.

Không nên dùng `@PostConstruct` gọi API này chỉ để “sửa” một `@PropertySource` được nạp muộn. Nếu có thể đưa property vào Config Data ban đầu, cách đó rõ ràng và dễ vận hành hơn.

### 16.2. Actuator loggers endpoint

Khi có Spring Boot Actuator, endpoint `loggers` có thể cho phép xem và trong cấu hình phù hợp có thể điều chỉnh logger level lúc runtime.

Ví dụ xem (khi endpoint được expose và được cấp quyền):

~~~text
GET /actuator/loggers/com.example.catalog
~~~

Việc bật endpoint và quyền chỉnh sửa phải được kiểm soát. Không expose chức năng điều chỉnh log level ra internet công khai mà không có authentication/authorization và chính sách vận hành.

## 17. Thứ tự listener và rủi ro can thiệp quá muộn

Spring Boot khởi tạo hệ thống logging bằng các listener/hạ tầng bootstrap. Nếu code ứng dụng cũng đăng ký listener cho event sớm, **thứ tự listener** có thể ảnh hưởng việc property đã sẵn sàng khi LoggingSystem lấy cấu hình hay chưa.

Ví dụ:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new CustomEnvironmentListener());
app.run(args);
~~~

Nếu `CustomEnvironmentListener` lắng nghe `ApplicationEnvironmentPreparedEvent` và thay đổi property sources, cần xét vị trí của nó so với các listener nội bộ của Boot.

Một listener chạy **sau** khi Boot đã đọc logging property không thể tự thay đổi những log đã được phát. Thay vì dựa vào những order number nội bộ và hành vi có thể thay đổi theo phiên bản, cách bền vững hơn để cung cấp configuration data là `spring.config.import` hoặc `EnvironmentPostProcessor` được Boot quản lý.

### 17.1. Early listener không phải @EventListener bean

Ví dụ sau không phải cách đáng tin cậy để xử lý Environment trước khi context tồn tại:

~~~java
@Component
class EarlyLoggingBeanListener {

    @EventListener
    void onEnvironmentPrepared(
            ApplicationEnvironmentPreparedEvent event) {
        // Bean này chỉ được tạo sau khi context bắt đầu xử lý bean.
    }
}
~~~

Event đã xảy ra trước khi bean `EarlyLoggingBeanListener` được tạo. Đăng ký listener bằng SpringApplication hoặc metadata bootstrap nếu thật sự cần nhận event sớm. Tuy nhiên, với mục đích chính là bổ sung property logging, ưu tiên extension point cấu hình thay vì listener.

## 18. Logging config backend và application.properties có thể cùng tồn tại

Một ứng dụng có thể có:

~~~text
src/main/resources/
├── application.yml
└── logback-spring.xml
~~~

Trong `application.yml`:

~~~yaml
spring:
  application:
    name: catalog-service

logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
~~~

Trong `logback-spring.xml`, bạn có thể khai báo appender, encoder, pattern hoặc logger riêng theo nhu cầu backend.

Điều quan trọng là **hiểu nguồn sở hữu một thiết lập**. Nếu vừa khai báo level trong file Logback vừa dùng `logging.level.com.example.catalog` trong Environment, Spring Boot có thể áp dụng level từ Environment thông qua LoggingSystem theo thứ tự khởi tạo. Người vận hành cần có một chính sách rõ về chỗ cấu hình level, tránh hai nguồn mâu thuẫn khiến kết quả khó giải thích.

### 18.1. Không dùng bean để cấu hình appender từ đầu

Ví dụ tạo một bean `AppenderConfigurator` rồi đợi nó chạy sau refresh không phải cách tự nhiên để thiết lập file appender từ dòng log đầu tiên. Với backend như Logback/Log4j2, dùng file cấu hình backend được Boot tải đúng thời điểm hoặc một extension point bootstrap được thiết kế rõ ràng.

Nếu cần custom appender hoặc integration nâng cao, cần lưu ý lifecycle của backend, class loading và quy tắc khởi tạo trước context.

## 19. Log xuất hiện trên console nhưng không có trong file

Một hiện tượng thường gặp là:

- Dòng log startup sớm xuất hiện trên console.
- Những dòng log về sau xuất hiện trong file.
- Hoặc ngược lại, một số phần đầu không nằm trong file đang mong đợi.

Điều này có thể xảy ra khi backend logging dùng một cấu hình tạm ở giai đoạn đầu rồi mới áp dụng file appender theo Environment. Những dòng đã in ra không nhất thiết được lưu lại và ghi bù vào file appender sau đó.

Cần kiểm tra:

1. `logging.file.name`/`logging.file.path` có được cung cấp trước bước logging setup không?
2. `logging.config` có chỉ đúng resource và backend không?
3. Filesystem có tồn tại và có quyền ghi trước khi file appender mở không?
4. Logback/Log4j2 đã tự khởi tạo bằng một native config khác từ rất sớm chưa?
5. Có nhiều backend/binding trên classpath gây chọn hệ thống logging khác với kỳ vọng không?

Không nên cố tìm một `@PostConstruct` để “ghi lại mọi log startup vào file”, vì framework không mặc nhiên lưu lại toàn bộ dòng đã phát từ trước.

## 20. Tác động của cấu hình logging đến performance và an toàn

Bật `DEBUG` hoặc `TRACE` quá rộng trong production có thể tạo lượng log rất lớn ngay từ giai đoạn bootstrap, ảnh hưởng I/O, ổ đĩa và khả năng quan sát lỗi quan trọng.

Một cấu hình cân nhắc thường có:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework: INFO
    com.example.catalog: INFO
~~~

Khi cần điều tra một package:

~~~yaml
logging:
  level:
    com.example.catalog.integration: DEBUG
~~~

Ngoài lưu lượng, log có thể chứa dữ liệu nhạy cảm:

- URL có token/query parameters.
- Header xác thực và cookie.
- Password/secret khi cấu hình lỗi.
- Payload từ request/response hoặc SQL parameter.
- Exception message tự nối dữ liệu người dùng.

Hãy hạn chế mức log chi tiết theo phạm vi cần thiết, không in toàn bộ Environment để điều tra một property, và tránh debug toàn bộ package framework trong production nếu chưa đánh giá tác động.

### 20.1. Logging quá sớm không có đầy đủ hệ thống quan sát

Khi context chưa tồn tại, những tính năng như tracing context, request correlation ID, MDC do servlet filter thêm hoặc exporter dựa trên Spring bean có thể chưa hoạt động.

Do đó, các log rất sớm có thể thiếu trace ID/request ID so với log của request về sau. Đây không nhất thiết là lỗi pattern; đơn giản là request context và các bean quan sát chưa được tạo.

Nếu cần liên hệ log bootstrap với một instance, có thể dùng metadata triển khai không nhạy cảm, ví dụ pod name hoặc process identifier khi backend/log pattern hỗ trợ, thay vì mong servlet filter hoạt động trước context.

## 21. Chẩn đoán: một property có nhưng logging vẫn không thay đổi

Giả sử bean in ra:

~~~java
System.out.println(
        environment.getProperty(
                "logging.level.com.example.catalog"
        )
);
~~~

và kết quả là `DEBUG`, nhưng log vẫn ở `INFO`.

Để điều tra, phân biệt hai câu hỏi:

1. **Giá trị hiện tại trong Environment là gì?**
2. **LoggingSystem đã đọc và áp dụng giá trị nào, vào thời điểm nào?**

Có thể thực hiện tuần tự:

- Xác định nguồn tạo property: `application.yml`, command-line, environment, config import, `@PropertySource` hoặc source được thêm sau startup.
- Kiểm tra property có mặt từ bước chuẩn bị Environment hay chỉ xuất hiện khi context xử lý bean.
- Kiểm tra logger name chính xác; logger có thể là fully qualified class thay vì package.
- Kiểm tra level effective của logger trong backend; level của parent/root có thể ảnh hưởng.
- Kiểm tra có custom `logback-spring.xml`, `logback.xml` hoặc `logging.config` và chúng có mâu thuẫn không.
- Kiểm tra backend được chọn trên classpath; không mặc định mọi dự án đều dùng Logback.
- Nếu thay đổi runtime, xác nhận đã gọi API đổi level, thay vì chỉ thay đổi Environment.
- Nếu vấn đề chỉ nằm ở log rất sớm, xác định liệu log đã phát **trước** thời điểm Boot áp dụng cấu hình hay không.

### 21.1. Không chỉ dựa vào log trong @PostConstruct

`@PostConstruct` xảy ra muộn hơn logging bootstrap. Log/print tại đây cho thấy trạng thái của lúc bean khởi tạo, không chứng minh rằng logging đã dùng cùng giá trị đó ở thời điểm `ApplicationStartingEvent`.

### 21.2. Bật debug trong môi trường kiểm thử có chủ đích

Có thể chạy:

~~~bash
java -jar catalog.jar --logging.level.org.springframework.boot=DEBUG
~~~

hoặc:

~~~bash
java -jar catalog.jar --debug
~~~

`--debug` trong Spring Boot không đồng nghĩa bật TRACE cho toàn bộ ứng dụng. Nó kích hoạt một số chế độ/nhóm log debug hữu ích và có thể tạo Condition Evaluation Report theo hành vi của phiên bản đang dùng.

Không nên sử dụng những thiết lập debug này lâu dài ở production nếu chưa có kế hoạch quản lý dữ liệu và dung lượng log.

## 22. Kiểm thử cấu hình logging cần đúng mức bootstrap

Một test chỉ kiểm tra:

~~~java
assertThat(environment.getProperty(
        "logging.level.com.example.catalog"
)).isEqualTo("DEBUG");
~~~

sẽ không đủ để chứng minh LoggingSystem đã áp dụng level đó **đúng thời điểm**.

Có thể kiểm thử theo hai lớp:

### 22.1. Test phần config data/binding

Đảm bảo property ở file config hoặc môi trường kiểm thử được nạp đúng. Test này phù hợp để xác nhận cấu trúc config và thứ tự nguồn của property.

### 22.2. Test startup logging thực tế

Chạy một `SpringApplication` nhỏ hoặc ứng dụng test theo đúng cơ chế khởi động để quan sát log được phát ở giai đoạn phù hợp.

Ví dụ minh họa một context không có web server:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

public class LoggingStartupProbe {

    @Configuration(proxyBeanMethods = false)
    static class ProbeConfiguration {
    }

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProbeConfiguration.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setDefaultProperties(
                java.util.Map.of(
                        "logging.level.com.example.catalog",
                        "DEBUG"
                )
        );

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            // Context đã chạy; quan sát log khởi động từ process.
        }
    }
}
~~~

Ví dụ dùng `setDefaultProperties` để đưa giá trị vào Environment trước khi Boot bắt đầu quá trình chạy. Tuy nhiên, nó vẫn thuộc cấu hình Environment, không có nghĩa log từ những bước trước Environment setup phải được in lại.

Khi viết test tự động, nên dùng công cụ capture output phù hợp và tránh assert cứng format log hoặc timestamp giữa những backend/phiên bản khác nhau. Nếu test thay đổi global logging state, cần cô lập test để không ảnh hưởng đến test khác trong cùng JVM.

## 23. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `logging.level.*` trong `@PropertySource` không có tác dụng | `@PropertySource` được xử lý sau logging bootstrap | Chuyển sang `application.yml`, ENV, system property hoặc Config Data |
| Bean đọc được `DEBUG` nhưng log vẫn ở `INFO` | Property đến muộn hoặc logger/backend chưa áp dụng lại | Kiểm tra thời điểm nguồn được thêm; dùng runtime log-level API nếu cần |
| `@PostConstruct` đặt logger level nhưng không ảnh hưởng log đầu startup | Bean chạy sau khi log đã phát | Đưa cấu hình logging lên bootstrap |
| `<springProfile>` không được Logback nhận | File `logback.xml` bị native Logback tải quá sớm | Dùng `logback-spring.xml` do Boot quản lý |
| Logback báo lỗi extension khi reload | Bật native scan với Spring-specific tags | Tránh scan tùy tiện với extension, dùng cơ chế điều chỉnh phù hợp |
| Dòng log đầu không có trong file | File appender chưa được áp dụng khi dòng đó phát | Hiểu hai pha logging; cấu hình output đủ sớm |
| File appender mở lỗi | Thư mục chưa tồn tại hoặc thiếu permission | Chuẩn bị filesystem/volume trước khi chạy JVM |
| Level class logger không đúng từ ENV | Mất case trong relaxed environment-variable mapping | Dùng property source giữ nguyên tên hoặc `SPRING_APPLICATION_JSON` |
| Config logging ở remote source không tác động startup | Source được đọc bởi bean sau refresh | Tích hợp Config Data/Environment sớm |
| Đổi property lúc runtime nhưng level không đổi | LoggingSystem không tự quan sát mọi thay đổi của Environment | Dùng LoggingSystem/Actuator loggers hoặc cơ chế reconfiguration |
| Log startup thiếu trace ID | Tracing/request infrastructure chưa sẵn sàng | Phân biệt log bootstrap với log request |
| Actuator loggers không truy cập được | Endpoint chưa expose hoặc thiếu quyền | Cấu hình exposure/authentication có kiểm soát |
| Có hai backend logging trên classpath | Dependency/binding gây chọn backend ngoài dự kiến | Kiểm tra dependency tree và logging system thực tế |

## 24. Cách chọn đúng cơ chế theo yêu cầu

| Bạn cần điều gì? | Cơ chế nên dùng |
|---|---|
| Đặt log level mặc định theo package | `logging.level.*` trong `application.yml` |
| Override level theo deployment | Environment variable, command-line hoặc Config Data ngoài artifact |
| Ghi log ngay từ các thông báo bootstrap đầu tiên | Logging infrastructure sẵn có và những lựa chọn có thể cung cấp trước/ở đầu startup |
| Pattern/appender Logback có Spring profile/property | `logback-spring.xml` |
| File Logback native đơn giản, không dùng Spring extension | `logback.xml` có thể phù hợp |
| Nạp logging config từ file ở ngoài JAR | `logging.config` qua nguồn xuất hiện đúng bootstrap |
| Thêm property source trước khi context được tạo | `EnvironmentPostProcessor` hoặc Config Data extension |
| Thêm cấu hình ứng dụng cho bean sau khi context tạo | `@PropertySource` nếu phù hợp, **không** để điều khiển logging sớm |
| Điều chỉnh logger level ở runtime | LoggingSystem API hoặc Actuator loggers |
| Phân tích vì sao log bị thiếu | Xác định event time, property source time, backend và effective level |

### Checklist thiết kế

1. Xác định **log cần ảnh hưởng ở giai đoạn nào**: trước Environment, trong bootstrap hay sau context.
2. Đặt những property `logging.*` cần cho bootstrap vào nguồn **được Boot xử lý đủ sớm**.
3. Không phụ thuộc vào `@PropertySource`, `@Bean`, `@PostConstruct` hoặc runner để cấu hình những log đã phát.
4. Khi cần Spring-specific Logback extensions, dùng `logback-spring.xml` và tránh native scan không tương thích.
5. Kiểm soát backend và file/volume sẵn sàng trước khi LoggingSystem mở appender.
6. Không mặc định việc Environment thay đổi sẽ tự reconfigure toàn bộ logging.
7. Khi cần log-level động, dùng API quản lý phù hợp và bảo vệ endpoint chẩn đoán.
8. Không để logging quá chi tiết làm lộ secret hoặc làm quá tải hệ thống.
9. Với custom EnvironmentPostProcessor, giữ logic nhẹ và không phụ thuộc các Spring bean được tạo muộn.
10. Kiểm tra hành vi bằng startup thật nếu vấn đề liên quan **thời điểm** phát log.

## 25. Tổng kết

Logging của Spring Boot được khởi tạo sớm để ứng dụng có thể ghi nhận cả những lỗi xảy ra **trước khi ApplicationContext tồn tại**. Vì vậy, việc một property cuối cùng xuất hiện trong `Environment` không chứng minh rằng nó đã có mặt lúc LoggingSystem đọc cấu hình.

`application.yml`, environment variables, JVM properties và các nguồn Config Data được xử lý đúng giai đoạn là những cách thích hợp để cấu hình logging từ bootstrap. Ngược lại, `@PropertySource`, các phương thức `@Bean`, `@ConfigurationProperties` bean và `@PostConstruct` được xử lý khi context đã xây dựng, nên có thể quá muộn cho mục tiêu này.

**Nguyên tắc quan trọng nhất:** muốn điều khiển logging ở thời điểm nào, hãy cung cấp cấu hình **trước hoặc đúng thời điểm LoggingSystem sử dụng nó**. Phân biệt bootstrap logging, Environment-based logging và runtime log-level changes giúp tránh việc “property đã có mà log vẫn không đổi”, đồng thời làm quá trình vận hành ứng dụng Spring Boot dễ dự đoán hơn.
