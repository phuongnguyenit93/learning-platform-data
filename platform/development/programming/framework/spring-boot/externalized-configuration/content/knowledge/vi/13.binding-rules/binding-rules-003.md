# Phân biệt quy tắc prefix với quy tắc tên thuộc tính thành viên trong Spring Boot

## 1. Vì sao cần phân biệt hai quy tắc?

Khi sử dụng `@ConfigurationProperties`, chúng ta thường thấy một annotation chứa `prefix` và một class có nhiều field hoặc record component. Hai loại tên này liên quan nhau nhưng không tuân theo cùng một mức độ linh hoạt.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store.order-processing")
public record OrderProperties(
        int batchSize,
        String defaultCurrency,
        boolean auditEnabled) {
}
~~~

Tệp `application.yaml`:

~~~yaml
store:
  order-processing:
    batch-size: 100
    default-currency: VND
    audit-enabled: true
~~~

Ở đây có ba tầng tên:

1. **Prefix trong annotation:** `store.order-processing` xác định nhóm khóa cần đọc.
2. **Tên thành viên Java:** `batchSize`, `defaultCurrency`, `auditEnabled` tuân theo quy tắc đặt tên của Java.
3. **Tên khóa từ nguồn cấu hình:** `batch-size`, `default-currency`, `audit-enabled` biểu diễn thành viên tương ứng trong YAML.

Spring Boot có cơ chế **relaxed binding** giúp kết nối các cách viết khác nhau của tên khóa nguồn với thành viên Java. Nhưng giá trị `prefix` trong annotation **phải viết theo dạng canonical, lowercase kebab-case**.

Hình dung:

~~~text
@ConfigurationProperties(prefix = "store.order-processing")
                                  |____________________|
                                         PREFIX

application.yaml:
store:
  order-processing:
    batch-size: 100
    default-currency: VND

store.order-processing.batch-size
|____________________| |________|
        prefix           member name

Java:
int batchSize;
    |_______|
  Java member
~~~

Điểm cốt lõi: **relaxed binding cho tên thuộc tính không có nghĩa mọi kiểu chữ đều hợp lệ ở chỗ khai báo prefix**.

## 2. Prefix là namespace của một nhóm cấu hình

Một prefix xác định phần đầu chung của các khóa được liên kết vào một bean.

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        String apiUrl,
        int connectionTimeout) {
}
~~~

Các tên cấu hình dạng chuẩn:

~~~properties
payment.gateway.api-url=https://gateway.example.test
payment.gateway.connection-timeout=5
~~~

Cách phân tích:

~~~text
payment.gateway.api-url
|_____________| |_____|
     prefix      member

payment.gateway.connection-timeout
|_____________| |________________|
     prefix            member
~~~

Prefix không phải tên class, tên package, tên bean, hay tên một field. Nó là một **không gian tên logic** dùng để tổ chức dữ liệu trong `Environment`.

Ví dụ, hai nhóm có thể cùng có thành viên `timeout` nhưng không xung đột:

~~~properties
payment.gateway.timeout=10s
notification.email.timeout=3s
~~~

~~~java
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(Duration timeout) {
}

@ConfigurationProperties(prefix = "notification.email")
public record EmailProperties(Duration timeout) {
}
~~~

Đây là hai nhóm cấu hình khác nhau dù cùng có record component tên `timeout`.

### Prefix và tên bean không giống nhau

Khi `@ConfigurationProperties` được đăng ký thông qua quét cấu hình hoặc `@EnableConfigurationProperties`, Spring Boot có một quy ước tên bean kết hợp prefix và tên class đầy đủ. Nhưng **tên bean** thuộc cơ chế `ApplicationContext`, còn **prefix** chỉ xác định đường dẫn thuộc tính cho Binder.

Một prefix như `payment.gateway` không buộc bạn đặt class tên `PaymentGateway` hay để nó ở package `payment.gateway`.

## 3. Quy tắc canonical cho prefix của @ConfigurationProperties

Tài liệu Spring Boot 3.3 yêu cầu giá trị prefix trong annotation viết bằng dạng **kebab-case chữ thường**, có thể gồm nhiều đoạn phân cấp bằng dấu chấm.

Các ví dụ hợp lệ:

~~~java
@ConfigurationProperties(prefix = "app")
@ConfigurationProperties(prefix = "app.mail")
@ConfigurationProperties(prefix = "my.main-project")
@ConfigurationProperties(prefix = "my.main-project.person")
@ConfigurationProperties(prefix = "service-client.http")
~~~

Các dạng cần tránh ở **vị trí annotation prefix**:

~~~java
// camelCase ở prefix, không phải dạng canonical
@ConfigurationProperties(prefix = "my.mainProject.person")

// Chữ hoa
@ConfigurationProperties(prefix = "My.MainProject.Person")

// Dấu gạch dưới trong một đoạn
@ConfigurationProperties(prefix = "my.main_project.person")

// Viết theo dạng tên biến môi trường
@ConfigurationProperties(prefix = "MY_MAINPROJECT_PERSON")
~~~

Ở nơi khai báo annotation, nên dùng:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

Không cần sửa nó thành camelCase chỉ vì Java record có field `firstName`.

### Những dấu phân cách mang ý nghĩa khác nhau

- Dấu chấm `.` phân chia các đoạn trong tên cấu hình: `my`, `main-project`, `person`.
- Dấu gạch ngang `-` phân chia các từ trong cùng một đoạn: `main-project`.
- Dấu gạch dưới `_` được dùng theo quy ước của một số **nguồn dữ liệu**, đặc biệt là biến môi trường, không phải cách thay thế tùy ý cho prefix annotation.

Chọn prefix theo **mô hình cấu hình** chứ không theo phong cách tên class Java.

## 4. Tên thành viên Java được relaxed binding ánh xạ như thế nào?

Xét JavaBean:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.main-project.person")
public class PersonProperties {

    private String firstName;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
~~~

Tên JavaBean property là `firstName`. Trong tệp `.properties`, các biểu diễn sau đều có thể liên kết đến thành viên đó:

~~~properties
my.main-project.person.first-name=Lan
~~~

~~~properties
my.main-project.person.firstName=Lan
~~~

~~~properties
my.main-project.person.first_name=Lan
~~~

Spring Boot gọi đây là relaxed binding: không yêu cầu tên trong tệp giống hệt tên Java property theo từng ký tự.

| Địa điểm | Ví dụ | Có ý nghĩa gì? |
| --- | --- | --- |
| Annotation `prefix` | `my.main-project.person` | Gốc nhóm; canonical bắt buộc. |
| Thành viên Java | `firstName` | Tên field/JavaBean/record component. |
| Properties hoặc YAML | `first-name` | Tên nguồn kebab-case được khuyến nghị. |
| Properties hoặc YAML | `firstName` | Biến thể camelCase được nhận. |
| Properties hoặc YAML | `first_name` | Biến thể gạch dưới được nhận. |
| Biến môi trường | `MY_MAINPROJECT_PERSON_FIRSTNAME` | Dạng hệ điều hành tương ứng. |

Quy tắc linh hoạt ở **nguồn** không thay đổi annotation:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

### Vì sao nên viết kebab-case trong tệp?

Tài liệu Spring Boot khuyến nghị kiểu chữ thường và gạch ngang:

~~~properties
my.main-project.person.first-name=Lan
~~~

Với cách viết nhất quán, người đọc dễ tìm khóa trong tài liệu, so sánh YAML với Properties và dựng tên biến môi trường. Relaxed binding là công cụ tương thích giữa các nguồn, không phải lời khuyên nên trộn mọi cách đặt tên vào cùng một dự án.

Không nên định nghĩa cả ba khóa sau với giá trị khác nhau trong cùng tệp:

~~~properties
my.main-project.person.first-name=Lan
my.main-project.person.firstName=Mai
my.main-project.person.first_name=Hoa
~~~

Dù các tên có thể cùng hướng tới một thành viên, việc cấu hình nhiều biến thể cạnh tranh gây khó hiểu và không nên là cách thiết kế độ ưu tiên.

## 5. Công thức ghép prefix với member path

Với một thuộc tính phẳng, có thể suy luận:

~~~text
Tên khóa đầy đủ = prefix + "." + tên thành viên theo dạng cấu hình
~~~

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record HttpProperties(
        String baseUrl,
        int maxConnections) {
}
~~~

Kết quả:

~~~text
client.http.base-url
client.http.max-connections
~~~

Sơ đồ:

~~~text
client.http.max-connections
|_________| |_____________|
   prefix     member name

Java member:
maxConnections
~~~

Không đặt thêm prefix vào tên Java component:

~~~java
// Dài không cần thiết
String clientHttpBaseUrl;
~~~

Mô hình gọn hơn:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record HttpProperties(String baseUrl) {
}
~~~

Bạn có thể sử dụng `properties.baseUrl()` trong Java; tên khóa vẫn là `client.http.base-url`.

### Nếu prefix không có giá trị

Một số cấu hình có thể khai báo `@ConfigurationProperties` không dùng prefix. Khi đó binder liên kết ở gốc không gian cấu hình tương ứng. Nhưng trong ứng dụng thực tế, đặt prefix rõ ràng thường giúp tránh xung đột và thuận tiện khi bổ sung cấu hình.

## 6. Ví dụ Spring Boot hoàn chỉnh: record + scan + service

### 6.1. Định nghĩa bean cấu hình

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store.order-processing")
public record OrderProperties(
        int batchSize,
        Duration requestTimeout,
        URI resultEndpoint) {
}
~~~

### 6.2. Nguồn YAML

~~~yaml
store:
  order-processing:
    batch-size: 200
    request-timeout: 15s
    result-endpoint: https://results.example.test
~~~

### 6.3. Đăng ký nhóm cấu hình

~~~java
package com.example.demo;

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

Đặt `OrderProperties` bên dưới package được `@ConfigurationPropertiesScan` quét; hoặc đăng ký tường minh bằng `@EnableConfigurationProperties(OrderProperties.class)`.

### 6.4. Service nhận bean

~~~java
package com.example.demo.service;

import com.example.demo.config.OrderProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderProperties properties;

    public OrderService(OrderProperties properties) {
        this.properties = properties;
    }

    public String summary() {
        return "batch=" + properties.batchSize()
                + ", timeout=" + properties.requestTimeout()
                + ", endpoint=" + properties.resultEndpoint();
    }
}
~~~

Với nguồn trên, các giá trị liên kết là:

~~~text
batchSize = 200
requestTimeout = PT15S
resultEndpoint = https://results.example.test
~~~

Ba trách nhiệm tách biệt:

1. `@ConfigurationPropertiesScan` làm cho `OrderProperties` được đăng ký làm bean cấu hình.
2. Binder lấy dữ liệu theo **prefix** và ánh xạ các khóa con đến **member** rồi chuyển kiểu.
3. Spring dependency injection truyền bean cấu hình đã tạo vào `OrderService`.

Giữ ranh giới này giúp gỡ lỗi chính xác: thiếu bean là vấn đề đăng ký, sai giá trị là vấn đề tên khóa/nguồn/binding, service không nhận được bean có thể là vấn đề DI.

## 7. Biến môi trường: chuyển đổi từ tên canonical thế nào?

Biến môi trường OS thường dùng chữ hoa và dấu gạch dưới, không dùng dấu chấm và gạch ngang như tên Properties.

Để chuyển tên canonical sang tên biến môi trường, quy tắc Spring Boot là:

1. Thay dấu chấm `.` bằng gạch dưới `_`.
2. **Bỏ** dấu gạch ngang `-`, không đổi nó thành gạch dưới.
3. Chuyển thành chữ hoa.

Ví dụ:

~~~text
store.order-processing.batch-size
       |
       +-- dots -> underscores
       +-- dashes -> removed
       +-- uppercase
       v
STORE_ORDERPROCESSING_BATCHSIZE
~~~

Bảng quy đổi:

| Thuộc tính canonical | Biến môi trường |
| --- | --- |
| `app.retry-count` | `APP_RETRYCOUNT` |
| `my.main-project.person.first-name` | `MY_MAINPROJECT_PERSON_FIRSTNAME` |
| `store.order-processing.request-timeout` | `STORE_ORDERPROCESSING_REQUESTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `client.http.max-connections` | `CLIENT_HTTP_MAXCONNECTIONS` |

Điểm gây nhầm thường là:

~~~text
app.retry-count  -> APP_RETRYCOUNT
~~~

Không nên tự động suy ra:

~~~text
app.retry-count  -> APP_RETRY_COUNT
~~~

Trong quy tắc canonical được tài liệu hóa, ký tự `-` bị bỏ đi. Dấu `_` bổ sung có thể bị hiểu là ranh giới giữa hai đoạn tên và không luôn cho cùng kết quả binding.

### Ví dụ với biến môi trường và YAML

Tệp:

~~~yaml
store:
  order-processing:
    batch-size: 100
    request-timeout: 10s
~~~

Lệnh Unix:

~~~bash
STORE_ORDERPROCESSING_BATCHSIZE=500 \
STORE_ORDERPROCESSING_REQUESTTIMEOUT=30s \
java -jar app.jar
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè, binder dùng:

~~~text
batchSize = 500
requestTimeout = PT30S
~~~

Trong mã, prefix vẫn là:

~~~java
@ConfigurationProperties(prefix = "store.order-processing")
~~~

Không cần đổi prefix thành tên biến môi trường. Binder xử lý cách biểu diễn phù hợp với nguồn.

**Lưu ý:** `System.getenv("STORE_ORDERPROCESSING_BATCHSIZE")` là API đọc đúng tên biến môi trường literal của JVM. Nó không tự triển khai toàn bộ quy tắc relaxed binding của Spring Boot.

## 8. Dòng lệnh --key=value và thứ tự PropertySource

Spring Boot mặc định đưa các tùy chọn dòng lệnh bắt đầu bằng `--` vào `Environment`.

Ví dụ:

~~~bash
java -jar app.jar \
  --store.order-processing.batch-size=750 \
  --store.order-processing.request-timeout=45s
~~~

Nguồn command-line thường có độ ưu tiên cao hơn biến môi trường và Config Data trong một lần chạy thông thường. Vì vậy hai giá trị từ CLI có thể ghi đè YAML hoặc OS environment.

Điều này không thay đổi `prefix` hay tên thành viên Java. Nó chỉ thay đổi **giá trị đầu vào có hiệu lực** của khóa logic.

Ví dụ có cùng một thuộc tính trong nhiều nguồn:

~~~text
application.yaml:
  store.order-processing.batch-size = 100

OS environment:
  STORE_ORDERPROCESSING_BATCHSIZE = 500

CLI:
  --store.order-processing.batch-size=750
~~~

Trong trường hợp thông thường:

~~~text
OrderProperties.batchSize() = 750
~~~

Vì thế, khi thấy một bean nhận giá trị khác tệp, hãy kiểm tra thứ tự `PropertySource` trước khi kết luận binder ánh xạ sai.

## 9. Object lồng nhau: prefix chung, nhiều member path

Một namespace có thể chứa cấu trúc sâu hơn.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        String senderName,
        Smtp smtp) {

    public record Smtp(
            String host,
            int port,
            Duration connectionTimeout) {
    }
}
~~~

YAML:

~~~yaml
app:
  messaging:
    sender-name: Operations
    smtp:
      host: smtp.example.test
      port: 2525
      connection-timeout: 5s
~~~

Các khóa:

~~~text
app.messaging.sender-name
app.messaging.smtp.host
app.messaging.smtp.port
app.messaging.smtp.connection-timeout
~~~

Phân biệt:

- Prefix là `app.messaging`.
- Thành viên trực tiếp là `senderName` và `smtp`.
- Thành viên của record lồng nhau `Smtp` gồm `host`, `port`, `connectionTimeout`.

Dấu `.` sau prefix có thể là ranh giới đi sâu vào **object thành viên**, không phải do annotation tự thay đổi.

### Thiết kế prefix sâu thay cho object lồng nhau

Một cách khác:

~~~java
@ConfigurationProperties(prefix = "app.messaging.smtp")
public record SmtpProperties(
        String host,
        int port,
        Duration connectionTimeout) {
}
~~~

Cùng nhóm khóa `app.messaging.smtp.*` có thể được biểu diễn bằng một bean riêng. Lựa chọn này tùy cấu trúc Java và cách tái sử dụng cấu hình.

Số cấp trong prefix **không bắt buộc** bằng số cấp object lồng nhau.

## 10. List và chỉ số: các thành phần của đường dẫn

Ví dụ:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Server> servers) {

    public record Server(
            String host,
            int maxConnections) {
    }
}
~~~

YAML:

~~~yaml
app:
  servers:
    - host: host-a.example.test
      max-connections: 10
    - host: host-b.example.test
      max-connections: 20
~~~

Các đường dẫn:

~~~text
app.servers[0].host
app.servers[0].max-connections
app.servers[1].host
app.servers[1].max-connections
~~~

Ở đây:

- `app` là prefix.
- `servers` là thành viên danh sách.
- `[0]` và `[1]` biểu thị phần tử.
- `max-connections` ánh xạ đến member `maxConnections` của `Server`.

### Dạng biến môi trường cho phần tử List

Theo quy tắc môi trường, chỉ số được bao quanh bằng dấu gạch dưới:

~~~text
app.servers[0].max-connections
      |
      v
APP_SERVERS_0_MAXCONNECTIONS
~~~

Trong thực tế, cấu hình danh sách từ nhiều nguồn có quy tắc ghi đè riêng; Spring Boot có thể thay thế cả danh sách theo nguồn ưu tiên hơn, không mặc nhiên ghép từng phần tử giữa các nguồn. Vì vậy đừng suy ra từ một chỉ số rằng list sẽ merge theo ý muốn.

## 11. Map: phân biệt Java member với key dữ liệu

Với Map, cần phân biệt ba thứ:

1. Prefix của properties bean.
2. Tên member Java chứa Map.
3. Key dữ liệu của từng entry.

Ví dụ:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service.gateway")
public record GatewayProperties(
        Map<String, String> routes) {
}
~~~

YAML:

~~~yaml
service:
  gateway:
    routes:
      north: https://north.example.test
      south: https://south.example.test
~~~

`routes` là member Java; `north` và `south` là **Map keys**, không phải field được khai báo trong class.

### Bracket notation cho key đặc biệt

Nếu key chứa dấu `/`, Spring Boot có cú pháp bracket để bảo toàn key:

~~~properties
service.gateway.routes[/admin]=https://admin.example.test
service.gateway.routes[/public]=https://public.example.test
~~~

Trong YAML, key có bracket phải được đặt trong dấu nháy:

~~~yaml
service:
  gateway:
    routes:
      "[/admin]": https://admin.example.test
      "[/public]": https://public.example.test
~~~

Nếu không có bracket, một số ký tự ngoài tập chữ/số, `-` hoặc `.` có thể bị loại khỏi key khi binding.

Với Map có key chứa dấu chấm, quy tắc còn phụ thuộc kiểu giá trị. Trong `Map<String, String>`, dấu chấm có thể được giữ với key scalar; còn trong `Map<String, Object>`, dấu chấm có thể tạo các cấp lồng nhau. Bracket notation giúp nêu rõ ý định bảo toàn key chính xác.

Đừng áp dụng quy tắc chuyển tên member như `first-name` → `firstName` một cách tùy tiện cho **Map key vốn là dữ liệu do người dùng đặt**.

## 12. Prefix trong annotation khác package scanning

Hai annotation có thể xuất hiện cạnh nhau:

~~~java
@ConfigurationPropertiesScan("com.example.config")
~~~

và:

~~~java
@ConfigurationProperties(prefix = "app.notifications")
~~~

Nhưng hai chuỗi phục vụ mục đích khác:

| Cơ chế | Đường dẫn | Ý nghĩa |
| --- | --- | --- |
| `@ConfigurationPropertiesScan` | `com.example.config` | Java package cần tìm các class properties. |
| `@ConfigurationProperties` | `app.notifications` | Namespace cấu hình trong `Environment`. |

Một class có thể ở package `com.example.config` nhưng dùng prefix `payment.gateway`. Và hai class ở hai package khác nhau có thể đọc các nhóm cấu hình liên quan nếu được đăng ký phù hợp.

Không đặt prefix theo package chỉ để “Spring tìm được class”. Đó là trách nhiệm của cơ chế đăng ký bean.

## 13. Prefix @ConfigurationProperties khác Environment prefix của SpringApplication

Spring Boot có thêm một khái niệm khác với tên gần giống:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setEnvironmentPrefix("input");
app.run(args);
~~~

`SpringApplication.setEnvironmentPrefix(...)` điều chỉnh cách ứng dụng đọc **biến môi trường hệ thống**. Ví dụ, khi environment prefix là `input`, một thuộc tính `remote.timeout` có thể được nạp từ biến `INPUT_REMOTE_TIMEOUT`.

Nó khác với:

~~~java
@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(Duration timeout) {
}
~~~

Ở đây `remote` là prefix xác định **nhóm khóa liên kết vào một object**.

| Loại prefix | Mục đích |
| --- | --- |
| `@ConfigurationProperties(prefix="remote")` | Chọn nhóm thuộc tính `remote.*` cho binder. |
| `SpringApplication.setEnvironmentPrefix("input")` | Thêm quy ước prefix cho biến môi trường hệ thống ứng dụng đọc. |

Environment prefix không có nghĩa mọi khóa trong `application.yaml` phải đổi thành `input.remote.timeout`. Tài liệu Spring Boot xác định cơ chế này áp dụng cho nguồn biến môi trường.

## 14. Prefix ở @Bean và setter binding

Không phải mọi class liên kết cấu hình đều dùng record. Với đối tượng mutable do factory tạo ra:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "client.http")
    ClientOptions clientOptions() {
        return new ClientOptions();
    }
}
~~~

Giả sử `ClientOptions` là JavaBean có:

~~~java
public void setBaseUrl(String baseUrl) { ... }
public void setReadTimeout(Duration readTimeout) { ... }
~~~

thì:

~~~properties
client.http.base-url=https://api.example.test
client.http.read-timeout=5s
~~~

được binder liên kết qua các property có thể ghi.

- `@Bean` chịu trách nhiệm tạo bean.
- `@ConfigurationProperties(prefix = "client.http")` chọn namespace.
- JavaBean property `baseUrl` và `readTimeout` là đích binding.
- Bean khác nhận `ClientOptions` qua dependency injection.

Tên phương thức factory `clientOptions` **không phải** prefix; nó liên quan đến tên bean theo cơ chế Spring.

### Constructor binding

Với record:

~~~java
@ConfigurationProperties(prefix = "client.http")
public record ClientProperties(
        String baseUrl,
        Duration readTimeout) {
}
~~~

khi đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Binder có thể dùng constructor chính của record để tạo object bất biến.

Trong cả setter binding và constructor binding, **quy tắc prefix và relaxed member names vẫn giữ nguyên**. Chỉ khác cách giá trị được chuyển vào object.

## 15. @Value và Environment không giống hoàn toàn với Binder

Spring Boot cũng cho phép đọc một khóa đơn bằng:

~~~java
@Value("${client.http.base-url}")
String baseUrl;
~~~

hoặc:

~~~java
String baseUrl = environment.getProperty(
        "client.http.base-url");
~~~

Những cơ chế này đọc qua hạ tầng `Environment` / property resolution. Còn `@ConfigurationProperties` dùng Binder để gắn các member Java theo cấu trúc object và relaxed binding.

Không nên mặc định mọi biến thể tên khóa hỗ trợ bởi Binder đều hoạt động giống hệt khi bạn trực tiếp dùng `Environment.getProperty(...)` hoặc placeholder `@Value` trong mọi tình huống.

Khi viết placeholder, Spring Boot khuyến nghị dùng tên canonical:

~~~java
@Value("${client.http.base-url}")
~~~

thay vì tùy ý thay bằng camelCase:

~~~java
@Value("${client.http.baseUrl}")
~~~

Đối với một nhóm có nhiều giá trị liên quan, `@ConfigurationProperties` thường rõ ràng hơn việc tiêm hàng loạt `@Value` ở mỗi service.

## 16. Các lỗi phổ biến: prefix hay member?

### Lỗi 1: prefix viết camelCase

~~~java
@ConfigurationProperties(prefix = "my.mainProject.person")
public record PersonProperties(String firstName) {
}
~~~

Prefix annotation không ở dạng canonical; sửa thành:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

Tên Java `firstName` không cần thay đổi.

### Lỗi 2: thiếu toàn bộ prefix trong tệp

Java:

~~~java
@ConfigurationProperties(prefix = "data.pipeline")
public record PipelineProperties(String inputDir) {
}
~~~

Nguồn:

~~~properties
input-dir=/tmp/data
~~~

Khóa này không nằm dưới namespace `data.pipeline`. Cần:

~~~properties
data.pipeline.input-dir=/tmp/data
~~~

### Lỗi 3: tên member bị gõ sai, không chỉ khác kiểu chữ

~~~properties
data.pipeline.input-dr=/tmp/data
~~~

`input-dr` không tự động tương đương `input-dir`. Relaxed binding xử lý biến thể đặt tên, **không phải bộ sửa lỗi chính tả**.

### Lỗi 4: nghĩ dấu gạch ngang thành gạch dưới ở biến môi trường

~~~text
Canonical: app.retry-count
Chuẩn:     APP_RETRYCOUNT
~~~

Không nên tùy tiện đặt `APP_RETRY_COUNT` rồi kỳ vọng luôn khớp cùng đường dẫn.

### Lỗi 5: cấu hình YAML đúng tên nhưng bean chưa đăng ký

Một class có `@ConfigurationProperties` không nhất thiết tự được Spring quản lý nếu chưa có `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc một cơ chế đăng ký phù hợp.

Đây là vấn đề **bean registration**, không phải quy tắc relaxed member naming.

### Lỗi 6: tên đúng nhưng kiểu dữ liệu sai

~~~properties
client.http.max-connections=not-a-number
~~~

Binder đã tìm đúng member `maxConnections` nhưng không thể chuyển thành `int`. Đây là lỗi **conversion/binding**, không phải lỗi prefix.

### Lỗi 7: nguồn khác ghi đè

~~~properties
client.http.max-connections=20
~~~

nhưng chạy với:

~~~bash
java -jar app.jar --client.http.max-connections=80
~~~

Bean nhận 80 theo độ ưu tiên dòng lệnh thông thường. Cần xem `PropertySource`, không đổi prefix.

### Lỗi 8: dùng tên Map key như Java field

Một key `/admin` trong Map không tương đương một Java field tên `admin`. Nếu key có ký tự đặc biệt, cần xem quy tắc Map binding và bracket notation.

### Lỗi 9: mặc định kiểu primitive che mất cấu hình thiếu

Nếu một record có `int maxRetries` nhưng khóa không tồn tại, không nên coi giá trị nguyên thủy mặc định là cấu hình hợp lệ. Khi dữ liệu quan trọng, cần validation hoặc mặc định có chủ đích.

### Lỗi 10: cho rằng sửa tệp runtime tự cập nhật bean

`@ConfigurationProperties` thường được bind trong quá trình khởi động. Sửa YAML trên đĩa không tự làm mới mọi bean đang tồn tại; cần cơ chế refresh riêng nếu ứng dụng yêu cầu.

## 17. Validation bổ trợ việc đặt tên như thế nào?

Để ràng buộc giá trị:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        @NotBlank String apiUrl,
        @Min(1) int maxRetries) {
}
~~~

Dữ liệu:

~~~properties
payment.gateway.api-url=https://gateway.example.test
payment.gateway.max-retries=3
~~~

Nếu có Bean Validation provider tương thích, Spring Boot có thể kiểm tra giá trị lúc binding:

- `apiUrl` không được rỗng.
- `maxRetries` phải ít nhất 1.

Validation **không sửa** prefix sai `payment.gateways` thành `payment.gateway` hoặc đoán `max-reties` là `max-retries`. Nó giúp phát hiện dữ liệu thiếu/sai ở bước sau khi binder tìm và gắn được thuộc tính theo cơ chế tương ứng.

## 18. Cách chẩn đoán theo thứ tự

Nếu `@ConfigurationProperties` không nhận giá trị như kỳ vọng, nên kiểm tra từng tầng:

**Bước 1 — Prefix annotation**

~~~java
@ConfigurationProperties(prefix = "client.http")
~~~

Xác minh dạng canonical, đúng chính tả, dấu chấm và gạch ngang.

**Bước 2 — Member Java**

~~~java
int maxConnections;
~~~

Với JavaBean, xem getter/setter. Với record, xem tên component và constructor binding.

**Bước 3 — Ghép khóa canonical**

~~~text
client.http.max-connections
~~~

Đây là tên nên ghi trong tệp và sử dụng làm tham số CLI.

**Bước 4 — Chuyển tên nếu là biến môi trường**

~~~text
CLIENT_HTTP_MAXCONNECTIONS
~~~

Áp dụng chính xác quy tắc dấu chấm/gạch ngang.

**Bước 5 — Kiểm tra nguồn có hiệu lực**

Ví dụ với giá trị không nhạy cảm:

~~~java
Integer max = environment.getProperty(
        "client.http.max-connections", Integer.class);
~~~

Nếu giá trị từ `Environment` đã khác tệp, cần điều tra nguồn và thứ tự ưu tiên.

**Bước 6 — Kiểm tra cơ chế bean/binding**

Bean có được đăng ký qua scan, enable hoặc factory không? Record có được tạo theo constructor binding phù hợp không? JavaBean có setter và cấu trúc dữ liệu có thể ghi không?

**Bước 7 — Chuyển kiểu và validation**

Nếu Binder tìm đúng đường dẫn nhưng không thể chuyển giá trị, cần sửa dữ liệu/kiểu đích. Nếu chuyển kiểu đúng nhưng giá trị vô lý, thêm constraint.

Trong log Spring Boot, có thể gặp lỗi thiếu bean, lỗi bind hoặc lỗi validation. Đừng kết luận mọi lỗi đều do `prefix`.

## 19. Bài thực hành

### Bài 1 — xác định các phần trong tên

Class:

~~~java
@ConfigurationProperties(prefix = "shop.checkout")
public record CheckoutProperties(
        int maxItems,
        String defaultLocale) {
}
~~~

Hãy viết hai khóa canonical.

**Đáp án:**

~~~properties
shop.checkout.max-items=20
shop.checkout.default-locale=vi-VN
~~~

Prefix = `shop.checkout`; các member = `maxItems`, `defaultLocale`.

### Bài 2 — chọn prefix hợp lệ

Lựa chọn:

A. `my.mainProject.person`

B. `my.main-project.person`

C. `MY_MAINPROJECT_PERSON`

D. `my.main_project.person`

**Đáp án: B**, vì đó là dạng canonical lowercase kebab-case cho annotation.

### Bài 3 — thư giãn tên member

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String senderAddress) {
}
~~~

Ba cách viết sau trong nguồn Properties:

~~~properties
app.mail.sender-address=team@example.test
app.mail.senderAddress=team@example.test
app.mail.sender_address=team@example.test
~~~

cùng có thể ánh xạ tới `senderAddress`. **Cách khuyến nghị** cho tệp là `sender-address`; không dùng đồng thời cả ba với các giá trị khác nhau.

### Bài 4 — biến môi trường

Chuyển ba khóa:

~~~text
app.retry-policy.max-attempts
payments.credit-card.provider-name
client.http.max-connections
~~~

**Đáp án:**

~~~text
APP_RETRYPOLICY_MAXATTEMPTS
PAYMENTS_CREDITCARD_PROVIDERNAME
CLIENT_HTTP_MAXCONNECTIONS
~~~

### Bài 5 — object lồng nhau

~~~java
@ConfigurationProperties(prefix = "app.pipeline")
public record PipelineProperties(Worker worker) {
    public record Worker(int maxParallelJobs) {
    }
}
~~~

**Hỏi:** khóa canonical của `maxParallelJobs`?

**Đáp án:** `app.pipeline.worker.max-parallel-jobs`. `app.pipeline` là prefix; `worker.max-parallel-jobs` là đường dẫn các member.

### Bài 6 — một tên member trong hai namespace

~~~java
@ConfigurationProperties(prefix = "http.client")
public record HttpProperties(int maxConnections) {
}

@ConfigurationProperties(prefix = "database.pool")
public record PoolProperties(int maxConnections) {
}
~~~

Dữ liệu:

~~~properties
http.client.max-connections=40
database.pool.max-connections=15
~~~

**Đáp án:** hai bean nhận các giá trị độc lập 40 và 15. Trùng tên Java member không gây xung đột vì prefix khác.

### Bài 7 — Map key đặc biệt

~~~java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(Map<String, String> routes) {
}
~~~

Hãy giữ nguyên key `/v1` trong YAML.

**Đáp án:**

~~~yaml
gateway:
  routes:
    "[/v1]": "https://api.example.test/v1"
~~~

### Bài 8 — phát hiện lỗi chính tả

~~~java
@ConfigurationProperties(prefix = "billing.invoice")
public record InvoiceProperties(int maxRetries) {
}
~~~

~~~properties
billing.invoice.max-retyries=10
~~~

**Đáp án:** `max-retyries` là lỗi chính tả; đúng là `billing.invoice.max-retries`. Relaxed binding không đoán một tên mới dựa vào lỗi đánh máy.

### Bài 9 — nguồn ưu tiên cao

~~~yaml
app:
  retry-policy:
    max-attempts: 2
~~~

Chạy:

~~~bash
java -jar app.jar --app.retry-policy.max-attempts=8
~~~

Với bean `@ConfigurationProperties(prefix = "app.retry-policy")` có `maxAttempts`, giá trị có hiệu lực thông thường là 8, không phải 2. Prefix và member name không đổi; nguồn giá trị mới ưu tiên cao hơn.

### Bài 10 — phân biệt quét bean và nhóm thuộc tính

~~~java
@ConfigurationPropertiesScan("com.example.config")
~~~

cùng:

~~~java
@ConfigurationProperties(prefix = "feature.delivery")
public record DeliveryProperties(String endpoint) {
}
~~~

**Đáp án:** `com.example.config` là **Java package được scan**, còn `feature.delivery` là **namespace cấu hình**. Một chuỗi không thay thế chuỗi kia.

## 20. Bảng ghi nhớ

| Nơi sử dụng | Quy tắc nên theo | Ví dụ |
| --- | --- | --- |
| `prefix` trong `@ConfigurationProperties` | **Bắt buộc** dạng canonical kebab-case chữ thường | `my.main-project.person` |
| Thành viên của record/JavaBean | Theo tên Java, thường camelCase | `firstName` |
| Khóa trong Properties/YAML | Nên dùng lowercase kebab-case | `my.main-project.person.first-name` |
| Biến môi trường | Dấu chấm thành `_`, bỏ `-`, viết hoa | `MY_MAINPROJECT_PERSON_FIRSTNAME` |
| CLI option | Dùng tên đầy đủ ở dạng canonical | `--my.main-project.person.first-name=Lan` |
| Object lồng nhau | Ghép đường dẫn member sau prefix | `app.messaging.smtp.connection-timeout` |
| Danh sách | Chỉ số giữa các đoạn member | `app.servers[0].host` |
| Map key đặc biệt | Bracket notation khi cần bảo toàn | `gateway.routes[/admin]` |
| Java package scan | `@ConfigurationPropertiesScan`, độc lập với prefix | `com.example.config` |
| Environment prefix của ứng dụng | Phục vụ tên biến môi trường OS | `input` |

## 21. Tổng kết

Khi dùng `@ConfigurationProperties`, hãy tách **hai nguyên tắc**:

- **Prefix là tên nhóm được khai báo trong annotation**. Nó phải ở dạng chuẩn lowercase kebab-case, ví dụ `my.main-project.person`.
- **Tên thành viên là đích ánh xạ của binder**. Java có thể dùng `firstName`, trong khi nguồn Properties/YAML khuyến nghị `first-name` và biến môi trường tương ứng dùng `FIRSTNAME` trong tên biến đầy đủ.

Ví dụ ngắn gọn:

~~~java
@ConfigurationProperties(prefix = "my.main-project.person")
public record PersonProperties(String firstName) {
}
~~~

~~~properties
my.main-project.person.first-name=Lan
~~~

~~~text
MY_MAINPROJECT_PERSON_FIRSTNAME=Lan
~~~

Đây là những cách biểu diễn tương thích của **một nhóm và một thành viên**, nhưng **không thay thế trực tiếp cho nhau ở mọi vị trí cú pháp**. Nếu bean nhận sai giá trị, hãy kiểm tra tuần tự prefix, đường dẫn member, cách viết của nguồn, thứ tự `PropertySource`, chuyển kiểu và validation. Cách làm này phân biệt chính xác lỗi namespace với lỗi liên kết thành viên.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — @ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
- [Spring Framework — Environment](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).