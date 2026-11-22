# Kiểm tra tính nhất quán giữa `parse` và `print` khi định dạng số trong Spring Framework

## 1. Mục tiêu và bối cảnh

Trong form nhập liệu, cùng một số có thể được **in ra để người dùng đọc** và **đọc ngược từ chuỗi người dùng gửi lên**. Ví dụ, giá trị `BigDecimal("1234.50")` có thể hiển thị là `1,234.50` theo `en-US`, nhưng là `1.234,50` theo `de-DE`. Nếu hai chiều không thống nhất, form có thể hiển thị đúng nhưng lưu sai số, làm mất chữ số thập phân hoặc báo lỗi khi gửi lại chính giá trị vừa hiển thị.

Sau bài này, bạn cần:
- Phân biệt `print(value, locale)` với `parse(text, locale)` và nhận diện nơi Spring sử dụng chúng trong data binding.
- Xây dựng hai phép kiểm tra round-trip đúng: **giá trị → chuỗi → giá trị** và **chuỗi → giá trị → chuỗi chuẩn hóa**.
- Kiểm tra locale, dấu phân nhóm, độ chính xác, quy tắc làm tròn, input không hợp lệ và lỗi binding.
- Viết test ở cả mức `Formatter` và đường chuyển đổi thực tế của Spring, không dựa duy nhất vào việc quan sát giao diện.

Phạm vi bài là **tính nhất quán parse/print của số** trong Spring Framework, nhất là form và data binding. Việc kiểm tra khoảng giá trị, điều kiện nghiệp vụ hoặc dữ liệu JSON là các lớp trách nhiệm khác.

## 2. `parse` và `print` thực sự làm gì?

Spring định nghĩa `Formatter<T>` bằng cách kết hợp hai giao diện:

```java
public interface Printer<T> {
    String print(T value, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

Đây là **chữ ký rút gọn để giải thích**, không phải file Java độc lập. Trong Spring, các giao diện nằm ở package `org.springframework.format`.

- `print`: nhận một giá trị đã có kiểu (`BigDecimal`, `Integer`...) và `Locale`, trả chuỗi dùng trong giao diện.
- `parse`: nhận chuỗi từ phía người dùng và `Locale`, trả đối tượng có kiểu hoặc báo lỗi.
- `Locale` là một phần của hợp đồng: không được dùng `Locale.US` khi in rồi vô tình dùng `Locale.GERMANY` khi đọc ngược.
- `ConversionService` kết nối các bước chuyển kiểu. Với môi trường web, `DataBinder`/Spring MVC có thể dùng formatter được đăng ký để liên kết chuỗi yêu cầu với field.

Luồng đơn giản:

```text
Model BigDecimal  --print(value, locale)-->  Chuỗi trên form
Model BigDecimal  <--parse(text, locale)---  Chuỗi người dùng gửi
```

Spring có các formatter số như `NumberStyleFormatter`, `CurrencyStyleFormatter`, `PercentStyleFormatter` và annotation `@NumberFormat`. Chúng phục vụ những hợp đồng hiển thị khác nhau. `Converter<String, BigDecimal>` đơn thuần không diễn đạt hai chiều gắn với locale rõ ràng bằng `Formatter<BigDecimal>`.

## 3. Hai bất biến cần kiểm tra

Gọi `P_L(x) = print(x, L)` và `Q_L(s) = parse(s, L)` với cùng locale `L`.

### 3.1. Giá trị round-trip: `parse(print(value))`

Với mỗi giá trị `x` thuộc miền dữ liệu được formatter hỗ trợ:

```text
Q_L(P_L(x)) == x           (theo quan hệ tương đương đã định nghĩa)
```

Điều quan trọng nằm ở chữ **tương đương**:
- Nếu bài toán là số học, `BigDecimal.compareTo(...) == 0` kiểm tra cùng giá trị. `BigDecimal.equals(...)` còn so sánh `scale`: `1.0` và `1.00` bằng nhau về số học nhưng `equals` trả `false`.
- Nếu yêu cầu **tiền tệ luôn hai chữ số thập phân**, ngoài cùng giá trị còn phải kiểm tra `scale() == 2` hoặc quy tắc chuẩn hóa tương đương.
- Nếu cần giữ cả chữ số thập phân gốc, số âm `-0`, đơn vị hoặc cách ghi ban đầu, chỉ so sánh giá trị số là chưa đủ. Hãy xác định rõ thông tin nào bắt buộc được giữ.
- Với `double`/`float`, quy tắc về sai số phải được nêu riêng; không tùy tiện dùng `==` cho phép tính số thực. Với lượng tiền chính xác, thường ưu tiên `BigDecimal`.

Ví dụ lỗi: nếu `print` làm tròn `1.23456` thành `"1.23"`, thì `parse` chỉ khôi phục `1.23`. Hai chiều không thể bảo toàn giá trị gốc. Đây là **quyết định mất độ chính xác**, không phải một lỗi mà parser có thể tự sửa.

### 3.2. Chuỗi round-trip: `print(parse(text))`

Không nên mặc định mọi chuỗi hợp lệ đều được in lại y hệt:

```text
P_L(Q_L(s)) = normalize_L(s)
```

`normalize_L` là cách biểu diễn chuẩn do formatter quy định. Ví dụ nếu chuẩn `en-US` yêu cầu nhóm hàng nghìn và hai số lẻ:

```text
"1234.5"  --parse-->  1234.50  --print-->  "1,234.50"
```

Đây là hành vi **nhất quán** vì chuỗi đầu vào được chuẩn hóa. Chỉ yêu cầu `P_L(Q_L(s)).equals(s)` khi `s` đã được xác định là chuỗi **canonical**. Với một formatter chuẩn hóa tốt, tính chất nên kiểm tra thêm là:

```text
normalize_L(normalize_L(s)) == normalize_L(s)
```

Nghĩa là chuẩn hóa lần thứ hai không đổi kết quả lần thứ nhất.

### 3.3. Đầu vào sai phải thất bại có chủ đích

Nếu chuỗi chứa ký tự thừa, trộn locale, vượt giới hạn chữ số thập phân hoặc không phải số, parser cần trả lỗi phù hợp với hợp đồng thay vì âm thầm chấp nhận một tiền tố.

Ví dụ: `123.45abc` tuyệt đối không được trở thành `123.45` nếu ứng dụng yêu cầu toàn bộ nội dung ô nhập phải là số. Khi dùng `java.text.DecimalFormat`, có thể kiểm tra `ParsePosition.getIndex() == text.length()` để bảo đảm không bỏ sót hậu tố. **Kiểm tra đã đọc hết chuỗi chưa đồng nghĩa với kiểm tra chặt mọi quy tắc đặt dấu nhóm**; nếu cần cú pháp canonical nghiêm ngặt, phải kiểm tra thêm.

## 4. Các tình huống dễ làm sai phép đối chiếu

| Tình huống | Sai lệch thường gặp | Cần kiểm tra |
| --- | --- | --- |
| Locale | `1,234` có thể mang nghĩa khác theo locale | In và parse cùng `Locale`; test các locale thực tế của sản phẩm |
| Dấu thập phân/nhóm | Đổi dấu `,` và `.` hoặc chấp nhận nhóm sai | Chuỗi hợp lệ, chuỗi không hợp lệ, tiêu thụ toàn bộ input |
| Làm tròn | Mất phần lẻ khi `print` giới hạn số chữ số | Test số ở ngay trước/sau ngưỡng làm tròn |
| `BigDecimal` scale | Giá trị đúng nhưng `equals` thất bại | Dùng `compareTo` cho số học; kiểm tra scale riêng |
| Kiểu đích | Parse số lớn rồi ép sang `int` gây tràn hoặc đổi nghĩa | Biên `Integer`/`Long`, số nguyên so với số lẻ |
| `%` và tiền tệ | Percent thường có phép nhân/chia 100; currency thêm ký hiệu, quy tắc làm tròn | Test đúng style, locale, ký hiệu và kiểu dữ liệu |
| Giá trị âm/zero | Mất dấu, số âm zero hoặc số rất nhỏ bị in thành `0` | Test âm, zero, cận 0 và giới hạn miền |
| Chuỗi trống | Binding có thể chuyển thành `null` tùy kiểu/cấu hình | Quy ước blank/null rõ ràng, test riêng ở tầng binding |
| Khoảng trắng/Unicode | Ký tự space, non-breaking space, dấu trừ Unicode khác nhau | Copy/paste thật, khoảng trắng đầu/cuối, ký tự phân nhóm |
| Cấu hình runtime | Locale mặc định, JDK locale data, formatter đăng ký khác kỳ vọng | Locale tường minh, kiểm thử trên JDK triển khai, test qua Spring |

Đừng suy đoán rằng số có `@NumberFormat` luôn tương đương với `NumberStyleFormatter` tự tạo: annotation, pattern, kiểu field và formatter đã đăng ký có thể chọn đường xử lý khác nhau. Hãy kiểm tra chính đường đi mà form đang sử dụng.

## 5. Ví dụ hoàn chỉnh: formatter cho số tiền hai chữ số thập phân

Giả định nghiệp vụ: lưu `BigDecimal` có chính xác hai chữ số phần thập phân; **không làm tròn ngầm** khi giá trị có quá hai chữ số. Khi hiển thị, dùng dấu nhóm hàng nghìn và dấu thập phân theo locale. Chuỗi đầu vào có thể thiếu dấu nhóm hoặc thiếu một chữ số lẻ; sau khi parse sẽ được chuẩn hóa về hai chữ số lẻ. Đây là một **hợp đồng cụ thể để kiểm thử**, không phải quy tắc mặc định cho mọi formatter của Spring.

Tạo project Maven Java 17+ với `pom.xml` sau:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>parse-print-consistency</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
        </plugins>
    </build>
</project>
```

Tạo file `src/main/java/demo/ParsePrintDemo.java`:

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;

public class ParsePrintDemo {

    static final class AmountFormatter implements Formatter<BigDecimal> {

        private DecimalFormat numberFormat(Locale locale) {
            DecimalFormat format = new DecimalFormat(
                    "#,##0.00",
                    DecimalFormatSymbols.getInstance(locale));
            format.setParseBigDecimal(true);
            format.setRoundingMode(RoundingMode.UNNECESSARY);
            return format;
        }

        @Override
        public String print(BigDecimal value, Locale locale) {
            // Không âm thầm cắt phần lẻ thứ ba.
            BigDecimal fixedScale = value.setScale(2, RoundingMode.UNNECESSARY);
            return numberFormat(locale).format(fixedScale);
        }

        @Override
        public BigDecimal parse(String text, Locale locale) throws ParseException {
            if (text == null || text.isBlank()) {
                throw new ParseException("Amount must not be blank", 0);
            }

            DecimalFormat format = numberFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number number = format.parse(text, position);

            if (number == null || position.getIndex() != text.length()) {
                throw new ParseException(
                        "Invalid amount or trailing characters",
                        Math.max(0, position.getIndex()));
            }

            try {
                // Chỉ chấp nhận giá trị biểu diễn được với hai chữ số lẻ.
                return ((BigDecimal) number).setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new ParseException("More than 2 fractional digits",
                        position.getIndex());
            }
        }
    }

    public static final class PaymentForm {
        private BigDecimal amount;

        public BigDecimal getAmount() {
            return amount;
        }

        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    private static void assertAmount(BigDecimal expected, BigDecimal actual) {
        if (actual == null || expected.compareTo(actual) != 0
                || actual.scale() != 2) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) throws ParseException {
        AmountFormatter formatter = new AmountFormatter();
        BigDecimal original = new BigDecimal("1234.50");

        for (Locale locale : new Locale[] {Locale.US, Locale.GERMANY}) {
            String printed = formatter.print(original, locale);
            BigDecimal parsed = formatter.parse(printed, locale);
            assertAmount(original, parsed);
            System.out.println(locale.toLanguageTag() + ": " + printed
                    + " -> " + parsed.toPlainString());
        }

        String canonical = formatter.print(
                formatter.parse("1234.5", Locale.US), Locale.US);
        if (!"1,234.50".equals(canonical)) {
            throw new AssertionError("Unexpected canonical output: " + canonical);
        }
        System.out.println("canonical: " + canonical);

        try {
            formatter.parse("1,234.50abc", Locale.US);
            throw new AssertionError("Trailing characters were accepted");
        } catch (ParseException expected) {
            // Pass: parser không bỏ qua phần đuôi sai.
        }

        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(formatter);

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            String display = service.convert(original, String.class);
            BigDecimal restored = service.convert(display, BigDecimal.class);
            if (!"1.234,50".equals(display)) {
                throw new AssertionError("Unexpected Spring output: " + display);
            }
            assertAmount(original, restored);
            System.out.println("spring: " + display + " -> "
                    + restored.toPlainString());

            PaymentForm form = new PaymentForm();
            DataBinder binder = new DataBinder(form);
            binder.setConversionService(service);
            binder.bind(new MutablePropertyValues(
                    Map.of("amount", "1.234,50")));
            if (binder.getBindingResult().hasErrors()) {
                throw new AssertionError(binder.getBindingResult().toString());
            }
            assertAmount(original, form.getAmount());
            System.out.println("binding: " + form.getAmount().toPlainString());

            PaymentForm invalidForm = new PaymentForm();
            DataBinder invalidBinder = new DataBinder(invalidForm);
            invalidBinder.setConversionService(service);
            invalidBinder.bind(new MutablePropertyValues(
                    Map.of("amount", "1.234,50xyz")));
            if (!invalidBinder.getBindingResult().hasFieldErrors("amount")) {
                throw new AssertionError("Expected amount binding error");
            }
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }

        System.out.println("checks: PASS");
    }
}
```

Chạy trong thư mục có `pom.xml` (Maven 3.9+, JDK 17+):

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.ParsePrintDemo
```

Đầu ra kỳ vọng khi chạy cùng các locale đã chỉ định:

```text
en-US: 1,234.50 -> 1234.50
de-DE: 1.234,50 -> 1234.50
canonical: 1,234.50
spring: 1.234,50 -> 1234.50
binding: 1234.50
checks: PASS
```

### Vì sao ví dụ được thiết kế như vậy?

1. `DecimalFormat` được **tạo mới cho mỗi lượt gọi**: tránh chia sẻ một instance mutable, vốn không bảo đảm thread-safe, giữa các request.
2. `DecimalFormatSymbols.getInstance(locale)` khiến dấu phân nhóm và thập phân phụ thuộc locale truyền vào, không vô tình dùng locale mặc định của máy.
3. `setParseBigDecimal(true)` giữ số ở dạng thập phân chính xác; không đi đường `double` rồi mất độ chính xác nhị phân.
4. `ParsePosition` kiểm tra parser đã tiêu thụ **hết** chuỗi; nó không tự kiểm tra chặt mọi cách đặt dấu phân nhóm.
5. `RoundingMode.UNNECESSARY` biến phép làm tròn ngoài hợp đồng thành lỗi rõ ràng. Giá trị như `1.234` không được giả vờ là `1.23`.
6. `LocaleContextHolder` được đặt và đặt lại bằng `finally` trong phần kiểm tra `ConversionService`/`DataBinder`, tránh rò locale qua luồng chạy test.
7. Test binding chứng minh cả đường đi Spring tạo field value và báo `FieldError`, ngoài hai phép gọi trực tiếp `formatter.print`/`formatter.parse`.

**Giới hạn có chủ đích của ví dụ:** formatter chấp nhận một số biến thể cú pháp mà `DecimalFormat` có thể parse hết, kể cả chuỗi thiếu dấu nhóm hoặc ít chữ số lẻ. Nếu nghiệp vụ bắt buộc chuỗi đầu vào đúng *duy nhất* định dạng hiển thị, sau khi parse thành công có thể so sánh `print(parsed, locale)` với `text` và từ chối nếu khác. Khi đó `"1234.5"` sẽ bị từ chối thay vì được chuẩn hóa. Quyết định này phải nhất quán với trải nghiệm người dùng. Ví dụ cũng chưa mô hình hóa tiền tệ, mã đơn vị hay giới hạn số tiền tối đa.

## 6. Dùng trong Spring MVC và `@NumberFormat`

Với form HTML, `WebMvcConfigurer.addFormatters(FormatterRegistry)` là một điểm đăng ký custom formatter. Đoạn sau là **trích đoạn cấu hình** (giả định đã chuyển `AmountFormatter` thành class dùng chung):

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new AmountFormatter());
    }
}
```

Các import tương ứng là `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry` và `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`; cấu hình web cần dependency Spring MVC. Khi form nhận chuỗi field `BigDecimal`, Spring MVC sử dụng hệ thống conversion/formatting được cấu hình, và `BindingResult` ghi nhận lỗi chuyển kiểu khi parse thất bại.

Một lựa chọn khác cho field cụ thể là annotation (trích đoạn model):

```java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;
```

Import `org.springframework.format.annotation.NumberFormat`. Annotation này mô tả cách định dạng số theo pattern. **Không giả định** nó có toàn bộ chính sách `RoundingMode.UNNECESSARY`, kiểm tra `scale` hoặc từ chối input của `AmountFormatter` tự viết. Nếu thay custom formatter bằng `@NumberFormat`, phải chạy lại cùng ma trận kiểm thử. Khi dùng cả annotation lẫn formatter được đăng ký, cần test đường chuyển đổi thực sự của field vì thứ tự và cách chọn formatter có thể khác điều dự đoán.

Trong ứng dụng, người dùng sửa form theo locale này rồi gửi lại theo locale khác có thể dẫn đến giá trị sai hoặc `typeMismatch`. Hãy có chính sách locale ổn định giữa lúc render và lúc submit; không dựa vào default locale của máy chủ. Với API JSON, số theo cú pháp JSON dùng dấu chấm thập phân theo chuẩn JSON; không đem format số theo locale của HTML form áp dụng cho JSON numeric payload.

## 7. Ma trận test nên có trong dự án

Mỗi case cần ghi rõ: **input**, **locale**, **kỳ vọng parse**, **kỳ vọng print/canonical**, **kiểu dữ liệu**, và **kết quả lỗi**.

| Nhóm | Dữ liệu nên thử | Kỳ vọng/điều cần phát hiện |
| --- | --- | --- |
| Cơ bản | `0.00`, `1.00`, `1234.50`, `-1234.50` | Giá trị round-trip đúng, dấu âm/scale được xử lý |
| Locale | `en-US`, `de-DE`, locale thực tế như `vi-VN` | Dấu nhóm và dấu thập phân đúng theo cấu hình/runtime |
| Chuẩn hóa | `1234.5`, `1234.50`, `1,234.50` (`en-US`) | Cùng giá trị; in về dạng chuẩn đã định |
| Chính xác | `0.01`, `999999999999.99`, số sát biên | Không tràn, không qua `double`, không mất chữ số |
| Từ chối làm tròn | `1.234` với formatter 2 số lẻ | Báo lỗi thay vì lặng lẽ ghi `1.23` |
| Ký tự thừa | `123.45abc`, `12%`, dấu phân cách lạ | Không nhận nhầm một phần chuỗi là toàn bộ số |
| Null/blank | `null`, `""`, `"   "` | Quy tắc rõ ở tầng form/binding và yêu cầu bắt buộc |
| Quy tắc nghiêm ngặt | `12,34.50` (`en-US`) | Nếu yêu cầu cú pháp canonical, thêm kiểm tra riêng; parse hết chưa đủ |
| Kiểu số khác | `Integer`, `Long`, `Double`, `BigDecimal` | Không giả định cùng chính sách precision/range |
| Spring integration | Chuỗi hợp lệ/không hợp lệ qua `DataBinder` hoặc MVC test | Field có giá trị đúng hoặc `BindingResult` có `FieldError` |
| Ranh giới vận hành | Nhiều request/locale song song, JDK và cấu hình triển khai | Không rò locale, không dùng chung `DecimalFormat` mutable |

**Tách ba tầng kiểm thử:**

1. **Formatter unit test:** gọi `print` và `parse` trực tiếp với `Locale` tường minh để xác nhận hợp đồng thuần.
2. **ConversionService/binding integration test:** xác nhận formatter được đăng ký đúng kiểu field, nhận locale đúng và tạo lỗi binding khi cần.
3. **MVC form test:** render giá trị lên giao diện, submit lại và kiểm tra `BindingResult`/giá trị model; bao gồm trường hợp locale thay đổi và dữ liệu người dùng dán từ nơi khác. Không thay thế các test này bằng test JSON serialization.

Với test có nhiều locale, nên truyền `Locale` trực tiếp khi test formatter; khi test Spring integration, luôn khôi phục `LocaleContextHolder` trong `finally` hoặc cơ chế teardown tương ứng. Tránh để một test tùy thuộc locale hay thứ tự chạy của test khác.

## 8. Cách chẩn đoán khi round-trip thất bại

Nếu `parse(print(x))` trả số khác:
1. Ghi lại **giá trị gốc cùng kiểu và scale**, locale, pattern, chuỗi đã in, giá trị parse và loại formatter thực sự được dùng.
2. Kiểm tra có bước làm tròn, chuyển `BigDecimal` sang `double`, giới hạn phần lẻ, áp dụng percent/currency hoặc ép kiểu số nguyên hay không.
3. So lại cùng locale và cùng cấu hình ở hai chiều; tái hiện bằng unit test độc lập.
4. Xác định đây là **mất thông tin được chấp nhận theo hợp đồng** hay lỗi cần sửa. Nếu mất thông tin là không được phép, sửa chiến lược print/kiểu dữ liệu trước.

Nếu `print(parse(s))` khác `s`:
1. Xác định `s` đã canonical hay mới chỉ là chuỗi hợp lệ cần chuẩn hóa.
2. So giá trị `parse(s)` và `parse(print(parse(s)))`; nếu số giữ nguyên và chuỗi thứ hai đã ổn định, đó có thể là chuẩn hóa đúng.
3. Nếu parser bỏ đuôi, nhận sai dấu phân cách, đổi nghĩa theo locale hoặc chấp nhận dữ liệu cấm, bổ sung xác thực cú pháp và test lỗi.

Nếu unit test đúng nhưng form sai, kiểm tra formatter/annotation nào được Spring chọn, kiểu field thực tế, locale resolver, `BindingResult`, `@InitBinder`/WebMvcConfigurer và sự khác biệt giữa render với submit. Một `@NotNull` hay `@DecimalMin` không thay thế việc parse đúng; Bean Validation đánh giá giá trị sau bước chuyển đổi, còn lỗi chuyển kiểu cần được kiểm tra ở tầng binding.

## 9. Checklist hoàn thành

- [ ] Viết rõ miền giá trị hợp lệ, locale, số chữ số thập phân, quy tắc làm tròn và dạng canonical.
- [ ] Kiểm tra `parse(print(x, L), L)` theo **quan hệ tương đương đúng của miền số**.
- [ ] Kiểm tra `print(parse(s, L), L)` là dạng chuẩn hóa và ổn định, không áp sai yêu cầu giống từng ký tự với input tự do.
- [ ] Có case locale, zero/âm/biên, precision/scale, input sai, ký tự thừa và blank.
- [ ] Không chia sẻ `DecimalFormat` mutable giữa luồng; test không phụ thuộc locale máy chủ.
- [ ] Có integration test cho formatter được Spring thực sự sử dụng và `BindingResult` khi parse lỗi.
- [ ] Khi đổi pattern, annotation, JDK hoặc locale resolver, chạy lại test cho cả hai chiều.

## Tài liệu đối chiếu

- Spring Framework — Spring Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — Spring MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Java SE — `DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE — `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
