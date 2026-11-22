# Chuyển đổi kiểu dữ liệu và định dạng ngày giờ

Trong Spring Boot, client gửi dữ liệu qua path, query string, header, form hoặc JSON body. Spring MVC phải chuyển representation HTTP thành kiểu Java như `long`, `boolean`, `BigDecimal`, `LocalDate`, `OffsetDateTime` hoặc một value object do ứng dụng tự định nghĩa. Khi xử lý ngày giờ, tính đúng đắn phụ thuộc không chỉ vào pattern mà còn vào **kiểu thời gian, ISO 8601, locale, UTC offset và timezone**.

Bài này thuộc nhóm **Dữ liệu yêu cầu**, sử dụng **Spring Boot 3.3.x, Spring MVC trên Servlet stack, Java 17+**. Trọng tâm là cách Spring binding request parameter, cách dùng `@DateTimeFormat`, cách cấu hình formatter/converter và sự khác biệt với Jackson khi đọc JSON.

## 1. Conversion, formatting và JSON deserialization

Một request:

~~~http
GET /api/events/42?day=2026-11-07&active=true HTTP/1.1
Host: localhost:8080
~~~

có các giá trị path/query dưới dạng text. Controller có thể khai báo:

~~~java
@GetMapping("/api/events/{id}")
EventView find(
    @PathVariable long id,
    @RequestParam("day")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate day,
    @RequestParam boolean active) {
    // ...
}
~~~

Spring MVC chọn handler, tìm argument resolver và dùng `ConversionService`/formatter để biến `"42"` thành `long`, `"2026-11-07"` thành `LocalDate`, `"true"` thành `boolean`.

Với request:

~~~http
POST /api/events HTTP/1.1
Content-Type: application/json

{"day":"2026-11-07","active":true}
~~~

JSON body được `HttpMessageConverter` (thường là Jackson JSON converter) chuyển thành DTO. **Đường binding query/path/form không giống đường JSON `@RequestBody`.**

| Cơ chế | Thường dùng cho | Công cụ chính |
|---|---|---|
| Type conversion | Chuỗi request -> Java type | `ConversionService`, `Converter` |
| Field formatting | Chuỗi có định dạng/locale -> date, number | `Formatter`, `@DateTimeFormat`, `@NumberFormat` |
| HTTP message conversion | Body JSON/XML/text -> object | `HttpMessageConverter` và Jackson/codec |

Sơ đồ khái niệm:

~~~text
HTTP request
    |
DispatcherServlet -> HandlerMapping -> HandlerAdapter
    |
    +-- Query/path/form/header -> ArgumentResolver
    |                             -> WebDataBinder
    |                             -> ConversionService / Formatter
    |
    +-- JSON @RequestBody -----> HttpMessageConverter / Jackson
    |
Java arguments / DTO
    |
Controller -> service
~~~

Nếu converter/formatter không parse được input, lỗi có thể được xử lý **trước khi method controller được gọi**. Với các lỗi argument binding thông thường, Spring MVC trả **400 Bad Request**.

## 2. Chuyển kiểu số, boolean và enum

Spring cung cấp nhiều converter thông dụng. Ví dụ:

~~~java
@GetMapping("/api/search")
String search(
        @RequestParam int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(defaultValue = "false") boolean archived) {
    return "page=" + page
        + ",size=" + size
        + ",archived=" + archived;
}
~~~

Request `GET /api/search?page=2&size=10&archived=true` cho body:

~~~text
page=2,size=10,archived=true
~~~

Nếu gửi `page=abc` thì không chuyển được sang `int`; `defaultValue` cho `size` không có nghĩa mọi input sai đều được thay bằng mặc định. Với `enum`, việc parse thường dựa vào tên hằng enum; nếu API phải nhận alias hoặc chữ thường, cần converter riêng và test.

Với số tiền, nên cân nhắc `BigDecimal` để tránh sai số biểu diễn nhị phân. Nhưng vẫn cần quy định cú pháp text; dấu phân cách thập phân `,` và `.` có thể mang ý nghĩa khác nhau theo locale.

## 3. Các kiểu thời gian trong java.time

| Kiểu Java | Thông tin chứa | Ví dụ |
|---|---|---|
| `LocalDate` | Ngày lịch không có giờ/zone | `2026-11-07` |
| `LocalTime` | Giờ trong ngày không có ngày/zone | `09:30:00` |
| `LocalDateTime` | Ngày + giờ, **không mang offset** | `2026-11-07T09:30:00` |
| `OffsetDateTime` | Ngày + giờ + UTC offset | `2026-11-07T09:30:00+07:00` |
| `ZonedDateTime` | Ngày + giờ + zone/region | `2026-11-07T09:30+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Thời điểm tuyệt đối trên UTC timeline | `2026-11-07T02:30:00Z` |
| `Duration` | Độ dài theo giây/nano | `PT15M` |
| `Period` | Khoảng theo năm/tháng/ngày lịch | `P1M` |

Chọn đúng kiểu là một phần của hợp đồng API. `LocalDateTime` không thể tự xác định một instant vì thiếu timezone. `OffsetDateTime` giữ offset; `ZonedDateTime` giữ region zone và có thể cần xử lý quy tắc daylight saving time. `LocalDate` là ngày lịch, không tự đồng nghĩa mốc 00:00 UTC.

Dùng `LocalDate` cho ngày sinh/ngày đặt lịch; `Instant` cho audit timestamp; `OffsetDateTime` nếu client gửi mốc thời gian có offset; `ZonedDateTime` nếu nghiệp vụ phụ thuộc lịch vùng.

## 4. @DateTimeFormat(iso = ...) dành cho text request parameter

`@DateTimeFormat` thuộc `org.springframework.format.annotation`. Cách khai báo rõ cho API:

~~~java
@GetMapping("/api/reports")
String report(
        @RequestParam("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day) {
    return day.toString();
}
~~~

Với `GET /api/reports?day=2026-11-07`, kết quả:

~~~text
2026-11-07
~~~

Các lựa chọn thường gặp:
- `ISO.DATE`: ngày ISO.
- `ISO.TIME`: giờ ISO.
- `ISO.DATE_TIME`: ngày giờ ISO.
- `ISO.NONE`: không áp dụng ISO tường minh.

Khi cần thời điểm có offset, ghép `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)` với `OffsetDateTime`. Việc áp dụng ISO tại tham số giúp API ổn định hơn so với phụ thuộc format localized theo môi trường.

## 5. @DateTimeFormat(pattern = ...) cho định dạng riêng

Client cũ có thể dùng `07/11/2026` thay cho `2026-11-07`:

~~~java
@GetMapping("/api/reports/local")
String localReport(
        @RequestParam("day")
        @DateTimeFormat(pattern = "dd/MM/uuuu")
        LocalDate day) {
    return day.toString();
}
~~~

Request `GET /api/reports/local?day=07%2F11%2F2026` trả:

~~~text
2026-11-07
~~~

Những ký tự dễ nhầm: `MM` là tháng, `mm` là phút; `HH` là giờ 0–23, `hh` là giờ 1–12; `dd` là ngày trong tháng; `uuuu` là proleptic year và thường thích hợp cho strict parsing với `java.time`. Một pattern không chứa offset/zone không tạo timezone từ input.

Nên ưu tiên ISO 8601 cho API máy-máy. Pattern riêng chỉ phù hợp khi contract thực sự yêu cầu hoặc ứng dụng phục vụ form theo định dạng được hiển thị rõ với người dùng.

## 6. Cấu hình Spring Boot: spring.mvc.format.*

Spring Boot 3.3 hỗ trợ:

~~~yaml
spring:
  mvc:
    format:
      date: "dd/MM/uuuu"
      time: "HH:mm:ss"
      date-time: "dd/MM/uuuu HH:mm:ss"
~~~

| Property | Các kiểu được tài liệu Boot 3.3 mô tả |
|---|---|
| `spring.mvc.format.date` | `java.util.Date`, `LocalDate` |
| `spring.mvc.format.time` | `LocalTime`, `OffsetTime` |
| `spring.mvc.format.date-time` | `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` |

Khi không khai báo, Boot 3.3 cho biết các formatter mặc định sử dụng `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)`, `ofLocalizedTime(SHORT)`, `ofLocalizedDateTime(SHORT)` tương ứng. Các localized format phụ thuộc locale, vì vậy không nên để public API phải đoán format mặc định.

Đặt `date-time: "dd/MM/uuuu HH:mm:ss"` làm toàn cục có thể ảnh hưởng endpoint nhận `OffsetDateTime` vì pattern không mô tả offset. Nếu nhiều API có các hợp đồng khác nhau, hãy dùng `@DateTimeFormat` tại từng parameter/field thay vì thay đổi toàn bộ formatter mặc định.

Với WebFlux, property là `spring.webflux.format.date`, `spring.webflux.format.time` và `spring.webflux.format.date-time`, không phải namespace `spring.mvc.*`.

## 7. MVC ConversionService khác configuration properties binding

Spring Boot có thể bind:

~~~yaml
app:
  client:
    timeout: 15s
    cache-size: 16MB
~~~

thành `Duration` và `DataSize` khi dùng `@ConfigurationProperties`. Nhưng Spring MVC có **ConversionService khác** hệ thống bind application config: các converter đặc thù `Period`/`Duration`/`DataSize` dùng cho property binding không mặc nhiên có cùng semantics trong MVC.

Đừng suy luận `@RequestParam Duration timeout` tự hiểu `15s` chỉ vì `application.yml` hiểu nó. Các annotation `@DurationUnit` và `@DataSizeUnit` cũng không phải lời giải tổng quát cho HTTP parameter binding. Nếu API cần duration, quy định cú pháp (milliseconds hoặc ISO duration), đăng ký converter cần thiết và test.

## 8. Converter cho kiểu dữ liệu miền nghiệp vụ

Giả sử mã sự kiện `EV-42` cần kiểu mạnh:

~~~java
record EventCode(String value) {}
~~~

Tạo converter qua `WebMvcConfigurer.addFormatters`:

~~~java
@Configuration(proxyBeanMethods = false)
class MvcConversionConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, EventCode.class,
            text -> {
                if (!text.matches("EV-[0-9]+")) {
                    throw new IllegalArgumentException("Invalid event code");
                }
                return new EventCode(text);
            });
    }
}
~~~

Đây là snippet có import ở ví dụ hoàn chỉnh bên dưới. Với `@PathVariable EventCode code`, MVC gọi converter trước khi controller chạy. Input `EV-42` trở thành value object; `wrong` thất bại conversion, thường dẫn đến HTTP 400.

Một converter nên xử lý biểu diễn/cú pháp, không truy vấn database hoặc gọi HTTP service để kiểm tra mã có tồn tại. Việc kiểm tra resource và phân quyền thuộc service/domain.

`Formatter<T>` phù hợp khi parse và print theo `Locale`:
- `parse(String, Locale)`: text thành object.
- `print(T, Locale)`: object thành text.

Ví dụ `1,234.50` và `1.234,50` có thể biểu diễn cùng một số ở locale khác nhau. `@NumberFormat` là một công cụ cho field cần format số theo quy tắc được chỉ định. Với API công khai, công bố cú pháp rõ thay vì dùng locale máy chủ một cách ngầm định.

## 9. Locale khác TimeZone

Trong MVC, `LocaleResolver` và header `Accept-Language` có thể ảnh hưởng formatter localized. Nhưng `Locale` là quy ước ngôn ngữ/văn hóa, **không tự xác định timezone**. Header `Accept-Language: vi-VN` không có nghĩa client đã gửi `Asia/Ho_Chi_Minh` hoặc một UTC offset cụ thể.

Nếu nghiệp vụ yêu cầu timezone, sử dụng `ZoneId` và offset/zone trong dữ liệu đầu vào theo hợp đồng. Không tạo timestamp từ `LocalDateTime` bằng timezone JVM mà không giải thích cho client.

## 10. Dấu + trong offset và URL-encoding

Hai chuỗi sau mô tả cùng một instant:

~~~text
2026-11-07T09:30:00+07:00
2026-11-07T02:30:00Z
~~~

Trong query parameter, dấu `+` có thể bị decode thành dấu cách theo quy tắc form-style. Client không nên tự nối raw `?at=2026-11-07T09:30:00+07:00` rồi kỳ vọng mọi server parse đúng.

Hãy URL-encode:

~~~bash
curl -G "http://localhost:8080/api/events/42" \
  --data-urlencode "day=2026-11-07" \
  --data-urlencode "at=2026-11-07T09:30:00+07:00"
~~~

Ví dụ kết quả URI chứa `%2B`:

~~~text
/api/events/42?day=2026-11-07&at=2026-11-07T09%3A30%3A00%2B07%3A00
~~~

Trong JSON body, dấu `+` bên trong chuỗi JSON không cần URL-encode. Với MockMvc `.param("at", "2026-11-07T09:30:00+07:00")`, tham số được truyền trực tiếp.

Ví dụ Java 17 thuần:

~~~java
import java.time.OffsetDateTime;

public class TimeDemo {
    public static void main(String[] args) {
        OffsetDateTime time =
            OffsetDateTime.parse("2026-11-07T09:30:00+07:00");
        System.out.println(time.toInstant());
    }
}
~~~

Chạy `javac TimeDemo.java` rồi `java TimeDemo`, stdout chính xác:

~~~text
2026-11-07T02:30:00Z
~~~

## 11. JSON @RequestBody dùng Jackson, không phải @DateTimeFormat

Body:

~~~json
{"day":"2026-11-07","at":"2026-11-07T09:30:00+07:00"}
~~~

DTO:

~~~java
record CreateEventRequest(LocalDate day, OffsetDateTime at) {}
~~~

Spring MVC dùng `HttpMessageConverter`, thường Jackson với Java Time module đi kèm `spring-boot-starter-web`, để đọc JSON thành Java record.

Khi cần format riêng cho **JSON field**, dùng Jackson `@JsonFormat` hoặc ObjectMapper configuration:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

record SpecialBody(
    @JsonFormat(pattern = "dd/MM/uuuu") LocalDate day
) {}
~~~

`@JsonFormat` không sửa `@RequestParam LocalDate`; `@DateTimeFormat` của query không phải cấu hình chính cho JSON body. Property `spring.jackson.date-format` liên quan Jackson nhưng không đảm bảo tất cả `java.time` serializer/deserializer đổi theo cùng pattern: phải test ObjectMapper đang dùng.

Input JSON sai cú pháp hoặc date sai có thể bị Jackson từ chối và Spring MVC thường trả 400. Nếu `Content-Type` không được handler/converter hỗ trợ, status có thể là 415.

## 12. Ví dụ Spring Boot đầy đủ

Project Java 17+ / Spring Boot 3.3.x cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là đoạn dependencies, không phải toàn bộ file Gradle. Đặt mã sau tại `src/main/java/com/example/demo/RequestFormatApplication.java`:

~~~java
package com.example.demo;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class RequestFormatApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestFormatApplication.class, args);
    }
}

record EventCode(String value) {}
record EventView(long id, String day, String instant) {}
record CreateEventRequest(LocalDate day, OffsetDateTime at) {}

@RestController
@RequestMapping("/api/events")
class EventController {

    @GetMapping("/{id}")
    EventView find(
            @PathVariable long id,
            @RequestParam("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day,
            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return new EventView(
            id, day.toString(), at.toInstant().toString());
    }

    @GetMapping("/local")
    Map<String, String> local(
            @RequestParam("day")
            @DateTimeFormat(pattern = "dd/MM/uuuu")
            LocalDate day) {
        return Map.of("isoDay", day.toString());
    }

    @GetMapping("/by-code/{code}")
    Map<String, String> byCode(@PathVariable EventCode code) {
        return Map.of("code", code.value());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EventView create(@RequestBody CreateEventRequest body) {
        return new EventView(
            43L, body.day().toString(),
            body.at().toInstant().toString());
    }
}

@Configuration(proxyBeanMethods = false)
class MvcConversionConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, EventCode.class,
            text -> {
                if (!text.matches("EV-[0-9]+")) {
                    throw new IllegalArgumentException(
                        "Invalid event code");
                }
                return new EventCode(text);
            });
    }
}
~~~

Ví dụ đúng ranh giới:
1. `@PathVariable long id` chuyển path text thành `long`.
2. `@DateTimeFormat(ISO.DATE)` parse query ngày ISO.
3. `@DateTimeFormat(ISO.DATE_TIME)` parse query datetime có offset.
4. `pattern = "dd/MM/uuuu"` xử lý một route legacy riêng.
5. Custom Converter chuyển mã String thành `EventCode`.
6. `@RequestBody` qua Jackson đọc JSON, không dùng query formatter.
7. `EventView` hiển thị UTC instant thành String để output demo ổn định. POST trả ID giả lập 43 và HTTP 200 thông thường; API tạo resource thực cần chọn 201/Location khi phù hợp.

Chạy bằng Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

GET query ISO có offset:

~~~bash
curl -G "http://localhost:8080/api/events/42" \
  --data-urlencode "day=2026-11-07" \
  --data-urlencode "at=2026-11-07T09:30:00+07:00"
~~~

Body:

~~~json
{"id":42,"day":"2026-11-07","instant":"2026-11-07T02:30:00Z"}
~~~

GET legacy pattern:

~~~bash
curl -G "http://localhost:8080/api/events/local" \
  --data-urlencode "day=07/11/2026"
~~~

Body:

~~~json
{"isoDay":"2026-11-07"}
~~~

GET custom code:

~~~bash
curl http://localhost:8080/api/events/by-code/EV-42
~~~

Body:

~~~json
{"code":"EV-42"}
~~~

POST JSON:

~~~bash
curl -X POST "http://localhost:8080/api/events" \
  -H "Content-Type: application/json" \
  -d '{"day":"2026-11-07","at":"2026-11-07T09:30:00+07:00"}'
~~~

Body:

~~~json
{"id":43,"day":"2026-11-07","instant":"2026-11-07T02:30:00Z"}
~~~

Dấu `\` xuống dòng theo Bash; trên Windows PowerShell dùng `curl.exe` và cú pháp quote phù hợp.

## 13. MockMvc test để chứng minh thời điểm binding

Tạo `src/test/java/com/example/demo/RequestFormatApplicationTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestFormatApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void isoDateAndOffset() throws Exception {
        mvc.perform(get("/api/events/{id}", 42)
                .param("day", "2026-11-07")
                .param("at", "2026-11-07T09:30:00+07:00"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.instant")
                .value("2026-11-07T02:30:00Z"));
    }

    @Test
    void customDatePattern() throws Exception {
        mvc.perform(get("/api/events/local")
                .param("day", "07/11/2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.isoDay").value("2026-11-07"));
    }

    @Test
    void customConverter() throws Exception {
        mvc.perform(get("/api/events/by-code/EV-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("EV-42"));
    }

    @Test
    void invalidDateIs400() throws Exception {
        mvc.perform(get("/api/events/{id}", 42)
                .param("day", "2026-02-30")
                .param("at", "2026-11-07T09:30:00+07:00"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jacksonForJsonBody() throws Exception {
        mvc.perform(post("/api/events")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"day\":\"2026-11-07\","
                    + "\"at\":\"2026-11-07T09:30:00+07:00\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.instant")
                .value("2026-11-07T02:30:00Z"));
    }
}
~~~

Trong project đã cấu hình JUnit Platform, chạy:

~~~bash
./gradlew test
~~~

Test này đi qua argument resolver, formatter, converter và Jackson của Spring MVC, không chỉ test Java parser riêng lẻ. Ngoài ví dụ, nên test ngày không tồn tại, query thiếu tham số, JSON format sai, UTC offset và locale đặc thù.

## 14. @ModelAttribute và @InitBinder

Với form/query nhiều field, `@ModelAttribute` có thể bind vào form object:

~~~java
public class SearchForm {
    private String keyword;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate to;

    // Getter/setter để Spring bind bean properties.
}
~~~

Đây là snippet minh họa, cần bổ sung accessors/import để chạy độc lập.

Với controller cần giới hạn field được bind:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("keyword", "from", "to");
}
~~~

`@InitBinder` có phạm vi controller/advice tương ứng. Đừng bind trực tiếp JPA entity chứa field nhạy cảm từ client. DTO và allowed fields hỗ trợ tránh over-posting nhưng không thay authorization hoặc business validation.

**Binding khác validation:** format text thành `LocalDate` là conversion; `@Valid`/`@NotBlank` thuộc Bean Validation khi implementation có mặt; quy tắc “không được đặt lịch quá ngày cho phép” thuộc service/domain. Một ngày hợp lệ về cú pháp vẫn có thể sai về nghiệp vụ.

## 15. Lỗi thường gặp

| Hiện tượng | Hướng điều tra |
|---|---|
| `day=2026-02-30` bị 400 | Date parser/formatter từ chối ngày không hợp lệ |
| Query có offset `+07:00` parse sai | Encode `+` thành `%2B` |
| JSON date hoạt động nhưng query date lỗi | Jackson khác MVC formatter |
| Query enum chữ thường lỗi | Quy tắc chuyển String -> enum; cân nhắc Converter |
| `@RequestParam Duration` không hiểu `15s` | MVC ConversionService khác property binder |
| Đổi global date-time làm hỏng API khác | Pattern áp dụng rộng và có thể thiếu offset |
| Request body không đúng Content-Type | Có thể 415 Unsupported Media Type |
| Accept không tương thích output | Có thể 406 Not Acceptable |
| Lỗi text nhưng controller không log | Argument resolution thất bại trước khi gọi handler |

Một lỗi conversion thường được Spring biểu diễn bằng `MethodArgumentTypeMismatchException`, `TypeMismatchException` hoặc binding exception phù hợp; JSON body có thể gặp `HttpMessageNotReadableException`. Nên trả HTTP 400 cho input không parse được, tránh trả 200 hoặc lộ stack trace. Khi cần định dạng lỗi thống nhất, cân nhắc `@RestControllerAdvice`/`ProblemDetail`.

## 16. Ghi nhớ và tài liệu tham khảo

- MVC query/path/form dùng ConversionService, Formatter và `@DateTimeFormat`.
- JSON `@RequestBody` dùng `HttpMessageConverter` và Jackson; nếu cần pattern JSON riêng, dùng `@JsonFormat`.
- `spring.mvc.format.date`, `time`, `date-time` điều khiển formatter MVC; `spring.webflux.format.date` thuộc WebFlux.
- `LocalDate` là ngày lịch; `OffsetDateTime` có offset; `Instant` là thời điểm tuyệt đối.
- Query offset có `+` phải được encode.
- `WebMvcConfigurer.addFormatters` bổ sung converter/formatter mà không cần giành toàn quyền MVC bằng `@EnableWebMvc`.
- Test toàn tuyến HTTP qua MockMvc để xác định request thật được parse đúng.

Tài liệu chính thức:
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Java 17 — java.time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)

**Kết luận:** API nhận dữ liệu đúng khi phân biệt query/path/form binding với JSON deserialization, chọn đúng `java.time` type, công bố format ISO hoặc pattern cụ thể, không suy đoán offset/timezone và dùng HTTP test để xác minh cả dữ liệu hợp lệ lẫn dữ liệu sai.
