# Ma trận kiểm thử locale: vi-VN, en-US, de-DE, tr-TR và ngôn ngữ phải–trái trong Java

## 1. Vì sao một bài kiểm thử tiếng Anh không bảo đảm localization đúng?

Một chương trình Java có thể chạy hoàn hảo với `Locale.US` nhưng thất bại khi người dùng chọn tiếng Việt, tiếng Đức, tiếng Thổ Nhĩ Kỳ hoặc một ngôn ngữ viết **từ phải sang trái (RTL)**. Lỗi có thể nằm ở:

- Cách viết **số, phân cách hàng nghìn, dấu thập phân, phần trăm, tiền tệ**.
- **Thứ tự ngày/tháng/năm**, tên tháng, múi giờ và cách parse lại chuỗi ngày.
- **Chữ hoa/chữ thường theo ngôn ngữ**, đặc biệt chữ I trong tiếng Thổ Nhĩ Kỳ.
- **Tải bản dịch `ResourceBundle`**, fallback, các key hoặc placeholder bị thiếu.
- **Sắp xếp chữ theo ngôn ngữ** với `Collator` thay vì `String.compareTo`.
- **Bố cục RTL**, vị trí icon, nút, dấu câu, số và văn bản pha trộn Latin/Ả Rập/Hebrew.
- **Độ dài bản dịch**, Unicode combining marks, emoji, text overflow và vấn đề accessibility.
- Lỗi chỉ xuất hiện khi máy chủ dùng một **default locale khác** môi trường phát triển.

Vì thế, một **ma trận locale** không chỉ là danh sách ngôn ngữ để “mở xem thử”, mà là kế hoạch QA có dữ liệu, điều kiện, kỳ vọng, loại test và tiêu chí đánh giá rõ ràng.

Bài này sử dụng **Java 17+**, tập trung vào sáu locale đại diện:

1. `vi-VN` — tiếng Việt tại Việt Nam;
2. `en-US` — tiếng Anh tại Hoa Kỳ;
3. `de-DE` — tiếng Đức tại Đức;
4. `tr-TR` — tiếng Thổ Nhĩ Kỳ tại Thổ Nhĩ Kỳ;
5. `ar-EG` — tiếng Ả Rập tại Ai Cập, ngôn ngữ RTL;
6. `he-IL` — tiếng Hebrew tại Israel, ngôn ngữ RTL.

**Lưu ý về thuật ngữ:** `Locale` không phải là test case duy nhất. Mỗi locale còn phải được kiểm thử trên dữ liệu/ngữ cảnh cụ thể, với font, viewport, `ZoneId`, charset và phiên bản JDK/CLDR được xác định khi cần.

## 2. Xác định phạm vi của ma trận

| Locale | Mục tiêu kiểm thử trọng tâm | Ví dụ rủi ro |
| --- | --- | --- |
| `vi-VN` | Chữ có dấu, bản dịch tiếng Việt, ngày/số bản địa | Thiếu font, dấu lỗi, text dài, fallback |
| `en-US` | Mốc so sánh tiếng Anh, ngày tháng theo Hoa Kỳ | Giả định tất cả locale có cùng pattern |
| `de-DE` | Dấu thập phân và grouping khác tiếng Anh, format tiền/số | Parse `1,5` như `1.5` theo locale sai |
| `tr-TR` | Hai cặp chữ I/ı và İ/i; case mapping và lookup key | `"TITLE".toLowerCase()` ra `"tıtle"` |
| `ar-EG` | Định dạng và chữ Ả Rập, số/văn bản lẫn LTR, UI RTL | Dấu câu, thứ tự icon, mã số hiển thị lộn xộn |
| `he-IL` | Văn bản Hebrew, LTR/RTL pha trộn, ngày và layout | Căn lề, caret, dấu ngoặc, email/URL |

Ma trận trên **không ngầm khẳng định** mọi người dùng `ar-EG` sẽ dùng cùng kiểu chữ số, tiền tệ hay lịch. Hành vi có thể thay đổi theo Unicode locale extensions, preference riêng, JDK locale provider và chính sách sản phẩm.

Tương tự, một người dùng ở Việt Nam có thể dùng giao diện tiếng Anh, múi giờ Nhật và đơn vị tiền tệ USD. **Locale, ZoneId, Currency, Chronology, writing direction và định dạng giao thức là những lựa chọn liên quan nhưng không đồng nhất.**

### 2.1. Hai chiều kiểm thử: chức năng và trình bày

**Kiểm thử chức năng có thể tự động hóa:**

- Format số/ngày thành chuỗi và parse lại bằng đúng formatter.
- Lấy đúng bundle, đủ key và đúng fallback.
- Case mapping Thổ Nhĩ Kỳ ra đúng Unicode code points.
- So sánh chuỗi theo `Collator` với bộ dữ liệu/cấu hình đã xác định.
- Không thay đổi giá trị nghiệp vụ khi đổi locale.
- Dữ liệu API vẫn ở định dạng máy tường minh.

**Kiểm thử trực quan hoặc tương tác:**

- Thứ tự hiển thị RTL trong UI; biểu tượng, nút Back/Next, menu, breadcrumb.
- Nội dung lẫn chữ Ả Rập/Hebrew và số ASCII/URL.
- Vị trí dấu câu, cursor, selection, copy/paste.
- Tràn chữ khi bản dịch dài, phóng to font hoặc màn hình hẹp.
- Screen reader đọc đúng thứ tự ngữ nghĩa.
- Font fallback, diacritics và glyph shaping đúng.

Không nên đánh dấu **“PASS toàn bộ RTL” chỉ vì `java.text.Bidi` xác định được hướng đoạn**. Phần rendering còn cần engine UI và kiểm thử người dùng.

## 3. Khởi tạo các Locale một cách tường minh

Java hỗ trợ BCP 47 language tags:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.forLanguageTag("en-US");
Locale de = Locale.forLanguageTag("de-DE");
Locale tr = Locale.forLanguageTag("tr-TR");
Locale ar = Locale.forLanguageTag("ar-EG");
Locale he = Locale.forLanguageTag("he-IL");
```

Đây là đoạn mã minh họa **bên trong method**, cần `import java.util.Locale;`.

Trong application thực tế, nên có **danh sách locale được hỗ trợ** do sản phẩm xác nhận, không chấp nhận mọi language tag rồi giả định đã có bản dịch và font.

### 3.1. Language tag khác locale mặc định

- `Locale.forLanguageTag("de-DE")` tạo locale đích rõ ràng.
- `Locale.getDefault()` nhận default locale chung cho JVM.
- `Locale.getDefault(Locale.Category.FORMAT)` nhận default phục vụ định dạng.
- `Locale.getDefault(Locale.Category.DISPLAY)` nhận default cho display names.

Đừng dùng `Locale.setDefault(...)` cho **mỗi HTTP request**: default là trạng thái toàn JVM có thể ảnh hưởng người dùng khác. Truyền locale từng nơi, hoặc quản lý context theo request nhưng **không biến nó thành default toàn hệ thống**.

### 3.2. Unicode locale extensions

Language tag có thể chứa lựa chọn bổ sung, chẳng hạn:

```text
ar-EG-u-nu-latn
th-TH-u-ca-buddhist
```

`nu` gợi ý hệ chữ số và `ca` gợi ý calendar; nhưng khả năng áp dụng phụ thuộc API cụ thể và locale provider. Không suy rằng chỉ gọi `String.toLowerCase(locale)` hoặc `NumberFormat.getInstance(locale)` sẽ áp dụng cùng một tập extension giống tất cả các API còn lại.

Một locale tag **không tự quyết định** `ZoneId`. Với định dạng giờ, chọn ZoneId riêng theo nghiệp vụ.

## 4. Ma trận kiểm thử nền tảng

Đây là **bộ kiểm thử mẫu** có thể chuyển thành test plan của sản phẩm:

| Nhóm chức năng | vi-VN | en-US | de-DE | tr-TR | ar-EG | he-IL |
| --- | --- | --- | --- | --- | --- | --- |
| Số/thập phân | Có | Có | Có | Có | Có | Có |
| Phần trăm/tiền tệ | Có | Có | Có | Có | Có | Có |
| Ngày giờ localized | Có | Có | Có | Có | Có | Có |
| Date/number parse round-trip | Có | Có | Có | Có | Có | Có |
| ResourceBundle/fallback | Có | Có | Có | Có | Có | Có |
| Format placeholder | Có | Có | Có | Có | Có | Có |
| Collation/sort | Có | Có | Có | Có | Có | Có |
| Case-mapping chữ I | Bảo đảm không bị locale khác tác động | Mốc ROOT | Theo policy | **Đặc biệt** | Không dùng để suy I tiếng Thổ | Không dùng để suy I tiếng Thổ |
| Chữ có dấu/Unicode | **Đặc biệt** | Cơ bản | Có | Có | **Đặc biệt** | **Đặc biệt** |
| RTL layout | Test không bị đảo nhầm | Test không bị đảo nhầm | Test không bị đảo nhầm | Test không bị đảo nhầm | **Bắt buộc** | **Bắt buộc** |
| Bidi text lẫn số/URL | Cơ bản | Cơ bản | Cơ bản | Cơ bản | **Bắt buộc** | **Bắt buộc** |
| Overflow/zoom/accessibility | Có | Có | Có | Có | Có | Có |

“Có” nghĩa là **phải chạy test tương ứng**; nó không khẳng định locale tự nhiên phải cho chuỗi output cố định. “Đặc biệt” chỉ nhóm rủi ro cần bổ sung nhiều dữ liệu/điều kiện.

Ma trận không nên bị đóng băng vĩnh viễn. Thêm các locale khác khi thị trường mở rộng, đặc biệt chữ viết phức tạp, ngôn ngữ không phân tách từ bằng khoảng trắng, lịch không ISO và bản địa hóa số.

## 5. Test định dạng số: đừng hard-code dấu phân cách

`java.text.NumberFormat` có thể tạo formatter theo locale:

```java
NumberFormat nf = NumberFormat.getNumberInstance(locale);
nf.setGroupingUsed(true);

String shown = nf.format(12345.5);
Number parsed = nf.parse(shown);
```

**Điều cần khẳng định bằng test:** với chính formatter, dữ liệu mẫu hợp lệ phải được định dạng và parse lại thành giá trị tương đương, xét precision. Trong một test không pin JDK/CLDR/provider, không nên hard-code rằng một chuỗi `shown` luôn bằng một literal duy nhất cho mọi môi trường.

Ví dụ thường gặp:

- `en-US` thường có dấu `.` cho decimal và dấu `,` cho grouping.
- `de-DE` thường dùng dấu `,` cho decimal và dấu `.` cho grouping.
- `vi-VN` có quy ước riêng có thể khác `en-US`.
- `ar-EG` có thể dùng Arabic-Indic digits và ký hiệu phân cách bản địa, tùy runtime/config.

**Nhưng đây là mô tả quy ước, không phải oracle tuyệt đối để so exact string trên mọi JDK**. Một số separator còn là khoảng trắng Unicode không dễ nhìn thấy.

### 5.1. Không parse localized string bằng `Double.parseDouble`

`Double.parseDouble("1,5")` không có cơ chế đọc dấu thập phân của Đức. Với input người dùng tiếng Đức, dùng formatter được chọn theo locale hoặc một parser UI có contract rõ.

Đồng thời, `NumberFormat.parse` có thể chấp nhận prefix rồi dừng ở ký tự chưa hiểu. Nếu muốn validate **toàn bộ input**, dùng `ParsePosition` và kiểm tra `position.getIndex() == text.length()`, cùng điều kiện lỗi. Đó là lý do ví dụ runnable ở phần sau dùng `ParsePosition` thay vì chỉ gọi parse mơ hồ rồi coi mọi chữ là hợp lệ.

### 5.2. Giá trị tiền tệ không tự quy đổi

`NumberFormat.getCurrencyInstance(locale)` chọn cách **hiển thị** tiền theo locale; đổi locale hoặc ký hiệu tiền **không phải** đổi giá trị từ USD sang EUR. Với ứng dụng tài chính, cần có `Currency`/mã ISO rõ, tỷ giá có nguồn và thời điểm khi nghiệp vụ thực sự chuyển đổi, tính toán chính xác với `BigDecimal` và làm tròn có policy.

Trong test localization, kiểm tra hai điều độc lập: *giá trị số không đổi* và *nhãn/cách trình bày tiền tệ đúng yêu cầu*.

## 6. Test ngày giờ: localized pattern và múi giờ khác nhau

Java 17 dùng `java.time.format.DateTimeFormatter`. Để hiển thị ngày cho người dùng:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);

String text = formatter.format(LocalDate.of(2026, 10, 28));
LocalDate parsed = LocalDate.parse(text, formatter);
```

Đây là đoạn trong method với import `java.time.LocalDate`, `java.time.format.*`.

Với các locale đã chọn, test **round-trip** sẽ cho biết formatter và parser hoạt động nhất quán với cùng locale/runtime. Pattern thực tế đến từ dữ liệu locale. `FormatStyle.MEDIUM` không có nghĩa một literal cố định như `dd/MM/yyyy` ở mọi quốc gia.

Nếu UI thực sự muốn layout ngày theo vùng người dùng, dùng `ofLocalizedDate(FormatStyle...)`. Nếu sản phẩm cần một định dạng **cố định** như `uuuu-MM-dd` cho API, dùng `DateTimeFormatter.ISO_LOCAL_DATE` hoặc contract máy, **không** lấy output UI truyền thành dữ liệu giao thức.

### 6.1. Cố định ngày cho test

Không dùng `LocalDate.now()` trong test yêu cầu output cố định vì ngày có thể thay đổi theo hệ thống và timezone. Dùng:

```java
LocalDate testDate = LocalDate.of(2026, 10, 28);
```

Nếu cần test một thời điểm tuyệt đối, dùng một `Instant` cố định rồi chọn `ZoneId` **tường minh**. Ví dụ `Instant.parse("2026-10-28T07:30:00Z")` là một instant; khi hiển thị ở Việt Nam hoặc Berlin, giờ đồng hồ phụ thuộc zone, không phụ thuộc `Locale` một mình.

### 6.2. Test ở ranh giới năm và DST

Bổ sung ít nhất:

- Ngày 1 tháng 1 và 31 tháng 12 để phát hiện nhầm `YYYY` (week-based-year) với `uuuu`.
- Ngày 29 tháng 2 năm nhuận và ngày 31 tháng 2 không hợp lệ để test `ResolverStyle.STRICT`.
- Các thời điểm tại vùng có daylight saving time (DST), bao gồm thời điểm **gap/overlap** nếu tính giờ địa phương.
- Một date-only `LocalDate` không cần tự chuyển giờ theo timezone.
- Locale `ar-EG`/`he-IL` không đồng nghĩa phải dùng calendar Hijrah/Hebrew; chronology/currency/zone phải chọn theo yêu cầu.

**Không** khẳng định các locale `ar-EG` hoặc `he-IL` mặc định đổi chronology sang hệ lịch khác. `DateTimeFormatter.ofLocalizedDate` dùng ISO chronology nếu không override chronology.

## 7. Ví dụ độc lập Java 17: chạy ma trận số và ngày

Tệp `LocaleMatrixSmokeDemo.java` dưới đây dùng **sáu locale**, không đòi exact string định dạng. Nó kiểm tra **giá trị sau round-trip**, số ký tự được parser tiêu thụ và sự ổn định của date.

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleMatrixSmokeDemo {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    private static boolean numberRoundTrip(Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        format.setGroupingUsed(true);
        format.setMaximumFractionDigits(1);

        double expected = 12345.5;
        String shown = format.format(expected);

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(shown, position);

        return parsed != null
                && position.getIndex() == shown.length()
                && Math.abs(parsed.doubleValue() - expected) < 0.000001;
    }

    private static boolean dateRoundTrip(Locale locale) {
        LocalDate expected = LocalDate.of(2026, 10, 28);
        DateTimeFormatter format =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                        .withLocale(locale);

        String shown = format.format(expected);
        LocalDate parsed = LocalDate.parse(shown, format);
        return expected.equals(parsed);
    }

    public static void main(String[] args) {
        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);

            System.out.println(tag
                    + " number=" + numberRoundTrip(locale)
                    + " date=" + dateRoundTrip(locale));
        }
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac -encoding UTF-8 LocaleMatrixSmokeDemo.java
java LocaleMatrixSmokeDemo
```

Trên một JDK 17 tiêu chuẩn hỗ trợ các locale này, kết quả kỳ vọng theo test invariant là:

```text
vi-VN number=true date=true
en-US number=true date=true
de-DE number=true date=true
tr-TR number=true date=true
ar-EG number=true date=true
he-IL number=true date=true
```

Nếu một hàng không PASS, hãy ghi lại **JDK vendor/version, locale provider, locale tag, formatted string và vị trí parser dừng**, rồi điều tra. Đoạn test không coi mọi locale phải dùng cùng dấu ngăn cách hay cùng thứ tự ngày. Với sản phẩm thực, thêm test các giá trị 0, âm, số cực lớn, NaN/Infinity nếu được hỗ trợ, phần trăm và tiền tệ theo policy, chứ không chỉ một giá trị 12345.5.

**Chú ý giới hạn:** đây là smoke test, không phải chứng minh mọi pattern, mọi dữ liệu và mọi UI đã được bản địa hóa đúng. Định dạng ngày theo một calendar đặc biệt hoặc input sai cần test riêng. Để test chính xác tiền tệ, ưu tiên số học `BigDecimal` thay vì so sánh tài chính bằng `double`; `double` ở đây chỉ để minh họa round-trip số đơn giản 12345.5, một giá trị biểu diễn nhị phân chính xác.

## 8. Chữ I của tiếng Thổ Nhĩ Kỳ: test bắt buộc

Tiếng Thổ Nhĩ Kỳ có hai cặp chữ:

```text
I (U+0049)  <-->  ı (U+0131)
İ (U+0130)  <-->  i (U+0069)
```

Trong khi đó, `Locale.ROOT` và nhiều ngôn ngữ khác thường có quy tắc `I → i` cho lowercase. Vì vậy `"TITLE".toLowerCase()` có thể tạo `"tıtle"` (với dotless ı) khi default locale của JVM là tiếng Thổ, làm lookup khóa máy `"title"` thất bại.

**Chia test thành hai mục đích:**

1. Văn bản tiếng Thổ phải dùng `String.toLowerCase(trLocale)` hoặc `toUpperCase(trLocale)` với kết quả Unicode đúng.
2. **Machine identifiers** như key cấu hình/protocol ASCII phải chuẩn hóa **độc lập locale**, thường với `Locale.ROOT` và validation bộ ký tự. Không dùng default locale để xử lý mã định danh.

### Java 17 độc lập: TurkishIAssertions.java

```java
import java.util.Locale;

public class TurkishIAssertions {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        check("I-to-dotless-i",
                "I".toLowerCase(TR).equals("\u0131"));
        check("dotted-I-to-i",
                "\u0130".toLowerCase(TR).equals("i"));
        check("i-to-dotted-I",
                "i".toUpperCase(TR).equals("\u0130"));
        check("dotless-i-to-I",
                "\u0131".toUpperCase(TR).equals("I"));

        check("ROOT-machine-key",
                "TITLE".toLowerCase(Locale.ROOT).equals("title"));
        check("TR-not-machine-key",
                !"TITLE".toLowerCase(TR).equals("title"));
        check("ROOT-dotted-I-expansion",
                "\u0130".toLowerCase(Locale.ROOT)
                        .equals("i\u0307"));
    }
}
```

```bash
javac -encoding UTF-8 TurkishIAssertions.java
java TurkishIAssertions
```

Stdout kỳ vọng theo Java 17:

```text
PASS I-to-dotless-i
PASS dotted-I-to-i
PASS i-to-dotted-I
PASS dotless-i-to-I
PASS ROOT-machine-key
PASS TR-not-machine-key
PASS ROOT-dotted-I-expansion
```

Lưu ý: `"\u0130".toLowerCase(Locale.ROOT)` tạo `i` cộng combining dot above U+0307 (hai code points); còn tiếng Thổ tạo `i` duy nhất. Vì thế case conversion có thể làm **độ dài và offset của chuỗi thay đổi**. Không dùng các index tính từ chuỗi trước khi lowercase để highlight chuỗi sau mà không thiết kế mapping offsets.

`String.equalsIgnoreCase` **không nhận Locale** nên không phải thuật toán so sánh ngữ nghĩa tiếng Thổ. Khi yêu cầu sort hoặc matching theo ngôn ngữ, cân nhắc `Collator`/công cụ tìm kiếm được cấu hình locale; không dùng `equalsIgnoreCase` để chứng minh I/ı/İ/i đã được xử lý chính xác theo quy tắc sản phẩm.

## 9. Test ResourceBundle và fallback theo từng locale

Một hệ thống localization thường có family:

```text
demo/
  Messages.properties
  Messages_vi.properties
  Messages_tr.properties
  Messages_de.properties
  Messages_ar.properties
  Messages_he.properties
```

`ResourceBundle` dùng **baseName**, ví dụ `"demo.Messages"`, rồi chọn các ứng viên theo `Locale`. Việc có hay không file locale cụ thể tùy trạng thái dịch của sản phẩm.

Các tình huống test cần có:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| `getBundle(baseName, viVN)` | Dùng bundle tiếng Việt được đóng gói, hoặc fallback được công bố |
| `getBundle(baseName, enUS)` | Dùng bundle tiếng Anh/root phù hợp |
| `getBundle(baseName, deDE)` | Dùng bundle Đức nếu có; nếu chưa có, fallback chính thức |
| `getBundle(baseName, trTR)` | Không làm hỏng key khi đổi case; bản dịch tiếng Thổ đúng |
| `getBundle(baseName, arEG)` | Text Ả Rập đúng Unicode, có RTL layout ở tầng giao diện |
| `getBundle(baseName, heIL)` | Text Hebrew đúng Unicode, có RTL layout ở tầng giao diện |
| Một key bắt buộc bị thiếu | QA phát hiện; không để production hiện raw key hoặc exception vô kiểm soát |
| Thay loader/package/JAR | Vẫn tìm thấy resources trong phạm vi đúng |
| Default locale khác | Không thay đổi kết quả khi caller đã chọn locale và fallback tường minh |

### 9.1. Fallback không phải dịch chính xác

Một ứng dụng có thể fallback về `Messages.properties` tiếng Anh khi thiếu `Messages_ar.properties`. Điều đó giúp giao diện không crash, **nhưng không có nghĩa bản địa hóa tiếng Ả Rập đã đạt**. Test nên phân biệt:

- **Functional fallback PASS**: có nội dung đọc được, không bị `MissingResourceException`.
- **Translation coverage FAIL/WARNING**: thiếu bản dịch theo mức độ bắt buộc của release.

Không dùng chỉ tiêu “getString không rỗng” như chứng minh toàn bộ bộ dịch đã hoàn chỉnh. Cần so sánh key set giữa bundle gốc và các bản dịch, tìm key thiếu/không dùng nữa, kiểm tra placeholder, văn bản bị cắt và thứ tự tham số.

### 9.2. Java 17 độc lập: kiểm tra một bộ bundle mẫu

Dùng cấu trúc:

```text
project/
  src/demo/BundleLocaleMatrixDemo.java
  resources/demo/Messages.properties
  resources/demo/Messages_vi.properties
  resources/demo/Messages_tr.properties
```

Nội dung `resources/demo/Messages.properties`:

```properties
hello=Hello
```

Nội dung `resources/demo/Messages_vi.properties`:

```properties
hello=Xin chào
```

Nội dung `resources/demo/Messages_tr.properties`:

```properties
hello=Merhaba
```

Mã `src/demo/BundleLocaleMatrixDemo.java`:

```java
package demo;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLocaleMatrixDemo {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    public static void main(String[] args) {
        ClassLoader loader =
                BundleLocaleMatrixDemo.class.getClassLoader();

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle = ResourceBundle.getBundle(
                    "demo.Messages", locale, loader, control);

            System.out.println(tag + "=" +
                    bundle.getString("hello"));
        }
    }
}
```

Biên dịch, copy resources và chạy trong **classpath/unnamed module** (lệnh Bash):

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/BundleLocaleMatrixDemo.java
cp resources/demo/Messages*.properties out/demo/
java -cp out demo.BundleLocaleMatrixDemo
```

Stdout khi dùng đúng các file mẫu:

```text
vi-VN=Xin chào
en-US=Hello
de-DE=Hello
tr-TR=Merhaba
ar-EG=Hello
he-IL=Hello
```

Vì demo cố tình chỉ có resource tiếng Việt, tiếng Thổ và root tiếng Anh, ba locale `de-DE`, `ar-EG`, `he-IL` fallback về root. Đây là **minh họa fallback**, không phải mẫu release hoàn chỉnh. Khi sản phẩm yêu cầu dịch Đức/Ả Rập/Hebrew, ba locale ấy phải có coverage riêng.

**Lưu ý về Java 17:** `PropertyResourceBundle` từ Java 9 hỗ trợ UTF-8 mặc định cùng cơ chế tương thích legacy; ví dụ giả định file được lưu UTF-8 và không có cấu hình override encoding khác. `ResourceBundle.Control` không phải con đường thích hợp cho mọi cấu hình named module; với JPMS, có thể cần overload module-aware hoặc `ResourceBundleProvider`. Ví dụ ở đây cố ý chạy trên classpath.

## 10. MessageFormat, placeholder và bản dịch đảo thứ tự đối số

Một bản dịch đúng không chỉ thay từ; thứ tự từ có thể thay đổi giữa các ngôn ngữ. Với Java `MessageFormat`, nên dùng **argument indexes** như `{0}`, `{1}` thay vì nối chuỗi bằng `+`.

Ví dụ:

```text
English: "{0} sent {1} to {2}."
Other locale: "To {2}, {0} sent {1}."
```

Đây là ví dụ minh họa tái sắp xếp ý trong câu, không khẳng định đó là bản dịch tự nhiên cho mọi ngôn ngữ. Cần người dịch bản địa biên tập pattern. Mỗi bản dịch có thể đổi vị trí `{0}`/`{1}`/`{2}` nhưng vẫn phải giữ đúng **vai trò và kiểu tham số**.

### Những điều cần test

- Bản dịch có đủ những argument bắt buộc.
- Không dùng sai index, ví dụ `{3}` khi caller chỉ truyền ba đối số.
- Các loại format `number`/`date` được gán đúng loại dữ liệu.
- Dấu nháy đơn `'` và dấu ngoặc nhọn được escape theo cú pháp `MessageFormat`.
- Không nối fragment cứng trước/sau như “Hello ” rồi cộng tên người trong mọi ngôn ngữ.
- Trong HTML, nội dung tham số do người dùng cung cấp vẫn phải được **escape đúng ngữ cảnh**; `MessageFormat` không phải HTML sanitizer.
- Bản dịch dài hơn không tràn UI và không đổi thứ tự đọc RTL.

### Ví dụ Java 17 về định dạng với locale

```java
import java.text.MessageFormat;
import java.util.Locale;

// Bên trong method:
Locale german = Locale.forLanguageTag("de-DE");
MessageFormat format = new MessageFormat(
        "Wert: {0,number}", german);

String shown = format.format(new Object[]{12345.5});
```

Ở đây formatter dùng locale Đức để biểu diễn số, nhưng output của `shown` có thể khác chi tiết theo CLDR/JDK; test hợp đồng số học và ngữ nghĩa thay vì luôn so một literal nếu môi trường không được pin.

**Không dùng `MessageFormat.format(pattern, args)` tĩnh khi bạn cần một locale tường minh** mà không kiểm soát default locale. Tạo `new MessageFormat(pattern, locale)` và dùng nó trong đúng ngữ cảnh.

## 11. Collator: sort theo ngôn ngữ chứ không theo Unicode code unit

`String.compareTo` so sánh giá trị UTF-16 code units; nó không biết cách xếp từ theo ngôn ngữ. `java.text.Collator` dùng quy tắc collation của locale:

```java
Collator collator = Collator.getInstance(locale);
collator.setStrength(Collator.TERTIARY);

names.sort(collator::compare);
```

Đây là code minh họa bên trong method với biến `locale` và `names` hợp lệ, import `java.text.Collator`.

### Các mức strength

| Strength | Ý nghĩa chung | Cần kiểm thử |
| --- | --- | --- |
| `PRIMARY` | Khác biệt chữ cơ bản | Không giả định mọi dấu đều bị bỏ qua trong mọi ngôn ngữ |
| `SECONDARY` | Thêm một số khác biệt dấu | Locale có thể xem dấu là quan trọng ở mức khác |
| `TERTIARY` | Thêm khác biệt case/biến thể | Dùng khi muốn thứ tự chi tiết hơn |
| `IDENTICAL` | Độ phân biệt sâu hơn | Cần có chiến lược Unicode decomposition |

Trong tiếng Thổ, `I` và `ı` cùng một cặp case, còn `İ` và `i` là một cặp khác. `Collator` có quy tắc tiếng Thổ khác các phép ép case độc lập locale. Ở tiếng Đức, thứ tự chữ có dấu cũng chịu locale rules. Không hard-code một thứ tự chung cho tất cả locale.

### 11.1. Test Collator có độ bền tốt

- Test **phản xạ**: `collator.compare(s,s)==0`.
- Test **đối xứng dấu**: `sign(compare(a,b)) == -sign(compare(b,a))`.
- Test **bắc cầu**: nếu `a≤b` và `b≤c` thì `a≤c`.
- Test tương đương giữa `collator.compare(a,b)` và `getCollationKey(a).compareTo(getCollationKey(b))` trong **cùng Collator không đổi cấu hình**.
- Test tên thật cho từng thị trường, có người bản địa phê duyệt thứ tự kỳ vọng.
- Không lưu `CollationKey` lâu dài như một thứ tự vĩnh viễn khi JDK/provider/CLDR có thể thay đổi.

**Không đồng nhất so sánh ngôn ngữ với kiểm tra username/password hoặc mã định danh kỹ thuật**. Bảo mật và uniqueness có contract khác; collation level thấp có thể coi hai chuỗi khác nhau là bằng nhau.

## 12. RTL: hướng văn bản khác với ngôn ngữ và dữ liệu nguồn

Ngôn ngữ phải–trái (right-to-left, RTL) như tiếng Ả Rập hoặc Hebrew cần kiểm thử riêng. Có ít nhất ba cấp:

1. **Logical order:** thứ tự Unicode code points trong `String`, dùng cho lưu trữ, copy/paste và giao thức.
2. **Bidirectional reordering:** thứ tự hiển thị của các đoạn RTL/LTR sau khi áp Unicode Bidirectional Algorithm.
3. **Glyph shaping/layout:** cách chữ nối nhau, chọn glyph, đặt dấu, căn lề, icon và phân bố ô giao diện.

Java có `java.text.Bidi` hỗ trợ phân tích bidi, nhưng nó **không phải bộ dịch**, không tự “đảo cả String” và **không thay** engine render/shaping.

Một đoạn văn Ả Rập có thể chứa chữ số 1234, URL `https://example.com` và tên sản phẩm Latin. Nếu code cố `new StringBuilder(text).reverse()` để làm RTL, thứ tự logic và ý nghĩa dấu câu/cụm Unicode có thể bị hỏng.

### 12.1. Không suy direction từ toàn bộ ứng dụng một cách cứng nhắc

- `ar-EG` và `he-IL` thường dùng giao diện hướng RTL, nhưng một trường **email/URL/mã serial** bên trong vẫn cần xử lý hướng LTR thích hợp.
- Người dùng có thể chọn locale tiếng Ả Rập nhưng nhập tiếng Anh; không nên đảo ký tự input.
- `vi-VN`/`en-US`/`de-DE`/`tr-TR` thường là LTR, nhưng vẫn phải hiển thị được trích dẫn hoặc tên tiếng Ả Rập.
- Icon mũi tên điều hướng có thể cần **mirror** tùy ngữ nghĩa; icon không có ý nghĩa hướng như biểu tượng play/media hoặc logo không nhất thiết cần mirror.

### 12.2. Test văn bản trộn

Bộ dữ liệu test nên gồm:

```text
Arabic only:       مرحبا
Hebrew only:       שלום
Arabic + digits:   رقم الطلب 12345
Hebrew + Latin:    שלום Java 17
Mixed address:     demo@example.com - مرحبا
Parentheses:       (مرحبا) 123
Currency/percent:  123.45 USD / 25%
```

Các chuỗi là **dữ liệu kiểm thử**, không phải một hướng dẫn “đảo String” trước khi vẽ. Khi chụp screenshot, phải ghi rõ font, viewport, text direction, tình huống input và render engine.

### 12.3. Java 17 runnable: xác nhận dữ liệu có đặc tính RTL

Tệp `BidiSmokeDemo.java`:

```java
import java.text.Bidi;

public class BidiSmokeDemo {
    public static void main(String[] args) {
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        String hebrew = "\u05E9\u05DC\u05D5\u05DD";

        Bidi arabicBidi = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi hebrewBidi = new Bidi(
                hebrew, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("arabicRequiresBidi=" +
                Bidi.requiresBidi(
                        arabic.toCharArray(), 0, arabic.length()));
        System.out.println("hebrewRequiresBidi=" +
                Bidi.requiresBidi(
                        hebrew.toCharArray(), 0, hebrew.length()));
        System.out.println("arabicBaseRTL=" +
                !arabicBidi.baseIsLeftToRight());
        System.out.println("hebrewBaseRTL=" +
                !hebrewBidi.baseIsLeftToRight());
    }
}
```

```bash
javac -encoding UTF-8 BidiSmokeDemo.java
java BidiSmokeDemo
```

Stdout kỳ vọng:

```text
arabicRequiresBidi=true
hebrewRequiresBidi=true
arabicBaseRTL=true
hebrewBaseRTL=true
```

Demo xác nhận **đặc tính bidirectional** của hai chuỗi và cách xác định hướng cơ sở từ ký tự mạnh khi dùng default paragraph direction. Nó **không xác minh glyph Arabic có nối đúng**, checkbox bên phải hay menu đã mirror, vì những việc ấy thuộc tầng UI.

## 13. Kiểm thử giao diện RTL không thể bỏ qua

Dưới đây là ma trận test thủ công/visual regression dành cho `ar-EG` và `he-IL`:

| Vùng giao diện | Trường hợp test | Kỳ vọng |
| --- | --- | --- |
| Thanh điều hướng | Back, Next, breadcrumb | Thứ tự và hướng icon theo thiết kế RTL |
| Form | Label, text input, placeholder, validation | Căn lề đúng; không mất focus/caret |
| Trường email/URL | Nhập/chỉnh/copy URL LTR trong form RTL | Nội dung lưu và paste giữ đúng logical string |
| Giá tiền | Ký hiệu currency, số âm/dương, phần thập phân | Thứ tự phần số/ký hiệu dễ hiểu, không bị đảo byte |
| Danh sách | Thứ tự icon, bullet, số thứ tự, pagination | Hợp hướng đọc, không đổi meaning |
| Dialog/toast | Message chứa ID Latin, số và ký tự Arabic | Dấu câu/ngoặc hiển thị rõ, text không tràn |
| Bảng dữ liệu | Cột, header, sort control | Thứ tự và alignment nhất quán |
| Error state | Text validation dài, icon cảnh báo | Không che field hoặc nút submit |
| Accessibility | Screen reader, tab order | Thứ tự focus/đọc phù hợp logical flow |
| Responsive | Điện thoại nhỏ, zoom 200–400% | Không mất nội dung hoặc bị chồng chữ |

Với giao diện web, đặt `lang` và `dir` đúng ngữ cảnh; cách diễn đạt ví dụ:

```html
<div lang="ar" dir="rtl">
  <p>رقم الطلب: <bdi>ABC-1234</bdi></p>
</div>
```

`bdi` giúp cô lập một đoạn nhúng có hướng độc lập trong ngữ cảnh bidi khi phù hợp. Đây là ví dụ **HTML UI**, không phải Java code, và không tự thay mọi quy tắc CSS. Đối với input type/email hoặc component UI phức tạp, cần test chính browser/framework được dùng.

Trong Java Swing, có `ComponentOrientation.RIGHT_TO_LEFT` và các thành phần hỗ trợ orientation, nhưng không phải mọi custom-painted component tự mirror theo orientation. Cần xác nhận cả layout manager, font và text renderer.

### 13.1. Những ký tự điều khiển Bidi và bảo mật

Unicode có các **bidi formatting controls**, ví dụ U+202E RIGHT-TO-LEFT OVERRIDE, có thể khiến văn bản hiển thị khác thứ tự logical code points. Trong log, tên file, mã nguồn hoặc nội dung không đáng tin, những ký tự này có thể bị lạm dụng để che giấu thứ tự ký tự.

Đối với dữ liệu có độ nhạy bảo mật như filename, URL, mã định danh, review nội dung và audit log:

- Không tự xóa toàn bộ ký tự RTL hợp lệ của một ngôn ngữ.
- Có chính sách phát hiện/cảnh báo các bidi controls bất thường trong identifier hoặc log.
- Khi cần hiển thị nội dung người dùng trong UI, dùng **isolation/escaping đúng ngữ cảnh**.
- Hiển thị code point/escaped representation khi debug các chuỗi có khả năng gây nhầm lẫn.
- Không dựa hoàn toàn vào screenshot để chứng minh dữ liệu gốc không bị sửa.

**Bidi controls và dữ liệu RTL bình thường là hai thứ khác nhau**. Chính sách validation nên theo miền dữ liệu chứ không cấm mọi ký tự tiếng Ả Rập/Hebrew.

## 14. Unicode: dấu tiếng Việt, combining marks và emoji

Một bài QA localization cần có dữ liệu Unicode ngoài chữ ASCII:

- Tiếng Việt: `Tiếng Việt`, `Đặng`, `nghiêng`, chữ hoa/thường có dấu.
- Đức: `Straße`, `Äpfel`, `für`.
- Thổ: `İstanbul`, `Iğdır`, `ışık`.
- Ả Rập/Hebrew: text thuần và text trộn Latin/số.
- Emoji supplementary: `😀`, `🚀`.
- Dạng phân rã: `e\u0301`, cùng các dấu kết hợp tiếng Việt nếu cần.

Trong Java, `String.length()` đếm **UTF-16 code units**, không phải số code points hoặc grapheme clusters. Chữ ngoài BMP cần surrogate pair; một chữ có dấu kết hợp có thể có nhiều code points.

### Test canonical normalization

`java.text.Normalizer` có thể đưa chuỗi về `NFC` khi hợp đồng yêu cầu. Ví dụ `"\u00E9"` và `"e\u0301"` khác về code units nhưng canonically equivalent sau NFC.

Tuy nhiên, không tự normalize password, token, chữ ký hoặc các dữ liệu có contract byte-level. Normalization, case conversion, collation và bidi rendering có **mục tiêu khác nhau**, cần kiểm thử độc lập.

### Charset ở ranh giới I/O

Dữ liệu bản dịch cần được lưu/đọc với charset rõ ràng, thường là UTF-8. Một file UTF-8 được decode sai charset có thể tạo mojibake mà không phát sinh exception. `Locale.forLanguageTag("vi-VN")` **không** bảo đảm một file nguồn được mã hóa bằng UTF-8; charset phải do giao thức hoặc cấu hình dữ liệu xác định.

Khi cần phát hiện malformed UTF-8, có thể dùng `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)` thay vì dựa vào constructor `new String(bytes, UTF_8)` có khả năng replacement. Test một file chứa dấu/emoji giúp phát hiện sai đường đọc.

## 15. Chẩn đoán test thất bại: nhóm lỗi theo tầng

| Dấu hiệu | Nhóm vấn đề có thể | Bước điều tra |
| --- | --- | --- |
| `vi-VN` hiển thị `?` hoặc ký tự lạ | Encoding/font | Kiểm tra byte UTF-8, decoder và font glyph |
| `de-DE` parse `"1,5"` sai | Dùng parser máy thay locale | Kiểm tra NumberFormat/ParsePosition |
| `tr-TR` lookup key `"TITLE"` thất bại | Dùng default locale khi lower-case ID | Đổi sang ROOT/canonicalization rõ |
| `ar-EG` văn bản đúng nhưng layout LTR | Thiếu `dir`/orientation | Kiểm tra document direction và UI component |
| `he-IL` dấu ngoặc/số bị đặt lạ | Bidi embedding/isolation | Test chuỗi logical, dùng Bidi-aware engine |
| Locale mục tiêu rơi về English | ResourceBundle thiếu file/loader/fallback | Kiểm tra bundle và translation coverage |
| Ngày 03/04 bị hiểu nhầm | Pattern locale hoặc contract không rõ | Định nghĩa input format, parse strict |
| Chỉ lỗi trên container Linux | JDK/locale provider/font khác | Ghi môi trường và chụp UI thực tế |
| Text dài tràn nút | Layout cố định, translation expansion | Responsive/auto-layout, pseudo-localization |
| Test exact string thay đổi sau nâng JDK | CLDR/locale data thay đổi | Pin runtime hoặc test theo invariant |
| Sort tên khác dự kiến | Collator locale/strength khác | Kiểm tra provider và test dữ liệu bản địa |
| Timestamps lệch giờ | Nhầm Locale với ZoneId | Kiểm tra `Instant`, `ZoneId`, DST |

Một lỗi có thể xuất phát từ nhiều tầng; đừng luôn “sửa” bằng cách đổi `Locale.setDefault` hoặc ép mọi chuỗi thành lowercase. Cần xác định lỗi thuộc **formatting, parsing, resource loading, encoding, text processing hay layout**.

## 16. Test dữ liệu sai, biên và các đường lỗi

Đối với mỗi locale, ngoài happy path hãy có:

**Number:**

- `0`, số âm, phần thập phân, số lớn có grouping.
- Input thiếu/méo dấu phân cách, chuỗi có ký tự lạ ở cuối.
- Percent, currency cùng mã tiền thực tế, negative sign và precision.
- Đầu vào người dùng có spaces Unicode, Arabic digit shaping, hoặc ký tự hai chiều nếu sản phẩm cho phép.

**Date/time:**

- Ngày nhuận, ngày không tồn tại, chuyển năm, DST gap/overlap.
- `LocalDate` so với `Instant`, timezone tường minh và date style.
- Parse strict với `uuuu` khi input có pattern cố định.
- Dữ liệu API dùng ISO để tránh diễn giải mơ hồ.

**Resource/text:**

- Missing bundle, missing key, placeholder thiếu/sai index.
- Ký tự escape trong `MessageFormat`, ký hiệu HTML, emoji.
- Trường không có bản dịch và trường có bản dịch dài hơn 2–3 lần.
- Fallback đã được thiết kế có chủ đích.

**RTL and UI:**

- Nút điều hướng, bảng, form, notification, modal, keyboard tab order.
- Chuỗi trộn code, email, số, dấu ngoặc và script RTL.
- Resize, zoom, rotation thiết bị, font lớn, thiếu glyph.
- Screen reader, copy/paste và selection đúng logical text.

**Khác nhau giữa hai loại kiểm thử:** một check Java xác nhận `Bidi.requiresBidi` trả true không thể chứng minh một modal đã căn nội dung đúng. Ngược lại, screenshot đẹp không chứng minh backend không làm mất code points. Cần cả functional assertions lẫn UI/visual checks.

## 17. Pseudo-localization: bổ sung cho ma trận locale thật

Pseudo-localization là việc biến văn bản để mô phỏng bản dịch, ví dụ thêm dấu, kéo dài text hoặc ký tự RTL giả lập. Nó hữu ích để tìm:

- String hard-coded chưa chuyển qua resource bundle.
- Khung/chiều rộng UI quá chật.
- Truncation trong button/menu, line height và text clipping.
- Đường dẫn layout phụ thuộc số chữ tiếng Anh.

**Nhưng pseudo-localization không thay thế** bản dịch thật và native linguistic review. Một chuỗi “English kéo dài” không thể kiểm chứng quy tắc chữ I tiếng Thổ, collation tiếng Đức, dấu tiếng Việt hay bidi shaping tiếng Ả Rập.

Có thể chạy **pseudo-locale mở rộng** như một cột phụ, nhưng sáu locale thật trong bài vẫn phải có test riêng.

## 18. Viết assertion bền vững: tách invariant và snapshot

Không phải mọi test locale đều nên so exact text.

### 18.1. Những assertion nên ổn định

- Cùng numeric value khi format/parse hợp lệ với cùng NumberFormat, đủ precision.
- Cùng `LocalDate` khi format/parse bằng cùng formatter.
- Các mapping `I/ı/İ/i` tiếng Thổ theo Java 17.
- `"TITLE".toLowerCase(Locale.ROOT)` luôn là `"title"`, bất kể default JVM.
- Chuỗi nguồn Unicode không mất code points sau encode/decode UTF-8 hợp lệ.
- Bundle key bắt buộc có thể load và không rỗng.
- Bidi utility nhận diện một chuỗi tiếng Ả Rập/Hebrew thuần có hướng RTL.

### 18.2. Những snapshot cần pin môi trường

- Chuỗi chính xác của `NumberFormat`, `DateTimeFormatter.ofLocalizedDate`, `Currency`, tên tháng.
- Pattern và ký hiệu grouping/decimal do CLDR/provider trả về.
- Text sort order theo `Collator` khi provider thay đổi.
- Screenshot visual RTL phụ thuộc font/OS, CSS/renderer, DPI và browser.
- Hiển thị emoji, combining marks và fallback glyph.

Nếu hệ thống **yêu cầu output exact** (chẳng hạn một báo cáo quy định phải theo một pattern), cần định nghĩa pattern/format tường minh, version/pin môi trường và test literal. Nếu chỉ cần tuân quy ước locale, đừng lấy một snapshot máy dev làm “chân lý vĩnh viễn”.

### 18.3. Ghi môi trường khi báo lỗi

Khi một test locale fail, nên ghi:

```text
Locale tag:   tr-TR
Java version: 17.x (vendor/build cụ thể)
Locale provider: CLDR/COMPAT/config liên quan
ZoneId:       explicit setting
Font/renderer: (với test UI)
Input value:  Unicode escaped, đã lọc thông tin nhạy cảm
Actual/expected: loại so sánh và lý do bất biến
```

Đây là ví dụ **thông tin cần thu thập**, không phải output của một lệnh Java. Không log password/token hoặc toàn bộ PII khi debug.

## 19. Thiết kế test suite và chiến lược CI

### 19.1. Phân lớp kiểm thử

| Lớp test | Mục tiêu | Đặc tính |
| --- | --- | --- |
| Unit | Casing, format/parse, fallback/key contract | Chạy nhanh, dữ liệu cố định |
| Integration | Load resources từ JAR/module, I/O UTF-8 | Gần môi trường production |
| Component UI | Orientation, text overflow và interaction | Kiểm tra rendering engine của app |
| E2E | Người dùng đổi locale, nhập form, nhận email/report | Kiểm tra nhiều tầng |
| Visual regression | So sánh screenshot tại width/font cố định | Pin font/browser và review RTL |
| Native review | Dịch tự nhiên và thứ tự sắp xếp theo ngôn ngữ | Người thông thạo ngôn ngữ phê duyệt |
| Accessibility | Screen reader, focus/tab order, zoom | Không chỉ kiểm tra screenshot |

### 19.2. Quản lý test matrix để không bùng nổ tổ hợp

Sáu locale × nhiều browser × nhiều viewport × nhiều timezone × nhiều currency tạo số lượng tổ hợp lớn. Có thể:

1. Chạy unit matrix cho **mọi locale** trong mỗi pull request.
2. Chạy smoke UI ít nhất một LTR và **cả hai RTL** ở kích thước chính.
3. Chạy visual regression trên các màn quan trọng và các locale rủi ro cao.
4. Chạy full matrix theo lịch hoặc trước release.
5. Chạy targeted tests khi thay đổi thư viện i18n, CLDR/JDK, font, CSS, resource loader.

Không bỏ hẳn `tr-TR` hay RTL vì “sản phẩm hiện ít người dùng”: đây là những locale **rất dễ phát hiện lỗi giả định ngầm của code**.

### 19.3. Dữ liệu mẫu phải thật và có tính đối kháng

Ngoài dữ liệu đơn giản, cần đặt tên chứa dấu, tên dài, ký tự tổ hợp, chuỗi trộn script, dấu ngoặc/URL trong RTL. Chọn ví dụ có chủ đích:

```text
vi-VN:  Nguyễn Thị Minh Anh
de-DE:  Straße, München
tr-TR:  İstanbul, Iğdır
ar-EG:  مرحبا Java 17 - 12345
he-IL:  שלום ABC-123
Unicode: e + U+0301, U+1F600
```

Không phải đây là bộ corpus ngôn ngữ đầy đủ. Test ngôn ngữ thực tế cần chuyên gia bản địa xác nhận lựa chọn từ, hướng layout và case/ordering expected.

## 20. Một chương trình Java 17 tổng hợp kiểm tra bất biến

Dưới đây là ví dụ độc lập **không dùng JUnit**, phù hợp làm smoke check nhỏ trong build nếu muốn. Nó kiểm tra các điều kiện bất biến không dựa vào exact localized output.

Tệp `LocaleMatrixAssertions.java`:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleMatrixAssertions {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            nf.setMaximumFractionDigits(1);
            String shownNumber = nf.format(12345.5);

            ParsePosition pos = new ParsePosition(0);
            Number parsedNumber = nf.parse(shownNumber, pos);

            check(parsedNumber != null
                    && pos.getIndex() == shownNumber.length()
                    && parsedNumber.doubleValue() == 12345.5,
                    tag + " number");

            LocalDate date = LocalDate.of(2026, 10, 28);
            DateTimeFormatter df =
                    DateTimeFormatter.ofLocalizedDate(
                            FormatStyle.MEDIUM).withLocale(locale);

            check(LocalDate.parse(df.format(date), df).equals(date),
                    tag + " date");

            check(!shownNumber.isEmpty(),
                    tag + " formatting missing");
            System.out.println(tag + ":PASS");
        }

        Locale tr = Locale.forLanguageTag("tr-TR");
        check("I".toLowerCase(tr).equals("\u0131"),
                "Turkish I");
        check("i".toUpperCase(tr).equals("\u0130"),
                "Turkish i");
        check("TITLE".toLowerCase(Locale.ROOT).equals("title"),
                "Machine key");
        System.out.println("case:PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocaleMatrixAssertions.java
java LocaleMatrixAssertions
```

Với Java 17 tiêu chuẩn và locale data được cung cấp cho sáu tag, expected stdout là:

```text
vi-VN:PASS
en-US:PASS
de-DE:PASS
tr-TR:PASS
ar-EG:PASS
he-IL:PASS
case:PASS
```

Test này không thay thế JUnit, không kiểm tra translator quality, UI RTL, money conversion, DST hay style exact. Nó chỉ đảm bảo một tập các API i18n cơ bản hoạt động nhất quán trên runtime đang chạy.

Để dùng làm CI nghiêm túc, đưa từng điều kiện vào JUnit 5 parameterized test để báo lỗi riêng theo locale và case. JUnit không đi kèm JDK 17 nên phải khai báo test dependency riêng (Maven/Gradle), không coi code import JUnit là chương trình chạy với `javac` thuần nếu chưa thêm classpath.

## 21. Các lỗi và hiểu lầm thường gặp

| Hiểu lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Chạy en-US là đủ.” | Locale khác có dấu/số/case/RTL khác | Chạy ma trận đa locale |
| “tr-TR khác en-US chỉ ở từ dịch.” | Turkish I có case mapping khác | Test I/ı/İ/i rõ ràng |
| “Mọi số parse được bằng Double.parseDouble.” | Parser máy không theo dấu địa phương | NumberFormat/contract UI |
| “Việt Nam và Đức đều dùng cùng mẫu ngày.” | Pattern phụ thuộc locale/JDK | Dùng localized formatter và test |
| “Locale tự quyết định timezone.” | Locale và ZoneId độc lập | Chọn zone tường minh |
| “Ả Rập/Hebrew chỉ cần text dịch, không cần đổi layout.” | RTL ảnh hưởng navigation, input, bidi | Test UI thực tế |
| “Muốn RTL thì đảo String.” | Phá logical order và Unicode | Dùng Bidi-aware renderer |
| “String.length = số ký tự nhìn thấy.” | Đếm UTF-16 code units | Test code points/graphemes riêng |
| “Đủ key là đủ dịch.” | Fallback có thể che thiếu translation | Theo dõi coverage |
| “Collator giống compareTo.” | Collation theo ngôn ngữ | Test với locale thật |
| “Snapshot localized output luôn cố định.” | CLDR/provider/JDK có thể đổi | Pin môi trường hoặc test invariant |
| “Dữ liệu RTL hợp lệ luôn là bidi control độc hại.” | Chữ Ả Rập/Hebrew hợp lệ là dữ liệu ngôn ngữ | Policy validation theo ngữ cảnh |
| “Pseudo-localization thay được native QA.” | Không chứng minh đúng nghĩa/culture | Kết hợp pseudo và native review |
| “SetDefault locale theo request không có tác dụng phụ.” | Default dùng chung toàn JVM | Truyền locale tường minh |
| “Screen đẹp là test pass.” | Có thể sai parsing/encoding/Unicode | Cần cả assertion và UI test |

## 22. Bài tập và đáp án

**Bài 1.** Tại sao `"TITLE".toLowerCase()` có thể làm hỏng một key map trong môi trường `tr-TR`?

**Đáp án:** Overload không đối số phụ thuộc JVM default locale; tiếng Thổ chuyển chữ `I` thành dotless `ı`. Key `"tıtle"` không bằng `"title"`. Với identifier kỹ thuật ASCII, dùng một hợp đồng canonicalization độc lập locale như `Locale.ROOT`.

**Bài 2.** Một bài test `de-DE` so `NumberFormat.getNumberInstance(de).format(12345.5)` với một literal chính xác. Vì sao nó có thể bị lỗi sau khi nâng JDK?

**Đáp án:** Separator, dấu cách hoặc locale data có thể thay theo provider/CLDR. Nếu app chỉ yêu cầu hành vi bản địa, test giá trị và parse round-trip; nếu cần literal chính xác, pin environment/format contract.

**Bài 3.** `ar-EG` và `he-IL` đã hiển thị đúng bản dịch. Có đủ để kết luận UI RTL đạt không?

**Đáp án:** Không. Còn phải test navigation, icon direction, form, text trộn số/email, dấu câu, caret, font/shaping, zoom và accessibility.

**Bài 4.** Vì sao không dùng `new StringBuilder(arabicText).reverse()` để “đổi sang RTL”?

**Đáp án:** RTL là quy tắc bố trí bidirectional, không phải đảo logical Unicode code units; reverse có thể phá chữ, dấu và dữ liệu.

**Bài 5.** Khi dùng `ResourceBundle`, locale `he-IL` nhận text `Hello` từ root bundle. Test nào PASS, test nào có thể FAIL?

**Đáp án:** Có thể PASS về fallback/không crash; translation coverage Hebrew vẫn FAIL nếu release bắt buộc tiếng Hebrew.

**Bài 6.** Một `LocalDate` được format cho `vi-VN` và `en-US` rồi parse lại bằng formatter tương ứng. Giá trị ngày có nên thay đổi không?

**Đáp án:** Không. Đây là hai cách trình bày cùng một ngày; test round-trip phải giữ giá trị `LocalDate`.

**Bài 7.** Người dùng tiếng Ả Rập nhập mã `ABC-123`. Có cần đảo ký tự trong database vì UI đang RTL không?

**Đáp án:** Không. Lưu logical value, dùng bidi isolation/orientation ở tầng hiển thị theo nhu cầu.

**Bài 8.** Thay locale thành `tr-TR` thì `Collator` và `String.equalsIgnoreCase` có tương đương ngữ nghĩa không?

**Đáp án:** Không. `Collator` dùng quy tắc so sánh theo locale, `equalsIgnoreCase` không nhận locale và không thay thế collation tiếng Thổ.

**Bài 9.** Vì sao ấn định `Locale.setDefault(ar)` trong một request không phải cách kiểm thử/triển khai đa ngôn ngữ tốt?

**Đáp án:** Default locale là trạng thái JVM dùng chung, có thể ảnh hưởng các request khác. Dùng locale tường minh và test cô lập nếu muốn kiểm tra overload phụ thuộc default.

**Bài 10.** Một chuỗi địa danh tiếng Việt có dạng composed và decomposed giống mắt thường. `String.equals` có tự nhận là bằng nhau không?

**Đáp án:** Không. Java so code units; nếu contract yêu cầu canonical equivalence, chuẩn hóa Unicode `NFC` trước khi so sánh, nhưng không tự normalize dữ liệu nhạy cảm ngoài contract.

**Bài 11.** Test `BidiSmokeDemo` PASS có chứng minh UI Arabic trong Android/web/Swing render chính xác không?

**Đáp án:** Không. Nó chỉ kiểm tra thuật toán bidi ở dữ liệu chữ; cần kiểm thử rendering, fonts, direction và thao tác UI.

**Bài 12.** Có một sản phẩm sắp mở thị trường mới dùng lịch không ISO. Có nên chỉ thêm locale trong ma trận là đủ?

**Đáp án:** Không. Cần thêm các biến thể calendar/chronology, số, zone, resource bundle, font và test domain-specific; locale language-region không tự quyết định tất cả.

## 23. Checklist trước khi phát hành

- [ ] Mọi locale được hỗ trợ có resource bundles và coverage dịch theo tiêu chí release.
- [ ] Tên key/placeholder nhất quán, fallback được kiểm soát.
- [ ] Unit test định dạng số/ngày chạy với `vi-VN`, `en-US`, `de-DE`, `tr-TR`, `ar-EG`, `he-IL`.
- [ ] Test Turkish I/ı/İ/i và bảo đảm identifier kỹ thuật độc lập locale.
- [ ] Không dùng localized number/date string làm giao thức máy không có contract.
- [ ] Currency/Chronology/ZoneId được chọn tường minh khi nghiệp vụ cần.
- [ ] Collation được kiểm thử với dữ liệu bản địa, không dùng `String.compareTo` thay thế.
- [ ] Có UI test trực quan cho cả Arabic và Hebrew với chuỗi trộn Latin/số/URL.
- [ ] Form RTL hoạt động đúng khi caret, copy/paste và validation.
- [ ] Font được hỗ trợ, text không tràn khi dịch dài hoặc zoom.
- [ ] Test Unicode, combining marks, emoji và UTF-8.
- [ ] Không dựa vào JVM default locale cho logic đa người dùng.
- [ ] Ghi Java version/provider/font khi debug các snapshot thay đổi.
- [ ] Có accessibility QA và native linguistic review.
- [ ] Unit, integration, UI/E2E và visual regression phối hợp, không chỉ một loại test.

## 24. Tổng kết

**Ma trận locale là công cụ phát hiện giả định sai của ứng dụng, không phải danh sách bản dịch cần hiển thị.** Với Java 17, hãy bắt đầu từ `vi-VN`, `en-US`, `de-DE`, `tr-TR` và ít nhất hai ngôn ngữ RTL như `ar-EG`, `he-IL`.

Chạy các assertion **đúng loại**: round-trip number/date, Unicode casing Thổ Nhĩ Kỳ, bundle fallback/key contract, collation theo locale và encoding đúng. Bên cạnh đó, phải kiểm tra **rendering thực tế** cho RTL, font, diacritics, bidi/selection, overflow và accessibility. Tránh hard-code exact localized strings khi không pin dữ liệu JDK/CLDR; dùng chính xác các literal khi API/protocol có contract rõ.

Nếu cần một nguyên tắc duy nhất: **giá trị nghiệp vụ, ngôn ngữ hiển thị, direction UI và dữ liệu giao thức phải được tách biệt; mỗi lớp cần test phù hợp.**

### Tham khảo API Java SE 17

- [Locale — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [NumberFormat — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [DateTimeFormatter — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [ResourceBundle — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Collator — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Bidi — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html)
- [String — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Unicode Bidirectional Algorithm (UAX #9)](https://www.unicode.org/reports/tr9/)
