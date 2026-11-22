# Quy ước máy đọc được cho tệp, API và dữ liệu lưu trữ trong Java

Ứng dụng bản địa hóa cần xử lý **hai thế giới khác nhau**: văn bản người dùng đọc/nhập theo `Locale`, và dữ liệu máy móc truyền/lưu với một **hợp đồng định dạng ổn định**. Một người dùng ở Đức có thể nhập `1.234,50`; một người dùng tại Hoa Kỳ nhìn thấy `1,234.50`. Tuy nhiên, API, tệp trao đổi và bản ghi lưu trữ không nên phụ thuộc vào `Locale.getDefault()` của máy đang chạy để quyết định số đó là bao nhiêu.

**Nguyên tắc:** *Giao diện bản địa hóa dữ liệu cho người dùng; ranh giới trao đổi và lưu trữ phải dùng kiểu dữ liệu, mã hóa, cú pháp và quy tắc kiểm tra đã được định nghĩa rõ.* Với Java 17+, điều này thường có nghĩa: số thập phân dùng `BigDecimal` và biểu diễn decimal theo hợp đồng; ngày thuần dùng ISO `yyyy-MM-dd`; thời điểm dùng `Instant` ở UTC hoặc chuỗi có offset rõ ràng; locale dùng thẻ BCP 47 như `vi-VN`; nội dung tệp/API dùng UTF-8 và parser phù hợp với định dạng.

Bài học tập trung **quy ước máy đọc được**: cách tạo, đọc, xác thực và chuyển đổi dữ liệu an toàn ở các ranh giới *file → ứng dụng → API → database*, không phải cách dịch nhãn giao diện.

## 1. Vì sao không được dùng định dạng hiển thị làm định dạng truyền/lưu?

Xét cùng giá trị số một nghìn hai trăm ba mươi tư phẩy năm:

| Ngữ cảnh | Biểu diễn minh họa | Tính chất |
| --- | --- | --- |
| UI `en-US` | `1,234.50` | Dấu phẩy phân nhóm, dấu chấm thập phân |
| UI `de-DE` | `1.234,50` | Dấu chấm phân nhóm, dấu phẩy thập phân |
| UI `vi-VN` | Có thể dùng ký hiệu phân nhóm/thập phân theo dữ liệu locale của JDK | Kết quả phụ thuộc locale/provider |
| Dữ liệu decimal dạng text theo hợp đồng đề xuất | `1234.50` | Không grouping, dấu chấm ASCII, chữ số rõ ràng |
| Database cột DECIMAL/NUMERIC | Giá trị decimal có kiểu | Không phải chuỗi được format cho một locale |
| JSON number | `1234.50` | Cú pháp số của JSON; độ chính xác phụ thuộc bên tiêu thụ |
| JSON string mang decimal chính xác | `"1234.50"` | Cần hợp đồng nói rõ phải parse thành decimal |

Nếu ghi trực tiếp chuỗi `1.234,50` vào một tệp CSV rồi để dịch vụ khác gọi `Double.parseDouble`, việc phân tích thất bại hoặc bị diễn giải sai. Nếu dùng `NumberFormat.getInstance()` không truyền locale tại server, kết quả còn phụ thuộc cấu hình của máy chạy.

### Hai trục cần tách

1. **Ý nghĩa dữ liệu:** decimal tiền tệ, tỷ lệ, số đếm, ngày trên lịch, timestamp, mã locale, mã khách hàng.
2. **Cách biểu diễn ở ranh giới:** JSON number hay string, chuỗi ISO, cột SQL kiểu `DECIMAL`, byte UTF-8, dấu phân cách CSV, timezone, quy ước null.

Một `Locale` chỉ hỗ trợ cách gọi tên/định dạng/đọc theo vùng; nó **không tự định nghĩa** toàn bộ giao thức trao đổi hoặc lược đồ lưu trữ. Hãy bắt đầu bằng **hợp đồng dữ liệu** thay vì bắt đầu bằng `NumberFormat`.

## 2. Chọn kiểu trong mô hình nội bộ trước khi chọn chuỗi ngoài

Java có kiểu thích hợp cho các khái niệm thông dụng:

| Ý nghĩa | Kiểu Java nên cân nhắc | Biểu diễn trao đổi thường dùng |
| --- | --- | --- |
| Số lượng nguyên | `int`, `long`, `BigInteger` tùy phạm vi | JSON integer, cột integer, chuỗi chữ số nếu cần |
| Decimal chính xác, tiền | `BigDecimal` | JSON string decimal có hợp đồng hoặc JSON number có giới hạn tương thích |
| Số đo xấp xỉ | `double` | JSON number hữu hạn với quy ước sai số/độ chính xác rõ |
| Ngày không kèm giờ | `LocalDate` | `2026-10-28` (ISO calendar date) |
| Giờ không kèm ngày, vùng | `LocalTime` | `14:30:00` theo quy tắc đã thống nhất |
| Thời điểm tuyệt đối | `Instant` | `2026-10-28T03:30:00Z` |
| Thời gian với offset | `OffsetDateTime` | `2026-10-28T10:30:00+07:00` |
| Giờ địa phương + vùng | `ZonedDateTime` hoặc cặp `LocalDateTime` và `ZoneId` | Truyền cả local time, zone ID và chính sách DST nếu ý nghĩa nghiệp vụ cần |
| Ngôn ngữ/vùng người dùng | `Locale` | BCP 47, ví dụ `en-US` |
| Mã định danh có số 0 đầu | `String` | `"001234"`, không ép sang số |

**Không chọn `double` cho mọi giá trị chỉ vì API nhận số.** Decimal tài chính có thể cần độ chính xác thập phân và quy tắc làm tròn có thể kiểm toán. **Không chọn `Date`/`Instant` cho một ngày sinh** nếu ý nghĩa chỉ là ngày trên lịch: chuyển ngày sang timestamp có thể gây đổi ngày khi dịch múi giờ.

Kiểu trong bộ nhớ và kiểu khi trao đổi phải có **ánh xạ rõ ràng**, không dựa vào `toString()` của một đối tượng tùy ý như một hợp đồng vĩnh viễn.

## 3. Số thập phân máy đọc: không có grouping, dấu chấm được quy định

Với một trường decimal do ứng dụng tự định nghĩa dưới dạng chuỗi, hợp đồng đơn giản có thể yêu cầu:

- Chỉ dùng các chữ số ASCII `0–9`; dấu trừ ASCII `-` nếu cho phép số âm.
- Dấu thập phân **`.`**, không phải dấu phẩy.
- Không ký hiệu phân nhóm như `,`, khoảng trắng, dấu chấm nhóm, dấu phân cách theo locale.
- Không ký hiệu tiền tệ, phần trăm, khoảng trắng tùy ý, `NaN` hoặc `Infinity`.
- Phải xác định có chấp nhận phần mũ `E`, số 0 đầu, dấu `+`, số âm bằng `-0` và số chữ số tối đa hay không.

Một grammar **do ứng dụng lựa chọn** (không phải grammar duy nhất của tất cả giao thức) là:

```text
decimal := "-"? ( "0" | [1-9][0-9]* ) ( "." [0-9]+ )?
Hợp lệ:  0, -0, 12, 1234.50, -0.75
Không hợp lệ: 01, +2, .5, 1., 1,000.5, NaN, 1e3
```

Cú pháp ở trên cố ý **không cho phép số mũ** để hợp đồng dễ kiểm soát. JSON number lại có grammar riêng và *có* phần số mũ; đừng lấy regex này rồi tuyên bố nó là parser cho toàn bộ JSON.

Với Java, `new BigDecimal("1234.50")` tạo giá trị thập phân không phụ thuộc locale; `toPlainString()` tạo chuỗi decimal không có ký pháp mũ. Tuy nhiên, `BigDecimal(String)` chấp nhận một phạm vi cú pháp khác grammar đề xuất, nên **phải xác thực riêng** nếu giao thức yêu cầu grammar hẹp.

### Ví dụ Java 17+ kiểm tra decimal theo hợp đồng

Lưu **`StrictWireDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.regex.Pattern;

public class StrictWireDecimalDemo {
    private static final Pattern WIRE_DECIMAL = Pattern.compile(
            "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?");

    private static void inspect(String input) {
        if (!WIRE_DECIMAL.matcher(input).matches()) {
            System.out.println("Rejected: " + input);
            return;
        }

        BigDecimal amount = new BigDecimal(input);
        System.out.println("Accepted: " + amount.toPlainString());
    }

    public static void main(String[] args) {
        inspect("1234.50");
        inspect("1,234.50");
        inspect("0123");
        inspect("-0.75");
        inspect("1e3");
    }
}
```

Lệnh chạy tại thư mục chứa file:

```bash
javac -encoding UTF-8 StrictWireDecimalDemo.java
java StrictWireDecimalDemo
```

Stdout:

```text
Accepted: 1234.50
Rejected: 1,234.50
Rejected: 0123
Accepted: -0.75
Rejected: 1e3
```

**Giải thích:** `matches()` yêu cầu **toàn bộ** chuỗi đúng grammar; không chấp nhận một prefix hợp lệ rồi bỏ phần còn lại. Khi grammar hợp lệ, chuyển sang `BigDecimal`; từ đó các phép toán decimal có thể dùng `setScale(RoundingMode)` hoặc `MathContext` theo chính sách riêng. `toPlainString()` không tự thêm phân nhóm và không đọc cấu hình `Locale.getDefault()`.

**Cảnh báo cần thiết:** ví dụ minh họa cú pháp, chưa giới hạn kích thước chuỗi, số chữ số, quy mô tuyệt đối, scale, khoảng số hợp lệ hay tài nguyên máy dùng để xử lý input rất dài. Trong API thực, phải có giới hạn độ dài, precision, scale và phạm vi trước/sau parse. `BigDecimal` chính xác hơn `double` về decimal, nhưng không tự động bảo đảm input hợp lệ cho nghiệp vụ.

## 4. Chuyển đổi đúng tại ranh giới UI → mô hình → storage

Giả sử người dùng ở Đức nhập `1.234,50` và ứng dụng muốn lưu giá trị `1234.50`:

```text
UI người dùng (de-DE): "1.234,50"
            |
            | parse theo locale ĐƯỢC CHỌN cho input
            v
Mô hình Java: BigDecimal 1234.50
            |
            | validate số lượng, precision, scale, range
            v
Cột DECIMAL hoặc trường wire "1234.50"
            |
            | dữ liệu độc lập với locale
            v
Đọc lại -> BigDecimal -> format theo locale của người xem
```

**Không cố thay dấu phẩy thành dấu chấm bằng `String.replace(...)`** một cách phổ quát. Dấu phẩy có thể là grouping ở `en-US`, dấu thập phân ở `de-DE`, hoặc xuất hiện trong nội dung không phải số. Dùng parser locale-aware cho input do người dùng tạo, và kiểm tra toàn bộ chuỗi đã được tiêu thụ.

Trong Java, `NumberFormat.parse(String)` có thể chấp nhận **một prefix hợp lệ** mà không xác nhận phần ký tự còn lại. `DecimalFormat.setParseBigDecimal(true)` có thể giúp giữ giá trị thập phân thay vì chuyển về `double`, nhưng chỉ gọi được nếu parser thật sự là `DecimalFormat`. Với code yêu cầu decimal chính xác, một cách có kiểm soát là tạo `DecimalFormat` tường minh với `DecimalFormatSymbols.getInstance(userLocale)`, bật `setParseBigDecimal(true)`, dùng `ParsePosition` và kiểm tra `position.getIndex() == input.length()`. Mẫu pattern của parser còn có thể cho phép cách viết rộng hơn yêu cầu nghiệp vụ, nên vẫn cần validation.

### Minh họa Java 17+ đọc số UI theo locale

Tạo file **`UserNumberBoundaryDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class UserNumberBoundaryDemo {
    public static void main(String[] args) {
        Locale inputLocale = Locale.GERMANY;
        String typed = "1.234,50";

        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(inputLocale));
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(typed, position);

        boolean complete = parsed instanceof BigDecimal
                && position.getIndex() == typed.length()
                && position.getErrorIndex() < 0;

        if (!complete) {
            throw new IllegalArgumentException("Invalid amount");
        }

        BigDecimal value = (BigDecimal) parsed;
        System.out.println("Wire: " + value.toPlainString());
        System.out.println("Value unchanged: "
                + (value.compareTo(new BigDecimal("1234.50")) == 0));
    }
}
```

```bash
javac -encoding UTF-8 UserNumberBoundaryDemo.java
java UserNumberBoundaryDemo
```

Stdout trên JDK có dữ liệu `Locale.GERMANY` tương ứng:

```text
Wire: 1234.50
Value unchanged: true
```

Ứng dụng thực còn phải kiểm tra quy tắc grouping (parser có thể khá dung thứ), số chữ số tối đa, scale, phạm vi và liệu có chấp nhận chuỗi input đã trim hay không. `DecimalFormat` là đối tượng mutable, không chia sẻ cùng một instance không đồng bộ giữa nhiều request.

**Tách rõ hai luồng:** `user-entered text` có thể parse theo locale người dùng; `machine wire text` phải parse theo **grammar của giao thức**, không theo locale mặc định server. Đừng sử dụng phương thức locale-aware để đọc JSON numbers hoặc dữ liệu SQL decimal.

## 5. Định dạng máy đọc của ngày: LocalDate là ngày, không phải timestamp

Một ngày như ngày sinh hoặc ngày giao hàng chỉ có năm-tháng-ngày. Dùng `LocalDate` và biểu diễn ISO `yyyy-MM-dd`:

```text
2026-10-28
```

Đối với ngày lịch, định dạng này **không mang múi giờ**. Không nên tự chuyển `2026-10-28` thành `2026-10-28T00:00:00Z` rồi coi hai giá trị là đồng nghĩa: đó là một **thời điểm UTC**, trong khi ngày lịch chỉ là ngày và có thể diễn ra tại nhiều múi giờ.

Java:

```java
LocalDate date = LocalDate.parse(
        "2026-10-28", DateTimeFormatter.ISO_LOCAL_DATE);
String wire = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
```

Đây là **fragment trong một phương thức** với imports `java.time.LocalDate` và `java.time.format.DateTimeFormatter`. `LocalDate.parse` theo formatter ISO có kiểm tra ngày hợp lệ; chẳng hạn ngày `2026-02-30` không tồn tại và không được tự chuyển thành tháng ba trong cách parse chuẩn này.

Khi hiển thị trên UI, dùng `DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(uiLocale)` để render. Chuỗi ngày trên giao diện có thể khác giữa các locale, trong khi giá trị wire giữ nguyên.

## 6. Thời điểm tuyệt đối: UTC, offset và zone ID

Ba khái niệm dễ bị đánh đồng:

- **`Instant`:** một thời điểm trên trục thời gian; có thể trao đổi bằng chuỗi ISO-8601 với `Z`, ví dụ `2026-10-28T03:30:00Z`.
- **`OffsetDateTime`:** ngày-giờ kèm độ lệch UTC, ví dụ `2026-10-28T10:30:00+07:00`. Hai chuỗi có thể mô tả cùng một instant.
- **`ZonedDateTime`/`ZoneId`:** vùng múi giờ với quy tắc lịch sử và DST, chẳng hạn `Europe/Paris`. **Offset +07:00 không phải zone ID**: nó không mang theo toàn bộ quy tắc chuyển giờ theo khu vực.

### Ví dụ đầy đủ — `TemporalWireDemo.java`

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class TemporalWireDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse(
                "2026-10-28", DateTimeFormatter.ISO_LOCAL_DATE);
        Instant utc = Instant.parse(
                "2026-10-28T03:30:00Z");
        OffsetDateTime localOffset = OffsetDateTime.parse(
                "2026-10-28T10:30:00+07:00");

        System.out.println("Day: " + day);
        System.out.println("UTC instant: " + utc);
        System.out.println("Same instant: "
                + utc.equals(localOffset.toInstant()));

        try {
            LocalDate.parse("2026-02-30");
            System.out.println("Invalid date accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 TemporalWireDemo.java
java TemporalWireDemo
```

Stdout:

```text
Day: 2026-10-28
UTC instant: 2026-10-28T03:30:00Z
Same instant: true
Invalid date rejected
```

Nhận xét: cùng một instant có thể được biểu diễn bằng `Z` hoặc một offset cụ thể. Nếu API yêu cầu **UTC canonical form**, hãy chuyển qua `Instant` và định dạng theo hợp đồng đó; đừng chỉ xóa phần `+07:00` khỏi chuỗi. Cần quy định rõ độ chính xác phần giây (giây/millisecond/microsecond/nanosecond), cách làm tròn và sự tương thích của bên tiêu thụ; `Instant.toString()` có thể bỏ các chữ số phần giây không cần thiết và không phải cam kết độ rộng cố định.

**Dữ liệu về cuộc hẹn theo giờ địa phương:** nếu người dùng đặt lịch “09:00 hằng ngày ở Europe/Paris”, chỉ lưu `Instant` của một lần xảy ra có thể không đủ để tái tạo lịch lặp theo quy tắc DST. Khi nghiệp vụ cần, lưu **local date/time + IANA zone ID + chính sách xử lý giờ trùng/không tồn tại**. Lưu một offset tức thời không thay thế được zone ID.

## 7. Mã locale trong tệp và API: dùng BCP 47, không dùng tên hiển thị

Cần phân biệt:

| Vai trò | Giá trị |
| --- | --- |
| Thẻ locale chuẩn hóa để trao đổi | `vi-VN`, `en-US`, `pt-BR` |
| Java tạo đối tượng | `Locale.forLanguageTag("vi-VN")` hoặc `Locale.Builder` |
| Java xuất thẻ | `locale.toLanguageTag()` |
| Java `locale.toString()` cũ | Có thể dùng dấu `_` và có phần mở rộng theo cú pháp Java riêng |
| Nhãn UI | `locale.getDisplayName(uiLocale)`, phụ thuộc locale hiển thị |
| Tên file `ResourceBundle` | Ví dụ `messages_vi_VN.properties`; đây là quy ước tài nguyên, không phải wire tag |

Nếu API nhận `languageTag`, **đừng lưu nhãn tiếng Việt `"Tiếng Anh (Hoa Kỳ)"` hoặc chuỗi `Locale.toString()` như thể đó là BCP 47**. Locale label phụ thuộc ngôn ngữ giao diện/JDK; `Locale.toString()` không phải serialisation thẻ BCP 47 được thiết kế cho HTTP/JSON.

**Lưu ý về parse:** `Locale.forLanguageTag(String)` cố tình khoan dung với input lỗi theo BCP 47, có thể bỏ hoặc điều chỉnh phần không hợp lệ. Nếu cần **từ chối cú pháp sai**, dùng `new Locale.Builder().setLanguageTag(input).build()` và bắt `IllformedLocaleException`; sau đó còn phải đối chiếu với **tập locale được sản phẩm hỗ trợ**. Cú pháp hợp lệ **không** có nghĩa ứng dụng có tài nguyên dịch/định dạng nghiệp vụ tương ứng.

### Ví dụ Java 17+ — `LocaleWireDemo.java`

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleWireDemo {
    public static void main(String[] args) {
        Locale locale = new Locale.Builder()
                .setLanguageTag("pt-BR")
                .build();
        System.out.println("Tag: " + locale.toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en_US").build();
            System.out.println("Unexpected acceptance");
        } catch (IllformedLocaleException ex) {
            System.out.println("Invalid tag rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LocaleWireDemo.java
java LocaleWireDemo
```

Stdout:

```text
Tag: pt-BR
Invalid tag rejected
```

Dấu gạch nối `-` của thẻ BCP 47 khác dấu gạch dưới `_` ở một số tên file properties truyền thống. Đừng suy diễn một định dạng từ định dạng còn lại bằng replace nếu yêu cầu hỗ trợ đủ language/script/region/variant/extension; dùng API locale chuyên dụng.

## 8. Tệp văn bản: bytes phải có charset, newline và cấu trúc rõ

Một tệp máy đọc không chỉ là `String`: nó là **byte + encoding + format + version/schema**. Trong hệ thống mới, **UTF-8** thường là lựa chọn hợp lý để hỗ trợ tiếng Việt và các bảng chữ khác.

Java 17 có API tạo/đọc file văn bản với charset tường minh:

```java
Files.writeString(path, text, StandardCharsets.UTF_8);
String loaded = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **fragment** có biến `path` và `text` được khai báo. Hai phương thức có overload có default charset UTF-8 trong Java hiện đại, nhưng truyền `StandardCharsets.UTF_8` tường minh làm hợp đồng rõ ràng, nhất là khi code bị chuyển sang API I/O khác.

Một bộ quy tắc file nên xác định:

- **Encoding:** UTF-8, có/không BOM, xử lý byte không hợp lệ; không đoán qua default charset.
- **Dấu kết thúc dòng:** LF hoặc CRLF, có chấp nhận dòng cuối không có newline hay không.
- **Cấu trúc:** JSON, CSV, TSV, NDJSON hoặc định dạng domain đã được version; có delimiter và quoting được định nghĩa.
- **Schema:** tên trường, kiểu, null/missing, precision, phạm vi, bắt buộc/tùy chọn và khả năng mở rộng.
- **Đọc/ghi lỗi:** khi parse sai cần báo nguyên nhân, không biến dữ liệu lỗi thành zero/ngày hiện tại mà không có chính sách.

### Ví dụ Java 17+ round-trip UTF-8

Lưu **`Utf8FileRoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FileRoundTripDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("localization-", ".txt");
        try {
            String original = "Chào bạn — café";
            Files.writeString(
                    path, original, StandardCharsets.UTF_8);

            String restored = Files.readString(
                    path, StandardCharsets.UTF_8);
            System.out.println("Round trip: "
                    + original.equals(restored));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac -encoding UTF-8 Utf8FileRoundTripDemo.java
java Utf8FileRoundTripDemo
```

Stdout:

```text
Round trip: true
```

Mã dùng tệp tạm để bảo đảm ví dụ độc lập; nó xóa tệp trong `finally` khi đã thử. Trong ứng dụng thực, lưu ý quyền ghi, lỗi I/O, atomic write, tính toàn vẹn và encoding của dữ liệu nguồn. Một round-trip thành công chỉ chứng minh hai phía cùng dùng UTF-8 trong ví dụ, **không chứng minh mọi hệ thống khác đều đang đọc đúng format**.

## 9. JSON trong API: grammar của JSON không phải grammar của NumberFormat

JSON sử dụng cấu trúc với number, string, boolean, null, array và object. Trong JSON, **number token** viết bằng chữ số ASCII và `.` làm dấu thập phân; **không dùng dấu phân nhóm theo locale**:

```json
{
  "amount": 1234.50,
  "eventDate": "2026-10-28",
  "occurredAt": "2026-10-28T03:30:00Z",
  "locale": "vi-VN",
  "customerCode": "001234"
}
```

Một chuỗi JSON chứa `"amount": 1.234,50` là sai cú pháp JSON, kể cả người dùng đang xem giao diện tiếng Đức. Việc hiển thị của UI nằm **sau khi** JSON đã được parse thành dữ liệu có kiểu.

**JSON number và độ chính xác:** JSON không định nghĩa rằng mọi implementation bên nhận phải dùng `BigDecimal`. Nhiều client JavaScript dùng `Number` (binary floating point), khiến số nguyên rất lớn hoặc decimal tiền tệ có thể mất precision. Nếu API tài chính cần decimal chính xác end-to-end, cần hợp đồng rõ: ví dụ trường `"amount": "1234.50"` là string decimal hợp lệ và cả hai phía parse bằng kiểu decimal phù hợp, hoặc sử dụng phương án typed/decimal đã thỏa thuận. Không mặc định JSON number nào cũng giữ nguyên decimal scale hay precision ở mọi ngôn ngữ.

**Java SE 17 không có parser/generator JSON tổng quát dựng sẵn trong `java.base`.** Ở ứng dụng thực, sử dụng thư viện JSON chuẩn của stack (ví dụ Jackson hoặc JSON-B) với cấu hình serialize/deserialize kiểu `BigDecimal`, `LocalDate`, `Instant` và validation thích hợp. Đừng nối chuỗi thủ công để tạo JSON từ input người dùng: ký tự trích dẫn, backslash, control characters và Unicode cần được escape theo JSON.

### HTTP: charset và media type

Khi gửi JSON, dùng media type `application/json` và nội dung UTF-8 theo hợp đồng JSON hiện đại. Tránh dựa vào locale của HTTP server để mã hóa hoặc parse payload. Header `Accept-Language` là **gợi ý ngôn ngữ cho nội dung trình bày**, không thay grammar của số JSON. `Content-Language` có thể mô tả ngôn ngữ của phần nội dung, nhưng không biến `1234.50` thành `1.234,50` trong JSON number.

Nếu API muốn trả giá trị đã format cho UI, nên phân biệt trường **giá trị có kiểu** và **nhãn hiển thị**. Một trường có tên `amount` dùng cho máy không nên âm thầm thay từ number sang string theo locale của request.

## 10. CSV và TSV: định nghĩa delimiter, quoting, encoding và schema

CSV là một **định dạng trao đổi văn bản**; dấu phẩy vừa có thể là delimiter, vừa có thể xuất hiện trong một trường tên hoặc trong chuỗi số được format theo locale. Nếu không có hợp đồng quoting, parser có thể nhầm số cột.

Ví dụ CSV với ba cột: `id,amount,customerName`:

```csv
id,amount,customerName
1,1234.50,"Nguyễn, Lan"
2,15.00,"Lê ""An"""
```

Theo quy ước CSV kiểu RFC 4180, dấu `"` trong trường trích dẫn được biểu diễn bằng **hai dấu `""`**, và dấu phẩy bên trong trường đã quote **không tách cột**. File trao đổi nên quy định charset UTF-8, delimiter, header, newline và quy tắc quote; không tự dùng dấu chấm phẩy chỉ vì `Locale` của một người xem dùng dấu phẩy thập phân.

**Fragment encoder đơn giản cho một trường CSV** (không phải parser hoặc writer CSV đầy đủ):

```java
static String quotedCsvField(String value) {
    return "\"" + value.replace("\"", "\"\"") + "\"";
}
```

Nó **luôn quote** một trường và nhân đôi các dấu `"` bên trong. Khi ghi cả file cần xử lý newline, CRLF, delimiter, null và schema nhất quán; khi đọc, **không dùng `String.split(",")` làm CSV parser** vì hàm đó không hiểu quoted fields hoặc dấu xuống dòng trong trường. Sử dụng thư viện CSV uy tín hoặc parser theo grammar hợp đồng.

### Bài học từ số thập phân trong CSV

Một file có cột `amount` theo máy có thể chứa `1234.50`. Không được dùng `NumberFormat.getCurrencyInstance(locale).format(amount)` rồi lưu vào cột dữ liệu vì có thể thêm dấu phân nhóm và ký hiệu tiền tệ. Khi cần lưu thêm nhãn `1.234,50 €` cho một báo cáo phục vụ con người, đó là **cột trình bày khác**, không thay cho trường giá trị.

Nếu phần mềm bảng tính của người dùng tự nhận diện CSV theo locale, hãy coi đó là **hành vi nhập của client**, không phải lý do để thay đổi hợp đồng hệ thống máy đọc. Có thể cung cấp một bản xuất “cho Excel người dùng” riêng với thông số delimiter rõ ràng.

## 11. Database: lưu số/ngày theo kiểu cột, không lưu bản dịch chuỗi

Trong một cơ sở dữ liệu quan hệ, hãy ưu tiên các cột có kiểu tương ứng:

| Dữ liệu | Kiểu cột thường gặp | Java |
| --- | --- | --- |
| Giá trị tiền/decimal | `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` | `BigDecimal` |
| Số lượng nguyên | `INTEGER`, `BIGINT` | `int`/`long` |
| Ngày lịch | `DATE` | `LocalDate` (JDBC 4.2+ và driver hỗ trợ) |
| Timestamp | Cột thời gian tương ứng với hệ CSDL; chọn ngữ nghĩa UTC/offset/zone rõ | `Instant`/`OffsetDateTime` theo mapping của driver |
| Thẻ locale | `VARCHAR` với constraint ứng dụng | BCP 47 string như `vi-VN` |
| Mã khách có leading zeros | `VARCHAR` | `String` |

**Không lưu `"1.234,50"` vào cột decimal, `"28/10/2026"` vào cột DATE** chỉ vì đó là cách người dùng nhìn thấy. Dữ liệu có kiểu giúp truy vấn, index, tính toán và di chuyển môi trường an toàn hơn.

Với JDBC, dùng **prepared statements và typed parameters**, không nối literal số/ngày đã format vào SQL:

```java
// Fragment bên trong phương thức với PreparedStatement ps.
ps.setBigDecimal(1, new BigDecimal("1234.50"));
ps.setObject(2, LocalDate.of(2026, 10, 28));
ps.setString(3, "vi-VN");
```

Đoạn này giả định câu SQL đã có các tham số `?` đúng thứ tự, cùng kết nối/driver JDBC phù hợp. `LocalDate` được hỗ trợ ở JDBC 4.2 nhưng mapping timestamp/zone còn phụ thuộc DB/driver và loại cột. Với thời điểm tuyệt đối, cần xem tài liệu driver về cách lưu UTC, offset và chuyển timezone; không mặc định mọi cột `TIMESTAMP` của mọi DB có nghĩa như `Instant`.

**PreparedStatement không chỉ tránh lỗi dấu phân cách decimal**, mà còn tách cấu trúc truy vấn và dữ liệu đầu vào, giảm nguy cơ SQL injection. Locale dùng để format báo cáo **không phải** một tham số quyết định SQL parser sẽ hiểu dấu phẩy hay dấu chấm.

## 12. Ký tự, Unicode và mã định danh

UTF-8 chuyển ký tự thành byte nhất quán, nhưng **không tự chuẩn hóa Unicode**. Một chữ có dấu có thể có biểu diễn Unicode dạng ký tự dựng sẵn hoặc dạng ký tự cơ sở + dấu kết hợp. Hai chuỗi trông giống nhau có thể có dãy code point khác nhau.

Đối với tên người và văn bản tự do, phải có chính sách lưu trữ/so sánh phù hợp, tránh tự bỏ dấu hoặc đổi chữ hoa/thường bằng default locale mà không hiểu hậu quả. Nếu hệ thống chọn một form chuẩn hóa như **NFC**, làm ở ranh giới được định nghĩa và kiểm thử hiệu quả; không chuẩn hóa vô điều kiện mọi chuỗi mã/ID nếu giao thức yêu cầu giữ nguyên byte hoặc có chữ ký số.

Đối với machine-readable identifiers:

- `"001234"` là **mã**, không phải số 1234; nếu đổi sang `int` sẽ mất số 0 đầu.
- UUID, hash, enum code, currency code như `USD` nên theo chính tả chuẩn giao thức, không theo tên hiển thị `"Đô la Mỹ"`.
- Đừng dùng `getDisplayName()` của locale làm khóa database; nhãn có thể thay đổi theo ngôn ngữ giao diện/JDK.
- Nếu ký số/canonicalize JSON hoặc file, phải dùng **quy tắc canonicalization** được định nghĩa bởi giao thức và hai phía, không chỉ tùy tiện trim hoặc dùng `toString()`.

## 13. Một mô hình API Java tách dữ liệu khỏi nhãn

Có thể tổ chức luồng xử lý thành các bước sau:

```text
Request/CSV/file
    ↓ Parse đúng grammar + charset
Typed input DTO (BigDecimal, LocalDate, Instant, Locale tag)
    ↓ Validate domain (precision, scale, date range, supported locale)
Domain/service + database typed columns
    ↓ Serialize theo schema máy đọc
Stable API/file values
    ↓ Tại tầng UI: format theo Locale người xem
Human-readable labels
```

Nếu một request mang cả `locale=de-DE` và `amount="1234.50"`, nên diễn giải `locale` là cài đặt/gợi ý trình bày được sản phẩm cho phép, còn `amount` vẫn là wire decimal theo schema. Nếu sản phẩm thiết kế endpoint **nhận chuỗi số người dùng nhập** theo locale, hãy nêu rõ endpoint ấy là đường nhập của UI và parse theo locale đã được xác thực, không lẫn với endpoint dùng numeric wire format.

### Ví dụ Java 17+ round-trip một bản ghi

Tạo file **`StableRecordDemo.java`**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Locale;

public class StableRecordDemo {
    record OrderData(
            BigDecimal amount,
            LocalDate deliveryDate,
            Instant createdAt,
            Locale displayLocale) {}

    public static void main(String[] args) {
        OrderData order = new OrderData(
                new BigDecimal("1234.50"),
                LocalDate.parse("2026-10-28"),
                Instant.parse("2026-10-28T03:30:00Z"),
                Locale.forLanguageTag("vi-VN"));

        String amountWire = order.amount().toPlainString();
        String dayWire = order.deliveryDate().toString();
        String instantWire = order.createdAt().toString();
        String localeWire = order.displayLocale().toLanguageTag();

        OrderData restored = new OrderData(
                new BigDecimal(amountWire),
                LocalDate.parse(dayWire),
                Instant.parse(instantWire),
                Locale.forLanguageTag(localeWire));

        System.out.println("Amount: " + amountWire);
        System.out.println("Day: " + dayWire);
        System.out.println("Instant: " + instantWire);
        System.out.println("Locale: " + localeWire);
        System.out.println("Same data: "
                + order.equals(restored));
    }
}
```

```bash
javac -encoding UTF-8 StableRecordDemo.java
java StableRecordDemo
```

Stdout:

```text
Amount: 1234.50
Day: 2026-10-28
Instant: 2026-10-28T03:30:00Z
Locale: vi-VN
Same data: true
```

Đây là ví dụ **định nghĩa và kiểm tra các giá trị canonical cho một mô hình nhỏ**, chưa phải JSON serializer hoặc JDBC adapter. Trong hệ thống thật, schema cần rõ trường nào bắt buộc, null hay vắng trường, định dạng decimal, precision, timestamp fraction, giới hạn độ dài và chiến lược version. `BigDecimal.equals` còn quan tâm **scale**, do đó nếu hệ thống không yêu cầu giữ scale, phải chọn chính sách so sánh/normalize thích hợp và kiểm tra bằng `compareTo` theo nhu cầu.

## 14. Quy ước phải được version và kiểm tra nghiêm túc

**“Máy đọc được” không đồng nghĩa “hễ parse thành công là đúng”.** Một dữ liệu trao đổi phải tuân thủ những điều kiện:

1. **Định dạng được đặt tên:** JSON/CSV/ISO/BCP47/decimal grammar; không mô tả mơ hồ “dạng số quốc tế”.
2. **Kiểu và nullability:** trường nào là number/string/date, trường nào có thể null hoặc không có mặt.
3. **Precision, scale, range:** số chữ số tối đa, phần lẻ cho phép, vùng giá trị, đơn vị tiền/đo.
4. **Time semantics:** ngày lịch hay instant; offset, zone ID, độ chính xác phần giây và DST khi liên quan.
5. **Charset và newline:** UTF-8, có/không BOM, policy khi byte không hợp lệ, newline CSV.
6. **Canonicalization nếu cần:** định dạng ổn định phục vụ so sánh/chữ ký/kiểm toán; không tự coi mọi `toString` canonical.
7. **Version/schema evolution:** có chính sách thêm field, bỏ field, tương thích client cũ và migration dữ liệu.
8. **Thông báo lỗi:** lỗi parse/validate phải có mã lỗi và trường liên quan; không âm thầm đổi input lỗi thành giá trị khác.
9. **Khả năng round-trip:** parse → serialize → parse không làm mất ý nghĩa đã cam kết; thử locale default khác nhau.
10. **An toàn:** giới hạn kích thước request, số chữ số, độ sâu JSON, file CSV, ký tự điều khiển; dùng thư viện parse phù hợp để tránh injection và DoS.

Ví dụ, format `BigDecimal("1234.50")` qua một `NumberFormat` tối đa một chữ số lẻ rồi parse ngược có thể thành `1234.5`; **giá trị số** bằng nhau nhưng **scale** và chuỗi ban đầu đã khác. Cần biết hợp đồng của mình yêu cầu giữ giá trị, giữ số chữ số lẻ, hay giữ nguyên literal.

## 15. Kiểm thử độc lập với locale mặc định của máy chạy

Một bài test có giá trị là chạy việc đọc dữ liệu máy với **hai locale JVM khác nhau** và chứng minh kết quả không thay đổi:

```bash
java -Duser.language=en -Duser.country=US StableRecordDemo
java -Duser.language=de -Duser.country=DE StableRecordDemo
```

Chương trình `StableRecordDemo` không dùng `Locale.getDefault()` để parse/serialize nên những trường máy đọc của ví dụ giữ cùng ý nghĩa. Lưu ý `-D...` trong đây là **cấu hình khởi động JVM**, không phải lời khuyên đổi default trong chương trình server.

Các trường hợp QA nên có:

| Nhóm | Input kiểm thử | Kết quả mong muốn |
| --- | --- | --- |
| Decimal hợp lệ | `1234.50` | Parse đúng decimal; không grouping |
| Decimal sai wire grammar | `1.234,50`, `1,234.50` | Reject ở endpoint sử dụng grammar hẹp |
| Số quá lớn/quá nhiều chữ số | Chuỗi nhiều chữ số vượt policy | Reject có giới hạn trước khi tiêu tốn tài nguyên |
| Date chuẩn | `2026-10-28` | Parse thành `LocalDate` |
| Date sai | `2026-02-30` | Reject, không tự đổi ngày |
| Instant/offset | `...Z` và `...+07:00` tương đương | So cùng instant sau chuyển offset |
| Locale hợp lệ/cú pháp sai | `pt-BR` / `en_US` | Validate tag, đối chiếu supported locales |
| Unicode text | `Chào bạn`, ký tự kết hợp | UTF-8 đúng, áp dụng policy Unicode rõ |
| CSV quoted field | `"Nguyễn, Lan"` | Không bị tách thành hai cột |
| JSON decimal lớn | Số ngoài safe-integer của client | Áp dụng schema string decimal hoặc giải pháp precision |
| DB typed parameter | `BigDecimal`, `LocalDate` | Không cần chuỗi hiển thị để chèn SQL |
| Locale mặc định đổi | JVM `en-US` và `de-DE` | Machine representations vẫn ổn định |

**Không kiểm thử chỉ bằng mắt** rằng số nhìn “đẹp”; phải so sánh giá trị có kiểu, literal wire và khả năng round-trip. Với JSON/CSV, có thể viết test contract giữa hai service dùng parser khác nhau để phát hiện khác biệt trước khi phát hành.

## 16. Các lỗi phổ biến

| Sai lầm | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Dùng `NumberFormat.getInstance()` mặc định cho API/DB | Kết quả thay đổi theo locale máy chủ | Dùng kiểu/grammar máy đọc đã định nghĩa |
| Lưu số ở dạng `1.234,50` | Bên nhận hiểu sai decimal hoặc dấu nhóm | Chuyển sang `BigDecimal` và serialize theo schema |
| Dùng `String.replace(",", ".")` để chuẩn hóa mọi số | Sai khi có grouping và format khác nhau | Parse UI theo locale cụ thể, kiểm tra toàn input |
| Dùng `double` cho decimal tiền cần chính xác | Sai số nhị phân, mất precision | `BigDecimal` và policy rounding rõ |
| Dùng `BigDecimal.toString()` rồi tin luôn không có số mũ | Có thể dùng dạng scientific notation | Chọn `toPlainString()` nếu grammar cấm số mũ |
| Dùng `Date.toString()` làm timestamp API | Không phải hợp đồng wire ổn định, có timezone | `Instant`/ISO với offset/UTC rõ |
| Lưu ngày sinh thành midnight UTC | Khi đổi múi giờ có thể lệch ngày | `LocalDate`, cột DATE |
| Lưu giờ hẹn lặp chỉ bằng offset | Không có quy tắc DST của địa phương | Lưu `ZoneId` và local schedule khi cần |
| Lưu `Locale.getDisplayName()` vào API | Nhãn phụ thuộc ngôn ngữ UI | Dùng `toLanguageTag()` |
| Tin `Locale.forLanguageTag` tự từ chối mọi lỗi | API khoan dung với phần sai | Dùng `Locale.Builder` và supported-locale validation |
| Gọi `String.split(",")` cho CSV | Không xử lý dấu phẩy trong quoted field | Dùng CSV parser theo grammar |
| Nối chuỗi JSON thủ công | Escape sai, JSON injection/sai cú pháp | Dùng JSON serializer |
| Lưu mã `001234` dưới dạng số nguyên | Mất leading zeros | Dùng String |
| Đổi `Locale.setDefault` cho từng request | Ảnh hưởng toàn JVM, race condition | Truyền locale theo request cho tầng UI |
| Ghi tệp qua charset mặc định mà không có hợp đồng | Bị hỏng Unicode khi đổi môi trường | UTF-8 tường minh |
| Bỏ validation vì parser trả object | Có thể sai domain/precision/scale | Validate cả cú pháp, phạm vi, scale và đơn vị |
| Chuyển SQL literal từ số đã format | Sai syntax và nguy cơ injection | PreparedStatement typed parameters |

## 17. Bài tập ứng dụng

**Bài 1 — Chuẩn hóa đường nhập số.** Tạo một giao diện ở `de-DE` nhận `1.234,50`. Parse bằng `DecimalFormat` với symbols tương ứng và `ParsePosition`; validate precision/scale; lưu thành `BigDecimal`. Khi trả API machine decimal, dùng `toPlainString()` theo grammar đã công bố. So sánh kết quả với nhập `1,234.50` ở `en-US`.

**Bài 2 — Phân biệt ngày với thời điểm.** Thiết kế DTO cho `birthDate=2026-10-28` và `createdAt=2026-10-28T03:30:00Z`. Chọn `LocalDate`/`Instant` tương ứng; thử chuyển cùng instant sang offset `+07:00` và so sánh bằng `toInstant()`.

**Bài 3 — Hợp đồng JSON decimal.** Giả sử frontend JavaScript cần xử lý hóa đơn decimal chính xác. Đề xuất schema dùng `"amount": "1234.50"` và nêu rõ đơn vị tiền (ví dụ `"currency": "USD"`), cách parse, precision/scale/rounding. Giải thích vì sao một trường hiển thị như `"1,234.50 USD"` không đủ dùng cho tính toán.

**Bài 4 — CSV có tên chứa dấu phẩy.** Tạo một CSV với trường `customerName=Nguyễn, Lan`, số decimal `1234.50` và timestamp ISO. Kiểm chứng parser CSV không nhầm dấu phẩy trong quoted field thành dấu phân cột.

**Bài 5 — Locale tag.** Kiểm tra `pt-BR`, `zh-Hant-TW`, `en_US` bằng `Locale.Builder`. Ghi nhận giá trị hợp lệ về cú pháp, và thử đối chiếu với danh sách locale hỗ trợ của ứng dụng. Phân biệt “tag hợp lệ” với “ứng dụng có bản dịch”.

## 18. Tài liệu tham khảo

- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): numeric string, `toPlainString`, precision và scale.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO formatters, parse/format và locale.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `toLanguageTag`, `forLanguageTag` và `Locale.Builder`.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): parsing theo locale, `setParseBigDecimal`, rounding.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON và trao đổi UTF-8.
- [RFC 4180 — CSV](https://www.rfc-editor.org/rfc/rfc4180): quy tắc quoted fields của CSV truyền thống.
- [RFC 5646 — Language Tags](https://www.rfc-editor.org/rfc/rfc5646): cơ sở cú pháp thẻ ngôn ngữ BCP 47.

## 19. Ghi nhớ

**Không lưu hoặc truyền “số/ngày đã được dịch” khi bên nhận cần dữ liệu có kiểu.** Dùng `BigDecimal` cho decimal chính xác, `LocalDate` cho ngày lịch, `Instant`/offset rõ ràng cho thời điểm, BCP 47 cho locale, UTF-8 cho tệp và các chuẩn cụ thể như JSON/CSV/JDBC với schema được version. Parse input người dùng theo **locale của input**; parse machine wire theo **grammar của giao thức**, độc lập default JVM. Luôn kiểm tra toàn input, precision/scale/range, múi giờ và khả năng round-trip; chỉ khi hiển thị cho người dùng mới áp dụng `Locale` để tạo nhãn phù hợp.