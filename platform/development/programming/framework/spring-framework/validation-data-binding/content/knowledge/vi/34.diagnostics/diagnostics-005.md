# Formatter không áp dụng do dữ liệu đi qua JSON converter

## 1. Triệu chứng: Formatter hoạt động với form/query nhưng không hoạt động với JSON

Bạn khai báo một `Formatter<LocalDate>`, đăng ký qua `WebMvcConfigurer#addFormatters` và thử thành công với request parameter:

```http
GET /api/events/query?title=Conference&eventDate=06.11.2026
Accept: application/json
```

Nhưng khi gửi giá trị tương tự trong JSON:

```http
POST /api/events/json
Content-Type: application/json

{"title":"Conference","eventDate":"06.11.2026"}
```

server trả **400 Bad Request**. Bạn đặt breakpoint trong `Formatter#parse` nhưng breakpoint **không chạy**. Vậy Spring có làm mất Formatter, hay bean chưa được đăng ký?

**Thường là không.** Hai request đi qua **hai cơ chế chuyển đổi dữ liệu khác nhau**:

1. `@RequestParam`, `@PathVariable` và `@ModelAttribute` nhận các giá trị kiểu chuỗi/field binding → Spring MVC `ConversionService`, `Formatter`, `Converter`, `WebDataBinder`.
2. `@RequestBody` có nội dung JSON → Spring MVC chọn `HttpMessageConverter` tương ứng (thường `MappingJackson2HttpMessageConverter` trong Spring Boot 3.3) → Jackson `ObjectMapper`/deserializers tạo Java object. Một `Formatter<T>` đã đăng ký trên MVC `FormatterRegistry` **không tự động trở thành Jackson deserializer**.

Ví dụ:

```text
                        HTTP request
                             |
                       DispatcherServlet
                             |
                    HandlerMethod argument
                         /         \
                        /           \
        @RequestParam / @ModelAttribute    @RequestBody EventInput
                   |                              |
      WebDataBinder + ConversionService          HttpMessageConverter
                   |                              |
      Formatter<LocalDate>.parse()               Jackson ObjectMapper
                   |                              |
             EventInput                     EventInput
                   \                              /
                    \                            /
                          @Valid (nếu có)
                                |
                         Controller method
                                |
                       @ResponseBody JSON
                                |
                     HttpMessageConverter
                     (Jackson serialization)
```

Vì vậy **cấu hình formatter hợp lệ không bảo đảm JSON dùng formatter đó**. Sửa lỗi bằng cách xác định **đúng đường đi của request** trước khi chỉnh code.

**Phạm vi:** Spring Framework 6.1.x, Spring Boot 3.3.6, Servlet Spring MVC, Java 17+, Jackson và Jakarta Validation. Phiên bản mới hơn có thể đổi tên/lựa chọn JSON converter; nguyên lý tách Spring field formatting khỏi JSON object mapping vẫn cần được xác minh với hệ thống thực.

## 2. Các thành phần khác nhau ở tầng nào?

| Thành phần | Vai trò | Áp dụng phổ biến |
| --- | --- | --- |
| `org.springframework.core.convert.ConversionService` | API chuyển đổi giữa các kiểu | `@RequestParam`, `@PathVariable`, `@ModelAttribute`, Spring binding |
| `org.springframework.core.convert.converter.Converter<S,T>` | Chuyển một kiểu sang kiểu khác, thường không phụ thuộc locale | Chuyển chuỗi thành value object trong Spring conversion |
| `org.springframework.format.Formatter<T>` | `parse(String,Locale)` và `print(T,Locale)` | Giá trị field giao diện, form/query, các biểu diễn có locale |
| `FormattingConversionService` | Kết hợp converters, formatters và annotation-based formatters | Binding chuỗi vào method parameters/model attributes |
| `@DateTimeFormat` | Chọn format cho date/time trong Spring conversion | Method parameter hoặc field/model attribute |
| `@NumberFormat` | Cấu hình số cho Spring formatting | Field/model attribute, request arguments phù hợp |
| `WebDataBinder` | Gắn request values vào model object, quản lý binding errors và validation | `@ModelAttribute`; ngoài ra dùng cho validation sau `@RequestBody` |
| `HttpMessageConverter` | Đọc/ghi **HTTP body** theo media type và target type | `@RequestBody`, `@ResponseBody` |
| `MappingJackson2HttpMessageConverter` | JSON body ↔ Java object bằng Jackson | JSON request/response trong Spring MVC 6.1 |
| `ObjectMapper` và Jackson deserializers | Giải mã JSON tokens, creator properties, date/time formats | Jackson JSON pathway |
| `@JsonFormat` | Jackson format metadata cho property/type | JSON serialization/deserialization |
| `@Valid` / `@Validated` | Chạy Bean Validation sau khi dữ liệu được tạo/bind | Có thể dùng ở cả form và JSON |

**Hai điểm dễ nhầm:**

- `@RequestBody` có thể được Spring tạo `WebDataBinder` để **chạy validation sau khi Jackson tạo object**, nhưng điều đó **không** có nghĩa Jackson sử dụng `WebDataBinder` để parse từng JSON field.
- `Content-Type: application/json` là yếu tố lựa chọn media type. Chỉ đổi header không làm `@ModelAttribute` trở thành `@RequestBody`. Chính **handler argument annotation**, target type và converter configuration quyết định đường xử lý.

### 2.1. Spring Formatter là gì?

Interface:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    String print(T object, Locale locale);
    T parse(String text, Locale locale) throws ParseException;
}
```

Đây là **chữ ký giải thích**, không phải đoạn code để đưa vào project như một file độc lập. Trong Spring, `Formatter<T>` dành cho biểu diễn **chuỗi field** ở client/UI; `Locale` là một phần API. Có thể đăng ký bằng:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DottedLocalDateFormatter());
}
```

Phần này tùy biến Spring MVC `FormattingConversionService`. Nó **không** gọi:

```java
objectMapper.registerModule(...);
```

và cũng không tự thêm một Jackson `JsonDeserializer<LocalDate>`. Đó là điểm phân tách thiết kế.

### 2.2. Jackson đọc JSON như thế nào?

Khi controller có:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public EventView create(@RequestBody EventInput input) {
    ...
}
```

Spring MVC chọn một converter có thể đọc `EventInput` từ JSON. Với cấu hình Spring Boot 3.3 tiêu chuẩn, Jackson đọc JSON object, ánh xạ properties vào record canonical constructor hoặc bean properties theo metadata của Jackson và dùng deserializer cho `LocalDate`.

`LocalDate` thường được Jackson Java Time module đọc theo chuỗi ISO `yyyy-MM-dd` nếu không cấu hình định dạng khác. Chữ `"06.11.2026"` do custom Spring Formatter chấp nhận **không phải** ISO local date theo Jackson default, nên JSON có thể bị từ chối.

**Không phải mọi `@RequestBody` đều dùng Jackson.** Nếu argument là `String` hoặc `byte[]`, một `HttpMessageConverter` khác có thể được chọn. Nếu cấu hình dùng Gson/JSON-B hoặc thay đổi converters, cách sửa phải tương ứng. Luôn dựa vào converter thực tế, không giả định Jackson chỉ từ dòng `Content-Type`.

## 3. Cách chẩn đoán có hệ thống

### 3.1. Bắt đầu từ handler signature

Kiểm tra endpoint đang dùng annotation nào:

```java
// Spring string/field conversion:
@GetMapping("/query")
public Object query(@RequestParam LocalDate eventDate) { ... }

// Spring model attribute binding:
@PostMapping("/form")
public Object form(@ModelAttribute EventInput input) { ... }

// HTTP body conversion (thường Jackson):
@PostMapping("/json")
public Object json(@RequestBody EventInput input) { ... }
```

Các ví dụ này là method snippets, không phải classes hoàn chỉnh.

Đây là bước hiệu quả nhất. Nếu có `@RequestBody`, tìm `ObjectMapper`/`HttpMessageConverter` trước, không tiếp tục thêm một `Formatter` khác rồi kỳ vọng JSON tự thay đổi.

### 3.2. Xem Content-Type và target type

Ví dụ:

- `application/x-www-form-urlencoded` + `@ModelAttribute`: các form fields được Servlet request parameter API cung cấp, rồi Spring binder chuyển String sang type.
- `application/json` + `@RequestBody EventInput`: Jackson JSON path.
- `application/json` + `@RequestBody String`: có thể được đọc bằng `StringHttpMessageConverter`, không nhất thiết Jackson parse object.
- `multipart/form-data`: cách xử lý còn phụ thuộc `@RequestPart`, `MultipartFile`, form field hay part JSON; một JSON part được đọc bằng message converter có thể không đi qua Formatter.
- `@RequestParam` không tự bóc các JSON object properties từ body; nếu client gửi JSON nhưng controller trông chờ query/form params, thường sẽ không thấy các giá trị như mong muốn.

### 3.3. Đặt breakpoint đúng vị trí

Với Spring MVC 6.1:

- `org.springframework.web.method.annotation.AbstractNamedValueMethodArgumentResolver` và các argument resolvers: `@RequestParam`, `@PathVariable`...
- `org.springframework.web.method.annotation.ModelAttributeMethodProcessor` hoặc Servlet subclass: `@ModelAttribute`, binder.
- `org.springframework.web.servlet.mvc.method.annotation.RequestResponseBodyMethodProcessor`: `@RequestBody`.
- `org.springframework.web.servlet.mvc.method.annotation.AbstractMessageConverterMethodArgumentResolver#readWithMessageConverters`: chọn và gọi body converter.
- `org.springframework.http.converter.json.MappingJackson2HttpMessageConverter`: đọc JSON qua Jackson.
- `org.springframework.format.Formatter#parse` của class do bạn viết: parse path của Spring formatting.
- Jackson `LocalDateDeserializer` hoặc custom deserializer: parse path của JSON.

Nếu breakpoint trong `Formatter#parse` hit khi gọi form/query nhưng **không** hit khi gọi JSON, và breakpoint Jackson path hit, đó là bằng chứng chẩn đoán rõ ràng về việc **đi qua hai pipeline khác nhau**.

### 3.4. Phân loại exception thay vì chỉ nhìn HTTP 400

| Tình huống | Exception / nơi chứa lỗi thường gặp |
| --- | --- |
| `@RequestParam LocalDate` sai format | `MethodArgumentTypeMismatchException` hoặc mismatch resolution |
| `@ModelAttribute` field không chuyển kiểu được | `BindingResult`/`FieldError` với `typeMismatch`; nếu không có result có thể ném `MethodArgumentNotValidException` |
| `@RequestBody` JSON không parse được vào `LocalDate` | `HttpMessageNotReadableException`, nested Jackson mapping/format error |
| JSON deserialize được nhưng `@NotNull`/`@NotBlank` không hợp lệ | `MethodArgumentNotValidException` khi `@Valid` chạy |
| Media type không được endpoint hỗ trợ | HTTP 415, thường `HttpMediaTypeNotSupportedException` |
| JSON body thiếu hẳn với `@RequestBody(required=true)` | Body unreadable/missing, thường 400 |

**Cảnh báo:** không gọi mọi lỗi “Bean Validation error”. Nếu Jackson chưa tạo được object từ JSON, `@Valid` chưa có object để kiểm tra; nếu JSON tạo thành công nhưng date null, `@NotNull` có thể phát hiện lỗi ở bước sau.

### 3.5. Log cấu hình có mục đích

Ở môi trường dev/test, có thể nâng logger liên quan đến handler/converters:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation=DEBUG
logging.level.org.springframework.http.converter=DEBUG
logging.level.org.springframework.web.method.annotation=DEBUG
```

Logger thực sự phát ra dòng gì phụ thuộc version, code path và log level. **Không** dựa vào một mẫu log cụ thể như hợp đồng bền vững; kết hợp với MockMvc/debugger. Không bật body/headers debug logging trên production nếu có dữ liệu cá nhân, authorization header hoặc secrets.

## 4. @DateTimeFormat khác @JsonFormat

### 4.1. @DateTimeFormat trong Spring field binding

```java
public record SearchInput(
        @DateTimeFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

Trên một `@ModelAttribute`/`@RequestParam` phù hợp, Spring annotation formatter dùng định dạng được khai báo cho giá trị chuỗi. Trong ví dụ, `06.11.2026` tương ứng ngày 6 tháng 11 năm 2026. `@DateTimeFormat` không đảm bảo Jackson JSON cũng đọc format này.

Có thể viết:

```java
@GetMapping("/search")
public EventView search(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate eventDate) {
    // ...
}
```

với format ISO `2026-11-06` cho argument đó. Spring MVC hỗ trợ annotation-driven formatting riêng cho field/method parameter; rule có thể ghi đè formatter theo type đã được đăng ký.

### 4.2. @JsonFormat cho Jackson property

```java
public record JsonInput(
        @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

Jackson có thể dùng pattern đó khi đọc/ghi JSON property `eventDate` nếu Java Time module và annotation introspection phù hợp. `@JsonFormat` là annotation **Jackson**, không tự cấu hình `FormattingConversionService` của Spring.

Một class/record có thể chứa **cả** `@DateTimeFormat` và `@JsonFormat` cho cùng một property nếu bạn phải hỗ trợ hai biểu diễn khác nhau. Khi đó phải hiểu rõ:

- Form/query path nhìn `@DateTimeFormat`.
- JSON path nhìn `@JsonFormat`.
- Khi một endpoint trả `@ResponseBody` JSON, Jackson writer quyết định biểu diễn đầu ra.
- Chỉ khi có integration custom rõ ràng, hai cơ chế mới dùng chung một bộ format rules.

Dự án thực hành bên dưới dùng **một global Spring Formatter** cho form/query, và một **record JSON có `@JsonFormat`** để đối chiếu.

### 4.3. spring.mvc.format.date và spring.jackson.*

`spring.mvc.format.date` hoặc `WebMvcConfigurer#addFormatters` điều khiển Spring MVC conversion/field formatting. Chúng không phải cấu hình mặc định cho Jackson `ObjectMapper`.

Ngược lại, Spring Boot hỗ trợ Jackson ObjectMapper customization. Với Java Time types, cần chú ý Jackson Java Time module, serializers/deserializers theo type/property; cấu hình `spring.jackson.date-format` toàn cục không nên được coi là bảo đảm cho **mọi `java.time.LocalDate`** mà không có test, vì Java Time deserializers có quy tắc riêng.

Một nguyên tắc thực dụng: nếu API JSON công bố ngày theo ISO 8601, giữ JSON ISO; nếu UI cần `dd.MM.uuuu`, dùng formatter ở form/query. Đừng bắt JSON tuân theo format hiển thị của một locale chỉ vì đã đăng ký Formatter cho UI.

## 5. Hướng giải quyết đúng theo mục tiêu

### 5.1. Giữ JSON ISO, Formatter chỉ cho form/query

**Khuyến nghị khi thiết kế API:** JSON dùng `"2026-11-06"`, form nhập `"06.11.2026"` nếu UX yêu cầu. Spring Formatter và Jackson tự xử lý ở hai đường tương ứng. Đây là cách demo mặc định.

Ưu điểm:

- JSON schema nhất quán với client đa ngôn ngữ.
- Ít phụ thuộc locale server.
- Frontend có thể đổi cách hiển thị ngày nhưng không cần đổi API contract.
- Client mobile/web sử dụng chuẩn ISO phổ biến.

### 5.2. Cho JSON dùng một pattern khác bằng @JsonFormat

Khi business contract thực sự muốn dotted string trong JSON:

```java
public record JsonDottedInput(
        @NotBlank String title,
        @JsonFormat(pattern = "dd.MM.uuuu")
        @NotNull LocalDate eventDate
) {}
```

Đây là cách **cấu hình Jackson per property**. Nó không làm Spring Formatter chạy; đó là **một Jackson date format riêng**.

Không nên thay đổi tất cả JSON dates trên ứng dụng chỉ để xử lý một form nếu API đã công bố format ISO và có clients đang dùng nó.

### 5.3. JSON format phức tạp: custom JsonDeserializer

Với format như `dd MMM uuuu` theo locale client, parsing có điều kiện, hoặc value object phức tạp, có thể viết một Jackson `JsonDeserializer<T>` và đăng ký bằng `@JsonDeserialize(using=...)`, Jackson Module hoặc Spring Boot `@JsonComponent`.

Những tình huống cần quan tâm:

- Parsing phải chặt chẽ, không normalize âm thầm ngày không tồn tại.
- Trả lỗi rõ ràng khi sai pattern và không leak internal parsing details.
- Không dùng locale hệ điều hành làm implicit contract nếu API đa vùng.
- Không “reuse” Spring Formatter bằng một adapter tùy tiện mà bỏ qua thread safety hoặc format consistency.
- Test serialize **và** deserialize, kể cả null, invalid string, timezone/offset khi type chứa giờ.

### 5.4. Chuyển JSON string thành LocalDate trong service?

Một giải pháp khác là DTO nhận `String`:

```java
public record RawDateRequest(
        String eventDate
) {}
```

sau đó service gọi một parser được ứng dụng sở hữu. Điều này có thể hợp lý khi muốn trả nhiều lỗi business-specific mà không phụ thuộc Jackson. Tuy nhiên có nhược điểm: trộn validation với parsing thủ công, tăng cơ hội thiếu test, làm Swagger/OpenAPI schema khác và thêm mã chuyển đổi. Ưu tiên Jackson configuration khi chỉ cần một định dạng JSON chuẩn.

## 6. Dự án runnable: so sánh Spring Formatter và Jackson

Ứng dụng Java 17, Spring Boot 3.3.6, Spring MVC và Jakarta Validation. Nó có năm endpoint:

| Endpoint | Nguồn input | Định dạng ngày được chấp nhận trong demo |
| --- | --- | --- |
| `POST /api/events/form` | `@ModelAttribute EventInput` | `06.11.2026` nhờ custom Formatter |
| `GET /api/events/query` | `@RequestParam LocalDate` | `06.11.2026` nhờ custom Formatter |
| `GET /api/events/query-iso` | `@RequestParam @DateTimeFormat(iso=ISO.DATE)` | `2026-11-06` nhờ annotation |
| `POST /api/events/json` | `@RequestBody EventInput` | `2026-11-06` nhờ Jackson mặc định |
| `POST /api/events/json-dotted` | `@RequestBody JsonDottedInput` | `06.11.2026` nhờ `@JsonFormat` của Jackson |

### 6.1. Cấu trúc project

```text
formatter-json-diagnosis/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/formatdiag/
        FormatDiagnosisApplication.java
        DottedLocalDateFormatter.java
        WebFormattingConfiguration.java
        EventInput.java
        JsonDottedInput.java
        EventView.java
        FieldIssue.java
        ApiError.java
        ErrorPayloadMapper.java
        EventController.java
        EventExceptionAdvice.java
      resources/
        application.properties
    test/
      java/com/example/formatdiag/
        FormatterVsJsonTest.java
```

### 6.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'formatter-json-diagnosis'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` trong Boot 3.3 cung cấp MVC và Jackson cùng Java Time support qua starter JSON. `spring-boot-starter-validation` cung cấp Jakarta Validation provider. Không cần thêm Jackson module thủ công trong project này vì Boot auto-config chuẩn đã có Java Time module từ dependencies tương ứng.

### 6.3. Main application

`src/main/java/com/example/formatdiag/FormatDiagnosisApplication.java`:

```java
package com.example.formatdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormatDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatDiagnosisApplication.class, args);
    }
}
```

### 6.4. application.properties

`src/main/resources/application.properties`:

```properties
spring.application.name=formatter-json-diagnosis
spring.jackson.serialization.write-dates-as-timestamps=false
```

Dòng Jackson property trên giúp ý định xuất Java Time values thành chuỗi ISO rõ ràng trong demo. Nó **không làm Jackson đọc định dạng dotted**; input dotted vẫn cần `@JsonFormat` hoặc custom deserializer.

Không thêm `@EnableWebMvc` chỉ để cấu hình một Formatter, vì annotation đó có thể thay đổi cách Boot auto-configure MVC. `WebMvcConfigurer` là đủ để tùy biến trong mô hình thông thường.

### 6.5. Custom Formatter<LocalDate>

`src/main/java/com/example/formatdiag/DottedLocalDateFormatter.java`:

```java
package com.example.formatdiag;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

@Component
public class DottedLocalDateFormatter implements Formatter<LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd.MM.uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, FORMAT);
    }

    @Override
    public String print(LocalDate date, Locale locale) {
        return date.format(FORMAT);
    }
}
```

Giải thích:

- `Formatter<LocalDate>` cung cấp parser/printer cho Spring MVC string field conversion.
- Pattern `dd.MM.uuuu` nhận `06.11.2026`.
- `ResolverStyle.STRICT` từ chối ngày không tồn tại, ví dụ `31.02.2026`.
- `DateTimeFormatter` là immutable/thread-safe; biến `static final` dùng được trong singleton Spring bean.
- Tham số `Locale` không được dùng vì ví dụ chọn **pattern cố định không theo ngôn ngữ**. Nếu muốn localized month names, cần thiết kế và test locale policy rõ ràng.
- `LocalDate.parse` có thể ném `DateTimeParseException`, một runtime exception. Spring conversion/binding xử lý nó theo pipeline tương ứng; formatter không tự phát HTTP status.

### 6.6. Đăng ký Formatter vào Spring MVC

`src/main/java/com/example/formatdiag/WebFormattingConfiguration.java`:

```java
package com.example.formatdiag;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    private final DottedLocalDateFormatter formatter;

    public WebFormattingConfiguration(
            DottedLocalDateFormatter formatter) {
        this.formatter = formatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(formatter);
    }
}
```

Spring MVC sử dụng registry để chuyển giá trị `String` sang `LocalDate` ở những binding path phù hợp.

**Câu hỏi kiểm tra:** code này có gọi `ObjectMapper#registerModule` không? **Không.** Nó đăng ký Spring Formatter. Khi controller có `@RequestBody` JSON, Jackson không tự đến đây gọi `formatter.parse(...)`.

Nếu formatter không hit cả form/query, hãy kiểm tra:

- Configuration class có được component scan không?
- `addFormatters` có thực sự được Spring gọi không?
- Có `@EnableWebMvc` hoặc custom MVC config vô hiệu hóa auto config mong muốn không?
- Có một `Converter<String,LocalDate>` hoặc annotation `@DateTimeFormat` khác được ưu tiên không?
- Method signature/target type có đúng `LocalDate` không?
- Request có thật sự đi vào `@RequestParam`/`@ModelAttribute` hay vào một `@RequestBody` argument?

### 6.7. DTO dùng cho cả form và JSON ISO

`src/main/java/com/example/formatdiag/EventInput.java`:

```java
package com.example.formatdiag;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record EventInput(
        @NotBlank String title,
        @NotNull LocalDate eventDate
) {}
```

Với `@ModelAttribute`, Spring constructor binding lấy chuỗi `eventDate` từ request và gọi formatter thích hợp. Với `@RequestBody`, Jackson nhận JSON và tạo cùng record nhưng sử dụng JSON deserializer.

Record không có setter, song Spring MVC 6.1 có khả năng constructor binding. `@NotNull` bắt ngày bị thiếu sau khi object được tạo; nó không bắt lỗi text ngày chưa convert thành `LocalDate` trong JSON vì lỗi đó phát sinh ở Jackson trước validation.

### 6.8. DTO cho JSON dotted được cấu hình riêng

`src/main/java/com/example/formatdiag/JsonDottedInput.java`:

```java
package com.example.formatdiag;

import com.fasterxml.jackson.annotation.JsonFormat;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record JsonDottedInput(
        @NotBlank String title,

        @NotNull
        @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

`@JsonFormat` là thông tin cho Jackson. Nó **không** chứng minh custom Spring Formatter chạy; nó chỉ hướng dẫn Jackson Java Time deserializer dùng pattern của riêng nó. Đối với API thật, nên tránh hai DTO có format khác nhau nếu không có lý do nghiệp vụ, vì dễ gây confusion cho clients. Demo có hai DTO **để quan sát rõ hai pipeline**.

### 6.9. DTO trả về và error schema

`src/main/java/com/example/formatdiag/EventView.java`:

```java
package com.example.formatdiag;

import java.time.LocalDate;

public record EventView(
        String title,
        LocalDate eventDate
) {}
```

`src/main/java/com/example/formatdiag/FieldIssue.java`:

```java
package com.example.formatdiag;

public record FieldIssue(
        String field,
        String code
) {}
```

`src/main/java/com/example/formatdiag/ApiError.java`:

```java
package com.example.formatdiag;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> fields
) {}
```

`EventView` chứa `LocalDate`: khi trả `@ResponseBody`, Jackson serializer xuất ngày ở định dạng ISO. Điều này **không đối nghịch** với việc form input dùng dotted pattern — input parser và output serializer khác nhau.

`ApiError` không trả raw exception text, rejected JSON hoặc field value. Các dữ liệu này có thể chứa thông tin cá nhân; chỉ dùng error codes được kiểm soát.

### 6.10. Error mapper dùng BindingResult

`src/main/java/com/example/formatdiag/ErrorPayloadMapper.java`:

```java
package com.example.formatdiag;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public final class ErrorPayloadMapper {

    private ErrorPayloadMapper() {
    }

    public static ApiError invalid(BindingResult result) {
        List<FieldIssue> fields = result.getAllErrors()
                .stream()
                .map(ErrorPayloadMapper::toFieldIssue)
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        return new ApiError("VALIDATION_ERROR", fields);
    }

    private static FieldIssue toFieldIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        return new FieldIssue(field, code);
    }
}
```

Mapper nhận cả `FieldError` và `ObjectError`, giữ machine-readable codes và sort đầu ra. Không nên suy rằng thứ tự error provider/Binder luôn trùng thứ tự khai báo fields. Nếu product yêu cầu error message đa ngữ, bổ sung `MessageSource` riêng, nhưng đó **không phải cơ chế giúp Jackson parse ngày**.

### 6.11. EventController với năm endpoint

`src/main/java/com/example/formatdiag/EventController.java`:

```java
package com.example.formatdiag;

import jakarta.validation.Valid;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/events")
public class EventController {

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> fromForm(
            @Valid @ModelAttribute("eventInput") EventInput input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    ErrorPayloadMapper.invalid(errors)
            );
        }

        return ResponseEntity.ok(
                new EventView(input.title(), input.eventDate())
        );
    }

    @GetMapping("/query")
    public EventView fromQuery(
            @RequestParam String title,
            @RequestParam LocalDate eventDate) {

        return new EventView(title, eventDate);
    }

    @GetMapping("/query-iso")
    public EventView fromAnnotatedQuery(
            @RequestParam String title,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate eventDate) {

        return new EventView(title, eventDate);
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EventView fromJson(
            @Valid @RequestBody EventInput input) {

        return new EventView(input.title(), input.eventDate());
    }

    @PostMapping(
            path = "/json-dotted",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EventView fromConfiguredJson(
            @Valid @RequestBody JsonDottedInput input) {

        return new EventView(input.title(), input.eventDate());
    }
}
```

**Đọc đúng vai trò:**

- `fromForm` dùng `@ModelAttribute`, nên `WebDataBinder` sử dụng MVC `Formatter<LocalDate>`.
- `fromQuery` dùng `@RequestParam LocalDate`, cũng đi qua Spring MVC conversion.
- `fromAnnotatedQuery` dùng `@DateTimeFormat(iso=ISO.DATE)` để yêu cầu ISO **cho tham số đó**, không ảnh hưởng Jackson.
- `fromJson` dùng `@RequestBody EventInput`, nên JSON body do Jackson parse.
- `fromConfiguredJson` vẫn do **Jackson** parse, nhưng `@JsonFormat` chọn dotted pattern.
- Các response `EventView` là JSON do Jackson **serialize**, không dùng `Formatter#print` chỉ vì object có `LocalDate`.

`BindingResult errors` đứng **ngay sau** `@Valid @ModelAttribute` argument. Nếu đặt một tham số khác xen vào, Spring có thể không liên kết lỗi đúng chỗ.

### 6.12. Global advice phân biệt lỗi JSON, query và validation

`src/main/java/com/example/formatdiag/EventExceptionAdvice.java`:

```java
package com.example.formatdiag;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class EventExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidArgument(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                ErrorPayloadMapper.invalid(
                        exception.getBindingResult()
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_JSON", List.of())
        );
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidQueryParameter(
            MethodArgumentTypeMismatchException exception) {

        FieldIssue issue = new FieldIssue(
                exception.getName(),
                "typeMismatch"
        );

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "QUERY_TYPE_MISMATCH",
                        List.of(issue)
                )
        );
    }
}
```

Trong demo:

- JSON date string sai định dạng → `HttpMessageNotReadableException` → `INVALID_JSON`.
- Query param date sai định dạng → `MethodArgumentTypeMismatchException` → `QUERY_TYPE_MISMATCH`.
- Object đã tạo thành công nhưng `@NotNull`/`@NotBlank` vi phạm → `MethodArgumentNotValidException` (JSON) hoặc `BindingResult` (form) → `VALIDATION_ERROR`.
- Form field `LocalDate` không thể parse thường được ghi nhận bằng binding error trong `BindingResult`; response vẫn `VALIDATION_ERROR` nhưng `FieldIssue.code` có thể là `typeMismatch`.

**Đây là mã lỗi thiết kế của demo**, không phải bộ HTTP error codes mặc định mà Spring bắt buộc mọi ứng dụng phải dùng. API production có thể chọn `ProblemDetail` theo RFC 9457, nhưng cần giữ phân biệt binding, parsing và validation.

## 7. Kiểm thử thực tế bằng MockMvc

Tệp `src/test/java/com/example/formatdiag/FormatterVsJsonTest.java`:

```java
package com.example.formatdiag;

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
class FormatterVsJsonTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formUsesCustomSpringFormatter() throws Exception {
        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Conference"))
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void queryUsesCustomSpringFormatter() throws Exception {
        mvc.perform(get("/api/events/query")
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void isoStringIsNotTheCustomFormFormat()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void isoQueryIsNotTheCustomQueryFormat()
            throws Exception {

        mvc.perform(get("/api/events/query")
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("QUERY_TYPE_MISMATCH"));
    }

    @Test
    void annotatedQueryCanUseIsoInstead() throws Exception {
        mvc.perform(get("/api/events/query-iso")
                .param("title", "Conference")
                .param("eventDate", "2026-11-06"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void annotatedIsoQueryRejectsDottedInput()
            throws Exception {

        mvc.perform(get("/api/events/query-iso")
                .param("title", "Conference")
                .param("eventDate", "06.11.2026"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("QUERY_TYPE_MISMATCH"));
    }

    @Test
    void normalJsonUsesJacksonIsoDeserialization()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "2026-11-06"
                        }
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void sameDottedTextInJsonDoesNotUseSpringFormatter()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "06.11.2026"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void jsonFormatMakesJacksonAcceptDottedText()
            throws Exception {

        mvc.perform(post("/api/events/json-dotted")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "06.11.2026"
                        }
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.eventDate")
                    .value("2026-11-06"));
    }

    @Test
    void jsonFormatDoesNotMeanJsonAlsoAcceptsIso()
            throws Exception {

        mvc.perform(post("/api/events/json-dotted")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Conference",
                          "eventDate": "2026-11-06"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void missingDateInFormFailsNotNull()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("eventDate"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotNull"));
    }

    @Test
    void missingDateInJsonFailsValidationNotParsing()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"Conference"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotNull"));
    }

    @Test
    void blankTitleInJsonIsBeanValidation()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"  ","eventDate":"2026-11-06"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("title"))
            .andExpect(jsonPath("$.fields[0].code")
                    .value("NotBlank"));
    }

    @Test
    void malformedJsonFailsInConverter()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Conference\",\"eventDate\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void invalidCalendarDateInFormIsRejected()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Conference")
                .param("eventDate", "31.02.2026"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void invalidCalendarDateInJsonIsRejected()
            throws Exception {

        mvc.perform(post("/api/events/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title":"Conference",
                          "eventDate":"2026-02-31"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void unsupportedMediaTypeDoesNotBecomeFormatterFailure()
            throws Exception {

        mvc.perform(post("/api/events/form")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"Conference","eventDate":"2026-11-06"}
                        """))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Bộ test có **17 phương thức `@Test`**. Chúng kiểm tra:

1. Form-urlencoded chấp nhận `06.11.2026`.
2. Query parameter chấp nhận `06.11.2026`.
3. Form ISO không đúng custom formatter → binding error.
4. Query ISO không đúng custom formatter → query type mismatch.
5. `@DateTimeFormat(iso=ISO.DATE)` làm một query parameter đọc ISO.
6. Query có annotation ISO từ chối dotted.
7. JSON mặc định đọc ISO qua Jackson.
8. Cùng dotted text trong JSON bị từ chối, dù Spring Formatter đã đăng ký.
9. `@JsonFormat` giúp **Jackson** đọc dotted mà không cần Spring Formatter.
10. JSON endpoint đã ghi pattern dotted từ chối ISO khi pattern không khớp.
11. Form thiếu date → Bean Validation `NotNull`.
12. JSON thiếu date, khi record được tạo với null → Bean Validation `NotNull`.
13. JSON title blank → Bean Validation `NotBlank`.
14. JSON malformed → converter/parser error.
15. Ngày không tồn tại bị custom Formatter từ chối.
16. Ngày không tồn tại bị Jackson từ chối.
17. Wrong Content-Type/consumes → 415, không phải formatter failure.

### 7.1. Chạy test

Từ thư mục project đã có Gradle wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có wrapper, có thể chạy `gradle test` bằng Gradle đã cài hoặc tạo wrapper trước.

**Kỳ vọng:** 17 test PASS với Spring Boot 3.3.6, Java 17 và dependency được khai báo, khi không có các custom converter/mapper khác chen vào. Đây là kỳ vọng của mã nguồn được rà soát tĩnh; **không phải** khẳng định đã thực sự chạy Gradle/JUnit trong quá trình biên soạn bài.

### 7.2. Vì sao chọn những assertions này?

Chỉ kiểm tra HTTP 400 không đủ để chẩn đoán “Formatter không áp dụng”. HTTP 400 có thể phát sinh từ Jackson deserialization, Bean Validation, Spring property binding hoặc Servlet parameter resolution. Vì vậy test so sánh thêm:

- Endpoint nào được gọi.
- `Content-Type`.
- Dữ liệu ngày dạng dotted/ISO.
- Mã lỗi từ advice: `INVALID_JSON`, `VALIDATION_ERROR`, `QUERY_TYPE_MISMATCH`.
- Khi thành công, response `eventDate` ISO chứng minh **Jackson writer** serialize ngày độc lập với Spring Formatter input.

Không assert một câu lỗi tiếng Anh cụ thể từ Jackson/Bean Validation; nó có thể thay đổi theo locale, version hoặc provider. Mã lỗi demo ổn định hơn cho việc chẩn đoán.

## 8. Expected HTTP responses: đối chiếu cùng một ngày

### 8.1. Form-urlencoded với Formatter

```bash
curl -i -X POST 'http://localhost:8080/api/events/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Conference' \
  --data-urlencode 'eventDate=06.11.2026'
```

Kỳ vọng HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

Mặc dù **input** là dotted, **output** là ISO. Đây không phải bug: request đi qua Spring Formatter, response JSON đi qua Jackson serializer.

### 8.2. JSON mặc định với cùng dotted input

```bash
curl -i -X POST 'http://localhost:8080/api/events/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"06.11.2026"}'
```

Kỳ vọng HTTP 400:

```json
{
  "code": "INVALID_JSON",
  "fields": []
}
```

Ở đây Jackson không parse được dotted format theo default ISO `LocalDate` deserializer. Spring Formatter đã đăng ký **không được gọi**, bởi `@RequestBody` dùng `HttpMessageConverter`.

### 8.3. JSON ISO

```bash
curl -i -X POST 'http://localhost:8080/api/events/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"2026-11-06"}'
```

Kỳ vọng HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

### 8.4. JSON dotted với @JsonFormat

```bash
curl -i -X POST 'http://localhost:8080/api/events/json-dotted' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Conference","eventDate":"06.11.2026"}'
```

Kỳ vọng HTTP 200:

```json
{
  "title": "Conference",
  "eventDate": "2026-11-06"
}
```

Trong endpoint này Jackson đã được hướng dẫn đọc dotted pattern bằng `@JsonFormat` trên **request DTO**. Khi serialize `EventView` response DTO không có `@JsonFormat`, Jackson writer dùng ISO.

### 8.5. Query có @DateTimeFormat

```bash
curl -i 'http://localhost:8080/api/events/query-iso?title=Conference&eventDate=2026-11-06'
```

Kỳ vọng HTTP 200 với date ISO. Mặc dù global `Formatter<LocalDate>` dùng dotted pattern, annotation `@DateTimeFormat(iso=...)` ở argument chọn định dạng cho Spring argument binding.

## 9. Những sai lầm thường gặp khi “sửa formatter cho JSON”

### 9.1. Đăng ký thêm Formatter nhưng vẫn dùng @RequestBody

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DottedLocalDateFormatter());
}
```

Thêm code này lần nữa không khiến Jackson thay đổi. Hãy tìm `ObjectMapper`, `@JsonFormat` hoặc `JsonDeserializer` thay vì lặp lại cùng đăng ký.

### 9.2. Đặt @DateTimeFormat trên JSON DTO rồi chờ Jackson đọc theo pattern

```java
public record JsonDateInput(
        @DateTimeFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate
) {}
```

Annotation này phục vụ Spring formatting, không phải Jackson deserialization. Với `@RequestBody` JSON, nếu chỉ có annotation đó, Jackson vẫn có thể từ chối dotted input. Sử dụng `@JsonFormat` nếu định dạng JSON thật sự cần đổi.

### 9.3. Đặt @JsonFormat nhưng đang xử lý @RequestParam

```java
@GetMapping("/query")
public String query(
        @RequestParam @JsonFormat(pattern = "dd.MM.uuuu")
        LocalDate eventDate) {
    return eventDate.toString();
}
```

Jackson annotation không phải cách cấu hình request parameter string conversion. Cần `@DateTimeFormat` hoặc Spring `Formatter`/`Converter` tương ứng. Đây chỉ là snippet để chỉ ra phân biệt trách nhiệm.

### 9.4. Dùng @EnableWebMvc để thử chữa lỗi

Trong Spring Boot, bật `@EnableWebMvc` có thể làm thay đổi đáng kể MVC auto-configuration và converters. Chỉ để thêm formatter, dùng `WebMvcConfigurer#addFormatters`; không kích hoạt override toàn bộ Web MVC khi chưa có lý do và test.

### 9.5. Nhầm Formatter với Jackson Serializer

`Formatter#print` tạo string cho **Spring field formatting**, không phải chức năng của `MappingJackson2HttpMessageConverter` khi serialize JSON. Cả hai đều “định dạng” dữ liệu nhưng có SPI và lifecycle khác nhau.

### 9.6. Coi @Valid là parser JSON

`@Valid` không parse JSON. Nó được chạy sau khi object được tạo thành công. Nếu date string không được Jackson hiểu, thông thường lỗi nằm ở `HttpMessageNotReadableException`, không phải `@NotNull` mặc định.

### 9.7. Xử lý mọi 400 bằng một thông báo “Validation failed”

Tạo chung một HTTP 400 là hợp lệ nếu API contract chọn vậy, nhưng backend logs/metrics nên phân biệt:

- Unsupported media type.
- JSON parse/deserialize failure.
- Spring binding/type conversion failure.
- Bean Validation constraint failure.
- Business-level validation failure.

Nếu tất cả đều chuyển thành “invalid input” không có context, rất khó xác định vì sao formatter breakpoint không hit.

### 9.8. Sử dụng LocaleResolver và nghĩ Jackson sẽ dùng cùng locale

Spring Formatter nhận `Locale` làm tham số và có thể áp dụng locale của request do Spring resolve. Jackson deserialization không tự lấy toàn bộ luật của Spring `LocaleResolver` chỉ vì header `Accept-Language: vi` được gửi. Nếu JSON có localized dates hoặc numbers, hãy định nghĩa explicit Jackson locale/format policy và test; trong APIs công khai, ISO/numeric JSON thường dễ liên thông hơn.

### 9.9. Nhầm số JSON với chuỗi được format theo locale

Đối với JSON:

```json
{"price": 1234.56}
```

`price` là JSON **number token**, không phải một `String` "1.234,56" để Spring `@NumberFormat` parse. Jackson xử lý loại token phù hợp. Nếu JSON muốn gửi giá trị ở dạng string có dấu ngăn hàng nghìn, phải thiết kế JSON schema và Jackson deserializer/format cho trường đó; không kỳ vọng Spring `Formatter<BigDecimal>` hoạt động tự động.

### 9.10. Không kiểm tra annotation precedence

Nếu bạn đặt `@DateTimeFormat(iso=ISO.DATE)` cho method parameter, nó có thể ghi đè lựa chọn formatter theo type trong Spring. Khi đó breakpoint custom Formatter không hit ở **query endpoint có annotation**, khác hẳn trường hợp **JSON endpoint**. Phải phân biệt hai nguyên nhân:

- JSON path **bỏ qua Spring FormattingConversionService** cho deserialization.
- Spring conversion path **chọn một annotation-specific formatter khác**.

Dùng các cặp test cùng format nhưng không/ có annotation sẽ chỉ ra nguyên nhân.

### 9.11. Chỉ test một endpoint JSON và bỏ form/query

Nếu formatter không chạy, làm sao biết do thiếu registration hay do request đi qua converter? Test đơn giản:

1. Gọi `@RequestParam LocalDate` với dotted string.
2. Gọi `@ModelAttribute` với dotted form field.
3. Gọi `@RequestBody` với dotted JSON string.

Nếu 1 và 2 thành công, 3 thất bại, registration không phải lỗi chính. Nếu cả 1 và 2 thất bại, kiểm tra Spring MVC converter registry, component scan và annotation precedence.

### 9.12. JSON malformed và validation groups là vấn đề khác

Nếu đã bật method validation/`@Validated` ở controller class, exception type có thể khác Spring MVC built-in method validation từ Framework 6.1; tuy nhiên nó **không biến Spring Formatter thành Jackson deserializer**. Đừng thay đổi validation groups để sửa parsing. Giữ từng lớp trách nhiệm tách biệt.

## 10. Checklist chẩn đoán production

1. Xác định annotation của method parameter: `@RequestParam`, `@ModelAttribute`, `@RequestBody`, `@RequestPart` hay loại khác.
2. Xác định Content-Type và target Java type; không suy từ URL hoặc client code.
3. Nếu `@RequestBody` JSON, kiểm tra `HttpMessageConverter` được chọn, Jackson ObjectMapper và Java Time module.
4. Nếu form/query, kiểm tra `FormattingConversionService`, `WebMvcConfigurer#addFormatters` và `FormatterRegistry`.
5. Kiểm tra có `@DateTimeFormat` / `@NumberFormat` ở field/method parameter không.
6. Đặt breakpoint vào custom `Formatter#parse`, Jackson deserializer và converter resolver để nhận diện pipeline.
7. Không dùng `@DateTimeFormat` để điều khiển Jackson JSON; cần `@JsonFormat` hoặc Jackson deserializer.
8. Không dùng `@JsonFormat` để điều khiển Spring query/form field binding; cần Formatter/Converter hoặc `@DateTimeFormat`.
9. Phân biệt invalid body vs null/missing property sau deserialization.
10. Xác minh `@Valid` có được chạy sau bind/deserialize không, và exception mapping đúng.
11. Không phản chiếu raw JSON body, SQL logs, tokens hoặc exception detail nhạy cảm trong lỗi trả client.
12. Nếu dùng API dates, ưu tiên ISO 8601 trong JSON và định dạng localized ở UI; đặc biệt kiểm soát time zone cho `Instant`, `OffsetDateTime`, `ZonedDateTime`.
13. Test đúng ba đường form/query/JSON, cả success và failure.
14. Test annotation precedence: có/không `@DateTimeFormat` và per-property `@JsonFormat`.
15. Test ngày không tồn tại, null/missing, text sai định dạng, body malformed và wrong media type.
16. Không bật `@EnableWebMvc` tùy tiện khi chỉ cần đăng ký Formatter.
17. Cân nhắc docs/OpenAPI/JSON schema: contract JSON phải công bố định dạng ngày cho client.
18. Khi nâng Boot/Spring/Jackson, chạy lại tests vì implementation, defaults và error messages có thể khác.

**Kết luận:** Khi một Formatter không chạy trong endpoint JSON, hãy kiểm tra **đường xử lý request** trước khi thêm cấu hình. `@ModelAttribute` và `@RequestParam` thường dùng Spring `ConversionService`/`Formatter` để chuyển từ chuỗi request, còn `@RequestBody` JSON dùng `HttpMessageConverter` và JSON mapper (thường Jackson). Hai cơ chế không tự chia sẻ formatter registrations. Cách sửa tùy mục tiêu: **giữ ISO JSON** để đơn giản, hoặc cấu hình **`@JsonFormat`/Jackson deserializer** khi JSON thật sự cần một pattern khác. Test so sánh form, query và JSON là cách chẩn đoán đáng tin cậy hơn việc chỉ nhìn HTTP 400.

## 11. Tài liệu tham khảo

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `Parser`, `Printer` và `FormattingConversionService`.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): conversion của request arguments dựa trên chuỗi.
- [Spring Framework — MVC Conversion Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): `WebMvcConfigurer#addFormatters` và `@DateTimeFormat`.
- [Spring Framework — @ModelAttribute Argument](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): `WebDataBinder`, binding request parameters và validation.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization bằng `HttpMessageConverter` và validation sau đó.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converters cho request/response body.
- [Spring Framework — MVC Message Converter Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): tùy chỉnh converters.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC ConversionService và HttpMessageConverters.
- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): ObjectMapper auto-config và custom serializers/deserializers.
- [Jackson — JsonFormat Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.17.3/com/fasterxml/jackson/annotation/JsonFormat.html): pattern/shape/locale cho Jackson properties.
