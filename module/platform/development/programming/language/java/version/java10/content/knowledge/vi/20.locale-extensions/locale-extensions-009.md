# Quan hệ giữa các khóa `ca` và `nu` trong Unicode Locale Extensions (Java 10+)

## Mục tiêu bài học

`java.util.Locale` không chỉ lưu mã ngôn ngữ và vùng lãnh thổ như `vi-VN`, `ja-JP` hay `th-TH`. Theo chuẩn **IETF BCP 47** và **Unicode Locale Data Markup Language (UTS #35/LDML)**, một thẻ ngôn ngữ có thể chứa các **Unicode locale keyword** để mô tả cách ứng dụng mong muốn xử lý lịch, chữ số, tiền tệ, vùng áp dụng quy tắc hoặc múi giờ.

Trong nhóm này, hai khóa nền tảng là:

- **`ca` — calendar**: hệ lịch, ví dụ `buddhist`, `japanese`, `gregory`.
- **`nu` — numbering system**: hệ chữ số dùng khi định dạng, ví dụ `thai`, `latn`, `arab`.

Hai khóa **độc lập nhưng có thể phối hợp**. Một locale có thể yêu cầu **lịch Phật giáo** và **chữ số Thái** cùng lúc: `th-TH-u-ca-buddhist-nu-thai`.

Điểm lịch sử quan trọng: **`ca` và `nu` đã được Java hỗ trợ trước Java 10**, cụ thể tài liệu quốc tế hóa của Oracle ghi nhận Java SE 9 đã hỗ trợ hai khóa này. Java 10 mở rộng hỗ trợ thêm **`cu`** (currency), **`fw`** (first day of week), **`rg`** (region override), **`tz`** (time zone), đồng thời giới thiệu **`DateTimeFormatter.localizedBy(Locale)`** để áp dụng các lựa chọn bản địa hóa có trong locale. Không nên trình bày `ca` và `nu` như tính năng lần đầu xuất hiện ở Java 10.

Sau bài này, bạn sẽ:

1. Đọc và tạo BCP 47 tag có các cặp `ca`/`nu`.
2. Phân biệt chức năng của hai khóa và hiểu chúng không thay thế nhau.
3. Dùng `Locale.forLanguageTag`, `Locale.Builder`, `getUnicodeLocaleType` và `toLanguageTag`.
4. Kiểm tra tác động lên `Calendar`, `Chronology`, `NumberFormat` và đặc biệt `DateTimeFormatter.localizedBy`.
5. Biết giới hạn của `withLocale`, sự phụ thuộc dữ liệu/provider của runtime, cùng các lỗi i18n thường gặp.
6. Chạy ví dụ Java 17+ có stdout đã được kiểm chứng.

## 1. Đọc cú pháp `-u-ca-...-nu-...`

Một BCP 47 language tag thông dụng có dạng:

~~~text
ngôn-ngữ [-Script] [-Vùng] -u-[khóa-loại]...
~~~

Đoạn **`-u-`** mở đầu *Unicode locale extension*. Phần sau chứa các keyword gồm **khóa hai ký tự** và **loại (type)**:

~~~text
th-TH-u-ca-buddhist-nu-thai
│  │  │ │           │
│  │  │ │           └─ nu=thai: dùng hệ chữ số Thái khi service hỗ trợ
│  │  │ └───────────── ca=buddhist: yêu cầu hệ lịch Phật giáo
│  │  └─────────────── u: Unicode locale extension
│  └────────────────── vùng TH (Thái Lan)
└───────────────────── ngôn ngữ th (tiếng Thái)
~~~

Ví dụ khác:

| Language tag | `ca` | `nu` | Ý nghĩa |
| --- | --- | --- | --- |
| `ja-JP-u-ca-japanese` | `japanese` | Không chỉ định | Nhật ngữ/Japan, ưu tiên lịch Nhật |
| `th-TH-u-nu-thai` | Không chỉ định | `thai` | Chọn chữ số Thái khi định dạng số |
| `th-TH-u-ca-buddhist-nu-thai` | `buddhist` | `thai` | Phối hợp lịch Phật giáo và chữ số Thái |
| `ja-JP-u-ca-japanese-nu-latn` | `japanese` | `latn` | Lịch Nhật, chữ số Latin `0–9` |
| `en-US-u-ca-gregory-nu-thai` | `gregory` | `thai` | Tiếng Anh/Mỹ, lịch Gregory, chữ số Thái |
| `en-US` | Không chỉ định | Không chỉ định | Dùng mặc định theo locale/provider |

Các cặp được biểu diễn bằng chữ thường trong language tag chuẩn hóa. Trong dạng serialization, các khóa Unicode được sắp xếp theo **thứ tự chữ cái** (ví dụ `ca` trước `nu`), không phải theo thứ tự lời gọi API khi xây dựng đối tượng.

**Không được nhầm:**

- `-u-` là **extension singleton**, không phải một keyword giống `ca`/`nu`.
- `ca` là **loại lịch**, không phải mã quốc gia như `CA` (Canada).
- `nu` không phải ngôn ngữ, vùng hay mã tiền tệ; nó chỉ định numbering system.
- `th` và `TH` là hai thành phần cơ bản; `ca`/`nu` là các **ưu tiên bổ sung** của dịch vụ bản địa hóa.

## 2. `ca` điều khiển điều gì?

`ca` viết tắt cho **calendar**, xác định hệ lịch mong muốn của các thành phần xử lý ngày tháng phù hợp. Một số loại có ý nghĩa:

- `gregory`: lịch Gregory.
- `buddhist`: hệ lịch Phật giáo Thái Lan.
- `japanese`: hệ lịch Nhật với các niên hiệu (*era*).

Ví dụ:

~~~java
Locale calendarLocale =
        Locale.forLanguageTag("th-TH-u-ca-buddhist");

System.out.println(calendarLocale.getUnicodeLocaleType("ca"));
// buddhist
~~~

Khi đưa locale này cho một API có hỗ trợ khóa `ca`, nó có thể dùng hệ lịch được yêu cầu. Trong Java:

~~~java
Calendar cal = Calendar.getInstance(calendarLocale);
System.out.println(cal.getCalendarType()); // buddhist trên JDK hỗ trợ
~~~

`Calendar.getInstance(Locale)` có thể nhận biết `ca`. Với `java.time`, có thể kiểm tra trực tiếp:

~~~java
Chronology chronology = Chronology.ofLocale(calendarLocale);
System.out.println(chronology.getId()); // ThaiBuddhist
~~~

Ở đây `Chronology.ofLocale` chọn một **hệ lịch**. Tuy nhiên, `LocalDate` thường vẫn là ngày ISO; chỉ đặt locale không có nghĩa đối tượng `LocalDate` gốc được đổi kiểu hoặc thay đổi giá trị ngày.

**Cần phân biệt hệ lịch với múi giờ:** `ca=japanese` nói về hệ lịch/era, **không** có nghĩa múi giờ Japan/Tokyo. Múi giờ là khái niệm độc lập, có thể được điều khiển bằng `ZoneId`, `TimeZone` hoặc Unicode key `tz` ở API hỗ trợ.

### Hệ lịch không chỉ là cách in năm

Một hệ lịch có thể có cách đánh số năm, niên hiệu và quy tắc xác định ngày khác. Vì vậy đừng nghĩ `ca` luôn chỉ cộng/trừ một hằng số vào năm ISO. Ví dụ `japanese` liên quan đến **era Nhật**, còn `buddhist` có cách biểu diễn năm Phật lịch. Với xử lý ngày tháng nghiệp vụ, cần chọn `Chronology` phù hợp, không tự biến đổi số năm bằng công thức tùy ý.

## 3. `nu` điều khiển điều gì?

`nu` là khóa **numbering system**: nó biểu thị kiểu chữ số hoặc hệ số được một số dịch vụ định dạng hỗ trợ. Các loại thường gặp:

| Giá trị `nu` | Ý nghĩa điển hình |
| --- | --- |
| `latn` | Chữ số Latin/ASCII `0 1 2 ... 9` |
| `thai` | Chữ số Thái `๐ ๑ ๒ ... ๙` |
| `arab` | Chữ số Arabic-Indic trong các locale/provider phù hợp |

Ví dụ:

~~~java
Locale thaiDigits = Locale.forLanguageTag("th-TH-u-nu-thai");
NumberFormat formatter = NumberFormat.getIntegerInstance(thaiDigits);

String localizedNumber = formatter.format(12345);
// Trên JDK có dữ liệu locale tương ứng: "๑๒,๓๔๕"
~~~

Giá trị số nguyên `12345` **không thay đổi**. Chỉ **biểu diễn dạng văn bản** được bản địa hóa. `nu` không biến `int`, `long`, `BigDecimal` hay các phép tính của Java thành một hệ số học khác.

Một cách kiểm tra ký tự số không dựa vào dấu phân tách hàng nghìn:

~~~java
char zero = DecimalFormatSymbols.getInstance(thaiDigits)
        .getZeroDigit();
// Trên JDK hỗ trợ nu=thai, zero là ký tự '๐'.
~~~

Tuy nhiên, `nu` không phải mệnh lệnh tuyệt đối đối với **mọi** thư viện:

- API locale-sensitive như `NumberFormat` có thể áp dụng numbering system.
- `String.valueOf(12345)` hoặc `Integer.toString(12345)` không tự nhận một `Locale` và không đổi sang chữ số Thái.
- `DecimalFormatSymbols` và `DateTimeFormatter` có cơ chế điều chỉnh chữ số riêng.
- Mức hỗ trợ của một tổ hợp khóa/loại có thể phụ thuộc CLDR, provider và runtime.

Đừng dùng kết quả của `String.valueOf` để kiểm tra liệu `nu` đã được một `Locale` lưu hay chưa. Hãy dùng đúng dịch vụ định dạng có nhận Locale.

## 4. Quan hệ thực sự giữa `ca` và `nu`

Hai khóa biểu diễn **hai chiều bản địa hóa độc lập**:

| Thành phần | `ca` | `nu` |
| --- | --- | --- |
| Điều khiển | Hệ lịch/chronology | Hệ chữ số/numbering |
| Phạm vi điển hình | `Calendar`, `Chronology`, formatter ngày có hỗ trợ | `NumberFormat`, `DecimalFormatSymbols`, formatter số/ngày có hỗ trợ |
| Có thể tồn tại riêng? | Có | Có |
| Có thể kết hợp? | Có | Có |
| Tác động trực tiếp lên phép tính số? | Không | Không |
| Tự đặt múi giờ? | Không | Không |
| Có thay đổi `Locale.getLanguage()/getCountry()`? | Không | Không |

Do độc lập, cùng một locale có thể:

- Dùng hệ lịch **Phật giáo**, nhưng số biểu diễn bằng **chữ số Latin**: `th-TH-u-ca-buddhist-nu-latn`.
- Dùng hệ lịch **ISO/Gregory** phù hợp và chữ số **Thái**: `th-TH-u-ca-gregory-nu-thai`.
- Dùng hệ lịch **Nhật** và số thông thường bằng **Latin**: `ja-JP-u-ca-japanese-nu-latn`.
- Dùng đồng thời lịch Phật giáo và chữ số Thái: `th-TH-u-ca-buddhist-nu-thai`.

Với ngày ISO `2024-04-13`, cách hiển thị với Thai Buddhist chronology có thể biểu diễn năm **2567**; khi chọn `nu=thai`, các chữ số hiển thị có thể là `๒๕๖๗`. Hai thay đổi không mâu thuẫn: một thay đổi **giá trị trường năm của hệ lịch khi biểu diễn**, một thay đổi **glyph chữ số**.

**Không được khẳng định** `ca` luôn tự áp `nu`, hoặc `nu` luôn tự chọn lịch tương ứng. Thái Lan có mặc định văn hóa trong một số API, nhưng đó là **quy ước mặc định/compatibility**, không phải quan hệ logic bắt buộc giữa hai Unicode keyword.

## 5. Tạo và đọc Locale chứa hai khóa

### 5.1. Dùng `Locale.forLanguageTag`

~~~java
Locale locale =
        Locale.forLanguageTag("th-TH-u-ca-buddhist-nu-thai");

System.out.println(locale.toLanguageTag());
// th-TH-u-ca-buddhist-nu-thai

System.out.println(locale.getUnicodeLocaleType("ca")); // buddhist
System.out.println(locale.getUnicodeLocaleType("nu")); // thai
~~~

`forLanguageTag` là API hiện hành để tạo `Locale` từ BCP 47 language tag. `toLanguageTag()` là cách phù hợp để **serialize** Locale theo BCP 47; không dùng `Locale.toString()` thay cho tag trao đổi giữa các hệ thống vì cú pháp của nó được thiết kế cho debugging/compatibility.

### 5.2. Dùng `Locale.Builder`

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setUnicodeLocaleKeyword("ca", "japanese")
        .build();

System.out.println(locale.toLanguageTag());
// en-US-u-ca-japanese-nu-thai
~~~

Dù gọi `setUnicodeLocaleKeyword("nu",...)` trước `setUnicodeLocaleKeyword("ca",...)`, tag chuẩn hóa vẫn hiển thị **`ca` trước `nu`** theo thứ tự khóa.

Builder hữu ích khi các lựa chọn đến từ form cấu hình tách rời, thay vì phải nối thủ công một language tag.

### 5.3. Phân biệt extension `u` với từng keyword

~~~java
String extension = locale.getExtension(Locale.UNICODE_LOCALE_EXTENSION);
// "ca-japanese-nu-thai"

String calendarType = locale.getUnicodeLocaleType("ca");
// "japanese"

String numberingType = locale.getUnicodeLocaleType("nu");
// "thai"
~~~

`getExtension('u')` trả về **toàn bộ nội dung của extension `u`**, không phải một giá trị `ca` riêng. Khi cần một loại cụ thể, dùng `getUnicodeLocaleType("ca")` hoặc `getUnicodeLocaleType("nu")`.

`getUnicodeLocaleKeys()` trả tập các khóa Unicode của Locale. Nếu bạn cần kiểm tra có cả hai khóa, dùng `contains("ca")` và `contains("nu")`, không dựa vào **thứ tự duyệt** của một `Set`.

### 5.4. Nếu khóa không có mặt thì sao?

~~~java
Locale simple = Locale.forLanguageTag("en-US");
String value = simple.getUnicodeLocaleType("ca"); // null
~~~

- **`null`**: khóa không được định nghĩa trong Locale.
- **Chuỗi rỗng `""`**: khóa có mặt nhưng không chỉ định type trong các trường hợp cú pháp cho phép.
- **Chuỗi type** như `"japanese"`: keyword được khai báo.

Đừng nhầm `null` (không có keyword) với `"gregory"` hay `"latn"`: nếu không khai báo, dịch vụ có thể chọn **mặc định** theo locale/provider thay vì một type cố định như bạn tự đoán.

Builder và Locale có kiểm tra **cú pháp**, nhưng việc một type có được **dịch vụ cụ thể hỗ trợ** hay không là câu hỏi khác. Một tag hợp cú pháp không tự bảo đảm formatter/chronology hiểu mọi type mà người dùng đưa vào.

## 6. Tác động lên `Calendar` và `Chronology`

### `java.util.Calendar`

~~~java
Locale thai =
        Locale.forLanguageTag("th-TH-u-ca-buddhist-nu-thai");

Calendar calendar = Calendar.getInstance(thai);

System.out.println(calendar.getCalendarType());
// buddhist trong JDK hỗ trợ
~~~

`Calendar.getInstance` nhận locale và có khả năng lựa chọn calendar type thông qua Unicode key `ca`. Tuy nhiên `Calendar` cũng có **múi giờ**, **thời điểm hiện tại** và các quy tắc hệ lịch khác. Nếu chỉ muốn kiểm tra type, dùng `getCalendarType()`, tránh in nguyên đối tượng (vốn chứa dữ liệu hiện thời và phụ thuộc timezone).

### `java.time.chrono.Chronology`

~~~java
Chronology chronology = Chronology.ofLocale(thai);
System.out.println(chronology.getId()); // ThaiBuddhist
~~~

`Chronology.ofLocale` có thể chọn hệ lịch tương ứng với `ca`. Khác biệt quan trọng là:

~~~java
Locale onlyNu = Locale.forLanguageTag("th-TH-u-nu-thai");

System.out.println(Chronology.ofLocale(onlyNu).getId());
// ISO — vì không chỉ định ca
~~~

Trong `java.time`, nếu không có `ca`, `Chronology.ofLocale` theo hợp đồng thường trả về ISO chronology. Đừng dựa vào thói quen của một API cũ chọn Thai Buddhist Calendar cho locale vùng Thái mà suy ra mọi API `java.time` cũng chọn giống hệt.

Khi cần một hệ lịch được hỗ trợ rõ ràng, có thể dùng `ThaiBuddhistChronology.INSTANCE` hoặc `JapaneseChronology.INSTANCE` trong `java.time.chrono`. Việc tạo chronology và định dạng văn bản nên được thiết kế có chủ ý, không dựa vào đối chiếu tên quốc gia một cách ngầm định.

## 7. Tác động lên `NumberFormat` và `DecimalFormatSymbols`

`NumberFormat.getInstance(Locale)` và các factory tương ứng có thể sử dụng **`nu`** để xác định chữ số:

~~~java
Locale thai =
        Locale.forLanguageTag("th-TH-u-ca-buddhist-nu-thai");

NumberFormat nf = NumberFormat.getIntegerInstance(thai);
String result = nf.format(12345);

// Với dữ liệu CLDR của JDK kiểm chứng: "๑๒,๓๔๕"
~~~

Lưu ý ba điểm:

1. `NumberFormat` quan tâm đến **numbering system**: `ca=buddhist` không tự làm `12345` thành `12988` hay một giá trị khác.
2. Dấu phân tách số (như dấu phẩy) vẫn có thể phụ thuộc locale/provider; không giả định cùng một dấu nhóm trên mọi cấu hình.
3. `NumberFormat` là formatter có trạng thái mutable, không nên chia sẻ không đồng bộ giữa nhiều thread chỉ vì `Locale` là bất biến.

Để kiểm tra biến thể chữ số Latin:

~~~java
Locale japaneseWithLatin =
        Locale.forLanguageTag("ja-JP-u-ca-japanese-nu-latn");

String number = NumberFormat.getIntegerInstance(japaneseWithLatin)
        .format(12345);

// Ví dụ được kiểm chứng trong JDK: "12,345".
~~~

Hệ lịch Nhật được chọn bởi `ca`, còn chữ số Latin bởi `nu`. Hai lựa chọn không “triệt tiêu” nhau.

**Không đưa `nu` vào nơi không hỗ trợ rồi kết luận Java sai.** `String.format`, `NumberFormat`, `DecimalFormat`, `DateTimeFormatter` và serializer JSON có hợp đồng khác nhau. Đọc Javadoc của API định dạng thực sự được gọi.

## 8. Trọng tâm Java 10: `DateTimeFormatter.localizedBy(Locale)`

Từ **Java 10**, `java.time.format.DateTimeFormatter` có phương thức:

~~~java
public DateTimeFormatter localizedBy(Locale locale)
~~~

Phương thức này tạo **một formatter mới** áp dụng các lựa chọn bản địa hóa của Locale tới **calendar/chronology**, **numbering/decimal style**, và những thuộc tính như region/timezone khi có hỗ trợ. Các khóa `ca` và `nu` có thể được áp dụng **cùng một lần**.

Đây là cầu nối trực tiếp giữa chủ đề mở rộng Locale và API được bổ sung ở Java 10.

### `localizedBy` khác `withLocale` ở đâu?

Hai lời gọi trông gần giống:

~~~java
DateTimeFormatter byLocale = base.withLocale(thai);
DateTimeFormatter fullyLocalized = base.localizedBy(thai);
~~~

Nhưng **không nên coi là alias**:

- **`withLocale(locale)`**: thay Locale của formatter; có ảnh hưởng tới bản địa hóa text/pattern, nhưng không tự lấy mọi Unicode keyword để thay chronology/decimal style đã có của formatter.
- **`localizedBy(locale)`**: áp dụng các phần bản địa hóa phù hợp gồm `ca` → chronology và `nu` → decimal style, cùng vùng/múi giờ nếu được yêu cầu và hỗ trợ.

Xét ngày ISO cố định **13/04/2024**:

~~~java
Locale thai = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist-nu-thai"
);

LocalDate isoDate = LocalDate.of(2024, 4, 13);
DateTimeFormatter base = DateTimeFormatter.ofPattern(
        "yyyy-MM-dd", Locale.US
);

System.out.println(base.format(isoDate));
// 2024-04-13

System.out.println(base.withLocale(thai).format(isoDate));
// 2024-04-13

System.out.println(base.localizedBy(thai).format(isoDate));
// ๒๕๖๗-๐๔-๑๓ trên JDK kiểm chứng
~~~

Lý do:

- Formatter gốc dùng ISO chronology/decimal style như được cấu hình.
- `withLocale(thai)` thay locale, nhưng với pattern số thuần ở đây không chuyển năm ISO thành năm Phật lịch hay đổi glyph chữ số.
- `localizedBy(thai)` áp dụng **cả hệ lịch Phật giáo** lẫn **chữ số Thái**, nên năm hiển thị là 2567 theo Phật lịch và các glyph số là chữ số Thái.
- Đối tượng `isoDate` **không bị thay đổi**. Thay đổi xảy ra ở **cách formatter biểu diễn ngày**.

Có thể kiểm tra ý định định dạng bằng API thay vì chỉ so chuỗi:

~~~java
DateTimeFormatter localized = base.localizedBy(thai);

System.out.println(localized.getChronology().getId());
// ThaiBuddhist

System.out.println(localized.getDecimalStyle().getZeroDigit());
// '๐' trên JDK hỗ trợ nu=thai
~~~

**Lưu ý về thứ tự gọi:** `localizedBy` có thể ghi đè chronology/decimal style/zone từng được cấu hình bởi các phương thức `withXXXX` tùy thứ tự chaining. Nếu ứng dụng chủ động đặt `withChronology`, `withZone` hoặc `withDecimalStyle`, cần xác định rõ lệnh nào có quyền ưu tiên và kiểm tra formatter cuối cùng. Javadoc của `localizedBy` ghi rõ thứ tự gọi có thể tạo kết quả khác.

## 9. Chương trình Java 17+ hoàn chỉnh

Ví dụ sau dùng **ngày cố định**, không phụ thuộc thời gian hiện tại. Các phép kiểm tra trong chương trình đã được chạy trên JDK của môi trường thực nghiệm có dữ liệu locale phù hợp.

Lưu toàn bộ mã vào tệp **LocaleCaNuDemo.java**:

~~~java
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.chrono.Chronology;
import java.time.format.DateTimeFormatter;
import java.util.Calendar;
import java.util.Locale;

public class LocaleCaNuDemo {
    public static void main(String[] args) {
        Locale thai = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist-nu-thai"
        );
        Locale japanese = Locale.forLanguageTag(
                "ja-JP-u-ca-japanese-nu-latn"
        );

        Locale built = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("nu", "thai")
                .setUnicodeLocaleKeyword("ca", "japanese")
                .build();

        System.out.println("thai tag: " + thai.toLanguageTag());
        System.out.println("thai ca: "
                + thai.getUnicodeLocaleType("ca"));
        System.out.println("thai nu: "
                + thai.getUnicodeLocaleType("nu"));
        System.out.println("thai extension: "
                + thai.getExtension(Locale.UNICODE_LOCALE_EXTENSION));
        System.out.println("thai calendar type: "
                + Calendar.getInstance(thai).getCalendarType());
        System.out.println("thai chronology: "
                + Chronology.ofLocale(thai).getId());
        System.out.println("thai formatted: "
                + NumberFormat.getIntegerInstance(thai).format(12345));
        System.out.println("thai zero: "
                + DecimalFormatSymbols.getInstance(thai).getZeroDigit());

        System.out.println("japanese tag: " + japanese.toLanguageTag());
        System.out.println("japanese ca: "
                + japanese.getUnicodeLocaleType("ca"));
        System.out.println("japanese nu: "
                + japanese.getUnicodeLocaleType("nu"));
        System.out.println("japanese calendar type: "
                + Calendar.getInstance(japanese).getCalendarType());
        System.out.println("japanese formatted: "
                + NumberFormat.getIntegerInstance(japanese).format(12345));

        System.out.println("builder tag: " + built.toLanguageTag());
        System.out.println("builder ca: "
                + built.getUnicodeLocaleType("ca"));
        System.out.println("builder nu: "
                + built.getUnicodeLocaleType("nu"));
        System.out.println("builder extension: "
                + built.getExtension(Locale.UNICODE_LOCALE_EXTENSION));

        LocalDate date = LocalDate.of(2024, 4, 13);
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "yyyy-MM-dd", Locale.US
        );

        System.out.println("base: " + base.format(date));
        System.out.println("withLocale: "
                + base.withLocale(thai).format(date));
        System.out.println("localizedBy: "
                + base.localizedBy(thai).format(date));
        System.out.println("localized chronology: "
                + base.localizedBy(thai).getChronology().getId());
        System.out.println("localized decimal zero: "
                + base.localizedBy(thai).getDecimalStyle().getZeroDigit());

        Locale onlyNu = Locale.forLanguageTag("th-TH-u-nu-thai");
        System.out.println("no ca: "
                + Chronology.ofLocale(onlyNu).getId());

        Locale latinDigits = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist-nu-latn"
        );
        System.out.println("no thai digits: "
                + NumberFormat.getIntegerInstance(latinDigits).format(12345));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocaleCaNuDemo.java
java LocaleCaNuDemo
~~~

**Stdout đã xác minh trên JDK có dữ liệu locale tương ứng:**

~~~text
thai tag: th-TH-u-ca-buddhist-nu-thai
thai ca: buddhist
thai nu: thai
thai extension: ca-buddhist-nu-thai
thai calendar type: buddhist
thai chronology: ThaiBuddhist
thai formatted: ๑๒,๓๔๕
thai zero: ๐
japanese tag: ja-JP-u-ca-japanese-nu-latn
japanese ca: japanese
japanese nu: latn
japanese calendar type: japanese
japanese formatted: 12,345
builder tag: en-US-u-ca-japanese-nu-thai
builder ca: japanese
builder nu: thai
builder extension: ca-japanese-nu-thai
base: 2024-04-13
withLocale: 2024-04-13
localizedBy: ๒๕๖๗-๐๔-๑๓
localized chronology: ThaiBuddhist
localized decimal zero: ๐
no ca: ISO
no thai digits: 12,345
~~~

**Giải thích vì sao đầu ra đúng:**

1. `toLanguageTag` trả về BCP 47 tag chuẩn hóa với `ca` và `nu` theo thứ tự khóa.
2. `getUnicodeLocaleType` đọc type của từng keyword một cách độc lập.
3. `getExtension(Locale.UNICODE_LOCALE_EXTENSION)` trả phần `u` không kèm prefix `u-`.
4. `Calendar.getInstance(thai)` chọn `buddhist`; `Chronology.ofLocale(thai)` chọn `ThaiBuddhist`.
5. `NumberFormat` dùng chữ số Thái khi `nu=thai`, nhưng chữ số Latin khi `nu=latn`.
6. Builder cho tag chuẩn hóa giống cấu trúc yêu cầu, dù gọi `nu` trước `ca`.
7. `DateTimeFormatter.withLocale` không tự áp dụng hai thay đổi chronology/decimal style của `localizedBy`; `localizedBy` đưa năm ISO 2024 sang năm Phật lịch 2567 và in chữ số Thái.
8. `Chronology.ofLocale` với một Locale **chỉ có `nu`** trả ISO chronology, chứng minh `nu` không tự chọn `ca`.

**Giới hạn tái lập:** ký hiệu số, mẫu ngày, dấu phân tách và một số loại lịch còn phụ thuộc locale provider/CLDR và cách cấu hình runtime. Phần stdout nêu trên là kết quả thực đã kiểm chứng trong JDK với dữ liệu tương ứng; nếu môi trường dùng provider hoặc runtime image tối giản không có dữ liệu locale, có thể xuất hiện khác biệt. Phần **type/tag** nên được dùng để kiểm thử việc tạo Locale; phần **format** nên kiểm thử trên môi trường mục tiêu.

## 10. Liên hệ Java 10 với `cu`, `fw`, `rg` và `tz`

Để hiểu chính xác vị trí của `ca` và `nu` trong Java 10, cần đặt chúng bên cạnh các extension bổ sung ở phiên bản đó:

| Khóa | Đã hỗ trợ trong JDK trước Java 10? | JDK 10 bổ sung? | Vai trò chính |
| --- | --- | --- | --- |
| `ca` | Có | Không | Lựa chọn calendar/chronology |
| `nu` | Có | Không | Lựa chọn numbering system |
| `cu` | — | **Có** | Loại tiền tệ, ví dụ `cu-eur`, `cu-jpy` |
| `fw` | — | **Có** | Ngày đầu tuần, ví dụ `fw-mon` |
| `rg` | — | **Có** | Override vùng áp dụng dữ liệu bản địa hóa |
| `tz` | — | **Có** | Lựa chọn timezone ở dịch vụ hỗ trợ |

**Quan hệ giữa các khóa:**

- `ca` và `nu` là hai lựa chọn **tường minh**, có thể kết hợp với các khóa mới.
- `fw` liên quan đến ngày bắt đầu tuần; nó **không phải** cách chọn hệ lịch. Có thể dùng `ca` và `fw` đồng thời để diễn đạt hai ý định.
- `cu` chọn **đồng tiền** được định dạng ở dịch vụ hỗ trợ; `nu` chọn **hệ chữ số**. Ví dụ mong muốn Euro không đồng nghĩa phải đổi chữ số Latin sang Thái.
- `rg` có thể ảnh hưởng mặc định bản địa hóa theo vùng; khi **`nu` được khai báo tường minh**, dịch vụ `NumberFormat` ưu tiên chữ số từ `nu` so với lựa chọn số ngầm định theo `rg`. Với `DateTimeFormatter.localizedBy`, tài liệu cũng nêu `ca`/`nu` tường minh ưu tiên so với các mặc định tương ứng rút ra từ `rg`.
- `tz` điều khiển múi giờ ở các API hỗ trợ; không thay thế `ca` hoặc `nu`.

Ví dụ cấu trúc kết hợp nhiều khóa:

~~~text
en-US-u-ca-japanese-nu-latn
th-TH-u-ca-buddhist-nu-thai
en-US-u-ca-gregory-fw-mon-nu-latn
~~~

Không phải mọi service đều tiêu thụ tất cả các khóa có trong cùng tag. Một `Locale` chỉ **lưu thông tin yêu cầu**; tác động thực tế là việc của từng API và locale provider.

### Tại sao Java 10 đặc biệt đáng nhớ ở phần này?

Một thay đổi dễ thấy ở JDK 10 là phương thức **`DateTimeFormatter.localizedBy(Locale)`**, cho phép formatter đọc và sử dụng cùng lúc các lựa chọn có trong Unicode Locale, bao gồm **`ca` và `nu`**. Nhờ vậy một tag có thể vừa chọn chronology vừa chọn cách hiển thị chữ số mà không bắt buộc ứng dụng phải cấu hình từng thuộc tính bằng các lời gọi `withChronology`/`withDecimalStyle` riêng lẻ.

Tuy nhiên, nếu hợp đồng nghiệp vụ cần cài đặt cụ thể, việc chỉ định chronology/decimal style/zone tường minh vẫn hoàn toàn hợp lệ và nhiều khi rõ ràng hơn.

## 11. Chú ý sự khác nhau giữa `Calendar` và `java.time`

`Calendar` của `java.util` vẫn được hỗ trợ; không cần gọi nó là API đã bị loại bỏ. Tuy nhiên, với code ngày giờ mới, các kiểu của `java.time` thường có mô hình bất biến rõ ràng hơn.

**Cùng là `th-TH`, nhưng khi không chỉ định `ca`, các API có thể dùng mặc định khác nhau.** Theo tài liệu `Chronology.ofLocale`, khi không có khóa `ca`, kết quả thường là **ISO**, dù một `Calendar.getInstance` dùng quy ước văn hóa/compatibility và có thể chọn hệ lịch khác cho vùng Thái.

Để tránh suy đoán:

~~~java
Locale explicit = Locale.forLanguageTag("th-TH-u-ca-buddhist");
Chronology chronology = Chronology.ofLocale(explicit);
// ThaiBuddhist khi được hỗ trợ
~~~

Trong hệ thống lưu ngày tháng, ưu tiên giữ giá trị ngày theo **chuẩn nội bộ rõ ràng** (thường ISO `LocalDate` hoặc thời điểm `Instant`), rồi áp dụng lịch/numbering tại tầng trình bày. Đừng chuyển đổi dữ liệu lõi sang chuỗi số theo locale và sau đó giả định mọi consumer đều hiểu.

Một ví dụ sai lầm:

~~~java
// Dữ liệu nghiệp vụ vẫn là số 2024:
int year = 2024;

// Một formatter bản địa hóa có thể hiển thị năm là 2567,
// nhưng không có nghĩa biến year trên tự đổi thành 2567.
~~~

Việc hiển thị số năm theo một hệ lịch có thể đi kèm era, ngày tháng và quy tắc chuyển đổi; không tự cộng 543 cho mọi đối tượng ngày hoặc mọi hệ lịch.

## 12. Lưu ý về hỗ trợ provider và tính hợp lệ của Locale

Các keyword BCP 47 là một **giao thức mô tả ưu tiên**, không phải cam kết mọi runtime/formatter sẽ đáp ứng được mọi giá trị.

### 12.1. Cú pháp hợp lệ không có nghĩa type được hỗ trợ

~~~java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai"
);
~~~

Tag trên hợp cú pháp. Nhưng nếu ứng dụng cho phép nhập type tùy ý từ cấu hình hoặc request, cần xác minh nó có nằm trong tập giá trị/chronology mà hệ thống mục tiêu hỗ trợ.

`Locale.Builder` giúp kiểm tra cú pháp và có thể ném `IllformedLocaleException` với input sai dạng. Nó **không phải validator** đảm bảo mọi calendar/numbering type thực sự hoạt động ở mọi service. Đối với lựa chọn calendar, có thể kiểm tra `Calendar.getAvailableCalendarTypes()` hoặc lựa chọn chronology theo các API thích hợp.

### 12.2. Runtime image và locale provider

Với các bản dựng JDK tùy biến bằng `jlink`, dữ liệu locale có thể được cắt giảm. Locale provider cũng có thể khác nhau theo môi trường. Kết quả định dạng hiển thị trong các ví dụ cần được kiểm thử trên đúng runtime mà ứng dụng triển khai.

Ngay cả khi `getUnicodeLocaleType("nu")` trả `"thai"`, điều đó chỉ chứng minh **Locale chứa yêu cầu**, chưa chứng minh tất cả thư viện bên thứ ba hoặc tất cả formatter đều dùng đúng glyph chữ số Thái.

### 12.3. Không bỏ qua Locale của từng operation

~~~java
Locale locale = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist-nu-thai"
);

// Locale của operation phải được truyền vào dịch vụ được dùng:
NumberFormat numbers = NumberFormat.getIntegerInstance(locale);
DateTimeFormatter dates = DateTimeFormatter
        .ofPattern("yyyy-MM-dd", Locale.US)
        .localizedBy(locale);
~~~

Đặt `Locale` vào một biến **không làm thay đổi tự động** toàn bộ định dạng của ứng dụng. Các API không nhận `Locale` thường vẫn hoạt động theo hợp đồng riêng của chúng.

Nếu dùng `Locale.setDefault`, bạn thay đổi trạng thái mặc định toàn JVM và có thể ảnh hưởng các luồng/khối code khác. Không đổi default toàn cục chỉ để in một giá trị bản địa hóa; hãy truyền Locale tường minh khi phù hợp.

## 13. Các lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| “Java 10 lần đầu hỗ trợ `ca` và `nu`.” | Theo hướng dẫn Oracle, hai khóa này đã được hỗ trợ trước Java 10. | Nêu rõ Java 10 mở rộng `cu/fw/rg/tz` và thêm `DateTimeFormatter.localizedBy`. |
| Dùng `ca` để yêu cầu chữ số Thái | `ca` chọn calendar, không chọn numbering. | Dùng `nu=thai`. |
| Dùng `nu` để đổi niên đại Phật lịch | `nu` chọn glyph chữ số, không đổi chronology. | Dùng `ca=buddhist`, rồi dùng API lịch hỗ trợ. |
| Nghĩ `ca` và `nu` không thể kết hợp | Chúng là hai keyword Unicode độc lập. | Dùng tag `-u-ca-...-nu-...`. |
| Viết `ca-TH` thay vì type hợp lệ | `TH` là mã vùng, không phải calendar type. | Dùng `ca-buddhist`, `ca-japanese`, `ca-gregory` tùy nhu cầu. |
| Dùng `Locale.toString()` làm tag trao đổi | `toString` có cú pháp debug/compatibility. | Dùng `toLanguageTag()`. |
| Nghĩ `withLocale` luôn giống `localizedBy` | `localizedBy` có thể áp dụng chronology/decimal style theo keyword. | Dùng đúng API và xem formatter cuối. |
| Giả định `th-TH` luôn là Thai Buddhist trong mọi API | `Calendar` và `Chronology.ofLocale` có mặc định khác nhau. | Khai báo `ca` tường minh khi nghiệp vụ cần. |
| Kiểm tra chữ số bằng `Integer.toString` | Không phải formatter locale-sensitive. | Dùng `NumberFormat` hoặc formatter được cấu hình. |
| Nghĩ `nu=thai` làm thay đổi giá trị số | Chỉ biểu diễn/định dạng, không thay số học. | Lưu/so sánh dữ liệu lõi độc lập locale. |
| Nghĩ `Locale.Builder` bảo đảm mọi type được hỗ trợ | Builder chủ yếu kiểm tra cú pháp. | Kiểm tra runtime/service và có fallback rõ ràng. |
| Hard-code một mẫu ngày/chuỗi output cho mọi provider | CLDR/provider và runtime có thể khác. | Kiểm thử theo môi trường triển khai; kiểm tra đặc tính cần thiết. |
| Dùng `Locale.setDefault` tùy tiện | Thay trạng thái mặc định toàn JVM. | Truyền Locale theo request/operation. |
| Nhầm `ca` với timezone | Hệ lịch và múi giờ là hai lựa chọn riêng. | Chỉ định `ZoneId`/`tz` nếu cần. |

## 14. Chọn API đúng theo mục đích

| Tình huống | API nên dùng | Vai trò của `ca`/`nu` |
| --- | --- | --- |
| Lưu hoặc truyền sở thích locale của người dùng | `Locale.forLanguageTag`, `toLanguageTag`, `Locale.Builder` | Lưu cặp `ca`/`nu` trong BCP 47 |
| Muốn biết một locale chọn loại lịch nào | `getUnicodeLocaleType("ca")` | Đọc yêu cầu `ca` |
| Muốn biết locale chọn numbering nào | `getUnicodeLocaleType("nu")` | Đọc yêu cầu `nu` |
| Muốn một `Calendar` theo locale | `Calendar.getInstance(locale)` | `ca` có thể quyết định loại Calendar |
| Muốn hệ lịch theo `java.time` | `Chronology.ofLocale(locale)` | `ca` chọn chronology |
| Định dạng số theo chữ số locale | `NumberFormat.getInstance(locale)` | `nu` có thể quyết định numbering |
| Định dạng ngày với cả lịch và chữ số | `DateTimeFormatter.localizedBy(locale)` | Áp dụng `ca` và `nu` cùng lúc (Java 10+) |
| Cần chronology luôn cố định | `withChronology(...)` hoặc `ThaiBuddhistChronology` | Không phụ thuộc chỉ vào sở thích từ locale |
| Cần định dạng chữ số luôn cố định | `withDecimalStyle(...)` hoặc `DecimalFormatSymbols` | Có thể đặt tường minh với kiểm soát rõ |
| Lưu ngày giờ/số trong giao thức máy đọc | `LocalDate`, `Instant`, định dạng ISO cụ thể | Không để locale hiển thị làm đổi hợp đồng dữ liệu máy |

Nguyên tắc thiết kế: **Locale mô tả ưu tiên; formatter/chronology thực hiện ưu tiên đó nếu hợp đồng cho phép.** Khi cần định dạng máy đọc bất biến theo locale, không dùng kết quả của một localized formatter làm chuẩn lưu trữ giao thức.

## 15. Tự kiểm tra

### Bài 1 — xác định hai keyword

~~~java
Locale x = Locale.forLanguageTag(
        "ja-JP-u-ca-japanese-nu-latn"
);
~~~

Hỏi: `x.getUnicodeLocaleType("ca")` và `x.getUnicodeLocaleType("nu")` trả gì?

**Đáp án:** lần lượt là `"japanese"` và `"latn"`. Đây là lựa chọn **lịch Nhật** và **chữ số Latin**. Hai sở thích không loại trừ nhau.

### Bài 2 — chỉ có `nu`

~~~java
Locale x = Locale.forLanguageTag("th-TH-u-nu-thai");
Chronology chronology = Chronology.ofLocale(x);
~~~

Hỏi: `chronology.getId()` là gì theo hợp đồng `Chronology.ofLocale`?

**Đáp án:** `ISO`, vì Locale không có `ca`. `nu=thai` không tự chọn Buddhist chronology.

### Bài 3 — chỉ có `ca`

~~~java
Locale x = Locale.forLanguageTag("th-TH-u-ca-buddhist");
~~~

Hỏi: có thể khẳng định mọi `NumberFormat` phải dùng chữ số Thái chỉ vì `ca=buddhist` không?

**Đáp án:** **không**. `ca` là khóa calendar. Nếu ứng dụng cần số Latin hoặc Thái cụ thể, khai báo `nu` và dùng dịch vụ định dạng hỗ trợ.

### Bài 4 — `DateTimeFormatter` của Java 10

~~~java
Locale x = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist-nu-thai"
);
DateTimeFormatter fmt = DateTimeFormatter
        .ofPattern("yyyy-MM-dd", Locale.US)
        .localizedBy(x);
~~~

Hỏi: hai lựa chọn nào của `fmt` được áp dụng từ Locale?

**Đáp án:** chronology Phật giáo (`ca=buddhist`) và decimal/numbering style Thái (`nu=thai`). Formatter có thể hiển thị ngày ISO `2024-04-13` thành `๒๕๖๗-๐๔-๑๓` trên runtime có dữ liệu tương ứng.

### Bài 5 — phân biệt lịch sử phiên bản

Hỏi: Java 10 đã giới thiệu lần đầu `ca`, `nu` hay mở rộng các khóa khác?

**Đáp án:** `ca`/`nu` **đã có trước**. Java 10 bổ sung hỗ trợ `cu`, `fw`, `rg`, `tz` trong những class liên quan và cung cấp `DateTimeFormatter.localizedBy(Locale)`, giúp áp dụng các lựa chọn lịch/numbering từ Unicode locale extension dễ dàng hơn.

### Bài 6 — kiểm tra lỗi cấu hình

Một hệ thống nhận tag tùy ý từ người dùng rồi chỉ dùng `getUnicodeLocaleType("ca")` để xác nhận calendar hợp lệ. Điều này đủ chưa?

**Đáp án:** chưa. Lời gọi đó chỉ đọc **type được ghi trong Locale**, không bảo đảm type được calendar/chronology provider cụ thể hỗ trợ. Cần xác thực theo tập calendar được phép và thử cấu hình dịch vụ thật, có fallback hoặc lỗi rõ ràng.

## 16. Tóm tắt và tài liệu chính thức

- **`ca` chọn hệ lịch; `nu` chọn hệ chữ số.** Chúng là hai Unicode locale keyword độc lập, có thể đồng thời xuất hiện trong `-u-`.
- Cú pháp ví dụ: **`th-TH-u-ca-buddhist-nu-thai`**.
- `Locale.forLanguageTag`, `Locale.Builder`, `getUnicodeLocaleType`, `toLanguageTag` giúp tạo, đọc và trao đổi Locale một cách tường minh.
- `Calendar` và `Chronology` có thể đọc `ca`; `NumberFormat` và `DecimalFormatSymbols` có thể sử dụng `nu`.
- **`DateTimeFormatter.localizedBy(Locale)` từ Java 10** là API quan trọng để áp dụng đồng thời hệ lịch và kiểu chữ số của locale; **`withLocale` không tương đương**.
- `ca` và `nu` không mới ở Java 10; phiên bản này mở rộng thêm **`cu/fw/rg/tz`** trong các dịch vụ thích hợp.
- Locale mô tả ưu tiên, còn formatter/provider quyết định mức độ thực thi. Không có bảo đảm mọi type đều được hỗ trợ trên mọi runtime.
- Không trộn định dạng hiển thị với dữ liệu lõi; số học và giá trị ngày giờ không bị biến đổi chỉ vì chọn một Locale.

Tài liệu tham khảo:

- [Oracle — Internationalization Enhancements in JDK 10](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html): phân biệt `ca/nu` đã có trước và `cu/fw/rg/tz` thêm trong Java 10.
- [Java SE 17 — `Locale` và Unicode locale extensions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html)
- [Java SE 17 — `DateTimeFormatter.localizedBy(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html#localizedBy(java.util.Locale))
- [Java SE 17 — `Chronology.ofLocale(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html#ofLocale(java.util.Locale))
- [Java SE 17 — `NumberFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 17 — `Calendar.getCalendarType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Calendar.html#getCalendarType())

**Kết luận:** Trong mở rộng Locale, **`ca` là hệ lịch, `nu` là hệ chữ số**. Chúng bổ sung cho nhau và có thể phối hợp trong một BCP 47 tag. Điểm cần nhớ của Java 10 là **`DateTimeFormatter.localizedBy` và hỗ trợ các khóa Unicode bổ sung**; muốn định dạng đáng tin cậy, hãy dùng Locale tường minh, kiểm tra API tiêu thụ extension và chạy kiểm thử trên runtime mục tiêu.
