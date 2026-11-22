# Tham chiếu thuộc tính bằng cú pháp `${key}` trong Spring Boot

## 1. Mục đích và bối cảnh

Trong Spring Boot Externalized Configuration, các giá trị cấu hình có thể đến từ file `application.properties`, `application.yml`, biến môi trường, Java system properties, đối số dòng lệnh hoặc tệp cấu hình bên ngoài. Khi nhiều property sử dụng chung một thành phần như hostname, port, vùng triển khai hay thư mục gốc, việc lặp nguyên giá trị ở nhiều khóa làm tăng khả năng sai lệch.

**Placeholder `${key}` cho phép giá trị của một property tham chiếu tới property khác.** Ví dụ:

~~~properties
app.api.host=localhost
app.api.port=8080
app.api.url=http://${app.api.host}:${app.api.port}/api
~~~

Trong môi trường không có nguồn ưu tiên cao hơn ghi đè, `app.api.url` có thể được phân giải thành `http://localhost:8080/api`.

Điểm chính là mối quan hệ giữa các **khóa cấu hình**, không phải thao tác nối chuỗi do Java code tự thực hiện. Nếu một nơi khác cung cấp giá trị mới cho `app.api.host`, URL tham chiếu có thể nhận giá trị mới khi Spring phân giải placeholder.

Cần phân biệt:

- **`${key}`**: cú pháp property placeholder, tham chiếu một khóa trong `Environment`.
- **`${key:default}`**: tham chiếu khóa và cung cấp giá trị dự phòng khi khóa thiếu.
- **`#{...}`**: Spring Expression Language (SpEL), một cơ chế đánh giá biểu thức khác.
- **Shell expansion**: ví dụ `${HOME}` trong Bash, do shell xử lý trước khi chương trình Java chạy nếu không được quote thích hợp.
- **Configuration binding**: ánh xạ property sang Java object, ví dụ bằng `@ConfigurationProperties`; binding có thể sử dụng giá trị chứa placeholder nhưng không phải chính placeholder.

## 2. Cú pháp cơ bản

Dạng chung:

~~~text
${property.name}
~~~

Ví dụ:

~~~properties
spring.application.name=order-service
app.banner.title=Welcome to ${spring.application.name}
~~~

Khi `spring.application.name` hiệu lực là `order-service`, `app.banner.title` có thể được phân giải thành `Welcome to order-service`.

Có thể sử dụng nhiều placeholder trong cùng một giá trị:

~~~properties
db.host=localhost
db.port=5432
db.name=orders
db.url=jdbc:postgresql://${db.host}:${db.port}/${db.name}
~~~

Kết quả tương ứng:

~~~text
jdbc:postgresql://localhost:5432/orders
~~~

Không bắt buộc placeholder chiếm toàn bộ chuỗi. Nó có thể ở đầu, giữa hoặc cuối chuỗi:

~~~properties
app.log.prefix=[${spring.application.name}]
app.storage.path=/srv/${spring.application.name}/data
app.health.url=${app.api.url}/health
~~~

Ví dụ cuối còn minh họa **tham chiếu nhiều tầng**: `app.health.url` tham chiếu `app.api.url`, giá trị `app.api.url` lại có thể chứa các placeholder khác.

### 2.1. Thứ tự dòng trong file không phải thứ tự thực thi

~~~properties
app.url=https://${app.host}/v1
app.host=api.example.test
~~~

Dù `app.host` xuất hiện sau `app.url`, placeholder vẫn có thể phân giải khi truy vấn cấu hình. Đây không phải chương trình chạy tuần tự từng dòng; parser đọc các cặp thuộc tính, còn Spring tra cứu các khóa qua `Environment`.

### 2.2. Không giới hạn trong một file

Placeholder không chỉ tham chiếu những property khai báo trong cùng file. Giá trị được tham chiếu có thể đến từ `application-prod.properties`, file external, biến môi trường, Java system properties hoặc command-line arguments, miễn là chúng đã tham gia vào `Environment` theo cơ chế nạp cấu hình phù hợp.

## 3. Cơ chế phân giải qua `Environment`

Spring Framework cung cấp `Environment`, `PropertyResolver` và các `PropertySource`. Spring Boot bổ sung cơ chế Config Data và các nguồn cấu hình thông dụng vào hệ thống này.

Khi một component yêu cầu giá trị:

1. Spring tìm property theo tên khóa trong các nguồn, xét thứ tự ưu tiên.
2. Nếu giá trị được chọn chứa placeholder, resolver có thể tra cứu khóa bên trong placeholder.
3. Giá trị của khóa tham chiếu được thay vào chuỗi.
4. Nếu còn placeholder lồng nhau, resolver có thể tiếp tục phân giải theo khả năng được hỗ trợ.
5. Component nhận giá trị sau khi xử lý, có thể tiếp tục qua bước chuyển đổi kiểu và validation.

Ví dụ:

~~~properties
app.region=ap-southeast-1
app.storage.path=/data/${app.region}/orders
~~~

Java đọc giá trị:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StorageSettings {
    private final Environment environment;

    public StorageSettings(Environment environment) {
        this.environment = environment;
    }

    public String storagePath() {
        return environment.getRequiredProperty("app.storage.path");
    }
}
~~~

Trong cấu hình ví dụ, `storagePath()` trả về `/data/ap-southeast-1/orders`.

**Lưu ý:** tham chiếu được phân giải lúc component thực sự sử dụng cơ chế của Spring, không phải một thao tác thay text vĩnh viễn vào tệp nguồn. Điều này lý giải vì sao một khóa ở nguồn ưu tiên cao hơn có thể ảnh hưởng đến các placeholder trong file ưu tiên thấp hơn.

## 4. Tham chiếu property trong `application.properties`

Ví dụ tổ chức cấu hình dùng chung:

~~~properties
spring.application.name=inventory-service

app.http.scheme=https
app.http.host=localhost
app.http.port=8443

app.http.base-url=${app.http.scheme}://${app.http.host}:${app.http.port}
app.http.health-url=${app.http.base-url}/actuator/health
app.log.prefix=[${spring.application.name}]
~~~

Các giá trị có thể phân giải:

| Khóa | Giá trị |
| --- | --- |
| `app.http.base-url` | `https://localhost:8443` |
| `app.http.health-url` | `https://localhost:8443/actuator/health` |
| `app.log.prefix` | `[inventory-service]` |

Không cần thêm dấu quote vào giá trị `.properties` chỉ vì có placeholder. Trong Java properties, dấu `=` đầu tiên không được escape dùng phân cách khóa và giá trị; dấu `:` nằm trong giá trị URL không nhất thiết có ý nghĩa tách property.

Nếu giá trị chứa dấu gạch chéo ngược hoặc ký tự đặc biệt của định dạng file, cần hiểu cả quy tắc escape của `.properties`. Ví dụ `\n` là newline, `\\` biểu diễn backslash. Những quy tắc này thuộc định dạng file và được áp dụng trước khi một component Spring dùng giá trị.

## 5. Tham chiếu trong YAML

Trong `application.yml`, dùng cấu trúc lồng nhau và placeholder giống về mặt ý nghĩa:

~~~yaml
spring:
  application:
    name: inventory-service

app:
  http:
    scheme: https
    host: localhost
    port: 8443
    base-url: "${app.http.scheme}://${app.http.host}:${app.http.port}"
    health-url: "${app.http.base-url}/actuator/health"
  log:
    prefix: "[${spring.application.name}]"
~~~

YAML parser xử lý cấu trúc key/value, sau đó Spring Boot đưa các property phù hợp vào nguồn cấu hình. Chuỗi `${...}` được xử lý theo cơ chế placeholder của Spring khi được sử dụng.

### 5.1. Khi nào nên dùng quote?

Trong YAML, chuỗi có ký tự `:`, `#`, `[`, `]` hoặc các ký tự đặc biệt khác đôi lúc cần quote để tránh parser diễn giải thành cấu trúc YAML. Dùng double quote hoặc single quote thích hợp giúp làm rõ một giá trị là chuỗi.

Ví dụ:

~~~yaml
app:
  api-url: "https://${app.api.host}:${app.api.port}/v1"
~~~

Không coi dấu quote trong YAML giống dấu quote được thêm trực tiếp vào giá trị của `.properties`. Đó là hai quy tắc phân tích định dạng khác nhau.

### 5.2. Phân biệt YAML interpolation và Spring placeholder

YAML thuần không biết rằng `${app.api.host}` là property Spring. Chính Spring Boot và các API Spring sử dụng cơ chế resolver phù hợp để thay thế. Nếu cùng file được đọc bởi một ứng dụng không dùng Spring, placeholder có thể vẫn là chuỗi văn bản nguyên vẹn.

## 6. Giá trị mặc định với `${key:default}`

Cú pháp mở rộng:

~~~text
${property.name:default-value}
~~~

Cho phép cung cấp giá trị mặc định nếu property cần tham chiếu không tồn tại trong quá trình tra cứu.

Ví dụ:

~~~properties
app.api.host=${APP_API_HOST:localhost}
app.api.port=${APP_API_PORT:8080}
app.api.url=http://${app.api.host}:${app.api.port}/v1
~~~

Nếu `APP_API_HOST` và `APP_API_PORT` không được cung cấp từ những nguồn mà resolver có thể tìm thấy, kết quả có thể là `http://localhost:8080/v1`. Khi hai khóa hiện diện, giá trị từ các source được dùng.

Một số ví dụ phổ biến:

~~~properties
app.display-name=${spring.application.name:unknown-service}
app.log.level=${APP_LOG_LEVEL:INFO}
app.timeout=${APP_TIMEOUT:3s}
app.features.audit-enabled=${APP_AUDIT_ENABLED:false}
~~~

Giá trị mặc định của placeholder **không tạo ra một property mới** trong `Environment`. Ví dụ `${APP_TIMEOUT:3s}` cho phép chuỗi hiện tại nhận `3s` khi thiếu `APP_TIMEOUT`, chứ không có nghĩa Spring đã khai báo `APP_TIMEOUT=3s` trong một property source.

### 6.1. Giá trị mặc định rỗng

~~~properties
app.optional-suffix=${APP_SUFFIX:}
~~~

Nếu không tìm được `APP_SUFFIX`, giá trị có thể trở thành chuỗi rỗng. Chuỗi rỗng khác với việc thiếu khóa; việc chuyển đổi thành số, boolean, URI hoặc một kiểu cần validation có thể cho kết quả khác nhau.

Không nên đặt mặc định rỗng cho cấu hình bắt buộc chỉ để tránh lỗi startup.

### 6.2. Mặc định chứa dấu hai chấm

~~~properties
app.api.url=${APP_API_URL:https://api.example.test:8443/v1}
~~~

Dấu `:` phân tách tên khóa với giá trị mặc định là dấu phân cách đầu tiên ở vị trí thích hợp trong biểu thức. Các dấu `:` xuất hiện trong URL mặc định là nội dung của default, không có nghĩa đây là nhiều placeholder.

Với biểu thức rất phức tạp hoặc chuỗi mang cú pháp đặc biệt của một thư viện khác, cần kiểm tra qua đúng parser và Spring version đang sử dụng.

### 6.3. Default không thay thế validation

~~~properties
app.retry-count=${APP_RETRIES:3}
~~~

Nếu `APP_RETRIES` được khai báo là `many` và thành phần Java yêu cầu `int`, placeholder có thể phân giải thành `many` nhưng bước chuyển kiểu vẫn thất bại. Giá trị mặc định chủ yếu xử lý trường hợp thiếu khóa, không tự bảo đảm dữ liệu hợp lệ.

## 7. Placeholder lồng nhau

Có thể dùng placeholder trong chính phần default của placeholder khác:

~~~properties
app.primary.host=${PRIMARY_HOST:${FALLBACK_HOST:localhost}}
~~~

Ý nghĩa mong muốn: ưu tiên `PRIMARY_HOST`; khi thiếu, xét `FALLBACK_HOST`; khi cả hai thiếu, dùng `localhost`.

Hoặc:

~~~properties
app.service.name=order-service
app.service.url=${SERVICE_URL:http://${app.service.name}:8080}
~~~

Nếu `SERVICE_URL` không tồn tại, giá trị mặc định tham chiếu tới `app.service.name` để tạo URL.

Spring Framework có cơ chế phân giải nested placeholders, nhưng những biểu thức lồng quá sâu thường khó bảo trì và khó phát hiện vấn đề thứ tự nguồn. Nếu có nhiều biến thể cấu hình theo môi trường, nên cân nhắc profile-specific files, document có điều kiện hoặc cung cấp một property hoàn chỉnh ở môi trường triển khai.

## 8. Tên property canonical và relaxed binding

Spring Boot khuyến nghị dùng **canonical property names** bên trong placeholder: chữ thường, các phần phân tách bằng dấu chấm, và từ ghép sử dụng kebab-case.

**Ví dụ nên dùng:**

~~~properties
app.client.read-timeout=5s
app.effective-timeout=${app.client.read-timeout}
~~~

Tránh phụ thuộc vào biến thể không canonical:

~~~properties
app.client.readTimeout=5s
app.effective-timeout=${app.client.readTimeout}
~~~

Dạng canonical giúp Spring Boot áp dụng các quy tắc tra cứu phù hợp với externalized configuration, bao gồm biến môi trường ở dạng quy ước.

Đối với tên `app.client.read-timeout`, dạng biến môi trường theo quy tắc chuyển tên trong Spring Boot thường là `APP_CLIENT_READTIMEOUT`: thay dấu chấm bằng underscore, loại bỏ dấu gạch nối, viết hoa. `APP_CLIENT_READ_TIMEOUT` không mặc nhiên là dạng tương đương trong mọi cơ chế tra cứu.

Ví dụ quy đổi:

| Tên canonical | Tên biến môi trường điển hình |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `app.client.read-timeout` | `APP_CLIENT_READTIMEOUT` |
| `app.connection.pool-size` | `APP_CONNECTION_POOLSIZE` |

Quy tắc binding cho list, map và các loại key đặc biệt có thể phức tạp hơn. Khi có nghi ngờ, xác nhận tên và nguồn property tại runtime thay vì suy đoán theo thói quen đặt tên Java.

## 9. Độ ưu tiên của nguồn: khóa đích và khóa tham chiếu

Cùng một khóa có thể xuất hiện trong nhiều `PropertySource`. Spring Boot có quy tắc ưu tiên giữa Config Data trong JAR, Config Data bên ngoài, biến môi trường, Java system properties và command-line arguments.

Ví dụ trong `application.properties`:

~~~properties
app.api.host=localhost
app.api.url=https://${app.api.host}/v1
~~~

Khi khởi chạy:

~~~bash
java -jar app.jar --app.api.host=api.production.example
~~~

Trong Spring Boot thông thường, command-line property có độ ưu tiên cao hơn file, nên URL có thể được phân giải là `https://api.production.example/v1`.

Nhưng nếu chạy:

~~~bash
java -jar app.jar --app.api.url=https://override.example/v2
~~~

thì chính **khóa đích `app.api.url`** bị ghi đè bởi command line. Spring không buộc phải sử dụng chuỗi chứa placeholder trong file ưu tiên thấp hơn để tạo URL hiệu lực.

Khi phân tích một property có placeholder, đặt hai câu hỏi riêng:

1. Nguồn nào thắng cho **property đang đọc**?
2. Nếu giá trị thắng cuộc chứa `${...}`, nguồn nào thắng cho **property được tham chiếu**?

Đây là điểm quan trọng nhất khi một ứng dụng hoạt động khác nhau giữa local và production.

### 9.1. File external ghi đè cấu hình trong JAR

Trong JAR:

~~~properties
# classpath:/application.properties
app.api.host=api.default.example
app.api.url=https://${app.api.host}/v1
~~~

Bên ngoài JAR:

~~~properties
# file:./config/application.properties
app.api.host=api.prod.example
~~~

Với quy tắc tìm kiếm mặc định phù hợp và không có nguồn ưu tiên cao hơn, file external có thể ghi đè `app.api.host`; `app.api.url` từ JAR được phân giải thành `https://api.prod.example/v1`. Không cần sao chép cùng một URL hoàn chỉnh ở cả hai file.

### 9.2. Property trong file theo profile

~~~properties
# application.properties
app.scheme=https
app.host=api.example.test
app.url=${app.scheme}://${app.host}/v1
~~~

~~~properties
# application-dev.properties
app.scheme=http
app.host=localhost:8081
~~~

Khi profile `dev` được kích hoạt, `app.url` có thể thành `http://localhost:8081/v1` trong tình huống không có source khác ghi đè. Profile quyết định file nào được nạp, còn placeholder sử dụng giá trị hiệu lực của các khóa.

Không nên hiểu rằng một placeholder chỉ tra cứu file chứa nó. Spring giải quyết tham chiếu trên tập `Environment` đã có.

## 10. `@Value` trong bean Spring

`@Value` phù hợp khi một bean cần một số ít cấu hình đơn lẻ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ClientEndpoint {
    private final String baseUrl;

    public ClientEndpoint(
            @Value("${app.api.url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

Với:

~~~properties
app.api.host=api.example.test
app.api.url=https://${app.api.host}/v1
~~~

constructor nhận chuỗi URL đã được phân giải.

Giá trị mặc định cũng dùng được ngay trong `@Value`:

~~~java
@Component
public class RetryPolicy {
    private final long delayMillis;

    public RetryPolicy(
            @Value("${app.retry.delay-ms:500}") long delayMillis) {
        this.delayMillis = delayMillis;
    }

    public long delayMillis() {
        return delayMillis;
    }
}
~~~

Spring thực hiện chuyển kiểu khi inject theo khả năng conversion hiện có. Nếu property chứa ký tự không phù hợp với `long`, bean có thể không tạo được.

### 10.1. Khác biệt với SpEL

~~~java
@Value("${app.retry-count:3}") // Property placeholder.
private int retryCount;

@Value("#{2 * 3}")              // Spring Expression Language.
private int batchSize;
~~~

`${...}` tra cứu cấu hình; `#{...}` đánh giá biểu thức SpEL. Dù có những ngữ cảnh kết hợp hai cơ chế, không nên sử dụng thay thế cho nhau hoặc coi chúng là cùng một cú pháp.

### 10.2. Thời điểm inject

Bean thường nhận giá trị trong lúc được tạo. Khi thay đổi file `application.properties` trên ổ đĩa sau khi context đã khởi động, `@Value` không tự động cập nhật trường Java. Ứng dụng có thể cần restart hoặc một cơ chế refresh được thiết kế riêng.

## 11. `Environment`: giải quyết placeholder theo yêu cầu

Nếu ứng dụng có một chuỗi template cần được phân giải trực tiếp, có thể sử dụng các API của `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class TemplateResolver {
    private final Environment environment;

    public TemplateResolver(Environment environment) {
        this.environment = environment;
    }

    public String resolve(String template) {
        return environment.resolvePlaceholders(template);
    }

    public String resolveRequired(String template) {
        return environment.resolveRequiredPlaceholders(template);
    }
}
~~~

Giả sử `app.region=asia`:

~~~java
String a = resolver.resolve("Region: ${app.region}");
// "Region: asia"

String b = resolver.resolve("Region: ${unknown.region}");
// Placeholder thiếu có thể được giữ nguyên.

String c = resolver.resolveRequired("Region: ${unknown.region}");
// Báo lỗi nếu không tìm thấy khóa bắt buộc.
~~~

Sự khác nhau:

- `resolvePlaceholders`: xử lý những placeholder tìm được và có thể giữ nguyên placeholder chưa giải quyết được.
- `resolveRequiredPlaceholders`: yêu cầu những placeholder được tham chiếu phải phân giải thành công, nếu không báo lỗi.

Vì vậy, không thể khẳng định mọi placeholder thiếu khóa đều khiến Spring Boot dừng khởi động, hoặc đều biến thành chuỗi rỗng. Cần xác định chính xác API hoặc thành phần đang đọc cấu hình.

Ví dụ đọc trực tiếp một property:

~~~java
String url = environment.getRequiredProperty("app.api.url");
~~~

Nếu giá trị property đó chứa placeholder, cơ chế `PropertyResolver` thông thường có thể phân giải nội dung khi đọc.

## 12. `@ConfigurationProperties` và tham chiếu giá trị

Đối với nhiều thuộc tính liên quan, `@ConfigurationProperties` giúp đưa cấu hình vào object có kiểu:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientSettings(
        String host,
        Duration timeout,
        int maxRetries
) {}
~~~

Trong `application.properties`:

~~~properties
app.default-host=localhost
app.client.host=${app.default-host}
app.client.timeout=5s
app.client.max-retries=2
~~~

Ứng dụng cần đăng ký class này bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(ClientSettings.class)`. Spring Boot Binder có thể phân giải tham chiếu và chuyển `5s` sang `Duration`.

Không cần tạo placeholder cho mọi trường: `@ConfigurationProperties` đã trực tiếp bind các giá trị của nhóm `app.client.*`. Dùng placeholder khi thực sự cần chia sẻ một giá trị giữa nhiều property.

Có thể bổ sung Bean Validation và `@Validated` nếu cần kiểm tra cấu hình bắt buộc hoặc giới hạn giá trị.

## 13. Placeholder và biến môi trường

File cấu hình:

~~~properties
app.api.url=https://${app.api.host:localhost}/v1
~~~

Biến môi trường:

~~~bash
export APP_API_HOST=api.example.test
java -jar app.jar
~~~

Với cách đặt tên canonical và quy tắc tra cứu thông dụng, placeholder `${app.api.host}` có thể nhận giá trị từ `APP_API_HOST`.

Có thể cấu hình bằng JVM property:

~~~bash
java -Dapp.api.host=api.example.test -jar app.jar
~~~

Hoặc đối số ứng dụng:

~~~bash
java -jar app.jar --app.api.host=api.example.test
~~~

Đây là ba nguồn property khác nhau. Nếu chúng cùng tồn tại và khai báo giá trị khác nhau, mức ưu tiên của Spring Boot quyết định giá trị được sử dụng.

### 13.1. Tránh để shell xử lý placeholder trước Spring

Trong Bash, `${HOME}` là cú pháp shell expansion. Nếu cần truyền literal `${APP_API_HOST:localhost}` cho Spring dưới dạng command-line argument, dùng cách quote phù hợp:

~~~bash
java -jar app.jar '--app.api.host=${APP_API_HOST:localhost}'
~~~

Dấu nháy đơn trong shell POSIX giúp giữ nguyên chuỗi placeholder để Spring đọc. PowerShell và Windows CMD có quy tắc quoting khác; cần xem cú pháp đúng cho shell đang sử dụng.

Khi placeholder nằm trực tiếp trong `application.properties` hoặc `application.yml`, shell không tự can thiệp vào nội dung file trong quy trình nạp Config Data thông thường.

## 14. Tham chiếu vòng và tên khóa không tồn tại

### 14.1. Tham chiếu vòng

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Hai property cùng trỏ ngược lại nhau, không có giá trị kết thúc. Khi được phân giải, một cơ chế Spring có thể báo lỗi circular placeholder. Chu trình cũng có thể gồm nhiều khóa:

~~~properties
app.a=${app.b}
app.b=${app.c}
app.c=${app.a}
~~~

Sửa bằng cách định nghĩa một giá trị gốc không phụ thuộc vào các khóa tham chiếu ngược:

~~~properties
app.base=localhost
app.a=${app.base}
app.b=${app.a}
~~~

Trong môi trường có profile hoặc nguồn ghi đè, vòng tham chiếu đôi khi chỉ xuất hiện ở một tổ hợp nguồn cụ thể; hãy lần theo **giá trị hiệu lực** của từng khóa.

### 14.2. Thiếu khóa

~~~properties
app.api.url=https://${app.missing.host}/v1
~~~

Khi `app.missing.host` không tồn tại, có thể xảy ra lỗi unresolved placeholder trong các API cần giá trị bắt buộc. Ở những API nới lỏng hơn, một placeholder chưa được phân giải có thể còn nguyên văn.

Nếu thiếu khóa là trường hợp hợp lệ, có thể dùng:

~~~properties
app.api.url=https://${app.api.host:localhost}/v1
~~~

Nếu thiếu khóa là lỗi cấu hình nghiêm trọng, đừng dùng default ngẫu nhiên chỉ để làm ứng dụng khởi động. Nên phát hiện thiếu cấu hình bắt buộc và báo lỗi sớm.

### 14.3. Có giá trị nhưng sai kiểu

~~~properties
app.retry-count=not-a-number
app.effective-retries=${app.retry-count}
~~~

Placeholder có thể hoàn tất về mặt tham chiếu, nhưng `not-a-number` không phải `int` hợp lệ. Kiểm tra quá trình binding và conversion, không chỉ placeholder resolution.

### 14.4. Giá trị rỗng khác thiếu property

~~~properties
APP_SUFFIX=
app.suffix=${APP_SUFFIX:default}
~~~

Nếu `APP_SUFFIX` được khai báo với chuỗi rỗng, resolver có thể xem là một giá trị đã tồn tại và không sử dụng default, tùy cơ chế và nguồn thực tế. Không mặc nhiên coi chuỗi rỗng như property vắng mặt. Khi cần quy tắc riêng cho empty string, hãy thể hiện bằng validation hoặc logic cấu hình rõ ràng.

## 15. Giữ nguyên literal `${...}` khi có template engine khác

Một hệ thống có thể cần lưu chuỗi:

~~~text
Dear ${customerName}
~~~

để một template engine xử lý sau. Nếu chuỗi đi qua Spring placeholder resolver, Spring có thể cố tìm property tên `customerName`.

Cách escape phụ thuộc vào lớp đang xử lý:

- Trong file `.properties`, `\` là escape của định dạng file; một dấu backslash có thể bị parser loại bỏ trước khi giá trị tới Spring.
- Trong Java string literal, bản thân `\` cũng cần escape đúng.
- Trong YAML, single-quoted và double-quoted scalar có quy tắc escape khác nhau.
- Trong các phiên bản Spring Framework, ký tự escape và cách xử lý placeholder có thể có khác biệt theo cấu hình resolver.

Vì vậy, không nên nghĩ thêm một backslash trước `${...}` sẽ luôn giữ nguyên literal ở mọi nguồn. Với template dành cho hệ thống khác, hãy chọn cơ chế được component đó hỗ trợ và kiểm tra chuỗi **ở đúng điểm sử dụng cuối**.

## 16. Placeholder và bí mật cấu hình

Ví dụ:

~~~properties
spring.datasource.url=${DATABASE_URL:jdbc:postgresql://localhost:5432/app}
spring.datasource.username=${DATABASE_USER:app}
spring.datasource.password=${DATABASE_PASSWORD}
~~~

Cách này cho phép truyền kết nối database từ môi trường chạy. Tuy nhiên:

- Placeholder **không mã hóa** mật khẩu hoặc token.
- Không đặt secret thật trong default hay file commit vào repository.
- Secret thiếu có thể cần làm startup thất bại thay vì rơi vào password mẫu.
- Hạn chế hiển thị giá trị đã phân giải trong log và endpoint chẩn đoán.
- Quyền truy cập secret phụ thuộc vào hạ tầng triển khai, không phải vào cú pháp `${...}`.

Khi một giá trị secret có ký tự giống placeholder, cần xem xét cách nguồn và resolver xử lý. Một chuỗi bí mật không nên bị vô tình thay thế hoặc ghi log dưới dạng chưa che giấu.

## 17. Tương tác với profile và Config Data

Giả sử trong JAR:

~~~properties
# application.properties
app.host=api.default.example
app.url=https://${app.host}/v1
~~~

File dành riêng cho profile:

~~~properties
# application-prod.properties
app.host=api.prod.example
~~~

Nếu profile `prod` đang hoạt động và không có nguồn ưu tiên cao hơn ghi đè, `app.url` có thể được phân giải thành `https://api.prod.example/v1`.

Trong YAML nhiều document:

~~~yaml
app:
  host: api.default.example
  url: "https://${app.host}/v1"
---
spring:
  config:
    activate:
      on-profile: prod
app:
  host: api.prod.example
~~~

Document thứ hai chỉ tham gia khi profile phù hợp. Placeholder không tự bật profile và không quyết định document nào được nạp.

Đặc biệt, một số thuộc tính chọn vị trí Config Data như `spring.config.location` hoặc `spring.config.name` cần sẵn sàng rất sớm trong quy trình khởi động. Không nên giả định chúng có thể tham chiếu bất kỳ property nào chỉ được nạp ở giai đoạn sau từ chính location đang được chọn.

## 18. Ví dụ kiểm tra bằng Spring Boot Test

Có thể kiểm tra hành vi phân giải trong test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.api.host=test.example",
    "app.api.url=https://${app.api.host}/v1"
})
class PlaceholderResolutionTest {

    @Autowired
    Environment environment;

    @Test
    void resolvesReference() {
        assertEquals(
            "https://test.example/v1",
            environment.getProperty("app.api.url")
        );
    }
}
~~~

Tình huống này minh họa việc một property được đưa vào test context có thể tham chiếu property khác. Kết quả giả định không có nguồn test ưu tiên cao hơn ghi đè hai giá trị đó.

Nếu muốn kiểm tra default của `${app.api.host:localhost}`, cần bảo đảm `app.api.host` thật sự không xuất hiện trong nguồn khác của test. Nếu không, bài kiểm tra đang kiểm tra precedence thay vì fallback.

## 19. Chẩn đoán khi placeholder trả sai giá trị

Khi ứng dụng nhận `${key}` nguyên văn, giá trị thiếu hoặc một URL khác mong đợi, có thể lần lượt kiểm tra:

1. **Khóa đích là gì?** Xác định property ứng dụng thực sự đang đọc, ví dụ `app.api.url`.
2. **Nguồn nào thắng cho khóa đích?** Có thể command line đã ghi đè toàn bộ chuỗi chứa placeholder.
3. **Tên khóa bên trong placeholder có đúng không?** Ưu tiên dạng canonical, ví dụ `app.client.read-timeout`.
4. **Khóa tham chiếu có tồn tại không?** Kiểm tra file, profile, biến môi trường, JVM property và command line.
5. **File chứa khóa đã được nạp chưa?** Xem tên file, location, profile, Config Data import và document activation.
6. **Có tham chiếu vòng không?** Tìm chuỗi khóa gọi lẫn nhau mà không có giá trị gốc.
7. **Có default không?** Nếu có, nó có đang che khuất một lỗi cấu hình bắt buộc?
8. **Có bước parse trước Spring không?** Shell expansion, YAML quoting hoặc properties escape có thể thay đổi chuỗi.
9. **Property đã phân giải nhưng sai kiểu?** Kiểm tra binding, conversion và validation.
10. **Ứng dụng đã restart sau khi cấu hình đổi chưa?** Cơ chế thông thường không tự refresh toàn bộ bean và Config Data.
11. **Thành phần có thực sự dùng Spring resolver không?** Một thư viện tự mở file bằng parser riêng có thể không hiểu `${...}`.
12. **Có thể quan sát an toàn không?** Dùng `Environment` hoặc công cụ chẩn đoán được bảo vệ; không in secret ra log.

Spring Boot Actuator, nếu được bật với bảo mật và che giấu phù hợp, có thể giúp quan sát `Environment` và nguồn property qua endpoint `/actuator/env`. Tuy nhiên, không nên mở endpoint quản trị ra Internet hoặc in toàn bộ giá trị bí mật chỉ để tìm nguồn thắng.

## 20. Bài tập suy luận giá trị hiệu lực

Giả sử `application.properties` có:

~~~properties
app.region=local
app.host=service.${app.region}.example
app.url=https://${app.host}/api
app.timeout=${APP_TIMEOUT:3s}
~~~

**Tình huống A: không có nguồn ghi đè.**

Giá trị có thể là:

~~~text
app.host    = service.local.example
app.url     = https://service.local.example/api
app.timeout = 3s
~~~

**Tình huống B: chạy với command-line argument.**

~~~bash
java -jar app.jar --app.region=prod
~~~

Khi đó:

~~~text
app.host = service.prod.example
app.url  = https://service.prod.example/api
~~~

**Tình huống C: ghi đè trực tiếp URL.**

~~~bash
java -jar app.jar \
  --app.region=prod \
  --app.url=https://another.example/api
~~~

Giá trị hiệu lực của `app.url` là URL được truyền trực tiếp từ command line; việc `app.region` là `prod` không ép `app.url` phải dùng placeholder chứa trong file.

**Tình huống D: môi trường có timeout.**

~~~bash
APP_TIMEOUT=10s java -jar app.jar
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè, `app.timeout` có thể nhận `10s`.

Bốn tình huống này làm rõ sự khác biệt giữa tham chiếu property, fallback, và độ ưu tiên của nguồn cấu hình.

## 21. Checklist áp dụng

- Viết `${key}` để tham chiếu một property qua cơ chế Spring.
- Viết `${key:default}` khi giá trị dự phòng là hợp lệ về nghiệp vụ và vận hành.
- Ưu tiên tên khóa lowercase và kebab-case theo quy ước canonical của Spring Boot.
- Nhớ rằng placeholder có thể tham chiếu nguồn khác, không chỉ file hiện tại.
- Khi giá trị sai, xác định cả source của **khóa đích** và source của **khóa được tham chiếu**.
- Không dùng placeholder để thay thế validation, type conversion hay cơ chế profile.
- Tránh tham chiếu vòng và cấu trúc nested placeholder quá sâu.
- Không nhầm `${...}` với SpEL `#{...}` hoặc với phép thay biến của shell.
- Với nhóm cấu hình lớn, sử dụng `@ConfigurationProperties` để bind có kiểu, chỉ dùng placeholder nơi thật sự cần tái sử dụng giá trị.
- Không đưa mật khẩu, API key hoặc token vào giá trị mặc định.
- Kiểm tra behavior tại đúng component đang dùng property và đúng phiên bản Spring Boot/Framework.

## 22. Ghi nhớ

**`${key}` liên kết một giá trị cấu hình với giá trị của khóa khác.** Nó hoạt động qua mô hình `Environment` và property sources của Spring; Spring Boot làm cho cơ chế này hữu ích trong thực tế bằng cách hỗ trợ nhiều nguồn externalized configuration, profile và binding.

**`${key:default}`** cung cấp phương án dự phòng khi khóa được tham chiếu thiếu. Kết quả cuối còn phụ thuộc vào nguồn property được ưu tiên, thời điểm tra cứu, cách parser xử lý chuỗi và thành phần Java sử dụng giá trị.

Muốn cấu hình dễ bảo trì, hãy định nghĩa các khóa dùng chung rõ ràng, dùng placeholder canonical, tránh vòng tham chiếu và xác minh giá trị hiệu lực tại runtime.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration, Property Placeholders](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.property-placeholders)
- [Spring Framework Reference — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Framework API — PropertyResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertyResolver.html)
