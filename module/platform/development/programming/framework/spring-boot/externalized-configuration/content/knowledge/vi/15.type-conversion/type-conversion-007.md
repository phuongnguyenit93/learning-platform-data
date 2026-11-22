# Tạo Converter tùy chỉnh với `@ConfigurationPropertiesBinding` trong Spring Boot 3.3

## 1. Tại sao cần Converter tùy chỉnh?

Spring Boot được thiết kế để nhận cấu hình từ nhiều nguồn: `application.properties`, `application.yaml`, các tệp cấu hình bên ngoài, biến môi trường, thuộc tính hệ thống JVM, `SPRING_APPLICATION_JSON` và đối số dòng lệnh. Khi một kiểu được đánh dấu `@ConfigurationProperties`, Spring Boot Binder sẽ đọc các khóa có cùng tiền tố, áp dụng quy tắc tên linh hoạt (*relaxed binding*) và chuyển những giá trị đầu vào về kiểu Java tương ứng.

Các kiểu thông thường như `String`, `int`, `boolean`, `Duration`, `DataSize`, `URI`, enum và nhiều kiểu của Java đã được Spring Boot hỗ trợ chuyển đổi. Nhưng ứng dụng thường có **kiểu miền riêng** (*domain-specific type*) mà Binder không biết cách tạo từ một chuỗi.

Giả sử một hệ thống xử lý tác vụ có cấu hình:

```properties
app.worker.primary=ap-southeast-1:12
```

Đội phát triển muốn biểu diễn giá trị này dưới dạng đối tượng Java:

```java
public record RegionQuota(String region, int capacity) {}
```

`ap-southeast-1:12` là quy ước riêng: phần trước dấu `:` là mã vùng, phần sau là năng lực xử lý tối đa. Binder không thể tự suy ra quy tắc tách hai thành phần từ một chuỗi đơn.

Trong Spring Boot 3.3, ta có thể viết:

```java
Converter<String, RegionQuota>
```

và đăng ký nó dưới dạng bean được đánh dấu **`@ConfigurationPropertiesBinding`**. Khi đó Spring Boot có thể sử dụng converter trong quá trình liên kết giá trị của `@ConfigurationProperties`.

**Mục tiêu bài học:**

- Hiểu vị trí của converter trong chuỗi **nguồn cấu hình → Binder → đối tượng Java**.
- Biết khi nào cần viết converter và khi nào nên dùng các chuyển đổi có sẵn.
- Viết `Converter<String, T>` có quy tắc parse rõ ràng và thông báo lỗi phù hợp.
- Đăng ký converter với `@ConfigurationPropertiesBinding` đúng package, đúng thời điểm khởi tạo.
- Hiểu lý do nên dùng một phương thức `@Bean static` khi đăng ký converter bằng Java configuration.
- Sử dụng converter cho scalar, phần tử `List<T>` và tham số constructor của record.
- Phân biệt **chuyển đổi định dạng** với **validation nghiệp vụ**.
- Kiểm thử converter đơn lẻ và kiểm thử việc Spring Boot thực sự dùng converter khi binding.
- Xử lý các lỗi phổ biến liên quan generic type, lifecycle, tên cấu hình và thứ tự ưu tiên nguồn.

Các ví dụ dùng **Java 17+** và **Spring Boot 3.3.x**.

## 2. Converter nằm ở đâu trong quá trình nạp cấu hình?

Một luồng đơn giản:

```text
application.yaml / application.properties
          |
          | app.worker.primary=ap-southeast-1:12
          v
      Spring Environment
          |
          v
   @ConfigurationProperties Binder
          |
          +-- tìm khóa theo prefix
          +-- áp dụng relaxed binding
          +-- xác định kiểu Java đích
          +-- tìm bộ chuyển đổi phù hợp
                        |
                        v
       Converter<String, RegionQuota>
                        |
                        v
       RegionQuota("ap-southeast-1", 12)
                        |
                        v
        WorkerProperties.primary()
                        |
                        v
     Service sử dụng bean cấu hình đã bind
```

Điểm then chốt: converter chạy **khi cần chuyển một giá trị của nguồn cấu hình sang kiểu đích**. Nó không thay thế `PropertySource`, không thay thế logic xác định nguồn nào có ưu tiên cao nhất, và không tự chọn profile.

Trong ví dụ, Spring Boot có thể lấy chuỗi `"ap-southeast-1:12"` từ YAML. Converter chỉ nhận chuỗi đó để tạo `RegionQuota`.

Điều này cũng có nghĩa:

- Nếu khóa không tồn tại, converter không nhất thiết được gọi.
- Nếu một đối số dòng lệnh ghi đè chuỗi trong YAML, converter nhận **giá trị có hiệu lực** được Binder sử dụng.
- Nếu giá trị đã có kiểu phù hợp mà Binder không cần dùng cặp chuyển đổi `String -> RegionQuota`, converter có thể không tham gia.
- Converter không giải quyết xung đột giá trị giữa các nguồn; nó chỉ xử lý **cách diễn giải một giá trị**.

## 3. Kiểm tra các converter có sẵn trước khi tự viết

Không phải cứ thấy chuỗi trong YAML là phải tạo converter. Spring Boot 3.3 đã hỗ trợ nhiều kiểu cấu hình phổ biến.

Ví dụ:

```yaml
app:
  http:
    enabled: true
    connect-timeout: 250ms
    read-timeout: 5s
    max-payload: 10MB
    endpoint: https://api.example.test
```

Có thể liên kết vào:

```java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        boolean enabled,
        Duration connectTimeout,
        Duration readTimeout,
        DataSize maxPayload,
        URI endpoint
) {
}
```

Một số import:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;
```

Spring Boot đã có chuyển đổi tương ứng cho `Duration`, `DataSize` và nhiều loại giá trị chuẩn. Tự định nghĩa lại converter cho `Duration` hoặc `String` có thể thay đổi hành vi phổ biến của toàn bộ cấu hình, khiến một thay đổi nhỏ ảnh hưởng nhiều bean không liên quan.

**Hãy tự viết converter khi đầu vào có cú pháp riêng và kiểu đích biểu diễn một khái niệm miền riêng.** Với giá trị đã có thể mô tả bằng các thuộc tính con thông thường, cân nhắc dùng nested `@ConfigurationProperties` thay vì phát minh định dạng chuỗi riêng.

Ví dụ không cần converter:

```yaml
app:
  worker:
    primary:
      region: ap-southeast-1
      capacity: 12
```

Binder có thể liên kết một cấu trúc YAML như thế vào record lồng:

```java
public record RegionQuota(String region, int capacity) {}
```

Nhưng nếu có yêu cầu giữ cấu hình ngắn gọn như:

```yaml
app:
  worker:
    primary: "ap-southeast-1:12"
```

thì một `Converter<String, RegionQuota>` trở nên hợp lý.

## 4. Phân biệt `Converter`, `ConversionService` và `@ConfigurationPropertiesBinding`

Ba khái niệm liên quan nhưng không đồng nhất:

| Thành phần | Mục đích | Phạm vi |
| --- | --- | --- |
| `Converter<S, T>` | Định nghĩa cách chuyển từ một kiểu nguồn `S` sang kiểu đích `T` | Một cặp kiểu nguồn/đích |
| `ConversionService` | Dịch vụ quản lý và tìm các converter phù hợp | Cơ chế chuyển đổi kiểu |
| `@ConfigurationPropertiesBinding` | Đánh dấu bean dùng để hỗ trợ liên kết `@ConfigurationProperties` | Bộ converter/property binding của Spring Boot |

Giao diện Spring Framework:

```java
import org.springframework.core.convert.converter.Converter;
```

Có phương thức:

```java
T convert(S source);
```

Trong đó `S` là kiểu đầu vào, `T` là kiểu đầu ra.

Với cấu hình dạng chuỗi:

```java
Converter<String, RegionQuota>
```

là lựa chọn tự nhiên. Khi Spring Boot cần tạo `RegionQuota` từ một chuỗi, converter có thể được tìm và sử dụng trong quá trình binding.

Annotation của Spring Boot 3.3 cần import chính xác:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
```

Đây là **qualifier cho bean** phục vụ `@ConfigurationProperties`. Nó không phải annotation đặt trên một record cấu hình để “bật binding”, cũng không phải một cơ chế tự triển khai mọi phép chuyển đổi.

Để kiểu được bind từ một prefix, ta vẫn cần:

```java
@ConfigurationProperties(prefix = "app.worker")
```

và phải đăng ký kiểu cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 5. Thiết kế cú pháp chuyển đổi rõ ràng

Trước khi viết mã converter, cần có hợp đồng dữ liệu đầu vào.

Trong bài này:

```text
<region>:<capacity>
```

Ví dụ hợp lệ về **cú pháp**:

```text
ap-southeast-1:12
eu-west-1:6
us-east-1:4
```

Kiểu đích:

```java
public record RegionQuota(String region, int capacity) {}
```

Các quyết định cần thống nhất:

1. Dấu phân cách là dấu `:` duy nhất.
2. `region` là chuỗi sau khi loại khoảng trắng ở hai đầu.
3. `capacity` là số nguyên theo cơ số 10 sau khi loại khoảng trắng ở hai đầu.
4. Nếu thiếu phần trước/sau dấu phân cách hoặc có quá nhiều dấu `:`, converter báo lỗi cú pháp.
5. Nếu phần capacity không chuyển thành `int` được, converter báo lỗi chuyển kiểu.
6. Quy tắc *capacity phải lớn hơn 0* là quy tắc nghiệp vụ được kiểm tra bằng Bean Validation trong model.

Tách quy tắc **parse cú pháp** và **validation miền giá trị** giúp người đọc hiểu rõ lỗi nào xuất phát từ đâu.

Ví dụ:

| Giá trị | Parse được? | Có thể đạt nghiệp vụ? |
| --- | --- | --- |
| `ap-southeast-1:12` | Có | Có |
| `eu-west-1:0` | Có | Không nếu capacity phải ≥ 1 |
| `ap-southeast-1:-3` | Có | Không nếu capacity phải ≥ 1 |
| `eu-west-1:abc` | Không | Chưa tạo được đối tượng |
| `eu-west-1` | Không | Thiếu dấu `:` và capacity |
| `us:2:extra` | Không | Có quá nhiều phần |
| `:10` | Có thể tạo đối tượng với region rỗng nếu parser cho phép | Không đạt `@NotBlank` |
| `bad region:5` | Có thể parse được | Có thể vi phạm mẫu mã vùng |
| `ap-southeast-1:999999999999` | Không thể chuyển thành `int` | Không đạt ở bước conversion |

Đây là một ví dụ cố ý đơn giản. Với URI có dấu `:` trong scheme, IPv6 có dấu `:`, hoặc giá trị chứa các dấu phân tách lồng nhau, cần thiết kế cú pháp khác thay vì dùng `split(":")` tùy tiện.

## 6. Bước 1 — tạo kiểu Java riêng

Tạo file:

`src/main/java/example/configconversion/RegionQuota.java`

```java
package example.configconversion;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record RegionQuota(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9-]*")
        String region,

        @Min(1)
        int capacity
) {
}
```

Trong ứng dụng có dependency Bean Validation và validation được kích hoạt:

- `@NotBlank` ngăn region rỗng hoặc chỉ có khoảng trắng.
- `@Pattern` quy định mã vùng dùng chữ thường, số và dấu gạch nối; bắt đầu bằng chữ thường.
- `@Min(1)` yêu cầu capacity lớn hơn hoặc bằng 1.

Đây là **mô hình dữ liệu đích**, không chứa logic tự đọc YAML. Record có component rõ tên và kiểu, dễ dùng trong các service.

Trong một ứng dụng nhỏ không cần validation, có thể dùng record chưa có annotation:

```java
public record RegionQuota(String region, int capacity) {}
```

Nhưng nên giữ riêng trách nhiệm của converter và trách nhiệm của validation khi mô hình bắt đầu có quy tắc nghiệp vụ.

### Tại sao không đặt `String raw` ở mọi nơi?

Có thể viết:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(String primary) {}
```

và mỗi service tự tách `"ap-southeast-1:12"`. Nhưng cách này khiến:

- Cú pháp phân tích bị lặp lại trong nhiều nơi.
- Service phải biết chi tiết dấu phân cách của cấu hình.
- Lỗi nhập liệu có thể chỉ xuất hiện khi một request thật đi qua.
- Việc thay định dạng đòi hỏi sửa nhiều đoạn code.

Kiểu `RegionQuota` gom ý nghĩa “mã vùng + capacity” thành một đối tượng. Converter gom quy tắc parse tại **một điểm trung tâm**.

## 7. Bước 2 — viết `Converter<String, RegionQuota>`

Tạo file:

`src/main/java/example/configconversion/RegionQuotaConverter.java`

```java
package example.configconversion;

import org.springframework.core.convert.converter.Converter;

public final class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    @Override
    public RegionQuota convert(String source) {
        String[] parts = source.trim().split(":", -1);

        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected region:capacity with one ':' separator");
        }

        String region = parts[0].trim();
        String number = parts[1].trim();

        try {
            int capacity = Integer.parseInt(number);
            return new RegionQuota(region, capacity);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Capacity must be a valid 32-bit integer", ex);
        }
    }
}
```

### Vì sao dùng `split(":", -1)`?

Giá trị thứ hai `-1` yêu cầu Java giữ cả những phần rỗng ở cuối chuỗi.

Ví dụ:

```text
"eu-west-1:" -> ["eu-west-1", ""]
```

Sau đó `Integer.parseInt("")` thất bại theo đúng mong đợi. Nếu dùng `split(":")` mặc định, các phần rỗng cuối có thể bị loại bỏ, khiến việc giải thích lỗi kém rõ ràng.

### Vì sao dùng `trim()`?

Người dùng có thể nhập:

```properties
app.worker.primary= ap-southeast-1 : 12
```

Trong phạm vi cú pháp mà dự án chấp nhận, converter có thể loại bỏ khoảng trắng trước khi tách thành phần. Đây là lựa chọn của hợp đồng chuyển đổi; một converter cho chữ ký số hoặc token có khoảng trắng ý nghĩa có thể **không nên trim**.

### Vì sao không ghi toàn bộ chuỗi nguồn vào thông báo lỗi?

Các giá trị cấu hình đôi khi chứa host nội bộ, token hoặc bí mật. Ví dụ `region:capacity` không có bí mật, nhưng một converter tổng quát hơn có thể được dùng với URI chứa credentials. Nên ưu tiên thông báo mô tả **hình thức mong đợi** hơn là in nguyên giá trị nhạy cảm.

### Converter này có cần state hoặc dependency bên ngoài không?

Không. Converter chỉ diễn giải chuỗi theo quy tắc thuần Java:

```text
String -> RegionQuota
```

Nó không cần repository, HTTP client, `Environment`, logger đặc biệt hoặc gọi dịch vụ bên ngoài. **Càng ít phụ thuộc và càng ít side effect, converter càng phù hợp với giai đoạn binding sớm.**

## 8. Bước 3 — đăng ký converter bằng `@ConfigurationPropertiesBinding`

Tạo file:

`src/main/java/example/configconversion/BindingConvertersConfiguration.java`

```java
package example.configconversion;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class BindingConvertersConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionQuota> regionQuotaConverter() {
        return new RegionQuotaConverter();
    }
}
```

Đây là một cách đăng ký rõ ràng và phù hợp với Spring Boot 3.3.

Phân tích:

- `@Configuration` đưa lớp định nghĩa bean vào Spring context thông qua component scanning phù hợp.
- `@Bean` đăng ký đối tượng converter thành Spring bean.
- `@ConfigurationPropertiesBinding` xác định converter này được dùng cho **binding cấu hình**.
- Phương thức `static` tránh việc phải khởi tạo sớm đối tượng lớp cấu hình chỉ để gọi phương thức `@Bean`.
- Kiểu trả về `Converter<String, RegionQuota>` thể hiện cặp kiểu nguồn/đích, hỗ trợ việc xác định converter phù hợp.

Trong trường hợp này, bạn **không** phải định nghĩa một bean tên `conversionService` chỉ để có thêm một converter.

### Vì sao `static` được khuyến nghị?

Theo tài liệu Spring Boot 3.3, những bean tham gia chuyển đổi cấu hình được yêu cầu **rất sớm** trong vòng đời ứng dụng. Với phương thức `@Bean` có `@ConfigurationPropertiesBinding`, Spring Boot khuyến nghị dùng `static` nhằm tránh các cảnh báo dạng:

```text
Bean ... is not eligible for getting processed by all BeanPostProcessors
```

Một phương thức `@Bean` bình thường thường cần instance của lớp `@Configuration`. Nếu binder cần converter quá sớm, việc tạo instance đó trước khi mọi BeanPostProcessor sẵn sàng có thể gây cảnh báo và những hậu quả khó đoán trong thiết kế phức tạp.

Vì vậy:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RegionQuota> regionQuotaConverter() {
    return new RegionQuotaConverter();
}
```

là mẫu nên ưu tiên.

**Không có nghĩa mọi `@Bean` đều phải static.** Khuyến nghị này gắn với converter dùng ở giai đoạn binding cấu hình sớm.

## 9. Có thể đăng ký bằng `@Component` không?

Một converter được đánh dấu trực tiếp bằng `@Component` và `@ConfigurationPropertiesBinding` cũng có thể được Spring quét làm bean:

```java
@Component
@ConfigurationPropertiesBinding
public class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    @Override
    public RegionQuota convert(String source) {
        // Parse dữ liệu cấu hình tại đây.
        return ...;
    }
}
```

Đây là mẫu **minh họa lựa chọn đăng ký**, không phải file thứ hai cần tạo đồng thời trong ví dụ đầy đủ. Nếu dùng cách `@Component`, hãy đặt triển khai hoàn chỉnh của converter vào lớp này và không đăng ký thêm một bean khác cho cùng converter một cách không cần thiết.

So sánh:

| Cách đăng ký | Ưu điểm | Lưu ý |
| --- | --- | --- |
| `@Bean static` + `@ConfigurationPropertiesBinding` | Rõ ràng, kiểm soát tên bean và thời điểm khởi tạo | Cần lớp configuration chứa method |
| `@Component` + `@ConfigurationPropertiesBinding` | Ít code cấu hình riêng | Phụ thuộc vào phạm vi component scan; tránh injection nặng vào converter |
| `ConversionService` riêng | Có thể quản lý nhiều converter ở một nơi | Phức tạp hơn, cần hiểu thời điểm bean được gọi và phạm vi áp dụng |
| `@Bean` không gắn qualifier | Không rõ bean có tham gia binder chuyên biệt hay không | Không phải mẫu nên chọn cho converter cấu hình riêng |

Trong bài thực hành, ta dùng **`@Bean static`** để rõ chủ đích và giảm rủi ro khởi tạo sớm.

### Không gắn annotation vào model thay cho converter

Sai về ý tưởng:

```java
@ConfigurationPropertiesBinding
public record RegionQuota(String region, int capacity) {}
```

Annotation này không biến record thành một converter. Record là **kiểu đích**; converter là **bean nhận giá trị nguồn và tạo ra kiểu đích**.

Đúng về phân vai:

```text
RegionQuota                  -> kiểu dữ liệu
RegionQuotaConverter         -> Converter<String, RegionQuota>
BindingConvertersConfiguration
    @Bean
    @ConfigurationPropertiesBinding
    static ...               -> đăng ký converter cho Binder
WorkerProperties             -> model @ConfigurationProperties sử dụng RegionQuota
```

## 10. Bước 4 — tạo `@ConfigurationProperties` sử dụng kiểu riêng

Tạo file:

`src/main/java/example/configconversion/WorkerProperties.java`

```java
package example.configconversion;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Valid RegionQuota primary,
        @NotEmpty List<@Valid RegionQuota> fallbacks,
        @NotNull Duration timeout
) {
    @AssertTrue(message = "timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout != null
                && timeout.compareTo(Duration.ZERO) > 0;
    }
}
```

Cần chú ý:

1. **`primary` là một `RegionQuota`**, nhưng giá trị cấu hình của nó là một chuỗi.
2. `fallbacks` là `List<RegionQuota>`; mỗi phần tử có thể được Binder xử lý bằng cùng converter nếu nguồn của phần tử là chuỗi.
3. `timeout` là `Duration`; không cần tự viết converter, vì Spring Boot đã hỗ trợ.
4. `@Validated` + Bean Validation kiểm tra những ràng buộc được khai báo.
5. `@Valid` trên `primary` và phần tử danh sách đưa validation vào `RegionQuota`.
6. `@NotEmpty` yêu cầu danh sách fallback không rỗng trong ví dụ nghiệp vụ này.
7. `@AssertTrue` kiểm tra timeout dương, không đồng nhất với việc chuỗi `5s` chuyển được sang `Duration`.

Đây là một record dùng constructor binding thông thường. Vì nó có constructor canonical phù hợp duy nhất nên Spring Boot 3.3 không đòi hỏi thêm `@ConstructorBinding`.

### Dùng `@ConfigurationProperties` với YAML

Tạo:

`src/main/resources/application.yaml`

```yaml
spring:
  application:
    name: custom-config-converter-demo

app:
  worker:
    primary: "ap-southeast-1:12"
    fallbacks:
      - "eu-west-1:6"
      - "us-east-1:4"
    timeout: 5s
```

Các chuỗi trong dấu nháy là **giá trị cấu hình**; dấu nháy YAML không phải ký tự thuộc region. Với `RegionQuotaConverter`:

```text
primary   = RegionQuota(region=ap-southeast-1, capacity=12)
fallbacks = [
  RegionQuota(region=eu-west-1, capacity=6),
  RegionQuota(region=us-east-1, capacity=4)
]
timeout   = PT5S
```

Với danh sách, Binder xử lý từng phần tử theo cặp chuyển đổi `String -> RegionQuota`, không phải ghép toàn bộ danh sách thành một chuỗi rồi gọi converter một lần.

### Tương đương trong `.properties`

```properties
spring.application.name=custom-config-converter-demo

app.worker.primary=ap-southeast-1:12
app.worker.fallbacks[0]=eu-west-1:6
app.worker.fallbacks[1]=us-east-1:4
app.worker.timeout=5s
```

`WorkerProperties` không cần đổi. Converter hoạt động theo **giá trị đầu vào và kiểu đích**, không phụ thuộc trực tiếp vào việc nguồn ban đầu là `.properties` hay YAML.

## 11. Bước 5 — đăng ký configuration properties và sử dụng

Tạo file:

`src/main/java/example/configconversion/ConverterDemoApplication.java`

```java
package example.configconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfiguration(WorkerProperties properties) {
        return args -> {
            System.out.println("primary=" + properties.primary());
            System.out.println("fallbacks=" + properties.fallbacks());
            System.out.println("timeout=" + properties.timeout());
        };
    }
}
```

Lớp `ConverterDemoApplication` nằm cùng gói hoặc trên gói cha của `WorkerProperties` và `BindingConvertersConfiguration`, nên component scan thông thường có thể tìm thấy class cấu hình converter; `@ConfigurationPropertiesScan` tìm thấy kiểu `WorkerProperties`.

**Phân biệt hai việc quét:**

- `@SpringBootApplication` bao gồm component scanning cho bean cấu hình converter (nếu đúng phạm vi package).
- `@ConfigurationPropertiesScan` tìm các kiểu được đánh dấu `@ConfigurationProperties`.

Một kiểu `@ConfigurationProperties` dùng constructor binding **không cần** thêm `@Component`. Việc thêm `@Component` có thể khiến Spring tạo đối tượng bằng cơ chế bean thông thường thay vì Binder constructor binding.

### Dependency Maven

Ví dụ Maven có Spring Boot dependency management phù hợp; bạn cần `spring-boot-starter` và, vì ví dụ sử dụng `@Validated` cùng Jakarta Bean Validation, thêm starter validation:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Với project Spring Boot 3.3 dùng Maven parent/Gradle plugin, các phiên bản dependency Spring tương ứng thường được quản lý bởi Boot. Đừng trộn tùy tiện phiên bản Spring Framework khác với bản Boot đang dùng.

## 12. Chạy ứng dụng và quan sát

Trong dự án có Maven wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc đóng gói:

```bash
./mvnw package
java -jar target/ten-ung-dung-thuc-te.jar
```

`ten-ung-dung-thuc-te.jar` là tên minh họa; thay bằng JAR do quá trình build tạo ra.

Kết quả chính do `ApplicationRunner` in dự kiến:

```text
primary=RegionQuota[region=ap-southeast-1, capacity=12]
fallbacks=[RegionQuota[region=eu-west-1, capacity=6], RegionQuota[region=us-east-1, capacity=4]]
timeout=PT5S
```

Dạng `RegionQuota[...]` là cách `record` mặc định biểu diễn `toString()`. Giá trị `PT5S` là dạng chuỗi của `Duration` năm giây.

Nếu các giá trị đọc được như trên, ứng dụng đã:

1. Tìm các khóa `app.worker.*`.
2. Liên kết `primary` với kiểu riêng `RegionQuota`.
3. Sử dụng converter cho các phần tử danh sách.
4. Dùng converter sẵn có cho `Duration`.
5. Xây dựng `WorkerProperties`.
6. Áp dụng validation cho các constraint đã khai báo.

Điều này chưa có nghĩa `"ap-southeast-1"` là region hợp lệ đối với một dịch vụ đám mây thật. Nếu dùng tên region thực tế của nhà cung cấp, cần chính sách hoặc tài liệu tương ứng.

## 13. Thử ghi đè cấu hình từ đối số dòng lệnh

Đối số dòng lệnh thường có ưu tiên cao hơn cấu hình trong `application.yaml`:

```bash
java -jar target/ten-ung-dung-thuc-te.jar \
  --app.worker.primary=eu-central-1:8
```

Khi không có nguồn khác ưu tiên cao hơn và converter đăng ký đúng, `primary` sẽ nhận:

```text
RegionQuota[region=eu-central-1, capacity=8]
```

Converter không cần biết giá trị này đến từ dòng lệnh hay YAML. Đó là nhiệm vụ của hệ thống `PropertySource` và Binder.

Trong PowerShell, ví dụ tương ứng:

```powershell
java -jar .\target\ten-ung-dung-thuc-te.jar `
  '--app.worker.primary=eu-central-1:8'
```

Dấu backtick ở cuối dòng là cú pháp nối dòng của PowerShell. Có thể tránh khác biệt shell bằng cách viết một dòng:

```powershell
java -jar .\target\ten-ung-dung-thuc-te.jar '--app.worker.primary=eu-central-1:8'
```

Nếu truyền giá trị có dấu `&`, khoảng trắng, `$` hoặc ký tự điều khiển shell, hãy nháy đúng để Java nhận **một đối số**. Đây là vấn đề ở tầng shell, khác với cơ chế converter.

## 14. Thử giá trị lỗi: tách conversion failure với validation failure

### 14.1. Không có dấu phân cách

```properties
app.worker.primary=ap-southeast-1
```

Converter nhận một phần tử thay vì hai, rồi báo:

```text
Expected region:capacity with one ':' separator
```

Ứng dụng có thể không tạo được `WorkerProperties` vì không thể chuyển từ chuỗi sang `RegionQuota`.

Đó là **lỗi chuyển đổi cú pháp**, không phải lỗi Bean Validation.

### 14.2. Capacity không phải số

```properties
app.worker.primary=ap-southeast-1:many
```

`Integer.parseInt("many")` ném `NumberFormatException`, được converter bọc lại với thông báo:

```text
Capacity must be a valid 32-bit integer
```

Bộ Binder có thể hiển thị chuỗi nguyên nhân bên trong các ngoại lệ dạng binding/conversion. Đừng phụ thuộc vào đúng một loại ngoại lệ bao ngoài trong mọi ngữ cảnh; kiểm tra root cause và tên thuộc tính gây lỗi.

### 14.3. Capacity bằng 0

```properties
app.worker.primary=ap-southeast-1:0
```

Converter **có thể tạo**:

```text
RegionQuota[region=ap-southeast-1, capacity=0]
```

Nhưng nếu model có:

```java
@Min(1) int capacity
```

và validation được kích hoạt, cấu hình bị từ chối vì **quy tắc nghiệp vụ**, không phải parser không hiểu số 0.

### 14.4. Region không phù hợp pattern

```properties
app.worker.primary=Bad Region:12
```

Converter có thể tách chuỗi thành `"Bad Region"` và `12`. Tuy nhiên, `@Pattern(regexp = "[a-z][a-z0-9-]*")` không cho phép dấu cách/chữ hoa, nên validation từ chối.

### 14.5. Timeout sai định dạng

```properties
app.worker.timeout=five-seconds
```

Converter `RegionQuotaConverter` không có trách nhiệm xử lý khóa này. Spring Boot cố dùng quy tắc chuyển kiểu **chuẩn cho `Duration`**, và thất bại nếu chuỗi không phải định dạng thời lượng được hỗ trợ.

Điều này minh họa hai converter có phạm vi khác nhau:

```text
String -> RegionQuota  : converter tùy chỉnh của ứng dụng
String -> Duration     : chuyển đổi chuẩn của Spring Boot
```

## 15. `@ConfigurationPropertiesBinding` là qualifier, không phải tên prefix

Có một số nhầm lẫn thường gặp.

### Nhầm lẫn A — annotation chứa prefix

Sai:

```java
@ConfigurationPropertiesBinding(prefix = "app.worker")
```

Không có ý nghĩa như vậy. Annotation này đánh dấu converter bean, không khai báo một nhóm khóa.

Prefix nằm ở model:

```java
@ConfigurationProperties(prefix = "app.worker")
```

### Nhầm lẫn B — converter được gọi cho mọi thuộc tính

`Converter<String, RegionQuota>` phục vụ những chỗ cần chuyển **chuỗi sang `RegionQuota`** trong context binding phù hợp. Nó không tự chạy khi Binder cần `String -> Duration` hoặc `String -> int`.

Ngược lại, nếu nhiều bean cấu hình trong cùng ứng dụng có trường kiểu `RegionQuota`, converter có thể được dùng ở **nhiều prefix khác nhau**. Đây không phải converter chỉ áp dụng cho `"app.worker.primary"`.

### Nhầm lẫn C — qualifier làm mọi bean nhìn thấy converter

`@ConfigurationPropertiesBinding` giúp Spring Boot nhận biết bean dành cho việc liên kết configuration properties. Đừng tự suy luận rằng mọi API dùng `ApplicationConversionService`, mọi `@Value` hoặc mọi form formatter trong Spring MVC sẽ dùng converter này theo đúng cùng quy trình.

Nếu một phần khác của ứng dụng cần cùng chuyển đổi, có thể đăng ký converter vào đúng `ConversionService` của phần đó, hoặc gọi một hàm parse dùng chung. Hãy phân biệt **configuration binding conversion** với chuyển đổi dữ liệu ở các tầng khác.

### Nhầm lẫn D — chỉ tạo `new RegionQuotaConverter()` là đủ

Nếu không có bean được đăng ký hoặc không có cách đưa converter vào ConversionService được Binder sử dụng, Spring Boot không có lý do gì tự tìm đối tượng Java do bạn tạo riêng trong một hàm bất kỳ.

Cần khai báo bean với qualifier như ví dụ:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RegionQuota> regionQuotaConverter() {
    return new RegionQuotaConverter();
}
```

## 16. Vòng đời khởi tạo sớm: tránh dependency phức tạp

Đây là một trong những điểm quan trọng nhất khi làm converter cho `@ConfigurationProperties`.

Theo Spring Boot 3.3 Reference, những bean dùng cho chuyển đổi kiểu cấu hình được yêu cầu **rất sớm** trong application lifecycle. Vì vậy, không nên thiết kế converter phụ thuộc vào các bean có thể chưa hoàn tất khởi tạo.

Ví dụ không nên làm:

```java
public class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    private final DatabaseRegionRepository repository;

    public RegionQuotaConverter(DatabaseRegionRepository repository) {
        this.repository = repository;
    }

    // convert() truy vấn database để quyết định có chấp nhận region...
}
```

Dù DI có thể hoạt động trong một số trường hợp, thiết kế trên tiềm ẩn những vấn đề:

- Repository có thể chưa sẵn sàng khi converter được yêu cầu.
- Có thể tạo vòng phụ thuộc: cấu hình cần converter, converter cần bean, bean lại cần cấu hình.
- Binding có thể kéo theo truy vấn DB, làm khởi động chậm và dễ thất bại vì lỗi mạng.
- Lỗi tạm thời của dịch vụ ngoài trở thành lỗi chuyển đổi dữ liệu.
- Unit test converter khó viết hơn.

Một thiết kế tốt hơn:

```text
Converter:
    cú pháp chuỗi -> đối tượng có kiểu

Bean Validation:
    miền giá trị, quan hệ trường, ràng buộc tĩnh

Service / readiness:
    kiểm tra tồn tại thực tế, database, network, credential, tài nguyên
```

Nếu cần một danh sách region hợp lệ cập nhật từ dịch vụ ngoài, hãy thiết kế **một bước xác thực riêng** thay vì biến converter thành nơi gọi network ẩn.

## 17. Không nên tự tạo bean `conversionService` khi chỉ cần một converter

Spring Boot cũng cho phép cung cấp một bean tên:

```text
conversionService
```

để phục vụ chuyển đổi kiểu cấu hình. Tuy nhiên, khi bạn tự định nghĩa một ConversionService tổng thể, bạn cần hiểu rằng nó có thể được yêu cầu rất sớm và cần đủ các converter tiêu chuẩn mà cấu hình đang dùng.

Ví dụ tạo một `ConversionService` rỗng hoặc thiếu những formatter mặc định có thể làm các thuộc tính `Duration`, `DataSize` hoặc enum gặp khó khăn mà trước đây không có.

Với một cặp kiểu riêng:

```text
String -> RegionQuota
```

cách đơn giản hơn là tạo **một converter được đánh dấu `@ConfigurationPropertiesBinding`**, để hệ thống binding thêm nó vào khả năng chuyển đổi phù hợp.

Nếu ứng dụng thật sự cần `ConversionService` tùy chỉnh cho nhiều mục đích ngoài configuration properties, hãy phân biệt tên bean và phạm vi, đừng vô tình thay đổi cơ chế binding của toàn ứng dụng.

### Khi nào cân nhắc converter tổng quát hơn?

Spring Framework còn có:

- `ConverterFactory<S, R>` cho một họ các kiểu đích có liên quan.
- `GenericConverter` cho các chuyển đổi phức tạp hoặc nhiều cặp kiểu.
- `ConditionalGenericConverter` khi cần quyết định chuyển đổi theo thông tin kiểu.

Những API này phù hợp với nhu cầu nâng cao. Đối với một format cấu hình rõ ràng, **`Converter<String, RegionQuota>` là mẫu dễ đọc và dễ bảo trì hơn**.

## 18. Converter không phải validation

Converter chịu trách nhiệm:

```text
"ap-southeast-1:12"
          |
          v
RegionQuota("ap-southeast-1", 12)
```

Validation chịu trách nhiệm:

```text
RegionQuota("ap-southeast-1", 12)
          |
          v
region có rỗng không?
region có đúng pattern không?
capacity >= 1 không?
```

Hai loại lỗi khác nhau:

| Trường hợp | Conversion | Validation |
| --- | --- | --- |
| `eu-west-1:abc` | Không tạo được đối tượng | Chưa có đối tượng hợp lệ để validate |
| `eu-west-1:0` | Có thể thành công | Vi phạm `@Min(1)` |
| `Bad Region:12` | Có thể thành công | Vi phạm `@Pattern` |
| `us-east-1:5` | Thành công | Đạt ràng buộc mẫu |
| `us-east-1:9999999999999` | `Integer.parseInt` thất bại | Không tới giai đoạn kiểm tra miền int |

Với những định dạng cần giữ tính nhất quán ngay từ khi tạo đối tượng, constructor của domain type có thể áp dụng bất biến riêng. Tuy nhiên, khi giải thích lỗi cấu hình, cần phân biệt lỗi do parser, lỗi do quy tắc mô hình và lỗi do Bean Validation để tránh thông báo quá chung chung.

### Không mặc định `@Validated` đã kiểm tra mọi object lồng nhau

Trong ví dụ, `WorkerProperties.primary` được đánh dấu:

```java
@NotNull @Valid RegionQuota primary
```

và danh sách:

```java
@NotEmpty List<@Valid RegionQuota> fallbacks
```

`@Valid` cho phép Bean Validation đi sâu vào các constraint của `RegionQuota`. Nếu quên cascade validation, có thể có những trường hợp cấu hình được bind nhưng một số ràng buộc của object lồng không được đánh giá như dự kiến.

Việc model hóa kiểu riêng có lợi khi các ràng buộc và ý nghĩa của vùng dữ liệu được dùng ở nhiều nơi.

## 19. Dùng converter với `@DefaultValue`

Một constructor-bound configuration properties có thể khai báo mặc định cho tham số:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("ap-southeast-1:4") RegionQuota primary,
        @DefaultValue("5s") Duration timeout
) {
}
```

Khi không có `app.worker.primary`, Spring Boot có thể áp dụng giá trị chuỗi của `@DefaultValue`, rồi **chuyển nó sang kiểu đích `RegionQuota`** bằng cơ chế conversion phù hợp. Giá trị mặc định cũng phải có cú pháp mà converter chấp nhận.

Nếu viết:

```java
@DefaultValue("invalid-default") RegionQuota primary
```

thì ngay cả khi người dùng không cấu hình gì, default có thể gây lỗi binding vì converter không nhận được `region:capacity`.

Không dùng default chỉ để che thiếu cấu hình bắt buộc trong môi trường production. Nếu một cluster buộc phải cấp `primary` rõ ràng, nên diễn đạt yêu cầu đó bằng cấu hình và validation phù hợp thay vì mặc định chọn một region ngoài ý muốn.

**Không phải mọi chuỗi đều cần converter tùy chỉnh.** Trong ví dụ, `@DefaultValue("5s")` cho `Duration` sử dụng converter sẵn có của Spring Boot.

## 20. Bộ sưu tập và đối tượng lồng: converter chạy ở mức phần tử

Một tệp YAML:

```yaml
app:
  worker:
    groups:
      primary: "ap-southeast-1:12"
      backup: "eu-west-1:6"
    fallbacks:
      - "us-east-1:4"
      - "eu-west-2:5"
```

Một model cấu hình tương ứng:

```java
@ConfigurationProperties(prefix = "app.worker")
public record GroupedWorkerProperties(
        Map<String, RegionQuota> groups,
        List<RegionQuota> fallbacks
) {
}
```

Binder có thể kết hợp việc liên kết cấu trúc `Map` / `List` với converter đã được đăng ký để tạo từng `RegionQuota` từ giá trị chuỗi.

**Đừng nhầm hai cấp:**

1. Binder biết cách tìm key `primary`, `backup`, và các phần tử danh sách.
2. Converter biết cách biến **một scalar chuỗi** thành **một `RegionQuota`**.

Converter không cần tự duyệt toàn bộ YAML hoặc xử lý `PropertySource`. Nếu muốn chuyển một chuỗi JSON thành cả danh sách `List<RegionQuota>`, đó là một yêu cầu định dạng **khác**, không phải việc mà `Converter<String, RegionQuota>` tự đảm nhiệm.

### Lưu ý về ưu tiên khi nhiều nguồn cấu hình

Nếu `application.yaml` có hai fallback nhưng profile `dev` cung cấp danh sách chỉ một fallback, Binder thường **thay thế danh sách** từ nguồn ưu tiên thấp bằng danh sách từ nguồn ưu tiên cao, không ghép tất cả phần tử lại. Converter vẫn xử lý phần tử của danh sách cuối được binding.

Với `Map`, quy tắc kết hợp có thể khác: các key con từ nhiều nguồn có thể đóng góp vào map theo quy tắc ưu tiên. Đây là **quy tắc binding collection**, không phải thay đổi của converter.

## 21. Tên thuộc tính và relaxed binding vẫn hoạt động bình thường

Khai báo:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(RegionQuota primary) {}
```

Key chuẩn:

```properties
app.worker.primary=ap-southeast-1:12
```

Biến môi trường tương ứng trên Unix:

```bash
export APP_WORKER_PRIMARY='eu-west-1:6'
java -jar app.jar
```

Trong PowerShell:

```powershell
$env:APP_WORKER_PRIMARY = 'eu-west-1:6'
java -jar .\app.jar
```

Spring Boot chọn giá trị có hiệu lực cho `app.worker.primary` từ các nguồn cấu hình theo thứ tự ưu tiên, rồi gọi converter để tạo `RegionQuota`.

Nếu một property có dấu gạch nối:

```text
app.worker.primary-region
```

tên biến môi trường dùng quy tắc relaxed binding là:

```text
APP_WORKER_PRIMARYREGION
```

Thay dấu chấm bằng `_`, bỏ dấu gạch nối, đổi chữ thành in hoa. **Converter không xử lý cách đặt tên khóa**; Binder xử lý việc này.

Một nhầm lẫn hay gặp là viết converter đúng nhưng khóa trong biến môi trường sai, khiến người phát triển kết luận converter không được gọi. Trước khi sửa mã converter, hãy xác nhận property cuối đã được nhận diện.

## 22. Viết unit test cho converter

Vì `RegionQuotaConverter` không có dependency, unit test không cần khởi động Spring context. Sử dụng JUnit 5:

`src/test/java/example/configconversion/RegionQuotaConverterTest.java`

```java
package example.configconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class RegionQuotaConverterTest {

    private final RegionQuotaConverter converter =
            new RegionQuotaConverter();

    @Test
    void convertsNormalValue() {
        RegionQuota result =
                converter.convert("ap-southeast-1:12");

        assertEquals("ap-southeast-1", result.region());
        assertEquals(12, result.capacity());
    }

    @Test
    void allowsSurroundingWhitespace() {
        RegionQuota result =
                converter.convert("  eu-west-1 : 6  ");

        assertEquals(new RegionQuota("eu-west-1", 6), result);
    }

    @Test
    void rejectsMissingSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1"));
    }

    @Test
    void rejectsNonNumericCapacity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1:many"));
    }

    @Test
    void rejectsMoreThanOneSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("us-east-1:2:extra"));
    }
}
```

Các test trên kiểm tra **phần parse thuần Java**. Chúng chưa chứng minh Spring Boot đã đăng ký converter thông qua `@ConfigurationPropertiesBinding`.

Nếu muốn test rằng `capacity=0` bị từ chối bởi Bean Validation, đó là **một loại test khác**: phải gọi Jakarta Validator trên object hoặc thử binding trong Spring context có validation được bật. Không nên kỳ vọng converter unit test tự từ chối mọi giá trị vi phạm constraint nếu converter cố ý chỉ kiểm tra cú pháp.

## 23. Kiểm thử tích hợp: Spring Boot có thực sự dùng converter không?

Để chứng minh một converter đã được gắn vào quá trình configuration binding, cần một test khởi tạo Spring context với nguồn cấu hình.

Một lựa chọn đơn giản là test Spring Boot:

`src/test/java/example/configconversion/ConverterBindingIntegrationTest.java`

```java
package example.configconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.worker.primary=eu-central-1:9",
        "app.worker.fallbacks[0]=us-east-1:3",
        "app.worker.timeout=2s"
})
class ConverterBindingIntegrationTest {

    @Autowired
    private WorkerProperties properties;

    @Test
    void usesRegisteredConverterDuringBinding() {
        assertEquals(
                new RegionQuota("eu-central-1", 9),
                properties.primary());

        assertEquals(
                new RegionQuota("us-east-1", 3),
                properties.fallbacks().get(0));

        assertEquals(1, properties.fallbacks().size());
    }
}
```

Để dùng `@SpringBootTest`, dự án cần `spring-boot-starter-test` trong test scope:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test này dựa trên ứng dụng demo và phạm vi component scanning ở các phần trước, gồm `BindingConvertersConfiguration`, `WorkerProperties` và `ConverterDemoApplication`.

Nó kiểm tra:

1. Context Spring Boot được tạo.
2. `WorkerProperties` được đăng ký.
3. Converter bean được tìm thấy.
4. Binder chuyển chuỗi của `primary` và phần tử `fallbacks` thành `RegionQuota`.
5. Kết quả có giá trị đúng như kỳ vọng.

Nếu unit test converter qua nhưng test này lỗi, nguyên nhân có thể nằm ở **đăng ký bean, package scanning, qualifier hoặc cấu hình Spring**, không phải thuật toán `split` trong converter.

### Test giá trị sai trong integration

Có thể bổ sung test khởi động context với:

```properties
app.worker.primary=eu-west-1:abc
```

và xác nhận context khởi động thất bại theo cách kiểm thử phù hợp, chẳng hạn `ApplicationContextRunner` với cấu hình bean/validation đã đăng ký đúng.

Lưu ý một test dùng `@SpringBootTest` với cấu hình cố ý sai có thể làm toàn bộ test context thất bại trước khi phương thức `@Test` chạy. Nếu muốn khẳng định và phân tích lỗi startup ngay trong test, nên dùng một context runner có thể quan sát `getStartupFailure()` thay vì kỳ vọng method JUnit bình thường sẽ được gọi.

## 24. Những lỗi thường gặp khi đăng ký custom converter

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Binder không biết chuyển `String` sang `RegionQuota` | Converter không được đăng ký | Kiểm tra `@Bean`, qualifier và phạm vi scan |
| Import `ConfigurationPropertiesBinding` báo lỗi | Import sai package | Dùng `org.springframework.boot.context.properties.ConfigurationPropertiesBinding` |
| Chỉ viết class `implements Converter` nhưng không có tác dụng | Class không thành bean cấu hình | Dùng `@Bean @ConfigurationPropertiesBinding` hoặc đăng ký phù hợp |
| Warning “not eligible for getting processed…” | Converter bean bị yêu cầu quá sớm, `@Bean` không static hoặc phụ thuộc tạo sớm | Ưu tiên `static @Bean` và giới hạn dependency |
| Cấu hình có giá trị nhưng converter không chạy | Kiểu đích khác, nguồn ưu tiên khác hoặc kiểu đã được chuyển bằng cách khác | Xem trường `@ConfigurationProperties` và giá trị cuối |
| Converter làm hỏng nhiều module | Converter đăng ký cho cặp kiểu quá phổ biến, ví dụ `String -> String` | Dùng kiểu miền riêng để giới hạn ảnh hưởng |
| `capacity=0` vẫn convert được | Converter chỉ parse số | Dùng Bean Validation cho quy tắc >= 1 |
| Chuỗi `host:port` nhiều dấu `:` gây lỗi | Định dạng phân tách không hỗ trợ IPv6/URI | Dùng định dạng rõ ràng hoặc kiểu chuẩn thay vì split đơn giản |
| Đổi YAML mà bean vẫn nhận giá trị cũ | Nguồn cấu hình khác ưu tiên cao hơn, JAR chưa rebuild hoặc process chưa restart | Kiểm tra môi trường chạy và PropertySource |
| `@Value` không dùng converter như dự kiến | Khác cơ chế tra cứu/tiêm giá trị với Binder | Kiểm tra API đang dùng và đăng ký conversion đúng phạm vi |
| `@ConfigurationProperties` không được tạo bean | Thiếu scan hoặc enable | Dùng `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` |
| Converter gọi repository và gây lỗi khởi động | Dependency chưa sẵn sàng hoặc vòng khởi tạo | Làm converter thuần parse, chuyển kiểm tra ngoại vi sang bước khác |
| List không được ghép qua các profile | Quy tắc binding danh sách thay thế thay vì append | Khai báo danh sách đầy đủ trong nguồn ưu tiên cao |
| Thiếu key dẫn tới `null` mà không có lỗi | Không có constraint/mandatory policy | Thêm `@NotNull`, default hoặc kiểm tra phù hợp |

### Đừng sửa lỗi bằng cách bỏ qua invalid fields

`@ConfigurationProperties` có tùy chọn như `ignoreInvalidFields`, nhưng nếu chuỗi domain cấu hình sai định dạng, việc lờ đi lỗi có thể khiến ứng dụng chạy thiếu thông tin cần thiết. Nếu `RegionQuota` là bắt buộc, thường nên để lỗi binding bộc lộ sớm và giải thích cách nhập đúng.

Không tạo một giá trị giả như `new RegionQuota("unknown", 0)` chỉ để tránh ném exception nếu nghiệp vụ không cho phép; cách đó chuyển lỗi nhập liệu thành trạng thái runtime khó chẩn đoán.

## 25. Khi nào không nên dùng `Converter<String, T>`?

Có một số tình huống mà converter tùy chỉnh không phải lựa chọn tốt nhất.

### 25.1. Dữ liệu vốn đã có cấu trúc

Thay vì chuỗi:

```yaml
app:
  worker:
    primary: "ap-southeast-1:12"
```

có thể dùng:

```yaml
app:
  worker:
    primary:
      region: ap-southeast-1
      capacity: 12
```

và model:

```java
public record WorkerProperties(RegionQuota primary) {}
```

với prefix thích hợp trên `WorkerProperties`. Binder có thể liên kết các trường con mà không cần parse một chuỗi tổng hợp. Dạng này cũng có thể rõ ràng hơn khi cần đặt từng khóa từ biến môi trường.

### 25.2. Kiểu dữ liệu có sẵn converter của Spring Boot

Ví dụ:

```properties
app.worker.timeout=5s
app.worker.max-batch-size=10MB
```

Nên dùng `Duration`, `DataSize` với chuyển đổi chuẩn, không tự định nghĩa lại cú pháp tùy ý nếu không có yêu cầu rõ.

### 25.3. Dữ liệu phụ thuộc vào dịch vụ bên ngoài

Nếu chỉ muốn kiểm tra region có nằm trong danh sách hiện tại của nhà cung cấp cloud, converter không phải nơi tốt để gọi API từ xa. Chọn tên region theo quy tắc chuỗi rồi thực hiện kiểm tra nghiệp vụ ở tầng phù hợp.

### 25.4. Cần parse cấu trúc lớn, nhiều cấp

Nếu giá trị là JSON lồng nhau, danh sách dài hoặc nhiều loại phần tử, hãy cân nhắc YAML/properties có cấu trúc, kiểu Java phù hợp và Binder. Tự ép mọi thứ thành một scalar rồi viết converter lớn sẽ làm schema khó hiểu.

### 25.5. Cần chuyển đổi dùng ở nhiều tầng ứng dụng

Nếu cùng phép chuyển đổi cần dùng ở MVC request parameter, messaging và cấu hình, có thể tách **hàm parse thuần** ra khỏi lớp converter. Mỗi tầng đăng ký adapter chuyển đổi thích hợp, tránh mặc định qualifier dành cho cấu hình sẽ được mọi cơ chế khác tự sử dụng.

## 26. Cải thiện thiết kế converter cho dự án lớn

Một converter tốt thường có các đặc điểm:

- **Deterministic:** cùng input cho cùng output hoặc cùng kiểu lỗi.
- **Side-effect free:** không ghi file, gọi network hoặc sửa state của ứng dụng.
- **Thread-safe:** không giữ state mutable chung không cần thiết.
- **Không phụ thuộc thời gian hoặc môi trường** trừ khi đó là yêu cầu được thiết kế rõ.
- **Lỗi có thông tin:** chỉ rõ cấu trúc đầu vào mong đợi mà không tiết lộ bí mật.
- **Tách parser và validation:** nhận diện định dạng khác với kiểm tra chính sách nghiệp vụ.
- **Nhất quán:** định nghĩa rõ whitespace, chữ hoa/thường, encoding và dấu phân cách.
- **Có test tốt:** đúng, sai định dạng, thiếu phần, số quá lớn, số âm, giá trị rỗng.
- **Có kiểu đích cụ thể:** tránh converter quá rộng gây tác động ngoài dự kiến.
- **Dễ di chuyển giữa YAML/properties/env:** không gắn logic converter vào một định dạng nguồn cụ thể.

Với mã nguồn lớn, có thể tách parser thuần:

```java
public final class RegionQuotaParser {

    private RegionQuotaParser() {
    }

    public static RegionQuota parse(String raw) {
        // Thực hiện kiểm tra cú pháp và chuyển đổi ở đây.
        return ...;
    }
}
```

Sau đó `RegionQuotaConverter.convert(...)` chỉ gọi `RegionQuotaParser.parse(source)`. Đây là mẫu tổ chức **minh họa**; không tạo một parser thứ hai nếu converter hiện tại đã nhỏ và đủ dễ đọc.

Tách parser ra giúp các công cụ CLI hoặc quy trình nhập dữ liệu khác tái sử dụng mà không phải phụ thuộc trực tiếp vào Spring context.

## 27. Một ví dụ domain khác: phân tích mã màu thương hiệu

Giả sử ứng dụng nhận:

```properties
app.ui.accent-color=#1A73E8
```

Bạn có một kiểu riêng:

```java
public record RgbColor(int red, int green, int blue) {}
```

Converter có thể nhận `String` dạng `#RRGGBB`, kiểm tra đúng sáu ký tự hex, rồi tạo ba thành phần `red`, `green`, `blue`.

Ví dụ ý tưởng:

```java
public final class RgbColorConverter
        implements Converter<String, RgbColor> {

    @Override
    public RgbColor convert(String source) {
        if (!source.matches("#[0-9A-Fa-f]{6}")) {
            throw new IllegalArgumentException(
                    "Expected color in #RRGGBB format");
        }

        int value = Integer.parseInt(source.substring(1), 16);
        return new RgbColor(
                (value >> 16) & 0xff,
                (value >> 8) & 0xff,
                value & 0xff);
    }
}
```

Đây là một trường hợp phù hợp vì `"#{hex}"` có **cú pháp scalar rõ ràng**, kiểu đích biểu diễn **một đối tượng có ý nghĩa riêng**, và việc parse thuần không cần dịch vụ ngoài.

Đăng ký:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RgbColor> rgbColorConverter() {
    return new RgbColorConverter();
}
```

Nếu `RgbColor` được dùng trong `@ConfigurationProperties`, Spring Boot có thể liên kết chuỗi `#1A73E8` vào giá trị có kiểu.

Lưu ý khi nhập trực tiếp vào shell, ký tự `#` có thể mang ý nghĩa chú thích trong ngữ cảnh nhất định; nên dùng dấu nháy bao giá trị theo shell. Việc quote ở terminal xảy ra **trước** converter và không thay đổi thuật toán đọc màu.

## 28. Bài tập tự kiểm tra

### Bài 1 — biết khi nào cần converter

Cho ba khóa:

```properties
app.timeout=5s
app.max-size=10MB
app.region-quota=ap-southeast-1:12
```

Kiểu đích tương ứng là `Duration`, `DataSize` và `RegionQuota`.

**Hỏi:** Giá trị nào có thể cần converter riêng?

**Đáp án:** `app.region-quota`. `Duration` và `DataSize` đã có hỗ trợ chuyển đổi chuẩn trong Spring Boot 3.3; `RegionQuota` là kiểu miền do ứng dụng tự định nghĩa với cú pháp riêng.

### Bài 2 — import annotation chính xác

Hai package:

```java
org.springframework.boot.context.properties.ConfigurationPropertiesBinding
```

```java
org.springframework.boot.context.properties.bind.ConfigurationPropertiesBinding
```

**Hỏi:** Import nào đúng?

**Đáp án:** Package đầu tiên, thuộc `org.springframework.boot.context.properties`.

### Bài 3 — cấu hình có nhiều constructor

Một record `WorkerProperties` dùng `RegionQuota primary`. Converter có phải được đặt `@ConstructorBinding` không?

**Đáp án:** Không. `@ConstructorBinding` liên quan cách Binder chọn constructor cho model cấu hình khi cần, còn converter được đăng ký là bean nhờ `@ConfigurationPropertiesBinding`.

### Bài 4 — static `@Bean`

Bạn viết:

```java
@Bean
@ConfigurationPropertiesBinding
Converter<String, RegionQuota> converter() {
    return new RegionQuotaConverter();
}
```

**Hỏi:** Vì sao Spring Boot khuyến nghị thêm `static`?

**Đáp án:** Converter binding có thể được yêu cầu rất sớm. Phương thức `static` giảm việc khởi tạo sớm lớp configuration và tránh những cảnh báo về BeanPostProcessor theo tài liệu Spring Boot.

### Bài 5 — phân biệt parse và validation

```properties
app.worker.primary=eu-west-1:0
```

Converter tạo `RegionQuota("eu-west-1", 0)`, model dùng `@Min(1)`.

**Hỏi:** Chuyển đổi có thành công không, validation có đạt không?

**Đáp án:** Chuyển đổi cú pháp và kiểu có thể thành công; validation không đạt do capacity bằng 0.

### Bài 6 — key từ nguồn khác

YAML khai báo `primary=ap-southeast-1:12`, nhưng lệnh chạy truyền:

```bash
java -jar app.jar --app.worker.primary=us-east-1:4
```

**Hỏi:** Converter nhận chuỗi nào trong trường hợp thông thường?

**Đáp án:** Chuỗi từ nguồn có ưu tiên cao hơn (`us-east-1:4`) được Binder sử dụng; converter không tự chọn nguồn.

### Bài 7 — kết hợp danh sách

YAML:

```yaml
app:
  worker:
    fallbacks:
      - "eu-west-1:6"
      - "us-east-1:4"
```

Kiểu Java:

```java
List<RegionQuota> fallbacks
```

**Hỏi:** Converter nhận đầu vào nào?

**Đáp án:** Converter có thể được sử dụng cho **từng phần tử scalar** để tạo từng `RegionQuota`; Binder chịu trách nhiệm tạo cấu trúc danh sách.

### Bài 8 — lỗi `NumberFormatException`

```properties
app.worker.primary=eu-west-1:large
```

**Hỏi:** Nên xử lý ra sao?

**Đáp án:** Báo rõ định dạng số không hợp lệ, giữ nguyên nguyên nhân ngoại lệ nếu hữu ích; không âm thầm trả về capacity mặc định để che lỗi cấu hình.

### Bài 9 — dependency ngoài

Một converter cần lấy vùng mặc định từ database. Có nên inject repository vào converter binding để gọi DB trong `convert()` không?

**Đáp án:** Tránh làm như vậy nếu có thể, vì converter được yêu cầu trong giai đoạn khởi tạo rất sớm và có thể tạo vòng phụ thuộc/khởi động bất ổn. Chọn quy tắc parse thuần rồi xác thực nghiệp vụ ở tầng phù hợp.

### Bài 10 — kiểm thử

Unit test `new RegionQuotaConverter().convert(...)` thành công. Có đủ chứng minh Spring Boot sẽ bind `WorkerProperties.primary` không?

**Đáp án:** Chưa. Unit test chỉ kiểm tra thuật toán parse. Cần một kiểm thử Spring context chứng minh bean converter có qualifier được đăng ký và Binder sử dụng nó.

## 29. Checklist áp dụng trong dự án thật

Trước khi thêm một converter cấu hình, có thể tự hỏi:

- [ ] Kiểu đích có thật sự là domain type riêng, hay đã được Spring Boot hỗ trợ?
- [ ] Có thể biểu diễn cấu hình bằng các trường nested thay cho scalar tự chế không?
- [ ] Đã ghi rõ cú pháp đầu vào (delimiter, whitespace, casing, range) chưa?
- [ ] `Converter<S,T>` có cặp generic type cụ thể và phù hợp không?
- [ ] Lỗi parse có rõ ràng mà không làm lộ bí mật không?
- [ ] Converter có thuần dữ liệu, tránh network, database và trạng thái mutable không?
- [ ] Đã đăng ký converter như bean cho configuration properties chưa?
- [ ] Khi dùng `@Bean`, đã dùng `@ConfigurationPropertiesBinding` và cân nhắc phương thức `static` chưa?
- [ ] `@ConfigurationProperties` có đúng prefix và được scan/enable chưa?
- [ ] Model có kiểm tra các ràng buộc nghiệp vụ riêng với conversion chưa?
- [ ] Các nested object và phần tử list có validation cascade thích hợp chưa?
- [ ] Unit test có giá trị đúng, sai cú pháp, số ngoài phạm vi và phần tử rỗng chưa?
- [ ] Integration test có chứng minh Spring Boot dùng converter khi binding chưa?
- [ ] Đã kiểm tra tên biến môi trường và thứ tự ưu tiên nguồn chưa?
- [ ] Cấu hình đã lưu không chứa bí mật bị in ra log khi converter thất bại chứ?

Checklist trên giúp giữ cho converter là một **đơn vị chuyển đổi rõ ràng**, thay vì biến nó thành nơi tập trung các xử lý khởi động không liên quan.

## 30. Tổng kết

`@ConfigurationPropertiesBinding` là một công cụ quan trọng khi Spring Boot Binder phải chuyển giá trị cấu hình sang **kiểu Java do ứng dụng tự định nghĩa**.

Quy trình chuẩn:

```text
1. Định nghĩa kiểu miền T
          |
          v
2. Viết Converter<String, T>
          |
          v
3. Đăng ký bean:
   @Bean
   @ConfigurationPropertiesBinding
   static Converter<String, T> ...
          |
          v
4. Khai báo T trong @ConfigurationProperties
          |
          v
5. Đăng ký configuration properties bằng scan/enable
          |
          v
6. Binder áp dụng converter khi cần
          |
          v
7. Bean Validation kiểm tra các quy tắc nghiệp vụ
          |
          v
8. Service sử dụng cấu hình đã có kiểu
```

Các điểm cốt lõi:

1. **Đừng viết converter khi Spring Boot đã hỗ trợ kiểu đó**, như `Duration` hoặc `DataSize`.
2. **`Converter<String, T>` giải quyết định dạng của một giá trị**, không thay thế hệ thống `PropertySource` hay Binder.
3. **`@ConfigurationPropertiesBinding` đánh dấu bean converter dành cho configuration properties binding**; nó không khai báo prefix.
4. **Dùng `@Bean static` khi đăng ký converter theo Java configuration** để giảm rủi ro liên quan vòng đời khởi tạo sớm.
5. **Converter nên đơn giản và ít dependency**; không nên gọi mạng/DB trong bước parse.
6. **Tách chuyển đổi kiểu khỏi validation nghiệp vụ**; `"region:0"` có thể parse được nhưng vẫn không hợp lệ.
7. **Kiểm thử cả parser lẫn đường đi binding thực tế** để biết thuật toán đúng và converter đã được Spring Boot sử dụng.

Khi hiểu đúng ranh giới giữa Converter, Binder và Validation, bạn có thể mở rộng khả năng cấu hình của Spring Boot 3.3 mà vẫn giữ mã Java có kiểu, dễ kiểm thử, ít phụ thuộc và đáng tin cậy khi triển khai.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, mục **Properties Conversion**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigurationPropertiesBinding`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html
- Spring Boot 3.3 Reference — `@ConfigurationProperties` Validation và Type-safe Configuration Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Type Conversion (`Converter`, `ConversionService`): https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Boot 3.3 Reference — Testing (`@SpringBootTest`, ApplicationContextRunner): https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
