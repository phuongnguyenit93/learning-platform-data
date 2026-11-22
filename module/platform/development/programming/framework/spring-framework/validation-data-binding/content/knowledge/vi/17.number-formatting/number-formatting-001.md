# @NumberFormat với kiểu số, tiền tệ hoặc phần trăm trong Spring Framework

## 1. @NumberFormat giải quyết vấn đề gì?

Một giá trị số trong Java thường được lưu dưới dạng kiểu máy, chẳng hạn `Integer`, `Long`, `BigDecimal` hoặc `Double`. Khi hiển thị cho người dùng, cùng một giá trị có thể cần nhiều cách viết:

- Số thông thường: `1234567.5` có thể hiển thị thành `1,234,567.5` ở locale Hoa Kỳ hoặc `1.234.567,5` ở nhiều locale châu Âu.
- Tiền tệ: `1234.5` có thể hiển thị thành `$1,234.50`, `1.234,50 €` hoặc một dạng khác tùy locale/currency.
- Phần trăm: giá trị tỷ lệ `0.125` thường hiển thị thành `12.5%`.

Spring cung cấp annotation `org.springframework.format.annotation.NumberFormat` để khai báo **cách trình bày số trên một field/property/parameter**. Formatting infrastructure đọc annotation này và chọn formatter tương ứng để chuyển đổi giữa biểu diễn dạng chuỗi và giá trị kiểu số.

Ví dụ:

```java
public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal total;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal taxRate;
}
```

Với ba property trên, giá trị Java vẫn là số. Annotation chỉ mô tả cách parse/print khi Spring thực hiện conversion trong một context có hỗ trợ field formatting. `@NumberFormat` **không biến field thành String**, không tự thay đổi schema database và cũng không phải validation rule.

## 2. Ba kiểu style: NUMBER, CURRENCY và PERCENT

`NumberFormat.Style` định nghĩa ba lựa chọn chính:

| Style | Mục đích | Formatter của Spring |
| --- | --- | --- |
| `NUMBER` | Số thập phân thông thường, có grouping/decimal separator theo locale | `NumberStyleFormatter` |
| `CURRENCY` | Hiển thị số theo kiểu tiền tệ của locale | `CurrencyStyleFormatter` |
| `PERCENT` | Hiển thị số theo phần trăm | `PercentStyleFormatter` |

Ví dụ với locale Hoa Kỳ và `BigDecimal("1234.5")`:

| Giá trị Java | Style | Dạng hiển thị minh họa |
| --- | --- | --- |
| `1234.5` | `NUMBER` | `1,234.5` |
| `1234.5` | `CURRENCY` | `$1,234.50` |
| `0.125` | `PERCENT` | `12.5%` |

Các kết quả này phụ thuộc locale và quy tắc định dạng của JDK. Locale khác có thể thay dấu nhóm, dấu thập phân, vị trí ký hiệu tiền tệ và khoảng trắng. Không nên hardcode một chuỗi hiển thị tiền tệ làm giá trị nghiệp vụ.

### NUMBER

Dùng cho số đếm, số lượng, điểm số, hệ số hoặc các đại lượng không mang ý nghĩa tiền tệ. Formatter mặc định sử dụng quy tắc number style theo locale. Có thể cấu hình pattern để quyết định số chữ số thập phân, grouping và cách hiển thị.

### CURRENCY

Dùng khi muốn hiển thị giá trị như tiền tệ. `CurrencyStyleFormatter` dựa trên currency formatting của locale, bao gồm ký hiệu, dấu phân cách và số chữ số lẻ theo currency format. Annotation không tự xác định currency nghiệp vụ của tài khoản hay giao dịch; nó dùng quy tắc locale hiện hành trừ khi ứng dụng có cấu hình bổ sung.

**Không dùng currency style như một cơ chế quy đổi tiền.** `BigDecimal("100")` hiển thị thành đơn vị tiền tệ của locale không có nghĩa số 100 đã được chuyển từ USD sang VND hoặc ngược lại. Tỷ giá, currency code và quy tắc làm tròn là logic tiền tệ riêng của domain.

### PERCENT

Dùng cho các tỷ lệ như thuế suất, tỷ lệ hoàn thành, mức chiết khấu hoặc xác suất. Formatter phần trăm thường nhân số tỷ lệ với 100 khi hiển thị và chuyển chuỗi phần trăm về giá trị tỷ lệ khi parse.

Ví dụ `BigDecimal("0.125")` hiển thị thành `12.5%` ở locale Hoa Kỳ. Khi parse `"12.5%"`, giá trị số nhận lại là `0.125` (không phải `12.5`). Hãy lưu ý điều này khi dữ liệu lưu ở database hoặc API dùng tỷ lệ dạng decimal.

## 3. Khai báo annotation và các thuộc tính

Cú pháp cơ bản:

```java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class ProductForm {

    @NumberFormat(style = NumberFormat.Style.NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal price;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;
}
```

`@NumberFormat` có hai thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `style` | Chọn `NUMBER`, `CURRENCY` hoặc `PERCENT` | `NUMBER` |
| `pattern` | Mẫu định dạng số kiểu DecimalFormat | Chuỗi rỗng, tức dùng style |

Có thể viết:

```java
@NumberFormat
private BigDecimal amount;
```

Cách này tương đương dùng `style = NumberFormat.Style.NUMBER` khi không khai báo pattern.

### Pattern được ưu tiên hơn style

Nếu `pattern` khác rỗng, Spring tạo `NumberStyleFormatter(pattern)`. Khi đó pattern là quy tắc trực tiếp, thay cho formatter mặc định được chọn bằng `style`.

Ví dụ:

```java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal unitPrice;

@NumberFormat(pattern = "0.000")
private BigDecimal exchangeFactor;
```

Pattern `#,##0.00` yêu cầu grouping và hai chữ số thập phân; `0.000` yêu cầu ba chữ số thập phân. Pattern dựa trên cú pháp của `DecimalFormat`. Pattern này không tự thêm currency code, không xác định tỷ giá và cũng không validate business range.

Không nên ghi cả `style = CURRENCY` và một pattern tùy ý rồi mong Spring tự kết hợp hai quy tắc. Với pattern được khai báo, formatter pattern được sử dụng. Nếu cần biểu diễn tiền tệ có quy tắc riêng, hãy thiết kế pattern/formatter phù hợp hoặc dùng mô hình tiền tệ có currency rõ ràng.

## 4. @NumberFormat được Spring xử lý như thế nào?

Annotation không tự chạy. Formatting infrastructure phải được cấu hình và sử dụng trong đường conversion phù hợp.

Trong Spring, `NumberFormatAnnotationFormatterFactory` là thành phần kết nối annotation `@NumberFormat` với các formatter. Factory cung cấp hỗ trợ cho các kiểu số thường dùng như:

- `Short`, `Integer`, `Long`.
- `Float`, `Double`.
- `BigDecimal`, `BigInteger`.

Factory đọc annotation:

1. Nếu `pattern` không rỗng, tạo `NumberStyleFormatter(pattern)`.
2. Nếu không có pattern và style là `PERCENT`, tạo `PercentStyleFormatter`.
3. Nếu style là `CURRENCY`, tạo `CurrencyStyleFormatter`.
4. Trường hợp còn lại dùng `NumberStyleFormatter`.

`DefaultFormattingConversionService` đăng ký formatter factory cho `@NumberFormat` trong bộ mặc định. Spring MVC cũng cài đặt các formatter số phổ biến và hỗ trợ annotation này trong conversion/formatting infrastructure.

Luồng:

```text
String từ form/request hoặc Number trong model
                    |
                    v
     FormattingConversionService
                    |
                    v
       đọc TypeDescriptor/property
                    |
                    v
       phát hiện @NumberFormat
                    |
                    v
 NumberFormatAnnotationFormatterFactory
                    |
          +---------+---------+
          |         |         |
          v         v         v
        NUMBER   CURRENCY   PERCENT
          |         |         |
          v         v         v
      NumberStyle CurrencyStyle PercentStyle
       Formatter    Formatter   Formatter
          |         |         |
          +---------+---------+
                    |
                    v
       parse String <-> Number
                    |
                    v
        property / view / form
```

`TypeDescriptor` giúp Spring biết annotation nằm trên property/parameter nào và kiểu số cụ thể là gì. Chỉ gọi formatter theo raw class mà không có metadata property thì không thể kỳ vọng Spring biết nên lấy annotation từ field nào.

## 5. Locale ảnh hưởng đến kết quả

Format số là thao tác phụ thuộc locale. Cùng giá trị Java `1234.5` có thể được biểu diễn khác nhau:

| Locale | Number ví dụ | Currency ví dụ |
| --- | --- | --- |
| `en-US` | `1,234.5` | `$1,234.50` |
| `de-DE` | `1.234,5` | dạng EUR theo quy tắc Đức |
| `vi-VN` | quy tắc dấu số Việt Nam | dạng VND theo quy tắc Việt Nam |

Bảng chỉ minh họa khác biệt locale, không phải hợp đồng chuỗi cố định cho mọi JDK/CLDR version. Cần dùng locale của request/người dùng và test trên môi trường triển khai.

Trong Spring, formatter nhận `Locale` khi parse/print. Web request có thể dùng locale resolver/interceptor để xác định locale hiện tại. Ở code không có web context, có thể cung cấp locale khi gọi trực tiếp formatter hoặc thiết lập `LocaleContextHolder` cho conversion flow phù hợp.

Ví dụ trong Spring MVC:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Có thể đăng ký Formatter/Converter tùy ứng dụng.
    }
}
```

Đây là cấu hình mở rộng khi cần custom behavior. Với `@NumberFormat` thông thường, Spring MVC đã cung cấp hỗ trợ mặc định trong formatting conversion service; không cần tự đăng ký lại formatter factory ở mọi controller.

**Locale không phải currency setting.** Locale quyết định quy tắc hiển thị theo vùng/ngôn ngữ, trong đó có currency format mặc định. Với ứng dụng tài chính hỗ trợ nhiều currency, phải lưu currency code riêng (ví dụ ISO 4217) và không suy ra currency giao dịch chỉ từ locale của người dùng.

## 6. Ví dụ Java 17+ chạy được: định dạng ba kiểu số

Ví dụ sử dụng Spring Framework 6.2.x, Java 17+ và Maven. Nó dùng `DefaultFormattingConversionService` để minh họa annotation trên property được sử dụng cho cả hai chiều format và parse. Để kết quả dễ dự đoán, ví dụ đặt locale là `Locale.US` trong lúc chạy.

### 6.1. Maven dependency

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>number-format-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` kéo theo Spring Core/Beans cần thiết cho formatting service. Ví dụ không cần Spring Boot hay server HTTP.

### 6.2. Java class đầy đủ

Tạo file `src/main/java/demo/NumberFormatDemo.java`:

```java
package demo;

import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.context.i18n.LocaleContextHolder;

public class NumberFormatDemo {

    public static class Invoice {
        @NumberFormat(style = NumberFormat.Style.NUMBER)
        private BigDecimal quantity = new BigDecimal("1234.5");

        @NumberFormat(style = NumberFormat.Style.CURRENCY)
        private BigDecimal amount = new BigDecimal("1234.5");

        @NumberFormat(style = NumberFormat.Style.PERCENT)
        private BigDecimal taxRate = new BigDecimal("0.125");
    }

    private static String print(
            DefaultFormattingConversionService service,
            Invoice invoice,
            String fieldName) throws NoSuchFieldException {

        Field field = Invoice.class.getDeclaredField(fieldName);
        TypeDescriptor descriptor = new TypeDescriptor(field);
        BigDecimal value = (BigDecimal) descriptor.getType()
                .cast(readValue(invoice, fieldName));

        return (String) service.convert(
                value,
                descriptor,
                TypeDescriptor.valueOf(String.class));
    }

    private static Object readValue(
            Invoice invoice, String fieldName) {
        return switch (fieldName) {
            case "quantity" -> invoice.quantity;
            case "amount" -> invoice.amount;
            case "taxRate" -> invoice.taxRate;
            default -> throw new IllegalArgumentException(fieldName);
        };
    }

    private static BigDecimal parse(
            DefaultFormattingConversionService service,
            String fieldName,
            String text) throws NoSuchFieldException {

        Field field = Invoice.class.getDeclaredField(fieldName);
        TypeDescriptor target = new TypeDescriptor(field);

        return (BigDecimal) service.convert(
                text,
                TypeDescriptor.valueOf(String.class),
                target);
    }

    public static void main(String[] args) throws Exception {
        LocaleContextHolder.setLocale(Locale.US);
        try {
            DefaultFormattingConversionService service =
                    new DefaultFormattingConversionService();
            Invoice invoice = new Invoice();

            String number = print(service, invoice, "quantity");
            String currency = print(service, invoice, "amount");
            String percent = print(service, invoice, "taxRate");

            System.out.println("number=" + number);
            System.out.println("currency=" + currency);
            System.out.println("percent=" + percent);

            System.out.println("parsedAmount="
                    + parse(service, "amount", currency).toPlainString());
            System.out.println("parsedRate="
                    + parse(service, "taxRate", percent).toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Trong đoạn demo, `TypeDescriptor` được tạo từ chính field có annotation. Khi convert từ BigDecimal sang String, Spring nhìn annotation trên source property descriptor và chọn formatter phù hợp. Khi parse String về BigDecimal, descriptor của field đích cung cấp annotation cho parser.

### 6.3. Biên dịch, chạy và output

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.NumberFormatDemo
```

Với Spring 6.2.x, JDK 17+ và locale `en-US`, kết quả dự kiến từ chương trình là:

```text
number=1,234.5
currency=$1,234.50
percent=12.5%
parsedAmount=1234.50
parsedRate=0.125
```

Giải thích:

- `quantity` dùng NUMBER, do đó format nhóm hàng nghìn và dấu thập phân.
- `amount` dùng CURRENCY, hiển thị ký hiệu tiền tệ và hai chữ số lẻ của USD theo locale Hoa Kỳ.
- `taxRate` lưu `0.125`, khi in ra biểu diễn thành `12.5%`.
- Parse ngược currency string cho ra `BigDecimal`, không biến thành String nghiệp vụ.
- Parse phần trăm `12.5%` trả tỷ lệ `0.125`.

Ví dụ chủ động dùng `BigDecimal` để giữ precision thập phân. Với bài toán tiền tệ, tránh dùng `double` cho giá trị cần tính toán chính xác.

## 7. Dùng @NumberFormat trong Spring MVC form

Trong Spring MVC, các request parameter dạng chuỗi được bind vào model attribute. Formatting conversion infrastructure đọc `@NumberFormat` trên property để parse giá trị và format lại khi render form/view.

Ví dụ model:

```java
package demo.web;

import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class PriceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal unitPrice;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public BigDecimal getDiscountRate() { return discountRate; }
    public void setDiscountRate(BigDecimal discountRate) {
        this.discountRate = discountRate;
    }
}
```

Controller:

```java
@Controller
public class PriceController {

    @PostMapping("/price")
    public String submit(
            @Valid @ModelAttribute("priceForm") PriceForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "price-form";
        }
        return "price-result";
    }
}
```

Đây là mẫu controller cần import Spring MVC, Jakarta Validation nếu dùng `@Valid`, và view tương ứng. `BindingResult` phải đứng ngay sau tham số model attribute để nhận lỗi bind/validation. Không cần tự gọi `NumberFormatAnnotationFormatterFactory` trong controller; infrastructure mặc định đã xử lý annotation.

Một form field được gửi dạng chuỗi theo locale đang sử dụng. Nếu locale là en-US, input currency có thể ở dạng `$1,234.50`; với locale khác, dấu phân cách và ký hiệu có thể khác. Form nên render giá trị theo cùng locale mà server dùng để parse. Nếu client gửi chuỗi theo locale khác locale request, parse có thể thất bại.

### Render giá trị trong view

Với template engine, có thể hiển thị trực tiếp property đã được format theo integration tương ứng hoặc dùng formatter/conversion service của view. Cách cụ thể phụ thuộc Thymeleaf, JSP, FreeMarker hay template engine đang dùng. Không giả định mọi expression engine tự gọi `@NumberFormat` chỉ vì model property có annotation; xác minh integration và cách render của framework/view technology.

## 8. Khi nào chọn pattern thay vì style?

Dùng style khi quy tắc chuẩn theo locale là đủ. Dùng pattern nếu yêu cầu hiển thị cần quy định số chữ số hoặc grouping cụ thể.

Ví dụ:

```java
@NumberFormat(pattern = "#,##0")
private BigDecimal wholeUnits;

@NumberFormat(pattern = "#,##0.000")
private BigDecimal preciseRate;

@NumberFormat(pattern = "0.00")
private BigDecimal shortDisplay;
```

Một số pattern thường gặp:

| Pattern | Ý nghĩa |
| --- | --- |
| `#,##0` | Số nguyên có grouping |
| `#,##0.00` | Hai chữ số thập phân |
| `0.000` | Ba chữ số thập phân, không grouping bắt buộc |
| `#,##0.###` | Tối đa ba chữ số thập phân |
| `000000` | Đệm số 0 bên trái đến sáu chữ số |

Pattern được diễn giải bởi `DecimalFormat`, nên các ký tự như `0`, `#`, dấu nhóm và dấu thập phân có ý nghĩa riêng. Dấu phân cách thực tế vẫn phụ thuộc locale khi formatter tạo format instance.

**Pattern không phải regex và không phải validation annotation.** Pattern kiểm soát cách parse/print số. Để yêu cầu giá trị trong khoảng, dùng Bean Validation như `@DecimalMin`/`@DecimalMax` hoặc kiểm tra nghiệp vụ ở service.

## 9. @NumberFormat hỗ trợ những kiểu số nào?

Factory mặc định của Spring hỗ trợ các wrapper/number types thường gặp như `Short`, `Integer`, `Long`, `Float`, `Double`, `BigDecimal` và `BigInteger`. Các kiểu primitive có thể được hỗ trợ thông qua primitive/wrapper handling của conversion framework, nhưng khi giá trị có thể null, wrapper/reference type thường rõ ràng hơn.

Không nên giả định annotation áp dụng trực tiếp cho mọi kiểu tự định nghĩa, chẳng hạn `Money` hoặc `Quantity`, chỉ vì kiểu ấy chứa một `BigDecimal` bên trong. Với domain type riêng, cần viết `Formatter`/`Converter` phù hợp hoặc dùng một property số thực tế để annotation xử lý.

Với tiền tệ, `BigDecimal` thích hợp cho giá trị decimal, nhưng không mang theo currency code. Một class như `Money(amount, currency)` biểu diễn domain đầy đủ hơn. Formatter chuyên biệt có thể cần đọc currency code thay vì chỉ dùng currency mặc định của locale.

## 10. @NumberFormat khác @Digits, @DecimalMin và validation

Đây là điểm dễ nhầm:

| Annotation | Vai trò |
| --- | --- |
| `@NumberFormat` | Quy tắc format/parse số |
| `@Digits(integer=..., fraction=...)` | Giới hạn số chữ số integer/fraction trong validation |
| `@DecimalMin("0.01")` | Giá trị tối thiểu theo validation |
| `@DecimalMax("100")` | Giá trị tối đa theo validation |
| `@Positive` / `@PositiveOrZero` | Điều kiện dấu của giá trị |
| `@NotNull` | Bắt buộc có giá trị |

Có thể kết hợp:

```java
@NumberFormat(style = NumberFormat.Style.CURRENCY)
@NotNull
@DecimalMin("0.01")
private BigDecimal price;
```

`@NumberFormat` chuyển đổi cách viết; các annotation validation kiểm tra giá trị sau binding. Để validation hoạt động cần Jakarta Bean Validation provider và cơ chế kích hoạt như `@Valid`/`@Validated` phù hợp. Chỉ thêm `@NumberFormat` không làm giá trị âm bị từ chối hay biến chuỗi rỗng thành lỗi nghiệp vụ.

## 11. Đăng ký formatter tùy chỉnh

Khi ba style mặc định không đủ, có thể đăng ký `Formatter<Number>` hoặc `Converter` trong `FormatterRegistry`.

Ví dụ cấu hình MVC:

```java
@Configuration
public class NumberFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                BigDecimal.class, new CustomMoneyFormatter());
    }
}
```

Đây là snippet cần class `CustomMoneyFormatter` của ứng dụng và imports tương ứng. Nó đăng ký formatter cho field type BigDecimal ở registry này; nếu có nhiều BigDecimal property với quy tắc khác nhau, formatter toàn kiểu có thể quá rộng. Có thể cân nhắc annotation-specific `AnnotationFormatterFactory` hoặc một domain type riêng.

`DefaultFormattingConversionService` là một lựa chọn cho code ngoài MVC; `FormattingConversionService` trong MVC được cấu hình trong application context. Tạo formatter service cục bộ không khiến Spring MVC tự động sử dụng instance đó.

## 12. Precision, rounding và tiền tệ

Một số lưu ý khi xử lý tiền:

- Dùng `BigDecimal` thay cho `double`/`float` trong tính toán cần độ chính xác thập phân.
- Khởi tạo từ chuỗi, ví dụ `new BigDecimal("19.95")`, thay vì `new BigDecimal(19.95)` để tránh mang sai số nhị phân của double vào decimal.
- Phân biệt giá trị lưu trữ với cách hiển thị: hiển thị hai chữ số không có nghĩa giá trị bên trong đã được làm tròn/ghi lại hai chữ số.
- Xác định chính sách rounding tại business/service hoặc tầng tiền tệ, không dựa vào việc format text.
- Lưu currency code cùng amount khi domain có nhiều loại tiền.
- Không cộng/trừ trực tiếp các amount thuộc currency khác nhau nếu chưa quy đổi theo chính sách nghiệp vụ.
- Kiểm tra giới hạn scale/precision của database và cách serialize API.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("19.955");
BigDecimal rounded = amount.setScale(
        2, RoundingMode.HALF_UP);
```

Đây là phép làm tròn dữ liệu thực sự. Nó khác với việc chỉ hiển thị `19.955` thành một chuỗi có hai chữ số qua formatter. Hãy chọn rounding mode rõ ràng theo quy định nghiệp vụ và loại currency; không có một cách làm tròn duy nhất phù hợp mọi hệ thống.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Annotation không ảnh hưởng hiển thị | Conversion service không có NumberFormat formatter factory hoặc không dùng property TypeDescriptor | Dùng FormattingConversionService phù hợp; kiểm tra descriptor |
| `@NumberFormat` bị xem như validation | Nhầm format với kiểm tra giá trị | Dùng Bean Validation cho range/digit constraints |
| Parse được ở máy này, lỗi ở máy khác | Locale khác nhau | Xác định locale request/test rõ ràng |
| Currency symbol không như mong muốn | Locale đang dùng có currency mặc định khác | Quản lý currency code nghiệp vụ riêng |
| Percent hiển thị lớn hơn 100 lần mong đợi | Lưu `12.5` thay vì tỷ lệ `0.125` | Thống nhất contract lưu decimal ratio |
| Decimal separator sai | Chuỗi nhập theo locale khác | Đồng bộ locale form và server |
| Mất precision sau parse | Dùng Float/Double hoặc tự parse bằng double | Dùng BigDecimal/formatter thích hợp |
| Pattern không có tác dụng như style mong muốn | Pattern khác rỗng được ưu tiên hơn style | Chọn một quy tắc chủ đạo |
| Chuỗi rỗng cho ra null | Conversion/editor có thể map empty input sang null | Kiểm tra required validation riêng |
| @RequestBody JSON không dùng annotation như form | JSON đi qua Jackson HttpMessageConverter | Cấu hình Jackson khi cần format JSON |
| canConvert/format trực tiếp khác với MVC | Khác locale/context hoặc descriptor | Test qua đúng MVC request path |
| Annotation trên field không được tìm thấy | Conversion gọi bằng class-only overload, thiếu property descriptor | Truyền TypeDescriptor của field/parameter |

### Quy trình debug

1. Xem kiểu Java thật của property và annotation trên field/getter/parameter.
2. Xác định conversion path có đi qua FormattingConversionService không.
3. Kiểm tra TypeDescriptor có giữ annotation không.
4. Xác định Locale hiện hành của request.
5. Thử print và parse riêng với dữ liệu có dấu phân cách, ký hiệu currency và percent.
6. Kiểm tra BindingResult khi bind form; phân biệt type mismatch với validation failure.
7. Kiểm tra JSON converter riêng nếu lỗi chỉ xảy ra với @RequestBody.

## 14. Kiểm thử có ý nghĩa

Một bộ test nên bao phủ:

| Test | Giá trị | Điều cần xác nhận |
| --- | --- | --- |
| NUMBER format | `1234.5` | Grouping/decimal separator theo locale |
| CURRENCY format | `1234.5` | Symbol và decimal digits theo locale |
| PERCENT format | `0.125` | In ra 12.5%, parse trở lại 0.125 |
| Custom pattern | `1234.5678` | Số chữ số hiển thị theo pattern |
| Locale thay đổi | en-US và de-DE | Dấu phân cách/format khác nhau |
| Invalid input | `"abc"` | Binding/conversion error |
| Validation range | số âm khi có @DecimalMin | Binding có thể thành công, validation thất bại |
| BigDecimal precision | chuỗi decimal dài | Không mất precision ngoài ý muốn |

Khi test locale, đặt locale rõ ràng rồi khôi phục context sau test; đừng để locale của một test ảnh hưởng test kế tiếp. Với Spring MVC, nên có MockMvc integration test để xác nhận request parameter parse theo locale đã cấu hình.

## 15. Checklist sử dụng trong dự án

1. Chọn kiểu số phù hợp: Integer/Long cho số nguyên; BigDecimal cho decimal và tiền.
2. Chọn style NUMBER, CURRENCY hoặc PERCENT đúng ý nghĩa property.
3. Nếu cần format đặc thù, khai báo pattern và nhớ pattern được ưu tiên.
4. Xác định locale của request/người dùng; không giả định locale máy chủ là locale nghiệp vụ.
5. Giữ tỷ lệ phần trăm dạng decimal thống nhất, ví dụ 0.125 cho 12.5%.
6. Với currency đa quốc gia, lưu amount và currency code riêng.
7. Xác nhận FormattingConversionService được sử dụng trong MVC hoặc code path thực tế.
8. Dùng validation riêng cho required/range/precision.
9. Test format và parse hai chiều trên các locale hỗ trợ.
10. Không dựa vào chuỗi hiển thị để thực hiện phép tính hoặc quy đổi tiền.

## 16. Ghi nhớ

`@NumberFormat` khai báo cách Spring **parse/print kiểu số** trong formatting conversion. `NUMBER` dùng number style, `CURRENCY` dùng currency style và `PERCENT` dùng percent style. Nếu pattern không rỗng, formatter theo pattern được tạo thay cho style formatter mặc định. Kết quả phụ thuộc locale; percent là tỷ lệ decimal khi lưu, còn currency style không tự quy đổi hay xác định currency code nghiệp vụ.

Annotation có tác dụng khi dữ liệu đi qua formatting infrastructure với metadata property phù hợp. Trong Spring MVC, các formatter số mặc định và hỗ trợ `@NumberFormat` đã được cài sẵn. Khi kiểm tra range, số chữ số hoặc giá trị bắt buộc, dùng Bean Validation; khi xử lý tiền, dùng BigDecimal, currency code và rounding policy rõ ràng.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [NumberFormat API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [NumberFormatAnnotationFormatterFactory API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/NumberFormatAnnotationFormatterFactory.html)
- [NumberStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html)
- [CurrencyStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html)
- [PercentStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/PercentStyleFormatter.html)
- [DefaultFormattingConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
