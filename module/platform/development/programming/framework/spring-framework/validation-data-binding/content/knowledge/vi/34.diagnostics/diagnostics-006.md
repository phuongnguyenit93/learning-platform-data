# Sai Locale, charset, pattern hoặc múi giờ — chẩn đoán Spring MVC Validation & Data Binding

## 1. Tình huống thực tế: dữ liệu “giống nhau” nhưng kết quả khác nhau

Một API Java/Spring MVC nhận ngày, số tiền, tên tiếng Việt và thời điểm hẹn. Người dùng phản ánh:

- Máy A chấp nhận `amount=1,234.50`, máy B chấp nhận `amount=1.234,50`.
- Form gửi `day=06/11/2026` nhưng server báo `typeMismatch`; cùng giá trị trong JSON lại được đọc khác.
- Thông báo `@NotBlank` hiện tiếng Anh dù client gửi header `Accept-Language: vi`.
- Tên `Đà Nẵng` trở thành chuỗi lỗi dấu như `ÄÃ  Nẵng`.
- `2026-11-06T09:30:00+07:00` và `2026-11-06T02:30:00Z` bị xem là hai cuộc hẹn khác nhau.
- Người dùng ở Berlin chọn `2026-03-29 02:30` nhưng ngày đó local time **không tồn tại** vì daylight saving time (DST).
- Sau khi chạy CI hoặc deploy container ở zone UTC, những tests dựa vào `ZoneId.systemDefault()` bỗng thất bại.

Đây có thể là **bốn nhóm sự cố độc lập**:

| Nhóm | Điều gì được quyết định? | Ví dụ |
| --- | --- | --- |
| **Locale** | Ngôn ngữ message, dấu thập phân, dấu phân nhóm, tên tháng/ngày | `1,234.50` (US) và `1.234,50` (Germany) |
| **Charset / encoding** | Cách bytes được giải mã thành Unicode text, và text được mã hóa lại thành bytes | UTF-8 của `Đà Nẵng` |
| **Pattern** | Chuỗi input nào được parser chấp nhận, phần ngày/tháng/năm nằm ở đâu | `dd/MM/yyyy` khác `yyyy-MM-dd` |
| **Time zone / UTC offset** | Một local date-time trỏ đến instant nào, có gap/overlap DST không | `+07:00` khác `Europe/Berlin` |

**Mục tiêu bài:** có quy trình chẩn đoán để tìm đúng tầng lỗi, không thử thay ngẫu nhiên `Locale.setDefault()`, `spring.jackson.time-zone` hoặc thêm `@JsonFormat` cho đến khi “hết lỗi”.

Trong module **Spring Framework - validation-data-binding**, chúng ta đặc biệt quan tâm việc:
1. Spring MVC lấy locale thế nào khi bind query/form.
2. `@DateTimeFormat`, `@NumberFormat` và `ConversionService` chọn parser ra sao.
3. `@RequestBody` đi qua Jackson, khác `@ModelAttribute`/`@RequestParam`.
4. Jakarta Validation và Spring `MessageSource` chọn bản dịch lỗi.
5. Encoding HTTP request, response và resource bundles nằm ở các điểm khác nhau.
6. Java Time phân biệt `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, `Instant`.
7. Viết MockMvc/JUnit tests rõ locale, charset, pattern, zone và DST.

**Phiên bản minh họa:** Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.6, Jakarta Validation và Jackson do Spring Boot quản lý. Đây là ví dụ cố định phiên bản, không tuyên bố Boot 3.5.6 là phiên bản mới nhất.

## 2. Sơ đồ đường đi dữ liệu: xác định lỗi xuất hiện ở bước nào

```text
HTTP bytes
   |
   v
[1] HTTP decoding / request parameters
    Content-Type + charset, percent-encoding, query/form parsing
   |
   v
[2a] @RequestParam / @ModelAttribute
     ConversionService + Formatter + WebDataBinder
     @DateTimeFormat, @NumberFormat, type conversion
   |
   +------> [2b] @RequestBody JSON
                HttpMessageConverter / Jackson
                @JsonFormat, ObjectMapper, JavaTimeModule
   |
   v
[3] Jakarta Validation / Spring Validator
    @NotBlank, @NotNull, @Past, @Valid...
    LocalValidatorFactoryBean / MessageInterpolator
   |
   v
[4] Error handling / serialization
    BindingResult, FieldError, exception advice
    MessageSource, Locale, JSON response bytes
```

Đừng gộp [1] và [2]: chuỗi đã bị giải mã sai từ bytes không thể được `@DateTimeFormat` sửa. Đừng gộp [2a] và [2b]: `@JsonFormat` **không** tự điều khiển `@RequestParam`; `@DateTimeFormat` **không** tự điều khiển Jackson đang deserialize `@RequestBody`. Đừng gộp [3] và [4]: thông báo localized là **output của validation**, còn dữ liệu có thể đã được convert đúng hoặc chưa được convert.

### 2.1. Bảng triệu chứng nhanh

| Triệu chứng | Ưu tiên kiểm tra | Không nên làm ngay |
| --- | --- | --- |
| `typeMismatch` với `06/11/2026` | `@DateTimeFormat`, target Java type, URI encoding | Đổi timezone trước khi biết pattern |
| Giá tiền phân tích sai | Locale request, `@NumberFormat`, dấu nhóm/thập phân | Sửa JVM default locale trong request thread |
| JSON ngày parse khác query | Jackson `@JsonFormat`/ObjectMapper vs Spring Formatter | Giả định một annotation áp dụng cho cả hai |
| Text Việt bị “mojibake” | Bytes thực, request charset, resource encoding | Thay `Accept-Language` để sửa Unicode |
| Message lỗi sai ngôn ngữ | `LocaleResolver`, `MessageSource`, `ValidationMessages` | Thay timezone |
| Hai timestamp biểu diễn khác nhau | So `Instant`, kiểm tra offset | So sánh raw date-time strings |
| Giờ 02:30 xảy ra 0 hoặc 2 lần | ZoneId rules + DST transition | Dùng offset tĩnh cho cả năm |
| CI fail do ngày hiện tại | `Clock`/ZoneId/Locale mặc định | Cố định locale/zone toàn JVM trong parallel tests |

## 3. Locale: ngôn ngữ và quy ước định dạng, không phải múi giờ

### 3.1. Locale là gì?

Java `Locale` biểu diễn ngôn ngữ và các biến thể vùng, ví dụ:

```java
Locale.ENGLISH;                           // en
Locale.US;                                // en-US
Locale.GERMANY;                           // de-DE
Locale.forLanguageTag("vi-VN");          // vi-VN
```

Một locale thường ảnh hưởng:
- Resource bundle được chọn.
- Dấu phân cách phần nguyên/thập phân và cách biểu diễn số.
- Tên tháng hoặc thứ nếu pattern dùng text (ví dụ `MMM`, `EEEE`).
- Một số quy tắc số nhiều/cách trình bày thông báo.

**Nó không mang ý nghĩa time zone.** Một người dùng `Locale.US` có thể đang ở Paris, Tokyo, Đà Nẵng hoặc dùng một lịch hẹn UTC. Không suy timezone từ `Accept-Language`.

### 3.2. Spring MVC xác định request locale

Trong Spring MVC Servlet, `LocaleResolver` quản lý locale trong phạm vi request. Một cấu hình phổ biến là `AcceptHeaderLocaleResolver`, đọc locale được client biểu thị qua `Accept-Language`. Mã ứng dụng có thể truy cập:

```java
Locale locale = LocaleContextHolder.getLocale();
```

Đây là **fragment**, cần import `org.springframework.context.i18n.LocaleContextHolder` và phải được gọi trong ngữ cảnh request. Khi chạy test/service ngoài request, `LocaleContextHolder` có thể fallback về locale hệ thống/được đặt trên thread.

Ví dụ:

```http
GET /api/format/amount?amount=1.234,50
Accept-Language: de-DE
```

Nếu field có `@NumberFormat(pattern="#,##0.00")`, formatter theo locale de-DE hiểu dấu `,` là thập phân và dấu `.` là phân nhóm; một request en-US tương ứng thường dùng `1,234.50`.

### 3.3. `Accept-Language` không chứng minh charset

Header:

```http
Accept-Language: vi-VN
```

chỉ biểu thị ngôn ngữ ưu tiên. Nó **không** tuyên bố body là UTF-8, không “sửa” những bytes đã bị decode sai, và không chọn `Asia/Ho_Chi_Minh`. Các quyết định liên quan tới encoding, locale và zone phải được cấu hình riêng.

## 4. `@NumberFormat` và lỗi do dấu thập phân/phân nhóm

### 4.1. Ví dụ MVC

```java
@GetMapping("/amount")
public Map<String, String> amount(
        @RequestParam("amount")
        @NumberFormat(pattern = "#,##0.00")
        BigDecimal amount) {

    return Map.of(
            "plain", amount.stripTrailingZeros().toPlainString());
}
```

Đây là fragment của controller đầy đủ ở phần 13. Mẫu `#,##0.00` có:
- Dấu phân nhóm theo **locale đang dùng**.
- Phần thập phân ít nhất hai chữ số khi format.
- Parser/formatter do Spring `FormattingConversionService` sử dụng.

Hai request mô tả **cùng một lượng số học**:

```http
GET /api/format/amount?amount=1,234.50
Accept-Language: en-US
```

```http
GET /api/format/amount?amount=1.234,50
Accept-Language: de-DE
```

Kết quả logic mong đợi:

```json
{"plain":"1234.5"}
```

Dùng `stripTrailingZeros().toPlainString()` trong ví dụ để không phụ thuộc scale của `BigDecimal` (có thể là 1234.50 hay 1234.5). Đây là **canonical display của demo**, không phải một serialization contract phổ quát cho tiền tệ.

### 4.2. Chẩn đoán parser: locale đúng nhưng giá trị vẫn sai

Có thể là:
1. `@NumberFormat` không đặt trên **đúng** field/parameter.
2. Controller đang nhận String rồi tự `new BigDecimal(text)`, bypass formatter.
3. Request locale resolver bị thay.
4. NumberFormat parser có quy tắc leniency/coercion ngoài mong muốn.
5. Có một `Converter<String,BigDecimal>` custom ưu tiên khác.
6. Bạn dùng `@RequestBody` JSON numeric value, đường đi là Jackson.

**Quan trọng:** Không dùng một test `"1.234,50"` gửi với locale en-US rồi giả định chắc chắn sẽ lỗi. Một số parser số có hành vi lenient hoặc trả giá trị **khác** mà không báo exception. Nếu yêu cầu hợp đồng đầu vào thật nghiêm ngặt, bổ sung validation/strict parser chuyên biệt với full-input consumption và test riêng các tình huống dễ gây hiểu nhầm.

### 4.3. `@NumberFormat(style=...)` hay pattern?

```java
@NumberFormat(style = NumberFormat.Style.CURRENCY)
BigDecimal price;
```

Có thể dùng khi UI yêu cầu currency formatting theo locale, nhưng currency symbol, dấu cách và grouping phụ thuộc locale. Với API máy-máy, **nên dùng số canonical không có grouping** hoặc một schema rõ ràng thay vì bắt client gửi currency text đã format.

Nếu nghiệp vụ dùng tiền, `BigDecimal` thường phù hợp hơn `double` để tránh sai số binary floating point. Nhưng rounding, currency scale và business math vẫn phải được định nghĩa riêng.

## 5. Date pattern: `@DateTimeFormat` khác `@JsonFormat`

### 5.1. Spring MVC query/form binding

```java
@GetMapping("/day")
public Map<String, String> day(
        @RequestParam("day")
        @DateTimeFormat(pattern = "dd/MM/yyyy")
        LocalDate day) {

    return Map.of("isoDate", day.toString());
}
```

Request:

```http
GET /api/format/day?day=06/11/2026
```

Kết quả:

```json
{"isoDate":"2026-11-06"}
```

Nhưng:

```http
GET /api/format/day?day=2026-11-06
```

**không khớp pattern `dd/MM/yyyy`**. Đường conversion của Spring thường dẫn tới `MethodArgumentTypeMismatchException`/`TypeMismatchException` với HTTP 400 (nếu có error resolver phù hợp).

### 5.2. Đừng nhầm thứ tự ngày-tháng

Với `dd/MM/yyyy`:
- `06/11/2026` là **ngày 6 tháng 11 năm 2026**.
- `11/06/2026` là **ngày 11 tháng 6 năm 2026**.

Nếu API nhận `MM/dd/yyyy`:
- `06/11/2026` là **ngày 11 tháng 6 năm 2026**.

Một chuỗi có thể hợp lệ với **cả hai pattern** nhưng mang nghĩa khác nhau. Test chỉ kiểm tra status 200 là chưa đủ: phải assert `LocalDate` được hiểu đúng (output canonical ISO).

### 5.3. Dùng ISO khi giao tiếp giữa các hệ thống

Khi không có yêu cầu UI đặc biệt, kiểu API dễ hiểu hơn:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate day
```

với giá trị `2026-11-06`. ISO được khuyến khích trong API giữa các service/client vì ít mơ hồ ngày-tháng hơn. Nếu nghiệp vụ thật sự dùng `dd/MM/yyyy` cho form, **ghi rõ** và kiểm thử pattern, không đoán theo locale mặc định.

### 5.4. Đặt pattern không thay đổi timezone của `LocalDate`

`LocalDate` chỉ mô tả **ngày trên lịch**, không có thời điểm trong ngày và không chứa timezone hay UTC offset. Vì vậy:
- Chuyển `06/11/2026` thành `2026-11-06` là **chuyển cách biểu diễn ngày**, chưa chuyển instant.
- Không cộng trừ 7 giờ cho `LocalDate` để “chỉnh Việt Nam”.
- Khi biến một ngày thành khoảng thời gian (ví dụ báo cáo bán hàng 00:00–24:00), phải chọn **ZoneId theo nghiệp vụ** và lưu ý DST.

### 5.5. `dd/MM/yyyy`, `dd/MM/uuuu` và strict parsing

Trong `java.time.format.DateTimeFormatter`:
- `y` là year-of-era.
- `u` là proleptic year.
- `ResolverStyle.SMART` và `ResolverStyle.STRICT` có thể tạo kết quả khác cho ngày không tồn tại hoặc era handling.

Ví dụ strict parsing JDK:

```java
DateTimeFormatter strict =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed =
        LocalDate.parse("06/11/2026", strict);
```

Đây là fragment Java 17 với imports `LocalDate`, `DateTimeFormatter` và `ResolverStyle`. Nếu cần **strict validation** cho tất cả inputs (không chấp nhận ngày không tồn tại), hãy dùng parser với resolver style rõ ràng hoặc custom validation. Không tự suy rằng mọi cấu hình `@DateTimeFormat` mặc định đã tương đương đoạn strict JDK này.

## 6. JSON có đường định dạng ngày riêng

Khi controller dùng:

```java
@PostMapping("/json")
public void json(@RequestBody SomeDto dto) {}
```

Spring MVC thường dùng Jackson `HttpMessageConverter`. Đối với request DTO:

```java
public record SomeDto(
        @JsonFormat(pattern = "dd/MM/yyyy")
        LocalDate day) {}
```

annotation `@JsonFormat` ở đây cấu hình Jackson xử lý field `day` trong JSON, không thay thế `@DateTimeFormat` trên query/form.

Một DTO có thể chứa cả hai:

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
@JsonFormat(pattern = "yyyy-MM-dd")
private LocalDate day;
```

Chúng dùng ở **hai đường input khác nhau**; test phải chỉ ra một request `application/x-www-form-urlencoded` và một JSON request có kết quả mong đợi khác nhau. Nếu không có yêu cầu đặc biệt, hãy thống nhất ISO ở boundary để tránh duy trì hai hợp đồng format.

**Lưu ý:** Không xem `spring.jackson.date-format` hay `spring.jackson.time-zone` là biện pháp “đổi format toàn ứng dụng cho mọi Java Time type”. Jackson có modules, serializers và annotations khác nhau cho `java.time`; các tính năng global không nhất thiết tác động giống nhau đến `LocalDate`, `LocalDateTime`, `Instant` hoặc legacy `java.util.Date`. Kiểm tra JSON wire format thật bằng ObjectMapper test hoặc MockMvc.

## 7. Charset: lỗi bytes → String, không phải Locale

### 7.1. UTF-8 và mojibake

Một Java `String` dùng Unicode. Khi gửi qua HTTP, nó được mã hóa thành bytes theo charset (thường UTF-8). Bên nhận phải giải mã bằng charset **phù hợp với bytes thực**.

Ví dụ thuần Java có thể chạy độc lập:

```java
// CharsetEvidence.java
import java.nio.charset.StandardCharsets;

public class CharsetEvidence {
    public static void main(String[] args) {
        String value = "Đà Nẵng";
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

        System.out.println(
                new String(utf8, StandardCharsets.UTF_8));
        System.out.println(
                value.equals(new String(
                        utf8, StandardCharsets.ISO_8859_1)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CharsetEvidence.java
java CharsetEvidence
```

Stdout **xác định**:

```text
Đà Nẵng
false
```

Điều này chứng minh sai charset có thể làm biến dạng text dù `Locale.forLanguageTag("vi-VN")` đã được chọn đúng.

### 7.2. Những nơi encoding có thể khác nhau

1. **URL/query**: URI percent-encoding của các ký tự không phải ASCII; cách server decode query.
2. **HTML form**: body `application/x-www-form-urlencoded` thường chứa percent-encoded bytes; request character encoding phải phù hợp.
3. **JSON**: `application/json` trên Internet thường sử dụng UTF-8; Jackson JSON parser nhận bytes qua message converter, có xử lý encoding riêng.
4. **Response**: Charset được chỉ định/áp dụng khi serialize text, đặc biệt với plain text hoặc HTML.
5. **Resource bundles**: Encoding khi đọc `messages.properties`/`messages_vi.properties`.
6. **Source/build**: Encoding file Java/properties và Maven compiler/resources.
7. **Database**: Connection/column charset, collation, dữ liệu lưu trước đó.
8. **Terminal/log viewer**: Console có thể hiển thị sai dù HTTP bytes và JSON đúng.

Không chỉ nhìn một screenshot “chữ lỗi font”: kiểm tra bytes và từng boundary, xác định **nơi đầu tiên** Unicode text bị thay đổi.

### 7.3. Spring Boot Servlet encoding

Một cấu hình mẫu:

```properties
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force=true
spring.messages.encoding=UTF-8
```

`server.servlet.encoding.*` liên quan tới Servlet request/response encoding. `spring.messages.encoding` liên quan đến Spring `MessageSource` resource bundles. Hai thuộc tính xử lý **hai vấn đề khác nhau**. Jackson JSON, database hay terminal vẫn có cấu hình riêng nếu có.

Đừng đổi cấu hình encoding production chỉ vì một test dùng `MockMvc.param(...)` bị lỗi: `param(...)` truyền **Java Strings đã được decode** cho mock request và **không phải** kiểm thử đầy đủ bytes/percent-decoding từ mạng.

### 7.4. Kiểm thử raw bytes thay vì chỉ String

Khi kiểm thử JSON:

```java
String json = """
    {"name":"Đà Nẵng"}
    """;

mvc.perform(post("/api/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.name").value("Đà Nẵng"));
```

Ở đây `content(byte[])` thực sự đưa UTF-8 bytes vào mock HTTP message converter. Khác với một unit test `new String(...)`, nó đi qua Jackson và MVC endpoint.

Đối với form:
- `.param("city", "Đà Nẵng")` kiểm tra binding của String đã decode.
- Muốn kiểm thử wire bytes của `application/x-www-form-urlencoded`, đưa URL-encoded body bytes với đúng encoding hoặc chạy một real-server test. Tránh tuyên bố test `.param(...)` chứng minh proxy/container giải mã UTF-8 đúng.

### 7.5. Không sửa charset bằng `Accept-Language`

Một người dùng chọn tiếng Anh vẫn có thể gửi tên `Nguyễn Thị Mai`; UTF-8 phải giữ nguyên Unicode. Locale điều khiển lựa chọn câu thông báo và một số formatting rules; charset điều khiển bytes↔text.

## 8. MessageSource: “lỗi đúng nhưng thông báo sai ngôn ngữ”

### 8.1. Jakarta Validation message key

Một record DTO:

```java
public record EchoRequest(
        @NotBlank(message = "{request.name.required}")
        String name) {}
```

Bản dịch của ứng dụng Spring Boot:

```properties
# messages.properties
request.name.required=Please enter a name
```

```properties
# messages_vi.properties
request.name.required=Vui lòng nhập tên
```

Spring Boot tích hợp `MessageSource` vào validation message interpolation khi dùng hạ tầng Validator được auto-configure. Vì vậy cùng một `@NotBlank` có thể trả text khác nhau tùy request locale. **Phải có file cơ sở `messages.properties`** trong trường hợp sử dụng Boot auto-configured message source theo convention.

### 8.2. Kiểm tra lỗi thông báo sai locale theo thứ tự

1. Endpoint có dùng đúng `@Valid` hay `@Validated` để kích hoạt Bean Validation?
2. Có `spring-boot-starter-validation`/provider trên classpath?
3. `LocaleResolver` có dùng `Accept-Language` hay bị override?
4. `messages.properties` và `messages_vi.properties` có đúng vị trí `src/main/resources`?
5. Có sai tên key, basename hoặc encoding?
6. Handler trả `FieldError.getDefaultMessage()` hay trả một hard-coded English message?
7. Có custom `LocalValidatorFactoryBean` hoặc `MessageInterpolator` bỏ qua Spring MessageSource?
8. Test có thiết lập locale rõ ràng hay đang dựa vào default máy CI?

### 8.3. `getMessageTemplate()` khác `getMessage()`

Đối với Jakarta `ConstraintViolation`:
- `getMessageTemplate()` thường giữ descriptor gốc, ví dụ `{request.name.required}`.
- `getMessage()` là text đã interpolation theo locale.

Với Spring MVC `MethodArgumentNotValidException`, `FieldError.getDefaultMessage()` thường chứa thông điệp tương ứng từ validator. Nếu cần machine-readable error code, **đừng dùng nguyên text đã dịch** làm code: hãy dùng một mã ổn định riêng.

Trong project mẫu, JSON error response có:
- `code`: ví dụ `VALIDATION_ERROR`, `TYPE_MISMATCH`.
- `issues[].field` và `issues[].code` ổn định.
- `issues[].message` có thể localized, nhưng không chứa rejected raw value.

## 9. Múi giờ: local date-time, offset và instant là ba thứ khác nhau

### 9.1. Phân biệt các Java Time types

| Type | Chứa gì? | Ví dụ ứng dụng |
| --- | --- | --- |
| `LocalDate` | Ngày trên lịch, **không có giờ/zone** | Ngày sinh, ngày báo cáo |
| `LocalTime` | Giờ trong ngày, **không có ngày/zone** | Giờ mở cửa hàng ngày |
| `LocalDateTime` | Ngày + giờ cục bộ, **không có zone/offset** | Giờ hẹn khách chọn trước khi xác định địa điểm |
| `OffsetDateTime` | Local date-time + UTC offset cụ thể | Timestamp client gửi có `+07:00` |
| `ZonedDateTime` | Date-time + `ZoneId` với timezone rules | Lịch hẹn theo `Europe/Berlin` |
| `Instant` | Một điểm trên trục thời gian UTC | Lưu, so sánh, audit timestamp |
| `ZoneId` | Timezone rules địa lý hoặc fixed offset | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `ZoneOffset` | Chênh lệch cố định với UTC | `+07:00`, `+01:00` |

**Không đồng nhất**:
- `LocalDateTime.of(2026,11,6,9,30)` và `Instant`: local time này chưa đủ để xác định instant.
- `ZoneId.of("Europe/Berlin")` và `ZoneOffset.ofHours(1)`: Berlin có DST; offset có thể +01:00 hoặc +02:00 tùy ngày.
- `Locale.GERMANY` và `ZoneId.of("Europe/Berlin")`: chọn locale không tự chọn zone.
- `Asia/Ho_Chi_Minh` và `+07:00`: có thể trùng offset trong thời điểm được xét nhưng một cái là zone rules, một cái là offset tĩnh.

### 9.2. Hai chuỗi khác nhau biểu diễn cùng một instant

```text
2026-11-06T09:30:00+07:00
2026-11-06T02:30:00Z
```

Hai timestamp đều tương ứng **2026-11-06T02:30:00Z**. Java:

```java
Instant first = OffsetDateTime.parse(
        "2026-11-06T09:30:00+07:00").toInstant();

Instant second = OffsetDateTime.parse(
        "2026-11-06T02:30:00Z").toInstant();

System.out.println(first.equals(second));  // true
```

Lưu ý `Z` nghĩa là UTC offset zero trong ISO timestamp. Test phải so **Instant** thay vì so raw string/`LocalDateTime` khi yêu cầu là “cùng một thời điểm”.

### 9.3. `@DateTimeFormat(iso=ISO.DATE_TIME)`

Với query parameter:

```java
@GetMapping("/instant")
public Map<String, String> instant(
        @RequestParam("at")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        OffsetDateTime at) {

    return Map.of("instant", at.toInstant().toString());
}
```

Request có thể gửi `at=2026-11-06T09:30:00%2B07:00` (URL-encode dấu cộng); hoặc `at=2026-11-06T02:30:00Z`. Kỳ vọng canonical instant giống nhau. Nếu URL không encode dấu `+` đúng, một số cơ chế query/form decoding có thể xem nó là space: lỗi xuất hiện **trước** parsing DateTimeFormat.

### 9.4. Đặt zone ở đâu?

Với một hệ thống đặt lịch, API có thể nhận:
- `local=2026-11-06T09:30:00`
- `zone=Asia/Ho_Chi_Minh`

rồi xác định instant bằng timezone rules. Cần nêu rõ zone gắn với **địa điểm/sự kiện**, không suy từ ngôn ngữ UI.

Nếu user nhập `LocalDateTime` mà không chọn zone:
- Không thể xác định chính xác instant trong hệ thống đa vùng.
- Trừ khi nghiệp vụ cố định một zone rõ ràng, hãy yêu cầu client gửi offset/zone.
- Không âm thầm gán `ZoneId.systemDefault()` của server vì khi deploy vùng khác sẽ đổi kết quả.

## 10. DST: gap và overlap phải được xử lý có chủ đích

### 10.1. DST gap — local time không tồn tại

Tại `Europe/Berlin` ngày **29/03/2026**, đồng hồ chuyển từ 02:00 sang 03:00 (đổi offset +01:00 sang +02:00). Vì vậy `2026-03-29T02:30` là **local time không tồn tại**.

Java:

```java
LocalDateTime local = LocalDateTime.of(2026, 3, 29, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

System.out.println(offsets.size()); // 0
```

Nếu dùng `local.atZone(zone)`, Java có cơ chế tự xử lý gap, có thể đẩy local time tới thời điểm hợp lệ về sau. Nhưng với business yêu cầu người dùng chọn **chính xác giờ hẹn**, cách đó có thể che lỗi nhập. Project demo sẽ **trả trạng thái GAP** thay vì tự dịch giờ.

### 10.2. DST overlap — local time xảy ra hai lần

Tại `Europe/Berlin` ngày **25/10/2026**, đồng hồ quay về. `2026-10-25T02:30` có thể tương ứng:
- `+02:00`, hoặc
- `+01:00`.

```java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");

List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

System.out.println(offsets.size()); // 2
```

Không thể xác định một instant duy nhất chỉ từ local time + ZoneId trong giờ overlap nếu không có chính sách chọn offset. Project demo sẽ trả trạng thái **OVERLAP** kèm hai offsets cho client/chính sách nghiệp vụ quyết định.

### 10.3. Đừng dùng fixed +07:00 cho mọi lịch trên thế giới

`Asia/Ho_Chi_Minh` có offset +07:00 cho các thời điểm hiện đại đang xét và không áp dụng chuyển DST hiện nay. Nhưng không được áp quy tắc này cho `Europe/Berlin`, `America/New_York` hoặc mọi timezone.

### 10.4. Thời gian “hiện tại” và test ổn định

Code dễ flaky:

```java
LocalDate today = LocalDate.now();
```

Với test, nên inject `Clock`:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-06T02:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate today = LocalDate.now(clock);
// today = 2026-11-06
```

Dùng `Clock.fixed` để không phụ thuộc giờ chạy CI. Với logic hiển thị theo người dùng, chọn zone đúng cho use case. Không gọi `TimeZone.setDefault(...)`/`Locale.setDefault(...)` trong test chạy song song nếu có thể truyền dependencies/locale tường minh, vì đó là global mutable state.

## 11. Thiết kế error contract để chẩn đoán đúng

Ta dùng một JSON envelope do ứng dụng tự thiết kế:

```json
{
  "code": "TYPE_MISMATCH",
  "issues": [
    {
      "field": "day",
      "code": "typeMismatch",
      "message": "Invalid value or format"
    }
  ]
}
```

Một lỗi Bean Validation khác:

```json
{
  "code": "VALIDATION_ERROR",
  "issues": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Vui lòng nhập tên"
    }
  ]
}
```

**Định nghĩa:**
- `code`: nhóm ổn định và không dịch theo locale, ví dụ `TYPE_MISMATCH`, `BODY_UNREADABLE`, `BINDING_ERROR`, `VALIDATION_ERROR`, `UNEXPECTED_FIELD`, `INVALID_TIME_INPUT`.
- `issues[].code`: nguyên nhân ổn định ở mức field, không phải raw exception message.
- `issues[].message`: text dành cho người dùng; được dịch khi phù hợp.
- Input sai kiểu không trả nguyên request value trong message; message đơn giản `Invalid value or format`.
- `issues[]` được sort để test deterministic.
- Không trả rejected value, full request body, stack trace, class name nội bộ hoặc SQL details.

**Điểm cần phân biệt:** `typeMismatch` của data binder không phải `@Min`/`@NotBlank`. Nếu lỗi parse xảy ra trước, validator có thể không kiểm tra được giá trị như kỳ vọng.

Trong dự án thật có thể dùng Spring `ProblemDetail`/RFC 9457, nhưng bài này chọn schema nhỏ để học viên thấy rõ mapping giữa binding/validation và response.

## 12. Một checklist chẩn đoán trước khi thay cấu hình

### 12.1. Thu thập tối thiểu bốn thứ

Ghi lại:
1. Input ở **dạng nào**: query, form, JSON, path variable?
2. Java target type và annotations: `LocalDate`/`OffsetDateTime`/`BigDecimal`/`String`, `@DateTimeFormat`, `@NumberFormat`, `@JsonFormat`?
3. Locale/charset/zone **đang được dùng ở đúng tầng**: request locale, request encoding, MessageSource, parser, business zone?
4. Kết quả xảy ra tại đâu: converter, binder, Jackson, validator, message interpolation hay serializer?

Sau đó mới sửa nguyên nhân. Thay global JVM locale/zone quá sớm có thể che một bug và tạo bug khác.

### 12.2. Phân loại bằng exception và `BindingResult`

| Exception/đầu ra | Gợi ý chẩn đoán |
| --- | --- |
| `MethodArgumentTypeMismatchException` | Query/path parameter không convert được; kiểm tra pattern và converter |
| `FieldError.isBindingFailure()==true` | Form field binder conversion lỗi, có thể nằm trong `BindingResult` |
| `HttpMessageNotReadableException` | JSON body không đọc được; Jackson parse/type/schema |
| `MethodArgumentNotValidException` | DTO validation và có thể một số binding errors tùy argument |
| `HandlerMethodValidationException` | Direct constraints trên handler parameters hoặc return (Spring MVC 6.1+) |
| `FieldError.getDefaultMessage()` sai ngôn ngữ | Kiểm tra Spring MessageSource/locale và provider interpolation |
| `DateTimeParseException` từ service | Java Time pattern/zone/offset sai hoặc input không hợp lệ |

Không đoán qua HTTP status duy nhất: nhiều lỗi trên cùng trả 400. Nếu hạ tầng `@Validated` AOP method validation trên service thì exception path khác built-in MVC method validation; bài tập trung vào query/form/JSON.

### 12.3. Log thông tin an toàn

Log nên chứa:
- Correlation/request ID.
- Tên endpoint và error category.
- Tên field **trong hợp đồng**, không phải raw field path tùy ý dài vô hạn.
- Locale từ request, charset đã xác định, formatter/pattern name và business zone nếu có.
- Bước thất bại: decoding, binding, validation, domain time-resolution.
- Không log giá trị nhạy cảm hoặc raw body mặc định.

Không dùng nguyên input người dùng làm metric label; cardinality và privacy sẽ trở thành vấn đề vận hành.

## 13. Dự án chạy được: Java 17, Spring Boot 3.5.6

Project tạo các endpoints:
- `GET /api/format/day`: bind `LocalDate` với `dd/MM/yyyy`.
- `GET /api/format/amount`: bind `BigDecimal` theo `@NumberFormat` và locale.
- `GET /api/format/instant`: bind `OffsetDateTime` rồi trả canonical `Instant`.
- `GET /api/format/zone`: kiểm tra ZoneId và DST gap/overlap cho local time.
- `POST /api/echo`: nhận JSON UTF-8, validate tên và trả message en/vi.
- `POST /api/form`: bind UTF-8 form, date/number, báo lỗi pattern/type và field ngoài allowlist.

Có đầy đủ source, resource bundles và JUnit/MockMvc tests. Không cần database/network service bên ngoài.

### 13.1. Cây thư mục

```text
locale-time-diagnostics/
├── pom.xml
├── src/main/java/demo/diagnostics/
│   ├── DiagnosticsApplication.java
│   ├── TimeDiagnostics.java
│   ├── DiagnosticForm.java
│   ├── EchoRequest.java
│   ├── DiagnosticError.java
│   ├── DiagnosticController.java
│   └── DiagnosticAdvice.java
├── src/main/resources/
│   ├── application.properties
│   ├── messages.properties
│   └── messages_vi.properties
└── src/test/java/demo/diagnostics/
    ├── DateNumberMvcTest.java
    ├── UnicodeLocaleMvcTest.java
    ├── TimeZoneMvcTest.java
    ├── FormBindingMvcTest.java
    └── TimeDiagnosticsTest.java
```

### 13.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>locale-time-diagnostics</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Giữ các dependencies do Boot quản lý; không tự thêm nhiều phiên bản Jackson, Jakarta Validation hoặc Spring Framework lệch nhau. Spring Boot 3.5.6 dùng Java 17 trở lên.

### 13.3. `application.properties`

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8

server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force=true
```

Không thêm `spring.jackson.time-zone=Asia/Ho_Chi_Minh` rồi hy vọng mọi `LocalDateTime` trở thành instant; business zone được truyền **tường minh** ở endpoint `/zone`.

### 13.4. `messages.properties`

```properties
request.name.required=Please enter a name
form.city.required=Please enter a city
form.day.required=Please select a day
form.amount.required=Please enter an amount
```

### 13.5. `messages_vi.properties`

```properties
request.name.required=Vui lòng nhập tên
form.city.required=Vui lòng nhập thành phố
form.day.required=Vui lòng chọn ngày
form.amount.required=Vui lòng nhập số tiền
```

Lưu file UTF-8. Cần có file `messages.properties` cơ sở để Boot auto-configure MessageSource theo convention khi không có message source bean riêng.

### 13.6. `DiagnosticsApplication.java`

```java
package demo.diagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }
}
```

### 13.7. `TimeDiagnostics.java`

```java
package demo.diagnostics;

import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class TimeDiagnostics {

    private TimeDiagnostics() {}

    public record Analysis(
            String status,
            String instant,
            List<String> offsets) {
    }

    public static Analysis analyze(String localRaw, String zoneRaw) {
        LocalDateTime local = LocalDateTime.parse(localRaw);
        ZoneId zone = ZoneId.of(zoneRaw);

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            return new Analysis("GAP", null, List.of());
        }

        if (valid.size() > 1) {
            return new Analysis(
                    "OVERLAP",
                    null,
                    valid.stream()
                            .map(ZoneOffset::toString)
                            .toList());
        }

        ZoneOffset offset = valid.get(0);

        return new Analysis(
                "OK",
                local.atOffset(offset).toInstant().toString(),
                List.of(offset.toString()));
    }
}
```

**Giải thích:**
- `LocalDateTime.parse` dùng ISO local date-time, ví dụ `2026-11-06T09:30:00`.
- `ZoneId.of` yêu cầu zone ID đúng; nếu sai ném `DateTimeException` (bao gồm `ZoneRulesException`).
- `getValidOffsets(local)` trả 0/1/2 offsets ở gap/normal/overlap.
- Với một offset, `local.atOffset(offset).toInstant()` cho instant xác định.
- Với gap hoặc overlap, **không tự chọn** một instant thay user.
- `status` là output hợp đồng của demo, không phải enum chuẩn của Java Time.

Vì method sử dụng timestamp và zone do caller truyền vào, nó không phụ thuộc `ZoneId.systemDefault()`/`LocalDateTime.now()`. Tests ổn định hơn khi chạy CI.

### 13.8. `DiagnosticForm.java`

```java
package demo.diagnostics;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

import java.math.BigDecimal;
import java.time.LocalDate;

public class DiagnosticForm {

    @NotBlank(message = "{form.city.required}")
    private String city;

    @NotNull(message = "{form.day.required}")
    @DateTimeFormat(pattern = "dd/MM/yyyy")
    private LocalDate day;

    @NotNull(message = "{form.amount.required}")
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public LocalDate getDay() {
        return day;
    }

    public void setDay(LocalDate day) {
        this.day = day;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

`@NotNull` xác định field bắt buộc có giá trị. `@DateTimeFormat` và `@NumberFormat` xử lý **cú pháp chuyển đổi**, không tự là Jakarta constraints. Nếu field không parse được, `WebDataBinder` ghi binding failure; nếu không có field, `@NotNull` có thể tạo constraint error.

### 13.9. `EchoRequest.java`

```java
package demo.diagnostics;

import jakarta.validation.constraints.NotBlank;

public record EchoRequest(
        @NotBlank(message = "{request.name.required}")
        String name) {
}
```

DTO JSON này không có `@JsonFormat` vì `name` là Unicode text. Với date/time JSON fields trong ứng dụng thật, chỉ dùng `@JsonFormat` theo Jackson schema phù hợp; không nhầm với `@DateTimeFormat` của query/form.

### 13.10. `DiagnosticError.java`

```java
package demo.diagnostics;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record DiagnosticError(
        String code,
        List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String message) {
    }

    public static DiagnosticError simple(String code) {
        return new DiagnosticError(code, List.of());
    }

    public static DiagnosticError one(
            String code,
            String field,
            String issueCode,
            String message) {

        return new DiagnosticError(
                code,
                List.of(new Issue(field, issueCode, message)));
    }

    public static DiagnosticError fromBindingResult(
            BindingResult bindingResult) {

        List<Issue> issues = bindingResult
                .getFieldErrors()
                .stream()
                .map(e -> new Issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.toString(e.getCode(), "invalid"),
                        e.isBindingFailure()
                                ? "Invalid value or format"
                                : Objects.toString(
                                        e.getDefaultMessage(),
                                        "Invalid value")))
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code))
                .toList();

        boolean hasBindingFailure =
                bindingResult.getFieldErrors().stream()
                        .anyMatch(FieldError::isBindingFailure);

        return new DiagnosticError(
                hasBindingFailure
                        ? "BINDING_ERROR"
                        : "VALIDATION_ERROR",
                issues);
    }
}
```

`getDefaultMessage()` được dùng cho **constraint violations** đã qua message interpolation; type-binding failures dùng câu safe cố định để không echo raw rejected values hoặc exception text. Trong production, bạn có thể map thêm `ObjectError` và dịch `typeMismatch` theo locale, nhưng giữ machine-readable `code` ổn định.

### 13.11. `DiagnosticController.java`

```java
package demo.diagnostics;

import jakarta.validation.Valid;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class DiagnosticController {

    @GetMapping("/format/day")
    public Map<String, String> day(
            @RequestParam("day")
            @DateTimeFormat(pattern = "dd/MM/yyyy")
            LocalDate day) {

        return Map.of("isoDate", day.toString());
    }

    @GetMapping("/format/amount")
    public Map<String, String> amount(
            @RequestParam("amount")
            @NumberFormat(pattern = "#,##0.00")
            BigDecimal amount) {

        return Map.of(
                "plain", amount.stripTrailingZeros().toPlainString());
    }

    @GetMapping("/format/instant")
    public Map<String, String> instant(
            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return Map.of("instant", at.toInstant().toString());
    }

    @GetMapping("/format/zone")
    public ResponseEntity<?> zone(
            @RequestParam("local") String local,
            @RequestParam("zone") String zone) {

        try {
            return ResponseEntity.ok(
                    TimeDiagnostics.analyze(local, zone));
        } catch (DateTimeException ex) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.simple("INVALID_TIME_INPUT"));
        }
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echo(
            @Valid @RequestBody EchoRequest body) {

        return Map.of("name", body.name());
    }

    @InitBinder("diagnosticForm")
    void binder(WebDataBinder binder) {
        binder.setAllowedFields("city", "day", "amount");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("diagnosticForm")
            DiagnosticForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "city", form.getCity(),
                "day", form.getDay().toString(),
                "amount", form.getAmount()
                        .stripTrailingZeros().toPlainString()));
    }
}
```

**Hợp đồng MVC của ví dụ:**
- `/format/day` chấp nhận `dd/MM/yyyy` ở query parameter.
- `/format/amount` dùng request locale để diễn giải `@NumberFormat`.
- `/format/instant` nhận timestamp có UTC offset, trả canonical Instant.
- `/format/zone` trả `GAP`, `OVERLAP` hoặc `OK`, không nhầm locale với zone.
- `/echo` test raw JSON UTF-8 + localized `@NotBlank`.
- `/form` test WebDataBinder với 3 fields, cả suppressed field và binding failures.

`@InitBinder` không được dùng để áp đặt `@DateTimeFormat` lên JSON via Jackson. `BindingResult` đứng ngay sau model attribute để controller tự xử lý lỗi.

### 13.12. `DiagnosticAdvice.java`

```java
package demo.diagnostics;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class DiagnosticAdvice extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            DiagnosticError error) {

        return new ResponseEntity<>(error, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            return reply(headers, status,
                    DiagnosticError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException m
                        ? m.getName()
                        : "input";

        return reply(headers, status,
                DiagnosticError.one(
                        "TYPE_MISMATCH",
                        field,
                        "typeMismatch",
                        "Invalid value or format"));
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.one(
                        "MISSING_PARAMETER",
                        ex.getParameterName(),
                        "required",
                        "Required parameter is missing"));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.fromBindingResult(
                        ex.getBindingResult()));
    }
}
```

Đây là exception advice đúng scope cho các lỗi được bài demo sinh ra: query type mismatch, missing parameter, JSON unreadable, Bean Validation của request DTO. Nó **không** cố “bắt hết mọi lỗi” của Spring MVC. Nếu application có direct method constraints `@Min`/`@NotBlank` trên handler parameters, cần bổ sung xử lý `HandlerMethodValidationException` theo Spring MVC 6.1+ để duy trì JSON contract.

Đừng khai báo một `@ExceptionHandler` trùng với những exception đã được `ResponseEntityExceptionHandler` đăng ký trong superclass; ưu tiên override protected method. Giữ `HttpStatusCode status` được framework truyền tới, không tự ép toàn bộ `TypeMismatchException` thành HTTP 400 vì có trường hợp lỗi conversion do cấu hình server.

## 14. MockMvc test: Locale và pattern

### 14.1. `DateNumberMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DateNumberMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void dayPatternIsExplicitDayMonthYear() throws Exception {
        mvc.perform(get("/api/format/day")
                        .param("day", "06/11/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-11-06"));
    }

    @Test
    void isoDateIsNotAcceptedByDdMmYyyyPattern()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .param("day", "2026-11-06"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("day"));
    }

    @Test
    void ambiguousDateShowsImportanceOfPattern()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .param("day", "11/06/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-06-11"));
    }

    @Test
    void datePatternWorksWithGermanLocaleToo()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .locale(Locale.GERMANY)
                        .param("day", "06/11/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-11-06"));
    }

    @Test
    void usLocaleParsesCommaGroupingDotDecimal()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.US)
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.plain")
                        .value("1234.5"));
    }

    @Test
    void germanLocaleParsesDotGroupingCommaDecimal()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.GERMANY)
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.plain")
                        .value("1234.5"));
    }

    @Test
    void missingAmountIsPresenceErrorNotParsingError()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.US))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("amount"));
    }

    @Test
    void obviouslyNonNumericAmountIsRejected()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.GERMANY)
                        .param("amount", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"));
    }
}
```

**Ý nghĩa các assertions:**
- Pattern quyết định ngày/tháng, không chỉ việc parse “thành công”.
- Fixed pattern `dd/MM/yyyy` không tự đảo vị trí theo German locale.
- `@NumberFormat` dùng dấu thập phân/grouping theo locale.
- Thiếu parameter không phải converter failure.
- Chọn một input **rõ ràng không phải số** cho test negative; không cố định behavior của ambiguous numeric strings khi parser lenient.

## 15. MockMvc test: JSON UTF-8 và thông báo đa ngữ

### 15.1. `UnicodeLocaleMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;
import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UnicodeLocaleMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void utf8JsonBytesRoundTripVietnameseName()
            throws Exception {

        byte[] body = """
                {"name":"Đà Nẵng"}
                """.getBytes(StandardCharsets.UTF_8);

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name")
                        .value("Đà Nẵng"));
    }

    @Test
    void vietnameseConstraintMessageUsesRequestLocale()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.forLanguageTag("vi-VN"))
                        .content("{\"name\":\"\"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Vui lòng nhập tên"));
    }

    @Test
    void englishConstraintMessageIsDifferent()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.ENGLISH)
                        .content("{\"name\":\"\"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Please enter a name"));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void blankTextIsInvalidRegardlessOfLocale()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.forLanguageTag("vi"))
                        .content("{\"name\":\"   \"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"));
    }
}
```

**Điểm then chốt:** Test đầu truyền **UTF-8 bytes** qua `content(byte[])`, không chỉ tạo sẵn `String` rồi gọi converter thủ công. Hai test messages chọn locale cụ thể và assert English/Vietnamese, còn `code` không thay đổi.

Nếu test localized message fail nhưng JSON Unicode round-trip pass, đó là dấu hiệu encoding của HTTP payload có thể **đúng** trong khi MessageSource/locale interpolation sai. Đừng thay charset request chỉ để sửa locale message.

## 16. MockMvc test: OffsetDateTime và DST

### 16.1. `TimeZoneMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TimeZoneMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void vietnamOffsetConvertsToUtcInstant()
            throws Exception {

        mvc.perform(get("/api/format/instant")
                        .param("at",
                                "2026-11-06T09:30:00+07:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"));
    }

    @Test
    void equivalentUtcTimestampHasSameInstant()
            throws Exception {

        mvc.perform(get("/api/format/instant")
                        .param("at",
                                "2026-11-06T02:30:00Z"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"));
    }

    @Test
    void localTimeWithVietnamZoneHasOneOffset()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00")
                        .param("zone", "Asia/Ho_Chi_Minh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"))
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"))
                .andExpect(jsonPath("$.offsets[0]")
                        .value("+07:00"));
    }

    @Test
    void berlinSpringGapIsReported()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-03-29T02:30:00")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("GAP"))
                .andExpect(jsonPath("$.offsets", hasSize(0)));
    }

    @Test
    void berlinAutumnOverlapIsReported()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-10-25T02:30:00")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OVERLAP"))
                .andExpect(jsonPath("$.offsets", hasSize(2)));
    }

    @Test
    void invalidZoneIdIsClientInputError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00")
                        .param("zone", "Not/A_Real_Zone"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_TIME_INPUT"));
    }

    @Test
    void invalidLocalDateTimeIsClientInputError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "06/11/2026 09:30")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_TIME_INPUT"));
    }

    @Test
    void missingZoneStillUsesRequiredParameterError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("zone"));
    }
}
```

Test chuyển offset dùng `.param(...)` nên đã cung cấp Java String **sau decoding**; trong HTTP thực, dấu `+` ở query cần percent-encode, ví dụ `%2B07:00`. Nếu muốn kiểm tra query byte encoding đúng qua mạng, bổ sung real-server test hoặc test URL raw riêng.

**Tại sao HTTP 200 cho GAP/OVERLAP?** Trong demo, endpoint `/zone` là một **chức năng chẩn đoán**, trả kết quả phân tích cho caller. Một API **tạo lịch hẹn** thật có thể chọn 400/422 khi local time gap/overlap chưa được giải quyết; đây là quyết định business API, không phải một status bắt buộc của Spring.

## 17. MockMvc test: form field encoding, @DateTimeFormat và @NumberFormat

### 17.1. `FormBindingMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormBindingMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form() {
        return post("/api/form")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED);
    }

    @Test
    void validFormBindsVietnameseTextAndUsNumber()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Đà Nẵng")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.city").value("Đà Nẵng"))
                .andExpect(jsonPath("$.day").value("2026-11-06"))
                .andExpect(jsonPath("$.amount").value("1234.5"));
    }

    @Test
    void validFormBindsGermanNumber()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.GERMANY)
                        .param("city", "Berlin")
                        .param("day", "06/11/2026")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount").value("1234.5"));
    }

    @Test
    void invalidDatePatternIsBindingFailure()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "2026-11-06")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("day")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void nonNumericFormValueIsBindingFailure()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "06/11/2026")
                        .param("amount", "not-money"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("amount")));
    }

    @Test
    void blankCityIsValidationError()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "   ")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void unknownFieldIsRejectedSeparately()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50")
                        .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void missingDayIsConstraintError()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }
}
```

**Cần hiểu đúng về .param(...):** `MockMvc.param("city", "Đà Nẵng")` truyền Java String vào mock request, nên chứng minh binding/validation giữ nguyên text Unicode sau khi được giải mã, nhưng **chưa** chứng minh real HTTP client, proxy hoặc servlet container phân tích percent-encoding UTF-8 đúng. Bài đã có test JSON dùng `content(byte[])` để kiểm tra bytes, và có thể bổ sung integration test thực tế cho form wire bytes nếu hệ thống nhạy về encoding.

## 18. Unit test Java Time: không phụ thuộc Spring

### 18.1. `TimeDiagnosticsTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TimeDiagnosticsTest {

    @Test
    void hoChiMinhZoneProducesExpectedUtcInstant() {
        var result = TimeDiagnostics.analyze(
                "2026-11-06T09:30:00",
                "Asia/Ho_Chi_Minh");

        assertEquals("OK", result.status());
        assertEquals("2026-11-06T02:30:00Z",
                result.instant());
        assertEquals(1, result.offsets().size());
        assertEquals("+07:00", result.offsets().get(0));
    }

    @Test
    void berlinSpringGapHasNoValidOffset() {
        var result = TimeDiagnostics.analyze(
                "2026-03-29T02:30:00",
                "Europe/Berlin");

        assertEquals("GAP", result.status());
        assertNull(result.instant());
        assertTrue(result.offsets().isEmpty());
    }

    @Test
    void berlinFallOverlapHasTwoValidOffsets() {
        var result = TimeDiagnostics.analyze(
                "2026-10-25T02:30:00",
                "Europe/Berlin");

        assertEquals("OVERLAP", result.status());
        assertNull(result.instant());
        assertEquals(2, result.offsets().size());
    }

    @Test
    void fixedClockMakesCurrentDateDeterministic() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-06T02:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(LocalDate.of(2026, 11, 6),
                LocalDate.now(clock));
    }

    @Test
    void utcAndVietnamOffsetRepresentSameInstant() {
        Instant fromVietnam = java.time.OffsetDateTime.parse(
                "2026-11-06T09:30:00+07:00").toInstant();
        Instant utc = Instant.parse(
                "2026-11-06T02:30:00Z");

        assertEquals(utc, fromVietnam);
    }
}
```

Ưu điểm của pure unit tests:
- Không cần Spring ApplicationContext.
- Chẩn đoán logic Java Time độc lập với HTTP/locale.
- Dùng các dates cụ thể để không phụ thuộc giờ hiện tại.
- Sử dụng ZoneId thật thay vì fixed offset ở các bài toán DST.

## 19. Chạy và kiểm chứng

Có năm test classes:
- `DateNumberMvcTest` kiểm tra date/amount formatting theo locale.
- `UnicodeLocaleMvcTest` kiểm tra UTF-8 JSON và bản dịch en/vi.
- `TimeZoneMvcTest` kiểm tra offset/instant và DST gap/overlap qua MVC.
- `FormBindingMvcTest` kiểm tra form binding, pattern, suppression.
- `TimeDiagnosticsTest` kiểm tra Java Time logic không qua Spring.

Chạy từ thư mục `locale-time-diagnostics`:

```bash
mvn test
```

Chạy từng nhóm:

```bash
mvn -Dtest=DateNumberMvcTest test
mvn -Dtest=UnicodeLocaleMvcTest test
mvn -Dtest=TimeZoneMvcTest test
mvn -Dtest=FormBindingMvcTest test
mvn -Dtest=TimeDiagnosticsTest test
```

Chạy server:

```bash
mvn spring-boot:run
```

Các expected JSON và assertions ở trên là **hành vi dự kiến** cho project mẫu với dependencies đúng. Chúng **chưa phải kết quả test đã chạy**; khi làm bài thực hành, xem `target/surefire-reports` và sửa theo root cause nếu có differences do framework hoặc môi trường.

### 19.1. Bảng những request chẩn đoán trọng điểm

| Request | Kết quả mong đợi |
| --- | --- |
| `GET /api/format/day?day=06/11/2026` | `2026-11-06` |
| `GET /api/format/day?day=2026-11-06` | `TYPE_MISMATCH` |
| Amount `1,234.50` + locale en-US | `1234.5` |
| Amount `1.234,50` + locale de-DE | `1234.5` |
| JSON `{"name":"Đà Nẵng"}` bằng UTF-8 bytes | Echo chính xác `Đà Nẵng` |
| JSON blank name + locale vi-VN | `Vui lòng nhập tên` |
| ISO offset `09:30+07:00` | Instant `02:30:00Z` |
| Berlin `2026-03-29T02:30` | `GAP` |
| Berlin `2026-10-25T02:30` | `OVERLAP` |
| Form `day=2026-11-06` trong pattern `dd/MM/yyyy` | `BINDING_ERROR` |
| Form có field `admin=true` | `UNEXPECTED_FIELD` |

## 20. Thử API bằng curl: lưu ý URL-encoding

### 20.1. Ngày theo pattern form

```bash
curl -i -G 'http://localhost:8080/api/format/day' \
  --data-urlencode 'day=06/11/2026'
```

Kỳ vọng:

```json
{"isoDate":"2026-11-06"}
```

### 20.2. Giá trị số theo locale

```bash
curl -i -G 'http://localhost:8080/api/format/amount' \
  -H 'Accept-Language: de-DE' \
  --data-urlencode 'amount=1.234,50'
```

Kỳ vọng:

```json
{"plain":"1234.5"}
```

Thử en-US:

```bash
curl -i -G 'http://localhost:8080/api/format/amount' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'amount=1,234.50'
```

### 20.3. Instant với dấu cộng trong offset

```bash
curl -i -G 'http://localhost:8080/api/format/instant' \
  --data-urlencode 'at=2026-11-06T09:30:00+07:00'
```

`--data-urlencode` bảo đảm dấu `+` trong `+07:00` được mã hóa đúng trong query. Kỳ vọng:

```json
{"instant":"2026-11-06T02:30:00Z"}
```

### 20.4. Chẩn đoán DST gap/overlap

```bash
curl -i -G 'http://localhost:8080/api/format/zone' \
  --data-urlencode 'local=2026-03-29T02:30:00' \
  --data-urlencode 'zone=Europe/Berlin'
```

Kỳ vọng status `GAP`, offsets rỗng. Với local `2026-10-25T02:30:00` cùng zone, kết quả `OVERLAP`, có 2 offsets.

### 20.5. UTF-8 JSON và localized error

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi-VN' \
  --data-binary '{"name":"Đà Nẵng"}'
```

Kỳ vọng:

```json
{"name":"Đà Nẵng"}
```

Với `{"name":""}` và locale vi-VN, kỳ vọng error issue có `message="Vui lòng nhập tên"`.

### 20.6. Form có ký tự Unicode

```bash
curl -i -X POST 'http://localhost:8080/api/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'city=Đà Nẵng' \
  --data-urlencode 'day=06/11/2026' \
  --data-urlencode 'amount=1,234.50'
```

Kỳ vọng `city="Đà Nẵng"`, `day="2026-11-06"` và `amount="1234.5"`. Nếu có lỗi dấu trong form nhưng JSON đúng, tập trung chẩn đoán **form decoding/Servlet request encoding**; không đổi `@DateTimeFormat` hoặc timezone.

## 21. Những lỗi chẩn đoán và cách sửa

| Lỗi/suy luận sai | Nguyên nhân chính | Cách xác minh |
| --- | --- | --- |
| “Locale tiếng Việt phải làm số thành dấu phẩy” | Locale vi có quy tắc format riêng; không đoán bằng nhãn ngôn ngữ | Test với formatter và exact locale |
| “`Accept-Language: vi` sửa lỗi UTF-8” | Charset khác locale | So HTTP bytes và decoded Strings |
| “`@JsonFormat` sửa query parameter date” | Jackson chỉ cho JSON path | Test `@RequestParam` + `@DateTimeFormat` |
| “`@DateTimeFormat` sửa JSON date field” | JSON qua Jackson | Kiểm tra `@JsonFormat`/ObjectMapper |
| “Mọi ngày ISO được @DateTimeFormat pattern=dd/MM/yyyy nhận” | Pattern là hợp đồng rõ | Assert type mismatch với input ISO |
| “Locale tự chọn Asia/Ho_Chi_Minh” | Locale không có timezone | Truyền ZoneId rõ ràng |
| “Offset +01:00 luôn là giờ Berlin” | Berlin có DST | Kiểm tra getValidOffsets ở thời điểm |
| “LocalDateTime xác định một instant” | Thiếu ZoneId/offset; gap/overlap | Dùng Instant/OffsetDateTime hoặc ZoneRules |
| “LocalDate cần cộng 7 giờ” | LocalDate không có time/zone | Chỉ convert nếu business định nghĩa start-of-day zone |
| “Cứ đổi server default timezone cho dễ” | Phụ thuộc môi trường, phá tests | Inject Clock/ZoneId |
| “Formatter parse lỗi là Jakarta Validation lỗi” | Converter/binder thất bại trước validator | Kiểm tra FieldError.isBindingFailure() |
| “Test .param Unicode là test wire charset” | Param đã là Java String | Test content bytes/real server |
| “Test chỉ status 400 là đủ” | Không xác định category/field/message | Assert stable codes và exception class khi cần |
| “Parse số sai locale chắc chắn ném exception” | Parsers có thể lenient hoặc nhận giá trị khác | Test semantic number + strict parser nếu yêu cầu |
| “`spring.jackson.time-zone` đổi mọi Java Time types” | JavaTimeModule/annotations có semantics khác nhau | Test wire JSON từng type |
| “MessageSource tự có khi chỉ có messages_vi.properties” | Boot auto-config convention thường cần base bundle | Đặt messages.properties + locale files |
| “Chuỗi lỗi có dấu = do DB” | Có nhiều boundary encoding | Truy từng bước bytes→String→response |
| “Giờ DST gap/overlap đều tự xử lý được” | Business phải chọn chính sách | Check ZoneRules.getValidOffsets |
| “Dùng `Date`/`Calendar` là giải pháp duy nhất cho timezone” | `java.time` cung cấp types rõ ràng hơn | Chọn LocalDate/OffsetDateTime/Instant đúng nghĩa |
| “Đổi JVM default locale trong test song song an toàn” | Global mutable state | MockMvc.locale / explicit Locale / Clock |

## 22. Checklist QA khi thay format/locale/timezone

1. Xác định data path: query/form `ConversionService` hay JSON Jackson.
2. Ghi rõ target Java type và annotations hiện tại.
3. Kiểm tra request locale được chọn bằng header hoặc test helper.
4. Kiểm tra language/region và precedence của LocaleResolver.
5. Kiểm tra encoding source files, request body và response content.
6. Với form, test URI-percent-encoding và character encoding thật khi cần.
7. Với JSON, test raw UTF-8 bytes qua `content(byte[])`.
8. Với messages, kiểm tra base bundle, locale-specific bundle và encoding.
9. Với `@NumberFormat`, assert **numeric meaning**, không chỉ HTTP 200.
10. Với date, assert LocalDate canonical `yyyy-MM-dd`, không chỉ parser success.
11. Với `@JsonFormat`, test JSON riêng, không suy luận từ form tests.
12. Với `@DateTimeFormat`, test query/form riêng, không suy luận từ JSON tests.
13. Nếu cần strict date validity, xác định resolver style/algorithm.
14. Với `OffsetDateTime`, test hai timestamp khác offset nhưng cùng instant.
15. Với local + zone, test normal time, DST gap, DST overlap.
16. Dùng ZoneId theo nghiệp vụ; tránh `ZoneId.systemDefault()` ở boundary.
17. Tránh `Locale.setDefault()`/`TimeZone.setDefault()` trong parallel tests.
18. Inject `Clock` để tránh tests phụ thuộc ngày/giờ hiện tại.
19. Map type mismatch sang error code ổn định, không công bố raw values.
20. Với form BindingResult, phân biệt binding failures với constraints.
21. Với Bean Validation, assert localized messages theo locale rõ ràng.
22. Khi nâng Spring Boot/Jackson/Hibernate/TZDB, chạy lại regression tests.
23. Kiểm tra browser input types (date/datetime-local/number) gửi format nào thực tế.
24. Với log, lưu safe metadata về locale/charset/pattern/zone và request ID.
25. Với API public, ghi format/zone contract trong OpenAPI và SDK docs.

## 23. Bài tập tự luyện

1. Thêm endpoint nhận `@DateTimeFormat(iso=DATE) LocalDate`, test `2026-11-06` thành công và `06/11/2026` thất bại.
2. Đổi pattern `dd/MM/yyyy` thành `MM/dd/yyyy` rồi so cùng chuỗi `06/11/2026`; giải thích sự khác biệt.
3. Dùng `ResolverStyle.STRICT` + `dd/MM/uuuu` để từ chối `31/02/2026`.
4. Tạo request de-DE có `amount=1.234,50` và en-US có `amount=1,234.50`; so semantic BigDecimal.
5. Thử text số sai locale; không assume ném exception, hãy kiểm tra toàn bộ parsed result.
6. Thêm một `@JsonFormat(pattern="dd/MM/yyyy") LocalDate` trong JSON DTO và so với query `@DateTimeFormat`.
7. Thêm XML/form endpoint chỉ cho phép UTF-8, test raw percent-encoded Vietnamese text qua real server.
8. Trong test dùng `Locale.forLanguageTag("vi-VN")` và `Locale.ENGLISH`; message phải đổi nhưng error code ổn định.
9. Thay `spring.messages.basename` thành tên bundle khác; test key missing để chẩn đoán.
10. Loại bỏ `spring.messages.encoding=UTF-8` trong một test profile và tìm hiểu behavior có còn đúng với Boot version hiện tại không.
11. Thêm timestamp `2026-11-06T09:30:00+07:00` và `2026-11-06T02:30:00Z`; xác minh equal Instant.
12. Chọn ZoneId Berlin cho `2026-03-29T02:30`, hiển thị GAP chứ không tự chọn 03:30.
13. Chọn ZoneId Berlin cho `2026-10-25T02:30`, yêu cầu client chọn offset ở overlap.
14. Thêm `Clock.fixed` vào logic kiểm tra “trước ngày hôm nay” để tests không flaky.
15. So `LocalDateTime.now(Clock.systemUTC())` với `LocalDateTime.now(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")))` tại cùng instant.
16. Bổ sung một `@NumberFormat(style=CURRENCY)` endpoint, test ký hiệu tiền và locale có/không dùng decimal comma.
17. Thêm `@Past`/`@Future` với `ClockProvider` của Jakarta Validation nếu cần quản lý current time.
18. Giả lập message bị mojibake từ một resource file sai encoding, chẩn đoán nơi bytes bị decode sai.
19. Dùng `Content-Type` sai (text/plain vào JSON endpoint) và phân biệt HTTP 415 với JSON 400.
20. Thêm correlation ID và structured safe logs ghi category, locale và zone mà không log raw request body.

**Kết luận:** Đừng dùng một thay đổi toàn cục để sửa mọi “lỗi định dạng”. **Locale** chọn ngôn ngữ/quy ước hiển thị; **charset** quyết định Unicode qua bytes; **pattern** định nghĩa cú pháp ngày/số; **time zone/offset** xác định instant và xử lý DST. Để chẩn đoán Spring MVC đúng, xác định request đi qua `ConversionService/WebDataBinder` hay Jackson, test riêng mỗi tầng và assert **ý nghĩa giá trị** sau khi parse. Dùng `Instant`/`OffsetDateTime`/`ZoneId` đúng vai trò, locale/encoding tường minh và bộ MockMvc/JUnit kiểm thử hồi quy.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — DateTimeFormat annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Spring Framework 6.2 — NumberFormat annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [Spring Framework 6.2 — MVC Locale](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html)
- [Spring Framework 6.2 — Data Binding / @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
- [Spring Boot 3.5 — Servlet Encoding](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Testing with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Java 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java 17 — ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Java 17 — DateTimeFormatter and ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Jackson — JsonFormat annotation](https://fasterxml.github.io/jackson-annotations/javadoc/2.15/com/fasterxml/jackson/annotation/JsonFormat.html)
- [Jakarta Validation 3.0 — Message Interpolation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)