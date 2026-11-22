# Parser.parse và Printer.print trong Spring Formatter

Trong Spring Framework, **`Parser<T>`** và **`Printer<T>`** là hai interface tách riêng hai chiều chuyển đổi giữa văn bản người dùng và kiểu Java:

- **`Parser<T>.parse(String text, Locale locale)`** nhận chuỗi đầu vào và tạo object kiểu `T`.
- **`Printer<T>.print(T object, Locale locale)`** nhận object kiểu `T` và tạo chuỗi để hiển thị.

`Formatter<T>` kết hợp cả hai interface, nên một formatter có thể vừa **đọc dữ liệu nhập (parse)**, vừa **hiển thị dữ liệu (print)**. Đây là SPI định dạng trường của Spring, đặc biệt phù hợp với giao diện web vì cùng một giá trị có thể được nhập và hiển thị theo quy ước của locale.

Ví dụ: người dùng nhập mã `" sku-123 "`; parser chuẩn hóa thành `ProductCode("SKU-123")`. Khi đưa object trở lại giao diện, printer tạo chuỗi `"SKU-123"`. Với số/ngày tháng, cùng một giá trị có thể có cách hiển thị khác nhau theo `Locale`.

## 1. Hai interface giải quyết hai chiều khác nhau

Spring định nghĩa các hợp đồng cốt lõi:

~~~java
public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}
~~~

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}
~~~

Đây là **đoạn khai báo rút gọn** để minh họa API; khi viết code cần import `java.util.Locale`, `java.text.ParseException` và package Spring tương ứng.

| Interface | Method | Input | Output | Khi nào được dùng? |
| --- | --- | --- | --- | --- |
| `Parser<T>` | `parse(String, Locale)` | Chuỗi từ client, locale hiện tại | Object kiểu `T` | Khi binding văn bản vào field/object |
| `Printer<T>` | `print(T, Locale)` | Object Java, locale hiện tại | Chuỗi hiển thị | Khi tạo biểu diễn văn bản cho field/object |

Hai method không phải hai chiều của một hàm đảo ngược tuyệt đối. Parser có thể chấp nhận nhiều cách nhập và chuẩn hóa về một object duy nhất; printer thường chọn một cách hiển thị chuẩn. Ví dụ:

~~~text
Chuỗi người dùng nhập: " sku-123 "
                |
                v
       Parser.parse(text, locale)
                |
                v
         ProductCode("SKU-123")
                |
                v
       Printer.print(object, locale)
                |
                v
             "SKU-123"
~~~

Vì vậy, round-trip thường có dạng **parse → print → chuỗi chuẩn hóa**, không nhất thiết chuỗi in ra phải giống nguyên văn chuỗi đã nhập.

## 2. Parser.parse — chuyển chuỗi thành object

Chữ ký:

~~~java
T parse(String text, Locale locale)
        throws ParseException;
~~~

- `text`: nội dung văn bản cần phân tích, ví dụ `"21/11/2026"`, `"1,234.50"` hoặc `"sku-123"`.
- `locale`: quy ước ngôn ngữ/vùng miền hiện tại, ảnh hưởng dấu thập phân, dấu nhóm số, cách hiển thị ngày hoặc tên tháng.
- Giá trị trả về: object kiểu `T` nếu chuỗi hợp lệ.
- `ParseException`: có thể xuất hiện khi parser sử dụng API parse trong `java.text` và không đọc được chuỗi.
- `IllegalArgumentException`: cũng có thể dùng để báo chuỗi không hợp lệ theo hợp đồng formatter.

Ví dụ parser cho ngày theo mẫu cụ thể:

~~~java
public LocalDate parse(String text, Locale locale) throws ParseException {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    return LocalDate.parse(text, formatter);
}
~~~

Đây là **đoạn method minh họa**, cần import `java.time.LocalDate` và `java.time.format.DateTimeFormatter`. Với `"31/12/2026"`, parser tạo `LocalDate.of(2026, 12, 31)`. Nếu dùng `"31/19/2026"`, `DateTimeParseException` có thể được ném ra; nó không bắt buộc là `java.text.ParseException`.

Chữ ký `Parser.parse` cho phép `ParseException` nhưng không giới hạn parser chỉ ném loại exception đó. Khi tích hợp với Spring binding, conversion service chuyển lỗi parse phù hợp thành lỗi conversion/binding để tầng trên hiển thị.

### Khi nào locale có tác dụng?

| Locale | Biểu diễn số 1234.5 thường gặp |
| --- | --- |
| `Locale.US` | `1,234.5` |
| `Locale.GERMANY` | `1.234,5` |
| `Locale.FRANCE` | Dấu phẩy thập phân và dấu phân cách nhóm dạng khoảng trắng |

Không được giả định chuỗi số theo locale nào cũng giống nhau. Parser và printer phải dùng quy ước nhất quán hoặc locale do Spring cung cấp.

## 3. Printer.print — chuyển object thành chuỗi

Chữ ký:

~~~java
String print(T object, Locale locale);
~~~

Ví dụ:

~~~java
public String print(LocalDate date, Locale locale) {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    return formatter.format(date);
}
~~~

Đây là **đoạn method minh họa**. Với `LocalDate.of(2026, 12, 31)` và pattern `dd/MM/uuuu`, kết quả là `"31/12/2026"`.

Printer không nên thay đổi object đầu vào; nó tạo chuỗi biểu diễn. Nếu `object` là `null`, cần quyết định hợp đồng rõ ràng: trả `""`, placeholder hoặc để nơi gọi xử lý. Không nên mặc định mọi printer xử lý null giống nhau.

### Parse và print có cần đối xứng tuyệt đối?

Không. Chúng cần tương thích về hợp đồng:

- Chuỗi do printer phát ra nên parse lại được bởi parser tương ứng.
- Parser có thể nhận thêm khoảng trắng, alias hoặc định dạng cũ mà printer không phát ra.
- Printer có thể chuẩn hóa chữ hoa/thường hoặc định dạng theo locale.
- Không phải mọi chuỗi parser chấp nhận đều cần in lại y hệt.

Phép thử round-trip:

~~~java
T value = parser.parse(text, locale);
String normalized = printer.print(value, locale);
T parsedAgain = parser.parse(normalized, locale);
~~~

Đây là **đoạn kiểm thử khái niệm**. Thường cần xác nhận `parsedAgain` tương đương `value`, không phải `normalized.equals(text)`.

## 4. Formatter<T> kết hợp Parser và Printer

Spring cung cấp interface:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Khi một kiểu cần cả đọc chuỗi và hiển thị chuỗi, triển khai một class formatter:

~~~java
public final class ProductCodeFormatter
        implements Formatter<ProductCode> {

    @Override
    public ProductCode parse(String text, Locale locale) {
        // Chuỗi -> ProductCode
    }

    @Override
    public String print(ProductCode value, Locale locale) {
        // ProductCode -> chuỗi
    }
}
~~~

Đây là **khung class** minh họa, không phải chương trình độc lập. Import chính:

~~~java
import java.util.Locale;
import org.springframework.format.Formatter;
~~~

Formatter giúp hai chiều tuân thủ một chính sách chung, ví dụ cùng chuẩn hóa mã sản phẩm, cùng pattern ngày hoặc quy tắc số. Với formatter không dùng locale, vẫn phải nhận tham số `Locale` theo interface; có thể chủ động không sử dụng và ghi rõ lý do.

### So sánh với Converter

| Thành phần | Hướng | Nhận Locale? | Mục tiêu |
| --- | --- | --- | --- |
| `Converter<S,T>` | `S → T` | Không trực tiếp | Chuyển kiểu tổng quát |
| `Parser<T>` | `String → T` | Có | Phân tích input |
| `Printer<T>` | `T → String` | Có | Hiển thị object |
| `Formatter<T>` | Cả parse và print | Có | Định dạng hai chiều cho field |

Dùng `Converter` khi chỉ cần chuyển kiểu tổng quát, chẳng hạn `String → UUID` hoặc `Long → DomainId`. Dùng `Formatter` khi cần parse và print theo locale cho trường form như tiền tệ, ngày tháng, phần trăm. Dùng riêng `Parser` hoặc `Printer` nếu ứng dụng chỉ cần một chiều.

`ConversionService` cung cấp API thống nhất để Spring sử dụng cả `Converter` lẫn `Formatter`, nhưng hai SPI vẫn giữ vai trò khác nhau.

## 5. Ví dụ hoàn chỉnh Java 17+: custom Formatter cho mã sản phẩm

Quy tắc ví dụ:

- Cho phép khoảng trắng đầu/cuối khi nhập.
- Chuẩn hóa mã về chữ hoa.
- Chỉ chấp nhận dạng hai chữ cái, dấu gạch ngang và ba chữ số, ví dụ `AB-123`.
- Printer luôn phát ra dạng chuẩn hóa.
- Locale được nhận từ Spring nhưng không ảnh hưởng mã kỹ thuật này.

### 5.1. Maven project

Tạo file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-formatter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo theo các module Spring cần thiết như `spring-core` và `spring-beans`. Trong ứng dụng Spring Boot, nên để BOM/parent của Boot quản lý các module cùng phiên bản; không ghim riêng một module Spring lệch với stack đang dùng.

### 5.2. Mã nguồn hoàn chỉnh

Tạo file `src/main/java/example/FormatterDemo.java`:

~~~java
package example;

import java.util.Locale;

import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class FormatterDemo {

    public record ProductCode(String value) {
    }

    public static final class ProductCodeFormatter
            implements Formatter<ProductCode> {

        @Override
        public ProductCode parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Product code must not be blank");
            }

            String normalized =
                    text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Product code must match AA-999");
            }

            // Locale không ảnh hưởng định dạng mã kỹ thuật.
            return new ProductCode(normalized);
        }

        @Override
        public String print(ProductCode value, Locale locale) {
            if (value == null) {
                return "";
            }
            return value.value();
        }
    }

    public static void main(String[] args) {
        ProductCodeFormatter formatter =
                new ProductCodeFormatter();

        Locale locale = Locale.US;

        ProductCode code =
                formatter.parse(" ab-123 ", locale);
        String display = formatter.print(code, locale);

        System.out.println("parsed=" + code.value());
        System.out.println("printed=" + display);

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addFormatter(formatter);

        ProductCode converted = conversionService.convert(
                " cd-456 ", ProductCode.class);
        String convertedBack =
                conversionService.convert(converted, String.class);

        System.out.println("service.parsed=" + converted.value());
        System.out.println("service.printed=" + convertedBack);

        try {
            formatter.parse("wrong", locale);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Các điểm quan trọng:

- `parse` trả về `ProductCode`, không trả một `String` đã chuẩn hóa.
- `print` nhận `ProductCode` và tạo chuỗi hiển thị.
- `Locale.ROOT` được dùng để chuẩn hóa chữ hoa ổn định theo quy tắc kỹ thuật, tránh phụ thuộc ngôn ngữ máy người dùng.
- Tham số `locale` được giữ trong chữ ký để Spring truyền context; mã sản phẩm không có quy tắc địa phương nên không sử dụng.
- `DefaultFormattingConversionService.addFormatter(...)` đăng ký cả parser và printer cho kiểu tương ứng.
- Đầu vào sai ném `IllegalArgumentException`, không âm thầm tạo mã không hợp lệ.

### 5.3. Biên dịch và chạy

Cấu trúc:

~~~text
spring-formatter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── FormatterDemo.java
~~~

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.FormatterDemo
~~~

Đầu ra do chương trình `System.out.println` tạo ra:

~~~text
parsed=AB-123
printed=AB-123
service.parsed=CD-456
service.printed=CD-456
invalid=IllegalArgumentException
~~~

Các dòng log khác của Maven (nếu có) không thuộc stdout minh họa. Ví dụ chạy như chương trình Java Maven độc lập, không cần Spring Boot hay HTTP server.

Khi formatter phụ thuộc locale, `FormattingConversionService` lấy locale từ context hiện hành trong các luồng formatting. Test trực tiếp `parse/print` như trên cho phép truyền `Locale` tường minh, không phụ thuộc thread context.

## 6. Đăng ký Formatter trong Spring MVC

Spring MVC có thể đăng ký formatter để `WebDataBinder` và `ConversionService` dùng khi bind form:

~~~java
@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new ProductCodeFormatter());
    }
}
~~~

Đây là **đoạn cấu hình** cần import `@Configuration`, `FormatterRegistry` và `WebMvcConfigurer`. Class `ProductCodeFormatter` phải nằm trong package ứng dụng và được import.

DTO JavaBean:

~~~java
public class OrderForm {
    private ProductCode productCode;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }
}
~~~

Đây là class cần import hoặc cùng package với `ProductCode`. Khi request form gửi `productCode=ab-123`, parser có thể chuyển thành `ProductCode("AB-123")`. Khi hiển thị lại field, printer có thể tạo chuỗi phù hợp.

Controller snippet:

~~~java
@PostMapping("/orders")
String submit(
        @ModelAttribute OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "order-form";
    }
    return "order-success";
}
~~~

Đây là **trích đoạn** cần `@Controller`, import MVC và view. `BindingResult` đặt ngay sau model attribute để lấy lỗi parse/conversion của field. Formatter chỉ chuyển đổi; validation nghiệp vụ cần được cấu hình riêng.

### Với Spring WebFlux

WebFlux cũng có hệ thống formatting/conversion tương tự thông qua `FormattingConversionService` và cơ chế cấu hình WebFlux. Dùng `WebFluxConfigurer#addFormatters(FormatterRegistry)`:

~~~java
@Configuration
public class ReactiveFormattingConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new ProductCodeFormatter());
    }
}
~~~

Đây là **đoạn cấu hình WebFlux**, cần import `org.springframework.web.reactive.config.WebFluxConfigurer` và các lớp liên quan. Không trộn `WebMvcConfigurer` với `WebFluxConfigurer` trong cùng một cấu hình chỉ vì hai interface đều có method `addFormatters`; chọn web stack ứng dụng đang sử dụng.

## 7. Annotation-driven formatting và phạm vi áp dụng

Ngoài đăng ký theo type, Spring có thể đăng ký formatter theo annotation field qua `AnnotationFormatterFactory`. Cách này hữu ích nếu cùng một kiểu Java cần nhiều định dạng tùy annotation/ngữ cảnh field.

Spring có các annotation tích hợp như `@NumberFormat` và `@DateTimeFormat`:

~~~java
public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate invoiceDate;

    // Getter/setter...
}
~~~

Đây là **đoạn class minh họa**, cần import `NumberFormat`, `DateTimeFormat`, `BigDecimal` và `LocalDate`. Annotation tích hợp giúp giảm nhu cầu tự viết formatter cho trường hợp phổ biến.

Nếu một kiểu có quy tắc khác nhau tùy field, **field annotation formatter** có thể phù hợp hơn đăng ký toàn cục theo type. Nếu tất cả trường kiểu `ProductCode` luôn có cùng hợp đồng, formatter theo type thường đơn giản hơn.

## 8. Locale: parse và print phải nhất quán

Locale là tham số quan trọng giúp formatter hoạt động đúng với quy ước người dùng. Ví dụ với số `1234.5`:

~~~java
NumberStyleFormatter formatter = new NumberStyleFormatter();
String us = formatter.print(1234.5, Locale.US);
String de = formatter.print(1234.5, Locale.GERMANY);
~~~

Đây là **đoạn trích**, cần import `org.springframework.format.number.NumberStyleFormatter`. Kết quả minh họa thường là:

~~~text
us=1,234.5
de=1.234,5
~~~

Khi parse, `"1,234.5"` theo locale US có thể được hiểu là 1234.5, nhưng theo locale Đức có thể không hợp lệ hoặc mang ý nghĩa khác. Vì vậy:

1. Dùng locale do người dùng/request context cung cấp.
2. Tránh tự dựng `Locale.getDefault()` trong formatter cho mọi request; server default có thể khác người dùng.
3. Cùng một field nên parse và print theo quy tắc nhất quán.
4. Test nhiều locale quan trọng, gồm dấu thập phân và dấu phân nhóm.
5. Nếu dữ liệu là mã kỹ thuật, ID hay token không phụ thuộc locale, dùng quy tắc ổn định như `Locale.ROOT`.

Locale không chỉ là ngôn ngữ dịch thông điệp. Nó còn tác động đến cách viết và đọc dữ liệu.

## 9. Thread safety và trạng thái trong Formatter

Formatter thường được đăng ký vào `ConversionService` dùng chung trong ứng dụng. Implementation nên **thread-safe**:

- Không lưu `ParsePosition`, `StringBuilder` hoặc giá trị request hiện tại vào field mutable rồi tái sử dụng giữa các request.
- Không chia sẻ `SimpleDateFormat` mutable giữa threads; dùng API immutable/thread-safe như `DateTimeFormatter`.
- Không thay đổi cấu hình formatter sau khi đưa vào registry dùng chung.
- Giữ state theo biến local trong `parse`/`print`.
- Nếu cần cache, dùng cấu trúc an toàn luồng và chỉ cache dữ liệu bất biến.

`ProductCodeFormatter` ở phần 5 là stateless: biến `normalized` chỉ tồn tại trong lần gọi method; không lưu giá trị request vào field. Vì thế cùng formatter có thể được tái sử dụng.

**Đừng nhầm với PropertyEditor:** JavaBeans `PropertyEditor` có trạng thái `setValue/getValue`, còn `Formatter<T>` nhận input/output trực tiếp qua tham số method và thường dễ triển khai thread-safe hơn.

## 10. Lỗi phổ biến khi viết Parser và Printer

### Chỉ triển khai parse mà quên print

Nếu field cần vừa hiển thị vừa nhận dữ liệu, chỉ có parser có thể đủ cho binding nhưng không đáp ứng đầy đủ formatter hai chiều. Hãy triển khai `Formatter<T>` hoặc đăng ký riêng parser/printer nếu đó là chủ ý.

### Printer không theo cùng hợp đồng parser

Nếu `print` tạo chuỗi mà `parse` không đọc được, dữ liệu có thể hiển thị nhưng submit lại sẽ lỗi. Kiểm thử round-trip ở nhiều locale và giá trị biên.

### Không xử lý chuỗi rỗng hoặc null

`""`, chuỗi chỉ có khoảng trắng và `null` có thể mang ý nghĩa khác nhau: bỏ trống, xóa giá trị hoặc lỗi bắt buộc nhập. Parser nên theo hợp đồng đã chọn; validation quyết định field có bắt buộc hay không.

### Nuốt ParseException rồi trả giá trị mặc định

Biến dữ liệu sai thành `0`, ngày mặc định hoặc object rỗng có thể che lỗi người dùng và tạo dữ liệu sai. Nên ném exception phù hợp để Spring ghi nhận binding error.

### Dùng formatter cho chuyển đổi phi văn bản

Nếu chỉ chuyển `Long → CustomerId` mà không có nhập/hiển thị locale, `Converter<Long, CustomerId>` phù hợp hơn. Formatter có giá trị khi một bên là văn bản client.

### Dùng locale mặc định của server

Một ứng dụng ở máy chủ có locale khác người dùng có thể đọc sai dấu thập phân/ngày. Hãy sử dụng `Locale` được truyền và kiểm thử thực tế.

### Lẫn conversion với validation

`parse("15", locale)` có thể thành công tạo số 15. Nếu nghiệp vụ yêu cầu tuổi tối thiểu 18, đó là validation, không phải parse failure.

### Chỉ test formatter trực tiếp, không test registry/binder

Formatter parse/print đúng khi gọi trực tiếp chưa chứng minh `FormattingConversionService` hoặc `WebDataBinder` đã đăng ký formatter đúng phạm vi. Test thêm binding request và hiển thị giá trị trong ứng dụng.

## 11. Bài tập tự kiểm tra

1. `Parser<T>` và `Printer<T>` khác nhau về chiều chuyển đổi như thế nào?
2. Vì sao `Formatter<T>` extends cả hai interface?
3. Một `DateFormatter` nhận `Locale` để giải quyết vấn đề gì?
4. Nếu printer in `"31.12.2026"` nhưng parser chỉ đọc `"dd/MM/yyyy"`, chuyện gì xảy ra khi submit lại form?
5. Khi chỉ cần chuyển `String → UUID` mà không cần hiển thị locale, nên chọn `Converter` hay `Formatter`?
6. Vì sao không nên để `SimpleDateFormat` mutable làm field singleton trong formatter?
7. Nếu input `"15"` parse thành công nhưng không đạt tuổi tối thiểu, lỗi thuộc parsing hay validation?
8. Làm thế nào đăng ký cùng formatter trong Spring MVC và WebFlux mà không trộn cấu hình hai stack?

**Ghi nhớ:** `Parser.parse(String, Locale)` biến văn bản thành kiểu Java; `Printer.print(T, Locale)` biến object thành văn bản; `Formatter<T>` kết hợp hai chiều. Dùng formatter khi field cần parse/print theo locale, đăng ký vào `ConversionService`/web configuration đúng phạm vi và giữ implementation thread-safe. Parse thành công mới chứng minh chuỗi tạo được object, không chứng minh dữ liệu hợp lệ về nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — Parser](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework Javadoc — Printer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Printer.html)
- [Spring Framework Javadoc — Formatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework Javadoc — FormatterRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework Reference — ConversionService](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework MVC — Data Binding and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
