# Cấu hình khoảng thời gian bằng Duration

## 1. Mục tiêu của bài học

Trong ứng dụng Spring Boot, rất nhiều giá trị cấu hình biểu diễn **một khoảng thời gian**: thời gian chờ kết nối, timeout của request, độ trễ thử lại, thời gian tồn tại của cache, khoảng cách giữa hai lượt kiểm tra hoặc thời gian giữ phiên.

Một cách làm cũ thường gặp là lưu những giá trị này dưới dạng số:

~~~properties
client.connect-timeout=5000
client.retry-delay=1000
~~~

Nhưng các con số **5000** và **1000** không nói rõ chúng biểu diễn mili-giây hay giây. Khi chuyển sang hệ thống khác hoặc khi đọc lại sau vài tháng, người vận hành rất dễ hiểu nhầm đơn vị.

Spring Boot có cơ chế **chuyển đổi kiểu cấu hình (configuration properties conversion)** dành riêng cho **java.time.Duration**. Nhờ đó, cấu hình có thể viết rõ ràng:

~~~properties
client.connect-timeout=5s
client.retry-delay=250ms
client.session-timeout=30m
~~~

Mã Java dùng kiểu **Duration** thay vì tự chuyển chuỗi thành số.

Sau bài này, bạn sẽ có thể:

- Hiểu **Duration** biểu diễn gì và khác với **Period**, **LocalDateTime**.
- Viết giá trị thời gian ở ba định dạng Spring Boot hỗ trợ.
- Phân biệt các hậu tố **ns**, **us**, **ms**, **s**, **m**, **h**, **d**.
- Biết giá trị số **không kèm đơn vị mặc định là mili-giây**, trừ khi khai báo **@DurationUnit**.
- Khai báo **@ConfigurationProperties** dùng Duration bằng Java record hoặc JavaBean.
- Kết hợp **@DefaultValue**, **@DurationUnit**, validation và nguồn cấu hình ngoài.
- Đọc thời gian từ YAML, properties, biến môi trường và tham số khởi động.
- Tránh lỗi chuyển kiểu, nhầm đơn vị và giá trị không phù hợp.
- Viết test xác nhận cấu hình được bind đúng.

Ví dụ lấy **Spring Boot 3.3.x**, **Java 21** làm bối cảnh.

## 2. Duration trong Java biểu diễn điều gì?

**java.time.Duration** là kiểu của Java Time API dùng để biểu diễn **một lượng thời gian** dựa trên giây và nano-giây, thay vì một thời điểm cụ thể trên lịch.

Một vài cách tạo Duration trong Java:

~~~java
import java.time.Duration;

Duration connectTimeout = Duration.ofSeconds(5);
Duration retryDelay = Duration.ofMillis(250);
Duration sessionTimeout = Duration.ofMinutes(30);
Duration backoff = Duration.ofHours(2);
Duration oneDay = Duration.ofDays(1);
~~~

Các phương thức thường dùng:

~~~java
Duration timeout = Duration.ofSeconds(5);

long milliseconds = timeout.toMillis();   // 5000
long seconds = timeout.getSeconds();       // 5
boolean zero = timeout.isZero();           // false
boolean negative = timeout.isNegative();   // false

Duration doubled = timeout.multipliedBy(2);
Duration total = timeout.plusMillis(500);
~~~

**Duration** không tự kết nối mạng, không đặt lịch và không làm ứng dụng ngủ. Nó là **giá trị mô tả một khoảng thời gian**. Component sử dụng — ví dụ HTTP client hoặc scheduler — sẽ quyết định cách áp dụng nó.

Ví dụ: nếu một cấu hình tên **retry-delay** là **500ms**, logic thử lại có thể dùng giá trị đó để quyết định chờ bao lâu. Nếu là **connect-timeout**, HTTP client có thể dùng cùng kiểu Duration nhưng với ý nghĩa hoàn toàn khác.

### 2.1. Duration khác thời điểm và ngày theo lịch

| Kiểu Java | Mục đích |
| --- | --- |
| **Duration** | Một khoảng thời gian tính bằng đơn vị thời gian, ví dụ 5 giây hoặc 2 giờ |
| **Period** | Một khoảng theo lịch, ví dụ 2 tháng, 3 ngày |
| **Instant** | Một thời điểm trên trục thời gian |
| **LocalDateTime** | Ngày giờ địa phương, không gắn timezone |
| **ZonedDateTime** | Ngày giờ với vùng thời gian |

**Duration.ofDays(1)** là khoảng thời gian **24 giờ**. Nếu yêu cầu nghiệp vụ nói “ngày mai cùng giờ địa phương”, điều đó có thể khác 24 giờ trong môi trường có thay đổi giờ mùa hè. Khi thao tác theo lịch, cần cân nhắc **Period**, **LocalDate**, **ZonedDateTime** hoặc các API lịch tương ứng.

Đối với timeout, retry delay và thời gian chờ kỹ thuật, **Duration** thường là kiểu thích hợp.

## 3. Ba cách Spring Boot nhận giá trị Duration

Khi bind một property tới **Duration** qua **@ConfigurationProperties**, Spring Boot hỗ trợ ba cách diễn đạt quan trọng.

### 3.1. Số nguyên thông thường

~~~properties
demo.client.connect-timeout=5000
~~~

Nếu không có cấu hình đơn vị khác, số **5000** được hiểu là **5000 mili-giây**, tương đương **5 giây**.

Đây là cú pháp ngắn nhưng dễ nhầm. Chỉ nhìn con số không biết tác giả nghĩ đến đơn vị gì.

### 3.2. Chuẩn ISO-8601

~~~properties
demo.client.connect-timeout=PT5S
demo.client.session-timeout=PT30M
demo.client.long-timeout=PT2H
~~~

Chuỗi ISO-8601 dùng cú pháp mà **java.time.Duration** hỗ trợ:

- **PT5S**: 5 giây.
- **PT30M**: 30 phút.
- **PT2H**: 2 giờ.
- **PT1H30M**: 1 giờ 30 phút.
- **PT0.5S**: nửa giây.

Cách này có ích khi hệ thống hoặc công cụ cần một dạng biểu diễn tiêu chuẩn, có thể truyền giữa nhiều nền tảng.

### 3.3. Giá trị kèm hậu tố đơn vị, dễ đọc

~~~properties
demo.client.connect-timeout=5s
demo.client.retry-delay=250ms
demo.client.session-timeout=30m
demo.client.maintenance-delay=2h
~~~

Đây là dạng thuận tiện nhất cho phần lớn ứng dụng Spring Boot: người đọc nhìn thấy ngay **5s** là năm giây, **250ms** là 250 mili-giây.

**Không cần tự parse chuỗi bằng Duration.parse(...)** trong một class cấu hình dùng **@ConfigurationProperties**. Spring Boot Binder có cơ chế chuyển đổi riêng để hiểu các dạng trên, kể cả **5s** là dạng dễ đọc không phải cú pháp ISO-8601 của Java.

## 4. Bảng đơn vị được Spring Boot hỗ trợ

Theo tài liệu Spring Boot 3.3, các hậu tố trong dạng đơn giản bao gồm:

| Hậu tố | Đơn vị | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| **ns** | Nanosecond | **100ns** | 100 nano-giây |
| **us** | Microsecond | **50us** | 50 micro-giây |
| **ms** | Millisecond | **500ms** | Nửa giây |
| **s** | Second | **10s** | 10 giây |
| **m** | Minute | **15m** | 15 phút |
| **h** | Hour | **2h** | 2 giờ |
| **d** | Day | **3d** | 3 ngày, tương đương 72 giờ |

Những điểm cần nhớ:

- **ms** là mili-giây, **m** là phút. Hai hậu tố này không thể dùng thay nhau.
- **us** là micro-giây, **ns** là nano-giây.
- **h** biểu diễn giờ và **d** biểu diễn lượng thời gian theo ngày 24 giờ.
- Hậu tố nên viết nguyên dạng như tài liệu, đặc biệt khi dữ liệu đi qua nhiều hệ thống.
- Không tự suy rằng một hậu tố **w** (tuần), **mo** (tháng) hay **y** (năm) là hợp lệ cho Duration. Đối với đơn vị lịch như tháng và năm, cần xem **Period**.
- Không nên tự ghép nhiều cặp đơn vị trong một chuỗi dạng đơn giản như **1h30m** rồi mặc định chắc chắn được hỗ trợ. Dùng **PT1H30M** trong ISO-8601, hoặc chuyển thành **90m** khi phù hợp.

### 4.1. Các chuỗi tương đương về thời lượng

| Dạng số | Dạng ISO | Dạng có hậu tố | Duration |
| --- | --- | --- | --- |
| **500** | **PT0.5S** | **500ms** | Nửa giây |
| **1000** | **PT1S** | **1s** | Một giây |
| **5000** | **PT5S** | **5s** | Năm giây |
| **60000** | **PT1M** | **1m** | Một phút |
| **3600000** | **PT1H** | **1h** | Một giờ |

**Bảng giả định đơn vị mặc định là mili-giây**. Nếu field/constructor parameter được đặt **@DurationUnit(ChronoUnit.SECONDS)**, các số thuần phải được hiểu theo đơn vị mới.

## 5. Mặc định của số không hậu tố: mili-giây

Đây là quy tắc quan trọng nhất khi chuyển hệ thống cũ sang Duration.

Giả sử record:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientTimeoutProperties(
        Duration connectTimeout) {
}
~~~

Nếu file cấu hình ghi:

~~~properties
demo.client.connect-timeout=30
~~~

thì **connectTimeout** được hiểu là **30 mili-giây**, không phải 30 giây.

Nếu mục tiêu thực sự là 30 giây, có thể sửa rõ:

~~~properties
demo.client.connect-timeout=30s
~~~

Hoặc:

~~~properties
demo.client.connect-timeout=PT30S
~~~

Một lỗi triển khai điển hình:

~~~text
Ý định:     timeout 30 giây
Cấu hình:   30
Kết quả:    30 mili-giây
Ảnh hưởng:  request dễ timeout bất ngờ
~~~

**Khuyến nghị trong cấu hình mới:** luôn viết hậu tố đơn vị ngay trong file/biến môi trường, kể cả khi mặc định là mili-giây. Ví dụ **500ms** rõ hơn **500**.

## 6. Thay đơn vị mặc định bằng @DurationUnit

Đôi khi dự án cũ đã dùng số thuần với ý nghĩa là **giây**:

~~~properties
legacy.session-timeout=30
~~~

Nếu chuyển property từ **long** sang **Duration** mà không thông báo thay đổi cú pháp, Spring Boot sẽ hiểu **30** là 30 mili-giây. Để giữ ý nghĩa cũ, có thể dùng **@DurationUnit**.

Annotation:

~~~java
import org.springframework.boot.convert.DurationUnit;
import java.time.temporal.ChronoUnit;
~~~

Ví dụ một JavaBean có field và getter/setter:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "legacy")
public class LegacySessionProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration sessionTimeout = Duration.ofSeconds(30);

    public Duration getSessionTimeout() {
        return sessionTimeout;
    }

    public void setSessionTimeout(Duration sessionTimeout) {
        this.sessionTimeout = sessionTimeout;
    }
}
~~~

Với class trên:

~~~properties
legacy.session-timeout=30
~~~

mang nghĩa **30 giây**, vì field đã được đặt **@DurationUnit(ChronoUnit.SECONDS)**.

Nhưng:

~~~properties
legacy.session-timeout=500ms
~~~

vẫn là **500 mili-giây** vì chuỗi đã có hậu tố đơn vị rõ ràng. **@DurationUnit** thay **đơn vị mặc định khi không nêu**, chứ không xóa ý nghĩa của hậu tố được khai báo trực tiếp.

### 6.1. Đặt @DurationUnit ở constructor parameter

Spring Boot 3.3 cũng hỗ trợ constructor binding. Ví dụ dùng class immutable:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.session")
public class SessionProperties {

    private final Duration sessionTimeout;
    private final Duration readTimeout;

    public SessionProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("30s") Duration sessionTimeout,
            @DefaultValue("1000ms") Duration readTimeout) {
        this.sessionTimeout = sessionTimeout;
        this.readTimeout = readTimeout;
    }

    public Duration getSessionTimeout() {
        return sessionTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }
}
~~~

Giá trị:

~~~properties
demo.session.session-timeout=60
demo.session.read-timeout=500
~~~

sẽ được hiểu thành:

~~~text
sessionTimeout -> 60 giây
readTimeout    -> 500 mili-giây
~~~

**@DurationUnit** được gắn cho **sessionTimeout**, không phải cho toàn bộ class hay mọi field Duration.

### 6.2. Khi nào nên dùng @DurationUnit?

Nên cân nhắc **@DurationUnit** khi:

- Đang di chuyển từ một property số cũ có đơn vị ngầm định khác mili-giây.
- Cần giữ tương thích với công cụ triển khai vốn luôn cấp giá trị thuần theo giây/phút.
- Một API cấu hình công khai có hợp đồng rõ rằng số không hậu tố sẽ được hiểu theo đơn vị cụ thể.

Với cấu hình mới, cách rõ nhất vẫn thường là đặt hậu tố như **5s**, **250ms**, **2m** ngay trong file.

## 7. Khai báo cấu hình Duration trong application.yml

Một ứng dụng xử lý thanh toán có thể cần:

- Timeout kết nối.
- Timeout của request.
- Độ trễ trước lần thử tiếp theo.
- Timeout phiên làm việc.

Cấu hình YAML:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      initial-delay: 250ms
      max-delay: 5s

  session:
    idle-timeout: 30m
~~~

Tên property phẳng tương ứng:

~~~text
demo.client.connect-timeout
demo.client.request-timeout
demo.client.retry.initial-delay
demo.client.retry.max-delay
demo.session.idle-timeout
~~~

Giá trị **2s** hay **30m** được giữ dưới dạng text/scalar trong Config Data và được chuyển sang **Duration** khi bind vào type tương ứng.

Để cấu hình rõ ràng khi có giá trị phức tạp hoặc khoảng trắng, có thể dùng dấu nháy trong YAML:

~~~yaml
demo:
  client:
    request-timeout: "PT10S"
    connect-timeout: "2s"
~~~

Với Duration simple style thông thường, dấu nháy không bắt buộc, nhưng dùng nhất quán có thể giúp tránh một số cách diễn giải scalar không mong muốn.

### 7.1. Phiên bản application.properties

~~~properties
demo.client.connect-timeout=2s
demo.client.request-timeout=10s
demo.client.retry.initial-delay=250ms
demo.client.retry.max-delay=5s
demo.session.idle-timeout=30m
~~~

YAML và properties là hai cách biểu diễn cùng nhóm key. Đừng khai báo hai file cùng tên với các giá trị mâu thuẫn mà không biết quy tắc ưu tiên Config Data của Spring Boot.

## 8. Java record với Duration và nested configuration

Giả sử app dùng Java 21, Spring Boot 3.3.x, dependency **spring-boot-starter-web**.

Một record configuration properties:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("10s") Duration requestTimeout,
        Retry retry) {

    public record Retry(
            @DefaultValue("250ms") Duration initialDelay,
            @DefaultValue("5s") Duration maxDelay) {
    }
}
~~~

Khi có YAML như mục trước, Spring Boot bind:

~~~text
ClientProperties
  connectTimeout = PT2S
  requestTimeout = PT10S
  retry
    initialDelay = PT0.25S
    maxDelay     = PT5S
~~~

**@DefaultValue** có tác dụng khi property tương ứng không được cung cấp cho constructor binding. Nó không có nghĩa là mọi cấu hình thiếu đều hợp lệ; với nested object, việc khởi tạo object con còn tùy có dữ liệu hay khai báo default nested binding phù hợp.

Nếu **retry** là bắt buộc, có thể dùng validation hoặc yêu cầu đầy đủ các property. Nếu muốn record lồng nhau luôn được tạo ngay cả khi không có property ở nhánh đó, Spring Boot hỗ trợ chỉ định default rỗng cho nested constructor parameter để yêu cầu tạo nested object, kết hợp các default cho field bên trong.

### 8.1. Đăng ký @ConfigurationPropertiesScan

~~~java
package com.example.duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DurationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DurationApplication.class, args);
    }
}
~~~

Với class app ở package **com.example.duration**, record **ClientProperties** trong cùng package được scanning.

Một cách thay thế:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DurationApplication {
    public static void main(String[] args) {
        SpringApplication.run(DurationApplication.class, args);
    }
}
~~~

Đoạn thay thế cần import **org.springframework.boot.context.properties.EnableConfigurationProperties**. Hai cách đăng ký **scan** và **enable** không bắt buộc dùng chung.

Với constructor binding/record, không nên chỉ thêm **@Component** vào record rồi mong Spring Boot tự liên kết những constructor parameter như property.

## 9. Ví dụ đọc cấu hình đã chuyển kiểu

Để quan sát kết quả, có thể dùng một REST controller đơn giản:

~~~java
package com.example.duration;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DurationController {

    private final ClientProperties properties;

    public DurationController(ClientProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/duration-demo")
    public Map<String, Object> read() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("connectTimeoutMs",
                properties.connectTimeout().toMillis());
        result.put("requestTimeoutSeconds",
                properties.requestTimeout().getSeconds());
        result.put("retryInitialDelayMs",
                properties.retry().initialDelay().toMillis());
        result.put("retryMaxDelayMs",
                properties.retry().maxDelay().toMillis());
        return result;
    }
}
~~~

Với cấu hình:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      initial-delay: 250ms
      max-delay: 5s
~~~

gọi:

~~~bash
curl http://localhost:8080/duration-demo
~~~

cho kết quả minh họa:

~~~json
{
  "connectTimeoutMs": 2000,
  "requestTimeoutSeconds": 10,
  "retryInitialDelayMs": 250,
  "retryMaxDelayMs": 5000
}
~~~

Controller chỉ thể hiện việc convert và đọc Duration. Nó không thực hiện network request hay scheduler thật, nên các giá trị không gây phụ thuộc vào hạ tầng ngoài.

**Trong ứng dụng production, không nên mở endpoint trả về cấu hình nhạy cảm**. Ví dụ ở đây chỉ chứa timeout và delay giả.

## 10. Có thể cấp Duration bằng biến môi trường

Cấu hình ngoài JAR là một ưu điểm chính của Spring Boot. Bạn có thể thay giá trị timeout của cùng một artifact khi deploy.

Tên canonical:

~~~text
demo.client.connect-timeout
demo.client.request-timeout
demo.client.retry.initial-delay
demo.client.retry.max-delay
~~~

Biến môi trường tương ứng theo relaxed binding:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT
DEMO_CLIENT_REQUESTTIMEOUT
DEMO_CLIENT_RETRY_INITIALDELAY
DEMO_CLIENT_RETRY_MAXDELAY
~~~

Quy tắc chuyển từ canonical sang biến môi trường:

1. Thay dấu chấm **.** bằng gạch dưới **_**.
2. Bỏ dấu gạch ngang **-**.
3. Viết hoa tên.

Chính giá trị sau dấu **=** vẫn dùng cú pháp Duration:

~~~bash
DEMO_CLIENT_CONNECTTIMEOUT=5s \
DEMO_CLIENT_REQUESTTIMEOUT=15s \
DEMO_CLIENT_RETRY_INITIALDELAY=500ms \
DEMO_CLIENT_RETRY_MAXDELAY=8s \
java -jar app.jar
~~~

Với PowerShell:

~~~powershell
$env:DEMO_CLIENT_CONNECTTIMEOUT = "5s"
$env:DEMO_CLIENT_REQUESTTIMEOUT = "15s"
$env:DEMO_CLIENT_RETRY_INITIALDELAY = "500ms"
$env:DEMO_CLIENT_RETRY_MAXDELAY = "8s"
java -jar app.jar
~~~

Điều quan trọng là **đơn vị nằm trong giá trị**, không nằm trong tên biến môi trường. Tên **DEMO_CLIENT_CONNECTTIMEOUT** được dùng cho cả **5s**, **5000ms** hoặc **PT5S**.

### 10.1. Tham số dòng lệnh

~~~bash
java -jar app.jar \
  --demo.client.connect-timeout=5s \
  --demo.client.request-timeout=15s
~~~

Lệnh này dùng cùng key canonical như Config Data. Khi command-line properties được bật theo cấu hình Spring Boot thông thường, chúng có độ ưu tiên cao đối với key trùng tên.

### 10.2. Java system properties

~~~bash
java \
  -Ddemo.client.connect-timeout=5s \
  -Ddemo.client.request-timeout=15s \
  -jar app.jar
~~~

Nhớ đặt các tham số **-D** trước **-jar**.

**Không cần build lại JAR** chỉ để điều chỉnh Duration nếu ứng dụng đọc cấu hình qua hệ thống externalized configuration.

## 11. Thứ tự ưu tiên nguồn có ảnh hưởng đến Duration như thế nào?

Giả sử:

**application.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 2s
~~~

**application-prod.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 4s
~~~

Biến môi trường:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=6s
~~~

Tham số dòng lệnh:

~~~text
--demo.client.connect-timeout=8s
~~~

Nếu profile **prod** hoạt động và mọi nguồn này được cung cấp cùng lúc trong điều kiện Spring Boot thông thường, các nguồn có độ ưu tiên cao hơn ghi đè những giá trị thấp hơn. Tham số dòng lệnh thường thắng đối với key này, nên **ClientProperties.connectTimeout()** nhận 8 giây.

**Binder không cộng các khoảng thời gian lại với nhau**. Nó chọn giá trị property theo cơ chế ưu tiên và chuyển **giá trị cuối** sang Duration.

Do đó:

~~~text
application.yml          2s
application-prod.yml     4s
environment variable     6s
command line             8s
--------------------------------
Kết quả ví dụ          Duration.ofSeconds(8)
~~~

Nếu bỏ tham số dòng lệnh nhưng giữ biến môi trường, có thể nhận 6 giây. Nếu bỏ cả env và argument, profile-specific Config Data có thể quyết định giá trị.

### 11.1. Một đơn vị rõ ràng giúp override an toàn

Không nên viết:

~~~yaml
demo:
  client:
    connect-timeout: 2000
~~~

rồi cung cấp:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=4
~~~

với kỳ vọng 4 giây. Khi không có **@DurationUnit** đặc biệt, **4** chỉ là **4 mili-giây**.

Nên cấp:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=4s
~~~

## 12. Dùng @DurationUnit trong record và constructor binding

Đối với dự án dùng record Java và cần **thay đơn vị mặc định** cho một Duration field, có thể minh họa bằng record component:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.timeout")
public record TimeoutProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("30s") Duration session,
        @DefaultValue("500ms") Duration read) {
}
~~~

Nếu Spring Boot bind:

~~~properties
demo.timeout.session=45
demo.timeout.read=600
~~~

thì:

~~~text
session = 45 giây
read    = 600 mili-giây
~~~

Còn nếu cấu hình:

~~~properties
demo.timeout.session=500ms
~~~

thì Duration vẫn là 500 mili-giây, vì hậu tố được nêu rõ.

**@DurationUnit không phải annotation để giới hạn độ lớn của thời gian**. Nó chỉ ảnh hưởng cách diễn giải những giá trị không có đơn vị. Nếu cần kiểm tra timeout phải lớn hơn 0, hãy sử dụng validation hoặc logic bảo vệ phù hợp.

## 13. Duration trong Java không nên được xử lý như một String tùy ý

Ví dụ một cách viết dễ gây rủi ro:

~~~java
String rawTimeout = environment.getProperty(
        "demo.client.connect-timeout");
long timeout = Long.parseLong(rawTimeout);
~~~

Đoạn này sẽ lỗi nếu cấu hình là **5s**, và ngay cả khi dùng số **5000**, code cũng phải tự quyết định đơn vị.

Thay bằng model có kiểu:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(Duration connectTimeout) {
}
~~~

Sau khi bind:

~~~java
Duration timeout = properties.connectTimeout();
~~~

Cách này tạo một hợp đồng thống nhất cho YAML, properties, env và CLI.

Nếu bạn chỉ cần tra cứu một key đơn lẻ mà không muốn tạo một configuration properties bean, **Environment** có overload typed lookup:

~~~java
Duration timeout = environment.getProperty(
        "demo.client.connect-timeout",
        Duration.class);
~~~

Việc chuyển kiểu của Environment phụ thuộc ConversionService hiện hành, còn khả năng chuyển đổi Duration được Spring Boot tài liệu hóa rõ cho **@ConfigurationProperties Binder**. Đối với các giá trị Duration phức tạp hoặc muốn có validation và defaults nhất quán, **@ConfigurationProperties** là cách ưu tiên.

## 14. Cấu hình thời gian trong JavaBean có setter

Không phải mọi ứng dụng đều sử dụng record. Một class mutable vẫn có thể bind Duration:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.polling")
public class PollingProperties {

    private Duration interval = Duration.ofSeconds(10);
    private Duration initialDelay = Duration.ofSeconds(2);

    public Duration getInterval() {
        return interval;
    }

    public void setInterval(Duration interval) {
        this.interval = interval;
    }

    public Duration getInitialDelay() {
        return initialDelay;
    }

    public void setInitialDelay(Duration initialDelay) {
        this.initialDelay = initialDelay;
    }
}
~~~

Cấu hình:

~~~yaml
demo:
  polling:
    interval: 15s
    initial-delay: 3s
~~~

Nếu không cung cấp giá trị nào cho các property này, JavaBean đang có các field được khởi tạo bằng **Duration.ofSeconds(10)** và **Duration.ofSeconds(2)**.

So sánh:

- **JavaBean setters**: có thể khởi tạo mặc định trực tiếp trên field.
- **Record/constructor binding**: có thể dùng **@DefaultValue** trên component hoặc parameter.
- **Cấu hình YAML**: cũng có thể lưu các giá trị mặc định chung ngay trong Config Data.

Không cần kết hợp tất cả cách đặt default cho cùng một field. Nên chọn một chiến lược rõ ràng.

## 15. @DefaultValue cho Duration trong constructor binding

Ví dụ:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.job")
public record JobProperties(
        @DefaultValue("5s") Duration startupDelay,
        @DefaultValue("1m") Duration runInterval) {
}
~~~

Nếu không có property:

~~~text
demo.job.startup-delay
demo.job.run-interval
~~~

thì record có thể được tạo với:

~~~text
startupDelay = 5 giây
runInterval  = 1 phút
~~~

Nên ghi **hậu tố đơn vị trong @DefaultValue**, đặc biệt khi người đọc không biết quy tắc bare number.

Các annotation @DefaultValue có thể kết hợp với @DurationUnit khi cần hỗ trợ số không hậu tố từ nguồn cấu hình. Tuy nhiên, với default được ghi rõ **5s** hoặc **1m**, ý nghĩa không phụ thuộc đơn vị ngầm định.

### 15.1. Giá trị thiếu và null

Nếu một Duration record component không được cung cấp và không có default, component đó có thể nhận **null** theo điều kiện binding. Nếu code sau đó gọi **timeout.toMillis()**, NullPointerException có thể xuất hiện.

Dùng validation với **@NotNull**, một default hợp lý hoặc fail-fast tùy hợp đồng ứng dụng.

## 16. Validation cho khoảng thời gian

Một Duration được parse thành công **không có nghĩa** nó hợp lệ cho mọi mục đích.

Ví dụ:

~~~yaml
demo:
  client:
    connect-timeout: -5s
    request-timeout: 0s
~~~

Về ý nghĩa thời lượng, Duration có thể biểu diễn số âm và zero. Nhưng HTTP client có thể yêu cầu timeout dương hoặc có cách diễn giải riêng cho 0; một giá trị quá lớn cũng có thể không phù hợp.

### 16.1. @NotNull cho field bắt buộc

Nếu dự án có dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

có thể dùng:

~~~java
package com.example.duration;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public record ValidatedTimeoutProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {
}
~~~

Khi property bắt buộc vắng mặt, validation có thể báo lỗi trong quá trình khởi tạo context.

**Đây là type minh họa thay thế** cho ClientProperties; không cần đăng ký cả hai cùng prefix trong một project bài tập.

### 16.2. Kiểm tra dương bằng logic riêng

Bean Validation **@Min** và **@Positive** thường dành cho các kiểu số, không nên mặc nhiên dùng chúng trực tiếp cho **Duration** khi chưa có validator hỗ trợ type đó.

Một cách đơn giản là kiểm tra lúc tạo bean sử dụng cấu hình:

~~~java
public static Duration requirePositive(
        Duration value,
        String propertyName) {

    if (value == null || value.isZero() || value.isNegative()) {
        throw new IllegalArgumentException(
                propertyName + " must be positive");
    }
    return value;
}
~~~

Sử dụng:

~~~java
Duration connectTimeout = requirePositive(
        properties.connectTimeout(),
        "demo.client.connect-timeout");
~~~

Trong dự án lớn, có thể tạo **custom Bean Validation constraint** cho Duration để giữ ràng buộc ngay tại configuration model.

### 16.3. Zero có thể có ý nghĩa riêng

Một số framework hoặc client hiểu **0** là “không giới hạn” hoặc “vô hiệu hóa timeout”, nhưng một số API lại hiểu zero là không chờ. Không tự giả định chung cho mọi thư viện.

Khi thiết kế property như **connect-timeout**, cần ghi rõ:

- Đơn vị và định dạng được hỗ trợ.
- Có chấp nhận **0s** hay không.
- Giá trị âm có bị cấm không.
- Giới hạn tối đa phù hợp.
- Có cho phép vô hiệu hóa timeout không, và cú pháp nào thực hiện việc đó.

## 17. Sử dụng Duration trong logic nghiệp vụ

Giả sử một service tính thời gian delay cho retry:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class RetryDelayService {

    private final ClientProperties properties;

    public RetryDelayService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration initialDelay() {
        return properties.retry().initialDelay();
    }

    public Duration nextDelay(int attempt) {
        Duration initial = properties.retry().initialDelay();
        Duration maximum = properties.retry().maxDelay();

        if (attempt <= 1) {
            return initial;
        }

        long multiplier = Math.min(attempt, 10);
        Duration computed = initial.multipliedBy(multiplier);

        return computed.compareTo(maximum) > 0
                ? maximum
                : computed;
    }
}
~~~

Service này trả về **Duration**, không cần ép dữ liệu thành mili-giây ngay từ đầu.

Nếu sau đó thư viện scheduling yêu cầu số mili-giây, có thể chuyển tại **ranh giới tích hợp**:

~~~java
long delayMillis = retryDelayService.nextDelay(3).toMillis();
~~~

Không chuyển đổi qua lại giữa String, long và Duration ở mọi lớp của ứng dụng.

**Cẩn trọng:** các phép nhân hoặc chuyển đổi số có thể overflow đối với Duration cực lớn. Trong config nghiệp vụ thực, validation nên giới hạn giá trị. Nếu cần chính xác đến nano-giây, đừng chuyển sang mili-giây quá sớm vì có thể làm mất phần lẻ.

## 18. Duration và profile-specific configuration

Cùng một field Duration có thể nhận giá trị khác theo profile.

**application.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
~~~

**application-dev.yml**:

~~~yaml
demo:
  client:
    request-timeout: 30s
~~~

**application-prod.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 5s
    request-timeout: 8s
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

hoặc:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot nạp các file Config Data theo profile và bind Duration từ giá trị có hiệu lực.

Không cần khai báo **hai lớp ClientProperties khác nhau** cho dev và prod. Một model Java có thể được dùng xuyên suốt môi trường; chỉ dữ liệu cấu hình thay đổi.

Nếu có system property, biến môi trường hoặc command-line argument ghi đè, chúng vẫn tham gia vào thứ tự ưu tiên chung.

## 19. Dùng Duration trong Docker Compose

Ví dụ một container chạy ứng dụng:

~~~yaml
services:
  api:
    image: example/duration-demo:1.0.0
    ports:
      - "8080:8080"
    environment:
      DEMO_CLIENT_CONNECTTIMEOUT: "5s"
      DEMO_CLIENT_REQUESTTIMEOUT: "15s"
      DEMO_CLIENT_RETRY_INITIALDELAY: "500ms"
      DEMO_CLIENT_RETRY_MAXDELAY: "8s"
~~~

Phần **environment** chứa giá trị chuỗi. Docker Compose đưa chúng vào môi trường container; chính Spring Boot Binder mới đổi chuỗi thành **Duration**.

Nên đặt các giá trị trong dấu nháy để biểu thị rõ là chuỗi, đặc biệt khi cấu hình chứa **0**, số hoặc những giá trị có thể được YAML diễn giải theo kiểu dữ liệu khác.

Nếu file **.env** của Compose chỉ dùng làm nguồn interpolation, cần chắc chắn các biến được truyền qua cấu hình Compose vào container. Chỉ khai báo một giá trị trong **.env** không bảo đảm nó tự xuất hiện trong môi trường tiến trình Java.

## 20. Dùng Duration trong Kubernetes

Một đoạn **containers** thuộc Pod template:

~~~yaml
containers:
  - name: app
    image: example/duration-demo:1.0.0
    env:
      - name: DEMO_CLIENT_CONNECTTIMEOUT
        value: "5s"
      - name: DEMO_CLIENT_REQUESTTIMEOUT
        value: "15s"
      - name: DEMO_CLIENT_RETRY_INITIALDELAY
        value: "500ms"
~~~

Đây là đoạn YAML minh họa, không phải Deployment manifest đầy đủ.

Kubernetes không cần hiểu nghĩa **5s** hay **500ms** ở các biến môi trường này. Nó truyền String vào container; Spring Boot xử lý ở bước bind configuration.

Nếu bạn mount ConfigMap thành file **application.yml**, các giá trị Duration cũng có thể được nạp bằng cơ chế Config Data; vẫn cần xác định đúng vị trí file, đường dẫn và thứ tự ưu tiên.

**Không đặt secret thật vào cấu hình minh họa hay các endpoint debug**. Duration bản thân không chứa secret, nhưng hệ thống cấu hình cũng có thể chứa các key nhạy cảm khác.

## 21. Duration và Period không giống nhau

Spring Boot hỗ trợ cả **Duration** và **Period**, nhưng chúng giải quyết những bài toán khác nhau.

Ví dụ:

~~~text
Duration: 5s, 2h, 1d
Period:   3d, 2w, 1m, 1y
~~~

Trong cách viết simple style của **Duration**:

~~~text
m = phút
~~~

Trong cách viết simple style của **Period**:

~~~text
m = tháng
~~~

Điều này cực kỳ quan trọng khi đổi Java type. **5m** là 5 phút nếu bind vào Duration, nhưng có thể biểu diễn 5 tháng nếu bind vào Period theo quy tắc tương ứng.

Dùng Duration cho:

- Connect timeout.
- Request timeout.
- Retry delay.
- Cache TTL tính theo thời lượng.
- Polling interval.
- Thời gian backoff.

Cân nhắc Period hoặc API lịch cho:

- Thời hạn 3 tháng tính theo lịch.
- Gia hạn 1 năm.
- Cộng thêm ngày/tháng/năm trên LocalDate.
- Quy tắc ngày kết thúc dựa vào lịch địa phương.

Đừng dùng **Duration.ofDays(30)** thay thế mặc định cho khái niệm “một tháng”.

## 22. Nâng cấp property cũ từ long sang Duration

Giả sử ứng dụng cũ có:

~~~java
private long timeoutSeconds;
~~~

và cấu hình:

~~~properties
legacy.timeout-seconds=30
~~~

Có hai chiến lược migration:

### 22.1. Giữ key cũ và gắn @DurationUnit

Một class:

~~~java
@ConfigurationProperties(prefix = "legacy")
public class LegacyProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeoutSeconds;

    public Duration getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public void setTimeoutSeconds(Duration timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }
}
~~~

Lúc này **30** vẫn được hiểu là 30 giây, hỗ trợ chuyển sang kiểu Duration mà không phá hợp đồng đơn vị ngầm định của các file triển khai cũ.

**Lưu ý:** ví dụ class trên cần import **java.time.Duration**, **java.time.temporal.ChronoUnit**, **org.springframework.boot.context.properties.ConfigurationProperties** và **org.springframework.boot.convert.DurationUnit** như các ví dụ trước.

### 22.2. Đổi sang key mới và bắt buộc ghi rõ đơn vị

Ví dụ:

~~~properties
legacy.timeout=30s
~~~

Đây là cơ hội thiết kế lại API cấu hình. Tuy nhiên, việc đổi từ **timeout-seconds** sang **timeout** có thể làm hỏng các environment hoặc manifest còn dùng key cũ. Nếu đã có người sử dụng, cần kế hoạch chuyển đổi tên key, document và test.

**Relaxed binding không tự hiểu hai property có ý nghĩa khác nhau như timeout-seconds và timeout là alias của nhau**.

## 23. Kiểm thử chuyển đổi Duration

Giả sử Spring Boot app đã đăng ký:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        Duration connectTimeout,
        Duration requestTimeout,
        Retry retry) {

    public record Retry(
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

Có thể dùng test context:

~~~java
package com.example.duration;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "demo.client.connect-timeout=500ms",
    "demo.client.request-timeout=PT10S",
    "demo.client.retry.initial-delay=250ms",
    "demo.client.retry.max-delay=5s"
})
class DurationBindingTest {

    @Autowired
    ClientProperties properties;

    @Test
    void bindsDurationFromSeveralFormats() {
        assertEquals(
                Duration.ofMillis(500),
                properties.connectTimeout());
        assertEquals(
                Duration.ofSeconds(10),
                properties.requestTimeout());
        assertEquals(
                Duration.ofMillis(250),
                properties.retry().initialDelay());
        assertEquals(
                Duration.ofSeconds(5),
                properties.retry().maxDelay());
    }
}
~~~

Test giả định dự án có **spring-boot-starter-test** và đã đăng ký ClientProperties bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**.

**Điểm quan trọng:** test truyền ba kiểu Duration khác nhau: simple style với hậu tố, ISO-8601, và tương ứng một số có unit. Spring Boot Binder chuyển về cùng type Java.

### 23.1. Test giá trị số không có hậu tố

Một test khác cho property mặc định mili-giây:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration sessionTimeout;
~~~

cần kiểm tra:

~~~text
session-timeout=30    -> Duration.ofSeconds(30)
session-timeout=30s   -> Duration.ofSeconds(30)
session-timeout=500ms -> Duration.ofMillis(500)
~~~

Nếu bỏ **@DurationUnit**, giá trị **30** phải được hiểu là 30 mili-giây. Khi nâng cấp hệ thống cũ, nên có test chứng minh chính xác quy tắc này.

## 24. Kiểm tra lỗi binding và cách chẩn đoán

Khi khởi động ứng dụng, nếu cấu hình Duration không hợp lệ, Binder có thể báo lỗi chuyển đổi giá trị.

Ví dụ:

~~~properties
demo.client.connect-timeout=maybe
~~~

**maybe** không phải duration hợp lệ. Nếu binder cần tạo Duration từ key đó, quá trình bind có thể thất bại.

Quy trình kiểm tra:

1. Xác định chính xác tên key đang được bind.
2. Xác định property cuối đang có hiệu lực từ Config Data, env, CLI hoặc nguồn khác.
3. Xem field/constructor parameter có kiểu **Duration** hay nhầm sang String, long, Period.
4. Kiểm tra cú pháp của giá trị: số, ISO-8601 hay số kèm hậu tố.
5. Nếu dùng số không hậu tố, kiểm tra **@DurationUnit** và đơn vị mặc định.
6. Kiểm tra số quá lớn hoặc nhỏ gây overflow khi chuyển đổi.
7. Nếu lỗi do validation, phân biệt nó với lỗi parse Duration.
8. Kiểm tra profile và override từ môi trường triển khai.

**Không log toàn bộ Environment khi đang debug**, bởi các nguồn có thể chứa password, token hoặc thông tin nội bộ. Chỉ log key và các giá trị không nhạy cảm cần chẩn đoán.

Một ví dụ bật log cấu hình chi tiết trong môi trường phát triển:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.properties=DEBUG
~~~

Log debug có thể giúp định vị lỗi binding, nhưng nội dung và mức độ chi tiết phụ thuộc phiên bản, logger và tình huống. Đừng giả định nó sẽ luôn in ra mọi key.

## 25. Những sai lầm dễ gặp

### 25.1. Quên hậu tố nên bị hiểu là mili-giây

~~~properties
demo.client.connect-timeout=30
~~~

Mặc định là **30ms**, không phải **30s**. Giải pháp: viết **30s** hoặc khai báo @DurationUnit khi cần giữ hợp đồng cũ.

### 25.2. Nhầm m với ms

~~~properties
retry-delay=5m
~~~

**5m** là 5 phút, không phải 5 mili-giây. Muốn 5 mili-giây, dùng **5ms**.

### 25.3. Dùng ký hiệu tháng/năm với Duration

Một nhu cầu như “gia hạn sau 2 tháng” thường thuộc kiểu **Period** hoặc thao tác lịch. Đừng kỳ vọng Duration tự hiểu tháng như một độ dài cố định.

### 25.4. Dùng Duration.parse(...) cho chuỗi simple style

~~~java
Duration.parse("5s")
~~~

Không phải ví dụ về cú pháp ISO-8601 chuẩn của Java. Nếu cần parse trực tiếp ngoài Binder, hãy dùng API Java phù hợp với ISO-8601 hoặc cơ chế conversion của Spring Boot, không mặc nhiên cho rằng Java Duration.parse hiểu mọi hậu tố Boot.

### 25.5. Coi @DurationUnit là đơn vị bắt buộc

@DurationUnit chỉ thay đơn vị mặc định của **giá trị không nêu hậu tố**. **500ms** vẫn có ý nghĩa mili-giây khi field được gắn **@DurationUnit(SECONDS)**.

### 25.6. Thực hiện toán học bằng mili-giây quá sớm

Chuyển Duration sang long qua **toMillis()** có thể làm mất phần nano-giây hoặc gặp overflow với khoảng cực lớn. Giữ Duration trong logic, chỉ chuyển ở API boundary cần một kiểu số.

### 25.7. Không kiểm tra zero hoặc âm

Một Duration có thể biểu diễn zero hoặc số âm; không phải mọi client hoặc scheduler đều chấp nhận. Cần validation riêng theo ý nghĩa nghiệp vụ.

### 25.8. Nhầm giá trị YAML với tên property

~~~yaml
demo:
  client:
    connect-timeout: 5s
~~~

**connect-timeout** là tên canonical, **5s** là giá trị được convert. Java field tương ứng có thể tên **connectTimeout** nhờ relaxed binding.

### 25.9. Tự chuyển String thành long

Điều này loại bỏ khả năng dùng **500ms**, **PT5S** và khiến đơn vị ngầm định không rõ. Dùng **Duration** và Binder khi cấu hình là một khoảng thời gian.

### 25.10. Quên đăng ký configuration properties

Có annotation nhưng không scanning hoặc enable, bean sẽ không được tạo thích hợp. Với record constructor binding, dùng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

### 25.11. Nghĩ chỉnh env là cập nhật bean đang chạy

Thông thường configuration properties được bind khi context khởi tạo. Thay biến ở terminal khác không tự làm bean đã bind cập nhật. Hãy restart/rolling deploy khi thay cấu hình theo phương thức thông thường.

### 25.12. Dùng property không đúng ý nghĩa tiêu thụ

Một Duration đúng cú pháp chưa bảo đảm thư viện sử dụng cùng ý nghĩa timeout. Ví dụ connect timeout khác read timeout, request timeout và idle timeout. Tên property và tài liệu cần nói rõ.

## 26. Bài thực hành

### Bài A — so sánh ba cách viết Duration

1. Tạo **demo.client.connect-timeout** trong YAML.
2. Thử lần lượt **5000**, **PT5S** và **5s**.
3. In kết quả **connectTimeout().toMillis()** bằng một endpoint local.
4. Quan sát tất cả đều là **5000 ms** khi không dùng @DurationUnit.

### Bài B — xem đơn vị mặc định

1. Đổi property thành **30**.
2. Giữ field Duration không có @DurationUnit.
3. Quan sát kết quả **30ms**.
4. Gắn **@DurationUnit(ChronoUnit.SECONDS)**.
5. Khởi động lại với cùng giá trị **30**, quan sát **30s**.

**Mục tiêu:** hiểu annotation thay đổi đơn vị mặc định của số không hậu tố.

### Bài C — cùng JAR, khác môi trường

1. Build ứng dụng một lần.
2. Trong YAML, đặt **request-timeout: 10s**.
3. Khởi động bằng **DEMO_CLIENT_REQUESTTIMEOUT=15s**.
4. Gọi endpoint để kiểm tra giá trị thực.
5. Dừng và chạy lại bằng **--demo.client.request-timeout=20s**.

**Mục tiêu:** nhận biết thứ tự nguồn cấu hình và cách một Duration field có thể nhận giá trị khác nhau khi deploy.

### Bài D — kiểm thử ISO-8601

1. Đặt **connect-timeout: PT0.5S**.
2. Bind sang Duration.
3. Xác nhận **toMillis() = 500**.
4. Thử **PT1M30S** và xác nhận 90 giây.

**Mục tiêu:** hiểu cú pháp ISO-8601 và sự tương đương với đơn vị simple style.

### Bài E — thử lỗi conversion và validation

1. Thử **request-timeout: wrong**.
2. Quan sát lỗi chuyển kiểu khi khởi động.
3. Sửa thành **0s**: nó có thể parse được.
4. Dùng logic kiểm tra > 0 hoặc custom validator phù hợp.
5. Phân biệt lỗi parse và lỗi ràng buộc nghiệp vụ.

### Bài F — migration từ long

1. Tạo property cũ **session-timeout: 30** với hợp đồng “giây”.
2. Chuyển type Java từ long sang Duration.
3. Gắn **@DurationUnit(ChronoUnit.SECONDS)**.
4. Test cả **30**, **30s** và **500ms**.
5. Ghi hướng dẫn cho người vận hành rằng hậu tố rõ ràng được hỗ trợ.

**Mục tiêu:** chuyển đổi kiểu mà không thay đổi ngầm định của cấu hình đã phát hành.

## 27. Checklist trước khi dùng Duration cho một property

- Property biểu diễn **khoảng thời gian kỹ thuật** hay khái niệm **ngày/tháng theo lịch**?
- Tên có mô tả đúng **connect**, **read**, **request**, **idle** hoặc **retry** timeout?
- File YAML/properties có **hậu tố đơn vị rõ ràng** hay không?
- Nếu người dùng cấp số không hậu tố, đơn vị mặc định có được tài liệu hóa không?
- Có cần **@DurationUnit** để giữ tương thích ngược?
- Có default hợp lý từ YAML hoặc **@DefaultValue** không?
- Giá trị **0** có nghĩa gì đối với component thực tế?
- Giá trị âm có bị chặn theo yêu cầu nghiệp vụ không?
- Có giới hạn trên để tránh overflow hoặc chờ quá lâu không?
- Tên biến môi trường đã được chuyển đúng từ canonical property chưa?
- Type đã được đăng ký bằng scanning/enable phù hợp chưa?
- Có test xác nhận những định dạng quan trọng và đơn vị mặc định không?
- Việc thay cấu hình có yêu cầu restart ứng dụng không?
- Có tài liệu cho người vận hành về định dạng ISO, đơn vị simple và fallback không?

## 28. Tổng kết

- **java.time.Duration** là kiểu thích hợp để biểu diễn timeout, delay và interval trong Java.
- Spring Boot có cơ chế conversion dành riêng cho Duration trong **@ConfigurationProperties**.
- Ba dạng giá trị được hỗ trợ là **số**, **ISO-8601** và **số kèm hậu tố đơn vị**.
- Hậu tố đơn vị được tài liệu hóa gồm **ns**, **us**, **ms**, **s**, **m**, **h**, **d**.
- **Số không có hậu tố mặc định được hiểu là mili-giây**.
- **@DurationUnit** có thể đổi đơn vị mặc định, đặc biệt hữu ích khi migration từ property long cũ.
- **@DefaultValue** có thể cung cấp default trong constructor binding, trong khi JavaBean có thể khởi tạo field.
- Cùng một Duration property có thể được cấp từ YAML, properties, env, system properties hoặc CLI.
- Cần phân biệt **Duration** với **Period** khi nghiệp vụ liên quan đến lịch.
- Chuyển đổi kiểu đúng chưa đủ: phải quy định ý nghĩa của zero, âm và giới hạn hợp lệ.
- Giữ Duration trong code cho đến khi một API cụ thể yêu cầu số mili-giây hoặc đơn vị khác.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 Reference — Externalized Configuration, phần *Converting Durations*, *Constructor Binding*, *Properties Conversion*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Java 21 API — Duration: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html
- Java 21 API — Period: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html
- Spring Boot API — DurationUnit: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html
