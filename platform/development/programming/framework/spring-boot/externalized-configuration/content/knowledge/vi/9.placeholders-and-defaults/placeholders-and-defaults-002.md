# Cung cấp giá trị dự phòng bằng `${key:default}` trong Spring Boot

## 1. Vấn đề: ứng dụng cần cấu hình nhưng một thuộc tính có thể chưa được cung cấp

Khi triển khai Spring Boot trên laptop, máy kiểm thử và production, cùng một thuộc tính có thể có hoặc không có giá trị tùy môi trường. Ví dụ, một dịch vụ cần cổng HTTP, số lần thử lại, thời gian chờ hoặc địa chỉ của một hệ thống bên ngoài:

- Trên máy lập trình viên, cổng mặc định `8080` và thời gian chờ `5s` thường đủ dùng.
- Trên production, hệ thống triển khai có thể cấp `SERVER_PORT` và một URL đích khác.
- Một tính năng không quan trọng có thể được tắt mặc định nếu chưa có biến môi trường.
- Ngược lại, mật khẩu cơ sở dữ liệu hoặc khóa ký bắt buộc không nên được thay bằng một giá trị giả chỉ để ứng dụng khởi động.

Spring hỗ trợ **property placeholder** để tham chiếu một thuộc tính từ môi trường cấu hình. Cú pháp `${key:default}` cho phép khai báo **giá trị dự phòng** nếu thuộc tính được tham chiếu không tồn tại hoặc không được giải quyết thành giá trị.

Ví dụ:

~~~properties
app.retry.max-attempts=${MAX_ATTEMPTS:3}
~~~

Khi không có cấu hình `MAX_ATTEMPTS`, giá trị của `app.retry.max-attempts` sau khi placeholder được giải quyết là `3`. Khi môi trường cấp `MAX_ATTEMPTS=7`, giá trị trở thành `7`.

Mục tiêu của bài là hiểu rõ **cú pháp, thời điểm sử dụng giá trị dự phòng, kiểu dữ liệu, cách kết hợp các nguồn cấu hình và giới hạn của default**. Chỉ một dấu hai chấm trong placeholder có thể thay đổi hành vi khởi động của cả ứng dụng.

## 2. Cấu trúc của một property placeholder

Một property placeholder có dạng:

~~~text
${key}
${key:default}
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `${` và `}` | Đánh dấu biểu thức property placeholder |
| `key` | Tên thuộc tính Spring cần tìm trong `Environment` hoặc các property source |
| `:` | Ký tự phân tách tên thuộc tính và giá trị mặc định |
| `default` | Giá trị được dùng khi không giải quyết được thuộc tính `key` |

Ví dụ:

~~~text
${server.port}                    → yêu cầu tra cứu server.port
${server.port:8080}               → dùng 8080 nếu server.port không có
${app.feature.enabled:false}     → mặc định false
${app.message:Hello}             → mặc định chuỗi Hello
${app.timeout:5s}                → mặc định chuỗi 5s, có thể chuyển thành Duration
${app.endpoint:http://localhost:8080} → mặc định một URL
~~~

Đây là cơ chế **property resolution**, không phải phép gán mặc định cho toàn bộ ứng dụng ở cấp hệ điều hành. Placeholder được giải quyết dựa trên những property source mà Spring biết tại thời điểm sử dụng.

Chú ý: `${...}` không phải **Spring Expression Language**. SpEL sử dụng cú pháp `#{...}`, thường để tính biểu thức. Hai cú pháp có thể xuất hiện trong cùng hệ sinh thái Spring nhưng có ý nghĩa khác nhau; không nên thay thế lẫn nhau.

## 3. Khi thuộc tính có và khi thuộc tính không có

Giả sử code:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RetryPolicy {
    private final int maxAttempts;

    public RetryPolicy(@Value("${app.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Trong file `application.yml` có:

~~~yaml
app:
  retry:
    max-attempts: 6
~~~

Tham chiếu `${app.retry.max-attempts:3}` lấy được giá trị `6`, vì khóa tồn tại. Nếu bỏ cấu hình `app.retry.max-attempts` ở mọi nguồn, placeholder sử dụng giá trị dự phòng `3`.

| Tình huống | Thuộc tính tìm được | Kết quả khi injection vào `int` |
| --- | --- | --- |
| `app.retry.max-attempts=6` | Có | `6` |
| `app.retry.max-attempts=0` | Có | `0` |
| Không có `app.retry.max-attempts` | Không | `3` |
| `app.retry.max-attempts=invalid` | Có, nhưng sai kiểu | Có thể lỗi chuyển kiểu; không tự lấy `3` |
| `app.retry.max-attempts=` (chuỗi rỗng) | Có giá trị rỗng | Không mặc nhiên lấy `3`; có thể lỗi chuyển sang `int` |

**Điểm mấu chốt:** default nhằm xử lý **thiếu thuộc tính**, không phải một hệ thống kiểm tra hợp lệ tự động. Giá trị `0`, `false` và chuỗi rỗng có thể là những giá trị được cấp thật, không đồng nghĩa với “không tìm thấy”.

## 4. Dùng placeholder trong `application.properties`

Trong file `src/main/resources/application.properties`:

~~~properties
server.port=${PORT:8080}
spring.application.name=${APP_NAME:catalog-service}

app.client.base-url=${CATALOG_API_URL:http://localhost:8081}
app.client.connect-timeout=${CONNECT_TIMEOUT:5s}
app.retry.max-attempts=${MAX_ATTEMPTS:3}
app.audit.enabled=${AUDIT_ENABLED:false}
~~~

Cách giải quyết khi chưa cấp biến môi trường nào:

~~~properties
server.port=8080
spring.application.name=catalog-service

app.client.base-url=http://localhost:8081
app.client.connect-timeout=5s
app.retry.max-attempts=3
app.audit.enabled=false
~~~

Nếu triển khai cung cấp:

~~~bash
export PORT=9090
export APP_NAME=catalog-production
export CATALOG_API_URL=https://catalog.example.org
export CONNECT_TIMEOUT=2s
export MAX_ATTEMPTS=5
export AUDIT_ENABLED=true
java -jar catalog-service.jar
~~~

thì những giá trị được tham chiếu trong tệp có thể nhận giá trị mới.

Một điểm cần phân biệt: trong ví dụ này `PORT` là tên thuộc tính/biến môi trường được **đặt bên trong placeholder**. Điều đó khác với cách Spring Boot ánh xạ trực tiếp biến `SERVER_PORT` sang thuộc tính `server.port` qua relaxed binding. Cả hai cách đều có thể hoạt động nhưng có quy tắc ưu tiên và nguồn giá trị cần xét rõ ràng.

## 5. Dùng placeholder trong YAML

YAML cho phép cấu hình phân cấp; property placeholder thường nằm tại giá trị cuối:

~~~yaml
server:
  port: "${PORT:8080}"

spring:
  application:
    name: "${APP_NAME:catalog-service}"

app:
  client:
    base-url: "${CATALOG_API_URL:http://localhost:8081}"
    connect-timeout: "${CONNECT_TIMEOUT:5s}"
  retry:
    max-attempts: "${MAX_ATTEMPTS:3}"
  audit:
    enabled: "${AUDIT_ENABLED:false}"
~~~

Spring Boot nạp file YAML thành các tên thuộc tính như `app.client.base-url` và `app.retry.max-attempts`. Khi những giá trị này được yêu cầu, placeholder có thể tham chiếu sang các nguồn cấu hình khác.

**Nên đặt chuỗi chứa placeholder trong dấu nháy YAML** nếu giá trị có ký tự đặc biệt, dấu hai chấm, hoặc cần tránh YAML parser diễn giải nhầm. Trong YAML, dấu nháy bao quanh giá trị không có nghĩa nó trở thành literal không được Spring giải quyết; nó chủ yếu điều khiển cách parser YAML đọc chuỗi.

Ví dụ URL:

~~~yaml
app:
  callback-url: "${CALLBACK_URL:http://localhost:8080/api/callback}"
~~~

Dấu hai chấm đầu tiên sau `CALLBACK_URL` là ký tự phân tách phần mặc định. Dấu hai chấm trong `http://` thuộc phần giá trị dự phòng.

## 6. Dùng `@Value` với giá trị mặc định

`@Value` phù hợp khi một bean cần vài giá trị đơn giản:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final String senderName;
    private final boolean enabled;
    private final int maxAttempts;

    public NotificationService(
            @Value("${app.notification.sender-name:system}") String senderName,
            @Value("${app.notification.enabled:false}") boolean enabled,
            @Value("${app.notification.max-attempts:3}") int maxAttempts) {
        this.senderName = senderName;
        this.enabled = enabled;
        this.maxAttempts = maxAttempts;
    }

    public String describe() {
        return senderName + ": enabled=" + enabled + ", maxAttempts=" + maxAttempts;
    }
}
~~~

Khi ứng dụng có:

~~~properties
app.notification.enabled=true
app.notification.max-attempts=8
~~~

thì `senderName` nhận `system`, `enabled` nhận `true` và `maxAttempts` nhận `8`.

Khuyến nghị sử dụng **tên thuộc tính canonical dạng lowercase kebab-case** trong placeholder, ví dụ `app.notification.sender-name`. Điều này hỗ trợ cách Spring Boot tra cứu tên thuộc tính nhất quán, kể cả khi giá trị được cấp qua biến môi trường.

### Khi dùng `@Value("${key}")` không có default

Ví dụ:

~~~java
public ConnectionInfo(@Value("${app.remote.url}") String url) {
    this.url = url;
}
~~~

Nếu Spring không giải quyết được `app.remote.url`, việc tạo bean có thể thất bại với lỗi placeholder chưa được giải quyết. Với một giá trị **bắt buộc**, đây có thể là hành vi mong muốn: ứng dụng phát hiện thiếu cấu hình ngay khi khởi động.

Nếu muốn giá trị thật sự tùy chọn, thêm một default có ý nghĩa:

~~~java
public ConnectionInfo(@Value("${app.remote.url:http://localhost:8080}") String url) {
    this.url = url;
}
~~~

Không nên thêm default giả như `changeme`, `password` hoặc URL production không an toàn chỉ để che lỗi thiếu cấu hình quan trọng.

## 7. Default có thể là chuỗi, số, boolean hoặc thời lượng

Giá trị sau dấu hai chấm về mặt cú pháp trước hết là **nội dung mặc định**; kiểu cuối cùng phụ thuộc nơi sử dụng hoặc kiểu đích khi binding.

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.time.Duration;

@Component
public class RuntimeOptions {
    private final String region;
    private final int workerCount;
    private final boolean metricsEnabled;
    private final Duration timeout;

    public RuntimeOptions(
            @Value("${app.region:local}") String region,
            @Value("${app.worker-count:4}") int workerCount,
            @Value("${app.metrics-enabled:false}") boolean metricsEnabled,
            @Value("${app.timeout:10s}") Duration timeout) {
        this.region = region;
        this.workerCount = workerCount;
        this.metricsEnabled = metricsEnabled;
        this.timeout = timeout;
    }
}
~~~

Các giá trị `4`, `false` và `10s` cần được chuyển sang các kiểu `int`, `boolean` và `Duration` tương ứng. Trong ứng dụng Spring Boot có conversion service phù hợp, cú pháp duration như `10s` được hỗ trợ; với cấu hình nhiều thuộc tính hoặc cần kiểm soát conversion/validation rõ ràng, nên ưu tiên `@ConfigurationProperties`.

Nếu một nguồn đặt `app.worker-count=hello`, default `4` **không tự thay thế giá trị sai**. Spring tìm thấy `hello` và có thể báo lỗi chuyển sang `int`.

## 8. Placeholder trong giá trị có tiền tố và hậu tố

Một placeholder không nhất thiết chiếm toàn bộ giá trị. Có thể ghép với văn bản cố định:

~~~yaml
app:
  storage:
    root: "/srv/${APP_NAME:catalog}/data"
  client:
    endpoint: "https://${API_HOST:localhost}:${API_PORT:8443}/v1"
  welcome:
    message: "Xin chào ${DISPLAY_NAME:khách}"
~~~

Nếu `APP_NAME=catalog-prod`, `API_HOST=api.example.org` và `API_PORT=443`, các giá trị sau khi giải quyết có dạng:

~~~text
/srv/catalog-prod/data
https://api.example.org:443/v1
Xin chào khách
~~~

Việc ghép chuỗi làm cho các trường hợp đơn giản trở nên gọn, nhưng đừng cố xây dựng URL phức tạp bằng nhiều placeholder nếu điều đó làm khó quan sát hoặc dễ quên escaping. Khi cấu hình thay đổi đáng kể theo môi trường, một thuộc tính `app.client.endpoint` hoàn chỉnh thường dễ kiểm soát hơn.

## 9. Default rỗng: `${key:}`

Có thể để trống phần sau dấu hai chấm:

~~~text
${key:}
~~~

Ví dụ:

~~~java
@Value("${app.optional-label:}")
private String optionalLabel;
~~~

Khi `app.optional-label` không có trong các nguồn cấu hình, placeholder giải quyết thành **chuỗi rỗng** (`""`).

Đối với một chuỗi thực sự tùy chọn, điều này có thể phù hợp. Nhưng với số, boolean, enum hoặc kiểu có quy tắc chuyển đổi chặt chẽ, chuỗi rỗng có thể tạo ra lỗi chuyển kiểu hoặc kết quả không mong muốn.

Không nên xem ba trường hợp sau là giống nhau:

| Trường hợp | Ý nghĩa |
| --- | --- |
| `${app.label:guest}` và không có khóa | Kết quả `guest` |
| `${app.label:}` và không có khóa | Kết quả chuỗi rỗng |
| `app.label=` đã được khai báo | Khóa tồn tại với giá trị rỗng; default `guest` không mặc nhiên được áp dụng |

Nếu nghiệp vụ muốn “dùng default khi chuỗi chỉ chứa khoảng trắng”, “dùng default khi số không dương” hoặc “dùng default khi value là null”, đó là **quy tắc nghiệp vụ/validation riêng**, không phải hành vi cơ bản của cú pháp placeholder.

## 10. Default lồng nhau: tìm nguồn thứ nhất rồi nguồn thứ hai

Giá trị mặc định có thể chứa **một placeholder khác**. Ví dụ:

~~~yaml
app:
  client:
    base-url: "${PRIMARY_API_URL:${SECONDARY_API_URL:http://localhost:8080}}"
~~~

Ý nghĩa:

1. Nếu `PRIMARY_API_URL` có giá trị, sử dụng nó.
2. Nếu không, thử `SECONDARY_API_URL`.
3. Nếu cả hai không có, sử dụng `http://localhost:8080`.

Có thể hình dung:

~~~text
PRIMARY_API_URL tồn tại?
  ├─ Có  → dùng PRIMARY_API_URL
  └─ Không
        SECONDARY_API_URL tồn tại?
          ├─ Có  → dùng SECONDARY_API_URL
          └─ Không → dùng http://localhost:8080
~~~

Trong `application.properties`:

~~~properties
app.client.base-url=${PRIMARY_API_URL:${SECONDARY_API_URL:http://localhost:8080}}
~~~

Nested placeholder hữu ích khi cần chuyển dần từ tên biến cũ sang tên mới hoặc cho phép nhiều cấp nguồn dự phòng.

Tuy nhiên, một chuỗi lồng nhau quá dài sẽ khó hiểu và dễ tạo vòng tham chiếu. Với chính sách cấu hình phức tạp, cân nhắc áp dụng logic rõ ràng trong code hoặc hệ thống quản lý cấu hình, và dùng validation để đảm bảo giá trị cuối hợp lệ.

## 11. Tham chiếu một thuộc tính Spring khác làm default

Không nhất thiết default phải là chuỗi cố định. Một thuộc tính có thể dùng thuộc tính khác làm dự phòng:

~~~yaml
app:
  http:
    default-timeout: 8s
  client:
    timeout: "${CLIENT_TIMEOUT:${app.http.default-timeout:5s}}"
~~~

Với ví dụ này:

- Nếu `CLIENT_TIMEOUT=3s`, giá trị client timeout là `3s`.
- Nếu không có `CLIENT_TIMEOUT` nhưng có `app.http.default-timeout=8s`, giá trị là `8s`.
- Nếu cả hai nguồn được tham chiếu đều không có, giá trị là `5s`.

Việc tham chiếu `app.http.default-timeout` thay vì hardcode `8s` nhiều lần giúp tránh cấu hình trùng lặp.

Lưu ý: mặc dù placeholder có thể tra cứu các khóa từ `Environment`, quá trình giải quyết vẫn phải tuân theo thứ tự ưu tiên của các property source. Việc file YAML đặt một khóa trước khóa kia không có nghĩa khóa trước “được giải quyết và khóa sau mới được phép tham chiếu”.

**Tránh vòng tham chiếu**, ví dụ:

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Khi các khóa này được giải quyết, vòng tham chiếu có thể gây lỗi thay vì tạo ra một giá trị hữu ích.

## 12. Kết hợp với profile: default và thứ tự ưu tiên là hai lớp khác nhau

Giả sử file chung trong JAR:

~~~yaml
# application.yml
app:
  client:
    timeout: "${CLIENT_TIMEOUT:5s}"
    base-url: "${CLIENT_URL:http://localhost:8080}"
~~~

Và file cho profile prod:

~~~yaml
# application-prod.yml
app:
  client:
    timeout: "${PROD_CLIENT_TIMEOUT:12s}"
    base-url: "${CLIENT_URL:https://api.example.org}"
~~~

Khi profile `prod` được kích hoạt, file profile có thể ghi đè các khóa từ file chung. Khi đó Spring giải quyết placeholder từ **giá trị cuối đã thắng cho khóa đang được dùng**, không phải ghép mặc định của hai file.

Ví dụ:

| Tình huống | Giá trị `app.client.timeout` |
| --- | --- |
| Không có profile prod; không có `CLIENT_TIMEOUT` | `5s` |
| Không có profile prod; `CLIENT_TIMEOUT=4s` | `4s` |
| Có profile prod; không có `PROD_CLIENT_TIMEOUT` | `12s` |
| Có profile prod; `PROD_CLIENT_TIMEOUT=20s` | `20s` |

Nếu một biến môi trường khác đặt trực tiếp tên thuộc tính `APP_CLIENT_TIMEOUT=30s`, nguồn môi trường có thể ghi đè cả giá trị từ file chung và file profile, vì biến môi trường thường ưu tiên cao hơn Config Data.

Đây là hai khái niệm cần phân biệt:

- **Property source precedence:** chọn nguồn chứa định nghĩa có hiệu lực cho `app.client.timeout`.
- **Placeholder default:** chỉ áp dụng khi placeholder bên trong định nghĩa được chọn không tìm được khóa được tham chiếu.

`${CLIENT_TIMEOUT:5s}` không phải lệnh “bất kể profile nào cũng đặt timeout 5 giây”.

## 13. Khi nào default bị bỏ qua vì nguồn ưu tiên cao hơn?

Giả sử trong `application.yml` có:

~~~yaml
server:
  port: "${PORT:8080}"
~~~

Khi hệ điều hành có `PORT=9090`, placeholder thường đưa tới cổng `9090`.

Nhưng nếu thêm:

~~~bash
java -jar app.jar --server.port=7070
~~~

thì đối số dòng lệnh `--server.port=7070` thường có ưu tiên cao hơn file Config Data. Giá trị hiệu lực của `server.port` là `7070`; ứng dụng không cần lấy `8080` hoặc `9090` từ giá trị placeholder trong file.

Nếu biến môi trường `SERVER_PORT=6060` được đặt, tên đó có thể trực tiếp ánh xạ tới `server.port`, trong khi `PORT` chỉ có tác dụng vì file đang tham chiếu `${PORT:8080}`.

Ví dụ so sánh:

~~~text
application.yml:
  server.port = ${PORT:8080}

Biến:
  PORT=9090
  SERVER_PORT=6060

Không có CLI override:
  server.port → 6060 (biến SERVER_PORT ghi đè thuộc tính trực tiếp)
~~~

Vì vậy, nếu default không có tác dụng, hãy kiểm tra **nguồn cấu hình đang thắng**, không chỉ kiểm tra placeholder có viết đúng hay không.

## 14. Placeholder không phải cách thay thế mọi cấu hình bắt buộc

Một số thuộc tính có thể có default an toàn:

| Thuộc tính | Default phù hợp trong nhiều ứng dụng | Điều kiện |
| --- | --- | --- |
| `server.port` | `8080` | Không có yêu cầu bắt buộc về cổng |
| `app.retry.max-attempts` | `3` | Có chính sách retry rõ ràng |
| `app.feature.enabled` | `false` | Tắt tính năng là trạng thái an toàn |
| `app.client.timeout` | `5s` | Được đánh giá phù hợp cho môi trường |
| `app.logging.sample-rate` | `0.1` | Có giới hạn tỷ lệ và hiểu ý nghĩa |

Ngược lại, những giá trị sau thường nên được yêu cầu rõ ràng thay vì có default giả:

- Mật khẩu cơ sở dữ liệu production.
- Khóa ký JWT, private key hoặc bí mật xác thực.
- URL hệ thống thanh toán thật khi không có chế độ sandbox rõ ràng.
- Tên bucket/tenant xác định ranh giới dữ liệu khách hàng.

Ví dụ cần fail fast khi thiếu:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentCredentials {
    private final String apiKey;

    public PaymentCredentials(@Value("${payment.api-key}") String apiKey) {
        this.apiKey = apiKey;
    }
}
~~~

Ở đây không khai báo default, để phát hiện cấu hình chưa được cấp khi bean được tạo. Với ứng dụng lớn, có thể dùng `@ConfigurationProperties` và Bean Validation để kiểm tra cả điều kiện bắt buộc, định dạng hoặc khoảng giá trị.

Không nên ghi mật khẩu/token thật trong ví dụ, file đã commit hoặc log chẩn đoán.

## 15. Phân biệt default trong placeholder và default của `@ConfigurationProperties`

Với một nhóm thuộc tính có kiểu rõ ràng, Spring Boot thường khuyến nghị sử dụng `@ConfigurationProperties` thay cho nhiều `@Value` riêng lẻ.

Ví dụ YAML dùng placeholder:

~~~yaml
app:
  worker:
    count: "${WORKER_COUNT:4}"
    timeout: "${WORKER_TIMEOUT:10s}"
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int count, Duration timeout) {}
~~~

Bật quét lớp cấu hình:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(WorkerApplication.class, args);
    }
}
~~~

Khi bind, bộ chuyển đổi kiểu có thể chuyển `4` thành `int` và `10s` thành `Duration`.

Nhưng có một **cơ chế mặc định riêng** của constructor binding trong Spring Boot: `@DefaultValue`. Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerPropertiesWithDefaults(
        @DefaultValue("4") int count,
        @DefaultValue("10s") Duration timeout
) {}
~~~

Ở đây, default thuộc **quy tắc bind thành record**; nó không đòi hỏi phải viết placeholder vào file YAML. Hai cách có thể cùng giải quyết nhu cầu mặc định nhưng khác trách nhiệm:

| Cách đặt mặc định | Vị trí | Khi nào phù hợp |
| --- | --- | --- |
| `${KEY:default}` trong YAML/properties | File cấu hình | Muốn tham chiếu nguồn khác và có giá trị dự phòng ở cấp property |
| `@Value("${key:default}")` | Điểm injection Java | Một vài thuộc tính đơn lẻ |
| `@DefaultValue` trong `@ConfigurationProperties` | Định nghĩa cấu hình có kiểu | Muốn default gắn với cấu trúc cấu hình/binding |

Không nên trộn nhiều cơ chế cho cùng thuộc tính một cách tùy tiện, vì việc xác định giá trị thực tế lúc triển khai sẽ khó hơn.

## 16. Khác biệt giữa default của placeholder và `Environment#getProperty`

`Environment` cũng có API lấy giá trị mặc định:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionResolver {
    private final Environment environment;

    public RegionResolver(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

`getProperty("app.region", "local")` trả `local` khi tra cứu `app.region` không có kết quả. Về mục tiêu sử dụng, nó gần với `${app.region:local}`.

Tuy nhiên, cần phân biệt:

- `${app.region:local}` là **cú pháp tham chiếu thuộc tính**, dùng trong string mà Spring giải quyết placeholder.
- `environment.getProperty("app.region", "local")` là **lệnh gọi API Java** của `Environment` với tham số mặc định.
- `@DefaultValue` là cách mô tả default trong **binding** của `@ConfigurationProperties`.

Ba cơ chế thuộc các lớp khác nhau. Dùng cơ chế phù hợp với nơi mà bạn muốn khai báo và kiểm soát giá trị mặc định.

## 17. Default có thể chứa dấu hai chấm, dấu cách hay dấu gạch chéo không?

Có. Giá trị dự phòng có thể là URL, đường dẫn hoặc đoạn văn bản:

~~~yaml
app:
  callback-url: "${CALLBACK_URL:http://localhost:8080/callback}"
  cache-dir: "${CACHE_DIR:/tmp/app-cache}"
  greeting: "${APP_GREETING:Xin chào người dùng}"
~~~

Dấu hai chấm sau tên khóa đánh dấu **bắt đầu default**; các dấu hai chấm khác nằm trong chuỗi mặc định có thể là một phần của giá trị.

Nhưng khi default có các ký tự như dấu ngoặc, chuỗi lồng nhau, ký tự escape hoặc các dấu phân cách do công cụ bên ngoài xử lý, phải phân biệt ba tầng cú pháp:

1. Cú pháp của file nguồn (YAML, properties hoặc Java string).
2. Cú pháp property placeholder của Spring.
3. Cú pháp của shell/Compose/Kubernetes nếu giá trị được đặt ở bên ngoài.

Ví dụ, YAML có dấu nháy không làm placeholder ngừng được Spring xử lý; ngược lại, file Docker Compose có cơ chế nội suy biến riêng với ký tự `$`. Nếu copy nguyên `${...}` vào một giá trị trong Compose, có thể cần escape theo quy tắc của Compose để tránh nội suy sớm. Đừng mặc định mọi công cụ diễn giải cùng một cú pháp.

Khi cần lưu **literal** văn bản `${some.key}` mà không cho Spring giải quyết, phải dùng cơ chế escape phù hợp với Spring Framework và định dạng file đang dùng; chỉ thêm dấu nháy YAML không đủ để thể hiện ý định “không xử lý placeholder”.

## 18. Kiểm tra hành vi bằng một ví dụ Spring Boot nhỏ

Tạo file `src/main/resources/application.yml`:

~~~yaml
app:
  profile-label: "${PROFILE_LABEL:local}"
  retries: "${APP_RETRIES:3}"
  display-url: "${APP_DISPLAY_URL:http://localhost:8080}"
~~~

Tạo một bean để quan sát ba giá trị sau khi Spring khởi động:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationPrinter implements CommandLineRunner {
    private final String label;
    private final int retries;
    private final String displayUrl;

    public ConfigurationPrinter(
            @Value("${app.profile-label}") String label,
            @Value("${app.retries}") int retries,
            @Value("${app.display-url}") String displayUrl) {
        this.label = label;
        this.retries = retries;
        this.displayUrl = displayUrl;
    }

    @Override
    public void run(String... args) {
        System.out.println("label = " + label);
        System.out.println("retries = " + retries);
        System.out.println("displayUrl = " + displayUrl);
    }
}
~~~

**Lần chạy 1 — không cấp biến:**

~~~bash
java -jar demo.jar
~~~

Kết quả kỳ vọng:

~~~text
label = local
retries = 3
displayUrl = http://localhost:8080
~~~

**Lần chạy 2 — cấp biến:**

~~~bash
export PROFILE_LABEL=production
export APP_RETRIES=6
export APP_DISPLAY_URL=https://example.org
java -jar demo.jar
~~~

Kết quả kỳ vọng:

~~~text
label = production
retries = 6
displayUrl = https://example.org
~~~

**Lần chạy 3 — ghi đè trực tiếp thuộc tính:**

~~~bash
java -jar demo.jar --app.retries=9
~~~

Nếu không có nguồn đặc biệt ưu tiên cao hơn, `app.retries` có giá trị `9` do đối số dòng lệnh thắng giá trị từ YAML. Trường hợp này minh họa rằng **default trong placeholder không khóa cứng giá trị**.

Các lệnh là ví dụ minh họa; tên JAR cần thay theo ứng dụng thực tế. Khi viết log cấu hình, chỉ in những giá trị không nhạy cảm.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Thấy lỗi `Could not resolve placeholder` | Không có khóa được yêu cầu và không khai báo default | Bổ sung cấu hình bắt buộc hoặc một default hợp lệ |
| `@Value` dùng default dù nghĩ đã đặt biến | Sai tên biến hoặc biến chưa truyền tới tiến trình Java | Kiểm tra tên và cách export/cấu hình container |
| Có `${key:3}` nhưng bean vẫn lỗi parse số | Khóa tồn tại với giá trị sai hoặc rỗng | Sửa nguồn giá trị, bổ sung validation; default không thay thế giá trị sai |
| Đổi file YAML nhưng kết quả không đổi | Nguồn ưu tiên cao hơn ghi đè thuộc tính | Xác định property source đang thắng |
| `${APP_PORT:8080}` nhận giá trị khác 8080 | `APP_PORT` đã có giá trị | Kiểm tra môi trường triển khai |
| `server.port=${PORT:8080}` nhưng server nghe cổng do `SERVER_PORT` chỉ định | Biến `SERVER_PORT` ghi đè trực tiếp `server.port` | Phân biệt tham chiếu `PORT` và override `SERVER_PORT` |
| Placeholder trong YAML có lỗi cú pháp | Ký tự đặc biệt/quote/escape không hợp lệ | Dùng dấu nháy phù hợp và kiểm tra định dạng nguồn |
| Đặt default mật khẩu cố định | Thiếu secret vẫn bị che bởi giá trị giả | Bỏ default, yêu cầu cấp secret rõ ràng |
| Default là chuỗi rỗng nhưng code cần số | Không có giá trị hợp lệ để chuyển sang số | Chọn default số hợp lệ hoặc xử lý optional có chủ đích |
| Placeholder tham chiếu vòng tròn | Hai khóa hoặc nhiều khóa phụ thuộc lẫn nhau | Loại bỏ vòng tham chiếu, định nghĩa một nguồn mặc định rõ ràng |
| Docker Compose xử lý `${...}` trước Spring | Có hai cơ chế nội suy của hai công cụ | Escape hoặc quote theo đúng lớp cấu hình mà placeholder cần đi qua |

Khi điều tra, nên đi từ **tên thuộc tính đang được hỏi** đến **nguồn cấu hình cuối cùng**, sau đó mới kiểm tra placeholder và kiểu giá trị. Nếu ứng dụng dùng Actuator, endpoint `env` hoặc `configprops` có thể hỗ trợ chẩn đoán nhưng phải hạn chế truy cập và bảo vệ dữ liệu nhạy cảm.

## 20. Bài tập tự kiểm tra

### Bài 1 — Có giá trị và không có giá trị

Code:

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

Hãy xác định kết quả khi:

- Không có `app.retry.max-attempts`.
- Có `app.retry.max-attempts=5`.
- Có `app.retry.max-attempts=0`.

**Đáp án:** lần lượt `3`, `5` và `0`. Default chỉ được dùng khi không tìm thấy thuộc tính.

### Bài 2 — Nested placeholder

Cấu hình:

~~~properties
app.api-url=${PRIMARY_URL:${FALLBACK_URL:http://localhost:8080}}
~~~

Hãy xác định giá trị khi:

1. `PRIMARY_URL=https://primary.example.org`.
2. Không có `PRIMARY_URL`, nhưng `FALLBACK_URL=https://backup.example.org`.
3. Cả hai biến đều không có.

**Đáp án:** lần lượt `https://primary.example.org`, `https://backup.example.org` và `http://localhost:8080`.

### Bài 3 — Giá trị rỗng

Trong YAML:

~~~yaml
app:
  worker-count: "${WORKER_COUNT:4}"
~~~

Nếu môi trường có `WORKER_COUNT=` là chuỗi rỗng, có thể kết luận giá trị sẽ luôn là `4` không?

**Đáp án:** **không**. Biến đã tồn tại với giá trị rỗng nên không mặc nhiên sử dụng default. Nếu bind vào `int`, việc chuyển đổi từ chuỗi rỗng còn có thể gây lỗi.

### Bài 4 — Property source ưu tiên hơn placeholder

Trong YAML:

~~~yaml
server:
  port: "${PORT:8080}"
~~~

Môi trường có `PORT=9090`. Lệnh chạy:

~~~bash
java -jar app.jar --server.port=7070
~~~

Cổng nào có hiệu lực nếu không có nguồn đặc biệt ưu tiên cao hơn?

**Đáp án:** `7070`. Đối số `--server.port` thường thắng thuộc tính từ Config Data; placeholder trong YAML không có quyền ưu tiên hơn đối số này.

### Bài 5 — Chọn nơi đặt default

Bạn có một nhóm cấu hình gồm `maxAttempts` và `timeout`, muốn Java record có giá trị mặc định ngay cả khi không tạo các khóa trong `application.yml`. Chọn cơ chế nào phù hợp?

**Đáp án gợi ý:** dùng `@ConfigurationProperties` cùng `@DefaultValue` trên constructor parameters/record components khi phù hợp. Cách đó đặt default tại lớp binding có kiểu, còn `${key:default}` phù hợp khi cần tham chiếu nguồn khác trong giá trị cấu hình.

## 21. Ghi nhớ

- Cú pháp **`${key:default}`** nghĩa là tìm `key`; nếu không có, dùng `default`.
- **`${key}`** không có default thường thích hợp khi giá trị bắt buộc; thiếu thuộc tính có thể làm bean khởi tạo thất bại.
- Default chỉ xử lý **khóa không tìm thấy**. Giá trị hiện diện nhưng sai kiểu, rỗng hoặc không đáp ứng nghiệp vụ cần được xử lý riêng.
- Trong YAML/properties, placeholder có thể lấy giá trị từ biến môi trường hoặc một thuộc tính Spring khác.
- Có thể viết **nested placeholder**: `${PRIMARY:${FALLBACK:local}}`.
- **`${key:}`** cho phép default rỗng, phù hợp với chuỗi tùy chọn hơn là cấu hình bắt buộc có kiểu.
- Việc chọn giá trị từ **property source ưu tiên cao** xảy ra độc lập với cơ chế default của placeholder.
- `@Value`, `Environment#getProperty(key, default)` và `@ConfigurationProperties`/`@DefaultValue` phục vụ những lớp cấu hình khác nhau.
- Chỉ cung cấp default khi sự vắng mặt là hợp lệ; với secret hoặc thuộc tính production bắt buộc, nên fail fast và validate rõ ràng.

**Tài liệu tham khảo:**

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — PropertySource Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
