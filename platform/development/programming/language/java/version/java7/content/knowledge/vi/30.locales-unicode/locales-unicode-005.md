# Phân biệt locale hiển thị với locale định dạng trong Java

## 1. Cùng một người dùng, hai nhu cầu bản địa hóa khác nhau

Trong ứng dụng đa ngôn ngữ, người dùng có thể chọn **tiếng Pháp làm ngôn ngữ hiển thị** cho giao diện nhưng lại muốn **định dạng số và ngày tháng theo quy ước Đức**. Trường hợp này hoàn toàn hợp lý: ngôn ngữ người dùng muốn đọc không nhất thiết giống vùng/quy tắc họ muốn xem và nhập các giá trị số, tiền tệ, ngày giờ.

Java cung cấp `java.util.Locale` để mô tả tổ hợp ngôn ngữ, vùng, chữ viết và các phần mở rộng Unicode. Từ **Java 7**, `Locale.Category` cho phép JVM lưu hai locale mặc định **riêng biệt**:

- **`Locale.Category.DISPLAY`:** locale mặc định cho các chức năng **hiển thị tên có bản địa hóa**, chẳng hạn `Locale.getDisplayLanguage()`, `getDisplayCountry()` và `getDisplayName()`; đây là category cho user-interface display.
- **`Locale.Category.FORMAT`:** locale mặc định cho các chức năng **định dạng số, tiền tệ, ngày và giờ**, chẳng hạn `NumberFormat.getNumberInstance()`, `NumberFormat.getCurrencyInstance()`, `DateFormat.getDateInstance()` và `DateTimeFormatter.ofLocalizedDate(...)`.

Đề bài chính là **“Phân biệt locale hiển thị với locale định dạng”**, thuộc chủ đề cha **“Locale và Unicode”** của Java 7. Đây là API được giới thiệu từ Java 7 **nhưng vẫn được hỗ trợ trong Java SE 21 và các bản Java hiện đại**.

**Special Note của module:** chỉ lấy kiến thức còn áp dụng hiện nay; không sử dụng hướng dẫn lỗi thời hoặc legacy làm kiến trúc khuyến nghị. Bài dùng `Locale.Category`, `Locale.forLanguageTag`, `NumberFormat`, `java.time.format.DateTimeFormatter` và explicit locale parameters. `java.text.DateFormat` xuất hiện để đối chiếu API đang được hỗ trợ, nhưng với code ngày giờ mới, `java.time` thường là lựa chọn phù hợp hơn. Không khuyên dùng các constructor `Locale` đã deprecated trên JDK mới hoặc mẹo thay system properties lúc runtime để điều khiển mặc định.

### Mục tiêu

Sau bài học, bạn cần trả lời được:

1. `DISPLAY` và `FORMAT` khác nhau về **chức năng**, không chỉ tên gọi.
2. Vì sao một ứng dụng có thể dùng `fr-FR` để hiển thị tên locale nhưng `de-DE` để định dạng số/ngày.
3. Cách đọc và thay đổi hai default locale bằng `Locale.getDefault(Locale.Category)` và `Locale.setDefault(Locale.Category, Locale)`.
4. `Locale.getDefault()` không có category khác gì với hai default category.
5. Vì sao `Locale.setDefault(Locale)` lại đồng thời đặt **cả hai** category mặc định.
6. Những API nào dùng DISPLAY, những API nào dùng FORMAT, những API nào **không tự động** dùng DISPLAY.
7. Khi nào nên truyền `Locale` cụ thể thay vì dựa vào mặc định toàn JVM.
8. Tại sao locale khác Unicode charset, time zone và currency business value.
9. Cách viết unit test có output xác định dù tên locale và mẫu định dạng có thể thay đổi theo locale-data provider.
10. Cách thiết kế UI, API, batch, logging và multi-tenant service nhất quán.

## 2. `Locale.Category` là một enum hiện hành

Định nghĩa từ Java 7:

~~~java
public static enum Locale.Category {
    DISPLAY,
    FORMAT
}
~~~

Đây là **dạng mã minh họa** về các enum constants, không phải mã để tự khai báo vì enum đã nằm trong JDK. Oracle Java SE 21 Javadoc mô tả:

| Category | Ý nghĩa | Ví dụ điển hình |
| --- | --- | --- |
| `Locale.Category.DISPLAY` | Locale mặc định để hiển thị user-interface information | Tên của language, country, script, variant, một `Locale` khác |
| `Locale.Category.FORMAT` | Locale mặc định để định dạng dates, numbers, currencies | `NumberFormat`, `DateFormat`, `DateTimeFormatter` với locale mặc định |

Mã đọc hai giá trị:

~~~java
Locale displayLocale =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale formatLocale =
        Locale.getDefault(Locale.Category.FORMAT);
~~~

Đây là snippet, cần `import java.util.Locale;`. Chúng có thể **giống hoặc khác nhau**. Không mặc định rằng `getDefault(DISPLAY).equals(getDefault(FORMAT))` luôn đúng.

### 2.1. Tại sao cần category?

Một giá trị “default locale” duy nhất thường **không đủ** cho mọi nhu cầu. Người dùng có thể sử dụng ứng dụng UI tiếng Anh nhưng làm việc với dữ liệu số Đức; một người nói tiếng Việt đang ở Hoa Kỳ có thể muốn UI tiếng Việt với cách trình bày số, ngày hoặc currency theo yêu cầu riêng.

`DISPLAY` và `FORMAT` cho phép các thư viện quan sát **hai default khác nhau**. Tuy nhiên đây là **JVM-wide default configuration**, không phải preference riêng của từng HTTP request hay từng thread. Trong ứng dụng phục vụ nhiều người dùng, truyền locale rõ ràng theo từng người dùng thường an toàn hơn.

### 2.2. Locale là gì, và không phải gì?

`Locale` có thể chứa:

- **language:** thẻ ngôn ngữ, ví dụ `vi`, `en`, `fr`, `de`;
- **region:** mã lãnh thổ, ví dụ `VN`, `US`, `FR`, `DE`;
- **script:** ví dụ `Latn`, `Cyrl` khi có ý nghĩa;
- **variants/Unicode locale extensions:** có thể biểu diễn preference về lịch, numbering system và những thuộc tính địa phương khác.

`Locale` **không** trực tiếp là:

- `Charset`/encoding của chuỗi (Java `String` chứa Unicode text; đọc/ghi bytes vẫn cần charset như UTF-8).
- `ZoneId` của thời gian (múi giờ và locale là hai khái niệm khác nhau).
- Bản thân số tiền và loại tiền của giao dịch (locale có thể quyết định cách hiển thị, nhưng domain currency vẫn cần xác định).
- Bản dịch UI strings; `Locale` là tín hiệu chọn resource, **không tự dịch văn bản tiếng Anh bất kỳ**.
- Vị trí GPS hoặc quốc tịch người dùng.
- Guarantee rằng JDK có dữ liệu bản địa hóa đầy đủ cho mọi `Locale` hợp lệ.

### 2.3. Cách khai báo locale hiện hành

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale french = Locale.forLanguageTag("fr-FR");
Locale german = Locale.forLanguageTag("de-DE");
Locale englishUS = Locale.US;
~~~

Đây là snippet có `import java.util.Locale;`. `forLanguageTag` đọc thẻ theo BCP 47, phổ biến và portable trên Java 17+. Từ Java 19 có thêm `Locale.of(...)`, nhưng `forLanguageTag` phù hợp khi ứng dụng đã nhận locale theo dạng tag, ví dụ từ user profile.

**Đừng dùng `String.replace("_","-")` tùy tiện rồi cho rằng đã validate mọi tag.** Khi nhận input từ network, cần parse/validate theo danh sách locale ứng dụng hỗ trợ và fallback policy; một `Locale` biểu diễn được không đồng nghĩa mọi tài nguyên dịch/format đều sẵn có.

## 3. Ba giá trị mặc định: general, DISPLAY, FORMAT

Java có các overloads:

~~~java
Locale general = Locale.getDefault();
Locale display = Locale.getDefault(Locale.Category.DISPLAY);
Locale format  = Locale.getDefault(Locale.Category.FORMAT);
~~~

`Locale.getDefault()` không có category trả **general default locale** của JVM. Hai overload có category trả **giá trị mặc định dành riêng** cho DISPLAY và FORMAT. Khi ứng dụng đặt riêng một category, general default có thể **không thay đổi**.

### 3.1. Đặt category độc lập

~~~java
Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
~~~

Đây là snippet minh họa, không nên chạy trực tiếp trong request của production server. Sau hai lời gọi:

- DISPLAY trở thành `fr-FR`.
- FORMAT trở thành `de-DE`.
- General default `Locale.getDefault()` **không bị hai category-specific setters này tự sửa**.

Nếu trước đó general default là `en-US`, nó vẫn là `en-US`. Mã chạy đầy đủ sẽ in chính xác ba thẻ này và kiểm tra độc lập.

### 3.2. `setDefault(Locale)` có ảnh hưởng cả hai category?

**Có.** Java SE Javadoc quy định:

~~~java
Locale.setDefault(Locale.US);
~~~

Lời gọi này thiết lập **general default** và đồng thời thiết lập **default của mọi `Locale.Category`** thành `Locale.US`. Nếu trước đó DISPLAY và FORMAT khác nhau, `setDefault(Locale.US)` **reset sự tách biệt ấy**, rồi ứng dụng phải đặt lại category-specific defaults nếu cần.

Điểm này cực kỳ quan trọng khi đọc code cấu hình: một thư viện gọi `Locale.setDefault(Locale.X)` có thể phá cấu hình khác biệt giữa ngôn ngữ UI và định dạng số do một component khác thiết lập.

### 3.3. Thay một category không sửa category còn lại

~~~java
Locale.setDefault(Locale.Category.DISPLAY, Locale.ITALY);
~~~

Nếu FORMAT đang `de-DE` thì sau lời gọi vẫn `de-DE`. Tương tự:

~~~java
Locale.setDefault(Locale.Category.FORMAT, Locale.JAPAN);
~~~

sẽ không tự đổi DISPLAY đang `it-IT`. Hãy đọc lại bằng `getDefault(category)` nếu cần chẩn đoán.

### 3.4. Default không phải per-thread

`Locale.setDefault(...)` thay **configuration của cả JVM**, ảnh hưởng những thread khác đang dùng default locale. Không phải `ThreadLocal<Locale>`. Một HTTP request gọi `setDefault(FORMAT, userLocale)` có thể làm request khác **format số sai locale** ngay khi chạy song song.

Nếu cần per-request, hãy **truyền `Locale` trực tiếp** vào formatter hoặc component. Chương trình demo có một thread phụ xác nhận các defaults mới được nhìn thấy từ thread khác, không tạo race vì mọi thay đổi đã hoàn tất trước khi thread phụ chạy.

### 3.5. Nguồn default ban đầu

JVM thiết lập default locale lúc startup dựa trên môi trường host và system properties. Một số hệ thống phân biệt category-specific system properties như `user.language.display` và `user.language.format` cùng các thành phần region/script tương ứng.

Nhưng **không nên tự đọc system properties này rồi suy ra current locale** khi application có thể gọi `setDefault` trong runtime: Javadoc không hứa rằng setter cập nhật ngược những properties ấy. API đáng tin để hỏi trạng thái hiện tại là `Locale.getDefault()` và `Locale.getDefault(category)`. Một số providers/configurations có thể ảnh hưởng dữ liệu hiển thị; đừng hardcode mọi chuỗi định dạng.

## 4. DISPLAY: cách biểu diễn tên locale cho người đọc

Một đối tượng `Locale` có thể cung cấp **mã định danh** hoặc **tên có thể đọc**. Đó là hai kiểu dữ liệu khác nhau.

~~~java
Locale target = Locale.GERMANY;

String code = target.toLanguageTag();
String shown = target.getDisplayName(Locale.FRANCE);
~~~

Đây là đoạn minh họa. `toLanguageTag()` là BCP 47 tag, có thể là `de-DE`, dùng tốt để lưu/trao đổi định danh. `getDisplayName(Locale.FRANCE)` tạo tên hiển thị phù hợp với ngôn ngữ Pháp nếu provider hỗ trợ. **Không dùng display name như ID**: tên có thể đổi theo dữ liệu CLDR/JDK, không nhất thiết duy nhất hoặc ổn định.

### 4.1. Những phương thức dùng DISPLAY mặc định

| API không truyền locale | Vai trò DISPLAY |
| --- | --- |
| `target.getDisplayLanguage()` | Tên ngôn ngữ của target cho người xem, theo default DISPLAY |
| `target.getDisplayCountry()` | Tên quốc gia/vùng của target theo default DISPLAY |
| `target.getDisplayScript()` | Tên hệ chữ viết của target |
| `target.getDisplayVariant()` | Tên biến thể được hỗ trợ |
| `target.getDisplayName()` | Tên hiển thị tổng hợp của target |

Với `Locale.setDefault(DISPLAY, Locale.FRANCE)`:

~~~java
String a = Locale.JAPAN.getDisplayName();
String b = Locale.JAPAN.getDisplayName(Locale.FRANCE);
boolean same = a.equals(b);
~~~

Nếu hai lời gọi được thực hiện cùng provider/configuration, `same` phải true vì overload không tham số dùng default DISPLAY. Bài demo kiểm tra tính chất đó **thay vì in tên tiếng Pháp có thể khác nhau theo dữ liệu bản địa hóa**.

### 4.2. Các overloads nhận locale rõ ràng

~~~java
String english = Locale.GERMANY.getDisplayName(Locale.US);
String french = Locale.GERMANY.getDisplayName(Locale.FRANCE);
String vietnamese = Locale.GERMANY.getDisplayName(
        Locale.forLanguageTag("vi-VN"));
~~~

Chúng trả tên hiển thị theo **locale được truyền**, không cần dựa vào `Locale.Category.DISPLAY` hiện hành. Kết quả strings có thể khác theo JDK locale-data provider hoặc mức hỗ trợ bản dịch. Đừng assert một chuỗi tên tự nhiên cố định trong tests xuyên nhiều runtime nếu không pin data version.

### 4.3. DISPLAY không tự dịch application UI

Một lỗi thường gặp là viết:

~~~java
Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
System.out.println("Save changes");
~~~

Thông điệp literal `"Save changes"` **không tự dịch**. Category DISPLAY chỉ là default để các API được thiết kế cho việc hiển thị tên/nhãn có bản địa hóa tham chiếu tới. Với UI strings, dùng resource bundle/message catalog/translation system phù hợp và chọn locale rõ ràng theo user preference.

Ví dụ resource bundle:

~~~java
Locale userUi = Locale.forLanguageTag("vi-VN");
ResourceBundle messages = ResourceBundle.getBundle(
        "i18n.Messages", userUi);
String buttonLabel = messages.getString("button.save");
~~~

Đây là snippet **không độc lập**, cần import `java.util.ResourceBundle` và các files bundle `i18n/Messages_vi_VN.properties` hoặc fallback phù hợp trên classpath/module. `Locale` không tự tạo các translations. Trong ứng dụng modular, còn phải tuân theo resource encapsulation/service provider rules.

### 4.4. `ResourceBundle.getBundle(baseName)` không tự ưu tiên DISPLAY

**Điểm tinh tế:** overload `ResourceBundle.getBundle("i18n.Messages")` dùng **general default locale** qua `Locale.getDefault()`, **không phải mặc định `Locale.Category.DISPLAY`** theo contract. Do đó đừng suy ra “đã set DISPLAY=fr-FR thì `getBundle(baseName)` chắc chắn tải tiếng Pháp”.

Nếu mục tiêu là ngôn ngữ UI, truyền:

~~~java
Locale ui = Locale.getDefault(Locale.Category.DISPLAY);
ResourceBundle bundle = ResourceBundle.getBundle("i18n.Messages", ui);
~~~

Đây là snippet minh họa; với ứng dụng đa user, dùng `uiLocale` của chính người dùng thay default toàn JVM.

### 4.5. Display text là nội dung có thể thay đổi

Một target locale có thể có nhiều biến thể về tên quốc gia/ngôn ngữ ở các bản dữ liệu Unicode CLDR khác nhau. Vì thế:

- **Database key/URL:** lưu language tag như `"fr-FR"`, không lưu `getDisplayName()`.
- **UI:** render tên hiển thị bằng `getDisplayName(uiLocale)`.
- **Tests:** assert locale tag, mã, invariants hoặc dữ liệu đã pin; không assert mọi cụm từ dịch trên mọi JDK.
- **Search/sorting:** có `Collator` và Unicode normalization riêng; đổi DISPLAY không tự áp locale-aware collation cho mọi comparator.

## 5. FORMAT: quy ước số, tiền tệ, ngày giờ

`Locale.Category.FORMAT` quyết định default locale cho nhiều API định dạng và phân tích dữ liệu.

### 5.1. NumberFormat

~~~java
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
NumberFormat numbers = NumberFormat.getNumberInstance();
String rendered = numbers.format(1234567.89);
~~~

Đây là snippet minh họa, cần import `java.text.NumberFormat`. Java SE Javadoc quy định `NumberFormat.getNumberInstance()` không tham số tương đương việc gọi `getNumberInstance(Locale.getDefault(Locale.Category.FORMAT))`.

Với German formatting thường dùng dấu phẩy làm dấu thập phân và ký hiệu phân nhóm theo dữ liệu locale, nhưng **đừng hardcode ký tự space/dấu phân nhóm cụ thể để assert cross-runtime**, vì CLDR/provider có thể khác.

### 5.2. Currency formatting

~~~java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.GERMANY);
String label = money.format(1234.5);
~~~

Đây là snippet; `Locale.GERMANY` chọn **cách trình bày** và thường chọn currency mặc định gắn với vùng đó nếu provider có dữ liệu. Nhưng **currency giao dịch** nên được xác định độc lập:

~~~java
NumberFormat usdInGermanStyle =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
usdInGermanStyle.setCurrency(Currency.getInstance("USD"));
~~~

Snippet cần imports `java.util.Currency`/`NumberFormat`. Khi giao dịch thực tế tính bằng USD, đừng để `getCurrencyInstance(Locale.GERMANY)` vô tình biến nó thành EUR. Dùng domain currency rõ ràng, quy tắc làm tròn và định dạng phù hợp yêu cầu tài chính.

### 5.3. DateFormat (vẫn được hỗ trợ) và lựa chọn hiện đại

~~~java
DateFormat legacyInterop = DateFormat.getDateInstance(
        DateFormat.MEDIUM);
~~~

Đây là snippet minh họa; `DateFormat.getDateInstance()` không có locale tham chiếu **default FORMAT** và vẫn là API hiện hành. Tuy nhiên đối với code ngày tháng mới, ưu tiên các kiểu `java.time` như `LocalDate`, `ZonedDateTime` cùng `DateTimeFormatter` thay vì `Date`/`Calendar` khi phù hợp.

### 5.4. DateTimeFormatter

~~~java
LocalDate date = LocalDate.of(2026, 11, 4);
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);
String output = formatter.format(date);
~~~

Đây là snippet cần imports `java.time.LocalDate`, `DateTimeFormatter`, `FormatStyle`. Theo Javadoc Java SE 21, `ofLocalizedDate` dùng **default FORMAT locale** tại thời điểm tạo formatter. Nếu FORMAT đang `de-DE`, formatter có `getLocale().equals(Locale.GERMANY)`.

**Điểm quan trọng:** `DateTimeFormatter` là immutable. Nếu sau đó bạn gọi `Locale.setDefault(FORMAT, Locale.JAPAN)`, formatter **đã được tạo** vẫn giữ locale `de-DE`. Một formatter **mới tạo** sau thay đổi dùng `ja-JP`. Chương trình demo kiểm tra cả hai.

Có thể chọn locale rõ ràng bằng:

~~~java
DateTimeFormatter frenchDate = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.FRANCE);
~~~

hoặc `DateTimeFormatter.ofPattern("d MMM uuuu", Locale.FRANCE)` khi muốn pattern cụ thể. **Không dùng `Locale.setDefault` cho mỗi request chỉ để tạo formatter**; truyền user locale trực tiếp.

### 5.5. String.format

~~~java
String localized = String.format("%,.2f", 1234567.89);
String explicit = String.format(Locale.GERMANY, "%,.2f", 1234567.89);
~~~

`String.format` không có Locale parameter dùng default **FORMAT locale**. Với `FORMAT=de-DE`, hai kết quả được kỳ vọng tương ứng như nhau trong cùng JDK. Chú ý `%,.2f` là format specifier: comma là grouping option; đây **không** phải dấu phân nhóm output được đảm bảo luôn là comma. Output thực tế chịu ảnh hưởng locale.

Để xuất data cho giao thức/máy, hãy dùng **định dạng được chuẩn hóa và có contract riêng**, không dựa vào FORMAT đang bị người dùng thay đổi.

### 5.6. Date time zone là một trục khác

`Locale.GERMANY` không tự có nghĩa thời điểm nào cũng được diễn giải theo `Europe/Berlin`; `LocalDate` không có timezone, `Instant` chỉ mô tả thời điểm toàn cầu. Khi format một instant theo múi giờ người dùng, cần `ZoneId` rõ ràng:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
DateTimeFormatter display = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"))
        .withZone(zone);
String shown = display.format(Instant.parse("2026-11-04T12:00:00Z"));
~~~

Đây là snippet minh họa, cần imports `ZoneId`, `Instant` và formatter classes. `Locale` quyết định quy ước trình bày; `ZoneId` quyết định offset/rules của múi giờ. **Không dùng `Locale` để suy ra timezone duy nhất của một người dùng**.

## 6. Khi DISPLAY khác FORMAT: một tình huống chuẩn

Giả sử trước tiên:

~~~java
Locale.setDefault(Locale.US);
Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
~~~

Khi đó:

| Câu hỏi | API | Giá trị |
| --- | --- | --- |
| General default locale? | `Locale.getDefault()` | `en-US` |
| Locale cho display? | `Locale.getDefault(DISPLAY)` | `fr-FR` |
| Locale cho format? | `Locale.getDefault(FORMAT)` | `de-DE` |
| Tên của `Locale.JAPAN` trong display language nào? | `Locale.JAPAN.getDisplayName()` | Theo `fr-FR` |
| Number formatting mặc định nào? | `NumberFormat.getNumberInstance()` | Theo `de-DE` |
| Currency formatting mặc định nào? | `NumberFormat.getCurrencyInstance()` | Theo `de-DE` |
| DateTimeFormatter localized date default? | `DateTimeFormatter.ofLocalizedDate(LONG)` | Theo `de-DE` |
| Resource bundle không truyền locale? | `ResourceBundle.getBundle(baseName)` | Thường dùng **general default `en-US`**, không tự lấy DISPLAY |

Một kiểu kiểm thử đáng tin:

~~~java
boolean uiMatches = Locale.JAPAN.getDisplayName()
        .equals(Locale.JAPAN.getDisplayName(Locale.FRANCE));

boolean numbersMatch = NumberFormat.getNumberInstance()
        .format(1234567.89)
        .equals(NumberFormat.getNumberInstance(Locale.GERMANY)
                .format(1234567.89));
~~~

Đây là snippet minh họa trong context có defaults như trên. Hai booleans đều true, nhưng không cần biết chính xác tên nước Nhật trong tiếng Pháp hay ký tự dấu phân nhóm số của Đức do provider chọn.

### 6.1. Vì sao không in mọi localized string vào stdout cố định?

Locale-data provider của JDK (chẳng hạn CLDR hoặc cấu hình khác) có thể thay đổi tên hiển thị và mẫu định dạng giữa các versions. Oracle JDK 21 cũng cung cấp những locale data providers khác nhau theo platform/configuration. Vì vậy demo in **các thẻ locale cố định cùng các invariants so sánh overload không-đối-số với overload explicit**. Như vậy test tập trung đúng contract DISPLAY/FORMAT và ổn định hơn.

### 6.2. Hai categories không tự phản ánh preference của từng người dùng

Nếu phục vụ 10.000 người dùng, server có thể có chỉ một general/DISPLAY/FORMAT defaults. Không có mapping tự động tới cookies, HTTP `Accept-Language`, user profile hoặc mobile device locale. Muốn cá nhân hóa, phải đọc preference và truyền locale vào phần tạo tên, dịch, format.

## 7. Kiến trúc ứng dụng đa người dùng: ưu tiên explicit locale

### 7.1. Không đổi JVM default trong mỗi request

**Phản ví dụ:**

~~~java
// Không nên thực hiện trong request handler trên server nhiều người dùng:
Locale.setDefault(Locale.Category.FORMAT, userLocale);
String invoice = NumberFormat.getCurrencyInstance().format(total);
~~~

Đây là pseudocode Java; `userLocale` và `total` do ứng dụng cung cấp. Nếu hai request chạy đồng thời, request A có thể set German, request B set US, request A sau đó format theo US ngoài ý muốn. `Locale.setDefault` không có scope theo thread hoặc HTTP request.

**Cách phù hợp:**

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(userLocale);
String invoice = formatter.format(total);
~~~

Snippet minh họa; mỗi call dùng locale cụ thể, không sửa global defaults. `NumberFormat` có mutable state và không nên chia sẻ một instance không đồng bộ cho nhiều threads; tạo instance theo scope, clone/cấu hình phù hợp hoặc bảo vệ bằng synchronization nếu bắt buộc.

### 7.2. Tách hai preferences trong profile

Một profile có thể lưu:

~~~json
{
  "uiLocale": "vi-VN",
  "formatLocale": "en-US",
  "timeZone": "Asia/Ho_Chi_Minh",
  "currencyCode": "USD"
}
~~~

Đây là JSON minh họa domain data, **không** phải runtime config hay Java class. Mỗi field có trách nhiệm riêng:

- `uiLocale` để chọn translation bundle và `getDisplayName(uiLocale)`.
- `formatLocale` để tạo `NumberFormat`/`DateTimeFormatter`.
- `timeZone` để diễn giải/trình bày thời điểm thành local time.
- `currencyCode` là loại tiền nghiệp vụ, không suy ra hoàn toàn từ format locale.

Trong cùng một người dùng, các giá trị có thể **khác vùng** mà vẫn hợp lý.

### 7.3. Truyền theo phương thức

~~~java
static String formatTotal(
        java.math.BigDecimal total,
        java.util.Currency currency,
        Locale formatLocale) {
    NumberFormat number = NumberFormat.getCurrencyInstance(formatLocale);
    number.setCurrency(currency);
    return number.format(total);
}
~~~

Đây là method minh họa; cần imports `NumberFormat` và `Locale` cùng caller/domain policy về rounding/fraction digits. Không đổi `Locale.getDefault`.

### 7.4. Context object hoặc request-scoped service

Khi có nhiều methods cần locale, có thể đóng gói:

~~~java
record PresentationContext(
        Locale uiLocale,
        Locale formatLocale,
        ZoneId timeZone) {}
~~~

Đây là fragment minh họa, cần `ZoneId`/`Locale` imports; application layer truyền context tới formatter/UI renderer. Không dùng một mutable global để truyền sở thích người dùng giữa tầng HTTP, service và persistence.

### 7.5. Trong desktop app đơn người dùng thì sao?

Nếu ứng dụng desktop chỉ có một người dùng và muốn thiết lập defaults chung khi startup, việc gọi `Locale.setDefault(DISPLAY, ui)` và `setDefault(FORMAT, fmt)` **có thể chấp nhận được** nếu toàn bộ ứng dụng kiểm soát lifecycle. Tuy nhiên nên đặt **một lần tại initialization** và hiểu một số components có thể đã cache locale/formatter trước khi thay defaults.

Ngay cả trong desktop app, explicit locale vẫn giúp library code dễ test và tránh hidden dependencies.

## 8. Thiết kế phù hợp Unicode và dữ liệu quốc tế hóa

### 8.1. Unicode không thay đổi do category

Java `String` biểu diễn Unicode text; `DISPLAY` hay `FORMAT` không quyết định encoding file. Với I/O bytes, chọn charset rõ:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là snippet minh họa; cần imports `Files`, `StandardCharsets` và biến `path`. Cách decode UTF-8 không được chọn bởi `Locale.Category.FORMAT`, cũng không thay đổi khi DISPLAY từ French sang Vietnamese.

### 8.2. Case conversion có locale

`String.toLowerCase()` không có tham số sử dụng **default locale chung** theo contract của nó, và một số ngôn ngữ như Turkish có quy tắc case khác tiếng Anh. Đừng tự suy ra mọi phương thức liên quan ngôn ngữ đều đọc DISPLAY.

Với **identifier/ASCII protocol tokens** không có mục đích ngôn ngữ tự nhiên, dùng:

~~~java
String normalizedKey = input.toLowerCase(Locale.ROOT);
~~~

Đây là snippet minh họa, `input` do ứng dụng cung cấp; tùy giao thức, cần validate ASCII/Unicode normalization riêng. Với tên người dùng hoặc văn bản tự nhiên, có thể cần locale cụ thể, Unicode case folding và normalization đúng bài toán.

### 8.3. Collation và so sánh chuỗi

`String.compareTo` so thứ tự code units Unicode, không tự đổi sang linguistic sorting chỉ vì DISPLAY/FORMAT được cấu hình. Để sắp xếp nhãn hiển thị theo ngôn ngữ, tạo `Collator` cho một locale cụ thể:

~~~java
Collator collator = Collator.getInstance(uiLocale);
int comparison = collator.compare("a", "b");
~~~

Đây là snippet cần `java.text.Collator` và biến `uiLocale`. `Collator` là đối tượng có thể thay cấu hình; không chia sẻ mutable instance vô kiểm soát giữa threads. Nếu cần sorting ổn định qua các versions/providers, cần pin comparator strategy/data; locale-sensitive collation có thể thay đổi theo CLDR version.

### 8.4. Normalization không phải locale

Unicode normalization (NFC/NFD) dùng `java.text.Normalizer` và quy tắc Unicode, không phải “DISPLAY normalization” hoặc “FORMAT normalization”. Hai chuỗi có cùng hình hiển thị có thể khác sequence code points. Nếu ứng dụng làm search/index, cần chính sách normalization/case folding riêng, không chỉ đổi locale.

### 8.5. Language tag là định danh, không phải display label

`Locale.forLanguageTag("vi-VN")` cho một locale; `toLanguageTag()` giúp lưu trao đổi dạng BCP 47. Không lưu `locale.getDisplayName()` vào database làm key vì text được localized và có thể đổi theo phiên bản dữ liệu.

## 9. Vòng đời formatter và tác động khi đổi defaults

### 9.1. Factory đọc default tại lúc tạo

Khi gọi:

~~~java
DateTimeFormatter german = DateTimeFormatter.ofLocalizedDate(
        FormatStyle.LONG);
~~~

nếu FORMAT lúc đó là `de-DE`, đối tượng mới tạo có locale German. Sau khi gọi `setDefault(FORMAT, Locale.JAPAN)`:

~~~java
DateTimeFormatter japanese = DateTimeFormatter.ofLocalizedDate(
        FormatStyle.LONG);
~~~

`japanese` dùng `ja-JP`, còn `german` **vẫn giữ locale cũ**. Đây là immutable formatter behavior, không phải dynamic view của mutable global default. Chương trình Java 21 phần 12 kiểm chứng.

### 9.2. DateFormat và NumberFormat có state riêng

`java.text.NumberFormat`/`DateFormat` là các formatter objects có thể cấu hình và **không được bảo đảm thread-safe** khi chia sẻ một instance mutable. Khi user format locale thay đổi, những instances đã tạo từ locale cũ không tự được cập nhật thành locale mới. Nếu cần format mới, tạo formatter thích hợp hoặc explicit reconfiguration.

Với `java.time.format.DateTimeFormatter`, instances immutable và thread-safe theo contract, nên một formatter explicit locale có thể được tái sử dụng rộng hơn, với lưu ý cache keys phải bao gồm locale và pattern khi có nhiều preferences.

### 9.3. Khi nào cần khôi phục default trong tests?

Nếu test buộc phải gọi `Locale.setDefault`, lưu **cả ba** giá trị trước:

~~~java
Locale oldGeneral = Locale.getDefault();
Locale oldDisplay = Locale.getDefault(Locale.Category.DISPLAY);
Locale oldFormat = Locale.getDefault(Locale.Category.FORMAT);
~~~

Sau test, trong `finally`:

~~~java
Locale.setDefault(oldGeneral);
Locale.setDefault(Locale.Category.DISPLAY, oldDisplay);
Locale.setDefault(Locale.Category.FORMAT, oldFormat);
~~~

Tại sao không chỉ `setDefault(oldGeneral)`? Vì `setDefault(Locale)` reset **cả DISPLAY và FORMAT** về general, làm mất sự khác biệt ban đầu. Chương trình đầy đủ dùng đúng thứ tự phục hồi này.

**Quan trọng:** ngay cả khi có `finally`, việc đổi default vẫn ảnh hưởng các threads khác **trong khoảng thời gian test chạy**. Không chạy các tests thay default song song trên cùng JVM; ưu tiên explicit locale để không cần global mutation, hoặc fork một process test riêng nếu cần kiểm tra chính cơ chế defaults.

### 9.4. Exception và validation của category setters

`Locale.getDefault(null)` và `Locale.setDefault(category, null)` không hợp lệ, có thể ném `NullPointerException` theo contract. Không dùng null để nói “dùng default” đối với các overload yêu cầu non-null. Hãy chủ động lấy `Locale.getDefault(category)` nếu muốn một locale tại thời điểm đó.

## 10. Những phương thức không tự dùng category như bạn nghĩ

Bảng sau nhấn mạnh rằng **phải xem contract của từng API**, không suy từ tên method:

| API | Locale được dùng khi không truyền explicit locale | Cách tránh mơ hồ |
| --- | --- | --- |
| `Locale.getDefault()` | General default | Dùng `getDefault(Category)` khi cần category |
| `Locale.getDisplayName()` | Default DISPLAY | `getDisplayName(uiLocale)` |
| `Locale.getDisplayLanguage()` | Default DISPLAY | `getDisplayLanguage(uiLocale)` |
| `NumberFormat.getNumberInstance()` | Default FORMAT | `getNumberInstance(formatLocale)` |
| `NumberFormat.getCurrencyInstance()` | Default FORMAT | `getCurrencyInstance(formatLocale)` |
| `DateFormat.getDateInstance(...)` | Default FORMAT | Overload nhận `Locale` |
| `DateTimeFormatter.ofLocalizedDate(...)` | Default FORMAT lúc tạo | `withLocale(formatLocale)` |
| `String.format(format, args)` | Default FORMAT | `String.format(formatLocale, format, args)` |
| `ResourceBundle.getBundle(baseName)` | General default, không phải DISPLAY | `getBundle(baseName, uiLocale)` |
| `String.toLowerCase()` | Default locale chung theo contract | `toLowerCase(Locale.ROOT)` cho non-linguistic keys |
| `LocalDate.toString()` | ISO-style date representation, không theo FORMAT | `DateTimeFormatter` explicit khi hiển thị cho user |
| `Locale.toLanguageTag()` | Language tag định danh, không phụ thuộc DISPLAY | Dùng để lưu tag, không phải display name |

Không có quy tắc “mọi API `String`/`java.util` đều dùng DISPLAY” hoặc “mọi API `java.time` đều dùng FORMAT”. Ví dụ `LocalDate.toString()` không cố định theo locale người dùng; `DateTimeFormatter` localized mới có lựa chọn locale.

## 11. Ứng dụng thực tế: UI tiếng Pháp, báo cáo số kiểu Đức

Một báo cáo kế toán có:

- Ngôn ngữ UI: `fr-FR`.
- Định dạng số: `de-DE`.
- Currency giao dịch: `USD`.
- Múi giờ: `Asia/Ho_Chi_Minh`.

Một thiết kế đúng:

~~~java
Locale uiLocale = Locale.forLanguageTag("fr-FR");
Locale formatLocale = Locale.forLanguageTag("de-DE");
Currency currency = Currency.getInstance("USD");
ZoneId timeZone = ZoneId.of("Asia/Ho_Chi_Minh");

String countryName = Locale.JAPAN.getDisplayCountry(uiLocale);
NumberFormat price = NumberFormat.getCurrencyInstance(formatLocale);
price.setCurrency(currency);
String amountText = price.format(1234.5);
~~~

Đây là snippet minh họa; imports cần có. Cách làm này **không đổi bất kỳ default locale của JVM** nên dễ sử dụng trong server nhiều users.

### 11.1. Định dạng để hiển thị và lưu dữ liệu là hai bài toán

Cơ sở dữ liệu nên lưu một số tiền dưới kiểu decimal/số phù hợp, không lưu văn bản đã format với dấu phân nhóm. Nếu người dùng gửi `"1.234,50"`, cần parse theo đúng `formatLocale` và validate chặt chẽ; không được gọi `Double.parseDouble` như thể mọi locale đều dùng dấu chấm thập phân.

Ngược lại, khi gửi JSON hay CSV machine-to-machine, cần schema/escaping/canonical numeric representation; **không dùng NumberFormat dựa vào default FORMAT đang thay đổi**. Định dạng dành cho người đọc ở presentation layer.

### 11.2. Currency không tự đồng nhất với locale vùng

`de-DE` có thể dẫn tới presentation EUR theo mặc định của formatter, nhưng giao dịch thực tế có thể tính USD, VND hay JPY. Tách code tiền và cách hiển thị là bắt buộc nếu domain cần tính chính xác. Tương tự, định dạng số không xác định thuế, tỷ giá hoặc rounding policy nghiệp vụ.

### 11.3. Ngày/giờ phải có timezone nếu chứa thời điểm

Một `LocalDate` là ngày lịch không có time zone; `Instant` là thời điểm. Nếu báo cáo “đơn hàng được tạo lúc…” theo timezone người dùng, nên chuyển `Instant` sang `ZonedDateTime` theo `ZoneId` rồi format theo `formatLocale`. Không suy từ `vi-VN` rằng user nhất định sống ở một múi giờ duy nhất.

## 12. Ví dụ Java 21 hoàn chỉnh: tách DISPLAY và FORMAT, kiểm chứng, khôi phục

Chương trình `demo.LocaleCategoryExample` thực hiện **tất cả thao tác trong một process Java 21**, không cần dependencies, locale files hoặc external services:

1. Lưu general/DISPLAY/FORMAT defaults hiện có để khôi phục trong `finally`.
2. Gọi `Locale.setDefault(Locale.US)` và kiểm tra **cả hai category** được đồng bộ về `en-US`.
3. Đặt DISPLAY=`fr-FR`, FORMAT=`de-DE`; in ba locale tags.
4. Kiểm tra `getDisplayName()/getDisplayLanguage()` không tham số tương đương overload explicit `Locale.FRANCE`.
5. Kiểm tra `NumberFormat` (number/currency), `String.format` và `DateFormat` không truyền locale tương đương overload explicit `Locale.GERMANY`.
6. Kiểm tra `DateTimeFormatter.ofLocalizedDate` tạo ra locale `de-DE`, format tương đương explicit `withLocale(Locale.GERMANY)`.
7. Đổi DISPLAY sang `it-IT`, xác minh general/FORMAT không đổi và display names dùng Italian.
8. Đổi FORMAT sang `ja-JP`, xác minh general/DISPLAY không đổi, formatter cũ vẫn German và formatter mới Japanese.
9. Tạo một thread phụ để chứng minh default categories là JVM-wide, không phải request-local/thread-local.
10. Xác minh một formatter được tạo với explicit `Locale.US` không bị đổi nghĩa chỉ vì FORMAT mặc định hiện là Japanese.
11. Luôn khôi phục **đúng cả ba defaults** trong `finally`; in kiểm tra restored.
12. **Không in những chuỗi localized tự nhiên** như tên đất nước hoặc tên tháng, vì chúng có thể khác theo locale-data provider. Chỉ in tags cố định và boolean invariants đã được kiểm thử.

**Lưu ý chạy:** chương trình này **cố ý thay JVM global locale defaults trong lúc chạy** để dạy đúng cơ chế. Chạy nó như **chương trình demo độc lập**, không copy phần đổi defaults vào HTTP request handler của production service. Trong test suite, không chạy song song với tests khác cùng JVM mà dựa vào default locale.

### 12.1. Mã nguồn đầy đủ

Tạo file `src/main/java/demo/LocaleCategoryExample.java`:

~~~java
package demo;

import java.text.DateFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LocaleCategoryExample {
    private LocaleCategoryExample() {}

    public static void main(String[] args) throws InterruptedException {
        Locale originalGeneral = Locale.getDefault();
        Locale originalDisplay = Locale.getDefault(Locale.Category.DISPLAY);
        Locale originalFormat = Locale.getDefault(Locale.Category.FORMAT);

        try {
            Locale.setDefault(Locale.US);
            System.out.println("setDefault-updates-both="
                    + (Locale.getDefault(Locale.Category.DISPLAY).equals(Locale.US)
                    && Locale.getDefault(Locale.Category.FORMAT).equals(Locale.US)));

            Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            System.out.println("general=" + Locale.getDefault().toLanguageTag());
            System.out.println("display="
                    + Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("format="
                    + Locale.getDefault(Locale.Category.FORMAT).toLanguageTag());

            System.out.println("display-name-uses-fr="
                    + Locale.JAPAN.getDisplayName()
                            .equals(Locale.JAPAN.getDisplayName(Locale.FRANCE)));
            System.out.println("display-language-uses-fr="
                    + Locale.GERMANY.getDisplayLanguage()
                            .equals(Locale.GERMANY.getDisplayLanguage(Locale.FRANCE)));

            double amount = 1234567.89;
            System.out.println("number-uses-de="
                    + NumberFormat.getNumberInstance().format(amount)
                            .equals(NumberFormat.getNumberInstance(Locale.GERMANY)
                                    .format(amount)));
            System.out.println("currency-uses-de="
                    + NumberFormat.getCurrencyInstance().format(amount)
                            .equals(NumberFormat.getCurrencyInstance(Locale.GERMANY)
                                    .format(amount)));
            System.out.println("string-format-uses-de="
                    + String.format("%,.2f", amount)
                            .equals(String.format(Locale.GERMANY, "%,.2f", amount)));

            Date fixedDate = Date.from(Instant.parse("2026-11-04T12:00:00Z"));
            System.out.println("dateformat-uses-de="
                    + DateFormat.getDateInstance(DateFormat.MEDIUM)
                            .format(fixedDate)
                            .equals(DateFormat.getDateInstance(
                                    DateFormat.MEDIUM, Locale.GERMANY)
                                    .format(fixedDate)));

            LocalDate calendarDate = LocalDate.of(2026, 11, 4);
            DateTimeFormatter createdInDe =
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);
            System.out.println("datetimeformatter-locale="
                    + createdInDe.getLocale().toLanguageTag());
            System.out.println("datetimeformatter-uses-de="
                    + createdInDe.format(calendarDate)
                            .equals(DateTimeFormatter.ofLocalizedDate(
                                    FormatStyle.LONG).withLocale(Locale.GERMANY)
                                    .format(calendarDate)));

            Locale.setDefault(Locale.Category.DISPLAY, Locale.ITALY);
            System.out.println("changing-display-keeps-general-and-format="
                    + (Locale.getDefault().equals(Locale.US)
                    && Locale.getDefault(Locale.Category.FORMAT)
                            .equals(Locale.GERMANY)));
            System.out.println("display-name-now-uses-it="
                    + Locale.JAPAN.getDisplayName()
                            .equals(Locale.JAPAN.getDisplayName(Locale.ITALY)));

            Locale.setDefault(Locale.Category.FORMAT, Locale.JAPAN);
            System.out.println("changing-format-keeps-general-and-display="
                    + (Locale.getDefault().equals(Locale.US)
                    && Locale.getDefault(Locale.Category.DISPLAY)
                            .equals(Locale.ITALY)));
            System.out.println("existing-formatter-keeps-de="
                    + createdInDe.getLocale().equals(Locale.GERMANY));
            System.out.println("new-formatter-uses-ja="
                    + DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                            .getLocale().equals(Locale.JAPAN));

            AtomicBoolean fromAnotherThread = new AtomicBoolean();
            Thread reader = new Thread(() -> fromAnotherThread.set(
                    Locale.getDefault(Locale.Category.DISPLAY).equals(Locale.ITALY)
                    && Locale.getDefault(Locale.Category.FORMAT)
                            .equals(Locale.JAPAN)));
            reader.start();
            reader.join();
            System.out.println("defaults-visible-across-threads="
                    + fromAnotherThread.get());

            System.out.println("explicit-formatter-ignores-default="
                    + NumberFormat.getNumberInstance(Locale.US).format(amount)
                            .equals(String.format(Locale.US, "%,.2f", amount)));
        } finally {
            Locale.setDefault(originalGeneral);
            Locale.setDefault(Locale.Category.DISPLAY, originalDisplay);
            Locale.setDefault(Locale.Category.FORMAT, originalFormat);
        }

        System.out.println("original-locales-restored="
                + (Locale.getDefault().equals(originalGeneral)
                && Locale.getDefault(Locale.Category.DISPLAY)
                        .equals(originalDisplay)
                && Locale.getDefault(Locale.Category.FORMAT)
                        .equals(originalFormat)));
    }
}
~~~

### 12.2. Biên dịch và chạy

Từ thư mục chứa `src`, sử dụng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/LocaleCategoryExample.java
java -cp out demo.LocaleCategoryExample
~~~

Không có dependency thứ ba và không cần download dữ liệu. Chương trình dùng các classes từ Java SE modules có sẵn. `-Xlint:all` giúp hiển thị cảnh báo nếu có; bản mã từ chính Markdown đã được biên dịch sạch trong môi trường kiểm thử.

### 12.3. Stdout chính xác đã kiểm thử

~~~text
setDefault-updates-both=true
general=en-US
display=fr-FR
format=de-DE
display-name-uses-fr=true
display-language-uses-fr=true
number-uses-de=true
currency-uses-de=true
string-format-uses-de=true
dateformat-uses-de=true
datetimeformatter-locale=de-DE
datetimeformatter-uses-de=true
changing-display-keeps-general-and-format=true
display-name-now-uses-it=true
changing-format-keeps-general-and-display=true
existing-formatter-keeps-de=true
new-formatter-uses-ja=true
defaults-visible-across-threads=true
explicit-formatter-ignores-default=true
original-locales-restored=true
~~~

**Đây là 20 dòng stdout**. Số dòng được kiểm tra theo bản chạy thật của JDK 21, không suy ra từ một bản code riêng.

### 12.4. Đọc các assertions

| Dòng | Điều chứng minh |
| --- | --- |
| `setDefault-updates-both=true` | `setDefault(Locale)` đặt lại cả DISPLAY và FORMAT |
| `general=en-US` | General default vẫn là US khi đặt riêng category |
| `display=fr-FR` | DISPLAY có thể khác general |
| `format=de-DE` | FORMAT có thể khác DISPLAY |
| `display-name-uses-fr=true` | `Locale.getDisplayName()` dùng default DISPLAY |
| `display-language-uses-fr=true` | `getDisplayLanguage()` cũng dùng default DISPLAY |
| `number-uses-de=true` | NumberFormat không truyền locale dùng FORMAT |
| `currency-uses-de=true` | Currency formatter không truyền locale dùng FORMAT |
| `string-format-uses-de=true` | String.format không truyền locale dùng FORMAT |
| `dateformat-uses-de=true` | DateFormat không truyền locale dùng FORMAT |
| `datetimeformatter-locale=de-DE` | DateTimeFormatter mới tạo dùng FORMAT hiện hành |
| `datetimeformatter-uses-de=true` | Localized date output tương đương explicit German |
| `changing-display-keeps-general-and-format=true` | Đặt DISPLAY không thay general/FORMAT |
| `display-name-now-uses-it=true` | DISPLAY được cập nhật độc lập |
| `changing-format-keeps-general-and-display=true` | Đặt FORMAT không thay general/DISPLAY |
| `existing-formatter-keeps-de=true` | Formatter cũ immutable, không đổi locale |
| `new-formatter-uses-ja=true` | Formatter mới đọc FORMAT hiện tại |
| `defaults-visible-across-threads=true` | Locale defaults là JVM-wide |
| `explicit-formatter-ignores-default=true` | Explicit Locale.US được tôn trọng |
| `original-locales-restored=true` | General/DISPLAY/FORMAT đều được phục hồi |

### 12.5. Tại sao không in tên nước Nhật tiếng Pháp?

Kết quả text tự nhiên có thể thay đổi khi JDK cập nhật CLDR/localization data. Bài học kiểm tra **quan hệ giữa overload implicit và explicit locale** để thử đúng contract, thay vì biến chính tả một tên địa danh thành assertion bất biến giữa mọi runtime.

### 12.6. Vì sao ngày giả định không phụ thuộc thời gian hiện tại?

`fixedDate` tạo từ một `Instant` cố định, `calendarDate` là một `LocalDate` cố định. Chương trình không gọi `LocalDate.now()` hay `new Date()` dựa vào clock. Phép so sánh DateFormat cùng JVM dùng cùng timezone mặc định và chỉ so locale; DateTimeFormatter dùng LocalDate không có timezone, nên kết quả deterministic về semantics.

### 12.7. Vì sao demo tạo một thread?

Đây là phép chứng minh rằng việc đổi default category của JVM **không bị giới hạn trong thread đã gọi setter**. Thread phụ chỉ đọc sau khi main đã cập nhật, không có concurrent mutation, nên không phụ thuộc race của scheduler. Trong server thật, việc thay default trong mỗi request mới chính là điều cần tránh.

## 13. Sai lầm phổ biến và sửa đúng cách

| Sai lầm | Điều gì sai | Cách thay |
| --- | --- | --- |
| Coi DISPLAY và FORMAT là hai tên của cùng một locale | Có thể khác nhau | Đọc `getDefault(DISPLAY)` và `getDefault(FORMAT)` |
| Nghĩ `Locale.getDefault()` luôn bằng hai category | General có thể khác khi set category riêng | Hỏi đúng overload theo nhu cầu |
| `setDefault(Locale.US)` chỉ đổi general | Thực tế reset cả hai categories | Dùng `setDefault(Category,...)` nếu cố ý đổi một category |
| `setDefault(FORMAT, ...)` chỉ ảnh hưởng thread hiện tại | Nó JVM-wide | Truyền explicit locale per request |
| Dùng DISPLAY để format tiền/ngày | Sai contract | Dùng FORMAT hoặc explicit formatLocale |
| Dùng FORMAT để gọi `getDisplayName()` | Sai contract | Dùng DISPLAY hoặc explicit uiLocale |
| Nghĩ DISPLAY tự dịch UI literal | Không | Translation resource/message catalog |
| Nghĩ `ResourceBundle.getBundle(baseName)` tự dùng DISPLAY | Nó dùng general default | Truyền uiLocale rõ ràng |
| Dùng `Locale.getDisplayName()` làm database key | Localized text có thể đổi | Dùng `toLanguageTag()` |
| Gọi `Locale.setDefault` trong HTTP handler | Race giữa requests | Explicit locale, request context |
| Cho rằng DateTimeFormatter cũ tự đổi locale khi FORMAT đổi | Formatter immutable | Tạo formatter mới hoặc `withLocale` |
| Chia sẻ một `NumberFormat` mutable giữa threads | Không bảo đảm thread-safe | Instance theo scope hoặc synchronization |
| Gán `formatLocale` làm currency giao dịch | Cách trình bày không phải business currency | `Currency`/ISO currency code riêng |
| Gán locale = timezone | Region không xác định ZoneId | Dùng `ZoneId` explicit |
| Dùng `NumberFormat` ngầm để lưu số trong protocol | Locale có dấu riêng | Canonical serialization |
| Assert tên hiển thị cố định trên mọi JDK | CLDR/provider có thể đổi | Assert invariants/tags |
| Khôi phục tests chỉ với `setDefault(originalGeneral)` | Mất category originals | Lưu và phục hồi cả ba |
| Thay default trong các parallel tests | Tests tác động lẫn nhau | Fork JVM hoặc explicit locale |
| Suy mọi API string dùng DISPLAY | Mỗi API có contract riêng | Xem Javadoc, truyền locale |
| Dùng default case-folding cho identifier | Turkish/Unicode case rules có thể khác | `Locale.ROOT` hoặc protocol-specific rules |
| Nhầm locale với charset | Unicode/UTF-8 là vấn đề encoding riêng | Chọn Charset rõ khi I/O |
| Xử lý `Accept-Language` thành Locale duy nhất mà không validate | Không chắc app hỗ trợ | Negotiation/fallback theo allowlist |
| Coi `Locale.forLanguageTag` đảm bảo bản dịch UI có sẵn | Locale object không phải resource bundle | Kiểm tra resources/providers |

## 14. Bài tập có lời giải

**Câu 1.** `Locale.Category` được giới thiệu từ Java nào?  
**Đáp án:** Java 7, và API vẫn đang được hỗ trợ trên các JDK hiện đại.

**Câu 2.** Hai category là gì?  
**Đáp án:** DISPLAY cho hiển thị tên thông tin UI, FORMAT cho định dạng ngày/số/tiền tệ.

**Câu 3.** Nếu DISPLAY là `fr-FR` nhưng FORMAT là `de-DE`, `Locale.JAPAN.getDisplayName()` dùng gì?  
**Đáp án:** `fr-FR`, vì không truyền locale nên dùng default DISPLAY.

**Câu 4.** `NumberFormat.getNumberInstance()` lúc ấy dùng gì?  
**Đáp án:** `de-DE` vì nó dùng default FORMAT.

**Câu 5.** `DateTimeFormatter.ofLocalizedDate(LONG)` có dùng FORMAT không?  
**Đáp án:** Có, locale được lấy từ default FORMAT khi tạo formatter.

**Câu 6.** `Locale.getDefault()` có bắt buộc bằng DISPLAY không?  
**Đáp án:** Không. General default có thể khác khi set category riêng.

**Câu 7.** `Locale.setDefault(Locale.US)` có đổi category defaults?  
**Đáp án:** Có. Nó đặt lại mọi default category thành US.

**Câu 8.** `setDefault(DISPLAY, Locale.ITALY)` có sửa FORMAT?  
**Đáp án:** Không, category setter chỉ sửa category được yêu cầu.

**Câu 9.** `Locale.setDefault(FORMAT, userLocale)` có phù hợp multi-user HTTP server không?  
**Đáp án:** Không, vì thay đổi JVM-wide. Truyền `userLocale` trực tiếp cho formatter.

**Câu 10.** `ResourceBundle.getBundle(baseName)` mặc định dùng DISPLAY?  
**Đáp án:** Không; overload không truyền locale dùng general default. Cần `getBundle(baseName, uiLocale)`.

**Câu 11.** Category DISPLAY tự dịch chuỗi `"Save"` sang tiếng Việt không?  
**Đáp án:** Không. Cần translation resource phù hợp.

**Câu 12.** Locale `de-DE` có bắt buộc số tiền là EUR?  
**Đáp án:** Không. Currency giao dịch là business data riêng, nên khai báo `Currency` rõ.

**Câu 13.** Locale `vi-VN` có tự đặt timezone của ứng dụng?  
**Đáp án:** Không. Timezone là `ZoneId`, nên giữ riêng.

**Câu 14.** `Locale.forLanguageTag("vi-VN")` có tự tạo các resource bundles tiếng Việt không?  
**Đáp án:** Không. Nó tạo Locale, resources phải do ứng dụng hoặc provider cung cấp.

**Câu 15.** Tại sao không dùng `getDisplayName()` làm ID?  
**Đáp án:** Text bản địa hóa có thể thay đổi theo locale và dữ liệu provider; dùng `toLanguageTag()`.

**Câu 16.** Cần làm gì để format số per-request an toàn?  
**Đáp án:** `NumberFormat.getNumberInstance(formatLocale)`, không sửa global FORMAT.

**Câu 17.** Formatter localized date đã tạo có tự đổi sang locale mới khi đổi default FORMAT?  
**Đáp án:** Không, `DateTimeFormatter` immutable. Tạo formatter mới hoặc explicit `withLocale`.

**Câu 18.** Test thay locale mặc định cần lưu những gì?  
**Đáp án:** General, DISPLAY và FORMAT, rồi khôi phục đủ ba trong `finally`.

**Câu 19.** Dùng `Locale.ROOT` trong `toLowerCase` khi nào?  
**Đáp án:** Với non-linguistic machine keys/identifiers khi contract đòi normalization không phụ thuộc ngôn ngữ người dùng; vẫn cần xét Unicode/protocol riêng.

**Câu 20.** Có thể parse số `"1.234,50"` bằng `Double.parseDouble` một cách tổng quát không?  
**Đáp án:** Không. Cần parser theo format locale và validation, không nhầm human formatting với machine number syntax.

**Câu 21.** `java.text.DateFormat` có bị xóa khỏi Java 21 không?  
**Đáp án:** Không. Nó vẫn là API hiện hành; với code ngày giờ mới có thể ưu tiên `java.time`.

**Câu 22.** Nếu tên ngôn ngữ hiển thị khác nhau giữa hai JDK, category API có sai không?  
**Đáp án:** Không nhất thiết; CLDR/locale-data providers và versions có thể cung cấp text khác. Test các contract/invariants thay vì giả định bản dịch cố định.

**Câu 23.** Vì sao locale, timezone, currency nên là những fields tách biệt?  
**Đáp án:** Chúng mô tả những khía cạnh khác nhau: ngôn ngữ UI, cách format, thời điểm địa phương và đơn vị tiền nghiệp vụ.

**Câu 24.** Một thread khác có thấy thay đổi `Locale.setDefault` không?  
**Đáp án:** Có, defaults thuộc JVM, không thuộc một thread; vì vậy không đổi trong request song song.

## 15. Checklist triển khai

- [ ] Xác định rõ sở thích **ngôn ngữ UI** và **định dạng số/ngày** là độc lập.
- [ ] Biết `Locale.Category.DISPLAY` và `FORMAT` từ Java 7, còn được hỗ trợ.
- [ ] Dùng `getDefault(Category)` khi cần category cụ thể; không tự lấy general rồi đoán.
- [ ] Hiểu `setDefault(Locale)` đồng thời reset DISPLAY/FORMAT.
- [ ] Chỉ gọi `setDefault(Category,...)` khi thực sự muốn đổi default của JVM.
- [ ] Không dùng default setters trong per-user/per-request handler.
- [ ] Dùng `getDisplayName(uiLocale)` hoặc overloads tương ứng cho tên UI.
- [ ] Dùng resource catalog có ngôn ngữ explicit cho application messages.
- [ ] Nhớ `ResourceBundle.getBundle(baseName)` dùng general default, không bảo đảm dùng DISPLAY.
- [ ] Dùng `NumberFormat.getNumberInstance(formatLocale)` cho số cần hiển thị.
- [ ] Dùng `getCurrencyInstance(formatLocale)` kèm currency code của nghiệp vụ.
- [ ] Dùng `DateTimeFormatter.withLocale(formatLocale)` cho ngày/giờ hiển thị.
- [ ] Dùng `ZoneId` explicit cho instant-to-local-time presentation.
- [ ] Không nhầm locale với charset/UTF-8 hoặc Unicode normalization.
- [ ] Lưu BCP 47 tag thay vì localized display names.
- [ ] Nếu xử lý user-supplied language tags, kiểm tra supported locales/fallback.
- [ ] Nếu dùng `Collator`, chọn uiLocale phù hợp và cân nhắc provider/version.
- [ ] Khi format/parsing user-facing strings, sử dụng cùng locale policy và validation.
- [ ] Khi serialize dữ liệu máy, sử dụng canonical schema, không dùng FORMAT default.
- [ ] Nếu muốn đổi locale của một formatter đã tạo, tạo instance mới hoặc withLocale.
- [ ] Không share mutable `NumberFormat/DateFormat` tùy tiện giữa threads.
- [ ] Trong tests thay defaults, lưu và khôi phục **general/DISPLAY/FORMAT** trong finally.
- [ ] Không chạy tests thay default song song trong cùng JVM.
- [ ] Khi test localized strings, pin provider/version hoặc assert category invariants.
- [ ] Trong code mới, ưu tiên `java.time` cho ngày giờ và truyền locale cụ thể.
- [ ] Chỉ dùng các API hiện hành, không dựa vào cách triển khai lỗi thời.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 21 — Locale.Category](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Category.html): hai category DISPLAY và FORMAT, giới thiệu từ Java 7.
- [Oracle Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `getDefault`/`setDefault` có hoặc không có category, `getDisplayName`, `forLanguageTag` và language tags.
- [Oracle Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): default FORMAT, overloads nhận locale, formatting numbers và currencies.
- [Oracle Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): localized dates dùng default FORMAT, explicit `withLocale`, immutable formatter.
- [Oracle Java SE 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html): date formatting contract và overloads theo locale.
- [Oracle Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): bundle lookup với general default và explicit target locale.
- [Oracle Java SE 21 — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): đơn vị tiền tệ và mã tiền.
- [Oracle Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): overloads `format`, case conversion có Locale.
- [Oracle Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html): locale-sensitive comparison/sorting.
- [Oracle JDK 21 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk21-supported-locales.html): các locale-data providers và giới hạn support theo platform.

**Kết luận:** `Locale.Category.DISPLAY` và `Locale.Category.FORMAT` phục vụ **hai mục tiêu khác nhau**: tên/ngôn ngữ hiển thị so với quy ước định dạng số, tiền tệ và ngày giờ. `Locale.getDefault()` là default chung, còn `getDefault(category)` cho phép tách hai loại; `setDefault(Locale)` sẽ đặt lại cả hai. Với desktop app có thể đặt defaults khi startup; với server đa người dùng, **hãy truyền locale rõ ràng theo user/request** thay vì thay default của toàn JVM. Tách thêm currency, timezone và charset theo contract, dùng `java.time` hiện đại và không phụ thuộc hướng dẫn lỗi thời.
