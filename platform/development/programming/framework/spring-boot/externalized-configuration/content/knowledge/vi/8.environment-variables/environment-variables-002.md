# Quy tắc dấu chấm, dấu gạch ngang và chữ hoa khi liên kết biến môi trường trong Spring Boot

## Mục tiêu

Spring Boot dùng cơ chế **externalized configuration** để ứng dụng nhận giá trị từ file cấu hình, biến môi trường, JVM system property, tham số dòng lệnh và nhiều nguồn khác. Trong Java, một thuộc tính thường có tên như **app.notification.retry-count**; trong môi trường hệ điều hành, người vận hành lại thường cấu hình biến như **APP_NOTIFICATION_RETRYCOUNT**. Chúng có thể liên kết với cùng một giá trị cấu hình nhờ cơ chế **relaxed binding**.

Vấn đề xuất hiện khi người dùng tự đổi dấu chấm và dấu gạch ngang thành dấu gạch dưới theo thói quen. Không phải mọi dấu gạch ngang đều chuyển thành một dấu gạch dưới. Một biến viết sai có thể vẫn tồn tại trong container, nhưng bean **@ConfigurationProperties** lại nhận giá trị mặc định hoặc báo thiếu cấu hình.

Bài học giải thích rõ:

- Quy tắc chuẩn để chuyển tên thuộc tính Spring Boot sang tên biến môi trường.
- Vì sao **dấu chấm**, **dấu gạch ngang** và **chữ hoa** được xử lý khác nhau.
- Cơ chế relaxed binding khi đi từ biến môi trường đến class Java.
- Sự khác nhau giữa **System.getenv**, **Environment** và **@ConfigurationProperties**.
- Cách viết biến cho thuộc tính lồng nhau, danh sách và một số cấu trúc map.
- Các tình huống lỗi trên Linux, Windows PowerShell, Docker và Kubernetes.
- Phương pháp kiểm chứng giá trị cấu hình thực sự được bind.

## 1. Từ tên thuộc tính đến tên biến môi trường

Trong Spring Boot, tên thuộc tính trong file cấu hình nên theo dạng **canonical kebab-case**: chữ thường, các cấp phân tách bằng dấu chấm và các từ trong một phần tên phân tách bằng dấu gạch ngang.

Ví dụ:

~~~properties
app.notification.retry-count=3
app.notification.send-timeout=5s
spring.main.log-startup-info=true
~~~

Trong YAML, các thuộc tính tương ứng có thể được trình bày như một cây:

~~~yaml
app:
  notification:
    retry-count: 3
    send-timeout: 5s
spring:
  main:
    log-startup-info: true
~~~

Spring Boot có thể liên kết chúng với các tên biến môi trường chuẩn:

~~~text
APP_NOTIFICATION_RETRYCOUNT
APP_NOTIFICATION_SENDTIMEOUT
SPRING_MAIN_LOGSTARTUPINFO
~~~

Điểm đáng nhớ nhất là sự khác biệt giữa hai loại dấu:

- **Dấu chấm (.)** phân tách các cấp của tên thuộc tính; khi chuyển sang tên biến môi trường, nó trở thành **dấu gạch dưới (_)**.
- **Dấu gạch ngang (-)** phân tách các từ trong một phần tên; khi chuyển sang tên biến môi trường theo quy tắc chuẩn, nó **bị bỏ đi**.
- **Chữ cái** được chuyển thành **chữ hoa**.

Vì vậy **app.notification.retry-count** trở thành **APP_NOTIFICATION_RETRYCOUNT**, chứ không phải công thức máy móc “thay tất cả dấu chấm và dấu gạch ngang bằng dấu gạch dưới”.

## 2. Ba bước chuyển đổi tên chuẩn

Theo quy tắc chuyển canonical property name sang environment variable name của Spring Boot:

1. Thay mọi dấu chấm **.** bằng dấu gạch dưới **_**.
2. Bỏ mọi dấu gạch ngang **-**.
3. Chuyển các chữ cái còn lại thành **chữ hoa**.

Áp dụng từng bước cho thuộc tính:

~~~text
app.mail.max-retries
         |
         | Bước 1: "." thành "_"
         v
app_mail_max-retries
         |
         | Bước 2: xóa "-"
         v
app_mail_maxretries
         |
         | Bước 3: chữ hoa
         v
APP_MAIL_MAXRETRIES
~~~

Bảng chuyển đổi:

| Thuộc tính canonical | Biến môi trường theo quy tắc chuẩn |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| app.mail.max-retries | APP_MAIL_MAXRETRIES |
| app.mail.connect-timeout | APP_MAIL_CONNECTTIMEOUT |
| app.payment.retry-delay | APP_PAYMENT_RETRYDELAY |
| app.cache.time-to-live | APP_CACHE_TIMETOLIVE |
| app.http.client.read-timeout | APP_HTTP_CLIENT_READTIMEOUT |
| app.service-name | APP_SERVICENAME |
| my.service[0].other | MY_SERVICE_0_OTHER |

Hai ví dụ giúp kiểm tra quy tắc:

**Ví dụ A — chỉ có dấu chấm:**

~~~text
spring.datasource.username
=> spring_datasource_username
=> SPRING_DATASOURCE_USERNAME
~~~

**Ví dụ B — vừa có dấu chấm vừa có dấu gạch ngang:**

~~~text
app.payment.max-retry-attempts
=> app_payment_maxretryattempts
=> APP_PAYMENT_MAXRETRYATTEMPTS
~~~

Trong ví dụ B, phần **max-retry-attempts** tạo thành **MAXRETRYATTEMPTS** khi áp dụng quy tắc chuẩn. Nếu tự chuyển thành **MAX_RETRY_ATTEMPTS**, đó là một cách viết khác và không nên coi là tên canonical đã được bảo đảm từ phép chuyển đổi trên.

## 3. Vì sao không thay cả dấu gạch ngang thành dấu gạch dưới?

Hãy xét thuộc tính:

~~~properties
app.client.read-timeout=10s
~~~

Tên biến môi trường được suy ra theo quy tắc chuẩn:

~~~bash
APP_CLIENT_READTIMEOUT=15s java -jar demo.jar
~~~

Một cách viết có vẻ tự nhiên là:

~~~text
APP_CLIENT_READ_TIMEOUT
~~~

Nhưng cách viết đó tạo thêm dấu gạch dưới giữa **READ** và **TIMEOUT**, trong khi ở tên canonical, dấu gạch ngang giữa hai từ đã bị loại bỏ. Spring Boot hỗ trợ nhiều dạng tên linh hoạt trong một số ngữ cảnh, nhưng khi cấu hình cho môi trường triển khai hoặc tài liệu vận hành, **hãy tạo tên bằng đúng ba bước chuẩn**, không phụ thuộc vào một biến thể có thể tình cờ hoạt động với cơ chế binding nào đó.

So sánh:

| Ý định | Tên nên dùng |
| --- | --- |
| Cấp con **client** trong **app**, thuộc tính **read-timeout** | APP_CLIENT_READTIMEOUT |
| Cấp con **client** có cấp con **read**, thuộc tính **timeout** | APP_CLIENT_READ_TIMEOUT |

Hai tên property sau có cấu trúc khác nhau:

~~~properties
app.client.read-timeout=10s
app.client.read.timeout=10s
~~~

Dấu chấm trong tên thứ hai tạo thêm một cấp. Khi đặt tên cho class cấu hình, cấu trúc nested và các trường Java, điều này có thể dẫn tới binding khác nhau.

**Quy ước dễ duy trì:** dùng dấu chấm cho đường dẫn các cấp cấu hình, dùng kebab-case cho tên thuộc tính trong từng cấp, rồi chuyển sang env var bằng ba bước chuẩn.

## 4. Relaxed binding hoạt động ở phía Spring như thế nào?

Spring Boot có cơ chế **relaxed binding**, giúp các dạng tên được sử dụng trong nguồn cấu hình khác nhau có thể liên kết với cùng một trường trong bean Java.

Ví dụ Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        int maxRetries,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

File application.yml:

~~~yaml
app:
  mail:
    max-retries: 3
    connect-timeout: 5s
    enabled: true
~~~

Khi ứng dụng đăng ký bean MailProperties, chẳng hạn qua **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(MailProperties.class)**, binder có thể liên kết:

~~~text
app.mail.max-retries     -> maxRetries
app.mail.connect-timeout -> connectTimeout
app.mail.enabled         -> enabled
~~~

Đặt biến môi trường:

~~~bash
APP_MAIL_MAXRETRIES=7 APP_MAIL_CONNECTTIMEOUT=12s APP_MAIL_ENABLED=false java -jar demo.jar
~~~

Trong tình huống thông thường, những giá trị từ biến môi trường có độ ưu tiên cao hơn file application.yml. Bean nhận:

~~~text
maxRetries   = 7
connectTimeout = PT12S (Duration 12 giây)
enabled      = false
~~~

Điều này bao gồm **hai bước** riêng:

1. Spring Boot xác định biến môi trường nào tương ứng với tên property trong cấu hình.
2. Binder chuyển giá trị chuỗi từ nguồn bên ngoài sang kiểu đích trong Java, ví dụ **int**, **Duration**, **boolean**.

Việc liên kết tên thành công không bảo đảm chuyển kiểu thành công. Nếu đặt **APP_MAIL_MAXRETRIES=abc**, binder không thể chuyển **abc** thành một số nguyên hợp lệ. Khi đó ứng dụng có thể lỗi trong giai đoạn bind cấu hình.

### 4.1. Đăng ký ConfigurationProperties

Một cách đăng ký trong ứng dụng Spring Boot:

~~~java
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

Đặt MailProperties dưới package được scan phù hợp. Khi đó có thể inject bean MailProperties vào service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class MailJob {
    private final MailProperties properties;

    public MailJob(MailProperties properties) {
        this.properties = properties;
    }

    public String description() {
        return "retry=" + properties.maxRetries()
            + ", timeout=" + properties.connectTimeout()
            + ", enabled=" + properties.enabled();
    }
}
~~~

Ví dụ này cho thấy ứng dụng không cần tự gọi System.getenv cho từng biến. Bean cấu hình tập trung phản ánh kết quả từ các PropertySource đã được Spring lựa chọn.

## 5. System.getenv, Environment và @ConfigurationProperties khác nhau

Ba API thường bị nhầm là tương đương:

~~~java
String osValue = System.getenv("APP_MAIL_MAXRETRIES");
String springValue = environment.getProperty("app.mail.max-retries");
MailProperties bound = mailProperties;
~~~

**System.getenv("APP_MAIL_MAXRETRIES")** đọc trực tiếp biến môi trường của tiến trình Java. Nó không nhìn thấy giá trị từ application.yml, JVM system property hay tham số dòng lệnh của Spring Boot.

**Environment.getProperty("app.mail.max-retries")** tra cứu qua Spring Environment và thứ tự các PropertySource. Cùng một khóa có thể đến từ file, biến môi trường hoặc các nguồn khác.

**@ConfigurationProperties** sử dụng binder để liên kết tên cấu hình vào đối tượng Java và chuyển đổi kiểu dữ liệu. Cơ chế relaxed binding được thiết kế rõ ràng cho đường đi này.

Ví dụ:

~~~yaml
# application.yml
app:
  mail:
    max-retries: 3
~~~

Lệnh chạy:

~~~bash
APP_MAIL_MAXRETRIES=7 java -Dapp.mail.max-retries=9 -jar demo.jar --app.mail.max-retries=11
~~~

Nếu không có nguồn ưu tiên cao hơn ngoài những nguồn trong ví dụ:

| Cách đọc | Kết quả |
| --- | --- |
| System.getenv("APP_MAIL_MAXRETRIES") | "7" |
| System.getProperty("app.mail.max-retries") | "9" |
| Environment.getProperty("app.mail.max-retries") | "11" |
| Bean MailProperties.maxRetries() | 11 |

Vì vậy khi chẩn đoán “đã đặt biến môi trường nhưng ứng dụng vẫn nhận số khác”, đừng chỉ in System.getenv. Spring Boot có thể đang sử dụng system property hoặc command-line property có ưu tiên cao hơn.

### 5.1. Tên chữ hoa không phải tên Java system property

Một JVM system property thường được truyền như sau:

~~~bash
java -Dapp.mail.max-retries=9 -jar demo.jar
~~~

Biến môi trường tương ứng thường được cung cấp như sau:

~~~bash
APP_MAIL_MAXRETRIES=7 java -jar demo.jar
~~~

Hai cơ chế này đều là nguồn của Spring Environment, nhưng chúng có cú pháp đặt tên và phương thức truy cập trực tiếp khác nhau. Không tự giả định **-DAPP_MAIL_MAXRETRIES=7** là cùng một thao tác với **APP_MAIL_MAXRETRIES=7**.

Một Java system property có thể được đọc bằng tên chính xác từ System.getProperty(...). Khi thiết kế cấu hình, giữ tên hệ thống JVM dạng property thông thường giúp giảm nhầm lẫn.

### 5.2. @Value dùng canonical name

Với placeholder của Spring:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class RetryCounter {
    @Value("${app.mail.max-retries:3}")
    private int maxRetries;
}
~~~

Dùng tên placeholder **canonical kebab-case** như **app.mail.max-retries** là lựa chọn nên ưu tiên để Spring Boot áp dụng khả năng tra cứu linh hoạt phù hợp. Nếu tự viết placeholder theo kiểu camelCase hoặc tên biến môi trường chữ hoa, có thể tạo ra cách phân giải khác với điều mong muốn ở một số nguồn.

Đối với nhóm cấu hình có nhiều trường, **@ConfigurationProperties** thường rõ ràng và dễ kiểm soát kiểu dữ liệu hơn việc rải nhiều @Value trong các class.

## 6. Cấp lồng nhau trong YAML và quy tắc dấu chấm

Cấu hình YAML:

~~~yaml
app:
  gateway:
    http:
      connect-timeout: 2s
      read-timeout: 10s
      max-connections: 50
~~~

Tương ứng với các đường dẫn property:

~~~properties
app.gateway.http.connect-timeout=2s
app.gateway.http.read-timeout=10s
app.gateway.http.max-connections=50
~~~

Tên biến môi trường chuẩn:

~~~text
APP_GATEWAY_HTTP_CONNECTTIMEOUT
APP_GATEWAY_HTTP_READTIMEOUT
APP_GATEWAY_HTTP_MAXCONNECTIONS
~~~

Để dễ hiểu, hãy tách **đường dẫn** và **tên trường**:

~~~text
app.gateway.http.read-timeout
    |       |         |
    |       |         +-- read-timeout: một tên trường gồm hai từ
    |       +------------ http: một cấp cấu hình
    +-------------------- gateway: một cấp cấu hình
~~~

Ở YAML, mức thụt lề quyết định cấp nào là con của cấp nào. Nếu viết:

~~~yaml
app:
  gateway:
    http:
      connect-timeout: 2s
    read-timeout: 10s
~~~

thì read-timeout đã chuyển thành **app.gateway.read-timeout**. Tên môi trường theo quy tắc chuẩn cũng đổi từ **APP_GATEWAY_HTTP_READTIMEOUT** thành **APP_GATEWAY_READTIMEOUT**.

Một biến môi trường đúng cú pháp vẫn có thể bị bỏ qua nếu nó đại diện cho **đường dẫn property khác** với đường dẫn bean đòi hỏi.

## 7. Chữ hoa và tính phân biệt chữ hoa/chữ thường

Trong tài liệu Spring Boot, cách chuyển tên property thành env var thường dùng **chữ hoa**. Đây là quy ước thân thiện với các hệ điều hành và nền tảng triển khai.

Ví dụ:

~~~text
app.feature.enabled   -> APP_FEATURE_ENABLED
app.feature.batch-size -> APP_FEATURE_BATCHSIZE
~~~

Với shell Unix/Linux, tên biến môi trường thường phân biệt chữ hoa và chữ thường ở cấp tiến trình. Chẳng hạn **APP_FEATURE_ENABLED** và **app_feature_enabled** có thể là hai biến riêng biệt nếu môi trường cho phép thiết lập cả hai. Trên Windows, quy tắc tên biến môi trường của hệ điều hành có khác biệt; đừng thiết kế hành vi ứng dụng dựa trên việc tồn tại hai biến chỉ khác chữ hoa/thường.

**Không nên** đặt đồng thời những biến chỉ khác hoa/thường để thử ép độ ưu tiên. Điều đó làm cấu hình phụ thuộc nền tảng và khó chẩn đoán. Chuẩn hóa một tên duy nhất dạng chữ hoa khi đưa vào container, script hoặc file triển khai.

Quy tắc chữ hoa cũng không đồng nghĩa class Java phải có trường viết hoa:

~~~java
public record FeatureProperties(boolean enabled, int batchSize) {}
~~~

Các trường Java vẫn theo camelCase thông thường; tên property canonical là **app.feature.batch-size** và tên biến môi trường chuẩn là **APP_FEATURE_BATCHSIZE**.

## 8. Khi hai tên cấu hình chuyển thành cùng một biến môi trường

Bước **xóa dấu gạch ngang** có hệ quả quan trọng: trong một số thiết kế tên, hai tên canonical khác nhau có thể chuyển thành cùng tên biến môi trường.

Ví dụ:

~~~text
app.http.max-retries -> APP_HTTP_MAXRETRIES
app.http.maxretries  -> APP_HTTP_MAXRETRIES
~~~

Ở góc độ người viết file .properties, **max-retries** và **maxretries** là hai chuỗi khác nhau. Nhưng khi biểu diễn bằng tên biến môi trường chuẩn, chúng va vào cùng một tên. Cơ chế relaxed binding cũng có thể coi những cách viết này tương đương trong ngữ cảnh bind.

Để tránh nhập nhằng:

- Đặt **mỗi thuộc tính một tên canonical ổn định**.
- Không đồng thời thiết kế hai thuộc tính chỉ khác vị trí dấu gạch ngang.
- Dùng cấu trúc cấp khác hoặc một tên rõ nghĩa hơn nếu hai giá trị mang ý nghĩa nghiệp vụ khác nhau.
- Ghi tài liệu tên biến môi trường chính xác, nhất là những cấu hình public cho người vận hành.

Ví dụ nếu thực sự cần hai loại retry:

~~~yaml
app:
  http:
    connect:
      retry-count: 2
    request:
      retry-count: 5
~~~

Chúng có tên môi trường riêng:

~~~text
APP_HTTP_CONNECT_RETRYCOUNT
APP_HTTP_REQUEST_RETRYCOUNT
~~~

Việc tách cấp cấu hình giúp tránh va chạm tên và mô tả rõ phạm vi của từng thông số.

## 9. Liên kết biến môi trường với danh sách

Một List trong @ConfigurationProperties cần quan tâm đến **chỉ số phần tử**, không chỉ tên trường.

Giả sử YAML:

~~~yaml
app:
  clients:
    - name: catalog
      base-url: https://catalog.example.test
      retries: 2
    - name: billing
      base-url: https://billing.example.test
      retries: 4
~~~

Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientsProperties(List<Client> clients) {
    public record Client(String name, String baseUrl, int retries) {}
}
~~~

Theo quy tắc chuẩn dành cho env var khi bind danh sách, **chỉ số được bao quanh bởi dấu gạch dưới**. Ví dụ các tên:

~~~text
APP_CLIENTS_0_NAME
APP_CLIENTS_0_BASEURL
APP_CLIENTS_0_RETRIES
APP_CLIENTS_1_NAME
APP_CLIENTS_1_BASEURL
APP_CLIENTS_1_RETRIES
~~~

Chỉ số **0** và **1** biểu diễn các phần tử khác nhau của danh sách. Đối với property như **app.clients[0].base-url**, phép chuyển tương ứng là:

~~~text
app.clients[0].base-url
=> app_clients_0_base-url
=> app_clients_0_baseurl
=> APP_CLIENTS_0_BASEURL
~~~

Trong ví dụ thực tế, nếu khai báo:

~~~bash
APP_CLIENTS_0_NAME=catalog APP_CLIENTS_0_BASEURL=https://catalog.example.test java -jar demo.jar
~~~

binder có thể liên kết thông tin của phần tử đầu tiên nếu cấu trúc bean và nguồn dữ liệu phù hợp.

### 9.1. Các lỗi thường gặp với chỉ số

Không viết:

~~~text
APP_CLIENTS_0_BASE_URL
~~~

rồi mặc định rằng nó chắc chắn là chuyển đổi canonical của **app.clients[0].base-url**. Theo quy tắc chuẩn, phần **base-url** trở thành **BASEURL**.

Không viết chỉ số dính liền với phần tên theo ý thích:

~~~text
APP_CLIENTS0_BASEURL
~~~

vì cơ chế chuyển chuẩn của danh sách yêu cầu chỉ số được biểu diễn rõ theo quy ước.

Nếu danh sách được khai báo từ nhiều PropertySource như application.yml và biến môi trường, quy tắc liên kết danh sách của Spring Boot có thể chọn danh sách từ nguồn ưu tiên cao thay vì tự động nối mọi phần tử. Khi muốn ghi đè một danh sách phức tạp, hãy kiểm tra dữ liệu cuối cùng binder nhận được và cung cấp đầy đủ phần tử cần thiết.

## 10. Liên kết với Map: không suy rộng máy móc

Ví dụ bean:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(Map<String, String> endpoints) {
}
~~~

Cấu hình:

~~~yaml
app:
  endpoints:
    asia: https://asia.example.test
    europe: https://europe.example.test
~~~

Với các key đơn giản, tên biến môi trường có thể được xây dựng theo tên property dạng đường dẫn:

~~~text
APP_ENDPOINTS_ASIA
APP_ENDPOINTS_EUROPE
~~~

Tuy nhiên, key của **Map** là dữ liệu, không phải lúc nào cũng là một phần tên Java canonical thông thường. Nếu key chứa dấu chấm, dấu gạch chéo, dấu ngoặc, chữ hoa có ý nghĩa hoặc ký tự khác, việc đổi toàn bộ thành chữ hoa và dấu gạch dưới có thể khiến key bị thay đổi hoặc tạo cấu trúc ngoài ý muốn.

Spring Boot có **bracket notation** trong một số nguồn file để bảo toàn các key Map có ký tự đặc biệt:

~~~yaml
app:
  headers:
    "[X-Trace-Id]": "example"
    "[/internal/path]": "enabled"
~~~

Trong trường hợp như vậy, dấu ngoặc vuông và dấu nháy là một phần cách biểu diễn key trong YAML; không có phép thay thế dấu chấm/dấu gạch ngang/chữ hoa đơn giản nào đảm bảo giữ nguyên mọi ký tự key khi dùng biến môi trường.

Đối với key Map đặc biệt, nên cân nhắc cấu hình bằng YAML, properties đúng cú pháp, config tree hoặc một dạng cấu trúc ít nhập nhằng hơn. Nếu bắt buộc dùng biến môi trường, hãy kiểm tra cách binder của phiên bản Spring Boot thực tế phân giải từng key.

### 10.1. Phân biệt Map với nested object

Giả sử có:

~~~yaml
app:
  regions:
    europe:
      endpoint: https://eu.example.test
~~~

Nếu Java dùng một nested record/class có trường **europe**, cấu trúc có thể khác với Java dùng **Map<String, Region>**. Cả hai có thể biểu diễn cùng đường dẫn property trên ví dụ đơn giản, nhưng cách xử lý key động, kiểu nested và dữ liệu không chuẩn có thể khác nhau.

Hãy xác định rõ kiểu đích trước khi tạo tên env var, nhất là với map có key lấy từ bên thứ ba.

## 11. Cách khai báo trên Linux và macOS

Trong Bash hoặc các shell tương thích, có thể truyền biến chỉ cho một lệnh:

~~~bash
APP_HTTP_CONNECTTIMEOUT=3s APP_HTTP_READTIMEOUT=20s java -jar demo.jar
~~~

Hai biến này tồn tại trong môi trường của tiến trình java được khởi chạy từ lệnh trên.

Có thể dùng **export** để các lệnh con chạy sau đó kế thừa biến:

~~~bash
export APP_HTTP_CONNECTTIMEOUT=3s
export APP_HTTP_READTIMEOUT=20s
java -jar demo.jar
~~~

Khi dùng export, cần lưu ý biến có thể còn tồn tại trong phiên shell. Nếu chạy lại ứng dụng với cấu hình khác, hãy kiểm tra những biến cũ đang được kế thừa:

~~~bash
printenv APP_HTTP_CONNECTTIMEOUT
printenv APP_HTTP_READTIMEOUT
~~~

Việc dùng **printenv** trong ví dụ chỉ phù hợp với giá trị không nhạy cảm như timeout. Không in password, token hoặc secret lên terminal/log để kiểm tra binding.

### 11.1. Có cần đặt dấu nháy quanh giá trị không?

Giá trị chứa dấu cách hoặc ký tự shell có ý nghĩa đặc biệt cần được quote theo quy tắc của shell. Ví dụ:

~~~bash
APP_LABEL='Order service - local' java -jar demo.jar
~~~

Tên biến **APP_LABEL** vẫn là một tên biến môi trường bình thường. Dấu nháy thuộc cú pháp shell để truyền giá trị có dấu cách, không phải một phần tên biến.

## 12. Cách khai báo trên Windows PowerShell

Trong PowerShell, dùng cú pháp **$env:**:

~~~powershell
$env:APP_HTTP_CONNECTTIMEOUT = "3s"
$env:APP_HTTP_READTIMEOUT = "20s"
java -jar demo.jar
~~~

Để kiểm tra tên biến:

~~~powershell
$env:APP_HTTP_READTIMEOUT
~~~

Cấu hình qua **$env:** áp dụng cho môi trường phiên PowerShell hiện tại và các tiến trình con tạo từ phiên đó theo hành vi của hệ điều hành. Nó không sửa application.yml và không phải là tùy chọn JVM.

Nếu muốn bỏ biến trong phiên shell rồi chạy lại, có thể dùng:

~~~powershell
Remove-Item Env:APP_HTTP_READTIMEOUT
java -jar demo.jar
~~~

Cần phân biệt tên biến môi trường với giá trị Spring Environment. Một biến bị xóa khỏi shell có thể khiến giá trị từ application.yml xuất hiện, nhưng nếu còn **-Dapp.http.read-timeout** hoặc **--app.http.read-timeout**, Spring có thể chọn những nguồn đó.

## 13. Docker và Kubernetes sử dụng đúng tên biến thế nào?

### 13.1. Docker

Giả sử image chạy Spring Boot JAR:

~~~bash
docker run --rm -e APP_HTTP_CONNECTTIMEOUT=3s -e APP_HTTP_READTIMEOUT=20s demo-image
~~~

Docker cấp tên và giá trị biến cho tiến trình trong container. Spring Boot đọc chúng qua PropertySource dành cho environment variables.

Nếu Docker image dùng một entrypoint script, cần bảo đảm script giữ hoặc chuyển tiếp environment của tiến trình đúng cách. Tên biến xuất hiện trong lệnh docker run không tự chứng minh nó đã tới tiến trình Java nếu launcher đã xử lý hoặc lọc môi trường.

### 13.2. Kubernetes

Đoạn cấu hình Pod:

~~~yaml
containers:
  - name: demo
    image: demo-image
    env:
      - name: APP_HTTP_CONNECTTIMEOUT
        value: "3s"
      - name: APP_HTTP_READTIMEOUT
        value: "20s"
~~~

Ở đây giá trị nằm trong trường **env** của container. Kubernetes không cần biết trường Java có tên **readTimeout** hay file application.yml dùng **read-timeout**; trách nhiệm chuyển tên và bind thuộc về Spring Boot.

Nếu dùng ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-runtime
data:
  APP_HTTP_CONNECTTIMEOUT: "3s"
  APP_HTTP_READTIMEOUT: "20s"
~~~

Sau đó tham chiếu ConfigMap vào env của container bằng cơ chế Kubernetes phù hợp. Một ConfigMap tồn tại trong cluster không tự động đưa dữ liệu vào một ứng dụng; phải có đường dẫn cấp dữ liệu cụ thể như **env**, **envFrom** hoặc volume mount.

Đối với thông tin nhạy cảm, dùng Secret và quản lý quyền truy cập thích hợp. Không đưa token thật vào README, lệnh kiểm thử hoặc ảnh chụp cấu hình.

### 13.3. Tên biến trong YAML triển khai không đổi quy tắc binding

Một lỗi dễ xảy ra:

~~~yaml
env:
  - name: APP_HTTP_READ_TIMEOUT
    value: "20s"
~~~

Trong khi key canonical là **app.http.read-timeout**. Người viết nhìn tên biến và nghĩ nó đúng vì ngăn cách từ bằng dấu gạch dưới. Cách an toàn là lấy key canonical rồi áp dụng ba bước, từ đó ra **APP_HTTP_READTIMEOUT**.

Khi đặt tên biến không chuẩn, ứng dụng có thể giữ giá trị trong file hoặc từ nguồn khác; việc Pod khởi động thành công không chứng minh cấu hình đã ghi đè.

## 14. Thứ tự ưu tiên khi biến môi trường và file cùng khai báo

Quy tắc đổi tên chỉ trả lời câu hỏi **“Tên biến nào tương ứng tên property nào?”**. Câu hỏi **“Giá trị nào được chọn?”** còn phụ thuộc thứ tự PropertySource.

Ví dụ:

~~~yaml
# application.yml
app:
  cache:
    time-to-live: 30s
~~~

Biến môi trường:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -jar demo.jar
~~~

Với hành vi nguồn chuẩn, **APP_CACHE_TIMETOLIVE** có thể override giá trị **30s** từ application.yml, và bean cấu hình nhận **45s**.

Thêm JVM system property:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -Dapp.cache.time-to-live=60s -jar demo.jar
~~~

Trong các nguồn đang so sánh, system property **60s** ưu tiên cao hơn biến môi trường **45s**.

Thêm tham số dòng lệnh:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -Dapp.cache.time-to-live=60s -jar demo.jar --app.cache.time-to-live=90s
~~~

Khi command-line properties được bật theo mặc định, Spring nhận **90s**.

Bảng tổng hợp:

| Nguồn | Tên/cú pháp | Giá trị |
| --- | --- | --- |
| application.yml | app.cache.time-to-live | 30s |
| Biến môi trường | APP_CACHE_TIMETOLIVE | 45s |
| JVM system property | -Dapp.cache.time-to-live | 60s |
| Command line của Spring Boot | --app.cache.time-to-live | **90s** |

Nếu đặt đúng tên biến môi trường mà thấy giá trị vẫn là 90s, vấn đề không nhất thiết nằm ở relaxed binding. Cần kiểm tra những nguồn có độ ưu tiên cao hơn.

Đây là thứ tự **giữa các nguồn đang xét**. Spring Boot còn có những PropertySource khác dành cho JSON, test, DevTools hoặc cấu hình bổ sung. Tránh dùng bảng này như danh sách tuyệt đối của tất cả nguồn có thể tồn tại.

## 15. Lỗi tên biến phổ biến và cách xử lý

### 15.1. Đổi cả dấu gạch ngang thành gạch dưới

Property:

~~~properties
app.mail.retry-count=5
~~~

Tên chuyển đổi chuẩn:

~~~text
APP_MAIL_RETRYCOUNT
~~~

Tên nhiều người đoán:

~~~text
APP_MAIL_RETRY_COUNT
~~~

**Cách xử lý:** xác định key canonical, chuyển dấu chấm thành gạch dưới, xóa dấu gạch ngang rồi viết hoa. Không tạo tên chỉ từ cách đọc bằng tiếng Anh của Java field.

### 15.2. Bỏ dấu gạch dưới của cấp lồng nhau

Property:

~~~text
app.mail.retry.count
~~~

Tên chuẩn:

~~~text
APP_MAIL_RETRY_COUNT
~~~

Nếu dùng **APP_MAIL_RETRYCOUNT**, tên này lại phù hợp hơn với key **app.mail.retry-count**. Một cấp cấu hình và một từ ghép trong field không thể luôn dùng thay cho nhau.

### 15.3. Chữ hoa/ thường không nhất quán

~~~text
app_mail_retrycount
App_Mail_RetryCount
APP_MAIL_RETRYCOUNT
~~~

Trong tài liệu triển khai nên chọn **APP_MAIL_RETRYCOUNT**. Không cài đặt cấu hình dựa trên việc hệ điều hành hoặc thư viện nhất định tự chuẩn hóa mọi trường hợp chữ hoa/thường theo một cách giống nhau.

### 15.4. Tên đúng nhưng chưa cấp vào tiến trình Java

Ví dụ một biến được thiết lập trong một cửa sổ terminal khác, nhưng ứng dụng chạy từ IDE hoặc một service riêng. Environment của tiến trình Java có thể không chứa biến đó.

**Cách xử lý:** kiểm tra cấu hình environment ở nơi thực sự khởi chạy JVM: Run Configuration của IDE, lệnh của shell, service manager, Docker entrypoint hoặc Pod specification.

### 15.5. Bị nguồn ưu tiên cao hơn ghi đè

Một biến môi trường đúng tên nhưng JVM có **-D** hoặc CLI có **--** cùng thuộc tính. Spring Environment có thể trả về giá trị của nguồn khác.

**Cách xử lý:** đọc Environment.getProperty(...) và các PropertySource tham gia, không chỉ System.getenv(...).

### 15.6. Lỗi chuyển kiểu dữ liệu

~~~text
APP_MAIL_MAXRETRIES=many
~~~

Nếu trường Java là **int maxRetries**, giá trị **many** không thể chuyển thành số nguyên. Lỗi này khác với việc không tìm thấy biến.

**Cách xử lý:** xem exception về binding/conversion, tên property và kiểu đích. Thử một số hợp lệ như **3** hoặc **7**.

### 15.7. Tên prefix của @ConfigurationProperties không khớp

Class:

~~~java
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(int retryCount) {}
~~~

Tên canonical là **app.email.retry-count**, nên tên môi trường chuẩn là **APP_EMAIL_RETRYCOUNT**. Nếu người vận hành đặt **APP_MAIL_RETRYCOUNT**, Spring không tự suy ra email và mail là từ đồng nghĩa.

### 15.8. Dùng @Value với tên không canonical

Ví dụ:

~~~java
@Value("${app.mail.maxRetries:3}")
private int retries;
~~~

Đặt tên placeholder theo kiểu camelCase có thể không được phân giải qua mọi nguồn giống với canonical **app.mail.max-retries**. Để rõ ràng, ưu tiên:

~~~java
@Value("${app.mail.max-retries:3}")
private int retries;
~~~

Đối với nhiều thuộc tính liên quan, gom thành một class **@ConfigurationProperties** sẽ giúp quản lý cấu trúc và kiểu dữ liệu tốt hơn.

### 15.9. Khóa xuất hiện hai lần do khác quy ước tên

Nếu cùng một nhóm cấu hình có cả **retry-count** và **retryCount**, binder có thể xem đó là những biến thể của cùng khái niệm. Khi chúng ở nhiều nguồn, kết quả phụ thuộc thứ tự ưu tiên; khi cùng một nguồn, có thể tạo ra nhập nhằng.

**Cách xử lý:** thống nhất tên file cấu hình ở kebab-case, đặt một khóa có nghĩa rõ ràng và tránh định nghĩa hai biến mang cùng mục đích dưới các biến thể khác nhau.

### 15.10. Không phân biệt chuỗi rỗng và biến không tồn tại

Một biến được cấp giá trị rỗng vẫn là một giá trị trong môi trường tiến trình. Khi bind, nó có thể gây lỗi chuyển đổi hoặc tạo kết quả khác với việc biến không được khai báo.

~~~bash
APP_MAIL_MAXRETRIES='' java -jar demo.jar
~~~

Đừng mặc định rỗng nghĩa là “bỏ qua để quay về file mặc định”. Tùy PropertySource, kiểu dữ liệu và binder, cần xác minh trường hợp cụ thể.

## 16. Kiểm tra tên biến và giá trị tại runtime

Một đoạn mã chẩn đoán có thể tập trung vào một thuộc tính không nhạy cảm:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigInspector implements ApplicationRunner {
    private final Environment environment;
    private final MailProperties properties;

    ConfigInspector(Environment environment, MailProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("OS env: "
            + System.getenv("APP_MAIL_MAXRETRIES"));
        System.out.println("Spring property: "
            + environment.getProperty("app.mail.max-retries"));
        System.out.println("Bound bean: "
            + properties.maxRetries());
    }
}
~~~

Khi chạy:

~~~bash
APP_MAIL_MAXRETRIES=7 java -jar demo.jar
~~~

trong điều kiện không có override ưu tiên cao hơn, kết quả kỳ vọng là:

~~~text
OS env: 7
Spring property: 7
Bound bean: 7
~~~

Nếu **OS env** là 7 nhưng **Spring property** và **Bound bean** không như mong đợi, tiếp tục kiểm tra nguồn ưu tiên cao hơn hoặc cách bind. Nếu **OS env** là null, biến chưa có trong môi trường của tiến trình dưới đúng tên được truy vấn.

### 16.1. Liệt kê tên PropertySource

Để biết Spring Environment đang xét những loại nguồn nào:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
class EnvironmentSources implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    EnvironmentSources(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Trong môi trường Spring Boot thông thường, danh sách có thể chứa nguồn biến môi trường hệ thống cùng các nguồn file config data và command-line arguments. Thứ tự trong Environment cho biết cách tra cứu thuộc tính được tổ chức ở runtime.

Chỉ in **tên** các nguồn trong ví dụ, không in toàn bộ nội dung vì biến môi trường và file cấu hình có thể chứa thông tin nhạy cảm.

### 16.2. Kiểm tra bean nhận đúng kiểu

Nếu bean nhận Duration:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(java.time.Duration readTimeout) {}
~~~

và biến:

~~~bash
APP_HTTP_READTIMEOUT=12s java -jar demo.jar
~~~

giá trị đọc được từ bean là đối tượng Duration biểu diễn 12 giây, thường được in thành **PT12S**. Điều này khác với chuỗi gốc **12s** nhưng không có nghĩa binding sai.

Đối với số nguyên, boolean, enum và collection, luôn so sánh cả **kiểu đích** thay vì chỉ đọc ký tự đầu vào.

### 16.3. Actuator và dữ liệu nhạy cảm

Nếu ứng dụng đã có Spring Boot Actuator và endpoint được cấu hình truy cập an toàn, các công cụ quan sát thông tin môi trường có thể giúp truy nguyên nguồn giá trị. Nhiều giá trị nhạy cảm sẽ bị che theo chính sách bảo mật.

Không mở công khai endpoint môi trường chỉ để xem biến tên gì; không in mật khẩu hoặc token vào console trong quá trình chẩn đoán. Chọn các property mô phỏng như timeout và retry-count để thử nghiệm.

## 17. Bài thực hành chuyển tên

### Bài 1 — Chuyển từ property sang env var

Hãy tự tính tên biến môi trường chuẩn của các property sau:

~~~text
1. server.port
2. spring.profiles.active
3. app.mail.retry-count
4. app.payment.request-timeout
5. app.metrics.export-enabled
6. app.gateway.client.max-open-connections
7. app.items[0].display-name
~~~

Đáp án:

~~~text
1. SERVER_PORT
2. SPRING_PROFILES_ACTIVE
3. APP_MAIL_RETRYCOUNT
4. APP_PAYMENT_REQUESTTIMEOUT
5. APP_METRICS_EXPORTENABLED
6. APP_GATEWAY_CLIENT_MAXOPENCONNECTIONS
7. APP_ITEMS_0_DISPLAYNAME
~~~

Ở bài 7, chỉ số list **[0]** được chuyển thành **_0_** theo quy tắc environment variable của danh sách.

### Bài 2 — Phân biệt hai key dễ nhầm

Hai thuộc tính:

~~~properties
app.http.max-connections=20
app.http.max.connections=20
~~~

Tên env chuẩn lần lượt là:

~~~text
APP_HTTP_MAXCONNECTIONS
APP_HTTP_MAX_CONNECTIONS
~~~

Hãy giải thích vì sao hai tên khác nhau. Đáp án: **max-connections** là một tên thuộc tính ghép từ hai từ; **max.connections** là hai cấp cấu hình.

### Bài 3 — Thử override file YAML

Tạo file:

~~~yaml
app:
  mail:
    max-retries: 2
    connect-timeout: 3s
~~~

Sau đó chạy:

~~~bash
APP_MAIL_MAXRETRIES=5 APP_MAIL_CONNECTTIMEOUT=8s java -jar demo.jar
~~~

Dùng bean MailProperties và Environment để quan sát hai giá trị. Trong tình huống nguồn chuẩn, các giá trị từ environment là **5** và **8s**; bean có thể nhận **5** và Duration 8 giây.

Thử thêm:

~~~bash
APP_MAIL_MAXRETRIES=5 java -Dapp.mail.max-retries=6 -jar demo.jar --app.mail.max-retries=7
~~~

Đọc System.getenv, System.getProperty và Environment.getProperty để thấy ba cơ chế có thể trả ra ba giá trị khác nhau trong cùng một tiến trình.

### Bài 4 — Tìm tên biến sai

Một file Deployment khai báo:

~~~yaml
env:
  - name: APP_PAYMENT_RETRY_DELAY
    value: "1s"
~~~

Trong khi bean chờ **app.payment.retry-delay**. Hãy nêu tên được chuyển theo quy tắc chuẩn và sửa cấu hình.

Đáp án:

~~~yaml
env:
  - name: APP_PAYMENT_RETRYDELAY
    value: "1s"
~~~

Lý do: dấu chấm giữa **app** và **payment** cùng dấu chấm trước **retry-delay** thành dấu gạch dưới; dấu gạch ngang giữa **retry** và **delay** bị bỏ.

### Bài 5 — Liên kết một danh sách

Với key:

~~~text
app.workers[0].max-tasks
app.workers[1].max-tasks
~~~

Tên env chuẩn:

~~~text
APP_WORKERS_0_MAXTASKS
APP_WORKERS_1_MAXTASKS
~~~

Thử tạo class chứa **List<Worker>**, cấp hai biến rồi quan sát số phần tử và giá trị của từng phần tử. Nếu một phần tử thiếu trường bắt buộc, xử lý tại validation hoặc cấu trúc cấu hình, không thay đổi tùy tiện quy tắc chuyển tên.

## 18. Quy ước đặt tên cho dự án

Khi thiết kế cấu hình dùng lâu dài, một quy ước nhất quán sẽ giúp file YAML, biến môi trường, class Java và tài liệu vận hành cùng mô tả một khóa.

| Tầng | Quy ước nên dùng | Ví dụ |
| --- | --- | --- |
| Property trong .properties | chữ thường, dấu chấm giữa cấp, kebab-case cho tên ghép | app.http.read-timeout |
| YAML | cây lồng nhau, tên khóa kebab-case | app → http → read-timeout |
| Biến môi trường | chữ hoa, dấu gạch dưới thay dấu chấm, bỏ dấu gạch ngang | APP_HTTP_READTIMEOUT |
| Class Java | tên class PascalCase, field camelCase | HttpProperties.readTimeout |
| JVM system property | tên property canonical | -Dapp.http.read-timeout=5s |
| Spring Boot CLI argument | tên property canonical | --app.http.read-timeout=5s |

Ví dụ hoàn chỉnh:

~~~yaml
# application.yml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
    java.time.Duration readTimeout,
    java.time.Duration connectTimeout,
    int maxConnections
) {}
~~~

~~~bash
APP_HTTP_READTIMEOUT=9s APP_HTTP_CONNECTTIMEOUT=4s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

Đây là một hợp đồng cấu hình rõ ràng: tên chính thức ở tầng Spring là **app.http.read-timeout**, còn tên dùng trong môi trường triển khai là **APP_HTTP_READTIMEOUT**.

### 18.1. Tài liệu hóa từ tên canonical, không từ Java field

Khi class có field **maxConnections**, đừng suy đoán tên biến bằng cách tự ngăn từng từ camelCase thành **MAX_CONNECTIONS**. Hãy bắt đầu từ property đầy đủ:

~~~text
app.http.max-connections
=> APP_HTTP_MAXCONNECTIONS
~~~

Cách này giúp tài liệu theo đúng quy tắc của Spring Boot, nhất là khi refactor tên class hoặc thêm cấp cấu hình.

### 18.2. Tên env không phải nơi thể hiện đơn vị

Ví dụ property có kiểu Duration nên chấp nhận giá trị như **5s**, **250ms** nếu binder hỗ trợ. Tên biến vẫn là **APP_HTTP_READTIMEOUT**; không cần tự gắn hậu tố **_SECONDS** trừ khi đây thực sự là một tên property khác do ứng dụng thiết kế.

Nếu muốn biểu diễn đơn vị ngay trong tên, hãy đặt tên property rõ nghĩa như **app.http.read-timeout-seconds**, rồi chuyển chuẩn thành **APP_HTTP_READTIMEOUTSECONDS**. Lúc đó bean cũng cần sử dụng kiểu và cách diễn giải tương ứng.

## 19. Quy trình tìm lỗi khi biến môi trường không được liên kết

Khi gặp tình huống “đã set env nhưng Spring không nhận”, thực hiện lần lượt:

1. **Đọc key canonical mà bean cần.** Xem prefix của @ConfigurationProperties và tên field Java; viết ra đường dẫn như **app.mail.max-retries**.
2. **Áp dụng ba bước chuyển đổi chuẩn.** Dấu chấm thành dấu gạch dưới, xóa dấu gạch ngang, chuyển chữ hoa.
3. **Kiểm tra môi trường của đúng tiến trình.** Biến có được truyền vào JVM đang chạy hay chỉ tồn tại trong terminal, Pod hoặc service khác?
4. **Kiểm tra file YAML/properties.** Có sai cấp, sai tên khóa hoặc một dạng viết khác của cùng thuộc tính không?
5. **Kiểm tra các nguồn ưu tiên hơn.** Có -D, -- hoặc PropertySource tùy chỉnh cùng khóa không?
6. **Đọc giá trị Spring Environment trả về.** Dùng tên canonical để giảm nhập nhằng.
7. **Kiểm tra lỗi bind/validation.** Nếu thấy giá trị ở Environment nhưng bean không khởi tạo, xem kiểu dữ liệu và điều kiện bắt buộc.
8. **Với List/Map, kiểm tra cấu trúc.** Chỉ số phần tử và key đặc biệt cần được xét riêng, không chỉ thay ký tự.
9. **Sau khi sửa, khởi động lại và quan sát.** Việc sửa biến trong shell sau khi JVM đã khởi động không tự cập nhật các bean đã được bind.

Một tên env chính xác giải quyết phần nhận diện property, nhưng cấu hình cuối cùng vẫn cần hợp lệ về giá trị và thứ tự nguồn.

## 20. Ghi nhớ

Quy tắc chuẩn của Spring Boot khi biến đổi **tên property canonical → tên environment variable** có ba thao tác: **dấu chấm thành dấu gạch dưới, dấu gạch ngang bị bỏ, chữ cái thành chữ hoa**.

~~~text
app.feature.max-retries  -> APP_FEATURE_MAXRETRIES
app.feature.max.retries  -> APP_FEATURE_MAX_RETRIES
~~~

Hai ví dụ trên thể hiện khác biệt quan trọng giữa **một trường có tên ghép** và **hai cấp thuộc tính**. Với danh sách, chỉ số được biểu diễn như **_0_**, **_1_** trong tên biến.

**@ConfigurationProperties** sử dụng relaxed binding và chuyển đổi kiểu; **System.getenv** chỉ đọc biến môi trường trực tiếp; **Environment** áp dụng cơ chế PropertySource của Spring. Tên đúng chưa bảo đảm giá trị thắng, vì biến môi trường có thể bị JVM system property, command-line argument hoặc nguồn ưu tiên cao hơn ghi đè.

Đối với cấu hình thật, hãy công bố một tên canonical, một tên env chính thức và một kiểu dữ liệu rõ ràng. Khi có sự cố, lần theo chuỗi **property canonical → env var → môi trường của tiến trình → Spring Environment → bean đích** để tìm đúng nguyên nhân.
