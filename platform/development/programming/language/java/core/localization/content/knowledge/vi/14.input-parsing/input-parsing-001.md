# Phân biệt format, parse và kiểm tra dữ liệu hợp lệ trong Java

## 1. Ba thao tác khác nhau trong xử lý dữ liệu theo Locale

Trong một ứng dụng đa ngôn ngữ, người dùng có thể nhìn thấy số `1,234.50` ở giao diện tiếng Anh hoặc một cách viết khác theo locale của họ. Cần phân biệt rõ ba việc thường bị gộp làm một:

1. **Format (định dạng):** chuyển một giá trị đã có kiểu và ý nghĩa thành **chuỗi để hiển thị**, theo locale, quy tắc số chữ số, currency, ngày giờ.
2. **Parse (phân tích đầu vào):** cố gắng đọc một chuỗi và tạo **giá trị có kiểu**, chẳng hạn `BigDecimal`, `LocalDate`. Parser có thể chỉ tiêu thụ phần đầu hoặc chấp nhận cú pháp mềm dẻo.
3. **Validate (kiểm tra tính hợp lệ):** xác nhận giá trị đáp ứng **quy tắc cú pháp, đầy đủ đầu vào và quy tắc nghiệp vụ**: số tiền không âm, giới hạn số chữ số thập phân, giá trị trong khoảng, ngày có thật, không có dữ liệu thừa.

**Cần nhớ: format thành công không có nghĩa chuỗi đó là dạng đầu vào duy nhất được chấp nhận; parse thành công không có nghĩa dữ liệu hợp lệ theo nghiệp vụ.**

Ví dụ đơn giản:

```text
BigDecimal(1234.50)
       |
       | FORMAT với Locale.US
       v
"1,234.50"                 -> chuỗi hiển thị
       |
       | PARSE (nếu là dữ liệu nhập)
       v
BigDecimal(1234.50)       -> giá trị được hiểu
       |
       | VALIDATE
       v
đúng cú pháp, được tiêu thụ hết, <= giới hạn, >= 0, ...
       |
       v
cho phép lưu/xử lý nghiệp vụ
```

Với dữ liệu từ API, cơ sở dữ liệu hoặc các hệ thống tích hợp, không nên đưa qua một formatter UI rồi parse ngược để “chuẩn hóa”. Hãy giữ giá trị dạng số/ngày có kiểu, chỉ dùng format ở ranh giới hiển thị.

## 2. So sánh format, parse và validate

| Chiều xử lý | Đầu vào | Đầu ra | API Java thường dùng | Không bảo đảm |
| --- | --- | --- | --- | --- |
| Format | `Number`, `BigDecimal`, `Date`, `LocalDate`... | `String` | `NumberFormat.format`, `DecimalFormat.format`, `DateTimeFormatter.format` | Đơn vị tiền tệ nghiệp vụ, tỷ giá, độ chính xác số gốc hay tính hợp lệ của dữ liệu. |
| Parse | `String` và cấu hình pattern/locale | `Number`, `BigDecimal`, `LocalDate`... hoặc lỗi | `DecimalFormat.parse`, `DateTimeFormatter.parse`, `LocalDate.parse` | Giá trị phù hợp domain, quy tắc nhập chặt, không có phần dữ liệu thừa ở mọi API. |
| Validate | Chuỗi và/hoặc giá trị đã parse, cộng chính sách | Chấp nhận/từ chối cùng lý do | `Pattern`, `ParsePosition`, kiểm tra phạm vi, `BigDecimal.compareTo`, điều kiện nghiệp vụ | Tự động dịch/định dạng dữ liệu hay phát hiện mọi quy tắc nếu không được mã hóa. |

Ba bước có thể cùng xuất hiện trong một luồng nghiệp vụ nhưng **không thay thế lẫn nhau**. Trình tự thực tế phụ thuộc domain: đôi khi cần kiểm tra toàn bộ grammar trước khi parse; với định dạng khác cần parse rồi kiểm tra số lượng ký tự đã tiêu thụ, cuối cùng validate giá trị. Trong mọi trường hợp, điều kiện chấp nhận phải được viết rõ.

### Ai chịu trách nhiệm về quy tắc?

- **Locale và formatter:** dấu phân cách, cách nhóm chữ số, thứ tự hiển thị ngày/tháng/năm, ký hiệu số và ngôn ngữ hiển thị.
- **Parser:** chuyển chữ sang dữ liệu và báo lỗi cú pháp theo quy tắc của API.
- **Application/domain:** giá trị tối thiểu/tối đa, số tiền âm có được phép không, ngày có nằm trong khoảng đặt lịch không, có cho phép phần thập phân không, ngày trong quá khứ hay tương lai, currency thực và giới hạn an toàn.
- **Boundary của hệ thống:** biết input là định dạng dành cho người dùng hay dữ liệu giao tiếp máy–máy; quyết định xử lý dấu khoảng trắng, chuẩn Unicode, số thập phân, thông báo lỗi và khả năng retry.

## 3. Format số theo locale: chỉ là chuỗi hiển thị

Ví dụ dùng `DecimalFormat` với `Locale.US`:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat formatter =
        new DecimalFormat("#,##0.00", symbols);

String view = formatter.format(new BigDecimal("1234.5"));
// "1,234.50"
```

Đây là đoạn đặt trong phương thức Java, cần import `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.util.Locale` và `java.math.BigDecimal`. Nó làm tròn/điền số 0 và dùng dấu grouping theo pattern/symbols; nó **không thay đổi** giá trị `BigDecimal("1234.5")`.

Những lưu ý quan trọng:

- `format` có thể **làm tròn** khi số nguồn nhiều chữ số hơn pattern. Chuỗi `"1.23"` có thể được tạo từ những giá trị khác nhau; không bảo toàn toàn bộ precision.
- Pattern `"#,##0.00"` dùng ký hiệu cú pháp chuẩn; dấu thập phân, grouping hiển thị được quyết định bởi `DecimalFormatSymbols`.
- `DecimalFormat` không tự xác nhận số tiền có âm hay không, tỷ giá tiền tệ hay hạn mức giao dịch.
- Nếu muốn in số theo locale cho người dùng, dùng locale tường minh. Không thay `Locale.setDefault(...)` cho từng request; đó là trạng thái chung của JVM.
- Không dùng `format` để tạo chuỗi lưu số tiền vào database, khóa định danh hay giá trị JSON mang tính chuẩn tắc. Dữ liệu giao tiếp máy nên có schema riêng, ví dụ một số thập phân ở dạng bất biến ngôn ngữ.

## 4. Parse số: có thể mềm dẻo hơn mong đợi

`DecimalFormat.parse(String)` có thể trả một `Number` nếu đọc được phần hợp lệ ở đầu chuỗi. Một số parser không bắt buộc tự kiểm tra đã tiêu thụ hết input. Vì vậy, cú pháp được parse thành công **chưa chắc hợp lệ theo yêu cầu màn hình nhập**.

Ví dụ giả sử parser theo `Locale.US` và pattern `"#,##0.00"`:

```text
"1,234.50"       -> đọc thành 1234.50
"1,234.50abc"    -> có thể đọc được 1234.50 rồi dừng trước "abc"
"12,34.50"       -> có thể đọc thành 1234.50, dù nhóm chữ số sai quy ước UI
```

Hai chuỗi cuối không nên mặc nhiên được coi là hợp lệ nếu form yêu cầu định dạng grouping chuẩn và cấm ký tự thừa.

### Dùng ParsePosition để kiểm tra tiêu thụ hết

`java.text.ParsePosition` cho phép biết parser dừng ở ký tự nào:

```java
ParsePosition pos = new ParsePosition(0);
Number parsed = parser.parse(input, pos);

boolean completelyParsed =
        parsed != null && pos.getIndex() == input.length();
```

Đây là đoạn Java minh họa trong phương thức với biến `parser` và `input` đã được tạo, không phải chương trình độc lập.

- `parsed == null` có nghĩa không đọc ra giá trị.
- `pos.getIndex() == input.length()` chứng tỏ parser đã tiêu thụ hết chuỗi đầu vào.
- Nhưng **tiêu thụ hết chưa đủ**: ví dụ `"12,34.50"` có thể được `DecimalFormat` đọc trọn mà vẫn vi phạm chính sách nhóm 3 chữ số của form. Cần kiểm tra grammar chặt hơn khi yêu cầu UI đặt ra điều đó.
- `ParsePosition.getErrorIndex()` có thể hỗ trợ chẩn đoán vị trí lỗi; không dùng duy nhất error index để kết luận giá trị hợp lệ, vì điều kiện tiêu thụ hết và domain vẫn quan trọng.

Với những trường hợp parse trả giá trị nhưng còn đuôi, parser có thể trả số mà không ném `ParseException`. Đừng dùng một lời gọi `parse` thành công làm bằng chứng nhận đủ dữ liệu.

### Vì sao cần BigDecimal khi nhận số thập phân chính xác?

`DecimalFormat` có thể được cấu hình:

```java
DecimalFormat parser = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
parser.setParseBigDecimal(true);
```

Với chế độ này, giá trị số thông thường do `parse` trả về có thể được xử lý như `BigDecimal`, tránh sai số nhị phân của `double` trong nghiệp vụ tiền tệ. Tuy nhiên, phải cân nhắc giá trị đặc biệt như NaN/infinity và các điều kiện parse riêng; không ép kiểu tùy tiện sau khi nhận input ngoài domain. Việc dùng BigDecimal **không tự xác nhận** số có tối đa hai chữ số thập phân hay nằm trong hạn mức cho phép.

## 5. Validate gồm ít nhất ba lớp

Một màn hình nhập số tiền có thể yêu cầu: định dạng `Locale.US`, số không âm, tối đa hai chữ số sau dấu thập phân, giới hạn `10,000.00` và không có nội dung thừa. Khi đó cần ba lớp kiểm tra:

1. **Grammar (lexical/syntax):** chuỗi có đúng dạng được phép không? Ví dụ cấm khoảng trắng bất ngờ, cấm số có nhóm chữ số `"12,34"`, cấm nhiều hơn hai chữ số thập phân, không cho chữ cái.
2. **Conversion/parsing:** có đọc được thành số chính xác không, parser có tiêu thụ hết input và không tạo giá trị đặc biệt không?
3. **Domain/semantic:** giá trị có nằm trong khoảng `[0,10000]` không, có quy tắc làm tròn, hạn mức, scale, đơn vị tiền tệ hoặc điều kiện riêng không?

Ví dụ bảng phân loại:

| Input | Ý nghĩa | Kết quả chính sách minh họa |
| --- | --- | --- |
| `1,234.50` | Đúng grouping, hai chữ số thập phân | Hợp lệ; số `1234.50` |
| `10.00` | Không grouping, hai chữ số thập phân | Hợp lệ |
| `1,234.50abc` | Có đuôi chữ cái | Không hợp lệ về grammar |
| `12,34.50` | Grouping sai | Không hợp lệ về grammar |
| `5.555` | Ba chữ số thập phân | Không hợp lệ về grammar |
| `-2.00` | Số âm | Đọc được nhưng không hợp lệ về domain |
| `10,000.01` | Vượt giới hạn `10,000.00` | Không hợp lệ về domain |
| `abc` | Không phải số | Không hợp lệ về grammar / parse |

Regex có thể diễn đạt một grammar cố định của giao diện, nhưng **không được áp regex theo US lên mọi locale**. Ở locale dùng dấu phẩy thập phân hoặc khoảng trắng grouping, grammar phải được thiết kế cho quy tắc được sản phẩm chấp nhận. Một số địa phương dùng dấu cách không ngắt (NBSP) hay khoảng trắng hẹp (narrow NBSP); không nên thay tất cả bằng dấu cách ASCII mà không xác định yêu cầu.

### Chọn chính sách về khoảng trắng

Một quyết định thực tế cần ghi rõ là có cho phép `" 1,234.50 "` không. Nếu có, hãy định nghĩa việc loại bỏ ký tự nào, ở đâu, và thông báo cho người dùng. `String.trim()` không xử lý tất cả Unicode whitespace. Việc `strip()` có tác dụng với nhiều ký tự hơn cũng không có nghĩa nó xử lý đúng mọi loại khoảng trắng trong định dạng số ở mọi ngôn ngữ. Với tiền tệ và dữ liệu nhạy cảm, chuẩn hóa tùy tiện có thể che khuất input không đúng.

### Không nhầm validation với sanitizer

Sanitization/normalization có thể giúp xử lý khác biệt Unicode hoặc ký tự vô hại, nhưng nó **không thay validation**. Đặc biệt, không nên chỉ xóa dấu phân cách, chữ cái, ký hiệu tiền tệ hay dấu trừ rồi parse phần còn lại: điều này có thể biến dữ liệu nhập sai thành một giá trị khác mà người dùng không hề xác nhận.

## 6. Ví dụ Java 17+ chạy độc lập: format, parse, validate

Tạo tệp **`LocalizedInputDemo.java`** dưới đây. Ví dụ cố định `Locale.US` cho số tiền, dùng `BigDecimal`, `ParsePosition` và grammar rõ ràng. Phần ngày dùng `DateTimeFormatter` ở chế độ strict để phân biệt đọc một ngày thực sự với việc “sửa” ngày không tồn tại.

Giả định nghiệp vụ **chỉ dành cho ví dụ**: nhận số có dấu trừ tùy chọn trong grammar để chứng minh parse khác domain; sau parse chỉ chấp nhận số **không mang dấu âm**, có tối đa hai chữ số thập phân và không vượt `10000.00`. Nếu dấu âm xuất hiện ngay cả với `-0.00`, nó cũng bị từ chối bởi chính sách không chấp nhận dấu âm. Quy ước nhóm chữ số: không nhóm hoặc nhóm đúng ba chữ số theo `Locale.US`.

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class LocalizedInputDemo {

    private static final BigDecimal MAX =
            new BigDecimal("10000.00");

    // Cú pháp chấp nhận của form mẫu, không phải grammar
    // chung của mọi Locale.
    private static final Pattern US_AMOUNT = Pattern.compile(
            "-?(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}"
            + "(?:,[0-9]{3})+)(?:\\.[0-9]{1,2})?");

    private static DecimalFormat createParser() {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        parser.setParseBigDecimal(true);
        return parser;
    }

    private static void checkAmount(String input,
                                    DecimalFormat parser) {
        if (!US_AMOUNT.matcher(input).matches()) {
            System.out.println(input + " -> INVALID_GRAMMAR");
            return;
        }

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);
        if (!(parsed instanceof BigDecimal amount)
                || position.getIndex() != input.length()) {
            System.out.println(input + " -> PARSE_ERROR");
            return;
        }

        if (input.startsWith("-") || amount.signum() < 0
                || amount.compareTo(MAX) > 0) {
            System.out.println(input + " -> DOMAIN_ERROR");
            return;
        }

        System.out.println(input + " -> OK:"
                + amount.toPlainString());
    }

    private static void showPermissiveParse(String input,
                                            DecimalFormat parser) {
        ParsePosition position = new ParsePosition(0);
        Number number = parser.parse(input, position);
        System.out.println("lenient=" + input + " -> " + number
                + "; consumed=" + position.getIndex()
                + "/" + input.length());
    }

    private static void checkDate(String input,
                                  DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(input, formatter);
            System.out.println("date=" + input + " -> " + date);
        } catch (DateTimeParseException ex) {
            System.out.println("date=" + input + " -> INVALID_DATE");
        }
    }

    public static void main(String[] args) {
        DecimalFormat parser = createParser();
        System.out.println("format="
                + parser.format(new BigDecimal("1234.5")));

        showPermissiveParse("12,34.50", parser);
        showPermissiveParse("1,234.50abc", parser);

        String[] amounts = {
                "1,234.50", "1,234.50abc",
                "12,34.50", "-2.00",
                "5.555", "abc", "10.00",
                "10,000.01"
        };
        for (String input : amounts) {
            checkAmount(input, parser);
        }

        DateTimeFormatter dates = DateTimeFormatter
                .ofPattern("dd/MM/uuuu",
                        Locale.forLanguageTag("vi-VN"))
                .withResolverStyle(ResolverStyle.STRICT);

        for (String input : new String[] {
                "29/02/2024", "31/02/2024", "29/02/2023"
        }) {
            checkDate(input, dates);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ tại thư mục chứa file:

```bash
javac -encoding UTF-8 LocalizedInputDemo.java
java LocalizedInputDemo
```

**Stdout đúng với cấu hình trong ví dụ:**

```text
format=1,234.50
lenient=12,34.50 -> 1234.50; consumed=8/8
lenient=1,234.50abc -> 1234.50; consumed=8/11
1,234.50 -> OK:1234.50
1,234.50abc -> INVALID_GRAMMAR
12,34.50 -> INVALID_GRAMMAR
-2.00 -> DOMAIN_ERROR
5.555 -> INVALID_GRAMMAR
abc -> INVALID_GRAMMAR
10.00 -> OK:10.00
10,000.01 -> DOMAIN_ERROR
date=29/02/2024 -> 2024-02-29
date=31/02/2024 -> INVALID_DATE
date=29/02/2023 -> INVALID_DATE
```

### Phân tích ba loại kết quả

**Format:** `new BigDecimal("1234.5")` được định dạng thành `1,234.50`, thêm dấu nhóm và chữ số thập phân theo pattern. Dữ liệu gốc vẫn là một `BigDecimal`.

**Parse:** hai dòng `lenient` cho thấy parser có thể tiêu thụ toàn bộ cú pháp grouping mà form không chấp nhận hoặc dừng trước chuỗi đuôi. Đây là hành vi của việc chuyển đổi mềm dẻo, không phải kết luận validation.

**Validate:** quy tắc regex loại input không đúng grammar; `ParsePosition` cùng kiểm tra kiểu loại sự cố parse/tiêu thụ; `BigDecimal.compareTo` và quy tắc dấu xử lý domain. `10,000.01` là số hợp cú pháp nhưng vượt hạn mức.

**Ngày:** `29/02/2024` là ngày nhuận hợp lệ. `31/02/2024` và `29/02/2023` không tồn tại nên bị từ chối bởi `ResolverStyle.STRICT`. Đặc biệt, pattern dùng `uuuu` (proleptic year) thay vì `yyyy` (year-of-era), tránh một bẫy phổ biến với strict resolver khi không cung cấp era.

Ví dụ cố ý không tự đổi locale mặc định JVM và không sửa file dự án. Nếu sản phẩm cần nhiều locale, hãy tạo grammar tương ứng từng locale thay vì dùng thẳng regex của `Locale.US` cho tất cả.

## 7. Date/time: parse được phải là ngày hợp lệ

Đối với ngày giờ, hai API thường gặp là:

- `java.text.SimpleDateFormat`: API cũ, mutable, có cấu hình lenient; cần chủ động gọi `setLenient(false)` khi muốn parse lịch nghiêm ngặt và kiểm tra tiêu thụ hết chuỗi.
- `java.time.format.DateTimeFormatter` (Java 8+): API hiện đại, immutable, có thể dùng `ResolverStyle.STRICT`, locale và pattern tường minh.

Ví dụ:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"))
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("29/02/2024", formatter);
// 2024-02-29
```

Đoạn trên nằm trong phương thức Java, không phải chương trình hoàn chỉnh; ví dụ runnable đã có ở mục 6.

Với `DateTimeFormatter`, phân biệt **định dạng chữ** và **giá trị ngày**:

- `format(LocalDate)` trả chuỗi hiển thị theo mẫu và locale.
- `LocalDate.parse(...)` tạo ngày có kiểu, có thể ném `DateTimeParseException` khi chuỗi không phù hợp hoặc ngày không tồn tại.
- Validation nghiệp vụ còn kiểm tra ngày có nằm trong khoảng được phép không; ví dụ ngày đặt hàng có được trong quá khứ không, lịch có giới hạn 90 ngày không, ngày sinh có hợp lệ theo chính sách không.
- `LocalDate` không đại diện thời điểm theo múi giờ. Đối với giờ đặt lịch/hẹn, cần quy định `ZoneId` và xem xét chuyển giờ mùa hè hoặc giờ không tồn tại/lặp lại tại địa phương.

### Các bẫy ở API ngày cũ

`SimpleDateFormat` có thể “sửa” một ngày không tồn tại thành ngày khác khi lenient. Nếu cần xác thực đúng input, đặt `setLenient(false)` và không bỏ qua hậu tố thừa. `DateFormat.parse(String)` không thay thế việc validate ngày trong domain. Ngoài ra, pattern của `SimpleDateFormat` và `DateTimeFormatter` có những khác biệt, đặc biệt quanh `y`/`u`, tuần trong năm và timezone; đừng chuyển pattern giữa API mà không kiểm thử.

## 8. Kiểm tra dữ liệu hợp lệ theo ngữ cảnh nghiệp vụ

### 8.1. Number không phải Money

Một input `1234.50` không tự biết đó là USD, VND, EUR hay một đại lượng khác. Nếu hệ thống quản lý tiền, hãy lưu **số tiền và mã currency riêng**, rồi validate currency thuộc danh sách cho phép. `NumberFormat.getCurrencyInstance(locale)` giúp hiển thị, nhưng không xác minh tỷ giá hoặc đơn vị giao dịch.

Một số lượng sản phẩm có thể phải là số nguyên; số tiền có thể cho hai chữ số lẻ; khối lượng có thể cho ba chữ số; lãi suất có thể cho nhiều chữ số hơn. Không áp dụng một regex/scale cho mọi nghiệp vụ.

### 8.2. Giá trị nguyên, phần lẻ và precision

Một số `BigDecimal` có hai khái niệm quan trọng:

- **Giá trị:** kiểm tra bằng `compareTo(...)` khi xác định lớn hơn/nhỏ hơn.
- **Scale:** số chữ số bên phải dấu thập phân trong biểu diễn BigDecimal, có thể dùng cho chính sách giới hạn precision, nhưng cần xác định có chấp nhận số 0 vô nghĩa ở cuối hay không.

Ví dụ `1.0` và `1.00` có giá trị số học bằng nhau khi dùng `compareTo` nhưng khác `scale()` và khác về hình thức nhập. Nếu hợp đồng yêu cầu chính xác tối đa hai chữ số thập phân, bạn có thể kiểm soát hình thức trước parse và kiểm tra scale sau parse. Không coi `BigDecimal.equals` như kiểm tra bằng nhau về giá trị số học trong mọi hoàn cảnh, vì nó còn xét scale.

### 8.3. Chữ số và ký tự Unicode

Người dùng có thể nhập chữ số ASCII, chữ số của hệ viết khác, dấu âm Unicode hoặc dấu cách đặc biệt. Parser và regex có thể xử lý chúng khác nhau; không giả định `[0-9]` khớp mọi chữ số Unicode hoặc `\\d` luôn có cùng nghĩa ở mọi cấu hình regex. Khi cần hỗ trợ chữ số địa phương, hãy dựa trên yêu cầu sản phẩm, `Locale` và các parser/normalizer phù hợp, đồng thời có bộ test riêng.

Các trường nhập số có giá trị quan trọng không nên âm thầm loại bỏ ký tự lạ. Nếu cho phép quy đổi chữ số sang dạng chuẩn, phải làm theo quy tắc được thiết kế rõ và lưu dấu vết khi cần.

### 8.4. Giới hạn độ dài, tài nguyên và độ lớn

Validation không chỉ là dấu phân cách và khoảng số. Một input số dài hàng triệu ký tự có thể làm parser hoặc code xử lý nặng. Đặt giới hạn độ dài, độ chính xác và độ lớn hợp lý **trước** khi thực hiện các thao tác tốn tài nguyên. Trên API server, kết hợp giới hạn payload và kiểm soát lỗi để chống nhập dữ liệu bất thường.

### 8.5. Chia nhỏ kiểm tra để báo lỗi đúng

Thay vì một thông báo `"Invalid input"` cho mọi thứ, bạn có thể phân loại:

- `INVALID_GRAMMAR`: ký tự, grouping, decimal digits hoặc cú pháp không được phép.
- `PARSE_ERROR`: không thể chuyển thành giá trị có kiểu hoặc còn hậu tố không đọc.
- `DOMAIN_ERROR`: số/giá trị đã đọc không thỏa hạn mức, dấu, đơn vị hoặc điều kiện nghiệp vụ.

Các nhãn này trong demo là nhãn kỹ thuật. Giao diện người dùng nên dịch thành thông báo ngắn, hữu ích theo locale của sản phẩm. Không đưa nội dung exception kỹ thuật thô hoặc stack trace trực tiếp cho người dùng cuối.

## 9. Khi nào nên dùng API nào?

| Tình huống | Khuyến nghị |
| --- | --- |
| Hiển thị số theo ngôn ngữ người dùng | `NumberFormat` hoặc `DecimalFormat` với `Locale` rõ ràng. |
| Hiển thị ngày giờ | `DateTimeFormatter`, `Locale` và `ZoneId` đúng ngữ cảnh. |
| Parse số từ form locale-specific | `DecimalFormat`/`NumberFormat` thích hợp, kiểm tra `ParsePosition` và quy tắc grammar của form. |
| Parse chuỗi tiền chính xác | Xử lý thành `BigDecimal` và validate scale, range, currency; không tự đưa qua `double`. |
| Parse ngày từ input có pattern cố định | `LocalDate.parse` với `DateTimeFormatter` và `ResolverStyle.STRICT`. |
| Nhận số từ JSON API | Sử dụng schema số/decimal thống nhất không phụ thuộc locale UI; không áp regex US cho mọi quốc gia. |
| Nhập liệu ở dạng đã chuẩn hóa | Parse theo dạng chuẩn đã quy định, thay vì tự đoán locale từ từng chuỗi. |
| Kiểm tra số tiền không âm, giới hạn 10.000 | Domain validation sau khi xác định giá trị; không kỳ vọng formatter thực hiện. |
| Báo lỗi input cho người dùng | Mã lỗi có cấu trúc, thông điệp bản địa hóa qua `ResourceBundle`/cơ chế dịch. |

### Parse và regex: không phải lựa chọn một trong hai

Một regex tốt có thể kiểm tra **hình thức nhập cụ thể**; parser hiểu các quy tắc số/locale, tạo dữ liệu có kiểu và thông báo trạng thái. Tuy nhiên:

- Regex cho cả thế giới dễ trở nên quá phức tạp và bỏ sót ký tự hợp lệ.
- Parser có thể quá rộng so với chính sách màn hình nhập.
- Cả hai vẫn cần kiểm tra phạm vi nghiệp vụ.

Với dữ liệu locale đa dạng, có thể chọn một component nhập liệu được kiểm thử cho từng thị trường và dùng API chuẩn hóa đầu vào đã được thiết kế. Tránh tạo regex chung từ giả định “mọi ngôn ngữ đều dùng dấu phẩy để nhóm nghìn”.

## 10. Tính bất biến, concurrency và đối tượng dùng chung

`DecimalFormat` và `SimpleDateFormat` là **mutable** và không bảo đảm an toàn khi chia sẻ tùy tiện giữa nhiều thread. Không để một `static DecimalFormat` rồi thay `Locale`, pattern hoặc suffix theo mỗi request. Dùng formatter mới cho từng lần xử lý, clone một template hoặc đồng bộ hóa đúng phạm vi.

`DateTimeFormatter` của `java.time` là immutable và thường phù hợp để dùng lại giữa thread khi cấu hình đã cố định. Việc dùng lại một formatter không biến input chưa xác thực thành an toàn; vẫn phải validate ngày theo domain.

Môi trường đa luồng cũng không nên thay `Locale.setDefault(...)` để parse theo từng request; setter làm đổi trạng thái toàn JVM, có thể ảnh hưởng người dùng khác. Truyền `Locale` rõ ràng vào parser/formatter.

## 11. Lỗi phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| `format(parse(text))` rồi so chuỗi bằng nhau là validation duy nhất | Formatter có thể đổi grouping, precision, không bảo toàn hình thức nhập hợp lệ khác. | Thiết kế grammar, parse đầy đủ, domain validation. |
| Tin `DecimalFormat.parse` luôn tiêu thụ hết input | Có thể đọc prefix rồi bỏ qua đuôi. | Dùng `ParsePosition` và so với độ dài toàn chuỗi. |
| Tin parser luôn kiểm tra grouping chặt | Có thể nhận `12,34.50` là 1234.50. | Xác thực grouping theo policy của form. |
| Xóa dấu phẩy, dấu âm và ký tự lạ trước parse | Dữ liệu sai có thể biến thành số khác. | Chuẩn hóa có quy tắc, sau đó validate. |
| Dùng `double` cho tiền và so sánh bằng chính xác tuyệt đối | Sai số nhị phân dễ gây lỗi làm tròn/so sánh. | `BigDecimal` và chính sách rounding/scale. |
| Dùng regex của Locale.US cho chuỗi mọi locale | Thập phân/grouping, chữ số, whitespace khác nhau. | Chọn parser/grammar theo locale thực tế. |
| Tin `parse("31/02/2024")` luôn bị từ chối | Một số parser lịch lenient có thể tự điều chỉnh ngày. | Dùng `ResolverStyle.STRICT` hoặc tắt lenient. |
| Dùng `yyyy` mà không hiểu year-of-era khi strict | Parse ngày có thể thất bại vì thiếu era. | Dùng `uuuu` khi pattern yêu cầu proleptic year. |
| Chỉ validate regex và bỏ qua limit | `999999...` có thể đúng hình thức nhưng ngoài domain. | Giới hạn độ dài, phạm vi, precision và đơn vị. |
| Coi format tiền là đổi tỷ giá | Chỉ thay biểu diễn. | Tách logic currency/FX khỏi định dạng UI. |
| Dùng chung mutable parser đa luồng | Race condition, kết quả không ổn định. | Tạo parser theo request/đồng bộ hóa. |
| Hiển thị thông điệp exception thô | Gây khó hiểu, có thể lộ thông tin kỹ thuật. | Ánh xạ mã lỗi sang bản dịch phù hợp. |

## 12. Kiểm thử đầu vào: positive, negative và boundary

Một bộ test đủ mạnh cần kiểm thử **từng lớp**. Với form số tiền trong demo:

| Nhóm | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ cơ bản | `0`, `10.00`, `1,234.50` | Chấp nhận. |
| Grouping sai | `1,23`, `12,34.50` | Reject về grammar. |
| Ký tự thừa | `1,234.50abc`, `10.00 USD` | Reject nếu policy không cho suffix. |
| Số âm | `-2.00`, `-0.00` | Reject theo chính sách không chấp nhận dấu âm. |
| Quá nhiều phần lẻ | `5.555` | Reject về grammar/precision. |
| Hạn mức | `10,000.00`, `10,000.01` | Chấp nhận giới hạn, từ chối lớn hơn. |
| Ký tự Unicode | Chữ số ngoài ASCII, NBSP, dấu trừ Unicode | Chấp nhận/từ chối theo chính sách đã tài liệu hóa. |
| Null/empty | `null`, `""`, chuỗi chỉ khoảng trắng | Có kết quả kiểm tra rõ, không ném lỗi ngoài dự kiến. |
| Độ dài lớn | Chuỗi vài chục nghìn chữ số | Reject sớm trước parse nặng. |
| Lịch | `29/02/2024`, `29/02/2023`, `31/02/2024` | Chỉ ngày có thật được parse. |

Lưu ý: demo dùng `Pattern.matcher(input)` và kỳ vọng `input` không null. Trong một form hoặc API thực tế phải kiểm tra null và giới hạn độ dài **trước khi gọi matcher**.

### Test độc lập locale mặc định

Trên máy khác, `Locale.getDefault()` có thể là `vi-VN`, `en-US` hay locale khác. Không viết test giả định mặc định toàn JVM luôn như máy của lập trình viên. Trong unit test, truyền `Locale` tường minh, chọn `ZoneId` cố định nếu cần, và test các chuỗi đã được thiết kế theo chính locale đó.

## 13. Bài tập thực hành

**Bài 1 — Phân biệt ba giai đoạn:** lấy giá trị `BigDecimal("1234.567")`, format bằng `DecimalFormat("#,##0.00", Locale.US symbols)`, rồi parse chuỗi hiển thị. So sánh giá trị gốc với giá trị parse lại. Giải thích tại sao pipeline format → parse không bảo toàn precision.

**Bài 2 — Sửa lỗ hổng trailing input:** gọi `DecimalFormat.parse` cho `"123abc"`, ghi kết quả `Number` và chỉ số của `ParsePosition`. Viết kiểm tra từ chối nếu parser chưa đọc hết chuỗi, thay vì chỉ kiểm tra kết quả không null.

**Bài 3 — Grouping theo form:** mở rộng grammar chấp nhận số âm trong màn hình khác; test `12,345.67`, `12,34.67`, `-0.00` và chuỗi chứa dấu phân cách Unicode. Ghi rõ chính sách nào là cú pháp, chính sách nào là domain.

**Bài 4 — Ngày không tồn tại:** so sánh `SimpleDateFormat` lenient với `DateTimeFormatter` strict cho `"31/02/2024"`. Sau đó thêm validation từ chối ngày quá khứ trong tính năng đặt lịch. Thấy rõ **parse đúng ngày** và **được phép đặt lịch** là hai câu hỏi khác nhau.

**Bài 5 — Đa locale:** thiết kế form nhập số lượng hoặc tiền theo `Locale.US` và `Locale.forLanguageTag("vi-VN")`. Chọn policy về grouping, dấu thập phân, ký tự Unicode và phản hồi lỗi. Chạy test trên CI với locale mặc định JVM khác nhau, nhưng luôn cấu hình parser/formatter tường minh.

**Bài 6 — Validation domain:** yêu cầu giá trị từ `0` tới `10000`, tối đa hai chữ số phần lẻ, không mang dấu âm, currency `USD`. Thiết kế DTO có amount và currency riêng. Test trường hợp đủ điều kiện cú pháp nhưng sai hạn mức/currency, và trường hợp đúng amount nhưng đầu vào chưa được parse hết.

## 14. Checklist và kết luận

- [ ] Nói đúng chiều đi của **format** (giá trị có kiểu → chuỗi) và **parse** (chuỗi → giá trị có kiểu).
- [ ] Biết tại sao parse thành công không tự động có nghĩa toàn bộ input đã được đọc hoặc cấu trúc grouping hợp lệ.
- [ ] Dùng `ParsePosition` khi cần phát hiện chuỗi thừa ở cuối và xử lý null/exception phù hợp.
- [ ] Phân biệt kiểm tra grammar, kiểm tra conversion và kiểm tra domain; kiểm soát giới hạn độ dài trước parse.
- [ ] Với số tiền/thập phân, hiểu lý do dùng `BigDecimal`, kiểm tra range/scale và quản lý currency riêng.
- [ ] Với ngày tháng, biết cách yêu cầu parse strict, tránh tự sửa ngày không tồn tại và thêm điều kiện nghiệp vụ.
- [ ] Không phụ thuộc locale/timezone mặc định toàn JVM, không dùng chung mutable formatter/parser không an toàn.
- [ ] Có test cho input hợp lệ, sai cú pháp, âm 0, ký tự Unicode, input thừa, boundary và miền giá trị.

**Quy tắc cốt lõi:** **format để trình bày, parse để hiểu dữ liệu, validate để quyết định có được chấp nhận hay không.** Ba thao tác có mục đích khác nhau; cách làm đúng là định nghĩa rõ input contract rồi kiểm tra đầy đủ trước khi dùng giá trị vào logic nghiệp vụ.
