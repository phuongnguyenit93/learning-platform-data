# Phân biệt lỗi liên kết, lỗi chuyển đổi và lỗi vi phạm ràng buộc

Trong Spring Boot Externalized Configuration, một ứng dụng có thể đọc hàng chục hoặc hàng trăm giá trị từ `application.yml`, `application.properties`, tệp theo profile, biến môi trường, JVM system properties hoặc tham số dòng lệnh. Những giá trị này được đưa vào `Environment`, rồi `Binder` của Spring Boot liên kết chúng với `@ConfigurationProperties` để tạo các đối tượng Java có kiểu. Sau đó, nếu được cấu hình, **Bean Validation** kiểm tra các quy tắc như bắt buộc có giá trị, không rỗng hoặc nằm trong phạm vi cho phép.

Khi một ứng dụng không khởi động do cấu hình, ba loại vấn đề thường bị gọi chung là “lỗi validate”: **lỗi liên kết (binding)**, **lỗi chuyển đổi kiểu (conversion)** và **lỗi vi phạm ràng buộc (constraint validation)**. Cách gọi chung đó khiến việc sửa lỗi đi sai hướng: có người thêm `@NotNull` để sửa giá trị `abc` không đổi được sang `int`, có người sửa converter khi vấn đề thật ra là prefix YAML viết sai, và có người bỏ `@Validated` để che một giá trị port nằm ngoài khoảng hợp lệ.

Bài này giải thích chính xác trách nhiệm của từng tầng, mối quan hệ giữa chúng, dấu hiệu trong exception và log, cách đọc `Property`/`Value`/`Origin`/`Reason`, cách tạo ví dụ tái hiện và quy trình gỡ lỗi có thể dùng trong dự án Spring Boot 3.x (Java 17+).

## 1. Ba câu hỏi khác nhau trong một quá trình khởi động

Hãy hình dung cấu hình đầu vào:

~~~yaml
app:
  notification:
    endpoint: https://notify.example.test
    timeout: 2s
    max-retries: 3
    enabled: true
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    URI endpoint,
    Duration timeout,
    int maxRetries,
    boolean enabled
) {}
~~~

Spring Boot cần trả lời lần lượt:

1. **Liên kết (bind):** Các key dưới prefix `app.notification` tương ứng với những thành phần nào của record? Có tạo được object theo cấu trúc Java đó không?
2. **Chuyển đổi (convert):** Chuỗi `2s` có chuyển thành `Duration` không? `3` có thành `int` không? URL có thành `URI` không?
3. **Kiểm tra ràng buộc (validate):** Sau khi có các giá trị đúng kiểu, chúng có thỏa yêu cầu nghiệp vụ không, chẳng hạn `maxRetries >= 0`, `endpoint != null` hoặc `timeout` bắt buộc có mặt?

Ba câu hỏi có liên hệ với nhau nhưng **không phải cùng một lỗi**. Conversion là một công việc nằm trong quá trình binding: khi conversion thất bại, Spring Boot thường báo thông qua một ngoại lệ binding ở lớp ngoài. Validation cũng thường được gọi trong quá trình bind configuration properties, nhưng **lý do thất bại** lại đến từ ràng buộc trên dữ liệu đã có hoặc dữ liệu thiếu.

### Luồng sự kiện

~~~text
Các nguồn cấu hình bên ngoài
  application.yml / application.properties
  profile / import / environment / -D / --args
                    |
                    v
          Environment / PropertySource
                    |
                    v
          Config Data và binder tìm key
                    |
          +---------+-----------+
          |                     |
          v                     v
     Key có thể map?      Cấu trúc key không
     Tên/prefix/shape     khớp target, binder
     phù hợp?             không tạo được object
          |                     |
          v                     v
     Chuyển kiểu              BINDING FAILURE
     String -> Java type
          |
     +----+---------------------+
     |                          |
     v                          v
  Thành công              CONVERSION FAILURE
     |                  (thường bọc trong
     |                    binding exception)
     v
  Object cấu hình
     |
     v
  Bean Validation (nếu được bật)
     |
     +-----> Vi phạm constraint
     |            |
     |            v
     |       VALIDATION FAILURE
     v
  Bean cấu hình sẵn sàng
~~~

**Điều cần nhớ:** tên exception ngoài cùng như `ConfigurationPropertiesBindException` hoặc `BindException` chưa đủ để xác định nguyên nhân. Phải đọc **cause chain**, `Reason`, key lỗi và kiểu đích.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Lỗi liên kết | Lỗi chuyển đổi | Lỗi ràng buộc |
| --- | --- | --- | --- |
| Câu hỏi thất bại | Key/cấu trúc có map được vào model không? | Value có thành kiểu Java yêu cầu không? | Value đã nhận có thỏa rule không? |
| Ví dụ | YAML dùng object, Java yêu cầu list; constructor không bind được | `max-retries=many` nhưng field `int` | `max-retries=-2` nhưng có `@Min(0)` |
| Nguyên nhân gốc | Shape, prefix, accessor, cách đăng ký/constructor, key không phù hợp | Format, converter, kiểu đích, enum, đơn vị | Constraint, điều kiện nghiệp vụ, giá trị bắt buộc |
| Dấu hiệu thường gặp | `BindException`, `Failed to bind properties` | `ConversionFailedException` hoặc nguyên nhân chuyển kiểu được bọc | `BindValidationException` hoặc các validation errors |
| Dữ liệu sai kiểu? | Có thể, do conversion là một phần của bind | Có | Không nhất thiết; có thể hoàn toàn đúng kiểu |
| `@Validated` cần thiết? | Không phải điều kiện phát sinh lỗi bind | Không phải điều kiện phát sinh lỗi convert | Thường cần cho Bean Validation của configuration properties |
| Hướng sửa chính | Sửa tên/shape của cấu hình hoặc model/binding mechanism | Sửa value hoặc converter/type Java | Sửa dữ liệu để đáp ứng rule hoặc sửa rule sai |
| Có thể xảy ra khi startup không? | Có | Có | Có, nếu validation được cấu hình |

Một ví dụ tối giản để ghi nhớ:

~~~properties
# Lỗi mapping/cấu trúc, nếu Java cần List<Server>
app.servers.name=primary

# Lỗi conversion, nếu field cần int
app.max-retries=many

# Lỗi validation, nếu field int và có @Min(0)
app.max-retries=-3
~~~

Ở ví dụ cuối, Java vẫn có thể chuyển `-3` thành số nguyên. Lỗi chỉ xuất hiện ở bước kiểm tra ràng buộc `@Min(0)`. Đừng gọi nó là “lỗi parse số”.

## 3. Bối cảnh: @ConfigurationProperties phải được đăng ký

Trước khi phân loại ba lỗi trên, cần bảo đảm có **configuration properties bean** đúng cách. Chỉ khai báo một record chưa đủ:

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    URI endpoint,
    Duration timeout,
    int maxRetries
) {}
~~~

Đăng ký qua scanning:

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

Hoặc dùng cách đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {}
~~~

Nếu ứng dụng báo `required a bean of type NotificationProperties that could not be found`, trước hết kiểm tra **bean registration**: annotation scan/enable, package, configuration class có được load chưa. **Thiếu bean không đồng nghĩa một constraint trên dữ liệu đã bị vi phạm.** Chưa có bean thì Binder có thể còn chưa đến giai đoạn validate đối tượng.

Với record constructor-bound, tránh thêm `@Component` chỉ để “làm Spring nhìn thấy class”: component construction và configuration properties constructor binding là hai đường tạo object khác nhau.

## 4. Lỗi liên kết (binding) là gì?

**Binding** là quá trình Spring Boot lấy các property có tên thích hợp, xử lý cấu trúc lồng nhau/collection và gán hoặc truyền chúng vào một object Java. Binding có thể dùng setter trên JavaBean mutable hoặc constructor trên record/class immutable.

Những vấn đề liên kết điển hình:

- Cấu trúc YAML không giống target Java: danh sách và object bị nhầm lẫn.
- Đường dẫn nested property không khớp field mà Binder có thể truy cập.
- Kiểu cần setter binding nhưng thiếu constructor/setter phù hợp.
- Constructor binding không tìm được constructor/parameter name cần thiết trong cấu hình phức tạp.
- Định nghĩa unknown fields được yêu cầu kiểm soát nghiêm ngặt, nhưng source có key không bind được.
- Một giá trị không chuyển đổi được, khiến binding dừng (cần phân loại sâu hơn là lỗi conversion).
- Một lỗi validation được bọc bởi exception binding (cần đọc lý do bên trong).

**Binding failure là một nhóm biểu hiện rộng.** Khi thấy từ “bind” trên log, hãy kiểm tra nguyên nhân gốc trước khi quyết định là lỗi shape, conversion hay validation.

### Ví dụ binding do cấu trúc sai

Model mong đợi danh sách:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record GatewayProperties(List<Gateway> gateways) {
    public record Gateway(String name, URI url) {}
}
~~~

Nhưng YAML lại viết một object đơn:

~~~yaml
app:
  gateways:
    name: primary
    url: https://gateway.example.test
~~~

`gateways` ở đây là mapping object, trong khi Java yêu cầu `List<Gateway>`. Tùy đường binding và converter có sẵn, Spring Boot có thể không tạo được danh sách mong muốn và báo lỗi bind, hoặc không bind như dự tính.

Cấu trúc phù hợp là YAML sequence:

~~~yaml
app:
  gateways:
    - name: primary
      url: https://gateway.example.test
    - name: backup
      url: https://backup.example.test
~~~

Trong `.properties`, danh sách cần chỉ số:

~~~properties
app.gateways[0].name=primary
app.gateways[0].url=https://gateway.example.test
app.gateways[1].name=backup
app.gateways[1].url=https://backup.example.test
~~~

Không sửa loại lỗi này bằng cách thêm `@Min` hay `@NotNull`: chúng không làm một mapping YAML tự biến thành sequence.

## 5. Cấu trúc lồng nhau bị sai cấp

Giả sử Java yêu cầu:

~~~java
@ConfigurationProperties(prefix = "app")
public record MailProperties(
    Mail mail
) {
    public record Mail(
        String host,
        Security security
    ) {}
    public record Security(
        boolean tlsEnabled,
        int port
    ) {}
}
~~~

YAML đúng:

~~~yaml
app:
  mail:
    host: smtp.example.test
    security:
      tls-enabled: true
      port: 587
~~~

YAML sai cấp:

~~~yaml
app:
  mail:
    host: smtp.example.test
    tls-enabled: true
    port: 587
~~~

Các key `tls-enabled` và `port` không nằm dưới `app.mail.security`. Nếu Binder cho phép các field không được nhận diện bị bỏ qua, ứng dụng thậm chí có thể khởi động nhưng `security` là `null` hoặc có giá trị không như mong đợi. Nếu strict binding hoặc validation được cấu hình, lỗi có thể phát lộ khi khởi động.

**Rất quan trọng:** “không bind được field mong muốn” không phải lúc nào cũng làm startup thất bại. Một số trường hợp thiếu key hoặc unknown key được bỏ qua theo cấu hình mặc định; khi đó cần validation và kiểm thử để phát hiện.

### Tên key và relaxed binding

Spring Boot hỗ trợ relaxed binding, ví dụ:

~~~properties
app.mail.security.tls-enabled=true
~~~

có thể map sang `boolean tlsEnabled` trong nested record phù hợp.

Nhưng relaxed binding không có nghĩa tự sửa mọi chính tả:

~~~properties
app.mail.securty.tls-enabled=true
~~~

`securty` khác `security`; thiếu chữ `i` không được Binder đoán lại. Nếu key bắt buộc, dùng validation để làm lỗi thiếu property xuất hiện rõ thay vì âm thầm nhận giá trị mặc định không mong muốn.

## 6. Unknown properties và ignoreUnknownFields

`@ConfigurationProperties` có thuộc tính `ignoreUnknownFields`. Cấu hình mặc định của annotation là **bỏ qua các field không xác định** trong nhiều tình huống binding, không phải mặc định fail mọi key sai chính tả.

Ví dụ:

~~~java
@ConfigurationProperties(
    prefix = "app.mail",
    ignoreUnknownFields = false
)
public class MailProperties {
    private String host;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }
}
~~~

File:

~~~properties
app.mail.host=smtp.example.test
app.mail.hots=smtp.other.example.test
~~~

Key `hots` là unknown property so với JavaBean chỉ có `host`. Với strict binding thích hợp, Binder có thể báo lỗi về những property không được bind.

Trong thực tế, `ignoreUnknownFields=false` là công cụ giúp phát hiện cấu hình thừa/sai tên trong một prefix mà class muốn kiểm soát. Tuy nhiên, không áp dụng rộng một cách thiếu cân nhắc: nếu một prefix được chia sẻ giữa nhiều cấu hình khác nhau, strict binding có thể từ chối key thực sự hợp lệ cho thành phần khác.

### ignoreUnknownFields khác ignoreInvalidFields

`@ConfigurationProperties` còn có `ignoreInvalidFields`, mặc định là `false`. Hai ý nghĩa không giống nhau:

- **Unknown field:** nguồn có key mà model không nhận; ví dụ `app.mail.hots`.
- **Invalid field:** key đúng nhưng value không bind được theo kiểu cần thiết; ví dụ `app.mail.port=abc` với field `int port`.

Không nên bật `ignoreInvalidFields=true` chỉ để “cho ứng dụng chạy” khi có kiểu dữ liệu sai. Làm vậy có thể khiến đối tượng thiếu dữ liệu hoặc giữ default không phù hợp, rồi lỗi nghiệp vụ xuất hiện muộn.

## 7. Lỗi chuyển đổi kiểu (conversion) là gì?

Lỗi conversion xảy ra khi Binder **đã tìm đúng đường dẫn property**, nhưng value không thể chuyển sang kiểu Java target.

Những phép chuyển phổ biến:

| Source value | Target type | Kết quả mong đợi |
| --- | --- | --- |
| `"3"` | `int` / `Integer` | 3 |
| `"true"` | `boolean` / `Boolean` | true |
| `"750ms"` | `Duration` | 750 mili giây |
| `"10MB"` | `DataSize` | 10 megabyte theo quy tắc DataSize |
| `"https://api.example.test"` | `URI` | URI hợp lệ |
| `"EMAIL"` | `Channel` enum | `Channel.EMAIL` nếu định nghĩa đúng |

Các lỗi chuyển kiểu rõ ràng:

~~~properties
app.notification.max-retries=many
app.notification.timeout=soon
app.notification.enabled=maybe
~~~

Nếu Java yêu cầu `int`, `Duration`, `boolean`, những value trên không phù hợp với converter thông dụng và có thể khiến startup thất bại.

### Ví dụ có thể tái hiện

Model:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

Cấu hình sai:

~~~properties
app.retry.max-attempts=three
app.retry.backoff=250ms
~~~

Key `app.retry.max-attempts` **đúng tên** và đi vào đúng component `maxAttempts`. Nhưng chuỗi `three` không chuyển thành `int`. Thông báo có thể chứa kiểu đích `java.lang.Integer` hoặc `int` và nguyên nhân như không parse được số.

Sửa bằng dữ liệu đúng kiểu:

~~~properties
app.retry.max-attempts=3
app.retry.backoff=250ms
~~~

**Không cần đổi prefix, không cần bỏ @Validated, không cần thay constructor** nếu lỗi nằm đúng ở conversion value `three`.

## 8. Cách đọc exception của conversion

Trong stack trace Spring Boot, một lỗi chuyển kiểu có thể xuất hiện qua nhiều lớp:

~~~text
BeanCreationException / ConfigurationPropertiesBindException
  └─ BindException: Failed to bind properties under 'app.retry'
       └─ ConversionFailedException
            └─ NumberFormatException
~~~

Đây là **minh họa cause chain**, không phải cam kết mọi phiên bản sẽ in đúng bốn lớp hoặc đúng thứ tự. Tùy kiểu dữ liệu, converter, cách đăng ký bean và Spring Boot version, loại exception cụ thể có thể khác.

Tập trung vào ba thông tin:

1. **Tên key:** property nào không convert được?
2. **Kiểu đích:** `int`, `Duration`, enum hay custom type nào?
3. **Giá trị nguồn:** chuỗi nào đang được cố chuyển? Value đó lấy từ file/profiles/env/CLI nào?

Ví dụ thông báo (minh họa):

~~~text
Failed to bind properties under 'app.retry.max-attempts'
to int:

    Property: app.retry.max-attempts
    Value: "three"
    Origin: class path resource [application.properties] - 1:24
    Reason: failed to convert java.lang.String to int
~~~

`Origin`, số dòng và cách trình bày tùy Spring Boot và nguồn dữ liệu. Nếu output cho biết dòng trong `application.properties` hoặc giá trị biến môi trường, hãy dùng thông tin đó để sửa **nguồn đang có ưu tiên thực tế**, không chỉ sửa một tệp thấp ưu tiên mà bạn đang mở trong IDE.

## 9. Enum, Duration, DataSize và kiểu tự định nghĩa

Conversion không chỉ là đổi chuỗi thành số.

### Enum

~~~java
public enum DeliveryMode {
    SYNC, ASYNC
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(DeliveryMode mode) {}
~~~

~~~properties
app.delivery.mode=ASYNC
~~~

là value có thể được nhận theo cơ chế binding phù hợp. Nhưng:

~~~properties
app.delivery.mode=SUPERFAST
~~~

không có constant tương ứng. Đây là lỗi chuyển kiểu hoặc binding value, **không phải `@Pattern` validation** nếu model chỉ yêu cầu enum.

### Duration

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

~~~properties
app.client.timeout=1500ms
~~~

là ví dụ hợp lệ. Ngược lại, `app.client.timeout=tomorrow` không có định dạng `Duration` mà converter Spring Boot thông thường hiểu.

### DataSize

~~~java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxSize) {}
~~~

~~~properties
app.upload.max-size=10MB
~~~

có thể bind qua conversion dành cho `DataSize`. `app.upload.max-size=very-big` có thể thất bại khi convert.

### Custom type

Nếu ứng dụng tạo một record:

~~~java
public record RegionCode(String value) {}
~~~

và typed properties yêu cầu `RegionCode`, hãy bảo đảm có cơ chế chuyển đổi phù hợp. Với custom conversion dành cho configuration properties, Spring Boot hỗ trợ converter được qualify bằng `@ConfigurationPropertiesBinding`.

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RegionConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode> regionCodeConverter() {
        return RegionCode::new;
    }
}
~~~

Đây là ví dụ cho trường hợp cần custom converter. Trong Spring Boot 3.x, static factory method cho converter binding được khuyến nghị để tránh kéo configuration class khởi tạo quá sớm.

Nếu converter không có hoặc ném exception khi gặp input không hợp lệ, lỗi có thể nổi lên ở giai đoạn conversion. Không cần thêm `@NotBlank` trên một `RegionCode` chỉ để sửa việc Binder hoàn toàn không biết cách tạo `RegionCode`.

## 10. Lỗi ràng buộc (constraint validation) là gì?

Sau khi Binder có dữ liệu đúng kiểu, application vẫn cần kiểm tra **giá trị hợp lệ theo quy tắc**. Đây là nhiệm vụ của Bean Validation nếu bạn đã cấu hình sử dụng nó.

Ví dụ:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    @NotNull URI endpoint,
    @NotNull Duration timeout,
    @Min(0) @Max(10) int maxRetries
) {}
~~~

File:

~~~properties
app.notification.endpoint=https://notify.example.test
app.notification.timeout=2s
app.notification.max-retries=-3
~~~

Ở đây `-3` **chuyển được sang int**, nhưng vi phạm `@Min(0)`. Do đó nguyên nhân chính là **validation failure**, không phải conversion failure.

Sửa value thành số không âm và không vượt 10:

~~~properties
app.notification.max-retries=3
~~~

Hoặc nếu nghiệp vụ thực sự cho phép giá trị âm (không phổ biến với retry count), hãy xem lại quy tắc validation. Không nên bỏ constraint chỉ để tắt lỗi mà không xác nhận contract.

## 11. Bật Bean Validation đúng cách

Trong Spring Boot 3.x, các constraint phổ biến thuộc namespace `jakarta.validation.constraints.*`. Project cần validator implementation/provider phù hợp; với Spring Boot thường dùng starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Giả sử project đã sử dụng Spring Boot dependency management tương ứng, không cần hardcode version riêng cho starter trong ví dụ.

Bean config:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
    @NotBlank String host,
    @Positive int port
) {}
~~~

`@Validated` trên root configuration properties bean giúp kích hoạt kiểm tra ràng buộc qua cơ chế binding/validation thích hợp. Có provider thì mới có implementation thực thi Bean Validation; nếu thiếu dependency, không nên kỳ vọng các annotation `@NotBlank` hoặc `@Positive` sẽ tự hoạt động.

Với Spring Boot 2.x cũ sử dụng `javax.validation.*` ở một số dòng phiên bản, cần theo đúng namespace tương thích của dự án. Không trộn imports `javax.validation` và `jakarta.validation` một cách tùy tiện.

## 12. @NotNull, @NotBlank, @Min: chọn đúng ràng buộc

| Constraint | Mục đích chính | Ví dụ phù hợp |
| --- | --- | --- |
| `@NotNull` | Giá trị phải khác null | `URI endpoint`, `Duration timeout` |
| `@NotBlank` | String không null/rỗng/chỉ toàn whitespace | `String host` |
| `@NotEmpty` | String, array, collection hoặc map không được rỗng | `List<String> recipients` |
| `@Min(0)` | Số phải lớn hơn hoặc bằng 0 | Retry count |
| `@Max(65535)` | Số không vượt giá trị trên | Port (kết hợp `@Min(1)`) |
| `@Positive` | Số dương | Pool size |
| `@Pattern(...)` | Chuỗi khớp biểu thức chính quy | Một code có định dạng cụ thể |
| `@Size(min=..., max=...)` | Giới hạn kích thước của String/collection/map/array | Giới hạn số recipients |

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @NotBlank String name,
    @Min(1) @Max(32) int concurrency,
    @NotNull Duration pollInterval
) {}
~~~

Các value:

~~~properties
app.worker.name=consumer-1
app.worker.concurrency=0
app.worker.poll-interval=2s
~~~

`concurrency=0` chuyển sang `int` thành công nhưng vi phạm `@Min(1)`. Trong khi `concurrency=abc` không chuyển được sang `int` nên là lỗi conversion trước khi có thể kiểm tra ràng buộc số học trên giá trị đã bind.

### Một annotation không áp dụng cho mọi kiểu

Không đặt `@NotBlank` trên `int` hoặc `Duration` như một cách “bắt buộc có”. `@NotBlank` dành cho `CharSequence`. Nếu muốn ép số dương, dùng `@Positive`/`@Min`; nếu Duration bắt buộc có, dùng `@NotNull` và ràng buộc custom hoặc cơ chế tương thích khi cần giới hạn độ dài thời gian.

Một constraint đặt sai kiểu cũng có thể tạo ra lỗi cấu hình validator chứ không phải “property value không hợp lệ” thông thường. Hãy chọn constraint theo kiểu Java.

## 13. Missing property: có thể là lỗi validation hoặc không lỗi

Thiếu key không mặc nhiên là lỗi conversion.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app")
public record FeatureProperties(
    String endpoint,
    Integer maxRetries
) {}
~~~

Nếu không có `app.endpoint` và `app.max-retries`, Binder có thể tạo object với các component null tùy cấu hình constructor binding. **Không có constraint bắt buộc**, ứng dụng có thể khởi động rồi chỉ lỗi khi service truy cập giá trị null.

Thêm ràng buộc:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record FeatureProperties(
    @NotBlank String endpoint,
    @NotNull Integer maxRetries
) {}
~~~

khi validation hoạt động, dữ liệu thiếu có thể gây vi phạm constraint, giúp ứng dụng **fail fast** lúc startup.

Với primitive như `int`, không thể dựa vào `@NotNull` để bắt thiếu vì primitive không chứa null. Nếu muốn bắt buộc một cấu hình phải được khai báo, dùng wrapper `Integer` + `@NotNull` hoặc một cơ chế phù hợp khác.

### Missing khác empty khác invalid

~~~properties
# Case A: không có key
# app.worker.name không được khai báo

# Case B: có key nhưng value rỗng
app.worker.name=

# Case C: có value nhưng không hợp với ràng buộc
app.worker.name=   
~~~

Với `String name` và `@NotBlank`, cả trường hợp rỗng hoặc chỉ khoảng trắng đều không phù hợp. Nếu hoàn toàn thiếu key và model nhận null, `@NotBlank` cũng không cho phép null.

Trong khi đó, nếu Java cần `int concurrency` và cấu hình `app.worker.concurrency=abc`, lỗi chính lại là conversion. Cần sửa input thành số chứ không chỉ thêm `@NotNull`.

## 14. Validation object lồng nhau bằng @Valid

Một lỗi thường bị bỏ sót là root đã annotate `@Validated` nhưng các field bên trong object lồng nhau chưa được kiểm tra như mong đợi.

Ví dụ YAML:

~~~yaml
app:
  outbound:
    base-url: https://api.example.test
    retry:
      max-attempts: -1
      backoff: 200ms
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    @NotNull URI baseUrl,
    @NotNull @Valid Retry retry
) {
    public record Retry(
        @Min(0) int maxAttempts,
        @NotNull Duration backoff
    ) {}
}
~~~

Root `OutboundProperties` được validate, và `@Valid` yêu cầu cascade sang nested `Retry` theo cơ chế Bean Validation. Nếu `max-attempts=-1`, giá trị chuyển sang `int` thành công nhưng nested constraint thất bại.

Nếu thiếu `retry` hoàn toàn, `@NotNull` trên field `retry` phát hiện null. Nếu nested object có mặt nhưng thiếu `backoff`, `@Valid` cùng `@NotNull` trên nested field có thể phát hiện.

### List<@Valid Item> và Map nested

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record GatewayCatalog(
    @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
        @NotBlank String id,
        @NotNull URI url,
        @Min(1) int weight
    ) {}
}
~~~

Nếu `app.gateways[1].id` rỗng hoặc `weight=0`, Bean Validation có thể báo lỗi ràng buộc tại phần tử tương ứng khi provider và cascade được cấu hình đúng.

Một cấu trúc có `Map<String, @Valid Target>` cũng có thể được kiểm tra theo phần tử value. Đừng nghĩ `@Validated` một mình tự khám phá mọi constraint nằm sâu trong cây object mà không có cascade phù hợp.

## 15. Validation khác conversion trong nested list

Dùng model `GatewayCatalog` từ trên. Hai source:

**Trường hợp chuyển kiểu sai:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://api.example.test
app.gateways[0].weight=heavy
~~~

`weight` phải là `int` nhưng có value `heavy`, nên lỗi có nguyên nhân chuyển kiểu.

**Trường hợp ràng buộc sai:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://api.example.test
app.gateways[0].weight=0
~~~

`0` là `int` hợp lệ, nhưng vi phạm `@Min(1)`.

**Trường hợp thiếu field bắt buộc:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].weight=2
~~~

Nếu `url` không có và record có `@NotNull URI url`, validation có thể thất bại sau binding (giả định object được tạo và cascade chạy).

**Trường hợp shape sai:**

~~~properties
app.gateways.id=primary
~~~

Source không chỉ định list index. Đây trước hết là vấn đề cấu trúc binding; không phải kiểu của `weight` hay ràng buộc `@Min`.

Mỗi trường hợp cần một cách sửa khác nhau, dù log startup có thể cùng bắt đầu bằng “Failed to bind properties”.

## 16. Khi nào lỗi YAML không thuộc cả ba nhóm trên?

Một ngoại lệ quan trọng: không phải tất cả lỗi externalized configuration đều đi vào Binder.

Ví dụ YAML sai cú pháp:

~~~yaml
app:
  retry:
    max-attempts: [1, 2
~~~

Sequence `[1, 2` không đóng ngoặc, nên parser YAML có thể thất bại **trước khi Spring Boot có được danh sách key/value** để bind vào Java.

Hoặc YAML có hai dòng trùng key theo cách parser không chấp nhận:

~~~yaml
app:
  enabled: true
  enabled: false
~~~

Tùy parser/cấu hình, quá trình nạp YAML có thể báo lỗi duplicate key trước binding. Lúc này sửa lại cấu trúc file chứ không đổi constraint `@Min` hay converter `String -> Integer`.

Các vấn đề khác có thể xảy ra trước binding:

- `spring.config.import` trỏ đến location bắt buộc không tồn tại.
- Tệp cấu hình không được phép truy cập hoặc encoding không phù hợp.
- Một tên profile hoặc tài liệu Config Data vi phạm quy tắc vị trí của Spring Boot.
- Placeholder không được giải quyết trong một ngữ cảnh yêu cầu giá trị hợp lệ.
- Cấu hình bị xung đột giữa các nguồn hoặc lỗi load một PropertySource tùy chỉnh.

**Quy trình chẩn đoán đúng bắt đầu từ xác định tầng lỗi**: parser/load Config Data, binding, conversion, validation, rồi mới đến startup bean/nghiệp vụ.

## 17. Đọc thông báo startup: Property, Value, Origin, Reason

Spring Boot có cơ chế failure analysis giúp nhiều lỗi cấu hình xuất hiện dưới dạng khối mô tả:

~~~text
Failed to bind properties under 'app.retry' to RetryProperties:

    Property: app.retry.max-attempts
    Value: "many"
    Origin: class path resource [application.yml] - 4:19
    Reason: failed to convert java.lang.String to int
~~~

Đây là **dạng mô phỏng** để học cách đọc log. Nội dung chính xác phụ thuộc phiên bản Boot, converter, kiểu bean và nguồn cấu hình. Dùng bốn thành phần:

- **Property:** key nào được Binder xét. Kiểm đúng prefix, chữ viết, dấu gạch và index nếu là list.
- **Value:** value thực tế đã tới Binder, không nhất thiết là value bạn đang nhìn trong file mở ở IDE.
- **Origin:** nguồn file/dòng hoặc thông tin nguồn khác. Nếu có Origin, dùng nó để truy vị trí cần sửa.
- **Reason:** lý do cuối cùng, đặc biệt quan trọng để tách conversion và validation.

Đối với một số nguồn như environment variable hoặc nguồn do code cung cấp, origin có thể khác định dạng file/dòng. Không phải mọi failure đều có một khối 4 dòng hoàn chỉnh.

### Vấn đề log có thể chứa secret

Nếu property là password, API key hoặc token, thông tin value trong log/debug có thể nhạy cảm dù một số cơ chế đã sanitize. Không paste nguyên log chứa secret vào issue công khai. Chỉ lưu thông tin tối thiểu: tên key, loại lỗi, kiểu đích, nguồn và thông điệp đã che value nhạy cảm.

## 18. Ngoại lệ ngoài cùng và nguyên nhân gốc

Một startup failure có thể được bọc nhiều lớp:

~~~text
org.springframework.beans.factory.BeanCreationException
  -> org.springframework.boot.context.properties.ConfigurationPropertiesBindException
     -> org.springframework.boot.context.properties.bind.BindException
        -> ...
~~~

Phần `...` có thể là lỗi conversion, lỗi validation hoặc lỗi do cơ chế tạo object. **Đừng dùng quy tắc “cứ thấy BindException thì là sai YAML”**.

Các tên thường gặp:

| Tên ngoại lệ/khái niệm | Ý nghĩa cần hiểu |
| --- | --- |
| `BeanCreationException` | Spring không tạo được bean; rất rộng, không chỉ lỗi config |
| `ConfigurationPropertiesBindException` | Binding configuration properties bean thất bại; xem cause |
| `BindException` của Spring Boot Binder | Lỗi khi bind một prefix/value vào target |
| `ConversionFailedException` | Dấu hiệu chuyển kiểu thất bại, có thể được bọc |
| `BindValidationException` | Dấu hiệu lỗi validation trong quá trình bind |
| `NumberFormatException` | Có thể là nguyên nhân sâu của conversion từ String sang số |
| `ConstraintViolationException` | Một biểu hiện của Bean Validation ở nhiều ngữ cảnh; không phải mọi config validation failure đều mang tên này |
| `IllegalArgumentException` | Rất rộng; có thể do converter, constructor, custom validator hoặc logic khác |

Trong ứng dụng Spring, còn có lớp `BindException` thuộc các package khác nhau cho những cơ chế data binding khác; không nên lẫn ngoại lệ **Spring Boot configuration properties Binder** với lỗi bind form/request của Spring MVC.

Khi kiểm exception, đọc **tên package đầy đủ**, cause chain và chi tiết failure analyzer.

## 19. Triệu chứng tương tự, nguyên nhân khác

Giả sử ứng dụng in:

~~~text
Application failed to start
Failed to bind properties under 'app.server'
~~~

Có thể có các nguyên nhân hoàn toàn khác nhau.

**Case A — sai kiểu:**

~~~properties
app.server.port=abc
~~~

Java yêu cầu `int port`. Đây là conversion failure.

**Case B — số đúng kiểu nhưng sai khoảng:**

~~~properties
app.server.port=70000
~~~

Java dùng `@Min(1) @Max(65535) int port`. Đây là validation failure, khi constraint được bật.

**Case C — thiếu property bắt buộc:**

~~~properties
# app.server.host không được khai báo
~~~

Java dùng `@NotBlank String host`. Đây thường là validation failure nếu binding cho phép object được tạo với host null.

**Case D — sai tên key:**

~~~properties
app.server.hots=localhost
~~~

Java dùng `String host`. Với unknown fields được bỏ qua, Binder có thể không có value cho `host`; nếu @NotBlank được bật, validation mới phát hiện. Nếu strict unknown binding được bật, có thể xảy ra lỗi binding về property không được nhận diện.

**Case E — sai cấu trúc:**

~~~yaml
app:
  server:
    endpoints:
      id: primary
~~~

Java yêu cầu `List<Endpoint> endpoints`. Đây là mismatch cấu trúc cần xem ở tầng binding.

**Case F — thiếu bean config:** class annotated nhưng không được scan/enable. Đây là bean registration problem, không phải value conversion hay constraint validation.

Một biểu hiện ngoài cùng không xác định được category duy nhất nếu thiếu `Reason` và cause chain.

## 20. Sửa lỗi theo đúng tầng

| Lỗi | Cách sửa phù hợp | Cách sửa sai hướng |
| --- | --- | --- |
| YAML mapping thay vì sequence | Viết `-` cho list hoặc đổi model thành object | Thêm `@NotNull` lên list |
| Prefix `app.clients` khác `app.client` | Thống nhất tên key/prefix | Đổi số max retries |
| Thiếu setter/constructor binding hợp lệ | Sửa model hoặc đường đăng ký bean | Bỏ validation |
| Value `abc` cho `int` | Cấp số nguyên hợp lệ | Thêm `@Min(0)` |
| Value `tomorrow` cho `Duration` | Dùng đơn vị `ms`/`s` hoặc converter phù hợp | Đổi tên bean |
| Enum value không tồn tại | Dùng enum constant hợp lệ hoặc custom converter có chủ đích | Thêm `@NotBlank` cho enum |
| `-1` với `@Min(0)` | Cấp số không âm hoặc xem lại rule | Thay converter số nguyên |
| Host trống với `@NotBlank` | Cấp host có nội dung | Bật `ignoreInvalidFields` |
| Nested object có constraint nhưng không được cascade | Thêm `@Valid` đúng vị trí | Tự parse YAML thủ công |
| Nguồn cấu hình không nạp được | Sửa file/path/config import | Đổi `@Validated` |
| Giá trị runtime khác file mong đợi | Kiểm profile và PropertySource precedence | Sửa getter của record |

Với cấu hình production, đừng tắt validation, nới constraint hoặc bỏ qua invalid fields chỉ để tiến trình khởi động. Làm như vậy biến một lỗi cấu hình rõ ràng ở startup thành lỗi nghiệp vụ khó truy vết khi có traffic thật.

## 21. Precedence có thể làm bạn sửa nhầm nguồn

Giả sử file cơ sở:

~~~properties
app.retry.max-attempts=3
~~~

Nhưng khi chạy:

~~~bash
java -jar app.jar --app.retry.max-attempts=many
~~~

Command-line argument thường có ưu tiên cao hơn Config Data thông thường. Dù file chứa `3`, Binder nhận value `many` và conversion sang `int` thất bại.

Nếu bạn sửa `app.retry.max-attempts` trong file từ `3` thành `4` mà vẫn giữ tham số `--app.retry.max-attempts=many`, lỗi vẫn tồn tại. Đây là lý do `Origin` và giá trị hiệu lực quan trọng.

Tương tự:

~~~bash
APP_RETRY_MAXATTEMPTS=bad java -jar app.jar
~~~

trong shell phù hợp có thể đưa value từ biến môi trường vào ứng dụng. Nếu nó thắng file cấu hình, lỗi cần sửa ở môi trường triển khai.

**Binding, conversion và validation luôn xảy ra trên những value mà cấu hình hiệu lực cung cấp**, không phải mặc định trên file đầu tiên developer mở.

## 22. Profile-specific config có thể tạo lỗi chỉ ở một môi trường

Ví dụ:

~~~yaml
# application.yml
app:
  worker:
    concurrency: 4
~~~

~~~yaml
# application-prod.yml
app:
  worker:
    concurrency: many
~~~

Khi không có profile `prod`, ứng dụng có thể bind `4` bình thường. Khi active profile `prod`, value `many` từ file profile có thể trở thành giá trị hiệu lực và conversion sang `int` thất bại.

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Hãy kiểm:

1. Profile nào active?
2. Những tệp profile-specific nào được nạp?
3. Có `spring.config.import` và external configuration nào ghi đè không?
4. `Origin` có trỏ đến đúng file production không?
5. Value có đúng kiểu và đúng constraint không?

Việc local pass không chứng minh mọi profile đều có cấu hình hợp lệ. Với properties quan trọng, nên có test context cho các profile hoặc scenario deployment thực tế.

## 23. Test conversion failure bằng ApplicationContextRunner

`ApplicationContextRunner` của Spring Boot Test cho phép tạo một context nhỏ với các property đầu vào và kiểm xem startup có thất bại hay không.

Ví dụ model:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RetryConversionTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void invalidIntegerFailsDuringBinding() {
        runner
            .withPropertyValues(
                "app.retry.max-attempts=many",
                "app.retry.backoff=250ms"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RetryProperties.class)
    static class TestConfig {}
}
~~~

Bài test khẳng định context không khởi động với value sai. Nếu muốn **khẳng định chính xác conversion failure** chứ không chỉ startup failure, test của dự án cần xem root cause/exception message hoặc exception type có tính ổn định cho Spring Boot version đang dùng.

Tránh assert nguyên văn toàn bộ failure analyzer output vì cách format thông điệp có thể thay đổi giữa các phiên bản.

## 24. Test constraint failure bằng ApplicationContextRunner

Model có validation:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @Min(0) int maxAttempts
) {}
~~~

Giả sử test classpath có Bean Validation provider và context đã cấu hình validator phù hợp. Test với value hợp kiểu nhưng sai ràng buộc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RetryValidationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class)
            .withConfiguration(
                org.springframework.boot.autoconfigure.AutoConfigurations
                    .of(ValidationAutoConfiguration.class)
            );

    @Test
    void negativeRetryCountViolatesConstraint() {
        runner
            .withPropertyValues("app.retry.max-attempts=-2")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RetryProperties.class)
    static class TestConfig {}
}
~~~

Ví dụ cần `spring-boot-starter-test` và `spring-boot-starter-validation` phù hợp với project. Nó minh họa rằng **`-2` là số nguyên hợp lệ**; việc từ chối dữ liệu đến từ `@Min(0)`.

Nếu test này không fail, cần kiểm xem validation provider thực sự được đưa vào context chưa, record có `@Validated` chưa, type có được đăng ký đúng chưa. Đừng vội kết luận `@Min` bị Spring Boot bỏ qua.

## 25. Test binding structure failure

Tạo một test cho sự không phù hợp giữa shape của property và target:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record GatewayProperties(List<Gateway> gateways) {
    public record Gateway(String id, URI url) {}
}
~~~

Input không có index:

~~~properties
app.gateways.id=primary
app.gateways.url=https://gateway.example.test
~~~

Trong test, kiểm tra startup outcome hoặc giá trị bean được bind (nếu context khởi động), rồi đối chiếu với **hình dạng list mong muốn**. Cần phân biệt một lỗi bind cứng với trường hợp Binder bỏ qua dữ liệu và bean có field null/empty. Để tránh cả hai, nên dùng cấu hình rõ chỉ số và validation cho list bắt buộc.

Ví dụ đúng:

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://gateway.example.test
~~~

Test binding có ý nghĩa không chỉ là “không có exception”. Nó phải khẳng định kết quả có **đúng số phần tử, đúng trường và đúng kiểu**. Không suy đoán rằng Binder nhận một file mà đồng nghĩa mọi key đã đi vào object.

## 26. @SpringBootTest kiểm tra các nguồn thực tế

Khi cần kiểm thử cách Spring Boot nạp YAML, profile, imports và auto-configuration thật, có thể dùng `@SpringBootTest`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.retry.max-attempts=3",
    "app.retry.backoff=500ms"
})
class RetryPropertiesIntegrationTest {

    @Autowired
    RetryProperties retry;

    @Test
    void bindsValidConfiguration() {
        assertThat(retry.maxAttempts()).isEqualTo(3);
        assertThat(retry.backoff())
            .isEqualTo(Duration.ofMillis(500));
    }
}
~~~

Test giả định ứng dụng đã đăng ký `RetryProperties` via `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Đây là **positive path**: dữ liệu được bind và loại Java đúng.

Với negative path làm context startup fail, `ApplicationContextRunner` thường giúp assert failure mà không khiến toàn test bootstrap thất bại trước khi test method được chạy. Chọn công cụ tùy mức cần kiểm chứng của dự án.

## 27. Tạo test matrix ba tầng

Một chiến lược kiểm thử dễ hiểu là giữ một mô hình và thay input:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @NotBlank String name,
    @Min(1) @Max(16) int concurrency,
    @NotNull Duration pollInterval
) {}
~~~

| Case | Input tiêu biểu | Kỳ vọng |
| --- | --- | --- |
| Thành công | `name=worker-1`, `concurrency=4`, `poll-interval=2s` | Bind + convert + validate thành công |
| Sai conversion | `concurrency=many` | Conversion failure |
| Sai validation | `concurrency=0` | Validation failure |
| Thiếu bắt buộc | không có `name` | Validation failure nếu được bật |
| Sai shape | `poll-interval` bị đặt dưới một nested object khác | Key không bind đúng; có thể validation báo thiếu |
| Unknown field | `concurency=4` viết thiếu chữ `r` | Có thể bị bỏ qua hoặc strict binding từ chối |
| Value từ CLI override | `--app.worker.concurrency=bad` | Conversion failure ở nguồn có ưu tiên |
| YAML parse fail | YAML thiếu dấu đóng list hoặc sai cấu trúc | Config loading failure trước binding |

Đối với từng case, viết assertion phù hợp. Một test “context hasFailed” chỉ chứng minh có lỗi; muốn phân loại rõ, xem cause chain và, khi cần, khẳng định đúng property path hay kiểu nguyên nhân. Bản thân validation phải thật sự có provider, nếu không case sai ràng buộc có thể không fail.

## 28. @Value có hành vi lỗi khác @ConfigurationProperties

Một component có thể inject:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerClient {
    private final int concurrency;

    public WorkerClient(
        @Value("${app.worker.concurrency}") int concurrency
    ) {
        this.concurrency = concurrency;
    }
}
~~~

Nếu key thiếu, placeholder resolution có thể gây lỗi khi tạo bean. Nếu value `many`, cơ chế conversion của `@Value` có thể báo lỗi injection/type mismatch. Đây là lỗi liên quan externalized config, nhưng không nhất thiết đi qua cùng pipeline hoặc exception classes của Spring Boot `@ConfigurationProperties` Binder.

Một lỗi với `@Value` không nên luôn được ghi nhãn là `ConfigurationPropertiesBindException`. Tên exception cụ thể phụ thuộc cơ chế injection.

### Khi nào nên dùng @ConfigurationProperties?

Nếu có một nhóm trường với kiểu và ràng buộc, `@ConfigurationProperties` giúp gom model, binding và validation rõ ràng. `@Value` hợp lý với một vài scalar đơn giản. Không nên tạo hàng chục annotation `@Value` rồi tự viết validation rải rác khi tất cả chúng là một hợp đồng cấu hình chung.

## 29. Không làm mờ lỗi bằng fallback bừa bãi

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    // getter, setter...
}
~~~

Giá trị default `4` hữu ích khi optional key vắng mặt. Nhưng nếu `concurrency` là bắt buộc trong production, default không được tạo ra chỉ để che việc deploy thiếu cấu hình.

Tương tự, bật `ignoreInvalidFields=true` có thể khiến input sai kiểu không làm startup thất bại theo cách bạn mong đợi, nhưng bean lại nhận default hoặc value thiếu phù hợp. Điều này có thể nguy hiểm khi một ứng dụng xử lý tiền, timeout, port hoặc quyền truy cập.

Một nguyên tắc:

- **Có default** nếu ngữ nghĩa nghiệp vụ quy định fallback an toàn.
- **Có validation** nếu thiếu hoặc sai value phải làm startup thất bại.
- **Không bỏ qua invalid fields** chỉ để giảm số lỗi startup.
- **Kiểm tra nguồn effective value** để tránh nghĩ sai một lỗi là do default.

## 30. Phân biệt phạm vi kiểm tra: cú pháp, kiểu, nghiệp vụ

Ba tầng cũng có thể được hiểu như những mức trách nhiệm kiểm dữ liệu:

| Tầng | Ví dụ câu hỏi | Công cụ |
| --- | --- | --- |
| Cú pháp/structure file | YAML có parse được không? | YAML/properties parser, Config Data loader |
| Mapping/binding | `app.worker.concurrency` map vào field nào? | Spring Boot Binder |
| Type conversion | `"4"` có thành `int`? `"2s"` có thành `Duration`? | ConversionService/converter |
| Constraint validation | `concurrency` phải từ 1 đến 16? | Bean Validation |
| Cross-field validation | `readTimeout >= connectTimeout`? | Custom class-level constraint hoặc kiểm tra sau bind |
| Logic runtime | Remote endpoint có reachable? | Health check/service logic, không phải Binder |

Không nên nhồi network calls hay database queries vào converter chỉ để “validate config”. Một endpoint URL đúng cú pháp chưa chắc reachable; đó là vấn đề vận hành hoặc nghiệp vụ, không phải ConversionService đơn giản.

Validation nên phản ánh những điều kiện có thể kiểm tra cục bộ, nhanh và xác định. Kiểm tra external dependency cần chính sách timeout/retry và lựa chọn fail startup phù hợp với deployment.

## 31. Validation liên thuộc giữa nhiều field

Một ví dụ domain có `connectTimeout` và `readTimeout`:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    @NotNull Duration connectTimeout,
    @NotNull Duration readTimeout
) {}
~~~

Yêu cầu “read timeout phải lớn hơn hoặc bằng connect timeout” không được diễn đạt đầy đủ bởi hai `@NotNull`. Có thể dùng một **class-level Bean Validation constraint** tự định nghĩa như `@ValidTimeoutPair`, hoặc một bước validation rõ ràng phù hợp với kiến trúc của bạn.

Những điều kiện liên thuộc là **constraint validation**, không phải conversion. Hai thời gian `10s` và `2s` đều chuyển thành `Duration` hợp lệ; lỗi là do quan hệ `readTimeout >= connectTimeout` bị vi phạm.

Nếu custom validator cần phụ thuộc tài nguyên ngoài, xem lại thiết kế: validation giai đoạn startup nên có ít dependency và thông điệp lỗi dễ hiểu.

## 32. Cách đặt error message hữu ích

Đối với constraint custom, thông điệp nên cho biết:

- Property/group nào không hợp lệ.
- Giá trị hoặc quan hệ nào vi phạm, nhưng không lộ secret.
- Khoảng hợp lệ hoặc ví dụ đúng.
- Có thể sửa ở nguồn nào nếu đã biết.

Ví dụ message:

~~~text
app.worker.concurrency must be between 1 and 16
~~~

Hoặc:

~~~text
app.client.read-timeout must be >= app.client.connect-timeout
~~~

Với lỗi conversion, message hữu ích nêu target type:

~~~text
app.worker.poll-interval must be a valid Duration
(e.g. 250ms, 2s, 1m)
~~~

Không “dịch” toàn bộ stack trace thành một thông báo mơ hồ như “Cấu hình sai”. Giữ cause để người vận hành biết lỗi thuộc mapping, conversion hay constraint.

## 33. Troubleshooting khi có custom Converter

Một số dự án dùng custom type:

~~~java
public record CurrencyCode(String value) {}
~~~

và custom converter:

~~~java
public final class CurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        String code = source.trim().toUpperCase();
        if (code.length() != 3) {
            throw new IllegalArgumentException(
                "Currency code must have 3 characters");
        }
        return new CurrencyCode(code);
    }
}
~~~

Nếu Binder không tìm được đường chuyển từ `String` sang `CurrencyCode`, đây là một **conversion configuration problem**. Nếu converter có chạy nhưng ném exception vì value `LONGCODE`, vẫn là conversion failure ở tầng parsing.

Nếu yêu cầu bổ sung là “currency code phải nằm trong danh sách được hỗ trợ của ứng dụng”, có thể dùng Bean Validation hoặc domain validation có chủ đích sau khi type đã được tạo. Điều này tách hai ý:

1. Chuỗi có tạo được một `CurrencyCode` có cấu trúc hợp lệ không?
2. Code đó có được phép trong ngữ cảnh nghiệp vụ không?

Không nhất thiết mọi dự án phải tách hai bước đúng như vậy, nhưng sự phân biệt sẽ giúp message và test đúng trách nhiệm.

## 34. Lỗi binding với JavaBean mutable và record immutable

Hai mô hình binding khác nhau có thể dẫn đến những lỗi không cùng biểu hiện.

### JavaBean setter binding

~~~java
@ConfigurationProperties(prefix = "app.pool")
public class PoolProperties {
    private int maxSize = 8;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

Nếu thiếu setter hoặc field không bind được theo cơ chế JavaBean phù hợp, dữ liệu có thể không được gán như kỳ vọng. Kiểm constructor, getter/setter, visibility và cách đăng ký bean.

### Record constructor binding

~~~java
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(int maxSize) {}
~~~

Khi đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Binder có thể dùng constructor record.

Nhưng:

~~~java
@Component
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(int maxSize) {}
~~~

đưa type vào đường component construction. Spring có thể tìm dependency cho tham số constructor theo cơ chế bean injection, thay vì Binder đặt value property. Lỗi tạo bean phát sinh ở đây là **đăng ký/khởi tạo không đúng đường**, không nên đổ cho `@Min` hay giá trị `max-size` nếu chưa xác minh.

## 35. Quy trình gỡ lỗi 10 bước

1. **Đọc exception/root cause**, không chỉ dòng “Application run failed”.
2. **Xác định giai đoạn:** file parse/load, bean registration, binding, conversion, validation hay service startup.
3. **Kiểm key:** prefix, relaxed binding, tên field, index list và nested path.
4. **Kiểm value:** dạng scalar/list/map có khớp target Java không?
5. **Kiểm type Java:** `Integer`, `Duration`, enum, custom type đã có converter chưa?
6. **Kiểm constraint:** `@NotBlank`, `@NotNull`, `@Min`, `@Valid` và validator provider đã chạy chưa?
7. **Kiểm nguồn ghi đè:** profile, import, env, system properties và CLI; xem `Origin` nếu có.
8. **Kiểm bean registration:** scan/enable, package, constructor-binding/setter-binding mechanism.
9. **Tạo test nhỏ:** dùng `ApplicationContextRunner` để kiểm failure ở một input; dùng integration test cho nhiều nguồn.
10. **Sửa đúng tầng và xác nhận startup** với value hợp lệ; không bật cơ chế bỏ qua lỗi để che vấn đề.

Sau khi khởi động thành công, nếu nghiệp vụ vẫn không đúng, kiểm giá trị đã bind và cách consumer dùng chúng. “Không có exception” không chứng minh mọi optional key đã nhận đúng theo kỳ vọng.

## 36. Bài tập nhận dạng lỗi

### Bài 1: cấu hình số không parse được

~~~properties
app.worker.concurrency=several
~~~

Java: `int concurrency` có `@Min(1)`.

**Đáp án:** conversion failure vì không có số để đem đi kiểm `@Min(1)`.

### Bài 2: số parse được nhưng sai range

~~~properties
app.worker.concurrency=0
~~~

Java: `@Min(1) int concurrency`.

**Đáp án:** validation failure khi Bean Validation được bật.

### Bài 3: thiếu chuỗi bắt buộc

Không có `app.worker.name`; Java có `@NotBlank String name`.

**Đáp án:** nếu Binder tạo bean với name null và validation hoạt động, ràng buộc `@NotBlank` bị vi phạm; không phải parse String lỗi.

### Bài 4: list bị viết như object

~~~yaml
app:
  servers:
    host: one.example.test
~~~

Java: `List<Server> servers`.

**Đáp án:** shape mismatch trong binding; cần YAML sequence có dấu `-` hoặc model khác phù hợp.

### Bài 5: sai key, nhưng unknown fields bị bỏ qua

~~~properties
app.mail.hots=smtp.example.test
~~~

Java: `String host`, không có validation.

**Đáp án:** có thể không có startup failure, nhưng `host` không nhận dữ liệu như kỳ vọng. Đây là lý do cần đặt constraint cho key bắt buộc hoặc kiểm strict binding khi thích hợp.

### Bài 6: enum không tồn tại

~~~properties
app.delivery.mode=INSTANTLY
~~~

Java: `DeliveryMode mode` với enum chỉ có `SYNC` và `ASYNC`.

**Đáp án:** conversion failure, không phải `@Pattern` failure.

### Bài 7: nested constraint chưa cascade

Model root có `@Validated`, nested field có `@Min` nhưng không cấu hình cascade `@Valid` phù hợp.

**Đáp án:** Bean Validation có thể không đánh giá nested constraint như mong đợi. Cần `@Valid` và provider đúng, không sửa source YAML nếu nó vốn đang cung cấp giá trị test cố ý sai.

### Bài 8: YAML không parse

~~~yaml
app:
  tags: [one, two
~~~

**Đáp án:** lỗi parsing Config Data, trước binding/conversion/validation.

### Bài 9: lỗi nằm ở CLI, không ở file

File có `app.retry.max-attempts=3`. Lệnh chạy thêm `--app.retry.max-attempts=many`.

**Đáp án:** conversion failure trên value hiệu lực `many`; sửa CLI hoặc nguồn ưu tiên cao hơn.

### Bài 10: bean không được đăng ký

Một record có `@ConfigurationProperties` nhưng ứng dụng không scan/enable type ấy.

**Đáp án:** bean registration failure; chưa thể suy luận bất kỳ constraint nào đã chạy.

## 37. Checklist khi đọc log thực tế

| Câu hỏi chẩn đoán | Nếu “có” thì chú ý |
| --- | --- |
| Có lỗi YAML/parser trước khi thấy prefix? | Config loading, không phải Bean Validation |
| Có `required a bean ... could not be found`? | Bean registration / package scan |
| Có `Failed to bind properties under ...`? | Kiểm cause; có thể thuộc cả ba nhóm |
| Có `Failed to convert ...` hoặc converter exception? | Conversion |
| Có `@NotBlank`/`@Min`/constraint violation? | Validation |
| Có key gần đúng nhưng viết thiếu chữ? | Binding name/prefix, unknown fields |
| Có `Value` khác file đang mở? | PropertySource precedence/profile |
| Có `Origin` chỉ tới file khác? | Sửa đúng nguồn thắng |
| Có List nhưng YAML thiếu dấu `-`? | Binding structure |
| Có kiểu JavaBean nhưng không setter? | Binding model |
| Có record `@Component` yêu cầu bean int/URI? | Sai cơ chế khởi tạo/registration |
| Có valid scalar nhưng sai business rule? | Constraint/domain validation |
| Đã thêm provider và `@Validated` chưa? | Cấu hình validation |
| Lỗi chỉ ở prod? | Profile-specific Config Data và override |

## 38. Tổng kết

Có thể nhớ theo ba câu:

- **Binding:** “Tôi có ghép được dữ liệu cấu hình vào đúng hình dạng đối tượng Java không?”
- **Conversion:** “Giá trị nguồn có chuyển thành đúng kiểu Java mà model đòi hỏi không?”
- **Validation:** “Giá trị đã đọc có thỏa ràng buộc và quy tắc nghiệp vụ không?”

Chúng là những lớp trách nhiệm có liên quan, không phải ba thế giới tách biệt: conversion failure hoặc validation failure đều có thể được **bọc trong binding exception**. Khi gỡ lỗi, hãy bắt đầu từ `Property`, `Value`, `Origin` và đặc biệt là `Reason`/root cause. Nếu lỗi là mapping, sửa cấu trúc hoặc đường đăng ký; nếu là conversion, sửa định dạng hoặc converter; nếu là constraint, sửa giá trị hoặc quy tắc validation có chủ đích. Tránh tắt `@Validated` và bỏ qua invalid fields chỉ để ứng dụng khởi động, vì một lỗi cấu hình rõ ràng lúc startup có thể biến thành hành vi khó kiểm soát ở runtime.
