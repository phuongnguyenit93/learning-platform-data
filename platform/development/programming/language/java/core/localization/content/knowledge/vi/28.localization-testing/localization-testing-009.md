# Đối chiếu thay đổi đầu ra khi nâng JDK, CLDR hoặc runtime image

Nâng phiên bản JDK không nhất thiết làm hỏng mã Java, nhưng có thể khiến **cùng dữ liệu đầu vào tạo ra chuỗi hiển thị khác trước**. Điều này đặc biệt quan trọng với module **Java core - localization**, nơi ứng dụng dùng `Locale`, `NumberFormat`, `DateFormat`, `DateTimeFormatter`, `MessageFormat`, `Currency`, `ResourceBundle`, tên múi giờ hoặc quy tắc lịch địa phương.

Ví dụ, một dấu phân nhóm số có thể đổi từ **U+00A0 NO-BREAK SPACE** sang **U+202F NARROW NO-BREAK SPACE**; tên tháng, định dạng ngày dài, ký hiệu tiền tệ, cách viết giờ hay thông điệp theo locale cũng có thể thay đổi khi **dữ liệu CLDR** hoặc cách lựa chọn locale provider của JDK được cập nhật. Hai chuỗi có thể **trông giống nhau** trong giao diện nhưng không bằng nhau theo `String.equals`. Đôi khi thay đổi hoàn toàn hợp lệ theo dữ liệu ngôn ngữ mới; đôi khi là regression của ứng dụng.

Với **runtime image** tạo bằng `jlink`, vấn đề còn rộng hơn: image tối giản có thể **không chứa cùng tập module và dữ liệu locale** như full JDK. Một test chạy trên máy phát triển thành công không chứng minh image triển khai sẽ dùng dữ liệu định dạng tương đương.

Bài này hướng dẫn cách xây một **đường chuẩn đầu ra (baseline)**, chạy cùng **bộ input cố định** trên **JDK cũ/mới và runtime image thực tế**, xuất bằng chứng ở mức Unicode code point, phân loại thay đổi và chỉ chấp thuận những khác biệt đã được review. Mục tiêu là **đối chiếu kết quả khi nâng cấp**, không phải cưỡng ép mọi phiên bản JDK mãi trả cùng câu chữ.

## 1. Những thành phần có thể làm đầu ra thay đổi

| Thành phần được nâng/thay | Ảnh hưởng có thể quan sát | Ví dụ cần thử |
| --- | --- | --- |
| **JDK feature/update/build** | Triển khai API, locale data, Unicode, TZDB, bug fixes | Tháng/ngày, ký số, currency |
| **CLDR data** | Tên tháng, ngày, số, ký hiệu, mẫu locale, chữ viết tắt | `NumberFormat`, `DateTimeFormatter` |
| **`java.locale.providers`** | Thứ tự chọn nguồn locale data | `CLDR`, `SPI`, `HOST`; legacy `COMPAT` trong JDK cũ |
| **Vendor/distribution** | Dữ liệu build và cấu hình đóng gói có thể khác | Hai JDK cùng feature number |
| **`jdk.localedata`** | Khả dụng của dữ liệu locale mở rộng | Image `jlink` có/không module |
| **`--include-locales`** | Tập locale được giữ lại trong image | `fr-FR`, `vi-VN`, `ja-JP` |
| **Time-zone database (TZDB)** | Offset lịch sử/tương lai, tên vùng, quy tắc DST | `ZoneId`, `ZonedDateTime` |
| **Default locale/timezone** | Đầu ra phụ thuộc máy chạy | `Locale.getDefault`, `ZoneId.systemDefault` |
| **Ứng dụng và bundle** | Pattern, tài nguyên, provider dịch tự viết | `ResourceBundle`, `MessageFormat` |

**Điểm phân loại:** Không phải mọi thay đổi định dạng là lỗi. Dữ liệu CLDR phản ánh quy ước bản địa hóa được cập nhật; trong một số trường hợp **mới đúng hơn cũ**. Quy trình kiểm thử phải cho thấy **thay đổi gì, vì sao và nó ảnh hưởng người dùng/hợp đồng thế nào**.

## 2. Phân biệt JDK, CLDR, Unicode, TZDB và ứng dụng

Không nên gộp tất cả vào cụm “lỗi Java mới”:

- **JDK/runtime** chứa mã triển khai API và phiên bản các tập dữ liệu đi kèm.
- **CLDR (Common Locale Data Repository)** cung cấp nhiều mẫu định dạng và dữ liệu ngôn ngữ được Java sử dụng qua locale provider.
- **Unicode character data** ảnh hưởng những hàm như `Character.isLetter`, `isDigit`, case mappings, normalization và tên code point.
- **TZDB** là cơ sở dữ liệu quy tắc múi giờ, được `java.time` sử dụng cho `ZoneId` và các phép chuyển thời gian.
- **Resource bundles của ứng dụng** có thể độc lập với CLDR. Một bản `Messages_vi.properties` do dự án quản lý không tự dịch lại vì nâng CLDR.
- **Default environment** như locale mặc định, timezone mặc định hoặc charset có thể đổi khi container, OS hoặc cấu hình chạy đổi.

Khi diff xuất hiện, trước tiên hãy hỏi **nó đến từ dữ liệu locale, time zone, Unicode hay bản dịch của ứng dụng**, sau đó mới quyết định sửa.

## 3. CLDR trong JDK: dữ liệu ngôn ngữ không phải hằng số bất biến

Từ **JDK 9**, CLDR là nguồn dữ liệu locale mặc định trong Java. Ở **JDK 17**, `java.locale.providers` có thể chọn thứ tự những provider như `CLDR`, `COMPAT`, `SPI`, `HOST` tùy môi trường và provider có sẵn.

Ví dụ khởi động:

~~~bash
java -Djava.locale.providers=CLDR -cp out LocaleSnapshot
~~~

Dòng trên minh họa chạy một class đã biên dịch ở `out`, **không phải lệnh chạy một thư viện chung của JDK**. Property này cần được thiết lập **khi khởi động JVM**, không nên gọi `System.setProperty` sau khi các locale-sensitive services đã khởi tạo rồi mong toàn bộ provider selection thay đổi.

**Mốc migration cần nhớ:** legacy `JRE`/`COMPAT` locale data **bị loại bỏ từ JDK 23**. Vì vậy lời khuyên “cứ cấu hình `COMPAT` để giữ kết quả cũ” **chỉ có thể là giải pháp tạm cho các JDK còn hỗ trợ**, không phải chiến lược nâng cấp lâu dài.

Tài liệu Oracle:
- [Internationalization Enhancements, JDK 17](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html).
- [Removed Tools and Components, JDK 23](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html).

### Provider order là một biến độc lập phải ghi nhận

Với runtime hỗ trợ, các cấu hình:

~~~text
-Djava.locale.providers=CLDR
-Djava.locale.providers=SPI,CLDR
-Djava.locale.providers=HOST,CLDR
~~~

có thể dẫn đến các nguồn dữ liệu khác nhau. `HOST` phụ thuộc nền tảng và cấu hình người dùng; `SPI` phụ thuộc các service provider được cài đặt. Không phải mọi provider đều cung cấp mọi locale hay mọi service; JDK có thể chuyển sang provider tiếp theo.

Trong phép đối chiếu có kiểm soát, **giữ nguyên provider order giữa hai lần chạy** trừ khi chính sự thay đổi provider là đối tượng cần kiểm thử.

## 4. Không chỉ số phiên bản `17` hay `21`

Hai runtime cùng feature version có thể có khác biệt vì:
- khác patch/update;
- khác vendor;
- khác dữ liệu CLDR/TZDB đi kèm;
- một bên là **full JDK**, bên kia là **jlink image**;
- khác provider selection và service providers;
- khác cấu hình khởi động, locale mặc định, timezone.

Đối với mỗi kết quả baseline, cần gắn **fingerprint môi trường**:

| Metadata | Lấy từ đâu |
| --- | --- |
| Version/build | `java -version`, `java.runtime.version` |
| Vendor | `java.vendor` |
| Runtime image | `java.home` hoặc image identifier/hash trong pipeline |
| Locale provider order | Startup flag và `java.locale.providers` |
| Default FORMAT locale | `Locale.getDefault(Locale.Category.FORMAT)` |
| Default DISPLAY locale | `Locale.getDefault(Locale.Category.DISPLAY)` |
| Default timezone | `ZoneId.systemDefault()` |
| TZDB version | `ZoneRulesProvider.getVersions(zoneId).lastKey()` khi provider hỗ trợ |
| Module/locale coverage | `java --list-modules`, `jdk.localedata` và `jlink` configuration |

Metadata giúp giải thích diff; nó **không tự cho biết chuỗi mới có đúng ngữ nghĩa hay không**.

Không đưa các đường dẫn máy chứa tài khoản, hostname, API token hoặc dữ liệu người dùng thật vào artifact CI công khai. Có thể ghi **image digest/ID** thay cho toàn bộ `java.home`.

## 5. Mỗi phép thử phải có input ổn định

Nếu test viết:

~~~java
NumberFormat.getInstance().format(12345.67);
LocalDate.now();
ZoneId.systemDefault();
Locale.getDefault();
~~~

thì kết quả chịu ảnh hưởng bởi locale, ngày giờ và timezone của máy. Diff có thể đến từ môi trường, **không phải nâng JDK**.

Hãy cố định đầu vào:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");
LocalDate date = LocalDate.of(2024, 1, 2);
BigDecimal amount = new BigDecimal("12345.67");
ZoneId zone = ZoneId.of("Europe/Paris");
Instant instant = Instant.parse("2024-03-31T01:30:00Z");
~~~

Đây là snippet trong method, cần import `Locale`, `LocalDate`, `BigDecimal`, `ZoneId`, `Instant`.

**Tách hai loại phép thử:**
1. **Locale explicitly specified:** dùng locale/timezone/amount cố định để phát hiện thay đổi từ data/provider/runtime.
2. **Default environment behavior:** cố tình dùng default locale/timezone để kiểm chứng container hay command line đã đặt cấu hình đúng.

Không trộn hai mục tiêu vào một snapshot rồi cho rằng mọi khác biệt là do CLDR.

## 6. Các điểm đo có giá trị cao

Một bộ probes có thể bao gồm:

- `NumberFormat.getNumberInstance(locale)`: grouping, decimal separator, rounding và digit symbols.
- `NumberFormat.getCurrencyInstance(locale)`: ký hiệu tiền, vị trí ký hiệu, khoảng trắng đặc biệt.
- `DecimalFormatSymbols.getInstance(locale)`: ký tự decimal/grouping.
- `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT/MEDIUM/LONG/FULL)`: mẫu và tên ngày/tháng.
- `DateFormat.getDateInstance(...)`: so sánh API `java.text` với `java.time`.
- `Month.getDisplayName(TextStyle.FULL, locale)`: tên tháng.
- `DayOfWeek.getDisplayName(...)`: tên thứ.
- `WeekFields.of(locale)`: ngày đầu tuần và số ngày tối thiểu của tuần đầu (cũng có thể khác khi dữ liệu locale đổi).
- `Currency.getInstance(locale)`: mã và ký hiệu.
- `MessageFormat(pattern, locale)`: mẫu số/ngày áp dụng locale.
- `ResourceBundle`: locale thực tế tìm thấy và fallback.
- `ZoneId`/`ZonedDateTime`: offset và tên vùng tại những instant cụ thể.
- `Character`/`Normalizer`: các code point liên quan khi Unicode data cập nhật.

Không cần snapshot **mọi** locale và API ngay từ đầu. Nên ưu tiên **locale sản phẩm thực sự hỗ trợ** cùng các màn hình quan trọng: thanh toán, đơn hàng, thời gian giao dịch, email, thông báo và lịch.

## 7. Dấu cách Unicode: nhìn giống, giá trị khác

Một ví dụ quan trọng là khoảng trắng phân nhóm của tiếng Pháp:

~~~text
U+0020  SPACE
U+00A0  NO-BREAK SPACE
U+202F  NARROW NO-BREAK SPACE
~~~

Trong giao diện, chúng có thể trông giống dấu cách. Nhưng:

~~~java
"12 345".equals("12\u202F345");
~~~

có kết quả `false` vì code point khác nhau. Đây là snippet hợp lệ của biểu thức Java, không phải chương trình độc lập.

Một test dùng chuỗi hiển thị:

~~~text
expected: 12 345,67
actual:   12 345,67
~~~

có thể khiến người review bỏ sót thay đổi. Vì vậy **đừng chỉ chụp màn hình** hoặc xem output trên console; phải xuất Unicode code points hoặc escape các ký tự có khả năng gây nhầm lẫn.

**Không thay mọi khoảng trắng Unicode thành U+0020 trước khi diff** nếu nhiệm vụ là kiểm tra chính xác hành vi bản địa hóa; làm vậy sẽ che một thay đổi có thể ảnh hưởng layout, copy/paste hoặc parser của hệ khác.

## 8. Xây phép đo Unicode có thể so sánh byte-for-byte

Tạo helper Java 17+ hiển thị mọi code point dưới dạng `U+XXXX`:

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public final class CodePoints {
    private CodePoints() {}

    public static String show(String text) {
        return text.codePoints()
                .mapToObj(cp ->
                        String.format(Locale.ROOT,
                                "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        System.out.println(show(
                "A" + (char) 0x00A0 + "B"));
        System.out.println(show(
                "A" + (char) 0x202F + "B"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CodePoints.java
java CodePoints
~~~

Kết quả **ổn định**:

~~~text
U+0041 U+00A0 U+0042
U+0041 U+202F U+0042
~~~

Code point notation cũng làm rõ khác biệt giữa chữ dựng sẵn `é` và `e + COMBINING ACUTE ACCENT`. Một phép diff có thể ghi rõ **giá trị code point** thay vì buộc người đọc phân biệt bằng mắt.

`String.length()` đếm UTF-16 code units, không phải Unicode code points. Phương thức `codePoints()` thích hợp hơn cho báo cáo Unicode.

## 9. Chương trình snapshot chạy được trên Java 17+

Ví dụ sau tạo hai loại dòng:
- **`META`** ghi fingerprint môi trường.
- **`DATA`** ghi kết quả của các phép định dạng **với input cố định**.

Các trường `DATA` được chuyển thành chuỗi `U+XXXX`, nên dễ so sánh chính xác bằng công cụ diff và không phụ thuộc cách console render glyph.

Lưu thành **`LocaleSnapshot.java`**:

~~~java
import java.math.BigDecimal;
import java.text.DateFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Month;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.format.TextStyle;
import java.time.temporal.WeekFields;
import java.time.zone.ZoneRulesProvider;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class LocaleSnapshot {
    static String points(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static void meta(String name, String value) {
        System.out.println("META\t" + name + "\t" + value);
    }

    static void data(String name, String value) {
        System.out.println("DATA\t" + name
                + "\t" + points(value));
    }

    public static void main(String[] args) {
        meta("java.runtime.version",
                System.getProperty("java.runtime.version"));
        meta("java.vendor",
                System.getProperty("java.vendor"));
        meta("java.locale.providers",
                System.getProperty("java.locale.providers",
                        "(unset)"));
        meta("default.format.locale",
                Locale.getDefault(
                        Locale.Category.FORMAT).toLanguageTag());
        meta("default.zone",
                ZoneId.systemDefault().toString());
        meta("tzdb.Europe/Paris",
                ZoneRulesProvider.getVersions(
                        "Europe/Paris").lastKey());

        LocalDate date = LocalDate.of(2024, 1, 2);
        BigDecimal amount = new BigDecimal("12345.67");

        Map<String, Locale> locales = new TreeMap<>();
        locales.put("en-US", Locale.US);
        locales.put("fr-FR", Locale.FRANCE);
        locales.put("ja-JP", Locale.JAPAN);
        locales.put("vi-VN",
                Locale.forLanguageTag("vi-VN"));

        for (var entry : locales.entrySet()) {
            String key = entry.getKey();
            Locale locale = entry.getValue();

            data(key + ".number",
                    NumberFormat.getNumberInstance(
                            locale).format(amount));
            data(key + ".currency",
                    NumberFormat.getCurrencyInstance(
                            locale).format(amount));
            data(key + ".date.long",
                    DateTimeFormatter.ofLocalizedDate(
                            FormatStyle.LONG)
                            .withLocale(locale).format(date));
            data(key + ".month",
                    Month.JANUARY.getDisplayName(
                            TextStyle.FULL, locale));

            DecimalFormatSymbols symbols =
                    DecimalFormatSymbols.getInstance(locale);
            data(key + ".symbols",
                    "" + symbols.getGroupingSeparator()
                            + symbols.getDecimalSeparator());

            WeekFields weeks = WeekFields.of(locale);
            data(key + ".weekFields",
                    weeks.getFirstDayOfWeek()
                            + "/" + weeks.getMinimalDaysInFirstWeek());

            data(key + ".message",
                    new MessageFormat(
                            "Items: {0,number,integer}",
                            locale).format(
                                    new Object[]{12345}));

            DateFormat legacy = DateFormat.getDateInstance(
                    DateFormat.LONG, locale);
            legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
            data(key + ".legacyDate",
                    legacy.format(new Date(0)));
        }

        Instant fixed =
                Instant.parse("2024-03-31T01:30:00Z");
        ZoneId zone = ZoneId.of("Europe/Paris");
        data("Europe-Paris.offset",
                zone.getRules().getOffset(
                        fixed).toString());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleSnapshot.java
java -Djava.locale.providers=CLDR LocaleSnapshot
~~~

**Output là dữ liệu đo, không được hardcode một bảng expected cho mọi JDK.** Mỗi dòng có định dạng:

~~~text
META\tjava.runtime.version\t<version của runtime>
META\tjava.locale.providers\tCLDR
DATA\ten-US.number\t<dãy Unicode code points>
DATA\tfr-FR.currency\t<dãy Unicode code points>
...
~~~

Trong đoạn mô tả trên, `\t` thể hiện dấu TAB để dễ đọc; chương trình xuất đúng tab (xem lưu ý ngay dưới đây).

**Lưu ý khi copy mã:** Trong Java source, hãy dùng `"\t"` để tạo tab. Nếu sao chép code hiển thị trong một môi trường tự escape backslash, phải kiểm tra chuỗi thực tế và điều chỉnh; đặc biệt các dòng `META`/`DATA` phải dùng delimiter thống nhất để chương trình diff bên dưới đọc được.

Có thể kiểm tra nhanh file được biên dịch bằng chạy thử và nhìn output: đầu dòng phải bắt đầu `META` hoặc `DATA`, sau đó là **tab**, key, **tab** và nội dung.

## 10. Snapshot không nên ngầm chứa dữ liệu động

Chương trình ở trên giữ ngày test là `2024-01-02` và instant là `2024-03-31T01:30:00Z` để tránh phụ thuộc vào lúc test được chạy. `DateFormat` cũ còn được đặt timezone UTC riêng, và các phép `DateTimeFormatter` được cho locale cụ thể.

Nếu snapshot dùng:
- `LocalDate.now()`;
- `new Date()`;
- `NumberFormat.getInstance()` không truyền locale;
- `DateFormat.getDateInstance()` không truyền locale;
- timezone mặc định;
- dữ liệu lấy trực tiếp từ môi trường production;

thì diff dễ bị “nhiễu”, không cô lập được tác động của JDK/CLDR.

**Nguyên tắc:** Chỉ để metadata thay đổi theo runtime; phần `DATA` nên xuất phát từ input được định nghĩa rõ. Nếu chủ đích thử default behavior, đưa default locale/timezone vào tên test riêng và ghi chúng vào baseline.

## 11. Chạy baseline/candidate trên hai JDK

Giả sử đã có class `LocaleSnapshot.class` được biên dịch theo Java 17; có hai runtime:

~~~text
/path/to/jdk-old/bin/java
/path/to/jdk-new/bin/java
~~~

Một quy trình shell minh họa trên Linux/macOS:

~~~bash
/path/to/jdk-old/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleSnapshot > baseline.txt

/path/to/jdk-new/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleSnapshot > candidate.txt

diff -u baseline.txt candidate.txt
~~~

Đường dẫn JDK là **placeholder mô tả cấu hình cần có**, không phải file có sẵn trên máy người học. Thay bằng đường dẫn thực của hai runtime. Trên Windows, dùng `java.exe` theo đường dẫn tương ứng và công cụ so sánh file UTF-8.

Trong CI, cố định:
1. JDK feature/update/vendor hoặc image digest;
2. đối số `-Djava.locale.providers`;
3. timezone/default locale nếu thử default;
4. cùng `LocaleSnapshot.class`, input và module/classpath;
5. cùng cách ghi file UTF-8 và newline nếu cần so sánh bytes.

**Không kết luận chỉ từ lệnh `diff` rằng lỗi thuộc về CLDR.** Cần đọc từng key khác biệt và kiểm tra provenance: provider, locale coverage, TZDB, hoặc code ứng dụng.

## 12. Tách metadata drift khỏi data drift

Nếu version JDK thay, dòng `META java.runtime.version` **đương nhiên khác**. Đây là thông tin cần ghi, nhưng không phải regression của định dạng.

Tách báo cáo:
- **Environment drift**: Java version, vendor, tzdb, image id, provider.
- **Behavior drift**: `DATA` về số/ngày/tiền/format/zone offset.
- **Product acceptance**: khác biệt đó có được phê duyệt hay không.

Một báo cáo tốt:

~~~text
ENVIRONMENT:
  JDK old: 17.x
  JDK new: 21.x
  locale providers: CLDR in both
  runtime image modules: compared

BEHAVIOR:
  CHANGED fr-FR.number
  CHANGED fr-FR.date.long
  UNCHANGED en-US.number

DECISION:
  fr-FR.number: accepted locale-data update
  fr-FR.date.long: requires translator/UI review
~~~

Đây là **mẫu báo cáo minh họa**, không phải kết quả khẳng định từ một cặp JDK cụ thể. Không gắn nhãn `accepted` trước khi review có bằng chứng.

## 13. Công cụ so sánh hai snapshot bằng Java

Có thể viết tiện ích nhỏ so sánh **chỉ các dòng `DATA`**, bỏ qua dòng `META` vốn được ghi để truy vết. Dữ liệu được xuất dưới dạng code points nên không cần so sánh font/console.

Tạo **`SnapshotDiff.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.TreeSet;

public class SnapshotDiff {
    static SortedMap<String, String> read(Path file)
            throws Exception {
        SortedMap<String, String> data = new TreeMap<>();

        for (String line : Files.readAllLines(
                file, StandardCharsets.UTF_8)) {
            if (!line.startsWith("DATA\t")) {
                continue;
            }
            String[] parts = line.split("\t", 3);
            if (parts.length != 3 || parts[1].isBlank()) {
                throw new IllegalArgumentException(
                        "Bad DATA line: " + line);
            }
            if (data.putIfAbsent(
                    parts[1], parts[2]) != null) {
                throw new IllegalArgumentException(
                        "Duplicate key: " + parts[1]);
            }
        }
        return data;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: SnapshotDiff baseline candidate");
            System.exit(2);
        }

        Map<String, String> before =
                read(Path.of(args[0]));
        Map<String, String> after =
                read(Path.of(args[1]));

        TreeSet<String> keys = new TreeSet<>();
        keys.addAll(before.keySet());
        keys.addAll(after.keySet());

        int changes = 0;
        for (String key : keys) {
            String a = before.get(key);
            String b = after.get(key);

            if (a == null) {
                System.out.println("ADDED " + key);
                changes++;
            } else if (b == null) {
                System.out.println("REMOVED " + key);
                changes++;
            } else if (!a.equals(b)) {
                System.out.println("CHANGED " + key);
                System.out.println("  old: " + a);
                System.out.println("  new: " + b);
                changes++;
            }
        }

        if (changes > 0) {
            System.out.println("DIFF count=" + changes);
            System.exit(1);
        }
        System.out.println("PASS data identical");
    }
}
~~~

~~~bash
javac -encoding UTF-8 SnapshotDiff.java
java SnapshotDiff baseline.txt candidate.txt
~~~

Trả `exit code 0` khi không có khác biệt `DATA`, `exit code 1` khi có khác biệt; `exit code 2` khi sai số tham số. Nếu file đọc lỗi hoặc duplicate key, Java báo lỗi và không được xem là PASS.

Ví dụ, với một key khác dấu phân nhóm:

~~~text
CHANGED fr-FR.number
  old: U+0031 U+0032 U+00A0 U+0033
  new: U+0031 U+0032 U+202F U+0033
DIFF count=1
~~~

Đây là **kịch bản mô phỏng**, không phải đầu ra được khẳng định cho mọi bản JDK. Chương trình báo thay đổi, **không quyết định thay đổi đó đúng hay sai**.

### Một lưu ý về mã nguồn snapshot

Khi viết literal delimiter trong `LocaleSnapshot.java`, các dòng `System.out.println` cần dùng `"\t"` với **một escape Java cho tab**. Nếu copy trong hệ thống có thêm một lớp escaping, có thể thay cách viết bằng:

~~~java
System.out.println("DATA" + (char) 9
        + name + (char) 9 + points(value));
~~~

Đây là **snippet thay thế toàn bộ thân phương thức `data`**. Nó giúp tránh nhầm nhiều lớp `\` khi code đi qua Markdown, JSON hay template.

## 14. So sánh ở mức code point và so sánh ngữ nghĩa

Có ít nhất ba mức chấp nhận thay đổi:

**Mức A — Exact string parity**

~~~text
String.equals / Unicode code points identical
~~~

Phù hợp khi:
- Giao thức yêu cầu chính xác ký pháp;
- Snapshot định dạng phải ổn định vì hợp đồng;
- Có người chủ động phê duyệt mọi thay đổi hiển thị.

**Mức B — Structural/semantic parity**

Ví dụ hai chuỗi ngày khác thứ tự tháng/ngày nhưng vẫn biểu diễn **cùng LocalDate** theo locale. Kiểm bằng parse với formatter thích hợp và so giá trị:

~~~java
LocalDate parsed = LocalDate.parse(
        formatted, formatter);

boolean sameDate =
        parsed.equals(LocalDate.of(2024, 1, 2));
~~~

Đây là **snippet** với `formatted` và `formatter` đã có. Với formatter locale không thuận nghịch ở một số style hoặc dữ liệu mơ hồ, parse cũng có thể không hoàn hảo; phải chọn tình huống test thích hợp.

**Mức C — UX/linguistic acceptance**

Ví dụ dấu cách hẹp, tên tháng mới hoặc ký hiệu tiền thay đổi nhưng đúng quy ước CLDR. Cần review:
- bản địa hóa có đúng kỳ vọng người dùng;
- UI còn đủ chiều rộng;
- accessibility/screen reader đọc được;
- copy/paste sang hệ thống khác có an toàn;
- biểu diễn có ảnh hưởng báo cáo/CSV/log hay không.

Không nên **normalize mọi Unicode whitespace trước exact diff** rồi mất tín hiệu cần review ở mức C.

## 15. NumberFormat: grouping, decimal và tiền tệ

Các nhóm thay đổi đáng thử:
- U+00A0 và U+202F khi phân nhóm hoặc giữa số và ký hiệu;
- dấu thập phân và dấu nhóm;
- cách đặt ký hiệu tiền trước/sau số;
- chữ số bản địa (ví dụ ASCII vs chữ số Ả Rập nếu locale/numbering system thay đổi);
- số chữ số sau dấu thập phân và rounding mặc định;
- dấu âm, ký hiệu phần trăm, khoảng trắng không ngắt.

Không dùng `NumberFormat.getInstance()` thiếu locale trong test so CLDR. Hãy dùng:

~~~java
Locale fr = Locale.FRANCE;
NumberFormat number = NumberFormat.getNumberInstance(fr);
NumberFormat money = NumberFormat.getCurrencyInstance(fr);

String amountText = number.format(12345.67);
String currencyText = money.format(12345.67);
~~~

Đây là **snippet**, cần import `Locale` và `NumberFormat`. Giá trị nội dung chính xác là **dữ liệu cần đo trên JDK**, không nên ghi đè expected bằng ví dụ “nhìn gần giống”.

Nếu cần **ký pháp chính xác để trao đổi dữ liệu giữa hệ thống**, hãy dùng định dạng có hợp đồng rõ (JSON numbers, decimal canonical) thay vì lấy chuỗi UI phụ thuộc CLDR làm protocol.

## 16. DateTimeFormatter và java.text.DateFormat không nhất thiết có cùng output

`DateTimeFormatter` và `DateFormat` là hai họ API khác nhau. Cả hai có locale-sensitive formatting, nhưng không nên suy luận chúng có cùng pattern hay luôn hiển thị giống nhau.

Ví dụ:

~~~java
DateTimeFormatter modern =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.LONG).withLocale(Locale.FRANCE);

DateFormat legacy =
        DateFormat.getDateInstance(
                DateFormat.LONG, Locale.FRANCE);
legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

Đây là **snippet** với imports `java.time.format.DateTimeFormatter`, `FormatStyle`, `java.text.DateFormat`, `Locale` và `TimeZone`.

Khi snapshot:
- Dùng một `LocalDate` cố định với `DateTimeFormatter`;
- Dùng một instant cố định cùng timezone rõ ràng với `DateFormat`;
- Không so hai API trên hai **ngày khác nhau** rồi kết luận có lỗi;
- Kiểm tra tên tháng/thứ, thứ tự các thành phần và dấu câu.

Đặc biệt, phép parse một ngày ngắn có thể mơ hồ nếu thiếu năm hoặc dùng thứ tự `dd/MM` vs `MM/dd`. Đừng biến snapshot hiển thị thành nguồn dữ liệu chuẩn của giao thức.

## 17. Timezone và TZDB: một nguồn drift độc lập

Khi quốc gia điều chỉnh DST hoặc offset, bản cập nhật TZDB có thể làm thay đổi kết quả chuyển:

~~~java
Instant event =
        Instant.parse("2024-03-31T01:30:00Z");

ZonedDateTime local =
        event.atZone(ZoneId.of("Europe/Paris"));
~~~

Đây là snippet; cần import `Instant`, `ZonedDateTime` và `ZoneId`.

**Phải giữ `Instant` và `ZoneId` cố định.** Nếu thay `ZoneId` theo timezone của CI host, phép thử không còn cô lập được thay đổi TZDB.

Có thể truy vấn version mà provider cung cấp:

~~~java
String tzdbVersion =
        ZoneRulesProvider.getVersions(
                "Europe/Paris").lastKey();
~~~

Đây là snippet; cần import `ZoneRulesProvider`. Thông thường JDK TZDB provider cung cấp map version. Với provider khác, hãy xử lý việc version info không có/khác theo hợp đồng của provider.

Test nên bao gồm:
- instant trong giai đoạn DST chuyển mùa;
- instant lịch sử quan trọng với nghiệp vụ;
- instant tương lai nếu dùng đặt lịch dài hạn;
- vùng cụ thể như `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York` khi liên quan.

**Không gọi mọi khác biệt timezone là lỗi CLDR.** TZDB và CLDR phục vụ những loại dữ liệu khác nhau.

## 18. `MessageFormat` và bản dịch của ứng dụng

Một thông điệp:

~~~text
Order {0}: {1,number,currency}
~~~

được `MessageFormat` format theo `Locale`. Khi nâng JDK/CLDR, phần định dạng `{1,number,currency}` có thể thay đổi dù pattern bản dịch không đổi.

Để xác định nguồn:
1. Giữ nguyên `ResourceBundle` và phiên bản message pattern.
2. Chạy cùng locale, amount, rounding.
3. Snapshot **pattern** và **formatted output**.
4. Nếu chỉ output đổi, điều tra dữ liệu locale/formatter.
5. Nếu pattern đổi, điều tra bản dịch/build/version của ứng dụng.

Không trộn `MessageFormat` từ JDK với cú pháp ICU `plural/select`. Nếu dự án dùng ICU4J, phiên bản thư viện và dữ liệu ICU là **một biến độc lập** cần ghi nhận, không thể gộp chung vào JDK version.

## 19. Runtime image `jlink` có thể cắt dữ liệu locale

Full JDK và runtime image do `jlink` tạo không mặc nhiên có tập module/dữ liệu giống nhau.

Một image tối giản:

~~~bash
jlink --add-modules java.base --output image-min
~~~

có thể hoạt động với các service thuộc `java.base` nhưng **không chứa module dữ liệu locale mở rộng `jdk.localedata`**. Kết quả cho những locale ngoài tập dữ liệu cơ bản có thể khác hoặc được fallback theo provider/rules của runtime.

Một image có locale mở rộng:

~~~bash
jlink --add-modules java.base,jdk.localedata \
  --include-locales=en,fr,vi,ja \
  --output image-localized
~~~

Đây là **lệnh minh họa** trên shell hỗ trợ `\` nối dòng. `--include-locales` là plugin `jlink` để chỉ giữ những locale khớp danh sách language tag theo cơ chế matching hỗ trợ; cần **bao gồm module `jdk.localedata`** khi dùng plugin.

Không coi việc dùng `--include-locales=fr,vi` là bảo đảm toàn bộ mọi locale extension, calendar/numbering system hoặc provider riêng đều tồn tại. Kiểm tra **các language tag và chức năng thật** của ứng dụng trên image đã build.

Tài liệu: [jlink Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).

## 20. Kiểm tra module có sẵn và module đã được resolve

Hai khái niệm khác nhau:

- **Module available in image**: hệ thống có artifact module.
- **Module resolved into boot layer**: module được đưa vào cấu hình chạy cụ thể.

Ví dụ snippet:

~~~java
boolean available = ModuleFinder.ofSystem()
        .find("jdk.localedata").isPresent();

boolean resolved = ModuleLayer.boot()
        .findModule("jdk.localedata").isPresent();
~~~

Cần import `java.lang.module.ModuleFinder`; `ModuleLayer` nằm trong `java.lang`.

Có thể kiểm tra modules trong image:

~~~bash
./image-localized/bin/java --list-modules
~~~

Với Windows, đường dẫn file chạy dùng `image-localized\bin\java.exe`. Không dùng thông tin “JDK trên máy dev có `jdk.localedata`” để suy luận image container production cũng có.

**Đặc biệt quan trọng:** Một test chạy trên `java` nằm trong PATH có thể vô tình dùng full JDK, thay vì chính `image-localized/bin/java` vừa tạo. CI phải chạy **binary của image ứng dụng triển khai**.

## 21. So sánh hai runtime images công bằng

Ma trận kiểm thử nên tách:

| Run | JDK | Runtime image | Locale data | Mục tiêu |
| --- | --- | --- | --- | --- |
| A | Cũ | Full JDK | Full/expected | Baseline |
| B | Mới | Full JDK | Full/expected | Đo drift do nâng JDK/dữ liệu |
| C | Mới | `jlink` image đầy đủ locale cần dùng | Có `jdk.localedata`/include-locale | Đo ảnh hưởng image |
| D | Mới | `jlink` image tối giản | Không đủ locale coverage | Negative/compatibility test |

Không so A trực tiếp với D rồi kết luận “nâng JDK làm định dạng sai” khi **đồng thời** thay JDK, module graph, dữ liệu locale và image packaging.

Thay từng biến nếu có thể:
- A → B cô lập JDK/distribution;
- B → C cô lập khác biệt full JDK vs target image;
- C → D xác định tác động của dữ liệu locale bị lược bớt.

Nếu không thể giữ nguyên mọi biến (ví dụ vendor khác), phải ghi nhận và **không quy nguyên nhân quá tự tin**.

## 22. Tập locale khả dụng và fallback cần đo riêng

Các API như:

~~~java
NumberFormat.getAvailableLocales();
DateFormat.getAvailableLocales();
Locale.getAvailableLocales();
~~~

trả những danh sách khả dụng theo **service**, và có thể không giống nhau. Một locale xuất hiện trong một danh sách không bảo đảm **mọi API dịch/ngày/số** đều có cùng mức hỗ trợ.

`Locale.forLanguageTag("vi-VN")` luôn có thể tạo đối tượng `Locale` hợp lệ ngay cả khi runtime không có đầy đủ dữ liệu riêng cho locale đó. Việc tạo object **không chứng minh** có sẵn format data bản địa.

Để kiểm tra runtime image, phải:
1. Tạo formatter cho locale sản phẩm sử dụng.
2. Chạy các phép đo date/number/currency/message.
3. Kiểm tra output và metadata.
4. Xác nhận locale/provider cụ thể đã được included/resolved.
5. Có **negative test** về thiếu locale data nếu cần bảo đảm image build đúng.

`ResourceBundle.getBundle` có cơ chế fallback riêng. Không dùng kết quả fallback của ResourceBundle để kết luận dữ liệu CLDR của `NumberFormat` đã được đóng gói đầy đủ.

## 23. Startup properties và môi trường là một phần của snapshot

Các thuộc tính như:

~~~text
-Djava.locale.providers=CLDR
-Duser.language=vi
-Duser.country=VN
-Duser.timezone=Asia/Ho_Chi_Minh
~~~

có thể ảnh hưởng các default values ở startup. Trong phép so sánh có kiểm soát, tốt nhất là **truyền `Locale` và `ZoneId` trực tiếp cho API** thay vì phụ thuộc các defaults.

Nếu có lý do để test default locale, hãy thiết lập chúng khi startup và ghi lại **cả FORMAT/DISPLAY locale**. `Locale.getDefault()` không luôn phản ánh mọi trường hợp phân biệt category nếu ứng dụng thay đổi default cho từng category.

Đừng gọi `System.setProperty("java.locale.providers", ...)` ở giữa chương trình rồi so hai kết quả trong cùng JVM như thể provider được thay nóng. **Provider selection cần được thử bằng những JVM process độc lập**, với cờ startup khác nhau.

## 24. So sánh hành vi parser, không chỉ formatter

Nâng CLDR/JDK cũng có thể làm thay đổi **những chuỗi được parser chấp nhận** hoặc cách parser diễn giải ký tự phân nhóm/thập phân.

Ví dụ người dùng gửi:

~~~text
12 345,67
12 345,67
12 345,67
~~~

Ba dòng có thể chứa **U+0020**, **U+00A0** và **U+202F**. Đừng xem chúng giống nhau chỉ vì font render gần giống.

Một phép thử parse nên kiểm:
- `NumberFormat.parse` có trả kết quả?
- Parser tiêu thụ **toàn bộ chuỗi** hay chỉ tiền tố?
- Giá trị số sau parse có đúng không?
- Locale/provider được dùng là gì?
- Mọi ký tự không hợp lệ có bị bỏ qua âm thầm không?

`ParsePosition` giúp kiểm tra độ dài đã tiêu thụ:

~~~java
ParsePosition pos = new ParsePosition(0);
Number value = numberFormat.parse(input, pos);

boolean complete = value != null
        && pos.getIndex() == input.length();
~~~

Đây là snippet; cần import `ParsePosition`, `NumberFormat`; `numberFormat` và `input` đã được khởi tạo.

**Không coi parse thành công là tương đương với chuỗi hợp lệ toàn phần**: một parser có thể chỉ đọc tiền tố. Khi nâng JDK, test cần theo dõi cả **giá trị** và **chỉ số tiêu thụ**, không chỉ exception.

## 25. Cách xử lý golden tests khi có khác biệt hợp lệ

Một snapshot vàng (*golden file*) giúp phát hiện thay đổi không mong muốn, nhưng nếu máy móc bắt output mới giống byte-for-byte vĩnh viễn sẽ gây khó nâng cấp CLDR.

Quy trình review:

1. **Tạo baseline có metadata** từ runtime production hiện tại.
2. **Tạo candidate** trên runtime/image mới.
3. **Diff theo Unicode code point** cho tất cả `DATA`.
4. **Phân nhóm**: number, currency, date/time, week/calendar, timezone, ResourceBundle, message.
5. **Xác định nguyên nhân** dựa vào CLDR/provider/TZDB/image, không đoán từ chuỗi đơn lẻ.
6. **Review tác động**: UI, parser, serialization, test, báo cáo, khách hàng.
7. **Chấp thuận hoặc sửa** với lý do có thể truy vết.
8. **Chỉ cập nhật golden sau khi đã review**, lưu cả baseline cũ/diff và quyết định.

Nếu một dấu phân nhóm đổi U+00A0 sang U+202F và đó là định dạng địa phương được dữ liệu CLDR mới khuyến nghị, có thể chấp nhận cập nhật snapshot UI. Nếu cùng định dạng này đang được ghi vào CSV làm mã máy đọc và gây lỗi parser, giải pháp đúng là **không sử dụng định dạng UI làm protocol**, thay vì ép Java mãi dùng ký tự cũ ở mọi nơi.

## 26. Kiểm thử định dạng giao thức khác kiểm thử giao diện

**Giao thức dữ liệu** thường cần ký pháp ổn định độc lập locale: ISO 8601 cho thời gian, JSON number, hoặc định dạng số/currency được định nghĩa rõ.

**Giao diện** cần theo quy ước từng locale và có thể thay đổi khi dữ liệu CLDR cập nhật.

Ví dụ:
- Gửi timestamp giữa các service: dùng `Instant` và chuẩn serialization rõ ràng.
- Hiển thị timestamp trong email tiếng Việt: dùng `DateTimeFormatter` với locale/timezone phù hợp.
- Lưu số tiền: lưu `BigDecimal` cùng currency code, không lưu kết quả `NumberFormat.getCurrencyInstance` làm giá trị nguồn.
- Hiển thị giá tiền: format `BigDecimal` theo locale và currency đã chọn.

Đừng giải quyết test snapshot thay đổi bằng cách đặt một locale cho toàn ứng dụng. Cần phân biệt **contract ổn định** và **presentation thay đổi hợp lệ**.

## 27. Kiểm thử Unicode và nguồn dữ liệu Character

Bản nâng JDK có thể cập nhật Unicode data. Một code point được nhận diện là `UNASSIGNED` ở phiên bản cũ có thể trở thành chữ cái/biểu tượng ở phiên bản mới. Những hàm cần xem nếu ứng dụng phụ thuộc chúng:

~~~java
Character.isLetter(codePoint);
Character.isDigit(codePoint);
Character.getType(codePoint);
Character.UnicodeScript.of(codePoint);
Normalizer.normalize(text, Normalizer.Form.NFC);
~~~

Đây là snippet, `codePoint` và `text` đã có.

Nếu validation username, tìm kiếm, phân loại chữ số hoặc chuyển case dựa trên Unicode properties, cần test **các code point ở ranh giới chính sách**. Không nhầm một thay đổi Unicode property với thay đổi CLDR locale formatting.

**An toàn:** Không được tự động nới chính sách định danh bảo mật chỉ vì runtime mới nhận diện thêm nhiều code point. Quy tắc ứng dụng phải có profile/phiên bản được quyết định chủ động, rồi mới nâng dữ liệu khi thích hợp.

## 28. Trường hợp `jlink` image thiếu provider hoặc resource bundle

Khi chuyển sang runtime image:
- `jdk.localedata` có thể vắng mặt;
- service provider tùy biến có thể chưa được đưa vào module graph;
- resource `.properties` có thể bị loại khỏi artifact;
- ứng dụng dùng `ResourceBundleProvider`/SPI có thể cần binding/configuration;
- locale fallback có thể trả chuỗi khác mà không ném exception.

Đối với `ResourceBundle`, test phải xác nhận **file/provider được đóng gói** và **key/locale đang được tìm đúng nguồn**. Đối với CLDR, test phải xác nhận **formatter output** trên runtime image.

**Không chữa mọi lỗi bằng `--add-modules jdk.localedata`** nếu nguyên nhân là ứng dụng quên copy `Messages_vi.properties`. Và không chữa file thiếu bằng cách chỉnh `java.locale.providers`. Hai lớp tài nguyên này liên quan nhưng **không phải một loại**.

## 29. Các bài test nên có trong CI

Tổ chức test thành ba nhóm:

**Nhóm 1 — Behavioral contract, chạy mọi PR**
- `Locale`/`ZoneId` cố định.
- Input ngày/số/tiền/mẫu cố định.
- Parser round-trip và tiêu thụ đầy đủ.
- Resource bundle keys và MessageFormat arguments.
- Các quy tắc sản phẩm **bắt buộc bất biến**.

**Nhóm 2 — Snapshot drift, chạy khi nâng JDK/image**
- Golden output codepoints cho locale chính.
- Metadata Java vendor/build/provider/TZDB/module.
- Diff nguyên chuỗi, phân loại theo service/locale.
- Các màn hình quan trọng: invoice, email, payment, lịch.
- Review thủ công trước khi cập nhật expected.

**Nhóm 3 — Image integration, chạy trên artifact deploy**
- Binary `bin/java` của image `jlink` thật.
- Module list, `jdk.localedata`, provider availability.
- ResourceBundle module/provider lookup.
- Định dạng và parse locale chính.
- Kiểm tra root fallback hoặc missing locale theo policy.

Nên giữ kết quả baseline/candidate/diff dưới dạng CI artifacts có version. Đừng chỉ xuất screenshot của UI hoặc xóa metadata khiến lần so sau không biết môi trường nào tạo ra output.

## 30. Khi test thất bại, làm thế nào để phân loại?

| Quan sát | Khả năng cần kiểm | Bước tiếp theo |
| --- | --- | --- |
| `fr-FR.number` đổi dấu nhóm | CLDR/provider | So code points, provider order |
| `fr-FR.currency` đổi vị trí/ký hiệu | Locale/currency data | Review UI và số tiền |
| Date/time text khác | CLDR/format provider | So locale, style, pattern |
| Zoned date offset khác | TZDB | So fixed instant, zone, TZDB version |
| Chỉ `jlink` image khác full JDK | Module/locale coverage | Kiểm `jdk.localedata` và include-locales |
| Mọi locale khác do default | Cấu hình startup | Ghi FORMAT locale/timezone, truyền explicit |
| `MessageFormat` khác nhưng raw pattern giống | Formatter locale/provider | So fixed args và format data |
| Bản dịch text khác và raw bundle cũng khác | Ứng dụng/package | So bundle version và key |
| Lỗi parser sau nâng | Number/date parsing rules | Kiểm `ParsePosition`, locale |
| Lỗi test chỉ xuất hiện trên CI | Environment hoặc image khác | Dùng chính binary runtime của CI |

Đây là các **giả thuyết kiểm tra**, không phải kết luận tự động. Một key có thể thay đổi vì nhiều nguyên nhân cùng lúc, đặc biệt khi nâng container và JDK đồng thời.

## 31. Tránh những lỗi thường gặp

1. **Chỉ snapshot `String` bằng mắt**: bỏ sót NBSP, NNBSP, combining mark.
2. **Không ghi JDK vendor/update**: không tái hiện được nguồn dữ liệu.
3. **Không ghi provider order**: không biết test dùng CLDR, HOST hay SPI.
4. **So full JDK cũ với jlink image mới rồi quy hết cho JDK**: thay nhiều biến.
5. **Dùng ngày hôm nay/default timezone**: snapshot thay đổi vì thời gian chạy.
6. **Dùng default locale ngầm**: khác máy developer/CI.
7. **Chỉ kiểm `Locale.forLanguageTag` tạo được object**: không chứng minh có locale data.
8. **Lấy số locale available làm bằng chứng đủ mọi API**: mỗi service có coverage riêng.
9. **Coi `COMPAT` là lựa chọn lâu dài**: legacy data đã bị loại bỏ từ JDK 23.
10. **Coi mọi diff là regression**: cập nhật CLDR hợp lệ vẫn có thể đổi output.
11. **Coi mọi diff là chấp nhận được**: có thể phá hợp đồng giao thức/UI.
12. **Tự normalize Unicode whitespace trước exact diff**: che khác biệt thực.
13. **Tự cập nhật golden theo candidate**: loại bỏ cơ hội review.
14. **Quên kiểm parser**: hiển thị đúng chưa chắc parse input cũ được.
15. **Quên kiểm TZDB**: offset DST có thể thay đổi độc lập CLDR.
16. **Quên module `jdk.localedata` khi tạo image**: thiếu coverage locale.
17. **Test PATH `java` thay vì image thực**: kết quả không đại diện production.
18. **Đánh đồng ResourceBundle của app với CLDR**: gây chẩn đoán sai.
19. **Snapshot dữ liệu người dùng thật**: có thể rò rỉ PII/secret.
20. **Cố đóng băng mọi định dạng UI**: cản trở cập nhật ngôn ngữ có lợi.

## 32. Câu hỏi ôn tập kèm đáp án

**Câu 1.** Vì sao cùng code Java mà đầu ra `NumberFormat` có thể đổi khi nâng JDK?

**Đáp án:** Dữ liệu CLDR/provider, cấu hình locale hoặc triển khai JDK có thể thay đổi mà không cần sửa code.

**Câu 2.** `java.locale.providers=COMPAT` có dùng được mãi để giữ output cũ?

**Đáp án:** Không. Legacy `COMPAT/JRE` locale data bị loại bỏ từ JDK 23; phải migrate sang CLDR và test lại.

**Câu 3.** Tại sao so chuỗi phân nhóm số bằng mắt không đủ?

**Đáp án:** U+0020, U+00A0 và U+202F có thể trông giống nhau nhưng khác code point.

**Câu 4.** Một `jlink` image không có `jdk.localedata` có nhất thiết giống full JDK không?

**Đáp án:** Không. Image có thể thiếu dữ liệu locale mở rộng nên cần kiểm thử trên chính image thật.

**Câu 5.** `--include-locales` cần chú ý gì?

**Đáp án:** Cần module `jdk.localedata` khi dùng plugin và xác minh các locale/service ứng dụng thật sự cần đã được giữ lại.

**Câu 6.** Vì sao nên ghi `TZDB version` khi test múi giờ?

**Đáp án:** Quy tắc DST/offset có thể được cập nhật độc lập với CLDR và thay đổi kết quả tại một instant cố định.

**Câu 7.** Có nên dùng `LocalDate.now()` trong golden test nâng JDK?

**Đáp án:** Không, nếu muốn cô lập thay đổi runtime. Dùng một `LocalDate` cố định.

**Câu 8.** Nếu chỉ metadata Java version khác nhưng mọi dòng `DATA` giống nhau, có regression formatting không?

**Đáp án:** Chưa có bằng chứng regression trong tập probes được đo; không thể suy ra mọi hành vi đều giống nhau ngoài phạm vi test.

**Câu 9.** Nếu một parser chỉ đọc tiền tố của chuỗi mới, `parse` không ném exception thì đã đạt chưa?

**Đáp án:** Chưa. Kiểm tra `ParsePosition.getIndex() == input.length()` để biết toàn bộ input được tiêu thụ.

**Câu 10.** Vì sao không được cập nhật golden tự động cho mọi khác biệt?

**Đáp án:** Có thể che regression. Cần phân loại nguyên nhân, review tác động và chấp nhận theo quyết định sản phẩm.

## 33. Checklist nâng cấp thực tế

- [ ] Liệt kê các locale, currency, calendar và timezone sản phẩm hỗ trợ.
- [ ] Ghi version/build/vendor của runtime baseline và candidate.
- [ ] Ghi `java.locale.providers`, default FORMAT/DISPLAY locale và timezone.
- [ ] Ghi TZDB version, image ID và module/locale coverage.
- [ ] Biên dịch cùng nguồn/cùng bộ probe tương thích hai runtime.
- [ ] Cố định input `BigDecimal`, `LocalDate`, `Instant` và sample args.
- [ ] Xuất formatted text dưới dạng Unicode code points.
- [ ] So sánh `NumberFormat`, `DateTimeFormatter`, `DateFormat`, `MessageFormat`, `ResourceBundle` và parser.
- [ ] Chạy riêng trên full JDK và **runtime image deploy thật**.
- [ ] Xác minh `jdk.localedata` và `--include-locales` nếu dùng `jlink`.
- [ ] Phân loại differences theo CLDR/provider, TZDB, app resources hoặc environment.
- [ ] Review ảnh hưởng UI/format/protocol và tính đúng ngôn ngữ.
- [ ] Chỉ sau review mới cập nhật golden và ghi lý do.
- [ ] Giữ bản so sánh làm artifact cho lần migration tiếp theo.

## 34. Kết luận

Một phép nâng JDK, CLDR hoặc runtime image **không được đánh giá chỉ bằng “code còn compile”**. Phần localization cần các phép đo có thể tái hiện: **cùng input, cùng locale, cùng timezone, cùng provider policy, khác runtime một cách có kiểm soát**.

Hãy xây **snapshot có fingerprint môi trường**, xuất cả **Unicode code points** của kết quả và dùng một **diff được review**. Tách lỗi **định dạng giao diện** khỏi **hợp đồng dữ liệu máy đọc**; tách **CLDR** khỏi **TZDB**; tách dữ liệu locale của JDK khỏi **resource bundle của ứng dụng**. Với `jlink`, chạy test trên chính image triển khai, không chỉ full JDK ở máy phát triển.

**Ghi nhớ:** **Khác biệt đầu ra là tín hiệu cần điều tra**, không mặc định là bug cũng không mặc định được phép bỏ qua. Quy trình migration tốt là **phát hiện → tái hiện → xác định nguyên nhân → đánh giá tác động → chấp thuận hoặc sửa → cập nhật baseline có kiểm soát**.

**Nguồn tham khảo Java và Oracle:**
- [Oracle JDK 17 Internationalization Enhancements](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html).
- [Java 17 LocaleServiceProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html).
- [JDK 23 Removed Tools and Components](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html).
- [JDK 17 jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [Java 17 NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html).
- [Java 17 DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java 17 ZoneRulesProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRulesProvider.html).