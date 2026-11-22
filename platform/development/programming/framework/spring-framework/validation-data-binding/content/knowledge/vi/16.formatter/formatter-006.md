# FormatterRegistry và các cách đăng ký formatter trong Spring Framework

Formatter của Spring chuyển đổi văn bản thành đối tượng Java và in đối tượng trở lại văn bản. Formatter nhận Locale trong cả hai chiều, vì vậy phù hợp với dữ liệu nhập từ giao diện có cách biểu diễn ngày, số và tiền khác nhau giữa các vùng. FormatterRegistry là nơi đăng ký formatter để DataBinder, Spring MVC và ConversionService tìm thấy chúng.

Bài học giải thích các cách đăng ký theo kiểu trường, theo annotation, qua FormatterRegistrar và cấu hình MVC; đồng thời phân biệt Formatter với Converter, hướng dẫn chọn locale, xử lý chuỗi sai định dạng và viết ví dụ Java 17/Spring 6.2.

## 1. Formatter và FormatterRegistry

Giao diện org.springframework.format.Formatter<T> kết hợp hai hợp đồng:

- Parser<T>: parse(String text, Locale locale) đọc văn bản thành đối tượng.
- Printer<T>: print(T object, Locale locale) in đối tượng thành văn bản.

Chữ ký cốt lõi:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

FormatterRegistry thuộc package org.springframework.format và mở rộng ConverterRegistry. Vì vậy, cùng một registry có thể đăng ký formatter và converter.

Các phương thức thường dùng:

```java
public interface FormatterRegistry extends ConverterRegistry {
    void addFormatter(Formatter<?> formatter);

    void addFormatterForFieldType(
            Class<?> fieldType, Formatter<?> formatter);

    void addFormatterForFieldType(
            Class<?> fieldType,
            Printer<?> printer,
            Parser<?> parser);

    void addFormatterForFieldAnnotation(
            AnnotationFormatterFactory<? extends Annotation> factory);
}
```

Ý nghĩa:

| API | Phạm vi |
| --- | --- |
| addFormatter(formatter) | Formatter tự khai báo kiểu đích qua generic Formatter<T> |
| addFormatterForFieldType(type, formatter) | Dùng formatter cho một kiểu trường cụ thể |
| addFormatterForFieldType(type, printer, parser) | Đăng ký riêng phần in và phần đọc cho cùng kiểu |
| addFormatterForFieldAnnotation(factory) | Định dạng field hoặc parameter được đánh dấu annotation |
| addConverter(...) | Đăng ký chuyển đổi kiểu một chiều |

FormatterRegistry là nơi đăng ký. ConversionService là nơi thực hiện conversion/formatting khi có yêu cầu. Một đối tượng như DefaultFormattingConversionService thường triển khai cả hai vai trò.

## 2. Formatter khác Converter như thế nào?

| Tiêu chí | Formatter | Converter |
| --- | --- | --- |
| Hướng chuyển đổi | Văn bản ↔ đối tượng | Kiểu nguồn → kiểu đích |
| Locale | Nhận Locale khi parse và print | Không nhận locale trực tiếp |
| Hợp đồng | parse và print | convert |
| Trường hợp điển hình | Ngày, số, tiền trên form | String sang kiểu miền hoặc giữa hai kiểu Java |

Nếu cần parse và hiển thị dữ liệu văn bản theo locale, dùng Formatter. Nếu chỉ cần một chiều giữa hai kiểu Java, Converter thường đơn giản hơn. Formatter phải có cả hai chiều theo hợp đồng Parser/Printer; Converter chỉ cần một chiều.

## 3. Cách 1: đăng ký trực tiếp theo generic

Khi formatter triển khai Formatter<Price>, có thể đăng ký:

```java
registry.addFormatter(new PriceFormatter());
```

Spring suy ra kiểu đích từ generic đã khai báo. Cách này ngắn gọn khi formatter có một kiểu đích cố định. Không dùng raw type Formatter nếu muốn framework xác định kiểu một cách rõ ràng.

## 4. Cách 2: đăng ký rõ kiểu trường

Khi muốn khai báo tường minh kiểu nhận formatter:

```java
registry.addFormatterForFieldType(
        Price.class, new PriceFormatter());
```

Cách này giúp người đọc cấu hình thấy ngay Price là kiểu được định dạng. Cũng có thể tách thành printer và parser:

```java
registry.addFormatterForFieldType(
        Price.class, pricePrinter, priceParser);
```

Printer và parser phải thống nhất hợp đồng biểu diễn của Price. Parser đọc văn bản thành Price; printer in Price thành chuỗi. Nếu ứng dụng chỉ có một chiều, cân nhắc Converter thay vì tạo formatter không hoàn chỉnh.

## 5. Cách 3: đăng ký theo annotation

Một số field cùng kiểu Java cần kiểu biểu diễn khác nhau. Ví dụ hai field BigDecimal: một field hiển thị dạng phần trăm, field kia hiển thị số thập phân thông thường. Đăng ký theo kiểu trường không phân biệt được hai ngữ cảnh đó.

AnnotationFormatterFactory liên kết annotation với formatter phù hợp. Đăng ký factory bằng:

```java
registry.addFormatterForFieldAnnotation(
        new MoneyFormatAnnotationFormatterFactory());
```

Factory cung cấp formatter cho field/parameter có annotation tương ứng và kiểu dữ liệu tương thích. Nó có thể đọc thuộc tính của annotation để chọn pattern, style hoặc tùy chọn định dạng.

Spring có formatter factory hỗ trợ các annotation phổ biến như @NumberFormat và @DateTimeFormat trong các conversion service mặc định. Nếu mọi field Price đều có cùng cách hiển thị, formatter theo kiểu đơn giản hơn; dùng annotation khi chính sách phụ thuộc từng vị trí sử dụng.

## 6. Cách 4: FormatterRegistrar

FormatterRegistrar cho phép gom nhiều formatter/converter vào một nơi:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

Ví dụ:

```java
public class ApplicationFormatterRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
        registry.addFormatter(new LocalDateFormatter());
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

Registrar hữu ích khi một module có nhiều formatter cần tái sử dụng ở nhiều ứng dụng. Tuy nhiên, tạo object registrar không tự đăng ký nó; cần nối registrar với conversion service hoặc cấu hình MVC thích hợp.

## 7. DefaultFormattingConversionService

DefaultFormattingConversionService là triển khai conversion service có formatter registry và các quy tắc mặc định. Có thể khởi tạo rồi thêm formatter riêng:

```java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();
service.addFormatter(new PriceFormatter());
```

Service mặc định cung cấp các converter/formatter phổ biến. Khi khởi tạo conversion service riêng, cần quyết định có muốn đăng ký các formatter mặc định hay muốn registry tối giản.

FormattingConversionService là nền tảng chung; DefaultFormattingConversionService bổ sung các formatter tiêu chuẩn. Trong ứng dụng Spring, có thể khai báo conversion service như bean nếu cần dùng ở cấp container, nhưng phải nối đúng registry được tầng ứng dụng sử dụng.

## 8. Ví dụ chạy được: PriceFormatter theo locale

Ví dụ dùng Java 17 và Spring Framework 6.2. Kiểu Price lưu BigDecimal. Formatter parse và in số theo locale. Chương trình console kiểm tra trực tiếp formatter và đăng ký vào DefaultFormattingConversionService.

Cấu trúc:

```text
formatter-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/format/FormatterRegistryDemo.java
```

settings.gradle:

```groovy
rootProject.name = 'formatter-registry-demo'
```

build.gradle:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.format.FormatterRegistryDemo'
}
```

Tạo src/main/java/demo/format/FormatterRegistryDemo.java:

```java
package demo.format;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.support.DefaultFormattingConversionService;
import org.springframework.format.Formatter;

public class FormatterRegistryDemo {

    public record Price(BigDecimal amount) {
        public Price {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Price must be non-negative");
            }
        }
    }

    public static final class PriceFormatter implements Formatter<Price> {
        @Override
        public Price parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("Price is required");
            }

            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            if (!(nf instanceof DecimalFormat df)) {
                throw new IllegalStateException(
                        "Expected DecimalFormat");
            }

            df.setParseBigDecimal(true);
            String input = text.trim();
            ParsePosition position = new ParsePosition(0);
            Number parsed = df.parse(input, position);

            if (parsed == null || position.getErrorIndex() >= 0
                    || position.getIndex() != input.length()) {
                throw new IllegalArgumentException(
                        "Invalid price for locale " + locale);
            }

            return new Price((BigDecimal) parsed);
        }

        @Override
        public String print(Price price, Locale locale) {
            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            nf.setMinimumFractionDigits(2);
            nf.setMaximumFractionDigits(2);
            return nf.format(price.amount());
        }
    }

    public static void main(String[] args) {
        PriceFormatter formatter = new PriceFormatter();
        Locale germany = Locale.GERMANY;

        Price parsed = formatter.parse("1.234,50", germany);
        System.out.println("parsed=" + parsed.amount().toPlainString());
        System.out.println("printed=" + formatter.print(parsed, germany));

        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatterForFieldType(Price.class, formatter);

        LocaleContextHolder.setLocale(germany);
        try {
            Price converted = service.convert("2.345,75", Price.class);
            System.out.println("service="
                    + converted.amount().toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }

        try {
            formatter.parse("12,3x", germany);
        } catch (IllegalArgumentException exception) {
            System.out.println("invalid=rejected");
        }
    }
}
```

Chạy từ thư mục dự án:

```bash
gradle -q run
```

Nếu dùng Gradle Wrapper, chạy ./gradlew -q run trên Unix/macOS hoặc gradlew.bat -q run trên Windows.

Stdout của chương trình:

```text
parsed=1234.50
printed=1.234,50
service=2345.75
invalid=rejected
```

Giải thích:

1. Locale.GERMANY dùng dấu chấm phân nhóm và dấu phẩy thập phân.
2. parse đọc chuỗi 1.234,50 thành BigDecimal 1234.50.
3. print tạo lại chuỗi 1.234,50.
4. addFormatterForFieldType đăng ký formatter cho Price.
5. LocaleContextHolder cung cấp locale cho conversion service trong ngữ cảnh hiện tại; finally luôn reset để không rò trạng thái thread.
6. ParsePosition xác nhận toàn bộ chuỗi đã được tiêu thụ. Chuỗi có ký tự dư như 12,3x bị từ chối.

NumberFormat/DecimalFormat được tạo mới trong mỗi lời gọi. Không dùng chung một instance DecimalFormat mutable giữa nhiều thread.

## 9. Đăng ký formatter cho Spring MVC

Cách chuẩn để bổ sung formatter toàn cục cho MVC là triển khai WebMvcConfigurer và override addFormatters:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new PriceFormatter());
        registry.addConverter(new StringToCurrencyCode());
    }
}
```

Đây là cấu hình Java cần các imports và formatter/converter tương ứng. MVC sử dụng registry này trong các luồng conversion và data binding phù hợp.

Trường hợp thường gặp:

- @RequestParam Price price: query parameter được chuyển qua conversion/formatting service.
- @ModelAttribute PaymentForm form: thuộc tính Price có thể được bind bằng formatter.
- Form cần hiển thị lại: printer định dạng object thành văn bản theo locale khi cơ chế rendering sử dụng formatter.

Trong Spring Boot, thường chỉ cần bổ sung WebMvcConfigurer để mở rộng MVC hiện tại. Không thêm @EnableWebMvc chỉ để đăng ký formatter vì annotation này thay đổi cơ chế auto-configuration MVC của Boot.

### 9.1. Dùng FormatterRegistrar với MVC

Nếu có registrar tập hợp các formatter, gọi nó trong addFormatters:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    formatterRegistrar.registerFormatters(registry);
}
```

Đoạn này giả định registrar đã được inject. Tránh đăng ký cùng một formatter qua nhiều cơ chế nếu chúng có thể được gọi song song.

### 9.2. @InitBinder có vai trò gì?

@InitBinder cấu hình WebDataBinder cho một controller hoặc đối tượng được chỉ định. Nó thích hợp khi muốn quy tắc chỉ áp dụng trong phạm vi nhỏ. Với formatter dùng rộng khắp MVC, WebMvcConfigurer.addFormatters thường rõ ràng hơn. Đừng khai báo formatter toàn cục lặp lại trong từng controller.

## 10. Chọn kiểu đăng ký phù hợp

| Nhu cầu | Cách đăng ký |
| --- | --- |
| Mọi field Price cùng một định dạng | addFormatterForFieldType(Price.class, formatter) |
| Formatter tự khai báo Formatter<Price> | addFormatter(formatter) |
| Một số field có định dạng riêng | addFormatterForFieldAnnotation(factory) |
| Nhiều formatter cùng module | FormatterRegistrar |
| Dùng chung query/form MVC | WebMvcConfigurer.addFormatters(...) |
| Chỉ một controller cần binding riêng | @InitBinder |
| Chuyển kiểu Java một chiều, không cần locale | Converter<S,T> |

Đăng ký theo kiểu khi mọi thuộc tính cùng kiểu có chính sách chung. Đăng ký theo annotation khi chính sách phụ thuộc vị trí sử dụng.

## 11. Locale và xử lý lỗi

Formatter nhận locale ở cả parse và print. Trong MVC, locale thường đến từ LocaleResolver/LocaleContextResolver và request context; LocaleContextHolder cung cấp locale hiện hành cho code tích hợp.

Nguyên tắc:

1. Dùng locale request thay vì giả định locale máy chủ.
2. Dùng Locale.ROOT cho chuẩn hóa kỹ thuật không phụ thuộc ngôn ngữ.
3. Không dùng định dạng hiển thị theo locale làm định dạng lưu trữ cố định.
4. Với API machine-to-machine, ưu tiên định dạng chuẩn ổn định khi phù hợp.
5. Parse toàn bộ chuỗi, không chấp nhận phần đầu đúng rồi bỏ ký tự dư.

Formatter có thể từ chối đầu vào sai bằng exception phù hợp. Khi chạy qua data binding, Spring có thể ghi lỗi vào BindingResult để form hiển thị lại thông báo. Không trả stack trace hay giá trị nhạy cảm cho client.

Không bắt mọi exception rồi trả về giá trị mặc định im lặng. Nếu chuỗi abc bị biến thành 0, người dùng không biết dữ liệu sai và ứng dụng có thể xử lý một giá trị ngoài ý định.

## 12. Thread-safety và vòng đời

Formatter thường được đăng ký một lần trong conversion service dùng chung. Vì vậy formatter không nên lưu locale, dữ liệu request hoặc trạng thái mutable theo request trong field.

DecimalFormat và SimpleDateFormat không an toàn khi chia sẻ giữa nhiều thread. Tạo instance theo lời gọi hoặc dùng API thread-safe/immutable. Ví dụ PriceFormatter tạo NumberFormat mới mỗi lần parse/print và dùng locale được truyền vào.

## 13. Kiểm thử FormatterRegistry

| Test | Điều cần xác minh |
| --- | --- |
| Đăng ký generic | Service nhận diện formatter theo kiểu |
| Đăng ký field type | Field đúng kiểu dùng formatter đã đăng ký |
| Đăng ký annotation | Chỉ field có annotation nhận quy tắc riêng |
| Parse hợp lệ | Văn bản tạo đúng object |
| Print | Object được in đúng locale |
| Locale khác nhau | Dấu phân cách phù hợp từng locale |
| Chuỗi rỗng | Đúng chính sách required/empty |
| Ký tự dư | Bị từ chối nếu phải parse toàn bộ |
| Dữ liệu biên | Số âm, quá lớn, ngày không tồn tại |
| MVC integration | Formatter có mặt trong registry MVC thực tế |
| Đa luồng | Không chia sẻ formatter mutable không an toàn |

Unit test có thể tạo DefaultFormattingConversionService, đăng ký formatter và gọi conversion. Integration test MVC nên dùng MockMvc để chứng minh request thực sự đi qua registry của MVC. Chỉ kiểm tra canConvert không đủ chứng minh mọi chuỗi đều parse thành công.

## 14. Lỗi thường gặp

1. Nhầm FormatterRegistry với ConversionService: registry đăng ký, service thực thi.
2. Chỉ triển khai parse mà quên print: Formatter yêu cầu cả hai chiều.
3. Dùng Converter khi cần locale: Converter không nhận locale trực tiếp.
4. Đăng ký sai kiểu đích: Formatter<Price> phải gắn với Price.
5. Tạo bean formatter nhưng quên đăng ký: MVC không nhất thiết tự dùng bean đó.
6. Đăng ký trùng lặp qua nhiều cơ chế: gom trách nhiệm cấu hình.
7. Chia sẻ DecimalFormat giữa request: có nguy cơ race condition.
8. Bỏ qua locale: cùng chuỗi số có thể mang ý nghĩa khác.
9. Chấp nhận chuỗi parse một phần: kiểm tra toàn bộ input.
10. Tưởng formatter MVC tự áp dụng vào Jackson: JSON dùng HttpMessageConverter và cấu hình riêng.
11. Dùng formatter để kiểm tra nghiệp vụ: validator/service vẫn chịu trách nhiệm quy tắc miền.
12. Giả định locale máy chủ luôn là locale của người dùng: dùng locale request.

## 15. Bài tập tự luyện

1. Viết LocalDateFormatter parse và print theo locale; kiểm tra ngày không tồn tại.
2. Đăng ký PriceFormatter bằng addFormatterForFieldType.
3. Viết FormatterRegistrar đăng ký formatter tiền và ngày tháng.
4. Tạo annotation CompactNumber và AnnotationFormatterFactory để một số field có cách hiển thị riêng.
5. Đăng ký formatter trong WebMvcConfigurer.addFormatters và kiểm thử @RequestParam.
6. Chạy cùng giá trị với Locale.US, Locale.GERMANY và vi-VN; giải thích dấu phân cách.
7. Viết test đa luồng để bảo đảm formatter không chia sẻ DecimalFormat mutable.

Bạn nắm vững bài khi giải thích được FormatterRegistry nhận các loại formatter nào, đăng ký theo kiểu khác annotation ra sao, FormatterRegistrar giúp gì và vì sao locale ảnh hưởng parse lẫn print.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework — FormatterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework — Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework — FormatterRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/FormatterRegistrar.html)
- [Spring Framework — AnnotationFormatterFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html)
- [Spring Framework — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
