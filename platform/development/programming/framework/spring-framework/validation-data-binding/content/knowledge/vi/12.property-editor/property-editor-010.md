# Lựa chọn PropertyEditor, Converter hoặc Formatter theo nhu cầu trong Spring Framework

## 1. Bài toán cần giải quyết

Khi Spring nhận dữ liệu từ form HTML, query string, path variable hoặc một nguồn cấu hình, giá trị ban đầu thường là chuỗi, trong khi thuộc tính Java có thể là `LocalDate`, `BigDecimal`, enum hoặc kiểu miền nghiệp vụ như `OrderId`. Framework cần một cách chuyển từ biểu diễn đầu vào sang kiểu đích. Ở chiều ngược lại, giao diện đôi khi cần in giá trị thành chuỗi để hiển thị.

Spring cung cấp ba hướng mở rộng dễ gây nhầm lẫn:

- **`PropertyEditor`**: cơ chế JavaBeans lâu đời, thường xử lý chuỗi và đối tượng cho một kiểu/thuộc tính thông qua một đối tượng editor có trạng thái.
- **`Converter<S, T>`**: chuyển một kiểu nguồn `S` thành kiểu đích `T`; phù hợp chuyển đổi tổng quát, không phụ thuộc cách hiển thị.
- **`Formatter<T>`**: đọc (`parse`) và in (`print`) giá trị `T` từ/sang chuỗi theo `Locale`; phù hợp dữ liệu hướng người dùng, đặc biệt ngày, số, tiền tệ.

**Nguyên tắc ra quyết định:** trước tiên kiểm tra converter/formatter mặc định và annotation có sẵn. Khi phải tự mở rộng, chọn `Converter` cho quy tắc đổi kiểu, `Formatter` cho cú pháp trình bày phụ thuộc locale, `PropertyEditor` cho điểm tích hợp JavaBeans hoặc mã cũ cần tương thích. Không cần tạo cả ba cho cùng một thuộc tính.

Ví dụ phân biệt:

| Nhu cầu | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| `"ORD-042"` → `OrderId`, dùng trong nhiều lớp | `Converter<String, OrderId>` | Quy tắc đổi kiểu độc lập với giao diện |
| `LocalDate` ↔ `"31/12/2026"` theo locale của form | `Formatter<LocalDate>` hoặc `@DateTimeFormat` | Có cả parse, print và ngữ cảnh locale |
| Làm việc với thư viện cũ yêu cầu `java.beans.PropertyEditor` | `PropertyEditor` | Tuân theo hợp đồng JavaBeans hiện có |
| Cắt khoảng trắng và đổi chuỗi rỗng thành `null` trong binder cũ | `StringTrimmerEditor`, qua `@InitBinder` khi cần | Editor chuyên dụng đã được Spring cung cấp |
| `"ACTIVE"` → enum `Status` thông thường | Không cần mã riêng | `ConversionService` của Spring đã hỗ trợ nhiều kiểu phổ biến |
| Đọc/ghi JSON ở `@RequestBody` hoặc `@ResponseBody` | Cấu hình JSON (ví dụ Jackson) | Bộ chuyển đổi HTTP message xử lý JSON, không phải `Formatter` MVC cho form |

## 2. Đặt ba cơ chế vào đúng luồng data binding

Đối với một form/model attribute trong Spring MVC, luồng khái niệm là:

```text
HTTP request parameters / form fields (String)
           |
           v
WebDataBinder / DataBinder
           |
           +--> custom PropertyEditor (nếu được đăng ký cho kiểu/field)
           |
           +--> ConversionService
                  +--> Converter<S,T>
                  +--> Formatter<T> (thông qua parser/printer adapter)
           |
           v
Thuộc tính Java đã được gán
           |
           +--> BindingResult: thông tin lỗi binding/conversion
           +--> Validation: kiểm tra ràng buộc nghiệp vụ/Bean Validation
```

Sơ đồ chỉ diễn tả các thành phần tham gia, **không phải thứ tự ưu tiên bất biến cho mọi API/đường đi**. `Formatter` thường được đăng ký vào `FormattingConversionService`, vốn triển khai `ConversionService`; `PropertyEditor` có cách đăng ký riêng trên binder/bean wrapper. Spring sử dụng cơ chế tương ứng tùy ngữ cảnh và cấu hình. Tránh đăng ký nhiều cách chuyển đổi cạnh tranh cho cùng một cặp kiểu và cùng một field.

Phân biệt ba trách nhiệm:

1. **Binding**: lấy tên field/giá trị từ nguồn dữ liệu và đặt vào object.
2. **Conversion/formatting**: diễn giải biểu diễn dữ liệu thành đúng kiểu Java hoặc in trở lại dạng chuỗi.
3. **Validation**: xác nhận giá trị đã có đúng yêu cầu hay không (`@NotNull`, `@Positive`, quy tắc miền nghiệp vụ).

Lỗi đổi kiểu có thể tạo `FieldError` với mã dạng `typeMismatch` trong `BindingResult` khi binding form; đó không phải là lỗi Bean Validation. Với `@RequestParam` hoặc `@PathVariable` đơn lẻ, cách framework bề mặt hóa ngoại lệ có thể khác. Khi sử dụng `@RequestBody` JSON, Spring giao nội dung cho `HttpMessageConverter`/thư viện JSON; tùy chỉnh `Converter` của MVC không mặc nhiên thay thế cấu hình Jackson.

## 3. PropertyEditor: thích hợp cho tích hợp JavaBeans và hệ thống cũ

`java.beans.PropertyEditor` là giao diện JDK, còn `PropertyEditorSupport` là lớp nền giúp ghi đè ít phương thức. Editor thường có `setAsText(String)`, `getAsText()`, `setValue(Object)` và `getValue()`.

Ví dụ đọc múi giờ từ form:

```java
import java.beans.PropertyEditorSupport;
import java.time.ZoneId;

public final class ZoneIdEditor extends PropertyEditorSupport {
    @Override
    public void setAsText(String text) {
        setValue(ZoneId.of(text.trim()));
    }

    @Override
    public String getAsText() {
        Object value = getValue();
        return value == null ? "" : ((ZoneId) value).getId();
    }
}
```

Đăng ký cục bộ trên một `WebDataBinder`:

```java
// Phương thức bên trong @Controller; đây là đoạn tích hợp, không phải file chạy độc lập.
@InitBinder("orderForm")
void initOrderFormBinder(WebDataBinder binder) {
    binder.registerCustomEditor(ZoneId.class, "zone", new ZoneIdEditor());
}
```

Trong đoạn trên, `"orderForm"` là tên model attribute và `"zone"` là đường dẫn thuộc tính của nó. Cần các import `@InitBinder`, `WebDataBinder`, `ZoneId` và class `ZoneIdEditor` tương ứng. Với `registerCustomEditor(ZoneId.class, editor)` không truyền field, editor có thể áp dụng theo kiểu trên binder đó.

**Điểm mạnh:** dễ tương thích hạ tầng JavaBeans cũ, có sẵn các editor như `CustomDateEditor` và `StringTrimmerEditor`; phù hợp khi thư viện hiện tại đã định nghĩa `PropertyEditor`.

**Hạn chế quan trọng:**

- Editor chứa trạng thái giá trị qua `setValue/getValue`. Không đặt một instance mutable dùng chung cho nhiều request hoặc nhiều thread; thường khởi tạo editor mới cho mỗi binder, hoặc đăng ký một `PropertyEditorRegistrar` có trách nhiệm tạo instance.
- Hợp đồng dựa trên `Object`/`String` nên tính an toàn kiểu yếu hơn `Converter<S,T>`.
- `PropertyEditor` không có tham số `Locale` ở các phương thức `setAsText/getAsText`. Nếu phải đọc/in theo locale, `Formatter` rõ ràng hơn.
- `SimpleDateFormat` cũng không thread-safe; nếu dùng trong `CustomDateEditor`, không chia sẻ đối tượng formatter mutable xuyên request.

Một ứng dụng mới không nên chọn editor chỉ vì dữ liệu đầu vào là `String`: `Converter<String,T>` cũng xử lý được tình huống này rõ ràng hơn.

## 4. Converter: đổi kiểu tổng quát, có kiểu rõ ràng

Hợp đồng chính là:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`S` và `T` có thể là kiểu bất kỳ; không bắt buộc một phía là `String`. Ví dụ `String → OrderId`, `UUID → AccountKey`, `EntityCode → DomainCode`, `Long → Duration`. Logic nên đơn nhiệm, dễ kiểm thử, không phụ thuộc HTTP request, hiển thị UI hoặc timezone ngầm.

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

record OrderId(String value) {}

final class StringToOrderId implements Converter<String, OrderId> {
    @Override
    public OrderId convert(String source) {
        String normalized = source.strip().toUpperCase(Locale.ROOT);
        if (!normalized.matches("ORD-[0-9]{3}")) {
            throw new IllegalArgumentException("OrderId phải có dạng ORD-123");
        }
        return new OrderId(normalized);
    }
}
```

Như vậy `" ord-042 "` trở thành `OrderId("ORD-042")`. Cấu trúc và kiểm tra mã được gom vào chỗ có thể dùng lại, thay vì rải `parse` ở controller.

Trong ứng dụng, đăng ký với `ConverterRegistry`, ví dụ `FormattingConversionService#addConverter` hoặc `WebMvcConfigurer#addFormatters`. `ConversionService` là facade để ứng dụng gọi `convert(source, Target.class)` hoặc để `DataBinder` dùng gián tiếp.

**Khi cần biến thể:**

- `ConverterFactory<S,R>` hữu ích khi nguồn giống nhau nhưng kiểu đích là một họ `R` có quan hệ kế thừa.
- `GenericConverter` và `ConditionalGenericConverter` hữu ích khi phải xem `TypeDescriptor`, generic/annotation hay điều kiện áp dụng phức tạp. Chỉ sử dụng khi `Converter<S,T>` không biểu đạt đủ.
- Nếu một giá trị hiển thị phải đổi theo `Locale`, `Converter` không nhận locale trong `convert`; đừng lén truy cập locale toàn cục để biến converter nghiệp vụ thành formatter giao diện.

`ConversionService` có nhiều chuyển đổi mặc định như `String` với số, enum và collection. Nên kiểm tra nhu cầu thực trước khi bổ sung converter mới, vì converter tự tạo quá rộng có thể ảnh hưởng các field khác.

## 5. Formatter: parse và print cho người dùng, có Locale

Hợp đồng Spring là:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // String print(T object, Locale locale)
    // T parse(String text, Locale locale) throws ParseException
}
```

Một formatter giải quyết **hai chiều của cùng quy tắc biểu diễn**: từ chuỗi do người dùng nhập thành kiểu Java và từ giá trị Java thành chuỗi để hiển thị. `Locale` được truyền vào cả hai chiều. Đây là khác biệt thiết kế với `Converter` chỉ có `convert(S)`.

Ví dụ formatter hiển thị ngày theo quy ước minh họa: tiếng Pháp `dd/MM/uuuu`, những locale khác `MM/dd/uuuu`. Mẫu này cố định để output của bài có thể kiểm tra; sản phẩm thật thường dùng chuẩn ISO hoặc chính sách locale cụ thể:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

final class UiLocalDateFormatter implements Formatter<LocalDate> {
    private DateTimeFormatter pattern(Locale locale) {
        String p = locale.getLanguage().equals(Locale.FRENCH.getLanguage())
                ? "dd/MM/uuuu" : "MM/dd/uuuu";
        return DateTimeFormatter.ofPattern(p, locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, pattern(locale));
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return pattern(locale).format(value);
    }
}
```

`ResolverStyle.STRICT` giúp tránh chấp nhận ngày không hợp lệ; dùng `uuuu` thay `yyyy` trong ví dụ với strict parsing để xử lý năm theo lịch ISO rõ ràng. `DateTimeFormatter` là immutable và thread-safe.

Trong Spring MVC, `FormattingConversionService` sẽ chuyển lời gọi tới formatter dựa trên kiểu và locale hiện hành. Các annotation sẵn có thường đủ:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class CheckoutForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate deliveryDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    // Cần có getter/setter hoặc cơ chế binding tương ứng.
}
```

`@DateTimeFormat` và `@NumberFormat` áp dụng định dạng ở field/parameter theo cơ chế formatting của Spring. Pattern số phụ thuộc quy tắc locale; với API cần định dạng ổn định giữa các máy và máy khách, cân nhắc ISO và quy ước rõ ràng. Không nên nhầm `@DateTimeFormat` với `@JsonFormat` của Jackson. Locale không đồng nghĩa timezone; `LocalDate` biểu diễn ngày không mang múi giờ, còn thời điểm (`Instant`, `ZonedDateTime`) cần chính sách timezone riêng.

Khi tự triển khai formatter: xử lý trường hợp dữ liệu sai bằng ngoại lệ có nghĩa; đảm bảo `parse` và `print` nhất quán trong cùng locale; tránh biến formatter thành service truy vấn database; giữ implementation thread-safe.

## 6. Chọn nhanh bằng câu hỏi quyết định

1. **Spring đã hỗ trợ sẵn chưa?** Thử chuyển đổi mặc định hoặc `@DateTimeFormat` / `@NumberFormat` trước; nếu đủ, không viết extension.
2. **Đầu vào/đầu ra chủ yếu là biểu diễn giao diện và có locale không?** Có → `Formatter<T>`; nếu chỉ cần định dạng một field, ưu tiên annotation tương ứng.
3. **Chỉ cần đổi một kiểu `S` thành kiểu `T`, không dính giao diện?** Có → `Converter<S,T>`, kể cả `S=String`.
4. **Có API JavaBeans hoặc mã cũ bắt buộc editor?** Có → `PropertyEditor`, đăng ký trong phạm vi cần thiết.
5. **Chỉ một form hoặc một field cần cách diễn giải đặc biệt?** Dùng `@InitBinder`/`binder.addCustomFormatter(...)` hoặc editor theo field; đừng tạo quy tắc toàn cục nếu chỉ một màn hình dùng.
6. **Cần nhận biết generic, annotation hoặc họ kiểu đích?** Xem `GenericConverter` / `ConverterFactory` / `AnnotationFormatterFactory` thay vì ép mọi trường hợp vào một `Converter`.

Bảng so sánh kỹ thuật:

| Tiêu chí | PropertyEditor | Converter<S,T> | Formatter<T> |
| --- | --- | --- | --- |
| Thuộc nền tảng | JavaBeans (`java.beans`) | Spring Core conversion | Spring formatting |
| Chữ ký trọng tâm | `setAsText/getAsText`, `setValue/getValue` | `T convert(S)` | `parse(String,Locale)` và `print(T,Locale)` |
| Kiểu đầu vào | Chủ yếu String/giá trị Object | Bất kỳ `S` | String ↔ `T` |
| Hướng sử dụng | Đọc và in theo editor | Một hướng/cặp kiểu | Hai chiều |
| Nhận `Locale` trực tiếp | Không | Không | Có |
| Trạng thái | Thường mutable | Nên stateless | Nên thread-safe |
| Nơi đăng ký | `DataBinder.registerCustomEditor`, registrar | `ConverterRegistry` / `addFormatters` | `FormatterRegistry` / `addFormatters` hoặc binder |
| Khuyến nghị | Tích hợp legacy hoặc đặc thù binder | Mặc định cho chuyển kiểu nghiệp vụ | Dữ liệu UI có parse/print/locale |

## 7. Ví dụ Java 17 chạy được: ba cơ chế cùng tham gia một lần binding

Ví dụ dưới đây chủ động dùng **ba kiểu đích khác nhau** để minh họa, tránh xung đột giữa ba quy tắc: converter cho `OrderId`, formatter cho `LocalDate`, editor cục bộ cho `ZoneId`. Chạy độc lập với máy chủ web, dùng `DataBinder` nên quan sát được đúng cơ chế bên dưới Spring MVC.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>binding-choice-demo</artifactId>
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
</project>
```

Tạo `ConversionChoiceDemo.java` ở cùng thư mục:

```java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.validation.DataBinder;

public class ConversionChoiceDemo {

    public record OrderId(String value) {}

    public static final class OrderIdConverter
            implements Converter<String, OrderId> {
        @Override
        public OrderId convert(String text) {
            String normalized = text.strip().toUpperCase(Locale.ROOT);
            if (!normalized.matches("ORD-[0-9]{3}")) {
                throw new IllegalArgumentException("Expected ORD-123");
            }
            return new OrderId(normalized);
        }
    }

    public static final class UiDateFormatter
            implements Formatter<LocalDate> {
        private DateTimeFormatter pattern(Locale locale) {
            String p = locale.getLanguage()
                    .equals(Locale.FRENCH.getLanguage())
                    ? "dd/MM/uuuu" : "MM/dd/uuuu";
            return DateTimeFormatter.ofPattern(p, locale)
                    .withResolverStyle(ResolverStyle.STRICT);
        }

        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text, pattern(locale));
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return pattern(locale).format(value);
        }
    }

    public static final class ZoneIdEditor
            extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            setValue(ZoneId.of(text.strip()));
        }

        @Override
        public String getAsText() {
            Object value = getValue();
            return value == null ? "" : ((ZoneId) value).getId();
        }
    }

    public static final class OrderForm {
        private OrderId id;
        private LocalDate deliveryDate;
        private ZoneId zone;

        public OrderId getId() { return id; }
        public void setId(OrderId id) { this.id = id; }

        public LocalDate getDeliveryDate() { return deliveryDate; }
        public void setDeliveryDate(LocalDate date) {
            this.deliveryDate = date;
        }

        public ZoneId getZone() { return zone; }
        public void setZone(ZoneId zone) { this.zone = zone; }
    }

    public static void main(String[] args) {
        // Mô phỏng locale của request để formatter in/đọc ngày.
        LocaleContextHolder.setLocale(Locale.FRANCE);
        try {
            var service = new DefaultFormattingConversionService();
            service.addConverter(new OrderIdConverter());
            service.addFormatter(new UiDateFormatter());

            var form = new OrderForm();
            var binder = new DataBinder(form, "orderForm");
            binder.setConversionService(service);
            binder.setAllowedFields("id", "deliveryDate", "zone");
            binder.registerCustomEditor(
                    ZoneId.class, "zone", new ZoneIdEditor());

            var input = new MutablePropertyValues();
            input.add("id", " ord-042 ");
            input.add("deliveryDate", "31/12/2026");
            input.add("zone", "Asia/Ho_Chi_Minh");

            binder.bind(input);

            System.out.println("errors="
                    + binder.getBindingResult().getErrorCount());
            System.out.println("id=" + form.getId().value());
            System.out.println("date=" + form.getDeliveryDate());
            System.out.println("zone=" + form.getZone().getId());
            System.out.println("uiDate="
                    + service.convert(form.getDeliveryDate(), String.class));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Chạy bằng Maven và JDK 17+; hai lệnh `javac`/`java` sau lấy toàn bộ dependency transitively từ Maven:

**PowerShell (Windows):**

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
$classpath = Get-Content cp.txt -Raw
javac -encoding UTF-8 -cp $classpath ConversionChoiceDemo.java
java -cp ".;$classpath" ConversionChoiceDemo
```

**Bash (Linux/macOS):**

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
CP="$(cat cp.txt)"
javac -encoding UTF-8 -cp "$CP" ConversionChoiceDemo.java
java -cp ".:$CP" ConversionChoiceDemo
```

**Stdout kỳ vọng** (không tính log tải dependency của Maven):

```text
errors=0
id=ORD-042
date=2026-12-31
zone=Asia/Ho_Chi_Minh
uiDate=31/12/2026
```

Giải thích từng kết quả:

- `id` được `OrderIdConverter` chuẩn hóa bằng `strip` và `Locale.ROOT`.
- `deliveryDate` được `UiDateFormatter.parse` đọc theo `Locale.FRANCE` thành `LocalDate`.
- `zone` được editor riêng của binder biến thành `ZoneId`.
- `uiDate` sử dụng chiều `print` của formatter thông qua `FormattingConversionService`, cho ra định dạng của locale đang áp dụng.
- `errors=0` cho thấy ba trường hợp đã bind thành công. Nó **không chứng minh dữ liệu đã qua Bean Validation** vì chương trình chưa gọi `validate()`.

Nếu sửa `id` thành `"INVALID"` hoặc ngày thành `"31/02/2026"`, conversion có thể bị từ chối; khi bind vào form, kiểm tra `binder.getBindingResult().getFieldErrors()` để biết trường nào sai. Trong chương trình nhỏ này không truy cập thuộc tính sau khi binding lỗi nếu thuộc tính có thể vẫn `null`.

## 8. Đăng ký đúng phạm vi trong Spring MVC

Trong ứng dụng MVC, nơi đăng ký phổ biến là:

**Toàn ứng dụng web** — dùng khi một quy tắc áp dụng nhất quán cho các controller:

```java
@Configuration
class MvcBindingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new OrderIdConverter());
        registry.addFormatter(new UiDateFormatter());
    }
}
```

Đây là đoạn tích hợp: cần các import Spring MVC/formatting và dùng đúng class converter/formatter của dự án. Với Spring Boot, `WebMvcConfigurer#addFormatters` thường là đường mở rộng thích hợp để giữ cấu hình MVC được tự động thiết lập. Đừng tự thay thế toàn bộ `FormattingConversionService` chỉ để thêm một converter nếu chưa xét các formatter mặc định và cấu hình của framework.

**Cục bộ một controller/model attribute** — dùng khi một form có format riêng hoặc phải dùng JavaBeans editor:

```java
@InitBinder("orderForm")
void configureOrderForm(WebDataBinder binder) {
    binder.registerCustomEditor(
            ZoneId.class, "zone", new ZoneIdEditor());
    // Hoặc binder.addCustomFormatter(new UiDateFormatter(), "deliveryDate");
}
```

`@ControllerAdvice` có thể chia sẻ binder customization cho nhiều controller nếu cần, nhưng phải kiểm soát phạm vi áp dụng. `WebFluxConfigurer#addFormatters` là điểm tương ứng ở stack WebFlux; không coi `@InitBinder` của MVC là cấu hình dùng cho mọi tầng và mọi kiểu nội dung.

**Ngoài web** — với `DataBinder` tự tạo, có thể `binder.setConversionService(service)` và `binder.registerCustomEditor(...)` như ví dụ. Với bean container, `ConversionService` còn được dùng trong nhiều tình huống chuyển đổi property. Phạm vi của từng đường đăng ký không giống nhau; bean conversion service không nên được giả định tự động ảnh hưởng mọi ngõ vào HTTP nếu cấu hình MVC đã có service riêng.

**Mở rộng theo annotation tùy biến** — khi cần quy tắc hiển thị riêng cho từng field như `@MoneyPattern`, xem `AnnotationFormatterFactory` thay vì tạo converter dùng toàn cục cho mọi `BigDecimal`.

## 9. Các lỗi thiết kế thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân dễ gặp | Hướng xử lý |
| --- | --- | --- |
| Format ngày đúng ở máy này nhưng sai ở máy khác | Dựa vào locale mặc định/JDK style thay vì pattern/ISO rõ ràng | Chỉ định `Locale`, ISO hoặc pattern thống nhất; thử các locale cần hỗ trợ |
| `Converter` không chạy khi nhận JSON | JSON được đọc qua `HttpMessageConverter`/Jackson | Đặt quy tắc JSON trong bộ cấu hình serializer/deserializer tương ứng |
| Editor thỉnh thoảng trả giá trị request trước | Dùng chung một instance `PropertyEditorSupport` mutable | Tạo editor mới theo binder/registrar |
| Parse ngày `31/02` được chấp nhận hoặc bị sửa thành ngày khác | Parser quá dễ dãi | Dùng strict parsing, validate domain sau convert |
| Converter đăng ký toàn cục làm đổi các field ngoài ý muốn | Định nghĩa chuyển đổi quá rộng hoặc nhiều đăng ký cạnh tranh | Thu hẹp kiểu `S,T`, dùng field-specific formatter/editor khi thực sự cục bộ |
| Form hiển thị ngày khác với ngày nhận vào | Parse và print không cùng quy tắc/locale | Kiểm tra tính round-trip `parse(print(value,locale),locale)` |
| Lỗi input thành HTTP 500 hoặc bị nuốt | Ngoại lệ bị bắt sai chỗ hoặc không kiểm tra `BindingResult` | Dùng cơ chế lỗi binding và trả thông báo theo field; test dữ liệu sai |
| `@NotNull` không bắt được chuỗi rỗng như mong đợi | Trim/null conversion và validation là hai bước khác nhau | Xác định hợp đồng của chuỗi trắng, `null` và ràng buộc phù hợp |
| Gắn timezone vào `LocalDate` | Nhầm ngày lịch với thời điểm | Phân biệt `LocalDate` với `Instant`/`ZonedDateTime` và chính sách timezone |
| Custom converter truy vấn DB cho mỗi field | Chuyển đổi cú pháp bị trộn với lookup nghiệp vụ | Đổi sang value object nhẹ rồi kiểm tra/tra cứu ở service/validator thích hợp |

Nên thiết kế kiểm thử theo ba nhóm: (1) giá trị hợp lệ và chuẩn hóa, (2) dữ liệu lỗi, `null` và chuỗi rỗng, (3) locale, thread safety và tích hợp binder. Với formatter, kiểm tra round-trip trong từng locale; với converter, test trực tiếp `convert` và `ConversionService`; với editor, test mỗi binder nhận instance độc lập và field path đúng. Khi binding HTTP, kiểm tra cả thông báo lỗi, field bị lỗi và việc không bind ngoài danh sách `allowedFields`.

## 10. Kết luận áp dụng

- Nếu bài toán là **đổi kiểu dữ liệu dùng lại nhiều nơi**, chọn **`Converter<S,T>`**.
- Nếu bài toán là **nhập và hiển thị dữ liệu theo locale**, chọn **`Formatter<T>`** hoặc annotation formatting có sẵn.
- Nếu phải **tương thích JavaBeans/legacy hoặc dùng editor sẵn có của binder**, chọn **`PropertyEditor`**, đăng ký ở phạm vi cần thiết và không chia sẻ editor có trạng thái.
- Nếu Spring đã có chuyển đổi và format phù hợp, **không tạo extension mới**.

Các công cụ này giải quyết chuyển đổi biểu diễn; chúng không thay thế validation miền nghiệp vụ, không tự động thay cấu hình JSON và không quyết định chính sách bảo mật cho việc bind input. Chọn đúng hợp đồng và phạm vi đăng ký giúp mã dễ đọc, dễ kiểm thử, nhất quán giữa các biểu mẫu.

### Tài liệu đối chiếu

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring MVC — Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring MVC — @InitBinder: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
