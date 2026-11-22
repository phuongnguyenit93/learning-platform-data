# Vai trò của ConversionService trong liên kết cấu hình

## 1. Tại sao liên kết cấu hình cần chuyển đổi kiểu?

Trong Spring Boot Externalized Configuration, giá trị cấu hình có thể được cung cấp từ nhiều nguồn: tệp `application.yml`, `application.properties`, biến môi trường, Java system properties, tham số dòng lệnh và các nguồn Config Data bổ sung. Nhiều nguồn trong số này biểu diễn giá trị dưới dạng văn bản, trong khi mã Java cần làm việc với những **kiểu dữ liệu cụ thể**.

Ví dụ:

```yaml
delivery:
  endpoint: "https://delivery.example.invalid"
  timeout: 3s
  max-attempts: 5
  enabled: true
  max-payload: 2MB
```

Ứng dụng muốn sử dụng cấu hình dưới dạng:

```java
URI endpoint;
Duration timeout;
int maxAttempts;
boolean enabled;
DataSize maxPayload;
```

Chuyển `"3s"` thành `Duration.ofSeconds(3)`, `"5"` thành số nguyên hoặc `"2MB"` thành một đối tượng `DataSize` không phải là phép gán chuỗi thông thường.

Đây là lý do **hệ thống chuyển đổi kiểu của Spring**, đặc biệt là giao diện `ConversionService` và các converter được đăng ký trong đó, có vai trò quan trọng trong quá trình **binding** của `@ConfigurationProperties`.

Tư tưởng chính của bài:

> Binder quyết định thuộc tính nào tương ứng với thành phần Java; hệ thống chuyển đổi kiểu giúp tạo ra giá trị Java đúng kiểu cho thành phần đó.

Hai trách nhiệm liên quan nhưng không đồng nghĩa.

## 2. Từ nguồn cấu hình đến đối tượng Java: toàn bộ luồng xử lý

Giả sử tệp `application.yml` khai báo:

```yaml
client:
  connect-timeout: 5s
  retry-count: 4
  enabled: false
```

Và lớp cấu hình:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        int retryCount,
        boolean enabled) {
}
```

Có thể hình dung quá trình:

```text
application.yml / môi trường / đối số CLI / Config Data
                       |
                       v
             Spring Environment
                       |
                       v
           ConfigurationProperties Binder
                       |
           1. Xác định prefix "client"
           2. Tìm thuộc tính phù hợp
           3. Ánh xạ tên với thành phần Java
                       |
                       v
                 Type conversion
                (ConversionService)
                       |
             "5s"   -> Duration
             "4"    -> int
             "false"-> boolean
                       |
                       v
          ClientProperties object
                       |
                       v
        Spring service nhận bean qua DI
```

Trong ví dụ này, Spring Boot xử lý cả việc chọn nguồn có ưu tiên phù hợp, phân giải tên thuộc tính, chuyển đổi giá trị và khởi tạo bean.

**`ConversionService` không tự quyết định tệp YAML nào được nạp, profile nào đang hoạt động hay nguồn nào có ưu tiên cao hơn.** Nó tham gia ở giai đoạn cần chuyển một giá trị đã được tìm thấy sang kiểu đích thích hợp.

Nếu khóa `client.retry-count` không tồn tại hoặc bị viết sai, chỉ thêm converter `String → Integer` không thể làm binder tự tìm ra tên khóa khác. Đó là vấn đề tìm kiếm/liên kết tên và kiểm soát cấu hình, không phải vấn đề chuyển đổi kiểu.

## 3. ConversionService là gì?

Trong Spring Framework, `ConversionService` là một giao diện cung cấp khả năng **chuyển giá trị từ một kiểu nguồn sang kiểu đích**. Những phương thức quen thuộc gồm:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
```

Ví dụ mang tính khái niệm:

```java
String raw = "42";
Integer number = conversionService.convert(raw, Integer.class);
```

Nếu service có converter phù hợp, kết quả là số nguyên `42`.

Tuy nhiên, `ConversionService` không phải một trình chuyển đổi “bất kỳ kiểu nào sang bất kỳ kiểu nào”. Nó cần có **converter được đăng ký** hoặc cơ chế chuyển đổi tương ứng. Nếu không tồn tại đường chuyển đổi phù hợp, phép chuyển đổi có thể thất bại.

Những giao diện liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `ConversionService` | Cung cấp API kiểm tra và thực hiện chuyển đổi |
| `Converter<S, T>` | Cài đặt phép chuyển từ một kiểu nguồn `S` sang kiểu đích `T` |
| `ConverterFactory<S, R>` | Cung cấp converter cho một họ kiểu đích thuộc `R` |
| `GenericConverter` | Xử lý chuyển đổi tổng quát hơn, có thông tin mô tả kiểu |
| `ConditionalGenericConverter` | Có thể quyết định có hỗ trợ một cặp kiểu trong ngữ cảnh cụ thể hay không |
| `ApplicationConversionService` | Bộ ConversionService do Spring Boot chuẩn bị với nhiều phép chuyển đổi hữu ích cho cấu hình |

Ở tầng Spring Framework, `DefaultConversionService` là một triển khai có các converter thông dụng. Spring Boot bổ sung một bộ conversion thuận tiện hơn cho ứng dụng Boot, bao gồm kiểu thời gian và kích thước dữ liệu thường gặp trong cấu hình.

## 4. ApplicationConversionService của Spring Boot

Spring Boot cung cấp `org.springframework.boot.convert.ApplicationConversionService`, một ConversionService với nhiều phép chuyển đổi chuẩn dành cho ứng dụng.

Nó dựa trên hạ tầng chuyển đổi của Spring Framework và bổ sung những cách hiểu có ý nghĩa trong cấu hình Boot. Ví dụ, một giá trị timeout thường được viết:

```properties
client.connect-timeout=5s
```

Trong Java, giá trị này phù hợp với:

```java
java.time.Duration
```

Tương tự:

```properties
upload.max-size=10MB
```

có thể liên kết vào:

```java
org.springframework.util.unit.DataSize
```

Để quan sát các chuyển đổi có sẵn, có thể thực hành một ví dụ Java độc lập với ngữ cảnh ứng dụng:

```java
import java.time.Duration;

import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.core.convert.ConversionService;
import org.springframework.util.unit.DataSize;

public class ConversionDemo {

    public static void main(String[] args) {
        ConversionService conversions =
                new ApplicationConversionService();

        Integer count = conversions.convert("12", Integer.class);
        Boolean enabled = conversions.convert("true", Boolean.class);
        Duration timeout = conversions.convert("5s", Duration.class);
        DataSize payload = conversions.convert("4MB", DataSize.class);

        System.out.println("count = " + count);
        System.out.println("enabled = " + enabled);
        System.out.println("timeout = " + timeout);
        System.out.println("payload bytes = " + payload.toBytes());
    }
}
```

Ví dụ trên cho thấy **chuyển đổi kiểu độc lập** với việc có tệp `application.yml`. Một `ConversionService` có thể được gọi trực tiếp để thực hiện chuyển đổi, còn binder là thành phần sử dụng khả năng ấy trong quá trình liên kết cấu hình.

Không nên kết luận rằng mọi `ConversionService` mới tạo trong mã đều có cùng converter với service mà binder của ứng dụng đang dùng. Điều này phụ thuộc cách bạn tạo và cấu hình đối tượng conversion.

## 5. Ví dụ đầy đủ với @ConfigurationProperties

### 5.1. Cấu hình đầu vào

Tệp `src/main/resources/application.yml`:

```yaml
upload:
  endpoint: "https://upload.example.invalid"
  timeout: 7s
  max-file-size: 16MB
  max-connections: 20
  enabled: true
```

### 5.2. Record cấu hình với kiểu dữ liệu thật

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "upload")
public record UploadProperties(
        URI endpoint,
        Duration timeout,
        DataSize maxFileSize,
        int maxConnections,
        boolean enabled) {
}
```

Khi bind, Spring Boot cần xử lý các giá trị tương ứng:

| Khóa | Dạng đầu vào | Đích |
| --- | --- | --- |
| `upload.endpoint` | URL dạng chuỗi | `URI` |
| `upload.timeout` | `7s` | `Duration` |
| `upload.max-file-size` | `16MB` | `DataSize` |
| `upload.max-connections` | `20` | `int` |
| `upload.enabled` | `true` | `boolean` |

Không cần tự gọi `Integer.parseInt`, `Duration.parse` hoặc tự tách số khỏi hậu tố `MB` trong lớp nghiệp vụ.

### 5.3. Đăng ký record cấu hình

Lớp ứng dụng:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp Spring Boot tìm và đăng ký những lớp cấu hình được đánh dấu `@ConfigurationProperties` ở package phù hợp.

Có thể dùng `@EnableConfigurationProperties(UploadProperties.class)` nếu muốn đăng ký tường minh thay vì quét.

### 5.4. Sử dụng dữ liệu đã chuyển kiểu

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class UploadConfigPrinter implements ApplicationRunner {

    private final UploadProperties properties;

    public UploadConfigPrinter(UploadProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("URI: " + properties.endpoint());
        System.out.println("Timeout ms: "
                + properties.timeout().toMillis());
        System.out.println("Max bytes: "
                + properties.maxFileSize().toBytes());
        System.out.println("Connections: "
                + properties.maxConnections());
        System.out.println("Enabled: "
                + properties.enabled());
    }
}
```

Với dữ liệu ví dụ, đoạn chương trình có thể in:

```text
URI: https://upload.example.invalid
Timeout ms: 7000
Max bytes: 16777216
Connections: 20
Enabled: true
```

Ở đây `DataSize` sử dụng đơn vị dựa trên hệ nhị phân cho hậu tố `MB` theo cách chuyển đổi của Spring Boot, nên `16MB` tương ứng `16 × 1024 × 1024` byte trong ví dụ.

Giá trị ban đầu có thể đến từ YAML, file Properties, biến môi trường hoặc một nguồn khác; bean nghiệp vụ vẫn đọc một đối tượng Java đã có kiểu.

## 6. Duration: chuỗi cấu hình và đơn vị thời gian

`Duration` là kiểu rất thường gặp: timeout, chu kỳ kiểm tra, thời gian chờ giữa các lần thử lại, TTL.

Spring Boot hỗ trợ các cách viết thuận tiện:

```properties
client.read-timeout=500ms
client.retry-delay=2s
client.cache-ttl=15m
client.session-ttl=1h
```

Các giá trị này có thể liên kết vào những thành phần `Duration` khác nhau.

Ví dụ:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientTimingProperties(
        Duration readTimeout,
        Duration retryDelay,
        Duration cacheTtl,
        Duration sessionTtl) {
}
```

Một số đơn vị có thể gặp:

| Hậu tố | Diễn giải |
| --- | --- |
| `ns` | Nanosecond |
| `us` | Microsecond |
| `ms` | Millisecond |
| `s` | Second |
| `m` | Minute |
| `h` | Hour |
| `d` | Day |

Spring Boot còn có thể hiểu chuỗi theo định dạng thời gian ISO-8601, ví dụ:

```properties
client.read-timeout=PT3S
```

Chuỗi `PT3S` biểu thị ba giây theo cú pháp thời lượng của Java.

**Không nhầm** cú pháp thuận tiện `3s` với cú pháp của chính `Duration.parse("3s")`. `Duration.parse` của Java hướng tới dạng ISO-8601, còn bộ chuyển đổi của Spring Boot hỗ trợ thêm các dạng thân thiện với cấu hình.

### 6.1. Số không ghi đơn vị

Giả sử cấu hình là:

```properties
client.read-timeout=2000
```

Với kiểu `Duration`, Spring Boot mặc định diễn giải một số nguyên không ghi đơn vị theo **millisecond**, nếu không có annotation hoặc cơ chế chuyển đổi khác quy định đơn vị. Vì vậy kết quả dự kiến là hai giây.

Tuy nhiên, kiểu cấu hình này dễ gây hiểu nhầm. Người đọc có thể nghĩ `2000` là giây, millisecond hay microsecond.

**Khuyến nghị:** ghi rõ đơn vị ngay tại nguồn, ví dụ `2000ms` hoặc `2s`.

### 6.2. Điều chỉnh đơn vị mặc định bằng @DurationUnit

Có thể xác định đơn vị cho giá trị không ghi hậu tố:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "client")
public record ClientTimingProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration readTimeout) {
}
```

Với:

```properties
client.read-timeout=5
```

giá trị được hiểu là khoảng năm giây theo annotation.

Nếu nguồn đã nêu rõ `500ms`, dạng có đơn vị được sử dụng để biểu diễn giá trị tương ứng. Annotation chủ yếu giúp xác định cách hiểu số **không ghi đơn vị**.

Trong dự án mới, việc ghi đơn vị ở YAML thường là lựa chọn dễ đọc hơn; `@DurationUnit` có ích khi cần tương thích với một quy ước đầu vào sẵn có.

## 7. DataSize: chuyển cấu hình dung lượng thành đối tượng

Thông số về giới hạn upload, bộ đệm hoặc kích thước dữ liệu nên dùng kiểu `DataSize` thay vì giữ chuỗi.

Ví dụ:

```yaml
storage:
  max-file-size: 50MB
  chunk-size: 512KB
```

Record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        DataSize maxFileSize,
        DataSize chunkSize) {
}
```

Sau khi binding, bạn có thể sử dụng:

```java
long maxBytes = properties.maxFileSize().toBytes();
long chunkBytes = properties.chunkSize().toBytes();
```

Các hậu tố thường được hỗ trợ gồm `B`, `KB`, `MB`, `GB`, `TB`. Giá trị nhận được là một đối tượng mô tả kích thước, giúp tránh việc nhân/chia nhầm trong code.

Khi giá trị không có hậu tố, Boot thường dùng **byte** làm đơn vị mặc định cho `DataSize`.

Để đổi mặc định cho giá trị không ghi hậu tố, có thể dùng `@DataSizeUnit`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize maxFileSize) {
}
```

Khi dùng:

```properties
storage.max-file-size=8
```

giá trị được hiểu theo đơn vị megabyte trong ví dụ này.

**Tư duy đúng:** cấu hình và domain nhận một kiểu có ý nghĩa, còn ConversionService đảm nhiệm chuyển đổi định dạng đầu vào; code nghiệp vụ không nên lặp lại việc phân tích suffix đơn vị.

## 8. Số, Boolean, enum và URI

Không chỉ các kiểu chuyên biệt, binder còn dựa vào chuyển đổi kiểu cho nhiều loại dữ liệu cơ bản.

### 8.1. Số nguyên và số thực

```yaml
queue:
  batch-size: 128
  backoff-multiplier: 1.5
```

Record:

```java
@ConfigurationProperties(prefix = "queue")
public record QueueProperties(
        int batchSize,
        double backoffMultiplier) {
}
```

Nếu giá trị là `batch-size: many`, việc chuyển thành `int` không thành công theo quy tắc thông thường. Đây là lỗi chuyển đổi, không phải lỗi thiếu tên thuộc tính.

### 8.2. Boolean

```yaml
feature:
  enabled: true
```

Java:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(boolean enabled) {
}
```

Sử dụng `boolean` khi tính năng thực sự luôn có trạng thái bật/tắt. Nếu cần phân biệt “chưa cấu hình” với `false`, cân nhắc `Boolean` cùng validation hoặc một giá trị mặc định rõ ràng.

### 8.3. Enum

Giả sử một ứng dụng hỗ trợ các chế độ:

```java
public enum DeliveryMode {
    IMMEDIATE,
    SCHEDULED,
    DISABLED
}
```

Cấu hình:

```yaml
delivery:
  mode: scheduled
```

Record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(DeliveryMode mode) {
}
```

Spring Boot cung cấp các converter hỗ trợ việc ánh xạ kiểu cấu hình quen thuộc sang enum, bao gồm những xử lý thuận tiện về cách viết tên trong nhiều trường hợp.

Nếu tên chế độ hoàn toàn không hợp lệ, chẳng hạn `mode: teleport`, sẽ không có enum `TELEPORT` tương ứng; binding có thể thất bại thay vì tự đoán một giá trị gần giống.

Với những giá trị có tính nghiệp vụ quan trọng, enum giúp compiler và validation làm rõ tập lựa chọn hợp lệ.

### 8.4. URI

```yaml
delivery:
  endpoint: "https://delivery.example.invalid"
```

Record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(java.net.URI endpoint) {
}
```

Chọn `URI` thay vì `String` để biểu đạt đúng ý nghĩa. Nhưng **có kiểu URI chưa đồng nghĩa với kiểm tra tính hợp lệ của endpoint trong nghiệp vụ**: ứng dụng còn có thể cần yêu cầu scheme là HTTPS, host thuộc danh sách được phép hoặc endpoint không rỗng. Đó là nhiệm vụ validation/kiểm tra riêng.

## 9. Chuyển đổi kiểu cho List, Set và Map

Khi thuộc tính là danh sách hoặc map, binder còn có trách nhiệm liên kết cấu trúc, chỉ số và khóa.

Ví dụ:

```yaml
worker:
  retry-delays:
    - 1s
    - 3s
    - 10s
  shard-ids:
    - 1
    - 2
    - 7
  labels:
    team: "orders"
    tier: "backend"
```

Record:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        List<Duration> retryDelays,
        List<Integer> shardIds,
        Map<String, String> labels) {
}
```

Sau khi binding:

```java
Duration firstDelay = properties.retryDelays().get(0);
Integer firstShard = properties.shardIds().get(0);
String team = properties.labels().get("team");
```

Spring Boot có thể chuyển từng phần tử danh sách sang `Duration` hoặc `Integer`. Song **ConversionService không phải là toàn bộ cơ chế ghép cấu trúc**: binder phối hợp việc nhận diện nhánh cấu hình và chỉ số với chuyển đổi kiểu của các phần tử.

Đối với map, tên khóa có thể là dữ liệu động, còn kiểu giá trị của map vẫn có thể cần chuyển đổi.

Nếu một phần tử có giá trị sai kiểu, ví dụ `retry-delays: [1s, invalid-duration]`, binding có thể thất bại do không chuyển được một phần tử.

### 9.1. Lưu ý về collection có thể thay đổi

Record chứa `List<Duration>` không tự đảm bảo danh sách bên trong bất biến sâu. Nếu muốn hạn chế việc chỉnh sửa sau khi khởi tạo, có thể tạo bản sao phòng vệ:

```java
public record WorkerProperties(List<Duration> retryDelays) {

    public WorkerProperties {
        retryDelays = retryDelays == null
                ? List.of()
                : List.copyOf(retryDelays);
    }
}
```

Đây là quyết định thiết kế Java object, không phải một converter mới.

## 10. Giới hạn: converter không sửa được mọi loại lỗi cấu hình

Khi cấu hình không bind được, cần xác định lỗi thuộc giai đoạn nào.

| Vấn đề | Ví dụ | Cơ chế liên quan |
| --- | --- | --- |
| Tên khóa sai | `retry-coutn` thay vì `retry-count` | Tìm khóa/relaxed binding, strict unknown field |
| Nguồn không được nạp | Tệp profile không được kích hoạt | Config Data, profile |
| Nguồn khác ghi đè | CLI override YAML | Thứ tự ưu tiên PropertySource |
| Giá trị sai kiểu | `max-attempts=many` cho `int` | ConversionService/binding |
| Giá trị sai ràng buộc | `max-attempts=-4` | Validation hoặc kiểm tra constructor |
| Đơn vị không rõ | `timeout=3` | Quy tắc chuyển đổi/annotation đơn vị |
| Kiểu đích không có converter | Chuỗi đặc thù sang value object | Custom Converter |
| Bean không được đăng ký | Có annotation nhưng không scan/enable | Đăng ký bean cấu hình |

**ConversionService xử lý vấn đề biểu diễn và kiểu**, không tự quyết định tính hợp lệ của mọi yêu cầu nghiệp vụ. Ví dụ, chuỗi `"-10"` có thể được chuyển thành `int -10` hoàn toàn hợp lệ về mặt kiểu, dù ứng dụng không cho phép số lần thử âm.

Nếu giá trị đúng kiểu nhưng sai quy định, thêm Bean Validation hoặc kiểm tra trong constructor.

## 11. Cách bổ sung Converter<S,T> cho kiểu riêng

Đôi khi một ứng dụng dùng kiểu domain không có converter mặc định.

Giả sử cấu hình muốn nhận mã vùng theo quy ước `VN-SG`, `VN-HN` hoặc tương tự. Ở YAML, người vận hành thích viết đơn giản:

```yaml
routing:
  region: "vn-sg"
  timeout: 2s
```

Trong Java, ta muốn một **value object** `RegionCode` để tránh truyền chuỗi tùy ý khắp hệ thống.

### 11.1. Tạo value object

```java
package com.example.configdemo;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "Region code phải có dạng XX-YY");
        }
    }
}
```

Đối tượng có quy tắc tạo: mã phải chứa hai chữ cái, dấu gạch ngang và hai chữ cái. Nếu muốn mở rộng mã vùng thật, có thể định nghĩa một hợp đồng phù hợp hơn.

### 11.2. Tạo Converter<String,RegionCode>

```java
package com.example.configdemo;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Trách nhiệm của converter:

1. Nhận một `String` từ nguồn.
2. Chuẩn hóa khoảng trắng đầu/cuối.
3. Chuyển chữ cái sang dạng chữ hoa theo locale ổn định.
4. Tạo `RegionCode`, để value object tự kiểm tra tính hợp lệ.

**Không nên âm thầm thay một mã vùng sai bằng mã mặc định** ngay trong converter. Nếu đầu vào là `unknown`, hãy để việc tạo `RegionCode` thất bại với thông tin hữu ích, tránh âm thầm định tuyến sai.

### 11.3. Đăng ký converter riêng cho ConfigurationProperties

Spring Boot hỗ trợ annotation `@ConfigurationPropertiesBinding` nhằm nhận diện các converter dành cho quá trình liên kết `@ConfigurationProperties`.

Có thể viết:

```java
package com.example.configdemo;

import java.util.Locale;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Đây là phiên bản **đã đăng ký Spring bean** của converter. Khi lớp nằm trong phạm vi component scan, Spring Boot có thể sử dụng converter được đánh dấu cho `@ConfigurationProperties`.

Cách làm này giúp chuyển đổi chuyên biệt của cấu hình không bị nhầm với các converter khác của ứng dụng, ví dụ converter dành cho binding tham số HTTP của Spring MVC.

Nếu thích đăng ký bằng `@Bean`, cũng có thể tạo converter tại một lớp `@Configuration` và đánh dấu bean bằng `@ConfigurationPropertiesBinding`. Đối với converter được tạo rất sớm trong quá trình khởi tạo, thường nên giữ phụ thuộc của converter tối thiểu.

### 11.4. Sử dụng trong record cấu hình

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        RegionCode region,
        Duration timeout) {
}
```

Khi đã đăng ký `RoutingProperties` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, binder có thể sử dụng converter vừa viết để tạo thành phần `region`:

```text
routing.region = "vn-sg"
           |
           v
StringToRegionCodeConverter
           |
           v
new RegionCode("VN-SG")
           |
           v
RoutingProperties.region()
```

Các lớp nghiệp vụ chỉ cần sử dụng:

```java
RegionCode region = properties.region();
String canonicalCode = region.value();
```

Chúng không còn phải gọi `trim()` và `toUpperCase()` lặp lại ở nhiều nơi.

## 12. Tránh nhầm @ConfigurationPropertiesBinding với component scanning

Hai annotation:

```java
@Component
@ConfigurationPropertiesBinding
```

có trách nhiệm khác nhau.

- `@Component` khiến lớp trở thành một ứng viên Spring bean khi component scanning được cấu hình và chạy qua package phù hợp.
- `@ConfigurationPropertiesBinding` đánh dấu converter là converter dành cho cơ chế binding cấu hình.

Nếu bạn chỉ tạo một đối tượng bằng:

```java
new StringToRegionCodeConverter()
```

trong mã ứng dụng thông thường nhưng không đăng ký vào hệ thống chuyển đổi mà binder dùng, converter ấy **không tự động trở thành converter của ConfigurationProperties**.

Tương tự, nếu lớp converter không được component scan phát hiện, chỉ có annotation trên source code chưa đủ để chứng minh converter đã có mặt trong ApplicationContext.

Một cách đăng ký rõ ràng khác:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RoutingConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
```

Lưu ý ví dụ này là **cách đăng ký thay thế** cho `@Component` ở phần trước. Trong một ứng dụng, không cần đồng thời đăng ký hai bean converter giống hệt nhau mà không có lý do.

Việc dùng `static @Bean` trong trường hợp thích hợp giúp đăng ký bean mà không cần khởi tạo lớp `@Configuration` chứa factory method quá sớm.

## 13. Kiểm thử converter riêng lẻ

Converter nên có logic nhỏ, rõ ràng để dễ kiểm thử.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToRegionCodeConverterTest {

    private final StringToRegionCodeConverter converter =
            new StringToRegionCodeConverter();

    @Test
    void normalizesValidRegionCode() {
        RegionCode result = converter.convert(" vn-sg ");

        assertEquals("VN-SG", result.value());
    }

    @Test
    void rejectsInvalidRegionCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("invalid"));
    }
}
```

Unit test này kiểm tra **logic chuyển đổi chuỗi sang value object**, không kiểm tra việc Spring Boot thật sự phát hiện converter.

Đó là lý do cần phân biệt hai tầng kiểm thử:

1. **Unit test converter**: xác nhận cách chuyển đổi và lỗi đầu vào.
2. **Test binding**: xác nhận converter được đăng ký và binder thật sự sử dụng nó với `@ConfigurationProperties`.

Một converter đúng nhưng không được đăng ký vẫn không giải quyết được nhu cầu của ứng dụng.

## 14. Kiểm thử binding với ApplicationContextRunner

Spring Boot Test cung cấp `ApplicationContextRunner` để khởi tạo một ApplicationContext nhỏ với các thuộc tính thử nghiệm.

Giả sử đã có:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException("Invalid region");
        }
    }
}
```

Và:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(RegionCode region) {
}
```

Viết một test đăng ký converter và bean cấu hình tường minh:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

class RoutingPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void convertsRegionCodeDuringBinding() {
        runner.withPropertyValues("routing.region=vn-sg")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RoutingProperties properties =
                            context.getBean(RoutingProperties.class);

                    assertThat(properties.region().value())
                            .isEqualTo("VN-SG");
                });
    }

    @Test
    void failsWhenRegionCodeIsInvalid() {
        runner.withPropertyValues("routing.region=broken")
                .run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RoutingProperties.class)
    static class TestConfiguration {

        @Bean
        @ConfigurationPropertiesBinding
        static Converter<String, RegionCode> regionCodeConverter() {
            return value -> new RegionCode(
                    value.trim().toUpperCase(Locale.ROOT));
        }
    }
}
```

Kết quả dự kiến:

- Với `routing.region=vn-sg`, context tạo được bean và giá trị là `VN-SG`.
- Với `routing.region=broken`, converter/value object báo dữ liệu không hợp lệ, khiến quá trình binding của bean cấu hình thất bại.
- Không cần khởi động web server để kiểm tra chuyển đổi kiểu.

Đây là một cách phát hiện sớm vấn đề cấu hình mà không phải chạy toàn bộ ứng dụng rồi quan sát lỗi ở môi trường triển khai.

## 15. Converter, ConverterFactory và GenericConverter khác nhau thế nào?

Với phần lớn nhu cầu cấu hình riêng của một dự án, `Converter<String, T>` là đủ. Tuy nhiên, Spring có các giao diện mở rộng cho những trường hợp khác.

### 15.1. Converter<S,T>

Thích hợp khi biết rõ cặp kiểu.

```java
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String value) {
        return new RegionCode(value.toUpperCase(Locale.ROOT));
    }
}
```

Một converter với trách nhiệm hẹp thường dễ kiểm thử và bảo trì.

### 15.2. ConverterFactory<S,R>

Dùng khi một nhà máy converter phục vụ **nhiều kiểu đích liên quan** thay vì chỉ một lớp đơn. Ví dụ ở mức khái niệm: một factory hỗ trợ chuyển chuỗi sang các kiểu enum khác nhau.

Bạn không cần tự xây `ConverterFactory` chỉ để chuyển `"vn-sg"` sang `RegionCode`. Việc chọn giao diện phức tạp hơn không tự làm phép chuyển đổi chính xác hơn.

### 15.3. GenericConverter

Hữu ích khi phép chuyển đổi cần thông tin kiểu tổng quát hoặc không phù hợp để biểu diễn dưới một cặp `Converter<S,T>` đơn giản.

Ví dụ một hạ tầng chuyển đổi collection có thể cần xem kiểu phần tử đích, không chỉ kiểu của `List`.

### 15.4. ConditionalGenericConverter

Có thể quyết định có hỗ trợ chuyển đổi trong ngữ cảnh cụ thể dựa trên thông tin kiểu nguồn/đích.

Đối với bài toán Externalized Configuration thông thường, chỉ nên dùng những giao diện nâng cao khi có yêu cầu thực sự như nhiều kiểu đích, generic type hoặc điều kiện hỗ trợ phụ thuộc metadata.

## 16. Có nên tạo bean tên conversionService không?

Spring Boot cho phép tùy chỉnh cách chuyển đổi dùng trong ứng dụng. Một lựa chọn là cung cấp một `ConversionService` được đăng ký với tên bean đặc biệt `conversionService` theo cơ chế mà Boot hỗ trợ.

Tuy nhiên, đây là một quyết định có phạm vi rộng hơn việc thêm một converter cho nhóm cấu hình cụ thể.

**Vấn đề cần chú ý:** quá trình binding cấu hình được thực hiện **rất sớm** khi ApplicationContext khởi tạo. Nếu định nghĩa bean `conversionService` tùy chỉnh có nhiều dependency từ các bean ứng dụng khác, có nguy cơ khởi tạo những bean ấy trước thời điểm thích hợp.

Ví dụ, cách tiếp cận thiếu thận trọng:

```java
@Bean(name = "conversionService")
ConversionService conversionService(MyBusinessService service) {
    // Không nên buộc hệ thống chuyển đổi cấu hình
    // phụ thuộc vào service nghiệp vụ tạo muộn.
}
```

Converter cho cấu hình nên là thành phần **nhẹ, độc lập và ít phụ thuộc**, đặc biệt khi phải dùng trong giai đoạn khởi tạo sớm.

Trong nhiều ứng dụng, bạn không cần thay thế toàn bộ ConversionService. Hãy ưu tiên đăng ký converter chuyên biệt bằng `@ConfigurationPropertiesBinding` khi chỉ cần hỗ trợ một kiểu domain cụ thể cho `@ConfigurationProperties`.

Nếu bắt buộc tạo một ConversionService tổng quát, cần hiểu rõ những converter mặc định nào phải được giữ lại, cách tích hợp với Spring Boot và phạm vi tác động của bean mới. Không nên thay service chuẩn bằng một service trống rồi vô tình đánh mất các chuyển đổi hữu ích như `Duration` hoặc `DataSize`.

## 17. Phân biệt conversion cho ConfigurationProperties và conversion ở các tầng khác

Một ứng dụng Spring Boot có thể có nhiều tình huống cần chuyển đổi dữ liệu:

1. Liên kết cấu hình từ `Environment` vào `@ConfigurationProperties`.
2. Chuyển tham số trong URL hoặc form khi xử lý request Spring MVC.
3. Chuyển dữ liệu trong một ứng dụng dùng Spring Data.
4. Chuyển giá trị biểu thức hoặc property placeholder ở các điểm tiêm.
5. Chuyển dữ liệu do mã nghiệp vụ tự gọi thông qua một `ConversionService` cụ thể.

Không nên giả định rằng một converter đăng ký trong **Spring MVC formatting registry** sẽ tự động được sử dụng làm converter của configuration-properties binder.

Tương tự, một converter được đánh dấu `@ConfigurationPropertiesBinding` được khai báo để phục vụ **binding cấu hình**, không nhất thiết trở thành quy tắc xử lý mọi loại dữ liệu vào của HTTP request.

Nếu một quy tắc chuyển đổi cần được chia sẻ bởi nhiều tầng, hãy chủ động thiết kế cách đăng ký phù hợp ở các tầng đó, tránh phụ thuộc vào hành vi ngầm.

## 18. @Value và @ConfigurationProperties có giống nhau về chuyển đổi kiểu không?

Cả hai đều có thể cung cấp giá trị có kiểu cho Java, nhưng cách sử dụng không giống hệt.

**@Value cho một giá trị đơn:**

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PollingService {

    private final Duration interval;

    public PollingService(
            @Value("${polling.interval:3s}") Duration interval) {
        this.interval = interval;
    }
}
```

**@ConfigurationProperties cho một nhóm giá trị:**

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "polling")
public record PollingProperties(
        Duration interval,
        int batchSize,
        boolean enabled) {
}
```

Cả hai cơ chế có thể sử dụng hạ tầng chuyển đổi kiểu của Spring, nhưng **không nên coi mọi converter được gắn `@ConfigurationPropertiesBinding` đương nhiên có hiệu lực y hệt khi dùng trong `@Value`**. Các điểm tiêm `@Value` được xử lý bởi cơ chế placeholder/dependency injection của Spring, còn `@ConfigurationProperties` sử dụng binder với nhiều tính năng chuyên biệt.

Khi cần một nhóm thông số có kiểu, đặc biệt là cấu hình lồng nhau, danh sách, giá trị mặc định và validation, `@ConfigurationProperties` thường phù hợp hơn.

Với một giá trị độc lập, `@Value` vẫn tiện lợi và không phải trường hợp nào cũng cần tạo một record cấu hình mới.

## 19. Conversion không phải validation

Một chuỗi có thể chuyển đổi thành kiểu Java thành công nhưng **vẫn không hợp lệ về mặt nghiệp vụ**.

Ví dụ:

```yaml
job:
  max-attempts: -3
  timeout: -5s
```

Bộ chuyển đổi có thể tạo được:

```java
int maxAttempts = -3;
Duration timeout = Duration.ofSeconds(-5);
```

Đây là các giá trị hợp lệ xét riêng ở cấp **kiểu dữ liệu**. Nhưng ứng dụng có thể yêu cầu số lần thử ít nhất bằng 1 và timeout phải dương.

Để kiểm tra ràng buộc:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "job")
public record JobProperties(
        @Min(1) int maxAttempts,
        @NotNull Duration timeout) {

    public JobProperties {
        if (timeout != null && !timeout.isPositive()) {
            throw new IllegalArgumentException(
                    "job.timeout phải là thời lượng dương");
        }
    }
}
```

Lưu ý: đoạn trên minh họa kiểm tra trong constructor kết hợp Bean Validation; `@NotNull` không tự bảo đảm một `Duration` lớn hơn 0.

Để dùng Jakarta Bean Validation với Spring Boot, dự án thường cần dependency `spring-boot-starter-validation`.

Sự phân biệt:

| Giai đoạn | Câu hỏi |
| --- | --- |
| Chọn nguồn | Lấy giá trị từ nơi nào? |
| Liên kết tên | Khóa cấu hình tương ứng với field/parameter nào? |
| Chuyển đổi kiểu | Có tạo được `Duration`, `int`, `URI`... không? |
| Validation | Giá trị Java có đáp ứng yêu cầu bắt buộc/nghiệp vụ không? |
| Tạo bean | Đối tượng đã đủ điều kiện cho ứng dụng sử dụng chưa? |

Việc đặt converter để tự chữa dữ liệu sai không luôn là lựa chọn tốt. Cần để lỗi cấu hình quan trọng lộ ra rõ ràng.

## 20. Mặc định không thay thế việc chuyển đổi kiểu

Spring Boot hỗ trợ `@DefaultValue` cho constructor binding, ví dụ:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "task")
public record TaskProperties(
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int maxAttempts) {
}
```

Nếu thuộc tính không có trong những nguồn được binder xem xét, giá trị mặc định dạng chuỗi được **chuyển sang kiểu đích**.

Ví dụ:

```yaml
task:
  max-attempts: 8
```

Khi đó:

```text
timeout     = Duration.ofSeconds(5)
maxAttempts = 8
```

Nếu nguồn có:

```yaml
task:
  timeout: nonsense
```

không nên nghĩ rằng mặc định `5s` sẽ tự thay thế mọi giá trị không chuyển được. Thuộc tính đã hiện diện nhưng sai định dạng; việc binding có thể thất bại. Bỏ qua lỗi chuyển đổi và dùng một giá trị thay thế chỉ nên xảy ra khi thiết kế có chủ đích và được kiểm thử rõ.

## 21. ConversionService với cấu hình theo profile và nguồn ưu tiên

Giả sử:

```yaml
# application.yml
client:
  timeout: 5s
```

```yaml
# application-prod.yml
client:
  timeout: 2s
```

Và:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(java.time.Duration timeout) {
}
```

Khi profile `prod` đang hoạt động, nguồn cấu hình dành cho profile ấy có thể cung cấp giá trị `2s` theo quy tắc Config Data.

Nếu chạy:

```bash
java -jar app.jar --spring.profiles.active=prod --client.timeout=900ms
```

đối số dòng lệnh cung cấp giá trị có ưu tiên cao hơn các tệp Config Data trong cấu hình Spring Boot thông thường, nên binder có thể nhận giá trị `900ms`.

**ConversionService được dùng để chuyển `"900ms"` thành `Duration`**, nhưng **nó không quyết định rằng CLI phải thắng YAML**.

Mô hình đầy đủ hơn:

```text
PropertySource priority
      |
      v
"900ms" là giá trị có hiệu lực
      |
      v
Binder nhận client.timeout
      |
      v
ConversionService chuyển "900ms" -> Duration
      |
      v
ClientProperties(timeout=PT0.9S)
```

Hiểu đúng ranh giới này giúp chẩn đoán lỗi: nếu kiểu đã đúng nhưng giá trị bất ngờ, thường cần kiểm tra **nguồn cấu hình** trước khi thay converter.

## 22. Những ngoại lệ thường gặp khi chuyển đổi thất bại

Trong quá trình binding, Spring Boot và Spring Framework có thể báo lỗi liên quan tới chuyển đổi kiểu. Tùy đường đi của lỗi, có thể thấy những lớp ngoại lệ như:

- `ConversionFailedException` trong hệ thống conversion;
- `ConverterNotFoundException` khi không có phép chuyển đổi phù hợp;
- `BindException` thuộc binder;
- `ConfigurationPropertiesBindException` khi quá trình tạo bean cấu hình thất bại.

Những tên này mô tả các tầng khác nhau của lỗi; không phải mọi tình huống đều ném ra chính xác cùng một lớp ngoại lệ hay cùng một thông điệp.

Ví dụ:

```properties
client.connect-timeout=abc
```

Bean yêu cầu:

```java
Duration connectTimeout
```

Nhưng `abc` không phải biểu diễn thời lượng hợp lệ cho converter được sử dụng. Kết quả có thể là lỗi binding trong lúc khởi động.

Khi đọc log, hãy tìm:

1. **Tên property** đang được bind.
2. **Giá trị** hoặc nguồn khiến lỗi xảy ra.
3. **Kiểu đích** mà binder cần tạo.
4. **Nguyên nhân sâu** trong chuỗi exception.
5. Thông tin về nguồn Config Data, nếu được log cung cấp.

Tránh dựa vào một chuỗi log cố định trong test vì nó có thể thay đổi giữa các phiên bản Spring Boot.

## 23. Lỗi thường gặp: nhầm chuỗi "5s" với Duration.parse

Trong Java chuẩn:

```java
Duration.parse("PT5S");
```

là một cách parse hợp lệ, nhưng:

```java
Duration.parse("5s");
```

không dùng cùng cú pháp và có thể ném exception.

Spring Boot lại hỗ trợ một định dạng thời lượng thuận tiện:

```properties
client.timeout=5s
```

và liên kết với:

```java
Duration timeout
```

Điều này không có nghĩa mọi API Java đều chấp nhận hậu tố `s`. Nếu tự viết converter, đừng trộn lẫn kỳ vọng về cú pháp của `Duration.parse` và cú pháp thân thiện của Spring Boot mà không có chủ đích.

Khi cần cấu hình thời lượng chuẩn, sử dụng `Duration` với binder mặc định là cách rõ ràng hơn việc để mỗi service tự phân tích chuỗi.

## 24. Lỗi thường gặp: converter được tạo nhưng binder không dùng

Xét một converter:

```java
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source);
    }
}
```

Nếu chỉ có tệp Java này trong dự án, chưa chắc Spring đã đăng ký nó.

Hãy kiểm tra:

- Lớp có được đăng ký là bean chưa?
- Converter có được đánh dấu `@ConfigurationPropertiesBinding` nếu được dùng cho binder không?
- Nó có nằm trong phạm vi component scan không?
- Bean `@ConfigurationProperties` cần converter có được đăng ký không?
- Tên kiểu đích trong lớp cấu hình có đúng là `RegionCode` không?
- Nguồn dữ liệu có thật sự cung cấp giá trị chuỗi mà converter có thể xử lý không?

Đôi khi developer đã đăng ký converter cho Spring MVC và dùng nó với request parameter thành công, nhưng lại thấy `@ConfigurationProperties` không dùng converter đó. Điều này có thể xảy ra vì các tầng dùng hệ thống conversion/registry khác nhau.

**Đăng ký đúng nơi quan trọng không kém việc viết đúng phương thức `convert`.**

## 25. Lỗi thường gặp: thiếu khóa hoặc đặt sai prefix

Ví dụ bean:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

nhưng YAML ghi:

```yaml
clients:
  timeout: 5s
```

Khóa thực tế là `clients.timeout`, còn bean tìm `client.timeout`.

Dù `ApplicationConversionService` hỗ trợ chuyển `"5s"` sang `Duration`, binder không thể tự dùng converter để sửa chữ `client` thành `clients`.

Đây là lỗi **khớp khóa**, không phải lỗi chuyển đổi kiểu.

Cách chẩn đoán:

1. Kiểm tra `prefix` của bean.
2. Kiểm tra tên chuẩn trong YAML hoặc Properties.
3. Kiểm tra bean cấu hình đã được đăng ký.
4. Kiểm tra tệp có được nạp theo profile hiện tại.
5. Nếu giá trị đã đến được binder nhưng sai định dạng, lúc ấy mới tập trung vào conversion.

Có thể kết hợp `@Validated`, annotation bắt buộc và `ignoreUnknownFields = false` để phát hiện thêm một số lỗi cấu hình, nhưng mỗi cơ chế có phạm vi riêng.

## 26. Lỗi thường gặp: bean conversionService có dependency quá sớm

Trong nhiều ứng dụng, `@ConfigurationProperties` được dùng ngay khi Spring Boot đang tạo những thành phần hạ tầng.

Nếu tạo một `conversionService` tùy chỉnh mà constructor phụ thuộc vào bean nghiệp vụ cần các cấu hình khác, bạn có thể tạo quan hệ phụ thuộc vòng hoặc khởi tạo sớm khó hiểu.

Ví dụ về một thiết kế nên tránh:

```text
conversionService bean
      -> NotificationService
             -> NotificationProperties
                    -> cần ConversionService để bind
```

Hướng xử lý:

- Giữ converter **stateless** nếu có thể.
- Không gọi mạng hoặc cơ sở dữ liệu trong converter chỉ để phân tích một chuỗi cấu hình.
- Không để conversion phụ thuộc vào service mà chính việc tạo service cần thuộc tính cấu hình.
- Cân nhắc `@ConfigurationPropertiesBinding` cho converter có phạm vi hẹp.
- Nếu cần custom ConversionService toàn cục, thiết kế và kiểm thử thứ tự khởi tạo cẩn thận.

Việc chuyển đổi kiểu cho cấu hình nên có khả năng chạy ngay khi ứng dụng mới bắt đầu, không phụ thuộc vào toàn bộ hạ tầng nghiệp vụ đã sẵn sàng.

## 27. Lỗi thường gặp: dùng converter để che dấu cấu hình sai

Giả sử giá trị cấu hình:

```properties
delivery.mode=immedaite
```

Người vận hành muốn `immediate` nhưng gõ sai. Một converter nguy hiểm có thể chọn cách:

```java
return DeliveryMode.IMMEDIATE;
```

cho **mọi** chuỗi không nhận diện.

Ứng dụng vẫn chạy nhưng người cấu hình không biết đã mắc lỗi. Tùy mục đích, đây là hành vi không an toàn vì nó tạo cấu hình ngầm.

Một thiết kế tốt hơn:

```java
@Override
public DeliveryMode convert(String value) {
    String normalized = value.trim().toUpperCase(Locale.ROOT);
    try {
        return DeliveryMode.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "delivery.mode không hợp lệ: " + value, ex);
    }
}
```

Đoạn này chỉ là ví dụ cho converter của một enum do ứng dụng định nghĩa. Spring Boot vốn đã có chuyển đổi enum thông thường; không cần tự viết lại trừ khi có cú pháp riêng.

Với đầu vào sai, việc báo lỗi sớm thường đáng tin cậy hơn việc tự đoán.

## 28. Bảng chọn giải pháp

| Nhu cầu | Giải pháp phù hợp |
| --- | --- |
| Bind `int`, `boolean`, `URI` | Converter mặc định của Spring Boot |
| Bind `Duration` hoặc `DataSize` | Converter có sẵn trong hệ thống Boot |
| Quy định đơn vị cho số không có suffix | `@DurationUnit`, `@DataSizeUnit` hoặc ghi đơn vị tường minh |
| Bind tên enum | Hệ thống chuyển đổi enum mặc định |
| Bind kiểu domain riêng từ chuỗi | `Converter<String,T>` + `@ConfigurationPropertiesBinding` |
| Bind nhiều trường liên quan | `@ConfigurationProperties` thay vì parse thủ công |
| Bắt giá trị âm hoặc giới hạn sai | Bean Validation hoặc kiểm tra constructor |
| Bắt tên khóa sai | Kiểm tra prefix, metadata, strict binding và test |
| Chọn giá trị từ CLI, biến môi trường, YAML | Cơ chế PropertySource/Config Data priority |
| Cần cấu hình cập nhật khi chạy | Thiết kế cơ chế refresh/rebind riêng; ConversionService không tự thực hiện |

Bảng trên nhấn mạnh việc **chọn đúng tầng xử lý**. Nhiều lỗi có biểu hiện “giá trị cấu hình không đúng” nhưng nguyên nhân thật sự thuộc một tầng khác.

## 29. Bài tập A: dự đoán giá trị sau khi chuyển đổi

Cho tệp:

```yaml
batch:
  size: 64
  interval: 250ms
  payload-limit: 1MB
  enabled: false
```

Và record:

```java
@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        int size,
        Duration interval,
        DataSize payloadLimit,
        boolean enabled) {
}
```

Hãy dự đoán các giá trị:

| Biểu thức Java | Kết quả |
| --- | --- |
| `properties.size()` | `64` |
| `properties.interval().toMillis()` | `250` |
| `properties.payloadLimit().toBytes()` | `1048576` |
| `properties.enabled()` | `false` |

Giải thích: binder tìm các tên tương ứng, còn hệ thống conversion tạo các giá trị đúng kiểu.

## 30. Bài tập B: chuyển kiểu hay lỗi khóa?

Cho bean:

```java
@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        int maxConnections,
        Duration acquireTimeout) {
}
```

Xét ba tình huống:

**Trường hợp 1**

```yaml
pool:
  max-connections: many
  acquire-timeout: 2s
```

**Trường hợp 2**

```yaml
pool:
  max-conections: 8
  acquire-timeout: 2s
```

**Trường hợp 3**

```yaml
pools:
  max-connections: 8
  acquire-timeout: 2s
```

Đáp án:

1. Tên `max-connections` đúng, nhưng `many` không chuyển được sang `int` → lỗi conversion/binding.
2. `max-conections` sai chính tả → binder có thể không liên kết với `maxConnections`, không thể khắc phục chỉ bằng converter.
3. Sai prefix `pools` thay vì `pool` → binder có thể không thấy cả nhóm cấu hình; phải sửa nguồn hoặc cấu hình prefix.

Một công cụ có nhiều converter không đồng nghĩa có khả năng sửa tên khóa.

## 31. Bài tập C: viết Converter cho loại giá trị riêng

Giả sử ứng dụng cần một mã kênh gồm đúng ba chữ cái và muốn chấp nhận cấu hình chữ thường.

Value object:

```java
public record ChannelCode(String value) {

    public ChannelCode {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid channel code");
        }
    }
}
```

Hãy viết converter:

```java
import java.util.Locale;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class StringToChannelCodeConverter
        implements Converter<String, ChannelCode> {

    @Override
    public ChannelCode convert(String value) {
        return new ChannelCode(
                value.trim().toUpperCase(Locale.ROOT));
    }
}
```

Với `channel.code=web`, kết quả mong đợi là `ChannelCode("WEB")`. Nếu cấu hình `channel.code=mobile` (sáu chữ cái), constructor từ chối giá trị.

## 32. Bài tập D: tại sao chỉ custom converter chưa đủ?

Giả sử bạn đã viết:

```java
class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    // ...
}
```

Nhưng không đăng ký bean hay thêm converter vào registry.

**Câu hỏi:** binder có nhất thiết biết phép chuyển này không?

**Đáp án:** không. Một lớp tồn tại trong mã không tự được Spring Boot phát hiện như converter cấu hình. Cần đăng ký theo một cơ chế được hỗ trợ, ví dụ bean `@ConfigurationPropertiesBinding`.

## 33. Bài tập E: timeout không có đơn vị

Tệp:

```properties
client.timeout=7
```

Record:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

**Câu hỏi:** nếu không có đơn vị hoặc annotation khác, Spring Boot thường hiểu `7` là gì?

**Đáp án:** khoảng **7 millisecond** theo đơn vị mặc định của `Duration` trong binding thông thường.

Nếu yêu cầu là 7 giây, sửa thành:

```properties
client.timeout=7s
```

hoặc khai báo đơn vị thích hợp với `@DurationUnit` cho tham số tương ứng.

## 34. Bài tập F: kiểm tra thất bại ở tầng nào?

Cho:

```yaml
task:
  timeout: -3s
  max-attempts: -2
```

Và record:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(
        Duration timeout,
        int maxAttempts) {
}
```

Các giá trị này có thể chuyển thành `Duration` và `int` tương ứng, nhưng có hợp lệ với một tác vụ thực tế không?

**Đáp án:** chưa chắc. Nếu thời gian chờ phải dương và số lần thử ít nhất bằng một, cần **validation hoặc kiểm tra constructor**. Chuyển đổi kiểu thành công không bảo đảm đầu vào hợp lệ về mặt nghiệp vụ.

## 35. Quy trình chẩn đoán khi binding thất bại

Khi Spring Boot báo lỗi liên kết cấu hình, có thể xử lý tuần tự:

1. **Xác định bean và prefix** đang được bind. Nếu prefix sai, mọi converter đều không giúp tìm được dữ liệu.
2. **Xác định nguồn có hiệu lực:** file theo profile, file import, biến môi trường, Java system property hay đối số dòng lệnh.
3. **Kiểm tra khóa chuẩn:** có đúng chính tả và được relaxed binding hiểu như mong muốn không?
4. **Xem dạng giá trị:** số, Boolean, đơn vị thời gian, đơn vị dữ liệu, enum, URI hay một mã domain riêng?
5. **Xem kiểu Java đích:** có converter mặc định hỗ trợ không? Nếu cần custom converter, nó đã được đăng ký cho binder chưa?
6. **Kiểm tra ràng buộc nghiệp vụ:** kiểu đã chuyển được nhưng giá trị có đạt validation không?
7. **Viết test nhỏ:** dùng ApplicationContextRunner với giá trị hợp lệ và sai để khóa chặt hành vi mong muốn.
8. **Tránh log secret:** chỉ in khóa minh họa không nhạy cảm hoặc metadata cần thiết, không in toàn bộ mật khẩu/token.

Những bước này giúp tránh sửa sai tầng. Ví dụ, nếu nguyên nhân là một khóa tên `client.timeoutt`, việc thêm một converter cho `Duration` không giải quyết được gì.

## 36. Ghi nhớ

- `ConversionService` là hạ tầng chuyển đổi kiểu của Spring; binder của `@ConfigurationProperties` sử dụng khả năng chuyển đổi để tạo ra giá trị Java đúng kiểu.
- `ApplicationConversionService` của Spring Boot cung cấp nhiều phép chuyển đổi mặc định hữu ích, đặc biệt cho kiểu thường xuất hiện trong cấu hình như `Duration` và `DataSize`.
- **Binder chịu trách nhiệm liên kết tên và cấu trúc; ConversionService chịu trách nhiệm chuyển giá trị sang kiểu phù hợp.** Hai phần phối hợp, không thay thế nhau.
- Ghi đơn vị rõ ràng như `500ms`, `3s`, `2MB` giúp giảm hiểu nhầm; `@DurationUnit` và `@DataSizeUnit` hỗ trợ thiết lập đơn vị cho số không có hậu tố.
- Khi kiểu domain không có converter phù hợp, có thể tự viết `Converter<String,T>` và đăng ký với `@ConfigurationPropertiesBinding`.
- Converter tùy chỉnh cần **được Spring đăng ký đúng cách**, và nên có phụ thuộc tối thiểu vì quá trình binding diễn ra sớm.
- Converter của Spring MVC, converter của binder cấu hình và converter được mã nghiệp vụ gọi không mặc nhiên là cùng một registry.
- **Chuyển đổi kiểu không đồng nghĩa validation**: số âm có thể chuyển thành `int` nhưng vẫn sai yêu cầu nghiệp vụ.
- **ConversionService không sửa khóa sai, không chọn profile, không quyết định PropertySource precedence và không tự refresh cấu hình.**
- Kiểm thử converter riêng lẻ lẫn test binding với ApplicationContextRunner giúp phát hiện sớm cả lỗi xử lý giá trị lẫn lỗi đăng ký converter.
