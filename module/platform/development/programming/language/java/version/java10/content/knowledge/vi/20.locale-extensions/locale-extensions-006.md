# Khóa `tz` của Unicode Locale Extension để lựa chọn múi giờ trong Java 10+

**Chủ đề:** Mở rộng `Locale` — Java 10 trở lên.

Khi người dùng chọn một **múi giờ ưu tiên** cho việc hiển thị ngày giờ, Java hỗ trợ biểu diễn lựa chọn đó ngay trong một thẻ ngôn ngữ **BCP 47** bằng khóa Unicode locale extension **`tz`**. Ví dụ `en-US-u-tz-uslax` có phần ngôn ngữ–vùng là `en-US` và tùy chọn múi giờ là **`uslax`**, một mã múi giờ ngắn của Unicode CLDR chỉ `America/Los_Angeles`.

**Java 10** bổ sung cơ chế để các API định dạng ngày giờ liên quan hiểu khóa `tz`, đặc biệt `java.time.format.DateTimeFormatter.localizedBy(Locale)` và các phương thức tạo `java.text.DateFormat` theo locale. Khả năng này xuất phát từ **JEP 314 — Additional Unicode Language-Tag Extensions**, và **vẫn được hỗ trợ trong Java hiện đại**. Bài học ưu tiên API `java.time`, đồng thời giới thiệu `DateFormat` ở mức cần thiết để hiểu tương tác với JEP 314.

Mục tiêu là biết cách **tạo, đọc, áp dụng và kiểm tra** khóa `tz` mà không nhầm mã ngắn CLDR với `ZoneId` IANA, không ngầm thay múi giờ toàn JVM và không bỏ qua các quy tắc daylight saving time (DST). Năm chương trình Java độc lập trong bài đã được **biên dịch bằng `javac --release 10` và chạy kiểm tra trên JDK 24**, với kết quả đầu ra ghi cụ thể.

## 1. Cú pháp `-u-tz-...` trong thẻ `Locale`

Một Unicode locale extension thuộc BCP 47 bắt đầu bằng `-u-`, tiếp theo là các cặp **khóa** và **kiểu giá trị**. Khóa `tz` biểu diễn lựa chọn múi giờ:

~~~text
en-US-u-tz-uslax
│  │  │  │  └── uslax: mã múi giờ ngắn CLDR, tương ứng Los Angeles
│  │  │  └───── tz: khóa lựa chọn time zone
│  │  └──────── u: Unicode locale extension
│  └─────────── US: mã vùng của Locale
└────────────── en: mã ngôn ngữ
~~~

Các phần trong thẻ không có cùng nhiệm vụ:

- `en` quyết định ngôn ngữ (tiếng Anh) cho dịch vụ cần bản địa hóa.
- `US` là mã vùng trong `Locale`, có thể ảnh hưởng dữ liệu định dạng địa phương.
- `u-tz-uslax` là **tùy chọn múi giờ**, không phải tên ngôn ngữ hay mã quốc gia.
- `uslax` không phải ID dạng `Area/City` của IANA; đó là **short time-zone ID** trong Unicode CLDR, dùng được trong BCP 47.
- Các khóa khác như `ca` (calendar), `nu` (numbering system), `cu` (currency), `fw` (first day of week) và `rg` (region override) phục vụ lựa chọn khác. Bài này chỉ tập trung vào `tz`.

Vì vùng `US` có **nhiều múi giờ**, một `Locale.US` hoặc `en-US` thông thường **không** cho biết người dùng đang ở New York hay Los Angeles. Ngay cả quốc gia có một múi giờ chủ yếu, mã vùng cũng không nên được dùng làm thay thế tổng quát cho một lựa chọn múi giờ rõ ràng.

### Tạo `Locale` bằng thẻ BCP 47

~~~java
Locale selected = Locale.forLanguageTag("en-US-u-tz-uslax");

System.out.println(selected.toLanguageTag());          // en-US-u-tz-uslax
System.out.println(selected.getUnicodeLocaleType("tz")); // uslax
~~~

Đây là **đoạn mã bên trong một phương thức**, cần import `java.util.Locale`. `getUnicodeLocaleType("tz")` lấy kiểu giá trị của khóa `tz`, trả về `null` nếu Locale không khai báo khóa đó. Lời gọi này chỉ **đọc metadata của Locale**, chưa tự định dạng ngày giờ hay thay đổi đồng hồ hệ thống.

### Tạo bằng `Locale.Builder`

~~~java
Locale selected = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("tz", "uslax")
        .build();
~~~

`Locale.Builder` phù hợp khi xây lựa chọn từ các thành phần riêng. Với dữ liệu không tin cậy, Builder kiểm tra **cú pháp BCP 47**; tuy nhiên một kiểu `tz` có cú pháp hợp lệ **không nhất thiết** là mã múi giờ được CLDR/JDK nhận diện. Kiểm tra hợp lệ về cú pháp và **được hỗ trợ về ngữ nghĩa** là hai bước khác nhau.

## 2. Java 10 đã mở rộng điều gì?

**JEP 314** đưa bốn khóa Unicode extension bổ sung vào các dịch vụ JDK liên quan:

| Khóa | Ý nghĩa | Ví dụ tác động |
| --- | --- | --- |
| `cu` | Currency type | `Currency.getInstance(locale)` |
| `fw` | First day of week | `WeekFields.of(locale)` và dữ liệu tuần |
| `rg` | Region override | Nhiều dịch vụ dữ liệu theo vùng |
| **`tz`** | **Time zone** | **`DateTimeFormatter.localizedBy(locale)`; `DateFormat.get*Instance(..., locale)`** |

`Locale` hỗ trợ cơ chế mang Unicode extension từ trước Java 10, nhưng **việc các dịch vụ liên quan áp dụng thêm khóa `tz`** là nội dung quan trọng của Java 10. Đừng nhầm “đọc được khóa từ `Locale`” với “mọi API tự áp dụng khóa khi nhìn thấy Locale”.

Hai cách làm khác nhau:

~~~java
formatter.withLocale(selectedLocale);   // đặt locale cho formatter
formatter.localizedBy(selectedLocale);  // bản địa hóa thêm zone/chronology...
~~~

Đây là **hai đoạn gọi minh họa** với một `DateTimeFormatter` đã tồn tại. `withLocale` không tự thiết lập override zone từ `tz` trong ví dụ Java 10+, còn `localizedBy` được thiết kế để áp dụng các Unicode extension tương ứng, bao gồm **`tz`**. Phần thực hành dưới đây sẽ kiểm tra bằng `getZone()` và một `Instant` cố định.

### Dùng thư viện `java.time` trong mã mới

`java.time.ZoneId`, `Instant`, `ZonedDateTime` và `DateTimeFormatter` là các API hiện hành để tính toán và định dạng thời gian. `java.text.DateFormat` vẫn hoạt động và có thể tiếp nhận `tz` khi tạo instance theo locale, nhưng trong thiết kế mới nên ưu tiên `java.time` vì kiểu dữ liệu rõ và API bất biến hơn.

**Không gọi `Locale.setDefault(...)` hay `TimeZone.setDefault(...)` chỉ để định dạng thời gian của một người dùng.** Trong một ứng dụng phục vụ nhiều người, default toàn tiến trình là trạng thái dùng chung và không phải nơi lưu “múi giờ người dùng A”.

## 3. Mã múi giờ ngắn `tz` khác với tên `ZoneId` IANA

Unicode CLDR định nghĩa các **short time-zone IDs** để đặt trong Unicode locale extension. Ví dụ:

| Mã `tz` trong Locale | Múi giờ tương ứng về ý nghĩa | Ví dụ thẻ |
| --- | --- | --- |
| `uslax` | Los Angeles, Hoa Kỳ (`America/Los_Angeles`) | `en-US-u-tz-uslax` |
| `usnyc` | New York, Hoa Kỳ (`America/New_York`) | `en-US-u-tz-usnyc` |
| `jptyo` | Tokyo, Nhật Bản (`Asia/Tokyo`) | `ja-JP-u-tz-jptyo` |
| `gblon` | London, Vương quốc Anh (`Europe/London`) | `en-GB-u-tz-gblon` |
| `vnsgn` | Thành phố Hồ Chí Minh, Việt Nam (IANA `Asia/Ho_Chi_Minh`; có alias `Asia/Saigon`) | `vi-VN-u-tz-vnsgn` |

**Chú ý với Việt Nam:** JDK 24 trong môi trường kiểm thử có thể giải mã `vnsgn` thành ID `Asia/Saigon`, một bí danh vùng thời gian cùng ý nghĩa với `Asia/Ho_Chi_Minh`. Tên ID mà các lớp trả về có thể chịu ảnh hưởng phiên bản CLDR/TZDB và alias. Nếu muốn lưu một lựa chọn IANA rõ ràng trong nghiệp vụ, sử dụng `ZoneId.of("Asia/Ho_Chi_Minh")` thay vì khẳng định `getZone().getId()` từ locale luôn phải là một chuỗi alias cụ thể.

### Không đưa nguyên tên IANA vào `tz`

`America/Los_Angeles` **không** phải một Unicode locale type hợp lệ để đưa trực tiếp vào `setUnicodeLocaleKeyword("tz", ...)`: dấu `/` và `_` không thuộc cú pháp type BCP 47. Dạng đúng là:

~~~java
Locale locale = Locale.forLanguageTag("en-US-u-tz-uslax");
ZoneId zone = ZoneId.of("America/Los_Angeles");
~~~

Hai đối tượng mô tả hai vai trò khác nhau:

- **Locale + `tz`:** diễn tả tùy chọn bản địa hóa và lựa chọn múi giờ theo short ID CLDR.
- **`ZoneId` IANA:** định danh múi giờ dùng để tính offsets và DST theo luật thời gian, gắn với sự kiện, lịch hẹn và các phép chuyển đổi thời điểm.

Không tự gán `ZoneId.of("uslax")`: `uslax` không phải một IANA ZoneId mà `ZoneId.of` bắt buộc phải hiểu. Nếu cần chuyển từ mã CLDR sang IANA, phải dùng dữ liệu ánh xạ chuẩn thích hợp hoặc một bảng ánh xạ ứng dụng có kiểm soát; JDK không cam kết một helper tổng quát biến mọi mã `tz` bất kỳ thành tên IANA chỉ bằng `ZoneId.of(type)`.

## 4. Chương trình hoàn chỉnh 1 — Tạo và đọc khóa `tz`

Lưu tệp **`LocaleTzKeyDemo.java`**:

~~~java
import java.util.Locale;

public class LocaleTzKeyDemo {
    public static void main(String[] args) {
        Locale fromTag = Locale.forLanguageTag("en-US-u-tz-uslax");
        Locale fromBuilder = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("tz", "uslax")
                .build();

        System.out.println("tag=" + fromTag.toLanguageTag());
        System.out.println("tz-type=" + fromTag.getUnicodeLocaleType("tz"));
        System.out.println("builder-same=" + fromTag.equals(fromBuilder));
        System.out.println("language=" + fromTag.getLanguage());
        System.out.println("region=" + fromTag.getCountry());
        System.out.println("base-tz=" + Locale.US.getUnicodeLocaleType("tz"));
    }
}
~~~

Lệnh chạy trên JDK hỗ trợ `--release 10`:

~~~bash
javac --release 10 LocaleTzKeyDemo.java
java LocaleTzKeyDemo
~~~

**Stdout chính xác:**

~~~text
tag=en-US-u-tz-uslax
tz-type=uslax
builder-same=true
language=en
region=US
base-tz=null
~~~

Giải thích:

1. `Locale.forLanguageTag` và `Locale.Builder` tạo ra cùng một Locale khi thành phần giống nhau.
2. `toLanguageTag` có khóa `tz`, thể hiện thông tin lựa chọn múi giờ ngay trong tag.
3. `getUnicodeLocaleType("tz")` trả `"uslax"`; API không tự trả chuỗi IANA `"America/Los_Angeles"`.
4. `Locale.US` không có khóa `tz` nên phương thức trả `null`. Điều này **không** có nghĩa hệ thống không có múi giờ; nó chỉ có nghĩa Locale này **chưa khai báo lựa chọn múi giờ qua extension**.
5. Ngôn ngữ `en` và vùng `US` vẫn giữ nguyên khi có thêm khóa `tz`.

**Bài học:** `tz` là một tùy chọn **bổ sung** của Locale. Cần áp dụng Locale đó vào dịch vụ có hỗ trợ `tz` để việc định dạng dùng múi giờ mong muốn.

## 5. `DateTimeFormatter.localizedBy` áp dụng `tz` như thế nào?

Với Java 10+, `DateTimeFormatter.localizedBy(Locale)` trả một formatter mới đã được bản địa hóa theo những thông tin liên quan trong Locale: lịch, đánh số, vùng và **múi giờ**. Nếu Locale có một mã `tz` được hỗ trợ, formatter nhận một **override zone** phù hợp.

~~~java
Locale laLocale = Locale.forLanguageTag("en-US-u-tz-uslax");

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.US)
        .localizedBy(laLocale);
~~~

Đây là **đoạn mã trong phương thức**. `formatter.getZone()` trên JDK kiểm thử là `America/Los_Angeles`. Khi gọi `formatter.format(Instant.parse("2024-01-15T12:00:00Z"))`, formatter dùng giờ Los Angeles tương ứng thời điểm UTC đã cho.

### So sánh `withLocale` và `localizedBy`

| Lời gọi | Hiệu ứng thiết yếu với `tz` | Kết quả `getZone()` trong ví dụ |
| --- | --- | --- |
| `base.withLocale(laLocale)` | Đặt Locale cho formatter; **không tự áp dụng override time zone theo `tz`** | `null` |
| `base.localizedBy(laLocale)` | Đọc Unicode extension thích hợp và áp dụng lựa chọn múi giờ | `America/Los_Angeles` |
| `base.withZone(ZoneId.of("UTC")).localizedBy(laLocale)` | Áp dụng locale **sau** nên lựa chọn `tz` có thể thay override zone trước đó | `America/Los_Angeles` |
| `base.localizedBy(laLocale).withZone(ZoneId.of("UTC"))` | Chỉ định `withZone(UTC)` **sau** nên UTC thắng | `UTC` |

**Thứ tự gọi có ý nghĩa.** Nếu một đối tượng formatter vừa có `tz` trong locale vừa có `withZone(...)` tường minh, phải biết bước nào được áp dụng cuối. Đây là một lý do để thống nhất **một nguồn quyết định múi giờ** cho mỗi màn hình/hợp đồng API.

### Tại sao dùng `Instant` cố định khi kiểm thử?

`Instant` biểu diễn một thời điểm trên trục UTC. Định dạng một `Instant` vào múi giờ Los Angeles dùng quy tắc timezone đúng của từng ngày, có thể đổi offset do DST:

- `2024-01-15T12:00:00Z` → `2024-01-15 04:00 -08:00`.
- `2024-07-15T12:00:00Z` → `2024-07-15 05:00 -07:00`.

**Không lấy `OffsetDateTime.now()` hay `LocalDateTime.now()` làm dữ liệu expected trong unit test cố định**: kết quả thay đổi theo thời điểm chạy, múi giờ hệ thống và ngày DST. Dùng thời điểm được chọn rõ giúp test dễ lặp lại.

## 6. Chương trình hoàn chỉnh 2 — `withLocale`, `localizedBy` và DST

Lưu **`LocalizedByTzDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocalizedByTzDemo {
    public static void main(String[] args) {
        Locale selected = Locale.forLanguageTag("en-US-u-tz-uslax");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US);
        DateTimeFormatter justLocale = base.withLocale(selected);
        DateTimeFormatter selectedZone = base.localizedBy(selected);

        System.out.println("base-zone=" + base.getZone());
        System.out.println("withLocale-zone=" + justLocale.getZone());
        System.out.println("localizedBy-zone=" + selectedZone.getZone());

        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");
        System.out.println("winter=" + selectedZone.format(winter));
        System.out.println("summer=" + selectedZone.format(summer));

        System.out.println("zone-then-localize=" +
                base.withZone(ZoneId.of("UTC"))
                        .localizedBy(selected).getZone());
        System.out.println("localize-then-zone=" +
                selectedZone.withZone(ZoneId.of("UTC")).getZone());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 LocalizedByTzDemo.java
java LocalizedByTzDemo
~~~

**Stdout chính xác trong môi trường JDK kiểm thử:**

~~~text
base-zone=null
withLocale-zone=null
localizedBy-zone=America/Los_Angeles
winter=2024-01-15 04:00 -08:00
summer=2024-07-15 05:00 -07:00
zone-then-localize=America/Los_Angeles
localize-then-zone=UTC
~~~

Ý nghĩa:

1. Formatter gốc chưa có override zone, vì thế `getZone()` trả `null`.
2. `withLocale` **không tự biến `tz-uslax` thành override zone**. Với các nhu cầu bản địa hóa kiểu ngôn ngữ, `withLocale` vẫn có vai trò riêng, nhưng không thay thế `localizedBy` trong ví dụ này.
3. `localizedBy` hiểu `tz-uslax` và thiết lập múi giờ Los Angeles.
4. Offset mùa đông và mùa hè khác nhau, vì `tz` chọn một **vùng thời gian với luật DST**, không phải một offset cố định như `-08:00`.
5. `withZone(UTC)` và `localizedBy(locale)` có thể ghi đè lẫn nhau theo thứ tự lời gọi. Điều này phải được xét khi cấu hình formatter trong nhiều tầng service.

**Lưu ý tính di động:** tên alias/zone ID hoặc chi tiết dữ liệu bản địa hóa có thể chịu ảnh hưởng JDK và phiên bản CLDR/TZDB. Kiểm thử nghiệp vụ nên xác nhận offset tại thời điểm cố định và vùng được chọn, không khóa cứng vào tên hiển thị được dịch hoặc viết tắt vùng có thể thay đổi theo dữ liệu locale.

## 7. Lựa chọn múi giờ theo các ngôn ngữ và vùng khác nhau

Khóa `tz` không bị giới hạn bởi ngôn ngữ trong Locale. `vi-VN-u-tz-uslax` vẫn có ngôn ngữ tiếng Việt, nhưng **múi giờ lựa chọn** là Los Angeles. Đây là điều quan trọng trong ứng dụng đa quốc gia: một người dùng nói tiếng Việt không nhất thiết muốn mọi lịch hẹn hiển thị theo giờ Việt Nam.

Với ba ví dụ điển hình:

~~~text
vi-VN-u-tz-vnsgn  -> lựa chọn giờ Thành phố Hồ Chí Minh
ja-JP-u-tz-jptyo  -> lựa chọn giờ Tokyo
en-US-u-tz-usnyc  -> lựa chọn giờ New York
~~~

Các tag có thể dùng cho một màn hình đồng hồ/thông báo với cùng một thời điểm `Instant`. **Cùng một Instant** được diễn đạt thành **giờ địa phương khác nhau**; bản thân thời điểm không đổi.

### `DateFormat` cũng nhận `tz` qua factory theo Locale

JEP 314 còn mô tả `java.text.DateFormat.get*Instance(..., locale)` tạo formatter dựa trên `tz`. API này **vẫn có trong Java**, hữu ích khi tương tác với hệ thống hiện có. Tuy vậy, code mới nên ưu tiên `java.time.DateTimeFormatter` do kiểu dữ liệu và cấu hình thời gian rõ ràng hơn.

Không dùng việc thử nhiều `Locale` rồi đoán từ tên hiển thị như `PST`, `PDT` hoặc chuỗi dịch: các tên này phụ thuộc dữ liệu locale, mùa và provider. Hãy dùng `ZoneId` và thời điểm kiểm thử cố định để xác nhận.

## 8. Chương trình hoàn chỉnh 3 — Việt Nam, Tokyo, New York và `DateFormat`

Lưu **`LocaleTzChoicesDemo.java`**:

~~~java
import java.text.DateFormat;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleTzChoicesDemo {
    static String display(Instant instant, Locale locale) {
        return DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.US)
                .localizedBy(locale)
                .format(instant);
    }

    public static void main(String[] args) {
        Instant fixed = Instant.parse("2024-01-15T12:00:00Z");

        Locale vietnam = Locale.forLanguageTag("vi-VN-u-tz-vnsgn");
        Locale tokyo = Locale.forLanguageTag("ja-JP-u-tz-jptyo");
        Locale newYork = Locale.forLanguageTag("en-US-u-tz-usnyc");

        System.out.println("vn-tz=" + vietnam.getUnicodeLocaleType("tz"));
        System.out.println("vn-time=" + display(fixed, vietnam));
        System.out.println("tokyo-time=" + display(fixed, tokyo));
        System.out.println("new-york-time=" + display(fixed, newYork));

        DateFormat oldApi = DateFormat.getDateTimeInstance(
                DateFormat.SHORT, DateFormat.SHORT, newYork);
        System.out.println("dateformat-zone=" +
                oldApi.getTimeZone().getID());
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 LocaleTzChoicesDemo.java
java LocaleTzChoicesDemo
~~~

**Stdout chính xác trên JDK kiểm thử:**

~~~text
vn-tz=vnsgn
vn-time=2024-01-15 19:00 +07:00
tokyo-time=2024-01-15 21:00 +09:00
new-york-time=2024-01-15 07:00 -05:00
dateformat-zone=America/New_York
~~~

`2024-01-15T12:00:00Z` tương ứng 19 giờ tại Thành phố Hồ Chí Minh (+07:00), 21 giờ tại Tokyo (+09:00), và 7 giờ sáng tại New York (-05:00 ở thời điểm này). Cùng một sự kiện được hiển thị theo múi giờ mà **mỗi Locale yêu cầu**.

Dòng `dateformat-zone` chứng minh Java 10+ cho phép `DateFormat` do factory theo Locale hiểu `tz`. Chương trình chỉ in ID múi giờ từ `DateFormat`, không in toàn bộ câu ngày tháng đã dịch, để tránh khẳng định quá mức về định dạng văn bản có thể khác giữa phiên bản CLDR.

**Lưu ý về `vnsgn`:** kết quả hiển thị giờ trong ví dụ không phụ thuộc vào việc provider trả ID `Asia/Saigon` hay alias `Asia/Ho_Chi_Minh`; kiểm tra trực tiếp giờ/offset tại thời điểm đã xác định là cách phù hợp hơn.

## 9. Một `Locale` có `tz` không thay đổi múi giờ mặc định của JVM

Một suy luận sai thường gặp:

> “Sau khi tạo `Locale.forLanguageTag("en-US-u-tz-uslax")`, cả chương trình sẽ tự chuyển sang giờ Los Angeles.”

**Không đúng.** `Locale` chứa metadata, còn `DateTimeFormatter.localizedBy(locale)` áp dụng metadata đó lên **formatter mới**. Tự tạo Locale hoặc một formatter **không gọi `TimeZone.setDefault(...)`**, **không gọi `System.setProperty("user.timezone", ...)`** và **không sửa `ZoneId.systemDefault()`**.

Phân biệt:

- `Locale.getDefault()`: lựa chọn locale mặc định của JVM cho dịch vụ bản địa hóa.
- `TimeZone.getDefault()` và `ZoneId.systemDefault()`: múi giờ mặc định của JVM, xuất phát từ cấu hình môi trường và có thể bị thay đổi theo API hệ thống.
- `Locale.forLanguageTag("...-u-tz-...")`: một Locale **cụ thể** mang lựa chọn `tz`.
- `formatter.localizedBy(locale)`: áp dụng lựa chọn trên **đối tượng formatter đó**.
- `Instant`: một thời điểm tuyệt đối, không tự gắn múi giờ địa phương.
- `ZoneId`: múi giờ IANA cần cho việc xác định quy tắc offset/DST của một thời điểm hoặc một lịch hẹn.

**Hạn chế sửa default toàn tiến trình**, đặc biệt ở ứng dụng web/multi-tenant. Một người dùng ở New York và người dùng khác ở Tokyo phải có cấu hình riêng thay vì tranh nhau gọi `TimeZone.setDefault`.

### Không truyền mã `tz` trực tiếp cho `ZoneId.of`

~~~java
Locale selected = Locale.forLanguageTag("en-US-u-tz-uslax");

// SAI: uslax là CLDR short ID, không phải IANA ZoneId
// ZoneId.of("uslax");

// ĐÚNG: sử dụng ID IANA khi nghiệp vụ cần ZoneId tường minh
ZoneId zone = ZoneId.of("America/Los_Angeles");
~~~

Đây là đoạn trong phương thức; các dòng có chú thích “SAI” được **comment out** để mã còn chạy được. Trên JDK kiểm thử, `ZoneId.of("uslax")` ném `ZoneRulesException`. Một số API khác như `TimeZone.getTimeZone("uslax")` có thể **âm thầm trả `GMT` nếu ID không được hỗ trợ**; đừng sử dụng cách đó để “xác minh” một mã CLDR.

## 10. Chương trình hoàn chỉnh 4 — Lỗi mã không hợp lệ và default JVM

Lưu **`LocaleTzSafetyDemo.java`**:

~~~java
import java.time.ZoneId;
import java.time.DateTimeException;
import java.time.format.DateTimeFormatter;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.TimeZone;

public class LocaleTzSafetyDemo {
    public static void main(String[] args) {
        Locale selected = Locale.forLanguageTag("en-US-u-tz-uslax");
        ZoneId globalBefore = ZoneId.systemDefault();

        DateTimeFormatter fmt = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm XXX")
                .localizedBy(selected);

        System.out.println("locale-chosen-zone=" + fmt.getZone());
        System.out.println("global-unchanged=" +
                globalBefore.equals(ZoneId.systemDefault()));

        try {
            ZoneId.of("uslax");
        } catch (DateTimeException expected) {
            System.out.println("ZoneId-short-key=" +
                    expected.getClass().getSimpleName());
        }

        System.out.println("TimeZone-short-key=" +
                TimeZone.getTimeZone("uslax").getID());

        try {
            new Locale.Builder().setLanguage("en")
                    .setUnicodeLocaleKeyword(
                            "tz", "America/Los_Angeles");
        } catch (IllformedLocaleException expected) {
            System.out.println("invalid-locale-type=" +
                    expected.getClass().getSimpleName());
        }

        Locale unknown = Locale.forLanguageTag("en-US-u-tz-zzzzz");
        System.out.println("unknown-type=" +
                unknown.getUnicodeLocaleType("tz"));
        System.out.println("unknown-resolved=" +
                DateTimeFormatter
                        .ofPattern("uuuu-MM-dd HH:mm XXX")
                        .localizedBy(unknown).getZone());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 LocaleTzSafetyDemo.java
java LocaleTzSafetyDemo
~~~

**Stdout trên JDK 24 đã kiểm thử:**

~~~text
locale-chosen-zone=America/Los_Angeles
global-unchanged=true
ZoneId-short-key=ZoneRulesException
TimeZone-short-key=GMT
invalid-locale-type=IllformedLocaleException
unknown-type=zzzzz
unknown-resolved=null
~~~

Giải thích thận trọng:

1. Lựa chọn `uslax` được áp dụng cho `fmt`; múi giờ mặc định của JVM không bị đổi trong ví dụ.
2. `ZoneId.of("uslax")` không hiểu mã ngắn CLDR. `TimeZone.getTimeZone("uslax")` trên JDK kiểm thử lại cho `GMT` — có thể gây **sai giờ một cách im lặng** nếu coi đó là kết quả chuyển đổi hợp lệ.
3. `Locale.Builder` kiểm tra **cú pháp**: đưa `America/Los_Angeles` vào vị trí Unicode locale type làm phát sinh `IllformedLocaleException`.
4. `zzzzz` là một giá trị có thể được lưu dưới dạng locale type đúng cú pháp, nhưng không có ý nghĩa múi giờ được JDK kiểm thử nhận diện; `localizedBy` không thiết lập override zone, trả `null`. Không được coi mọi chuỗi 3–8 ký tự là múi giờ hợp lệ.
5. Với mã người dùng nhập, nên kiểm tra **có được CLDR/JDK hỗ trợ hay không** trước khi dùng; không chỉ dựa vào `getUnicodeLocaleType("tz") != null`. Danh sách ánh xạ CLDR có thể thay đổi/bổ sung theo phiên bản dữ liệu, nên cần chiến lược cập nhật và thông báo lỗi rõ ràng.

**Đối với bài test xuyên nhiều phiên bản:** kết quả fallback hoặc tên alias từ các ID không được hỗ trợ có thể phụ thuộc implementation/data provider. Các dòng chứa `zzzzz` và `TimeZone.getTimeZone("uslax")` ở đây minh họa hành vi quan sát trên JDK 24, **không phải đề xuất dựa vào fallback ấy trong logic nghiệp vụ**.

## 11. Lưu thời điểm và lựa chọn múi giờ: không đánh đồng

Với lịch hẹn, giao dịch hoặc tác vụ định kỳ, thường cần phân biệt:

1. **Thời điểm đã xảy ra:** `Instant`, chẳng hạn `2024-07-15T12:00:00Z`.
2. **Múi giờ dùng để hiển thị:** một `ZoneId` IANA hoặc tùy chọn `tz` đã được xác thực.
3. **Ngôn ngữ, định dạng vùng:** `Locale`, ví dụ `vi-VN` hay `en-US`.
4. **Thời gian địa phương cho cuộc hẹn tương lai:** `LocalDateTime` **cùng ZoneId và chính sách xử lý DST**; không chỉ lưu một local time trần.

Không phải một chuỗi `Locale` duy nhất luôn đủ cho mọi mục đích. Dùng `tz` để diễn đạt lựa chọn bản địa hóa trong BCP 47 khi có nhu cầu, nhưng đối với dữ liệu nghiệp vụ về thời gian nên lưu **IANA ZoneId** (ví dụ `America/Los_Angeles` hoặc `Asia/Ho_Chi_Minh`) nếu cần tính giờ theo các quy tắc thực.

### Offset cố định không thay thế một múi giờ có DST

- `ZoneOffset.of("-08:00")` là một **offset cố định**, không tự đổi mùa.
- `ZoneId.of("America/Los_Angeles")` mô tả một **vùng thời gian** có quy tắc offset theo ngày/lịch sử; năm 2024, mùa đông là `-08:00` và mùa hè là `-07:00`.
- `Locale.forLanguageTag("en-US-u-tz-uslax")` biểu thị **lựa chọn vùng Los Angeles qua CLDR** khi được dùng với dịch vụ hỗ trợ.

Dùng một offset cố định để lập lịch cuộc hẹn định kỳ qua các tháng có thể tạo sai giờ khi tới thời điểm DST. Hãy dùng ZoneId thuộc khu vực được chọn và quy tắc quản lý trường hợp giờ địa phương bị bỏ qua hoặc lặp lại khi chuyển DST.

## 12. Chương trình hoàn chỉnh 5 — Cùng một `Instant`, nhiều múi giờ hiển thị

Lưu **`ExplicitZoneStorageDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitZoneStorageDemo {
    public static void main(String[] args) {
        Instant timestamp = Instant.parse("2024-07-15T12:00:00Z");

        ZonedDateTime losAngeles = timestamp.atZone(
                ZoneId.of("America/Los_Angeles"));
        ZonedDateTime vietnam = timestamp.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US);

        System.out.println("los-angeles=" +
                display.format(losAngeles));
        System.out.println("vietnam=" +
                display.format(vietnam));
        System.out.println("same-instant=" +
                losAngeles.toInstant().equals(vietnam.toInstant()));

        Locale vietnamLanguageLaZone =
                Locale.forLanguageTag("vi-VN-u-tz-uslax");
        DateTimeFormatter fromLocale =
                display.localizedBy(vietnamLanguageLaZone);

        System.out.println("language=" +
                vietnamLanguageLaZone.getLanguage());
        System.out.println("locale-zone=" + fromLocale.getZone());
        System.out.println("locale-display=" +
                fromLocale.format(timestamp));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ExplicitZoneStorageDemo.java
java ExplicitZoneStorageDemo
~~~

**Stdout trong môi trường kiểm thử:**

~~~text
los-angeles=2024-07-15 05:00 -07:00
vietnam=2024-07-15 19:00 +07:00
same-instant=true
language=vi
locale-zone=America/Los_Angeles
locale-display=2024-07-15 05:00 -07:00
~~~

Điều chương trình cho thấy:

- Một `Instant` có thể được xem dưới nhiều múi giờ mà không biến thành một thời điểm khác.
- `ZonedDateTime` mang thông tin vùng cụ thể; `DateTimeFormatter` dùng vùng đó khi định dạng.
- Locale có ngôn ngữ `vi` nhưng mang `tz-uslax` vẫn chọn giờ Los Angeles qua `localizedBy`. **Ngôn ngữ không quyết định múi giờ**.
- Với API hiển thị dựa trên Locale, có thể dùng `tz`; với nghiệp vụ cần thời điểm, lịch hẹn và cập nhật luật thời gian, tiếp tục dùng `Instant`/`ZoneId`.
- `same-instant=true` xác nhận việc đổi vùng xem giờ khác với thay đổi thời điểm trên trục thời gian.

## 13. Thiết kế chức năng “Chọn múi giờ” thực tế

Một hệ thống có màn hình hồ sơ người dùng nên có các bước rõ ràng:

1. **Chọn nguồn định danh:** lưu `ZoneId` IANA cho lịch hẹn/dữ liệu nghiệp vụ, hoặc lưu mã CLDR `tz` nếu một giao thức BCP 47 cụ thể cần. Nếu cần cả hai, lưu mối quan hệ có kiểm soát.
2. **Hiển thị nhãn người dùng:** ngôn ngữ `Locale` và nhãn time zone đã bản địa hóa chỉ phục vụ UI; không dùng chuỗi tên hiển thị làm ID kỹ thuật.
3. **Xác thực lựa chọn:** chỉ chấp nhận ID hoặc mã `tz` mà runtime và dữ liệu ánh xạ đang hỗ trợ. **Không tự nhận mọi BCP 47 type đúng cú pháp là zone hợp lệ.**
4. **Áp dụng vào định dạng:** khi nhận một BCP 47 Locale có `tz` hợp lệ, dùng `DateTimeFormatter.localizedBy(locale)`; khi đã có `ZoneId` IANA được xác thực, dùng `DateTimeFormatter.withZone(zone)` để rõ nguồn quyết định.
5. **Không đổi default JVM:** không gọi `TimeZone.setDefault` vì từng request hoặc từng user. Formatter `java.time` là immutable, dễ tái sử dụng nếu cấu hình không bị thay đổi ngoài ý muốn.
6. **Lưu và truyền sự kiện:** dùng `Instant` để thể hiện một thời điểm; dùng `ZoneId` khi cần giữ lựa chọn khu vực hoặc tính lịch biểu.
7. **Xử lý DST:** người dùng chọn Los Angeles thì cần kiểm thử cả ngày offset `-08:00` và `-07:00`, cùng các thời điểm chuyển mùa nếu có lập lịch.
8. **Cập nhật dữ liệu múi giờ:** CLDR/TZDB được cập nhật theo thay đổi pháp luật và tên alias; không hard-code một offset cố định hay tên vùng đã dịch.
9. **Kiểm thử giao diện:** đưa ra cùng một `Instant`, đặt `Locale` hoặc `ZoneId` khác nhau và so sánh giờ/offset kỳ vọng.
10. **Thông báo khi mã không hợp lệ:** lựa chọn không được hỗ trợ cần bị từ chối hoặc fallback minh bạch theo chính sách sản phẩm. Không âm thầm chuyển sang GMT mà người dùng không biết.

### Mẫu xử lý khi ứng dụng đã có `ZoneId`

~~~java
static String renderTimestamp(Instant when, String ianaZone) {
    ZoneId zone = ZoneId.of(ianaZone);
    DateTimeFormatter fmt = DateTimeFormatter.ofPattern(
            "uuuu-MM-dd HH:mm XXX", Locale.US).withZone(zone);
    return fmt.format(when);
}
~~~

Đây là **một phương thức minh họa**, cần import `Instant`, `ZoneId`, `DateTimeFormatter` và `Locale`. `ZoneId.of` dùng ID IANA như `America/Los_Angeles`; nó không nhận `uslax` chỉ vì chuỗi đó là `tz` hợp lệ trong BCP 47.

### Mẫu khi đầu vào là Locale có `tz`

~~~java
static String renderWithLocale(Instant when, Locale selected) {
    DateTimeFormatter fmt = DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm XXX")
            .localizedBy(selected);

    if (fmt.getZone() == null) {
        throw new IllegalArgumentException(
                "Locale không xác định múi giờ được hỗ trợ");
    }
    return fmt.format(when);
}
~~~

Đây là **một phương thức minh họa**. Nó chỉ chấp nhận Locale khi việc bản địa hóa tạo ra một override zone. Trong ứng dụng thật, nên xác định rõ whitelist/nguồn CLDR được hỗ trợ cho lựa chọn, vì một Locale có `tz` về mặt cú pháp chưa chắc đủ để chỉ ra múi giờ hợp lệ.

Không đưa thông báo tiếng Việt vào logic quốc tế hóa nếu dự án yêu cầu thông báo theo ngôn ngữ người dùng; câu thông báo ở đây chỉ minh họa lỗi khi thiếu ánh xạ.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `en-US` đủ để suy ra Los Angeles | US có nhiều vùng thời gian | Chọn `tz-uslax` hoặc `ZoneId` riêng |
| `tz` có thể chứa `America/Los_Angeles` | Đây không phải type BCP 47 đúng cú pháp | Trong Locale dùng `uslax`, trong `ZoneId` dùng ID IANA |
| `ZoneId.of("uslax")` trả Los Angeles | `uslax` là mã ngắn CLDR, không phải IANA ID | Dùng ID đã ánh xạ/xác thực |
| Cứ gọi `withLocale` thì sẽ áp dụng `tz` | `withLocale` không tự đặt override zone trong ví dụ này | Dùng `localizedBy` khi muốn áp dụng Unicode extension |
| Tạo Locale có `tz` sẽ đổi giờ toàn JVM | Locale chỉ mang dữ liệu, không tự sửa default | Dùng formatter được cấu hình theo request |
| `tz-uslax` đồng nghĩa offset `-08:00` cố định | LA có DST theo mùa | Dùng vùng có ZoneRules và Instant |
| Mọi type `tz` đúng cú pháp đều được nhận diện | BCP 47 syntax và CLDR semantic validity khác nhau | Kiểm tra dữ liệu ánh xạ được hỗ trợ |
| Dùng `TimeZone.getTimeZone("uslax")` để chuyển mã | API có thể trả GMT khi input không được công nhận | Dùng mapping chuẩn và validate |
| Dùng tên hiển thị “PST” làm ID ổn định | Tên hiển thị/viết tắt không duy nhất, có thể đổi | Lưu ZoneId IANA hoặc short ID CLDR được xác thực |
| Truyền `Instant` vào formatter chưa có zone | Các field giờ địa phương không thể suy ra từ Instant đơn lẻ | Gắn zone bằng `localizedBy` hoặc `withZone` |
| Dùng `Locale.setDefault` cho mỗi user | Tác động trạng thái toàn tiến trình, dễ xung đột request | Truyền Locale/zone cụ thể cho từng phép định dạng |
| Khóa cứng tên `Asia/Saigon`/`Asia/Ho_Chi_Minh` ở mọi JDK | Alias/ID có thể được xử lý khác giữa data provider | Kiểm tra ZoneRules, offset và IANA ID đã chọn |
| Xem `java.text.DateFormat` là cách tốt nhất cho mọi code mới | `java.time` cho mô hình Instant/ZoneId/formatter rõ hơn | Ưu tiên `java.time`, chỉ tích hợp DateFormat khi có lý do |
| Kiểm thử với `now()` rồi assert giờ cố định | Thời điểm hiện tại và timezone mặc định thay đổi | Dùng `Instant.parse` có timestamp xác định |

## 15. Checklist kiểm thử mã nguồn có khóa `tz`

Kiểm thử ít nhất những trường hợp sau:

1. **Cú pháp hợp lệ:** `Locale.forLanguageTag("en-US-u-tz-uslax")` giữ thẻ và `getUnicodeLocaleType("tz")` trả `uslax`.
2. **Tạo bằng Builder:** kết quả bằng Locale tạo từ BCP 47 nếu language, region và type tương đương.
3. **Không có `tz`:** `Locale.US.getUnicodeLocaleType("tz") == null`; ứng dụng phải có chính sách fallback rõ ràng.
4. **Có `tz` nhưng type không được hỗ trợ:** thử mã đúng cú pháp nhưng không đăng ký; không mặc định coi đó là lựa chọn hợp lệ.
5. **Phân biệt API:** `withLocale` không thiết lập zone từ `tz` trong trường hợp kiểm thử, `localizedBy` có áp dụng zone.
6. **Thời điểm mùa đông và mùa hè:** với Los Angeles, `2024-01-15T12:00:00Z` và `2024-07-15T12:00:00Z` có offset khác nhau.
7. **Ngôn ngữ khác múi giờ:** `vi-VN-u-tz-uslax` phải thể hiện tiếng Việt (qua Locale) và giờ Los Angeles (qua tz); không ép về giờ Việt Nam theo language tag.
8. **Không động chạm mặc định JVM:** tạo formatter theo user không được làm thay đổi `ZoneId.systemDefault()`.
9. **Chuỗi IANA và CLDR:** `ZoneId.of("America/Los_Angeles")` hợp lệ, còn `ZoneId.of("uslax")` không phải cách chuyển mã.
10. **Thứ tự ghi đè:** `localizedBy` rồi `withZone` có thể cho zone khác so với `withZone` rồi `localizedBy`.
11. **Data provider:** không assert các chuỗi dịch tên múi giờ, tên alias hay thứ tự locale data nếu chúng không thuộc hợp đồng của ứng dụng.
12. **Lịch hẹn tương lai:** lựa chọn vùng có DST phải được áp dụng theo quy tắc zone tại ngày hẹn, không sử dụng offset tại ngày hiện tại cho mọi lịch.

Một bài test tốt nên so sánh các mốc thời gian cố định, `formatter.getZone()` khi có ý nghĩa, và offset tại một `Instant` cụ thể. Kiểm thử bất kỳ một locale khó đọc/không có dữ liệu provider cũng cần biết phạm vi bộ dữ liệu cài đặt của runtime.

## 16. Câu hỏi tự kiểm tra

1. Trong thẻ `en-US-u-tz-uslax`, đâu là language, region, Unicode extension key và type?
2. `getUnicodeLocaleType("tz")` trả chuỗi gì với thẻ trên? Nó có trực tiếp trả `America/Los_Angeles` không?
3. Khóa `tz` được Java hỗ trợ áp dụng cho các dịch vụ liên quan từ phiên bản nào, theo JEP nào?
4. `DateTimeFormatter.withLocale(locale)` và `localizedBy(locale)` có giống nhau về việc đặt override zone từ `tz` không?
5. Vì sao cần short code `uslax` thay vì viết `America/Los_Angeles` ngay sau `u-tz-`?
6. Vì sao cùng `2024-01-15T12:00:00Z` nhưng Los Angeles hiển thị 04:00 và Tokyo hiển thị 21:00?
7. Lựa chọn `vi-VN-u-tz-uslax` có buộc phải hiển thị giờ Việt Nam chỉ vì language là `vi` không?
8. Tạo một Locale có `tz` có tự gọi `TimeZone.setDefault` hay thay `ZoneId.systemDefault` không?
9. Nếu người dùng chọn Los Angeles, có nên lưu `-08:00` làm offset vĩnh viễn không?
10. Tại sao `ZoneId.of("uslax")` không phải cách áp dụng khóa `tz`?
11. Thẻ có `tz-zzzzz` đúng cú pháp thì có chắc runtime hiểu đó là múi giờ hợp lệ không?
12. Khi ứng dụng phải tính lịch hẹn và lưu thời điểm, nên giữ `Instant`/`ZoneId` hay chỉ chuỗi tên vùng đã dịch?

**Đáp án:**

1. `en` = language, `US` = region, `u` = Unicode extension, `tz` = key, `uslax` = type.
2. Trả `uslax`; không tự chuyển thành ID IANA.
3. Java 10, theo **JEP 314**.
4. Không; `localizedBy` áp dụng lựa chọn zone từ extension khi được hỗ trợ, còn `withLocale` không tự biến `tz` thành override zone.
5. Unicode BCP 47 dùng mã type ngắn theo CLDR; tên IANA chứa dấu `/` và `_` không đúng cú pháp type đó.
6. Một Instant được diễn giải theo các quy tắc timezone và offset khác nhau.
7. Không. `tz-uslax` có thể chọn Los Angeles dù ngôn ngữ là tiếng Việt.
8. Không.
9. Không; khu vực Los Angeles có quy tắc DST và offset có thể đổi theo ngày.
10. `uslax` là short ID CLDR, không phải một `ZoneId` IANA đã được `ZoneId.of` cam kết nhận.
11. Không; đúng cú pháp không bảo đảm type đã đăng ký hoặc có ánh xạ được hỗ trợ.
12. Dùng `Instant` để lưu thời điểm và `ZoneId` cho vùng/lịch hẹn; Locale/`tz` có thể lưu như preference bản địa hóa riêng.

## 17. Tài liệu chính thức đang áp dụng

- **OpenJDK — JEP 314, Additional Unicode Language-Tag Extensions (Java 10):** https://openjdk.org/jeps/314
- **Oracle — Internationalization Enhancements in JDK 10:** https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm
- **Oracle Javadoc — `Locale` và Unicode Locale Extension, Java SE 26:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html
- **Oracle Javadoc — `Locale.Builder`, `setUnicodeLocaleKeyword`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html
- **Oracle Javadoc — `DateTimeFormatter.localizedBy` và `withLocale`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html
- **Oracle Javadoc — `ZoneId` và timezone rules:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- **Oracle Javadoc — `TimeZone`, lưu ý fallback khi ID không hợp lệ:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TimeZone.html
- **Unicode CLDR — Unicode Timezone Identifier và short IDs:** https://www.unicode.org/reports/tr35/
- **Unicode CLDR — Time Zone Identifiers và cách liên hệ short ID với TZDB/IANA:** https://unicode.org/reports/tr35/tr35.html

**Ghi nhớ:** `tz` là **khóa lựa chọn múi giờ trong Unicode locale extension**, ví dụ `en-US-u-tz-uslax`. Java 10+ có `DateTimeFormatter.localizedBy(locale)` để áp dụng lựa chọn này vào định dạng ngày giờ; `withLocale` đơn thuần không thay thế nó. **Đừng nhầm mã `tz` ngắn với IANA `ZoneId`, đừng dùng offset cố định thay vùng có DST, và đừng thay đổi múi giờ mặc định toàn JVM theo từng người dùng.** Dùng `Instant` và `ZoneId` khi lưu/tính toán thời gian, và dùng `Locale` với `tz` được xác thực khi cần biểu diễn một lựa chọn bản địa hóa.