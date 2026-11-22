# Phân biệt giá trị không có, null và chuỗi rỗng

> **Chương:** Environment  
> **Module:** SPRING_CLOUD_CORE

Khi ứng dụng Spring Boot nhận cấu hình từ `application.yml`, biến môi trường, tham số dòng lệnh hoặc Spring Cloud Config, một thuộc tính có thể ở nhiều trạng thái khác nhau: **không được khai báo**, được khai báo với giá trị **null**, hoặc được khai báo bằng **chuỗi rỗng**. Ba trạng thái này không tương đương. Nếu nhầm lẫn chúng, ứng dụng có thể dùng sai giá trị mặc định, không xóa được cấu hình cũ, khởi động với dữ liệu thiếu hoặc gửi request với một URL rỗng.

Bài này phân tích các trạng thái đó qua YAML, Spring `Environment`, property source, placeholder và `@ConfigurationProperties`. Mục tiêu là biết cách biểu diễn ý định cấu hình một cách rõ ràng, kiểm tra giá trị bắt buộc và xử lý ghi đè khi ứng dụng chạy ở nhiều môi trường.

## 1. Ba trạng thái cần phân biệt

Giả sử ứng dụng có thuộc tính `notification.sender`:

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Không có (absent)** | Không khai báo key `notification.sender` | Nguồn cấu hình này không cung cấp giá trị |
| **Null** | `sender: null` hoặc `sender:` trong YAML | Key được biểu diễn bằng giá trị null theo cú pháp nguồn |
| **Chuỗi rỗng (empty string)** | `sender: ""` | Giá trị là một chuỗi có độ dài bằng không |
| **Chuỗi chữ `null`** | `sender: "null"` | Giá trị là bốn ký tự `n`, `u`, `l`, `l` |
| **Chuỗi chỉ có khoảng trắng** | `sender: "   "` | Chuỗi có ký tự nhưng không có nội dung hữu ích theo nghĩa thông thường |

Trong Java, các trường hợp thường được nhìn nhận như sau:

- Không có giá trị hoặc giá trị null thường được biểu diễn bằng `null` khi đọc vào một kiểu tham chiếu, nếu không có giá trị mặc định hoặc nguồn cấu hình khác.
- Chuỗi rỗng được biểu diễn bằng `""`; `value != null` nhưng `value.isEmpty()` là `true`.
- Chuỗi chỉ có khoảng trắng không rỗng, nhưng `value.isBlank()` là `true`.
- Chuỗi chữ `"null"` là một giá trị bình thường, không phải Java `null`.

Đối với boolean và số, `false` và `0` cũng là **giá trị được khai báo hợp lệ**, không phải absent hay empty. Đừng dùng chuỗi rỗng để diễn đạt `false`, `0` hoặc một giá trị mặc định.

## 2. Biểu diễn trong YAML

YAML có cú pháp riêng để biểu diễn null và chuỗi rỗng. Ví dụ:

~~~yaml
notification:
  # Key không xuất hiện trong document:
  # sender không được khai báo.

  sender-null: null
  sender-empty: ""
  sender-literal: "null"
  sender-whitespace: "   "
  sender-with-value: "alerts@example.com"
~~~

Các cách biểu diễn null phổ biến trong YAML:

~~~yaml
first: null
second: ~
third:
~~~

Cả ba đều được YAML parser hiểu là giá trị null. Dòng `third:` không có nội dung sau dấu hai chấm cũng tạo ra giá trị null, không phải chuỗi rỗng.

Để biểu diễn chuỗi rỗng, dùng dấu nháy:

~~~yaml
empty-a: ""
empty-b: ''
~~~

Hai cách trên biểu diễn chuỗi có độ dài bằng không.

Nếu muốn giá trị gồm đúng bốn ký tự `null`, phải đặt trong dấu nháy:

~~~yaml
literal-null: "null"
~~~

### 2.1. Không nhầm comment với khai báo null

Hai ví dụ sau khác nhau:

~~~yaml
# notification.sender:
~~~

~~~yaml
notification:
  sender:
~~~

Ví dụ đầu chỉ là comment, nên key không tồn tại trong dữ liệu YAML. Ví dụ thứ hai có khai báo `sender` với giá trị null.

Khi đọc file, cần phân biệt key bị lược bỏ, key có giá trị null và key có giá trị chuỗi rỗng. Đây là cơ sở để hiểu việc merge cấu hình giữa nhiều file hoặc nhiều property source.

## 3. Spring Environment và PropertySource xử lý các trạng thái này thế nào?

Spring Boot đưa các nguồn cấu hình vào `Environment`. Mỗi `PropertySource` cung cấp các property theo tên key; có thể có nhiều nguồn cùng chứa một key, ví dụ:

- `application.yml` trong classpath.
- `application-production.yml`.
- File cấu hình bên ngoài.
- Biến môi trường.
- Java system properties.
- Tham số dòng lệnh.
- Nguồn cấu hình từ Spring Cloud Config.
- Property được thêm trong test context.

Khi cùng một key xuất hiện ở nhiều nguồn, nguồn có độ ưu tiên cao hơn thường được xét trước. Nhưng một giá trị null có ý nghĩa đặc biệt: **property resolver chuẩn của Spring không xem null là một giá trị có thể trả về để ghi đè giá trị thấp hơn**. Khi gặp null, việc tra cứu có thể tiếp tục tìm một giá trị không null ở nguồn thấp hơn.

Ví dụ, `application.yml`:

~~~yaml
service:
  endpoint: "https://api.default.example"
  label: "Order API"
  description: "Default description"
~~~

`application-production.yml`:

~~~yaml
service:
  endpoint: null
  label: ""
  description: "Production API"
~~~

Khi profile `production` active, có thể hiểu kết quả tra cứu như sau:

| Key | Giá trị ở nguồn profile | Kết quả tra cứu điển hình |
| --- | --- | --- |
| `service.endpoint` | null | Null không cung cấp giá trị ghi đè; giá trị thấp hơn có thể được dùng |
| `service.label` | `""` | Chuỗi rỗng là giá trị có mặt và có thể ghi đè `"Order API"` |
| `service.description` | `"Production API"` | Giá trị profile ghi đè giá trị chung |

Đây là điểm quan trọng khi muốn “xóa” một giá trị mặc định. Đặt key thành null trong một nguồn cấu hình không phải là cách đáng tin cậy để xóa giá trị ở nguồn thấp hơn. Nếu cần biểu diễn một trạng thái rõ ràng, hãy thiết kế property và quy tắc xử lý phù hợp, ví dụ một cờ `enabled`, một giá trị sentinel được định nghĩa rõ, hoặc một cấu hình riêng có semantics cụ thể.

**Giới hạn cần nhớ:** `Environment.getProperty("service.endpoint")` trả về giá trị có thể phân giải được, hoặc `null` nếu không có giá trị phù hợp. Chỉ nhìn kết quả này không đủ để biết key hoàn toàn không xuất hiện trong bất kỳ file nào hay một nguồn đã khai báo key bằng null. Muốn điều tra nguồn gốc, cần kiểm tra property source/origin và cấu hình đầu vào cụ thể.

### 3.1. Ví dụ đọc qua Environment

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServiceConfigurationReader {

    private final Environment environment;

    public ServiceConfigurationReader(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        String endpoint = environment.getProperty("service.endpoint");
        String label = environment.getProperty("service.label");

        if (endpoint == null) {
            // Không có giá trị endpoint có thể phân giải.
            // Cần quyết định fallback hoặc báo lỗi.
        }

        if (label == null) {
            // Không có giá trị label có thể phân giải.
        } else if (label.isEmpty()) {
            // Có giá trị chuỗi rỗng.
        } else if (label.isBlank()) {
            // Có ký tự nhưng chỉ gồm whitespace.
        } else {
            // Có nội dung.
        }
    }
}
~~~

`Environment` hữu ích khi cần đọc một property động theo tên. Với một nhóm cấu hình có cấu trúc, `@ConfigurationProperties` thường rõ ràng và dễ kiểm thử hơn.

## 4. Placeholder và giá trị mặc định

Spring hỗ trợ placeholder trong YAML và `@Value`. Cú pháp thường gặp:

~~~yaml
service:
  label: ${SERVICE_LABEL:Default label}
  endpoint: ${SERVICE_ENDPOINT:https://localhost:8443}
~~~

Cấu trúc `${NAME:default}` cung cấp giá trị mặc định khi placeholder không tìm được giá trị phù hợp. Cần phân biệt:

- Biến/property không được cung cấp: fallback có thể được sử dụng.
- Property source có null: null không được xem là giá trị phân giải; resolver có thể tiếp tục tìm nguồn thấp hơn hoặc dùng fallback nếu không tìm thấy giá trị.
- Property được cung cấp bằng chuỗi rỗng: chuỗi rỗng là giá trị; fallback không tự thay thế nó.
- Property được cung cấp bằng chuỗi `"null"`: đây là chuỗi literal, không phải null.

Ví dụ:

~~~yaml
service:
  label: ${SERVICE_LABEL:Default label}
~~~

Nếu `SERVICE_LABEL` không tồn tại, kết quả là `Default label`. Nếu biến môi trường tồn tại với giá trị rỗng, kết quả là chuỗi rỗng. Vì vậy, fallback placeholder **không phải** cơ chế thay thế mọi giá trị rỗng.

Có thể dùng placeholder trực tiếp trong `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ServiceLabel {

    private final String label;

    public ServiceLabel(
            @Value("${service.label:Default label}") String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
~~~

Nếu nghiệp vụ coi chuỗi rỗng cũng là không hợp lệ, hãy kiểm tra riêng bằng `isBlank()` hoặc dùng Bean Validation. Đừng mong placeholder tự động hiểu ý nghĩa nghiệp vụ của chuỗi rỗng.

## 5. Binding vào @ConfigurationProperties

Với cấu hình có nhiều thuộc tính, dùng `@ConfigurationProperties` giúp gom chúng thành một kiểu Java. Ví dụ:

~~~yaml
mail:
  sender: ""
  reply-to: "support@example.com"
  footer: null
  enabled: false
  retry-count: 0
~~~

Kiểu cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String sender,
        String replyTo,
        String footer,
        Boolean enabled,
        Integer retryCount
) {}
~~~

Giả sử kiểu cấu hình đã được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, các giá trị thể hiện những trạng thái khác nhau:

| Trường | Giá trị đầu vào | Giá trị Java mong đợi theo binding thông thường |
| --- | --- | --- |
| `sender` | `""` | Chuỗi rỗng |
| `replyTo` | Chuỗi địa chỉ | Chuỗi địa chỉ |
| `footer` | YAML null | Không có giá trị có thể bind; có thể là null nếu không có nguồn khác |
| `enabled` | `false` | `Boolean.FALSE` |
| `retryCount` | `0` | `Integer.valueOf(0)` |

Dùng wrapper như `Boolean` và `Integer` khi cần phân biệt “không được cấu hình” với `false` hoặc `0`. Nếu dùng primitive `boolean` hoặc `int`, Java không thể biểu diễn null; giá trị mặc định của primitive có thể làm mất thông tin rằng property đã bị bỏ trống.

Với kiểu `String`, chuỗi rỗng có thể được giữ nguyên. Với kiểu đích khác như số, boolean, enum hoặc URI, chuỗi rỗng có thể không chuyển đổi được hoặc được xử lý tùy converter và phiên bản. **Không dùng chuỗi rỗng như một quy ước chung cho mọi kiểu dữ liệu.**

### 5.1. Phân biệt String null, empty và blank trong code

~~~java
public final class MailSenderPolicy {

    public boolean hasSender(String sender) {
        return sender != null && !sender.isBlank();
    }

    public String resolveSender(String configured, String fallback) {
        if (configured == null || configured.isBlank()) {
            return fallback;
        }
        return configured;
    }
}
~~~

`isBlank()` kiểm tra chuỗi rỗng hoặc chỉ chứa whitespace. `isEmpty()` chỉ kiểm tra độ dài bằng không. Ví dụ:

| Giá trị Java | `value == null` | `value.isEmpty()` | `value.isBlank()` |
| --- | --- | --- | --- |
| `null` | true | Không gọi được | Không gọi được |
| `""` | false | true | true |
| `"   "` | false | false | true |
| `"mail"` | false | false | false |

Luôn kiểm tra null trước khi gọi `isEmpty()` hoặc `isBlank()` để tránh `NullPointerException`.

### 5.2. Validation cho cấu hình bắt buộc

Nếu `mail.sender` bắt buộc phải có nội dung, có thể dùng `@NotBlank`:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        @NotBlank String sender,
        String replyTo
) {}
~~~

Với dependency validation phù hợp, ứng dụng sẽ báo lỗi binding/validation khi `sender` là null, chuỗi rỗng hoặc chỉ có whitespace.

Các annotation có ý nghĩa khác nhau:

| Annotation | Điều kiện |
| --- | --- |
| `@NotNull` | Giá trị không được null; chuỗi rỗng vẫn hợp lệ |
| `@NotEmpty` | Không null và không rỗng; chuỗi chỉ có khoảng trắng vẫn có thể hợp lệ |
| `@NotBlank` | Không null và phải chứa ít nhất một ký tự không phải whitespace |
| `@Min(1)` | Giá trị số phải lớn hơn hoặc bằng 1 |
| `@Positive` | Giá trị số phải lớn hơn 0 |

Validation nên phản ánh quy tắc nghiệp vụ. Một thuộc tính tùy chọn có thể cho phép null; một thuộc tính bắt buộc dạng text thường cần `@NotBlank`; một cờ boolean có thể cần giá trị tường minh để tránh trạng thái không xác định.

## 6. Phân biệt absent/null/empty với false, zero và collection rỗng

Một lỗi phổ biến là gom tất cả các giá trị “trông như không có gì” thành một trạng thái. Thực tế, các kiểu dữ liệu có những giá trị hợp lệ riêng:

~~~yaml
feature:
  enabled: false
  max-connections: 0
  allowed-origins: []
  metadata: {}
  description: ""
  optional-endpoint: null
~~~

Ý nghĩa:

- `false`: đã cấu hình rõ ràng rằng tính năng tắt.
- `0`: đã cấu hình số không; hợp lệ hay không do quy tắc nghiệp vụ quyết định.
- `[]`: danh sách được khai báo nhưng không có phần tử.
- `{}`: map được khai báo nhưng không có entry.
- `""`: chuỗi được khai báo với nội dung rỗng.
- `null`: giá trị null theo định dạng nguồn; trong quá trình resolve Spring, nó không hoạt động như một giá trị ghi đè thông thường.
- Không khai báo key: nguồn cấu hình không cung cấp thuộc tính đó.

Đối với list và map, quy tắc binding/merge giữa nhiều property source có thể khác với scalar. Danh sách ở nguồn có độ ưu tiên cao thường thay thế danh sách ở nguồn thấp hơn; không mặc định rằng các phần tử sẽ được nối. Nếu cần xóa toàn bộ danh sách mặc định, hãy dùng cú pháp collection rỗng phù hợp và viết test xác nhận kết quả binder của phiên bản Spring Boot đang chạy.

## 7. Ghi đè giữa các nguồn cấu hình

Spring Boot có thể đọc cùng một key từ nhiều property source. Ví dụ:

`application.yml`:

~~~yaml
feature:
  banner: "Welcome"
  endpoint: "https://default.example"
~~~

`application-production.yml`:

~~~yaml
feature:
  banner: ""
  endpoint: null
~~~

Biến môi trường:

~~~text
FEATURE_BANNER=Production
~~~

Nếu biến môi trường có độ ưu tiên cao hơn file cấu hình, `feature.banner` có thể nhận `Production`. Nếu không có biến môi trường, chuỗi rỗng ở file profile là một giá trị có mặt và có thể ghi đè `Welcome`. Trong khi đó, `feature.endpoint: null` không cung cấp một giá trị ghi đè hữu dụng; giá trị từ nguồn thấp hơn có thể tiếp tục được dùng.

Điều này dẫn đến ba quy tắc thiết kế:

1. **Muốn dùng mặc định:** bỏ key ở nguồn cụ thể hoặc dùng placeholder/default có chủ đích.
2. **Muốn đặt một chuỗi rỗng:** dùng `""` và bảo đảm code chấp nhận empty string như một trạng thái hợp lệ.
3. **Muốn tắt một chức năng:** dùng boolean `false` hoặc thuộc tính trạng thái riêng, thay vì null hoặc chuỗi rỗng.

Không dựa vào null để “xóa” giá trị ở file thấp hơn. Nếu cần xóa một giá trị cấu hình, hãy thiết kế property có semantics rõ ràng như `feature.enabled: false`, `feature.endpoint: ""` nếu empty có nghĩa được định nghĩa, hoặc một chế độ `feature.mode: disabled`. Đối với các giá trị phức tạp, có thể cần thay đổi nguồn cấu hình hoặc cấu trúc cấu hình thay vì cố biểu diễn thao tác xóa bằng null.

## 8. Biến môi trường và tham số dòng lệnh

Trong môi trường triển khai, biến môi trường có thể ở ba trạng thái thực tế:

- Không được đặt.
- Được đặt thành chuỗi rỗng.
- Được đặt thành một chuỗi có nội dung.

Ví dụ PowerShell:

~~~powershell
Remove-Item Env:FEATURE_LABEL -ErrorAction SilentlyContinue
$env:FEATURE_LABEL = ""
$env:FEATURE_LABEL = "Production"
~~~

Ba thao tác trên lần lượt xóa biến khỏi process environment, đặt biến bằng chuỗi rỗng và đặt biến có nội dung. Trong tiến trình Spring Boot, trạng thái biến được cung cấp trở thành property source theo quy tắc ánh xạ tên của Spring Boot.

Tham số dòng lệnh cũng phân biệt:

~~~bash
java -jar app.jar
java -jar app.jar --feature.label=
java -jar app.jar --feature.label=Production
~~~

- Lệnh đầu không cung cấp `feature.label` qua command line.
- Lệnh thứ hai cung cấp key với giá trị rỗng.
- Lệnh thứ ba cung cấp giá trị `Production`.

Khi dùng Docker, Kubernetes hoặc hệ thống CI/CD, hãy kiểm tra cách nền tảng biểu diễn key bị thiếu và key có giá trị `""`. Không phải mọi giao diện nhập liệu đều hiển thị hai trạng thái này giống nhau. Với secret, tránh đặt giá trị rỗng ngoài ý muốn; cấu hình bắt buộc nên được xác thực ngay khi khởi động.

## 9. Tương tác với Spring Cloud Config và refresh

Trong hệ thống Spring Cloud, cấu hình có thể đến từ Config Server thay vì chỉ từ `application.yml` cục bộ. Một Config Server có thể trả về property sources cho application name, profile và label được yêu cầu.

Ví dụ client:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu Config Server trả một key với giá trị rỗng, chuỗi rỗng có thể trở thành giá trị cấu hình có hiệu lực và ghi đè giá trị thấp hơn theo thứ tự property source. Nếu payload chứa null, Spring property resolution không xem null như giá trị có thể ghi đè thông thường. Cách biểu diễn null và nguồn property cụ thể có thể phụ thuộc repository, serialization và phiên bản; cần kiểm tra kết quả thực tế.

### 9.1. Refresh không làm thay đổi ý nghĩa của null

Spring Cloud Context cung cấp `@RefreshScope` và các cơ chế refresh để một số bean có thể được tạo lại sau khi môi trường cấu hình được cập nhật. Refresh không thay đổi nguyên tắc cơ bản:

- Key không được cung cấp có thể khiến ứng dụng dùng giá trị ở nguồn khác hoặc fallback.
- Giá trị null không tự động xóa giá trị thấp hơn trong property resolution chuẩn.
- Chuỗi rỗng là giá trị có mặt và có thể được bind vào bean.
- Bean cần được thiết kế để xử lý trường hợp cấu hình null/empty hợp lệ hoặc từ chối chúng bằng validation.

Ví dụ một bean đọc nhãn có thể phân biệt null và empty:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class NotificationLabel {

    private final String label;

    public NotificationLabel(
            @Value("${notification.label:Default}") String label) {
        this.label = label;
    }

    public boolean isVisible() {
        return label != null && !label.isBlank();
    }
}
~~~

Nếu giá trị được refresh thành chuỗi rỗng, bean mới vẫn nhận chuỗi rỗng; `isVisible()` trả về false. Nếu key không có giá trị có thể phân giải, placeholder có thể cung cấp `Default`. Hành vi thực tế còn phụ thuộc nguồn cấu hình và quá trình refresh đã được kích hoạt đúng cách.

Không coi `@RefreshScope` là cơ chế tự theo dõi file. Phải có nguồn cấu hình, sự kiện hoặc thao tác refresh tương ứng; đồng thời bảo vệ các endpoint refresh và không ghi log secret.

## 10. Kiểm thử các trạng thái cấu hình

Một test hữu ích nên xác nhận cả ba trạng thái: property bị bỏ qua, property rỗng và property có giá trị. Có thể dùng `ApplicationContextRunner` để kiểm thử binding trong một context nhỏ, hoặc dùng `@SpringBootTest` với property được override.

Ví dụ kiểm tra chuỗi rỗng được bind:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class BannerPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsEmptyStringAsAnExplicitValue() {
        runner.withPropertyValues("feature.banner=")
                .run(context -> {
                    FeatureProperties properties =
                            context.getBean(FeatureProperties.class);

                    assertThat(properties.banner()).isEmpty();
                });
    }

    @Test
    void leavesMissingStringUnconfigured() {
        runner.run(context -> {
            FeatureProperties properties =
                    context.getBean(FeatureProperties.class);

            assertThat(properties.banner()).isNull();
        });
    }

    @EnableConfigurationProperties(FeatureProperties.class)
    static class TestConfiguration {
    }

    @ConfigurationProperties(prefix = "feature")
    record FeatureProperties(String banner) {
    }
}
~~~

Ví dụ này minh họa một property đơn giản với `String` và constructor binding. Dự án cần có dependency test của Spring Boot, JUnit 5 và AssertJ. Khi kiểm thử giá trị null trong YAML hoặc JSON, hãy thêm test với đúng nguồn cấu hình mà ứng dụng sử dụng; `withPropertyValues` không mô phỏng toàn bộ hành vi của YAML parser hay Config Server.

### 10.1. Ma trận kiểm thử đề xuất

| Đầu vào | Kết quả cần kiểm tra |
| --- | --- |
| Key không khai báo ở mọi nguồn | Binder nhận trạng thái thiếu; fallback hoặc validation hoạt động đúng |
| Key YAML có giá trị null | Resolver không dùng null làm giá trị ghi đè; kiểm tra nguồn thấp hơn |
| Key YAML là `""` | String binding nhận empty; fallback placeholder không thay thế empty |
| Key là `"null"` | Giá trị là chuỗi literal `null` |
| Key là `"   "` | String không rỗng nhưng `isBlank()` là true |
| Key boolean là `false` | Giá trị false được giữ, không bị hiểu thành thiếu |
| Key số là `0` | Giá trị zero được giữ; validation quyết định có hợp lệ không |
| Key list là `[]` | Binder nhận collection rỗng theo cấu hình và phiên bản đang dùng |
| Nguồn ưu tiên cao đặt empty | Empty ghi đè giá trị có nội dung ở nguồn thấp |
| Nguồn ưu tiên cao đặt null | Giá trị thấp hơn có thể tiếp tục được phân giải |

Test nên chạy với profile và Config Data gần với cách triển khai thật nếu ứng dụng phụ thuộc nhiều nguồn. Không chỉ kiểm tra giá trị trong unit test; cần có ít nhất một smoke test khởi động ứng dụng với cấu hình đại diện.

## 11. Những lỗi thường gặp

1. **Viết `key:` và nghĩ đó là chuỗi rỗng.** Trong YAML, key không có giá trị thường là null; dùng `key: ""` nếu muốn empty string.
2. **Dùng `"null"` khi muốn Java null.** Dấu nháy làm cho `null` trở thành chuỗi literal.
3. **Mong null ghi đè giá trị mặc định.** Property resolver chuẩn bỏ qua null như giá trị có thể trả về; nguồn thấp hơn có thể vẫn cung cấp giá trị.
4. **Nghĩ placeholder fallback xử lý cả chuỗi rỗng.** Fallback dành cho property không resolve được; empty string là giá trị đã được cung cấp.
5. **Dùng primitive khi cần phân biệt thiếu và false/zero.** Dùng wrapper hoặc một kiểu biểu diễn trạng thái rõ ràng.
6. **Dùng `@NotNull` cho yêu cầu chuỗi phải có nội dung.** `@NotNull` vẫn chấp nhận `""`; dùng `@NotBlank` nếu cần từ chối empty và whitespace.
7. **Gọi `isBlank()` trên giá trị có thể null.** Kiểm tra null trước hoặc dùng validation để bảo đảm điều kiện.
8. **Cố xóa list bằng null.** Dùng collection rỗng có chủ đích và kiểm thử hành vi binding/merge.
9. **Không kiểm tra property source có độ ưu tiên cao.** Một biến môi trường rỗng có thể ghi đè chuỗi có nội dung trong file.
10. **Cho rằng refresh sẽ tự biến empty thành fallback.** Refresh chỉ nạp và áp dụng trạng thái cấu hình mới; logic fallback vẫn do resolver hoặc code ứng dụng quyết định.

## 12. Quy tắc thiết kế cấu hình rõ ràng

Khi định nghĩa một property, hãy quyết định rõ trạng thái nào được phép:

| Nhu cầu | Cách biểu diễn nên dùng |
| --- | --- |
| Cho phép dùng giá trị mặc định | Bỏ key ở nguồn ghi đè hoặc định nghĩa fallback rõ ràng |
| Cho phép người dùng nhập chuỗi rỗng | Dùng `""` và xử lý empty trong code |
| Bắt buộc có nội dung | Dùng `@NotBlank` hoặc validation tương đương |
| Cho phép giá trị tùy chọn | Dùng kiểu tham chiếu và quy định rõ ý nghĩa null |
| Tắt một chức năng | Dùng boolean `false` hoặc thuộc tính mode có ý nghĩa |
| Không có phần tử trong danh sách | Dùng `[]` và kiểm tra quy tắc merge |
| Xóa giá trị mặc định ở nguồn thấp | Thiết kế semantics xóa/disable tường minh; không dựa vào YAML null |
| Phân biệt chưa cấu hình với giá trị zero | Dùng wrapper như `Integer` thay vì `int` khi cần |

Trước khi triển khai, nên viết một bảng ngắn cho mỗi property quan trọng: có bắt buộc không, có cho phép empty không, null có ý nghĩa gì, giá trị mặc định đến từ đâu, nguồn nào được phép ghi đè và khi sai thì ứng dụng fail-fast hay dùng fallback.

**Điểm ghi nhớ:** Absent nghĩa là nguồn không cung cấp property; null là giá trị null theo định dạng nguồn nhưng không hoạt động như một giá trị ghi đè thông thường trong Spring property resolution; empty string là một giá trị chuỗi thực sự. `false`, `0` và collection rỗng cũng là các giá trị tường minh. Hãy biểu diễn đúng ý định trong YAML/biến môi trường, xác thực bằng `@ConfigurationProperties` và kiểm thử cả thứ tự ưu tiên lẫn hành vi refresh.
