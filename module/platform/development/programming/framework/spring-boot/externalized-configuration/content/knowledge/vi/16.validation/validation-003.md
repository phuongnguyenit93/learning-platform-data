# Kích hoạt kiểm tra hợp lệ bằng `@Validated` trên cấu hình Spring Boot

## 1. Vì sao đọc được cấu hình vẫn chưa đủ?

Spring Boot hỗ trợ **Externalized Configuration**: ứng dụng có thể lấy thuộc tính từ `application.yml`, `application.properties`, biến môi trường, Java system properties, đối số dòng lệnh và các nguồn khác. Khi một class được đánh dấu bằng `@ConfigurationProperties`, Binder cố gắng chuyển những giá trị đó sang kiểu Java tương ứng.

Ví dụ:

~~~yaml
app:
  worker:
    thread-count: 8
    request-timeout: 10s
    service-name: order-worker
~~~

Class cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threadCount,
        Duration requestTimeout,
        String serviceName
) {}
~~~

Binder có thể chuyển `8` sang `int` và `10s` sang `Duration`. Tuy nhiên, nếu YAML khai báo:

~~~yaml
app:
  worker:
    thread-count: -8
    request-timeout: 0s
    service-name: " "
~~~

các giá trị này **vẫn có thể bind thành công**: `-8` là một số nguyên hợp lệ, `0s` là một thời lượng hợp lệ và chuỗi khoảng trắng là một `String` hợp lệ về mặt kiểu dữ liệu. Nhưng tất cả đều có thể vi phạm yêu cầu vận hành của một worker.

Vì thế, phải phân biệt hai tầng:

1. **Binding/conversion:** Có chuyển được giá trị cấu hình thành kiểu Java không?
2. **Validation:** Giá trị Java sau khi bind có thỏa điều kiện nghiệp vụ hay không?

Annotation `@Validated` trên một kiểu `@ConfigurationProperties` là cách phổ biến để yêu cầu Spring Boot thực hiện **Bean Validation** trên đối tượng cấu hình sau khi liên kết. Việc này giúp ứng dụng phát hiện cấu hình bất hợp lệ khi bean được tạo, thay vì chỉ gặp lỗi sau khi bắt đầu phục vụ request.

## 2. Kết quả mong muốn khi bật validation

Một lớp cấu hình có thể yêu cầu:

- Số worker ít nhất là 1 và không vượt quá giới hạn vận hành.
- Tên dịch vụ phải có nội dung, không chỉ gồm khoảng trắng.
- Địa chỉ máy chủ phải được cung cấp.
- Một nhóm cấu hình lồng nhau không được thiếu.
- Danh sách các endpoint phải chứa ít nhất một phần tử.
- Mỗi phần tử endpoint phải có tên và timeout hợp lệ.

Ví dụ hợp đồng cấu hình:

| Thuộc tính | Kiểu Java | Ràng buộc | Giá trị sai tiêu biểu |
| --- | --- | --- | --- |
| `app.worker.thread-count` | `int` | Từ 1 đến 32 | `0`, `-3`, `100` |
| `app.worker.service-name` | `String` | Không rỗng hoặc toàn khoảng trắng | `""`, `"  "` |
| `app.worker.request-timeout` | `Duration` | Không null; nếu cần, lớn hơn 0 | Khóa thiếu, `0s` |
| `app.worker.enabled` | `Boolean` | Phải được cấu hình nếu bắt buộc | Không có khóa |
| `app.worker.endpoints` | `List` | Có ít nhất một phần tử | Danh sách rỗng |
| `app.worker.endpoint.url` | `String` | Không rỗng; định dạng phù hợp | `""` |

Spring Boot không tự suy luận các quy tắc này chỉ từ tên field. Ta phải mô tả chúng bằng **Jakarta Bean Validation constraints**, thông qua annotation và/hoặc logic kiểm tra có chủ đích.

## 3. Ba nhóm annotation cần phân biệt

| Annotation | Package tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| `@ConfigurationProperties` | `org.springframework.boot.context.properties` | Khai báo prefix và đích binding của một nhóm cấu hình |
| `@Validated` | `org.springframework.validation.annotation` | Kích hoạt quá trình validation cho bean cấu hình khi có hạ tầng validation phù hợp |
| `@NotBlank`, `@Min`, `@NotNull`, `@Valid`... | `jakarta.validation...` | Khai báo điều kiện hoặc yêu cầu kiểm tra tiếp đối tượng lồng nhau |

Ví dụ:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threadCount,
        @NotBlank String serviceName
) {}
~~~

Ý nghĩa:

- `@ConfigurationProperties` cho Binder biết phải tìm các khóa bắt đầu bằng `app.worker`.
- `@Min(1)` kiểm tra `threadCount` không nhỏ hơn 1.
- `@NotBlank` yêu cầu `serviceName` không phải null, chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- `@Validated` đánh dấu đối tượng cấu hình cần được kiểm tra bởi cơ chế validation đã cấu hình.

**Quan trọng:** `@Validated` không tự định nghĩa ràng buộc nào. Nếu không có constraint thích hợp, việc thêm annotation đó không tự làm trường `threadCount` phải dương.

## 4. Chuẩn bị dependency Bean Validation

Trong dự án Spring Boot 3.x dùng hệ Jakarta, các annotation constraint nằm trong package `jakarta.validation`. Để thực thi chúng lúc runtime, ứng dụng cần một **Bean Validation provider**. Cách thông dụng là thêm Spring Boot Validation Starter.

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### Gradle (Groovy DSL)

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Starter này thường cung cấp hạ tầng Hibernate Validator phù hợp với phiên bản Spring Boot đang dùng. Chỉ có annotation `@NotBlank` trong source code, nhưng không có provider validation phù hợp lúc runtime, **không đủ để bảo đảm kiểm tra constraint sẽ diễn ra như mong đợi**.

Nếu dự án dùng Spring Boot 2.x cũ, nhiều ví dụ trên mạng sử dụng namespace `javax.validation`. Với Spring Boot 3.x, hãy dùng `jakarta.validation` theo hệ Jakarta EE mà Boot 3 hỗ trợ; không trộn ngẫu nhiên hai namespace.

Có thể dùng các constraint chuẩn:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
~~~

Từng annotation có semantics khác nhau; chọn đúng constraint cho đúng kiểu và yêu cầu nghiệp vụ.

## 5. Ví dụ đầy đủ: cấu hình worker có validation

Giả sử ứng dụng xử lý công việc nền cần cấu hình:

~~~yaml
# src/main/resources/application.yml
app:
  worker:
    service-name: invoice-worker
    thread-count: 6
    enabled: true
    request-timeout: 8s
~~~

Khai báo kiểu cấu hình bất biến:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotBlank String serviceName,
        @Min(1) @Max(32) int threadCount,
        @NotNull Boolean enabled,
        @NotNull Duration requestTimeout
) {}
~~~

Cách đọc:

- `serviceName` phải là chuỗi có nội dung.
- `threadCount` phải thuộc đoạn từ 1 đến 32.
- `enabled` phải được cung cấp khi dùng wrapper `Boolean` và `@NotNull`; nó có thể nhận `true` **hoặc** `false`.
- `requestTimeout` không được null, nhưng vẫn cần một ràng buộc khác nếu nghiệp vụ yêu cầu thời lượng lớn hơn 0.

Đăng ký các class cấu hình bằng `@ConfigurationPropertiesScan`:

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

Sau đó một service dùng cấu hình:

~~~java
package com.example.demo.service;

import com.example.demo.config.WorkerProperties;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {
    private final WorkerProperties properties;

    public WorkerService(WorkerProperties properties) {
        this.properties = properties;
    }

    public int configuredThreads() {
        return properties.threadCount();
    }
}
~~~

Khi bean `WorkerProperties` được tạo thông qua cơ chế configuration properties binding, Spring Boot lấy giá trị cấu hình, chuyển kiểu, tạo record, rồi thực hiện validation. Nếu constraint bị vi phạm, quá trình khởi tạo ứng dụng thường thất bại thay vì tạo ra một bean cấu hình sai mà những service khác tiếp tục sử dụng.

## 6. Các ví dụ không hợp lệ và vì sao bị từ chối

Giữ class ở phần trên. Xét từng file cấu hình sau.

### 6.1. Số luồng bằng 0

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 0
    enabled: true
    request-timeout: 8s
~~~

`0` có thể chuyển thành `int`, nhưng vi phạm `@Min(1)`. Đây là **lỗi validation**, không phải lỗi conversion.

### 6.2. Số luồng quá lớn

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 128
    enabled: true
    request-timeout: 8s
~~~

Giá trị vi phạm `@Max(32)`. Binder có thể chuyển `128` thành `int` mà không gặp vấn đề về kiểu; validator mới phát hiện giới hạn.

### 6.3. Tên chỉ có khoảng trắng

~~~yaml
app:
  worker:
    service-name: "   "
    thread-count: 8
    enabled: true
    request-timeout: 8s
~~~

`@NotBlank` không chỉ kiểm tra chuỗi khác null mà còn kiểm tra nội dung không phải toàn ký tự trắng.

### 6.4. Thiếu thuộc tính enabled

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 8
    request-timeout: 8s
~~~

Với tham số `Boolean enabled`, nếu không có giá trị được cung cấp và không có default, giá trị có thể là null; `@NotNull` từ chối trạng thái này.

Nếu dùng primitive `boolean enabled`, giá trị mặc định Java là `false`, nên `@NotNull` **không phân biệt được** giữa “người triển khai cố ý cấp false” với “không có giá trị”. Khi muốn yêu cầu khai báo tường minh, dùng wrapper `Boolean` cùng ràng buộc phù hợp hoặc một chiến lược kiểm tra sự tồn tại của property.

### 6.5. Timeout sai định dạng

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 8
    enabled: true
    request-timeout: tomorrow
~~~

`tomorrow` không phải chuỗi thời lượng hợp lệ theo converter thông thường. Việc bind sang `Duration` có thể thất bại **trước khi validator đánh giá `@NotNull`**. Đây là lý do validation không thay thế conversion; hai bước xử lý những loại lỗi khác nhau.

## 7. Thứ tự khái niệm: đọc nguồn → bind → validate

Có thể hình dung luồng:

~~~text
application.yml / .properties / environment / CLI
                       │
                       ▼
            Xác định property source
               và giá trị ưu tiên
                       │
                       ▼
           ConfigurationProperties Binder
              - tìm prefix và khóa
              - relaxed binding tên
              - chuyển kiểu dữ liệu
              - tạo object / gọi setter
                       │
                       ▼
               Bean Validation
            - @NotBlank / @Min...
            - kiểm tra @Valid nested
                       │
              ┌────────┴────────┐
              ▼                 ▼
           Hợp lệ             Vi phạm
              │                 │
              ▼                 ▼
        Bean cấu hình        Báo lỗi binding/
        dùng được            validation khi khởi tạo
~~~

Đây là sơ đồ khái niệm. Chi tiết triển khai và loại exception thay đổi theo phiên bản Spring Boot và cơ chế tạo bean, nhưng việc phân biệt **conversion** và **constraint validation** là quan trọng.

| Dữ liệu đầu vào | Kết quả chuyển kiểu | Kết quả validation |
| --- | --- | --- |
| `thread-count=8` | Thành `int 8` | Đạt `@Min(1)` và `@Max(32)` |
| `thread-count=0` | Thành `int 0` | Vi phạm `@Min(1)` |
| `thread-count=128` | Thành `int 128` | Vi phạm `@Max(32)` |
| `thread-count=abc` | Không chuyển được thành `int` | Có thể dừng trước validation |
| `service-name="  "` | Thành `String` | Vi phạm `@NotBlank` |
| `enabled=false` | Thành `Boolean.FALSE` | Đạt `@NotNull` |
| `enabled` thiếu | Có thể thành null | Vi phạm `@NotNull` |

Tính đúng về kiểu không đồng nghĩa với tính đúng về nghiệp vụ.

## 8. `@NotNull`, `@NotEmpty` và `@NotBlank`: ba thứ khác nhau

Ba constraint thường bị dùng lẫn:

| Constraint | Kiểu hay dùng | Điều kiện |
| --- | --- | --- |
| `@NotNull` | Object bất kỳ có thể null | Giá trị phải khác null |
| `@NotEmpty` | Chuỗi, collection, Map, array | Không null và không rỗng |
| `@NotBlank` | `CharSequence`/`String` | Không null và có ít nhất một ký tự không phải khoảng trắng |

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record NotificationSettings(
        @NotBlank String senderName,
        @NotEmpty java.util.List<String> channels,
        @NotNull Boolean enabled
) {}
~~~

Những trường hợp:

- `senderName="  "`: `@NotBlank` vi phạm.
- `channels=[]`: `@NotEmpty` vi phạm.
- `enabled=false`: `@NotNull` **không** vi phạm, vì false là giá trị có mặt.
- `senderName=""`: cả `@NotBlank` và `@NotEmpty` có thể từ chối, nhưng `@NotBlank` thể hiện rõ yêu cầu “không chỉ có khoảng trắng”.

Không dùng `@NotBlank` cho `int`, `Duration` hay một object bất kỳ. Constraint sai kiểu có thể dẫn tới lỗi cấu hình validator, chứ không tự chuyển thành phép kiểm tra tương đương.

## 9. Constraint cho số: `@Min`, `@Max`, `@Positive`

Với số lượng kết nối:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;

public record PoolSettings(
        @Min(1) @Max(100) int maxConnections,
        @Positive int retryBudget
) {}
~~~

Ý nghĩa:

- `@Min(1)`: số phải lớn hơn hoặc bằng 1.
- `@Max(100)`: số phải nhỏ hơn hoặc bằng 100.
- `@Positive`: số phải dương, tức lớn hơn 0.

Một ví dụ ràng buộc số thực:

~~~java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import java.math.BigDecimal;

public record SamplingSettings(
        @DecimalMin("0.0") @DecimalMax("1.0")
        BigDecimal sampleRate
) {}
~~~

Giá trị `0.0` và `1.0` là hợp lệ khi ràng buộc không đặt chế độ `inclusive=false`. Các annotation số không tự đảm bảo property **được cung cấp** khi dùng một wrapper nullable; nếu việc thiếu giá trị phải bị từ chối, kết hợp `@NotNull`.

Đặc biệt: `@Positive` không phải annotation tổng quát áp dụng cho mọi type có khái niệm dương, ví dụ `Duration`. Với thời lượng, dùng logic kiểm tra riêng hoặc custom constraint phù hợp.

## 10. `@Pattern`, `@Size` và validation chuỗi

Ví dụ yêu cầu tên môi trường chỉ gồm chữ thường, số và dấu gạch ngang:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record EnvironmentSettings(
        @NotBlank
        @Size(max = 30)
        @Pattern(regexp = "[a-z0-9]+(?:-[a-z0-9]+)*")
        String environmentName
) {}
~~~

Giải thích:

- `@NotBlank`: không thiếu, không rỗng và không chỉ chứa khoảng trắng.
- `@Size(max=30)`: chiều dài tối đa 30 ký tự theo semantics của constraint với chuỗi.
- `@Pattern`: giá trị phải khớp regular expression.

Khi đặt trong một `@Validated @ConfigurationProperties` hợp lệ, chuỗi `prod-us-1` có thể đạt, trong khi `PROD US` vi phạm pattern.

Với URL, `@NotBlank` chỉ kiểm tra có nội dung; không đảm bảo cú pháp URL hợp lệ, HTTPS được yêu cầu hay host nằm trong danh sách cho phép. Có thể sử dụng một constraint URL phù hợp, chuyển sang kiểu `URI` và kiểm tra scheme, hoặc viết custom constraint/constructor validation. Không nên giả định một regex đơn giản đã kiểm tra an toàn hoàn chỉnh cho URL.

## 11. Kích hoạt validation trong JavaBean binding

Không nhất thiết phải dùng record. Với JavaBean, vẫn có thể dùng `@Validated`:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {

    @Min(1)
    @Max(10000)
    private int maxEntries = 100;

    @NotBlank
    private String cacheName = "local-cache";

    public int getMaxEntries() {
        return maxEntries;
    }

    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }

    public String getCacheName() {
        return cacheName;
    }

    public void setCacheName(String cacheName) {
        this.cacheName = cacheName;
    }
}
~~~

File cấu hình:

~~~yaml
app:
  cache:
    max-entries: 500
    cache-name: product-cache
~~~

Bean được tạo theo cách phù hợp với `@ConfigurationProperties` và Binder gọi setter; sau đó validation đánh giá các constraint. Với `max-entries=0`, `@Min(1)` bị vi phạm.

Lưu ý: JavaBean có field initializer nên khi một khóa **không có**, giá trị được khởi tạo sẵn có thể tiếp tục tồn tại. Vì vậy, validation được chạy trên **trạng thái object cuối cùng**, không nhất thiết phân biệt được “có cấp giá trị” và “đang dùng default”. Nếu việc khai báo tường minh là bắt buộc, phải thiết kế kiểu/default/constraint phù hợp.

## 12. Validation trong constructor binding và Java record

Trong Spring Boot 3.x, một record `@ConfigurationProperties` được đăng ký phù hợp thường được bind bằng canonical constructor:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        @NotBlank String queueName,
        @Min(1) @Max(64) int workers,
        @NotNull Duration shutdownTimeout
) {}
~~~

Đây là một cách gọn để:

- Không cần getter và setter thông thường.
- Biểu đạt schema cấu hình bằng component types.
- Gắn constraint ngay vào component.
- Làm cho object không bị sửa trường sau khi tạo.

Tuy nhiên, record bất biến ở mức field reference không đảm bảo tính bất biến sâu nếu component là `List` hoặc `Map` có thể thay đổi. Nếu cần dữ liệu không thể thay đổi sau khi khởi động, cân nhắc defensive copy, và vẫn dùng validation cho nội dung collection.

**Không nhầm constructor binding với dependency injection của bean.** `@ConfigurationPropertiesScan` và `@EnableConfigurationProperties` là hai cách đăng ký phù hợp cho kiểu cấu hình dùng constructor binding; không thêm `@Component` vào record chỉ để buộc Spring tìm nó như bean thông thường.

## 13. Kiểm tra đối tượng lồng nhau với `@Valid`

Một cấu hình thực tế có thể gồm nhiều cấp:

~~~yaml
app:
  client:
    name: catalog-client
    connection:
      host: catalog.example.org
      port: 8443
~~~

Record:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String name,
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {}
}
~~~

Ở đây:

- `@NotNull` yêu cầu `connection` phải tồn tại.
- `@Valid` yêu cầu validator **đi tiếp vào đối tượng `connection`** và kiểm tra các constraint bên trong.
- `@NotBlank` kiểm tra `host`.
- `@Min` và `@Max` kiểm tra cổng trong khoảng 1–65535.

Nếu bỏ `@Valid`, không nên mặc định rằng validator luôn tự đi sâu vào mọi nested object. Trong Bean Validation, **cascade validation** là hành vi cần được yêu cầu rõ ràng.

### Tại sao `@NotNull` và `@Valid` thường đi cùng nhau?

Một nested property có thể hoàn toàn thiếu trong cấu hình:

~~~yaml
app:
  client:
    name: catalog-client
~~~

Với constructor binding, `connection` có thể thành null nếu không có giá trị và không có default. Khi đối tượng con null, `@Valid` không tự biến nó thành một object rồi kiểm tra các field `host` và `port`. `@NotNull` sẽ phát hiện rằng **toàn bộ nhóm bắt buộc đã thiếu**.

Có thể coi:

- `@NotNull`: bắt buộc có object con.
- `@Valid`: khi có object con, kiểm tra các điều kiện bên trong.

Hai yêu cầu khác nhau, không thay thế cho nhau.

## 14. Trường hợp nested object không có cấu hình nào

Spring Boot có hỗ trợ tạo object lồng nhau qua constructor binding với empty `@DefaultValue` khi phù hợp:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @DefaultValue Worker worker
) {
    public record Worker(
            @Min(1) int threads,
            @NotNull String name
    ) {}
}
~~~

Ý tưởng: empty `@DefaultValue` trên `worker` yêu cầu Binder tạo nested object ngay cả khi không có thuộc tính nào bên dưới `app.worker`, miễn là việc tạo object có thể thực hiện được. Nếu không có child configuration, `threads` có thể nhận giá trị mặc định của kiểu primitive còn `name` có thể null; validation sau đó có thể phát hiện các constraint bị vi phạm.

Không nên dùng empty default chỉ để che việc thiếu cả nhóm cấu hình. Nếu `worker` là nhóm bắt buộc, `@NotNull` trên object con và ràng buộc nội bộ có thể mô tả ý định rõ hơn. Nếu cần object con với default thực sự hợp lệ, hãy thiết kế `@DefaultValue("...")` cho từng tham số cần thiết.

Đây là ví dụ minh họa mối quan hệ giữa **tạo nested object** và **validate nested object**; không phải lời khuyên thêm `@DefaultValue` vào mọi object lồng nhau.

## 15. Validation cho danh sách và các phần tử bên trong

Giả sử cấu hình danh sách endpoint:

~~~yaml
app:
  upstreams:
    - name: catalog
      base-url: https://catalog.example.org
      weight: 10
    - name: inventory
      base-url: https://inventory.example.org
      weight: 20
~~~

Java:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record UpstreamProperties(
        @NotEmpty List<@Valid Upstream> upstreams
) {
    public record Upstream(
            @NotBlank String name,
            @NotBlank String baseUrl,
            @Min(1) int weight
    ) {}
}
~~~

Ý nghĩa:

1. `@NotEmpty` yêu cầu danh sách `upstreams` không null và có ít nhất một phần tử.
2. `List<@Valid Upstream>` yêu cầu validator đi vào từng phần tử.
3. `@NotBlank` và `@Min` áp dụng trên từng `Upstream`.

Nếu phần tử thứ hai có `weight=0`, thì type conversion sang `int` vẫn thành công, nhưng validation sẽ phát hiện phần tử đó vi phạm ràng buộc.

Nếu cấu hình chỉ có:

~~~yaml
app:
  upstreams: []
~~~

`@NotEmpty` phát hiện danh sách rỗng.

Một lưu ý: `@NotEmpty` **không kiểm tra các phần tử bên trong có hợp lệ**. Muốn kiểm tra nội dung phần tử phải có `@Valid` hoặc các container-element constraints phù hợp.

## 16. Validation cho Map và các value object

Với Map các tenant:

~~~yaml
app:
  tenants:
    team-a:
      quota: 100
      region: asia
    team-b:
      quota: 200
      region: europe
~~~

Java:

~~~java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        @NotEmpty Map<String, @Valid Tenant> tenants
) {
    public record Tenant(
            @Min(1) int quota,
            @NotBlank String region
    ) {}
}
~~~

`@NotEmpty` kiểm tra Map phải có entry. `@Valid` trên type argument yêu cầu đi sâu vào các `Tenant` để kiểm tra quota và region.

Nếu key của Map cần ràng buộc riêng, Bean Validation hỗ trợ các **container-element constraints** theo khả năng của provider. Ví dụ một mô hình có thể yêu cầu key không rỗng bằng `Map<@NotBlank String, @Valid Tenant>`. Cần đảm bảo runtime validator hỗ trợ các constraint trên type arguments và viết test tương ứng.

Nếu Map có key chứa dấu chấm hoặc ký tự đặc biệt, cú pháp binding có thể cần bracket notation trong YAML, nhưng đó là vấn đề **mô tả tên thuộc tính khi bind**, khác với việc `@Valid` kiểm tra value sau binding.

## 17. Ràng buộc thời lượng: `@NotNull` không đồng nghĩa `Duration` dương

Dự án hay dùng:

~~~java
@NotNull Duration timeout
~~~

Constraint này chỉ yêu cầu `timeout` **khác null**. Nó không ngăn những giá trị như `Duration.ZERO` hoặc thời lượng âm nếu Binder chấp nhận chúng.

Ví dụ:

~~~yaml
app:
  retry:
    timeout: 0s
~~~

`0s` có thể chuyển thành `Duration.ZERO`, vẫn đạt `@NotNull`.

Nếu yêu cầu thời lượng phải dương, có thể kiểm tra trong constructor:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        @NotNull Duration timeout
) {
    public RetryProperties {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.retry.timeout must be positive");
        }
    }
}
~~~

Giải pháp này kiểm tra bất biến ngay khi record được tạo, **khác** với việc dùng Bean Validation constraint. Nếu muốn có cùng khả năng mô tả quy tắc cho nhiều `Duration`, có thể tạo **custom Bean Validation constraint** và một `ConstraintValidator` thích hợp.

Không đặt `@Positive` lên `Duration` chỉ vì tên annotation trông phù hợp: constraint đó được thiết kế cho những kiểu số được Bean Validation hỗ trợ, không phải cho mọi class có phép so sánh với 0.

## 18. Default không thay thế validation

Giả sử:

~~~yaml
app:
  worker:
    thread-count: "${WORKER_COUNT:4}"
~~~

Khi biến môi trường `WORKER_COUNT` không có, placeholder có default `4`. Nhưng khi biến được cấp:

~~~bash
export WORKER_COUNT=0
~~~

placeholder giải quyết thành `0`; conversion sang `int` thành công; rồi `@Min(1)` mới từ chối.

Default chỉ xử lý **thiếu giá trị tham chiếu**, không kiểm tra giá trị có hợp lý hay không.

Tương tự, trong constructor binding có thể dùng:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int threadCount
) {}
~~~

`@DefaultValue("4")` mô tả default khi không có giá trị bind cho tham số. `@Min(1)` mô tả constraint. Hai annotation bổ sung cho nhau nhưng có trách nhiệm khác nhau:

| Tình huống | Default | Validation |
| --- | --- | --- |
| Không cấu hình số luồng | Có thể cung cấp 4 | Kiểm tra 4 hợp lệ |
| Cấu hình `thread-count=6` | Không cần dùng default | Kiểm tra 6 hợp lệ |
| Cấu hình `thread-count=0` | Không thay 0 bằng 4 | `@Min(1)` từ chối |
| Cấu hình `thread-count=abc` | Không tự sửa dữ liệu sai kiểu | Binding có thể thất bại trước validation |

Đừng coi một default hợp lý là bằng chứng rằng mọi cấu hình runtime đều an toàn.

## 19. Thứ tự ưu tiên cấu hình và validation

Giả sử `application.yml` có:

~~~yaml
app:
  worker:
    thread-count: 4
~~~

`application-prod.yml` có:

~~~yaml
app:
  worker:
    thread-count: 8
~~~

Môi trường chạy cấp:

~~~bash
APP_WORKER_THREADCOUNT=0
~~~

Khi profile `prod` hoạt động, biến môi trường thường có ưu tiên cao hơn Config Data. Binder có thể nhận `0` thay vì giá trị `8` trong file production. Nếu class khai báo `@Min(1)` và bật `@Validated`, ứng dụng có thể thất bại ở validation.

Điều này hữu ích vì validation bảo vệ **giá trị cuối sau khi xét nguồn cấu hình**, không chỉ bảo vệ từng file riêng lẻ.

Đừng vì nhìn thấy giá trị hợp lệ trong `application-prod.yml` mà kết luận ứng dụng đã an toàn. Một nguồn ưu tiên cao hơn, chẳng hạn CLI argument, environment variable hoặc cấu hình test, có thể thay đổi kết quả.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.worker.thread-count=0
~~~

Trong thứ tự ưu tiên thông thường, đối số `--app.worker.thread-count=0` có thể thắng Config Data và khiến constraint `@Min(1)` bị vi phạm.

## 20. `@Validated` khác `@Valid` ở vai trò kích hoạt

Hai annotation thường xuất hiện cùng nhau nhưng không phải một:

- `@Validated`: annotation của Spring, dùng để chỉ ra việc validation cho bean cấu hình hoặc để chọn validation groups trong các ngữ cảnh hỗ trợ.
- `@Valid`: annotation của Jakarta Bean Validation, thường yêu cầu **cascade validation** vào một object/con phần tử bên trong.

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host
    ) {}
}
~~~

Không nên bỏ `@Validated` ở root chỉ vì đã đặt `@Valid` trên nested property rồi giả định Spring Boot nhất định sẽ kích hoạt kiểm tra root. Cũng không nên đặt chỉ `@Validated` ở root rồi mặc định mọi nested object đều được kiểm tra sâu.

Trong một cấu hình có cấu trúc:

1. Đánh dấu **root properties class** cần validation.
2. Đặt constraint trên những trường cụ thể.
3. Đặt `@Valid` tại những ranh giới cần đi sâu vào object hoặc phần tử.
4. Dùng `@NotNull`/`@NotEmpty` khi cần yêu cầu nested object/collection phải xuất hiện.

Đó là cách diễn đạt rõ cả **kích hoạt** và **phạm vi** validation.

## 21. Validation trên Spring bean thông thường và trên `@ConfigurationProperties`

`@Validated` cũng có thể dùng ở các ngữ cảnh khác trong Spring, chẳng hạn method validation. Tuy nhiên, bài này tập trung vào **validation của giá trị configuration properties khi bind**, không phải kiểm tra tham số HTTP request hoặc method invocation nói chung.

Ví dụ class service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Validated
@Service
public class PaymentService {
    // Có thể tham gia method validation
}
~~~

Mục đích ở đây khác với:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotBlank String merchantId
) {}
~~~

Với `PaymentProperties`, ta muốn đảm bảo bean cấu hình vừa tạo không chứa merchant ID rỗng. Với service, method validation nếu được cấu hình có thể kiểm tra các lời gọi phương thức theo constraint tương ứng.

Đừng trộn lỗi cấu hình startup với lỗi validation của request DTO hoặc validation của một service method. Chúng cùng dùng Bean Validation nhưng chạy tại các điểm trong vòng đời ứng dụng khác nhau.

## 22. Khi nào validation được thực thi?

Đối với bean `@ConfigurationProperties` được tạo và bind trong quá trình khởi động thông thường, validation được thực hiện như một phần của việc xây dựng bean. Nếu bean có constraint bị vi phạm, quá trình khởi tạo application context thường thất bại.

Nhưng không nên phát biểu tuyệt đối “mọi lỗi validation luôn xuất hiện tại dòng đầu tiên của chương trình”. Thời điểm cụ thể còn phụ thuộc:

- Bean có được tạo ngay hay được khởi tạo lazy.
- Cách class `@ConfigurationProperties` được đăng ký.
- Bean Validation provider có thực sự sẵn sàng không.
- Có sử dụng cơ chế tạo bean đặc biệt hoặc refresh riêng không.
- Có đặt constraint đúng vị trí hay không.

Đối với ứng dụng cần fail fast, hãy bảo đảm các bean cấu hình quan trọng được khởi tạo trong vòng đời startup bình thường và có kiểm thử chứng minh điều đó.

Cũng không nên cho rằng việc thay đổi `application.yml` sau khi Java process đã chạy sẽ tự kích hoạt validation lại; Config Data và các bean cấu hình thường được nạp/bind lúc startup, trừ khi có cơ chế refresh riêng.

## 23. Lỗi thường thấy khi validation thất bại

Một lỗi Bean Validation trên `@ConfigurationProperties` có thể được báo trong chuỗi exception của quá trình bind hoặc khởi tạo bean. Tùy phiên bản, ta có thể thấy các thành phần như `ConfigurationPropertiesBindException`, `BindException`, `BindValidationException` hoặc thông báo hiển thị trường, giá trị, constraint bị vi phạm.

Ví dụ minh họa, **không phải thông báo cố định**:

~~~text
Failed to bind properties under 'app.worker'
to com.example.demo.config.WorkerProperties

Property: app.worker.thread-count
Value: "0"
Reason: must be greater than or equal to 1
~~~

Khi thấy lỗi kiểu này, không nên chỉ sửa annotation để ứng dụng khởi động được. Quy trình phân tích:

1. Xác định **prefix** của properties class, ví dụ `app.worker`.
2. Tìm **tên property** bị vi phạm, ví dụ `thread-count`.
3. Xác định nguồn nào đang cung cấp **giá trị cuối cùng**.
4. Xem violation thuộc **conversion**, **Bean Validation**, hay một lỗi constructor/bean creation.
5. Sửa giá trị cấu hình hoặc điều chỉnh constraint nếu yêu cầu nghiệp vụ thật sự thay đổi.
6. Chạy lại test và startup với môi trường liên quan.

Nếu phải log dữ liệu cấu hình, tránh in secret hoặc chuỗi nhạy cảm. Một thông báo exception có thể chứa giá trị cấu hình, nên cần bảo vệ log trong production.

## 24. `ignoreInvalidFields` không thay thế validation

`@ConfigurationProperties` có các thuộc tính cấu hình Binder như:

~~~java
@ConfigurationProperties(
        prefix = "app.worker",
        ignoreInvalidFields = false,
        ignoreUnknownFields = true
)
~~~

Hai cờ này thường bị nhầm với validation:

- `ignoreInvalidFields` ảnh hưởng đến cách Binder xử lý một số lỗi giá trị không bind được; mặc định là `false`.
- `ignoreUnknownFields` ảnh hưởng đến các thuộc tính không có đích tương ứng trong class; mặc định là `true`.
- `@Validated` và các constraint kiểm tra giá trị **sau khi đã bind**.

Ví dụ `thread-count=abc` là sai kiểu, còn `thread-count=-3` có kiểu `int` hợp lệ nhưng vi phạm `@Min(1)`.

Bật `ignoreInvalidFields=true` không phải cách làm tất cả constraint biến mất. Nếu Binder bỏ qua một giá trị sai và để lại default ban đầu, validation vẫn kiểm tra **giá trị cuối của object**. Nếu default đạt constraint, object có thể được chấp nhận dù người triển khai thực tế đã cung cấp chuỗi sai; đây là một rủi ro cần hiểu rõ.

Với cấu hình vận hành quan trọng, thường nên giữ **strict binding** để sai kiểu bị phát hiện, đồng thời bật validation để phát hiện giá trị đúng kiểu nhưng không hợp lệ.

## 25. Missing property và primitive default: một bẫy phổ biến

Giả sử:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Min(0) int retryCount,
        @NotNull boolean enabled
) {}
~~~

Đây **không** phải cách bảo đảm hai khóa bắt buộc được cấp. Lý do:

- Primitive `int` có thể nhận `0` khi thiếu giá trị.
- `@Min(0)` chấp nhận `0`.
- Primitive `boolean` không thể null, nên `@NotNull` không có ý nghĩa phát hiện sự vắng mặt.

Nếu muốn bắt buộc người triển khai khai báo:

~~~java
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull Integer retryCount,
        @NotNull Boolean enabled
) {}
~~~

Khi không có thuộc tính và không có default, wrapper có thể là null, để constraint kiểm tra.

Nếu `retryCount` phải lớn hơn hoặc bằng 1:

~~~java
@NotNull @Min(1) Integer retryCount
~~~

Với `Boolean enabled`, `@NotNull` cho phép cả false lẫn true; nó chỉ yêu cầu có giá trị.

Khi muốn giá trị mặc định thay vì yêu cầu phải có, khai báo `@DefaultValue` hoặc default của cấu hình. **Bắt buộc** và **có default** là hai ý định khác nhau, cần chọn một cách có chủ đích.

## 26. Kiểm tra cross-field: khi một constraint đơn không đủ

Có những quy tắc cần nhìn **nhiều thuộc tính cùng lúc**, ví dụ:

- Nếu bật TLS thì phải cung cấp trust store.
- Nếu bật retry thì retry count phải dương.
- Khi `mode=REMOTE` thì endpoint phải không rỗng.
- Nếu một tính năng chỉ cho phép production thì active profile phải phù hợp.

Các constraint đơn như `@NotBlank` hay `@Min` không thể tự mô tả đầy đủ quan hệ này. Ví dụ:

~~~yaml
app:
  sender:
    mode: REMOTE
    endpoint: ""
~~~

Có thể tạo một đối tượng cấu hình với constraint cấp class tùy biến hoặc kiểm tra bất biến ở constructor:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.sender")
public record SenderProperties(
        Mode mode,
        String endpoint
) {
    public enum Mode { LOCAL, REMOTE }

    public SenderProperties {
        if (mode == Mode.REMOTE &&
                (endpoint == null || endpoint.isBlank())) {
            throw new IllegalArgumentException(
                    "app.sender.endpoint is required in REMOTE mode");
        }
    }
}
~~~

Đây là **constructor invariant**, không phải `@Validated` constraint. Nếu dự án muốn lỗi được đưa vào cùng cơ chế Jakarta Bean Validation, có thể định nghĩa một **class-level custom constraint** với `ConstraintValidator`.

Khi nào dùng cách nào?

| Phương án | Phù hợp khi |
| --- | --- |
| Constraint chuẩn trên field | Một thuộc tính có quy tắc độc lập |
| Constructor check | Bất biến đơn giản, cần từ chối object không hợp lệ ngay khi tạo |
| Class-level custom Bean Validation constraint | Quy tắc liên quan nhiều field, cần violation thống nhất hoặc tái sử dụng |

Không nên viết logic nghiệp vụ phức tạp trong getter cấu hình chỉ để giấu việc thiếu validation.

## 27. Ví dụ custom constraint cho timeout dương

Nếu nhiều properties class cần yêu cầu `Duration` lớn hơn 0, có thể định nghĩa annotation riêng.

Annotation:

~~~java
package com.example.demo.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PositiveDurationValidator.class)
public @interface PositiveDuration {
    String message() default "must be a positive duration";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
package com.example.demo.validation;

import java.time.Duration;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class PositiveDurationValidator
        implements ConstraintValidator<PositiveDuration, Duration> {

    @Override
    public boolean isValid(
            Duration value,
            ConstraintValidatorContext context) {
        // Null được xử lý bởi @NotNull khi thuộc tính là bắt buộc.
        return value == null || (!value.isZero() && !value.isNegative());
    }
}
~~~

Sử dụng:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import com.example.demo.validation.PositiveDuration;

@Validated
@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        @NotNull @PositiveDuration Duration timeout
) {}
~~~

Khi `timeout=0s`, conversion có thể thành công nhưng custom validator từ chối.

Hai nguyên tắc:

1. Không tự coi null là invalid trong mọi custom constraint nếu đã dùng `@NotNull` để biểu đạt tính bắt buộc; tách trách nhiệm giúp tái sử dụng.
2. Custom validator không nên có network call hoặc side effect chỉ để kiểm tra một giá trị cấu hình.

Trong dự án thực tế, custom constraint là một phần của code, cần test riêng cho giá trị null, zero, âm, dương.

## 28. Kiểm thử startup thất bại bằng `ApplicationContextRunner`

Một cách đáng tin cậy để xác minh validation hoạt động là tạo một application context nhỏ trong unit/integration test Spring Boot.

Class cấu hình đang thử:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotBlank String serviceName,
        @Min(1) @Max(32) int threadCount
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerPropertiesValidationTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void validValuesCreatePropertiesBean() {
        runner.withPropertyValues(
                "app.worker.service-name=invoice-worker",
                "app.worker.thread-count=6"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            WorkerProperties props =
                    context.getBean(WorkerProperties.class);

            assertThat(props.threadCount()).isEqualTo(6);
            assertThat(props.serviceName()).isEqualTo("invoice-worker");
        });
    }

    @Test
    void zeroThreadCountFailsValidation() {
        runner.withPropertyValues(
                "app.worker.service-name=invoice-worker",
                "app.worker.thread-count=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void blankServiceNameFailsValidation() {
        runner.withPropertyValues(
                "app.worker.service-name=   ",
                "app.worker.thread-count=3"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

Ví dụ giả định dependency Spring Boot Test, AssertJ, JUnit 5 và Bean Validation provider đã được khai báo đúng trong test runtime. Với dự án cần chính xác về nguyên nhân lỗi, có thể kiểm tra startup failure và chuỗi nguyên nhân để chứng minh đó là validation violation chứ không phải lỗi thiếu bean khác.

`ApplicationContextRunner` đặc biệt phù hợp để giữ test nhỏ, không cần khởi chạy toàn bộ web server hay truy cập database.

## 29. Kiểm thử nested validation

Với class:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        @NotNull @Valid Remote remote
) {
    public record Remote(
            @NotBlank String host
    ) {}
}
~~~

Có thể kiểm tra ít nhất ba tình huống:

| Test case | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Nested hợp lệ | `app.gateway.remote.host=api.example.org` | Context tạo được bean |
| Nested thiếu hẳn | Không có khóa `app.gateway.remote.*` | `@NotNull` trên `remote` phát hiện |
| Nested tồn tại nhưng host trống | `app.gateway.remote.host=` | `@Valid` đi vào `Remote`, `@NotBlank` phát hiện |

Nếu bỏ `@Valid` khỏi root record, case nested host rỗng có thể không bị kiểm tra sâu; đó là lý do test cascade validation là một phần quan trọng của hợp đồng cấu hình.

Đối với nhiều tầng nested object, đặt `@Valid` ở từng ranh giới mà Bean Validation cần đi qua. Không nên giả định một `@Valid` trên root sẽ tự động đi qua mọi tầng sâu mà không có cascade metadata ở các tầng tiếp theo.

## 30. `@Validated` có hỗ trợ validation groups không?

Jakarta Bean Validation hỗ trợ **groups**, tức nhóm các constraint được kiểm tra theo mục đích. Annotation Spring `@Validated` cũng có thuộc tính cho phép chỉ định nhóm trong những ngữ cảnh được hỗ trợ.

Ví dụ khái niệm:

~~~java
public interface ProductionChecks {}

public record ConnectionSettings(
        @NotBlank String host,
        @NotBlank(groups = ProductionChecks.class) String certificateAlias
) {}
~~~

Trong mô hình Bean Validation, constraint không có `groups` thuộc nhóm mặc định, còn constraint có `groups = ProductionChecks.class` có thể được kiểm tra khi yêu cầu nhóm tương ứng.

Tuy nhiên, việc chọn groups cho `@ConfigurationProperties` cần xét cách Spring Boot tạo validator và đánh giá annotation trong phiên bản đang dùng. Không nên copy một ví dụ group phức tạp từ validation của Spring MVC rồi giả định nó áp dụng nguyên xi cho mọi loại configuration properties bean.

Với một đối tượng cấu hình duy nhất cần hợp lệ ở mọi môi trường, lựa chọn đơn giản hơn thường là:

- Một tập constraint áp dụng ở mọi môi trường.
- Những tùy chọn cụ thể theo môi trường có kiểu/nhóm riêng.
- Một custom constraint cấp class cho các quy tắc phụ thuộc môi trường, nếu thực sự cần.

Chỉ dùng groups khi dự án có nhu cầu rõ ràng và có test xác nhận hành vi.

## 31. Những lỗi thường gặp khi bật `@Validated`

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có `@Min(1)` nhưng `0` vẫn được chấp nhận | Chưa kích hoạt validation trên bean cấu hình hoặc thiếu provider | Kiểm tra `@Validated`, dependency validation và cách đăng ký bean |
| `@Valid` trên nested nhưng cả nhóm con thiếu vẫn không lỗi | Nested object null; cascade không đồng nghĩa bắt buộc có object | Thêm `@NotNull` cho object con |
| Có `@NotNull` nhưng chuỗi toàn khoảng trắng vẫn lọt | `@NotNull` chỉ kiểm tra khác null | Dùng `@NotBlank` |
| `@NotNull boolean` không phát hiện thiếu khóa | Primitive không thể null | Dùng `Boolean` và `@NotNull` |
| Có `@NotEmpty` trên list nhưng phần tử sai vẫn được nhận | Chưa cascade vào từng phần tử | Dùng `List<@Valid Item>` hoặc `@Valid` phù hợp |
| Có `@NotNull Duration` nhưng `0s` vẫn hợp lệ | Constraint chỉ kiểm tra khác null | Dùng custom positive-duration constraint/constructor check |
| `thread-count=abc` báo lỗi trước validation | Conversion sang `int` thất bại | Sửa dữ liệu sai kiểu; đây là lỗi binding |
| Thêm `@Validated` nhưng context không tìm thấy properties bean | Chưa đăng ký `@ConfigurationProperties` class | Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Record có `@Component` và constructor binding không như mong đợi | Bean được tạo theo cơ chế dependency injection thông thường | Đăng ký record bằng cơ chế configuration properties |
| Test validation vẫn thành công dù constraint cần lỗi | Test runtime thiếu provider hoặc tạo object bằng `new` thay vì Binder | Test bằng context và đầy đủ dependency |
| Giá trị trong YAML hợp lệ nhưng startup vẫn lỗi | Nguồn ưu tiên cao hơn có thể ghi đè | Kiểm tra env, system properties và CLI |
| Default hợp lệ che việc chưa cấu hình | Mặc định đã được áp dụng trước validation | Quyết định rõ muốn default hay muốn fail khi thiếu |
| Có `ignoreInvalidFields=true` nên cấu hình sai vẫn chạy | Conversion error có thể bị bỏ qua | Ưu tiên strict binding và dùng validation |
| Validation chạy không đúng như test kỳ vọng | Không đúng version/namespace của Jakarta hoặc ranh giới cascade | Kiểm tra dependency, import và test nested |

## 32. Chẩn đoán trong môi trường Docker/Kubernetes

Một ứng dụng có file:

~~~yaml
app:
  worker:
    service-name: invoice-worker
    thread-count: 6
~~~

Docker Compose có thể ghi đè:

~~~yaml
services:
  worker:
    image: example/invoice-worker:latest
    environment:
      APP_WORKER_SERVICENAME: "invoice-worker"
      APP_WORKER_THREADCOUNT: "0"
~~~

Biến `APP_WORKER_THREADCOUNT` được chuyển theo quy tắc relaxed binding của Spring Boot từ `app.worker.thread-count` và có thể có ưu tiên cao hơn file cấu hình trong JAR. Lúc khởi động, Bean Validation `@Min(1)` có thể từ chối `0`.

Trong Kubernetes:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoice-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: invoice-worker
  template:
    metadata:
      labels:
        app: invoice-worker
    spec:
      containers:
        - name: worker
          image: example/invoice-worker:latest
          env:
            - name: APP_WORKER_THREADCOUNT
              value: "0"
            - name: APP_WORKER_SERVICENAME
              value: "invoice-worker"
~~~

Nếu bean cấu hình bắt buộc được bind lúc startup và validation hoạt động, container có thể thoát sớm vì cấu hình không hợp lệ. Đó là một tín hiệu để sửa manifest/ConfigMap/Secret hoặc giá trị được inject, thay vì vô hiệu hóa constraint.

Trong triển khai thật:

- Đặt các key và giới hạn hợp lệ trong tài liệu vận hành.
- Kiểm tra manifest và biến môi trường trước khi rollout.
- Quan sát log startup có kiểm soát, không làm lộ secret.
- Phân biệt lỗi config với lỗi liveness/readiness hoặc lỗi kết nối downstream.
- Sửa nguồn cấp sai, sau đó redeploy theo quy trình bình thường.

Bean Validation là một lớp bảo vệ mạnh, nhưng không thay thế việc kiểm tra sẵn các manifest và thử nghiệm triển khai.

## 33. Không validate bí mật bằng cách đưa chúng vào log

Một số thuộc tính như API key, password, token hoặc private key có thể cần ràng buộc hiện diện:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String apiKey
) {}
~~~

Constraint `@NotBlank` giúp phát hiện một API key thiếu hoặc chỉ có khoảng trắng. Nhưng nó không chứng minh key còn hiệu lực, thuộc đúng tenant hay có quyền sử dụng dịch vụ bên ngoài.

Không nên viết custom validator lấy key rồi gửi request ra internet để kiểm tra ngay trong quá trình bind, vì điều này làm startup phụ thuộc mạng và có thể phơi lộ credential. Kiểm tra định dạng/hiện diện nên tách khỏi bước thử kết nối thực tế.

Khi cần quan sát sự cố, tránh log toàn bộ bean cấu hình có chứa secret. Java record tự tạo `toString()` có thể in các component, nên càng cần cẩn thận nếu record chứa password hay token.

## 34. Bài tập thực hành

### Bài 1 — Đúng kiểu nhưng sai giá trị

Cho:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @Min(1) int minConnections,
        @Max(200) int maxConnections
) {}
~~~

YAML:

~~~yaml
app:
  pool:
    min-connections: 0
    max-connections: 100
~~~

Hỏi: phép chuyển kiểu có thành công không? Validation có nên chấp nhận không?

**Đáp án:** cả `0` và `100` đều có thể chuyển thành `int`. Nhưng `minConnections=0` vi phạm `@Min(1)`, nên validation từ chối khi được kích hoạt phù hợp.

### Bài 2 — `@NotNull` với boolean

Cho:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull boolean enabled
) {}
~~~

Nếu không có `app.enabled`, `@NotNull` có đảm bảo ứng dụng báo lỗi không?

**Đáp án:** không. Primitive `boolean` không thể null; để nhận biết giá trị thiếu, dùng `Boolean` cùng `@NotNull` hoặc một cơ chế kiểm tra sự hiện diện có chủ đích.

### Bài 3 — Kiểm tra nhóm con

Cho:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull @Valid Client client
) {
    public record Client(@NotBlank String endpoint) {}
}
~~~

Nếu chỉ cấu hình `app.client.endpoint=" "`, ràng buộc nào phát hiện lỗi?

**Đáp án:** `@Valid` yêu cầu đi vào `Client`, sau đó `@NotBlank` từ chối endpoint chỉ có khoảng trắng. `@NotNull` trên client chỉ yêu cầu object con tồn tại.

### Bài 4 — Danh sách rỗng

Một `List<Endpoint>` không được rỗng và mỗi Endpoint phải có name. Hãy chọn annotation.

**Đáp án gợi ý:**

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty java.util.List<@Valid Endpoint> endpoints
) {
    public record Endpoint(@NotBlank String name) {}
}
~~~

`@NotEmpty` kiểm tra danh sách có phần tử, `@Valid` kích hoạt cascade và `@NotBlank` kiểm tra tên từng phần tử.

### Bài 5 — Giá trị sai kiểu

File có `app.worker.thread-count=abc`, Java field là `int threadCount` với `@Min(1)`. Đây là lỗi conversion hay lỗi `@Min`?

**Đáp án:** trước hết là lỗi conversion/binding vì `abc` không thể chuyển thành `int`. Validator có thể chưa có cơ hội kiểm tra `@Min(1)`.

### Bài 6 — Default và validation

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int threadCount
) {}
~~~

Khi thiếu khóa, kết quả? Khi cấp `0`, kết quả?

**Đáp án:** thiếu khóa thì default `4` có thể được bind và đạt constraint. Khi cấp `0`, default không tự thay thế, nên `@Min(1)` từ chối.

### Bài 7 — Ràng buộc timeout dương

Vì sao `@NotNull Duration timeout` không đủ để ngăn `timeout=0s`?

**Đáp án:** `Duration.ZERO` không phải null. Cần custom Bean Validation constraint cho `Duration` dương hoặc kiểm tra bất biến tại constructor.

### Bài 8 — Từ YAML đến runtime

`application-prod.yml` định nghĩa `app.worker.thread-count=8`, nhưng env đặt `APP_WORKER_THREADCOUNT=0`. Nếu `@Min(1)` được bật đúng, có thể xảy ra điều gì?

**Đáp án:** biến môi trường thường ưu tiên hơn Config Data và cung cấp giá trị cuối `0`. Binder chuyển kiểu thành công, Bean Validation từ chối, khiến quá trình tạo bean cấu hình/startup thất bại.

## 35. Checklist vận dụng vào dự án

Khi tạo một class `@ConfigurationProperties` mới:

1. Xác định **prefix** và tên thuộc tính canonical cần bind.
2. Chọn kiểu Java đúng: `int`, `Integer`, `Duration`, `List`, `Map` hoặc nested record.
3. Thêm dependency Bean Validation provider, thường qua `spring-boot-starter-validation`.
4. Đánh dấu root properties class với **`@Validated`**.
5. Gắn constraint chuẩn phù hợp: `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@NotEmpty`...
6. Với nested object/collection, thêm **`@Valid`** để đi sâu và `@NotNull`/`@NotEmpty` khi cần yêu cầu cấu trúc đó tồn tại.
7. Chỉ định default khi sự vắng mặt là một trường hợp hợp lệ; dùng wrapper nullable nếu cần phát hiện thiếu cấu hình.
8. Với ràng buộc nhiều field hoặc kiểu đặc biệt, thêm custom constraint hoặc kiểm tra bất biến có chủ đích.
9. Đăng ký bean đúng cách qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
10. Viết test cho **giá trị hợp lệ, thiếu, sai kiểu, sai ràng buộc và nested object**.
11. Khi triển khai, đảm bảo cấu hình từ env/CLI không vô tình ghi đè giá trị hợp lệ trong YAML.
12. Không ghi log giá trị nhạy cảm và không xem Bean Validation là thay thế cho kiểm thử integration.

Checklist này chỉ là quy trình để lập trình viên vận dụng; mỗi ứng dụng cần tự xác định điều kiện nghiệp vụ và mức độ nghiêm ngặt của cấu hình.

## 36. Ghi nhớ

- **`@Validated` trên `@ConfigurationProperties`** là cách phổ biến để kích hoạt validation của đối tượng cấu hình Spring Boot.
- Cần **Bean Validation provider** thích hợp; trong Spring Boot 3.x, cách thông dụng là thêm `spring-boot-starter-validation` và dùng annotation từ namespace `jakarta.validation`.
- **Binding/conversion** và **validation** là hai bước khác nhau: `abc` vào `int` là lỗi conversion, còn `0` vi phạm `@Min(1)` là lỗi validation.
- `@Validated` không tự tạo ràng buộc. Phải khai báo `@NotBlank`, `@Min`, `@NotNull` và những constraint thực sự cần thiết.
- **`@NotNull` không kiểm tra chuỗi trắng** và cũng không kiểm tra thời lượng dương; chọn đúng constraint cho đúng kiểu.
- Với cấu hình lồng nhau, **`@Valid` kích hoạt cascade**, còn `@NotNull`/`@NotEmpty` yêu cầu object/collection tồn tại.
- Dùng **wrapper `Integer`/`Boolean`** nếu muốn phát hiện trạng thái thiếu thay vì để primitive nhận default 0/false.
- `@DefaultValue` và placeholder default không thay thế validation đối với giá trị được cung cấp nhưng không hợp lệ.
- Validation kiểm tra **giá trị sau khi Binder đã chọn nguồn cấu hình có hiệu lực**, kể cả biến môi trường và CLI.
- Nên kiểm thử bằng `ApplicationContextRunner` để chắc rằng cấu hình hợp lệ khởi tạo được, còn cấu hình sai làm context thất bại theo chủ đích.
- Giữ cơ chế **fail fast** cho cấu hình quan trọng; không dùng `ignoreInvalidFields` để che lỗi sai kiểu hoặc thiếu ràng buộc.

## Tài liệu tham khảo

- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 Reference — Type-safe Configuration Properties and Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
