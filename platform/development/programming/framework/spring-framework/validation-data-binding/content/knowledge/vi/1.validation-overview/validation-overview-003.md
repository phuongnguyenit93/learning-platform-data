# Chuyển đổi kiểu và định dạng dữ liệu trong Spring

## 1. Vì sao cần chuyển đổi kiểu và định dạng?

Dữ liệu đi vào một ứng dụng Spring MVC thường xuất phát từ URL, query parameter, path variable, header hoặc biểu mẫu HTML. Ở ranh giới HTTP, các giá trị này thường có biểu diễn văn bản, trong khi chương trình Java cần kiểu có ý nghĩa như `Integer`, `BigDecimal`, `LocalDate`, `UUID`, enum hoặc kiểu nghiệp vụ. Khi hiển thị lại dữ liệu trên form, ứng dụng còn phải chuyển giá trị Java thành chuỗi đúng quy tắc ngày tháng, số và ngôn ngữ người dùng.

Ví dụ: yêu cầu `GET /orders?quantity=3&orderedOn=2026-11-02` có `quantity` là văn bản "3" và `orderedOn` là văn bản "2026-11-02". Controller muốn nhận số nguyên và ngày. Spring có thể chuyển đổi chúng trước khi gọi phương thức xử lý, thay vì buộc controller tự gọi `Integer.parseInt` và `LocalDate.parse` cho từng tham số.

Cần phân biệt bốn việc:

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
| --- | --- | --- |
| **Type conversion** (chuyển kiểu) | Biến một giá trị kiểu A thành kiểu B như thế nào? | Chuỗi "42" thành `Integer`; chuỗi mã hàng thành `ProductCode` |
| **Formatting** (định dạng/đọc định dạng) | Chuyển giá trị sang hoặc từ chuỗi theo quy ước trình bày nào? | `LocalDate` thành ngày hiển thị theo `Locale`; "1,234.50" thành số theo thiết lập tiếng Anh |
| **Data binding** (gán dữ liệu) | Ánh xạ tham số yêu cầu vào tham số phương thức hoặc thuộc tính đối tượng nào? | `price=12.50` thành thuộc tính `price` của đối tượng form |
| **Validation** (kiểm tra hợp lệ) | Giá trị đã chuyển có đáp ứng quy tắc nghiệp vụ không? | Số lượng phải lớn hơn 0; ngày bắt đầu không sau ngày kết thúc |

Chuyển kiểu và định dạng tham gia vào quá trình binding; validation thường diễn ra sau khi dữ liệu đã được gán hoặc cố gắng gán. Cú pháp không hợp lệ (ví dụ chuỗi "abc" cho số nguyên) là lỗi chuyển kiểu, khác với số nguyên -2 đã chuyển thành công nhưng vi phạm `@Min(1)`.

Luồng thường gặp trong Spring MVC:

~~~text
HTTP request (query/form/path/header)
        |
        v
HandlerMethodArgumentResolver / WebDataBinder
        |
        v
ConversionService / Converter / Formatter
        |
        +--> Thành công: kiểu Java, gán vào tham số hoặc model attribute
        |
        +--> Thất bại: lỗi typeMismatch / xử lý lỗi binding
        |
        v
Validation nếu được cấu hình -> controller -> kết quả/HTML
~~~

Riêng `@RequestBody` chứa JSON/XML đi chủ yếu qua `HttpMessageConverter` (thường là Jackson cho JSON). Jackson có hệ thống deserialization riêng. Không được mặc định rằng đăng ký một `Converter<String, T>` cho Spring MVC sẽ thay đổi cách Jackson đọc một trường trong JSON.

## 2. Các thành phần cốt lõi

### 2.1. ConversionService và ConverterRegistry

`org.springframework.core.convert.ConversionService` là API thống nhất để hỏi liệu một phép chuyển kiểu có được hỗ trợ và yêu cầu chuyển đổi:

~~~java
boolean supported = conversionService.canConvert(String.class, Integer.class);
Integer value = conversionService.convert("42", Integer.class);
~~~

`ConversionService` chỉ trình bày khả năng sử dụng. Việc đăng ký bộ chuyển kiểu thuộc `ConverterRegistry`. Một số triển khai thông dụng:

- `GenericConversionService`: engine đăng ký và thực hiện các converter.
- `DefaultConversionService`: cung cấp sẵn các converter phổ biến cho số, chuỗi, enum, collections và những loại thường gặp.
- `FormattingConversionService`: kết hợp `ConversionService` với `FormatterRegistry` để xử lý cả conversion và formatting.
- `DefaultFormattingConversionService`: cài đặt các converter và formatter mặc định, bao gồm hỗ trợ định dạng annotation phổ biến.

Không nên tạo `ConversionService` mới cho từng HTTP request. Thông thường cấu hình một instance dùng chung lúc ứng dụng khởi động. Các converter có trạng thái chỉ đọc hoặc không có trạng thái sẽ thuận tiện và an toàn hơn cho việc tái sử dụng đồng thời.

Khi cần thông tin kiểu đầy đủ hơn `Class<?>`, Spring dùng `TypeDescriptor`. Nó mô tả kiểu nguồn/đích, bao gồm thông tin generic, thuộc tính và annotation trong các trường hợp phù hợp. Cơ chế này quan trọng khi chuyển `List<String>` thành danh sách kiểu phần tử khác, hoặc khi formatter phụ thuộc annotation trên một field.

### 2.2. Chọn đúng SPI

| SPI | Khả năng | Khi dùng |
| --- | --- | --- |
| `Converter<S, T>` | Chuyển một kiểu nguồn cụ thể sang một kiểu đích cụ thể qua `T convert(S source)` | Phần lớn quy tắc chuyển đổi nghiệp vụ |
| `ConverterFactory<S, R>` | Tạo các converter cho một họ kiểu đích | Chẳng hạn một họ enum hoặc kiểu con của cùng một lớp gốc |
| `GenericConverter` | Xem cặp `ConvertiblePair` và `TypeDescriptor` lúc chạy | Quy tắc phụ thuộc generic/annotation hoặc nhiều cặp kiểu |
| `ConditionalGenericConverter` | Bổ sung điều kiện khớp cho converter tổng quát | Chỉ kích hoạt khi metadata của kiểu đích đáp ứng điều kiện |
| `Formatter<T>` | Kết hợp `Printer<T>` và `Parser<T>`, có tham số `Locale` | Đọc và in ngày, tiền, tỷ lệ hoặc giá trị hiển thị phụ thuộc locale |
| `AnnotationFormatterFactory<A>` | Chọn parser/printer theo annotation trên field | Xây cơ chế định dạng tùy biến bằng annotation |

Ưu tiên `Converter<S, T>` cho phép chuyển đổi không phụ thuộc trình bày; ưu tiên `Formatter<T>` nếu một giá trị phải được đọc và in như chuỗi, đặc biệt cần `Locale`. Chỉ dùng `GenericConverter` khi API đơn giản không thể diễn đạt đầy đủ quy tắc.

## 3. Ví dụ runnable: custom Converter<String, ProductCode>

Đây là một ứng dụng Java 17+ độc lập dùng Spring Core; không cần khởi chạy web server. Quy tắc của ví dụ: mã hàng luôn được chuẩn hóa thành chữ hoa và phải có dạng `SKU-` rồi tới bốn ký tự chữ/số.

Tạo file `src/main/java/ConversionExample.java`:

~~~java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

record ProductCode(String value) {
    ProductCode {
        if (value == null || !value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}

final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}

public class ConversionExample {
    public static void main(String[] args) {
        DefaultConversionService conversions = new DefaultConversionService();
        conversions.addConverter(new ProductCodeConverter());

        Integer quantity = conversions.convert("42", Integer.class);
        ProductCode code = conversions.convert(" sku-a123 ", ProductCode.class);

        System.out.println(quantity);
        System.out.println(code);
        System.out.println(conversions.canConvert(String.class, ProductCode.class));
    }
}
~~~

File `build.gradle` tối thiểu:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-core:7.0.9'
}

application {
    mainClass = 'ConversionExample'
}
~~~

Với JDK 17+ và Gradle đã cài, chạy:

~~~bash
gradle -q run
~~~

Đầu ra chuẩn:

~~~text
42
ProductCode[value=SKU-A123]
true
~~~

Giải thích:

1. `DefaultConversionService` cung cấp sẵn phép chuyển `String -> Integer`.
2. `addConverter` đăng ký quy tắc tùy biến `String -> ProductCode`. `Locale.ROOT` làm phép chuẩn hóa mã độc lập với ngôn ngữ của người dùng.
3. Record kiểm tra bất biến đầu vào. Chuỗi không khớp mẫu làm phép chuyển thất bại với ngoại lệ; trong bối cảnh web, Spring có thể chuyển thất bại đó thành lỗi binding.
4. `canConvert` chỉ cho biết có đường chuyển kiểu được đăng ký, **không chứng minh** mọi giá trị nguồn đều hợp lệ. Ví dụ, mã `SKU-ABCDEF` vẫn bị từ chối khi thực sự chuyển.

Nếu dự án dùng Spring Boot hoặc một Spring Framework khác, lấy phiên bản `spring-core` do dependency management của dự án quản lý thay cho phiên bản cố định ở ví dụ standalone. Converter nên xử lý một quy tắc có thể dự đoán; tránh truy cập cơ sở dữ liệu hoặc gọi mạng ngay trong một phép chuyển giá trị đơn giản.

## 4. Định dạng: Formatter, Printer, Parser và Locale

`Formatter<T>` gồm hai chiều:

- `T parse(String text, Locale locale)`: đọc chuỗi người dùng nhập thành giá trị có kiểu.
- `String print(T value, Locale locale)`: tạo chuỗi hiển thị từ giá trị đã có kiểu.

Ví dụ dưới đây là một formatter cho `LocalDate` hiển thị ngày theo cách viết ngày tháng trung bình của locale; lớp này đặt trong dự án có dependency `spring-context` hoặc thư viện Spring formatting tương ứng:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class LocalDateDisplayFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatFor(Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatFor(locale).format(value);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, formatFor(locale));
    }
}
~~~

`DateTimeFormatter` là immutable, thuận tiện cho ứng dụng đa luồng. Với cùng một `LocalDate`, các locale có thể cho chuỗi hiển thị khác nhau; không được giả định chuỗi ngày người dùng nhập theo locale A sẽ được phân tích đúng dưới locale B. Nếu API bên ngoài cần định dạng cố định, chọn ISO-8601 thay vì phụ thuộc locale hoặc thiết lập hệ điều hành.

Spring cũng cung cấp formatter có sẵn cho số, tiền, phần trăm và ngày giờ. Không cần viết formatter riêng chỉ để đọc một ngày ISO hay số thông thường. Nếu viết formatter cho tiền, chú ý đơn vị tiền, làm tròn và `BigDecimal`; kiểu `double` không phù hợp cho nhiều phép tính tiền chính xác.

`FormattingConversionService`/`FormatterRegistry` cho phép đăng ký converter và formatter tập trung. Ví dụ trong một dự án Spring MVC:

~~~java
import java.time.LocalDate;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DateDisplayConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                LocalDate.class, new LocalDateDisplayFormatter());
    }
}
~~~

Đây là đoạn **tích hợp**, không phải chương trình có `main` riêng: đặt cùng package với `LocalDateDisplayFormatter` và chạy trong ứng dụng Spring MVC. Đăng ký theo kiểu có thể ảnh hưởng nhiều field `LocalDate` trong MVC; nếu một trường cần kiểu trình bày khác, cân nhắc annotation định dạng hoặc quy tắc cục bộ. Đừng thêm global formatter chỉ để khắc phục lỗi của một endpoint.

## 5. Annotation @DateTimeFormat và @NumberFormat

Spring hỗ trợ định dạng ngay tại field/parameter, thường dễ đọc hơn cấu hình một formatter áp dụng toàn ứng dụng.

### 5.1. Ngày và giờ

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate arrivalDate;

    @DateTimeFormat(pattern = "dd/MM/yyyy HH:mm")
    private LocalDateTime appointmentTime;

    public LocalDate getArrivalDate() {
        return arrivalDate;
    }

    public void setArrivalDate(LocalDate arrivalDate) {
        this.arrivalDate = arrivalDate;
    }

    public LocalDateTime getAppointmentTime() {
        return appointmentTime;
    }

    public void setAppointmentTime(LocalDateTime appointmentTime) {
        this.appointmentTime = appointmentTime;
    }
}
~~~

- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` diễn đạt hợp đồng nhập ngày dạng ISO, ví dụ `2026-11-02` cho `LocalDate`. Đây là lựa chọn tốt cho HTML `input type="date"` và query parameter cần định dạng ổn định.
- `pattern = "dd/MM/yyyy HH:mm"` là một định dạng cụ thể, ví dụ `02/11/2026 09:30`; người gửi yêu cầu phải dùng đúng định dạng mong đợi.
- `LocalDate` không chứa múi giờ hoặc giờ trong ngày. `LocalDateTime` cũng không biểu diễn offset/múi giờ; với thời điểm thực tế xuyên múi giờ, cân nhắc `Instant` hoặc `OffsetDateTime` và xác định quy ước timezone rõ ràng.
- Pattern cho parsing và hiển thị thuộc cùng ngữ cảnh format. Một chuỗi ngày không hợp lệ vẫn tạo lỗi binding; annotation không tự xác nhận tính hợp lý nghiệp vụ như ngày đặt trong tương lai.

### 5.2. Số và tiền tệ

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class PaymentForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal subtotal;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal displayAmount;

    public BigDecimal getSubtotal() {
        return subtotal;
    }

    public void setSubtotal(BigDecimal subtotal) {
        this.subtotal = subtotal;
    }

    public BigDecimal getDisplayAmount() {
        return displayAmount;
    }

    public void setDisplayAmount(BigDecimal displayAmount) {
        this.displayAmount = displayAmount;
    }
}
~~~

`@NumberFormat` hỗ trợ pattern hoặc style như `NUMBER`, `CURRENCY`, `PERCENT`. Ký tự phân cách hàng nghìn, phần thập phân và ký hiệu tiền có thể khác nhau theo `Locale`. Chẳng hạn chuỗi `1,234.50` thường hợp với thiết lập tiếng Anh Mỹ; không nên gửi nguyên chuỗi này và giả định mọi locale đều hiểu giống nhau.

Một giá trị `BigDecimal` mang con số, **không tự chứa đơn vị tiền tệ**. `CURRENCY` là quy tắc hiển thị/nhập theo locale, không phải cơ chế quy đổi tỷ giá hay giải quyết tiền tệ đa quốc gia. Giá trị lưu trữ và dữ liệu trao đổi nên theo một hợp đồng rõ ràng; quy tắc trình bày để ở biên giao diện.

## 6. Đăng ký converter/formatter trong Spring MVC

Cách phổ biến để đăng ký dùng chung ở Spring MVC là `WebMvcConfigurer.addFormatters(FormatterRegistry)`. Ví dụ sau chuyển mã hàng trong `@RequestParam` bằng một converter riêng, đồng thời nhận ngày ISO. Các lớp thuộc cùng package trong ứng dụng Spring MVC/Spring Boot có web starter; mã là ví dụ tích hợp, ứng dụng host phải có cấu hình khởi chạy web.

File `ProductCode.java`:

~~~java
package com.example.catalog;

public record ProductCode(String value) {
    public ProductCode {
        if (value == null || !value.matches("SKU-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
~~~

File `StringToProductCode.java`:

~~~java
package com.example.catalog;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCode
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

File `CatalogMvcConfig.java`:

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CatalogMvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCode());
    }
}
~~~

File `CatalogController.java`:

~~~java
package com.example.catalog;

import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    @GetMapping("/preview")
    public String preview(
            @RequestParam("code") ProductCode code,
            @RequestParam("date")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate date) {
        return code.value() + " @ " + date;
    }
}
~~~

Với server đang chạy trên `localhost:8080`, yêu cầu:

~~~http
GET /catalog/preview?code=sku-a123&date=2026-11-02 HTTP/1.1
Host: localhost:8080
~~~

Kết quả body dạng text:

~~~text
SKU-A123 @ 2026-11-02
~~~

Đường đi: MVC đọc chuỗi `code` và `date`; converter đã đăng ký chuẩn hóa `code`, trong khi formatter ngày xử lý `date` theo `@DateTimeFormat`. Controller nhận hai đối tượng Java có kiểu và không cần tự parse chúng. Nếu mã hàng hoặc ngày sai định dạng, quá trình resolve tham số có thể thất bại trước khi vào phương thức controller, thường tạo HTTP 400 qua cơ chế xử lý lỗi mặc định. Ứng dụng có thể chuẩn hóa thông báo lỗi bằng `@ControllerAdvice`, nhưng không nên chuyển mọi lỗi parse thành 500.

Ngoài `@RequestParam`, nhiều tham số `@PathVariable`, `@RequestHeader`, `@CookieValue` và giá trị khác xuất phát từ chuỗi cũng dùng cơ chế chuyển kiểu của MVC. Việc formatter có được dùng ở vị trí cụ thể hay không phụ thuộc kiểu nguồn, annotation và bộ binder của request.

## 7. Data binding vào @ModelAttribute

Với form có nhiều trường, `WebDataBinder` tạo/gắn các giá trị lên một đối tượng nhận dữ liệu. Ví dụ một lớp form có thuộc tính ngày và ngân sách:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class SearchFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal budget;

    public LocalDate getFrom() {
        return from;
    }

    public void setFrom(LocalDate from) {
        this.from = from;
    }

    public BigDecimal getBudget() {
        return budget;
    }

    public void setBudget(BigDecimal budget) {
        this.budget = budget;
    }
}
~~~

Controller sử dụng DTO chuyên cho input và bắt lỗi binding:

~~~java
package com.example.catalog;

import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {

    @InitBinder("searchFilter")
    public void configureBinding(WebDataBinder binder) {
        binder.setAllowedFields("from", "budget");
    }

    @GetMapping("/catalog/search")
    public String search(
            @ModelAttribute("searchFilter") SearchFilter filter,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "Invalid filter";
        }

        return "from=" + filter.getFrom()
                + ", budget=" + filter.getBudget();
    }
}
~~~

Ví dụ khi locale của request là `en_US`, `/catalog/search?from=2026-11-02&budget=1%2C234.50` có thể bind `from` thành `LocalDate.of(2026, 11, 2)` và `budget` thành `BigDecimal("1234.50")`. Nếu giá trị không parse được, `BindingResult` đứng **ngay sau** tham số `@ModelAttribute` cho phép controller đọc lỗi; có thể kiểm tra `getFieldErrors()` và mã `typeMismatch` để trả thông báo chi tiết. Không nên giả định kết quả parse theo cùng mẫu khi đổi locale của request.

`@InitBinder` chỉ cấu hình binder trong phạm vi controller, hoặc phạm vi được xác định nếu đặt tại `@ControllerAdvice`; có thể đăng ký `Formatter` hay `PropertyEditor` cục bộ khi cần. Ví dụ `binder.addCustomFormatter(...)` là một lựa chọn cho kiểu định dạng đặc thù. `setAllowedFields` giới hạn các thuộc tính được phép gán qua property binding, tránh để client sửa những field ngoài ý muốn; constructor binding và quy tắc liên quan vẫn phải được thiết kế cẩn thận. Dùng form DTO thay vì bind trực tiếp lên entity domain có nhiều thuộc tính nhạy cảm.

## 8. Lỗi chuyển kiểu và tương tác với validation

Spring không tự biến giá trị sai kiểu thành giá trị đúng. Các trường hợp cần phân biệt:

| Đầu vào hoặc tình huống | Giai đoạn | Cách xử lý phù hợp |
| --- | --- | --- |
| `quantity=abc` cho `int` | Conversion thất bại | Trả lỗi kiểu dữ liệu / thông báo nhập số |
| `date=2026-02-30` cho ngày ISO | Parsing ngày thất bại | Trả lỗi định dạng/ngày không tồn tại |
| `quantity=-3` cho `int` có `@Min(1)` | Chuyển kiểu thành công, validation thất bại | Trả lỗi quy tắc tối thiểu |
| `@RequestParam` bắt buộc vắng mặt | Resolving argument / missing value | Trả lỗi thiếu tham số |
| Chuỗi rỗng chuyển thành `null` trong tham số bắt buộc | Resolving sau conversion | Có thể bị coi là thiếu giá trị |
| JSON chứa kiểu không hợp lệ trong `@RequestBody` | JSON deserialization / message conversion | Xử lý lỗi đọc body; không kỳ vọng MVC Converter tự xử lý |

Trong `@ModelAttribute`, lỗi field binding có thể xuất hiện trong `BindingResult`. Sau đó `@Valid` hoặc `@Validated` mới kích hoạt validation theo cấu hình tương ứng. Một thuộc tính không parse được có thể chưa có giá trị đúng để áp dụng ràng buộc nghiệp vụ; giao diện nên báo lỗi parse trước và tránh thông báo khó hiểu.

Với tham số đơn như `@RequestParam`, lỗi chuyển kiểu thường được Spring MVC biểu diễn qua `MethodArgumentTypeMismatchException` hoặc các ngoại lệ resolve tương ứng, rồi đưa qua exception resolver. `@ModelAttribute` có thể được xử lý bằng `BindingResult` ngay trong controller nếu khai báo sát tham số đó; thiếu tham số xử lý lỗi/validation có thể dẫn tới ngoại lệ như `MethodArgumentNotValidException` tùy trường hợp. Không nên ghi cứng một kiểu exception cho mọi đường binding hay mọi phiên bản Spring.

Có thể kết hợp validation:

~~~java
import jakarta.validation.constraints.Min;

public class QuantityForm {
    @Min(1)
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Để Bean Validation hoạt động, ứng dụng phải có Jakarta Validation API và provider phù hợp (trong Spring Boot thường dùng dependency validation starter), và controller cần kích hoạt validation như `@Valid @ModelAttribute`. `@Min(1)` không thay thế converter; nó kiểm tra số lượng sau khi phép chuyển kiểu thành công. Nếu `null` không được chấp nhận, cần thêm `@NotNull` thay vì chỉ dùng `@Min`.

## 9. Phạm vi cấu hình và các ranh giới dễ nhầm

**Converter trong Spring container và MVC:** `ConversionService` được Spring sử dụng trong nhiều tình huống như binding thuộc tính bean hoặc SpEL; MVC có conversion service phục vụ argument binding. Việc cấu hình một bean tên `conversionService` và việc thêm formatter qua `WebMvcConfigurer.addFormatters` liên quan nhưng không nên mặc định là cùng instance ở mọi cấu hình ứng dụng. Đăng ký converter vào đúng registry của luồng đang gặp lỗi.

**Global vs local:** `addFormatters` thích hợp cho quy tắc chung, nhất quán ở nhiều controller. `@InitBinder` thích hợp cho quy tắc đặc thù của controller/model attribute. Annotation trên field thích hợp khi chính field đó có quy ước format riêng. Tránh thay đổi converter mặc định toàn cục chỉ để giải quyết một mẫu input ngoại lệ.

**Binding vs serialization:** `@RequestBody` được đọc từ nội dung HTTP bằng message converter, thường Jackson, nên định dạng ngày trong JSON thường chịu ảnh hưởng cấu hình Jackson hoặc các annotation của Jackson. Tương tự, việc trả JSON phụ thuộc serializer, không phải chiều `Formatter.print` của form MVC. Test form/query và JSON thành hai luồng riêng.

**Nhập dữ liệu vs hiển thị:** Một API dùng chung giữa nhiều hệ thống nên định nghĩa dạng chuẩn như ISO-8601 cho ngày giờ và dạng số không phụ thuộc locale. Một trang HTML có thể chọn định dạng thân thiện với người dùng theo `Locale`; khi parse và print phải dùng cùng quy tắc. Không lấy chuỗi hiển thị làm biểu diễn chuẩn để lưu dữ liệu.

**Khoảng trắng và rỗng:** Converter tùy biến có thể chọn `trim`/chuẩn hóa. Hãy ghi rõ quy ước vì khoảng trắng đôi khi có ý nghĩa. Với tham số bắt buộc, chuỗi rỗng có thể bị chuyển thành `null` rồi được xem là thiếu giá trị; `Optional<T>` hoặc `required=false` chỉ nên dùng nếu nghiệp vụ thật sự chấp nhận vắng mặt.

**Thread safety:** Tránh chia sẻ `SimpleDateFormat` mutable giữa các request. Dùng `DateTimeFormatter` immutable hoặc tạo formatter theo request. Không lưu trạng thái request/locale trong singleton converter; `Formatter` đã nhận `Locale` qua tham số.

**Định dạng sai và lỗi bảo mật:** Converter không phải chỗ thích hợp để ghi thay đổi vào hệ thống, bỏ qua kiểm tra quyền hoặc suy diễn đối tượng domain nhạy cảm từ chuỗi người dùng. Với binding đối tượng, dùng DTO và giới hạn field được bind; validation và phân quyền vẫn là các bước độc lập.

## 10. Cách lựa chọn trong bài toán thực tế

| Nhu cầu | Cách làm thường phù hợp | Lý do |
| --- | --- | --- |
| Query parameter số/ngày/enum chuẩn | Dùng built-in conversion; thêm `@DateTimeFormat` khi cần ISO/pattern | Ít cấu hình, hợp đồng input rõ |
| Chuỗi mã nghiệp vụ thành value object | `Converter<String, ValueObject>` và đăng ký vào registry đúng phạm vi | Tập trung chuẩn hóa và bất biến |
| Field số/tiền/ngày theo locale trên form | `@NumberFormat`, `@DateTimeFormat` hoặc `Formatter<T>` | Có cả parse và print |
| Nhiều định dạng tùy theo annotation riêng | `AnnotationFormatterFactory` | Quy tắc rõ theo từng field |
| Chuyển collection hoặc kiểu phụ thuộc generic/annotation | `GenericConverter`/`TypeDescriptor` | Cần metadata kiểu ở runtime |
| Chỉ một form có quy tắc ngoại lệ | `@InitBinder` / formatter cục bộ | Hạn chế tác động ngoài phạm vi |
| JSON có cấu trúc hoặc ngày trong `@RequestBody` | Cấu hình Jackson/message converter | Đúng tầng deserialization của body |

Ví dụ checklist kiểm thử cho một form hoặc endpoint:

1. **Đường đi đúng:** xác nhận source là query/form/path hay JSON; cấu hình formatter/converter đúng thành phần sử dụng.
2. **Happy path:** số nguyên, ngày ISO, custom value object; kiểm tra cả kiểu Java thu được lẫn phản hồi.
3. **Input lỗi:** chữ trong số, ngày không tồn tại, mã sai cấu trúc; kỳ vọng lỗi binding rõ ràng và status HTTP thích hợp.
4. **Locale:** cùng một chuỗi số/ngày thử với hai locale để phát hiện dấu phân cách và thứ tự ngày tháng không nhất quán.
5. **Giá trị biên:** vắng mặt, rỗng, whitespace, `null`, giá trị quá lớn hoặc nhiều chữ số thập phân.
6. **Validation:** tách lỗi type mismatch khỏi lỗi `@NotNull`, `@Min`, `@Past`/`@Future` theo yêu cầu nghiệp vụ.
7. **Phạm vi tác động:** test endpoint khác để chắc rằng custom converter/formatter toàn cục không đổi ý nghĩa input ngoài dự kiến.
8. **Binding an toàn:** gửi thêm field không được phép và xác minh đối tượng không bị gán ngoài dự kiến.

## 11. Ghi nhớ

Spring tách việc chuyển kiểu (`ConversionService`, `Converter`) với việc đọc/in biểu diễn theo locale (`Formatter`), rồi dùng chúng trong quy trình data binding. Với đa số dữ liệu phổ biến, bộ chuyển đổi và annotation có sẵn đã đủ. Khi thêm quy tắc riêng, hãy chọn SPI đơn giản nhất, đăng ký đúng phạm vi, kiểm thử cả đường vào lẫn hiển thị, và xử lý lỗi binding tách biệt với validation nghiệp vụ. Đây là nền tảng để controller nhận dữ liệu Java có kiểu rõ ràng và không chứa logic parse lặp lại.

### Tài liệu đối chiếu chính thức

- [Spring Framework - Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework - Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring MVC - Type Conversion configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring MVC - Controller argument type conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
- [Spring MVC - @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC - Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
