# Unicode locale extension cho lịch, hệ chữ số và quy ước khác

## 1. Vì sao chỉ có ngôn ngữ và quốc gia chưa đủ?

Một `Locale` trong Java thường được hình dung qua ngôn ngữ (`language`), chữ viết (`script`) và vùng (`region`). Tuy nhiên, hai người cùng sử dụng tiếng Thái tại Thái Lan vẫn có thể muốn **hệ lịch** hoặc **hệ chữ số** khác nhau; hai người cùng sử dụng tiếng Đức tại Đức có thể muốn **kiểu sắp xếp từ** khác nhau.

**Unicode locale extension** là cách ghi thêm các *ưu tiên về quy ước địa phương* ngay trong thẻ ngôn ngữ **BCP 47**, với ký hiệu mở đầu `-u-`. Trong Java, `java.util.Locale` lưu và cho phép truy vấn các ưu tiên này.

Ví dụ:

| Thẻ locale | Thành phần cơ sở | Unicode extension | Ý nghĩa ưu tiên |
| --- | --- | --- | --- |
| `th-TH` | Tiếng Thái, Thái Lan | Không khai báo | Dùng quy ước mặc định do API/dữ liệu locale quyết định |
| `th-TH-u-ca-buddhist` | `th-TH` | `ca=buddhist` | Yêu cầu dùng lịch Phật giáo khi API hỗ trợ |
| `th-TH-u-nu-thai` | `th-TH` | `nu=thai` | Ưu tiên chữ số Thái trong định dạng số khi API hỗ trợ |
| `th-TH-u-ca-buddhist-nu-thai` | `th-TH` | `ca=buddhist`, `nu=thai` | Kết hợp cả hai ưu tiên |
| `de-DE-u-co-phonebk` | `de-DE` | `co=phonebk` | Yêu cầu kiểu đối chiếu/sắp xếp theo danh bạ, nếu dịch vụ hỗ trợ |
| `en-US-u-hc-h23` | `en-US` | `hc=h23` | Ưu tiên chu kỳ giờ 0–23 ở nơi có hỗ trợ |

Cốt lõi: **Unicode locale extension mô tả một ưu tiên, không phải mệnh lệnh khiến mọi API tự động thực hiện ưu tiên đó**. API tạo locale có thể lưu đầy đủ `u-ca`, `u-nu`, `u-co` hoặc `u-hc`; định dạng hay sắp xếp có thật sự thay đổi hay không còn tùy API, phiên bản Java, dữ liệu locale và provider được sử dụng.

## 2. Cấu trúc `-u-` trong thẻ BCP 47

Xem thẻ sau:

~~~text
th-TH-u-ca-buddhist-nu-thai
│  │  │ │  │        │  └── thai: kiểu chữ số Thái
│  │  │ │  │        └───── nu: khóa numbering system
│  │  │ │  └────────────── buddhist: kiểu lịch Phật giáo
│  │  │ └───────────────── ca: khóa calendar
│  │  └─────────────────── u: Unicode locale extension
│  └────────────────────── TH: vùng lãnh thổ
└───────────────────────── th: ngôn ngữ
~~~

Phần `u` là một **extension singleton** của BCP 47; sau nó là các thuộc tính (*attributes*, nếu có) và những cặp **khóa–kiểu giá trị** (*keyword key–type*).

- Khóa Unicode locale keyword như `ca`, `nu`, `co`, `hc` có **hai ký tự chữ/số** theo cú pháp extension.
- Kiểu giá trị thường gồm một hay nhiều subtag, ví dụ `buddhist`, `gregory`, `latn`, `thai`, `phonebk`. Giá trị có được dịch vụ hiểu hay không là vấn đề khác với việc cú pháp hợp lệ.
- Nhiều keyword có thể cùng tồn tại trong một extension `-u-`. Khi xuất thẻ từ `Locale.toLanguageTag()`, Java dùng dạng chuẩn hóa, bao gồm thứ tự khóa.
- Các vùng `language`, `script`, `region`, `variant` nằm ở phần thẻ chính; keyword nằm trong extension. **`ca` không thay thế ngôn ngữ; `nu` không thay thế vùng.**

Ví dụ `en-US-u-ca-buddhist-nu-thai` vẫn có `getLanguage()` bằng `en` và `getCountry()` bằng `US`. Lịch, hệ chữ số là các sở thích bổ sung, không làm locale biến thành tiếng Thái.

**Phân biệt với extension khác:** `-x-` dùng cho private-use; một thẻ có thể có extension khác ngoài `-u-`. `Locale.stripExtensions()` xóa **tất cả** extension, không chỉ một keyword Unicode. Đừng dùng phương pháp này nếu muốn loại riêng một ưu tiên mà giữ lại các ưu tiên khác.

## 3. Các keyword quan trọng và giới hạn áp dụng

| Keyword | Ý nghĩa | Ví dụ | Cần hiểu đúng |
| --- | --- | --- | --- |
| `ca` | Calendar system | `ca-buddhist`, `ca-gregory`, `ca-japanese` | Dùng để chọn hệ lịch ở API hỗ trợ; **không** xác định múi giờ |
| `nu` | Numbering system | `nu-latn`, `nu-thai`, `nu-arab` | Tác động đến dạng chữ số ở bộ định dạng hỗ trợ; **không** đổi giá trị số nguyên |
| `co` | Collation | `co-phonebk`, `co-pinyin` | Nói về so sánh/sắp xếp văn bản; mức hỗ trợ phụ thuộc bộ đối chiếu |
| `hc` | Hour cycle | `hc-h12`, `hc-h23` | Sở thích hiển thị đồng hồ 12/24 giờ, nhưng không phải mọi API thời gian đều áp dụng |
| `fw` | First day of week | `fw-mon`, `fw-sun` | Mô tả ngày bắt đầu tuần; cần kiểm tra API lịch có sử dụng hay không |
| `ms` | Measurement system | `ms-metric`, `ms-ussystem` | Mô tả quy ước đơn vị; không tự động đổi mọi giá trị đo |
| `kn` | Numeric collation | `kn-true` | Liên quan đến đối chiếu chuỗi chứa chữ số khi collator hỗ trợ |

Các keyword và kiểu giá trị thuộc hệ thống dữ liệu locale Unicode (UTS #35/CLDR). Không suy ra rằng Java SE bắt buộc hỗ trợ mọi tổ hợp chỉ vì `Locale.Builder` chấp nhận thẻ. Các giá trị điển hình ở bảng trên giúp đọc yêu cầu cấu hình, không phải danh mục đầy đủ.

### Ba lớp cần phân biệt

1. **Định danh và lưu trữ:** `Locale` giữ keyword có trong tag và cho phép đọc lại.
2. **Dữ liệu và provider:** JDK hoặc thư viện cần có quy tắc tương ứng cho calendar, number symbols, collation…
3. **API sử dụng:** đoạn mã phải đi qua API hiểu keyword đó. Một `String`, `LocalDate` hay phép so sánh `String.compareTo` thông thường không tự thay đổi chỉ vì bạn tạo một `Locale` có extension.

Ví dụ, `nu-thai` ảnh hưởng đến *cách trình bày* số khi dùng bộ định dạng có hỗ trợ; phép cộng `123 + 7` vẫn bằng `130`, kiểu `int` không thay đổi và `Integer.toString(123)` vẫn dùng các ký tự `1`, `2`, `3` ASCII thông thường.

## 4. Tạo và đọc Unicode locale extension bằng Java 17+

Java có sẵn API để thao tác với Unicode extension:

- `Locale.forLanguageTag(String)`: đọc một thẻ BCP 47 từ chuỗi.
- `Locale.Builder.setLanguageTag(String)`: dựng locale từ thẻ, kiểm tra lỗi cú pháp chặt hơn.
- `Locale.Builder.setUnicodeLocaleKeyword(String key, String type)`: gán hoặc thay một keyword Unicode trong locale đang xây dựng.
- `Locale.getUnicodeLocaleKeys()`: tập các khóa Unicode keyword.
- `Locale.getUnicodeLocaleType(String key)`: đọc kiểu giá trị của một khóa; trả `null` nếu khóa không hiện diện.
- `Locale.getExtension('u')`: lấy toàn bộ giá trị extension `u` dưới dạng chuỗi, bỏ phần `u-` ở đầu.
- `Locale.toLanguageTag()`: xuất thẻ đã chuẩn hóa.
- `Locale.stripExtensions()`: tạo locale mới không chứa các extension.

### Ví dụ 1 — tạo, truy vấn và so sánh locale

Lưu đoạn mã sau vào `UnicodeLocaleDemo.java`:

~~~java
import java.util.Locale;

public class UnicodeLocaleDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("th-TH");

        Locale preferred = new Locale.Builder()
                .setLocale(base)
                .setUnicodeLocaleKeyword("ca", "buddhist")
                .setUnicodeLocaleKeyword("nu", "thai")
                .build();

        System.out.println("Tag: " + preferred.toLanguageTag());
        System.out.println("Language: " + preferred.getLanguage());
        System.out.println("Region: " + preferred.getCountry());
        System.out.println("Unicode u: " + preferred.getExtension('u'));
        System.out.println("Calendar: " + preferred.getUnicodeLocaleType("ca"));
        System.out.println("Numbers: " + preferred.getUnicodeLocaleType("nu"));
        System.out.println("Collation absent: "
                + (preferred.getUnicodeLocaleType("co") == null));
        System.out.println("Base without extensions: "
                + preferred.stripExtensions().toLanguageTag());
        System.out.println("Same as base: " + preferred.equals(base));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 UnicodeLocaleDemo.java
java UnicodeLocaleDemo
~~~

Kết quả:

~~~text
Tag: th-TH-u-ca-buddhist-nu-thai
Language: th
Region: TH
Unicode u: ca-buddhist-nu-thai
Calendar: buddhist
Numbers: thai
Collation absent: true
Base without extensions: th-TH
Same as base: false
~~~

Giải thích:

1. `base` và `preferred` cùng dùng ngôn ngữ `th`, vùng `TH`.
2. `setUnicodeLocaleKeyword` chỉ thêm hai sở thích; `getUnicodeLocaleType` đọc lại chính xác các giá trị đó.
3. Java không tự điền khóa không được khai báo: `getUnicodeLocaleType("co")` trả `null`.
4. `stripExtensions()` loại hai sở thích, trả về thẻ `th-TH`.
5. `Locale.equals` xét cả extension nên hai locale ở đây khác nhau. Nếu ứng dụng tạo cache theo locale, cần quyết định rõ có dùng cả extension trong khóa hay không; việc chỉ lưu `language + country` sẽ làm mất ưu tiên.

### Các thao tác hữu ích khác

~~~java
Locale input = Locale.forLanguageTag("de-DE-u-co-phonebk");
System.out.println(input.getUnicodeLocaleType("co")); // phonebk

Locale changed = new Locale.Builder()
        .setLocale(input)
        .setUnicodeLocaleKeyword("co", null) // Xóa riêng keyword co
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
System.out.println(changed.toLanguageTag()); // de-DE-u-nu-latn
~~~

Đây là một **mảnh mã minh họa đặt trong phương thức Java**, không phải chương trình độc lập. Cách xóa bằng `setUnicodeLocaleKeyword("co", null)` giữ lại thành phần nền và các extension/keyword khác nếu có. Giá trị type là chuỗi rỗng có ý nghĩa khác với `null` đối với một số keyword Unicode dạng boolean.

Khi nhận locale từ hệ thống ngoài, hãy kiểm tra cú pháp và danh mục keyword sản phẩm cho phép. `Locale.forLanguageTag` có thể chấp nhận phần đầu hợp lệ rồi bỏ qua phần không hợp lệ tiếp theo; `Locale.Builder.setLanguageTag` có thể ném `IllformedLocaleException` khi thẻ sai cú pháp. **“Thẻ parse được” không đồng nghĩa “keyword được API nghiệp vụ hỗ trợ”.**

## 5. Ứng dụng của `ca` và `nu` trong Java

### 5.1. Calendar: cùng vùng, khác hệ lịch

Trong API `java.util.Calendar`, hệ lịch có thể được chọn từ `ca` khi cách cài đặt/provider hỗ trợ. Ví dụ `th-TH-u-ca-buddhist` chỉ định Buddhist Calendar; `th-TH-u-ca-gregory` chỉ định Gregorian Calendar.

Lưu thành `CalendarKeywordDemo.java`:

~~~java
import java.util.Calendar;
import java.util.Locale;

public class CalendarKeywordDemo {
    public static void main(String[] args) {
        Locale buddhist = Locale.forLanguageTag("th-TH-u-ca-buddhist");
        Locale gregory = Locale.forLanguageTag("th-TH-u-ca-gregory");

        Calendar first = Calendar.getInstance(buddhist);
        Calendar second = Calendar.getInstance(gregory);

        System.out.println(first.getCalendarType());
        System.out.println(second.getCalendarType());
        System.out.println(first.getTimeZone().getID().equals(
                second.getTimeZone().getID()));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CalendarKeywordDemo.java
java CalendarKeywordDemo
~~~

Trong JDK có hỗ trợ hai kiểu lịch này, hai dòng đầu là:

~~~text
buddhist
gregory
~~~

Dòng thứ ba thường là `true` nếu JVM không thay đổi múi giờ mặc định giữa hai lần gọi; ví dụ cố ý **không cố định** múi giờ hay ngày hiện tại. Mục tiêu là thấy `ca` chọn hệ lịch, còn timezone là một quyết định riêng. Muốn kết quả tất định về thời điểm, ngày giờ và số năm, hãy chỉ định timezone và ngày tham chiếu rõ ràng trước khi định dạng.

**Với `java.time`:** `LocalDate` là ngày theo hệ ISO; việc giữ locale có `u-ca` không làm một `LocalDate` đang tồn tại tự biến thành đối tượng lịch Phật giáo. Khi thực sự cần lịch khác ISO, hãy sử dụng chronology có chủ đích (chẳng hạn `ThaiBuddhistChronology.INSTANCE` và `DateTimeFormatter.withChronology(...)`) và kiểm thử kết quả định dạng. Không coi việc chỉ gọi `withLocale(locale)` là bảo đảm đổi chronology trong mọi hoàn cảnh.

### 5.2. NumberFormat: cùng giá trị số, cách viết chữ số khác nhau

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class NumberingKeywordDemo {
    public static void main(String[] args) {
        int value = 12345;

        Locale latinDigits = Locale.forLanguageTag("th-TH-u-nu-latn");
        Locale thaiDigits = Locale.forLanguageTag("th-TH-u-nu-thai");

        NumberFormat western = NumberFormat.getIntegerInstance(latinDigits);
        NumberFormat thai = NumberFormat.getIntegerInstance(thaiDigits);

        System.out.println(western.format(value));
        System.out.println(thai.format(value));
        System.out.println(value);
    }
}
~~~

Lưu thành `NumberingKeywordDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 NumberingKeywordDemo.java
java NumberingKeywordDemo
~~~

Với provider CLDR hỗ trợ `nu-thai`, kết quả thường là:

~~~text
12,345
๑๒,๓๔๕
12345
~~~

Lỗi thường gặp là xem các dòng trên như kết quả cố định cho **mọi** JVM. Kiểu chữ số, dấu phân nhóm, dữ liệu locale và các thiết lập provider có thể ảnh hưởng đầu ra. Hãy kiểm thử trên JDK và cấu hình mà sản phẩm triển khai. Dòng thứ ba vẫn in `12345` do nó in trực tiếp `int`, không thông qua `NumberFormat`.

Ngoài ra, chọn chữ số để **hiển thị** không đồng nghĩa mọi API **phân tích chuỗi** đều hỗ trợ mọi hệ chữ số. Nếu cần đọc dữ liệu người dùng nhập, hãy kiểm tra `NumberFormat.parse` và chính sách xử lý lỗi đối với input dự kiến.

### 5.3. Các quy ước khác: collation, giờ, tuần, đo lường

Ví dụ `de-DE-u-co-phonebk` diễn tả yêu cầu đối chiếu theo danh bạ, `en-US-u-hc-h23` diễn tả mong muốn dạng giờ 24 giờ, `en-US-u-fw-mon` gợi ý tuần bắt đầu thứ Hai. Có thể đọc chúng bằng `getUnicodeLocaleType`, nhưng **mỗi dịch vụ có mức hỗ trợ khác nhau**:

- Với sắp xếp, sử dụng bộ đối chiếu có hiểu locale (`Collator` hoặc thư viện chuyên dụng như ICU tùy yêu cầu) và kiểm thử bộ dữ liệu thực tế. `String.compareTo` so sánh theo giá trị UTF-16, không phải quy tắc địa phương.
- Với định dạng giờ, cấu hình mẫu hiển thị/formatter minh bạch khi yêu cầu 12/24 giờ là bắt buộc. Đừng giả định chỉ thêm `hc-h23` chắc chắn thay đổi mọi `DateTimeFormatter`.
- Với ngày bắt đầu tuần hoặc hệ đo lường, kiểm tra tài liệu API cụ thể hoặc cài đặt quy tắc nghiệp vụ thay vì trông đợi `fw`/`ms` tự làm thay đổi mọi phép tính, màn hình hoặc thư viện.

## 6. Thiết kế luồng xử lý locale đúng cách

Giả sử người dùng chọn tiếng Thái, lịch Phật giáo và chữ số Thái. Một luồng triển khai đáng tin là:

~~~text
Lựa chọn người dùng
    |
    v
th-TH-u-ca-buddhist-nu-thai
    |
    +--> Lưu toàn bộ language tag trong hồ sơ/cấu hình
    |
    +--> Locale.forLanguageTag(...) ở phía Java
    |
    +--> Calendar / NumberFormat / formatter hỗ trợ tương ứng
    |
    +--> Kiểm thử giá trị được hiển thị và fallback
~~~

**Nguyên tắc áp dụng:**

1. **Giữ nguyên thẻ đầy đủ:** lưu `Locale.toLanguageTag()` (hoặc thẻ đầu vào đã kiểm tra và chuẩn hóa) khi yêu cầu cần được duy trì giữa các request, session hoặc dịch vụ. Không chỉ lưu `th-TH` nếu `ca`/`nu` là lựa chọn chủ đích.
2. **Phân định sở thích với tính năng:** API lưu được `u-ca`/`u-nu` chưa chứng minh được bộ định dạng thực sự hỗ trợ các kiểu giá trị đó. Chọn API phù hợp và xử lý giá trị không hỗ trợ.
3. **Fallback có chính sách:** khi hệ lịch hoặc chữ số không khả dụng, xác định rõ dùng mặc định nào, có thông báo người dùng hay không và cách giữ nhất quán giữa các màn hình.
4. **Không để metadata thay đổi dữ liệu nguồn:** số tiền, timestamp và thời điểm lưu trữ không nên phụ thuộc ký hiệu hiển thị. Quy tắc lịch và số dùng trong giao diện phải tách khỏi biểu diễn dữ liệu lâu dài.
5. **Tạo khóa cache và so sánh đủ thành phần:** hai locale cùng `language` và `region` vẫn có thể khác `u-nu` hoặc `u-ca`. Đối với kết quả định dạng có phụ thuộc các keyword đó, cache chỉ dựa trên `language/region` có thể trả nhầm kết quả.
6. **Lưu tâm timezone:** `ca` là hệ lịch, **không** phải `ZoneId`. Khi đưa ra ngày giờ thực, hãy chọn timezone riêng, đặc biệt nếu có giao tiếp giữa máy chủ và người dùng ở nhiều vùng.
7. **Đảm bảo tương thích thư viện:** chạy test trên JDK/provider thực tế. Các thư viện bên ngoài đôi khi đọc các extension khác hoặc bỏ qua chúng; truyền `Locale` vào hàm không tự động xác nhận khả năng hỗ trợ.
8. **Kiểm tra cả parsing và formatting:** cần xử lý dữ liệu nhập, biểu mẫu, CSV, API và các ký tự khác nhau mà không vô tình ép hiển thị thành định dạng lưu trữ.

### Kiểm tra có mục tiêu

| Tình huống kiểm thử | Điều cần xác minh |
| --- | --- |
| `th-TH` so với `th-TH-u-nu-thai` | Đầu ra định dạng số có khác khi provider hỗ trợ, giá trị số có giữ nguyên |
| `th-TH-u-ca-buddhist` so với `th-TH-u-ca-gregory` | `Calendar.getCalendarType()` có đúng với lựa chọn đã chỉ định |
| Keyword hợp lệ nhưng provider không hỗ trợ | Ứng dụng xử lý fallback/cảnh báo rõ ràng |
| Tag không có keyword `nu` | `getUnicodeLocaleType("nu")` trả `null`; ứng dụng dùng chính sách mặc định |
| Thẻ có hai keyword | Đọc lại đủ `ca` và `nu`, không mất lựa chọn khi serialize |
| Người dùng đổi lựa chọn | Cache, hồ sơ và giao diện được cập nhật đúng, không trộn kết quả của locale cũ |

## 7. Sai lầm phổ biến và cách sửa

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`th-TH` luôn đồng nghĩa lịch Phật giáo.” | Locale nền không ghi rõ keyword; hành vi mặc định tùy API và dữ liệu/provider. Muốn chỉ định rõ, dùng `ca-buddhist`. |
| “Có `nu-thai` thì `int` chứa chữ số Thái.” | `int` vẫn là giá trị số; bộ định dạng chọn ký tự để biểu diễn. |
| “`getUnicodeLocaleType("ca")` trả `buddhist` thì mọi API đều dùng lịch Phật giáo.” | Đây chỉ xác nhận metadata. Phải kiểm chứng từng API, bao gồm `java.time` và các thư viện ngoài. |
| “`ca` là country/region.” | `ca` là Unicode keyword về **calendar**; `getCountry()` vẫn phản ánh vùng trong phần chính của locale. |
| “Mọi extension đều là `-u-`.” | BCP 47 có các extension khác và `-x-` private-use. |
| “Xóa bằng `stripExtensions()` chỉ xóa `ca`.” | Phương thức xóa **tất cả** extension. Muốn xóa một Unicode keyword, dùng `Locale.Builder.setUnicodeLocaleKeyword(key, null)`. |
| “`ResourceBundle` mặc định sẽ tự chọn bản dịch theo `u-nu`/`u-ca`.” | Quy tắc tìm bundle thông thường dựa chủ yếu trên language/script/region/variant; không thiết kế tên file bản dịch dựa vào extension nếu chưa triển khai cơ chế chọn bundle riêng. |
| “Chỉ cần kiểm thử `Locale.toLanguageTag()`.” | Cần thêm test thật trên Calendar/NumberFormat/collator/formatter và luồng lưu trữ, cache, fallback. |

## 8. Bài tập tự kiểm tra

1. Tạo `Locale` từ `en-US-u-ca-japanese-nu-latn`. `getLanguage()`, `getCountry()`, `getUnicodeLocaleType("ca")` và `getUnicodeLocaleType("nu")` lần lượt trả về gì? Vì sao phần ngôn ngữ vẫn là `en`?
2. Bắt đầu với `th-TH-u-ca-buddhist-nu-thai` rồi dùng `Locale.Builder` xóa riêng keyword `ca`. Viết và kiểm tra thẻ còn lại; bảo đảm `nu-thai` chưa bị mất.
3. Hai request có `th-TH-u-nu-latn` và `th-TH-u-nu-thai` cùng truy vấn cache định dạng số. Nếu khóa cache chỉ là `th-TH`, tình huống sai nào có thể xảy ra?
4. So sánh `Calendar.getCalendarType()` cho hai tag chỉ khác `ca`, sau đó định dạng cùng một số bằng hai tag chỉ khác `nu`. Ghi nhận kết quả và thông tin JDK/provider của bạn.
5. Giải thích vì sao `hc-h23` hoặc `co-phonebk` được lưu trong `Locale` nhưng không nên coi việc toàn hệ thống tuân thủ chúng là điều hiển nhiên.

**Ghi nhớ:** `-u-` mở rộng một language tag BCP 47 bằng các sở thích địa phương hóa như `ca` (hệ lịch), `nu` (hệ chữ số) và `co` (quy tắc đối chiếu). Trong Java, `Locale` **lưu và truy vấn** các keyword này; **API xử lý cụ thể** mới quyết định chúng có được áp dụng hay không. Muốn đúng nghiệp vụ, hãy lưu đủ thẻ, chọn API phù hợp, kiểm thử trên provider thật và xây dựng fallback rõ ràng.