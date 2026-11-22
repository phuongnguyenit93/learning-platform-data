# DateFormatterRegistrar cho API thời gian cũ trong Spring Framework

> **Module:** Spring Framework – validation-data-binding  
> **Nhóm kiến thức:** Định dạng thời gian  
> **Trọng tâm:** Đăng ký quy tắc parse/print cho `java.util.Date`, `java.util.Calendar` và các phép chuyển đổi liên quan đến `long`/epoch milliseconds bằng `DateFormatterRegistrar`.

## 1. Vì sao cần `DateFormatterRegistrar`?

Trong ứng dụng Java lâu năm, DTO, entity hoặc API tích hợp có thể vẫn sử dụng các kiểu thời gian cổ điển như `Date` và `Calendar`. Trong khi đó, dữ liệu từ query parameter, URL path và HTML form thường là **chuỗi**, ví dụ:

```text
GET /legacy/date?value=05%2F11%2F2026
```

Spring MVC phải đổi chuỗi `05/11/2026` thành đối tượng Java có kiểu `Date` trước khi gọi controller. Nếu mọi điểm nhập đều theo quy ước `dd/MM/yyyy`, việc viết formatter lặp lại cho từng field dễ gây sai lệch.

`org.springframework.format.datetime.DateFormatterRegistrar` là một `FormatterRegistrar` do Spring cung cấp để **đăng ký nhóm formatter và converter liên quan đến API ngày giờ cũ** vào `FormatterRegistry`. Khi cấu hình một `DateFormatter` qua `setFormatter(...)`, registrar có thể áp dụng định dạng chung cho các field `Date` và `Calendar` **không gắn `@DateTimeFormat`**. Nó cũng đăng ký hỗ trợ annotation và các converter liên quan đến `Date`, `Calendar`, `Long`.

Mục tiêu của bài: hiểu đúng vai trò registrar, tránh đánh đồng các phép chuyển đổi kiểu Java với định dạng chuỗi, và triển khai được định dạng ngày cũ có kiểm soát timezone.

## 2. Phân biệt bốn thành phần trong Spring

| Thành phần | Package / vai trò | Cách dùng |
| --- | --- | --- |
| `DateFormatter` | `org.springframework.format.datetime.DateFormatter` — `Formatter<Date>` | Parse chuỗi thành `Date` và print `Date` thành chuỗi theo pattern/style/ISO/locale/timezone |
| `DateFormatterRegistrar` | `org.springframework.format.datetime.DateFormatterRegistrar` — `FormatterRegistrar` | Đăng ký formatter cho các kiểu ngày cũ, converter và factory hỗ trợ annotation |
| `FormatterRegistry` | `org.springframework.format.FormatterRegistry` | Nơi các formatter và converter được đăng ký |
| `FormattingConversionService` | `org.springframework.format.support.FormattingConversionService` | Sử dụng các quy tắc đã đăng ký khi chuyển đổi, parse và print dữ liệu |

Cơ chế tổng quát:

```text
Định nghĩa formatter: DateFormatter("dd/MM/yyyy")
            |
            v
DateFormatterRegistrar.setFormatter(...)
            |
            v
registerFormatters(FormatterRegistry)
            |
            +-- Converter: Date <-> Long, Date <-> Calendar,
            |              Calendar <-> Long
            +-- Formatter<Date> và formatter cho Calendar
            |   (khi đã gọi setFormatter)
            +-- @DateTimeFormat annotation formatter factory
            |
            v
Spring MVC ConversionService
            |
            v
"05/11/2026" -> Date / Calendar -> controller
```

`DateFormatter` **định nghĩa cách biểu diễn**; `DateFormatterRegistrar` **gắn các khả năng vào registry**; `ConversionService` **thực thi chuyển đổi** tại vị trí cần thiết. `DateFormatterRegistrar` không tự tạo endpoint, không đọc HTTP và không tự bật Bean Validation.

## 3. Các kiểu legacy liên quan

### 3.1. `java.util.Date`

`Date` lưu một thời điểm (instant) với độ chính xác mili giây tính từ Unix epoch; `Date.getTime()` trả về số mili giây kể từ 1970-01-01T00:00:00Z. Bản thân `Date` không lưu một pattern định dạng hay timezone. Một instant có thể hiện ra thành ngày khác nhau nếu format theo timezone khác nhau.

### 3.2. `java.util.Calendar`

`Calendar` là đối tượng lịch có timezone và trạng thái thay đổi được. Nó có thể biểu diễn cùng instant với `Date` nhưng cung cấp các trường năm/tháng/ngày/giờ theo lịch và timezone đang dùng. Các API cũ thường nhận `Calendar`, dù ứng dụng mới đa phần nên ưu tiên `java.time` bất biến.

### 3.3. `long` và `Long`

Một giá trị `long` dùng làm timestamp thường chứa **epoch milliseconds**, ví dụ `1793836800000` là thời điểm 2026-11-05T00:00:00Z.

`DateFormatterRegistrar.addDateConverters(...)` cung cấp các phép chuyển đổi typed-value:

```text
Date     <-> Long
Date     <-> Calendar
Calendar <-> Long
```

Các converter trên không có nghĩa mọi `Long` không annotation sẽ được parse từ chuỗi ngày `dd/MM/yyyy`. Phân biệt rõ:
- `"1793836800000"` → `Long` thường là chuyển chuỗi thành **số**.
- `"05/11/2026"` → `Date` là **parse ngày theo formatter**.
- `Date` → `Long` là **lấy epoch milliseconds**.

Không nhầm epoch milliseconds với epoch seconds (chênh lệch hệ số 1.000).

## 4. Chính xác `DateFormatterRegistrar` đăng ký những gì?

Các API quan trọng:

```java
DateFormatterRegistrar registrar = new DateFormatterRegistrar();
registrar.setFormatter(new DateFormatter("dd/MM/yyyy"));
registrar.registerFormatters(registry);
```

Khi gọi `registerFormatters(registry)`, Spring thực hiện ba nhóm việc:

1. **Luôn đăng ký** các converter giữa `Date`, `Calendar` và `Long` (thông qua `addDateConverters`).
2. **Chỉ khi đã gọi `setFormatter(DateFormatter)`**, đăng ký formatter chung cho field `Date` và `Calendar` không được đánh dấu bằng quy tắc format riêng.
3. Đăng ký `DateTimeFormatAnnotationFormatterFactory` để các trường/tham số legacy mang `@DateTimeFormat` được parse/print theo annotation.

Điểm số 2 rất quan trọng: tạo registrar rồi chỉ gọi `registerFormatters` **không tự thiết lập một global pattern `dd/MM/yyyy`**. Không có `setFormatter`, những trường không annotation sử dụng quy tắc khác hiện có trong registry (hoặc có thể không chuyển được tùy cấu hình). Đừng kết luận rằng không có `setFormatter` thì mọi chuyển đổi `Date` đều bị vô hiệu — registrar vẫn thêm các converter và hỗ trợ annotation.

Phương thức static:

```java
DateFormatterRegistrar.addDateConverters(converterRegistry);
```

chỉ hữu ích khi **chỉ muốn** nhóm converter `Date`/`Calendar`/`Long`, không cần cả registrar hỗ trợ định dạng chuỗi.

## 5. Cấu hình `DateFormatter` đúng cách

`DateFormatter` nhận mẫu dựa trên API `java.text.DateFormat` / `SimpleDateFormat`. Ví dụ:

```java
DateFormatter formatter = new DateFormatter("dd/MM/yyyy");
formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
formatter.setLenient(false);
```

Ba lựa chọn trên có ý nghĩa:

- `"dd/MM/yyyy"`: quy ước ngày/tháng/năm theo hai chữ số cho ngày và tháng.
- `setTimeZone(...)`: chọn rõ múi giờ để chuyển **chuỗi ngày không có giờ** thành một instant; trong ví dụ `05/11/2026` tương ứng **2026-11-05T00:00:00Z**. Chọn UTC chỉ là quyết định minh họa; với dữ liệu ngày mang ý nghĩa vùng cụ thể, cần chọn timezone nghiệp vụ đúng.
- `setLenient(false)`: từ chối các trường lịch không hợp lệ, ví dụ 31/02/2026, thay vì tự “chuẩn hóa” thành ngày khác. Đây cũng là giá trị mặc định của `DateFormatter`, nhưng khai báo tường minh giúp người đọc nhận rõ quy tắc.

Các lựa chọn khác của `DateFormatter` gồm:

| Phương thức | Tác dụng | Lưu ý |
| --- | --- | --- |
| `new DateFormatter("yyyyMMdd")` hoặc `setPattern("yyyyMMdd")` | Pattern cố định | `MM` là tháng, `mm` là phút; `yyyy` khác `YYYY` |
| `setIso(DateTimeFormat.ISO.DATE)` | Mẫu ISO theo Spring | Với kiểu `Date`, ISO thường gắn với UTC |
| `setStylePattern("S-")` | Style ngắn cho ngày, không có giờ | Locale/JDK có thể khiến chuỗi thay đổi |
| `setTimeZone(TimeZone)` | Timezone dùng cho formatter | Tránh phụ thuộc timezone mặc định của máy |
| `setLenient(boolean)` | Điều khiển độ dễ dãi của parsing | Không thay thế kiểm tra nghiệp vụ |
| `setFallbackPatterns(String...)` | Các mẫu dự phòng khi parse thất bại | Chỉ dùng khi parse; print vẫn theo mẫu chính |

Khi dùng style phụ thuộc locale, không nên coi một chuỗi cụ thể là giao thức cố định giữa nhiều client. Với API cần dự đoán chính xác, ưu tiên pattern/ISO được thống nhất và kiểm thử.

## 6. Đăng ký trong Spring MVC bằng `WebMvcConfigurer`

Đây là cách thường dùng khi có ứng dụng Spring MVC/Spring Boot với các form và query legacy. Ví dụ hoàn chỉnh cần **Java 17+** và dependency `spring-boot-starter-web`.

Đặt mã vào `src/main/java/example/legacydate/LegacyDateApplication.java`:

```java
package example.legacydate;

import java.util.Calendar;
import java.util.Date;
import java.util.TimeZone;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class LegacyDateApplication implements WebMvcConfigurer {

    public static void main(String[] args) {
        SpringApplication.run(LegacyDateApplication.class, args);
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateFormatter formatter = new DateFormatter("dd/MM/yyyy");
        formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
        formatter.setLenient(false);

        DateFormatterRegistrar registrar = new DateFormatterRegistrar();
        registrar.setFormatter(formatter);
        registrar.registerFormatters(registry);
    }

    @RestController
    public static class LegacyDateController {

        @GetMapping("/legacy/date")
        public String date(@RequestParam("value") Date value) {
            return value.toInstant().toString();
        }

        @GetMapping("/legacy/calendar")
        public String calendar(@RequestParam("value") Calendar value) {
            return value.toInstant().toString();
        }

        @PostMapping("/legacy/form")
        public String form(
                @ModelAttribute AppointmentForm appointment,
                BindingResult bindingResult) {
            if (bindingResult.hasErrors()) {
                return "invalid-date";
            }
            return appointment.getWhen().toInstant().toString();
        }
    }

    public static class AppointmentForm {
        private Date when;

        public Date getWhen() {
            return when;
        }

        public void setWhen(Date when) {
            this.when = when;
        }
    }
}
```

**Cách chạy:** Trong một dự án Spring Boot có `spring-boot-starter-web`, lưu file đúng package/path rồi dùng `./mvnw spring-boot:run` (Maven wrapper) hoặc `./gradlew bootRun` (Gradle wrapper) tùy dự án. Chạy với cổng mặc định `8080` và bảo đảm không có cấu hình formatter khác ghi đè quy tắc này.

Gửi request:

```bash
curl -G --data-urlencode "value=05/11/2026" http://localhost:8080/legacy/date
curl -G --data-urlencode "value=05/11/2026" http://localhost:8080/legacy/calendar
curl -X POST --data-urlencode "when=05/11/2026" http://localhost:8080/legacy/form
```

Body của từng response trong điều kiện đã nêu:

```text
2026-11-05T00:00:00Z
2026-11-05T00:00:00Z
2026-11-05T00:00:00Z
```

Tại sao các response đều giống nhau?

- `DateFormatter` parse chuỗi `05/11/2026` thành cùng instant vì đã định rõ UTC.
- `Date` và `Calendar` đại diện cùng thời điểm đó; `toInstant().toString()` biểu diễn UTC theo ISO.
- DTO `AppointmentForm` không có `@DateTimeFormat`, nên binding của field `when` dùng formatter toàn cục đã đăng ký.
- `BindingResult` đặt **ngay sau** `@ModelAttribute` để bắt lỗi binding, chẳng hạn nhập sai pattern. Việc trả chuỗi `"invalid-date"` chỉ nhằm minh họa nhánh lỗi; ứng dụng thực cần mã HTTP/status và cấu trúc lỗi phù hợp.

**Giới hạn quan trọng:** Bản thân `DateFormatterRegistrar` xử lý conversion trong Spring. Các output trên do **mã controller tự gọi `toInstant()`**, không phải do formatter tự thay đổi kiểu trả về hoặc cấu trúc JSON.

## 7. Thử trực tiếp với `FormattingConversionService`

Không cần khởi động web server nếu chỉ muốn kiểm tra registrar. Mã sau có thể đặt trong một dự án Java 17+ **đã có thư viện `spring-context` và các phụ thuộc Spring liên quan**. Đây là một class độc lập có `main`, nhưng `javac` thuần vẫn cần classpath Spring.

Tệp `RegistrarDemo.java`:

```java
import java.util.Date;
import java.util.TimeZone;

import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.support.DefaultFormattingConversionService;

public class RegistrarDemo {
    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService(false);

        DateFormatter formatter = new DateFormatter("dd/MM/yyyy");
        formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
        formatter.setLenient(false);

        DateFormatterRegistrar registrar = new DateFormatterRegistrar();
        registrar.setFormatter(formatter);
        registrar.registerFormatters(service);

        Date parsed = service.convert("05/11/2026", Date.class);
        Long millis = service.convert(parsed, Long.class);
        String printed = service.convert(parsed, String.class);

        System.out.println(parsed.toInstant());
        System.out.println(millis);
        System.out.println(printed);
    }
}
```

Stdout khi chạy class này với Spring 6.x trên classpath:

```text
2026-11-05T00:00:00Z
1793836800000
05/11/2026
```

`DefaultFormattingConversionService(false)` dùng ở đây để có registry kiểm soát được formatter mặc định trong bài thử. **Không** sao chép nguyên cấu hình này để thay thế toàn bộ conversion service của ứng dụng thực mà không đăng ký lại các formatter khác đang cần; Spring Boot/Spring MVC thường đã có registry, và `WebMvcConfigurer#addFormatters` ở mục trước phù hợp hơn để bổ sung quy tắc.

Luồng chi tiết:

```text
"05/11/2026" --(DateFormatter.parse)--> Date
Date             --(DateToLongConverter)--> Long 1793836800000
Date             --(DateFormatter.print)--> "05/11/2026"
```

`Long` ở giữa là giá trị **epoch milliseconds**, không phải một số nguyên có định dạng ngày/tháng.

## 8. Đối chiếu bằng Java 17 không cần Spring

Để tự kiểm chứng timezone và epoch milliseconds ngay cả khi chưa tạo Spring project, lưu chương trình Java thuần sau thành `DateEpochCheck.java`:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DateEpochCheck {
    public static void main(String[] args) throws Exception {
        SimpleDateFormat format =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);

        Date date = format.parse("05/11/2026");

        System.out.println(date.toInstant());
        System.out.println(date.getTime());
        System.out.println(format.format(date));
    }
}
```

Chạy:

```bash
javac DateEpochCheck.java
java DateEpochCheck
```

Stdout chính xác:

```text
2026-11-05T00:00:00Z
1793836800000
05/11/2026
```

Đây là phép kiểm tra `java.text` độc lập, **không** chứng minh Spring đã đăng ký formatter; để kiểm tra wiring của `DateFormatterRegistrar`, chạy mục 6 hoặc 7.

## 9. Toàn cục và cục bộ: `@DateTimeFormat`

Khi một quy tắc chung đã được đăng ký, một trường legacy đôi khi cần cú pháp riêng. Spring có `@DateTimeFormat` để khai báo trên từng field hoặc parameter.

```java
import java.util.Date;
import org.springframework.format.annotation.DateTimeFormat;

public class LegacyCommand {
    private Date submittedOn; // dùng định dạng chung nếu được bind qua registry

    @DateTimeFormat(pattern = "yyyy-MM-dd")
    private Date approvedOn;  // định dạng riêng cho field này

    public Date getSubmittedOn() {
        return submittedOn;
    }

    public void setSubmittedOn(Date submittedOn) {
        this.submittedOn = submittedOn;
    }

    public Date getApprovedOn() {
        return approvedOn;
    }

    public void setApprovedOn(Date approvedOn) {
        this.approvedOn = approvedOn;
    }
}
```

Đoạn này là **DTO minh họa**, không phải ứng dụng chạy độc lập. Khi binding từ form với conversion service đã đăng ký:

- `submittedOn` nhận chuỗi theo quy tắc chung, ví dụ `05/11/2026`.
- `approvedOn` được điều khiển bởi `@DateTimeFormat(pattern = "yyyy-MM-dd")`, ví dụ `2026-11-05`.

Với `java.util.Date`, pattern/style trên `@DateTimeFormat` dùng **timezone mặc định của JVM**, còn ISO dùng UTC theo Javadoc. Annotation không có thuộc tính `timezone`; đừng giả định `setTimeZone(UTC)` trên global formatter tự áp dụng cho một annotation khai báo formatter riêng. Nếu muốn cùng một instant khi dùng annotation pattern, cần chủ động quản lý timezone của ứng dụng hoặc chọn kiểu dữ liệu / cơ chế chuyển đổi thích hợp.

Phân biệt:

| Cơ chế | Phạm vi | Ví dụ |
| --- | --- | --- |
| `DateFormatterRegistrar.setFormatter(...)` | Quy tắc chung cho field `Date`/`Calendar` không annotation trong registry liên quan | Form legacy đồng nhất `dd/MM/yyyy` |
| `@DateTimeFormat(pattern=...)` | Field hoặc parameter có annotation | Ngoại lệ `yyyy-MM-dd` trên một field |
| `DateTimeFormatterRegistrar` | Mặc định cho các kiểu `java.time` | `LocalDate`, `LocalTime`, `LocalDateTime` |
| `@JsonFormat` / cấu hình Jackson | JSON serialization/deserialization | Body `@RequestBody` hoặc JSON response |

Cần lưu ý `@DateTimeFormat` không tự thay đổi cách Jackson đọc một JSON `@RequestBody`. Trường `Date` trong JSON phải theo quy tắc Jackson đã cấu hình.

## 10. Phân biệt `DateFormatterRegistrar` với `DateTimeFormatterRegistrar`

Hai class tên rất giống nhưng giải quyết hai họ API khác nhau:

```java
import org.springframework.format.datetime.DateFormatterRegistrar;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
```

| Tiêu chí | `DateFormatterRegistrar` | `DateTimeFormatterRegistrar` |
| --- | --- | --- |
| Đối tượng chính | API cũ: `Date`, `Calendar`, chuyển đổi `Long` | API mới: `LocalDate`, `LocalTime`, `LocalDateTime` và kiểu `java.time` liên quan |
| Formatter cấu hình | `org.springframework.format.datetime.DateFormatter` | `java.time.format.DateTimeFormatter` |
| Phương thức điển hình | `setFormatter(DateFormatter)` | `setDateFormatter(DateTimeFormatter)`, `setTimeFormatter(...)`, `setDateTimeFormatter(...)`, `setUseIsoFormat(true)` |
| Ngữ nghĩa thời gian | `Date` đại diện instant; timezone cần cho parse ngày/giờ | Nhiều kiểu mới tách rõ date/time/local/offset/zone |
| Nên dùng khi | Cần tích hợp hoặc duy trì API legacy | Thiết kế mới có thể dùng `java.time` |

Một ứng dụng có thể đăng ký cả hai nếu cùng lúc xử lý legacy và `java.time`. Tuy nhiên, **không** truyền `DateTimeFormatter.ofPattern(...)` vào `DateFormatterRegistrar.setFormatter(...)`: hai kiểu tham số khác nhau, code sẽ không biên dịch.

## 11. Timezone, locale, leniency và an toàn dữ liệu

**Timezone.** Với ngày chỉ có phần `dd/MM/yyyy`, Java phải chọn một mốc giờ khi tạo `Date`. Nếu không cố định timezone, kết quả `Date.getTime()` có thể khác giữa server UTC và server Asia/Ho_Chi_Minh. Ví dụ cùng ngày `05/11/2026`:

```text
Mốc 00:00 theo UTC              = 2026-11-05T00:00:00Z
Mốc 00:00 theo Asia/Ho_Chi_Minh = 2026-11-04T17:00:00Z
```

Hai giá trị khác nhau bảy giờ nhưng có thể được trình bày cùng một ngày trong timezone tương ứng. Chọn timezone theo nghiệp vụ trước khi parse dữ liệu legacy. Nếu bản chất dữ liệu là **ngày thuần** không có thời điểm, `LocalDate` thường thích hợp hơn.

**Locale.** `DateFormatter` hỗ trợ `Locale`. Pattern số như `dd/MM/yyyy` giảm sự mơ hồ, còn định dạng có tên tháng hoặc style (`M-`, `S-`...) có thể biến đổi theo locale và dữ liệu CLDR/JDK. Không xây dựng API cố định dựa trên chuỗi format locale nhạy cảm nếu chưa có hợp đồng rõ ràng.

**Leniency.** `setLenient(false)` giúp từ chối ngày không hợp lệ. Tuy nhiên, việc một chuỗi parse được không có nghĩa ngày đó được phép theo nghiệp vụ: ví dụ ngày kết thúc trước ngày bắt đầu vẫn phải được validate riêng.

**Tính mutable.** `Date` và `Calendar` có trạng thái thay đổi được; tránh lưu một instance chia sẻ giữa nhiều luồng. `DateFormatter` là cấu hình cho quá trình format, không nên tự tạo một `SimpleDateFormat` mutable dùng chung toàn ứng dụng để xử lý request concurrent.

## 12. Những lỗi thường gặp

1. **Chỉ tạo registrar rồi gọi `registerFormatters`, quên `setFormatter`.** Các converter và annotation support vẫn được thêm, nhưng không có global formatter riêng cho unannotated `Date`/`Calendar`.
2. **Nhầm `DateFormatterRegistrar` với `DateTimeFormatterRegistrar`.** Hãy đọc package, kiểu Java đích và loại formatter mà setter nhận.
3. **Nhầm mẫu `dd/MM/yyyy` với `dd/mm/YYYY`.** `MM` là tháng; `mm` là phút; `YYYY` là năm theo tuần, không phải năm thông thường.
4. **Bỏ timezone trong hệ thống nhiều máy chủ.** Có thể khiến cùng chuỗi ngày trở thành timestamp khác nhau.
5. **Hiểu `long` là chuỗi ngày có formatter toàn cục.** `Long` chủ yếu đóng vai trò epoch milliseconds trong các converter này.
6. **Cho rằng global formatter tự áp dụng cho JSON body.** JSON do Jackson phụ trách; kiểm tra `@JsonFormat` hoặc cấu hình `ObjectMapper`.
7. **Lạm dụng `Date` cho thông tin chỉ có ngày.** Một `LocalDate` có thể tránh sai lệch timezone khi đổi dữ liệu sang thiết kế mới.
8. **Quên `BindingResult` khi cần thông báo lỗi form.** Binding sai pattern sinh lỗi conversion; xử lý lỗi theo hợp đồng HTTP.
9. **Thay `ConversionService` mặc định mà không giữ các formatter khác.** Khi cấu hình thay thế hoàn toàn, phải bảo đảm các chuyển đổi khác của ứng dụng vẫn hoạt động.
10. **Tin rằng parse thành công là validation đầy đủ.** Vẫn phải kiểm tra bắt buộc, giới hạn ngày, thứ tự thời gian và ràng buộc nghiệp vụ.

## 13. Bài tập tự kiểm tra

**Câu 1.** Một DTO có `Date shippedAt` không annotation; toàn ứng dụng nhận `dd/MM/yyyy`. Nên cấu hình lớp nào?

- Tạo `DateFormatter("dd/MM/yyyy")`, gắn vào `DateFormatterRegistrar.setFormatter(...)`, rồi đăng ký registrar với `FormatterRegistry` dùng cho binding của ứng dụng.

**Câu 2.** `DateFormatterRegistrar` đã gọi `registerFormatters` nhưng không gọi `setFormatter`. Điều nào vẫn xảy ra?

- Các converter `Date`/`Calendar`/`Long` và factory hỗ trợ `@DateTimeFormat` được đăng ký. Global formatter cho field `Date`/`Calendar` không annotation không được đăng ký bởi registrar đó.

**Câu 3.** `Date` của `05/11/2026` tại 00:00 UTC có `getTime()` bằng bao nhiêu?

- `1793836800000` mili giây. Đây là timestamp, không phải `20261105`.

**Câu 4.** Cùng DTO có field `LocalDate` và `Date`; đăng ký `DateFormatterRegistrar` có đủ để cấu hình chung cho cả hai kiểu không?

- Không. `LocalDate` thuộc `java.time`, thường dùng `DateTimeFormatterRegistrar` hoặc `@DateTimeFormat` tương ứng.

**Câu 5.** Vì sao API nhận chuỗi `05/11/2026` nhưng response JSON vẫn là ISO mặc dù registrar đã được cấu hình?

- Vì registrar phục vụ conversion/binding ở luồng Spring; JSON response có thể do Jackson serialize theo cấu hình riêng. Trong ví dụ controller trả `String` thì kết quả đến từ `toInstant().toString()`.

## 14. Ghi nhớ

- `DateFormatterRegistrar` là **bộ đăng ký**, không phải bản thân formatter.
- `setFormatter(DateFormatter)` là bước cần thiết khi muốn **global format cụ thể** cho unannotated `Date`/`Calendar`.
- Registrar vẫn hỗ trợ converter `Date` ↔ `Calendar` ↔ `Long` và `@DateTimeFormat` khi không đặt formatter toàn cục.
- Luôn kiểm soát timezone khi chuyển ngày thuần thành `Date`/epoch milliseconds.
- Ưu tiên `java.time` ở thiết kế mới; dùng các kiểu legacy khi tích hợp hoặc duy trì hệ thống hiện hữu.

### Nguồn kỹ thuật chính thức

- Spring Framework, `DateFormatterRegistrar` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/DateFormatterRegistrar.html
- Spring Framework, `DateFormatter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/format/datetime/DateFormatter.html
- Spring Framework, Configuring a Global Date and Time Format: https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html
- Spring MVC, Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
