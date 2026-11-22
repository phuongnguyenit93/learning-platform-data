# Thiết kế thông báo lỗi hữu ích mà không lộ giá trị bí mật trong Spring Boot

## 1. Bối cảnh và mục tiêu

Ứng dụng Spring Boot thường nhận cấu hình từ `application.properties`, `application.yml`, biến môi trường, Java system properties, đối số dòng lệnh, tệp bên ngoài hoặc một secret store. Cấu hình có thể bị thiếu, sai kiểu, không phù hợp với môi trường chạy hoặc vi phạm một ràng buộc nghiệp vụ.

Một thông báo lỗi kiểu:

~~~text
Failed to bind properties under 'payment.gateway'
~~~

cho biết cấu hình có vấn đề, nhưng đôi khi chưa đủ để người vận hành xác định phải sửa khóa nào. Ngược lại, thông báo “chi tiết” theo cách nguy hiểm:

~~~text
Could not bind payment.gateway.api-key='sk_live_EXAMPLE_SECRET'
~~~

lại có thể ghi **giá trị bí mật** vào terminal, file log, log tập trung, hệ thống giám sát và ticket hỗ trợ.

Mục tiêu của bài là thiết kế lỗi cấu hình có hai đặc tính cùng lúc:

1. **Hữu ích:** cho biết lỗi thuộc nhóm gì, xảy ra ở khóa hoặc thành phần nào, cần sửa cấu hình theo cách nào, và có cách tra cứu tài liệu hay mã sự cố.
2. **An toàn:** không tiết lộ password, access token, secret, private key, connection string chứa credential, header xác thực hoặc giá trị nhạy cảm khác qua message, exception, log, tracing, metrics, API hay endpoint quản trị.

Đây là chủ đề thuộc nhóm **kiểm tra hợp lệ** của Spring Boot Externalized Configuration, bao gồm `@ConfigurationProperties`, conversion, Bean Validation, xử lý lỗi startup và quan sát trong môi trường triển khai.

**Nguyên tắc trung tâm:** thông báo lỗi cần mô tả **hợp đồng cấu hình bị vi phạm**, không phải in lại **giá trị đầu vào đã gây lỗi**.

## 2. Phân biệt khóa cấu hình với giá trị cấu hình

Một property gồm tên khóa và giá trị:

~~~properties
payment.gateway.endpoint=https://gateway.example.test
payment.gateway.timeout=3s
payment.gateway.api-key=...
~~~

Mức độ nhạy cảm có thể khác nhau:

| Thành phần | Ví dụ | Cách xử lý trong diagnostic |
| --- | --- | --- |
| Khóa cấu hình thường | `payment.gateway.timeout` | Có thể hiển thị nếu được kiểm soát |
| Tên khóa nhạy cảm nhưng ổn định | `payment.gateway.api-key` | Có thể nêu tên trong thông báo dành cho operator đáng tin cậy |
| Giá trị secret | API key, password, token | Không bao giờ in lại |
| Giá trị URI có credential | `postgresql://user:pass@host/db` | Không in nguyên URL |
| Header chứa credential | `Authorization: Bearer ...` | Không in |
| Nội dung resource | private key, certificate, Secret volume | Không đính kèm nội dung |
| Đường dẫn/hệ thống nội bộ | đường dẫn mount, hostname nội bộ | Có thể nhạy cảm; chỉ hiển thị khi thực sự cần và đúng đối tượng |
| Tên khóa động chứa user ID | `tenant.<id>.secret` | Có thể tiết lộ danh tính; nên rút gọn hoặc che phần động |

Không nên áp dụng quy tắc cực đoan “tên khóa luôn an toàn”. Một tên khóa tĩnh được đội phát triển quy định thường có thể hiển thị cho người vận hành, nhưng tên khóa chứa dữ liệu do người dùng nhập, thông tin khách hàng hoặc định danh hệ thống nội bộ có thể cũng cần được che.

Cách an toàn là xây **allowlist các định danh lỗi và tên trường được phép công khai**, thay vì ghép thẳng dữ liệu tùy ý vào thông điệp lỗi.

## 3. Có những loại lỗi cấu hình nào?

Trong Spring Boot, lỗi có thể xuất hiện ở nhiều giai đoạn:

1. **Không tìm thấy nguồn cấu hình:** tệp Config Data hoặc import bắt buộc không tồn tại.
2. **Sai cú pháp nguồn:** YAML indentation không hợp lệ, `.properties` escape sai hoặc document activation không đúng.
3. **Không tìm thấy property bắt buộc:** ví dụ thiếu khóa `payment.gateway.api-key`.
4. **Không chuyển đổi được kiểu:** nhập `timeout=tomorrow` trong khi Java yêu cầu `Duration`.
5. **Vi phạm Bean Validation:** timeout âm, chuỗi blank, port vượt phạm vi hoặc collection rỗng.
6. **Vi phạm điều kiện giữa các trường:** bật TLS nhưng chưa cấu hình trust material; bật authentication nhưng thiếu credential.
7. **Lỗi sử dụng tài nguyên:** location của `Resource` hợp lệ về cú pháp nhưng tệp không tồn tại hoặc không đọc được.
8. **Bị nguồn ưu tiên cao hơn ghi đè:** giá trị đúng ở file cơ sở nhưng bị environment variable hoặc command-line argument sai ghi đè.
9. **Cấu hình thay đổi sai thời điểm:** sửa file sau khi bean đã bind mà không restart/reload phù hợp.

Mỗi loại cần thông điệp khác nhau. Một lỗi chuyển kiểu không nên được mô tả như lỗi thiếu file; một lỗi mạng không nên bị báo thành “property không hợp lệ” nếu cú pháp cấu hình đã đúng.

### 3.1. Binding thành công chưa chắc sử dụng thành công

Ví dụ:

~~~properties
payment.gateway.endpoint=https://payment.example.test
~~~

Binder có thể chuyển chuỗi sang `URI` thành công, nhưng endpoint vẫn có thể không truy cập được do DNS, TLS hoặc firewall. Không nên tuyên bố “cấu hình đã hợp lệ hoàn toàn” chỉ vì một field đã được bind.

Tương tự:

~~~properties
payment.gateway.trust-store=file:/etc/payment/trust.pem
~~~

có thể được bind thành Spring `Resource` trước khi code thực sự mở file. Nếu tệp thiếu, lỗi sẽ xuất hiện khi kiểm tra existence hoặc đọc stream. Thông báo cần chỉ ra **thành phần tài nguyên** nào không sẵn sàng mà không in đường dẫn chứa thông tin nhạy cảm ngoài phạm vi cần thiết.

## 4. Phương pháp thiết kế thông báo lỗi an toàn

Một thông báo dành cho operator nên có cấu trúc:

~~~text
[ERROR_CODE] Configuration for <component> is invalid:
<safe-property> <safe-requirement>.
Action: <concrete-remediation>. Reference: <doc-or-runbook>.
~~~

Ví dụ:

~~~text
[CFG-101] Payment gateway configuration is incomplete.
Property: payment.gateway.api-key
Requirement: a non-blank secret must be provided.
Action: configure the secret in the deployment secret source
and restart the service.
~~~

Thông báo trên cung cấp đủ việc cần làm mà không in giá trị API key.

### 4.1. Năm thành phần nên có

| Thành phần | Ví dụ | Lợi ích |
| --- | --- | --- |
| Mã lỗi ổn định | `CFG-101` | Dễ tìm kiếm trong runbook và dashboard |
| Tên thành phần | `payment-gateway` | Xác định phạm vi ảnh hưởng |
| Khóa an toàn | `payment.gateway.api-key` | Chỉ đúng property cần sửa |
| Điều kiện vi phạm | `must be present and non-blank` | Nêu yêu cầu, không in đầu vào |
| Hướng xử lý | `set the deployment secret and restart` | Operator có hành động rõ ràng |

Có thể bổ sung correlation ID, môi trường chạy ở mức không nhạy cảm, tên nguồn cấu hình ở mức khái quát và đường dẫn tài liệu nội bộ đã được cho phép.

### 4.2. Những thành phần không nên đưa vào

Không chứa:

- raw rejected value;
- nội dung secret file;
- header `Authorization`, cookie hoặc credentials;
- `Throwable.getMessage()` không kiểm soát từ một exception chứa giá trị đầu vào;
- toàn bộ `Environment`, `PropertySource`, object `@ConfigurationProperties`;
- stack trace trong response gửi tới client không tin cậy;
- URL chứa `userinfo` hoặc token query parameter;
- output nguyên văn của lệnh in tất cả biến môi trường.

**Không có một bộ lọc duy nhất bảo đảm mọi kênh an toàn**. Cần kiểm soát cả dữ liệu đầu vào, cách tạo lỗi, nơi log được gửi và ai có quyền xem.

## 5. Ví dụ một thông báo tốt và một thông báo xấu

### 5.1. Thiếu credential

**Không nên:**

~~~text
Validation failed for payment.gateway.api-key:
value='' with all environment variables: ...
~~~

Ngay cả việc liệt kê “tất cả biến môi trường” cũng có thể đưa nhiều secret khác vào log.

**Nên:**

~~~text
[CFG-101] Missing required credential for payment gateway.
Property: payment.gateway.api-key
Action: provide the secret through the configured secret source.
~~~

### 5.2. Sai thời gian timeout

**Không nên:**

~~~text
payment.gateway.timeout rejected value='MY_PRIVATE_TEMPLATE'
~~~

**Nên:**

~~~text
[CFG-102] Invalid payment gateway timeout.
Property: payment.gateway.timeout
Requirement: a positive duration such as 500ms, 3s or 1m.
Action: correct the configuration value and restart.
~~~

Đưa **ví dụ định dạng hợp lệ** khác với in lại giá trị sai của người vận hành.

### 5.3. URL có credential

**Không nên:**

~~~text
Database connection failed: jdbc:postgresql://account:password@db.internal/app
~~~

**Nên:**

~~~text
[CFG-103] Database connection configuration is invalid.
Property group: datasource
Action: verify the configured endpoint and credentials.
~~~

Nếu thực sự cần phân biệt DNS/TLS/authentication, tạo mã lỗi riêng dựa trên loại sự cố đã được phân loại an toàn; đừng bắt buộc in toàn bộ connection string.

### 5.4. Resource không đọc được

**Không nên:**

~~~text
Cannot read the private key at /run/secrets/customer-A/token.key:
<raw file contents>
~~~

**Nên:**

~~~text
[CFG-104] Required signing key resource cannot be read.
Property: app.signing.key-resource
Action: verify that the secret volume is mounted and readable.
~~~

Đường dẫn thực tế có thể được dùng trong môi trường chẩn đoán tin cậy khi thực sự cần, nhưng không nên đưa mặc định vào thông báo công khai.

## 6. Dùng `@ConfigurationProperties` để tập trung hợp đồng cấu hình

Giả sử hệ thống thanh toán cần một endpoint HTTP, credential và timeout. Khai báo object có kiểu:

~~~java
package com.example.payment.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentGatewayProperties(
        URI endpoint,
        String apiKey,
        Duration connectTimeout
) {}
~~~

Đăng ký bằng:

~~~java
package com.example.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }
}
~~~

Cấu hình:

~~~yaml
payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    api-key: "${PAYMENT_GATEWAY_SECRET}"
    connect-timeout: 3s
~~~

Giá trị của `PAYMENT_GATEWAY_SECRET` cần được cung cấp bằng cơ chế secret phù hợp. Ví dụ minh họa cú pháp placeholder; không đặt credential thật trong tài liệu hoặc repository.

Lợi ích của `@ConfigurationProperties`:

1. Các key liên quan được gom theo prefix.
2. `URI` và `Duration` được Binder chuyển sang kiểu phù hợp.
3. Có thể khai báo Bean Validation gần property.
4. Service inject một object thay vì tự tra cứu nhiều key rải rác.
5. Có một vị trí rõ để mô tả hợp đồng, validation và tài liệu hướng dẫn vận hành.

Tuy nhiên, **`@ConfigurationProperties` không tự bảo đảm thông báo lỗi có redaction an toàn**. Khi conversion hoặc validation thất bại, framework và các extension có thể tạo mô tả chứa tên field, nguồn, giá trị đầu vào hoặc thông điệp ngoại lệ. Cần kiểm soát luồng log và error reporting tương ứng.

## 7. Kiểm tra sự hiện diện và miền giá trị bằng Bean Validation

Spring Boot có thể tích hợp Jakarta Bean Validation cho `@ConfigurationProperties`. Với Spring Boot 3.x và Jakarta:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import java.net.URI;
import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentGatewayProperties(
        @NotNull URI endpoint,
        @NotBlank String apiKey,
        @NotNull Duration connectTimeout
) {}
~~~

Ứng dụng cần Bean Validation provider, thường được đưa vào qua `spring-boot-starter-validation`.

Ý nghĩa:

- `@NotNull`: object phải tồn tại.
- `@NotBlank`: chuỗi phải khác null, khác rỗng và không chỉ chứa khoảng trắng.
- `@Validated`: yêu cầu thực hiện validation trong cơ chế configuration properties tương ứng.

Đây là cách phát hiện lỗi thiếu cấu hình sớm thay vì đợi đến request đầu tiên.

### 7.1. Constraint message nên nêu yêu cầu, không lặp giá trị

Có thể sử dụng message ngắn:

~~~java
@NotBlank(message = "credential is required")
String apiKey
~~~

Hoặc:

~~~java
@NotNull(message = "endpoint must be configured")
URI endpoint
~~~

Message như vậy không chứa token hoặc API key.

**Nhưng cần lưu ý:** mặc dù một constraint message an toàn, phần mô tả bind failure do Boot hoặc hệ thống log tạo ra **vẫn có thể chứa rejected value hoặc property origin**. Không nên cho rằng chỉ cần viết message không chứa secret thì toàn bộ startup log đã được redacted.

### 7.2. Không dùng annotation sai kiểu

`@NotBlank` dành cho các kiểu chuỗi thích hợp, không dùng trực tiếp cho `URI` hoặc `Duration`. Với các object này, dùng `@NotNull` và quy tắc riêng.

Nếu `connectTimeout` phải dương, có thể dùng một kiểm tra custom phù hợp hoặc một bean-level constraint, vì không thể suy rằng mọi constraint số áp dụng trực tiếp cho `Duration`.

### 7.3. Không tự đưa giá trị sai vào message

Ví dụ có rủi ro:

~~~java
throw new IllegalArgumentException(
    "Invalid API key: " + properties.apiKey()
);
~~~

Thay bằng:

~~~java
throw new IllegalStateException(
    "Payment gateway credential does not satisfy configuration policy"
);
~~~

Những nơi cần phản hồi chi tiết hơn nên dùng mã lỗi và **tên property an toàn** thay vì giá trị.

## 8. Kiểm tra điều kiện liên trường mà không tiết lộ đầu vào

Một hệ thống có thể yêu cầu: nếu bật authentication thì phải có credential. Việc kiểm tra từng field độc lập đôi khi chưa đủ.

Ví dụ một record:

~~~java
import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        boolean authenticationRequired,
        String apiKey
) {
    @AssertTrue(message = "credential is required when authentication is enabled")
    public boolean isCredentialConfigurationValid() {
        return !authenticationRequired
                || (apiKey != null && !apiKey.isBlank());
    }
}
~~~

Thông điệp nêu **điều kiện bị vi phạm**, không in giá trị `apiKey`.

Tuy nhiên, khi thiết kế lớp cấu hình có rule phức tạp:

- cần kiểm tra behavior của Bean Validation provider và phương thức được nhận diện;
- không in object nguyên vẹn trong custom validator;
- không gọi `toString()` trên một record chứa secret để tạo log;
- không biến mọi validation failure thành một mã chung khó hiểu;
- xem xét một custom class-level constraint nếu rule có nhiều field và cần kiểm soát tên lỗi hiển thị.

### 8.1. Bẫy `toString()` của record

Java record tự tạo `toString()` có thể bao gồm **giá trị của các component**:

~~~java
public record RemoteProperties(String endpoint, String apiKey) {}
~~~

Do đó câu lệnh:

~~~java
log.error("Invalid remote configuration: {}", properties);
~~~

có nguy cơ ghi trực tiếp `apiKey`.

**Không log toàn bộ configuration properties object khi có field nhạy cảm.** Nếu bắt buộc tạo một dạng xem chẩn đoán, hãy xây DTO chứa duy nhất thông tin đã được allowlist như trạng thái presence và loại lỗi, không có giá trị secret.

### 8.2. “Ẩn field trong toString” chưa đủ

Dù custom `toString()` loại bỏ secret, các kênh khác như JSON serialization, exception cause, debugger, framework report hoặc object mapping vẫn có thể truy cập field. Một custom `toString()` chỉ bảo vệ **một đường đi hiển thị**, không phải cơ chế redaction tổng quát.

## 9. Kiểm tra URI và timeout nhưng không in giá trị sai

### 9.1. URI hợp lệ về cú pháp vẫn có thể sai chính sách

Binder có thể chuyển một chuỗi thành `URI` dù đó là URI tương đối hoặc dùng scheme không phù hợp cho HTTP.

Ví dụ kiểm tra:

~~~java
import java.net.URI;

public final class ConfigurationRules {
    private ConfigurationRules() {}

    public static void requireHttpsEndpoint(URI endpoint) {
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalStateException(
                "payment.gateway.endpoint must be an absolute HTTPS URI with a host"
            );
        }
    }
}
~~~

Đây là thông báo hữu ích vì cho biết **định dạng bắt buộc**, không in lại URL cấu hình. Đối với endpoint có credential trong userinfo hoặc query, tránh mọi lời gọi `endpoint.toString()` trong đường báo lỗi.

### 9.2. Timeout cần kiểm tra miền giá trị

~~~java
import java.time.Duration;

public static void requirePositiveTimeout(Duration timeout) {
    if (timeout == null || timeout.isZero() || timeout.isNegative()) {
        throw new IllegalStateException(
            "payment.gateway.connect-timeout must be a positive duration"
        );
    }
}
~~~

Khi input `connect-timeout` sai cú pháp, lỗi có thể xuất hiện **trước** khi phương thức trên chạy, ngay tại bước conversion. Vì vậy, thông điệp tự viết sau binding chỉ giải quyết trường hợp **đã convert thành công nhưng không đáp ứng quy tắc**; cần quan tâm cả lỗi conversion do framework tạo.

### 9.3. Không đưa nguyên nhân từ thư viện ra public response

Ví dụ nguy hiểm:

~~~java
catch (Exception ex) {
    return ResponseEntity.internalServerError().body(ex.getMessage());
}
~~~

`ex.getMessage()` có thể chứa URL, credential, giá trị Config Data hoặc chi tiết hệ thống nội bộ.

Với public API, nên trả một lỗi ổn định không chứa các dữ liệu đó, ví dụ `SERVICE_CONFIGURATION_ERROR`, và chỉ cho người vận hành tra cứu correlation ID trong kênh kiểm soát truy cập.

## 10. Phân biệt diagnostic dành cho operator và lỗi trả về API

Một lỗi cấu hình startup thường là **lỗi vận hành nội bộ**. Nếu ứng dụng không thể khởi động, cơ chế triển khai như systemd, container orchestrator hoặc supervisor sẽ ghi nhận startup failure. Người dùng cuối không cần biết tên `spring.datasource.password` hay đường dẫn secret mount.

Nếu dịch vụ vẫn chạy nhưng một subsystem không sẵn sàng, phản hồi API nên tổng quát:

~~~json
{
  "code": "SERVICE_UNAVAILABLE",
  "message": "The requested service is temporarily unavailable.",
  "requestId": "req-opaque-id"
}
~~~

Ở kênh log nội bộ, có thể có:

~~~text
[CFG-104] Signing resource unavailable.
component=signing
property=app.signing.key-resource
requestId=req-opaque-id
action=verify secret mount and permissions
~~~

Hai kênh khác nhau có mục tiêu khác nhau:

| Kênh | Mục tiêu | Có nên hiển thị secret? |
| --- | --- | --- |
| Startup console/log nội bộ | Giúp vận hành chẩn đoán | Không |
| Log tập trung/APM | Phân loại và tương quan sự cố | Không |
| Dashboard/alert | Phát hiện xu hướng và mức ảnh hưởng | Không |
| Public HTTP response | Thông báo an toàn cho client | Không |
| Ticket hỗ trợ | Hướng dẫn sửa cấu hình | Không |
| Security incident channel | Điều tra có kiểm soát | Chỉ dữ liệu cần thiết theo chính sách riêng; tránh sao chép secret |

**Không dựa vào giả định “log nội bộ thì có thể chứa mật khẩu”.** Log thường được sao chép sang nhiều hệ thống, có người truy cập khác nhau và thời gian lưu dài.

## 11. Thiết kế mã lỗi và bảng hành động

Một hệ thống có thể xác định các mã lỗi ổn định:

| Mã | Tình huống | Thông điệp an toàn | Hành động |
| --- | --- | --- | --- |
| `CFG-101` | Thiếu secret bắt buộc | Credential is required | Kiểm tra secret source |
| `CFG-102` | Timeout không hợp lệ | Timeout must be positive | Sửa duration |
| `CFG-103` | Endpoint không phải HTTPS URI tuyệt đối | HTTPS endpoint is required | Sửa endpoint |
| `CFG-104` | Resource không đọc được | Required resource unavailable | Kiểm tra mount và quyền file |
| `CFG-105` | Giá trị enum ngoài miền | Unsupported configuration option | Chọn giá trị trong danh sách hỗ trợ |
| `CFG-106` | Thiếu phần tử cấu hình | At least one destination is required | Thêm phần tử hợp lệ |
| `CFG-107` | Hai cấu hình mâu thuẫn | Incompatible configuration options | Kiểm tra policy liên trường |
| `CFG-108` | Cấu hình của profile không đầy đủ | Profile-specific configuration incomplete | Kiểm tra profile đang active |

Mã lỗi giúp operator và hệ thống giám sát nhận diện nhóm sự cố mà không cần đưa rejected value vào metric label.

Đối với loại lỗi cần phân biệt nhiều phiên bản, mã lỗi nên giữ ý nghĩa ổn định qua thời gian. Có thể thay nội dung runbook mà không đổi mã nếu nguyên nhân vận hành và hành động vẫn như cũ.

### 11.1. Không để mã lỗi chứa dữ liệu động

**Không nên:**

~~~text
CFG-MISSING-sk_live_...-prod
~~~

**Nên:**

~~~text
CFG-101 component=payment-gateway
~~~

Giá trị được chọn từ danh sách tĩnh, không phải tạo bằng nối secret hoặc tên người dùng.

### 11.2. Không đặt giá trị cấu hình vào metric label

Một metric như:

~~~text
config_validation_failure{key="payment.gateway.api-key",code="CFG-101"}
~~~

có thể hữu ích nếu `key` và `code` nằm trong allowlist có cardinality giới hạn. Nhưng không dùng:

~~~text
config_validation_failure{value="<raw-secret>"}
~~~

Ngoài rủi ro bảo mật, dùng giá trị cấu hình làm label gây bùng nổ cardinality và tăng chi phí hệ thống monitoring.

## 12. Safe logging trong Java

Một helper nhỏ giúp thống nhất những gì được phép ghi:

~~~java
package com.example.payment.diagnostics;

import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ConfigurationDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigurationDiagnostics.class);

    private static final Set<String> SAFE_KEYS = Set.of(
            "payment.gateway.api-key",
            "payment.gateway.endpoint",
            "payment.gateway.connect-timeout",
            "app.signing.key-resource"
    );

    private ConfigurationDiagnostics() {}

    public static void missingRequired(String key, String code) {
        String safeKey = SAFE_KEYS.contains(key)
                ? key
                : "restricted-property";

        log.error(
            "Configuration error code={} property={} reason=missing-required-value",
            code, safeKey
        );
    }
}
~~~

Sử dụng:

~~~java
ConfigurationDiagnostics.missingRequired(
        "payment.gateway.api-key", "CFG-101"
);
~~~

Output không chứa secret. Danh sách `SAFE_KEYS` nên được quản lý cùng hợp đồng cấu hình và quy tắc phân quyền của tổ chức.

### 12.1. Không đưa exception làm tham số cuối một cách vô thức

Trong SLF4J, một tham số `Throwable` thường có thể được diễn giải là exception và làm logger in stack trace/cause. Nếu exception chứa rejected value, hành vi này có thể làm lộ bí mật dù format message ban đầu không chứa value.

Ví dụ có rủi ro:

~~~java
log.error("Configuration failed", exception);
~~~

Không nên xem việc in stack trace là mặc định an toàn. Khi exception đến từ Binder, parser, client kết nối hoặc secret manager, hãy biết nó chứa những dữ liệu nào trước khi cho phép log raw.

Thay thế trong kênh mặc định:

~~~java
log.error(
    "Configuration error code=CFG-101 component=payment-gateway action=check-secret-source"
);
~~~

Nếu cần stack trace trong một luồng điều tra đặc biệt, phải có cơ chế sanitize, chính sách truy cập, lưu giữ và kiểm tra kỹ thuật tương ứng; không đơn giản bật stack trace ở log public.

### 12.2. Cẩn thận với structured logging

Structured logging hữu ích nhưng vẫn có thể lộ giá trị:

~~~java
log.atError()
    .addKeyValue("key", "payment.gateway.api-key")
    .addKeyValue("value", apiKey) // Không an toàn.
    .log("Invalid configuration");
~~~

**Quy tắc:** chỉ đưa tên khóa được phép, mã lỗi, tên component và metadata chẩn đoán an toàn. Không đính kèm object cấu hình hoặc toàn bộ `Throwable` khi chưa đánh giá nội dung.

## 13. Một wrapper lỗi cấu hình không chứa dữ liệu nhạy cảm

Ứng dụng có thể định nghĩa một exception chỉ mang thông tin an toàn:

~~~java
package com.example.payment.diagnostics;

public final class SafeConfigException extends RuntimeException {

    private final String code;
    private final String property;

    public SafeConfigException(
            String code,
            String property,
            String safeMessage
    ) {
        super(safeMessage);
        this.code = code;
        this.property = property;
    }

    public String code() {
        return code;
    }

    public String property() {
        return property;
    }
}
~~~

Sử dụng:

~~~java
if (apiKey == null || apiKey.isBlank()) {
    throw new SafeConfigException(
        "CFG-101",
        "payment.gateway.api-key",
        "Required credential is missing"
    );
}
~~~

Điều này giảm nguy cơ secret xuất hiện trong `exception.getMessage()`.

Tuy nhiên:

- Không để `safeMessage` đến từ input không tin cậy.
- `property` nên là một tên trong allowlist.
- Không truyền một `cause` chưa được kiểm soát nếu kênh log sẽ in cause.
- Một exception an toàn không tự lọc tất cả diagnostics khác mà framework có thể phát ra.
- Không dùng lỗi này để che một lỗi thật mà không giữ đủ thông tin vận hành.

### 13.1. Nên phân loại bằng enum khi mã lỗi cố định

Nếu hệ thống có nhiều thành phần, có thể dùng một enum nội bộ:

~~~java
public enum ConfigErrorCode {
    REQUIRED_CREDENTIAL,
    INVALID_TIMEOUT,
    INVALID_ENDPOINT,
    RESOURCE_UNAVAILABLE
}
~~~

Khi log, map enum sang mã như `CFG-101`. Cách này tránh việc developer gõ mã lỗi khác nhau tùy chỗ và dễ viết test kiểm tra log không có secret.

## 14. Vòng đời startup và vị trí nên kiểm tra cấu hình

Trong ứng dụng Spring Boot thông thường:

1. Spring Boot tìm và nạp Config Data, bao gồm profile-specific files và imports phù hợp.
2. `Environment` được xây dựng với thứ tự ưu tiên property sources.
3. Container tạo configuration properties bean.
4. Binder chuyển đổi kiểu, liên kết property và chạy validation nếu được cấu hình.
5. Bean khác được tạo và sử dụng cấu hình.
6. Ứng dụng sẵn sàng phục vụ request sau khi quá trình startup hoàn tất.

**Không phải mọi validation do ứng dụng tự viết đều chạy trước bước binding.** Nếu field `Duration` nhận giá trị không parse được, Binder có thể thất bại ngay ở bước 4, trước khi bạn có cơ hội chạy phương thức kiểm tra domain.

Vì vậy cần thiết kế bảo vệ nhiều lớp:

- Đầu vào triển khai được kiểm tra theo schema hoặc policy trước khi process khởi động.
- `@ConfigurationProperties` mô tả các field có kiểu.
- Bean Validation diễn tả các yêu cầu hợp lệ.
- Custom invariant kiểm tra điều kiện nghiệp vụ.
- Diagnostic/failure reporting bảo đảm không sao chép rejected values ra các kênh không tin cậy.
- Hệ thống logging, monitoring và support có quy tắc redaction riêng.

### 14.1. Không dùng ApplicationRunner để thay thế binding validation

`ApplicationRunner` chạy sau khi application context được tạo. Nếu binding đã thất bại trong lúc tạo bean, runner sẽ không được chạy. Vì vậy nó phù hợp với một số kiểm tra bổ sung sau startup, nhưng **không thể thay thế hoàn toàn việc xử lý lỗi conversion và validation ở giai đoạn context initialization**.

### 14.2. Không “bắt rồi tiếp tục” khi thiếu cấu hình bắt buộc

Khi thiếu credential bắt buộc hoặc endpoint quan trọng, việc nuốt exception và chạy bằng giá trị mặc định sai có thể nguy hiểm hơn việc fail fast.

Một thông báo lỗi an toàn không đồng nghĩa phải cho phép ứng dụng khởi động trong trạng thái không hợp lệ. Mục tiêu là **thất bại đúng lúc, với thông tin đủ dùng và không lộ secret**.

## 15. Kiểm soát thông điệp mặc định từ Spring Boot

Spring Boot có những cơ chế phân tích lỗi startup (failure analysis). Trong nhiều tình huống, nó tạo thông tin về property, nguồn cấu hình, nguyên nhân binding hoặc hướng hành động.

Điều này giúp chẩn đoán, nhưng cũng có một rủi ro: một error report mặc định có thể chứa **giá trị bị từ chối** hoặc thông điệp ngoại lệ được tạo từ giá trị đó. Không được giả định mọi version của Spring Boot, mọi loại exception và mọi extension sẽ che toàn bộ bí mật.

Đặc biệt với `@ConfigurationProperties`:

- Một chuỗi secret được bind vào `String` vẫn có thể xuất hiện trong thông điệp validation hoặc log nếu code ghi lại rejected value.
- Nếu một trường bí mật được bind vào một kiểu không phù hợp và conversion thất bại, thông điệp lỗi có thể phản ánh input gốc.
- Nếu custom validator ghép giá trị vào message, framework có thể in lại message đó.
- Một thư viện ngoài Spring Boot có thể log nguyên exception hoặc object mà không áp dụng chính sách sanitization của ứng dụng.

### 15.1. Thiết kế fallback error reporting

Trong deployment nhạy cảm, cần cân nhắc cơ chế báo lỗi startup đã kiểm soát, ví dụ:

~~~text
[CFG-102] Configuration binding failed.
component=payment-gateway
property=payment.gateway.connect-timeout
requirement=positive duration
action=check deployment configuration
~~~

Nếu cần tự xây FailureAnalyzer hoặc handler tương ứng với phiên bản Spring Boot, nó nên:

1. Nhận diện **loại lỗi**, không in raw input.
2. Trích tên property từ danh sách được phép hoặc map sang định danh cố định.
3. Trả một thông điệp và hành động xử lý cố định.
4. Không truyền `cause.getMessage()` hoặc `cause.toString()` ra output.
5. Có test chứng minh secret không xuất hiện trong startup logs.

**Lưu ý:** một custom FailureAnalyzer không tự ngăn mọi logger khác ghi exception. Muốn bảo đảm không rò rỉ, cần kiểm soát đường log tổng thể, kể cả application/framework/library loggers và pipeline log sau đó.

### 15.2. Hạn chế debug logging khi có secret

Mức `TRACE`/`DEBUG` có thể hữu ích khi tìm nguồn Config Data, nhưng cũng tăng số lượng thông tin về source, paths và trạng thái quá trình binding. Không bật log chi tiết toàn cục ở production chỉ để tìm một lỗi cấu hình.

Nếu cần bật một logger cụ thể để điều tra, nên:

- giới hạn thời gian và phạm vi;
- sử dụng môi trường không chứa secret thật khi có thể;
- xác minh log thực tế không lộ rejected values;
- kiểm soát quyền truy cập và thời gian lưu;
- khôi phục cấu hình logging về mức thông thường sau điều tra.

## 16. Origin tracking: hữu ích nhưng cần che thông tin phù hợp

Spring Boot có thể theo dõi nguồn gốc của một property được nạp, ví dụ từ file nào, document nào hoặc vị trí nào trong Config Data. Thông tin này giúp người vận hành biết **sửa ở đâu**.

Ví dụ chẩn đoán an toàn ở mức khái quát:

~~~text
[CFG-102] Invalid timeout configuration.
source-kind=external-config
property=payment.gateway.connect-timeout
action=check duration syntax in the deployment configuration
~~~

Một thông báo chi tiết hơn cho operator đáng tin cậy có thể bao gồm tên file cấu hình đã được duyệt, chẳng hạn `application-prod.yml`. Nhưng không nên in mọi đường dẫn tuyệt đối chứa tên người dùng, ID khách hàng, đường dẫn secret mount nội bộ hoặc URI có credential.

### 16.1. Mức độ chi tiết theo vai trò

Có thể phân tầng:

- **Public client:** mã lỗi và correlation ID, không tên property hoặc đường dẫn.
- **Operator:** mã lỗi, component, tên property allowlisted, loại nguồn và hành động.
- **Maintainer có quyền điều tra:** origin ở mức cần thiết, vẫn không gồm secret value.
- **Security team:** dấu vết điều tra theo chính sách kiểm soát riêng, không mặc định sao chép credential.

Đây là một lựa chọn thiết kế security, không phải một thứ tự “ngầm có sẵn” mà Spring Boot tự phân quyền thay ứng dụng.

### 16.2. Không đặt secret vào metadata

Không nên xây tên file, tên metric hoặc tên property source từ API key. Nếu chuỗi động đã chứa secret thì ngay cả việc chỉ in **origin** cũng có thể tiết lộ dữ liệu đó.

## 17. Config Data và nguồn có độ ưu tiên cao

Một lỗi dễ làm người vận hành nhầm là đang sửa một file nhưng giá trị hiệu lực lại được lấy từ nguồn khác.

Ví dụ file đóng gói:

~~~properties
payment.gateway.connect-timeout=3s
~~~

Nhưng process chạy với:

~~~bash
java -jar payment.jar --payment.gateway.connect-timeout=invalid-duration
~~~

Command-line argument thường có độ ưu tiên cao hơn file. Binder sẽ thấy giá trị sai từ command line chứ không dùng `3s` trong JAR.

Thông báo hữu ích:

~~~text
[CFG-102] Payment gateway connect timeout is invalid.
source-kind=command-line
property=payment.gateway.connect-timeout
action=provide a valid duration and restart
~~~

Không cần in rejected value.

### 17.1. Secret từ command-line argument có thể bị lộ ngoài ứng dụng

Ngay cả khi log được sanitize, truyền mật khẩu qua command-line argument có thể làm secret xuất hiện trong process inspection, shell history hoặc hệ thống ghi lệnh triển khai.

Ví dụ nên tránh khi có giải pháp bảo mật hơn:

~~~bash
java -jar payment.jar --payment.gateway.api-key=<secret>
~~~

Nên cấp credential qua secret management của hạ tầng, ví dụ secret volume, cơ chế injection an toàn hoặc dịch vụ quản lý bí mật. **Biến môi trường cũng không phải tuyệt đối an toàn**: tùy môi trường, chúng có thể xuất hiện trong process diagnostics, container inspection hoặc crash reports.

Chọn secret source dựa trên threat model của tổ chức, không chỉ vì giá trị không xuất hiện trong file Git.

### 17.2. Không sao chép toàn bộ cấu hình khi báo lỗi precedence

Để xác định nguồn thắng, nhiều người thử in tất cả `PropertySource` hoặc `Environment`. Đây là cách nguy hiểm vì có thể tiết lộ secret từ các key không liên quan.

Thay vào đó, chẩn đoán **một khóa được cho phép** bằng cách xác định loại nguồn thắng và rule bị vi phạm, tránh in value. Nếu cần xem value, chỉ dùng dữ liệu giả lập trong test hoặc kênh được kiểm soát nghiêm ngặt theo quy trình bảo mật.

## 18. Secret trong YAML, properties và Config Tree

### 18.1. Bí mật trong file cấu hình

~~~yaml
payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    api-key: "${PAYMENT_GATEWAY_SECRET}"
~~~

Cách này không đặt secret thật trong YAML, nhưng secret vẫn được nạp vào process khi chạy. Nếu code log object `PaymentGatewayProperties` hoặc Binder error report chứa rejected value, secret vẫn có thể rò rỉ.

### 18.2. Config Tree và file được mount

Spring Boot hỗ trợ nhập cấu hình từ cây file, ví dụ:

~~~properties
spring.config.import=optional:configtree:/etc/app-secrets/
~~~

Giả sử một file trong cây có tên property tương ứng và chứa nội dung secret. Việc sử dụng Config Tree giúp quản lý nguồn dữ liệu tách khỏi bản JAR, **không bảo đảm nội dung được tự che ở mọi kênh log**.

Thông báo khi thiếu một resource:

~~~text
[CFG-101] Required credential is unavailable.
source-kind=secret-volume
property=payment.gateway.api-key
action=check secret mount and deployment permissions
~~~

Không in nội dung file hoặc hash của secret. Hash của một bí mật có entropy thấp vẫn có thể hỗ trợ đoán lại qua brute-force hoặc kiểm tra từ điển.

### 18.3. Đường dẫn secret cũng là metadata

Trong một số hệ thống, đường dẫn mount có thể chứa tenant ID hoặc tên hệ thống riêng. Nếu không cần thiết cho việc sửa lỗi, dùng `source-kind=secret-volume` hoặc một alias đã cho phép thay vì toàn bộ path.

## 19. Actuator `/actuator/env` và `/actuator/configprops`

Spring Boot Actuator có các endpoint giúp quan sát `Environment` và bean cấu hình, tiêu biểu:

- `/actuator/env`: thông tin về property sources và các property.
- `/actuator/configprops`: các bean configuration properties đã đăng ký/bind.

Các endpoint này có thể hỗ trợ chẩn đoán, nhưng **cũng là bề mặt tiết lộ cấu hình**. Spring Boot có cơ chế sanitization/che giá trị và thiết lập kiểm soát việc hiển thị giá trị, nhưng hành vi chính xác phụ thuộc phiên bản, cấu hình security và cách expose endpoint.

Nguyên tắc vận hành:

1. Không công khai endpoint cấu hình ra Internet.
2. Xác thực và phân quyền cho những người dùng thật sự cần.
3. Duy trì chính sách che giá trị nhạy cảm; không tắt sanitization vì muốn xem nhanh secret.
4. Kiểm tra cả property từ custom source và các class `@ConfigurationProperties` tự viết.
5. Chỉ cấp quyền truy cập rộng rãi tới mã lỗi và trạng thái an toàn, không phải raw config.
6. Coi một phản hồi JSON của Actuator cũng là dữ liệu có thể đi qua reverse proxy, logging và giám sát.

Một cấu hình `management.endpoint.env.show-values` hoặc `management.endpoint.configprops.show-values` có thể ảnh hưởng việc hiển thị chi tiết tùy phiên bản Boot. Không tùy tiện đặt chế độ hiển thị giá trị ở production mà không hiểu phân quyền và chính sách bảo mật của phiên bản đang dùng.

### 19.1. Không dựa hoàn toàn vào pattern tên key

Cơ chế tự che các key như `password`, `secret` hoặc `token` rất hữu ích, nhưng một khóa tên `app.connection-string` cũng có thể chứa credential. Một giá trị nhạy cảm có thể nằm dưới tên key không gợi ý rằng đó là secret.

Nên dùng **danh mục cấu hình nhạy cảm do ứng dụng định nghĩa**, chính sách chặn giá trị mặc định ở kênh public và kiểm thử cụ thể các endpoint/fields có thể chứa bí mật.

## 20. Trace, exception và hệ thống giám sát

Bí mật không chỉ rò qua một câu `log.error(...)`. Chúng có thể được sao chép qua:

- Exception messages và stack traces.
- MDC hoặc structured log context.
- HTTP request/response body logging.
- Tracing span attributes.
- Metrics tags.
- Error aggregation platforms.
- Diagnostic dump khi ứng dụng crash.
- Health details trả về từ endpoint.
- Ticket hỗ trợ có đính kèm log hoặc screenshot terminal.

Ví dụ một tracing attribute không nên chứa giá trị cấu hình:

~~~text
config.value = sk_live_EXAMPLE_SECRET
~~~

Thay bằng:

~~~text
config.error_code = CFG-101
config.component = payment-gateway
~~~

Các attribute phải có tập giá trị ổn định, an toàn và ít cardinality.

### 20.1. Health check nên hiển thị trạng thái

Khi thiếu cấu hình bắt buộc, một health component có thể báo `DOWN` với mã lý do an toàn nếu hệ thống được thiết kế để tiếp tục khởi động. Nhưng không nên xuất mật khẩu hoặc path bí mật trong `details` của health response.

Nếu thiếu credential làm hệ thống không thể vận hành đúng, ứng dụng có thể fail fast ở startup; lúc đó health endpoint cũng có thể chưa sẵn sàng. Hai cơ chế không loại trừ nhau.

### 20.2. Không đưa config object vào baggage

Tracing baggage thường được truyền giữa các service. Không đặt secret hoặc đối tượng cấu hình vào baggage để “các service cùng debug”; như vậy dữ liệu có thể lan sang hệ thống khác mà không có quyền truy cập tương ứng.

## 21. Cách kiểm tra lỗi bắt buộc với thông báo có hành động rõ

Một ví dụ minh họa class cấu hình record:

~~~java
package com.example.payment.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentGatewayProperties(
        URI endpoint,
        String apiKey,
        @DefaultValue("3s") Duration connectTimeout
) {
    public void requireUsableConfiguration() {
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalStateException(
                "CFG-103: payment.gateway.endpoint must be an absolute HTTPS URI"
            );
        }

        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException(
                "CFG-101: payment.gateway.api-key is required"
            );
        }

        if (connectTimeout == null
                || connectTimeout.isZero()
                || connectTimeout.isNegative()) {
            throw new IllegalStateException(
                "CFG-102: payment.gateway.connect-timeout must be positive"
            );
        }
    }
}
~~~

Trong ví dụ, mọi lỗi đều sử dụng **literal cố định** thay vì nối đầu vào. Tuy nhiên, phương thức `requireUsableConfiguration()` phải được gọi tại một điểm vòng đời phù hợp nếu muốn bảo đảm fail fast. Tự định nghĩa phương thức trong record không khiến Spring Boot gọi nó tự động.

### 21.1. Kiểm tra tự động bằng validation

Một phương án khác là dùng `@Validated`, `@NotNull`, `@NotBlank` và custom constraints. Với Bean Validation, framework có thể gọi validation trong quá trình binding phù hợp khi provider được đăng ký.

Điểm cần quan tâm về an toàn log: **dù validation message là chuỗi cố định, thông báo lỗi cuối do framework tạo vẫn cần được kiểm chứng để không lộ rejected value**.

### 21.2. Không in object khi kiểm tra

Không nên:

~~~java
throw new IllegalStateException(
    "Invalid payment configuration: " + this
);
~~~

Với record, `this.toString()` có thể đưa API key vào exception. Cách dùng static message như ví dụ đầu tránh được lỗi này trong chính exception ứng dụng tạo.

## 22. Default value và tính minh bạch của lỗi

Spring Boot hỗ trợ default ở nhiều nơi, ví dụ:

~~~java
@DefaultValue("3s") Duration connectTimeout
~~~

Hoặc:

~~~properties
payment.gateway.connect-timeout=${PAYMENT_TIMEOUT:3s}
~~~

Default hữu ích cho cấu hình có fallback hợp lý. Nhưng đối với secret bắt buộc, dùng default không an toàn có thể che lỗi triển khai:

~~~properties
# Không nên dùng trong hệ thống thật:
payment.gateway.api-key=${PAYMENT_GATEWAY_SECRET:demo-password}
~~~

Khi biến môi trường bị thiếu, ứng dụng có thể tiếp tục chạy với credential mẫu. Điều này có thể nguy hiểm hơn việc startup thất bại.

**Nguyên tắc:**

- Default cho timeout, retry count hoặc chế độ thử nghiệm khi nghiệp vụ cho phép.
- Không hardcode mật khẩu, API key hoặc private key thực trong code hoặc file.
- Dùng validation để phân biệt “được phép thiếu” với “bắt buộc có”.
- Nếu giá trị được phép thiếu trong local nhưng bắt buộc ở production, mô tả rule bằng profile/condition và validation liên trường thay vì tạo default giả.

Không mặc định rằng một property không có giá trị sẽ gây lỗi; cần thiết kế rõ ràng yêu cầu của ứng dụng.

## 23. Lỗi thiếu secret khác lỗi xác thực thất bại

Đây là hai loại sự cố khác nhau:

| Tình huống | Thời điểm | Diagnostic an toàn |
| --- | --- | --- |
| Thiếu key cấu hình | Binding/validation lúc startup | `CFG-101 Required credential missing` |
| Có key nhưng định dạng không hợp lệ | Conversion/validation | `CFG-109 Invalid credential format` |
| Có credential nhưng remote từ chối | Khi gọi dịch vụ | `AUTH-401 Remote authentication rejected` |
| Secret file không đọc được | Khi mở resource | `CFG-104 Required secret resource unavailable` |
| Credential hết hạn | Khi xác minh theo cơ chế riêng | `AUTH-402 Credential needs rotation` |

Không đưa token vào thông báo của bất kỳ trường hợp nào.

Một lỗi `401` từ remote server có thể có response body chứa chi tiết nhạy cảm. Nếu log nguyên body/exception, ứng dụng có thể rò rỉ cả dữ liệu của remote service. Hãy map nguyên nhân về mã lỗi nội bộ an toàn và giữ thông tin điều tra tại kênh được kiểm soát.

## 24. Kiểm thử không rò rỉ secret

Không thể đánh giá thông báo có an toàn chỉ bằng cách đọc một vài dòng code. Cần test quan sát thực tế khi ứng dụng xử lý những cấu hình sai.

Có thể dùng **secret canary** là một chuỗi giả, ví dụ:

~~~text
FAKE_SECRET_CANARY_DO_NOT_LOG_42
~~~

Đây phải là giá trị giả, không phải credential thật.

### 24.1. Các ca kiểm thử nên có

| Ca | Đầu vào thử nghiệm | Điều cần khẳng định |
| --- | --- | --- |
| Thiếu credential | Không có property bắt buộc | Có mã `CFG-101`, không có raw secret |
| Credential blank | Chuỗi rỗng hoặc khoảng trắng | Thông báo nêu yêu cầu, không in giá trị |
| Credential chứa canary | Chuỗi canary giả | Không xuất hiện trong captured logs và error report |
| Timeout sai kiểu | Chuỗi giả không parse được | Có mã/nhóm lỗi an toàn, không in rejected value |
| URI chứa userinfo | URI giả có user/password | Không in URI đầy đủ |
| Resource thiếu | File path giả có tenant ID | Không in nội dung file hoặc path nhạy cảm |
| Nhiều PropertySource | File hợp lệ, source cao hơn sai | Nêu source kind phù hợp mà không in raw value |
| Startup failure | ApplicationContext không khởi động | Captured stderr/stdout an toàn |
| Actuator | Endpoint env/configprops được bật có kiểm soát | Secret vẫn bị che theo cấu hình |
| Public API | Subsystem cấu hình lỗi | Trả mã lỗi/correlation ID, không lộ config |

### 24.2. Dùng `OutputCaptureExtension`

Spring Boot Test có utility hỗ trợ thu log/output. Ví dụ minh họa một diagnostic do ứng dụng chủ động phát ra:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(OutputCaptureExtension.class)
class SafeDiagnosticsTest {

    @Test
    void errorMessageDoesNotContainRawSecret(CapturedOutput output) {
        String secretCanary = "FAKE_SECRET_CANARY_DO_NOT_LOG_42";

        ConfigurationDiagnostics.missingRequired(
                "payment.gateway.api-key", "CFG-101"
        );

        assertTrue(output.getAll().contains("CFG-101"));
        assertFalse(output.getAll().contains(secretCanary));
    }
}
~~~

**Giới hạn của ví dụ:** đây chỉ kiểm tra helper diagnostic, không kiểm chứng toàn bộ Spring Boot binding failure. Cần có thêm **integration test khởi động context với canary sai kiểu/vi phạm constraint** rồi kiểm tra stdout, stderr, stack trace và dữ liệu xuất tới pipeline log thực tế.

### 24.3. Không test với secret thật

Không lấy token production vào unit test, log chẩn đoán hoặc snapshot. Dùng chuỗi giả có dấu hiệu rõ ràng để khẳng định hệ thống không lộ dữ liệu. Có thể đặt nhiều canary cho các lớp khác nhau: password, API key, URI userinfo, resource path.

### 24.4. Kiểm tra lỗi của framework và library

Một bộ test đầy đủ nên cố ý gây lỗi:

- `BindException` hoặc lỗi liên quan binding.
- Lỗi chuyển kiểu `String -> Duration`, `URI`, enum.
- Bean Validation failure.
- Lỗi đọc Config Data.
- Exception từ secret manager.
- Lỗi HTTP/TLS có message chứa endpoint.
- Config object bị in do một logger hoặc exception serializer.

Không chỉ kiểm tra helper do nhóm tự viết; các kênh mặc định mới thường gây bất ngờ.

## 25. Ví dụ quy trình xử lý sự cố dành cho vận hành

Giả sử deploy production bị lỗi khởi động. Người vận hành thấy:

~~~text
[CFG-102] Invalid configuration for payment gateway.
property=payment.gateway.connect-timeout
source-kind=environment
requirement=positive duration
action=check environment configuration and restart
runbook=CONFIG/PAYMENT/CFG-102
~~~

Quy trình đề xuất:

1. Tra cứu mã `CFG-102` trong runbook.
2. Xác nhận property `payment.gateway.connect-timeout` được cấp từ nguồn environment của deployment.
3. Kiểm tra giá trị trong công cụ quản lý cấu hình có phân quyền, **không dán nguyên value vào ticket/chat**.
4. Sửa thành duration hợp lệ theo hướng dẫn, ví dụ `500ms` hoặc `3s`.
5. Restart/redeploy theo quy trình.
6. Xác nhận ứng dụng khởi động và health checks đạt yêu cầu.
7. Theo dõi lỗi cấu hình còn xuất hiện không; không cần in các biến môi trường khác.

Nếu khóa liên quan là secret:

~~~text
[CFG-101] Required credential unavailable.
property=payment.gateway.api-key
source-kind=secret-store
action=verify secret reference, access and deployment permissions
~~~

Operator kiểm tra secret reference và quyền truy cập qua hệ thống quản lý bí mật, không đưa secret thật vào logs. Runbook có thể mô tả cách xác minh **sự tồn tại và quyền sử dụng** mà không yêu cầu công khai giá trị.

## 26. Những lỗi thiết kế thường gặp

### 26.1. In rejected value để “dễ debug”

~~~java
log.error("Bad value for key {}: {}", key, value);
~~~

Nếu `value` có thể chứa secret, đây là rủi ro trực tiếp. Thay bằng error code và requirement. Khi cần chẩn đoán một cấu hình phức tạp, sử dụng source kind và field allowlist.

### 26.2. Log nguyên `Throwable`

Một exception có thể chứa source, raw rejected value hoặc nội dung thư viện. Không log raw exception mặc định trong đường xử lý config nhạy cảm. Kiểm tra cả logging framework và startup failure analysis.

### 26.3. In toàn bộ `Environment`

Việc gọi `environment.getPropertySources()` rồi liệt kê key/value để tìm một lỗi có thể lộ secret không liên quan. Chỉ đọc metadata cần thiết của một khóa cụ thể và không log value.

### 26.4. Dùng `@ToString` trên class chứa secret

Các code generator như Lombok có thể tạo `toString()` gồm tất cả field. Với record, Java tự sinh `toString()` theo component. Không dùng các output đó cho cấu hình có credential.

### 26.5. Chỉ dựa vào mask tên `password`

Có secret nằm ở `app.endpoint`, `app.private-key`, `app.header-value`, `app.credentials-json` hoặc tên tự định nghĩa. Phải phân loại nguồn dữ liệu và kiểm tra output thực tế; pattern tên key là một lớp phòng vệ chứ không phải lời đảm bảo.

### 26.6. Dùng default password khi validation thất bại

Fallback secret giả hoặc password mẫu có thể khiến deployment sai vẫn khởi động. Với giá trị bắt buộc, fail fast với message an toàn.

### 26.7. Trả nguyên stack trace cho client

Người dùng cuối chỉ cần biết request không thể phục vụ và mã tham chiếu. Stack trace là dữ liệu nội bộ, có thể chứa đường dẫn, tên lớp, URI và thông tin cấu hình.

### 26.8. Ghi secret vào MDC/tracing

Một lần đưa secret vào MDC hoặc span có thể khiến nó được nhân bản vào rất nhiều bản ghi, khó thu hồi. Chỉ dùng metadata an toàn và có cardinality thấp.

### 26.9. Tin rằng Actuator mặc định luôn an toàn

Sanitization và cách expose endpoint phụ thuộc phiên bản, cấu hình và quyền truy cập. Kiểm thử trực tiếp `/actuator/env` và `/actuator/configprops` với giá trị giả trước khi triển khai.

### 26.10. Không tính đến property precedence

Cùng một khóa có thể bị override ở command line hoặc environment. Người vận hành chỉ sửa file trong JAR sẽ không giải quyết lỗi nếu source khác đang thắng. Diagnostic nên nêu **loại nguồn** khi có thể, nhưng không cần giá trị thực tế.

## 27. Checklist trước khi phát hành

- [ ] Mỗi field quan trọng có hợp đồng rõ: bắt buộc, mặc định, phạm vi hợp lệ và nguồn cấp.
- [ ] Dùng `@ConfigurationProperties` có kiểu phù hợp, kết hợp `@Validated` khi cần.
- [ ] Error message mô tả requirement, không ghép rejected value.
- [ ] Mã lỗi là hằng hoặc enum được định nghĩa trước.
- [ ] Tên property trong diagnostic là tên tĩnh/allowlisted; không chứa dữ liệu động nhạy cảm.
- [ ] Không log record/JavaBean config object có secret bằng `toString()`.
- [ ] Không log raw `Throwable` hoặc cause nếu chưa kiểm chứng chúng an toàn.
- [ ] Startup failure analysis và conversion failures đã được kiểm thử với canary.
- [ ] Console, file log, stdout/stderr, structured log, APM và tracing không chứa canary.
- [ ] Public API không trả tên secret, raw config hoặc stack trace.
- [ ] Actuator `env`/`configprops` được bảo vệ và đã xác minh sanitization thực tế.
- [ ] Secret không được truyền qua command line hoặc ticket khi có kênh an toàn hơn.
- [ ] Default không khiến ứng dụng âm thầm chạy với credential mẫu.
- [ ] Runbook chỉ dẫn cách kiểm tra secret reference/quyền, không yêu cầu in giá trị.
- [ ] Chẩn đoán có thể phân biệt nguồn thắng mà không dump tất cả property sources.
- [ ] Quy trình restart/redeploy sau khi sửa Config Data được mô tả rõ.
- [ ] Chính sách quyền xem và thời gian lưu log được áp dụng.
- [ ] Các lỗi chưa biết vẫn có mã lỗi chung an toàn, không fallback sang `exception.toString()`.

## 28. Mẫu quy định thông điệp trong nhóm phát triển

Một quy ước ngắn có thể ghi vào tài liệu nội bộ:

~~~text
CONFIGURATION ERROR CONTRACT

Required:
  - Stable error code
  - Safe component name
  - Allowlisted property identifier (operator channel only)
  - Requirement that failed
  - Concrete remediation step
  - Optional correlation ID or runbook reference

Forbidden:
  - Raw property value
  - Raw secret, token, password or credential URI
  - Full configuration object or Environment dump
  - Unreviewed Throwable message/cause/stack trace
  - Sensitive file contents or unreviewed absolute path
  - Secret-derived metric label or trace attribute

Public API:
  - Generic error code and request ID only

Verification:
  - Automated test with canary secrets
  - Runtime checks of logs and Actuator exposure
~~~

Quy ước này không phải tính năng tự động của Spring Boot; nó là **hợp đồng bảo mật của ứng dụng và quy trình vận hành**. Spring Boot cung cấp binding, validation và diagnostics, còn đội phát triển chịu trách nhiệm kiểm soát thông tin đi ra.

## 29. Tóm tắt

Thiết kế thông báo lỗi cấu hình tốt trong Spring Boot là bài toán kết hợp **type-safe binding**, **validation**, **property-source precedence**, **observability** và **bảo mật dữ liệu**.

Một thông báo hữu ích trả lời: *thành phần nào lỗi, tên cấu hình nào bị ảnh hưởng, yêu cầu đúng là gì, operator cần làm gì tiếp theo?* Nó **không** phải trả lời bằng cách in toàn bộ rejected value hoặc secret.

Các thực hành quan trọng nhất:

1. Gom cấu hình trong `@ConfigurationProperties` và xác định rõ trường bắt buộc/mặc định.
2. Dùng Bean Validation hoặc custom invariants với message mô tả quy tắc, không chứa input.
3. Coi giá trị bí mật là dữ liệu không được đưa vào error message, log, metric, trace, API hoặc ticket.
4. Cẩn thận với `toString()` của record, raw exceptions và các failure reports do framework/library tạo.
5. Dùng mã lỗi ổn định, source kind, tên property allowlisted và runbook thay cho raw values.
6. Kiểm thử **đường lỗi thật** với canary secret, bao gồm startup failure, logging pipeline và Actuator.
7. Đảm bảo cấu hình bắt buộc không bị che bởi default thiếu an toàn; fail fast và báo lỗi đúng cách.

Khi thực hiện các nguyên tắc này, ứng dụng có thể từ chối cấu hình không hợp lệ ngay lúc khởi động, giúp người vận hành sửa đúng chỗ, mà không biến thông báo lỗi thành một kênh rò rỉ credential.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Framework Reference — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [OWASP Cheat Sheet Series — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
