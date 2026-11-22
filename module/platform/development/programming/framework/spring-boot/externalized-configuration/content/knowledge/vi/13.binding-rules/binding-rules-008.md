# Giá trị mặc định của kiểu nguyên thủy và rủi ro che giấu cấu hình thiếu

Spring Boot hỗ trợ liên kết (*binding*) các thuộc tính từ `application.yml`, `application.properties`, biến môi trường, tham số dòng lệnh và các nguồn khác vào đối tượng Java thông qua `@ConfigurationProperties`. Khi khai báo kiểu dữ liệu, chúng ta thường chọn `int`, `long` hoặc `boolean` vì ngắn gọn và quen thuộc.

Tuy nhiên, kiểu nguyên thủy (*primitive*) của Java có một đặc điểm dễ bị bỏ qua: **nó không biểu diễn được trạng thái `null`**. Khi thuộc tính không được cung cấp, đối tượng cấu hình có thể nhận những giá trị mặc định của kiểu nguyên thủy như `0` hoặc `false`. Nếu các giá trị ấy vẫn có vẻ hợp lệ đối với mã ứng dụng, cấu hình thiếu có thể bị **che giấu** thay vì được phát hiện sớm.

Ví dụ:

- Thiếu `app.email.enabled` có thể khiến tính năng bị hiểu là **tắt** (`false`), dù người vận hành quên cấu hình.
- Thiếu `app.batch.max-items` có thể tạo `0`, khiến một batch không xử lý phần tử nào.
- Thiếu `app.client.connect-timeout-ms` có thể tạo `0`; tùy thư viện, giá trị này có thể mang ý nghĩa không chờ, chờ vô hạn hoặc không hợp lệ.
- Thiếu `app.worker.concurrency` có thể trở thành `0` và chỉ gây lỗi muộn khi tạo thread pool.

Bài học sử dụng Spring Boot 3.3.x và Java 21. Trọng tâm là **phân biệt thuộc tính thiếu với thuộc tính được cấp một giá trị thực sự**, lựa chọn kiểu Java thích hợp, khai báo mặc định có chủ đích và dùng validation để ứng dụng *fail fast* khi cấu hình bắt buộc không tồn tại.

## 1. Nhắc lại: binding từ nguồn cấu hình vào Java

Giả sử file `src/main/resources/application.yml` có:

~~~yaml
app:
  worker:
    enabled: true
    concurrency: 4
    retry-count: 3
~~~

Một record cấu hình tương ứng:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        boolean enabled,
        int concurrency,
        int retryCount) {
}
~~~

Spring Boot Binder tìm các thuộc tính dưới tiền tố `app.worker` rồi chuyển thành đối số của constructor record:

~~~text
app.worker.enabled       → enabled       → boolean
app.worker.concurrency   → concurrency   → int
app.worker.retry-count   → retryCount    → int
~~~

Trong tình huống có đủ ba thuộc tính, object nhận:

~~~text
enabled = true
concurrency = 4
retryCount = 3
~~~

Nhưng nếu file chỉ có:

~~~yaml
app:
  worker:
    enabled: true
~~~

hai thuộc tính `concurrency` và `retry-count` không được cung cấp. Với component primitive của đối tượng đã được bind, các giá trị thiếu có thể biểu hiện như:

~~~text
enabled = true
concurrency = 0
retryCount = 0
~~~

**Vấn đề:** đây không phải là những giá trị được người vận hành chủ động chọn. Chúng xuất phát từ tính chất mặc định của kiểu Java trong quá trình tạo object.

## 2. Những giá trị mặc định của primitive trong Java

Các kiểu nguyên thủy không có `null`. Khi một **field** Java không được khởi tạo tường minh, Java sử dụng giá trị mặc định:

| Primitive | Giá trị mặc định của field |
| --- | --- |
| `boolean` | `false` |
| `byte` | `0` |
| `short` | `0` |
| `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | ký tự NUL `'\u0000'` |

Lưu ý chính xác về Java: biến cục bộ bên trong phương thức **không tự được gán mặc định** trước khi sử dụng; trình biên dịch yêu cầu definite assignment. Bảng trên nói về field/array component hoặc kết quả mặc định primitive khi framework tạo đối tượng cấu hình, **không** phải mọi biến Java trong mọi ngữ cảnh.

Ví dụ với JavaBean:

~~~java
public class WorkerSettings {

    private int concurrency;
    private boolean enabled;

    public int getConcurrency() {
        return concurrency;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

Nếu đối tượng được tạo bằng `new WorkerSettings()` mà không có lệnh gán khác:

~~~text
concurrency = 0
enabled = false
~~~

Trong Spring Boot, nếu một property không được bind vào field tương ứng của JavaBean, giá trị ban đầu của field có thể được giữ nguyên. Với constructor/record binding, Binder có cơ chế tạo đối số constructor; kết quả thiếu đối với primitive tương ứng thường là giá trị primitive mặc định.

### Vì sao số 0 và false nguy hiểm trong cấu hình?

Cả `0` lẫn `false` đều là giá trị Java hợp lệ. Java không thể biết người dùng **đã cấu hình `0`/`false`** hay **quên cấu hình** chỉ từ giá trị primitive đã được tạo.

~~~text
Trường hợp A: app.worker.concurrency=0
Trường hợp B: không có app.worker.concurrency

Object primitive cuối cùng:
concurrency == 0
~~~

Nếu mã chỉ kiểm tra `concurrency == 0`, nó không còn dữ liệu để phân biệt hai tình huống.

## 3. Ví dụ cấu hình thiếu dẫn đến hành vi sai

Xét một dịch vụ xử lý đơn hàng:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        boolean processingEnabled,
        int maxBatchSize) {
}
~~~

Một service:

~~~java
package com.example.orders.service;

import com.example.orders.config.OrdersProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderBatchService {

    private final OrdersProperties properties;

    public OrderBatchService(OrdersProperties properties) {
        this.properties = properties;
    }

    public void process() {
        if (!properties.processingEnabled()) {
            System.out.println("Processing is disabled");
            return;
        }

        for (int i = 0; i < properties.maxBatchSize(); i++) {
            // Xử lý một đơn hàng
        }
    }
}
~~~

Nếu người vận hành quên khai báo toàn bộ `app.orders`, đối tượng cấu hình có thể có:

~~~text
processingEnabled = false
maxBatchSize = 0
~~~

Ứng dụng có thể khởi động bình thường và in `Processing is disabled`. Đây là lỗi **âm thầm** nếu yêu cầu nghiệp vụ bắt buộc người triển khai phải xác định rõ có xử lý đơn hàng hay không.

Nếu sau đó người vận hành bật `processing-enabled=true` nhưng vẫn thiếu `max-batch-size`, vòng lặp chạy 0 lần. Không có exception Java nào bắt buộc phải xuất hiện trong ví dụ này.

**Bài học:** sự thành công của quá trình binding không chứng minh rằng cấu hình đầu vào đầy đủ và hợp lệ về nghiệp vụ.

## 4. Primitive khác wrapper như thế nào?

Java có các lớp bao (*wrapper type*):

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `int` | `Integer` |
| `long` | `Long` |
| `double` | `Double` |
| `float` | `Float` |

Wrapper là kiểu tham chiếu (*reference type*) nên có thể chứa `null`. Khi một property không được cung cấp và không có mặc định hay cơ chế cấp giá trị khác, một component wrapper có thể nhận `null`.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        Boolean processingEnabled,
        Integer maxBatchSize) {
}
~~~

Với cấu hình thiếu, ta có thể quan sát:

~~~text
processingEnabled = null
maxBatchSize = null
~~~

Điều này **chưa tự gây lỗi**: mã vẫn phải sử dụng hoặc validate giá trị. Nhưng nó tạo ra cách biểu diễn khác nhau cho hai trạng thái:

~~~text
null   → chưa được cấu hình
false  → đã được cấu hình là tắt
0      → đã được cấu hình là 0
~~~

Khi ứng dụng **cần phân biệt thiếu và giá trị hợp lệ**, wrapper thường phù hợp hơn primitive.

### Đừng tự động unbox wrapper thiếu

Ví dụ:

~~~java
Boolean enabled = properties.processingEnabled();

if (enabled) {  // Có thể NullPointerException khi enabled == null.
    // ...
}
~~~

Vì `if` cần `boolean`, Java phải unbox `Boolean`. Nếu giá trị là `null`, phát sinh `NullPointerException`.

Giải pháp không phải luôn dùng primitive. Nếu property là bắt buộc, hãy **validate nó ngay khi tạo configuration properties bean** để lỗi xuất hiện trước khi service sử dụng.

## 5. Dùng @NotNull để yêu cầu thuộc tính phải được cung cấp

Spring Boot hỗ trợ Bean Validation trên `@ConfigurationProperties` khi có Bean Validation provider. Trong các dự án Spring Boot thông thường, có thể thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Tạo cấu hình:

~~~java
package com.example.orders.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer maxBatchSize) {
}
~~~

Ý nghĩa:

- `@Validated` yêu cầu validation khi Spring Boot bind bean cấu hình.
- `@NotNull Boolean processingEnabled`: người triển khai phải cung cấp giá trị `true` hoặc `false`; thiếu dẫn đến lỗi validation.
- `@NotNull Integer maxBatchSize`: không chấp nhận thiếu.
- `@Min(1) Integer maxBatchSize`: giá trị phải từ 1 trở lên.

Với file:

~~~yaml
app:
  orders:
    processing-enabled: false
    max-batch-size: 10
~~~

Cả hai giá trị hợp lệ: `false` là một lựa chọn tường minh, và `10` thỏa `@Min(1)`.

Nhưng nếu chỉ có:

~~~yaml
app:
  orders:
    processing-enabled: false
~~~

`maxBatchSize` thiếu. Khi Bean Validation được bật và configuration properties bean được tạo, ứng dụng có thể dừng khởi động với thông báo lỗi binding/validation liên quan `app.orders.max-batch-size`.

### Vì sao không chỉ dùng @NotNull trên primitive?

Đoạn sau không bắt được sự khác biệt giữa “thiếu” và “giá trị false”:

~~~java
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull boolean processingEnabled) {
}
~~~

`boolean` không bao giờ là `null`. Vì vậy, `@NotNull` không mang lại cơ chế phát hiện thuộc tính boolean bị thiếu.

Tương tự:

~~~java
@NotNull int maxBatchSize
~~~

không phát hiện trạng thái thiếu chỉ thông qua null. Nếu muốn yêu cầu người vận hành **phải chỉ định một số**, dùng `Integer` + `@NotNull`. Nếu muốn số luôn lớn hơn 0 nhưng không cần phân biệt thiếu/0, `@Min(1) int` có thể bắt giá trị 0, tuy nhiên cách này vẫn không cho biết riêng nguyên nhân “thiếu property” hay “cố ý đặt 0”.

## 6. @Min và @Positive có thay thế @NotNull không?

Không hoàn toàn. Đây là các loại ràng buộc khác nhau:

- `@NotNull`: giá trị phải tồn tại.
- `@Min(1)`: một số phải lớn hơn hoặc bằng 1.
- `@Positive`: một số phải lớn hơn 0.
- `@Max(100)`: một số không được lớn hơn 100.
- `@NotBlank`: chuỗi không được null, trống hoặc toàn khoảng trắng.

Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Min(1) @Max(64) Integer concurrency) {
}
~~~

Đối với `Integer`:

~~~text
Thiếu property  → null → vi phạm @NotNull
Có giá trị 0    → 0    → vi phạm @Min(1)
Có giá trị 100  → 100  → vi phạm @Max(64)
Có giá trị 8    → 8    → hợp lệ
~~~

Phân biệt lỗi thiếu với sai miền giá trị giúp log và hướng dẫn vận hành rõ ràng hơn.

Một số Bean Validation constraint như `@Min` thường cho phép `null` đi qua vì việc yêu cầu có giá trị là trách nhiệm của `@NotNull`. Do đó, chỉ viết `@Min(1) Integer concurrency` mà bỏ `@NotNull` không nên được xem là cơ chế bảo đảm property phải được khai báo.

### Nếu số 0 là giá trị hợp lệ?

Ví dụ một số API cho phép timeout 0 mang ý nghĩa đặc biệt; hoặc `server.port=0` trong ứng dụng web là yêu cầu gán cổng ngẫu nhiên. Không nên gắn `@Min(1)` theo thói quen vào mọi số nguyên.

Khi `0` là giá trị hợp lệ nhưng người dùng **phải khai báo rõ**, dùng wrapper với `@NotNull`:

~~~java
@NotNull Integer port
~~~

Sau đó thêm các constraint khác đúng với yêu cầu nghiệp vụ. Kiểu `Integer` cho phép xác định có hay không có property; `@Min(1)` sẽ loại bỏ `0`, vì vậy không phù hợp nếu 0 là trường hợp hợp lệ.

## 7. Boolean: false có thể là giá trị nghiệp vụ, không phải lỗi

Giả sử phải chọn một chế độ xử lý:

~~~yaml
app:
  settlement:
    enabled: false
~~~

`false` được người vận hành đặt chủ động, ví dụ để tạm dừng thanh toán. Không có lý do mặc định coi nó sai.

Nhưng nếu hoàn toàn không có `app.settlement.enabled`, nhận `false` từ kiểu primitive sẽ không cho biết việc tắt là **chủ đích** hay **sai sót**.

Hai hợp đồng khác nhau:

**Chế độ A — Tính năng tùy chọn, mặc định tắt**

~~~java
@ConfigurationProperties(prefix = "app.settlement")
public record SettlementProperties(
        @DefaultValue("false") boolean enabled) {
}
~~~

Đây là một default rõ ràng trong thiết kế: khi thiếu property, ứng dụng được phép tắt tính năng.

**Chế độ B — Bắt buộc quyết định tường minh**

~~~java
@Validated
@ConfigurationProperties(prefix = "app.settlement")
public record SettlementProperties(
        @NotNull Boolean enabled) {
}
~~~

Trong chế độ B, thiếu property là lỗi cấu hình, nhưng giá trị `true` hoặc `false` đều hợp lệ khi được cấp.

Không có lựa chọn nào luôn tốt hơn. Quyết định phụ thuộc hợp đồng vận hành: **thiếu cấu hình là tình huống hợp lệ hay phải báo lỗi?**

## 8. @DefaultValue: khai báo giá trị mặc định có chủ đích

Spring Boot có annotation:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
~~~

Với constructor binding/record, có thể ghi:

~~~java
package com.example.worker.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int concurrency,
        @DefaultValue("3") int retryCount) {
}
~~~

Nếu không có property tương ứng, Binder sử dụng `true`, `4`, `3` thay cho giá trị primitive không có ý nghĩa nghiệp vụ như `0` hoặc `false`.

Tác dụng:

- Đọc record thấy ngay default mà ứng dụng chấp nhận.
- Người vận hành vẫn có thể ghi đè qua YAML, biến môi trường hoặc CLI.
- Dễ phân biệt **default đã thiết kế** với **giá trị 0/false xuất hiện ngầm**.

Tuy nhiên, `@DefaultValue` chỉ phù hợp khi việc thiếu thuộc tính **được phép**. Nếu cấu hình bắt buộc phải có, đừng thêm default chỉ để tránh lỗi.

### @DefaultValue hoạt động khi không có property

Ví dụ:

~~~java
@DefaultValue("4") int concurrency
~~~

Với:

~~~yaml
app:
  worker:
    concurrency: 8
~~~

giá trị là `8`, không phải `4`. Mặc định chỉ có vai trò khi Binder **không tìm được** property tương ứng.

### Giá trị trống không đồng nghĩa với thiếu

Nếu nguồn cấu hình có:

~~~properties
app.worker.concurrency=
~~~

đây là một property có mặt với chuỗi rỗng; không nên mặc nhiên kỳ vọng `@DefaultValue("4")` được kích hoạt. Kết quả sẽ tùy thuộc conversion, kiểu đích và cách Binder xử lý giá trị rỗng; có thể phát sinh lỗi hoặc giá trị không mong muốn.

Quy tắc đáng nhớ: **fallback khi không tìm thấy property không giống fallback khi property tồn tại nhưng rỗng, sai kiểu hoặc sai nghiệp vụ**.

## 9. So sánh default Java, @DefaultValue và default trong YAML

Ba cách đều có thể ảnh hưởng giá trị cuối cùng, nhưng nằm ở các tầng khác nhau.

### 9.1. Default ngầm của primitive

~~~java
private int concurrency;
~~~

Nếu đây là field không được gán, Java để `0`. Nó không diễn đạt ý nghĩa “0 là mức song song mặc định của ứng dụng”.

### 9.2. Default tường minh ở field JavaBean

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int concurrency = 4;
    private boolean enabled = true;

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Khi dùng JavaBean binding, giá trị field được khởi tạo và có thể được giữ lại nếu Binder không cấp property. Khi property tồn tại, setter có thể ghi đè nó.

### 9.3. Default tường minh trong constructor binding

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

Đây là phương án gọn gàng với record.

### 9.4. Default ở file cấu hình

~~~yaml
app:
  worker:
    concurrency: 4
    enabled: true
~~~

Giá trị thuộc `Environment` và tham gia thứ tự ưu tiên. File theo profile, biến môi trường hoặc CLI có thể ghi đè chúng.

| Cách | Nơi khai báo | Khi property thiếu | Có thể ghi đè bằng property bên ngoài? |
| --- | --- | --- | --- |
| Primitive ngầm | Bản chất Java | `0`/`false` | Có |
| JavaBean field initializer | Class JavaBean | Giữ giá trị khởi tạo nếu không bị bind | Có |
| `@DefaultValue` | Constructor/record | Binder dùng default nếu property thiếu | Có |
| `application.yml` | Config Data | Property đã hiện diện trong nguồn được nạp | Có theo thứ tự ưu tiên |

Nên chọn một nguồn default chính có chủ đích. Đặt cùng một mặc định ở YAML và annotation với các giá trị khác nhau có thể khiến người đọc hiểu sai, dù tại runtime Binder có thứ tự rõ ràng.

## 10. Cấu hình bắt buộc nên fail fast

Với một hệ thống thanh toán hoặc xử lý dữ liệu quan trọng, nhiều giá trị phải được cung cấp:

- Có cho phép xử lý yêu cầu không?
- Giới hạn số bản ghi mỗi lượt là bao nhiêu?
- Số worker được phép chạy là bao nhiêu?
- Tên endpoint hoặc queue đích là gì?

Một cấu hình an toàn hơn:

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer batchSize,
        @NotNull @Min(1) Integer workerCount,
        @NotBlank String queueName) {
}
~~~

Thêm `spring-boot-starter-validation` và đăng ký class cấu hình đúng cách. Khi thiếu `batch-size`, `processing-enabled` hoặc `queue-name`, ứng dụng báo lỗi trong quá trình tạo bean cấu hình, trước khi chạy tác vụ nghiệp vụ.

Ví dụ file hợp lệ:

~~~yaml
app:
  payment:
    processing-enabled: false
    batch-size: 100
    worker-count: 2
    queue-name: payment-events
~~~

Lưu ý `processing-enabled=false` vẫn **hợp lệ** vì yêu cầu của hệ thống là phải có một quyết định tường minh. Đây là lý do dùng `@NotNull Boolean` chứ không phải một ràng buộc “luôn true”.

### Đăng ký configuration properties bean

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

Nếu class `PaymentProperties` nằm dưới package `com.example.payment`, `@ConfigurationPropertiesScan` sẽ tìm được nó. Cũng có thể dùng `@EnableConfigurationProperties(PaymentProperties.class)`.

Với record constructor-bound, tránh gắn `@Component` rồi trông chờ autowire các tham số constructor từ bean thông thường. Binder cần được kích hoạt qua cơ chế registration phù hợp.

## 11. Những rủi ro khác của primitive ngoài giá trị 0/false

### 11.1. Log có vẻ bình thường

Một log như:

~~~text
workerCount=0
processingEnabled=false
~~~

không có thông tin “thuộc tính bị thiếu”. Lập trình viên có thể tưởng người vận hành cố ý cấu hình như vậy. Hãy thiết kế validation hoặc thông báo lỗi ngay từ đầu thay vì dựa vào log giá trị cuối cùng.

### 11.2. Cấu hình bị lỗi chỉ ở môi trường production

Trong development, file `application-dev.yml` có đủ khóa. Khi triển khai, `application-prod.yml` có thể thiếu một giá trị và bean primitive nhận mặc định ngầm. Ứng dụng khởi động nhưng hành vi khác kỳ vọng.

### 11.3. Giá trị 0 có ý nghĩa khác nhau giữa các thư viện

Với các API, `0` có thể biểu thị:

- Không phần tử nào.
- Chạy ngay không chờ.
- Không giới hạn hoặc chờ vô hạn theo quy ước cụ thể.
- Để hệ điều hành tự chọn cổng.
- Một giá trị bất hợp lệ dẫn đến exception.

Không thể áp dụng một kết luận chung cho tất cả API. **Thiết kế validation theo hợp đồng của từng thư viện**, không dựa vào quy tắc “0 luôn sai”.

### 11.4. Hành vi mặc định có thể không an toàn

Một trường `boolean auditEnabled` thiếu và nhận `false` có thể vô tình tắt audit. Ngược lại, một giá trị bật mặc định không suy nghĩ kỹ cũng có thể kích hoạt việc gửi dữ liệu ra ngoài. Những cấu hình có ảnh hưởng bảo mật hoặc dữ liệu thật nên yêu cầu giá trị rõ ràng và được kiểm tra.

## 12. Nested object: rủi ro còn nằm ở object bị thiếu

Một record có cấu hình lồng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Retry retry) {

    public record Retry(
            int maxAttempts,
            boolean enabled) {
    }
}
~~~

Nếu không có bất kỳ property `app.client.retry.*`, Binder có thể không tạo nested object; `retry` có thể là `null`. Đây khác với tình huống nested object đã được tạo nhưng primitive bên trong nhận `0`/`false`.

Nếu service gọi:

~~~java
properties.retry().maxAttempts();
~~~

có thể gặp `NullPointerException` khi `retry()` bằng null.

### Nhóm nested bắt buộc

Nếu nhóm retry phải hiện diện, kết hợp validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @Valid @NotNull Retry retry) {

    public record Retry(
            @NotNull @Min(1) Integer maxAttempts,
            @NotNull Boolean enabled) {
    }
}
~~~

`@NotNull Retry retry` phát hiện object không có; `@Valid` cho phép kiểm tra các ràng buộc bên trong nếu object được tạo.

### Nhóm nested tùy chọn nhưng cần mặc định

Nếu retry là chức năng tùy chọn và muốn tạo object với defaults khi không có dữ liệu, dùng `@DefaultValue` rỗng trên nested component:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("true") boolean enabled) {
    }
}
~~~

Trong mô hình này, `@DefaultValue` không đối số trên `Retry retry` yêu cầu Binder tạo nested object ngay cả khi không có khóa tương ứng, còn các component của `Retry` có defaults tường minh.

**Không trộn hai chính sách “bắt buộc phải được cấp” và “cho phép thiếu và dùng default” mà không xác định rõ ý nghĩa nghiệp vụ.**

## 13. Constructor binding, JavaBean binding và record

Có hai phong cách phổ biến của `@ConfigurationProperties`.

### 13.1. JavaBean mutable

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {

    private int concurrency;
    private Boolean enabled;

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Nếu không có `concurrency`, field primitive giữ giá trị mặc định `0`. Nếu không có `enabled`, field wrapper có thể là null. Nhưng code khác có setter nên vẫn có thể thay đổi object sau khởi động nếu không kiểm soát.

### 13.2. Record constructor binding

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int concurrency,
        Boolean enabled) {
}
~~~

Record có API ngắn gọn, component rõ ràng và không có setter. Khi thiếu property, `concurrency` có thể là 0, `enabled` có thể là null. Vì vậy, **chuyển từ JavaBean sang record không tự giải quyết vấn đề thiếu cấu hình**.

Điểm khác biệt quan trọng là annotation default nên dùng `@DefaultValue` trên record component hoặc constructor parameter, thay vì trông chờ field initializer như ở JavaBean.

### 13.3. Kiểu chọn lựa theo hợp đồng

| Yêu cầu | Kiểu/annotation phù hợp |
| --- | --- |
| Cho phép thiếu, mặc định false có chủ đích | `@DefaultValue("false") boolean` |
| Cho phép thiếu, mặc định 4 worker | `@DefaultValue("4") int` |
| Bắt buộc người triển khai chọn true/false | `@NotNull Boolean` |
| Bắt buộc cấp số nguyên dương | `@NotNull @Min(1) Integer` |
| Chuỗi bắt buộc không blank | `@NotBlank String` |
| Có thể thiếu và ứng dụng tự xử lý | `Integer`/`Boolean` nullable, nhưng phải xử lý null tường minh |
| Nhóm nested bắt buộc | `@Valid @NotNull Nested` |
| Nhóm nested có defaults có chủ đích | `@DefaultValue Nested` kết hợp default ở component con |

## 14. Phân biệt property thiếu, property rỗng, sai kiểu và giá trị sai nghiệp vụ

Không phải mọi sự cố đều là “thiếu cấu hình”.

| Tình huống | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| Không tồn tại | Không có `app.worker.concurrency` | Dùng default có chủ đích hoặc báo lỗi validation |
| Có chuỗi rỗng | `app.worker.concurrency=` | Không giả định nó tương đương thiếu; kiểm tra conversion và validation |
| Sai kiểu | `app.worker.concurrency=many` | Binder có thể báo lỗi chuyển sang số |
| Giá trị đúng kiểu nhưng không hợp lệ | `app.worker.concurrency=-1` | Dùng `@Min(1)` hoặc constraint phù hợp |
| False hợp lệ | `app.worker.enabled=false` | Cho phép nếu nghiệp vụ chấp nhận; dùng `Boolean @NotNull` nếu phải khai báo |
| Zero hợp lệ | `app.service.port=0` | Không áp dụng `@Min(1)` nếu 0 có ý nghĩa hợp lệ |
| Sai đường dẫn key | `app.workers.concurrency` thay vì `app.worker.concurrency` | Sửa property name, không che lỗi bằng default tùy tiện |

Từ góc nhìn của đối tượng Java, kiểu primitive làm mất khả năng phân biệt **missing** và **giá trị 0/false** sau khi bind. Nhưng điều đó không có nghĩa Binder không thể báo lỗi cho những trường hợp khác: chuyển đổi kiểu và validation vẫn có thể phát hiện các vấn đề độc lập.

### Trường hợp sai chính tả tên khóa

Ví dụ:

~~~yaml
app:
  worker:
    concurency: 8
~~~

Nhưng Java dùng `concurrency`. Vì YAML viết thiếu chữ `r`, property mong đợi không được bind. Nếu kiểu Java là `int` không có default hay validation, giá trị có thể bị hiểu là 0, gây nhầm lẫn.

Đây là một rủi ro thực tế: **lỗi chính tả có thể biến thành cấu hình “thiếu” và bị primitive che giấu**.

Với tập thuộc tính quan trọng, nên kết hợp validation với việc kiểm soát tên key, test binding và công cụ hỗ trợ metadata cấu hình trong IDE. Không coi một object được tạo thành công là bằng chứng mọi property của file đã được nhận.

## 15. @Value cũng có vấn đề tương tự nếu default không rõ

Một bean dùng:

~~~java
@Value("${app.worker.concurrency:0}")
private int concurrency;
~~~

cũng có thể tự che giấu việc thiếu `app.worker.concurrency` bằng mặc định 0. Điểm khác là fallback này **được viết tường minh** trong placeholder, nhưng nó vẫn có thể không hợp lệ về nghiệp vụ.

Khi chuyển sang `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int concurrency) {
}
~~~

nếu xóa `@Value` nhưng không thiết kế lại default/validation, người đọc có thể không nhận thấy rằng giá trị 0 vẫn có thể xuất hiện do kiểu primitive.

Nếu thuộc tính bắt buộc:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Min(1) Integer concurrency) {
}
~~~

Nếu cho phép default 4:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency) {
}
~~~

Mỗi phương án diễn đạt một chính sách khác nhau, không đơn giản chỉ là thay annotation.

## 16. Tác động của profile, biến môi trường và CLI

Giả sử:

~~~java
@ConfigurationProperties(prefix = "app.batch")
public record BatchProperties(
        @DefaultValue("50") int maxItems,
        @NotNull Boolean enabled) {
}
~~~

File chung:

~~~yaml
app:
  batch:
    enabled: false
~~~

File `application-prod.yml`:

~~~yaml
app:
  batch:
    max-items: 200
~~~

Khi chạy không có profile riêng và không có nguồn ghi đè:

~~~text
maxItems = 50     (mặc định ở @DefaultValue)
enabled  = false  (giá trị tường minh trong file chung)
~~~

Khi chạy:

~~~bash
java -jar batch-app.jar --spring.profiles.active=prod
~~~

kết quả:

~~~text
maxItems = 200    (application-prod.yml)
enabled  = false  (application.yml)
~~~

Nếu CLI cấp:

~~~bash
java -jar batch-app.jar --spring.profiles.active=prod --app.batch.max-items=500
~~~

`maxItems` nhận `500` theo thứ tự ưu tiên property sources. Dùng wrapper hay primitive **không thay đổi thứ tự ưu tiên**, chỉ thay khả năng biểu diễn thiếu/giá trị và cơ chế kiểm tra hợp lệ.

### Khi một file không còn được nạp

Nếu `spring.config.location` được dùng để thay vị trí tìm config data mặc định, file chứa `app.batch.enabled` có thể không còn được đọc. Khi đó `@NotNull Boolean enabled` sẽ giúp phát hiện cấu hình thiếu, thay vì mặc nhiên coi ứng dụng nên tắt chức năng vì default primitive.

Đó là lợi ích vận hành của fail-fast: một thay đổi ngoài ý muốn trong việc nạp file sẽ lộ ra tại khởi động thay vì khi nghiệp vụ đã chạy.

## 17. Kiểm thử tình huống thiếu thuộc tính bằng ApplicationContextRunner

Một test nên kiểm tra không chỉ giá trị **đúng khi cấu hình đầy đủ**, mà còn xem ứng dụng phản ứng ra sao **khi cấu hình thiếu**.

Dùng `ApplicationContextRunner` từ `spring-boot-test` và đăng ký bean cấu hình:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrdersProperties(
        @NotNull Boolean processingEnabled,
        @NotNull @Min(1) Integer maxBatchSize) {
}
~~~

Test:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.OrdersProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class OrdersPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(OrdersProperties.class)
    static class BindingConfig {
    }

    @Test
    void missingRequiredPropertyFailsAtStartup() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=false")
                .run(context -> {
                    assertThat(context).hasFailed();
                });
    }

    @Test
    void explicitFalseAndValidBatchSizeAreAccepted() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=false",
                "app.orders.max-batch-size=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    OrdersProperties props =
                            context.getBean(OrdersProperties.class);

                    assertThat(props.processingEnabled()).isFalse();
                    assertThat(props.maxBatchSize()).isEqualTo(100);
                });
    }

    @Test
    void invalidNumberFailsAtStartup() {
        runner.withPropertyValues(
                "app.orders.processing-enabled=true",
                "app.orders.max-batch-size=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                });
    }
}
~~~

Đoạn test này giả định dự án có `spring-boot-starter-test` và `spring-boot-starter-validation`. Khi áp dụng vào codebase thực tế, bảo đảm class configuration-properties nằm đúng package và validation provider khả dụng trong test context.

Ba trường hợp trả lời ba câu hỏi khác nhau:

1. Thiếu `max-batch-size` có bị phát hiện không?
2. Người dùng chủ động cấp `false` có được chấp nhận không?
3. Giá trị `0` có bị từ chối khi hợp đồng yêu cầu tối thiểu 1 không?

### Test đối chiếu kiểu primitive

Để thấy khác biệt, tạo record không dùng validation:

~~~java
@ConfigurationProperties(prefix = "app.unsafe")
public record UnsafeProperties(
        boolean enabled,
        int concurrency) {
}
~~~

Với bean được bind mà không có hai property tương ứng, ví dụ có thể quan sát `false` và `0`. Test kiểm tra bằng `assertThat(props.enabled()).isFalse()` và `assertThat(props.concurrency()).isZero()` chỉ chứng minh object đã được tạo với các giá trị đó — **không** chứng minh người vận hành cố tình cấu hình.

### Test @DefaultValue có chủ đích

~~~java
@ConfigurationProperties(prefix = "app.safe-default")
public record SafeDefaultProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int concurrency) {
}
~~~

Khi property thiếu, test nên nhận `enabled=true` và `concurrency=4`. Nếu test cấp `app.safe-default.enabled=false` và `app.safe-default.concurrency=8`, hai giá trị tường minh phải được dùng thay mặc định.

## 18. Đọc Environment để chẩn đoán không đồng nghĩa với bind primitive

Khi cần xác định một property có thực sự được cung cấp hay không, có thể dùng `Environment`:

~~~java
import org.springframework.core.env.Environment;

String rawConcurrency =
        environment.getProperty("app.worker.concurrency");

if (rawConcurrency == null) {
    System.out.println("app.worker.concurrency is not configured");
}
~~~

Trong tình huống đơn giản, `getProperty` trả `null` khi không tìm thấy property. Nhưng cách kiểm tra này là truy vấn vào Environment, **khác với việc đọc một component primitive đã bind**.

Ví dụ:

~~~java
int fromRecord = workerProperties.concurrency();
String fromEnv = environment.getProperty("app.worker.concurrency");
~~~

Khi thiếu property:

~~~text
fromRecord = 0
fromEnv    = null
~~~

Do đó, nếu cần phát hiện thiếu ở một điểm cụ thể, có thể truy vấn Environment. Tuy nhiên, cách thiết kế bền vững hơn cho một **nhóm cấu hình** là khai báo rõ hợp đồng trên `@ConfigurationProperties` và dùng validation, tránh rải kiểm tra `getProperty(...) == null` khắp codebase.

### Cần tránh in dữ liệu nhạy cảm

Để tìm lỗi binding, đôi khi chỉ cần in tên property và trạng thái “có/không”. Không in token, password hoặc secret ra log. Spring Boot Actuator có endpoint hỗ trợ quan sát cấu hình, nhưng phải bật, giới hạn quyền truy cập và xử lý masking phù hợp.

## 19. Quy trình thiết kế kiểu dữ liệu cấu hình

Khi thêm một property, có thể tự hỏi theo thứ tự:

**Câu 1: Thuộc tính này có thể bị thiếu hợp lệ không?**

- Nếu **không**: dùng kiểu có thể nhận null ở tầng binding nếu cần phân biệt thiếu, ví dụ `Integer`/`Boolean`, rồi thêm `@NotNull` hoặc validation tương đương.
- Nếu **có**: xác định default rõ ràng hoặc cách xử lý null có chủ đích.

**Câu 2: Zero/false có phải giá trị hợp lệ không?**

- Nếu **có**: tránh constraint loại bỏ chúng. Nếu vẫn yêu cầu khai báo tường minh, dùng wrapper + `@NotNull`.
- Nếu **không**: thêm constraint như `@Min(1)`/`@Positive` khi phù hợp.

**Câu 3: Có default nghiệp vụ rõ ràng không?**

- Nếu **có**: với record, dùng `@DefaultValue` hoặc đặt trong file cấu hình theo một quy ước nhất quán.
- Nếu **không**: đừng dựa vào default primitive ngầm.

**Câu 4: Property thuộc nhóm nested nào?**

- Dùng cấu trúc record lồng nhau khi các khóa có prefix chung.
- Chọn `@NotNull`/`@Valid` nếu nested object bắt buộc; chọn `@DefaultValue` rỗng nếu có policy tạo nested object mặc định.

**Câu 5: Test khi thiếu đã tồn tại chưa?**

- Kiểm tra cả trường hợp thiếu, có giá trị 0, có `false`, sai kiểu và giá trị hợp lệ.
- Đừng chỉ test happy path có đầy đủ dữ liệu.

Mục tiêu không phải luôn dùng wrapper trong mọi field; mục tiêu là **diễn đạt đúng hợp đồng cấu hình và tránh lỗi bị che giấu**.

## 20. Những hiểu nhầm phổ biến

### “Ứng dụng khởi động được nghĩa là tất cả property bắt buộc đã được khai báo”

Không chính xác. Nếu dùng primitive không có validation, thiếu property có thể vẫn cho một object hợp lệ về kiểu Java nhưng sai nghiệp vụ.

### “@NotNull trên int sẽ phát hiện thiếu”

Không. `int` không thể null. Nếu bắt buộc phải biết property có được cấp hay không, hãy dùng `Integer` + `@NotNull`.

### “@Min(1) trên Integer đã đủ phát hiện mọi trường hợp thiếu”

Không chắc. Với reference type, constraint kiểm tra phạm vi số không nhất thiết coi null là sai. Nên dùng thêm `@NotNull` nếu yêu cầu sự hiện diện.

### “false luôn là một giá trị sai”

Không. `false` có thể là lựa chọn hợp lệ của người vận hành. Điều cần phát hiện là **thiếu quyết định** nếu nghiệp vụ yêu cầu cấu hình tường minh.

### “@DefaultValue bảo đảm giá trị hợp lệ”

Không. `@DefaultValue("0")` vẫn có thể vi phạm `@Min(1)`. Default là giá trị đầu vào cho Binder, không thay thế validation.

### “Đặt @DefaultValue sẽ ghi giá trị vào Environment”

Không. Annotation cung cấp default khi **bind** object; nó không phải lệnh tạo thêm property trong mọi PropertySource. Vì vậy `properties.concurrency()` có thể trả 4, trong khi `environment.getProperty("app.worker.concurrency")` vẫn null nếu không có property nguồn.

### “Chỉ cần dùng Boolean là ứng dụng sẽ tự báo lỗi khi thiếu”

Không. Wrapper cho phép biểu diễn null, nhưng không tự fail fast. Dùng Bean Validation hoặc kiểm tra tường minh ở ranh giới cấu hình.

### “Tất cả cấu hình thiếu nên có default”

Không. Với endpoint production, thông số giao dịch, secret, quyền truy cập hoặc cờ điều khiển nghiệp vụ quan trọng, việc thiếu có thể phải được coi là lỗi khởi động.

## 21. Bài tập thực hành

### Bài 1 — Dự đoán kết quả từ primitive

Cho:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        int retries,
        boolean enabled) {
}
~~~

Không có `demo.retries` hoặc `demo.enabled` trong các nguồn cấu hình. Với object được Binder tạo thành công, hãy dự đoán hai component.

**Đáp án:** thường là `0` và `false`. Hai giá trị này không chứng minh người vận hành đã chủ động cấp chúng.

### Bài 2 — Phân biệt thiếu và false

Một tính năng bắt buộc người triển khai phải chọn bật hoặc tắt. Hãy chọn kiểu và validation.

**Đáp án:**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.feature")
public record FeatureProperties(
        @NotNull Boolean enabled) {
}
~~~

`null` biểu diễn thiếu; `false` là lựa chọn hợp lệ.

### Bài 3 — Số 0 là lỗi nghiệp vụ

`demo.pool.size` phải từ 1 đến 32. Dựng cấu hình phù hợp.

**Đáp án:**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.pool")
public record PoolProperties(
        @NotNull @Min(1) @Max(32) Integer size) {
}
~~~

Nếu thiếu, `@NotNull` báo lỗi; nếu có `0`, `@Min(1)` báo lỗi; nếu có `64`, `@Max(32)` báo lỗi.

### Bài 4 — Số 0 là giá trị hợp lệ

Một port có thể là 0 với ý nghĩa framework tự chọn cổng, nhưng người dùng bắt buộc phải cung cấp. Đừng gắn `@Min(1)`. Dùng `@NotNull Integer port` và bổ sung constraint đúng với các giá trị port hệ thống chấp nhận, bao gồm 0.

### Bài 5 — Chọn default có chủ đích

Một job cho phép thiếu `demo.job.max-items` và sẽ dùng 500.

**Một cách viết:**

~~~java
@ConfigurationProperties(prefix = "demo.job")
public record JobProperties(
        @DefaultValue("500") int maxItems) {
}
~~~

Thử ghi đè qua `--demo.job.max-items=200`; giá trị cuối phải là 200.

### Bài 6 — Phát hiện lỗi chính tả

YAML có:

~~~yaml
demo:
  worker:
    concurreny: 5
~~~

Record chờ `concurrency`. Hãy giải thích vì sao primitive `int concurrency` không validation có thể tạo `0` và sửa đúng tên property.

### Bài 7 — Nested object bị thiếu

Record có `Retry retry` và bên trong `int maxAttempts`. Không có `demo.client.retry.*`. Hãy phân biệt hai tình huống:

- `retry` bằng null vì không có nested object.
- `retry` được tạo nhưng `maxAttempts` không có giá trị nguồn và là 0.

Sau đó thiết kế một trong hai chính sách: yêu cầu retry qua `@Valid @NotNull` và wrapper, hoặc dùng `@DefaultValue` rỗng cùng default hợp lệ.

### Bài 8 — Kiểm thử fail fast

Viết test `ApplicationContextRunner` với `@NotNull Integer batchSize`; không cấp `demo.batch.batch-size`, rồi kiểm tra context thất bại. Cấp `batch-size=10` và kiểm tra context khởi tạo thành công.

### Bài 9 — Không dùng default cho secret

Một cấu hình `app.payment.api-token` là bắt buộc. Chọn `@NotBlank String apiToken` thay vì `@DefaultValue("demo")`; giải thích rủi ro nếu dùng một token giả khi thiếu cấu hình production.

## 22. Tổng kết

Các kiểu nguyên thủy `int`, `long` và `boolean` rất tiện trong Java, nhưng **không thể biểu diễn trạng thái “không có giá trị” bằng null**. Trong quá trình binding, property thiếu có thể tạo thành `0` hoặc `false` mà không phát sinh lỗi ngay; ứng dụng có thể hoạt động sai mà khó nhận biết.

Khi giá trị thiếu là **hợp lệ**, hãy khai báo một default có chủ đích qua `@DefaultValue` hoặc file cấu hình. Khi giá trị là **bắt buộc**, hãy cân nhắc wrapper `Integer`/`Boolean` cùng `@NotNull` và các constraint như `@Min`, `@Max`. Với cấu hình lồng nhau, xử lý cả sự tồn tại của nested object và validation của các field con.

Nguyên tắc thiết kế: **không để mặc định ngầm của kiểu Java thay cho quyết định cấu hình của người vận hành**. Việc chọn kiểu, default và validation cần theo hợp đồng nghiệp vụ, đi kèm test cho trường hợp thiếu cấu hình, giá trị 0/false tường minh và dữ liệu không hợp lệ.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Constructor Binding](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Boot 3.3 — @DefaultValue API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
- [Jakarta Bean Validation — Built-in Constraints](https://jakarta.ee/specifications/bean-validation/)
