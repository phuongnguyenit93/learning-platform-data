# AnnotationFormatterFactory và tạo annotation định dạng riêng trong Spring

## 1. Bài toán và vai trò của annotation formatter

Spring có hai SPI cơ bản cho định dạng văn bản: Printer<T> để in giá trị Java thành chuỗi và Parser<T> để đọc chuỗi thành giá trị Java. Formatter<T> kết hợp cả hai chiều. Chúng đặc biệt hữu ích khi ứng dụng cần chuyển dữ liệu phụ thuộc Locale như ngày, số và tiền.

Một kiểu Java có thể xuất hiện trong nhiều field nhưng mỗi field có quy tắc khác nhau. Ví dụ ba thuộc tính BigDecimal có thể lần lượt cần 2, 4 và 3 chữ số thập phân. Một formatter đăng ký chung theo kiểu BigDecimal không đủ để biết field hiện tại cần quy tắc nào; tạo riêng formatter cho từng field lại làm cấu hình rời rạc.

AnnotationFormatterFactory<A> giải quyết bài toán này bằng cách kết nối annotation trên field/parameter với parser và printer. Annotation chứa cấu hình; factory đọc annotation instance và kiểu field, rồi trả implementation phù hợp. Khi TypeDescriptor của lần conversion mang annotation, FormattingConversionService có thể chọn formatter theo metadata đó.

Trong bài này ta tạo annotation @DecimalPlaces(value), dùng cho BigDecimal để quy định số chữ số thập phân:

| Field | Annotation | Input/output theo Locale.US |
| --- | --- | --- |
| subtotal | @DecimalPlaces(2) | 1,234.50 |
| unitPrice | @DecimalPlaces(4) | 1,234.5000 |
| taxRate | @DecimalPlaces(3) | 0.082 |

Đây là quy ước trình bày và nhập liệu của ví dụ. Nó không phải quy tắc làm tròn/kế toán chung cho mọi loại tiền hay mọi domain.

## 2. API chính

### 2.1. Printer, Parser và Formatter

Các hợp đồng trong Spring:

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Formatter có cả chiều nhập và chiều hiển thị, nhận Locale ở mỗi lần gọi. Vì Locale là tham số, không cần lưu locale của request trong field mutable trên formatter singleton.

### 2.2. AnnotationFormatterFactory<A>

Factory thuộc package org.springframework.format. Các method trọng tâm:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();

    Printer<?> getPrinter(A annotation, Class<?> fieldType);

    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

| Method | Vai trò |
| --- | --- |
| getFieldTypes() | Khai báo kiểu field factory hỗ trợ |
| getPrinter(annotation, fieldType) | Tạo printer cho field mang annotation |
| getParser(annotation, fieldType) | Tạo parser cho field mang annotation |

A là kiểu annotation cụ thể. Spring cung cấp annotation instance đang gắn trên target và kiểu field tương ứng. Factory không tự kích hoạt chỉ nhờ annotation tồn tại; phải đăng ký nó vào FormatterRegistry/FormattingConversionService được dùng trong luồng conversion.

### 2.3. TypeDescriptor là cầu nối metadata

TypeDescriptor mô tả kiểu nguồn/đích phong phú hơn Class<?>: ngoài raw type, descriptor có thể chứa annotation metadata lấy từ Field hoặc MethodParameter. Ví dụ:

~~~java
Field field = InvoiceForm.class.getDeclaredField("subtotal");
TypeDescriptor descriptor = new TypeDescriptor(field);
~~~

Descriptor này mô tả BigDecimal và có thể đọc @DecimalPlaces(2). Nếu chỉ tạo TypeDescriptor.valueOf(BigDecimal.class), metadata của field cụ thể không tồn tại; factory không thể biết field đó cần scale 2 hay scale 4.

## 3. Thiết kế annotation

File DecimalPlaces.java:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
public @interface DecimalPlaces {
    int value() default 2;
}
~~~

Lý do:

- RUNTIME để reflection và TypeDescriptor có thể đọc annotation khi ứng dụng chạy.
- FIELD hỗ trợ annotation trực tiếp trên field.
- METHOD và PARAMETER cho phép dùng ở các vị trí khác nếu đường tích hợp tạo descriptor phù hợp; ví dụ chạy trong bài tập này chỉ dùng FIELD.
- value là số chữ số sau dấu thập phân, mặc định 2.

Annotation không tự giới hạn miền giá trị. Ví dụ cho phép 0 đến 8 chữ số là một policy của ứng dụng; factory/formatter phải kiểm tra giá trị để cấu hình sai không âm thầm đi vào hệ thống.

## 4. Viết Formatter<BigDecimal>

File DecimalPlacesFormatter.java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class DecimalPlacesFormatter
        implements Formatter<BigDecimal> {

    private final int scale;

    public DecimalPlacesFormatter(int scale) {
        if (scale < 0 || scale > 8) {
            throw new IllegalArgumentException(
                    "Scale must be between 0 and 8");
        }
        this.scale = scale;
    }

    private DecimalFormat newFormat(Locale locale) {
        String pattern = scale == 0
                ? "#,##0"
                : "#,##0." + "0".repeat(scale);

        DecimalFormat format = new DecimalFormat(
                pattern, DecimalFormatSymbols.getInstance(locale));
        format.setParseBigDecimal(true);
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format;
    }

    @Override
    public String print(BigDecimal value, Locale locale) {
        if (value == null) {
            return "";
        }
        return newFormat(locale).format(value);
    }

    @Override
    public BigDecimal parse(String text, Locale locale) {
        if (text == null || text.isBlank()) {
            return null;
        }

        String candidate = text.trim();
        ParsePosition position = new ParsePosition(0);
        Number parsed = newFormat(locale).parse(candidate, position);

        if (!(parsed instanceof BigDecimal decimal)
                || position.getIndex() != candidate.length()
                || position.getErrorIndex() >= 0) {
            throw new IllegalArgumentException("Invalid decimal input");
        }

        return decimal.setScale(scale, RoundingMode.UNNECESSARY);
    }
}
~~~

Thiết kế có chủ đích:

1. scale là final nên cấu hình formatter bất biến sau khi tạo.
2. DecimalFormat được tạo mới trong từng lần parse/print. DecimalFormat mutable, không an toàn khi dùng chung đồng thời giữa các request.
3. DecimalFormatSymbols lấy từ Locale được truyền vào, không dựa vào locale mặc định của máy.
4. setParseBigDecimal(true) giúp giữ độ chính xác decimal thay vì parse qua Double.
5. ParsePosition kiểm tra toàn bộ input đã được tiêu thụ. Chuỗi "12abc" không được chấp nhận chỉ vì prefix "12" parse được.
6. setScale với UNNECESSARY từ chối input có nhiều chữ số thập phân hơn annotation cho phép. Việc từ chối hay làm tròn input là quyết định nghiệp vụ; không để DecimalFormat tự quyết định thay contract của API.

Ví dụ này dùng HALF_UP khi print và từ chối input có precision vượt scale khi parse. Hai chiều có thể có policy khác nhau, nhưng phải ghi rõ và kiểm thử. Nếu domain yêu cầu làm tròn đồng nhất hoặc theo currency, hãy đặt quy tắc đó ở domain/service phù hợp.

## 5. Tạo AnnotationFormatterFactory

File DecimalPlacesAnnotationFormatterFactory.java:

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.format.AnnotationFormatterFactory;
import org.springframework.format.Parser;
import org.springframework.format.Printer;

public final class DecimalPlacesAnnotationFormatterFactory
        implements AnnotationFormatterFactory<DecimalPlaces> {

    @Override
    public Set<Class<?>> getFieldTypes() {
        return Set.of(BigDecimal.class);
    }

    @Override
    public Printer<?> getPrinter(
            DecimalPlaces annotation, Class<?> fieldType) {
        return new DecimalPlacesFormatter(annotation.value());
    }

    @Override
    public Parser<?> getParser(
            DecimalPlaces annotation, Class<?> fieldType) {
        return new DecimalPlacesFormatter(annotation.value());
    }
}
~~~

Factory chỉ tuyên bố hỗ trợ BigDecimal. Printer và Parser cùng dùng formatter cấu hình theo value của annotation. Có thể trả hai instance riêng vì API hai chiều độc lập; trong ví dụ formatter chỉ giữ scale bất biến và tạo DecimalFormat cục bộ.

Không khai báo Number.class nếu implementation không xử lý đúng mọi subclass Number. getFieldTypes là hợp đồng của factory, vì vậy phải phản ánh đúng những kiểu mà parser/printer thực sự hỗ trợ.

## 6. Gắn annotation lên model

File InvoiceForm.java:

~~~java
import java.math.BigDecimal;

public class InvoiceForm {

    @DecimalPlaces(2)
    private BigDecimal subtotal;

    @DecimalPlaces(4)
    private BigDecimal unitPrice;

    @DecimalPlaces(3)
    private BigDecimal taxRate;

    public BigDecimal getSubtotal() { return subtotal; }
    public void setSubtotal(BigDecimal value) { this.subtotal = value; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal value) { this.unitPrice = value; }

    public BigDecimal getTaxRate() { return taxRate; }
    public void setTaxRate(BigDecimal value) { this.taxRate = value; }
}
~~~

Cùng một kiểu Java BigDecimal nhưng mỗi field mang annotation instance riêng. Metadata được dùng khi Spring conversion xử lý descriptor của field. Annotation format nên đặt trên DTO/form hoặc property có trách nhiệm trình bày; không nên làm cho mọi entity persistence bị phụ thuộc vào quy ước của một giao diện cụ thể.

Nếu annotation đặt trên getter thay vì field, phải bảo đảm metadata accessor thực tế mà Spring dùng có thể nhìn thấy annotation đó. Tránh đặt annotation ở field nhưng lại tạo descriptor từ một getter khác mà không hiểu cách introspection kết hợp metadata.

## 7. Đăng ký factory

### 7.1. Đăng ký thủ công

~~~java
FormattingConversionService conversionService =
        new FormattingConversionService();

conversionService.addFormatterForFieldAnnotation(
        new DecimalPlacesAnnotationFormatterFactory());
~~~

Đây là cấu hình cho một conversion service được tạo trực tiếp. Code sử dụng service này phải thực sự gọi đúng instance đã cấu hình.

### 7.2. Đăng ký cho Spring MVC

Trong ứng dụng MVC, có thể dùng WebMvcConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldAnnotation(
                new DecimalPlacesAnnotationFormatterFactory());
    }
}
~~~

Spring MVC gọi addFormatters để cấu hình registry phục vụ conversion/formatting trong binder. Với Spring Boot MVC, WebMvcConfigurer thường là cách mở rộng cấu hình sẵn có; không tự thay thế toàn bộ MVC infrastructure chỉ để thêm factory.

Nếu converter đã đăng ký trong một FormattingConversionService do test tự tạo, điều đó không chứng minh MVC production đang dùng service ấy. Luôn kiểm tra đúng registry trong đường request thực tế.

## 8. Dùng TypeDescriptor để parse và print theo field

Đoạn sau tạo descriptor từ field subtotal:

~~~java
Field field = InvoiceForm.class.getDeclaredField("subtotal");
TypeDescriptor fieldType = new TypeDescriptor(field);
~~~

Vì descriptor mang @DecimalPlaces(2), FormattingConversionService có thể chọn parser/printer tương ứng:

~~~java
LocaleContextHolder.setLocale(Locale.US);
try {
    BigDecimal parsed = (BigDecimal) conversionService.convert(
            "1,234.50",
            TypeDescriptor.valueOf(String.class),
            fieldType);

    String printed = (String) conversionService.convert(
            new BigDecimal("1234.5"),
            fieldType,
            TypeDescriptor.valueOf(String.class));

    System.out.println(parsed.toPlainString());
    System.out.println(printed);
} finally {
    LocaleContextHolder.resetLocaleContext();
}
~~~

LocaleContextHolder được đặt để demo có kết quả xác định và được reset trong finally. Trong request MVC bình thường, locale context do framework quản lý theo vòng đời request. Không lưu Locale hiện tại trong field của singleton formatter.

Kết quả mong đợi:

~~~text
1234.50
1,234.50
~~~

Khi chuyển đổi theo field descriptor, factory biết annotation của field. Nếu chỉ truyền BigDecimal.class, metadata field không có và quy tắc theo annotation không thể được chọn.

## 9. Ví dụ chạy độc lập bằng Java 17+ và Gradle

Tạo project với các file: DecimalPlaces.java, DecimalPlacesFormatter.java, DecimalPlacesAnnotationFormatterFactory.java, InvoiceForm.java và AnnotationFormatterFactoryDemo.java. Đặt chúng trong cùng package (ví dụ mặc định bên dưới).

settings.gradle:

~~~groovy
rootProject.name = 'annotation-formatter-factory-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'AnnotationFormatterFactoryDemo'
}
~~~

AnnotationFormatterFactoryDemo.java:

~~~java
import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.support.FormattingConversionService;

public class AnnotationFormatterFactoryDemo {

    public static void main(String[] args) throws Exception {
        FormattingConversionService service =
                new FormattingConversionService();

        service.addFormatterForFieldAnnotation(
                new DecimalPlacesAnnotationFormatterFactory());

        Field subtotalField =
                InvoiceForm.class.getDeclaredField("subtotal");
        TypeDescriptor subtotalType =
                new TypeDescriptor(subtotalField);

        Field unitPriceField =
                InvoiceForm.class.getDeclaredField("unitPrice");
        TypeDescriptor unitPriceType =
                new TypeDescriptor(unitPriceField);

        LocaleContextHolder.setLocale(Locale.US);
        try {
            BigDecimal subtotal = (BigDecimal) service.convert(
                    "1,234.50",
                    TypeDescriptor.valueOf(String.class),
                    subtotalType);

            BigDecimal unitPrice = (BigDecimal) service.convert(
                    "1,234.5000",
                    TypeDescriptor.valueOf(String.class),
                    unitPriceType);

            String subtotalText = (String) service.convert(
                    new BigDecimal("1234.5"),
                    subtotalType,
                    TypeDescriptor.valueOf(String.class));

            String unitPriceText = (String) service.convert(
                    new BigDecimal("1234.5"),
                    unitPriceType,
                    TypeDescriptor.valueOf(String.class));

            System.out.println("subtotal=" + subtotal.toPlainString());
            System.out.println("unitPrice=" + unitPrice.toPlainString());
            System.out.println("subtotalText=" + subtotalText);
            System.out.println("unitPriceText=" + unitPriceText);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Chạy từ thư mục dự án với JDK 17+:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper, dùng ./gradlew -q run trên Linux/macOS hoặc gradlew.bat -q run trên Windows. Máy cần truy cập Maven Central nếu dependency chưa được cache.

Stdout mong đợi:

~~~text
subtotal=1234.50
unitPrice=1234.5000
subtotalText=1,234.50
unitPriceText=1,234.5000
~~~

Ví dụ thể hiện cùng một factory điều khiển hai field cùng kiểu nhưng có annotation value khác nhau. AnnotationFormatterFactoryDemo.java không độc lập một mình: cần bốn file phụ trợ cùng package như đã liệt kê.

## 10. Cách Spring chọn factory và các giới hạn

Factory chỉ được áp dụng nếu các điều kiện sau phù hợp:

1. Annotation có retention runtime.
2. Annotation nằm ở vị trí metadata mà descriptor của lần conversion có thể đọc.
3. Source/target TypeDescriptor chứa annotation tương ứng.
4. Field type thuộc tập do getFieldTypes() trả về.
5. Factory được đăng ký trong đúng FormatterRegistry.
6. Code đi qua conversion service có registry đó.

Khi có nhiều factory hoặc formatter cùng có thể áp dụng, cần tránh cấu hình mơ hồ và test thứ tự/khả năng chọn trong phiên bản Spring cụ thể. Không dựa vào thứ tự component scan như một hợp đồng.

Một annotation trên field List<BigDecimal> không mặc nhiên có nghĩa factory hỗ trợ annotation trên từng phần tử BigDecimal. Field type và element type là metadata ở cấp khác nhau. Nếu muốn format từng phần tử dựa trên type-use annotation, cần thiết kế annotation target và kiểm tra TypeDescriptor ở element level; không dùng ví dụ field formatter để suy ra hỗ trợ tự động cho mọi generic element.

AnnotationFormatterFactory phục vụ formatting theo annotation. Nó không thay thế Converter cho mọi chuyển đổi và cũng không thay thế Bean Validation: một chuỗi có thể parse thành BigDecimal nhưng vẫn vi phạm giới hạn nghiệp vụ.

## 11. Chọn annotation formatter hay cơ chế có sẵn?

Spring đã có @DateTimeFormat và @NumberFormat. Hãy dùng chúng khi quy tắc phổ biến đã được đáp ứng.

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Ngày ISO hoặc pattern | @DateTimeFormat |
| Số, currency, percent thông dụng | @NumberFormat |
| Quy tắc parse/print tùy biến theo annotation riêng | AnnotationFormatterFactory |
| Chuyển một cặp kiểu không cần print | Converter<S,T> |
| Chuyển đổi phụ thuộc generic/metadata phức tạp | GenericConverter / ConditionalGenericConverter |
| Quy tắc nghiệp vụ sau khi parse | Validator / Jakarta Bean Validation / service |

AnnotationFormatterFactory thích hợp khi field cần cấu hình formatter riêng có thể khai báo ngay tại model. Nếu quy tắc phụ thuộc currency, tenant hoặc policy thay đổi theo thời gian, cần cân nhắc đưa policy vào tầng phù hợp thay vì nhồi toàn bộ logic vào annotation tĩnh.

## 12. Locale, thread safety và hiệu năng

FormattingConversionService thường được dùng chung trong application context. Factory và formatter vì vậy cần an toàn khi nhiều thread cùng gọi.

- Giữ cấu hình formatter bất biến, ví dụ scale trong final field.
- Không lưu giá trị parse gần nhất, Locale, request, BindingResult hoặc WebDataBinder trong field.
- DecimalFormat mutable được tạo mới trong mỗi call.
- Dùng Locale truyền vào phương thức thay vì locale hệ thống ngầm định.
- Không gọi database/HTTP để quyết định cách parse chuỗi.
- Không nuốt lỗi parse thành null; empty và malformed là hai trường hợp khác nhau.
- Tránh cache formatter nếu cache làm chia sẻ object mutable hoặc không cần thiết.

Nếu muốn cache formatter theo scale, chỉ cache formatter bất biến và bảo đảm mọi helper mutable vẫn được tạo theo từng lần gọi. Benchmark trước khi tối ưu allocation; correctness quan trọng hơn việc giảm một object nhỏ.

## 13. Kiểm thử đầy đủ

### 13.1. Parse và print

Với @DecimalPlaces(2), test:

- Parse "1,234.50" thành BigDecimal 1234.50.
- Print BigDecimal 1234.5 thành "1,234.50".
- Parse "12abc" phải thất bại vì còn suffix.
- Parse "1,234.567" phải tuân thủ policy scale (ví dụ này từ chối).
- Chuỗi rỗng trả null theo hợp đồng đã định.
- Scale âm hoặc trên 8 bị từ chối.

Với @DecimalPlaces(4), cùng factory cần parse/print bốn chữ số. Kiểm tra chính BigDecimal scale nếu contract cần phân biệt 1234.50 và 1234.5000.

### 13.2. Locale

Cùng một số có thể được viết khác nhau theo Locale.US và Locale.GERMANY. Thiết lập locale từng test và reset context sau đó. Không coi chuỗi "1.234,50" hợp lệ ở tất cả locale.

API trao đổi giữa hệ thống thường nên có wire format ổn định, không phụ thuộc locale. Định dạng theo người dùng phù hợp cho giao diện, không nhất thiết phù hợp để lưu trữ hoặc tích hợp ngoài.

### 13.3. Spring MVC integration

Dùng MockMvc hoặc request thực để xác minh:

- @InitBinder/FormatterRegistry đã đăng ký factory.
- @ModelAttribute field có annotation được parse đúng.
- Giá trị trả về được print đúng khi render form.
- Lỗi parse được đưa vào BindingResult theo đường MVC.
- Hai field có scale khác nhau không dùng nhầm cấu hình.
- Các request có locale khác nhau không làm rò state.

### 13.4. Concurrency

Dùng cùng FormattingConversionService và factory đã đăng ký từ nhiều thread. Mỗi task parse/print input riêng rồi so output. Kiểm tra thread cleanup cho LocaleContextHolder. Không chia sẻ DecimalFormat giữa các task. Test concurrency bổ trợ cho review code; nó không chứng minh tuyệt đối mọi race condition không thể xảy ra.

## 14. Lỗi thường gặp

**Annotation không được áp dụng:** kiểm tra RUNTIME, target, field descriptor và factory registry.

**Factory không được chọn:** kiểm tra getFieldTypes, kiểu thực của field và conversion có dùng TypeDescriptor lấy từ field không.

**Chỉ tạo descriptor từ BigDecimal.class:** descriptor đó không mang annotation cụ thể của property.

**Parse prefix nhưng chấp nhận suffix:** kiểm tra ParsePosition đã tiêu thụ toàn bộ chuỗi.

**DecimalFormat dùng chung gây sai kết quả đồng thời:** tạo DecimalFormat theo từng call.

**Locale của request này ảnh hưởng request khác:** không giữ locale trong formatter field; dùng tham số Locale và quản lý context đúng vòng đời.

**Input sai bị chuyển thành null:** phân biệt chuỗi rỗng với malformed; giữ exception để binder xử lý.

**Factory công bố quá nhiều kiểu:** getFieldTypes chỉ chứa field type implementation hỗ trợ.

**Làm tròn không rõ:** quy định riêng parse và print, ghi rõ rounding mode.

**Nhầm formatting với validation:** parse thành công không đồng nghĩa giá trị hợp lệ theo nghiệp vụ.

**Tạo annotation cho yêu cầu đã có sẵn:** xem @DateTimeFormat và @NumberFormat trước khi tự viết factory.

## 15. Checklist triển khai

1. Annotation có tên và thuộc tính diễn đạt đúng policy?
2. Retention có RUNTIME?
3. Target annotation phù hợp vị trí field/parameter đang dùng?
4. Factory khai báo chính xác field types?
5. getPrinter và getParser có dùng annotation instance?
6. Formatter xử lý null, empty, malformed, locale và rounding rõ ràng?
7. Parser xác minh toàn bộ chuỗi?
8. Mutable helper có được tạo trong từng lần gọi?
9. Factory/formatter có giữ cấu hình immutable?
10. Đã đăng ký factory vào đúng MVC FormattingConversionService?
11. TypeDescriptor có giữ annotation từ field?
12. Có test parse và print cho nhiều giá trị annotation?
13. Có test locale, malformed input và concurrency?
14. Có integration test qua MockMvc/WebDataBinder?
15. Đã đối chiếu Javadoc đúng phiên bản Spring đang dùng?

## 16. Tài liệu chính thức

- [Spring Framework – Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [AnnotationFormatterFactory Javadoc (Spring 6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html)
- [Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Formatter.html)
- [Printer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Printer.html)
- [Parser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Parser.html)
- [FormatterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [FormattingConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/support/FormattingConversionService.html)
- [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [Java DecimalFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [Java Locale API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)

**Nguyên tắc cốt lõi:** AnnotationFormatterFactory ánh xạ annotation metadata thành parser/printer phù hợp với kiểu field. Muốn hoạt động đúng, annotation phải có runtime retention, factory phải đăng ký đúng registry, TypeDescriptor phải mang annotation, và formatter phải xử lý Locale cùng mutable parsing state an toàn. Hãy test cả parse/print và qua chính đường binding mà ứng dụng sẽ sử dụng.
