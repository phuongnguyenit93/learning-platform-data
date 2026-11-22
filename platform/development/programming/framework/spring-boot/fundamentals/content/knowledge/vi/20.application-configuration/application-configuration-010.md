# Relaxed binding và quy ước tên thuộc tính, biến môi trường

Trong một ứng dụng Spring Boot, cùng một cấu hình có thể xuất hiện ở nhiều nơi: file `application.properties`, `application.yml`, biến môi trường của hệ điều hành, Java system property hoặc tham số dòng lệnh. Mỗi nơi lại có quy ước đặt tên khác nhau. Ví dụ, tên thuộc tính trong file thường viết dạng `app.mail.sender-address`, trong Java là `senderAddress`, còn ở biến môi trường có thể là `APP_MAIL_SENDERADDRESS`.

Spring Boot cung cấp cơ chế **relaxed binding** để ánh xạ những cách viết khác nhau đó vào cùng một cấu trúc cấu hình, đặc biệt thông qua `@ConfigurationProperties`. Cơ chế này giúp ứng dụng giữ một mô hình cấu hình rõ ràng mà không phải tạo riêng một tên cho từng môi trường chạy.

Tuy nhiên, **relaxed không có nghĩa là mọi cách thêm dấu gạch dưới hoặc dấu gạch ngang đều tương đương**. Đặc biệt, khi chuyển từ thuộc tính chứa dấu chấm và dấu gạch ngang sang biến môi trường, cần tuân theo quy tắc chuẩn để tránh cấu hình không được nhận hoặc bị hiểu thành một đường dẫn khác.

Bài học thuộc **Spring Boot Fundamentals → Cấu hình ứng dụng**, tập trung vào:

- Hiểu relaxed binding là gì và áp dụng cho trường hợp nào.
- Phân biệt **kebab-case**, **camelCase**, **underscore notation** và **UPPER_CASE**.
- Chuyển đúng tên thuộc tính sang tên biến môi trường.
- Sử dụng `@ConfigurationProperties` cho cấu hình có cấu trúc.
- Hiểu giới hạn khi dùng `@Value`, danh sách, map và nhiều nguồn cấu hình.
- Điều tra các lỗi cấu hình thường gặp mà không phải thử ngẫu nhiên nhiều cách đặt tên.

## 1. Bài toán: một cấu hình, nhiều cách biểu diễn

Giả sử ứng dụng gửi email và có cấu hình địa chỉ người gửi. Tên thuộc tính chuẩn ta chọn là:

~~~properties
app.mail.sender-address=no-reply@example.org
~~~

Trong Java, trường tương ứng có thể mang tên:

~~~java
private String senderAddress;
~~~

Ở môi trường production, thay vì sửa file đóng gói trong JAR, đội vận hành muốn đặt cấu hình qua biến môi trường:

~~~bash
export APP_MAIL_SENDERADDRESS=notifications@example.org
~~~

Ba cách biểu diễn trên cùng mô tả một giá trị logic:

~~~text
application.properties     app.mail.sender-address
                                  |
                                  | relaxed binding
                                  v
Java configuration bean    senderAddress
                                  ^
                                  | relaxed binding
                                  |
Environment variable      APP_MAIL_SENDERADDRESS
~~~

Mục tiêu là cho code Java đọc **một thuộc tính kiểu mạnh** và Spring Boot đảm nhiệm việc giải thích tên thuộc tính theo quy ước của nguồn cấu hình.

Nếu không có cơ chế này, ứng dụng dễ phải tự viết các nhánh đọc `System.getenv(...)`, xử lý chuyển đổi chuỗi, kiểm tra giá trị mặc định và giải quyết xung đột giữa file với biến môi trường.

### Tên thuộc tính khác với giá trị thuộc tính

Relaxed binding chủ yếu nói về **cách nhận diện tên**. Sau khi xác định được thuộc tính, Spring Boot còn thực hiện **chuyển đổi giá trị** sang kiểu Java như `int`, `Duration`, `DataSize`, `boolean`, enum hoặc danh sách.

Ví dụ:

~~~properties
app.mail.retry-interval=15s
~~~

Tên `retry-interval` có thể bind tới trường `retryInterval`, còn chuỗi `15s` được chuyển thành `Duration`. Đây là hai khả năng liên quan nhưng không đồng nhất: **chuẩn hóa tên** và **chuyển đổi kiểu giá trị**.

## 2. Relaxed binding là gì?

**Relaxed binding** là khả năng binder của Spring Boot chấp nhận các biến thể đặt tên hợp lệ khi ánh xạ property từ các `PropertySource` vào một đối tượng cấu hình.

Ví dụ class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String senderAddress;

    public String getSenderAddress() {
        return senderAddress;
    }

    public void setSenderAddress(String senderAddress) {
        this.senderAddress = senderAddress;
    }
}
~~~

Khi được đăng ký làm configuration properties bean, class này có thể nhận giá trị theo những biến thể của cùng một property, tùy nguồn:

| Nơi khai báo | Cách viết minh họa |
|---|---|
| `application.properties` | `app.mail.sender-address=...` |
| `application.properties` | `app.mail.senderAddress=...` |
| `application.properties` | `app.mail.sender_address=...` |
| Biến môi trường | `APP_MAIL_SENDERADDRESS=...` |
| Trường Java | `senderAddress` |

Có thể hình dung binder tách namespace `app.mail`, sau đó nhận diện tên trường `senderAddress` theo quy ước hợp lệ của nguồn dữ liệu.

**Cần phân biệt:** ví dụ trên minh họa relaxed binding của `@ConfigurationProperties`, không khẳng định mọi API tra cứu property hoặc mọi loại `PropertySource` đều có hành vi giống hệt.

### Relaxed binding không phải là đổi tên tự do

Những tên mang nghĩa khác nhau không tự trở thành một chỉ vì giống mắt nhìn:

- `app.mail.sender-address` và `app.mail.server-address` mô tả hai thuộc tính khác nhau.
- `app.mail.sender-address` và `app.mails.sender-address` có namespace khác nhau.
- `app.mail.sender-address` và `app.mail.sender.address` có cấu trúc dấu chấm khác nhau.
- `app.mail.timeout` và `app.mail.timeouts` không phải một.

Mục đích của relaxed binding là hỗ trợ **biến thể cú pháp của cùng một thuộc tính**, không phải suy đoán ý định khi người viết đổi cấu trúc hoặc đánh sai tên.

## 3. Kebab-case là dạng chuẩn nên dùng

Trong tài liệu và tên thuộc tính cấu hình của ứng dụng, nên chọn **lowercase kebab-case**:

~~~properties
app.mail.sender-address=no-reply@example.org
app.mail.retry-interval=10s
app.mail.max-attempts=3
~~~

Cách viết này có các đặc điểm:

- Các thành phần namespace phân cách bởi dấu chấm: `app.mail`.
- Trong một thành phần, các từ phân cách bằng dấu gạch ngang: `sender-address`.
- Chữ thường giúp tránh nhập nhằng.
- Dễ đọc và tương thích với cách đặt tên canonical được Spring Boot khuyến nghị.

So sánh ba cách đặt tên:

| Dạng | Ví dụ | Thường dùng ở đâu? |
|---|---|---|
| Kebab-case | `sender-address` | Tên property canonical trong file |
| camelCase | `senderAddress` | Tên biến/trường trong Java |
| Underscore notation | `sender_address` | Biến thể được binder hỗ trợ trong một số nguồn |
| Uppercase env convention | `APP_MAIL_SENDERADDRESS` | Biến môi trường của hệ điều hành |

Với `@ConfigurationProperties(prefix = "...")`, phần **prefix** cũng nên viết theo canonical kebab-case: chữ thường, dấu chấm phân tách namespace và dấu gạch ngang phân tách từ bên trong mỗi thành phần.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "integration.mail-service")
public class MailServiceProperties {
    // ...
}
~~~

Viết `integration.mail-service` rõ ràng hơn việc đưa cách viết camelCase hoặc chữ hoa vào prefix.

## 4. Quy tắc chuyển property name sang biến môi trường

Spring Boot mô tả một quy tắc chuẩn để chuyển tên property canonical thành dạng thích hợp cho biến môi trường:

1. **Thay dấu chấm (`.`) bằng dấu gạch dưới (`_`)** để phân cách các thành phần namespace.
2. **Xóa dấu gạch ngang (`-`)** bên trong tên thuộc tính; không biến mỗi dấu gạch ngang thành một dấu gạch dưới mới.
3. **Chuyển tất cả chữ cái thành chữ hoa**.

Ví dụ bắt đầu từ:

~~~text
spring.main.log-startup-info
~~~

Áp dụng từng bước:

~~~text
Bước 1. Dấu chấm thành dấu gạch dưới:
spring_main_log-startup-info

Bước 2. Xóa dấu gạch ngang:
spring_main_logstartupinfo

Bước 3. Chuyển chữ hoa:
SPRING_MAIN_LOGSTARTUPINFO
~~~

Kết quả:

~~~bash
export SPRING_MAIN_LOGSTARTUPINFO=false
~~~

Các ví dụ khác:

| Tên property canonical | Tên biến môi trường theo quy tắc |
|---|---|
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `app.mail.sender-address` | `APP_MAIL_SENDERADDRESS` |
| `app.mail.retry-interval` | `APP_MAIL_RETRYINTERVAL` |
| `app.report.max-file-size` | `APP_REPORT_MAXFILESIZE` |
| `app.feature.new-dashboard-enabled` | `APP_FEATURE_NEWDASHBOARDENABLED` |
| `integration.mail-service.connect-timeout` | `INTEGRATION_MAILSERVICE_CONNECTTIMEOUT` |

**Điểm dễ nhầm:** `app.mail.sender-address` không được chuyển theo quy tắc chuẩn thành `APP_MAIL_SENDER_ADDRESS`. Ký tự `_` trong quy ước env được dùng để thay **dấu chấm**, còn dấu gạch ngang trong `sender-address` phải được **bỏ đi**.

Nói cách khác:

~~~text
app.mail.sender-address
       ^      ^
       |      +-- dấu "-" bị loại bỏ
       +--------- dấu "." thành "_"

=> APP_MAIL_SENDERADDRESS
~~~

Nếu một tên env được đặt là `APP_MAIL_SENDER_ADDRESS`, các thành phần phân tách bằng dấu gạch dưới có thể được diễn giải như một đường dẫn property khác, ví dụ `app.mail.sender.address`. Không nên đặt tên tùy tiện rồi dựa vào relaxed binding để đoán rằng binder sẽ hiểu đúng.

### Vì sao có tên env rất dài và liền chữ?

Ví dụ `APP_FEATURE_NEWDASHBOARDENABLED` có vẻ khó đọc hơn `APP_FEATURE_NEW_DASHBOARD_ENABLED`. Đây là hệ quả của quy tắc chuyển từ **cấu trúc property** sang **cấu trúc env**.

Điều đó không cấm bạn thiết kế tên cấu hình ngắn gọn và hợp lý. Bạn có thể chọn property canonical đơn giản hơn ngay từ đầu. Tuy nhiên, khi đã công bố một property, nên tuân thủ tên env tương ứng để tránh hai hệ thống cùng dùng hai quy ước khác nhau.

## 5. Biến môi trường không phải property file

Biến môi trường thuộc môi trường thực thi của process. Chúng không tự nằm trong JAR và không cần được khai báo trong `application.properties` nếu Spring Boot có thể đọc chúng từ environment.

Ví dụ trên Linux/macOS shell:

~~~bash
export APP_MAIL_SENDERADDRESS=alerts@example.org
export APP_MAIL_RETRYINTERVAL=20s

java -jar app.jar
~~~

Nếu chỉ muốn đặt cho một lần chạy:

~~~bash
APP_MAIL_RETRYINTERVAL=20s java -jar app.jar
~~~

Trên Windows PowerShell:

~~~powershell
$env:APP_MAIL_SENDERADDRESS = "alerts@example.org"
$env:APP_MAIL_RETRYINTERVAL = "20s"

java -jar app.jar
~~~

Giá trị cần tồn tại trong **môi trường của process Java** khi ứng dụng khởi động. Thay đổi biến ở một shell khác thường không tự cập nhật environment của process Java đã chạy.

Nếu chạy qua Docker, Kubernetes, IDE hoặc service manager, cần truyền biến vào đúng process/container. Việc biến tồn tại trên máy chủ không đồng nghĩa container hoặc dịch vụ của bạn tự nhận được nó.

### Ví dụ trong Docker Compose

~~~yaml
services:
  backend:
    image: example/backend:latest
    environment:
      APP_MAIL_SENDERADDRESS: alerts@example.org
      APP_MAIL_RETRYINTERVAL: 20s
~~~

Phần `environment` của Compose làm cho các biến đó xuất hiện trong môi trường process của container. Spring Boot có thể nhận chúng qua property source tương ứng, miễn là tên khớp với cấu hình ứng dụng.

Đối với password hoặc token, cần một cơ chế quản lý secret phù hợp thay vì đưa giá trị thật trực tiếp vào file cấu hình có thể được commit.

## 6. @ConfigurationProperties: trung tâm của relaxed binding

Cách sử dụng relaxed binding rõ ràng nhất là gom các thuộc tính có quan hệ thành một configuration properties type.

Ví dụ ứng dụng tích hợp dịch vụ gửi thông báo. Ta chọn các property:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

Trong Spring Boot 3.x, có thể dùng Java record:

~~~java
package com.example.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        String senderAddress,
        Duration retryInterval,
        int maxAttempts
) {
}
~~~

Giải thích ánh xạ:

| Property canonical | Thành phần record | Kiểu Java |
|---|---|---|
| `app.notification.sender-address` | `senderAddress` | `String` |
| `app.notification.retry-interval` | `retryInterval` | `Duration` |
| `app.notification.max-attempts` | `maxAttempts` | `int` |

Binder nhận các property rồi chuyển giá trị thành kiểu tương ứng. Ví dụ `5s` được chuyển thành `Duration` dài 5 giây.

### Đăng ký configuration properties bean

Trên class main:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm các class được chú thích `@ConfigurationProperties` trong package phù hợp để đăng ký bean.

Một lựa chọn khác là dùng `@EnableConfigurationProperties(NotificationProperties.class)` tại class cấu hình:

~~~java
@Configuration
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Khi dùng kiểu record constructor-bound như ví dụ, nên đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, thay vì tự tạo record bằng một `@Bean` rồi mong binder xử lý constructor đó theo cùng một cách.

### Sử dụng trong service

~~~java
package com.example.notification;

import org.springframework.stereotype.Service;
import com.example.config.NotificationProperties;

@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public void showRetrySettings() {
        System.out.println(
                "Retry interval: " + properties.retryInterval());
        System.out.println(
                "Max attempts: " + properties.maxAttempts());
    }
}
~~~

Service nhận cấu hình đã bind và chuyển kiểu sẵn qua dependency injection. Nó không cần biết property đến từ YAML, properties hay environment variable.

**Không nên in ra email password, access token hoặc secret** trong logic demo hoặc log production. Ở đây chỉ hiển thị thông số retry không nhạy cảm.

## 7. Cấu hình YAML và .properties là hai cách biểu diễn tương đương

Với ví dụ `NotificationProperties`, file `application.properties`:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

Có thể viết tương đương trong `application.yml`:

~~~yaml
app:
  notification:
    sender-address: no-reply@example.org
    retry-interval: 5s
    max-attempts: 3
~~~

Trong YAML, cấu trúc lồng nhau biểu diễn các thành phần phân tách bằng dấu chấm. Spring Boot xử lý dữ liệu cấu hình và binder ánh xạ tới record:

~~~text
app
 +-- notification
      +-- sender-address  ---> senderAddress
      +-- retry-interval  ---> retryInterval
      +-- max-attempts    ---> maxAttempts
~~~

Đừng hiểu rằng YAML là một dạng binding khác biệt hoàn toàn. Mục tiêu cuối cùng vẫn là property name và property value.

Để tránh xung đột khó hiểu, một project nên có quy ước nhất quán về file cấu hình và thứ tự nguồn dữ liệu. Không cần khai báo cùng một giá trị ở cả `application.properties` và `application.yml` chỉ để thử xem relaxed binding có hoạt động hay không.

## 8. Ghi đè cấu hình bằng biến môi trường

Tiếp tục ví dụ trên, để giữ giá trị mặc định trong file và thay đổi ở môi trường triển khai:

~~~properties
app.notification.sender-address=no-reply@example.org
app.notification.retry-interval=5s
app.notification.max-attempts=3
~~~

Đặt biến môi trường:

~~~bash
export APP_NOTIFICATION_SENDERADDRESS=ops@example.org
export APP_NOTIFICATION_RETRYINTERVAL=30s
~~~

Khi ứng dụng chạy trong cấu hình Spring Boot thông thường, giá trị từ biến môi trường có thể ghi đè các giá trị tương ứng từ file:

~~~text
notification.senderAddress  = "ops@example.org"
notification.retryInterval  = PT30S
notification.maxAttempts    = 3
~~~

`PT30S` là cách `Duration.toString()` biểu diễn thời lượng 30 giây, không phải một yêu cầu bắt buộc về định dạng nguồn cấu hình.

Một điểm cần hiểu: **relaxed binding quyết định những tên nào chỉ cùng một property; property-source precedence quyết định giá trị nào thắng khi nhiều nguồn khai báo property đó**. Đây là hai cơ chế độc lập.

### Tham số dòng lệnh cũng có thể ghi đè

Ví dụ:

~~~bash
java -jar app.jar --app.notification.retry-interval=45s
~~~

Trong thứ tự nguồn cấu hình thông thường của Spring Boot, command-line property có độ ưu tiên cao hơn biến môi trường và file application config. Vì vậy nó thường cho giá trị cuối là `45s`.

Không nên tự xây dựng một “thứ tự toàn cục” dựa trên tên property. Thứ tự ưu tiên đến từ cách các `PropertySource` được Spring Boot sắp xếp, profile, config import và tùy chỉnh của ứng dụng. Nếu dự án đã thay đổi thứ tự property sources, cần xét cấu hình thực tế.

## 9. @Value có dùng relaxed binding giống @ConfigurationProperties không?

`@Value` cho phép lấy giá trị từ một property bằng placeholder:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MailSender {

    @Value("${app.notification.sender-address}")
    private String senderAddress;
}
~~~

Điểm cần lưu ý:

- `@Value` phù hợp với một vài giá trị riêng lẻ.
- `@ConfigurationProperties` phù hợp với nhóm thuộc tính có cấu trúc và hỗ trợ relaxed binding chuyên biệt.
- Xử lý placeholder của `@Value` **không giống hoàn toàn** với binder dùng cho `@ConfigurationProperties`.
- Spring Boot khuyến nghị dùng tên **canonical kebab-case** trong placeholder để tận dụng khả năng tìm các biến thể tên thuộc tính tốt hơn.

Nên viết:

~~~java
@Value("${app.notification.sender-address}")
private String senderAddress;
~~~

Thay vì dựa vào tên camelCase:

~~~java
@Value("${app.notification.senderAddress}")
private String senderAddress;
~~~

Tên camelCase trong `@Value` có thể không được tìm theo cùng tập quy tắc relaxed như canonical name. Vì vậy nên nhất quán cách viết canonical, kể cả khi field Java dùng camelCase.

### Giá trị mặc định trong @Value

Có thể cung cấp fallback đơn giản:

~~~java
@Value("${app.notification.max-attempts:3}")
private int maxAttempts;
~~~

Dấu `:3` thể hiện giá trị mặc định nếu placeholder không tìm được thuộc tính. Với nhiều thuộc tính liên quan, immutable configuration properties và validation thường dễ bảo trì hơn việc rải `@Value` trên nhiều bean.

### Khi nào chọn loại nào?

| Trường hợp | Gợi ý |
|---|---|
| Một cờ hoặc một giá trị riêng lẻ | `@Value` có thể đủ |
| Một nhóm cấu hình liên quan | `@ConfigurationProperties` |
| Cấu hình lồng nhau | `@ConfigurationProperties` |
| List, Map, Duration, DataSize có cấu trúc | `@ConfigurationProperties` |
| Cần validation cấu hình | `@ConfigurationProperties` kết hợp Bean Validation |
| Cần biểu thức SpEL | `@Value` hỗ trợ expression; `@ConfigurationProperties` binder không được thiết kế để đánh giá SpEL |

Bài học này tập trung vào tên thuộc tính; quyết định cuối cùng còn phụ thuộc vào thiết kế configuration object của ứng dụng.

## 10. Property binding sang object lồng nhau

Trong thực tế, cấu hình thường có nhiều tầng:

~~~yaml
app:
  mail:
    smtp:
      host: smtp.example.org
      port: 587
      connect-timeout: 10s
~~~

Ta có thể thiết kế cấu hình tương ứng:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(Smtp smtp) {

    public record Smtp(
            String host,
            int port,
            Duration connectTimeout
    ) {
    }
}
~~~

Cấu hình sẽ được bind theo đường dẫn:

~~~text
app.mail.smtp.host                 -> smtp.host
app.mail.smtp.port                 -> smtp.port
app.mail.smtp.connect-timeout      -> smtp.connectTimeout
~~~

Và biến môi trường có thể là:

~~~bash
export APP_MAIL_SMTP_HOST=smtp.internal.example.org
export APP_MAIL_SMTP_PORT=2525
export APP_MAIL_SMTP_CONNECTTIMEOUT=15s
~~~

Chú ý cách đặt underscore:

- `APP_MAIL_SMTP` tương ứng với namespace `app.mail.smtp`.
- `HOST` hoặc `PORT` là tên thành phần bên dưới.
- `CONNECTTIMEOUT` tương ứng với tên thuộc tính một thành phần `connect-timeout`.

Không nên chuyển `connect-timeout` thành `CONNECT_TIMEOUT` theo thói quen rồi mặc định binder sẽ xử lý như một thuộc tính duy nhất.

## 11. Binding danh sách: quy tắc chỉ số

Với danh sách, index nằm giữa dấu ngoặc vuông trong property canonical:

~~~properties
app.clients[0].base-url=https://api-one.example.org
app.clients[0].max-connections=4
app.clients[1].base-url=https://api-two.example.org
app.clients[1].max-connections=6
~~~

Trong biến môi trường, quy ước dành cho list index dùng chữ số được bao bởi dấu gạch dưới để biểu diễn vị trí trong đường dẫn.

Ví dụ:

~~~text
app.clients[0].base-url        -> APP_CLIENTS_0_BASEURL
app.clients[0].max-connections -> APP_CLIENTS_0_MAXCONNECTIONS
app.clients[1].base-url        -> APP_CLIENTS_1_BASEURL
~~~

Trong Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientProperties(List<Client> clients) {

    public record Client(String baseUrl, int maxConnections) {
    }
}
~~~

Ở đây:

- `clients` là danh sách.
- `0` và `1` là vị trí của từng phần tử.
- `base-url` bind vào thành phần Java `baseUrl`.
- `max-connections` bind vào `maxConnections`.

### Viết danh sách bằng YAML

~~~yaml
app:
  clients:
    - base-url: https://api-one.example.org
      max-connections: 4
    - base-url: https://api-two.example.org
      max-connections: 6
~~~

Đây là cách dễ đọc hơn khi một danh sách có nhiều object hoặc nhiều thành phần.

### Lưu ý về ghi đè danh sách

Một điểm rất quan trọng: **khi cùng một list được định nghĩa ở nhiều property source, Spring Boot thường chọn list từ nguồn có độ ưu tiên cao hơn, thay vì tự ghép từng phần tử của các nguồn như phép merge tùy ý**.

Giả sử file YAML khai báo hai client, còn biến môi trường chỉ định client ở index 0. Không nên mặc định client ở index 1 của YAML luôn được giữ nguyên theo cách bạn dự tính.

Khi cần ghi đè danh sách qua environment, hãy xác định rõ quy tắc ghi đè và cung cấp đầy đủ danh sách cần thiết ở nguồn ưu tiên cao hơn. Với danh sách phức tạp, một file cấu hình riêng theo profile hoặc `SPRING_APPLICATION_JSON` có thể dễ quản lý hơn nhiều biến môi trường rời rạc.

## 12. Map: tên khóa không nhất thiết là Java property name

Ví dụ ứng dụng có map tên tuyến đến URL:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RouteProperties(Map<String, String> routes) {
}
~~~

Trong `application.properties`, nếu key của map chứa ký tự đặc biệt cần giữ nguyên, dùng cú pháp **ngoặc vuông**:

~~~properties
app.routes.[/payments]=https://payments.example.org
app.routes.[/orders]=https://orders.example.org
~~~

Trong `application.yml`, khóa có ngoặc vuông nên được đặt trong dấu nháy:

~~~yaml
app:
  routes:
    "[/payments]": https://payments.example.org
    "[/orders]": https://orders.example.org
~~~

Khi đó, keys mong muốn là `/payments` và `/orders`, thay vì bị chuẩn hóa làm mất ký tự đặc biệt.

Nếu không dùng ngoặc vuông, binder có thể loại bỏ một số ký tự không được hỗ trợ trong key của map khi bind, khiến tên key thực tế không như mong đợi.

### Hạn chế khi map key đến từ biến môi trường

Tên biến môi trường truyền thống chỉ hỗ trợ tập ký tự khá hạn chế. Việc biểu diễn chính xác key chứa dấu `/`, dấu chấm hoặc phân biệt chữ hoa/chữ thường có thể khó hoặc không thực hiện được bằng cách chuyển tên env đơn giản.

Đặc biệt, khi bind map từ system environment variables, key có thể được chuyển thành chữ thường. Nếu logic nghiệp vụ cần **giữ nguyên chính xác mọi ký tự của key**, nên sử dụng YAML/properties với bracket notation, cấu hình JSON thích hợp hoặc một nguồn cấu hình chuyên biệt.

Không nên coi quy tắc đặt tên env cho bean field là giải pháp tổng quát cho mọi loại key tùy ý trong map.

## 13. Field Java, prefix và tên env phải khớp đúng về cấu trúc

Đặt cấu hình:

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        String apiEndpoint,
        String clientId,
        Duration connectionTimeout
) {
}
~~~

Các property canonical tương ứng:

~~~properties
payment.gateway.api-endpoint=https://pay.example.org
payment.gateway.client-id=demo-client
payment.gateway.connection-timeout=5s
~~~

Và biến môi trường:

~~~text
PAYMENT_GATEWAY_APIENDPOINT
PAYMENT_GATEWAY_CLIENTID
PAYMENT_GATEWAY_CONNECTIONTIMEOUT
~~~

Sơ đồ:

~~~text
prefix                         property name
payment.gateway                connection-timeout
       |                              |
       v                              v
PAYMENT_GATEWAY                CONNECTIONTIMEOUT
       |                              |
       +--------------+---------------+
                      |
                      v
       PAYMENT_GATEWAY_CONNECTIONTIMEOUT
~~~

Các lỗi dễ xảy ra:

- Viết sai prefix: `payments.gateway` thay vì `payment.gateway`.
- Dùng tên field không khớp: `connectTimeout` nhưng cấu hình tên `connection-timeout`.
- Đưa thêm namespace: `PAYMENT_GATEWAY_CONNECTION_TIMEOUT` rồi kỳ vọng dấu underscore thứ ba là dấu gạch ngang.
- Không đăng ký `@ConfigurationProperties` bean.
- Giá trị cấu hình bị nguồn ưu tiên cao hơn ghi đè.

Relaxed binding giúp giảm phụ thuộc vào cách viết **bên trong cùng một tên logic**, chứ không tự sửa lỗi thiết kế namespace.

## 14. Chuyển đổi kiểu giá trị có liên quan thế nào?

Một số ví dụ:

| Property canonical | Giá trị mẫu | Kiểu Java phù hợp |
|---|---|---|
| `app.retry.max-attempts` | `4` | `int` |
| `app.retry.enabled` | `true` | `boolean` |
| `app.retry.delay` | `250ms` | `Duration` |
| `app.upload.max-size` | `10MB` | `DataSize` |
| `app.mode` | `SAFE` | Enum ứng dụng |
| `app.tags` | Tùy cách khai báo nguồn | `List<String>` |

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.limits")
public record LimitProperties(
        Duration requestTimeout,
        DataSize maxPayloadSize
) {
}
~~~

Và:

~~~properties
app.limits.request-timeout=2s
app.limits.max-payload-size=10MB
~~~

Trong trường hợp này:

- `request-timeout` bind vào `requestTimeout` nhờ relaxed binding.
- `max-payload-size` bind vào `maxPayloadSize`.
- Binder chuyển `2s` thành `Duration`.
- Binder chuyển `10MB` thành `DataSize`.

Annotation `@DataSizeUnit` chỉ cần khi ứng dụng muốn quy định đơn vị mặc định cho một số trường hợp số không có hậu tố; nó không bắt buộc trong ví dụ đã có `10MB`. Import đó có thể bỏ khỏi class minh họa.

### Lỗi kiểu giá trị không phải lỗi tên property

Nếu viết:

~~~properties
app.limits.request-timeout=tomorrow
~~~

thì tên property có thể hoàn toàn đúng, nhưng giá trị không chuyển được thành `Duration`. Khi xử lý lỗi startup, cần phân biệt:

- Không tìm thấy property vì sai tên hoặc sai nguồn.
- Tìm thấy property nhưng giá trị không convert được.
- Tìm thấy và convert được, nhưng giá trị không thỏa quy tắc validation.

Đây là ba nhóm vấn đề khác nhau.

## 15. Validation giúp phát hiện cấu hình thiếu hoặc sai

Relaxed binding làm cấu hình linh hoạt hơn, nhưng không bảo đảm mọi thuộc tính bắt buộc có giá trị hợp lệ. Một tên cấu hình viết sai có thể khiến field giữ giá trị `null` hoặc giá trị mặc định mà ứng dụng không mong muốn.

Với Spring Boot và Bean Validation, có thể ràng buộc một configuration properties record:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @NotBlank String senderAddress,
        @Min(1) int maxAttempts
) {
}
~~~

Nếu dự án dùng Spring Boot starter theo cách thông thường, hãy bảo đảm có dependency Bean Validation thích hợp, chẳng hạn `spring-boot-starter-validation`.

Ví dụ cấu hình:

~~~properties
app.notification.sender-address=
app.notification.max-attempts=0
~~~

Cấu hình có thể được bind, nhưng validation phát hiện giá trị không thỏa ràng buộc. Nhờ đó, ứng dụng có thể thất bại ngay khi khởi động thay vì âm thầm vận hành bằng cấu hình sai.

Lưu ý rằng validation không tự phát hiện mọi property dư thừa hoặc mọi lỗi chính tả. Cần thiết kế cấu hình rõ ràng và chọn chính sách xử lý những giá trị không bind được phù hợp với yêu cầu hệ thống.

## 16. PropertySource precedence: một tên có thể có nhiều giá trị

Giả sử cùng một property xuất hiện ở ba nơi:

~~~properties
# application.properties
app.notification.max-attempts=3
~~~

~~~bash
# Process environment
export APP_NOTIFICATION_MAXATTEMPTS=5
~~~

~~~bash
# Command-line args
java -jar app.jar --app.notification.max-attempts=7
~~~

Trong cấu hình Spring Boot điển hình, giá trị từ dòng lệnh thường có độ ưu tiên cao hơn biến môi trường, còn biến môi trường thường cao hơn config data đóng gói trong ứng dụng. Do đó, giá trị cuối thường là `7`.

Quan trọng: Spring Boot không chọn dựa trên việc tên nào viết hoa, camelCase hay kebab-case. Nó xem nguồn giá trị và thứ tự ưu tiên, sau khi đã xác định các tên là tương ứng.

### Profile có tác động tới kết quả

Giả sử có:

~~~properties
# application.properties
app.notification.max-attempts=3
~~~

~~~properties
# application-prod.properties
app.notification.max-attempts=6
~~~

Khi profile `prod` được kích hoạt, config theo profile có thể ghi đè cấu hình cơ sở. Sau đó các nguồn có độ ưu tiên cao hơn, như environment hoặc command-line args, vẫn có thể ảnh hưởng tới kết quả.

Biến môi trường thường dùng để chọn profile:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
~~~

Tuy nhiên, thứ tự cụ thể còn tùy cách ứng dụng tải config import, profile, external files và các `PropertySource` bổ sung. Khi debug, đừng chỉ tìm một property trong một file rồi kết luận đó là giá trị có hiệu lực.

## 17. SPRING_APPLICATION_JSON khi env name không đủ linh hoạt

Với cấu hình lồng nhau hoặc key khó biểu diễn bằng tên env thông thường, Spring Boot có thể đọc dữ liệu JSON từ `SPRING_APPLICATION_JSON`.

Ví dụ:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"notification":{"sender-address":"alerts@example.org","max-attempts":4}}}'
java -jar app.jar
~~~

Tương đương với một cấu trúc property:

~~~text
app.notification.sender-address = alerts@example.org
app.notification.max-attempts   = 4
~~~

Ưu điểm là giữ được dấu gạch ngang và cấu trúc lồng nhau mà không phải suy luận quá nhiều dấu gạch dưới.

Cần lưu ý:

- JSON phải đúng cú pháp.
- Cách quote khác nhau giữa shell và các nền tảng.
- Giá trị vẫn chịu quy tắc ưu tiên giữa property sources.
- Không nên đặt secret trong lệnh hiển thị công khai, history hoặc log.
- Giá trị `null` trong JSON không luôn có tác dụng “xóa” một thuộc tính đang có ở nguồn khác, vì cơ chế resolve property có những quy tắc riêng với null.

Đối với một số ứng dụng phức tạp, file config mount vào container hoặc kho cấu hình chuyên biệt vẫn là cách rõ ràng hơn.

## 18. Ví dụ tổng hợp: Java record, YAML và biến môi trường

Ta xây dựng cấu hình cho service gọi API ngoài.

### 18.1. File cấu hình cơ sở

`src/main/resources/application.yml`:

~~~yaml
integration:
  inventory:
    base-url: https://inventory.example.org
    connect-timeout: 3s
    max-retries: 2
    enabled: true
~~~

### 18.2. Record bind cấu hình

`InventoryClientProperties.java`:

~~~java
package com.example.inventory;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.inventory")
public record InventoryClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled
) {
}
~~~

Đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(InventoryClientProperties.class)`.

### 18.3. Service sử dụng cấu hình

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryClient {

    private final InventoryClientProperties properties;

    public InventoryClient(InventoryClientProperties properties) {
        this.properties = properties;
    }

    public String targetDescription() {
        return "Inventory endpoint: " + properties.baseUrl()
                + "; timeout: " + properties.connectTimeout()
                + "; retry count: " + properties.maxRetries()
                + "; enabled: " + properties.enabled();
    }
}
~~~

Đây là ví dụ minh họa việc đọc cấu hình đã bind; service chưa thực hiện network request thực sự.

### 18.4. Ghi đè khi triển khai

Tên biến môi trường tương ứng:

~~~text
integration.inventory.base-url          -> INTEGRATION_INVENTORY_BASEURL
integration.inventory.connect-timeout   -> INTEGRATION_INVENTORY_CONNECTTIMEOUT
integration.inventory.max-retries       -> INTEGRATION_INVENTORY_MAXRETRIES
integration.inventory.enabled           -> INTEGRATION_INVENTORY_ENABLED
~~~

Ví dụ:

~~~bash
export INTEGRATION_INVENTORY_BASEURL=https://inventory.internal.example.org
export INTEGRATION_INVENTORY_CONNECTTIMEOUT=8s
export INTEGRATION_INVENTORY_MAXRETRIES=5
export INTEGRATION_INVENTORY_ENABLED=true

java -jar app.jar
~~~

Nếu biến môi trường có mặt trong đúng process và không có nguồn cấu hình khác ưu tiên hơn, bean nhận:

~~~text
baseUrl        = https://inventory.internal.example.org
connectTimeout = PT8S
maxRetries     = 5
enabled        = true
~~~

Điều này cho phép triển khai cùng một artifact lên nhiều môi trường mà không phải biên dịch lại chỉ để thay URL và timeout.

## 19. Khi một env var “không có tác dụng”, kiểm tra gì?

Giả sử bạn đặt:

~~~bash
export APP_NOTIFICATION_RETRY_INTERVAL=20s
~~~

nhưng ứng dụng vẫn đọc giá trị mặc định từ YAML cho `app.notification.retry-interval`. Đừng lập tức kết luận Spring Boot bị lỗi. Nên kiểm tra theo thứ tự có căn cứ.

### Bước 1: xác định tên canonical thực tế

Tìm prefix và trường Java:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(Duration retryInterval) {}
~~~

Từ đó tên canonical là:

~~~text
app.notification.retry-interval
~~~

### Bước 2: chuyển tên theo quy tắc chuẩn

~~~text
app.notification.retry-interval
          |
          v
APP_NOTIFICATION_RETRYINTERVAL
~~~

Tránh thêm underscore thay cho dấu gạch ngang.

### Bước 3: kiểm tra đúng process có biến

Trên Linux/macOS, trước khi chạy ứng dụng, có thể xem:

~~~bash
printenv APP_NOTIFICATION_RETRYINTERVAL
~~~

Trên PowerShell:

~~~powershell
$env:APP_NOTIFICATION_RETRYINTERVAL
~~~

Nếu chạy trong container, phải kiểm tra environment bên trong container hoặc cấu hình service chứ không chỉ kiểm tra ở host.

### Bước 4: kiểm tra việc đăng ký configuration properties

Nếu quên `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế đăng ký phù hợp, configuration properties bean có thể chưa tồn tại.

### Bước 5: kiểm tra nguồn khác ưu tiên cao hơn

Một command-line argument hoặc cấu hình đặc biệt có thể đang ghi đè giá trị environment. Cần xác định **giá trị có hiệu lực** và nguồn nào cung cấp nó.

### Bước 6: kiểm tra lỗi chuyển đổi và validation

Biến có thể được đọc nhưng giá trị không chuyển sang `Duration` hoặc kiểu Java mong muốn. Khi đó nên xem stack trace và thông báo binding/validation của Spring Boot.

### Bước 7: kiểm tra thời điểm lấy giá trị

Nếu một phần code chỉ đọc cấu hình khi startup, thay biến môi trường sau khi ứng dụng đã chạy không có nghĩa trường Java sẽ được tự cập nhật. Một số hệ thống có cơ chế refresh riêng, nhưng đó không phải là hành vi tự động chung của mọi configuration properties bean.

## 20. Quan sát cấu hình một cách an toàn

Trong môi trường phát triển, Spring Boot Actuator có các endpoint hỗ trợ xem thông tin cấu hình và property binding, ví dụ `/actuator/env` và `/actuator/configprops` nếu dự án có starter Actuator và endpoint được cấu hình cho phép truy cập.

Các endpoint này hữu ích khi xác định:

- Property name có được nhận diện không.
- Cấu hình cuối cùng đến từ nguồn nào.
- Configuration properties bean đã được bind theo nhóm nào.
- Có cấu hình bị ghi đè ngoài dự kiến không.

Tuy nhiên, **đây là dữ liệu vận hành có thể nhạy cảm**. Không nên công khai những endpoint này ra Internet chỉ để debug; Spring Boot có cơ chế che giá trị nhạy cảm, nhưng vẫn cần phân quyền, giới hạn truy cập và cấu hình hiển thị phù hợp.

Các nguyên tắc an toàn:

- Tránh ghi toàn bộ `Environment` vào log.
- Không in password, token, connection string chứa credential.
- Khi cần giải thích một giá trị được bind, ưu tiên hiển thị tên thuộc tính, loại nguồn và những trường an toàn.
- Dùng cấu hình tách theo môi trường và hệ thống quản lý secret cho production.

## 21. Các lỗi và hiểu lầm thường gặp

| Nhầm lẫn | Vì sao không đúng? | Cách tiếp cận |
|---|---|---|
| “Dấu gạch ngang chuyển thành dấu gạch dưới” | Quy tắc env canonical **xóa** dấu gạch ngang | Từ `retry-interval` tạo `RETRYINTERVAL` |
| “Mọi dấu underscore trong env đều vô hại” | Underscore có ý nghĩa phân tách namespace | Bắt đầu từ tên property canonical rồi chuyển đổi |
| “@Value tương đương hoàn toàn @ConfigurationProperties” | Cơ chế placeholder và binder không có cùng khả năng | Dùng `@ConfigurationProperties` cho nhóm cấu hình |
| “Property tồn tại trong file thì chắc chắn được dùng” | Nguồn ưu tiên cao hơn có thể ghi đè | Kiểm tra property sources và profile |
| “Đổi env khi app đang chạy sẽ tự cập nhật bean” | Thông thường binding xảy ra khi bean được tạo | Restart hoặc thiết kế cơ chế refresh riêng |
| “List từ YAML và env luôn được ghép từng mục” | List có quy tắc ghi đè khác map | Kiểm tra nguồn thắng và khai báo đủ list cần dùng |
| “Relaxed binding tự chữa tên sai” | Binder không suy đoán namespace mới | So khớp prefix và tên trường chính xác |
| “Field Java phải viết kebab-case” | Java dùng camelCase; kebab-case là tên property canonical | Giữ Java idiomatic, property canonical thống nhất |
| “Map key đặc biệt luôn bảo toàn khi không có ngoặc” | Binder có thể chuẩn hóa hoặc loại ký tự | Dùng bracket notation và YAML quoting |
| “Cấu hình đúng tên thì chắc chắn chạy được” | Giá trị vẫn có thể không convert hoặc vi phạm validation | Kiểm tra conversion và ràng buộc |

## 22. Bài tập thực hành

### Bài tập 1: Chuyển tên property sang env

Không dùng công cụ sinh mã, hãy tự chuyển:

1. `server.port`
2. `app.payment.max-retries`
3. `feature.user-profile.show-avatar`
4. `spring.main.log-startup-info`

**Đáp án:**

~~~text
server.port                     -> SERVER_PORT
app.payment.max-retries         -> APP_PAYMENT_MAXRETRIES
feature.user-profile.show-avatar -> FEATURE_USERPROFILE_SHOWAVATAR
spring.main.log-startup-info    -> SPRING_MAIN_LOGSTARTUPINFO
~~~

Điểm kiểm tra: chỉ dấu chấm thành underscore; các dấu gạch ngang bị loại bỏ.

### Bài tập 2: Bind Duration và boolean

Tạo record:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        Duration pollInterval,
        boolean enabled
) {
}
~~~

Sau đó khai báo:

~~~properties
app.worker.poll-interval=1500ms
app.worker.enabled=true
~~~

Đăng ký configuration properties bean và truyền vào một service. Hãy thử ghi đè bằng:

~~~bash
export APP_WORKER_POLLINTERVAL=3s
export APP_WORKER_ENABLED=false
~~~

Quan sát giá trị bind của `pollInterval` và `enabled`. Không cần thay đổi code Java khi chuyển từ file cấu hình sang environment.

### Bài tập 3: Kiểm tra thứ tự ưu tiên

Giữ trong file:

~~~properties
app.worker.enabled=true
~~~

Đặt trong environment:

~~~bash
export APP_WORKER_ENABLED=false
~~~

Và chạy:

~~~bash
java -jar app.jar --app.worker.enabled=true
~~~

Dự đoán kết quả và giải thích tại sao. Với cấu hình nguồn mặc định thông thường, command-line argument có độ ưu tiên cao hơn env và file.

### Bài tập 4: Phát hiện lỗi cấu hình

Một đồng nghiệp khai báo:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(int maxFileSize) {
}
~~~

Rồi đặt:

~~~bash
export APP_REPORT_MAX_FILE_SIZE=10
~~~

Hãy:

1. Viết tên property canonical cho trường `maxFileSize`.
2. Chuyển theo đúng quy tắc env.
3. Giải thích vì sao tên env đồng nghiệp đang dùng không phải dạng chuyển chuẩn.
4. Thêm validation phù hợp nếu kích thước tối đa phải lớn hơn 0.

**Gợi ý:** property canonical là `app.report.max-file-size`, tên env theo quy tắc chuẩn là `APP_REPORT_MAXFILESIZE`.

### Bài tập 5: Danh sách endpoint

Viết cấu hình YAML:

~~~yaml
app:
  destinations:
    - name: primary
      url: https://primary.example.org
    - name: secondary
      url: https://secondary.example.org
~~~

Tạo `@ConfigurationProperties(prefix = "app")` với `List<Destination> destinations`. Sau đó xác định tên env cho `app.destinations[0].url` và `app.destinations[1].name`.

**Đáp án:**

~~~text
APP_DESTINATIONS_0_URL
APP_DESTINATIONS_1_NAME
~~~

Hãy thử ghi đè danh sách từ env và quan sát quy tắc thay thế giữa các property sources, thay vì mặc định rằng Spring Boot luôn merge từng phần tử.

## 23. Nguyên tắc áp dụng trong dự án thực tế

Một dự án Spring Boot có nhiều môi trường thường dễ bảo trì hơn khi thống nhất những quy tắc sau:

1. **Đặt property canonical bằng lowercase kebab-case**, có prefix thuộc namespace của ứng dụng, chẳng hạn `app.mail` hoặc `integration.inventory`.
2. **Dùng `@ConfigurationProperties` cho một nhóm thuộc tính liên quan**, nhất là khi cần cấu trúc lồng nhau, conversion và validation.
3. **Từ canonical name suy ra tên environment theo quy tắc chính thức**: dấu chấm → underscore, dấu gạch ngang → bỏ, chữ hoa.
4. **Không viết code đọc trực tiếp `System.getenv(...)` cho mỗi cấu hình**, trừ khi có lý do đặc thù; ưu tiên để Spring Boot kết hợp các nguồn.
5. **Không nhầm tên với precedence**: nhiều nguồn có thể cung cấp cùng thuộc tính, và giá trị có hiệu lực phụ thuộc thứ tự nguồn.
6. **Cẩn trọng với list và map**: index, key có ký tự đặc biệt và quy tắc merge có những điểm riêng.
7. **Validation các cấu hình thiết yếu**, để thiếu hoặc sai dữ liệu được phát hiện càng sớm càng tốt.
8. **Hạn chế phơi bày cấu hình trong log và Actuator**, nhất là secret.
9. **Ghi lại tên property canonical trong tài liệu triển khai**, kèm tên env tương ứng, để đội phát triển và vận hành không phải tự suy đoán.

Một bảng tài liệu triển khai tối thiểu có thể là:

| Property | Environment variable | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `app.notification.sender-address` | `APP_NOTIFICATION_SENDERADDRESS` | `noreply@example.org` | Địa chỉ gửi |
| `app.notification.retry-interval` | `APP_NOTIFICATION_RETRYINTERVAL` | `10s` | Thời gian chờ thử lại |
| `app.notification.max-attempts` | `APP_NOTIFICATION_MAXATTEMPTS` | `3` | Số lần thử tối đa |
| `app.notification.enabled` | `APP_NOTIFICATION_ENABLED` | `true` | Bật/tắt chức năng |

Những bảng như vậy rất hữu ích trong Docker Compose, Kubernetes manifests, Helm values, pipeline CI/CD và tài liệu onboarding dự án.

## Kết luận

**Relaxed binding** giúp Spring Boot ánh xạ nhiều biến thể tên thuộc tính hợp lệ về cùng một trường Java, đặc biệt khi sử dụng `@ConfigurationProperties`. Nhờ đó, code có thể giữ tên camelCase tự nhiên, còn file cấu hình dùng tên canonical kebab-case.

Đối với biến môi trường, quy tắc quan trọng nhất là: **thay dấu chấm bằng underscore, xóa dấu gạch ngang và chuyển thành chữ hoa**. Ví dụ `app.mail.sender-address` trở thành `APP_MAIL_SENDERADDRESS`, không phải tự động `APP_MAIL_SENDER_ADDRESS`.

Hãy phân biệt cơ chế **nhận diện tên** với **thứ tự ưu tiên của nguồn cấu hình** và **chuyển đổi kiểu dữ liệu**. Khi kết hợp tên property nhất quán, `@ConfigurationProperties`, validation và cách kiểm tra nguồn cấu hình an toàn, ứng dụng Spring Boot có thể dùng cùng một artifact ở nhiều môi trường mà vẫn dễ hiểu, dễ triển khai và dễ điều tra sự cố.
