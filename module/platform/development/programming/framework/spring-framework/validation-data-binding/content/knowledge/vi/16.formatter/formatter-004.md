# FormattingConversionService kết hợp Formatter và Converter

## 1. Bài toán: một nơi chuyển kiểu và định dạng dữ liệu

Trong ứng dụng Spring, dữ liệu thường đi qua nhiều ranh giới: HTTP form/query parameters, model object, service và trang hiển thị. Một giá trị có thể cần được chuyển đổi thành kiểu Java, rồi biểu diễn lại thành chuỗi thân thiện với người dùng.

Ví dụ:

- Client gửi `"C-2048"`; model cần kiểu miền `CustomerId`.
- Form gửi `"03/2026"`; model cần `YearMonth`.
- Khi render lại form, `YearMonth.of(2026, 3)` cần được in thành `"03/2026"`.
- Một field `BigDecimal` có thể dùng mẫu số `#,##0.00` trong khi field khác dùng quy tắc định dạng riêng.

Spring có hai SPI bổ sung cho nhau:

- **`Converter<S, T>`** chuyển đổi tổng quát từ một kiểu nguồn sang một kiểu đích.
- **`Formatter<T>`** kết hợp parse chuỗi đầu vào thành object và print object thành chuỗi; nó phù hợp với dữ liệu hiển thị ở giao diện và có thể nhận `Locale`.

**`FormattingConversionService`** kết hợp hai thế giới này. Nó triển khai `ConversionService` để thực hiện chuyển kiểu và `FormatterRegistry` để đăng ký formatter, parser/printer, converter và annotation-based formatter factory. Nhờ vậy ứng dụng có thể khai báo các quy tắc định dạng/chuyển đổi tại một registry chung thay vì cấu hình rời rạc ở nhiều controller.

Mục tiêu bài học:

1. Phân biệt `Converter`, `Formatter`, `Printer`, `Parser`.
2. Hiểu quan hệ `FormattingConversionService` – `FormatterRegistry` – `ConversionService`.
3. Đăng ký một converter và một formatter vào cùng service.
4. Dùng `Locale` khi parse/print và hiểu annotation formatting.
5. Tích hợp registry vào Spring MVC bằng `WebMvcConfigurer#addFormatters`.
6. Kiểm thử cả hai chiều conversion, input không hợp lệ và cách Spring DataBinder sử dụng service.

Ví dụ dùng **Java 17+ và Spring Framework 6.2.x**. Các API cơ bản được giữ ổn định trong những phiên bản Spring gần đây; hãy dùng BOM/plugin của Spring Boot nếu dự án quản lý dependency bằng Boot.

## 2. Converter và Formatter giải quyết hai nhu cầu khác nhau

### Converter: chuyển đổi kiểu tổng quát

`Converter<S, T>` có một phương thức:

~~~java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Đây là chữ ký khái niệm của SPI. Converter tập trung vào một chiều: từ `S` sang `T`. Ví dụ `String → CustomerId`, `String → UUID`, `Long → InvoiceNumber`.

Một converter có thể được dùng trong nhiều nơi không liên quan đến giao diện. Nó không nhận `Locale` trực tiếp và không có hợp đồng in object thành chuỗi.

### Formatter: parse và print cho dữ liệu hiển thị

`Formatter<T>` kết hợp hai interface:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException;
}
~~~

Các chữ ký trên minh họa SPI. `parse` nhận chuỗi từ client và tạo object; `print` nhận object và trả chuỗi để hiển thị. Cả hai có `Locale`, rất phù hợp với ngày tháng, số, tiền tệ hoặc định dạng phụ thuộc ngôn ngữ/vùng.

| Nhu cầu | Converter | Formatter |
| --- | --- | --- |
| Một kiểu sang kiểu khác | Có | Có thể tham gia qua parse/print khi có String |
| Chỉ có một chiều chuyển đổi | Phù hợp | Thường có cả parse và print |
| Cần Locale | Không có tham số Locale trực tiếp | Có sẵn |
| Form web, hiển thị dữ liệu | Dùng khi logic chuyển kiểu tổng quát | Phù hợp cho chuỗi giao diện |
| Domain value object | Rất phù hợp | Phù hợp khi cần parse/print value object |

**Quy tắc lựa chọn:** dùng `Converter` cho phép chuyển kiểu tổng quát; dùng `Formatter` khi cần parse và in giá trị theo định dạng giao diện/locale. Không viết formatter chỉ để thay thế một converter một chiều đơn giản nếu ứng dụng không cần parse/print.

## 3. FormattingConversionService là gì?

Các thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ConversionService` | API hỏi có convert được không và thực hiện conversion |
| `ConverterRegistry` | API đăng ký converter/converter factory/generic converter |
| `FormatterRegistry` | API đăng ký formatter, parser/printer và annotation formatter |
| `FormattingConversionService` | Kết hợp registry và conversion service; cung cấp hạ tầng chọn formatter/converter |
| `DefaultFormattingConversionService` | Implementation phổ biến, đã cài các formatter mặc định và hỗ trợ đăng ký phần mở rộng |
| `FormatterRegistrar` | Đóng gói nhóm converter/formatter để đăng ký vào registry |

`FormattingConversionService` vừa thực thi `ConversionService` vừa thực thi `FormatterRegistry`. Đây là điểm kết nối: một đối tượng có thể nhận đăng ký converter, formatter, sau đó được dùng bằng `convert(...)`.

### Những API thường gặp trên FormatterRegistry

~~~java
void addConverter(Converter<?, ?> converter);
void addFormatter(Formatter<?> formatter);
void addFormatterForFieldType(
        Class<?> fieldType, Formatter<?> formatter);
void addFormatterForFieldAnnotation(
        AnnotationFormatterFactory<? extends Annotation> factory);
~~~

Đây là chữ ký rút gọn minh họa các nhóm API; các method kế thừa từ `ConverterRegistry` cũng có thể đăng ký `ConverterFactory` và `GenericConverter`. Có các overload đăng ký theo kiểu field hoặc cặp `Printer`/`Parser`.

Điểm cần nhớ:

- `addConverter(...)` đăng ký chuyển đổi tổng quát.
- `addFormatter(...)` đăng ký formatter theo kiểu mà formatter khai báo.
- `addFormatterForFieldType(...)` gắn formatter vào kiểu field cụ thể.
- `addFormatterForFieldAnnotation(...)` gắn logic formatting với một annotation.
- `ConversionService.convert(...)` thực hiện conversion; `FormatterRegistry` là nơi cấu hình.

### Vì sao có chữ “Default”?

`DefaultFormattingConversionService` là implementation thực tế phổ biến. Nó kế thừa hạ tầng conversion và tự cài các formatter mặc định cho những kiểu thường gặp. Tùy constructor/cấu hình, ứng dụng có thể bật/tắt việc đăng ký default formatters, rồi bổ sung quy tắc riêng.

Trong đa số ứng dụng, bắt đầu từ `new DefaultFormattingConversionService()` sẽ thuận tiện vì có sẵn các conversion/formatting phổ biến như số và ngày. Nếu muốn kiểm soát toàn bộ danh sách, có thể tạo `FormattingConversionService`/`GenericConversionService` phù hợp và chủ động đăng ký những gì cần thiết.

## 4. Ví dụ Java 17+: cùng một service nhận Converter và Formatter

Ta xây dựng ứng dụng nhỏ với hai kiểu miền:

- `CustomerId`: value object được tạo từ chuỗi `C-2048`.
- `YearMonth`: kiểu thời gian cần nhận và in theo mẫu `MM/yyyy`.

Converter cho `CustomerId` là chuyển đổi tổng quát. Formatter cho `YearMonth` xử lý cả parse lẫn print.

### 4.1. Cấu trúc project

~~~text
formatting-conversion-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/FormattingDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'formatting-conversion-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.FormattingDemo'
}
~~~

`spring-context` kéo theo các module cần thiết cho Spring core/formatting. Ví dụ dùng Spring Framework 6.2.14 để có môi trường phiên bản cố định. Trong project Spring Boot, nên để Boot BOM quản lý phiên bản Spring tương thích.

### 4.2. Tệp Java chạy được

Tạo `src/main/java/demo/FormattingDemo.java`:

~~~java
package demo;

import java.text.ParseException;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormattingDemo {

    public record CustomerId(long value) {}

    public static final class CustomerIdConverter
            implements Converter<String, CustomerId> {

        private static final Pattern FORMAT =
                Pattern.compile("C-(\\d+)");

        @Override
        public CustomerId convert(String source) {
            if (source == null) {
                return null;
            }

            Matcher matcher = FORMAT.matcher(source.trim());
            if (!matcher.matches()) {
                throw new IllegalArgumentException(
                        "Customer ID phải có dạng C-số");
            }

            return new CustomerId(
                    Long.parseLong(matcher.group(1)));
        }
    }

    public static final class YearMonthFormatter
            implements Formatter<YearMonth> {

        private DateTimeFormatter formatter(Locale locale) {
            return DateTimeFormatter.ofPattern(
                    "MM/uuuu", locale);
        }

        @Override
        public YearMonth parse(String text, Locale locale)
                throws ParseException {
            try {
                return YearMonth.parse(
                        text.trim(), formatter(locale));
            } catch (RuntimeException ex) {
                ParseException parseException =
                        new ParseException(
                                "Tháng phải có dạng MM/yyyy", 0);
                parseException.initCause(ex);
                throw parseException;
            }
        }

        @Override
        public String print(YearMonth object, Locale locale) {
            return formatter(locale).format(object);
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new CustomerIdConverter());
        service.addFormatter(new YearMonthFormatter());

        CustomerId customerId =
                service.convert("C-2048", CustomerId.class);

        YearMonth month =
                service.convert("03/2026", YearMonth.class);

        String printedMonth =
                service.convert(month, String.class);

        System.out.println("customerId=" + customerId.value());
        System.out.println("yearMonth=" + month);
        System.out.println("printedMonth=" + printedMonth);
    }
}
~~~

Đây là chương trình Java hoàn chỉnh trong một file. Các nested class được dùng để giữ ví dụ gọn; trong ứng dụng lớn, có thể tách mỗi converter/formatter thành file riêng.

### 4.3. Chạy chương trình

Dùng Gradle Wrapper tại thư mục gốc:

~~~bash
./gradlew run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout của class Java, bỏ qua log Gradle:

~~~text
customerId=2048
yearMonth=2026-03
printedMonth=03/2026
~~~

Kết quả cho thấy cùng một `DefaultFormattingConversionService` đã xử lý hai kiểu extension khác nhau:

1. `String → CustomerId` đi qua `CustomerIdConverter`.
2. `String → YearMonth` đi qua `YearMonthFormatter.parse(...)`.
3. `YearMonth → String` đi qua `YearMonthFormatter.print(...)`.

Đó là ý nghĩa của việc kết hợp converter và formatter trong một conversion service: caller chỉ cần dùng API `convert`, còn registry chọn chiến lược phù hợp theo kiểu nguồn và đích.

## 5. Locale ảnh hưởng Formatter như thế nào?

`Formatter` nhận `Locale` trong cả `parse` và `print`. Với mẫu ngày `MM/yyyy`, kết quả tình cờ không khác nhiều giữa nhiều locale, nhưng các định dạng số/tiền tệ sẽ khác rõ hơn:

- Một số locale dùng dấu phẩy làm dấu thập phân.
- Locale khác dùng dấu chấm làm dấu thập phân.
- Dấu phân nhóm hàng nghìn và ký hiệu tiền tệ cũng có thể khác.

Ví dụ dùng `NumberFormat`:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
Number number = format.parse(text);
String rendered = format.format(number);
~~~

Đây là fragment minh họa, cần import `java.text.NumberFormat` và có xử lý `ParseException`. Nó cho thấy tại sao formatter nên dùng locale được truyền vào thay vì hard-code một dấu thập phân.

### Không nên tự giả định Locale trong ConversionService trực tiếp

`Formatter` có `Locale`, nhưng overload thông thường `conversionService.convert(source, targetClass)` không có tham số locale. Trong môi trường web, formatter được gọi qua hạ tầng Spring formatting và locale context của request. Khi gọi trực tiếp từ code ngoài web, locale hiện hành có thể dựa trên context holder hoặc default locale tùy implementation/cách gọi.

Đối với ví dụ `YearMonthFormatter` ở mục 4, pattern số `MM/uuuu` không làm thay đổi kết quả theo ngôn ngữ, nên stdout ổn định. Với tiền tệ/số hiển thị, hãy kiểm thử dưới các locale mục tiêu trong cùng context thực tế.

Nếu cần truyền locale tường minh trong code độc lập, có thể gọi trực tiếp formatter:

~~~java
YearMonthFormatter formatter = new YearMonthFormatter();
YearMonth parsed = formatter.parse(
        "03/2026", Locale.US);
String text = formatter.print(parsed, Locale.US);
~~~

Đây là fragment dùng nested class ở mục 4. Nó cho phép kiểm soát locale trực tiếp mà không phụ thuộc request context.

## 6. Annotation-driven formatting

Có những trường hợp không muốn đăng ký formatter riêng cho mọi property của cùng một kiểu. Thay vào đó, **annotation trên field/parameter** quyết định cách định dạng.

Spring hỗ trợ các annotation quen thuộc:

- `@NumberFormat`: định dạng số.
- `@DateTimeFormat`: định dạng ngày/thời gian.
- Một annotation tùy chỉnh có thể được nối với formatter qua `AnnotationFormatterFactory`.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate invoiceDate;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public LocalDate getInvoiceDate() {
        return invoiceDate;
    }

    public void setInvoiceDate(LocalDate invoiceDate) {
        this.invoiceDate = invoiceDate;
    }
}
~~~

Đây là JavaBean hoàn chỉnh cho hai property. Khi `DefaultFormattingConversionService` (hoặc hạ tầng formatting đã đăng ký formatter tương ứng) được dùng cùng `DataBinder`, annotation cung cấp metadata để chọn định dạng phù hợp cho field.

Ví dụ, `@DateTimeFormat(iso = ISO.DATE)` cho định dạng ngày ISO dạng `yyyy-MM-dd`. `@NumberFormat(pattern = "#,##0.00")` đặt pattern số; dấu phân nhóm/thập phân vẫn cần xem locale thực tế.

**Chú ý:** annotation có tác dụng khi conversion đi qua cơ chế Spring formatting có nhận metadata field/parameter. Gọi `convert("...", BigDecimal.class)` trực tiếp chỉ truyền class đích, nên không cung cấp ngữ cảnh annotation của một field cụ thể. Khi muốn dùng annotation trên property, binder cần làm việc với `TypeDescriptor`/property metadata.

## 7. TypeDescriptor giúp formatter biết field nào đang được xử lý

Một `ConversionService` có các overload nhận `TypeDescriptor`. Descriptor cung cấp thông tin về kiểu và nơi khai báo, bao gồm generic, annotation và metadata property.

Ví dụ lấy descriptor của field:

~~~java
Field field = InvoiceForm.class.getDeclaredField("amount");
TypeDescriptor amountDescriptor = new TypeDescriptor(field);

Object amount = service.convert(
        "1,234.50",
        TypeDescriptor.valueOf(String.class),
        amountDescriptor);
~~~

Đây là **fragment** cần import `java.lang.reflect.Field` và `org.springframework.core.convert.TypeDescriptor`; biến `service` phải là conversion service đã đăng ký formatter mặc định phù hợp. Nó cho thấy vì sao chỉ truyền `BigDecimal.class` có thể không đủ để áp dụng annotation của field.

Khi binder xử lý property, Spring có thể tạo descriptor gắn với field và dùng metadata annotation để chọn formatter. Đây là cơ chế nền phía sau annotation-driven formatting.

### AnnotationFormatterFactory

Để hỗ trợ một annotation tự định nghĩa, triển khai `AnnotationFormatterFactory<A>`:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {

    Set<Class<?>> getFieldTypes();

    Printer<?> getPrinter(A annotation, Class<?> fieldType);

    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

Đây là chữ ký SPI rút gọn. Luồng hoạt động:

1. Khai báo annotation có `RetentionPolicy.RUNTIME` và target như FIELD/PARAMETER.
2. `getFieldTypes()` trả những kiểu property có thể dùng annotation.
3. `getPrinter(...)` cung cấp cách in object thành chuỗi.
4. `getParser(...)` cung cấp cách parse chuỗi vào object.
5. Đăng ký factory qua `FormatterRegistry.addFormatterForFieldAnnotation(...)`.

Đây là lựa chọn phù hợp khi annotation chứa metadata như pattern, precision hoặc đơn vị. Không cần tạo factory nếu chỉ có một formatter đơn giản cho một kiểu; `addFormatter(...)` hoặc `addFormatterForFieldType(...)` sẽ dễ hơn.

## 8. FormatterRegistrar: gom nhóm đăng ký converter và formatter

`FormatterRegistrar` cho phép gom nhiều rule liên quan thành một đơn vị đăng ký:

~~~java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
~~~

Đây là chữ ký SPI.

Ví dụ:

~~~java
public class DomainFormattingRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new FormattingDemo.CustomerIdConverter());
        registry.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }
}
~~~

Đây là class có thể biên dịch khi đặt cùng package `demo` và import `FormatterRegistrar`/`FormatterRegistry`. Nó đăng ký hai thành phần đã viết ở mục 4.

Registrar hữu ích khi:

- Có nhiều formatter cho cùng một nhóm domain (tiền tệ, ngày nghiệp vụ, số định danh).
- Cần thêm converter và formatter như một module cấu hình.
- Một formatter cần được đăng ký theo field type khác với generic type mà formatter khai báo.
- Muốn tái sử dụng cấu hình conversion giữa nhiều application context.

Registrar **không tự thực hiện conversion**; nó chỉ thêm các rule vào registry được truyền vào. Service sau đó mới dùng các rule ấy.

## 9. Tích hợp trong Spring MVC

Spring MVC có formatting conversion service riêng cho binding request parameters, path variables, form model attributes và các điểm cần đổi kiểu. Để đăng ký converter/formatter tùy chỉnh, triển khai `WebMvcConfigurer`:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new FormattingDemo.CustomerIdConverter());
        registry.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }
}
~~~

Đây là class cấu hình đầy đủ với Spring MVC. Trong Spring Boot Web MVC, cấu hình được component scan phát hiện khi package nằm dưới application root.

Sau khi đăng ký, controller có thể nhận kiểu đích trực tiếp:

~~~java
@GetMapping("/customers/{id}")
ResponseEntity<?> find(@PathVariable CustomerId id) {
    return ResponseEntity.ok(id.value());
}

@PostMapping("/invoices")
String save(@ModelAttribute InvoiceForm form) {
    // form.amount và form.invoiceDate đã được binding/conversion.
    return "success";
}
~~~

Đây là fragment trong controller, cần import các annotation MVC và khai báo kiểu `CustomerId`/`InvoiceForm`. `/customers/C-2048` có thể được chuyển thành `CustomerId` thông qua converter đã đăng ký. Với form, formatter/annotation tương ứng được sử dụng trong quá trình bind.

### Đăng ký qua FormatterRegistrar trong MVC

Nếu nhóm rule nhiều, dùng registrar:

~~~java
@Configuration
public class WebFormattingConfig
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        new DomainFormattingRegistrar()
                .registerFormatters(registry);
    }
}
~~~

Đây là biến thể thay cho method đăng ký từng thành phần trực tiếp. Chỉ dùng **một cấu hình** phù hợp trong ứng dụng; không cần đồng thời đăng ký thủ công và registrar cho cùng converter/formatter.

## 10. DataBinder sử dụng FormattingConversionService

`DataBinder` dùng conversion service để chuyển giá trị đầu vào trước khi gán vào property. Vì `FormattingConversionService` đồng thời là `ConversionService`, có thể cấu hình nó cho binder thuần:

~~~java
FormattingConversionService conversionService =
        new DefaultFormattingConversionService();

conversionService.addConverter(
        new FormattingDemo.CustomerIdConverter());
conversionService.addFormatter(
        new FormattingDemo.YearMonthFormatter());

DataBinder binder = new DataBinder(form, "invoice");
binder.setConversionService(conversionService);
binder.bind(propertyValues);

BindingResult result = binder.getBindingResult();
~~~

Đây là fragment; `form` cần là object đã có getter/setter, `propertyValues` là `PropertyValues` hợp lệ, và cần import `DataBinder`/`BindingResult` cùng các API formatting. Trong MVC, framework đã có conversion service tích hợp nên thường không cần tự tạo binder trong controller.

Luồng binding có thể hiểu:

~~~text
HTTP String values
       |
       v
WebDataBinder / DataBinder
       |
       v
FormattingConversionService
       |
    +--+----------------+
    |                   |
Converter              Formatter
String -> CustomerId  String <-> YearMonth
    |                   |
    +---------+---------+
              |
       Bean property / model
              |
        BindingResult
~~~

`BindingResult` ghi nhận lỗi binding/convert theo cơ chế của binder. Ví dụ `yearMonth=not-a-month` sẽ không tạo được `YearMonth`; controller có thể kiểm tra `hasErrors()` và trả lại form hoặc response lỗi.

## 11. Xử lý lỗi parse/convert đúng cách

Khi converter/formatter nhận input không hợp lệ:

- `Converter` có thể ném exception conversion thích hợp hoặc exception mô tả input không hợp lệ để Spring bọc theo đường conversion.
- `Formatter.parse(...)` khai báo `ParseException`; không nên trả một object mặc định khi chuỗi sai.
- `DataBinder` có thể đưa conversion error vào `BindingResult` để controller hiển thị lỗi theo field.
- Gọi `ConversionService.convert(...)` trực tiếp có thể ném `ConversionException`/`ConversionFailedException`; caller tự xử lý theo contract.

Ví dụ kiểm tra lỗi trực tiếp:

~~~java
try {
    service.convert("not-a-month", YearMonth.class);
} catch (ConversionException ex) {
    System.out.println("Không thể chuyển tháng");
}
~~~

Đây là fragment cần import `org.springframework.core.convert.ConversionException` và dùng service đã đăng ký `YearMonthFormatter`. Thông điệp hiển thị là do ứng dụng quyết định; không trả nguyên stack trace hoặc exception detail cho client.

**Đừng trộn validation với formatting.** `"03/2026"` có thể parse hợp lệ thành `YearMonth`, nhưng quy tắc “không cho chọn tháng trong quá khứ” là business validation riêng. Formatter nên tập trung vào biểu diễn/chuyển đổi.

## 12. Thread safety và thiết kế tốt

`ConversionService` là đối tượng được thiết kế stateless, thường khởi tạo khi ứng dụng khởi động rồi chia sẻ giữa nhiều thread. `FormattingConversionService` cũng phù hợp với cách sử dụng tập trung đó.

Tuy vậy, **converter/formatter tùy chỉnh phải tự bảo đảm an toàn khi dùng đồng thời**:

- Không lưu giá trị input hiện tại vào field.
- Không lưu `BindingResult`, `Locale` của request hoặc kết quả parse gần nhất trong field mutable.
- Dùng biến cục bộ trong `convert`, `parse` và `print`.
- Cấu hình dùng chung nên bất biến.
- Dùng các API immutable/thread-safe như `DateTimeFormatter`; tránh chia sẻ `SimpleDateFormat` mutable giữa các request.
- Không truy vấn database/cập nhật trạng thái nghiệp vụ trong formatter; đó là trách nhiệm của service/domain.

`YearMonthFormatter` trong ví dụ tạo `DateTimeFormatter` từ locale trong từng lần gọi. `DateTimeFormatter` bản thân là immutable và thread-safe, nên có thể tái sử dụng an toàn nếu lưu thành field final với cấu hình cố định phù hợp.

Nếu formatter phụ thuộc timezone, locale, đơn vị tiền tệ hoặc context người dùng, truyền/đọc context theo hợp đồng rõ ràng. Không cất locale của request trước vào singleton.

## 13. Converter, Formatter và annotation formatter: chọn cách nào?

| Tình huống | Thiết kế đề xuất |
| --- | --- |
| String → CustomerId, không cần chiều ngược lại | `Converter<String, CustomerId>` |
| String ↔ YearMonth theo mẫu/locale | `Formatter<YearMonth>` |
| Nhiều kiểu target cùng một họ | `ConverterFactory` |
| Một field cần pattern do annotation xác định | `AnnotationFormatterFactory` |
| Nhiều formatter/converter cùng nhóm domain | `FormatterRegistrar` |
| Đăng ký tập trung và dùng ở MVC/DataBinder | `FormattingConversionService` |
| Rule riêng của MVC request binding | `WebMvcConfigurer#addFormatters` |

Đừng dùng `Formatter` chỉ vì nó có chữ “format” khi bài toán không cần locale/print. Ngược lại, tránh dùng `Converter` cho mọi chuỗi hiển thị nếu logic phụ thuộc locale hoặc cần chuyển object ngược lại thành chuỗi.

Một field type có thể có formatter mặc định, formatter đăng ký theo type và formatter gắn bằng annotation. Khi quy tắc chồng lấp, hãy kiểm tra converter được chọn trong context thực tế và viết test để tránh giả định thứ tự ưu tiên.

## 14. Kiểm thử formatter và converter

Không chỉ kiểm tra conversion thành công. Cần kiểm thử hai chiều parse/print, locale, input không hợp lệ và tích hợp binder.

### Unit test JUnit 5

Tệp `src/test/java/demo/FormattingDemoTest.java`:

~~~java
package demo;

import java.time.YearMonth;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.*;

class FormattingDemoTest {

    private final DefaultConversionService service =
            new DefaultConversionService();

    FormattingDemoTest() {
        service.addConverter(
                new FormattingDemo.CustomerIdConverter());
        service.addFormatter(
                new FormattingDemo.YearMonthFormatter());
    }

    @Test
    void convertsDomainId() {
        var id = service.convert(
                "C-2048", FormattingDemo.CustomerId.class);
        assertEquals(2048L, id.value());
    }

    @Test
    void parsesAndPrintsYearMonth() {
        YearMonth month =
                service.convert("03/2026", YearMonth.class);

        String printed = service.convert(month, String.class);

        assertEquals(YearMonth.of(2026, 3), month);
        assertEquals("03/2026", printed);
    }

    @Test
    void rejectsMalformedCustomerId() {
        assertThrows(RuntimeException.class, () ->
                service.convert(
                        "bad-id", FormattingDemo.CustomerId.class));
    }

    @Test
    void formatterCanUseExplicitLocale() throws Exception {
        var formatter = new FormattingDemo.YearMonthFormatter();
        var value = formatter.parse("03/2026", Locale.US);
        assertEquals("03/2026", formatter.print(value, Locale.US));
    }
}
~~~

Test class dùng JUnit Jupiter. Bổ sung vào `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Assertion `RuntimeException` cho dữ liệu sai chỉ dùng để bao quát demo; trong project thực tế nên assert đúng exception cụ thể sau khi đã chốt cách bọc lỗi của converter và Spring version.

### Các test tích hợp nên có

- Đăng ký cả converter và formatter qua `WebMvcConfigurer` và gửi một request form.
- Kiểm tra `@DateTimeFormat`/`@NumberFormat` trên field thực.
- Gửi locale khác nhau và xác minh parse/print tương ứng.
- Kiểm tra format không hợp lệ tạo đúng field error trong `BindingResult`.
- Xác nhận converter/formatter không chia sẻ mutable state giữa các request.
- Kiểm tra cùng kiểu nguồn/đích nhưng field annotation khác nhau nếu dùng `AnnotationFormatterFactory`.

## 15. Lỗi thường gặp

**Chỉ đăng ký Converter mà quên Formatter.** Service chuyển được kiểu domain nhưng không có quy tắc in chuỗi phù hợp. Dùng `Formatter` khi cần hai chiều parse/print.

**Dùng Locale mặc định cố định.** Kết quả có thể sai cho người dùng ở locale khác. Dùng tham số locale trong Formatter thay vì hard-code quy tắc hiển thị.

**Nghĩ mọi ConversionService đều có formatter mặc định.** `GenericConversionService` và `DefaultFormattingConversionService` không có cùng tập converter/formatter khởi tạo. Chọn implementation và cấu hình có chủ đích.

**Chờ annotation hoạt động khi gọi convert chỉ bằng Class.** Lời gọi class-only không mang metadata field; dùng `TypeDescriptor` hoặc binder xử lý property có annotation.

**Dùng @DateTimeFormat trên kiểu nhưng không qua Spring binding.** Annotation không tự biến thành khả năng parse khi gọi `LocalDate.parse` trực tiếp; cần conversion service/binder đã đăng ký formatter phù hợp.

**Ghi đè quy tắc mặc định ngoài ý muốn.** Khi đăng ký formatter cho kiểu chung, xem xét tác động đến các controller và model attribute khác. Nên dùng annotation-based formatting khi chỉ một số field cần cách biểu diễn riêng.

**Parser trả null khi dữ liệu sai.** Null có thể là giá trị hợp lệ theo contract và làm mất dấu lỗi. Parse sai nên ném exception thích hợp để binder ghi nhận.

**Lưu parser mutable vào singleton.** Ví dụ `SimpleDateFormat` có thể gây race condition. Dùng `DateTimeFormatter` hoặc instance cục bộ.

**Làm business validation bên trong Formatter.** Formatting là chuyển đổi/biểu diễn; quy tắc nghiệp vụ cần Spring Validator/Bean Validation hoặc service.

## 16. Ghi nhớ

`FormattingConversionService` kết hợp **`ConversionService` để chuyển kiểu** với **`FormatterRegistry` để đăng ký định dạng**. Nhờ đó ứng dụng có thể quản lý converter và formatter tại một registry dùng chung. Converter phù hợp với chuyển đổi tổng quát một chiều; formatter phù hợp với parse/print có locale; annotation formatter xử lý các field cần quy tắc riêng; registrar gom các cấu hình liên quan.

Trong Spring MVC, đăng ký qua `WebMvcConfigurer#addFormatters` để binding request, model và render view dùng chung quy tắc. Kiểm thử cả hai chiều, locale, annotation metadata và lỗi đầu vào để conversion nhất quán trong toàn ứng dụng.

### Tài liệu tham khảo chính thức

- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring MVC — Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [FormattingConversionService API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html)
- [FormatterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Formatter API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
