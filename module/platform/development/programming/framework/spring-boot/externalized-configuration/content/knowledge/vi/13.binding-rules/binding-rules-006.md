# Xử lý giá trị sai kiểu với `ignoreInvalidFields` trong Spring Boot

## 1. Vấn đề: cấu hình tồn tại nhưng không thể liên kết vào kiểu Java

Trong Spring Boot, một ứng dụng có thể nhận cấu hình từ `application.yml`, `application.properties`, biến môi trường, Java system properties hoặc đối số dòng lệnh. Khi dùng `@ConfigurationProperties`, Spring Boot cố gắng **liên kết (bind)** những giá trị cấu hình này với các trường hoặc tham số constructor của một class Java.

Ví dụ, file cấu hình khai báo:

~~~yaml
app:
  worker:
    thread-count: 8
    timeout: 15s
    enabled: true
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int threadCount = 4;
    private Duration timeout = Duration.ofSeconds(5);
    private boolean enabled = false;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Nếu các giá trị hợp lệ, Binder có thể chuyển:

- `8` → `int`.
- `15s` → `java.time.Duration`.
- `true` → `boolean`.

Nhưng giả sử môi trường production cấp:

~~~yaml
app:
  worker:
    thread-count: "many"
    timeout: "15s"
    enabled: true
~~~

`many` không phải giá trị số nguyên hợp lệ. Binder tìm thấy khóa `app.worker.thread-count` nhưng không thể chuyển chuỗi sang `int`.

Mặc định, Spring Boot thường **báo lỗi binding và dừng việc tạo bean cấu hình** thay vì âm thầm sử dụng một giá trị khác. Tuy vậy, annotation `@ConfigurationProperties` cung cấp thuộc tính `ignoreInvalidFields` để lựa chọn cách xử lý bớt nghiêm ngặt trong một số lỗi binding.

Chủ đề này cần phân biệt rõ ba vấn đề:

1. **Thuộc tính có tồn tại hay không?**
2. **Tên thuộc tính có thuộc mô hình Java cần bind hay không?**
3. **Giá trị thuộc tính có thể chuyển sang kiểu Java đích hay không?**

`ignoreInvalidFields` liên quan chủ yếu đến nhóm thứ ba. Nó không phải cơ chế thay thế mọi lỗi cấu hình bằng giá trị hợp lệ, và không được xem như một hệ thống validation.

## 2. `ignoreInvalidFields` là gì?

`ignoreInvalidFields` là một thuộc tính của annotation:

~~~java
org.springframework.boot.context.properties.ConfigurationProperties
~~~

Cú pháp:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    // ...
}
~~~

Giá trị mặc định của `ignoreInvalidFields` là **`false`**.

| Giá trị | Ý nghĩa |
| --- | --- |
| `ignoreInvalidFields = false` | Mặc định. Lỗi liên kết/chuyển đổi giá trị không hợp lệ thường được báo thay vì bỏ qua. |
| `ignoreInvalidFields = true` | Hướng dẫn Binder bỏ qua những lỗi trường không hợp lệ có thể bỏ qua trong quá trình liên kết cấu hình. |

Nên hiểu `true` là **nới lỏng việc xử lý lỗi binding**, không phải một lựa chọn làm dữ liệu đầu vào trở nên hợp lệ.

Ví dụ:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Nếu đầu vào là `app.worker.thread-count=many`, Binder có thể bỏ qua lỗi chuyển đổi của thuộc tính đó, để giá trị `threadCount` đã khởi tạo trong object vẫn là `4`. Tuy nhiên, đây là **hành vi cần hiểu trong ngữ cảnh JavaBean binding cụ thể**: không nên suy ra rằng mọi loại cấu hình hay mọi constructor-bound object đều tự nhận một giá trị default hợp lệ.

Lý do: khi một trường bị bỏ qua, giá trị kết quả phụ thuộc vào cách object được tạo, trạng thái ban đầu của trường, kiểu primitive/reference, cách liên kết và các ràng buộc tiếp theo.

## 3. Mặc định nghiêm ngặt: `ignoreInvalidFields = false`

Ví dụ cấu hình:

~~~properties
app.worker.thread-count=not-a-number
app.worker.enabled=true
~~~

Class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = false
)
public class WorkerProperties {
    private int threadCount = 4;
    private boolean enabled;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Khi Spring Boot tạo bean `WorkerProperties` thông qua cơ chế `@ConfigurationProperties`, nó cố chuyển `not-a-number` sang `int` và thường thất bại.

Một thông báo lỗi có thể đề cập đến:

~~~text
Failed to bind properties under 'app.worker.thread-count'
to int

Property: app.worker.thread-count
Value: "not-a-number"
Reason: failed to convert ...
~~~

Thông báo thực tế phụ thuộc phiên bản Spring Boot, nguồn cấu hình, converter và vị trí bean. Có thể gặp `ConfigurationPropertiesBindException`, `BindException` hoặc exception chuyển đổi ở chuỗi nguyên nhân.

**Đây thường là hành vi có lợi cho production.** Thay vì chạy với số luồng sai, ứng dụng dừng sớm để người triển khai sửa cấu hình.

Trong code không nhất thiết phải viết `ignoreInvalidFields = false` vì đó đã là mặc định:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    // ...
}
~~~

Việc ghi tường minh `false` chỉ có ích khi muốn nhấn mạnh chính sách của dự án hoặc phục vụ giảng giải.

## 4. Khi bật `ignoreInvalidFields = true`

Thay annotation:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    private int threadCount = 4;
    private boolean enabled = false;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

File:

~~~yaml
app:
  worker:
    thread-count: invalid
    enabled: true
~~~

Với JavaBean binding kiểu này, một tình huống thường thấy là:

- Binder không chuyển được `invalid` sang `int`.
- Lỗi của thuộc tính đó được bỏ qua nhờ `ignoreInvalidFields=true`.
- `threadCount` có thể giữ giá trị ban đầu là `4`.
- `enabled=true`, nếu được bind bình thường, vẫn có thể được áp dụng.

Tuy nhiên, **không nên xem trạng thái cuối của tất cả trường như một hợp đồng bảo đảm rằng Binder luôn bỏ qua đúng một thuộc tính rồi tiếp tục mọi thuộc tính khác**. Phạm vi lỗi bị bỏ qua và trạng thái kết quả còn tùy cơ chế bind, đặc biệt đối với nested object, collection, constructor binding hoặc conversion tùy biến.

Với mục tiêu kỹ thuật “giá trị không hợp lệ phải được phát hiện ngay”, nên giữ mặc định `false` thay vì dựa vào `ignoreInvalidFields=true`.

## 5. Sai kiểu (invalid) khác với tên không nhận biết (unknown)

Trong annotation `@ConfigurationProperties` có **hai thuộc tính độc lập** dễ bị nhầm:

~~~java
@ConfigurationProperties(
        prefix = "app",
        ignoreInvalidFields = false,
        ignoreUnknownFields = true
)
public class AppProperties {
    // ...
}
~~~

Giá trị mặc định thường dùng là:

- `ignoreInvalidFields = false`.
- `ignoreUnknownFields = true`.

Phân biệt:

**Sai kiểu hoặc không bind được (invalid field)**

~~~yaml
app:
  retry:
    max-attempts: "a lot"
~~~

Java:

~~~java
private int maxAttempts;
~~~

Tên `max-attempts` có đích bind là trường `int maxAttempts`, nhưng giá trị `a lot` không thể chuyển thành `int`. Đây là tình huống liên quan `ignoreInvalidFields`.

**Tên không có đích tương ứng (unknown field)**

~~~yaml
app:
  retry:
    max-attempts: 3
    experimental-toggle: true
~~~

Java chỉ có:

~~~java
private int maxAttempts;
~~~

Nếu `experimental-toggle` không có trường phù hợp trong mô hình cấu hình, nó có thể được xem là thuộc tính không được bind. Đây là vấn đề của `ignoreUnknownFields`, không phải lỗi chuyển `String` sang `int`.

| Tình huống | Thuộc tính chính liên quan |
| --- | --- |
| `max-attempts=abc` nhưng Java cần `int` | `ignoreInvalidFields` |
| `max-attempts=3` nhưng Java không có trường tương ứng | `ignoreUnknownFields` |
| `timeout=oops` nhưng Java cần `Duration` | `ignoreInvalidFields` |
| Có thêm `debug-extra` mà class không khai báo | `ignoreUnknownFields` |
| Khóa bắt buộc hoàn toàn thiếu | Default, nullability, validation; không được `ignoreInvalidFields` giải quyết tự động |
| Giá trị đúng kiểu nhưng trái quy tắc nghiệp vụ | Bean Validation hoặc kiểm tra nghiệp vụ |

Không nên đặt `ignoreUnknownFields=false` rồi kỳ vọng nó giải quyết lỗi parse `int`. Ngược lại, bật `ignoreInvalidFields=true` không nhằm “cho phép cấu hình thừa khóa lạ”.

## 6. Ví dụ đối chiếu bốn kịch bản

Giả sử bean cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxConnections = 10;
    private Duration timeout = Duration.ofSeconds(5);

    public int getMaxConnections() {
        return maxConnections;
    }

    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Xét các tình huống, giả sử không có property source ưu tiên cao hơn:

| Trường hợp | Cấu hình | Diễn giải |
| --- | --- | --- |
| Hợp lệ | `max-connections=20`, `timeout=8s` | Hai trường có thể được chuyển và bind |
| Thiếu khóa | Không có `max-connections` | JavaBean có thể giữ giá trị khởi tạo `10` |
| Sai kiểu | `max-connections=lots` | Mặc định báo lỗi chuyển kiểu |
| Unknown | `connection-label=primary`, class không khai báo | Mặc định `ignoreUnknownFields=true` thường cho phép bỏ qua khóa không bind được |

Khi bật `ignoreInvalidFields=true`, kịch bản “sai kiểu” có thể được bỏ qua. Nhưng việc bỏ qua một trường **không xác nhận rằng toàn bộ object hợp lệ**.

Ví dụ, nếu `timeout` bị bỏ qua và vẫn là `5s`, giá trị đó có thể phù hợp cho dev nhưng không phù hợp production. Do đó, một ứng dụng cần chính sách riêng quyết định cấu hình nào là tùy chọn và giá trị mặc định nào thực sự an toàn.

## 7. Cách đăng ký bean cấu hình để binding hoạt động

`@ConfigurationProperties` không đủ nếu class chưa được đăng ký thành Spring bean theo cách phù hợp. Một cách phổ biến là bật scan.

File `src/main/java/com/example/demo/config/ClientProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxConnections = 10;
    private Duration timeout = Duration.ofSeconds(5);

    public int getMaxConnections() {
        return maxConnections;
    }

    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

File ứng dụng:

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

Cách khác là dùng `@EnableConfigurationProperties(ClientProperties.class)` trên một class `@Configuration` hoặc class ứng dụng.

Sau đó service có thể sử dụng cấu hình qua constructor injection:

~~~java
import org.springframework.stereotype.Service;
import com.example.demo.config.ClientProperties;

@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public int configuredPoolSize() {
        return properties.getMaxConnections();
    }
}
~~~

Ở đây Binder liên kết **dữ liệu cấu hình** vào `ClientProperties`, còn Spring container tiêm bean `ClientProperties` đã tạo vào `ClientService`.

Tình huống `ignoreInvalidFields` chỉ có ý nghĩa nếu bean thực sự đi qua quy trình configuration properties binding.

## 8. Ví dụ với `Duration` và `DataSize`: đơn vị sai cũng là dữ liệu không hợp lệ

Spring Boot có thể chuyển các chuỗi có đơn vị sang kiểu Java thích hợp:

~~~yaml
app:
  transport:
    timeout: 5s
    max-payload: 10MB
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transport")
public class TransportProperties {
    private Duration timeout = Duration.ofSeconds(3);
    private DataSize maxPayload = DataSize.ofMegabytes(1);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public DataSize getMaxPayload() {
        return maxPayload;
    }

    public void setMaxPayload(DataSize maxPayload) {
        this.maxPayload = maxPayload;
    }
}
~~~

Những giá trị `5s` và `10MB` hợp lệ theo các cú pháp đơn vị mà Spring Boot hỗ trợ.

Nhưng:

~~~yaml
app:
  transport:
    timeout: "soon"
    max-payload: "lots-of-data"
~~~

không biểu diễn được `Duration` hoặc `DataSize` phù hợp. Lỗi nằm ở **conversion/binding**.

Nếu bật `ignoreInvalidFields=true`:

- Có thể tránh được việc báo lỗi binding tương ứng.
- Không vì thế mà giá trị sai được chuyển thành kiểu đúng.
- Các giá trị mặc định khởi tạo có thể còn nguyên trong JavaBean, nhưng không nên giả định tương tự với mọi kiểu bind.

Đối với timeout hoặc dung lượng payload có tác động đến hiệu năng, chi phí hoặc an toàn hệ thống, **phát hiện lỗi và sửa dữ liệu đầu vào** thường đáng tin cậy hơn bỏ qua âm thầm.

## 9. Khi giá trị đúng kiểu nhưng trái quy tắc nghiệp vụ

Giả sử:

~~~yaml
app:
  worker:
    thread-count: -4
    timeout: 0s
~~~

`-4` là một số nguyên hợp lệ. `0s` là một giá trị thời lượng có thể chuyển được. Vậy nên chúng có thể **không gây lỗi chuyển kiểu**.

Nhưng trong một ứng dụng worker pool:

- Số luồng âm có thể không hợp lệ.
- Timeout bằng 0 có thể phá vỡ yêu cầu xử lý.
- Ngưỡng retry quá lớn có thể gây tải cho hệ thống.

`ignoreInvalidFields` không có trách nhiệm định nghĩa những ràng buộc này. Cần dùng **Bean Validation** hoặc kiểm tra tại code Java.

Ví dụ:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    @Min(1)
    private int threadCount = 4;

    @NotNull
    private Duration timeout = Duration.ofSeconds(5);

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Dự án cần Bean Validation provider tương ứng, chẳng hạn dependency `spring-boot-starter-validation` trong Spring Boot 3.x.

`@Min(1)` kiểm tra số luồng ít nhất là 1. `@NotNull` chỉ kiểm tra timeout không null; nó **không** đảm bảo timeout lớn hơn 0. Nếu yêu cầu `timeout > 0`, cần constraint phù hợp hoặc kiểm tra bổ sung.

**Quan trọng:** ngay cả khi có `ignoreInvalidFields=true`, validation vẫn có thể khiến startup thất bại nếu object cuối cùng không thỏa các constraint. Không được coi cờ ignore là cơ chế tắt toàn bộ validation.

## 10. Kết hợp `ignoreInvalidFields` với `@Validated`

Một số dự án có thể cần bỏ qua lỗi conversion ở các trường không quan trọng nhưng vẫn từ chối trạng thái cuối không hợp lệ:

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class WorkerProperties {
    @Min(1)
    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Giả sử file có `thread-count=invalid`. Nếu lỗi conversion được bỏ qua và trường giữ giá trị mặc định `4`, điều kiện `@Min(1)` vẫn đạt.

Điều này không chứng minh cấu hình production đã được cấp chính xác. Nó chỉ chứng minh rằng **object cuối cùng đáp ứng một điều kiện sau binding**.

Nếu trong JavaBean không đặt default cho `threadCount`:

~~~java
@Min(1)
private int threadCount;
~~~

giá trị Java mặc định của primitive `int` là `0`. Khi conversion bị bỏ qua và field vẫn bằng 0, validation `@Min(1)` có thể từ chối bean.

Có thể hình dung ba tầng trách nhiệm:

~~~text
Property sources
      ↓
Binder + conversion
      ↓
ignoreInvalidFields?  → bỏ qua lỗi binding có thể bỏ qua
      ↓
Giá trị cuối trong object
      ↓
Bean Validation / kiểm tra bất biến
      ↓
Bean có hợp lệ để ứng dụng sử dụng hay không?
~~~

`ignoreInvalidFields` chỉ ảnh hưởng đến cách xử lý **một nhóm lỗi ở tầng Binder**. Nó không tự đảm bảo các tầng phía sau thành công.

## 11. Thiếu thuộc tính không đồng nghĩa với sai kiểu

Ví dụ class:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private int maxRetries = 3;

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Nếu hoàn toàn không có khóa `app.client.max-retries`:

- Không có conversion thất bại vì không có giá trị `abc` để chuyển.
- Với JavaBean binding, field `maxRetries` có thể tiếp tục giữ default `3`.
- `ignoreInvalidFields` không phải điều kiện bắt buộc để xảy ra việc giữ default này.

Trong một immutable class dùng constructor binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(int maxRetries) {}
~~~

Không có setter hoặc field initializer tương tự class JavaBean. Việc thiếu giá trị phụ thuộc vào semantics constructor binding, kiểu tham số và default được khai báo. Để có default rõ ràng:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("3") int maxRetries
) {}
~~~

`@DefaultValue` là **cơ chế mặc định ở tầng binding**, không phải cờ bỏ qua lỗi. Nếu người triển khai cấp `max-retries=abc`, bản thân `@DefaultValue("3")` không phải một lời hứa tự sửa giá trị sai.

## 12. Constructor binding và khả năng bỏ qua lỗi

Trong Spring Boot 3.x, một class `@ConfigurationProperties` có một constructor có tham số phù hợp, hoặc một record có canonical constructor phù hợp, thường có thể được constructor-bound mà không cần `@ConstructorBinding` tường minh.

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public record WorkerProperties(
        @DefaultValue("4") int threadCount,
        @DefaultValue("5s") Duration timeout
) {}
~~~

Khác với JavaBean binding:

- Object được tạo sau khi Binder chuẩn bị các tham số.
- Không có một instance với setter và field initializer để “để nguyên” khi bỏ qua một giá trị.
- Khi một giá trị bị bỏ qua, Binder có thể phải giải quyết tham số còn thiếu hoặc tạo nested object.
- Constructor hoặc validation vẫn có thể từ chối dữ liệu, dù `ignoreInvalidFields=true`.

Do đó, **không nên coi `ignoreInvalidFields=true` trên record là cơ chế bảo đảm giá trị sai luôn rơi về `@DefaultValue`**, đặc biệt khi có nested object hoặc cấu trúc phức tạp.

Nếu cần một chính sách fallback cụ thể cho dữ liệu sai, hãy triển khai và kiểm thử nó một cách tường minh trong code. Đối với thuộc tính bắt buộc, thường tốt hơn là để conversion thất bại và báo lỗi.

## 13. Collection, danh sách và Map: bỏ qua lỗi có thể làm cấu hình không đồng nhất

Giả sử có danh sách các endpoint:

~~~yaml
app:
  endpoints:
    - name: primary
      timeout: 5s
    - name: backup
      timeout: invalid
~~~

Java record:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Endpoint> endpoints) {
    public record Endpoint(String name, Duration timeout) {}
}
~~~

Binder cố xây dựng `List<Endpoint>`; một phần tử chứa timeout sai kiểu.

Từ đây không thể suy ra giản đơn rằng `ignoreInvalidFields=true` sẽ:

- Chỉ xóa phần tử backup.
- Tự chuyển timeout backup thành 0.
- Luôn giữ nguyên phần tử backup với timeout default.
- Ghép danh sách còn hợp lệ với danh sách ở file cấu hình ưu tiên thấp hơn.

Không có kết luận nào ở trên là **hợp đồng chung** cho mọi tình huống. Việc bỏ qua lỗi có thể tác động đến kết quả binding của một phần hoặc cả cấu trúc, tùy type, converter và BindHandler.

Nếu danh sách endpoint là cấu hình nghiệp vụ quan trọng, nên **giữ strict binding**, phát hiện phần tử sai và sửa dữ liệu đầu vào. Nếu cần chấp nhận phần tử lỗi từ nguồn ngoài, hãy thiết kế một bước parsing/validation riêng với quy tắc bỏ qua hoặc báo lỗi rõ ràng, kèm test.

Tương tự với `Map<String, Duration>`: một value sai đơn vị không mặc nhiên trở thành một map entry hợp lệ chỉ vì bật ignore.

## 14. `ignoreInvalidFields` không sửa lỗi YAML và không cứu được mọi exception

Xét YAML sai cú pháp:

~~~yaml
app:
  worker:
    thread-count: [not, closed
~~~

Đây là vấn đề **phân tích cú pháp YAML** trước khi có thể bind thuộc tính vào Java. `ignoreInvalidFields` nằm trên annotation của một class Java và không có vai trò tự sửa dấu ngoặc vuông thiếu trong file.

Các tình huống khác cần phân biệt:

| Tình huống | `ignoreInvalidFields` có phải giải pháp? |
| --- | --- |
| Chuỗi `abc` cần bind vào `int` | Có thể ảnh hưởng đến cách Binder xử lý lỗi conversion |
| Chuỗi `tomorrow` cần bind vào `Duration` | Có thể ảnh hưởng đến cách Binder xử lý lỗi conversion |
| File YAML có cú pháp sai | Không |
| Tệp `spring.config.import` bắt buộc không tồn tại | Không; là lỗi tìm Config Data |
| Bean cần một dependency không có trong container | Không |
| Constructor tự ném `IllegalArgumentException` vì nghiệp vụ | Không thể kỳ vọng cờ ignore che được |
| Bean Validation báo cấu hình không hợp lệ | Không phải nhiệm vụ của cờ ignore |
| Mật khẩu database sai | Không; thường là lỗi kết nối/xác thực khi sử dụng |
| Typo tạo ra một khóa không có trường đích | Xem `ignoreUnknownFields` |
| Giá trị được chuyển kiểu thành công nhưng rỗng/không hợp lệ về nghiệp vụ | Dùng validation hoặc kiểm tra nghiệp vụ |

Không nên dùng `ignoreInvalidFields=true` như một “chế độ tiếp tục khởi động bằng mọi giá”. Những lỗi ngoài quá trình binding vẫn có thể làm application context không tạo được.

## 15. `@Value` và `Environment` có chịu tác động không?

`ignoreInvalidFields` là thuộc tính **của `@ConfigurationProperties`**. Nó không phải một công tắc toàn cục thay đổi mọi lần đọc cấu hình.

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerLimits {
    private final int threadCount;

    public WorkerLimits(
            @Value("${app.worker.thread-count:4}") int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Nếu môi trường cấp `app.worker.thread-count=invalid`, việc chuyển `invalid` thành `int` tại constructor parameter vẫn có thể thất bại. Bật `ignoreInvalidFields=true` trên **một class cấu hình khác** không khiến mọi `@Value` trong ứng dụng tự bỏ qua conversion error.

Tương tự, code:

~~~java
import org.springframework.core.env.Environment;

public int readThreadCount(Environment environment) {
    Integer count = environment.getProperty(
            "app.worker.thread-count", Integer.class, 4);
    return count;
}
~~~

API `Environment#getProperty(...)` có logic tra cứu và chuyển kiểu riêng; `ignoreInvalidFields` không tự áp dụng cho mọi lần gọi.

Nếu nhu cầu chỉ là “đọc một khóa, nếu thiếu thì dùng giá trị dự phòng”, hãy dùng placeholder có default, `Environment#getProperty(key, default)` hoặc `@DefaultValue` ở đúng tầng. Nhưng **giá trị sai kiểu** vẫn là vấn đề khác với **khóa không tồn tại**.

## 16. Thứ tự ưu tiên nguồn cấu hình vẫn có hiệu lực

Spring Boot có nhiều nguồn cấu hình. Ví dụ file `application.yml`:

~~~yaml
app:
  worker:
    thread-count: 4
~~~

File profile `application-prod.yml`:

~~~yaml
app:
  worker:
    thread-count: 8
~~~

Biến môi trường:

~~~bash
APP_WORKER_THREADCOUNT=invalid
~~~

Khi profile `prod` hoạt động và biến môi trường được cấp, trong thứ tự ưu tiên cấu hình thông thường, biến môi trường có thể là **nguồn được chọn** cho `app.worker.thread-count`.

Điều này gây một tình huống đáng chú ý: file YAML vẫn chứa `4` và `8` hợp lệ, nhưng giá trị cuối có ưu tiên cao nhất lại là `invalid`.

`ignoreInvalidFields=false` có thể khiến binding thất bại. Còn `ignoreInvalidFields=true` **không có nghĩa Binder sẽ tự tìm ngược xuống mọi nguồn ưu tiên thấp hơn cho đến khi gặp một giá trị `int` hợp lệ**.

Đừng suy ra rằng trong ví dụ này kết quả chắc chắn là `8`. Khi một giá trị từ nguồn ưu tiên cao hơn không chuyển được, cơ chế xử lý lỗi không tương đương “fallback sang property source thấp hơn”.

Giải pháp an toàn là sửa biến môi trường sai hoặc loại bỏ biến đó để nguồn hợp lệ có hiệu lực theo thứ tự ưu tiên thông thường.

## 17. Điều gì xảy ra với kiểu primitive và kiểu tham chiếu?

Với JavaBean binding:

~~~java
@ConfigurationProperties(prefix = "app.limit", ignoreInvalidFields = true)
public class LimitProperties {
    private int maxConnections;
    private Integer retryCount;
    private boolean enabled = true;

    // getters và setters phù hợp
}
~~~

Trước khi binding:

- `maxConnections` của primitive `int` có giá trị Java mặc định `0`.
- `retryCount` của `Integer` có giá trị `null`.
- `enabled` đã khởi tạo tường minh là `true`.

Nếu Binder bỏ qua một lỗi conversion cho từng trường, object **có thể giữ trạng thái ban đầu khác nhau tùy trường**: 0, null hoặc true.

Đây là một rủi ro quan trọng, vì những giá trị đó có thể trông hợp lệ khi log ra nhưng thực chất là do không bind được.

Thực hành nên áp dụng:

1. Không dùng `0` hoặc `null` như dấu hiệu đảm bảo rằng người triển khai cố tình cấu hình như vậy.
2. Nếu có default, đặt default theo **ý nghĩa nghiệp vụ** và mô tả nó rõ ràng.
3. Kiểm tra các ràng buộc tối thiểu bằng validation.
4. Nếu trạng thái cuối khác nhau giữa các phiên bản/binder hoặc các nguồn, viết integration test để cố định hành vi mong muốn.
5. Với cấu hình quan trọng, từ chối dữ liệu sai thay vì âm thầm giữ giá trị ban đầu.

Không phải cứ class có getter và setter là nên bật ignore.

## 18. Trường hợp enum và giá trị ngoài tập cho phép

Giả sử ứng dụng có một enum:

~~~java
public enum ProcessingMode {
    SAFE,
    FAST,
    AUDIT
}
~~~

Class cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.processing")
public class ProcessingProperties {
    private ProcessingMode mode = ProcessingMode.SAFE;

    public ProcessingMode getMode() {
        return mode;
    }

    public void setMode(ProcessingMode mode) {
        this.mode = mode;
    }
}
~~~

File cấu hình:

~~~yaml
app:
  processing:
    mode: FAST
~~~

Binder có thể chuyển giá trị `FAST` sang `ProcessingMode.FAST`.

Nhưng `mode=UNKNOWN` không thuộc enum. Mặc định, conversion có thể thất bại. Nếu bật `ignoreInvalidFields=true`, lỗi có thể được bỏ qua và JavaBean còn giá trị `SAFE` trong những điều kiện phù hợp.

Nếu `SAFE` thực sự là fallback đã được thiết kế, quyết định này có thể phù hợp với tính năng không quan trọng. Tuy nhiên, trong một hệ thống thanh toán hoặc xử lý dữ liệu, việc âm thầm chuyển một mode sai sang `SAFE` có thể làm thay đổi hành vi mà người triển khai không biết.

Có thể cân nhắc:

- Giữ strict binding.
- Cung cấp tài liệu liệt kê các giá trị enum hợp lệ.
- Dùng validation nếu có điều kiện bổ sung.
- Viết test cho trường hợp mode không được hỗ trợ.
- Chỉ cho phép fallback nếu đó là yêu cầu đã thống nhất, không phải một giải pháp tạm.

## 19. Cần quan sát lỗi binding ở đâu?

Khi ứng dụng dừng vì binding thất bại, log thường chỉ ra:

- **Prefix** của `@ConfigurationProperties`, ví dụ `app.worker`.
- **Tên property** cụ thể, ví dụ `app.worker.thread-count`.
- **Giá trị** đầu vào nếu phù hợp và không bị ẩn theo chính sách.
- **Kiểu đích** như `int` hoặc `Duration`.
- **Nguồn cấu hình** nếu nguồn cung cấp origin metadata.
- **Nguyên nhân** conversion hoặc validation.

Ví dụ minh họa, không phải chuỗi thông báo cố định của mọi phiên bản:

~~~text
Failed to bind properties under 'app.worker.thread-count'
to int:

Property: app.worker.thread-count
Value: "lots"
Origin: class path resource [application.yml]
Reason: failed to convert java.lang.String to int
~~~

Quy trình chẩn đoán:

1. Xác nhận bean và `prefix` nào đang bind.
2. Đối chiếu tên khóa canonical (thường là kebab-case).
3. Xác định **nguồn cấu hình cuối** đang cấp giá trị, gồm biến môi trường và CLI.
4. Kiểm tra kiểu Java đích, ví dụ `Duration` cần giá trị thời lượng hợp lệ.
5. Sửa dữ liệu sai thay vì bật ignore ngay.
6. Nếu muốn sử dụng ignore, xác định **giá trị còn lại** sau khi bỏ qua, bằng một test cụ thể.
7. Đảm bảo validation vẫn bảo vệ các ràng buộc bắt buộc.

Nếu dùng Spring Boot Actuator, endpoint `env` và `configprops` có thể hỗ trợ tìm nguồn/giá trị cấu hình khi được bật. Phải giới hạn quyền truy cập và tránh làm lộ secret.

## 20. Nên giữ strict binding trong production khi nào?

Những thuộc tính sau thường cần được xem xét nghiêm ngặt:

| Nhóm cấu hình | Ví dụ | Rủi ro nếu bỏ qua sai kiểu |
| --- | --- | --- |
| Tài nguyên | `app.worker.thread-count` | Tạo ít/quá nhiều worker, hiệu năng không dự đoán |
| Timeout | `app.gateway.timeout` | Request treo lâu hoặc thất bại sớm |
| Số lần retry | `app.retry.max-attempts` | Gây tải ngoài ý muốn lên dịch vụ khác |
| Security | `app.security.session-ttl` | Thời hạn xác thực không đúng chính sách |
| Dung lượng | `app.upload.max-size` | Chấp nhận request quá lớn hoặc vô tình chặn request |
| Feature flags | `app.payment.enabled` | Bật/tắt sai chức năng |
| Connection pool | `app.database.max-connections` | Lãng phí tài nguyên hoặc nghẽn kết nối |

Đối với phần lớn cấu hình **có ý nghĩa vận hành**, mặc định `ignoreInvalidFields=false` đáng tin cậy hơn. Khi đó sai kiểu làm lỗi khởi động rõ ràng, phù hợp nguyên tắc **fail fast**.

Có thể cân nhắc `ignoreInvalidFields=true` khi đáp ứng được nhiều điều kiện:

- Trường cấu hình thực sự không thiết yếu.
- Default/giá trị ban đầu đã được thiết kế an toàn.
- Có test chứng minh object kết quả trong tình huống dữ liệu sai.
- Có cảnh báo hoặc quan sát bổ sung để biết cấu hình bị bỏ qua.
- Việc bỏ qua không tạo lỗ hổng bảo mật, sai lệch dữ liệu hay vi phạm SLA.

Đừng dùng cờ này để xử lý hàng loạt lỗi do typo trong biến môi trường production.

## 21. Một chiến lược khác: default tường minh và validation

Thay vì nới lỏng binding, dùng mặc định có chủ đích:

~~~yaml
app:
  worker:
    thread-count: "${WORKER_COUNT:4}"
    timeout: "${WORKER_TIMEOUT:5s}"
~~~

Điều này giải quyết trường hợp **không có biến môi trường**: `WORKER_COUNT` không có thì dùng `4`. Nhưng nếu biến `WORKER_COUNT=invalid` đã tồn tại, placeholder `${WORKER_COUNT:4}` vẫn chọn `invalid`; kết quả có thể lỗi khi bind.

Đó là hành vi hữu ích: thiếu biến môi trường là tình huống có default, còn biến môi trường sai kiểu là **lỗi cần sửa**.

Một cách khác với constructor binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int threadCount,
        @DefaultValue("5s") Duration timeout
) {}
~~~

`@DefaultValue` định nghĩa default khi tham số không được cấu hình. Nó cũng không phải công cụ tự thay thế mọi giá trị sai kiểu.

Khi cần ràng buộc mạnh, kết hợp `@Validated` và các constraint phù hợp. Như vậy hệ thống phân biệt:

- Thiếu giá trị nhưng có default an toàn.
- Có giá trị hợp lệ.
- Có giá trị sai kiểu.
- Có giá trị đúng kiểu nhưng sai nghiệp vụ.

Bốn trạng thái này không nên bị trộn thành một nhánh “cứ dùng mặc định”.

## 22. Cách kiểm thử bằng Spring Boot ApplicationContextRunner

`ApplicationContextRunner` của Spring Boot Test hữu ích để chạy một application context nhỏ với property values tự chọn và quan sát kết quả tạo bean.

Ví dụ kiểm tra hành vi strict binding:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    @Test
    void invalidIntegerShouldFailWhenBindingIsStrict() {
        runner.withPropertyValues(
                "app.worker.thread-count=not-a-number"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

Với class `WorkerProperties` mặc định `ignoreInvalidFields=false`, test trên giúp cố định yêu cầu “sai kiểu phải làm context thất bại”.

Để kiểm tra một kiểu JavaBean cho phép ignore, tạo class riêng:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = true
)
public class LenientWorkerProperties {

    private int threadCount = 4;

    public int getThreadCount() {
        return threadCount;
    }

    public void setThreadCount(int threadCount) {
        this.threadCount = threadCount;
    }
}
~~~

Bài test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class LenientWorkerPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(LenientWorkerProperties.class)
    static class TestConfig {}

    @Test
    void checkResultAfterInvalidPropertyWasIgnored() {
        new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class)
                .withPropertyValues(
                        "app.worker.thread-count=not-a-number"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    LenientWorkerProperties props =
                            context.getBean(LenientWorkerProperties.class);
                    assertThat(props.getThreadCount()).isEqualTo(4);
                });
    }
}
~~~

Ví dụ này minh họa **cách viết test để xác nhận hành vi của JavaBean cụ thể**, không có nghĩa mọi loại lỗi binding/constructor/list đều có kết quả như vậy. Nếu test thất bại trên cấu hình thực tế, hãy điều tra thay vì thay đổi kỳ vọng để che lỗi.

Các dependency test phổ biến gồm `spring-boot-starter-test` ở scope test, tùy cấu hình build của dự án.

## 23. Test phân biệt missing, invalid và unknown

Một bộ kiểm thử tốt nên có ít nhất các nhóm tình huống:

| Case | Dữ liệu đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Hợp lệ | `thread-count=8` | Giá trị cuối là 8 |
| Thiếu | Không có `thread-count` | Có default nào được áp dụng? |
| Sai kiểu | `thread-count=lots` | Strict binding có fail không? |
| Không có trường Java | `new-flag=true` | Unknown field được xử lý theo cấu hình nào? |
| Đúng kiểu nhưng không hợp lệ | `thread-count=-2` | Validation có từ chối không? |
| Bị override từ nguồn cao | YAML 8, env `invalid` | Có phát hiện nguồn cuối gây lỗi không? |
| Nested/list sai kiểu | `endpoints[1].timeout=bad` | Cả cấu trúc được xử lý ra sao? |

Không nhất thiết tạo hàng chục test cho mọi property, nhưng với các cấu hình ảnh hưởng đến vận hành, nên có ít nhất kiểm thử đại diện cho **giá trị thiếu, sai kiểu, và giá trị hợp lệ**.

Đặc biệt nếu dự án cho phép `ignoreInvalidFields=true`, test càng quan trọng vì ứng dụng có thể chạy tiếp mà không biểu lộ lỗi ngay ở startup.

## 24. Những nhầm lẫn phổ biến

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “`ignoreInvalidFields=true` làm mọi giá trị sai thành hợp lệ.” | Nó có thể bỏ qua một số lỗi binding; giá trị sai không được chuyển thành kiểu hợp lệ. |
| “Bật ignore nghĩa là dùng giá trị trong YAML ưu tiên thấp hơn.” | Không có bảo đảm tự fallback qua từng property source khi conversion từ nguồn cao sai. |
| “`ignoreInvalidFields` và `ignoreUnknownFields` giống nhau.” | Một cái liên quan invalid binding; cái kia liên quan tên thuộc tính không bind được. |
| “Không có khóa cũng là invalid field.” | Missing property là tình huống khác, cần default/nullable/validation. |
| “`ignoreInvalidFields` thay thế Bean Validation.” | Nó không kiểm tra các quy tắc như số dương hoặc URL hợp lệ. |
| “Chỉ cần JavaBean có field initializer thì mọi lỗi đều an toàn.” | Default có thể không phù hợp với môi trường và nhiều lỗi khác vẫn xuất hiện. |
| “Bật ignore là sửa được file YAML sai cú pháp.” | YAML parser cần đọc file thành công trước khi Binder hoạt động. |
| “`@Value` sẽ tự tuân theo cờ ignore trên `@ConfigurationProperties` khác.” | Đây không phải tùy chọn toàn cục của mọi đường đọc cấu hình. |
| “Có record thì ignore luôn giữ `@DefaultValue`.” | Constructor binding có semantics khác JavaBean; không nên giả định. |
| “Ứng dụng khởi động thành công nghĩa là cấu hình đúng.” | Giá trị sai có thể đã bị bỏ qua, hoặc lỗi nghiệp vụ chỉ xuất hiện về sau. |

## 25. Bài tập tự kiểm tra

### Bài 1 — Giá trị sai kiểu

File:

~~~properties
app.retry.max-attempts=abc
~~~

Class:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private int maxAttempts = 3;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Câu hỏi: Với mặc định của `@ConfigurationProperties`, Binder nên xử lý thế nào?

**Đáp án:** `ignoreInvalidFields=false` theo mặc định nên conversion từ `abc` sang `int` thường làm binding thất bại và báo lỗi. Giá trị khởi tạo `3` không có nghĩa lỗi phải được bỏ qua.

### Bài 2 — Bật ignore

Thêm:

~~~java
@ConfigurationProperties(
        prefix = "app.retry",
        ignoreInvalidFields = true
)
~~~

Với class JavaBean ở Bài 1, kết quả nào có thể quan sát được?

**Đáp án:** conversion error có thể bị bỏ qua, và field `maxAttempts` đã khởi tạo bằng `3` có thể được giữ nguyên. Cần có test trên bean cụ thể; không suy rộng cho mọi kiểu dữ liệu và cơ chế constructor binding.

### Bài 3 — Unknown hay invalid?

Class chỉ có `int maxAttempts`. YAML:

~~~yaml
app:
  retry:
    max-attempts: 5
    max-extra: true
~~~

Câu hỏi: `max-extra` không có trường tương ứng thì thuộc trường hợp nào?

**Đáp án:** unknown/unbound property. Nó liên quan `ignoreUnknownFields` hơn là `ignoreInvalidFields`.

### Bài 4 — Đúng kiểu nhưng sai nghiệp vụ

Có `thread-count=-5` và Java dùng `int threadCount`. Bật `ignoreInvalidFields=true` có tự bảo đảm số luồng dương không?

**Đáp án:** không. `-5` chuyển được sang `int` nên không phải conversion error. Dùng `@Min(1)` cùng validation hoặc kiểm tra rõ trong code.

### Bài 5 — Lỗi file và lỗi bind

Một file `application.yml` thiếu dấu ngoặc YAML và ứng dụng không khởi động. Thêm `ignoreInvalidFields=true` có xử lý được không?

**Đáp án:** không. Đây là lỗi phân tích cú pháp file, trước khi Binder có dữ liệu để liên kết với class.

### Bài 6 — Giá trị từ biến môi trường sai

File profile `application-prod.yml` có `app.worker.thread-count=8` nhưng môi trường cấp `APP_WORKER_THREADCOUNT=invalid`. Vì sao không thể kết luận bật ignore thì threadCount sẽ là 8?

**Đáp án:** biến môi trường thường ưu tiên hơn Config Data. Cờ ignore không phải một thuật toán tìm giá trị hợp lệ ở các nguồn thấp hơn. Cần sửa hoặc loại bỏ biến sai và xác nhận hành vi trong test.

### Bài 7 — Default theo kiểu binding

Một record:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        @DefaultValue("3") int maxAttempts
) {}
~~~

Khi không có `app.retry.max-attempts`, giá trị mong muốn là gì? Nếu cấp `abc` thì sao?

**Đáp án:** khi thiếu, default `3` có thể được áp dụng. Khi cấp `abc`, đó là conversion error; `@DefaultValue` không phải công cụ tự động thay thế mọi giá trị sai.

## 26. Ghi nhớ

- `@ConfigurationProperties(ignoreInvalidFields = true)` hướng Binder **bỏ qua những lỗi giá trị không hợp lệ mà cơ chế binding cho phép bỏ qua**; mặc định là **`false`**.
- Sai kiểu (`"abc"` vào `int`) khác với unknown field (không có thuộc tính Java tương ứng) và khác với thiếu khóa.
- `ignoreUnknownFields` là cờ riêng; giá trị mặc định thường là **`true`**.
- Với JavaBean binding, trường bị bỏ qua **có thể giữ giá trị khởi tạo** như `4`, `false` hoặc `null`; điều đó không bảo đảm đúng nghiệp vụ.
- Constructor binding, record, collection và nested object có semantics khác; không được mặc định suy ra cùng một kết quả fallback.
- **Giá trị đúng kiểu vẫn có thể sai nghiệp vụ**: dùng Bean Validation hoặc kiểm tra bất biến.
- `ignoreInvalidFields` không sửa YAML sai cú pháp, không sửa lỗi thiếu Config Data, không thay thế `@Value`/`Environment` và không đảm bảo ứng dụng luôn khởi động.
- Khi biến môi trường có ưu tiên cao hơn nhưng chứa dữ liệu sai, đừng kỳ vọng ignore sẽ tự chọn lại giá trị từ file thấp hơn.
- **Production thường nên giữ strict binding và fail fast** cho các giá trị vận hành quan trọng.
- Nếu chọn bỏ qua lỗi ở một trường không thiết yếu, hãy có default an toàn, test thể hiện hành vi và cơ chế quan sát hợp lý.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
