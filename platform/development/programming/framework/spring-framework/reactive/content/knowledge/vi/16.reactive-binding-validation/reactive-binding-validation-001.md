# Chuyển đổi chuỗi tham số bằng `Converter` và `Formatter` trong Spring

## 1. Vì sao request cần chuyển đổi kiểu?

HTTP truyền dữ liệu qua URL, header, cookie hoặc form dưới dạng văn bản. Nhưng Java controller thường cần nhận kiểu dữ liệu rõ ràng: `Long`, `UUID`, `LocalDate`, enum hoặc một value object của nghiệp vụ.

Ví dụ client gọi:

```text
GET /orders?status=paid&from=15%2F03%2F2025
```

Trong controller, ta muốn nhận `OrderStatus` và `LocalDate`, không phải tự đọc hai chuỗi rồi parse trong từng method:

```java
@GetMapping("/orders")
Mono<OrderSummary> search(
        @RequestParam("status") OrderStatus status,
        @RequestParam("from") LocalDate from) {
    // Spring chuyển String thành kiểu đích trước khi gọi method.
}
```

Spring có hệ thống **type conversion** để chuyển một kiểu Java sang kiểu khác và hệ thống **formatting** để parse/print giá trị theo định dạng, đặc biệt có xét `Locale`.

Hai SPI quan trọng:

- **`Converter<S, T>`**: chuyển một đối tượng kiểu nguồn `S` thành kiểu đích `T`. Thích hợp cho chuyển đổi kiểu thuần túy, không phụ thuộc ngôn ngữ hoặc cách hiển thị.
- **`Formatter<T>`**: chuyển văn bản thành object và in object thành văn bản. Formatter có cả chiều parse và print, nhận `Locale` của người dùng để xử lý ngày, số và nội dung hiển thị.

Trong Spring WebFlux, khi một tham số controller nhận dữ liệu dạng chuỗi nhưng khai báo kiểu không phải `String`, framework tự áp dụng conversion service đã cấu hình. Vì vậy `@RequestParam`, `@PathVariable`, `@RequestHeader` và `@CookieValue` có thể nhận kiểu đích trực tiếp.

## 2. Phân biệt `Converter` và `Formatter`

| Tiêu chí | `Converter<S, T>` | `Formatter<T>` |
|---|---|---|
| Mục đích | Chuyển đổi kiểu Java | Parse/print object dưới dạng text |
| Chiều chuyển đổi | `S` → `T` | String → `T` và `T` → String |
| Locale | Không nhận `Locale` | Nhận `Locale` ở cả `parse` và `print` |
| Phạm vi điển hình | String → enum, ID → value object, entity → DTO | Chuỗi ngày/số theo locale, dữ liệu nhập từ form |
| API | `convert(S source)` | `parse(String, Locale)` và `print(T, Locale)` |
| Khi nên chọn | Quy tắc chuyển đổi không phụ thuộc cách trình bày | Cần định dạng nhập/xuất cho người dùng |

Ví dụ:

- Chuỗi `"paid"` thành `OrderStatus.PAID`: dùng `Converter<String, OrderStatus>`.
- Chuỗi `"15/03/2025"` thành `LocalDate` và in lại theo định dạng ngày của người dùng: dùng `Formatter<LocalDate>`.
- Chuỗi `"42"` thành `Integer`: Spring đã có converter mặc định, không cần tự viết.
- Số tiền cần parse/print với dấu thập phân và ký hiệu theo quốc gia: thường dùng formatter hoặc API tiền tệ phù hợp.

**Không nên dùng `Formatter` cho mọi phép chuyển đổi.** Nếu chỉ cần biến đổi kiểu và không cần biểu diễn theo locale, `Converter` ngắn gọn, rõ mục đích hơn.

## 3. `Converter<S, T>`: chuyển đổi một chiều, có kiểu rõ ràng

Interface trong package `org.springframework.core.convert.converter`:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`S` là kiểu nguồn, `T` là kiểu đích. Mỗi lần gọi `convert`, source được bảo đảm không null theo hợp đồng của Spring. Converter nên an toàn khi dùng đồng thời từ nhiều request; tránh giữ state mutable theo request trong một bean dùng chung.

Ví dụ chuyển chuỗi thành enum:

```java
public enum OrderStatus {
    PENDING, PAID, CANCELLED
}

public final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        try {
            return OrderStatus.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Expected PENDING, PAID or CANCELLED", ex
            );
        }
    }
}
```

`Locale.ROOT` được dùng khi chuẩn hóa token kỹ thuật như tên enum. Không nên dùng locale hiện tại của người dùng để đổi chữ hoa/thường cho mã giao thức hoặc mã trạng thái cố định.

Các nguyên tắc:

1. **Kiểm tra và chuẩn hóa đầu vào:** `trim()` nếu khoảng trắng ngoài chuỗi được cho phép.
2. **Không che giấu dữ liệu sai:** nếu token không hợp lệ, ném `IllegalArgumentException` với thông báo có ích.
3. **Không trả `null` tùy tiện:** xác định rõ đầu vào rỗng là thiếu dữ liệu, giá trị mặc định hay lỗi.
4. **Không thực hiện I/O trong converter:** converter nên là phép biến đổi nhanh, xác định; truy vấn database để đổi ID thành entity thuộc trách nhiệm service.
5. **Không lưu trạng thái request:** converter thường được đăng ký dùng chung và có thể được gọi đồng thời.

Spring có sẵn nhiều converter trong `core.convert.support`, ví dụ chuyển String sang số, Boolean, enum, collection và các kiểu phổ biến. Hãy tận dụng converter mặc định trước khi bổ sung logic tùy chỉnh.

## 4. Các SPI mở rộng: `ConverterFactory` và `GenericConverter`

### 4.1. `ConverterFactory<S, R>`

Dùng `ConverterFactory` khi một kiểu nguồn có thể chuyển thành nhiều kiểu đích thuộc cùng một họ hoặc lớp cơ sở.

Ví dụ một factory chuyển String thành các enum khác nhau:

```java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
```

Spring có thể dùng factory để tạo converter phù hợp với kiểu enum đích cụ thể. Với một enum đơn lẻ như `OrderStatus`, `Converter<String, OrderStatus>` thường đủ; không cần viết factory.

### 4.2. `GenericConverter`

`GenericConverter` linh hoạt hơn nhưng ít type-safe hơn. Nó có thể chuyển nhiều cặp source/target và nhận `TypeDescriptor`:

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );
}
```

`TypeDescriptor` cung cấp thông tin kiểu tổng quát và metadata trên field/method, chẳng hạn kiểu phần tử của `List<T>` hoặc annotation trên trường đích. Đây là lý do Spring có thể tái sử dụng converter phần tử để chuyển collection/array mà không cần viết converter riêng cho mọi tổ hợp.

Chỉ dùng `GenericConverter` khi cần xử lý nhiều kiểu nguồn/đích hoặc cần đọc metadata. Với phép chuyển đổi đơn giản, ưu tiên `Converter` hoặc `ConverterFactory`.

### 4.3. `ConditionalGenericConverter`

Nếu converter chỉ áp dụng khi có điều kiện, ví dụ target field mang annotation riêng hoặc target type có một phương thức factory cụ thể, dùng `ConditionalGenericConverter`:

```java
public interface ConditionalConverter {
    boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
}

public interface ConditionalGenericConverter
        extends GenericConverter, ConditionalConverter {
}
```

`matches(...)` cho phép Spring kiểm tra điều kiện trước khi chọn converter. Không nên dùng kiểu conditional chỉ để thay một phép parse đơn giản; nó dành cho trường hợp lựa chọn converter phụ thuộc metadata của kiểu nguồn/đích.

## 5. `Formatter<T>`: parse và print theo Locale

`Formatter<T>` nằm trong package `org.springframework.format` và kế thừa hai interface:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

Hai phương thức:

```java
public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Printer<T> {
    String print(T object, Locale locale);
}
```

- `parse` nhận văn bản từ client và tạo object.
- `print` chuyển object thành chuỗi để hiển thị.
- `Locale` cho biết quy tắc ngôn ngữ/khu vực cần áp dụng.

Ví dụ với ngày tháng:

```java
public final class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        try {
            return LocalDate.parse(text.trim(), formatter(locale));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected date in dd/MM/uuuu format", ex
            );
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
```

Trong ví dụ, `ResolverStyle.STRICT` yêu cầu ngày hợp lệ theo lịch, tránh việc tự điều chỉnh một ngày không tồn tại sang ngày khác. Formatter không dùng một `SimpleDateFormat` mutable dùng chung; `DateTimeFormatter` là immutable và thread-safe.

Nếu chỉ cần một chiều, Spring cho phép đăng ký riêng `Parser<T>` hoặc `Printer<T>` thay vì một `Formatter<T>` đầy đủ.

## 6. `ConversionService` và `FormatterRegistry`

### 6.1. `ConversionService`

`ConversionService` là API thống nhất để kiểm tra và thực hiện chuyển đổi khi chạy:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType,
        TypeDescriptor targetType
);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
);
```

Ví dụ:

```java
ConversionService service = ...;

boolean supported = service.canConvert(String.class, LocalDate.class);

LocalDate date = service.convert(
        "15/03/2025", LocalDate.class
);
```

`canConvert` hữu ích khi muốn kiểm tra trước một phép chuyển đổi tùy chọn. Không dùng nó thay cho xử lý lỗi: giữa lúc kiểm tra và lúc chuyển đổi, dữ liệu vẫn có thể không hợp lệ.

Khi cần chuyển đổi kiểu generic như `List<Integer>` thành `List<String>`, overload nhận `TypeDescriptor` giúp Spring biết kiểu phần tử nguồn và đích. Chỉ truyền `List.class` là chưa đủ để mô tả đầy đủ generic element type.

### 6.2. `ConverterRegistry` và `FormatterRegistry`

`ConverterRegistry` là SPI đăng ký converter. `FormatterRegistry` mở rộng registry này và cung cấp thêm các phương thức:

```java
void addFormatter(Formatter<?> formatter);
void addFormatterForFieldType(
        Class<?> fieldType, Formatter<?> formatter
);
void addFormatterForFieldType(
        Class<?> fieldType, Printer<?> printer, Parser<?> parser
);
void addFormatterForFieldAnnotation(
        AnnotationFormatterFactory<? extends Annotation> factory
);
void addParser(Parser<?> parser);
void addPrinter(Printer<?> printer);
```

`FormattingConversionService` vừa thực hiện chuyển đổi, vừa là nơi đăng ký formatter. `DefaultFormattingConversionService` là implementation được cấu hình sẵn các converter và formatter phổ biến, phù hợp với phần lớn ứng dụng.

Đây là object stateless được thiết kế để tạo lúc khởi động và chia sẻ giữa nhiều thread. Đừng tạo một conversion service mới cho mỗi request.

### 6.3. `FormatterRegistrar`

Nếu một nhóm định dạng cần đăng ký nhiều converter/formatter liên quan, có thể gom logic trong `FormatterRegistrar`:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

Cách này giúp cấu hình theo nhóm, ví dụ ngày tháng, tiền tệ hoặc mã định danh, thay vì đặt nhiều dòng đăng ký rải rác trong cấu hình.

## 7. Annotation định dạng có sẵn

Spring cung cấp annotation để khai báo quy tắc trên field hoặc method parameter:

- `@DateTimeFormat`: định dạng ngày/giờ; có thể dùng ISO, style hoặc pattern.
- `@NumberFormat`: định dạng số; hỗ trợ style hoặc pattern.
- Trong các phiên bản mới hơn, có thêm annotation định dạng cho một số kiểu như `Duration`; kiểm tra API đúng phiên bản Spring của dự án.

Ví dụ:

```java
public class SearchCriteria {

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal minimumAmount;

    // getter/setter
}
```

Annotation mô tả quy tắc trên một field cụ thể. Formatter đăng ký theo kiểu áp dụng quy tắc chung cho kiểu đó. Khi cần quy tắc phụ thuộc annotation tùy chỉnh, dùng `AnnotationFormatterFactory`.

Không nên đặt annotation định dạng vào field chỉ để giải quyết validation. `@DateTimeFormat` nói về cách parse/print; `@NotNull`, `@Positive` hoặc validator mới mô tả điều kiện hợp lệ của dữ liệu.

## 8. WebFlux tự áp dụng conversion khi bind tham số

Spring WebFlux chuyển đổi các giá trị chuỗi của annotated controller method arguments khi kiểu tham số không phải `String`. Những vị trí thường gặp:

- `@RequestParam`: query parameter.
- `@PathVariable`: biến trong URI template.
- `@RequestHeader`: HTTP header.
- `@CookieValue`: cookie.
- `@ModelAttribute`: bind dữ liệu request vào command object.

Ví dụ:

```java
@GetMapping("/orders")
Mono<String> search(
        @RequestParam("status") OrderStatus status,
        @RequestParam("from") LocalDate from) {

    return Mono.just(status + "|" + from);
}
```

Khi client gửi `?status=paid&from=15%2F03%2F2025`, WebFlux lấy giá trị chuỗi, dùng conversion service đã cấu hình để tạo `OrderStatus` và `LocalDate`, rồi mới gọi method.

Một khác biệt cần nhớ: trong WebFlux, `@RequestParam` chỉ truy cập query parameters. Form data và multipart được truy cập riêng qua `ServerWebExchange`; chúng có thể tham gia bind command object bằng `@ModelAttribute`.

**Conversion không đồng nghĩa validation.** Converter/formatter xác định chuỗi có thể biểu diễn thành kiểu Java hay không. Bean Validation hoặc Spring `Validator` kiểm tra điều kiện nghiệp vụ sau khi dữ liệu đã được bind.

Ví dụ ngày `31/02/2025` không parse được thành ngày hợp lệ; nhưng một ngày hợp lệ về lịch vẫn có thể vi phạm nghiệp vụ, chẳng hạn ngày bắt đầu nằm sau ngày kết thúc. Trường hợp sau cần validation riêng.

## 9. Đăng ký Converter và Formatter cho Spring WebFlux

Cách cấu hình chuẩn là triển khai `WebFluxConfigurer` và thêm converter/formatter qua `addFormatters`:

```java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatusConverter());
        registry.addFormatter(new LocalDateFormatter());
    }
}
```

Trong ứng dụng Spring Boot dùng `spring-boot-starter-webflux`, có thể đăng ký class cấu hình này như một bean `@Configuration`; Boot và WebFlux tổng hợp các `WebFluxConfigurer` để cấu hình conversion service dùng cho annotated controllers.

Nếu dùng cấu hình WebFlux thuần với `@EnableWebFlux`, cũng có thể triển khai `WebFluxConfigurer`. Tránh tự tạo một `DefaultFormattingConversionService` cục bộ rồi chỉ dùng nó trong service của bạn nếu mục tiêu là thay đổi binding của controller: registry đó phải được đăng ký vào đúng hạ tầng WebFlux.

Đối với một nhóm định dạng ngày tháng tiêu chuẩn, có thể dùng `DateTimeFormatterRegistrar`:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();

    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);

    registry.addConverter(new StringToOrderStatusConverter());
}
```

WebFlux mặc định xem xét request `Locale` khi parse/format giá trị ngày. Tuy nhiên, HTML `<input type="date">` và `<input type="time">` gửi định dạng cố định theo HTML specification; với các trường đó, định dạng ISO thường phù hợp hơn. Hãy thống nhất format giữa browser, API và server thay vì phụ thuộc locale một cách ngầm định.

## 10. Ví dụ Java 17+ chạy độc lập với `DefaultFormattingConversionService`

Ví dụ này cho thấy cùng một conversion service xử lý hai loại quy tắc:

- `Converter<String, OrderStatus>` chuyển mã trạng thái.
- `Formatter<LocalDate>` parse và print ngày theo định dạng đã chọn.

Cấu trúc:

```text
converter-formatter-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-formatter-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

enum OrderStatus {
    PENDING, PAID, CANCELLED
}

final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        try {
            return OrderStatus.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Expected PENDING, PAID or CANCELLED", ex
            );
        }
    }
}

final class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        try {
            return LocalDate.parse(text.trim(), formatter(locale));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Expected date in dd/MM/uuuu format", ex
            );
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}

public final class Main {
    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new StringToOrderStatusConverter());
        service.addFormatter(new LocalDateFormatter());

        LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
        try {
            OrderStatus status =
                    service.convert(" paid ", OrderStatus.class);

            LocalDate date =
                    service.convert("15/03/2025", LocalDate.class);

            String printedDate = service.convert(date, String.class);

            System.out.println("status=" + status);
            System.out.println("date=" + date);
            System.out.println("printed=" + printedDate);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Từ thư mục `converter-formatter-demo/`, chạy bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Stdout:

```text
status=PAID
date=2025-03-15
printed=15/03/2025
```

Giải thích:

1. `DefaultFormattingConversionService` khởi tạo các converter và formatter mặc định.
2. `addConverter` đăng ký converter tùy chỉnh cho `OrderStatus`.
3. `addFormatter` đăng ký parser/printer cho `LocalDate`.
4. `convert(" paid ", OrderStatus.class)` gọi converter, chuẩn hóa token và tạo `PAID`.
5. `convert("15/03/2025", LocalDate.class)` gọi formatter để parse ngày.
6. `convert(date, String.class)` dùng printer của formatter; `LocaleContextHolder` cung cấp locale hiện tại cho ví dụ console.
7. `finally` reset locale context để không để lại locale gắn với thread sau khi demo kết thúc.

Đây là chương trình console kiểm tra conversion service. Nó không khởi động WebFlux server; mục 9 cho thấy cách đăng ký chính các converter/formatter đó vào WebFlux.

## 11. Ví dụ tích hợp trong controller WebFlux

Sau khi cấu hình `WebFluxConfigurer` ở mục 9, controller có thể nhận kiểu đích trực tiếp:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    Mono<String> search(
            @RequestParam("status") OrderStatus status,
            @RequestParam("from") LocalDate from) {

        return Mono.just(status + "|" + from);
    }
}
```

Với server chạy tại `localhost:8080`, gửi request:

```bash
curl --get "http://localhost:8080/orders" \
  --data-urlencode "status=paid" \
  --data-urlencode "from=15/03/2025"
```

Response body:

```text
PAID|2025-03-15
```

Đây là ví dụ tích hợp phụ thuộc một ứng dụng Spring Boot WebFlux đã có `spring-boot-starter-webflux`, cấu hình `WebConfig`, các kiểu `OrderStatus`, `StringToOrderStatusConverter` và `LocalDateFormatter`. Nó không phải chương trình độc lập thứ hai.

Nếu client gửi `status=unknown` hoặc ngày không hợp lệ, conversion thất bại trước khi controller nhận được tham số. WebFlux sẽ xử lý như lỗi argument binding; thông thường request không hợp lệ được ánh xạ thành HTTP 400, trừ khi ứng dụng thay đổi exception handling. Không nên bắt mọi lỗi conversion rồi âm thầm gán giá trị mặc định.

## 12. `Converter` và `Formatter` không thay thế HTTP message codecs

Một điểm dễ nhầm: conversion/formatting của tham số controller không đồng nghĩa với việc xử lý JSON body.

- `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue` và data binding cho `@ModelAttribute` thường bắt đầu từ dữ liệu chuỗi; conversion service phù hợp cho bước này.
- `@RequestBody` JSON được đọc bởi `HttpMessageReader`/codec, thường thông qua Jackson. Cấu hình JSON serialization/deserialization nằm ở codec/ObjectMapper tương ứng.
- `@ResponseBody` JSON cũng được ghi bởi `HttpMessageWriter`/codec; `Formatter` không tự định dạng mọi field JSON.
- Nếu muốn định dạng một field JSON theo hợp đồng API, cấu hình serializer/deserializer hoặc DTO representation rõ ràng; đừng giả định `@DateTimeFormat` sẽ tự thay đổi cách Jackson ghi JSON.

Chọn extension point đúng tầng giúp tránh tình trạng một format hoạt động với query parameter nhưng không áp dụng cho JSON body.

## 13. Chuỗi rỗng, lỗi parse và validation

### 13.1. Thiếu tham số và tham số rỗng

Hai request khác nhau:

```text
GET /orders
GET /orders?limit=
```

- Không gửi `limit`: tham số có thể thiếu theo quy tắc `required`.
- Gửi `limit=`: giá trị là chuỗi rỗng; quá trình conversion có thể coi nó như missing nếu kết quả chuyển đổi là `null`.

Với `Long`, `UUID` và một số kiểu khác, chuỗi rỗng có thể được chuyển thành `null`. Nếu tham số bắt buộc, WebFlux có thể báo lỗi thiếu tham số/giá trị sau conversion. Nếu nghiệp vụ cho phép thiếu, dùng `required = false`, `Optional<T>` hoặc khai báo nullable phù hợp với codebase.

Đừng trả `null` từ converter chỉ để né lỗi dữ liệu nếu quy tắc nghiệp vụ chưa xác định rõ.

### 13.2. Thông báo lỗi có thể hành động được

Converter/formatter nên ném exception có mô tả giá trị mong đợi, ví dụ:

```java
throw new IllegalArgumentException(
        "Expected status: PENDING, PAID or CANCELLED"
);
```

Không đưa stack trace, thông tin nội bộ hoặc dữ liệu nhạy cảm vào thông báo lỗi gửi cho client. Log chi tiết ở server theo chính sách bảo mật, còn response nên có message rõ và an toàn.

### 13.3. Conversion không phải validation

Ví dụ:

- `"100"` chuyển thành `BigDecimal` thành công.
- Nhưng số tiền âm có thể không hợp lệ về nghiệp vụ.
- `"2025-03-15"` parse thành `LocalDate` thành công.
- Nhưng ngày đó có thể nằm ngoài khoảng cho phép.

Dùng Bean Validation (`@NotNull`, `@Positive`, `@Size`, custom constraint) hoặc Spring `Validator` sau khi bind để kiểm tra điều kiện nghiệp vụ. Với controller, `@Valid`/`@Validated` và `BindingResult`/`Errors` được dùng theo quy tắc của handler method.

Không biến converter thành nơi truy cập database hoặc kiểm tra quyền truy cập. Những kiểm tra đó thuộc service/domain layer.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Viết converter cho kiểu Spring đã hỗ trợ | Trùng lặp và có thể thay đổi hành vi mặc định | Kiểm tra `canConvert` và default converters trước |
| Dùng `Converter` để xử lý ngày theo locale | Không có tham số `Locale`, khó quản lý parse/print | Dùng `Formatter<T>` |
| Dùng `Formatter` cho chuyển đổi domain thuần túy | Code có thêm logic print/locale không cần thiết | Dùng `Converter<S,T>` |
| Không chuẩn hóa enum/token | Input có khoảng trắng hoặc chữ thường gây lỗi không mong muốn | `trim()` và dùng `Locale.ROOT` cho token kỹ thuật |
| Dùng `SimpleDateFormat` mutable trong formatter singleton | Có thể gặp race condition khi nhiều request đồng thời | Dùng `DateTimeFormatter` hoặc formatter thread-safe |
| Bắt exception rồi trả `null` không có quy tắc | Giá trị sai biến thành dữ liệu thiếu, khó debug | Ném `IllegalArgumentException` hoặc định nghĩa rõ empty policy |
| Đăng ký formatter chỉ trong service riêng | WebFlux controller vẫn dùng registry mặc định | Đăng ký qua `WebFluxConfigurer.addFormatters` |
| Tạo `ConversionService` mới mỗi request | Tốn tài nguyên và cấu hình không nhất quán | Tạo một instance dùng chung theo application |
| Nghĩ converter xử lý JSON body | JSON vẫn được codec/Jackson đọc độc lập | Cấu hình HTTP message codec/serializer |
| Dùng conversion để kiểm tra nghiệp vụ | Chuyển kiểu thành công nhưng dữ liệu vẫn sai nghiệp vụ | Dùng Bean Validation hoặc service/domain validation |
| Dùng format ngày không thống nhất với browser | `<input type=date>` gửi ISO nhưng formatter chờ format địa phương | Thống nhất ISO hoặc cấu hình registrar phù hợp |
| Ghi đè converter mặc định mà không kiểm thử | Các API khác có thể đổi hành vi | Giới hạn source/target và test các input biên |

## 15. Kiểm thử converter và formatter

Nên kiểm tra cả trường hợp hợp lệ và không hợp lệ:

| Trường hợp | Kỳ vọng |
|---|---|
| `"paid"` → `OrderStatus` | `PAID` |
| `" CANCELLED "` → `OrderStatus` | `CANCELLED` |
| `"unknown"` → `OrderStatus` | Ném lỗi conversion |
| `"15/03/2025"` → `LocalDate` | `2025-03-15` |
| `LocalDate.of(2025, 3, 15)` → String | `"15/03/2025"` với formatter đã đăng ký |
| `"31/02/2025"` → `LocalDate` | Lỗi parse do ngày không hợp lệ |
| Query param bị thiếu | Hành vi theo `required`/`Optional` |
| Query param là chuỗi rỗng | Hành vi theo quy tắc conversion và nullable |

Một unit test cho converter/formatter có thể gọi trực tiếp `convert`, `parse` và `print`. Một integration test WebFlux nên gửi HTTP request thật qua `WebTestClient` để kiểm tra registry đã được cấu hình và argument resolver thực sự dùng nó.

Ví dụ test cho conversion service:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new StringToOrderStatusConverter());
service.addFormatter(new LocalDateFormatter());

assertEquals(
        OrderStatus.PAID,
        service.convert("paid", OrderStatus.class)
);

assertEquals(
        LocalDate.of(2025, 3, 15),
        service.convert("15/03/2025", LocalDate.class)
);
```

Đây là đoạn test cần JUnit và import các kiểu trong ví dụ; không phải file chạy độc lập. Integration test bổ sung nên xác minh response với `status=unknown`, ngày sai, query param thiếu và locale khác nhau.

## 16. Bài tập tự kiểm tra

**Câu 1.** Chuyển `"paid"` thành `OrderStatus.PAID` nên dùng gì?

**Đáp án:** `Converter<String, OrderStatus>` vì đây là phép chuyển đổi kiểu một chiều, không cần locale hay in lại.

**Câu 2.** Vì sao `Formatter<LocalDate>` có thể phù hợp hơn `Converter<String, LocalDate>`?

**Đáp án:** Formatter có cả `parse` và `print`, nhận `Locale`, phù hợp với dữ liệu ngày hiển thị/nhập theo quy tắc khu vực.

**Câu 3.** `Formatter<T>` kế thừa interface nào?

**Đáp án:** `Printer<T>` và `Parser<T>`.

**Câu 4.** Muốn đăng ký custom converter và formatter để WebFlux dùng cho tham số controller, cấu hình ở đâu?

**Đáp án:** Triển khai `WebFluxConfigurer` và đăng ký qua `addFormatters(FormatterRegistry registry)`.

**Câu 5.** `ConversionService` có tự kiểm tra `amount > 0` không?

**Đáp án:** Không. Nó chuyển kiểu; điều kiện nghiệp vụ cần Bean Validation hoặc Spring Validator/domain logic.

**Câu 6.** `@RequestBody` JSON có tự dùng Formatter đã đăng ký cho query parameter không?

**Đáp án:** Không mặc định. JSON body được xử lý qua HTTP message codecs, thường là Jackson; cần cấu hình serializer/deserializer tương ứng nếu muốn định dạng JSON riêng.

**Câu 7.** Vì sao converter/formatter nên thread-safe?

**Đáp án:** Spring thường đăng ký chúng trong conversion service dùng chung cho nhiều request đồng thời.

**Câu 8.** Khi một query param là chuỗi rỗng, có luôn tương đương tham số bị thiếu không?

**Đáp án:** Không. Hành vi phụ thuộc converter và kiểu đích; một số chuyển đổi trả `null` khiến Spring coi như missing. Cần xác định rõ required/nullable/Optional.

## 17. Quy tắc lựa chọn

- Chọn **`Converter<S,T>`** cho phép chuyển đổi kiểu rõ ràng, không phụ thuộc locale.
- Chọn **`Formatter<T>`** khi cần parse và print dữ liệu text theo locale.
- Chọn **`ConverterFactory`** cho một họ kiểu đích; chọn **`GenericConverter`** khi cần nhiều cặp kiểu hoặc `TypeDescriptor`.
- Dùng **`DefaultFormattingConversionService`** cho ứng dụng cần cả converter và formatter mặc định.
- Đăng ký converter/formatter dùng trong WebFlux bằng **`WebFluxConfigurer.addFormatters`**.
- Phân biệt conversion, formatting, validation và JSON codec; mỗi tầng có nhiệm vụ riêng.
- Kiểm thử input rỗng, sai định dạng, locale, tham số thiếu và các giá trị biên.

**Ghi nhớ:** `Converter` chuyển kiểu; `Formatter` parse và print text theo `Locale`. Spring WebFlux dùng conversion service để bind dữ liệu chuỗi vào tham số controller. Đăng ký quy tắc một lần qua `WebFluxConfigurer`, giữ converter/formatter thread-safe và dùng validation riêng để kiểm tra điều kiện nghiệp vụ.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — WebFlux Type Conversion](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html)
- [Spring Framework — WebFlux `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html)
- [Spring Framework 6.1.11 — `DefaultFormattingConversionService` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
- [Spring Framework 6.1.11 — `Formatter` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.1.13 — `WebFluxConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
