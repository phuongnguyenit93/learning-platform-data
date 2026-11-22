# Chuyển chuỗi thành số, boolean, enum và kiểu chuẩn trong Spring Boot

Spring Boot cho phép cung cấp cấu hình từ `application.properties`, `application.yml`, biến môi trường, Java system properties, tham số dòng lệnh và nhiều nguồn khác. Các giá trị này thường được biểu diễn dưới dạng văn bản, trong khi mã Java lại cần những kiểu dữ liệu rõ ràng như `int`, `boolean`, `BigDecimal`, `Duration`, `URI` hay enum.

Khi sử dụng `@ConfigurationProperties`, Spring Boot **Configuration Binder** không chỉ tìm thuộc tính theo tên mà còn chuyển giá trị nguồn thành kiểu Java tương ứng. Nhờ vậy, một service có thể nhận một object cấu hình có kiểu thay vì tự gọi `Integer.parseInt(...)`, `Boolean.parseBoolean(...)` hay viết converter rải rác.

Ví dụ:

~~~properties
app.client.max-connections=12
app.client.enabled=true
app.client.mode=ACTIVE
app.client.connect-timeout=3s
app.client.endpoint=https://api.example.org
~~~

Có thể bind thành một record gồm `int maxConnections`, `boolean enabled`, `ClientMode mode`, `Duration connectTimeout` và `URI endpoint`.

Bài học dùng Spring Boot 3.3.x và Java 21; giải thích các nhóm chuyển đổi thường gặp, cách khai báo trong YAML/properties/biến môi trường, lỗi conversion, validation và kiểm thử.

## 1. Phân biệt tên thuộc tính, chuyển đổi kiểu và validation

Khi đọc một thuộc tính, thường có ba vấn đề khác nhau:

1. **Tìm property:** chọn giá trị hiệu lực của `app.client.max-connections` từ các `PropertySource`.
2. **Chuyển đổi kiểu:** đổi văn bản `"12"` thành giá trị Java kiểu `int`.
3. **Validation:** kiểm tra `12` có đáp ứng quy tắc nghiệp vụ, ví dụ lớn hơn 0 và nhỏ hơn 1000.

Ví dụ:

~~~properties
app.client.max-connections=abc
~~~

Nếu Java yêu cầu `int`, giá trị không thể được chuyển thành số nguyên thông thường. Đây là lỗi **conversion/binding**.

~~~properties
app.client.max-connections=-3
~~~

`-3` chuyển thành `int` được, nhưng có thể vi phạm ràng buộc nghiệp vụ `@Min(1)`. Đây là lỗi **validation**, không phải lỗi cú pháp số.

Một vấn đề khác:

~~~yaml
app:
  client:
    max-connetions: 12
~~~

Tên `max-connetions` sai chính tả so với `max-connections`. Binder có thể không tìm thấy thuộc tính; với kiểu nguyên thủy `int`, giá trị kết quả có thể là 0 mà không báo lỗi. Trường hợp này không giống lỗi chuyển chuỗi `"abc"` thành số.

Sơ đồ:

~~~text
Properties / YAML / Environment / CLI
                 |
                 v
     Environment + PropertySource
                 |
                 v
       @ConfigurationProperties Binder
                 |
                 +-- tìm tên (relaxed binding)
                 +-- chọn giá trị hiệu lực
                 +-- chuyển thành kiểu Java
                 +-- tạo object/nested object
                 +-- validation nếu được bật
                 |
                 v
              Service
~~~

Binder có các converter thông dụng, nhưng không tự hiểu mọi định dạng hay mọi kiểu nghiệp vụ do ứng dụng định nghĩa.

## 2. Dựng ví dụ nhiều kiểu trong một record

Tạo enum:

~~~java
package com.example.configdemo.config;

public enum ClientMode {
    ACTIVE,
    PASSIVE,
    MAINTENANCE
}
~~~

Tạo `ClientProperties.java`:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        int maxConnections,
        boolean enabled,
        ClientMode mode,
        Duration connectTimeout,
        URI endpoint) {
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
app:
  client:
    max-connections: 12
    enabled: true
    mode: ACTIVE
    connect-timeout: 3s
    endpoint: https://api.example.org
~~~

Đăng ký class cấu hình trong ứng dụng:

~~~java
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
~~~

Với package `com.example.configdemo.config` ở dưới package ứng dụng, `@ConfigurationPropertiesScan` tìm được record. Cũng có thể thay bằng `@EnableConfigurationProperties(ClientProperties.class)` khi muốn đăng ký tường minh.

Tạo một bean đọc cấu hình:

~~~java
package com.example.configdemo;

import com.example.configdemo.config.ClientProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientSettingsPrinter {

    @Bean
    ApplicationRunner showSettings(ClientProperties properties) {
        return args -> {
            System.out.println("connections=" + properties.maxConnections());
            System.out.println("enabled=" + properties.enabled());
            System.out.println("mode=" + properties.mode());
            System.out.println("timeout=" + properties.connectTimeout());
            System.out.println("endpoint=" + properties.endpoint());
        };
    }
}
~~~

Kết quả:

~~~text
connections=12
enabled=true
mode=ACTIVE
timeout=PT3S
endpoint=https://api.example.org
~~~

`PT3S` là biểu diễn ISO-8601 của `Duration.ofSeconds(3)`. Kết quả giả định không có nguồn ưu tiên cao hơn thay những khóa trong YAML.

## 3. Số nguyên: int, long, short và BigInteger

Một số kiểu số nguyên Java:

| Kiểu | Khoảng giá trị điển hình |
| --- | --- |
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `int` | -2.147.483.648 đến 2.147.483.647 |
| `long` | Xấp xỉ ±9,22 × 10^18 |
| `BigInteger` | Số nguyên độ chính xác tùy ý trong giới hạn tài nguyên |

Ví dụ cấu hình:

~~~properties
app.limits.retry-count=4
app.limits.worker-count=16
app.limits.total-records=9000000000
app.limits.external-id=123456789012345678901234567890
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.math.BigInteger;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.limits")
public record LimitProperties(
        int retryCount,
        short workerCount,
        long totalRecords,
        BigInteger externalId) {
}
~~~

Binder chuyển chuỗi số thành kiểu tương ứng. Ví dụ `9000000000` không vừa phạm vi `int` nhưng nằm trong phạm vi `long`.

### Giá trị vượt phạm vi

~~~properties
app.limits.worker-count=40000
~~~

`40000` vượt phạm vi `short`. Nếu target type là `short`, conversion có thể thất bại. Không nên thay mọi field bằng `long` chỉ để né lỗi; cần chọn kiểu theo quy mô thực và đặt validation cho phạm vi nghiệp vụ.

### Giá trị không phải số

~~~properties
app.limits.retry-count=four
~~~

Chuỗi `four` không phải cú pháp số nguyên thông thường. Trong quá trình binding, có thể xuất hiện lỗi với nguyên nhân gốc `NumberFormatException` hoặc `ConversionFailedException`, được bọc bởi các exception liên quan bind/configuration properties.

Dùng số theo cách ổn định:

~~~properties
app.limits.total-records=1000000
~~~

Không viết phân tách hàng nghìn theo dạng hiển thị locale như `1.000.000` khi một thuộc tính yêu cầu số nguyên.

### Chuỗi số 0 ở đầu

Mã bưu chính, số tài khoản, mã khách hàng hoặc mã hàng hóa như `00123` không phải đại lượng số học. Hãy dùng `String` và viết:

~~~yaml
app:
  customer:
    code: "00123"
~~~

Đừng bind thành `int` rồi kỳ vọng giữ được số 0 ở đầu.

## 4. Số thập phân: float, double và BigDecimal

Ví dụ:

~~~properties
app.price.discount-rate=0.125
app.price.base-amount=199.95
app.price.max-ratio=1.5
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.math.BigDecimal;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.price")
public record PriceProperties(
        double discountRate,
        BigDecimal baseAmount,
        float maxRatio) {
}
~~~

`float` và `double` là các kiểu dấu phẩy động nhị phân, không biểu diễn chính xác mọi số thập phân. Với số tiền, thuế hoặc phép tính đòi hỏi chính xác theo hệ thập phân, `BigDecimal` thường phù hợp hơn.

Ví dụ:

~~~java
BigDecimal tax = properties.baseAmount()
        .multiply(new BigDecimal("0.10"));
~~~

Không mặc định dùng `new BigDecimal(0.1)` nếu mục tiêu là giá trị thập phân chính xác `0.1`; số double có thể đã chứa sai số biểu diễn.

Nên viết dấu chấm trong số thập phân cấu hình:

~~~properties
app.price.discount-rate=0.125
~~~

Một chuỗi `0,125` theo cách hiển thị của một locale không nên được coi là đầu vào số hợp lệ trong mọi converter cấu hình. Nếu nguồn dữ liệu thật cần locale khác, ứng dụng phải thiết kế converter/formatter rõ ràng.

## 5. Chuyển chuỗi thành boolean

Ví dụ phổ biến:

~~~properties
app.feature.enabled=true
app.feature.audit=false
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.feature")
public record FeatureProperties(
        boolean enabled,
        boolean audit) {
}
~~~

`true` và `false` là hai cách viết nên ưu tiên. Chúng rõ nghĩa và dễ di chuyển giữa file cấu hình, biến môi trường và CI/CD.

Spring Framework có converter String-to-Boolean hỗ trợ những cách viết quen thuộc khác như `on/off`, `yes/no` hoặc `1/0` trong ngữ cảnh phù hợp. Tuy nhiên, không nên dựa vào những cách viết không cần thiết khi khai báo cấu hình vận hành. Đặc biệt, một giá trị `maybe` không phải boolean hợp lệ.

### Vì sao không tự gọi Boolean.parseBoolean?

Ví dụ:

~~~java
boolean enabled = Boolean.parseBoolean(
        environment.getProperty("app.feature.enabled"));
~~~

Phương thức Java này có cách xử lý giá trị lạ khác với converter của Spring. Trong trường hợp dữ liệu sai cú pháp, tự parse có thể che lỗi bằng `false` thay vì phát hiện cấu hình sai.

Với `@ConfigurationProperties`, Binder cố chuyển sang kiểu yêu cầu và có thể báo lỗi khi chuỗi boolean không hợp lệ. Đây thường là hành vi tốt hơn khi cần cấu hình chặt chẽ.

### boolean và Boolean không giống nhau khi thiếu cấu hình

~~~java
boolean enabled
Boolean enabled
~~~

Primitive `boolean` không thể `null`; khi property thiếu trong một object đã được tạo, nó có thể trở thành `false`. Wrapper `Boolean` có thể giữ `null` để biểu thị thiếu.

Nếu cần người vận hành **bắt buộc chọn bật hoặc tắt**, dùng:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.audit")
public record AuditProperties(
        @NotNull Boolean enabled) {
}
~~~

Khi dùng đoạn minh họa, import `org.springframework.validation.annotation.Validated` và `jakarta.validation.constraints.NotNull`, đồng thời thêm Bean Validation provider. Với trường hợp thiếu được phép mặc định tắt, có thể dùng `@DefaultValue("false") boolean`.

## 6. Chuyển chuỗi thành enum

Enum giới hạn một lựa chọn vào tập giá trị đã định nghĩa. Ví dụ:

~~~java
package com.example.configdemo.config;

public enum ProcessingMode {
    SYNC,
    ASYNC,
    MAINTENANCE
}
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.processing")
public record ProcessingProperties(
        ProcessingMode mode) {
}
~~~

Cấu hình:

~~~yaml
app:
  processing:
    mode: ASYNC
~~~

Binder biến `ASYNC` thành `ProcessingMode.ASYNC`. Service có thể dựa vào enum thay vì so sánh chuỗi thủ công:

~~~java
switch (settings.mode()) {
    case SYNC -> processNow();
    case ASYNC -> queueForLater();
    case MAINTENANCE -> pauseProcessing();
}
~~~

Ba phương thức trên đại diện cho logic nghiệp vụ do ứng dụng tự định nghĩa.

Với giá trị:

~~~properties
app.processing.mode=UNKNOWN
~~~

nếu enum không có hằng `UNKNOWN`, Binder không thể tạo một giá trị enum tương ứng và có thể báo lỗi conversion. Một chuỗi Java `"UNKNOWN"` vẫn là String hợp lệ, nhưng một enum value không tồn tại là cấu hình sai kiểu lựa chọn.

Spring Boot hỗ trợ cách chuyển đổi enum thuận tiện cho cấu hình, nhưng cách rõ ràng nhất là **viết đúng tên hằng enum** như `SYNC`, `ASYNC` và `MAINTENANCE`. Relaxed binding của **tên property** không có nghĩa mọi nhãn hiển thị đều tự trở thành enum hợp lệ.

### Enum mặc định

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.processing")
public record ProcessingProperties(
        @DefaultValue("SYNC") ProcessingMode mode) {
}
~~~

Khi không có `app.processing.mode`, Binder có thể chọn `SYNC`. Nếu người vận hành cấp `MAINTENANCE`, property được cấp sẽ thay default.

## 7. Các kiểu chuẩn Java có thể bind từ chuỗi

Ngoài số, boolean và enum, rất nhiều kiểu chuẩn thường được hỗ trợ qua converter của Spring và Spring Boot.

| Kiểu đích | Ví dụ cấu hình | Ý nghĩa |
| --- | --- | --- |
| `String` | `warehouse-service` | Tên và mã định danh |
| `URI` | `https://api.example.org/v1` | Địa chỉ tài nguyên |
| `URL` | `https://example.org` | Đối tượng URL |
| `Path` | `/var/app/data` | Đường dẫn filesystem |
| `File` | `/var/app/result.csv` | Đối tượng file |
| `InetAddress` | `127.0.0.1` | Địa chỉ IP/hostname |
| `Charset` | `UTF-8` | Bộ mã ký tự |
| `Locale` | `en_US` | Ngôn ngữ/vùng |
| `UUID` | `123e4567-e89b-12d3-a456-426614174000` | Mã định danh |
| `Duration` | `3s` | Khoảng thời gian |
| `Period` | `2w` | Chu kỳ theo lịch |
| `DataSize` | `10MB` | Dung lượng |

Một số kiểu cần converter hoặc cách diễn giải theo ngữ cảnh thích hợp; các kiểu `Duration`, `Period`, `DataSize` có hỗ trợ đặc biệt từ Spring Boot trong Configuration Properties.

### Ví dụ URI

~~~java
import java.net.URI;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(URI endpoint) {
}
~~~

Với:

~~~yaml
app:
  remote:
    endpoint: https://api.example.org
~~~

Binder có thể tạo object `URI`. Tuy nhiên, `URI` hợp lệ về cú pháp **không bảo đảm** server tồn tại, DNS hoạt động, TLS đáng tin cậy hoặc đường dẫn có quyền truy cập.

Nếu ứng dụng yêu cầu HTTPS, kiểm tra tường minh:

~~~java
if (!"https".equalsIgnoreCase(properties.endpoint().getScheme())) {
    throw new IllegalArgumentException("HTTPS endpoint is required");
}
~~~

Đây là validation nghiệp vụ, không phải một bước mặc định của việc chuyển String thành URI.

### Ví dụ Path

~~~java
import java.nio.file.Path;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path outputDir) {
}
~~~

~~~yaml
app:
  storage:
    output-dir: /var/app/output
~~~

`Path` chỉ biểu diễn vị trí đường dẫn. Chuyển sang `Path` không tự tạo thư mục, không kiểm tra quyền đọc/ghi và không chứng minh tệp tồn tại. Nếu cần, ứng dụng sử dụng `Files.exists(...)`, `Files.createDirectories(...)` hoặc kiểm tra phù hợp trước khi xử lý dữ liệu.

Đường dẫn tương đối thường phụ thuộc working directory của tiến trình Java.

## 8. Duration: chuỗi thời gian và đơn vị

Spring Boot có hỗ trợ chuyên biệt cho `java.time.Duration` với ba dạng:

1. Một số nguyên không ghi đơn vị, mặc định **mili giây** nếu không khai báo `@DurationUnit`.
2. Cú pháp ISO-8601 như `PT30S`.
3. Chuỗi số kèm hậu tố như `500ms`, `3s` hoặc `2m`.

Ví dụ:

~~~yaml
app:
  timeout:
    connect: 500ms
    read: 3s
    idle: 2m
    absolute: PT30S
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.timeout")
public record TimeoutProperties(
        Duration connect,
        Duration read,
        Duration idle,
        Duration absolute) {
}
~~~

Kết quả:

~~~text
connect  = 500 mili giây
read     = 3 giây
idle     = 2 phút
absolute = 30 giây
~~~

Bảng hậu tố:

| Hậu tố | Đơn vị |
| --- | --- |
| `ns` | Nano giây |
| `us` | Micro giây |
| `ms` | Mili giây |
| `s` | Giây |
| `m` | Phút |
| `h` | Giờ |
| `d` | Ngày |

### Bẫy số không có đơn vị

~~~properties
app.timeout.read=30
~~~

Với `Duration read`, giá trị này thường tương ứng **30 mili giây**, không phải 30 giây. Đây là lỗi phổ biến khi chuyển từ `long readTimeoutSeconds` sang `Duration readTimeout` nhưng giữ nguyên `30` trong file.

### @DurationUnit

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.timeout")
public record TimeoutProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration read) {
}
~~~

Với annotation này, `app.timeout.read=30` được diễn giải theo đơn vị giây. Dù vậy, `30s` trong YAML thường dễ hiểu và ít gây lỗi hơn vì đơn vị nằm ngay cạnh giá trị.

## 9. DataSize: dung lượng theo đơn vị

Spring Framework cung cấp `org.springframework.util.unit.DataSize`. Spring Boot hỗ trợ các giá trị như:

~~~properties
app.upload.max-size=20MB
app.upload.memory-buffer=512KB
app.upload.chunk-size=1024B
~~~

Record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        DataSize maxSize,
        DataSize memoryBuffer,
        DataSize chunkSize) {
}
~~~

Muốn làm việc với số byte, dùng:

~~~java
long bytes = properties.maxSize().toBytes();
~~~

Các đơn vị gồm `B`, `KB`, `MB`, `GB`, `TB`. Nếu property `DataSize` chỉ có số không hậu tố, đơn vị mặc định là **byte** trừ khi có `@DataSizeUnit`.

Ví dụ:

~~~properties
app.upload.max-size=10
~~~

Không nên hiểu là 10 MB; theo mặc định là 10 byte.

### @DataSizeUnit

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize maxSize) {
}
~~~

Khi đó chuỗi `10` có thể được diễn giải thành 10 megabyte. Để giảm nhầm lẫn khi vận hành, cấu hình `10MB` vẫn thường rõ ràng hơn.

`DataSize` không thay thế việc kiểm tra giới hạn nghiệp vụ. Ví dụ, max upload là 0 byte có thể không hợp lệ nhưng vẫn là một giá trị `DataSize` có kiểu đúng.

## 10. Period: khoảng thời gian theo lịch

`Duration` tính theo giây/nano giây; `Period` tính theo năm, tháng, ngày và phù hợp với quy tắc lịch.

Ví dụ:

~~~properties
app.retention.short=2w
app.retention.archive=1y3d
app.retention.monthly=P1M
~~~

Record:

~~~java
import java.time.Period;

@ConfigurationProperties(prefix = "app.retention")
public record RetentionProperties(
        Period shortPeriod,
        Period archive,
        Period monthly) {
}
~~~

Nếu dùng tên property khác với component, giữ chúng thống nhất theo relaxed binding, ví dụ `short-period` với `shortPeriod`. Trong bài tập trên có thể sửa khóa `app.retention.short` thành `app.retention.short-period` nếu record khai báo `shortPeriod`; điều quan trọng là đường dẫn phải khớp.

Các hậu tố `y` (năm), `m` (tháng), `w` (tuần), `d` (ngày) được sử dụng trong định dạng ngắn của Period. `2w` tương đương 14 ngày trong `Period`.

**Chú ý:** hậu tố `m` của `Period` là **tháng**, trong khi `m` của `Duration` là **phút**. Kiểu Java đích quyết định cách diễn giải. Đừng biến một `Period` thành số giây cố định nếu cần giữ ý nghĩa tháng/năm vì độ dài lịch thay đổi.

## 11. Tham số lồng nhau và conversion trong một object lớn

Một ứng dụng có thể có cấu hình:

~~~yaml
app:
  pipeline:
    mode: ASYNC
    enabled: true
    worker-count: 8
    output-path: /var/app/result
    retry:
      max-attempts: 4
      delay: 250ms
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.nio.file.Path;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.pipeline")
public record PipelineProperties(
        ProcessingMode mode,
        boolean enabled,
        int workerCount,
        Path outputPath,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration delay) {
    }
}
~~~

Binder liên kết và chuyển:

~~~text
ASYNC             → ProcessingMode.ASYNC
true              → boolean true
8                 → int 8
/var/app/result   → Path
4                 → int 4
250ms             → Duration.ofMillis(250)
~~~

`Retry` là một object lồng nhau. Nếu toàn bộ `app.pipeline.retry` vắng mặt, nested object có thể là null khi constructor binding. Đó là vấn đề **cấu trúc cấu hình thiếu**, không hẳn là lỗi conversion của từng field.

Nếu nhóm retry phải tồn tại, dùng `@NotNull`/`@Valid` khi validation được bật. Nếu cho phép thiếu nhưng muốn một object mặc định, Spring Boot hỗ trợ `@DefaultValue` không đối số trên nested component, kết hợp defaults hợp lệ ở các component con.

## 12. Giá trị mặc định và kiểu đích

Đối với constructor binding và record, Spring Boot hỗ trợ:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.scheduler")
public record SchedulerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int workers,
        @DefaultValue("3s") Duration interval,
        @DefaultValue("ASYNC") ProcessingMode mode) {
}
~~~

Khi một property không được tìm thấy, Binder dùng chuỗi `@DefaultValue` rồi chuyển về đúng kiểu Java.

Nếu YAML cung cấp:

~~~yaml
app:
  scheduler:
    workers: 10
~~~

kết quả có thể là:

~~~text
enabled  = true
workers  = 10
interval = PT3S
mode     = ASYNC
~~~

Các giới hạn cần nhớ:

- `@DefaultValue` chỉ áp dụng khi Binder **không tìm thấy property** tương ứng.
- Property tồn tại nhưng rỗng hoặc sai kiểu không tự được thay bằng default.
- Chuỗi trong annotation phải là hằng số, không hỗ trợ property placeholder như `${APP_INTERVAL:3s}` bên trong `@DefaultValue`.
- Một default có thể convert thành công nhưng vẫn không hợp lệ về nghiệp vụ, ví dụ số worker âm.

Đối với trường bắt buộc, không nên đặt default giả để ứng dụng luôn khởi động; hãy dùng wrapper cùng validation thích hợp.

## 13. Lỗi conversion khác validation

Xét:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @NotNull @Min(1) @Max(64) Integer size) {
}
~~~

Import:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;
~~~

Và có `spring-boot-starter-validation` hoặc provider tương ứng.

Các tình huống:

| Input | Conversion | Validation |
| --- | --- | --- |
| `size=8` | Thành `Integer 8` | Hợp lệ |
| `size=0` | Thành `Integer 0` | Vi phạm `@Min(1)` |
| `size=100` | Thành `Integer 100` | Vi phạm `@Max(64)` |
| `size=abc` | Không chuyển thành Integer thông thường | Chưa tới bước xác thực giá trị số phù hợp |
| Không có `size` | Có thể nhận null | Vi phạm `@NotNull` |

Với primitive `int`, giá trị thiếu có thể biểu hiện bằng 0, khiến không thể phân biệt “thiếu property” với “người dùng chủ động ghi 0” từ object sau bind. `Integer` + `@NotNull` giúp diễn đạt rõ hợp đồng phải cung cấp thuộc tính.

Trong ứng dụng thực tế, một lỗi bind có thể xuất hiện dưới dạng `ConfigurationPropertiesBindException`, `BindException` hoặc exception bọc ngoài tùy phiên bản. Đọc root cause để biết vấn đề nằm ở tên property, chuỗi đầu vào, kiểu đích hay constraint.

### Boolean và nghiệp vụ

`@NotNull Boolean auditEnabled` giúp yêu cầu người triển khai phải chọn `true` hoặc `false`. `false` vẫn là một lựa chọn hợp lệ; không nên gắn kiểm tra “phải true” nếu hợp đồng nghiệp vụ chỉ yêu cầu có quyết định tường minh.

### URI và validation

Một URI có scheme `http` vẫn có thể được convert thành `URI` hợp lệ. Nếu ứng dụng bắt buộc HTTPS, cần rule riêng. Không coi conversion thành công là giấy chứng nhận kết nối hoặc bảo mật.

## 14. Những lỗi thường gặp khi chuyển chuỗi

### Lỗi số vượt phạm vi

~~~properties
app.client.max-connections=99999999999999999999
~~~

Nếu dùng `int`, số quá lớn. Chọn kiểu rộng hơn khi phù hợp và kiểm tra phạm vi nghiệp vụ.

### Lỗi boolean không hợp lệ

~~~properties
app.client.enabled=maybe
~~~

Một giá trị tùy ý không phải boolean thông dụng có thể làm Binder báo lỗi. Sửa thành `true` hoặc `false`.

### Lỗi enum không tồn tại

~~~properties
app.client.mode=SILENT
~~~

Nếu enum chỉ có `ACTIVE`, `PASSIVE`, `MAINTENANCE` thì `SILENT` không chuyển thành một hằng enum tương ứng.

### Lỗi đơn vị thời gian

~~~properties
app.timeout.read=30
~~~

Nếu field là `Duration` thì mặc định thường là 30 mili giây. Để biểu diễn 30 giây, viết `30s` hoặc dùng `@DurationUnit(ChronoUnit.SECONDS)`.

### Lỗi đơn vị dung lượng

~~~properties
app.upload.max-size=10
~~~

Đối với `DataSize`, giá trị không có đơn vị mặc định là byte. Nếu muốn 10 megabyte, viết `10MB`.

### Lỗi YAML làm mất số 0 ở đầu

~~~yaml
app:
  customer:
    code: 00123
~~~

Nếu đây là mã khách hàng, hãy viết `code: "00123"` và bind vào `String`. Đừng dùng số nguyên cho dữ liệu định danh.

### Lỗi sai tên property

~~~yaml
app:
  client:
    max-connetions: 12
~~~

Khóa `max-connetions` không trùng `max-connections`. Không có conversion nào có thể sửa một lỗi chính tả tùy ý của tên property. Tên property, profile và các nguồn cấu hình phải được kiểm tra riêng.

### Lỗi property rỗng

~~~properties
app.client.max-connections=
~~~

Chuỗi rỗng không nhất thiết được xử lý giống property thiếu. Kết quả phụ thuộc kiểu đích và converter; có thể thành null hoặc gây lỗi. Nếu property bắt buộc, dùng validation và test cho trường hợp này.

## 15. Relaxed binding khác chuyển đổi giá trị

Các tên sau có thể tương ứng với cùng component Java `maxConnections` trong những nguồn phù hợp:

~~~text
app.client.max-connections
app.client.maxConnections
APP_CLIENT_MAXCONNECTIONS
~~~

Đây là **relaxed binding của tên**, không phải việc chuyển `"12"` thành `int`.

Quy tắc thông dụng đổi tên canonical property sang biến môi trường:

1. Dấu chấm `.` thành gạch dưới `_`.
2. Dấu gạch ngang `-` bị bỏ.
3. Chuyển thành chữ hoa.

Ví dụ:

~~~text
app.client.max-connections → APP_CLIENT_MAXCONNECTIONS
app.client.connect-timeout → APP_CLIENT_CONNECTTIMEOUT
~~~

Chạy:

~~~bash
export APP_CLIENT_MAXCONNECTIONS=24
java -jar config-demo.jar --app.client.enabled=false
~~~

Binder có thể nhận `24` từ biến môi trường và `false` từ CLI, sau đó chuyển thành `int` và `boolean`. Bản thân `@ConfigurationProperties` không thay đổi thứ tự ưu tiên `PropertySource`.

### Tên Map key cần chú ý

Khi bind một `Map<String,String>` từ biến môi trường, Spring Boot chuẩn hóa tên biến thành chữ thường trước khi xử lý map key. Ví dụ `MY_PROPS_VALUES_KEY=VALUE` thường cho key `key` với value `VALUE`. Đây là quy tắc tên khóa của Map, **không phải** việc lowercasing giá trị.

Nếu tên key nghiệp vụ bắt buộc phân biệt chữ hoa, cần thiết kế nguồn dữ liệu phù hợp như YAML với bracket notation hoặc dữ liệu JSON được parse riêng.

## 16. @Value và Environment cũng có cơ chế chuyển kiểu

`@Value` có thể inject một property:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class TimeoutConsumer {

    private final Duration timeout;

    public TimeoutConsumer(
            @Value("${app.client.connect-timeout:3s}") Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Spring có thể chuyển giá trị cho injection point; nhưng `@Value` không có đầy đủ cùng cơ chế metadata, cấu trúc object và relaxed binding như `@ConfigurationProperties`.

`Environment` cũng hỗ trợ truy vấn với kiểu đích:

~~~java
Integer connections = environment.getProperty(
        "app.client.max-connections", Integer.class);

Boolean enabled = environment.getProperty(
        "app.client.enabled", Boolean.class);
~~~

Nếu một property không tồn tại, API `getProperty` có thể trả null. Đối với một nhóm lớn có nested object và validation, `@ConfigurationProperties` thường rõ ràng, dễ bảo trì hơn.

Cách ít phù hợp khi dùng ở khắp nơi:

~~~java
int connections = Integer.parseInt(
        environment.getProperty("app.client.max-connections"));
~~~

Nếu property thiếu, việc tự parse có thể gây lỗi ở tầng nghiệp vụ. Tốt hơn là bind và xác thực cấu hình sớm trong bootstrap.

## 17. Custom Converter cho kiểu nghiệp vụ riêng

Đối với một kiểu Java tự định nghĩa, Spring Boot không thể đoán mọi quy tắc chuyển đổi.

Giả sử ứng dụng dùng mã khu vực ba chữ cái:

~~~java
package com.example.configdemo.config;

public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Region must have three uppercase letters");
        }
    }
}
~~~

Converter:

~~~java
package com.example.configdemo.config;

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
~~~

Đăng ký cho configuration binding:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RegionConverterConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static StringToRegionCodeConverter regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

Sau đó:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(RegionCode region) {
}
~~~

~~~properties
app.shipping.region=vnm
~~~

Binder có thể dùng converter để tạo `RegionCode("VNM")`.

Converter cho configuration properties có thể được Spring Boot gọi **rất sớm** trong vòng đời ứng dụng. Tránh phụ thuộc vào những bean chưa được khởi tạo hoặc các lời gọi mạng. Đừng tạo custom converter chỉ vì một enum hoặc `int` thông thường đã có hỗ trợ sẵn.

## 18. Kiểm thử chuyển đổi bằng ApplicationContextRunner

`ApplicationContextRunner` tạo context nhỏ và cho phép cấp thuộc tính trong test.

Ví dụ:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.configdemo.config.ClientMode;
import com.example.configdemo.config.ClientProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class BindingConfiguration {
    }

    @Test
    void bindsTypedValues() {
        runner.withPropertyValues(
                "app.client.max-connections=12",
                "app.client.enabled=true",
                "app.client.mode=ACTIVE",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    ClientProperties props =
                            context.getBean(ClientProperties.class);

                    assertThat(props.maxConnections()).isEqualTo(12);
                    assertThat(props.enabled()).isTrue();
                    assertThat(props.mode()).isEqualTo(ClientMode.ACTIVE);
                    assertThat(props.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(3));
                    assertThat(props.endpoint()).isEqualTo(
                            URI.create("https://api.example.org"));
                });
    }

    @Test
    void invalidIntegerFails() {
        runner.withPropertyValues(
                "app.client.max-connections=many",
                "app.client.enabled=true",
                "app.client.mode=ACTIVE",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void unknownEnumFails() {
        runner.withPropertyValues(
                "app.client.max-connections=12",
                "app.client.enabled=true",
                "app.client.mode=UNKNOWN",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> assertThat(context).hasFailed());
    }
}
~~~

Đoạn trên giả định dự án có `spring-boot-starter-test`, JUnit Jupiter và AssertJ. Class `ClientProperties` được đăng ký bằng `@EnableConfigurationProperties` trong test context.

Test conversion và validation nên là hai nhóm khác nhau. Ví dụ `max-connections=-5` vẫn chuyển thành `int`, nhưng sẽ bị từ chối khi thêm `@Min(1)` và Bean Validation phù hợp.

## 19. Chẩn đoán trong runtime

Có thể tạo một `ApplicationRunner` quan sát các giá trị sau khi bind:

~~~java
@Bean
ApplicationRunner inspectSettings(ClientProperties props) {
    return args -> {
        System.out.println("mode=" + props.mode());
        System.out.println("connections=" + props.maxConnections());
        System.out.println("timeoutSeconds="
                + props.connectTimeout().toSeconds());
    };
}
~~~

Đặt method trong `@Configuration` hoặc `@SpringBootApplication`, import `org.springframework.context.annotation.Bean` và `org.springframework.boot.ApplicationRunner`.

Để thử ghi đè:

~~~bash
java -jar config-demo.jar --app.client.max-connections=20
~~~

Để cố tình gây lỗi:

~~~bash
java -jar config-demo.jar --app.client.max-connections=not-a-number
~~~

Khi xem stack trace, tìm tên thuộc tính, giá trị nguồn, kiểu Java đích và nguyên nhân gốc. Không chỉ nhìn exception bọc ngoài.

Nếu ứng dụng sử dụng Spring Boot Actuator, endpoint `env` và `configprops` có thể hỗ trợ quan sát cấu hình khi được bật và bảo vệ phù hợp. Không công khai secret qua log hoặc endpoint phục vụ chẩn đoán.

## 20. Những nguyên tắc khi chọn kiểu dữ liệu

| Nhu cầu | Kiểu phù hợp thường gặp | Ví dụ |
| --- | --- | --- |
| Số lần thử | `int`/`Integer` | `retries=3` |
| Số lượng rất lớn | `long` | `records=9000000000` |
| Tiền tệ | `BigDecimal` | `amount=199.95` |
| Bật/tắt | `boolean`/`Boolean` | `enabled=true` |
| Chế độ cố định | `enum` | `mode=ASYNC` |
| Địa chỉ tài nguyên | `URI` | `endpoint=https://example.org` |
| Vị trí file | `Path` | `dir=/var/app/data` |
| Thời gian chờ | `Duration` | `timeout=3s` |
| Chu kỳ theo lịch | `Period` | `retention=2w` |
| Giới hạn dung lượng | `DataSize` | `size=10MB` |
| Mã cần giữ số 0 đầu | `String` | `code="00123"` |
| Danh sách | `List<String>` | `regions=[vn,sg]` |
| Khóa động | `Map<String,String>` | `labels.team=platform` |

Đừng chọn primitive chỉ vì ngắn gọn nếu ứng dụng phải biết property có tồn tại hay không. Đừng chọn `String` cho mọi trường nếu muốn hỗ trợ validate kiểu và logic Java dễ đọc.

## 21. Bài tập thực hành

### Bài 1 — Số nguyên

Cho `demo.worker.count=8` và `demo.worker.max-items=120000`. Tạo `WorkerProperties(int count, long maxItems)` với prefix `demo.worker`. Kết quả dự kiến: 8 và 120000.

### Bài 2 — Boolean bắt buộc

Cấu hình `demo.feature.enabled=false`. Nếu người dùng phải chọn bật/tắt tường minh, hãy dùng `@NotNull Boolean enabled` và `@Validated`; giải thích tại sao `false` là giá trị hợp lệ nhưng `null` phải bị từ chối.

### Bài 3 — Enum

Tạo enum `LogMode { SIMPLE, VERBOSE }`. Bind `demo.log.mode=VERBOSE` vào `LogMode`. Thử `demo.log.mode=QUIET` khi không có hằng `QUIET` và quan sát lỗi.

### Bài 4 — Duration

Với `Duration read`, `demo.timeout.read=2000` có nghĩa bao nhiêu giây khi không có `@DurationUnit`? **Đáp án:** 2 giây vì đơn vị mặc định là mili giây.

### Bài 5 — DataSize

Với `DataSize maxUpload`, đặt `demo.file.max-upload=10MB`. Dùng `maxUpload.toBytes()`. Giải thích tại sao `10MB` rõ nghĩa hơn con số `10` không có hậu tố.

### Bài 6 — Conversion và validation

So sánh `demo.pool.size=abc` với `demo.pool.size=-2` khi field là `int` và có `@Min(1)`. Trường hợp đầu không parse thành số, trường hợp sau parse được nhưng sai constraint.

### Bài 7 — Custom converter

Tạo `RegionCode` và converter chuẩn hóa `vnm` thành `VNM`, đăng ký bằng `@ConfigurationPropertiesBinding`. Bind `demo.region=vnm`.

### Bài 8 — Bảo toàn mã định danh

Hãy lưu mã khách hàng `00123` trong YAML và chọn kiểu Java. **Đáp án:** dùng `"00123"` trong YAML và `String` trong Java.

### Bài 9 — Ghi đè từ CLI

`application.yml` khai báo `app.client.max-connections: 10`. Chạy với `--app.client.max-connections=25`. Binder dùng giá trị 25 trong điều kiện không có nguồn ưu tiên cao hơn.

### Bài 10 — URI

Bind `https://api.example.org` vào `URI` rồi giải thích vì sao vẫn phải kiểm tra scheme, host, mạng và quyền truy cập theo yêu cầu nghiệp vụ.

## 22. Ghi nhớ

- `@ConfigurationProperties` cho phép Binder chuyển giá trị cấu hình từ các nguồn thành kiểu Java, không cần parse String ở từng service.
- Phân biệt **tên property** (relaxed binding), **chuyển giá trị** (conversion) và **quy tắc hợp lệ** (validation).
- Dùng `int`/`long` cho số nguyên, `BigDecimal` cho thập phân cần độ chính xác, `boolean` cho bật/tắt và enum cho tập lựa chọn cố định.
- Với giá trị bị thiếu, primitive có thể che giấu vấn đề bằng `0`/`false`; wrapper với `@NotNull` giúp kiểm tra sự hiện diện khi cần.
- Kiểu `URI` và `Path` thể hiện dữ liệu rõ ràng nhưng không tự xác minh mạng hoặc filesystem.
- `Duration` không hậu tố mặc định tính theo mili giây; `DataSize` không hậu tố mặc định tính theo byte. Dùng hậu tố rõ ràng hoặc `@DurationUnit`/`@DataSizeUnit`.
- `Period` phục vụ đơn vị lịch, không giống `Duration`.
- `@DefaultValue` dùng khi property thiếu và giá trị được chuyển sang kiểu đích; không tự thay property sai kiểu và không thay validation.
- Với kiểu nghiệp vụ riêng, có thể cung cấp custom converter qua `@ConfigurationPropertiesBinding`.
- Kiểm thử cả giá trị hợp lệ, property thiếu, chuỗi không thể convert, giá trị ngoài phạm vi và ràng buộc nghiệp vụ.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Properties Conversion](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
- [Spring Boot 3.3 — Converting Durations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.durations)
- [Spring Boot 3.3 — Converting Data Sizes](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.data-sizes)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Framework — ConversionService](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/ConversionService.html)
