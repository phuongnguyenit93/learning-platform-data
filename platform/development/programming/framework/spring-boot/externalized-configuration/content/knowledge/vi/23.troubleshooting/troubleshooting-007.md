# Phân tích lỗi placeholder, chuyển đổi kiểu và ConfigurationPropertiesBindException trong Spring Boot 3.3

## 1. Mục tiêu bài học

Khi Spring Boot không khởi động vì một property, log thường có nhiều lớp exception lồng nhau. Dòng ngoài cùng có thể chỉ là `BeanCreationException`; bên trong lại có `ConfigurationPropertiesBindException`, `BindException`, `ConversionFailedException` hoặc một lỗi xác thực. Đôi khi chỉ xuất hiện thông báo kiểu `Could not resolve placeholder '...' in value "${...}"`. Nếu chỉ đọc dòng cuối hoặc chỉ nhìn tên exception đầu tiên, người xử lý rất dễ sửa nhầm file, nhầm giá trị hoặc che lỗi bằng default.

Bài này tập trung vào ba nhóm:

1. **Lỗi placeholder:** một biểu thức `${name}` không tìm được property phù hợp, tạo vòng tham chiếu, có default sai hoặc dùng tên không canonical.
2. **Lỗi chuyển đổi kiểu:** giá trị đã được tìm thấy nhưng không thể chuyển sang `int`, `Duration`, `DataSize`, enum, collection hoặc Java type đích.
3. **Lỗi binding bean:** Spring Boot không thể hoàn tất binding/validation của `@ConfigurationProperties` bean và có thể ném `ConfigurationPropertiesBindException` ở lớp bao ngoài.

**Mục tiêu thực hành:** nhìn log và xác định được **property nào lỗi**, **nguồn giá trị nào đang có hiệu lực**, **kiểu Java nào được yêu cầu**, **giai đoạn nào thất bại**, **điều kiện sửa phù hợp**, đồng thời tránh in secret trong log.

Phạm vi là Spring Boot **3.3** và các Spring Framework APIs tương ứng; tên exception, message và cách bọc có thể thay đổi tùy đường chạy, kiểu bean, patch version, IDE và cấu hình logging. Các log minh họa trong bài diễn giải cấu trúc thường gặp, không phải cam kết nội dung byte-for-byte cho mọi lần chạy.

## 2. Bức tranh từ Config Data đến bean

Hãy xem luồng thông thường:

```text
application.properties / application.yaml
profile-specific files / config imports
OS environment / JVM -D / CLI
                |
                v
      Environment + PropertySources
                |
                v
      Chọn property có hiệu lực
                |
                v
        Placeholder resolution
      ${app.host}, ${app.port:8080}
                |
                v
      Binder / ConversionService
  String -> Integer / Boolean / Duration
         DataSize / enum / object
                |
                v
           Bean Validation
       @Min / @NotBlank / @Valid
                |
                v
       @ConfigurationProperties bean
                |
                v
      Dịch vụ khác inject và dùng
```

Đây là sơ đồ khái quát. `@Value`, `Environment.getProperty`, `@ConfigurationProperties` và Binder trực tiếp có điểm giao nhau nhưng **không đi qua cùng một đường callback và exception wrapping** ở mọi tình huống.

Một lỗi có thể xảy ra ở nhiều tầng:

| Tầng | Ví dụ | Triệu chứng thường gặp |
| --- | --- | --- |
| Nạp Config Data | YAML sai cú pháp, import location thiếu | Config Data/YAML parsing exception |
| Chọn nguồn | Env ghi đè file bằng value sai | Property hiệu lực khác file người dùng đang xem |
| Placeholder | `${service.host}` không giải được | `Could not resolve placeholder` hoặc placeholder còn nguyên ở đường bind nhất định |
| Conversion | `server.port=abc` cho `Integer` | Conversion/number format failure |
| Bean binding | `app.port=abc` cho một `@ConfigurationProperties` bean | `ConfigurationPropertiesBindException` / `BindException` |
| Validation | `app.threads=0` nhưng `@Min(1)` | Bean validation/bind validation error |
| Bean lifecycle | Setter/constructor ném exception | Bean creation failure, nguyên nhân là code người dùng |
| Runtime downstream | Bind thành công nhưng timeout 10ms thay vì 10s | Không nhất thiết có startup exception |

**Quan trọng:** không phải cứ có `ConfigurationPropertiesBindException` là do placeholder. Không phải cứ thấy `BeanCreationException` là do bean registration. Hãy đi vào chuỗi `Caused by` và phân tích **nguyên nhân gốc**.

## 3. Bộ ví dụ thống nhất

Giả sử ứng dụng có các file sau:

```text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/config/AppProperties.java
src/main/resources/application.yaml
pom.xml
```

Model cấu hình JavaBean:

```java
package com.example.demo.config;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @NotBlank
    private String serviceName = "catalog";

    @Min(1)
    @Max(64)
    private int workerCount = 4;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    private boolean featureEnabled;

    public String getServiceName() { return serviceName; }
    public void setServiceName(String value) { serviceName = value; }

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int value) { workerCount = value; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration value) {
        connectTimeout = value;
    }

    public boolean isFeatureEnabled() { return featureEnabled; }
    public void setFeatureEnabled(boolean value) {
        featureEnabled = value;
    }
}
```

Ứng dụng:

```java
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
```

Config hợp lệ:

```yaml
app:
  service-name: catalog
  worker-count: 4
  connect-timeout: 5s
  feature-enabled: false
```

Để chạy Bean Validation, ứng dụng cần provider tương thích, thường qua:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Nếu provider không có hoặc cấu hình validation không áp dụng, những constraint như `@Min`/`@NotBlank` có thể **không được thực thi như mong đợi**. Đó là lỗi thiết lập hạ tầng, không phải lỗi Binder bỏ qua cú pháp số.

## 4. Đọc một chuỗi exception đúng cách

Một log minh họa khi `app.worker-count` được đặt thành `abc`:

```text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'app.worker-count' to int:

    Property: app.worker-count
    Value: "abc"
    Origin: class path resource [application.yaml] - 4:17
    Reason: failed to convert java.lang.String to int

Action:
Update your application's configuration
```

Có thể thấy ở stack trace một chuỗi tương tự:

```text
BeanCreationException
  caused by ConfigurationPropertiesBindException
    caused by BindException
      caused by ConversionFailedException
        caused by IllegalArgumentException
          caused by NumberFormatException
```

Đây là **sơ đồ minh họa**, không bảo đảm cả sáu lớp luôn xuất hiện hoặc đúng thứ tự trong mọi build. Ví dụ với `@Value` đơn lẻ có thể không đi qua `ConfigurationPropertiesBindException`; với Bean Validation, nguyên nhân sâu có thể là `BindValidationException` chứ không phải `NumberFormatException`.

Khi phân tích, ưu tiên đọc:

1. **Loại lỗi gần nhất với dữ liệu** ở phần cuối `Caused by`.
2. **Tên property và prefix** ứng dụng cố bind.
3. **Value** gây lỗi nếu log hiển thị an toàn.
4. **Origin** để biết file, vị trí hoặc nguồn môi trường.
5. **Target type** mà code Java yêu cầu.
6. **Validation message** nếu value chuyển kiểu được nhưng vi phạm constraint.
7. **Action** do FailureAnalyzer gợi ý, rồi xác minh nó khớp nguyên nhân thật.

Không chỉ sửa một file có tên giống property khi log chỉ rõ nguồn giá trị đang đến từ OS environment hoặc CLI.

## 5. Placeholder syntax và cách Spring giải quyết

Spring Boot hỗ trợ placeholder trong giá trị cấu hình qua cú pháp:

```properties
app.base-url=https://api.example.test
app.endpoint=${app.base-url}/v1
```

Khi sử dụng `app.endpoint` qua Environment/Binding thích hợp, giá trị mong đợi là:

```text
https://api.example.test/v1
```

Cú pháp:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `${key}` | Tham chiếu value của một property |
| `${key:default}` | Dùng default nếu property không được giải quyết |
| `${app.host}` | Tham chiếu tên canonical nhiều segment |
| `${app.port:8080}` | Port mặc định 8080 nếu thiếu nguồn |
| `https://${app.host:localhost}:${app.port:8080}/v1` | Ghép nhiều placeholder trong một chuỗi |

**Default sau dấu hai chấm không phải một giá trị có thể vượt mọi nguồn ưu tiên.** Nó chỉ là fallback khi quá trình resolve không tìm được property phù hợp theo semantics của resolver. Nếu key tồn tại với giá trị rỗng, đừng tự cho rằng default sẽ được áp dụng.

### 5.1. Placeholder trong application.yaml

```yaml
app:
  host: "api.internal"
  port: 8443
  endpoint: "https://${app.host}:${app.port}/v1"
```

Dấu nháy giúp YAML lưu giá trị chứa ký tự `:` hoặc `${...}` thành text rõ ràng. Spring Boot sử dụng Environment để giải quyết những placeholder **khi giá trị được tiêu thụ**, không phải bằng một phép biến đổi toàn bộ cấu hình ngay lúc parser đọc file.

### 5.2. Placeholder tham chiếu nguồn cao hơn

File:

```properties
app.host=localhost
app.endpoint=https://${app.host}:8443
```

Env:

```bash
APP_HOST=api.production.internal
```

Nếu không có source cao hơn cho `app.endpoint`, khi nó được giải quyết qua Environment thích hợp, placeholder `${app.host}` có thể lấy `api.production.internal` từ OS environment. Chỉnh `app.host` trong file thấp hơn có thể không đổi endpoint nếu env vẫn override host.

**Hãy xác định mọi tham chiếu trong chuỗi**, không chỉ tìm property `app.endpoint`.

## 6. Lỗi placeholder không tồn tại

### 6.1. Trường hợp @Value

```java
@Component
public class ClientInfo {

    @Value("${client.api-url}")
    private String apiUrl;
}
```

Nếu không có nguồn nào cung cấp `client.api-url`, quá trình inject placeholder bắt buộc có thể thất bại. Thông báo thường gặp:

```text
Could not resolve placeholder 'client.api-url'
in value "${client.api-url}"
```

Lỗi này có thể được bọc trong `BeanCreationException` hoặc lỗi bean injection khác. Không nhất thiết có `ConfigurationPropertiesBindException` vì đây là đường `@Value`.

Các câu hỏi cần trả lời:

- Tên key có đúng canonical không?
- File đang chứa property đó có thực sự được nạp không?
- Active profile có khớp không?
- Tên environment variable có đúng không?
- Property có bị đặt trong YAML path khác vì indentation không?
- Code có đang chạy trước khi một source tùy chỉnh được thêm không?

### 6.2. Khi có default

```java
@Value("${client.api-url:https://localhost:8443}")
private String apiUrl;
```

Khi không tìm thấy key, default được sử dụng. Đây có thể hữu ích cho thông số optional ở local development.

**Nhưng không phải property nào cũng nên có default:** mật khẩu, API key, địa chỉ production bắt buộc hoặc namespace có điều kiện an toàn thường cần fail-fast. Dùng một URL mặc định ở production có thể làm ứng dụng kết nối nhầm hệ thống.

### 6.3. Missing và empty khác nhau

File:

```properties
client.api-url=
```

Khi key có mặt nhưng value rỗng, placeholder `${client.api-url:...}` thường không tự dùng default chỉ vì String rỗng. Nếu ứng dụng yêu cầu URL không trống, cần `@NotBlank` hoặc kiểm tra nghiệp vụ thích hợp. Nếu target là `URI`, việc chuyển kiểu/validation cũng cần được xem xét.

### 6.4. Placeholder trong @ConfigurationProperties có thể có biểu hiện khác

Ví dụ:

```properties
app.connect-timeout=${DEPLOY_TIMEOUT}
```

Nếu `DEPLOY_TIMEOUT` thiếu, kết quả phụ thuộc cách placeholder resolver, target type và BindHandler của đường binding đó xử lý unresolved value. Có thể thấy thông báo unresolved placeholder hoặc lỗi chuyển `String` chứa placeholder sang `Duration`.

**Không suy luận tất cả lỗi `${...}` đều phát ra chính xác `Could not resolve placeholder`.** Hãy đọc stack trace và target type, đặc biệt khi dùng Binder hoặc custom PlaceholdersResolver.

## 7. Tên canonical trong placeholder quan trọng

Spring Boot khuyến nghị tham chiếu property qua placeholder **dạng lowercase kebab-case**.

Đúng:

```properties
app.display-name=Catalog
app.greeting=Hello, ${app.display-name}
```

Nên tránh:

```properties
app.greeting=Hello, ${app.displayName}
```

Với `${app.display-name}`, Spring Boot có thể xét cả dạng `app.displayName` và OS environment `APP_DISPLAYNAME` theo quy tắc relaxed name phù hợp. Dùng camelCase trong placeholder có thể không xét những biến thể tên mà bạn kỳ vọng.

### 7.1. Chuyển property name sang OS env

Với một property canonical:

```text
app.connect-timeout
```

Tên environment variable chuẩn:

```text
APP_CONNECTTIMEOUT
```

Quy tắc:

1. Thay `.` bằng `_`.
2. **Bỏ** `-`, không thay thành `_`.
3. Viết hoa.

`APP_CONNECT_TIMEOUT` có thể được diễn giải thành property phân cấp khác và không nên mặc định nó tương đương `app.connect-timeout`.

### 7.2. Một ví dụ lỗi giả do env đặt sai tên

File:

```properties
app.url=https://${app.backend-host}
app.backend-host=localhost
```

Người vận hành đặt:

```text
APP_BACKEND_HOST=api.example.test
```

Có thể không ghi đè đúng `app.backend-host` như mong muốn. Giá trị cần kiểm tra theo convention là:

```text
APP_BACKENDHOST=api.example.test
```

Nếu URL vẫn trỏ localhost, đó có thể là vấn đề **mapping env name**, không phải placeholder resolver.

## 8. Lỗi placeholder tạo vòng tham chiếu

Tình huống tự tham chiếu:

```properties
app.host=${app.host}
```

Hoặc vòng giữa hai key:

```properties
app.host=${app.endpoint-host}
app.endpoint-host=${app.host}
```

Khi resolver truy giá trị, nó có thể phát hiện vòng tham chiếu và ném exception về **circular placeholder reference**. Thông điệp, lớp exception và thời điểm phát hiện tùy resolver và đường tiêu thụ.

### Chẩn đoán vòng tham chiếu

Lập sơ đồ:

```text
app.host
   |
   v
app.endpoint-host
   |
   v
app.host  <-- vòng lặp
```

Cách sửa là **phá vòng** và chọn một nguồn làm giá trị gốc:

```properties
app.host=api.example.test
app.endpoint-host=${app.host}
```

Không thêm default một cách mù quáng vào cả hai key để “ẩn” vòng tham chiếu. Default thường chỉ áp dụng khi key không resolve được, không phải để sửa cấu trúc tham chiếu vòng vốn đã tồn tại.

### Tự tham chiếu để override giá trị cũ

Một cấu hình dễ gây nhầm:

```properties
app.url=${app.url}/v2
```

Ý định có thể là lấy value của nguồn thấp hơn rồi thêm `/v2`. Nhưng một placeholder tham chiếu cùng tên property có thể giải ngược về chính value đang được chọn và tạo vòng. **Đừng dùng cú pháp này như cơ chế “lấy value trước khi override”.** Hãy dùng tên property khác cho base URL, hoặc quy ước transformation trong code.

## 9. Lỗi cú pháp và lồng placeholder

Một chuỗi như:

```properties
app.base=https://api.example.test
app.url=${app.base/v1
```

thiếu dấu `}`. Đường xử lý có thể giữ nguyên text hoặc không giải quyết như dự định. Với target String, điều này dễ bị bỏ sót cho tới khi request được gửi đến URL sai; với target `URI`, lỗi có thể xuất hiện trong conversion.

Nên viết:

```properties
app.url=${app.base}/v1
```

### 9.1. Default chứa dấu hai chấm

Ví dụ:

```properties
app.callback=${app.callback-url:https://localhost:9443/v1}
```

Dấu `:` đầu tiên sau tên key phân tách default; những dấu `:` khác nằm trong default có thể được giữ theo semantics của resolver. Tuy nhiên, việc lồng nhiều placeholder phức tạp và các escape sequences khác nhau có thể khó đọc. Nên kiểm tra trực tiếp bằng một test cấu hình và tránh dùng placeholder làm ngôn ngữ biểu thức tùy ý.

### 9.2. Không nhầm cú pháp Spring với Docker Compose hoặc shell

Trong `compose.yaml`:

```yaml
environment:
  APP_HOST: "${APP_HOST:-localhost}"
```

đây là **cú pháp interpolation của Docker Compose**, không phải Spring placeholder. Compose xử lý trước khi container được tạo.

Trong `application.properties`:

```properties
app.host=${APP_HOST:localhost}
```

đây là **placeholder do Spring xử lý** khi value được tiêu thụ. Hai cơ chế có cùng ký hiệu `${...}` nhưng quy tắc default, escaping, thời điểm xử lý và nguồn giá trị khác nhau.

Khi một giá trị đi qua YAML Compose rồi file ứng dụng rồi Spring, hãy xác định **tầng nào diễn giải placeholder trước**. Đừng lặp escaping theo trực giác mà không có test.

## 10. SpEL và placeholder là hai cơ chế khác

Spring hỗ trợ biểu thức SpEL trong `@Value`, ví dụ:

```java
@Value("#{2 * 3}")
private int computed;
```

Đây là một biểu thức trong annotation Java. Nó khác với:

```java
@Value("${app.worker-count:4}")
private int workerCount;
```

Cú pháp thứ hai tìm property và default nếu thiếu.

Trong `application.properties`:

```properties
app.count=#{2 * 3}
```

SpEL **không được tự đánh giá khi parser nạp file vào Environment**. Spring Boot nêu rằng SpEL không được xử lý lúc đọc file và đưa giá trị vào Environment, mặc dù `@Value` có thể đánh giá SpEL khi nó tiêu thụ value. Không kỳ vọng `@ConfigurationProperties` tự đánh giá một biểu thức SpEL như `@Value`.

**Quy tắc thực tế:** dùng `@ConfigurationProperties` cho cấu hình kiểu dữ liệu, dùng placeholder cho việc tham chiếu property, và chỉ dùng SpEL trong những bối cảnh thực sự cần expression semantics.

## 11. Conversion failure: value có nhưng target type không nhận

Giả sử model:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount = 4;

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int workerCount) {
        this.workerCount = workerCount;
    }
}
```

File:

```properties
app.worker-count=three
```

Binder đọc được String `three` nhưng không thể convert sang `int` bằng converter thông thường. Đây là **lỗi chuyển kiểu**, không phải thiếu placeholder hay thiếu bean.

Một failure analysis có thể chỉ ra:

```text
Failed to bind properties under 'app.worker-count' to int

Property: app.worker-count
Value: "three"
Origin: class path resource [application.properties] - ...
Reason: failed to convert java.lang.String to int
```

Nguyên nhân sâu thường liên quan `ConversionFailedException` hoặc lỗi parse số. Không nên cố sửa bằng cách thêm `${app.worker-count:4}` nếu value `three` **đang tồn tại**; default không chữa một value sai định dạng.

### 11.1. Các ví dụ số

| Giá trị `app.worker-count` | Chuyển sang int? | Diễn giải |
| --- | --- | --- |
| `4` | Có | Giá trị hợp lệ |
| `0` | Có | Conversion hợp lệ, policy có thể từ chối |
| `-1` | Có | Conversion hợp lệ, policy có thể từ chối |
| `3.5` | Không theo String → Integer thông thường | Số thập phân không phù hợp kiểu int |
| `three` | Không | Chuỗi không phải số |
| `999999999999999999999` | Không | Vượt giới hạn kiểu int |
| Chuỗi rỗng | Tùy target/đường binding | Không tự xem là 0 |
| Property thiếu | Có thể giữ initializer/default | Không phải một lỗi conversion tự thân |

### 11.2. Vượt miền Java khác với vượt miền nghiệp vụ

```properties
app.worker-count=100
```

Có thể chuyển sang `int`. Nhưng nếu có:

```java
@Min(1)
@Max(64)
private int workerCount;
```

thì 100 **vi phạm validation**, không phải `NumberFormatException`.

Ngược lại:

```properties
app.worker-count=99999999999999999999999
```

có thể thất bại trước validation vì int không biểu diễn được. Điều tra đúng tầng giúp báo lỗi và sửa chính xác.

## 12. Duration: sai format và sai đơn vị âm thầm

Spring Boot 3.3 hỗ trợ binding `java.time.Duration` từ:

- Số nguyên, mặc định **mili giây** nếu không có `@DurationUnit`.
- Dạng ISO-8601, ví dụ `PT5S` hoặc `PT1M`.
- Dạng compact như `500ms`, `5s`, `2m`, `1h`.

Các đơn vị tài liệu Boot 3.3 liệt kê:

| Hậu tố | Đơn vị |
| --- | --- |
| `ns` | Nanosecond |
| `us` | Microsecond |
| `ms` | Millisecond |
| `s` | Giây |
| `m` | Phút |
| `h` | Giờ |
| `d` | Ngày |

Ví dụ:

```properties
app.connect-timeout=5s
```

cho Java field:

```java
private Duration connectTimeout;
```

là năm giây.

Nhưng:

```properties
app.connect-timeout=5
```

được hiểu là **5 mili giây** theo mặc định, dù có thể bind thành công. Đây là **lỗi ngữ nghĩa/đơn vị** mà exception không tự phát hiện.

### 12.1. Một số triệu chứng

| Input | Kết quả/chẩn đoán |
| --- | --- |
| `5000ms` | Duration năm giây |
| `5s` | Duration năm giây |
| `PT5S` | Duration năm giây |
| `5` | Duration 5ms theo mặc định |
| `soon` | Sai định dạng Duration |
| `5seconds` | Không thuộc cú pháp compact được tài liệu 3.3 liệt kê; dùng `5s` |
| `-5s` | Có thể biểu diễn Duration âm; nghiệp vụ phải kiểm tra |
| Giá trị quá lớn | Có thể lỗi conversion hoặc lỗi downstream |

Nếu muốn số không hậu tố được hiểu là giây:

```java
@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
```

Cần import `java.time.temporal.ChronoUnit` và `org.springframework.boot.convert.DurationUnit`.

**Không dùng default placeholder để che lỗi sai đơn vị.** `${app.connect-timeout:5s}` có default hợp lý khi key thiếu, nhưng nếu env cung cấp `5`, source env vẫn có thể thắng và cho ra 5ms.

## 13. DataSize: 64 không phải 64MB

`org.springframework.util.unit.DataSize` là kiểu dành cho kích thước dữ liệu. Nếu không có `@DataSizeUnit`:

```properties
app.cache-size=64
```

được hiểu là **64 byte**, không phải 64 MB.

Nên dùng:

```properties
app.cache-size=64MB
```

Hậu tố được Spring Boot 3.3 hỗ trợ gồm `B`, `KB`, `MB`, `GB`, `TB`.

### 13.1. Ví dụ converter/annotation

```java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize cacheSize = DataSize.ofMegabytes(64);
```

Nếu có annotation này, bare value `64` được hiểu theo đơn vị MB. Dẫu vậy, việc viết `64MB` trong file thường dễ hiểu hơn đối với người vận hành.

### 13.2. Sai hậu tố

```properties
app.cache-size=64Megabytes
```

không thuộc dạng compact chuẩn Boot 3.3, có thể gây conversion failure. Dùng `64MB`.

Tương tự `64MiB` không nằm trong danh sách hậu tố `B/KB/MB/GB/TB` của tài liệu Boot 3.3; hãy sử dụng hậu tố được hỗ trợ và thống nhất ý nghĩa đơn vị trong toàn hệ thống.

## 14. Enum, Boolean, URI và List/Map

### Enum

```java
enum Mode {
    SAFE, FAST
}

private Mode mode = Mode.SAFE;
```

Property:

```properties
app.mode=UNKNOWN
```

có thể gây conversion failure vì không có enum constant tương ứng. Không nên trông cậy default `SAFE` sẽ được dùng khi key có mặt với value không hợp lệ.

### Boolean

```properties
app.feature-enabled=false
```

là một value hợp lệ và explicit. Nhưng:

```properties
app.feature-enabled=perhaps
```

không phải dạng boolean rõ ràng; có thể gây lỗi conversion. Nếu muốn cấu hình dễ đọc và ít mơ hồ, dùng `true`/`false`.

### URI/URL

```java
private URI baseUri;
```

```properties
app.base-uri=http://[invalid
```

Target `URI` có thể từ chối cú pháp. Ngược lại, một URI hợp lệ về cú pháp chưa bảo đảm host có DNS record hoặc TLS certificate hợp lệ. **Conversion success không phải connectivity test.**

### List và Map

```yaml
app:
  retries:
    billing: 3
    search: invalid
```

Nếu Java model là `Map<String,Integer>`, lỗi có thể nằm ở `app.retries.search` chứ không phải cả Map. Cần đọc đường property con trong bind failure.

Với List:

```properties
app.workers[0]=4
app.workers[1]=abc
```

target `List<Integer>` có thể thất bại ở index 1. Hãy kiểm tra value thực ở nguồn ưu tiên cao nhất; list cũng có quy tắc replacement giữa PropertySources, không nhất thiết nối phần tử từ hai nguồn.

## 15. ConfigurationPropertiesBindException là gì?

`org.springframework.boot.context.properties.ConfigurationPropertiesBindException` là exception mà Spring Boot định nghĩa cho tình huống **binding của một `@ConfigurationProperties` bean thất bại**.

Nó thường xuất hiện khi Spring Boot tạo hoặc xử lý bean cấu hình trong ApplicationContext. Không nên đọc tên lớp rồi kết luận đó là root cause; nó có thể chỉ đóng vai trò **wrapper ghi ngữ cảnh bean/prefix** cho một `BindException` hoặc lỗi validation bên trong.

Ví dụ:

```text
Error creating bean with name 'app-...AppProperties'
    ...
ConfigurationPropertiesBindException:
    Error creating bean with name ...:
    Could not bind properties to 'AppProperties'
Caused by: BindException:
    Failed to bind properties under 'app' ...
Caused by: ConversionFailedException:
    Failed to convert from String to Integer
Caused by: NumberFormatException:
    For input string: "many"
```

Tên bean được Spring Boot tạo có thể khác theo cách đăng ký, bean name strategy và type; đừng hard-code dựa trên ví dụ minh họa.

### 15.1. Phân biệt với BindException

| Exception | Vai trò tổng quát |
| --- | --- |
| `ConfigurationPropertiesBindException` | Ngữ cảnh binding `@ConfigurationProperties` bean thất bại |
| `org.springframework.boot.context.properties.bind.BindException` | Binding một target bằng Binder thất bại |
| `ConversionFailedException` | Chuyển một value từ source type sang target type thất bại |
| `BindValidationException` | Validation của một bind operation thất bại |
| `BeanCreationException` | Container không tạo/khởi tạo bean thành công; có thể bao bọc lỗi trên |
| `IllegalArgumentException` | Có thể là lỗi parse, placeholder, constructor validation hoặc nguyên nhân khác |
| `NumberFormatException` | Một trong các lỗi parse số, thường nằm sâu trong stack |

**Không nhầm hai `BindException` khác package:**

- Spring Boot Binder: `org.springframework.boot.context.properties.bind.BindException`.
- Spring Framework data binding: `org.springframework.validation.BindException`.

Chúng có vai trò và API khác nhau; khi đọc code/import, hãy xác định **full package name**.

### 15.2. Đọc thông tin từ BindException

Spring Boot `BindException` cung cấp thông tin hữu ích như:

- `getName()`: tên configuration property đang bind.
- `getTarget()`: target bind metadata.
- `getProperty()`: configuration property cụ thể liên quan, nếu có.
- `getOrigin()`: nguồn gốc, nếu xác định được.

Ví dụ trong code xử lý Binder riêng:

```java
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.Binder;

try {
    int count = Binder.get(environment)
            .bind("app.worker-count", Integer.class)
            .orElse(4);
} catch (BindException ex) {
    System.err.println("Could not bind property: " + ex.getName());
    System.err.println("Target: " + ex.getTarget());
    System.err.println("Origin: " + ex.getOrigin());
    throw ex;
}
```

**Không log `getProperty().getValue()` vô điều kiện**: cấu hình có thể chứa secret. `getOrigin()` có thể là `null` nếu nguồn không cung cấp origin metadata.

Khi code gọi Binder trực tiếp, `BindException` có thể xuất hiện mà **không có `ConfigurationPropertiesBindException`**, vì không phải đường khởi tạo một `@ConfigurationProperties` bean.

## 16. Bean Validation: đúng kiểu nhưng sai ràng buộc

Trong model ví dụ:

```java
@Min(1)
@Max(64)
private int workerCount = 4;
```

Input:

```properties
app.worker-count=0
```

chuyển thành int 0 thành công. Nhưng khi `@Validated` và Bean Validation provider được cấu hình phù hợp, 0 vi phạm `@Min(1)`, có thể khiến quá trình bind bean thất bại.

Phần nguyên nhân có thể là `BindValidationException` với các lỗi validation, thay vì `NumberFormatException`.

### So sánh

| Input | Conversion | Validation `@Min(1)` | Kết quả |
| --- | --- | --- | --- |
| `4` | Thành công | Qua | Hợp lệ |
| `1` | Thành công | Qua | Biên dưới |
| `0` | Thành công | Không qua | Validation failure |
| `-1` | Thành công | Không qua | Validation failure |
| `abc` | Thất bại | Chưa kiểm tra | Conversion failure |
| `999999999999999999` | Có thể thất bại cho int | Chưa kiểm tra | Tràn miền type |

### Nested validation

```java
@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Valid
    private final Server server = new Server();

    public Server getServer() { return server; }

    public static class Server {

        @Min(1)
        private int port = 8080;

        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

Khi muốn constraint của nested object được xem xét, `@Valid` và cơ chế validation phù hợp là quan trọng. Thiếu cascade validation có thể khiến nested field invalid không bị phát hiện như mong muốn. Hãy dùng Jakarta `jakarta.validation.Valid` với Spring Boot 3.3.

**Đừng cố dùng `@Min` trực tiếp cho mọi kiểu custom hoặc `Duration`:** các constraint có những kiểu dữ liệu được hỗ trợ. Với thời lượng phải dương, có thể tạo custom validator hoặc logic domain checks phù hợp.

## 17. Vì sao property đúng trong file nhưng vẫn fail?

Một case điển hình:

```properties
# application.properties
app.worker-count=4
```

Nhưng container có:

```text
APP_WORKERCOUNT=abc
```

OS environment thường có precedence cao hơn Config Data trong Spring Boot 3.3. Binder có thể chọn `abc` và cố chuyển sang `int`, rồi thất bại.

**Không phải giá trị file bị bỏ quên vô lý.** Đây là quy tắc nguồn ưu tiên; nguồn cao chứa dữ liệu sai.

Bảng minh họa:

| Source | Property | Value | Thứ tự tương đối |
| --- | --- | --- | --- |
| Packaged application.properties | `app.worker-count` | `4` | Thấp |
| External application-prod.yaml | `app.worker-count` | `8` | Cao hơn file packaged |
| OS environment | `APP_WORKERCOUNT` | `abc` | Cao hơn Config Data |
| JVM `-D` | Không khai báo | — | Không ảnh hưởng |
| Command-line | Không khai báo | — | Không ảnh hưởng |

Kết quả có thể là conversion failure trên `abc`, **không tự fallback về 8 hoặc 4**.

### 17.1. Thứ tự quan trọng trong triển khai

Theo thứ tự mặc định phổ biến:

```text
Config Data
    <
OS environment
    <
Java system properties (-D)
    <
SPRING_APPLICATION_JSON
    <
Command-line arguments (--key=value)
```

Các nguồn trong test/Devtools và custom PropertySources có thể thay đổi môi trường thực tế. Khi làm việc với một ứng dụng đã tùy biến bootstrap, hãy quan sát thứ tự thực chứ không chỉ đoán theo tài liệu mặc định.

### 17.2. Profile và Config Data import

- `application-prod.yaml` chỉ được nạp theo ngữ cảnh profile phù hợp.
- `spring.config.import` có thể đưa thêm nguồn file/configtree.
- `spring.config.location` và `additional-location` có thể thay đổi những nơi Boot tìm file.
- File Config Data ngoài JAR có thứ tự ưu tiên riêng so với file đóng gói.
- Một import location thiếu và không optional có thể làm startup fail **trước** khi bean binding.
- Multiple-document YAML/property và `spring.config.activate.on-profile` có thể khiến một document được bật/tắt.

Để biết raw value hiệu lực, phải xét **tất cả nguồn đã được nạp**, không chỉ file bạn đang mở trong IDE.

## 18. Phân tích lỗi YAML trước lỗi Binder

Ví dụ YAML hợp lệ:

```yaml
app:
  worker-count: 4
  connect-timeout: 5s
```

Lỗi indent:

```yaml
app:
worker-count: 4
```

Đoạn này có cấu trúc không phù hợp ý định hoặc có thể gây parser error tùy nội dung. Không nhất thiết nó tạo key `app.worker-count`; khi YAML được flatten, tên path có thể khác.

Lỗi syntax:

```yaml
app:
  connect-timeout: [5s
```

Có thể không parse được thành YAML hợp lệ, làm quá trình Config Data load thất bại **trước khi** `@ConfigurationProperties` được bind.

Vì vậy:

- Nếu lỗi báo không parse được file YAML, sửa cấu trúc/syntax của YAML.
- Nếu YAML parse được nhưng property không có mặt, kiểm tra indentation/path và active document.
- Nếu property có mặt nhưng conversion fail, kiểm tra value/target type.
- Nếu conversion thành công nhưng validation fail, kiểm tra constraint.

Không tự xử lý YAML parser error bằng `@Min` hay custom Converter.

## 19. Origin: nguồn file, vị trí và giá trị hiệu lực

Spring Boot có khả năng lưu **Origin** cho một số Config Data properties, ví dụ đường dẫn file và vị trí dòng/cột. Khi binding error, FailureAnalyzer có thể hiển thị thông tin này.

Ví dụ minh họa:

```text
Property: app.worker-count
Value: "oops"
Origin: class path resource [application.yaml] - 5:17
Reason: failed to convert java.lang.String to int
```

Không phải mọi PropertySource đều biết file/line:

- OS environment có thể chỉ hiển thị tên source/biến.
- Java system properties không mang line number.
- Một custom MapPropertySource có thể không có origin metadata.
- Nếu log bị sanitize, Value có thể không được in rõ.
- Nếu lỗi xảy ra quá sớm hoặc ngoài Binder, FailureAnalyzer có thể không cung cấp cấu trúc tương tự.

**Không thiếu origin = không có property.** Origin là thông tin hỗ trợ điều tra, không phải điều kiện bắt buộc để giá trị hợp lệ.

### 19.1. Đừng lộ secret khi debug

Các property như:

```text
spring.datasource.password
client.api-token
app.private-key
```

cần được xem là nhạy cảm. Không in raw values từ Environment, BindException hoặc Actuator để chứng minh origin. Chỉ kiểm tra key presence, nguồn, loại dữ liệu, chiều dài khi thực sự an toàn và tình trạng kết nối.

## 20. Chẩn đoán bằng Environment trong ứng dụng

Đối với key **không nhạy cảm**, bạn có thể đọc value hiệu lực và target bean đã bind:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ConfigDiagnostics {

    @Bean
    ApplicationRunner showSafeSettings(
            Environment env, AppProperties props) {
        return args -> {
            String raw = env.getProperty("app.connect-timeout");
            System.out.println("Raw timeout: " + raw);
            System.out.println("Typed timeout: "
                    + props.getConnectTimeout());
        };
    }
}
```

Khi `app.connect-timeout=5s`, typed value thường in thành `PT5S`. Khi `5` mà không có `@DurationUnit`, typed value có thể là `PT0.005S` (5ms).

**Giới hạn:** `ApplicationRunner` chỉ chạy nếu context đã khởi tạo được. Nếu startup fail trong bean binding, Runner sẽ không thể chạy để in diagnostic. Lúc đó đọc failure analysis, stack trace và nguồn cấu hình đã biết.

### 20.1. Kiểm tra source names mà không in values

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void listPropertySources(ConfigurableEnvironment env) {
    for (PropertySource<?> source : env.getPropertySources()) {
        System.out.println("Source: " + source.getName());
    }
}
```

Thứ tự các PropertySource hữu ích cho việc hiểu precedence. Tuy nhiên, Source names không tự cho biết một key đã được resolve qua alias env var/relaxed binding thế nào. **Không tìm một raw key String duy nhất trong mọi source rồi kết luận chắc source nào thắng.**

## 21. Dùng Actuator và logging có kiểm soát

Nếu ứng dụng có Spring Boot Actuator:

- `/actuator/env` có thể hiển thị thông tin PropertySources/value hiệu lực theo cấu hình exposure/sanitization.
- `/actuator/configprops` hỗ trợ xem những `@ConfigurationProperties` beans và dữ liệu binding.

Hai endpoint này nhạy cảm về mặt vận hành. Không public expose chúng; cần authentication, authorization, chỉ mở endpoints thực sự cần và thiết lập masking/sanitization trước khi điều tra.

Trong môi trường test hoặc staging, có thể tăng logging cho những package liên quan:

```properties
logging.level.org.springframework.boot.context.config=DEBUG
logging.level.org.springframework.boot.context.properties=DEBUG
```

`--debug` của Spring Boot có thể làm xuất hiện condition evaluation report, nhưng **không bảo đảm** hiển thị toàn bộ raw values hoặc từng bước convert. Khi thiếu thông tin, có thể tăng mức log có mục tiêu trong một môi trường được kiểm soát; tránh bật TRACE toàn bộ application trên production.

### 21.1. Startup logging không giải quyết circular placeholder

Nếu có vòng `app.a=${app.b}` và `app.b=${app.a}`, debug logging chỉ giúp nhận diện key, không tự phá vòng. Sửa relationship giữa property names.

### 21.2. Logs có thể bị che giá trị

Việc value bị sanitize trong Actuator/failure analysis là tín hiệu bảo mật đúng. Không cần bỏ masking chỉ để có một câu trả lời nhanh; có thể đối chiếu manifest, source path, key presence và loại value ở nơi được phép mà không đưa secret ra log.

## 22. Khi nào cần custom Converter?

Giả sử property là `RegionCode`:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[a-z]{2}-[a-z]+-[0-9]+")) {
            throw new IllegalArgumentException("Invalid region code");
        }
    }
}
```

Một converter đăng ký cho `@ConfigurationProperties`:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class RegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source.trim());
    }
}
```

Nếu value không match định dạng, constructor có thể ném `IllegalArgumentException` và binding fail. Đây là **application-defined conversion/domain rule**, không phải lỗi thiếu placeholder.

### 22.1. Converter được yêu cầu rất sớm

Spring Boot khởi tạo hạ tầng conversion configuration properties ở giai đoạn sớm; custom Converter nên có dependencies đơn giản. Nếu bạn viết Converter inject một service chỉ khởi tạo muộn, có thể gây bean initialization/circular dependency khác với lỗi value.

Đừng thêm custom converter chỉ để parse `Duration`/`DataSize` cơ bản: Boot đã hỗ trợ các kiểu và unit annotations tương ứng.

### 22.2. Đừng dùng Converter làm secret logger

Code converter không nên log source values vô điều kiện. Một converter phục vụ token/password có thể làm lộ dữ liệu nếu in "Cannot convert value: ..." cùng raw credential. Ném thông điệp không nhạy cảm và giữ metadata về property name/target type khi có thể.

## 23. @ConfigurationProperties và @Value có đường lỗi khác

| Đặc điểm | `@ConfigurationProperties` | `@Value` |
| --- | --- | --- |
| Mục đích | Bind nhóm cấu hình type-safe | Inject một giá trị/biểu thức |
| Relaxed binding | Có | Hạn chế; nên dùng canonical placeholder |
| Metadata IDE | Có qua processor | Không theo cơ chế config-properties metadata tương tự |
| SpEL | Không tự hỗ trợ theo `@Value` | Có |
| Bean validation | `@Validated` và provider phù hợp | Không tự có cùng cơ chế configprops validation |
| Lỗi không bind được | Có thể `ConfigurationPropertiesBindException` | Thường lỗi bean injection/placeholder/conversion |
| Nested object/Map/List | Hỗ trợ tốt | Khó quản lý hơn |
| Default khi missing | Initializer/`@DefaultValue`/fallback theo model | `${key:default}` |
| Code khuyến nghị cho nhiều keys | Có | Chỉ nên dùng cho scalar đơn giản khi phù hợp |

### 23.1. @Value thiếu placeholder

```java
@Value("${app.service-name}")
private String name;
```

Nếu key vắng, một strict placeholder resolver có thể ném IllegalArgumentException làm bean creation fail. Lỗi không nhất thiết được bọc bởi Spring Boot configuration properties binder.

### 23.2. @Value chuyển kiểu thất bại

```java
@Value("${app.worker-count}")
private int workerCount;
```

Nếu key tồn tại với value `abc`, resolver tìm được String nhưng injection/chuyển kiểu sang int thất bại. Lỗi có thể là `TypeMismatchException`/`ConversionFailedException` trong chuỗi BeanCreationException; **không cần có `ConfigurationPropertiesBindException`**.

### 23.3. @ConfigurationProperties sai kiểu

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount;
    // getters/setters
}
```

Với `app.worker-count=abc`, Spring Boot Binder thất bại, và trong lifecycle managed bean có thể phát ra `ConfigurationPropertiesBindException`. Hãy nhìn target bean và `BindException` để biết giá trị bị lỗi.

## 24. Một bài tập tái hiện ba loại lỗi

### Kịch bản A — Missing placeholder

Trong một bean:

```java
@Component
public class RemoteClientConfig {
    @Value("${remote.api-url}")
    private String apiUrl;
}
```

Không đặt `remote.api-url` ở bất kỳ nguồn nào. Kỳ vọng lỗi lúc injection với thông tin chưa resolve placeholder. Cách sửa: cung cấp property ở nguồn được nạp, sửa tên key hoặc thêm default **nếu optional thật sự**.

### Kịch bản B — Conversion failure

Dùng `AppProperties` từ phần 3, đặt:

```properties
app.worker-count=many
```

Kỳ vọng binding bean thất bại vì chuyển String sang int. Cách sửa: dùng value numeric hợp lệ, ví dụ `4`; đừng đổi `@Min(1)` vì constraint không giải quyết syntax.

### Kịch bản C — Validation failure

Đặt:

```properties
app.worker-count=0
```

Kỳ vọng conversion thành công nhưng validation từ chối vì `@Min(1)`, nếu `@Validated`/provider đã sẵn sàng. Cách sửa: cung cấp `1` hoặc hơn, trừ khi nghiệp vụ thật sự cho phép 0 thì sửa contract/constraint và tests.

### Kịch bản D — Sai đơn vị không ném lỗi

Đặt:

```properties
app.connect-timeout=5
```

Binder có thể thành công nhưng cho 5ms, không phải 5s. Cách sửa: viết `5s`. Đây là kịch bản cần **assert typed value**, vì tìm exception sẽ không phát hiện.

### Kịch bản E — Env override gây lỗi không giống file

File:

```properties
app.worker-count=4
```

Môi trường:

```bash
APP_WORKERCOUNT=bad
```

Kỳ vọng lỗi tương tự B, dù file đúng. Cách sửa: sửa hoặc gỡ env var thắng precedence.

## 25. Kiểm thử bằng ApplicationContextRunner

`ApplicationContextRunner` của `spring-boot-test` tạo context nhỏ, phù hợp để kiểm tra bean binding. Với model `AppProperties` ở phần 3:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.config.AppProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class AppPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void validPropertyBinds() {
        runner.withPropertyValues(
                "app.worker-count=4",
                "app.connect-timeout=5s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                AppProperties props =
                    context.getBean(AppProperties.class);
                assertThat(props.getWorkerCount()).isEqualTo(4);
                assertThat(props.getConnectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
            });
    }

    @Test
    void invalidIntegerFails() {
        runner.withPropertyValues("app.worker-count=many")
            .run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void invalidRangeFailsWithValidationProvider() {
        runner.withPropertyValues("app.worker-count=0")
            .run(context ->
                assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class Config {
    }
}
```

Điều kiện: class `AppProperties` có `@Validated`, Bean Validation provider phù hợp trong test classpath, Spring Boot test/JUnit/AssertJ tương ứng. `hasFailed()` không khẳng định chính xác exception wrapper ở mọi patch; nếu cần, đọc startup failure và cause chain trong test để phân biệt conversion vs validation.

### 25.1. Test placeholder

Đối với bean dùng `@Value("${remote.api-url}")`, một context runner có thể đăng ký bean và chạy không cung cấp `remote.api-url`. Khi placeholder strict không được giải quyết, context thất bại. Sau đó thử `withPropertyValues("remote.api-url=https://example.test")` để xác minh bean khởi tạo thành công.

Nếu test runner tự động có một source khác cung cấp property, phải cô lập môi trường hoặc dùng một key test khó trùng để tránh kết luận nhầm rằng placeholder không bắt buộc.

### 25.2. Test bare Duration

```java
runner.withPropertyValues("app.connect-timeout=5")
    .run(context -> {
        assertThat(context).hasNotFailed();
        AppProperties props = context.getBean(AppProperties.class);
        assertThat(props.getConnectTimeout())
            .isEqualTo(java.time.Duration.ofMillis(5));
    });
```

Đây là một test hữu ích để chứng minh **giá trị hợp lệ về parser nhưng sai đơn vị** nếu người vận hành muốn 5 giây.

### 25.3. ApplicationContextRunner không thay thế mọi bootstrap test

Runner cho phép cấp properties trực tiếp và tạo context tối giản. Nhưng nó không tự tái hiện toàn bộ Config Data bootstrap, profile-specific external files, OS env/container secret mounts và command-line arguments của production.

Nếu lỗi chỉ xuất hiện trên Kubernetes, hãy thêm integration/smoke test chạy ứng dụng với cùng profile, Config Data import, env var naming và file volume layout (dùng dummy secrets).

## 26. Kiểm tra Bean Registration và binding strategy

Có trường hợp người phát triển thấy value đúng trong `Environment` nhưng bean property vẫn null/default. Đó có thể là:

- Class `@ConfigurationProperties` **chưa được đăng ký**.
- Prefix không đúng.
- JavaBean thiếu setter cho field scalar.
- Constructor binding không phù hợp model/constructor.
- Class bị scan trong package khác.
- Có nhiều beans cùng kiểu nhưng service inject bean khác.
- Property name trùng nhưng bean field/record component đặt khác.
- Class được tạo thủ công bằng `new` thay vì do container bind.
- Các property con nested thiếu getter/setter hoặc instance setup phù hợp.

Ví dụ:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private int workerCount = 4;

    public int getWorkerCount() { return workerCount; }

    // Không có setter để JavaBean binding thay workerCount
}
```

Nếu code sử dụng JavaBean binding cho scalar field, chỉ có getter có thể khiến Binder không cập nhật value. Cách khắc phục là thêm setter hoặc dùng constructor binding phù hợp, chứ không phải đổi `app.worker-count` thành một key lạ.

### Constructor binding

Với record:

```java
@ConfigurationProperties(prefix = "app")
public record WorkerOptions(int workerCount,
                            java.time.Duration timeout) {
}
```

có thể dùng constructor binding khi loại bean được đăng ký bằng `@EnableConfigurationProperties` hoặc scanning phù hợp. Đừng tạo record rồi kỳ vọng `@Autowired` field injection hoặc setter binding xảy ra.

## 27. BindResult và Binder trực tiếp khác managed bean

Ví dụ:

```java
import org.springframework.boot.context.properties.bind.Binder;

Integer retryCount = Binder.get(environment)
    .bind("app.worker-count", Integer.class)
    .orElse(4);
```

Đây là lời gọi Binder trực tiếp. Nếu value không bind được, có thể gặp `org.springframework.boot.context.properties.bind.BindException`; không tự động có `ConfigurationPropertiesBindException` ở ngoài vì ứng dụng không phải đang tạo một `@ConfigurationProperties` bean.

Một điểm quan trọng:

- Không tìm thấy property: `BindResult` có thể không bound; `orElse(4)` dùng fallback.
- Có property `app.worker-count=0`: kết quả bound là 0, không dùng fallback.
- Có property `app.worker-count=abc`: conversion có thể ném lỗi; `orElse(4)` không phải lệnh bắt exception để cứu value sai.

Ngoài ra, Binder tự tạo với một tập `ConfigurationPropertySources` không mặc nhiên có cùng các converter, placeholder resolver, validation handler hay bean lifecycle như Binder do Spring Boot thiết lập trong ApplicationContext. Khi debug manual Binder, phân biệt thiếu hạ tầng với value thực sự sai.

## 28. Lỗi ở custom converter, placeholder resolver hoặc early lifecycle

Một case nâng cao: project tự đăng ký `@ConfigurationPropertiesBinding` converter, hoặc một bean tên `conversionService`.

Spring Boot có thể yêu cầu hạ tầng conversion rất sớm. Nếu custom converter inject service phức tạp, log có thể cho thấy bean creation/circular dependency chứ không chỉ lỗi parse value.

Tương tự, một `EnvironmentPostProcessor` chạy rất sớm có thể đọc value **trước** khi toàn bộ nguồn Config Data được chuẩn bị, tùy thứ tự post-processor. Một custom placeholder resolver có thể làm thay đổi cách missing/default/circular references được xử lý.

Để tìm lỗi đúng:

1. Xác định **thời điểm** property được đọc.
2. Xem môi trường đã có những `PropertySources` cần thiết chưa.
3. Kiểm tra custom Converter/BindHandler/PlaceholderResolver có thực sự tham gia không.
4. Đảm bảo code không tạo vòng dependency hoặc side effect khi đọc config.
5. Nếu dùng Binder thủ công, so sánh riêng cách cấu hình hạ tầng của Binder đó với managed binding.

Không thay đổi global `ConversionService`/PropertySource order chỉ để chữa một key không đúng, trừ khi có yêu cầu rõ ràng và test đảm bảo tác động rộng.

## 29. Bảng xử lý sự cố theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Bước chẩn đoán tiếp |
| --- | --- | --- |
| `Could not resolve placeholder 'x'` | Không có key, sai tên, profile/source chưa nạp | Xác định canonical key và source thực |
| `${x}` xuất hiện nguyên trong String | Resolver không xử lý theo đường tiêu thụ hoặc đang bỏ qua unresolved | Xem resolver, target type và thời điểm |
| Circular placeholder reference | `x` tham chiếu `y` rồi quay lại `x` | Vẽ đồ thị tham chiếu, phá vòng |
| `NumberFormatException` | Text không phải số hoặc quá lớn | Xem value và Java numeric target |
| `ConversionFailedException` | Converter từ source type sang target type thất bại | Đọc cause/target type |
| `ConfigurationPropertiesBindException` | Managed config bean không bind xong | Đọc nested `BindException`/validation |
| `BindValidationException` | Dữ liệu bind được nhưng constraint không đạt | Xem `@Min`/`@Max`/`@NotBlank`/`@Valid` |
| BeanCreationException | Container không khởi tạo bean | Xem nguyên nhân sâu; không kết luận ngay |
| `@Value` lỗi nhưng config bean không lỗi | Đường placeholder/injection khác Binder | Dùng canonical placeholder, kiểm tra scope |
| File có int hợp lệ nhưng startup fail | Env/CLI ghi đè bằng value sai | Xem precedence và Origin |
| Bare Duration 5 chạy như 5ms | Unit mặc định là ms | Viết `5s` |
| Bare DataSize 64 chạy như 64B | Unit mặc định là byte | Viết `64MB` |
| YAML đã parse nhưng property missing | Indentation/nested path sai | Kiểm tra flattened key |
| App chạy nhưng @Min(1) không từ chối 0 | Validation chưa áp dụng | Kiểm tra `@Validated` và provider |
| Nested @Valid không được áp dụng | Không cascade validation | Thêm `@Valid`/đăng ký validation phù hợp |
| Bean getter giữ default dù env đã override | Bean chưa đăng ký hoặc JavaBean binding không có setter | Kiểm tra model |
| Error chỉ xảy ra ở prod | Active profiles, env, configtree/import hoặc -D/CLI khác | Tái hiện deployment sources |
| Lỗi ngay lúc import Config Data | Location không tồn tại, file format không hợp lệ | Kiểm tra `spring.config.import` và startup log |
| Secret bị in trong failure analysis/log | Logging thiếu masking hoặc code log raw | Ngừng dump value, bảo vệ Actuator |
| Đổi file mà bean vẫn cũ | Không tự hot reload | Restart/rollout hoặc refresh có chủ đích |

## 30. Trình tự phân tích từng bước

Khi thấy startup exception, làm theo quy trình:

1. **Đọc thông điệp trên cùng** để biết failure xảy ra lúc nạp Config Data, tạo bean hay chạy user code.
2. **Tìm tất cả `Caused by`** và xác định nguyên nhân sâu nhất có ý nghĩa, không chỉ wrapper.
3. **Ghi lại tên canonical property** và prefix bị ảnh hưởng.
4. **Xác định Java target type**: primitive, String, enum, Duration, DataSize, URI, List, Map, custom type.
5. **Xác định nguồn hiệu lực:** file, profile, OS env, `-D`, CLI, JSON, configtree, import.
6. **Kiểm tra placeholder**: tất cả key được tham chiếu có tồn tại không? Có default? Có vòng tham chiếu?
7. **Kiểm tra tên env mapping**: dot → underscore, dash → bỏ, uppercase.
8. **Kiểm tra syntax của value**: parse số, boolean, enum, Duration, URI...
9. **Kiểm tra đơn vị và miền biểu diễn**: `5` cho Duration là 5ms? Số có vượt `int`?
10. **Kiểm tra Bean Validation** nếu convert thành công: constraints, nested `@Valid`, provider.
11. **Kiểm tra bean registration/lifecycle** nếu property có nhưng không bind: scan, setters, constructors.
12. **Sửa đúng nguồn đang thắng precedence**, không sửa một file thấp hơn rồi trông mong giá trị runtime đổi.
13. **Tạo test nhỏ nhất có thể tái hiện** và test cả giá trị sau chuyển đổi.
14. **Chạy lại trong môi trường tương ứng** để xác minh startup và downstream behavior.
15. **Tránh lộ secret** trong mọi bước và cập nhật runbook nếu nguyên nhân nằm ở cách cấp cấu hình.

Sơ đồ quyết định:

```text
APPLICATION FAILED TO START
             |
             v
   Có phải Config Data parse/load?
       /                \
      Có                Không
      |                   |
      v                   v
 Sửa file/location    Có missing placeholder?
                          /       \
                         Có       Không
                         |           |
                         v           v
                  Sửa key/source   Có conversion error?
                     /default        /       \
                                    Có       Không
                                    |           |
                                    v           v
                              Sửa format    Có bind validation?
                              /target/unit      /      \
                                             Có         Không
                                             |             |
                                             v             v
                                       Sửa constraint   Kiểm tra
                                       /value           bean lifecycle
                                                        /code
```

Cây quyết định giúp định hướng; stack trace thực tế có thể chứa nhiều lỗi kết hợp như placeholder missing rồi converter cố chuyển cả chuỗi literal.

## 31. Những sai lầm khi sửa lỗi

### 31.1. Bật ignoreInvalidFields để ứng dụng chạy bằng mọi giá

`@ConfigurationProperties` có option `ignoreInvalidFields`. Nhưng nếu source cao chứa `app.worker-count=abc`, việc bỏ qua binding invalid có thể khiến ứng dụng dùng một giá trị mặc định im lặng, che lỗi triển khai. Thông thường nên sửa giá trị nguồn và để startup fail-fast khi cấu hình quan trọng không hợp lệ.

### 31.2. Xóa constraint chỉ vì @Min làm startup fail

Nếu `@Min(1)` là ràng buộc nghiệp vụ đúng, sửa input `worker-count=0` thay vì loại bỏ validation. Chỉ thay constraint khi yêu cầu nghiệp vụ thật sự thay đổi và có tests đi kèm.

### 31.3. Dùng default placeholder cho password bắt buộc

`${db.password:secret}` có thể làm hệ thống chạy với một mật khẩu mặc định nguy hiểm. Với credential production, dùng secret manager/configtree và validation fail-fast; không hard-code secret trong source.

### 31.4. Chỉ sửa file application.yaml đang mở trong IDE

Nếu `APP_WORKERCOUNT` hoặc `--app.worker-count=...` thắng, sửa YAML thấp hơn không đổi value runtime. Đọc Origin/PropertySource precedence.

### 31.5. Dùng SpEL thay placeholder trong @ConfigurationProperties

`@ConfigurationProperties` không xử lý SpEL như `@Value`. Nếu mục tiêu là tham chiếu một property khác, sử dụng placeholder trong Config Data; nếu cần tính toán phức tạp, làm trong code theo contract rõ.

### 31.6. Bỏ qua kiểu dữ liệu

Property `app.connect-timeout=5` có thể bind mà chạy sai thành 5ms. Không tìm exception trong tình huống đó; kiểm tra typed value và unit.

### 31.7. Giấu lỗi bằng @Value default khác với config default thật

`@Value("${app.worker-count:4}")` có thể phù hợp cho một component, nhưng một `@ConfigurationProperties` bean khác có thể có default riêng. Giữ một contract nhất quán; tránh hai thành phần dùng hai fallback khác nhau cho cùng key.

### 31.8. In toàn bộ Environment và exception payload chứa secret

Điều này có thể làm lộ thông tin ở logs/ticket/chat. Giữ diagnostics theo key không nhạy cảm và origin, không dump password/token.

## 32. Checklist vận hành

- [ ] Đã xác định nguyên nhân sâu nhất trong `Caused by` thay vì chỉ tên wrapper.
- [ ] Đã phân biệt lỗi Config Data parse, placeholder, conversion, validation và bean lifecycle.
- [ ] Placeholder `${name}` dùng canonical lowercase kebab-case.
- [ ] Mọi key được tham chiếu tồn tại hoặc có default phù hợp khi optional.
- [ ] Không có vòng tham chiếu placeholder.
- [ ] Đã phân biệt empty String, missing, `0` và `false`.
- [ ] Đã kiểm tra profile, external file, Config Data import, OS env, JVM `-D` và CLI.
- [ ] Biến môi trường được đổi tên đúng dot/underscore/dash/uppercase.
- [ ] Đã xem Java target type và conversion rules.
- [ ] `Duration`/`DataSize` dùng hậu tố đơn vị explicit.
- [ ] Enum, Boolean, number, URI có cú pháp tương ứng.
- [ ] Bean `@ConfigurationProperties` đã được đăng ký.
- [ ] JavaBean setters/constructor binding hoạt động.
- [ ] Có Bean Validation provider khi cần constraints.
- [ ] Nested object được validate qua `@Valid` khi yêu cầu.
- [ ] Không bật ignoreInvalidFields chỉ để che lỗi.
- [ ] Đã kiểm tra `Origin` nếu nguồn hỗ trợ.
- [ ] Không log raw credentials hoặc expose Actuator endpoint công khai.
- [ ] Có test tái hiện lỗi với value thực tế không nhạy cảm/dummy.
- [ ] Sau sửa đổi đã restart/rollout nếu process đang chạy không tự refresh.
- [ ] Runbook ghi rõ property owner và nguồn phải sửa.

## 33. Tài liệu tham khảo chính thức

- **Spring Boot 3.3 — Externalized Configuration**, bao gồm *PropertySource Order*, *Property Placeholders*, *Type-safe Configuration Properties*, *Properties Conversion*, *ConfigurationProperties Validation*, *Config Data Imports*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API — ConfigurationPropertiesBindException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindException.html
- **Spring Boot 3.3 API — BindException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindException.html
- **Spring Boot 3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- **Spring Boot 3.3 API — BindValidationException**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html
- **Spring Boot 3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Framework 6.1 — PropertyPlaceholderHelper**: https://docs.spring.io/spring-framework/docs/6.1.4/javadoc-api/org/springframework/util/PropertyPlaceholderHelper.html
- **Spring Framework — Environment Abstraction / PropertySources**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Jakarta Bean Validation**: https://jakarta.ee/specifications/bean-validation/

## 34. Kết luận

Trong Spring Boot 3.3, muốn xử lý một lỗi cấu hình hiệu quả, hãy luôn phân biệt:

```text
Placeholder không giải được
     -> thiếu key / sai tên / vòng tham chiếu / source chưa nạp
Giá trị có mặt nhưng không chuyển được
     -> sai format / sai kiểu / vượt miền Java type
Giá trị chuyển được nhưng bean validation không đạt
     -> ràng buộc nghiệp vụ / @Validated / @Valid
Managed @ConfigurationProperties binding không hoàn tất
     -> ConfigurationPropertiesBindException bao bọc ngữ cảnh
```

**Thông điệp cần nhớ:** `ConfigurationPropertiesBindException` thường nói *bean cấu hình không bind xong*, không tự nói *vì sao*. Lý do nằm ở cause chain, `Property`, `Origin`, source precedence, target type và validation. Sửa đúng tầng gây lỗi, kiểm thử bằng giá trị sau chuyển đổi và giữ bí mật cấu hình khỏi logs.
