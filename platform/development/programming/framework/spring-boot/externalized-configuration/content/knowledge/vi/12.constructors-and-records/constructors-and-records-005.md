# Cấp giá trị mặc định bằng @DefaultValue trong Spring Boot

Khi dùng `@ConfigurationProperties` với **constructor binding** hoặc Java `record`, ứng dụng có thể khai báo các giá trị mặc định ngay trên tham số constructor hoặc record component thông qua `@DefaultValue`. Spring Boot Binder dùng những mặc định này **khi thuộc tính tương ứng không xuất hiện trong nguồn cấu hình**, sau đó chuyển chuỗi khai báo trong annotation sang kiểu Java đích.

Đây là một cách thiết kế cấu hình có cấu trúc, giúp tập hợp tên thuộc tính, kiểu dữ liệu và giá trị dự phòng ngay trong một hợp đồng Java. Nó đặc biệt hữu ích khi bạn muốn:

- Có mặc định hợp lý cho timeout, số lần retry, kích thước batch, cờ tính năng hoặc danh sách vai trò.
- Giữ một nhóm cấu hình ở dạng record đọc sau khi khởi động.
- Để môi trường triển khai ghi đè giá trị mà không cần sửa mã Java.
- Tạo đối tượng cấu hình lồng nhau ngay cả khi không có bất kỳ khóa nào thuộc nhóm đó.
- Tránh lặp biểu thức `@Value("${property:default}")` ở nhiều bean.

Bài học sử dụng **Spring Boot 3.3.x và Java 21**. Trọng tâm là ý nghĩa của `@DefaultValue` trong Binder, cách áp dụng lên constructor/record, giới hạn của annotation và các tình huống kiểm thử thực tế.

## 1. @DefaultValue nằm ở đâu trong hệ thống cấu hình?

Spring Boot có thể lấy thuộc tính từ `application.yml`, `application.properties`, biến môi trường, Java system properties, command-line arguments và nhiều nguồn khác. Các giá trị được tổng hợp theo thứ tự ưu tiên vào `Environment`; `@ConfigurationProperties` dùng **Binder** để ánh xạ chúng sang object có kiểu.

Sơ đồ:

~~~text
application.yml / application-prod.yml
environment variables / system properties / CLI
                       |
                       v
             Environment + Binder
                       |
                       v
        @ConfigurationProperties record
                       |
                       +--> Thuộc tính có nguồn cung cấp?
                       |       |
                       |       +--> Có: bind giá trị nguồn
                       |       |
                       |       +--> Không: dùng @DefaultValue nếu có
                       |
                       v
                Object đã bind
~~~

`@DefaultValue` **không tạo thêm một PropertySource** và không ghi một giá trị mới vào file cấu hình. Nó là chỉ dẫn cho Binder về cách điền một tham số constructor khi không có property phù hợp.

Chẳng hạn, bạn có record:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("500") int maxRows) {
}
~~~

Nếu không có `app.report.max-rows`, Binder có thể tạo `ReportProperties(500)`. Nhưng nếu môi trường cung cấp `app.report.max-rows=1000`, giá trị `1000` được dùng thay vì mặc định.

## 2. Khai báo @DefaultValue đúng package và đúng vị trí

Annotation thuộc Spring Boot:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
~~~

Nó được dùng trên:

- **Tham số constructor** của class sử dụng constructor binding.
- **Record component** của Java record sử dụng constructor binding.

Ví dụ trên record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("500ms") Duration backoff) {
}
~~~

Khi các thuộc tính không được cung cấp, ba component nhận `true`, `3` và `Duration.ofMillis(500)`.

Annotation không phải cơ chế gán giá trị cho **mọi field Java** và không thay thế các constructor parameter của bean dịch vụ thông thường. Nó có hiệu lực trong quá trình Spring Boot Binder tạo object cấu hình.

### API cơ bản

Ở Spring Boot 3.3, hình dạng khái niệm của annotation là:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
public @interface DefaultValue {
    String[] value() default {};
}
~~~

Điểm đáng chú ý:

- Giá trị annotation có kiểu `String[]`; cú pháp một chuỗi đơn như `@DefaultValue("5s")` là hợp lệ.
- Có thể khai báo nhiều chuỗi, ví dụ `@DefaultValue({"CSV", "JSON"})` cho collection.
- `@DefaultValue` **không có đối số** cũng hợp lệ và có ý nghĩa đặc biệt đối với object lồng nhau.
- Mỗi chuỗi phải là **hằng số hợp lệ của Java annotation**; không phải một expression được tính lúc chương trình chạy.

## 3. Ví dụ đơn giản với Java record

Tạo `src/main/java/com/example/configdemo/config/ReportProperties.java`:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("500") int maxRows,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("summary") String format) {
}
~~~

Trong `src/main/resources/application.yml`, có thể chỉ khai báo:

~~~yaml
app:
  report:
    max-rows: 200
~~~

Spring Boot Binder sẽ lấy `maxRows=200` từ file và sử dụng mặc định cho các component còn thiếu:

| Component của record | Property | Giá trị cuối trong ví dụ | Nguồn |
| --- | --- | --- | --- |
| `enabled` | `app.report.enabled` | `true` | `@DefaultValue("true")` |
| `maxRows` | `app.report.max-rows` | `200` | YAML |
| `timeout` | `app.report.timeout` | `PT10S` | `@DefaultValue("10s")` |
| `format` | `app.report.format` | `summary` | `@DefaultValue("summary")` |

`PT10S` là dạng chuỗi ISO-8601 do `Duration.toString()` biểu diễn khoảng thời gian 10 giây.

Với một record, các component được khởi tạo cùng nhau qua constructor; không cần setter, và **không cần `@ConstructorBinding`** nếu record chỉ có constructor phù hợp thông thường.

## 4. Đăng ký bean cấu hình trước khi sử dụng

Một record có `@ConfigurationProperties` cần được đăng ký thông qua cơ chế hỗ trợ configuration properties. Cách thông dụng là sử dụng `@ConfigurationPropertiesScan` trong lớp khởi động:

~~~java
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
~~~

Lớp `ReportProperties` nằm dưới package `com.example.configdemo` nên được quét. Một cách khác là:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ReportProperties.class)
public class ConfigDemoApplication {
    // main method...
}
~~~

Trong phương án thứ hai, thêm import tới đúng `ReportProperties` của dự án. Thông thường chỉ cần **một** cơ chế đăng ký cho class.

Không gắn `@Component` lên một record constructor-bound với kỳ vọng Spring sẽ tự bind mọi tham số constructor từ `Environment`. Với constructor binding, Spring Boot yêu cầu đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, thay vì cơ chế tạo bean `@Component`/`@Bean` thông thường.

### Đọc giá trị từ bean

~~~java
package com.example.configdemo;

import com.example.configdemo.config.ReportProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportPrinter {

    @Bean
    ApplicationRunner printReportSettings(ReportProperties settings) {
        return args -> {
            System.out.println("enabled = " + settings.enabled());
            System.out.println("maxRows = " + settings.maxRows());
            System.out.println("timeout = " + settings.timeout());
            System.out.println("format = " + settings.format());
        };
    }
}
~~~

Với YAML ở mục 3, kết quả mong đợi:

~~~text
enabled = true
maxRows = 200
timeout = PT10S
format = summary
~~~

Các component chỉ được dùng như dữ liệu có kiểu; service không cần tự gọi `Environment.getProperty` hoặc tự parse chuỗi timeout.

## 5. Default chỉ có hiệu lực khi property không được tìm thấy

Đây là quy tắc trung tâm của `@DefaultValue`:

> Giá trị trong annotation chỉ được dùng nếu Binder **không tìm được property** trong các nguồn thuộc tính. Nếu property tồn tại, giá trị nguồn được bind; annotation không tự ghi đè lên nó.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.search")
public record SearchProperties(
        @DefaultValue("20") int pageSize,
        @DefaultValue("false") boolean debug) {
}
~~~

Những tình huống:

| Cấu hình cung cấp | `pageSize` | `debug` |
| --- | ---: | --- |
| Không có cả hai property | 20 | false |
| `app.search.page-size=50` | 50 | false |
| `app.search.debug=true` | 20 | true |
| Cấp cả hai property | Theo giá trị được cấp | Theo giá trị được cấp |

**Giá trị rỗng không đồng nghĩa với property không tồn tại.** Tài liệu API Spring Boot 3.3 ghi rõ: khi property có mặt trong Environment, `@DefaultValue` không được dùng ngay cả nếu giá trị property rỗng.

Ví dụ:

~~~properties
app.search.page-size=
~~~

Vì `app.search.page-size` hiện diện nhưng có chuỗi trống, không nên kỳ vọng nó tự nhận mặc định `20`. Kết quả tiếp theo phụ thuộc Binder, kiểu đích và conversion/validation; có thể dẫn đến giá trị không như mong muốn hoặc lỗi binding. Nếu muốn xử lý giá trị rỗng như thiếu, hãy bổ sung quy tắc kiểm tra rõ ràng phù hợp với nghiệp vụ.

### Đọc thiếu thuộc tính và đọc thuộc tính rỗng

~~~text
app.search.page-size không có ở mọi PropertySource
    → Binder xem xét @DefaultValue("20")

app.search.page-size có giá trị "50"
    → Binder sử dụng 50

app.search.page-size hiện diện với giá trị ""
    → @DefaultValue không tự được chọn chỉ vì chuỗi rỗng
~~~

Cần phân biệt rõ quy tắc này với cách ứng dụng xử lý giá trị null/blank sau khi bind.

## 6. Chuyển đổi kiểu từ chuỗi annotation

Dù khai báo `@DefaultValue` sử dụng chuỗi, Binder có thể chuyển chuỗi đó sang kiểu tham số đích bằng conversion service của Spring Boot.

Ví dụ:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.download")
public record DownloadProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int maxParallel,
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("10MB") DataSize maxSize,
        @DefaultValue("https://download.example.org") URI endpoint) {
}
~~~

Các mặc định thể hiện:

- `true` → `boolean`.
- `4` → `int`.
- `3s` → `Duration` ba giây.
- `10MB` → `DataSize`.
- `https://download.example.org` → `URI`.

Dùng đơn vị thời gian và dung lượng có hậu tố để tránh nhầm. Ví dụ `"3s"` rõ ràng hơn `"3000"` khi kiểu Java là `Duration`.

### Duration và @DurationUnit

Ví dụ:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

public record Limits(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("30")
        Duration timeout) {
}
~~~

Trong trường hợp này, `@DurationUnit(ChronoUnit.SECONDS)` cho biết cách diễn giải giá trị không ghi đơn vị. Khi không có property, mặc định `"30"` có thể được chuyển thành 30 giây. Nếu khai báo `@DefaultValue("30s")`, ý nghĩa đơn vị đã nằm trực tiếp trong chuỗi nên thường dễ đọc hơn.

### Giá trị không thể chuyển kiểu

~~~java
@DefaultValue("ten") int maxAttempts
~~~

`ten` không phải chuỗi số nguyên phù hợp. Khi Binder cần dùng default này để tạo bean, việc chuyển sang `int` có thể thất bại, khiến ứng dụng không khởi động được. `@DefaultValue` không miễn trừ kiểm tra kiểu dữ liệu.

Khi dùng enum, chuỗi mặc định phải phù hợp với enum hoặc quy tắc chuyển đổi đang được cấu hình. Với một kiểu tự tạo, nếu conversion service không có converter thích hợp, giá trị mặc định cũng có thể không bind được.

## 7. Mặc định cho enum

Giả sử ứng dụng có mức độ ghi log nghiệp vụ:

~~~java
package com.example.configdemo.config;

public enum ReportMode {
    SUMMARY,
    DETAIL,
    ARCHIVE
}
~~~

Record:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportModeProperties(
        @DefaultValue("SUMMARY") ReportMode mode) {
}
~~~

Nếu `app.report.mode` không được khai báo, mode mặc định là `ReportMode.SUMMARY`.

Nhưng nếu có:

~~~yaml
app:
  report:
    mode: DETAIL
~~~

giá trị cấu hình `DETAIL` sẽ được bind thay cho mặc định. Nếu người vận hành nhập một giá trị không thể chuyển thành `ReportMode`, quá trình bind có thể báo lỗi; mặc định không tự động thay thế một giá trị đã có nhưng sai kiểu.

## 8. Mặc định cho danh sách và mảng

API `@DefaultValue` chấp nhận một mảng chuỗi. Điều này cho phép chỉ định một hoặc nhiều phần tử mặc định cho property dạng collection hoặc array.

Ví dụ:

~~~java
package com.example.configdemo.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
        @DefaultValue({"CSV", "JSON"}) List<String> formats,
        @DefaultValue({"vn", "sg"}) String[] regions) {
}
~~~

Khi không có `app.export.formats` và `app.export.regions`:

~~~text
formats = [CSV, JSON]
regions = ["vn", "sg"]
~~~

Nếu file YAML cung cấp:

~~~yaml
app:
  export:
    formats:
      - XML
~~~

`formats` lấy giá trị từ YAML và **không tự ghép thêm** `CSV`, `JSON` của annotation. Lúc đó, `@DefaultValue` không được dùng vì property đã có dữ liệu từ nguồn cấu hình.

### Cần phân biệt với cách merge danh sách giữa các nguồn

Trong Spring Boot, danh sách cấu hình từ nhiều nguồn thường tuân theo quy tắc **thay thế toàn bộ danh sách** ở nguồn có ưu tiên cao hơn, không mặc định nối thêm phần tử. `@DefaultValue({"CSV", "JSON"})` chỉ là một tập mặc định khi property thiếu, không phải quy tắc merge list.

Nếu muốn mặc định theo từng phần tử nhưng vẫn cho tùy chỉnh, cần thiết kế hợp đồng cấu hình riêng hoặc xử lý logic rõ ràng tại ứng dụng.

### Với Map thì sao?

`@DefaultValue` không phải một cú pháp tổng quát để mô tả cả cấu trúc YAML/Map phức tạp ngay trong annotation. Đối với cấu hình có nhiều key động, nên dùng file YAML/properties, constructor binding của nested object phù hợp hoặc một lớp tạo defaults theo logic có chủ đích. Đừng giả định truyền một chuỗi JSON vào `@DefaultValue` sẽ tự chuyển thành `Map<String,String>` nếu không có converter tương ứng.

## 9. Mặc định cho cấu hình lồng nhau: @DefaultValue không đối số

Đây là tính năng dễ bị bỏ qua nhất của annotation. Giả sử cấu hình có object lồng nhau:

~~~yaml
app:
  email:
    enabled: true
~~~

Bạn tạo record:

~~~java
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        boolean enabled,
        Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("2525") int port) {
    }
}
~~~

Nếu file YAML **không có bất kỳ khóa nào thuộc `app.email.smtp`**, object `smtp` có thể là `null` trong constructor binding. Mặc định trên `Smtp.host` và `Smtp.port` **không tự buộc Binder tạo một `Smtp` nếu toàn bộ nhóm nested không hiện diện**.

Nếu service gọi:

~~~java
properties.smtp().host();
~~~

nó có thể gặp `NullPointerException` khi `smtp()` bằng `null`.

### Giải pháp: @DefaultValue trống ở tham số nested

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("2525") int port) {
    }
}
~~~

`@DefaultValue` **không có đối số** trên `Smtp smtp` nói với Binder rằng nested object này nên được tạo ngay cả khi không có property nào của nhóm `smtp`.

Vì nested record chứa default cho `host` và `port`, object được tạo với:

~~~text
EmailProperties(
    enabled = true,
    smtp = Smtp(
        host = "localhost",
        port = 2525
    )
)
~~~

Nếu có cấu hình:

~~~yaml
app:
  email:
    smtp:
      host: mail.example.org
~~~

kết quả sẽ là `smtp.host=mail.example.org` và `smtp.port=2525`. Mặc định của nested component vẫn được xét riêng nếu thiếu property tương ứng.

### @DefaultValue trống không phải chuỗi rỗng

Phân biệt:

~~~java
@DefaultValue Smtp smtp
~~~

với:

~~~java
@DefaultValue("") String hostname
~~~

Cách thứ nhất là chỉ dẫn về việc tạo một object lồng nhau. Cách thứ hai khai báo một **giá trị chuỗi rỗng** làm default cho một tham số String. Chúng có ý nghĩa hoàn toàn khác nhau.

Nếu không cần nested object luôn tồn tại, có thể bỏ `@DefaultValue` trống và để cấu hình thiếu được biểu diễn bằng `null` rồi xử lý phù hợp trong logic nghiệp vụ. Không bắt buộc tạo mọi nhóm cấu hình lồng nhau.

## 10. Nested @DefaultValue và ràng buộc validation

Giả sử những giá trị mặc định phải thỏa quy tắc ứng dụng. Dùng Bean Validation kết hợp với `@ConfigurationProperties`:

~~~java
package com.example.configdemo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        @DefaultValue("true") boolean enabled,
        @Valid @NotNull @DefaultValue Smtp smtp) {

    public record Smtp(
            @NotBlank @DefaultValue("localhost") String host,
            @Min(1) @DefaultValue("2525") int port) {
    }
}
~~~

Trong dự án Gradle có thể dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

- `@Validated` yêu cầu kiểm tra constraints khi bind configuration-properties bean.
- `@Valid` cho phép xác thực cả thành viên nested.
- `@NotNull` diễn đạt rằng `smtp` là nhóm cấu hình bắt buộc ở mức object, dù đã có default tạo nó.
- `@NotBlank` bảo đảm hostname có nội dung.
- `@Min(1)` bảo đảm port không nhỏ hơn 1.

**Default không đồng nghĩa hợp lệ.** Nếu dùng `@DefaultValue("0")` trên port với `@Min(1)`, binder có thể tạo port = 0 nhưng validation sẽ báo lỗi. Thiết kế defaults cần phù hợp với constraint nghiệp vụ.

Với các trường khác như timeout dương, endpoint đúng scheme hoặc số lần retry tối đa, có thể dùng validation tùy nhu cầu. Chỉ dùng `@NotNull` trên `Duration` chưa bảo đảm duration lớn hơn 0.

## 11. Trên constructor của class thay vì record

`@DefaultValue` không giới hạn ở record. Với class immutable có một constructor phù hợp, có thể đặt annotation lên từng tham số:

~~~java
package com.example.configdemo.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.session")
public final class SessionProperties {

    private final int maxSessions;
    private final Duration idleTimeout;

    public SessionProperties(
            @DefaultValue("100") int maxSessions,
            @DefaultValue("30m") Duration idleTimeout) {

        this.maxSessions = maxSessions;
        this.idleTimeout = idleTimeout;
    }

    public int getMaxSessions() {
        return maxSessions;
    }

    public Duration getIdleTimeout() {
        return idleTimeout;
    }
}
~~~

Với Spring Boot 3.3, một class chỉ có một constructor tham số thường được xem xét dùng constructor binding khi được đăng ký theo cơ chế configuration properties. Không cần viết setter cho field `final`.

Lợi ích của kiểu này:

- Có thể kiểm soát logic bên trong constructor.
- Có thể giữ API getter truyền thống cho mã Java cũ.
- Có thể thêm các invariant hoặc tính toán khác nếu thực sự cần.

Với record, Java tự sinh constructor chuẩn và accessor nên mã gọn hơn. Chọn cách nào tùy quy mô, yêu cầu tương thích và mô hình dự án.

### Khi class có nhiều constructor

Nếu class có nhiều constructor và việc chọn constructor để bind không còn hiển nhiên, Spring Boot cung cấp `@ConstructorBinding` trên constructor thích hợp:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

public class ClientProperties {

    private final String baseUrl;
    private final int retries;

    public ClientProperties() {
        this("http://localhost:8080", 3);
    }

    @ConstructorBinding
    public ClientProperties(
            @DefaultValue("http://localhost:8080") String baseUrl,
            @DefaultValue("3") int retries) {
        this.baseUrl = baseUrl;
        this.retries = retries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getRetries() {
        return retries;
    }
}
~~~

Để dùng class này làm configuration properties, cần gắn `@ConfigurationProperties(prefix="app.client")` lên class và đăng ký bằng configuration-properties scan hoặc enable tương ứng. Đoạn mã tập trung vào việc chọn constructor, không minh họa toàn bộ class ứng dụng.

Lưu ý package `@ConstructorBinding` trong Spring Boot 3.x là `org.springframework.boot.context.properties.bind.ConstructorBinding`. Không nhầm với package cũ của những phiên bản Spring Boot trước đây.

## 12. @DefaultValue khác mặc định trong @Value như thế nào?

`@Value` sử dụng property placeholder:

~~~java
@Value("${app.session.max-sessions:100}")
private int maxSessions;
~~~

Trong khi constructor binding dùng:

~~~java
@ConfigurationProperties(prefix = "app.session")
public record SessionProperties(
        @DefaultValue("100") int maxSessions) {
}
~~~

Hai cách có thể cho cùng kết quả nếu thuộc tính thiếu và conversion thành công, nhưng chúng nằm ở **hai tầng cơ chế khác nhau**:

| Tiêu chí | `@Value("${key:default}")` | `@DefaultValue("default")` |
| --- | --- | --- |
| Nơi dùng | Điểm inject field, constructor parameter hoặc method parameter | Tham số constructor/record component của configuration properties |
| Cơ chế | Property placeholder resolution tại điểm dùng | ConfigurationProperties Binder |
| Phạm vi | Một giá trị hoặc biểu thức | Một component trong object cấu hình có cấu trúc |
| Chuyển kiểu | Tại injection point | Conversion service của Binder |
| Nguồn giá trị | Environment và các cơ chế biểu thức tương ứng | Environment thông qua Binder |
| Dữ liệu mặc định | Phần văn bản trong placeholder | Chuỗi/hằng số từ annotation |
| Khả năng biểu diễn nested object | Không phải mục tiêu chính | Có thể dùng `@DefaultValue` trống để bind nested object |
| Placeholder bên trong mặc định | Có thể tham gia cơ chế placeholder resolution theo ngữ cảnh | **Không hỗ trợ placeholder resolution trong `@DefaultValue`** |

### Ví dụ không nên viết

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

Trong Spring Boot 3.3, **`@DefaultValue` không hỗ trợ phân giải property placeholder**; tài liệu API yêu cầu giá trị là hằng số. Không nên kỳ vọng annotation trên đọc `APP_TIMEOUT` từ Environment hoặc chọn `5s` khi biến thiếu.

### Cách đúng để cho phép environment override

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("5s") Duration timeout) {
}
~~~

Sau đó người vận hành có thể đặt:

~~~bash
export APP_CLIENT_TIMEOUT="8s"
java -jar config-demo.jar
~~~

Trong trường hợp này, Binder tìm thấy `app.client.timeout` qua environment variable và sử dụng `8s`, còn `5s` chỉ được dùng khi không tìm thấy property.

Cách này giữ nguồn cấu hình độc lập với annotation và tuân theo thứ tự ưu tiên chung của Spring Boot.

## 13. Giá trị mặc định ở YAML hay Java?

Cùng một giá trị dự phòng có thể được cung cấp tại nhiều nơi, nhưng ý nghĩa và khả năng vận hành khác nhau.

### 13.1. Đặt default ở @DefaultValue

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(
        @DefaultValue("3") int retries) {
}
~~~

Phù hợp khi `3` là một mặc định của **hợp đồng Java**, không phụ thuộc môi trường triển khai. Nếu mọi file không khai báo khóa, Binder vẫn có thể tạo object với giá trị rõ ràng.

### 13.2. Đặt default ở application.yml

~~~yaml
app:
  task:
    retries: 3
~~~

Phù hợp khi default muốn được nhìn thấy và thay đổi bằng cấu hình triển khai. File `application-prod.yml` hoặc các nguồn ưu tiên cao hơn có thể ghi đè theo cơ chế Spring Boot.

### 13.3. Dùng Java constructor để tự đặt default

Một record có thể cung cấp logic constructor:

~~~java
public record LocalSettings(String region) {

    public LocalSettings {
        if (region == null || region.isBlank()) {
            region = "vn";
        }
    }
}
~~~

Nhưng đây là **logic Java** xảy ra bất cứ khi nào record được tạo, kể cả khi bạn gọi `new LocalSettings(null)` trong unit test. Ngược lại, `@DefaultValue` được Binder sử dụng theo điều kiện property thiếu, không tự chạy khi Java tạo object thủ công.

Nếu yêu cầu là: “đặt default chỉ khi người vận hành không cung cấp property”, `@DefaultValue` diễn đạt sát ý hơn. Nếu yêu cầu là: “mọi object được tạo đều phải chuẩn hóa dữ liệu”, logic constructor có thể là lựa chọn có chủ đích.

### Tránh chồng mặc định mâu thuẫn

Ví dụ:

~~~yaml
app:
  task:
    retries: 5
~~~

~~~java
@DefaultValue("3") int retries
~~~

Không có mâu thuẫn ở thời điểm binding: vì YAML đã cung cấp property, giá trị hiệu lực là `5`. Nhưng với người đọc, hai con số xuất hiện ở hai nơi có thể gây hiểu lầm. Nên ghi rõ đâu là **mặc định của code** và đâu là **giá trị vận hành**.

## 14. Kiểu primitive, reference type và giá trị thiếu

Nếu constructor binding không nhận được property và cũng không có `@DefaultValue`, giá trị của component tùy thuộc kiểu:

| Kiểu Java | Khi property thiếu và không có @DefaultValue |
| --- | --- |
| `int` | Thường nhận giá trị mặc định primitive `0` |
| `boolean` | Thường nhận giá trị mặc định primitive `false` |
| `String` | Có thể là `null` |
| `Duration` | Có thể là `null` |
| Object nested | Có thể là `null` nếu không có property con |
| Collection | Có thể là `null` khi không có dữ liệu bind |

Với ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        int attempts,
        boolean enabled,
        Duration delay) {
}
~~~

Khi không có khóa thuộc nhóm `app.job`, việc phụ thuộc vào `0`/`false`/`null` có thể không phản ánh yêu cầu nghiệp vụ. Một số thuộc tính thiếu cần **báo lỗi**, một số khác nên có default.

Dùng annotation để định nghĩa đúng:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        @DefaultValue("1") int attempts,
        @DefaultValue("true") boolean enabled,
        @DefaultValue("1s") Duration delay) {
}
~~~

Đừng sử dụng `@DefaultValue` để che đi một property bắt buộc như secret hoặc endpoint production. Với những trường đó, có thể để không có default và dùng validation để khởi động thất bại khi cấu hình không đầy đủ.

## 15. Ảnh hưởng của profile và các nguồn cấu hình khác

`@DefaultValue` chỉ hoạt động sau khi Binder xét dữ liệu trong các nguồn thuộc tính hiệu lực. Nó **không ghi đè** giá trị từ `application-prod.yml`, environment variables hoặc CLI.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.batch")
public record BatchProperties(
        @DefaultValue("100") int chunkSize,
        @DefaultValue("5s") Duration timeout) {
}
~~~

`application.yml`:

~~~yaml
app:
  batch:
    chunk-size: 250
~~~

`application-prod.yml`:

~~~yaml
app:
  batch:
    timeout: 2s
~~~

Trường hợp chạy mặc định:

~~~text
chunkSize = 250 (application.yml)
timeout   = 5s  (@DefaultValue)
~~~

Trường hợp chạy với profile prod:

~~~bash
java -jar config-demo.jar --spring.profiles.active=prod
~~~

Kết quả:

~~~text
chunkSize = 250 (application.yml)
timeout   = 2s  (application-prod.yml)
~~~

Nếu thêm:

~~~bash
java -jar config-demo.jar --spring.profiles.active=prod --app.batch.chunk-size=500
~~~

kết quả `chunkSize` thành `500`. Đó là giá trị CLI, không phải giá trị annotation.

**Tóm lại:** thứ tự ưu tiên các PropertySource quyết định property có giá trị nào; `@DefaultValue` chỉ bổ sung dữ liệu khi Binder không thấy property tương ứng. Không nên xem nó là một cách can thiệp thứ tự ưu tiên.

## 16. Kiểm thử @DefaultValue mà không phụ thuộc nhiều file

Spring Boot Test cung cấp `ApplicationContextRunner` để xây dựng context nhỏ, thuận tiện kiểm tra binding và defaults.

Giả sử `ReportProperties` như ở mục 3 đã được tạo. Tạo test:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.configdemo.config.ReportProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class ReportPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ReportProperties.class)
    static class BindingConfig {
    }

    @Test
    void usesDefaultsWhenPropertiesAreMissing() {
        runner.run(context -> {
            ReportProperties properties =
                    context.getBean(ReportProperties.class);

            assertThat(properties.enabled()).isTrue();
            assertThat(properties.maxRows()).isEqualTo(500);
            assertThat(properties.timeout().toSeconds()).isEqualTo(10);
            assertThat(properties.format()).isEqualTo("summary");
        });
    }

    @Test
    void suppliedValuesOverrideDefaults() {
        runner.withPropertyValues(
                "app.report.enabled=false",
                "app.report.max-rows=200",
                "app.report.timeout=4s",
                "app.report.format=detail")
                .run(context -> {
                    ReportProperties properties =
                            context.getBean(ReportProperties.class);

                    assertThat(properties.enabled()).isFalse();
                    assertThat(properties.maxRows()).isEqualTo(200);
                    assertThat(properties.timeout().toSeconds())
                            .isEqualTo(4);
                    assertThat(properties.format()).isEqualTo("detail");
                });
    }
}
~~~

Test trên dùng `spring-boot-starter-test`, JUnit Jupiter và AssertJ. Hai trường hợp chứng minh:

1. Khi không có property được cấp, Binder sử dụng các `@DefaultValue`.
2. Khi property có mặt trong test Environment, Binder dùng giá trị đó thay vì default.

Đây là test về binding của `@ConfigurationProperties`, không phải test giá trị được gán khi gọi constructor Java thủ công.

### Kiểm tra @DefaultValue không ảnh hưởng constructor Java

~~~java
ReportProperties manual =
        new ReportProperties(false, 0, null, null);
~~~

Kết quả là các giá trị được **truyền trực tiếp vào constructor**, không tự trở thành `true`/`500`/`10s`/`summary`. `@DefaultValue` không tự chạy trong JVM như một câu lệnh gán giá trị; nó cần Spring Boot Binder.

### Kiểm tra nested defaults

Với `EmailProperties` ở mục 9, test có thể kiểm tra:

~~~java
assertThat(properties.smtp()).isNotNull();
assertThat(properties.smtp().host()).isEqualTo("localhost");
assertThat(properties.smtp().port()).isEqualTo(2525);
~~~

Nếu muốn kiểm tra cơ chế chẩn đoán lỗi, có thể dùng `context.getStartupFailure()` trong `ApplicationContextRunner` khi cố ý cung cấp property không hợp lệ. Thông báo lỗi cụ thể có thể thay đổi theo phiên bản.

## 17. Những lỗi thường gặp

### Lỗi 1 — Import nhầm annotation

`@DefaultValue` phục vụ Spring Boot configuration properties có tên đầy đủ:

~~~java
org.springframework.boot.context.properties.bind.DefaultValue
~~~

Hãy kiểm tra IDE import đúng package. Cùng tên “default value” trong thư viện khác có thể không được Binder nhận.

### Lỗi 2 — Gắn @DefaultValue ở field của @Component

~~~java
@Component
class TaskService {
    @DefaultValue("3")
    private int retries;
}
~~~

Đây không phải cách sử dụng hợp lệ của annotation trong ví dụ (annotation được định nghĩa cho constructor parameters và record components). Dùng `@ConfigurationProperties` cho nhóm cấu hình hoặc `@Value` cho điểm inject phù hợp.

### Lỗi 3 — Quên đăng ký configuration properties

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("500") int maxRows) {
}
~~~

Nếu không có `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(ReportProperties.class)`, Spring có thể không tạo bean cấu hình để inject. Đăng ký bean là điều kiện riêng, không được `@DefaultValue` thay thế.

### Lỗi 4 — Dùng placeholder trong @DefaultValue

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

Tài liệu `DefaultValue` nêu rõ **không hỗ trợ property placeholder resolution**. Khai báo `@DefaultValue("5s")` rồi để môi trường ghi đè qua một property thực như `APP_CLIENT_TIMEOUT`.

### Lỗi 5 — Trông đợi default khi property có chuỗi rỗng

~~~properties
app.report.format=
~~~

Đây là một property có mặt với giá trị rỗng; `@DefaultValue("summary")` không tự được chọn vì giá trị hiện diện. Nếu muốn cấm chuỗi rỗng, sử dụng Bean Validation như `@NotBlank`.

### Lỗi 6 — Nested object vẫn null

~~~java
public record EmailProperties(
        Smtp smtp) {
    public record Smtp(@DefaultValue("localhost") String host) {}
}
~~~

Nếu không có property `app.email.smtp.*`, `smtp` có thể là null. Thêm `@DefaultValue` rỗng vào component `Smtp smtp` nếu muốn luôn tạo nested object.

### Lỗi 7 — Mặc định không chuyển được sang kiểu đích

~~~java
@DefaultValue("five") int retries
~~~

Khi Binder phải dùng default này, conversion có thể thất bại. Với `Duration`, nên ghi giá trị rõ đơn vị như `"5s"` hoặc `"250ms"`.

### Lỗi 8 — Nhầm default với validation

~~~java
@Min(1)
@DefaultValue("0")
int retries
~~~

Annotation đã cung cấp số nguyên 0, nhưng nó không thỏa constraint. Cần chọn default hợp lệ hoặc không có default để yêu cầu người vận hành cấp cấu hình.

### Lỗi 9 — Dùng default cho secret bắt buộc

~~~java
@DefaultValue("password")
String password
~~~

Đây là thiết kế nguy hiểm với môi trường production. Nếu password bắt buộc, không đặt một giá trị giả/không an toàn chỉ để ứng dụng khởi động. Sử dụng nguồn secret phù hợp và validation để phát hiện thiếu cấu hình.

### Lỗi 10 — Tưởng annotation làm thay đổi Environment

Mặc định của `@DefaultValue` thuộc dữ liệu bind ra object. Không nên giả định `environment.getProperty("app.report.max-rows")` sẽ nhận `"500"` chỉ vì record có `@DefaultValue("500")`. Nếu không có property nguồn, `Environment` có thể trả null, trong khi `ReportProperties.maxRows()` trả 500.

### Lỗi 11 — Dùng collection default như cơ chế nối list

~~~java
@DefaultValue({"CSV", "JSON"}) List<String> formats
~~~

Khi có cấu hình `app.export.formats=[XML]`, danh sách không tự nhận `[CSV, JSON, XML]` chỉ vì annotation có hai phần tử. Mặc định chỉ dùng khi không có property tương ứng.

### Lỗi 12 — Nhầm với default profile

`@DefaultValue` của Binder không liên quan đến `spring.profiles.default` hoặc `ConfigurableEnvironment.setDefaultProfiles(...)`. Một bên điền giá trị thuộc tính thiếu khi tạo object; bên kia quản lý profile được sử dụng khi không có active profiles.

## 18. Hướng dẫn thiết kế một nhóm cấu hình với defaults hợp lý

Giả sử một service xử lý file cần:

- Số worker mặc định.
- Giới hạn kích thước file.
- Thời gian chờ xử lý.
- Danh sách định dạng đầu vào.
- Nhóm retry settings.
- Một thư mục output bắt buộc.

Có thể thiết kế:

~~~java
package com.example.configdemo.config;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.processor")
public record ProcessorProperties(
        @Min(1) @DefaultValue("2") int workers,
        @NotNull @DefaultValue("20MB") DataSize maxFileSize,
        @NotNull @DefaultValue("30s") Duration timeout,
        @DefaultValue({"CSV", "JSON"}) List<String> acceptedFormats,
        @Valid @NotNull @DefaultValue Retry retry,
        @NotNull Path outputDir) {

    public record Retry(
            @Min(1) @DefaultValue("3") int attempts,
            @NotNull @DefaultValue("200ms") Duration backoff) {
    }
}
~~~

Trong trường hợp này, `outputDir` không có default vì hệ thống cần đường dẫn triển khai thực tế. File YAML có thể cung cấp:

~~~yaml
app:
  processor:
    output-dir: /var/app/output
    workers: 4
~~~

Các field còn lại lấy defaults từ annotation. Khi chạy với profile hoặc biến môi trường khác, người vận hành có thể override các field có property tương ứng.

Lợi ích:

- Service inject **một object typed**.
- Defaults được khai báo cạnh kiểu dữ liệu của chúng.
- Một nhóm nested (`retry`) vẫn có giá trị khi YAML không có phần `retry`.
- Các ràng buộc nghiệp vụ như `workers >= 1` được kiểm tra.
- Trường `outputDir` vẫn bắt buộc và không bị che bởi default giả.

Một bean sử dụng:

~~~java
package com.example.configdemo.service;

import com.example.configdemo.config.ProcessorProperties;
import org.springframework.stereotype.Service;

@Service
public class FileProcessor {

    private final ProcessorProperties properties;

    public FileProcessor(ProcessorProperties properties) {
        this.properties = properties;
    }

    public int workers() {
        return properties.workers();
    }

    public java.time.Duration retryBackoff() {
        return properties.retry().backoff();
    }
}
~~~

Không cần inject từng chuỗi property riêng lẻ; tất cả được truy cập qua cấu trúc Java có kiểu.

## 19. Bài tập thực hành

### Bài 1 — Dự đoán giá trị mặc định

Cho:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("30s") Duration ttl,
        @DefaultValue("100") int maxEntries) {
}
~~~

File `application.yml` chỉ có:

~~~yaml
app:
  cache:
    max-entries: 250
~~~

Kết quả `enabled`, `ttl` và `maxEntries` là gì?

**Đáp án:** `true`, `Duration.ofSeconds(30)` và `250`. Property `max-entries` có mặt nên ghi đè default 100.

### Bài 2 — Cấp giá trị qua command-line argument

Giữ `CacheProperties` trên và chạy:

~~~bash
java -jar config-demo.jar --app.cache.ttl=45s
~~~

Nếu không nguồn nào ưu tiên cao hơn ghi đè, `ttl` có giá trị bao nhiêu?

**Đáp án:** `Duration.ofSeconds(45)`, vì giá trị CLI đã có nên `@DefaultValue("30s")` không được dùng.

### Bài 3 — Tạo nested object mặc định

Cho:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("1025") int port) {
    }
}
~~~

Khi không có `app.mail.smtp.*`, hãy sửa record để vẫn truy cập được `properties.smtp().host()`.

**Đáp án:** thêm `@DefaultValue` rỗng trước `Smtp smtp`:

~~~java
public record MailProperties(
        @DefaultValue Smtp smtp) {
    // ...
}
~~~

### Bài 4 — Phân biệt empty string và missing property

Cho:

~~~java
@DefaultValue("summary") String format
~~~

So sánh hai lần chạy:

~~~text
Lần A: không có app.report.format
Lần B: app.report.format=
~~~

**Đáp án:** lần A Binder có thể dùng default `summary`. Lần B property hiện diện nhưng rỗng; không thể dựa vào annotation để tự thay nó bằng `summary`. Nếu yêu cầu giá trị không blank, thêm validation.

### Bài 5 — Sửa annotation sai

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

Hãy sửa để giá trị mặc định là 5 giây, đồng thời cho phép ghi đè bằng `APP_CLIENT_TIMEOUT`.

**Một lời giải:** khai báo `@ConfigurationProperties(prefix="app.client")` và component `@DefaultValue("5s") Duration timeout`. Khi cần override, cấp `APP_CLIENT_TIMEOUT=10s`.

### Bài 6 — Khai báo defaults cho collection

Tạo record có `List<String> regions` mặc định gồm `vn`, `sg`. Kiểm tra rằng khi YAML cung cấp `regions: [th]`, danh sách có hiệu lực không tự nối ba phần tử.

**Một lời giải:**

~~~java
@ConfigurationProperties(prefix = "app.region")
public record RegionProperties(
        @DefaultValue({"vn", "sg"}) List<String> regions) {
}
~~~

### Bài 7 — Kiểm tra validation

Tạo `ProcessorProperties` có `@Min(1) @DefaultValue("0") int workers`. Chạy với không có property `app.processor.workers`. Giải thích vì sao binding có thể tạo một giá trị số nguyên nhưng validation lại báo lỗi.

**Đáp án:** default là một giá trị được bind, không phải sự bảo đảm hợp lệ; `0` vi phạm constraint `@Min(1)`.

### Bài 8 — Phân biệt tạo object bằng Java và Binder

Cho:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        @DefaultValue("3") int attempts) {
}
~~~

So sánh:

~~~java
JobProperties direct = new JobProperties(0);
~~~

với một bean được Spring Boot bind khi property thiếu.

**Đáp án:** object tạo thủ công chứa `attempts=0`; bean do Binder tạo khi property thiếu có thể dùng `attempts=3`. Annotation không phải lệnh Java chạy mỗi khi gọi constructor.

## 20. Tổng kết

`@DefaultValue` là cơ chế của **Spring Boot ConfigurationProperties Binder** dành cho constructor binding và Java record. Annotation chứa những chuỗi hằng; Binder dùng chúng khi không tìm thấy property tương ứng, sau đó chuyển sang kiểu đích thông qua conversion service. Nếu property đã có giá trị, giá trị nguồn được ưu tiên; **ngay cả property rỗng cũng không tự kích hoạt default**.

Dạng `@DefaultValue("...")` hữu ích cho scalar, enum, `Duration`, `DataSize`, collection và những loại có converter phù hợp. Dạng **`@DefaultValue` không đối số** có thể yêu cầu Binder tạo một nested object dù không có property con. Annotation không hỗ trợ phân giải `${...}` bên trong giá trị, không tự tác động đến object tạo bằng `new` và không thay thế validation cho cấu hình bắt buộc.

Khi sử dụng cùng `@ConfigurationProperties`, `@ConfigurationPropertiesScan` và Bean Validation, `@DefaultValue` giúp định nghĩa một hợp đồng cấu hình có cấu trúc, dễ dùng lại và dễ thay đổi theo môi trường mà không rải các giá trị mặc định ở nhiều service.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration: Constructor Binding và @DefaultValue](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — DefaultValue Annotation API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — ConfigurationProperties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
