# @Validated và phát hiện cấu hình không hợp lệ khi khởi động

Spring Boot cho phép cấu hình ứng dụng từ `application.yml`, `application.properties`, biến môi trường, tham số dòng lệnh và nhiều nguồn khác. Những giá trị này thường quyết định cách kết nối tới dịch vụ, giới hạn xử lý, timeout hoặc các tính năng được bật.

Tuy nhiên, việc một giá trị **đọc được** không có nghĩa giá trị đó **hợp lệ**. Một endpoint trống, số kết nối tối đa bằng 0 hoặc thông số retry ngoài phạm vi cho phép có thể khiến lỗi chỉ xuất hiện sau khi ứng dụng nhận request đầu tiên. Spring Boot kết hợp `@ConfigurationProperties` với `@Validated` và Jakarta Bean Validation để phát hiện nhiều lỗi như vậy ngay trong giai đoạn khởi tạo bean cấu hình.

## 1. Phân biệt cấu hình có mặt, bind được và hợp lệ

Hãy xét một service gửi thông báo. Nó cần các thuộc tính:

~~~yaml
app:
  notifications:
    sender: no-reply@example.test
    gateway: https://notify.example.test
    max-batch-size: 20
    retry:
      max-attempts: 3
      delay: 2s
~~~

Có ba mức kiểm tra khác nhau:

1. **Đọc giá trị:** Spring Boot tìm `app.notifications.max-batch-size` từ các nguồn cấu hình theo thứ tự ưu tiên.
2. **Binding và chuyển đổi kiểu:** Binder chuyển `20` thành số nguyên, `2s` thành `Duration`, URL thành `URI`.
3. **Validation:** quy tắc nghiệp vụ xác định `max-batch-size` phải từ 1 đến 100, `sender` không được rỗng, `retry.max-attempts` nằm trong phạm vi cho phép.

Ví dụ `max-batch-size: abc` sẽ thất bại ở bước chuyển đổi kiểu, trước khi quy tắc `@Min` có thể kiểm tra. Ngược lại, `max-batch-size: 0` vẫn chuyển thành `int` thành công nhưng không đạt ràng buộc giá trị.

`@Validated` nhằm kích hoạt bước kiểm tra thứ ba cho bean `@ConfigurationProperties`; nó không thay thế Binder hoặc các kiểm tra lỗi định dạng đầu vào.

## 2. Các annotation và dependency cần thiết

Để dùng các constraint theo Jakarta Bean Validation với Spring Boot, dự án thường thêm starter validation.

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Starter cung cấp Bean Validation API và một provider phù hợp, thường là Hibernate Validator. Nếu không có provider, chỉ đặt các annotation constraint trong code chưa đủ để đảm bảo các giá trị được kiểm tra như mong muốn.

Các annotation đến từ những package khác nhau:

| Thành phần | Package | Vai trò |
|---|---|---|
| `@ConfigurationProperties` | `org.springframework.boot.context.properties` | Bind nhóm property vào đối tượng Java |
| `@Validated` | `org.springframework.validation.annotation` | Yêu cầu áp dụng validation khi bind configuration properties |
| `@NotBlank`, `@NotNull`, `@Min`, `@Max` | `jakarta.validation.constraints` | Khai báo các ràng buộc |
| `@Valid` | `jakarta.validation` | Yêu cầu validate lồng xuống object con |
| `@ConfigurationPropertiesScan` | `org.springframework.boot.context.properties` | Quét và đăng ký các lớp configuration properties |
| `@EnableConfigurationProperties` | `org.springframework.boot.context.properties` | Đăng ký cụ thể một hoặc nhiều lớp configuration properties |

Với Spring Boot 3, namespace Bean Validation sử dụng `jakarta.validation.*`. Các hướng dẫn cũ dùng `javax.validation.*` thuộc hệ sinh thái Java EE trước đây và không nên sao chép nguyên xi vào ứng dụng Boot 3.

## 3. Ví dụ đầy đủ với @ConfigurationProperties và @Validated

Định nghĩa một Java record để chứa cấu hình thông báo:

~~~java
package com.example.notifications.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        @NotBlank String sender,
        @NotNull URI gateway,
        @Min(1) @Max(100) int maxBatchSize,
        @Valid @NotNull Retry retry
) {

    public record Retry(
            @Min(0) @Max(5) int maxAttempts,
            @NotNull Duration delay
    ) {
    }
}
~~~

Lớp `NotificationProperties` có vai trò lưu cấu hình, không chứa logic gửi thông báo. Mỗi property có một ràng buộc phù hợp:

- `sender`: dùng `@NotBlank` vì chuỗi không được `null`, rỗng hoặc chỉ có khoảng trắng.
- `gateway`: dùng `@NotNull` vì endpoint bắt buộc phải được cung cấp. Kiểu `URI` cũng yêu cầu quá trình binding chuyển đổi được từ chuỗi.
- `maxBatchSize`: dùng `@Min(1)` và `@Max(100)` để giới hạn kích thước một batch.
- `retry`: dùng `@NotNull` để bắt buộc có đối tượng cấu hình retry và `@Valid` để validate các trường bên trong.
- `maxAttempts`: được phép bằng 0 khi ứng dụng không muốn retry, nhưng không vượt quá 5.
- `delay`: không được thiếu; ví dụ này chưa đặt ràng buộc về việc duration phải dương.

Với record có một constructor tương ứng các thành phần, Spring Boot hỗ trợ constructor binding. Giá trị được truyền vào constructor khi bean configuration properties được tạo, thay vì phải viết setter cho từng thuộc tính.

### Đăng ký bean configuration properties

Chỉ định nghĩa record chưa khiến Spring tự động đăng ký nó như một bean. Có thể kích hoạt `@ConfigurationPropertiesScan`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
~~~

Hoặc đăng ký riêng lớp này từ một configuration class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Chỉ cần chọn một cách đăng ký phù hợp; không nhất thiết dùng cả hai trong cùng ứng dụng.

Sau khi được đăng ký, bean có thể được tiêm vào service thông thường:

~~~java
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final NotificationProperties properties;

    public NotificationSender(NotificationProperties properties) {
        this.properties = properties;
    }

    public int batchLimit() {
        return properties.maxBatchSize();
    }
}
~~~

Service chỉ nhận một đối tượng cấu hình có kiểu dữ liệu rõ ràng. Nó không phải tự tìm nguồn cấu hình, chuyển `String` sang `Duration` hoặc lặp lại các điều kiện kiểm tra giá trị.

## 4. Điều gì xảy ra khi cấu hình không hợp lệ?

Giả sử `application.yml` chứa:

~~~yaml
app:
  notifications:
    sender: "  "
    gateway: https://notify.example.test
    max-batch-size: 0
    retry:
      max-attempts: 9
      delay: 1s
~~~

Các giá trị vẫn có thể được chuyển về đúng kiểu Java. Tuy nhiên:

- `sender` không đáp ứng `@NotBlank`.
- `max-batch-size` không đáp ứng `@Min(1)`.
- `retry.max-attempts` không đáp ứng `@Max(5)`.

Khi Spring Boot tạo và bind `NotificationProperties`, validation phát hiện các lỗi này. Quá trình khởi tạo context thường thất bại, do đó ứng dụng không đi tới trạng thái chạy thành công.

Thông báo lỗi thực tế phụ thuộc vào phiên bản Spring Boot, provider validation và kiểu ràng buộc. Về mặt ý nghĩa, thông báo thường cung cấp thông tin dạng:

~~~text
Binding to target NotificationProperties failed

Property: app.notifications.sender
Value: "  "
Reason: must not be blank

Property: app.notifications.max-batch-size
Value: 0
Reason: must be greater than or equal to 1

Property: app.notifications.retry.max-attempts
Value: 9
Reason: must be less than or equal to 5
~~~

Đây là **minh họa nội dung lỗi**, không phải cam kết nguyên văn một stack trace cụ thể. Trong log thật, Spring Boot có thể kèm tên bean, nguyên nhân lồng nhau, nguồn file và vị trí property khi thông tin origin có sẵn.

Ý nghĩa quan trọng là lỗi được phát hiện **trong quá trình bind/khởi tạo bean cấu hình**, trước khi service nghiệp vụ phụ thuộc vào bean đó bắt đầu sử dụng giá trị sai.

### Khi nào không chắc lỗi xuất hiện ngay lúc startup?

Trong ứng dụng thông thường, các singleton không lazy được khởi tạo khi context refresh, nên cấu hình sai thường làm startup thất bại. Tuy nhiên, nếu bean configuration properties bị lazy và chưa được tạo trong giai đoạn startup, việc binding/validation có thể bị hoãn đến lúc bean được yêu cầu.

Nếu yêu cầu là **fail fast ở startup**, cần bảo đảm bean cấu hình bắt buộc được đăng ký và tạo trong quá trình khởi động thông thường. Đừng nhầm `@Validated` với một tác vụ kiểm tra toàn bộ mọi key trong mọi file cấu hình ngay khi JVM vừa bắt đầu chạy.

## 5. @NotNull, @NotBlank, @NotEmpty và kiểu nguyên thủy

Ba annotation dễ bị nhầm lẫn khi kiểm tra chuỗi và collection:

| Constraint | Điều được kiểm tra | Ví dụ sử dụng |
|---|---|---|
| `@NotNull` | Giá trị không được `null` | URI, Duration, object lồng |
| `@NotEmpty` | Không `null` và kích thước hoặc độ dài không bằng 0 | Collection, map, chuỗi |
| `@NotBlank` | Chuỗi không `null`, không rỗng và không chỉ là khoảng trắng | Tên, host, identifier |

Ví dụ:

~~~java
@NotNull
URI gateway;

@NotBlank
String sender;

@NotEmpty
List<String> allowedRegions;
~~~

`@NotBlank` không phải annotation chung cho mọi kiểu; hãy dùng nó cho `CharSequence`.

### Lưu ý với int, boolean và kiểu nguyên thủy

Một trường `int` không thể là `null`. Nếu property bị thiếu, giá trị có thể là 0 sau binding, nên `@NotNull` trên `int` không giúp phát hiện việc thiếu cấu hình.

Thay vào đó, có thể đặt ràng buộc miền giá trị:

~~~java
@Min(1)
@Max(100)
int maxBatchSize;
~~~

Nếu muốn phân biệt chính xác **không cung cấp thuộc tính** với **có cung cấp 0**, có thể dùng wrapper:

~~~java
@NotNull
@Min(0)
Integer maxAttempts;
~~~

Với `Integer`, `null` có ý nghĩa riêng và `@NotNull` có thể bắt trường hợp thiếu giá trị. Cách chọn kiểu dữ liệu cần phản ánh yêu cầu thực tế: cấu hình bắt buộc, có default hay có thể bỏ qua.

## 6. Validate object lồng nhau bằng @Valid

Một cấu hình không phải lúc nào cũng phẳng. Ví dụ, `app.notifications.retry` chứa nhiều trường liên quan.

Nếu chỉ đặt constraint bên trong `Retry` mà không cho validator đi sâu vào object, các quy tắc lồng nhau có thể không được thực thi như mong đợi. `@Valid` là cơ chế cascade validation của Jakarta Bean Validation:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        @NotBlank String sender,
        @Valid @NotNull Retry retry
) {

    public record Retry(
            @Min(0) @Max(5) int maxAttempts,
            @NotNull Duration delay
    ) {
    }
}
~~~

Hai annotation trên `retry` có nhiệm vụ khác nhau:

- `@NotNull` yêu cầu object `Retry` phải tồn tại.
- `@Valid` yêu cầu kiểm tra các constraint của đối tượng `Retry` sau khi nó được bind.

Chỉ có `@Valid` không tự coi `null` là sai, vì Bean Validation mặc định không cascade vào giá trị `null`. Nếu object con là bắt buộc, hãy kết hợp với `@NotNull` như ví dụ.

### Validate phần tử trong danh sách

Với cấu hình chứa danh sách, có thể đặt constraint lên chính collection và các phần tử:

~~~java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record RegionProperties(
        @NotEmpty List<@NotBlank String> regions
) {
}
~~~

`@NotEmpty` yêu cầu danh sách có ít nhất một phần tử. `List<@NotBlank String>` yêu cầu mỗi chuỗi trong danh sách không trống hoặc toàn khoảng trắng.

Nếu danh sách chứa các object có constraint riêng, có thể dùng `@Valid` để cascade vào từng phần tử. Đây là cách tổ chức phù hợp khi cấu hình phức tạp cần được kiểm tra theo nhiều tầng.

## 7. Validation không thay thế type conversion

Spring Boot có thể bind nhiều kiểu dữ liệu trực tiếp:

~~~yaml
app:
  notifications:
    gateway: https://notify.example.test
    max-batch-size: 30
    retry:
      max-attempts: 2
      delay: 750ms
~~~

Binder chuyển:

- `https://notify.example.test` thành `URI`.
- `30` thành `int`.
- `750ms` thành `Duration`.

Nếu người vận hành đặt:

~~~yaml
app:
  notifications:
    max-batch-size: several
~~~

Giá trị `several` không chuyển được sang `int`. Startup có thể thất bại vì lỗi binding trước khi Bean Validation kiểm tra `@Min` hay `@Max`.

Tương tự, một URI sai định dạng có thể làm conversion thất bại; một URI đúng cú pháp nhưng không thỏa yêu cầu nghiệp vụ (ví dụ scheme không phải HTTPS) có thể cần constraint bổ sung.

Phân biệt hai loại lỗi giúp chọn công cụ:

- **Sai kiểu hoặc sai cú pháp:** xem lại property name, định dạng dữ liệu và conversion.
- **Đúng kiểu nhưng sai quy tắc:** dùng Jakarta Bean Validation, custom constraint hoặc kiểm tra nhất quán giữa các trường.

Một property thiếu thường không tự tạo lỗi conversion nếu Java có thể nhận `null` hoặc giá trị mặc định. Nếu property bắt buộc, hãy khai báo constraint tương ứng.

## 8. Kiểm tra những quy tắc phức tạp hơn

Các constraint chuẩn xử lý tốt những quy tắc đơn giản:

~~~java
@NotBlank
String sender;

@Min(1)
@Max(100)
int maxBatchSize;

@Pattern(regexp = "[a-z0-9-]+")
String tenantCode;
~~~

Với yêu cầu cần so sánh nhiều trường hoặc kiểm tra domain đặc thù, có thể xây dựng custom Bean Validation constraint và validator.

Ví dụ, một thư viện nội bộ có thể cần ràng buộc rằng timeout phải lớn hơn 0, endpoint phải dùng HTTPS hoặc hai cấu hình xác thực phải xuất hiện cùng nhau. Những quy tắc này không nhất thiết biểu đạt tốt bằng `@NotNull` và `@Min`.

Một lựa chọn đơn giản cho quy tắc kiểm tra một thuộc tính suy diễn là `@AssertTrue`:

~~~java
import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record RetryOptions(@NotNull Duration delay) {

    @AssertTrue(message = "delay must be greater than zero")
    public boolean isDelayPositive() {
        return delay != null
                && !delay.isZero()
                && !delay.isNegative();
    }
}
~~~

Phương thức `isDelayPositive()` là getter kiểu boolean để Bean Validation kiểm tra. Trong configuration properties bao ngoài, vẫn cần `@Valid` để validator đi tới `RetryOptions`.

Với logic phức tạp hoặc cần thông báo lỗi gắn vào nhiều field, custom class-level constraint thường dễ mở rộng và test hơn. Nên giữ validation quyết định tính hợp lệ của **cấu hình**, không nên biến nó thành bước kết nối tới các dịch vụ mạng.

### Không gọi hệ thống bên ngoài trong constraint

Không nên dùng một validator cấu hình để thực hiện các request HTTP dài hoặc kiểm tra database còn online. Validation diễn ra trong startup, nên I/O không ổn định có thể làm ứng dụng khởi động thất bại vì lỗi hạ tầng tạm thời.

Những kiểm tra runtime liên quan tới dependency nên được thực hiện bằng cơ chế phù hợp, chẳng hạn health indicator, readiness, runner hoặc chiến lược kết nối có timeout/retry.

## 9. Thứ tự ưu tiên nguồn cấu hình vẫn được áp dụng

Validation không kiểm tra riêng lẻ từng bản sao giá trị trong mọi property source. Nó kiểm tra giá trị được bind sau khi Spring Boot đã giải quyết thứ tự ưu tiên các nguồn cấu hình.

Ví dụ file đóng gói có:

~~~yaml
app:
  notifications:
    max-batch-size: 20
~~~

Người vận hành ghi đè bằng biến môi trường:

~~~bash
APP_NOTIFICATIONS_MAXBATCHSIZE=0
~~~

Nếu biến môi trường này có độ ưu tiên cao hơn file, Binder nhận `0` và `@Min(1)` sẽ thất bại dù file `application.yml` chứa `20` hợp lệ.

Tương tự, nếu giá trị trong file classpath không hợp lệ nhưng một nguồn ưu tiên cao hơn thay bằng giá trị hợp lệ, bean có thể bind thành công. Điều được kiểm tra là **giá trị cuối cùng được chọn** cho bean, không phải mọi giá trị từng xuất hiện.

Với Spring Boot, quy tắc chuyển tên property sang environment variable thường là thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch nối và chuyển chữ hoa. Ví dụ `app.notifications.max-batch-size` trở thành `APP_NOTIFICATIONS_MAXBATCHSIZE`.

Nếu ứng dụng đọc giá trị sai, hãy kiểm tra active profile, external files, environment variables và command-line arguments trước khi kết luận validator không hoạt động.

## 10. Kiểm thử thất bại khởi động bằng ApplicationContextRunner

Một ứng dụng có thể chứa hàng chục configuration properties. Thay vì phải khởi động toàn bộ server để kiểm tra từng trường hợp, có thể dùng `ApplicationContextRunner` trong Spring Boot Test để tạo context nhỏ và kiểm tra trạng thái.

Ví dụ với `NotificationProperties` ở trên:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ValidationAutoConfiguration.class
                    ))
                    .withUserConfiguration(PropertiesConfig.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
                "app.notifications.sender=no-reply@example.test",
                "app.notifications.gateway=https://notify.example.test",
                "app.notifications.max-batch-size=20",
                "app.notifications.retry.max-attempts=3",
                "app.notifications.retry.delay=2s"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(NotificationProperties.class);

            NotificationProperties properties =
                    context.getBean(NotificationProperties.class);

            assertThat(properties.maxBatchSize()).isEqualTo(20);
        });
    }

    @Test
    void invalidBatchSizePreventsStartup() {
        runner.withPropertyValues(
                "app.notifications.sender=no-reply@example.test",
                "app.notifications.gateway=https://notify.example.test",
                "app.notifications.max-batch-size=0",
                "app.notifications.retry.max-attempts=3",
                "app.notifications.retry.delay=2s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class PropertiesConfig {
    }
}
~~~

Kiểm thử dùng `ValidationAutoConfiguration` để cung cấp hạ tầng validation trong context nhỏ khi provider có mặt trên classpath. Trong ứng dụng chính, starter validation và auto-configuration của Spring Boot thường đảm nhiệm phần đó.

Có thể mở rộng bộ test để kiểm tra:

- `sender` trống hoặc chỉ có dấu cách.
- `gateway` không có hoặc sai định dạng.
- `max-batch-size` nhỏ hơn 1 hoặc lớn hơn 100.
- `retry.max-attempts` nằm ngoài khoảng 0–5.
- `retry` thiếu toàn bộ hoặc một trường bắt buộc bị thiếu.
- Thuộc tính ghi đè từ một nguồn ưu tiên cao làm kết quả validation thay đổi.

Khi test lỗi startup, không nhất thiết phải assert toàn bộ chuỗi exception vì thông báo chi tiết có thể khác nhau giữa phiên bản framework. Hãy kiểm tra lỗi có xảy ra và, khi cần, tìm những thông tin ổn định như tên property hoặc constraint gây lỗi.

## 11. Debug khi validation không hoạt động

Nếu đã đặt `@Validated` nhưng ứng dụng vẫn khởi động với cấu hình sai, có thể xem xét các nguyên nhân sau.

### Bean configuration properties chưa được đăng ký

Ví dụ, lớp có `@ConfigurationProperties` nhưng không được quét bằng `@ConfigurationPropertiesScan`, không được đăng ký bằng `@EnableConfigurationProperties` và cũng không được khai báo theo một cơ chế bean phù hợp.

Khi lớp chưa được tạo thành bean, Spring không có bước bind và validate cấu hình đó. Hãy bảo đảm bean thật sự tham gia ApplicationContext.

### Thiếu Bean Validation provider

Các annotation `jakarta.validation.constraints.*` cần một provider để chạy. Nếu thiếu `spring-boot-starter-validation` hoặc provider tương đương, hành vi có thể không như mong đợi. Hãy xác nhận dependency thực tế thay vì chỉ kiểm tra source import.

### Đặt @Validated sai vị trí

Với configuration properties, hãy đặt `@Validated` trên lớp dùng để bind hoặc dùng cơ chế validation phù hợp khi đăng ký bean. Đặt `@Validated` trên service khác không tự kích hoạt validation của mọi cấu hình liên quan.

Không nhầm cơ chế này với `@Valid` trong Spring MVC controller dùng để validate request body; cả hai dựa trên Bean Validation nhưng được kích hoạt trong các giai đoạn khác nhau.

### Thiếu @Valid cho cấu hình lồng nhau

Nếu constraint nằm trong một object con, cần cascade validation qua `@Valid` ở property chứa object. Nếu object con là bắt buộc, thêm `@NotNull` để bắt trường hợp nó hoàn toàn vắng mặt.

### Constraint không phát hiện giá trị thiếu

`@NotNull` không có ý nghĩa thực tế trên `int` nguyên thủy. Một giá trị bị thiếu có thể thành 0; dùng `@Min(1)` hoặc kiểu wrapper `Integer` kết hợp `@NotNull` theo yêu cầu.

### Bean bị lazy nên chưa bind

Nếu bean cấu hình không được tạo trong startup, validation có thể diễn ra muộn hơn. Với cấu hình cốt lõi cần fail fast, đừng vô tình trì hoãn việc tạo bean đến request đầu tiên.

### Đang đọc property khác với property đã kiểm tra

Một service có thể tự đọc Environment bằng tên khác hoặc tạo object cấu hình bằng `new`, khiến giá trị mà service dùng không đi qua bean `@ConfigurationProperties` đã được validate. Nên inject chính bean cấu hình đã bind thay vì có nhiều đường đọc property song song.

## 12. Validation và giá trị mặc định

Giá trị mặc định là công cụ hữu ích nhưng cần được thiết kế có chủ đích.

Một property tùy chọn có thể có default trong code:

~~~java
@ConfigurationProperties(prefix = "app.worker")
@Validated
public record WorkerProperties(
        @DefaultValue("10") @Min(1) @Max(100) int parallelism
) {
}
~~~

Trong ví dụ này, `@DefaultValue` thuộc package `org.springframework.boot.context.properties.bind`. Nếu không cung cấp `app.worker.parallelism`, Binder dùng giá trị mặc định `10`; `@Min` và `@Max` vẫn áp dụng cho giá trị đã bind.

Nếu người vận hành truyền `--app.worker.parallelism=0`, giá trị `0` ghi đè default và validation thất bại.

Không nên đặt default cho một thuộc tính thực sự bắt buộc mà thiếu nó phải được báo lỗi. Ví dụ, endpoint production có thể cần `@NotNull` mà không có default, để tránh ứng dụng vô tình kết nối tới một endpoint thử nghiệm.

Với cấu hình có nhiều nguồn, default tại lớp Java và default trong `application.yml` đều có ích, nhưng cần tránh tạo quá nhiều nguồn giá trị khiến người đọc khó xác định giá trị thực tế.

## 13. Không dùng @Validated để thay thế các tầng bảo vệ khác

Cấu hình hợp lệ là điều kiện cần, không phải bảo đảm rằng hệ thống sẽ hoạt động hoàn hảo.

- `@NotNull URI gateway` chỉ kiểm tra gateway được cung cấp, không bảo đảm DNS hoặc API từ xa đang hoạt động.
- `@Min(1) int maxBatchSize` bảo đảm giới hạn dương, không bảo đảm server đủ tài nguyên cho mọi mức cấu hình.
- `@NotBlank String sender` loại bỏ giá trị trống, không xác nhận địa chỉ gửi có được cấp quyền sử dụng.
- Một `Duration` hợp lệ về cú pháp vẫn có thể quá nhỏ hoặc quá lớn đối với yêu cầu vận hành; cần thêm constraint domain nếu muốn giới hạn.

Khi xây dựng validation, nên phân biệt:

1. **Cú pháp và kiểu:** Binder và conversion.
2. **Quy tắc tĩnh của cấu hình:** Bean Validation với `@Validated`.
3. **Trạng thái hệ thống bên ngoài:** kiểm tra runtime, health/readiness hoặc cơ chế kết nối riêng.
4. **Quy tắc nghiệp vụ của từng request:** validation ở tầng API/domain.

Phân tách đúng các tầng tránh đưa các phép gọi mạng không ổn định vào startup validation và giúp thông báo lỗi rõ ràng hơn.

## 14. Quy trình áp dụng trong một dự án Spring Boot

Để phát hiện cấu hình không hợp lệ sớm và nhất quán:

1. Gom các property liên quan vào một lớp hoặc record `@ConfigurationProperties` có prefix rõ ràng.
2. Thêm dependency `spring-boot-starter-validation` hoặc provider Bean Validation phù hợp.
3. Đánh dấu lớp cấu hình bằng `@Validated`.
4. Áp dụng constraint phù hợp cho từng trường: `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@Pattern` và các ràng buộc khác.
5. Dùng `@Valid` cho object lồng nhau, kết hợp `@NotNull` khi cả object con là bắt buộc.
6. Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
7. Bảo đảm bean cấu hình bắt buộc được tạo trong startup để validation thất bại sớm.
8. Test cả cấu hình hợp lệ, giá trị sai miền, thiếu property và sai định dạng kiểu.
9. Khi startup lỗi, tìm tên property, nguồn giá trị và nguyên nhân binding/validation trước khi sửa cấu hình.
10. Inject bean `@ConfigurationProperties` đã được validate vào các service thay vì tạo nhiều đường đọc cấu hình khác nhau.

Khi dùng đúng cách, `@Validated` chuyển lỗi cấu hình từ một sự cố khó đoán trong lúc chạy thành lỗi có thể phát hiện và sửa ngay tại thời điểm ứng dụng khởi động. Kết hợp validation với binding có kiểu dữ liệu rõ ràng, nguồn cấu hình minh bạch và các bài test startup giúp ứng dụng Spring Boot vận hành đáng tin cậy hơn.

