# Xử lý thuộc tính không có trong lớp với ignoreUnknownFields

## 1. Bài toán: YAML có khóa nhưng lớp Java không có trường tương ứng

Khi sử dụng Spring Boot Externalized Configuration, chúng ta thường ánh xạ một nhóm thuộc tính trong `application.yml` hoặc `application.properties` vào lớp Java thông qua `@ConfigurationProperties`.

Ví dụ:

```yaml
mailer:
  enabled: true
  max-attempts: 3
  connect-timeout: 2s
```

Và lớp Java:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration connectTimeout
) {}
```

Ba khóa trong YAML có thể được liên kết vào ba thành phần của record. Nhưng sẽ ra sao nếu một đồng nghiệp thêm khóa không tồn tại trong lớp?

```yaml
mailer:
  enabled: true
  max-attempts: 3
  connect-timeout: 2s
  debug-mode: true
```

Record trên **không có** thành phần `debugMode`. Khóa `mailer.debug-mode` thuộc cùng tiền tố `mailer`, nhưng không có đích nhận tương ứng trong đối tượng Java. Spring Boot phải quyết định nên:

- **Bỏ qua** thuộc tính dư và tiếp tục khởi động; hay
- **Báo lỗi** để người phát triển nhận ra cấu hình đang lệch khỏi lớp Java?

Annotation `@ConfigurationProperties` cung cấp thuộc tính `ignoreUnknownFields` để điều khiển lựa chọn này.

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = true
)
```

Giá trị mặc định của `ignoreUnknownFields` là **`true`**: các thuộc tính không được liên kết theo cơ chế này thường được bỏ qua. Nếu đặt **`false`**, Spring Boot thực hiện binding nghiêm ngặt hơn và có thể làm quá trình khởi tạo configuration-properties bean thất bại khi phát hiện các phần tử cấu hình dưới prefix còn chưa được liên kết.

Đó là trọng tâm của bài: **thuộc tính dư khác với thuộc tính thiếu hoặc sai kiểu**, và `ignoreUnknownFields` chỉ giải quyết một nhóm vấn đề cụ thể.

## 2. ignoreUnknownFields nằm ở đâu?

`ignoreUnknownFields` là một phần của annotation `@ConfigurationProperties` thuộc Spring Boot:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Ý nghĩa các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `@ConfigurationProperties` | Đánh dấu một kiểu/bean sẽ được liên kết từ cấu hình ngoài |
| `prefix = "mailer"` | Xác định nhóm thuộc tính đang được liên kết |
| `ignoreUnknownFields = true` | Cho phép bỏ qua thuộc tính không có đích liên kết, là mặc định |
| `ignoreUnknownFields = false` | Yêu cầu phát hiện các thuộc tính dư mà binder không thể liên kết |
| `enabled`, `maxAttempts` | Các thuộc tính Java có đích nhận giá trị |

Tên khóa cấu hình không phải lúc nào cũng trùng hoàn toàn với tên Java. Spring Boot hỗ trợ **relaxed binding**. Chẳng hạn `max-attempts` trong YAML phù hợp với `maxAttempts` trong record. Vì vậy, `max-attempts` không bị coi là không xác định chỉ vì có dấu gạch ngang.

**Unknown field** ở đây không có nghĩa là “khóa lạ đối với toàn bộ ứng dụng”. Nó có nghĩa là **thuộc tính thuộc phạm vi binding của một `@ConfigurationProperties` nhưng binder không ánh xạ được vào đối tượng đích trong ngữ cảnh cụ thể**.

Điều này làm `ignoreUnknownFields` khác với một công cụ quét mọi khóa trong toàn bộ `Environment`. Nó không áp dụng như một bộ kiểm tra schema toàn cục cho mọi thư viện và mọi prefix.

## 3. Hành vi mặc định: ignoreUnknownFields = true

Viết ngắn:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Tương đương về lựa chọn bỏ qua thuộc tính dư:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = true
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Với cấu hình:

```yaml
mailer:
  enabled: true
  max-attempts: 4
  debug-mode: true
```

Nếu không có trở ngại khác, kết quả binding là:

```text
MailerProperties.enabled()     = true
MailerProperties.maxAttempts() = 4
mailer.debug-mode              = không có trường đích trong record
```

Ứng dụng có thể tiếp tục khởi động. Thuộc tính `mailer.debug-mode` không biến thành trường mới, không tự tạo getter và không làm record có thêm dữ liệu. Nó chỉ không được sử dụng bởi binding của record này.

Đừng nhầm “bỏ qua khi binding” với “xóa khỏi môi trường cấu hình”. Giá trị `mailer.debug-mode` có thể vẫn tồn tại trong `Environment` nếu nguồn cung cấp nó đang được nạp; một thành phần khác tra cứu cùng khóa theo cách khác vẫn có thể đọc được. `ignoreUnknownFields` là lựa chọn của **quá trình binding đối tượng**, không phải lệnh xóa khóa khỏi mọi nguồn.

### Vì sao Spring Boot mặc định bỏ qua?

Trong hệ sinh thái cấu hình, cùng một prefix đôi khi được dùng chung giữa nhiều thành phần hoặc cấu trúc đối tượng được phát triển theo thời gian. Một lớp có thể chỉ cần một tập con thuộc tính. Cho phép bỏ qua khóa dư giúp một lớp tương thích với nguồn cấu hình phong phú hơn.

Ví dụ, file cấu hình có:

```yaml
mail:
  smtp:
    host: smtp.example.invalid
    port: 2525
    protocol: smtp
```

Nếu một lớp chỉ liên kết `mail.smtp.host` và `mail.smtp.port`, chế độ khoan dung có thể giúp lớp đó tiếp tục hoạt động ngay cả khi file còn `protocol`.

Tuy nhiên, **tính linh hoạt này cũng là một đánh đổi**. Một khóa viết sai có thể bị bỏ qua và ứng dụng sử dụng giá trị mặc định hoặc giá trị thiếu mà người viết YAML không nhận ra.

## 4. Chế độ nghiêm ngặt: ignoreUnknownFields = false

Thay annotation:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Giữ nguyên YAML có khóa dư:

```yaml
mailer:
  enabled: true
  max-attempts: 4
  debug-mode: true
```

Trong quá trình bind, Spring Boot cố kiểm tra xem các thuộc tính dưới phạm vi `mailer` có được liên kết hết với đối tượng đích hay không. `mailer.debug-mode` không có trường tương ứng, nên quá trình tạo bean có thể thất bại với lỗi liên quan đến **unbound properties**.

Thông báo phụ thuộc phiên bản Spring Boot và cách cấu hình, nhưng thường mang cấu trúc tương tự:

```text
Failed to bind properties under 'mailer'
...
The elements [mailer.debug-mode] were left unbound.
```

Thông báo này là ví dụ minh họa, không phải cam kết từng dòng log luôn giống nhau. Ý nghĩa kỹ thuật là: **có phần tử cấu hình trong phạm vi đang bind không được đối tượng đích tiêu thụ**.

Nếu gỡ `mailer.debug-mode` hoặc bổ sung thành phần Java tương ứng `boolean debugMode` (nếu ứng dụng thật sự cần), việc binding có thể thành công trở lại.

Một cách tư duy:

```text
Cấu hình dưới prefix mailer
              |
              v
       Spring Boot Binder
              |
    +---------+---------+
    |                   |
Ánh xạ được         Không ánh xạ được
    |                   |
    v                   v
Ghi vào object     ignoreUnknownFields?
                        |
                +-------+-------+
                |               |
               true            false
                |               |
             Bỏ qua      Báo unbound / lỗi
```

Đây là công cụ phù hợp khi muốn cấu hình phản ánh sát **hợp đồng của lớp Java** thay vì âm thầm chấp nhận khóa viết nhầm.

## 5. Thực hành có thể chạy: tạo lớp properties và quan sát hai chế độ

Để thấy sự khác biệt, ta tạo một ứng dụng Spring Boot nhỏ (ví dụ Spring Boot 3.x, Java 17 trở lên). Không cần database hoặc HTTP server.

### 5.1. Cấu trúc dự án

```text
unknown-field-lab/
└── src/main/
    ├── java/com/example/unknown/
    │   ├── UnknownFieldApplication.java
    │   └── MailerProperties.java
    └── resources/
        └── application.yml
```

Dự án cần các dependency Spring Boot cơ bản để chạy ứng dụng, ví dụ `spring-boot-starter`. Có thể tạo bằng Spring Initializr rồi chọn Java và một phiên bản Spring Boot tương thích.

### 5.2. Lớp cấu hình ở chế độ mặc định

`MailerProperties.java`:

```java
package com.example.unknown;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration timeout
) {}
```

`UnknownFieldApplication.java`:

```java
package com.example.unknown;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(MailerProperties.class)
public class UnknownFieldApplication {

    public static void main(String[] args) {
        SpringApplication.run(UnknownFieldApplication.class, args);
    }

    @Bean
    ApplicationRunner printBoundValues(MailerProperties properties) {
        return args -> {
            System.out.println("=== UNKNOWN FIELD LAB ===");
            System.out.println("enabled     = " + properties.enabled());
            System.out.println("maxAttempts = " + properties.maxAttempts());
            System.out.println("timeout     = " + properties.timeout());
            System.out.println("=========================");
        };
    }
}
```

`@EnableConfigurationProperties` đăng ký record để Spring Boot tạo đối tượng bằng constructor binding. Không gắn `@Component` vào record trong ví dụ này; record properties được khởi tạo thông qua cơ chế configuration binding, không phải constructor injection của một service thông thường.

### 5.3. YAML có khóa dư

Tạo `application.yml`:

```yaml
mailer:
  enabled: true
  max-attempts: 5
  timeout: 2s
  trace-mode: verbose
```

Khóa `mailer.trace-mode` **không có** thành phần `traceMode` trong record. Đóng gói JAR thực thi bằng Gradle hoặc Maven phù hợp rồi chạy nó. Các lệnh dùng `app.jar` làm tên minh họa; thay bằng đường dẫn thực tế của bản dựng.

```bash
java -jar app.jar
```

Với `ignoreUnknownFields=true` mặc định, kết quả mong đợi:

```text
=== UNKNOWN FIELD LAB ===
enabled     = true
maxAttempts = 5
timeout     = PT2S
=========================
```

`timeout` là `Duration.ofSeconds(2)` và khi in bằng `toString()` thường có biểu diễn `PT2S`. Khóa `trace-mode` không xuất hiện trong output vì record không giữ nó.

### 5.4. Bật chế độ nghiêm ngặt

Chỉ sửa annotation trong `MailerProperties.java`:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts,
        Duration timeout
) {}
```

Đóng gói lại và chạy với **cùng YAML**.

Kỳ vọng: ứng dụng **không tạo thành công bean `MailerProperties`** vì `mailer.trace-mode` không có đích binding. Spring Boot có thể hiển thị lỗi bind/unbound trong quá trình khởi tạo context. `ApplicationRunner` sẽ không in ba dòng kết quả thông thường vì context chưa khởi động hoàn tất.

Đó là sự khác nhau có thể quan sát: **không thay YAML, chỉ đổi giá trị `ignoreUnknownFields` từ `true` sang `false`**.

### 5.5. Giữ strict mode và loại bỏ khóa dư

Xóa dòng:

```yaml
trace-mode: verbose
```

Để YAML còn:

```yaml
mailer:
  enabled: true
  max-attempts: 5
  timeout: 2s
```

Đóng gói lại. Khi không còn lỗi nào khác, ứng dụng lại khởi động bình thường và in cùng ba giá trị đã được binding.

Ba bước trên chứng minh:

| Cấu hình | `ignoreUnknownFields` | Kết quả |
| --- | --- | --- |
| Có `mailer.trace-mode` không có trường nhận | `true` | Có thể khởi động, khóa dư bị bỏ qua |
| Cùng YAML, khóa dư còn nguyên | `false` | Lỗi unbound/binding |
| Loại bỏ khóa dư | `false` | Binding thành công |

## 6. Sai chính tả khóa: lỗi dễ bị che giấu nhất

Giả sử lập trình viên mong đợi cấu hình:

```yaml
mailer:
  max-attempts: 5
```

nhưng người viết YAML gõ nhầm:

```yaml
mailer:
  max-atempt: 5
```

Trong lớp Java, tên trường vẫn là `maxAttempts`. Đây **không phải** chỉ là khác biệt về dấu gạch ngang hay chữ hoa; `max-atempt` thiếu chữ `t` và thiếu phần `s` của tên đúng.

Với `ignoreUnknownFields=true`:

- Binder không có đích cho `mailer.max-atempt`.
- Thành phần `maxAttempts` có thể nhận giá trị mặc định của kiểu nếu thiếu khóa và không có quy tắc binding/validation khác.
- Nếu `maxAttempts` là `int` primitive, giá trị mặc định trong trường hợp constructor binding thiếu dữ liệu có thể là `0`.
- Ứng dụng có thể khởi động và hành vi nghiệp vụ sai mà không có tín hiệu rõ từ khóa gõ nhầm.

Với `ignoreUnknownFields=false`, Spring Boot có cơ hội báo `mailer.max-atempt` chưa được liên kết. Người phát triển có thể phát hiện lỗi ngay từ khởi động.

Tuy nhiên, **strict mode vẫn chưa chứng minh mọi khóa bắt buộc đều tồn tại**. Nếu người viết **quên hoàn toàn** `mailer.max-attempts` và không khai báo bất kỳ khóa dư nào, có thể không có unbound property để phát hiện.

Do đó cần tách hai yêu cầu:

1. **Không có khóa dư/sai tên:** sử dụng `ignoreUnknownFields=false` nếu phù hợp.
2. **Giá trị bắt buộc phải có và hợp lệ:** sử dụng validation, kiểu phù hợp và quy tắc rõ ràng.

Đặt `ignoreUnknownFields=false` không thay thế ràng buộc như số lần thử lại phải lớn hơn 0.

## 7. Unknown, missing và invalid: ba trạng thái khác nhau

Ba nhóm lỗi dễ bị lẫn:

### 7.1. Unknown property — khóa không có đích

```yaml
mailer:
  old-retry-setting: 3
```

Lớp không có trường `oldRetrySetting` hay cấu trúc nhận dữ liệu tương ứng. Đây là tình huống thuộc phạm vi `ignoreUnknownFields`.

### 7.2. Missing property — lớp mong đợi nhưng nguồn không cấp

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        String senderAddress
) {}
```

Nếu hoàn toàn không có `mailer.sender-address`, đây là **thuộc tính thiếu**. Không có khóa dư để `ignoreUnknownFields=false` bắt. Record có thể nhận `null` nếu không áp dụng yêu cầu khác.

Muốn bắt buộc sender address phải được cấp, dùng validation như `@NotBlank` hoặc một quy tắc kiểm tra rõ ràng.

### 7.3. Invalid property — khóa đúng nhưng giá trị không chuyển được

```yaml
mailer:
  max-attempts: many
```

Nếu record có `int maxAttempts`, đây là khóa **đúng tên**, nhưng giá trị `many` không phù hợp kiểu `int`. Thông thường, binding sẽ thất bại vì chuyển đổi kiểu, bất kể `ignoreUnknownFields` là `true` hay `false`.

Bảng phân biệt:

| Tình huống | Ví dụ | Cơ chế liên quan |
| --- | --- | --- |
| Khóa không có trường đích | `mailer.debug-mode` | `ignoreUnknownFields` |
| Khóa bắt buộc bị thiếu | Không có `mailer.sender-address` | Validation / kiểm tra điều kiện |
| Khóa có giá trị sai kiểu | `mailer.max-attempts=many` | Type conversion |
| Giá trị đúng kiểu nhưng vô lý | `mailer.max-attempts=-3` | Validation/ràng buộc nghiệp vụ |
| Khóa ngoài prefix được bind | `payment.debug-mode` khi bind `mailer` | Không thuộc phạm vi của `MailerProperties` |
| Khác biệt tên được relaxed binding hỗ trợ | `max-attempts` ↔ `maxAttempts` | Không phải unknown |

**Ý nghĩa của `ignoreUnknownFields` hẹp và cụ thể:** nó không phải công tắc “báo lỗi mọi cấu hình bất thường”.

## 8. So sánh ignoreUnknownFields và ignoreInvalidFields

`@ConfigurationProperties` có hai thuộc tính tên khá giống:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false,
        ignoreInvalidFields = false
)
```

Hai thuộc tính không đồng nghĩa:

- `ignoreUnknownFields`: xử lý những thuộc tính **không có đích liên kết** trong cấu trúc.
- `ignoreInvalidFields`: liên quan đến việc có bỏ qua những lỗi **không thể liên kết/convert giá trị** trong một số trường hợp hay không.

Mặc định thông dụng:

```text
ignoreUnknownFields = true
ignoreInvalidFields = false
```

Giả sử:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(
        int maxAttempts
) {}
```

Trường hợp A:

```properties
mailer.max-attempts=5
mailer.unknown-switch=on
```

`max-attempts` có đích; `unknown-switch` không có. `ignoreUnknownFields` là lựa chọn cần quan tâm.

Trường hợp B:

```properties
mailer.max-attempts=not-a-number
```

Khóa tồn tại và có đích `int maxAttempts`, nhưng không thể chuyển `not-a-number` sang số nguyên. Lỗi này thuộc về **conversion/binding invalid**, không tự được sửa bằng `ignoreUnknownFields=true`.

Đừng bật `ignoreInvalidFields=true` chỉ vì muốn ứng dụng luôn khởi động. Việc bỏ qua giá trị sai kiểu có thể khiến object ở trạng thái mặc định, thiếu dữ liệu hoặc khó xác định trong các cấu trúc khác nhau. Với dữ liệu quan trọng, **báo lỗi sớm** thường an toàn hơn.

Khi đang tìm hiểu một lỗi, hỏi theo thứ tự:

```text
1. Khóa có thuộc đúng prefix không?
2. Khóa có ánh xạ tới một trường/đường dẫn trong class không?
3. Nếu có, giá trị có chuyển đúng kiểu không?
4. Nếu chuyển được, giá trị có đạt ràng buộc nghiệp vụ không?
```

Mỗi câu hỏi tương ứng với một lớp kiểm tra khác nhau.

## 9. Strict mode chỉ kiểm tra trong phạm vi tiền tố được bind

Giả sử:

```java
@ConfigurationProperties(
        prefix = "mail",
        ignoreUnknownFields = false
)
public record MailProperties(
        String host,
        int port
) {}
```

Cấu hình:

```yaml
mail:
  host: smtp.example.invalid
  port: 2525

payment:
  endpoint: https://payments.example.invalid
  experimental-flag: true
```

`MailProperties` chỉ liên kết nhóm `mail`. Nó không có trách nhiệm nhận hoặc kiểm tra mọi khóa trong nhóm `payment`. Vì thế, strict mode của `MailProperties` không phải công cụ phát hiện lỗi ở `payment.experimental-flag`.

Để kiểm tra `payment`, cần có mô hình cấu hình và quy tắc tương ứng của chính nhóm đó, nếu nhóm thuộc về ứng dụng và thực sự cần strict binding.

Cũng nên hiểu rằng một ứng dụng Spring Boot có **rất nhiều nguồn cấu hình do framework và thư viện sử dụng**. Không hợp lý nếu một lớp `@ConfigurationProperties(prefix="mail")` làm nhiệm vụ xác thực mọi khóa bắt đầu bằng `server.`, `spring.` hoặc `management.`.

### Một prefix bị nhiều bean cùng dùng

Nếu hai bean cùng bind prefix `mail` nhưng chỉ nhận các tập con khác nhau, strict mode có thể trở thành vấn đề:

```java
@ConfigurationProperties(prefix = "mail", ignoreUnknownFields = false)
public record MailTransportProperties(String host, int port) {}

@ConfigurationProperties(prefix = "mail", ignoreUnknownFields = false)
public record MailPolicyProperties(int maxAttempts) {}
```

Trong YAML:

```yaml
mail:
  host: smtp.example.invalid
  port: 2525
  max-attempts: 4
```

Mỗi lớp chỉ có một phần các thuộc tính của cùng prefix. Nếu binder thực hiện kiểm tra unbound nghiêm ngặt cho từng bean, mỗi lớp có thể xem những khóa của lớp còn lại là không được liên kết.

Khi muốn tách trách nhiệm rõ, nên tách luôn prefix:

```yaml
mail:
  transport:
    host: smtp.example.invalid
    port: 2525
  policy:
    max-attempts: 4
```

```java
@ConfigurationProperties(
    prefix = "mail.transport",
    ignoreUnknownFields = false
)
public record MailTransportProperties(String host, int port) {}

@ConfigurationProperties(
    prefix = "mail.policy",
    ignoreUnknownFields = false
)
public record MailPolicyProperties(int maxAttempts) {}
```

Cách này giúp mỗi lớp có một hợp đồng cấu hình độc lập, tránh trường hợp strict mode xung đột với cách chia lớp.

## 10. Cấu hình lồng nhau và thuộc tính dư

Một thuộc tính không chỉ là trường ở cấp đầu tiên. Với nhóm cấu hình lồng nhau:

```yaml
transfer:
  endpoint:
    host: transfer.example.invalid
    port: 8443
    protocol: https
  retries: 3
```

Ta có thể dùng record lồng:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "transfer",
        ignoreUnknownFields = false
)
public record TransferProperties(
        Endpoint endpoint,
        int retries
) {
    public record Endpoint(
            String host,
            int port
    ) {}
}
```

Lớp `Endpoint` chỉ có `host` và `port`, không có `protocol`. Do đó, `transfer.endpoint.protocol` là ứng viên thuộc tính dư trong cấu trúc dưới prefix `transfer`.

Thêm trường tương ứng:

```java
public record Endpoint(
        String host,
        int port,
        String protocol
) {}
```

thì binder có một đích nhận `protocol`. Hoặc xóa khóa đó nếu không sử dụng. Nên quyết định dựa trên hợp đồng cấu hình, không thêm field chỉ để “làm hết lỗi” khi tính năng không cần giá trị đó.

### Đường dẫn sâu không đồng nghĩa với khóa lạ ở cấp gốc

Nếu record cấp gốc có `Endpoint endpoint`, không phải mọi khóa `transfer.endpoint.*` đều được chấp nhận vô điều kiện. Binder phải đi tiếp vào cấu trúc của `Endpoint` để xác định thuộc tính nào có đích.

Ngược lại, một field được thiết kế là `Map<String, String>` có thể nhận nhiều khóa động không cần khai báo sẵn từng tên trong lớp. Với cấu trúc dạng map, “khóa lạ” có thể là **dữ liệu hợp lệ** do mô hình đã cho phép tập tên mở.

## 11. Map, danh sách và mô hình có khóa động

Xét yêu cầu khai báo endpoint của nhiều vùng:

```yaml
regions:
  endpoints:
    ap-southeast-1: https://ap.example.invalid
    eu-west-1: https://eu.example.invalid
```

Một lớp thích hợp:

```java
import java.net.URI;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "regions",
        ignoreUnknownFields = false
)
public record RegionProperties(
        Map<String, URI> endpoints
) {}
```

Với `Map<String, URI>`, các tên vùng là **khóa dữ liệu**, không nhất thiết phải có trường Java `apSoutheast1` hay `euWest1`. Vì vậy, strict mode không thể được hiểu đơn giản là “chỉ cho phép tên khóa xuất hiện trong code Java theo từng đoạn đường dẫn”.

Nếu ứng dụng cần cấm một vùng không được hỗ trợ, hãy đặt tập tên hợp lệ trong một cơ chế kiểm tra riêng: enum, custom validator, danh sách cho phép hoặc quy tắc nghiệp vụ phù hợp.

Ví dụ, nếu cấu hình vô tình viết:

```yaml
regions:
  endpoints:
    ap-southeast-2: https://ap2.example.invalid
```

Binder có thể xem `ap-southeast-2` là một entry hợp lệ của map. `ignoreUnknownFields=false` không có nhiệm vụ xác thực rằng tên vùng đó có nằm trong danh sách vùng được doanh nghiệp chấp thuận hay không.

Tương tự, list có các chỉ số và phần tử riêng; không nên coi strict mode là bộ kiểm tra schema mạnh như JSON Schema cho mọi cấu trúc collection.

## 12. Cách dùng relaxed binding tránh kết luận nhầm

Spring Boot sử dụng relaxed binding để ánh xạ các cách đặt tên tương đương trong những nguồn phù hợp.

Ví dụ Java:

```java
@ConfigurationProperties(prefix = "order")
public record OrderProperties(
        int maxAttempts,
        boolean dryRun
) {}
```

Những dạng khóa có thể được Spring Boot nhận dạng tùy nguồn:

```text
order.max-attempts
order.maxAttempts
order.dry-run
order.dryRun
```

Khi dùng biến môi trường, Spring Boot có quy tắc tên riêng; ví dụ từ canonical `order.max-attempts` có thể ánh xạ tới biến `ORDER_MAXATTEMPTS` trong nguồn environment thông dụng. Không nên tùy tiện thêm dấu gạch dưới tại mọi vị trí và giả định tất cả hệ thống đều cho kết quả như nhau.

Khi chẩn đoán unbound property, nên:

1. Đọc tên khóa đang được cung cấp.
2. Đọc prefix và tên trường thực tế trong lớp.
3. Xem tên đó có phải chỉ là một biến thể được relaxed binding hỗ trợ hay không.
4. Nếu không, xác nhận đây là khóa mới, khóa cũ chưa xóa hay lỗi gõ sai.

Ví dụ `order.max-attemtps` là lỗi đảo ký tự; nó không phải một kiểu đặt tên tương đương của `order.maxAttempts`.

Bật strict mode thường có ích khi nhóm muốn chống những lỗi chính tả như vậy ngay trong quá trình khởi động.

## 13. Test tự động: bắt lỗi khóa dư bằng ApplicationContextRunner

Ngoài chạy JAR bằng tay, có thể kiểm tra quy tắc binding bằng Spring Boot Test. `ApplicationContextRunner` cho phép tạo một application context nhỏ với tập property do test chủ động cung cấp.

Giả sử có:

```java
package com.example.unknown;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Một lớp test:

```java
package com.example.unknown;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.context.PropertyPlaceholderAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class MailerPropertiesTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(PropertiesTestConfig.class);

    @Test
    void bindsKnownProperties() {
        contextRunner
            .withPropertyValues(
                "mailer.enabled=true",
                "mailer.max-attempts=4"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                MailerProperties properties =
                    context.getBean(MailerProperties.class);
                assertThat(properties.maxAttempts()).isEqualTo(4);
            });
    }

    @Test
    void rejectsUnknownPropertyWhenStrict() {
        contextRunner
            .withPropertyValues(
                "mailer.enabled=true",
                "mailer.max-attempts=4",
                "mailer.trace-mode=verbose"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(MailerProperties.class)
    static class PropertiesTestConfig {
    }
}
```

Test cần dependency `spring-boot-starter-test` (bao gồm các công cụ test cần thiết). `PropertyPlaceholderAutoConfiguration` được import trong ví dụ nhưng không bắt buộc để thể hiện phép kiểm tra ở đây; có thể bỏ import đó nếu IDE cảnh báo không dùng.

Điều test chứng minh:

- Khi chỉ có khóa phù hợp, bean được tạo và có giá trị mong đợi.
- Khi có khóa không được ánh xạ với `ignoreUnknownFields=false`, context có thể không khởi động.
- Không cần xây một ứng dụng lớn hoặc gọi mạng thật để chứng minh khác biệt của annotation.

Đây là một test **binding contract**. Nó không kiểm tra logic nghiệp vụ của mailer hoặc nội dung email.

### Test riêng cho chế độ mặc định

Để kiểm chứng chế độ khoan dung, đổi annotation trong một kiểu test khác thành:

```java
@ConfigurationProperties(prefix = "mailer")
public record LenientMailerProperties(
        boolean enabled,
        int maxAttempts
) {}
```

Đăng ký kiểu này trong context test riêng. Với các giá trị `mailer.enabled=true`, `mailer.max-attempts=4`, `mailer.trace-mode=verbose`, binder có thể tạo thành công đối tượng và bỏ qua khóa dư.

Không nên đồng thời đăng ký hai record khác nhau cùng prefix trong một test nếu mục đích chỉ là so sánh hành vi từng class; mỗi test nên chỉ bật một contract để kết quả rõ ràng.

## 14. Strict mode có bắt tất cả cấu hình không dùng không?

Không nên hiểu `ignoreUnknownFields=false` là một bộ lint tĩnh toàn bộ file YAML.

Có một số giới hạn cần nhận thức:

- Nó áp dụng khi một **đối tượng `@ConfigurationProperties` thực sự được bind**. Nếu class chưa đăng ký, không có lần binding nào cho nó để phát hiện khóa dư.
- Phạm vi là **prefix của đối tượng đích**, không phải mọi prefix trong `Environment`.
- Các nguồn cấu hình khác nhau có cách cung cấp và liệt kê thuộc tính khác nhau; không nên giả định mọi biến thể khóa từ mọi nguồn ngoài đều bị kiểm tra giống hệt.
- Cấu trúc mở như `Map` cho phép nhiều khóa động và có thể tiêu thụ chúng hợp lệ.
- Một thuộc tính có thể được một bean khác xử lý riêng, ngay cả khi không có đích trong bean đang xét.
- Không có khẳng định rằng việc thiếu một khóa bắt buộc sẽ tự bị phát hiện chỉ nhờ strict mode.
- Không có khẳng định rằng giá trị hợp lệ về cú pháp sẽ phù hợp nghiệp vụ.

Vì vậy, nên kết hợp:

```text
strict binding           -> hạn chế khóa dư/khóa viết nhầm
type conversion          -> chặn dữ liệu sai kiểu
Bean Validation          -> kiểm tra khóa bắt buộc / phạm vi giá trị
tests                    -> xác nhận contract dưới từng nguồn cấu hình
code review / docs       -> làm rõ tên khóa được hỗ trợ
```

Đây là các lớp phòng vệ bổ sung cho nhau, không phải những cách thay thế cùng một mục tiêu.

## 15. Kết hợp ignoreUnknownFields với validation

Giả sử một cấu hình phải có endpoint HTTPS, timeout dương và số lần thử lại tối thiểu là 1.

Lớp record có thể bắt đầu bằng:

```java
package com.example.unknown;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "gateway",
        ignoreUnknownFields = false
)
public record GatewayProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts
) {}
```

Ví dụ YAML:

```yaml
gateway:
  endpoint: https://gateway.example.invalid/api/
  timeout: 3s
  max-attempts: 4
```

Khi có dependency validation phù hợp, chẳng hạn `spring-boot-starter-validation`:

- Nếu YAML có `gateway.timeot: 3s` thay vì `gateway.timeout`, strict binding có thể phát hiện khóa `timeot` không ánh xạ được.
- Nếu hoàn toàn không có `gateway.timeout`, ràng buộc `@NotNull` giúp phát hiện giá trị bắt buộc bị thiếu.
- Nếu `gateway.max-attempts=0`, `@Min(1)` giúp phát hiện giá trị ngoài phạm vi.
- Nếu `gateway.max-attempts=abc`, conversion sang `int` có thể thất bại trước khi validation có thể coi đây là số hợp lệ.

Đây là cách thiết kế giúp **lỗi cấu hình bộc lộ lúc khởi động**, thay vì đợi đến khi một request quan trọng sử dụng trường sai.

### Đừng coi @NotNull(URI) là xác thực HTTPS

`URI` có thể biểu diễn nhiều dạng URI, kể cả những URI không dùng HTTPS. `@NotNull` chỉ yêu cầu không null. Nếu quy tắc nghiệp vụ yêu cầu HTTPS hoặc host thuộc danh sách cho phép, cần custom validation phù hợp.

Tương tự, `Duration` có thể biểu diễn số âm hoặc zero; `@NotNull` chưa bảo đảm timeout phải dương. Có thể dùng kiểm tra riêng hoặc ràng buộc phù hợp với cách thiết kế.

## 16. Nên đặt ignoreUnknownFields = false khi nào?

Chế độ nghiêm ngặt hữu ích nhất khi một nhóm cấu hình được định nghĩa như **hợp đồng hoàn chỉnh**, thuộc quyền kiểm soát của một ứng dụng hoặc một module.

Ví dụ:

- `billing.*` chứa những tham số được vận hành theo quy định, sai tên khóa có thể dẫn đến quyết định thanh toán không mong muốn.
- `shipping.*` là một object cấu hình độc lập, mọi khóa của nhóm đều được mô hình hóa trong lớp properties.
- Một thư viện nội bộ cung cấp cấu hình public có danh sách khóa được hỗ trợ rõ ràng và muốn fail fast khi xuất hiện khóa cũ sau nâng cấp.
- Một dịch vụ cần xác nhận cấu hình deployment tương ứng với phiên bản mã hiện hành.

Trong những tình huống đó, ưu điểm:

1. Phát hiện lỗi gõ sai sớm.
2. Ngăn cấu hình lỗi thời tồn tại mà không được chú ý.
3. Khi thay đổi tên trường, buộc các tệp cấu hình liên quan phải được cập nhật.
4. Tạo tín hiệu rõ cho pipeline kiểm thử hoặc deployment.
5. Giúp quản lý một hợp đồng cấu hình có giới hạn và được tài liệu hóa.

Tuy nhiên, strict mode có thể gây bất tiện khi một prefix **được cố tình chia sẻ** cho nhiều người tiêu thụ hoặc có những khóa không thể liệt kê trước. Với thiết kế đó, nên xem lại ranh giới prefix hoặc kiểu dữ liệu hơn là bật strict ở mọi nơi.

## 17. Khi nào nên giữ mặc định true?

Chế độ khoan dung phù hợp khi mục tiêu là **đọc một tập con cấu hình** mà không sở hữu toàn bộ không gian khóa.

Ví dụ:

- Một module chỉ quan tâm vài thuộc tính của một prefix dùng chung.
- Nguồn cấu hình chứa khóa bổ sung dành cho thành phần triển khai khác.
- Mô hình cấu hình được phát triển dần và cần tương thích với một số phiên bản source cũ.
- Một integration cần đọc một subset có kiểu của dữ liệu mà những phần khác được xử lý bằng cách khác.

Mặt trái: khó phát hiện khóa thừa hoặc tên bị viết sai chỉ từ việc ứng dụng khởi động thành công.

Để giảm rủi ro, có thể:

- Tạo prefix riêng rõ ràng cho từng nhóm properties.
- Dùng annotation validation cho trường bắt buộc.
- Viết integration test bind các file cấu hình được hỗ trợ.
- Có tài liệu mô tả tập khóa cho từng module.
- Tận dụng metadata hỗ trợ IDE gợi ý tên thuộc tính.

Điểm quan trọng là **chọn dựa trên hợp đồng cấu hình**. `true` không phải luôn sai; `false` cũng không phải luôn đúng.

## 18. Tác động khi nâng cấp phiên bản hoặc đổi tên thuộc tính

Giả sử phiên bản đầu của ứng dụng dùng:

```yaml
mailer:
  retry-count: 3
```

Và Java:

```java
@ConfigurationProperties(prefix = "mailer")
public record MailerProperties(int retryCount) {}
```

Ở phiên bản sau, nhóm đổi tên thành `max-attempts`:

```java
@ConfigurationProperties(
        prefix = "mailer",
        ignoreUnknownFields = false
)
public record MailerProperties(int maxAttempts) {}
```

Nếu deployment vẫn giữ khóa cũ `mailer.retry-count`, strict mode có thể làm ứng dụng dừng khởi động và chỉ rõ khóa cũ chưa được cập nhật.

Với mặc định `true`, khóa cũ có thể bị bỏ qua; `maxAttempts` không có giá trị tường minh và có thể nhận giá trị thiếu hoặc mặc định không phù hợp. Đây là trường hợp strict mode mang lại lợi ích vận hành đáng kể.

Nhưng nếu cần giai đoạn chuyển tiếp hỗ trợ **cả hai tên khóa**, không nên đơn giản bật strict rồi cấm deployment cũ. Cần có một **kế hoạch migration có chủ đích**, ví dụ:

- Tạm thời chấp nhận hai khóa qua một mô hình cấu hình chuyển tiếp phù hợp.
- Đánh dấu tên cũ deprecated trong tài liệu/metadata nếu có cơ chế hỗ trợ.
- Cập nhật tệp cấu hình và hệ thống triển khai.
- Loại bỏ tên cũ khi hết thời gian tương thích.
- Bật strict mode theo phạm vi sẵn sàng, không bất ngờ làm hỏng mọi triển khai.

Không tự suy luận Spring Boot sẽ chuyển mọi tên cũ sang tên mới. Relaxed binding hỗ trợ **biến thể cách viết của một tên thuộc tính**, không phải mọi lần đổi tên có ý nghĩa giữa các phiên bản.

## 19. Metadata cấu hình hỗ trợ phát hiện lỗi từ sớm

Spring Boot có annotation processor hỗ trợ sinh metadata cho `@ConfigurationProperties`. Khi dự án dùng `spring-boot-configuration-processor`, IDE có thể dựa trên metadata để gợi ý tên thuộc tính, kiểu dữ liệu và mô tả của chúng.

Ví dụ, khi gõ:

```yaml
mailer:
  max-attempts:
```

IDE có thể gợi ý `max-attempts` nếu metadata của `MailerProperties` được sinh và IDE hỗ trợ. Điều này giúp giảm trường hợp viết `max-atempt` hoặc `retry-cout`.

Tuy nhiên, có khác biệt:

- **Metadata/IDE:** hỗ trợ người viết cấu hình trong quá trình phát triển; mức cảnh báo tùy IDE và build.
- **`ignoreUnknownFields=false`:** ảnh hưởng hành vi runtime binding của lớp properties.
- **Validation:** kiểm tra giá trị theo quy tắc kiểu và nghiệp vụ.

Không dùng metadata làm bằng chứng chắc chắn rằng ứng dụng đã kiểm tra mọi file và mọi thuộc tính khi chạy. Chúng là các công cụ bổ sung, hoạt động ở những giai đoạn khác nhau.

## 20. Đọc lỗi unbound và xác định nguyên nhân

Khi ứng dụng báo lỗi binding và có phần tử unbound, nên phân tích theo từng bước thay vì vội tắt strict mode.

### Bước 1: xác định bean và prefix

Lỗi thuộc `MailerProperties` với prefix `mailer` hay thuộc một lớp khác? Kiểm tra annotation:

```java
@ConfigurationProperties(
    prefix = "mailer",
    ignoreUnknownFields = false
)
```

### Bước 2: tìm khóa cụ thể

Giả sử thông báo nhắc `mailer.trace-mode`. Đọc đúng khóa này trong nguồn cấu hình được cung cấp. Nó có thể xuất hiện ở YAML, properties, biến môi trường hoặc tham số dòng lệnh tùy nguồn.

### Bước 3: so với cấu trúc lớp Java

Lớp có `traceMode` không? Có cấu trúc lồng nhau hoặc map tiêu thụ nó không? Nếu khóa là lỗi gõ, sửa về tên canonical phù hợp.

### Bước 4: kiểm tra nguồn ưu tiên

Một giá trị có thể tồn tại trong nhiều nguồn. Khi chẩn đoán, cần ghi nhận nguồn nào đang khai báo khóa và thứ tự ưu tiên. Đừng chỉ mở một file YAML rồi cho rằng đó là toàn bộ cấu hình của tiến trình.

### Bước 5: quyết định sửa file hay sửa class

Nếu khóa dư không còn được dùng: loại bỏ khỏi cấu hình.

Nếu khóa là yêu cầu mới: bổ sung một field có kiểu phù hợp, đồng thời xây logic sử dụng và validation cần thiết.

Nếu đây là khóa thuộc miền khác: tách prefix để các binder không chồng chéo.

Nếu prefix được thiết kế chia sẻ: xem xét liệu strict mode có phù hợp với phạm vi sử dụng không.

### Bước 6: chạy lại một lần khởi động sạch

Sau khi thay YAML hoặc class, đóng gói lại khi cần và khởi động một tiến trình mới. Đừng chờ Spring tự bind lại record đã tạo khi file được chỉnh lúc ứng dụng đang chạy.

### Vì sao không nên sửa ngay thành ignoreUnknownFields = true?

Đổi `false` thành `true` có thể che lỗi chính tả và khiến ứng dụng khởi động dù ý định cấu hình chưa được thực hiện. Nếu thật sự muốn thay đổi chính sách chấp nhận khóa dư, hãy ghi rõ lý do thiết kế thay vì coi việc tắt strict là cách sửa mọi lỗi.

## 21. Một số câu hỏi cần tránh hiểu sai

### “Bật false thì mọi khóa trong file YAML đều phải có trường?”

Không. Chỉ xét **phạm vi prefix và quá trình binding của object được đăng ký**. Một file có nhiều nhóm `server.*`, `spring.*` và `mailer.*` là bình thường.

### “Nếu thiếu một field trong YAML, strict mode sẽ phát hiện?”

Không nhất thiết. Đây là **missing property**, không phải unknown property. Muốn bắt buộc phải có một giá trị, hãy dùng validation hoặc cơ chế hợp đồng khác.

### “Nếu YAML chứa chữ thay vì int, true có bỏ qua không?”

`ignoreUnknownFields=true` không phải cơ chế bỏ qua lỗi đổi kiểu. Sai kiểu là vấn đề của type conversion; có thuộc tính `ignoreInvalidFields` riêng và phải cân nhắc hậu quả nếu sử dụng.

### “Dấu gạch ngang khiến tên khóa thành unknown?”

Không nhất thiết. Spring Boot hỗ trợ relaxed binding giữa cách viết kiểu `max-attempts` và thành phần Java `maxAttempts` theo quy tắc phù hợp.

### “Có thể dùng false như bộ lọc an ninh cho mọi biến môi trường?”

Không. Nó không phải firewall cấu hình hoặc bộ lọc secret. Những nguồn và cấu trúc được bind có giới hạn; chính sách bảo mật phải dùng các cơ chế bảo vệ riêng.

### “Bật false có làm mọi giá trị không dùng bị xóa khỏi Environment?”

Không. Việc kiểm tra unbound liên quan đến tính toàn vẹn binding của bean; nó không phải lệnh thay đổi dữ liệu gốc của các `PropertySource`.

### “Một khóa bên trong Map có bị coi là unknown?”

Không thể kết luận chỉ từ việc tên khóa không xuất hiện dưới dạng trường Java. `Map<String, ...>` được thiết kế để tiếp nhận những khóa dữ liệu động.

## 22. Bài tập thực hành

### Bài tập 1: dự đoán hành vi

Cho record:

```java
@ConfigurationProperties(prefix = "queue")
public record QueueProperties(
        String name,
        int capacity
) {}
```

Và cấu hình:

```yaml
queue:
  name: inbound
  capacity: 100
  durable: true
```

Câu hỏi:

1. `queue.durable` có đích nhận trong record không?
2. Với annotation như trên, ứng dụng có thể tiếp tục khởi động không?
3. Nếu thêm `ignoreUnknownFields=false` thì có thể xảy ra lỗi gì?
4. Nếu thêm trường `boolean durable`, tình hình thay đổi như thế nào?

### Bài tập 2: phân biệt thiếu và sai tên

Lớp:

```java
@ConfigurationProperties(
    prefix = "cache",
    ignoreUnknownFields = false
)
public record CacheProperties(
        String host,
        int port
) {}
```

So sánh hai tệp:

```yaml
# Tệp A: hoàn toàn không khai báo port
cache:
  host: localhost
```

```yaml
# Tệp B: khai báo sai tên
cache:
  host: localhost
  prot: 6379
```

Tại sao A và B không được xử lý cùng một cách? Chế độ strict có thể phát hiện `prot`, trong khi việc buộc phải có `port` cần một ràng buộc riêng.

### Bài tập 3: giá trị sai kiểu

```yaml
cache:
  host: localhost
  port: seven
```

Giải thích vì sao `ignoreUnknownFields=true` không tự biến `seven` thành giá trị mặc định. Đây là khóa đúng tên nhưng không chuyển được sang `int`.

### Bài tập 4: thuộc tính lồng

```java
@ConfigurationProperties(
    prefix = "storage",
    ignoreUnknownFields = false
)
public record StorageProperties(
        Connection connection
) {
    public record Connection(
            String host,
            int port
    ) {}
}
```

```yaml
storage:
  connection:
    host: storage.example.invalid
    port: 9000
    secure: true
```

Xác định khóa nào chưa có đích nhận. Sau đó đề xuất sửa: thêm `boolean secure` nếu có ý nghĩa hoặc xóa khóa khỏi nguồn nếu không dùng.

### Bài tập 5: tổ chức prefix độc lập

Một ứng dụng có `AuditProperties` và `AuditSinkProperties` cùng đọc prefix `audit`. Cả hai bật strict mode và mỗi lớp chỉ nhận một tập con. Hãy thiết kế lại thành `audit.policy.*` và `audit.sink.*` để các nhóm tách biệt, tránh xung đột do những thuộc tính thuộc lớp còn lại.

### Bài tập 6: viết test hợp đồng

Từ `ApplicationContextRunner`, viết hai test:

- Dữ liệu chỉ có khóa hợp lệ phải bind thành công.
- Dữ liệu có thêm `mailer.trace-mode` phải gây startup failure khi `ignoreUnknownFields=false`.

Sau đó tạo một phiên bản lenient cùng prefix nhưng đăng ký ở context riêng và quan sát sự khác biệt.

### Bài tập 7: migration tên khóa

Giả sử phiên bản cũ dùng `retry-count`, phiên bản mới dùng `max-attempts`. Hãy lập kế hoạch cập nhật deployment và test để tránh việc bật strict mode làm đứt triển khai đang dùng khóa cũ.

## 23. Tổng kết

`ignoreUnknownFields` xác định chính sách xử lý **những thuộc tính trong phạm vi binding không có đích tương ứng trong lớp `@ConfigurationProperties`**.

```text
@ConfigurationProperties(prefix = "mailer")
          |
          v
      Cấu hình mailer.*
          |
          v
          Binder
          |
     +----+----+
     |         |
 Có đích    Không có đích
     |         |
     v         v
  Bind      ignoreUnknownFields
                 |
            +----+----+
            |         |
          true      false
            |         |
       Bỏ qua     Báo unbound
```

Những điều cần nhớ:

1. **Mặc định `ignoreUnknownFields=true`**, nên khóa dư có thể bị bỏ qua.
2. **`ignoreUnknownFields=false`** giúp phát hiện khóa không được liên kết và có thể làm ứng dụng dừng khởi động.
3. **Unknown không phải missing.** Thuộc tính bắt buộc bị thiếu cần validation, không chỉ strict mode.
4. **Unknown không phải invalid.** Giá trị sai kiểu do cơ chế chuyển đổi và binding xử lý.
5. **Strict mode không kiểm tra toàn bộ `Environment`**; nó hoạt động trong phạm vi object/prefix được bind, với những giới hạn của nguồn và mô hình dữ liệu.
6. **Các prefix có phạm vi rõ ràng** giúp strict mode đáng tin và giảm xung đột giữa nhiều bean cấu hình.
7. **Validation và test** hoàn thiện hợp đồng: không chỉ đúng tên khóa, mà còn đủ giá trị và phù hợp nghiệp vụ.

Với một nhóm cấu hình sở hữu riêng, được quản lý chặt chẽ và ít khóa động, `ignoreUnknownFields=false` có thể là một cách **phát hiện sớm lỗi gõ tên và cấu hình cũ**. Với một prefix được cố ý dùng chung hoặc mô hình có tập tên mở, giữ chế độ mặc định có thể phù hợp hơn, kèm validation và tài liệu rõ ràng.

Tài liệu tham khảo: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html), và [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).