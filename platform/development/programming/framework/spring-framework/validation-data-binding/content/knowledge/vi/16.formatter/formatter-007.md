# Đăng ký Formatter theo kiểu trường hoặc annotation trong Spring

## 1. Formatter là gì và vì sao cần đăng ký?

Dữ liệu gửi từ form thường là text, trong khi model Java cần kiểu cụ thể. Ví dụ người dùng gửi ngày `2026-11-02`, số tiền `$1,234.50` hoặc một giá trị phần trăm. Khi hiển thị lại object, ứng dụng cũng cần chuyển giá trị Java thành text phù hợp với người đọc.

Spring cung cấp hai hướng chuyển đổi:

- **`Converter<S,T>`** chuyển một chiều giữa hai kiểu Java, ví dụ `String → CustomerId`. Chữ ký không nhận `Locale`.
- **`Formatter<T>`** chuyên cho chuyển đổi giữa text và object, có cả `parse(String, Locale)` và `print(T, Locale)`. Đây là lựa chọn tự nhiên khi cách nhập hoặc hiển thị phụ thuộc ngôn ngữ, vùng hay quy ước định dạng.

Một `Formatter<T>` có thể đăng ký theo hai cách:

1. **Theo kiểu trường:** mọi field có kiểu tương ứng dùng chung formatter, ví dụ tất cả `LocalDate` trong form.
2. **Theo annotation trên field/property:** formatter được chọn khi field có annotation cụ thể, ví dụ `@UsdAmount` chỉ áp dụng cho các trường tiền tệ cần USD, dù nhiều field có cùng kiểu `BigDecimal`.

Hai API trọng tâm của `FormatterRegistry` là `addFormatterForFieldType(...)` và `addFormatterForFieldAnnotation(...)`. Chọn đúng phạm vi đăng ký giúp một kiểu Java có thể được hiển thị khác nhau theo ý nghĩa của từng field mà không cần tạo nhiều kiểu dữ liệu chỉ để phục vụ presentation.

## 2. Hợp đồng Formatter và Parser/Printer

Spring định nghĩa `org.springframework.format.Formatter<T>` là hợp đồng kết hợp `Printer<T>` và `Parser<T>`:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}
```

- `parse` nhận text và locale, tạo object kiểu `T`.
- `print` nhận object và locale, tạo chuỗi hiển thị.
- `Locale` cho phép xử lý ngày, số và tiền tệ theo quy ước địa phương.
- `ParseException` biểu diễn text không parse được; khi formatter chạy qua conversion infrastructure, Spring chuyển thất bại thành exception chuyển đổi thích hợp.

Formatter nên có parse/print đối xứng về ý nghĩa. Nếu `print` tạo ra chuỗi mà `parse` không thể đọc lại, form round-trip có thể làm sai lệch dữ liệu. Không nên tự thay dấu phẩy/dấu chấm bằng `String.replace` khi định dạng phụ thuộc locale.

## 3. Đăng ký theo kiểu trường: addFormatterForFieldType

Dùng đăng ký theo kiểu khi mọi field thuộc cùng kiểu dữ liệu có cùng quy tắc parse/print.

```java
FormatterRegistry registry = ...;
registry.addFormatterForFieldType(
    LocalDate.class,
    new IsoLocalDateFormatter()
);
```

`FormatterRegistry` thuộc `org.springframework.format`. Phương thức `addFormatterForFieldType(Class<?>, Formatter<?>)` đăng ký formatter cho kiểu trường cụ thể. Có overload dành cho `Printer<?>` hoặc `Parser<?>` riêng nếu ứng dụng chỉ cần một chiều.

Ví dụ một formatter ngày ISO:

```java
public final class IsoLocalDateFormatter
        implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text);
        } catch (DateTimeParseException ex) {
            ParseException failure =
                new ParseException("Expected ISO date yyyy-MM-dd", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return value.toString();
    }
}
```

Snippet cần import `java.time.LocalDate`, `java.time.format.DateTimeParseException`, `java.text.ParseException` và `java.util.Locale`. `LocalDate.toString()` dùng ISO-8601 nên locale không ảnh hưởng kết quả. Nếu yêu cầu hiển thị ngày bản địa hóa, nên dùng `DateTimeFormatter` phù hợp locale thay vì cố định ISO.

**Khi dùng type-based registration:**

- Mọi field có kiểu phù hợp đều có thể sử dụng formatter.
- Không phân biệt ý nghĩa nghiệp vụ của các field cùng kiểu.
- Cấu hình đơn giản và dễ kiểm thử.
- Nếu một field cần định dạng khác, cân nhắc annotation-based registration hoặc một formatter có điều kiện thay vì làm formatter kiểu chung phức tạp.

## 4. Đăng ký theo annotation: addFormatterForFieldAnnotation

Dùng khi quy tắc định dạng phụ thuộc metadata trên field/property, không chỉ phụ thuộc kiểu Java.

Ví dụ form có hai field kiểu `BigDecimal`: `usdPrice` là số tiền USD, còn `ratio` là tỷ lệ. Nếu chỉ đăng ký một formatter cho `BigDecimal.class`, cả hai đều nhận cùng một cách hiển thị. Annotation cho phép chọn formatter đúng ngữ cảnh.

```java
registry.addFormatterForFieldAnnotation(
    new UsdAmountAnnotationFormatterFactory()
);
```

Factory triển khai `AnnotationFormatterFactory<A>`, với `A` là loại annotation. Factory khai báo:

- `getFieldTypes()`: các kiểu Java mà annotation hỗ trợ.
- `getPrinter(annotation, fieldType)`: printer phù hợp với annotation và kiểu field.
- `getParser(annotation, fieldType)`: parser tương ứng.

Các phương thức trọng tâm có dạng:

```java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();
    Printer<?> getPrinter(A annotation, Class<?> fieldType);
    Parser<?> getParser(A annotation, Class<?> fieldType);
}
```

Đây là chữ ký trọng tâm của SPI Spring. Factory trả về parser/printer tương ứng. Nếu formatter hỗ trợ cả hai chiều, một implementation `Formatter<T>` có thể được trả về cho cả hai phương thức.

### Annotation phải có runtime retention

Factory cần đọc annotation trong runtime, nên annotation phải có `RetentionPolicy.RUNTIME` và target phù hợp:

```java
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface UsdAmount {}
```

Annotation chỉ đánh dấu field nào dùng quy tắc USD; nó không tự thực hiện parse/print. Logic nằm trong `AnnotationFormatterFactory` và formatter mà factory cung cấp.

## 5. Chọn đăng ký theo kiểu hay theo annotation?

| Tiêu chí | Theo kiểu trường | Theo annotation |
| --- | --- | --- |
| API | `addFormatterForFieldType` | `addFormatterForFieldAnnotation` |
| Căn cứ chọn | Kiểu Java của field | Annotation metadata và kiểu field |
| Phù hợp khi | Các field cùng kiểu có quy tắc đồng nhất | Cùng kiểu Java nhưng ý nghĩa/định dạng khác nhau |
| Ví dụ | Mọi `LocalDate` dùng ISO | `@UsdAmount BigDecimal` hiển thị USD |
| Cấu hình | Đơn giản, áp dụng rộng | Tường minh theo field |
| Rủi ro | Quy tắc có thể áp nhầm field cùng kiểu | Quên annotation hoặc khai báo sai kiểu hỗ trợ |

Không nên dùng annotation cho mọi field nếu quy tắc vốn đồng nhất. Ngược lại, khi cùng kiểu Java có ý nghĩa khác nhau, type-based formatter có thể áp quy tắc quá rộng. Có thể đăng ký cả hai cách trong một service: formatter theo kiểu xử lý những trường hợp chung, còn annotation cung cấp ngữ cảnh riêng cho field được đánh dấu.

## 6. FormattingConversionService và TypeDescriptor

`FormattingConversionService` là implementation của ConversionService có tích hợp cơ chế formatting. `DefaultFormattingConversionService` đăng ký sẵn nhiều converter/formatter phổ biến và là điểm khởi đầu thuận tiện.

```java
DefaultFormattingConversionService service =
    new DefaultFormattingConversionService();

service.addFormatterForFieldType(
    LocalDate.class, new IsoLocalDateFormatter()
);
service.addFormatterForFieldAnnotation(
    new UsdAmountAnnotationFormatterFactory()
);
```

Hai cách đăng ký cùng thêm formatter vào một registry/service. Khi convert, Spring dùng kiểu và metadata của vị trí nguồn/đích để chọn quy tắc thích hợp.

### Vì sao TypeDescriptor quan trọng?

Nếu chỉ gọi:

```java
service.convert("$1,234.50", BigDecimal.class);
```

caller chỉ cung cấp kiểu đích `BigDecimal.class`. Spring không biết giá trị đó thuộc field `usdPrice` có annotation `@UsdAmount`. Annotation trên model không thể tự xuất hiện trong một lời gọi chỉ mang class.

Khi binder/MVC chuyển đổi một property cụ thể, Spring có thể cung cấp `TypeDescriptor`. Descriptor mô tả:

- Kiểu Java của field.
- Generic element type hoặc map key/value type nếu có.
- Annotation gắn trên vị trí khai báo.
- Metadata cần thiết cho converter/formatter có điều kiện.

Ví dụ:

```java
Field field = PriceForm.class.getDeclaredField("usdPrice");
TypeDescriptor target = new TypeDescriptor(new Property(field));

Object amount = service.convert(
    "$1,234.50",
    TypeDescriptor.valueOf(String.class),
    target
);
```

Snippet cần import `java.lang.reflect.Field`, `org.springframework.beans.Property` và `org.springframework.core.convert.TypeDescriptor`. Descriptor lấy từ field nên giữ annotation `@UsdAmount`. Đây là khác biệt quyết định giữa conversion theo class và conversion theo metadata khai báo.

**Đừng kỳ vọng** `convert(text, BigDecimal.class)` tự dùng annotation field. Lời gọi đó đã bỏ metadata của field. Dùng overload TypeDescriptor hoặc để DataBinder/MVC thực hiện property conversion khi cần annotation-aware formatting.

## 7. Ví dụ Java 17 chạy được: một formatter theo kiểu và một formatter theo annotation

Chương trình dưới đây dùng Spring Framework 6.1.14 và `DefaultFormattingConversionService`. Nó đăng ký:

- `IsoDateFormatter` cho field kiểu `LocalDate`.
- `UsdAmountFormatterFactory` cho field `BigDecimal` có annotation `@UsdAmount`.

Cấu trúc:

```text
formatter-registration-demo/
├── pom.xml
└── src/main/java/demo/FormatterRegistrationDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-registration-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
```

File `src/main/java/demo/FormatterRegistrationDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Currency;
import java.util.Locale;
import java.util.Set;

import org.springframework.beans.Property;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.AnnotationFormatterFactory;
import org.springframework.format.Formatter;
import org.springframework.format.Printer;
import org.springframework.format.Parser;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class FormatterRegistrationDemo {

    @Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER})
    @Retention(RetentionPolicy.RUNTIME)
    public @interface UsdAmount {}

    public static final class PriceForm {
        private LocalDate deliveryDate;

        @UsdAmount
        private BigDecimal usdPrice;

        public LocalDate getDeliveryDate() {
            return deliveryDate;
        }

        public BigDecimal getUsdPrice() {
            return usdPrice;
        }
    }

    public static final class IsoDateFormatter
            implements Formatter<LocalDate> {

        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {
            try {
                return LocalDate.parse(text);
            } catch (DateTimeParseException ex) {
                ParseException failure =
                    new ParseException("Expected ISO date yyyy-MM-dd", 0);
                failure.initCause(ex);
                throw failure;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return value.toString();
        }
    }

    public static final class UsdAmountFormatter
            implements Formatter<BigDecimal> {

        private NumberFormat createFormat(Locale locale) {
            NumberFormat format =
                NumberFormat.getCurrencyInstance(locale);
            format.setCurrency(Currency.getInstance("USD"));
            if (format instanceof java.text.DecimalFormat decimal) {
                decimal.setParseBigDecimal(true);
            }
            return format;
        }

        @Override
        public BigDecimal parse(String text, Locale locale)
                throws ParseException {
            NumberFormat format = createFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number parsed = format.parse(text, position);

            if (parsed == null
                    || position.getErrorIndex() >= 0
                    || position.getIndex() != text.length()) {
                int errorAt = Math.max(
                    0,
                    Math.max(position.getErrorIndex(), position.getIndex())
                );
                throw new ParseException("Invalid USD amount", errorAt);
            }
            if (parsed instanceof BigDecimal decimal) {
                return decimal;
            }
            return new BigDecimal(parsed.toString());
        }

        @Override
        public String print(BigDecimal value, Locale locale) {
            return createFormat(locale).format(value);
        }
    }

    public static final class UsdAmountFormatterFactory
            implements AnnotationFormatterFactory<UsdAmount> {

        private final Formatter<BigDecimal> formatter =
            new UsdAmountFormatter();

        @Override
        public Set<Class<?>> getFieldTypes() {
            return Set.of(BigDecimal.class);
        }

        @Override
        public Printer<?> getPrinter(
                UsdAmount annotation, Class<?> fieldType) {
            return formatter;
        }

        @Override
        public Parser<?> getParser(
                UsdAmount annotation, Class<?> fieldType) {
            return formatter;
        }
    }

    private static TypeDescriptor field(String name)
            throws NoSuchFieldException {
        Field field = PriceForm.class.getDeclaredField(name);
        return new TypeDescriptor(new Property(field));
    }

    public static void main(String[] args) throws Exception {
        var service = new DefaultFormattingConversionService();

        // Registration theo kiểu trường: mọi LocalDate dùng ISO.
        service.addFormatterForFieldType(
            LocalDate.class, new IsoDateFormatter()
        );

        // Registration theo annotation: field BigDecimal có @UsdAmount.
        service.addFormatterForFieldAnnotation(
            new UsdAmountFormatterFactory()
        );

        TypeDescriptor textType =
            TypeDescriptor.valueOf(String.class);
        TypeDescriptor dateType = field("deliveryDate");
        TypeDescriptor usdType = field("usdPrice");

        LocalDate date = (LocalDate) service.convert(
            "2026-11-02", textType, dateType
        );

        BigDecimal amount = (BigDecimal) service.convert(
            "$1,234.50", textType, usdType
        );

        String dateText = (String) service.convert(
            date, dateType, textType
        );
        String moneyText = (String) service.convert(
            amount, usdType, textType
        );

        System.out.println("date=" + date);
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("dateText=" + dateText);
        System.out.println("moneyText=" + moneyText);
    }
}
```

Chạy từ thư mục có `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FormatterRegistrationDemo
```

Với formatter và `TypeDescriptor` như trên, các dòng chương trình in ra theo `Locale.US` là:

```text
date=2026-11-02
amount=1234.50
dateText=2026-11-02
moneyText=$1,234.50
```

Giải thích:

1. `addFormatterForFieldType(LocalDate.class, ...)` áp dụng formatter ISO cho field `deliveryDate`.
2. Field `usdPrice` có kiểu `BigDecimal` và annotation `@UsdAmount`.
3. `TypeDescriptor` được tạo từ field nên Spring đọc được annotation. Factory chỉ tuyên bố hỗ trợ `BigDecimal.class`.
4. `getParser` và `getPrinter` trả formatter USD cho hai chiều parse/print.
5. Locale US tạo định dạng `$1,234.50`; formatter đặt currency code là USD tường minh.
6. Khi chuyển object lại thành text, descriptor field tiếp tục giúp Spring chọn đúng formatter.

Đây là chương trình Java độc lập, không khởi động Spring MVC. Nó minh họa cơ chế đăng ký và conversion theo TypeDescriptor mà Spring binding cũng có thể sử dụng.

## 8. AnnotationFormatterFactory: thiết kế đúng phạm vi

Factory cần giới hạn field types được hỗ trợ. Ví dụ `UsdAmountFormatterFactory` trả `Set.of(BigDecimal.class)`. Nếu annotation gắn nhầm lên field `String`, factory không tuyên bố hỗ trợ kiểu đó.

Các nguyên tắc:

- Generic annotation parameter `A` phải là annotation thật được gắn trên model.
- `getFieldTypes()` trả các kiểu mà parser/printer có thể xử lý.
- `getPrinter(A annotation, Class<?> fieldType)` chọn printer phù hợp với annotation và field type.
- `getParser(A annotation, Class<?> fieldType)` chọn parser tương ứng.
- Có thể đọc thuộc tính annotation, ví dụ `@DatePattern(pattern = "...")`, để cấu hình formatter theo từng field.
- Formatter thường được dùng ở nhiều request; hãy giữ stateless/thread-safe hoặc tạo đối tượng có trạng thái theo cách an toàn.

Nếu annotation có thuộc tính cấu hình, factory có thể tạo formatter từ chính instance annotation. Không cache một formatter đã cấu hình cho annotation này rồi dùng lại cho annotation khác có pattern/currency khác nếu formatter giữ mutable state.

## 9. Annotation có thuộc tính: pattern ngày riêng

Ví dụ:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface DatePattern {
    String value();
}
```

Factory có thể đọc `annotation.value()` rồi tạo formatter dùng `DateTimeFormatter.ofPattern(pattern, locale)`. Hai field cùng kiểu `LocalDate` khi đó có thể có pattern riêng. Đây là hướng annotation-based khi định dạng khác nhau theo field, trong khi đăng ký `LocalDate.class` chỉ áp một quy tắc chung.

Nên kiểm tra pattern ngay khi khởi tạo cấu hình; pattern sai là lỗi cấu hình, không phải lỗi dữ liệu người dùng. Ngoài ra, Java date/time pattern phân biệt chữ hoa/thường: `M` là tháng, `m` là phút. Cần test parse/print với dữ liệu biên.

## 10. Đăng ký trong Spring MVC

Spring MVC cho phép bổ sung formatter thông qua `FormatterRegistry` trong `WebMvcConfigurer#addFormatters(...)`:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
            LocalDate.class, new IsoDateFormatter()
        );
        registry.addFormatterForFieldAnnotation(
            new UsdAmountFormatterFactory()
        );
    }
}
```

Đoạn code là ví dụ tích hợp trong ứng dụng Spring MVC có dependency web và các class formatter đã định nghĩa.

- `@ModelAttribute` và `WebDataBinder` dùng binding/conversion infrastructure của Spring; formatter phù hợp có thể parse/print field dựa trên metadata property.
- Với annotation-based formatting, conversion call site cần giữ descriptor của field/parameter; không thể chỉ truyền `BigDecimal.class` rồi mong Spring biết field nào có annotation.
- Trong Spring Boot, thường cấu hình qua `WebMvcConfigurer` hoặc cơ chế formatter registry tương ứng, đồng thời để Boot BOM quản lý phiên bản Spring.
- `@RequestBody` JSON thường đi qua `HttpMessageConverter` như Jackson. Spring Formatter registration không tự động thay quy tắc deserialization JSON; Jackson có module/deserializer riêng.
- Formatter hữu ích cho form/query values và render lại giá trị trong giao diện.

## 11. Locale, parse/print và round-trip

Locale ảnh hưởng số, ngày và tiền tệ. Một số nguyên tắc quan trọng:

1. Locale US thường dùng dấu chấm cho phần thập phân và dấu phẩy cho grouping; locale khác có thể đảo quy ước.
2. Currency symbol không đủ để xác định currency code. `$` có thể đại diện nhiều đồng tiền; nếu nghiệp vụ yêu cầu USD, cấu hình USD như trong ví dụ.
3. Parse nên dùng đúng locale mà form đang sử dụng; không nên lấy locale mặc định của server nếu người dùng có locale riêng.
4. Kiểm tra toàn bộ text đã được parse; không chấp nhận một prefix hợp lệ rồi bỏ phần đuôi rác.
5. Với tiền tệ, dùng `BigDecimal` thay vì `double` để tránh sai số biểu diễn nhị phân.
6. Quy tắc scale/rounding thuộc nghiệp vụ. Formatter không nên tự làm tròn số tiền nếu contract không cho phép.
7. `NumberFormat` và `DecimalFormat` không an toàn khi chia sẻ mutable instance giữa nhiều thread; tạo instance riêng cho mỗi thao tác hoặc dùng giải pháp immutable phù hợp.
8. `print(parse(text, locale), locale)` nên tái tạo biểu diễn canonical hoặc ít nhất giữ nguyên giá trị có ý nghĩa.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Formatter theo annotation không chạy | Chỉ truyền `BigDecimal.class` nên thiếu descriptor field | Dùng TypeDescriptor hoặc để DataBinder/MVC xử lý property |
| Annotation không được nhận diện | Factory chưa đăng ký hoặc retention không phải RUNTIME | Đăng ký qua FormatterRegistry và kiểm tra annotation metadata |
| Factory không áp dụng | `getFieldTypes()` không gồm kiểu field | Khai báo đúng kiểu được hỗ trợ |
| Tất cả LocalDate có cùng định dạng ngoài ý muốn | Type-based formatter áp dụng rộng | Dùng annotation nếu field cần quy tắc khác |
| Parse lỗi ở locale khác | Separator/grouping không khớp | Chọn locale đúng và test theo từng locale |
| Symbol `$` không xác định đúng currency | Một symbol dùng cho nhiều đồng tiền | Xác định currency code tường minh |
| Print được nhưng parse thất bại | Hai chiều không đối xứng | Viết test round-trip |
| Chuỗi có đuôi rác vẫn được nhận | Parser không kiểm tra hết input | Kiểm tra ParsePosition/index hoặc toàn chuỗi |
| Lỗi giữa requests | Formatter chia sẻ mutable state không an toàn | Giữ stateless hoặc tạo formatter state an toàn |
| Formatter không chạy trong MVC | Đăng ký nhầm registry/service | Dùng WebMvcConfigurer/MVC registry thực tế |
| Formatter không xử lý JSON như kỳ vọng | JSON được đọc bởi Jackson | Cấu hình Jackson deserializer khi cần |
| Pattern annotation sai | Lỗi cấu hình phát hiện muộn | Validate pattern lúc khởi tạo |

## 13. Quy trình kiểm thử formatter

Với formatter theo kiểu hoặc annotation, nên kiểm tra:

- **Registration:** registry dùng đúng formatter/factory.
- **Parse hợp lệ:** text theo locale tạo đúng object.
- **Parse không hợp lệ:** input sai tạo exception phù hợp, không trả giá trị giả.
- **Print:** object tạo ra chuỗi đúng quy ước locale.
- **Round-trip:** parse sau print giữ nguyên giá trị có ý nghĩa.
- **Annotation scope:** field có annotation dùng formatter đúng; field cùng kiểu không có annotation không bị áp dụng nhầm.
- **Metadata:** conversion với TypeDescriptor giữ annotation/generic metadata cần thiết.
- **Concurrency:** formatter dùng chung không chia sẻ mutable state không an toàn.
- **MVC:** nếu ứng dụng sử dụng web binding, kiểm thử qua `@ModelAttribute` và `WebDataBinder`.

## 14. Câu hỏi tự kiểm tra

1. Khác biệt giữa `Converter<S,T>` và `Formatter<T>` là gì? Vì sao Formatter nhận Locale?
2. Khi nào nên dùng `addFormatterForFieldType` và khi nào nên dùng `addFormatterForFieldAnnotation`?
3. Vì sao `TypeDescriptor` cần thiết để chọn formatter dựa vào annotation của field?
4. `AnnotationFormatterFactory` khai báo các kiểu hỗ trợ ở phương thức nào?
5. Vì sao annotation cần `RetentionPolicy.RUNTIME`?
6. Hai field cùng kiểu `BigDecimal` nhưng một field tiền USD và một field tỷ lệ nên dùng type-based hay annotation-based registration?
7. Vì sao `convert(text, BigDecimal.class)` không tự biết annotation của field?
8. Khi parse số tiền, vì sao nên dùng `BigDecimal` và xác định currency rõ ràng?
9. Spring Formatter registration có tự động tác động lên `@RequestBody` JSON qua Jackson không?
10. Làm sao kiểm thử parse/print round-trip với nhiều Locale?

**Ghi nhớ:** Đăng ký theo kiểu trường áp dụng một Formatter cho mọi field có kiểu tương ứng; đăng ký theo annotation chọn formatter theo metadata của từng field. `TypeDescriptor` mang annotation và generic metadata đến ConversionService. Dùng type-based khi quy tắc đồng nhất; dùng annotation-based khi cùng kiểu Java nhưng ý nghĩa hoặc cách hiển thị khác nhau.

## Tài liệu tham khảo

- Spring Framework — Formatter SPI: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — Registering Formatters: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.1.14 — FormatterRegistry Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/FormatterRegistry.html
- Spring Framework 6.1.14 — AnnotationFormatterFactory Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html
- Spring Framework 6.1.14 — TypeDescriptor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html
- Spring Framework 6.1.14 — FormattingConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html
