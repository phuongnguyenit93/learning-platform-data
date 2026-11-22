# Giới hạn của việc định dạng rồi phân tích để khôi phục dữ liệu gốc

## 1. Câu hỏi cốt lõi: `parse(format(x))` có bằng `x` không?

Trong Java Core Localization, quá trình **định dạng (format)** chuyển một giá trị có cấu trúc thành chuỗi dễ đọc theo locale, còn **phân tích (parse)** cố gắng diễn giải một chuỗi thành giá trị có cấu trúc. Hai việc này có liên quan nhưng **không mặc nhiên là hai phép toán nghịch đảo**.

```text
Giá trị ban đầu x
      |
      | format(x, locale, pattern, precision...)
      v
   Chuỗi hiển thị s
      |
      | parse(s, locale, pattern, parser options...)
      v
  Giá trị được khôi phục x'
```

Có hai điều kiện rất khác:

- **Về giá trị:** `x'` có cùng nghĩa toán học/thời điểm với `x` hay không?
- **Về dữ liệu gốc:** `x'` có giữ **đầy đủ kiểu, scale, độ chính xác, múi giờ, offset, ký tự và ngữ cảnh** của `x` hay không?

Thậm chí khi số học bằng nhau, đối tượng có thể không bằng nhau: `BigDecimal("1.20")` và `BigDecimal("1.2")` có cùng trị số nhưng `equals` trả `false` do khác scale. Một đối tượng `ZonedDateTime` với vùng `Asia/Ho_Chi_Minh` có thể bị giảm thành `OffsetDateTime` chỉ mang `+07:00`, nên thời điểm vẫn đúng nhưng danh tính vùng giờ đã mất.

Bài này tập trung giải thích **giới hạn của việc định dạng rồi phân tích để khôi phục dữ liệu gốc** trong nhóm *Phân tích đầu vào*: nguyên nhân, minh chứng Java 17+, những lỗi thường gặp và cách thiết kế lưu trữ/trao đổi dữ liệu an toàn.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `parse(format(x))` với `format(parse(s))` và hiểu vì sao cả hai không đảm bảo round-trip tuyệt đối.
2. Nhận diện **mất độ chính xác**, **mất scale**, **mất kiểu dữ liệu**, **mất vùng giờ** và **mất thông tin văn bản ban đầu**.
3. Dùng `DecimalFormat`, `ParsePosition` và `DateTimeFormatter` đúng mục đích, không coi chúng là bộ serializer.
4. Thiết kế đầu vào có **locale rõ ràng**, kiểm tra **toàn bộ chuỗi** và kiểm tra miền dữ liệu.
5. Lựa chọn biểu diễn lưu trữ chính tắc bằng kiểu số, `BigDecimal` và các dạng ISO 8601 phù hợp.

## 2. Vì sao một phép format thường không thể đảo ngược?

Muốn parse chính xác lại mọi thông tin của `x`, phép format phải không làm mất thông tin cần thiết. Nhưng formatter dành cho người đọc được thiết kế để **bỏ bớt chi tiết** hoặc **thay đổi cách biểu diễn**:

- **Làm tròn:** `1234.567` hiển thị `1,234.57` khi chỉ cho hai chữ số phần lẻ.
- **Bỏ các số 0 cuối:** `BigDecimal("1.20")` hiển thị `1.2` theo pattern tối đa hai chữ số phần lẻ nhưng không bắt buộc hai chữ số.
- **Chỉ hiện ngày:** thời gian `08:45:37.123456789` không có trong chuỗi `28/10/2026`.
- **Chỉ hiện offset:** `+07:00` không chứa tên vùng giờ gốc `Asia/Ho_Chi_Minh`.
- **Thay đổi locale:** dấu `,` có thể là phân nhóm ở `en-US` nhưng thập phân ở `de-DE`.
- **Biểu diễn đồng nghĩa:** `"1,234.50"` và `"1234.50"` có thể cùng được parse thành một giá trị; parser không biết input ban đầu viết theo dạng nào.
- **Thay chữ số, dấu hoặc khoảng trắng:** kết quả có thể dùng Arabic-Indic digits, U+202F, tiền tố/ký hiệu tiền tệ; một bước parse không luôn phục hồi các ký tự gốc.

Về mặt toán học, nếu hai giá trị `x1` và `x2` khác nhau nhưng formatter trả **cùng một chuỗi**, thì không thể tồn tại một parser chỉ nhìn chuỗi ấy mà khôi phục chính xác **cả hai**. Đây là tính **không đơn ánh (non-injective)** của phép format.

Ví dụ:

```text
format(1.20, pattern "#,##0.##") = "1.2"
format(1.2,  pattern "#,##0.##") = "1.2"
```

Cả hai đầu vào dẫn đến cùng `"1.2"`, nên sau parse không thể suy ra người dùng/bộ dữ liệu ban đầu đã dùng scale 2 hay scale 1.

**Kết luận:** chuỗi hiển thị không nên được xem là bản sao dự phòng toàn vẹn của dữ liệu gốc.

## 3. Ba cấp độ round-trip phải phân biệt

| Mục tiêu | Ví dụ kiểm tra | Có thể mất những gì? |
| --- | --- | --- |
| **Cùng giá trị số học** | `a.compareTo(b) == 0` với `BigDecimal` | Scale, hình thức viết, số 0 cuối |
| **Cùng dữ liệu/đối tượng** | `a.equals(b)` với kiểu có ngữ nghĩa rõ | Precision, scale, zone ID, nano-giây, loại dữ liệu |
| **Cùng chuỗi byte/ký tự ban đầu** | `originalText.equals(formattedAgain)` | Dấu nhóm, whitespace Unicode, chữ số, kiểu viết, dấu `+`, số 0 đầu |

Ví dụ, parser có thể đọc:

```text
"1234.50"
"1,234.50"
"001234.50"
```

thành cùng `BigDecimal("1234.50")` trong một số cấu hình `en-US`. Nhưng khi định dạng lại bằng `#,##0.00`, tất cả đều thành `"1,234.50"`. Nếu mục tiêu là phục hồi chuỗi đầu vào **chính xác từng ký tự**, bạn phải lưu chính chuỗi đầu vào hoặc thông tin biểu diễn bổ sung.

Cũng cần phân biệt hai biểu thức:

- `parse(format(x))`: từ giá trị → văn bản → giá trị. Có thể mất độ chính xác/cấu trúc.
- `format(parse(s))`: từ văn bản → giá trị → văn bản. Thường **chuẩn hóa cách viết** nên không bằng `s` dù giá trị vẫn hợp lệ.

## 4. Mất độ chính xác do rounding và giới hạn phần lẻ

`DecimalFormat` có thể chỉ hiển thị một số chữ số phần thập phân:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

Pattern `#,##0.00` yêu cầu hai chữ số phần lẻ. Giá trị `1234.567` được hiển thị `1,234.57` theo quy tắc rounding hiệu lực; lúc parse lại không còn cách nào biết chữ số cuối `7` của giá trị ban đầu.

Ví dụ:

```text
Giá trị BigDecimal:  1234.567
Chuỗi hiển thị:      1,234.57
Giá trị parse lại:   1234.57
Sai khác:            0.003
```

`setMaximumFractionDigits(2)` và `setRoundingMode(...)` giúp kiểm soát **đầu ra hiển thị**; chúng không làm phép format trở thành không mất mát. Việc parser có `setParseBigDecimal(true)` vẫn không giúp phục hồi chữ số đã bị formatter loại bỏ.

**Dùng `BigDecimal` để tránh sai số nhị phân** là việc khác với **tránh mất chữ số do formatter làm tròn**. Một BigDecimal chính xác đến hàng trăm chữ số vẫn có thể bị format thành một chuỗi chỉ có hai chữ số phần lẻ.

## 5. Mất `scale` dù giá trị vẫn bằng nhau

`BigDecimal` có hai khía cạnh đáng chú ý: **giá trị số học** và **scale**.

```text
new BigDecimal("1.20") : scale 2
new BigDecimal("1.2")  : scale 1
```

Pattern `#,##0.##` cho phép tối đa hai chữ số phần lẻ nhưng không bắt buộc, nên cả hai có thể được hiển thị `1.2`. Sau khi parse lại:

- `compareTo(...) == 0`: vẫn cùng giá trị số học.
- `equals(...)`: có thể `false` vì đối tượng ban đầu có scale khác.

Scale có thể quan trọng trong số tiền, chuẩn hiển thị hóa đơn, độ phân giải phép đo hoặc yêu cầu audit. Nếu nghiệp vụ cần giữ scale đầu vào, đừng dựa vào formatter bỏ số 0; lưu giá trị cùng scale hoặc dùng một biểu diễn decimal chính tắc có chính sách scale rõ.

Ngược lại, nếu scale **không** phải thuộc tính nghiệp vụ, không cần đòi `BigDecimal.equals` sau mọi round-trip: có thể kiểm tra `compareTo` để so giá trị. Chính sách kiểm tra phải theo nghĩa dữ liệu, không chọn bừa phương thức equality.

## 6. Ví dụ Java 17+: cùng giá trị nhưng không khôi phục đầy đủ

Tạo file `NumberRoundTripDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberRoundTripDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat rounded = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        rounded.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1234.567");
        String shown = rounded.format(original);
        BigDecimal parsed = (BigDecimal) rounded.parse(shown);

        System.out.println("original: " + original);
        System.out.println("shown: " + shown);
        System.out.println("parsed: " + parsed);
        System.out.println("same numeric value: "
                + (original.compareTo(parsed) == 0));

        DecimalFormat optional = new DecimalFormat(
                "#,##0.##",
                DecimalFormatSymbols.getInstance(Locale.US));
        optional.setParseBigDecimal(true);

        BigDecimal scaled = new BigDecimal("1.20");
        BigDecimal scaledBack =
                (BigDecimal) optional.parse(optional.format(scaled));

        System.out.println("scaled display: " + optional.format(scaled));
        System.out.println("scaled original: " + scaled);
        System.out.println("scaled parsed: " + scaledBack);
        System.out.println("BigDecimal.equals: "
                + scaled.equals(scaledBack));
        System.out.println("BigDecimal.compareTo: "
                + scaled.compareTo(scaledBack));

        DecimalFormat percent = (DecimalFormat)
                NumberFormat.getPercentInstance(Locale.US);
        percent.setParseBigDecimal(true);
        BigDecimal fraction = new BigDecimal("0.1245");
        String percentShown = percent.format(fraction);
        System.out.println("percent display: " + percentShown);
        System.out.println("percent parsed: "
                + percent.parse(percentShown));
    }
}
```

Chạy:

```bash
javac NumberRoundTripDemo.java
java NumberRoundTripDemo
```

Kết quả trên JDK có dữ liệu locale tiêu chuẩn:

```text
original: 1234.567
shown: 1,234.57
parsed: 1234.57
same numeric value: false
scaled display: 1.2
scaled original: 1.20
scaled parsed: 1.2
BigDecimal.equals: false
BigDecimal.compareTo: 0
percent display: 12%
percent parsed: 0.12
```

**Ba cơ chế mất thông tin:**

1. `1234.567 → 1,234.57 → 1234.57`: mất chữ số do rounding.
2. `1.20 → 1.2 → 1.2`: giữ giá trị nhưng mất scale.
3. `0.1245 → 12% → 0.12`: định dạng phần trăm thường nhân 100 và làm tròn số hiển thị; parse không phục hồi số thập phân gốc.

`NumberFormat.getPercentInstance` có quy tắc phụ thuộc locale/provider; ví dụ này dùng `Locale.US` và mặc định hiển thị phần trăm nguyên trên JDK đã kiểm thử. Trong sản phẩm, chọn rõ phần lẻ cần hiển thị và rounding policy.

## 7. Chế độ parse cũng có thể mất độ chính xác

Ngay cả trước khi format, nếu parse số thành `double`, bạn có thể mất chữ số:

```text
input:      12345678901234567890.123456789
Double:     một giá trị nhị phân xấp xỉ
BigDecimal: giữ chính xác các chữ số thập phân đã đọc
```

Trong Java, `NumberFormat.parse(...)` thường trả về `Long` hoặc `Double` theo dữ liệu/cấu hình. Với `DecimalFormat`, bật `setParseBigDecimal(true)` giúp parse các số **hữu hạn** thành `BigDecimal`, nhưng không làm đầu ra display trước đó chính xác trở lại.

Đối tượng `BigDecimal` cần được giữ xuyên suốt xử lý; chuyển `BigDecimal.doubleValue()` rồi quay lại `new BigDecimal(double)` có thể gây mất giá trị. Với input decimal canonical không có dấu ngăn cách locale, `new BigDecimal("1234.50")` tránh phải parse bằng `DecimalFormat`.

**Ngoại lệ của `setParseBigDecimal(true)`:** `NaN` hoặc vô cực có thể được parse thành `Double` chứ không phải `BigDecimal`. `BigDecimal` cũng không giữ âm zero phân biệt với zero. Nếu domain chỉ chấp nhận số hữu hạn, kiểm tra kiểu kết quả và miền giá trị.

## 8. Locale không khớp: cùng chuỗi, hai giá trị

Locale khác nhau có thể gán **vai trò ngược nhau** cho dấu `.` và `,`:

| Chuỗi | Theo `en-US` | Theo `de-DE` |
| --- | --- | --- |
| `1,234` | một nghìn hai trăm ba mươi tư | một phẩy hai ba bốn |
| `1.234` | một phẩy hai ba bốn | một nghìn hai trăm ba mươi tư |
| `1,234.50` | một nghìn hai trăm ba mươi tư phẩy năm | không thể mặc định hiểu đúng |
| `1.234,50` | không thể mặc định hiểu đúng | một nghìn hai trăm ba mươi tư phẩy năm |

Vì vậy, nếu định dạng ở `de-DE` mà parse lại bằng parser `en-US`, bạn có thể nhận **số sai nhưng không có exception**, hoặc parser chỉ đọc một phần chuỗi.

Tương tự, dấu phân nhóm của `fr-FR` có thể là U+202F (*narrow no-break space*), không phải space ASCII thông thường. Các hệ chữ số như `arab`, `thai` hoặc BCP 47 extension `u-nu-*` làm văn bản trông khác mà giá trị số không đổi. Không tự thay mọi dấu chấm/phẩy hoặc bỏ mọi whitespace để "chuẩn hóa" input; hãy dùng đúng locale của nguồn dữ liệu và validation tường minh.

**Locale dùng để format và parse phải được truyền rõ ràng**, thường là cùng locale và cùng chính sách ký hiệu, khi ứng dụng có chủ đích thực hiện round-trip hiển thị. Không gọi `Locale.setDefault(userLocale)` trên mỗi request: default locale là trạng thái chung của JVM, không phải riêng từng người dùng.

## 9. `parse` có thể chỉ đọc một tiền tố

Một lỗi phổ biến khác: nghĩ rằng `parse(input)` trả một số nghĩa là **toàn bộ chuỗi đã được xác thực**. Trên thực tế, `NumberFormat.parse` có thể chấp nhận phần đầu rồi dừng:

```text
raw:      "1,234.50oops"
parsed:   1234.50
ignored:  "oops"
```

Dùng `ParsePosition` để biết parser tiêu thụ bao nhiêu ký tự:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParseLimitsDemo {
    private static DecimalFormat parser(Locale locale) {
        NumberFormat base = NumberFormat.getNumberInstance(locale);
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        decimal.setParseBigDecimal(true);
        return decimal;
    }

    public static void main(String[] args) throws Exception {
        DecimalFormat us = parser(Locale.US);
        DecimalFormat de = parser(Locale.GERMANY);

        System.out.println("US 1,234: " + us.parse("1,234"));
        System.out.println("DE 1,234: " + de.parse("1,234"));
        System.out.println("US on DE text: " + us.parse("1.234,50"));

        String input = "1,234.50oops";
        ParsePosition position = new ParsePosition(0);
        Number parsed = us.parse(input, position);
        boolean fullInput = parsed instanceof BigDecimal
                && position.getIndex() == input.length();

        System.out.println("value: " + parsed);
        System.out.println("consumed: " + position.getIndex());
        System.out.println("length: " + input.length());
        System.out.println("fully parsed: " + fullInput);

        System.out.println("wrong grouping: "
                + us.parse("12,34.5"));
    }
}
```

```bash
javac LocaleParseLimitsDemo.java
java LocaleParseLimitsDemo
```

Kết quả:

```text
US 1,234: 1234
DE 1,234: 1.234
US on DE text: 1.234
value: 1234.50
consumed: 8
length: 12
fully parsed: false
wrong grouping: 1234.5
```

Diễn giải:

- Chuỗi `1,234` có ý nghĩa khác nhau giữa hai locale.
- Parser Mỹ đọc `1.234,50` thành `1.234` rồi bỏ phần `,50`.
- `ParsePosition.getIndex()` kiểm tra số ký tự đã tiêu thụ; trong ví dụ mới đọc 8/12 ký tự.
- Nhiều parser số Java **không kiểm tra nghiêm ngặt vị trí dấu phân nhóm**, vì vậy `12,34.5` có thể vẫn được đọc thành `1234.5`.

**Quan trọng:** chỉ kiểm tra `position.getIndex() == input.length()` vẫn không đảm bảo input là biểu diễn đúng duy nhất theo quy ước của locale. Với input số tiền hoặc dữ liệu được kiểm soát chặt, phải kiểm tra thêm định dạng được phép, độ dài, ký tự, thập phân, grouping, miền giá trị và scale. Không nên tin rằng `parse(format(x))` hoặc `format(parse(s))` chứng minh dữ liệu gốc hoàn toàn hợp lệ.

## 10. Mất kiểu dữ liệu, ký hiệu và hình thức viết ban đầu

Formatter có thể chuyển nhiều kiểu sang cùng một chuỗi:

- Số nguyên `1`, số thực `1.0`, `BigDecimal("1.00")` đều có thể hiển thị `"1"`.
- `-0.0` có thể hiển thị `"-0.00"`, nhưng parser đang bật `setParseBigDecimal(true)` trả `BigDecimal("0.00")` và không giữ dấu âm của zero.
- Số được nhập `"0012"` có thể format lại thành `"12"`, mất hai chữ số 0 đầu.
- Input có dấu `+`, có hoặc không có grouping hoặc dùng khoảng trắng Unicode khác nhau có thể được chuẩn hóa thành một biểu diễn duy nhất.

Vì thế cần hỏi **dữ liệu nào thật sự cần lưu**. Với số lượng hàng hóa, có thể chỉ cần giá trị nguyên. Với mã có số 0 đầu như `0012`, **đó là mã định danh dạng chuỗi**, không phải số nên đừng parse thành số rồi format lại. Với dữ liệu kiểm toán cần bảo tồn nguyên văn đầu vào, lưu giá trị canonical **và** raw input theo chính sách bảo mật/dữ liệu.

Cùng một nguyên tắc áp dụng cho định dạng tiền tệ và phần trăm: ký hiệu `$` không đủ phân biệt mọi mã tiền như USD/CAD/AUD; số `12%` không tự cho biết giá trị đầu vào là tỷ lệ `0.12`, số phần trăm `12`, hay một số đã làm tròn từ `0.1245`. Kiểu và đơn vị phải nằm trong schema/domain, không đoán ngược từ chuỗi UI.

## 11. Date/time còn mất nhiều thông tin hơn số

`java.time.format.DateTimeFormatter` cũng được thiết kế cho **trình bày** và **phân tích theo pattern**, không tự đóng gói đầy đủ mọi trường của đối tượng thời gian.

Ví dụ đối tượng:

```text
2026-10-28T08:45:37.123456789
```

Nếu định dạng bằng pattern `dd/MM/uuuu HH:mm`, chuỗi chỉ còn:

```text
28/10/2026 08:45
```

Sau khi parse lại thành `LocalDateTime`, seconds và nanoseconds không có trong chuỗi nên được khôi phục ở giá trị mặc định 0 (nếu kiểu đích có thể được tạo), không phải giá trị cũ. Hai thời điểm `08:45:01` và `08:45:59` có thể cùng hiển thị `08:45`.

Tương tự:

| Định dạng | Phần có thể bị mất |
| --- | --- |
| `dd/MM/uuuu` | Giờ, phút, giây, nano-giây |
| `dd/MM/uuuu HH:mm` | Giây và nano-giây; không chứa zone/offset |
| `HH:mm` | Ngày, offset, zone; không thể khôi phục `Instant` chỉ từ đây |
| `ISO_OFFSET_DATE_TIME` | Offset được giữ nhưng **region ZoneId** như `Europe/Paris` có thể không được ghi |
| Một mẫu có tên tháng địa phương hóa | Chịu ảnh hưởng locale, có thể mơ hồ/khác dữ liệu khi parse không cùng locale |
| Mẫu 2 chữ số năm `yy` | Không bảo tồn nguyên văn năm đầy đủ nếu không có quy ước diễn giải bổ sung |

Chỉ lưu `LocalDateTime` không đủ xác định một thời điểm tuyệt đối nếu không có múi giờ/offset. Ở nơi có quy tắc giờ mùa hè (DST), một giờ địa phương có thể **không tồn tại** (gap) hoặc **lặp hai lần** (overlap); cùng chuỗi `02:30` chưa chắc xác định duy nhất `Instant`. Không giải quyết bằng cách lấy default timezone của máy chủ.

**Một lưu ý Java:** trong pattern của `DateTimeFormatter`, `uuuu` biểu thị năm proleptic, còn `yyyy` là year-of-era. Khi parse ngày chặt chẽ (STRICT) mà không có era, các pattern `yyyy` có thể cần thông tin era hoặc resolver phù hợp. Trong ví dụ dưới dùng `uuuu`.

## 12. Ví dụ Java 17+: mất giây/nano-giây và danh tính vùng giờ

Tạo file `DateTimeRoundTripDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DateTimeRoundTripDemo {
    public static void main(String[] args) {
        LocalDateTime original = LocalDateTime.of(
                2026, 10, 28, 8, 45, 37, 123_456_789);

        DateTimeFormatter minutes = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));

        String shown = minutes.format(original);
        LocalDateTime parsed = LocalDateTime.parse(shown, minutes);

        System.out.println("original: " + original);
        System.out.println("shown: " + shown);
        System.out.println("parsed: " + parsed);
        System.out.println("same: " + original.equals(parsed));

        ZonedDateTime zoned = ZonedDateTime.of(
                2026, 10, 28, 8, 45, 37, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));
        String withOffset = DateTimeFormatter.ISO_OFFSET_DATE_TIME
                .format(zoned);
        OffsetDateTime offsetParsed = OffsetDateTime.parse(
                withOffset, DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        System.out.println("original zone: " + zoned.getZone());
        System.out.println("offset text: " + withOffset);
        System.out.println("parsed zone: "
                + offsetParsed.toZonedDateTime().getZone());
        System.out.println("same instant: "
                + zoned.toInstant().equals(offsetParsed.toInstant()));

        String withZone = DateTimeFormatter.ISO_ZONED_DATE_TIME
                .format(zoned);
        ZonedDateTime restored = ZonedDateTime.parse(
                withZone, DateTimeFormatter.ISO_ZONED_DATE_TIME);
        System.out.println("zone kept: " + restored.getZone());
        System.out.println("zoned equal: " + zoned.equals(restored));
    }
}
```

```bash
javac DateTimeRoundTripDemo.java
java DateTimeRoundTripDemo
```

Đầu ra với phiên bản Java đã đối chiếu:

```text
original: 2026-10-28T08:45:37.123456789
shown: 28/10/2026 08:45
parsed: 2026-10-28T08:45
same: false
original zone: Asia/Ho_Chi_Minh
offset text: 2026-10-28T08:45:37+07:00
parsed zone: +07:00
same instant: true
zone kept: Asia/Ho_Chi_Minh
zoned equal: true
```

Giải thích:

1. `DateTimeFormatter` với phút là độ phân giải cuối cùng đã **bỏ giây và nano-giây**.
2. `ISO_OFFSET_DATE_TIME` giữ được offset và đủ thông tin về instant ở ví dụ, nhưng `OffsetDateTime` được chuyển sang `ZonedDateTime` có zone ID chỉ là `+07:00`, không còn `Asia/Ho_Chi_Minh`.
3. `ISO_ZONED_DATE_TIME` có thể lưu cả `[Asia/Ho_Chi_Minh]` và phục hồi zone với trường hợp này, nhưng điều đó không làm cho **mọi pattern tùy biến** trở thành lossless.
4. Các quy tắc múi giờ trong tzdb có thể cập nhật; nếu ứng dụng phải tái hiện chính xác cách hiển thị lịch sử dưới một bộ quy tắc cụ thể, cần thiết kế lưu trữ/phiên bản dữ liệu phù hợp.

Trong các hệ thống nghiệp vụ, thường lưu `Instant` cho thời điểm tuyệt đối, và lưu thêm `ZoneId` nếu cần bảo tồn ý nghĩa "giờ địa phương của vùng" để hiển thị về sau. Với lịch hẹn tương lai, có thể cần lưu `LocalDateTime` và `ZoneId` để giữ giờ tường minh theo khu vực, đồng thời xác định chính sách khi gặp DST gap/overlap.

## 13. Parse ngày giờ có thể "sửa" input nếu cấu hình quá dễ dãi

Không chỉ mất thông tin, parser ngày cũ còn có thể tự chuẩn hóa ngày ngoài miền.

Ví dụ `java.text.SimpleDateFormat` có chế độ **lenient** mặc định, nên một ngày không tồn tại như "32/01/2026" có thể bị quy đổi sang tháng khác khi parse. Trên code mới, ưu tiên `java.time` với `DateTimeFormatter` và lựa chọn `ResolverStyle.STRICT` khi cần xác thực input.

Ví dụ **độc lập**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class StrictDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            LocalDate.parse("31/02/2026", strict);
            System.out.println("accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalid date rejected");
        }

        System.out.println(LocalDate.parse("28/02/2026", strict));
    }
}
```

```bash
javac StrictDateDemo.java
java StrictDateDemo
```

```text
invalid date rejected
2026-02-28
```

`STRICT` giúp phát hiện ngày lịch không hợp lệ nhưng không tự cung cấp zone/offset đã thiếu, và cũng không khôi phục các trường đã bỏ khỏi pattern. **Strict parsing và lossless serialization là hai yêu cầu khác nhau.**

## 14. Chuỗi được format lại không nhất thiết bằng chuỗi đầu vào

Giả sử người dùng nhập:

```text
1234.50
```

Parser theo `en-US` có thể tạo `BigDecimal("1234.50")`. Nếu formatter bật grouping, khi hiển thị lại có thể thu:

```text
1,234.50
```

Về giá trị, hai chuỗi có thể tương đương; về ký tự, chúng khác nhau. Thậm chí phần whitespace có thể khác `U+0020` so với `U+202F`; locale có thể chọn hệ chữ số `latn`, `arab` hoặc `thai`. Do đó:

- **Không so sánh chuỗi UI** để quyết định hai số/đối tượng thời gian có bằng nhau.
- **Không lấy chuỗi UI làm chữ ký, mã định danh hay khóa cache** trừ khi hợp đồng xác định rõ mọi thuộc tính biểu diễn.
- **Không dùng `format(parse(s)).equals(s)` làm validator duy nhất**: nó có thể từ chối đầu vào hợp lệ nhưng viết khác chuẩn, hoặc chấp nhận đầu vào đã bị parser làm mất thông tin.

Nếu yêu cầu xác minh tính **chính tắc của một định dạng nhập**, có thể parse chặt và kiểm tra lại theo schema được định nghĩa rõ, nhưng đó là chính sách ứng dụng, **không** phải bảo đảm chung của mọi formatter.

## 15. Những trường hợp khác cũng không round-trip tự động

### Tiền tệ và đơn vị

Một chuỗi `$1,234.50` chứa ký hiệu `$` nhưng không tự truyền đầy đủ mã tiền tệ, quy tắc làm tròn và đơn vị tính. `NumberFormat.getCurrencyInstance(locale)` có thể dùng currency mặc định của locale, không nhất thiết là currency của giao dịch. Nếu lưu tiền, cần cấu trúc như **amount + currency code**, không suy currency từ dấu tiền.

### Phần trăm

Định dạng phần trăm thường nhân 100 rồi thêm `%`; số `0.1245` có thể hiển thị `12%`. Nếu parse lại, có thể chỉ được `0.12`. Không lấy dữ liệu dạng tỷ lệ `12` và `0.12` làm một nếu chưa thống nhất domain representation.

### Compact numbers

Chuỗi như `1K`, `1,2 nghìn` hoặc dạng tắt theo ngôn ngữ có thể chứa giá trị làm tròn và hậu tố; không thể luôn suy lại số gốc chính xác. Dùng `NumberFormat.getCompactNumberInstance` cho trình bày nếu phù hợp, nhưng không dùng chuỗi compact cho lưu trữ.

### Ký hiệu đặc biệt và âm zero

`DecimalFormat` có thể định dạng `Double.NaN`, vô cực hoặc `-0.0`; sau parse `BigDecimal` không có tương đương cho NaN/vô cực và không duy trì trạng thái âm zero như `double`. Nếu các trạng thái đặc biệt là một phần domain, phải có schema/kiểu dữ liệu thích hợp; không chỉ lưu chuỗi hiển thị.

## 16. Thiết kế đúng: tách giá trị miền, lưu trữ và trình bày

Hãy xác định rõ mục tiêu của từng tầng:

| Tầng | Đại diện nên dùng | Chỉ thực hiện |
| --- | --- | --- |
| **Domain** | `BigDecimal`, `long`, `Instant`, `ZonedDateTime` hoặc kiểu nghiệp vụ rõ nghĩa | Tính toán, xác thực, diễn giải |
| **Storage / API** | Cột decimal/numeric, JSON number theo schema, decimal string canonical, ISO 8601 và metadata cần thiết | Giữ những trường dữ liệu cần round-trip |
| **Presentation** | `NumberFormat`, `DecimalFormat`, `DateTimeFormatter` kèm `Locale` | Chuyển thành văn bản người dùng đọc được |
| **Input** | Parser theo locale + validator có chính sách rõ | Hiểu chuỗi người dùng nhập, từ chối input sai |

Ví dụ một luồng an toàn:

```text
User input: "1.234,50" (de-DE)
    |
    | DecimalFormat de-DE; setParseBigDecimal(true)
    | ParsePosition + validation domain
    v
BigDecimal("1234.50")
    |
    +--> Lưu DECIMAL(14,2) hoặc decimal string theo schema
    |
    +--> Hiển thị "1,234.50" cho en-US
    |
    +--> Hiển thị "1.234,50" cho de-DE
```

Nếu cần giữ **cách người dùng đã nhập**, phải lưu raw input như một thuộc tính riêng (có giới hạn/kiểm soát dữ liệu cá nhân, bảo mật và retention). Không thể khôi phục input raw từ BigDecimal canonical nếu những ký tự biểu diễn đã bị bỏ qua.

### Ví dụ lưu trữ decimal chính tắc và khôi phục

Tạo file `CanonicalDecimalDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class CanonicalDecimalDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.50");

        String stored = original.toPlainString();
        BigDecimal restored = new BigDecimal(stored);

        NumberFormat display = NumberFormat.getNumberInstance(
                Locale.GERMANY);
        display.setMinimumFractionDigits(2);
        display.setMaximumFractionDigits(2);

        System.out.println("stored: " + stored);
        System.out.println("restored: " + restored.toPlainString());
        System.out.println("same BigDecimal: "
                + original.equals(restored));
        System.out.println("display: " + display.format(restored));
    }
}
```

```bash
javac CanonicalDecimalDemo.java
java CanonicalDecimalDemo
```

```text
stored: 1234.50
restored: 1234.50
same BigDecimal: true
display: 1.234,50
```

Ở đây `BigDecimal.toPlainString()` mang dữ liệu số decimal và scale trong ví dụ này. Nó phù hợp cho hợp đồng lưu trữ decimal string được xác định rõ; với `BigDecimal` có scale âm, `toPlainString()` có thể thay đổi biểu diễn scale khi khôi phục, nên nếu **bảo toàn mọi scale ở mọi trường hợp** là yêu cầu nghiêm ngặt, dùng `toString()` cùng `new BigDecimal(String)` hoặc lưu `unscaledValue` + `scale` rõ ràng. Không xem `toPlainString` là hợp đồng tuyệt đối cho mọi đặc tính biểu diễn của mọi BigDecimal.

Dạng canonical không chỉ là "bỏ dấu nhóm": phải định nghĩa cả kiểu, dấu âm, giới hạn, độ chính xác, scale, timezone/currency khi áp dụng.

## 17. Checklist kiểm tra round-trip trong Java

Trước khi quyết định dùng `parse(format(x))`, trả lời các câu hỏi:

1. **Mục đích:** muốn giữ đúng giá trị toán học, đúng đối tượng, đúng thời điểm, hay đúng chuỗi gốc?
2. **Có rounding không?** Cấu hình maximum fraction digits, precision và rounding mode là gì?
3. **Có mất scale không?** `BigDecimal.equals` khác `compareTo` như thế nào trong domain?
4. **Có mất field không?** Formatter ngày/giờ có bỏ seconds/nanos/zone/offset/era/chronology không?
5. **Locale nào được dùng hai chiều?** Có ổn định giữa các request và hệ thống khác nhau không?
6. **Có ký hiệu và nhóm số mơ hồ không?** Dấu `,`, `.`, U+202F, non-Latin digits được xử lý ra sao?
7. **Parser có dùng hết chuỗi không?** Kiểm tra `ParsePosition`/parse-unresolved hoặc API parse strict thích hợp.
8. **Parser có lenient không?** Có chấp nhận grouping sai hoặc ngày không tồn tại rồi sửa ngầm không?
9. **Có giá trị đặc biệt không?** NaN, infinity, signed zero, ngày DST gap/overlap, tiền tệ?
10. **Có yêu cầu lưu chính xác raw text không?** Nếu có, không thể suy từ giá trị parsed.
11. **Đã kiểm tra đủ các phiên bản/locale provider chưa?** Dữ liệu CLDR, pattern và Unicode symbols có thể thay đổi.
12. **Serialization có schema không?** Lưu type/scale, currency, zone và phần metadata cần thiết, thay vì một chuỗi display.

Đối với test round-trip, nên tách riêng:

- `assertNumericEquals`: kiểm tra số học bằng nhau nếu chấp nhận mất scale.
- `assertEquals`: kiểm tra đầy đủ identity/scale/zone nếu đây là hợp đồng.
- `assertTextEquals`: chỉ dùng khi yêu cầu bảo tồn **đúng văn bản**.
- `assertRejectsInvalid`: kiểm tra dữ liệu thừa, sai dấu nhóm, ngày không hợp lệ, các số đặc biệt không cho phép.

## 18. Lỗi thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `format(x)` làm phương thức serialize mặc định | Rounding, locale và pattern có thể làm mất dữ liệu | Lưu schema canonical/domain value |
| Parse lại số đã làm tròn rồi mong bằng số gốc | Chữ số không còn trong chuỗi | Không dùng display làm nguồn sự thật |
| Nghĩ `setParseBigDecimal(true)` tự khôi phục precision đã mất | Nó chỉ giữ chính xác **chuỗi được parse** | Bảo toàn dữ liệu trước khi format |
| So `BigDecimal.equals` mà không xem scale | Kết luận khác nhau dù cùng số học | Chọn equality theo nghiệp vụ |
| Dùng parser khác locale formatter | Giá trị sai hoặc parse một phần | Truyền locale và settings tường minh |
| Không kiểm tra phần đuôi input | `parse` nhận tiền tố, bỏ dữ liệu sai | `ParsePosition` và validation |
| Coi parse hết chuỗi là xác thực grouping | Parser có thể dễ dãi với nhóm dấu | Kiểm tra cú pháp theo hợp đồng |
| Format date chỉ đến phút rồi đòi phục hồi nano-giây | Thông tin đã bị bỏ | Dùng lưu trữ thời gian đầy đủ |
| Lưu offset mà không lưu region zone ID | Không khôi phục `Asia/Ho_Chi_Minh` | Lưu `ZoneId` nếu cần |
| Lưu `LocalDateTime` rồi suy thành instant bằng default timezone | Có thể sai DST/vùng giờ | Lưu `Instant` hoặc zone và chính sách DST |
| Xem `NaN`/infinity là `BigDecimal` | ClassCastException hoặc dữ liệu không hợp lệ | Kiểm tra kiểu và domain |
| Lưu mã `0012` như số | Mất số 0 đầu | Mã định danh phải là `String` |
| Dùng `DecimalFormat` singleton mutable giữa thread | Race và thay đổi cấu hình | Formatter riêng từng xử lý |
| Dựa vào chuỗi locale để suy currency | Ký hiệu tiền có thể mơ hồ | Lưu currency code độc lập |

## 19. Tự kiểm tra

1. **`parse(format(new BigDecimal("1234.567")))`** với pattern chỉ có hai chữ số thập phân có thể ra số nào? **`1234.57`**, không phải `1234.567`.
2. **`1.20` và `1.2`** được format thành `1.2`: có khôi phục scale ban đầu được không? **Không**, vì hai dữ liệu khác nhau đã thành cùng một chuỗi.
3. Nếu dùng `parseBigDecimal` thì chữ số đã bị formatter làm tròn có quay lại không? **Không**; parser chỉ có chuỗi đầu vào hiện tại.
4. Chuỗi `1,234` ở `en-US` và `de-DE` có cùng giá trị không? **Không**; locale có thể hiểu nó là `1234` hoặc `1.234`.
5. Vì sao `parse("1,234.50oops")` có thể trả số mà không báo lỗi? **Parser có thể chấp nhận tiền tố**; kiểm tra `ParsePosition`.
6. Nếu chuỗi hiển thị chỉ đến phút, có thể khôi phục nano-giây gốc từ nó không? **Không**.
7. `ISO_OFFSET_DATE_TIME` giữ offset `+07:00` có khôi phục `ZoneId.of("Asia/Ho_Chi_Minh")` không? **Không tự động**; offset không phải region ID.
8. Có thể suy `Instant` chính xác từ `LocalDateTime` mà không biết zone/offset không? **Không**, đặc biệt có DST gap/overlap.
9. Với `BigDecimal("1.20")` và `BigDecimal("1.2")`, `compareTo` và `equals` khác nhau thế nào? **`compareTo==0` nhưng `equals=false`**.
10. Muốn bảo toàn byte/ký tự người dùng đã nhập như `"001234.50"`, chỉ lưu `BigDecimal` có đủ không? **Không**; phải lưu raw text hoặc metadata biểu diễn bổ sung.
11. Khi lưu dữ liệu tiền tệ, format `"$10.00"` có đủ thông tin không? **Không**; cần mã tiền tệ và amount theo schema.
12. Đâu là ranh giới trách nhiệm tốt nhất? **Domain/storage giữ cấu trúc và dữ liệu chính xác, presentation format theo locale, input parser + validator chuyển chuỗi thành domain value.**

## Tài liệu tham khảo

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): format/parse theo locale và phạm vi của parser.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): pattern, rounding, `setParseBigDecimal`, trường hợp `NaN`/infinity.
- [Java SE 21 — ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html): kiểm tra phần đã được parse.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): giá trị, scale, precision, canonical strings.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern, ISO formatters và resolver style.
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): zone, offset, instant và DST.
- [Unicode CLDR — Date/Number Formats](https://cldr.unicode.org/): dữ liệu locale có thể ảnh hưởng ký hiệu và kiểu định dạng.
