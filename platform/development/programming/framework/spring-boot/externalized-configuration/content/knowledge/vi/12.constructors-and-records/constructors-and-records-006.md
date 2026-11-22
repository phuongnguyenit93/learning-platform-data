# Đối tượng lồng nhau khi toàn bộ nhóm thuộc tính vắng mặt

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Constructor và record

## 1. Bài toán: khi không có cả nhóm thuộc tính thì nested object ở đâu?

Spring Boot hỗ trợ bind cấu hình từ `Environment` thành Java object với `@ConfigurationProperties`. Khi cấu hình có nhiều cấp, một field của object cha có thể là **object lồng nhau** (nested object).

Ví dụ `application.yml`:

~~~yaml
client:
  endpoint: "https://api.example.test"
  retry:
    max-attempts: 3
    backoff: 200ms
~~~

Record Java:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        URI endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

Khi có `client.retry.max-attempts` và `client.retry.backoff`, Binder có dữ liệu để tạo `Retry`. Nhưng nếu một môi trường **không cung cấp bất kỳ property nào trong nhóm `client.retry.*`**:

~~~yaml
client:
  endpoint: "https://api.example.test"
  # Không có retry:
~~~

thì với **constructor binding** thông thường, field `retry` có thể trở thành **`null`**. Không nên giả định rằng Spring Boot luôn tạo `Retry` rỗng hoặc dùng mặc định 0 cho mọi field.

Có ba tình huống cần phân biệt:

1. **Cả nhóm nested vắng mặt:** không có property nào thuộc `client.retry.*` từ các nguồn có hiệu lực.
2. **Chỉ thiếu một số field:** có `client.retry.max-attempts` nhưng không có `client.retry.backoff`.
3. **Yêu cầu nested object mặc định:** constructor parameter/record component được cấu hình bằng empty `@DefaultValue`, hoặc một JavaBean có initializer phù hợp.

Trong ứng dụng thực, sự khác nhau này quyết định khả năng xảy ra `NullPointerException`, yêu cầu validation và hành vi mặc định.

### Mục tiêu học tập

- Hiểu tại sao nested constructor-bound property có thể là `null` khi cả nhóm vắng mặt.
- Sử dụng `@DefaultValue` **không có đối số** để tạo nested object trong trường hợp không có nhóm property.
- Đặt default cho từng field con, kể cả kiểu `Duration`, số nguyên và boolean.
- So sánh constructor/record binding với JavaBean binding có field initializer.
- Dùng `@NotNull`, `@Valid` và `@Validated` khi nested group là bắt buộc.
- Kiểm tra cấu hình đến từ các nguồn có ưu tiên khác nhau và test hành vi khi nhóm vắng mặt.

## 2. Cơ chế binding nested properties

`@ConfigurationProperties` không phải một YAML parser tùy ý trong code của service. Spring Boot đọc các nguồn cấu hình, giải quyết property theo precedence và dùng **Binder** ánh xạ các tên khóa vào field hoặc constructor parameter.

Ví dụ:

~~~yaml
mail:
  sender:
    address: "noreply@example.test"
    display-name: "My App"
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(Sender sender) {
    public record Sender(String address, String displayName) {}
}
~~~

Ánh xạ:

~~~text
mail.sender.address       -> sender.address()
mail.sender.display-name  -> sender.displayName()
~~~

Nếu không có bất kỳ `mail.sender.*` nào và không có default cho `sender`, Binder không nhất thiết tạo `Sender`. Với record constructor-bound, đối số `sender` có thể nhận `null`.

**Object YAML vắng mặt** không phải một cam kết rằng **Java object tương ứng luôn được tạo rỗng**.

### 2.1. Một nhóm có thể đến từ nhiều nguồn

Các thuộc tính có thể đến từ:

- `application.yml` hoặc `application.properties` trong classpath;
- file cấu hình ngoài JAR và `spring.config.import`;
- biến môi trường OS, Java system properties;
- `SPRING_APPLICATION_JSON`;
- tham số dòng lệnh;
- test property sources hoặc các nguồn tùy chỉnh.

Vì vậy, khái niệm “nhóm vắng mặt hoàn toàn” phải xét **toàn bộ dữ liệu mà Binder thấy**, không chỉ nội dung một file YAML. Một biến môi trường như `MAIL_SENDER_ADDRESS` có thể cung cấp giá trị dù file chính không chứa nhánh `sender`.

### 2.2. Record và constructor binding

Trong Spring Boot 3, record với một canonical constructor thông thường được hỗ trợ constructor binding mà không cần thêm `@ConstructorBinding`.

~~~java
@ConfigurationProperties(prefix = "sample")
public record SampleProperties(String name, Nested nested) {
    public record Nested(String label) {}
}
~~~

Record không có setter để Binder điền từng field sau khi đã tạo object. Binder cần chuẩn bị đối số constructor. Nếu thiếu cả nhóm nested, đối số tham chiếu có thể là `null`.

Cơ chế này **khác** việc Spring dependency-inject một bean loại `Nested` vào service. Đây là binding dữ liệu cấu hình, không phải tự động tìm một Spring bean cho mọi tham số của record.

## 3. Khi cả nhóm nested vắng mặt và không khai báo default

### 3.1. Ví dụ rõ ràng

`application.yml`:

~~~yaml
report:
  title: "Daily Report"
~~~

Record:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        String title,
        Export export
) {
    public record Export(String format, String directory) {}
}
~~~

Khi không có `report.export.format` và `report.export.directory` trong các nguồn:

~~~text
report.title   -> "Daily Report"
report.export  -> null
~~~

Code sau không an toàn nếu không có điều kiện bổ sung:

~~~java
public String exportFormat(ReportProperties config) {
    return config.export().format(); // Có thể NullPointerException.
}
~~~

Đây không phải một lỗi parse YAML. Code đang giả định object nested tồn tại, trong khi hợp đồng cấu hình chưa hề yêu cầu phải có nhóm đó.

### 3.2. Thiếu một field khác thiếu cả nhóm

Nếu chuyển thành:

~~~yaml
report:
  title: "Daily Report"
  export:
    format: "csv"
~~~

thì đã có `report.export.format`, nên Binder có cơ sở tạo object `Export`. Field `directory` là `String` không được cung cấp, nên có thể bằng `null` khi không có default/validation khác:

~~~text
report.export              -> Export(...)
report.export.format       -> "csv"
report.export.directory    -> null
~~~

Đừng đánh đồng “object không null” với “toàn bộ field đều đủ”.

### 3.3. Các kiểu primitive không làm object cha tự tồn tại

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(Queue queue) {
    public record Queue(int capacity, boolean enabled) {}
}
~~~

Khi cả `worker.queue.*` vắng, `queue` có thể là `null`. Không thể đọc `queue.capacity()` để nhận `0` nếu ngay cả `Queue` chưa được tạo.

Khi object `Queue` được tạo và field primitive thiếu, giá trị mặc định của primitive có thể là `0` hoặc `false`. Nhưng số 0 thường không có ý nghĩa như một default nghiệp vụ; cần khai báo rõ nếu muốn giá trị khác.

## 4. Empty `@DefaultValue`: yêu cầu tạo object nested khi cả nhóm thiếu

Spring Boot hỗ trợ `@DefaultValue` ở tham số constructor hoặc record component. Khi đặt annotation này **không có đối số** lên một tham số là nested object, bạn yêu cầu Binder tạo nested object ngay cả khi không có property nào cho nhóm đó.

Ví dụ Spring Boot 3, Java 17+:

~~~java
package com.example.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @DefaultValue Queue queue
) {
    public record Queue(
            @DefaultValue("10") int capacity,
            @DefaultValue("false") boolean enabled,
            @DefaultValue("250ms") Duration pollInterval
    ) {}
}
~~~

Một file `application.yml` hoàn toàn không có nhánh `worker` vẫn có thể cho bean `WorkerProperties` như sau:

~~~text
properties.queue()                -> không null
properties.queue().capacity()     -> 10
properties.queue().enabled()      -> false
properties.queue().pollInterval() -> PT0.25S (Duration 250 ms)
~~~

Đây là ví dụ **hai cấp default**:

1. `@DefaultValue Queue queue` không có string yêu cầu tạo `Queue`.
2. `@DefaultValue("10")` và các annotation có string trên field con cung cấp các giá trị mặc định khi không có property con tương ứng.

### 4.1. Phân biệt các dạng `@DefaultValue`

| Cách viết | Trên phần nào? | Ý nghĩa |
| --- | --- | --- |
| `@DefaultValue Queue queue` | Nested object | Tạo nested object khi không có property cho cả nhóm |
| `@DefaultValue("10") int capacity` | Scalar kiểu số | Dùng 10 nếu field chưa được cung cấp |
| `@DefaultValue("false") boolean enabled` | Boolean | Dùng false khi field chưa được cung cấp |
| `@DefaultValue("250ms") Duration pollInterval` | Thời lượng | Dùng thời lượng 250 ms qua conversion |

Annotation rỗng trên object **không tự sinh các giá trị có ý nghĩa** cho mọi field của object đó. Phải cấu hình default riêng nếu muốn các field được gán giá trị cụ thể.

### 4.2. Empty `@DefaultValue` nhưng các field con không có default

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DefaultValue Credentials credentials
) {
    public record Credentials(String username, String password) {}
}
~~~

Nếu không có `service.credentials.*`, object `Credentials` có thể vẫn được tạo, nhưng hai String chưa có dữ liệu có thể là `null`:

~~~text
service.credentials            -> object không null
service.credentials.username   -> null
service.credentials.password   -> null
~~~

**Tạo object ≠ có một cấu hình hợp lệ.** Nếu credential bắt buộc, nên dùng validation để báo lỗi sớm thay vì cố tạo một object trống.

### 4.3. Trường hợp nên dùng default nested

Những nhóm **tùy chọn nhưng có policy mặc định** phù hợp với kỹ thuật này: cache policy, retry policy, polling interval, tùy chọn UI hoặc log mức demo.

Nếu không có `worker.queue.*`, ứng dụng vẫn có chính sách `capacity=10`, `enabled=false` và `pollInterval=250ms`. Service dùng `properties.queue().capacity()` mà không phải tự viết fallback lặp ở nhiều nơi.

Ngược lại, một nhóm bắt buộc chứa endpoint hoặc secret thường nên **fail fast khi thiếu**, không âm thầm nhận một object rỗng.

## 5. Cây nested nhiều cấp

Cấu hình có thể gồm nhiều cấp:

~~~yaml
notifier:
  enabled: true
  channel:
    kind: "email"
  # Không có nhóm notifier.channel.retry
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "notifier")
public record NotifierProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue Channel channel
) {
    public record Channel(
            @DefaultValue("console") String kind,
            @DefaultValue Retry retry
    ) {}

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("1s") Duration backoff
    ) {}
}
~~~

Ở đây:

- `channel` có empty `@DefaultValue` và có thể được tạo dù không có `notifier.channel.*`.
- `retry` bên trong `Channel` cũng có empty `@DefaultValue` để không trở thành null khi cả nhóm retry thiếu.
- `kind` có default `console`, nhưng giá trị `email` trong YAML thắng default.
- `maxAttempts=3`, `backoff=1s` được dùng nếu không có nguồn nào cấp hai field.

Điểm đáng nhớ: **mỗi cấp nested có semantics vắng mặt riêng**. Nếu muốn object cấp dưới cũng tồn tại khi thiếu nhóm, phải xem xét default của **tham số tại chính cấp đó**.

### 5.1. Không buộc mọi nhóm optional có object mặc định

Giả sử notifier có cấu hình gửi SMS chỉ khi bật kênh SMS:

~~~java
@ConfigurationProperties(prefix = "notifier")
public record NotifierProperties(
        @DefaultValue Channel channel,
        Sms sms
) {
    public record Channel(@DefaultValue("console") String kind) {}
    public record Sms(String senderId, String providerUrl) {}
}
~~~

Không có `notifier.sms.*` thì `sms` có thể bằng `null`. Đó là semantics hợp lý nếu tính năng SMS thật sự không được cấu hình. Nhưng mọi code dùng SMS cần kiểm tra rằng cấu hình cần thiết có sẵn hoặc có validator phù hợp.

## 6. Constructor binding với class thường

Cơ chế empty `@DefaultValue` không chỉ dành cho record. Một class constructor-bound cũng có thể áp dụng:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "batch")
public class BatchProperties {

    private final Retry retry;

    public BatchProperties(@DefaultValue Retry retry) {
        this.retry = retry;
    }

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {
        private final int count;
        private final Duration delay;

        public Retry(
                @DefaultValue("3") int count,
                @DefaultValue("500ms") Duration delay) {
            this.count = count;
            this.delay = delay;
        }

        public int getCount() { return count; }
        public Duration getDelay() { return delay; }
    }
}
~~~

Với một constructor phù hợp, Spring Boot 3 có thể thực hiện constructor binding. Nếu class có nhiều constructor, việc chọn constructor và dùng `@ConstructorBinding` cần phù hợp phiên bản Boot. Record với một canonical constructor thường đơn giản hơn.

Không đặt `@Component` lên record constructor-bound rồi mong Spring DI biến các tham số thành property tùy ý. Đăng ký lớp cấu hình qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` để Spring Boot sử dụng đúng Binder.

## 7. JavaBean: initializer của nested field

JavaBean binding là cách khác. Class có constructor không tham số và getter/setter, trong đó nested field có thể được **khởi tạo ngay khi tạo object cha**.

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public class WorkerBeanProperties {

    private Queue queue = new Queue();

    public Queue getQueue() { return queue; }
    public void setQueue(Queue queue) { this.queue = queue; }

    public static class Queue {
        private int capacity = 10;
        private boolean enabled = false;
        private Duration pollInterval = Duration.ofMillis(250);

        public int getCapacity() { return capacity; }
        public void setCapacity(int capacity) {
            this.capacity = capacity;
        }
        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
        public Duration getPollInterval() { return pollInterval; }
        public void setPollInterval(Duration pollInterval) {
            this.pollInterval = pollInterval;
        }
    }
}
~~~

Khi không có `worker.queue.*`, initializer `new Queue()` vẫn chạy. Object `Queue` đã tồn tại với field defaults. Binder có thể cập nhật các field con nếu được cung cấp sau đó.

So sánh:

| Tiêu chí | Record/constructor binding | JavaBean binding |
| --- | --- | --- |
| Cách tạo nested object khi vắng nhóm | Empty `@DefaultValue` trên parameter | Khởi tạo field như `new Queue()` |
| Cấp giá trị cho field | Constructor arguments | Setter/JavaBean properties |
| Mutable sau khởi tạo | Record components không có setter | Có thể sửa qua setter |
| Default scalar | `@DefaultValue("...")` | Field initializer hoặc nguồn cấu hình |
| Mục đích chính | Mô hình có kiểu hướng bất biến | Mô hình mutable theo JavaBean conventions |

Nếu JavaBean khai báo `private Queue queue;` **mà không có initializer**, thì khi không có nhóm property, getter cũng có thể trả về `null`. Không phải hễ dùng JavaBean thì nested object luôn có mặt.

### 7.1. `@NestedConfigurationProperty` không phải công cụ tạo instance

`@NestedConfigurationProperty` là annotation phục vụ **configuration metadata** cho tooling. Nó không có nghĩa Binder buộc phải tạo nested object khi nhóm vắng mặt.

Khi muốn constructor-bound nested object có mặt, cách được đề cập trong bài là empty `@DefaultValue`. Khi dùng JavaBean, có thể dùng initializer của field.

## 8. Validation: nhóm bắt buộc hay tùy chọn?

Cần chọn một trong hai chính sách:

- **Optional với default:** không có nhóm retry thì tạo policy mặc định.
- **Required:** không có thông tin kết nối thì quá trình khởi động phải báo lỗi cấu hình.

Đừng dùng một object mặc định rỗng để che giấu trường hợp yêu cầu bắt buộc chưa được cấp dữ liệu.

### 8.1. Bật Bean Validation

Trong Spring Boot 3, thường thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Các annotation dùng package `jakarta.validation`. Class `@ConfigurationProperties` có thể dùng `@Validated` để yêu cầu validation trong quá trình binding.

### 8.2. Required nested object: `@NotNull` và `@Valid`

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @Valid @NotNull Gateway gateway
) {
    public record Gateway(
            @NotBlank String endpoint,
            @NotBlank String apiKey
    ) {}
}
~~~

Nếu toàn bộ `payment.gateway.*` vắng:

- Với constructor binding không có empty `@DefaultValue`, `gateway` có thể là `null`.
- `@NotNull` báo lỗi vì object bắt buộc không được cung cấp.
- `@Valid` yêu cầu validation đi vào nested object **khi có object**, giúp kiểm tra constraints của `endpoint` và `apiKey`.

Chỉ đặt `@Valid` không có nghĩa field null trở thành bắt buộc. Cần `@NotNull` hoặc constraint tương đương nếu muốn bác bỏ trường hợp cả object vắng.

Đối với thông tin nhạy cảm, không in `apiKey` qua log hoặc `toString()` của record.

### 8.3. Nested object được tạo mặc định nhưng vẫn phải hợp lệ

~~~java
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "task")
@Validated
public record TaskProperties(
        @Valid @DefaultValue Retry retry
) {
    public record Retry(
            @Min(1) @DefaultValue("3") int maxAttempts,
            @NotNull @DefaultValue("100ms") Duration backoff
    ) {}
}
~~~

Nếu cả `task.retry.*` vắng, `Retry` được tạo với 3 và 100ms; validation được áp dụng với `@Valid`.

Nếu deployment khai báo `task.retry.max-attempts=0`, giá trị `0` có thể được bind thay cho default 3, rồi `@Min(1)` phát hiện lỗi. Default **không làm mất hiệu lực các validation constraints**.

### 8.4. Default object không bảo đảm field không null

~~~java
@ConfigurationProperties(prefix = "security")
@Validated
public record SecurityProperties(
        @Valid @DefaultValue Credentials credentials
) {
    public record Credentials(
            @NotBlank String username,
            @NotBlank String password
    ) {}
}
~~~

Nếu không có `security.credentials.*`, object `Credentials` có thể được tạo, nhưng `username` và `password` vẫn thiếu. Validation có thể báo lỗi vì `@NotBlank`.

Trong hệ thống có credential bắt buộc, không nên gán password giả chỉ để ứng dụng startup thành công. Hãy lấy secret từ nguồn quản lý phù hợp và xác thực cấu hình lúc khởi động.

## 9. Optional nested object cần semantics rõ ràng

Giả sử cấu hình thông báo:

~~~java
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        boolean enabled,
        Smtp smtp
) {
    public record Smtp(String host, int port) {}
}
~~~

Khi `notifications.smtp.*` vắng, `smtp` có thể bằng `null`. Điều đó phù hợp nếu `enabled=false` nghĩa là ứng dụng không dùng SMTP. Nhưng khi bật tính năng, phải có dữ liệu SMTP:

~~~java
if (properties.enabled()) {
    NotificationProperties.Smtp smtp = properties.smtp();
    if (smtp == null) {
        throw new IllegalStateException(
                "SMTP phải được cấu hình khi notifications.enabled=true");
    }
    // Sử dụng smtp.host() và smtp.port().
}
~~~

Cách kiểm tra trong service là ví dụ cơ bản. Trong ứng dụng lớn, có thể dùng validation chéo hoặc cấu trúc config riêng để thông báo lỗi sớm và nhất quán.

### 9.1. Có nên dùng `Optional<Nested>`?

Java `Optional` là công cụ API cho sự hiện diện/vắng mặt. Nhưng đừng tự cho rằng Binder của Spring Boot coi mọi `Optional<Nested>` là `Optional.empty()` khi thiếu cấu hình. Spring Boot có lưu ý rằng `Optional` không nên được dùng tùy tiện cho `@ConfigurationProperties`: trường hợp vắng mặt có thể được bind là `null`.

Một nested field nullable kết hợp validation hoặc default rõ ràng thường dễ dự đoán và test hơn. Nếu thực sự cần dùng `Optional`, hãy kiểm tra behavior đúng phiên bản Boot đang sử dụng.

## 10. Default scalar và sự khác nhau giữa thiếu và sai

### 10.1. Default từ `application.yml`

~~~yaml
worker:
  queue:
    capacity: 10
    enabled: false
    poll-interval: 250ms
~~~

Nếu file này được nạp, các giá trị nested tồn tại và có thể override bằng nguồn ưu tiên cao hơn. Nhưng khi file không có trong một môi trường hoặc vị trí config data thay đổi, nhóm có thể vắng hoàn toàn. Default ở file không tự đảm bảo nested object sẽ tồn tại trong **mọi cách triển khai**.

### 10.2. Default trên constructor parameters

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(@DefaultValue Queue queue) {
    public record Queue(
            @DefaultValue("10") int capacity,
            @DefaultValue("false") boolean enabled
    ) {}
}
~~~

Mục tiêu là một hợp đồng fallback rõ ràng ngay trong kiểu Java. Nếu deployment cấp `worker.queue.capacity=25`, giá trị 25 thắng default 10.

### 10.3. Primitive defaults có thể gây hiểu nhầm

Nếu nested object được tạo nhưng không có default cụ thể, primitive components có thể nhận `0` hoặc `false`. Tuy nhiên:

- `max-attempts=0` có thể là cấu hình sai.
- `port=0` có thể mang ý nghĩa đặc biệt, không phải “cổng mặc định”.
- `timeout=0` có thể gây hành vi khác dự kiến.
- `enabled=false` có thể an toàn nhưng cần được lựa chọn có chủ đích.

Với policy thật, nên dùng `@DefaultValue` có ý nghĩa hoặc validation ràng buộc dải giá trị.

### 10.4. Property sai không tương đương property vắng

Ví dụ:

~~~properties
worker.queue.poll-interval=not-a-duration
~~~

Nếu field đích là `Duration`, đây có thể là lỗi conversion. Không nên trông chờ Binder bỏ qua chuỗi không hợp lệ và dùng `@DefaultValue("250ms")` thay thế. Default dành cho **giá trị không được cung cấp**, không phải cơ chế che dấu lỗi input.

## 11. Vắng nhóm trong toàn bộ Environment

Ví dụ `application.yml` không có `client.retry`:

~~~yaml
client:
  endpoint: "https://api.example.test"
~~~

Nhưng CLI có:

~~~bash
java -jar app.jar --client.retry.max-attempts=5
~~~

hoặc biến môi trường cung cấp tên tương ứng theo relaxed binding. Khi đó `client.retry` **không còn vắng hoàn toàn** theo dữ liệu mà Binder nhìn thấy. Dù file YAML không có nhánh này, nested object có thể được tạo từ field đã được cấp.

### 11.1. Override riêng một field

Default YAML:

~~~yaml
client:
  retry:
    max-attempts: 3
    backoff: 500ms
~~~

CLI:

~~~bash
java -jar app.jar --client.retry.max-attempts=6
~~~

Trong tình huống thông thường:

~~~text
client.retry.max-attempts = 6      (CLI)
client.retry.backoff      = 500ms  (YAML)
~~~

Binder có thể kết hợp dữ liệu nested theo từng property. Không mặc định rằng một key con ở nguồn ưu tiên cao xóa toàn bộ những key còn lại của object từ nguồn thấp.

### 11.2. Chuỗi rỗng và JSON null

Biến môi trường:

~~~bash
export CLIENT_RETRY_BACKOFF=''
~~~

không nhất thiết tương đương với việc hoàn toàn **không tồn tại property**. Binder có thể thấy một giá trị rỗng và thử chuyển kiểu hoặc xử lý theo converter hiện có.

Tương tự, JSON `null` có semantics riêng trong Spring Boot externalized configuration: không nên dùng nó như một cách chắc chắn để xóa giá trị từ nguồn ưu tiên thấp. Với một tính năng cần tắt, hãy dùng property như `enabled=false` thay vì trông chờ null semantics.

## 12. Collection bên trong nested object

Một nested object có mặt không bảo đảm List/Map ở bên trong được khởi tạo rỗng.

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @DefaultValue Rules rules
) {
    public record Rules(
            List<String> regions,
            Map<String, String> tags
    ) {}
}
~~~

Nếu `routing.rules.*` vắng, `Rules` có thể được tạo nhờ empty `@DefaultValue`, nhưng không thể mặc định rằng `regions` chắc chắn là `List.of()` và `tags` chắc chắn là `Map.of()`.

Nếu code cần collection không null, hãy thiết kế default/khởi tạo có kiểm soát và test Binder đúng phiên bản. Đừng giả định một annotation trên object cha tự sinh mọi collection con.

### 12.1. List và map có quy tắc ghi đè khác nhau

Giả sử một nguồn thấp khai báo:

~~~yaml
routing:
  rules:
    regions: ["a", "b"]
    tags:
      owner: "backend"
      region: "local"
~~~

Nguồn ưu tiên cao khai báo danh sách vùng `["c"]` và chỉ tag `region=apac`. Trong `@ConfigurationProperties`, list thường **được thay thế** bởi list từ nguồn cao, trong khi map có thể được hợp nhất theo từng entry (giữ `owner`, ghi đè `region`).

Đây là quy tắc collection binding, khác với chuyện object nested có được tạo khi cả nhóm vắng hay không.

## 13. Đăng ký properties bean đúng cách

Một record có `@ConfigurationProperties` chưa đủ để được Spring tạo thành bean nếu ứng dụng chưa đăng ký nó.

Cách 1, scan:

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

Cách 2, enable tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WorkerProperties.class)
class WorkerConfig {}
~~~

Không cần cả hai cách cho cùng một class. Với constructor-bound record, hãy chọn phương án phù hợp và bảo đảm package scan bao gồm properties class.

**Hai câu hỏi độc lập:**

- Bean `WorkerProperties` đã được đăng ký chưa?
- Field `queue` trong bean đó sẽ null hay có default nếu `worker.queue.*` vắng?

Thêm `@DefaultValue` không giải quyết được vấn đề class chưa được đăng ký; ngược lại, đăng ký bean cũng không bảo đảm nested field tự hiện diện.

## 14. Ví dụ ứng dụng thực: HTTP client có retry mặc định

Giả sử mỗi HTTP client bắt buộc có base URL, nhưng có thể bỏ qua toàn bộ nhóm retry để nhận policy mặc định.

~~~java
package com.example.http;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "outbound.http")
@Validated
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @Valid @DefaultValue Retry retry
) {
    public record Retry(
            @Min(1) @DefaultValue("3") int maxAttempts,
            @NotNull @DefaultValue("200ms") Duration delay
    ) {}
}
~~~

Cấu hình tối thiểu:

~~~yaml
outbound:
  http:
    base-url: "https://partner.example.test"
~~~

Kết quả mong đợi:

~~~text
baseUrl            = https://partner.example.test
retry              = object không null
retry.maxAttempts  = 3
retry.delay        = 200ms
~~~

Nếu staging đặt:

~~~properties
outbound.http.retry.max-attempts=5
~~~

thì `maxAttempts` được override thành 5, còn `delay` tiếp tục dùng 200ms.

Nếu production đặt `outbound.http.retry.max-attempts=0`, `@Min(1)` giúp báo lỗi cấu hình thay vì để một policy không hợp lệ đến service runtime. Đây là ví dụ điển hình của việc kết hợp **default cho nhóm tùy chọn** và **validation cho field đã được cấu hình**.

## 15. Kiểm thử trường hợp nhóm nested vắng mặt

Khi một service dựa vào null/default của nested object, nên có test binding cho ba tình huống: nhóm hoàn toàn vắng, nhóm chỉ có một property và nhóm đầy đủ.

### 15.1. `ApplicationContextRunner`

Với Spring Boot test, có thể tạo context nhỏ không cần khởi chạy web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    @Test
    void absentQueueGroupUsesDefaults() {
        runner.run(context -> {
            WorkerProperties props =
                    context.getBean(WorkerProperties.class);

            assertThat(props.queue()).isNotNull();
            assertThat(props.queue().capacity()).isEqualTo(10);
            assertThat(props.queue().enabled()).isFalse();
        });
    }

    @Test
    void partialGroupOverridesOnlyProvidedField() {
        runner.withPropertyValues("worker.queue.capacity=25")
                .run(context -> {
                    WorkerProperties props =
                            context.getBean(WorkerProperties.class);

                    assertThat(props.queue().capacity()).isEqualTo(25);
                    assertThat(props.queue().enabled()).isFalse();
                });
    }
}
~~~

Test sử dụng `WorkerProperties` từ mục 4. Nó kiểm tra kết quả **sau binding**, thay vì đoán cơ chế từ cú pháp YAML. Khi cần test nạp file `application.yml` thật, dùng kiểu test có config data loading phù hợp.

### 15.2. Test trường hợp không có default

~~~java
@ConfigurationProperties(prefix = "plain")
public record PlainProperties(Nested nested) {
    public record Nested(String label) {}
}
~~~

Khi context không có `plain.nested.*` và không có default trên `nested`, kết quả constructor binding thường là:

~~~text
plainProperties.nested() == null
~~~

Nếu ứng dụng chọn chính sách “nhóm optional”, đây là behavior cần được kiểm tra bằng test và xử lý ở nơi sử dụng. Nếu muốn không-null, thay đổi hợp đồng cấu hình thay vì rải các null checks không nhất quán trong nhiều service.

### 15.3. Test required group

Với `PaymentProperties` có `@NotNull Gateway gateway`, khởi tạo context không cấp `payment.gateway.*` và xác nhận ứng dụng báo lỗi binding/validation khi hạ tầng validation có sẵn.

Đừng ràng buộc test vào đúng một đoạn text của exception; tên exception hoặc định dạng thông báo có thể thay đổi theo phiên bản framework. Kiểm tra rằng context không khởi động bình thường với cấu hình bắt buộc bị thiếu.

## 16. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `properties.retry()` là null | Cả nhóm `retry` vắng và không có empty `@DefaultValue` | Xác định optional/required; thêm default hoặc validation |
| Retry object tồn tại nhưng field null | Annotation rỗng chỉ tạo object, field chưa có default | Thêm default riêng hoặc validation |
| `NullPointerException` ở service | Code giả định nested field luôn có mặt | Thiết kế hợp đồng cấu hình hoặc xử lý null rõ |
| Test thấy nested khác dự đoán | Test có property từ env/profile/nguồn khác | Dùng context cô lập và đọc nguồn thực tế |
| `@NotNull` không phát hiện thiếu nhóm | Chưa có validation đúng cách, bean chưa được bind | Kiểm tra `@Validated`, starter validation, registration |
| Constraint của field nested không chạy | Thiếu cascade `@Valid` | Đặt `@Valid` trên nested component |
| Primitive field nhận 0 | Không có default cho field đang được tạo | Dùng `@DefaultValue("...")` và validation |
| `@NestedConfigurationProperty` không tạo object | Annotation dùng cho metadata | Dùng empty `@DefaultValue` hoặc initializer |
| Không inject được properties class | Chưa scan/enable đúng | `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| YAML không có nhóm nhưng object vẫn tồn tại | Source khác cung cấp key hoặc có default | Xem toàn bộ `Environment` và precedence |
| List/map con không như dự đoán | Collection có semantics binder riêng | Xem source priority và test collection binding |
| Thiếu credential nhưng app vẫn chạy | Nhóm bắt buộc chưa validation | Thêm constraints và cung cấp secret an toàn |

### 16.1. Quan sát một property không nhạy cảm

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    public ConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        String key = "worker.queue.capacity";
        System.out.println(key + " = " + environment.getProperty(key));
    }
}
~~~

Chỉ dùng khóa demo để chẩn đoán. Không log password, token hoặc object cấu hình có chứa secret; nếu dùng Actuator `env`/`configprops`, cần bảo vệ endpoint và che giấu dữ liệu nhạy cảm.

### 16.2. Quy trình kiểm tra khi nested object bất ngờ null

1. Xem class có được bind theo `@ConfigurationProperties` và được scan/enable không.
2. Xem prefix, tên field và relaxed binding có đúng không.
3. Xác định có **bất kỳ** property phù hợp nào cho nhóm nested trong mọi nguồn không.
4. Kiểm tra tham số constructor/record component nested có empty `@DefaultValue` không.
5. Kiểm tra các default của field con, nhất là kiểu tham chiếu, `Duration`, list và map.
6. Kiểm tra validation: `@Validated`, `@Valid`, `@NotNull` và constraint con.
7. Nếu kết quả khác môi trường khác, xem profile, import, biến môi trường, CLI và test property.
8. Viết test binding để cố định semantics mà ứng dụng thực sự cần.

## 17. Bài tập thực hành

### Bài tập A — Nhóm không có default

Định nghĩa:

~~~java
@ConfigurationProperties(prefix = "lesson")
public record LessonProperties(Info info) {
    public record Info(String title, String author) {}
}
~~~

Chạy khi không có `lesson.info.*`; quan sát `info`. Sau đó thêm `lesson.info.title=Hello` và quan sát object nested cùng field `author`.

### Bài tập B — Empty `@DefaultValue`

Đổi `Info info` thành `@DefaultValue Info info`, đặt `@DefaultValue("Untitled") String title` và `@DefaultValue("Unknown") String author`. Chạy không có property nào thuộc `lesson.info.*`. Dự đoán object và các field.

### Bài tập C — Override một phần

Cung cấp `lesson.info.title=Spring Boot` nhưng không cấp `lesson.info.author`. Với class đã có default ở bài B, dự đoán tên và tác giả cuối cùng, giải thích vì sao chỉ một field bị override.

### Bài tập D — Nhóm bắt buộc

Tạo `DatabaseProperties` có nested `Credentials` bắt buộc, với `@NotNull` và `@Valid`. Khi thiếu cả nhóm, ứng dụng phải báo lỗi. Khi chỉ có username, dùng `@NotBlank` trên password để phát hiện thiếu field.

### Bài tập E — Record so với JavaBean

Viết hai kiểu `CacheProperties`: record dùng empty `@DefaultValue` trên nested `Policy` và JavaBean dùng field `private Policy policy = new Policy()`. Test khi nhóm policy vắng, rồi test khi chỉ có một field được cấp.

### Bài tập F — Nguồn cấu hình khác

Bỏ nhóm `lesson.info` khỏi YAML nhưng chạy `--lesson.info.title=FromCLI`. Giải thích tại sao nested object có thể được tạo dù file chính không có nhánh `info`. Thử thêm biến môi trường và kiểm tra precedence.

## 18. Ghi nhớ

- **Constructor-bound `@ConfigurationProperties` / record:** nếu toàn bộ nhóm nested vắng mặt và không có default, nested object có thể là **`null`**.
- **Empty `@DefaultValue`** trên nested parameter/record component yêu cầu tạo object dù không có property thuộc cả nhóm.
- **Scalar `@DefaultValue("...")`** trên field con cung cấp giá trị mặc định; tạo object không có nghĩa field con luôn đầy đủ.
- **Validation:** dùng `@NotNull` nếu nested object bắt buộc, `@Valid` để kiểm tra sâu và `@Validated` cùng validator để thực thi constraints.
- **JavaBean initializer** như `new Retry()` có thể tạo nested object mặc định nhưng có lifecycle binding khác record.
- **Tổng thể nguồn cấu hình:** nhóm không có trong YAML vẫn có thể hiện diện do CLI, env var, config import hoặc property source khác.
- **Thiết kế rõ ý nghĩa:** nhóm tùy chọn nên có default/null semantics nhất quán; nhóm bắt buộc nên từ chối startup nếu thiếu.

## Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding object cấu hình có kiểu.
- [Spring Boot Reference — Constructor Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding): constructor/record binding và empty `@DefaultValue` cho nested group vắng mặt.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, `@Valid` và constraints trên nested properties.
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding): ánh xạ tên property từ các nguồn.
- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): vai trò metadata của `@NestedConfigurationProperty`.
