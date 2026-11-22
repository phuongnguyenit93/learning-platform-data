# Kiểm tra cấu hình thiếu hoặc sai và quan sát ứng dụng dừng sớm trong Spring Boot

## 1. Mục tiêu bài thực hành

Trong Spring Boot, ứng dụng có thể nạp cấu hình từ `application.yml`, `application.properties`, các file theo profile, biến môi trường, command-line arguments và Config Data import. Các cơ chế này giúp triển khai linh hoạt, nhưng cũng tạo ra nguy cơ một giá trị bị thiếu, nhập sai hoặc bị override mà nhóm phát triển không phát hiện ngay.

Bài thực hành này xây dựng một ứng dụng nhỏ có cấu hình kiểu rõ ràng, sau đó cố tình tạo những lỗi khác nhau và quan sát cơ chế **fail fast**: ứng dụng **từ chối khởi động thành công** khi cấu hình quan trọng không hợp lệ.

Sau bài học, người học có thể:

1. Tạo bean `@ConfigurationProperties` có validation.
2. Phân biệt **thiếu khóa**, **giá trị rỗng**, **sai kiểu**, **sai ràng buộc** và **khóa không được liên kết**.
3. Biết trường hợp nào Spring Boot có thể dùng default, trường hợp nào nên dừng khởi động.
4. Chạy ứng dụng với cấu hình hợp lệ và những cấu hình lỗi có chủ đích.
5. Đọc thông báo startup và cause chain mà không dựa vào một chuỗi log cố định.
6. Viết test khẳng định application context chỉ khởi động khi cấu hình đáp ứng hợp đồng.
7. Phân biệt lỗi nạp Config Data với lỗi binding/validation.
8. Kiểm tra các nguồn ưu tiên cao như biến môi trường và CLI.
9. Kiểm tra profile được kích hoạt đúng.
10. Viết một checklist cấu hình triển khai nhằm bắt lỗi trước production.

Toàn bộ endpoint, token và đường dẫn trong ví dụ đều là dữ liệu học tập. Không sử dụng credential thực trong bài test hoặc log.

## 2. “Dừng sớm” nghĩa là gì?

Fail fast trong bài này có nghĩa: **nếu cấu hình bắt buộc không đúng, quá trình khởi tạo Spring application context thất bại thay vì để ứng dụng nhận traffic với trạng thái không mong muốn**.

Ví dụ:

~~~text
Start application
       |
       v
Load Config Data / PropertySources
       |
       v
Bind demo.delivery.* into DeliveryProperties
       |
       +-- conversion failed ------> startup failure
       |
       v
Validate DeliveryProperties
       |
       +-- constraints violated ---> startup failure
       |
       v
Create dependent beans
       |
       +-- invalid invariant -----> startup failure
       |
       v
Application context ready
       |
       v
Serve workload / run job
~~~

Lưu ý: không phải mọi lỗi đều xuất hiện đúng ở cùng một bước; một missing Config Data location có thể thất bại trước Binder, còn lỗi credential hết hạn tại upstream có thể chỉ được phát hiện khi gọi dịch vụ nếu không có startup check. “Dừng sớm” ở đây tập trung vào những điều kiện **có thể và nên kiểm tra trong startup**.

Một chương trình Java có thể in log rồi kết thúc với mã thoát khác 0 khi exception không được xử lý. Mã thoát và định dạng thông báo tùy launcher, hệ điều hành, phiên bản Boot và test runner. Bằng chứng đáng tin cậy là **context failed vì đúng nguyên nhân cấu hình**, không chỉ một đoạn log có chữ ERROR.

## 3. Tình huống thực hành

Giả sử có dịch vụ `delivery-worker` đẩy sự kiện sang một API đối tác. Nó cần:

| Thuộc tính | Kiểu | Hợp đồng |
| --- | --- | --- |
| `demo.delivery.enabled` | Boolean | Bắt buộc khai báo rõ true/false |
| `demo.delivery.endpoint` | String | Bắt buộc và không blank |
| `demo.delivery.request-timeout` | Duration | Bắt buộc, lớn hơn 0 |
| `demo.delivery.max-attempts` | Integer | Bắt buộc, từ 1 đến 5 |

Trong bài này `endpoint` luôn bắt buộc, kể cả `enabled=false`, để minh họa ràng buộc đơn giản, dễ test. Nếu hệ thống thật yêu cầu endpoint **chỉ khi enabled**, hãy dùng cross-field validation hoặc schema/bean registration theo mode; phần nâng cao sẽ minh họa ở cuối.

Bộ cấu hình hợp lệ:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

Các tình huống cần cố tình phá:

- Bỏ `endpoint`.
- Cấp `endpoint=""` hoặc chỉ whitespace.
- Cấp `max-attempts=abc`.
- Cấp `max-attempts=0` hoặc 9.
- Cấp `request-timeout=tomorrow`.
- Cấp `request-timeout=0s`.
- Bỏ `enabled`.
- Viết sai `max-attemtps`.
- Đưa một override sai qua environment/CLI.
- Nhập một Config Data location bắt buộc không tồn tại.

Những lỗi này không cùng bản chất; học cách xác định **lớp lỗi** là một mục tiêu quan trọng.

## 4. Cấu trúc dự án

Một cấu trúc Maven/Spring Boot Java ví dụ:

~~~text
config-fail-fast-demo/
  pom.xml
  src/
    main/
      java/com/example/demo/
        DemoApplication.java
        config/
          DeliveryProperties.java
        service/
          DeliveryRunner.java
      resources/
        application.yml
        application-local.yml
        application-prod.yml
    test/
      java/com/example/demo/
        config/
          DeliveryPropertiesTests.java
~~~

Không cần một API HTTP thật để kiểm tra binding; một `CommandLineRunner` có thể chứng minh application context đã khởi tạo. Trong production, runner không nên in secret hoặc cả properties bean khi nó có credential.

Nếu dùng Gradle, cấu trúc source tương tự; thay `pom.xml` bằng `build.gradle` hoặc `build.gradle.kts` và dùng task tương ứng.

## 5. Dependencies cần thiết

Nếu dự án đã dùng Spring Boot với dependency management, cần các dependency:

### Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dự án phải có Spring Boot parent/BOM hoặc cơ chế quản lý version phù hợp. Snippet này là phần `dependencies` chèn vào POM đã được cấu hình, không phải một POM đứng riêng.

### Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Với Spring Boot 3.x, dùng namespace `jakarta.validation`. Nếu thiếu một Bean Validation provider, chỉ khai báo `@Validated` hoặc `@NotBlank` không đảm bảo mọi constraint được thực thi như dự kiến.

Không nhầm `spring-boot-configuration-processor` — phục vụ metadata cho IDE trong lúc compile — với `spring-boot-starter-validation` phục vụ validation lúc runtime.

## 6. Khai báo bean cấu hình

Tạo `src/main/java/com/example/demo/config/DeliveryProperties.java`:

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
@ConfigurationProperties(
        prefix = "demo.delivery",
        ignoreUnknownFields = false
)
public record DeliveryProperties(
        @NotNull Boolean enabled,
        @NotBlank String endpoint,
        @NotNull Duration requestTimeout,
        @NotNull @Min(1) @Max(5) Integer maxAttempts
) {
    public DeliveryProperties {
        if (requestTimeout != null
                && (requestTimeout.isZero()
                    || requestTimeout.isNegative())) {
            throw new IllegalArgumentException(
                    "demo.delivery.request-timeout must be positive"
            );
        }
    }
}
~~~

Các lựa chọn thiết kế:

- `Boolean` thay vì `boolean` để phân biệt “không khai báo” với `false`.
- `@NotNull` trên `enabled` yêu cầu có giá trị, nhưng cả `true` lẫn `false` đều hợp lệ.
- `@NotBlank` trên `endpoint` từ chối null, chuỗi rỗng và whitespace.
- `Duration` nhận các giá trị có thể chuyển đổi như `5s` theo Binder.
- `@NotNull` trên timeout đảm bảo không thiếu.
- Constructor invariant từ chối `0s` và thời gian âm.
- `Integer` + `@NotNull` + `@Min`/`@Max` phân biệt thiếu với giá trị ngoài khoảng.
- `ignoreUnknownFields=false` giúp từ chối khóa thừa nằm trong namespace được class sở hữu, khi nguồn cấu hình cho phép phát hiện unbound properties.

**Không in `endpoint` hoặc toàn bộ properties bean vào exception trong dự án thực tế** nếu endpoint có thể chứa query token hoặc userinfo. Ở đây chỉ hiển thị tên khóa trong message của invariant.

Trong bài này record không có default: đó là quyết định có chủ ý để việc thiếu một trong bốn property trở thành lỗi.

## 7. Đăng ký properties bean và ứng dụng

`DemoApplication.java`:

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

`@ConfigurationPropertiesScan` cho phép Spring Boot phát hiện class `DeliveryProperties` dưới package thích hợp. Một lựa chọn khác là `@EnableConfigurationProperties(DeliveryProperties.class)`.

Nếu quên đăng ký properties bean, có thể không có bean để validate và kết quả bài thực hành bị hiểu sai. **Annotation `@ConfigurationProperties` trên class không nên được coi là bằng chứng rằng mọi đường tạo bean đã được thiết lập.**

Không đồng thời dùng nhiều chiến lược registration một cách tùy tiện khiến bean bị đăng ký trùng.

## 8. Một runner chứng minh startup thành công

`src/main/java/com/example/demo/service/DeliveryRunner.java`:

~~~java
package com.example.demo.service;

import com.example.demo.config.DeliveryProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRunner implements CommandLineRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DeliveryRunner.class);

    private final DeliveryProperties properties;

    public DeliveryRunner(DeliveryProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        log.info(
                "Delivery configuration valid: enabled={} timeout={} maxAttempts={}",
                properties.enabled(),
                properties.requestTimeout(),
                properties.maxAttempts()
        );
    }
}
~~~

Runner log ba trường được xem là phi bí mật trong ví dụ; không log nguyên record vì một phiên bản tương lai có thể thêm API token.

Khi properties bean tạo thành công, runner sẽ được gọi sau khi context được chuẩn bị theo vòng đời Spring Boot. Khi binding/validation thất bại trong startup, bạn sẽ không nhìn thấy thông điệp “Delivery configuration valid” từ runner này.

Nhưng **việc không thấy log runner tự nó chưa chứng minh lỗi validation**, vì ứng dụng cũng có thể lỗi do dependency, mã Java hoặc logger. Phải đọc cause chain.

## 9. Tạo `application.yml` hợp lệ

~~~yaml
spring:
  application:
    name: config-fail-fast-demo

demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

Đây là cấu hình **không có credential thật** và đủ bốn field cần thiết.

Với runner trên, ứng dụng không cần gọi endpoint thật. Việc domain minh họa không phục vụ request không ảnh hưởng đến phép thử chỉ kiểm tra cấu hình.

Nếu hệ thống thật tạo HTTP client và kết nối upstream ngay lúc startup, cần thiết kế mock hoặc tách rõ lỗi kết nối khỏi lỗi config validation.

## 10. Chạy cấu hình hợp lệ trước

Ví dụ Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Kết quả mong đợi: context khởi động thành công và runner log một thông điệp tương tự:

~~~text
Delivery configuration valid: enabled=true timeout=PT5S maxAttempts=3
~~~

`Duration.toString()` hiển thị dạng ISO-8601, nên `5s` có thể được log là `PT5S`. Không dùng so sánh từng ký tự của startup banner/stack trace làm tiêu chí duy nhất, vì format phụ thuộc phiên bản Boot và logger.

Dừng process sau khi đã quan sát baseline trước khi chuyển sang các ca lỗi khác. Mỗi ca lỗi nên dùng **cấu hình xuất phát giống nhau**, chỉ thay đúng property đang thử.

## 11. Cách tổ chức thử nghiệm không làm hỏng baseline

Để tránh sửa file duy nhất rồi quên hoàn nguyên, có thể:

1. Giữ `application.yml` hợp lệ trong repository.
2. Dùng command-line argument override một giá trị để tạo lỗi.
3. Hoặc tạo file profile riêng chứa một ca lỗi.
4. Dùng test code để truyền `withPropertyValues(...)` trực tiếp.
5. Chạy mỗi ca trong một process/test context độc lập.
6. Không commit cấu hình sai vào baseline đã duyệt.

Dùng CLI để **minh họa lỗi phi bí mật** như timeout hoặc retry là phù hợp trong bài học. Không truyền mật khẩu/token thật qua command-line arguments vì có thể xuất hiện trong process inspection, shell history và logs.

Trong thực hành thủ công, bắt đầu từ cấu hình hợp lệ rồi đưa đúng một lỗi vào mỗi lần chạy để dễ liên kết triệu chứng với nguyên nhân.

## 12. Ca lỗi 1 — Thiếu thuộc tính bắt buộc `endpoint`

Bỏ dòng:

~~~yaml
endpoint: "https://delivery.example.org/v1/events"
~~~

Cấu hình còn:

~~~yaml
demo:
  delivery:
    enabled: true
    request-timeout: 5s
    max-attempts: 3
~~~

Với record `DeliveryProperties`:

~~~java
@NotBlank String endpoint
~~~

giá trị thiếu có thể khiến `endpoint` thành null trong quá trình tạo properties object. Khi validation chạy, `@NotBlank` từ chối nó.

Một thông báo lỗi khởi động **có thể** chứa các ý:

~~~text
Failed to bind properties under 'demo.delivery'
Property: demo.delivery.endpoint
Reason: must not be blank
~~~

Đây chỉ là **minh họa về nội dung**. Không giả định tất cả Spring Boot versions hoặc logger in đúng các dòng trên. Ở một số phiên bản, top-level exception được bọc, property name hoặc reason nằm trong cause chain.

Điều cần xác nhận:

- Context failed.
- Nguyên nhân bắt nguồn từ configuration binding/validation.
- Field `endpoint` là field vi phạm.
- Runner thông báo cấu hình hợp lệ không được thực thi.

Nếu test chạy mà vẫn thành công, kiểm tra `@Validated`, validation provider, bean registration và có nguồn cấu hình ưu tiên khác đang cấp endpoint không.

## 13. Ca lỗi 2 — Khóa có mặt nhưng giá trị rỗng

Cấu hình:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: ""
    request-timeout: 5s
    max-attempts: 3
~~~

`@NotBlank` cũng phải từ chối chuỗi rỗng.

Thử biến thể:

~~~yaml
endpoint: "   "
~~~

Vì toàn whitespace, `@NotBlank` tiếp tục từ chối.

Bài học:

- `@NotNull` chỉ phát hiện null, không từ chối `""`.
- `@NotEmpty` từ chối chuỗi rỗng nhưng có thể chấp nhận whitespace.
- `@NotBlank` phù hợp khi String cần có ký tự không trắng.

Không gộp thiếu và rỗng thành một trường hợp khi phân tích lỗi; hai trạng thái có thể đến từ các nguyên nhân triển khai khác nhau.

## 14. Ca lỗi 3 — Sai kiểu `max-attempts`

Giữ các field khác hợp lệ và sửa:

~~~yaml
max-attempts: many
~~~

Java target là:

~~~java
Integer maxAttempts
~~~

Binder không thể chuyển `many` sang số nguyên. Lỗi này xảy ra ở bước **conversion/binding**, có thể trước Bean Validation vì chưa tạo được object hợp lệ.

Một thông điệp điển hình có thể chứa:

~~~text
Failed to bind ... 'demo.delivery.max-attempts'
Failed to convert from type java.lang.String to type java.lang.Integer
~~~

Đừng coi đây là “`@Min(1)` không hoạt động”. `@Min` kiểm tra số đã được chuyển thành công, trong khi trường hợp này chưa có `Integer` hợp lệ.

Bước chẩn đoán:

1. Xác định property nào được Binder đọc.
2. Kiểm tra kiểu Java đích.
3. Xác định giá trị thô hoặc origin nếu có thể làm an toàn.
4. Sửa nguồn đang có ưu tiên cao nhất.
5. Chạy lại baseline.

Nếu một field chứa secret, không echo giá trị thô của nó ra log/ticket. Ở đây `many` là dữ liệu phi bí mật dùng để học.

## 15. Ca lỗi 4 — Đúng kiểu nhưng sai khoảng cho phép

Sửa:

~~~yaml
max-attempts: 0
~~~

Hoặc:

~~~yaml
max-attempts: 9
~~~

Hai giá trị đều có thể chuyển thành `Integer`. Nhưng:

~~~java
@Min(1) @Max(5)
Integer maxAttempts
~~~

yêu cầu giá trị từ 1 đến 5.

Với 0, `@Min(1)` bị vi phạm. Với 9, `@Max(5)` bị vi phạm. Đây là **Bean Validation failure**, khác với conversion failure ở phần trước.

Điểm cần quan sát:

- Quá trình bind sang Java integer không phải vấn đề chính.
- Validation phát hiện giá trị không đạt policy.
- Application context thất bại trước khi runner báo thành công.
- Không sửa bằng cách đặt `ignoreInvalidFields=true` để bỏ qua lỗi.

Một constraint chính xác giúp tránh trường hợp ứng dụng chạy với số lần retry gây quá tải upstream hoặc mất khả năng phục hồi.

## 16. Ca lỗi 5 — Sai định dạng `Duration`

Sửa:

~~~yaml
request-timeout: tomorrow
~~~

Target:

~~~java
Duration requestTimeout
~~~

Spring Boot Binder hỗ trợ các cách biểu diễn duration như `5s`, `250ms`, `2m` hoặc ISO-8601 duration theo quy tắc của framework. Chuỗi `tomorrow` không phải duration hợp lệ.

Kết quả mong đợi là lỗi conversion.

Để sửa:

~~~yaml
request-timeout: 5s
~~~

hoặc một duration hợp lệ khác. Không chỉ thay đổi sang số 5 mà không hiểu đơn vị mặc định của binding; với duration không ghi đơn vị, cách diễn giải phụ thuộc quy tắc bind và annotation như `@DurationUnit` nếu có.

Một cấu hình có thể đúng về YAML syntax nhưng sai kiểu nghiệp vụ tại Binder.

## 17. Ca lỗi 6 — `Duration.ZERO` hợp lệ về kiểu nhưng sai chính sách

Sửa:

~~~yaml
request-timeout: 0s
~~~

`0s` có thể bind thành `Duration.ZERO` — tức type conversion thành công. Tuy nhiên record constructor có invariant:

~~~java
if (requestTimeout != null
        && (requestTimeout.isZero()
            || requestTimeout.isNegative())) {
    throw new IllegalArgumentException(
            "demo.delivery.request-timeout must be positive");
}
~~~

Do đó startup có thể thất bại từ việc tạo record, thay vì một `@NotNull` constraint.

So sánh:

| Value | Kết quả chuyển kiểu | Kết quả hợp đồng |
| --- | --- | --- |
| `5s` | Hợp lệ | Hợp lệ |
| `0s` | Hợp lệ | Sai — không dương |
| `-2s` | Hợp lệ nếu parser chấp nhận biểu diễn | Sai — âm |
| `tomorrow` | Sai | Chưa tới bước invariant |
| Thiếu `request-timeout` | Có thể thành null | `@NotNull` từ chối |

Đây là lý do **conversion** và **validation/invariant** cần được xem là hai tầng riêng.

## 18. Ca lỗi 7 — Thiếu Boolean bắt buộc

Xóa:

~~~yaml
enabled: true
~~~

Class dùng:

~~~java
@NotNull Boolean enabled
~~~

Không có default nên khi không cấp giá trị, `enabled` có thể là null và bị validator từ chối.

Nếu thay bằng primitive:

~~~java
boolean enabled
~~~

giá trị vắng mặt có thể được biểu diễn bằng `false`, khiến ứng dụng không phân biệt người triển khai cố ý tắt feature hay quên khai báo.

Bài này dùng `Boolean` để required nghĩa là **phải có quyết định rõ ràng**. Trong hệ thống khác, feature có default false an toàn có thể được thiết kế là optional; lựa chọn này phải xuất phát từ hợp đồng cấu hình.

## 19. Ca lỗi 8 — Gõ sai tên property

Cấu hình:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
    max-attemtps: 4
~~~

Khóa `max-attemtps` là typo; record chỉ có `maxAttempts`.

Vì class có:

~~~java
@ConfigurationProperties(
    prefix = "demo.delivery",
    ignoreUnknownFields = false
)
~~~

Spring Boot có thể từ chối property không được bind khi Binder phát hiện nó trong nguồn cấu hình có khả năng liệt kê tên property.

Quan trọng: `@NotNull` hoặc `@Min` **không tự phát hiện một key dư**. Nếu giá trị hợp lệ `max-attempts=3` vẫn có mặt, bean có thể thỏa mọi constraint nhưng chứa typo bị bỏ qua nếu không bật strict unknown-fields checking.

`ignoreUnknownFields=false` không phải công cụ tìm mọi typo ở mọi namespace. Một lỗi chuyển prefix thành `demo.deliveries` có thể nằm ngoài root `demo.delivery`. Cần test cả sự tồn tại của root và các field bắt buộc.

## 20. Ca lỗi 9 — Có khóa nhưng bị nguồn khác override

Baseline:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

Chạy qua command line với một giá trị sai:

~~~bash
java -jar target/config-fail-fast-demo.jar --demo.delivery.max-attempts=10
~~~

Đường dẫn JAR là ví dụ; dùng tên file build thực tế. Trong thứ tự ưu tiên thông thường của Spring Boot, command-line property có thể override cấu hình file. Vì 10 vượt `@Max(5)`, application context nên từ chối startup.

Kiểm tra khi lỗi:

- Command-line argument có được chuyển đến ứng dụng không?
- Property name đúng không?
- Có source khác còn ưu tiên cao hơn không?
- Bean validation có đang chạy không?

Đừng chỉ mở YAML và nói "max-attempts là 3 nên validation không thể fail". **Effective value** có thể đến từ nguồn khác.

## 21. Ca lỗi 10 — Biến môi trường ghi đè

Property canonical:

~~~text
demo.delivery.max-attempts
~~~

Tên environment variable thường dùng:

~~~text
DEMO_DELIVERY_MAXATTEMPTS
~~~

Một shell Unix/Linux minh họa:

~~~bash
DEMO_DELIVERY_MAXATTEMPTS=8 java -jar target/config-fail-fast-demo.jar
~~~

Một lệnh PowerShell minh họa:

~~~powershell
$env:DEMO_DELIVERY_MAXATTEMPTS = "8"
java -jar .\target\config-fail-fast-demo.jar
Remove-Item Env:DEMO_DELIVERY_MAXATTEMPTS
~~~

Với convention Spring Boot, tên env thường được tạo bằng cách thay dấu chấm bằng gạch dưới, bỏ dấu gạch ngang và uppercase. Nếu ứng dụng nhận giá trị 8 từ environment, `@Max(5)` cần từ chối.

Sau test, gỡ biến môi trường hoặc dùng process test cô lập; nếu quên, các ca sau có thể vẫn fail dù file YAML đã được sửa đúng.

Không dùng environment variable chứa token thật cho một bài test in toàn bộ diagnostic; secret vẫn có thể bị lộ qua process inspection, debug hoặc logs.

## 22. Ca lỗi 11 — Import vị trí cấu hình bắt buộc không tồn tại

Trong `application.yml` có thể đặt:

~~~yaml
spring:
  config:
    import: "file:./required-override.properties"
~~~

Nếu file `required-override.properties` không tồn tại ở vị trí runtime và import là bắt buộc, Spring Boot Config Data có thể từ chối startup **trước bước bind `DeliveryProperties`**.

Đây là lỗi **Config Data location**, không phải lỗi `@NotBlank` của endpoint.

Nếu viết:

~~~yaml
spring:
  config:
    import: "optional:file:./required-override.properties"
~~~

thì việc **không tồn tại của location** có thể được cho phép. Nhưng điều đó không biến các property trong location thành optional về mặt nghiệp vụ.

Ví dụ `endpoint` vẫn là required nếu properties bean được tạo và validation hoạt động. Một file location có mặt cũng chưa chứng minh mọi khóa bên trong đều có giá trị.

Không đánh dấu mọi import production là `optional:` chỉ để startup “dễ qua” khi mount/config deployment gặp lỗi.

## 23. Ca lỗi 12 — Profile thiếu cấu hình

Ví dụ file chung có những giá trị không đủ để chạy:

~~~yaml
# application.yml
spring:
  application:
    name: config-fail-fast-demo
~~~

Profile local:

~~~yaml
# application-local.yml
demo:
  delivery:
    enabled: true
    endpoint: "https://local.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 2
~~~

Profile prod:

~~~yaml
# application-prod.yml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 3s
    max-attempts: 3
~~~

Chạy với profile local:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=local
~~~

Với profile prod:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=prod
~~~

Nếu không kích hoạt profile mà file chung không có `demo.delivery.*`, ứng dụng có thể thất bại khi tạo bean cấu hình bắt buộc. Tuy nhiên, chính xác exception còn phụ thuộc vào đường constructor binding và bean registration; hãy xác nhận qua test.

**Không đặt secret thật vào `application-prod.yml`** chỉ vì file theo profile chỉ được kích hoạt ở production. File vẫn có thể nằm trong Git/JAR.

## 24. Rủi ro có nhiều profile hoạt động

Giả sử chạy:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=local,prod
~~~

Nếu cả hai file profile cùng định nghĩa `demo.delivery.endpoint` hoặc `max-attempts`, kết quả phụ thuộc quy tắc Config Data và thứ tự profile/nguồn trong phiên bản Spring Boot đang dùng.

Một quy trình tốt:

1. Định nghĩa tổ hợp profile nào được phép.
2. Tránh cho production mang profile local hoặc test ngoài ý định.
3. Lưu active profiles trong release metadata.
4. Có integration test cho tổ hợp thực tế.
5. Kiểm tra effective values phi bí mật.
6. Đưa chính sách môi trường vào deployment pipeline.

Validation có thể xác nhận từng field đúng dạng nhưng **không tự xác nhận chính sách tổ hợp profile**. Nếu cần cấm `local` ở production, thêm deploy-time guardrail hoặc một kiểm tra startup phù hợp.

## 25. Ba lớp lỗi cần phân biệt trên startup

| Nhóm | Ví dụ | Nơi dễ quan sát |
| --- | --- | --- |
| Config Data loading | Import file không có | Trước hoặc trong chuẩn bị environment |
| Conversion/binding | `max-attempts=many` | Bind exception/conversion cause |
| Bean validation | `endpoint=""`, `max-attempts=9` | Validation failure/constraint details |
| Constructor invariant | `request-timeout=0s` | Exception từ constructor |
| Unknown field | `max-attemtps` | Unbound/unknown property handling |
| Bean registration | Quên scan/enable properties | Bean không có hoặc bean creation error |
| Runtime external failure | API down, credential revoked | Client/health/startup probe tùy thiết kế |

Lưu ý lỗi ở lớp runtime external có thể **không** làm startup thất bại nếu không có startup validation riêng. Một request thất bại sau khi service nhận traffic không có nghĩa configuration binder đã sai.

Một phép thử fail fast nên khẳng định đúng lớp lỗi. Chỉ quan sát process exit code khác 0 chưa đủ để nói validation đang hoạt động.

## 26. Đọc log startup đúng cách

Khi chạy cấu hình sai:

1. Xác định lỗi đầu tiên liên quan tới configuration.
2. Xem property name hoặc prefix mà framework đang bind.
3. Xác định type Java đích.
4. Xem lỗi là không có giá trị, parse thất bại hay constraint.
5. Nếu framework báo origin file/dòng, kiểm tra đúng nguồn đó.
6. Xem có override từ env/CLI không.
7. Đọc cause chain khi exception top-level chỉ nói `BeanCreationException` hoặc `ConfigurationPropertiesBindException`.
8. Không chỉ đọc vài dòng cuối mà bỏ qua nguyên nhân gốc.
9. Không copy toàn bộ log chứa credential thật vào ticket/chat.
10. Sửa cấu hình rồi khởi chạy lại bằng trạng thái sạch.

Ví dụ log mang tính minh họa:

~~~text
APPLICATION FAILED TO START

Failed to bind properties under 'demo.delivery'

Property: demo.delivery.max-attempts
Value: 9
Reason: must be less than or equal to 5
~~~

Tên field, định dạng log và exception chain có thể khác. Chương trình cũng có thể tạo thông báo riêng do constructor invariant.

## 27. Không tin một thông báo lỗi cố định khi viết test

Test không nên chỉ tìm chuỗi:

~~~text
APPLICATION FAILED TO START
~~~

vì Spring Boot có thể thay đổi presentation hoặc logger configuration.

Thay vào đó:

- Dùng `ApplicationContextRunner` hoặc test context tương đương.
- Assert context has failed.
- Truy cập startup failure/cause chain.
- Kiểm tra exception root/cause liên quan tới binding/validation.
- Kiểm tra tên property được báo khi API hỗ trợ.
- Với lỗi constructor invariant, assert message do chính code mình định nghĩa.

Cũng không nên test quá chặt từng dòng startup report, vì đó là presentation layer không phải hợp đồng API ổn định của ứng dụng.

## 28. Viết test bằng `ApplicationContextRunner`

`ApplicationContextRunner` của `spring-boot-test` giúp tạo một context nhỏ với property values, không cần mở HTTP port.

Tạo `src/test/java/com/example/demo/config/DeliveryPropertiesTests.java`:

~~~java
package com.example.demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Config {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(Config.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.endpoint=https://delivery.example.org/v1/events",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=3"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);
            assertThat(props.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void missingEndpointFails() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=3"
        ).run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void retryAboveLimitFails() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.endpoint=https://delivery.example.org/v1/events",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=9"
        ).run(context ->
                assertThat(context).hasFailed());
    }
}
~~~

Các test `hasFailed()` là mức tối thiểu để học. Trong dự án thật, thêm assertion về **đúng nguyên nhân**; nếu thiếu validation provider mà context fail vì lỗi bean không liên quan, test không được xem là chứng minh đúng logic.

Khi có các JUnit/AssertJ versions được quản lý đúng bởi Spring Boot, chạy:

~~~bash
./mvnw test
~~~

hoặc:

~~~bash
./gradlew test
~~~

## 29. Test sai kiểu độc lập với Bean Validation

Một test bổ sung:

~~~java
@Test
void invalidIntegerFailsDuringConversion() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=many"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

Ở đây mong đợi một binding/conversion failure. Để test tốt hơn, inspect cause chain và xác nhận lỗi liên quan `demo.delivery.max-attempts` hoặc conversion sang Integer.

Không sử dụng cùng một input vừa sai kiểu vừa thiếu field khác nếu mục tiêu của test là chứng minh conversion. Một lỗi khác có thể xảy ra trước và che nguyên nhân muốn kiểm tra.

## 30. Test blank value riêng

~~~java
@Test
void blankEndpointFailsValidation() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=   ",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=3"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

Một property string trong `ApplicationContextRunner` được cấp bằng cặp `name=value`. Với whitespace, nên đảm bảo value đúng là các ký tự muốn thử và kiểm tra behavior tương ứng của nguồn test. Có thể thêm test `endpoint=` cho chuỗi rỗng.

Nếu thiếu endpoint không fail, kiểm tra:

- `DeliveryProperties` có thực sự được tạo không?
- Có `@Validated` không?
- Có Bean Validation provider hoạt động không?
- Có nguồn property nào cấp giá trị không?
- Record có bị thay đổi default không?
- Test có vô tình tắt validation không?

## 31. Test giới hạn thời lượng

Với constructor invariant:

~~~java
@Test
void zeroTimeoutFailsEarly() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=0s",
            "demo.delivery.max-attempts=3"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

Test này chủ đích kiểm tra lỗi từ constructor. Nếu muốn thử `@NotNull`, bỏ timeout hoàn toàn trong một test riêng.

Không dùng `@Positive` trên `java.time.Duration` rồi mặc định rằng mọi Bean Validation provider sẽ hiểu constraint như kiểu số. Dùng custom validator hoặc constructor invariant cho quy tắc duration dương.

## 32. Test unknown property

Với `ignoreUnknownFields=false`:

~~~java
@Test
void unknownPropertyFails() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=3",
            "demo.delivery.max-attemtps=4"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

Property `max-attemtps` là typo. Vì test property source có tên key cụ thể, strict unknown-field behavior có thể phát hiện unbound key.

Nếu namespace của hệ thống thật do nhiều beans chia sẻ, đừng áp dụng strict policy lên một prefix quá rộng mà không xác định quyền sở hữu schema.

Test unknown property và test missing property là hai việc khác nhau. Một key sai prefix có thể nằm ngoài root và không được unbound handler thấy.

## 33. Kiểm tra fail-fast khi thiếu toàn bộ root

Với baseline chỉ có:

~~~properties
spring.application.name=config-fail-fast-demo
~~~

không có key nào thuộc `demo.delivery`, cần xác định cách bean được đăng ký và được tạo khi toàn bộ prefix không hiện diện.

Một record có toàn bộ field required có thể fail khi được bind/khởi tạo/validate, nhưng **không nên suy đoán exception trước khi chạy test trên Spring Boot version thật**. Một số đường binding khi không có dữ liệu có thể không tạo object theo cách giống khi có partial keys.

Cách làm thực tế:

1. Viết integration test chạy app với nguồn được kiểm soát và không có `demo.delivery.*`.
2. Assert startup failed vì cấu hình.
3. Nếu không fail như hợp đồng, bổ sung cơ chế fail-fast tường minh: bean yêu cầu root, custom precondition hoặc startup check có mục tiêu rõ.
4. Không để ứng dụng lặng lẽ sử dụng object null/default sai.
5. Ghi trường hợp này vào runbook triển khai.

Đây là lý do test “thiếu một field” chưa thay thế được test “thiếu nguyên namespace”.

## 34. Khi nào dùng `@DefaultValue`?

Một setting optional có default an toàn:

~~~java
@ConfigurationProperties(prefix = "demo.retry")
public record RetryProperties(
        @org.springframework.boot.context.properties.bind.DefaultValue("3")
        int maxAttempts
) {}
~~~

Khi property thiếu, Binder có thể cấp default 3. Nhưng:

~~~properties
demo.retry.max-attempts=abc
~~~

sẽ không tự được sửa thành 3. Khi input được cấp nhưng sai conversion, cần báo lỗi.

Bài thực hành dùng required fields nên không dùng default trong `DeliveryProperties`. Nếu thêm default vô điều kiện cho một required property, test missing có thể chuyển từ fail sang pass và làm thay đổi hợp đồng.

Quy tắc:

- Vắng mặt **hợp lệ** → default được cân nhắc.
- Vắng mặt **là lỗi** → không che bằng default.
- Giá trị được cấp **sai** → validation/conversion báo lỗi.
- Giá trị được cấp nhưng **không được bind** → policy unknown fields/schema kiểm tra.

## 35. `ignoreInvalidFields` không phải giải pháp khắc phục

Một anti-pattern:

~~~java
@ConfigurationProperties(
        prefix = "demo.delivery",
        ignoreInvalidFields = true
)
~~~

Đặt `ignoreInvalidFields=true` chỉ để cấu hình sai không làm startup fail có thể khiến ứng dụng chạy với giá trị mặc định hoặc trạng thái không mong muốn.

Bài thực hành cần **quan sát lỗi** và sửa nguồn:

- Sai số nguyên → sửa input sang integer hợp lệ.
- Sai duration → sửa thành biểu diễn duration hợp lệ.
- Vi phạm constraint → sửa về phạm vi cho phép hoặc thay policy có review.
- Thiếu key → cấp key ở đúng nguồn.
- Typos → sửa tên property.

Không nên chuyển từ fail-fast sang ignore-errors một cách âm thầm ở production.

## 36. Cách nhận diện nguồn gây lỗi

Spring Boot có thể lấy một property từ nhiều nguồn. Ví dụ:

~~~yaml
demo:
  delivery:
    max-attempts: 3
~~~

Nhưng container environment cấp:

~~~text
DEMO_DELIVERY_MAXATTEMPTS=9
~~~

Khi Binder nhận 9, constraint `@Max(5)` thất bại. Sửa YAML từ 3 thành 2 không giúp nếu environment vẫn override 9.

Để tìm nguồn:

1. Kiểm tra deployment manifest/pod template.
2. Kiểm tra lệnh start và system properties được cho phép.
3. Kiểm tra Config Data imports và profile.
4. Dùng thông tin origin từ startup failure nếu framework cung cấp.
5. Với môi trường được bảo vệ, dùng diagnostic chỉ cho các field phi bí mật đã allowlist.
6. Không công khai `/actuator/env` hoặc dump toàn bộ environment chỉ để debug.
7. Sửa nơi có quyền quyết định effective value, không sửa nơi bị override.

Nếu muốn kiểm tra exact source ordering, tham khảo tài liệu Externalized Configuration của Spring Boot version dự án đang dùng.

## 37. Test profile gần thực tế

`ApplicationContextRunner` thử binding với property values nhưng không phải luôn tái tạo đầy đủ pipeline Config Data như một ứng dụng `SpringApplication` đọc `application-prod.yml`.

Vì vậy, bổ sung **integration test** hoặc một lần chạy thật với profile cần kiểm chứng:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Cú pháp này dùng tham số plugin Spring Boot Maven trong dự án phù hợp. Với Gradle:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=prod'
~~~

Cần đảm bảo profile file có đầy đủ cấu hình phi bí mật và secret được cấp qua nguồn test phù hợp, không truy cập production credential từ CI.

Các trường hợp cần test:

- Chỉ `local`.
- Chỉ `prod`.
- Không bật profile.
- Tổ hợp profile được cho phép.
- Profile file thiếu key.
- Env var ghi đè profile file với giá trị invalid.
- Import config file thiếu.
- Secret reference không có hoặc blank.

Mục tiêu là phát hiện khác biệt giữa test binding đơn lẻ và hệ thống load Config Data thực tế.

## 38. Fail fast cho secret cần cẩn trọng khi log

Một property có thể là secret:

~~~yaml
demo:
  delivery:
    api-token: "${DELIVERY_API_TOKEN}"
~~~

Nếu secret required, có thể khai báo `@NotBlank String apiToken` ở một properties bean được validation phù hợp. Nhưng khi bean lỗi, không nên ghi:

~~~java
log.error("Bad token value={}", apiToken);
~~~

hoặc:

~~~java
throw new IllegalArgumentException(
        "Invalid token: " + apiToken
);
~~~

Thông báo nên nêu tên property và rule, không echo nội dung. Trong test dùng sentinel giả:

~~~text
TEST_ONLY_DELIVERY_TOKEN
~~~

Không dùng credential thật trong unit test, terminal screenshots hay tài liệu.

Nếu một deployment sử dụng secret manager/mounted file, fail-fast có thể bao gồm kiểm tra file/reference và required validation; không tự coi việc có một token String là bằng chứng upstream đã xác thực thành công.

## 39. Một ví dụ nâng cao: required theo feature mode

Có những trường hợp `endpoint` và token chỉ cần khi feature được bật:

~~~yaml
demo:
  delivery:
    enabled: false
~~~

Một record có conditional invariant:

~~~java
@ConfigurationProperties(prefix = "demo.delivery")
public record DeliveryFeatureProperties(
        boolean enabled,
        String endpoint,
        String apiToken
) {
    public DeliveryFeatureProperties {
        if (enabled) {
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalArgumentException(
                        "demo.delivery.endpoint is required when enabled");
            }
            if (apiToken == null || apiToken.isBlank()) {
                throw new IllegalArgumentException(
                        "demo.delivery.api-token is required when enabled");
            }
        }
    }
}
~~~

Ở mode disabled, thiếu endpoint/token có thể hợp lệ. Ở mode enabled, chúng phải có nội dung. Điều kiện này khác với `DeliveryProperties` của bài lab chính, nơi endpoint luôn required.

Nếu production policy yêu cầu feature enabled, đừng dùng `boolean enabled` mặc định false rồi âm thầm chạy NoOp mode. Cần policy theo environment và test deployment riêng.

## 40. Làm sao để dừng trước khi nhận traffic?

Fail-fast configuration validation thường được thực thi trong lúc application context khởi động. Với web application, nó giúp ngăn việc ứng dụng đạt trạng thái ready khi bean cấu hình không tạo được.

Tuy nhiên, với một ứng dụng có nhiều asynchronous startup tasks hoặc tự bắt exception:

~~~java
try {
    initializeClient();
} catch (Exception ex) {
    log.warn("Client initialization failed, continuing");
}
~~~

ứng dụng có thể tiếp tục chạy dù integration quan trọng chưa sẵn sàng.

Đối với dependency quan trọng:

- Không nuốt exception cấu hình bắt buộc.
- Không fallback sang anonymous/stub mode ngoài policy.
- Nếu remote connection là yêu cầu readiness, triển khai readiness/health check phù hợp.
- Cân nhắc tránh kết nối network thật trong Bean Validation nếu nó làm startup quá chậm hoặc bất ổn.
- Phân biệt startup validation (schema/value) với runtime health (dependency readiness).
- Test orchestration không đưa traffic cho workload chưa ready.

Trong bài lab, không có network call nên nguyên nhân startup failure có thể được cô lập vào configuration.

## 41. Tác động trong container và orchestration

Khi một process Spring Boot không khởi động vì cấu hình sai:

- Local terminal có thể trả về exit code khác 0.
- Docker container có thể dừng.
- Kubernetes có thể thử khởi động lại container theo restart policy, dẫn đến lặp khởi động thất bại.
- Deployment có thể không đạt readiness và rollout kéo dài/không thành công.
- Hệ thống cảnh báo có thể ghi nhận startup failure hoặc restart count tăng.

Không nên giải quyết bằng cách tăng restart count hoặc tắt validation. Cần sửa giá trị cấu hình, secret reference hoặc artifact triển khai.

Một runbook cần lưu:

~~~text
Application version
Config revision
Active profile
Relevant non-secret property names
Source of override
Root-cause category
Fix / rollback decision
Validation result after redeploy
~~~

Không lưu secret plaintext hoặc full environment dump vào incident report.

## 42. Quan sát mã thoát của process

Trên Linux/macOS, sau khi process kết thúc:

~~~bash
echo $?
~~~

Trong PowerShell:

~~~powershell
$LASTEXITCODE
~~~

Thông thường, startup exception không được xử lý khiến chương trình thất bại và launcher trả non-zero. Nhưng nếu một wrapper/script hoặc IDE bắt lỗi và trả code khác, số exit code quan sát có thể không đại diện trực tiếp cho Spring context.

Do đó nên kết hợp:

1. Log/cause chain cho thấy lỗi config.
2. Process không đạt trạng thái ready.
3. Runner không báo success.
4. Test `ApplicationContextRunner` hoặc integration test thất bại đúng nguyên nhân.
5. Triển khai không được đánh dấu healthy.

Không viết bài test kiểu “có exit code 1 nghĩa chắc chắn thiếu endpoint”.

## 43. Bảng xử lý lỗi nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Thiếu `endpoint` nhưng app vẫn chạy | Bean không được đăng ký hoặc validation không chạy | Kiểm tra scan/enable, provider, test |
| `endpoint=""` không bị từ chối | Dùng `@NotNull` thay vì `@NotBlank` | Kiểm tra constraint |
| `max-attempts=many` gây lỗi | Chuyển String sang Integer thất bại | Xem conversion cause |
| `max-attempts=9` bị từ chối | Vi phạm `@Max(5)` | Xem validation |
| `request-timeout=0s` thất bại | Constructor invariant yêu cầu dương | Xem exception cause |
| Thiếu `enabled` nhưng app dùng false | Primitive hoặc default che thiếu | Dùng Boolean + `@NotNull` |
| `max-attemtps` bị bỏ qua | Unknown field policy chưa chặt | `ignoreUnknownFields=false` hoặc schema lint |
| YAML đúng nhưng startup sai | Env/CLI override | Tìm effective source |
| Một file import không tồn tại | Config Data location bắt buộc | Kiểm tra `spring.config.import` |
| File import optional bỏ qua lỗi | `optional:` áp dụng cho location | Validate key required riêng |
| Test `hasFailed()` pass vì bean lỗi khác | Assert quá rộng | Xem root cause đúng property |
| Dev pass nhưng prod fail | Profile/secret/overlay khác | Test profile matrix |
| Prod chạy ở local mode | Active profile/policy sai | Guardrail deployment |
| App restart liên tục trong Pod | Startup failure chưa được xử lý | Kiểm tra container logs và config revision |
| Log chứa token khi fail | Exception/record `toString()` in secret | Redact và không log giá trị |

## 44. Checklist thực hành theo từng bước

### Chuẩn bị

- [ ] App có `@ConfigurationProperties` được đăng ký.
- [ ] Có Bean Validation provider.
- [ ] Có `@Validated` trên properties bean.
- [ ] Các field required dùng wrapper và constraints thích hợp.
- [ ] Có invariant cho Duration dương.
- [ ] Không có credential thật trong file hoặc test.
- [ ] Có baseline `application.yml` hợp lệ.

### Thử lỗi

- [ ] Bỏ endpoint.
- [ ] Đặt endpoint rỗng.
- [ ] Đặt endpoint chỉ có whitespace.
- [ ] Đặt max-attempts là chữ.
- [ ] Đặt max-attempts bằng 0 hoặc vượt giới hạn.
- [ ] Đặt request-timeout sai định dạng.
- [ ] Đặt request-timeout bằng 0.
- [ ] Bỏ enabled.
- [ ] Thêm key typo.
- [ ] Override bằng env và CLI.
- [ ] Import một file bắt buộc không có.
- [ ] Test đúng active profile.

### Xác nhận kết quả

- [ ] Application context failed cho từng ca lỗi.
- [ ] Lỗi được phân loại conversion/validation/config loading/invariant.
- [ ] Cause chain hoặc property name phù hợp với ca test.
- [ ] Không có log startup success của runner trong các ca fail.
- [ ] Không có secret xuất hiện trong log.
- [ ] Sau khi khôi phục baseline, ứng dụng chạy thành công.
- [ ] CI chạy cùng các tests cho config artifact/version được triển khai.

## 45. Bài tập mở rộng

### Bài 1 — Phân loại

`max-attempts=many` và `max-attempts=9` đều thất bại. Vì sao khác nhau?

**Đáp án:** `many` không convert được sang Integer; `9` convert được nhưng vi phạm `@Max(5)`.

### Bài 2 — Null và blank

Với String `endpoint`, tại sao `@NotNull` chưa đủ?

**Đáp án:** chuỗi rỗng hoặc whitespace không null. Dùng `@NotBlank` khi yêu cầu có nội dung.

### Bài 3 — Primitive

Thiếu `enabled` mà code dùng `boolean`. Vì sao có thể không fail?

**Đáp án:** primitive có default false. Khi muốn bắt buộc explicit, dùng `Boolean` + `@NotNull`.

### Bài 4 — Default

Có `@DefaultValue("3")` cho maxAttempts. Thiếu property có thể dùng 3; vậy input `abc` có được tự sửa thành 3 không?

**Đáp án:** không. Default dành cho trường hợp vắng mặt, không phải sửa value sai kiểu.

### Bài 5 — Profile

`application-local.yml` có endpoint, `application-prod.yml` không có. Test local pass, prod fail. Đây có phải bug của Binder không?

**Đáp án:** không nhất thiết. Đây có thể là config contract theo môi trường chưa được đáp ứng; cần cấp required value cho prod hoặc thay thiết kế nếu endpoint thực sự optional.

### Bài 6 — Unknown key

`max-attemtps=4` xuất hiện nhưng `max-attempts=3` vẫn hợp lệ. Vì sao validation có thể pass?

**Đáp án:** validator kiểm tra object đã bind, không tự kiểm kê mọi key nguồn. Dùng strict unknown checking/schema lint nếu muốn bắt typo.

### Bài 7 — Config Data import

`optional:file:missing.properties` không có. Vì sao application vẫn có thể fail?

**Đáp án:** optional chỉ cho phép vị trí file vắng mặt; các field required trong bean vẫn có thể thiếu và bị validation từ chối.

### Bài 8 — Secret

Lỗi thiếu API token được xử lý bằng `log.error("token="+token)`. Có nên làm vậy?

**Đáp án:** không. Không log secret hoặc nội dung credential. Chỉ ghi tên property, trạng thái missing/invalid và error code an toàn.

### Bài 9 — Kiểm thử

Test chỉ assert `hasFailed()`. Làm sao bảo đảm fail vì validation thay vì lỗi khác?

**Đáp án:** đọc `getStartupFailure()` và cause chain; assert trường hợp đúng constraint/property mà test nhằm kiểm tra.

### Bài 10 — Runtime override

YAML có maxAttempts=3 nhưng env có 8. Cần sửa ở đâu?

**Đáp án:** tìm source có hiệu lực theo precedence; môi trường có thể override file. Sửa đúng nguồn hoặc policy override, không chỉ sửa YAML.

## 46. Một quy trình CI/CD để kiểm tra fail fast

Một pipeline gợi ý:

~~~text
Commit app + config changes
         |
         v
Check YAML syntax and secret scan
         |
         v
Compile application
         |
         v
Run ApplicationContextRunner tests
         |
         v
Run profile-specific integration tests
         |
         v
Render environment configuration
         |
         v
Deploy to staging
         |
         v
Smoke/readiness and config diagnostics
         |
         v
Approve canary/production
~~~

Nếu test fail vì cấu hình, **dừng pipeline** thay vì bỏ qua. Khi production rollout fail, áp dụng runbook sửa cấu hình hoặc khôi phục known-good app/config artifact.

Không đưa secret thô vào CI logs hoặc artifact. Với bài test required token, dùng sentinel giả; với production, kiểm tra secret reference và quyền workload bằng cơ chế được cấp phép.

Một configuration revision được commit chưa chắc là giá trị runtime cuối; cần có kiểm soát đối với env/CLI overrides và Config Data của môi trường triển khai.

## 47. Những giới hạn của cơ chế fail fast

Fail-fast bằng Bean Validation và Binder rất hữu ích, nhưng không chứng minh toàn bộ ứng dụng an toàn hoặc mọi dependency hoạt động.

Ví dụ:

- Một endpoint có URL hợp lệ nhưng DNS không resolve.
- Một token có nội dung nhưng đã hết hạn.
- Một số nguyên trong khoảng hợp lệ nhưng không phù hợp traffic thực tế.
- Một feature flag được thay động sau startup.
- Một external configuration source thay đổi khi ứng dụng đang chạy.
- Một required bean không được tạo vì điều kiện registration sai.
- Một ConfigMap mới chưa được container cũ đọc vì Pod chưa restart.
- Một secret được đọc lúc startup nhưng quyền access sau đó bị thay đổi.

Vì thế, một thiết kế đầy đủ thường gồm:

1. Startup schema/binding validation.
2. Runtime readiness/health checks.
3. Logging và metrics an toàn.
4. Profile/deployment policy.
5. Integration tests thực tế.
6. Configuration revision management.
7. Rollback và incident response.

Đừng tạo một “đường thoát” luôn catch exception config rồi tiếp tục, nếu hệ thống cần từ chối khởi động khi configuration contract bị vi phạm.

## 48. Tóm tắt

- **Thiếu property** khác **rỗng**, **sai kiểu**, **vi phạm constraint** và **unknown property**.
- `@ConfigurationProperties` tạo mô hình binding có kiểu; `@Validated` với Bean Validation provider kiểm tra các constraint.
- Dùng **`@NotBlank`** cho String cần có nội dung, **`@NotNull`** cho wrapper/object bắt buộc, **`@Min`/`@Max`** cho giới hạn số.
- Khi cần phát hiện khóa Boolean thiếu, dùng **`Boolean` thay vì `boolean`**.
- `Duration` đúng kiểu không đồng nghĩa lớn hơn 0; dùng custom constraint hoặc constructor invariant.
- `ignoreUnknownFields=false` có thể giúp bắt key thừa trong namespace được quản lý, không tự quét tất cả environment.
- Không thêm default để che lỗi deployment của field bắt buộc.
- `optional:` trên Config Data location không biến business property thành optional.
- **CLI và environment** có thể override file YAML; luôn xác minh effective configuration.
- **`ApplicationContextRunner`** phù hợp để test binding/validation cô lập; cần thêm integration tests cho profile/Config Data thực tế.
- Startup fail fast tốt phải được xác minh bằng **context failure đúng nguyên nhân**, không chỉ thông báo chung hoặc exit code.
- Không để exception/log hiển thị credential thật khi cấu hình thất bại.
- Trong production, fail-fast cần phối hợp với readiness, release policy và khả năng rollback bản cấu hình đã biết hoạt động.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot Test — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
