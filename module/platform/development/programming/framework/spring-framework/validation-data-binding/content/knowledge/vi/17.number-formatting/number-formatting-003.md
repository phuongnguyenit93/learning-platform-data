# Mẫu số tùy chỉnh và ký hiệu phân cách theo Locale trong Spring

## 1. Vì sao cần mẫu số tùy chỉnh và Locale?

Một giá trị số Java có thể được hiển thị và nhập theo nhiều quy ước vùng miền. Ví dụ cùng giá trị 1234.50 có thể được biểu diễn:

| Locale | Biểu diễn thường gặp | Ý nghĩa dấu |
| --- | --- | --- |
| en-US | 1,234.50 | Phẩy phân nhóm hàng nghìn, chấm thập phân |
| de-DE | 1.234,50 | Chấm phân nhóm, phẩy thập phân |
| fr-FR | 1 234,50 | Dấu phân nhóm thường là khoảng trắng hẹp, phẩy thập phân |

Đây vẫn là cùng một giá trị số, nhưng chuỗi ký tự khác nhau theo Locale và quy ước định dạng. Nếu ứng dụng nhận 1.234,50 rồi parse bằng quy tắc en-US, kết quả có thể sai hoặc bị từ chối. Nếu code tự xóa dấu chấm/phẩy tùy tiện, dữ liệu có thể biến thành số khác.

Trong Spring, các thành phần chính liên quan gồm:

- **@NumberFormat**: khai báo pattern hoặc style định dạng cho field/property.
- **NumberStyleFormatter**: formatter số theo pattern và Locale.
- **CurrencyStyleFormatter**, **PercentStyleFormatter**: formatter theo kiểu tiền tệ/phần trăm.
- **FormattingConversionService**: tích hợp Formatter vào cơ chế ConversionService.
- **LocaleContextHolder** trong web request: cung cấp Locale theo ngữ cảnh request khi Spring MVC định dạng.

Cần phân biệt ba việc: cách hiển thị số; cách parse chuỗi người dùng; và quy tắc nghiệp vụ như số tiền dương, số chữ số thập phân tối đa hay giới hạn giá trị. Format không tự thay thế validation.

## 2. Cú pháp mẫu số của DecimalFormat

Spring formatter số dựa trên API format của Java, đặc biệt là **java.text.NumberFormat** và **java.text.DecimalFormat**. Pattern phổ biến dùng các ký hiệu sau:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| 0 | Chữ số bắt buộc; nếu thiếu sẽ hiển thị 0 | 000 |
| # | Chữ số tùy chọn; bỏ số 0 dư | ### |
| , | Dấu phân nhóm phần nguyên trong pattern không định vị | #,##0 |
| . | Dấu thập phân trong pattern không định vị | 0.00 |
| % | Nhân giá trị với 100 khi format | 0.00% |
| ‰ | Nhân với 1000 khi format | 0.0‰ |
| E | Ký hiệu số mũ khoa học | 0.00E0 |
| ; | Phân tách pattern dương và âm | #,##0.00;(#,##0.00) |
| ' | Bao ký tự đặc biệt để coi là literal | #,##0.00 'USD' |

Ví dụ với en-US:

| Pattern | Giá trị | Hiển thị |
| --- | ---: | --- |
| 0 | 7.2 | 7 |
| 0.00 | 7.2 | 7.20 |
| #,##0.## | 1234.5 | 1,234.5 |
| #,##0.00 | 1234.5 | 1,234.50 |
| 00000 | 42 | 00042 |
| #,##0.00;(#,##0.00) | -1234.5 | (1,234.50) |
| 0.0% | 0.125 | 12.5% |

### 2.1. Phân biệt 0 và #

0 giữ chữ số ở vị trí tối thiểu; # chỉ hiện chữ số nếu có dữ liệu tương ứng. Pattern 000.00 bảo đảm ít nhất ba chữ số phần nguyên và hai chữ số thập phân. Pattern #,##0.00 thường phù hợp báo cáo cần hai chữ số thập phân.

Số tài khoản 001234 là chuỗi định danh, không phải đại lượng số. Nếu lưu thành Number, số 0 đầu có thể bị mất và ý nghĩa dữ liệu thay đổi.

### 2.2. Grouping separator và decimal separator

Trong non-localized pattern, ký tự phẩy và chấm có ý nghĩa cú pháp nhất quán: phẩy chỉ grouping, chấm chỉ decimal. Khi tạo DecimalFormat với Locale, pattern được áp dụng cùng bộ DecimalFormatSymbols của Locale đó.

~~~java
new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
~~~

Cùng pattern nhưng symbols khác nhau nên 1234.5 lần lượt hiển thị 1,234.50 và 1.234,50. Đừng nhầm pattern không định vị với localized pattern. Không cần đảo ký tự pattern chỉ vì Locale Đức dùng ký hiệu hiển thị đảo chiều.

### 2.3. Phần trăm và per mille là phép nhân

Pattern 0.00% nhân giá trị với 100 khi format và chia theo hệ số tương ứng khi parse. Vì vậy 0.125 hiển thị thành 12.50%. Nếu database đã lưu 12.5 thay vì 0.125, việc gắn phần trăm có thể hiển thị thành 1250%. Hãy xác định quy ước lưu trữ trước khi chọn formatter.

## 3. Locale quyết định ký hiệu và cách đọc chuỗi

Locale ảnh hưởng:
- Decimal separator: ký tự phân cách phần nguyên và phần thập phân.
- Grouping separator: ký tự chia nhóm chữ số.
- Digit symbols và quy ước biểu diễn.
- Currency symbol khi dùng currency formatter.
- Một số style mặc định.

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat france = NumberFormat.getNumberInstance(Locale.FRANCE);
~~~

Với cùng BigDecimal 1234.50, format theo từng Locale tạo biểu diễn khác nhau. Dấu phân nhóm của Pháp có thể là khoảng trắng hẹp không ngắt dòng tùy JDK/CLDR; đừng hard-code ký tự hiển thị dựa trên một môi trường runtime.

### 3.1. Locale nguồn và Locale đích

Khi format để hiển thị, dùng Locale của người xem hoặc báo cáo. Khi parse dữ liệu gửi vào, dùng Locale mà hợp đồng đầu vào quy định. Hai Locale này có thể khác nhau.

Ví dụ trang web hiển thị theo vi-VN, nhưng API tích hợp yêu cầu định dạng cố định dùng dấu chấm thập phân và không có grouping. Không nên parse API theo Locale tùy ý lấy từ trình duyệt nếu API đã công bố format riêng.

Chuỗi 1,234 có thể được hiểu là một nghìn hai trăm ba mươi tư hoặc một phẩy hai ba bốn tùy quy ước. Nếu client thay Locale, không có cách đoán an toàn nếu hợp đồng không rõ.

### 3.2. Locale không xác định đơn vị

Locale Germany có thể cung cấp ký hiệu Euro trong currency style, nhưng điều đó không có nghĩa mọi BigDecimal đều là EUR. Số tiền cần currency code/đơn vị tường minh trong model hoặc API contract. Không dùng Locale để suy luận đơn vị kinh doanh.

## 4. Spring @NumberFormat và formatter số

### 4.1. Khai báo trên field/property

~~~java
public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal netAmount;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal grossAmount;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;

    // Getter và setter...
}
~~~

- **pattern** dành cho mẫu số do ứng dụng quy định.
- **style** có lựa chọn NUMBER, CURRENCY hoặc PERCENT.
- Với pattern cụ thể, formatter vẫn dùng Locale để xác định DecimalFormatSymbols khi parse/print.
- Annotation không áp dụng quy tắc min/max, scale nghiệp vụ hay currency code của entity.

### 4.2. NumberStyleFormatter

NumberStyleFormatter dùng NumberFormat theo Locale và có thể nhận pattern:

~~~java
NumberStyleFormatter formatter =
        new NumberStyleFormatter("#,##0.00");

String text = formatter.print(
        new BigDecimal("1234.5"), Locale.GERMANY);
~~~

Giá trị mong đợi là 1.234,50. Có thể parse với Locale tương ứng:

~~~java
Number value = formatter.parse("1.234,50", Locale.GERMANY);
~~~

Đây là lời gọi trực tiếp Formatter. Trong Spring MVC, Locale thường lấy từ LocaleContext của request. Kiểm thử parse trên đúng phiên bản Spring và Locale ứng dụng cấu hình.

### 4.3. CurrencyStyleFormatter và PercentStyleFormatter

- **CurrencyStyleFormatter** format số theo quy ước tiền tệ của Locale. Cần cân nhắc currency code, fraction digits và contract API.
- **PercentStyleFormatter** format theo quy ước phần trăm, với hệ số phần trăm tương ứng.
- **NumberStyleFormatter** phù hợp số thông thường và pattern tùy chỉnh.

Không sử dụng currency formatter để thay thế Money type hoặc mô hình tiền tệ. Giá trị tiền trong nghiệp vụ thường cần cả số tiền và mã đơn vị (EUR, USD, VND).

## 5. Ký hiệu phân cách tùy chỉnh ngoài Locale có sẵn

Nếu hệ thống có quy ước riêng, Java cho phép tạo **DecimalFormatSymbols**:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);

symbols.setDecimalSeparator(',');
symbols.setGroupingSeparator('.');
~~~

Sau đó:

~~~java
DecimalFormat format =
        new DecimalFormat("#,##0.00", symbols);
~~~

Kết quả ví dụ: 1234.5 hiển thị 1.234,50. Đây là cấu hình custom symbols; không nên làm tùy tiện vì chuỗi có thể không tương thích với Locale mặc định, file export hoặc API khác.

Các ký hiệu phải phân biệt được. Nếu decimal separator và grouping separator giống nhau, parser có thể không biết cách phân tách. Prefix/suffix dương/âm cũng cần khác biệt để parse dấu âm đúng. Nên cấu hình một bộ symbols cho mỗi hợp đồng định dạng và kiểm thử cả parse lẫn print.

### 5.1. Grouping size

Grouping size thường là 3 chữ số ở nhiều Locale, nhưng không phải mọi hệ thống đều nhóm theo ba. DecimalFormat cho phép thay grouping size:

~~~java
DecimalFormat format = new DecimalFormat("#,##0.00");
format.setGroupingSize(3);
~~~

Grouping size là số chữ số giữa các grouping separator. Nếu nghiệp vụ yêu cầu kiểu nhóm chữ số khác, cần kiểm tra Locale/implementation hoặc xây formatter phù hợp; không tự giả định mọi dấu phẩy đều phân nhóm giống nhau.

### 5.2. Prefix, suffix và literal

Có thể thêm literal vào pattern, ví dụ #,##0.00 'kg' hoặc ¤ #,##0.00 cho currency symbol. Ký tự đặc biệt cần quote bằng dấu nháy đơn để được coi là văn bản thường.

Pattern dương/âm có thể viết:

~~~text
#,##0.00;(#,##0.00)
~~~

Điều này hiển thị số âm trong ngoặc. Pattern âm chủ yếu xác định prefix/suffix; quy tắc số chữ số thường dùng chung với pattern dương.

Đơn vị vật lý, currency code hoặc phần trăm phải thống nhất với giá trị lưu trữ. Pattern chỉ kiểm soát cách thể hiện, không chứng minh đơn vị hay giá trị là đúng.

## 6. Làm tròn, scale và độ chính xác

DecimalFormat mặc định dùng **RoundingMode.HALF_EVEN**. Giá trị có nhiều chữ số lẻ hơn pattern hiển thị có thể được làm tròn.

Ứng dụng cần quyết định:
- Kết quả tính toán lưu trong database có giữ scale gốc không?
- Chỉ format hiển thị hay persist giá trị đã làm tròn?
- Quy tắc là HALF_UP, HALF_EVEN, DOWN hay quy tắc khác?
- Tiền tệ có số chữ số thập phân phụ thuộc currency không?
- Người dùng nhập nhiều chữ số hơn cho phép thì từ chối hay làm tròn?

Format hiển thị không nên âm thầm biến thành phép tính nghiệp vụ. Với tiền, nên dùng **BigDecimal** và áp dụng scale/rounding rõ ràng ở domain/service.

~~~java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded =
        amount.setScale(2, RoundingMode.HALF_UP);
~~~

Kết quả là 12.35. Đây là phép làm tròn trong domain code; không giống việc DecimalFormat chỉ in hai chữ số ra màn hình.

## 7. Parse nghiêm ngặt: kiểm tra toàn bộ chuỗi

Một điểm dễ bỏ qua là NumberFormat.parse(String) có thể phân tích tiền tố của chuỗi. Chẳng hạn chuỗi 123abc không nên được coi là một số hợp lệ chỉ vì parser đọc được phần 123.

Đối với dữ liệu nhập cần khớp toàn bộ, dùng **ParsePosition** và kiểm tra:
- Kết quả parse không null.
- errorIndex không báo lỗi.
- index cuối cùng bằng độ dài chuỗi.
- Có quy tắc rõ cho khoảng trắng đầu/cuối.
- Giá trị không vượt giới hạn và scale nghiệp vụ.

Không phải mọi formatter Spring mặc định đều có cùng chính sách strict. Nếu endpoint yêu cầu chuỗi khớp hoàn toàn, thêm bước kiểm tra hoặc viết Formatter/Converter riêng có hợp đồng rõ.

## 8. Ví dụ Java 17+ chạy được: custom pattern và Locale

Chương trình sau chỉ dùng JDK. Nó minh họa:
1. Cùng một BigDecimal được format bằng US và Germany symbols.
2. Parse đúng chuỗi theo Locale tương ứng.
3. Parse nghiêm ngặt để từ chối dữ liệu còn ký tự thừa.
4. Pattern custom và rounding mode được khai báo rõ.

Cấu trúc:

~~~text
number-locale-demo/
└── NumberLocaleDemo.java
~~~

**NumberLocaleDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public final class NumberLocaleDemo {

    private static DecimalFormat createFormat(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        DecimalFormat format =
                new DecimalFormat("#,##0.00;(#,##0.00)", symbols);

        format.setParseBigDecimal(true);
        format.setRoundingMode(RoundingMode.HALF_EVEN);
        return format;
    }

    private static BigDecimal parseStrict(
            DecimalFormat format, String text) {

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid number for selected locale");
        }

        if (parsed instanceof BigDecimal decimal) {
            return decimal;
        }
        return new BigDecimal(parsed.toString());
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.5");

        DecimalFormat us = createFormat(Locale.US);
        DecimalFormat germany = createFormat(Locale.GERMANY);

        String usText = us.format(value);
        String germanText = germany.format(value);

        System.out.println("US_FORMAT=" + usText);
        System.out.println("DE_FORMAT=" + germanText);

        System.out.println("US_PARSE="
                + parseStrict(us, usText).toPlainString());
        System.out.println("DE_PARSE="
                + parseStrict(germany, germanText).toPlainString());

        try {
            parseStrict(us, "1,234.50xyz");
            System.out.println("STRICT_PARSE=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("STRICT_PARSE=rejected");
        }
    }
}
~~~

Trong thư mục chứa file, chạy:

~~~bash
javac NumberLocaleDemo.java
java NumberLocaleDemo
~~~

Stdout chính xác:

~~~text
US_FORMAT=1,234.50
DE_FORMAT=1.234,50
US_PARSE=1234.50
DE_PARSE=1234.50
STRICT_PARSE=rejected
~~~

Giải thích:
- DecimalFormatSymbols.getInstance(locale) lấy bộ dấu phù hợp Locale.
- Cùng pattern không định vị nhưng symbols khác nhau nên chuỗi hiển thị khác.
- setParseBigDecimal(true) giúp parser trả BigDecimal, tránh chuyển qua Double.
- ParsePosition cho phép kiểm tra parser đã tiêu thụ toàn bộ chuỗi chưa.
- RoundingMode.HALF_EVEN được chọn tường minh để tránh phụ thuộc người đọc có nhớ mặc định hay không.

Đây là chương trình Java hoàn chỉnh, không phải formatter Spring hoặc web application. Các phần sau chỉ cách gắn quy tắc format vào Spring.

## 9. Đăng ký mẫu số trong Spring MVC

### 9.1. Dùng @NumberFormat cho DTO

~~~java
public final class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Trong controller:

~~~java
@PostMapping("/invoice")
public String submit(
        @Valid @ModelAttribute("invoice") InvoiceForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "invoice-form";
    }
    return "invoice-success";
}
~~~

Đây là đoạn tích hợp MVC, cần controller, imports, view và validation provider. Spring MVC dùng FormattingConversionService được cấu hình trong MVC để đọc annotation. Locale của request có thể được dùng khi formatter parse/print.

### 9.2. Đăng ký formatter qua WebMvcConfigurer

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new NumberStyleFormatter("#,##0.00"));
    }
}
~~~

Đây là cách đăng ký formatter chung; cần xác định kiểu mà formatter hỗ trợ và phạm vi ảnh hưởng. Nếu nhiều field có pattern khác nhau, annotation hoặc formatter chuyên biệt theo property thường rõ hơn formatter chung.

Không tạo FormattingConversionService độc lập rồi giả định Spring MVC tự sử dụng service đó. Hãy đăng ký bằng cơ chế MVC tương ứng theo đúng phiên bản ứng dụng.

### 9.3. LocaleResolver và request locale

Spring MVC có thể xác định Locale của request bằng LocaleResolver/LocaleContextResolver. Formatter nhận Locale qua locale context lúc parse/print. Vì vậy cùng DTO và pattern có thể tạo chuỗi khác theo request locale.

Cần thống nhất:
- Locale mặc định khi client không gửi preference.
- Locale được chấp nhận và thứ tự ưu tiên.
- Locale cho API đầu vào so với Locale hiển thị.
- Cách xử lý chuỗi không khớp Locale.
- Locale có ảnh hưởng dữ liệu lưu hay chỉ phần trình bày.

## 10. Tách conversion, formatting và validation

| Giai đoạn | Ví dụ | Mục đích |
| --- | --- | --- |
| Format/parse | "1.234,50" → BigDecimal 1234.50 theo de-DE | Đưa chuỗi về kiểu Java |
| Validation | @DecimalMin("0.00") | Kiểm tra ngưỡng |
| Domain logic | Tiền phải có currency code và scale đúng | Kiểm tra quy tắc nghiệp vụ |
| Persistence | Lưu DECIMAL với precision/scale đã thiết kế | Lưu số chính xác |
| Presentation | BigDecimal → "1.234,50" theo Locale | Hiển thị cho người dùng |

Người dùng nhập "0,00" theo de-DE: parse có thể thành công thành BigDecimal.ZERO; @DecimalMin("0.01") có thể từ chối vì số nhỏ hơn mức tối thiểu. Đây là validation, không phải lỗi format.

Nếu người dùng nhập "0,00 EUR" trong khi formatter chỉ chấp nhận số, parse có thể thất bại. Nếu muốn nhận currency symbol/unit, phải dùng formatter hoặc model có currency rõ ràng và hợp đồng đầu vào tương ứng.

## 11. Lỗi thường gặp

1. **Dùng pattern như thể dấu phẩy và chấm luôn là literal.** Pattern DecimalFormat có cú pháp riêng; symbols từ Locale điều khiển ký tự hiển thị.
2. **Đổi dấu chấm/phẩy bằng replace.** Có thể làm 1,234 thành số sai vì không biết dấu nào là grouping/decimal.
3. **Dùng Locale hiển thị để parse API.** API cần hợp đồng đầu vào ổn định; Locale trình duyệt có thể thay đổi.
4. **Dùng Double cho tiền cần chính xác thập phân.** Ưu tiên BigDecimal và quy tắc scale/rounding tường minh.
5. **Đưa grouping separator vào dữ liệu lưu trữ.** Database nên lưu số, không lưu chuỗi đã format.
6. **Tin pattern 0.00 xác nhận đúng hai chữ số đầu vào.** Format pattern chủ yếu kiểm soát biểu diễn; parse có thể linh hoạt hơn yêu cầu API.
7. **Không kiểm tra toàn bộ chuỗi parse.** Dùng ParsePosition hoặc parser strict nếu không được phép bỏ phần đuôi.
8. **Nhầm 12.5 với 12.5%.** Pattern phần trăm nhân giá trị; cần xác định tỷ lệ lưu là 0.125 hay 12.5.
9. **Dùng Locale để suy ra currency.** Currency code phải rõ trong model/hợp đồng.
10. **Không kiểm soát làm tròn.** Chọn RoundingMode trong domain, không để UI format quyết định kết quả kinh doanh.
11. **Đăng ký formatter toàn cục không kiểm tra tác động.** Cùng kiểu số có thể được dùng ở field có quy ước khác.
12. **Cho rằng @NumberFormat là Bean Validation.** Nó hướng dẫn format/parse; min/max, scale và quy tắc nghiệp vụ cần validator riêng.

## 12. Checklist kiểm thử

| Trường hợp | Điều phải xác minh |
| --- | --- |
| Cùng BigDecimal format bằng en-US và de-DE | Grouping/decimal separator khác nhau đúng |
| Parse en-US bằng formatter de-DE | Không âm thầm hiểu sai số |
| Số âm với pattern dương/âm | Prefix/suffix đúng |
| Pattern 0.00 và #,##0.## | Số 0 dư và fraction digits đúng |
| Pattern phần trăm | Giá trị lưu và hiển thị không nhân hai lần |
| Số có quá nhiều fraction digits | Quy tắc làm tròn hoặc từ chối rõ |
| Chuỗi có ký tự thừa cuối | Parser strict từ chối |
| Empty/null | Chính sách optional và validation đúng |
| Locale request thay đổi | Parse/print theo hợp đồng công bố |
| Currency | Amount và currency code không bị suy diễn |
| @NumberFormat trên DTO | Annotation được đọc trong MVC FormattingConversionService |
| Formatter toàn cục | Không ảnh hưởng ngoài dự kiến tới field khác |

## 13. Tài liệu chính thức

- [Spring Field Formatting Reference](https://docs.spring.io/spring-framework/reference/core/validation/format.html): NumberStyleFormatter, CurrencyStyleFormatter, PercentStyleFormatter, @NumberFormat và Locale.
- [@NumberFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html): pattern và style.
- [NumberStyleFormatter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html): formatter số dựa trên NumberFormat.
- [Java 17 DecimalFormat Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): pattern, symbols, grouping, rounding và parse.
- [Java 17 DecimalFormatSymbols Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): decimal/grouping separator và ký hiệu khác.
- [Spring MVC Formatting Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): đăng ký Formatter và Converter trong MVC.

**Nguyên tắc cần nhớ:** pattern quy định cấu trúc số; Locale cung cấp ký hiệu và quy ước vùng miền; BigDecimal giữ giá trị số; validation và domain logic kiểm tra tính hợp lệ nghiệp vụ. Xác định Locale cho cả chiều parse và print, kiểm tra toàn bộ chuỗi khi cần strict, và giữ rounding/scale ở đúng tầng nghiệp vụ.