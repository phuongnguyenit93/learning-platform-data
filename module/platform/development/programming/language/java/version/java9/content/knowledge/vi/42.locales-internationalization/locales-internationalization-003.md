# Kiểm thử định dạng ngày, số và tiền tệ theo locale trong Java

## 1. Mục tiêu

Một giá trị dữ liệu có thể được hiển thị khác nhau tùy ngôn ngữ và vùng của người dùng. Ví dụ, cùng số `1234567.89` có thể hiện là `1,234,567.89` tại `en-US` nhưng là `1.234.567,89` tại `de-DE`. Ngày có thể đổi thứ tự ngày–tháng–năm và tên tháng; tiền tệ còn có ký hiệu, vị trí ký hiệu, khoảng trắng và số chữ số thập phân.

Sau bài này, bạn có thể:

- Chọn `Locale` tường minh và lập ma trận kiểm thử cho nhiều vùng.
- Kiểm thử định dạng ngày bằng `java.time`; số và tiền tệ bằng `NumberFormat`, `Currency` và `BigDecimal`.
- Kiểm tra cả chuỗi hiển thị lẫn việc phân tích chuỗi về giá trị gốc (`round-trip`), với điều kiện áp dụng đúng.
- Phân biệt lỗi ứng dụng với khác biệt dữ liệu locale/CLDR giữa các bản JDK.
- Viết bài kiểm thử tự động dễ bảo trì mà không giả định mọi locale dùng dấu chấm, dấu phẩy, ký hiệu `$` hay khoảng trắng giống nhau.

**Phạm vi công nghệ:** `Locale`, `java.time.format.DateTimeFormatter`, `java.text.NumberFormat`, `java.util.Currency` và `BigDecimal` vẫn được dùng trong Java hiện đại. Chương trình độc lập bên dưới tương thích cú pháp Java 9 trở lên (`List.of` có từ Java 9), nên có thể biên dịch bằng JDK 17/21 hoặc mới hơn. Với mã mới, ưu tiên `java.time` cho ngày/giờ.

## 2. Phân biệt dữ liệu với cách hiển thị

| Thành phần | Đại diện cho điều gì? | Quy tắc khi kiểm thử |
| --- | --- | --- |
| `LocalDate` | Một ngày theo lịch ISO, không chứa múi giờ | Cố định một ngày cụ thể; dùng `DateTimeFormatter` với `Locale` đã chọn |
| `Instant` và `ZoneId` | Một thời điểm toàn cầu và vùng giờ dùng để hiển thị | Khi kiểm thử *ngày-giờ*, cố định cả thời điểm lẫn `ZoneId`; `Locale` không thay cho múi giờ |
| `BigDecimal` | Giá trị thập phân, phù hợp để biểu diễn số tiền | Tạo từ chuỗi như `new BigDecimal("1234.50")`; không khởi tạo số tiền từ `double` |
| `Locale` | Quy tắc trình bày theo ngôn ngữ/vùng, ví dụ `vi-VN`, `en-US` | Truyền tường minh vào formatter, không phụ thuộc `Locale.getDefault()` |
| `Currency` | Đơn vị tiền theo mã ISO 4217, ví dụ `USD`, `EUR`, `JPY`, `VND` | Cố định đơn vị tiền độc lập với locale; đừng suy ra mã tiền từ ký hiệu hiển thị |

Một locale có thể mặc định gắn với đơn vị tiền trong một vùng, nhưng đó không nhất thiết là đồng tiền của giao dịch. Chẳng hạn giao diện Việt Nam vẫn có thể hiển thị số tiền **USD**. Hãy giữ riêng `BigDecimal amount` và `String currencyCode` trong dữ liệu nghiệp vụ; chỉ định dạng tại ranh giới giao diện.

API phù hợp:

- Ngày: `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(locale)`, sau đó `format` hoặc `LocalDate.parse`.
- Số: `NumberFormat.getNumberInstance(locale)`, đặt grouping và số chữ số thập phân tùy yêu cầu.
- Tiền tệ: `NumberFormat.getCurrencyInstance(locale)`, `setCurrency(Currency.getInstance("USD"))`, rồi điều chỉnh số chữ số thập phân.
- `Currency.getDefaultFractionDigits()` thường trả `2` cho USD/EUR, `0` cho JPY/VND; có thể trả `-1` cho loại tiền đặc biệt không có đơn vị nhỏ xác định. Quy tắc làm tròn nghiệp vụ vẫn phải được quyết định riêng.

**Chi tiết dễ sai:** `NumberFormat.setCurrency(...)` **không tự cập nhật** `minimumFractionDigits` và `maximumFractionDigits`. Nếu đổi từ một formatter mặc định VND sang USD mà không đặt lại hai giá trị này, kết quả có thể mất hai chữ số lẻ của USD.

## 3. Thiết kế ma trận locale và dữ liệu thử

Không chỉ kiểm thử một máy với locale mặc định. Chọn các trường hợp đại diện cho quy ước khác nhau:

| Locale | Trọng tâm kiểm thử |
| --- | --- |
| `vi-VN` | Dấu ngăn cách nhóm/chữ số thập phân, cách viết ngày tiếng Việt, VND thường không có phần lẻ |
| `en-US` | Số thường dùng dấu phẩy nhóm và dấu chấm thập phân; tháng dạng chữ trong ngày dài |
| `de-DE` | Quy ước dấu phân cách số khác `en-US`, thứ tự ngày và tên tháng tiếng Đức |
| `fr-FR` | Dấu phẩy thập phân; dấu nhóm có thể là khoảng trắng Unicode hẹp không ngắt dòng (`U+202F`) |
| `ja-JP` | Ngày và nhãn tháng/ngày kiểu Nhật, JPY thường có 0 chữ số lẻ |

Bộ dữ liệu gợi ý:

- **Ngày:** `2026-11-07`, thêm `2028-02-29` (ngày nhuận), `2026-12-31` (ranh giới năm).
- **Số:** `1234567.89` để thấy grouping và dấu thập phân; `0`, `-1234.50` và `0.005` để bắt lỗi dấu âm, số 0, độ chính xác/làm tròn.
- **Tiền:** `1234.50 USD`, `1234.50 EUR`, `1234 JPY` và `1234 VND`; kiểm tra mã tiền và số chữ số hiển thị theo quy tắc đã chốt.
- **Đầu vào bất thường:** chuỗi rỗng, chuỗi có ký tự thừa, ký tự phân cách sai locale, số âm, ký tự khoảng trắng Unicode.

Mỗi ca kiểm thử cần xác định **đầu vào cố định**, **locale**, **currency (nếu có)**, **quy tắc format**, **kỳ vọng**, và **điều kiện môi trường**. Nếu sản phẩm đòi hỏi chuỗi chính xác từng ký tự, còn phải kiểm soát JDK và nguồn dữ liệu locale.

## 4. Ba cấp độ khẳng định nên sử dụng

1. **Bất biến dữ liệu:** Định dạng một ngày rồi parse bằng cùng formatter phải trả về ngày ban đầu. Với số không bị làm tròn, giá trị parse phải tương đương giá trị đầu vào. Đây là phép kiểm thử `round-trip`.
2. **Quy tắc trình bày mà sản phẩm cam kết:** Ví dụ riêng `en-US` phải hiện `1,234.50`, `de-DE` phải hiện `1.234,50` cho cùng số với đúng hai chữ số lẻ. Chỉ đặt kỳ vọng chuỗi cứng cho những trường hợp đã được xác nhận và có môi trường chạy kiểm soát.
3. **Tính an toàn của xử lý đầu vào:** Khi parse số, kiểm tra chuỗi đã được tiêu thụ hết bằng `ParsePosition`. Parse thành công một phần không có nghĩa toàn bộ đầu vào hợp lệ. Với form tài chính, cần thêm validation theo nghiệp vụ vì `NumberFormat` có thể parse khá linh hoạt.

Không so sánh chuỗi đã `replace(",", ".")` hoặc xóa mọi dấu cách: cách đó phá hủy ý nghĩa của grouping, dấu thập phân và khoảng trắng Unicode. Không bắt buộc các locale khác nhau luôn cho chuỗi khác nhau: một số cặp locale có thể chia sẻ quy ước hiển thị.

## 5. Chương trình kiểm thử chạy độc lập

Lưu **toàn bộ** mã sau vào tệp `LocaleFormattingChecks.java`. Mã dùng một giá trị ngày, một số thập phân và ba loại tiền; kiểm tra năm locale. Mỗi lần gọi đều tạo formatter mới để không bị trạng thái cấu hình của lần chạy khác ảnh hưởng.

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class LocaleFormattingChecks {
    private static final LocalDate DATE = LocalDate.of(2026, 11, 7);
    private static final BigDecimal NUMBER = new BigDecimal("1234567.89");

    public static void main(String[] args) {
        List<Locale> locales = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.JAPAN
        );

        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");
        Currency vnd = Currency.getInstance("VND");

        for (Locale locale : locales) {
            String dateText = checkDate(locale);
            String numberText = checkNumber(locale);
            String usdText =
                    checkCurrency(locale, usd, new BigDecimal("1234.50"));

            checkCurrency(locale, jpy, new BigDecimal("1234"));
            checkCurrency(locale, vnd, new BigDecimal("1234"));

            System.out.printf(
                    "%s | date=%s | number=%s | USD=%s%n",
                    locale.toLanguageTag(), dateText, numberText, usdText
            );
        }

        System.out.println("PASS: 5 locales, 5 checks per locale");
    }

    private static String checkDate(Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

        String text = DATE.format(formatter);
        LocalDate parsed = LocalDate.parse(text, formatter);

        if (!DATE.equals(parsed)) {
            throw new AssertionError(
                    "Date failed for " + locale + ": " + text
            );
        }
        return text;
    }

    private static String checkNumber(Locale locale) {
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setGroupingUsed(true);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        String text = formatter.format(NUMBER);
        checkNumberRoundTrip(formatter, text, NUMBER, locale);
        return text;
    }

    private static String checkCurrency(
            Locale locale, Currency currency, BigDecimal amount) {
        NumberFormat formatter = NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            formatter.setMinimumFractionDigits(digits);
            formatter.setMaximumFractionDigits(digits);
        }

        if (!currency.equals(formatter.getCurrency())) {
            throw new AssertionError("Wrong currency for " + locale);
        }

        String text = formatter.format(amount);
        checkNumberRoundTrip(formatter, text, amount, locale);
        return text;
    }

    private static void checkNumberRoundTrip(
            NumberFormat formatter, String text,
            BigDecimal expected, Locale locale) {
        ParsePosition position = new ParsePosition(0);
        Number parsed = formatter.parse(text, position);

        boolean valid = parsed != null
                && position.getErrorIndex() < 0
                && position.getIndex() == text.length()
                && Math.abs(parsed.doubleValue()
                            - expected.doubleValue()) < 0.000001d;

        if (!valid) {
            throw new AssertionError(
                    "Number failed for " + locale + ": " + text
            );
        }
    }
}
```

Biên dịch và chạy trong thư mục có tệp nguồn:

```bash
javac -encoding UTF-8 LocaleFormattingChecks.java
java LocaleFormattingChecks
```

Chương trình in năm dòng quan sát, mỗi dòng gồm locale, ngày, số và số tiền USD đã format. Chuỗi cụ thể (nhất là khoảng trắng, ký hiệu USD và tên tháng) có thể thay đổi theo dữ liệu locale của JDK. **Nếu các kiểm tra đều qua, dòng cuối luôn là:**

```text
PASS: 5 locales, 5 checks per locale
```

**Giải thích các phép kiểm tra:**

- `checkDate` kiểm tra `LocalDate` thu được sau `format → parse` đúng bằng ngày ISO ban đầu.
- `checkNumber` đặt hai chữ số thập phân rồi parse lại số. Vì `NumberFormat.parse` thông thường có thể trả `Double`/`Long`, phép kiểm tra minh họa dùng sai số nhỏ; **không dùng so sánh số thực dạng này để quyết định tiền thanh toán**.
- `checkCurrency` ép mã tiền giao dịch rồi cấu hình số chữ số phần lẻ tương ứng. Trường hợp JPY/VND dùng số nguyên để không tạo ra sai khác do làm tròn hiển thị.
- `ParsePosition.getIndex() == text.length()` kiểm tra parser đã đọc hết chuỗi. Đây là kiểm tra *tiêu thụ đầy đủ*, chưa thay thế một bộ validator nghiêm ngặt theo yêu cầu nhập liệu.
- Nếu một assert sai, chương trình ném `AssertionError` và không in dòng `PASS`.

## 6. Đưa kỳ vọng cụ thể vào JUnit 5

Phép kiểm tra round-trip thường bền hơn qua các lần nâng cấp JDK. Tuy nhiên nếu thiết kế sản phẩm **bắt buộc** cách hiển thị chính xác cho một locale, hãy kiểm tra chuỗi tương ứng. Ví dụ lớp test sau dùng JUnit Jupiter với `junit-jupiter-params` đã có trong cấu hình test của dự án. Đây là **lớp test JUnit**, chạy bằng test runner của dự án, không phải chương trình `main` độc lập.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class LocaleFormattingContractTest {
    @ParameterizedTest
    @ValueSource(strings = {
            "vi-VN", "en-US", "de-DE", "fr-FR", "ja-JP"
    })
    void dateRoundTrips(String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);
        DateTimeFormatter formatter = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
        LocalDate date = LocalDate.of(2028, 2, 29);

        String formatted = formatter.format(date);

        assertEquals(date, LocalDate.parse(formatted, formatter));
    }

    @ParameterizedTest
    @CsvSource({
            "en-US, '1,234.50'",
            "de-DE, '1.234,50'"
    })
    void numberUsesApprovedDisplay(
            String languageTag, String expected) {
        Locale locale = Locale.forLanguageTag(languageTag);
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setGroupingUsed(true);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        assertEquals(
                expected,
                formatter.format(new BigDecimal("1234.50"))
        );
    }
}
```

Test đầu bảo vệ giá trị ngày trên nhiều locale. Test sau bảo vệ một **hợp đồng hiển thị đã chốt** cho `en-US` và `de-DE`. Nếu đổi phiên bản JDK/CLDR và snapshot bắt đầu lệch, hãy kiểm tra thay đổi có hợp lệ về mặt ngôn ngữ hay không trước khi cập nhật expected. Đừng sao chép kỳ vọng từ ảnh chụp ở một máy khác mà không biết môi trường.

Đối với pipeline CI, cố định phiên bản JDK dùng để duyệt hợp đồng hiển thị; sau khi nâng JDK, chạy lại ma trận locale. Sử dụng ngày và số cố định để kết quả không phụ thuộc thời điểm test chạy.

## 7. Kiểm thử ngày và ngày-giờ: các điểm cần phân biệt

**Chỉ có ngày:** `LocalDate` không chứa offset hay time zone. `Locale` ảnh hưởng mẫu định dạng, tên tháng và cách trình bày, không biến đổi ngày gốc sang múi giờ khác. `FormatStyle.SHORT` có thể sử dụng năm hai chữ số ở một số locale; khi cần round-trip ít mơ hồ hơn, ưu tiên kiểm thử `LONG`/`MEDIUM` và cấu hình parser phù hợp với đầu vào.

**Có thời điểm và giờ:** nếu đầu vào là `Instant`, trước khi format theo locale cần chuyển sang `ZonedDateTime` bằng `ZoneId` cụ thể, ví dụ `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`. Cùng `Instant` có thể nằm ở ngày địa phương khác nhau khi đổi vùng giờ. Test ngày-giờ nên bao gồm ranh giới ngày, offset/DST tại vùng có thay đổi giờ và thời điểm gần chuyển năm. Đừng phụ thuộc `ZoneId.systemDefault()` nếu mong CI tái lập kết quả.

**Giá trị trao đổi giữa hệ thống:** dùng biểu diễn có cấu trúc hay ISO 8601 cho dữ liệu máy đọc, ví dụ `DateTimeFormatter.ISO_LOCAL_DATE`; định dạng địa phương dành cho màn hình và tài liệu người dùng. Không parse một chuỗi ngày tùy tiện theo locale khác với locale đã dùng để tạo ra nó.

## 8. Kiểm thử số và tiền: độ chính xác và làm tròn

**Grouping và dấu thập phân:** mặc dù `en-US` và `de-DE` là cặp mẫu tốt để minh họa dấu phân cách, không được tự suy ra ký tự phân cách từ một dấu cố định. Đặc biệt, nhiều locale dùng `U+00A0` (NBSP) hoặc `U+202F` (NNBSP) làm khoảng trắng nhóm số/tiền. Một lỗi thường gặp là test nhìn thấy hai chuỗi giống nhau trên màn hình nhưng thực chất khác code point.

**Số âm, 0 và số rất lớn:** thêm test `-1234.50`, `0` và giá trị lớn để phát hiện mất dấu, grouping sai hoặc suy giảm độ chính xác. Khi việc phân tích số nhập cần **giữ chính xác BigDecimal**, có thể kiểm tra implementation `instanceof DecimalFormat` rồi bật `DecimalFormat.setParseBigDecimal(true)` và parse với `ParsePosition`. Không ép kiểu `DecimalFormat` vô điều kiện: provider của `NumberFormat` có thể trả một lớp triển khai khác.

**Làm tròn:** định dạng có thể làm tròn số hiển thị. Nếu muốn hiển thị hai chữ số cho `1234.567`, cần xác định trước quy tắc nghiệp vụ (ví dụ `RoundingMode.HALF_EVEN` hoặc quy tắc kế toán cụ thể) và giá trị dự kiến sau làm tròn. Không yêu cầu parse của một chuỗi đã làm tròn trả lại giá trị chưa làm tròn. Không trộn phép tính tiền với `double`, kể cả khi formatter in đúng hai chữ số.

**Mã và ký hiệu tiền:** ký hiệu USD có thể là `$`, `US$` hoặc dạng khác tùy locale và dữ liệu JDK. Không dùng ký hiệu hiển thị để xác định đồng tiền của giao dịch; kiểm tra `Currency.getCurrencyCode()` hoặc mã tiền lưu trong dữ liệu. Kiểm thử riêng những tiền có `0` chữ số lẻ như JPY/VND, tiền có `2` chữ số như USD/EUR, và chính sách làm tròn thực tế của hệ thống.

## 9. Các lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa/test |
| --- | --- | --- |
| Test chỉ pass trên máy lập trình viên | Sử dụng locale hoặc timezone mặc định | Cố định `Locale`; với thời điểm, cố định cả `Instant` và `ZoneId` |
| USD bị mất `.50` khi hiển thị ở một số vùng | Chỉ gọi `setCurrency("USD")` mà không đặt fraction digits | Đặt `minimumFractionDigits` và `maximumFractionDigits` theo hợp đồng/currency |
| Test `fr-FR` thất bại dù nhìn giống expected | Khác dấu cách ASCII với NBSP/NNBSP | Kiểm tra Unicode code point; không tùy tiện trim/replace |
| Parser chấp nhận `"1,234xyz"` | Parse tiêu thụ một phần chuỗi | Dùng `ParsePosition` kiểm tra toàn bộ chuỗi, kết hợp validation chặt hơn |
| Mất vài cent hoặc sai phép so sánh tiền | Tạo `BigDecimal` từ `double`, hoặc so sánh giá trị đã bị làm tròn | Dùng `BigDecimal(String)`; so sánh theo scale và quy tắc làm tròn nghiệp vụ |
| Test snapshot ngày/tiền đổi sau nâng JDK | Nguồn dữ liệu locale/CLDR hoặc quy ước địa phương thay đổi | Giữ test bất biến giá trị; review lại các snapshot chính xác theo bản JDK triển khai |
| Cùng một formatter gây sai dữ liệu khi chạy song song | Chia sẻ `NumberFormat` mutable giữa các thread | Tạo formatter riêng cho mỗi luồng/lần thao tác hoặc bảo vệ đồng bộ |
| Một chuỗi tiền tệ bị hiểu nhầm là currency khác | Chỉ dựa vào ký hiệu thay vì ISO code | Lưu/truyền `Currency` hoặc mã ISO riêng với text trình bày |

Khi điều tra lỗi Unicode, có thể dùng `formatted.codePoints()` để xem từng code point theo hệ 16; điều này giúp nhận ra khoảng trắng không ngắt dòng, dấu âm Unicode hay chữ số thuộc hệ đếm khác. Đối với giao diện thực, kiểm tra thêm font và khả năng sao chép/dán, vì test Java đơn thuần không phát hiện mọi lỗi trình bày.

## 10. Checklist nghiệm thu

- [ ] Nguồn ngày, số, số tiền và currency code cố định, có testcase biên.
- [ ] Locale được truyền trực tiếp; trường hợp datetime có `ZoneId` rõ ràng.
- [ ] Có ít nhất một locale dùng dấu phân cách khác `en-US` và một locale dùng chữ/Unicode khác.
- [ ] Ngày round-trip về đúng `LocalDate`; số không làm tròn round-trip về giá trị tương đương.
- [ ] Mọi phép parse được kiểm tra phần còn dư; dữ liệu nhập bên ngoài được validate theo yêu cầu sản phẩm.
- [ ] Currency theo mã ISO; fraction digits và rounding policy được xác định.
- [ ] Kỳ vọng chuỗi chính xác chỉ được dùng cho hợp đồng hiển thị có chủ đích; JDK/locale-data được quản lý khi snapshot có ý nghĩa.
- [ ] Không dùng `double` để tính tiền và không chia sẻ formatter mutable giữa nhiều thread.
- [ ] Test chạy tự động sau thay đổi formatter, nâng JDK hoặc thêm ngôn ngữ/vùng hỗ trợ.

## Tài liệu API chính thức

- [DateTimeFormatter — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [NumberFormat — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [DecimalFormat — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Currency — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html)

Nên coi **giá trị dữ liệu đúng, đồng tiền đúng, và quy tắc hiển thị đã được phê duyệt** là ba điều kiện nghiệm thu riêng. Cách kiểm thử này cho phép mở rộng i18n mà vẫn nhận diện đúng lỗi thực sự khi dữ liệu locale trên JDK thay đổi.