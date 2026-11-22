# DefaultFormattingConversionService và bộ định dạng mặc định trong Spring

Spring Framework cung cấp một hạ tầng thống nhất để **chuyển kiểu dữ liệu** và **định dạng giá trị phục vụ giao tiếp**. Ứng dụng thường nhận chuỗi từ form/query parameter rồi cần chuyển thành `Integer`, `BigDecimal`, `LocalDate`, enum hoặc kiểu domain. Khi hiển thị lại, ứng dụng cần chuyển giá trị Java thành chuỗi theo quy ước có thể phụ thuộc locale.

`DefaultFormattingConversionService` là implementation tiện dụng kết hợp hai khả năng: cơ chế chuyển kiểu tổng quát của Spring Core (`ConversionService`) và registry cho formatter. Nó đăng ký các converter/formatter phổ biến, đồng thời cho phép ứng dụng bổ sung converter, formatter và annotation formatter riêng.

Bài này giải thích bộ định dạng mặc định, cách locale ảnh hưởng parse/print, annotation định dạng số, formatter ngày giờ, cách đăng ký formatter tùy chỉnh và điểm mở rộng trong Spring MVC. Một ví dụ Java 17+ chạy độc lập minh họa chuyển số/Boolean bằng converter mặc định và formatter domain theo locale.

## 1. ConversionService, Formatter và FormattingConversionService

### ConversionService

`org.springframework.core.convert.ConversionService` cung cấp API kiểm tra và thực hiện chuyển đổi:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

API có thêm overload nhận `TypeDescriptor` để mô tả generic type và metadata của property. Các chuyển đổi phổ biến gồm `String -> Integer`, `String -> Boolean`, chuyển đổi giữa các kiểu số và chuyển đổi collection/array khi Spring xác định được kiểu nguồn/đích.

Một `Converter<S,T>` thực hiện chuyển đổi một chiều từ S sang T:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Converter thích hợp với chuyển đổi kỹ thuật hoặc domain không cần locale, chẳng hạn `String -> UUID` hoặc `String -> CustomerId`.

### Formatter

`org.springframework.format.Formatter<T>` kết hợp hai interface `Printer<T>` và `Parser<T>`:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Hai thao tác chính:

- `parse(String text, Locale locale)`: chuyển chuỗi người dùng nhập thành object `T`.
- `print(T object, Locale locale)`: chuyển object thành chuỗi để hiển thị.

Formatter nhận `Locale` nên phù hợp với số, ngày giờ, tiền tệ và dữ liệu có quy ước hiển thị theo ngôn ngữ/vùng địa lý. Ví dụ cùng số `1234.5` có thể hiển thị thành `1,234.5` ở locale Mỹ và `1.234,5` ở locale Đức.

### FormattingConversionService

`FormattingConversionService` là một `ConversionService` đồng thời là `FormatterRegistry`. Nó cho phép đăng ký:

- `Converter<S,T>` cho chuyển đổi một chiều.
- `ConverterFactory<S,R>` khi cần một họ kiểu đích.
- `GenericConverter` khi cần kiểm soát theo `TypeDescriptor`.
- `Formatter<T>` cho parse/print có locale.
- `AnnotationFormatterFactory<A>` cho định dạng phụ thuộc annotation.

`DefaultFormattingConversionService` là implementation có cấu hình mặc định hữu ích. Nó không tự hiểu tất cả kiểu domain riêng; những kiểu đó vẫn cần converter hoặc formatter do ứng dụng cung cấp.

## 2. DefaultFormattingConversionService đăng ký gì?

Khi khởi tạo mặc định, service đăng ký các converter scalar thông dụng và các formatter chuẩn. Nhìn tổng quát:

| Nhóm | Ví dụ |
|---|---|
| String và scalar | String sang số, Boolean, Character, enum và một số kiểu đơn giản |
| Number | Chuyển đổi giữa các kiểu số có hỗ trợ |
| Array/collection | Chuyển đổi phần tử và container khi biết kiểu nguồn/đích |
| Object và text | Các chuyển đổi chuỗi/đối tượng do converter tương ứng cung cấp |
| Formatting annotation | Ví dụ `@NumberFormat` trên field/property số |
| Date/time | Các formatter có thể đăng ký cho Java Date/Time; cấu hình Java Time dùng registrar tương ứng |

Cần tách hai khái niệm. Chuyển `"42"` thành `Integer(42)` là chuyển kiểu cơ bản. Hiển thị `BigDecimal` với dấu phân nhóm và thập phân theo locale là định dạng. Cùng một service quản lý cả hai, nhưng mục đích của converter và formatter khác nhau.

Constructor của `DefaultFormattingConversionService` cho phép chọn có đăng ký formatter mặc định hay không:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

// Tạo service không tự đăng ký các default formatters:
DefaultFormattingConversionService withoutDefaultFormatters =
        new DefaultFormattingConversionService(false);
~~~

Tham số `false` bỏ qua bước đăng ký formatter mặc định; ứng dụng có thể tự đăng ký formatter cần thiết qua registry. Không nên chọn chế độ này nếu code đang dựa vào annotation formatter hoặc các quy tắc định dạng chuẩn mà chưa bổ sung cấu hình thay thế.

Các converter và formatter mặc định cụ thể có thể thay đổi theo phiên bản Spring. Khi cần hành vi chính xác cho một kiểu, hãy kiểm tra Javadoc/reference của phiên bản ứng dụng đang chạy và viết test cho cấu hình thực tế.

## 3. Annotation @NumberFormat

Spring hỗ trợ `@NumberFormat` để khai báo cách định dạng property số:

~~~java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal total;

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Các style thường dùng:

- `NUMBER`: định dạng số.
- `CURRENCY`: định dạng tiền tệ theo locale.
- `PERCENT`: định dạng phần trăm theo locale.

Annotation cũng có thể khai báo pattern tương ứng với quy tắc `DecimalFormat`. Pattern phải được lựa chọn cẩn thận và kiểm tra với locale thật của ứng dụng. Không nên lưu chuỗi đã format như `"1.234,50"` trong database để thay cho giá trị số chuẩn; nên lưu `BigDecimal` và chỉ định dạng ở biên giao tiếp.

Ví dụ locale có thể cho cách biểu diễn khác nhau:

| Locale | Ví dụ số |
|---|---|
| `Locale.US` | `1,234.5` |
| `Locale.GERMANY` | `1.234,5` |
| `Locale.FRANCE` | Dùng dấu thập phân và ký tự phân nhóm theo quy ước tiếng Pháp |

Không hard-code dấu chấm hoặc dấu phẩy để parse dữ liệu người dùng. Với tiền, `CURRENCY` còn có thể thêm ký hiệu tiền tệ và khoảng trắng tùy locale/JDK. Locale **không xác định thay currency** cho nghiệp vụ; ứng dụng vẫn cần mã tiền tệ riêng nếu cần phân biệt EUR, USD hay loại khác.

### Annotation và TypeDescriptor

Khi chuyển đổi một property có `@NumberFormat`, Spring cần biết metadata của property. `TypeDescriptor` có thể mang annotation và generic information. Vì vậy chuyển đổi theo `Class<BigDecimal>` không luôn tương đương với chuyển đổi theo descriptor của field đã annotate: overload chỉ có Class không mang metadata annotation của field đó.

Ví dụ sử dụng descriptor:

~~~java
TypeDescriptor sourceType = TypeDescriptor.valueOf(String.class);
TypeDescriptor targetType =
        new TypeDescriptor(InvoiceForm.class.getDeclaredField("total"));

Object result = service.convert(
        "1,234.50", sourceType, targetType);
~~~

Kết quả phụ thuộc locale hiện hành và annotation trên property. Dùng `TypeDescriptor` khi cần metadata của field; dùng overload `Class` khi chỉ cần chuyển đổi dựa trên kiểu nguồn và kiểu đích.

## 4. Định dạng ngày giờ với Java Time

Ngày giờ có nhiều cách biểu diễn: `dd/MM/uuuu`, `MM/dd/uuuu`, tên tháng theo ngôn ngữ hoặc ISO-8601. Trong Spring MVC, `DateTimeFormatterRegistrar` giúp đăng ký formatter chuẩn cho kiểu Java Time.

Ví dụ cấu hình:

~~~java
import java.time.format.DateTimeFormatter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();

        registrar.setDateFormatter(
                DateTimeFormatter.ofPattern("dd/MM/uuuu"));
        registrar.setDateTimeFormatter(
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm"));

        registrar.registerFormatters(registry);
    }
}
~~~

Đây là cấu hình tích hợp vào Spring MVC, không phải chương trình độc lập. Pattern trên là quy ước được chọn rõ trong ứng dụng; nó không tự động đổi theo locale.

Lưu ý:

- `LocalDate` không chứa múi giờ. Không diễn giải nó như một instant.
- `LocalDateTime` cũng không xác định múi giờ; nếu cần một thời điểm toàn cầu, cân nhắc `Instant` hoặc `OffsetDateTime` theo hợp đồng.
- Với Java Time pattern, `uuuu` biểu diễn proleptic year; `YYYY` là week-based-year và có thể khác quanh ranh giới năm mới.
- Ngày không tồn tại như 31/02 phải bị từ chối, không tự điều chỉnh thành ngày khác.
- Nếu muốn định dạng theo locale, dùng formatter localized hoặc cấu hình locale-aware thay vì luôn đóng đinh một pattern.

## 5. Ví dụ Java 17+ chạy độc lập: converter mặc định và formatter riêng

Chương trình dùng `DefaultFormattingConversionService` để chuyển `String -> Integer` và `String -> Boolean` bằng converter có sẵn, sau đó đăng ký formatter cho kiểu domain `Price`. Formatter parse và print theo locale hiện hành.

Cấu trúc:

~~~text
formatting-service-demo/
├── pom.xml
└── src/main/java/demo/FormattingServiceDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatting-service-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/FormattingServiceDemo.java`:

~~~java
package demo;

import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.support.DefaultFormattingConversionService;
import org.springframework.format.Formatter;

public final class FormattingServiceDemo {

    public record Price(BigDecimal amount) {
    }

    public static final class PriceFormatter implements Formatter<Price> {

        @Override
        public Price parse(String text, Locale locale) {
            String input = text.trim();
            NumberFormat format = NumberFormat.getNumberInstance(locale);
            ParsePosition position = new ParsePosition(0);
            Number number = format.parse(input, position);

            if (number == null || position.getIndex() != input.length()) {
                throw new IllegalArgumentException(
                        "Giá không đúng định dạng: " + text);
            }

            return new Price(new BigDecimal(number.toString()));
        }

        @Override
        public String print(Price price, Locale locale) {
            NumberFormat format = NumberFormat.getNumberInstance(locale);
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
            return format.format(price.amount());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        Integer quantity = service.convert("42", Integer.class);
        Boolean enabled = service.convert("true", Boolean.class);

        System.out.println("quantity=" + quantity);
        System.out.println("enabled=" + enabled);

        service.addFormatterForFieldType(Price.class, new PriceFormatter());

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            Price price = service.convert("1.234,50", Price.class);
            String display = service.convert(price, String.class);

            System.out.println("price.amount=" + price.amount().toPlainString());
            System.out.println("price.display=" + display);
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Chạy với JDK 17+ và Maven:

~~~bash
cd formatting-service-demo
mvn -q compile exec:java -Dexec.mainClass=demo.FormattingServiceDemo
~~~

Stdout của các câu lệnh Java:

~~~text
quantity=42
enabled=true
price.amount=1234.5
price.display=1.234,50
~~~

Maven có thể in log riêng tùy môi trường. Kết quả `price.display` dùng `Locale.GERMANY` được đặt qua `LocaleContextHolder`. Formatter lấy locale hiện hành để parse/print. Vì LocaleContextHolder gắn với thread, ví dụ reset trong `finally`; trong web request Spring thường quản lý locale context theo vòng đời request.

Giải thích:

1. `service.convert("42", Integer.class)` dùng converter số mặc định.
2. `service.convert("true", Boolean.class)` dùng converter Boolean mặc định.
3. `addFormatterForFieldType(Price.class, ...)` đăng ký formatter cho kiểu domain `Price`.
4. Khi chuyển chuỗi sang Price và chuyển Price sang String, formatter được gọi ở hai chiều parse/print.
5. Formatter dùng NumberFormat theo locale và kiểm tra toàn bộ chuỗi đã được parse; phần ký tự thừa bị từ chối.

Ví dụ minh họa formatter số theo locale, chưa phải mô hình tiền tệ hoàn chỉnh. Ứng dụng tiền tệ thực tế cần xác định currency, số chữ số thập phân, rounding và đơn vị lưu trữ. `BigDecimal` phù hợp với giá trị thập phân hơn kiểu dấu phẩy động nhị phân.

## 6. Converter và Formatter: chọn cái nào?

| Tiêu chí | Converter | Formatter |
|---|---|---|
| Hợp đồng | `Converter<S,T>` | `Formatter<T>` |
| Chiều xử lý | Thường một chiều S → T | Hai chiều parse và print |
| Locale | SPI cơ bản không nhận locale | Nhận locale ở cả parse và print |
| Phù hợp | Chuyển đổi kỹ thuật/domain | Nhập và hiển thị dữ liệu người dùng |
| Ví dụ | `String -> UUID` | `String <-> LocalDate` |

Đăng ký converter:

~~~java
registry.addConverter(new CustomerIdConverter());
~~~

Đăng ký formatter:

~~~java
registry.addFormatter(new PriceFormatter());
~~~

Không cần tạo formatter chỉ để bọc một converter không phụ thuộc locale. Ngược lại, nếu giá trị có cách biểu diễn theo ngôn ngữ/vùng, formatter thường là lựa chọn tự nhiên hơn.

## 7. Đăng ký trong Spring MVC qua WebMvcConfigurer

Spring MVC cung cấp formatting conversion service cho data binding của form và query parameters. `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` là điểm mở rộng để đăng ký thêm formatter/converter vào service MVC quản lý.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                LocalDate.class,
                new Formatter<>() {
                    private final DateTimeFormatter formatter =
                            DateTimeFormatter.ofPattern("dd/MM/uuuu");

                    @Override
                    public LocalDate parse(String text, Locale locale) {
                        return LocalDate.parse(text, formatter);
                    }

                    @Override
                    public String print(LocalDate value, Locale locale) {
                        return formatter.format(value);
                    }
                });
    }
}
~~~

Đây là cấu hình tích hợp MVC. Ứng dụng nên tránh đăng ký nhiều formatter xung đột cho cùng kiểu mà không quy định rõ mục đích. Nếu muốn mẫu ngày tự thay đổi theo locale, sử dụng formatter localized hoặc registrar thay vì pattern cố định.

Handler nhận form:

~~~java
@PostMapping("/appointments")
String create(@Valid @ModelAttribute("form") AppointmentForm form,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "appointments/form";
    }
    // Tiếp tục kiểm tra nghiệp vụ sau khi binding/validation hợp lệ.
    return "appointments/success";
}
~~~

Nếu request gửi `date=31/12/2026`, formatter có thể chuyển thành `LocalDate`. Ngày sai định dạng hoặc không tồn tại tạo lỗi field được ghi vào `BindingResult`. Tham số BindingResult phải đứng ngay sau model attribute liên quan.

`@RequestBody` JSON là đường xử lý khác: Jackson/`HttpMessageConverter` deserialize body. Không giả định formatter được cấu hình cho `@ModelAttribute` sẽ tự điều khiển toàn bộ JSON serialization/deserialization. Jackson module và quy tắc JSON cần cấu hình riêng theo hợp đồng API.

## 8. Locale đến từ đâu?

Formatter nhận `Locale` để biết quy ước parse/print. Trong ứng dụng web, locale thường được quyết định qua `LocaleResolver` hoặc `LocaleContextResolver` và thông tin request. Các nguồn phổ biến:

- Locale mặc định của ứng dụng.
- Header HTTP `Accept-Language`.
- Locale đã được người dùng chọn và lưu theo cấu hình session/cookie.
- `LocaleContextHolder` trong quá trình xử lý request.

Không chỉ dựa vào locale mặc định của máy chủ để diễn giải chuỗi người dùng. Máy chủ chạy ở Đức không có nghĩa mọi người dùng đều nhập theo quy ước Đức. API machine-to-machine nên dùng định dạng ổn định theo hợp đồng, chẳng hạn ISO-8601 cho ngày; format thân thiện theo locale thích hợp hơn ở giao diện.

Với tiền, locale quyết định cách biểu diễn số nhưng không xác định currency. `1.234,50` trong ví dụ chỉ cho thấy cách viết số theo locale Đức, không chứng minh đó là EUR hay currency nào.

## 9. Những lỗi thường gặp

**Nhầm Converter và Formatter.** Converter một chiều không tự cung cấp cách hiển thị ngược theo locale. Khi cần cả parse và print, triển khai `Formatter<T>`.

**Hard-code dấu phân nhóm/thập phân.** Dùng `replace(",", ".")` hoặc `Double.parseDouble` cho nhiều locale rất dễ sai. Dùng formatter nhận locale.

**Nhầm locale với currency.** Locale quyết định cách biểu diễn; currency là thuộc tính nghiệp vụ riêng.

**Dùng pattern năm sai.** Trong Java Time, `YYYY` là week-based-year, không giống `uuuu` hoặc `yyyy` trong mọi ngữ cảnh. Gần ranh giới năm có thể tạo kết quả không như mong đợi.

**Định dạng ở tầng lưu trữ.** Lưu `"1.234,50"` như chuỗi làm tính toán, truy vấn và sắp xếp khó khăn. Lưu `BigDecimal` hoặc kiểu domain phù hợp; chỉ format ở UI/API boundary.

**Chỉ parse một phần input.** Formatter tự viết phải kiểm tra toàn bộ chuỗi đã được tiêu thụ, nếu không giá trị có ký tự thừa có thể được chấp nhận.

**Đăng ký formatter xung đột.** Nhiều formatter cho cùng kiểu có thể làm lựa chọn khó hiểu. Quy định một formatter rõ ràng hoặc dùng annotation để phân biệt property.

**Nhầm MVC binding với JSON.** `WebDataBinder` và formatter cho `@ModelAttribute` khác với Jackson khi đọc `@RequestBody`. Kiểm thử riêng từng con đường.

**Bỏ qua lỗi chuyển đổi.** Đặt BindingResult đúng vị trí, hiển thị lỗi phù hợp và không tiếp tục lưu dữ liệu khi form có lỗi.

## 10. Kiểm thử nên có

| Tình huống | Điều cần xác minh |
|---|---|
| `"42"` sang Integer | Giá trị số 42 |
| `"true"` sang Boolean | Boolean true |
| `"1.234,50"` với locale Đức | Giá trị domain 1234.50 |
| Cùng Price in với locale Mỹ | Dấu thập phân/phân nhóm theo locale Mỹ |
| Chuỗi có ký tự thừa | Formatter từ chối thay vì parse một phần |
| Ngày hợp lệ theo pattern | Parse thành đúng LocalDate |
| Ngày không tồn tại | Có lỗi chuyển đổi, không tự sửa sang ngày khác |
| `@NumberFormat` trên field | Annotation ảnh hưởng conversion khi metadata TypeDescriptor được dùng |
| Form MVC có lỗi | BindingResult chứa lỗi đúng field |
| JSON `@RequestBody` | Kiểm tra riêng quy tắc Jackson/JSON |

Với formatter tự viết, test hai chiều parse/print, nhiều locale, giá trị biên, chuỗi rỗng, null theo hợp đồng và dữ liệu sai. Nếu conversion service được chia sẻ, bảo đảm formatter không giữ mutable state theo request.

## 11. Chọn cấu hình phù hợp

- Dùng `DefaultFormattingConversionService` khi cần một service độc lập với bộ converter và formatter thông dụng.
- Dùng constructor `DefaultFormattingConversionService(false)` nếu muốn chủ động đăng ký formatter và không cần bộ formatter mặc định; phải bổ sung cấu hình thay thế đầy đủ.
- Dùng `addConverter(...)` cho chuyển đổi kỹ thuật/domain một chiều.
- Dùng `addFormatter(...)` hoặc `addFormatterForFieldType(...)` khi cần parse/print với locale.
- Dùng `@NumberFormat` khi một property số cần quy tắc riêng.
- Dùng `DateTimeFormatterRegistrar` cho cấu hình nhóm kiểu Java Time trong Spring MVC.
- Dùng `WebMvcConfigurer.addFormatters(...)` để mở rộng formatter/converter của MVC thay vì tạo service mới trong mỗi request.
- Giữ dữ liệu domain dưới dạng số/ngày giờ có kiểu; chỉ format khi nhận hoặc xuất dữ liệu.
- Kiểm tra lỗi conversion/validation và phân biệt form binding với JSON deserialization.

**Ghi nhớ:** `DefaultFormattingConversionService` là điểm khởi đầu hữu ích vì kết hợp chuyển kiểu cốt lõi với formatter mặc định. `ConversionService` trả lời “giá trị này chuyển được sang kiểu nào?”, còn `Formatter` trả lời “người dùng nhập và nhìn thấy giá trị đó theo locale nào?”. Cấu hình phù hợp giúp dữ liệu được parse và hiển thị nhất quán trong ứng dụng Spring.

### Tài liệu tham khảo

- Spring Framework Reference — Spring Type Conversion: `ConversionService`, `Converter`, `TypeDescriptor`.
- Spring Framework Reference — Spring Field Formatting: `Formatter`, `FormattingConversionService` và annotation formatting.
- Spring Framework Reference — Spring MVC Data Binding và `WebMvcConfigurer.addFormatters(...)`.
- Spring Framework Javadoc — `DefaultFormattingConversionService`, `FormattingConversionService`, `FormatterRegistry`, `DateTimeFormatterRegistrar`.
