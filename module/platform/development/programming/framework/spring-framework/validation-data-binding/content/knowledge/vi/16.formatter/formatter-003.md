# Phân biệt chuyển đổi kiểu tổng quát với định dạng hiển thị trong Spring Framework

## 1. Hai nhu cầu khác nhau

Ứng dụng thường phải biến đổi dữ liệu giữa kiểu Java và chuỗi người dùng nhập hoặc nhìn thấy. Hai việc này liên quan nhưng không giống nhau:

- **Chuyển đổi kiểu tổng quát (type conversion):** biến giá trị từ kiểu nguồn sang kiểu đích, ví dụ `String` thành `CurrencyCode`, `Integer` thành `Long`, hoặc `LegacyId` thành `CustomerId`. Trọng tâm là ý nghĩa và kiểu dữ liệu.
- **Định dạng hiển thị (field formatting):** parse chuỗi người dùng nhập thành giá trị có kiểu và in giá trị đó thành chuỗi phù hợp với giao diện/locale. Cùng ngày 31/12/2026 có thể hiển thị `31/12/2026` hoặc `12/31/2026`.

Spring cung cấp hai SPI chính:

- `Converter<S,T>` trong `org.springframework.core.convert.converter` dành cho chuyển đổi kiểu tổng quát.
- `Formatter<T>` trong `org.springframework.format` dành cho parse và print field value theo locale.

`ConversionService` cung cấp API thống nhất để thực hiện chuyển đổi; `FormattingConversionService` tích hợp cả converter lẫn formatter. Khác biệt nằm ở mục đích và hợp đồng của SPI, không phải ở việc chúng không thể làm việc chung.

## 2. Cùng một giá trị, nhiều cách hiển thị

Giá trị nghiệp vụ:

```java
LocalDate date = LocalDate.of(2026, 12, 31);
```

Đối tượng `LocalDate` không tự mang quy ước hiển thị. Tùy giao diện/locale, nó có thể được trình bày thành:

| Quy ước | Chuỗi ví dụ | Ý nghĩa |
| --- | --- | --- |
| Ngày/tháng/năm | `31/12/2026` | Phổ biến tại Việt Nam |
| Tháng/ngày/năm | `12/31/2026` | Ví dụ quy ước Hoa Kỳ |
| ISO | `2026-12-31` | Năm-tháng-ngày |

Các chuỗi diễn tả cùng một ngày. Nếu lưu chuỗi UI làm giá trị nghiệp vụ, hệ thống dễ nhầm ngày/tháng khi đổi locale hoặc trao đổi dữ liệu.

Hãy hỏi: “Giá trị này cần trở thành kiểu Java nào?” thì chọn Converter; “Giá trị Java này nên hiển thị thế nào cho người dùng ở locale hiện tại?” thì chọn Formatter. Định dạng không nên làm thay đổi giá trị nghiệp vụ.

## 3. Converter: chuyển đổi kiểu tổng quát

### 3.1. Hợp đồng API

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`S` là kiểu nguồn, `T` là kiểu đích. Converter thường stateless, thread-safe và có thể ném `IllegalArgumentException` khi nguồn không hợp lệ. Nó không có tham số `Locale` và không cung cấp phương thức in ngược.

Ví dụ chuyển chuỗi mã tiền tệ thành value object:

```java
public record CurrencyCode(String value) {}

public final class StringToCurrencyCodeConverter
        implements Converter<String, CurrencyCode> {
    @Override
    public CurrencyCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Currency is blank");
        }
        String code = source.strip().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
        return new CurrencyCode(code);
    }
}
```

Cần import `java.util.Locale` và `Converter`. Input `" usd "` trở thành `CurrencyCode("USD")`. Dùng `Locale.ROOT` vì chuẩn hóa mã định danh không nên bị ảnh hưởng bởi locale giao diện.

Converter này không biết chuỗi sẽ xuất hiện ở HTML, log hay JSON. Nó chỉ tạo kiểu dữ liệu có ý nghĩa đã chuẩn hóa.

### 3.2. Converter không tự định dạng ngược

`Converter<String, CurrencyCode>` chỉ xử lý chiều String sang CurrencyCode. Nếu muốn chiều ngược, đăng ký converter khác:

```java
public final class CurrencyCodeToStringConverter
        implements Converter<CurrencyCode, String> {
    @Override
    public String convert(CurrencyCode source) {
        return source == null ? null : source.value();
    }
}
```

Hai converter độc lập; chúng không tự tạo hợp đồng parse/print theo locale. Khi đầu ra cần localization, Formatter thường phù hợp hơn.

### 3.3. Khi nào dùng Converter?

Dùng Converter khi chuyển identifier/string sang domain value object; chuyển `Long` sang `CustomerId`; hoặc khi logic chuyển kiểu ổn định, không phụ thuộc locale. Converter có thể được tái sử dụng ở BeanFactory, DataBinder, SpEL và các nơi dùng ConversionService.

Đừng đưa database lookup, authorization hay side effect nghiệp vụ vào converter dùng chung.

## 4. Formatter: parse và print cho giao diện

### 4.1. Hợp đồng Formatter

```java
public interface Printer<T> {
    String print(T fieldValue, Locale locale);
}
public interface Parser<T> {
    T parse(String clientValue, Locale locale) throws ParseException;
}
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

- `parse` đọc chuỗi client gửi và tạo object kiểu `T`.
- `print` chuyển object `T` thành chuỗi hiển thị.
- Cả hai nhận `Locale`.
- `parse` có thể ném `ParseException` hoặc `IllegalArgumentException`.
- Formatter dùng chung phải thread-safe. Tránh giữ `SimpleDateFormat` mutable dùng chung; `DateTimeFormatter` bất biến là lựa chọn an toàn.

### 4.2. Ví dụ Formatter cho LocalDate

```java
public final class LocalDateShortFormatter
        implements Formatter<LocalDate> {
    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        DateTimeFormatter format =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale)
                .withResolverStyle(ResolverStyle.STRICT);
        try {
            return LocalDate.parse(text, format);
        }
        catch (DateTimeParseException ex) {
            ParseException error =
                new ParseException(ex.getMessage(), 0);
            error.initCause(ex);
            throw error;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
            .withLocale(locale).format(value);
    }
}
```

Cần imports `java.text.ParseException`, `java.time.LocalDate`, `java.time.format.*`, `java.util.Locale` và `org.springframework.format.Formatter`.

`FormatStyle.SHORT` chọn kiểu ngày ngắn theo locale. Với quy ước Hoa Kỳ, ngày 31/12/2026 có thể parse từ `12/31/26`; locale khác có thể dùng thứ tự trường khác. `ResolverStyle.STRICT` giúp từ chối ngày không tồn tại thay vì âm thầm điều chỉnh. Hãy kiểm thử các locale sản phẩm hỗ trợ.

### 4.3. Parse/print không nhất thiết là nghịch đảo hoàn hảo

Formatter có hai thao tác nhưng chuỗi in ra có thể bỏ bớt độ chính xác hoặc thông tin. Ví dụ formatter chỉ in ngày mà không gồm thời gian; parse lại chỉ khôi phục phần ngày. Quy tắc nên xác định rõ dạng input, chuỗi output, locale, chính sách với chuỗi rỗng/null và hành vi khi giá trị sai định dạng.

## 5. So sánh Converter và Formatter

| Tiêu chí | `Converter<S,T>` | `Formatter<T>` |
| --- | --- | --- |
| Mục đích | Chuyển kiểu tổng quát | Định dạng field cho client/UI |
| Hướng | Một chiều `S → T` | Parse chuỗi thành T, print T thành chuỗi |
| Locale | Không có tham số locale | Có Locale ở cả parse/print |
| Tập trung | Ý nghĩa kiểu dữ liệu | Biểu diễn cho con người |
| Ví dụ | `String → CurrencyCode` | `String → LocalDate` theo locale và `LocalDate → String` |
| Đăng ký | `ConverterRegistry.addConverter` | `FormatterRegistry.addFormatter` |
| Use case | Domain IDs, value objects | Form ngày, số tiền, phần trăm |

Quy tắc lựa chọn: cần chuyển đổi ý nghĩa kiểu độc lập locale thì chọn Converter; cần parse/print chuỗi hiển thị theo locale thì chọn Formatter. Một ứng dụng thường cần cả hai.

## 6. ConversionService nối hai SPI thế nào?

`ConversionService` là API tra cứu và thực hiện phép chuyển đổi:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
```

`FormatterRegistry` là SPI đăng ký converter và formatter. `FormattingConversionService` triển khai cả `FormatterRegistry` và `ConversionService`, vì vậy một service có thể chuyển kiểu tổng quát, parse chuỗi ngày và print ngày theo locale.

Ví dụ:

```java
DefaultFormattingConversionService service =
    new DefaultFormattingConversionService();

service.addConverter(new StringToCurrencyCodeConverter());
service.addFormatterForFieldType(
    LocalDate.class,
    new LocalDateShortFormatter()
);
```

Cần import `DefaultFormattingConversionService` cùng các class custom. Sau khi đăng ký, caller dùng `convert` thay vì tự gọi từng converter/formatter:

```java
CurrencyCode currency =
    service.convert(" usd ", CurrencyCode.class);

LocalDate date =
    service.convert("12/31/26", LocalDate.class);

String rendered = service.convert(date, String.class);
```

Kết quả ngày phụ thuộc locale context và formatter; không nên giả định cùng chuỗi hiển thị trên mọi máy. `DefaultFormattingConversionService` là implementation có sẵn với converter/formatter phổ biến; nó không phải một SPI riêng với `FormattingConversionService`.

## 7. TypeDescriptor và metadata của property

API `convert(source, targetClass)` đủ cho nhiều phép đơn giản. Nhưng `Class<?>` không luôn mô tả generic và annotation.

`TypeDescriptor` có thể mang metadata về generic element của `List`/array, key/value type của `Map`, annotation trên field/property và kiểu component.

`List<Integer>` và `List<String>` cùng có runtime class `List.class`. Nếu chỉ truyền `List.class`, caller không biểu đạt được kiểu element nguồn/đích:

```java
TypeDescriptor source = TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(Integer.class));

TypeDescriptor target = TypeDescriptor.collection(
    List.class, TypeDescriptor.valueOf(String.class));

Object result = service.convert(
    List.of(1, 2, 3), source, target);
```

Cần import `TypeDescriptor`; với converter Integer→String, kết quả là danh sách chuỗi `["1", "2", "3"]`. Trong property binding, Spring thường lấy metadata từ property; khi gọi API thấp tầng, caller có thể cần cung cấp descriptor.

## 8. Đăng ký converter và formatter ở đâu?

### 8.1. FormatterRegistry

```java
registry.addConverter(new StringToCurrencyCodeConverter());
registry.addFormatter(new LocalDateShortFormatter());
registry.addFormatterForFieldType(
    LocalDate.class, new LocalDateShortFormatter());
```

`addConverter` đăng ký phép chuyển đổi kiểu tổng quát; `addFormatter` đăng ký formatter theo kiểu T; `addFormatterForFieldType` giới hạn formatter cho một kiểu field; `addFormatterForFieldAnnotation` cho phép gắn quy tắc với annotation.

### 8.2. Spring MVC

Đăng ký tập trung qua `WebMvcConfigurer.addFormatters`:

```java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCurrencyCodeConverter());
        registry.addFormatterForFieldType(
            LocalDate.class, new LocalDateShortFormatter());
    }
}
```

Đây là fragment tích hợp, cần imports Spring MVC và các class custom. Spring MVC có formatter mặc định cho nhiều kiểu số/ngày; cấu hình này bổ sung converter/formatter riêng. Locale request được framework cung cấp cho formatter; tránh tự lấy locale mặc định của JVM nếu framework đã có locale phù hợp.

### 8.3. DataBinder và WebDataBinder

`DataBinder` dùng conversion service khi bind property:

```java
DataBinder binder = new DataBinder(form, "form");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
```

Đây là fragment cho target JavaBean có property writable. `WebDataBinder` mở rộng DataBinder cho web. Formatter có thể parse chuỗi request thành field object; khi hiển thị lại, formatter có thể print giá trị theo locale.

Formatter không tự ép mọi serializer JSON dùng quy tắc print của nó. `@RequestBody` và Jackson/`HttpMessageConverter` có cơ chế deserialize riêng.

## 9. Annotation formatters

Spring hỗ trợ annotation trên field/parameter, phổ biến là `@DateTimeFormat` và `@NumberFormat`:

```java
public class SearchForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    // getters/setters
}
```

Cần imports annotation, `LocalDate` và `BigDecimal`. `@DateTimeFormat` chỉ định cách parse/print ngày; `@NumberFormat` chỉ định cách định dạng số. Annotation không thay đổi kiểu Java của property.

Nếu hai field LocalDate trong cùng form cần hai quy tắc khác nhau, cấu hình theo annotation phù hợp hơn formatter mặc định cho mọi LocalDate.

## 10. Ví dụ Java 17: ConversionService và DataBinder cùng sử dụng

Ví dụ này dùng một Converter cho mã tiền tệ và một Formatter cho ngày, cùng đăng ký vào `DefaultFormattingConversionService`; sau đó `DataBinder` dùng service để bind form.

### 10.1. Cấu trúc Maven

```text
formatter-demo/
├── pom.xml
└── src/main/java/example/FormatterDemo.java
```

`pom.xml` dùng Java 17 và Spring Framework 6.2.14:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>formatter-demo</artifactId>
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
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.FormatterDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/FormatterDemo.java`:

```java
package example;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.FormatStyle;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class FormatterDemo {

    public record CurrencyCode(String value) {}

    public static final class StringToCurrencyCode
            implements Converter<String, CurrencyCode> {
        @Override
        public CurrencyCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Currency is blank");
            }
            String code = source.strip().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency");
            }
            return new CurrencyCode(code);
        }
    }

    public static final class LocalDateFormatter
            implements Formatter<LocalDate> {
        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {
            DateTimeFormatter format =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                    .withLocale(locale)
                    .withResolverStyle(ResolverStyle.STRICT);
            try {
                return LocalDate.parse(text, format);
            }
            catch (DateTimeParseException ex) {
                ParseException error =
                    new ParseException(ex.getMessage(), 0);
                error.initCause(ex);
                throw error;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale).format(value);
        }
    }

    public static class SearchForm {
        private CurrencyCode currency;
        private LocalDate startDate;

        public CurrencyCode getCurrency() { return currency; }
        public void setCurrency(CurrencyCode value) { currency = value; }
        public LocalDate getStartDate() { return startDate; }
        public void setStartDate(LocalDate value) { startDate = value; }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
            new DefaultFormattingConversionService();
        service.addConverter(new StringToCurrencyCode());
        service.addFormatterForFieldType(
            LocalDate.class, new LocalDateFormatter());

        SearchForm form = new SearchForm();
        DataBinder binder = new DataBinder(form, "searchForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("currency", " usd ");
        values.add("startDate", "12/31/26");

        LocaleContextHolder.setLocale(Locale.US);
        try {
            binder.bind(values);
        }
        finally {
            LocaleContextHolder.resetLocaleContext();
        }

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            throw new IllegalStateException(
                "Binding failed: " + errors.getAllErrors());
        }

        System.out.println("currency=" + form.getCurrency().value());
        System.out.println("date-iso=" + form.getStartDate());
        System.out.println("date-display=" +
            service.convert(form.getStartDate(), String.class));
        System.out.println("errors=" + errors.hasErrors());
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

`stdout` dự kiến trên Java 17/Spring 6.2.14:

```text
currency=USD
date-iso=2026-12-31
date-display=12/31/26
errors=false
```

`currency=USD` minh họa Converter chuẩn hóa mã; `date-iso` là giá trị LocalDate; `date-display` là Formatter in theo locale US, style SHORT. Locale được đặt qua `LocaleContextHolder` khi binder chạy và reset bằng `finally` để tránh rò rỉ sang xử lý khác trên cùng thread.

Trong Spring MVC, locale resolver/request context cung cấp locale của request. Chương trình độc lập phải đặt context khi kiểm thử parse/print phụ thuộc locale.

## 11. Parse error, conversion error và validation

| Tình huống | Tầng phù hợp |
| --- | --- |
| `"abc"` không thể thành Integer | Converter/built-in conversion |
| `"31/02/2026"` là ngày không tồn tại | Formatter parse |
| Mã `"usd"` cần chuẩn hóa thành `"USD"` | Converter |
| Ngày cần in theo locale US/VN | Formatter print |
| Ngày parse hợp lệ nhưng nằm ngoài thời gian đặt lịch | Validation nghiệp vụ |
| Người dùng không được phép dùng loại tiền này | Authorization/service |

Parse/convert chỉ tạo giá trị có kiểu. Validation kiểm tra ràng buộc. Authorization kiểm tra quyền thực hiện. Đừng đưa database lookup hoặc side effect vào Formatter.

Khi Formatter/Converter thất bại qua DataBinder, binder có thể ghi lỗi field trong `BindingResult`. Handler cần kiểm tra `hasErrors()` trước khi gọi service. Nếu gọi `ConversionService.convert` trực tiếp, exception có thể truyền lên caller tùy API.

Với form Spring MVC, đặt `BindingResult` ngay sau `@ModelAttribute`. Với JSON `@RequestBody`, message converter/JSON mapper chịu trách nhiệm deserialize; Formatter của DataBinder không tự động thay Jackson.

## 12. Lỗi thường gặp

1. Dùng Converter để in UI theo locale: Converter không nhận Locale; dùng Formatter.
2. Dùng Formatter cho mọi domain conversion: phép chuyển kiểu tổng quát vẫn nên là Converter.
3. Rải format logic trong controller: đăng ký tập trung qua FormatterRegistry.
4. Dùng SimpleDateFormat singleton: mutable, không thread-safe; dùng DateTimeFormatter.
5. Dựa vào locale mặc định JVM: kết quả khác giữa môi trường; dùng Locale framework truyền hoặc đặt trong test.
6. Nhầm format với lưu trữ: lưu kiểu ngày/tiền phù hợp, không lưu chuỗi hiển thị làm dữ liệu nghiệp vụ.
7. Không kiểm soát ResolverStyle: ngày sai có thể bị điều chỉnh nếu resolver không strict.
8. Cho rằng Formatter điều khiển JSON: JSON mapper có serializer/deserializer riêng.
9. Đăng ký trùng quy tắc: converter/formatter xung đột khiến hành vi khó hiểu.
10. Đưa business rule vào Formatter: giữ Formatter tập trung parse/print; validation và quyền truy cập thuộc tầng khác.

## 13. Kiểm thử và chọn abstraction

Nên kiểm thử Converter với input hợp lệ, khoảng trắng, input rỗng và input sai; Formatter với parse/print từng locale, ngày không hợp lệ và round-trip; DataBinder với field hợp lệ, field lỗi, BindingResult và giá trị target; MVC integration với locale request và formatter registry.

| Nhu cầu | Lựa chọn |
| --- | --- |
| String sang domain ID/value object | `Converter<String,T>` |
| Ngày nhập và hiển thị theo locale | `Formatter<LocalDate>` |
| Tiền nhập/in theo locale | `Formatter<BigDecimal>` |
| Quy tắc riêng từng field | Annotation formatter |
| Cần cả conversion và formatting | `FormattingConversionService` |
| Collection generic | `TypeDescriptor` |

## 14. Bài tập tự kiểm tra

**Bài 1.** Chuyển `"42"` thành `CustomerId(42)`, không phụ thuộc locale. Dùng gì?

**Đáp án:** `Converter<String, CustomerId>` vì đây là phép chuyển kiểu domain tổng quát.

**Bài 2.** Form nhập ngày theo quy ước người dùng và hiển thị lại theo cùng locale. Dùng gì?

**Đáp án:** `Formatter<LocalDate>` với parse và print nhận Locale.

**Bài 3.** Một LocalDate hiển thị `31/12/2026` ở form A và `12/31/2026` ở form B. Có cần hai kiểu LocalDate?

**Đáp án:** Không. Giữ một kiểu miền; chọn formatter/locale phù hợp từng field.

**Bài 4.** `CurrencyCode("USD")` chuyển đổi thành công; tài khoản không được giao dịch bằng USD. Converter có nên tra tài khoản và từ chối?

**Đáp án:** Không. Quyền giao dịch và validation nghiệp vụ thuộc service/domain.

## 15. Tài liệu tham khảo chính thức

- Spring Framework Reference — [Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): khác biệt Converter/Formatter, Printer, Parser, FormatterRegistry và FormatterRegistrar.
- Spring Framework Reference — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter SPI, TypeDescriptor và registry.
- Spring Framework Reference — [Spring MVC Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký formatter/converter qua WebMvcConfigurer.
- Spring Framework Javadoc — [Formatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Formatter.html): contract parse/print.
- Spring Framework Javadoc — [FormattingConversionService](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/support/FormattingConversionService.html): FormatterRegistry và ConversionService.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): binding qua ConversionService.
