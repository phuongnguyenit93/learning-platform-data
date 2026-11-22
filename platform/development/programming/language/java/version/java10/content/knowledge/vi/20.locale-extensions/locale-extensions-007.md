# Phân biệt ngôn ngữ hiển thị với vùng quy ước trong `Locale` (Java 10+)

*Ngữ cảnh: Java 10 — Mở rộng Locale. Bài học giải thích cách Java phân biệt **ngôn ngữ để hiển thị văn bản** với **vùng văn hóa/địa lý áp dụng quy ước định dạng**, cách dùng hai loại default locale `DISPLAY` và `FORMAT`, và những Unicode locale extension được Java 10 hỗ trợ thêm. Các API và khuyến nghị dưới đây vẫn phù hợp với Java 17+ và các JDK hiện hành.*

## 1. Vấn đề thực tế

Một ứng dụng hiển thị cho người dùng bằng **tiếng Việt**, nhưng người ấy muốn **định dạng số kiểu Đức** và làm việc với **tiền tệ USD**. Cần biểu diễn các lựa chọn này ra sao?

Đừng mặc định rằng một chuỗi như `"vi-VN"` sẽ giải quyết mọi nhu cầu: 

- **Ngôn ngữ của giao diện**: thông báo “Lưu thành công”, tên quốc gia, tên ngôn ngữ, tiêu đề và các bản dịch khác.
- **Vùng quy ước**: dấu phân cách hàng nghìn/thập phân, dạng ngày tháng, quy tắc tuần, một số lựa chọn tiền tệ mặc định.
- **Đơn vị tiền tệ của giao dịch**: phải xuất phát từ dữ liệu nghiệp vụ, không đơn thuần suy từ quốc gia trên `Locale`.
- **Múi giờ**: lựa chọn riêng như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`, không được suy rằng `Locale` luôn xác định chính xác múi giờ.
- **Hệ chữ số/lịch hoặc vùng ghi đè**: có thể được thể hiện bởi các Unicode locale extensions trong language tag.

Java có những API giúp **tách biệt** các lớp thông tin ấy. Có hai nguyên tắc quan trọng:

1. `Locale.getLanguage()`, `Locale.getCountry()`, `getDisplayLanguage(...)` và `getDisplayCountry(...)` **không trả cùng loại thông tin**.
2. Các hoạt động cần tên hiển thị có thể dùng default `Locale.Category.DISPLAY`, còn những factory định dạng số/ngày thường dùng default `Locale.Category.FORMAT` hoặc một `Locale` được truyền tường minh.

Ví dụ:

~~~java
Locale preferredLabels = Locale.forLanguageTag("vi-VN");
Locale numberConventions = Locale.GERMANY;

String countryNameForUi = Locale.US.getDisplayCountry(preferredLabels);
String amountForUi =
        NumberFormat.getNumberInstance(numberConventions).format(12345.67);
~~~

Hai dòng tạo dữ liệu **cho hai mục đích khác nhau**: `countryNameForUi` biểu thị tên gọi vùng US theo ngôn ngữ hiển thị tiếng Việt; `amountForUi` biểu thị số theo quy ước số Đức (trên JDK thử nghiệm là `12.345,67`). Đoạn này giả định có import `Locale` và `NumberFormat`, nằm trong một phương thức.

## 2. `Locale` chứa những gì?

`java.util.Locale` mô tả tập hợp thông tin về **language**, **script**, **country/region**, **variant** và những extension tùy chọn. Nó thực hiện quy tắc language tag theo BCP 47 và các Unicode locale extensions tương ứng.

Ví dụ:

| Language tag | Language | Region | Ý nghĩa cơ bản |
| --- | --- | --- | --- |
| `en-US` | `en` | `US` | Tiếng Anh với ngữ cảnh vùng Hoa Kỳ |
| `en-GB` | `en` | `GB` | Tiếng Anh với ngữ cảnh vùng Anh |
| `en-DE` | `en` | `DE` | Tiếng Anh với ngữ cảnh vùng Đức |
| `de-DE` | `de` | `DE` | Tiếng Đức với ngữ cảnh vùng Đức |
| `vi-VN` | `vi` | `VN` | Tiếng Việt với ngữ cảnh vùng Việt Nam |
| `fr-CA` | `fr` | `CA` | Tiếng Pháp với ngữ cảnh vùng Canada |
| `zh-Hant-TW` | `zh` | `TW` | Tiếng Trung, script phồn thể, vùng Đài Loan |

Tạo locale bằng API hiện hành, dùng được trên Java 17:

~~~java
Locale us = Locale.forLanguageTag("en-US");
Locale englishInGermany = Locale.forLanguageTag("en-DE");
Locale vietnamese = Locale.forLanguageTag("vi-VN");

System.out.println(us.getLanguage());          // en
System.out.println(us.getCountry());           // US
System.out.println(englishInGermany.getLanguage()); // en
System.out.println(englishInGermany.getCountry());  // DE
~~~

Ở `en-DE`, phần `en` và `DE` là hai thành phần riêng. Từ ngôn ngữ `en` không suy ra quốc gia phải là `US` hoặc `GB`; từ vùng `DE` cũng không suy ra mọi văn bản phải dùng tiếng Đức.

### 2.1. Mã ngôn ngữ khác với tên ngôn ngữ hiển thị

~~~java
Locale german = Locale.GERMAN;
String code = german.getLanguage(); // "de"
String inEnglish = german.getDisplayLanguage(Locale.ENGLISH);
String inVietnamese = german.getDisplayLanguage(
        Locale.forLanguageTag("vi-VN"));
~~~

- `getLanguage()` là **mã** ngôn ngữ, thích hợp lưu trong cấu hình, dữ liệu hoặc language tag.
- `getDisplayLanguage(displayLocale)` là **nhãn đã bản địa hóa**, thích hợp cho menu chọn ngôn ngữ. Nhãn đó được hiển thị theo `displayLocale`.
- Độ chính xác/diễn đạt của tên hiển thị phụ thuộc dữ liệu locale mà JDK cung cấp; không nên hardcode giá trị một ngôn ngữ dịch trong unit test portable.

Không dùng `getDisplayLanguage()` để lấy mã `"de"`; không dùng `getLanguage()` để trực tiếp hiện chữ “German” hay “Tiếng Đức” cho người dùng.

### 2.2. Mã quốc gia khác với tên quốc gia hiển thị

~~~java
Locale us = Locale.US;

String regionCode = us.getCountry();             // "US"
String nameEnglish = us.getDisplayCountry(Locale.ENGLISH);
String nameVietnamese = us.getDisplayCountry(
        Locale.forLanguageTag("vi-VN"));
~~~

Cả `nameEnglish` và `nameVietnamese` đều nói về **cùng vùng US**. Khác biệt nằm ở **ngôn ngữ dùng để gọi tên vùng ấy**, không phải vùng đang được thay đổi.

Đừng dùng chuỗi tên quốc gia đã bản địa hóa để làm khóa dữ liệu. Sử dụng mã vùng như `US`, `DE`, `VN` theo quy ước phù hợp; tên hiển thị chỉ để phục vụ UI. Nếu dữ liệu thực tế đòi mã quốc gia ISO 3166 hoặc mã vùng M.49, hãy xác định hợp đồng trước.

### 2.3. Không nhầm `Locale` với vị trí địa lý thật

`getCountry() == "VN"` chỉ nói **locale được đặt vùng VN**. Nó không chứng minh thiết bị đang ở Việt Nam, không chứng minh người dùng có quốc tịch Việt Nam và không chứng minh họ dùng VND. Ngôn ngữ giao diện, định dạng số, múi giờ, địa chỉ giao hàng, quốc tịch và tiền tệ giao dịch là các loại dữ liệu khác nhau.

## 3. Hai default locale trong Java: `DISPLAY` và `FORMAT`

Java cho phép duy trì các giá trị mặc định theo **`Locale.Category`**:

~~~java
Locale displayDefault = Locale.getDefault(Locale.Category.DISPLAY);
Locale formatDefault = Locale.getDefault(Locale.Category.FORMAT);
~~~

### 3.1. `Locale.Category.DISPLAY`

Dùng cho các thao tác lấy **tên hiển thị được địa phương hóa**, ví dụ:

~~~java
Locale.US.getDisplayCountry()
Locale.GERMANY.getDisplayLanguage()
Locale.getDefault(Locale.Category.DISPLAY)
~~~

Trong các lời gọi `getDisplayXXX()` **không có tham số locale**, implementation dùng default DISPLAY. Vì vậy:

~~~java
Locale.US.getDisplayCountry();
~~~

tương ứng về ý nghĩa với:

~~~java
Locale.US.getDisplayCountry(
    Locale.getDefault(Locale.Category.DISPLAY));
~~~

Nếu ứng dụng cần tên quốc gia bằng một ngôn ngữ **cụ thể cho từng người dùng**, cách chắc chắn hơn là truyền `displayLocale` tường minh:

~~~java
Locale.US.getDisplayCountry(Locale.forLanguageTag("vi-VN"));
~~~

### 3.2. `Locale.Category.FORMAT`

Được dùng làm default cho nhiều API định dạng số/ngày khi người gọi không truyền locale:

~~~java
NumberFormat.getNumberInstance();
NumberFormat.getCurrencyInstance();
Locale.getDefault(Locale.Category.FORMAT);
~~~

Ví dụ:

~~~java
NumberFormat.getNumberInstance().format(12345.67);
~~~

sẽ dùng quy ước phù hợp với default FORMAT của JVM trong môi trường đó. Về nguyên tắc nó tương ứng với:

~~~java
NumberFormat.getNumberInstance(
    Locale.getDefault(Locale.Category.FORMAT))
    .format(12345.67);
~~~

Vì vậy, **default DISPLAY và default FORMAT có thể khác nhau**. Một máy hoặc tiến trình có thể hiển thị tên quốc gia bằng tiếng Việt, trong khi dùng dấu thập phân và phân nhóm theo quy ước Đức.

### 3.3. Không suy ra `Locale.getDefault()` luôn bằng cả hai category

~~~java
Locale generic = Locale.getDefault();
Locale display = Locale.getDefault(Locale.Category.DISPLAY);
Locale format = Locale.getDefault(Locale.Category.FORMAT);
~~~

Ba kết quả có thể cùng hoặc khác nhau, tùy cấu hình JVM và các thao tác thay đổi default. Không dùng `Locale.getDefault()` thay cho `Locale.getDefault(DISPLAY/FORMAT)` khi API yêu cầu phân biệt. Càng không dùng “locale của server” làm thay cho lựa chọn người dùng trong hệ thống nhiều tài khoản.

## 4. Cấu hình thử hai default category đúng cách

Chương trình Java có API:

~~~java
Locale.setDefault(Locale.Category.DISPLAY, displayLocale);
Locale.setDefault(Locale.Category.FORMAT, formatLocale);
~~~

Ví dụ trong một chương trình thử nghiệm **một tiến trình độc lập**:

~~~java
Locale previousDisplay =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale previousFormat =
        Locale.getDefault(Locale.Category.FORMAT);

try {
    Locale.setDefault(Locale.Category.DISPLAY,
            Locale.forLanguageTag("vi-VN"));
    Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

    String countryName = Locale.US.getDisplayCountry();
    String formatted =
            NumberFormat.getNumberInstance().format(12345.67);
} finally {
    Locale.setDefault(Locale.Category.DISPLAY, previousDisplay);
    Locale.setDefault(Locale.Category.FORMAT, previousFormat);
}
~~~

Đoạn code này giả định import `Locale`, `NumberFormat` và nằm trong một method. Các giá trị default cần được lưu và phục hồi để test không làm bẩn môi trường sau khi chạy.

**Cảnh báo quan trọng:** `setDefault` thay đổi cấu hình **cấp JVM**, không phải riêng một user hay một request. Trong web server nhiều luồng, đổi global default giữa hai request có thể ảnh hưởng những người dùng khác, tạo race và gây lỗi khó tái lập. Không sử dụng `Locale.setDefault(...)` để thay ngôn ngữ/định dạng cho từng request.

Trong ứng dụng nhiều người dùng, hãy giữ các `Locale` như dữ liệu của user/request và truyền chúng tường minh:

~~~java
String label = region.getDisplayCountry(userDisplayLocale);
String number = NumberFormat.getNumberInstance(userFormatLocale)
        .format(amount);
~~~

Cách đó tránh phụ thuộc vào global state. Những formatter/format object mutable như `NumberFormat` cũng không nên dùng chung bất cẩn giữa threads.

## 5. Language quyết định ngôn ngữ nhãn, region góp phần quyết định quy ước

`Locale` có cả language và region, và **các locale-sensitive service xét tổ hợp ấy**, cùng những extension nếu có. Vì thế không thể phát biểu đơn giản “format number chỉ xem country, bỏ language”. Cách thiết kế đúng:

- Xác định ngôn ngữ của UI bằng **display locale** và resource bản dịch.
- Xác định **format locale** của số/ngày theo sở thích vùng quy ước của người dùng, không nhất thiết trùng display locale.
- Nếu cần một định dạng cụ thể theo protocol, truyền đúng format locale hoặc dùng định dạng máy-máy được quy định, thay vì lấy default locale.
- Không suy rằng country trong locale hoàn toàn quyết định tất cả các quy tắc formatting ở mọi phiên bản JDK.

Ví dụ đã kiểm chứng trên JDK chạy thử:

~~~java
double amount = 12345.67;

NumberFormat.getNumberInstance(Locale.US).format(amount);
// "12,345.67"

NumberFormat.getNumberInstance(Locale.GERMANY).format(amount);
// "12.345,67"

NumberFormat.getNumberInstance(Locale.forLanguageTag("en-DE"))
        .format(amount);
// "12.345,67" trong JDK được thử, dù language vẫn là "en".
~~~

Điểm cần rút ra là `en-DE` **không đồng nghĩa** với `en-US` về mọi quy ước định dạng; ngôn ngữ giao diện và quy tắc vùng có thể tách.

**Lưu ý về tính portable:** cách biểu diễn cụ thể của số/ngày/tên vùng chịu ảnh hưởng dữ liệu locale và provider hiện có. Java không cam kết mọi provider/JDK phát ra chính xác cùng chuỗi hiển thị ở mọi phiên bản. Ở test quan trọng, hãy so sánh với hành vi cùng một formatter locale được truyền tường minh hoặc cô lập test theo runtime đã được chọn.

## 6. Ví dụ giao diện tiếng Việt, định dạng số Đức

Giả sử dữ liệu cấu hình của một người dùng gồm:

~~~java
record UiPreferences(
        Locale displayLocale,
        Locale formatLocale
) {
    UiPreferences {
        Objects.requireNonNull(displayLocale);
        Objects.requireNonNull(formatLocale);
    }
}
~~~

Đây là record minh họa, cần import `java.util.Locale` và `java.util.Objects`. Nó làm rõ ý định lưu hai lựa chọn độc lập.

Sử dụng:

~~~java
var prefs = new UiPreferences(
        Locale.forLanguageTag("vi-VN"),
        Locale.GERMANY);

String selectedRegionLabel =
        Locale.US.getDisplayCountry(prefs.displayLocale());

String amountLabel =
        NumberFormat.getNumberInstance(prefs.formatLocale())
                .format(12345.67);
~~~

Kết quả:

- `selectedRegionLabel` là nhãn vùng US theo **ngôn ngữ hiển thị** được chọn.
- `amountLabel` là số theo **quy ước định dạng** được chọn.
- Việc có `displayLocale=vi-VN` không có nghĩa mọi chuỗi được tự động dịch sang tiếng Việt. Muốn dịch `"Save"` thành `"Lưu"` cần quản lý bản dịch của ứng dụng, chẳng hạn `ResourceBundle`, dịch vụ i18n hoặc giải pháp framework tương ứng.

Một ứng dụng thương mại điện tử có thể có các lựa chọn riêng:

~~~text
UI language:      vi-VN
Number/date style: de-DE
Transaction money: USD (explicit business field)
Time zone:        Asia/Ho_Chi_Minh (explicit ZoneId)
~~~

Đó là một cấu hình **hợp lệ về mặt mô hình**, không phải một tổ hợp quốc gia/ngôn ngữ “sai”. Đừng cố sửa tự động mọi giá trị về cùng một mã quốc gia nếu yêu cầu sản phẩm cho phép độc lập.

## 7. Bài Java 10 liên quan trực tiếp: JEP 314 mở rộng Unicode locale extensions

Ngoài việc có `Locale.Category.DISPLAY` và `FORMAT` (hai category **đã tồn tại trước Java 10**), Java 10 triển khai **JEP 314 — Additional Unicode Language-Tag Extensions**.

Đừng gán nhầm toàn bộ class `Locale` hoặc hai category cho Java 10. Các extension có từ trước gồm:

- `ca` — loại calendar.
- `nu` — numbering system.

Java 10 tăng hỗ trợ trong các API i18n tương ứng cho bốn key:

- `cu` — **currency type**, ví dụ chọn EUR dù locale cơ sở là `en-US`.
- `fw` — **first day of week**, ví dụ tuần bắt đầu thứ Hai.
- `rg` — **region override**, dùng quy ước của vùng được chỉ định khác với region cơ sở.
- `tz` — **time zone**, được một số API thời gian/định dạng hỗ trợ.

Cấu trúc Unicode locale extension:

~~~text
language-region-u-key-type[-key-type...]

en-US-u-cu-eur
en-US-u-fw-mon
en-US-u-rg-gbzzzz
en-US-u-tz-uslax
en-US-u-nu-arab
~~~

`-u-` là singleton Unicode extension; mã key có hai ký tự, sau đó là type của key. Không phải một chuỗi tùy ý được đảm bảo tác động đến mọi API: **mỗi provider và API có tập key/type được hỗ trợ riêng**. Kiểm tra contract của API thực sự đang dùng.

### 7.1. `cu`: chọn loại tiền tệ, không đổi ngôn ngữ

~~~java
Locale base = Locale.forLanguageTag("en-US");
Locale withEuro = Locale.forLanguageTag("en-US-u-cu-eur");

System.out.println(Currency.getInstance(base).getCurrencyCode());
// USD
System.out.println(Currency.getInstance(withEuro).getCurrencyCode());
// EUR
~~~

Trong ví dụ đã kiểm thử, `Currency.getInstance(withEuro)` nhận key `cu=eur` từ locale, trả Currency EUR. Base language `en` và country `US` **không đổi**.

Không suy rằng thay `cu` là chuyển đổi tỷ giá, cũng không có nghĩa một giá USD trong database đã biến thành EUR. `Currency` là metadata về đơn vị tiền; đổi tiền thật yêu cầu giá trị giao dịch, tỷ giá áp dụng, làm tròn và quy tắc nghiệp vụ.

### 7.2. `fw`: ngày đầu tuần khác với ngôn ngữ hiển thị

~~~java
Locale base = Locale.forLanguageTag("en-US");
Locale mondayStart = Locale.forLanguageTag("en-US-u-fw-mon");

System.out.println(WeekFields.of(base).getFirstDayOfWeek());
// SUNDAY trong JDK được thử
System.out.println(WeekFields.of(mondayStart).getFirstDayOfWeek());
// MONDAY
~~~

`WeekFields.of(Locale)` trong `java.time.temporal` hỗ trợ quy tắc về ngày bắt đầu tuần. `en-US-u-fw-mon` vẫn là tiếng Anh và vùng US trong các trường cơ sở, nhưng yêu cầu ngày đầu tuần là Monday ở những API hỗ trợ extension.

Không nhầm `fw` với thứ tự hiển thị chữ trên lịch. Ngày đầu tuần ảnh hưởng **cách tính tuần/hiển thị lịch**, trong khi tên “Monday/Thứ Hai” là dữ liệu hiển thị tùy ngôn ngữ.

### 7.3. `rg`: vùng quy ước ghi đè không sửa country cơ sở

~~~java
Locale overridden = Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

System.out.println(overridden.getCountry()); // US
System.out.println(
        Currency.getInstance(overridden).getCurrencyCode()); // GBP
~~~

`getCountry()` vẫn là `US` vì thành phần region cơ sở của tag vẫn US. Nhưng các API có hỗ trợ `rg=gbzzzz` có thể lấy **quy ước vùng GB** như lựa chọn override; trong thử nghiệm `Currency.getInstance` cho GBP.

**Không nhầm `rg` là sửa country của người dùng.** Nó là một chỉ dẫn điều chỉnh dữ liệu locale cho service phù hợp. Với các yêu cầu địa lý, billing, thuế, vận chuyển hoặc timezone, hãy dùng thuộc tính nghiệp vụ thực tế. Một extension trong format locale không phải bằng chứng địa điểm giao hàng hay pháp lý.

### 7.4. `tz`: extension múi giờ cho API phù hợp, không thay cho `ZoneId` rõ ràng

~~~java
Locale withZone = Locale.forLanguageTag(
        "en-US-u-tz-uslax");

DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .localizedBy(withZone);

System.out.println(withZone.getUnicodeLocaleType("tz"));
// uslax
System.out.println(formatter.getZone());
// America/Los_Angeles trên JDK được thử
~~~

Ở đây `localizedBy` của `DateTimeFormatter` xem xét các extension thích hợp, bao gồm time zone. Điều này khác với:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withLocale(withZone);

System.out.println(formatter.getZone());
// null khi không có override zone nào khác, theo JDK được thử
~~~

`withLocale` thay locale dùng cho phần text, còn `localizedBy` có thể áp dụng các phần mở rộng như lịch và múi giờ. Không coi hai method là đồng nghĩa tuyệt đối.

Với ứng dụng cần xác định múi giờ nghiệp vụ của một sự kiện hoặc người dùng, dùng `ZoneId.of("America/Los_Angeles")` hoặc một `ZoneId` đã được người dùng/chính sách chọn một cách tường minh và gắn nó vào tính toán/format phù hợp. Locale extension không phải một thay thế tổng quát cho mô hình thời gian.

### 7.5. `nu`: hệ chữ số, khác language và region

~~~java
Locale arabDigits = Locale.forLanguageTag("en-US-u-nu-arab");
System.out.println(arabDigits.getUnicodeLocaleType("nu"));
// arab
~~~

Extension `nu` chọn numbering system ở các API định dạng có hỗ trợ. Người dùng có thể xem ngôn ngữ tiếng Anh nhưng muốn hệ chữ số khác chữ số Latin. Điều này **không** thay `getLanguage()` hay `getCountry()`.

Cách ký tự số xuất hiện còn phụ thuộc provider hỗ trợ, dữ liệu locale và formatter. Muốn kiểm thử một hệ chữ số cụ thể, dùng `NumberFormat`/`DecimalStyle` thích hợp trong runtime đích; không giả định mọi locale extension được mọi API hiểu.

## 8. Chương trình Java 17+ hoàn chỉnh — ngôn ngữ, vùng, hai category, và extension Java 10

Chương trình sau chạy được trên Java 17+, không dựa vào tên quốc gia tiếng Việt cố định trong stdout. Những nhãn hiển thị có thể thay theo dữ liệu CLDR/JDK, vì vậy test so sánh **hành vi**: tên nước thay đổi khi đổi ngôn ngữ hiển thị, và default DISPLAY/FORMAT điều khiển các API tương ứng.

~~~java
// File: DisplayLanguageRegionDemo.java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class DisplayLanguageRegionDemo {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale germanRegionEnglish = Locale.forLanguageTag("en-DE");
        Locale displayVi = Locale.forLanguageTag("vi-VN");
        Locale displayEn = Locale.ENGLISH;

        System.out.println("en-US language = " + us.getLanguage());
        System.out.println("en-US region = " + us.getCountry());
        System.out.println("en-DE language = "
                + germanRegionEnglish.getLanguage());
        System.out.println("en-DE region = "
                + germanRegionEnglish.getCountry());
        System.out.println("US country display localized = "
                + !us.getDisplayCountry(displayVi).equals(
                        us.getDisplayCountry(displayEn)));

        double amount = 12345.67;
        System.out.println("US number = "
                + NumberFormat.getNumberInstance(Locale.US).format(amount));
        System.out.println("German number = "
                + NumberFormat.getNumberInstance(Locale.GERMANY).format(amount));
        System.out.println("en-DE number = "
                + NumberFormat.getNumberInstance(germanRegionEnglish).format(amount));

        Locale initialDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale initialFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        try {
            Locale.setDefault(Locale.Category.DISPLAY, displayVi);
            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
            System.out.println("DISPLAY category = "
                    + Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("FORMAT category = "
                    + Locale.getDefault(Locale.Category.FORMAT).toLanguageTag());
            System.out.println("default country label follows DISPLAY = "
                    + us.getDisplayCountry().equals(
                            us.getDisplayCountry(displayVi)));
            System.out.println("default number follows FORMAT = "
                    + NumberFormat.getNumberInstance().format(amount)
                            .equals(NumberFormat.getNumberInstance(
                                    Locale.GERMANY).format(amount)));
        } finally {
            Locale.setDefault(Locale.Category.DISPLAY, initialDisplay);
            Locale.setDefault(Locale.Category.FORMAT, initialFormat);
        }

        Locale currencyType = Locale.forLanguageTag("en-US-u-cu-eur");
        Locale regionOverride = Locale.forLanguageTag(
                "en-US-u-rg-gbzzzz");
        Locale weekStartOverride = Locale.forLanguageTag(
                "en-US-u-fw-mon");

        System.out.println("base currency = "
                + Currency.getInstance(us).getCurrencyCode());
        System.out.println("cu currency = "
                + Currency.getInstance(currencyType).getCurrencyCode());
        System.out.println("rg country field unchanged = "
                + regionOverride.getCountry());
        System.out.println("rg currency = "
                + Currency.getInstance(regionOverride).getCurrencyCode());
        System.out.println("base first weekday = "
                + WeekFields.of(us).getFirstDayOfWeek());
        System.out.println("fw first weekday = "
                + WeekFields.of(weekStartOverride).getFirstDayOfWeek());

        Locale withNu = Locale.forLanguageTag("en-US-u-nu-arab");
        System.out.println("nu locale keyword = "
                + withNu.getUnicodeLocaleType("nu"));
        System.out.println("locale immutable base = "
                + us.toLanguageTag());
        System.out.println("vi-VN label available = "
                + !us.getDisplayCountry(displayVi).isBlank());

        LocalDate date = LocalDate.of(2026, 11, 7);
        String usDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.US).format(date);
        String deDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.GERMANY).format(date);
        System.out.println("date text differs by locale = "
                + !usDate.equals(deDate));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 DisplayLanguageRegionDemo.java
java DisplayLanguageRegionDemo
~~~

Stdout đã kiểm chứng trên JDK thử nghiệm:

~~~text
en-US language = en
en-US region = US
en-DE language = en
en-DE region = DE
US country display localized = true
US number = 12,345.67
German number = 12.345,67
en-DE number = 12.345,67
DISPLAY category = vi-VN
FORMAT category = de-DE
default country label follows DISPLAY = true
default number follows FORMAT = true
base currency = USD
cu currency = EUR
rg country field unchanged = US
rg currency = GBP
base first weekday = SUNDAY
fw first weekday = MONDAY
nu locale keyword = arab
locale immutable base = en-US
vi-VN label available = true
date text differs by locale = true
~~~

### 8.1. Giải thích kết quả

1. `en-US` và `en-DE` đều có `getLanguage() == "en"`, nhưng có `getCountry()` là `US` và `DE` khác nhau. Đó là ví dụ trực tiếp của việc **ngôn ngữ và vùng là hai thành phần độc lập**.
2. `getDisplayCountry(Locale.ENGLISH)` so với `getDisplayCountry(vi-VN)` cho tên cùng một vùng US nhưng theo hai ngôn ngữ hiển thị. Chương trình chỉ in boolean “localized”, không khóa chặt unit test vào một bản dịch cụ thể.
3. `NumberFormat` cho `12,345.67` (US) và `12.345,67` (Đức) trên môi trường thử nghiệm. `en-DE` giữ language `en` nhưng nhận định dạng số theo ngữ cảnh locale vùng DE ở môi trường đó.
4. Tạm thiết lập `DISPLAY=vi-VN` và `FORMAT=de-DE`: `getDisplayCountry()` không có tham số đi theo DISPLAY, còn `NumberFormat.getNumberInstance()` không có tham số đi theo FORMAT. Sau đó `finally` khôi phục hai default của JVM.
5. Extension `cu=eur` khiến `Currency.getInstance(...)` cho EUR trong ví dụ. `rg=gbzzzz` khiến Currency dùng GBP, nhưng `getCountry()` trên locale ấy vẫn là US.
6. `fw=mon` làm `WeekFields.of(locale).getFirstDayOfWeek()` cho Monday, trong khi locale cơ sở US ở môi trường thử nghiệm có Sunday.
7. `nu=arab` được giữ trong Locale và đọc ra bằng `getUnicodeLocaleType("nu")`. Chương trình không giả định ký tự số cụ thể được hỗ trợ ở mọi runtime.
8. `DateTimeFormatter.ofLocalizedDate(...).withLocale(...)` tạo văn bản ngày khác nhau giữa US và Germany; test so sánh sự khác biệt thay vì gắn một bản dịch hoặc pattern cố định.

**Giới hạn của thử nghiệm:** Các giá trị ở đây được xác minh trên một JDK có dữ liệu locale thông dụng. Một runtime tối giản hoặc provider khác có thể thiếu dữ liệu địa phương hóa hoặc đổi cách thể hiện; API không nên được dùng như nguồn duy nhất của các chuỗi UI đã dịch sẵn. Đặc biệt, ví dụ thay `setDefault` chỉ phù hợp demo/test đơn luồng, **không phải kiến trúc server đa người dùng**.

## 9. Những sai lầm thường gặp khi dùng default category

### 9.1. Dùng default FORMAT để chọn ngôn ngữ menu

~~~java
// Ý định cần nhãn tiếng Việt, nhưng lại lấy nhầm FORMAT locale:
Locale selected = Locale.getDefault(Locale.Category.FORMAT);
String label = Locale.US.getDisplayCountry(selected);
~~~

Nếu default FORMAT là `de-DE`, nhãn có thể xuất hiện bằng tiếng Đức dù UI là tiếng Việt. Đúng hơn là dùng display locale được chọn cho UI:

~~~java
String label =
        Locale.US.getDisplayCountry(userDisplayLocale);
~~~

Trong ứng dụng không có user-specific locale, `Locale.getDefault(Locale.Category.DISPLAY)` có thể được dùng làm default phù hợp cho nhãn hiển thị.

### 9.2. Dùng default DISPLAY để format số giao dịch

~~~java
Locale uiLocale = Locale.getDefault(Locale.Category.DISPLAY);
String number = NumberFormat.getNumberInstance(uiLocale)
        .format(12345.67);
~~~

Nếu người dùng chọn UI tiếng Việt nhưng đã chọn định dạng số Đức, đoạn trên **bỏ qua lựa chọn FORMAT**. Hãy truyền đúng `userFormatLocale` hoặc sử dụng default FORMAT khi đó là contract mong muốn.

### 9.3. Thay global default cho mỗi request

~~~java
// Thiết kế không phù hợp trong web server nhiều user:
Locale.setDefault(Locale.Category.FORMAT, requestLocale);
String amount = NumberFormat.getNumberInstance().format(12345.67);
~~~

Một request khác có thể đổi default cùng lúc, làm giá trị bị format theo locale không mong muốn. Sử dụng tham số tường minh thay vì thay global state.

### 9.4. Coi tên vùng hiển thị là mã chuẩn

Không dùng `getDisplayCountry()` làm database key hoặc gửi nó như country code trong API. Tên dịch có thể thay giữa các ngôn ngữ hoặc JDK; `getCountry()` hoặc trường địa chỉ chuẩn phù hợp mới là mã dữ liệu.

## 10. Ngôn ngữ bản dịch không tự động được xác định bởi việc format số

Bộ chọn “Language: Vietnamese” thường điều khiển:

- Thông điệp UI, button, error descriptions.
- Tên ngôn ngữ và quốc gia hiển thị.
- Cách sắp xếp/dấu câu và ngữ pháp khi ứng dụng đã có tài nguyên i18n phù hợp.

Bộ chọn “Regional format: Germany” thường điều khiển:

- Dấu nhóm/thập phân trong số.
- Thứ tự/tháng/ngày trong chuỗi ngày được format theo locale.
- Thứ tự ngày đầu tuần và những convention khác.
- Một số mặc định định dạng tiền tệ nếu ứng dụng chủ đích sử dụng dịch vụ locale.

**Không có nghĩa rằng Java tự dịch nội dung tùy ý.** Ví dụ:

~~~java
String literal = "Save changes";
String result = String.format(
        Locale.forLanguageTag("vi-VN"), "%s", literal);

// result vẫn là "Save changes".
~~~

`String.format` xử lý format specifier, không dịch chuỗi tiếng Anh thành tiếng Việt. Nếu cần lời nhắn tiếng Việt, hệ thống cần thông điệp đã được bản địa hóa riêng (ví dụ `ResourceBundle` với bundle thích hợp).

### 10.1. Chọn bản dịch bằng language tag

Có thể lưu preference `"vi-VN"` hoặc `"en-US"` rồi tải bundle theo locale. Tuy nhiên:

- Không giả định `ResourceBundle.getBundle(...)` sẽ tìm thấy một bản dịch chỉ vì có locale đó.
- Java có cơ chế fallback và candidate locales; cần khai báo resource thực sự tồn tại.
- Ngôn ngữ UI có thể được người dùng chọn riêng với định dạng số; tổ hợp này cần được lưu trong model request/user.
- Đầu vào language tag phải được kiểm tra/giới hạn theo những ngôn ngữ ứng dụng hỗ trợ, không tự tin rằng mọi chuỗi hợp cú pháp đều có bản dịch.

Khi có fallback, hiển thị tiếng Anh cho những message chưa dịch có thể là lựa chọn sản phẩm; nhưng phải là policy rõ, không phải kết quả vô tình của country code.

## 11. Chọn vùng định dạng cho ngày tháng và thời gian

Các API java.time hiện đại có hỗ trợ format theo locale:

~~~java
LocalDate date = LocalDate.of(2026, 11, 7);

String us = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.US)
        .format(date);

String de = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.GERMANY)
        .format(date);
~~~

Đoạn này cần import `LocalDate`, `DateTimeFormatter`, `FormatStyle` và `Locale`. Cùng một `LocalDate` nhưng cách trình bày khác nhau theo locale. Nếu bài toán cần **thời điểm thực** (instant) thay vì ngày lịch không có giờ, còn phải chọn `ZoneId` để chuyển đổi sang thời gian địa phương trước khi hiển thị.

Phân biệt:

| Thông tin | API hoặc loại dữ liệu gợi ý |
| --- | --- |
| Ngôn ngữ tên ngày/tháng | `Locale` truyền vào formatter |
| Quy tắc trình bày ngày | `DateTimeFormatter` localized pattern |
| Múi giờ | `ZoneId`, `ZonedDateTime` hoặc cấu hình zone rõ ràng |
| Ngày đầu tuần | `WeekFields.of(locale)` hoặc cấu hình tương đương |
| Hệ lịch/numbering | Unicode locale extensions thích hợp trong API có hỗ trợ |
| Timestamp lưu trữ | `Instant`/kiểu thời gian phù hợp, không lưu chuỗi hiển thị theo locale làm giá trị chuẩn |

Có thể hiển thị thời gian ở múi giờ Berlin bằng ngôn ngữ tiếng Việt; đây không phải dữ liệu mâu thuẫn. `Locale` và `ZoneId` phục vụ các trục thông tin khác nhau.

### 11.1. Khi dùng `tz` extension

`DateTimeFormatter.localizedBy(locale)` có thể áp dụng Unicode locale extension `tz`, như ví dụ `uslax` cho Los Angeles. Nhưng `withLocale(locale)` chủ yếu thay locale cho phần text và không nên được coi là alias với `localizedBy` khi cần tác động đến chronology/zone.

Nếu dịch vụ có yêu cầu múi giờ chính xác và áp dụng DST, cung cấp `ZoneId` tường minh, ví dụ:

~~~java
ZoneId zone = ZoneId.of("Europe/Berlin");
ZonedDateTime timestamp =
        instant.atZone(zone);
~~~

Đây là đoạn minh họa giả định `instant` là `Instant`, import `ZoneId`/`ZonedDateTime`. Một country code như `US` không xác định duy nhất một time zone.

## 12. Extension và compatibility giữa JDK/runtime

BCP 47 language tag có thể mang nhiều loại Unicode extension. Nhưng **việc parse một extension** không đồng nghĩa **mọi locale-sensitive service** sẽ áp dụng nó.

Ví dụ:

~~~java
Locale custom = Locale.forLanguageTag("en-US-u-nu-arab");
System.out.println(custom.getUnicodeLocaleType("nu")); // arab
~~~

`getUnicodeLocaleType("nu")` trả type đã lưu trong tag. `NumberFormat` chỉ áp dụng hệ chữ số đó nếu provider hỗ trợ; không có bảo đảm Java phải nhận mọi type trong mọi runtime.

### 12.1. Extension không nhất thiết thay đổi mọi API

- `cu` được Java 10 bổ sung hỗ trợ ở `Currency.getInstance(locale)`. Không vì thế giả định tất cả API dùng currency đều tự đổi mọi giá trị hoặc biểu tượng theo chính sách mong muốn.
- `fw` được hỗ trợ ở logic tuần như `WeekFields.of(locale)`; không tự thay lịch làm việc của doanh nghiệp.
- `rg` có thể được xét bởi các factory định dạng hoặc currency thích hợp, **không sửa** thành phần country cơ sở.
- `tz` có ý nghĩa ở API thời gian được hỗ trợ, **không tự cấu hình hệ thống timezone của tiến trình hoặc kết nối bên ngoài**.
- `nu` và `ca` ảnh hưởng một số formatter/data provider, không phải toàn bộ Java runtime.

Đọc Javadoc của service thực sự thay vì chỉ thấy một key nằm trong language tag.

### 12.2. Dữ liệu CLDR và locale provider

Dữ liệu ngôn ngữ, format, biểu tượng tiền tệ, tên vùng... có thể thay đổi theo phiên bản Unicode/CLDR và cấu hình runtime. Tập locale khả dụng còn có thể bị giới hạn bởi một runtime image được đóng gói tối giản.

Bởi vậy:

- Đừng lưu chính tên nước đã dịch thành mã chuẩn.
- Đừng hardcode một bản dịch từ provider thành kỳ vọng bất biến giữa các JDK.
- Với dữ liệu máy đọc, dùng format có quy định tường minh thay vì output địa phương hóa.
- Đối với UI quan trọng, test bộ JDK/provider thực tế triển khai và các language tag được hỗ trợ.
- Nếu extension không được một provider hỗ trợ, cần có fallback/policy sản phẩm rõ ràng.

## 13. Thiết kế cấu hình: tách `uiLocale`, `formatLocale`, `currency` và `zone`

Một model rõ ràng:

~~~java
record UserPresentationOptions(
        Locale uiLocale,
        Locale formatLocale,
        Currency currency,
        ZoneId zoneId
) {
    UserPresentationOptions {
        Objects.requireNonNull(uiLocale);
        Objects.requireNonNull(formatLocale);
        Objects.requireNonNull(currency);
        Objects.requireNonNull(zoneId);
    }
}
~~~

Đoạn này cần import `Locale`, `Currency`, `ZoneId`, `Objects`. Mỗi trường đại diện cho một lựa chọn khác nhau. Dùng `record` (Java 16+) để tiện tạo kiểu dữ liệu không tự thay đổi trường tham chiếu; `Locale`, `Currency`, `ZoneId` đều là các giá trị phù hợp. Nếu thêm object mutable vào record trong thực tế, vẫn cần xét defensive copy.

Ví dụ lấy thông tin đã cấu hình:

~~~java
var prefs = new UserPresentationOptions(
        Locale.forLanguageTag("vi-VN"),
        Locale.GERMANY,
        Currency.getInstance("USD"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

String regionName = Locale.US
        .getDisplayCountry(prefs.uiLocale());

String amountText = NumberFormat
        .getNumberInstance(prefs.formatLocale())
        .format(12345.67);
~~~

Đây chỉ là cách trình bày. Không dùng `NumberFormat.getCurrencyInstance(Locale.GERMANY)` rồi mặc nhiên coi giao dịch là EUR nếu dữ liệu hợp đồng ghi USD. Nếu cần hiển thị số **bằng loại tiền cụ thể**, có thể lấy currency formatter theo format locale, sau đó gọi `setCurrency(prefs.currency())` cho formatter riêng đó, và kiểm soát số chữ số thập phân/rounding theo nghiệp vụ.

### 13.1. Đừng gắn kết vùng quy ước với quyền truy cập

Không quyết định quyền sử dụng tính năng dựa trên `Locale.getCountry()`. Country của locale chỉ là lựa chọn ngữ cảnh định dạng, không phải nguồn xác thực về pháp lý, địa chỉ người dùng hoặc quyền hạn.

Một người có thể dùng `en-US` cho UI nhưng đang ở quốc gia khác; điều đó bình thường. Tách riêng các dữ liệu nhạy cảm và logic authorization từ user preferences.

## 14. Mã language tag và validation

`Locale.forLanguageTag(String)` thích hợp để nhận một language tag BCP 47 phổ biến:

~~~java
Locale a = Locale.forLanguageTag("vi-VN");
Locale b = Locale.forLanguageTag("en-US-u-fw-mon");
Locale c = Locale.forLanguageTag("zh-Hant-TW");
~~~

Nếu hệ thống muốn kiểm tra **cú pháp** chặt chẽ hơn, cân nhắc `Locale.Builder`:

~~~java
Locale supported = new Locale.Builder()
        .setLanguageTag("vi-VN")
        .build();
~~~

`Locale.Builder` có thể ném `IllformedLocaleException` nếu một trường/tag không hợp cú pháp. Nhưng **hợp cú pháp** không đồng nghĩa **có bản dịch** hoặc mọi extension được hỗ trợ: cần kiểm tra tập locale sản phẩm cho phép.

### 14.1. Language tag không phải free-text mô tả tên nước

Không đưa thẳng `"Vietnamese in Germany"` vào `Locale.forLanguageTag` rồi chờ nó hiểu mong muốn. Language tag có grammar cụ thể; dùng `vi-DE` hoặc hai locale riêng nếu yêu cầu thực tế là UI tiếng Việt và định dạng kiểu Đức. Không encode quá nhiều lựa chọn nghiệp vụ vào một tag khi chúng độc lập.

### 14.2. Lưu mã, không lưu tên dịch

Trong database/config nên lưu `"vi-VN"`, `"de-DE"` hoặc các mã được sản phẩm hỗ trợ. Tên hiển thị như “Tiếng Việt” hoặc “Deutsch” được tạo **khi render UI** theo display locale hiện hành, thay vì được xem là ID bất biến.

### 14.3. Đầu vào thiếu hoặc không được hỗ trợ

Cần chính sách fallback có thứ tự: locale user chọn → locale tổ chức → locale ứng dụng. Tránh phụ thuộc ngầm default của server, đặc biệt với môi trường triển khai nhiều vùng. Với yêu cầu formatting cho máy, nên dùng format chuẩn được chỉ định trong protocol, không tự lấy từ preference của user.

## 15. Bài toán chọn ngôn ngữ UI và format locale trong HTTP

Header `Accept-Language` có thể giúp **gợi ý** ngôn ngữ người dùng muốn nhận nội dung. Nhưng không nên suy thẳng từ header này thành:

- Quốc gia hiện tại.
- Loại tiền tệ của đơn hàng.
- Địa chỉ thuế hoặc giao hàng.
- Múi giờ.
- Ngôn ngữ UI đã được user cố định trong tài khoản.

Ứng dụng có thể đưa ra lựa chọn ngôn ngữ và quy tắc vùng riêng. Một chính sách thường hợp lý:

1. Khi user đã đặt ngôn ngữ UI, ưu tiên setting đó.
2. Nếu chưa đặt, đàm phán với tập ngôn ngữ **thực sự hỗ trợ**, có thể dựa vào `Accept-Language`.
3. Khi user có lựa chọn vùng format riêng, dùng nó cho số/ngày.
4. Khi không có lựa chọn vùng, dùng một default sản phẩm đã xác định.
5. Currency và timezone phải được xác định từ dữ liệu/hợp đồng hoặc lựa chọn riêng.

Java có `Locale.LanguageRange` và `Locale.lookup`/`filter` cho việc matching language tags, nhưng cách sử dụng phải phù hợp với danh sách locale của ứng dụng. Matching một tag không sinh ra một bản dịch mới khi tài nguyên dịch chưa tồn tại.

## 16. Những ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`getLanguage()` trả tên ngôn ngữ đã dịch.” | Nó trả mã như `en`, `vi`, `de`. Dùng `getDisplayLanguage(displayLocale)` để tạo tên. |
| “`getCountry()` trả tên quốc gia người dùng nhìn thấy.” | Nó trả mã vùng như `US`, `DE`; dùng `getDisplayCountry(displayLocale)` để lấy tên đã địa phương hóa. |
| “Mã quốc gia trên Locale cho biết vị trí địa lý hiện tại.” | Không; đó là thành phần cấu hình locale. |
| “Ngôn ngữ UI và cách hiển thị số bắt buộc cùng locale.” | Không. Có thể tách `uiLocale` và `formatLocale`. |
| “`Locale.Category.DISPLAY` và `FORMAT` là tính năng mới từ Java 10.” | Không; category đã có trước. Java 10 mở rộng một số **Unicode language-tag extensions** qua JEP 314. |
| “`getDisplayCountry()` không có tham số dùng default FORMAT.” | Không; nó dùng default DISPLAY. |
| “`NumberFormat.getNumberInstance()` không có tham số dùng default DISPLAY.” | Không; nó dùng default FORMAT. |
| “`Locale.getDefault()` chắc chắn bằng cả DISPLAY và FORMAT.” | Không khi category defaults được cấu hình khác. |
| “Dùng `Locale.setDefault` mỗi request là cách tạo cá nhân hóa an toàn.” | Không; thay global JVM state và có thể ảnh hưởng người dùng khác. |
| “`en-DE` đồng nghĩa với `en-US` vì đều language en.” | Không; region khác và có thể tạo quy ước định dạng khác. |
| “`Locale.GERMANY` tự dịch mọi chữ tiếng Anh thành tiếng Đức.” | Không. Phải có tài nguyên dịch riêng. |
| “`rg` tự thay `getCountry()` của tag.” | Không. Region override ảnh hưởng API có hỗ trợ, country cơ sở giữ nguyên. |
| “`cu` đổi tiền và tỷ giá của giao dịch.” | Không. Đây là extension chọn metadata currency ở API thích hợp. |
| “`fw` luôn đồng nghĩa đổi ngôn ngữ của tên ngày.” | Không; nó ảnh hưởng ngày đầu tuần ở API hỗ trợ. |
| “`tz` sẽ tự đặt timezone hệ thống cho mọi tác vụ.” | Không; chỉ một số service i18n/time áp dụng extension. |
| “`DateTimeFormatter.withLocale` giống hệt `localizedBy` với tz/calendar extensions.” | Không nên coi là tương đương. |
| “Một tag hợp cú pháp bảo đảm JDK có dữ liệu bản địa hóa đầy đủ.” | Không; còn phụ thuộc provider và locale data. |
| “Output localized từ NumberFormat có thể lưu như giao thức số bất biến.” | Không; dùng protocol format/serializer phù hợp để trao đổi máy-máy. |
| “Dùng tên nước đã dịch làm database key là ổn định.” | Không; lưu mã vùng chuẩn phù hợp. |
| “Locale cũng quyết định currency của mọi giá trị tiền nghiệp vụ.” | Không; mã tiền và giá trị giao dịch nên tách riêng. |

## 17. Câu hỏi thực hành và đáp án

### Câu 1 — Nhận biết language và region

~~~java
Locale locale = Locale.forLanguageTag("en-DE");
~~~

**Hỏi:** `getLanguage()` và `getCountry()` trả gì?

**Đáp án:** Lần lượt `"en"` và `"DE"`. Tiếng Anh vẫn được giữ trong language field; region là Đức.

### Câu 2 — Tên quốc gia theo ngôn ngữ khác

~~~java
Locale target = Locale.US;
var name1 = target.getDisplayCountry(Locale.ENGLISH);
var name2 = target.getDisplayCountry(
        Locale.forLanguageTag("vi-VN"));
~~~

**Đáp án:** Cả hai cùng mô tả vùng US; cách hiển thị tên theo hai ngôn ngữ có thể khác. `target.getCountry()` vẫn là `US`.

### Câu 3 — Dùng sai default category

Ứng dụng muốn tên quốc gia theo UI tiếng Việt, nhưng lấy `Locale.getDefault(Locale.Category.FORMAT)` (đang là `de-DE`) để truyền vào `getDisplayCountry(...)`.

**Đáp án:** Có thể nhận tên theo tiếng Đức, không phù hợp UI. Hãy dùng display locale của user hoặc default DISPLAY.

### Câu 4 — Định dạng số kiểu Đức

~~~java
var amount = NumberFormat
        .getNumberInstance(Locale.GERMANY)
        .format(12345.67);
~~~

**Đáp án:** Kết quả trong JDK thử nghiệm là `12.345,67`. Quy tắc format được chọn bởi locale truyền tường minh.

### Câu 5 — Chọn độc lập hai category

Muốn `Locale.US.getDisplayCountry()` dùng ngôn ngữ Việt và `NumberFormat.getNumberInstance()` dùng quy ước Đức thì cần gì?

**Đáp án:** Có thể cấu hình default DISPLAY là `vi-VN`, default FORMAT là `de-DE` trong **demo/JVM do bạn kiểm soát**, hoặc tốt hơn ở application nhiều user là truyền hai locale tường minh cho từng API. Không thay global default mỗi request.

### Câu 6 — Extension tiền tệ

~~~java
Locale loc = Locale.forLanguageTag("en-US-u-cu-eur");
Currency currency = Currency.getInstance(loc);
~~~

**Đáp án:** `currency.getCurrencyCode()` là `EUR` trên JDK hỗ trợ JEP 314 như môi trường thử. Ngôn ngữ và vùng cơ sở vẫn `en` và `US`; không có phép chuyển tỷ giá.

### Câu 7 — Region override

~~~java
Locale loc = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
~~~

**Hỏi:** `loc.getCountry()` có phải `GB` không?

**Đáp án:** Không, nó vẫn `US`. `rg=gbzzzz` là extension hướng dẫn một số API dùng quy ước vùng GB. Với `Currency.getInstance(loc)` trong môi trường đã thử, kết quả là GBP.

### Câu 8 — Ngày đầu tuần

~~~java
var loc = Locale.forLanguageTag("en-US-u-fw-mon");
var day = WeekFields.of(loc).getFirstDayOfWeek();
~~~

**Đáp án:** `MONDAY` với API hỗ trợ extension `fw`. Điều này không đổi language field thành một ngôn ngữ khác.

### Câu 9 — Múi giờ và formatter

~~~java
var tz = Locale.forLanguageTag("en-US-u-tz-uslax");
var f = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(tz);
~~~

**Đáp án:** Trên JDK thử, `f.getZone()` là `America/Los_Angeles`. `withLocale(tz)` không tự tương đương hoàn toàn với `localizedBy(tz)` về timezone override.

### Câu 10 — `nu` không tự dịch nội dung

~~~java
Locale loc = Locale.forLanguageTag("en-US-u-nu-arab");
~~~

**Đáp án:** Language vẫn `en`, country vẫn `US`; extension `nu=arab` chỉ là chỉ dẫn hệ chữ số cho API định dạng có hỗ trợ. Nó không tự dịch nhãn “Save”.

### Câu 11 — Chọn timezone từ country

Một người dùng có locale `en-US`. Có thể khẳng định timezone của họ là New York không?

**Đáp án:** Không. Hoa Kỳ có nhiều vùng múi giờ và `Locale` chỉ là cấu hình locale. Hãy dùng `ZoneId` được xác định riêng.

### Câu 12 — Tên nước làm khóa dữ liệu

Bạn muốn lưu vùng US vào database nhưng đang có chuỗi từ `getDisplayCountry(vi-VN)`.

**Đáp án:** Lưu **mã** vùng `US` hoặc mã chuẩn nghiệp vụ thích hợp, không lưu tên nước đã dịch vì nó có thể đổi theo ngôn ngữ/provider.

### Câu 13 — Định dạng số cho parser

Service A gửi số cho service B theo protocol yêu cầu dấu thập phân `.`. Có nên để `NumberFormat` tự chọn locale của user?

**Đáp án:** Không. Dùng định dạng được protocol quy định và serializer đúng chuẩn; locale người dùng chỉ áp dụng khi **trình bày**.

### Câu 14 — Language tag được parse nhưng thiếu hỗ trợ

`Locale.forLanguageTag("...")` tạo object, nhưng service không thay đổi định dạng như mong đợi. Có phải Java bỏ qua toàn bộ Locale?

**Đáp án:** Không nhất thiết. Một số extension/type có thể không được API/provider đó hỗ trợ; kiểm tra contract service, dữ liệu locale có sẵn và fallback. Việc parse tag là một việc khác với áp dụng tất cả extensions.

### Câu 15 — Khả năng thay đổi global default

Một endpoint gọi `Locale.setDefault(Locale.Category.FORMAT,...)` cho mỗi request, rồi chạy `NumberFormat.getNumberInstance()`.

**Đáp án:** Đây là cách thiết kế không an toàn với nhiều request đồng thời. Lưu locale theo request/user rồi truyền vào `NumberFormat.getNumberInstance(locale)`; không sửa global JVM state cho nhu cầu cá nhân hóa.

## 18. Checklist khi xây UI hỗ trợ nhiều ngôn ngữ và vùng

- [ ] **Ngôn ngữ UI** có được lưu riêng (`uiLocale`) và dùng để chọn resource bản dịch không?
- [ ] **Quy ước format** có được lưu riêng (`formatLocale`) và truyền vào formatter số/ngày không?
- [ ] Có phân biệt rõ `getLanguage()` với `getDisplayLanguage(...)` không?
- [ ] Có phân biệt rõ `getCountry()` với `getDisplayCountry(...)` không?
- [ ] Nếu API không nhận locale, có biết nó dựa default `DISPLAY` hay `FORMAT` không?
- [ ] Có tránh `Locale.setDefault` cho từng request không?
- [ ] Có dùng `Locale.forLanguageTag` hoặc `Locale.Builder` với language tags được hỗ trợ không?
- [ ] Có hiểu `en-US` và `en-DE` cùng language nhưng khác vùng không?
- [ ] Có tránh suy region thành geolocation, địa chỉ hoặc quốc tịch không?
- [ ] Có tách `Currency` và giá trị tiền giao dịch ra khỏi format locale không?
- [ ] Có lưu `ZoneId` riêng cho dữ liệu thời gian không?
- [ ] Có cân nhắc `nu`, `ca` và extensions Java 10 `cu`, `fw`, `rg`, `tz` khi thực sự cần không?
- [ ] Có kiểm tra API i18n cụ thể có hỗ trợ extension được chọn không?
- [ ] Có kiểm tra dữ liệu CLDR/provider trong các runtime thực tế (đặc biệt runtime image tối giản) không?
- [ ] Có tránh hardcode display names làm mã/tên cột trong dữ liệu lưu trữ không?
- [ ] Có giới hạn tập locale/ngôn ngữ ứng dụng thực sự dịch được không?
- [ ] Có định dạng giao thức máy-máy theo chuẩn, không phụ thuộc UI locale không?
- [ ] Có kiểm thử locale độc lập với global defaults trên server nhiều luồng không?
- [ ] Có test cặp display vi-VN + format de-DE hoặc tổ hợp khác để phát hiện việc gán nhầm locale không?

## 19. Tài liệu chính thức còn hiệu lực

- [Java SE API — `Locale`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): cấu trúc language tag, `getLanguage`, `getCountry`, `getDisplayLanguage`, `getDisplayCountry`, hai `Locale.Category`, default theo category và Unicode extension.
- [JEP 314 — Additional Unicode Language-Tag Extensions (Java 10)](https://openjdk.org/jeps/314): các key `cu`, `fw`, `rg`, `tz` và API được mở rộng hỗ trợ từ Java 10.
- [Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): tài liệu quốc tế hóa chính thức theo release.
- [Java SE API — `NumberFormat`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html): format locale, default FORMAT, và các Unicode locale extensions phù hợp.
- [Java SE API — `Currency`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html): lấy mã tiền tệ theo locale và extension `cu`/`rg` khi hỗ trợ.
- [Java SE API — `WeekFields`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html): ngày bắt đầu tuần, quy tắc tuần và locale extensions liên quan.
- [Java SE API — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale`, `localizedBy`, format ngày/thời gian theo locale và extension.
- [Java SE API — `ZoneId`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html): timezone ID độc lập với display locale và country code.
- [Java SE API — `ResourceBundle`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.html): tìm tài nguyên bản dịch theo locale và fallback.
- [BCP 47 — IETF Language Tags](https://www.rfc-editor.org/rfc/rfc5646.html): chuẩn language tag phù hợp với `Locale.forLanguageTag`.
- [Unicode LDML / UTS #35](https://unicode.org/reports/tr35/): Unicode locale extension keywords và dữ liệu định dạng, phạm vi hỗ trợ tùy JDK/provider.

**Ghi nhớ cuối cùng:** **Language** cho biết ngôn ngữ hoặc ngữ cảnh bản dịch; **region** góp phần xác định những quy ước văn hóa và định dạng; **display locale** quyết định cách gọi tên ngôn ngữ/quốc gia cho người dùng; **format locale** quyết định cách biểu diễn số/ngày ở API phù hợp. Java có hai default category `DISPLAY`/`FORMAT` để phân biệt mục đích, và Java 10 mở rộng khả năng sử dụng `cu`, `fw`, `rg`, `tz`. Hãy truyền locale tường minh trong ứng dụng nhiều người dùng, kiểm soát tiền tệ và múi giờ riêng, và không nhầm nhãn đã dịch với mã dữ liệu hoặc địa điểm thực tế.