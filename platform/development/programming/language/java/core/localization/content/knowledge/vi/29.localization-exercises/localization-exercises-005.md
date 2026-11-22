# Phân tích dữ liệu nhập theo locale với kiểm tra toàn chuỗi trong Java

## 1. Bài toán thực tế: parse thành công chưa chắc đầu vào hợp lệ

Người dùng ở các khu vực khác nhau có thể nhập **cùng giá trị số** bằng chuỗi khác nhau: `1,234.50` theo quy ước `en-US`, nhưng `1.234,50` theo `de-DE`. Một ngày cũng có thể được viết `29/02/2024`, `02/29/2024` hoặc theo mẫu chữ tên tháng của một ngôn ngữ. Ứng dụng Java phục vụ nhiều locale cần hiểu **đầu vào văn bản** theo quy tắc đã chọn và đồng thời xác nhận **người dùng đã nhập toàn bộ một giá trị hợp lệ**, không chỉ một tiền tố mà parser hiểu được.

Ví dụ một số parser có thể phân tích phần `123` của `123abc` rồi dừng ở chữ `a`. Nếu ứng dụng chỉ hỏi “parse có trả về `Number` không?” thì nó có thể vô tình chấp nhận một chuỗi đã chứa dữ liệu rác. Ngược lại, ngay cả khi parser **đã tiêu thụ toàn chuỗi**, nó vẫn có thể chấp nhận cách đặt dấu phân nhóm mà nghiệp vụ không cho phép.

Bài thực hành này giải quyết **hai lớp kiểm tra độc lập**:

1. **Kiểm tra toàn chuỗi (full consumption):** parser phải xử lý đến đúng cuối input, không còn ký tự thừa.
2. **Kiểm tra chính sách cú pháp và ngữ nghĩa:** định dạng, dấu nhóm, số chữ số phần thập phân, dải giá trị, ngày hợp lịch và đơn vị tiền tệ phải khớp contract đã thiết kế.

**Không coi hai bước là một.** `ParsePosition` cho phép kiểm tra việc parser đã đi đến đâu; `ResolverStyle.STRICT` giúp phân giải ngày lịch hợp lệ; nhưng một hệ thống tài chính còn cần chính sách về dấu nhóm, độ chính xác và giới hạn tiền riêng.

## 2. Quyết định đơn vị dữ liệu trước khi parse

Một ứng dụng đa ngôn ngữ thường có ít nhất hai loại input:

| Nguồn nhập | Ví dụ | Cách nên xử lý |
| --- | --- | --- |
| **Ô nhập UI theo locale** | `12,50` tại `de-DE` | Chọn locale hỗ trợ, kiểm tra cú pháp, parse theo locale, validate nghiệp vụ |
| **Trường giao tiếp máy có schema cố định** | JSON number `12.50` | Dùng parser JSON theo chuẩn; không phụ thuộc `Accept-Language` |
| **CSV nhập theo hợp đồng nguồn** | `12.50` với decimal `.` cố định | Theo dialect/schema của nguồn, không đoán locale từ người đọc |
| **Ngày lịch nhập trên UI** | `29/02/2024` theo mẫu công bố | Parse `LocalDate` theo pattern/locale và resolver strict |
| **Thời điểm trao đổi API** | `2024-02-29T10:00:00Z` | Parse ISO instant/offset theo contract, không dùng định dạng ngày UI |
| **Số tiền có currency** | amount `12,50` + currency `EUR` | Parse decimal, xác minh currency riêng, áp scale/range theo quy tắc |
| **Mã định danh kỹ thuật** | `INV-00125` | Không tự xử lý bằng `NumberFormat` vì có thể mất số 0 đầu và ký tự mã |

`Locale` là một thông số của **quy tắc đọc/hiển thị văn bản**, không xác thực nguồn tiền, đơn vị tiền, timezone hay quốc gia pháp lý. Locale do người dùng chọn và contract dữ liệu máy cần được quản lý tách biệt.

### 2.1. Điều gì xảy ra nếu chọn sai locale?

Với locale Mỹ, dấu phẩy thường là phân nhóm và dấu chấm thường là thập phân. Với Đức, vai trò của hai dấu ngược lại. Chuỗi `1,23` có thể mang ý “một phẩy hai ba” đối với người dùng quen dấu phẩy thập phân; nhưng parser `en-US` có thể diễn giải nó như **123** do dấu phẩy được xử lý là separator nhóm.

Không chỉ kiểm tra “parser không báo lỗi”; cần bảo đảm locale được lựa chọn chính xác từ ngữ cảnh UI hoặc cấu hình nguồn import. Đừng thử parse tuần tự bằng nhiều locale rồi chọn kết quả đầu tiên thành công: cùng chuỗi có thể có **nhiều cách hiểu hợp lệ nhưng khác giá trị**.

## 3. NumberFormat và DecimalFormat trong Java 17

`java.text.NumberFormat` là API định dạng và phân tích số theo `Locale`:

~~~java
NumberFormat formatter = NumberFormat.getNumberInstance(Locale.US);
~~~

Đây là **đoạn minh họa trong một phương thức**, cần `import java.text.NumberFormat;` và `import java.util.Locale;`. Một số việc quan trọng:

- `getNumberInstance(locale)` lấy bộ formatter/parser theo quy ước dữ liệu locale do runtime cung cấp.
- `NumberFormat.parse(String, ParsePosition)` cho biết giá trị và cập nhật vị trí ký tự đã tiêu thụ.
- `DecimalFormat` là implementation phổ biến có thêm `setParseBigDecimal(true)`.
- `DecimalFormat` là **mutable**, không nên chia sẻ một instance rồi thay đổi cấu hình giữa các thread.
- Dữ liệu locale/CLDR và locale providers có thể thay đổi giữa JDK; đừng hard-code một kết quả sắp xếp/dấu của mọi locale mà không kiểm tra runtime hỗ trợ.

Đối với xử lý số tiền cần chính xác, nên sử dụng `BigDecimal` thay vì tính qua `double`. Trong môi trường Java chuẩn, `NumberFormat.getNumberInstance(Locale.US)` thường là `DecimalFormat`; nếu một locale provider khác trả subtype khác, mã cần xử lý rõ thay vì cast mù quáng.

### 3.1. ParsePosition theo đúng ý nghĩa

~~~java
ParsePosition pos = new ParsePosition(0);
Number result = formatter.parse(text, pos);
~~~

Đây là hai lệnh minh họa, giả sử `formatter` và `text` đã có. Các đại lượng:

- `pos.getIndex()`: chỉ số UTF-16 ngay sau phần parser đã tiêu thụ thành công.
- `text.length()`: tổng số UTF-16 code units của input.
- `pos.getErrorIndex()`: vị trí parser ghi nhận lỗi khi parse thất bại, nếu có. Có thể vẫn là `-1` khi parser **thành công một phần** rồi dừng trước hậu tố.
- `result`: giá trị được parser trả, hoặc `null` khi không thể phân tích ở vị trí bắt đầu.

Điều kiện cơ bản:

~~~java
boolean fullyConsumed = result != null
        && pos.getIndex() == text.length();
~~~

Đây là điều kiện **cần** để chấp nhận một giá trị số, không tự động là điều kiện **đủ** cho mọi quy tắc nhập liệu.

Nếu tạo `ParsePosition(0)`, không được chỉ xét `pos.getIndex() > 0`; điều đó chỉ chứng minh có một tiền tố được tiêu thụ. Luôn so index với `length()`, và xét `result != null`.

**Index là UTF-16**, không phải byte offset hay code point ordinal. Với chuỗi có surrogate pairs, `length()` vẫn là mốc kết thúc phù hợp vì `ParsePosition` cũng hoạt động theo chỉ số `String`.

### 3.2. Vì sao parse(String) không bảo đảm toàn chuỗi?

Overload đơn giản `NumberFormat.parse(String)` được thiết kế tiện lợi và có thể chấp nhận **một tiền tố hợp lệ**, tùy pattern/parser. Nó không cung cấp một kết quả full-consumption trực tiếp cho caller như `ParsePosition`.

Nếu người dùng nhập `1,234.50oops`, bộ parser `en-US` có thể phân tích phần số nhưng để lại `oops`. Mã validation cần từ chối input như vậy.

Chương trình độc lập ở mục 8 thực sự thử trường hợp có hậu tố và in `en suffix=REJECTED`.

### 3.3. BigDecimal và phân tích chính xác

Với `DecimalFormat`, gọi `setParseBigDecimal(true)` trước khi parse:

~~~java
DecimalFormat decimal = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
decimal.setParseBigDecimal(true);
~~~

Đây là snippet theo cấu hình provider phổ biến; ví dụ hoàn chỉnh ở mục 8 **kiểm tra `instanceof`** trước khi sử dụng. Khi bật chế độ này, phần số hữu hạn trong ví dụ trả `BigDecimal`. Không dùng `new BigDecimal(Double.toString(...))` như một cách khắc phục tùy tiện nếu trước đó parser đã làm mất precision qua `double`.

`BigDecimal` giữ giá trị thập phân chính xác; nhưng kiểm tra số tiền hợp lệ vẫn cần logic nghiệp vụ: dương/không âm, giới hạn, scale, currency, rounding policy và khả năng được lưu trong hệ thống.

## 4. Full consumption chưa đủ: dấu nhóm và độ rộng

Thử chuỗi:

~~~text
Input en-US: "1,23"
~~~

Trong môi trường Java đã kiểm thử, `DecimalFormat` do `NumberFormat.getNumberInstance(Locale.US)` cung cấp **đọc hết chuỗi** và trả `123`. Parser linh hoạt với vị trí dấu phân nhóm; nó không nhất thiết từ chối mọi cách nhóm không chuẩn.

Vì vậy:

~~~text
parse thành công + pos.index == input.length
KHÔNG SUY RA
dấu nhóm hợp lệ theo quy tắc UI hoặc kế toán.
~~~

Tùy yêu cầu, có thể chọn:

- **Chấp nhận grouping linh hoạt** trong input thông thường và làm rõ giá trị đã phân tích khi xác nhận.
- **Cấm grouping** cho một ô nhập tiền để tránh mơ hồ; chỉ chấp nhận chữ số và dấu thập phân theo locale.
- **Cho phép grouping nghiêm ngặt** theo pattern đã quy định, với quy tắc nhóm đầu, nhóm giữa và loại separator cụ thể.
- **Yêu cầu format giao thức cố định** (ví dụ JSON decimal string có dấu chấm) cho dữ liệu máy, không dựa vào locale.

Trong ví dụ thực hành này, phương thức `parseMoneyNoGrouping` triển khai một **chính sách cố ý hẹp**:

1. Chỉ chấp nhận chữ số ASCII `0`–`9`.
2. Không chấp nhận dấu nhóm, dấu âm, dấu cộng hoặc khoảng trắng.
3. Chấp nhận phần thập phân có **một hoặc hai chữ số** sau dấu thập phân của locale.
4. Sau khi pass regex, vẫn phải parse số và xác minh full consumption.

Đây là một **ví dụ policy** cho trường giá trị không âm, không phải định nghĩa đầy đủ của “số hợp lệ trong mọi locale”. Nó không hỗ trợ các chữ số bản địa hóa như Arabic-Indic và không áp dụng được cho tất cả mẫu nhóm số của thế giới. Nếu sản phẩm cần hỗ trợ chữ số bản địa hóa, hãy xác định rõ bộ chữ số được phép và cơ chế số hóa tương ứng, rồi kiểm thử từng locale.

### 4.1. Lấy separator theo locale

~~~java
char separator = DecimalFormatSymbols.getInstance(locale)
        .getDecimalSeparator();
~~~

Đây là snippet cần `locale` đã được xác định và import `DecimalFormatSymbols`. Kết hợp với `Pattern.quote(String.valueOf(separator))` để ký tự như dấu chấm `.` được coi là **ký tự literal trong regex**, không phải metacharacter “bất kỳ ký tự nào”.

Đừng thay tất cả dấu phẩy thành dấu chấm rồi parse bằng `BigDecimal` khi đầu vào còn có group separator. Ví dụ `1.234,50` theo Đức có dấu nhóm chấm và dấu decimal phẩy; một phép replace ngây thơ có thể tạo giá trị sai hoặc lỗi khó chẩn đoán.

### 4.2. Có cần so round-trip format(parse(s)) với s?

So `format(parse(input)).equals(input)` có thể hữu ích để phát hiện sai lệch nếu bạn **quy định duy nhất một dạng canonical display**, nhưng không phải bộ kiểm tra locale-input tổng quát:

- Người dùng có thể nhập `12,5` thay vì `12,50`, cả hai cùng giá trị.
- Parser/formatter có thể chèn/bỏ dấu nhóm theo pattern.
- Formatter có thể làm tròn, thêm số 0 hoặc dùng dấu cách/Unicode spacing khác.
- Các locale provider có thể có cách biểu diễn khác giữa các phiên bản JDK.

Nếu business cần chính xác một pattern, định nghĩa pattern/cú pháp cụ thể trước rồi validate. Nếu chấp nhận nhiều cách nhập hợp lệ, đừng dùng equality của chuỗi đã format làm tiêu chuẩn duy nhất.

## 5. Date parsing: nghiêm ngặt cả cú pháp và lịch

Số và ngày không có cùng mô hình. `LocalDate` là một **ngày lịch**, cần kiểm tra tháng, ngày, năm nhuận và ranh giới input. Java 17 có bộ `java.time` hiện đại:

~~~java
DateTimeFormatter dateFormatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", locale)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse(text, dateFormatter);
~~~

Đây là snippet nằm trong một phương thức, cần import `DateTimeFormatter`, `ResolverStyle`, `LocalDate`; `locale` và `text` đã được cấp. `LocalDate.parse` dùng formatter để parse **toàn bộ input** và báo `DateTimeParseException` nếu còn hậu tố hoặc ngày không hợp lệ.

### 5.1. Vì sao dùng uuuu thay yyyy?

Trong `DateTimeFormatter`:

- `u` là **proleptic year**.
- `y` là **year-of-era**, có thể cần thông tin `ERA` để resolve đầy đủ ở `ResolverStyle.STRICT`.
- `M` là tháng trong năm.
- `d` là ngày trong tháng.

Với một trường ngày ISO đơn giản cần strict resolving, `dd/MM/uuuu` thuận tiện hơn `dd/MM/yyyy`. Dùng `yyyy` với STRICT mà không cung cấp era có thể phát sinh lỗi resolve không mong muốn. Đừng thay `uuuu` bằng `yyyy` chỉ vì hai pattern trông tương đương trên màn hình.

### 5.2. STRICT, SMART và LENIENT

`ResolverStyle.STRICT` yêu cầu bộ trường ngày hợp lệ theo calendar chronology. Chẳng hạn:

~~~text
29/02/2024 -> hợp lệ (2024 là năm nhuận)
29/02/2023 -> không hợp lệ (2023 không nhuận)
31/04/2024 -> không hợp lệ (tháng 4 chỉ 30 ngày)
~~~

`ResolverStyle.SMART` có thể điều chỉnh một số ngày vượt cuối tháng trong quá trình phân giải, ví dụ số ngày 31 thành cuối tháng; `LENIENT` còn có thể cộng dồn các trường vượt phạm vi. **Không** dùng SMART/LENIENT cho ngày nhập cần được kiểm chứng đúng hệt lịch mà người dùng đưa vào.

Lưu ý kỹ thuật: `ResolverStyle` xử lý **giai đoạn resolve các trường lịch**, không quy định toàn bộ lexical grammar. Nếu cần kiểm soát width, chữ số, dấu phân tách hoặc case folding rất cụ thể, cần một `DateTimeFormatterBuilder` hoặc kiểm tra cú pháp bổ sung. `LocalDate.parse` đã kiểm tra full consumption, nhưng điều đó không tự kiểm tra policy về ngôn ngữ, range nghiệp vụ hoặc timezone.

### 5.3. DateTimeFormatter immutable; DecimalFormat thì không

`DateTimeFormatter` là **immutable** và thread-safe, nên có thể tạo sẵn instance cho một pattern/locale cố định và tái sử dụng an toàn. `DecimalFormat` là **mutable** và không nên dùng chung giữa các thread mà không có quy tắc bảo vệ riêng. Trong ví dụ dưới, tạo `DecimalFormat` mới theo lần parse giúp tránh trạng thái thay đổi lẫn nhau.

Khi cache formatter theo locale, key phải bao gồm các thành phần ảnh hưởng kết quả như locale, pattern, resolver style, zone (nếu có), chronology, decimal style và các lựa chọn khác tùy thiết kế. Không chỉ cache một `DateTimeFormatter` duy nhất rồi dùng cho mọi locale.

### 5.4. Ngày UI khác thời điểm máy

Chuỗi `29/02/2024` là ngày lịch theo mẫu đang nhập. Nó không tự suy ra timezone hay `Instant` tuyệt đối. Với API gửi instant nên dùng `Instant.parse` hoặc formatter ISO tương ứng đã định; với ngày sinh, `LocalDate` thường phù hợp hơn. Không biến một ngày lịch thành timestamp 00:00 UTC khi chưa có định nghĩa miền nghiệp vụ.

## 6. Quyết định về khoảng trắng, Unicode và dữ liệu bẩn

### 6.1. Trim có thể thay nghĩa input

Một số form cho phép khoảng trắng vô tình ở đầu/cuối. Nếu policy cho phép, ứng dụng có thể **chuẩn hóa có kiểm soát** rồi parse. Nhưng để kiểm tra toàn chuỗi theo input gốc, đừng lặng lẽ `trim()` trước khi kiểm tra rồi tuyên bố chuỗi ban đầu “100% hợp lệ”.

Ví dụ:

~~~text
"12.50"  -> có thể hợp lệ theo chính sách hẹp
"12.50 " -> phải bị từ chối nếu policy cấm whitespace
~~~

Nếu sản phẩm **chấp nhận** whitespace, hãy ghi rõ rule normalize. `String.trim()` chỉ xử lý một tập ký tự có phạm vi khác `String.strip()`; cả hai không tự giải quyết mọi Unicode separator hoặc non-breaking spaces.

### 6.2. Group separator có thể là ký tự không nhìn thấy rõ

Nhiều locale dùng dấu cách, non-breaking space `U+00A0`, narrow no-break space `U+202F` hoặc ký tự khác làm separator. Hai chuỗi có vẻ giống nhau nhưng chứa các code point khác nhau, dẫn đến hành vi parser khác.

Khi debug:

- In các code point (ví dụ `String.codePoints()`) thay vì chỉ nhìn glyph.
- Xác nhận locale và provider đã được chọn.
- Ghi rõ policy cho grouping, whitespace và Unicode digits.
- Tránh tự thay `U+00A0` thành ASCII space trên mọi input nếu contract không cho phép.

### 6.3. Locale không phải cơ chế bảo mật

`Accept-Language` và cài đặt ngôn ngữ người dùng **không** đáng dùng như nguồn xác minh vùng pháp lý, đơn vị tiền hoặc quyền truy cập. Dữ liệu máy như JSON number, ISO timestamp, ID và error code phải được parse theo schema cố định. Với dữ liệu tự do do người dùng nhập, cần kiểm tra độ dài, charset, giới hạn và loại trường theo business policy, không chỉ dựa vào việc formatter parse được.

## 7. Một luồng validation dễ kiểm thử

Sơ đồ:

~~~text
Raw UI input + supported Locale
               |
               v
  Chọn policy field:
  number, money, date, decimal, percent?
               |
               v
  Validate lexical input (nếu field cần cú pháp hẹp)
               |
               v
  Parse theo Locale / pattern đã chọn
               |
               v
  Xác minh full consumption hoặc dùng API full parse
               |
               v
  Validate business constraints + typed value
               |
               v
  Store BigDecimal / LocalDate / domain value
               |
               v
  Serialize machine data theo schema ổn định
~~~

Khi sai input, UI nên báo lỗi có **mã kỹ thuật và thông điệp được dịch**, không giữ nguyên một `ParseException.toString()` làm câu gửi cho người dùng. Thông tin kỹ thuật như position/errorIndex có thể hữu ích trong log/diagnostics, nhưng không nên để lộ dữ liệu nhạy cảm của input trong logs.

### 7.1. Những điều ParsePosition không tự làm

`ParsePosition` **không**:

- Xác nhận số tiền phải lớn hơn 0.
- Xác nhận một loại currency code được chấp nhận.
- Ngăn grouping không chuẩn nếu parser vẫn chấp nhận.
- Ngăn nhập nhiều chữ số thập phân hơn quy tắc business nếu parser parse được.
- Xác nhận độ lớn `BigDecimal` phù hợp giới hạn DB.
- Xác nhận định dạng năm/tháng/ngày của một trường `LocalDate`.
- Tự thay cho một parser JSON/CSV theo schema riêng.

Đó là những lớp validation khác cần thực hiện sau hoặc trước bước parse tùy đặc tính.

## 8. Chương trình Java 17 hoàn chỉnh

Chương trình minh họa:

- Parse số theo `en-US` và `de-DE` bằng `DecimalFormat` trả `BigDecimal`.
- Dùng `ParsePosition` để **từ chối ký tự thừa cuối chuỗi**.
- Chỉ ra `1,23` ở `en-US` vẫn được parser chung đọc thành 123.
- Dùng regex theo dấu decimal của locale để áp chính sách **không grouping, tối đa hai chữ số thập phân**.
- Dùng `LocalDate.parse` và `ResolverStyle.STRICT` để từ chối ngày sai và hậu tố.

**Lưu tệp `LocaleInputValidationDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class LocaleInputValidationDemo {
    static BigDecimal parseWholeDecimal(String text, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        if (!(format instanceof DecimalFormat decimal)) {
            throw new IllegalStateException(
                    "DecimalFormat provider required");
        }
        decimal.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number number = decimal.parse(text, pos);
        if (number == null || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid number, consumed=" + pos.getIndex()
                    + ", length=" + text.length()
                    + ", errorIndex=" + pos.getErrorIndex());
        }
        return (BigDecimal) number;
    }

    static BigDecimal parseMoneyNoGrouping(String text, Locale locale) {
        char decimal = DecimalFormatSymbols.getInstance(locale)
                .getDecimalSeparator();
        String rule = "[0-9]+(?:"
                + Pattern.quote(String.valueOf(decimal))
                + "[0-9]{1,2})?";
        if (!Pattern.matches(rule, text)) {
            throw new IllegalArgumentException("Invalid money syntax");
        }
        return parseWholeDecimal(text, locale);
    }

    static LocalDate parseStrictDate(String text, Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
        return LocalDate.parse(text, formatter);
    }

    public static void main(String[] args) {
        Locale en = Locale.US;
        Locale de = Locale.GERMANY;

        System.out.println("en full=" +
                parseWholeDecimal("1,234.50", en).toPlainString());
        System.out.println("de full=" +
                parseWholeDecimal("1.234,50", de).toPlainString());

        try {
            parseWholeDecimal("1,234.50oops", en);
            System.out.println("en suffix=ACCEPTED");
        } catch (IllegalArgumentException e) {
            System.out.println("en suffix=REJECTED");
        }

        System.out.println("en odd grouping parses=" +
                parseWholeDecimal("1,23", en).toPlainString());
        try {
            parseMoneyNoGrouping("1,23", en);
            System.out.println("strict en grouping=ACCEPTED");
        } catch (IllegalArgumentException e) {
            System.out.println("strict en grouping=REJECTED");
        }

        System.out.println("money en=" +
                parseMoneyNoGrouping("12.50", en).toPlainString());
        System.out.println("money de=" +
                parseMoneyNoGrouping("12,50", de).toPlainString());
        System.out.println("leap date=" +
                parseStrictDate("29/02/2024", en));

        for (String input : new String[] {
                "29/02/2023", "29/02/2024extra"
        }) {
            try {
                parseStrictDate(input, en);
                System.out.println("date " + input + "=ACCEPTED");
            } catch (DateTimeParseException e) {
                System.out.println("date " + input + "=REJECTED");
            }
        }
    }
}
~~~

**Biên dịch và chạy trên JDK 17+**:

~~~bash
javac -encoding UTF-8 LocaleInputValidationDemo.java
java LocaleInputValidationDemo
~~~

**Stdout đã xác minh bằng Java:**

~~~text
en full=1234.50
de full=1234.50
en suffix=REJECTED
en odd grouping parses=123
strict en grouping=REJECTED
money en=12.50
money de=12.50
leap date=2024-02-29
date 29/02/2023=REJECTED
date 29/02/2024extra=REJECTED
~~~

**Phân tích từng nhóm kết quả:**

1. `en full=1234.50`: chuỗi `1,234.50` theo Mỹ được parse thành giá trị thập phân `1234.50`.
2. `de full=1234.50`: chuỗi `1.234,50` theo Đức cũng biểu diễn giá trị tương đương, dù **đầu vào khác dấu**.
3. `en suffix=REJECTED`: parser chung có thể hiểu tiền tố nhưng `pos.getIndex() != text.length()`, nên validator từ chối.
4. `en odd grouping parses=123`: parser đã tiêu thụ `1,23` nhưng không xác nhận grouping nghiêm ngặt. Đây là bằng chứng full consumption chưa đủ.
5. `strict en grouping=REJECTED`: policy riêng **cấm dấu nhóm**; dấu phẩy trong input Mỹ bị từ chối trước parse.
6. `money en=12.50` và `money de=12.50`: cùng giá trị, nhưng locale Mỹ dùng dấu `.`, Đức dùng `,` ở đầu vào.
7. `leap date=2024-02-29`: ngày 29/2 của năm 2024 là hợp lệ.
8. `date 29/02/2023=REJECTED`: năm 2023 không nhuận, ResolverStyle.STRICT không tự điều chỉnh thành một ngày khác.
9. `date 29/02/2024extra=REJECTED`: `LocalDate.parse` không bỏ qua hậu tố.
10. Chương trình in kết quả dựa trên **giá trị đã parse**, không lưu nguyên chuỗi đã định dạng theo locale làm số tiền trong domain.

Đây là ví dụ học tập có chính sách regex ASCII cố ý hẹp, không phải hệ parser universal cho mọi ngôn ngữ. Nếu sản phẩm hỗ trợ chữ số bản địa hóa, dấu nhóm Ấn Độ, percent, dấu âm kế toán, currency symbol hoặc chuỗi thời gian có timezone, cần thiết kế parser riêng cho từng loại và có bộ test tương ứng.

## 9. Cách mở rộng một cách an toàn

### 9.1. Chính sách grouping nghiêm ngặt

Nếu phải cho phép dấu nhóm, đừng thay vì cho phép bất kỳ vị trí nào. Hãy xác định mẫu được hỗ trợ, ví dụ ở một trường chỉ chấp nhận grouping ba chữ số:

~~~text
en-US được phép: 1,234.50
en-US từ chối : 1,23
en-US từ chối : 12,34,567.89  (nếu policy là nhóm ba)
~~~

Những ngôn ngữ/khu vực khác có thể dùng nhóm không đồng nhất (ví dụ hàng lakh) hoặc dấu phân cách khác. Chính sách nên được quyết định trên **field contract** và tập locale được hỗ trợ, không ép regex nhóm ba cho mọi quốc gia.

Một cách triển khai là validator lexical riêng theo locale, theo sau bằng `ParsePosition` và validation kết quả. Nếu chỉ một vài locale được hỗ trợ, có thể định nghĩa trường hợp rõ, kiểm thử trên từng locale. Nếu cần tất cả locale Unicode, cân nhắc giải pháp parsing i18n chuyên dụng được kiểm chứng thay vì regex đơn giản.

### 9.2. Thêm dấu âm hoặc percent

Demo cố ý không hỗ trợ `-12.50`. Nếu domain cho phép số âm, hãy định nghĩa:

- Dấu âm ASCII hay dấu minus Unicode được chấp nhận?
- Dấu âm ở đầu, cuối hay dạng ngoặc kế toán?
- Có chấp nhận `+12.50`?
- Dải min/max và có cho phép negative zero?
- Percent `12%` có nghĩa 12 hay 0.12 trong domain?

`NumberFormat.getPercentInstance(locale)` có thể parse/format phần trăm với phép chia tỷ lệ theo quy ước của formatter. **Không** nhầm percent UI với một decimal domain chưa quy định semantics. Tách parser đúng loại field.

### 9.3. Kiểm tra scale và precision

Ngay cả khi `DecimalFormat` trả `BigDecimal`, bạn vẫn cần xem `value.scale()`, `value.precision()` và quy tắc đơn vị tiền:

~~~java
if (value.signum() < 0 || value.scale() > 2) {
    throw new IllegalArgumentException("Amount outside contract");
}
~~~

Đây là đoạn minh họa nằm trong phương thức có `BigDecimal value`. Quy tắc `scale <= 2` chỉ phù hợp nếu business thật quy định tối đa hai chữ số thập phân; một loại tiền có thể có số minor units khác. Đối với phần tiền được làm tròn, dùng `RoundingMode` rõ ràng và không tự cắt chữ số vượt chuẩn.

### 9.4. Hỗ trợ nhập ngày theo văn bản

Nếu UI cho phép tên tháng (ví dụ `29 February 2024`), dùng `DateTimeFormatter` với `Locale` và pattern phù hợp. Khi business yêu cầu chỉ định dạng `dd/MM/uuuu`, không tự cho phép `02/29/2024` chỉ vì người dùng đổi locale; pattern cũng là một phần giao kèo của field.

Để ngăn các kiểu ngày mơ hồ `03/04/2024`, tốt hơn dùng **date picker** hoặc hiển thị rõ pattern đang chờ. Không tự “phát hiện” ngày/tháng từ dữ liệu ít thông tin.

## 10. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra `parse(text) != null` | Chấp nhận tiền tố và bỏ hậu tố | Kiểm tra `ParsePosition` tới cuối |
| Chỉ kiểm tra `pos.getIndex() > 0` | Hậu tố không được kiểm tra | So với `text.length()` |
| Chỉ đọc `pos.getErrorIndex()` | Hậu tố có thể dừng mà không đặt error index | Kiểm tra cả value và consumed index |
| Tưởng full consumption = grouping chuẩn | `en-US` vẫn có thể parse `1,23` thành 123 | Thêm policy lexical |
| Parse UI bằng `Double.parseDouble` | Không hiểu decimal separator locale | Dùng parser locale phù hợp |
| Parse JSON number bằng `NumberFormat` | Thay contract máy theo locale | Dùng JSON parser chuẩn |
| Thử nhiều locale và lấy kết quả đầu tiên | Một chuỗi có thể mang hai nghĩa | Chọn locale nguồn có chủ đích |
| Dùng `double` để tính tiền | Precision có thể sai | `BigDecimal` + business policy |
| Dùng `yyyy` với `ResolverStyle.STRICT` tùy tiện | Year-of-era thiếu `ERA` | Dùng `uuuu` khi phù hợp |
| Dùng date formatter lenient | Ngày sai bị sửa thành ngày khác | ResolverStyle.STRICT |
| Nghĩ ResolverStyle thay mọi lexical rule | Dấu cách/ký tự có thể vẫn được nhận theo parser policy | Validate syntax/pattern riêng |
| `trim` input rồi báo chuỗi gốc hợp lệ | Thay input âm thầm | Quy định normalization |
| Dùng `DecimalFormat` static mutable trong thread pool | Race, sai cấu hình | Tạo per call hoặc clone có kiểm soát |
| Dùng `LocalDate` thay instant | Thiếu thông tin múi giờ | Chọn kiểu domain phù hợp |
| Đoán comma/dot không xét grouping | Có thể parse sai giá trị | Dùng locale đúng và policy rõ |
| Dùng `format(parse(s)) == s` làm chuẩn duy nhất | Từ chối cách nhập hợp lệ khác canonical output | Xây grammar và validation có mục đích |

## 11. Bộ kiểm thử và QA theo locale

Một module đầu vào đa ngôn ngữ nên có tests ở hai mức: **quy tắc parse/validation** và **hợp đồng UI/API**.

### 11.1. Ma trận số

| Locale và input | Kỳ vọng cho parser/policy của bài |
| --- | --- |
| `en-US`: `1,234.50` | Parser tổng quát thành `1234.50` |
| `de-DE`: `1.234,50` | Parser tổng quát thành `1234.50` |
| `en-US`: `1,234.50oops` | Từ chối vì chưa tiêu thụ hết |
| `en-US`: `1,23` | Parser tổng quát nhận 123; money policy từ chối |
| `en-US`: `12.50` | Money policy nhận 12.50 |
| `de-DE`: `12,50` | Money policy nhận 12.50 |
| `de-DE`: `12.50` | Money policy từ chối vì sai decimal separator theo rule hẹp |
| `en-US`: `12.50 ` | Money policy từ chối khoảng trắng cuối |
| `en-US`: `12.345` | Money policy từ chối ba chữ số thập phân |
| `en-US`: `-12.50` | Money policy từ chối dấu âm vì contract ví dụ không cho phép |

Đây là kết quả **của policy và locale đã xác định**, không phải bảng quy định Java phải xử lý tất cả chuỗi tương tự trên mọi CLDR version.

### 11.2. Ma trận ngày

- Năm nhuận: `29/02/2024` hợp lệ.
- Năm không nhuận: `29/02/2023` không hợp lệ.
- Tháng chỉ 30 ngày: `31/04/2024` không hợp lệ.
- Tháng ngoài `1..12`: từ chối.
- Hậu tố `29/02/2024extra`: từ chối.
- Leading/trailing whitespace: chính sách rõ, không chấp nhận im lặng.
- Year-of-era vs proleptic year: kiểm tra `uuuu` cho strict date.
- Locale có tên tháng hoặc non-ASCII digits: test bằng dữ liệu thực và formatter hỗ trợ.

### 11.3. Những bất biến cần giữ khi tích hợp

1. Client truyền một locale **đã được chọn từ danh sách hỗ trợ**; không parse chệch vì server default locale khác.
2. Parser chỉ chấp nhận input mà validation policy cho phép.
3. Cùng một giá trị domain có thể được nhập bằng các cách khác nhau theo locale nhưng **lưu bằng một kiểu dữ liệu máy**, không lưu chuỗi format hiển thị.
4. Không có ký tự thừa sau khi parse thành công, trừ khi một grammar chính thức cho phép chúng.
5. Mọi lỗi được thể hiện bằng error code/field path ổn định và message bản địa hóa.
6. Test concurrency không tái sử dụng `DecimalFormat` mutable bị thay đổi giữa các thread.
7. Test upgrade JDK/CLDR trên các locale thật đang hỗ trợ, không chỉ `Locale.US`.

### 11.4. Nên làm gì với invalid input?

UI nên giữ lại nguyên chuỗi người dùng để họ sửa (nếu phù hợp với bảo mật), đánh dấu field tương ứng và hiển thị **mẫu định dạng mong đợi**. Đừng tự chuẩn hóa âm thầm từ chuỗi mơ hồ `1,234` sang một giá trị khác rồi lưu mà không báo rõ.

Không ghi nguyên input thô vào logs nếu có dữ liệu nhạy cảm; khi cần debug, dùng mã lỗi parser, vị trí lỗi và metadata được kiểm soát, có thể log code points một cách đã ẩn danh cho các trường không nhạy cảm.

## 12. Bài tập thực hành

1. Tạo form nhập `amount` với hai lựa chọn locale `en-US` và `de-DE`. Đổi ngôn ngữ rồi nhập `12,50`, giải thích vì sao giá trị khác nếu dùng locale sai.
2. Bỏ điều kiện `pos.getIndex() == text.length()`, thử `1,234.50oops` và ghi lại hệ quả.
3. Giữ full consumption nhưng thử `1,23` ở `en-US`; lý giải vì sao phải thêm lexical policy.
4. Thêm lựa chọn **cho phép dấu nhóm đúng quy tắc** đối với `en-US`, so với policy không grouping ở demo.
5. Thay regex demo để chấp nhận dấu âm và một số chữ số phần thập phân khác; nêu rõ quy tắc monetary domain.
6. Viết một test cho `value.scale()`, `value.precision()`, min/max sau khi parse `BigDecimal`.
7. Thêm `31/04/2024` vào kiểm thử `LocalDate.parse` với STRICT; kiểm tra exception.
8. Thử `ResolverStyle.SMART` trên các input ngày sai rồi so với STRICT, không dùng kết quả SMART như validation cho dữ liệu pháp lý.
9. Thử `dd/MM/yyyy` với `ResolverStyle.STRICT` và giải thích vấn đề `YEAR_OF_ERA`.
10. Dùng `Locale.forLanguageTag("vi-VN")`, kiểm tra separator và format trên JDK đang dùng; không giả định luôn giống môi trường khác.
11. Viết test thay `Locale.setDefault` trong môi trường test cô lập; code truyền locale tường minh phải cho kết quả không đổi.
12. Xây một DTO API có `BigDecimal amount` và `LocalDate date`; serialize thành JSON theo schema cố định, không gửi định dạng UI.
13. Dùng parser từ `NumberFormat.getPercentInstance` trong một test riêng, giải thích scale nghĩa của kết quả.
14. Định nghĩa một kiểu lỗi `INPUT_FORMAT_INVALID` và `INPUT_OUT_OF_RANGE` có technical field path; dịch message mà không dịch code.

## 13. Tổng kết

Trong Java localization, **phân tích theo locale** phải đi cùng **kiểm tra toàn chuỗi và kiểm tra nghiệp vụ**. Đối với `NumberFormat`, dùng `ParsePosition` để xác nhận `result != null` và `position == input.length()`; nhưng đừng nhầm full consumption với nhóm số hoặc grammar nghiêm ngặt. Với `DecimalFormat` và tiền cần chính xác, bật `setParseBigDecimal(true)`, chọn locale rõ ràng, kiểm tra scale/range và tránh chia sẻ formatter mutable tùy tiện.

Đối với ngày lịch, `LocalDate.parse` cùng `DateTimeFormatter` và `ResolverStyle.STRICT` giúp từ chối ngày sai/hậu tố; dùng `uuuu` thay cho `yyyy` khi muốn năm proleptic ISO. Sau khi parse thành công, giữ dữ liệu kiểu `BigDecimal`/`LocalDate` trong domain, không lấy chuỗi hiển thị làm dữ liệu máy.

**Tài liệu tham khảo:**

- Java SE 17, `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE 17, `DecimalFormatSymbols`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html
- Java SE 17, `ParsePosition`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `ResolverStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html
- Java SE 17, `LocalDate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
