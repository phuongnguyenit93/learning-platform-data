# DateTimeFormatter.withLocale so với localizedBy trong Java

## 1. Bài toán: đổi ngôn ngữ hiển thị có đồng nghĩa đổi lịch, chữ số và múi giờ?

Trong Java localization, `java.time.format.DateTimeFormatter` hỗ trợ cả hai phương thức:

- `withLocale(Locale)`: trả về formatter mới với **locale dùng để chọn văn bản và mẫu định dạng bản địa**.
- `localizedBy(Locale)`: trả về formatter mới có thể áp dụng thêm **lịch (chronology), hệ chữ số (decimal style), khu vực (region) và múi giờ (zone)** theo thông tin trong locale, đặc biệt là Unicode locale extensions.

Hai phương thức không đồng nghĩa, dù đôi khi cùng cho ra chuỗi giống nhau khi chỉ dùng locale đơn giản như `en-US` hoặc `vi-VN` và formatter không chứa tính năng cần ghi đè.

**Khác biệt thực dụng:** `withLocale` phù hợp khi chủ đích là *giữ thời điểm/lịch/múi giờ đã chọn và thay ngôn ngữ hoặc mẫu định dạng*. `localizedBy` phù hợp khi muốn *áp dụng các sở thích bản địa hóa mở rộng đã được chấp nhận*, bao gồm calendar, numbering system, region override hoặc timezone. Khi đối tượng chứa `ca`, `nu`, `rg`, `tz` trong language tag, kết quả có thể khác rõ rệt.

Không nên coi locale là dữ liệu thời điểm nghiệp vụ. `Instant` lưu một thời điểm trên trục thời gian; `ZoneId` xác định cách quy chiếu giờ địa phương; `Chronology` xác định hệ lịch; `Locale` xác định các quy ước bản địa hóa. Chúng liên quan nhưng **không thể dùng thay nhau**.

## 2. Hai phương thức làm việc trên formatter bất biến

`DateTimeFormatter` là kiểu **immutable** và an toàn khi dùng giữa các thread. Cả hai lời gọi đều trả về formatter mới (hoặc có thể tái sử dụng instance khi không cần đổi), **không sửa** formatter ban đầu:

~~~java
DateTimeFormatter base = DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);

DateTimeFormatter vietnamese =
        base.withLocale(Locale.forLanguageTag("vi-VN"));

DateTimeFormatter extended =
        base.localizedBy(Locale.forLanguageTag("vi-VN"));
~~~

Đây là **đoạn minh họa trong một phương thức**, cần import `java.time.format.DateTimeFormatter` và `java.util.Locale`. Chương trình hoàn chỉnh và kết quả kiểm chứng nằm ở mục 7.

| Khía cạnh | `withLocale(locale)` | `localizedBy(locale)` |
| --- | --- | --- |
| Trả về formatter mới, không sửa `base` | Có | Có |
| Thay `getLocale()` | Có | Có |
| Ảnh hưởng tên tháng/ngày và localized pattern | Có | Có |
| Thay `getChronology()` theo Unicode `ca` | **Không** tự động | Có thể |
| Thay `getDecimalStyle()` theo Unicode `nu` | **Không** tự động | Có thể |
| Thay `getZone()` theo Unicode `tz` | **Không** tự động | Có thể |
| Xem xét region override `rg` khi chọn dữ liệu bản địa | Locale được lưu và có thể được dùng khi lookup | Có thể áp dụng sâu hơn vào lịch/chữ số/zone theo locale |
| Thứ tự với `withZone`, `withChronology`, `withDecimalStyle` | Chỉ đổi trường locale, giữ override còn lại | **Có thể ghi đè** các giá trị override tùy thứ tự gọi |

Dấu “có thể” rất quan trọng: `localizedBy` dựa trên **các dữ liệu mà locale cung cấp** và những gì nhà cung cấp locale của runtime hỗ trợ. Không phải locale nào cũng yêu cầu thay lịch hoặc múi giờ.

## 3. withLocale: đổi nguồn bản địa hóa văn bản và pattern

Chữ ký Java SE 17:

~~~java
DateTimeFormatter withLocale(Locale locale)
~~~

Theo hợp đồng API, locale được lưu theo đúng giá trị truyền vào; formatter dùng nó để tra cứu phần cần bản địa hóa, như tên tháng, tên thứ và pattern ngày giờ theo locale. Những override đang có như chronology, zone và decimal style **được giữ lại**.

Ví dụ minh họa:

~~~java
LocalDate date = LocalDate.of(2024, 3, 1);
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);

String usText = english.format(date);
String viText = english.withLocale(
        Locale.forLanguageTag("vi-VN")).format(date);
~~~

Đoạn trên cần `import java.time.LocalDate;` cùng các import formatter/locale. Tên tháng có thể xuất hiện bằng từ viết tắt theo dữ liệu CLDR của JDK; không cần hardcode đầu ra nếu chưa kiểm soát môi trường. Hai chuỗi đều đang biểu diễn **cùng ngày 2024-03-01**, nhưng ngôn ngữ tháng có thể khác.

### 3.1. Localized style cũng chịu ảnh hưởng của withLocale

Các factory sau tạo formatter theo **style**, không cố định pattern văn bản ngay tại thời điểm tạo:

~~~java
DateTimeFormatter dateStyle =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter us = dateStyle.withLocale(Locale.US);
DateTimeFormatter vietnam = dateStyle.withLocale(
        Locale.forLanguageTag("vi-VN"));
~~~

Đây là các câu lệnh minh họa; cần import `java.time.format.FormatStyle`. Formatter được `ofLocalizedDate` tạo ra dùng pattern bản địa phù hợp với locale khi format/parse, và pattern có thể được tìm **một cách trì hoãn (lazily)**. Do vậy **không đúng** nếu nói `withLocale` chỉ dịch tên tháng mà không đổi thứ tự ngày/tháng/năm: với localized style, pattern cũng thay đổi.

Một formatter được tạo với `DateTimeFormatter.ofPattern("uuuu-MM-dd")` lại có **cấu trúc pattern cố định**; `withLocale` không tự biến nó thành thứ tự tháng/ngày/năm theo locale Mỹ. Muốn dùng mẫu ngày giờ truyền thống theo vùng, dùng factory `ofLocalizedDate`/`ofLocalizedDateTime` hoặc pattern được thiết kế cụ thể.

### 3.2. withLocale không tự giải quyết Unicode extensions thành override

Khi locale là `en-US-u-ca-japanese-nu-thai-tz-jptyo`, `withLocale` **lưu nguyên locale kèm extension**. Điều đó không đồng nghĩa formatter đã tự chuyển:

- `getChronology()` sang lịch Nhật;
- `getDecimalStyle()` sang chữ số Thái;
- `getZone()` sang `Asia/Tokyo`.

Các phần cần bản địa hóa **vẫn có thể nhìn thấy locale extensions trong quá trình tra cứu văn bản/pattern**. Tuy nhiên, để yêu cầu thiết lập chronology, zone và decimal style từ extensions ngay trên formatter, phải xem xét `localizedBy`.

Nếu cần thay rõ ràng chỉ một giá trị, `withChronology(Chronology)`, `withZone(ZoneId)`, `withDecimalStyle(DecimalStyle)` là các API có mục đích rõ ràng hơn việc đưa cấu hình nghiệp vụ vào locale string.

## 4. localizedBy: áp dụng calendar, numbering system, region và timezone

Chữ ký Java SE 17:

~~~java
DateTimeFormatter localizedBy(Locale locale)
~~~

Phương thức này có từ **Java 10**. Nó trả về formatter mới với các giá trị bản địa hóa của locale, calendar, region, decimal style và/hoặc timezone có thể **ghi đè** những giá trị formatter đang giữ.

Các khóa Unicode locale extension cần nhớ:

| Khóa | Chức năng | Ví dụ trong language tag |
| --- | --- | --- |
| `ca` | Calendar/chronology được yêu cầu | `en-US-u-ca-japanese` |
| `nu` | Hệ chữ số (numbering system) | `en-US-u-nu-thai` |
| `tz` | Timezone được yêu cầu, bằng mã Unicode timezone | `en-US-u-tz-jptyo` |
| `rg` | Region override | `en-US-u-rg-gbzzzz` |

Trong `en-US-u-ca-japanese-nu-thai-tz-jptyo`:

- `en-US` là language và country thông thường.
- `u` mở đầu Unicode extension.
- `ca-japanese` yêu cầu lịch Nhật.
- `nu-thai` yêu cầu hệ chữ số Thái.
- `tz-jptyo` chỉ timezone được đăng ký cho Tokyo. **Không** viết tùy tiện `tz-Asia/Tokyo` trong BCP 47: Unicode timezone type có mã theo registry riêng, khác chuỗi IANA ZoneId.

Locale có thể được tạo qua:

~~~java
Locale preference = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai-tz-jptyo");
DateTimeFormatter enriched = base.localizedBy(preference);
~~~

Đây là đoạn minh họa với biến `base` là formatter đã tồn tại. Với formatter có đủ khả năng biểu diễn, kết quả `enriched` có thể mang:

- `getChronology().getId()`: `Japanese`;
- `getZone().getId()`: `Asia/Tokyo`;
- `getDecimalStyle().getZeroDigit()`: chữ số không `๐` của Thái (Unicode `U+0E50`).

**Ưu tiên giữa các extensions:** nếu đồng thời có `ca` và `rg`, chronology xác định bởi `ca` ưu tiên chronology ngầm suy ra từ `rg`; quy tắc tương tự áp dụng với `nu` khi chọn numbering system. Không nên nghĩ chỉ country gốc `US` quyết định toàn bộ cách format khi có region override.

### 4.1. localizedBy cũng không “đổi thời gian” của một Instant

Nếu dùng một `Instant` đầu vào, timezone trong formatter ảnh hưởng **cách biểu diễn giờ theo vùng**. Một `Instant` ở `2024-03-01T03:04:00Z` sẽ tương ứng `03:04` tại UTC nhưng `12:04` ở Tokyo (UTC+9 tại thời điểm đó). **Instant vẫn là cùng một thời điểm.**

Nếu dữ liệu nguồn là `LocalDateTime` không có zone/offset, không thể xem việc định dạng với một zone override là phép quy đổi thời điểm có nghĩa khi chưa gắn zone cho dữ liệu nguồn. Đối với các hệ thống lịch/sự kiện, hãy mô hình hóa `Instant` hoặc `ZonedDateTime`/zone nghiệp vụ đúng trước khi format.

### 4.2. Chronology là cách diễn giải hệ lịch, không phải dịch chữ

Một chronology khác, ví dụ `JapaneseChronology`, có cách xác định niên hiệu/era, năm trong kỷ nguyên và quy tắc lịch. Khi format đối tượng ngày theo lịch khác, formatter có thể chuyển sang chronology override trước khi phát sinh chuỗi. Vì vậy khi chọn `localizedBy` có `ca`, phải cân nhắc cả ý nghĩa ngày, chữ số và era, không coi đây là “đổi ngôn ngữ” thuần túy.

Những formatter dùng pattern `uuuu` có thể vẫn in năm proleptic tương ứng `2024` ngay khi `getChronology()` là `Japanese`; để nhìn rõ niên hiệu trong output cần pattern thích hợp như `G y`. Đừng dựa vào một chuỗi năm đơn lẻ để suy luận rằng chronology không thay đổi: kiểm tra `getChronology()` và các trường era/năm nếu nhiệm vụ cần.

## 5. Thứ tự gọi phương thức quan trọng với localizedBy

Các formatter là immutable và phương thức `withXXX` trả về bản sao. Với `withLocale`, không tự ghi đè chronology/zone/decimal style, nên thường có thể cấu hình các override độc lập.

**Với `localizedBy`, thứ tự có thể làm thay đổi kết quả** vì `localizedBy` có thể đặt lại các thuộc tính đã được gán trước:

~~~java
Locale pref = Locale.forLanguageTag("en-US-u-tz-jptyo");

DateTimeFormatter a = base
        .localizedBy(pref)
        .withZone(ZoneId.of("UTC"));

DateTimeFormatter b = base
        .withZone(ZoneId.of("UTC"))
        .localizedBy(pref);
~~~

Đây là đoạn minh họa; `base` là formatter đã có, cần import `Locale` và `ZoneId`.

- Ở **a**, `localizedBy` lấy timezone Tokyo từ `tz`, rồi `withZone(UTC)` **ghi đè cuối cùng**: `a.getZone()` là `UTC`.
- Ở **b**, `withZone(UTC)` được áp dụng trước nhưng `localizedBy` sau đó nhận extension `tz-jptyo`: `b.getZone()` là `Asia/Tokyo` trên JDK có mapping đó.

Điều tương tự có thể xảy ra khi `withChronology` hoặc `withDecimalStyle` đứng trước/sau `localizedBy`. Để tránh cấu hình ngầm:

1. Dùng `localizedBy(pref)` trước nếu muốn nhận mặc định bản địa được cho phép.
2. Sau đó gọi `withZone(businessZone)`, `withChronology(businessChronology)`, `withDecimalStyle(requiredStyle)` **cuối cùng** nếu chính sách ứng dụng bắt buộc giữ chúng.
3. Không chấp nhận các Unicode extensions do client tự khai như một lệnh đổi timezone hoặc chronology của nghiệp vụ mà chưa kiểm tra quyền, danh sách hỗ trợ và ranh giới dữ liệu.
4. Viết kiểm thử `getLocale()`, `getChronology()`, `getZone()`, `getDecimalStyle()` cho các cấu hình dễ nhầm.

## 6. Đừng lẫn DecimalStyle với toàn bộ localization

`DateTimeFormatter` có `DecimalStyle` để kiểm soát chữ số, dấu cộng/trừ và dấu thập phân dùng cho quá trình format/parse. Nó **không** phải `java.text.DecimalFormat` dành cho format số nói chung.

Ví dụ:

~~~java
DecimalStyle style = DecimalStyle.STANDARD;
char zeroDigit = style.getZeroDigit(); // '0' (U+0030)
~~~

Đây là đoạn minh họa, cần import `java.time.format.DecimalStyle`.

`withLocale(Locale.forLanguageTag("th-TH"))` có thể đổi văn bản/pattern theo locale nhưng **không tự đổi** `DecimalStyle.STANDARD` đã cấu hình. Ngược lại, `localizedBy(Locale.forLanguageTag("th-TH-u-nu-thai"))` có thể chọn chữ số Thái theo extension `nu`.

Cũng không được đồng nhất locale với `ZoneId`: không phải mọi ngôn ngữ/khu vực quy về một múi giờ duy nhất. Một country có thể trải qua nhiều zone hoặc phụ thuộc thời điểm. `tz` extension là một **yêu cầu timezone được mã hóa trong locale**, không phải sự thật về vị trí thực của người dùng.

## 7. Ví dụ Java 17 chạy độc lập, kiểm chứng cả metadata và output

Đặt mã trong file **`LocaleMethodDemo.java`**:

~~~java
import java.time.*;
import java.time.chrono.*;
import java.time.format.*;
import java.util.*;

public class LocaleMethodDemo {
    static void state(String name, DateTimeFormatter f) {
        String chrono = f.getChronology() == null
                ? "none" : f.getChronology().getId();
        String zone = f.getZone() == null
                ? "none" : f.getZone().getId();
        int digit = (int) f.getDecimalStyle().getZeroDigit();

        System.out.println(name + ": locale="
                + f.getLocale().toLanguageTag()
                + ", chronology=" + chrono
                + ", zone=" + zone
                + ", zeroDigitU+"
                + String.format(Locale.ROOT, "%04X", digit));
    }

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag(
                "en-US-u-ca-japanese-nu-thai-tz-jptyo");

        DateTimeFormatter base = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
                .withChronology(IsoChronology.INSTANCE)
                .withZone(ZoneId.of("UTC"))
                .withDecimalStyle(DecimalStyle.STANDARD);

        DateTimeFormatter with = base.withLocale(target);
        DateTimeFormatter localized = base.localizedBy(target);

        state("base", base);
        state("withLocale", with);
        state("localizedBy", localized);
        state("zoneAfter",
                base.localizedBy(target).withZone(ZoneId.of("UTC")));
        state("localeAfter",
                base.withZone(ZoneId.of("UTC")).localizedBy(target));

        System.out.println("unchanged="
                + base.getLocale().equals(Locale.US));

        Instant instant = Instant.parse("2024-03-01T03:04:00Z");
        System.out.println("withLocale text=" + with.format(instant));
        System.out.println("localizedBy text=" + localized.format(instant));
    }
}
~~~

Biên dịch và chạy với **Java 17 trở lên**:

~~~bash
javac -encoding UTF-8 LocaleMethodDemo.java
java LocaleMethodDemo
~~~

**Stdout đã đối chiếu** trên JDK có dữ liệu calendar, numbering system và timezone tương ứng:

~~~text
base: locale=en-US, chronology=ISO, zone=UTC, zeroDigitU+0030
withLocale: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=ISO, zone=UTC, zeroDigitU+0030
localizedBy: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=Asia/Tokyo, zeroDigitU+0E50
zoneAfter: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=UTC, zeroDigitU+0E50
localeAfter: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=Asia/Tokyo, zeroDigitU+0E50
unchanged=true
withLocale text=2024-03-01 03:04
localizedBy text=๒๐๒๔-๐๓-๐๑ ๑๒:๐๔
~~~

Đọc kết quả:

1. **base** chứa `ISO`, `UTC` và chữ số `0` ASCII (`U+0030`).
2. **withLocale** thay ngôn ngữ/locale được lưu sang tag có extension nhưng vẫn giữ cả ba override của base.
3. **localizedBy** thay sang lịch Nhật, timezone Tokyo và chữ số Thái (`U+0E50`) theo `ca`, `tz`, `nu`.
4. **zoneAfter** cho `UTC` vì `withZone(UTC)` được gọi cuối.
5. **localeAfter** cho `Asia/Tokyo` vì `localizedBy` được gọi cuối và diễn giải `tz`.
6. **unchanged=true** chứng minh formatter base ban đầu không bị thay đổi.
7. **withLocale text** dùng thời gian UTC và chữ số ASCII: `2024-03-01 03:04`.
8. **localizedBy text** dùng giờ Tokyo (UTC+9) và chữ số Thái: `๒๐๒๔-๐๓-๐๑ ๑๒:๐๔`.

Dòng cuối **không có nghĩa một `Instant` mới được tạo**. Cả hai chuỗi đều định dạng cùng `Instant.parse("2024-03-01T03:04:00Z")`; khác biệt đến từ zone và numbering system trong formatter.

Nếu JDK không hỗ trợ một loại calendar, mã vùng hoặc numbering system được yêu cầu, kết quả cụ thể có thể khác. Khi triển khai, hãy kiểm tra theo runtime/locale provider đã chọn và tránh snapshot Unicode text vượt mọi phiên bản mà không ghim dữ liệu. Trong ví dụ, in `zeroDigitU+` là cách kiểm tra metadata rõ ràng hơn việc trông vào kiểu chữ của console.

## 8. withLocale hay localizedBy: chọn theo tình huống

| Nhu cầu | Phương án thường phù hợp | Lý do |
| --- | --- | --- |
| Dịch tên tháng, thứ và đổi mẫu ngày theo locale | `withLocale(locale)` trên formatter phù hợp | Đổi nguồn văn bản và localized pattern |
| Dùng `ofLocalizedDate(FormatStyle.LONG)` theo user locale | `withLocale(locale)` | Localized style đã tìm pattern theo locale |
| Giữ lịch ISO và một zone của nghiệp vụ | `withLocale(locale)` cùng `withChronology`/`withZone` rõ ràng | Hạn chế tác dụng của locale extension lên override |
| Cho phép user chọn lịch Nhật qua `ca-japanese` | `localizedBy(locale)` nếu policy cho phép | Áp dụng chronology từ locale extension |
| Cho phép hệ chữ số Thái qua `nu-thai` | `localizedBy(locale)` hoặc `withDecimalStyle` rõ ràng | Áp dụng numbering system |
| Cho phép timezone từ `tz` | `localizedBy(locale)` sau kiểm tra chính sách | Có thể chọn zone theo extension |
| Timezone của lịch họp phải là `Asia/Ho_Chi_Minh` bất kể client locale | `localizedBy(locale).withZone(businessZone)` hoặc `withLocale(locale).withZone(businessZone)` | Ghi đè zone sau khi bản địa hóa |
| Sinh chuỗi chuẩn để lưu DB/API | Formatter ISO/chuẩn cố định theo contract | Không phụ thuộc presentation locale |
| Một server phục vụ nhiều request | Truyền locale theo request, dùng formatter immutable | Tránh `Locale.setDefault` toàn JVM |

**Không thể chỉ chọn một phương thức làm “đúng cho mọi trường hợp”.** Quyết định phải dựa trên ý nghĩa của hệ lịch, vùng thời gian và hệ chữ số trong sản phẩm.

## 9. Các lỗi thường gặp

### Lỗi 1: tưởng withLocale tự đổi timezone

~~~java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH:mm")
        .withZone(ZoneId.of("UTC"))
        .withLocale(Locale.forLanguageTag("ja-JP"));
~~~

Đây là đoạn minh họa, cần import các lớp tương ứng. Kết quả `getZone()` vẫn là `UTC`. Locale tiếng Nhật không tự chuyển mốc thời gian thành giờ Tokyo.

**Cách đúng:** nếu cần giờ Tokyo, dùng `withZone(ZoneId.of("Asia/Tokyo"))` rõ ràng, hoặc chọn `localizedBy` khi người dùng thực sự có `tz` extension hợp lệ và sản phẩm cho phép nó.

### Lỗi 2: tưởng localizedBy chỉ thay tên tháng

Nếu locale chứa `ca`, `nu`, `tz`, phương thức này có thể ghi đè lịch, chữ số và zone đã cấu hình. **Không** gọi `localizedBy` cuối pipeline nếu nghiệp vụ bắt buộc một `ZoneId` cố định mà không hiểu rủi ro.

### Lỗi 3: không lưu formatter trả về

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);
formatter.withLocale(Locale.FRANCE); // Bỏ qua đối tượng trả về!
~~~

Formatter bất biến, nên biến `formatter` vẫn giữ locale `en-US`. Hãy dùng `formatter = formatter.withLocale(Locale.FRANCE);` hoặc đặt vào biến mới.

### Lỗi 4: dùng locale để thay dữ liệu thời gian

Đổi UI sang `vi-VN` không tự xác định một `LocalDateTime` phải thuộc timezone nào. Nếu ứng dụng nhận thời điểm từ backend, lưu/truyền `Instant` hoặc `OffsetDateTime`/`ZonedDateTime` với semantics rõ ràng; áp dụng locale ở bước trình bày. Đừng tự coi ngày giờ không gắn zone là một instant rồi cộng/trừ giờ theo country.

### Lỗi 5: ép formatter theo locale cho dữ liệu máy đọc

Chuỗi `2024-03-01` theo ISO format thường ổn định hơn để truyền qua API so với localized date text mà thứ tự ngày/tháng và chữ số có thể thay đổi. Các serializer nên theo contract rõ ràng, không lấy formatter của màn hình làm chuẩn lưu trữ.

### Lỗi 6: cho client quyết định chronology/zone bằng extension không được kiểm tra

Một header locale do client gửi có thể chứa `u-ca-...`, `u-nu-...`, `u-tz-...`. Đừng dùng trực tiếp để đổi lịch tính hạn, giờ hẹn hoặc xử lý lịch sử nếu hệ thống cần zone/chronology từ nguồn đáng tin cậy. Parse và allowlist locale, rồi áp dụng quy tắc nghiệp vụ riêng.

## 10. Kiểm thử cần viết

Để kiểm tra chính xác lựa chọn API, tạo test bao phủ:

1. **Immutability:** formatter gốc không đổi sau cả hai phương thức.
2. **Locale text/style:** tên tháng, tên thứ hoặc localized pattern thay theo `withLocale` đối với formatter có phần bản địa hóa.
3. **No hidden override:** `withLocale` với `ca/nu/tz` vẫn giữ explicit chronology/zone/decimal style của base.
4. **Extended localization:** `localizedBy` với các extension hợp lệ cập nhật metadata mong đợi.
5. **Chaining order:** `localizedBy(tz).withZone(UTC)` khác `withZone(UTC).localizedBy(tz)`.
6. **Same Instant:** định dạng cùng `Instant` ở UTC và Tokyo, kiểm tra chênh lệch giờ chính xác nhưng giá trị `Instant` không đổi.
7. **Input edge cases:** `null` ném `NullPointerException`; locale không có extension và locale có extension không hỗ trợ phải được xử lý theo hợp đồng của JDK và chính sách ứng dụng.
8. **Parser:** nếu dùng `localizedBy` có chronology khác ISO, xác nhận thời gian parse ra có meaning đúng; không tự suy diễn LocalDate khi hệ lịch khác.
9. **Provider/CLDR differences:** snapshot tên tháng, era và chữ số theo phiên bản Java/locale data mà sản phẩm đã cam kết.
10. **Multi-thread:** formatter immutable có thể chia sẻ an toàn; context locale của mỗi request phải được quản lý riêng thay vì thay default JVM.

Đối với parser và format cần ổn định trên giao thức, hãy dùng formatter chuẩn cố định và kiểm thử round-trip độc lập với language preference.

## 11. Bài tập thực hành

- Thay `Locale.US` của `base` bằng `Locale.forLanguageTag("vi-VN")`, rồi dùng `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)` để quan sát pattern theo locale.
- Bỏ `tz-jptyo` khỏi `target`; so `getZone()` của formatter base, `withLocale` và `localizedBy` trên runtime đang dùng.
- Bỏ `ca-japanese`; so `getChronology()`.
- Bỏ `nu-thai`; so `getDecimalStyle().getZeroDigit()`.
- Thay pattern thành `"G y-MM-dd HH:mm"`; quan sát cách chronology Nhật định dạng era/năm của era, nhưng lưu ý tên era phụ thuộc locale/provider.
- Đảo thứ tự `withChronology(IsoChronology.INSTANCE)` và `localizedBy(target)`; giải thích giá trị cuối cùng của formatter.
- Truyền cùng `Instant` qua các formatter nhưng đặt zone business ở cuối bằng `withZone(ZoneId.of("Asia/Ho_Chi_Minh"))`; xác nhận chênh lệch múi giờ so với UTC ở ngày đã chọn.
- Viết một factory `formatterFor(Locale locale, ZoneId requiredZone)` nhận locale từ request và zone từ domain, rồi chứng minh không cần `Locale.setDefault`.

## 12. Tóm tắt

**`withLocale` thay nguồn bản địa hóa văn bản và pattern; `localizedBy` có thể áp dụng cả chronology, numbering system, region và timezone từ locale.** Cả hai đều trả về formatter bất biến mới. Sự khác biệt thường rõ nhất khi locale có Unicode extensions `ca`, `nu`, `rg`, `tz`, hoặc formatter đã có `withZone`, `withChronology`, `withDecimalStyle`.

Khi hệ thống chỉ cần đổi ngôn ngữ hoặc cách trình bày ngày giờ mà vẫn giữ zone/lịch nghiệp vụ, `withLocale` thường là lựa chọn dễ kiểm soát. Khi ứng dụng **chủ đích** hỗ trợ sở thích lịch/chữ số/zone được mã hóa trong locale, cân nhắc `localizedBy`, kiểm tra dữ liệu đầu vào và đặt các override bắt buộc **sau** thao tác bản địa hóa. Đừng nhầm định dạng hiển thị với cách lưu hoặc tính toán thời điểm.

**Tài liệu tham khảo:**

- Java SE 17, `DateTimeFormatter` (withLocale, localizedBy): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `DecimalStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DecimalStyle.html
- Java SE 17, `Locale` và Unicode extensions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Chronology`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html
- Java SE 17, `ZoneId`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html
