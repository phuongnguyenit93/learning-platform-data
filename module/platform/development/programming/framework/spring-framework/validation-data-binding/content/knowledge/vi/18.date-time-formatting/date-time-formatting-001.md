# @DateTimeFormat với ISO, pattern và style trong Spring Framework

> **Chủ đề:** Spring Framework – validation-data-binding → Định dạng thời gian. Bài này tập trung vào cách Spring chuyển chuỗi ngày/giờ thành kiểu Java và định dạng ngược lại bằng `@DateTimeFormat`.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `@DateTimeFormat` trong quá trình data binding và formatting của Spring.
- Phân biệt ba cách cấu hình `iso`, `pattern` và `style`, chọn đúng cách cho từng nguồn dữ liệu.
- Áp dụng annotation cho `@RequestParam`, trường của `@ModelAttribute` và các kiểu `java.time`.
- Dự đoán kết quả parse hợp lệ, nhận biết lỗi định dạng, locale, múi giờ và pattern.
- Biết khi nào cần `fallbackPatterns`, `BindingResult` hoặc cơ chế khác như JSON/Jackson.

## 2. `@DateTimeFormat` giải quyết vấn đề gì?

HTTP query parameter, path variable và dữ liệu form thường đến dưới dạng **chuỗi**. Nhưng mã Java cần `LocalDate`, `LocalTime`, `LocalDateTime` hoặc kiểu thời gian khác. Spring dùng `ConversionService` và các `Formatter` để chuyển đổi trong quá trình binding. `@DateTimeFormat` khai báo quy tắc parse (chuỗi → đối tượng thời gian) và print (đối tượng → chuỗi) cho trường hoặc tham số được đánh dấu.

Ví dụ, client gửi `date=05/11/2026`; một trường `LocalDate` có `@DateTimeFormat(pattern = "dd/MM/yyyy")` được bind thành ngày **5 tháng 11 năm 2026**, không phải ngày 11 tháng 5. Quy tắc này thuộc tầng **định dạng/chuyển đổi dữ liệu**; nó không tự kiểm tra một ngày có nằm trong tương lai hay không. Các ràng buộc nghiệp vụ như `@Future`, `@Past` hoặc `@NotNull` thuộc Bean Validation.

Annotation nằm trong package:

```java
import org.springframework.format.annotation.DateTimeFormat;
```

Có thể đặt trên field, method hoặc method parameter; trong Spring MVC các vị trí thường gặp là tham số `@RequestParam`, `@PathVariable` và field của đối tượng `@ModelAttribute`. Kiểu được hỗ trợ gồm `java.util.Date`, `Calendar`, `Long` biểu diễn thời điểm theo mili giây, cùng các kiểu thời gian trong `java.time` như `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime` khi formatter tương ứng hỗ trợ.

Luồng xử lý điển hình:

```text
Chuỗi từ query/form/path
    → Spring MVC WebDataBinder
    → ConversionService / Formatter dựa trên @DateTimeFormat
    → LocalDate, LocalDateTime, ...
    → controller / model
```

Khi không parse được giá trị, binding tạo lỗi chuyển đổi; hành vi trả lỗi tùy vị trí annotation và cách controller xử lý.

## 3. Ba lựa chọn: `iso`, `pattern`, `style`

| Thuộc tính | Đặc điểm | Ví dụ khai báo | Chuỗi minh họa | Nên dùng |
| --- | --- | --- | --- | --- |
| `iso` | Dùng chuẩn ngày/giờ ISO được Spring hỗ trợ; ổn định cho giao tiếp máy | `iso = DateTimeFormat.ISO.DATE` | `2026-11-05` | Query/form/API có định dạng ISO xác định |
| `pattern` | Mẫu tùy chỉnh với các ký hiệu ngày/giờ | `pattern = "dd/MM/yyyy"` | `05/11/2026` | Form hoặc hệ thống có quy ước nhập rõ ràng |
| `style` | Định dạng ngắn/vừa/dài/đầy đủ theo locale | `style = "M-"` | Có thể là `Nov 5, 2026` với locale tiếng Anh Mỹ | Giao diện nhập/xuất theo ngôn ngữ và vùng |

**Chỉ cấu hình một trong ba thuộc tính chính cho mỗi annotation.** Nếu vô tình khai báo nhiều thuộc tính, thứ tự ưu tiên trong Spring là **`pattern` > `iso` > `style`**. Không nên dựa vào ưu tiên này để viết annotation khó hiểu. Khi không khai báo gì, mặc định là style `"SS"` (ngày ngắn, giờ ngắn).

### 3.1. `iso`: định dạng chuẩn

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate startDate;

@DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
private LocalTime startTime;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
private LocalDateTime createdAt;
```

Ba giá trị tiêu biểu của enum `DateTimeFormat.ISO` là `DATE`, `TIME`, `DATE_TIME`; `NONE` là giá trị mặc định khi không yêu cầu ISO.

- `DATE`: ngày dạng `yyyy-MM-dd`, ví dụ `2026-11-05`.
- `TIME`: giờ dạng ISO, ví dụ `14:30:45` (chi tiết thành phần tùy kiểu đích và chuỗi).
- `DATE_TIME`: ngày và giờ ISO, ví dụ `2026-11-05T14:30:45`, với ký tự `T` phân tách.

Chọn kiểu Java tương ứng với ngữ nghĩa: `LocalDate` cho ngày không có giờ; `LocalDateTime` cho ngày–giờ **không mang múi giờ/offset**; `OffsetDateTime` hoặc `ZonedDateTime` khi dữ liệu thật sự chứa offset hoặc zone. Không giả định `LocalDateTime` tự biết người dùng đang ở múi giờ nào.

### 3.2. `pattern`: mẫu cụ thể do ứng dụng kiểm soát

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate birthday;

@DateTimeFormat(pattern = "dd/MM/yyyy HH:mm")
private LocalDateTime appointmentAt;
```

Với mẫu thứ hai, `05/11/2026 14:30` có nghĩa 14:30 ngày 5/11/2026. Mẫu dùng ký hiệu quen thuộc của Java date/time formatting; Spring lựa chọn formatter phù hợp với kiểu đích. Việc cố định một pattern giúp giao diện và backend thống nhất, nhưng client phải gửi **đúng** thứ tự ngày/tháng/năm và dấu phân cách.

Các ký hiệu quan trọng:

| Ký hiệu | Ý nghĩa | Cần tránh nhầm |
| --- | --- | --- |
| `dd` | Ngày trong tháng, hai chữ số | `DD` là ngày trong năm |
| `MM` | Tháng, hai chữ số | `mm` là phút |
| `yyyy` | Năm dương lịch | `YYYY` là năm theo tuần, có thể lệch gần giao thừa |
| `HH` | Giờ 00–23 | `hh` là giờ 01–12, thường cần `a` (AM/PM) |
| `mm` | Phút | `MM` là tháng |
| `ss` | Giây | Chỉ thêm nếu đầu vào có giây |

Ví dụ đúng: `dd/MM/yyyy HH:mm`. Ví dụ dễ sai: `dd/mm/YYYY HH:MM` vì đổi nhầm tháng/phút và năm theo tuần. Không áp dụng pattern ngày–giờ cho một kiểu `LocalDate` chỉ lưu ngày.

### 3.3. `style`: định dạng theo locale

`style` là chuỗi **hai ký tự**. Ký tự thứ nhất điều khiển ngày, ký tự thứ hai điều khiển giờ:

- `S` = short (ngắn), `M` = medium (vừa), `L` = long (dài), `F` = full (đầy đủ).
- `-` = bỏ thành phần đó: `"M-"` chỉ có ngày dạng medium, `"-S"` chỉ có giờ dạng short, `"SS"` gồm cả ngày và giờ dạng short.

```java
@DateTimeFormat(style = "M-")
private LocalDate day;

@DateTimeFormat(style = "-S")
private LocalTime time;
```

Với `style`, **không có một chuỗi đầu vào cố định cho mọi máy và mọi người dùng**. Kết quả chịu ảnh hưởng locale (ví dụ `en_US` khác `vi_VN`) và dữ liệu/phiên bản JDK. Spring cảnh báo định dạng locale có thể thay đổi giữa các JDK, đặc biệt từ JDK 20. Nếu hợp đồng API cần ổn định, ưu tiên `iso` hoặc `pattern` cụ thể; chỉ chọn `style` khi chủ đích là giao tiếp theo locale.

## 4. Ví dụ Spring MVC có thể chạy

Ví dụ dưới đây dành cho dự án **Spring Boot với `spring-boot-starter-web` và Java 17+**. Đặt toàn bộ mã vào `src/main/java/com/example/dates/DateTimeFormatDemoApplication.java`; đây là một file Java hoàn chỉnh của ứng dụng Spring Boot (chạy bằng `./gradlew bootRun` hoặc lệnh chạy Spring Boot tương ứng với dự án).

```java
package com.example.dates;

import java.time.LocalDate;
import java.time.LocalDateTime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DateTimeFormatDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DateTimeFormatDemoApplication.class, args);
    }

    @RestController
    @RequestMapping("/dates")
    public static class DateController {

        @GetMapping("/iso")
        public String iso(
                @RequestParam("date")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
            return date.toString();
        }

        @GetMapping("/custom")
        public String custom(
                @RequestParam("date")
                @DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate date) {
            return date.toString();
        }

        @GetMapping("/time")
        public String time(
                @RequestParam("at")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                LocalDateTime at) {
            return at.toString();
        }

        @GetMapping("/style")
        public String style(
                @RequestParam("date")
                @DateTimeFormat(style = "M-") LocalDate date) {
            return date.toString();
        }

        @PostMapping("/form")
        public String form(
                @ModelAttribute ScheduleForm form, BindingResult result) {
            if (result.hasErrors()) {
                return "invalid-date";
            }
            return form.getStartDate().toString();
        }
    }

    public static class ScheduleForm {

        @DateTimeFormat(pattern = "dd/MM/yyyy")
        private LocalDate startDate;

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }
    }
}
```

Dùng các request sau sau khi server chạy ở cổng `8080`:

```bash
curl -G --data-urlencode "date=2026-11-05" http://localhost:8080/dates/iso
curl -G --data-urlencode "date=05/11/2026" http://localhost:8080/dates/custom
curl -G --data-urlencode "at=2026-11-05T14:30:45" http://localhost:8080/dates/time
curl -X POST --data-urlencode "startDate=05/11/2026" http://localhost:8080/dates/form
```

Khi chạy với cấu hình Spring MVC tiêu chuẩn, phần body của bốn response trên lần lượt là:

```text
2026-11-05
2026-11-05
2026-11-05T14:30:45
2026-11-05
```

**Giải thích:** `@DateTimeFormat` quyết định cách **đọc** chuỗi đầu vào. Trong ví dụ, `return date.toString()` là phương thức Java của `LocalDate`, nên body hiển thị chuẩn ISO ngay cả khi input theo `dd/MM/yyyy`. Đừng nhầm kết quả đó với việc `@DateTimeFormat` tự quyết định JSON hay mọi chuỗi response. Phương thức `/style` có thể được gọi sau khi xác định giá trị ngày theo locale đang dùng; vì không cố định được chuỗi đầu vào giữa các môi trường, ví dụ không khẳng định một literal áp dụng cho mọi locale.

Ở `/form`, Spring bind thuộc tính `startDate` của `ScheduleForm` bằng annotation trên field. `BindingResult` đặt **ngay sau** `@ModelAttribute` để nhận lỗi binding (ví dụ sai pattern) thay vì xử lý như một đối số độc lập.

## 5. Phân biệt lỗi parse với lỗi kiểm tra dữ liệu

Giả sử controller nhận `@RequestParam("date") @DateTimeFormat(iso = ISO.DATE) LocalDate date`:

| Đầu vào | Điều gì xảy ra |
| --- | --- |
| `2026-11-05` | Parse thành `LocalDate.of(2026, 11, 5)` |
| `05/11/2026` | Sai định dạng ISO DATE: lỗi conversion |
| `2026-02-30` | Ngày không tồn tại: lỗi parse |
| Bỏ tham số `date` | Mặc định `@RequestParam` yêu cầu có tham số: lỗi thiếu tham số |

Trong ứng dụng Spring MVC thông thường, lỗi chuyển đổi hoặc thiếu `@RequestParam` bắt buộc dẫn tới phản hồi HTTP 400 (trừ khi ứng dụng có cấu hình xử lý lỗi riêng). Với đối tượng `@ModelAttribute`, lỗi chuyển đổi field có thể được xem qua `BindingResult`. Muốn kiểm tra ngày tương lai hoặc bắt buộc khác với cú pháp, dùng Bean Validation phù hợp và kích hoạt validation theo yêu cầu của ứng dụng.

Nếu người dùng phải nhập nhiều định dạng cũ, có thể cho phép **fallback khi parse**:

```java
@DateTimeFormat(
    iso = DateTimeFormat.ISO.DATE,
    fallbackPatterns = {"dd/MM/yyyy", "M/d/yyyy"}
)
private LocalDate dueDate;
```

`fallbackPatterns` (Spring Framework 5.3.5+) thử các pattern dự phòng khi định dạng chính không parse được; thao tác **print vẫn dùng định dạng chính** (`ISO.DATE` ở đây). Không lạm dụng fallback nếu các định dạng có thể mơ hồ, chẳng hạn `03/04/2026` có thể hiểu là 3/4 hoặc 4/3 tùy quy ước.

## 6. Locale, múi giờ và kiểu dữ liệu

Ba khái niệm này khác nhau:

- **Locale** quyết định quy ước văn bản và ngôn ngữ của format theo `style`; ví dụ tên tháng và thứ tự thành phần có thể khác nhau.
- **Time zone / offset** quyết định cách một thời điểm tuyệt đối được biểu diễn theo giờ địa phương. `LocalDateTime` không lưu offset; `OffsetDateTime` có offset; `Instant` biểu diễn một thời điểm UTC trên timeline.
- **Pattern** quyết định hình dạng chuỗi. Một pattern giống nhau không tự bổ sung múi giờ cho kiểu không mang múi giờ.

Riêng với kiểu **`java.util.Date`** trong `@DateTimeFormat`, tài liệu Spring ghi rõ `iso` dùng **UTC**, còn `pattern` và `style` dùng múi giờ mặc định của JVM khi định dạng. Vì vậy một `Date` chứa cùng thời điểm có thể hiển thị ngày/giờ khác nhau giữa server khác timezone. Để thống nhất, cấu hình timezone rõ ràng, ví dụ `-Duser.timezone=UTC` nếu phù hợp với toàn ứng dụng; đừng suy diễn quy tắc `Date` này thành hành vi của mọi kiểu `java.time`.

Khi dữ liệu có offset như `2026-11-05T14:30:45+07:00`, hãy cân nhắc kiểu `OffsetDateTime` và formatter ISO phù hợp. Khi chỉ cần ngày sinh, ngày đặt lịch hoặc ngày hạn, `LocalDate` thường rõ nghĩa hơn một `Date` kèm thời điểm và timezone không cần thiết.

## 7. `@DateTimeFormat` khác gì `@JsonFormat`?

`@DateTimeFormat` tham gia vào **Spring formatting/binding** cho giá trị chuỗi trong query/path/form/model. Với `@RequestBody` có JSON, request body thường do **Jackson `HttpMessageConverter`** deserialize, không đi qua cùng luồng binding của tham số form. Vì vậy đặt `@DateTimeFormat` lên field không mặc nhiên khiến Jackson chấp nhận JSON dạng `"05/11/2026"` hay xuất JSON với pattern đó.

Ví dụ yêu cầu JSON có định dạng riêng thường dùng annotation/configuration của Jackson như:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

public class CreateEventJson {
    @JsonFormat(pattern = "dd/MM/yyyy")
    public LocalDate startDate;
}
```

Đoạn này chỉ minh họa **cấu hình JSON của Jackson**, không phải ứng dụng độc lập; cần Jackson hỗ trợ kiểu `java.time` (được cấu hình thông thường trong dự án Spring Boot dùng Jackson). Nếu có thể thiết kế API từ đầu, hãy chọn ISO date/time thống nhất cho JSON và query thay vì tạo nhiều mẫu ngày mơ hồ.

## 8. Kiểm tra pattern bằng Java thuần

Đây là ví dụ Java 17+ **độc lập với Spring** để kiểm tra chính xác cách `dd/MM/yyyy` biểu diễn ngày. Đặt vào file `PatternCheck.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class PatternCheck {
    public static void main(String[] args) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/yyyy");
        LocalDate day = LocalDate.parse("05/11/2026", formatter);
        System.out.println(day);
        System.out.println(day.format(formatter));
    }
}
```

```bash
javac PatternCheck.java
java PatternCheck
```

Stdout:

```text
2026-11-05
05/11/2026
```

Ví dụ này xác minh định dạng ngày bằng Java; phần tích hợp `@DateTimeFormat` phải chạy trong Spring `ConversionService`/MVC như mục 4.

## 9. Lỗi thường gặp và hướng xử lý

1. **Dùng `MM` thay `mm` hoặc `yyyy` thay `YYYY` không đúng mục đích.** Kiểm tra từng ký hiệu và thử ngày gần giao thừa.
2. **Dùng `style` cho hợp đồng API cố định.** Locale/JDK có thể làm thay đổi format; dùng `iso` hoặc `pattern` xác định.
3. **Đưa `dd/MM/yyyy` vào endpoint yêu cầu `ISO.DATE`.** Hai định dạng khác nhau; thống nhất với client hoặc có fallback nếu hợp đồng cho phép.
4. **Nhầm `LocalDateTime` với thời điểm có múi giờ.** Nếu cần offset/zone, chọn kiểu phù hợp và thống nhất timezone khi lưu trữ.
5. **Cho rằng annotation tự thực hiện validation nghiệp vụ.** `@DateTimeFormat` chỉ xử lý cách biểu diễn/parse; áp dụng validation riêng.
6. **Mong annotation trên DTO tự đổi JSON `@RequestBody`.** Hãy kiểm tra cơ chế Jackson và `@JsonFormat`.
7. **Bỏ qua lỗi binding.** Với form DTO, đặt `BindingResult` ngay sau `@ModelAttribute` và phản hồi lỗi cụ thể cho người nhập.
8. **Dùng `fallbackPatterns` cho các format mơ hồ.** Chỉ chấp nhận nhiều format khi có thứ tự ưu tiên và quy ước dữ liệu nhất quán.

## 10. Tự luyện tập

**Bài 1.** Endpoint nhận `?birthday=20/09/2000` vào `LocalDate`. Viết annotation phù hợp.

```java
@RequestParam("birthday")
@DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate birthday
```

**Bài 2.** Endpoint nhận `?due=2026-12-31` vào `LocalDate` theo chuẩn ổn định. Chọn `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`.

**Bài 3.** Vì sao không nên viết `@DateTimeFormat(pattern = "dd/mm/YYYY")` nếu người dùng nhập ngày/tháng/năm? Vì `mm` là phút và `YYYY` là năm theo tuần; cần `dd/MM/yyyy`.

**Bài 4.** Một form dùng `style = "M-"` hoạt động ở máy A nhưng lỗi ở máy B với chuỗi ngày cũ. Xem locale, phiên bản JDK và pattern thực tế; nếu cần dữ liệu ổn định, đổi sang ISO/pattern rõ ràng, hoặc thêm fallback chỉ khi quy ước nhập cho phép.

## 11. Ghi nhớ khi áp dụng

- **ISO** cho giao tiếp cần tính nhất quán; **pattern** cho biểu mẫu có cú pháp đã thống nhất; **style** cho giao diện phụ thuộc locale.
- Một annotation chỉ nên chọn **một** trong ba cách. Nếu xung đột: `pattern > iso > style`.
- Dùng đúng kiểu dữ liệu, phân biệt ngày đơn thuần, ngày–giờ không offset và thời điểm có offset.
- Test cả input hợp lệ, sai format, ngày không tồn tại, locale khác và lỗi binding.
- `fallbackPatterns` chỉ bổ sung cách **parse**, không thay định dạng **print**.

### Tài liệu tham khảo

- Spring Framework — `@DateTimeFormat` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring MVC — `@ModelAttribute` và data binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
