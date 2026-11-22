# Lỗi placeholder không phân giải được và tham chiếu vòng trong Spring Boot

Spring Boot hỗ trợ tham chiếu một giá trị cấu hình từ giá trị khác bằng cú pháp placeholder `${property.name}`. Ví dụ, ứng dụng có thể đặt URL dịch vụ dựa trên tên host hoặc lấy mật khẩu từ biến môi trường. Cơ chế này giúp giảm lặp cấu hình, nhưng cũng có thể gây hai nhóm lỗi quan trọng:

1. **Placeholder không phân giải được (unresolved placeholder):** Spring không tìm thấy thuộc tính mà biểu thức tham chiếu yêu cầu.
2. **Tham chiếu vòng (circular placeholder reference):** một thuộc tính trực tiếp hoặc gián tiếp tham chiếu trở lại chính nó, khiến chuỗi phân giải không có điểm kết thúc.

Hai lỗi đều có thể xảy ra khi nạp hoặc sử dụng cấu hình, nhất là ở lúc tạo bean bằng `@Value` hoặc lúc Spring Boot bind các thuộc tính. Tuy nhiên, thời điểm xuất hiện lỗi còn phụ thuộc vào **API truy cập**, nguồn thuộc tính, cách xử lý nghiêm ngặt hay cho phép bỏ qua placeholder chưa phân giải.

Bài học sử dụng Spring Boot 3.3.x và Java 21, đi từ cú pháp cơ bản đến ví dụ ứng dụng, cách chẩn đoán và giải pháp thực tế.

## 1. Placeholder trong cấu hình là gì?

Một placeholder là đoạn văn bản có dạng:

~~~text
${property.name}
~~~

Khi giá trị được phân giải, Spring tìm `property.name` trong các `PropertySource` của `Environment`. Nếu tìm được giá trị phù hợp, đoạn tham chiếu được thay bằng giá trị ấy.

Ví dụ trong `application.yml`:

~~~yaml
app:
  host: localhost
  port: 8085
  base-url: "http://${app.host}:${app.port}/api"
~~~

Nếu các giá trị này có hiệu lực và không bị nguồn ưu tiên cao hơn ghi đè, biểu thức `app.base-url` được phân giải thành:

~~~text
http://localhost:8085/api
~~~

Trong `application.properties`, cách viết tương đương:

~~~properties
app.host=localhost
app.port=8085
app.base-url=http://${app.host}:${app.port}/api
~~~

Nên sử dụng tên placeholder ở dạng chuẩn của Spring Boot, chẳng hạn `app.service-url` với chữ thường và dấu gạch ngang. Cách đặt tên này giúp áp dụng relaxed binding nhất quán giữa các nguồn cấu hình.

### Giá trị cuối cùng có thể đến từ nguồn khác

Giả sử `application.yml` có:

~~~yaml
app:
  host: localhost
  base-url: "http://${app.host}/api"
~~~

Khi chạy:

~~~bash
java -jar demo.jar --app.host=service.internal
~~~

`app.base-url` có thể trở thành `http://service.internal/api` vì tham số CLI cung cấp giá trị hiệu lực cao hơn cho `app.host`. Placeholder tham chiếu **tên thuộc tính trong Environment**, không nhất thiết chỉ tham chiếu khóa trong cùng tệp YAML.

## 2. Placeholder có giá trị mặc định

Cú pháp phổ biến:

~~~text
${property.name:default-value}
~~~

Nếu thuộc tính được yêu cầu **không tồn tại**, Spring có thể sử dụng phần mặc định sau dấu hai chấm.

Ví dụ:

~~~yaml
app:
  display-name: "${APP_DISPLAY_NAME:Local Demo}"
  endpoint: "${APP_ENDPOINT:http://localhost:8080}"
  retries: "${APP_RETRIES:3}"
~~~

Nếu không có các biến tương ứng, giá trị sau khi phân giải là:

~~~text
app.display-name = Local Demo
app.endpoint     = http://localhost:8080
app.retries      = 3
~~~

Đối với `retries`, kết quả placeholder thường bắt đầu là văn bản; khi bind vào `int` qua `@ConfigurationProperties`, Spring Boot thực hiện chuyển đổi kiểu thích hợp.

Có thể viết placeholder lồng nhau:

~~~yaml
app:
  endpoint: "${APP_ENDPOINT:${APP_FALLBACK_ENDPOINT:http://localhost:8080}}"
~~~

Khi `APP_ENDPOINT` không tồn tại, Spring thử `APP_FALLBACK_ENDPOINT`; nếu cả hai thiếu, dùng URL sau cùng. Đây là **chuỗi lựa chọn fallback có điểm dừng**, không phải tham chiếu vòng.

### Giá trị rỗng khác giá trị không tồn tại

Nếu biến `APP_DISPLAY_NAME` tồn tại nhưng có giá trị chuỗi rỗng, fallback trong `${APP_DISPLAY_NAME:Local Demo}` thường **không được kích hoạt chỉ vì giá trị rỗng**. Cú pháp placeholder mặc định được dùng khi không giải quyết được thuộc tính, không phải quy tắc “nếu blank thì dùng default”.

Nếu ứng dụng yêu cầu chuỗi không rỗng, hãy xác thực giá trị sau bind. Một fallback placeholder không thay thế cho kiểm tra dữ liệu đầu vào.

### Không phải default nào cũng an toàn

Các giá trị dự phòng phù hợp: timeout, số lần retry, chế độ chạy local, URL giả lập khi phát triển. Với mật khẩu, token hoặc endpoint production bắt buộc, đừng đặt giá trị giả để lấp lỗi cấu hình thiếu; nên cho ứng dụng báo lỗi rõ ràng.

## 3. Lỗi không phân giải được: tham chiếu tới khóa không tồn tại

Ví dụ `application.yml`:

~~~yaml
app:
  payment:
    url: "${PAYMENT_API_URL}"
~~~

Nếu `PAYMENT_API_URL` không được cấp trong môi trường, một thành phần yêu cầu **phân giải bắt buộc** sẽ không thể xác định URL.

Ví dụ bean sử dụng `@Value`:

~~~java
package com.example.placeholderdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentClient {

    private final String endpoint;

    public PaymentClient(@Value("${app.payment.url}") String endpoint) {
        this.endpoint = endpoint;
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

Nếu không có biến môi trường hay nguồn thuộc tính nào cung cấp `PAYMENT_API_URL`, quá trình phân giải có thể báo lỗi dạng:

~~~text
Could not resolve placeholder 'PAYMENT_API_URL' in value "${PAYMENT_API_URL}"
~~~

Trong ứng dụng Spring, thông báo đó có thể nằm sâu bên trong chuỗi exception khi tạo bean, ví dụ `BeanCreationException` hoặc `UnsatisfiedDependencyException`. Vì thế nên tìm **nguyên nhân gốc (root cause)** trong stack trace, thay vì chỉ nhìn exception bọc bên ngoài.

Một tình huống thiếu khóa trực tiếp:

~~~java
@Component
public class ReportService {

    public ReportService(@Value("${report.timeout}") String timeout) {
        // ...
    }
}
~~~

Nếu `report.timeout` không tồn tại và không có default phù hợp, xử lý placeholder bắt buộc tại điểm inject có thể không thành công.

**Lưu ý về thời điểm lỗi:** Spring Boot không nhất thiết kiểm tra và báo lỗi cho tất cả văn bản có dạng placeholder ngay khi đọc file YAML. Một biểu thức có thể chỉ gây vấn đề lúc được truy cập, phân giải hoặc bind bằng cơ chế yêu cầu giá trị hợp lệ.

## 4. Tại sao placeholder đôi khi vẫn còn nguyên văn mà ứng dụng chưa lỗi?

Spring Framework hỗ trợ cả hai cách giải quyết placeholder:

- **Cho phép chưa phân giải:** giữ lại đoạn `${missing.key}` nếu không tìm thấy.
- **Bắt buộc phân giải:** ném exception khi không tìm thấy khóa và không có fallback.

Có thể thấy khác biệt bằng `Environment`:

~~~java
import org.springframework.core.env.Environment;

String nonStrict = environment.resolvePlaceholders(
        "URL=${missing.url}");

String strict = environment.resolveRequiredPlaceholders(
        "URL=${missing.url}");
~~~

Nếu `missing.url` không tồn tại:

~~~text
nonStrict = "URL=${missing.url}"
strict    = lỗi vì thiếu missing.url
~~~

Hai API này được định nghĩa qua `PropertyResolver`/`Environment`. Cách thứ nhất hữu ích khi ứng dụng chủ động chấp nhận chuỗi chưa được thay thế; cách thứ hai phù hợp khi cần fail fast.

Không nên suy ra rằng mọi API đọc property đều xử lý thiếu placeholder giống nhau. Hành vi của `getProperty`, `@Value` và Binder phụ thuộc thời điểm, resolver và các quy tắc tích hợp của Spring.

### Ví dụ kiểm tra rõ ràng bằng Java

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class PlaceholderInspection {

    @Bean
    ApplicationRunner inspect(Environment environment) {
        return args -> {
            String sample = "Current=${missing.key}";

            System.out.println(environment.resolvePlaceholders(sample));

            try {
                System.out.println(
                        environment.resolveRequiredPlaceholders(sample));
            } catch (IllegalArgumentException ex) {
                System.out.println("Required resolution failed: "
                        + ex.getMessage());
            }
        };
    }
}
~~~

Đây là ví dụ minh họa cách xử lý lỗi khi **chủ động gọi resolver**. Trong ứng dụng production, chỉ nên bắt lỗi ở nơi có thể phục hồi hợp lệ; với cấu hình bắt buộc, thường cần báo rõ rồi dừng luồng khởi động thay vì âm thầm dùng dữ liệu chưa hoàn chỉnh.

## 5. Trường hợp thiếu thuộc tính do viết sai tên

Giả sử có cấu hình:

~~~yaml
app:
  external-service:
    base-url: https://service.example.org
~~~

Nhưng trong bean lại dùng:

~~~java
@Value("${app.external.base-url}")
private String endpoint;
~~~

`app.external.base-url` và `app.external-service.base-url` là hai đường dẫn khác nhau. Mặc dù có một URL hợp lệ trong YAML, placeholder đang tìm sai khóa.

Một lỗi tương tự xảy ra khi sai tên biến môi trường:

~~~yaml
app:
  api-key: "${PAYMENT_API_KEY}"
~~~

~~~bash
export PAYMENT_KEY="sample"
~~~

Biến `PAYMENT_KEY` không tự động cung cấp `PAYMENT_API_KEY`. Không thể kết luận “đã export biến” nếu tên biến không khớp biểu thức thực tế.

Các nguyên nhân phổ biến khác:

- File cấu hình nằm ngoài các vị trí mà Spring Boot đang nạp.
- Chỉ định nhầm tên profile, nên tệp `application-prod.yml` không được áp dụng.
- `spring.config.location` đã thay thế các vị trí mặc định, khiến file chứa khóa mong muốn không còn được nạp.
- Một document YAML có `spring.config.activate.on-profile` không khớp profile hiện hành.
- Tên khóa nằm sai cấp vì YAML thụt lề không đúng.
- Một nguồn thuộc tính có ưu tiên cao hơn ghi đè giá trị bằng chuỗi placeholder khác.

Khi chẩn đoán, cần xác định **đường dẫn property**, **nguồn property** và **biểu thức placeholder** đang được xử lý.

## 6. Vòng tham chiếu trực tiếp: một khóa trỏ về chính nó

Lỗi vòng đơn giản nhất:

~~~properties
app.name=${app.name}
~~~

Hoặc trong YAML:

~~~yaml
app:
  name: "${app.name}"
~~~

Ý định “lấy `app.name` từ nơi khác” không được biểu đạt đúng, vì thuộc tính hiện tại đang tham chiếu chính nó. Nếu chính giá trị đó được resolver chọn để giải quyết `app.name`, quá trình diễn ra về mặt logic như sau:

~~~text
Cần giải quyết app.name
  → đọc giá trị: ${app.name}
  → lại cần giải quyết app.name
  → lại đọc giá trị: ${app.name}
  → ...
~~~

Spring có cơ chế phát hiện tình huống này và báo lỗi circular placeholder reference thay vì đi vào vòng lặp vô hạn.

Thông báo thường mang ý nghĩa:

~~~text
Circular placeholder reference 'app.name' in property definitions
~~~

Câu chữ và exception bao ngoài có thể khác nhau giữa các phiên bản hoặc đường đi trong framework, nhưng nguyên nhân là **chuỗi thay thế placeholder quay lại tên thuộc tính đã có trên đường phân giải**.

### Mặc định không chữa được tự tham chiếu

Ví dụ:

~~~properties
app.name=${app.name:my-app}
~~~

Nếu resolver đã thấy `app.name` tồn tại và giá trị ấy tham chiếu lại `app.name`, phần `my-app` không tự động cắt vòng lặp. Fallback sau dấu hai chấm áp dụng khi **không tìm thấy** thuộc tính; ở đây thuộc tính đang tồn tại nhưng tự tham chiếu.

Cách sửa đúng là dùng **một khóa nguồn khác**, hoặc bỏ hẳn self-reference:

~~~properties
app.name=${APP_NAME:my-app}
~~~

Trong phiên bản này, `APP_NAME` là tên cấu hình khác và `my-app` là giá trị dự phòng khi khóa nguồn vắng mặt.

## 7. Vòng tham chiếu gián tiếp giữa nhiều thuộc tính

Một vòng không nhất thiết xuất hiện trong cùng dòng. Ví dụ:

~~~yaml
app:
  api-url: "${app.gateway-url}"
  gateway-url: "${app.api-url}"
~~~

Quá trình phân giải:

~~~text
app.api-url
   ↓
app.gateway-url
   ↓
app.api-url
   ↓
vòng tham chiếu
~~~

Hai thuộc tính đều tồn tại, nên đây không phải lỗi “không tìm thấy khóa”. Vấn đề là **không có giá trị cuối cùng độc lập với các placeholder còn lại**.

Một vòng dài hơn:

~~~properties
service.entrypoint=${service.edge}
service.edge=${service.backend}
service.backend=${service.entrypoint}
~~~

Sơ đồ:

~~~text
service.entrypoint → service.edge
        ↑                  ↓
service.backend ←──────────┘
~~~

Để sửa, cần phá ít nhất một cạnh tham chiếu bằng giá trị thực hoặc một nguồn dữ liệu độc lập:

~~~properties
service.entrypoint=${service.edge}
service.edge=${service.backend}
service.backend=https://backend.example.org
~~~

Lúc này:

~~~text
service.backend    = https://backend.example.org
service.edge       = https://backend.example.org
service.entrypoint = https://backend.example.org
~~~

Cả ba biểu thức có điểm kết thúc, nên không còn vòng.

## 8. Phân biệt tham chiếu vòng với chuỗi tham chiếu hợp lệ

Chuỗi phụ thuộc **không phải** vòng nếu cuối cùng chạm đến một giá trị cụ thể:

~~~yaml
app:
  public-host: gateway.example.org
  base-url: "https://${app.public-host}"
  health-url: "${app.base-url}/health"
~~~

Thứ tự:

~~~text
app.health-url
    → app.base-url
    → app.public-host
    → gateway.example.org
~~~

Giá trị cuối:

~~~text
https://gateway.example.org/health
~~~

Bản thân việc một property tham chiếu property khác là tính năng hữu ích. Lỗi chỉ xảy ra khi có một **chu trình** chưa được giải quyết hoặc một **khóa không tồn tại** ở chuỗi tham chiếu cần được phân giải bắt buộc.

### Default lồng nhau vẫn có thể hợp lệ

~~~yaml
app:
  host: "${APP_HOST:localhost}"
  url: "http://${app.host}:8080"
~~~

Nếu `APP_HOST` thiếu, `app.host` nhận `localhost`; sau đó `app.url` nhận `http://localhost:8080`. Chuỗi này kết thúc nên hợp lệ.

## 9. Lỗi vòng khác với circular dependency của Spring bean

Hai loại lỗi có chữ “circular” nhưng nguyên nhân hoàn toàn khác nhau.

**Vòng placeholder:**

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Đây là lỗi trong **giá trị cấu hình và quá trình resolve property**.

**Vòng phụ thuộc bean:**

~~~java
@Component
class Alpha {
    Alpha(Beta beta) {}
}

@Component
class Beta {
    Beta(Alpha alpha) {}
}
~~~

Đây là lỗi trong **đồ thị phụ thuộc giữa các bean**. Spring Boot có thể báo lỗi tạo bean hoặc phụ thuộc vòng với loại thông báo khác.

Thuộc tính `spring.main.allow-circular-references` liên quan một số trường hợp vòng phụ thuộc **bean**, không phải giải pháp cho các giá trị `app.a=${app.b}` và `app.b=${app.a}`. Thay đổi thuộc tính đó không tạo ra giá trị cấu hình thực để kết thúc vòng placeholder.

Để xử lý vòng placeholder, phải sửa **đường tham chiếu giữa các property**.

## 10. Ví dụ Spring Boot với cấu hình đúng và sai

Tạo dự án Spring Boot có dependency `spring-boot-starter` và lớp main:

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PlaceholderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
~~~

Tạo lớp đọc cấu hình:

~~~java
package com.example.placeholderdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoConfiguration {

    @Bean
    ApplicationRunner showGreeting(
            @Value("${demo.greeting}") String greeting) {

        return args -> System.out.println("Greeting: " + greeting);
    }
}
~~~

### 10.1. Trường hợp hợp lệ

Trong `src/main/resources/application.yml`:

~~~yaml
demo:
  user: "Spring"
  greeting: "Xin chào, ${demo.user}!"
~~~

Chạy ứng dụng, dòng in ra:

~~~text
Greeting: Xin chào, Spring!
~~~

### 10.2. Trường hợp thiếu placeholder

Thay file thành:

~~~yaml
demo:
  greeting: "Xin chào, ${demo.user}!"
~~~

Nếu `demo.user` không được cung cấp bởi nguồn khác, việc inject `@Value("${demo.greeting}")` yêu cầu phân giải biểu thức lồng nhau nhưng không có giá trị cho `demo.user`, nên context có thể không khởi tạo được bean và báo lỗi thiếu placeholder.

Sửa theo một trong hai hướng:

~~~yaml
demo:
  user: Spring
  greeting: "Xin chào, ${demo.user}!"
~~~

Hoặc:

~~~yaml
demo:
  greeting: "Xin chào, ${demo.user:Khách}!"
~~~

Cách thứ nhất khai báo nguồn; cách thứ hai cung cấp mặc định hợp lệ.

### 10.3. Trường hợp vòng tham chiếu

~~~yaml
demo:
  user: "${demo.greeting}"
  greeting: "Xin chào, ${demo.user}!"
~~~

Lúc giải quyết `demo.greeting`, Spring cần `demo.user`; giá trị của `demo.user` lại cần `demo.greeting`. Để phá vòng:

~~~yaml
demo:
  user: "Spring"
  greeting: "Xin chào, ${demo.user}!"
~~~

Sau đó chạy lại, việc phân giải có điểm kết thúc.

## 11. Lỗi có thể xuất hiện ở các thời điểm khác nhau

Điều này đặc biệt quan trọng khi đọc log Spring Boot.

| Vị trí sử dụng | Khi nào placeholder được xử lý | Biểu hiện có thể gặp |
| --- | --- | --- |
| `@Value("${missing}")` | Trong quá trình tạo/inject bean | Lỗi tạo bean, nguyên nhân gốc do không resolve được |
| `Environment.resolveRequiredPlaceholders(...)` | Khi mã chủ động gọi hàm | `IllegalArgumentException` hoặc lỗi phân giải phù hợp |
| `Environment.resolvePlaceholders(...)` | Khi mã chủ động gọi hàm | Có thể giữ biểu thức thiếu dưới dạng chuỗi |
| `@ConfigurationProperties` | Khi binder lấy giá trị cho field | Có thể phát sinh lỗi bind, chuyển đổi, xác thực hoặc giá trị không mong muốn tùy kiểu |
| Chuỗi placeholder có vòng | Khi resolver đi qua vòng | Lỗi circular placeholder reference |
| File YAML chỉ chứa giá trị chưa dùng | Có thể chưa kích hoạt strict resolution | Chưa chắc lỗi ngay lúc đọc file |

Không nên khẳng định cứ có `${missing}` trong `application.yml` là Spring Boot luôn dừng ngay ở bước parse YAML. YAML parser chủ yếu hiểu cấu trúc dữ liệu; quá trình xử lý placeholder diễn ra ở tầng property resolution/binding. Thời điểm lỗi được báo phụ thuộc việc thuộc tính đó có được dùng hay không và được đọc bằng cơ chế nào.

### Đừng che lỗi ở tầng bean nếu cấu hình là bắt buộc

Ví dụ:

~~~java
@Value("${payment.secret:demo-secret}")
private String secret;
~~~

Cách này có thể làm ứng dụng khởi động khi thiếu secret, nhưng lại dùng một giá trị không phù hợp môi trường thật. Nếu secret bắt buộc, nên yêu cầu cung cấp nó qua cơ chế secrets đáng tin cậy và xác thực cấu hình rõ ràng.

Với cấu hình tùy chọn như `app.batch-size`, fallback `${app.batch-size:100}` thường hợp lý hơn.

## 12. Placeholder trong `@ConfigurationProperties`

Đối với các nhóm thuộc tính, Spring Boot khuyến nghị bind thành một cấu trúc có kiểu. Ví dụ:

~~~yaml
service:
  base-url: "${SERVICE_BASE_URL:http://localhost:8080}"
  connect-timeout: "${SERVICE_CONNECT_TIMEOUT:3s}"
~~~

Tạo record:

~~~java
package com.example.placeholderdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        String baseUrl,
        Duration connectTimeout) {
}
~~~

Trong ứng dụng chính bật quét:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class PlaceholderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
~~~

Cần import `org.springframework.boot.context.properties.ConfigurationPropertiesScan` và các class Spring Boot như trong ví dụ main trước. Khi bind, `base-url` được nối với `baseUrl`; chuỗi `3s` có thể được chuyển thành `Duration`.

Khi cần một thuộc tính **bắt buộc**, có thể dùng Bean Validation trên `@ConfigurationProperties` nếu dự án bổ sung dependency validation và đăng ký phù hợp.

Ví dụ minh họa:

~~~java
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String endpoint) {
}
~~~

Nếu không khai báo giá trị `payment.endpoint`, validation giúp báo rõ lỗi cấu hình bắt buộc. Điều này không đồng nghĩa Bean Validation tự động phát hiện mọi chuỗi placeholder còn sót lại trong mọi đường xử lý; vẫn cần bảo đảm nguồn cấu hình và cơ chế resolve đúng.

### Sử dụng default trong Java khi thích hợp

Một record có thể đặt giá trị mặc định qua cấu trúc Java hoặc một lớp config có khởi tạo field; một số kiểu constructor binding cũng hỗ trợ annotation default theo Spring Boot. Nhưng nếu nhu cầu chỉ là dự phòng một chuỗi cấu hình, `${name:default}` trong file có thể dễ hiểu hơn.

Hãy lựa chọn nơi đặt default dựa trên yêu cầu quản lý cấu hình, tránh cùng lúc tạo nhiều mặc định mâu thuẫn ở YAML, Java và CLI.

## 13. Vòng tham chiếu do nhiều nguồn cấu hình

Placeholder có thể trỏ từ một nguồn sang nguồn khác. Ví dụ:

~~~yaml
# application.yml
app:
  public-url: "https://${app.host}"
~~~

Và giá trị `app.host` đến từ biến môi trường:

~~~bash
export APP_HOST=example.org
~~~

Khi resolver tìm thấy `app.host`, biểu thức được giải quyết thành URL hợp lệ.

Nhưng nếu cấu hình nguồn khác trả về:

~~~text
app.host=${app.public-url}
~~~

thì hai đường dẫn có thể tạo vòng:

~~~text
app.public-url → app.host → app.public-url
~~~

Kết quả cụ thể phụ thuộc `PropertySource` nào thắng theo thứ tự ưu tiên. Nếu một nguồn cao hơn cung cấp giá trị thực như `app.host=example.org`, vòng có thể biến mất đối với đường phân giải có hiệu lực. Ngược lại, nếu nguồn hiệu lực còn chứa biểu thức tự tham chiếu, việc thêm một giá trị thấp hơn chưa chắc sửa được lỗi.

Do đó, khi phân tích vấn đề, đừng chỉ nhìn một file. Hãy xác định **giá trị hiệu lực của từng khóa trong chuỗi tham chiếu**, xét cả tham số CLI, system property, biến môi trường, file theo profile và tài nguyên được import.

## 14. Chẩn đoán lỗi bằng cách lần theo chuỗi tham chiếu

Một quy trình dễ áp dụng khi nhận lỗi:

1. Xác định tên placeholder trong thông báo lỗi, ví dụ `PAYMENT_API_URL`, `app.host` hoặc `app.base-url`.
2. Xác định nơi đoạn tham chiếu được khai báo: YAML, properties, annotation `@Value` hay file import.
3. Xác định tên khóa được yêu cầu có đúng chính tả, đúng cấp và đúng profile hay không.
4. Kiểm tra nguồn nào đang cung cấp giá trị hiệu lực cho khóa đó.
5. Nếu thông báo là vòng tham chiếu, lần theo chuỗi `A → B → C → A` và chọn một điểm làm **giá trị gốc độc lập**.
6. Sau khi sửa cấu hình, chạy lại và quan sát giá trị cần thiết bằng API phù hợp.

Ví dụ thông báo:

~~~text
Could not resolve placeholder 'app.gateway.host'
~~~

Hãy tìm các biểu thức `${app.gateway.host}` và cấu hình `app.gateway.host` tại các nguồn có hiệu lực. Nếu tài liệu định nghĩa `app.gateway.url` thay vì `app.gateway.host`, vấn đề có thể đơn giản là dùng sai tên.

Với thông báo:

~~~text
Circular placeholder reference 'app.a' in property definitions
~~~

Hãy ghi lại giá trị `app.a`, rồi ghi các khóa mà nó tham chiếu, tiếp tục cho đến lúc đường đi lặp lại. **Không nên thêm default tùy ý vào từng dòng** khi vẫn giữ nguyên vòng.

### Ví dụ truy vết thủ công

~~~properties
app.api=${app.edge}
app.edge=${app.internal}
app.internal=${app.api}
~~~

Ghi chuỗi:

~~~text
app.api
  ↳ app.edge
      ↳ app.internal
          ↳ app.api  ← đã xuất hiện trước đó
~~~

Sửa một thuộc tính thành:

~~~properties
app.internal=https://internal.example.org
~~~

Sự thay đổi này loại vòng vì `app.internal` đã có một điểm kết thúc độc lập.

## 15. Quan sát nguồn và giá trị cấu hình

### 15.1. Dùng `Environment`

Có thể kiểm tra một thuộc tính không chứa thông tin nhạy cảm:

~~~java
@Bean
ApplicationRunner inspectConfig(Environment env) {
    return args -> {
        System.out.println(
                "app.host=" + env.getProperty("app.host"));

        System.out.println(
                "app.base-url=" + env.getProperty("app.base-url"));
    };
}
~~~

Đoạn này đặt trong lớp `@Configuration` hoặc `@SpringBootApplication` với các import:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
~~~

Nếu truy cập một giá trị dẫn đến lỗi phân giải, bạn sẽ thấy exception tại thời điểm đó. Đừng tự động bắt mọi exception rồi coi là “cấu hình hợp lệ”; đối với cấu hình bắt buộc, lỗi nên được hiển thị rõ để xử lý.

### 15.2. Kiểm tra biến môi trường

Linux/macOS:

~~~bash
printenv PAYMENT_API_URL
~~~

Windows PowerShell:

~~~powershell
Get-Item Env:PAYMENT_API_URL
~~~

Kiểm tra biến trong đúng môi trường của tiến trình ứng dụng. Việc một biến tồn tại trong terminal cá nhân không chứng minh rằng dịch vụ chạy bằng systemd, Docker hoặc CI/CD đã nhận cùng biến đó.

### 15.3. Xem profile đang hoạt động

~~~java
System.out.println(
        java.util.Arrays.toString(env.getActiveProfiles()));
~~~

Nếu chỉ có `dev` trong khi giá trị được định nghĩa tại `application-prod.yml`, hãy kiểm tra lựa chọn profile trước khi chỉnh biểu thức placeholder.

### 15.4. Actuator và log

Nếu ứng dụng đã dùng Spring Boot Actuator, endpoint `env` hoặc `configprops` có thể hỗ trợ truy vết nguồn hoặc kết quả bind cấu hình, khi được bật và bảo vệ thích hợp. Không nên mở công khai endpoint chứa thông tin cấu hình nhạy cảm.

Log khởi động và stack trace thường đủ để phát hiện tên placeholder thiếu hoặc vòng tham chiếu. Với trace xử lý Config Data, có thể bật logging chi tiết trong môi trường phát triển để biết các file được nạp. Việc bật log không sửa bản chất lỗi; nó chỉ giúp xác định nguồn cấu hình hiệu lực.

## 16. Các trường hợp cần phân biệt thêm

### 16.1. Không tìm thấy location không giống thiếu placeholder

Ví dụ:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

Nếu tệp bắt buộc không tồn tại, Spring Boot có thể báo `ConfigDataLocationNotFoundException`. Đây là lỗi **không tìm được tài nguyên config data**. Nó khác với việc tài nguyên đã được nạp thành công nhưng trong đó có `${PAYMENT_API_URL}` không tìm được giá trị.

Tiền tố `optional:` của `spring.config.import` giúp bỏ qua location không tồn tại; nó **không** tự tạo giá trị cho mọi placeholder bên trong tài nguyên được nạp.

### 16.2. Tham chiếu vòng placeholder không phải vòng trong cấu hình profile

Ví dụ `spring.profiles.active` kích hoạt `prod`, còn YAML có document cho `prod`, chưa đủ để gọi đó là vòng placeholder. Chỉ khi chuỗi `${...}` quay lại chính thuộc tính đang giải quyết mới là vòng placeholder.

Có các quy tắc riêng về nơi được phép đặt `spring.profiles.active` và `spring.profiles.include` trong Spring Boot; chúng không thay thế quy tắc phát hiện vòng tham chiếu property.

### 16.3. Placeholder mặc định không giống mặc định Java

~~~java
@Value("${app.retry-count:3}")
private int retryCount;
~~~

Ở đây Spring phân giải placeholder rồi chuyển giá trị cho trường `int`. Nhưng:

~~~java
private int retryCount = 3;
~~~

là khởi tạo field theo Java. Hai cách có thể cho cùng giá trị ở một trường hợp, nhưng cơ chế khác nhau, đặc biệt khi có nguồn cấu hình ghi đè hoặc khi bean được tạo theo cách khác.

### 16.4. Tên khóa có phân biệt cú pháp

Viết `${app.service-url}` theo kiểu chuẩn giúp tương thích tốt với quy tắc relaxed binding. Một tên như `${app.serviceUrl}` có thể được xử lý khác ở một số nguồn. Khi một placeholder tưởng chừng tồn tại nhưng không được tìm thấy, kiểm tra tên canonical và cách nguồn cung cấp thuộc tính.

### 16.5. Placeholder trong chuỗi log hoặc văn bản không tự động được resolve

Một chuỗi có ký tự `${...}` trong dữ liệu nghiệp vụ không tự nhiên biến thành cấu hình nếu không đi qua resolver tương ứng. Ví dụ, một nội dung tĩnh hiển thị ra UI có thể cần giữ nguyên cú pháp này. Chỉ dùng `resolvePlaceholders` khi thực sự muốn nội suy tên thuộc tính.

## 17. Bài tập thực hành

### Bài 1 — Khóa thiếu và fallback

Cho:

~~~yaml
demo:
  host: "${DEMO_HOST:localhost}"
  port: "${DEMO_PORT:9090}"
  url: "http://${demo.host}:${demo.port}/api"
~~~

Nếu không có `DEMO_HOST` và `DEMO_PORT`, `demo.url` nhận giá trị nào?

**Đáp án:** `http://localhost:9090/api`.

### Bài 2 — Tham chiếu thiếu không có default

Cho:

~~~yaml
billing:
  endpoint: "${BILLING_ENDPOINT}"
~~~

Và bean:

~~~java
@Value("${billing.endpoint}")
private String billingEndpoint;
~~~

Không có `BILLING_ENDPOINT` trong môi trường. Hãy dự đoán điều gì xảy ra khi Spring thực hiện phân giải bắt buộc cho bean và nêu hai hướng khắc phục.

**Gợi ý:** cung cấp biến môi trường/nguồn thuộc tính hợp lệ, hoặc sử dụng fallback chỉ khi endpoint dự phòng thực sự an toàn.

### Bài 3 — Phát hiện vòng trực tiếp

~~~properties
demo.name=${demo.name:demo-default}
~~~

Vì sao việc có `demo-default` chưa đủ để bảo đảm hết lỗi?

**Đáp án:** `demo.name` tồn tại và đang tự tham chiếu. Resolver có thể nhận lại `demo.name` thay vì coi là thuộc tính vắng mặt để dùng fallback.

### Bài 4 — Phá vòng ba khóa

~~~yaml
demo:
  a: "${demo.b}"
  b: "${demo.c}"
  c: "${demo.a}"
~~~

Hãy sửa một dòng để `demo.a` cuối cùng nhận `https://api.example.org`, đồng thời giữ tham chiếu giữa hai khóa còn lại.

**Một lời giải:**

~~~yaml
demo:
  a: "${demo.b}"
  b: "${demo.c}"
  c: "https://api.example.org"
~~~

### Bài 5 — Phân biệt hai API

Với chuỗi:

~~~text
Value=${UNDEFINED_KEY}
~~~

Dự đoán kết quả của:

~~~java
env.resolvePlaceholders("Value=${UNDEFINED_KEY}");
env.resolveRequiredPlaceholders("Value=${UNDEFINED_KEY}");
~~~

**Đáp án:** lệnh không strict có thể giữ nguyên placeholder; lệnh required báo lỗi khi không có khóa hoặc default.

### Bài 6 — Ưu tiên nguồn

Có:

~~~yaml
app:
  host: localhost
  url: "https://${app.host}"
~~~

Chạy:

~~~bash
java -jar demo.jar --app.host=api.example.org
~~~

Giá trị `app.url` khi được phân giải là gì?

**Đáp án:** `https://api.example.org`, giả định không nguồn ưu tiên cao hơn nào ghi đè `app.url`.

### Bài 7 — Xác định nguyên nhân từ thông báo

Một lần chạy báo:

~~~text
Could not resolve placeholder 'MAIL_PASSWORD'
~~~

Lần khác báo:

~~~text
Circular placeholder reference 'app.mail-host' in property definitions
~~~

Hãy nêu khác biệt. **Đáp án:** trường hợp đầu cần tìm giá trị cho khóa `MAIL_PASSWORD`; trường hợp sau cần lần theo các thuộc tính tham chiếu `app.mail-host` và phá chu trình. Chỉ thêm một giá trị thấp hơn có thể không giúp nếu nguồn đang thắng vẫn tạo vòng.

## 18. Nguyên tắc thiết kế cấu hình để tránh lỗi

- Đặt tên khóa rõ ràng và nhất quán, ưu tiên canonical kebab-case trong biểu thức placeholder và các file cấu hình.
- Chỉ dùng placeholder khi hai thuộc tính thực sự có quan hệ phụ thuộc; tránh tham chiếu qua nhiều lớp không cần thiết.
- Thiết kế chuỗi tham chiếu có **giá trị gốc độc lập**: giá trị literal, biến môi trường đã được cung cấp hoặc một default hợp lệ.
- Cung cấp fallback cho cấu hình tùy chọn; với cấu hình bắt buộc, cho lỗi xuất hiện rõ trong bootstrap hoặc xác thực.
- Tránh tham chiếu trực tiếp hoặc gián tiếp về chính khóa đang được giải quyết.
- Kiểm tra profile và thứ tự ưu tiên của các nguồn; đừng sửa file không được Spring Boot nạp.
- Phân biệt lỗi placeholder với lỗi thiếu config data location hoặc phụ thuộc vòng giữa các bean.
- Khi gặp sự cố, dựa vào root cause và đường tham chiếu, không chỉ dựa vào thông báo lỗi bọc ngoài.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration: Property Placeholders](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.property-placeholders)
- [Spring Boot 3.3 — Externalized Configuration and Property Source Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework — Property Placeholder Resolution](https://docs.spring.io/spring-framework/reference/core/beans/factory-placeholderconfigurer.html)
