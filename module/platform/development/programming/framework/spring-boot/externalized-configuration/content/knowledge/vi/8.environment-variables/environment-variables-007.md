# Tắt nguồn dòng lệnh bằng `setAddCommandLineProperties(false)` trong Spring Boot

## 1. Vấn đề: đối số dòng lệnh có thể ghi đè cấu hình ứng dụng

Spring Boot cho phép tách cấu hình khỏi mã Java. Cùng một ứng dụng có thể đọc các thuộc tính từ `application.yml`, `application.properties`, biến môi trường hệ điều hành, Java system properties và đối số dòng lệnh. Theo mặc định, những đối số ứng dụng bắt đầu bằng `--`, ví dụ `--server.port=9090`, được Spring Boot chuyển thành các **configuration properties** và đưa vào `Spring Environment`.

Giả sử `application.yml` có:

~~~yaml
server:
  port: 8080

app:
  message: from-file
  timeout: 3s
~~~

Ứng dụng được chạy:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

Khi dùng cơ chế mặc định, đối số dòng lệnh thường có mức ưu tiên cao hơn cấu hình file. Spring Boot sẽ thấy `server.port=9090` và `app.message=from-cli`. Đây là tính năng thuận tiện để điều chỉnh cấu hình theo từng lần chạy, nhưng một hệ thống có thể muốn **không dùng đối số `--key=value` làm nguồn cấu hình**.

Spring Boot cung cấp phương thức:

~~~java
springApplication.setAddCommandLineProperties(false);
~~~

Phương thức này tắt việc thêm **command-line property source** vào `Environment`. Đối số vẫn được truyền cho chương trình và vẫn có thể được xử lý theo cơ chế nhận tham số ứng dụng.

> Ý quan trọng nhất: `setAddCommandLineProperties(false)` không xóa các đối số truyền vào `main(String[] args)`; nó thay đổi cách Spring Boot **đưa các option arguments vào hệ thống tra cứu cấu hình**.

## 2. Cơ chế mặc định hoạt động thế nào?

Khi gọi:

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

Spring Boot khởi tạo ứng dụng với hành vi mặc định tương đương `addCommandLineProperties=true`. Các option arguments theo dạng:

~~~text
--server.port=9090
--logging.level.root=DEBUG
--app.timeout=10s
--spring.profiles.active=prod
~~~

có thể được chuyển thành những thuộc tính trong một `PropertySource` dành cho command line. `Environment` tập hợp nhiều nguồn `PropertySource` theo thứ tự ưu tiên để trả về giá trị cuối của một tên property.

Mô hình thông thường:

~~~text
args truyền vào main(String[] args)
             |
             v
SpringApplication chuẩn bị Environment
             |
             +-- addCommandLineProperties = true
             |          |
             |          v
             |    tạo CommandLinePropertySource
             |          |
             |          v
             |    thêm vào Environment
             |
             v
các nguồn khác: system properties, OS environment, config data...
             |
             v
tra cứu server.port, app.timeout, spring.profiles.active...
             |
             v
binding, auto-configuration và các bean ứng dụng
~~~

Trong các nguồn cấu hình thường gặp của Spring Boot, thứ tự được hiểu gần đúng từ cao xuống thấp là:

| Nguồn | Ví dụ |
| --- | --- |
| Đối số ứng dụng dạng `--key=value` | `--server.port=9090` |
| Java system properties | `-Dserver.port=9091` |
| Biến môi trường hệ điều hành | `SERVER_PORT=9092` |
| Config data | `application.yml`, `application-prod.yml`, file ngoài JAR |
| Default properties của `SpringApplication` | Cấu hình fallback do chương trình cung cấp |

Bảng chỉ chọn các nguồn thông dụng để minh họa; thực tế Spring Boot còn có các nguồn khác như JSON properties, môi trường web, nguồn phục vụ kiểm thử và Devtools. Không suy ra bảng trên là toàn bộ danh sách thứ tự ưu tiên trong mọi bối cảnh.

Nếu cả CLI, JVM và file cùng cung cấp `server.port`, nguồn CLI có thể thắng ở chế độ mặc định. Vì vậy `--server.port=9090` là một cách ghi đè nhanh khi chạy local.

## 3. Cách bật chế độ không lấy cấu hình từ command line

### 3.1. Cấu hình ở `main` trước khi chạy

Thay cách gọi tĩnh `SpringApplication.run(...)` bằng việc tạo đối tượng `SpringApplication` rồi thiết lập thuộc tính:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        // Không chuyển --key=value thành property trong Environment.
        application.setAddCommandLineProperties(false);

        application.run(args);
    }
}
~~~

Các điểm cần chú ý:

1. Tạo một instance `SpringApplication` từ lớp ứng dụng.
2. Gọi `setAddCommandLineProperties(false)` **trước khi gọi `run(args)`**.
3. Tiếp tục truyền `args` vào `run` để ứng dụng nhận được đối số thông thường.
4. Spring Boot khởi tạo context, nạp config data, thực hiện binding và tạo các bean theo các nguồn cấu hình còn lại.

Sau thay đổi này, nếu chạy:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

và file `application.yml` vẫn chứa `server.port=8080`, `app.message=from-file`, thì các option dòng lệnh trên **không còn trực tiếp ghi đè hai property đó trong `Environment`**. Với giả định không có nguồn nào khác ưu tiên hơn, ứng dụng sẽ dùng port `8080` và message `from-file`.

### 3.2. Phải gọi đúng instance trước khi chạy

Ví dụ sau không có ý nghĩa điều khiển lần chạy đang diễn ra:

~~~java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);

    // Quá muộn và còn là một đối tượng SpringApplication khác.
    SpringApplication another =
            new SpringApplication(DemoApplication.class);
    another.setAddCommandLineProperties(false);
}
~~~

Để thay đổi cách `Environment` nhận command-line properties, hãy cấu hình **đối tượng SpringApplication thực sự dùng để khởi động** và thực hiện trước `run`.

### 3.3. Giá trị `true` và hành vi mặc định

Nếu cần khôi phục cách xử lý command-line properties mặc định:

~~~java
application.setAddCommandLineProperties(true);
~~~

Khi không gọi phương thức này, Spring Boot mặc định cho phép đưa command-line option properties vào `Environment`. Có thể dùng `false` khi thiết kế muốn cấm cơ chế ghi đè theo kênh này.

## 4. Tắt command-line property source không có nghĩa bỏ qua `args`

Đây là phân biệt dễ nhầm nhất trong bài này.

Spring Boot có **hai luồng sử dụng** đối số dòng lệnh:

- **Cấu hình:** chuyển `--key=value` thành các property trong `Environment` để `@Value`, `@ConfigurationProperties` và Spring Boot auto-configuration có thể đọc.
- **Tham số ứng dụng:** truyền và phân tích `args` cho mã nghiệp vụ qua `ApplicationArguments`, `ApplicationRunner` hoặc `CommandLineRunner`.

`setAddCommandLineProperties(false)` tắt **luồng đầu tiên**, không tắt luồng thứ hai.

| Cách sử dụng | Khi mặc định | Khi `setAddCommandLineProperties(false)` |
| --- | --- | --- |
| `Environment.getProperty("app.mode")` nhận `--app.mode=fast` | Có thể nhận `fast` | Không nhận từ nguồn CLI đó |
| `@Value` hoặc `@ConfigurationProperties` đọc từ CLI | Có | Không, trừ khi một nguồn khác cung cấp cùng property |
| `ApplicationArguments.containsOption("app.mode")` | Có thể là `true` | Vẫn có thể là `true` |
| `ApplicationArguments.getOptionValues("app.mode")` | Có thể trả về `["fast"]` | Vẫn có thể trả về `["fast"]` |
| `CommandLineRunner.run(String... args)` | Nhận raw arguments | Vẫn nhận raw arguments |
| Biến môi trường `APP_MODE=...` | Được xét như OS environment | Vẫn được xét như OS environment |
| Java system property `-Dapp.mode=...` | Được xét | Vẫn được xét |

Vì thế, **không nên tuyên bố rằng chương trình sẽ hoàn toàn không nhìn thấy mọi tham số dòng lệnh**. Nếu mã của ứng dụng tự đọc `args` rồi gọi `System.setProperty(...)` hoặc thiết lập cấu hình theo cách riêng, thay đổi đó không bị phương thức này tự động ngăn chặn.

## 5. Ví dụ đầy đủ: phân biệt `Environment` và `ApplicationArguments`

### 5.1. File cấu hình

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: cli-property-demo

server:
  port: 8080

app:
  message: from-file
  mode: normal
~~~

### 5.2. Mã Java

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DemoApplication.class);
        app.setAddCommandLineProperties(false);
        app.run(args);
    }

    @Bean
    ApplicationRunner printConfiguration(Environment environment) {
        return (ApplicationArguments args) -> {
            System.out.println("server.port = "
                    + environment.getProperty("server.port"));
            System.out.println("app.message = "
                    + environment.getProperty("app.message"));
            System.out.println("app.mode = "
                    + environment.getProperty("app.mode"));

            System.out.println("Option app.message present = "
                    + args.containsOption("app.message"));
            System.out.println("Option app.message values = "
                    + args.getOptionValues("app.message"));
        };
    }
}
~~~

Ví dụ chỉ in thông số không nhạy cảm. Trong sản phẩm thật, không in password, token, khóa API hoặc toàn bộ đối số nếu có thể chứa dữ liệu bí mật.

### 5.3. Chạy với `--app.message`

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

Trong trường hợp không có nguồn cấu hình nào khác ghi đè, phần thông tin từ runner tương đương:

~~~text
server.port = 8080
app.message = from-file
app.mode = normal
Option app.message present = true
Option app.message values = [from-cli]
~~~

Điều này minh họa đồng thời hai sự thật:

1. `Environment` lấy `server.port` và `app.message` từ file cấu hình, vì command-line property source bị tắt.
2. `ApplicationArguments` vẫn thấy `--app.message=from-cli` và trả về giá trị của option đó.

Nếu bỏ dòng `app.setAddCommandLineProperties(false)` rồi chạy lại trong cùng điều kiện, các giá trị cấu hình hiệu lực có thể trở thành `server.port=9090` và `app.message=from-cli` theo hành vi mặc định.

## 6. Tác động đến biến môi trường hệ điều hành

Tên nhóm bài học là **Biến môi trường**, nên cần tách rõ **OS environment variables** khỏi **command-line option arguments**. Hai nguồn cùng có thể xuất hiện trong một lần chạy nhưng chúng không phải một cơ chế.

Ví dụ cấu hình file:

~~~yaml
server:
  port: 8080
app:
  mode: normal
~~~

Vẫn giữ `setAddCommandLineProperties(false)` và chạy trên shell Unix:

~~~bash
SERVER_PORT=9191 APP_MODE=production \
  java -jar demo.jar --server.port=9292 --app.mode=from-cli
~~~

Với giả định không có nguồn ưu tiên cao hơn biến môi trường:

| Thuộc tính | File YAML | OS environment | CLI | Giá trị hiệu lực |
| --- | --- | --- | --- | --- |
| `server.port` | `8080` | `SERVER_PORT=9191` | `--server.port=9292` | `9191` |
| `app.mode` | `normal` | `APP_MODE=production` | `--app.mode=from-cli` | `production` |

Lý do: Spring Boot **vẫn đọc các biến môi trường** và áp dụng relaxed binding. Ví dụ `SERVER_PORT` ánh xạ đến `server.port`; `APP_MODE` ánh xạ đến `app.mode`. Chỉ nguồn CLI option properties bị loại khỏi `Environment`.

Trên PowerShell có thể chuẩn bị môi trường như sau:

~~~powershell
$env:SERVER_PORT = "9191"
$env:APP_MODE = "production"
java -jar demo.jar --server.port=9292 --app.mode=from-cli
~~~

Kết quả cấu hình là tương tự, miễn là không có nguồn cấu hình khác ghi đè.

**Không nhầm `-D` với `--`:** `-Dserver.port=9191` là **Java system property** được truyền cho JVM, còn `--server.port=9292` là **đối số của ứng dụng** truyền sau tên JAR. `setAddCommandLineProperties(false)` xử lý nguồn thứ hai, không tắt Java system properties.

## 7. Tác động đến Java system properties

Xét lệnh:

~~~bash
java -Dserver.port=9191 -jar demo.jar --server.port=9292
~~~

Với `setAddCommandLineProperties(false)`, Spring Boot vẫn nhận `server.port=9191` từ JVM system properties. Phần `--server.port=9292` vẫn có trong raw args nhưng không được đưa vào `Environment` dưới dạng command-line configuration.

Khác biệt vị trí cú pháp:

~~~text
java -Dserver.port=9191 -jar demo.jar --server.port=9292
     └─ JVM property ──┘               └─ app option ──┘
~~~

Đặt `-D...` **trước** `-jar` để JVM nhận nó là system property. Đặt `--...` sau `demo.jar` để nó được truyền vào `main(String[] args)` của ứng dụng.

Một câu hỏi thường gặp: nếu chuyển toàn bộ `--key=value` thành `-Dkey=value` thì sao? Các giá trị đó có thể tiếp tục có hiệu lực qua `systemProperties`, bởi phương thức này **không ngăn kênh `-D`**. Nếu chính sách triển khai cần kiểm soát cả system properties, environment variables và file mounts, phải áp dụng các biện pháp quản trị tương ứng; một lời gọi phương thức này không quản lý tất cả kênh cấu hình.

## 8. Tác động đến `@Value` và `@ConfigurationProperties`

Trong một ứng dụng, `Environment` thường được tiêu thụ bởi:

- Spring Boot auto-configuration, chẳng hạn `server.port`.
- `@Value`, khi cần inject một property riêng lẻ.
- `@ConfigurationProperties`, khi bind nhiều property cùng tiền tố vào một cấu trúc Java.
- Mã tự gọi `Environment.getProperty(...)`.

Ví dụ cấu hình:

~~~yaml
app:
  client:
    base-url: https://sandbox.example.test
    timeout: 5s
~~~

Record dùng `@ConfigurationProperties`:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {
}
~~~

Đăng ký quét cấu hình qua `@ConfigurationPropertiesScan` tại lớp `@SpringBootApplication` hoặc đăng ký đúng cách bằng `@EnableConfigurationProperties`.

Nếu chạy:

~~~bash
java -jar demo.jar --app.client.timeout=20s
~~~

với command-line property source bị tắt, `ClientProperties.timeout()` sẽ **không** nhận `20s` chỉ nhờ đối số ấy. Nếu file khai báo `5s` và không có nguồn khác ghi đè, bean nhận `Duration` tương ứng `5s`.

Nếu dùng biến môi trường:

~~~bash
APP_CLIENT_TIMEOUT=12s java -jar demo.jar --app.client.timeout=20s
~~~

thì bean có thể nhận `12s` từ environment variable. Đây là một ứng dụng trực tiếp của việc **phân biệt nguồn cấu hình đang được cho phép**.

Lưu ý không nên bind cấu hình quá quan trọng một cách âm thầm. Khi bắt buộc có URL, timeout, credential hoặc các giá trị giới hạn, hãy đặt validation và lỗi startup rõ ràng để triển khai sai cấu hình được phát hiện sớm.

## 9. Tác động đến profile khi khởi động

Một trong các tác động lớn là **kích hoạt Spring profiles bằng đối số CLI**.

Với hành vi mặc định, lệnh:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

đưa `spring.profiles.active=prod` vào `Environment` và có thể kích hoạt profile `prod`, từ đó nạp các file như `application-prod.yml`.

Sau khi gọi `setAddCommandLineProperties(false)`, **giá trị từ `--spring.profiles.active=prod` không được đưa vào `Environment` qua nguồn CLI**. Vì vậy, nếu không có nguồn khác kích hoạt profile `prod`, không nên kỳ vọng lệnh trên kích hoạt profile đó.

Thay vào đó có thể đặt biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Hoặc dùng JVM system property:

~~~bash
java -Dspring.profiles.active=prod -jar demo.jar
~~~

Hai hình thức này vẫn thuộc các nguồn cấu hình được Spring Boot xử lý khi command-line property source bị tắt.

Nếu muốn profile `prod` cố định từ mã hoặc một cấu hình môi trường khác, cũng có những cơ chế tương ứng; điều quan trọng là phải xác định **nguồn thực sự thiết lập profile**, đặc biệt khi các profile quyết định file cấu hình và bean nào được kích hoạt.

Ví dụ:

~~~text
application.yml       → app.timeout=3s
application-prod.yml  → app.timeout=15s

setAddCommandLineProperties(false)
java -jar demo.jar --spring.profiles.active=prod
~~~

Nếu không có nguồn khác bật `prod`, `app.timeout` không trở thành `15s` chỉ do đối số trên. Nhưng nếu chạy với `SPRING_PROFILES_ACTIVE=prod`, file `application-prod.yml` có thể tham gia và cung cấp `15s`.

## 10. Tác động đến các tùy chọn nạp Config Data

Ngoài profile, một số thuộc tính cần được nhận biết **rất sớm** để Spring Boot quyết định nơi tìm và nạp cấu hình:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`

Ở chế độ mặc định, có thể truyền:

~~~bash
java -jar demo.jar \
  --spring.config.additional-location=file:/etc/my-service/
~~~

Nhưng khi đã tắt command-line property source, không nên dựa vào đối số `--spring.config.additional-location=...` để bổ sung location. Đối số này vẫn là một option argument của `ApplicationArguments`, nhưng không được đưa vào nguồn cấu hình của `Environment` theo cơ chế mặc định.

Dùng nguồn khác được nhận biết từ sớm, ví dụ:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/my-service/ \
  java -jar demo.jar
~~~

Hoặc:

~~~bash
java -Dspring.config.additional-location=file:/etc/my-service/ -jar demo.jar
~~~

Điều tương tự áp dụng cho `spring.config.location` và `spring.config.name`. Nếu chuyển sang cấu hình bằng file ngoài JAR, cần bảo đảm đường dẫn, quyền đọc, biến môi trường và các file profile tồn tại đúng thời điểm startup.

Đối với một số chế độ chạy tự động, nếu trước đây hệ thống chỉ định profile hoặc vị trí file qua `--...`, thay đổi một dòng `setAddCommandLineProperties(false)` có thể làm ứng dụng chạy bằng **bộ cấu hình mặc định khác**. Vì thế hãy rà soát contract khởi chạy của deployment trước khi dùng trong môi trường thật.

## 11. Tác động đến logging và cấu hình máy chủ

Bên cạnh `server.port`, một số thuộc tính logging cũng thường được truyền qua CLI:

~~~bash
java -jar demo.jar --logging.level.root=DEBUG
~~~

Khi command-line property source bị vô hiệu hóa, option `--logging.level.root=DEBUG` không cung cấp giá trị cấu hình cho Spring Boot logging qua kênh CLI đó. Giá trị hiệu lực có thể đến từ file, environment variable hoặc Java system property.

Để cung cấp từ biến môi trường:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG java -jar demo.jar
~~~

Hoặc từ file:

~~~yaml
logging:
  level:
    root: DEBUG
~~~

Tương tự với các thuộc tính liên quan tới server và datasource:

~~~bash
java -jar demo.jar \
  --server.port=9090 \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/demo
~~~

Những option này sẽ không tự ghi đè `server.port` và `spring.datasource.url` trong `Environment` khi command-line property source đã bị tắt. Nếu deployment vẫn cần thay giá trị cho mỗi môi trường, hãy cung cấp qua nguồn còn được phép, chẳng hạn `SERVER_PORT` và `SPRING_DATASOURCE_URL`.

**Không đưa credential vào lệnh mẫu.** Mật khẩu, API key và token cần được quản lý qua cơ chế secret phù hợp, với quyền truy cập và logging hạn chế. Việc tắt command-line property source không làm raw arguments biến mất khỏi hệ điều hành hoặc loại trừ khả năng mã ứng dụng tự xử lý chúng.

## 12. Vì sao một dự án muốn tắt nguồn cấu hình dòng lệnh?

Phương thức này hữu ích khi thiết kế vận hành có chủ đích và muốn giảm những lần ghi đè cấu hình không mong muốn từ `--key=value`.

### 12.1. Chuẩn hóa kênh cấu hình trong môi trường triển khai

Một đội ngũ có thể quyết định cấu hình runtime phải đi qua:

- `application.yml`/`application.properties` trong artifact cho default.
- File mount ngoài JAR hoặc config data import cho khác biệt môi trường.
- Environment variables được cấp bởi pipeline, Docker Compose, Kubernetes hoặc secret manager.

Khi ấy việc một entrypoint vô tình thêm `--server.port=...` sẽ không thay đổi port thông qua Spring Environment. Các tham số ứng dụng vẫn có thể được sử dụng cho chức năng khác.

### 12.2. Tránh một số ghi đè phát sinh từ script chạy

Kịch bản:

~~~text
File triển khai chỉ định:
  SERVER_PORT=9191

Script được sao chép từ môi trường cũ:
  java -jar app.jar --server.port=8080
~~~

Nếu cho phép command-line property source, option `--server.port=8080` có thể ghi đè environment variable. Nếu tắt nó, giá trị `SERVER_PORT=9191` có thể được sử dụng như mong muốn.

Điều này chỉ xử lý mâu thuẫn **giữa hai nguồn cấu hình**. Vẫn cần quản lý script, hiểu port binding và kiểm soát dữ liệu triển khai.

### 12.3. Tách các tham số tác vụ khỏi cấu hình hệ thống

Một CLI tool viết bằng Spring Boot có thể nhận:

~~~bash
java -jar batch-tool.jar --job=import --file=/data/orders.csv
~~~

Ứng dụng muốn tự xử lý `job` và `file` trong một `ApplicationRunner`, nhưng không muốn chúng vô tình trở thành các thuộc tính toàn cục của `Environment`. Khi đó, có thể tắt command-line property source và đọc args ở lớp xử lý tác vụ.

Dù vậy, nếu một số option `--...` **phải điều khiển Spring Boot auto-configuration**, phương thức này có thể không phù hợp: nó tắt nguồn cấu hình CLI nói chung, chứ không chọn riêng các option cần bỏ qua.

## 13. Khi nào không nên dùng?

Không nên tắt nguồn CLI tùy tiện khi hệ thống phụ thuộc vào đối số `--...` để điều khiển Spring Boot.

Các tình huống cần cân nhắc:

- Một JAR được chạy bởi hệ thống vận hành với `--spring.profiles.active=...`.
- Một nền tảng khởi chạy tự truyền `--server.port=...`.
- Pipeline sử dụng `--spring.config.location=...` để trỏ đến tệp cấu hình.
- Script local dùng `--logging.level...` để bật log chẩn đoán.
- Job hoặc test dùng `--app.*` như cách chủ động cung cấp thông số binding vào `@ConfigurationProperties`.

Trong những bối cảnh đó, việc tắt command-line property source có thể làm các giá trị cấu hình mong đợi **không còn hiệu lực**. Một cách tiếp cận thay thế là chuẩn hóa và kiểm soát đối số ở tầng khởi chạy, hoặc chuyển các property cần dùng sang OS environment/system properties/config data. Nếu chỉ muốn cấm **một vài** option nhất định, phương thức này khá rộng vì nó áp dụng cho **toàn bộ command-line property source**.

Đây là quyết định ở mức thiết kế khởi động, cần được ghi nhận trong tài liệu triển khai để người vận hành biết nguồn nào thực sự được chương trình tôn trọng.

## 14. So sánh ba cách truyền giá trị khi command-line properties bị tắt

Giả sử:

~~~yaml
# application.yml
app:
  mode: from-file
~~~

Và trong `main`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Thực hiện các lần chạy độc lập:

| Cách chạy | Nguồn giá trị | `Environment.getProperty("app.mode")` |
| --- | --- | --- |
| `java -jar demo.jar` | File YAML | `from-file` |
| `java -jar demo.jar --app.mode=from-cli` | CLI bị tắt trong Environment | `from-file` |
| `APP_MODE=from-env java -jar demo.jar --app.mode=from-cli` | OS environment | `from-env` |
| `java -Dapp.mode=from-jvm -jar demo.jar --app.mode=from-cli` | Java system property | `from-jvm` |

Bảng giả định không có nguồn khác ghi đè và mỗi lần chạy tạo một tiến trình mới với môi trường sạch. Cú pháp `APP_MODE=... java ...` dùng cho shell Unix; trên PowerShell cần khai báo biến môi trường theo cú pháp PowerShell.

## 15. Phân biệt với các cách khác để làm việc với tham số dòng lệnh

### 15.1. `SpringApplication.setDefaultProperties(...)`

`setDefaultProperties(...)` cung cấp những giá trị fallback ở mức ưu tiên thấp. Nó **không** tắt command-line property source.

Ví dụ:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setDefaultProperties(java.util.Map.of("app.mode", "fallback"));
app.run(args);
~~~

Với mặc định Spring Boot, `--app.mode=from-cli` vẫn có thể ghi đè giá trị fallback. Nếu muốn vô hiệu hóa nguồn dòng lệnh, cần gọi đúng `setAddCommandLineProperties(false)`.

### 15.2. `ApplicationArguments`

`ApplicationArguments` cung cấp một giao diện **truy cập đối số đã parse**:

~~~java
@Bean
ApplicationRunner runner() {
    return args -> {
        if (args.containsOption("job")) {
            var values = args.getOptionValues("job");
            // Thẩm định giá trị rồi thực hiện tác vụ phù hợp.
        }
    };
}
~~~

Nó có thể đọc `--job=import` ngay cả khi command-line property source bị tắt. Nếu cần phân tích nhiều loại tham số, đây là điểm thích hợp để triển khai logic riêng.

### 15.3. `CommandLineRunner`

`CommandLineRunner` nhận mảng đối số dạng chuỗi:

~~~java
@Bean
CommandLineRunner printArgCount() {
    return args -> System.out.println("arg count = " + args.length);
}
~~~

Số lượng raw args không mặc nhiên trở thành 0 sau `setAddCommandLineProperties(false)`. Chúng vẫn được Spring Boot chuyển tới runner.

### 15.4. Tự thao tác `Environment` hoặc `PropertySource`

Spring Framework có API để đọc và tổ chức các property source. Nhưng nếu mục tiêu chỉ là vô hiệu hóa việc thêm command-line option properties, Spring Boot đã cung cấp **cờ trực tiếp** qua `SpringApplication`. Không cần tự truy cập `MutablePropertySources` để tìm và xóa property source sau khi context khởi động; thời điểm đó có thể đã quá muộn đối với cấu hình dùng trong startup.

## 16. Cách kiểm chứng hoạt động trên một ứng dụng mẫu

Hãy thực hiện cùng một ứng dụng với cấu hình sau:

~~~yaml
server:
  port: 8080
app:
  message: file-value
~~~

Dùng component quan sát:

~~~java
@Bean
ApplicationRunner verify(Environment environment) {
    return args -> {
        System.out.println("Effective server.port: "
                + environment.getProperty("server.port"));
        System.out.println("Effective app.message: "
                + environment.getProperty("app.message"));
        System.out.println("CLI app.message supplied: "
                + args.containsOption("app.message"));
    };
}
~~~

### Trường hợp A — Cho phép command-line properties

Trong `main` không gọi `setAddCommandLineProperties(false)` hoặc đặt `true`:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

Với các nguồn thông thường, cấu hình hiệu lực là port `9090` và message `cli-value`.

### Trường hợp B — Tắt command-line properties

Trong `main` đặt `setAddCommandLineProperties(false)` và chạy cùng lệnh:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

Với cùng giả định, port `8080` và message `file-value`; `args.containsOption("app.message")` vẫn là `true`.

### Trường hợp C — Tắt command-line properties nhưng cấp biến môi trường

~~~bash
SERVER_PORT=9191 APP_MESSAGE=env-value \
  java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

Port `9191` và message `env-value`, còn option CLI vẫn hiển thị qua `ApplicationArguments`.

Các bước kiểm chứng cho thấy phương thức này thay đổi **nguồn dữ liệu cho Environment**, đồng thời giữ đường đi của raw arguments.

## 17. Những lỗi và hiểu nhầm thường gặp

| Hiện tượng hoặc nhận định | Giải thích và cách xử lý |
| --- | --- |
| “Tắt CLI rồi mà `ApplicationRunner` vẫn thấy `--app.mode`.” | Đúng theo thiết kế: runner nhận `ApplicationArguments` độc lập với nguồn cấu hình CLI. |
| “`--server.port=9090` không còn hiệu lực.” | Kiểm tra `setAddCommandLineProperties(false)`; nếu được bật, dùng OS env, JVM property hoặc file để cấp port. |
| “`--spring.profiles.active=prod` không bật profile.” | Khi CLI property source bị tắt, cần cấp `spring.profiles.active` từ nguồn khác như `SPRING_PROFILES_ACTIVE` hoặc `-Dspring.profiles.active`. |
| “`--spring.config.additional-location` không tìm thêm thư mục.” | Cấu hình tìm tệp cần được nhận từ nguồn hoạt động rất sớm; dùng system property hoặc OS env. |
| “`-Dserver.port=9090` vẫn có hiệu lực, sao phương thức không chặn?” | `-D` là JVM system property, không phải app command-line property `--key=value`. |
| “Biến môi trường `SERVER_PORT` cũng bị tắt.” | Không. OS environment là một `PropertySource` khác. |
| “Gọi phương thức sau `run` sẽ đổi cấu hình.” | Phải thiết lập trước khi Spring Boot tạo và dùng `Environment` cho lần khởi động đó. |
| “Tắt nguồn CLI sẽ bảo mật mọi secret truyền qua argv.” | Sai. Raw args và process arguments vẫn có thể bị ghi lại hoặc được ứng dụng đọc. |
| “Chỉ muốn chặn `--server.port` nhưng giữ `--app.mode`.” | Phương thức này vô hiệu hóa toàn bộ command-line property source; cần thiết kế xử lý lựa chọn khác nếu muốn phân biệt từng option. |
| “Dùng `@Value` thì vẫn tự đọc các đối số đã tắt.” | `@Value` nhận giá trị thông qua hệ thống property; nó không tự biến raw args thành property. |
| “Không có `--key=value` thì app không thể cấu hình bên ngoài.” | Vẫn có application files, environment variables, JVM properties và các nguồn tích hợp khác. |

## 18. Bài tập suy luận

Giả sử ứng dụng gọi:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Cấu hình đóng gói:

~~~yaml
server:
  port: 8080
app:
  region: vn
  timeout: 3s
~~~

Được khởi động bằng:

~~~bash
APP_REGION=apac java -Dapp.timeout=7s -jar demo.jar \
  --server.port=9090 \
  --app.region=from-cli \
  --app.timeout=20s \
  --job=sync
~~~

**Câu hỏi 1:** các giá trị trong `Environment` là gì?

- `server.port=8080`, do `--server.port=9090` không trở thành property.
- `app.region=apac`, do biến môi trường `APP_REGION` vẫn có hiệu lực.
- `app.timeout=7s`, do JVM system property `-Dapp.timeout=7s` vẫn có hiệu lực.

**Câu hỏi 2:** một `ApplicationRunner` có nhìn thấy option `job` không?

Có. `ApplicationArguments.containsOption("job")` vẫn có thể trả về `true`; `getOptionValues("job")` có thể trả về `["sync"]`. Việc tắt command-line property source không loại đối số này khỏi `args`.

**Câu hỏi 3:** bỏ dòng `setAddCommandLineProperties(false)` thì điều gì thay đổi?

Với cơ chế mặc định và không có nguồn nào ưu tiên cao hơn CLI trong ví dụ, các giá trị có thể trở thành `server.port=9090`, `app.region=from-cli` và `app.timeout=20s`. Trong khi đó, `ApplicationArguments` vẫn nhận `--job=sync` ở cả hai chế độ.

## 19. Ghi nhớ

`setAddCommandLineProperties(false)` là cách cấu hình `SpringApplication` để **không thêm các option arguments dạng `--key=value` vào `Spring Environment`**. Nó phải được gọi trên instance khởi động **trước `run(args)`**.

Hãy phân biệt rõ ba điều:

1. **Nguồn cấu hình CLI:** bị tắt khi gọi phương thức với `false`; các giá trị `--...` không còn tự ghi đè property.
2. **Các nguồn cấu hình khác:** biến môi trường, Java system properties, application files và config data vẫn hoạt động theo quy tắc riêng.
3. **Đối số ứng dụng:** vẫn đến `main`, `ApplicationArguments`, `ApplicationRunner` và `CommandLineRunner`; mã ứng dụng vẫn có thể chủ động xử lý chúng.

Trước khi dùng trong hệ thống thật, xem lại cách deployment truyền `spring.profiles.active`, `spring.config.*`, `server.port`, `logging.level.*` và các property nghiệp vụ. Nếu chúng đang được cấp bằng `--...`, phải chuyển sang nguồn cấu hình phù hợp hoặc chấp nhận rằng chúng không còn tự tác động lên Spring Boot Environment.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Application Arguments: https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-arguments
- Spring Boot Javadoc — SpringApplication: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html
