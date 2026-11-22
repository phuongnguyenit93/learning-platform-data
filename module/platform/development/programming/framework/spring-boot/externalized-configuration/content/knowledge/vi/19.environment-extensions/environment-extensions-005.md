# Thuộc tính đọc sớm như logging.* và spring.main.*

## 1. Vấn đề: có những property phải có mặt trước khi bean được tạo

Spring Boot hỗ trợ **externalized configuration**: người phát triển đặt giá trị trong **application.properties**, **application.yml**, biến môi trường, Java system properties hoặc tham số dòng lệnh; ứng dụng đọc những giá trị này khi chạy.

Với nhiều property nghiệp vụ, ta có thể inject bằng **@Value**, đọc từ **Environment** hoặc bind qua **@ConfigurationProperties** sau khi container đã được chuẩn bị. Tuy nhiên, **không phải property nào cũng được đọc vào cùng một thời điểm**.

Một số thuộc tính điều khiển **chính quá trình khởi động ứng dụng**. Spring Boot cần quyết định hệ thống logging, loại ứng dụng web, thông tin startup hoặc vị trí Config Data **trước khi ApplicationContext hoàn tất refresh**.

Hai nhóm dễ gặp nhất:

- **logging.***: ví dụ **logging.level.root**, **logging.file.name**, **logging.config**.
- **spring.main.***: ví dụ **spring.main.banner-mode**, **spring.main.web-application-type**, **spring.main.log-startup-info**.

Nếu đưa những key này vào một nguồn chỉ được thêm **sau** khi chúng đã được đọc, nguồn đó có thể vẫn xuất hiện trong Environment về sau nhưng **không thay đổi được quyết định khởi động đã xảy ra**.

Tài liệu Spring Boot 3.3 nêu rõ: các nguồn cấu hình từ **@PropertySource** trên **@Configuration** class chỉ được thêm khi context đang refresh, vì vậy **quá muộn cho một số property như logging.* và spring.main.***.

Bài này giải thích ý nghĩa của “đọc sớm”, thời điểm xử lý, những nguồn cấu hình phù hợp, cách mở rộng Environment bằng **EnvironmentPostProcessor**, và cách chẩn đoán khi property tồn tại nhưng hiệu lực startup không đúng mong đợi.

Bối cảnh ví dụ: **Spring Boot 3.3.x**, **Java 21**, JAR chạy từ command line. Các đoạn lệnh là ví dụ kỹ thuật; không cần kết nối dịch vụ ngoài.

## 2. Phân biệt ba thời điểm quan trọng

Để hiểu thuộc tính đọc sớm, cần tách:

1. **Trước khi có ApplicationContext**: SpringApplication chuẩn bị Environment và các nguồn cấu hình ban đầu.
2. **Trong quá trình chuẩn bị/refresh ApplicationContext**: Spring tạo bean definitions, đọc @Configuration, xử lý @PropertySource và dựng các bean.
3. **Sau khi context đã sẵn sàng**: ApplicationRunner, CommandLineRunner và logic ứng dụng bắt đầu sử dụng các bean.

Sơ đồ giản lược:

~~~text
main(String[] args)
        |
        v
SpringApplication.run(args)
        |
        v
Chuẩn bị Environment
  - default properties
  - system properties / OS env
  - command-line arguments
  - Config Data: application.yml, profile files, imports
  - EnvironmentPostProcessor
        |
        v
Các cơ chế startup đọc cấu hình sớm
  - cấu hình logging
  - các quyết định spring.main.*
        |
        v
Tạo và chuẩn bị ApplicationContext
        |
        v
Refresh ApplicationContext
  - @Configuration, @PropertySource
  - tạo bean và bind @ConfigurationProperties
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
Ứng dụng sẵn sàng xử lý công việc
~~~

**Đây là sơ đồ khái niệm, không phải thứ tự tuyệt đối của từng callback nội bộ**. Spring Boot có nhiều event và bước setup; logging và environment preparation có thể có nhiều giai đoạn. Điều cần nhớ là **@PropertySource ở giai đoạn refresh không thể quay ngược thời gian để cấu hình mọi quyết định đã được thực hiện trước đó**.

### 2.1. Đọc sớm không có nghĩa là tất cả property được đọc cùng một nanosecond

Ví dụ:

- **spring.config.name**, **spring.config.location**, **spring.config.additional-location** phải có đủ sớm để xác định cần tìm Config Data ở đâu.
- **logging.config** hoặc **logging.level.root** được logging infrastructure sử dụng ở giai đoạn startup.
- **spring.main.web-application-type** giúp SpringApplication quyết định kiểu context/web application.
- Một field thuộc **@ConfigurationProperties(prefix = "app")** thường được bind khi bean configuration properties được tạo.

Vì vậy, câu “chỉ cần có giá trị trước khi ứng dụng ready” là **chưa đủ**. Phải biết **thành phần nào tiêu thụ property và thời điểm tiêu thụ**.

## 3. @PropertySource thường quá muộn cho logging.* và spring.main.*

Một ví dụ dễ gây hiểu lầm:

**src/main/java/com/example/boot/LatePropertiesConfiguration.java**:

~~~java
package com.example.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:late-startup.properties")
public class LatePropertiesConfiguration {
}
~~~

**src/main/resources/late-startup.properties**:

~~~properties
logging.level.root=DEBUG
spring.main.banner-mode=off
spring.main.web-application-type=none
~~~

Có thể thấy tên property hợp lệ, file tồn tại trên classpath, thậm chí về sau **Environment.getProperty("logging.level.root")** có thể nhìn thấy **DEBUG**. Nhưng điều đó **không chứng minh** logging đã được khởi tạo ở mức DEBUG ngay từ đầu, banner đã bị tắt hoặc kiểu web context đã được chọn lại.

**Nguyên nhân:** @PropertySource được thêm khi context refresh. Những quyết định startup nói trên có thể đã được thực hiện trước đó.

Không nên kỳ vọng các câu lệnh sau sẽ “sửa lại quá khứ”:

~~~java
@Value("${spring.main.banner-mode}")
private String bannerMode;
~~~

hoặc:

~~~java
@ConfigurationProperties(prefix = "spring.main")
public record MainSettings(String bannerMode) {
}
~~~

Các API đó có thể **đọc một giá trị**, nhưng không có nghĩa giá trị mới sẽ được SpringApplication áp dụng lại cho bước khởi động đã hoàn tất.

### 3.1. @PropertySource có vô dụng không?

Không. **@PropertySource** vẫn hữu ích khi cần đưa một file **.properties** tùy chọn vào Environment để những bean thông thường sử dụng sau đó.

Ví dụ:

~~~properties
app.report.title=Monthly Report
app.report.max-rows=200
~~~

Nếu một bean chỉ cần các giá trị này trong quá trình refresh hoặc sau refresh, @PropertySource có thể phù hợp với thiết kế.

Vấn đề chỉ xảy ra khi **chọn sai nguồn hoặc chọn sai thời điểm** cho những thuộc tính được tiêu thụ rất sớm.

Một lưu ý khác: **@PropertySource** không trực tiếp nạp các file YAML đa tài liệu theo cơ chế giống Config Data; Spring Boot khuyến nghị dùng cơ chế Config Data cho application.yml và các file profile.

## 4. Những nguồn nên dùng cho thuộc tính đọc sớm

Thông thường, lựa chọn an toàn và đơn giản nhất là một trong các nguồn Spring Boot hỗ trợ **trước khi context refresh**:

| Nguồn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Command-line arguments** | **--logging.level.root=DEBUG** | Cấp khi khởi chạy một lần |
| **OS environment variables** | **LOGGING_LEVEL_ROOT=DEBUG** | Cấp cho process/container |
| **Java system properties** | **-Dlogging.level.root=DEBUG** | Cấp cho JVM trước khi chạy JAR |
| **Config Data** | **application.yml**, file profile, import | Spring Boot nạp trong giai đoạn chuẩn bị Environment |
| **SpringApplication default properties** | **setDefaultProperties(...)** | Cung cấp giá trị thấp ưu tiên làm fallback |
| **EnvironmentPostProcessor** | Bổ sung một PropertySource sớm | Cho yêu cầu mở rộng Environment đặc biệt |

**Chọn nguồn dựa vào yêu cầu triển khai**, không dựa vào việc có thể tạo annotation nào.

Nếu chỉ muốn thay log level giữa local và production, **application.yml** hoặc biến môi trường thường đủ. Chỉ viết **EnvironmentPostProcessor** khi có một nhu cầu tích hợp cụ thể mà các nguồn tiêu chuẩn không giải quyết gọn.

## 5. Cấu hình sớm bằng application.yml

**src/main/resources/application.yml**:

~~~yaml
spring:
  main:
    banner-mode: "off"
    log-startup-info: false

logging:
  level:
    root: INFO
    com.example.boot: DEBUG
  file:
    name: "logs/sample-app.log"
~~~

Ý nghĩa:

- **spring.main.banner-mode=off**: tắt banner của Spring Boot ở lần khởi động.
- **spring.main.log-startup-info=false**: kiểm soát thông tin startup do SpringApplication ghi.
- **logging.level.root=INFO**: cấu hình mức logging gốc.
- **logging.level.com.example.boot=DEBUG**: áp dụng mức DEBUG cho logger/package tương ứng.
- **logging.file.name**: chỉ định tên file log, tùy logging system và cấu hình hiện có.

Cấu hình này được xử lý thông qua **Config Data**. Nó khác với việc chỉ định một file riêng bằng @PropertySource trong một @Configuration class.

**Lưu ý:** đường dẫn file log tương đối như **logs/sample-app.log** được hiểu tương đối theo working directory/process tùy logging setup. Container cần có đường dẫn và quyền ghi phù hợp; trong nhiều hệ thống container/cloud, ghi log ra stdout/stderr thường đơn giản hơn việc tự quản lý file log bên trong container.

### 5.1. application.properties tương đương

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=INFO
logging.level.com.example.boot=DEBUG
logging.file.name=logs/sample-app.log
~~~

Nên dùng một định dạng Config Data nhất quán trong ứng dụng, tránh có cả application.properties và application.yml cùng location với các giá trị mâu thuẫn.

### 5.2. “Early” không có nghĩa phải đưa tất cả vào command line

**application.yml là một nguồn Config Data được Spring Boot xử lý sớm** trong vòng đời khởi động. Bạn hoàn toàn có thể cấu hình nhiều thuộc tính **logging.*** và **spring.main.*** ở file này.

Lỗi thường gặp không phải “dùng file” nói chung, mà là **dùng một file chỉ được đưa vào Environment quá muộn**.

## 6. Cấu hình sớm qua command-line arguments

Ví dụ chạy một JAR:

~~~bash
java -jar app.jar \
  --logging.level.root=DEBUG \
  --spring.main.banner-mode=off \
  --spring.main.log-startup-info=false
~~~

Đây là các **option arguments** của ứng dụng, không phải Java **-D** system properties.

Spring Boot mặc định chuyển các option bắt đầu bằng **--** thành property của Environment. Vì vậy, chúng được cung cấp từ lúc SpringApplication xử lý arguments.

Ví dụ tắt web server:

~~~bash
java -jar app.jar \
  --spring.main.web-application-type=none
~~~

Khi **web-application-type=none** có hiệu lực, ứng dụng không khởi tạo web application context thông thường. Nếu dự án đang cung cấp REST API, việc không có web server là **kết quả dự kiến**, không nhất thiết là lỗi khởi động.

### 6.1. Command-line có thể được vô hiệu hóa trong code

Theo mặc định, command-line properties được thêm vào Environment. Nhưng chương trình có thể gọi:

~~~java
springApplication.setAddCommandLineProperties(false);
~~~

Khi đó, các option **--...** không còn được đưa vào Environment theo cơ chế mặc định nói trên. Vì vậy, nếu command line không có tác dụng, hãy kiểm tra xem ứng dụng có tùy chỉnh SpringApplication không.

Đừng kết luận mọi ứng dụng đều hỗ trợ command-line override chỉ vì Spring Boot mặc định như vậy; code bootstrap có thể thay đổi hành vi này.

## 7. Cấu hình sớm qua Java system properties

System property dùng cú pháp **-Dkey=value** và phải đặt ở phần tham số của JVM, trước **-jar**:

~~~bash
java \
  -Dlogging.level.root=DEBUG \
  -Dspring.main.banner-mode=off \
  -jar app.jar
~~~

Với **logging.config**:

~~~bash
java \
  -Dlogging.config=classpath:logback-spring.xml \
  -jar app.jar
~~~

Ví dụ này giả định ứng dụng sử dụng một logging system tương thích, có resource **logback-spring.xml** trong classpath.

Phân biệt:

~~~text
-Dlogging.level.root=DEBUG       -> Java system property
--logging.level.root=DEBUG       -> Spring Boot command-line property
LOGGING_LEVEL_ROOT=DEBUG         -> OS environment variable
~~~

Chúng có thể cùng mô tả một key, nhưng đến từ những PropertySource khác nhau và có vị trí ưu tiên khác nhau.

### 7.1. Đặt -D sai vị trí

Lệnh:

~~~bash
java -jar app.jar -Dlogging.level.root=DEBUG
~~~

không có cùng ý nghĩa với việc đưa **-D** trước **-jar**. Sau **-jar**, chuỗi này thuộc arguments của ứng dụng, không phải JVM system property được đặt bởi launcher theo cú pháp chuẩn.

Nếu muốn dùng Spring Boot application argument sau JAR, dùng **--logging.level.root=DEBUG**.

## 8. Cấu hình sớm qua biến môi trường

Biến môi trường đặc biệt phù hợp với container và pipeline deploy.

Ví dụ trên Linux/macOS:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG \
SPRING_MAIN_BANNER_MODE=off \
SPRING_MAIN_LOGSTARTUPINFO=false \
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "DEBUG"
$env:SPRING_MAIN_BANNER_MODE = "off"
$env:SPRING_MAIN_LOGSTARTUPINFO = "false"

java -jar app.jar
~~~

Các tên biến theo quy tắc Spring Boot cho **relaxed binding**:

1. Dấu chấm **.** được đổi thành dấu gạch dưới **_**.
2. Dấu gạch ngang **-** trong mỗi segment được **loại bỏ**.
3. Các chữ cái chuyển thành chữ hoa.

| Property canonical | Biến môi trường |
| --- | --- |
| **logging.level.root** | **LOGGING_LEVEL_ROOT** |
| **logging.file.name** | **LOGGING_FILE_NAME** |
| **logging.config** | **LOGGING_CONFIG** |
| **spring.main.banner-mode** | **SPRING_MAIN_BANNERMODE** |
| **spring.main.log-startup-info** | **SPRING_MAIN_LOGSTARTUPINFO** |
| **spring.main.web-application-type** | **SPRING_MAIN_WEBAPPLICATIONTYPE** |
| **spring.main.lazy-initialization** | **SPRING_MAIN_LAZYINITIALIZATION** |
| **spring.config.name** | **SPRING_CONFIG_NAME** |
| **spring.config.additional-location** | **SPRING_CONFIG_ADDITIONALLOCATION** |

**Điểm rất dễ nhầm:** tên chuẩn cho **spring.main.banner-mode** là **SPRING_MAIN_BANNERMODE**, không phải **SPRING_MAIN_BANNER_MODE**. Dấu gạch ngang bị loại bỏ, không phải thay bằng dấu gạch dưới mới. Vì vậy khi thử nghiệm, nên tuân thủ tên được Spring Boot tài liệu hóa cho relaxed binding.

Một số công cụ có thể áp dụng quy tắc riêng khi chuyển biến môi trường sang property. Khi một biến không hoạt động, kiểm tra chính xác tên canonical, tên biến đã đặt và quá trình truyền vào **process Java**.

### 8.1. Ví dụ Docker Compose

~~~yaml
services:
  app:
    image: example/boot-early-config:1.0.0
    environment:
      LOGGING_LEVEL_ROOT: "INFO"
      SPRING_MAIN_BANNERMODE: "off"
      SPRING_MAIN_LOGSTARTUPINFO: "false"
      SPRING_MAIN_WEBAPPLICATIONTYPE: "servlet"
~~~

Đây là ví dụ một image đã có sẵn. Docker Compose đưa các giá trị string vào môi trường container; Spring Boot tiếp nhận khi process khởi động.

Nếu sử dụng **SPRING_MAIN_WEBAPPLICATIONTYPE=none** ở một ứng dụng chỉ phục vụ HTTP, đừng mong map port và curl vẫn nhận response từ embedded server. Đó chính là tác động của property startup này.

## 9. Thuộc tính logging.*: nên hiểu chính xác những gì?

**logging.*** điều khiển các khía cạnh khác nhau của logging infrastructure.

Ví dụ thường gặp:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.web=DEBUG
logging.file.name=logs/app.log
logging.config=classpath:logback-spring.xml
~~~

Không phải mọi key đều có cùng tác động:

- **logging.level.root**: mức log của logger gốc.
- **logging.level.<logger-name>**: mức của logger hoặc package.
- **logging.file.name**: tên file log khi logging system hỗ trợ.
- **logging.config**: yêu cầu nạp một file cấu hình logging cụ thể.

**logging.config** đáng chú ý vì logging system có thể cần file này khi chính nó được khởi tạo. Nếu giá trị chỉ được đưa vào Environment bởi một bean hoặc @PropertySource quá muộn, logging system có thể đã nạp cấu hình mặc định.

### 9.1. Thay đổi level package khác thay đổi level class cụ thể

Biến môi trường thông thường thuận tiện cho package-level logging:

~~~text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_WEB=DEBUG
~~~

Khi bind tên từ system environment, Spring Boot có quy tắc chữ thường hóa. Điều này có thể gây khó khăn với **tên class Java phân biệt chữ hoa/chữ thường**.

Nếu muốn chỉ định một logger/class chính xác như **com.example.payment.PaymentService**, việc dùng một tên biến môi trường viết hoa hoàn toàn không phải lúc nào cũng giữ nguyên được chữ hoa của tên class. Có thể dùng:

~~~properties
logging.level.com.example.payment.PaymentService=DEBUG
~~~

trong properties/YAML, hoặc dùng **SPRING_APPLICATION_JSON** với tên key phù hợp khi cần một cấu trúc JSON chứa tên logger chính xác.

### 9.2. Vì sao không nên dùng một bean để cấu hình log quá muộn?

Ví dụ:

~~~java
@Component
public class LateLogConfig {
    public LateLogConfig(Environment environment) {
        String level = environment.getProperty(
                "logging.level.root");
        System.out.println(level);
    }
}
~~~

Bean có thể đọc ra **DEBUG**, nhưng lúc constructor chạy, phần khởi động logging ban đầu đã diễn ra. Đọc giá trị không đồng nghĩa logging được khởi tạo lại với giá trị đó.

Có thể một hệ thống logging cho phép điều chỉnh level động thông qua API riêng, nhưng đó là **một cơ chế khác** với việc cấu hình **logging.*** ở startup.

### 9.3. Logback và tệp cấu hình riêng

Khi dùng Logback, Spring Boot thường khuyến nghị tên **logback-spring.xml** cho cấu hình có dùng các extension của Spring Boot, thay vì dựa vào **logback.xml** được logging framework nạp theo cách truyền thống.

Với cấu hình tùy chỉnh:

~~~properties
logging.config=classpath:logback-spring.xml
~~~

Nếu file không có hoặc dùng cú pháp không được hỗ trợ trong thời điểm nạp, quá trình khởi tạo logging có thể lỗi. Không nên đưa tên file logging vào @PropertySource rồi kỳ vọng logging system tự đọc lại nó.

## 10. Thuộc tính spring.main.*: định hình cách SpringApplication khởi động

Nhóm **spring.main.*** ảnh hưởng đến những quyết định của **SpringApplication**.

Một vài ví dụ:

| Property | Ý nghĩa khái quát |
| --- | --- |
| **spring.main.banner-mode** | Banner in ra console, log hay tắt |
| **spring.main.log-startup-info** | Có ghi thông tin startup do SpringApplication quản lý không |
| **spring.main.web-application-type** | Loại ứng dụng như **none**, **servlet**, **reactive** |
| **spring.main.lazy-initialization** | Cho phép lazy initialization trên phạm vi rộng khi được bật |
| **spring.main.allow-bean-definition-overriding** | Quyết định có cho phép bean definition overriding theo cấu hình phù hợp |

Những property khác nhau có thể được tiêu thụ ở các bước khác nhau, nhưng điểm chung là nhiều property trong nhóm này **cần có trước hoặc trong quá trình chuẩn bị context**, không phải sau khi toàn bộ bean đã được tạo.

### 10.1. Tắt banner từ Config Data

~~~yaml
spring:
  main:
    banner-mode: off
~~~

Giá trị **off** là enum/configuration value được Spring Boot hỗ trợ cho banner mode. Đặt trong **application.yml** là lựa chọn bình thường.

Nếu chương trình chỉ cần tắt banner một lần:

~~~bash
java -jar app.jar --spring.main.banner-mode=off
~~~

không cần viết @Configuration class hay tự xử lý banner sau startup.

### 10.2. Chuyển sang non-web application

~~~bash
java -jar app.jar \
  --spring.main.web-application-type=none
~~~

Tình huống này phù hợp với một số batch job, CLI tool hoặc ứng dụng không cần embedded web server.

Nhưng nếu chương trình thực sự cần khởi tạo servlet infrastructure, đổi kiểu web application có thể khiến các web components không còn được tạo hoặc không hoạt động như trước. Đây là **quyết định kiến trúc startup**, không chỉ là một cờ thông thường.

### 10.3. Lazy initialization không phải refresh config

~~~properties
spring.main.lazy-initialization=true
~~~

Property này ảnh hưởng đến việc các bean được khởi tạo theo cơ chế lazy. Nó không có nghĩa ứng dụng tự tải lại file cấu hình, và cũng không đồng nghĩa tất cả lỗi cấu hình được phát hiện ngay khi startup. Một số bean lazy có thể làm lỗi chỉ xuất hiện khi được sử dụng.

Vì thế, khi bật lazy initialization, càng cần hiểu khi nào các bean cấu hình/validation quan trọng được tạo.

## 11. Config Data và thuộc tính được dùng rất sớm để tìm file

Một nhóm property còn được sử dụng **sớm hơn một số cấu hình bình thường**:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
~~~

Chúng giúp Spring Boot xác định tên file và vị trí cần tìm **trong quá trình nạp Config Data**.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.name=myservice
~~~

Spring Boot sẽ tìm các tên file cấu hình tương ứng với **myservice** tại những location được áp dụng.

Hoặc:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./local-config/
~~~

Lúc khởi chạy, property này phải có đủ sớm để Spring Boot biết cần xét thư mục **local-config**.

### 11.1. Sai lầm vòng lặp tự tham chiếu

Giả sử bạn muốn nạp **custom/application.yml** và chỉ viết:

~~~yaml
spring:
  config:
    location: "file:./custom/"
~~~

trong một file mặc định khác, rồi mong Spring Boot dùng chính property đó để quay lại quyết định toàn bộ những vị trí đã tìm. Tài liệu Boot yêu cầu **spring.config.name**, **spring.config.location** và **spring.config.additional-location** được cung cấp như **environment property từ sớm**, thường qua OS env, system property hoặc command-line.

Không thiết kế quy trình “đọc được file rồi mới biết phải tìm file ở đâu” cho những key bootstrap này.

### 11.2. Dạng biến môi trường

~~~text
SPRING_CONFIG_NAME=myservice
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./local-config/
~~~

Với directory location, dấu gạch chéo cuối **/** có ý nghĩa: Spring Boot có thể nối tên file sinh từ **spring.config.name** vào đường dẫn thư mục.

### 11.3. spring.config.location khác additional-location

- **spring.config.location** có thể thay thế tập vị trí tìm kiếm mặc định.
- **spring.config.additional-location** bổ sung những vị trí mới mà vẫn giữ các vị trí mặc định.

Vì vậy, khi chỉ muốn thêm một folder cấu hình deploy, **additional-location** thường dễ tránh mất các Config Data location mặc định hơn.

## 12. spring.config.import: không giống @PropertySource

**spring.config.import** được Spring Boot Config Data infrastructure xử lý trong giai đoạn nạp cấu hình.

Ví dụ **application.yml**:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment-extra.properties"

logging:
  level:
    root: INFO
~~~

Nếu file **deployment-extra.properties** tồn tại:

~~~properties
logging.level.root=WARN
spring.main.banner-mode=off
~~~

thì nó được xem như Config Data nhập vào thông qua cơ chế của Boot. Dữ liệu có thể tham gia vào quyết định startup phù hợp ở thời điểm nạp Config Data.

**Khác biệt cốt lõi:**

- **spring.config.import** là một phần của Config Data processing, diễn ra sớm.
- **@PropertySource** trên một @Configuration class được thêm khi refresh context, muộn hơn.

Một file giống nhau về nội dung có thể tạo **hành vi khác nhau** chỉ vì nó được nạp theo **cơ chế khác nhau**.

### 12.1. Optional import

Tiền tố:

~~~text
optional:file:./deployment-extra.properties
~~~

cho phép ứng dụng tiếp tục startup khi file không tồn tại, theo quy tắc Config Data optional locations.

Nếu file thực sự chứa những giá trị bắt buộc cho production, không nên tùy tiện gắn **optional:** rồi để ứng dụng khởi động thiếu cấu hình mà không có validation hoặc guard thích hợp.

## 13. Programmatic early configuration trong main()

Khi viết code bootstrap, ta có thể cấu hình **SpringApplication** trước khi gọi **run(...)**.

Ví dụ:

~~~java
package com.example.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class EarlyConfigApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyConfigApplication.class);

        application.setDefaultProperties(Map.of(
                "spring.main.banner-mode", "off",
                "logging.level.root", "INFO"
        ));

        application.run(args);
    }
}
~~~

**setDefaultProperties(...)** cung cấp những default có độ ưu tiên thấp. Vì vậy, command-line hoặc env của người vận hành có thể ghi đè default phù hợp.

Khi muốn set thuộc tính SpringApplication trực tiếp bằng API, có thể gọi các setter trước **run(...)**:

~~~java
SpringApplication application =
        new SpringApplication(EarlyConfigApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.setLogStartupInfo(false);

application.run(args);
~~~

Đây là những quyết định programmatic được đưa ra sớm hơn việc tạo bean ứng dụng.

**Cẩn trọng với precedence:** giá trị set trên SpringApplication và giá trị bind từ Environment có thể tương tác theo vòng đời cụ thể. Nếu cần một contract override rõ ràng cho người triển khai, hãy ưu tiên một nguồn cấu hình chuẩn và test hành vi cho phiên bản Spring Boot thực tế. Không mặc nhiên cho rằng một setter luôn thắng mọi property hoặc ngược lại.

### 13.1. DefaultProperties không giống override cao nhất

Nếu đặt:

~~~java
application.setDefaultProperties(Map.of(
        "logging.level.root", "INFO"));
~~~

rồi operator chạy:

~~~bash
java -jar app.jar --logging.level.root=DEBUG
~~~

thì command-line thường có độ ưu tiên cao hơn default properties. **Default** là fallback, không phải chính sách bắt buộc.

Nếu cần khóa cứng một cấu hình vì yêu cầu bảo mật, đừng kỳ vọng chỉ dùng **setDefaultProperties** có thể làm việc đó.

## 14. Khi nào cần EnvironmentPostProcessor?

**EnvironmentPostProcessor** là extension point của Spring Boot để tùy biến Environment **trước khi ApplicationContext được refresh**.

Nó phù hợp khi:

- Ứng dụng cần dịch một convention cấu hình riêng thành property chuẩn của Spring Boot.
- Cần thêm một PropertySource từ nguồn bootstrap đã có sẵn.
- Cần chuẩn hóa một số giá trị trước khi các component startup sử dụng.
- Đang xây starter/platform library cung cấp cấu hình sớm cho nhiều ứng dụng.

Không cần EnvironmentPostProcessor chỉ để đổi **logging.level.root** từ INFO thành DEBUG. Với trường hợp đơn giản, command-line, env hoặc Config Data đã đủ.

### 14.1. Ví dụ: ánh xạ biến bootstrap riêng sang logging.level.root

Giả sử một môi trường deploy cấp biến:

~~~text
COMPANY_BOOTSTRAP_LOG_LEVEL=WARN
~~~

Bạn muốn sử dụng nó như một **default cho logging.level.root**, nhưng vẫn cho phép operator ghi đè trực tiếp bằng **LOGGING_LEVEL_ROOT** hoặc CLI.

Tạo class:

~~~java
package com.example.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.util.StringUtils;

public final class CompanyLoggingEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        String requestedLevel =
                environment.getProperty(
                        "COMPANY_BOOTSTRAP_LOG_LEVEL");

        if (!StringUtils.hasText(requestedLevel)) {
            return;
        }

        MapPropertySource source = new MapPropertySource(
                "companyBootstrapLoggingDefaults",
                Map.of("logging.level.root", requestedLevel));

        environment.getPropertySources().addLast(source);
    }
}
~~~

Giải thích:

- **EnvironmentPostProcessor** được Spring Boot gọi trong giai đoạn chuẩn bị Environment.
- **MapPropertySource** chứa key chuẩn **logging.level.root**.
- **addLast(...)** đặt source mới ở vị trí ưu tiên thấp so với các PropertySource đã có.
- **COMPANY_BOOTSTRAP_LOG_LEVEL** chỉ là convention ví dụ; bản thân Spring Boot không yêu cầu tên này.
- Nếu biến không được cung cấp, processor không thêm source mới.
- Processor không tạo hoặc sửa bean nghiệp vụ nào.

**Lưu ý:** việc thêm source ở cuối giữ nó như một fallback, nên nếu logging.level.root đã có ở Config Data hoặc CLI thì giá trị ưu tiên cao hơn vẫn thắng.

### 14.2. Vì sao không addFirst mọi lúc?

Đoạn:

~~~java
environment.getPropertySources().addFirst(source);
~~~

đưa source lên đầu danh sách và có thể ưu tiên hơn cả những giá trị người vận hành cố ý đặt ở CLI/env, tùy thời điểm source được thêm.

Đây có thể là hành vi mong muốn khi thiết kế một platform policy, nhưng không nên sử dụng một cách máy móc. Thứ tự PropertySource là một phần của contract override.

Trong ví dụ cấp default logging, **addLast** hợp lý hơn **addFirst** vì nó tránh ghi đè cấu hình startup do deployment chỉ định.

### 14.3. Không dùng processor để thực hiện I/O nặng

EnvironmentPostProcessor chạy sớm. Nếu nó kết nối database, thực hiện HTTP request dài hoặc phụ thuộc các bean chưa được tạo, startup sẽ khó dự đoán.

Nếu phải lấy dữ liệu từ một nguồn cấu hình bên ngoài, hãy dùng extension/config data mechanism phù hợp, có giới hạn thời gian và chính sách lỗi rõ ràng. Không biến processor thành một service nghiệp vụ đầy đủ.

## 15. Đăng ký EnvironmentPostProcessor trong Spring Boot 3.3

Chỉ viết class implements interface là **chưa đủ**. Spring Boot cần được khai báo để phát hiện nó ở thời điểm startup.

Tạo file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.boot.CompanyLoggingEnvironmentPostProcessor
~~~

Trong Spring Boot 3.3, **EnvironmentPostProcessor implementations được đăng ký qua META-INF/spring.factories**, với key là tên đầy đủ của interface.

**Không nhầm** cơ chế này với file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File **AutoConfiguration.imports** phục vụ đăng ký auto-configuration; nó **không thay thế** registration key của EnvironmentPostProcessor trong ví dụ này.

Một lỗi thường gặp là class đã compile thành công, nằm đúng package, nhưng processor không chạy vì thiếu file **spring.factories** hoặc khai báo sai fully qualified class name.

### 15.1. Thứ tự giữa các EnvironmentPostProcessor

Nếu có nhiều processor, thứ tự có thể ảnh hưởng đến giá trị cuối. Spring Boot cho phép implementation dùng **Ordered** hoặc **@Order**.

**ConfigDataEnvironmentPostProcessor** là một processor của Boot có nhiệm vụ xử lý Config Data. Nếu processor của bạn phụ thuộc vào các property trong application.yml, nó cần hoạt động ở thời điểm thích hợp **sau khi Config Data được nạp**.

Không tự đoán rằng mọi custom processor đều chạy theo thứ tự tên class hoặc thứ tự dòng trong spring.factories. Khi cần quan hệ thứ tự cụ thể, tìm hiểu ordering API và viết test chứng minh nó.

### 15.2. Logging trong chính EnvironmentPostProcessor

Vì processor chạy sớm, logging system có thể chưa được cấu hình đầy đủ. Nếu cần log chẩn đoán lúc bootstrap, Spring Boot hỗ trợ **DeferredLogFactory** như một constructor parameter tùy chọn trong EnvironmentPostProcessor, để log được phát sau khi hệ thống logging đã được chuẩn bị.

Không mặc định rằng ghi log trực tiếp từ constructor hoặc đầu postProcessEnvironment luôn sử dụng đúng logging level/formatter mà bạn sắp cấu hình.

## 16. EnvironmentPostProcessor khác ApplicationContextInitializer

Hai điểm mở rộng dễ bị nhầm:

| Extension point | Tác động chính | Thời điểm và lưu ý |
| --- | --- | --- |
| **EnvironmentPostProcessor** | Tùy biến Environment ở giai đoạn chuẩn bị sớm | Phù hợp cho nguồn cấu hình có thể ảnh hưởng đến startup |
| **ApplicationContextInitializer** | Tùy biến ApplicationContext trước refresh | Context đã được tạo; có thể quá muộn cho một số quyết định như banner/logging khởi đầu |
| **@PropertySource** | Thêm một source được khai báo trên @Configuration class | Thông thường xử lý khi context refresh |
| **ApplicationRunner** | Chạy logic sau khi context được chuẩn bị | Quá muộn cho các quyết định đọc sớm |
| **CommandLineRunner** | Chạy sau startup context | Không dùng để thay đổi loại web application đã tạo |
| **@ConfigurationProperties** | Bind một nhóm property vào bean có kiểu | Hữu ích cho cấu hình subsystem, không tự thay quyết định startup quá khứ |

Nếu mục tiêu là **thêm một key logging trước khi logging system tiêu thụ nó**, EnvironmentPostProcessor là lựa chọn phù hợp hơn một bean ApplicationRunner.

### 16.1. ApplicationEnvironmentPreparedEvent

Spring Boot có event **ApplicationEnvironmentPreparedEvent** trong vòng đời startup. Event này xảy ra sau khi Environment đã được chuẩn bị và trước khi context được tạo.

Một listener được **đăng ký đủ sớm vào SpringApplication** có thể tham gia vào việc tùy biến Environment, nhưng thứ tự listener so với những subsystem như logging vẫn cần được hiểu rõ.

Với nhu cầu bổ sung PropertySource chuẩn, **EnvironmentPostProcessor** là cơ chế được Boot dành riêng cho việc này và thường dễ quản lý hơn một listener tự cấu hình ordering tùy ý.

## 17. Tại sao Environment.getProperty có thể “đúng” nhưng hành vi vẫn “sai”?

Một tình huống gây nhầm:

1. SpringApplication đọc property **spring.main.banner-mode** ở giai đoạn startup.
2. Banner đã được quyết định và in (hoặc không in).
3. @PropertySource được xử lý khi refresh, thêm một file khai báo **spring.main.banner-mode=off**.
4. Sau đó một service gọi **environment.getProperty("spring.main.banner-mode")** và thấy **off**.

Người phát triển có thể nói: “Environment đã có off, sao banner vẫn hiện?”

Vì **Environment là tập property hiện tại**, còn hành vi banner là một **quyết định đã được thực thi ở thời điểm trước đó**.

Tương tự đối với logging:

~~~text
Environment hiện tại nói logging.level.root=DEBUG
          ≠
Hệ thống logging đã luôn ở DEBUG từ đầu startup
~~~

Một số logging subsystem cho phép thay đổi động, nhưng đó là cơ chế riêng; không nên xem property tồn tại muộn như bằng chứng chắc chắn logging đã được khởi tạo lại.

Đây là điểm quan trọng nhất khi gỡ lỗi các thuộc tính đọc sớm.

## 18. Khi nào @Value và @ConfigurationProperties được dùng?

Các bean nghiệp vụ có thể đọc config qua:

~~~java
@Value("${app.report.max-rows:100}")
private int maxRows;
~~~

hoặc:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(int maxRows) {
}
~~~

Đây là những công cụ hợp lý cho cấu hình thuộc về component, đặc biệt khi subsystem có nhiều field, cần type conversion và validation.

Nhưng đoạn:

~~~java
@ConfigurationProperties(prefix = "spring.main")
public record MainProperties(String bannerMode) {
}
~~~

không tự bảo đảm rằng SpringApplication sẽ áp dụng lại banner mode sau khi bean này được tạo.

Nguyên tắc:

- **Đọc và bind một giá trị** là một việc.
- **Áp dụng một quyết định khởi động** là việc khác.

Chọn nguồn cấu hình đúng **thời điểm đọc** và đúng **component tiêu thụ**.

## 19. Thứ tự ưu tiên nguồn trong Spring Boot

Spring Boot định nghĩa thứ tự các PropertySource theo nguyên tắc **nguồn ưu tiên cao hơn có thể override nguồn thấp hơn**.

Những nguồn thường gặp:

~~~text
Default properties
      |
@PropertySource (nạp khi context refresh)
      |
Config Data (application.properties / .yml)
      |
OS environment variables
      |
Java system properties
      |
SPRING_APPLICATION_JSON
      |
Command-line arguments
~~~

Đây là sơ đồ tóm tắt cho các nguồn tiêu biểu, **không phải danh sách đầy đủ mọi nguồn**: test properties, servlet init params, devtools settings và một số nguồn khác có vị trí riêng.

Thứ tự ở trên thể hiện cấp ưu tiên tương đối trong tài liệu Spring Boot; **đọc sớm hay muộn là một trục độc lập với độ ưu tiên**.

Một nguồn có ưu tiên “cao” trong Environment sau refresh vẫn có thể được thêm **quá muộn** đối với một quyết định startup. Vì vậy, khi debug, cần trả lời cả hai câu:

1. **Key cuối cùng lấy từ nguồn nào?**
2. **Nguồn đó có tồn tại lúc component cần key hay chưa?**

### 19.1. @PropertySource dù có key vẫn không phải giải pháp override early key

Ngay cả khi file @PropertySource đứng trong Environment, các key **logging.*** và **spring.main.*** được Boot nhấn mạnh là ví dụ có thể đã được đọc trước refresh.

Cách sửa thường không phải tăng priority cho @PropertySource bằng code muộn, mà là **đưa giá trị vào Config Data hoặc một nguồn bootstrap sớm**.

## 20. Một ví dụ quan sát từ đầu tới cuối

Giả sử ứng dụng có class:

~~~java
package com.example.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EarlyPropertiesDemo {

    public static void main(String[] args) {
        SpringApplication.run(EarlyPropertiesDemo.class, args);
    }
}
~~~

**application.yml**:

~~~yaml
spring:
  main:
    banner-mode: "console"
    log-startup-info: true

logging:
  level:
    root: INFO
~~~

Chạy mặc định:

~~~bash
java -jar app.jar
~~~

Sau đó thử:

~~~bash
java -jar app.jar \
  --spring.main.banner-mode=off \
  --spring.main.log-startup-info=false \
  --logging.level.root=WARN
~~~

Quan sát:

- Banner được tắt thay vì hiển thị.
- Những log startup do SpringApplication quản lý có thể giảm đi.
- Root logging level được đặt WARN, nên các thông điệp DEBUG/INFO thông thường không xuất hiện ở root logger.

**Không dùng số dòng log tuyệt đối làm tiêu chí**, vì các logging framework, dependency và code ứng dụng có thể tạo log khác nhau. Kiểm tra chính hành vi được property mô tả.

### 20.1. Thử nguồn nạp muộn

Tạo:

~~~properties
# late-startup.properties
spring.main.banner-mode=off
logging.level.root=DEBUG
~~~

Thêm @PropertySource lên một @Configuration class. Chạy lại với **application.yml** như trước và không truyền CLI.

Điều có thể thấy:

- File được đọc trong khi context refresh.
- Nhưng các quyết định startup đã diễn ra trước thời điểm ấy không bắt buộc thay đổi.

Kết luận không phải “@PropertySource không hoạt động”, mà là **@PropertySource không thích hợp cho nhóm property đọc sớm**.

### 20.2. Thử Config Data import

Chuyển các giá trị trên sang:

~~~properties
# deployment-extra.properties
spring.main.banner-mode=off
logging.level.root=DEBUG
~~~

Rồi trong **application.yml** thêm:

~~~yaml
spring:
  config:
    import: "optional:classpath:deployment-extra.properties"
~~~

Giờ file được đưa vào qua **Config Data** thay vì thông qua @PropertySource, vì vậy có thể được áp dụng trong giai đoạn Environment preparation.

## 21. Những lỗi thường gặp

### Lỗi 1 — Đặt logging.* trong @PropertySource rồi thấy không hiệu lực lúc startup

**Nguyên nhân:** nguồn chỉ được thêm khi context refresh.

**Cách xử lý:** chuyển key vào application.yml/properties, biến môi trường, system property, command-line hoặc EnvironmentPostProcessor đủ sớm.

### Lỗi 2 — Đọc được spring.main.banner-mode=off nhưng banner vẫn đã được in

**Nguyên nhân:** property xuất hiện sau khi SpringApplication đã xử lý banner.

**Cách xử lý:** dùng nguồn sớm và quan sát lần khởi động mới; không kỳ vọng banner in rồi có thể bị “thu hồi”.

### Lỗi 3 — Sai cách đặt tên env của key kebab-case

**Ví dụ:** **SPRING_MAIN_BANNER_MODE** thay cho tên canonical **SPRING_MAIN_BANNERMODE**.

**Cách xử lý:** chuyển tên theo quy tắc của Spring Boot: dấu chấm thành gạch dưới, dấu gạch ngang bỏ, chữ thành hoa.

### Lỗi 4 — Đặt spring.config.location trong file mong được tìm nhờ chính nó

**Nguyên nhân:** Spring Boot cần biết location để nạp file ngay từ đầu.

**Cách xử lý:** dùng env, system property hoặc command-line cho **spring.config.location** và các bootstrap location flags tương ứng.

### Lỗi 5 — Coi command-line và -D là một

~~~text
-Dspring.main.banner-mode=off
--spring.main.banner-mode=off
~~~

Hai cú pháp thuộc hai cơ chế khác nhau. **-D** là Java launcher property trước -jar; **--** là Spring Boot application argument sau JAR.

### Lỗi 6 — Chưa truyền biến môi trường vào process Java

Biến nằm ở shell khác, file .env chưa được Compose chuyển vào container hoặc biến nằm ở job CI khác có thể không xuất hiện trong process.

**Cách xử lý:** kiểm tra môi trường thực của process/Pod và cách truyền biến, không chỉ xem file khai báo.

### Lỗi 7 — Tưởng logging.config sẽ tự reload file

**logging.config** giúp chỉ định file logging configuration được dùng khi logging được cấu hình. Đổi file sau startup không mặc định kích hoạt reload qua Spring Boot. Nếu muốn reload, cần hiểu chính logging framework và cơ chế riêng.

### Lỗi 8 — EnvironmentPostProcessor không chạy

**Nguyên nhân:** thiếu **META-INF/spring.factories**, sai class name hoặc file không được đóng gói trong JAR.

**Cách xử lý:** xác nhận class ở output, file spring.factories có đúng key **org.springframework.boot.env.EnvironmentPostProcessor** và class có thể load.

### Lỗi 9 — Dùng addFirst làm mất quyền override từ CLI

**Nguyên nhân:** source tùy biến có độ ưu tiên cao bất ngờ.

**Cách xử lý:** nếu chỉ muốn defaults, dùng **addLast** hoặc nguồn default thích hợp; thiết kế precedence rõ ràng.

### Lỗi 10 — Cho custom processor phụ thuộc Spring bean

**Nguyên nhân:** EnvironmentPostProcessor chạy trước khi ApplicationContext refresh và trước khi các bean nghiệp vụ sẵn sàng.

**Cách xử lý:** giữ processor nhẹ, thuần, không giả định có @Autowired service hoặc database connection.

### Lỗi 11 — Chọn sai web application type

Đặt **spring.main.web-application-type=none** trong một service mong phục vụ REST API sẽ làm kỳ vọng về embedded server không đúng.

**Cách xử lý:** xác định ứng dụng là CLI/batch, Servlet web hay Reactive web trước khi đặt property.

### Lỗi 12 — Dùng ApplicationRunner để sửa thuộc tính startup

ApplicationRunner chạy sau khi context đã sẵn sàng, nên không thích hợp cho quyết định đã dùng khi tạo context.

### Lỗi 13 — Nhầm @ConfigurationProperties với bootstrap wiring

Một @ConfigurationProperties bean có thể nhận property **spring.main.web-application-type**, nhưng việc bean tồn tại không tự thiết lập lại SpringApplication.

### Lỗi 14 — Bật lazy initialization rồi mong mọi cấu hình sai vẫn fail-fast

Một số bean lazy có thể bị trì hoãn, kéo theo validation lúc bean được dùng. Không coi lazy initialization là cơ chế bảo đảm mọi config đã được kiểm tra sớm.

### Lỗi 15 — Log secret trong EnvironmentPostProcessor

Processor có thể nhìn thấy nhiều nguồn cấu hình, gồm thông tin nhạy cảm. Không in toàn bộ Environment hoặc giá trị secret ra log bootstrap.

## 22. Bài thực hành

### Bài A: so sánh Config Data với @PropertySource

1. Tạo một app Spring Boot tối thiểu với main class.
2. Đặt **spring.main.banner-mode=off** trong **application.properties**.
3. Chạy và quan sát banner.
4. Chuyển property sang **late-startup.properties** rồi chỉ nạp file qua **@PropertySource**.
5. Khởi chạy lại và so sánh.

**Điểm cần hiểu:** không phải mọi PropertySource được thêm vào Environment ở cùng một thời điểm.

### Bài B: override log level từ CLI

1. Đặt **logging.level.root=INFO** trong application.yml.
2. Chạy bằng **--logging.level.root=DEBUG**.
3. Chạy lại bằng **--logging.level.root=WARN**.
4. Quan sát các log có mức tương ứng.

**Điểm cần hiểu:** cấu hình sớm vẫn có thể externalize và thay đổi giữa các lượt chạy cùng JAR.

### Bài C: chuyển biến môi trường đúng quy tắc

1. Cấu hình **spring.main.log-startup-info=false** bằng env.
2. Đặt biến **SPRING_MAIN_LOGSTARTUPINFO=false**.
3. Chạy ứng dụng trong cùng shell/container có biến đó.
4. So sánh với trường hợp không cấp biến.

**Điểm cần hiểu:** dấu gạch ngang trong canonical property bị bỏ khi tạo tên env.

### Bài D: vị trí Config Data là bootstrap property

1. Tạo một thư mục **extra-config/** có **application.properties**.
2. Trong file đó đặt **logging.level.root=WARN**.
3. Khởi chạy bằng **--spring.config.additional-location=optional:file:./extra-config/**.
4. Kiểm tra log level đã có hiệu lực.
5. Bỏ argument, chạy lại để so sánh.

**Điểm cần hiểu:** đường dẫn Config Data phải được biết đủ sớm.

### Bài E: viết EnvironmentPostProcessor

1. Viết **CompanyLoggingEnvironmentPostProcessor** như mục 14.
2. Đăng ký class qua **META-INF/spring.factories**.
3. Đặt **COMPANY_BOOTSTRAP_LOG_LEVEL=WARN**.
4. Bảo đảm **logging.level.root** không có ở nguồn ưu tiên cao hơn nếu muốn nhìn thấy fallback.
5. Chạy và quan sát kết quả.
6. Cấp **--logging.level.root=DEBUG** rồi so sánh.

**Điểm cần hiểu:** PropertySource thêm sớm có thể phục vụ startup nhưng precedence vẫn quyết định giá trị cuối.

### Bài F: phân biệt programmatic default và command-line

1. Gọi **setDefaultProperties** trước **run(...)** với **spring.main.banner-mode=off**.
2. Chạy không có override.
3. Chạy với **--spring.main.banner-mode=console**.
4. Kiểm tra hành vi.

**Điểm cần hiểu:** default properties đóng vai trò fallback, không bắt buộc là giá trị cuối cùng.

### Bài G: non-web mode

1. Dùng một ứng dụng Spring Boot có embedded web server.
2. Chạy bình thường và xem port được khởi tạo.
3. Chạy cùng JAR với **--spring.main.web-application-type=none**.
4. Quan sát khác biệt về web context và embedded server.

**Điểm cần hiểu:** property startup có thể thay đổi loại ApplicationContext, không phải chỉ thay một field của bean.

## 23. Checklist chẩn đoán một property đọc sớm

Khi **logging.*** hoặc **spring.main.*** không có tác dụng, hãy kiểm tra:

1. Tên key canonical có đúng không?
2. Giá trị có được cấp **trước lúc SpringApplication đọc key** không?
3. Giá trị đến từ Config Data, env, system property, CLI hay @PropertySource?
4. Nếu dùng @PropertySource, có phải nguồn đó chỉ được thêm khi refresh không?
5. Nếu dùng env, biến đã thật sự vào process Java chưa?
6. Tên biến đã bỏ dấu gạch ngang đúng quy tắc chưa?
7. Có nguồn ưu tiên cao hơn đang override không?
8. Có tùy chỉnh **setAddCommandLineProperties(false)** không?
9. Có **spring.config.location** khiến các default locations bị thay thế không?
10. File bổ sung có được nạp qua **spring.config.import** sớm hay chỉ qua @PropertySource muộn?
11. Có code programmatic tùy chỉnh SpringApplication trước run không?
12. Với EnvironmentPostProcessor, file **spring.factories** có đúng không?
13. Processor có chạy ở order phù hợp với Config Data và logging không?
14. Source mới được thêm bằng addFirst hay addLast, ý định precedence là gì?
15. Property tác động đến startup hay chỉ tới bean nghiệp vụ?
16. Nếu property xuất hiện trong Environment sau refresh, nó đã xuất hiện vào thời điểm nào?
17. Có yêu cầu restart/rolling redeploy sau khi đổi env hoặc file không?
18. Có đang dùng test harness không mô phỏng đầy đủ SpringApplication startup không?
19. Nếu thay web-application-type, hậu quả không khởi tạo server có phải mong muốn không?
20. Có đang log/để lộ thông tin nhạy cảm khi debug Environment không?

## 24. Tổng kết

- Spring Boot có những property được đọc **trước khi ApplicationContext refresh**, tiêu biểu là một số **logging.*** và **spring.main.***.
- **@PropertySource** trên @Configuration class được xử lý khi context refresh, nên quá muộn để điều khiển một số quyết định startup.
- **Config Data**, command-line, Java system properties và OS env là những nguồn thích hợp để cấp giá trị từ sớm.
- **spring.config.name**, **spring.config.location**, **spring.config.additional-location** còn phải có đủ sớm để giúp Spring Boot tìm Config Data.
- **spring.config.import** được xử lý trong Config Data phase, khác với @PropertySource.
- **SpringApplication.setDefaultProperties(...)** cung cấp fallback programmatic trước khi run, không phải một override có quyền ưu tiên tuyệt đối.
- **EnvironmentPostProcessor** có thể bổ sung PropertySource trước refresh khi ứng dụng có nhu cầu bootstrap tùy biến.
- Với Spring Boot 3.3, đăng ký EnvironmentPostProcessor qua **META-INF/spring.factories**.
- Thứ tự ưu tiên và thời điểm xuất hiện của nguồn là **hai vấn đề độc lập**, đều ảnh hưởng đến property đọc sớm.
- Việc **Environment.getProperty(...)** đọc được giá trị sau refresh không chứng minh rằng một quyết định startup trước đó đã được cập nhật.
- Dùng **@ConfigurationProperties** cho cấu hình subsystem; dùng các extension bootstrap đúng thời điểm cho những thuộc tính điều khiển SpringApplication/logging.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — *Externalized Configuration*, đặc biệt phần *PropertySource Order*, *Config Data Files* và *Config Data Location*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — *Logging*: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- Spring Boot 3.3 — *EnvironmentPostProcessor API*: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3 — *SpringApplication API*: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — *Environment Abstraction*: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
