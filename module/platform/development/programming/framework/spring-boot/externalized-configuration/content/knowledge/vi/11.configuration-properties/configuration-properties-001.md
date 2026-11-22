# Mô hình cấu hình có kiểu và lợi ích của @ConfigurationProperties

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** @ConfigurationProperties

## 1. Vì sao cần mô hình cấu hình có kiểu?

Một ứng dụng Spring Boot thường có nhiều tham số thay đổi theo môi trường: địa chỉ API, thời gian chờ, giới hạn kích thước dữ liệu, số lần retry, cờ tính năng hoặc cấu hình kết nối. Ban đầu, mỗi thành phần có thể đọc một chuỗi từ `Environment` hoặc chèn giá trị bằng `@Value`:

~~~java
@Value("${acme.client.base-url}")
private String baseUrl;

@Value("${acme.client.connect-timeout:3s}")
private String timeout;
~~~

Khi cấu hình lớn dần, cách đọc rời rạc bộc lộ nhiều vấn đề: tên khóa lặp ở nhiều lớp; code phải tự chuyển kiểu; các giá trị liên quan không được nhóm lại; kiểm tra thiếu/sai cấu hình nằm rải rác; khó biết toàn bộ hợp đồng cấu hình của một tính năng.

**`@ConfigurationProperties` giải quyết bài toán bằng cách ánh xạ một nhóm property từ Spring `Environment` vào một Java object có kiểu rõ ràng.** Mỗi object này mô tả hợp đồng cấu hình của một phần ứng dụng. Ví dụ:

~~~text
acme.client.base-url             -> URI
acme.client.connect-timeout      -> Duration
acme.client.max-payload          -> DataSize
acme.client.retry.max-attempts   -> int
acme.client.retry.backoff        -> Duration
~~~

Ứng dụng sử dụng một bean `ClientProperties` với các field tương ứng, thay vì tự giải quyết từng chuỗi ở từng service. Đây là mô hình **type-safe configuration properties**: thuộc tính được bind và chuyển đổi sang kiểu Java trong quá trình khởi tạo/binding.

### Mục tiêu bài học

Sau bài học, bạn có thể:

- Định nghĩa một lớp cấu hình với `@ConfigurationProperties(prefix = "...")`.
- Bind property từ YAML, properties, biến môi trường hoặc CLI thành các kiểu Java và object lồng nhau.
- Đăng ký bean cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- Phân biệt kiểu record bất biến với JavaBean có setter.
- Áp dụng validation để ứng dụng phát hiện cấu hình thiếu hoặc sai ngay khi khởi động.
- Hiểu relaxed binding, default values, precedence và hành vi với list/map.
- Chọn `@ConfigurationProperties` hay `@Value` theo trường hợp, đồng thời nhận biết giới hạn vận hành và bảo mật.

## 2. Cơ chế hoạt động tổng quan

Luồng dữ liệu có thể hình dung:

~~~text
application.yml / application.properties
                 |
OS environment / JVM system properties / CLI
                 |
JSON application properties / config imports / ...
                 |
                 v
      Spring Environment
       (PropertySources)
                 |
                 v
      ConfigurationProperties Binder
       - giải quyết tên và nguồn
       - bind thuộc tính lồng nhau
       - chuyển đổi kiểu dữ liệu
       - áp dụng giá trị mặc định
       - validation nếu đã cấu hình
                 |
                 v
         ClientProperties bean
                 |
                 v
          Service / Component
~~~

Có ba vai trò khác nhau:

1. **Nguồn cấu hình** cung cấp tên khóa và giá trị. Ví dụ `application.yml` hoặc `ACME_CLIENT_BASE_URL` từ môi trường.
2. **Binder** của Spring Boot liên kết các property có prefix với field hoặc tham số constructor, đồng thời thực hiện chuyển kiểu.
3. **Bean cấu hình** giữ các giá trị có kiểu để những thành phần nghiệp vụ sử dụng qua constructor injection.

Bản thân `@ConfigurationProperties` **không đọc file YAML trực tiếp**, cũng không tự quyết định nguồn nào ưu tiên hơn. Việc nạp config data và thứ tự `PropertySource` là cơ chế externalized configuration của Spring Boot; binder sử dụng những giá trị đã được giải quyết từ môi trường đó.

## 3. Ví dụ từ đầu đến cuối với Java record

Giả sử một dịch vụ gọi API bên ngoài cần endpoint, timeout, giới hạn payload, danh sách vùng và chính sách retry.

### 3.1. Khai báo cấu hình trong `application.yml`

~~~yaml
acme:
  client:
    base-url: "https://api.example.test"
    connect-timeout: 3s
    max-payload: 2MB
    allowed-regions:
      - ap-southeast-1
      - ap-northeast-1
    headers:
      x-client-name: catalog
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Các khóa sau khi flatten có dạng:

~~~text
acme.client.base-url
acme.client.connect-timeout
acme.client.max-payload
acme.client.allowed-regions[0]
acme.client.allowed-regions[1]
acme.client.headers.x-client-name
acme.client.retry.max-attempts
acme.client.retry.backoff
~~~

Các giá trị như `3s`, `2MB` và `250ms` là chuỗi theo cú pháp cấu hình của Spring Boot; binder có thể chuyển chúng thành `Duration` hoặc `DataSize`.

### 3.2. Định nghĩa record bất biến

Ví dụ dành cho Spring Boot 3.x và Java 17 trở lên:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "acme.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        DataSize maxPayload,
        List<String> allowedRegions,
        Map<String, String> headers,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
~~~

Ý nghĩa từng phần:

- `@ConfigurationProperties(prefix = "acme.client")` chỉ định nhóm khóa mà binder sẽ sử dụng.
- `baseUrl` nhận `acme.client.base-url` và chuyển thành `URI`.
- `connectTimeout` nhận giá trị như `3s` và chuyển thành `Duration`.
- `maxPayload` nhận `2MB` và chuyển thành `DataSize`.
- `allowedRegions` được bind thành `List<String>`.
- `headers` nhận các entry từ map.
- `retry` là object lồng nhau với `maxAttempts` và `backoff`.

Trong Spring Boot 3, record với một constructor phù hợp được hỗ trợ constructor binding mà **không cần đặt `@ConstructorBinding`** cho trường hợp thông thường. Record giúp giữ tham số cấu hình theo hướng bất biến: các component đọc accessor như `baseUrl()` và `retry().maxAttempts()`, không sửa các field bằng setter.

Điều đó **không có nghĩa** tất cả object bên trong record đều bất biến sâu. Nếu record chứa `List`/`Map` có khả năng thay đổi, phải xem xét ngữ nghĩa và cách sử dụng các collection tương ứng khi cần bảo đảm immutability toàn phần.

### 3.3. Đăng ký lớp cấu hình thành bean

Đặt `@ConfigurationPropertiesScan` trên ứng dụng:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Khi scan trong phạm vi package thích hợp, Spring Boot tìm các lớp được chú thích `@ConfigurationProperties` và đăng ký chúng để binding.

Một lựa chọn khác là đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

Không cần đồng thời dùng cả hai cơ chế cho cùng một lớp. Chọn **scan** khi nhiều lớp cấu hình được đặt theo package convention; chọn **enable tường minh** khi muốn liệt kê những bean cấu hình cần đăng ký.

### 3.4. Sử dụng bean bằng constructor injection

~~~java
package com.example.catalog.service;

import java.net.URI;

import com.example.catalog.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {

    private final ClientProperties config;

    public CatalogClient(ClientProperties config) {
        this.config = config;
    }

    public URI endpoint() {
        return config.baseUrl();
    }

    public int maxAttempts() {
        return config.retry().maxAttempts();
    }
}
~~~

Service nhận **một object cấu hình đã được bind**. Code nghiệp vụ không cần biết các giá trị đến từ YAML nội bộ, file bên ngoài, môi trường hay tham số dòng lệnh.

Để dùng cấu hình trong ứng dụng thực, service có thể truyền `config.connectTimeout()` vào HTTP client builder, hoặc dùng `config.maxPayload().toBytes()` khi cần một giới hạn kích thước. Mục tiêu là cấu hình mang **đúng kiểu** trước khi đến logic sử dụng.

## 4. Lợi ích chính của cấu hình có kiểu

### 4.1. Gom cấu hình theo tính năng

So sánh hai cách:

~~~java
// Các property được đọc rời rạc ở nhiều nơi.
String baseUrl = env.getProperty("acme.client.base-url");
String timeout = env.getProperty("acme.client.connect-timeout");
String retry = env.getProperty("acme.client.retry.max-attempts");
~~~

Với:

~~~java
public CatalogClient(ClientProperties properties) {
    this.properties = properties;
}
~~~

Cách thứ hai thể hiện ranh giới rõ ràng: `ClientProperties` mô tả cấu hình của client. Khi thêm hoặc bỏ một option, có một nơi tập trung để cập nhật hợp đồng cấu hình.

### 4.2. Chuyển kiểu có hệ thống

Ví dụ `connect-timeout: 3s` được bind thành `Duration`. Code không phải tự gọi `Long.parseLong(...)`, nhân với 1.000 hoặc đoán đơn vị millisecond.

Spring Boot hỗ trợ chuyển đổi nhiều kiểu phổ biến như `Duration`, `DataSize`, enum, URL/URI, kiểu số, boolean và một số collection. Khả năng chuyển đổi cụ thể phụ thuộc kiểu đích và converter được cung cấp.

Nếu giá trị không thể chuyển thành kiểu yêu cầu, binder có thể báo lỗi binding khi bean được tạo. Đây là cách phát hiện sớm nhiều sai sót vốn dễ bị che giấu nếu mọi property đều dùng `String`.

### 4.3. Tập trung validation

Bạn có thể yêu cầu endpoint không rỗng, số lần retry phải dương, timeout phải phù hợp, hoặc danh sách vùng không được rỗng. Validation của bean cấu hình có thể chạy khi binding, khiến ứng dụng **fail fast** khi môi trường triển khai thiếu thông tin bắt buộc.

### 4.4. Dễ khám phá và bảo trì

Một `ClientProperties` record thể hiện rõ các trường và kiểu dữ liệu trong chữ ký constructor. Người đọc code không phải truy tìm nhiều chuỗi placeholder rải rác trong controller và service.

Spring Boot có thể tạo **configuration metadata** qua annotation processor cho các lớp cấu hình, hỗ trợ IDE completion, tài liệu mô tả property và cảnh báo một số tên khóa không khớp. Metadata là tiện ích phát triển, không phải điều kiện bắt buộc để binder runtime hoạt động.

### 4.5. Dễ kiểm thử với cấu hình xác định

Trong test, có thể cấp giá trị tường minh cho các property thay vì phụ thuộc vào biến môi trường của máy developer. Nếu service chỉ phụ thuộc một object cấu hình, một unit test thuần Java cũng có thể tạo record với giá trị mong muốn.

Ví dụ:

~~~java
ClientProperties properties = new ClientProperties(
        URI.create("https://example.test"),
        Duration.ofSeconds(2),
        DataSize.ofMegabytes(1),
        List.of("test-region"),
        Map.of("x-client-name", "test"),
        new ClientProperties.Retry(2, Duration.ofMillis(100))
);
~~~

Đây là ví dụ tạo object phục vụ test đơn vị; nó **không** tự kiểm tra cơ chế binding của Spring. Nếu muốn kiểm tra tên property hoặc chuyển đổi thực tế, dùng bài test khởi tạo context với cấu hình tường minh.

## 5. Record bất biến và JavaBean có setter

Spring Boot hỗ trợ nhiều kiểu object đích; hai phong cách thường gặp là constructor binding và JavaBean binding.

### 5.1. Constructor binding với record

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        String currency,
        boolean enabled,
        Duration timeout
) {}
~~~

Binder cung cấp các giá trị cho constructor của record. Khi object đã được tạo, các field không có setter. Phong cách này phù hợp khi muốn cấu hình đóng vai trò **bản mô tả cố định** trong vòng đời bean.

Với lớp Java thường có nhiều constructor, cần chú ý các quy tắc chọn constructor và `@ConstructorBinding` của phiên bản Spring Boot đang dùng. Record một canonical constructor là đường đi gọn và rõ trong Boot 3.

### 5.2. JavaBean binding

Một phương án khác:

~~~java
package com.example.catalog.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail.transport")
public class MailTransportProperties {

    private String host;
    private int port = 25;
    private Duration timeout = Duration.ofSeconds(5);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Trong JavaBean binding, Spring Boot tạo object bằng constructor phù hợp, sau đó bind bằng setters hoặc cấu trúc property thích hợp. Giá trị mặc định của field (`port=25`, `timeout=5s`) có thể dùng khi property không được cung cấp.

Nếu muốn object cấu hình có thể được sửa sau khởi tạo hoặc cần tích hợp với thư viện dựa trên JavaBean conventions, phong cách này có thể thuận tiện. Tuy nhiên, với cấu hình runtime chỉ cần đọc, object bất biến thường giúp giới hạn việc sửa nhầm giá trị.

### 5.3. Tránh dùng constructor binding sai ngữ cảnh

Constructor binding của `@ConfigurationProperties` không được áp dụng tùy ý cho mọi bean do Spring tạo bằng `@Component`, `@Bean` hay `@Import` như thể nó là bean dependency injection thông thường. Với record cấu hình constructor-bound, nên đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Đừng thêm `@Component` lên mọi record cấu hình chỉ để Spring tìm thấy nó; hãy dùng đúng cơ chế đăng ký configuration properties.

## 6. Relaxed binding: không phải viết tên Java giống hệt YAML

Một lợi ích của `@ConfigurationProperties` là **relaxed binding**: Spring Boot hỗ trợ các quy tắc ánh xạ nhiều dạng tên property vào cùng một Java field.

Ví dụ field Java:

~~~java
private Duration connectTimeout;
~~~

có thể nhận dữ liệu từ khóa canonical:

~~~properties
acme.client.connect-timeout=3s
~~~

Trong YAML:

~~~yaml
acme:
  client:
    connect-timeout: 3s
~~~

Và từ biến môi trường theo quy ước:

~~~bash
export ACME_CLIENT_CONNECTTIMEOUT=4s
~~~

Với environment variable, Spring Boot thường chuyển dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang, rồi viết hoa: `acme.client.connect-timeout` thành `ACME_CLIENT_CONNECTTIMEOUT`. Tránh tự suy đoán tùy tiện các biến thể gạch dưới khi tên chứa nhiều segment; ưu tiên dùng tên canonical trong file và tên biến đúng quy ước Spring Boot.

### 6.1. Tên prefix nên dùng dạng canonical

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public record ClientProperties(Duration connectTimeout) {}
~~~

Prefix `acme.client` dùng chữ thường và các segment ngăn bằng dấu chấm. Spring Boot khuyến nghị đặt tên property dưới dạng **kebab-case** như `connect-timeout`.

Khi tạo cấu hình mới, hãy giữ convention nhất quán để developer, IDE và deployment có thể tìm đúng tên khóa.

### 6.2. Trường lồng nhau

Property `acme.client.retry.max-attempts` có đường dẫn gồm prefix `acme.client`, object `retry` và field `maxAttempts`. Binder tạo object nested khi có cấu hình và constructor/đích binding phù hợp.

Không cần viết một property `retry` chứa JSON string rồi parse bằng tay. Các key con có thể được bind thành nested record hoặc class.

### 6.3. Map keys không giống field names

Với `Map<String, String>`, một số tên key chứa dấu chấm, dấu gạch chéo hoặc ký tự đặc biệt có thể cần cú pháp bracket notation để giữ nguyên ký tự khi binder xử lý.

Ví dụ trong YAML, một key map có thể đặt bằng dạng được quote:

~~~yaml
acme:
  client:
    headers:
      "[/special-key]": "value"
~~~

Không nên coi mọi key của map đều được xử lý y hệt field Java. Khi làm việc với tên key đặc biệt, tham khảo quy tắc **Binding Maps** của Spring Boot, nhất là trường hợp dùng bracket notation hoặc map có key chứa dấu chấm.

## 7. Chuyển đổi kiểu: Duration, DataSize, enum, list và map

### 7.1. `Duration`

~~~yaml
worker:
  connect-timeout: 500ms
  read-timeout: 5s
~~~

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

Các suffix như `ms` và `s` thể hiện đơn vị. Không nên nhập một số trần như `5000` rồi tự đoán đó là giây hay millisecond; với `Duration`, nếu dùng số không kèm đơn vị, binder có quy tắc đơn vị mặc định phụ thuộc cấu hình/annotation. Viết đơn vị tường minh làm giảm nhầm lẫn.

### 7.2. `DataSize`

~~~yaml
upload:
  max-file-size: 16MB
~~~

~~~java
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "upload")
public record UploadProperties(DataSize maxFileSize) {}
~~~

`DataSize` phù hợp để diễn tả giới hạn bytes. Khi code cần số byte, dùng `maxFileSize.toBytes()`. Chú ý đơn vị được Spring hỗ trợ và semantics của nó; không tự quy đổi chuỗi thủ công khi binder đã có conversion.

### 7.3. Enum và boolean

~~~java
public enum Mode {
    SAFE, FAST
}

@ConfigurationProperties(prefix = "worker")
public record ExecutionProperties(Mode mode, boolean enabled) {}
~~~

~~~yaml
worker:
  mode: SAFE
  enabled: true
~~~

Sử dụng enum thay vì string giúp giới hạn tập lựa chọn và làm rõ semantics trong code. Khi nhận giá trị không thể chuyển thành `Mode`, binding có thể báo lỗi thay vì tiếp tục với một string lạ.

### 7.4. Danh sách

~~~yaml
routing:
  regions:
    - ap-southeast-1
    - ap-northeast-1
~~~

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<String> regions) {}
~~~

Cần nhận biết **list replacement** khi nhiều nguồn cấu hình khác nhau cung cấp cùng list. Spring Boot thường sử dụng list từ nguồn có ưu tiên cao hơn, thay vì nối tất cả phần tử của các nguồn.

### 7.5. Map

~~~yaml
routing:
  labels:
    owner: backend
    region: apac
~~~

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(Map<String, String> labels) {}
~~~

Các entry của map có thể kết hợp theo từng khóa từ nhiều nguồn; entry cùng tên được chọn theo precedence. Ngữ nghĩa của list và map **khác nhau**, nên không giả định mọi collection đều deep merge.

## 8. Validation: phát hiện cấu hình sai sớm

Một object có kiểu chỉ đảm bảo binder cố chuyển dữ liệu thành kiểu đích. Nó chưa tự bảo đảm endpoint tồn tại, timeout hợp lệ hoặc giá trị nằm trong giới hạn nghiệp vụ. Đó là vai trò của validation.

### 8.1. Thêm dependency validation

Với Spring Boot 3 và ứng dụng dùng Spring Boot starter, Maven thường khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Hoặc Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Dependency này cung cấp hạ tầng Bean Validation thông dụng, với annotation thuộc package `jakarta.validation` trong Spring Boot 3.

### 8.2. Khai báo constraint trên properties

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.client")
@Validated
public record ValidatedClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

Trong ví dụ này:

- `@Validated` bật validation trong quá trình bind configuration properties.
- `@NotNull` yêu cầu các field tương ứng có giá trị.
- `@Min(1)` yêu cầu `maxAttempts` ít nhất là 1.
- `@Valid` yêu cầu kiểm tra cả constraints của object `Retry` lồng nhau.

Để thử ví dụ, đăng ký `ValidatedClientProperties` qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` và cấu hình đủ các field. Không cần đăng ký đồng thời một lớp khác trùng prefix nếu ứng dụng chỉ cần một bean mô tả cấu hình đó.

### 8.3. Lỗi thiếu và lỗi sai kiểu là hai loại khác nhau

Giả sử file có:

~~~yaml
acme:
  client:
    base-url: "https://api.example.test"
    connect-timeout: "not-a-duration"
    retry:
      max-attempts: 0
      backoff: 100ms
~~~

`connect-timeout` có thể gây lỗi **conversion/binding** vì không chuyển được sang `Duration`. Nếu sửa thành `2s` nhưng giữ `max-attempts: 0`, lỗi **validation** của `@Min(1)` có thể xuất hiện.

Khi cần một cấu hình bắt buộc, xác định rõ constraint phù hợp. Với string không được rỗng hoặc chỉ chứa khoảng trắng, thường dùng `@NotBlank` thay vì chỉ `@NotNull`. Với số nguyên có phạm vi, dùng `@Min`, `@Max` hoặc validator tùy chỉnh.

### 8.4. Validation của nested objects

Với nested record, annotation `@Valid` ở field cha có ý nghĩa quan trọng để validation đi sâu vào các constraint con. `@NotNull` trên nested object giúp bắt trường hợp cả object chưa được cung cấp.

Nếu chỉ đặt `@Min(1)` trong `Retry` mà không bảo đảm quá trình validation đi vào object lồng nhau, không nên mặc định mọi constraint sâu đều sẽ được kiểm tra như mong muốn. Cấu hình validation cần được thiết lập tường minh và có hạ tầng validator phù hợp.

### 8.5. Fail fast khi triển khai

Một deployment mới quên cung cấp `acme.client.base-url` có thể khiến bean cấu hình không hợp lệ. Việc ứng dụng từ chối khởi động trong trường hợp này thường tốt hơn để một request đầu tiên mới gặp `NullPointerException`.

Tuy vậy, validation lúc startup **không thay thế** kiểm tra điều kiện runtime: endpoint có thể đúng cú pháp nhưng không kết nối được, credential có thể đã hết hạn, hoặc dữ liệu remote thay đổi. Validation xác nhận hợp đồng cấu hình, còn khả năng kết nối và nghiệp vụ là vấn đề khác.

## 9. Giá trị mặc định trong typed configuration

Có ít nhất ba cách phổ biến để thiết kế default.

### 9.1. Default trong file cấu hình

~~~yaml
acme:
  client:
    connect-timeout: 3s
    retry:
      max-attempts: 3
~~~

Đây là cách dễ đọc và có thể được override từ các nguồn ưu tiên cao hơn như môi trường hoặc CLI.

### 9.2. Default trong field của JavaBean

~~~java
private Duration timeout = Duration.ofSeconds(5);
private boolean enabled = true;
~~~

Với JavaBean có setter, các giá trị khởi tạo có thể giữ nguyên khi không có property tương ứng được bind. Nhưng cách này gắn default vào mã nguồn Java, nên khi thay policy mặc định cần đổi code hoặc dùng override externalized configuration.

### 9.3. `@DefaultValue` với constructor binding

Trong Spring Boot 3, có thể dùng `@DefaultValue` cho tham số constructor-bound:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("false") boolean enabled
) {}
~~~

Khi `reports.timeout` hoặc `reports.enabled` không được cấp, binder có thể dùng giá trị mặc định từ annotation. Lưu ý rằng validation vẫn có thể được áp dụng lên giá trị cuối sau binding.

Giá trị mặc định nên có ý nghĩa an toàn về nghiệp vụ. **Không** dùng một password giả hoặc URL production giả làm fallback âm thầm cho cấu hình bắt buộc.

## 10. Nguồn cấu hình và thứ tự ưu tiên

`@ConfigurationProperties` không giới hạn dữ liệu đến từ `application.yml`. Binder đọc những property được Spring Boot tập hợp trong `Environment`.

Một số nguồn thường gặp:

- `application.properties` hoặc `application.yml` đóng gói trong JAR.
- File cấu hình ở ngoài JAR và các file được import bằng `spring.config.import`.
- Biến môi trường, ví dụ `ACME_CLIENT_BASE_URL`.
- Java system properties, ví dụ `-Dacme.client.base-url=...`.
- `SPRING_APPLICATION_JSON`.
- Tham số dòng lệnh, ví dụ `--acme.client.base-url=...`.
- Nguồn đặc thù của Servlet, test hoặc custom `PropertySource` khi được cấu hình.

### 10.1. Khi cùng một khóa xuất hiện ở nhiều nguồn

`application.yml`:

~~~yaml
acme:
  client:
    base-url: "https://default.example"
    connect-timeout: 3s
~~~

Biến môi trường:

~~~bash
export ACME_CLIENT_BASEURL=https://staging.example
~~~

Lệnh chạy:

~~~bash
java -jar catalog.jar \
  --acme.client.connect-timeout=1s
~~~

Với thứ tự ưu tiên mặc định của Spring Boot trong ví dụ này, bean `ClientProperties` thường nhận:

~~~text
baseUrl        = https://staging.example
connectTimeout = 1s
~~~

Source khác nhau cung cấp **từng key**; binder không coi toàn bộ object của một file là bản ghi bất khả chia. Nếu chỉ override `connect-timeout`, các field khác vẫn có thể lấy từ YAML.

### 10.2. Với các document có điều kiện/profile

~~~yaml
acme:
  client:
    connect-timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod"

acme:
  client:
    connect-timeout: 1s
~~~

Khi profile `prod` active, document phía sau có thể ghi đè `connect-timeout` trong phạm vi file này. Sau đó Boot vẫn xét các nguồn config data, môi trường và CLI khác theo precedence. `@ConfigurationProperties` chỉ bind giá trị **cuối cùng được giải quyết**; nó không tự bật profile.

### 10.3. List và map qua nhiều property sources

Một lưu ý quan trọng: list thường có quy tắc **thay thế cả danh sách** khi bind từ nguồn ưu tiên cao; map có thể kết hợp theo từng entry. Vì vậy, cấu hình gồm list/map cần được xem theo semantics của binder, không suy rằng object luôn deep merge mọi phần tử.

### 10.4. Lệnh chọn nơi nạp file được xử lý sớm

Các property như `spring.config.location` hoặc `spring.config.additional-location` có thể phải được cung cấp rất sớm trong vòng đời khởi động để Boot biết nơi tìm config data. Bean `@ConfigurationProperties` được bind **sau** quá trình thu thập cấu hình thích hợp; nó không thể thay thế cơ chế bootstrap để tự đi tìm những file chưa được nạp.

## 11. So sánh `@ConfigurationProperties`, `@Value` và `Environment`

| Tiêu chí | `@ConfigurationProperties` | `@Value` | `Environment` |
| --- | --- | --- | --- |
| Mục đích chính | Bind nhóm cấu hình có kiểu | Inject một biểu thức/giá trị | Tra cứu property qua API |
| Cấu hình lồng nhau | Thuận tiện, có nested objects | Phải khai báo từng placeholder | Tra cứu từng khóa |
| Chuyển kiểu | Binder hỗ trợ nhiều kiểu và collection | Có chuyển kiểu thông qua Spring | Có các overload với kiểu đích |
| Validation | Tích hợp Bean Validation khi cấu hình | Cần thiết kế kiểm tra phù hợp | Caller tự xử lý và kiểm tra |
| Khả năng khám phá | Lớp mô tả hợp đồng cấu hình | Khóa rải rác theo điểm dùng | Khóa dạng string trong code |
| Relaxed binding | Cơ chế binder riêng, khuyến nghị kebab-case | Không phải mọi quy tắc đều giống Binder | Phụ thuộc đường tra cứu/conversion |
| Expression/SpEL | Tập trung binding properties, không phải SpEL evaluator | Hỗ trợ expression theo cơ chế `@Value` | Tra cứu property, không tự là `@Value` |

### 11.1. Khi nào dùng `@Value`?

Khi một component nhỏ cần một property đơn giản:

~~~java
@Component
public class FeatureBanner {

    private final String title;

    public FeatureBanner(
            @Value("${feature.banner-title:Welcome}") String title) {
        this.title = title;
    }
}
~~~

Dùng `@Value` là hợp lý nếu chỉ có một hoặc vài giá trị độc lập và bạn không cần định nghĩa một mô hình cấu hình riêng.

### 11.2. Khi nào dùng `@ConfigurationProperties`?

Nếu cấu hình có nhiều trường liên quan, object lồng nhau, collection, kiểu đặc biệt hoặc constraint, một properties class giúp diễn đạt ý nghĩa rõ hơn.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "feature.banner")
public record BannerProperties(
        String title,
        boolean enabled,
        Duration refreshInterval
) {}
~~~

Service nhận `BannerProperties`, các test có thể cấp override tường minh và validator có thể xác minh bộ giá trị lúc khởi động.

### 11.3. Khi nào dùng `Environment` trực tiếp?

`Environment` phù hợp cho framework integration, công cụ chẩn đoán hoặc logic thật sự cần truy vấn tên property động. Trong code nghiệp vụ có tập property cố định, lặp lại `getProperty("...")` ở nhiều lớp thường làm hợp đồng cấu hình khó quản lý.

## 12. Configuration metadata và hỗ trợ IDE

Spring Boot có annotation processor sinh metadata cho các lớp `@ConfigurationProperties`. Trong Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Hoặc với Maven, cấu hình annotation processing phù hợp với plugin/compiler đang dùng và thêm dependency `spring-boot-configuration-processor` ở phạm vi hợp lý.

Metadata thường nằm trong artifact ở `META-INF/spring-configuration-metadata.json`. IDE có thể tận dụng nó để gợi ý key, kiểu và mô tả property. Nếu muốn mô tả từng option cho người dùng, viết JavaDoc cho lớp và các field/constructor components phù hợp để processor hoặc tooling nhận diện theo khả năng được hỗ trợ.

**Annotation processor không phải Binder.** Thiếu metadata có thể khiến IDE ít gợi ý hơn nhưng không đồng nghĩa bean `@ConfigurationProperties` không hoạt động. Ngược lại, có metadata không đảm bảo một bean đã được đăng ký hoặc cấu hình đã hợp lệ.

## 13. Nguyên tắc tổ chức configuration properties trong dự án

### 13.1. Chia theo năng lực, không gom mọi thứ vào một lớp

Thay vì một object `ApplicationProperties` chứa hàng trăm field không liên quan, có thể có:

~~~text
HttpClientProperties       -> acme.http-client.*
StorageProperties          -> acme.storage.*
NotificationProperties     -> acme.notification.*
SecurityIntegrationProps   -> acme.security-integration.*
~~~

Mỗi lớp thuộc về phần ứng dụng có trách nhiệm sử dụng các giá trị đó. Ví dụ HTTP client dùng `HttpClientProperties`; storage service dùng `StorageProperties`.

Cách tổ chức này giúp mỗi module có hợp đồng cấu hình và validation riêng, đồng thời giảm số dependency không cần thiết giữa các service.

### 13.2. Đặt namespace có ý nghĩa

Dùng prefix riêng như `acme.storage` hoặc `catalog.import-job` cho thuộc tính của ứng dụng, tránh lạm dụng các namespace framework như `spring.*` nếu chỉ muốn tạo tùy chọn nghiệp vụ.

Một prefix ổn định giúp tìm, document và override cấu hình qua từng môi trường. Khi đổi tên khóa public, đó là thay đổi hợp đồng triển khai; cân nhắc tương thích với manifest, Helm chart, environment variable, test và documentation.

### 13.3. Giữ logic nghiệp vụ ở ngoài properties class

Một lớp `@ConfigurationProperties` nên biểu diễn dữ liệu cấu hình và các constraint cần thiết. Không nên biến nó thành service gọi HTTP, truy cập database hoặc tự thao tác filesystem trong constructor.

Một class cấu hình dễ đọc và ít side effect sẽ được bind, xác thực và test đơn giản hơn. Nghiệp vụ sử dụng giá trị nên đặt trong bean phụ thuộc.

### 13.4. Phân biệt cấu hình và trạng thái thay đổi liên tục

Các giá trị như endpoint, timeout, retry policy phù hợp để bind thành cấu hình. Trạng thái như số request đang chạy, bộ đếm, cache entry hoặc token làm mới liên tục không nên lưu như field trong `@ConfigurationProperties` để rồi xem đó là nguồn dữ liệu runtime.

Nếu có nhu cầu cập nhật cấu hình nóng, thiết kế cơ chế refresh/rebind rõ ràng, kiểm soát cạnh tranh và vòng đời bean; `@ConfigurationProperties` cơ bản không tự phát hiện mọi lần sửa file hay biến môi trường.

## 14. Bảo mật và vận hành

### 14.1. Cấu hình có kiểu vẫn có thể chứa secret

Một lớp như:

~~~java
@ConfigurationProperties(prefix = "integration.auth")
public record AuthProperties(String username, String password) {}
~~~

chỉ mô tả nơi sử dụng các property. Nó **không mã hóa, che giấu hay bảo vệ bí mật** chỉ bằng annotation. Secret vẫn phải đến từ nguồn an toàn, chẳng hạn secret manager hoặc volume mount có giới hạn quyền.

Cần lưu ý `record.toString()` có thể in các field của record. **Không log nguyên object cấu hình chứa password, token hoặc private key.** Nếu cần chẩn đoán, chỉ log tên key và trạng thái hiện diện, hoặc giá trị không nhạy cảm đã được chọn lọc.

### 14.2. Không đặt giá trị nhạy cảm trong error message tùy tiện

Khi binding thất bại, một số framework diagnostics có thể chứa thông tin về property. Hãy cấu hình logging và các endpoint chẩn đoán phù hợp, kiểm soát quyền truy cập Actuator `env` / `configprops` và cơ chế làm mờ các value nhạy cảm. Đừng đưa một object cấu hình bí mật vào exception hoặc log tự tạo.

### 14.3. Cấu hình chỉ phản ánh thời điểm binding

Khi Kubernetes Secret, ConfigMap hoặc file externalized thay đổi, các field trong singleton properties bean không mặc định tự được rebind. Với cấu hình cần thay đổi trong runtime, thiết kế restart/rollout hoặc cơ chế refresh có kiểm soát. Đừng dùng một bean đã bind lúc startup như nguồn truth luôn cập nhật cho một dữ liệu thay đổi mỗi giây.

### 14.4. Binding không tự kiểm chứng hệ thống ngoài

Một `URI` hợp lệ có thể trỏ tới server đang tắt; một `Duration` hợp lệ có thể quá thấp cho latency thật; một credential đủ định dạng có thể bị thu hồi. Bean Validation kiểm tra **hợp đồng cấu hình trong ứng dụng**, không đảm bảo trạng thái của bên ngoài.

Nếu startup phải chứng minh một dependency đã sẵn sàng, đó là một cơ chế health/connectivity riêng, có timeout và chính sách lỗi phù hợp.

## 15. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không inject được `ClientProperties` | Chưa đăng ký bằng scan/enable hoặc sai package scan | Thêm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` phù hợp |
| Các field là null hoặc giá trị mặc định | Sai prefix/key; nguồn chưa nạp; thiếu property | Xác nhận `acme.client.*` và nguồn cấu hình thực tế |
| Không chuyển được `connect-timeout` | Value không hợp lệ với `Duration` | Dùng đơn vị tường minh như `500ms`, `3s` |
| Validation không chạy như mong đợi | Thiếu `@Validated`, validator dependency hoặc cascading `@Valid` | Thiết lập Bean Validation phù hợp |
| Nested object không được bind | Sai nhánh trong YAML hoặc constructor/target không phù hợp | Đối chiếu `retry.max-attempts` với field `retry.maxAttempts` |
| List mất phần tử default | Nguồn ưu tiên cao thay thế list | Xem semantics list binding và thứ tự nguồn |
| Map key có dấu chấm bị biến đổi | Không dùng bracket notation phù hợp | Xem quy tắc map keys của Spring Boot |
| Môi trường báo value khác local | Các nguồn bên ngoài JAR/env/CLI có ưu tiên khác | Xem `PropertySource` thực tế và config data |
| Bean giữ giá trị cũ sau đổi ConfigMap | Bean chưa được refresh/rebind hoặc ứng dụng chưa restart | Thiết kế rollout/refresh rõ ràng |
| IDE không gợi ý tên property | Chưa có configuration metadata processor | Thêm processor nếu cần hỗ trợ IDE |
| Record chứa password bị lộ khi log | Log object qua `toString()` | Chỉ log dữ liệu không nhạy cảm, bảo vệ secrets |

### 15.1. Quan sát giá trị và nguồn cấu hình

Với một khóa **không nhạy cảm**, có thể sử dụng `ConfigurableEnvironment` để xem nguồn và giá trị:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigurationProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "acme.client.connect-timeout";

        System.out.println("Resolved: "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Đoạn này chỉ để chẩn đoán. Tên/biểu diễn của `PropertySource` có thể thay đổi theo phiên bản hoặc nguồn cấu hình; không dùng tên source dạng string làm logic nghiệp vụ.

Một số nguồn không dùng cùng quy tắc relaxed binding khi tra cứu trực tiếp bằng `getProperty(...)` như khi dùng Binder; nên dùng tên canonical phù hợp, và nếu kết quả gây nghi ngờ, xem metadata origin/Actuator được bảo vệ hoặc thử binding thực tế.

### 15.2. Khi lỗi khởi động do cấu hình

Nếu Spring Boot báo `BindException` hoặc lỗi binding/validation liên quan `acme.client`, lần lượt kiểm tra:

1. **Bean đã được đăng ký?** `@ConfigurationPropertiesScan` có quét được package của properties class không?
2. **Prefix có đúng?** Code khai báo `acme.client`, nhưng file có thể viết nhầm `acme.clients`.
3. **File được nạp?** Đúng location, active profile, config import và working directory?
4. **Property có bị override?** OS environment, system properties, JSON/CLI hoặc test properties?
5. **Giá trị chuyển kiểu được không?** Ví dụ `2s` cho `Duration`, `16MB` cho `DataSize`.
6. **Constraint có thỏa?** `@NotNull`, `@Min` hoặc validator nested.
7. **Kiểu đích có đúng?** List, map, record constructor hoặc JavaBean setters có phù hợp?
8. **Có lộ secret trong log lỗi không?** Bảo vệ giá trị và điều chỉnh cách chẩn đoán.

Không nên tắt validation hoặc bỏ constraint chỉ để deployment khởi động khi cấu hình không hợp lệ. Hãy xác định và sửa property nguồn gây lỗi.

## 16. Bài tập thực hành

### Bài tập A: chuyển từ `@Value` sang typed config

Ban đầu một service dùng:

~~~java
@Value("${order.client.endpoint}")
private String endpoint;

@Value("${order.client.timeout:5s}")
private String timeout;

@Value("${order.client.retries:2}")
private int retries;
~~~

Hãy tạo record `OrderClientProperties` với prefix `order.client`, dùng kiểu `URI`, `Duration`, `int` tương ứng, đăng ký với `@ConfigurationPropertiesScan` và inject vào service. Kiểm tra code không còn cần parse timeout từ string.

### Bài tập B: nested properties

Tạo `application.yml`:

~~~yaml
order:
  client:
    endpoint: "https://orders.example.test"
    timeout: 4s
    retry:
      enabled: true
      attempts: 3
~~~

Định nghĩa `OrderClientProperties` có nested `Retry` record. In một kết quả không nhạy cảm như `timeout` hoặc `retry.attempts` khi startup để quan sát binding.

### Bài tập C: validation

Thêm `@Validated` và constraints để yêu cầu `endpoint` khác null, `timeout` khác null, `retry.attempts >= 1`. Chạy ứng dụng với `attempts=0` và quan sát lỗi validation. Sau đó sửa thành `3` và thử tiếp một `timeout` sai kiểu để phân biệt lỗi conversion với lỗi constraint.

### Bài tập D: override theo môi trường

Cho default:

~~~yaml
order:
  client:
    timeout: 5s
~~~

Chạy với:

~~~bash
export ORDER_CLIENT_TIMEOUT=2s
java -jar order.jar --order.client.timeout=1s
~~~

Dự đoán rằng CLI có ưu tiên hơn biến môi trường và file mặc định khi cơ chế precedence của Spring Boot không bị tùy chỉnh. Bind thành `Duration` và quan sát giá trị thực tế.

### Bài tập E: list và map

Khai báo `routing.regions` dạng list và `routing.labels` dạng map. Cấp một nguồn config cao hơn chỉ override một phần các khóa. Kiểm tra sự khác nhau giữa việc list bị thay thế và map kết hợp theo entry.

### Bài tập F: lựa chọn phong cách

Trong ba tình huống sau, giải thích chọn API nào:

1. Một component cần đúng một flag đơn giản và không có các thuộc tính liên quan.
2. Một HTTP client cần endpoint, timeout, retry, danh sách vùng và validation.
3. Một công cụ nội bộ cần truy vấn tên property do người vận hành nhập lúc runtime.

Gợi ý: `@Value` có thể đủ cho tình huống 1; `@ConfigurationProperties` phù hợp cho 2; `Environment` có thể phù hợp cho 3 nếu có kiểm soát và xử lý lỗi đúng cách.

## 17. Ghi nhớ

- `@ConfigurationProperties` mô tả **một nhóm cấu hình có kiểu**, được bind từ `Environment` vào Java object. Annotation này không tự đọc YAML và không thay đổi precedence của các nguồn.
- Dùng prefix canonical và tên khóa kebab-case. Relaxed binding giúp ánh xạ YAML/properties/environment variables vào field Java.
- Spring Boot 3 hỗ trợ constructor binding với record; dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` để đăng ký bean.
- Binder hỗ trợ `Duration`, `DataSize`, enum, list, map, object lồng nhau và chuyển đổi kiểu. List/map có semantics binding khác nhau khi có nhiều nguồn.
- Kết hợp `@Validated` và Bean Validation để phát hiện thiếu hoặc sai cấu hình ngay trong giai đoạn khởi tạo.
- `@Value` phù hợp với một vài scalar; `Environment` hữu ích cho tra cứu động; `@ConfigurationProperties` phù hợp khi cần một hợp đồng cấu hình ổn định, dễ bảo trì và test.
- Bảo vệ secret trong nguồn và log; record chứa password có thể lộ giá trị qua `toString()`. Thay đổi cấu hình bên ngoài không mặc định khiến mọi bean đang chạy cập nhật.

## Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): định nghĩa, binding, registration và lợi ích của `@ConfigurationProperties`.
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding): quy tắc đặt tên và binding theo nguồn.
- [Spring Boot Reference — Properties Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion): chuyển đổi kiểu, `Duration` và `DataSize`.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): validation bean cấu hình.
- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html): metadata hỗ trợ IDE và annotation processor.
- [Spring Framework Reference — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): inject và resolve placeholder.
