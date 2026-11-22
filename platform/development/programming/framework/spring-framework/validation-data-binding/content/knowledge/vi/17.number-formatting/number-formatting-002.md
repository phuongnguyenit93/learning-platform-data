# NumberStyleFormatter, CurrencyStyleFormatter và PercentStyleFormatter trong Spring Framework

> **Chủ đề:** Spring Framework – validation, data binding và type conversion.  
> **Nhóm:** Định dạng số.  
> **Môi trường ví dụ:** Java 17+, Spring Framework 6.2.x. Bài này giải thích cách parse chuỗi thành số và in số thành chuỗi theo locale/pattern, cách tích hợp formatter vào Spring MVC, và các giới hạn cần quản lý với tiền tệ/phần trăm.

## 1. Tại sao cần formatter số?

Giá trị số là dữ liệu có cấu trúc; chuỗi hiển thị của nó phụ thuộc locale. Cùng một giá trị `12345.67` có thể được trình bày như sau:

| Locale | Biểu diễn mẫu |
| --- | --- |
| `en-US` | `12,345.67` |
| `de-DE` | `12.345,67` |
| `fr-FR` | `12 345,67` |

Tiền tệ còn có ký hiệu và số chữ số thập phân; phần trăm có quy ước nhân giá trị ratio với 100 khi hiển thị. Vì vậy không nên tự thay dấu phẩy/dấu chấm hoặc parse số theo locale mặc định của máy chủ.

Spring cung cấp ba formatter chuyên biệt:

- `NumberStyleFormatter`: số thông thường theo locale hoặc decimal pattern.
- `CurrencyStyleFormatter`: số theo kiểu tiền tệ, cho phép cấu hình currency, fraction digits và rounding.
- `PercentStyleFormatter`: số theo kiểu phần trăm của locale.

Cả ba đều thực hiện hai chiều parse và print. Điều này hữu ích với form: dữ liệu nhập được chuyển thành kiểu số Java; khi hiển thị lại, giá trị có thể được format theo locale hiện tại.

## 2. Formatter contract: parse và print

Trong Spring, `Formatter<T>` kết hợp `Parser<T>` và `Printer<T>`. Hai thao tác cốt lõi là:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // parse(String text, Locale locale)
    // print(T object, Locale locale)
}
```

- `parse(text, locale)` chuyển văn bản thành giá trị Java.
- `print(object, locale)` tạo văn bản hiển thị.
- `Locale` xác định dấu thập phân, phân nhóm chữ số, ký hiệu currency/percent.
- Parse lỗi có thể ném `ParseException`; khi đi qua Spring binding, lỗi được chuyển thành lỗi binding phù hợp.

Khác với converter một chiều `Converter<S,T>`, formatter có cả parser và printer. Khi cùng một field cần nhận dữ liệu có định dạng và hiển thị lại theo quy ước tương ứng, formatter là abstraction phù hợp.

## 3. NumberStyleFormatter: số thông thường

`org.springframework.format.number.NumberStyleFormatter` là formatter tổng quát cho `Number`. Nó sử dụng number format theo locale tương ứng với `NumberFormat.getInstance(locale)`. Formatter cho phép cấu hình decimal pattern bằng cú pháp của Java `DecimalFormat`.

Javadoc Spring 6.2.14 mô tả việc parse của formatter này trả về `BigDecimal`, tránh mất độ chính xác khi phân tích chuỗi thập phân.

### 3.1. Parse và print theo locale

```java
import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.format.number.NumberStyleFormatter;

NumberStyleFormatter formatter = new NumberStyleFormatter();

BigDecimal us = (BigDecimal) formatter.parse("12,345.67", Locale.US);
BigDecimal de = (BigDecimal) formatter.parse("12.345,67", Locale.GERMANY);

String displayUs = formatter.print(us, Locale.US);
String displayDe = formatter.print(de, Locale.GERMANY);
```

Với đúng locale, chuỗi grouping và decimal separator được hiểu theo quy ước của locale đó. Ví dụ `1,234` có thể được hiểu khác nhau giữa hai locale; vì vậy phải chọn locale dựa trên hợp đồng đầu vào/user context, không phỏng đoán.

Đối với API machine-to-machine, cân nhắc dùng biểu diễn số JSON dạng numeric hoặc một format chuẩn cố định. Chuỗi localized dành cho người dùng không nên trở thành format tích hợp không được định nghĩa.

### 3.2. Decimal pattern

Có thể truyền pattern vào constructor hoặc dùng `setPattern`:

```java
NumberStyleFormatter twoDecimals =
        new NumberStyleFormatter("#,##0.00");

NumberStyleFormatter threeOptional =
        new NumberStyleFormatter("#,##0.###");
```

| Pattern | Ý nghĩa |
| --- | --- |
| `#,##0` | Grouping và tối thiểu một chữ số nguyên |
| `#,##0.00` | Hiển thị hai chữ số thập phân |
| `#,##0.###` | Tối đa ba chữ số thập phân |
| `0.000` | Hiển thị ba chữ số thập phân |
| `#,##0.00;(#,##0.00)` | Pattern dương; pattern âm dùng ngoặc |

Pattern ảnh hưởng parse/print và biểu diễn hiển thị. Nó không tự đặt quy tắc scale, precision hay phạm vi hợp lệ của domain. Ví dụ giới hạn số lượng tối đa hai chữ số thập phân nên được xác nhận trong validation/domain, không chỉ dựa vào việc formatter hiển thị hai chữ số.

### 3.3. Dùng khi nào?

Dùng `NumberStyleFormatter` cho số lượng, điểm số, phép đo, tỷ lệ dạng số thập phân hoặc giá trị `BigDecimal` thông thường. Nếu giá trị mang ý nghĩa tiền tệ hoặc phần trăm, formatter chuyên biệt thường diễn đạt đúng ý nghĩa hơn.

## 4. CurrencyStyleFormatter: số tiền

`org.springframework.format.number.CurrencyStyleFormatter` dùng currency style của `NumberFormat.getCurrencyInstance(locale)`. Formatter parse về `BigDecimal` và cho phép cấu hình đơn vị tiền, số chữ số lẻ, rounding mode và pattern.

Các API quan trọng:

| API | Mục đích |
| --- | --- |
| `setCurrency(Currency)` | Đặt currency cụ thể nếu nghiệp vụ đã biết |
| `setFractionDigits(int)` | Đặt số chữ số thập phân; mặc định 2 |
| `setRoundingMode(RoundingMode)` | Đặt chế độ làm tròn; mặc định `UNNECESSARY` |
| `setPattern(String)` | Đặt decimal pattern |
| `setLenient(boolean)` | Kiểm soát mức chấp nhận của quá trình parse |

### 4.1. Currency và Locale là hai khái niệm khác nhau

Locale cung cấp quy ước trình bày, ví dụ dấu phân nhóm và vị trí ký hiệu. Currency xác định đơn vị tiền thực tế như USD, EUR hoặc VND. Locale của người dùng không chứng minh đơn vị tiền của giao dịch.

Nếu currency đã biết, cấu hình tường minh:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;
import org.springframework.format.number.CurrencyStyleFormatter;

CurrencyStyleFormatter usd = new CurrencyStyleFormatter();
usd.setCurrency(Currency.getInstance("USD"));
usd.setFractionDigits(2);

BigDecimal amount = usd.parse("$1,234.50", Locale.US);
String display = usd.print(amount, Locale.US);
```

Ký hiệu và cách đặt ký hiệu theo locale. Nếu hệ thống hỗ trợ nhiều đơn vị tiền, hãy lưu currency cùng amount hoặc dùng một money value object. Không suy ra currency chỉ từ ký tự `$` vì nhiều đơn vị tiền có thể dùng ký hiệu này.

### 4.2. Rounding mode

Mặc định `RoundingMode.UNNECESSARY` có nghĩa formatter không được âm thầm làm tròn nếu parse cần rounding theo cấu hình fraction digits. Khi chính sách cho phép làm tròn, hãy đặt mode rõ:

```java
import java.math.RoundingMode;

usd.setFractionDigits(2);
usd.setRoundingMode(RoundingMode.HALF_UP);
```

Một số mode:

| Mode | Ý nghĩa |
| --- | --- |
| `HALF_UP` | Gần nhất; điểm giữa làm tròn lên theo trị tuyệt đối |
| `HALF_EVEN` | Gần nhất; điểm giữa về chữ số chẵn |
| `DOWN` | Bỏ phần dư về phía zero |
| `CEILING` | Làm tròn theo hướng dương vô cùng |
| `FLOOR` | Làm tròn theo hướng âm vô cùng |
| `UNNECESSARY` | Từ chối nếu phải làm tròn |

Rounding là chính sách nghiệp vụ/kế toán. Không chọn mode chỉ để làm ví dụ chạy được; xác định quy tắc tại bước tính toán và lưu trữ thích hợp. Formatter tiền tệ không kiểm tra số dư tài khoản, thuế, quyền giao dịch hoặc giới hạn tín dụng.

### 4.3. Lưu ý với BigDecimal

Dùng `BigDecimal` cho số tiền cần chính xác thập phân, không dùng `double`. Phân biệt scale dữ liệu, fraction digits hiển thị và rounding mode. Ví dụ `new BigDecimal("1.2300")` và `new BigDecimal("1.23")` có thể so sánh tương đương bằng `compareTo` nhưng khác theo `equals` vì scale.

Không dùng `new BigDecimal(0.1)` vì đầu vào là binary floating-point approximation. Dùng `new BigDecimal("0.1")` hoặc thiết kế lưu minor units khi domain phù hợp.

## 5. PercentStyleFormatter: giá trị phần trăm

`org.springframework.format.number.PercentStyleFormatter` dùng percent style của `NumberFormat.getPercentInstance(locale)`. Parse trả về `BigDecimal`.

Nếu domain lưu ratio `0.125`, hiển thị theo percent style thường là `12.5%`. Parse `12.5%` trả về ratio `0.125`:

```java
import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.format.number.PercentStyleFormatter;

PercentStyleFormatter percent = new PercentStyleFormatter();

String display = percent.print(new BigDecimal("0.125"), Locale.US);
BigDecimal ratio = (BigDecimal) percent.parse("12.5%", Locale.US);
```

Không truyền `12.5` khi domain lưu ratio và kỳ vọng formatter hiểu đó là 12.5%; percent style áp dụng quy ước phần trăm của `NumberFormat`.

Hai cách lưu dữ liệu khác nhau:

- **Ratio:** `0.125` biểu diễn 12.5%; thuận tiện cho các phép tính nhân.
- **Percentage points:** `12.5` biểu diễn 12.5 điểm phần trăm.

Đừng trộn hai mô hình trong cùng một field. Percent formatter chỉ parse/print; nó không kiểm tra discount âm, thuế suất vượt giới hạn hoặc tỷ lệ hoàn thành trên 100%.

## 6. So sánh ba formatter

| Tiêu chí | NumberStyleFormatter | CurrencyStyleFormatter | PercentStyleFormatter |
| --- | --- | --- | --- |
| Mục tiêu | Số tổng quát | Số theo kiểu tiền tệ | Số theo kiểu phần trăm |
| NumberFormat nền | `getNumberInstance(locale)` | `getCurrencyInstance(locale)` | `getPercentInstance(locale)` |
| Parse result | `BigDecimal` | `BigDecimal` | `BigDecimal` |
| Locale | Grouping và decimal | Grouping, decimal và currency style | Grouping, decimal và percent symbol |
| Tùy chỉnh | `setPattern` | Currency, fraction digits, rounding, pattern | Locale percent style |
| Dữ liệu phù hợp | Số lượng, đo lường | Amount kèm currency | Ratio/percentage |
| Validation nghiệp vụ | Vẫn cần | Vẫn cần | Vẫn cần |

Cả ba đều hỗ trợ parse và print. Hãy chọn theo ý nghĩa dữ liệu, không chỉ theo hình thức chuỗi.

## 7. Ví dụ Java 17 chạy được với Maven

Ví dụ dưới đây kiểm tra ba formatter với `Locale.US`. Nó dùng Spring Framework 6.2.14, không cần Spring Boot, servlet container hay database.

Cấu trúc:

```text
number-format-demo/
  pom.xml
  src/main/java/demo/NumberFormatterDemo.java
```

### 7.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
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
            <version>6.2.14</version>
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

### 7.2. NumberFormatterDemo.java

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.number.CurrencyStyleFormatter;
import org.springframework.format.number.NumberStyleFormatter;
import org.springframework.format.number.PercentStyleFormatter;

public final class NumberFormatterDemo {

    public static void main(String[] args) throws Exception {
        Locale locale = Locale.US;

        NumberStyleFormatter number = new NumberStyleFormatter();
        BigDecimal parsedNumber =
                (BigDecimal) number.parse("1,234.50", locale);
        String printedNumber = number.print(parsedNumber, locale);

        CurrencyStyleFormatter currency =
                new CurrencyStyleFormatter();
        currency.setCurrency(Currency.getInstance("USD"));
        currency.setFractionDigits(2);
        currency.setRoundingMode(RoundingMode.HALF_UP);

        BigDecimal parsedAmount =
                currency.parse("$1,234.50", locale);
        String printedAmount =
                currency.print(parsedAmount, locale);

        PercentStyleFormatter percent =
                new PercentStyleFormatter();
        BigDecimal parsedRatio =
                (BigDecimal) percent.parse("12.5%", locale);
        String printedPercent =
                percent.print(parsedRatio, locale);

        System.out.println("numberValue=" + parsedNumber.toPlainString());
        System.out.println("numberDisplay=" + printedNumber);
        System.out.println("currencyValue=" + parsedAmount.toPlainString());
        System.out.println("currencyDisplay=" + printedAmount);
        System.out.println("percentRatio=" + parsedRatio.toPlainString());
        System.out.println("percentDisplay=" + printedPercent);
    }
}
```

Chạy bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NumberFormatterDemo
```

Stdout kỳ vọng với locale US và locale data thông dụng của JDK:

```text
numberValue=1234.50
numberDisplay=1,234.50
currencyValue=1234.50
currencyDisplay=$1,234.50
percentRatio=0.125
percentDisplay=12.5%
```

Ví dụ cố định `Locale.US` để kết quả dễ đối chiếu. Ký hiệu và khoảng trắng tiền tệ có thể phụ thuộc locale data/JDK; khi xây test production, cố định locale và kiểm tra output trong JDK được triển khai. Ví dụ này là chương trình hoàn chỉnh có Maven dependency; chỉ dùng `javac` không có Spring trên classpath sẽ không biên dịch.

## 8. Đăng ký formatter trong Spring MVC

Spring MVC cho phép đăng ký formatter qua `WebMvcConfigurer` và `FormatterRegistry`:

```java
package demo.web;

import java.math.BigDecimal;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.number.NumberStyleFormatter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class NumberFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                BigDecimal.class,
                new NumberStyleFormatter("#,##0.00"));
    }
}
```

Đây là một cấu hình formatter chung cho property kiểu `BigDecimal` trong MVC registry. Khi một field cần currency hoặc percent riêng, không nên áp một formatter chung rồi kỳ vọng nó tự biết ngữ nghĩa của từng field. Dùng annotation hoặc cấu hình cụ thể theo field phù hợp hơn.

### 8.1. Dùng @NumberFormat cho từng field

Spring có annotation `@NumberFormat` để chọn style theo field:

```java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;
import static org.springframework.format.annotation.NumberFormat.Style.CURRENCY;
import static org.springframework.format.annotation.NumberFormat.Style.NUMBER;
import static org.springframework.format.annotation.NumberFormat.Style.PERCENT;

public class InvoiceForm {

    @NumberFormat(style = NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = CURRENCY)
    private BigDecimal total;

    @NumberFormat(style = PERCENT)
    private BigDecimal discountRate;

    // getters and setters
}
```

Spring dùng annotation formatter factory để chọn formatter tương ứng:
- `quantity` dùng number style.
- `total` dùng currency style.
- `discountRate` dùng percent style.

`@NumberFormat(style=CURRENCY)` chọn cách định dạng currency theo locale; annotation này không tự biểu diễn currency giao dịch cố định như USD. Nếu đơn vị tiền đã biết, phải cấu hình currency một cách tường minh hoặc dùng value object có currency.

### 8.2. Binding form và validation

Spring MVC form binding có thể parse chuỗi thành `BigDecimal` qua formatter đăng ký/annotation. Sau binding, `@Valid` có thể kích hoạt Bean Validation:

```java
@PostMapping("/invoice")
public String submit(
        @Valid @ModelAttribute("invoiceForm") InvoiceForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "invoice-form";
    }
    return "invoice-preview";
}
```

Đây là method minh họa trong một MVC controller có view tương ứng. `BindingResult` phải đặt ngay sau model attribute để nhận lỗi binding/validation của form.

Với `@RequestBody` JSON, nội dung thường đi qua `HttpMessageConverter` như Jackson và pipeline deserialize riêng. Không mặc định formatter registry của MVC điều khiển mọi JSON number/string. Hãy quy định JSON representation và cấu hình Jackson/custom deserializer khi cần.

## 9. Locale và xử lý dữ liệu người dùng

Locale quyết định decimal separator và grouping. Cùng `BigDecimal("1234.50")` có thể in thành chuỗi khác nhau:

```java
NumberStyleFormatter formatter = new NumberStyleFormatter();
BigDecimal amount = new BigDecimal("1234.50");

String us = formatter.print(amount, Locale.US);
String germany = formatter.print(amount, Locale.GERMANY);
```

Khi parse lại, phải dùng locale phù hợp với cách chuỗi đã được nhập. Không parse chuỗi `1.234,50` bằng `Locale.US` rồi kỳ vọng nhận cùng giá trị.

Trong Spring MVC, locale hiện hành có thể được xác định bởi locale resolver/interceptor và request context. Kiểm thử nên xác nhận locale thực tế của request. Với HTML input `type="number"`, browser có quy tắc định dạng/gửi dữ liệu riêng theo HTML; đừng suy luận mọi field gửi localized text như nội dung hiển thị.

Với API máy-máy, ưu tiên representation ổn định, không phụ thuộc ngôn ngữ UI. Locale-aware formatter thường phù hợp với form và nội dung hiển thị.

## 10. Parse errors, leniency và validation

Formatter không làm dữ liệu sai trở nên đúng. Những tình huống:
- Chuỗi không có định dạng số theo locale: parse error.
- Chuỗi tiền tệ không tương thích symbol/locale: parse error hoặc phụ thuộc number format.
- Giá trị phần trăm có thể parse thành công nhưng vượt chính sách.
- Currency có fraction digits bị giới hạn nhưng input yêu cầu rounding: với default `UNNECESSARY`, parse có thể từ chối.

`AbstractNumberFormatter` cung cấp `setLenient(boolean)` để điều chỉnh mức linh hoạt của parse. Lenient parsing có thể chấp nhận đầu vào rộng hơn tùy number format; strict input thường dễ kiểm soát hơn. Đừng bật lenient chỉ để giảm số lỗi nếu chuỗi mơ hồ có thể được hiểu theo cách không mong muốn.

Tách các trách nhiệm:

1. **Parse/format:** chuỗi có chuyển thành giá trị số theo locale/pattern không?
2. **Bean Validation:** giá trị có đạt required, min/max hoặc scale constraint không?
3. **Business rule:** amount/rate có được phép trong use case không?
4. **Persistence:** precision/scale của database có bảo toàn giá trị không?

Ví dụ validation:

```java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public class DiscountForm {

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private BigDecimal rate;

    // getter and setter
}
```

Ở đây domain lưu ratio từ 0 đến 1. Nếu field lưu percentage points 0 đến 100 thì giới hạn phải khác. Formatter không tự quyết định mô hình dữ liệu đó.

## 11. Precision, scale và hiển thị

Cần phân biệt:
- **Precision:** tổng số chữ số có nghĩa.
- **Scale:** số chữ số sau decimal point trong representation BigDecimal.
- **Fraction digits hiển thị:** số chữ số formatter in ra.
- **Rounding mode:** cách xử lý khi giá trị không thể biểu diễn ở scale yêu cầu.

Ví dụ `BigDecimal("1.2300")` có scale 4; formatter với pattern hai chữ số có thể hiển thị `1.23`. Hiển thị hai chữ số không chứng minh dữ liệu gốc đã được chuẩn hóa về scale 2.

Nếu scale là invariant domain, normalize/validate rõ ràng. Với tiền tệ, áp dụng rounding ở đúng bước nghiệp vụ tính toán; không để formatter làm thay đổi dữ liệu chỉ vì giao diện muốn ít chữ số hơn.

## 12. Lỗi phổ biến

**1. Dùng NumberStyleFormatter cho tiền mà không lưu currency.** Một con số không nói lên USD, EUR hay VND.

**2. Nhầm ratio và percentage points.** `0.125` và `12.5` khác nhau 100 lần khi dùng percent style.

**3. Parse localized string bằng locale sai.** Dấu phẩy/dấu chấm có thể mang ý nghĩa ngược nhau.

**4. Dùng double cho amount.** Binary floating point có thể tạo sai số; dùng BigDecimal.

**5. Cho rằng formatter tự validation.** Parse thành công không chứng minh amount/rate hợp lệ.

**6. Không quyết định rounding mode.** CurrencyStyleFormatter mặc định UNNECESSARY; trường hợp cần rounding có thể bị từ chối.

**7. Nghĩ @NumberFormat đặt currency cố định.** Annotation chọn style; currency giao dịch có thể cần cấu hình riêng.

**8. Kỳ vọng FormatterRegistry xử lý mọi JSON body.** JSON thường qua Jackson/HttpMessageConverter; test và cấu hình riêng.

**9. Không cố định locale trong test.** Expected string thay đổi theo locale/JDK data.

**10. Dùng pattern thay cho domain constraint.** Pattern hiển thị không kiểm soát range, precision hay quyền nghiệp vụ.

## 13. Ma trận kiểm thử khuyến nghị

| Case | Kết quả cần xác minh |
| --- | --- |
| Number parse `1,234.50` với `Locale.US` | BigDecimal 1234.50 |
| Number parse `1.234,50` với `Locale.GERMANY` | BigDecimal 1234.50 |
| In cùng số theo US và Germany | Decimal/group separator khác nhau |
| Currency parse `$1,234.50` với US/USD | BigDecimal 1234.50 |
| Currency fraction digits 2 và giá trị chính xác scale | Parse/print thành công |
| Currency input cần rounding | Theo rounding mode được chọn; default có thể từ chối |
| Percent parse `12.5%` với US | Ratio 0.125 |
| Percent print 0.125 với US | `12.5%` |
| Chuỗi số sai locale | Parse/binding error |
| `@NumberFormat` trên từng field | Mỗi field áp dụng đúng style |
| MVC form localized | Dùng đúng locale request |
| `@RequestBody` JSON | Test Jackson representation riêng |

Nên chia test thành ba mức: unit test formatter trực tiếp; binding test với DataBinder/MVC; domain/service test cho range, currency và rounding. Nếu assert output locale, hãy truyền locale cụ thể và cố định môi trường test.

## 14. Chọn formatter phù hợp

- Dùng **NumberStyleFormatter** cho số tổng quát cần parse/print theo locale hoặc pattern.
- Dùng **CurrencyStyleFormatter** cho số tiền; đặt currency và rounding mode theo chính sách.
- Dùng **PercentStyleFormatter** cho tỷ lệ lưu theo ratio và hiển thị theo percent style.
- Dùng **@NumberFormat** khi mỗi field của form cần style khai báo riêng.
- Dùng **FormatterRegistry/WebMvcConfigurer** khi muốn tích hợp formatter vào MVC binding.
- Dùng converter/deserializer riêng khi format đầu vào có contract khác formatter mặc định.

**Ghi nhớ:** NumberStyleFormatter format số; CurrencyStyleFormatter format số tiền; PercentStyleFormatter format tỷ lệ. Cả ba parse/print theo locale và hỗ trợ BigDecimal. Hãy xác định locale, currency, scale và rounding trước; tiếp tục kiểm tra validation/domain rules sau khi parse.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 – Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html): Formatter, locale và annotation formatting.
- [NumberStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html): number style, BigDecimal parsing và pattern.
- [CurrencyStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html): currency, fraction digits và rounding mode.
- [PercentStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/PercentStyleFormatter.html): percent style và BigDecimal parsing.
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): đăng ký formatter/converter qua WebMvcConfigurer.
