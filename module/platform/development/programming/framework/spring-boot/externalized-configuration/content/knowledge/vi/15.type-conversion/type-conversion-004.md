# Đơn vị mặc định và @DurationUnit khi chuyển đổi Duration trong Spring Boot

## 1. Một con số nhỏ có thể làm timeout sai một nghìn lần

Một ứng dụng Spring Boot gọi dịch vụ bên ngoài có cấu hình:

~~~properties
client.request-timeout=30
~~~

Bạn mong ý nghĩa của giá trị này là **30 giây**, nhưng field Java lại có kiểu:

~~~java
private Duration requestTimeout;
~~~

Nếu dùng cách liên kết `@ConfigurationProperties` thông thường và không chỉ định đơn vị riêng, Spring Boot hiểu con số `30` **không có hậu tố** là **30 mili giây**, không phải 30 giây.

Sự khác biệt là rất lớn:

~~~text
30 ms = 0,03 giây
30 s  = 30.000 ms
~~~

Một timeout ngắn bất thường có thể khiến các request thất bại dù dịch vụ bên ngoài vẫn hoạt động. Ngược lại, một giá trị tưởng là mili giây nhưng được hiểu thành giây có thể làm tác vụ treo quá lâu.

Spring Boot cung cấp annotation `@DurationUnit` để xử lý vấn đề này khi liên kết kiểu `java.time.Duration`:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
~~~

Khi được đặt đúng vị trí và cấu hình được binder xử lý, dòng `client.request-timeout=30` trở thành **30 giây** thay vì **30 mili giây**.

Bài học tập trung vào những câu hỏi:

1. Tại sao giá trị thuần số cho `Duration` mặc định là mili giây?
2. `@DurationUnit` thay đổi điều gì và không thay đổi điều gì?
3. Khi giá trị có hậu tố `ms`, `s`, `m` hoặc viết theo ISO-8601, annotation còn ảnh hưởng không?
4. Đặt annotation ở field JavaBean và constructor parameter như thế nào?
5. Phân biệt **đơn vị mặc định** với **giá trị mặc định** ra sao?
6. Chuyển từ thuộc tính `long` sang `Duration` thế nào để không làm thay đổi ý nghĩa cấu hình cũ?
7. Làm sao kiểm tra kiểu `Duration` đã bind đúng mà không nhầm với `Period` hoặc `DataSize`?

## 2. Duration là kiểu gì?

`java.time.Duration` là kiểu Java biểu diễn một khoảng thời gian dựa trên giây và phần nhỏ hơn của giây (*seconds and nanoseconds*). Nó thường xuất hiện ở:

- Thời gian chờ kết nối mạng.
- Thời gian chờ phản hồi HTTP.
- Độ trễ giữa các lần thử lại.
- Khoảng thời gian giữ cache.
- Thời gian chờ của một job.
- Khoảng thời gian của scheduler.
- Thời hạn một thao tác có thể tiếp tục chạy.

Trong Java:

~~~java
import java.time.Duration;

Duration first = Duration.ofMillis(500);
Duration second = Duration.ofSeconds(30);
Duration third = Duration.ofMinutes(2);
~~~

Các đối tượng này có giá trị thời gian cụ thể. `Duration` không lưu kiểu “30 với đơn vị chưa biết”; khi đã tạo, đối tượng biểu diễn độ dài thời gian rõ ràng.

Ví dụ:

~~~java
Duration.ofSeconds(30).toMillis(); // 30000
Duration.ofMillis(30).toMillis();  // 30
~~~

Spring Boot cần chuyển một chuỗi hoặc số từ `Environment` thành `Duration`. Chính ở **bước chuyển đổi đầu vào** này câu hỏi “đơn vị mặc định là gì?” xuất hiện.

### Không nhầm với thời điểm

`Duration` diễn tả *bao lâu*, không phải *lúc nào*:

- `Duration.ofSeconds(30)`: khoảng thời gian 30 giây.
- `Instant.now()`: một thời điểm.
- `LocalDateTime`: ngày giờ cục bộ.
- `Period.ofMonths(1)`: một khoảng theo năm/tháng/ngày, có quy tắc khác.

`@DurationUnit` chỉ phục vụ ý nghĩa đơn vị cho việc chuyển đổi `Duration`; nó không xác định múi giờ, lịch hay lịch hẹn.

## 3. Spring Boot nhận những định dạng Duration nào?

Trong cơ chế externalized configuration và type-safe configuration properties, Spring Boot hỗ trợ ba cách biểu diễn thường gặp.

### 3.1. Số không có hậu tố

~~~properties
client.request-timeout=30
~~~

Đây là một giá trị không chỉ rõ đơn vị. Trong binding thông thường:

- **Không có `@DurationUnit`:** 30 được hiểu là **30 ms**.
- **Có `@DurationUnit(ChronoUnit.SECONDS)`:** 30 được hiểu là **30 s**.
- **Có `@DurationUnit(ChronoUnit.MINUTES)`:** 30 được hiểu là **30 phút**.

### 3.2. Số có hậu tố đơn vị

~~~properties
client.request-timeout=30s
~~~

Hậu tố `s` chỉ rõ giây. Giá trị mang đơn vị tường minh; không cần suy đoán đơn vị mặc định.

Ví dụ:

~~~properties
client.request-timeout=500ms
client.retry-delay=2s
client.cache-ttl=15m
client.long-timeout=1h
~~~

### 3.3. Chuẩn ISO-8601 của Duration

~~~properties
client.request-timeout=PT30S
client.retry-delay=PT2M
client.cache-ttl=PT1H30M
~~~

`PT30S` là cách viết 30 giây; `PT2M` là 2 phút; `PT1H30M` là 1 giờ 30 phút. Trong những giá trị ấy, thông tin đơn vị nằm trong chính biểu thức ISO-8601.

Ba cách có thể cho cùng một `Duration`:

~~~properties
# Ba ví dụ độc lập — không đặt cả ba cùng một khóa trong một file
client.request-timeout=30000
client.request-timeout=30s
client.request-timeout=PT30S
~~~

**Điều kiện:** trường hợp `30000` chỉ tương đương 30 giây khi đơn vị mặc định của thuộc tính là **mili giây**.

Nếu field được đặt `@DurationUnit(ChronoUnit.SECONDS)` thì con số trần tương đương 30 giây phải là `30`, không phải `30000`.

## 4. Đơn vị mặc định: không có annotation nghĩa là milliseconds

Tài liệu Spring Boot quy định khi bind một `Duration` từ biểu diễn số thông thường, đơn vị mặc định là **milliseconds** — mili giây — trừ khi được thay bằng `@DurationUnit`.

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
~~~

Cấu hình:

~~~yaml
service:
  connect-timeout: 10
  read-timeout: 500
~~~

Với binding chuẩn và không có annotation đơn vị khác:

~~~text
connectTimeout = PT0.01S  = 10 ms
readTimeout    = PT0.5S   = 500 ms
~~~

Có thể quan sát:

~~~java
properties.connectTimeout().toMillis(); // 10
properties.readTimeout().toMillis();    // 500
~~~

**Tại sao người học thường nhầm?** Vì giá trị `10` trong tên khóa `connect-timeout` không tự nói rõ là giây hay mili giây. Tên field, tên thuộc tính, hay phần chú thích trong code không làm binder tự biết đơn vị nghiệp vụ bạn mong muốn.

Bộ chuyển đổi cần một quy tắc. Mặc định mà Spring Boot dùng cho số trần là **ms**.

### Bảng ví dụ khi không có @DurationUnit

| Chuỗi cấu hình | Duration tương ứng | Quy đổi |
| --- | --- | --- |
| `1` | 1 ms | `PT0.001S` |
| `20` | 20 ms | `PT0.02S` |
| `500` | 500 ms | `PT0.5S` |
| `1000` | 1.000 ms | `PT1S` |
| `30000` | 30.000 ms | `PT30S` |
| `60000` | 60.000 ms | `PT1M` |

Số trần không “mặc nhiên là giây” chỉ vì field có tên `timeout`, `delay` hay `duration`.

## 5. @DurationUnit thay đổi đơn vị mặc định như thế nào?

Annotation:

~~~java
import org.springframework.boot.convert.DurationUnit;
~~~

Nhận một `java.time.temporal.ChronoUnit`:

~~~java
import java.time.temporal.ChronoUnit;
~~~

Ví dụ:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
~~~

Ý nghĩa: **nếu dữ liệu đầu vào cho thuộc tính này không nêu đơn vị**, binder dùng đơn vị **giây** để chuyển thành `Duration`.

Ví dụ:

~~~properties
client.request-timeout=30
~~~

với field ở trên được bind thành:

~~~java
Duration.ofSeconds(30)
~~~

Thử đổi:

~~~java
@DurationUnit(ChronoUnit.MINUTES)
private Duration requestTimeout;
~~~

Khi nguồn vẫn là `30`, giá trị bây giờ là:

~~~java
Duration.ofMinutes(30)
~~~

**Không nên dùng một annotation đơn vị chung chỉ vì muốn mọi timeout có cùng “con số”.** Hãy lựa chọn đơn vị theo hợp đồng cấu hình của từng thuộc tính. Timeout kết nối có thể phù hợp giây; độ trễ polling có thể phù hợp mili giây; thời hạn TTL có thể phù hợp phút hoặc giờ.

### Thứ gì không thay đổi?

`@DurationUnit` **không**:

- Tự đặt một giá trị mặc định nếu khóa hoàn toàn vắng mặt.
- Tự kích hoạt hoặc tự tạo bean cấu hình.
- Thay đổi tên prefix hoặc tên thành viên khi relaxed binding.
- Chuyển các số ở mọi nơi trong Java thành giây.
- Thay đổi ý nghĩa của một giá trị có hậu tố rõ ràng như `500ms`, `2m` hoặc `PT30S`.
- Bật validation để đảm bảo thời gian luôn dương.
- Là một thay thế cho `Thread.sleep`, timeout API hay thuật toán scheduler.

Nó chỉ cung cấp **đơn vị được dùng khi chuyển một giá trị Duration không ghi đơn vị tường minh** qua cơ chế binding tương ứng.

## 6. Ví dụ JavaBean binding với @DurationUnit

Đây là kiểu ví dụ dễ quan sát nhất.

### 6.1. Class cấu hình

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration connectTimeout = Duration.ofSeconds(5);

    private Duration readTimeout = Duration.ofMillis(500);

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

### 6.2. Đăng ký bean cấu hình

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

`ClientProperties` phải nằm trong phạm vi quét, hoặc được đăng ký tường minh qua `@EnableConfigurationProperties(ClientProperties.class)`.

### 6.3. Nguồn cấu hình

~~~yaml
app:
  client:
    connect-timeout: 15
    read-timeout: 250
~~~

Kết quả:

~~~text
connectTimeout = 15 giây       (@DurationUnit(SECONDS))
readTimeout    = 250 mili giây  (không có @DurationUnit)
~~~

Cùng là số trần, nhưng **mỗi field có quy tắc đơn vị riêng**.

### 6.4. Đọc trong service

~~~java
package com.example.demo.service;

import com.example.demo.config.ClientProperties;
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class ClientSettingsService {

    private final ClientProperties properties;

    public ClientSettingsService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration connectTimeout() {
        return properties.getConnectTimeout();
    }

    public Duration readTimeout() {
        return properties.getReadTimeout();
    }
}
~~~

Service nhận bean đã được binder cấu hình. Không cần tự nối hậu tố `s` vào chuỗi nguồn hoặc chuyển `15` thành giây bằng phép nhân thủ công.

## 7. Khi giá trị đã có hậu tố: đơn vị tường minh được ưu tiên

Giữ class:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
~~~

Và thay đổi nguồn cấu hình lần lượt:

| Giá trị nguồn | Kết quả Duration | Lý do |
| --- | --- | --- |
| `15` | 15 giây | Không có hậu tố, dùng `SECONDS` từ annotation. |
| `15s` | 15 giây | Hậu tố `s` chỉ rõ giây. |
| `15000ms` | 15 giây | Hậu tố `ms` chỉ rõ mili giây. |
| `250ms` | 250 mili giây | Hậu tố `ms` được tôn trọng dù annotation là `SECONDS`. |
| `1m` | 1 phút | Hậu tố `m` chỉ rõ phút. |
| `PT15S` | 15 giây | ISO-8601 có ý nghĩa thời gian rõ ràng. |

Một nhầm lẫn dễ gây lỗi là cho rằng annotation “ép tất cả giá trị thành giây”. Không đúng.

Ví dụ:

~~~properties
app.client.connect-timeout=250ms
~~~

vẫn là 250 ms. Annotation không nhân 250 ms thành 250 giây.

Tương tự:

~~~properties
app.client.connect-timeout=2m
~~~

là 2 phút, không phải 2 giây. Điều này hữu ích khi muốn giữ **đơn vị mặc định dễ dùng cho số trần**, nhưng vẫn cho người triển khai chọn một đơn vị khác khi cần.

### Quy tắc thực hành

**Ghi hậu tố trong cấu hình mới** nếu bạn muốn người vận hành đọc là hiểu ngay đơn vị:

~~~yaml
app:
  client:
    connect-timeout: 15s
    read-timeout: 250ms
~~~

Còn `@DurationUnit` rất quan trọng khi phải duy trì tương thích với **các số không có hậu tố đang tồn tại**, hoặc khi dự án có một hợp đồng rõ ràng như “mọi giá trị timeout trần trong module này đều tính bằng giây”.

## 8. Các hậu tố Duration mà Spring Boot hỗ trợ

Theo tài liệu Spring Boot 3.3, cú pháp dễ đọc cho `Duration` hỗ trợ các hậu tố:

| Hậu tố | Đơn vị | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| `ns` | Nanosecond | `500ns` | 500 phần tỷ giây. |
| `us` | Microsecond | `250us` | 250 phần triệu giây. |
| `ms` | Millisecond | `500ms` | Nửa giây. |
| `s` | Second | `30s` | 30 giây. |
| `m` | Minute | `2m` | 2 phút. |
| `h` | Hour | `1h` | 1 giờ. |
| `d` | Day | `1d` | 24 giờ. |

Một số quy đổi:

~~~text
1s    = 1000ms
1ms   = 1000us
1us   = 1000ns
1m    = 60s
1h    = 60m
1d    = 24h
~~~

`Duration` dựa trên một độ dài thời gian chính xác, do đó `1d` tương ứng 24 giờ. Đừng dùng nó để thay một quy tắc lịch “đến cùng giờ ngày hôm sau ở múi giờ địa phương” trong mọi trường hợp; điều đó có thể liên quan tới lịch và daylight saving time.

### Phân biệt chữ m

Trong cú pháp Duration:

~~~text
5m = 5 phút
~~~

Không phải 5 tháng.

Nếu bạn cần biểu diễn số tháng hoặc năm trên lịch, kiểu phù hợp thường là `java.time.Period` với quy tắc riêng, không phải `Duration` có `@DurationUnit`.

### Có dùng y hay w không?

Không nên giả định các ký hiệu `y` hoặc `w` của `Period` hoạt động như hậu tố Duration dễ đọc. Đối với Duration theo tài liệu Spring Boot, hãy dùng các hậu tố trong bảng hoặc ISO-8601 tương ứng.

## 9. ISO-8601 và Duration.parse: khác gì với cú pháp 30s?

Spring Boot hỗ trợ cả cú pháp dễ đọc như `30s` và cú pháp ISO-8601 như `PT30S`.

Ví dụ:

~~~properties
jobs.retry-delay=PT2M
jobs.execution-timeout=PT1H30M
jobs.poll-interval=PT0.5S
~~~

Các giá trị tương ứng:

~~~java
Duration.ofMinutes(2)
Duration.ofMinutes(90)
Duration.ofMillis(500)
~~~

Điểm cần nhớ:

~~~java
Duration.parse("PT30S")
~~~

là cú pháp Java chuẩn và tạo `Duration.ofSeconds(30)`.

Còn:

~~~java
Duration.parse("30s")
~~~

**không phải** cú pháp ISO-8601 mà `Duration.parse` của Java chấp nhận. Spring Boot hỗ trợ `30s` nhờ bộ chuyển đổi cấu hình riêng. Đừng nhầm tính năng của Spring Boot Binder với khả năng mặc định của `java.time.Duration.parse`.

### Khi nào chọn ISO-8601?

ISO-8601 hữu ích khi cấu hình được chia sẻ với hệ thống khác đã dùng chuẩn này hoặc khi muốn thể hiện khoảng thời gian phức hợp rõ ràng. Cú pháp hậu tố ngắn như `30s`, `5m` thường dễ đọc hơn với người vận hành trong các file cấu hình Spring Boot.

## 10. @DurationUnit trong constructor binding

Spring Boot 3.x hỗ trợ constructor binding cho các class cấu hình bất biến. Với nhiều thông số Duration, bạn có thể chỉ định đơn vị ở **constructor parameter**.

Ví dụ:

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "jobs")
public class JobProperties {

    private final Duration executionTimeout;
    private final Duration retryDelay;

    public JobProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("30s")
            Duration executionTimeout,

            @DefaultValue("500ms")
            Duration retryDelay) {
        this.executionTimeout = executionTimeout;
        this.retryDelay = retryDelay;
    }

    public Duration getExecutionTimeout() {
        return executionTimeout;
    }

    public Duration getRetryDelay() {
        return retryDelay;
    }
}
~~~

Khi class này có constructor cần binding và được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, binder có thể tạo bean từ các giá trị cấu hình.

Ví dụ:

~~~yaml
jobs:
  execution-timeout: 45
  retry-delay: 2s
~~~

Kết quả:

~~~text
executionTimeout = 45 giây
retryDelay       = 2 giây
~~~

Ở trường `executionTimeout`, `45` không ghi đơn vị nên `@DurationUnit(SECONDS)` quyết định cách hiểu. Ở `retryDelay`, giá trị `2s` có đơn vị riêng nên không cần annotation.

### @DurationUnit có thể gắn ở đâu?

Theo API Spring Boot 3.x, `@DurationUnit` được thiết kế cho **field** hoặc **parameter**. Hai cách dùng quen thuộc:

- Field của JavaBean liên kết qua setter.
- Parameter constructor trong constructor binding.

Không nên tự suy ra có thể đặt annotation ở bất kỳ phương thức Java nào rồi mong binder luôn nhận. Với constructor binding, mẫu an toàn là annotate chính **constructor parameter** có kiểu `Duration`.

### Record

Với record:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "jobs")
public record SimpleJobProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration executionTimeout,
        Duration retryDelay) {
}
~~~

Record component có thể mang annotation áp dụng cho field/parameter, được trình biên dịch Java truyền tới các phần tử tương ứng khi phù hợp. Trong dự án dùng constructor binding, người đọc nên hiểu annotation này gắn với việc chuyển giá trị cho component `executionTimeout`. Nếu class có cấu trúc constructor phức tạp, hãy viết constructor/parameter tường minh để làm rõ điều kiện binding.

**Quan trọng:** constructor binding cho `@ConfigurationProperties` cần cơ chế đăng ký phù hợp, không phải một record bất kỳ gắn `@Component` rồi kỳ vọng Spring tự dùng binder cho các tham số constructor.

## 11. Đơn vị mặc định khác hoàn toàn giá trị mặc định

Hai khái niệm đều có chữ “mặc định” nhưng rất khác.

### 11.1. Đơn vị mặc định

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout;
~~~

Câu này trả lời:

> Nếu nguồn cấu hình có số trần như `20`, nó có nghĩa là 20 **đơn vị gì**?

Đáp án: 20 giây.

Nó **không** trả lời:

> Nếu hoàn toàn không có khóa `timeout` thì nên dùng bao nhiêu?

### 11.2. Giá trị mặc định trong JavaBean

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout = Duration.ofSeconds(20);
~~~

Nếu khóa không được cung cấp và không có cơ chế khác ghi đè, giá trị khởi tạo `Duration.ofSeconds(20)` có thể được giữ lại trong JavaBean binding.

Nếu cấu hình là:

~~~properties
app.timeout=40
~~~

thì binder chuyển `40` theo đơn vị giây và ghi đè field thành `Duration.ofSeconds(40)`.

### 11.3. Giá trị mặc định trong constructor binding

~~~java
public JobProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("20s")
        Duration timeout) {
    this.timeout = timeout;
}
~~~

`@DefaultValue("20s")` mô tả giá trị dự phòng **khi thuộc tính thiếu** trong constructor binding. Còn `@DurationUnit(SECONDS)` xác định đơn vị khi nguồn có một số trần.

Bảng đối chiếu:

| Tình huống | @DurationUnit(SECONDS) | @DefaultValue("20s") |
| --- | --- | --- |
| Nguồn có `timeout=40` | 40 giây | Không cần dùng default. |
| Nguồn có `timeout=500ms` | 500 ms | Không cần dùng default. |
| Nguồn không có `timeout` | Không tự tạo số 20 | Giá trị dự phòng 20 giây. |

Không dùng `@DurationUnit` để thay `@DefaultValue`, và không dùng `@DefaultValue` để thay quy tắc đơn vị trần của một trường.

## 12. Vì sao chuyển từ long sang Duration dễ gây lỗi?

Một dự án cũ có class:

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {
    private long expirySeconds;

    public long getExpirySeconds() {
        return expirySeconds;
    }

    public void setExpirySeconds(long expirySeconds) {
        this.expirySeconds = expirySeconds;
    }
}
~~~

Tệp:

~~~properties
cache.expiry-seconds=60
~~~

Trong phiên bản cũ của ứng dụng, mã dùng:

~~~java
Duration expiry = Duration.ofSeconds(
        properties.getExpirySeconds());
~~~

Nghĩa nghiệp vụ là **60 giây**.

Sau khi nâng cấp thiết kế, có thể muốn dùng kiểu Duration:

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {
    private Duration expirySeconds;
    // getters/setters
}
~~~

Nhưng nếu field `expirySeconds` **không** có annotation đơn vị và tệp vẫn là `60`, binder có thể coi 60 là **60 ms**. Đây là một lỗi tương thích ngược nghiêm trọng.

### Cách bảo toàn ý nghĩa

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration expirySeconds;

    public Duration getExpirySeconds() {
        return expirySeconds;
    }

    public void setExpirySeconds(Duration expirySeconds) {
        this.expirySeconds = expirySeconds;
    }
}
~~~

Với:

~~~properties
cache.expiry-seconds=60
~~~

bây giờ binder tạo `Duration.ofSeconds(60)`. Ý nghĩa của cấu hình cũ được giữ nguyên.

Đây là một ứng dụng quan trọng của `@DurationUnit`: **chuyển từ thuộc tính số truyền thống sang Duration mà không đổi ngầm đơn vị của dữ liệu cũ**.

### Một lựa chọn khác: sửa dữ liệu nguồn

Nếu bạn kiểm soát được toàn bộ nguồn cấu hình, có thể chuyển:

~~~properties
cache.expiry-seconds=60
~~~

thành:

~~~properties
cache.expiry=60s
~~~

và đổi tên property/field để phù hợp. Nhưng khi có nhiều hệ thống triển khai, secret manager, biến môi trường và cấu hình ngoài JAR, không chắc mọi nơi đã cập nhật cùng lúc.

`@DurationUnit(SECONDS)` cho phép hỗ trợ giá trị cũ ở dạng số trần trong thời gian di chuyển. Dù vậy, cần xác định rõ hợp đồng mới: với mọi cấu hình mới, dùng hậu tố tường minh sẽ dễ tránh nhầm lẫn hơn.

## 13. Không dựa vào tên field để đoán đơn vị

Đặt field tên:

~~~java
Duration timeoutSeconds;
~~~

không buộc binder hiểu giá trị:

~~~properties
app.timeout-seconds=30
~~~

là 30 giây. Tên chứa `Seconds` chỉ là một tên property; nó **không tự tạo annotation đơn vị**.

Cần:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeoutSeconds;
~~~

hoặc nguồn cấu hình chỉ rõ:

~~~properties
app.timeout-seconds=30s
~~~

Khi thiết kế mới, tên `timeout` + giá trị có hậu tố `30s` thường dễ bảo trì hơn việc mã hóa đơn vị vào tên field rồi vẫn phải nhớ annotation. Tuy nhiên, tên chứa đơn vị vẫn có thể cần duy trì để tương thích với cấu hình hiện có.

Tương tự:

~~~java
Duration retryDelayMillis;
~~~

không đảm bảo mọi nguồn phải ghi mili giây. Nếu nguồn có `2s` thì kết quả vẫn là 2 giây trong binding Duration; phần `Millis` ở tên Java không ghi đè một hậu tố tường minh.

## 14. YAML, Properties, biến môi trường và CLI dùng cùng nguyên tắc

Đơn vị mặc định là quy tắc **của trường Duration khi binder chuyển kiểu**, không phải quy tắc chỉ tồn tại trong một loại tệp.

Ví dụ class:

~~~java
@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

Có thể cung cấp giá trị qua Properties:

~~~properties
app.jobs.timeout=20
~~~

Qua YAML:

~~~yaml
app:
  jobs:
    timeout: 20
~~~

Qua biến môi trường trên shell kiểu Unix:

~~~bash
APP_JOBS_TIMEOUT=20 java -jar app.jar
~~~

Hoặc qua command line:

~~~bash
java -jar app.jar --app.jobs.timeout=20
~~~

Trong những điều kiện binding chuẩn, nếu đây là giá trị cuối cùng của thuộc tính, binder chuyển 20 thành **20 giây** do annotation.

Nếu đổi thành:

~~~bash
java -jar app.jar --app.jobs.timeout=500ms
~~~

thì kết quả là **500 mili giây**.

### Nguồn nào thắng?

Nếu YAML có:

~~~yaml
app:
  jobs:
    timeout: 30s
~~~

nhưng CLI ghi:

~~~bash
java -jar app.jar --app.jobs.timeout=15
~~~

trong lần chạy Spring Boot thông thường, CLI có ưu tiên cao hơn tệp Config Data. Binder lấy giá trị **15** từ CLI rồi áp dụng `@DurationUnit(SECONDS)`, dẫn đến **15 giây**.

Nghĩ theo hai bước:

1. `Environment` chọn **giá trị cấu hình có hiệu lực**.
2. Binder chuyển giá trị đó sang `Duration` bằng **đơn vị được xác định bởi hậu tố hoặc annotation**.

Không nhầm thứ tự `PropertySource` với chính sách đơn vị.

## 15. @DurationUnit không áp dụng chung cho Environment.getProperty

Hãy phân biệt hai đoạn mã:

~~~java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

và:

~~~java
Duration timeout = environment.getProperty(
        "client.timeout", Duration.class);
~~~

Đoạn thứ nhất đi qua binder của `@ConfigurationProperties` với metadata của thành viên `timeout`, bao gồm `@DurationUnit`.

Đoạn thứ hai chỉ yêu cầu `Environment` chuyển thuộc tính có tên `client.timeout` thành `Duration`. Lời gọi này **không tự nhận annotation nằm trên một class khác**, nên không nên giả định nó áp dụng đơn vị `SECONDS` của `ClientProperties`.

Ví dụ nếu `client.timeout=30`, giá trị qua bind properties bean có thể là 30 giây, trong khi một chuyển đổi Duration độc lập không có metadata đơn vị thường dùng mặc định mili giây.

Để tránh hai cách hiểu cho một khóa:

- Ưu tiên sử dụng **properties bean đã bind** ở các service cần biết timeout.
- Hoặc ghi **đơn vị tường minh** trong nguồn: `30s`.
- Nếu buộc phải đọc trực tiếp dạng chuỗi, tự chuyển đổi theo hợp đồng rõ ràng; đừng âm thầm nhân 1.000 ở nhiều chỗ.

### @Value

~~~java
@Value("${client.timeout}")
private Duration timeout;
~~~

`@Value` là một cơ chế tiêm giá trị qua placeholder; không phải lúc nào nó mang cùng metadata đơn vị như Binder của `@ConfigurationProperties`. Vì vậy, khi cần `@DurationUnit`, nên giữ mô hình properties bean hoặc luôn ghi hậu tố trong nguồn.

Trong code ứng dụng, tránh để nhiều con đường đọc cùng thuộc tính nhưng diễn giải số trần theo những đơn vị khác nhau.

## 16. Chuyển đổi Duration và validation là hai việc khác nhau

Giả sử:

~~~properties
app.retry-delay=0s
~~~

Binder có thể chuyển giá trị này thành:

~~~java
Duration.ZERO
~~~

Nhưng **độ trễ bằng 0** có phù hợp nghiệp vụ hay không là câu hỏi khác.

Hoặc:

~~~properties
app.request-timeout=-1s
~~~

Nếu hệ thống nhận giá trị Duration âm, điều đó không đồng nghĩa timeout âm có ý nghĩa hợp lệ đối với HTTP client bạn sử dụng. Từng API có thể yêu cầu một phạm vi khác nhau.

`@DurationUnit` không tự đảm bảo:

- Giá trị lớn hơn 0.
- Giá trị không âm.
- Không vượt mức an toàn.
- Đúng đơn vị mà thư viện HTTP/scheduler mong đợi.
- Giá trị đã được khởi tạo khi khóa thiếu.

Có thể kiểm tra rõ ràng khi sử dụng:

~~~java
Duration timeout = properties.requestTimeout();

if (timeout == null || timeout.isZero() || timeout.isNegative()) {
    throw new IllegalArgumentException(
            "app.request-timeout phải là thời gian dương");
}
~~~

Với một nhóm `@ConfigurationProperties`, bạn cũng có thể tích hợp Bean Validation hoặc quy tắc validation tùy chỉnh để phát hiện cấu hình sai sớm khi khởi động.

### Đừng coi chuyển đổi kiểu là kiểm tra nghiệp vụ

~~~properties
app.request-timeout=999999d
~~~

Có thể là một khoảng quá lớn so với nhu cầu, dù cú pháp có đơn vị hợp lệ và kiểu Java có thể biểu diễn nó. Bước validation cần kiểm tra giới hạn hợp lý nếu ứng dụng cần.

## 17. Khi thiếu khóa: @DurationUnit không cung cấp default value

Class:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration startupDelay) {
}
~~~

Nếu không có `app.startup-delay`, annotation không biến thành mặc định `0s`, `1s` hay `30s`. Giá trị nhận được sẽ phụ thuộc vào cách constructor binding, giá trị mặc định khai báo và việc thiếu khóa.

Nếu tham số là bắt buộc, cách rõ ràng là có validation hoặc một mặc định cụ thể:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private final Duration startupDelay;

    public AppProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("3s")
            Duration startupDelay) {
        this.startupDelay = startupDelay;
    }

    public Duration getStartupDelay() {
        return startupDelay;
    }
}
~~~

Với constructor binding đúng cơ chế, nếu khóa vắng mặt, `@DefaultValue("3s")` cung cấp 3 giây. Nếu khóa là `app.startup-delay=20`, annotation unit làm giá trị thành 20 giây.

### Nếu dùng @DefaultValue("3") thì sao?

Khi một parameter đồng thời có `@DefaultValue("3")` và `@DurationUnit(ChronoUnit.SECONDS)`, định nghĩa unit có thể được sử dụng để diễn giải số trần này. Nhưng để người đọc không phải suy đoán, cấu hình mặc định có ý nghĩa rõ ràng hơn khi viết `@DefaultValue("3s")`.

Đây cũng là một quy tắc tổ chức tốt: **giá trị mặc định tự ghi đơn vị**, trong khi annotation vẫn bảo vệ các số trần được người triển khai truyền vào sau này.

## 18. Phân biệt Duration, Period và DataSize

Spring Boot có những annotation tên gần giống:

| Kiểu đích | Ý nghĩa | Đơn vị mặc định của số trần | Annotation thay đổi đơn vị |
| --- | --- | --- | --- |
| `Duration` | Khoảng thời gian trên trục giây/nanosecond | Milliseconds | `@DurationUnit` |
| `Period` | Số năm, tháng và ngày theo lịch | Days | `@PeriodUnit` |
| `DataSize` | Dung lượng dữ liệu | Bytes | `@DataSizeUnit` |

Ví dụ Duration:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

Ví dụ Period (mục đích khác):

~~~java
@PeriodUnit(ChronoUnit.WEEKS)
Period retentionPeriod;
~~~

Ví dụ DataSize:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
DataSize bufferSize;
~~~

Các annotation này không thay thế cho nhau. `@DurationUnit` không nhận `DataUnit` và không có nghĩa “đổi mọi loại đơn vị”.

### So sánh m trong Duration và Period

Trong Duration:

~~~text
3m = 3 phút
~~~

Trong cú pháp Period:

~~~text
3m = 3 tháng
~~~

Đây là lý do loại Java đích rất quan trọng. Một chuỗi có ký tự giống nhau không nhất thiết mang cùng ý nghĩa khi bind vào kiểu khác.

### Vì sao cần cẩn thận với Period?

Một tháng trên lịch không có một số giây cố định chung cho mọi trường hợp. Nếu yêu cầu nghiệp vụ là “giữ dữ liệu trong 3 tháng lịch”, dùng `Period` hoặc mô hình ngày tháng phù hợp thường tốt hơn việc tự chuyển thành `Duration.ofDays(90)`.

Ngược lại, “timeout 30 giây” rõ ràng thuộc kiểu `Duration`.

## 19. Tích hợp Duration vào API client có đơn vị riêng

Một số API Java nhận `Duration` trực tiếp:

~~~java
someClient.setTimeout(properties.requestTimeout());
~~~

Đoạn trên chỉ minh họa nếu thư viện có method phù hợp. Trong tình huống này, kiểu `Duration` giúp tránh việc chuyển sang `long` mơ hồ.

Nhưng nhiều API khác nhận số kèm đơn vị:

~~~java
long millis = properties.requestTimeout().toMillis();
~~~

Hoặc:

~~~java
long seconds = properties.requestTimeout().getSeconds();
~~~

**Tính đúng đơn vị phải được kiểm tra tại ranh giới API.** Nếu thư viện kỳ vọng milliseconds nhưng bạn truyền `getSeconds()`, timeout sẽ ngắn hơn 1.000 lần ở nhiều trường hợp.

### Vấn đề độ chính xác

Một `Duration` có thể nhỏ hơn 1 ms:

~~~properties
app.poll-interval=250us
~~~

Nếu dùng:

~~~java
Duration d = properties.pollInterval();
long ms = d.toMillis();
~~~

`d.toMillis()` có thể làm mất phần nhỏ hơn mili giây khi chuyển thành số nguyên. Tùy nhu cầu, nên giữ nguyên `Duration` hoặc dùng API hỗ trợ nanosecond/microsecond.

Một số thư viện giới hạn giá trị timeout ở mức tối thiểu hoặc tối đa. `@DurationUnit` không thay thế việc đọc hợp đồng của thư viện nhận giá trị.

## 20. Cấu hình thực tế: nhiều timeout với đơn vị khác nhau

Giả sử hệ thống phải xử lý các thao tác HTTP, retry và cache:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.runtime")
public record RuntimeProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration connectTimeout,

        @DurationUnit(ChronoUnit.SECONDS)
        Duration readTimeout,

        @DurationUnit(ChronoUnit.MILLISECONDS)
        Duration retryDelay,

        @DurationUnit(ChronoUnit.MINUTES)
        Duration cacheTtl) {
}
~~~

Nguồn:

~~~yaml
app:
  runtime:
    connect-timeout: 5
    read-timeout: 30
    retry-delay: 250
    cache-ttl: 10
~~~

Kết quả:

| Field | Số nguồn | Đơn vị mặc định | Giá trị |
| --- | ---: | --- | --- |
| `connectTimeout` | 5 | `SECONDS` | 5s |
| `readTimeout` | 30 | `SECONDS` | 30s |
| `retryDelay` | 250 | `MILLIS` | 250ms |
| `cacheTtl` | 10 | `MINUTES` | 10m |

Nếu người triển khai ghi rõ đơn vị:

~~~yaml
app:
  runtime:
    connect-timeout: 750ms
    read-timeout: 1m
    retry-delay: 2s
    cache-ttl: 1h
~~~

thì kết quả là:

| Field | Giá trị có hậu tố | Duration |
| --- | --- | --- |
| `connectTimeout` | `750ms` | 750ms |
| `readTimeout` | `1m` | 60s |
| `retryDelay` | `2s` | 2000ms |
| `cacheTtl` | `1h` | 60m |

Annotation là quy tắc dự phòng khi **không có hậu tố**, không phải giới hạn đơn vị được phép viết trong tệp.

## 21. Phân biệt annotation unit với việc đổi tên property

Hai việc có thể thay đổi độc lập:

~~~java
@ConfigurationProperties(prefix = "remote.client")
public record RemoteClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration connectTimeout) {
}
~~~

Tên khóa canonical:

~~~properties
remote.client.connect-timeout=30
~~~

- `remote.client`: prefix.
- `connectTimeout`: tên record component.
- `connect-timeout`: tên member trong cấu hình sau relaxed binding.
- `@DurationUnit(SECONDS)`: cách hiểu **giá trị `30`**.

Đổi `@DurationUnit` từ `SECONDS` sang `MILLIS` không đổi tên khóa; nó đổi cách diễn giải số trần.

Đổi prefix từ `remote.client` sang `remote.gateway` không tự đổi đơn vị; nó đổi nơi binder tìm giá trị.

Đổi tên member từ `connectTimeout` sang `connectionTimeout` không tự đổi đơn vị; nhưng có thể đổi tên khóa canonical cần cung cấp.

Đừng trộn cả ba loại thay đổi trong một lần sửa cấu hình khi chưa lập kế hoạch tương thích.

## 22. Chẩn đoán khi Duration khác mong đợi

Khi kết quả quá ngắn, quá dài hoặc giá trị không đúng, hãy kiểm tra theo thứ tự.

### Bước 1: xem giá trị nguồn có hậu tố không

~~~text
timeout=30
timeout=30s
timeout=30000ms
~~~

Ba biểu diễn không có cùng hành vi khi annotation unit thay đổi. Xác định chuỗi thực tế được binder nhận sau khi các nguồn được hợp nhất.

### Bước 2: xem field/parameter có @DurationUnit không

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

Nếu không có, số trần mặc định là ms trong binding Duration.

Nếu annotation nằm trên một class khác không dùng cho binding hiện tại, nó không có hiệu lực trong đường chuyển đổi ấy.

### Bước 3: xác định loại binding

- JavaBean field và setter.
- Constructor parameter.
- Record component.
- `@Bean @ConfigurationProperties` gắn vào instance mutable.
- Đọc trực tiếp `Environment.getProperty(..., Duration.class)`.
- `@Value`.

Không giả định metadata của annotation xuất hiện ở đường đọc không dùng properties binder.

### Bước 4: kiểm tra nguồn có ưu tiên cao hơn

Nếu file là `30s` nhưng CLI có `--app.timeout=10`, Binder có thể nhận số trần `10` từ CLI, sau đó áp dụng unit từ annotation.

### Bước 5: quan sát dưới dạng đơn vị tường minh

Trong ứng dụng thử nghiệm, với giá trị không nhạy cảm:

~~~java
Duration timeout = properties.timeout();

System.out.println("timeout ISO = " + timeout);
System.out.println("timeout ms  = " + timeout.toMillis());
System.out.println("timeout sec = " + timeout.getSeconds());
~~~

Dùng các phép quy đổi để biết rõ kết quả. Không chỉ dựa vào `Duration.toString()` mà suy ra rằng nguồn có hậu tố giống cách in.

### Bước 6: kiểm tra khi được đưa sang API khác

Nếu properties bean đúng 30 giây nhưng HTTP client vẫn timeout sau 30 ms, lỗi có thể nằm ở cách gọi API — ví dụ truyền `getSeconds()` vào một method yêu cầu milliseconds. `@DurationUnit` đã làm đúng nhiệm vụ ở tầng binding; lỗi xảy ra sau đó.

## 23. Những lỗi phổ biến

### Lỗi 1 — Nghĩ 30 luôn là 30 giây

~~~properties
app.timeout=30
~~~

Không có annotation unit, `Duration` có thể là 30 ms. Nếu muốn 30 giây, viết `30s` hoặc đặt `@DurationUnit(SECONDS)` ở đúng field/parameter.

### Lỗi 2 — Đặt @DurationUnit nhưng tưởng nó cấp giá trị mặc định

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

Nếu không có `app.timeout` thì annotation không có con số để chuyển đổi. Hãy xác định giá trị mặc định bằng field initializer, `@DefaultValue` hoặc cơ chế phù hợp với binding.

### Lỗi 3 — Tưởng annotation ghi đè hậu tố rõ ràng

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

~~~properties
app.timeout=500ms
~~~

Kết quả vẫn là 500 ms.

### Lỗi 4 — Dùng kiểu long và chờ @DurationUnit tự tạo Duration

~~~java
long timeout;
~~~

`@DurationUnit` được thiết kế để thay đơn vị khi chuyển sang **Duration**. Nếu chỉ dùng `long` thì bạn phải xác định đơn vị và chuyển sang `Duration` bằng logic phù hợp.

### Lỗi 5 — Đổi long seconds sang Duration nhưng quên annotation

Trước đây `timeoutSeconds=30` nghĩa là 30 giây. Sau khi đổi sang `Duration` mà không có `@DurationUnit(SECONDS)`, số trần `30` có thể nghĩa là 30 ms. Đây là lỗi migration điển hình.

### Lỗi 6 — Dùng nhầm hậu tố m

~~~properties
app.timeout=3m
~~~

Với `Duration`, giá trị là 3 **phút**, không phải 3 tháng.

### Lỗi 7 — Tưởng @Value tự lấy @DurationUnit trên class khác

Nếu service dùng `@Value("${app.timeout}")` trong khi một properties bean khác có annotation unit, đừng mặc định giá trị tiêm sẽ theo annotation của bean khác. Nên dùng properties bean nhất quán hoặc ghi hậu tố vào nguồn.

### Lỗi 8 — Không đăng ký @ConfigurationProperties

Một class chỉ có annotation `@ConfigurationProperties` chưa chắc đã là bean. Đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` trong ngữ cảnh thích hợp, nếu muốn Spring binder tạo bean cấu hình.

### Lỗi 9 — Dùng đơn vị của Duration cho DataSize hoặc Period

`@DurationUnit` không phải `@DataSizeUnit` hoặc `@PeriodUnit`. Một chữ `m` có nghĩa khác nhau tùy kiểu Java.

### Lỗi 10 — Không kiểm tra giới hạn nghiệp vụ

Binder có thể chuyển một số thời gian không hợp lý về mặt ứng dụng. Cần validation cho timeout dương, nhỏ hơn giới hạn tối đa và tương thích API sử dụng.

### Lỗi 11 — Hiểu nhầm toMillis() là giữ đủ độ chính xác

Nếu Duration có phần microsecond/nanosecond, chuyển sang số nguyên milliseconds có thể mất phần nhỏ. Giữ `Duration` đến ranh giới sử dụng khi có thể.

### Lỗi 12 — Đổi đơn vị default giữa các phiên bản mà không thông báo

Nếu ứng dụng có cấu hình trần `30000` mang nghĩa 30 giây theo mặc định ms, rồi code thêm `@DurationUnit(SECONDS)` nhưng giữ giá trị cũ, dữ liệu trở thành 30.000 giây. Thay đổi annotation phải đi kèm kế hoạch cập nhật hoặc bảo toàn ý nghĩa cấu hình.

## 24. Kiểm thử cách liên kết Duration

Một cách thực tế là tạo test Spring Boot với nguồn cấu hình dành riêng cho test.

Giả sử bean:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.timing")
public record TimingProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout,
        Duration interval) {
}
~~~

và ứng dụng đã bật `@ConfigurationPropertiesScan`.

### 24.1. Test giá trị trần

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "demo.timing.timeout=30",
        "demo.timing.interval=30"
})
class TimingBindingTest {

    @Autowired
    TimingProperties properties;

    @Test
    void distinguishesDefaultUnits() {
        assertEquals(
                Duration.ofSeconds(30),
                properties.timeout());

        assertEquals(
                Duration.ofMillis(30),
                properties.interval());
    }
}
~~~

Dù cùng giá trị nguồn `30`, hai field có đơn vị mặc định khác nhau.

### 24.2. Test suffix tường minh

Có thể tạo một lớp test khác:

~~~java
@SpringBootTest(properties = {
        "demo.timing.timeout=250ms",
        "demo.timing.interval=2s"
})
class ExplicitUnitBindingTest {

    @Autowired
    TimingProperties properties;

    @Test
    void explicitUnitsAreRespected() {
        assertEquals(
                Duration.ofMillis(250),
                properties.timeout());

        assertEquals(
                Duration.ofSeconds(2),
                properties.interval());
    }
}
~~~

Annotation unit của `timeout` không biến `250ms` thành 250 giây; `interval` không có annotation nhưng vẫn hiểu `2s` là hai giây.

### 24.3. Test mặc định khi thiếu khóa

Với constructor binding có `@DefaultValue("5s")`, thử không cung cấp khóa tương ứng và xác nhận kết quả là `Duration.ofSeconds(5)`. Đây là bài test **giá trị mặc định**, độc lập với test đơn vị mặc định của con số trần.

### 24.4. Test migration

Nếu hệ thống cũ có `timeout-seconds=60`, viết test đối chiếu:

~~~java
assertEquals(
        Duration.ofSeconds(60),
        properties.timeoutSeconds());
~~~

khi nguồn còn là số `60`. Test này phát hiện thay đổi đơn vị ngoài ý muốn lúc chuyển field từ `long` sang `Duration`.

## 25. Bài tập dự đoán giá trị

### Bài 1 — không có @DurationUnit

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(Duration timeout) {
}
~~~

~~~properties
service.timeout=1000
~~~

Hỏi `timeout` dài bao lâu?

**Đáp án:** 1.000 ms, tức 1 giây. `1000` là số trần và đơn vị mặc định của binding Duration là ms.

### Bài 2 — có @DurationUnit(SECONDS)

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

~~~properties
service.timeout=1000
~~~

**Đáp án:** 1.000 giây. Không còn là 1 giây, vì annotation quy định số trần dùng giây.

### Bài 3 — hậu tố thắng đơn vị default

Giữ `@DurationUnit(ChronoUnit.SECONDS)` nhưng dùng:

~~~properties
service.timeout=1000ms
~~~

**Đáp án:** 1 giây. Hậu tố `ms` là đơn vị tường minh.

### Bài 4 — ISO-8601

~~~properties
service.timeout=PT1M30S
~~~

**Đáp án:** 90 giây. Annotation không cần suy ra đơn vị từ một số trần.

### Bài 5 — hai Duration khác nhau

~~~java
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration executionTimeout,
        Duration pollInterval) {
}
~~~

~~~yaml
jobs:
  execution-timeout: 5
  poll-interval: 5
~~~

**Đáp án:** `executionTimeout` bằng 5 giây; `pollInterval` bằng 5 mili giây.

### Bài 6 — đổi nguồn qua CLI

YAML:

~~~yaml
jobs:
  execution-timeout: 15s
~~~

CLI:

~~~bash
java -jar app.jar --jobs.execution-timeout=20
~~~

Với `@DurationUnit(ChronoUnit.SECONDS)` trên member:

**Đáp án:** 20 giây theo nguồn CLI có ưu tiên cao hơn, rồi được binder hiểu đơn vị theo annotation.

### Bài 7 — thời gian trong YAML có hậu tố

~~~yaml
jobs:
  retry-delay: 500ms
  cache-ttl: 2h
  timeout: 30s
~~~

Với các field Duration tương ứng, lần lượt là 500 ms, 2 giờ, 30 giây, không cần annotation đơn vị để hiểu ba giá trị này.

### Bài 8 — phân biệt @DefaultValue và @DurationUnit

~~~java
public JobProperties(
        @DurationUnit(ChronoUnit.MINUTES)
        @DefaultValue("2m")
        Duration cacheTtl) {
    this.cacheTtl = cacheTtl;
}
~~~

Các trường hợp:

| Cấu hình | Kết quả |
| --- | --- |
| Không có khóa `cache-ttl` | 2 phút nhờ `@DefaultValue`. |
| `cache-ttl=10` | 10 phút nhờ `@DurationUnit(MINUTES)`. |
| `cache-ttl=30s` | 30 giây vì hậu tố tường minh. |
| `cache-ttl=PT1H` | 1 giờ theo ISO-8601. |

### Bài 9 — nhận diện lỗi migration

Dự án cũ dùng `long timeoutSeconds` với giá trị `30`; code cũ thực hiện `Duration.ofSeconds(timeoutSeconds)`. Sau đó đổi kiểu field thành `Duration` mà giữ nguyên `30`.

**Đáp án:** Nếu không thêm `@DurationUnit(SECONDS)` hoặc sửa nguồn thành `30s`, có nguy cơ thay đổi ý nghĩa từ 30 giây sang 30 mili giây.

### Bài 10 — phân biệt kiểu

Với cùng chuỗi `3m`:

- Bind vào `Duration`: 3 phút.
- Bind vào `Period` theo cú pháp đơn giản: 3 tháng.

**Đáp án:** không coi `3m` là một đơn vị chung độc lập với kiểu đích.

## 26. Hướng dẫn thiết kế cấu hình bền vững

Khi thiết kế module mới, có thể áp dụng các nguyên tắc:

### 26.1. Ưu tiên tên khóa mô tả nhiệm vụ

~~~yaml
http:
  client:
    connect-timeout: 5s
    read-timeout: 30s
~~~

Các tên `connect-timeout` và `read-timeout` nói rõ ý nghĩa nghiệp vụ. Phần `s` nói rõ đơn vị.

### 26.2. Ưu tiên giá trị có hậu tố trong dữ liệu mới

~~~yaml
jobs:
  retry-delay: 200ms
  execution-timeout: 2m
~~~

Tệp có thể được đọc và hiểu mà không cần mở mã Java để xem annotation.

### 26.3. Dùng @DurationUnit cho hợp đồng số trần

Khi nhiều hệ thống đang cung cấp `timeout=30` với nghĩa 30 giây, `@DurationUnit(SECONDS)` giúp bảo toàn ý nghĩa đó khi bind sang `Duration`.

### 26.4. Dùng default value riêng cho khóa thiếu

Nếu không cấu hình, application phải có timeout 10 giây, hãy khai báo giá trị mặc định có đơn vị rõ ràng thay vì hy vọng `@DurationUnit` tự tạo ra 10.

### 26.5. Kiểm tra chuyển kiểu và giá trị nghiệp vụ

Timeout không dương, lớn bất thường, hoặc không tương thích với API nên bị phát hiện bởi validation hoặc code kiểm tra lúc khởi tạo.

### 26.6. Giữ Duration đến gần ranh giới sử dụng nhất có thể

Nếu API nhận `Duration` thì truyền trực tiếp. Nếu API chỉ nhận số, chuyển sang đơn vị nó yêu cầu và kiểm tra nguy cơ mất độ chính xác/overflow.

### 26.7. Test cả số trần và số có hậu tố

Một test với `30` và một test với `500ms` là cách đơn giản để phát hiện sai khác ở `@DurationUnit`.

## 27. Bảng tổng kết

| Câu hỏi | Quy tắc |
| --- | --- |
| Số trần `30` gắn vào `Duration` mặc định là gì? | 30 mili giây. |
| `@DurationUnit(SECONDS)` đổi điều gì? | Số trần `30` của member tương ứng thành 30 giây. |
| `@DurationUnit` có làm `500ms` thành 500 giây? | Không. Hậu tố tường minh `ms` vẫn được tôn trọng. |
| `30s` và `PT30S` có cùng Duration? | Có, đều 30 giây khi bind đúng. |
| Thiếu khóa mà có `@DurationUnit(SECONDS)` có tự cho 30 giây? | Không; cần giá trị mặc định riêng. |
| Mặc định của JavaBean field và `@DefaultValue` có giống annotation đơn vị? | Không; chúng cung cấp **giá trị** khi khóa thiếu. |
| @DurationUnit có áp dụng cho mọi `Environment.getProperty(..., Duration.class)`? | Không tự mang metadata từ properties bean khác sang lời gọi độc lập. |
| `3m` của Duration là gì? | 3 phút, không phải 3 tháng. |
| Khi chuyển từ `long timeoutSeconds` sang `Duration` cần chú ý gì? | Giữ hợp đồng đơn vị giây bằng annotation hoặc cập nhật nguồn. |
| Có cần hậu tố trong file nếu đã dùng annotation? | Không bắt buộc, nhưng hậu tố làm file tự mô tả rõ hơn. |

## 28. Kết luận

Trong Spring Boot, **số thời gian không có hậu tố được bind vào `Duration` mặc định theo mili giây**. Annotation `@DurationUnit` thay đổi đơn vị mặc định **cho field hoặc constructor parameter tương ứng**, chẳng hạn từ mili giây sang giây hay phút. Khi giá trị nguồn đã ghi `500ms`, `30s`, `2m` hoặc `PT30S`, bản thân biểu thức đã có đơn vị rõ ràng và không cần annotation đoán thêm.

Quan trọng hơn, phải phân biệt:

1. **Đơn vị mặc định**: diễn giải số trần như `30` theo ms, s hay m.
2. **Giá trị mặc định**: dùng bao nhiêu khi **không có thuộc tính**.
3. **Giá trị có hiệu lực**: do `Environment` chọn giữa YAML, Properties, biến môi trường, System properties và CLI.
4. **Giá trị nghiệp vụ hợp lệ**: do validation và API tiêu thụ yêu cầu.

Với cấu hình mới, nên viết `30s` hoặc `500ms` để người đọc không phải đoán. Với cấu hình cũ mang số trần, `@DurationUnit` là công cụ hữu ích để bảo toàn đơn vị khi nâng cấp thiết kế sang kiểu `Duration`. Sau binding, hãy giữ `Duration` ở dạng có kiểu và chỉ chuyển về số khi API tiếp nhận đòi hỏi một đơn vị cụ thể.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration, phần Converting Durations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion).
- [Spring Boot — DurationUnit API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html).
- [Java — Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).
- [Java — ChronoUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoUnit.html).