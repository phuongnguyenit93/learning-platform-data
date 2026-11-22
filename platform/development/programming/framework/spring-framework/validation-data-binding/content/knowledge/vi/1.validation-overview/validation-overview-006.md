# Quan hệ giữa ConversionService, Converter và Formatter trong Spring Framework

## 1. Bài toán và ý tưởng cốt lõi

Dữ liệu đi vào ứng dụng thường ở dạng chuỗi: tham số URL `?page=3`, path variable `/orders/42`, giá trị nhập vào form `04/11/2026`. Trong Java, đối tượng đích lại có kiểu `Integer`, `OrderId`, `LocalDate`, `BigDecimal`... Spring cần biến dữ liệu nguồn sang đúng kiểu trước khi gán vào thuộc tính hoặc truyền vào phương thức.

Ba thành phần liên quan nhưng có trách nhiệm khác nhau:

- **`ConversionService`**: giao diện thống nhất để *yêu cầu* chuyển từ kiểu nguồn sang kiểu đích; bên gọi không cần biết quy tắc chuyển đổi nào được chọn.
- **`Converter<S, T>`**: một *quy tắc* chuyển đổi kiểu từ `S` sang `T`, thường chỉ theo một chiều và không nhận `Locale`.
- **`Formatter<T>`**: một cặp quy tắc *parse* `String → T` và *print* `T → String`, có tham số `Locale` để phục vụ dữ liệu người dùng nhập và hiển thị theo vùng/ngôn ngữ.

Điểm nối quan trọng: **`FormattingConversionService` vừa là `ConversionService`, vừa là `FormatterRegistry`**. Nó đăng ký `Converter` và `Formatter` vào cùng hệ thống chuyển đổi. Vì vậy mã sử dụng có thể vẫn gọi `conversionService.convert(...)`, trong khi Spring tự chọn bộ chuyển đổi hoặc parser/printer phù hợp.

## 2. Vai trò và API của từng thành phần

### 2.1. ConversionService: điểm truy cập chung

Giao diện thuộc `org.springframework.core.convert.ConversionService`. Hai thao tác thường dùng:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
```

Đây là **trích đoạn chữ ký API**, không phải một chương trình Java độc lập. Các overload khác nhận `TypeDescriptor` để mang thông tin kiểu cụ thể, generic và annotation của nguồn/đích.

Ví dụ, `convert("42", Integer.class)` có thể dùng converter sẵn có; `convert("42", OrderId.class)` cần quy tắc riêng nếu Spring chưa biết `OrderId` là gì. `canConvert(...)` cho biết dịch vụ có đường chuyển đổi tương ứng theo thông tin kiểu được cung cấp, chứ không bảo đảm mọi giá trị đầu vào đều hợp lệ: `"abc"` vẫn có thể gây lỗi khi parse thành số.

`ConversionService` chỉ là **hợp đồng đọc/thi hành**. Việc đăng ký converter thuộc `ConverterRegistry`; do đó không thể gọi `addConverter(...)` trên một biến chỉ có kiểu tĩnh `ConversionService`. Những lớp cụ thể như `GenericConversionService` hay `DefaultFormattingConversionService` cung cấp API đăng ký.

### 2.2. Converter<S, T>: quy tắc chuyển đổi tổng quát

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Ví dụ nghiệp vụ: `String → OrderId`, `String → ProductCode` hoặc `Long → Instant`. `Converter` chỉ có một phương thức; không mặc nhiên sinh chiều ngược lại. Nếu cần `OrderId → String` với một quy tắc riêng, hãy đăng ký chiều ngược tương ứng hoặc dùng cách khác phù hợp.

`Converter` phù hợp khi cách chuyển đổi **không phụ thuộc cách trình bày theo ngôn ngữ/vùng**. Chẳng hạn, chuẩn hóa mã định danh, parse mã kỹ thuật, ánh xạ từ một value object sang một value object khác. Tránh dùng `Converter` để hard-code cách đọc số tiền/ngày tháng phụ thuộc `Locale` của từng người dùng.

Có các SPI linh hoạt hơn như `ConverterFactory` (họ nhiều kiểu đích) và `GenericConverter`/`ConditionalGenericConverter` (cần `TypeDescriptor` hoặc điều kiện áp dụng), nhưng đa số quy tắc một cặp kiểu chỉ cần `Converter<S, T>`.

### 2.3. Formatter<T>: parse và print theo Locale

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}

// Các phương thức do hai interface cha khai báo:
String print(T object, java.util.Locale locale);
T parse(String text, java.util.Locale locale)
        throws java.text.ParseException;
```

Đây là **mô tả rút gọn các chữ ký**, không phải nguyên một tệp Java. `Formatter<T>` kế thừa hai interface có phương thức như trên; không tự khai báo trực tiếp hai phương thức.

- `parse`: đọc chuỗi người dùng nhập thành giá trị Java, ví dụ `"04/11/2026" → LocalDate` theo quy ước ngày/tháng/năm.
- `print`: xuất giá trị Java thành chuỗi dùng cho form/giao diện, ví dụ `LocalDate → "04/11/2026"`.
- `locale`: quyết định quy tắc biểu diễn, như dấu phân cách số, thứ tự ngày/tháng/năm, ký hiệu tiền tệ. Một `Formatter` có thể dùng `Locale` để chọn cách biểu diễn khác nhau cho `vi-VN` và `en-US`.

`Formatter` đặc biệt hữu ích ở lớp giao tiếp người dùng. Cần bảo đảm `parse`/`print` nhất quán với nhau cho cùng locale, xử lý giá trị sai rõ ràng và triển khai thread-safe vì formatter thường được chia sẻ giữa nhiều request.

## 3. Cách ba thành phần phối hợp

```text
Dữ liệu nguồn (ví dụ một String từ request)
           |
           v
Spring MVC / DataBinder / lời gọi convert(...)
           |
           v
ConversionService  [giao diện gọi chung]
           |
           v
FormattingConversionService  [triển khai + registry]
           |
           +--> Converter<S,T>           : chuyển kiểu không cần Locale
           |
           +--> Formatter<T>.parse(...)  : String -> T, có Locale
           |
           +--> Formatter<T>.print(...)  : T -> String, có Locale
           |
           v
Giá trị có kiểu đích / chuỗi để hiển thị
```

Khi đăng ký một `Formatter<T>` vào `FormattingConversionService`, Spring bọc chức năng parser/printer thành các đường chuyển đổi thích hợp và đặt chúng trong cơ chế chọn converter chung. Đối tượng gọi `ConversionService` không cần tự quyết định gọi `parse` hay `print`.

Phân biệt các triển khai thường gặp:

| Thành phần | Vai trò | Nhận Converter | Nhận Formatter |
| --- | --- | --- | --- |
| `ConversionService` | API yêu cầu chuyển kiểu | Không có API đăng ký | Không có API đăng ký |
| `GenericConversionService` | Bộ máy chuyển đổi và registry | Có | Không trực tiếp triển khai `FormatterRegistry` |
| `DefaultConversionService` | `GenericConversionService` có bộ converter mặc định | Có | Không trực tiếp |
| `FormattingConversionService` | Bộ máy chuyển đổi có `FormatterRegistry` | Có | Có |
| `DefaultFormattingConversionService` | `FormattingConversionService` cài sẵn các converter/formatter thông dụng | Có | Có |

Lưu ý: `FormatterRegistry extends ConverterRegistry`; vì thế `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` có thể đăng ký cả `registry.addConverter(...)` và `registry.addFormatter(...)`.

## 4. So sánh để chọn đúng công cụ

| Tiêu chí | Converter<S,T> | Formatter<T> |
| --- | --- | --- |
| Hướng | Một chiều `S → T` | Hai chiều `String ↔ T` |
| API chính | `convert(S)` | `parse(String, Locale)`, `print(T, Locale)` |
| Locale | Không truyền trực tiếp | Có |
| Bài toán điển hình | `String → OrderId`, mã nghiệp vụ | Ngày, số, tiền và cách nhập/hiển thị theo locale |
| Đăng ký | `ConverterRegistry.addConverter` | `FormatterRegistry.addFormatter` / `addFormatterForFieldType` |
| Sử dụng từ code gọi | Qua `ConversionService.convert` | Qua `FormattingConversionService.convert` hoặc binder dùng dịch vụ đó |

Không phải cứ có nguồn là `String` thì phải dùng `Formatter`. Nếu `String` là mã kỹ thuật có cú pháp cố định, một `Converter<String, T>` đơn giản có thể là lựa chọn rõ ràng nhất. Ngược lại, ngày/tiền mà người dùng nhìn thấy thường cần formatter hoặc cơ chế định dạng theo annotation.

## 5. Ví dụ chạy được với Java 17 và Spring Framework 6.2.3

Ví dụ sau dùng **cả Converter và Formatter trong cùng một ConversionService**. `OrderId` là mã nghiệp vụ không phụ thuộc locale. `LocalDate` có hai quy ước định dạng minh họa: `vi` dùng `dd/MM/uuuu`, locale khác dùng `MM/dd/uuuu`.

Tạo cấu trúc:

```text
conversion-demo/
├── pom.xml
└── src/main/java/demo/ConversionDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.3</version>
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
                    <mainClass>demo.ConversionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ConversionDemo.java`:**

```java
package demo;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;

public class ConversionDemo {

    record OrderId(long value) {
        OrderId {
            if (value <= 0) {
                throw new IllegalArgumentException("OrderId must be positive");
            }
        }
    }

    static final class StringToOrderId implements Converter<String, OrderId> {
        @Override
        public OrderId convert(String source) {
            return new OrderId(Long.parseLong(source.trim()));
        }
    }

    static final class LocalDateFormatter implements Formatter<LocalDate> {
        private DateTimeFormatter patternFor(Locale locale) {
            String pattern = locale.getLanguage().equals("vi")
                    ? "dd/MM/uuuu"
                    : "MM/dd/uuuu";
            return DateTimeFormatter.ofPattern(pattern, locale)
                    .withResolverStyle(ResolverStyle.STRICT);
        }

        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text.trim(), patternFor(locale));
        }

        @Override
        public String print(LocalDate object, Locale locale) {
            return object.format(patternFor(locale));
        }
    }

    public static void main(String[] args) {
        var service = new DefaultFormattingConversionService();

        service.addConverter(new StringToOrderId());
        service.addFormatterForFieldType(
                LocalDate.class, new LocalDateFormatter());

        LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
        try {
            System.out.println(
                    service.canConvert(String.class, OrderId.class));
            System.out.println(service.convert(" 42 ", OrderId.class));
            System.out.println(
                    service.convert("04/11/2026", LocalDate.class));
            System.out.println(
                    service.convert(LocalDate.of(2026, 11, 4), String.class));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Tại thư mục `conversion-demo`, cần JDK 17+ và Maven. Chạy:

```bash
mvn -q compile exec:java
```

**Stdout của chương trình:**

```text
true
OrderId[value=42]
2026-11-04
04/11/2026
```

Giải thích:

1. `addConverter` khai báo cách biến một `String` thành `OrderId`. `" 42 "` được `trim()` rồi parse thành `long`; `record` được in bằng `toString()` mặc định.
2. `addFormatterForFieldType(LocalDate.class, ...)` đăng ký cả chiều `String → LocalDate` và `LocalDate → String`. Trong ví dụ, nó được thêm sau bộ formatter mặc định để áp dụng quy ước riêng cho `LocalDate`.
3. `LocaleContextHolder.setLocale(...)` đặt locale cho luồng hiện tại; adapter của Spring dùng locale ngữ cảnh khi gọi `Formatter` từ `FormattingConversionService`. `finally` khôi phục ngữ cảnh, tránh làm rò locale qua tác vụ khác.
4. `dd/MM/uuuu` cộng `ResolverStyle.STRICT` ngăn ngày lịch không hợp lệ như `31/02/2026`. Đây là quy ước **minh họa**; ứng dụng thực tế nên quyết định chính sách locale/format theo sản phẩm và tránh tự ý thay định dạng đã công bố cho API.
5. `service` được khai báo là lớp triển khai để đăng ký quy tắc. Sau khi cấu hình, mã nghiệp vụ có thể nhận nó dưới kiểu `ConversionService` và chỉ gọi `convert`.

Nếu đổi locale sang `en-US` trong ví dụ, formatter sẽ hiểu/hiển thị ngày theo `MM/dd/uuuu`. `Converter<String, OrderId>` không đổi hành vi theo locale. Việc chuyển `"abc"` sang `OrderId` hoặc `"31/02/2026"` sang `LocalDate` gây lỗi chuyển đổi; `canConvert` có thể vẫn là `true` vì đường chuyển đổi đã được đăng ký.

## 6. Ứng dụng trong Spring MVC và Data Binding

Luồng điển hình cho query, path variable hoặc form:

1. Spring nhận giá trị từ HTTP dưới dạng chuỗi (hoặc tập chuỗi).
2. Spring MVC/`WebDataBinder` tra cấu hình chuyển đổi phù hợp với kiểu tham số/field.
3. `ConversionService` lựa chọn converter hoặc parser từ formatter đã đăng ký.
4. Nếu chuyển đổi thành công, giá trị có kiểu được đưa vào tham số controller hoặc đối tượng `@ModelAttribute`.
5. Nếu có validation, quá trình kiểm tra ràng buộc xảy ra trên dữ liệu đã được bind; lỗi chuyển kiểu và lỗi validation là hai nhóm vấn đề khác nhau.

Đăng ký dùng chung cho việc định dạng/chuyển kiểu ở Spring MVC:

```java
// Đoạn cấu hình minh họa cho ứng dụng có spring-webmvc.
// Hai lớp converter/formatter được định nghĩa tương tự ví dụ mục 5.
@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderId());
        registry.addFormatterForFieldType(
                LocalDate.class, new LocalDateFormatter());
    }
}
```

Các import tương ứng là `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` và `org.springframework.format.FormatterRegistry`. Đoạn trên **minh họa phần cấu hình**, không phải tệp chạy độc lập; đặt các lớp do bạn viết trong cùng package hoặc import chúng từ module của ứng dụng. Trong Spring Boot MVC, có thể triển khai `WebMvcConfigurer` bằng bean `@Configuration`; Spring MVC sẽ dùng các quy tắc đã đăng ký trong ngữ cảnh MVC.

Ví dụ, nếu ứng dụng khai báo `@PathVariable OrderId id` và đã đăng ký `Converter<String, OrderId>` phù hợp, chuỗi `"42"` từ đường dẫn có thể được chuyển thành `OrderId` trước khi controller thực thi. Với `@ModelAttribute` chứa `LocalDate`, formatter có thể xử lý chuỗi ngày từ form. Khi xuất dữ liệu trở lại biểu mẫu, chiều `print` cung cấp chuỗi theo locale.

**Quan trọng về annotation:** `@DateTimeFormat` và `@NumberFormat` gắn quy tắc định dạng lên field/parameter. Spring sử dụng `AnnotationFormatterFactory` và thông tin kiểu/annotation khi binder có đủ ngữ cảnh. Một lệnh gọi trực tiếp `convert("04/11/2026", LocalDate.class)` chỉ truyền hai `Class`, nên không tự mang annotation của một field bất kỳ. Khi cần tôn trọng annotation trong chuyển đổi programmatic phức tạp, hãy xem overload dùng `TypeDescriptor`.

**Phân biệt với JSON:** `@RequestBody` nhận JSON thường được giải mã qua `HttpMessageConverter` (ví dụ Jackson), với cấu hình serialization/deserialization của nó. Không nên mặc định cho rằng đăng ký `Formatter` trong MVC sẽ thay đổi cách Jackson đọc ngày trong JSON.

**Phân biệt với validation:** `Converter`/`Formatter` chịu trách nhiệm tạo ra giá trị đúng kiểu; `Validator`/Bean Validation như `@NotNull`, `@Min` kiểm tra tính hợp lệ theo nghiệp vụ. Sai cú pháp như `"not-a-date"` có thể tạo lỗi binding/type mismatch trước khi một ràng buộc nghiệp vụ có cơ hội kiểm tra giá trị `LocalDate`. Với form `@ModelAttribute`, `BindingResult` giúp controller kiểm tra lỗi bind/validate nếu được khai báo đúng vị trí.

## 7. Đăng ký ở đâu và điều gì cần chú ý?

- **Trong code độc lập:** tạo `DefaultFormattingConversionService`, đăng ký quy tắc rồi đưa nó vào các thành phần cần chuyển đổi.
- **Trong Spring MVC:** sử dụng `WebMvcConfigurer.addFormatters(FormatterRegistry)` hoặc cấu hình MVC tương ứng để đăng ký quy tắc phục vụ các trường hợp MVC. `FormatterRegistry` chấp nhận cả converter lẫn formatter.
- **Trong Spring container nói chung:** có thể cấu hình `ConversionService` làm bean thích hợp (trong các tình huống được Spring tích hợp); cần xác định subsystem nào thật sự dùng bean đó. Không giả định MVC, Spring Boot property binding, JSON/Jackson và mọi bean trong ứng dụng đều dùng một registry.
- **Theo field/annotation:** ưu tiên `@DateTimeFormat`, `@NumberFormat` hoặc `AnnotationFormatterFactory` khi format thay đổi theo field, thay vì cài một quy tắc toàn cục tác động đến tất cả các field cùng kiểu.

Khi nhiều quy tắc cùng xử lý một cặp kiểu (ví dụ converter `String → LocalDate` và formatter `LocalDate`), chúng có thể cạnh tranh hoặc làm luồng khó dự đoán. Hãy chọn một chiến lược rõ ràng, đăng ký có chủ đích và kiểm thử đường chuyển đổi thực tế, đặc biệt với `Locale` và annotation.

## 8. Các lỗi và ngộ nhận thường gặp

| Nhầm lẫn / lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “`ConversionService` chính là một converter” | Trộn lẫn API gọi với quy tắc chuyển đổi | Xem `ConversionService` là façade và `Converter` là thành phần được registry sử dụng |
| Dùng `Converter<String, LocalDate>` hard-code `dd/MM` cho mọi người dùng | Ngày `04/05` bị hiểu khác kỳ vọng ở locale khác | Dùng `Formatter` hoặc annotation định dạng phù hợp |
| Tưởng `Converter<S,T>` tự hỗ trợ chiều `T → S` | Kết xuất ngược thiếu đường chuyển đổi | Đăng ký quy tắc ngược riêng, hoặc dùng `Formatter<T>` cho tình huống hiển thị |
| Tưởng `canConvert == true` bảo đảm input hợp lệ | Vẫn lỗi khi parse giá trị cụ thể | Kiểm thử giá trị biên, bắt lỗi ở lớp nhận request, phản hồi lỗi rõ ràng |
| Dùng formatter mutable dùng chung nhiều luồng | Race condition, kết quả format sai | Dùng formatter immutable như `DateTimeFormatter`; tránh chia sẻ `SimpleDateFormat` mutable |
| Quên ngữ cảnh `Locale` hoặc không reset sau khi tự đặt | Hiển thị lệch locale/ảnh hưởng request khác | Lấy locale từ request hoặc sử dụng `LocaleContextHolder` đúng phạm vi |
| Thay đổi global formatter cho `LocalDate` mà không khảo sát field khác | Ảnh hưởng nhiều form/parameter | Ưu tiên annotation ở field hoặc thu hẹp cấu hình |
| Mong `Formatter` của MVC xử lý `@RequestBody` JSON | Ngày trong JSON không đổi | Cấu hình Jackson/`HttpMessageConverter` tương ứng |
| Xem parse error như lỗi validation nghiệp vụ | Xử lý lỗi/sửa thông báo không đúng chỗ | Tách lỗi chuyển kiểu khi binding và lỗi từ `Validator` |

Các trường hợp nên thử khi QA: giá trị hợp lệ, chuỗi rỗng/khoảng trắng, ngày lịch không tồn tại, số âm nếu domain không cho phép, locale `vi-VN` và `en-US`, đường chuyển đổi ngược, cùng một kiểu có nhiều annotation. Với chuỗi rỗng/null, cách binder và converter mặc định xử lý còn tùy kiểu đích và cấu hình; cần xác định chính sách cụ thể trước khi tự trả `null` hay tạo giá trị mặc định.

## 9. Tự kiểm tra mức hiểu

1. Nếu hệ thống cần biến `"ORD-42"` thành một value object `OrderId` độc lập ngôn ngữ, nên viết gì? **`Converter<String, OrderId>`**.
2. Nếu một field tiền cần hiển thị `1.234,50` hoặc `1,234.50` tùy locale, cần khả năng gì? **`Formatter`/formatter theo annotation**, có `parse` và `print` dựa trên `Locale`.
3. Đối tượng nào để code controller hoặc binder gọi chuyển đổi thống nhất? **`ConversionService`**.
4. Thành phần nào cho phép đăng ký cả `Converter` và `Formatter`? **`FormatterRegistry`**, được triển khai bởi `FormattingConversionService`.
5. Có `canConvert(String.class, LocalDate.class) == true` thì `"31/02/2026"` có hợp lệ không? **Không**; kiểm tra khả năng tồn tại đường chuyển đổi khác với xác thực giá trị cụ thể.

**Ghi nhớ:** `ConversionService` là *cửa gọi*, `Converter` là *luật chuyển kiểu*, `Formatter` là *luật đọc/ghi chuỗi theo locale*. `FormattingConversionService` kết hợp cả hai loại luật, giúp Spring Data Binding và Spring MVC sử dụng một cơ chế chuyển đổi nhất quán.

## 10. Tài liệu chính thức để tra cứu sâu

- Spring Framework — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `Converter` và registry.
- Spring Framework — [Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `FormatterRegistry`, `FormattingConversionService`.
- Spring Framework MVC — [Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký qua `WebMvcConfigurer.addFormatters`.
- Spring Framework MVC — [Controller Method Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): tham số controller và lỗi chuyển kiểu.