# Phát hiện khóa viết sai thay vì bỏ qua âm thầm

## 1. Bài toán: ứng dụng khởi động nhưng cấu hình không đúng

Trong Spring Boot Externalized Configuration, cấu hình thường được đặt trong `application.yml`, `application.properties`, biến môi trường hoặc đối số dòng lệnh. Khi số lượng thuộc tính tăng, một lỗi đánh máy nhỏ có thể khiến ứng dụng nhận **giá trị mặc định** thay vì giá trị người vận hành mong muốn.

Giả sử dịch vụ gửi thông báo có cấu hình:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 5
  connect-timeout: 4s
```

Lớp Java mong muốn liên kết thuộc tính `notification.retry-count`. Nếu người viết YAML vô tình gõ:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retrty-count: 5       # LỖI: dư chữ t
  connect-timeout: 4s
```

thì `notification.retrty-count` **không phải** `notification.retry-count`. Tùy cấu hình binder và giá trị dự phòng, Spring Boot có thể bỏ qua khóa không được nhận diện, trong khi ứng dụng vẫn khởi động bình thường.

Đây là tình huống nguy hiểm vì log có thể không có thông báo rõ ràng, còn tính năng thử lại chạy ít hơn dự định. Với timeout, giới hạn truy cập hoặc các thông số quan trọng khác, một lỗi kiểu này có thể tạo ra hành vi khó chẩn đoán.

**Mục tiêu bài học:** hiểu cách yêu cầu Spring Boot phát hiện những khóa cấu hình không thể liên kết, cách phân biệt lỗi tên khóa với lỗi kiểu dữ liệu, và giới hạn của việc kiểm tra nghiêm ngặt.

## 2. Vì sao khóa không được nhận diện có thể bị bỏ qua?

Spring Boot dùng **Configuration Properties Binder** để ánh xạ các thuộc tính cấu hình sang bean có `@ConfigurationProperties`. Binder tìm các giá trị thuộc một tiền tố, ví dụ `notification`, rồi ánh xạ những tên hợp lệ sang field hoặc tham số constructor.

Ví dụ:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        String endpoint,
        int retryCount,
        java.time.Duration connectTimeout) {
}
```

Các tên liên kết mong đợi gồm:

| Tên thuộc tính chuẩn | Thành phần Java | Kiểu Java |
| --- | --- | --- |
| `notification.endpoint` | `endpoint` | `String` |
| `notification.retry-count` | `retryCount` | `int` |
| `notification.connect-timeout` | `connectTimeout` | `Duration` |

Nếu xuất hiện `notification.retrty-count`, binder không tự hiểu đây là cách viết khác của `retry-count`; đó là tên khác.

Thuộc tính `@ConfigurationProperties` có tùy chọn:

```java
ignoreUnknownFields
```

Mặc định của tùy chọn này là **`true`**. Nghĩa là trong quy trình binding thông thường, các trường cấu hình mà binder coi là không có đích liên kết tương ứng có thể được **bỏ qua**, thay vì bắt buộc khởi động thất bại.

Điều này hỗ trợ tương thích với nguồn cấu hình chứa nhiều khóa hoặc các phần mở rộng không có trong một bean. Nhưng với cấu hình quan trọng do ứng dụng sở hữu, bỏ qua âm thầm có thể che giấu lỗi gõ tên.

## 3. Bật chế độ không bỏ qua khóa lạ

Để yêu cầu binder phát hiện các thuộc tính chưa được liên kết trong phạm vi bean, đặt:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
```

Ví dụ record đầy đủ:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        String endpoint,
        int retryCount,
        Duration connectTimeout) {
}
```

Với YAML đúng:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 5
  connect-timeout: 4s
```

binder có thể liên kết ba thuộc tính với ba thành phần của record. Khi mã Java và các nguồn cấu hình khác đều phù hợp, bean được tạo thành công.

Với YAML có khóa sai:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retrty-count: 5
  connect-timeout: 4s
```

binder có thể nhận diện `notification.retrty-count` là một thuộc tính dưới tiền tố `notification` nhưng **không được liên kết** với thành phần nào. Khi chế độ bỏ qua khóa lạ bị tắt, việc tạo bean có thể thất bại, và thông tin lỗi chỉ ra khóa chưa được liên kết.

Tùy phiên bản Spring Boot và đường đi của binding, log có thể chứa thông báo dạng **“The elements ... were left unbound”**, đồng thời có ngoại lệ binding liên quan như `UnboundConfigurationPropertiesException` hoặc `ConfigurationPropertiesBindException` trong chuỗi nguyên nhân. Không nên viết xử lý phụ thuộc vào toàn văn một thông báo lỗi vì cấu trúc và cách trình bày log có thể thay đổi.

**Lưu ý về phạm vi:** chế độ này kiểm tra những thuộc tính mà binder thấy khi liên kết **bean cấu hình được đăng ký**. Đây không phải cơ chế tự động soát toàn bộ khóa của mọi nguồn cấu hình trên hệ thống.

## 4. Ví dụ chạy được với Spring Boot

Các ví dụ dùng Java 17 trở lên và kiểu đăng ký `@ConfigurationProperties` quen thuộc của Spring Boot 3.x.

### 4.1. Tệp cấu hình

Tạo `src/main/resources/application.yml`:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3
  connect-timeout: 5s
```

### 4.2. Lớp Configuration Properties

Tạo `NotificationProperties.java`:

```java
package com.example.configdemo;

import java.time.Duration;
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        URI endpoint,
        int retryCount,
        Duration connectTimeout) {
}
```

Dùng kiểu `URI` giúp mô tả rõ dữ liệu của `endpoint`; dùng `Duration` giúp chương trình xử lý thời gian thay vì tự parse chuỗi `"5s"`.

### 4.3. Đăng ký bean để binder thực sự chạy

Trong lớp khởi động:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` quét các kiểu cấu hình trong package thích hợp rồi đăng ký chúng thành bean.

Một lựa chọn khác là dùng:

```java
@EnableConfigurationProperties(NotificationProperties.class)
```

trên lớp cấu hình, với import `org.springframework.boot.context.properties.EnableConfigurationProperties`. Chỉ cần một cách đăng ký phù hợp, không cần gắn thêm `@Component` lên record với mục tiêu constructor binding.

**Nếu bean không hề được đăng ký**, không có quá trình binding của bean đó để phát hiện khóa lạ. Đây là một trong những giới hạn thường bị bỏ qua khi chẩn đoán.

### 4.4. Quan sát giá trị ở service

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class NotificationPrinter implements ApplicationRunner {

    private final NotificationProperties properties;

    public NotificationPrinter(NotificationProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("endpoint = " + properties.endpoint());
        System.out.println("retryCount = " + properties.retryCount());
        System.out.println(
                "connectTimeout = " + properties.connectTimeout());
    }
}
```

Khi cấu hình hợp lệ, kết quả minh họa:

```text
endpoint = https://notify.example.invalid
retryCount = 3
connectTimeout = PT5S
```

Nếu đổi `retry-count` thành `retrty-count` và khởi động lại, ta mong chế độ liên kết nghiêm ngặt **không chấp nhận một khóa lạ thuộc phạm vi của bean**. Thay vì chỉ in các giá trị sai, ứng dụng có thể dừng trong quá trình tạo context và hiển thị lỗi binding.

## 5. Vì sao một khóa sai đôi khi không gây lỗi?

Không phải mọi lỗi trong tệp cấu hình đều được `ignoreUnknownFields = false` phát hiện. Cần phân biệt các trường hợp.

### 5.1. Khóa sai ngay trong tiền tố được bind

Ví dụ bean có `prefix = "notification"` và nhận `retryCount`, nhưng nguồn chứa:

```properties
notification.retrty-count=3
```

Đây là trường hợp điển hình mà cơ chế không bỏ qua thuộc tính lạ nhằm phát hiện.

### 5.2. Sai chính tiền tố

Bean mong đợi `notification.*` nhưng cấu hình lại là:

```properties
notificaton.retry-count=3
```

Dấu hiệu sai nằm ở **tiền tố** `notificaton`. Binder đang liên kết prefix `notification` có thể không nhìn thấy thuộc tính bên ngoài tiền tố đó. Vì vậy chỉ đặt `ignoreUnknownFields = false` **không bảo đảm phát hiện mọi lỗi gõ ở cấp prefix**.

Để chống thiếu toàn bộ nhóm cấu hình, cần thêm các ràng buộc bắt buộc cho những giá trị chủ chốt hoặc kiểm thử cấu hình theo từng môi trường.

### 5.3. Khóa nằm ngoài nhóm được kiểm soát

Bean `NotificationProperties` không nên gây lỗi chỉ vì tệp còn có:

```yaml
server:
  port: 8080

logging:
  level:
    root: INFO

notification:
  retry-count: 3
```

Các khóa `server.*` và `logging.*` thuộc phạm vi cấu hình khác, không phải những trường lạ dưới `notification` của bean.

### 5.4. Lớp không được đăng ký

Nếu không dùng `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế tương đương, bean có thể không tồn tại. Không có quá trình liên kết bean thì cũng không có phép phát hiện khóa chưa được liên kết của bean ấy.

### 5.5. Nguồn cấu hình không được nạp

Nếu sửa một tệp không tham gia Config Data, chẳng hạn `application-stage.yml` khi profile `stage` không hoạt động, binder không thể phát hiện lỗi trong một tệp mà nó chưa đọc.

Vì thế, “đã bật strict binding nhưng không báo lỗi” không tự chứng minh cấu hình đúng. Hãy kiểm tra **tệp đã được nạp chưa, bean đã được đăng ký chưa và khóa có nằm trong prefix đang liên kết không**.

## 6. Giá trị mặc định có thể che giấu lỗi đánh máy

Xét record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @DefaultValue("3") int retryCount) {
}
```

Với cấu hình:

```yaml
notification:
  retrty-count: 8
```

Tên khóa `retrty-count` sai. Binder không tìm thấy `retry-count`, vì vậy có thể sử dụng `@DefaultValue("3")`. Ứng dụng chạy với `retryCount=3`, dù người cấu hình tưởng rằng đã đặt `8`.

Đây là ví dụ về lỗi **im lặng về mặt chức năng**: tính năng vẫn chạy, nhưng dùng một giá trị khác dự định.

Nếu đổi annotation thành:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        @DefaultValue("3") int retryCount) {
}
```

thì khóa `notification.retrty-count` có thể bị báo là chưa được liên kết trong phạm vi bean, thay vì bị chấp nhận như một thành viên vô nghĩa của nhóm cấu hình.

**Mặc định có giá trị sử dụng riêng, còn strict binding có giá trị kiểm soát đầu vào riêng.** Hai công cụ không thay thế cho nhau. Giá trị mặc định hợp lý là tốt; phát hiện lỗi tên khóa giúp chắc rằng người dùng cấu hình đúng ý định.

## 7. Phân biệt khóa lạ với giá trị sai kiểu

Đây là hai nhóm lỗi khác nhau.

### 7.1. Unknown field: tên khóa không được nhận diện

Bean:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(int retryCount) {
}
```

YAML:

```yaml
notification:
  retry-coutn: 4
```

`retry-coutn` là khóa lạ so với `retryCount`.

### 7.2. Invalid field: tên đúng nhưng giá trị không chuyển đổi được

YAML:

```yaml
notification:
  retry-count: many
```

Ở đây `retry-count` là **tên đúng**, nhưng `many` không thể chuyển thành `int` theo quy tắc thông thường.

Spring Boot cung cấp tùy chọn `ignoreInvalidFields` trên `@ConfigurationProperties`. Mặc định giá trị của nó là **`false`**, tức là lỗi chuyển đổi kiểu không được bỏ qua theo cách mặc định.

So sánh:

| Tình huống | Ví dụ | Loại lỗi |
| --- | --- | --- |
| Sai tên khóa | `retry-coutn=4` | Unknown / unbound property |
| Giá trị không chuyển kiểu | `retry-count=many` | Binding/conversion failure |
| Thiếu khóa | Không có `retry-count` | Missing configuration |
| Có khóa nhưng không hợp lệ theo nghiệp vụ | `retry-count=-4` | Validation/business constraint |
| Sai tiền tố | `notificaton.retry-count=4` | Có thể không thuộc phạm vi bean được bind |

Tùy chọn `ignoreUnknownFields = false` nhằm kiểm soát khóa **chưa được liên kết**, không phải là trình xác thực duy nhất cho tất cả những lỗi trên.

**Không khuyến khích dùng `ignoreInvalidFields = true` để né lỗi chuyển đổi kiểu** đối với cấu hình quan trọng, vì ứng dụng có thể tiếp tục chạy mà không nhận đúng giá trị.

## 8. Thêm validation để phát hiện cấu hình bị thiếu hoặc sai miền

Ngay cả khi tên khóa đều hợp lệ, các giá trị có thể không đáp ứng yêu cầu nghiệp vụ.

Ví dụ, `retry-count=0` có thể chuyển thành `int` bình thường nhưng không hợp lệ nếu hệ thống yêu cầu số lần thử lớn hơn hoặc bằng 1.

Với Spring Boot 3.x và Jakarta Validation, có thể dùng:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        @NotNull URI endpoint,
        @Min(1) int retryCount,
        @NotNull Duration connectTimeout) {
}
```

Ở đây:

- `ignoreUnknownFields = false` giúp phát hiện các khóa không được binder liên kết trong phạm vi nhóm.
- `@NotNull` yêu cầu `endpoint` và `connectTimeout` không thiếu.
- `@Min(1)` yêu cầu `retryCount` ít nhất là 1.
- `@Validated` yêu cầu thực hiện validation cho bean cấu hình.

Để dùng Jakarta Bean Validation trong một dự án Spring Boot thông thường, thêm dependency `spring-boot-starter-validation`.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Các ràng buộc validation giúp phát hiện thiếu giá trị hoặc giá trị không hợp lệ, kể cả khi lỗi đánh máy xảy ra **ở cấp prefix** và không bị phép kiểm tra khóa lạ bắt được.

Ví dụ `notification.endpoint` không xuất hiện vì người dùng gõ `notificaton.endpoint`, binder có thể để thành phần `endpoint` là `null`. `@NotNull` bảo vệ yêu cầu bắt buộc này.

**Công thức thực hành cho cấu hình quan trọng: kiểm soát khóa lạ + kiểm tra kiểu + validation giá trị bắt buộc.**

## 9. Relaxed binding không đồng nghĩa với bỏ qua lỗi chính tả

Spring Boot hỗ trợ **relaxed binding**, cho phép nhiều cách viết hợp lệ ánh xạ về cùng một thuộc tính.

Giả sử record có thành phần:

```java
int retryCount
```

Trong cấu hình Properties hoặc YAML, cách viết chuẩn nên dùng là:

```properties
notification.retry-count=4
```

Binder có thể hỗ trợ các biến thể về dấu gạch ngang, chữ hoa/chữ thường, camelCase hoặc dấu gạch dưới tùy loại nguồn. Với biến môi trường hệ điều hành, dạng canonical của `notification.retry-count` thường được biểu diễn thành:

```text
NOTIFICATION_RETRYCOUNT
```

Trong khi đó, các chuỗi:

```text
notification.retrty-count
notification.retry-coutn
notification.rety-count
```

chứa **lỗi chính tả thực sự**, không phải chỉ khác kiểu định dạng.

Cần hiểu:

> **Relaxed binding linh hoạt về cách trình bày tên khóa; nó không phải thuật toán tự sửa từ sai.**

Nếu một số biến thể tên được binder nhận diện là cùng khóa, chúng không nên bị coi là unknown. Vì vậy khi thử chế độ nghiêm ngặt, hãy dùng một lỗi đánh máy rõ ràng như `retry-coutn` chứ không chỉ thay `retry-count` bằng `retryCount`.

Việc dùng **kebab-case chuẩn** trong tài liệu cấu hình, tên prefix và ví dụ giúp giảm số cách viết khác nhau, qua đó làm lỗi đánh máy dễ phát hiện hơn.

## 10. Khóa lồng nhau: cần kiểm tra đúng nhánh

Cấu hình thực tế thường chứa đối tượng lồng nhau.

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

Record tương ứng:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        URI endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

Các khóa đúng gồm:

```text
notification.endpoint
notification.retry.attempts
notification.retry.delay
```

Nếu YAML bị viết sai:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry:
    attemps: 4
    delay: 2s
```

thì `notification.retry.attemps` không tương ứng với thành phần `attempts` của record lồng nhau.

Khi strict binding được áp dụng trên bean cấu hình này, những thuộc tính không thể liên kết trong cây cấu hình thuộc tiền tố `notification` có thể khiến binding thất bại.

Tuy nhiên, cần phân biệt lỗi tên thuộc tính của nhánh với việc **nhánh lồng nhau hoàn toàn không tồn tại**. Nếu `notification.retry` không được cung cấp, constructor binding có thể nhận `null` cho nhánh ấy. Hãy dùng `@NotNull` cùng `@Valid` (và các ràng buộc trên thành phần lồng nhau) nếu ứng dụng yêu cầu nhánh đó phải luôn có mặt và dữ liệu bên trong phải hợp lệ.

## 11. Map và các tên khóa động là trường hợp đặc biệt

Không phải tất cả tên xuất hiện dưới một tiền tố đều cần tương ứng với field Java cố định.

Ví dụ người dùng muốn khai báo một map động:

```yaml
integration:
  labels:
    department: "sales"
    cost-center: "c001"
    owner: "team-a"
```

Record:

```java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "integration",
        ignoreUnknownFields = false)
public record IntegrationProperties(
        Map<String, String> labels) {
}
```

Trong thiết kế này, `department`, `cost-center`, `owner` là **khóa của dữ liệu map**, không phải ba field cố định trên record. Binder có thể liên kết chúng vào `labels` mà không coi chúng là “unknown” chỉ vì record không định nghĩa từng tên một.

Điều này có nghĩa **`ignoreUnknownFields = false` không phải một schema validator cho toàn bộ nội dung map động**. Nếu ứng dụng yêu cầu map chỉ chứa những nhãn hợp lệ, cần validation nghiệp vụ hoặc một cấu trúc kiểu rõ ràng hơn thay cho map.

Ví dụ nếu chỉ cho phép `department` và `owner`, một record có hai trường cố định và validation sẽ phù hợp hơn so với cho phép mọi khóa tùy ý trong `Map<String,String>`.

## 12. Không phải khóa nào ở application.yml cũng phải có trong bean

Một tệp `application.yml` có thể chứa cấu hình của Spring Boot và nhiều thư viện:

```yaml
server:
  port: 9090

management:
  endpoints:
    web:
      exposure:
        include: health,info

notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3
  connect-timeout: 5s
```

Bean có `prefix = "notification"` chỉ chịu trách nhiệm với nhóm `notification.*`. Không có lý do để bean ấy từ chối `server.port` hoặc `management.endpoints.web.exposure.include` chỉ vì nó không có field `port` hay `include`.

Đó là ranh giới thiết kế hợp lý của `@ConfigurationProperties`: mỗi lớp quản lý một vùng cấu hình có trách nhiệm rõ ràng.

Nếu muốn phát hiện lỗi trên cấu hình do chính ứng dụng sở hữu, hãy:

1. Chọn các tiền tố riêng, có ý nghĩa, chẳng hạn `notification`, `billing`, `storage`.
2. Đăng ký một bean `@ConfigurationProperties` tương ứng cho từng nhóm.
3. Bật kiểm tra khóa lạ tại những bean cần nghiêm ngặt.
4. Dùng validation cho yêu cầu bắt buộc.
5. Kiểm thử các trường hợp cấu hình hợp lệ và lỗi đánh máy.

Không nên kỳ vọng một bean `NotificationProperties` duy nhất kiểm soát mọi thuộc tính của Spring Framework, server, logging, database và các thư viện khác.

## 13. Kiểm tra lỗi tên khóa bằng ApplicationContextRunner

Một cách hữu ích để xác nhận ứng dụng từ chối khóa sai là viết **test binding có phạm vi nhỏ**. Spring Boot Test cung cấp `ApplicationContextRunner` để tạo ApplicationContext thử nghiệm với những property nhất định.

Đầu tiên, dùng record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        String endpoint,
        int retryCount) {
}
```

Sau đó viết test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsCorrectPropertyNames() {
        runner.withPropertyValues(
                "notification.endpoint=https://notify.example.invalid",
                "notification.retry-count=5"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            NotificationProperties props =
                    context.getBean(NotificationProperties.class);

            assertThat(props.retryCount()).isEqualTo(5);
        });
    }

    @Test
    void rejectsMisspelledPropertyName() {
        runner.withPropertyValues(
                "notification.endpoint=https://notify.example.invalid",
                "notification.retry-coutn=5"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class TestConfiguration {
    }
}
```

Ý nghĩa của hai bài test:

- Bài thứ nhất xác nhận tên khóa hợp lệ có thể được liên kết.
- Bài thứ hai đưa một khóa sai có chủ đích vào cùng prefix và yêu cầu ứng dụng test **không khởi tạo context thành công**.
- `@EnableConfigurationProperties` đảm bảo bean thực sự đi qua quá trình binder.
- `ApplicationContextRunner` giúp cô lập bài kiểm tra khỏi toàn bộ web server hoặc các dependency khác.

Khi kiểm thử ứng dụng thực tế, có thể kiểm tra thêm loại ngoại lệ hoặc một thông báo đại diện cho khóa chưa được liên kết. Tuy nhiên, nội dung chính xác của thông báo lỗi tùy phiên bản, nên tránh phụ thuộc vào toàn bộ chuỗi log trong assertion.

### 13.1. Kiểm thử lỗi sai tiền tố

Nếu muốn bảo vệ tình huống sai hoàn toàn `notification` thành `notificaton`, test chỉ kiểm tra `hasFailed()` do unknown field **chưa đủ**. Hãy thêm validation bắt buộc (như `@NotBlank` hoặc `@NotNull`) để việc không nhận được cấu hình chính khiến context thất bại.

Đây là lý do nên kiểm thử đồng thời **khóa dư không được nhận diện** và **khóa bắt buộc bị thiếu**.

## 14. Sử dụng @SpringBootTest để kiểm tra cấu hình thực tế

Khi ứng dụng có nhiều nguồn Config Data, profile và auto-configuration, một integration test có thể phù hợp hơn test binder đơn lẻ.

Ví dụ:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "notification.endpoint=https://notify.example.invalid",
        "notification.retry-count=7",
        "notification.connect-timeout=2s"
})
class NotificationConfigurationIntegrationTest {

    @Autowired
    private NotificationProperties properties;

    @Test
    void bindsConfiguration() {
        assertThat(properties.retryCount()).isEqualTo(7);
    }
}
```

Để test chạy, ứng dụng phải đăng ký `NotificationProperties` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Các giá trị do `@SpringBootTest(properties=...)` cung cấp tham gia vào cấu hình của test.

Với test mong đợi cấu hình lỗi khiến context thất bại, `ApplicationContextRunner` thường tiện hơn vì có thể kiểm tra lỗi khởi tạo bên trong callback, thay vì để framework test thất bại ngay khi tạo context.

Test đơn lẻ không bảo đảm tất cả môi trường production đều đúng, nhưng nó kiểm tra hành vi bảo vệ của bean ở mức kỹ thuật.

## 15. Trợ giúp lúc gõ tên: metadata và IDE

Kiểm tra lúc khởi động là một lớp bảo vệ. Một lớp bảo vệ khác là **hỗ trợ phát hiện khóa sai ngay khi soạn tệp cấu hình**.

Spring Boot có cơ chế configuration metadata cho các kiểu `@ConfigurationProperties`. Khi cấu hình annotation processor phù hợp, dự án có thể sinh metadata để IDE gợi ý tên thuộc tính, kiểu dữ liệu và tài liệu mô tả.

Trong dự án Maven, dependency thường dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Trong Gradle:

```groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
```

Khi IDE, extension và build đã nhận metadata, việc viết:

```yaml
notification:
  retry-coutn: 5
```

có thể bị IDE cảnh báo là không có thuộc tính tương ứng hoặc không xuất hiện trong danh sách gợi ý.

Cần phân biệt:

- **Metadata/IDE completion:** hỗ trợ tác giả cấu hình trong lúc soạn thảo.
- **Strict binding:** kiểm tra trong quá trình ứng dụng thực sự liên kết bean.
- **Validation:** kiểm tra yêu cầu bắt buộc và ràng buộc kiểu/miền giá trị.
- **Test:** xác nhận những cơ chế bảo vệ này hoạt động trong dự án.

Không nên xem cảnh báo IDE là bằng chứng duy nhất. Một IDE thiếu plugin, metadata chưa được sinh hoặc một khóa đến từ thư viện khác có thể khiến mức hỗ trợ khác nhau.

## 16. Khác biệt giữa @Value và @ConfigurationProperties

`@Value` thích hợp với các giá trị đơn:

```java
@Component
public class NotificationService {

    private final int retryCount;

    public NotificationService(
            @Value("${notification.retry-count:3}") int retryCount) {
        this.retryCount = retryCount;
    }
}
```

Nếu YAML viết sai thành `notification.retry-coutn`, placeholder `notification.retry-count` không tìm thấy giá trị và có thể dùng mặc định `3`.

Không có cấu hình `ignoreUnknownFields = false` tương tự áp dụng cho **mọi khóa** thông qua việc dùng `@Value` ở một bean thông thường. `@Value` giải quyết những placeholder mà bean đã yêu cầu; nó không tự xác nhận toàn bộ các thuộc tính lạ dưới một namespace.

Đối với một nhóm thuộc tính cùng trách nhiệm, `@ConfigurationProperties` có lợi thế:

- Nhóm các trường trong một kiểu Java.
- Hỗ trợ relaxed binding có hệ thống.
- Có thể bật `ignoreUnknownFields = false`.
- Có thể gắn validation tập trung.
- Có thể sinh metadata cho IDE.
- Cho phép constructor binding và thiết kế bất biến.

Điều đó không có nghĩa tất cả `@Value` đều sai. Khi một bean chỉ cần một giá trị không thuộc nhóm cấu hình lớn, `@Value` vẫn là lựa chọn gọn. Nhưng nếu mục tiêu chính là **không bỏ qua âm thầm các khóa cấu hình sai**, cấu hình theo nhóm với `@ConfigurationProperties` thường tạo được ranh giới kiểm soát rõ hơn.

## 17. Các nguồn cấu hình khác nhau cũng có thể mang khóa sai

Một khóa sai không chỉ xuất hiện trong YAML. Người vận hành có thể viết:

```bash
java -jar app.jar --notification.retry-coutn=9
```

hoặc tạo khóa sai trong tệp Properties:

```properties
notification.retry-coutn=9
```

hoặc cấp một tên biến môi trường không tương ứng với thuộc tính mong đợi.

Với cơ chế liên kết nghiêm ngặt, binder có thể phát hiện những thuộc tính chưa được liên kết thuộc phạm vi bean và thuộc nguồn nó xử lý. Tuy nhiên, **không bảo đảm mọi biến môi trường lạc tên đều được phát hiện như một unknown property của bean**: cách biến được ánh xạ sang tên cấu hình và phạm vi nguồn liên quan là một phần của quy trình đó.

Một số ví dụ về khác biệt tên biến:

```text
Tên chuẩn: notification.retry-count
Dạng biến môi trường thông dụng: NOTIFICATION_RETRYCOUNT

Sai tên rõ ràng:
NOTIFICATION_RETRTYCOUNT
```

Đặc biệt khi cấp biến bằng hệ thống triển khai, hãy xác nhận:

1. Biến có thực sự vào tiến trình Java không?
2. Tên biến có được Spring ánh xạ sang khóa kỳ vọng không?
3. Đã có nguồn ưu tiên cao hơn ghi đè chưa?
4. Bean cấu hình có được binder xử lý không?
5. Validation có phát hiện thiếu cấu hình bắt buộc không?

Không được suy luận rằng cứ đặt `ignoreUnknownFields = false` là ứng dụng đã có một bộ quét toàn bộ environment variables.

## 18. Thứ tự ưu tiên và khóa sai là hai vấn đề riêng

Ví dụ:

```yaml
# application.yml
notification:
  retry-count: 3
```

Chạy:

```bash
java -jar app.jar --notification.retry-count=8
```

Giá trị có hiệu lực có thể là `8` do đối số dòng lệnh ưu tiên hơn Config Data.

Nếu thay bằng:

```bash
java -jar app.jar --notification.retry-coutn=8
```

thì đối số mới **không phải khóa `notification.retry-count`**. Nó có thể xuất hiện như một thuộc tính khác trong môi trường. Nếu binder coi khóa này là chưa được liên kết trong prefix của bean và `ignoreUnknownFields = false` đang áp dụng, ứng dụng có thể báo lỗi thay vì âm thầm dùng `3`.

Điều cần nhớ: **ưu tiên cao không sửa được tên khóa sai**. Một nguồn có ưu tiên cao hơn nhưng cung cấp tên khác không tự ghi đè tên thuộc tính mong đợi.

Ở chiều ngược lại, nếu nguồn ưu tiên cao cung cấp khóa đúng, strict binding không khiến nó bị từ chối chỉ vì nguồn thấp hơn cũng có cùng khóa đúng.

## 19. Bật chế độ nghiêm ngặt không đồng nghĩa từ chối mọi thuộc tính ngoài hợp đồng

Xét một file chứa:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3

database:
  pool-size: 20
```

Bean `NotificationProperties` với tiền tố `notification` không có nghĩa vụ nhận biết `database.pool-size`. Nếu ứng dụng có một bean khác mang prefix `database`, bean đó có thể liên kết thuộc tính trên.

Ngay cả bên trong prefix, một thuộc tính được binder nhận vào `Map<String,String>` hoặc một cấu trúc có phần tên động có thể là hợp lệ.

Vì thế cần xây dựng **hợp đồng cấu hình rõ ràng**:

- Với các trường có tên cố định, sử dụng thành phần Java cụ thể.
- Với tập khóa động được cho phép, sử dụng Map nhưng cân nhắc validation nội dung.
- Với yêu cầu bắt buộc, sử dụng validation.
- Với những namespace không thuộc ứng dụng, không cố dùng một bean để kiểm soát toàn bộ.

Một bộ cấu hình nghiêm ngặt tốt không nhất thiết là bộ cấu hình từ chối mọi thứ chưa biết trên toàn JVM; nó là bộ cấu hình biết **phạm vi nào thuộc trách nhiệm của từng nhóm**.

## 20. Cách xử lý khi ứng dụng báo lỗi khóa chưa được liên kết

Giả sử Spring Boot không khởi động và log có thông tin về `notification.retry-coutn` chưa được liên kết.

### Bước 1: tìm khóa trong nguồn có hiệu lực

Kiểm tra tệp Properties/YAML, profile đang hoạt động, đối số dòng lệnh và nguồn cấu hình bên ngoài. Đừng chỉ nhìn một tệp `application.yml` nếu ứng dụng còn import tệp khác hoặc sử dụng nhiều môi trường.

### Bước 2: đối chiếu với kiểu @ConfigurationProperties

Nếu record là:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(int retryCount) {
}
```

tên chuẩn mong đợi là `notification.retry-count`. Khóa `notification.retry-coutn` sai vị trí chữ.

### Bước 3: sửa ngay tại nguồn, không tắt bảo vệ chỉ để chạy

Sửa:

```yaml
notification:
  retry-count: 5
```

Không nên xử lý lỗi bằng cách đổi ngay sang `ignoreUnknownFields = true` khi chưa hiểu vì sao một khóa được xem là lạ.

### Bước 4: chạy lại test hoặc khởi động ứng dụng

Xác nhận bean được tạo và nhận giá trị đúng. Nếu có các bài kiểm tra binding, chạy lại cả trường hợp hợp lệ và trường hợp lỗi đánh máy.

### Bước 5: kiểm tra các khóa bắt buộc

Nếu typo làm một thuộc tính bắt buộc biến mất, hãy đảm bảo annotation validation hoặc kiểm tra constructor vẫn phát hiện việc thiếu giá trị sau khi sửa tên khóa.

### Bước 6: xem xét metadata và IDE

Nếu lỗi xuất hiện thường xuyên, cấu hình metadata và gợi ý của IDE để phát hiện sớm hơn. Giữ một danh sách tên khóa chuẩn trong tài liệu triển khai.

Cách chẩn đoán này giúp biến một lỗi cấu hình khó hiểu thành một quy trình kiểm tra có thể lặp lại.

## 21. Phân biệt “strict binding” với một bộ schema độc lập

Có thể xem bean `@ConfigurationProperties` như một hợp đồng cấu hình cho một nhóm thuộc tính. Nhưng `ignoreUnknownFields = false` không phải một bộ phân tích YAML tổng quát:

- Nó không kiểm tra cú pháp YAML trước parser.
- Nó không khẳng định mọi key trong tất cả các tệp thuộc ứng dụng đều đã khai báo trong một schema toàn cục.
- Nó không kiểm chứng ý nghĩa nghiệp vụ của giá trị hợp lệ về kiểu.
- Nó không tự bảo vệ các bí mật hoặc phân quyền nguồn cấu hình.
- Nó không thay thế việc kiểm thử từng profile và phương thức triển khai.
- Nó không kiểm tra một tệp chưa được nạp vào môi trường.

Ví dụ, nếu YAML sai thụt lề làm parser báo lỗi, đó là lỗi cú pháp/tài liệu, không phải lỗi field chưa được liên kết. Nếu `retry-count=-2` vẫn chuyển đổi thành `int`, đó là vấn đề validation nghiệp vụ, không phải unknown field.

Một thiết kế chắc chắn phối hợp **parser + binder + validation + kiểm thử**, thay vì dồn mọi trách nhiệm vào một annotation.

## 22. Khi nào nên bật ignoreUnknownFields = false?

Chế độ không bỏ qua khóa lạ thường phù hợp với:

1. **Nhóm cấu hình riêng của ứng dụng** có tập trường cố định, được quản lý như một hợp đồng.
2. **Thông số vận hành quan trọng** như retry, timeout, giới hạn, định tuyến hoặc lựa chọn tính năng.
3. **Hệ thống nhiều môi trường** mà một lỗi đánh máy có thể không lộ trong môi trường phát triển.
4. **Dự án cần fail fast**, tức là dừng sớm khi đầu vào cấu hình sai thay vì tiếp tục chạy với giá trị ngoài dự kiến.
5. **Nhóm có test cấu hình** và quy trình triển khai cho phép phát hiện/sửa lỗi trước production.

Có thể cần cân nhắc thêm khi:

- Cấu hình được chia sẻ với các thành phần có nhiều extension không do bean hiện tại sở hữu.
- Một namespace được thiết kế cho các khóa động trong map.
- Dự án đang chuyển phiên bản và còn những khóa cũ cần làm rõ trạng thái.
- Một phần cấu hình được nạp từ nguồn có nhiều khóa ngoài phạm vi của bean.

Trong các tình huống này, không nên ngay lập tức chọn `true` hay `false` theo cảm tính. Hãy chọn **ranh giới prefix đúng**, mô hình dữ liệu phù hợp, rồi viết test cho những nguồn thực sự được hỗ trợ.

## 23. Một mẫu thiết kế hoàn chỉnh cho cấu hình quan trọng

Giả sử một ứng dụng gửi email có nhóm cấu hình:

```yaml
delivery:
  smtp:
    host: "smtp.example.invalid"
    port: 2525
    connect-timeout: 4s
    retries: 3
```

Với Spring Boot 3.x, có thể dùng record bất biến:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "delivery.smtp",
        ignoreUnknownFields = false)
public record SmtpProperties(
        @NotBlank String host,
        @Min(1) @Max(65535) int port,
        @NotNull Duration connectTimeout,
        @Min(0) int retries) {
}
```

Đăng ký bằng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Bean vừa có:

- **Prefix cụ thể:** chỉ quản lý `delivery.smtp.*`.
- **Liên kết qua constructor:** không cần setter.
- **Kiểm tra khóa lạ:** `ignoreUnknownFields = false`.
- **Kiểm tra dữ liệu:** `@NotBlank`, `@Min`, `@Max`, `@NotNull`.
- **Kiểu đúng nghĩa:** `Duration` thay cho chuỗi thời gian.

Một lỗi:

```yaml
delivery:
  smtp:
    host: "smtp.example.invalid"
    port: 2525
    connect-timeout: 4s
    retrise: 3
```

đưa `delivery.smtp.retrise` vào phạm vi của bean nhưng không có trường tương ứng. Cơ chế strict binding có thể từ chối cấu hình này.

Nếu thay vì vậy người vận hành bỏ toàn bộ nhánh `delivery.smtp`, các ràng buộc bắt buộc như `@NotBlank host`, `@Min(1) port` và `@NotNull connectTimeout` giúp ngăn bean có đầu vào thiếu yếu tố quan trọng.

Đừng in toàn bộ đối tượng cấu hình có thể chứa mật khẩu SMTP ra log. Record tự sinh `toString()`; nếu thêm secret vào record, việc in record có thể làm lộ giá trị nhạy cảm.

## 24. Bài tập A: tìm khóa viết sai

Cho record:

```java
@ConfigurationProperties(
        prefix = "payment",
        ignoreUnknownFields = false)
public record PaymentProperties(
        String provider,
        int retryCount,
        boolean auditEnabled) {
}
```

Và cấu hình:

```yaml
payment:
  provider: demo
  retry-count: 4
  audit-enabld: true
```

**Câu hỏi:** khóa nào có khả năng không được liên kết?

**Đáp án:** `payment.audit-enabld`. Tên mong đợi là `payment.audit-enabled` tương ứng thành phần `auditEnabled`.

**Câu hỏi phụ:** nếu đổi `audit-enabld` thành `auditEnabled`, liệu đây vẫn chắc chắn là lỗi?

Không nhất thiết. Relaxed binding có thể hỗ trợ những biến thể tên hợp lệ; **lỗi chính tả** cần phân biệt với **khác quy ước trình bày**. Tuy nhiên, nên dùng kebab-case `audit-enabled` làm dạng chuẩn trong YAML.

## 25. Bài tập B: giá trị sai kiểu hay khóa sai?

Cho:

```java
@ConfigurationProperties(
        prefix = "queue",
        ignoreUnknownFields = false)
public record QueueProperties(
        int batchSize,
        java.time.Duration pollInterval) {
}
```

Xét ba cấu hình:

**Trường hợp 1**

```properties
queue.batch-size=not-a-number
queue.poll-interval=5s
```

**Trường hợp 2**

```properties
queue.batch-szie=100
queue.poll-interval=5s
```

**Trường hợp 3**

```properties
queue.batch-size=100
queue.poll-interval=5s
```

Đáp án:

| Trường hợp | Vấn đề |
| --- | --- |
| 1 | Tên `batch-size` đúng nhưng giá trị không chuyển thành `int` |
| 2 | Tên `batch-szie` sai, có thể bị xem là unbound |
| 3 | Hai khóa phù hợp, dữ liệu có thể liên kết thành công |

Bài tập cho thấy `ignoreUnknownFields` và chuyển đổi kiểu giải quyết hai loại lỗi khác nhau.

## 26. Bài tập C: sai prefix có chắc bị phát hiện không?

Bean:

```java
@Validated
@ConfigurationProperties(
        prefix = "gateway",
        ignoreUnknownFields = false)
public record GatewayProperties(
        @jakarta.validation.constraints.NotBlank String baseUrl) {
}
```

Nguồn cấu hình:

```yaml
gatway:
  base-url: "https://gateway.example.invalid"
```

**Câu hỏi:** chỉ riêng `ignoreUnknownFields = false` có bảo đảm bắt được lỗi `gatway` không?

**Không.** Khóa đã nằm ngoài prefix `gateway` mà bean đang liên kết. Nhưng nếu bean được đăng ký, validation với `@NotBlank` có thể phát hiện `baseUrl` bị thiếu/rỗng.

Giải pháp tốt nhất không phải chọn một trong hai cơ chế, mà là kết hợp chúng và kiểm thử tình huống sai prefix.

## 27. Bài tập D: khai báo không được nạp

Ứng dụng có:

```text
application.yml
application-prod.yml
```

Trong `application-prod.yml`:

```yaml
notification:
  retrty-count: 5
```

Nhưng ứng dụng chỉ chạy với profile `dev` và không có cơ chế nào nạp `application-prod.yml`.

**Câu hỏi:** strict binding của `NotificationProperties` có nhất thiết phát hiện khóa sai trong `application-prod.yml` ở lần chạy này không?

**Không.** Nếu tài liệu cấu hình đó không được nạp, binder không nhìn thấy khóa ấy trong lần chạy hiện tại. Cần kiểm thử cấu hình của profile `prod` hoặc dùng công cụ kiểm tra tĩnh thích hợp để phát hiện trước khi triển khai.

Bài tập này giải thích vì sao test cấu hình cần bao phủ các profile thực tế, không chỉ kiểm thử duy nhất cấu hình phát triển.

## 28. Ghi nhớ

- Với `@ConfigurationProperties`, `ignoreUnknownFields` mặc định là **`true`**, nên một số khóa không có đích liên kết có thể bị bỏ qua.
- Đặt **`ignoreUnknownFields = false`** khi muốn binder phát hiện các khóa chưa được liên kết trong phạm vi bean cấu hình.
- Cơ chế này có phạm vi theo **prefix và bean thực sự được đăng ký/bind**, không phải trình soát mọi thuộc tính từ mọi nguồn.
- **Sai tên khóa**, **giá trị sai kiểu**, **thiếu giá trị**, **sai prefix** và **giá trị sai yêu cầu nghiệp vụ** là những trường hợp khác nhau.
- `ignoreInvalidFields` liên quan đến lỗi binding/conversion, còn **Bean Validation** giúp kiểm tra giá trị bắt buộc và ràng buộc nghiệp vụ.
- Relaxed binding chấp nhận một số biến thể cách viết hợp lệ, nhưng **không tự sửa lỗi đánh máy**.
- Với map có khóa động, strict binding không thay thế kiểm tra schema cho từng key trong map.
- Tạo **configuration metadata** và tận dụng gợi ý của IDE để phát hiện lỗi sớm khi nhập cấu hình.
- Viết test bằng `ApplicationContextRunner` để kiểm tra cả đường đi thành công và trường hợp khóa viết sai làm context thất bại.
- Với cấu hình quan trọng, cách tiếp cận đáng tin cậy là **prefix rõ ràng + strict binding + validation + kiểm thử các profile/nguồn cấu hình được hỗ trợ**.
