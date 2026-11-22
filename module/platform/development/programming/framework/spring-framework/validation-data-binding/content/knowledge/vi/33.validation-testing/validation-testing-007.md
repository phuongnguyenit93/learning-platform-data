# Kiểm thử parse và print theo nhiều Locale trong Spring Framework

## 1. Mục tiêu: cùng dữ liệu, nhiều cách biểu diễn

Trong ứng dụng đa ngữ, giá trị Java **không đổi** nhưng chuỗi nhập vào và hiển thị có thể thay đổi theo `Locale`. Ví dụ cùng một số tiền `1234.50`:

| Locale | Chuỗi thường gặp | Ý nghĩa |
| --- | --- | --- |
| `en-US` | `1,234.50` | Dấu phẩy nhóm nghìn, dấu chấm thập phân |
| `de-DE` | `1.234,50` | Dấu chấm nhóm nghìn, dấu phẩy thập phân |
| `fr-FR` | Có thể dùng dấu cách không ngắt/narrow no-break space để nhóm nghìn | Không giả định dấu cách ASCII |
| `vi-VN` | Cách nhóm và dấu thập phân theo dữ liệu locale của JDK | Kiểm thử theo locale thật, không đoán từ giao diện |

Nếu `@ModelAttribute` nhận chuỗi `1.234,50` từ người dùng Đức nhưng parser chạy với `Locale.US`, nó có thể báo lỗi **hoặc diễn giải sai** tùy parser và mức độ lenient. Một bài test chỉ chạy với `Locale.getDefault()` trên máy phát triển sẽ không phát hiện khác biệt này.

Với ngày tháng, ví dụ `15 Sep 2026` và một chuỗi có tên tháng theo tiếng Đức/Pháp/Việt đều có thể biểu diễn cùng `LocalDate.of(2026,9,15)`. Nhưng không nên khẳng định một chuỗi localized date bất biến giữa mọi JDK, CLDR provider và phiên bản dữ liệu locale.

**Đề bài của bài học:** kiểm thử cả hai chiều của Spring `Formatter<T>`:
- `parse(String text, Locale locale)`: từ chuỗi người dùng → giá trị Java.
- `print(T value, Locale locale)`: từ giá trị Java → chuỗi hiển thị.
- `parse(print(value, locale), locale)`: *round-trip* phải bảo toàn ngữ nghĩa.
- `print(parse(text, locale), locale)`: kiểm tra văn bản được chuẩn hóa theo quy tắc đã định.
- Kiểm thử với nhiều locale cụ thể, cả trường hợp input sai, sai separator, dữ liệu thiếu và thay đổi JDK locale data.

Ví dụ dùng **Java 17, Spring Boot 3.5.7, Spring Framework 6.2**, hai formatters tự viết và JUnit 5/MockMvc. Có kiểm tra trực tiếp formatter, `FormattingConversionService`, `WebDataBinder` và HTTP `@ModelAttribute`. Kết quả test được mô tả là **dự kiến**, không giả vờ là log thực thi.

## 2. Khái niệm: Locale khác với ngôn ngữ của message

### 2.1. `Locale` là dữ liệu đầu vào của formatting

`java.util.Locale` có language, region và có thể có script/variants/extensions:

~~~java
Locale us = Locale.US;
Locale de = Locale.GERMANY;
Locale fr = Locale.FRANCE;
Locale vi = Locale.forLanguageTag("vi-VN");

System.out.println(us.toLanguageTag()); // en-US
System.out.println(de.toLanguageTag()); // de-DE
System.out.println(fr.toLanguageTag()); // fr-FR
System.out.println(vi.toLanguageTag()); // vi-VN
~~~

Đây là **đoạn minh họa trong một method**, không phải Java class đầy đủ. Các tag được chọn tường minh; không dùng `Locale.getDefault()` làm tham số test vì JVM/CI có thể chạy tại khu vực khác.

Locale ảnh hưởng tới grouping separators, decimal separators, chữ số, tên tháng, thứ tự ngày/tháng/năm và quy tắc format. Tuy nhiên, nó **không mang theo múi giờ**. `Locale` và `ZoneId` là hai thông tin khác nhau: với `Instant`/`ZonedDateTime`, phải kiểm thử thêm zone và DST nếu nghiệp vụ yêu cầu.

### 2.2. Spring `Formatter<T>`

Spring `Formatter<T>` kết hợp hai interface `Printer<T>` và `Parser<T>`:

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws java.text.ParseException;
}

public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

Đây là chữ ký API **rút gọn để học**, không thêm file có khai báo lại các interface của Spring. `Formatter<T>` mạnh hơn `Converter<S,T>` khi cần cả hai chiều và locale. Một `Converter<String, BigDecimal>` thường không có tham số locale trong chữ ký.

`Formatter` nên **thread-safe** vì có thể được đăng ký một lần trong `ConversionService` dùng chung. Nếu sử dụng `DecimalFormat` hoặc `SimpleDateFormat`, vốn mutable, tạo instance mới mỗi lần `parse`/`print` hoặc quản lý lifecycle an toàn. Đừng giữ một `DecimalFormat` trong field rồi gọi đồng thời từ nhiều requests.

### 2.3. `FormattingConversionService`

`FormattingConversionService` là một `ConversionService` cũng triển khai `FormatterRegistry`. Sau khi gọi `addFormatter(new CustomFormatter())`, hệ thống đăng ký các chuyển đổi `String → T` và `T → String`. Khi sử dụng qua adapter, Spring lấy locale từ `LocaleContextHolder` phù hợp.

Các lớp hữu ích:

| API | Vai trò trong test |
| --- | --- |
| `Formatter<T>.parse` | Kiểm tra parser trực tiếp với locale tường minh |
| `Formatter<T>.print` | Kiểm tra printer trực tiếp với locale tường minh |
| `FormattingConversionService#addFormatter` | Test đăng ký formatter |
| `ConversionService#convert` | Test adapter thật, cả `String→T` và `T→String` |
| `LocaleContextHolder` | Chọn locale tạm thời cho adapter trong test đồng bộ |
| `WebDataBinder#setConversionService` | Test property binding với formatter đã đăng ký |
| `WebMvcConfigurer#addFormatters` | Đăng ký formatters vào MVC |
| `WebFluxConfigurer#addFormatters` | Đăng ký formatters vào WebFlux |
| `MockMvc` | Kiểm thử locale của HTTP request trong Spring MVC |
| `WebTestClient` | Kiểm thử HTTP với WebFlux hoặc MVC theo cấu hình phù hợp |

**Chú ý:** `@DateTimeFormat`, `@NumberFormat` và các formatters mặc định của Spring đã hỗ trợ nhiều trường hợp. Bài tự viết formatters để minh họa rõ điều kiện đúng/sai; trong sản phẩm thật, ưu tiên API mặc định nếu đủ nhu cầu.

## 3. Định nghĩa chính xác điều cần chứng minh

### 3.1. Round-trip kiểu giá trị

Với mọi `Locale` được hỗ trợ và giá trị hợp lệ `x`:

~~~text
parse(print(x, locale), locale) ≈ x
~~~

Ký hiệu `≈` là **tương đương về ngữ nghĩa**, không luôn là `Object.equals`:
- Với `LocalDate` và một record chứa nó, equality là chính xác.
- Với `BigDecimal`, `equals` so sánh cả scale, nên `1.0` không bằng `1.00`; dùng `compareTo(...) == 0` khi contract chỉ yêu cầu giá trị số.
- Với số tiền cần đúng scale/currency, contract có thể mạnh hơn và yêu cầu cả scale.
- Với ngày/giờ có timezone, epoch, offset và instant là những khái niệm khác nhau.

Không giả định rằng formatter làm tròn hoặc loại bỏ phần thập phân vẫn bảo toàn dữ liệu. Nếu formatter chỉ in 2 chữ số sau dấu thập phân, `1.234` không thể round-trip thành chính nó. Cần quyết định: **từ chối** input có độ chính xác quá cao hay chấp nhận rounding như một quy tắc nghiệp vụ rõ ràng.

### 3.2. Round-trip của text có thể là canonicalization

~~~text
print(parse(text, locale), locale) == canonical(text, locale)
~~~

Không nhất thiết bằng input nguyên thủy. Một parser lenient có thể chấp nhận `"1234.5"` và printer in `"1,234.50"`. Nếu hệ thống đòi input đúng một dạng canonical, parser phải kiểm tra lại **chuỗi sau khi print** và từ chối các biến thể không mong muốn.

Bài chọn một contract **nghiêm ngặt** cho amount: grouping theo locale và luôn hai chữ số thập phân, không chấp nhận input có trailing garbage hoặc dạng không canonical. Đây là quy tắc ví dụ để test được minh bạch; không phải định dạng bắt buộc cho mọi website.

### 3.3. Parse sai phải báo lỗi, không tự đoán

Giả sử Java object yêu cầu `LocalizedAmount(1234.50)`:

~~~text
en-US valid: 1,234.50
de-DE valid: 1.234,50

en-US input: 1.234,50
=> reject, không âm thầm diễn giải thành 1.23450 hoặc 123450.
~~~

Trong production, một số form sẽ cho nhập thiếu grouping hoặc thiếu trailing zeros. Khi đó phải **định nghĩa tập input được chấp nhận**, không để mặc định của `NumberFormat` quyết định một cách ngẫu nhiên. Test cases nên chứng minh cả input được phép và input bị từ chối.

### 3.4. Locale matrix tối thiểu

| Loại dữ liệu | `en-US` | `de-DE` | `fr-FR` | `vi-VN` |
| --- | --- | --- | --- | --- |
| Decimal amount | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip |
| Localized day | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip | Parse + print + round-trip |
| Sai format | Test separator sai | Test separator sai | Test whitespace/grouping khác | Test locale data |
| Spring ConversionService | Test explicit locale context | Test explicit locale context | Test nếu sản phẩm hỗ trợ | Test nếu sản phẩm hỗ trợ |
| HTTP binding | Gửi locale tương ứng | Gửi locale tương ứng | Gửi locale tương ứng | Gửi locale tương ứng |

Đừng bỏ qua `fr-FR`: dấu nhóm nghìn có thể là **U+202F NARROW NO-BREAK SPACE** hoặc biến thể khác tùy dữ liệu locale. Test không nên viết cứng một dấu cách ASCII `" "` rồi mặc định nó luôn hợp lệ. Với `vi-VN`, cũng không ép một chuỗi locale “theo trí nhớ” làm expected cho mọi JDK mà chưa xác định môi trường.

## 4. Formatter cho số tiền có hai chữ số thập phân

### 4.1. Kiểu miền: `LocalizedAmount`

~~~java
package com.example.localeformat;

import java.math.BigDecimal;
import java.util.Objects;

public record LocalizedAmount(BigDecimal value) {
    public LocalizedAmount {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Đây là một Java 17 record độc lập. Nó biểu diễn giá trị, **không lưu cách hiển thị theo locale**. `BigDecimal` phù hợp hơn `double` cho các bài toán cần kiểm soát chữ số thập phân chính xác. Demo không định nghĩa currency, thuế hoặc rounding nghiệp vụ; `LocalizedAmount` chỉ là value object học formatting.

### 4.2. Thiết kế parser/printer cùng một số quy tắc

~~~java
package com.example.localeformat;

import org.springframework.format.Formatter;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocalizedAmountFormatter
        implements Formatter<LocalizedAmount> {

    private static final String PATTERN = "#,##0.00";

    private DecimalFormat newFormat(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                PATTERN, DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);
        return format;
    }

    @Override
    public String print(LocalizedAmount amount, Locale locale) {
        if (amount.value().scale() > 2) {
            throw new IllegalArgumentException(
                    "Amount has more than 2 fraction digits");
        }
        return newFormat(locale).format(amount.value());
    }

    @Override
    public LocalizedAmount parse(String text, Locale locale)
            throws ParseException {

        DecimalFormat format = newFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (!(parsed instanceof BigDecimal decimal)
                || position.getIndex() != text.length()
                || decimal.scale() > 2
                || !format.format(decimal).equals(text)) {
            throw new ParseException(
                    "Amount must have canonical locale format", 0);
        }

        return new LocalizedAmount(decimal);
    }
}
~~~

Đây là **toàn bộ class có thể biên dịch** cùng record `LocalizedAmount` và dependency `spring-context` (được kéo vào bởi starter web trong project).

Giải thích từng thiết kế:
- `new DecimalFormat(PATTERN, DecimalFormatSymbols.getInstance(locale))` chọn dấu phân cách theo locale.
- `PATTERN="#,##0.00"` dùng grouping và **đúng hai chữ số thập phân** ở output.
- `setParseBigDecimal(true)` để parser trả `BigDecimal`, không dựa vào binary floating-point.
- `ParsePosition` giúp kiểm tra parser tiêu thụ **toàn bộ** input. Java number parsers có thể chấp nhận prefix rồi bỏ lại hậu tố nếu không kiểm tra.
- `format.format(decimal).equals(text)` thực thi tính canonical: nếu input khác cách hiển thị đã định, parser từ chối.
- `scale()>2` tránh làm tròn lặng lẽ khi in/nhập một giá trị có hơn hai chữ số thập phân.
- Mỗi lần gọi tạo `DecimalFormat` mới, vì `DecimalFormat` **không thread-safe**.
- Không gọi `Locale.setDefault` hoặc `DecimalFormatSymbols.set...` toàn JVM trong parser.

Với `Locale.US`:

~~~text
print(LocalizedAmount(1234.50), en-US) -> "1,234.50"
parse("1,234.50", en-US) -> LocalizedAmount(BigDecimal("1234.50"))
~~~

Với `Locale.GERMANY`:

~~~text
print(LocalizedAmount(1234.50), de-DE) -> "1.234,50"
parse("1.234,50", de-DE) -> LocalizedAmount(BigDecimal("1234.50"))
~~~

Đây là hai ví dụ có separators thông dụng trong JDK Java 17. Với tiếng Pháp và tiếng Việt, test sẽ lấy output từ chính `DecimalFormatSymbols`/formatter đang chạy rồi kiểm tra round-trip, tránh hard-code dấu nhóm nghìn của mọi CLDR version.

**Giới hạn có chủ đích:** formatter ví dụ không xử lý currency code, negative zero, khoảng trắng tùy ý, số có nhiều hơn hai decimals hoặc số liệu định lượng quá lớn. Khi làm sản phẩm tiền tệ thật, cân nhắc JSR-354/Moneta, currency code/scale, policy rounding, chính sách số âm và định dạng nhập liệu quốc tế.

### 4.3. Sai locale và input không canonical

Bảng kiểm thử:

| Locale dùng để parse | Input | Kỳ vọng |
| --- | --- | --- |
| `en-US` | `1,234.50` | Hợp lệ |
| `de-DE` | `1.234,50` | Hợp lệ |
| `en-US` | `1.234,50` | `ParseException` |
| `de-DE` | `1,234.50` | `ParseException` |
| `en-US` | `1,234.50xyz` | `ParseException` |
| `en-US` | `1234.50` | `ParseException` do không canonical |
| `en-US` | `1,234.567` | `ParseException` do quá hai decimals |
| `en-US` | Chuỗi rỗng | Parse thất bại; với Spring binder cần kiểm tra xử lý null/empty riêng |

Việc bắt buộc grouping trong ví dụ là policy, không phải quy tắc tự nhiên của mọi Locale. Form UX có thể cho phép `1234.50` và chỉ chuẩn hóa thành `1,234.50`; khi đó bỏ điều kiện exact canonical check và viết tests mới tương ứng.

## 5. Formatter cho ngày có tên tháng theo Locale

Để test locale ở ngày tháng mà không phụ thuộc vào múi giờ, dùng `LocalDate`. Record:

~~~java
package com.example.localeformat;

import java.time.LocalDate;
import java.util.Objects;

public record ScheduleDay(LocalDate value) {
    public ScheduleDay {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Formatter:

~~~java
package com.example.localeformat;

import org.springframework.format.Formatter;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public final class ScheduleDayFormatter
        implements Formatter<ScheduleDay> {

    private DateTimeFormatter newFormat(Locale locale) {
        return DateTimeFormatter.ofPattern(
                        "dd MMM uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public String print(ScheduleDay day, Locale locale) {
        return day.value().format(newFormat(locale));
    }

    @Override
    public ScheduleDay parse(String text, Locale locale)
            throws ParseException {
        try {
            return new ScheduleDay(
                    LocalDate.parse(text, newFormat(locale)));
        } catch (DateTimeParseException badDate) {
            throw new ParseException(
                    "Invalid day for selected locale", 0);
        }
    }
}
~~~

- `dd`: ngày hai chữ số.
- `MMM`: tên tháng dạng viết tắt **theo locale**, giúp minh họa khác biệt ngôn ngữ.
- `uuuu`: proleptic year, phù hợp với strict date parsing khi pattern không có era.
- `ResolverStyle.STRICT`: từ chối ngày không tồn tại như 31/02 thay vì tự chỉnh ngày.
- `DateTimeFormatter` immutable và thread-safe; formatter tạo từ locale mỗi lần dùng để rõ contract. Nếu caching, hãy thiết kế cache an toàn và kiểm tra memory footprint.
- Trả `ParseException` khi input sai để phù hợp hướng dẫn của `Formatter.parse` và Spring binding errors.

Không viết cứng expected date text cho `fr-FR` và `vi-VN` trong mọi build. Tên tháng viết tắt, dấu chấm và cách ngắt có thể khác giữa JDK/CLDR versions. Test chính xác là tạo output bằng formatter đang dùng cho locale rồi parse trở lại **cùng ngày**, đồng thời test khác nhau/định dạng khi có yêu cầu product cố định.

Nếu API yêu cầu **format ngày bất biến theo locale**, ưu tiên ISO `2026-09-15` với `DateTimeFormatter.ISO_LOCAL_DATE`, không dùng tên tháng localized. Tách field dành cho hiển thị khỏi kiểu dữ liệu wire protocol là một quyết định API quan trọng.

## 6. Tích hợp Spring: ConverterService, DataBinder và MVC

### 6.1. Khác biệt giữa formatter trực tiếp và adapter

Khi gọi trực tiếp:

~~~java
LocalizedAmountFormatter formatter =
        new LocalizedAmountFormatter();

String german = formatter.print(
        new LocalizedAmount(
                new BigDecimal("1234.50")),
        Locale.GERMANY);
~~~

ta truyền `Locale.GERMANY` tường minh. Nhưng trong `ConversionService#convert` chữ ký không nhận locale:

~~~java
<T> T convert(Object source, Class<T> targetType);
~~~

Spring adapter lấy locale từ `LocaleContextHolder` khi áp dụng formatter. Do đó test cần thiết lập locale context đúng cách, không rely vào JVM default.

### 6.2. Đăng ký toàn MVC

~~~java
package com.example.localeformat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFormattingConfig implements WebMvcConfigurer {

    @Bean
    public LocalizedAmountFormatter amountFormatter() {
        return new LocalizedAmountFormatter();
    }

    @Bean
    public ScheduleDayFormatter dayFormatter() {
        return new ScheduleDayFormatter();
    }

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public WebFormattingConfig(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(amounts);
        registry.addFormatter(days);
    }
}
~~~

**Lưu ý về wiring:** đoạn config trên thể hiện **một ý tưởng hợp lý** nhưng có một dependency-cycle tinh vi: chính `@Configuration` này có constructor cần các bean `amountFormatter`/`dayFormatter` do nó khai báo bằng non-static `@Bean` methods. Khi tạo configuration instance, Spring cần constructor dependencies trước khi gọi bean methods, nên cách thiết kế như vậy có thể gây circular dependency. **Để có project runnable chắc chắn, ta dùng cách an toàn ở mục 8: định nghĩa mỗi formatter là một `@Component` độc lập, và config constructor-inject chúng mà không tự khai báo chúng bằng `@Bean` cùng class.** Đừng sao chép config trên vào project ở mục 8.

Nguyên tắc của `addFormatters` vẫn đúng: Spring MVC dùng một `FormattingConversionService` được cấu hình cho binding. Với WebFlux, cách đăng ký tương ứng là `WebFluxConfigurer#addFormatters(FormatterRegistry)`, nhưng integration HTTP và exception handling phải dùng reactive stack.

### 6.3. `@InitBinder` và formatter scope

Nếu một form riêng cần quy tắc cục bộ, `WebDataBinder` có thể đăng ký formatter theo field:

~~~java
@InitBinder("bookingForm")
void initBooking(WebDataBinder binder) {
    binder.setAllowedFields("amount", "day");
}
~~~

Ở đây không cần thêm formatter local vì formatter cho `LocalizedAmount` và `ScheduleDay` đã đăng ký trong MVC ConversionService. Không trộn các formatters cùng kiểu/đường dẫn chồng chéo mà không test precedence; một conversion policy rõ ràng sẽ dễ bảo trì hơn.

Nếu dùng `binder.addCustomFormatter(formatter, "fieldName")` cho riêng field, cần xác minh các phiên bản Spring và scope. Không dùng `@InitBinder` để kỳ vọng Jackson JSON `@RequestBody` chạy qua formatter của form.

### 6.4. `@NumberFormat`, `@DateTimeFormat` và annotation formatting

Spring đã có:

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate day;
~~~

Đây là **fields minh họa** trong một DTO, cần imports `org.springframework.format.annotation.NumberFormat` và `DateTimeFormat`. `@NumberFormat` có thể dùng `style` hoặc `pattern`; `@DateTimeFormat` có `iso` và `pattern`. Khi dùng ISO DATE, chuỗi `yyyy-MM-dd` được chọn để giao tiếp ổn định thay vì localized month name.

Tuy nhiên, đừng cho rằng các annotations đều làm Jackson deserialize JSON theo cùng cách. Jackson/`HttpMessageConverter` có các thiết lập riêng như `@JsonFormat`/modules, cần kiểm thử `@RequestBody` độc lập.

## 7. Dự án runnable: cấu trúc và dependencies

Project sử dụng **Spring MVC** và `spring-boot-starter-web` để minh họa form binding; không thêm WebFlux starter vào cùng ví dụ.

~~~text
pom.xml
src/main/java/com/example/localeformat/
  LocaleFormatApplication.java
  LocalizedAmount.java
  ScheduleDay.java
  LocalizedAmountFormatter.java
  ScheduleDayFormatter.java
  WebFormattingConfig.java
  BookingForm.java
  BookingController.java
src/test/java/com/example/localeformat/
  LocalizedFormatterTest.java
  ConversionServiceLocaleTest.java
  BookingControllerLocaleTest.java
~~~

### 7.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>locale-format-test-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, parameterized tests và MockMvc. `spring-boot-starter-validation` cho phép dùng Jakarta `@NotNull` trong form DTO. Demo không có database.

### 7.2. Main application

~~~java
// src/main/java/com/example/localeformat/LocaleFormatApplication.java
package com.example.localeformat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocaleFormatApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocaleFormatApplication.class, args);
    }
}
~~~

### 7.3. `LocalizedAmount.java`

~~~java
// src/main/java/com/example/localeformat/LocalizedAmount.java
package com.example.localeformat;

import java.math.BigDecimal;
import java.util.Objects;

public record LocalizedAmount(BigDecimal value) {
    public LocalizedAmount {
        Objects.requireNonNull(value, "value");
    }
}
~~~

### 7.4. `ScheduleDay.java`

~~~java
// src/main/java/com/example/localeformat/ScheduleDay.java
package com.example.localeformat;

import java.time.LocalDate;
import java.util.Objects;

public record ScheduleDay(LocalDate value) {
    public ScheduleDay {
        Objects.requireNonNull(value, "value");
    }
}
~~~

### 7.5. `LocalizedAmountFormatter.java`

~~~java
// src/main/java/com/example/localeformat/LocalizedAmountFormatter.java
package com.example.localeformat;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

@Component
public final class LocalizedAmountFormatter
        implements Formatter<LocalizedAmount> {

    private DecimalFormat newFormat(Locale locale) {
        DecimalFormat result = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(locale));
        result.setParseBigDecimal(true);
        return result;
    }

    @Override
    public String print(LocalizedAmount amount, Locale locale) {
        if (amount.value().scale() > 2) {
            throw new IllegalArgumentException(
                    "More than 2 decimal places");
        }
        return newFormat(locale).format(amount.value());
    }

    @Override
    public LocalizedAmount parse(String text, Locale locale)
            throws ParseException {
        DecimalFormat format = newFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(text, position);

        if (!(value instanceof BigDecimal amount)
                || position.getIndex() != text.length()
                || amount.scale() > 2
                || !format.format(amount).equals(text)) {
            throw new ParseException(
                    "Non-canonical localized amount", 0);
        }

        return new LocalizedAmount(amount);
    }
}
~~~

### 7.6. `ScheduleDayFormatter.java`

~~~java
// src/main/java/com/example/localeformat/ScheduleDayFormatter.java
package com.example.localeformat;

import org.springframework.format.Formatter;
import org.springframework.stereotype.Component;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

@Component
public final class ScheduleDayFormatter
        implements Formatter<ScheduleDay> {

    private DateTimeFormatter newFormat(Locale locale) {
        return DateTimeFormatter.ofPattern(
                        "dd MMM uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public String print(ScheduleDay day, Locale locale) {
        return day.value().format(newFormat(locale));
    }

    @Override
    public ScheduleDay parse(String text, Locale locale)
            throws ParseException {
        try {
            return new ScheduleDay(
                    LocalDate.parse(text, newFormat(locale)));
        } catch (DateTimeParseException ex) {
            throw new ParseException(
                    "Invalid localized day", 0);
        }
    }
}
~~~

### 7.7. `WebFormattingConfig.java` — cấu hình đúng lifecycle

~~~java
// src/main/java/com/example/localeformat/WebFormattingConfig.java
package com.example.localeformat;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public WebFormattingConfig(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(amounts);
        registry.addFormatter(days);
    }
}
~~~

Hai formatter đã có `@Component` ở các class riêng, nên constructor của `WebFormattingConfig` inject được các singleton đó mà không tạo vòng phụ thuộc `@Bean`. **Đây là cấu hình thực sự dùng trong project runnable**. Spring MVC đưa các formatters vào binding ConversionService. Chúng thread-safe vì mỗi lần parse/print tạo formatter/parser state tương ứng thay vì chia sẻ `DecimalFormat` mutable.

### 7.8. `BookingForm.java`

~~~java
// src/main/java/com/example/localeformat/BookingForm.java
package com.example.localeformat;

import jakarta.validation.constraints.NotNull;

public class BookingForm {

    @NotNull
    private LocalizedAmount amount;

    @NotNull
    private ScheduleDay day;

    public BookingForm() {}

    public LocalizedAmount getAmount() {
        return amount;
    }

    public void setAmount(LocalizedAmount amount) {
        this.amount = amount;
    }

    public ScheduleDay getDay() {
        return day;
    }

    public void setDay(ScheduleDay day) {
        this.day = day;
    }
}
~~~

`@NotNull` đảm bảo hai fields có giá trị **sau conversion** khi validation thực sự chạy. Nó không thay cho kiểm tra malformed number hoặc malformed date; các lỗi đó xuất hiện ở binding trước validation. DTO chỉ chứa hai fields công khai, tránh bind trực tiếp domain/JPA entity.

### 7.9. `BookingController.java`

~~~java
// src/main/java/com/example/localeformat/BookingController.java
package com.example.localeformat;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final LocalizedAmountFormatter amounts;
    private final ScheduleDayFormatter days;

    public BookingController(
            LocalizedAmountFormatter amounts,
            ScheduleDayFormatter days) {
        this.amounts = amounts;
        this.days = days;
    }

    @InitBinder("bookingForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("amount", "day");
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Locale locale) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("invalidFields", fields));
        }

        return ResponseEntity.ok(Map.of(
                "amount", form.getAmount().value().toPlainString(),
                "date", form.getDay().value().toString(),
                "amountText", amounts.print(form.getAmount(), locale),
                "dateText", days.print(form.getDay(), locale)
        ));
    }
}
~~~

Controller minh họa **hai đường chạy đồng bộ trong Spring MVC**:
1. Spring lấy locale từ request resolver và chuyển form strings sang `LocalizedAmount`/`ScheduleDay` bằng formatters đã đăng ký.
2. Controller gọi `print` theo `Locale` của request để trả các chuỗi đã được chuẩn hóa.
3. Nếu lỗi conversion hoặc `@NotNull`, `BindingResult` đứng ngay sau `@ModelAttribute` nên có thể trả HTTP 400 với tên fields.
4. `allowedFields` chỉ cho phép `amount`/`day` bằng property binding. Nếu có thêm fields ngoài hợp đồng, chúng có thể bị suppress; demo tập trung kiểm thử parse/print và chưa tạo handler phản hồi riêng cho `getSuppressedFields()`.

**Không đọc response JSON ở `amountText` rồi kỳ vọng Jackson tự gọi Formatter.** Ở đây controller gọi `amounts.print(...)` rõ ràng. Với `@RequestBody` JSON, Jackson deserialization là đường khác với `WebDataBinder` của `@ModelAttribute`.

## 8. Unit tests: parse, print và round-trip trên bốn Locale

### 8.1. `LocalizedFormatterTest.java`

~~~java
// src/test/java/com/example/localeformat/LocalizedFormatterTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.time.LocalDate;
import java.util.Locale;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalizedFormatterTest {

    private final LocalizedAmountFormatter amounts =
            new LocalizedAmountFormatter();
    private final ScheduleDayFormatter days =
            new ScheduleDayFormatter();

    static Stream<Locale> locales() {
        return Stream.of(
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.forLanguageTag("vi-VN"));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void amountPrintParseRoundTrip(Locale locale)
            throws ParseException {

        LocalizedAmount original =
                new LocalizedAmount(new BigDecimal("1234.50"));

        String printed = amounts.print(original, locale);
        LocalizedAmount parsed = amounts.parse(printed, locale);

        assertEquals(0,
                parsed.value().compareTo(original.value()));
        assertEquals(printed,
                amounts.print(parsed, locale));

        // Bảo đảm grouping/decimal separator theo locale.
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        assertTrue(printed.contains(
                String.valueOf(symbols.getGroupingSeparator())));
        assertTrue(printed.contains(
                String.valueOf(symbols.getDecimalSeparator())));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void dayPrintParseRoundTrip(Locale locale)
            throws ParseException {

        ScheduleDay original =
                new ScheduleDay(LocalDate.of(2026, 9, 15));

        String printed = days.print(original, locale);
        ScheduleDay parsed = days.parse(printed, locale);

        assertEquals(original, parsed);
        assertEquals(printed, days.print(parsed, locale));
    }

    @Test
    void knownUsAndGermanAmountRepresentations()
            throws ParseException {

        LocalizedAmount amount =
                new LocalizedAmount(new BigDecimal("1234.50"));

        assertEquals("1,234.50",
                amounts.print(amount, Locale.US));
        assertEquals("1.234,50",
                amounts.print(amount, Locale.GERMANY));

        assertEquals(amount,
                amounts.parse("1,234.50", Locale.US));
        assertEquals(amount,
                amounts.parse("1.234,50", Locale.GERMANY));
        assertNotEquals(
                amounts.print(amount, Locale.US),
                amounts.print(amount, Locale.GERMANY));
    }

    @Test
    void wrongLocaleSeparatorsAreRejected() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1.234,50", Locale.US));
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.50", Locale.GERMANY));
    }

    @Test
    void trailingGarbageCannotBeSilentlyIgnored() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.50ignored", Locale.US));
    }

    @Test
    void nonCanonicalAndTooPreciseInputAreRejected() {
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1234.50", Locale.US));
        assertThrows(ParseException.class,
                () -> amounts.parse(
                        "1,234.567", Locale.US));
    }

    @Test
    void printingDoesNotRoundAwayExtraPrecision() {
        LocalizedAmount tooPrecise =
                new LocalizedAmount(new BigDecimal("1.234"));

        assertThrows(IllegalArgumentException.class,
                () -> amounts.print(tooPrecise, Locale.US));
    }

    @Test
    void strictDateParserRejectsImpossibleDay() {
        assertThrows(ParseException.class,
                () -> days.parse(
                        "31 Feb 2026", Locale.US));
    }
}
~~~

Trong `@ParameterizedTest`, **mỗi locale là một invocation riêng**. Hai methods round-trip tạo tổng cộng tám invocations, và sáu regular `@Test` kiểm tra các biên. Không đánh đồng “hai methods” với “hai test executions”.

**Tại sao không assert chuỗi ngày tiếng Pháp/Việt cụ thể?** Vì mục tiêu ở đây là round-trip đúng theo formatter/JDK đang chạy. Khi product yêu cầu một chuỗi UI cố định, dùng riêng snapshot/contract tests trên JDK version đã pin và dữ liệu locale đã được duyệt; không trói unit test lõi vào một ký tự Unicode tình cờ khác giữa providers.

### 8.2. Kiểm tra input rỗng và âm

Các trường hợp bổ sung cần đưa vào test suite của ứng dụng:
- `""`, `" "`, `null`: trong binding, Spring có thể coi empty input là null trước khi gọi formatter; dùng `@NotNull` để bắt trường bắt buộc.
- `-1,234.50`, `(1,234.50)`: xử lý số âm theo product, không mặc định mọi locale có cùng cú pháp.
- `0.00`: parse thành zero, và business validation quyết định cho phép hay không.
- Dấu plus, dấu trừ Unicode, non-breaking space và zero-width characters.
- Số quá lớn khiến giới hạn ngân sách/BigDecimal scale và DoS.
- Locale không được hỗ trợ: xác định fallback/HTTP 400 theo policy.

Một parser được test “đủ tốt” không phải chỉ parse thành công một giá trị; nó còn phải **từ chối đúng những input không thuộc contract**.

## 9. Unit tests: ConversionService và WebDataBinder sử dụng Locale nào?

### 9.1. `ConversionServiceLocaleTest.java`

~~~java
// src/test/java/com/example/localeformat/ConversionServiceLocaleTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.web.bind.WebDataBinder;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ConversionServiceLocaleTest {

    private static FormattingConversionService service() {
        FormattingConversionService service =
                new FormattingConversionService();
        service.addFormatter(new LocalizedAmountFormatter());
        service.addFormatter(new ScheduleDayFormatter());
        return service;
    }

    @Test
    void conversionServiceUsesLocaleContextForBothDirections() {
        FormattingConversionService conversion = service();

        LocalizedAmount original =
                new LocalizedAmount(new BigDecimal("1234.50"));
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();

        try {
            for (Locale locale : new Locale[]{
                    Locale.US, Locale.GERMANY,
                    Locale.FRANCE,
                    Locale.forLanguageTag("vi-VN")}) {

                LocaleContextHolder.setLocale(locale);

                String printed = conversion.convert(
                        original, String.class);
                LocalizedAmount parsed = conversion.convert(
                        printed, LocalizedAmount.class);

                assertEquals(original, parsed);
                assertEquals(printed, conversion.convert(
                        parsed, String.class));
            }
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }

    @Test
    void webDataBinderUsesRegisteredFormattersForFields() {
        BookingForm form = new BookingForm();
        WebDataBinder binder =
                new WebDataBinder(form, "bookingForm");
        binder.setConversionService(service());

        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();

        try {
            LocaleContextHolder.setLocale(Locale.GERMANY);

            ScheduleDayFormatter days =
                    new ScheduleDayFormatter();
            String localizedDate = days.print(
                    new ScheduleDay(LocalDate.of(2026, 9, 15)),
                    Locale.GERMANY);

            binder.bind(new MutablePropertyValues(Map.of(
                    "amount", "1.234,50",
                    "day", localizedDate
            )));

            assertFalse(binder.getBindingResult().hasErrors());
            assertEquals(new LocalizedAmount(
                            new BigDecimal("1234.50")),
                    form.getAmount());
            assertEquals(new ScheduleDay(
                            LocalDate.of(2026, 9, 15)),
                    form.getDay());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }
}
~~~

`FormattingConversionService` là loại phù hợp để test registry vì nó triển khai `FormatterRegistry`. `LocaleContextHolder.setLocale(...)` tác động đến adapter parse/print trong luồng test đồng bộ. Đoạn `finally` khôi phục **LocaleContext trước đó**, tránh nhiễm state giữa tests.

`WebDataBinder` trong test dùng cùng conversion service thủ công; nếu chỉ kiểm thử `Formatter.parse` trực tiếp mà bỏ hai tầng này, ta có thể bỏ lỡ lỗi đăng ký formatter (ví dụ class không được scan hoặc `addFormatters` không được gọi).

**Cảnh báo:** `LocaleContextHolder` dùng ngữ cảnh theo thread, không phải cơ chế tự chuyển qua mọi Reactor scheduler. Với WebFlux, test qua `WebTestClient` và context propagation phù hợp; đừng tự gọi `setLocale` rồi mong mọi luồng bất đồng bộ nhìn thấy nó.

## 10. HTTP integration tests với MockMvc theo nhiều Locale

### 10.1. `BookingControllerLocaleTest.java`

~~~java
// src/test/java/com/example/localeformat/BookingControllerLocaleTest.java
package com.example.localeformat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;
import java.util.stream.Stream;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerLocaleTest {

    @Autowired MockMvc mvc;
    @Autowired LocalizedAmountFormatter amounts;
    @Autowired ScheduleDayFormatter days;

    static Stream<Locale> locales() {
        return Stream.of(
                Locale.US, Locale.GERMANY,
                Locale.FRANCE, Locale.forLanguageTag("vi-VN"));
    }

    @ParameterizedTest
    @MethodSource("locales")
    void formBindingAndPrintingUseRequestLocale(Locale locale)
            throws Exception {

        LocalizedAmount amount =
                new LocalizedAmount(new BigDecimal("1234.50"));
        ScheduleDay day =
                new ScheduleDay(LocalDate.of(2026, 9, 15));

        String amountText = amounts.print(amount, locale);
        String dayText = days.print(day, locale);

        mvc.perform(post("/api/bookings/form")
                    .locale(locale)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", amountText)
                    .param("day", dayText))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"))
                .andExpect(jsonPath("$.date")
                        .value("2026-09-15"))
                .andExpect(jsonPath("$.amountText")
                        .value(amountText))
                .andExpect(jsonPath("$.dateText")
                        .value(dayText));
    }

    @Test
    void wrongNumberForGermanLocaleIsBindingError()
            throws Exception {

        String correctDay = days.print(
                new ScheduleDay(LocalDate.of(2026, 9, 15)),
                Locale.GERMANY);

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.GERMANY)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", "1,234.50")
                    .param("day", correctDay))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("amount")));
    }

    @Test
    void wrongDateIsBindingError() throws Exception {

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.US)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("amount", "1,234.50")
                    .param("day", "31 Feb 2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("day")));
    }

    @Test
    void missingRequiredAmountIsValidationError()
            throws Exception {

        String correctDay = days.print(
                new ScheduleDay(LocalDate.of(2026, 9, 15)),
                Locale.US);

        mvc.perform(post("/api/bookings/form")
                    .locale(Locale.US)
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("day", correctDay))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.invalidFields",
                        hasItem("amount")));
    }
}
~~~

Dùng `.locale(locale)` trên `MockHttpServletRequestBuilder` để kiểm thử locale request một cách rõ ràng. Điều này khác với việc chỉ tạo `Locale.US` trong unit test và cho rằng controller tự dùng nó.

Phần test dùng cùng formatter được Spring inject để tạo input tương thích với locale ở runtime; sau đó assert **đầu ra đã normalized**. Test này không xác nhận một client độc lập có thể tạo đúng glyph cho từng locale; muốn bao phủ wire interoperability, thêm contract tests với input fixtures lấy từ UI/product của locale đó.

### 10.2. Lệnh chạy

~~~bash
mvn test
~~~

Chạy riêng lớp test:

~~~bash
mvn -Dtest=LocalizedFormatterTest test
mvn -Dtest=ConversionServiceLocaleTest test
mvn -Dtest=BookingControllerLocaleTest test
~~~

Bộ source có:
- `LocalizedFormatterTest`: 2 parameterized methods × 4 locales = 8 invocations, cộng 6 unit tests = **14 invocations**.
- `ConversionServiceLocaleTest`: 2 tests.
- `BookingControllerLocaleTest`: 1 parameterized method × 4 locales = 4 invocations, cộng 3 tests = 7 invocations.

**Tổng cộng 23 JUnit invocations dự kiến.** Đây là phép đếm từ code được cung cấp; kết quả PASS là kỳ vọng sau khi build trong môi trường Spring Boot/JDK phù hợp, **không phải một báo cáo Maven đã chạy**.

Nếu test không pass, kiểm tra package scanning, version Spring 6.2, locale/CLDR của JDK, conversion service đang được MVC sử dụng, và những lỗi parsing cụ thể. Không xóa một locale test thất bại chỉ để CI xanh: nó có thể tiết lộ dữ liệu người dùng bị diễn giải khác trên một môi trường.

### 10.3. Chạy server và thử bằng HTTP

~~~bash
mvn spring-boot:run
~~~

Ví dụ với `en-US`, có thể gửi:

~~~bash
curl -i -X POST http://localhost:8080/api/bookings/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: en-US" \
  --data-urlencode "amount=1,234.50" \
  --data-urlencode "day=15 Sep 2026"
~~~

Kết quả JSON kỳ vọng khi format/JDK hiện hành cho `en-US` khớp:

~~~json
{
  "amount": "1234.50",
  "date": "2026-09-15",
  "amountText": "1,234.50",
  "dateText": "15 Sep 2026"
}
~~~

Trên `de-DE`, gửi amount `1.234,50` và day được tạo bằng formatter tiếng Đức. Đừng tự thay `Sep` thành một từ tiếng Đức theo phỏng đoán: dùng output của formatter/JDK thật hoặc fixture đã được phê duyệt.

Lưu ý lệnh shell `\` nối dòng phù hợp Linux/macOS/Git Bash. PowerShell cần syntax nối dòng riêng hoặc `curl.exe` một dòng.

## 11. Những điều có thể khiến bài test đa Locale sai dù code không sai

### 11.1. JDK/CLDR/locale provider khác nhau

Java có nguồn dữ liệu locale thay đổi theo provider và version. Ví dụ cách viết tắt tên tháng trong tiếng Pháp, dấu nhóm nghìn `fr-FR` hay glyph của một script có thể khác giữa các runtime. Vì vậy chia tests thành hai nhóm:
- **Behavioral/round-trip tests:** giá trị được print và parse tương đương, hoạt động với dữ liệu locale runtime hiện tại.
- **Golden-output/contract tests:** so chuỗi chính xác được product duyệt; phải pin JDK, locale provider và cập nhật snapshot một cách có review khi nâng version.

Không dùng `String.replace(" ", "")` để làm test “pass” khi gặp non-breaking space: nó che sự khác biệt Unicode thật. Nếu có normalization được product chấp thuận, implement và test cụ thể, không sửa trong assertion.

### 11.2. Default locale làm test phụ thuộc máy

~~~java
// Không tốt cho test ổn định:
Locale locale = Locale.getDefault();
~~~

Trên laptop ngôn ngữ Anh, test có thể pass; trên runner tiếng Đức hoặc Việt, parse/print khác. Trong test, dùng `Locale.US`/`Locale.GERMANY`/`Locale.FRANCE`/`Locale.forLanguageTag("vi-VN")` tường minh. Với `LocaleContextHolder`, lưu trạng thái cũ và khôi phục `finally`.

Tránh test song song nếu cùng thao tác với **global** `Locale.setDefault(...)`. Ngay cả khi reset, việc đổi default JVM vẫn ảnh hưởng tests/threads khác trong khoảng thời gian đó.

### 11.3. Tách parse from binding/validation

~~~text
Input "1,234.50junk"
  |
  v
Formatter.parse -> ParseException
  |
  v
Spring DataBinder -> typeMismatch field error
  |
  v
BindingResult -> HTTP 400 do controller quyết định
~~~

Còn thiếu amount:

~~~text
Không có input field "amount"
  |
  v
BookingForm.amount == null
  |
  v
@Valid + @NotNull
  |
  v
BindingResult -> validation field error
~~~

Đừng assert mọi input sai đều có `@NotNull` error. Conversion failure và constraint violation là hai nguồn lỗi khác nhau. Với `@RequestBody` JSON, Jackson parse và `HttpMessageNotReadableException` thường là đường khác.

### 11.4. Locale không đồng nghĩa múi giờ

`LocalDate` biểu diễn ngày không có thời điểm/múi giờ. `Instant`, `OffsetDateTime` và `ZonedDateTime` có zone/offset semantics. Nếu form ghi `15/09/2026 23:30` ở một múi giờ, round-trip có thể thay ngày khi đổi zone; test cần cả `ZoneId`/DST. Đừng mở rộng `ScheduleDayFormatter` sang `Instant` mà chỉ thay generic type.

### 11.5. Grouping/decimal precision và BigDecimal scale

Với `BigDecimal("1.0")` và `BigDecimal("1.00")`:

~~~java
new BigDecimal("1.0").equals(
        new BigDecimal("1.00")); // false
new BigDecimal("1.0").compareTo(
        new BigDecimal("1.00")); // 0
~~~

Đây là đoạn minh họa biểu thức Java. Nếu unit test kiểm tra giá trị tiền theo ngữ nghĩa số, `compareTo` có thể đúng hơn `equals`; nếu cần giữ scale pháp lý, contract phải quy định scale và cách serialize. Formatter ví dụ in đúng hai decimals, nên một giá trị `1.0` có thể được chuẩn hóa sang `1.00` khi round-trip.

### 11.6. Thread safety và nhiều requests đồng thời

`DecimalFormat` không thread-safe; formatter ví dụ tạo instance mới mỗi lần `parse`/`print`. Nếu formatter cache một `DecimalFormat` dùng chung, tests đơn luồng có thể pass nhưng production concurrent requests làm lệch format. Có thể thêm test dùng `ExecutorService` để gọi parse/print đồng thời trên formatter singleton qua nhiều locale, nhưng cần tránh false positives/flaky assertions và không chia sẻ mutable number formatter.

### 11.7. Locale của message khác locale của giá trị

`MessageSource` quyết định ngôn ngữ lỗi, còn `Formatter` quyết định cách parse/print theo locale. Thường cả hai dùng locale của request, nhưng có thể có nghiệp vụ cố định: ví dụ file CSV nhập luôn chuẩn ISO/US dù UI tiếng Việt. Hãy document hai policies:
- **UI display locale:** cho frontend và thông báo.
- **Data wire format:** có thể cố định và locale-independent.

Nếu API JSON phục vụ nhiều máy, ưu tiên wire format ổn định thay vì localized text để trao đổi số/ngày. Formatting localized thích hợp cho form/UI.

## 12. Kiểm thử sâu hơn: property-specific, annotation và HTTP stack

### 12.1. Field có annotation riêng

Nếu cùng một object có hai fields `LocalDate` nhưng muốn một field ISO và một field localized, `@DateTimeFormat` theo field có thể phù hợp hơn một global `Formatter<LocalDate>`. Khi thiết kế tests:
1. Định nghĩa source/target type và annotation chính xác.
2. Test cả conversion khi field có annotation và khi field không có.
3. Đảm bảo `@InitBinder`/global formatter không override ngoài dự kiến.
4. Test bad input trở thành `FieldError` ở đúng path.

### 12.2. Indexed fields/nested object

Một form có `List<LineItem>` có thể gửi `items[0].price=1.234,50`, `items[1].price=2.345,60`. Nếu `price` là `LocalizedAmount`, Spring dùng formatter của type đó khi bind nested element. Bài test cần:
- Locale chính xác.
- `items[0].price`/`items[1].price` đúng index.
- Allowed field paths như `items[*].price`.
- Giới hạn auto-grow `setAutoGrowCollectionLimit` và request body size.
- Không bind `items[*].approved` hoặc role/owner fields từ client.

Những field paths bị suppress không nhất thiết làm `BindingResult#hasErrors()` true; nếu security policy muốn reject extra fields, kiểm tra `getSuppressedFields()` riêng.

### 12.3. MVC và WebFlux khác tầng HTTP, giống SPI formatter

Với MVC, `MockMvc` giúp kiểm tra locale resolver/formatting trên Servlet stack. Với WebFlux, dùng `WebTestClient` và `WebFluxConfigurer#addFormatters`. `Formatter<T>`/`ConversionService` là SPI chung của Spring, nhưng cách lấy locale trong một reactive chain cần kiểm chứng; không dựa vào `LocaleContextHolder` ThreadLocal được propagate ngầm qua mọi scheduler.

Nếu production dùng WebFlux, hãy chuyển integration test sang reactive context thật; không dùng `MockMvc` để khẳng định WebFlux hoạt động.

## 13. Debug các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Locale=en-US nhưng giá trị parse kiểu de-DE | Sai request LocaleResolver hoặc default locale | Test `.locale(Locale.US)`, kiểm tra `LocaleContextHolder` |
| Direct formatter test pass, MVC fail | Quên `WebMvcConfigurer#addFormatters` | Kiểm tra registry và integration test |
| Số có suffix `junk` vẫn được parse | `NumberFormat` chỉ parse prefix | Dùng `ParsePosition` và so index == length |
| `1234.50` bị từ chối | Demo quy định canonical grouping | Nới policy có chủ đích và đổi tests |
| `fr-FR` fail vì dấu cách | U+202F vs U+0020 hoặc JDK locale provider | Kiểm tra Unicode code points, không tự thay regex |
| Đổi JDK làm snapshot ngày fail | CLDR abbreviations/locale data thay đổi | Tách behavioral test và golden contract test |
| Formatter trả số bị mất decimals | Rounding/DecimalFormat pattern | Xác định scale và test full precision |
| `BigDecimal.equals` fail dù giá trị như nhau | Scale khác | Dùng `compareTo` nếu contract chỉ quan tâm numeric value |
| Cùng formatter singleton bị lỗi ngẫu nhiên | Shared mutable `DecimalFormat`/`SimpleDateFormat` | Tạo parser mới mỗi call hoặc dùng immutable formatters |
| Có `FieldError#typeMismatch` | ParseException trong binding | Test formatter riêng, kiểm tra input locale |
| Thiếu field nhưng không báo lỗi | Không có `@NotNull`/validation | Thêm constraint và test missing-field |
| JSON không dùng custom formatter | `@RequestBody` qua Jackson | Dùng DTO/Jackson modules và test riêng |
| API trả date ISO dù formatter dùng localized | JSON serializer không gọi `Formatter.print` | Print tường minh cho UI hoặc cấu hình JSON serializer |
| Test phá locale của test khác | Dùng `Locale.setDefault` hoặc quên reset context | Scoped `LocaleContextHolder` với `finally` |
| Grouping dấu chấm và dấu phẩy gây nhầm | Client gửi sai locale | Document accepted locale và test negative |
| Controller dùng `@Validated`/validator khác | Binding và validation lifecycle khác | Test đúng Spring app context |
| Form field nested không parse | Chưa có formatter cho target type hoặc path sai | Test type/field registration và nested indices |
| Đổi Locale giữa parse và print | Sử dụng locale không đồng nhất | Round-trip với cùng Locale và test mismatch |
| DateTimeFormatter strict thất bại với `yyyy` | Year-of-era thiếu era | Dùng `uuuu` cho strict parsing của year |
| Renderer dùng timezone mặc định | Nhầm Locale với ZoneId | Test timezone độc lập nếu type có thời điểm |

## 14. Checklist code review cho kiểm thử đa Locale

- [ ] Xác định rõ format nào phụ thuộc `Locale` và format nào là wire format độc lập locale.
- [ ] Kiểm thử **parse**, **print**, **parse(print(x))** và **print(parse(text))** theo quy tắc canonical.
- [ ] Chọn ít nhất `en-US`/`de-DE` và các locales sản phẩm thực sự hỗ trợ, ví dụ `fr-FR`/`vi-VN`.
- [ ] Test grouping separator, decimal separator, tháng viết tắt và ký tự Unicode không hiển thị.
- [ ] Test input sai separator, trailing garbage, quá nhiều chữ số thập phân, ngày không tồn tại và giá trị thiếu.
- [ ] Dùng `BigDecimal` cho nghiệp vụ cần chính xác, phân biệt numeric equality và scale equality.
- [ ] Không chia sẻ mutable `DecimalFormat`/`SimpleDateFormat` giữa threads.
- [ ] Cấu hình `FormatterRegistry` đúng MVC/WebFlux stack, rồi test qua `FormattingConversionService` và HTTP.
- [ ] Tránh global `Locale.setDefault` trong tests; dùng `LocaleContextHolder` có khôi phục context.
- [ ] Không hard-code locale strings cho `fr-FR`/`vi-VN` nếu chưa pin JDK/CLDR và contract.
- [ ] Có separate golden tests cho những chuỗi UI thực sự phải cố định giữa releases.
- [ ] `@Valid`/`@NotNull` xử lý dữ liệu thiếu, `BindingResult` xử lý conversion errors; không nhầm hai nguồn.
- [ ] Không giả định Jackson JSON đi qua `Formatter`/`@ModelAttribute` binder.
- [ ] Kiểm soát allowed field paths, input-size và collection index nếu form có nested objects.
- [ ] Khi nâng Java/Spring, chạy lại locale matrix và so differences có chủ đích.

## 15. Bài tập tự luyện

1. Thay `LocalizedAmountFormatter` để chấp nhận cả `1234.50` và `1,234.50` ở `en-US`, nhưng luôn print về `1,234.50`. Viết assertions tách accepted inputs và canonical output.
2. Bổ sung `ja-JP` và `ar-EG` vào locale matrix. Kiểm thử chữ số bản địa, bidi và Unicode; không giả định Latin digits.
3. Viết `Formatter<LocalDate>` với `FormatStyle.SHORT`, so sánh test round-trip với formatter `dd MMM uuuu` và thảo luận nguy cơ snapshot JDK/CLDR.
4. Test boundary `BigDecimal("1.00")`, `1.0`, `1.234`, số âm và zero. Xác định chính sách rounding/scale trước khi sửa parser.
5. Tạo form có `List<LocalizedAmount>`, gửi `items[0]` và `items[1]`. Test paths và allowlist, đồng thời áp collection limit.
6. Tạo màn hình có hai fields ngày, một theo ISO và một theo locale người dùng, dùng `@DateTimeFormat` tại field và kiểm thử độc lập.
7. Chuyển project sang WebFlux với `WebFluxConfigurer#addFormatters`, viết test WebTestClient locale headers; không sao chép `MockMvc`.
8. Dùng `LocaleContextHolder` trong một test đa luồng rồi giải thích vì sao trạng thái thread-local không tự động đi theo tất cả tasks.
9. Thiết kế message lỗi tiếng Việt/Anh cho amount parse failure bằng `MessageSource`; không dùng exception raw text hoặc rejected value làm public response.

## 16. Kết luận

Kiểm thử localized formatting không chỉ là xác minh một chuỗi có dấu phẩy hay dấu chấm. Một hệ thống Spring đáng tin cậy phải kiểm tra **hai chiều**, **nhiều Locale**, **các trường hợp lỗi** và **integration thực** từ Formatter qua ConversionService tới DataBinder/HTTP request.

Quy tắc dễ nhớ:

~~~text
value -> print(value, locale) -> localized text
localized text -> parse(text, locale) -> value

SAME locale + explicit contract + no silent truncation
    = predictable form binding and display
~~~

Hãy cố định *giá trị ngữ nghĩa* trong behavioral tests, chỉ cố định *exact localized string* khi product thực sự yêu cầu và runtime locale-data đã được quản trị. `Locale` là một phần của input contract, không phải một “biến toàn cục vô hại”.

## 17. Tài liệu tham khảo

- Spring Framework 6.2, **Spring Field Formatting** (Formatter/Printer/Parser): https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2, **Web MVC Type Conversion**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2, **FormattingConversionService Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/support/FormattingConversionService.html
- Spring Framework 6.2, **DefaultFormattingConversionService Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html
- Spring Framework 6.2, **NumberFormat Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/annotation/NumberFormat.html
- Spring Framework 6.2, **DateTimeFormat Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework 6.2, **WebMvcConfigurer.addFormatters Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework 6.2, **MVC @ModelAttribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Boot 3.5, **Spring MVC Conversion Service**: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Java 17, **DecimalFormat**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java 17, **DateTimeFormatter**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java 17, **Locale**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
