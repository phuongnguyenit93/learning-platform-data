# Chuẩn bị Bean Validation và các annotation jakarta.validation

## 1. Vì sao @ConfigurationProperties cần kiểm tra hợp lệ?

Spring Boot hỗ trợ đọc cấu hình từ nhiều nguồn: `application.yml`, `application.properties`, biến môi trường, tham số dòng lệnh, cấu hình theo profile và các nguồn Config Data khác. Với `@ConfigurationProperties`, Binder chuyển dữ liệu từ các nguồn này thành đối tượng Java có kiểu.

Ví dụ một dịch vụ thông báo cần:

```yaml
notification:
  enabled: true
  sender-name: Billing Team
  sender-email: billing@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Việc chuyển đổi kiểu giải quyết một số vấn đề:

- `"3"` có thể trở thành `int 3`.
- `"2s"` có thể trở thành `Duration.ofSeconds(2)`.
- Một URL có thể được chuyển thành `URI`.
- `"true"` có thể được liên kết thành `boolean true`.

Nhưng **đúng kiểu không đồng nghĩa với hợp lệ**:

```yaml
notification:
  enabled: true
  sender-name: "   "
  sender-email: not-an-email
  api-url: http://localhost:9999
  max-attempts: -5
  connect-timeout: -2s
```

Nhiều giá trị trong file thứ hai vẫn *có thể chuyển sang kiểu Java*: `-5` là `int` hợp lệ, `-2s` là `Duration` hợp lệ và chuỗi nhiều dấu cách vẫn là `String`. Tuy nhiên, chúng có thể vi phạm hợp đồng vận hành.

**Bean Validation** là cơ chế mô tả và kiểm tra các ràng buộc như “không được để trống”, “phải lớn hơn hoặc bằng một” hoặc “phải có định dạng email”. Khi kết hợp Bean Validation với `@ConfigurationProperties`, ứng dụng có thể **phát hiện cấu hình sai ngay lúc khởi động** trước khi service nhận những giá trị không phù hợp.

```text
YAML / ENV / CLI / Config Data
               |
               v
       Spring Environment
               |
               v
     @ConfigurationProperties Binder
               |
       +-------+-------+
       |               |
  Chuyển kiểu      Không chuyển được
       |               |
       v               v
  Object Java      Binding error
       |
       v
  Bean Validation
       |
  +----+----+
  |         |
Hợp lệ    Không hợp lệ
  |         |
  v         v
Bean dùng  Startup/binding
cấu hình  validation failure
```

Mục tiêu của bài là chuẩn bị dependency, import đúng API `jakarta.validation`, thêm các constraint annotation thường dùng, kích hoạt validation khi binding và quan sát lỗi một cách có thể kiểm chứng.

## 2. Ba khái niệm không nên nhầm lẫn

Trước khi viết code, cần tách ba lớp trách nhiệm.

### 2.1. Binding

`@ConfigurationProperties(prefix = "notification")` xác định nhóm khóa nào được liên kết vào object. Binder xử lý tên property theo relaxed binding và chuyển giá trị sang kiểu đích.

Ví dụ:

```yaml
notification:
  max-attempts: 3
```

có thể liên kết vào thành phần Java `int maxAttempts`.

### 2.2. Validation

Annotation như `@Min(1)` yêu cầu `maxAttempts` phải từ một trở lên. `int -5` là giá trị đúng kiểu nhưng không đạt constraint.

```java
@Min(1)
int maxAttempts
```

Nếu validation thực sự được kích hoạt, object có `maxAttempts=-5` sẽ bị từ chối trong quá trình khởi tạo bean cấu hình.

### 2.3. Quy tắc nghiệp vụ

Có những yêu cầu không thể diễn đạt đầy đủ bằng constraint đơn giản, ví dụ “chỉ khi `enabled=true` mới bắt buộc phải có `apiUrl`”, “URL phải thuộc danh sách endpoint được phê duyệt” hoặc “timeout phải ngắn hơn deadline của quy trình”.

Những yêu cầu đó cần ràng buộc cấp object, custom validator hoặc kiểm tra khởi tạo phù hợp. Không nên khẳng định rằng chỉ có `@NotNull` hay `@Email` là mọi quy tắc nghiệp vụ đã được bảo đảm.

Bảng phân biệt:

| Đầu vào | Binding | Validation | Kết luận |
| --- | --- | --- | --- |
| `max-attempts: 3` | Thành `int 3` | `@Min(1)` đạt | Hợp lệ |
| `max-attempts: abc` | Không chuyển sang `int` | Có thể chưa tới bước validation | Lỗi chuyển kiểu |
| `max-attempts: -2` | Thành `int -2` | `@Min(1)` không đạt | Lỗi validation |
| Thiếu `sender-name` | Có thể thành `null` | `@NotBlank` không đạt | Thiếu giá trị bắt buộc |
| `sender-name: "  "` | Thành `String` | `@NotBlank` không đạt | Giá trị rỗng về nội dung |
| `sender-email: invalid` | Thành `String` | `@Email` không đạt | Sai định dạng |

## 3. Jakarta Validation là gì?

Với những phiên bản Spring Boot hiện đại như Spring Boot 3.x, API Bean Validation sử dụng package **`jakarta.validation`**.

Ví dụ những import hợp lệ:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
```

Trong các hướng dẫn Spring Boot 2 hoặc dự án Java EE cũ, bạn có thể gặp:

```java
import javax.validation.constraints.NotNull;
```

Đó là namespace cũ. **Không sao chép nguyên xi các import `javax.validation.*` từ bài hướng dẫn cũ vào dự án Spring Boot 3 dùng Jakarta API.** Hai namespace là các kiểu annotation khác nhau; dùng nhầm package hoặc lẫn phiên bản dependency có thể gây lỗi biên dịch hoặc khiến validation không hoạt động như dự kiến.

Jakarta Validation có hai phần cần phân biệt:

- **API/contract**: `jakarta.validation.Valid`, `jakarta.validation.constraints.*`, `Validator`, `ConstraintViolation`, v.v.
- **Provider/implementation**: thư viện thực thi việc đánh giá các constraint, thường gặp là Hibernate Validator trong dự án Spring Boot.

Chỉ có annotation ở source code chưa bảo đảm tồn tại một validation provider trong runtime. Ứng dụng cần dependency tương thích để provider thực hiện các kiểm tra.

## 4. Cài dependency spring-boot-starter-validation

Với Spring Boot được quản lý dependency qua Spring Boot parent/BOM, cách thông dụng là thêm **`spring-boot-starter-validation`**. Starter này tích hợp các thành phần cần thiết cho Bean Validation và giúp tránh việc tự chọn những phiên bản API/provider không tương thích.

### 4.1. Maven

Trong `pom.xml`, dưới `dependencies`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Một dự án ứng dụng Boot đơn giản thường có thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
```

Với project có web, có thể đã dùng `spring-boot-starter-web` cho chức năng HTTP. Validation starter phục vụ **khả năng kiểm tra ràng buộc**; không cần mở HTTP server chỉ để validate một record cấu hình.

Sau khi sửa `pom.xml`, đồng bộ dependency trong IDE hoặc chạy build thông thường:

```bash
./mvnw test
```

Trên Windows, dùng `mvnw.cmd test` trong terminal thích hợp. Với dự án không có Maven Wrapper, có thể dùng Maven đã cài trên máy.

Không cố gắn cứng một phiên bản Hibernate Validator ngẫu nhiên nếu Spring Boot đã quản lý các phiên bản dependency tương thích.

### 4.2. Gradle Kotlin DSL

Trong `build.gradle.kts`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

### 4.3. Gradle Groovy DSL

Trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Các đoạn Gradle trên giả định project đã có các plugin Spring Boot và quản lý dependency theo cấu hình build phù hợp. Không cần dán lặp starter nếu nó đã tồn tại.

### 4.4. Tại sao nên dùng starter thay vì chỉ jakarta.validation-api?

`jakarta.validation-api` cung cấp interface và annotation. Nếu runtime không có provider thực thi, việc kiểm tra các constraint có thể không xảy ra như mong đợi hoặc việc yêu cầu một `Validator` sẽ thất bại.

`spring-boot-starter-validation` là lựa chọn thuận tiện cho ứng dụng Spring Boot vì cung cấp stack validation được tích hợp và quản lý dependency phù hợp với bản Boot của project. Trong một môi trường khác, có thể tự lắp API và provider, nhưng lúc đó người phát triển chịu trách nhiệm tương thích phiên bản và cấu hình provider.

**Kiểm tra runtime quan trọng hơn việc chỉ nhìn import:** một file Java có `@NotBlank` biên dịch thành công không chứng minh quá trình binding đang chạy validation.

## 5. Ví dụ mẫu: @ConfigurationProperties dạng record

Ta dùng một ứng dụng Spring Boot 3.x, Java 17 trở lên, không cần kết nối dịch vụ thực tế. Cấu trúc minh họa:

```text
validation-demo/
└── src/
    ├── main/
    │   ├── java/com/example/validationdemo/
    │   │   ├── ValidationDemoApplication.java
    │   │   └── NotificationProperties.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/validationdemo/
            └── NotificationPropertiesTest.java
```

Địa chỉ dùng đuôi `.invalid` chỉ là dữ liệu mẫu, không phải endpoint thực tế.

Tạo `application.yml`:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Tạo `NotificationProperties.java`:

```java
package com.example.validationdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(

        boolean enabled,

        @NotBlank
        String senderName,

        @NotBlank
        @Email
        String senderEmail,

        @NotNull
        URI apiUrl,

        @Min(1)
        @Max(10)
        int maxAttempts,

        @NotNull
        Duration connectTimeout
) {
}
```

Các annotation trong record có mục đích:

| Thành phần | Kiểu | Constraint | Ý định |
| --- | --- | --- | --- |
| `enabled` | `boolean` | Không bắt buộc constraint ở ví dụ | Bật/tắt tính năng |
| `senderName` | `String` | `@NotBlank` | Không null, không rỗng hoặc chỉ toàn khoảng trắng |
| `senderEmail` | `String` | `@NotBlank` và `@Email` | Bắt buộc có giá trị, đồng thời có dạng email |
| `apiUrl` | `URI` | `@NotNull` | Bắt buộc được cấp |
| `maxAttempts` | `int` | `@Min(1)`, `@Max(10)` | Giới hạn trong khoảng 1–10 |
| `connectTimeout` | `Duration` | `@NotNull` | Bắt buộc được cấp |

Một số lưu ý:

- `@Validated` được import từ **`org.springframework.validation.annotation.Validated`** của Spring.
- `@NotBlank`, `@Email`, `@Min`, `@Max` và `@NotNull` được import từ **`jakarta.validation.constraints`**.
- `@ConfigurationProperties` thuộc package **`org.springframework.boot.context.properties`**.
- `@NotNull` trên `Duration` chỉ đảm bảo không null; **nó không đảm bảo thời lượng lớn hơn zero**.
- `@NotNull` trên `URI` không có nghĩa URI dùng HTTPS, có host hợp lệ hoặc kết nối được.
- Khi thiết kế kiểu primitive `int`, thiếu giá trị có thể dẫn đến 0 trong trường hợp phù hợp; `@Min(1)` giúp phát hiện số không đạt yêu cầu.

Đây là một **đối tượng chứa cấu hình có kiểu và constraint**, không phải nơi gọi HTTP hay xử lý nghiệp vụ.

## 6. Đăng ký lớp cấu hình để validation có cơ hội chạy

Chỉ thêm annotation vào record chưa đủ nếu lớp đó không được đăng ký làm configuration-properties bean.

Tạo `ValidationDemoApplication.java`:

```java
package com.example.validationdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showNotificationConfig(
            NotificationProperties properties) {
        return args -> {
            System.out.println(
                "enabled = " + properties.enabled());
            System.out.println(
                "senderName = " + properties.senderName());
            System.out.println(
                "maxAttempts = " + properties.maxAttempts());
            System.out.println(
                "connectTimeout = " + properties.connectTimeout());
        };
    }
}
```

`@EnableConfigurationProperties(NotificationProperties.class)` đăng ký kiểu cấu hình. Khi Spring Boot dựng context:

1. Tìm các nguồn thuộc tính đang có hiệu lực.
2. Bind `notification.*` vào record.
3. Chạy Bean Validation đối với object có `@Validated` và provider phù hợp.
4. Nếu hợp lệ, tạo bean `NotificationProperties` để các bean khác nhận qua constructor.
5. Nếu không hợp lệ, có thể dừng quá trình khởi động và báo lỗi binding/validation.

Với ví dụ trên, `ApplicationRunner` chỉ in những giá trị **không nhạy cảm**. Không in token, password hoặc danh sách toàn bộ cấu hình trong một ứng dụng thật.

Thay vì `@EnableConfigurationProperties` cho từng lớp, dự án có nhiều lớp cấu hình có thể sử dụng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ValidationDemoApplication {
    // ...
}
```

Nhớ import `org.springframework.boot.context.properties.ConfigurationPropertiesScan`. Chọn một cơ chế đăng ký rõ ràng cho record trong ví dụ.

**Không nên mặc định thêm `@Component` vào record constructor-bound `@ConfigurationProperties` rồi mong Spring tự sử dụng Binder cho mọi constructor argument như khi dùng `@EnableConfigurationProperties`.** Cơ chế constructor binding và constructor injection của bean thông thường khác nhau.

## 7. Thí nghiệm đầu tiên: cấu hình hợp lệ và cấu hình không hợp lệ

### 7.1. Trường hợp hợp lệ

Dùng `application.yml` đã cho:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Đóng gói ứng dụng rồi chạy JAR thực thi; `app.jar` là tên minh họa:

```bash
java -jar app.jar
```

Kết quả mong đợi:

```text
enabled = true
senderName = Operations
maxAttempts = 3
connectTimeout = PT2S
```

Trong đó `PT2S` là dạng `Duration.toString()` cho hai giây.

### 7.2. Vi phạm @Min

Chỉ đổi giá trị `max-attempts`:

```bash
java -jar app.jar --notification.max-attempts=0
```

Giá trị `0` chuyển sang `int` thành công, nhưng không đạt `@Min(1)`. Vì vậy Spring Boot có thể báo lỗi khởi động liên quan đến validation của `NotificationProperties`, nêu field `maxAttempts`, giá trị bị từ chối và constraint chưa đạt.

Hình thức thông báo thay đổi giữa phiên bản, nhưng nội dung tương tự:

```text
Failed to bind properties under 'notification'
...
Property: notification.maxAttempts
Value: 0
Reason: must be greater than or equal to 1
```

Đây là ví dụ mô tả, không phải log phải giống từng ký tự. **Nguyên nhân không phải `0` không chuyển thành `int`**, mà là một ràng buộc trên số nguyên đã bị vi phạm.

### 7.3. Vi phạm @NotBlank

Chạy:

```bash
java -jar app.jar '--notification.sender-name=   '
```

Tham số đã được trích dẫn để giữ nguyên khoảng trắng. Một chuỗi chỉ có khoảng trắng không đạt `@NotBlank`. Nếu dùng một shell khác, cần đảm bảo giá trị thực sự đến ứng dụng đúng như mong muốn.

### 7.4. Vi phạm @Email

Chạy:

```bash
java -jar app.jar --notification.sender-email=not-an-email
```

Chuỗi được bind vào `String` nhưng không thỏa định dạng email theo validator đang sử dụng. Kết quả có thể là lỗi validation khi Spring dựng context.

`@Email` là ràng buộc cú pháp, **không chứng minh địa chỉ email tồn tại hay nhận được thư**. Việc xác thực email thực tế là một bài toán khác.

### 7.5. Lỗi conversion trước validation

Chạy:

```bash
java -jar app.jar --notification.max-attempts=several
```

`several` không chuyển thành `int`. Đây là lỗi binding/type conversion. Constraint `@Min` không thể biến một chuỗi không phải số thành số hợp lệ. Khi phân tích log, cần phân biệt nguyên nhân.

## 8. Các annotation jakarta.validation thường dùng

### 8.1. @NotNull

`@NotNull` yêu cầu giá trị khác `null`.

```java
@NotNull
URI apiUrl;
```

Phù hợp với reference type như `URI`, `Duration`, object lồng nhau. Với `int` primitive, kiểu này không thể `null` nên `@NotNull` không kiểm tra được tình huống thiếu khóa theo cùng cách.

Ví dụ:

```yaml
notification:
  api-url: https://notify.example.invalid/api
```

Nếu thuộc tính không tồn tại và object nhận `null`, constraint không đạt. Nhưng URL không hợp lệ về mặt nghiệp vụ vẫn cần kiểm tra riêng; `URI` hợp lệ về cú pháp chưa bảo đảm ứng dụng gọi được endpoint.

### 8.2. @NotEmpty

`@NotEmpty` yêu cầu giá trị không null và không rỗng. Nó có thể áp dụng cho `CharSequence`, collection, map hoặc array theo loại được provider hỗ trợ.

```java
@NotEmpty
List<String> recipients;
```

Điều này yêu cầu danh sách có phần tử, nhưng không có nghĩa **từng phần tử** đều không rỗng. Nếu cần kiểm tra từng email, dùng annotation cấp phần tử thích hợp.

### 8.3. @NotBlank

`@NotBlank` dành cho chuỗi `CharSequence`, yêu cầu không null và có ít nhất một ký tự không phải khoảng trắng.

```java
@NotBlank
String senderName;
```

So sánh:

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `null` | Sai | Sai | Sai |
| `""` | Đúng | Sai | Sai |
| `"   "` | Đúng | Đúng | Sai |
| `"Ops"` | Đúng | Đúng | Đúng |

`@NotBlank` phù hợp với tên hiển thị hoặc chuỗi bắt buộc. Không dùng `@NotBlank` trực tiếp cho `URI`, `Integer` hay `Duration`; nó không phải constraint tổng quát cho mọi kiểu.

### 8.4. @Min và @Max

Hai annotation dùng cho giới hạn số:

```java
@Min(1)
@Max(10)
int maxAttempts;
```

Chúng kiểm tra điều kiện `maxAttempts >= 1` và `maxAttempts <= 10`.

Ví dụ kết quả:

| Giá trị | `@Min(1)` | `@Max(10)` |
| --- | --- | --- |
| 0 | Sai | Đúng |
| 1 | Đúng | Đúng |
| 5 | Đúng | Đúng |
| 10 | Đúng | Đúng |
| 11 | Đúng | Sai |

Với `BigDecimal` hoặc nhu cầu kiểm soát số thập phân, có thể dùng `@DecimalMin`, `@DecimalMax` hoặc constraint thích hợp. Không mặc định `@Min` là giải pháp đúng cho mọi kiểu số thực.

### 8.5. @Positive và @PositiveOrZero

```java
@Positive
int retryCount;

@PositiveOrZero
long pendingCount;
```

`@Positive` yêu cầu lớn hơn 0. `@PositiveOrZero` cho phép 0. Khi mô hình hóa số lần thử **tối đa**, cần quyết định 0 có hợp nghĩa “không thực hiện” hay không trước khi chọn annotation.

### 8.6. @Size

```java
@Size(min = 2, max = 40)
String senderName;

@Size(min = 1, max = 5)
List<String> recipients;
```

`@Size` kiểm tra độ dài chuỗi hoặc kích thước collection/map/array theo loại được hỗ trợ. Nó không kiểm tra bản thân mỗi phần tử trong collection.

Đặc biệt, `@Size(min=1)` trên một chuỗi chỉ có khoảng trắng vẫn có thể đạt. Nếu mục tiêu là cấm chuỗi toàn khoảng trắng, cần `@NotBlank`.

### 8.7. @Email

```java
@NotBlank
@Email
String senderEmail;
```

Hai annotation có vai trò bổ sung. `@Email` có thể chấp nhận `null` như một giá trị không bị vi phạm bởi chính constraint định dạng; `@NotBlank` yêu cầu phải nhập nội dung.

Việc một chuỗi được chấp nhận là email về cú pháp **không chứng minh** domain có mail server, người nhận tồn tại hay địa chỉ đã được xác minh.

### 8.8. @Pattern

```java
@Pattern(regexp = "[a-z][a-z0-9-]*")
String clientCode;
```

Constraint dùng regex để kiểm tra định dạng chuỗi. Ở ví dụ này, mã bắt đầu bằng chữ thường, sau đó gồm chữ thường, số hoặc dấu gạch ngang.

Nếu giá trị bắt buộc, kết hợp với `@NotBlank`. Một mình `@Pattern` thường không dùng để bắt buộc thuộc tính phải có mặt.

### 8.9. @Valid

`@Valid` không phải constraint như `@Min`. Nó yêu cầu validation **đi tiếp vào đối tượng hoặc phần tử lồng nhau**, thường được gọi là *cascaded validation*.

```java
@Valid
@NotNull
RetryPolicy retry;
```

Khi object `retry` có mặt, `@Valid` giúp kiểm tra constraint trên các field bên trong. `@NotNull` yêu cầu object lồng nhau không được thiếu. Hai annotation này làm hai công việc khác nhau.

## 9. Validation của cấu hình lồng nhau

Ứng dụng thực tế thường có cấu hình nhiều cấp:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  retry:
    max-attempts: 4
    backoff: 250ms
```

Một record lồng nhau:

```java
package com.example.validationdemo;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(

        @NotBlank String senderName,

        @NotBlank String senderEmail,

        @Valid
        @NotNull
        Retry retry
) {
    public record Retry(
            @Min(1) @Max(10) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
```

Khi Binder tạo `NotificationProperties`, nó có thể tạo tiếp object `Retry` từ `notification.retry.*`. `@Valid` trên thành phần `retry` yêu cầu provider tiếp tục đánh giá các constraint trong `Retry`.

Nếu YAML có:

```yaml
notification:
  sender-name: Operations
  sender-email: ops@example.invalid
  retry:
    max-attempts: 0
    backoff: 100ms
```

thì `maxAttempts=0` không đạt `@Min(1)`. Nhờ validation lồng nhau, lỗi có thể được báo ở đường dẫn `notification.retry.max-attempts`.

**Đừng bỏ qua @Valid chỉ vì nested class có annotation.** Trong nhiều tình huống Bean Validation, các constraint trên đối tượng lồng nhau sẽ không tự được duyệt nếu không có cơ chế cascading hoặc quy tắc validation phù hợp. Để hành vi rõ ràng, dùng `@Valid` khi cần kiểm tra sâu.

### @NotNull và @Valid khác nhau thế nào?

Với:

```java
@Valid
Retry retry;
```

nếu `retry` là `null`, cascading không kiểm tra field của một object chưa tồn tại; `null` không tự trở thành vi phạm của `@Valid`.

Với:

```java
@Valid
@NotNull
Retry retry;
```

`@NotNull` yêu cầu object có mặt. Khi có mặt, `@Valid` kiểm tra các constraint bên trong.

Điều này đặc biệt quan trọng nếu một nhóm cấu hình lồng nhau **bắt buộc phải được cấp** ở mọi môi trường triển khai.

## 10. Collection và Map: kiểm tra phần tử, không chỉ toàn bộ nhóm

Giả sử cấu hình có danh sách email của người nhận thông báo:

```yaml
notification:
  recipients:
    - ops@example.invalid
    - audit@example.invalid
```

Có thể khai báo:

```java
import java.util.List;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

@ConfigurationProperties(prefix = "notification")
@Validated
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients
) {}
```

Ở đây:

- `@NotEmpty` yêu cầu danh sách không được rỗng.
- `@NotBlank` trên tham số generic yêu cầu từng phần tử chuỗi có nội dung.
- `@Email` kiểm tra định dạng của từng phần tử.

Đây là **container-element constraints** của Jakarta Validation, cần một provider hỗ trợ phù hợp, như Hibernate Validator hiện đại được quản lý bởi Spring Boot.

Với danh sách object, có thể sử dụng:

```java
public record NotificationProperties(
        @NotEmpty
        List<@Valid Channel> channels
) {
    public record Channel(
            @NotBlank String name,
            @NotBlank String topic
    ) {}
}
```

`@Valid` trên kiểu phần tử yêu cầu kiểm tra constraint trong từng `Channel`. Nếu cấu hình có một channel thiếu `topic`, ràng buộc có thể thất bại.

Với Map, tương tự có thể dùng các constraint ở key hoặc value theo khả năng provider hỗ trợ:

```java
public record NotificationProperties(
        Map<@NotBlank String, @Valid Channel> channels
) {
    public record Channel(@NotBlank String topic) {}
}
```

Nếu danh sách hoặc map có tên khóa động, **validation vẫn không tự chứng minh các tên đó thuộc danh sách nghiệp vụ được phép**. Để hạn chế tên channel, vùng hoặc tenant, cần constraint phù hợp hoặc một custom validator.

## 11. Khi nào cần custom constraint?

Những annotation chuẩn xử lý tốt các điều kiện cơ bản. Nhưng giả sử yêu cầu là:

> Nếu `notification.enabled=true` thì `api-url` phải sử dụng HTTPS và `max-attempts` phải từ 1 đến 5. Nếu tính năng tắt, không cần cấu hình URL.

`@NotNull` trên `apiUrl` không thể tự biểu diễn đầy đủ điều kiện “chỉ bắt buộc khi enabled”. `@Min` chỉ nhìn một trường, không hiểu cờ bật/tắt ở trường khác.

Có thể giải quyết bằng một ràng buộc cấp object, ví dụ một phương thức kiểm tra với `@AssertTrue`:

```java
package com.example.validationdemo;

import java.net.URI;

import jakarta.validation.constraints.AssertTrue;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        URI apiUrl,
        int maxAttempts
) {
    @AssertTrue(message =
        "when notification is enabled, HTTPS URL "
        + "and 1..5 attempts are required")
    public boolean isEnabledConfigurationValid() {
        if (!enabled) {
            return true;
        }

        return apiUrl != null
            && "https".equalsIgnoreCase(apiUrl.getScheme())
            && apiUrl.getHost() != null
            && maxAttempts >= 1
            && maxAttempts <= 5;
    }
}
```

Phương thức theo quy ước JavaBean `isEnabledConfigurationValid()` trả về boolean để Bean Validation có thể xem như một thuộc tính được ràng buộc. Khi `enabled=true` mà URL thiếu hoặc dùng HTTP, constraint thất bại.

Đây là ví dụ đơn giản cho quy tắc liên trường. Trong một hệ thống có quy tắc phức tạp, có thể định nghĩa một **class-level constraint** riêng bằng `@Constraint` và `ConstraintValidator`, giúp trả thông báo lỗi có cấu trúc, xác định field liên quan và tái sử dụng quy tắc.

Không nên nhét quá nhiều logic nghiệp vụ hoặc gọi mạng vào quá trình validation. Validation cấu hình nên kiểm tra những thuộc tính có sẵn, diễn ra nhanh và cho kết quả xác định lúc khởi động.

## 12. Giá trị mặc định và validation có thể phối hợp thế nào?

Giá trị mặc định giúp giảm số khóa phải khai báo, nhưng **mặc định cũng cần hợp lệ**.

Ví dụ trong `application.yml`:

```yaml
notification:
  enabled: false
  max-attempts: 3
```

Nếu record yêu cầu `@Min(1)`, giá trị mặc định `3` là hợp lệ. Nhưng nếu người triển khai ghi đè:

```bash
java -jar app.jar --notification.max-attempts=0
```

thì giá trị có hiệu lực là `0` và validation sẽ từ chối nó. Không có quy tắc rằng giá trị trong YAML luôn thắng hoặc rằng nó là fallback khi giá trị ghi đè không hợp lệ.

Trong constructor binding của Spring Boot, có thể dùng annotation `@DefaultValue` để chỉ định giá trị khi không có thuộc tính phù hợp:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("3") @Min(1) @Max(10) int maxAttempts
) {}
```

Cần nhớ:

- `@DefaultValue` là annotation hỗ trợ **binding mặc định** của Spring Boot, không phải Jakarta Validation constraint.
- `@Min`/`@Max` kiểm tra giá trị của record sau binding.
- Nếu môi trường thực sự cấp một giá trị không hợp lệ, mặc định không có nhiệm vụ tự sửa dữ liệu đó.
- Nếu một trường primitive không có giá trị và không có default, giá trị sau binding có thể là zero/false theo tình huống; constraint phù hợp giúp phát hiện thiếu trong những trường cần số dương.

Không nên dùng nhiều mặc định mâu thuẫn giữa YAML, annotation, giá trị trong service và cấu hình triển khai. Chọn một nơi mang tính hợp đồng rõ ràng.

## 13. Cấu hình theo profile vẫn phải hợp lệ

Ví dụ chung `application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

File `application-prod.yml`:

```yaml
notification:
  enabled: true
  api-url: https://notify-prod.example.invalid/api
  max-attempts: 5
```

Khi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Spring Boot nạp các nguồn cấu hình tương ứng, xác định giá trị có hiệu lực của từng khóa, rồi binder tạo `NotificationProperties`. Các constraint kiểm tra **giá trị cuối cùng sau binding**, không phải từng dòng YAML riêng rẽ.

Điều này có hai hệ quả:

1. Một file chung có giá trị hợp lệ có thể bị ghi đè bằng giá trị không hợp lệ từ nguồn có ưu tiên cao hơn.
2. Một file profile chỉ khai báo một vài khóa vẫn có thể hợp lệ vì các khóa còn lại được lấy từ nguồn chung, miễn là không có ràng buộc nào bị vi phạm.

Ví dụ:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.max-attempts=-1
```

Tham số dòng lệnh có thể có ưu tiên cao hơn Config Data và khiến validation thất bại dù file `application-prod.yml` ghi `max-attempts: 5`.

Vì vậy, một ứng dụng quan trọng nên được kiểm tra với những profile và cơ chế cấp cấu hình thực tế của từng môi trường, thay vì chỉ thử mỗi `application.yml`.

## 14. Lỗi binding và lỗi validation khác nhau trên log

Đọc thông báo khởi động theo trình tự giúp khoanh vùng nguyên nhân.

### 14.1. Sai kiểu

```properties
notification.max-attempts=several
```

Nếu record cần `int`, lỗi xảy ra vì không có cách chuyển một chuỗi như vậy sang `int` theo converter hiện có. Log có thể nêu `Failed to bind properties under 'notification.max-attempts' to int` hoặc nguyên nhân chuyển đổi tương đương.

**Không sửa bằng cách bỏ @Min**; vấn đề nằm ở dữ liệu đầu vào hoặc kiểu đích.

### 14.2. Đúng kiểu, sai ràng buộc

```properties
notification.max-attempts=-1
```

`-1` chuyển sang `int` thành công; `@Min(1)` mới là chỗ từ chối. Log có thể hiển thị rejected value và thông điệp `must be greater than or equal to 1`.

**Không sửa bằng cách đổi int sang String**; cần chỉnh số lần thử hoặc hợp đồng validation.

### 14.3. Thiếu giá trị bắt buộc

Nếu `sender-name` không có trong các nguồn và record nhận `null`, `@NotBlank` có thể báo lỗi. Điều này khác với một thuộc tính dư không có field nhận.

### 14.4. Thuộc tính dư

Nếu file có `notification.debug-mode` nhưng record không khai báo field đó, Spring Boot có thuộc tính `ignoreUnknownFields` trên `@ConfigurationProperties` để điều khiển việc bỏ qua hay báo lỗi những thuộc tính không được liên kết.

Đây không phải việc của `@NotBlank`/`@Min`. Validation của field và kiểm tra unknown property là hai nhóm quy tắc riêng.

### 14.5. Một khóa có giá trị rỗng

```properties
notification.sender-name=
```

Với `String senderName`, giá trị rỗng có thể vẫn bind thành chuỗi rỗng. `@NotBlank` sẽ từ chối nó. Với `int maxAttempts`, chuỗi rỗng có thể tạo lỗi conversion/binding thay vì lỗi `@Min`. Kết luận phụ thuộc loại dữ liệu và converter được dùng.

## 15. Kiểm thử validation mà không cần chạy JAR nhiều lần

Các ví dụ dòng lệnh giúp hiểu hành vi khi chạy thật. Để kiểm thử tự động, Spring Boot Test cung cấp `ApplicationContextRunner`, cho phép tạo một context nhỏ, cung cấp các property và quan sát nó có khởi động hay không.

Trong một file test, dùng một lớp properties thu gọn để tập trung vào constraint:

```java
package com.example.validationdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotBlank String queueName,
        @Min(1) int batchSize
) {}
```

Viết test:

```java
package com.example.validationdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "worker.queue-name=inbox",
                "worker.batch-size=20"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();

                WorkerProperties properties =
                    context.getBean(WorkerProperties.class);
                assertThat(properties.queueName()).isEqualTo("inbox");
                assertThat(properties.batchSize()).isEqualTo(20);
            });
    }

    @Test
    void rejectsInvalidBatchSize() {
        runner.withPropertyValues(
                "worker.queue-name=inbox",
                "worker.batch-size=0"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Test
    void rejectsBlankQueueName() {
        runner.withPropertyValues(
                "worker.queue-name=   ",
                "worker.batch-size=20"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}
}
```

Các kiểm thử này cần dependency Spring Boot Test và Jakarta Validation provider trên classpath test. Khi dùng `spring-boot-starter-test` và `spring-boot-starter-validation` theo project Spring Boot được cấu hình đúng, thường không cần khởi tạo mock HTTP server hoặc database.

Mục tiêu của test:

- **Test hợp lệ** xác nhận Binder tạo bean và cung cấp giá trị đúng kiểu.
- **Test số không hợp lệ** xác nhận `@Min(1)` từ chối `0`.
- **Test tên rỗng** xác nhận `@NotBlank` từ chối chuỗi chỉ có khoảng trắng.

Không nên kết luận mọi case đều được bảo vệ chỉ vì một test chạy qua; mỗi constraint quan trọng cần trường hợp hợp lệ và không hợp lệ đại diện.

## 16. Test nested validation

Với cấu hình lồng nhau, nên có test chứng minh constraint của nested object thật sự được chạy. Ví dụ:

```java
package com.example.validationdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts
    ) {}
}
```

Một test dùng `ApplicationContextRunner` tương tự:

```java
@Test
void validatesNestedRetryObject() {
    runner.withPropertyValues(
            "jobs.retry.max-attempts=0"
        )
        .run(context -> {
            assertThat(context.getStartupFailure()).isNotNull();
        });
}
```

Ví dụ test cần cấu hình `@EnableConfigurationProperties(JobProperties.class)` tương ứng, không dùng nguyên `TestConfig` chỉ đăng ký `WorkerProperties` ở phần trước.

Nếu test báo khởi động thành công bất ngờ, hãy kiểm tra:

1. `JobProperties` có được đăng ký làm configuration-properties bean không?
2. Có `@Validated` không?
3. Có `jakarta.validation.Valid` trên thành phần `retry` không?
4. Có Bean Validation provider tương thích trên runtime classpath không?
5. Giá trị test đã thật sự nằm dưới prefix `jobs.retry` chưa?

Việc viết test nested rất quan trọng vì một cấu hình có thể bind được object nhưng không chạy kiểm tra sâu theo ý định.

## 17. @Validated có phải luôn giống @Valid?

Không.

- `@Validated` là annotation của Spring, thường đặt trên lớp `@ConfigurationProperties` để yêu cầu Spring Boot chạy validation đối với đối tượng cấu hình được bind.
- `@Valid` là annotation Jakarta Validation, dùng để **cascaded validation** đối với một thuộc tính, đối tượng hoặc phần tử lồng nhau.
- Các constraint như `@NotBlank` và `@Min` nêu **điều kiện cụ thể** cần thỏa mãn.

Một thiết kế điển hình:

```java
@Validated
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @Valid @NotNull Retry retry
) {
    public record Retry(@Min(1) int maxAttempts) {}
}
```

Ở đây, ba lớp ý nghĩa:

```text
@Validated          -> kích hoạt validation trên root config object
@Valid              -> đi tiếp vào Retry khi có object
@Min(1)             -> luật cần kiểm tra trên maxAttempts
```

Không nên bỏ qua một thành phần rồi kỳ vọng những annotation còn lại tự thực hiện tất cả các bước.

## 18. Sử dụng annotation nào cho Duration?

Một lỗi phổ biến là gắn `@Min(1)` trực tiếp lên `Duration`:

```java
@Min(1)
Duration timeout;
```

`@Min` là một constraint dành cho các kiểu số được hỗ trợ. `Duration` không phải là `int`, `long` hay `BigDecimal`. Với một provider thông dụng, áp dụng sai loại constraint có thể gây lỗi như không tìm được validator phù hợp cho kiểu `Duration`.

Nếu chỉ cần yêu cầu có giá trị:

```java
@NotNull
Duration timeout;
```

Nếu cần yêu cầu **timeout dương**, bạn có những hướng xử lý:

1. Kiểm tra cấp object với `@AssertTrue` để bảo đảm `timeout != null && !timeout.isZero() && !timeout.isNegative()`.
2. Tạo custom constraint riêng cho `Duration`.
3. Dùng constraint bổ sung của framework nếu phiên bản Spring Boot đang dùng hỗ trợ, ví dụ các annotation thời lượng chuyên dụng; phải xác nhận package và điều kiện sử dụng theo phiên bản.
4. Nếu input thật sự là số mili giây, mô hình hóa nó bằng kiểu số và sử dụng constraint phù hợp, nhưng khi đó cần ghi rõ đơn vị.

Ví dụ cấp object:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Duration timeout
) {
    @AssertTrue(message = "worker.timeout must be positive")
    public boolean isTimeoutPositive() {
        return timeout != null
            && !timeout.isNegative()
            && !timeout.isZero();
    }
}
```

Nhớ import `jakarta.validation.constraints.AssertTrue`. Đừng cho rằng `Duration.parse(...)` hoặc Spring Boot Binder sẽ từ chối mọi Duration âm; một giá trị đúng kiểu chưa chắc phù hợp về nghiệp vụ.

## 19. Bean Validation không thay thế kiểm tra secret và endpoint

Một object `@ConfigurationProperties` có thể khai báo:

```java
@NotBlank
String apiToken;

@NotNull
URI endpoint;
```

Nếu token có nội dung và endpoint là URI có cú pháp hợp lệ, các constraint này có thể đạt. Nhưng không có gì bảo đảm:

- Token được cấp bởi đúng hệ thống hoặc chưa hết hạn.
- Token được lưu ở nơi an toàn.
- Endpoint thuộc mạng được phép truy cập.
- Server ở endpoint đang hoạt động.
- Endpoint thực hiện TLS đúng tiêu chuẩn.
- Tài khoản chạy ứng dụng có quyền kết nối.

Đây là những yêu cầu bảo mật và vận hành khác với Bean Validation cơ bản. Nên cấp secret qua kho bí mật, biến môi trường hoặc giải pháp phù hợp với nền tảng; không commit token thật trong file YAML chỉ vì lớp có `@NotBlank`.

Ngoài ra, tránh in toàn bộ `@ConfigurationProperties` khi record có trường nhạy cảm. `record.toString()` có thể đưa giá trị các trường vào log. Các thông báo lỗi validation cũng có thể hiển thị giá trị bị từ chối trong một số trường hợp; cần cân nhắc cách log và redaction cho dữ liệu bí mật.

## 20. Không phải tất cả cấu hình đều cần validation nghiêm ngặt như nhau

Với một dịch vụ production, thiếu endpoint thanh toán hoặc giới hạn retry có thể là lỗi nghiêm trọng. Nhưng một tính năng tùy chọn có thể được phép tắt khi thiếu một số khóa.

Ví dụ:

```yaml
notification:
  enabled: false
```

Nếu lớp properties luôn gắn `@NotNull` vào `apiUrl`, nó sẽ yêu cầu URL cả khi tính năng đang tắt. Điều này có thể đúng hoặc sai tùy hợp đồng.

Hai cách thiết kế:

**Cách A — mọi môi trường đều phải có URL.** Giữ `@NotNull URI apiUrl`. Điều này đơn giản, phù hợp khi endpoint là một yêu cầu triển khai bất kể cờ enabled.

**Cách B — chỉ cần URL khi tính năng bật.** Dùng constraint liên trường như `@AssertTrue` hoặc custom validator. Không áp `@NotNull` vô điều kiện lên API URL nếu hợp đồng thật sự cho phép null khi disabled.

Việc lựa chọn annotation phải xuất phát từ yêu cầu vận hành; không phải cứ thấy một trường có thể null là tự động thêm `@NotNull`.

## 21. @Validated và validation groups

Jakarta Validation hỗ trợ *validation groups* để chọn tập constraint trong những bối cảnh khác nhau. Spring `@Validated` cũng có tham số group.

Ví dụ về mặt ý tưởng: một API request ở giai đoạn tạo mới có những ràng buộc khác với giai đoạn cập nhật. Nhưng với configuration properties, quá nhiều group có thể làm hợp đồng cấu hình khó đọc.

Một ứng dụng có thể tách thành các class properties hoặc cấu hình điều kiện rõ ràng khi có tập yêu cầu khác biệt theo môi trường. Không nên vội tạo nhiều validation group chỉ để diễn đạt rằng `dev` và `prod` có endpoint khác nhau. Profile và nguồn cấu hình đảm nhận **việc chọn giá trị**; validation đảm nhận **việc kiểm tra giá trị đã chọn**.

Nếu sử dụng groups cho `@ConfigurationProperties`, cần kiểm tra cơ chế binding và phiên bản framework đang áp dụng để bảo đảm nhóm mong muốn được kích hoạt đúng. Cách đơn giản nhất để bắt đầu là validation theo nhóm mặc định, với những constraint có ý nghĩa trên mọi môi trường được hỗ trợ.

## 22. Khi validation không chạy: checklist tìm nguyên nhân

Giả sử `max-attempts=0` nhưng ứng dụng vẫn khởi động dù đã gắn `@Min(1)`. Hãy kiểm tra theo trình tự:

### 22.1. Có dependency validation provider chưa?

Mở build file của project và tìm `spring-boot-starter-validation`. Nếu chỉ có một API annotation mà không có provider phù hợp, quá trình đánh giá constraint có thể không được thiết lập.

### 22.2. Có dùng đúng namespace Jakarta không?

Với Spring Boot 3.x, import đúng:

```java
import jakarta.validation.constraints.Min;
```

Không trộn annotation từ `javax.validation` của dự án cũ.

### 22.3. Có @Validated trên lớp properties không?

```java
@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(...) {}
```

Nếu annotation chỉ tồn tại trên một class không được Spring Boot binder tạo, nó sẽ không tạo ra cơ chế kiểm tra khởi động như mong đợi.

### 22.4. Lớp properties đã được đăng ký chưa?

`@EnableConfigurationProperties(NotificationProperties.class)` hoặc `@ConfigurationPropertiesScan` phải bao phủ lớp cần bind trong ví dụ constructor binding.

### 22.5. Có đang kiểm tra nested object?

Nếu constraint nằm trong nested record, kiểm tra `@Valid` ở đường dẫn từ root tới nested object và sự hiện diện của object tương ứng.

### 22.6. Tên khóa YAML có chính xác không?

Nếu file khai báo `notification.max-atempt` (sai chính tả) nhưng record có `maxAttempts`, giá trị nhận vào có thể là thiếu/0 hoặc đến từ một nguồn khác. Lúc đó cần xem cả relaxed binding và tùy chọn `ignoreUnknownFields`; **validation chỉ nhìn thấy object và giá trị sau binding**.

### 22.7. Có nguồn ưu tiên cao hơn ghi đè không?

Tham số `--notification.max-attempts=5` có thể thắng `max-attempts: 0` trong file. Trong trường hợp đó, validation thấy giá trị hợp lệ 5 và không báo lỗi. Không kết luận validation không chạy chỉ từ việc mở một file YAML.

### 22.8. Có đang tạo object bằng new bên ngoài Spring?

```java
new NotificationProperties(true, "Ops", "bad-email", null, 0, null);
```

Đoạn Java này chỉ gọi constructor record. Bean Validation không tự chạy chỉ vì các thành phần có annotation; muốn kiểm tra một object do code tự tạo, phải dùng `Validator` hoặc một quy trình kiểm tra tương đương. Trong Spring Boot, cơ chế tích hợp validation tại binding đảm nhiệm điều đó đối với bean cấu hình được tạo theo đường chính thức.

## 23. Kiểm tra một object bằng jakarta.validation.Validator

Ngoài validation khi Spring bind properties, đôi khi cần kiểm tra một object đã được tạo sẵn. API Jakarta Validation cho phép dùng `Validator`.

Ví dụ giả định record cấu hình ngắn:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record JobOptions(
        @NotBlank String queue,
        @Min(1) int batchSize
) {}
```

Và trong một bean Spring được inject `jakarta.validation.Validator`:

```java
import java.util.Set;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

public class JobOptionsChecker {

    private final Validator validator;

    public JobOptionsChecker(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<JobOptions>> check(
            JobOptions options) {
        return validator.validate(options);
    }
}
```

Khi gọi `validator.validate(new JobOptions("", 0))`, provider có thể trả một tập vi phạm cho `queue` và `batchSize`.

Điều này minh họa rằng **Jakarta Validation là cơ chế kiểm tra object độc lập**, không chỉ dành cho HTTP request. Spring Boot tích hợp nó vào quá trình binding configuration properties khi được thiết lập phù hợp.

Với ứng dụng thật, tránh ghi các rejected value nhạy cảm ra log khi duyệt `ConstraintViolation`.

## 24. Chỉ báo lỗi sớm thôi đã đủ chưa?

Validation giúp ứng dụng từ chối cấu hình không phù hợp; nhưng quá trình triển khai vẫn cần một chu trình kiểm thử và quản lý cấu hình đáng tin cậy.

Một quy trình thực tế:

1. **Xác định hợp đồng cấu hình:** trường nào bắt buộc, trường nào có mặc định, phạm vi giá trị, phụ thuộc liên trường.
2. **Mô hình hóa bằng kiểu Java thích hợp:** `URI`, `Duration`, `int`, `List`, nested record.
3. **Thêm constraint Jakarta:** `@NotBlank`, `@Min`, `@NotNull`, `@Email`, `@Valid` theo đúng kiểu.
4. **Đăng ký và kích hoạt validation:** `@ConfigurationProperties`, `@Validated` và provider hợp lệ.
5. **Viết test cho cả hợp lệ và không hợp lệ:** nhất là default, nested object và override.
6. **Thử theo từng profile:** vì giá trị cuối cùng có thể khác giữa dev/staging/prod.
7. **Giữ nguồn cấu hình an toàn:** không commit credential, không log secret.
8. **Theo dõi lỗi khởi động:** một ứng dụng fail fast vẫn cần thông báo để người vận hành sửa đúng khóa và khởi động lại.

Không nên chặn lỗi validation bằng cách tự động thay mọi giá trị sai bằng default. Đôi khi mặc định an toàn là hợp lý; nhưng với khóa quan trọng, **lỗi được phát hiện sớm** thường tốt hơn việc chạy nhầm một cấu hình mà người triển khai không dự định.

## 25. Những lỗi thường gặp khi chuẩn bị Bean Validation

### 25.1. Chỉ thêm annotation mà quên starter

Ứng dụng có `@Min(1)` nhưng không có validation provider tương thích. Kết quả có thể không thực thi constraint như mong đợi. Thêm dependency phù hợp và kiểm tra bằng test invalid.

### 25.2. Import javax.validation của bài cũ

Spring Boot 3 dùng Jakarta API. Không trộn namespace `javax.validation.*` với `jakarta.validation.*` nếu project dùng stack Jakarta hiện đại.

### 25.3. Quên @Validated trên root properties

Chỉ gắn constraint lên record mà không có cơ chế validation phù hợp có thể khiến object được bind mà không chạy kiểm tra. `@Validated` truyền đạt rõ ý định validation cho configuration-properties bean.

### 25.4. Quên đăng ký @ConfigurationProperties

`@ConfigurationProperties` tự nó không bảo đảm một record bất kỳ sẽ được tạo thành bean. Dùng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` trong thiết kế constructor binding.

### 25.5. Dùng @NotNull để cấm chuỗi trống

`@NotNull` cho phép `""` và `"   "` vì chúng khác null. Với chuỗi bắt buộc có nội dung, dùng `@NotBlank`.

### 25.6. Dùng @Email mà không bắt buộc có email

`@Email` chủ yếu kiểm tra định dạng. Khi email bắt buộc, kết hợp với `@NotBlank` hoặc constraint phù hợp.

### 25.7. Dùng @Min trên Duration

`@Min` không phải constraint mặc định cho `Duration`. Dùng một cơ chế kiểm tra thời lượng được hỗ trợ, `@AssertTrue` hoặc custom constraint.

### 25.8. Bỏ @Valid cho object lồng nhau

Constraint bên trong nested object có thể không được đánh giá như mong đợi nếu không khai báo cascading. Kết hợp `@Valid` với `@NotNull` khi nested object bắt buộc có mặt.

### 25.9. Nhầm unknown field với validation

`notification.unused-property` có thể không được bind vào record, nhưng các constraint chuẩn chỉ kiểm tra những giá trị của object. `ignoreUnknownFields` giải quyết chính sách với khóa không có đích, không phải nhiệm vụ của `@NotBlank`.

### 25.10. Cho rằng @NotNull URI là xác nhận URL bảo mật

`@NotNull` không xác nhận scheme HTTPS, host, certificate hay kết nối. Với endpoint quan trọng, cần validation cấu trúc và chính sách truy cập phù hợp.

### 25.11. Chỉ kiểm thử dữ liệu hợp lệ

Nếu chỉ có test context khởi động thành công khi các giá trị đều chuẩn, ta chưa biết validation có chạy hay không. Phải có ít nhất một test cố tình vi phạm constraint và assert startup failure.

### 25.12. In toàn bộ cấu hình khi phát hiện lỗi

Record có thể chứa token hoặc mật khẩu; `toString()` thường in các trường. Việc log object hoặc rejected value có thể làm lộ bí mật. Chỉ hiển thị tên khóa và thông tin cần thiết bằng cơ chế log đã được bảo vệ.

## 26. Bài tập tự kiểm tra

### Bài tập 1: phân loại lỗi

Cho:

```java
@Validated
@ConfigurationProperties(prefix = "cache")
public record CacheProperties(
        @NotBlank String host,
        @Min(1) @Max(65535) int port
) {}
```

Phân loại các input:

| Cấu hình | Kết luận |
| --- | --- |
| `cache.host=localhost`, `cache.port=6379` | Hợp lệ |
| `cache.host=`, `cache.port=6379` | `@NotBlank` không đạt |
| `cache.host=localhost`, `cache.port=0` | `@Min(1)` không đạt |
| `cache.host=localhost`, `cache.port=70000` | `@Max(65535)` không đạt |
| `cache.host=localhost`, `cache.port=abc` | Lỗi chuyển đổi `int` |

### Bài tập 2: chọn annotation đúng

Một cấu hình có:

- `displayName`: chuỗi không được trống hoặc chỉ khoảng trắng.
- `email`: email bắt buộc.
- `connections`: số lượng kết nối từ 1 đến 100.
- `endpoint`: URI phải có mặt.
- `tags`: danh sách ít nhất một phần tử, mỗi phần tử không rỗng.
- `retry`: nested object bắt buộc và cần kiểm tra các trường bên trong.

Đáp án định hướng:

```java
@NotBlank String displayName

@NotBlank @Email String email

@Min(1) @Max(100) int connections

@NotNull URI endpoint

@NotEmpty List<@NotBlank String> tags

@Valid @NotNull Retry retry
```

### Bài tập 3: nhận ra vấn đề @NotNull Duration

Cho:

```java
@NotNull Duration timeout
```

Giá trị `timeout=-3s` có được chuyển thành `Duration` không? Nếu converter chấp nhận, `@NotNull` có thất bại không? Vì sao phải có kiểm tra dương riêng?

### Bài tập 4: xác nhận starter

Một project sử dụng:

```java
import jakarta.validation.constraints.Min;
```

nhưng không có `spring-boot-starter-validation`. Hãy xác định những gì cần kiểm tra ở dependency/runtime classpath để bảo đảm constraint thực sự được đánh giá, sau đó thêm starter và viết test cung cấp `max-attempts=0`.

### Bài tập 5: nested validation

Thiết kế:

```yaml
worker:
  retry:
    max-attempts: 0
```

Và record có nested `Retry` với `@Min(1)`. Thêm `@Validated` ở root, `@Valid` trên field `retry`, đăng ký bean và chứng minh ứng dụng từ chối cấu hình.

### Bài tập 6: phân biệt binding, validation và chính sách liên trường

Một dịch vụ gửi email có `enabled=false`, không có `api-url`. Đây có phải lỗi không? Hãy chọn một trong hai hợp đồng: URL luôn bắt buộc, hoặc URL chỉ bắt buộc khi enabled. Sau đó chọn constraint đơn giản hoặc validation cấp object cho phù hợp.

### Bài tập 7: khác nhau giữa @NotEmpty và @NotBlank

Thử các giá trị chuỗi: `null`, `""`, `"   "` và `"hello"`. Điền bảng kết quả của `@NotNull`, `@NotEmpty` và `@NotBlank`, rồi giải thích vì sao chỉ dùng `@NotEmpty` không đủ để kiểm tra tên người dùng.

### Bài tập 8: kiểm thử nguồn override

Trong YAML có `worker.batch-size: 20` và record gắn `@Min(1)`. Chạy với `--worker.batch-size=0`. Dự đoán trạng thái khởi động và giải thích vì sao validation kiểm tra giá trị cuối cùng sau khi nguồn ưu tiên cao hơn ghi đè YAML.

## 27. Ghi nhớ

Một chu trình validation đúng cho cấu hình Spring Boot gồm đủ ba phần:

```text
1. Dependencies
   spring-boot-starter-validation
              |
              v
2. API và annotation
   jakarta.validation.constraints.*
   jakarta.validation.Valid
   org.springframework.validation.annotation.Validated
              |
              v
3. Binding có kiểm tra
   @ConfigurationProperties
   @EnableConfigurationProperties / @ConfigurationPropertiesScan
              |
              v
   Hợp lệ -> bean được sử dụng
   Không hợp lệ -> lỗi khi khởi động
```

Phân biệt những điều quan trọng:

- **`@ConfigurationProperties`** liên kết nguồn cấu hình với một object Java có kiểu.
- **`@Validated`** yêu cầu validation của object cấu hình trong tích hợp Spring Boot.
- **`jakarta.validation.constraints.*`** khai báo các luật như không rỗng, khoảng số hoặc định dạng.
- **`@Valid`** kích hoạt kiểm tra sâu trên object hoặc phần tử lồng nhau.
- **Starter/provider** giúp các luật được thực thi, không chỉ tồn tại dưới dạng annotation.
- **Type conversion, unknown fields và Bean Validation** giải quyết các loại lỗi khác nhau.
- **Mặc định an toàn và validation** bổ sung cho nhau; validation không tự thay dữ liệu sai bằng mặc định.
- **Test trường hợp không hợp lệ** là cách trực tiếp để xác nhận validation đang hoạt động.

Kết quả mong muốn là **fail fast khi cấu hình sai**, để service không bắt đầu vận hành với endpoint thiếu, số lần thử lại âm, tên bắt buộc trống hoặc dữ liệu không đúng hợp đồng.

Tài liệu tham khảo: [Spring Boot — Type-safe Configuration Properties và Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation), [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Jakarta Validation specification](https://jakarta.ee/specifications/bean-validation/) và [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).