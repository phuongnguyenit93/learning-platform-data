# Phân biệt giá trị tỷ lệ với cách hiển thị phần trăm

Khi lưu tỷ lệ hoàn thành, thuế, chiết khấu hoặc tỷ lệ chuyển đổi, cần phân biệt **giá trị số dùng trong tính toán** với **cách biểu diễn phần trăm trên giao diện**. Ví dụ, tỷ lệ 12,5% thường được lưu dưới dạng ratio `0.125`. Khi hiển thị, percent formatter nhân ratio với 100 và thêm ký hiệu `%` để người đọc thấy `12.50%`.

`0.125` và `12.5` không thể thay thế nhau nếu chưa xác định quy ước. Nhầm lẫn thường gây nhân 100 hai lần, tính sai chiết khấu, lưu sai dữ liệu hoặc hiển thị kết quả lớn hơn thực tế 100 lần.

## 1. Ratio và percent

**Ratio** là tỷ lệ trên một đơn vị; **percent** là ratio được biểu diễn theo thang 100.

\[percent = ratio \times 100\]
\[ratio = percent \div 100\]

| Ý nghĩa | Ratio | Percent |
| --- | ---: | ---: |
| Không có | 0 | 0% |
| Một phần tư | 0.25 | 25% |
| Một nửa | 0.5 | 50% |
| Hoàn tất | 1 | 100% |
| Một phần tám | 0.125 | 12.5% |
| Một phần nghìn | 0.001 | 0.1% |
| Vượt gấp rưỡi | 1.5 | 150% |

`0.125` không có nghĩa `0.125%`; nó tương ứng 12,5%. Đặt tên biến thể hiện quy ước như `completionRatio` hoặc `taxRateRatio` tốt hơn tên mơ hồ `rate`.

Nếu domain chọn ratio từ 0 đến 1, kiểm tra hoàn tất có thể là:

```java
BigDecimal completionRatio = new BigDecimal("0.85");
boolean complete = completionRatio.compareTo(BigDecimal.ONE) >= 0;
```

Đây là đoạn minh họa. Không phải mọi tỷ lệ đều bắt buộc thuộc [0,1]. Tiến độ vượt kế hoạch, utilization hoặc tăng trưởng có thể lớn hơn 1; miền hợp lệ phải xuất phát từ nghiệp vụ.

## 2. Tránh nhân 100 hai lần

Giả sử model lưu `0.125` và cần hiển thị `12.50%`. Percent formatter đã tự nhân 100. Nếu code nhân model lên `12.5` trước khi format, formatter lại nhân 100 và cho `1250.00%`.

```text
Ratio trong domain: 0.125
Percent formatter: x 100 và thêm % -> 12.50%

Sai: code tự nhân trước formatter
0.125 -> 12.5 -> formatter -> 1250.00%
```

**Chỉ một nơi chịu trách nhiệm đổi thang biểu diễn.** Nếu model lưu ratio, truyền ratio trực tiếp cho percent formatter. Nếu model lưu percent points như `12.5`, không dùng formatter như thể giá trị ấy là ratio; chuyển đổi theo contract trước.

Kiểm tra nhanh: ratio `0.5` phải hiển thị 50%, không phải 0.5% hay 5000%.

## 3. Phần trăm và điểm phần trăm

**Điểm phần trăm (percentage point, pp)** là hiệu giữa hai mức tỷ lệ được biểu diễn theo phần trăm. **Thay đổi tương đối** là hiệu chia cho mức ban đầu.

Ví dụ tỷ lệ chuyển đổi tăng từ 4% lên 5%: ratio cũ `0.04`, ratio mới `0.05`, chênh lệch là `0.01`, tương ứng 1 pp. Mức tăng tương đối là `(5 - 4) / 4 = 25%`.

| Chỉ số | Kết quả |
| --- | ---: |
| Tỷ lệ cũ | 4% |
| Tỷ lệ mới | 5% |
| Chênh lệch tuyệt đối | 1 pp |
| Tăng tương đối | 25% |

\[ppDifference=(newRatio-oldRatio)\times100\]
\[relativeChange=\frac{newRatio-oldRatio}{oldRatio}\]

Kết quả `relativeChange` vẫn là ratio; `0.25` được percent formatter hiển thị thành 25%. Không viết “tăng 25 điểm phần trăm”: ví dụ này tăng 1 pp và tăng tương đối 25%. Nếu tỷ lệ ban đầu bằng 0, công thức relative change không thể chia cho 0; cần quy ước báo cáo riêng.

## 4. Kiểu số, precision và rounding

Java `double` dùng floating-point nhị phân. Nhiều phân số thập phân không biểu diễn chính xác:

```java
double ratio = 0.1 + 0.2;
System.out.println(ratio);
```

Kết quả thường thấy là `0.30000000000000004`. Với tiền, thuế, chiết khấu hoặc phân bổ cần rounding rõ, `BigDecimal` thường phù hợp hơn.

```java
BigDecimal ratio = new BigDecimal("0.125");
BigDecimal percent = ratio.multiply(BigDecimal.valueOf(100));
System.out.println(ratio.toPlainString());
System.out.println(percent.toPlainString());
```

Đầu ra:

```text
0.125
12.500
```

Tạo `BigDecimal` từ chuỗi thập phân hoặc số nguyên có scale rõ; tránh `new BigDecimal(0.1)` vì constructor nhận double đã có sai số nhị phân.

**Precision** là tổng chữ số có nghĩa; **scale** là số chữ số bên phải dấu thập phân. `0.1250` và `0.125` bằng nhau về số học theo `compareTo`, nhưng `equals` còn xét scale. Quy định precision/scale lưu trữ tách khỏi số chữ số hiển thị.

Không làm tròn sớm. Ratio `0.12496` có thể hiển thị thành `12.50%` theo HALF_UP khi giới hạn hai chữ số, nhưng phép tính sau đó vẫn nên dùng giá trị gốc nếu nghiệp vụ yêu cầu giữ precision. Format UI không phải chuẩn hóa domain data.

## 5. Percent formatter và locale

`NumberFormat.getPercentInstance(locale)` tạo formatter kiểu phần trăm. Nó tự nhân ratio với 100 khi in và parse theo quy ước phần trăm.

```java
NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
String text = percent.format(new BigDecimal("0.125"));
```

Đây là đoạn minh họa. Số chữ số mặc định phụ thuộc formatter/locale. Nếu cần hai chữ số, cấu hình fraction digits hoặc dùng `DecimalFormat` pattern `#,##0.00%`.

Pattern có `%` biểu thị grouping, hai chữ số thập phân và percent scaling. Ratio `0.125` thành `12.50%` với locale dùng dấu chấm. Locale Germany có thể hiển thị `12,50%`.

Parse `12.50%` bằng percent formatter phải cho ratio `0.125`, không phải percent points `12.50`. Decimal formatter thường không có cùng semantics; không parse chuỗi có `%` bằng formatter số thập phân rồi giả định đã chia 100.

Locale còn ảnh hưởng dấu phân nhóm và khoảng trắng. Đừng dùng `replace(",", ".")` cho mọi input: `1.234,50%` có thể dùng dấu chấm phân nhóm và dấu phẩy thập phân. Với Spring MVC form, locale request và formatter cần nhất quán; API máy-máy nên có schema số ổn định.

## 6. Spring @NumberFormat

Spring hỗ trợ `org.springframework.format.annotation.NumberFormat` để khai báo quy tắc formatting trên field/property:

```java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class CampaignForm {
    // Ratio 0.125 nghĩa là 12.5%.
    @NumberFormat(pattern = "#,##0.00%")
    private BigDecimal discountRatio;

    public BigDecimal getDiscountRatio() {
        return discountRatio;
    }

    public void setDiscountRatio(BigDecimal discountRatio) {
        this.discountRatio = discountRatio;
    }
}
```

Đây là JavaBean dùng trong Spring binding. Khi formatting infrastructure xử lý property có metadata annotation, pattern phần trăm có thể in `0.125` thành `12.50%` theo locale thích hợp. Giá trị model vẫn là `BigDecimal 0.125`; annotation không ghi model thành 12.5.

Cũng có thể dùng `@NumberFormat(style = NumberFormat.Style.PERCENT)`. Style `PERCENT` nêu intent; nếu cần số chữ số cụ thể, dùng `pattern`. Không giả định mọi locale/JDK có mặc định giống nhau.

Spring MVC dùng `FormattingConversionService` để đăng ký converter/formatter. Điểm mở rộng là `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

```java
@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Đăng ký formatter/converter riêng nếu module cần.
        // @NumberFormat được hỗ trợ bởi formatting infrastructure.
    }
}
```

Đây là method trong cấu hình MVC, cần imports và component scan. Nếu formatter mặc định của `@NumberFormat` đáp ứng nhu cầu thì không cần tự viết percent formatter. `@RequestBody` JSON thường đi qua message converter (ví dụ Jackson); `@NumberFormat` không tự thay đổi JSON serialization/deserialization.

## 7. Ví dụ Java 17+ chạy được: ratio, percent và locale

Ví dụ dùng JDK thuần để cô lập semantics của `DecimalFormat`. Tệp `src/PercentageFormattingDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class PercentageFormattingDemo {
    private static DecimalFormat percentFormat(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00%", DecimalFormatSymbols.getInstance(locale));
        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);
        return format;
    }

    private static BigDecimal parsePercent(String text, Locale locale)
            throws ParseException {
        DecimalFormat format = percentFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);
        if (!(parsed instanceof BigDecimal value)
                || position.getIndex() != text.length()) {
            int index = position.getErrorIndex() >= 0
                    ? position.getErrorIndex() : position.getIndex();
            throw new ParseException("Invalid percentage", index);
        }
        return value;
    }

    public static void main(String[] args) throws ParseException {
        BigDecimal ratio = new BigDecimal("0.125");
        System.out.println("stored.ratio=" + ratio.toPlainString());
        System.out.println("display.us=" +
                percentFormat(Locale.US).format(ratio));
        System.out.println("display.de=" +
                percentFormat(Locale.GERMANY).format(ratio));

        BigDecimal parsed = parsePercent("12.50%", Locale.US);
        System.out.println("parsed.matches=" +
                (parsed.compareTo(ratio) == 0));

        BigDecimal oldRatio = new BigDecimal("0.04");
        BigDecimal newRatio = new BigDecimal("0.05");
        BigDecimal difference = newRatio.subtract(oldRatio);
        BigDecimal pp = difference.multiply(BigDecimal.valueOf(100));
        BigDecimal relative = difference.divide(
                oldRatio, 6, RoundingMode.HALF_UP);
        System.out.println("difference.pp=" +
                pp.setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("relative.change=" +
                percentFormat(Locale.US).format(relative));
    }
}
```

Biên dịch/chạy với JDK 17+ từ project root:

```bash
javac -d out src/PercentageFormattingDemo.java
java -cp out PercentageFormattingDemo
```

Stdout:

```text
stored.ratio=0.125
display.us=12.50%
display.de=12,50%
parsed.matches=true
difference.pp=1.00
relative.change=25.00%
```

Giải thích: ratio vẫn là 0.125; formatter chỉ tạo chuỗi. Pattern `%` nhân 100 khi format và chia lại khi parse. US dùng dấu chấm, Germany dùng dấu phẩy. `setParseBigDecimal(true)` trả BigDecimal. `ParsePosition` xác nhận đã parse hết input. `DecimalFormat` mutable, không thread-safe; ví dụ tạo instance theo từng lời gọi. Chênh lệch từ 4% lên 5% là 1 pp; relative change 0.25 được hiển thị 25%.

## 8. Miền tỷ lệ phụ thuộc domain

Không mặc định ratio luôn ở [0,1]. Tỷ lệ hoàn thành thường ở [0,1] nhưng có thể vượt mục tiêu; chiết khấu thường bị giới hạn; tăng trưởng có thể âm hoặc lớn hơn 1; tỷ trọng phân bổ thường yêu cầu tổng bằng 1.

Formatter có thể in `1.25` thành 125% hoặc `-0.1` thành -10%. Nó không kiểm tra miền nghiệp vụ. Dùng validator/domain rule như `@DecimalMin("0")`, `@DecimalMax("1")` hoặc kiểm tra tổng tỷ trọng. `@DecimalMax("1")` trên ratio nghĩa tối đa 1 (100%), không phải tối đa 1%. Nếu model lưu percent points, constraint phải theo unit đó.

## 9. Database, JSON và tính tiền

Ví dụ database lưu ratio:

```sql
CREATE TABLE campaign (
    id BIGINT PRIMARY KEY,
    discount_ratio DECIMAL(9, 6) NOT NULL
);
```

`0.125000` đại diện chiết khấu 12,5%. Không lưu `12.500000` trừ khi schema nói rõ đang lưu percent points.

JSON API có thể chọn `discountRatio: 0.125` hoặc `discountPercent: 12.5`; cả hai dùng được nếu naming và tài liệu nhất quán. JSON number không chứa ký hiệu `%`. `@NumberFormat` không tự định nghĩa Jackson serialize BigDecimal thành chuỗi phần trăm.

Tính tiền từ amount 200.00 và ratio 0.125:

```java
BigDecimal amount = new BigDecimal("200.00");
BigDecimal discountRatio = new BigDecimal("0.125");
BigDecimal discount = amount.multiply(discountRatio)
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal net = amount.subtract(discount);
System.out.println(discount);
System.out.println(net);
```

Đầu ra `25.00` và `175.00`. Quy tắc làm tròn tiền là policy nghiệp vụ riêng với số chữ số percent display.

## 10. Nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lưu 12.5 nhưng tưởng là ratio | Hiển thị 1250% | Chọn ratio hay percent points |
| Nhân ratio trước percent formatter | Scale hai lần | Truyền ratio trực tiếp |
| Decimal formatter parse input có % | Sai scale/lỗi | Dùng percent formatter |
| Coi 1 pp là tăng 1% tương đối | Báo cáo sai | Phân biệt pp và relative percent |
| Dùng double cho thập phân exact | Sai số nhị phân | BigDecimal và rounding policy |
| Làm tròn model theo UI | Mất precision | Round tại boundary đã định |
| Coi mọi ratio thuộc 0–1 | Chặn giá trị >100% hợp lệ | Quy định miền domain |
| Dùng locale server ngầm | Khác môi trường | Cố định locale request/test |
| Chia sẻ DecimalFormat singleton | Race condition | Tạo instance theo thao tác |
| Tự nối ký hiệu % | Sai scale/spacing | Dùng percent formatter |
| Áp @NumberFormat cho JSON | Jackson không theo UI format | Cấu hình JSON riêng |

## 11. Checklist thiết kế field tỷ lệ

1. Giá trị lưu là ratio (`0.125`) hay percent points (`12.5`)?
2. 100% tương ứng 1 hay 100 trong domain?
3. Tên property có nêu convention như `taxRateRatio`?
4. Miền hợp lệ là [0,1], âm/dương hay có thể vượt 1?
5. Precision lưu và số chữ số hiển thị là bao nhiêu?
6. Rounding mode nào được dùng?
7. Input phụ thuộc locale không? API máy-máy có convention ổn định không?
8. Formatter scale ×100 đúng một lần không?
9. Validation có kiểm tra đúng unit không?
10. JSON serializer/deserializer có contract riêng không?
11. Báo cáo có phân biệt pp với relative change không?
12. Test có gồm 0%, 1%, 12.5%, 100%, >100%, âm và rounding boundary không?

## 12. Câu hỏi tự kiểm tra

**1. Tỷ lệ 12,5% lưu dạng ratio là bao nhiêu?** `0.125`; chia 12.5 cho 100.

**2. Model chứa `0.125` và percent formatter hiển thị bao nhiêu?** 12.5% (pattern hai chữ số là `12.50%`).

**3. Vì sao không nhân model với 100 trước percent formatter?** Formatter nhân tiếp: 0.125 -> 12.5 -> 1250%.

**4. Từ 4% lên 5% tăng bao nhiêu pp và bao nhiêu phần trăm tương đối?** Tăng 1 pp; tăng tương đối 25%.

**5. `@DecimalMax("1")` trên ratio nghĩa gì?** Tối đa 1, tương ứng 100%, không phải tối đa 1%.

**6. Khi nào dùng BigDecimal thay double?** Khi cần phép tính thập phân có precision/rounding kiểm soát.

**7. `@NumberFormat(pattern="#,##0.00%")` có đổi model 0.125 thành 12.5 không?** Không; model vẫn là ratio 0.125.

**8. Điểm phần trăm và relative change khác gì?** Điểm phần trăm là hiệu hai mức percent; relative change là hiệu chia cho mức ban đầu.

**9. JSON number 0.125 có ký hiệu % không?** Không; muốn trả chuỗi phần trăm cần DTO/serializer contract riêng.

**10. Có nên chia sẻ DecimalFormat giữa nhiều request không?** Không; nó mutable và không thread-safe.

**Ghi nhớ:** lưu và tính toán theo convention có tên rõ (thường ratio với 100% = 1), còn phần trăm là cách hiển thị do formatter đảm nhiệm. Tách ratio, percentage points, rounding và locale giúp tránh lỗi scale 100 lần và sai lệch báo cáo.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — NumberFormat annotation](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [Spring Framework 6.2 — NumberStyleFormatter](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html)
- [Java 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [Java 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [Java 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)