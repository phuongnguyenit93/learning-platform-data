# DateFormatter và DateTimeFormatterRegistrar trong Spring: định dạng ngày giờ và data binding

## 1. Vì sao Spring cần các bộ định dạng ngày giờ?

Khi người dùng gửi `2026-11-05` trong query parameter, path variable hoặc form HTML, dữ liệu ban đầu là một chuỗi. Controller hay model lại có thể yêu cầu `java.util.Date`, `LocalDate`, `LocalDateTime` hoặc `OffsetDateTime`. Spring phải **parse** chuỗi thành đối tượng đúng kiểu; khi hiển thị đối tượng trong form hay view, Spring có thể **print** đối tượng ngược thành chuỗi.

Những loại ngày giờ này khác bản chất: `Date` đại diện một thời điểm trên dòng thời gian; `LocalDate` chỉ có ngày lịch, không chứa giờ, offset hoặc timezone. Vì vậy **không thể dùng một quy tắc định dạng cho mọi kiểu mà không xét ý nghĩa của giá trị**.

Bài này tập trung vào hai API:
- `org.springframework.format.datetime.DateFormatter`: một `Formatter<Date>` cho hệ ngày giờ cũ `java.util.Date`.
- `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`: một **bộ đăng ký formatter** để sử dụng các định dạng dựa trên `java.time.format.DateTimeFormatter` cho nhóm kiểu `java.time`.

Tên dễ nhầm: `DateFormatter` là **đối tượng trực tiếp parse/print `Date`**; `DateTimeFormatterRegistrar` là **đối tượng cấu hình và đăng ký các formatter**. `DateTimeFormatter` (không có chữ `Registrar`) là lớp định dạng thuộc **JDK**, không phải lớp Spring.

## 2. Formatter nằm ở đâu trong cơ chế conversion?

Spring có hai khái niệm liên quan:

- `Converter<S,T>` chủ yếu mô tả phép chuyển kiểu từ `S` sang `T`, không cần tham số `Locale`.
- `Formatter<T>` gồm `Parser<T>.parse(String, Locale)` và `Printer<T>.print(T, Locale)`; phù hợp với dữ liệu hiển thị phụ thuộc địa phương như số, ngày, giờ.

`FormattingConversionService` kết hợp các converter và formatter. `FormatterRegistry` là API đăng ký: `addFormatter(...)`, `addFormatterForFieldType(...)`, cùng các phương thức đăng ký converter. `FormatterRegistrar` có một phương thức `registerFormatters(FormatterRegistry registry)` để đăng ký một nhóm formatter/converter theo chính sách chung.

```text
HTTP query / path / form (String)
               |
               v
     Spring MVC WebDataBinder
               |
               v
     FormattingConversionService
               |
        chọn quy tắc theo kiểu đích
           /                    \
  java.util.Date             java.time.*
       |                         |
 DateFormatter             formatter từ
 (DateFormatterRegistrar)  DateTimeFormatterRegistrar
       |                         |
   parse(text, Locale)      parse(text, Locale)
           \                    /
             đối tượng Java
                  |
            Controller / Model
```

Mũi tên ngược (in giá trị ra form hoặc view) sử dụng `print(value, Locale)` khi luồng hiển thị tích hợp Spring formatting. Không nên suy ra rằng trả JSON qua `@ResponseBody` cũng dùng formatter này: JSON thường do Jackson xử lý riêng.

## 3. DateFormatter: dành cho java.util.Date

`DateFormatter` implements `Formatter<java.util.Date>` và dựa trên `java.text.DateFormat`/`SimpleDateFormat`. Nó có thể nhận một mẫu cụ thể:

```java
import java.util.TimeZone;
import org.springframework.format.datetime.DateFormatter;

DateFormatter formatter = new DateFormatter("yyyy-MM-dd");
formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
formatter.setLenient(false);
```

Đây là **fragment** tạo formatter trong một dự án đã có thư viện Spring; không phải file Java độc lập. Ý nghĩa của từng lựa chọn:

- `"yyyy-MM-dd"` quy định mẫu ngày, ví dụ `2026-11-05`. `MM` là **tháng**; `mm` là **phút**.
- `setTimeZone(UTC)` quy định timezone dùng khi chuyển giữa **chuỗi ngày lịch** và một `Date` (thời điểm tuyệt đối). Nếu không đặt, quy tắc có thể phụ thuộc timezone mặc định của JVM.
- `setLenient(false)` từ chối các ngày vượt giới hạn như 30/02 thay vì tự điều chỉnh sang ngày khác. Đây cũng là mặc định của `DateFormatter`.
- `DateFormatter` có thể được cấu hình qua `setPattern(...)`, `setIso(...)`, `setStyle(...)`/`setStylePattern(...)` và `setFallbackPatterns(...)`. Các mẫu fallback chỉ được thử khi **parse** không thành công, không quyết định format khi **print**.

Thực chất, `java.util.Date` lưu một thời điểm. Chuỗi `2026-11-05` được parse theo mẫu date-only với UTC có nghĩa là **00:00 UTC ngày 05/11/2026**, còn parse cùng chuỗi ở múi giờ khác có thể cho `Date.getTime()` khác. Đây là lý do **ngày sinh, ngày đặt phòng, ngày đến hạn** thường phù hợp với `LocalDate` hơn `Date`.

### DateFormatterRegistrar là gì?

`org.springframework.format.datetime.DateFormatterRegistrar` là bộ đăng ký tương ứng cho các kiểu ngày giờ cũ. API chính:

```java
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.FormatterRegistry;

void registerLegacyDates(FormatterRegistry registry) {
    DateFormatterRegistrar registrar = new DateFormatterRegistrar();
    registrar.setFormatter(new DateFormatter("yyyy-MM-dd"));
    registrar.registerFormatters(registry);
}
```

Khi gọi `setFormatter(...)`, registrar đăng ký formatter chung cho các trường `Date`/`Calendar` không có annotation định dạng cụ thể, và đăng ký các converter/annotation hỗ trợ cho nhóm legacy. Nếu **không** gọi `setFormatter(...)`, registrar **không** tự thêm một formatter chung cho các trường `Date` và `Calendar` không được annotate. Các chi tiết hỗ trợ kiểu `long`/`Long` cần xem đúng ngữ cảnh converter hoặc `@DateTimeFormat`, không giả định rằng mọi số epoch tự được parse bằng pattern ngày.

Với code mới, ưu tiên `java.time`; vẫn cần biết `DateFormatter` khi tích hợp API và entity cũ.

## 4. DateTimeFormatterRegistrar: dành cho java.time

`DateTimeFormatterRegistrar` triển khai `FormatterRegistrar` và đăng ký formatter cho nhóm kiểu của Java Time API. API tiêu biểu:

| Phương thức | Tác dụng |
| --- | --- |
| `setUseIsoFormat(true)` | Dùng định dạng ISO cho các nhóm date, time và date-time; mặc định là `false` |
| `setDateStyle(FormatStyle)` | Chọn kiểu hiển thị theo locale cho ngày; mặc định `SHORT` |
| `setTimeStyle(FormatStyle)` | Chọn kiểu theo locale cho giờ; mặc định `SHORT` |
| `setDateTimeStyle(FormatStyle)` | Chọn kiểu theo locale cho ngày và giờ |
| `setDateFormatter(DateTimeFormatter)` | Dùng formatter cụ thể cho `LocalDate` |
| `setTimeFormatter(DateTimeFormatter)` | Dùng formatter cụ thể cho `LocalTime`, `OffsetTime` |
| `setDateTimeFormatter(DateTimeFormatter)` | Dùng formatter cụ thể cho `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime` |
| `registerFormatters(registry)` | Thực sự đăng ký các formatter/converter vào registry |

Các formatter được truyền trực tiếp bằng `setDateFormatter`/`setTimeFormatter`/`setDateTimeFormatter` **được ưu tiên hơn** tùy chọn style và `useIsoFormat` của nhóm tương ứng. `setUseIsoFormat(true)` làm cho style của các nhóm không còn tác dụng, trừ khi formatter cụ thể được đặt. Hãy chọn chính sách rõ ràng và test kiểu dữ liệu thực tế.

Ví dụ một cấu hình ISO ngắn:

```java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

void registerModernDates(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
```

Khi ứng dụng đã đăng ký như trên, các dạng phổ biến gồm:

| Kiểu Java | Ví dụ giá trị chuỗi ISO | Cần hiểu |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | Ngày lịch; không có múi giờ |
| `LocalTime` | `09:30:00` | Giờ trong ngày; không có ngày hoặc múi giờ |
| `LocalDateTime` | `2026-11-05T09:30:00` | Ngày và giờ địa phương; vẫn không có offset |
| `OffsetDateTime` | `2026-11-05T09:30:00+07:00` | Có UTC offset |
| `ZonedDateTime` | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` | Có thông tin zone/offset trong biểu diễn đầy đủ |
| `OffsetTime` | `09:30:00+07:00` | Có giờ và offset, không có ngày |

Các chuỗi trên minh họa hình thức dữ liệu hợp lệ tương ứng; độ dài phần giây phân số và cách in offset/zone phụ thuộc formatter cụ thể. Không biến `LocalDateTime` thành một thời điểm tuyệt đối nếu chưa biết timezone/offset.

### ISO, pattern và style khác nhau thế nào?

- **ISO** phù hợp với giao tiếp giữa hệ thống và với các giá trị chuẩn mà trình duyệt sử dụng, đặc biệt input HTML `type="date"` gửi `yyyy-MM-dd`.
- **Pattern** là hợp đồng ký tự cụ thể, ví dụ `DateTimeFormatter.ofPattern("dd/MM/uuuu")` cho `05/11/2026`. Phải xác định rõ ngôn ngữ/locale nếu dùng tên tháng, thứ.
- **Style** (`SHORT`, `MEDIUM`, `LONG`, `FULL`) nhằm hiển thị cho con người và phụ thuộc locale/JDK. Không nên coi style là định dạng dữ liệu ổn định của API.

Đối với `java.time`, pattern `uuuu` thể hiện năm proleptic và thuận lợi cho parse nghiêm ngặt; `yyyy` là năm trong era, có thể cần điều chỉnh khi dùng `ResolverStyle.STRICT`. Đối với `SimpleDateFormat` legacy, `yyyy` là quy ước năm quen thuộc. Đừng sao chép pattern giữa hai API mà không kiểm tra ý nghĩa ký tự.

## 5. Cấu hình Spring MVC hoàn chỉnh cho cả hai nhóm

Dưới đây là cấu hình Java sử dụng các registrar qua `WebMvcConfigurer.addFormatters`. Nó phù hợp để thêm chính sách định dạng cho request data binding trong **ứng dụng Spring Web MVC**:

**File `src/main/java/com/example/demo/WebDateFormatConfig.java`:**

```java
package com.example.demo;

import java.util.TimeZone;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebDateFormatConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // java.time: ISO cho LocalDate, LocalTime, LocalDateTime, ...
        DateTimeFormatterRegistrar modern = new DateTimeFormatterRegistrar();
        modern.setUseIsoFormat(true);
        modern.registerFormatters(registry);

        // java.util.Date (legacy): yyyy-MM-dd, diễn giải ở UTC.
        DateFormatter legacyDate = new DateFormatter("yyyy-MM-dd");
        legacyDate.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacyDate.setLenient(false);

        DateFormatterRegistrar legacy = new DateFormatterRegistrar();
        legacy.setFormatter(legacyDate);
        legacy.registerFormatters(registry);
    }
}
```

**File `src/main/java/com/example/demo/DateController.java`:**

```java
package com.example.demo;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Date;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DateController {

    @GetMapping("/dates")
    public String inspect(
            @RequestParam LocalDate day,
            @RequestParam Date legacy) {

        LocalDate legacyDay = legacy.toInstant()
                .atZone(ZoneOffset.UTC)
                .toLocalDate();

        return "day=" + day + ";legacyDay=" + legacyDay;
    }
}
```

Các đoạn này là **hai file trong ứng dụng Spring MVC/Spring Boot đang có dependency spring-webmvc**, không thể chỉ chạy bằng `javac` vì cần thư viện Spring và ứng dụng chạy trên HTTP server.

Giả sử các lớp nằm trong phạm vi component scan, gọi:

```http
GET /dates?day=2026-11-05&legacy=2026-11-05
```

Phần body văn bản do controller trên trả:

```text
day=2026-11-05;legacyDay=2026-11-05
```

Giải thích: `day` được parse thành `LocalDate` nhờ chính sách ISO của `DateTimeFormatterRegistrar`. `legacy` được parse thành `Date` nhờ `DateFormatter` mẫu `yyyy-MM-dd`, UTC. Controller đổi `Date` thành `LocalDate` trong UTC để minh họa ý nghĩa thời điểm. Nếu request dùng `day=05/11/2026`, formatter ISO sẽ không nhận theo cùng hợp đồng.

**Lưu ý về phạm vi:** `WebMvcConfigurer` cấu hình registry của Spring MVC. Một `ConversionService` tự tạo ở service layer, WebFlux hay bộ bind cấu hình của Spring Boot có thể dùng thiết lập khác. Đừng giả định toàn ứng dụng tự chia sẻ cùng registry.

## 6. Khi nào chọn formatter riêng cho từng loại java.time?

Ngoài ISO chung, có thể dùng các formatter cụ thể:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();

// Chuỗi date-only dd/MM/yyyy cho LocalDate:
registrar.setDateFormatter(
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT));

// Ví dụ formatter kiểu hiển thị cho LocalTime / OffsetTime:
registrar.setTimeStyle(FormatStyle.SHORT);

// Các nhóm chưa override bằng formatter cụ thể vẫn có thể dùng ISO:
registrar.setUseIsoFormat(true);
```

Đây là **fragment cấu hình**; phải gọi `registrar.registerFormatters(registry)` trong nơi có `FormatterRegistry` để có hiệu lực. Trong ví dụ, formatter cụ thể của `LocalDate` ưu tiên hơn ISO, còn ISO ưu tiên hơn style cho nhóm giờ. Vì vậy `setTimeStyle(SHORT)` **không có tác dụng** khi `useIsoFormat(true)` vẫn bật. Nếu thực sự muốn time style, bỏ `setUseIsoFormat(true)` hoặc cấu hình formatter cho time một cách riêng biệt.

Đối với kiểu mang offset/zone, không dùng bừa một pattern chỉ có `dd/MM/uuuu HH:mm`; pattern thiếu thông tin offset/zone có thể khiến việc parse `OffsetDateTime` hoặc `ZonedDateTime` thất bại. Với API cần chính xác về thời điểm, hãy xác định client cung cấp offset nào và chọn `OffsetDateTime`/`Instant` theo hợp đồng.

## 7. @DateTimeFormat so với chính sách global

`@DateTimeFormat` (Spring) áp dụng trực tiếp cho một field hoặc tham số; nó là cách chọn format *cục bộ* khi một endpoint có yêu cầu đặc biệt:

```java
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports")
    String report(
            @RequestParam
            @DateTimeFormat(pattern = "dd/MM/uuuu")
            LocalDate since) {

        return since.toString();
    }
}
```

Với cách khai báo trên, query `/reports?since=05%2F11%2F2026` được parse thành `LocalDate.of(2026,11,5)` và method trả `2026-11-05`, **ngay cả khi** global formatter cho `LocalDate` đang dùng ISO. Annotation cụ thể dùng cho thuộc tính/tham số đó được ưu tiên so với formatter toàn cục khi Spring áp dụng annotation formatting.

Những lựa chọn của annotation:
- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`: định dạng ngày ISO.
- `@DateTimeFormat(pattern = "dd/MM/uuuu")`: pattern cụ thể cho `java.time` trong Spring Framework.
- `@DateTimeFormat(style = "S-")`: kiểu ngày ngắn theo locale, dễ biến đổi khi locale/JDK đổi.
- `fallbackPatterns`: có thể hỗ trợ mẫu dự phòng **khi parse**, nhưng in ra vẫn dùng định dạng chính.

Không kết hợp tùy tiện `pattern`, `iso` và `style` trên cùng annotation: dùng **một chính sách chính**. Theo precedence của Spring, pattern có mức ưu tiên cao hơn ISO, ISO cao hơn style.

## 8. Ví dụ Java 17+ độc lập: sự khác biệt giữa hai API JDK

Để quan sát định dạng mà không phụ thuộc Spring hoặc web server, tạo file `DateFormatPlainJavaDemo.java`:

```java
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.TimeZone;

public class DateFormatPlainJavaDemo {
    public static void main(String[] args) throws Exception {
        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        LocalDate day = LocalDate.parse("05/11/2026", modern);
        System.out.println(day);
        System.out.println(modern.format(day));

        SimpleDateFormat legacy =
                new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacy.setLenient(false);

        System.out.println(legacy.format(legacy.parse("2026-11-05")));

        try {
            LocalDate.parse("31/02/2026", modern);
        } catch (DateTimeParseException ex) {
            System.out.println("INVALID_DATE");
        }
    }
}
```

Biên dịch/chạy (JDK 17+):

```bash
javac DateFormatPlainJavaDemo.java
java DateFormatPlainJavaDemo
```

Stdout chính xác:

```text
2026-11-05
05/11/2026
2026-11-05
INVALID_DATE
```

`SimpleDateFormat` dùng cho legacy mutable và không thread-safe khi chia sẻ cùng một instance giữa threads; `DateTimeFormatter` của Java Time là immutable/thread-safe và thích hợp cho ứng dụng hiện đại. Trong Spring, `DateFormatter` tạo `DateFormat` khi cần format/parse; ví dụ Java này trực tiếp tạo một `SimpleDateFormat` để minh họa pattern/timezone.

## 9. Kiểm thử trực tiếp Spring FormattingConversionService

Có thể tách xác minh registrar khỏi HTTP. Ví dụ JUnit Jupiter, giả định classpath chứa Spring Context và JUnit 5:

**File `DateRegistrarsTest.java` (trong package test của dự án):**

```java
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.TimeZone;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.format.support.DefaultFormattingConversionService;

import static org.junit.jupiter.api.Assertions.*;

class DateRegistrarsTest {

    private DefaultFormattingConversionService newService() {
        // Dịch vụ thử nghiệm độc lập, không dùng ngầm MVC registry.
        var service = new DefaultFormattingConversionService(false);

        var modern = new DateTimeFormatterRegistrar();
        modern.setUseIsoFormat(true);
        modern.registerFormatters(service);

        var legacyDate = new DateFormatter("yyyy-MM-dd");
        legacyDate.setTimeZone(TimeZone.getTimeZone("UTC"));
        var legacy = new DateFormatterRegistrar();
        legacy.setFormatter(legacyDate);
        legacy.registerFormatters(service);

        return service;
    }

    @Test
    void isoLocalDateAndUtcLegacyDate() {
        var service = newService();

        assertEquals(
                LocalDate.of(2026, 11, 5),
                service.convert("2026-11-05", LocalDate.class));

        Date legacyDate = service.convert("2026-11-05", Date.class);
        assertNotNull(legacyDate);
        assertEquals(
                LocalDate.of(2026, 11, 5),
                legacyDate.toInstant()
                        .atZone(ZoneOffset.UTC)
                        .toLocalDate());
    }

    @Test
    void incorrectPatternFailsInsteadOfGuessing() {
        var service = newService();

        assertThrows(
                ConversionFailedException.class,
                () -> service.convert("05/11/2026", LocalDate.class));
    }
}
```

`DefaultFormattingConversionService(false)` ở đây dùng để kiểm thử chính sách registrar với một registry độc lập và tránh phụ thuộc formatter mặc định. Khi cấu hình một `FormattingConversionService` thay thế cho ứng dụng thực, phải đăng ký đầy đủ những formatter/annotation factory còn cần thiết; ví dụ bộ test không đại diện cho toàn bộ default configuration của Spring MVC/Boot.

Ngoài unit test, cần integration test dùng `MockMvc` hoặc gọi HTTP thật để bảo đảm `WebMvcConfigurer` được scan, URL được parse và lỗi chuyển đổi được phản ánh đúng. Hãy kiểm thử cả ngày hợp lệ, sai pattern, ngày không tồn tại, timezone và chuỗi thiếu.

## 10. Quy tắc chọn kiểu dữ liệu và xử lý lỗi binding

| Dữ liệu nghiệp vụ | Kiểu nên xem xét | Lý do |
| --- | --- | --- |
| Ngày sinh, ngày giao hàng | `LocalDate` | Không phụ thuộc timezone |
| Giờ mở cửa (độc lập ngày) | `LocalTime` | Không có date/offset |
| Lịch hẹn giờ địa phương chưa gắn vùng | `LocalDateTime` | Lưu ngày + giờ địa phương; chưa xác định instant |
| Sự kiện có offset trong request | `OffsetDateTime` | Chuỗi chứa offset để xác định instant |
| Thời điểm log/sự kiện tuyệt đối | `Instant` | Mốc UTC trên timeline |
| Hệ thống cũ dùng `java.util.Date` | `Date` | Cần quan tâm timezone khi parse/print |

Trường hợp parse sai pattern, ví dụ gửi `day=05/11/2026` cho formatter ISO, Spring không tạo được `LocalDate`. Trong `ConversionService`, lỗi có thể được bọc thành `ConversionFailedException`; trong một controller MVC dùng `@RequestParam`, lỗi kiểu dữ liệu thường dẫn tới HTTP 400; trong `@ModelAttribute` có thể sinh lỗi `typeMismatch` trong `BindingResult`. Bean Validation chỉ kiểm tra các object đã bind được; nó không tự sửa chuỗi ngày sai định dạng.

Đối với body JSON (`@RequestBody`), Jackson thường deserialize chuỗi ngày giờ theo cấu hình `ObjectMapper`/module Java Time. `@JsonFormat` là annotation thuộc Jackson, khác `@DateTimeFormat` của Spring. Không kết luận rằng cấu hình `DateTimeFormatterRegistrar` trong MVC sẽ tự đổi cách Jackson đọc JSON. Tương tự, Spring WebFlux và Spring Boot configuration binding có cơ chế cấu hình riêng.

## 11. Lỗi phổ biến khi triển khai

1. **Nhầm `DateFormatter` với `DateTimeFormatter`:** cái đầu là Spring formatter của `Date`, cái sau là Java Time formatter trong JDK; `DateTimeFormatterRegistrar` đăng ký nhóm formatter Java Time.
2. **Đã tạo registrar nhưng không gọi `registerFormatters(registry)`:** cấu hình không được thêm vào dịch vụ chuyển đổi.
3. **Đăng ký đúng nhưng sai registry:** MVC, WebFlux, Jackson, và configuration binding không nhất thiết dùng chung conversion service.
4. **Sử dụng `dd/MM/yyyy` cho client HTML `input type="date"`:** trình duyệt gửi `yyyy-MM-dd` dù giao diện địa phương hiển thị khác; chọn ISO khi phù hợp.
5. **Nhầm `MM` và `mm`, hoặc `yyyy` và `YYYY`:** `MM` là tháng, `mm` là phút, còn `YYYY` thường là *week-based-year* trong JDK; có thể sai quanh năm mới.
6. **Parse date-only thành `Date` không chỉ rõ timezone:** cùng chuỗi có thể tạo timestamp khác trên những server ở múi giờ khác nhau.
7. **Dùng `LocalDateTime` như một instant:** kiểu này không có offset/zone, không đủ để xác định khoảnh khắc tuyệt đối.
8. **Kỳ vọng `@DateTimeFormat` sửa JSON:** JSON cần cấu hình Jackson riêng.
9. **Cố chấp với style phụ thuộc locale/JDK:** định dạng hiển thị có thể thay đổi theo runtime; dữ liệu API nên dùng ISO/pattern xác định.
10. **Dùng `SimpleDateFormat` singleton tự tạo:** lớp này mutable và không an toàn khi nhiều threads dùng chung; ưu tiên `DateTimeFormatter` cho dự án hiện đại.

## 12. Checklist thiết kế định dạng ngày giờ

- Chọn **kiểu Java đúng ý nghĩa nghiệp vụ** trước khi chọn pattern.
- Xác định dữ liệu đến từ **query/path/form**, hay **JSON body**, vì cơ chế parser khác nhau.
- Với `java.time`, đăng ký `DateTimeFormatterRegistrar`; với legacy `Date`, dùng `DateFormatter` và `DateFormatterRegistrar` khi cần.
- Ưu tiên ISO cho giao tiếp giữa hệ thống; dùng pattern theo locale khi yêu cầu giao diện thật sự cần.
- Với `Date`, cố định timezone nếu cần kết quả ổn định giữa môi trường.
- Định nghĩa cách báo lỗi cho chuỗi sai, ngày không tồn tại, timezone không hợp lệ; không tự đoán ngày.
- Test unit cho conversion và integration cho data binding/controller; luôn kiểm tra đúng Spring version và cấu hình runtime.

### Tham khảo chính thức

- [Spring Framework — Configuring a Global Date and Time Format](https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html).
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html).
- [Spring Framework — Spring MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html).
- [Spring Framework Javadoc — DateFormatter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/DateFormatter.html).
- [Spring Framework Javadoc — DateFormatterRegistrar](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/DateFormatterRegistrar.html).
- [Spring Framework Javadoc — DateTimeFormatterRegistrar](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html).
