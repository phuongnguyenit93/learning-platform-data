# Thay đổi tên, ký hiệu, dấu phân nhóm hoặc khoảng trắng sau nâng cấp JDK

## 1. Tại sao chỉ nâng cấp JDK mà văn bản đã khác?

Một ứng dụng Java có thể **không thay đổi mã nguồn**, vẫn dùng `Locale.FRANCE`, `NumberFormat` và `DateTimeFormatter` như trước, nhưng sau nâng cấp JDK lại tạo chuỗi khác. Tên ngôn ngữ, tên vùng, tên tháng, ký hiệu tiền tệ, dấu thập phân, dấu phân nhóm, loại chữ số và **ký tự khoảng trắng Unicode** đều có thể do **dữ liệu locale** của runtime quyết định.

Ví dụ cùng giá trị số `1234567.89` có thể được trình bày khác nhau tùy locale:

```text
en-US: 1,234,567.89
de-DE: 1.234.567,89
fr-FR: 1 234 567,89
vi-VN: 1.234.567,89
```

Trong dòng `fr-FR` ở ví dụ, các dấu phân nhóm giống khoảng trắng nhưng là **U+202F NARROW NO-BREAK SPACE**, không phải U+0020 ASCII SPACE. Dữ liệu ở runtime/phiên bản khác có thể sử dụng ký tự khác; không được coi bảng ví dụ này là một hợp đồng ổn định của mọi bản JDK.

Một bản dịch sẵn trong `ResourceBundle` của dự án không tự đổi chỉ vì JDK cập nhật. Vấn đề tập trung ở những văn bản mà **JDK sinh từ locale data**, không phải mọi chuỗi trong ứng dụng.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa **JDK, CLDR, locale provider và phiên bản dữ liệu**.
2. Nhận diện thay đổi ở **display names**, **currency symbols**, **number/date patterns**, **grouping separators** và **whitespace Unicode**.
3. Hiểu lý do snapshot tests, parser dữ liệu cũ, tìm kiếm và so sánh chuỗi có thể lỗi sau nâng cấp.
4. Dùng Java 17+ để **in code points** và dựng một bản chụp hiện trạng locale trước/sau nâng cấp.
5. Thiết kế **lưu trữ không phụ thuộc chuỗi hiển thị**; đặt locale, currency, numbering system và zone rõ ràng.
6. Phân biệt việc cần sửa **định dạng lưu trữ** với việc **cho phép dữ liệu hiển thị thay đổi** theo chuẩn locale mới.
7. Lập kế hoạch migration, kiểm thử hồi quy và chấp nhận cập nhật JDK mà không phải khóa toàn bộ ứng dụng vào dữ liệu locale cũ.

## 2. Nguồn dữ liệu: CLDR không phải toàn bộ API Java

**CLDR** (Common Locale Data Repository) do Unicode Consortium duy trì, cung cấp các quy ước và bản dịch locale, ví dụ:

- tên ngôn ngữ, lãnh thổ, hệ chữ và các mục hiển thị theo locale;
- tên ngày trong tuần, tháng, giai đoạn sáng/chiều và format date/time;
- số thập phân, phần trăm, tiền tệ, các dấu, pattern và numbering systems;
- một số quy tắc dựa vào vùng như đầu tuần và số ngày tối thiểu trong tuần đầu;
- dữ liệu liên quan cách trình bày giờ và tên múi giờ.

JDK sử dụng một **phiên bản** của dữ liệu CLDR để triển khai nhiều API nhạy locale trong `java.util`, `java.text` và `java.time`. **Một phiên bản JDK lớn mới có thể tích hợp bản CLDR mới**, nên nội dung đầu ra thay đổi là điều có thể xảy ra. Thậm chí khi vẫn dùng cùng CLDR, provider được chọn và cấu hình runtime cũng có thể ảnh hưởng kết quả.

Tuy nhiên, không phải mọi lớp quốc tế hóa đều được lấy dữ liệu đầy đủ trực tiếp từ CLDR. Theo trang Supported Locales của Oracle JDK, dữ liệu `BreakIterator` và `Collator` có những giới hạn/nguồn riêng, nên đừng nói "nâng cấp CLDR chắc chắn thay mọi quy tắc so sánh/ngắt từ". Cần kiểm tra từng API.

### Ví dụ lịch sử các bản JDK và CLDR

Theo tài liệu JDK về `LocaleServiceProvider`:

| Dòng JDK | CLDR tích hợp theo tài liệu Oracle |
| --- | --- |
| JDK 17 | CLDR 39 |
| JDK 18 | CLDR 39 |
| JDK 19 | CLDR 41 |
| JDK 20 | CLDR 42 |
| JDK 21 | CLDR 43 |
| JDK 22 | CLDR 44 |
| JDK 23 | CLDR 45 |

Đây là **mốc tham khảo lịch sử**, không phải cách suy ra phiên bản CLDR của mọi build Java trong tương lai. Nhà phân phối JDK, bản cập nhật, backport và locale provider có thể ảnh hưởng hành vi thực tế. Khi cần xác nhận, đọc release notes/tài liệu của **bản JDK cụ thể** được triển khai và chạy probe trên chính runtime đó.

### Ba mốc chuyển đổi đáng nhớ

1. **JDK 9:** CLDR trở thành nguồn locale data ưu tiên theo mặc định (JEP 252). Hệ thống từ Java 8 chuyển lên Java 9+ có thể thấy chuỗi định dạng đổi dù API không đổi.
2. **JDK 21:** khi chỉ định `JRE`/`COMPAT` legacy provider, runtime có cảnh báo về kế hoạch loại bỏ.
3. **JDK 23:** legacy locale data provider `JRE`/`COMPAT` **đã bị loại bỏ**; thêm tên đó vào `java.locale.providers` không còn giúp quay lại định dạng JDK 8.

Vì thế lời khuyên "nếu sai thì cứ thêm `-Djava.locale.providers=COMPAT`" chỉ có hiệu lực trong một số phiên bản cũ và không phải chiến lược di trú lâu dài cho JDK 23+.

## 3. Locale provider và cấu hình khởi động

Một ứng dụng có thể lấy dữ liệu locale từ các provider:

| Provider | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| `CLDR` | Dữ liệu CLDR đi cùng JDK | Mặc định trong các JDK hiện đại |
| `HOST` | Một số cấu hình/ngôn ngữ từ hệ điều hành, nếu platform hỗ trợ | Không có trên mọi runtime; khác nhau giữa máy |
| `SPI` | Dữ liệu do ứng dụng/thư viện cung cấp qua service-provider interfaces | Cần thiết kế/đăng ký provider |
| `COMPAT`/`JRE` | Locale data legacy tương thích Java 8 | **Không còn được cung cấp từ JDK 23** |

Thứ tự provider có thể chọn qua system property:

```bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
java -Djava.locale.providers=HOST,CLDR -cp . LocaleDataProbe
```

Ví dụ hai lệnh nhằm **so sánh provider khi provider HOST có hỗ trợ**; chúng không đảm bảo kết quả khác nhau. Với ứng dụng modular, classpath/module path và cách đóng gói có thể khác.

**Điểm cần nhớ:** `java.locale.providers` nên được đặt trên **lệnh khởi động JVM**; API đọc/cached cấu hình provider trong quá trình khởi tạo. Gọi `System.setProperty("java.locale.providers", ...)` trong lúc chương trình đang chạy không phải cách chuyển provider an toàn hay được bảo đảm.

Không nhầm `java.locale.providers` với `user.language`, `user.country` hoặc `Locale.setDefault(...)`. Một thứ chọn **nguồn dữ liệu locale**, các thứ khác ảnh hưởng **locale mặc định**. Thay locale mặc định toàn JVM theo từng HTTP request vẫn có thể gây race condition; hãy truyền `Locale` tường minh vào formatter.

## 4. Những loại văn bản có thể thay đổi

### 4.1. Tên ngôn ngữ, quốc gia và hệ chữ

Các API như:

```java
locale.getDisplayLanguage(displayLocale);
locale.getDisplayCountry(displayLocale);
locale.getDisplayScript(displayLocale);
locale.getDisplayName(displayLocale);
```

đọc tên đã địa phương hóa. Cách viết, dấu câu, chữ hoa, tên chính trị/địa lý được chấp nhận và thuật ngữ có thể được cập nhật theo CLDR. Thay đổi có thể là **nội dung dịch**, không phải thay đổi giá trị của `Locale`.

Ví dụ:

```text
Locale.forLanguageTag("de-DE") → mã vẫn là de-DE
Tên hiển thị tiếng Anh       → có thể là German / Germany theo thành phần
Tên hiển thị tiếng Đức       → có thể là Deutsch / Deutschland theo thành phần
```

**Đừng dùng `getDisplayName()` làm khóa dữ liệu.** Mã ngôn ngữ BCP 47 hoặc mã quốc gia theo hợp đồng dữ liệu thích hợp hơn, trong khi display name chỉ phục vụ UI. Danh sách lựa chọn ngôn ngữ nên lưu giá trị dạng tag/mã; tên hiển thị có thể cập nhật theo runtime và quyết định sản phẩm.

### 4.2. Tên tháng, thứ, thời điểm trong ngày

`DateTimeFormatter.ofLocalizedDate(...)`, `ofLocalizedTime(...)`, `DateFormat` và `DateFormatSymbols` có thể phụ thuộc locale data. Một phiên bản mới có thể thay tên tháng rút gọn, dấu phân cách, thứ tự trường, khoảng trắng hoặc mẫu thời gian 12/24 giờ.

Ví dụ Oracle Migration Guide mô tả `Locale.UK` định dạng ngày trung bình kiểu cũ `19-Mar-2024` ở JDK 8, trong khi dữ liệu CLDR ở JDK 9 sử dụng `19 Mar 2024`. Một dấu gạch nối đổi thành khoảng trắng đã đủ làm test snapshot hoặc parser dựa trên một pattern cố định sai.

Đây là ví dụ **lịch sử được Oracle tài liệu hóa**, không khẳng định mọi locale hoặc mọi ngày đều đổi chính xác theo cách đó.

### 4.3. Số và dấu thập phân/phân nhóm

`NumberFormat` và `DecimalFormatSymbols` chọn ký tự theo locale:

- `getDecimalSeparator()`: dấu phần thập phân.
- `getGroupingSeparator()`: dấu phân nhóm.
- `getZeroDigit()`: ký tự zero đại diện của hệ chữ số.
- Các factory `getNumberInstance`, `getPercentInstance`, `getCurrencyInstance` sử dụng nhiều pattern/biến thể khác.

Không có quy tắc toàn cầu "dấu phẩy là dấu thập phân". Trong `en-US`, `1,234.50` thường dùng `,` làm grouping; trong `de-DE`, `1.234,50` thường có nghĩa tương đương. Với `ar-EG`, ký tự chữ số và dấu nhóm có thể khác hoàn toàn Latin.

### 4.4. Khoảng trắng Unicode

Một số dấu nhìn giống nhau nhưng **code point khác**:

| Ký tự | Mã Unicode | Tên | Ghi chú |
| --- | --- | --- | --- |
| ` ` | U+0020 | SPACE | Dấu cách ASCII |
| ` ` | U+00A0 | NO-BREAK SPACE (NBSP) | Không cho phép xuống dòng tại khoảng này |
| ` ` | U+202F | NARROW NO-BREAK SPACE (NNBSP) | Khoảng trắng hẹp, không ngắt dòng |
| ` ` | U+2009 | THIN SPACE | Khoảng trắng mảnh, không đồng nghĩa các ký tự trên |

Nếu chỉ nhìn UI hoặc diff text không hiển thị ký tự vô hình, người kiểm thử có thể cho rằng hai chuỗi bằng nhau, nhưng `String.equals` vẫn trả `false`. `replace(" ", "")` chỉ xử lý **U+0020**, không loại mọi loại Unicode spacing; việc cố thay mọi khoảng trắng cũng có thể phá **quy tắc ngắt dòng và ý nghĩa số**.

### 4.5. Ký hiệu tiền tệ

`Currency.getInstance("USD").getCurrencyCode()` là mã ISO currency, còn `getSymbol(locale)` là **chuỗi trình bày có thể phụ thuộc locale/provider**. Đôi khi một ký hiệu ngắn không đủ phân biệt nhiều loại dollar; việc hiển thị có thể đổi thành dạng có tiền tố hoặc khác khoảng trắng.

Đừng lưu ký hiệu `$`/`€` làm định danh tiền tệ. Lưu **mã currency** và **giá trị decimal có schema**, rồi dùng `NumberFormat.getCurrencyInstance(locale)` để hiển thị, gọi `setCurrency(currency)` khi loại tiền giao dịch khác mặc định của locale. Số chữ số phần lẻ, currency rounding và pattern cũng cần tuân thủ domain; không suy chỉ từ ký hiệu nhìn thấy.

## 5. Ví dụ Java 17+: probe số, ký hiệu và Unicode code point

Một cách tin cậy để điều tra sau nâng cấp là **in code point của từng dấu** thay vì chỉ in chuỗi nhìn thấy. Tạo file `LocaleDataProbe.java`:

```java
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleDataProbe {
    static String codePoint(char ch) {
        return String.format(Locale.ROOT, "U+%04X", (int) ch);
    }

    static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    static void inspect(String tag) {
        Locale locale = Locale.forLanguageTag(tag);
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        String value = formatter.format(1234567.89);
        System.out.println("[" + tag + "]");
        System.out.println("decimal: "
                + codePoint(symbols.getDecimalSeparator()));
        System.out.println("group: "
                + codePoint(symbols.getGroupingSeparator()));
        System.out.println("zero: "
                + codePoint(symbols.getZeroDigit()));
        System.out.println("number code points: " + codePoints(value));
    }

    public static void main(String[] args) {
        System.out.println("java: " + Runtime.version());
        System.out.println("providers: " + System.getProperty(
                "java.locale.providers", "<default>"));

        for (String tag : new String[] {
                "en-US", "de-DE", "fr-FR", "ru-RU",
                "vi-VN", "ar-EG"
        }) {
            inspect(tag);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocaleDataProbe.java
java -Djava.locale.providers=CLDR LocaleDataProbe
```

Kết quả **tham chiếu** trên một JDK 24 sử dụng CLDR đã chạy thử (phần version/properties tùy runtime):

| Locale | Decimal | Group | Zero digit |
| --- | --- | --- | --- |
| `en-US` | U+002E | U+002C | U+0030 |
| `de-DE` | U+002C | U+002E | U+0030 |
| `fr-FR` | U+002C | **U+202F** | U+0030 |
| `ru-RU` | U+002C | **U+00A0** | U+0030 |
| `vi-VN` | U+002C | U+002E | U+0030 |
| `ar-EG` | U+066B | U+066C | U+0660 |

Đây **không phải bảng giá trị bất biến cho mọi JDK**: chính mục đích của probe là cho phép bạn chạy trên **JDK cũ và JDK mới**, rồi so output thực tế. `NumberFormat` ở đây đặt hai chữ số thập phân để kết quả kiểm thử dễ đối chiếu, không phải vì mọi locale bắt buộc hai chữ số.

Với `fr-FR`, chuỗi `1234567.89` ở runtime tham chiếu cho kết quả code points:

```text
[U+0031, U+202F, U+0032, U+0033, U+0034, U+202F,
 U+0035, U+0036, U+0037, U+002C, U+0038, U+0039]
```

Tại đây U+202F xuất hiện hai lần và U+002C là dấu thập phân. Khi bug report nói "dấu cách bị đổi", hãy đính kèm **code point trace**, Java version, provider, locale tag và đoạn format thực tế; đừng chỉ gửi ảnh.

## 6. Ví dụ thay đổi khoảng trắng AM/PM khi nâng cấp JDK

Một trường hợp thực tế đã được tài liệu hóa: **JDK 20** tích hợp CLDR 42, trong đó các mẫu date/time của một số locale đã đổi **dấu cách trước day period (AM/PM)** từ U+0020 thông thường sang **U+202F**. Spring Framework cũng lưu ý thay đổi này có thể làm các ứng dụng parse/format ngày giờ theo pattern mặc định gặp lỗi hoặc khác snapshot.

Hai chuỗi có thể trông gần giống:

```text
"8:30 PM"   — giữa 30 và PM là U+0020
"8:30 PM"   — giữa 30 và PM là U+202F
```

Không khẳng định tất cả locale/JDK đều in đúng mẫu `8:30 PM`: **điểm kiểm thử là mã ký tự separator**, không phải một format cố định toàn cầu. Tên ngày, phần AM/PM và cách viết còn tùy locale/pattern.

### Vì sao lỗi nguy hiểm?

- Parser ứng dụng đang dùng pattern literal với U+0020 sẽ không tự nhiên tương đương U+202F trong mọi trường hợp.
- Code lưu chuỗi ngày giờ đã địa phương hóa rồi parse sau nâng cấp có thể gặp `DateTimeParseException`.
- Unit test `assertEquals("8:30 PM", actual)` có thể thất bại dù người dùng vẫn nhìn thấy văn bản hợp lý.
- HTML, màn hình và PDF có thể xử lý **line breaking khác nhau**, vì U+202F là không ngắt dòng.
- Hệ thống nhận input từ mobile cũ có thể gửi U+0020 còn bản mới sinh U+202F; không thể chỉ "format thử lại bằng JDK mới" và mặc định khôi phục raw input gốc.

**Không khắc phục bằng cách thay mọi U+202F thành U+0020 trong toàn ứng dụng.** Với nội dung tiếng Pháp, số và tên/currency, no-break spacing có thể là quy tắc ngôn ngữ quan trọng. Hãy chọn nơi cần **parser tương thích input legacy** và nơi cần **renderer hiển thị theo locale hiện tại**.

## 7. Parse dữ liệu cũ: ký tự trông giống nhau không đảm bảo bằng nhau

Nếu parser locale yêu cầu dấu nhóm U+202F mà input lưu từ trước dùng dấu ASCII space, nó có thể:

- không parse được ngay từ đầu;
- parse **một phần chuỗi** rồi bỏ phần còn lại;
- trả số khác ý định;
- hoặc được provider nào đó chấp nhận, tùy parser/version.

Vì `NumberFormat.parse(String)` có thể chấp nhận **tiền tố**, kết quả không `null` chưa đủ chứng minh input hợp lệ.

### Ví dụ Java 17+: kiểm tra parse hết chuỗi

Tạo file `GroupingParseProbe.java`:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class GroupingParseProbe {
    static String codes(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    static void parseAll(NumberFormat format, String text) {
        ParsePosition at = new ParsePosition(0);
        Number value = format.parse(text, at);
        boolean consumed = value != null
                && at.getIndex() == text.length();

        System.out.println("input: " + codes(text));
        System.out.println("parsed: " + value);
        System.out.println("consumed: " + at.getIndex()
                + "/" + text.length());
        System.out.println("full input: " + consumed);
    }

    public static void main(String[] args) {
        Locale france = Locale.FRANCE;
        NumberFormat format = NumberFormat.getNumberInstance(france);

        String current = format.format(1234567.89);
        System.out.println("runtime format: " + codes(current));
        parseAll(format, current);

        // Giả lập đầu vào nơi dấu phân nhóm bị thay bằng ASCII SPACE.
        String changed = current.replace('\u202F', ' ');
        parseAll(format, changed);
    }
}
```

```bash
javac -encoding UTF-8 GroupingParseProbe.java
java -Djava.locale.providers=CLDR GroupingParseProbe
```

Với runtime tham chiếu có `fr-FR` grouping U+202F, kiểm thử cho thấy `changed` được parse chỉ đến chữ số đầu tiên:

```text
runtime format: [U+0031, U+202F, U+0032, U+0033, U+0034, U+202F, U+0035, U+0036, U+0037, U+002C, U+0038, U+0039]
input: [U+0031, U+202F, U+0032, U+0033, U+0034, U+202F, U+0035, U+0036, U+0037, U+002C, U+0038, U+0039]
parsed: 1234567.89
consumed: 12/12
full input: true
input: [U+0031, U+0020, U+0032, U+0033, U+0034, U+0020, U+0035, U+0036, U+0037, U+002C, U+0038, U+0039]
parsed: 1
consumed: 1/12
full input: false
```

Đây là **kết quả tham chiếu của runtime đã kiểm chứng**, không phải hợp đồng API bảo đảm với mọi JDK. Nếu provider khác đang dùng U+00A0 hoặc U+0020, `replace('\u202F', ' ')` có thể không đổi chuỗi hoặc parser có hành vi khác. Hãy lấy separator hiện hành từ `DecimalFormatSymbols` và kiểm tra dữ liệu thực.

**Rất quan trọng:** ngay cả `full input: true` vẫn không có nghĩa vị trí grouping luôn hợp lệ theo quy tắc nghiêm ngặt; `DecimalFormat` có thể khoan dung với grouping không chuẩn. Nếu nhập số tiền, cần thêm validation cú pháp, miền giá trị, scale và currency. Đừng sử dụng parse/format như một bộ validator duy nhất.

## 8. Tên ngôn ngữ và currency symbol: hiển thị, không làm khóa

Giữ mã có thể truy xuất ổn định hơn các chuỗi đã địa phương hóa:

```text
Dữ liệu lưu:
  locale tag = "de-DE"
  currency code = "EUR"

Hiển thị khi chọn locale:
  locale.getDisplayLanguage(...)
  currency.getSymbol(displayLocale)
```

Không dùng `"Deutsch"` hay `"€"` làm khóa chính/foreign key: hai giá trị đó có thể tùy locale, provider và cách phát triển hệ thống. `"€"` có thể được dùng ở nhiều quốc gia và mã `EUR` mới xác định đơn vị tiền theo chuẩn.

### Ví dụ Java 17+: tên và ký hiệu theo locale

File `NamesAndCurrencyProbe.java`:

```java
import java.util.Currency;
import java.util.Locale;

public class NamesAndCurrencyProbe {
    public static void main(String[] args) {
        Locale german = Locale.forLanguageTag("de-DE");
        Currency euro = Currency.getInstance("EUR");

        System.out.println("tag: " + german.toLanguageTag());
        System.out.println("code: " + euro.getCurrencyCode());
        System.out.println("language en: "
                + german.getDisplayLanguage(Locale.ENGLISH));
        System.out.println("language de: "
                + german.getDisplayLanguage(Locale.GERMAN));
        System.out.println("currency fr: "
                + euro.getSymbol(Locale.FRANCE));
    }
}
```

```bash
javac -encoding UTF-8 NamesAndCurrencyProbe.java
java -Djava.locale.providers=CLDR NamesAndCurrencyProbe
```

Ví dụ đầu ra trên runtime tham chiếu:

```text
tag: de-DE
code: EUR
language en: German
language de: Deutsch
currency fr: €
```

Bản nâng cấp có thể đổi **display names hoặc symbol**, nhưng `toLanguageTag()` và `getCurrencyCode()` được dùng như **mã dữ liệu**, không phải tên bản dịch. Với mã quốc gia, ngôn ngữ hoặc currency thay đổi theo tiêu chuẩn qua nhiều năm, ngay cả hệ mã cũng phải được quản lý bằng quy tắc domain và version, song vẫn tốt hơn dùng chuỗi hiển thị không có schema.

### Khi cần tên hiển thị ổn định tuyệt đối?

Nếu hợp đồng pháp lý, nhãn sản phẩm bắt buộc hoặc báo cáo được ký duyệt đòi tên cố định, **đừng phụ thuộc hoàn toàn vào CLDR mặc định của JVM**. Hãy lưu tên theo bản dịch được quản lý trong resource của ứng dụng cùng phiên bản nội dung. Khi đó cần quy trình cập nhật/duyệt bản dịch riêng; không kỳ vọng nâng cấp JDK tự đảm bảo wording cũ.

## 9. Ký tự Unicode nào gây lỗi nhiều nhất?

| Loại | Ví dụ | Triệu chứng |
| --- | --- | --- |
| U+0020 vs U+202F | space thường so với narrow no-break space | Snapshot khác, parser dừng sớm |
| U+00A0 vs U+202F | hai dấu không ngắt có độ rộng khác | Layout/PDF/test thay đổi |
| `,` vs `.` | dấu grouping/decimal đổi vai trò theo locale | Sai giá trị hoặc parse fail |
| U+066B/U+066C | dấu phân cách Arabic | Parser Latin không hiểu số Arabic |
| U+0030–U+0039 vs U+0660–U+0669 | Latin/Arabic-Indic digits | Truy xuất, regex, width khác |
| Ký hiệu tiền `$` vs dạng mã/tiền tố | Hai vùng dùng ký hiệu giống nhau | Currency ambiguity |
| Tên tháng rút gọn | khác dấu chấm, tên mới, cách viết | Parser/snapshot lỗi |
| Dấu gạch nối `-` vs space trong ngày | thay pattern short/medium | Input legacy không parse được |
| Text có bidi control hoặc no-break | trộn RTL/LTR | Khác thứ tự hiển thị hoặc xuống dòng |
| Tên quốc gia/ngôn ngữ mới | cập nhật thuật ngữ | UI snapshot, search key khác |

**Không nên “normalization” mọi dấu trắng và ký hiệu về ASCII một cách toàn cục.** Unicode NFC chỉ giải quyết canonical equivalence; U+0020, U+00A0 và U+202F **không phải các dấu cách giống hệt nhau về ngữ nghĩa** trong mọi ngữ cảnh.

## 10. Vì sao snapshot test dễ hỏng sau nâng cấp?

Một số test cứng như:

```java
assertEquals("1 234 567,89", actual);
```

có thể thất bại khi CLDR thay group separator sang U+00A0 hoặc U+202F. Một test khác có thể thất bại chỉ do thay tên quốc gia, tên tháng hoặc ký hiệu tiền, trong khi **nghiệp vụ vẫn đúng**.

Nhưng cũng có test **cần** phát hiện thay đổi này: khi một API đang xuất chuỗi hiển thị thành định dạng mà đối tác đã hiểu theo một pattern cố định, thay đổi format là **hỏng hợp đồng**. Vì vậy không thể giải quyết mọi lỗi snapshot bằng cách xóa assertion.

### Phân loại test theo mục tiêu

| Mục tiêu | Assertion phù hợp |
| --- | --- |
| Domain amount | So `BigDecimal.compareTo(...) == 0` hoặc scale theo hợp đồng |
| Locale display hiện hành | Kiểm tra separators/locale metadata của runtime, thử rendering đúng |
| Dạng chuẩn giao tiếp | So đúng contract, ví dụ numeric field hoặc decimal string canonical |
| UI snapshot | Chạy theo JDK/provider/font/locale đã cố định và chấp nhận cập nhật có review |
| Parser legacy | Test dữ liệu thực trước nâng cấp, cả ASCII/Unicode spaces và sample cũ |
| Độ dài/line breaking | Kiểm tra trên UI và text engine, không chỉ `String.length()` |
| Currency identity | So `Currency.getCurrencyCode()`, không so ký hiệu đơn lẻ |
| Display names | Kiểm tra chính sách wording sản phẩm thay vì tên CLDR ngẫu nhiên |

**Lý tưởng:** test nào bảo đảm ngữ nghĩa, test đó so ngữ nghĩa; test nào bảo đảm biểu diễn, test đó so biểu diễn chính xác và ghi rõ **locale + provider/version**.

### Snapshot nên lưu thêm metadata

```text
java.runtime.version
java.vendor
java.locale.providers (hoặc <default>)
Locale.toLanguageTag()
numbering system extension (u-nu nếu có)
zone ID, currency code, rounding mode
input number/date cố định
formatted output + Unicode code points
```

Đừng suy phiên bản CLDR từ `java.version` chỉ bằng một bảng cứng trong ứng dụng. Dùng tài liệu release tương ứng và **đo output thật**.

## 11. Kiểm tra cấu hình trước khi so sánh hai JDK

Hai runtime có thể khác nhau vì nhiều yếu tố ngoài CLDR:

1. **JDK vendor/build/update**: cùng major version chưa chắc mọi thành phần giống nhau.
2. **`java.locale.providers`**: CLDR/HOST/SPI hoặc legacy trên JDK hỗ trợ.
3. **`Locale` và Unicode extensions**: ví dụ `en-US-u-nu-arab` khác `en-US`.
4. **Default locale**: process/container/CI có thể dùng locale khác, nhất là nếu bỏ truyền locale.
5. **Currency**: formatter có thể chọn currency mặc định từ locale, không phải currency giao dịch.
6. **Time zone và tzdb**: tên/offset/date-time thay đổi còn có thể do dữ liệu múi giờ, **khác với CLDR**.
7. **Font/UI renderer**: text trông khác không luôn do format string khác.
8. **Application resource bundles/custom SPI**: bản dịch nội bộ có thể phủ lên cách hiển thị của runtime.
9. **Module đóng gói**: jlink image rút gọn có thể thiếu `jdk.localedata` hoặc một số locale.
10. **System default charset**: từ JDK 18, UTF-8 là default charset theo JEP 400; lỗi encode/decode file có thể gây sai Unicode **độc lập** với locale data.

Nếu đầu ra khác, hãy khoanh vùng từng yếu tố thay vì vội gán mọi thay đổi cho CLDR.

## 12. Chiến lược lưu trữ: không biến chuỗi hiển thị thành dữ liệu nguồn

Một ví dụ không nên làm:

```java
// Không nên lưu số lâu dài ở dạng hiển thị theo locale:
String stored = NumberFormat.getNumberInstance(userLocale)
        .format(amount);
```

Sau nâng cấp, chính runtime mới có thể không parse lại chính xác chuỗi cũ nếu separator/pattern đã thay đổi. Càng nguy hiểm khi locale của bản ghi không được lưu.

### Lưu dữ liệu theo kiểu có schema

- Số: `BigDecimal`/cột DECIMAL, hoặc decimal string chuẩn với dấu chấm và **không có grouping** theo hợp đồng.
- Ngày giờ: `Instant`/ISO offset timestamp; nếu cần ý nghĩa múi giờ vùng, lưu thêm `ZoneId`.
- Currency: `amount + ISO 4217 currency code`; chỉ hiển thị ký hiệu theo locale.
- Locale: thẻ BCP 47 như `vi-VN`, không dùng tên đã dịch.
- Quốc gia: mã trong miền nghiệp vụ, không dùng tên nước nhìn thấy.
- Dữ liệu văn bản được ký duyệt: lưu text/version nội dung khi cần cố định nguyên văn.

### Ví dụ Java 17+: domain khác presentation

Tạo file `CanonicalVsDisplayDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class CanonicalVsDisplayDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");

        String canonical = amount.toPlainString();
        BigDecimal restored = new BigDecimal(canonical);

        NumberFormat france =
                NumberFormat.getNumberInstance(Locale.FRANCE);
        france.setMinimumFractionDigits(2);
        france.setMaximumFractionDigits(2);

        System.out.println("stored: " + canonical);
        System.out.println("restored equal: "
                + (amount.compareTo(restored) == 0));
        System.out.println("display codepoints: "
                + france.format(restored).codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList());
    }
}
```

```bash
javac CanonicalVsDisplayDemo.java
java CanonicalVsDisplayDemo
```

Phần **ổn định theo schema**:

```text
stored: 1234567.89
restored equal: true
```

Dòng `display codepoints` có thể **thay đổi theo provider/JDK**; điều đó là hợp lệ nếu mục đích chỉ là hiển thị theo locale hiện hành. Với `BigDecimal` có **scale âm**, `toPlainString()` không bảo toàn mọi thuộc tính scale khi tạo lại; nếu cần round-trip đầy đủ đối tượng `BigDecimal` ở mọi scale, chọn `toString()` hoặc lưu `unscaledValue + scale` theo schema.

## 13. Khi phải hỗ trợ các chuỗi đã lưu từ JDK cũ

Nếu kho dữ liệu hiện đang lưu số/ngày dưới dạng **chuỗi hiển thị**, bạn không thể ngay lập tức chuyển toàn bộ format mà không xét dữ liệu cũ.

Một kế hoạch migration có kiểm soát:

1. **Inventory:** tìm những trường đang lưu localized strings và những đường parse/format tương ứng.
2. **Xác định nguồn từng bản ghi:** locale, JDK/provider/phiên bản nếu biết; dùng metadata/đặc điểm dữ liệu, tránh đoán tùy tiện.
3. **Định nghĩa parser legacy riêng:** hỗ trợ chính xác những định dạng cũ đã **xác nhận tồn tại**, không chấp nhận mọi biến thể một cách vô giới hạn.
4. **Validate toàn bộ input:** `ParsePosition`, giới hạn độ dài, dấu nhóm, decimal precision, ngày hợp lệ và miền giá trị.
5. **Đánh dấu trường hợp mơ hồ:** `1,234` có thể là một nghìn hai trăm ba mươi tư hoặc một phẩy hai ba bốn; không tự quyết nếu thiếu locale.
6. **Chuẩn hóa sang domain value và schema mới:** decimal/date/time/currency code, lưu trace dữ liệu nguồn theo chính sách bảo mật.
7. **Backfill có kiểm tra:** đếm số bản ghi thành công, thất bại, mơ hồ và collision trước khi cắt chuyển.
8. **Dual-read tạm thời nếu cần:** ưu tiên schema mới; parser cũ chỉ cho dữ liệu được gắn nguồn legacy.
9. **Không dùng dữ liệu hiện thời làm lời giải cho lịch sử:** việc parse chuỗi cũ qua default formatter của JDK mới có thể im lặng sai.
10. **Theo dõi production metrics:** lỗi parse theo locale, chiếm dụng dữ liệu legacy, tỷ lệ backfill và fallback.
11. **Lập chính sách kết thúc hỗ trợ:** khi đã chuyển hết dữ liệu, bỏ parser cũ có kiểm soát, tránh tồn tại sự dễ dãi vĩnh viễn.

Trong một số hệ thống, việc chấp nhận cả U+0020/U+00A0/U+202F khi đọc một trường số có thể hợp lý **nếu** schema, locale và quy tắc grouping được kiểm tra nghiêm. Nhưng không thay một ký tự thành ký tự khác trên toàn bộ nội dung tiếng Pháp/Ả Rập, tên người hoặc văn bản tự do.

## 14. Cần định dạng thật sự bất biến thì chọn gì?

Không phải nội dung nào cũng được phép thay đổi theo locale data:

| Loại đầu ra | Chiến lược |
| --- | --- |
| UI thân thiện người dùng | Dùng `NumberFormat`, `DateTimeFormatter`, display names theo locale; chấp nhận cập nhật đúng chuẩn |
| Định dạng giao tiếp JSON/CSV có schema riêng | Dùng định dạng máy rõ ràng, không dựa default locale |
| Báo cáo đã phát hành/được ký | Lưu snapshot đã phát hành hoặc versioned formatter policy |
| Tài liệu pháp lý và thông báo được phê duyệt | Lưu bản dịch đã phê duyệt dưới quyền quản lý nội dung |
| Parser giao thức cũ | Dùng pattern cố định và validate chặt theo hợp đồng đã công bố |
| Cần locale patterns cũ trong JDK 23+ | Xem xét custom formatter/pattern hoặc **SPI** có quản lý; không dựa `COMPAT` đã bị xóa |

**Không cố định dấu nhóm toàn bộ UI chỉ vì snapshot cũ.** CLDR được cập nhật để cải thiện dữ liệu theo ngôn ngữ/vùng; nếu hiển thị cho người dùng, một thay đổi đúng theo chuẩn có thể là cải tiến nên được chấp nhận. Chỉ khóa output vào pattern cũ khi có **yêu cầu nghiệp vụ thật sự** và được ghi rõ.

Nếu viết custom `DecimalFormat` với `DecimalFormatSymbols`, mọi dấu/pattern bạn đặt tường minh có thể ổn định hơn, nhưng bạn đang **tự gánh trách nhiệm** bảo trì khi ký hiệu tiền tệ, số lẻ mặc định hoặc quy ước địa phương thay đổi. Đây không phải lựa chọn không có chi phí.

## 15. `java.locale.providers` không phải giải pháp chữa mọi tương thích

Ví dụ trên JDK 17–22 có thể có thể chọn legacy data:

```bash
java -Djava.locale.providers=COMPAT,CLDR MyApp
```

Trên **JDK 23 trở lên**, `COMPAT`/`JRE` đã bị loại bỏ; việc đặt tên này không còn phục hồi locale data cũ. Với JDK mới, giải pháp duy trì một contract có thể là:

- truyền **pattern và symbols tường minh** vào `DecimalFormat`/`DateTimeFormatter`, nếu contract đủ cụ thể;
- cài đặt custom `LocaleServiceProvider` qua SPI nếu phù hợp quy mô/phạm vi;
- lưu/trao đổi **giá trị canonical** thay vì chuỗi localized;
- tạo parser legacy có giới hạn cho dữ liệu đã lưu;
- giữ nguồn dữ liệu UI bản dịch riêng và kiểm soát version.

Property `java.locale.providers` chỉ chọn nguồn ưu tiên trong số **provider được runtime hỗ trợ**; nó không cài đặt lại một provider đã bị xóa và không bảo đảm mọi API cùng một dữ liệu.

## 16. Các kiểm thử hồi quy nên có khi nâng cấp

### Ma trận locale tối thiểu

Chọn các locale đại diện cho ứng dụng:

- `en-US`: dấu `,` và `.`, tiếng Anh với các ngày/tiền tệ thường gặp.
- `de-DE`: dấu nhóm/thập phân đảo so với en-US.
- `fr-FR`: các khoảng trắng Unicode không ngắt.
- `ru-RU`: có thể dùng NBSP hoặc dấu tương tự trong định dạng số.
- `vi-VN`: dấu nhóm/thập phân, tên tháng và UI tiếng Việt.
- `ar-EG`: chữ số Arabic-Indic và dấu Arabic; kiểm thử RTL/BiDi.
- `ja-JP`: cách hiển thị tên vùng và format ngày tháng.
- `hi-IN`: kiểm thử pattern số/grouping theo provider nếu sản phẩm cần định dạng Ấn Độ.

Các kết quả **không được suy từ mã locale bằng tay**; chạy probe và kiểm chứng thực tế.

### Bộ input

| Nhóm | Input nên thử |
| --- | --- |
| Số thập phân | `0`, `1.2`, `1234567.89`, số âm, số nhiều chữ số |
| Currency | USD, EUR, VND và currency của giao dịch thực |
| Date/time | 12h AM/PM, 24h, tên tháng dài/ngắn, timezone |
| Unicode whitespace | U+0020, U+00A0, U+202F |
| Decimal/grouping | Dấu phẩy/chấm trái vai trò, nhóm đúng/sai |
| Numbering | `latn`, `arab` hoặc extensions được hỗ trợ |
| Locale display | language/country/script names |
| Legacy data | Mẫu chuỗi đã lưu từ phiên bản JDK cũ |
| Runtime | JDK cũ, mới, provider default và provider được cấu hình |

### Quy trình chạy

1. Cố định **input values** và **locale tags** cho hai runtime.
2. Chạy `LocaleDataProbe` trên cả hai, lưu output Unicode code points.
3. Chạy parser tests trên **dữ liệu thật do runtime cũ từng ghi**, không chỉ dữ liệu mới.
4. Phân loại diff: **đúng chuẩn mới** hoặc **hỏng contract**.
5. Kiểm thử UI layouts, đặc biệt no-break spaces, RTL, overflow và font fallback.
6. Kiểm thử hệ thống tích hợp/DB/caches nếu trước đây dùng display string làm key.
7. Chạy release canary và giám sát lỗi parse ngày/số sau deploy.
8. Review snapshot changes với người phụ trách i18n, không duyệt hàng loạt bằng cách cập nhật golden files mà không hiểu thay đổi.

## 17. Những lỗi thường gặp

| Sai lầm | Rủi ro | Giải pháp |
| --- | --- | --- |
| Cho rằng JDK upgrade chỉ thay JVM bytecode behavior | Locale display output có thể đổi | QA bản dữ liệu locale/JDK |
| So sánh chuỗi khoảng trắng bằng mắt | Bỏ qua U+0020/U+00A0/U+202F | In Unicode code points |
| `replace(" ", "")` để bỏ grouping | Không xử lý no-break spaces, có thể làm sai text | Parse theo locale + validation |
| Dùng `Locale.getDefault()` trong server đa user | Kết quả phụ thuộc JVM/environment | Truyền `Locale` tường minh |
| Dùng `Currency.getSymbol` như khóa tiền tệ | Ký hiệu không duy nhất/ổn định | Dùng mã currency |
| Lưu `getDisplayLanguage()` thành language ID | Tên dịch có thể đổi | Lưu BCP 47 language tag |
| Lưu `NumberFormat.format(amount)` để giao tiếp máy | Provider upgrade làm parse thất bại | Lưu decimal canonical/numeric |
| `parse(String)` trả một số được coi là success | Có thể chỉ parse tiền tố | Dùng `ParsePosition` và validation |
| Bỏ qua rủi ro Java 20 AM/PM U+202F | Snapshot/date parser khác | Kiểm tra ký tự, legacy parser riêng |
| Thêm `COMPAT` để chữa lỗi ở JDK 23+ | Legacy provider đã xóa | Pattern/SPI/canonical data |
| Chọn HOST trên CI và production khác OS | Locale data không nhất quán | Cố định provider hoặc test rõ |
| Snapshot output một runtime coi là chân lý toàn cầu | CLDR cập nhật gây sai test không cần thiết | Phân loại domain vs presentation tests |
| Thay mọi Unicode space bằng ASCII | Mất no-break semantics | Chính sách input theo field |
| Mặc định jlink image có mọi locale | Image rút gọn có thể thiếu locale data | Kiểm tra `jdk.localedata` và include locales |
| Không test parse dữ liệu JDK cũ | Hỏng migration sau deploy | Golden legacy input + backfill |
| Tự regex thay dấu `,`/`.` không có locale | Sai giá trị số | Parse đúng locale/source |
| Đổ lỗi CLDR cho lỗi charset/tzdb | Khắc phục sai nguyên nhân | Phân biệt data sources và runtime settings |

## 18. Tự kiểm tra

1. **Vì sao cùng code format ngày có thể trả chuỗi khác trên JDK mới?** Vì JDK có thể dùng CLDR/provider/pattern mới.
2. **JDK nào bật CLDR mặc định?** JDK 9, theo JEP 252.
3. **Từ JDK 23 có còn dùng `COMPAT` để quay về legacy data không?** Không, provider đã bị loại bỏ.
4. **U+202F khác U+0020 như thế nào?** Là narrow no-break space, có quy tắc xuống dòng khác và là ký tự khác hẳn.
5. **Nếu `fr-FR` thay U+202F bằng ASCII SPACE, parser chắc chắn chấp nhận không?** Không. Test thực tế có thể chỉ tiêu thụ tiền tố.
6. **`NumberFormat.parse(String)` có đảm bảo parse cả input không?** Không; dùng `ParsePosition` để kiểm tra.
7. **Vì sao `Locale.getDisplayLanguage()` không thích hợp làm khóa?** Tên hiển thị phụ thuộc display locale và locale data.
8. **Vì sao `Currency.getSymbol()` không thể thay thế mã ISO currency?** Ký hiệu có thể trùng và có thể đổi theo locale.
9. **Có nên đổi mọi U+202F sang U+0020 không?** Không; no-break semantics có thể quan trọng.
10. **CLDR mới là nguyên nhân duy nhất khi output khác sau nâng cấp?** Không; provider, default locale, tzdb, charset và UI fonts cũng có thể khác.
11. **Nên so sánh snapshot thế nào?** Gắn metadata JDK/provider/locale, in code points, phân loại hợp đồng domain và presentation.
12. **Khi kho dữ liệu lưu `1 234,50`, có nên chỉ parse bằng JDK mới rồi ghi đè không?** Không; cần biết locale/format nguồn, kiểm tra ambiguous và validate trước migration.
13. **Nếu API trả số thật thay vì localized string, JDK upgrade tác động gì?** Biểu diễn API theo schema ổn định hơn; UI có thể format lại theo locale mới mà không đổi giá trị.
14. **`java.locale.providers` được đổi bằng `System.setProperty` giữa chương trình có an toàn không?** Không được đảm bảo; cấu hình từ launcher startup.
15. **Nếu tên nước thay đổi theo CLDR mới, có phải dữ liệu ID cần đổi?** Không mặc nhiên; UI display name và identity code là hai vấn đề khác nhau.
16. **Khi nào có lý do chốt pattern cố định?** Khi hợp đồng pháp lý, protocol, parser legacy hoặc hệ thống giao tiếp quy định format chính xác.
17. **Khi nào nên chấp nhận locale display output mới?** Khi là giao diện thân thiện người dùng và dữ liệu cập nhật phản ánh chuẩn locale phù hợp.
18. **Test nào giúp phát hiện Unicode spaces không thể nhìn rõ?** In code points dạng `U+XXXX` và thử parse cả input với `ParsePosition`.

## Tài liệu tham khảo

- [Oracle — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): thay đổi quốc tế hóa, locale data, lưu ý COMPAT removal, ví dụ pattern ngày UK.
- [Oracle — LocaleServiceProvider (JDK 23)](https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): loại provider, cấu hình startup và bảng JDK ↔ CLDR.
- [Oracle — JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): CLDR 39, COMPAT, HOST/SPI và cấu hình provider.
- [Oracle — JDK 23 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk23-suported-locales.html): CLDR 45, removal của legacy data.
- [OpenJDK JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): lý do chuyển sang CLDR và chiến lược di trú.
- [Spring Framework — Date and Time Formatting with JDK 20 and higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher): ví dụ U+202F xuất hiện trước day period.
- [Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): các separator và chữ số theo locale.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): format, grouping và parse.
- [Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): mã tiền tệ và symbol theo locale.
- [Unicode CLDR Project](https://cldr.unicode.org/): dữ liệu ngôn ngữ/khu vực có version và release notes.
