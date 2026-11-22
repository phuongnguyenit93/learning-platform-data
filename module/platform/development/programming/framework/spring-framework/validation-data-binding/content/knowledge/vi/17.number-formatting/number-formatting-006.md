# Tiền tệ, đơn vị và dữ liệu được phép nhập trong Spring Formatting

Khi một form nhận giá, số lượng hoặc đại lượng đo, ứng dụng phải giải quyết ba vấn đề khác nhau:

1. **Định dạng (formatting):** hiển thị một giá trị theo locale, ví dụ `1,234.50 $` hoặc `1.234,50 $`; đọc chuỗi người dùng nhập thành kiểu Java.
2. **Mô hình hóa tiền tệ/đơn vị:** lưu số tiền kèm mã tiền tệ và lưu số đo kèm đơn vị, thay vì chỉ giữ một con số không có ngữ nghĩa.
3. **Kiểm soát dữ liệu được phép nhập:** giới hạn mã tiền tệ/đơn vị, số chữ số, miền giá trị và quy tắc nghiệp vụ.

Trong Spring Framework, `Formatter<T>` kết hợp `Parser<T>` và `Printer<T>` để chuyển chuỗi ⇄ object theo `Locale`. `@NumberFormat` cung cấp định dạng số/tiền tệ theo style hoặc pattern. `Formatter` và `@NumberFormat` hỗ trợ **cách đọc/hiển thị**; chúng không thay thế validation, allowlist hay authorization.

Bài này trình bày cách lựa chọn kiểu dữ liệu, định dạng tiền tệ, xử lý đơn vị, đăng ký formatter và giới hạn đầu vào; có ví dụ Java 17+ chạy bằng Maven và phần tích hợp Spring MVC.

## 1. Tách biệt bốn khái niệm

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị số** | Có bao nhiêu? | `1234.50` |
| **Tiền tệ** | Số tiền đó thuộc đồng nào? | `EUR`, `USD`, `VND` |
| **Đơn vị đo** | Đại lượng đang tính theo đơn vị nào? | `kg`, `g`, `L`, `m` |
| **Quy tắc nhập** | Giá trị nào được chấp nhận? | `amount > 0`; currency chỉ nhận `USD/EUR/VND` |

Không nên coi ký hiệu `$`, `€` hay `₫` là một phần định danh đủ tin cậy của tiền tệ. Ký hiệu có thể trùng nhau, thay đổi theo locale và không luôn cho biết mã ISO chính xác. Ví dụ `$` có thể chỉ USD, CAD, AUD hoặc một số đồng khác tùy ngữ cảnh.

Tương tự, số `10` không mang ý nghĩa rõ ràng nếu thiếu đơn vị: 10 kg khác 10 g; 10 lít khác 10 ml.

**Mô hình tốt thường lưu dữ liệu tách biệt:**

~~~text
Money
  amount   = BigDecimal("1234.50")
  currency = Currency("EUR")

Quantity
  amount   = BigDecimal("2.5")
  unit     = "kg"
~~~

Lớp trình bày mới định dạng chúng thành chuỗi phù hợp với người dùng. Dữ liệu lưu trữ và logic nghiệp vụ không nên phụ thuộc vào việc người dùng đang nhìn thấy dấu phẩy, dấu chấm, khoảng trắng hay ký hiệu tiền tệ nào.

## 2. Vì sao tiền tệ nên dùng BigDecimal?

Tiền tệ là dữ liệu số cần kiểm soát độ chính xác. Với giá trị thập phân, không nên dùng `float` hoặc `double` làm kiểu lưu trữ/ tính toán tiền chính vì các kiểu nhị phân này không biểu diễn chính xác mọi số thập phân.

Ví dụ:

~~~java
System.out.println(0.1 + 0.2);
System.out.println(new BigDecimal("0.1").add(new BigDecimal("0.2")));
~~~

Kết quả minh họa:

~~~text
0.30000000000000004
0.3
~~~

Dùng `new BigDecimal("0.1")` hoặc tạo từ dữ liệu thập phân chính xác; tránh `new BigDecimal(0.1)` vì lúc đó sai số nhị phân của `double` đã đi vào giá trị BigDecimal.

### Mô hình Money tối thiểu

~~~java
public record Money(BigDecimal amount, Currency currency) {
}
~~~

Đây là record minh họa, cần import `java.math.BigDecimal` và `java.util.Currency`. Nó giữ cả số tiền và mã tiền tệ. Hai khoản `10 USD` và `10 EUR` không nên được coi là cùng một giá trị tiền tệ chỉ vì cùng có amount bằng 10.

Khi thiết kế đầy đủ, cần quyết định:

- Có cho phép amount âm không (ví dụ khoản hoàn tiền, bút toán điều chỉnh)?
- Thang độ chính xác/scale nào được chấp nhận cho từng currency?
- Quy tắc làm tròn là gì khi tính thuế, chia tiền hoặc quy đổi?
- Có cho phép cộng hai khoản khác currency không? Thông thường cần cùng currency hoặc một quy trình FX rõ ràng.
- Có giới hạn số tiền tối đa và tối thiểu ở tầng nghiệp vụ không?

`BigDecimal` không tự biết quy tắc scale của một currency. `Currency.getDefaultFractionDigits()` cung cấp số chữ số thập phân mặc định theo metadata tiền tệ của JDK, nhưng nghiệp vụ vẫn phải quyết định cách làm tròn và các ngoại lệ. Không nên tự giả định mọi currency có hai chữ số thập phân.

## 3. Locale và Currency là hai thứ khác nhau

`Locale` mô tả quy ước ngôn ngữ/vùng, ví dụ cách viết số và vị trí ký hiệu. `Currency` xác định đồng tiền cụ thể, ví dụ mã `EUR` hoặc `USD`.

| Locale | Currency | Một kiểu hiển thị có thể gặp |
| --- | --- | --- |
| `Locale.US` | USD | `$1,234.50` |
| `Locale.GERMANY` | EUR | `1.234,50 €` |
| `Locale.FRANCE` | EUR | `1 234,50 €` |
| `Locale.US` | EUR | `€1,234.50` hoặc dạng phụ thuộc formatter/JDK |

Cột trên là ví dụ định dạng theo locale/JDK; vị trí ký hiệu và khoảng trắng cụ thể có thể khác phiên bản runtime. **Locale không tự quyết định currency của giao dịch.** Một người ở Đức có thể mua hàng bằng USD; người ở Mỹ có thể thanh toán bằng EUR.

Với một khoản tiền thực tế, cần chọn currency từ hợp đồng giao dịch hoặc dữ liệu server tin cậy. Không suy ra đồng tiền lưu trữ chỉ từ `Locale.getDefault()` của máy chủ.

Nếu client gửi `currency=USD`, ứng dụng phải kiểm tra đồng tiền đó có được phép cho nghiệp vụ, tài khoản, sản phẩm và người dùng hiện tại hay không.

## 4. @NumberFormat: định dạng number và currency trong Spring

Spring cung cấp annotation `org.springframework.format.annotation.NumberFormat` cho các field kiểu `Number` như `Integer`, `Long`, `Double`, `BigDecimal`.

Ví dụ:

~~~java
public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal unitPrice;

    @NumberFormat(pattern = "#,##0.000")
    private BigDecimal quantity;

    // Getter/setter...
}
~~~

Đây là **đoạn class minh họa**; cần import annotation Spring, `java.math.BigDecimal` và các getter/setter phù hợp. `@NumberFormat` có hai cách cấu hình chính:

- `style`: chọn style số phổ biến như `DEFAULT`, `NUMBER`, `PERCENT` hoặc `CURRENCY`.
- `pattern`: chỉ định pattern định dạng số cụ thể.

Hai thuộc tính `style` và `pattern` là hai lựa chọn thay thế; khi chỉ định `pattern` thì pattern được ưu tiên. Định dạng style dựa trên locale của người dùng/context. Tài liệu Javadoc của Spring nêu các kiểu tiền tệ có thể mặc định sử dụng currency style đối với các kiểu tiền tương ứng; ứng dụng cần test đúng field type và runtime.

### @NumberFormat không biến BigDecimal thành Money

Nếu field là `BigDecimal` và annotate `@NumberFormat(style=CURRENCY)`, formatter biết **định dạng số theo currency style của locale**. Nó không tự bổ sung một thuộc tính `Currency` vào object và không bảo đảm biết đồng tiền giao dịch cụ thể là gì.

Đối với domain model cần giữ mã tiền tệ, nên có object `Money(amount, currency)` và formatter/converter dành riêng cho kiểu đó. Có thể dùng `@NumberFormat` cho amount khi currency đã được xác định bằng nguồn dữ liệu tin cậy và quy tắc hiển thị đã rõ.

### Chọn pattern có chủ đích

Ví dụ `pattern="#,##0.00"` có thể yêu cầu hai chữ số thập phân trong cách hiển thị theo quy tắc DecimalFormat. Nhưng một pattern không giải quyết các quy tắc nghiệp vụ như:

- Có cho phép nhập nhiều hơn hai chữ số thập phân không?
- Dữ liệu có được làm tròn hay phải từ chối?
- Currency này có fraction digits bằng 0 hay 3?
- Có chấp nhận số âm không?

Hãy xác định riêng quy tắc nhập và lưu trữ. Format pattern chủ yếu là quy tắc biểu diễn/parse.

## 5. Đơn vị đo: không chỉ là hậu tố hiển thị

Một đại lượng đo nên gắn với đơn vị rõ ràng:

~~~java
public record Quantity(BigDecimal value, String unit) {
}
~~~

Đây là kiểu minh họa. Nếu chỉ lưu `BigDecimal value`, hệ thống không biết số ấy là kg, g, L, ml hay một đại lượng khác.

Một cách mô hình hóa tốt hơn là dùng enum cho các đơn vị **được hệ thống hỗ trợ**:

~~~java
public enum MassUnit {
    KG, G
}
~~~

Với unit enum, dữ liệu ngoài hệ thống phải được parse theo allowlist:

~~~java
MassUnit unit = MassUnit.valueOf(input.toUpperCase(Locale.ROOT));
~~~

Đây là đoạn code ngắn, cần import `java.util.Locale`. Trong ứng dụng thật, nên bắt `IllegalArgumentException` hoặc dùng một parser trả lỗi có ý nghĩa. Không chấp nhận mọi chuỗi tùy ý làm unit vì việc đó tạo ra dữ liệu không thể tính toán/so sánh nhất quán.

### Quy đổi đơn vị phải có định nghĩa

Ví dụ khối lượng:

- `1 kg = 1000 g`
- `1 g = 0.001 kg`

Hai đại lượng `500 g` và `0.5 kg` có cùng lượng vật chất nhưng chuỗi khác nhau. Nếu muốn so sánh/tính tổng, cần quy đổi về một đơn vị chuẩn trước khi tính hoặc dùng thư viện unit-of-measure có định nghĩa dimension/quantity rõ ràng.

Đừng cộng `2 kg + 300 g` bằng cách cộng số thuần thành 302. Cần đổi `300 g` thành `0.3 kg` trước.

**Đơn vị không tương thích dimension:** kg không thể đổi sang lít nếu không có thông tin về mật độ/chất liệu; m không thể cộng với kg. Kiểu dữ liệu và API domain nên ngăn các phép toán vô nghĩa này.

### Có thể dùng một Formatter cho từng kiểu Quantity

Formatter có thể parse chuỗi `"2.5 kg"` thành `Quantity(value=2.5, unit=KG)`, nhưng phải xác định:

- Locale dùng dấu thập phân nào?
- Chuỗi đơn vị có được viết hoa/thường linh hoạt?
- Có khoảng trắng bắt buộc giữa số và unit không?
- Có cho phép đơn vị ngoài allowlist không?
- Printer in unit theo mã kỹ thuật (`kg`) hay tên địa phương hóa (`kilogram`)?

Tách number parsing và unit parsing sẽ dễ test hơn một regex phức tạp. Với yêu cầu lớn, cân nhắc thư viện unit-of-measure chuyên biệt thay vì tự phát triển engine đơn vị tổng quát.

## 6. Định dạng một Money bằng Formatter<T>

Để thấy rõ currency và locale, ta triển khai `Formatter<Money>` với quy ước:

- `Money` chứa `BigDecimal amount` và `Currency currency`.
- Formatter được tạo với **một currency cố định** cho field/giao dịch đã xác định trước.
- Người dùng nhập phần số, ví dụ `1,234.50` theo locale US; chuỗi không cần ký hiệu currency.
- Printer hiển thị ký hiệu tiền tệ theo locale, nhưng currency được cố định từ cấu hình domain.
- Không dùng locale để tự quyết định đồng tiền được phép.

Việc nhận amount không kèm ký hiệu trong ví dụ có chủ đích: tránh mơ hồ khi cùng ký hiệu `$` có thể đại diện cho nhiều currency.

### 6.1. Mã formatter hoàn chỉnh

~~~java
package example;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class MoneyFormatter implements Formatter<MoneyFormatter.Money> {

    public record Money(BigDecimal amount, Currency currency) {
    }

    private final Currency currency;

    public MoneyFormatter(Currency currency) {
        this.currency = currency;
    }

    @Override
    public Money parse(String text, Locale locale) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("Amount is required");
        }

        NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
        if (!(numberFormat instanceof DecimalFormat decimalFormat)) {
            throw new IllegalStateException(
                    "This example requires DecimalFormat");
        }

        decimalFormat.setParseBigDecimal(true);
        ParsePosition position = new ParsePosition(0);
        Number parsed = decimalFormat.parse(text.trim(), position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.trim().length()) {
            throw new IllegalArgumentException(
                    "Amount is not valid for locale " + locale);
        }

        return new Money(amount, currency);
    }

    @Override
    public String print(Money money, Locale locale) {
        if (money == null) {
            return "";
        }
        if (!currency.equals(money.currency())) {
            throw new IllegalArgumentException("Unexpected currency");
        }

        NumberFormat format = NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(currency);
        return format.format(money.amount());
    }
}
~~~

Đây là class formatter hoàn chỉnh. Trong Java 17, pattern matching với `instanceof DecimalFormat decimalFormat` dùng được. `DecimalFormat#setParseBigDecimal(true)` giúp parse sang `BigDecimal` thay vì mất độ chính xác qua `double`. `ParsePosition` được kiểm tra để tránh nhận chuỗi chỉ parse được một phần.

Một số quyết định trong ví dụ cần hiểu rõ:

- Currency được truyền vào constructor, không lấy từ chuỗi ký hiệu tiền tệ.
- Parser chỉ nhận chuỗi số theo locale; nếu muốn client chọn currency, hãy parse mã ISO riêng rồi kiểm tra allowlist.
- Printer kiểm tra currency của Money khớp currency formatter; không âm thầm in một khoản EUR như thể nó là USD.
- Ví dụ dùng `NumberFormat`/`DecimalFormat` của JDK; dữ liệu sai bị từ chối. Quy tắc chấp nhận dấu grouping cụ thể còn phụ thuộc locale và JDK, nên cần test các chuỗi biên trong hệ thống thật.

### 6.2. Chương trình chạy kiểm tra round-trip

Tạo file `src/main/java/example/MoneyFormattingDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.support.DefaultFormattingConversionService;

public class MoneyFormattingDemo {

    public static void main(String[] args) {
        Currency eur = Currency.getInstance("EUR");
        MoneyFormatter formatter = new MoneyFormatter(eur);

        MoneyFormatter.Money money =
                formatter.parse("1,234.50", Locale.US);

        String us = formatter.print(money, Locale.US);
        String germany = formatter.print(money, Locale.GERMANY);

        System.out.println("amount=" + money.amount().toPlainString());
        System.out.println("currency=" + money.currency().getCurrencyCode());
        System.out.println("us=" + us);
        System.out.println("germany=" + germany);

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addFormatter(formatter);

        MoneyFormatter.Money fromService = conversionService.convert(
                "2,500.75", MoneyFormatter.Money.class);

        System.out.println(
                "service.amount=" + fromService.amount().toPlainString());

        try {
            formatter.parse("not-a-number", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Tên class và nested type được tham chiếu bằng `MoneyFormatter.Money`. Chương trình dùng trực tiếp `Formatter` và cũng đăng ký cùng formatter vào `DefaultFormattingConversionService` để minh họa luồng chuyển đổi qua registry.

### 6.3. Maven dependency và cách chạy

Dự án cần JDK 17+ và Maven. Tạo file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>money-formatting-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp Java cần có trong cùng project:

- `src/main/java/example/MoneyFormatter.java`
- `src/main/java/example/MoneyFormattingDemo.java`

Chạy từ thư mục có `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.MoneyFormattingDemo
~~~

Đầu ra dự kiến của chương trình (không tính log Maven):

~~~text
amount=1234.50
currency=EUR
us=€1,234.50
germany=1.234,50 €
service.amount=2500.75
invalid=IllegalArgumentException
~~~

Dấu cách trước ký hiệu € trong output locale Đức có thể là **non-breaking space**; cách hiển thị chính xác phụ thuộc JDK/CLDR. Phần số, currency code và hành vi round-trip là điều cần kiểm tra trong test; không nên viết test so sánh chuỗi format cứng qua mọi JDK nếu môi trường có thể thay đổi dữ liệu locale.

## 7. Đăng ký formatter trong Spring MVC

Formatter có thể được đăng ký tập trung qua `WebMvcConfigurer#addFormatters`:

~~~java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(
                new MoneyFormatter(Currency.getInstance("EUR")));
    }
}
~~~

Đây là **đoạn cấu hình**, cần import `@Configuration`, `WebMvcConfigurer`, `FormatterRegistry` và `Currency`. Currency EUR ở đây là currency cố định cho ví dụ; trong ứng dụng thật, không nên áp dụng EUR cho mọi giao dịch nếu người dùng/sản phẩm có currency khác. Có thể đăng ký formatter theo type hoặc theo field, hoặc cung cấp một resolver/service quyết định currency từ ngữ cảnh giao dịch tin cậy.

Khi Spring MVC nhận một DTO có property `MoneyFormatter.Money`, `WebDataBinder`/`ConversionService` có thể dùng formatter để parse giá trị form và printer để định dạng object. Việc chọn currency cho một giao dịch phải diễn ra theo hợp đồng của endpoint, không lấy từ dấu hiệu hiển thị.

Với Spring Boot, chỉ nên thêm một web stack phù hợp. Dự án MVC dùng starter MVC/web tương ứng phiên bản Boot; sau đó cấu hình formatter theo cơ chế của Spring MVC. Không tạo một `DefaultFormattingConversionService` riêng trong controller rồi kỳ vọng nó tự thay đổi registry toàn ứng dụng.

### Field type và field annotation

Ngoài cấu hình theo type, Spring có annotation formatting như `@NumberFormat`. Ví dụ:

~~~java
public class PriceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal amount;

    // Getter/setter...
}
~~~

Đây là **đoạn class minh họa**. Import `org.springframework.format.annotation.NumberFormat`, không nhầm với `java.text.NumberFormat`. Hai class cùng tên nhưng khác package và mục đích.

Nếu muốn đăng ký quy tắc dựa trên annotation riêng, Spring có `AnnotationFormatterFactory`; factory trả `Parser` và `Printer` phù hợp với field type và annotation. Điều này hữu ích khi cùng kiểu Java có nhiều cách định dạng theo trường.

## 8. Dữ liệu được phép nhập: allowlist, range và precision

Định dạng đúng không có nghĩa dữ liệu hợp lệ. Ví dụ `"1,000.00"` có thể parse thành `BigDecimal("1000.00")`, nhưng giao dịch có được phép lên đến 1000 hay không là câu hỏi khác.

### 8.1. Currency allowlist

Giả sử endpoint chỉ cho phép `USD`, `EUR` và `VND`:

~~~java
private static final Set<String> ALLOWED_CURRENCIES =
        Set.of("USD", "EUR", "VND");

static Currency parseAllowedCurrency(String code) {
    if (code == null || !ALLOWED_CURRENCIES.contains(code)) {
        throw new IllegalArgumentException("Currency is not allowed");
    }
    return Currency.getInstance(code);
}
~~~

Đây là đoạn code minh họa, cần import `java.util.Set` và `Currency`. Cách làm này kiểm tra **mã nằm trong danh sách cho phép**. Trong ứng dụng, danh sách nên đến từ cấu hình/kiến thức nghiệp vụ đáng tin cậy; có thể còn cần giới hạn currency theo người dùng, tài khoản, sản phẩm hoặc quốc gia.

Không chấp nhận bất kỳ mã ISO tồn tại nào nếu nghiệp vụ không hỗ trợ mã đó. “Mã hợp lệ về mặt chuẩn” khác với “được phép dùng trong giao dịch này”.

### 8.2. Giới hạn số tiền và chữ số

Với Jakarta Bean Validation, có thể dùng:

~~~java
public record PaymentRequest(
        @NotNull
        @DecimalMin(value = "0.01")
        @Digits(integer = 12, fraction = 2)
        BigDecimal amount,

        @NotBlank
        String currency) {
}
~~~

Đây là **record DTO minh họa**, cần import `jakarta.validation.constraints.*`, cấu hình provider và kích hoạt validation bằng `@Valid`/`@Validated` tại điểm phù hợp. Constraint trong ví dụ cho phép số tiền từ 0.01 trở lên, tối đa 12 chữ số phần nguyên và 2 chữ số phần lẻ. Đây là chính sách của ví dụ, không phải quy tắc chung cho mọi currency. Đối với VND hoặc currency có fraction digits khác, cần quy định precision phù hợp theo nghiệp vụ.

Nếu cho phép hoàn tiền/bút toán điều chỉnh âm, `@DecimalMin("0.01")` có thể sai với use case đó. Hãy viết DTO/constraint theo từng hành động, không áp dụng một quy tắc “giá phải dương” cho mọi nghiệp vụ.

### 8.3. Kiểm tra đơn vị cho phép

Với khối lượng chỉ hỗ trợ kg và g:

~~~java
enum MassUnit {
    KG, G
}
~~~

Client gửi `unit` phải được chuyển sang enum hoặc lookup từ danh sách cấu hình. Nếu gửi `LB` hoặc `STONE` mà ứng dụng chưa hỗ trợ, từ chối với thông báo có ý nghĩa. Đừng lưu unit lạ dưới dạng chuỗi rồi để các bước tính toán sau tự đoán.

Tương tự, lượng đo còn cần kiểm tra dimension: không cho dùng đơn vị khối lượng cho trường thể tích.

### 8.4. Giới hạn số lượng, bước nhảy và miền dữ liệu

Một số field cần quy tắc ngoài min/max:

- Số lượng hàng có thể là số nguyên dương (`@Min(1)`).
- Khối lượng có thể cần tối thiểu, tối đa và precision riêng.
- Giá có thể cho phép scale hai chữ số; phí FX có thể nhiều chữ số hơn.
- Phần trăm có thể giới hạn `0..100` hoặc một miền khác theo nghiệp vụ.
- Đơn vị cần nằm trong allowlist và tương thích với loại đại lượng.
- Ngày/giờ cần giới hạn trong khoảng có ý nghĩa cho giao dịch.

Spring Formatter giúp **parse/print**; Jakarta Bean Validation/validator/service quyết định các ràng buộc này.

## 9. Làm tròn tiền: quy định tại đúng bước nghiệp vụ

`BigDecimal` hỗ trợ các chế độ làm tròn qua `RoundingMode`. Ví dụ:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

Đây là đoạn code minh họa, cần import `java.math.RoundingMode`. `HALF_EVEN` là một lựa chọn làm tròn, không phải mặc định đúng cho mọi pháp nhân/thuế/tiền tệ. Các chính sách khác có thể cần `HALF_UP`, `DOWN` hoặc không làm tròn ở bước lưu trung gian.

Các quy tắc:

1. Quyết định precision của số tiền dựa trên currency và quy trình nghiệp vụ.
2. Chỉ làm tròn tại điểm nghiệp vụ đã định (ví dụ mỗi dòng hóa đơn, tổng hóa đơn hoặc lúc thanh toán); các cách này có thể cho kết quả khác.
3. Ghi rõ rounding mode trong code, không dựa vào default ngầm.
4. Test với giá trị đúng giữa hai mức làm tròn, số âm (nếu được phép), số có nhiều chữ số và các currency có minor unit khác nhau.
5. Không dùng formatter để làm tròn âm thầm dữ liệu lưu trữ. In hai chữ số thập phân không có nghĩa amount gốc đã được làm tròn đúng.

## 10. Kiểm thử định dạng và dữ liệu nhập

Một bộ test tốt cần kiểm tra ít nhất bốn nhóm:

| Nhóm | Input/test | Kết quả mong muốn |
| --- | --- | --- |
| Parse hợp lệ | Số theo locale đúng, amount nằm trong miền | Object có BigDecimal/Currency/unit chính xác |
| Locale khác nhau | US, Germany, France hoặc locale sản phẩm hỗ trợ | Parse/print theo đúng quy ước |
| Parse sai | Chuỗi chữ, chuỗi parse được một phần, grouping sai theo hợp đồng | Từ chối, ghi nhận lỗi field |
| Domain validation | Currency/unit không allowlist, amount ngoài range, scale quá lớn | Validation/business rule từ chối |

Ví dụ test logic cần xác nhận:

- `parse("1,234.50", Locale.US)` cho amount `1234.50`.
- `print(money, Locale.GERMANY)` hiển thị cùng một amount/currency theo quy ước Đức.
- `parse("abc", Locale.US)` bị từ chối.
- `currency="CAD"` bị từ chối nếu CAD không nằm trong allowlist.
- `unit="LB"` bị từ chối nếu ứng dụng chỉ hỗ trợ KG/G.
- Amount `0.001` bị từ chối nếu DTO quy định tối đa 2 chữ số phần lẻ.

Không chỉ test formatter độc lập; còn cần test registry, DataBinder/controller và validation pipeline để chắc chắn formatter được dùng ở đúng scope.

### Lưu ý về kết quả locale giữa các JDK

Dữ liệu locale có thể được cập nhật theo JDK/CLDR. Dấu cách không ngắt dòng, vị trí ký hiệu và dấu phân tách có thể khác. Với giao diện người dùng, nên test theo runtime triển khai; với API/máy móc, ưu tiên chuỗi chuẩn hóa và mã currency/unit riêng thay vì phụ thuộc chuỗi hiển thị địa phương hóa.

## 11. Những lỗi phổ biến

### Dùng Double cho tiền

Sai số nhị phân có thể làm kết quả cộng/trừ bất ngờ. Dùng `BigDecimal` hoặc kiểu tiền chuyên biệt với quy tắc rõ.

### Chỉ lưu ký hiệu tiền tệ

`$` không đủ để xác định currency. Lưu mã như `USD`, `CAD` hoặc `AUD` theo hợp đồng giao dịch.

### Để Locale quyết định currency giao dịch

Locale chỉ phản ánh quy ước hiển thị; người dùng ở Đức vẫn có thể giao dịch USD. Xác định currency từ server/domain và kiểm tra allowlist.

### Nhập số theo locale nhưng parse bằng locale mặc định của server

`1,234.50` và `1.234,50` có cách hiểu khác nhau. Dùng locale đúng của request/user và test nhiều locale.

### Dùng @NumberFormat như validation

`@NumberFormat` không bảo đảm amount thuộc khoảng cho phép, currency được phép hay đơn vị đúng. Thêm Bean Validation và kiểm tra domain.

### Dùng pattern cố định cho mọi loại currency

Không phải đồng nào cũng có hai chữ số phần lẻ. Scale và rounding phải dựa trên quy tắc currency/nghiệp vụ, không chỉ mẫu hiển thị.

### Lưu unit dưới dạng chuỗi tự do

Chuỗi tùy ý tạo ra unit không thể quy đổi. Dùng enum/allowlist hoặc thư viện unit-of-measure có định nghĩa dimension.

### Formatter tự động đổi currency/unit theo ký hiệu trong input

Dấu `$` hoặc `€` có thể mơ hồ. Chọn currency/unit qua field riêng và kiểm tra server-side; hoặc xác định hợp đồng input bao gồm mã rõ ràng như `USD 10.00`.

### Làm tròn trong printer

Printer có thể hiển thị số chữ số theo style, nhưng không nên làm thay đổi amount nghiệp vụ. Làm tròn ở service/domain theo chính sách được ghi nhận.

### Chỉ kiểm tra format mà quên giới hạn kích thước

Một chuỗi cực dài hoặc số mũ lớn có thể tạo dữ liệu tốn tài nguyên hoặc vượt logic nghiệp vụ. Giới hạn độ dài input, precision, scale và miền số ở tầng request/domain phù hợp.

## 12. Checklist và câu hỏi tự kiểm tra

**Checklist thiết kế:**

1. Lưu tiền bằng kiểu chính xác như `BigDecimal`, đi kèm mã `Currency`; không dựa vào ký hiệu hiển thị.
2. Lưu đại lượng kèm unit và dimension phù hợp; xác định rõ quy đổi được phép.
3. Chọn `@NumberFormat` cho trường số thông dụng, hoặc `Formatter<T>` cho value object/currency/unit đặc thù.
4. Nhận `Locale` đúng context; không lấy locale server làm chính sách giao dịch.
5. Parse đầy đủ input; từ chối chuỗi sai hoặc parse được một phần.
6. Kiểm tra allowlist cho currency/unit, range, digits, sign, max length và quyền thao tác.
7. Quy định rounding mode và thời điểm làm tròn ở domain/service.
8. Test formatter, ConversionService, DataBinder/controller, validation và nhiều locale trên runtime thật.

**Câu hỏi tự kiểm tra:**

1. Vì sao `BigDecimal` phù hợp với tiền tệ hơn `double`?
2. `Locale.US` có bắt buộc giao dịch phải dùng USD không? Vì sao?
3. `@NumberFormat(style=CURRENCY)` có lưu mã currency vào object không?
4. Vì sao một giá trị `10` phải gắn với đơn vị trước khi so sánh/cộng?
5. Nếu client gửi currency `CAD` nhưng API chỉ hỗ trợ USD/EUR, lớp nào phải từ chối?
6. Khi nào dùng `Formatter<Money>` thay vì `@NumberFormat` trên `BigDecimal`?
7. Vì sao không nên để printer quyết định quy tắc làm tròn tiền?
8. Cùng một amount/currency, vì sao chuỗi hiển thị ở US và Đức có thể khác?

**Ghi nhớ:** định dạng quyết định **cách đọc và hiển thị**, model tiền tệ/đơn vị quyết định **giá trị mang ý nghĩa gì**, còn allowlist/validation/authorization quyết định **dữ liệu nào được phép dùng**. Tách ba trách nhiệm này giúp ứng dụng xử lý chính xác số tiền và đại lượng đo khi người dùng ở nhiều locale.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework Reference — ConversionService](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Javadoc — NumberFormat](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [Spring Framework Javadoc — CurrencyStyleFormatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html)
- [Spring Framework Javadoc — NumberStyleFormatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html)
- [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
