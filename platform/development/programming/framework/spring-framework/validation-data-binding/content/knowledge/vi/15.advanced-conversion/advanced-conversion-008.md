# Chuyển đổi theo annotation trên trường hoặc tham số trong Spring

## 1. Ý tưởng cốt lõi: cùng kiểu Java nhưng định dạng khác nhau

Một ứng dụng có thể có nhiều thuộc tính cùng kiểu Java nhưng nhận hoặc hiển thị theo quy tắc văn bản khác nhau. Ví dụ: một LocalDate được nhập theo ISO yyyy-MM-dd; một LocalDate khác được nhập theo dd/MM/yyyy; hai BigDecimal có thể lần lượt biểu diễn phần trăm và tiền tệ; hai tham số method cùng kiểu String nhưng một tham số cần parse thành ngày còn tham số kia giữ nguyên.

Nếu chỉ nhìn vào cặp kiểu String → LocalDate hoặc String → BigDecimal, ConversionService chưa biết thuộc tính cụ thể đang mang hợp đồng định dạng nào. **TypeDescriptor** và cơ chế **annotation-driven formatting** bổ sung metadata của field hoặc method parameter vào quyết định chuyển đổi.

Annotation thường gặp gồm:

- **@DateTimeFormat**: định dạng ngày/giờ trên field hoặc method parameter.
- **@NumberFormat**: định dạng số trên field hoặc method parameter.
- **@DurationFormat**: định dạng Duration trong các phiên bản Spring có hỗ trợ.
- Annotation tùy chỉnh kết hợp **AnnotationFormatterFactory**: định nghĩa parser/printer riêng.

Annotation không tự chạy như một lệnh parse độc lập. Nó được đọc bởi cơ chế formatting trong **FormattingConversionService**, thông qua metadata của TypeDescriptor. Khi binder hoặc ứng dụng thực hiện conversion với descriptor đó, Spring có thể chọn parser/printer gắn với annotation.

## 2. TypeDescriptor là cầu nối giữa annotation và conversion

Hai cách chuyển đổi dưới đây không mang cùng mức metadata:

~~~java
service.convert("29/02/2024", String.class, LocalDate.class);
~~~

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String.class);
TypeDescriptor target = new TypeDescriptor(dateField);

service.convert("29/02/2024", source, target);
~~~

Cách thứ hai truyền descriptor của một field cụ thể, do đó Spring có thể đọc @DateTimeFormat trên field. Đây là lý do bài này thuộc nhóm **Chuyển đổi nâng cao**: quyết định chuyển đổi không chỉ phụ thuộc kiểu nguồn/đích, mà còn có thể phụ thuộc metadata khai báo tại nơi dùng giá trị.

TypeDescriptor có thể mang:
- Kiểu Java cơ bản.
- Generic type, component type, key/value type của container.
- Annotation hiện diện trên field, method parameter hoặc property.
- Ngữ cảnh khai báo của descriptor.

Ví dụ lấy metadata field:

~~~java
Field field = BookingForm.class.getDeclaredField("travelDate");
TypeDescriptor descriptor = new TypeDescriptor(field);
~~~

Với method parameter, có thể tạo MethodParameter rồi truyền cho TypeDescriptor:

~~~java
Method method = SearchController.class.getMethod("search", LocalDate.class);
MethodParameter parameter = new MethodParameter(method, 0);
TypeDescriptor descriptor = new TypeDescriptor(parameter);
~~~

Đây là ví dụ lấy metadata; cần class, import và method tương ứng. Không dùng TypeDescriptor.valueOf(LocalDate.class) khi cần annotation cụ thể, vì descriptor tạo chỉ từ Class không biết field/parameter nào đã mang annotation.

## 3. Annotation có sẵn trong Spring

### 3.1. @DateTimeFormat

@DateTimeFormat có thể đặt trên **field** hoặc **method parameter**. Nó hỗ trợ java.util.Date, Calendar, Long ở ngữ cảnh timestamp và các kiểu java.time được Spring hỗ trợ.

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate departureDate;

@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate localDate;

@DateTimeFormat(style = "M-")
private LocalDate mediumDate;
~~~

- **iso** dùng định dạng chuẩn ISO được chọn, ví dụ ISO.DATE.
- **pattern** dùng mẫu cụ thể; lựa chọn rõ ràng khi hợp đồng API quy định format.
- **style** dựa trên format theo Locale và có thể thay đổi theo môi trường Java/Locale; không nên dùng khi cần hợp đồng wire format ổn định.
- **fallbackPatterns** cho phép khai báo mẫu dự phòng khi cần hỗ trợ dữ liệu cũ hoặc nhiều định dạng đầu vào.
- Các thuộc tính style, iso và pattern có quan hệ loại trừ theo hợp đồng annotation; chọn một cách cho mỗi annotation instance.

Đối với java.util.Date, múi giờ ảnh hưởng ý nghĩa thời điểm. Với java.time.LocalDate, kiểu không lưu giờ/múi giờ; hãy chọn kiểu miền phù hợp với ngày lịch hay thời điểm thực.

Tài liệu Spring cảnh báo style-based parsing phụ thuộc Locale và pattern runtime, có thể thay đổi khi chạy trên JDK mới (đặc biệt JDK 20+). Nếu định dạng là một phần của hợp đồng hệ thống, ưu tiên ISO hoặc pattern cụ thể do ứng dụng kiểm soát.

### 3.2. @NumberFormat

@NumberFormat hỗ trợ kiểu Number như BigDecimal, Integer và các kiểu số phù hợp khác.

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@NumberFormat(style = NumberFormat.Style.CURRENCY)
private BigDecimal total;
~~~

- **pattern** mô tả mẫu số cụ thể theo quy tắc NumberFormat.
- **style** có các lựa chọn NUMBER, PERCENT và CURRENCY.
- Cách parse/print có thể phụ thuộc Locale; ứng dụng web cần thống nhất Locale và cách client gửi số.
- Format hiển thị không tự trở thành quy tắc nghiệp vụ như amount phải lớn hơn 0 hoặc không vượt ngân sách.

Ví dụ chuỗi 1,234.50 và 1.234,50 có thể mang ý nghĩa khác nhau theo Locale. Nếu nhận dữ liệu từ API tích hợp, hãy quy định format rõ ràng, không tự thay dấu chấm/phẩy bằng thao tác chuỗi tùy tiện.

### 3.3. Annotation khác và phạm vi hỗ trợ

Tùy phiên bản Spring, các annotation formatting khác như **@DurationFormat** cũng được hỗ trợ. Kiểm tra Javadoc của đúng phiên bản ứng dụng trước khi sử dụng. Annotation validation như @Min, @NotNull hay @Pattern không phải annotation formatter: chúng kiểm tra ràng buộc, không tạo parser/printer.

| Nhóm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Format annotation | @DateTimeFormat, @NumberFormat | Hướng dẫn parse/print dựa trên metadata |
| Validation annotation | @NotNull, @Min, @Pattern | Kiểm tra giá trị có thỏa constraint không |
| JSON mapping annotation | @JsonProperty | Ánh xạ tên property khi Jackson đọc/ghi JSON |
| Binding annotation | @ModelAttribute, @BindParam | Xác định cách nhận và bind dữ liệu trong Spring MVC |

## 4. Cơ chế phía sau: AnnotationFormatterFactory

Spring định nghĩa giao diện:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();
    Printer<?> getPrinter(A annotation, Class<?> fieldType);
    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

Ba phương thức có vai trò:

- **getFieldTypes()**: trả về tập kiểu field được phép sử dụng annotation này.
- **getPrinter(annotation, fieldType)**: cung cấp formatter để in giá trị Java thành chuỗi.
- **getParser(annotation, fieldType)**: cung cấp parser để chuyển chuỗi đầu vào thành giá trị Java.

Spring dùng annotation được tìm thấy trong TypeDescriptor để hỏi factory và lấy parser/printer phù hợp. Giao diện này hữu ích khi định dạng phụ thuộc annotation do ứng dụng tự định nghĩa hoặc cần mở rộng annotation-based formatting.

Một **Formatter<T>** kết hợp cả hai vai trò Printer<T> và Parser<T>:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {}
~~~

Parser<T>.parse(String text, Locale locale) chuyển văn bản thành đối tượng. Printer<T>.print(T object, Locale locale) chuyển đối tượng thành văn bản.

### Phân biệt AnnotationFormatterFactory và ConditionalGenericConverter

| Cơ chế | Dùng khi | Metadata chính |
| --- | --- | --- |
| AnnotationFormatterFactory | Annotation điều khiển parse/print cho field hoặc parameter | Annotation + kiểu field |
| ConditionalGenericConverter | Converter cần điều kiện chọn nâng cao theo descriptor | Source/target TypeDescriptor |
| Converter<S,T> | Chuyển một cặp kiểu đơn giản, không cần context annotation | Kiểu nguồn và đích |
| Formatter<T> | Định dạng một kiểu theo Locale | Giá trị + Locale |

Không cần tạo AnnotationFormatterFactory nếu @DateTimeFormat hoặc @NumberFormat đã giải quyết nhu cầu. Chỉ viết factory riêng khi quy tắc có giá trị tái sử dụng và cần gắn tường minh với annotation riêng.

## 5. Ví dụ annotation formatter tùy chỉnh

Giả sử ứng dụng có annotation **@TrimmedUppercase** để một số trường String được parse bằng cách bỏ khoảng trắng đầu/cuối và chuyển thành chữ hoa theo Locale.ROOT. Đây là ví dụ kỹ thuật; hệ thống thực cần cân nhắc field nào được phép biến đổi vì tên hiển thị có thể cần giữ nguyên chữ thường.

Annotation:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface TrimmedUppercase {
}
~~~

Formatter:

~~~java
public final class UppercaseFormatter implements Formatter<String> {

    @Override
    public String parse(String text, Locale locale) {
        return text == null ? null : text.strip().toUpperCase(Locale.ROOT);
    }

    @Override
    public String print(String object, Locale locale) {
        return object == null ? "" : object;
    }
}
~~~

Factory:

~~~java
public final class TrimmedUppercaseAnnotationFormatterFactory
        implements AnnotationFormatterFactory<TrimmedUppercase> {

    @Override
    public Set<Class<?>> getFieldTypes() {
        return Set.of(String.class);
    }

    @Override
    public Printer<?> getPrinter(
            TrimmedUppercase annotation, Class<?> fieldType) {
        return new UppercaseFormatter();
    }

    @Override
    public Parser<?> getParser(
            TrimmedUppercase annotation, Class<?> fieldType) {
        return new UppercaseFormatter();
    }
}
~~~

Đăng ký trong FormattingConversionService:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addFormatterForFieldAnnotation(
        new TrimmedUppercaseAnnotationFormatterFactory());
~~~

Sau đó dùng trên model:

~~~java
public final class CustomerForm {
    @TrimmedUppercase
    private String customerCode;

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }
}
~~~

Khi conversion dùng descriptor của field customerCode, Spring có thể kích hoạt factory tương ứng. Nếu chỉ truyền String.class và String.class, metadata annotation của field không có mặt; không thể kỳ vọng factory được chọn theo field annotation.

## 6. Ví dụ Java 17+ hoàn chỉnh: field và method parameter

Ví dụ Maven dùng **Java 17** và **Spring Framework 6.2.15**. Nó minh họa:
1. @DateTimeFormat trên field LocalDate.
2. @NumberFormat trên field BigDecimal.
3. @DateTimeFormat trên method parameter.
4. Conversion bằng TypeDescriptor trích từ đúng field/parameter.
5. Cùng kiểu đích nhưng descriptor không có annotation không tự mang định dạng của field.

Cấu trúc:

~~~text
annotation-formatting-demo/
├── pom.xml
└── src/main/java/demo/AnnotationFormattingDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>annotation-formatting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.15</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/AnnotationFormattingDemo.java**:

~~~java
package demo;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class AnnotationFormattingDemo {

    public static final class BookingForm {
        @DateTimeFormat(pattern = "dd/MM/yyyy")
        private LocalDate travelDate;

        @NumberFormat(pattern = "#,##0.00")
        private BigDecimal amount;

        public LocalDate getTravelDate() { return travelDate; }
        public void setTravelDate(LocalDate travelDate) {
            this.travelDate = travelDate;
        }
        public BigDecimal getAmount() { return amount; }
        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    public static final class SearchParameters {
        public void search(
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate date) {
            // Chỉ cần chữ ký method để tạo MethodParameter.
        }
    }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);
        ConversionService service = new DefaultFormattingConversionService();

        Field dateField = BookingForm.class.getDeclaredField("travelDate");
        TypeDescriptor dateTarget = new TypeDescriptor(dateField);

        LocalDate date = (LocalDate) service.convert(
                "29/02/2024",
                TypeDescriptor.valueOf(String.class),
                dateTarget);
        System.out.println("FIELD_DATE=" + date);

        Field amountField = BookingForm.class.getDeclaredField("amount");
        TypeDescriptor amountTarget = new TypeDescriptor(amountField);

        BigDecimal amount = (BigDecimal) service.convert(
                "1,234.50",
                TypeDescriptor.valueOf(String.class),
                amountTarget);
        System.out.println("FIELD_AMOUNT=" + amount.toPlainString());

        Method method = SearchParameters.class.getMethod(
                "search", LocalDate.class);
        MethodParameter parameter = new MethodParameter(method, 0);
        TypeDescriptor parameterTarget = new TypeDescriptor(parameter);

        LocalDate queryDate = (LocalDate) service.convert(
                "2024-03-01",
                TypeDescriptor.valueOf(String.class),
                parameterTarget);
        System.out.println("PARAMETER_DATE=" + queryDate);

        boolean supported = service.canConvert(
                TypeDescriptor.valueOf(String.class), dateTarget);
        System.out.println("ANNOTATED_PAIR_SUPPORTED=" + supported);
    }
}
~~~

Trong thư mục chứa pom.xml, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả dự kiến:

~~~text
FIELD_DATE=2024-02-29
FIELD_AMOUNT=1234.50
PARAMETER_DATE=2024-03-01
ANNOTATED_PAIR_SUPPORTED=true
~~~

**Điểm đáng chú ý:**
- dateTarget được tạo từ field có @DateTimeFormat(pattern = "dd/MM/yyyy"), vì vậy chuỗi ngày dùng định dạng đó.
- amountTarget mang @NumberFormat(pattern = "#,##0.00"); format/parse phụ thuộc Locale. Demo đặt Locale.US để kết quả số ổn định.
- parameterTarget được tạo từ MethodParameter có @DateTimeFormat(iso = ISO.DATE), nên dùng ISO date format.
- canConvert với TypeDescriptor có thể chọn đường chuyển đổi theo metadata annotation, nhưng vẫn không xác nhận chuỗi cụ thể là ngày hợp lệ. convert thực tế vẫn có thể ném conversion exception nếu chuỗi sai.

## 7. Dùng annotation với Spring MVC

Trong Spring MVC, @DateTimeFormat và @NumberFormat thường được áp dụng trực tiếp trên field hoặc parameter model:

~~~java
public final class ReportFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal minimumAmount;

    // Getter/setter...
}
~~~

Controller nhận model attribute:

~~~java
@GetMapping("/reports")
public String reports(
        @Valid @ModelAttribute("filter") ReportFilter filter,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "report-filter";
    }
    return "reports";
}
~~~

Đây là đoạn tích hợp trong ứng dụng MVC có DTO, view, import và validation provider; không phải chương trình độc lập. Spring MVC đăng ký formatter mặc định và hỗ trợ annotation format trên field/parameter. Nếu dùng cấu hình MVC tùy chỉnh, bảo đảm formatter/conversion service tương ứng vẫn được đăng ký.

Có thể thêm formatter hoặc converter dùng chung qua WebMvcConfigurer:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // registry.addFormatter(...);
        // registry.addFormatterForFieldAnnotation(...);
        // registry.addConverter(...);
    }
}
~~~

Đoạn trên là điểm mở rộng; bổ sung bean, formatter và import theo ứng dụng thực tế. Không tạo FormattingConversionService độc lập rồi giả định Spring MVC tự dùng service đó nếu chưa đăng ký vào MVC configuration.

**Phạm vi JSON:** @RequestBody JSON thường đi qua Jackson/HttpMessageConverter. @DateTimeFormat là annotation formatting cho conversion/formatting của Spring; nó không thay cho @JsonFormat hoặc @JsonProperty trong việc định dạng/đọc JSON bằng Jackson. Nếu endpoint hỗ trợ cả query/form và JSON, hãy kiểm thử từng nhánh riêng.

## 8. Giới hạn và cách chẩn đoán

### 8.1. Annotation không có trong descriptor

Nếu dùng:

~~~java
TypeDescriptor target = TypeDescriptor.valueOf(LocalDate.class);
~~~

descriptor chỉ biết target là LocalDate, không mang @DateTimeFormat của field cụ thể. Muốn annotation-driven formatting, tạo descriptor từ Field hoặc MethodParameter.

### 8.2. Descriptor nguồn và đích đều quan trọng

Annotation thường nằm ở descriptor của target field/parameter khi parse đầu vào. Với converter tùy chỉnh, metadata source cũng có thể tham gia điều kiện. Xác định chính xác annotation được khai báo ở đâu và descriptor nào được dùng lúc convert.

### 8.3. canConvert không bảo đảm giá trị parse thành công

canConvert(String.class, LocalDate.class) có thể phản ánh converter chung của cặp kiểu; nếu dùng overload TypeDescriptor, annotation có thể ảnh hưởng lựa chọn converter. Dù vậy, convert("31/02/2024", ...) vẫn có thể thất bại. Một ngày đúng cú pháp cũng có thể không hợp lệ theo quy tắc miền.

### 8.4. Locale và timezone

@NumberFormat có thể phụ thuộc Locale; @DateTimeFormat(style=...) cũng phụ thuộc Locale/style runtime. Với java.util.Date, timezone ảnh hưởng biểu diễn. Đừng dùng LocalDate cho dữ liệu cần thời điểm toàn cầu; đừng dùng Date khi chỉ cần ngày lịch. Quy định rõ kiểu dữ liệu và format ở biên API.

### 8.5. Pattern sai hoặc không tương thích

Các pattern date/time dùng quy tắc format của Spring/JDK. Không nhầm MM (tháng) với mm (phút), hoặc yyyy với ký hiệu year khác trong DateTimeFormatter. Kiểm thử năm nhuận, ngày không tồn tại, timezone, giá trị rỗng và format không hợp lệ.

### 8.6. Annotation formatter không phải validator

@DateTimeFormat(pattern = "dd/MM/yyyy") giúp parse/print theo mẫu, không xác nhận ngày nằm trong khoảng nghiệp vụ. @NumberFormat không tự đặt min/max. Dùng Bean Validation hoặc validator nghiệp vụ riêng.

## 9. Lỗi phổ biến

1. **Dùng TypeDescriptor.valueOf(...) rồi mong annotation field được áp dụng.** Descriptor đó không mang metadata field; tạo từ Field hoặc MethodParameter.
2. **Coi annotation là converter.** Annotation khai báo metadata; FormattingConversionService và formatter factory mới đọc nó.
3. **Dùng @DateTimeFormat để điều khiển Jackson JSON.** JSON thường do HttpMessageConverter/Jackson xử lý; cấu hình JSON mapping riêng.
4. **Bật style format rồi kỳ vọng giống nhau ở mọi Locale/JDK.** Style dựa runtime/Locale; dùng ISO hoặc pattern cố định cho hợp đồng ổn định.
5. **Dùng pattern ngày không chặt hoặc nhầm ký hiệu.** Kiểm tra MM/mm, ngày nhuận và format sai.
6. **Không quy định Locale cho số.** Chuỗi có dấu phẩy/chấm có thể mang nghĩa khác theo Locale.
7. **Đặt annotation formatter factory trên kiểu không hỗ trợ.** getFieldTypes() phải khai báo kiểu tương ứng; factory trả parser/printer tương thích.
8. **Cho rằng canConvert bảo đảm giá trị hợp lệ.** Giá trị thực tế vẫn phải parse; xử lý ConversionException.
9. **Dùng formatter để kiểm tra nghiệp vụ.** Conversion và validation cần tách biệt.
10. **Đăng ký formatter nhưng MVC không dùng service đó.** Kiểm tra đúng FormatterRegistry/WebMvcConfigurer của ứng dụng.

## 10. Checklist kiểm thử

| Ca thử | Mong đợi |
| --- | --- |
| Field LocalDate có ISO.DATE, input 2024-02-29 | Parse thành công |
| Field LocalDate có pattern dd/MM/yyyy, input 29/02/2024 | Parse thành công |
| Cùng field pattern, input 31/02/2024 | Conversion failure |
| Method parameter có @DateTimeFormat ISO.DATE | Dùng ISO date format |
| Field BigDecimal có @NumberFormat | Parse theo pattern và Locale cấu hình |
| TypeDescriptor chỉ tạo từ LocalDate.class | Không có annotation field cụ thể |
| Annotation formatter custom được đăng ký | Factory được xét khi descriptor mang annotation |
| Giá trị parse thành công nhưng vi phạm @Min/logic ngày | Conversion thành công, validation thất bại |
| @RequestBody JSON | Xác minh riêng cơ chế Jackson |
| Query/form @ModelAttribute | Xác minh Spring WebDataBinder và BindingResult |

## 11. Tài liệu chính thức

- [Spring Field Formatting – Annotation-driven Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Formatter, TypeDescriptor và AnnotationFormatterFactory.
- [AnnotationFormatterFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html): hợp đồng getFieldTypes/getParser/getPrinter.
- [@DateTimeFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html): target field/parameter, ISO/pattern/style/fallback và lưu ý timezone.
- [@NumberFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html): định dạng Number theo style hoặc pattern.
- [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): metadata field/parameter/generic.
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): formatter mặc định và đăng ký formatter qua WebMvcConfigurer.

**Nguyên tắc cần nhớ:** annotation trên field hoặc method parameter chỉ tham gia conversion khi metadata của nó được đưa vào TypeDescriptor và formatting service có factory/formatter tương ứng được sử dụng. Lấy descriptor đúng ngữ cảnh, quy định Locale/format rõ ràng, thực hiện conversion thực tế, rồi kiểm tra validation riêng.