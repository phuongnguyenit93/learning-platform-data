# FormatterRegistrar và nhóm quy tắc định dạng dùng chung trong Spring Framework

## 1. Bài toán và vai trò của FormatterRegistrar

Trong một ứng dụng Spring, nhiều controller, form và DataBinder có thể cần cùng một quy tắc parse/print. Ví dụ một module bán hàng có:

- OrderCode: mã đơn hàng, dạng ORD-0001.
- InvoiceReference: mã hóa đơn, dạng INV-0001.
- DepartmentCode: mã phòng ban, dạng DPT-SAL.

Nếu từng controller tự tạo formatter hoặc converter, quy tắc dễ bị lặp, khác nhau giữa các màn hình và khó kiểm soát khi thay đổi. Spring cung cấp FormatterRegistrar để **đăng ký một nhóm converter và formatter liên quan vào cùng một FormatterRegistry**.

Interface thuộc org.springframework.format:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

Ý nghĩa của contract:

- Một implementation tập hợp các quy tắc có liên quan về một nhóm nghiệp vụ hoặc một kiểu dữ liệu.
- Phương thức registerFormatters(...) nhận registry do cấu hình Spring cung cấp.
- Registrar đăng ký Formatter, Printer, Parser hoặc Converter thông qua registry.
- Registrar không trực tiếp parse dữ liệu và không thay thế Formatter hay Converter.
- Việc implements FormatterRegistrar **không tự khiến registrar được Spring phát hiện và chạy**. Ứng dụng phải gọi nó trong điểm cấu hình hoặc khai báo nó với cơ chế tạo FormattingConversionService tương ứng.

Có thể hình dung:

```text
Application configuration
        |
        v
BillingFormatterRegistrar
        |
        +--> OrderCodeFormatter
        |
        +--> InvoiceReferenceFormatter
        |
        +--> StringToDepartmentCode
        |
        v
FormatterRegistry
        |
        v
FormattingConversionService
        |
        +--> DataBinder / Spring MVC
        +--> ConversionService callers
```

**FormatterRegistrar là điểm tổ chức và đăng ký quy tắc.** Registry quản lý quy tắc; FormattingConversionService thực thi việc chuyển đổi/định dạng khi runtime.

## 2. Các interface và lớp liên quan

| Thành phần | Vai trò | API tiêu biểu |
| --- | --- | --- |
| Formatter<T> | Parse String thành T và print T thành String theo Locale | parse(text, locale), print(object, locale) |
| Printer<T> | In đối tượng thành chuỗi | print(object, locale) |
| Parser<T> | Parse chuỗi thành đối tượng | parse(text, locale) |
| Converter<S,T> | Chuyển đổi một cặp kiểu có hướng | convert(source) |
| ConverterRegistry | Đăng ký converter | addConverter(...) |
| FormatterRegistry | Đăng ký formatter, printer/parser và converter | addFormatter(...), addParser(...), addConverter(...) |
| FormatterRegistrar | Nhóm các hành động đăng ký liên quan | registerFormatters(registry) |
| FormattingConversionService | Registry và service dùng để parse/print/chuyển kiểu | addFormatter(...), convert(...) |
| DefaultFormattingConversionService | Implementation phổ biến với các quy tắc định dạng mặc định | tạo instance rồi bổ sung quy tắc riêng |

Quan hệ quan trọng: **FormatterRegistry extends ConverterRegistry**. Vì vậy một registrar có thể đăng ký cả formatter và converter qua cùng một tham số FormatterRegistry.

Registrar không phải một registry mới, không phải một ConversionService riêng và cũng không phải một formatter. Nó là adapter/configuration object để nhóm lệnh đăng ký.

### 2.1. Vì sao không đăng ký trực tiếp ở từng controller?

Đăng ký tập trung giúp:

- Dùng thống nhất một format giữa nhiều controller và form.
- Nhóm các formatter cùng domain, ví dụ billing, inventory hoặc customer.
- Tái sử dụng một cấu hình cho MVC hoặc một FormattingConversionService được xây riêng.
- Dễ kiểm thử tập quy tắc đã đăng ký.
- Giảm việc một controller tự tạo formatter khác với controller còn lại.

FormatterRegistrar phù hợp khi có **nhiều quy tắc liên quan** hoặc khi cần đăng ký một Printer/Parser theo field type cụ thể. Nếu chỉ có một formatter đơn giản, gọi registry.addFormatter(...) trực tiếp trong cấu hình cũng hoàn toàn hợp lệ.

## 3. FormatterRegistry nhận những loại quy tắc nào?

FormatterRegistry cung cấp các nhóm API sau:

| API | Công dụng |
| --- | --- |
| addFormatter(formatter) | Đăng ký Formatter cho kiểu T được khai báo qua generic |
| addFormatterForFieldType(fieldType, formatter) | Đăng ký formatter cho field type được chỉ định |
| addFormatterForFieldType(fieldType, printer, parser) | Đăng ký cặp Printer/Parser |
| addFormatterForFieldAnnotation(factory) | Đăng ký formatter theo annotation trên field |
| addPrinter(printer) | Đăng ký chiều in |
| addParser(parser) | Đăng ký chiều parse |
| addConverter(converter) | Đăng ký Converter |
| addConverterFactory(factory) | Đăng ký ConverterFactory |
| addGenericConverter(converter) | Đăng ký GenericConverter |

Việc chọn API phụ thuộc vào contract:

- Formatter có cả parse và print.
- Printer/Parser chỉ cung cấp một chiều; có thể đăng ký thành cặp.
- Formatter theo field type áp dụng cho kiểu field cụ thể.
- AnnotationFormatterFactory gắn format với annotation như @DateTimeFormat hoặc annotation domain do ứng dụng tạo.
- Converter được đăng ký vì FormatterRegistry kế thừa ConverterRegistry.

### 3.1. addFormatter và addFormatterForFieldType

addFormatter(formatter) suy ra kiểu T từ generic của Formatter<T>. Cách này thuận tiện khi formatter khai báo kiểu rõ ràng:

```java
registry.addFormatter(new OrderCodeFormatter());
```

addFormatterForFieldType cho phép chỉ định rõ kiểu field:

```java
registry.addFormatterForFieldType(
        OrderCode.class, new OrderCodeFormatter());
```

Cách thứ hai hữu ích khi cần đăng ký formatter dưới một field type cụ thể, ví dụ kiểu field là interface/base type khác với kiểu generic mà Printer/Formatter khai báo. Registry có thể thực hiện coercion khi kiểu khai báo và kiểu field không trùng trực tiếp; cần xác định đúng quan hệ kiểu và test hành vi mong muốn.

### 3.2. Đăng ký annotation formatter

Nếu format được quyết định bởi annotation của từng field thay vì một quy tắc toàn cục cho cả kiểu, có thể triển khai AnnotationFormatterFactory<A> rồi đăng ký:

```java
registry.addFormatterForFieldAnnotation(
        new ReferenceFormatAnnotationFormatterFactory());
```

Đây là snippet minh họa; factory phải triển khai các phương thức getFieldTypes(), getPrinter(annotation, fieldType) và getParser(annotation, fieldType). Kiểu field được factory hỗ trợ và annotation phải được xác định rõ. FormatterRegistrar thường là nơi gom một hoặc nhiều factory kiểu này với các formatter/converter khác.

## 4. Một registrar đăng ký nhiều quy tắc liên quan

Ví dụ module Billing cần hai formatter và một converter:

| Kiểu | Quy tắc | Hướng |
| --- | --- | --- |
| OrderCode | ORD- cộng bốn chữ số | String ↔ OrderCode |
| InvoiceReference | INV- cộng bốn chữ số | String ↔ InvoiceReference |
| DepartmentCode | DPT- cộng ba chữ cái | String → DepartmentCode |

Hai formatter chịu trách nhiệm parse/print. Converter của DepartmentCode chỉ cần chuyển chuỗi đầu vào thành value object; không giả định nó có chiều print ngược.

Registrar gom ba luật lại:

```java
public final class BillingFormatterRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                OrderCode.class, new OrderCodeFormatter());
        registry.addFormatterForFieldType(
                InvoiceReference.class,
                new InvoiceReferenceFormatter());
        registry.addConverter(new StringToDepartmentCode());
    }
}
```

Đây là snippet; các class formatter/value object/converter được định nghĩa trong phần ví dụ đầy đủ. Khi cần mở rộng quy tắc billing, thêm đăng ký liên quan trong registrar thay vì lặp lại ở từng controller.

**Không nên biến một registrar thành nơi đăng ký mọi format không liên quan.** Có thể chia thành DateTimeFormatterRegistrar, BillingFormatterRegistrar và CustomerFormatterRegistrar để mỗi nhóm có phạm vi trách nhiệm rõ ràng.

## 5. Ví dụ đầy đủ Java 17 và Spring Framework 6.2.6

Ví dụ dưới đây chạy độc lập, không cần Spring Boot, web server hay database. Nó tạo DefaultFormattingConversionService, gọi registrar và thực hiện parse/print.

### 5.1. Cấu trúc project

```text
formatter-registrar-demo/
├── pom.xml
└── src/main/java/demo/FormatterRegistrarDemo.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-registrar-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FormatterRegistrarDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

spring-context cung cấp formatting/conversion infrastructure cùng các module Spring phụ thuộc. Ví dụ chỉ dùng Java 17 và Spring; không dùng test framework.

### 5.3. Mã nguồn hoàn chỉnh

Tệp src/main/java/demo/FormatterRegistrarDemo.java:

```java
package demo;

import java.text.ParseException;
import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistrar;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class FormatterRegistrarDemo {

    public record OrderCode(String value) {
        public OrderCode {
            if (value == null || !value.matches("ORD-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid order code");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public record InvoiceReference(String value) {
        public InvoiceReference {
            if (value == null || !value.matches("INV-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid invoice reference");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public record DepartmentCode(String value) {
        public DepartmentCode {
            if (value == null || !value.matches("DPT-[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid department code");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static final class OrderCodeFormatter
            implements Formatter<OrderCode> {

        @Override
        public OrderCode parse(String text, Locale locale)
                throws ParseException {
            String normalized = text == null
                    ? ""
                    : text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("ORD-[0-9]{4}")) {
                throw new ParseException("Expected ORD- followed by 4 digits", 0);
            }
            return new OrderCode(normalized);
        }

        @Override
        public String print(OrderCode object, Locale locale) {
            return object.value();
        }
    }

    public static final class InvoiceReferenceFormatter
            implements Formatter<InvoiceReference> {

        @Override
        public InvoiceReference parse(String text, Locale locale)
                throws ParseException {
            String normalized = text == null
                    ? ""
                    : text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("INV-[0-9]{4}")) {
                throw new ParseException("Expected INV- followed by 4 digits", 0);
            }
            return new InvoiceReference(normalized);
        }

        @Override
        public String print(InvoiceReference object, Locale locale) {
            return object.value();
        }
    }

    public static final class StringToDepartmentCode
            implements Converter<String, DepartmentCode> {

        @Override
        public DepartmentCode convert(String source) {
            if (source == null) {
                throw new IllegalArgumentException("Department code is required");
            }

            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new DepartmentCode(normalized);
        }
    }

    public static final class BillingFormatterRegistrar
            implements FormatterRegistrar {

        @Override
        public void registerFormatters(FormatterRegistry registry) {
            registry.addFormatterForFieldType(
                    OrderCode.class, new OrderCodeFormatter());
            registry.addFormatterForFieldType(
                    InvoiceReference.class,
                    new InvoiceReferenceFormatter());
            registry.addConverter(new StringToDepartmentCode());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        new BillingFormatterRegistrar().registerFormatters(service);

        OrderCode order = service.convert(
                " ord-0042 ", OrderCode.class);
        InvoiceReference invoice = service.convert(
                " inv-0098 ", InvoiceReference.class);
        DepartmentCode department = service.convert(
                " dpt-sal ", DepartmentCode.class);

        String printedOrder = service.convert(order, String.class);
        String printedInvoice = service.convert(invoice, String.class);

        System.out.println("order=" + order);
        System.out.println("order.print=" + printedOrder);
        System.out.println("invoice=" + invoice);
        System.out.println("invoice.print=" + printedInvoice);
        System.out.println("department=" + department);
    }
}
```

Điểm cần chú ý:

1. Mỗi record bảo vệ format của chính value object bằng constructor invariant.
2. Formatter triển khai cả parse và print, nhận Locale dù ví dụ mã kỹ thuật không phụ thuộc locale.
3. Converter<String, DepartmentCode> chỉ có chiều String → DepartmentCode.
4. BillingFormatterRegistrar nhận FormatterRegistry và đăng ký ba quy tắc.
5. DefaultFormattingConversionService vừa có converter/formatter mặc định vừa là registry; ví dụ gọi registrar trực tiếp để dễ thấy thời điểm đăng ký.
6. Các class lồng trong một file để ví dụ Maven gọn; trong ứng dụng thực tế có thể tách thành các file/domain package riêng.

### 5.4. Chạy và stdout

Tại thư mục formatter-registrar-demo, cần JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Stdout do chương trình in:

```text
order=ORD-0042
order.print=ORD-0042
invoice=INV-0098
invoice.print=INV-0098
department=DPT-SAL
```

Giải thích:

- Các formatter được registry gắn với kiểu OrderCode và InvoiceReference; String có thể được parse thành object, object có thể được print thành String.
- Converter DepartmentCode chỉ tạo object khi đọc chuỗi; ví dụ không kiểm tra chiều DepartmentCode → String bằng converter đó.
- Thứ tự output theo thứ tự các lệnh println; không phụ thuộc thứ tự registry lưu formatter.
- Locale vẫn được truyền vào Formatter, nhưng format mã kỹ thuật được cố định bằng Locale.ROOT để không thay đổi theo máy người dùng.

Nếu thay chuỗi thành ord-XX42 hoặc inv-9, converter/formatter tương ứng từ chối input. canConvert cho biết có đường conversion theo kiểu, không đảm bảo nội dung từng giá trị hợp lệ.

## 6. Đăng ký registrar trong Spring MVC

Trong Spring MVC, WebMvcConfigurer cung cấp extension point addFormatters(FormatterRegistry). Đây là nơi thường gọi registrar để mọi controller sử dụng chung registry MVC.

```java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        new BillingFormatterRegistrar().registerFormatters(registry);
    }
}
```

Snippet này cần import Configuration, WebMvcConfigurer và FormatterRegistry; class BillingFormatterRegistrar là implementation ở phần trước. Trong Spring Boot MVC thông thường, có thể khai báo một cấu hình WebMvcConfigurer dạng bean và không cần bật @EnableWebMvc nếu không có chủ đích thay thế cấu hình MVC tự động.

Sau khi đăng ký, các kiểu được dùng trong:
- Query parameter và path variable bind vào tham số controller.
- Form object nhận qua @ModelAttribute.
- WebDataBinder trong những ngữ cảnh sử dụng FormattingConversionService MVC.

Ví dụ controller (snippet minh họa):

```java
@GetMapping("/orders/{code}")
public String order(@PathVariable OrderCode code) {
    return "Order code: " + code;
}

@PostMapping("/invoices")
public String createInvoice(
        @Valid @ModelAttribute("form") InvoiceForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "invoices/form";
    }
    return "redirect:/invoices/success";
}
```

InvoiceForm cần có property/constructor nhận InvoiceReference và import/validation tương ứng. Binding chỉ thành công khi tên field và conversion path phù hợp. BindingResult đặt ngay sau form để controller có thể xử lý lỗi.

**Không nên suy luận rằng đăng ký FormatterRegistrar trong MVC sẽ tự cấu hình mọi JSON body.** @RequestBody JSON thường được giải mã bằng HttpMessageConverter/Jackson với cấu hình riêng. Nếu JSON có dạng code chuỗi cần đổi sang value object, cần kiểm tra cấu hình deserializer/constructor Jackson hoặc adapter phù hợp cho JSON.

## 7. Dùng FormatterRegistrar với cấu hình XML

Spring cung cấp FormattingConversionServiceFactoryBean để tạo một formatting conversion service trong cấu hình XML. Factory bean hỗ trợ tập formatters, converters và formatter registrars.

Ví dụ cấu hình (đoạn XML minh họa, giả sử class BillingFormatterRegistrar có constructor mặc định):

```xml
<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="formatterRegistrars">
        <set>
            <bean class="demo.BillingFormatterRegistrar"/>
        </set>
    </property>
</bean>
```

Trong MVC XML namespace, có thể kết nối service này với annotation-driven configuration qua conversion-service attribute. Tên bean và package phải khớp class thực tế. Không khai báo đồng thời nhiều conversion service cùng thay thế nhau nếu chưa xác định rõ subsystem sử dụng bean nào.

Với Java configuration, WebMvcConfigurer.addFormatters thường rõ và gọn hơn cho ứng dụng MVC hiện đại. XML factory bean vẫn hữu ích ở ứng dụng cấu hình XML hoặc khi cần xây FormattingConversionService riêng để tiêm vào DataBinder/SpEL hay subsystem khác.

## 8. Nhóm quy tắc ngày giờ: DateTimeFormatterRegistrar

Spring có registrar dựng sẵn cho Java Time: org.springframework.format.datetime.standard.DateTimeFormatterRegistrar. Nó cho phép cấu hình các formatter và converter liên quan LocalDate, LocalTime, LocalDateTime, ZonedDateTime và các kiểu thời gian hỗ trợ khác.

Ví dụ dùng ISO format chung trong MVC:

```java
@Configuration
public class DateTimeWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

API setUseIsoFormat(true) yêu cầu registrar đăng ký định dạng ISO tương ứng thay vì style mặc định. Ngoài ra registrar cho phép cấu hình riêng DateFormatter, TimeFormatter, DateTimeFormatter hoặc FormatStyle cho từng nhóm. Nếu dùng một DateTimeFormatter cụ thể, các thiết lập style/ISO liên quan đến kiểu đó có thể bị ưu tiên bỏ qua theo hợp đồng setter của registrar.

Một registrar khác là DateFormatterRegistrar thuộc package org.springframework.format.datetime, chủ yếu hỗ trợ java.util.Date, Calendar và long trong ngữ cảnh cũ hơn. Nó có thể đăng ký DateFormatter và các converter date cần thiết. Với code mới dùng java.time, thường ưu tiên DateTimeFormatterRegistrar.

### 8.1. Vì sao date/time cần nhóm đăng ký riêng?

Ngày giờ có nhiều kiểu và chính sách:
- LocalDate chỉ có ngày, không chứa time-zone.
- LocalDateTime có ngày và giờ nhưng không có offset/zone.
- OffsetDateTime có offset UTC.
- ZonedDateTime gắn time-zone.
- Instant biểu diễn thời điểm trên trục UTC.

Một registrar có thể cấu hình một nhóm quy tắc nhất quán thay vì để từng controller tự tạo formatter. Nhưng phải chọn format theo hợp đồng giao tiếp: input HTML date/time có format cố định theo chuẩn trình duyệt; text input có thể chịu ảnh hưởng locale/request. ISO format thường phù hợp khi cần biểu diễn máy đọc được, còn style địa phương phù hợp với biểu mẫu người dùng nếu được xác định rõ.

## 9. FormatterRegistrar và AnnotationFormatterFactory

Hai SPI này có nhiệm vụ khác nhau và thường có thể dùng cùng nhau:

| Thành phần | Được kích hoạt theo | Vai trò |
| --- | --- | --- |
| FormatterRegistrar | Bước cấu hình đăng ký | Gom nhiều rule và đưa vào FormatterRegistry |
| AnnotationFormatterFactory | Annotation của field/parameter | Tạo Printer/Parser theo metadata annotation |
| Formatter<T> | Kiểu T và formatter được đăng ký | Parse/print value |
| FormatterRegistry | Kiểu/annotation/Converter pair được đăng ký | Tra cứu và quản lý rule |

Ví dụ ứng dụng có annotation @MoneyFormat(currency="VND") cho field BigDecimal. Một AnnotationFormatterFactory có thể cung cấp parser/printer dựa theo thuộc tính currency. BillingFormatterRegistrar có thể đăng ký factory đó cùng formatter OrderCode và converter DepartmentCode.

Như vậy registrar tổ chức nhóm rule, còn factory quyết định formatter cụ thể theo annotation. Không cần tạo annotation formatter factory nếu chỉ có một quy tắc cố định cho toàn bộ field của một kiểu.

## 10. Nhiều registrar và xung đột đăng ký

Một hệ thống có thể có nhiều nhóm:

```text
WebMvcConfigurer.addFormatters(registry)
        |
        +--> DateTimeFormatterRegistrar
        |
        +--> BillingFormatterRegistrar
        |
        +--> CustomerFormatterRegistrar
        |
        +--> Annotation Formatter Factories
        |
        +--> Custom Converters
```

Mỗi registrar cần có phạm vi rõ ràng. Một số nguyên tắc:

- Không đăng ký hai formatter cạnh tranh cho cùng kiểu field nếu không có mục tiêu override rõ ràng.
- Cẩn thận khi một Formatter được đăng ký theo cả generic inference và addFormatterForFieldType dưới nhiều type khác nhau.
- Converter và Formatter có thể cùng tạo đường String → T; tránh để hai rule cùng pair với cách parse khác nhau mà không có kiểm thử.
- Với annotation-driven formatter, xác định rõ annotation được ưu tiên và field type mà factory hỗ trợ.
- Đăng ký lúc cấu hình/startup, không bổ sung/loại bỏ rule tùy request.
- Không chia sẻ state mutable bên trong Formatter/Converter nếu nhiều request sẽ dùng đồng thời.

Thứ tự gọi registrar có thể ảnh hưởng việc một registry xử lý các rule trùng nhau. Đừng dựa vào thứ tự một cách ngầm định; hãy thiết kế tránh xung đột và test kết quả lookup.

## 11. Khi nào dùng registrar và khi nào gọi registry trực tiếp?

| Tình huống | Cách phù hợp |
| --- | --- |
| Chỉ có một formatter đơn giản | Gọi registry.addFormatter(...) trực tiếp |
| Có nhiều formatter cùng nhóm nghiệp vụ | Tạo FormatterRegistrar |
| Có formatter cho nhiều kiểu ngày giờ | Dùng DateTimeFormatterRegistrar hoặc registrar riêng |
| Cần nhóm converter và formatter | FormatterRegistrar vì registry cũng là ConverterRegistry |
| Cần formatter theo annotation | AnnotationFormatterFactory, đăng ký qua registry/registrar |
| Cần quy tắc riêng cho từng controller rất hẹp | Binder/controller configuration khi phù hợp, tránh làm global nếu không cần |
| Dùng chung toàn MVC | WebMvcConfigurer.addFormatters(...) gọi registrar |
| Dùng XML FormattingConversionServiceFactoryBean | Đưa registrar vào formatterRegistrars |

Không phải cứ có Formatter là bắt buộc có Registrar. Registrar hữu ích khi nó làm cho cấu hình nhóm rõ hơn, có thể tái sử dụng và dễ kiểm thử. Với một rule riêng lẻ, thêm một lớp registrar chỉ làm tăng gián tiếp không cần thiết.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Formatter không được gọi | Registrar chưa được đăng ký/gọi | Kiểm tra WebMvcConfigurer hoặc factory bean |
| Registry không tìm được format cho kiểu | Field type hoặc generic không khớp | Dùng addFormatterForFieldType và kiểm tra target type |
| Giá trị parse đúng nhưng print khác mong đợi | Formatter có quy tắc hai chiều không tương ứng | Kiểm thử parse/print và định nghĩa canonical representation |
| MVC dùng đúng nhưng JSON sai | JSON qua HttpMessageConverter/Jackson | Cấu hình Jackson riêng |
| Ngày giờ bị thay đổi theo locale | Dùng format phụ thuộc Locale nhưng hợp đồng client không dự kiến | Chọn ISO/format cố định hoặc thiết kế locale-aware rõ ràng |
| Hai formatter cùng kiểu xung đột | Đăng ký trùng quy tắc hoặc override không rõ | Loại bỏ rule thừa, test registry |
| Một converter chuỗi bị gọi thay vì formatter | Có nhiều conversion path cùng source/target | Rà soát Converter/Formatter pair và thứ tự đăng ký |
| Registrar có side effect khi request đến | Gọi registerFormatters không đúng vòng đời | Chỉ đăng ký khi cấu hình registry |
| Formatter không thread-safe | Chia sẻ object formatter mutable | Dùng implementation bất biến/thread-safe |
| Field annotation không được áp dụng | Factory chưa đăng ký hoặc annotation/type không được hỗ trợ | Kiểm tra factory, retention và getFieldTypes |
| DataBinder riêng không dùng registry MVC | Binder được tạo độc lập | Đặt ConversionService phù hợp cho binder |
| canConvert true nhưng một giá trị cụ thể lỗi | Đường kiểu tồn tại, dữ liệu sai | Xem ConversionFailedException/BindingResult |

## 13. Kiểm thử registrar và rule được đăng ký

Nên kiểm thử theo ba lớp:

**Unit test từng Formatter/Converter**
- Parse input canonical.
- Parse input có khoảng trắng.
- Print object thành canonical string.
- Từ chối dữ liệu sai, rỗng hoặc sai prefix.
- Với formatter phụ thuộc locale, test nhiều locale.

**Integration test registrar**
- Tạo DefaultFormattingConversionService.
- Gọi registrar.registerFormatters(service).
- Dùng service.canConvert(...) để kiểm tra đường chuyển đổi.
- Dùng service.convert(...) để xác minh parse và print.
- Kiểm tra converter một chiều không tự có chiều ngược.

**Integration test MVC**
- Gửi request parameter/path variable/form vào controller.
- Xác nhận binder dùng registry đã cấu hình.
- Test @ModelAttribute và BindingResult khi conversion sai.
- Tách test JSON @RequestBody nếu endpoint sử dụng Jackson.

Ví dụ test logic đơn giản có thể gọi service trực tiếp trong main hoặc JUnit. Đừng chỉ xác nhận method registerFormatters đã chạy; phải kiểm chứng kết quả trong registry mà runtime thực sự sử dụng.

## 14. Tự kiểm tra kiến thức

**Câu 1.** FormatterRegistrar có nhiệm vụ parse một chuỗi thành object không?

Không. Registrar đăng ký formatter/converter; Formatter hoặc Converter mới xử lý giá trị.

**Câu 2.** registerFormatters nhận loại tham số nào?

FormatterRegistry.

**Câu 3.** FormatterRegistry có đăng ký Converter được không?

Có. FormatterRegistry kế thừa ConverterRegistry.

**Câu 4.** Khi nào nên tạo FormatterRegistrar?

Khi muốn gom và tái sử dụng một nhóm formatter/converter liên quan hoặc cần cấu hình đăng ký phức tạp hơn một lệnh addFormatter đơn lẻ.

**Câu 5.** Implements FormatterRegistrar có làm Spring tự gọi registrar không?

Không. Cần gắn registrar vào WebMvcConfigurer, FormattingConversionServiceFactoryBean hoặc điểm cấu hình phù hợp.

**Câu 6.** DateTimeFormatterRegistrar dùng để làm gì?

Đăng ký nhóm formatter/converter cho các kiểu Java Time và cho phép cấu hình ISO/style/formatter theo nhu cầu.

**Câu 7.** Registrar MVC có tự cấu hình JSON Jackson không?

Không mặc định. JSON request/response thường có cơ chế HttpMessageConverter/Jackson riêng.

## 15. Checklist triển khai

1. Nhóm các formatter/converter theo một module hoặc domain rõ ràng.
2. Xác định quy tắc parse/print, Locale và canonical representation cho từng kiểu.
3. Dùng Formatter cho kiểu cần hai chiều String ↔ T; Converter cho luật chuyển kiểu phù hợp.
4. Triển khai FormatterRegistrar và đăng ký qua FormatterRegistry.
5. Gọi registrar ở cấu hình MVC hoặc FormattingConversionServiceFactoryBean; không chỉ tạo bean rồi giả định nó tự chạy.
6. Tránh formatter/converter trùng cặp kiểu với quy tắc mâu thuẫn.
7. Giữ formatter/converter stateless và thread-safe.
8. Test trực tiếp, test qua ConversionService/FormattingConversionService và test MVC.
9. Kiểm tra lỗi binding, input rỗng, locale và kiểu nested.
10. Cấu hình riêng Jackson nếu JSON cần định dạng riêng.

**Ghi nhớ:** FormatterRegistrar là điểm gom các lệnh đăng ký formatter và converter vào FormatterRegistry. Nó giúp chuẩn hóa quy tắc dùng chung qua nhiều form/controller và có thể đăng ký cả nhóm date/time hoặc nhóm nghiệp vụ. Runtime conversion vẫn do FormattingConversionService/ConversionService thực hiện; mỗi Formatter/Converter chịu trách nhiệm xử lý giá trị theo contract riêng.

## 16. Tài liệu chính thức

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Formatter, FormatterRegistry, FormatterRegistrar và annotation-driven formatting.
- [Spring Framework — MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký formatter/converter qua WebMvcConfigurer và DateTimeFormatterRegistrar.
- [Spring Javadoc — FormatterRegistrar 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistrar.html): contract registerFormatters(FormatterRegistry).
- [Spring Javadoc — FormatterRegistry 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html): addFormatter, addParser, addPrinter, addFormatterForFieldType và annotation.
- [Spring Javadoc — FormattingConversionService 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html): implementation của registry/service.
- [Spring Javadoc — DateTimeFormatterRegistrar 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html): cấu hình Java Time formatter và registerFormatters.
