# ParseException, IllegalArgumentException và kết quả lỗi binding trong Spring Formatter

Khi một form gửi chuỗi để gán vào property có kiểu Java cụ thể, **Formatter** phải phân tích chuỗi đó thành giá trị đích. Nếu chuỗi sai định dạng, formatter cần báo lỗi rõ ràng. Hợp đồng **Parser<T>.parse(String, Locale)** cho phép hai cách chính: ném **java.text.ParseException** hoặc **IllegalArgumentException**. Khi formatter được sử dụng qua Spring ConversionService và DataBinder, lỗi phân tích được chuyển qua tầng chuyển kiểu rồi thường xuất hiện trong **BindingResult** dưới dạng **FieldError** với mã **typeMismatch**.

Cần tách ba lớp khái niệm:

1. **Lỗi phân tích ở Formatter:** parser không thể tạo giá trị đích từ chuỗi.
2. **Lỗi chuyển đổi ở Spring:** ConversionService nhận lỗi từ formatter và biểu diễn thành exception của cơ chế conversion.
3. **Lỗi binding ở DataBinder:** binder ghi lỗi vào BindingResult để controller hoặc view xử lý.

Một ParseException không tự động đồng nghĩa với HTTP 400, còn IllegalArgumentException cũng không có nghĩa request đã thoát khỏi BindingResult. Ý nghĩa chính xác phụ thuộc đường xử lý: gọi Formatter trực tiếp, gọi ConversionService, bind bằng DataBinder hay xử lý method argument trong Spring MVC.

## 1. Hợp đồng Formatter và Parser

Spring định nghĩa Formatter<T> kết hợp hai chức năng: **Printer<T>** để định dạng object thành chuỗi và **Parser<T>** để phân tích chuỗi thành object.

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException, IllegalArgumentException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Đây là bản rút gọn thể hiện hợp đồng; trong API thực tế các interface nằm trong package **org.springframework.format**.

- **print(...)** dùng khi ứng dụng cần hiển thị giá trị object theo locale.
- **parse(...)** dùng khi ứng dụng nhận chuỗi và cần tạo giá trị kiểu T.
- **Locale** cho phép xử lý ngày, số, tiền tệ theo ngôn ngữ/vùng. Với mã kỹ thuật có định dạng cố định, locale có thể không ảnh hưởng.
- Khi parse thất bại, contract cho phép ném **ParseException** (thường khi dùng API parse của java.text) hoặc **IllegalArgumentException** (khi giá trị không thể được chấp nhận theo quy tắc parser).

Ví dụ giá trị ngày:

~~~text
Input: 2026-11-02
Output: LocalDate(2026-11-02)
~~~

Nếu input là **02/31/2026** trong khi formatter chỉ chấp nhận ISO yyyy-MM-dd, parser không thể tạo LocalDate đúng. Đây là lỗi dữ liệu ở thời điểm parse, không phải lỗi setter của bean hay lỗi database.

### ParseException là checked exception

**java.text.ParseException** kế thừa **Exception**, vì vậy là checked exception. Một phương thức khai báo ném nó phải xử lý bằng try/catch hoặc tiếp tục khai báo throws. API Parser.parse(...) đã cho phép ném ParseException nên implementation Formatter có thể khai báo:

~~~java
@Override
public LocalDate parse(String text, Locale locale) throws ParseException {
    // parse input hoặc ném ParseException nếu không đúng format
}
~~~

Đây là đoạn minh họa chữ ký, không phải một implementation đầy đủ.

### IllegalArgumentException là unchecked exception

**IllegalArgumentException** kế thừa **RuntimeException**. Parser có thể ném trực tiếp khi input không phù hợp:

~~~java
if (text == null || text.isBlank()) {
    throw new IllegalArgumentException("Date is required");
}
~~~

Lời gọi không cần khai báo throws. Tuy nhiên, cần dùng exception đúng chỗ: input không hợp lệ là một tình huống có thể dự đoán, vì vậy message nên nói rõ định dạng hoặc điều kiện mong đợi. Không dùng một IllegalArgumentException chung chung để che lỗi lập trình không liên quan đến dữ liệu.

## 2. Chọn ParseException hay IllegalArgumentException?

Cả hai đều hợp lệ theo Parser contract; lựa chọn thường phụ thuộc thư viện parsing mà formatter dùng và cách muốn biểu diễn nguyên nhân.

| Tình huống | Kiểu lỗi phù hợp | Vì sao |
| --- | --- | --- |
| Dùng API java.text như DateFormat.parse(...) và parse thất bại | **ParseException** | API nguồn đã định nghĩa checked parse failure |
| Dùng DateTimeFormatter/LocalDate.parse(...) và nhận DateTimeParseException | Có thể để exception runtime truyền ra hoặc bọc thành **IllegalArgumentException** theo parser contract | Java Time dùng exception runtime cho lỗi parse |
| Giá trị rỗng/blank không được chấp nhận theo quy tắc formatter | **IllegalArgumentException** thường dễ hiểu | Đây là vi phạm điều kiện đầu vào do formatter xác định |
| Input chứa ký tự không hợp lệ hoặc không đúng cú pháp | **ParseException** hoặc **IllegalArgumentException** | Tùy API parse và quy ước của implementation |
| Lỗi cấu hình formatter, ví dụ pattern sai ngay khi khởi tạo | Không nên biến thành lỗi binding của người dùng | Đây là lỗi cấu hình/startup, cần phát hiện sớm |

Không có quy tắc rằng ParseException luôn “tốt hơn” hoặc IllegalArgumentException luôn “xấu hơn”. Điều quan trọng là implementation tuân thủ contract, giữ nguyên cause để chẩn đoán và không đánh đồng lỗi dữ liệu với lỗi cấu hình.

### Ví dụ khi dùng Java Time

**DateTimeFormatter** là immutable và thread-safe. Phương thức LocalDate.parse(...) có thể ném **DateTimeParseException**. Có thể bọc nó thành ParseException để giữ phong cách checked exception:

~~~java
try {
    return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
}
catch (DateTimeParseException ex) {
    ParseException failure = new ParseException(
            "Expected ISO date yyyy-MM-dd", Math.max(ex.getErrorIndex(), 0));
    failure.initCause(ex);
    throw failure;
}
~~~

Cũng có thể sử dụng IllegalArgumentException:

~~~java
try {
    return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
}
catch (DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "Expected ISO date yyyy-MM-dd", ex);
}
~~~

Hai đoạn trên minh họa hai cách biểu diễn cùng một parse failure. Không ném cả hai trong cùng một luồng; chọn một quy ước cho formatter để người gọi dễ xử lý và test.

## 3. Spring chuyển lỗi parse thành lỗi conversion như thế nào?

Trong ứng dụng, Formatter thường được đăng ký với **FormattingConversionService**. Spring có adapter để dùng Parser/Printer qua **ConversionService**. Khi gọi conversion:

~~~text
Chuỗi đầu vào
     |
     v
ConversionService chọn Formatter/Parser phù hợp
     |
     v
Formatter.parse(text, locale)
     |
     +-- Thành công --> object kiểu T
     |
     +-- ParseException hoặc IllegalArgumentException
                     |
                     v
           lỗi conversion được truyền ra
           dưới dạng exception của Spring
~~~

Trong các luồng chuyển đổi thông thường, Spring biểu diễn lỗi converter/parser qua hệ exception conversion, thường là **ConversionFailedException** với cause gốc. Parser adapter chuyển checked ParseException thành lỗi runtime để đi qua ConversionService; IllegalArgumentException cũng được truyền trong chuỗi cause hoặc được bọc theo ngữ cảnh conversion.

Điều cần ghi nhớ:

- **ParseException** là exception ở ranh giới parser.
- **ConversionFailedException** là lỗi của phép chuyển đổi trong ConversionService.
- **TypeMismatchException** có thể xuất hiện khi DataBinder dùng type converter và không thể gán giá trị sang property đích.
- Các tầng có thể lồng exception; khi log/debug, xem cả root cause thay vì chỉ nhìn tên exception ngoài cùng.

Không nên viết code phụ thuộc vào một độ sâu cause cố định nếu ứng dụng cho phép thay đổi conversion service/formatter. Dùng exception type và API lỗi của tầng mà code hiện tại đang xử lý.

## 4. DataBinder ghi lỗi như thế nào?

**DataBinder** áp dụng property values vào target object. Nếu chuỗi không thể chuyển sang kiểu property đích, binder không xem đó là một object hợp lệ rồi gọi service; nó ghi lỗi vào **BindingResult**. Theo mã lỗi mặc định thường gặp:

| Mã lỗi binding | Ý nghĩa |
| --- | --- |
| **required** | Thiếu trường bắt buộc theo required fields configuration |
| **typeMismatch** | Giá trị không chuyển được sang kiểu property đích |
| **methodInvocation** | Lỗi khi gọi setter/property access |

Khi Formatter ném ParseException hoặc IllegalArgumentException trong quá trình chuyển chuỗi sang kiểu đích, binder thường ghi **typeMismatch** cho field tương ứng. Controller có thể quan sát:

~~~java
BindingResult result = binder.getBindingResult();
FieldError error = result.getFieldError("startDate");

if (error != null) {
    String code = error.getCode();
    Object rejected = error.getRejectedValue();
    boolean bindingFailure = error.isBindingFailure();
}
~~~

Đây là đoạn minh họa với **org.springframework.validation.BindingResult** và **FieldError**. Những trường quan trọng:

- **getCode()**: mã lỗi chính, thường là typeMismatch.
- **getCodes()**: chuỗi mã để MessageCodesResolver tra thông báo theo object/field/type.
- **getRejectedValue()**: giá trị input bị từ chối, nếu được lưu.
- **isBindingFailure()**: phân biệt lỗi conversion/binding với lỗi validation thông thường ở field.
- **getField()**: tên property bị lỗi.

**BindingResult không chỉ chứa parse failure.** Nó có thể chứa type mismatch, required, property access và cả các lỗi validation được thêm sau đó. Đừng kết luận mọi FieldError đều sinh ra từ Formatter.

### Target property sau lỗi có giá trị gì?

Nếu field target ban đầu đã có giá trị, khi conversion thất bại Spring thường không gán giá trị mới vào field đó. Giá trị cũ có thể vẫn còn trên object. UI có thể hiển thị rejected value thông qua BindingResult và giữ lại input người dùng đã nhập.

Ví dụ:

~~~text
Trước bind: startDate = 2026-11-01
Request:    startDate = 2026-02-30
Sau bind:   startDate có thể vẫn là 2026-11-01
BindingResult: FieldError(startDate, code=typeMismatch,
                          rejectedValue="2026-02-30")
~~~

Đây là hành vi quan trọng: **object target không phản ánh toàn bộ nội dung người dùng đã gửi nếu một field bind thất bại**. Luôn kiểm tra BindingResult trước khi chuyển target sang service hoặc lưu database. Không đọc giá trị cũ rồi tưởng rằng request mới đã được chấp nhận.

## 5. Ví dụ hoàn chỉnh Java 17: hai formatter, hai kiểu lỗi, cùng một mã binding

Chương trình sau dùng **Spring Framework 6.2.10**, Java 17+ và Maven, không cần Spring Boot hoặc HTTP server. Nó đăng ký hai Formatter cho hai kiểu đích khác nhau:

1. **LocalDateFormatter**: dùng Java Time; khi parse thất bại, bọc DateTimeParseException thành checked ParseException.
2. **ReferenceCodeFormatter**: khi input blank hoặc có ký tự không hợp lệ, ném IllegalArgumentException.

Sau đó DataBinder bind giá trị chuỗi vào JavaBean. Một field hợp lệ được gán; hai field sai định dạng tạo FieldError có mã typeMismatch.

Cấu trúc:

~~~text
formatter-binding-errors/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FormatterBindingErrorsDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-binding-errors</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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

**src/main/java/demo/FormatterBindingErrorsDemo.java**:

~~~java
package demo;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Map;

import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class FormatterBindingErrorsDemo {

    public static void main(String[] args) {
        DefaultFormattingConversionService conversions =
                new DefaultFormattingConversionService();

        conversions.addFormatter(new LocalDateFormatter());
        conversions.addFormatter(new ReferenceCodeFormatter());

        BookingForm form = new BookingForm();
        form.setStartDate(LocalDate.of(2026, 11, 1));

        DataBinder binder = new DataBinder(form, "bookingForm");
        binder.setConversionService(conversions);
        binder.setAllowedFields("startDate", "referenceCode", "endDate");

        binder.bind(new MutablePropertyValues(Map.of(
                "startDate", "2026-02-30",
                "referenceCode", "INV @ 17",
                "endDate", "2026-11-15"
        )));

        BindingResult result = binder.getBindingResult();

        printFieldResult("startDate", result, form);
        printFieldResult("referenceCode", result, form);
        printFieldResult("endDate", result, form);

        System.out.println("hasErrors = " + result.hasErrors());
        System.out.println("errorCount = " + result.getErrorCount());
    }

    private static void printFieldResult(
            String field, BindingResult result, BookingForm form) {

        FieldError error = result.getFieldError(field);
        String code = (error == null ? "none" : error.getCode());
        String rejected = (error == null
                ? "none" : String.valueOf(error.getRejectedValue()));

        System.out.println(field + ".code = " + code);
        System.out.println(field + ".rejected = " + rejected);
    }

    public static final class LocalDateFormatter
            implements Formatter<LocalDate> {

        private static final DateTimeFormatter FORMAT =
                DateTimeFormatter.ISO_LOCAL_DATE;

        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {

            try {
                return LocalDate.parse(text, FORMAT);
            }
            catch (DateTimeParseException ex) {
                ParseException failure = new ParseException(
                        "Expected ISO date yyyy-MM-dd",
                        Math.max(ex.getErrorIndex(), 0));
                failure.initCause(ex);
                throw failure;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return FORMAT.format(value);
        }
    }

    public record ReferenceCode(String value) {
    }

    public static final class ReferenceCodeFormatter
            implements Formatter<ReferenceCode> {

        @Override
        public ReferenceCode parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Reference code must not be blank");
            }

            String normalized = text.trim().toUpperCase(Locale.ROOT);
            if (!normalized.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException(
                        "Reference code accepts only A-Z, 0-9 and hyphen");
            }

            return new ReferenceCode(normalized);
        }

        @Override
        public String print(ReferenceCode value, Locale locale) {
            return value.value();
        }
    }

    public static final class BookingForm {
        private LocalDate startDate;
        private ReferenceCode referenceCode;
        private LocalDate endDate;

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }

        public ReferenceCode getReferenceCode() {
            return referenceCode;
        }

        public void setReferenceCode(ReferenceCode referenceCode) {
            this.referenceCode = referenceCode;
        }

        public LocalDate getEndDate() {
            return endDate;
        }

        public void setEndDate(LocalDate endDate) {
            this.endDate = endDate;
        }
    }
}
~~~

Chạy trong thư mục chứa pom.xml bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.FormatterBindingErrorsDemo
~~~

**Các dòng stdout kỳ vọng từ chương trình**:

~~~text
startDate.code = typeMismatch
startDate.rejected = 2026-02-30
referenceCode.code = typeMismatch
referenceCode.rejected = INV @ 17
endDate.code = none
endDate.rejected = none
hasErrors = true
errorCount = 2
~~~

Giải thích:

- **startDate**: chuỗi có hình thức yyyy-MM-dd nhưng ngày 30/02 không tồn tại. LocalDateFormatter nhận DateTimeParseException từ Java Time, chuyển thành ParseException như hợp đồng Parser. Spring conversion adapter tiếp nhận lỗi parse và DataBinder ghi typeMismatch.
- **referenceCode**: giá trị chứa ký tự @ và khoảng trắng nội bộ, không đúng biểu thức cho phép. ReferenceCodeFormatter ném IllegalArgumentException; DataBinder cũng ghi typeMismatch cho field.
- **endDate**: giá trị hợp lệ, formatter tạo LocalDate, setter nhận giá trị và không có FieldError.
- **startDate** trước bind đã có ngày 01/11/2026. Sau lỗi conversion, giá trị cũ có thể vẫn giữ; rejected value được lưu trong FieldError để hiển thị input sai.
- Tổng cộng hai field lỗi nên **hasErrors = true** và **errorCount = 2**.

Kết quả này minh họa rằng **ParseException và IllegalArgumentException có nguồn gốc khác nhau nhưng đều có thể trở thành lỗi typeMismatch của một lần property binding**. Chương trình không cần controller để quan sát điều đó; DataBinder trực tiếp đã đủ.

## 6. Tại sao lỗi parse không phải luôn là typeMismatch?

Cần nhìn đúng tầng đang gọi:

| Cách gọi | Điều có thể quan sát |
| --- | --- |
| Gọi trực tiếp **formatter.parse(...)** | ParseException hoặc IllegalArgumentException từ chính implementation |
| Gọi trực tiếp **conversionService.convert(...)** | Exception của conversion service, thường **ConversionFailedException**, có nguyên nhân parse ở bên trong |
| Gọi **DataBinder.bind(...)** | BindingResult có FieldError, thường mang mã **typeMismatch** |
| Controller **@ModelAttribute** với BindingResult | Controller có thể đọc lỗi field mà không tự ném lỗi method argument |
| Controller không có BindingResult phù hợp | Spring MVC xử lý theo exception/response path tương ứng; không mặc định controller tiếp tục |
| **@RequestBody JSON** sai cú pháp | HttpMessageConverter/Jackson có thể báo **HttpMessageNotReadableException** trước khi Formatter/BindingResult của property binding được gọi |

### Mã lỗi typeMismatch có phải exception type không?

Không. **typeMismatch** là error code được ghi vào FieldError/MessageCodesResolver. Nó là mã để tìm message, không phải tên class exception. Trong chuỗi nguyên nhân có thể có ParseException, IllegalArgumentException, ConversionFailedException hoặc TypeMismatchException tùy API và điểm bắt lỗi.

**FieldError.isBindingFailure()** thường true đối với lỗi do binding/conversion. Điều đó giúp phân biệt với một lỗi validation thông thường được thêm sau bind, ví dụ **@NotBlank** hoặc **@Email**.

### Vì sao không dùng ParseException trực tiếp ở controller?

Controller nhận kết quả của binding, không nên phải biết formatter nội bộ dùng thư viện parse nào. Với property binding, kiểm tra **BindingResult** và hiển thị lỗi theo field là cách rõ ràng hơn. Nếu gọi Formatter hoặc ConversionService thủ công trong service, bên gọi có thể bắt exception phù hợp với API đó.

## 7. Hiển thị thông báo lỗi: giữ error code, không phơi bày stack trace

Trong Spring, BindingResult chứa mã lỗi; **MessageSource** có thể chuyển mã và ngữ cảnh field thành thông điệp người dùng. Ví dụ tệp **messages_vi.properties**:

~~~properties
typeMismatch.bookingForm.startDate=Ngày bắt đầu phải theo định dạng yyyy-MM-dd và là ngày tồn tại.
typeMismatch.bookingForm.referenceCode=Mã tham chiếu chỉ được chứa chữ A-Z, số và dấu gạch nối.
typeMismatch=Giá trị nhập không đúng định dạng.
~~~

Đây là ví dụ key minh họa; mã cụ thể phụ thuộc **MessageCodesResolver**, object name, field name và kiểu property. Spring mặc định tạo các mã có mức độ cụ thể giảm dần, ví dụ:

~~~text
typeMismatch.bookingForm.startDate
typeMismatch.startDate
typeMismatch.java.time.LocalDate
typeMismatch
~~~

Trong controller/view, có thể render thông báo theo locale:

~~~java
String message = messageSource.getMessage(fieldError, locale);
~~~

Đây là đoạn minh họa cần có **MessageSource**, **FieldError**, **Locale** và bean injection phù hợp. Không nên trả cho người dùng nguyên văn stack trace hoặc message kỹ thuật chứa tên class nội bộ.

### Rejected value và bảo vệ dữ liệu

Rejected value hữu ích để hiển thị lại nội dung người dùng đã nhập. Tuy nhiên, không phải mọi giá trị đều an toàn để phản chiếu vào HTML hoặc log:

- Encode output theo ngữ cảnh HTML/JSON để tránh XSS.
- Không ghi log dữ liệu nhạy cảm như token, mật khẩu hoặc thông tin cá nhân không cần thiết.
- Giới hạn kích thước field/input trước khi giữ rejected value hoặc hiển thị lại.
- Không đưa exception message thô của thư viện parse ra API nếu nó tiết lộ cấu trúc nội bộ.

Một message thân thiện thường nêu định dạng mong đợi và field cụ thể, không cần nêu stack trace.

## 8. Tích hợp Formatter trong Spring MVC

Đăng ký formatter dùng chung cho các binder MVC qua **WebMvcConfigurer.addFormatters(...)**:

~~~java
@Configuration
class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new FormatterBinding.LocalDateFormatter());
        registry.addFormatter(new FormatterBinding.ReferenceCodeFormatter());
    }
}
~~~

Đây là ví dụ cấu hình trong một ứng dụng MVC đã có sẵn các formatter; tên class chỉ là minh họa và cần điều chỉnh theo package thực tế. Đăng ký trong registry MVC giúp binder dùng cùng quy tắc khi chuyển request parameter/form string sang kiểu Java.

Handler với **@ModelAttribute** có thể nhận BindingResult ngay sau tham số:

~~~java
@PostMapping("/bookings")
String create(
        @ModelAttribute("bookingForm") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "booking-form";
    }

    bookingService.create(form);
    return "redirect:/bookings/success";
}
~~~

Đây là đoạn controller minh họa; cần import các annotation Spring MVC, BindingResult và service/view tương ứng. **BindingResult phải đứng ngay sau model attribute** mà nó nhận lỗi.

Nếu không có BindingResult/Errors phù hợp, validation error của model attribute thường được chuyển thành exception như **MethodArgumentNotValidException** trong các trường hợp object validation tương ứng; với chữ ký method có constraint trực tiếp hoặc method validation, exception path có thể khác. Hãy kiểm tra đúng loại tham số, annotation và version Spring MVC.

### Khác biệt với @RequestBody

Với **@RequestBody**, JSON được đọc bởi **HttpMessageConverter** (thường Jackson) trước khi xử lý controller. JSON sai cú pháp hoặc không deserialize được có thể thành **HttpMessageNotReadableException**; đó không nhất thiết là lỗi Formatter trong DataBinder.

Nếu muốn format kiểu LocalDate trong JSON, thông thường cấu hình Jackson Java Time module hoặc serializer/deserializer phù hợp. Formatter đăng ký qua MVC ConversionService chủ yếu phục vụ type conversion/formatting của request parameters, path variables và property binding theo đường Spring MVC tương ứng; không suy ra Jackson tự động gọi nó.

## 9. Định nghĩa Formatter an toàn luồng và xác định

Formatter có thể được đăng ký trong ConversionService dùng chung cho nhiều request. Implementation nên **stateless** hoặc sử dụng các thành phần thread-safe.

**DateTimeFormatter** là immutable và thread-safe, phù hợp để giữ static final. Ngược lại, các lớp như **SimpleDateFormat** không thread-safe; nếu phải dùng, tạo instance riêng cho từng lần parse/print hoặc có chiến lược đồng bộ đúng. Không giữ một SimpleDateFormat mutable dùng chung trong field của singleton formatter.

Tránh các lỗi sau:

- Thay đổi locale hoặc pattern dùng chung theo request bằng cách ghi vào field.
- Nuốt ParseException rồi trả ngày mặc định như hôm nay.
- Trả null cho một chuỗi sai định dạng để tránh lỗi binding, khiến dữ liệu bị hiểu nhầm là optional.
- Chuyển mọi exception thành cùng một message không phân biệt field/pattern.
- Dùng formatter để truy vấn database hoặc kiểm tra quyền.
- Bắt IllegalArgumentException quá rộng rồi che cả lỗi lập trình không liên quan tới input.

Một formatter tốt có quy tắc parse rõ ràng, print ổn định, lỗi đủ thông tin và không giữ trạng thái theo request.

## 10. Phân biệt lỗi parse, binding và validation

| Tình huống | Tầng phát hiện | Ví dụ | Kết quả thường gặp |
| --- | --- | --- | --- |
| Chuỗi sai cú pháp | Formatter/Parser | 2026-02-30 | ParseException hoặc IllegalArgumentException |
| Conversion thất bại | ConversionService | Formatter không tạo được LocalDate | ConversionFailedException/cause parse |
| Không gán được property | DataBinder | String không đổi được sang kiểu field | FieldError, thường code typeMismatch |
| Field thiếu theo cấu hình | DataBinder | Required field vắng mặt | FieldError, code required |
| Giá trị đã bind nhưng vi phạm constraint | Bean Validation | Chuỗi trắng với @NotBlank | FieldError có mã constraint |
| Sai quy tắc nghiệp vụ | Service/domain | Ngày đặt nằm ngoài khoảng cho phép | Exception/domain error do ứng dụng định nghĩa |
| JSON không đọc được | HttpMessageConverter/Jackson | Body JSON hỏng | HttpMessageNotReadableException |

Ví dụ chuỗi ngày **2026-11-31** có thể thất bại ở Formatter vì ngày không tồn tại. Chuỗi **2026-11-30** parse thành công nhưng nếu quy tắc nghiệp vụ yêu cầu ngày kết thúc không được sau ngày đóng đăng ký, service vẫn có thể từ chối. Không nên đẩy tất cả những quy tắc này vào Formatter.

## 11. Test strategy để biết exception nào đã xảy ra

Một bộ test nên kiểm tra từng tầng riêng:

1. **Formatter unit test:** gọi parse trực tiếp với input hợp lệ, sai format, blank; xác nhận loại exception và cause.
2. **ConversionService test:** đăng ký formatter, gọi convert; xác nhận conversion exception bao bọc parse failure đúng.
3. **DataBinder test:** bind input lỗi; xác nhận target không nhận giá trị lỗi và FieldError có code typeMismatch.
4. **MVC MockMvc test:** gửi form request lỗi; xác nhận view/response nhận BindingResult và không gọi service ghi dữ liệu.
5. **Message test:** xác nhận code typeMismatch được ánh xạ ra thông báo đúng locale.
6. **Thread-safety test nếu cần:** chạy nhiều lần đồng thời, xác nhận formatter không thay đổi kết quả do dùng chung state.

Ví dụ assertion khái niệm:

~~~java
assertThat(result.getFieldError("startDate")).isNotNull();
assertThat(result.getFieldError("startDate").getCode())
        .isEqualTo("typeMismatch");
assertThat(result.getFieldError("startDate").isBindingFailure())
        .isTrue();
~~~

Đây là đoạn kiểm thử dùng AssertJ/JUnit trong dự án đã có test dependencies. Nó không chứng minh root cause là ParseException; muốn xác minh điều đó, kiểm tra cause chain của lỗi conversion hoặc test formatter trực tiếp.

Không nên test bằng cách so khớp toàn bộ message mặc định của Spring vì message có thể thay đổi theo version/locale/MessageSource. Ưu tiên kiểm tra error code, field, rejected value và hành vi controller.

## 12. Checklist thực hành

Khi gặp câu hỏi **ParseException, IllegalArgumentException và kết quả lỗi binding**, hãy xác định:

- Formatter đang gọi parser nào? API đó trả checked ParseException hay runtime exception?
- Formatter có giữ cause khi chuyển loại exception không?
- Lỗi đang xảy ra ở lời gọi parse trực tiếp, ConversionService hay DataBinder?
- Nếu qua DataBinder, FieldError nào được tạo? Mã typeMismatch hay mã khác?
- Controller có BindingResult đúng vị trí để tự xử lý hay Spring chuyển sang exception path?
- Target object có thể còn giá trị cũ sau khi field bind thất bại không?
- MessageSource đã chuyển mã lỗi thành thông báo an toàn theo locale chưa?
- Formatter có thread-safe và không nuốt dữ liệu lỗi không?
- Đường dữ liệu là form/@ModelAttribute hay JSON/@RequestBody?

**Ghi nhớ:** Parser exception giải thích tại sao một chuỗi không phân tích được; ConversionService đưa lỗi vào mô hình chuyển đổi của Spring; DataBinder biến lỗi đó thành thông tin binding có thể hiển thị và kiểm tra. Giữ đúng ranh giới ba tầng giúp xử lý lỗi nhất quán, không nhầm parse failure với validation hoặc nghiệp vụ.

## Tài liệu chính thức

- [Spring Framework — Formatter SPI và parse/print](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework 6.2 API — Parser<T>](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework 6.2 API — Formatter<T>](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.2 API — ConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 API — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/BindingResult.html)
