# Khác biệt nhà cung cấp và dữ liệu giữa các phiên bản JDK

## 1. Vì sao cùng mã Java nhưng kết quả bản địa hóa có thể thay đổi?

`Locale` chỉ biểu diễn yêu cầu về ngôn ngữ, vùng lãnh thổ và một số tùy chọn. Nó **không phải bản sao cố định của dữ liệu** dùng để hiển thị ngày, số, tên tháng hoặc so sánh chuỗi. Những API như `NumberFormat`, `DateFormat`, `DateTimeFormatter` và `Collator` thường sử dụng dữ liệu locale có sẵn trong Java runtime.

Vì vậy, ứng dụng chạy cùng source code và cùng `Locale.FRANCE` vẫn có thể sinh chuỗi khác khi nâng cấp JDK, thay nhà cung cấp dữ liệu, chạy trên hệ điều hành khác hoặc dùng runtime image được đóng gói tối giản.

Ba thành phần phải phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Định danh locale | `Locale.forLanguageTag("vi-VN")` | Yêu cầu quy tắc tiếng Việt tại Việt Nam |
| API nhạy với locale | `NumberFormat`, `DateFormat`, `Collator` | Format, parse hoặc so sánh |
| Nguồn dữ liệu | `CLDR`, `SPI`, `HOST`, legacy `COMPAT/JRE` | Cung cấp mẫu ngày, dấu số, tên hiển thị và quy tắc sắp xếp |

```text
Locale yêu cầu
   ↓
API locale-sensitive
   ↓
Thứ tự provider được JVM đọc lúc khởi động
   ├── CLDR
   ├── SPI
   ├── HOST (nếu môi trường hỗ trợ)
   └── COMPAT/JRE (dữ liệu cũ, chỉ trong các JDK trước 23)
   ↓
Chuỗi hiển thị / kết quả parse / thứ tự so sánh
```

**Một locale hợp lệ không đồng nghĩa mọi API đều có đầy đủ dữ liệu riêng cho locale đó.** Một provider có thể hỗ trợ định dạng số nhưng thiếu một dịch vụ khác; runtime có thể xét provider/locale fallback. Khi muốn có hành vi được bảo đảm, cần thử đúng API trên runtime triển khai.

## 2. CLDR và các mốc JDK quan trọng

CLDR (*Common Locale Data Repository*) là nguồn dữ liệu quốc tế hóa do Unicode Consortium duy trì. Các dữ liệu liên quan gồm mẫu hiển thị ngày/giờ, dấu grouping, dấu thập phân, tên tháng/ngày, tên vùng/ngôn ngữ, ký hiệu tiền tệ và một số quy tắc khác.

- **JDK 8:** có dữ liệu legacy JRE; CLDR đã được tích hợp nhưng không phải nguồn mặc định ưu tiên như các bản sau.
- **JDK 9:** dữ liệu CLDR trở thành nguồn mặc định được ưu tiên.
- **JDK 9–22:** dữ liệu cũ `COMPAT` (alias lịch sử `JRE`) còn được cung cấp để hỗ trợ chuyển đổi.
- **JDK 21:** việc chỉ định dữ liệu legacy được cảnh báo trước khi loại bỏ.
- **JDK 23 trở đi:** legacy locale data `COMPAT/JRE` **đã bị loại bỏ**. Chỉ thêm tên `COMPAT` vào thuộc tính JVM không khôi phục dữ liệu cũ.

Một số phiên bản CLDR theo tài liệu JDK:

| JDK | CLDR |
| --- | --- |
| 17 | 39 |
| 21 | 43 |
| 22 | 44 |
| 23 | 45 |
| 24 | 46 |
| 25 | 47 |
| 26 | 48 |

Các con số thể hiện **data version**, không có nghĩa tất cả locale đều thay đổi ở mỗi bản. Tuy vậy, dữ liệu khác nhau có thể làm test snapshot hoặc parser đọc chuỗi cũ thất bại. Dòng JDK có cùng Java language level không bảo đảm giống dữ liệu locale.

## 3. Bốn nhà cung cấp locale

### `CLDR`

Provider mặc định được ưu tiên từ JDK 9, dựa trên dữ liệu CLDR đóng gói trong JDK. Bản JDK mới có thể chứa bản CLDR mới. Dùng rõ:

```bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

Đây là ví dụ chạy chương trình `LocaleDataProbe` được định nghĩa ở phần sau.

### `COMPAT/JRE`

Trong JDK 9–22, cung cấp dữ liệu tương thích với JDK trước 9. Có thể dùng để chẩn đoán migration từ JDK 8:

```bash
java -Djava.locale.providers=COMPAT,CLDR -cp . LocaleDataProbe
```

Chỉ dùng thử trên các bản JDK **còn có legacy data**. Từ JDK 23, cơ chế này không còn là cách quay về định dạng legacy; nếu bắt buộc tương thích phải giữ một parser/mẫu riêng hoặc triển khai dịch vụ phù hợp.

### `SPI`

*Service Provider Interface* cho phép ứng dụng cung cấp những dịch vụ locale qua các lớp như `NumberFormatProvider`, `DateFormatProvider`, `DecimalFormatSymbolsProvider`, `CollatorProvider` và `LocaleNameProvider`.

Provider có thể được đóng gói trên classpath bằng `META-INF/services/…` hoặc dưới dạng module khai báo `provides … with …`. Nó phải công bố những locale mà nó hỗ trợ. Muốn ưu tiên provider ngoài, có thể dùng:

```text
-Djava.locale.providers=SPI,CLDR
```

**Liệt kê SPI không tự tạo nhà cung cấp**; phải có implementation được cài/đăng ký. Provider không hỗ trợ dịch vụ/locale nào thì runtime có thể tìm đến CLDR.

### `HOST`

Có thể phản ánh một số thiết lập locale của hệ điều hành/người dùng, đặc biệt số, ngày, giờ và tiền tệ. Không phải mọi JDK/vendor/OS đều hỗ trợ giống nhau.

```text
-Djava.locale.providers=HOST,CLDR
```

Với backend nhiều người dùng, phụ thuộc cấu hình hệ điều hành máy chủ thường không phải lựa chọn tốt nếu ứng dụng đòi kết quả đồng nhất.

## 4. `java.locale.providers`: cấu hình khi khởi động JVM

Thuộc tính hệ thống `java.locale.providers` chọn **thứ tự ưu tiên provider**. Ví dụ:

```bash
java -Djava.locale.providers=CLDR -cp . Main
java -Djava.locale.providers=SPI,CLDR -cp . Main
java -Djava.locale.providers=HOST,SPI,CLDR -cp . Main
```

Các quy tắc:

1. Truyền property vào **JVM launcher**, trước tên class hoặc JAR.
2. Nó được đọc và cached khi cơ chế locale service khởi tạo; **không** dựa vào `System.setProperty` trong một request để đổi provider của JVM đang chạy.
3. Provider đầu tiên chỉ được dùng khi có service/locale phù hợp. Một số API có cơ chế fallback.
4. `java.locale.providers` khác với `Locale.getDefault()`. Provider là nguồn dữ liệu; default locale là giá trị được dùng khi bạn bỏ qua tham số locale.
5. Sau JDK 23, `COMPAT`/`JRE` không khôi phục dữ liệu legacy.
6. Với hệ thống đa người dùng, **truyền locale tường minh** thay vì gọi `Locale.setDefault` mỗi request.

Cùng một property không bảo đảm output giống nhau nếu JDK đã tích hợp các bản CLDR khác, thiếu module data hoặc dùng SPI/HOST từ môi trường riêng.

## 5. Các lĩnh vực chịu ảnh hưởng

### Số và ký hiệu phân cách

`NumberFormat`, `DecimalFormatSymbols` và `DecimalFormat` có thể dùng các dấu phân nhóm/decimal khác. Đặc biệt những dấu cách dễ bị nhầm:

| Unicode | Ký tự |
| --- | --- |
| `U+0020` | Space ASCII |
| `U+00A0` | No-break space |
| `U+202F` | Narrow no-break space |

Chúng có thể trông tương tự nhưng khác code point. Một test so sánh byte, đầu vào copy/paste hoặc parser được viết theo dấu cố định có thể thất bại. Hãy in mã Unicode của separator, không chỉ chụp ảnh màn hình.

### Ngày giờ

`DateFormat.getDateInstance(style, locale)` và `DateTimeFormatter.ofLocalizedDate(style)` sử dụng mẫu địa phương; thứ tự ngày/tháng/năm, dấu ngăn cách, tên tháng, độ dài năm và cách biểu diễn giờ có thể khác.

Nếu đã lưu dữ liệu thành chuỗi được tạo từ `FormatStyle.SHORT` hoặc `DateFormat.SHORT`, runtime mới có thể không parse lại giống runtime cũ. **Định dạng hiển thị không phải schema lưu trữ/giao thức.** Lưu `LocalDate`/`Instant` hoặc ISO text xác định rõ, sau đó format theo locale khi hiển thị.

### Tiền tệ và tỷ lệ

Vị trí ký hiệu tiền, tên/ký hiệu currency, khoảng trắng và pattern phần trăm có thể phụ thuộc locale data. `NumberFormat.getCurrencyInstance(locale)` **không thực hiện chuyển tỷ giá**. Luôn lưu currency code, amount và quy tắc làm tròn theo nghiệp vụ.

### Sắp xếp theo ngôn ngữ

`Collator.getInstance(locale)` có thể thay đổi thứ tự/cách coi chuỗi tương đương theo dữ liệu locale và strength. Điều này ảnh hưởng sort, tìm kiếm, `TreeSet`/`TreeMap` dùng comparator, cache và phân trang.

Không lưu collation key như một định dạng vĩnh viễn không version. Khi thay dữ liệu collation, kiểm tra có cần rebuild index và tie-breaker theo ID hay không.

### Tên hiển thị

`Locale.getDisplayName(displayLocale)` và `Currency.getDisplayName(locale)` cũng chịu ảnh hưởng dữ liệu. Không dùng tên quốc gia/ngôn ngữ đã dịch làm khóa lâu dài; lưu mã chuẩn tách biệt.

## 6. Chương trình Java 17+: khảo sát runtime thực tế

Một cách phát hiện khác biệt là in **phiên bản Java, provider property và ký hiệu dưới dạng code point**.

Tạo tệp **`LocaleDataProbe.java`**:

```java
import java.text.Collator;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleDataProbe {
    private static String hex(int cp) {
        return String.format(Locale.ROOT, "U+%04X", cp);
    }

    private static void inspect(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        String number = NumberFormat.getNumberInstance(locale)
                .format(1234567.89);
        String date = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale)
                .format(LocalDate.of(2026, 10, 28));
        Collator c = Collator.getInstance(locale);

        System.out.println("locale=" + locale.toLanguageTag());
        System.out.println("  grouping=" +
                hex(symbols.getGroupingSeparator()));
        System.out.println("  decimal=" +
                hex(symbols.getDecimalSeparator()));
        System.out.println("  number=" + number);
        System.out.println("  date=" + date);
        System.out.println("  compare(a,ä)=" +
                Integer.signum(c.compare("a", "ä")));
    }

    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("providers=" +
                System.getProperty(
                        "java.locale.providers", "<unset>"));

        inspect(Locale.US);
        inspect(Locale.GERMANY);
        inspect(Locale.FRANCE);
        inspect(Locale.forLanguageTag("vi-VN"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 LocaleDataProbe.java
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

**Output phụ thuộc môi trường, nên không có một stdout cố định chính xác cho mọi JDK.** Chương trình in ba dòng runtime (`java.version`, `java.vendor`, `providers`), sau đó mỗi locale có năm dòng về grouping/decimal/number/date/collator.

```text
java.version=<phiên bản JDK>
java.vendor=<nhà cung cấp JDK>
providers=<CLDR hoặc cấu hình đã truyền>
locale=en-US
  grouping=U+....
  decimal=U+....
  number=...
  date=...
  compare(a,ä)=...
...
```

Đây chỉ là **sơ đồ đầu ra**, không phải snapshot chính xác. `System.getProperty("java.locale.providers")` cho biết cấu hình được truyền, **không chứng minh** provider đã xử lý mọi service. Cần so trực tiếp kết quả trên các process JVM với cùng locale.

## 7. Mẫu tường minh và kết quả Java 17+

Một pattern rõ ràng giúp giảm phụ thuộc **mẫu số mặc định** nhưng vẫn có thể lấy các ký hiệu từ locale data.

Tạo **`ExplicitLocalePatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitLocalePatternDemo {
    private static DecimalFormat number(Locale locale) {
        return new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale));
    }

    public static void main(String[] args) {
        DecimalFormat us = number(Locale.US);
        DecimalFormat de = number(Locale.GERMANY);

        System.out.println("US=" + us.format(1234567.89));
        System.out.println("DE=" + de.format(1234567.89));

        System.out.println("ISO=" +
                DateTimeFormatter.ISO_LOCAL_DATE.format(
                        LocalDate.of(2026, 10, 28)));

        ParsePosition position = new ParsePosition(0);
        Number parsed = de.parse("1.234,56", position);
        System.out.println("parsed=" + parsed +
                ", end=" + position.getIndex() +
                ", error=" + position.getErrorIndex());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExplicitLocalePatternDemo.java
java -cp . ExplicitLocalePatternDemo
```

Đầu ra trên JDK hiện đại với symbols Đức/Mỹ thông dụng:

```text
US=1,234,567.89
DE=1.234.567,89
ISO=2026-10-28
parsed=1234.56, end=8, error=-1
```

Phân biệt **pattern chuẩn** `#,##0.00` với **dấu thực tế khi hiển thị** từ `DecimalFormatSymbols`. Pattern không cố định mã Unicode của dấu phân cách trên mọi runtime. Với dữ liệu máy-máy, ISO date và định dạng giao thức cụ thể phù hợp hơn localized text.

## 8. Kiểm thử hợp đồng mà không đóng băng từng dấu địa phương

Golden tests cố định output có ích nếu sản phẩm yêu cầu đúng mẫu đó và đã pin JDK/provider. Nhưng các contract tests chung nên kiểm tra **ý nghĩa**, tránh coi từng dấu cách CLDR là bất biến.

Tạo **`LocaleDataContractChecks.java`**:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleDataContractChecks {
    private static void check(boolean valid) {
        if (!valid) throw new AssertionError("Check failed");
    }

    private static void roundTrip(Locale locale) {
        NumberFormat f = NumberFormat.getIntegerInstance(locale);
        f.setGroupingUsed(false);
        String text = f.format(1234567L);
        ParsePosition p = new ParsePosition(0);
        Number value = f.parse(text, p);

        check(value != null);
        check(p.getIndex() == text.length());
        check(value.longValue() == 1234567L);
    }

    public static void main(String[] args) {
        check(DateTimeFormatter.ISO_LOCAL_DATE.format(
                LocalDate.of(2026, 10, 28))
                .equals("2026-10-28"));

        roundTrip(Locale.US);
        roundTrip(Locale.GERMANY);
        roundTrip(Locale.forLanguageTag("vi-VN"));

        System.out.println("4 contract groups passed");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocaleDataContractChecks.java
java -cp . LocaleDataContractChecks
```

Đầu ra khi đạt các điều kiện:

```text
4 contract groups passed
```

Có một nhóm ISO và ba nhóm số nguyên. Mỗi nhóm số lại có các kiểm tra giá trị và đã tiêu thụ toàn bộ text. **Round-trip cùng một runtime không chứng minh runtime mới đọc được chuỗi được ghi từ JDK cũ**; việc đó cần migration tests riêng.

## 9. Quy trình đối chiếu hai JDK

1. Ghi JDK feature/update version, vendor/build, OS và runtime image.
2. Biên dịch cùng source cho phiên bản Java chung (ví dụ `javac --release 17` trên JDK mới).
3. Chạy **mỗi JDK ở một process mới** với `java.locale.providers` đã chọn.
4. Dùng cùng language tag, input, zone, style và loại API.
5. So code point của dấu phân cách, giá trị format/parse và thứ tự collation.
6. Nếu chỉ khác trên container, kiểm tra default locale, module `jdk.localedata` và HOST/SPI.
7. Đánh giá thay đổi có được sản phẩm chấp nhận hay cần migration parser, không chỉ cập nhật snapshot.
8. Không thử `COMPAT` để rollback JDK 23+, nơi dữ liệu legacy đã bị gỡ.

Ví dụ trên Linux/macOS với hai đường dẫn Java **minh họa**:

```bash
/path/to/jdk17/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe > jdk17.txt
/path/to/jdk25/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe > jdk25.txt
diff -u jdk17.txt jdk25.txt
```

Trên Windows PowerShell, dùng toán tử `&` với đường dẫn Java thật, và công cụ so nội dung như `Compare-Object`. Không coi những đường dẫn ví dụ là JDK đã được cài.

Thông tin cần có trong bản chẩn đoán:

```text
JDK version + vendor + build
java.locale.providers lúc startup
locale tag + Unicode extensions
API/style/pattern/strength được sử dụng
zone/chronology/currency (nếu có)
code point của dấu phân cách
format result, parse result và vị trí kết thúc
runtime modules, jdk.localedata, OS
```

## 10. `jlink` và module `jdk.localedata`

Một runtime image tự tạo bằng `jlink` có thể không chứa cùng tập locale như full JDK. Module `jdk.localedata` cung cấp dữ liệu locale bổ sung; `jlink` có plugin `--include-locales`.

Ví dụ:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=en,vi,fr --output custom-runtime
```

Đây chỉ là minh họa đóng gói locale; một ứng dụng thực tế còn cần module khác theo dependency. Hãy kiểm tra runtime bằng `java --list-modules` và chạy `LocaleDataProbe` **trên đúng image triển khai**.

Ngay cả khi cùng JDK major version, khác vendor, provider startup, custom modules hoặc OS có thể làm kết quả khác. Đừng kết luận mọi chênh lệch đều do CLDR.

## 11. Đừng nhầm CLDR với dữ liệu và cơ chế khác

| Hiện tượng | Điều cần điều tra |
| --- | --- |
| Số, dấu grouping khác | CLDR, provider, DecimalFormatSymbols |
| Mẫu ngày/tên tháng khác | Locale data và FormatStyle |
| Giờ bị lệch, DST khác | `ZoneId`, timezone database `tzdb` |
| Tên múi giờ hiển thị khác | Locale display names và timezone information |
| Sắp xếp tên khác | `Collator`, strength, version |
| Tiếng Việt bị méo mã | Encoding/decoding, không nhất thiết CLDR |
| Văn bản đúng code point nhưng ô vuông | Font/glyph/renderer |
| Nhãn nghiệp vụ chưa dịch | `ResourceBundle`/bản dịch ứng dụng |

CLDR **không tự cung cấp bản dịch của mọi thông điệp sản phẩm**. `ResourceBundle` vẫn cần các tệp/nguồn translation do ứng dụng quản lý.

## 12. Chiến lược migration

**Trước khi nâng cấp:** kiểm kê `DateFormat`, `NumberFormat`, `DecimalFormatSymbols`, `Collator`, `DateTimeFormatter.ofLocalized...`, `Locale.getDisplayName`, các lời gọi thiếu `Locale` và cấu hình `java.locale.providers`. Kiểm tra chỗ lưu ngày/số đã format theo locale làm dữ liệu.

**Khi thử JDK mới:** chạy probe trên runtime đích, test số/ngày/currency/sort cho những locale chính; kiểm tra cả format lẫn parse, nhất là dữ liệu legacy. Một parser có thể chỉ đọc được tiền tố hợp lệ, nên xác thực toàn bộ input bằng `ParsePosition` hoặc API strict tương ứng.

**Sau khi đánh giá:** chấp nhận những thay đổi CLDR đúng chính sách hiển thị; sửa hợp đồng nghiệp vụ hoặc dữ liệu lưu cũ nếu bị tác động. Dùng ISO/wire format độc lập locale, versioning cho collation/index và test tại CI/CD. Không dùng việc xóa mọi dấu cách hoặc khóa cứng một format tiếng Anh làm cách chữa chung.

## 13. Lỗi phổ biến

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Nghĩ `Locale.forLanguageTag` đảm bảo có locale data đầy đủ | Có fallback/thiếu dịch vụ | Test trên runtime đích |
| Dùng default locale server cho mọi user | Output thay đổi theo môi trường | Truyền locale tường minh |
| Trông chờ `COMPAT` trên JDK 23+ | Không khôi phục legacy data | Migration có kiểm soát |
| Gọi `System.setProperty` sau startup để đổi provider | Property có thể đã cached | Đặt trong JVM arguments |
| Coi các JDK LTS có dữ liệu giống nhau | CLDR version khác | Test theo JDK build |
| So dấu cách bằng mắt | Nhầm U+0020/U+00A0/U+202F | In Unicode code point |
| Lưu số/ngày display style làm wire format | JDK mới có thể parse khác | ISO/cấu trúc chuẩn |
| Chỉ test format | Bỏ qua lỗi parse dữ liệu cũ | Test cả hai chiều |
| Không kiểm tra custom runtime | Thiếu `jdk.localedata` | Kiểm thử trong deployment image |
| Dùng collation key không version | Index có thể lỗi thời | Reindex khi đổi policy |
| Nhầm locale với timezone | Hiển thị sai thời điểm | Truyền `ZoneId` riêng |

## 14. Checklist trước khi phát hành

- [ ] Ghi phiên bản, vendor/build và runtime image JDK.
- [ ] Biết `java.locale.providers` thực sự được truyền khi khởi động.
- [ ] Dùng locale explicit cho các API hiển thị theo người dùng.
- [ ] Kiểm tra decimal/grouping, Unicode separator, percent/currency.
- [ ] Kiểm tra ngày giờ, tên tháng, parse cũ, timezone và DST.
- [ ] Kiểm tra sort theo `Collator`, equality và phân trang.
- [ ] Kiểm tra fallback/SPI/HOST và module `jdk.localedata`.
- [ ] Phân biệt wire format với localized display text.
- [ ] Kiểm thử JDK cũ/mới bằng process riêng và lưu fingerprint.
- [ ] Đánh giá tác động và cập nhật golden tests có giải thích.

## 15. Tài liệu tham khảo chính thức

- [Java 17 — LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): provider và property trong JDK 17.
- [Java 25 — LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): dữ liệu CLDR theo từng dòng JDK.
- [JDK 23 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): loại bỏ legacy COMPAT/JRE.
- [JDK 26 — jlink reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): `--include-locales` và runtime tùy biến.

## 16. Ghi nhớ

- **`Locale` là yêu cầu, không phải bộ dữ liệu locale bất biến.**
- **CLDR mặc định được ưu tiên từ JDK 9; COMPAT/JRE bị loại từ JDK 23.**
- **SPI/HOST có giới hạn hỗ trợ** và phụ thuộc cấu hình/OS.
- **Cùng code + locale có thể ra output khác** khi thay CLDR, provider hoặc runtime image.
- **Dùng locale cho giao diện, wire format chuẩn cho lưu trữ**, không đảo hai mục tiêu.
- **Kiểm tra bằng hai JVM riêng, code point và regression tests**, nhất là format/parse và collation.
