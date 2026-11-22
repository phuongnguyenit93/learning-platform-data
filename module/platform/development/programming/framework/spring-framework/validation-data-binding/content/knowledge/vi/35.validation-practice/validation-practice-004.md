# Viết converter cho mã nghiệp vụ và formatter theo Locale

## Mục tiêu và bài toán

Trong Spring MVC, giá trị từ URL, query string và form thường bắt đầu là `String`. Tầng nghiệp vụ không nên phải tự cắt, chuẩn hóa, kiểm mã hay đoán dấu phân cách thập phân ở mọi controller. Bài thực hành thuộc module Spring Framework — validation-data-binding sẽ xây dựng:

1. `Converter<String, ProductCode>` biến `" abc-0042 "` thành domain value `ProductCode("ABC-0042")`, kiểm mẫu ba chữ cái Latin và bốn chữ số. Mã định danh **không phụ thuộc Locale**.
2. `Converter<ProductCode, String>` để in mã trong Spring form thay vì `toString()` mặc định của record.
3. `Formatter<MoneyAmount>` để parse và print `BigDecimal` theo request `Locale`. Ví dụ `1.234,50` với `vi-VN` và `1,234.50` với `en-US` là cùng giá trị `1234.50`.
4. `WebMvcConfigurer.addFormatters` để đăng ký các thành phần vào Spring MVC `FormattingConversionService`.
5. REST controller nhận `@PathVariable ProductCode` và `@RequestParam MoneyAmount`, form Thymeleaf dùng `@ModelAttribute`/`BindingResult`, và bộ kiểm thử JUnit/MockMvc.
6. Phân biệt lỗi chuyển kiểu với Bean Validation, và phân biệt MVC conversion với JSON `@RequestBody` qua Jackson.

Bài có một Maven project đầy đủ cho **Java 17+ và Spring Boot 3.5.7**. Có thể dùng JDK mới hơn, nhưng khi nâng cấp Spring/Boot phải kiểm tài liệu của đúng version.

### Vì sao không tiếp tục dùng String và double?

Một request:

~~~http
GET /api/quotes?code=abc-0042&amount=1.234,50
Accept-Language: vi-VN
~~~

có hai chuỗi mang ngữ nghĩa khác nhau: `code` là định danh máy đọc và `amount` là một số được trình bày theo ngôn ngữ/vùng. Nếu xử lý cả hai bằng cách nối chuỗi hoặc `Double.parseDouble` thì code có thể thiếu invariant, số có thể sai dấu thập phân và phép tính tiền có thể bị sai số nhị phân.

Thiết kế mục tiêu:

~~~text
HTTP "abc-0042"
  → ProductCodeConverter.convert(...)
  → ProductCode("ABC-0042")      [Locale.ROOT]

HTTP "1.234,50" + vi-VN
  → MoneyAmountFormatter.parse(...)
  → MoneyAmount(BigDecimal 1234.50)
  → Bean Validation / business rules

MoneyAmount(1234.50) + en-US
  → MoneyAmountFormatter.print(...)
  → "1,234.50"
~~~

### Quy ước của demo

| Phần | Quy ước |
| --- | --- |
| Business code | `AAA-0000`, ba chữ `A-Z`, dấu `-`, bốn chữ số ASCII |
| Chuẩn hóa | Strip khoảng trắng hai đầu, uppercase với `Locale.ROOT` |
| Amount | `BigDecimal` với scale 2, không rounding ngầm |
| Locale Việt Nam | `1.234,50` |
| Locale Hoa Kỳ | `1,234.50` |
| Input form hợp lệ | Amount tối thiểu 0,01 và tối đa tám chữ số phần nguyên |
| Dữ liệu trả API | Chuỗi decimal canonical `1234.50` không phụ thuộc Locale |
| Lỗi | Parser/Converter không đổi được → binding error hoặc HTTP 400 |

**Locale không đồng nghĩa currency.** Cùng một số USD có thể được hiển thị theo vi-VN hoặc en-US. Nếu hỗ trợ nhiều đồng tiền, cần mô hình hóa `Currency` riêng, không dự đoán currency từ Locale.

## 1. Converter khác Formatter như thế nào?

### 1.1. Converter<S,T> không có Locale

`org.springframework.core.convert.converter.Converter<S,T>` chỉ có một phương thức:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Đây là chữ ký minh họa, không cần tự tạo interface này. Converter rất hợp để chuyển một chuỗi định danh thành domain type với quy tắc **cố định**. Không dùng `source.toUpperCase()` phụ thuộc default JVM Locale khi mã theo ASCII: trong một số ngôn ngữ như tiếng Thổ Nhĩ Kỳ, chữ `i` có quy tắc uppercasing khác. Dùng:

~~~java
source.strip().toUpperCase(Locale.ROOT)
~~~

để chuẩn hóa định danh độc lập với ngôn ngữ người dùng.

### 1.2. Formatter<T> có hai chiều và Locale

`org.springframework.format.Formatter<T>` kết hợp `Printer<T>` và `Parser<T>`:

~~~java
public interface Printer<T> {
    String print(T value, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException;
}

public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

Đây cũng là sơ đồ chữ ký, không phải source cần biên dịch. `parse` đọc input localized; `print` in domain value để hiển thị. Vì vậy một formatter có thể được gọi khi **nhận** form hoặc khi **render** form, không chỉ khi parser được gọi thủ công.

### 1.3. ConversionService và phạm vi hoạt động

`ConversionService` là giao diện chuyển đổi kiểu của Spring; `FormattingConversionService` bổ sung formatting. Spring MVC có conversion service dùng để bind query, path và form. Spring Boot có conversion service khác dành cho `application.properties`/`application.yaml`. Không giả định đăng ký ở một chỗ sẽ tự áp dụng cho mọi chỗ.

| Nơi dùng | Có đi qua MVC converter/formatter? |
| --- | --- |
| `@PathVariable ProductCode` | Có |
| `@RequestParam MoneyAmount` | Có |
| `@ModelAttribute OfferForm.amount` | Có, qua WebDataBinder |
| Thymeleaf `th:field="*{amount}"` | Có, qua Spring-aware form binding |
| `@RequestBody JSON` | Không theo pipeline trên; Jackson xử lý |
| JSON `@ResponseBody` | Không tự dùng mọi MVC formatter để serialize |
| `@ConfigurationProperties` | Conversion service dành cho cấu hình Boot, khác MVC |

Một **Converter** chỉ có chiều String→domain, không tự sinh ra domain→String. Đối với form, ta đăng ký chiều in `ProductCode→String` tường minh.

## 2. Tổ chức project

~~~text
business-code-locale-format/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/formatdemo/
    │   │   ├── Application.java
    │   │   ├── ProductCode.java
    │   │   ├── ProductCodeConverter.java
    │   │   ├── ProductCodeToStringConverter.java
    │   │   ├── MoneyAmount.java
    │   │   ├── MoneyAmountFormatter.java
    │   │   ├── WebFormatConfiguration.java
    │   │   ├── QuoteController.java
    │   │   ├── OfferForm.java
    │   │   ├── OfferPageController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/offers/
    │           ├── form.html
    │           └── success.html
    └── test/java/com/example/formatdemo/
        ├── ProductCodeConverterTest.java
        ├── MoneyAmountFormatterTest.java
        ├── QuoteMvcTest.java
        └── OfferFormMvcTest.java
~~~

Các file Java dùng chung package `com.example.formatdemo`. Không cần database hay external API; ví dụ tách chuyển đổi/validation khỏi logic persistence.

### 2.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>business-code-locale-format</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` cung cấp Spring MVC/Jackson, Thymeleaf starter cung cấp Spring form binding, Validation starter cung cấp Jakarta Bean Validation, test starter có MockMvc/JUnit. Boot parent quản lý Spring Framework versions tương thích; không ép riêng một Spring JAR khác BOM nếu chưa đánh giá.

### 2.2. Application.java

~~~java
package com.example.formatdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 2.3. ProductCode.java

~~~java
package com.example.formatdemo;

import java.util.Objects;
import java.util.regex.Pattern;

public record ProductCode(String value) {

    private static final Pattern FORMAT =
            Pattern.compile("[A-Z]{3}-[0-9]{4}");

    public ProductCode {
        Objects.requireNonNull(value, "code is required");

        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Product code must be AAA-0000");
        }
    }
}
~~~

Canonical record constructor bảo vệ invariant của miền: kể cả code nội bộ tạo trực tiếp `new ProductCode("ABC-42")`, giá trị sai cũng bị từ chối. Converter chuẩn hóa trước khi gọi constructor; không copy regex ở controller/service.

### 2.4. ProductCodeConverter.java

~~~java
package com.example.formatdemo;

import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {

        String canonical =
                source.strip().toUpperCase(Locale.ROOT);

        if (canonical.isEmpty()) {
            throw new IllegalArgumentException(
                    "Product code is required");
        }

        return new ProductCode(canonical);
    }
}
~~~

`strip()` loại khoảng trắng hai đầu. `Locale.ROOT` bảo đảm kết quả máy đọc ổn định khi HTTP Accept-Language/JVM locale đổi. Converter không truy vấn database, không có side effects và không quyết định quyền truy cập. Nếu source là null, Spring ConversionService thường xử lý null trước khi gọi converter; demo không thiết kế việc gọi trực tiếp `convert(null)`.

### 2.5. ProductCodeToStringConverter.java

~~~java
package com.example.formatdemo;

import org.springframework.core.convert.converter.Converter;

public final class ProductCodeToStringConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

Chiều ngược giúp `th:field="*{productCode}"` in `ABC-0042` thay vì record `toString()` kiểu `ProductCode[value=ABC-0042]`.

### 2.6. MoneyAmount.java

~~~java
package com.example.formatdemo;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record MoneyAmount(
        @DecimalMin("0.01")
        @Digits(integer = 8, fraction = 2)
        BigDecimal value) {

    public MoneyAmount {
        Objects.requireNonNull(value, "amount is required");
        value = value.setScale(
                2, RoundingMode.UNNECESSARY);
    }
}
~~~

`BigDecimal` lưu số thập phân chính xác. Constructor bắt buộc scale 2 và **không làm tròn âm thầm**. `@DecimalMin` và `@Digits` là Bean Validation constraints: chúng được kiểm sau binding khi có `@Valid` phù hợp, không phải mọi lần constructor được gọi. Một `MoneyAmount(-1.00)` có thể parse thành công nhưng vi phạm `@DecimalMin` ở form.

### 2.7. MoneyAmountFormatter.java

~~~java
package com.example.formatdemo;

import org.springframework.format.Formatter;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public final class MoneyAmountFormatter
        implements Formatter<MoneyAmount> {

    @Override
    public MoneyAmount parse(String text, Locale locale)
            throws ParseException {

        String input = text.strip();

        if (input.isEmpty()) {
            throw new ParseException(
                    "Amount must not be empty", 0);
        }

        NumberFormat format =
                NumberFormat.getNumberInstance(locale);

        if (!(format instanceof DecimalFormat decimal)) {
            throw new ParseException(
                    "Unsupported number format", 0);
        }

        decimal.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = decimal.parse(input, position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getErrorIndex() >= 0
                || position.getIndex() != input.length()) {
            throw new ParseException(
                    "Invalid localized amount",
                    Math.max(0, position.getIndex()));
        }

        try {
            return new MoneyAmount(amount);
        } catch (ArithmeticException ex) {
            throw new ParseException(
                    "Amount must have at most two decimals",
                    position.getIndex());
        }
    }

    @Override
    public String print(MoneyAmount object, Locale locale) {
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);

        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(
                RoundingMode.UNNECESSARY);

        return format.format(object.value());
    }
}
~~~

**Phân tích `parse`:**

- `NumberFormat.getNumberInstance(locale)` tạo parser phù hợp với request locale.
- `DecimalFormat.setParseBigDecimal(true)` bảo đảm kết quả là `BigDecimal`, không đi qua `doubleValue()` có thể làm mất chính xác.
- `ParsePosition` kiểm toàn bộ input đã được tiêu thụ. `NumberFormat.parse(String)` một mình có thể nhận phần đầu hợp lệ rồi bỏ qua suffix: `1,234.50oops` không được xem là hợp lệ.
- Constructor `MoneyAmount` bảo vệ scale; nếu có quá hai fraction digits có ý nghĩa sẽ báo `ArithmeticException`, được đổi thành `ParseException`.
- Parser không tự quyết định amount có được phép âm hay không; đó là constraint/domain policy.

**Phân tích `print`:**

- Mỗi lần tạo NumberFormat mới. `DecimalFormat` mutable và không thread-safe nếu dùng chung instance singleton giữa requests.
- Bật grouping và hai fraction digits; `vi-VN`/`en-US` quyết định dấu phân cách.
- `RoundingMode.UNNECESSARY` tránh làm tròn ngoài ý muốn vì MoneyAmount đã chuẩn hóa scale.

**Giới hạn:** `DecimalFormat` có thể khá khoan dung với grouping separators. Điều kiện parse hết chuỗi **không bảo đảm grouping grammar luôn nghiêm ngặt**. Một chuỗi đúng với locale này có thể được hiểu thành một giá trị khác ở locale kia. Với dữ liệu tài chính nhạy cảm, hãy công bố rõ locale input, thêm strict grammar validation, giới hạn độ dài và dùng canonical data format khi phù hợp.

### 2.8. WebFormatConfiguration.java

~~~java
package com.example.formatdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormatConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(
            FormatterRegistry registry) {

        registry.addConverter(
                new ProductCodeConverter());

        registry.addConverter(
                new ProductCodeToStringConverter());

        registry.addFormatter(
                new MoneyAmountFormatter());
    }
}
~~~

Đăng ký cho **Spring MVC**. Không thêm `@EnableWebMvc` trong Spring Boot chỉ để đăng ký converter: điều đó có thể làm mất Boot MVC auto-configuration. Nếu có nhiều formatter cần dependency injection, có thể dùng Spring beans hoặc `FormatterRegistrar`; với pure value converter, tạo object trực tiếp trong registry rất dễ hiểu.

### 2.9. QuoteController.java

~~~java
package com.example.formatdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {

    public record ProductView(String code) {
    }

    public record QuoteView(
            String code, String amount) {
    }

    @GetMapping("/api/products/{code}")
    public ProductView product(
            @PathVariable("code") ProductCode code) {

        return new ProductView(code.value());
    }

    @GetMapping("/api/quotes")
    public QuoteView quote(
            @RequestParam("code") ProductCode code,
            @RequestParam("amount") MoneyAmount amount) {

        return new QuoteView(
                code.value(),
                amount.value().toPlainString());
    }
}
~~~

Đây là Spring MVC argument conversion **thật**, không tự gọi converter trong controller. JSON trả số amount dưới dạng chuỗi decimal canonical `"1234.50"` để consumer máy không cần đoán Locale. Nếu chọn JSON number thay vì string, phải định nghĩa schema/precision policy rõ ràng cho JS clients.

### 2.10. OfferForm.java

~~~java
package com.example.formatdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public class OfferForm {

    @NotNull
    private ProductCode productCode;

    @NotNull
    @Valid
    private MoneyAmount amount;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }

    public MoneyAmount getAmount() {
        return amount;
    }

    public void setAmount(MoneyAmount amount) {
        this.amount = amount;
    }
}
~~~

`@Valid` trên MoneyAmount là cần thiết để `@DecimalMin` và `@Digits` trên `MoneyAmount.value` được kiểm tra. `@NotNull` riêng chỉ bảo đảm form field không null, không tự cascade.

### 2.11. OfferPageController.java

~~~java
package com.example.formatdemo;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

import java.math.BigDecimal;

@Controller
public class OfferPageController {

    @GetMapping("/offers/new")
    public String showForm(Model model) {
        OfferForm form = new OfferForm();

        form.setProductCode(
                new ProductCode("ABC-1234"));

        form.setAmount(new MoneyAmount(
                new BigDecimal("1234.50")));

        model.addAttribute("offerForm", form);
        return "offers/form";
    }

    @PostMapping(
            path = "/offers/new",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public String submit(
            @Valid @ModelAttribute("offerForm") OfferForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            return "offers/form";
        }

        model.addAttribute(
                "code", form.getProductCode().value());

        model.addAttribute(
                "canonicalAmount",
                form.getAmount().value().toPlainString());

        return "offers/success";
    }
}
~~~

`BindingResult` đặt **ngay sau** `@ModelAttribute`. Khi conversion hoặc validation thất bại, controller render lại form và Spring giữ errors trong model. Demo trả success view trực tiếp; trong sản phẩm thật có thể dùng POST/Redirect/GET và chính sách CSRF để tránh double submit.

### 2.12. ApiErrorAdvice.java

~~~java
package com.example.formatdemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(
            MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> invalidParameter(
            MethodArgumentTypeMismatchException ex) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.BAD_REQUEST,
                        "A path or query value is invalid.");

        body.setTitle("Invalid parameter");
        body.setProperty("code", "INVALID_PARAMETER");

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

REST path/query không đổi được kiểu thường dẫn tới `MethodArgumentTypeMismatchException` và HTTP 400. Advice chỉ đưa mã lỗi an toàn, không xuất raw rejected input/exception internals. Form có `BindingResult` nên không cần ném cùng loại exception để render field errors.

### 2.13. application.properties

~~~properties
server.port=8080
spring.thymeleaf.cache=false
server.error.include-message=never
~~~

Tắt template cache chỉ để dễ chỉnh code khi học; production có thể bật. Không cần cấu hình conversion service riêng dành cho Boot properties.

### 2.14. templates/offers/form.html

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Offer editor</title>
</head>
<body>
<h1>Edit offer</h1>

<form th:action="@{/offers/new}"
      th:object="${offerForm}"
      method="post">

    <label for="productCode">Product code</label>
    <input type="text" th:field="*{productCode}">

    <label for="amount">Amount</label>
    <input type="text" th:field="*{amount}">

    <ul th:if="${#fields.hasAnyErrors()}">
        <li th:each="error : ${#fields.allErrors()}"
            th:text="${error}">Invalid value</li>
    </ul>

    <button type="submit">Save</button>
</form>
</body>
</html>
~~~

Khi GET form với `Accept-Language: vi-VN`, `th:field` dùng Formatter.print để hiển thị amount `1.234,50`; với `en-US`, hiển thị `1,234.50`. Reverse ProductCode converter in `ABC-1234`. Form cố ý dùng input `type="text"` vì HTML `type="number"` có quy ước browser riêng, không mặc định nhận cùng localized string.

### 2.15. templates/offers/success.html

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Offer accepted</title>
</head>
<body>
<h1>Offer accepted</h1>
<p>Product: <strong th:text="${code}">ABC-1234</strong></p>
<p>Canonical amount:
    <strong th:text="${canonicalAmount}">1234.50</strong>
</p>
<a th:href="@{/offers/new}">New offer</a>
</body>
</html>
~~~

Success view dùng canonical amount để người học phân biệt dữ liệu máy với chuỗi localized của form.

## 3. Chạy thử và HTTP output

Từ thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

### 3.1. Mã nghiệp vụ trong URL

~~~bash
curl -i "http://localhost:8080/api/products/abc-0042"
~~~

Kết quả HTTP 200:

~~~json
{"code":"ABC-0042"}
~~~

Nếu gọi `/api/products/abc-42`, converter/record từ chối mã sai; advice tạo HTTP 400 với `"code":"INVALID_PARAMETER"`.

### 3.2. Số tiền theo Locale Việt Nam

~~~bash
curl -i \
  -H "Accept-Language: vi-VN" \
  "http://localhost:8080/api/quotes?code=abc-0042&amount=1.234,50"
~~~

HTTP 200:

~~~json
{
  "code": "ABC-0042",
  "amount": "1234.50"
}
~~~

### 3.3. Số tiền theo Locale Hoa Kỳ

~~~bash
curl -i \
  -H "Accept-Language: en-US" \
  "http://localhost:8080/api/quotes?code=abc-0042&amount=1,234.50"
~~~

HTTP 200 với **cùng** JSON canonical:

~~~json
{
  "code": "ABC-0042",
  "amount": "1234.50"
}
~~~

### 3.4. Hiển thị và gửi form

~~~bash
curl -s -H "Accept-Language: vi-VN" \
  "http://localhost:8080/offers/new"
~~~

Input amount trong HTML có giá trị `1.234,50`; khi dùng en-US nó là `1,234.50`.

~~~bash
curl -i -X POST "http://localhost:8080/offers/new" \
  -H "Accept-Language: vi-VN" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "productCode=abc-0042" \
  --data-urlencode "amount=1.234,50"
~~~

Success view hiển thị product code `ABC-0042` và canonical amount `1234.50`. Input `1.234,50oops` được ghi thành lỗi binding thay vì tạo offer.

## 4. Unit tests: ProductCodeConverter

File `src/test/java/com/example/formatdemo/ProductCodeConverterTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class ProductCodeConverterTest {

    private final ProductCodeConverter incoming =
            new ProductCodeConverter();

    private final ProductCodeToStringConverter outgoing =
            new ProductCodeToStringConverter();

    @Test
    void normalizesCode() {
        assertEquals("ABC-0042",
                incoming.convert("  abc-0042  ").value());
    }

    @Test
    void rejectsBadCodes() {
        assertThrows(IllegalArgumentException.class,
                () -> incoming.convert("abc-42"));

        assertThrows(IllegalArgumentException.class,
                () -> incoming.convert("abc_0042"));
    }

    @Test
    void reverseConverterPrintsPlainCode() {
        assertEquals("ABC-0042",
                outgoing.convert(
                        new ProductCode("ABC-0042")));
    }

    @Test
    void normalizationIsIndependentOfDefaultLocale() {
        Locale old = Locale.getDefault();
        try {
            Locale.setDefault(
                    Locale.forLanguageTag("tr-TR"));

            assertEquals("MIX-0042",
                    incoming.convert("mix-0042").value());
        } finally {
            Locale.setDefault(old);
        }
    }
}
~~~

Test thay JVM default Locale là thay đổi **trạng thái toàn cục**; nếu CI chạy song song, dùng resource lock hoặc chạy riêng test này. `finally` hoàn nguyên Locale. Test chứng minh mã máy đọc không phụ thuộc quy tắc chữ hoa của một locale như tr-TR.

## 5. Unit tests: MoneyAmountFormatter

File `src/test/java/com/example/formatdemo/MoneyAmountFormatterTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.text.ParseException;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class MoneyAmountFormatterTest {

    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private static final Locale EN = Locale.US;

    private final MoneyAmountFormatter formatter =
            new MoneyAmountFormatter();

    @Test
    void parsesVietnameseAmount() throws Exception {
        MoneyAmount amount =
                formatter.parse("1.234,50", VI);

        assertEquals(new BigDecimal("1234.50"),
                amount.value());
    }

    @Test
    void parsesEnglishAmount() throws Exception {
        MoneyAmount amount =
                formatter.parse("1,234.50", EN);

        assertEquals(new BigDecimal("1234.50"),
                amount.value());
    }

    @Test
    void printsVietnameseAmount() {
        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        assertEquals("1.234,50",
                formatter.print(money, VI));
    }

    @Test
    void printsEnglishAmount() {
        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        assertEquals("1,234.50",
                formatter.print(money, EN));
    }

    @Test
    void roundTripPreservesDecimal()
            throws Exception {

        var money = new MoneyAmount(
                new BigDecimal("1234.50"));

        for (Locale locale : new Locale[]{VI, EN}) {
            String displayed =
                    formatter.print(money, locale);

            assertEquals(money.value(),
                    formatter.parse(
                            displayed, locale).value());
        }
    }

    @Test
    void trailingGarbageIsRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse(
                        "1,234.50oops", EN));
    }

    @Test
    void tooManyFractionDigitsAreRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse(
                        "1,234.567", EN));
    }

    @Test
    void blankInputIsRejected() {
        assertThrows(ParseException.class,
                () -> formatter.parse("  ", VI));
    }

    @Test
    void negativeAmountCanParseBeforeValidation()
            throws Exception {

        assertEquals(new BigDecimal("-1.00"),
                formatter.parse("-1,00", VI).value());
    }
}
~~~

`Formatter.parse` chỉ kiểm cấu trúc số/scale. Bean Validation mới thực hiện `@DecimalMin` và `@Digits` theo chính sách. Khi dùng JDK/locale provider khác, ký tự grouping có thể thay đổi: nếu test khác expectation, kiểm dữ liệu Locale/`DecimalFormatSymbols` trước khi cho rằng business conversion sai.

## 6. MockMvc: REST path/query

File `src/test/java/com/example/formatdemo/QuoteMvcTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productPathUsesConverter() throws Exception {
        mvc.perform(get("/api/products/abc-0042"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("ABC-0042"));
    }

    @Test
    void invalidPathReturns400() throws Exception {
        mvc.perform(get("/api/products/abc-42"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"));
    }

    @Test
    void vietnameseAmountInQuery() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "vi-VN")
                        .param("code", "abc-0042")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("ABC-0042"))
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"));
    }

    @Test
    void englishAmountInQuery() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "en-US")
                        .param("code", "abc-0042")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount")
                        .value("1234.50"));
    }

    @Test
    void malformedAmountReturns400() throws Exception {
        mvc.perform(get("/api/quotes")
                        .header("Accept-Language", "en-US")
                        .param("code", "ABC-0042")
                        .param("amount", "1,234.50oops"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"));
    }

    @Test
    void codeDoesNotDependOnLocale() throws Exception {
        mvc.perform(get("/api/products/mix-0042")
                        .header("Accept-Language", "tr-TR"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code")
                        .value("MIX-0042"));
    }
}
~~~

MockMvc dùng thật Spring MVC argument resolver, ConversionService và advice nhưng không mở socket. Nó xác nhận converter/formatter được đăng ký đúng, không chỉ class có method `convert`/`parse`.

## 7. MockMvc: form Thymeleaf

File `src/test/java/com/example/formatdemo/OfferFormMvcTest.java`:

~~~java
package com.example.formatdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OfferFormMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void vietnameseFormPrintsLocalizedAmount()
            throws Exception {

        mvc.perform(get("/offers/new")
                        .header("Accept-Language", "vi-VN"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(content().string(
                        containsString("1.234,50")))
                .andExpect(content().string(
                        containsString("ABC-1234")));
    }

    @Test
    void englishFormPrintsLocalizedAmount()
            throws Exception {

        mvc.perform(get("/offers/new")
                        .header("Accept-Language", "en-US"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(content().string(
                        containsString("1,234.50")));
    }

    @Test
    void vietnameseFormAcceptsValidInput()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "abc-0042")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/success"))
                .andExpect(model().attribute(
                        "code", "ABC-0042"))
                .andExpect(model().attribute(
                        "canonicalAmount", "1234.50"));
    }

    @Test
    void englishFormAcceptsValidInput()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/success"))
                .andExpect(model().attribute(
                        "canonicalAmount", "1234.50"));
    }

    @Test
    void invalidCodeCreatesBindingError()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "bad")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "productCode"));
    }

    @Test
    void invalidAmountTextCreatesBindingError()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "1.234,50oops"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount"));
    }

    @Test
    void negativeAmountFailsNestedBeanValidation()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "vi-VN")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "-1,00"))
                .andExpect(status().isOk())
                .andExpect(view().name("offers/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount.value"));
    }

    @Test
    void oversizedAmountFailsDigitsConstraint()
            throws Exception {

        mvc.perform(post("/offers/new")
                        .header("Accept-Language", "en-US")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("productCode", "ABC-0042")
                        .param("amount", "123,456,789.00"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "offerForm", "amount.value"));
    }
}
~~~

**Đọc kết quả đúng bản chất:**

- `productCode=bad` và `amount=1.234,50oops`: lỗi **conversion** tại field tương ứng, thường code `typeMismatch`.
- `amount=-1,00`: parse thành công, nhưng validation `@DecimalMin` trên nested `amount.value` lỗi.
- Amount có chín chữ số phần nguyên: parse thành công, `@Digits(integer=8)` lỗi.
- Form báo lỗi trả HTTP 200 vì controller chủ động render lại HTML; test nên assert view và `BindingResult`, không đồng nhất HTTP 200 với việc dữ liệu hợp lệ.
- Một input JSON sai không đi qua cùng BeanPropertyBindingResult/formatter; phải test ở Jackson boundary riêng.

Tổng bộ demo có **27 tests**: bốn converter tests, chín formatter tests, sáu REST MockMvc tests và tám form MockMvc tests. Chạy:

~~~bash
mvn test
~~~

Hoặc riêng:

~~~bash
mvn -Dtest=ProductCodeConverterTest test
mvn -Dtest=MoneyAmountFormatterTest test
mvn -Dtest=QuoteMvcTest test
mvn -Dtest=OfferFormMvcTest test
~~~

## 8. Locale resolution và những bẫy định dạng

### 8.1. Request Locale đến từ đâu?

Spring MVC thông thường sử dụng `AcceptHeaderLocaleResolver` để chọn Locale từ `Accept-Language` khi chưa cấu hình policy khác. Trong MockMvc, header `Accept-Language: vi-VN` làm formatter nhận `Locale.forLanguageTag("vi-VN")`; `en-US` cho ký hiệu Mỹ.

Nếu muốn đổi ngôn ngữ bằng `?lang=vi`, phải cấu hình `LocaleResolver`/`LocaleChangeInterceptor` thích hợp; không giả định query parameter `lang` tự đổi locale của Spring.

### 8.2. Một chuỗi có thể bị hiểu khác ở locale khác

`-1,00` trong vi-VN nghĩa là âm một, nhưng với en-US dấu phẩy thường có ý nghĩa grouping và có thể dẫn tới âm một trăm. Parser nhận sai Locale có thể trả **số khác** thay vì lỗi. `ParsePosition` kiểm toàn chuỗi là cần nhưng không đủ cho strict grammar.

Trong sản phẩm thật, nên giữ Locale nhất quán giữa mở form và submit; nếu không bảo đảm được, có thể chọn **canonical decimal input** cho API và localized display chỉ trên UI.

### 8.3. DecimalFormat không thread-safe

Đừng làm:

~~~java
private static final DecimalFormat FORMAT =
        new DecimalFormat("#,##0.00");
~~~

rồi thay ký hiệu/Locale trên singleton giữa các requests. `NumberFormat` và `DecimalFormat` mutable; demo tạo instance mới trong `parse` và `print`. Spring thường giữ Formatter trong registry dùng chung, nên state của formatter phải thread-safe.

### 8.4. Vì sao không chuyển qua Double?

Không nên:

~~~java
Number parsed = NumberFormat.getNumberInstance(locale)
        .parse(text);

BigDecimal amount =
        BigDecimal.valueOf(parsed.doubleValue());
~~~

Ở đây số decimal đã qua biểu diễn nhị phân. Dùng `DecimalFormat.setParseBigDecimal(true)`, sau đó giữ `BigDecimal`. Khi cần rounding, xác định rõ `RoundingMode` theo nghiệp vụ trước khi làm tròn.

### 8.5. Input type="number" khác localized text

HTML form `input type="number"` dùng quy tắc chuẩn/browser, có thể không gửi đúng chuỗi trình bày localized. Nếu muốn dùng Formatter nhận `1.234,50`, `type="text"` như demo là lựa chọn tường minh. Nếu dùng number input, thiết kế client gửi canonical decimal và server parser tương ứng.

### 8.6. Không đoán currency từ Locale

Locale quyết định cách hiển thị, không xác định currency cho một order. Đối với multi-currency, cần domain:

~~~java
public record Price(
        BigDecimal amount,
        Currency currency) {
}
~~~

Đây là snippet bổ sung, không thuộc demo Maven, cần import `java.util.Currency`. Currency có scale/rounding policy riêng và có thể được trình bày theo nhiều Locale.

## 9. Converter/Formatter không thay thế validation và authorization

Cả hai chỉ tạo **giá trị có kiểu**. Converter thấy `ABC-0042` hợp lệ không chứng minh người dùng có quyền sửa sản phẩm đó. Phải kiểm quyền ở service theo resource ID/owner/tenant, đồng thời bảo vệ input DTO khỏi mass assignment.

Phân biệt trách nhiệm:

~~~text
HTTP text → Converter/Formatter
             |
             +-- Parse không được → typeMismatch
             |
             v
         Typed input
             |
             +-- Bean Validation → DecimalMin/Digits/NotNull...
             |
             v
         Authentication + authorization
             |
             v
         Business state/transaction/persistence
~~~

Không để Converter gọi DB và tạo transaction với side effects. Converter có thể được gọi lại khi binding/render/test; nên deterministic và không sửa dữ liệu.

### 9.1. Giới hạn độ dài input

Một số text quá dài có thể tiêu tốn CPU/memory. Trước parse có thể thêm:

~~~java
if (input.length() > 64) {
    throw new ParseException(
            "Amount text is too long", 0);
}
~~~

Đây là snippet gia cố, không thuộc file formatter demo. Trong production, chọn limit phù hợp giao dịch và thêm HTTP body/parameter limits; `@Digits` chỉ chạy sau parsing, không ngăn chi phí parse chuỗi quá dài.

### 9.2. Không công khai rejectedValue

`FieldError.getRejectedValue()` có thể chứa mật khẩu/token/PII. API error response chỉ nên đưa mã lỗi, path và message an toàn; không serialize trực tiếp raw exception hoặc rejected value. Với Thymeleaf form, kiểm escaping của output và giữ `BindingResult` để hiển thị lỗi đúng mà không tạo đường XSS mới.

## 10. Khi nào dùng AnnotationFormatterFactory hoặc @NumberFormat?

Nếu field chỉ là `BigDecimal` hoặc `LocalDate` và không cần domain value type riêng, Spring có sẵn:

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate deliveryDate;
~~~

Đây là snippets cần imports. `@NumberFormat` và `@DateTimeFormat` thường đủ cho các trường phổ biến; không viết formatter custom chỉ để làm lại tính năng có sẵn.

Một số SPI liên quan:

- `ConverterFactory<S,R>`: một họ target types (ví dụ nhiều enum).
- `GenericConverter` và `ConditionalGenericConverter`: cần `TypeDescriptor`/annotation metadata hoặc nhiều cặp nguồn/đích.
- `AnnotationFormatterFactory<A>`: chỉ áp formatter cho fields có annotation cụ thể.
- `FormatterRegistrar`: đăng ký một nhóm formatters/converters tái sử dụng.

Đối với **một** domain code và **một** domain money type trong demo, `Converter<String,ProductCode>` + `Formatter<MoneyAmount>` đủ đơn giản và rõ ràng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `@PathVariable ProductCode` không convert | Converter chưa đăng ký, mã sai pattern | Kiểm MVC config và MockMvc |
| Path `abc-42` thành HTTP 400 | Đúng: mã không thỏa regex | Trả mã lỗi an toàn |
| Form hiện `ProductCode[value=...]` | Thiếu chiều ProductCode→String | Đăng ký reverse converter |
| Form hiện `MoneyAmount[value=...]` | Formatter không được dùng khi render | Kiểm th:field/registry |
| Query `1.234,50` báo lỗi | Locale là en-US hoặc khác | Kiểm Accept-Language |
| Formatter in đúng nhưng parser sai | Mới kiểm print | Unit test parse/round-trip |
| Parser nhận `1,234.50abc` | Chỉ dùng NumberFormat.parse(String) | ParsePosition kiểm full consumption |
| Parser trả sai số âm hoặc số lẻ | Qua double | parseBigDecimal và BigDecimal |
| Form âm tiền không báo lỗi | Thiếu @Valid cascade | Thêm @Valid trên MoneyAmount |
| Form lỗi vẫn HTTP 200 | Controller render lại view | Test BindingResult và view |
| JSON body không dùng MVC formatter | Jackson là pipeline khác | DTO/JSON mapping riêng |
| Boot config properties không dùng converter | MVC conversion service khác | WebMvcConfigurer.addFormatters |
| @EnableWebMvc làm mất Boot customizations | Vô hiệu auto-configuration | Chỉ implements WebMvcConfigurer |
| Tiền có dấu phân cách kỳ lạ | JDK locale data khác | Kiểm DecimalFormatSymbols |
| Dùng chung DecimalFormat bị race | Formatter mutable singleton | Tạo NumberFormat per call |
| Code thành ký tự lạ ở tr-TR | toUpperCase() phụ thuộc Locale | Locale.ROOT |
| Form mất giá trị vừa nhập sau lỗi | Tạo model mới thay BindingResult | Giữ object BindingResult gốc |
| Chuyển đổi đúng nhưng user không có quyền | Converter không làm authorization | Service kiểm resource rights |
| Giá tiền VND/USD bị nhầm | Dùng Locale làm currency | Domain Currency riêng |
| Input quá dài gây chậm | Không limit trước parsing | Giới hạn string/request size |
| HTTP 400 lộ giá trị nhạy cảm | Trả rejectedValue/exception | Error code và message an toàn |

### 11.1. Kiểm ConversionService độc lập

Có thể tạo một `DefaultFormattingConversionService` ngoài HTTP để kiểm registration:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addConverter(new ProductCodeConverter());
service.addConverter(
        new ProductCodeToStringConverter());
service.addFormatter(new MoneyAmountFormatter());

ProductCode code = service.convert(
        "abc-0042", ProductCode.class);

assertEquals("ABC-0042", code.value());
~~~

Đây là snippet test với import Spring/JUnit phù hợp. Để kiểm Locale, đặt `LocaleContextHolder` trong phạm vi try/finally:

~~~java
Locale previous = LocaleContextHolder.getLocale();

try {
    LocaleContextHolder.setLocale(
            Locale.forLanguageTag("vi-VN"));

    MoneyAmount amount = service.convert(
            "1.234,50", MoneyAmount.class);

    assertEquals(new BigDecimal("1234.50"),
            amount.value());
} finally {
    LocaleContextHolder.setLocale(previous);
}
~~~

Bài test này chỉ xác nhận registry do mình dựng; **MockMvc** vẫn cần thiết để chắc chắn request Locale và MVC argument binding thực sự sử dụng converter/formatter.

## 12. Đa ngôn ngữ cho lỗi form

Spring `BindingResult` có thể tạo message codes như:

~~~text
typeMismatch.offerForm.productCode
typeMismatch.offerForm.amount
typeMismatch.amount
typeMismatch
~~~

Các mã cụ thể phụ thuộc `MessageCodesResolver`, tên object và type. Nếu muốn Việt hóa field errors, có thể cấu hình `messages.properties` và `messages_vi.properties` với key như:

~~~properties
typeMismatch.offerForm.productCode=Mã sản phẩm không hợp lệ
typeMismatch.offerForm.amount=Số tiền không đúng định dạng
DecimalMin.offerForm.amount.value=Số tiền phải lớn hơn hoặc bằng 0,01
Digits.offerForm.amount.value=Số tiền vượt giới hạn cho phép
~~~

Đây là **đoạn cấu hình mở rộng**, không phải file bắt buộc của demo. Để Boot nhận MessageSource mặc định, cần base bundle hợp lệ, ví dụ `messages.properties`. Trước khi chuẩn hóa keys, xem `BindingResult.getFieldError(...).getCodes()` trong test; không đoán objectName hoặc nested path.

## 13. Bài tập vận dụng

**Bài 1.** Đổi mã doanh nghiệp thành `PRD-123456` và chỉnh record, tests. Tại sao regex không nên nằm trong mỗi controller?

**Bài 2.** Thử `tr-TR` với mã `mix-0042`. So sánh `toUpperCase()` và `toUpperCase(Locale.ROOT)`.

**Bài 3.** Thêm `Locale.FRANCE` cho formatter, kiểm dấu cách nhóm có thể là non-breaking space, không cố thay bằng ASCII space.

**Bài 4.** Thử parse `1,234.567`, `1.234,567` với locale tương ứng. Đề xuất strict grouping grammar.

**Bài 5.** Thay chính sách scale từ RoundingMode.UNNECESSARY sang HALF_EVEN, viết tests cho giá trị ở điểm giữa. Giải thích ai có quyền quyết định rounding policy.

**Bài 6.** Xây `Price(BigDecimal,Currency)`, phân biệt locale presentation và currency của giao dịch.

**Bài 7.** Thêm JSON endpoint nhận code/amount. Viết Jackson deserializer hoặc DTO canonical riêng; chứng minh MVC formatter không chạy cho @RequestBody.

**Bài 8.** Gửi amount text sai/âm/quá lớn và phân biệt typeMismatch với DecimalMin/Digits theo đúng field path.

**Bài 9.** Thêm language selector; bảo đảm giá trị mở form và submit được parse dưới cùng locale hoặc canonical protocol.

**Bài 10.** Dùng @NumberFormat trên BigDecimal và so sánh với custom Formatter<MoneyAmount>. Trường hợp nào phù hợp hơn?

**Bài 11.** Bổ sung tests trong Spring Security cho CSRF, owner/tenant authorization sau khi code được convert hợp lệ.

**Bài 12.** Đặt limit 64 ký tự trước khi parse amount, kiểm input cực dài và không log rejected values.

## Kết luận

~~~text
HTTP path/query/form
      |
      v
Spring MVC FormattingConversionService
      |
      +-- String → ProductCode  (Locale.ROOT)
      |
      +-- String ↔ MoneyAmount (request Locale)
      |
      v
Typed domain values
      |
      v
Bean Validation → authorization → service
      |
      v
Response JSON canonical / form localized

@RequestBody JSON → Jackson (không mặc định qua MVC formatter)
~~~

**Converter** tạo domain type theo quy tắc máy đọc cố định; **Formatter** giúp parse và print dữ liệu theo `Locale`. Với `BigDecimal` chính xác, `WebMvcConfigurer.addFormatters`, `BindingResult` và kiểm thử cho cả hai chiều, bạn có thể tạo form/API có mã nghiệp vụ đáng tin cậy và số tiền không bị nhầm dấu phân cách.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — Formatter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.2 — Parser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework 6.2 — Converter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — WebMvcConfigurer.addFormatters](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot 3.5 — MVC Conversion Service](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Thymeleaf 3.1 — Spring Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)
- [Java 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [Java 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [Java 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
