# Đăng ký editor hoặc formatter cục bộ với DataBinder trong Spring Framework

## 1. Vì sao cần đăng ký bộ chuyển đổi cục bộ?

Khi dữ liệu đi từ một biểu mẫu hoặc request parameter vào đối tượng Java, `DataBinder` phải biết cách biến biểu diễn bên ngoài thành kiểu thuộc tính. Một trường `LocalDate` có thể nhận chuỗi `31/12/2026` ở form đặt lịch A, trong khi form B nhận `2026-12-31`. Nếu áp dụng cùng một quy tắc chuyển đổi cho toàn bộ ứng dụng, thay đổi phục vụ form A có thể vô tình làm hỏng form B.

**Đăng ký cục bộ** nghĩa là gắn quy tắc chuyển đổi với **một DataBinder cụ thể**, và nếu cần chỉ với **một đường dẫn thuộc tính cụ thể**. Đây là công cụ thích hợp khi đầu vào đặc thù cho một form, một model attribute hoặc một controller, trong khi phần còn lại của ứng dụng phải giữ quy tắc chung.

Ví dụ: `travelDate=31/12/2026` cần thành `LocalDate.of(2026, 12, 31)`. Spring có thể sử dụng:

- **`PropertyEditor`** (cơ chế JavaBeans): bạn đăng ký một đối tượng editor và định nghĩa cách đọc chuỗi, ví dụ `setAsText(...)`.
- **`Formatter<T>`** (Spring Formatting): bạn định nghĩa `parse(String, Locale)` và `print(T, Locale)` cho một kiểu cụ thể. API `DataBinder.addCustomFormatter(...)` có thể đăng ký trực tiếp một formatter tại binder.

Cả hai cách phục vụ **type conversion/formatting**. Chúng không tự quyết định dữ liệu có hợp lệ về mặt nghiệp vụ, không tự gọi `Validator` và không cấp quyền sửa trường nhạy cảm.

## 2. Vị trí của editor và formatter trong luồng binding

~~~text
HTTP form/query parameters hoặc PropertyValues
                 |
                 v
     WebDataBinder / DataBinder
                 |
        tìm thuộc tính đích
                 |
        cần chuyển kiểu?
          /             \
         v               v
  PropertyEditor    Formatter / ConversionService
       \                  /
        v                v
          đối tượng Java
                 |
          BindingResult
       (lỗi chuyển kiểu nếu có)
                 |
     validation nếu được kích hoạt
                 |
      xử lý lỗi hoặc tiếp tục
~~~

Với cách dùng `DataBinder` thủ công:

1. Tạo đối tượng đích và `new DataBinder(target, "objectName")`.
2. **Đăng ký editor/formatter trước khi bind**.
3. Nếu cần, cấu hình `setAllowedFields(...)`, `setConversionService(...)`, `setValidator(...)`.
4. Gọi `binder.bind(propertyValues)` để cập nhật thuộc tính và ghi lỗi chuyển kiểu.
5. Gọi `binder.validate()` **chỉ khi** cần chạy các Spring `Validator` đã đăng ký.
6. Đọc `binder.getBindingResult()` để kiểm tra lỗi.

Trong Spring MVC, `WebDataBinder` mở rộng cơ chế trên và thường được tạo để xử lý các model attribute. Phương thức `@InitBinder` cho phép cấu hình binder **trước lúc Spring thực hiện binding**. Cả `registerCustomEditor(...)` lẫn `addCustomFormatter(...)` đều là cấu hình của binder; không cần tự gọi `bind()` bên trong `@InitBinder`.

Điểm dễ nhầm: `@RequestBody` JSON chủ yếu được deserialize qua `HttpMessageConverter` (thường Jackson). Editor đăng ký cho `WebDataBinder` **không phải** bộ chuyển đổi JSON mà Jackson sử dụng khi đọc body. Cần xác định dữ liệu đầu vào đi qua cơ chế nào trước khi chọn cách tùy biến.

## 3. Đăng ký PropertyEditor cho kiểu hoặc một trường

### 3.1. PropertyEditor là gì?

`java.beans.PropertyEditor` là hợp đồng JavaBeans cho chuyển một giá trị được biểu diễn dưới dạng text thành đối tượng và ngược lại. Trong thực tế, Spring thường dùng `java.beans.PropertyEditorSupport` làm lớp nền để triển khai editor của riêng bạn.

Các phương thức quan trọng:

- `setAsText(String text)`: được gọi để đổi chuỗi đầu vào thành giá trị đích; bên trong thường gọi `setValue(convertedValue)`.
- `getAsText()`: trả về chuỗi biểu diễn giá trị mà editor đang giữ, hữu ích khi form hiển thị lại.
- `getValue()`, `setValue(...)`: giữ giá trị hiện tại của một **instance editor**.

Ví dụ editor đổi một chuỗi ngày `dd/MM/uuuu` sang `LocalDate` với bộ phân tích nghiêm ngặt:

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class DayMonthYearEditor extends PropertyEditorSupport {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public void setAsText(String text) {
        setValue(LocalDate.parse(text, FORMAT));
    }

    @Override
    public String getAsText() {
        LocalDate date = (LocalDate) getValue();
        return date == null ? "" : FORMAT.format(date);
    }
}
~~~

Đây là một lớp Java độc lập (cần tệp `DayMonthYearEditor.java`) dùng Java 17+; không phụ thuộc Spring trong bản thân mã editor. Khi gặp `31/02/2027`, `LocalDate.parse(...)` báo sai ngày thực tế. Trong một lần `DataBinder.bind(...)` thông thường, Spring chuyển thất bại của editor thành lỗi binding tại trường tương ứng để đọc bằng `BindingResult`.

**Không dùng `DateTimeFormatter.ofPattern("dd/MM/yyyy").withResolverStyle(STRICT)` một cách thiếu hiểu biết về “year-of-era”**: với strict parsing, `uuuu` là proleptic year, rõ ràng hơn trong ví dụ này. `DateTimeFormatter` bất biến và có thể dùng chung an toàn; đối với `SimpleDateFormat` thì phải thận trọng vì mutable và không thread-safe.

### 3.2. Các overload của registerCustomEditor

~~~java
// Áp dụng cho các thuộc tính có kiểu LocalDate phù hợp trong binder này:
binder.registerCustomEditor(
        LocalDate.class, new DayMonthYearEditor());

// Chỉ áp dụng cho đường dẫn "travelDate" của binder này:
binder.registerCustomEditor(
        LocalDate.class, "travelDate", new DayMonthYearEditor());
~~~

Hai đoạn trên là **mã minh họa**, trong đó `binder` là một `DataBinder` hoặc `WebDataBinder` đã được tạo trước; mã chạy hoàn chỉnh ở mục 6.

| Đăng ký | Tác dụng | Khi sử dụng |
| --- | --- | --- |
| `registerCustomEditor(LocalDate.class, editor)` | Editor theo kiểu trong **binder hiện tại**, dùng cho những field phù hợp | Tất cả trường ngày của form đó tuân cùng mẫu |
| `registerCustomEditor(LocalDate.class, "travelDate", editor)` | Editor chỉ cho đường dẫn `travelDate` của **binder hiện tại** | Một field có định dạng nhập riêng |
| `registerCustomEditor(String.class, "externalCode", editor)` | Tùy chỉnh xử lý text cho field có tên tương ứng | Quy tắc text đặc thù, không làm thay đổi mọi `String` |

Đường dẫn thuộc tính phải khớp **tên thuộc tính Java**, không phải nhãn hiển thị trên giao diện. Với đối tượng lồng nhau, có thể là `customer.birthDate`; với collection, đường dẫn có thể có chỉ số như `items[0].deliveryDate` tùy cấu trúc và cấu hình binder. Tên `travelDate` không tự áp dụng cho một trường khác chỉ vì cùng kiểu.

Nếu dùng editor theo kiểu `LocalDate.class` mà form có cả `travelDate` và `cancelDate`, cả hai có thể dùng cùng quy tắc. Nếu chỉ một trường nhận dạng `dd/MM/uuuu`, hãy chọn biến thể **có property path**.

### 3.3. Vòng đời và an toàn luồng

`PropertyEditorSupport` lưu trạng thái thông qua `setValue(...)`. Không nên chia sẻ **cùng một instance editor mutable** cho nhiều request hoặc nhiều thread. Trong `@InitBinder`, hãy tạo editor mới khi thiết lập binder cho request tương ứng:

~~~java
@InitBinder("travelForm")
void initialize(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, "travelDate", new DayMonthYearEditor());
}
~~~

Đây là đoạn trong một Spring MVC controller, không phải ứng dụng chạy độc lập. Spring tạo binder cho ngữ cảnh binding; phương thức tạo editor mới phù hợp với vòng đời đó. **Không khai báo một editor mutable làm singleton và dùng trực tiếp cho mọi request**.

Khi nhiều controller cần cùng logic, có thể gói mã đăng ký vào một `PropertyEditorRegistrar` và gọi `registrar.registerCustomEditors(binder)` trong các `@InitBinder` thích hợp. Registrar nên tạo editor mới cho từng lần đăng ký; code tái sử dụng nằm ở *cách đăng ký*, không nằm ở một editor mutable được chia sẻ.

## 4. Đăng ký Formatter<T> cục bộ

### 4.1. Formatter phân tách parse và print

`org.springframework.format.Formatter<T>` là giao diện kết hợp `Parser<T>` và `Printer<T>`:

~~~java
public interface Formatter<T> {
    String print(T object, Locale locale);
    T parse(String text, Locale locale) throws ParseException;
}
~~~

Đây là **mô tả khái niệm rút gọn** của hai phương thức mà một lớp `Formatter<T>` cần triển khai; trong API Spring, `Formatter<T>` kế thừa `Printer<T>` và `Parser<T>`.

- `parse(...)`: chuyển chuỗi từ người dùng thành kiểu `T`.
- `print(...)`: chuyển giá trị `T` thành chuỗi hiển thị.
- `Locale`: cho phép định dạng ngày, tiền tệ hoặc số tùy khu vực. Lựa chọn locale của request và quy tắc định dạng nên được xác định rõ để tránh lỗi ngày/tháng bị đảo.

Ví dụ formatter cho `LocalDate`, dùng mẫu `dd.MM.uuuu`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class DotDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter format(Locale locale) {
        return DateTimeFormatter.ofPattern("dd.MM.uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, format(locale));
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return format(locale).format(value);
    }
}
~~~

Hai phương thức có kiểu rõ ràng nên dễ tái sử dụng và kiểm thử. `DotDateFormatter` không giữ giá trị hiện tại hay các biến theo request, vì vậy thiết kế này có thể dùng lại an toàn; dữ liệu locale được truyền vào từng lần gọi. Trong project thật, cân nhắc định dạng được áp dụng cho cả chiều đọc và chiều in, các trường trống và quy tắc validation.

### 4.2. addCustomFormatter và phạm vi áp dụng

~~~java
// Một định dạng cho tất cả thuộc tính LocalDate tương ứng trong binder:
binder.addCustomFormatter(new DotDateFormatter());

// Giới hạn formatter cho một hoặc vài đường dẫn thuộc tính:
binder.addCustomFormatter(
        new DotDateFormatter(), "travelDate");

binder.addCustomFormatter(
        new DotDateFormatter(), "travelDate", "returnDate");
~~~

`DataBinder.addCustomFormatter(...)` nhận formatter cụ thể, tìm kiểu đích từ `Formatter<T>` và dùng bộ chuyển tiếp sang `PropertyEditor` ở dưới để đăng ký vào registry của binder. Điều này giúp **dùng Formatter cục bộ mà không nhất thiết phải thêm formatter vào registry toàn cục**. `Formatter` có overload theo các **kiểu field** cũng như overload theo **tên field**; khi muốn giới hạn chính xác một thuộc tính, dùng overload nhận `String... fields`.

Lưu ý khi dùng generic type: `class DotDateFormatter implements Formatter<LocalDate>` cho phép Spring nhận biết kiểu `LocalDate`. Một formatter generic/ẩn kiểu quá phức tạp có thể cần overload chỉ định `Class<?>... fieldTypes`.

### 4.3. Khi nào ưu tiên formatter?

| Tiêu chí | PropertyEditor | Formatter |
| --- | --- | --- |
| API | JavaBeans `PropertyEditor`, thường kế thừa `PropertyEditorSupport` | Spring `Formatter<T>` |
| Kiểu | Nhận/giữ `Object`, thường cần cast | Generic `T` xác định kiểu rõ ràng |
| Chiều chuyển đổi | `setAsText/getAsText` cùng trạng thái instance | `parse/print` |
| Locale | Tự xử lý nếu cần | `Locale` là tham số có sẵn |
| Trạng thái | `PropertyEditorSupport` mutable | Dễ viết stateless và thread-safe |
| Dùng cục bộ | `registerCustomEditor` | `addCustomFormatter` |
| Dùng chung | Có thể qua registrar theo binder; chú ý vòng đời editor | Có thể đăng ký vào `FormattingConversionService` chung |

Với ứng dụng Spring hiện đại, **Formatter** thường thuận tiện hơn cho dữ liệu hướng người dùng cần parse/print, đặc biệt số, ngày, tiền tệ và locale. **PropertyEditor** vẫn hữu ích cho tích hợp API JavaBeans, editor sẵn có hoặc chuyển đổi đặc thù mà code hiện hành đang sử dụng. **Converter<S,T>** phù hợp hơn khi chủ yếu cần chuyển kiểu một chiều và không phụ thuộc locale.

## 5. Cục bộ theo binder, theo field, theo controller: ba tầng khác nhau

“Cục bộ” có nhiều lớp phạm vi. Phân biệt chính xác giúp tránh ảnh hưởng ngoài ý muốn:

| Cách cấu hình | Phạm vi thông thường |
| --- | --- |
| `new DataBinder(target)` rồi `registerCustomEditor/addCustomFormatter` | Chỉ instance `DataBinder` đó |
| Overload có `"travelDate"` | Chỉ trường/đường dẫn đó **trong binder** |
| `@InitBinder` trong một `@Controller` | Binder được khởi tạo cho việc binding của controller đó |
| `@InitBinder("travelForm")` trong controller | Hẹp thêm theo tên model attribute `travelForm` |
| `@InitBinder` trong `@ControllerAdvice` | Có thể áp dụng cho nhiều controller theo phạm vi advice |
| `WebMvcConfigurer.addFormatters(FormatterRegistry)` | Đăng ký dùng chung cho chuyển đổi/format trong Spring MVC |

Hai trục “**binder thuộc ngữ cảnh nào**” và “**field nào trong binder được tùy chỉnh**” là độc lập. Ví dụ `@InitBinder("travelForm")` có `addCustomFormatter(formatter, "travelDate")` nghĩa là quy tắc được cấu hình cho binder của model attribute `travelForm` và chỉ cho field `travelDate` của đối tượng đó.

Mã controller minh họa:

~~~java
// Đoạn trích; giả định TravelForm, DotDateFormatter và service đã có.
@Controller
@RequestMapping("/travel")
class TravelController {

    @InitBinder("travelForm")
    void bindTravelForm(WebDataBinder binder) {
        binder.setAllowedFields("travelerName", "travelDate");
        binder.addCustomFormatter(new DotDateFormatter(), "travelDate");
    }

    @PostMapping("/booking")
    String submit(
            @Valid @ModelAttribute("travelForm") TravelForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "booking-form";
        }

        travelService.book(form);
        return "redirect:/travel/success";
    }
}
~~~

Đoạn trên chỉ minh họa cách viết **bên trong controller**; để biên dịch cần imports, `TravelForm`, `travelService`, view template và cấu hình MVC. `BindingResult` phải **ngay sau** model attribute mà nó đại diện. `setAllowedFields` là một chính sách khác để hạn chế thuộc tính được phép property-bind; editor/formatter **không** làm thay nhiệm vụ whitelist hoặc kiểm tra quyền.

Nếu cùng ứng dụng có nhiều form đòi định dạng khác nhau cho `LocalDate`, đăng ký ở `@InitBinder` của từng controller hoặc theo model attribute thường hợp lý hơn thay đổi `WebMvcConfigurer.addFormatters(...)` toàn cục.

## 6. Ví dụ Java 17+ có thể chạy: editor và formatter được đăng ký tại từng DataBinder

Ví dụ này chạy **không cần web server** và trực tiếp dùng `org.springframework.validation.DataBinder`. Hai đối tượng `TravelForm` hoàn toàn độc lập chứng minh việc đăng ký trên binder thứ nhất không tự trở thành một cấu hình toàn cục cho binder thứ hai. Một tình huống ngày không hợp lệ minh họa lỗi chuyển kiểu được ghi vào `BindingResult`.

Cấu trúc:

~~~text
local-binding-demo/
├── pom.xml
└── src/main/java/LocalBindingDemo.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>local-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo theo các module Spring cần cho `DataBinder`, `Formatter` và `BindingResult` qua Maven transitive dependencies. Trong ứng dụng Spring Boot thực, nên dùng dependency management của phiên bản Boot mà dự án đã chọn.

### 6.2. src/main/java/LocalBindingDemo.java

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.validation.DataBinder;

public class LocalBindingDemo {

    public static final class TravelForm {
        private LocalDate travelDate;

        public LocalDate getTravelDate() {
            return travelDate;
        }

        public void setTravelDate(LocalDate travelDate) {
            this.travelDate = travelDate;
        }
    }

    public static final class SlashDateEditor
            extends PropertyEditorSupport {

        private static final DateTimeFormatter DATE_FORMAT =
                DateTimeFormatter.ofPattern("dd/MM/uuuu")
                        .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text, DATE_FORMAT));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : DATE_FORMAT.format(value);
        }
    }

    public static final class DotDateFormatter
            implements Formatter<LocalDate> {

        private DateTimeFormatter dateFormat(Locale locale) {
            return DateTimeFormatter.ofPattern("dd.MM.uuuu", locale)
                    .withResolverStyle(ResolverStyle.STRICT);
        }

        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text, dateFormat(locale));
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return dateFormat(locale).format(value);
        }
    }

    private static MutablePropertyValues input(String rawDate) {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("travelDate", rawDate);
        return values;
    }

    public static void main(String[] args) {
        TravelForm editorForm = new TravelForm();
        DataBinder editorBinder = new DataBinder(editorForm, "editorForm");
        editorBinder.registerCustomEditor(
                LocalDate.class, "travelDate", new SlashDateEditor());

        editorBinder.bind(input("31/12/2026"));
        System.out.println("editor.date=" + editorForm.getTravelDate());
        System.out.println("editor.errors="
                + editorBinder.getBindingResult().hasErrors());

        TravelForm formatterForm = new TravelForm();
        DataBinder formatterBinder =
                new DataBinder(formatterForm, "formatterForm");
        DotDateFormatter formatter = new DotDateFormatter();
        formatterBinder.addCustomFormatter(formatter, "travelDate");

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            formatterBinder.bind(input("01.01.2027"));
            System.out.println("formatter.date="
                    + formatterForm.getTravelDate());
            System.out.println("formatter.text="
                    + formatter.print(
                            formatterForm.getTravelDate(),
                            Locale.GERMANY));
            System.out.println("formatter.errors="
                    + formatterBinder.getBindingResult().hasErrors());

            TravelForm invalidForm = new TravelForm();
            DataBinder invalidBinder =
                    new DataBinder(invalidForm, "invalidForm");
            invalidBinder.addCustomFormatter(
                    new DotDateFormatter(), "travelDate");
            invalidBinder.bind(input("31.02.2027"));

            System.out.println("invalid.date="
                    + invalidForm.getTravelDate());
            System.out.println("invalid.fieldError="
                    + invalidBinder.getBindingResult()
                            .hasFieldErrors("travelDate"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=LocalBindingDemo
~~~

Kết quả `System.out` của chương trình (không tính log môi trường Maven):

~~~text
editor.date=2026-12-31
editor.errors=false
formatter.date=2027-01-01
formatter.text=01.01.2027
formatter.errors=false
invalid.date=null
invalid.fieldError=true
~~~

**Vì sao có kết quả đó?**

1. Binder `editorBinder` có editor theo field `travelDate` nhận `31/12/2026` và chuyển thành `LocalDate` cuối năm 2026. `LocalDate.toString()` xuất ISO `2026-12-31`. Không có lỗi binding.
2. Binder `formatterBinder` là **instance khác**. Nó nhận formatter riêng dùng dấu chấm `01.01.2027`, parse sang ngày đầu năm 2027. Khi gọi `formatter.print(...)`, giá trị được đưa về chuỗi `01.01.2027`.
3. `invalidBinder` nhận `31.02.2027`. Ngày 31 tháng 2 không tồn tại; formatter ném lỗi parse, quá trình binding ghi lỗi cho trường `travelDate`. Thuộc tính vẫn là `null`, `hasFieldErrors("travelDate")` trả `true`.
4. `LocaleContextHolder` được gán `Locale.GERMANY` để giữ locale rõ ràng trong ví dụ không có request. Trong Spring MVC, `LocaleResolver` và ngữ cảnh request thường quyết định locale mà formatter sử dụng. Khi tự thiết lập locale trong một luồng thực thi độc lập, dùng `try/finally` để tránh để sót ngữ cảnh locale.
5. Đăng ký formatter/editor **chỉ trên từng binder**, không đụng vào cấu hình conversion toàn cục. Việc class `DotDateFormatter` được dùng lại không tự làm các binder còn lại biết đến nó.

Với ứng dụng production, cần kiểm thử các đầu vào trống, ngày không hợp lệ, khác locale, ngày nhuận, múi giờ nếu chuyển sang `Instant` hoặc `ZonedDateTime`; `LocalDate` **không mang múi giờ**.

## 7. Đăng ký cục bộ trong Spring MVC: luồng thực tế

Khi xử lý form, Spring MVC thường theo trình tự:

~~~text
Tạo/lấy model attribute "travelForm"
                 |
       tạo WebDataBinder
                 |
  gọi @InitBinder phù hợp trong controller
       /                 \
   addCustomFormatter   registerCustomEditor
       \                 /
          bind field
                 |
       ghi lỗi vào BindingResult
                 |
  @Valid/@Validated nếu kích hoạt
                 |
     controller nhận form + BindingResult
~~~

Ví dụ rút gọn cho một form:

~~~java
@Controller
class BookingController {

    @InitBinder("travelForm")
    void configure(WebDataBinder binder) {
        binder.addCustomFormatter(
                new DotDateFormatter(), "travelDate");
    }

    @PostMapping("/book")
    String create(
            @Valid @ModelAttribute("travelForm") TravelForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "booking-form";
        }

        bookingService.create(form);
        return "redirect:/book/success";
    }
}
~~~

Đây là **đoạn minh họa nằm trong controller**, không phải chương trình độc lập. Nó giả định `TravelForm`, `DotDateFormatter`, `bookingService`, template và các imports Spring MVC đã có.

- `@InitBinder("travelForm")` nhắm tới binder cho model attribute tên `travelForm`.
- `binder.addCustomFormatter(..., "travelDate")` chỉ đổi quy tắc parse/print của field `travelDate` tại binder được cấu hình.
- Lỗi không chuyển được text sang `LocalDate` được tìm thấy qua `BindingResult`.
- `@Valid` hoặc `@Validated` kích hoạt bước validation thích hợp nếu ứng dụng có validator/Bean Validation tương ứng; việc đăng ký formatter **không tự gọi validate**.
- `bookingService` mới là nơi xử lý nghiệp vụ. Không để editor tự gọi repository hay thay đổi trạng thái domain.

Nếu input là JSON `@RequestBody` có giá trị ngày khác chuẩn, cần xem cấu hình Jackson và các annotation JSON như `@JsonFormat`. Đừng kỳ vọng editor cho form binding tự thay đổi cơ chế deserialize của Jackson.

## 8. Khi nào nên dùng @DateTimeFormat hoặc ConversionService chung?

Không phải tình huống nào cũng cần tự viết `PropertyEditor` hay `Formatter`.

### 8.1. Dùng annotation cho định dạng phổ biến

Với một trường ngày trong model nhận form parameters, có thể dùng:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class TravelForm {

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate travelDate;

    public LocalDate getTravelDate() {
        return travelDate;
    }

    public void setTravelDate(LocalDate travelDate) {
        this.travelDate = travelDate;
    }
}
~~~

Đây là một lớp riêng `TravelForm.java` dùng trong ngữ cảnh Spring MVC đã bật formatting. `@DateTimeFormat` thường gọn hơn nếu yêu cầu chỉ là một định dạng ngày tiêu chuẩn, không có logic phức tạp. Nếu dữ liệu đi vào `@RequestBody` JSON, annotation `@DateTimeFormat` không phải hợp đồng Jackson chính; cần cấu hình JSON độc lập.

### 8.2. Dùng FormatterRegistry nếu toàn ứng dụng thống nhất một quy tắc

~~~java
@Configuration
class MvcFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new DotDateFormatter());
    }
}
~~~

Đoạn này là cấu hình minh họa cần imports `Configuration`, `WebMvcConfigurer`, `FormatterRegistry` và `DotDateFormatter`. Nó đăng ký formatter vào registry chung của MVC, **khác** với đăng ký cục bộ trong `@InitBinder`. Chỉ dùng khi định dạng mong muốn áp dụng rộng rãi và đã xem xét tác động lên các controller, query parameters và form khác. Với nhiều field có yêu cầu khác nhau, đăng ký theo field trên binder phù hợp hơn.

### 8.3. Đừng nhầm Formatter với Converter

- `Converter<String, LocalDate>` chỉ giải bài toán chuyển chuỗi thành đối tượng theo cặp kiểu; hợp khi quy tắc độc lập locale hoặc không cần print ngược cho form.
- `Formatter<LocalDate>` có đủ parse, print và locale; phù hợp khi cần hiển thị và nhận lại dữ liệu người dùng ở cùng format.
- `PropertyEditorSupport` giữ trạng thái và hoạt động theo cơ chế JavaBeans; ưu tiên editor mới theo binder và chú ý thread-safety.
- `ConversionService` tập trung các converter/formatter được dùng chung. `DataBinder.setConversionService(...)` cho phép cấu hình conversion service ở binder, nhưng đây là lựa chọn khác với `addCustomFormatter(...)` đăng ký adapter ngay trong binder.
- `@DateTimeFormat` và `@NumberFormat` dùng với hạ tầng formatting của Spring cho những field thích hợp.

Không nên đăng ký nhiều formatter/editor khác nhau cho **cùng một field và cùng kiểu** rồi giả định thứ tự ưu tiên bất biến giữa mọi cấu hình. Hãy chọn một nguồn quy tắc rõ ràng, lập test cho field đó và không phụ thuộc vào thứ tự đăng ký ngẫu nhiên.

## 9. Lỗi chuyển kiểu, validation và việc hiển thị lỗi

Một lỗi input như `31.02.2027` không đồng nghĩa ngày đó vi phạm quy tắc nghiệp vụ đã được kiểm tra. Nó thất bại **ngay ở chuyển kiểu**. Spring lưu `FieldError` tương ứng vào `BindingResult` khi binding.

Với controller form:

~~~java
if (result.hasFieldErrors("travelDate")) {
    FieldError error = result.getFieldError("travelDate");
    String code = error != null ? error.getCode() : "unknown";
    // Ghi thông điệp phù hợp vào giao diện theo chính sách của ứng dụng.
}
~~~

Đoạn trên giả định đã có biến `BindingResult result` và import `org.springframework.validation.FieldError`. Mã lỗi có thể là một biến thể của `typeMismatch` được mở rộng với tên object/field; đừng cứng hóa chính xác toàn bộ chuỗi mã lỗi nếu chưa xem cấu hình `MessageCodesResolver`.

Với `DataBinder` thủ công:

~~~java
binder.bind(values);                       // Chuyển kiểu, ghi lỗi binding.
binder.validate();                         // Chạy validator nếu đã cấu hình.
BindingResult result = binder.getBindingResult();
boolean wrongDate = result.hasFieldErrors("travelDate");
~~~

Đây là đoạn minh họa cần biến `binder` và `values` đã có. Nếu chưa thêm validator thì `validate()` không có quy tắc kiểm tra nghiệp vụ để áp dụng. Một `Formatter` không thay thế Bean Validation hay Spring `Validator`. Cần cân nhắc khi validator truy cập field còn `null` do lỗi chuyển kiểu để tránh báo thêm lỗi trùng nguyên nhân.

Với UI form, Spring có thể dùng editor/formatter để in lại giá trị đã chuyển đổi; nhưng giá trị đầu vào bị từ chối có thể được giữ trong `BindingResult` để người dùng thấy dữ liệu vừa nhập. Đừng mặc định mọi `FieldError.getRejectedValue()` là an toàn để log hoặc đưa trực tiếp vào HTML mà không escape.

## 10. Những điểm cần tránh khi đăng ký cục bộ

1. **Đăng ký sau `bind(...)`.** Lúc đó conversion của dữ liệu đã xảy ra; cần đăng ký trước giai đoạn binding.
2. **Nhầm target type.** `CustomDateEditor` của Spring dành cho `java.util.Date`, không phải `java.time.LocalDate`. Với Java Time, dùng Formatter/Converter phù hợp, `@DateTimeFormat` hoặc editor tự viết đúng kiểu.
3. **Dùng editor mutable như singleton.** `PropertyEditorSupport` giữ giá trị; nên tạo instance editor mới cho từng binder, không chia sẻ giữa các request.
4. **Không khai báo field path khi yêu cầu chỉ một trường.** Overload theo type có thể tác động đến các thuộc tính cùng kiểu trên binder.
5. **Nhầm tên field và nhãn hiển thị.** Tên trong `registerCustomEditor(..., "travelDate", ...)` là property path trên đối tượng Java.
6. **Thay quy tắc toàn cục để giải quyết trường hợp cá biệt.** `WebMvcConfigurer.addFormatters` ảnh hưởng rộng; dùng `@InitBinder` hoặc DataBinder riêng khi đó mới là mong muốn.
7. **Giả định editor xử lý mọi JSON.** `@RequestBody` thường do Jackson deserialize; cấu hình WebDataBinder không tự thay đổi việc JSON parse thành model.
8. **Không xử lý đầu vào rỗng hoặc sai format.** Quyết định rõ chuỗi rỗng sẽ thành `null` hay lỗi, và kết hợp ràng buộc `@NotNull` khi bắt buộc phải có giá trị.
9. **Chấp nhận ngày không tồn tại.** Dùng parser nghiêm ngặt (`ResolverStyle.STRICT` hoặc `SimpleDateFormat.setLenient(false)`); kiểm thử ngày nhuận.
10. **Nhầm chuyển đổi và nghiệp vụ.** Editor/formatter chỉ tạo giá trị Java; điều kiện như “ngày khởi hành phải sau hôm nay” thuộc validation hoặc domain logic.
11. **Bỏ qua Locale.** Một formatter dùng dấu phẩy làm dấu thập phân ở khu vực này có thể khác dấu chấm ở khu vực khác; form gửi dữ liệu máy nên có format thống nhất.
12. **Quên giới hạn thuộc tính được gắn.** Editor/formatter không phải quyền truy cập. Ưu tiên DTO và giới hạn fields được phép property-bind khi cần.
13. **Không test phạm vi cục bộ.** Kiểm thử cả form được tùy biến và form khác để chắc chắn định dạng đặc biệt không lan ra ngoài.
14. **Dùng formatter chứa dữ liệu request mutable.** Formatter dùng chung nên stateless/thread-safe; context như locale đưa qua tham số hoặc Spring context thích hợp.

## 11. Bài tập kiểm tra hiểu biết

1. Có hai field `travelDate` và `birthday` cùng kiểu `LocalDate`. Chỉ `travelDate` nhập `dd.MM.uuuu`. Nên dùng overload `registerCustomEditor`/`addCustomFormatter` nào?
2. Vì sao một editor dùng `PropertyEditorSupport` không nên làm bean singleton chia sẻ giữa tất cả request?
3. `@InitBinder("travelForm")` có tác động tới mọi controller không? Phạm vi theo tên model attribute được xác định như thế nào?
4. Nếu API dùng `@RequestBody` JSON, đăng ký editor trong `@InitBinder` có thay đổi cách Jackson đọc `LocalDate` không?
5. Khi `travelDate=31.02.2027`, lỗi xuất hiện ở binding hay ở validator nghiệp vụ? Cần đọc thông tin nào từ `BindingResult`?
6. Khi mọi controller đều phải dùng cùng cách in tiền tệ theo locale, nên cân nhắc `@InitBinder` riêng hay `FormatterRegistry` chung?
7. Khi cần chặn field `admin` từ request, liệu `Formatter` có đủ không? Điều gì phải đảm nhận quyền chỉnh sửa dữ liệu?

Hãy tự thử thay `01.01.2027` thành `01/01/2027` ở binder có `DotDateFormatter` để quan sát lỗi, sau đó đổi sang `SlashDateEditor` **trên đúng binder đó** và giải thích vì sao kết quả khác đi. Bạn sẽ thấy rõ tính chất **“đăng ký ở binder nào, tác dụng ở binder đó”** và **“chỉ field được chọn mới nhận quy tắc cục bộ”**.

## Tài liệu tham khảo

- Spring Framework 6.2 — `@InitBinder` trong Spring MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — Data Binding và PropertyEditor: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Field Formatting / Formatter SPI: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- `DataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2.13 release: https://spring.io/blog/2025/11/13/spring-framework-6-2-13-available-now
