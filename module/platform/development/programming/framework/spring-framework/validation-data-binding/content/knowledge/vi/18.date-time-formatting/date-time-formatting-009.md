# Định dạng `Duration` theo API mà phiên bản Spring hỗ trợ

## 1. Mục tiêu và bối cảnh

`java.time.Duration` mô tả **một lượng thời gian**: thời hạn chờ 30 giây, thời gian retry 5 phút, khoảng xử lý 1 giờ 30 phút. Khi một trường dữ liệu `Duration` xuất hiện trong form hoặc request parameter của Spring, ứng dụng cần chuyển đổi theo hai chiều:

```text
Dữ liệu gửi lên "90s" --parse--> Duration.ofSeconds(90)
Duration.ofSeconds(90) --print--> "90s" để hiển thị lại
```

Điểm quan trọng nhất của chủ đề **“Định dạng Duration theo API mà phiên bản Spring hỗ trợ”** là **phân biệt API theo phiên bản**. `@DurationFormat`, `DurationFormatter` và `DurationFormatterUtils` được đưa vào **Spring Framework 6.2**; không thể sử dụng nguyên vẹn các ví dụ API này trên Spring Framework 6.1 hoặc cũ hơn. Ngoài ra, API `DurationStyle`/`@DurationUnit` của **Spring Boot** phục vụ hệ thống conversion của Boot; không mặc nhiên đồng nghĩa field formatting của Spring MVC.

Sau bài học, bạn có thể:
- Xác định phiên bản Spring Framework trên classpath rồi chọn đúng giải pháp.
- Phân biệt ISO-8601 của Java với định dạng `SIMPLE` và `COMPOSITE` của Spring Framework 6.2+.
- Áp dụng `@DurationFormat`, `DurationFormatter` và `defaultUnit` cho đúng nhu cầu parse/print.
- Dùng `Formatter<Duration>` tự định nghĩa khi Framework chưa có API 6.2 hoặc cần cú pháp riêng.
- Test round-trip, precision, lỗi nhập liệu và data binding thực sự qua Spring.

## 2. Hiểu đúng `Duration` trước khi format

`java.time.Duration` có từ Java 8, biểu diễn thời lượng bằng giây và nano giây, có thể âm hoặc bằng không. Kiểu này là **độ dài thời gian**, không phải thời điểm trên lịch.

Các biểu thức Java sau minh họa giá trị (cần `import java.time.Duration;`):

```java
Duration.ofSeconds(90);       // 90 giây
Duration.ofMinutes(90);       // 1 giờ 30 phút
Duration.ofMillis(250);       // 250 mili giây
Duration.parse("PT1H30M");    // 1 giờ 30 phút, cú pháp ISO-8601
Duration.ofMinutes(90).toString(); // "PT1H30M"
```

- `Duration`: timeout, delay, time-to-live, thời gian thực hiện.
- `Period`: số năm/tháng/ngày **theo lịch**. Một tháng không có số giây cố định, nên `Duration` không thay cho mọi nhu cầu “cộng 1 tháng”.
- `Instant`, `LocalDateTime`, `ZonedDateTime`: một mốc hoặc thời điểm, không phải thời lượng. Formatter dành cho ngày/giờ không thay thế formatter dành cho `Duration`.
- Một `Duration` 1 ngày tương ứng 24 giờ cố định; việc qua ranh giới múi giờ hoặc giờ mùa hè là trách nhiệm của tính toán trên timeline/lịch.
- Java `Duration.parse("PT30S")` hiểu ISO-8601; **không mặc định hiểu** `"30s"` hay `"1h30m"` theo cú pháp ngắn của Spring.

Việc dùng `Duration.ofMinutes(90).equals(Duration.parse("PT90M"))` cho kết quả `true`: so sánh thời lượng, không so sánh cách gõ chuỗi. `Duration.toString()` có thể chuẩn hóa cách biểu diễn.

## 3. Bảng chọn API theo phiên bản

| Môi trường | Cách phù hợp | Điều không nên giả định |
| --- | --- | --- |
| Java 8+ độc lập | `Duration.parse(String)` và `Duration.toString()` theo ISO-8601 | JDK hiểu `30s`, `2m`, `1h30m` |
| Spring Framework **6.1 trở về trước** | Tự định nghĩa/đăng ký `Formatter<Duration>` hoặc `Converter` cho contract mong muốn; có thể ủy quyền JDK ISO | Có sẵn `org.springframework.format.annotation.DurationFormat` |
| Spring Framework **6.2.x** | `@DurationFormat`, `DurationFormatter`, `DurationFormatterUtils`, các enum `DurationFormat.Style/Unit` | Tất cả style đều giữ nano giây hoặc dùng cùng quy tắc locale |
| Spring Framework **7.x** | Các API Duration formatter vẫn được hỗ trợ; đối chiếu Javadoc phiên bản chạy thật | Một ví dụ cho bản mới tự động biên dịch trên bản 6.1 |
| Spring Boot | `DurationStyle`, `@DurationUnit`, `ApplicationConversionService` cho các trường hợp conversion đặc thù Boot | Conversion của `@ConfigurationProperties` luôn áp dụng y nguyên cho `@ModelAttribute`/JSON |

**Lưu ý:** Spring Framework 6.2 giới thiệu API này; việc dự án dùng “Spring Boot 3.x” chưa đủ để suy ra phiên bản Framework. Hãy kiểm tra dependency tree hoặc version thực tế:

```java
System.out.println(org.springframework.core.SpringVersion.getVersion());
```

Trong Maven dùng `mvn dependency:tree`; trong Gradle dùng `dependencyInsight` đối với `org.springframework:spring-context`. Spring Boot thông thường quản lý phiên bản Spring Framework thông qua BOM; không nâng một mình `spring-context` lên 6.2 nếu những module Framework khác vẫn ở 6.1.

## 4. Các API Spring Framework 6.2+ cần nhớ

Những import chính:

```java
import org.springframework.format.annotation.DurationFormat;
import org.springframework.format.datetime.standard.DurationFormatter;
import org.springframework.format.datetime.standard.DurationFormatterUtils;
```

`DurationFormat` là annotation để mô tả cách format một field/parameter `Duration`. `DurationFormatter` cài đặt `Formatter<Duration>` và có hai hàm `parse(String, Locale)` / `print(Duration, Locale)`. `DurationFormatterUtils` cung cấp các hàm tĩnh để parse/print theo style hoặc phát hiện style.

`DurationFormatter` có constructor nhận `DurationFormat.Style`, hoặc nhận cả `DurationFormat.Style` và `DurationFormat.Unit` dự phòng. `@DurationFormat` có hai thuộc tính quan trọng:

```java
@DurationFormat(
    style = DurationFormat.Style.SIMPLE,
    defaultUnit = DurationFormat.Unit.SECONDS
)
private Duration timeout;
```

Mặc định annotation dùng `Style.ISO8601`, còn đơn vị dự phòng mặc định là `Unit.MILLIS` khi style cần một đơn vị. Việc chọn style quyết định cú pháp đầu vào; không phải cứ đặt `defaultUnit=SECONDS` là có thể parse chuỗi `"90"` dưới `Style.ISO8601`.

### 4.1. `Style.ISO8601`: chuẩn của JDK

| Chuỗi | Thời lượng |
| --- | --- |
| `PT30S` | 30 giây |
| `PT1H30M` | 1 giờ 30 phút |
| `PT0.25S` | 250 mili giây |
| `P2D` | 2 ngày, mỗi ngày 24 giờ theo thời lượng |

ISO-8601 phù hợp khi muốn cách biểu diễn rõ, có thể mang phần lẻ giây đến độ chính xác nano giây của `Duration`. `DurationFormatter(Style.ISO8601)` đi theo cú pháp parse và print của JDK. Ví dụ `Duration.parse("PT90S").toString()` sẽ cho chuỗi chuẩn hóa `"PT1M30S"`; không nên đòi raw text đầu vào giống hệt text sau khi in.

### 4.2. `Style.SIMPLE`: một số nguyên và một đơn vị

Các hậu tố được hỗ trợ:

| Hậu tố | Đơn vị | Ví dụ |
| --- | --- | --- |
| `ns` | nano giây | `500ns` |
| `us` | micro giây | `250us` |
| `ms` | mili giây | `750ms` |
| `s` | giây | `90s` |
| `m` | phút | `5m` |
| `h` | giờ | `2h` |
| `d` | ngày 24 giờ | `1d` |

`SIMPLE` không hỗ trợ số thập phân như `"1.5s"`. Có thể diễn đạt 1,5 giây bằng `"1500ms"`, hoặc chuyển sang `ISO8601` với `"PT1.5S"`.

Khi `DurationFormatter(Style.SIMPLE, Unit.SECONDS)` in 90 giây sẽ trả `"90s"`; khi parse chuỗi **không hậu tố** `"90"` thì dùng `defaultUnit=SECONDS` để hiểu 90 giây. Nhưng `"90ms"` vẫn là 90 mili giây, vì đơn vị **có hậu tố tường minh** không bị thay thế bằng default unit.

**Precision:** `SIMPLE` in theo một đơn vị cố định và có thể mất phần nhỏ hơn đơn vị đó. Ví dụ:

```java
Duration precise = Duration.ofMillis(5).plusNanos(1234);
DurationFormatter formatter = new DurationFormatter(
    DurationFormat.Style.SIMPLE,
    DurationFormat.Unit.MILLIS);
String printed = formatter.print(precise, Locale.US); // "5ms"
```

Đây là đoạn minh họa cần import `java.time.Duration`, `java.util.Locale` cùng các class Spring. Phần **1234 nano giây** không khôi phục được khi parse `"5ms"`. Nếu phải bảo toàn nano giây, chọn style/đơn vị phù hợp và test bằng giá trị biên; cũng cần cân nhắc nguy cơ tràn `long` khi biểu diễn một thời lượng rất dài thành số nano giây nguyên.

### 4.3. `Style.COMPOSITE`: nhiều đoạn thời lượng

Ví dụ cú pháp:

```text
1h30m
2h15m10s
1h 30m
-(34m 57s)
```

`COMPOSITE` cho phép nhiều đơn vị ghép theo thứ tự từ **lớn xuống nhỏ**. Style này phù hợp hiển thị thời gian dài dạng đọc nhanh. Spring chấp nhận một số biến thể khoảng trắng và dấu âm theo ngữ pháp của nó; không đồng nghĩa với parser ngôn ngữ tự nhiên. Chuỗi `"1 giờ 30 phút"` không được mặc định hỗ trợ.

`DurationFormatterUtils.parse("1h30m", DurationFormat.Style.COMPOSITE)` trả về thời lượng tương đương 90 phút. Khi bạn gọi `Duration.toString()` trên kết quả, Java vẫn in theo ISO-8601 (`PT1H30M`); đó **không phải** kết quả của COMPOSITE printer.

### 4.4. `Unit` của Spring khác `ChronoUnit`

Các giá trị enum `DurationFormat.Unit` là `NANOS`, `MICROS`, `MILLIS`, `SECONDS`, `MINUTES`, `HOURS`, `DAYS`. Đây là kiểu của **Spring Framework** trong `org.springframework.format.annotation.DurationFormat`, không phải kiểu `java.time.temporal.ChronoUnit`, dù các đơn vị tương ứng.

`defaultUnit` là fallback khi style hỗ trợ chuỗi không chỉ rõ đơn vị, đồng thời chọn độ phân giải khi `SIMPLE` in giá trị. Hãy chỉ định tường minh cho field nhận số không hậu tố; mặc định mili giây có thể tạo lỗi nghiệp vụ nghiêm trọng nếu người dùng nghĩ “90” nghĩa là 90 giây.

## 5. Dùng annotation trên field Spring MVC

Trên Spring Framework **6.2+**, một form model có thể khai báo:

```java
import java.time.Duration;
import org.springframework.format.annotation.DurationFormat;

public class JobForm {
    @DurationFormat(
        style = DurationFormat.Style.SIMPLE,
        defaultUnit = DurationFormat.Unit.SECONDS
    )
    private Duration timeout;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Với `FormattingConversionService` mặc định hỗ trợ annotation tương ứng, input `"90"` bind thành `Duration.ofSeconds(90)`; khi in theo style này, `90` giây được biểu diễn `"90s"`. Input `"2m"` thành hai phút vì đã có hậu tố.

Bạn cũng có thể dùng `@DurationFormat` cho tham số controller Spring MVC (đoạn mã **minh họa**, cần dependency Spring Web MVC):

```java
@GetMapping("/preview")
String preview(
        @RequestParam
        @DurationFormat(style = DurationFormat.Style.COMPOSITE)
        Duration delay) {
    return "delay=" + delay;
}
```

Các import web là `org.springframework.web.bind.annotation.GetMapping` và `RequestParam`. Request `/preview?delay=1h30m` có thể được parse thành `Duration` khi chạy trên Framework 6.2+ với hệ thống formatting MVC thích hợp. Khi parse lỗi, cần xử lý kết quả binding/HTTP theo chính sách API.

Một formatter dùng chung cho mọi `Duration` có thể được đăng ký bằng `WebMvcConfigurer.addFormatters(FormatterRegistry)`, ví dụ `registry.addFormatter(new DurationFormatter(Style.COMPOSITE))`. Chỉ dùng cấu hình toàn cục khi các field thực sự có chung hợp đồng; với mỗi field dùng style/defaultUnit khác nhau, annotation tại field rõ ràng hơn.

## 6. Ví dụ đầy đủ Java 17+: kiểm tra API Spring 6.2 và DataBinder

Ví dụ này cố định **Spring Framework 6.2.14**, dùng Maven và Java 17+. Nó kiểm tra formatter ISO-8601, SIMPLE, COMPOSITE, annotation trong data binding và lỗi chuyển đổi. Không cần Spring Boot hoặc server web.

Tạo file `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duration-format-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/DurationFormattingDemo.java`:

```java
package example;

import java.text.ParseException;
import java.time.Duration;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.format.annotation.DurationFormat;
import org.springframework.format.datetime.standard.DurationFormatter;
import org.springframework.format.datetime.standard.DurationFormatterUtils;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;

public final class DurationFormattingDemo {

    public static final class JobForm {
        @DurationFormat(
                style = DurationFormat.Style.SIMPLE,
                defaultUnit = DurationFormat.Unit.SECONDS)
        private Duration timeout;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws ParseException {
        Locale locale = Locale.US;

        // 1. ISO-8601: JDK duration format.
        DurationFormatter iso =
                new DurationFormatter(DurationFormat.Style.ISO8601);
        Duration ninetyMinutes = Duration.ofMinutes(90);
        String isoText = iso.print(ninetyMinutes, locale);
        check("PT1H30M".equals(isoText), "ISO print differs");
        check(ninetyMinutes.equals(iso.parse(isoText, locale)),
                "ISO round-trip failed");
        System.out.println("ISO: " + isoText);

        // 2. SIMPLE, chọn đơn vị khi in và khi input thiếu hậu tố.
        DurationFormatter simple = new DurationFormatter(
                DurationFormat.Style.SIMPLE,
                DurationFormat.Unit.SECONDS);
        String simpleText = simple.print(Duration.ofSeconds(90), locale);
        check("90s".equals(simpleText), "SIMPLE print differs");
        check(Duration.ofSeconds(90).equals(
                simple.parse(simpleText, locale)),
                "SIMPLE round-trip failed");
        check(Duration.ofSeconds(90).equals(
                simple.parse("90", locale)),
                "Wrong defaultUnit");
        System.out.println("SIMPLE: " + simpleText);

        // 3. COMPOSITE parse nhiều thành phần.
        Duration composite = DurationFormatterUtils.parse(
                "1h30m", DurationFormat.Style.COMPOSITE);
        check(ninetyMinutes.equals(composite),
                "COMPOSITE parse failed");
        System.out.println("COMPOSITE: " + composite);

        // 4. DataBinder sử dụng annotation trên field.
        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();

        JobForm form = new JobForm();
        DataBinder binder = new DataBinder(form);
        binder.setConversionService(conversionService);
        binder.bind(new MutablePropertyValues(Map.of("timeout", "90")));
        check(!binder.getBindingResult().hasErrors(),
                "Unexpected binding error");
        check(Duration.ofSeconds(90).equals(form.getTimeout()),
                "Wrong annotated timeout");
        System.out.println("FIELD: " + form.getTimeout());

        // 5. Input sai phải sinh FieldError, không thành zero.
        JobForm invalidForm = new JobForm();
        DataBinder invalidBinder = new DataBinder(invalidForm);
        invalidBinder.setConversionService(conversionService);
        invalidBinder.bind(new MutablePropertyValues(
                Map.of("timeout", "not-a-duration")));
        boolean badInputRejected = invalidBinder
                .getBindingResult().hasFieldErrors("timeout");
        check(badInputRejected, "Expected field conversion error");
        System.out.println("INVALID_BINDING: " + badInputRejected);

        System.out.println("CHECKS: PASS");
    }
}
```

Chạy với Maven 3.9+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.DurationFormattingDemo
```

Đầu ra kỳ vọng khi các kiểm tra đều qua:

```text
ISO: PT1H30M
SIMPLE: 90s
COMPOSITE: PT1H30M
FIELD: PT1M30S
INVALID_BINDING: true
CHECKS: PASS
```

Giải thích:
1. `ISO` trả `"PT1H30M"` và parse ngược thành cùng `Duration` 90 phút.
2. `SIMPLE` trả `"90s"` vì đơn vị hiển thị là giây; input không hậu tố `"90"` cũng được hiểu là giây nhờ `defaultUnit=SECONDS`.
3. `COMPOSITE` parse `"1h30m"` thành `Duration` 90 phút. Lệnh `System.out.println` in **`Duration.toString()` theo ISO**, không phải `DurationFormatterUtils.print(..., COMPOSITE)`.
4. `FIELD` kiểm tra đường `DataBinder` đọc annotation và bind `"90"` thành 90 giây; `Duration.toString()` biểu diễn 90 giây là `"PT1M30S"`.
5. Chuỗi `"not-a-duration"` phải tạo lỗi trường trong `BindingResult`. Khi triển khai thật, hiển thị lỗi dễ hiểu cho người dùng.

Mã ví dụ này dùng các class Spring đã được liệt kê trong Javadoc của **6.2.14**. Nếu chạy với **6.1** sẽ không biên dịch do thiếu API mới. Khi chuyển patch version, chạy lại test parse/print và binding trên đúng dependency runtime.

## 7. Cách thay thế trên Spring Framework 6.1 trở về trước

Khi chưa có `@DurationFormat`/`DurationFormatter` của 6.2, có thể viết `Formatter<Duration>` theo SPI có sẵn lâu nay trong Spring. Ví dụ này **chỉ hỗ trợ ISO-8601**, không hứa nhận `30s` hay `1h30m`.

File `src/main/java/example/IsoDurationFormatter.java`:

```java
package example;

import java.time.Duration;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class IsoDurationFormatter implements Formatter<Duration> {
    @Override
    public String print(Duration value, Locale locale) {
        return value.toString();
    }

    @Override
    public Duration parse(String text, Locale locale) {
        try {
            return Duration.parse(text);
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected ISO-8601, e.g. PT30S", ex);
        }
    }
}
```

Class này dùng JDK và interface Spring `Formatter` đã có trong các phiên bản cũ; `parse` có thể ném `IllegalArgumentException`, phù hợp với hợp đồng lỗi của Spring formatter.

Đăng ký trong Spring MVC qua cấu hình (đoạn **minh họa**, cần dependency `spring-webmvc` và import tương ứng):

```java
@Configuration
class DurationWebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new IsoDurationFormatter());
    }
}
```

Các import là `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` và `org.springframework.format.FormatterRegistry`. Nếu không chạy Spring MVC, có thể đăng ký vào `FormattingConversionService` rồi gắn vào `DataBinder`.

Với cấu hình ISO, `parse("PT30S", ...)` thành 30 giây, còn `parse("30s", ...)` phải báo lỗi. Nếu muốn hỗ trợ suffix, hãy thiết kế parser với ngữ pháp rõ ràng, test overflow/precision và đăng ký vào conversion service. Không khai báo `@DurationFormat` trên dự án Spring 6.1 rồi hy vọng framework tự nhận.

## 8. Tránh nhầm hệ thống chuyển đổi của Spring Boot

Spring Boot cung cấp những API khác:

```java
org.springframework.boot.convert.DurationStyle
org.springframework.boot.convert.DurationUnit
```

Chúng thường gặp khi đọc configuration properties, ví dụ:

```yaml
app:
  timeout: 30s
```

Cần phân biệt:
- `@DurationUnit` của **Boot** thiết lập đơn vị cho việc chuyển đổi theo cơ chế của Boot; `@DurationFormat(defaultUnit=...)` của **Framework 6.2+** mô tả field/parameter formatting.
- `ApplicationConversionService` của Boot có tập converter riêng; đừng suy luận `FormatterRegistry` cho Spring MVC dùng đúng mọi quy tắc đó nếu chưa kiểm tra.
- `@RequestBody` JSON thường được xử lý qua `HttpMessageConverter`/Jackson, khác với string conversion của `@ModelAttribute` hay `@RequestParam`. Nếu API JSON muốn nhận `"30s"`, cần định nghĩa contract JSON và test độc lập.
- Spring Boot có thể chạy cùng các phiên bản Spring Framework khác nhau; phải kiểm tra phiên bản thực tế, không suy đoán chỉ từ chữ “Boot”.

## 9. Kiểm tra hai chiều và tác động của precision

Gọi `P_s(d)` là phép in thời lượng `d` theo style `s`, `Q_s(t)` là phép parse chuỗi `t` theo cùng style/đơn vị.

**Giá trị → chuỗi → giá trị:**

```text
Q_s(P_s(d)) == d
```

Điều này chỉ đúng nếu cách in giữ đủ độ phân giải. Ví dụ `Duration.ofMillis(5).plusNanos(1234)` in bằng SIMPLE với `Unit.MILLIS` bị cắt về `5ms`; parse lại sẽ **khác** giá trị gốc. Nếu không chấp nhận mất nano giây, dùng ISO-8601 hoặc chọn unit phù hợp và kiểm thử phần dư/overflow.

**Chuỗi → giá trị → chuỗi chuẩn hóa:**

```text
P_s(Q_s(text)) == canonical_s(text)
```

Không bắt buộc chuỗi nhập có cùng từng ký tự với chuỗi in. `"90"` với SIMPLE/SECONDS có thể được in lại thành `"90s"`, `"PT90S"` theo ISO có thể chuẩn hóa thành `"PT1M30S"`. Chỉ đòi giữ nguyên text nếu yêu cầu nhập vào một dạng chuẩn duy nhất và đã xác thực dạng đó.

**Locale không biến suffix thành tiếng Việt.** `Formatter` nhận `Locale` theo SPI, nhưng style `ISO8601`/`SIMPLE`/`COMPOSITE` là các cú pháp token thời gian; `Locale.forLanguageTag("vi-VN")` không tự biến `"1h30m"` thành `"1 giờ 30 phút"`. Nếu UI cần ngôn ngữ tự nhiên, hãy làm formatter bản địa hóa riêng và kiểm thử nhiều locale.

## 10. Ma trận test thực tế

| Nhóm | Case đề xuất | Kỳ vọng |
| --- | --- | --- |
| ISO cơ bản | `PT0S`, `PT30S`, `PT1H30M` | Parse/print đúng theo JDK |
| ISO độ chính xác cao | `PT0.123456789S` | Không mất nano giây |
| SIMPLE có hậu tố | `500ms`, `90s`, `2m`, `1h` | Nhận đúng unit |
| SIMPLE không hậu tố | `"90"` với fallback `SECONDS` và fallback `MILLIS` | Phát hiện sai số nhân/chia 1000 |
| SIMPLE phần lẻ | `1.5s`, `1500ms` | `1.5s` không thuộc cú pháp SIMPLE; `1500ms` phù hợp |
| COMPOSITE | `1h30m`, `2h15m10s` | Cộng đúng các thành phần, thứ tự phù hợp |
| Khoảng trắng và dấu âm | `1h 30m`, `-(34m 57s)` | Chỉ chấp nhận dạng style hỗ trợ |
| Precision | `Duration.ofMillis(5).plusNanos(1234)` | Phát hiện mất phần nano nếu in mili giây |
| Zero/âm | `PT0S`, `-PT5S` và dữ liệu nghiệp vụ | Phân biệt parse được với hợp lệ theo domain |
| Chuỗi sai | `n/a`, `1hour`, ký tự thừa, unit không hỗ trợ | Binding có `FieldError`, không âm thầm ra zero |
| Blank/null | `""`, khoảng trắng, thiếu field | Kiểm tra chính sách required/null ở tầng binding |
| Runtime | Spring 6.1, 6.2, 7 hoặc Boot đang chạy | Không import API thiếu; formatter đúng đường nhận dữ liệu |
| Form thực tế | `@ModelAttribute`, `@RequestParam` | Kiểm tra giá trị model và `BindingResult`/HTTP error |

**Tách hai loại lỗi:** Parse được `PT0S` hoặc `-PT5S` không có nghĩa chúng hợp lệ cho timeout. Sau khi chuyển đổi thành `Duration`, dùng validation nghiệp vụ để từ chối thời gian âm, bằng zero hoặc vượt ngưỡng. Trước khi parse thành công, xử lý `typeMismatch` ở tầng binding; validation trên đối tượng đã có kiểu không thay thế parse đúng.

## 11. Chẩn đoán lỗi thường gặp

**`Cannot resolve symbol DurationFormat`**: dùng Spring Framework trước 6.2, thiếu dependency `spring-context`, import sai package, hoặc có nhiều phiên bản Spring trên classpath. Đọc dependency tree trước khi sửa code.

**Gõ `90` nhưng nhận 90 ms thay vì 90 s**: quên đặt `defaultUnit=SECONDS`, trong khi fallback mặc định là `MILLIS`. Ghi rõ đơn vị trong UX hoặc yêu cầu người dùng nhập suffix tường minh.

**Dùng `@DateTimeFormat(pattern = ...)` cho `Duration`**: đây là annotation dành cho ngày/giờ, không phải lựa chọn chính cho độ dài thời gian. Spring 6.2+ có `@DurationFormat`; phiên bản cũ dùng formatter riêng.

**`Duration.parse("1h30m")` lỗi**: Java JDK parser dùng ISO-8601, còn COMPOSITE là tính năng Spring 6.2+. Chọn `DurationFormatterUtils.parse(text, Style.COMPOSITE)` hoặc API formatter phù hợp.

**Round-trip mất phần lẻ nano giây**: `SIMPLE` in theo một đơn vị cố định và có thể truncate. Dùng style giữ precision hoặc chuẩn hóa dữ liệu trước khi in với hợp đồng rõ ràng.

**Unit test parser đúng, MVC vẫn báo lỗi**: kiểm tra formatter/annotation có thực sự được đăng ký trong `FormattingConversionService` dùng cho MVC, kiểu field/getter, binding result và các converter khác đã override hay không. Không kết luận chỉ từ một phép gọi parser độc lập.

**Form và JSON chấp nhận cú pháp khác nhau**: không trộn conversion của form với Jackson JSON. Nếu muốn chung contract, định nghĩa/kiểm thử cả hai đường nhận dữ liệu và error handling tương ứng.

## 12. Checklist chọn giải pháp

1. Xác định **phiên bản Spring Framework thực tế** và Java runtime; đối chiếu Javadoc đúng nhánh.
2. Xác định **đường nhập dữ liệu**: form, request parameter, configuration properties hay JSON.
3. Chọn một **cú pháp có tài liệu**: `ISO8601`, `SIMPLE`, `COMPOSITE` hoặc hợp đồng custom.
4. Chọn `defaultUnit` và độ phân giải in rõ ràng; tránh nhận một con số không đơn vị mà người dùng hiểu sai.
5. Dùng `@DurationFormat`/`DurationFormatter` khi Framework 6.2+; trên 6.1 hoặc cũ hơn dùng `Formatter<Duration>` tự định nghĩa.
6. Test parse/print, canonicalization, precision, overflow, negative/zero, input lỗi và `DataBinder` hoặc request thực tế.
7. Đặt validation nghiệp vụ tách biệt với chuyển đổi kiểu, và báo lỗi input phù hợp cho người dùng.

## Tài liệu đối chiếu

- Spring Framework 6.2 — Field Formatting: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2.14 — `DurationFormatter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/standard/DurationFormatter.html
- Spring Framework 6.2.4 — `DurationFormat` và `Style`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/format/annotation/DurationFormat.html
- Spring Framework 6.2.4 — `DurationFormat.Style`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/format/annotation/DurationFormat.Style.html
- Spring Framework 6.2.14 — `DurationFormat.Unit`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/annotation/DurationFormat.Unit.html
- Java SE 17 — `java.time.Duration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html
- Spring Boot — `DurationStyle` (Boot API, không đồng nhất với Framework): https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/convert/DurationStyle.html
