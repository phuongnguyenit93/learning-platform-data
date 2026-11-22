# Định dạng theo dữ liệu locale hiện hành trong Java

> **Module:** Java 8 — **Ngôn ngữ và locale**. Mục tiêu là dùng dữ liệu locale của JDK để hiển thị **số, phần trăm, tiền tệ, ngày giờ và thông báo** theo ngôn ngữ/vùng của người dùng; hiểu default `Locale.Category.FORMAT`, sử dụng locale tường minh, phân biệt locale với múi giờ và currency thực tế, xử lý parser có thể chấp nhận input một phần, và thiết kế hệ thống bền vững khi **CLDR locale data thay đổi giữa các bản JDK**. Các API chính đã có từ Java 8 và vẫn có giá trị trên Java hiện hành.

## 1. Vì sao cùng một dữ liệu có nhiều cách hiển thị hợp lệ?

Một giá trị số trong mô hình dữ liệu có thể là `1234567.5`, nhưng cách hiển thị phụ thuộc quy ước văn hóa:

| Ngữ cảnh hiển thị | Ví dụ minh họa thường gặp | Cần chú ý |
| --- | --- | --- |
| Tiếng Anh, Hoa Kỳ | `1,234,567.50` | Dấu phẩy nhóm, dấu chấm thập phân |
| Tiếng Đức, Đức | `1.234.567,50` | Dấu chấm nhóm, dấu phẩy thập phân |
| Tiếng Pháp, Pháp | Dấu phẩy thập phân và khoảng trắng đặc biệt để nhóm | Ký tự nhóm có thể là narrow no-break space |
| Tiếng Việt, Việt Nam | Dấu phân cách do dữ liệu `vi-VN` của JDK quy định | Không tự hard-code từ kinh nghiệm cá nhân |

Các ví dụ trên giải thích ý tưởng **không phải chuỗi vàng bất biến trên mọi JDK**. Locale provider, phiên bản CLDR, cấu hình runtime và style của formatter đều có thể thay đổi ký tự, chữ, dấu cách hoặc trật tự hiển thị.

Tương tự, một ngày duy nhất `2024-02-29` có thể hiển thị dưới dạng tháng/ngày/năm ở Mỹ và ngày.tháng.năm ở Đức. Nhưng **ngày trong mô hình** vẫn là cùng một `LocalDate`. Đổi locale chỉ đổi cách biểu diễn, **không đổi ý nghĩa của ngày**.

Một hệ thống tốt phải tách:

1. **Dữ liệu gốc**: số `BigDecimal`, `LocalDate`, `Instant`, `Currency` code...
2. **Ý định định dạng**: hiển thị tiền, phần trăm, date SHORT/LONG, thông báo.
3. **Locale đang áp dụng**: BCP 47 tag như `vi-VN`, `de-DE`, `en-US`.
4. **Dữ liệu locale hiện có**: JDK/CLDR cung cấp ký hiệu, pattern, tên tháng và quy ước.
5. **Múi giờ, currency thực tế và quy tắc nghiệp vụ**: không tự suy toàn bộ từ locale.

## 2. Locale là gì? Không phải timezone hay một kho định dạng bất biến

`java.util.Locale` là định danh ngôn ngữ/vùng/biến thể, ví dụ:

~~~java
Locale vietnam = Locale.forLanguageTag("vi-VN");
Locale germany = Locale.GERMANY;
Locale unitedStates = Locale.US;

System.out.println(vietnam.toLanguageTag()); // vi-VN
~~~

Đây là **đoạn minh họa Java 8**, cần `import java.util.Locale;`. Chuỗi `vi-VN` là một BCP 47 language tag; `vi` mô tả ngôn ngữ, `VN` mô tả vùng. Locale có thể còn script và extensions.

**Locale là định danh để truy xuất quy tắc**, không phải một đối tượng chứa tất cả format patterns cố định. `NumberFormat`, `DateTimeFormatter` và `Currency` dùng locale để chọn dữ liệu/luật hiển thị tương ứng theo môi trường Java hiện hành.

### 2.1. Những gì Locale có thể tác động

- Dấu phân cách hàng nghìn và thập phân.
- Ký tự chữ số và kiểu grouping trong một số locale.
- Symbol và vị trí hiển thị currency.
- Cách hiển thị phần trăm và khoảng trắng quanh ký hiệu.
- Thứ tự ngày–tháng–năm; tên tháng và ngày trong tuần.
- Cách hiển thị giờ 12/24, AM/PM, timezone display names khi formatter có dữ liệu đó.
- Mẫu thông báo có number/date subformats.
- Một số dữ liệu lịch như first day of week thông qua API liên quan.

### 2.2. Những gì Locale không tự quyết định

- **Múi giờ thực tế** của user. `Locale.US` không có nghĩa toàn nước Mỹ dùng một giờ.
- **Instant** ứng với một ngày giờ local chưa có zone.
- **Đơn vị tiền thật của giao dịch**. Người dùng Việt Nam vẫn có thể trả tiền bằng USD.
- **Tỷ giá ngoại tệ** hoặc quy tắc làm tròn của một hệ thống thanh toán.
- **Calendar/chronology** theo nghiệp vụ nếu hệ thống dùng lịch không phải ISO.
- Đúng/sai của input theo schema, quyền truy cập hay bản dịch văn bản.
- Mọi style/rendering chi tiết trong browser/mobile UI.

**Nguyên tắc:** Locale ảnh hưởng **biểu diễn**, còn timezone, currency, precision và business validation phải được chọn/ghi nhận riêng.

## 3. “Locale hiện hành” có ba khái niệm phải phân biệt

### 3.1. Default locale của JVM

~~~java
Locale current = Locale.getDefault();
~~~

Đây là mặc định ở phạm vi JVM, ban đầu thường được runtime xác định từ môi trường hệ thống. Nó **không** đồng nghĩa với ngôn ngữ của từng người dùng web đang truy cập service.

### 3.2. FORMAT category: định dạng ngày, số và currency

~~~java
Locale formattingLocale =
        Locale.getDefault(Locale.Category.FORMAT);

NumberFormat formatter =
        NumberFormat.getNumberInstance(formattingLocale);
~~~

`Locale.Category.FORMAT` dành cho việc chọn default locale của **date/number/currency formatting**. Các factory không có tham số locale như `NumberFormat.getNumberInstance()` sử dụng default FORMAT locale theo hợp đồng Java 8.

### 3.3. DISPLAY category: tên ngôn ngữ, vùng và UI

~~~java
Locale displayLocale =
        Locale.getDefault(Locale.Category.DISPLAY);
~~~

`Locale.Category.DISPLAY` dành cho việc hiển thị tên locale/language/region và thông tin UI liên quan. Hai category **có thể khác nhau**; không suy rằng format locale phải bằng display locale trong mọi runtime.

Ví dụ, ứng dụng có thể hiển thị menu tiếng Anh nhưng định dạng số theo quy ước Đức. Cả hai nhu cầu có thể tồn tại đồng thời.

### 3.4. Default FORMAT không phải locale của request

Trong backend phục vụ nhiều user:

~~~text
User A: vi-VN -> format số/ngày theo Việt Nam
User B: de-DE -> format số/ngày theo Đức
User C: en-US -> format số/ngày theo Hoa Kỳ
                           |
                           v
                     Cùng một JVM
~~~

Nếu code chỉ gọi `NumberFormat.getInstance()` không có locale, **cả ba request có thể dùng cùng default JVM**, không đạt yêu cầu cá nhân hóa.

Ưu tiên truyền locale theo ngữ cảnh request:

~~~java
String formatAmount(BigDecimal amount, Locale locale) {
    NumberFormat f = NumberFormat.getNumberInstance(locale);
    f.setMinimumFractionDigits(2);
    f.setMaximumFractionDigits(2);
    return f.format(amount);
}
~~~

Đây là **method minh họa**; format cho tiền thực tế cần cả currency, scale và rounding policy chứ không chỉ hai fraction digits.

### 3.5. Không gọi Locale.setDefault mỗi request

~~~java
// PHẢN VÍ DỤ trong một web server nhiều user:
Locale.setDefault(Locale.GERMANY);
~~~

`setDefault` thay đổi **shared process-wide state**. Nếu request A đổi default rồi request B đang format cho một người khác, kết quả có thể bị ảnh hưởng, khó test và có race. Giữ default locale cho cấu hình toàn JVM; request locale **truyền tường minh vào từng formatter**.

## 4. Lấy Locale từ yêu cầu người dùng, không đoán từ địa chỉ IP

Trong ứng dụng thực, locale có thể đến từ:

1. Thiết lập được user chọn và lưu trong profile.
2. Tham số request có quyền truy cập/validation thích hợp.
3. HTTP `Accept-Language` nếu user chưa chọn.
4. Cấu hình sản phẩm hoặc default của tenant.
5. Default ứng dụng (ví dụ `en-US` hoặc `vi-VN`).

Đây là **thứ tự minh họa**, không phải một luật bắt buộc. Sản phẩm phải quyết định rõ precedence và fallback. Một máy chủ ở Việt Nam không tự chứng minh mọi người dùng muốn format theo vi-VN; một IP không bảo đảm quốc tịch hoặc preferences.

### 4.1. Nhận tag chuẩn

~~~java
Locale requested = Locale.forLanguageTag("vi-VN");

String language = requested.getLanguage(); // "vi"
String country = requested.getCountry();   // "VN"
~~~

`Locale.forLanguageTag` hỗ trợ BCP 47, phù hợp khi dữ liệu đầu vào là language tag. Nó có thể chuẩn hóa/loại những phần không phù hợp theo quy tắc parser; **không coi một tag bất kỳ là locale được sản phẩm hỗ trợ chỉ vì không ném exception**.

### 4.2. Validate theo tập được hỗ trợ

Ví dụ, ứng dụng chỉ hỗ trợ `vi-VN`, `en-US` và `de-DE`:

~~~java
Set<String> allowed = new HashSet<>(
        Arrays.asList("vi-VN", "en-US", "de-DE"));

String tag = inputLanguageTag;
if (!allowed.contains(tag)) {
    // Từ chối hoặc chọn fallback được sản phẩm phê duyệt.
}
~~~

Đây là **đoạn minh họa** cần khai báo `inputLanguageTag`, import `Set`, `HashSet`, `Arrays`. Một hệ thống thực cần canonicalize tag và xử lý case/region/script đúng trước khi so với allowlist; không dùng raw string unchecked làm key.

### 4.3. BCP 47 tag không chứng minh mọi dữ liệu locale đều có

Runtime có thể fallback về dữ liệu từ ngôn ngữ/vùng cha khi thiếu locale cụ thể. Danh sách locale hỗ trợ cũng thay đổi theo implementation và cách đóng gói runtime (`jlink` có thể loại bớt locale data). Test locale mà sản phẩm cam kết hỗ trợ trên chính runtime triển khai.

### 4.4. Tránh dựa vào Locale.toString() để lưu chuẩn

`Locale.toLanguageTag()` phù hợp để trao đổi BCP 47 tags. `Locale.toString()` có dạng lịch sử đặc thù Java, không nên parse bằng substring rồi coi là wire-format chuẩn.

## 5. NumberFormat: định dạng số theo dữ liệu locale

### 5.1. Factory nên dùng

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

String usText = us.format(1234567.5);
String deText = de.format(1234567.5);
~~~

`NumberFormat.getNumberInstance(locale)` tạo formatter định dạng số tổng quát cho locale. Cách hiển thị cụ thể phụ thuộc dữ liệu locale, default maximum/minimum fraction digits và rounding.

**Nếu bài toán cần số chữ số sau dấu thập phân cụ thể, thiết lập tường minh:**

~~~java
NumberFormat fmt = NumberFormat.getNumberInstance(Locale.GERMANY);
fmt.setMinimumFractionDigits(2);
fmt.setMaximumFractionDigits(2);
String text = fmt.format(1234567.5);
~~~

Ví dụ kiểu Đức thông thường là `1.234.567,50`. Tuy nhiên, test có tính tương thích dài hạn nên kiểm tra **hành vi/semantic** và data set tương ứng thay vì khóa chặt mọi locale-generated string qua các bản CLDR.

### 5.2. Grouping và fractional digits là hai chính sách khác nhau

~~~java
NumberFormat fmt = NumberFormat.getNumberInstance(Locale.US);
fmt.setGroupingUsed(true);
fmt.setMinimumFractionDigits(2);
fmt.setMaximumFractionDigits(2);
~~~

- `setGroupingUsed(true)` cho phép trình bày grouping theo rules của formatter.
- `setMinimumFractionDigits(2)` yêu cầu ít nhất hai fraction digits.
- `setMaximumFractionDigits(2)` giới hạn nhiều nhất hai fraction digits và có thể làm tròn.
- `setRoundingMode(...)` chọn luật làm tròn nếu cần và implementation hỗ trợ.

Với một giá trị decimal nhạy cảm, hãy chọn **precision/rounding tại tầng nghiệp vụ** trước; định dạng cuối không nên là phép tính số học duy nhất kiểm soát kết quả.

### 5.3. DecimalFormatSymbols lấy theo locale

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

char decimal = symbols.getDecimalSeparator();
char grouping = symbols.getGroupingSeparator();
~~~

Đây là Java 8; cần import `java.text.DecimalFormatSymbols`. Không hard-code dấu phân cách cho mọi quốc gia, và đừng giả định dấu nhóm luôn là một ký tự ASCII space. Một số locale dùng NBSP/narrow NBSP hoặc ký tự chữ số/định dạng khác.

### 5.4. DecimalFormat khi cần pattern tùy chỉnh

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);

DecimalFormat df = new DecimalFormat("#,##0.00", symbols);
df.setRoundingMode(RoundingMode.HALF_UP);

String result = df.format(new BigDecimal("1234.565"));
// result.equals("1,234.57") == true với profile tường minh này.
~~~

Đây là **đoạn Java 8 minh họa**, cần import `java.text.DecimalFormat`, `java.math.RoundingMode`, `java.math.BigDecimal`. Một pattern và symbols tường minh thích hợp nếu ứng dụng yêu cầu **profile định dạng cố định**, không phải “định dạng locale sống tự cập nhật”.

### 5.5. NumberFormat.parse không phải validator định dạng nghiêm ngặt

~~~java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.GERMANY);

ParsePosition pos = new ParsePosition(0);
Number n = formatter.parse("1234xyz", pos);
~~~

Đây là đoạn minh họa cần import `ParsePosition`. Nhiều formatter có thể parse được phần đầu `1234` rồi dừng trước `xyz`. Vì vậy chỉ nhìn thấy `n != null` **không chứng minh toàn bộ input hợp lệ**.

Nên kiểm tra ít nhất:

~~~java
boolean consumedAll = n != null
        && pos.getIndex() == input.length();
~~~

Đây là **đoạn minh họa**, cần `input` chính là String đã đưa vào parse. Nhưng **tiêu thụ hết text vẫn chưa đủ để kiểm chứng cú pháp canonical**: formatter có thể lenient, có alternate symbols, grouping không mong đợi hoặc rounding. Nếu input phải theo contract rất chặt, cần một grammar/schema validator và cách parse phù hợp.

### 5.6. Không đổi locale giữa ghi và đọc mà không có metadata

Chuỗi `1.234` có thể là 1,234 (thousand separator) hoặc 1.234 (decimal fraction) tùy locale. Nếu lưu text do user nhập mà không lưu locale/format profile, quá trình parse về sau dễ gây sai dữ liệu.

**Với các số cần lưu trữ:** lưu structured numeric value (`BigDecimal`, integer minor units, v.v.), còn localized text chỉ là presentation hoặc input cần parse đúng context.

## 6. Percent và currency: cùng giá trị nhưng semantics khác

### 6.1. Percent dùng tỷ lệ, không tự nhận một giá trị đã nhân 100

~~~java
NumberFormat percent =
        NumberFormat.getPercentInstance(Locale.US);

percent.setMinimumFractionDigits(1);
percent.setMaximumFractionDigits(1);

String text = percent.format(0.125);
// "12.5%"
~~~

`0.125` là một tỷ lệ 12,5%. `getPercentInstance` thường thực hiện nhân với 100 khi format. Nếu ứng dụng đã lưu số 12.5 mang nghĩa “12,5 phần trăm” rồi đưa thẳng vào percent formatter, bạn có thể tạo ra hiển thị 1.250%. Phải thống nhất representation trước.

### 6.2. Currency formatter chọn vị trí/ký hiệu theo locale

~~~java
NumberFormat display =
        NumberFormat.getCurrencyInstance(Locale.JAPAN);

String text = display.format(1234.5);
~~~

Chuỗi hiển thị do dữ liệu locale JDK quy định, và số fraction digits mặc định của currency có thể khác nhau. Không tự suy mọi loại tiền có hai chữ số thập phân.

### 6.3. Locale of user không phải transaction currency

Một người dùng có locale `vi-VN` có thể thanh toán bằng `USD`. Nếu business state có:

~~~text
amount: 1234.56
currencyCode: "USD"
displayLocale: "vi-VN"
~~~

thì không được chỉ gọi `NumberFormat.getCurrencyInstance(viLocale)` rồi ngầm hiểu amount bằng VND. Cần **lưu currencyCode độc lập** và cấu hình formatter đúng mã currency thực tế.

### 6.4. Gắn currency rõ ràng

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Currency usd = Currency.getInstance("USD");

NumberFormat money = NumberFormat.getCurrencyInstance(locale);
money.setCurrency(usd);
String displayed = money.format(new BigDecimal("1234.56"));
~~~

Đây là **đoạn minh họa Java 8**. Trong production, còn phải quy định số fraction digits và rounding dựa trên business/currency contract. **`setCurrency` không nên được hiểu là tự tính đổi tỷ giá**, và việc chọn symbol/position vẫn tùy locale. Một số formatters có fraction digit defaults thiết lập từ currency locale ban đầu; sau khi đổi currency, phải kiểm tra/configure lại precision nếu nghiệp vụ yêu cầu.

### 6.5. Currency codes, symbols và defaultFractionDigits

~~~java
Currency usd = Currency.getInstance("USD");

String code = usd.getCurrencyCode();    // "USD"
int digits = usd.getDefaultFractionDigits();
String symbol = usd.getSymbol(Locale.US);
~~~

Symbol tùy locale và data, có thể trùng giữa nhiều loại tiền. `"$"` không đủ xác định là USD, CAD hay loại currency khác nếu thiếu context. Dùng **ISO currency code** cho dữ liệu/transaction; symbol chỉ hỗ trợ display.

`Currency.getDefaultFractionDigits()` phản ánh metadata currency có trong runtime, **không thay thế** chính sách precision cho hệ thống thanh toán hoặc nghiệp vụ tiền tệ đặc biệt.

### 6.6. Tiền chính xác: dùng BigDecimal hoặc minor units

Với tiền, dùng `BigDecimal`, số minor units theo currency hoặc domain model khác tránh sai số nhị phân của `double`. Đừng round-trip một amount bằng cách format cho người dùng rồi parse trở lại trong business computation.

## 7. Ngày giờ: DateTimeFormatter với FormatStyle và Locale

Java 8 có `java.time.format.DateTimeFormatter`, `FormatStyle`:

- `FULL`: phong cách đầy đủ, nhiều thông tin.
- `LONG`: chi tiết.
- `MEDIUM`: mức trung gian.
- `SHORT`: ngắn gọn.

### 7.1. LocalDate: localized date

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

DateTimeFormatter us = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.US);

DateTimeFormatter de = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

String usText = date.format(us);
String deText = date.format(de);
~~~

Các formatter trên cùng nhận một ngày, nhưng cho output thường khác nhau. Đặc biệt `SHORT` có thể dùng năm hai chữ số, không nên coi localized short string là định dạng lưu trữ không gây mơ hồ.

### 7.2. DateTimeFormatter immutable và thread-safe

~~~java
DateTimeFormatter german = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

DateTimeFormatter american = german.withLocale(Locale.US);

// german vẫn dùng Locale.GERMANY.
~~~

`withLocale` trả **một formatter mới**; nó không mutate instance gốc. `DateTimeFormatter` bất biến và thread-safe theo contract Java 8, nên có thể tái sử dụng khi đã xác định đúng locale/zone/pattern.

### 7.3. Các factory ngày/giờ khác

~~~java
DateTimeFormatter dateFmt = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.US);

DateTimeFormatter timeFmt = DateTimeFormatter
        .ofLocalizedTime(FormatStyle.SHORT)
        .withLocale(Locale.US);

DateTimeFormatter both = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(Locale.US);
~~~

Đây là đoạn minh họa với imports `DateTimeFormatter`/`FormatStyle`. Phải truyền loại temporal phù hợp vào `format`: `LocalDate` không có trường giờ, và một số date-time styles cần zone information. Đừng áp formatter FULL cho object thiếu các trường mà pattern yêu cầu.

### 7.4. ofPattern có locale với tên tháng

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.GERMANY);

String text = LocalDate.of(2024, 2, 29).format(formatter);
~~~

Pattern cố định phần trật tự nhưng tên tháng `MMM` vẫn do dữ liệu locale quyết định. Nếu muốn format mang tính interchange và không phụ thuộc tên tháng, chọn ISO hoặc định dạng số cố định thích hợp.

**Lưu ý pattern:** trong `DateTimeFormatter`, `u` là proleptic year, `y` là year-of-era. Đừng sao chép `yyyy` tùy tiện khi hệ thống có yêu cầu lịch sử/era; `uuuu` thường rõ hơn cho năm ISO proleptic trong pattern kỹ thuật.

### 7.5. Không dùng localized date làm wire format lâu dài

Nếu API cần ngày chính xác, dùng ISO date:

~~~java
String stored = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
// "2024-02-29"
~~~

Với `Instant`, dùng ISO instant kèm `Z`/offset phù hợp; với sự kiện dùng thời gian local, phải kèm zone/offset để tránh ambiguity. Locale display có thể thay đổi nhưng định dạng lưu trữ theo contract cần ổn định.

## 8. Locale, timezone và chronology: ba trục riêng

### 8.1. Locale không đổi múi giờ

~~~java
Instant instant = Instant.parse("2025-01-15T08:30:00Z");

ZonedDateTime utc = instant.atZone(ZoneId.of("UTC"));
ZonedDateTime hcm =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Cả hai là **cùng một instant** nhưng local time khác. Locale của người xem **không** được dùng thay cho `ZoneId`. Người dùng nói tiếng Việt có thể ở Đức; người dùng nói tiếng Đức có thể ở Việt Nam.

### 8.2. Render theo locale VÀ zone đã chọn

~~~java
DateTimeFormatter textFormat = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"));

String forUser = textFormat.format(
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Đây là **đoạn minh họa Java 8**. Luồng đúng là **Instant → ZoneId → ZonedDateTime → locale formatter**. Dữ liệu locale quyết định cách viết, zone quyết định giờ hiển thị. `DateTimeFormatter.withZone(zone)` cũng là một công cụ hợp lệ khi format một `Instant`, nhưng vẫn cần chọn locale riêng.

### 8.3. Chronology không phải timezone

`Chronology` xác định hệ lịch và quy tắc ngày; `ZoneId` xác định offset/timezone. Một locale đôi khi có Unicode extensions ảnh hưởng cách chọn lịch/numbering, tùy API và version. Đừng mặc định một calendar được chọn chỉ vì user dùng một locale; nếu ứng dụng dùng lịch cụ thể, chỉ định chronology và test.

### 8.4. DST tạo giờ local không tồn tại hoặc lặp lại

Một số timezone có DST, nên một `LocalDateTime` có thể bị ambiguous hoặc nonexistent ở thời điểm chuyển giờ. Locale không giải quyết vấn đề này. Với sự kiện thực, dùng `Instant` và `ZoneId` hoặc `OffsetDateTime` theo contract; khi biến đổi từ user-entered local time cần xử lý DST/zone rules.

### 8.5. Ngày tháng local không tự là Instant

`LocalDate` chỉ là ngày, không có giờ/zone. Không lấy `Locale.getDefault()` để tùy tiện biến nó thành UTC timestamp. Nếu nghiệp vụ cần một thời điểm, phải định nghĩa múi giờ và thời điểm trong ngày.

## 9. Parse localized date/number: phải giữ cùng context

### 9.1. Date parse theo đúng locale formatter

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

DateTimeFormatter f = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

String text = f.format(date);
LocalDate restored = LocalDate.parse(text, f);

// restored.equals(date) == true trong trường hợp ví dụ.
~~~

Nếu text nhập theo một locale mà server parse bằng locale khác, có thể có lỗi hoặc kết quả ngày khác. Hãy đính kèm locale context vào request hoặc áp quy ước input machine rõ ràng.

### 9.2. SHORT dates và hai chữ số năm có mơ hồ

Một localized short date có thể chỉ chứa năm hai chữ số và tùy các quy tắc parser để suy ra thế kỷ. Ví dụ demo có thể round-trip cho năm 2024, **không đủ chứng minh tất cả ngày lịch sử/tương lai đều round-trip**. Nếu cần lưu trữ ngày lâu dài và chính xác, dùng ISO local date với bốn chữ số năm và schema thống nhất.

### 9.3. NumberFormat parsing thường lenient

`NumberFormat.parse(String)` có thể chấp nhận một prefix hợp lệ hoặc có các quy tắc parse linh hoạt. Một kết quả `Number` không có nghĩa toàn bộ input theo chuẩn. Dùng `ParsePosition` để phát hiện trailing text; khi domain yêu cầu canonical grammar, cần validation độc lập.

### 9.4. Parse không tự làm rõ business precision

Một localized number có thể được parse thành `Long` hoặc `Double` tùy nội dung/formatter. Với tiền chính xác, nếu dùng `DecimalFormat`, cân nhắc `setParseBigDecimal(true)` (API Java 8) và validate kết quả/scale. Không chuyển số tiền qua `double` rồi kỳ vọng giữ nguyên mọi chữ số thập phân.

### 9.5. Tránh format → parse như bước tính toán

Một code như:

~~~java
String s = NumberFormat.getCurrencyInstance(locale).format(amount);
// Parse s rồi cộng với các amount khác: không khuyến nghị.
~~~

có thể làm mất fraction digits vì format đã round, hoặc parse sai currency/localedata. Business logic nên làm việc trên `BigDecimal`/numeric typed values, cuối cùng mới hiển thị cho người dùng.

## 10. String.format và Formatter: locale nên là tham số tường minh

`String.format` có overload nhận `Locale`:

~~~java
String us = String.format(
        Locale.US, "%,.2f", 12345.5);

String de = String.format(
        Locale.GERMANY, "%,.2f", 12345.5);
~~~

`%,.2f` yêu cầu grouping và hai fraction digits, nhưng dấu phân cách theo locale. Nếu gọi `String.format("%,.2f",...)` không truyền locale thì có thể dùng default format locale, tạo output khác trên các máy.

### 10.1. Những trường hợp phù hợp

- Text hiển thị nhanh trong UI hoặc log dành cho con người.
- Một thông báo ngắn cần formatting theo user locale.
- Tạo output mẫu trong CLI với locale được chọn.

### 10.2. Những trường hợp không nên phụ thuộc locale default

- Key/value của giao thức máy–máy.
- JSON numeric field cần số thực, không phải text có grouping.
- CSV/TSV được định nghĩa có dấu phân cách chuẩn cố định.
- Identifier, checksum, canonical signatures.
- Filename hoặc database key cần ổn định.

Nếu đang tạo text “giống số” cho máy đọc, hãy dùng `BigDecimal.toPlainString()`, ISO timestamps và schema rõ ràng, không lấy localized `NumberFormat.format` làm định dạng chuẩn.

## 11. MessageFormat: định dạng thông báo dựa trên locale

Để kết hợp bản dịch câu với các đối số là số/ngày/tiền, Java 8 có `java.text.MessageFormat`.

~~~java
MessageFormat message = new MessageFormat(
        "You''ve got {0,number,integer} items",
        Locale.US);

String result = message.format(new Object[] {3});
// "You've got 3 items"
~~~

Ở đây `{0,number,integer}` yêu cầu định dạng đối số index 0 như số nguyên. `MessageFormat` dùng locale khi tạo các subformats; code không nên tự ghép string với số tiền/ngày bằng dấu cộng cho mọi ngôn ngữ.

### 11.1. Quy tắc dấu nháy đơn đặc biệt

Trong pattern của `MessageFormat`, dấu nháy đơn `'` được dùng để quote phần literal; muốn hiện **một dấu nháy đơn** thường phải viết `''`.

~~~text
Pattern: You''ve got {0,number,integer} items
Output:  You've got 3 items
~~~

Nếu dịch giả sửa message pattern nhưng không biết luật dấu nháy, placeholder có thể bị quote sai và không được thay đối số. Cần tests cho những message chứa apostrophes, dấu ngoặc nhọn, nhiều tham số.

### 11.2. Đừng gọi setLocale rồi tin mọi subformat đã tạo tự đổi

`MessageFormat.setLocale` thay locale liên quan đến việc tạo/so sánh subformats, nhưng các subformats đã được tạo từ pattern trước đó **không nhất thiết thay đổi theo**. Thay vì mutate một formatter được chia sẻ giữa các request locale khác nhau, tạo `MessageFormat(pattern, requestLocale)` riêng, hoặc quản lý immutable configuration + fresh formatter.

### 11.3. MessageFormat khác ResourceBundle

- `ResourceBundle` chọn **nội dung chuỗi dịch** theo locale (cùng các fallback/control rules).
- `MessageFormat` thay tham số và **định dạng giá trị** trong chuỗi đó theo locale.
- `NumberFormat` và `DateTimeFormatter` xử lý số/ngày độc lập với văn bản câu.

Một locale number formatter không tự dịch các nhãn “Order”, “Total”, “Paid”. Muốn quốc tế hóa UI, cần cả translation content và formatting.

### 11.4. Hạn chế của MessageFormat với ngữ pháp đa ngôn ngữ

`MessageFormat` cơ bản có index parameters và choice formats, nhưng không tự giải quyết mọi vấn đề plural/gender/grammar của mọi ngôn ngữ. Với sản phẩm yêu cầu internationalization phức tạp, cân nhắc giải pháp message localization hỗ trợ chuẩn plurals theo công cụ/ngôn ngữ ứng dụng và quản lý translation workflow phù hợp.

## 12. Các phiên bản JDK có thể dùng dữ liệu locale KHÁC nhau

### 12.1. “Hiện hành” là dữ liệu của runtime, không phải một bảng đóng băng

Theo tài liệu Oracle, từ JDK 9, locale data CLDR được ưu tiên theo mặc định. Các bản JDK mới tiếp tục cập nhật CLDR, làm thay đổi text hiển thị như pattern ngày/giờ, symbol currency, grouping, month/era names hoặc các quy tắc liên quan.

**Dẫn chứng hiện hành:** Oracle JDK 26 dùng dữ liệu **CLDR 48**. Không nên giả định chuỗi định dạng chính xác giống nhau giữa JDK 8, 17, 21, 25 và 26, dù cùng `Locale` và cùng code.

### 12.2. Ví dụ tình huống khác biệt

Một hệ thống có test cố định:

~~~text
DateFormat.MEDIUM(Locale.UK) == "19-Mar-2024"
~~~

có thể hỏng sau nâng JDK/CLDR vì cách viết ngày thay đổi. **Đừng sửa test bằng cách bắt format tự quay về pattern cũ trên mọi locale** nếu sản phẩm thật muốn dùng quy ước locale cập nhật.

Giải pháp tùy mục tiêu:

1. **UI hiển thị theo hiện hành:** chấp nhận/kiểm tra thay đổi dữ liệu locale, test semantic + visual snapshot có version.
2. **Output contract bắt buộc cố định:** chọn pattern/ISO/decimal symbols rõ và version hợp đồng.
3. **Chính sách phiên bản dữ liệu locale:** ghi nhận phiên bản JDK/CLDR/runtime cho deployment, đánh giá regression khi nâng cấp.

### 12.3. Đừng phụ thuộc cơ chế legacy provider

Một số bài hướng dẫn cũ khuyên dùng `java.locale.providers=COMPAT` hoặc `JRE` để phục hồi behavior cũ. Đây **không phải khuyến nghị cho Java hiện đại**: Oracle đã loại bỏ dữ liệu locale legacy `COMPAT/JRE` từ JDK 23. JDK hiện đại mặc định dùng CLDR; tùy platform/config có thể có `HOST` và `SPI`.

Nếu ứng dụng cần provider preference, property `java.locale.providers` được đọc/cached khi khởi tạo locale services; phải cấu hình theo **launcher/runtime deployment**, không kỳ vọng đổi nó giữa request bằng `System.setProperty` sẽ tác động ngay.

### 12.4. Không dùng pattern xưa để cố đúng “ngữ pháp hiện hành”

Nếu sản phẩm chủ đích hiển thị chuẩn locale hiện hành, hãy dùng các factories localized:

~~~java
NumberFormat.getNumberInstance(locale);
DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
        .withLocale(locale);
~~~

Chúng cho phép runtime cung cấp dữ liệu locale hiện có. Dùng pattern cố định chỉ khi product requirement thật sự nói “mọi lần phải có thứ tự và dấu này”, và cần chấp nhận rằng output khi đó có thể **không hoàn toàn theo quy ước locale mới nhất**.

### 12.5. Locale data không giống tzdb

JDK cũng cập nhật dữ liệu múi giờ (tzdb) theo các thay đổi luật địa phương. **CLDR** ảnh hưởng tên/format; **tzdb** ảnh hưởng offset/DST. Cần test cả hai khi ứng dụng có lịch hẹn, chuyến bay, hóa đơn theo giờ địa phương hoặc các sự kiện xuyên múi giờ.

## 13. Ví dụ Java 8 hoàn chỉnh: dùng dữ liệu locale mà vẫn kiểm thử ổn định

Bài sample kiểm tra:

1. Đọc `Locale.Category.FORMAT` và `DISPLAY`.
2. Chứng minh no-arg `NumberFormat.getNumberInstance()` tuân theo default FORMAT.
3. Định dạng số theo Mỹ/Đức và kiểm tra hai biểu diễn khác nhau.
4. Round-trip số theo formatter/locale Đức, kiểm tra toàn input bằng `ParsePosition`.
5. Nhận biết parser có thể chấp nhận prefix của input.
6. Định dạng percent 0.125 theo Mỹ.
7. Xác định currency codes theo US, JP, VN, nhưng không hard-code currency symbol.
8. Format+parse date SHORT theo Mỹ/Đức với cùng date.
9. Dùng ISO local date cho dữ liệu ổn định.
10. Chứng minh `DateTimeFormatter.withLocale` không mutate original.
11. Chứng minh timezone làm đổi wall time nhưng giữ cùng Instant.
12. `MessageFormat` với apostrophe escaping.
13. Custom `DecimalFormat` có symbols, pattern và rounding policy tường minh.
14. `String.format(Locale,...)` khác nhau theo locale.

**Vì output localized có thể thay đổi giữa JDK/CLDR versions, demo in kết quả semantic dạng boolean thay vì khóa chặt toàn bộ chuỗi localized.** Chỉ những chuỗi được chỉ rõ hợp đồng (`vi-VN` tag, ISO, currency codes, MessageFormat tiếng Anh, decimal profile) mới được in nguyên văn. Đây là cách kiểm thử đúng trọng tâm “dữ liệu locale hiện hành”.

Lưu vào **LocaleFormattingDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public final class LocaleFormattingDemo {
    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        System.out.println("Vietnam language tag = " + vietnam.toLanguageTag());
        System.out.println("FORMAT category exists = "
                + (Locale.getDefault(Locale.Category.FORMAT) != null));
        System.out.println("DISPLAY category exists = "
                + (Locale.getDefault(Locale.Category.DISPLAY) != null));

        double value = 1234567.5;
        String implicit = NumberFormat.getNumberInstance().format(value);
        String explicit = NumberFormat.getNumberInstance(
                Locale.getDefault(Locale.Category.FORMAT)).format(value);
        System.out.println("default FORMAT matched = "
                + implicit.equals(explicit));

        NumberFormat usNumbers = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat deNumbers = NumberFormat.getNumberInstance(Locale.GERMANY);
        usNumbers.setMinimumFractionDigits(2);
        usNumbers.setMaximumFractionDigits(2);
        deNumbers.setMinimumFractionDigits(2);
        deNumbers.setMaximumFractionDigits(2);
        String german = deNumbers.format(value);
        String american = usNumbers.format(value);
        System.out.println("number locale styles differ = "
                + !german.equals(american));

        ParsePosition pos = new ParsePosition(0);
        Number roundTrip = deNumbers.parse(german, pos);
        System.out.println("German numeric round trip = "
                + (roundTrip != null
                    && roundTrip.doubleValue() == value
                    && pos.getIndex() == german.length()));
        ParsePosition partialPos = new ParsePosition(0);
        Number partial = deNumbers.parse("1234xyz", partialPos);
        System.out.println("partial parse detectable = "
                + (partial != null && partialPos.getIndex() < 7));

        NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
        percent.setMinimumFractionDigits(1);
        percent.setMaximumFractionDigits(1);
        System.out.println("US percent = " + percent.format(0.125));

        System.out.println("US currency code = "
                + Currency.getInstance(Locale.US).getCurrencyCode());
        System.out.println("JP currency code = "
                + Currency.getInstance(Locale.JAPAN).getCurrencyCode());
        System.out.println("VN currency code = "
                + Currency.getInstance(vietnam).getCurrencyCode());
        System.out.println("currency formatter uses JP currency = "
                + NumberFormat.getCurrencyInstance(Locale.JAPAN)
                    .getCurrency().equals(Currency.getInstance(Locale.JAPAN)));

        LocalDate date = LocalDate.of(2024, 2, 29);
        DateTimeFormatter usDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(Locale.US);
        DateTimeFormatter deDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(Locale.GERMANY);
        String formattedUs = date.format(usDate);
        String formattedDe = date.format(deDate);
        System.out.println("US date round trip = "
                + LocalDate.parse(formattedUs, usDate).equals(date));
        System.out.println("DE date round trip = "
                + LocalDate.parse(formattedDe, deDate).equals(date));
        System.out.println("date styles differ = "
                + !formattedUs.equals(formattedDe));
        System.out.println("ISO date = "
                + date.format(DateTimeFormatter.ISO_LOCAL_DATE));

        DateTimeFormatter changed = deDate.withLocale(Locale.US);
        System.out.println("date formatter immutable = "
                + (deDate.getLocale().equals(Locale.GERMANY)
                    && changed.getLocale().equals(Locale.US)));

        Instant instant = Instant.parse("2025-01-15T08:30:00Z");
        ZonedDateTime utc = instant.atZone(ZoneId.of("UTC"));
        ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("zones keep same instant = "
                + utc.toInstant().equals(hcm.toInstant()));
        System.out.println("zones change wall time = "
                + !utc.toLocalTime().equals(hcm.toLocalTime()));

        MessageFormat message = new MessageFormat(
                "You''ve got {0,number,integer} items", Locale.US);
        System.out.println("message apostrophe = "
                + message.format(new Object[] {3}));

        DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(Locale.US);
        symbols.setDecimalSeparator('.');
        symbols.setGroupingSeparator(',');
        DecimalFormat fixed = new DecimalFormat("#,##0.00", symbols);
        fixed.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("explicit decimal profile = "
                + fixed.format(new BigDecimal("1234.565")));

        String usPrintf = String.format(Locale.US, "%,.2f", 12345.5);
        String dePrintf = String.format(Locale.GERMANY, "%,.2f", 12345.5);
        System.out.println("String.format differs by locale = "
                + !usPrintf.equals(dePrintf));
    }
}
~~~

Biên dịch và chạy trên JDK có hỗ trợ target Java 8:

~~~bash
javac --release 8 LocaleFormattingDemo.java
java LocaleFormattingDemo
~~~

Nếu dùng trực tiếp JDK 8, lệnh biên dịch là `javac LocaleFormattingDemo.java`. Mã dùng API Java 8; trên một số JDK mới, compiler có thể cảnh báo target 8 cũ nhưng vẫn biên dịch/chạy thành công.

**Stdout thực tế đã chạy và kiểm chứng:**

~~~text
Vietnam language tag = vi-VN
FORMAT category exists = true
DISPLAY category exists = true
default FORMAT matched = true
number locale styles differ = true
German numeric round trip = true
partial parse detectable = true
US percent = 12.5%
US currency code = USD
JP currency code = JPY
VN currency code = VND
currency formatter uses JP currency = true
US date round trip = true
DE date round trip = true
date styles differ = true
ISO date = 2024-02-29
date formatter immutable = true
zones keep same instant = true
zones change wall time = true
message apostrophe = You've got 3 items
explicit decimal profile = 1,234.57
String.format differs by locale = true
~~~

### 13.1. Vì sao default FORMAT matched là true?

`NumberFormat.getNumberInstance()` không nhận locale sử dụng default của `Locale.Category.FORMAT`. So sánh với factory được truyền chính locale FORMAT là cách xác minh hợp đồng mà không phụ thuộc tên/định dạng chuỗi của máy chạy.

Trong hệ thống thật, **đừng gọi default factory cho request nhiều user**; hãy truyền request locale tường minh.

### 13.2. Vì sao không in chính xác localized text cho Đức/Vietnam?

Mục tiêu là kiểm thử semantics vẫn đúng khi JDK cập nhật dữ liệu CLDR. Nếu in và assert nguyên văn tất cả strings localized, một upgrade hoàn toàn hợp lệ (dấu nhóm, kiểu viết ngày, symbol) có thể khiến test hỏng không liên quan đến logic.

Ở sản phẩm cần screenshot/layout QA, có thể **kiểm tra trực quan text thật** trong một test được pin JDK/CLDR version, song song với test semantic ổn định như demo.

### 13.3. Vì sao parse text Đức thành công chưa đủ đảm bảo input luôn hợp lệ?

Ở ví dụ, parser đọc lại chính chuỗi do formatter Đức tạo ra và có `ParsePosition` xác nhận đã consume hết. Nhưng một chuỗi khác có prefix số hợp lệ và trailing garbage vẫn có thể tạo `Number` non-null. Vì vậy demo in `partial parse detectable = true`.

**Quan trọng:** kiểm tra `pos.getIndex()==input.length()` là điều kiện cần trong nhiều use cases, nhưng không phải validation đầy đủ cho canonical numeric text.

### 13.4. Vì sao các currency codes ổn định mà symbols không được in?

`Currency.getInstance(Locale.US/JAPAN/vi-VN)` cung cấp các currency codes `USD`, `JPY`, `VND` trong dữ liệu runtime được thử. Symbols và vị trí symbol là dữ liệu display có thể thay đổi theo locale/profile/JDK, nên demo chỉ khẳng định formatter chọn currency tương ứng.

Nếu giao dịch thực có currencyCode khác currency của vùng, ứng dụng phải chỉ định currency thực và test currency code của transaction.

### 13.5. Vì sao các dates round-trip trong demo?

`DateTimeFormatter.ofLocalizedDate(SHORT)` với US hoặc Germany chuyển ngày 29-02-2024 thành chuỗi theo locale và parse lại bằng **cùng formatter**. Đây là trường hợp được thử xác minh, **không phải chứng minh mọi ngày lịch sử có thể round-trip với short pattern hai chữ số năm**.

### 13.6. Vì sao timezone thay đổi wall time nhưng không Instant?

`08:30Z` tại UTC và local time tại Asia/Ho_Chi_Minh là hai cách biểu diễn **cùng một thời điểm**. Zone rules xác định giờ local; locale ảnh hưởng cách viết ra cho người xem. Hai trục phải được chọn riêng.

### 13.7. Vì sao custom decimal profile khác localized number factory?

`DecimalFormat("#,##0.00", DecimalFormatSymbols(Locale.US))` với rounding HALF_UP tạo output theo **quy tắc đã khóa**. Nó hữu ích khi contract yêu cầu chính xác grouping/digits/rounding. Ngược lại localized factory để runtime chọn conventions hiện hành cho locale.

### 13.8. Những gì chương trình không làm

- Không tự thay JVM default locale, tránh shared mutable global state.
- Không yêu cầu internet hoặc đọc resource bundle ngoài.
- Không hard-code expected month names từ CLDR.
- Không dùng số thời gian hiện tại dễ biến đổi.
- Không so throughput các formatter.
- Không khẳng định văn bản localized của mọi JDK/version sẽ giống nhau.

## 14. Thiết kế backend nhiều người dùng và caching formatters

### 14.1. Request context nên mang đủ ba thông tin

Một model hiển thị sự kiện thường cần:

~~~text
localeTag   = "vi-VN"
zoneId      = "Asia/Ho_Chi_Minh"
currencyCode = "USD"  // Nếu hiển thị số tiền bằng USD
~~~

**Đừng chỉ lưu `Locale` rồi suy ra zone/currency.** User có thể đổi preferred language mà không đổi timezone, hoặc thực hiện giao dịch nhiều loại tiền.

### 14.2. DateTimeFormatter có thể cache theo locale/style/zone nếu cấu hình đúng

Vì `DateTimeFormatter` immutable/thread-safe, có thể cache formatter được cấu hình đầy đủ theo locale và format style khi workload cần. Cần hiểu runtime data updates xảy ra theo deployment, không giả định CLDR tự cập nhật giữa chừng trên một JVM đang chạy.

### 14.3. NumberFormat và DecimalFormat không thread-safe

Javadoc Java 8 nói `NumberFormat` nhìn chung không synchronized. `DecimalFormat` là mutable subclass với setters như `setMinimumFractionDigits`, `setRoundingMode`, `setCurrency`.

**Không** đặt một `NumberFormat` mutable global singleton rồi gọi format/parse đồng thời từ hàng trăm request:

~~~java
// PHẢN VÍ DỤ:
static final NumberFormat SHARED =
        NumberFormat.getNumberInstance(Locale.US);
~~~

Ngay cả nếu không đổi locale giữa các calls, một formatter mutable dùng chung không có external synchronization vẫn có thể không thread-safe. Tạo formatter per call/per thread, clone an toàn khi phù hợp, hoặc quản lý pooling đúng. Với JVM server, cách đơn giản **tạo formatter trong request** thường đáng ưu tiên trước tối ưu bằng cache phức tạp.

### 14.4. MessageFormat cũng mutable

`MessageFormat` có `setLocale`, `applyPattern`, `setFormat`; không chia sẻ một mutable instance giữa các request đồng thời trừ khi có synchronization/protocol rõ. Đặc biệt, đổi locale không có nghĩa đã đổi lại mọi created subformats cũ.

### 14.5. Cache key phải bao gồm cấu hình ảnh hưởng output

Nếu cache:

~~~text
Key = (localeTag, style, fractionDigits,
       roundingMode, currencyCode, zoneId)
~~~

đó là một **schema minh họa**, không phải Java API. Tham số nào không ảnh hưởng loại formatter cụ thể có thể bỏ. Nhưng nếu quên currencyCode hoặc timezone ở một formatter cần chúng, hai user có thể nhận kết quả của nhau.

### 14.6. Localized data cũng là dependency của build/runtime

Nếu service dùng custom runtime image có `jdk.localedata` bị loại bớt, một vài locales có thể fallback khác kỳ vọng. Hãy kiểm tra locale coverage trên artifact deploy thực, không chỉ laptop của developer.

## 15. Bộ kiểm thử đúng cho locale data hiện hành

### 15.1. Phân loại ba nhóm test

| Loại test | Mục tiêu | Cách assert |
| --- | --- | --- |
| **Semantic unit test** | Format/parse cùng contract, zone và amount đúng | Typed values và invariant |
| **Locale integration test** | Formatter lấy locale data đúng trên runtime triển khai | Kiểm tra kết quả/format elements theo locale đã chọn |
| **Visual snapshot/golden test** | UI layout, RTL spacing, NBSP, currency symbol | Pin JDK/CLDR version hoặc cập nhật snapshots có review |

Đừng bắt mọi bài test locale-sensitive đều phải so exact string trong mọi JDK khác nhau. Ngược lại, nếu product contract **yêu cầu biểu diễn cụ thể**, exact output test là đúng và cần pin format profile/runtime.

### 15.2. Ma trận locale nên có

- `vi-VN` cho người dùng Việt Nam.
- `en-US` cho dấu số/thứ tự ngày kiểu Mỹ.
- `de-DE` cho grouping/decimal khác Mỹ.
- `fr-FR` cho dấu cách đặc biệt trong grouping.
- `ja-JP` cho currency pattern/fraction digits khác.
- Một locale dùng hệ chữ số khác nếu sản phẩm hỗ trợ.
- Một locale RTL nếu UI cần hỗ trợ.
- Locale không được sản phẩm hỗ trợ để kiểm tra fallback.

Chọn chỉ những locale product thực sự hỗ trợ khi đánh giá release. Mỗi locale có thể cần kiểm tra theo provider/config runtime.

### 15.3. Cases về số

1. Số nguyên 0, âm và dương.
2. Fraction nhỏ hơn 1.
3. Giá trị có grouping lớn.
4. Tiền với số fraction digits khác nhau.
5. Rounding theo business policy.
6. Input có dấu nhóm khác locale.
7. Input parse chỉ hợp lệ một phần.
8. Data dùng ký tự khoảng trắng NBSP/narrow NBSP.
9. BigDecimal có nhiều chữ số.
10. Currency code khác user locale.
11. Format percent đầu vào là tỷ lệ vs đã nhân 100.
12. Giá trị null/NaN/Infinity nếu domain có.

### 15.4. Cases về ngày giờ

1. Ngày 29/02 trong năm nhuận.
2. Ngày đầu/cuối năm.
3. Short date có năm hai chữ số.
4. Month/day text có dấu và ký tự Unicode.
5. Cùng Instant ở nhiều zones.
6. DST gap/overlap ở timezone hỗ trợ DST.
7. Formatter yêu cầu field không có trong temporal.
8. Date parse theo locale khác date format.
9. ISO output cho machine protocol.
10. Nâng JDK/CLDR thay đổi localized strings.

### 15.5. Cases về code và deployment

- Một JVM nhận request A/B với locales khác nhau cùng lúc.
- Không gọi `Locale.setDefault` per request.
- NumberFormat mutable không bị share unsafely.
- Mỗi request dùng đúng currencyCode và zone.
- Runtime image có locale data cần thiết.
- MessageFormat escaping apostrophe/braces đúng.
- Chữ số/format đặc biệt hiển thị không bị font/layout lỗi.
- Tests không giả định tất cả người dùng thuộc timezone dựa trên locale.

## 16. Những sai lầm thường gặp khi định dạng theo locale

### Lỗi 1 — Dùng Locale.US cho mọi user

UI hiển thị sai quy ước của người dùng khác. **Sửa:** chọn request locale và truyền vào formatter.

### Lỗi 2 — Dùng default JVM như locale của từng request

Backend multi-tenant không thể dựa vào một default duy nhất. **Sửa:** giữ locale trong request/user context.

### Lỗi 3 — Gọi Locale.setDefault giữa các request

Có shared global mutable state và race. **Sửa:** truyền locale tường minh.

### Lỗi 4 — Nhầm FORMAT với DISPLAY

Tên vùng/ngôn ngữ và formatting có thể cần hai locale khác nhau. **Sửa:** dùng `Locale.getDefault(Category.FORMAT)` cho default date/number/currency, DISPLAY cho display names/UI phù hợp.

### Lỗi 5 — Nghĩ Locale đổi timezone

Locale không tự xác định `ZoneId`. **Sửa:** lưu chọn zone riêng và áp cho Instant.

### Lỗi 6 — Nghĩ locale của user là currency giao dịch

User vi-VN vẫn có thể mua bằng USD. **Sửa:** giữ currencyCode độc lập.

### Lỗi 7 — Hard-code dấu nhóm/thập phân

Dấu khác giữa locales và có thể dùng Unicode spaces. **Sửa:** dùng NumberFormat/DecimalFormatSymbols.

### Lỗi 8 — Giả định grouping separator luôn là ASCII space

Một số locales có NBSP/narrow NBSP. **Sửa:** kiểm tra dữ liệu thực và UI Unicode.

### Lỗi 9 — Format một tỷ lệ 12.5 thành percent mà không chuẩn hóa

Percent formatter hiểu 0.125 là 12.5%. **Sửa:** định nghĩa nội bộ tỷ lệ 0..1 hay percent 0..100.

### Lỗi 10 — Nghĩ mọi currency có hai decimal places

JPY, VND và currencies khác có quy định riêng. **Sửa:** xác định currency metadata và contract precision.

### Lỗi 11 — Nghĩ Currency.getSymbol luôn xác định currency

Ký hiệu trùng và locale-dependent. **Sửa:** lưu ISO currencyCode.

### Lỗi 12 — Dùng Double cho số tiền cần chính xác

Binary floating-point làm tròn sai trong phép tính tài chính. **Sửa:** BigDecimal/minor-unit model.

### Lỗi 13 — Dùng localized number text như DB numeric value

Nó có thể biến đổi theo locale/JDK. **Sửa:** lưu structured numeric type.

### Lỗi 14 — Parse number bằng locale khác locale đã nhập

`1.234` có thể khác nghĩa. **Sửa:** parse cùng locale/context được thỏa thuận.

### Lỗi 15 — Chỉ kiểm tra NumberFormat.parse trả non-null

Parser có thể chấp nhận prefix. **Sửa:** ParsePosition + validation chặt hơn nếu cần.

### Lỗi 16 — Tin parse tiêu thụ hết nghĩa là canonical

Lenient parser có thể nhận nhiều biểu diễn. **Sửa:** schema/grammar validation cho input kỹ thuật nghiêm ngặt.

### Lỗi 17 — Dùng LocalDate với time-only formatter

Temporal thiếu giờ nên format có thể throw. **Sửa:** chọn đúng Temporal type và format style.

### Lỗi 18 — Dùng Locale như thay thế ZoneId khi format Instant

Instant chưa có giờ local. **Sửa:** chuyển sang ZonedDateTime bằng zone trước rồi format.

### Lỗi 19 — Nghĩ SHORT date luôn round-trip mọi năm

Hai chữ số năm có quy tắc suy diễn. **Sửa:** ISO date cho lưu trữ, test edge years.

### Lỗi 20 — Hard-code tiếng/tên tháng CLDR trong unit tests đa JDK

Locale data thay đổi hợp lệ. **Sửa:** semantic tests và version-pinned golden tests khi cần.

### Lỗi 21 — Phụ thuộc COMPAT/JRE locale provider cũ trên Java hiện đại

Provider legacy đã bị loại từ JDK 23. **Sửa:** chuyển sang CLDR và chọn định dạng explicit nếu contract cố định.

### Lỗi 22 — Đổi java.locale.providers khi ứng dụng đang chạy

Locale services cache provider preference ở startup. **Sửa:** cấu hình launcher/deployment và restart/test đúng cách.

### Lỗi 23 — Share NumberFormat mutable giữa threads

NumberFormat không đảm bảo thread safety. **Sửa:** tạo instance per operation/per thread hoặc sync.

### Lỗi 24 — Share MessageFormat mutable và setLocale liên tục

Subformats cũ không tự cập nhật hoàn toàn. **Sửa:** tạo mới theo locale/pattern.

### Lỗi 25 — Nghĩ DateTimeFormatter.withLocale mutate instance

Nó trả formatter mới, old formatter không đổi. **Sửa:** dùng returned instance.

### Lỗi 26 — Dùng String.format không truyền locale trong API boundary

Output phụ thuộc default JVM. **Sửa:** truyền Locale rõ ràng cho human-facing output, hoặc dùng định dạng invariant cho machine.

### Lỗi 27 — Dùng localized dates trong signed tokens/IDs

Chuỗi có thể thay giữa runtime versions. **Sửa:** dùng ISO hoặc canonical binary/JSON representation.

### Lỗi 28 — Tự ghép tiền tệ bằng "$" + amount

Vị trí, symbol và spacing khác giữa locales; $ cũng mơ hồ. **Sửa:** currency formatter với currencyCode đúng.

### Lỗi 29 — Dùng ISO format rồi nghĩ người dùng sẽ luôn hiểu

ISO là tốt cho interoperability nhưng không nhất thiết thân thiện với mọi user. **Sửa:** ISO cho máy, localized format cho hiển thị.

### Lỗi 30 — Áp regex ASCII để loại whitespace trong số Pháp

NBSP/narrow NBSP có thể bị mất hoặc bị hiểu sai. **Sửa:** kiểm tra Unicode input và locale parser.

### Lỗi 31 — Nghĩ Locale.forLanguageTag tự xác thực user preference

BCP47 parsing không đồng nghĩa allowlist của sản phẩm. **Sửa:** canonicalize, whitelist/fallback và ghi nhận request locale.

### Lỗi 32 — Bỏ quên region khi định dạng currency

Locale chỉ có language có thể không đủ để chọn currency của quốc gia. **Sửa:** cung cấp region/currency cụ thể.

### Lỗi 33 — Nhầm ResourceBundle với numeric formatting

ResourceBundle đưa ra chuỗi dịch, không tự thay số/ngày theo đúng locale. **Sửa:** phối hợp translation + NumberFormat/DateTimeFormatter.

### Lỗi 34 — Quên escape apostrophe trong MessageFormat

Pattern có thể quote placeholder thay vì thay argument. **Sửa:** kiểm tra dấu `''` và curly braces trong translation tests.

### Lỗi 35 — Mỗi lần nâng JDK đều “fix” bằng pattern cố định

Có thể vô tình khiến UI không còn cập nhật theo locale thật. **Sửa:** phân biệt UI sống theo CLDR với machine contract cố định.

### Lỗi 36 — Không test custom jlink runtime

Thiếu locale data khiến fallback khác JDK đầy đủ. **Sửa:** kiểm thử deployed runtime image.

### Lỗi 37 — Coi locale data là một phần của source code cố định

CLDR có thể được nâng cấp mà code không đổi. **Sửa:** pin/ghi nhận runtime version và kiểm tra release changes.

### Lỗi 38 — Không phân biệt display formatting với business validation

Một giá trị đẹp theo locale vẫn có thể vi phạm limits/rounding/currency policy. **Sửa:** validate domain typed values trước khi format.

## 17. Checklist triển khai sản phẩm

| Câu hỏi | Quy tắc kiểm tra |
| --- | --- |
| Locale đến từ đâu? | User preference/Accept-Language/fallback có thứ tự rõ |
| Runtime default FORMAT có bị dùng ngoài ý muốn? | Factory explicit locale trong request code |
| Locale và timezone có được lưu riêng? | ZoneId tường minh |
| Có lưu ISO currencyCode riêng? | Không suy toàn bộ từ locale |
| Số cần mấy fraction digits? | Business rounding/precision policy |
| Có xử lý phần trăm theo 0..1? | Representation cố định |
| Có parsing localized input? | Locale metadata và ParsePosition/validation |
| Có dùng date SHORT làm lưu trữ? | Chuyển sang ISO/typed values |
| Có DateTimeFormatter phù hợp temporal? | Date/time fields/zone đúng |
| Có share NumberFormat qua threads? | Per call/per thread/sync |
| Có dùng MessageFormat? | Test apostrophe/braces |
| Có Unicode spaces/RTL/digits? | Visual QA locale-specific |
| Dữ liệu CLDR từ JDK nào? | Ghi nhận runtime/provider version |
| Có phụ thuộc COMPAT/JRE? | Không dùng provider legacy |
| Có custom jlink runtime? | Xác minh locale data đầy đủ |
| Có test các locale sản phẩm hỗ trợ? | vi-VN, en-US, de-DE, v.v. |
| Có giao thức máy–máy cần ổn định? | ISO/typed numbers/currency code |
| Có sự kiện theo DST? | Test zone rules và ambiguous times |
| Có metadata đủ cho audit? | Locale/zone/currency/version theo nhu cầu |

### 17.1. Bộ test regression ưu tiên

1. Một amount với locale US và DE có formatting khác nhau.
2. NumberFormat không truyền locale tương đương default FORMAT.
3. Locale.DISPLAY có thể không giống FORMAT; không gộp.
4. Cùng một numeric value sau formatter→parser có đúng ngữ nghĩa trong case được thử.
5. Input có trailing text bị phát hiện.
6. Currency formatter hiển thị theo code của giao dịch.
7. Percent formatter dùng giá trị tỷ lệ đúng.
8. Date locale US/DE có style khác; ISO date vẫn ổn định.
9. DateTimeFormatter.withLocale trả instance mới.
10. Instant giữa hai zones có cùng instant, khác wall time.
11. MessageFormat apostrophe escaping đúng.
12. Thread pool không share mutable NumberFormat/MessageFormat sai protocol.
13. Nâng JDK/CLDR có test thay đổi chính đáng.
14. Tài nguyên UI xử lý NBSP/narrow NBSP, RTL, các scripts khác.
15. Runtime compact có `jdk.localedata` được đóng gói theo scope hỗ trợ.
16. Không dùng locale display string làm DB key hoặc signature.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Locale có phải timezone không?

**Đáp án:** Không. Locale quyết định quy ước hiển thị, `ZoneId` quyết định giờ local/offset từ một Instant.

**Câu 2.** `Locale.getDefault()` và `Locale.getDefault(Locale.Category.FORMAT)` có luôn giống nhau không?

**Đáp án:** Không nhất thiết, nhất là khi ứng dụng/hệ thống cấu hình category-specific defaults.

**Câu 3.** `NumberFormat.getNumberInstance()` dùng default nào?

**Đáp án:** Default `Locale.Category.FORMAT`.

**Câu 4.** Có nên dùng `Locale.setDefault` cho mỗi request user không?

**Đáp án:** Không. Nó thay đổi process-wide global state và dễ ảnh hưởng request khác.

**Câu 5.** `Locale.forLanguageTag("vi-VN")` hỗ trợ gì?

**Đáp án:** Tạo Locale từ BCP 47 tag; cần validation/fallback theo danh sách được sản phẩm hỗ trợ.

**Câu 6.** Vì sao dấu grouping của locale không nên hard-code?

**Đáp án:** Dữ liệu locale quy định separators; Unicode spaces và CLDR updates có thể ảnh hưởng output.

**Câu 7.** `NumberFormat.getPercentInstance` hiểu 0.125 như thế nào?

**Đáp án:** Một tỷ lệ 12.5%, định dạng theo conventions của locale; không truyền 12.5 nếu muốn 12.5%.

**Câu 8.** Người dùng locale vi-VN có giao dịch USD thì làm sao?

**Đáp án:** Giữ currencyCode USD độc lập, tạo money formatter với display locale vi-VN và đặt currency thực tế; kiểm soát precision/rounding riêng.

**Câu 9.** Vì sao `Currency.getSymbol` không dùng làm identity?

**Đáp án:** Symbol locale-dependent, có thể trùng; lưu ISO currency code.

**Câu 10.** `NumberFormat.parse("1234xyz",pos)` có thể thành công không?

**Đáp án:** Có thể parse prefix và dừng trước “xyz”; kiểm tra `ParsePosition.getIndex` và grammar domain.

**Câu 11.** `DateTimeFormatter.ofLocalizedDate(SHORT)` có làm đổi LocalDate không?

**Đáp án:** Không. Nó định dạng ngày hiện có thành text; giá trị ngày không đổi.

**Câu 12.** `DateTimeFormatter.withLocale` có thread-safe không?

**Đáp án:** DateTimeFormatter immutable/thread-safe, `withLocale` trả formatter copy được cấu hình khác.

**Câu 13.** Locale có thể quyết định múi giờ hiện tại của user không?

**Đáp án:** Không. Phải có ZoneId/preference hoặc business location context phù hợp.

**Câu 14.** Dữ liệu locale có giữ nguyên 100% từ JDK 8 sang JDK 26 không?

**Đáp án:** Không. JDK cập nhật CLDR; localized strings/patterns có thể thay đổi. JDK 26 dùng CLDR 48.

**Câu 15.** Có nên dùng `-Djava.locale.providers=COMPAT` trên Java hiện đại để giữ UI cũ không?

**Đáp án:** Không. Dữ liệu provider legacy COMPAT/JRE đã bị loại từ JDK 23; cần di chuyển sang CLDR hoặc định nghĩa contract định dạng cụ thể khi cần.

**Câu 16.** `NumberFormat` có thread-safe để share không?

**Đáp án:** Không được bảo đảm; thường phải per thread/per call hoặc đồng bộ hóa.

**Câu 17.** `MessageFormat` có tự dịch chữ trong pattern không?

**Đáp án:** Không. Nó định dạng arguments; phần bản dịch từ ResourceBundle/translation service.

**Câu 18.** Tại sao phải viết `You''ve` trong MessageFormat pattern?

**Đáp án:** Để thể hiện một apostrophe literal; một dấu nháy có ý nghĩa quote trong pattern.

**Câu 19.** Localized date SHORT có nên dùng trong JSON API không?

**Đáp án:** Không nếu cần stable machine format. Dùng ISO 8601/typed schema và timezone/offset theo nghĩa dữ liệu.

**Câu 20.** Một Locale không có country có xác định được currency mặc định quốc gia không?

**Đáp án:** Không phải lúc nào. Đối với money hãy chỉ định currencyCode; không giả định language = currency.

**Câu 21.** Tại sao test demo không in nguyên văn ngày tiếng Đức?

**Đáp án:** Vì localized text có thể thay đổi theo CLDR/JDK; demo test semantic và so sánh locale. Golden output nên pin version nếu product cần.

**Câu 22.** NumberFormat parse dùng locale German cho chuỗi nhập theo US thì sao?

**Đáp án:** Có thể lỗi hoặc diễn giải dấu không đúng nghĩa. Giữ locale input hoặc dùng machine grammar ổn định.

**Câu 23.** Khi cần một chuỗi số chính xác cố định cho đối tác, dùng factory localized hay pattern?

**Đáp án:** Dùng một wire-format/pattern/schema được thỏa thuận, rounding và symbols rõ. Localized factory dành cho human-facing output theo conventions hiện hành.

**Câu 24.** CLDR và tzdb khác gì?

**Đáp án:** CLDR chứa dữ liệu hiển thị ngôn ngữ/vùng; tzdb chứa rules múi giờ/DST. Locale và timezone cần được quản lý riêng.

**Câu 25.** Vì sao cần kiểm thử ở runtime production chứ không chỉ laptop?

**Đáp án:** JDK/provider/CLDR version, timezone database, OS preferences và runtime-image locale coverage có thể khác nhau.

## 19. Tổng kết

- **`Locale` là định danh quy ước hiển thị**, không phải timezone, currency transaction hay một bản snapshot của mọi format data.
- **`Locale.Category.FORMAT`** là category mặc định cho number/date/currency formatting; **`DISPLAY`** cho tên locale/UI. Một JVM backend nhiều người dùng nên dùng locale **tường minh** theo request.
- **`NumberFormat`**, `DecimalFormat`, `DecimalFormatSymbols`, `Currency` giúp render số, percent và tiền; quy tắc precision/rounding/currencyCode là trách nhiệm riêng của ứng dụng.
- **`DateTimeFormatter.ofLocalizedDate/Time/DateTime`** kết hợp `FormatStyle` và `withLocale`; formatter bất biến và an toàn để tái sử dụng. **ZoneId** vẫn phải được chỉ định riêng.
- **`NumberFormat.parse` có thể lenient hoặc parse prefix**; nếu dữ liệu cần canonical validation, chỉ check non-null là không đủ.
- **`MessageFormat`** ghép thông báo với number/date subformats, nhưng translation content và luật apostrophe cần test riêng.
- **Dữ liệu locale CLDR không cố định giữa các bản JDK**: Oracle JDK 26 sử dụng CLDR 48, và provider legacy COMPAT/JRE đã được loại khỏi JDK 23+.
- **Định dạng theo locale hiện hành cho UI**, còn **ISO/typed numeric/currency code** cho lưu trữ và trao đổi dữ liệu cần bền vững.
- **Java 8 runnable demo đã được kiểm thử** về FORMAT default, number/date locale variation, parser prefix, currencies, timezone, MessageFormat và explicit decimal profile.
- Các API và thực hành chính đều **còn áp dụng hiện nay**, tuân thủ ghi chú chỉ trình bày kiến thức không legacy.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Locale, Categories và BCP 47](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.html)
- [Oracle Java SE 8 — Locale.Category](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.Category.html)
- [Oracle Java SE 8 — NumberFormat](https://docs.oracle.com/javase/8/docs/api/java/text/NumberFormat.html)
- [Oracle Java SE 8 — DecimalFormat](https://docs.oracle.com/javase/8/docs/api/java/text/DecimalFormat.html)
- [Oracle Java SE 8 — DecimalFormatSymbols](https://docs.oracle.com/javase/8/docs/api/java/text/DecimalFormatSymbols.html)
- [Oracle Java SE 8 — Currency](https://docs.oracle.com/javase/8/docs/api/java/util/Currency.html)
- [Oracle Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 8 — FormatStyle](https://docs.oracle.com/javase/8/docs/api/java/time/format/FormatStyle.html)
- [Oracle Java SE 8 — MessageFormat](https://docs.oracle.com/javase/8/docs/api/java/text/MessageFormat.html)
- [Oracle Java SE 8 — ResourceBundle](https://docs.oracle.com/javase/8/docs/api/java/util/ResourceBundle.html)
- [Oracle Java SE 26 — LocaleServiceProvider và CLDR versions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [Oracle JDK 26 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html)
- [Oracle JDK 8 → JDK 26 Migration Guide — Locale Data](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [Oracle Java SE 26 — NumberFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html)
