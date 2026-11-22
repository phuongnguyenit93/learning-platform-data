# Kiểm tra phần tử collection và giá trị Map

Trong Spring Boot Externalized Configuration, cấu hình không chỉ là những giá trị đơn lẻ. Một ứng dụng có thể bind danh sách endpoint, tập email, danh sách tác vụ hoặc bản đồ các kết nối theo tên vào một bean `@ConfigurationProperties`. Với những cấu trúc đó, yêu cầu **kiểm tra hợp lệ (validation)** không dừng ở việc collection có tồn tại: từng phần tử, từng khóa Map và từng object nằm dưới Map value có thể có quy tắc riêng.

Ví dụ, `@NotEmpty List<Endpoint>` chỉ thể hiện rằng danh sách không được null hoặc rỗng; nó không tự đảm bảo mỗi `Endpoint` đều có URL, timeout và tên hợp lệ. Tương tự, `@NotEmpty Map<String, Client>` không có nghĩa mọi `Client` trong map đã được kiểm tra. Muốn kiểm tra các object lồng nhau, cần **cascaded validation** bằng `@Valid` hoặc dùng **container-element constraints** đặt trực tiếp lên kiểu phần tử, kết hợp `@Validated` trên configuration-properties root và một Bean Validation provider phù hợp.

Bài này tập trung vào Jakarta Bean Validation trong Spring Boot 3.x: `List`, `Set`, `Map`, container-element constraints, kiểm tra đệ quy, lỗi binding so với lỗi validation, ảnh hưởng của profile và cách kiểm thử. Các ví dụ giả định Java 17+ và Spring Boot 3.x; với phiên bản cũ dùng namespace `javax.validation` hoặc cơ chế khác, cần điều chỉnh import và dependency.

## 1. Vì sao validation collection khác validation scalar?

Giả sử ta có:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

Một kiểu Java:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Endpoint> endpoints) {

    public record Endpoint(
            String name,
            URI url,
            int maxRetries
    ) {}
}
~~~

Binder có thể tạo được một `List<Endpoint>` mà trong đó có phần tử `name=null`, `url=null` hoặc `maxRetries=-1`. Việc bind thành công không chứng minh cấu hình có thể dùng an toàn.

Các câu hỏi validation độc lập:

1. Danh sách có được khai báo không?
2. Danh sách có ít nhất một phần tử không?
3. Mỗi phần tử có khác null không?
4. Các trường của từng phần tử có hợp lệ không?
5. Có ràng buộc liên quan giữa các phần tử không, chẳng hạn tên không trùng nhau?
6. Có ràng buộc liên quan giữa nhiều collection hoặc map trong cùng properties bean không?

Một annotation thường chỉ trả lời **một phần** của những câu hỏi ấy. Cần chọn đúng mức ràng buộc.

## 2. Chuẩn bị Bean Validation cho Spring Boot

Với Spring Boot 3.x, ví dụ dùng các annotation thuộc `jakarta.validation` và `jakarta.validation.constraints`. Trong một dự án dùng Spring Boot starters, dependency thường gặp là:

~~~xml
<!-- Maven -->
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

Starter cung cấp sự tích hợp Bean Validation với provider thích hợp, thường là Hibernate Validator theo dependency management của Spring Boot. Không nên chỉ thêm một annotation API rồi mặc định chắc chắn có validator runtime để xử lý nó.

Để Spring Boot validate typed configuration properties, đặt `@Validated` trên root properties class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(/* ... */) {}
~~~

Và đăng ký như configuration-properties bean:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {
}
~~~

Có thể dùng `@ConfigurationPropertiesScan` thay thế nếu đó là quy ước dự án. Chỉ đánh dấu `@ConfigurationProperties` mà không có registration phù hợp có thể khiến bean không được tạo. Chỉ đăng ký bean nhưng không có validator phù hợp cũng không thể suy ra mọi constraint đều được thực thi.

**Phân vai:** Binder chuyển nguồn cấu hình thành object; Bean Validation kiểm tra object sau khi bind theo quy tắc được khai báo.

## 3. Collection tồn tại chưa? @NotNull, @NotEmpty và @Size

Với `List`, `Set` hoặc `Map`, những constraint thường gặp:

| Constraint | Null | Collection rỗng | Collection có phần tử |
| --- | --- | --- | --- |
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ |
| `@NotEmpty` | Không hợp lệ | Không hợp lệ | Hợp lệ |
| `@Size(min = 2, max = 10)` | Null thường được xem là hợp lệ | Không hợp lệ với min=2 | Hợp lệ nếu số phần tử trong khoảng |
| `@NotNull @Size(min = 2)` | Không hợp lệ | Không hợp lệ | Hợp lệ nếu đủ phần tử |

Ví dụ:

~~~java
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        @NotEmpty
        @Size(max = 20)
        List<String> tags,

        @NotEmpty
        Map<String, String> labels
) {}
~~~

Đây mới chỉ là **kiểm tra collection ở cấp root**. Các ràng buộc đó chưa nói rằng mỗi tag không được rỗng hoặc mỗi value của map không được blank.

Quan trọng: theo Bean Validation, nhiều constraint như `@Size` chấp nhận `null`; nếu muốn bắt buộc property phải có và có kích thước trong khoảng, phối hợp với `@NotNull` hoặc `@NotEmpty`.

Ví dụ yêu cầu tối thiểu hai điểm đến:

~~~java
@NotNull
@Size(min = 2, max = 5)
List<Endpoint> endpoints
~~~

Nếu thiếu collection, `@NotNull` phát hiện. Nếu collection rỗng hoặc chỉ có một phần tử, `@Size` phát hiện. Nếu có hai phần tử nhưng URL của một phần tử null, **hai constraint này vẫn có thể cho qua**; cần validation ở tầng phần tử.

## 4. Kiểm tra từng chuỗi: List<@NotBlank String>

Giả sử cấu hình:

~~~yaml
notification:
  recipients:
    - "ops@example.invalid"
    - ""
    - "alerts@example.invalid"
~~~

Kiểu Java nếu chỉ viết:

~~~java
@NotEmpty
List<String> recipients
~~~

thì danh sách có ba phần tử nên vẫn thỏa mãn `@NotEmpty`. Phần tử `""` không bị kiểm tra.

Muốn yêu cầu mỗi chuỗi không blank:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

@NotEmpty
List<@NotBlank String> recipients
~~~

`@NotBlank` đặt ở vị trí **type argument** của `List`, tức mỗi element type là String có constraint. Với Jakarta Bean Validation hỗ trợ container element validation, validator sẽ kiểm tra từng giá trị được duyệt bởi value extractor của List.

Có thể phối hợp thêm định dạng email:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

List<@NotBlank @Email String> recipients
~~~

Lưu ý:

- `@Email` kiểm tra cú pháp theo Bean Validation provider, không gửi email để xác thực địa chỉ có tồn tại.
- `@NotBlank` đảm bảo không null, không rỗng hoặc toàn whitespace; nó thích hợp với String, không dùng cho kiểu số.
- `@NotEmpty` trên List đảm bảo **ít nhất một phần tử**, khác `@NotBlank` trên từng phần tử.
- Nếu không bắt buộc có recipient, có thể không đặt `@NotEmpty` ở cấp List nhưng vẫn đặt constraint cho mọi phần tử khi List hiện diện.

Ví dụ hoàn chỉnh:

~~~java
package example.notification;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients
) {}
~~~

Nếu YAML có một địa chỉ rỗng, validation có thể khiến Spring Boot từ chối khởi tạo configuration-properties bean, thay vì để ứng dụng tiếp tục và nhận lỗi ở lúc gửi thông báo.

## 5. Kiểm tra số trong collection: List<@Min(...) Integer>

Một hệ thống batch có các mức retry theo tầng:

~~~yaml
batch:
  retry-limits:
    - 1
    - 3
    - 0
~~~

Nếu yêu cầu mỗi giá trị từ 1 đến 10:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
List<@NotNull @Min(1) @Max(10) Integer> retryLimits
~~~

Các ràng buộc này khác nhau:

- `@NotEmpty`: List phải có phần tử.
- `@NotNull` trên `Integer`: không chấp nhận phần tử null.
- `@Min(1)`: không chấp nhận số nhỏ hơn 1.
- `@Max(10)`: không chấp nhận số lớn hơn 10.

Không dùng `@NotBlank` với `Integer` vì đó là constraint cho chuỗi. Không nên chỉ dùng `@Min(1)` rồi suy luận null bị cấm: các numeric constraints thường xem null là hợp lệ trừ khi kết hợp `@NotNull`.

Nếu YAML chứa `retry-limits: ["many"]`, Binder có thể thất bại khi chuyển `"many"` sang Integer **trước khi validation** chạy. Đây là conversion/binding error, khác với dữ liệu integer 0 bị `@Min(1)` từ chối.

## 6. Kiểm tra object bên trong List bằng @Valid

Trường hợp phổ biến nhất là `List<Endpoint>`:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: ""
      url: "https://backup.example.invalid"
      max-retries: 0
~~~

Một bean với constraints trong nested record:

~~~java
package example.routing;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;

public record Endpoint(
        @NotBlank String name,
        @NotNull URI url,
        @Min(1) int maxRetries
) {}
~~~

Nếu root viết:

~~~java
@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty List<Endpoint> endpoints
) {}
~~~

thì việc có constraints trên các field của `Endpoint` **chưa đủ để chắc chắn chúng được duyệt**. Cần khai báo **cascaded validation**:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
List<@NotNull @Valid Endpoint> endpoints
~~~

Ở đây:

- `@NotEmpty` kiểm tra List.
- `@NotNull` trong angle brackets kiểm tra mỗi phần tử khác null.
- `@Valid` trong angle brackets yêu cầu validator đi vào object `Endpoint` để kiểm tra `name`, `url`, `maxRetries`.

Có thể đặt `@Valid` trên container property, ví dụ `@Valid List<Endpoint> endpoints`, để yêu cầu cascade qua collection với Bean Validation provider hỗ trợ. Việc khai báo ở type argument `List<@Valid Endpoint>` thường làm **đích validation** rõ hơn, đặc biệt khi có nhiều tầng collection.

**Đừng đặt `@Valid` lên mỗi phần tử và tưởng rằng nó thay `@NotNull`.** Theo Bean Validation, cascading một giá trị null thường không kiểm tra các field của nó; nếu phần tử null bị cấm thì cần `@NotNull` tương ứng.

## 7. Ví dụ hoàn chỉnh: List nested objects

Một root properties đủ cấu trúc và validation:

~~~java
package example.routing;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty
        @MaxItems(5)
        List<@NotNull @Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotNull URI url,
            @Min(1) @Max(10) int maxRetries
    ) {}
}
~~~

Trong ví dụ này `@MaxItems(5)` là **một custom constraint giả định**, không phải annotation chuẩn của Jakarta Validation. Nếu chỉ cần giới hạn kích thước theo Bean Validation chuẩn, dùng `@Size(max = 5)`:

~~~java
import jakarta.validation.constraints.Size;

@NotEmpty
@Size(max = 5)
List<@NotNull @Valid Endpoint> endpoints
~~~

Đăng ký:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {}
~~~

Cấu hình hợp lệ:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

Cấu hình không hợp lệ:

~~~yaml
routing:
  endpoints:
    - name: ""
      url: "https://primary.example.invalid"
      max-retries: 0
~~~

Khi ứng dụng có validation provider và binding được kích hoạt, trường `name` vi phạm `@NotBlank` và `maxRetries` vi phạm `@Min(1)`. Startup có thể bị từ chối với lỗi cấu hình; đường dẫn vi phạm thường gợi tới `routing.endpoints[0]` hoặc path tương tự, tùy cách provider/Boot hiển thị.

Để code minh họa tự chạy, dùng phiên bản với `@Size(max = 5)`, không cần tự tạo custom annotation.

## 8. Collection element constraint và cascading không giống nhau

Hãy phân biệt hai kiểu annotation:

~~~java
List<@NotBlank String> labels
~~~

và:

~~~java
List<@Valid Endpoint> endpoints
~~~

Câu đầu yêu cầu **giá trị phần tử String** thỏa một constraint trực tiếp. Câu sau yêu cầu **đi vào các field của Endpoint** và kiểm tra constraints đã khai báo trên class/record đó.

Nếu chỉ dùng:

~~~java
List<@Valid String> labels
~~~

thì `@Valid` không thay thế `@NotBlank`, vì String không có các Bean Validation constraints nội tại cần cascade như một configuration object.

Nếu chỉ dùng:

~~~java
List<@NotNull Endpoint> endpoints
~~~

thì object không null là điều kiện được kiểm tra, nhưng các field `name`, `url` có thể vẫn không được kiểm tra nếu thiếu cascading.

Khi object cần vừa tồn tại vừa có field hợp lệ, phối hợp:

~~~java
List<@NotNull @Valid Endpoint> endpoints
~~~

Annotation đúng loại là điều kiện quyết định validation có bao phủ phần tử hay không.

## 9. Set: kiểm tra phần tử mà không giả định thứ tự

`Set` cũng là collection có thể bind từ các nguồn externalized configuration:

~~~yaml
security:
  roles:
    - "ADMIN"
    - "VIEWER"
~~~

Properties:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.Set;

@NotEmpty
Set<@NotBlank String> roles
~~~

Container-element constraints có thể kiểm tra từng phần tử, tương tự List. Tuy nhiên:

- `Set` biểu diễn tập hợp, không phải thứ tự nghiệp vụ.
- Các phần tử trùng có thể bị loại theo semantics của Set; validation trên Set sau binding không đảm bảo có thể phát hiện mọi giá trị trùng trong YAML gốc.
- Nếu yêu cầu là “danh sách role có thứ tự”, Set không phù hợp.
- Nếu cần cấm trùng trong input trước khi chuyển Set, cần lựa chọn mô hình hoặc bước kiểm tra khác có khả năng quan sát dữ liệu gốc.

`@Size(min = 2)` trên Set kiểm tra số phần tử **sau khi bind vào Set**, không bảo đảm input ban đầu có hai giá trị khác chuỗi nhưng trùng nghĩa nghiệp vụ.

## 10. Kiểm tra Map: ba mức độ độc lập

Với một Map, cần tách:

1. **Map có tồn tại và có entry không?** `@NotEmpty Map<...>`.
2. **Map key có hợp lệ không?** Container-element constraints trên kiểu key, ví dụ `Map<@NotBlank String,...>`.
3. **Map value có hợp lệ không?** Constraint trực tiếp trên kiểu value, hoặc `@Valid` để cascade vào object value.

Ví dụ:

~~~yaml
rates:
  categories:
    standard: 1.0
    premium: 1.5
~~~

Root:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "rates")
public record RateProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotNull @DecimalMin("0.01") BigDecimal
        > categories
) {}
~~~

Ý nghĩa:

- Map không rỗng.
- Mỗi key là chuỗi không blank.
- Mỗi value không null và ít nhất bằng 0.01.
- Các value như 0 hoặc -2 vi phạm `@DecimalMin`.

Map key có thể được Binder xử lý/chuẩn hóa theo tên property. Constraint được đánh giá **trên key đã bind**, không nhất thiết trên chuỗi YAML nguyên văn. Nếu nghiệp vụ cần kiểm tra tên key chứa dấu đặc biệt, cú pháp bracket notation và cách binding Map phải được xem xét riêng.

## 11. Map<String, @NotBlank String> để kiểm tra giá trị chuỗi

Ví dụ thông tin header cấu hình:

~~~yaml
client:
  headers:
    X-Client-Id: "order-service"
    X-Region: ""
~~~

Java:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.Map;

@NotEmpty
Map<String, @NotBlank String> headers
~~~

`@NotEmpty` chỉ thấy Map có hai entry. `@NotBlank` ở value type kiểm tra từng String value. Entry có chuỗi `""` không hợp lệ.

Nếu key cũng phải không blank:

~~~java
@NotEmpty
Map<@NotBlank String, @NotBlank String> headers
~~~

Nhưng đây chỉ là ví dụ validation trên **dữ liệu đã bind**. Đối với tên HTTP header thực tế, chỉ `@NotBlank` chưa đủ: header name còn phải tuân thủ quy tắc ký tự hợp lệ của HTTP, có thể cần validator chuyên biệt. Không tự đưa các giá trị header nhạy cảm như authorization token vào log khi debug lỗi.

## 12. Map có value là object: @Valid ở vị trí value

Ứng dụng có nhiều outbound clients:

~~~yaml
connectors:
  clients:
    billing:
      base-url: "https://billing.example.invalid"
      timeout: 3s
      pool-size: 10
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 2s
      pool-size: 8
~~~

Typed properties:

~~~java
package example.connectors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "connectors")
public record ConnectorsProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotNull @Valid Client
        > clients
) {
    public record Client(
            @NotNull URI baseUrl,
            @NotNull Duration timeout,
            @Min(1) int poolSize
    ) {}
}
~~~

Với `@Valid` ở Map value type, Bean Validation có thể đi vào từng `Client` object để kiểm tra ba field. Nếu `inventory.pool-size=0` hoặc `billing.timeout` thiếu, constraint tương ứng có thể báo lỗi.

Nếu chỉ khai báo:

~~~java
@NotEmpty
Map<String, Client> clients
~~~

thì Map có entry là điều kiện đủ cho `@NotEmpty`; constraints bên trong `Client` không đương nhiên được duyệt. Cần khai báo cascade hợp lệ.

Một số codebase sử dụng:

~~~java
@Valid
Map<String, Client> clients
~~~

để cascade qua values. Cú pháp `Map<String, @Valid Client>` đặc biệt rõ rằng ta muốn validate **từng Map value**, chứ không chỉ kiểm tra bản thân Map.

## 13. Không đặt @Valid nhầm ở key

Với:

~~~java
Map<String, Client> clients
~~~

thường ý nghĩa là kiểm tra từng `Client` ở **vị trí value**. Cú pháp:

~~~java
Map<@Valid String, Client> clients
~~~

không giải quyết việc validate field của `Client` vì `@Valid` được đặt ở kiểu key. Nếu muốn kiểm tra tên key, sử dụng constraint thích hợp như `@NotBlank`, `@Pattern`:

~~~java
Map<
    @NotBlank String,
    @NotNull @Valid Client
> clients
~~~

Cần tránh việc thêm `@Valid` ở mọi tầng một cách máy móc: xác định **giá trị nào là object cần duyệt vào bên trong**, và constraint nào áp dụng trực tiếp lên String/Number.

## 14. Nested Map và nested List

Có những cấu trúc như:

~~~yaml
policies:
  groups:
    public:
      - code: "READ"
        limit: 100
      - code: "SEARCH"
        limit: 50
    internal:
      - code: "WRITE"
        limit: 20
~~~

Kiểu cấu hình:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "policies")
public record PolicyProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotEmpty List<@NotNull @Valid Rule>
        > groups
) {
    public record Rule(
            @NotBlank String code,
            @Min(1) int limit
    ) {}
}
~~~

Ở đây có nhiều tầng:

- Root Map `groups` phải có entry.
- Key của Map không được blank.
- List của mỗi group không được rỗng.
- Mỗi Rule không được null.
- Bean Validation cascade vào từng Rule để kiểm tra code và limit.

Việc validation nhiều tầng phụ thuộc provider có **ValueExtractor** hỗ trợ những container type được sử dụng, như Map và List thông dụng. Với custom container class, có thể cần ValueExtractor phù hợp; không mặc định mọi generic wrapper tự được duyệt.

Cấu hình phức tạp nên được thử bằng integration test thực tế, không chỉ nhìn annotation và suy đoán.

## 15. Map merge theo property source không thay thế validation

Spring Boot có quy tắc binding khác giữa Map và List khi nhiều nguồn cùng khai báo collection. Với Map, các key có thể được kết hợp theo property sources; với List, nguồn ưu tiên cao thường thay toàn bộ List.

Ví dụ chung:

~~~yaml
# application.yml
connectors:
  clients:
    billing:
      base-url: "https://billing.example.invalid"
      timeout: 3s
      pool-size: 10
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 2s
      pool-size: 8
~~~

File dev:

~~~yaml
# application-dev.yml
connectors:
  clients:
    billing:
      base-url: "http://localhost:9090"
~~~

Với `Map<String, Client>`, entry billing có thể lấy URL từ dev, timeout/pool size từ base; entry inventory vẫn có thể đến từ base. Validation được áp dụng cho **object có hiệu lực sau khi binding**, không chỉ một mẩu YAML của riêng file dev.

Điều này thường hữu ích, nhưng cũng có rủi ro: người vận hành nghĩ đã xóa một trường bằng cách bỏ nó khỏi file dev, trong khi Map vẫn kế thừa từ file chung. Nếu một field không được phép kế thừa giữa môi trường, cần thiết kế nguồn cấu hình và ràng buộc rõ ràng.

Đặc biệt, JSON `null` ở `SPRING_APPLICATION_JSON` không tự xóa property ở nguồn thấp hơn. Không dựa vào null như lệnh xóa để qua validation.

## 16. List replacement có thể tạo element thiếu dữ liệu

Cấu hình chung:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

File dev chỉ khai báo:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9080"
~~~

Khi dev active và list dev thắng, chỉ có một endpoint local; thuộc tính `max-retries` không tự được kế thừa từ phần tử primary ở base.

Nếu Java dùng:

~~~java
@Min(1) int maxRetries
~~~

thì giá trị thiếu có thể thành primitive default 0, dẫn tới lỗi validation. Đây là hành vi có ích: nếu retry count bắt buộc phải ít nhất 1, context nên từ chối cấu hình thiếu thay vì chạy sai.

Nếu dùng `Integer` cùng `@Min(1)`, cần thêm `@NotNull` nếu muốn cấm thiếu giá trị; bản thân numeric constraint thường cho null đi qua.

Trong test, hãy bật đúng profile và kiểm tra **từng phần tử sau binding**, thay vì chỉ xác nhận YAML file dev có cú pháp hợp lệ.

## 17. Sự khác nhau giữa @NotNull trên value và @Valid cascade

Ví dụ Map:

~~~java
Map<String, @NotNull Client> clients
~~~

Bắt buộc mỗi value không null, nhưng **không tự kiểm tra field bên trong Client**.

Ngược lại:

~~~java
Map<String, @Valid Client> clients
~~~

có thể cascade vào field của các Client khác null, nhưng `@Valid` không tự làm null value thành vi phạm.

Nếu cần cả hai:

~~~java
Map<String, @NotNull @Valid Client> clients
~~~

Tương tự cho List:

~~~java
List<@NotNull @Valid Endpoint> endpoints
~~~

Khi chỉ dùng:

~~~java
@NotNull Map<String, Client> clients
~~~

thì một Map không rỗng nhưng chứa value null vẫn có thể qua constraint của container root. Hãy đặt constraint đúng tầng.

## 18. Các constraint chỉ phù hợp với một số kiểu

Mỗi constraint có danh sách kiểu được hỗ trợ. Không phải annotation nào cũng dùng được cho mọi loại field.

| Kiểu dữ liệu | Constraint thường dùng | Mục đích |
| --- | --- | --- |
| `String` | `@NotBlank`, `@Size`, `@Pattern`, `@Email` | Nội dung/định dạng chuỗi |
| `Integer` / `Long` | `@Min`, `@Max`, `@Positive` | Khoảng số |
| `BigDecimal` | `@DecimalMin`, `@DecimalMax`, `@Digits` | Giá trị thập phân |
| `List` / `Set` / `Map` | `@NotNull`, `@NotEmpty`, `@Size` | Tồn tại và kích thước |
| Object lồng nhau | `@Valid` | Cascade vào field của object |
| Object nullable | `@NotNull` | Cấm null |
| `Duration` | `@NotNull` và custom validation khi cần dương | Kiểm tra presence và quy tắc thời lượng |
| `URI` | `@NotNull`, kiểm tra scheme/host riêng | URI khác null chưa đủ bảo đảm an toàn |

Ví dụ đặt `@NotBlank` trên `Duration` hoặc `@Min(1)` trực tiếp trên `Duration` có thể gây lỗi validator không tìm được cách validate kiểu đó, không phải mang lại check như mong muốn.

Khi cần kiểm tra thời lượng phải lớn hơn 0, có thể dùng một class-level validator, custom constraint hoặc kiểm tra khi khởi tạo client. Không nên xem validation là bước tự động kiểm tra mọi bất biến nghiệp vụ.

## 19. Validation bản thân key của Map

Ví dụ key của các client phải tuân theo `lowercase-kebab-case`:

~~~java
import jakarta.validation.constraints.Pattern;
import java.util.Map;

Map<
    @Pattern(regexp = "[a-z][a-z0-9-]*") String,
    @Valid Client
> clients
~~~

Constraint trên String key có thể kiểm tra tên sau khi Binder xử lý. Nhưng nếu key chứa dấu chấm, slash, dấu ngoặc hoặc ký tự đặc biệt, Spring Boot có quy tắc **Map binding và bracket notation** để bảo toàn key:

~~~yaml
features:
  labels:
    "[/api/v1]": "public"
~~~

Với Map String values, key có ký tự đặc biệt thường cần bracket notation và quy tắc quote phù hợp trong YAML. Nếu key bị chuẩn hóa khác ý định trước khi Bean Validation chạy, constraint không thể khôi phục ký tự gốc.

Đừng dùng constraint ở Map key để thay thế việc thiết kế schema key hợp lệ hoặc kiểm tra route/path theo quy tắc ứng dụng.

## 20. Dữ liệu sai kiểu xảy ra trước validation

Với:

~~~yaml
connectors:
  clients:
    billing:
      pool-size: "many"
~~~

Java:

~~~java
@Min(1) int poolSize
~~~

Binder phải chuyển `"many"` thành `int`. Nếu conversion thất bại, Spring Boot có thể báo lỗi binding trước khi Bean Validation kiểm tra `@Min(1)`. Điều này khác với:

~~~yaml
connectors:
  clients:
    billing:
      pool-size: 0
~~~

Số 0 bind được vào int, nhưng không đạt `@Min(1)`.

Phân biệt chẩn đoán:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Cấu trúc YAML sai | Sai indent, dấu `:` không hợp lệ | Sửa YAML |
| Conversion/binding | `"many"` vào int | Sửa định dạng property hoặc converter |
| Collection constraint | List rỗng bị `@NotEmpty` | Cấp phần tử phù hợp |
| Element constraint | List có `""` bị `@NotBlank` | Sửa phần tử |
| Cascaded validation | Endpoint thiếu URL | Sửa nested property hoặc default |
| Map key constraint | Key không đạt regex | Chuẩn hóa tên key |
| Map value constraint | Pool size 0 | Sửa giá trị hoặc hợp đồng |
| Bean registration | Không có bean `@ConfigurationProperties` | Enable/scan type đúng |

Không nên sửa lỗi validation bằng cách bỏ `@Validated` hoặc bắt exception rộng rồi cho startup tiếp tục. Nếu production cần các field đó, fail-fast là hành vi có ích.

## 21. @Valid không thay thế Bean Validation provider

Đoạn code có annotation:

~~~java
@Validated
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        List<@Valid Target> targets
) {}
~~~

không đủ để kết luận mọi trường được kiểm tra, nếu project thiếu validation provider/đường đăng ký bean. Cần:

- Dependency Jakarta Bean Validation tương thích.
- Một implementation như Hibernate Validator hoặc provider được dự án dùng.
- Configuration-properties bean được đăng ký đúng.
- `@Validated` hoặc cơ chế kích hoạt validation phù hợp.
- Constraint cụ thể trên Target và các nested types.
- `@Valid` đặt đúng mức để cascade.

Nếu nested object không có constraint nào, `@Valid` chỉ duyệt object chứ không tự biết “field nào bắt buộc”. Tính bắt buộc phải được khai báo tường minh.

## 22. Vì sao @NotEmpty Map không đảm bảo các value khác null?

Ví dụ:

~~~java
@NotEmpty
Map<String, String> labels
~~~

Map có một entry với value null vẫn **không rỗng**. `@NotEmpty` chỉ kiểm tra kích thước của Map, không kiểm tra giá trị bên trong.

Nếu mỗi value phải có chuỗi:

~~~java
@NotEmpty
Map<String, @NotBlank String> labels
~~~

Nếu value là object:

~~~java
@NotEmpty
Map<String, @NotNull @Valid LabelSettings> labels
~~~

Đây là lý do cấu hình Map cần xem ít nhất ba mức: Map root, Map key và Map value.

## 23. Ví dụ tập trung: cấu hình notification nhiều channel

Giả sử ứng dụng gửi thông báo qua nhiều channel theo ID.

~~~yaml
notification:
  default-recipients:
    - "ops@example.invalid"
    - "audit@example.invalid"
  channels:
    email:
      enabled: true
      endpoint: "https://mail.example.invalid"
      attempts: 3
      tags:
        - "critical"
        - "audit"
    webhook:
      enabled: false
      endpoint: "https://hooks.example.invalid"
      attempts: 1
      tags:
        - "system"
~~~

Kiểu Java:

~~~java
package example.notification;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> defaultRecipients,

        @NotEmpty
        Map<@NotBlank String, @NotNull @Valid Channel> channels
) {
    public record Channel(
            boolean enabled,
            @NotNull URI endpoint,
            @Min(1) @Max(10) int attempts,
            @NotEmpty @Size(max = 8)
            List<@NotBlank String> tags
    ) {}
}
~~~

Đăng ký:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
class NotificationConfiguration {}
~~~

Ví dụ này kiểm tra:

1. Default recipients không rỗng.
2. Mỗi địa chỉ recipient không blank và có cú pháp email phù hợp.
3. Map channels không rỗng.
4. Key của mỗi channel không blank.
5. Mỗi Channel value không null và được cascade vào các field.
6. Endpoint khác null.
7. Attempts nằm trong 1..10.
8. Tags của mỗi channel không rỗng và không vượt tám phần tử.
9. Mỗi tag không blank.

**Điểm cần thiết kế thêm:** nếu `enabled=false` nghĩa là Channel không cần endpoint, ràng buộc `@NotNull URI endpoint` ở đây quá nghiêm. Khi đó cần validation có điều kiện theo trạng thái enabled hoặc tách các kiểu config. `@Valid` không tự hiểu điều kiện nghiệp vụ như “chỉ bắt buộc khi enabled”.

## 24. Validation có điều kiện giữa các trường

Giả sử Channel có thể bị tắt:

~~~yaml
notification:
  channels:
    webhook:
      enabled: false
~~~

Nếu hợp đồng là “endpoint chỉ bắt buộc khi channel enabled”, class-level/cross-field validation là lựa chọn thích hợp.

Một cách đơn giản cho ví dụ:

~~~java
import jakarta.validation.constraints.AssertTrue;
import java.net.URI;

public record Channel(
        boolean enabled,
        URI endpoint
) {
    @AssertTrue(message = "endpoint is required when enabled")
    public boolean isEndpointPresentWhenEnabled() {
        return !enabled || endpoint != null;
    }
}
~~~

Để method trên được chạy, root configuration-properties cần validation và `@Valid` cascade vào Channel như phần trước. Đoạn code minh họa điều kiện phụ thuộc giữa hai field; trong ứng dụng lớn có thể dùng custom class-level constraint để kiểm tra nhiều điều kiện và báo lỗi tại field thích hợp.

Nếu endpoint có giá trị, vẫn cần kiểm tra scheme/host và các quy tắc bảo mật. Một URI hợp lệ về cú pháp không chứng minh địa chỉ được phép gọi hay không chứa mục tiêu không an toàn.

## 25. Kiểm tra liên hệ giữa các phần tử: tên không được trùng

Bean Validation chuẩn không tự quy định mọi `List<Endpoint>` phải có tên không trùng nhau. `@NotEmpty`, `@Valid` và `@NotBlank` kiểm tra mỗi giá trị riêng lẻ, không kiểm tra quy tắc liên phần tử.

Ví dụ:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://one.example.invalid"
    - name: "primary"
      url: "https://two.example.invalid"
~~~

Hai entry đều có name không blank và URL khác null, nhưng có thể vi phạm yêu cầu định danh unique.

Có thể thực hiện một kiểm tra sau binding trong factory hoặc validator chuyên dụng:

~~~java
import java.util.HashSet;
import java.util.Set;

Set<String> names = new HashSet<>();
for (RoutingProperties.Endpoint endpoint : properties.endpoints()) {
    if (!names.add(endpoint.name())) {
        throw new IllegalStateException(
            "Duplicate endpoint name: " + endpoint.name());
    }
}
~~~

Đoạn code giả định từng endpoint khác null và name đã được validate; nếu không, cần xử lý null trước khi dùng. Với một hợp đồng cấu hình phức tạp, có thể xây dựng class-level custom constraint thay vì rải kiểm tra ở nhiều service.

Tương tự, nếu một Map chứa key là tên endpoint và List chứa thứ tự gọi, cần kiểm tra mọi tên trong List có trong Map và không bị trùng theo nghiệp vụ.

## 26. Phân biệt empty, null và missing

Trong externalized configuration:

~~~yaml
app:
  tags: []
~~~

khác với hoàn toàn không khai báo `app.tags` ở nguồn nào. Sau binding, kết quả chính xác phụ thuộc mô hình Java, constructor default, provider và các nguồn ưu tiên khác.

Các trường hợp:

| Dữ liệu bind | `@NotNull` | `@NotEmpty` | `@Size(min=2)` |
| --- | --- | --- | --- |
| `null` | Vi phạm | Vi phạm | Thường được phép nếu chỉ có @Size |
| `[]` | Qua | Vi phạm | Vi phạm |
| `["a"]` | Qua | Qua | Vi phạm |
| `["a","b"]` | Qua | Qua | Qua |

Với Map, `{}` cũng là map rỗng nếu Binder tạo được object đó. `@NotEmpty` không cho phép map trống, còn `@NotNull` cho phép.

Nếu cần một cấu hình có thể vắng mặt hoàn toàn, không đặt `@NotEmpty` vô điều kiện trên mọi trường. Nếu cần bắt buộc ở production, thể hiện ràng buộc đó theo hợp đồng triển khai/validation.

Không dùng JSON `null` trong `SPRING_APPLICATION_JSON` như phương pháp xóa property ở nguồn ưu tiên thấp hơn; nó không có ngữ nghĩa “tombstone”.

## 27. DefaultValue và validation trong collection

Với constructor binding Spring Boot 3.x, `@DefaultValue` có thể đặt trên tham số/record component:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
import jakarta.validation.constraints.Min;

public record Endpoint(
        String name,
        @DefaultValue("3")
        @Min(1)
        int maxRetries
) {}
~~~

Nếu phần tử có mặt nhưng không cung cấp `max-retries`, Binder có thể dùng default 3 rồi Bean Validation kiểm tra. Nhưng:

- `@DefaultValue` không thay List replacement giữa hai profile thành phép merge.
- Nếu `max-retries: "many"`, default không phải cách bỏ qua conversion error.
- Nếu `max-retries: 0`, ràng buộc `@Min(1)` vẫn từ chối.
- Default phải an toàn với mọi môi trường áp dụng, không nên che thông số thực sự cần deployment cấp.

Nếu thiếu hoàn toàn List root, một default trên từng phần tử không thể tự sinh ra các entry cụ thể mà ứng dụng không mô tả. Cần default/khả năng absence ở root hoặc cấu hình nguồn phù hợp.

## 28. Kiểm thử đường binding + validation thay vì chỉ gọi Validator trên object tự tạo

Test với:

~~~java
Validator validator =
    Validation.buildDefaultValidatorFactory().getValidator();

var violations = validator.validate(someObject);
~~~

có thể hữu ích để kiểm tra constraints thuần Jakarta Bean Validation. Tuy nhiên, nó không mô phỏng đầy đủ việc:

- Spring Boot đọc YAML và profile.
- Binder phân rã các key cấu hình.
- Chuyển dữ liệu thành kiểu Java.
- Đăng ký `@ConfigurationProperties` bean.
- Áp dụng validation trong lifecycle startup.

Để xác minh tích hợp, nên có test **Spring Boot context** với property values thực tế hoặc gần với môi trường triển khai.

Ví dụ test context với `ApplicationContextRunner` (cần các test dependencies tương ứng):

~~~java
package example.connectors;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConnectorsPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    ValidationAutoConfiguration.class
                ))
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsValidMapEntries() {
        runner.withPropertyValues(
            "connectors.clients.billing.base-url=https://billing.example.invalid",
            "connectors.clients.billing.timeout=3s",
            "connectors.clients.billing.pool-size=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            var props = context.getBean(ConnectorsProperties.class);
            assertThat(props.clients()).containsKey("billing");
            assertThat(props.clients().get("billing").poolSize())
                .isEqualTo(4);
        });
    }

    @Test
    void rejectsInvalidMapValue() {
        runner.withPropertyValues(
            "connectors.clients.billing.base-url=https://billing.example.invalid",
            "connectors.clients.billing.timeout=3s",
            "connectors.clients.billing.pool-size=0"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ConnectorsProperties.class)
    static class TestConfiguration {}
}
~~~

Test giả định `ConnectorsProperties` của ví dụ Map đã được định nghĩa, validator tương thích nằm trên classpath. `hasNotFailed()` là cách diễn đạt trong các assertion APIs phù hợp; nếu phiên bản test library không có method này, có thể xác nhận `context.getStartupFailure()` là null theo API hiện có.

Điểm cần thấy: test hợp lệ phải khởi tạo bean; test vi phạm `@Min(1)` phải làm context thất bại. Điều này kiểm tra cả registration, Binder và validation.

## 29. Test trực tiếp nguyên tắc container-element validation

Một unit test Jakarta Bean Validation có thể tập trung vào List elements:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LabelValidationTest {

    record Labels(
        @NotEmpty List<@NotBlank String> values
    ) {}

    @Test
    void rejectsBlankListElement() {
        try (var factory =
                 Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Labels sample = new Labels(
                List.of("audit", " "));

            assertThat(validator.validate(sample))
                .isNotEmpty();
        }
    }
}
~~~

Test này không cần Spring ApplicationContext. Nó chứng minh rằng `@NotEmpty` trên List và `@NotBlank` trên element là hai checks khác nhau. Nhưng để chắc chắn configuration-properties bean có được validate lúc khởi động, vẫn cần test tích hợp tương ứng.

Nếu dùng custom constraints, phải đăng ký validator implementation và đảm bảo provider nhận diện annotation/ValueExtractor. Đây là vấn đề của tầng Bean Validation, không phải Spring Boot config file syntax.

## 30. Lỗi phổ biến: đặt @Valid nhưng không có constraint

Ví dụ:

~~~java
public record Target(String name, URI url) {}
~~~

Và:

~~~java
List<@Valid Target> targets
~~~

Validator có thể cascade tới từng Target nhưng không biết `name` hay `url` bắt buộc nếu Target không có constraints. Cần:

~~~java
public record Target(
        @NotBlank String name,
        @NotNull URI url
) {}
~~~

Tương tự, `Map<String, @Valid Settings>` chỉ có giá trị khi `Settings` chứa các constraints hoặc nested constraints cần kiểm tra.

## 31. Lỗi phổ biến: kiểm tra collection nhưng bỏ quên item

~~~java
@NotEmpty List<Endpoint> endpoints
~~~

Yêu cầu List có ít nhất một phần tử; không tự kiểm tra endpoint fields. Cần:

~~~java
@NotEmpty List<@NotNull @Valid Endpoint> endpoints
~~~

và constraints bên trong Endpoint.

## 32. Lỗi phổ biến: numeric constraint nhưng thiếu @NotNull

~~~java
List<@Min(1) Integer> limits
~~~

Với Bean Validation, null thường được xem là hợp lệ đối với `@Min`. Nếu null là trạng thái bị cấm:

~~~java
List<@NotNull @Min(1) Integer> limits
~~~

Dùng `Integer` nếu cần phân biệt absence, nhưng phải viết hợp đồng rõ ràng. Nếu dùng primitive `int` trong record, giá trị thiếu có thể thành 0, và `@Min(1)` có thể giúp phát hiện.

## 33. Lỗi phổ biến: nhầm cấu trúc Map với List

Một Map theo tên:

~~~yaml
clients:
  definitions:
    billing:
      max-connections: 5
~~~

khác List:

~~~yaml
clients:
  definitions:
    - name: "billing"
      max-connections: 5
~~~

Nếu Java đích là `Map<String, Client>`, dùng YAML mapping theo tên key. Nếu Java đích là `List<Client>`, dùng YAML sequence. Không nên sửa annotation validation để giải lỗi YAML có cấu trúc không tương ứng với target type.

## 34. Lỗi phổ biến: Map entry hợp lệ về field nhưng sai tên

Một map key `"legacy-prod"` có thể thỏa `@NotBlank` nhưng không được ứng dụng hỗ trợ. Nếu có tập giá trị hợp lệ, dùng `@Pattern`, enum/naming policy hoặc validator kiểm tra membership; không chỉ dùng `@NotBlank`.

Nếu cần kiểm tra các key hợp lệ thuộc tập xác định, ví dụ chỉ `billing` và `inventory`, có thể kiểm tra `keySet()` sau binding hoặc tạo custom constraint. Điều này là rule của ứng dụng, không phải ràng buộc collection mặc định.

## 35. Lỗi phổ biến: @Valid mà nested object null

~~~java
public record AppProperties(
        @Valid Client client
) {}
~~~

Nếu `client=null`, cascading thường bỏ qua giá trị null. Nếu bắt buộc có client:

~~~java
public record AppProperties(
        @NotNull @Valid Client client
) {}
~~~

Tương tự cho value của Map và phần tử List. Phân biệt `@Valid` là **duyệt tiếp** còn `@NotNull` là **bắt buộc tồn tại**.

## 36. Checklist triển khai

Trước khi phát hành configuration-properties bean chứa collection/Map:

1. Root class đã có `@ConfigurationProperties`, `@Validated` và registration phù hợp chưa?
2. Đã bổ sung Bean Validation provider tương thích với Spring Boot chưa?
3. Collection có bắt buộc tồn tại và không rỗng không? Chọn `@NotNull`/`@NotEmpty`/`@Size` phù hợp.
4. Phần tử là String/Number? Đặt constraint đúng ở container element type.
5. Phần tử là object? Dùng `@Valid` để cascade và constraints trên fields.
6. Có cần cấm phần tử null? Dùng `@NotNull` ở type argument.
7. Map key có quy tắc? Dùng constraint đúng kiểu, xem key sau binding.
8. Map value có rule? Dùng constraint trực tiếp hoặc `@Valid` vào value object.
9. Có collection nested trong Map/record không? Kiểm tra từng tầng.
10. Có thay List qua profile không? Xác định list hiệu lực đầy đủ, không dựa vào merge theo index.
11. Map có kế thừa field từ nguồn thấp hơn không? Đảm bảo đó là ý định mong muốn.
12. Các constraint có hỗ trợ kiểu dữ liệu đang dùng không?
13. Có ràng buộc liên phần tử như uniqueness/ordering? Thiết kế validator riêng.
14. Có logic phụ thuộc `enabled`? Áp dụng conditional/cross-field validation phù hợp.
15. Có test startup với cấu hình thiếu/rỗng/sai kiểu và giá trị vi phạm constraint không?
16. Có tránh in bí mật khi chẩn đoán lỗi cấu hình không?

## 37. Bài tập tổng hợp

Cho cấu hình:

~~~yaml
dispatch:
  recipients:
    - "ops@example.invalid"
    - ""
  routes:
    urgent:
      destination: "https://urgent.example.invalid"
      max-attempts: 3
    ordinary:
      destination: "https://ordinary.example.invalid"
      max-attempts: 0
~~~

Yêu cầu:

- Có ít nhất một recipient.
- Không recipient nào blank.
- Map routes không rỗng.
- Mỗi route có tên key không blank.
- Mỗi route value không null.
- Mỗi route destination khác null.
- Số lần thử lại ít nhất 1.

Một cấu trúc:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "dispatch")
public record DispatchProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients,

        @NotEmpty
        Map<@NotBlank String, @NotNull @Valid Route> routes
) {
    public record Route(
            @NotNull URI destination,
            @Min(1) int maxAttempts
    ) {}
}
~~~

Dự đoán:

1. Recipient thứ hai là `""` nên vi phạm `@NotBlank`.
2. Map có hai entries nên `@NotEmpty` qua.
3. Cả hai route key đều không blank nên key constraints qua.
4. Route ordinary có `maxAttempts=0` nên vi phạm `@Min(1)`.
5. Các URI khác null, không vi phạm `@NotNull`; nhưng validator URI scheme/host nếu được yêu cầu phải thiết kế thêm.

Sửa YAML:

~~~yaml
dispatch:
  recipients:
    - "ops@example.invalid"
    - "audit@example.invalid"
  routes:
    urgent:
      destination: "https://urgent.example.invalid"
      max-attempts: 3
    ordinary:
      destination: "https://ordinary.example.invalid"
      max-attempts: 2
~~~

Với dependency validation và registration đúng, cấu hình này có thể vượt qua các constraint đã định nghĩa.

## 38. Kết luận

Khi bind collection và Map trong Spring Boot:

- `@NotNull`, `@NotEmpty` và `@Size` trên container kiểm tra **sự tồn tại và kích thước của container**, không tự kiểm tra mọi phần tử.
- Container-element constraints như `List<@NotBlank String>`, `List<@Min(1) Integer>`, `Map<String, @NotBlank String>` cho phép kiểm tra **giá trị ở từng vị trí**.
- `@Valid` trên element/value type như `List<@Valid Endpoint>` hoặc `Map<String, @Valid Client>` kích hoạt **cascaded validation** vào object lồng nhau, miễn là object có constraints.
- Nếu cấm phần tử null, kết hợp `@NotNull` với `@Valid`; bản thân `@Valid` không làm null thành vi phạm.
- Nếu một profile thay List hoặc Map kết hợp dữ liệu từ nhiều nguồn, validation được áp dụng lên **cấu hình hiệu lực sau binding**, không phải từng file YAML riêng.
- Lỗi conversion, lỗi cấu trúc YAML, lỗi registration và lỗi constraint là các nhóm khác nhau; cần chẩn đoán đúng lớp.

**Ghi nhớ:** muốn dữ liệu cấu hình an toàn, hãy đặt constraint ở **đúng tầng**: root collection, phần tử, Map key, Map value và nested object. `@Validated` + `@Valid` + container-element constraints là bộ công cụ chính để phát hiện dữ liệu không hợp lệ trước khi ứng dụng bắt đầu xử lý nghiệp vụ.
