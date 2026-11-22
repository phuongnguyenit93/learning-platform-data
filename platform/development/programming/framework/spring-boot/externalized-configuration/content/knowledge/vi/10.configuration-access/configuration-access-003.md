# Thuộc tính bắt buộc với `getRequiredProperty` và kiểm tra `containsProperty` trong Spring Boot

## 1. Bài toán: cấu hình có thật sự được cung cấp không?

Spring Boot có thể lấy cấu hình từ nhiều nguồn: `application.yml`, `application.properties`, tệp bên ngoài JAR, biến môi trường hệ điều hành, Java system properties và đối số dòng lệnh. Ứng dụng thường cần phân biệt hai tình huống:

- **Thuộc tính tùy chọn:** không được cung cấp thì dùng mặc định hoặc tắt một chức năng.
- **Thuộc tính bắt buộc:** thiếu giá trị thì phải báo lỗi sớm, thay vì khởi động với cấu hình sai và chỉ gặp sự cố khi xử lý yêu cầu.

Ví dụ, cổng HTTP có thể dùng mặc định, nhưng địa chỉ dịch vụ thanh toán hay tên một topic bắt buộc có thể không được phép thiếu.

Spring Framework cung cấp giao diện `PropertyResolver`, và `Environment` kế thừa giao diện đó. Hai phương thức quan trọng là:

~~~java
boolean exists = environment.containsProperty("payment.gateway.url");
String required = environment.getRequiredProperty("payment.gateway.url");
~~~

`containsProperty` trả về trạng thái **có thể tra cứu được giá trị** cho tên property; `getRequiredProperty` trả về giá trị nếu có, nhưng ném ngoại lệ nếu không tra cứu được.

> Phân biệt quan trọng: **“Có property” không đồng nghĩa “giá trị hợp lệ cho nghiệp vụ”**. Chuỗi rỗng, khoảng trắng, URL sai và số ngoài giới hạn vẫn cần được kiểm tra riêng.

## 2. `Environment` và `PropertyResolver` nằm ở đâu?

Trong ứng dụng Spring Boot, `Environment` là một lớp trừu tượng để truy cập cấu hình hiệu lực. Nó kết hợp các `PropertySource` theo thứ tự ưu tiên và trả về giá trị của một property cụ thể.

Sơ đồ khái quát:

~~~text
                  Nguồn cấu hình
      +---------------------------------------+
      | --payment.gateway.url=...             |
      | -Dpayment.gateway.url=...             |
      | PAYMENT_GATEWAY_URL=...               |
      | application-prod.yml                  |
      | application.yml                       |
      | default properties                    |
      +---------------------------------------+
                          |
                          v
                    Environment
                          |
                 PropertyResolver API
                          |
           +--------------+----------------+
           |              |                |
      getProperty()  containsProperty() getRequiredProperty()
           |              |                |
     lấy giá trị     hỏi có giá trị    thiếu thì lỗi
~~~

Không phải file nào được nạp cuối cũng thắng mọi nguồn khác. Spring Boot áp dụng **thứ tự ưu tiên nguồn cấu hình**, sau đó giải quyết từng property theo tên. Khi tra cứu `payment.gateway.url`, một giá trị ở nguồn có ưu tiên cao sẽ thắng giá trị cùng tên ở nguồn thấp hơn.

Ví dụ:

~~~yaml
# application.yml
payment:
  gateway:
    url: https://sandbox.example.test
    connect-timeout-ms: 2000
~~~

Nếu môi trường chạy có biến `PAYMENT_GATEWAY_URL=https://payments.example.test`, `Environment` có thể trả về URL production từ biến môi trường, trong khi `connect-timeout-ms` vẫn lấy giá trị `2000` từ file.

Cả `containsProperty` và `getRequiredProperty` đều làm việc trên **hệ thống cấu hình hiệu lực**, không bị giới hạn chỉ trong `application.yml`.

## 3. So sánh các phương thức truy cập property

| Phương thức | Khi có property | Khi thiếu property | Mục đích |
| --- | --- | --- | --- |
| `getProperty("app.name")` | Trả về `String` | Trả về `null` | Giá trị tùy chọn |
| `getProperty("app.name", "default")` | Trả về giá trị hiện có | Trả về `"default"` | Có giá trị dự phòng |
| `containsProperty("app.name")` | Thường trả về `true` khi giá trị có thể tra cứu | Trả về `false` | Kiểm tra hiện diện |
| `getRequiredProperty("app.name")` | Trả về `String` | Ném `IllegalStateException` | Giá trị bắt buộc |
| `getRequiredProperty("app.port", Integer.class)` | Chuyển giá trị sang `Integer` | Ném lỗi khi thiếu; giá trị sai kiểu cũng có thể gây lỗi chuyển đổi | Giá trị bắt buộc có kiểu |

Các overload chính thường dùng:

~~~java
environment.getProperty("app.name");
environment.getProperty("app.name", "Demo");
environment.getProperty("app.port", Integer.class);
environment.getProperty("app.port", Integer.class, 8080);

environment.containsProperty("app.name");
environment.getRequiredProperty("app.name");
environment.getRequiredProperty("app.port", Integer.class);
~~~

Để hiểu kỹ hơn:

- `getProperty` phù hợp khi vắng property là một trạng thái hợp lệ.
- `getProperty(..., defaultValue)` tránh việc mã gọi phải xử lý `null` trong trường hợp muốn fallback.
- `containsProperty` chỉ hỏi trạng thái hiện diện; nó không tự đánh giá URL, password hay phạm vi số.
- `getRequiredProperty` phù hợp khi **không có giá trị** là một lỗi cấu hình.
- Bản overload có kiểu cần thêm bước **chuyển đổi kiểu**; không thể giả định chuỗi bất kỳ chuyển được thành `Integer`, `Boolean` hoặc kiểu tùy chỉnh.

Các phương thức này thuộc `org.springframework.core.env.PropertyResolver`; `Environment` là giao diện thường được inject để dùng chúng trong ứng dụng Spring.

## 4. Kiểm tra hiện diện bằng `containsProperty`

### 4.1. Ví dụ đơn giản

File `application.yml`:

~~~yaml
app:
  region: vn
  feature:
    enabled: false
~~~

Trong một component:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class FeatureInspector {
    public FeatureInspector(Environment environment) {
        boolean hasRegion = environment.containsProperty("app.region");
        boolean hasFlag = environment.containsProperty("app.feature.enabled");
        boolean hasMissing = environment.containsProperty("app.unknown");

        System.out.println("region present: " + hasRegion);
        System.out.println("feature flag present: " + hasFlag);
        System.out.println("unknown present: " + hasMissing);
    }
}
~~~

Nếu không có nguồn bổ sung khai báo `app.unknown`, các kết quả lần lượt là `true`, `true` và `false`.

Điểm dễ nhầm: `app.feature.enabled=false` **vẫn là một giá trị được khai báo**. Không nên dùng `containsProperty("app.feature.enabled")` để kết luận tính năng được bật hay tắt. Hãy đọc **giá trị boolean**:

~~~java
Boolean enabled = environment.getProperty(
        "app.feature.enabled", Boolean.class, false);
~~~

Trong ví dụ, `enabled` là `false` mặc dù `containsProperty` trả về `true`.

### 4.2. Không nên kiểm tra tên một nhánh YAML như một giá trị đơn

Với cấu hình:

~~~yaml
app:
  client:
    host: api.example.test
    port: 443
~~~

Các property dạng leaf thường có tên:

~~~text
app.client.host
app.client.port
~~~

Không nên giả định:

~~~java
environment.containsProperty("app.client")
~~~

phải trả về `true` chỉ vì YAML có khóa cha `client:`. Khi YAML được làm phẳng thành các thuộc tính, nhánh `app.client` có thể **không có giá trị vô hướng trực tiếp**. Hãy hỏi các khóa thực sự cần, ví dụ `app.client.host` và `app.client.port`.

### 4.3. Kiểm tra rồi lấy giá trị

Mẫu đơn giản:

~~~java
if (environment.containsProperty("app.region")) {
    String region = environment.getProperty("app.region");
    // Sử dụng region sau khi kiểm tra hợp lệ nếu cần.
}
~~~

Mẫu này có ích khi cần phân biệt “được cung cấp” với “không được cung cấp”. Tuy nhiên, nếu chỉ muốn lấy giá trị với mặc định, viết ngắn gọn hơn:

~~~java
String region = environment.getProperty("app.region", "vn");
~~~

Với một property **bắt buộc**, dùng `getRequiredProperty` trực tiếp thường rõ ý hơn việc kiểm tra `containsProperty` rồi tự ném ngoại lệ.

## 5. Dùng `getRequiredProperty` để báo lỗi khi thiếu key

### 5.1. Cú pháp cơ bản

~~~java
String gatewayUrl = environment.getRequiredProperty(
        "payment.gateway.url");
~~~

Nếu property tồn tại ở một nguồn cấu hình có hiệu lực, method trả về `String`. Nếu không tìm thấy giá trị phù hợp, method ném `IllegalStateException`.

Ví dụ ứng dụng không có `payment.gateway.url` trong file, environment, system properties hay nguồn khác:

~~~java
String gatewayUrl =
        environment.getRequiredProperty("payment.gateway.url");
~~~

Ứng dụng sẽ không nhận `null` như khi dùng `getProperty` mà đi vào nhánh ngoại lệ. Điều này hữu ích để tránh âm thầm dùng cấu hình rỗng cho một dependency bắt buộc.

Thông báo lỗi có thể chỉ rõ property không tìm thấy. Không nên dựa vào nguyên văn thông báo lỗi như một API ổn định để viết logic xử lý; hãy dựa vào **kiểu ngoại lệ và quy tắc thiếu property**.

### 5.2. Phiên bản có kiểu

~~~java
Integer timeoutMs = environment.getRequiredProperty(
        "payment.gateway.connect-timeout-ms", Integer.class);
~~~

Với:

~~~properties
payment.gateway.connect-timeout-ms=2500
~~~

giá trị trả về là số nguyên `2500`. Nếu property thiếu, phương thức báo lỗi bắt buộc. Nếu property có giá trị `abc`, bước chuyển đổi sang `Integer` có thể thất bại với một ngoại lệ chuyển đổi kiểu, **khác** với lỗi không tìm thấy property.

Vì vậy cần phân biệt:

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Key `payment.gateway.connect-timeout-ms` không được khai báo | Lỗi thiếu property bắt buộc |
| Key có giá trị `2500` | Chuyển thành `Integer 2500` |
| Key có giá trị `not-a-number` | Lỗi chuyển đổi kiểu |
| Key có giá trị `-10` | Có thể chuyển thành `Integer -10`, nhưng **không hợp lệ theo nghiệp vụ** nếu timeout phải dương |

`getRequiredProperty` không có nghĩa nó sẽ tự kiểm tra phạm vi giá trị như min/max. Việc thẩm định semantic thuộc trách nhiệm ứng dụng hoặc hệ thống validation.

## 6. Trường hợp đặc biệt: thiếu key, rỗng, trắng, `false` và `0`

Một trong những nguồn lỗi cấu hình phổ biến là gộp mọi giá trị “không như mong muốn” thành “không có property”.

Giả sử một ứng dụng cần `app.api-key`. Hãy phân biệt:

| Giá trị cấu hình | `containsProperty` | `getRequiredProperty` | Đủ điều kiện làm secret bắt buộc? |
| --- | --- | --- | --- |
| Không có property ở bất kỳ nguồn nào | `false` | Báo lỗi thiếu property | Không |
| `app.api-key=` | Thường `true` vì chuỗi rỗng là giá trị hiện diện | Có thể trả về `""` | **Không**, phải kiểm tra blank |
| `app.api-key=   ` | Có thể `true` | Có thể là chuỗi whitespace hoặc chịu quy tắc parser | **Không**, phải kiểm tra blank |
| `app.feature.enabled=false` | `true` | Trả về chuỗi `"false"` | Giá trị boolean hợp lệ, không phải thiếu |
| `app.retry-count=0` | `true` | Trả về `"0"` | Có thể hợp lệ tùy yêu cầu |
| `app.timeout-ms=-1` | `true` | Trả về `"-1"` hoặc số `-1` khi chuyển kiểu | Không hợp lệ nếu timeout bắt buộc dương |

`containsProperty` kiểm tra **sự hiện diện của một giá trị có thể giải quyết**, không thực hiện kiểm thử `isBlank()` hay xác minh độ mạnh của API key.

Muốn yêu cầu một chuỗi thực sự có nội dung:

~~~java
String apiKey = environment.getRequiredProperty("app.api-key");

if (apiKey.isBlank()) {
    throw new IllegalStateException(
            "Required configuration app.api-key must not be blank");
}
~~~

Với chuỗi có ý nghĩa phụ thuộc nghiệp vụ, ngoài `isBlank()` có thể phải kiểm tra schema URL, pattern tên topic, min/max, danh sách enum được phép hoặc các ràng buộc bảo mật khác.

**Không ghi trực tiếp giá trị secret vào thông báo ngoại lệ hay log.** Chỉ ghi **tên property** và lý do không hợp lệ.

## 7. Ví dụ Spring Boot hoàn chỉnh: fail-fast khi thiếu cấu hình

Giả sử một ứng dụng cần ba giá trị để kết nối hệ thống thanh toán:

~~~yaml
# src/main/resources/application.yml
payment:
  gateway:
    connect-timeout-ms: 2500
~~~

Hai giá trị `payment.gateway.base-url` và `payment.gateway.api-key` không được đóng gói trong JAR vì sẽ do môi trường triển khai cung cấp.

### 7.1. Định nghĩa đối tượng settings

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;

public record GatewaySettings(
        URI baseUrl,
        String apiKey,
        Duration connectTimeout) {
}
~~~

### 7.2. Xác minh khi Spring tạo bean

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class GatewayConfiguration {

    @Bean
    GatewaySettings gatewaySettings(Environment environment) {
        String baseUrl = environment.getRequiredProperty(
                "payment.gateway.base-url");

        String apiKey = environment.getRequiredProperty(
                "payment.gateway.api-key");

        Integer timeoutMs = environment.getRequiredProperty(
                "payment.gateway.connect-timeout-ms", Integer.class);

        if (baseUrl.isBlank()) {
            throw new IllegalStateException(
                    "payment.gateway.base-url must not be blank");
        }
        if (apiKey.isBlank()) {
            throw new IllegalStateException(
                    "payment.gateway.api-key must not be blank");
        }
        if (timeoutMs <= 0) {
            throw new IllegalStateException(
                    "payment.gateway.connect-timeout-ms must be positive");
        }

        URI endpoint;
        try {
            endpoint = URI.create(baseUrl);
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException(
                    "payment.gateway.base-url is not a valid URI", ex);
        }

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalStateException(
                    "payment.gateway.base-url must be an absolute HTTPS URI");
        }

        return new GatewaySettings(
                endpoint, apiKey, Duration.ofMillis(timeoutMs));
    }
}
~~~

Khi Spring tạo bean `GatewaySettings`, các property bắt buộc được kiểm tra. Với bean thông thường không bị trì hoãn tạo, cấu hình sai sẽ gây lỗi khởi tạo context thay vì chỉ phát hiện khi gọi gateway lần đầu. Đây là ví dụ **fail-fast** ở thời điểm khởi động.

Lệnh cung cấp cấu hình qua môi trường Unix:

~~~bash
export PAYMENT_GATEWAY_BASE_URL=https://payments.example.test
export PAYMENT_GATEWAY_API_KEY="example-secret-from-secret-manager"
java -jar app.jar
~~~

Giá trị minh họa trên không phải khóa thật; trong production hãy inject secret từ môi trường được bảo vệ hoặc secret manager, không hard-code vào repository hoặc đưa vào log.

Trong ví dụ:

- `payment.gateway.connect-timeout-ms` đến từ `application.yml`.
- `payment.gateway.base-url` được OS environment cung cấp.
- `payment.gateway.api-key` được OS environment cung cấp.
- `getRequiredProperty` lấy **giá trị hiệu lực** sau khi Spring xét thứ tự ưu tiên property source.
- `isBlank()`, kiểm tra `timeoutMs > 0` và URI HTTPS là **validation bổ sung**, không phải chức năng của `getRequiredProperty`.

### 7.3. Lỗi xuất hiện ở đâu?

Nếu biến `PAYMENT_GATEWAY_API_KEY` không được cung cấp và không có nguồn khác khai báo `payment.gateway.api-key`, lời gọi `getRequiredProperty` sẽ ném ngoại lệ. Vì bean cấu hình không tạo được, Spring Boot thông thường sẽ báo lỗi startup của application context.

Nếu giá trị được cung cấp nhưng là chuỗi rỗng, `getRequiredProperty` có thể trả về chuỗi đó, còn kiểm tra `isBlank()` sẽ từ chối.

Nếu `connect-timeout-ms` chứa văn bản không thể chuyển sang số nguyên, ứng dụng có thể thất bại ngay tại bước chuyển đổi kiểu trước khi tới kiểm tra `<= 0`.

## 8. `containsProperty` dùng cho tính năng tùy chọn

Đối với một giá trị tùy chọn, có thể chỉ bật logic khi cấu hình được cung cấp rõ ràng.

Ví dụ:

~~~yaml
app:
  reporting:
    enabled: false
~~~

Trong Java:

~~~java
Boolean enabled = environment.getProperty(
        "app.reporting.enabled", Boolean.class, false);

if (Boolean.TRUE.equals(enabled)) {
    // Bật reporting.
}
~~~

Đây thường là mẫu phù hợp hơn:

~~~java
if (environment.containsProperty("app.reporting.enabled")) {
    // Không đồng nghĩa reporting đang bật.
}
~~~

Vì giá trị `false` vẫn khiến `containsProperty` trả về `true`.

Một trường hợp hợp lý để dùng `containsProperty` là muốn biết **người triển khai có khai báo override hay không**, chẳng hạn:

~~~java
if (!environment.containsProperty("app.reporting.sample-rate")) {
    // Không có override; chọn policy nội bộ phù hợp.
} else {
    Integer sampleRate = environment.getRequiredProperty(
            "app.reporting.sample-rate", Integer.class);

    if (sampleRate < 0 || sampleRate > 100) {
        throw new IllegalStateException(
                "app.reporting.sample-rate must be between 0 and 100");
    }
}
~~~

Ở đây ý nghĩa của `containsProperty` là “có khai báo cấu hình riêng không?”, còn việc định dạng và kiểm tra khoảng giá trị thuộc các bước tiếp theo.

## 9. Khác biệt với `getProperty(..., defaultValue)`

Nếu property thực sự tùy chọn và có một giá trị fallback được chấp nhận, `getProperty` có overload lấy default:

~~~java
String locale = environment.getProperty("app.locale", "vi-VN");

Integer retryCount = environment.getProperty(
        "app.retry-count", Integer.class, 3);
~~~

Nếu không có property `app.locale`, Spring trả về `vi-VN`. Nếu không có `app.retry-count`, trả về số nguyên `3`.

Không nên dùng fallback vô điều kiện cho những cấu hình **bắt buộc**. Ví dụ:

~~~java
String gatewayUrl = environment.getProperty(
        "payment.gateway.base-url",
        "https://sandbox.example.test");
~~~

Đoạn mã có thể khiến production âm thầm kết nối tới sandbox nếu quên inject URL triển khai. Khi một URL bắt buộc theo chính sách, dùng `getRequiredProperty` và validation sẽ diễn đạt ý định rõ hơn.

So sánh ba cách:

~~~java
// Thiếu thì null: phù hợp với tùy chọn.
String a = environment.getProperty("app.value");

// Thiếu thì dùng default: phù hợp khi fallback là chủ đích.
String b = environment.getProperty("app.value", "fallback");

// Thiếu thì lỗi: phù hợp khi không được phép bỏ qua.
String c = environment.getRequiredProperty("app.value");
~~~

Không có phương thức nào là “tốt nhất” trong mọi trường hợp; chúng biểu diễn **contract cấu hình khác nhau**.

## 10. `containsProperty` không cho biết property đến từ đâu

Giả sử ứng dụng có:

~~~yaml
# application.yml
app:
  mode: sandbox
  timeout-ms: 1000
~~~

Khi khởi động:

~~~bash
APP_MODE=production java -jar app.jar --app.timeout-ms=2500
~~~

Nếu không có nguồn ưu tiên cao hơn trong ví dụ:

~~~java
environment.containsProperty("app.mode");        // true
environment.getRequiredProperty("app.mode");      // "production"
environment.containsProperty("app.timeout-ms");  // true
environment.getRequiredProperty(
        "app.timeout-ms", Integer.class);         // 2500
~~~

Cả hai property đều “có giá trị”, nhưng đến từ **nguồn khác nhau**. `containsProperty` chỉ cho biết hiện diện, không chỉ ra là YAML, biến môi trường hay command-line arguments.

Khi cần chẩn đoán nguồn gốc, hãy dùng công cụ quan sát có kiểm soát như các endpoint Spring Boot Actuator phù hợp hoặc kiểm tra `PropertySources` theo API. Cần hạn chế quyền truy cập và che những thông tin nhạy cảm. Không dùng output debug để công khai secret.

### 10.1. Relaxed names và tên biến môi trường

Với Spring Boot, biến môi trường thường dùng chữ hoa và dấu gạch dưới để tương ứng với property dạng dấu chấm/dấu gạch ngang. Ví dụ:

| Property dạng thông dụng | Biến môi trường |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `app.mode` | `APP_MODE` |
| `payment.gateway.base-url` | `PAYMENT_GATEWAY_BASEURL` |
| `payment.gateway.connect-timeout-ms` | `PAYMENT_GATEWAY_CONNECTTIMEOUTMS` |

Quy tắc biểu diễn chuẩn cho binding từ canonical property name sang environment variable là thay dấu `.` bằng `_`, **bỏ** dấu `-` rồi chuyển thành chữ hoa. Tùy phiên bản, API tra cứu và binding có thể có các biến thể tên được hỗ trợ; khi cấu hình thật, nên sử dụng dạng chuẩn và kiểm tra thực tế.

Ví dụ khi dùng `Environment.getRequiredProperty("payment.gateway.base-url")`, source từ môi trường cần cung cấp property mà hệ thống resolve được dưới tên đó. Đừng giả định tên biến tùy ý với nhiều dấu gạch dưới luôn được ánh xạ đúng.

## 11. Phân biệt `getRequiredProperty` với `@Value`

Một cách quen thuộc để inject property:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayClient {

    public GatewayClient(
            @Value("${payment.gateway.base-url}") String baseUrl) {
        // Dùng baseUrl.
    }
}
~~~

Nếu placeholder bắt buộc không giải quyết được, quá trình khởi tạo bean thường lỗi khi Spring xử lý injection. Tuy nhiên `@Value` là **cơ chế injection placeholder**, không phải cùng một API với `Environment.getRequiredProperty`.

So sánh:

| Cách | Điểm mạnh | Điểm cần lưu ý |
| --- | --- | --- |
| `Environment.getRequiredProperty("key")` | Explicit, dễ đặt logic kiểm tra, có overload chuyển kiểu | Phải tự quản lý chỗ gọi và validation |
| `@Value` | Ngắn khi inject ít property | Nhiều thuộc tính rời rạc khiến bảo trì khó, validation phức tạp |
| `@ConfigurationProperties` | Bind một nhóm thuộc tính theo kiểu Java rõ ràng | Cần đăng ký lớp cấu hình và validation phù hợp |

Nếu cấu hình có nhiều field liên quan, `@ConfigurationProperties` thường cho cấu trúc rõ hơn so với hàng chục lệnh `getRequiredProperty` trong các bean khác nhau.

## 12. Cấu hình nhóm bằng `@ConfigurationProperties` và Bean Validation

Đối với cấu hình ứng dụng quy mô lớn, Spring Boot hỗ trợ binding một nhóm property thành đối tượng Java, sau đó kiểm tra các điều kiện ràng buộc với Jakarta Bean Validation.

Ví dụ file:

~~~yaml
payment:
  gateway:
    base-url: https://payments.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

Record:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @NotNull Duration connectTimeout,
        @Min(0) int maxRetries) {
}
~~~

Đăng ký quét:

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

Nếu project dùng Spring Boot 3.x, các annotation validation là `jakarta.validation.*`. Để Bean Validation hoạt động, cần có implementation phù hợp, thường thông qua dependency `spring-boot-starter-validation`.

Lợi ích:

- `@NotBlank` từ chối chuỗi thiếu, rỗng hoặc toàn whitespace theo semantic của Bean Validation.
- `@NotNull` từ chối giá trị null.
- `@Min(0)` kiểm tra giới hạn dưới cho số lần retry.
- `Duration` có thể bind giá trị như `5s` theo cơ chế conversion của Spring Boot.

Cấu hình kiểu record là một ví dụ; có thể dùng Java class với getter/setter và constructor binding khi phù hợp. `@ConfigurationProperties` không đồng nghĩa rằng mọi ràng buộc tự có sẵn: cần **annotation validation** hoặc logic kiểm tra riêng cho các quy tắc nghiệp vụ.

### 12.1. Khi nào vẫn nên dùng `getRequiredProperty`?

Dùng `getRequiredProperty` khi:

- Cần một vài thuộc tính độc lập mà việc khai báo cả lớp cấu hình là không cần thiết.
- Muốn kiểm tra sớm một giá trị tại một điểm khởi tạo xác định.
- Cần thuật toán kiểm tra điều kiện phức tạp trước khi tạo dependency.
- Đang viết thành phần hạ tầng tương tác trực tiếp với `Environment`.

Dùng `@ConfigurationProperties` với validation khi:

- Có một nhóm cấu hình gồm nhiều trường.
- Cần conversion kiểu, cấu trúc rõ ràng và tính nhất quán.
- Muốn thông báo lỗi binding/validation tập trung hơn.
- Muốn đơn giản hóa mã nghiệp vụ và dễ kiểm thử cấu hình.

Hai cách có thể tồn tại đồng thời trong một ứng dụng. Không cần gọi `getRequiredProperty` cho từng field nếu một configuration properties bean đã đảm nhiệm việc bind và validate các trường đó.

## 13. Đặt kiểm tra ở đâu để lỗi xuất hiện sớm?

Cùng một `getRequiredProperty` nhưng **thời điểm gọi** quyết định thời điểm lỗi xuất hiện.

| Nơi gọi | Khi nào thường chạy | Rủi ro hoặc lợi ích |
| --- | --- | --- |
| Constructor của bean singleton tạo sớm | Trong lúc khởi tạo context | Có thể phát hiện thiếu cấu hình lúc startup |
| Method `@Bean` trả về một dependency bắt buộc | Trong lúc Spring tạo bean đó | Thuận tiện cho fail-fast nếu bean không lazy |
| `ApplicationRunner` | Sau khi context đã được tạo | Vẫn có thể fail startup, nhưng xảy ra ở giai đoạn muộn hơn |
| Phương thức nghiệp vụ chỉ chạy khi có request | Khi tính năng được gọi | Có thể phát hiện quá muộn |
| Bean `@Lazy` | Khi bean thực sự được tạo | Không bảo đảm lỗi xuất hiện trong startup |

Khuyến nghị thực tế: cấu hình bắt buộc cho toàn bộ dịch vụ nên được **kiểm tra khi khởi tạo dependency** hoặc trong lớp `@ConfigurationProperties` có validation. Không nên để kết nối đến một service quan trọng chỉ thất bại khi request production đầu tiên đến.

Tuy nhiên, nếu một tính năng **không luôn được bật**, giá trị bắt buộc cho tính năng ấy có thể chỉ cần kiểm tra khi feature được bật. Ví dụ, không cần bắt buộc có `email.smtp.password` khi chức năng email đã chủ động tắt.

## 14. Kiểm tra một tập các thuộc tính bắt buộc

Khi cần nhiều property, có hai chiến lược:

### 14.1. Lấy tuần tự và lỗi tại key đầu tiên bị thiếu

~~~java
String host = environment.getRequiredProperty("app.remote.host");
String user = environment.getRequiredProperty("app.remote.user");
String token = environment.getRequiredProperty("app.remote.token");
~~~

Ưu điểm: mã ngắn, lỗi phát sinh ngay. Nhược điểm: có thể phải sửa và khởi động lại nhiều lần nếu thiếu đồng thời nhiều key.

### 14.2. Thu thập danh sách các key thiếu trước khi fail

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.env.Environment;

public final class RequiredConfigChecker {
    private RequiredConfigChecker() {}

    public static void verify(Environment environment) {
        List<String> missing = new ArrayList<>();

        for (String key : List.of(
                "app.remote.host",
                "app.remote.user",
                "app.remote.token")) {
            if (!environment.containsProperty(key)) {
                missing.add(key);
            }
        }

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                    "Missing required configuration keys: " + missing);
        }
    }
}
~~~

Cách này tổng hợp **những key không có giá trị resolve được**, nhưng **chưa** bắt các key rỗng/blank hoặc giá trị sai định dạng. Muốn tổng hợp cả các vi phạm đó, cần bổ sung validation sau khi tra cứu.

Trong một hệ thống lớn, Bean Validation trên `@ConfigurationProperties` thường là lựa chọn hiệu quả hơn để thể hiện nhiều ràng buộc theo nhóm.

## 15. `getRequiredProperty` và xử lý placeholder

Một giá trị cấu hình có thể chứa placeholder tham chiếu một property khác:

~~~properties
app.remote.url=https://${REMOTE_HOST}/api
~~~

`getRequiredProperty("app.remote.url")` tìm thấy key `app.remote.url`, nhưng quá trình giải quyết giá trị có thể cần thêm `REMOTE_HOST`. Nếu placeholder không giải quyết được theo cấu hình đang dùng, ứng dụng có thể gặp lỗi ở giai đoạn resolve hoặc binding.

Cần phân biệt:

1. **Bản thân key được yêu cầu có tồn tại hay không?**
2. **Các placeholder bên trong giá trị có giải quyết được hay không?**
3. **Giá trị sau khi resolve có hợp lệ cho nghiệp vụ hay không?**

Các câu hỏi này không hoàn toàn tương đương. Một chuỗi URL chứa placeholder chưa được giải quyết không phải URL hợp lệ cho mọi ứng dụng.

Spring Framework cũng có `resolvePlaceholders(...)` và `resolveRequiredPlaceholders(...)` khi bạn cần xử lý các placeholder trong chuỗi một cách trực tiếp. Đừng nhầm các API giải quyết placeholder với `getRequiredProperty` vốn lấy giá trị của một property theo tên key.

## 16. Khi property đến từ các nguồn có ưu tiên khác nhau

### 16.1. Hai nguồn cùng khai báo một key

File:

~~~yaml
app:
  region: vn
  max-items: 100
~~~

Lệnh chạy:

~~~bash
APP_REGION=apac java -jar demo.jar --app.max-items=200
~~~

Khi dùng hành vi mặc định và không có nguồn ưu tiên cao hơn:

~~~java
environment.getRequiredProperty("app.region");                // "apac"
environment.getRequiredProperty("app.max-items", Integer.class); // 200
~~~

`getRequiredProperty` không chọn “file cấu hình” theo tên. Nó dùng giá trị hiệu lực do `Environment` xác định.

### 16.2. Một nguồn có key nhưng giá trị không dùng được

Giả sử file có:

~~~properties
app.max-items=100
~~~

nhưng nguồn có ưu tiên cao hơn cung cấp:

~~~bash
APP_MAXITEMS=invalid java -jar demo.jar
~~~

Nếu property trên được resolve thành `"invalid"`, việc gọi:

~~~java
environment.getRequiredProperty("app.max-items", Integer.class);
~~~

sẽ không tự bỏ qua nguồn sai kiểu để lấy số `100` từ nguồn ưu tiên thấp. Trước tiên property đã được chọn theo ưu tiên; chuyển đổi không thành công là một **lỗi cấu hình phải sửa**.

Hành vi này quan trọng khi chẩn đoán: không nên cho rằng cứ có một giá trị hợp lệ trong `application.yml` thì ứng dụng sẽ tự dùng nó nếu override hỏng.

### 16.3. Source động và thời gian tra cứu

`containsProperty` và `getRequiredProperty` là các lời gọi vào `Environment` tại thời điểm thực thi. Trong những ứng dụng có nguồn cấu hình thay đổi động, giữa hai lần gọi có thể có khác biệt về dữ liệu nguồn. Vì vậy, nếu cần một giá trị để dùng, việc **đọc một lần rồi validate và giữ trong settings object** thường dễ kiểm soát hơn kiểu gọi `containsProperty` rồi gọi `getRequiredProperty` ở nhiều thời điểm khác nhau.

Đối với config data thông thường của Spring Boot, phần lớn giá trị được nạp ở startup và được bind trong giai đoạn tạo bean; sửa file bên ngoài sau khi chạy không mặc nhiên kích hoạt refresh bean.

## 17. Những lỗi thường gặp

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “`containsProperty(key) == true` tức giá trị hợp lệ.” | Chỉ cho biết property hiện diện/resolve được; cần kiểm tra blank, format, range, domain rule. |
| “`containsProperty(key)` trả về false nếu giá trị là `false`.” | `false` là giá trị boolean, không phải thiếu property. |
| “`getRequiredProperty` luôn trả về chuỗi khác rỗng.” | Nó bảo đảm property có giá trị tra cứu được; chuỗi rỗng có thể vẫn được trả về. |
| “Dùng `getRequiredProperty(key, Integer.class)` sẽ kiểm tra số dương.” | Nó chỉ chuyển kiểu; số âm vẫn có thể là `Integer` hợp lệ. |
| “`getRequiredProperty` chỉ tìm trong `application.yml`.” | Nó tìm trên `Environment`, gồm nhiều property sources. |
| “`containsProperty("app.client")` phải true khi YAML có nhánh `app.client:`.” | Nhánh YAML có thể chỉ có những leaf properties, không có giá trị vô hướng tại khóa cha. |
| “Có default trong file thì override sai kiểu sẽ tự bỏ qua.” | Một override ưu tiên cao sai kiểu có thể làm conversion fail. |
| “Cứ `getRequiredProperty` là startup sẽ fail ngay.” | Phụ thuộc thời điểm method được gọi; gọi muộn thì lỗi cũng muộn. |
| “Dùng `@Value` và `@ConfigurationProperties` giống hệt nhau.” | Một bên inject placeholder, bên kia bind nhóm cấu hình với conversion/validation. |
| “Đưa tên key ra log là đủ để bảo mật secret.” | Vẫn phải bảo vệ nguồn secret, access, endpoint quan sát và tránh log **giá trị** secret. |

## 18. Bài tập: dự đoán kết quả

Có file `application.yml`:

~~~yaml
app:
  name: inventory
  feature:
    enabled: false
  workers: 0
  endpoint: ""
~~~

Không có nguồn nào khác ghi đè các key này.

### Câu hỏi A

~~~java
environment.containsProperty("app.name");
environment.containsProperty("app.feature.enabled");
environment.containsProperty("app.workers");
environment.containsProperty("app.unknown");
~~~

Kết quả lần lượt là `true`, `true`, `true`, `false`. Giá trị `false` và `0` vẫn là các property tồn tại.

### Câu hỏi B

~~~java
environment.getRequiredProperty("app.endpoint");
~~~

Key có giá trị chuỗi rỗng nên bản thân yêu cầu **có property** có thể vẫn được đáp ứng. Nhưng endpoint rỗng không dùng được; logic nghiệp vụ cần kiểm tra `isBlank()` và từ chối.

### Câu hỏi C

~~~java
environment.getRequiredProperty("app.workers", Integer.class);
~~~

Kết quả là `0`. Nếu ứng dụng yêu cầu ít nhất một worker, phải thêm `@Min(1)` hoặc kiểm tra `workers > 0` bằng Java.

### Câu hỏi D

~~~java
environment.getRequiredProperty("app.unknown");
~~~

Lời gọi thất bại với `IllegalStateException` vì key không được tìm thấy.

### Câu hỏi E

Thêm biến môi trường `APP_WORKERS=5` rồi chạy ứng dụng. Giá trị nào thắng?

`getRequiredProperty("app.workers", Integer.class)` có thể trả về `5` vì nguồn OS environment thông thường có ưu tiên cao hơn config data trong file. `containsProperty("app.workers")` vẫn trả về `true`; nó **không** cho biết key đến từ nguồn nào.

## 19. Ghi nhớ

1. `containsProperty(key)` kiểm tra một key có giá trị tra cứu được trong `Environment` hay không; không dùng nó để suy ra boolean flag được bật.
2. `getRequiredProperty(key)` lấy giá trị cấu hình **bắt buộc** và ném `IllegalStateException` khi không tìm thấy.
3. `getRequiredProperty(key, Type.class)` còn thực hiện chuyển đổi kiểu; property sai kiểu và property thiếu là những vấn đề khác nhau.
4. **Có giá trị không bằng hợp lệ**: luôn kiểm tra chuỗi rỗng, URL, các giới hạn số, điều kiện bảo mật và quy tắc nghiệp vụ cần thiết.
5. Đọc và xác minh cấu hình bắt buộc **khi khởi tạo ứng dụng**, thay vì đợi request đầu tiên; với nhóm cấu hình, cân nhắc `@ConfigurationProperties` + Bean Validation.
6. Hai phương thức dùng **cấu hình hiệu lực** sau khi `Environment` xét thứ tự ưu tiên nguồn; chúng không phải công cụ truy vết nguồn gốc hay bảo đảm secret được bảo vệ.

### Tài liệu tham khảo

- Spring Framework Javadoc — `PropertyResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertyResolver.html
- Spring Framework Reference — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
