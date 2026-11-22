# Thay các @Value rải rác bằng đối tượng cấu hình có cấu trúc

Trong một ứng dụng Spring Boot, cách đơn giản để lấy cấu hình là sử dụng `@Value("${...}")`. Khi chỉ có một hoặc hai giá trị, cách này rất tiện. Nhưng khi một chức năng có nhiều tham số như URL, timeout, retry, danh sách vùng hoạt động và các cờ bật/tắt, việc đặt `@Value` ở nhiều bean sẽ làm **cấu hình bị phân tán**, khó biết ứng dụng thực sự cần gì và khó xác thực toàn bộ nhóm thuộc tính.

Spring Boot giải quyết vấn đề bằng `@ConfigurationProperties`: gom các thuộc tính có cùng tiền tố thành **một đối tượng Java có kiểu dữ liệu rõ ràng**, hỗ trợ cấu trúc lồng nhau, chuyển kiểu, giá trị mặc định, validation và inject qua constructor.

Bài học hướng dẫn chuyển từ các `@Value` rải rác sang một cấu trúc cấu hình nhất quán, sử dụng Spring Boot 3.3.x và Java 21. Ví dụ chính dùng `record` để nhấn mạnh cấu hình được khởi tạo một lần và sử dụng như dữ liệu đọc.

## 1. Vấn đề với nhiều `@Value`

Giả sử hệ thống có chức năng gọi dịch vụ giao hàng. Ban đầu một bean đọc endpoint và timeout:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DeliveryClient {

    @Value("${app.delivery.endpoint}")
    private URI endpoint;

    @Value("${app.delivery.connect-timeout:4s}")
    private Duration connectTimeout;

    // Sử dụng endpoint và connectTimeout để gọi hệ thống ngoài.
}
~~~

Một bean khác quản lý retry:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRetryPolicy {

    @Value("${app.delivery.retry.max-attempts:3}")
    private int maxAttempts;

    @Value("${app.delivery.retry.backoff:250ms}")
    private java.time.Duration backoff;
}
~~~

Bean thứ ba xử lý một cờ tính năng:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DeliveryFeatureSwitch {

    @Value("${app.delivery.enabled:true}")
    private boolean enabled;
}
~~~

Năm giá trị đều thuộc một nhóm nghiệp vụ, nhưng lập trình viên phải đọc nhiều lớp mới thấy toàn bộ cấu hình. Một vài hệ quả:

- Không có một kiểu Java duy nhất mô tả **hợp đồng cấu hình** của chức năng giao hàng.
- Default `4s`, `3`, `250ms`, `true` nằm trong annotation ở những chỗ khác nhau, nên khó đối chiếu với file cấu hình.
- Khi thêm validation, mỗi bean có nguy cơ kiểm tra dữ liệu theo cách riêng.
- Cấu hình cùng nhóm có thể dùng tên không nhất quán như `retry.count` ở một nơi và `retry.max-attempts` ở nơi khác.
- Test muốn tạo nhiều bean phải chuẩn bị đúng các placeholder riêng lẻ, thay vì tạo một object dữ liệu được định nghĩa rõ.
- Field injection gây khó khăn khi đọc dependency của constructor và khi tạo đối tượng trong unit test.

`@Value` không phải API sai. Vấn đề nằm ở **cách sử dụng quá nhiều injection độc lập cho một nhóm thông số vốn thuộc chung một khái niệm**.

## 2. Kết quả mong muốn: một cấu hình theo nhóm

Giả sử file `src/main/resources/application.yml` được tổ chức như sau:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org/api
    enabled: true
    connect-timeout: 4s

    retry:
      max-attempts: 3
      backoff: 250ms

    allowed-regions:
      - vn
      - sg
~~~

Những thuộc tính này có cấu trúc rõ ràng:

~~~text
app.delivery
├── endpoint            → URI
├── enabled             → boolean
├── connect-timeout     → Duration
├── retry
│   ├── max-attempts    → int
│   └── backoff         → Duration
└── allowed-regions     → List<String>
~~~

Thay vì inject sáu giá trị vào nhiều field, một đối tượng `DeliveryProperties` chứa toàn bộ cấu hình của nhóm `app.delivery`. Các service khác chỉ phụ thuộc vào đối tượng đó.

Mục tiêu thiết kế:

~~~text
application.yml / environment variables / CLI
                    ↓
       Spring Boot Configuration Binder
                    ↓
             DeliveryProperties
                    ↓
       DeliveryClient / RetryPolicy / Service
~~~

Binder đọc cấu hình từ `Environment` theo thứ tự ưu tiên hiện hành; lớp `DeliveryProperties` thể hiện cấu trúc và kiểu dữ liệu mà mã nguồn mong đợi.

## 3. Tạo lớp cấu hình bằng `@ConfigurationProperties` và Java record

Tạo file `src/main/java/com/example/delivery/config/DeliveryProperties.java`:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        URI endpoint,
        boolean enabled,
        Duration connectTimeout,
        Retry retry,
        List<String> allowedRegions) {

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
~~~

Giải thích:

- `@ConfigurationProperties(prefix = "app.delivery")` yêu cầu Spring Boot bind các thuộc tính con của `app.delivery`.
- `endpoint` nhận giá trị `app.delivery.endpoint` và được chuyển thành `java.net.URI`.
- `enabled` nhận boolean `true` hoặc `false`.
- `connectTimeout` nhận giá trị như `4s` và chuyển thành `java.time.Duration`.
- `retry` là một record lồng nhau, nhóm `maxAttempts` và `backoff`.
- `allowedRegions` nhận các phần tử từ YAML list vào `List<String>`.

Spring Boot 3.x hỗ trợ constructor binding với class có một constructor tham số hoặc record phù hợp. Với record ở ví dụ này, **không cần đặt `@ConstructorBinding` trên record** và không cần viết setter.

Java record thích hợp với nhóm cấu hình đọc sau khi khởi động vì:

- Các component được khai báo rõ trong chữ ký của record.
- Object có các accessor `endpoint()`, `enabled()`, `retry()` và `allowedRegions()`.
- Component của record không có setter; dữ liệu được cấp khi object được tạo.
- Các phụ thuộc của service có thể được truyền qua constructor.

Record không bảo đảm tính bất biến sâu của mọi thành phần: chẳng hạn, `List<String>` có thể là một collection có thể thay đổi nếu giữ tham chiếu mutable. Hãy xem cấu hình như dữ liệu đọc và tránh sửa collection sau bind; nếu cần bất biến sâu, có thể tạo bản sao phù hợp trong logic thiết kế.

## 4. Đăng ký đối tượng cấu hình với Spring Boot

Annotation `@ConfigurationProperties` trên một class **không tự động** có nghĩa class đó là Spring bean. Một lựa chọn thông dụng là bật scan trong lớp khởi động.

~~~java
package com.example.delivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }
}
~~~

Với package `com.example.delivery`, `@ConfigurationPropertiesScan` tìm các class cấu hình bên dưới package đó, bao gồm `com.example.delivery.config.DeliveryProperties`.

Một cách đăng ký khác:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {
    // ...
}
~~~

Cách thứ hai hữu ích khi muốn **chỉ định chính xác những loại cấu hình** được đăng ký mà không scan. Trong ví dụ này, hãy chọn một trong hai cách đăng ký; không cần dùng đồng thời cả hai cho cùng class.

### Không gắn `@Component` vào record constructor-bound

Tránh cách viết:

~~~java
@Component
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(URI endpoint, Duration connectTimeout) {
}
~~~

Cấu hình bind qua constructor phải được Spring Boot đăng ký bằng cơ chế configuration-properties thích hợp (`@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`), thay vì để Spring tạo bean như một `@Component` thông thường rồi cố autowire tham số constructor từ bean khác. Với các class JavaBean dùng setter, Spring Boot có hỗ trợ một số mô hình đăng ký khác, nhưng không nên trộn chúng một cách tùy tiện với record constructor binding.

## 5. Inject object cấu hình vào các service

Thay vì đọc placeholder trực tiếp, service nhận một dependency có kiểu:

~~~java
package com.example.delivery.service;

import com.example.delivery.config.DeliveryProperties;
import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties settings;

    public DeliveryService(DeliveryProperties settings) {
        this.settings = settings;
    }

    public String describeConnection() {
        return "Endpoint=" + settings.endpoint()
                + ", timeout=" + settings.connectTimeout()
                + ", retry=" + settings.retry().maxAttempts();
    }

    public boolean supportsRegion(String region) {
        return settings.allowedRegions().contains(region);
    }
}
~~~

Ở đây:

- Không cần thêm `@Value` vào `DeliveryService`.
- Constructor của service nêu rõ rằng nó phụ thuộc `DeliveryProperties`.
- Logic đọc qua `settings.endpoint()` hoặc `settings.retry().backoff()`, thay vì lặp đường dẫn chuỗi `app.delivery.retry.backoff`.
- Khi đổi tên khóa cấu hình, chỉ cần sửa cách bind tại một nơi và các điểm truy cập typed-property liên quan, thay vì tìm từng annotation chuỗi.

Một bean khác dùng cùng object mà không copy cấu hình:

~~~java
package com.example.delivery.service;

import com.example.delivery.config.DeliveryProperties;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRetryPolicy {

    private final DeliveryProperties settings;

    public DeliveryRetryPolicy(DeliveryProperties settings) {
        this.settings = settings;
    }

    public int maxAttempts() {
        return settings.retry().maxAttempts();
    }

    public java.time.Duration backoff() {
        return settings.retry().backoff();
    }
}
~~~

Có thể tiếp tục tách interface hoặc lớp phụ trách nghiệp vụ tùy nhu cầu, nhưng **nguồn tham số** đã được gom trong một object chung. Không cần chuyển mọi bean của ứng dụng sang phụ thuộc vào cùng một class khổng lồ; mỗi nhóm chức năng nên có tiền tố và lớp cấu hình riêng.

## 6. Cách Spring Boot ánh xạ tên YAML sang Java

Spring Boot dùng cơ chế *relaxed binding*. Tên thuộc tính trong cấu hình thường viết theo chuẩn chữ thường, dấu gạch ngang (*kebab-case*), còn component Java dùng camelCase.

| Trong YAML | Trong Java |
| --- | --- |
| `app.delivery.endpoint` | `DeliveryProperties.endpoint()` |
| `app.delivery.enabled` | `DeliveryProperties.enabled()` |
| `app.delivery.connect-timeout` | `DeliveryProperties.connectTimeout()` |
| `app.delivery.retry.max-attempts` | `DeliveryProperties.retry().maxAttempts()` |
| `app.delivery.retry.backoff` | `DeliveryProperties.retry().backoff()` |
| `app.delivery.allowed-regions` | `DeliveryProperties.allowedRegions()` |

Không cần đổi toàn bộ YAML thành tên Java như `connectTimeout`. Nên giữ định dạng chuẩn trong YAML và properties để nhất quán với các nguồn cấu hình khác.

Các loại dữ liệu thường bind được:

- `boolean`: `true`, `false`.
- `int`, `long`: số nguyên phù hợp phạm vi.
- `URI`: địa chỉ như `https://delivery.example.org/api`.
- `Duration`: `250ms`, `4s`, `2m`, `1h`.
- `DataSize`: các chuỗi có đơn vị dung lượng, ví dụ `10MB`, khi field dùng kiểu `org.springframework.util.unit.DataSize`.
- `List<String>` hoặc `List<SomeRecord>`: YAML sequence.
- `Map<String, String>`: các cặp khóa–giá trị dưới một mapping.
- Enum: chuỗi cấu hình được chuyển sang enum phù hợp theo quy tắc chuyển kiểu của Binder.

### Tên biến môi trường tương ứng

Nếu chạy trong môi trường triển khai:

~~~bash
export APP_DELIVERY_ENDPOINT="https://delivery.example.org/api"
export APP_DELIVERY_CONNECTTIMEOUT="7s"
export APP_DELIVERY_RETRY_MAXATTEMPTS="5"
java -jar delivery-app.jar
~~~

Các giá trị được bind về `endpoint`, `connectTimeout` và `retry.maxAttempts`. Khi chuyển tên property chuẩn sang environment variable, dấu chấm `.` trở thành `_`, dấu `-` trong tên thuộc tính bị bỏ, sau đó tên được viết hoa.

Cách viết `APP_DELIVERY_CONNECT_TIMEOUT` có thêm dấu gạch dưới bên trong một component không phải dạng chuyển đổi chuẩn được khuyến nghị cho `connect-timeout`; nên dùng `APP_DELIVERY_CONNECTTIMEOUT`. Tương tự, `max-attempts` thành `MAXATTEMPTS`, không phải mặc nhiên `MAX_ATTEMPTS`.

### Ánh xạ danh sách

Ví dụ:

~~~yaml
app:
  delivery:
    allowed-regions:
      - vn
      - sg
      - th
~~~

Binding đưa dữ liệu vào `List<String>` theo thứ tự. Nếu muốn cung cấp danh sách bằng environment variables, các index của danh sách được biểu diễn trong tên, ví dụ `APP_DELIVERY_ALLOWEDREGIONS_0_=vn` và `APP_DELIVERY_ALLOWEDREGIONS_1_=sg` theo quy tắc môi trường dành cho list index. Với danh sách lớn, file YAML thường dễ đọc hơn.

## 7. Validation: biến lỗi cấu hình thành lỗi khởi động rõ ràng

Chuyển sang cấu hình typed **không tự động bảo đảm** mọi giá trị đều hợp lệ. Ví dụ, nếu `endpoint` không có, constructor có thể nhận `null`; nếu `maxAttempts` là 0, đây vẫn là số nguyên hợp lệ nhưng không phù hợp nghiệp vụ.

Dùng Bean Validation với `@Validated`, `@NotNull`, `@Min`, `@NotBlank`… để tạo hợp đồng rõ hơn.

Trong dự án Spring Boot thường thêm dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Nếu dùng Gradle Version Catalog hoặc BOM do dự án quản lý, điều chỉnh khai báo theo build hiện hành; artifact thể hiện chức năng Bean Validation cần có.

Ví dụ record có validation:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotNull URI endpoint,
        boolean enabled,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry,
        List<String> allowedRegions) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff) {
    }
}
~~~

Các annotation có mục đích khác nhau:

- `@Validated` bật kiểm tra validation trên bean configuration properties khi Binder tạo object.
- `@NotNull` đòi hỏi các component quan trọng phải có giá trị.
- `@Min(1)` ngăn số lần thử lại nhỏ hơn 1.
- `@Valid` yêu cầu kiểm tra các constraint của object lồng nhau `Retry`.

Nếu phần `app.delivery.retry` bị thiếu, `@NotNull` trên component `retry` có thể giúp phát hiện lỗi. Nếu object retry có nhưng `max-attempts=0`, `@Min(1)` báo lỗi.

Đối với chuỗi bắt buộc có nội dung, dùng `@NotBlank String name` thay vì chỉ `@NotNull`. Với URL, `@NotNull URI` kiểm tra sự hiện diện của object; nếu nghiệp vụ yêu cầu scheme `https` và host hợp lệ, cần thêm validation phù hợp cho quy tắc đó.

Khi bind thất bại, Spring Boot có thể báo thông tin như prefix, property, giá trị đầu vào, lỗi chuyển kiểu hoặc constraint bị vi phạm. Thay vì một lỗi sâu bên trong quá trình sử dụng service, lỗi có thể xuất hiện ở thời điểm tạo configuration properties bean.

## 8. Giá trị mặc định nên được đặt ở đâu?

Các `@Value` cũ thường có mặc định trong placeholder:

~~~java
@Value("${app.delivery.connect-timeout:4s}")
private Duration connectTimeout;

@Value("${app.delivery.retry.max-attempts:3}")
private int maxAttempts;
~~~

Khi di chuyển sang `@ConfigurationProperties`, cần **chuyển cả ý nghĩa của default**, không chỉ chuyển tên khóa.

Có ba cách phổ biến.

### 8.1. Khai báo mặc định trong `application.yml`

~~~yaml
app:
  delivery:
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Đây là cách trực quan khi defaults là quyết định cấu hình có thể thay đổi theo môi trường. Với class có validation và các khóa bắt buộc, file hoặc nguồn khác cần cung cấp đầy đủ dữ liệu tương ứng.

### 8.2. Dùng `@DefaultValue` trong constructor binding

Spring Boot hỗ trợ `org.springframework.boot.context.properties.bind.DefaultValue` cho tham số constructor-bound, bao gồm component record:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("500ms") Duration backoff,
        @DefaultValue("true") boolean enabled) {
}
~~~

Khi không có các khóa tương ứng, Binder dùng các mặc định đã khai báo. Các giá trị có mặt từ `Environment` sẽ được ưu tiên và chuyển kiểu như thông thường.

Cách này gắn default trực tiếp với hợp đồng Java. Khi áp dụng, hãy bảo đảm default thực sự hợp lệ ở mọi môi trường, nhất là với thuộc tính liên quan bảo mật.

### 8.3. JavaBean cấu hình có giá trị khởi tạo

Một lựa chọn khác là class mutable với field và setter:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(500);

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }

    public void setBackoff(Duration backoff) {
        this.backoff = backoff;
    }
}
~~~

Bean-style binding giúp một số dự án Java lâu năm chuyển đổi từng bước, nhưng record thường gọn hơn nếu không cần thay đổi object sau khi bind.

**Không nên vô tình tạo nhiều nguồn default khác nhau** như `4s` trong annotation cũ, `5s` trong YAML và `6s` trong constructor. Khi refactor, quyết định nguồn default nào là chủ đích, rồi cập nhật các điểm sử dụng còn lại tương ứng.

## 9. Refactor theo từng bước mà vẫn giữ hành vi

Một lần chuyển đổi an toàn cần quan tâm **giá trị hiệu lực**, cấu trúc bean và tình huống thiếu cấu hình. Quy trình thực hành:

### Bước 1 — Liệt kê các khóa thuộc cùng một chức năng

Ví dụ phát hiện:

~~~text
DeliveryClient
  app.delivery.endpoint
  app.delivery.connect-timeout

DeliveryRetryPolicy
  app.delivery.retry.max-attempts
  app.delivery.retry.backoff

DeliveryFeatureSwitch
  app.delivery.enabled

RegionFilter
  app.delivery.allowed-regions
~~~

Nhóm tất cả dưới prefix `app.delivery`. Ghi nhận kiểu dữ liệu, default và điều kiện validation mà bean hiện có áp dụng. Nếu một khóa chỉ dành cho chức năng khác, đừng cố đưa vào `DeliveryProperties` chỉ vì cùng chữ `app`.

### Bước 2 — Định nghĩa một class cấu hình typed

Tạo `DeliveryProperties` như mục 3. Dùng nested record cho `retry`, `List<String>` cho danh sách, `Duration` cho timeout, `URI` cho endpoint.

### Bước 3 — Đưa defaults và giá trị chung về nguồn đã chọn

Nếu mặc định vẫn thuộc file cấu hình:

~~~yaml
app:
  delivery:
    enabled: true
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Những giá trị bắt buộc như endpoint được cấp ở nơi thích hợp cho từng môi trường; tránh để một endpoint production giả trong ví dụ làm mặc định vận hành thật.

### Bước 4 — Đăng ký bean `@ConfigurationProperties`

Thêm `@ConfigurationPropertiesScan` ở application class, hoặc `@EnableConfigurationProperties(DeliveryProperties.class)` trong configuration. Đây là điều kiện để service có thể inject object bằng constructor.

### Bước 5 — Chuyển từng nơi sử dụng

Trước:

~~~java
@Value("${app.delivery.retry.max-attempts:3}")
private int attempts;
~~~

Sau:

~~~java
private final DeliveryProperties properties;

public DeliveryRetryPolicy(DeliveryProperties properties) {
    this.properties = properties;
}

public int attempts() {
    return properties.retry().maxAttempts();
}
~~~

Khi chuyển, các bean khác vẫn có thể tạm thời dùng `@Value`. Không cần chuyển mọi lớp trong một commit nếu phạm vi lớn; chỉ cần không giữ hai nguồn cấu hình mâu thuẫn cho cùng một giá trị.

### Bước 6 — Loại bỏ các đường đọc cũ sau khi chuyển xong

Khi tất cả nơi sử dụng trong cùng phạm vi đã nhận `DeliveryProperties`, bỏ các field `@Value` tương ứng. Nếu logic nghiệp vụ trước đây có chuyển đổi hoặc fallback riêng, chuyển nó một cách có chủ đích vào cấu hình typed hoặc service phù hợp.

Không nên giữ một `@Value` cũ “đề phòng” trong bean nếu nó có thể gây lỗi thiếu placeholder không còn cần thiết, hoặc khiến người bảo trì hiểu sai rằng còn hai cơ chế cấu hình độc lập.

## 10. Cấu hình theo profile và thứ tự ưu tiên vẫn hoạt động

`@ConfigurationProperties` không tạo thứ tự ưu tiên mới. Nó bind từ `Environment` mà Spring Boot đã xây dựng. Do đó, việc chuyển từ `@Value` sang object typed không đồng nghĩa với việc vô hiệu hóa:

- `application.yml` và các file theo profile như `application-prod.yml`.
- Các tệp được nạp bằng `spring.config.import`.
- Biến môi trường.
- Java system properties.
- Tham số dòng lệnh.

Ví dụ file chung:

~~~yaml
app:
  delivery:
    endpoint: https://sandbox.delivery.example.org/api
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

File `application-prod.yml`:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org/api
    connect-timeout: 2s
~~~

Chạy:

~~~bash
java -jar delivery-app.jar --spring.profiles.active=prod
~~~

Trong ví dụ, `DeliveryProperties.endpoint()` nhận endpoint production và `connectTimeout()` nhận `2s`. Nếu không có nguồn ưu tiên cao hơn, `retry.maxAttempts()` vẫn là `3` và `retry.backoff()` vẫn là `250ms` từ file chung.

Có thể ghi đè riêng retry qua CLI:

~~~bash
java -jar delivery-app.jar --spring.profiles.active=prod --app.delivery.retry.max-attempts=5
~~~

Binder nhận `5` cho `maxAttempts`. Class Java không cần thay đổi.

### Danh sách và cấu hình nhiều nguồn

Với các danh sách như `allowed-regions`, cần nhớ rằng Spring Boot thường **thay cả danh sách** bằng giá trị từ nguồn có ưu tiên cao hơn; nó không đơn giản ghép thêm phần tử vào danh sách cũ. Ví dụ nếu file prod cung cấp `allowed-regions: [vn]`, danh sách cuối không tự giữ `sg` từ file chung.

Với Map và các đối tượng cấu hình lồng nhau, quy tắc hợp nhất và ghi đè có thể khác danh sách. Khi refactor một nhóm thuộc tính có cấu trúc phức tạp, kiểm tra hành vi dự kiến của từng loại dữ liệu.

## 11. Test cấu hình sau khi chuyển đổi

Một lợi ích của object typed là test có thể kiểm tra **cấu hình đã bind** thay vì chỉ kiểm tra từng chuỗi placeholder.

Ví dụ Spring Boot Test:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.delivery.config.DeliveryProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.delivery.endpoint=https://test.delivery.example.org",
        "app.delivery.enabled=true",
        "app.delivery.connect-timeout=6s",
        "app.delivery.retry.max-attempts=4",
        "app.delivery.retry.backoff=200ms",
        "app.delivery.allowed-regions[0]=vn",
        "app.delivery.allowed-regions[1]=sg"
})
class DeliveryPropertiesTest {

    @Autowired
    private DeliveryProperties properties;

    @Test
    void bindsStructuredProperties() {
        assertThat(properties.endpoint()).isEqualTo(
                URI.create("https://test.delivery.example.org"));

        assertThat(properties.connectTimeout()).isEqualTo(
                Duration.ofSeconds(6));

        assertThat(properties.retry().maxAttempts()).isEqualTo(4);
        assertThat(properties.retry().backoff()).isEqualTo(
                Duration.ofMillis(200));

        assertThat(properties.allowedRegions())
                .containsExactly("vn", "sg");
    }
}
~~~

Mẫu này giả định dự án có `spring-boot-starter-test` và lớp `@SpringBootApplication` được tìm thấy. Những thuộc tính test được cấp trực tiếp vào Environment của test context, giúp kiểm tra binder, nested object và chuyển kiểu.

### Kiểm tra validation

Thử đặt `app.delivery.retry.max-attempts=0` khi `@Min(1)` được bật. Việc tạo bean cấu hình phải báo lỗi do ràng buộc này. Tương tự, bỏ endpoint bắt buộc hoặc đặt giá trị Duration không parse được là tình huống cần được nhận diện trong bước khởi động.

Đối với unit test logic nghiệp vụ thuần Java, không cần khởi động cả Spring context. Có thể tạo record cấu hình trực tiếp:

~~~java
DeliveryProperties settings = new DeliveryProperties(
        URI.create("https://mock.example.org"),
        true,
        Duration.ofSeconds(2),
        new DeliveryProperties.Retry(
                2, Duration.ofMillis(100)),
        java.util.List.of("vn")
);

DeliveryService service = new DeliveryService(settings);
~~~

Test như vậy kiểm tra việc service sử dụng object cấu hình mà không phụ thuộc file YAML hoặc môi trường. Với validation annotation, cần lưu ý tạo record trực tiếp **không tự gọi Bean Validation**; validation khi đó phải được kích hoạt riêng nếu test cần kiểm tra constraint.

## 12. Khác biệt giữa `@Value` và `@ConfigurationProperties`

| Tiêu chí | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Mục đích | Lấy một giá trị/biểu thức tại một điểm inject | Bind một nhóm thuộc tính vào object có cấu trúc |
| Cách đặt tên | Placeholder trực tiếp, thường là chuỗi | Prefix + field/record components, dùng relaxed binding |
| Object lồng nhau | Phải tự truy cập hoặc tạo cấu trúc | Bind nested class/record rõ ràng |
| List và Map | Có thể cần cách khai báo/chuyển đổi riêng tùy trường hợp | Binder hỗ trợ collection và Map có cấu trúc |
| Chuyển kiểu | Có hỗ trợ conversion tại điểm inject | Chuyển kiểu thống nhất cho các field |
| Validation | Thường xử lý riêng tại từng bean | Có thể dùng `@Validated` và Bean Validation cho cả object |
| Default | `${key:fallback}` | File cấu hình, `@DefaultValue`, JavaBean default |
| SpEL | Hỗ trợ Spring Expression Language trong `@Value` | Không được thiết kế để đánh giá SpEL trong giá trị cấu hình |
| Khả năng khám phá | Phải tìm ở từng bean | Xem một class để biết nhóm cấu hình cần gì |

### Trường hợp vẫn nên dùng `@Value`

- Chỉ lấy một thuộc tính độc lập, không thuộc một nhóm có ý nghĩa riêng.
- Đọc một biểu thức SpEL có chủ đích mà không phù hợp với binding cấu hình thông thường.
- Một bean nội bộ rất nhỏ chưa có nhu cầu tái sử dụng object cấu hình.

Chuyển sang `@ConfigurationProperties` không có nghĩa cấm tuyệt đối `@Value`. Nên dùng công cụ phù hợp với **độ phức tạp và ranh giới nghiệp vụ** của cấu hình.

## 13. Những lỗi thường gặp khi refactor

### 13.1. Quên đăng ký configuration-properties bean

Đã tạo:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(URI endpoint) {
}
~~~

Nhưng chưa thêm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, service inject `DeliveryProperties` có thể nhận lỗi “No qualifying bean”.

**Cách xử lý:** đăng ký class bằng cơ chế configuration-properties thích hợp.

### 13.2. Prefix không khớp

YAML:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.deliveries")
~~~

Prefix `app.deliveries` không khớp `app.delivery`. Binder không tìm được khóa dự kiến. Với record và validation, có thể gây lỗi thiếu trường bắt buộc; nếu không validation, ứng dụng có nguy cơ nhận `null` hoặc default kiểu nguyên thủy.

**Cách xử lý:** dùng một prefix chuẩn, thống nhất đường dẫn theo YAML, properties, CLI và class.

### 13.3. Chuyển sang record nhưng giữ default cũ ở annotation

Nếu trước đây dùng `@Value("${app.delivery.connect-timeout:4s}")`, khi bỏ `@Value` mà không cấp giá trị trong file hoặc `@DefaultValue`, `connectTimeout` có thể thành `null`.

**Cách xử lý:** đưa default và validation vào thiết kế của `DeliveryProperties`, hoặc bắt buộc người triển khai phải cung cấp thuộc tính.

### 13.4. Bỏ qua object lồng nhau

Nếu YAML không cung cấp `retry`, một record component `Retry retry` có thể là `null`. Khi service gọi `settings.retry().maxAttempts()`, có thể gây `NullPointerException`.

**Cách xử lý:** dùng validation `@NotNull`/`@Valid`, cấp default hợp lệ hoặc kiểm soát trường hợp cấu hình tùy chọn.

### 13.5. Tin rằng kiểu dữ liệu đã đủ xác thực nghiệp vụ

Giá trị `retry.max-attempts=0` bind thành `int` thành công, nhưng không hợp lệ nếu chức năng phải thử ít nhất một lần. `Duration.ofSeconds(-5)` cũng là một object Duration có thể được tạo, dù timeout âm không có nghĩa hợp lệ trong một số API.

**Cách xử lý:** thêm constraint nghiệp vụ thích hợp, ví dụ `@Min(1)` hoặc custom validation cho Duration dương.

### 13.6. Quên thay đổi test

Test cũ có thể gắn `@TestPropertySource` hoặc mock một field `@Value`. Sau khi chuyển, test nên tạo một `DeliveryProperties` phù hợp hoặc cấp đầy đủ thuộc tính để Binder xây dựng object.

**Cách xử lý:** cập nhật các test phụ thuộc cơ chế injection cũ theo mục tiêu của từng test: unit test dùng object Java, integration test dùng Environment và Binder thật.

### 13.7. Giữ bí mật trong `toString()` của record

Java record sinh `toString()` bao gồm các component. Nếu đưa API token hoặc password vào record, log trực tiếp toàn bộ object có thể làm lộ giá trị.

**Cách xử lý:** không ghi log toàn bộ cấu hình nhạy cảm; chỉ log những thuộc tính được phép hiển thị và sử dụng cơ chế secret management phù hợp. Validation và typed binding không tự che giá trị khi mã ứng dụng chủ động in chúng.

### 13.8. Sử dụng bean cấu hình như một object mutable

Với JavaBean chứa setter, có thể vô tình viết `properties.setTimeout(...)` ở runtime, làm trạng thái trong bộ nhớ khác với cấu hình ban đầu. Trong ứng dụng có nhu cầu cập nhật động, cần có thiết kế vòng đời và đồng bộ riêng.

**Cách xử lý:** với cấu hình được đọc lúc khởi động và ít thay đổi, dùng constructor binding/record. Đừng xem thao tác sửa field là cơ chế tự động cập nhật Config Data.

## 14. Một cấu trúc dự án dễ bảo trì

Với nhiều miền chức năng, có thể tách lớp cấu hình theo từng prefix:

~~~text
src/main/java/com/example/app/
├── AppApplication.java
├── delivery/
│   ├── DeliveryService.java
│   ├── DeliveryRetryPolicy.java
│   └── config/
│       └── DeliveryProperties.java
├── email/
│   ├── EmailService.java
│   └── config/
│       └── EmailProperties.java
└── storage/
    ├── StorageService.java
    └── config/
        └── StorageProperties.java
~~~

Trong YAML:

~~~yaml
app:
  delivery:
    endpoint: https://delivery.example.org
    connect-timeout: 4s
    retry:
      max-attempts: 3
      backoff: 250ms

  email:
    from: noreply@example.org
    timeout: 5s

  storage:
    base-path: /var/app/data
~~~

Mỗi service phụ thuộc vào cấu hình của chính miền đó. Một object “`AllApplicationSettings`” có hàng trăm trường sẽ lại tạo ra phụ thuộc rộng và khó kiểm tra, dù đã loại được `@Value`.

Có thể giữ cấu hình tại package riêng `config` hoặc đặt gần module nghiệp vụ; chọn cách nhất quán với kiến trúc và quy ước hiện tại của dự án.

## 15. Bài thực hành chuyển đổi

### Bài 1 — Gom nhóm cấu hình

Đang có:

~~~java
@Value("${app.report.enabled:true}")
private boolean enabled;

@Value("${app.report.max-rows:500}")
private int maxRows;

@Value("${app.report.output-dir:/tmp/reports}")
private String outputDir;
~~~

Hãy tạo `ReportProperties` với prefix `app.report` và ba component tương ứng. Một cách viết:

~~~java
import java.nio.file.Path;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("500") int maxRows,
        @DefaultValue("/tmp/reports") Path outputDir) {
}
~~~

Đăng ký record bằng `@ConfigurationPropertiesScan` rồi inject vào service.

### Bài 2 — Nested properties

Đang dùng:

~~~properties
app.cache.enabled=true
app.cache.redis.host=localhost
app.cache.redis.port=6379
~~~

Hãy xây dựng `CacheProperties` với một record lồng `Redis(String host, int port)`. Dự đoán accessor `settings.redis().host()` trả về `localhost`.

### Bài 3 — Validation

Đổi `app.delivery.retry.max-attempts` thành `0` và áp dụng `@Min(1)` trong nested record. Quan sát lỗi cấu hình lúc khởi động. Thử xóa `app.delivery.endpoint` và dùng `@NotNull` để phát hiện trường bắt buộc.

### Bài 4 — Profile override

Tạo `application-dev.yml` với `connect-timeout: 8s` và `application-prod.yml` với `connect-timeout: 2s`. Chạy với từng profile và kiểm tra `DeliveryProperties.connectTimeout()`. Không sửa mã Java khi đổi môi trường.

### Bài 5 — Unit test không cần Spring

Tạo một `DeliveryProperties` bằng constructor của record rồi truyền vào `DeliveryService`. Kiểm tra phương thức `supportsRegion("vn")` cho kết quả đúng với danh sách đã cấp.

### Bài 6 — Truy ra default bị mất

Sau khi xóa `@Value("${app.delivery.connect-timeout:4s}")`, test nhận `connectTimeout() == null`. Hãy xác định nơi đặt default phù hợp: YAML, `@DefaultValue("4s")` hoặc yêu cầu cấu hình bắt buộc. Giải thích lý do chọn.

## 16. Checklist khi xem một thay đổi từ `@Value` sang object cấu hình

Một thay đổi có thể được xem xét qua các câu hỏi kỹ thuật:

- Các khóa của một miền nghiệp vụ đã được gom dưới prefix rõ ràng hay chưa?
- Mỗi field/record component có kiểu phù hợp với dữ liệu thực tế không?
- Các default trước đây trong `@Value` đã được giữ hoặc thay đổi có chủ đích chưa?
- Config class đã được Spring Boot đăng ký đúng cách chưa?
- Những trường bắt buộc và constraint nghiệp vụ đã được validation phù hợp chưa?
- Các nơi dùng cấu hình đã inject object và bỏ placeholder cũ khi không còn cần chưa?
- Cấu hình theo profile, biến môi trường và CLI có còn cho giá trị hiệu lực dự kiến không?
- Các tình huống thiếu cấu hình, sai kiểu và validation fail có được quan sát trong test phù hợp không?
- Có tình huống nào log toàn bộ object và làm lộ secret không?

Checklist này giúp xác nhận rằng việc thay đổi cấu trúc code **không âm thầm thay đổi ý nghĩa của các thuộc tính đang được sử dụng**.

## 17. Ghi nhớ

`@Value` phù hợp để inject một thuộc tính nhỏ tại một điểm sử dụng. Khi nhiều thuộc tính thuộc cùng một chức năng, dùng `@ConfigurationProperties` sẽ tạo **một hợp đồng cấu hình có cấu trúc**, với tên prefix, kiểu dữ liệu, nested object, list, default và validation rõ ràng.

Với Spring Boot 3.3 và Java 21, một record được đánh dấu `@ConfigurationProperties`, đăng ký qua `@ConfigurationPropertiesScan` và inject bằng constructor là cách ngắn gọn để thay các `@Value` phân tán. Sau khi thay, Spring Boot vẫn dùng cùng cơ chế `Environment` và thứ tự ưu tiên cấu hình; điều cần giữ là **giá trị hiệu lực và hành vi nghiệp vụ** của những thuộc tính cũ.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Boot 3.3 — @Value and Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.vs-value-annotation)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
