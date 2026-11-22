# Spring MVC — Converter, Formatter, ConversionService và định dạng ngày giờ

## 1. Mục tiêu và bối cảnh

Khi HTTP client gửi `?quantity=3&deliveryDate=2026-12-31`, dữ liệu ban đầu là **chuỗi**. Controller có thể muốn nhận `int`, `LocalDate` hoặc một kiểu nghiệp vụ như `ProductCode`. Spring thực hiện chuyển đổi dữ liệu trong quá trình binding trước khi gọi handler.

Sau bài này, bạn có thể:

- Phân biệt `Converter<S,T>` (chuyển kiểu), `Formatter<T>` (parse/print theo `Locale`), `ConversionService` (dịch vụ điều phối) và `FormatterRegistry` (đăng ký các thành phần chuyển đổi).
- Viết, đăng ký và sử dụng converter/formatter riêng cho tham số controller và trường của `@ModelAttribute`.
- Dùng `@DateTimeFormat`, `@NumberFormat` với Java Time và số; nhận biết vấn đề định dạng theo locale, múi giờ, offset và HTML form.
- Hiểu lỗi chuyển đổi dữ liệu, điểm khác với Bean Validation, cùng cách kiểm thử lỗi và kết quả thật.
- Cấu hình Spring MVC bằng `WebMvcConfigurer#addFormatters` trong ứng dụng Spring Boot mà không thay toàn bộ cấu hình MVC.

Phạm vi là **Spring MVC Servlet stack** với Java 17+; ví dụ đầy đủ dùng Spring Boot 3.5.0 (Spring Framework 6.2). Một số cơ chế chung của Spring Core cũng được áp dụng trong các tầng khác.

## 2. Data binding cần conversion như thế nào?

Xem handler:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam int page,
        @RequestParam LocalDate date) {
    return page + " / " + date;
}
~~~

Đây là đoạn minh họa chữ ký, chưa có class/config và annotation định dạng ngày. Request:

~~~http
GET /search?page=2&date=2026-12-31
~~~

Chuỗi `"2"` phải trở thành `int 2`; chuỗi ngày phải thành `LocalDate`. Khi binding `@ModelAttribute`, việc chuyển đổi tương tự diễn ra trên các property:

~~~java
public class SearchForm {
    private Integer page;
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate date;

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }
    public LocalDate getDate() { return date; }
    public void setDate(LocalDate date) { this.date = date; }
}
~~~

Đoạn form class cần các import `java.time.LocalDate` và `org.springframework.format.annotation.DateTimeFormat`. Có thể bind bằng `@ModelAttribute SearchForm form` ở controller.

Luồng chính:

1. Spring MVC xác định controller method và tên trường cần lấy từ request.
2. `WebDataBinder` xác định kiểu đích (`int`, `LocalDate`, `ProductCode`, v.v.).
3. Hệ thống `ConversionService`/formatting tra converter hoặc parser phù hợp với kiểu và annotation.
4. Nếu chuyển đổi thành công, Spring gán giá trị vào method argument/JavaBean property hoặc constructor argument.
5. Nếu thất bại, Spring ghi binding error hoặc xử lý exception tùy handler signature; Bean Validation nếu có sẽ xử lý các constraint sau đó.

**Chuyển đổi không đồng nghĩa xác thực nghiệp vụ:** `age=17` có thể chuyển sang `int 17` thành công nhưng vi phạm `@Min(18)`; `age=abc` sai ngay ở bước chuyển kiểu.

## 3. Bản đồ các API

| API | Tác dụng | Có Locale? | Ví dụ sử dụng |
| --- | --- | --- | --- |
| `Converter<S,T>` | Chuyển từ một kiểu nguồn S sang kiểu đích T | Không có tham số `Locale` | `String → ProductCode`, `String → Enum` |
| `ConverterFactory<S,R>` | Cấp converter cho nhiều kiểu đích thuộc một họ R | Không trực tiếp | Một factory cho các kiểu enum |
| `GenericConverter` | Chuyển kiểu phức tạp có `TypeDescriptor` | Không trực tiếp; có metadata kiểu/annotation | Collection, trường generic hoặc theo annotation |
| `Formatter<T>` | `parse(String, Locale) → T` và `print(T, Locale) → String` | Có | Số, tiền, ngày/giờ theo locale |
| `ConversionService` | API thống nhất: `canConvert`, `convert` | Không truyền Locale trực tiếp trong chữ ký thông dụng | Cung cấp chuyển kiểu cho binder/service |
| `FormatterRegistry` | Đăng ký converter, formatter, annotation formatter | Không phải công cụ convert trực tiếp | `addConverter`, `addFormatter` |
| `FormattingConversionService` | `ConversionService` có khả năng đăng ký và sử dụng formatter | Formatter tra locale qua ngữ cảnh định dạng | Spring MVC form binding |

`ConversionService` là **facade**; `Converter`/`Formatter` cung cấp phần thực thi. Spring đã có sẵn nhiều quy tắc chuyển đổi thường gặp (chuỗi, số, boolean, enum, collection, ngày giờ). Chỉ viết converter mới khi kiểu hoặc quy tắc nghiệp vụ chưa được hỗ trợ đúng ý.

### 3.1. Chọn Converter hay Formatter?

- Dùng `Converter` khi muốn quy tắc **theo kiểu**, không quan tâm ngôn ngữ/locale, ví dụ mã sản phẩm `ab-123 → ProductCode("AB-123")`.
- Dùng `Formatter` khi chuỗi hiển thị và chuỗi người dùng nhập phụ thuộc locale, ví dụ `1,234.50` (en-US) so với `1.234,50` (vi-VN).
- Với date/time, ưu tiên các formatter có sẵn và `@DateTimeFormat` thay vì tự viết parser nếu định dạng đủ chuẩn.
- Không viết lại `String → Integer` hay `String → LocalDate` khi cấu hình mặc định hoặc annotation đã đáp ứng.

## 4. Converter<S,T> — chuyển kiểu đơn giản

Khai báo giao diện (tóm lược):

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Ví dụ mã sản phẩm phải có ba chữ cái và ba chữ số, không phụ thuộc locale:

~~~java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{3}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Product code must match AAA-123");
        }
        return new ProductCode(normalized);
    }
}
~~~

Kiểu đích (Java 17 record):

~~~java
package demo;

public record ProductCode(String value) {
}
~~~

- `source="ab-123"` → `ProductCode("AB-123")`.
- `source="a-123"` → converter ném `IllegalArgumentException`.
- Spring thường gọi converter sau khi xác định giá trị nguồn; quy tắc API `Converter` bảo đảm tham số `source` trong mỗi lời gọi không null.
- Converter được dùng lại giữa nhiều request, vì vậy nên viết **stateless, thread-safe**; `Locale.ROOT` tránh xử lý uppercase phụ thuộc locale của máy chủ.

Một converter hỗ trợ `String → ProductCode`; nó **không** tự đổi kiểu ngược `ProductCode → String` theo cùng quy tắc. Nếu cần hai hướng trong ngữ cảnh thuần kiểu, đăng ký thêm converter ngược; nếu cần parse/print theo locale, xem `Formatter`.

### 4.1. ConverterFactory và GenericConverter dùng khi nào?

`ConverterFactory<S,R>` tạo converter cho các subtype trong cùng họ đích, ví dụ một factory xử lý các enum thay vì viết converter cho từng enum. Spring đã có cơ chế enum phổ biến, nên thường không phải tự làm.

`GenericConverter` có chữ ký khái quát:

~~~java
Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
~~~

Các `TypeDescriptor` nêu kiểu thật, thông tin generic, metadata của field hoặc annotation; hữu ích khi cách chuyển đổi phụ thuộc cấu trúc như `List<String> → List<Integer>`. Phức tạp hơn `Converter<S,T>`; chỉ dùng khi cần metadata đó. `ConditionalGenericConverter` còn có thể giới hạn việc áp dụng bằng điều kiện `matches(sourceType, targetType)`.

## 5. ConversionService — sử dụng và đăng ký

Giao diện chính:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(Object source, TypeDescriptor sourceType, TypeDescriptor targetType);
~~~

Ví dụ độc lập ở Spring Core (cần các thư viện Spring trong classpath):

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversion = new DefaultConversionService();
conversion.addConverter(new ProductCodeConverter());

System.out.println(conversion.canConvert(String.class, ProductCode.class));
ProductCode code = conversion.convert("ab-123", ProductCode.class);
System.out.println(code.value());
~~~

Kết quả in ra:

~~~text
true
AB-123
~~~

Đây là đoạn chạy trong ngữ cảnh đã khai báo `ProductCodeConverter` và `ProductCode`, không phải một file Java độc lập chỉ chứa các dòng trên.

`canConvert` chỉ xác nhận có đường chuyển đổi phù hợp theo kiểu; **không bảo đảm** giá trị cụ thể hợp lệ. `canConvert(String.class, ProductCode.class) == true` nhưng chuỗi `"123"` vẫn làm converter báo lỗi.

Nếu làm việc với `List<String> → List<Integer>` trong code Java, chỉ chỉ định `List.class` sẽ thiếu generic element type. Hãy dùng `TypeDescriptor`:

~~~java
import java.util.List;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
Object converted = service.convert(
    List.of("10", "20"),
    TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class)),
    TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class)));
System.out.println(converted);
~~~

Output:

~~~text
[10, 20]
~~~

Trong Spring MVC, conversion được thực hiện tự động khi bind HTTP request. **Không mặc nhiên cho rằng một `ConversionService` bean do bạn tự tạo luôn là chính instance mà MVC dùng**; hãy đăng ký converter/formatter trong cấu hình MVC được hỗ trợ (mục 7) khi mục đích là chuyển đối số controller.

## 6. Formatter<T> — parse và print theo Locale

Giao diện:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Hai thao tác:

~~~java
String print(T value, Locale locale);
T parse(String text, Locale locale) throws ParseException;
~~~

`parse` đọc giá trị từ client vào đối tượng Java, còn `print` chuyển đối tượng thành chuỗi hiển thị cho client. Hai thao tác nên thống nhất nhau với cùng locale để người dùng có thể nhập lại giá trị vừa được hiển thị. `Formatter` có thể dùng trong MVC form binding, view rendering, hoặc khi gọi từ code sau khi được đăng ký.

Ví dụ cùng giá trị số `1234.50`:

| Locale | Chuỗi thường dùng | Ý nghĩa |
| --- | --- | --- |
| `en-US` | `1,234.50` | Dấu phẩy phân nhóm; dấu chấm thập phân |
| `vi-VN` | `1.234,50` | Dấu chấm phân nhóm; dấu phẩy thập phân |

Đừng tự viết `replace(",", ".")` để xử lý mọi locale: cách này dễ biến `1,234.50` thành dữ liệu không hợp lệ hoặc diễn giải nhầm nghìn/thập phân.

`java.text.NumberFormat` và `DecimalFormat` có thể biểu diễn quy tắc theo locale, nhưng **các formatter kiểu này không an toàn khi chia sẻ instance mutable giữa thread**. Tạo `DecimalFormat` mới trong từng lời gọi `parse`/`print` hoặc thiết kế cơ chế an toàn khác.

## 7. Đăng ký Converter và Formatter trong Spring MVC

Với Spring Boot và Java config:

~~~java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    private final AmountFormatter amountFormatter;

    public WebConversionConfig(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(amountFormatter);
    }
}
~~~

Các import tương ứng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Lớp ví dụ giả định `AmountFormatter` được đăng ký làm Spring bean (xem dự án đầy đủ ở mục 10). `addFormatters` là cách Spring MVC đề xuất để bổ sung converter/formatter mà vẫn dùng các mặc định cần thiết. Với Spring Boot MVC, thông thường **không cần `@EnableWebMvc`**; thêm nó có thể làm mất những cấu hình MVC tự động hữu ích do Boot cung cấp.

`FormatterRegistry` kế thừa khả năng đăng ký converter; các lời gọi `registry.addConverter(...)` và `registry.addFormatter(...)` góp các quy tắc vào conversion system dành cho MVC. Không nên vô tình đăng ký hai chiến lược cạnh tranh cho cùng kiểu nguồn/đích nếu không kiểm soát precedence.

### 7.1. Cấu hình tại controller bằng @InitBinder

Khi quy tắc đặc thù chỉ áp dụng một model/controller, có thể cấu hình binder:

~~~java
@InitBinder("filter")
public void bindFilter(WebDataBinder binder) {
    binder.addCustomFormatter(new CustomFilterFormatter());
}
~~~

Đây là đoạn minh họa (cần class `CustomFilterFormatter` và đầy đủ import). `@InitBinder` có thể đăng ký formatter/converter hay editor tùy API và phạm vi. Nếu kiểu dùng phổ biến khắp MVC, `WebMvcConfigurer#addFormatters` thường rõ và dễ tái sử dụng hơn.

Không cần dùng `PropertyEditor` cho code mới chỉ để chuyển đổi kiểu thông thường: hệ `ConversionService` và `Formatter` có API mạnh kiểu, dễ cấu hình. Nếu dùng `PropertyEditor` cũ, chú ý trạng thái và phạm vi tạo instance.

## 8. @DateTimeFormat với Java Time

Các kiểu java.time phổ biến:

| Kiểu | Có gì? | Dùng khi |
| --- | --- | --- |
| `LocalDate` | Ngày; không có giờ/múi giờ | Ngày sinh, ngày giao hàng |
| `LocalTime` | Giờ trong ngày; không có ngày/múi giờ | Giờ mở cửa |
| `LocalDateTime` | Ngày + giờ nhưng **không** có offset/zone | Giờ hẹn tại một địa điểm với timezone đã quy ước riêng |
| `OffsetDateTime` | Ngày + giờ + offset UTC (ví dụ +07:00) | API cần giữ offset của client |
| `ZonedDateTime` | Ngày + giờ + vùng thời gian có rule (ví dụ Asia/Ho_Chi_Minh) | Lịch hẹn gắn với timezone địa phương |
| `Instant` | Một thời điểm UTC trên timeline | Log, thời điểm tạo/cập nhật, giao tiếp giữa hệ thống |
| `Duration` / `Period` | Khoảng thời gian / khoảng ngày tháng | Thời lượng và phép tính thời gian, không phải ngày hẹn |

`LocalDateTime` không tự mang offset; không được suy đoán `2026-12-31T09:30` là UTC hay Việt Nam khi chưa có quy ước. Offset `+07:00` không phải một timezone có quy tắc DST lịch sử/tương lai.

### 8.1. Định dạng ISO rõ ràng

~~~java
@GetMapping("/events")
public String events(
        @RequestParam("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day,
        @RequestParam("at")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        OffsetDateTime at) {
    return day + " | " + at;
}
~~~

Các import cần thiết:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
~~~

Dữ liệu tương ứng:

~~~text
/events?day=2026-12-31&at=2026-12-31T09:30:00.000%2B07:00
~~~

Lưu ý ký tự `+` phải được URL-encode thành `%2B` trong query. Nếu viết trực tiếp `+07:00` trong URL form-encoding, dấu `+` có thể được giải mã thành dấu cách và gây lỗi parse.

`@DateTimeFormat` dùng trên **field hoặc method parameter**, ví dụ:

~~~java
public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    // Getter và setter...
}
~~~

Nếu client gửi JSON body và controller dùng `@RequestBody`, JSON được xử lý bởi HTTP message converter (thường Jackson). **`@DateTimeFormat` dành cho cơ chế formatting/binding của Spring**, không phải cách duy nhất hay mặc nhiên có hiệu lực để tùy biến định dạng JSON. Với JSON, xem cấu hình Jackson và `@JsonFormat` khi cần.

### 8.2. Pattern, ISO, style và fallbackPatterns

~~~java
@DateTimeFormat(pattern = "dd/MM/uuuu")
private LocalDate visitDate;
~~~

Với Java Time, chuỗi dự kiến là `31/12/2026`. Chữ `M` biểu thị **tháng**, còn `m` biểu thị **phút**. `HH` là giờ 0–23; `hh` là giờ 1–12, thường cần a.m./p.m. Ký hiệu pattern có chi tiết khác nhau giữa `java.time.format.DateTimeFormatter` và legacy `java.text.SimpleDateFormat`; đừng sao chép pattern tùy tiện giữa hai hệ.

Ba thuộc tính chính của `@DateTimeFormat`:

- `iso = DateTimeFormat.ISO.DATE`, `ISO.TIME` hoặc `ISO.DATE_TIME`: ưu tiên cho API cần định dạng tiêu chuẩn rõ ràng.
- `pattern = "..."`: dùng một cấu trúc do ứng dụng kiểm soát, ví dụ `dd/MM/uuuu` cho form ngày sử dụng `LocalDate`.
- `style = "..."`: dựa vào phong cách ngày/giờ theo locale; phù hợp UI nhưng biểu diễn có thể khác giữa môi trường/JDK.

Dùng **một quy tắc chính rõ ràng**; tránh khai báo `pattern`, `iso` và `style` trái nhau. Từ Spring 5.3.5, `fallbackPatterns` cho phép chỉ định thêm những pattern chấp nhận khi phân tích dữ liệu nếu pattern chính không khớp, ví dụ (minh họa, cân nhắc trước khi nới input contract):

~~~java
@DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"dd/MM/uuuu"})
private LocalDate date;
~~~

Fallback cho phép parse thêm định dạng cũ, nhưng làm API chấp nhận nhiều chuỗi. Đối với đầu vào máy với máy, một chuẩn ISO nhất quán thường tốt hơn. Formatting dựa trên style chịu ảnh hưởng locale và JDK/CLDR; không dùng làm định dạng lưu trữ hoặc hợp đồng API ổn định.

### 8.3. HTML input date/datetime-local

~~~html
<input type="date" name="startDate">
<input type="datetime-local" name="appointment">
~~~

- Input `type="date"` thường gửi `yyyy-MM-dd` dù browser có thể hiển thị ngày theo cách địa phương.
- Input `type="datetime-local"` gửi ngày + giờ địa phương, **không kèm timezone**. Phù hợp `LocalDateTime` nhưng server phải có quy tắc riêng để xác định timezone nếu cần tạo `Instant`.
- Chọn `@DateTimeFormat(iso = DATE)` cho `LocalDate` nhận từ input date; với giờ địa phương, chọn `LocalDateTime` và ISO phù hợp; nếu cần thời điểm tuyệt đối, nhận offset/zone hoặc thông tin timezone bổ sung.

Nếu muốn cấu hình ISO mặc định cho Java Time trong MVC (không phải mọi endpoint phải dùng annotation):

~~~java
@Configuration
public class IsoDateMvcConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Imports thêm: `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`. Trong ví dụ cấu hình này, đăng ký ISO ở mức MVC; không cần ghép trực tiếp class vào project mục 10 vì các trường ở đó đã được chú thích format cụ thể.

### 8.4. Múi giờ và xử lý sai lệch

Ví dụ `2026-12-31T09:30:00+07:00` là cùng thời điểm với `2026-12-31T02:30:00Z`. Tuy vậy, `2026-12-31T09:30` (`LocalDateTime`) **chưa xác định một Instant duy nhất** khi thiếu offset/zone.

Với ngày thuần `LocalDate` (ngày sinh/ngày giao hàng), không tự ép thành `Instant` nếu nghiệp vụ không cần giờ; timezone conversion có thể vô tình đổi ngày. Với lịch hẹn, lưu quy tắc timezone và quyết định rõ cách xử lý giờ trùng/không tồn tại do DST ở vùng khác.

## 9. @NumberFormat và Locale

`@NumberFormat` hỗ trợ format/parse giá trị số theo kiểu và locale:

~~~java
public class PricingForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal price;

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
~~~

Cần import:

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;
~~~

`pattern` của định dạng số được diễn giải trong bối cảnh locale. Tên pattern `#,##0.00` mô tả vị trí nhóm, số chữ số thập phân; dấu nhóm và dấu thập phân **được biểu diễn khác nhau** theo locale. Có thể dùng `@NumberFormat(style = NumberFormat.Style.NUMBER)` hoặc `Style.CURRENCY` khi phù hợp với kiểu dữ liệu và UX.

Cẩn thận: số tiền không nên lưu trữ/tính toán bằng `double` khi độ chính xác thập phân là yêu cầu nghiệp vụ; `BigDecimal` thường phù hợp hơn. Formatter phục vụ giao diện không tự định nghĩa quy tắc làm tròn, loại tiền, hay validation của nghiệp vụ. Không dùng dấu nhóm từ locale UI như giao thức API nội bộ nếu có thể truyền số thuần chuẩn (ví dụ JSON numeric hoặc decimal string có hợp đồng cố định).

## 10. Dự án chạy được: custom Converter + Formatter + ngày giờ

Ví dụ kết hợp cả bốn khái niệm với Spring MVC. Một endpoint nhận query parameters:
`code=ab-123` (custom `Converter`), `amount=1,234.50` (custom `Formatter` theo `Locale`), `deliveryDate=2026-12-31` và `meetingAt=2026-12-31T09:30:00.000+07:00` (`@DateTimeFormat`).

Sơ đồ:

~~~text
conversion-demo/
├── pom.xml
├── src/main/java/demo/
│   ├── ConversionDemoApplication.java
│   ├── ProductCode.java
│   ├── ProductCodeConverter.java
│   ├── Amount.java
│   ├── AmountFormatter.java
│   ├── WebConversionConfig.java
│   └── QuoteController.java
└── src/test/java/demo/
    └── QuoteControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

### 10.2. ConversionDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
~~~

### 10.3. ProductCode.java

~~~java
package demo;

public record ProductCode(String value) {
}
~~~

### 10.4. ProductCodeConverter.java

~~~java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{3}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Product code must match AAA-123");
        }
        return new ProductCode(normalized);
    }
}
~~~

### 10.5. Amount.java

~~~java
package demo;

import java.math.BigDecimal;

public record Amount(BigDecimal value) {
}
~~~

### 10.6. AmountFormatter.java

~~~java
package demo;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

@Component
public final class AmountFormatter implements Formatter<Amount> {

    @Override
    public Amount parse(String text, Locale locale) throws ParseException {
        DecimalFormat format = decimalFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null || position.getIndex() != text.length()) {
            int at = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();
            throw new ParseException("Invalid localized amount", at);
        }

        return new Amount((BigDecimal) parsed);
    }

    @Override
    public String print(Amount amount, Locale locale) {
        return decimalFormat(locale).format(amount.value());
    }

    private DecimalFormat decimalFormat(Locale locale) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setParseBigDecimal(true);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        return format;
    }
}
~~~

Giải thích:

- `parse` nhận đúng locale của request trong cơ chế MVC; nó tạo `DecimalFormat` riêng cho từng lời gọi nên không chia sẻ formatter mutable giữa thread.
- `setParseBigDecimal(true)` giúp nhận số dưới dạng `BigDecimal`, tránh chuyển qua `double`.
- `ParsePosition` cho phép từ chối chuỗi không parse hết; với dữ liệu tiền thật, còn cần kiểm tra tiền tệ, scale, khoảng giá trị và ngữ pháp chặt hơn.
- `print` dùng cùng quy tắc locale và cố định **hai chữ số thập phân** khi hiển thị.
- `@Component` giúp MVC configuration và controller dùng chung bean không trạng thái. Bean chỉ giữ code và không giữ instance `DecimalFormat` chung.

### 10.7. WebConversionConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    private final AmountFormatter amountFormatter;

    public WebConversionConfig(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(amountFormatter);
    }
}
~~~

Nhờ đăng ký này, Spring MVC biết cách nhận `ProductCode` và `Amount`. Các kiểu ngày ở ví dụ sử dụng formatter mặc định với `@DateTimeFormat`.

### 10.8. QuoteController.java

~~~java
package demo;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class QuoteController {
    private final AmountFormatter amountFormatter;

    public QuoteController(AmountFormatter amountFormatter) {
        this.amountFormatter = amountFormatter;
    }

    @GetMapping("/quote")
    public Map<String, String> quote(
            @RequestParam("code") ProductCode code,
            @RequestParam("amount") Amount amount,
            @RequestParam("deliveryDate")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate deliveryDate,
            @RequestParam("meetingAt")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime meetingAt,
            Locale locale) {

        Map<String, String> response = new LinkedHashMap<>();
        response.put("code", code.value());
        response.put("amount", amount.value().toPlainString());
        response.put("formattedAmount", amountFormatter.print(amount, locale));
        response.put("deliveryDate", deliveryDate.toString());
        response.put("meetingAt", meetingAt.toString());
        response.put("locale", locale.toLanguageTag());
        return response;
    }
}
~~~

Chữ ký handler cho thấy các bước parse **đã diễn ra trước khi vào method body**. `Locale` là argument MVC có thể resolve từ request; trong cấu hình MVC mặc định dựa trên `Accept-Language`. Thao tác `amountFormatter.print(...)` ở đây được gọi tường minh để quan sát chiều hiển thị; trong view MVC, cơ chế formatter có thể được dùng khi kết xuất field.

### 10.9. Chạy và quan sát

Tại thư mục `conversion-demo` có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Gửi giá trị theo locale Mỹ (`--data-urlencode` tự encode dấu `+`, dấu phẩy, dấu chấm và phần còn lại của tham số):

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'code=ab-123' \
  --data-urlencode 'amount=1,234.50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

HTTP **200 OK**, response body tương đương (JSON object có thể có thứ tự khác nếu cách serialize thay đổi):

~~~json
{
  "code": "AB-123",
  "amount": "1234.50",
  "formattedAmount": "1,234.50",
  "deliveryDate": "2026-12-31",
  "meetingAt": "2026-12-31T09:30+07:00",
  "locale": "en-US"
}
~~~

`OffsetDateTime.toString()` có thể rút gọn phần giây `:00` khi bằng 0; không nên so sánh với nguyên văn chuỗi đầu vào nếu hai cách biểu diễn cùng thời điểm.

Thử giá trị theo locale Việt Nam:

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: vi-VN' \
  --data-urlencode 'code=abc-123' \
  --data-urlencode 'amount=1.234,50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

Hai trường chính trong JSON sẽ biểu diễn giá trị tương đương:

~~~json
{
  "amount": "1234.50",
  "formattedAmount": "1.234,50"
}
~~~

Các trường khác vẫn có trong response; đoạn JSON rút gọn ở đây chỉ minh họa hai field số. Hành vi ký hiệu nhóm/thập phân dựa trên dữ liệu locale của Java runtime; ví dụ này dùng dữ liệu locale chuẩn thông dụng.

Sai mã sản phẩm:

~~~bash
curl -i -G 'http://localhost:8080/api/quote' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'code=wrong' \
  --data-urlencode 'amount=1,234.50' \
  --data-urlencode 'deliveryDate=2026-12-31' \
  --data-urlencode 'meetingAt=2026-12-31T09:30:00.000+07:00'
~~~

Spring MVC không thể chuyển `"wrong"` thành `ProductCode` nên request thông thường trả **400 Bad Request**; handler `quote` không chạy. Tương tự, ngày `deliveryDate=31/12/2026` không khớp ISO.DATE; chuỗi `amount=abc` không phù hợp với `AmountFormatter`. Nội dung JSON lỗi cụ thể tùy cấu hình Spring Boot và xử lý exception, vì vậy không dựa vào message mặc định ổn định.

Trong Windows PowerShell, dùng `curl.exe` và viết lệnh trên một dòng hoặc thay dấu nối dòng kiểu Bash `\` bằng cú pháp PowerShell phù hợp.

### 10.10. Test HTTP binding bằng MockMvc

File `src/test/java/demo/QuoteControllerTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void acceptsEnglishLocale() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "ab-123")
                .param("amount", "1,234.50")
                .param("deliveryDate", "2026-12-31")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("AB-123"))
            .andExpect(jsonPath("$.amount").value("1234.50"))
            .andExpect(jsonPath("$.formattedAmount").value("1,234.50"))
            .andExpect(jsonPath("$.deliveryDate").value("2026-12-31"))
            .andExpect(jsonPath("$.locale").value("en-US"));
    }

    @Test
    void rejectsInvalidProductCode() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "bad")
                .param("amount", "1,234.50")
                .param("deliveryDate", "2026-12-31")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidDate() throws Exception {
        mvc.perform(get("/api/quote")
                .header("Accept-Language", "en-US")
                .param("code", "abc-123")
                .param("amount", "1,234.50")
                .param("deliveryDate", "31/12/2026")
                .param("meetingAt", "2026-12-31T09:30:00.000+07:00"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Ba bài test kiểm tra **HTTP status và giá trị binding**; đây là kiểm thử nghiệp vụ của ứng dụng ví dụ, không phải kiểm thử chỉ đối chiếu nội dung phương thức converter. Khi test thất bại, nên xem cause của type conversion, config MVC và locale resolver trước khi thay đổi chuỗi expected một cách tùy tiện.

## 11. Conversion lỗi được báo ở đâu?

| Ngữ cảnh | Ví dụ lỗi | Đường xử lý thông thường |
| --- | --- | --- |
| `@RequestParam int quantity` | `quantity=abc` | Spring MVC ném exception không chuyển được argument, thường trả HTTP 400 |
| `@RequestParam ProductCode code` | `code=bad` | Converter ném `IllegalArgumentException`; quy trình argument binding thường trả HTTP 400 |
| `@ModelAttribute FormDto form` | `price=abc` trong field số | Lỗi binding có thể được lưu trong `BindingResult` nếu handler khai báo đúng |
| `@Valid @ModelAttribute FormDto` | `age=17` với `@Min(18)` | Đó là validation error, khác type mismatch |
| `@DateTimeFormat(iso=DATE)` | `31/12/2026` | Parse không khớp định dạng; lỗi binding |
| `@RequestBody JsonDto` | JSON ngày không hợp lệ | Jackson/HTTP message converter, không nhất thiết dùng Spring Formatter như form binding |

Ví dụ với form binding:

~~~java
@PostMapping("/submit")
public String submit(@Valid @ModelAttribute("form") FormDto form,
                     BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "form";
    }
    return "success";
}
~~~

Đây là mẫu chữ ký dành cho ứng dụng MVC với views và class `FormDto`, không phải endpoint của dự án mục 10. `BindingResult` phải ngay sau model attribute mà nó xử lý. `BindingResult#getFieldErrors()` thường chứa lỗi `typeMismatch` khi không chuyển đổi được. Đừng dùng `@Valid` thay cho converter hoặc xem converter thay cho validation: chúng giải quyết các bước khác nhau.

## 12. Các lỗi triển khai thường gặp

1. **Tạo converter nhưng chưa đăng ký đúng registry MVC.** `new ProductCodeConverter()` trong service không làm controller tự biết converter. Đăng ký bằng `WebMvcConfigurer#addFormatters` (hoặc cơ chế tích hợp phù hợp).
2. **Dùng Converter khi cần Locale.** `Converter<String,Amount>` không nhận Locale trực tiếp; dùng `Formatter<Amount>` khi format của người dùng theo vùng.
3. **Chia sẻ `SimpleDateFormat`/`DecimalFormat` mutable trong singleton.** Những object này thường không thread-safe; nên tạo từng lần hoặc dùng `DateTimeFormatter` immutable cho Java Time.
4. **Nhầm `MM` với `mm`**, `HH` với `hh`, `yyyy` với `uuuu` trong Java Time, hoặc quên escape literal theo đúng pattern syntax.
5. **Dùng `LocalDateTime` như thời điểm UTC.** Cần offset/zone để ra thời điểm toàn cục; nếu dữ liệu có offset nên giữ `OffsetDateTime` hoặc chuyển rõ sang `Instant`.
6. **Quên mã hóa `+` trong query.** Khi gửi offset `+07:00`, sử dụng `--data-urlencode` hoặc `%2B07:00`.
7. **Giả định Locale client luôn giống Locale máy chủ.** Kiểm tra locale resolver, header `Accept-Language` hoặc giao diện chọn ngôn ngữ và giới hạn locale mà hệ thống chấp nhận.
8. **Gửi JSON tới controller nhưng chỉ đặt `@DateTimeFormat`.** JSON body tuân theo Jackson/message converters; định dạng request params/form fields thuộc MVC conversion/formatting.
9. **Dùng style locale làm chuẩn lưu trữ.** Format mặc định có thể thay đổi theo JDK/CLDR/locale; dùng ISO hoặc pattern cố định cho hợp đồng API.
10. **Nhầm type conversion với validation.** `BigDecimal` parse thành công không có nghĩa tiền ≥ 0 hoặc hợp lệ với đơn vị tiền.
11. **Để formatter âm thầm bỏ qua ký tự dư.** Khi tự parse, cần kiểm tra parser đã dùng hết toàn bộ input.
12. **Tạo `ConversionService` mới rồi nghĩ MVC đang dùng chính instance đó.** Cần phân biệt conversion service cho application/service layer và hệ conversion/formatting đang gắn với MVC data binder.

## 13. Bài tập tự luyện

**Bài 1 — Converter:** Tạo `Converter<String, OrderId>` nhận `ORD-12345`, chuẩn hóa uppercase, từ chối chuỗi không hợp lệ. Đăng ký bằng `addFormatters` và thử `@RequestParam OrderId orderId`.

**Bài 2 — Formatter:** Viết `Formatter<Area>` gồm `BigDecimal squareMeters`. Với `en-US` chấp nhận `1,234.50`, với `vi-VN` chấp nhận `1.234,50`. Dùng `parse` và `print`; kiểm tra dữ liệu dư sau số.

**Bài 3 — Date:** Tạo `BookingForm` có `LocalDate startDate` được chú thích `@DateTimeFormat(iso=DATE)`. Dự đoán điều gì xảy ra với `2026-02-28`, `2026-02-30`, `28/02/2026`; không nhầm lỗi ngày không tồn tại và lỗi format.

**Bài 4 — Timezone:** Giải thích vì sao `2026-12-31T09:30` chưa xác định một `Instant` duy nhất. Chuyển `2026-12-31T09:30+07:00` sang UTC (kết quả: `2026-12-31T02:30Z`).

**Bài 5 — Debug:** Có `@RequestParam Price price`, client gửi `price=1,234.50`, app dùng locale `vi-VN` và báo lỗi. Hãy kiểm tra loại formatter, locale resolver, chuỗi gửi, việc đăng ký converter/formatter và dữ liệu test; tránh sửa bằng thay ký tự không có quy tắc.

**Bài 6 — Phân biệt đường xử lý:** Viết một endpoint GET nhận `@RequestParam @DateTimeFormat LocalDate` và một endpoint POST nhận JSON có trường `LocalDate`. So sánh nơi cấu hình định dạng và lỗi parse của hai endpoint.

## 14. Ghi nhớ

- `Converter` giải quyết quy tắc chuyển **kiểu**; `Formatter` giải quyết parse/print theo **Locale**.
- `ConversionService` điều phối chuyển đổi; `FormattingConversionService` kết hợp các formatter; `FormatterRegistry` giúp đăng ký.
- `WebMvcConfigurer#addFormatters` tích hợp custom conversion cho Spring MVC; `@DateTimeFormat`/`@NumberFormat` áp dụng cho field hoặc method parameter.
- Chuẩn ngày giờ cần phân biệt **ngày**, **giờ địa phương**, **offset**, **timezone** và **instant**.
- Xử lý lỗi binding cùng Bean Validation và định nghĩa hợp đồng format rõ ràng cho client.

## 15. Tài liệu Spring Framework

- [Spring Core — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html): Converter, ConverterFactory, GenericConverter, ConversionService, TypeDescriptor.
- [Spring Core — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html): Formatter, Printer, Parser, AnnotationFormatterFactory, registry.
- [Spring MVC — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): đăng ký qua WebMvcConfigurer, formatters mặc định, cấu hình ISO cho form.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding và chuyển kiểu đối số controller.
- [Spring API — DateTimeFormat](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html): iso, pattern, style, fallbackPatterns.
