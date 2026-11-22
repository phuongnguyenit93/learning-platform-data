# Kiểm thử locale, charset, múi giờ và dữ liệu quốc tế hóa

Nâng cấp JDK không chỉ là kiểm tra class file, API đã bị loại bỏ hoặc thời gian đáp ứng của ứng dụng. Cùng một source code Java có thể tạo ra **chuỗi ngày khác nhau**, **dấu phân cách số khác nhau**, **bytes khác nhau khi ghi file**, hoặc **kết quả tính thời điểm khác nhau** sau khi chuyển JDK, hệ điều hành, container image hay bản cập nhật timezone database. Những thay đổi này có thể không gây exception: hệ thống vẫn chạy nhưng dữ liệu trao đổi và quyết định nghiệp vụ sai.

Các đường xử lý liên quan tới **locale**, **charset**, **múi giờ** và **quốc tế hóa (internationalization, i18n)** đặc biệt nhạy cảm. Ví dụ, ký tự tiếng Việt ở dạng tổ hợp có thể trông giống ký tự dựng sẵn nhưng không bằng nhau khi so sánh trực tiếp; dấu phẩy ở `1,234` có thể biểu thị dấu nhóm hoặc dấu thập phân tùy locale; giờ `02:30` tại một nơi có daylight saving time (DST) có thể không tồn tại vào ngày chuyển giờ; file được ghi bằng charset mặc định trên JDK cũ có thể bị đọc khác khi lên JDK mới.

Bài học hướng dẫn thiết kế **kiểm thử hồi quy** cho các vấn đề đó trong ngữ cảnh Java Advance Compatibility Migration: xác định hợp đồng dữ liệu, cô lập giá trị mặc định của môi trường, tạo bộ dữ liệu kiểm thử có chủ đích, chạy ma trận nhiều JDK/locale/charset/timezone và xử lý khác biệt theo ý nghĩa nghiệp vụ thay vì chỉ so sánh snapshot chuỗi.

## 1. Vì sao cùng code Java có thể cho kết quả khác?

Một kết quả xử lý văn bản hoặc thời gian có thể phụ thuộc vào nhiều lớp:

~~~text
Source code + dependencies
            |
            v
       JDK runtime
            |
            +--> Phiên bản CLDR / locale data
            +--> Unicode properties / normalization data
            +--> Default charset / charset mappings
            +--> TZDB (time zone rules)
            |
            v
       Process environment
            |
            +--> Default Locale
            +--> Default ZoneId / user.timezone
            +--> OS/container locale & timezone
            +--> JAVA_TOOL_OPTIONS / JVM options
            |
            v
        Dữ liệu đầu vào
            |
            +--> Bytes + encoding
            +--> Locale của người dùng
            +--> Timezone và offset của sự kiện
            +--> Cách biểu diễn Unicode
            |
            v
       Parse / Format / Compare
            |
            v
       Data, response, business decision
~~~

Ngay cả khi JDK version không đổi, cập nhật container image, database, host settings hoặc tzdata cũng có thể tạo khác biệt. Trong một đợt migration thực tế, nhiều biến số thường thay đổi cùng lúc, nên trước tiên cần tách nguyên nhân.

### 1.1. Phân loại bốn nhóm thay đổi

| Nhóm | Đầu vào/thiết lập ảnh hưởng | Ví dụ regression |
|---|---|---|
| **Locale** | `Locale`, CLDR, language/region | Định dạng ngày, dấu phân cách số, case conversion, collation |
| **Charset** | `Charset.defaultCharset()`, decode/encode APIs | Tiếng Việt bị lỗi dấu khi đọc file, sai checksum, message bị mojibake |
| **Timezone** | `ZoneId`, TZDB, system default, DST | Lịch hẹn lệch giờ, tính khoảng thời gian sai, timestamp khác |
| **i18n/Unicode** | Normalization, properties, resource bundles, Unicode data | Không tìm được bản dịch, trùng/khác định danh, regex validation thay đổi |

Một testcase tốt phải chỉ rõ **đầu vào, locale, charset, zone, JDK và kết quả kỳ vọng**. Câu “chạy tốt trên máy tôi” thiếu các yếu tố này.

### 1.2. Source compatibility khác behavioral compatibility

Mã sau vẫn biên dịch:

~~~java
String output = java.text.NumberFormat.getInstance()
    .format(1234.56);
~~~

Nhưng kết quả có thể phụ thuộc default locale của process và dữ liệu locale trong runtime. Vì vậy việc biên dịch thành công trên JDK mới không chứng minh output còn tương thích với consumer cũ.

Ngược lại, nếu một hệ thống đã **cố ý** dùng định dạng theo ngôn ngữ người dùng, việc CLDR cập nhật một quy tắc có thể là thay đổi đúng theo ngôn ngữ, không phải bug cần ép trở lại output cũ. Test phải phân biệt hợp đồng ổn định ở cấp machine protocol và trình bày cho con người.

## 2. Bắt đầu từ hợp đồng dữ liệu

Trước khi viết JUnit tests, hãy phân loại nơi nào cần output bất biến và nơi nào được phép thay đổi theo locale/timezone.

| Trường/hành vi | Hợp đồng nên rõ ràng | Kiểu kiểm thử |
|---|---|---|
| Mã giao dịch | ASCII với grammar cố định | Exact input/output |
| Dữ liệu JSON | UTF-8 theo giao thức và schema | Byte round-trip, Unicode fixtures |
| Số tiền lưu DB | Đơn vị, precision, currency tường minh | Semantic equality, không dùng số đã format |
| Số tiền hiển thị | Locale/currency của người dùng | Format theo locale, semantic + snapshot có kiểm soát |
| Timestamp API | UTC instant / offset / zone được ghi rõ | ISO 8601 parse/round-trip |
| Lịch hẹn địa phương | `LocalDateTime` + region `ZoneId` + DST policy | Gap/overlap tests |
| Tên người | Unicode, normalization và giới hạn độ dài | NFC/NFD, supplementary, combining marks |
| Sắp xếp danh sách | Collation theo locale đã định | Thứ tự các trường hợp quan trọng |
| Thông báo đa ngôn ngữ | ResourceBundle locale/fallback | Missing keys, placeholders, translations |

**Không lưu chuỗi đã format theo locale như dữ liệu số học hoặc thời gian chuẩn để trao đổi giữa các service**, trừ khi giao thức đã quy định chính xác định dạng đó. Ưu tiên lưu giá trị chuẩn và chỉ format ở ranh giới hiển thị.

### 2.1. Bộ câu hỏi định nghĩa test

Mỗi đường dữ liệu nên trả lời:

1. Ký tự đi vào dưới dạng bytes hay `String`? Encoding từ đâu?
2. Locale lấy từ user/account, HTTP request, environment hay JVM default?
3. Ngày giờ đại diện cho **instant**, **giờ địa phương** hay **lịch theo zone**?
4. Kết quả format chỉ để hiển thị hay dùng làm key/API contract?
5. Có bước normalize Unicode, lowercase hoặc collation không?
6. Nếu JDK locale/TZDB data thay đổi, đầu ra nào được phép đổi?
7. Hệ thống cũ có tiếp tục parse được dữ liệu do phiên bản mới viết không?

Nếu không phân định, một assertion snapshot “giống hệt JDK cũ” có thể vừa quá cứng ở UI, vừa quá lỏng ở API.

## 3. `Locale` trong Java: chọn mặc định hay truyền tường minh?

`java.util.Locale` mô tả thông tin ngôn ngữ, vùng lãnh thổ và các subtags liên quan. Nó **không** tự chứa bộ quy tắc định dạng; các class như `DateTimeFormatter`, `NumberFormat`, `Collator` dùng dữ liệu locale của runtime.

Ví dụ:

~~~java
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale french = Locale.FRANCE;
Locale turkish = Locale.forLanguageTag("tr-TR");
Locale neutral = Locale.ROOT;

System.out.println(vietnamese.toLanguageTag()); // vi-VN
~~~

Dùng `Locale.forLanguageTag(...)` cho language tags theo BCP 47. Locale cũng có extensions như numbering system/calendar; với sản phẩm đa thị trường, không nên rút gọn tất cả về hai chữ cái ngôn ngữ.

### 3.1. Default locale là trạng thái môi trường

~~~java
Locale current = Locale.getDefault();
Locale format = Locale.getDefault(Locale.Category.FORMAT);
Locale display = Locale.getDefault(Locale.Category.DISPLAY);
~~~

Hai category `FORMAT` và `DISPLAY` có mục đích khác nhau. Một ứng dụng có thể cần ngôn ngữ menu khác với định dạng ngày/số; việc truyền `Locale.getDefault()` vào mọi chỗ có thể không đáp ứng thiết kế.

Default locale có thể phụ thuộc thiết lập OS, environment và JVM configuration. Khi di chuyển từ host sang container, giá trị này có thể đổi dù source và database không đổi.

### 3.2. Tránh dùng default locale cho protocol

**Không nên:**

~~~java
String reportValue =
    String.format("%.2f", 1234.56);
~~~

Vì `String.format` không truyền locale sử dụng default locale, output có thể khác dấu thập phân. Nếu chuỗi là giá trị protocol, hãy định nghĩa cách biểu diễn bất biến:

~~~java
String machineValue =
    String.format(Locale.ROOT, "%.2f", 1234.56);
~~~

Nếu là UI, truyền locale của người dùng:

~~~java
String displayValue =
    String.format(Locale.forLanguageTag("vi-VN"),
                  "%.2f", 1234.56);
~~~

`Locale.ROOT` thích hợp cho một số phép format/case mapping không phụ thuộc ngôn ngữ, nhưng không phải lựa chọn đúng cho mọi nội dung UI.

### 3.3. Không đổi default locale trong parallel tests

~~~java
Locale.setDefault(Locale.FRANCE);
~~~

Lệnh trên đổi **trạng thái toàn JVM**; các test chạy song song hoặc thư viện khác có thể thấy giá trị mới. Dù có `finally` đặt lại, test vẫn có thể race với luồng khác.

Hướng ưu tiên: truyền `Locale` tường minh vào code đang test. Nếu cần kiểm thử code legacy phụ thuộc JVM defaults, hãy chạy **một test process/fork riêng** được cấu hình default locale từ startup.

## 4. Locale data và CLDR thay đổi qua JDK

Java sử dụng dữ liệu locale để format ngày tháng, chữ số, currency, tên quốc gia, lịch và nhiều chức năng khác. Một phần dữ liệu này đến từ **Unicode Common Locale Data Repository (CLDR)**.

### 4.1. Các mốc cần biết

- **JDK 9 – JEP 252:** chuyển hướng dùng dữ liệu CLDR ưu tiên so với dữ liệu locale JRE legacy trong mặc định của runtime.
- **JDK 18 – JEP 400:** default charset trở thành UTF-8 theo chính sách chuẩn, là thay đổi khác với CLDR nhưng thường cùng gây hồi quy i18n.
- Các JDK feature/update mới có thể cập nhật CLDR, Unicode và dữ liệu locale.
- Những provider locale legacy như `COMPAT` đã bị thay đổi/loại bỏ ở những JDK hiện đại; không nên dựa lâu dài vào `java.locale.providers=COMPAT,...` để đóng băng định dạng cũ.

Nếu ứng dụng từng dùng lựa chọn provider legacy qua property `java.locale.providers`, kiểm tra **release notes của đúng runtime đích** và loại bỏ giả định rằng provider cũ luôn tồn tại.

### 4.2. Format output không phải chuẩn interchange bất biến

Ví dụ:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

Locale fr = Locale.FRANCE;
String text = NumberFormat.getNumberInstance(fr)
    .format(1234567.89);

System.out.println(text);
~~~

Chuỗi có thể dùng dấu thập phân và dấu nhóm đặc thù locale; ký tự nhóm có thể là một dạng Unicode space chứ không phải ASCII space. Dữ liệu CLDR và JDK version có thể ảnh hưởng ký tự cụ thể.

Nếu test đòi `"1 234 567,89"` bằng một ASCII space ở mọi JDK, test có thể thất bại dù implementation đúng theo dữ liệu locale mới. Cần quyết định output của UI được phép thay đổi tới mức nào.

### 4.3. Test regression nên có hai tầng

**Tầng hợp đồng ngữ nghĩa:** chuỗi format có thể parse về cùng một giá trị; currency code đúng; ngày đúng; người dùng nhận output theo locale yêu cầu.

**Tầng presentation snapshot:** khi giao diện yêu cầu ký tự, thông điệp hoặc format chính xác, lưu golden fixtures theo locale/JDK chính thức và review có chủ đích các thay đổi CLDR.

Không được “update all snapshots” sau khi nâng JDK mà chưa xác minh sự thay đổi có được nghiệp vụ/UX chấp nhận không.

## 5. Kiểm thử định dạng và parse số

`NumberFormat`, `DecimalFormat` và `DecimalFormatSymbols` có hành vi theo locale. `Double.parseDouble` và `BigDecimal(String)` lại sử dụng grammar số độc lập theo dạng Java/API, không phải các hàm parse locale-specific.

### 5.1. Dùng `NumberFormat` đúng mục đích

~~~java
import java.text.NumberFormat;
import java.util.Locale;

Locale fr = Locale.FRANCE;
NumberFormat formatter =
    NumberFormat.getNumberInstance(fr);

formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);

String display = formatter.format(1234.5);
System.out.println(display);
~~~

Giá trị hiển thị có thể mang dấu nhóm, dấu thập phân và Unicode spacing theo dữ liệu locale. Đừng lấy nó làm key lưu trữ hoặc chuyển thẳng cho một service đang chờ chuỗi thập phân ASCII.

### 5.2. Parse phải kiểm tra toàn chuỗi

`NumberFormat.parse(String)` có thể parse một **prefix** và bỏ phần đuôi tùy parser. Một testcase “parser không ném exception” chưa đủ nếu mã dùng đầu vào làm số tiền.

Có thể kiểm tra `ParsePosition`:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocaleNumberParser {
    public static Number parseEntirely(String text, Locale locale) {
        NumberFormat format =
            NumberFormat.getNumberInstance(locale);

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null ||
            position.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                "Invalid localized number");
        }
        return parsed;
    }
}
~~~

Đối với tiền tệ và decimal precision, dùng kiểu lưu trữ phù hợp như `BigDecimal`, đồng thời xem khả năng parse-to-`BigDecimal` của `DecimalFormat` (với `setParseBigDecimal(true)`) và xác định rõ cách làm tròn.

### 5.3. Không so sánh tiền dưới dạng `double`

~~~java
double amount = 0.1 + 0.2;
System.out.println(amount == 0.3); // false
~~~

Sai số floating-point không phải lỗi locale. Nhưng khi kết hợp format/parse, nó có thể làm test khó chẩn đoán. Với giá trị tiền, cần quy định đơn vị, currency, precision và rounding mode.

Ví dụ `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("1234.565")
    .setScale(2, RoundingMode.HALF_UP);

System.out.println(amount.toPlainString()); // 1234.57
~~~

Dạng `toPlainString()` phù hợp hơn cho một số hợp đồng số thập phân bất biến; không nên dùng chuỗi `NumberFormat` dành cho UI làm format trao đổi máy–máy.

### 5.4. Currency symbols cũng có thể đổi

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

NumberFormat money =
    NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("vi-VN"));

money.setCurrency(Currency.getInstance("VND"));
System.out.println(money.format(1234567));
~~~

Ký hiệu, vị trí ký hiệu, dấu nhóm và khoảng trắng có thể phụ thuộc locale data. Test nên xác nhận **currency code và amount semantics**, rồi kiểm soát UI snapshot riêng khi cần.

### 5.5. `NumberFormat` không an toàn để chia sẻ tùy tiện giữa threads

Một số formatter của `java.text` là mutable và không được thiết kế để chia sẻ không đồng bộ. Trong các concurrent tests, tạo formatter riêng cho từng request/test hoặc quản lý đồng bộ phù hợp. Nếu test bị flaky khi chạy song song, nguyên nhân có thể là shared formatter thay vì JDK locale data.

## 6. Case conversion, so sánh và sắp xếp theo ngôn ngữ

### 6.1. Chữ I trong tiếng Thổ Nhĩ Kỳ

~~~java
import java.util.Locale;

System.out.println("I".toLowerCase(Locale.ROOT)); // i
System.out.println(
    "I".toLowerCase(Locale.forLanguageTag("tr-TR"))
); // ı (dotless i)
~~~

Nếu hệ thống dùng `String.toLowerCase()` không truyền locale để chuẩn hóa technical identifier, một default locale khác có thể đổi key và gây lỗi lookup/trùng lặp.

Với định danh kỹ thuật độc lập ngôn ngữ, cân nhắc `Locale.ROOT` cùng quy tắc charset/normalization tường minh. Với tên riêng và văn bản tự nhiên, có thể cần case mapping theo locale.

### 6.2. Case folding không hoàn toàn đồng nghĩa lowercase

Việc so sánh không phân biệt hoa/thường có thể liên quan nhiều ký tự Unicode và quy tắc đặc biệt. `equalsIgnoreCase`, `toLowerCase(Locale)`, regex `CASE_INSENSITIVE` và Unicode-aware case folding không phải các giải pháp thay thế lẫn nhau trong mọi ngôn ngữ.

Nếu một ứng dụng dùng case-insensitive usernames, cần thiết kế canonicalization và uniqueness policy rõ ràng; không lấy `equalsIgnoreCase` như một bảo đảm bảo mật/phát hiện confusable toàn diện.

### 6.3. Collation với `Collator`

~~~java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

String[] names = {"An", "Ánh", "Anh", "Ân"};
Collator collator =
    Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

Arrays.sort(names, collator);
System.out.println(Arrays.toString(names));
~~~

`Collator` dùng quy tắc so sánh theo locale và có mức độ so sánh (*strength*) như primary, secondary, tertiary. Quy tắc thứ tự có thể thay đổi theo locale data hoặc cấu hình.

Nếu hệ thống lưu *sort keys* hay tạo search index dựa trên collation, nâng JDK có thể đòi **reindex** khi quy tắc thay đổi; không chỉ rerun unit tests.

### 6.4. Không dùng collation theo người dùng để tạo định danh dữ liệu bền vững

Dùng các sort key phụ thuộc locale/JDK làm khóa phân vùng, unique key hoặc chữ ký số có thể làm kết quả không ổn định qua migration. Hãy dùng một canonical representation đã định nghĩa rõ cho hợp đồng máy–máy; chỉ dùng collation cho tìm kiếm và trình bày khi phù hợp.

## 7. ResourceBundle và bản dịch giao diện

Java hỗ trợ tài nguyên đa ngôn ngữ qua `ResourceBundle`. Một ứng dụng có thể chứa:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_fr.properties
  messages_tr.properties
~~~

Ví dụ:

~~~properties
# messages.properties
welcome=Welcome
items=You have {0} items
~~~

~~~properties
# messages_vi.properties
welcome=Xin chào
items=Bạn có {0} mục
~~~

Code:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
    ResourceBundle.getBundle("messages", locale);

String template = bundle.getString("items");
String output = new MessageFormat(template, locale)
    .format(new Object[] {5});

System.out.println(output);
~~~

### 7.1. Fallback và missing translation

Một request `vi-VN` có thể dùng bundle `messages_vi` khi không có `messages_vi_VN`. Nếu key không có ở bundle được chọn, framework có thể fallback theo quy tắc `ResourceBundle` hoặc ném `MissingResourceException`.

Các test nên kiểm tra:

- Key bắt buộc tồn tại trong locales được hỗ trợ.
- Bundle fallback đúng khi locale cụ thể thiếu.
- Key không bị đổi tên giữa các phiên bản.
- Placeholder indices và types phù hợp.
- Format của parameter theo locale mong đợi.
- Không có text lẫn ngôn ngữ ngoài ý muốn ở màn hình quan trọng.

### 7.2. Encoding của properties files

Đừng nhầm hai API:

- `java.util.Properties.load(InputStream)` dùng quy tắc **ISO-8859-1** và hỗ trợ Unicode escapes `\uXXXX`.
- `Properties.load(Reader)` đọc ký tự đã được `Reader` decode theo charset mà caller chọn.

Ví dụ:

~~~java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

Properties props = new Properties();

try (InputStream input =
        getClass().getResourceAsStream("/config.properties");
     InputStreamReader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8)) {
    props.load(reader);
}
~~~

Ví dụ giả định resource tồn tại; trong code thực tế phải kiểm tra `input != null` trước khi tạo `InputStreamReader` và xử lý lỗi một cách phù hợp.

`PropertyResourceBundle` có quy tắc encoding riêng đã được cải tiến ở **JDK 9 (JEP 226)**: theo mặc định có cơ chế đọc UTF-8 và fallback trong trường hợp thích hợp để tương thích legacy. Không đồng nhất việc đọc bundle này với `Properties.load(InputStream)`.

### 7.3. `MessageFormat` có cú pháp quote riêng

Trong các template theo ngôn ngữ, dấu nháy đơn có ý nghĩa escape đặc biệt đối với `MessageFormat`. Một bản dịch chứa apostrophe có thể hiển thị sai hoặc làm mất placeholder nếu biên dịch template không đúng.

Test cần dùng **bản dịch thật** với dấu nháy, braces, pluralization và parameter values. Không chỉ xác nhận bundle đọc ra chuỗi.

### 7.4. Không hot-reload bundle theo cách gây flaky tests

`ResourceBundle` có caching, class loader và fallback behavior. Khi test thay nội dung properties trong cùng JVM, có thể phải xử lý cache bằng API phù hợp hoặc tạo isolated process/class loader. Tốt hơn, trong CI các resource files thường là immutable artifacts và test chạy trên artifact thật.

## 8. Charset: `String` và bytes là hai lớp khác nhau

`String` là chuỗi ký tự ở cấp Java API, còn file/network/storage xử lý **bytes**. Charset xác định cách encode/decode giữa hai lớp.

~~~text
Java String
     |
     | encode(UTF-8)
     v
Bytes  ------> File / API / Queue / DB
     |
     | decode(UTF-8)
     v
Java String
~~~

Nếu phía ghi dùng Windows-1252 hoặc charset hệ thống còn phía đọc mặc định UTF-8, dữ liệu có thể bị lỗi dấu hoặc xuất hiện ký tự thay thế `�` (*replacement character*).

### 8.1. Các API dễ phụ thuộc default charset

~~~java
byte[] bytes = text.getBytes();        // Không truyền charset
String decoded = new String(bytes);    // Không truyền charset
~~~

Các constructor như `InputStreamReader(InputStream)` và `OutputStreamWriter(OutputStream)` khi không chỉ rõ charset cũng có thể dùng default charset theo API.

Nếu nguồn dữ liệu có hợp đồng UTF-8, truyền tường minh:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes =
    text.getBytes(StandardCharsets.UTF_8);

String decoded =
    new String(bytes, StandardCharsets.UTF_8);
~~~

Các thao tác này ổn định hơn qua JDK và OS.

### 8.2. JDK 18 và JEP 400

**JEP 400 – UTF-8 by Default** đưa default charset của Java APIs trong phạm vi JEP về UTF-8 từ JDK 18. Trước đó, default charset có thể phụ thuộc OS/locale của môi trường.

Hệ quả migration:

- Một file được ghi bằng API không truyền charset ở JDK cũ trên Windows có thể dùng charset native.
- JDK mới có thể đọc cùng bytes như UTF-8 và nhận kết quả khác.
- Code truyền charset rõ ràng thường ít bị tác động hơn.
- Charset của **console I/O** có các cân nhắc riêng, không nên suy từ `Charset.defaultCharset()` rằng mọi terminal cũng sử dụng UTF-8.

Một số JDK hỗ trợ cách cấu hình tương thích như `-Dfile.encoding=COMPAT` theo JEP 400. Đây là **biện pháp chuyển tiếp** trong những runtime hỗ trợ, không phải thay thế lâu dài cho việc chỉ định charset rõ ràng. Không dựa vào việc đặt `file.encoding` thành một tên charset tùy ý nếu runtime/JDK không bảo đảm hành vi đó.

### 8.3. Kiểm tra charset thực tế

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
System.out.println(System.getProperty("file.encoding"));
System.out.println(System.getProperty("native.encoding"));
~~~

`native.encoding` là thông tin môi trường có trong những JDK hiện đại; tính sẵn có và giá trị cần được xác nhận trên bản JDK cụ thể.

Trong test, cần ghi chính xác runtime/vendor/build và startup options. Chỉ xem `file.encoding` trong environment rồi suy ra bytes thực tế là chưa đủ nếu code dùng một charset khác khi tạo `Reader`.

## 9. Đọc/ghi file phải khai báo encoding

### 9.1. Dùng `StandardCharsets.UTF_8`

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("data", "customers.csv");

Files.writeString(file,
    "id,name\n1,Nguyễn Ánh\n",
    StandardCharsets.UTF_8);

String text =
    Files.readString(file, StandardCharsets.UTF_8);
~~~

`Files.readString` và `writeString` có những overload với mặc định UTF-8 trong API hiện đại, nhưng truyền charset tường minh vẫn khiến hợp đồng dễ kiểm tra. Với `Path.of`/`readString`, cần đảm bảo Java runtime mục tiêu hỗ trợ các API này.

### 9.2. Không tự động dùng UTF-8 để đọc legacy bytes

Nếu hệ thống lưu file trong Windows-1258, Shift_JIS, ISO-8859-1 hoặc một charset legacy khác, đọc ngay bằng UTF-8 sẽ gây lỗi hoặc sai dữ liệu.

Quy trình chuyển đổi:

1. Xác định encoding thật từ giao thức, metadata hoặc nguồn phát hành.
2. Decode bằng charset nguồn.
3. Validate nội dung Unicode và xử lý malformed bytes theo chính sách.
4. Encode sang UTF-8 hoặc charset đích.
5. Đối chiếu dữ liệu, số bản ghi và checksum nếu phù hợp.
6. Ghi metadata version/encoding sau chuyển đổi.

Không thể xác định chính xác charset cho mọi file chỉ bằng cách “nhìn bytes”; các byte sequence đôi khi hợp lệ ở nhiều bảng mã. Khi không có nguồn tin cậy, cần quy trình nhận diện và phê duyệt dữ liệu.

### 9.3. Kiểm soát malformed/unmappable input

Mặc định của một số API decode có thể thay bytes lỗi bằng replacement character. Với dữ liệu nghiệp vụ quan trọng, muốn **phát hiện sai encoding** thay vì âm thầm thay ký tự, dùng `CharsetDecoder`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
    }
}
~~~

Đây là cách hữu ích khi parse file có chữ ký số, dữ liệu tài chính hoặc các hợp đồng yêu cầu không được làm mất ký tự. Với dữ liệu hiển thị của người dùng, chính sách replacement có thể khác, nhưng phải tường minh.

### 9.4. BOM và newline

UTF-8 có thể có byte order mark (BOM) ở đầu file. Một parser CSV/JSON tự viết có thể coi BOM là một phần của field đầu tiên nếu không xử lý. UTF-16 có yêu cầu byte order và BOM khác.

Line endings cũng thay đổi theo OS (`\n`, `\r\n`). Khi so sánh file ở byte level, cần tách **thay đổi newline** và **thay đổi charset**. Đừng normalize tất cả trước kiểm thử nếu giao thức thật sự đòi byte-for-byte match.

## 10. HTTP, CSV, JSON, database và queue

Charset migration thường lộ ra ở điểm giao tiếp giữa service.

### 10.1. HTTP Content-Type và body bytes

Nếu một endpoint nhận hoặc trả text, cần xác định charset theo media type và giao thức. Với JSON, hệ thống hiện đại thường dùng UTF-8 theo tiêu chuẩn tương ứng; không nên dựa vào default charset của một servlet container hoặc `OutputStreamWriter` không chỉ định encoding.

Ví dụ với Java HTTP client, khi tự tạo body từ text:

~~~java
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String json = "{\"name\":\"Nguyễn Ánh\"}";

HttpRequest.BodyPublisher body =
    HttpRequest.BodyPublishers.ofString(
        json, StandardCharsets.UTF_8);
~~~

Khi test HTTP, kiểm tra **bytes on the wire**, response header, client decode policy và nội dung round-trip, không chỉ so sánh String sau khi framework đã tự chuyển đổi.

### 10.2. CSV và file import/export

CSV không tự chỉ định charset, separator, quote và newline. Một file tiếng Việt xuất từ hệ thống cũ có thể dùng encoding khác UTF-8, và dấu phân cách cột còn có thể thay theo locale của spreadsheet tool.

Regression test nên có:

- UTF-8 có/không BOM theo hợp đồng.
- Tên tiếng Việt, tiếng Nhật, Arabic, emoji và combining marks.
- Dấu phẩy, chấm phẩy, dấu nháy và newline bên trong quoted fields.
- Dữ liệu rỗng/null, khoảng trắng Unicode.
- Kích thước lớn, chunk boundaries trong streaming parser.
- Round-trip export → import và byte-level assertions khi cần.

### 10.3. JDBC/database collation

JDBC driver trao đổi dữ liệu theo protocol/database encoding, không nhất thiết dùng `Charset.defaultCharset()` trực tiếp. Tuy nhiên, application có thể tạo bytes riêng, hoặc database collation có thể điều khiển thứ tự/uniqueness của text.

Kiểm tra:

- Database/server/client encoding.
- Cách bind `String`/`NString` và Unicode columns.
- Collation và cách so sánh case/accent.
- Index/search keys cần rebuild khi collation thay đổi.
- Migration scripts đọc file SQL bằng encoding nào.
- Quy tắc truncate theo bytes, code points hay characters.

Một unique constraint có collation mới có thể nhận diện hai chuỗi “trùng” khác trước. Đây là regression có khả năng ảnh hưởng dữ liệu chứ không chỉ giao diện.

### 10.4. Kafka/message broker và object storage

Nếu payload ở dạng bytes, producer và consumer phải thống nhất serialization/charset. Một consumer Java mới mặc định UTF-8 không thể “sửa” bytes đã được producer legacy ghi theo bảng mã khác mà không có metadata.

Nếu event được lưu lâu, nên có schema/version và format bất biến. Khi thay codec, test consumer cũ đọc dữ liệu do producer mới tạo và ngược lại theo hợp đồng tương thích.

## 11. Unicode normalization và giới hạn ký tự

Unicode cho phép một số chuỗi nhìn giống nhau nhưng có các chuỗi code point khác nhau.

Ví dụ tiếng Việt:

~~~java
String nfcLike = "ắ";               // U+1EAF
String decomposed = "a\u0306\u0301"; // a + breve + acute

System.out.println(nfcLike.equals(decomposed));
// false
~~~

Để so sánh canonical-equivalent theo chính sách chọn NFC:

~~~java
import java.text.Normalizer;

String a =
    Normalizer.normalize(nfcLike, Normalizer.Form.NFC);
String b =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(a.equals(b)); // true
~~~

### 11.1. NFC/NFD và NFKC/NFKD khác nhau

- **NFC/NFD:** canonical composition/decomposition.
- **NFKC/NFKD:** compatibility normalization, có thể làm mất những phân biệt có ý nghĩa trong một số dữ liệu.

Không áp dụng NFKC cho mọi tên riêng hoặc hồ sơ pháp lý chỉ vì muốn “chuẩn hóa tối đa”. Cần chọn form theo hợp đồng dữ liệu và lưu bản gốc khi có yêu cầu.

### 11.2. `String.length()` không đếm ký tự hiển thị

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(
    emoji.codePointCount(0, emoji.length())
); // 1 Unicode code point
~~~

Một grapheme cluster còn có thể gồm nhiều code points, ví dụ emoji sequence nối bằng zero-width joiner hoặc chữ có dấu kết hợp. Nếu UI giới hạn “20 ký tự”, cần định nghĩa đơn vị là bytes, UTF-16 code units, code points hay grapheme clusters.

### 11.3. Kiểm tra phân loại Unicode

`Character.isLetter`, `isDigit` và regex Unicode properties có thể phụ thuộc dữ liệu Unicode của JDK. Những code points mới được bổ sung có thể được nhận diện khác giữa các JDK.

Ví dụ:

~~~java
boolean isUnicodeDigit = Character.isDigit('١');
boolean isAsciiDigit = '١' >= '0' && '١' <= '9';

System.out.println(isUnicodeDigit); // true
System.out.println(isAsciiDigit);   // false
~~~

Nếu mã giao dịch chỉ chấp nhận ASCII digits, dùng chính sách rõ ràng thay vì `Character.isDigit`. Nếu tên người chấp nhận nhiều hệ chữ viết, cần test thêm dấu kết hợp, code point ngoài BMP và các script sản phẩm hỗ trợ.

### 11.4. Không dùng normalizer như bộ chống giả mạo

Một số ký tự thuộc script khác nhau nhìn tương tự nhau (*confusables*). NFC không biến mọi ký tự nhìn giống nhau thành một giá trị. Với username/định danh nhạy cảm, cần thêm chính sách mixed-script, uniqueness và chống spoofing phù hợp.

## 12. Java time API: chọn đúng loại dữ liệu

`java.time` phân biệt rõ **thời điểm tuyệt đối** và **thời gian biểu diễn theo lịch địa phương**.

| Type | Thông tin lưu | Mục đích |
|---|---|---|
| `Instant` | Điểm trên UTC timeline | Timestamp sự kiện, audit log, ordering |
| `LocalDate` | Ngày không gắn zone | Ngày sinh, ngày lễ, ngày kế toán |
| `LocalTime` | Giờ trong ngày không gắn zone | Giờ mở cửa theo lịch |
| `LocalDateTime` | Ngày/giờ local, không zone/offset | Giờ hẹn do người dùng nhập trước khi gắn zone |
| `OffsetDateTime` | Ngày/giờ + UTC offset | Truyền timestamp có offset |
| `ZonedDateTime` | Ngày/giờ + region zone + offset hiện thời | Lịch hẹn phụ thuộc DST/rules vùng |
| `Duration` | Lượng thời gian trên timeline | Timeout, elapsed seconds |
| `Period` | Khoảng lịch theo năm/tháng/ngày | Cộng tháng, lịch thanh toán |
| `ZoneId` | Region ID hoặc offset | `Asia/Ho_Chi_Minh`, `America/New_York` |
| `Clock` | Nguồn thời gian trừu tượng | Viết test deterministic |

**Không dùng `LocalDateTime` một mình để đại diện cho một instant toàn cầu.** Nó không chứa offset/zone nên nhiều instant có thể ứng với cùng local date-time tại vùng có DST overlap.

### 12.1. Persist event timestamps như instant

~~~java
import java.time.Instant;

Instant createdAt = Instant.parse(
    "2024-10-01T08:30:00Z");

System.out.println(createdAt.toString());
~~~

Định dạng `Instant.toString()` phù hợp cho nhiều hợp đồng ISO 8601/UTC. Khi trình bày cho người dùng, convert sang zone và locale phù hợp, không sửa giá trị `Instant` đang lưu.

### 12.2. Hiển thị instant theo vùng của người dùng

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant event = Instant.parse(
    "2024-10-01T08:30:00Z");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime local = event.atZone(zone);

System.out.println(local);
~~~

Với múi giờ Việt Nam ở mốc ngày ví dụ, UTC+07:00 được áp dụng. Nhưng **không hard-code `+07:00` cho toàn bộ mọi vùng/thời điểm** và không dùng một fixed offset khi cần biểu diễn các quy tắc vùng có DST.

## 13. Default timezone không phải dữ liệu nghiệp vụ

~~~java
import java.time.ZoneId;

ZoneId current = ZoneId.systemDefault();
System.out.println(current);
~~~

Giá trị này có thể khác giữa laptop, host Linux, container và server CI. Dùng `ZoneId.systemDefault()` ở chỗ quyết định thời hạn thanh toán hoặc giờ hẹn có thể khiến kết quả thay đổi sau khi chuyển hạ tầng.

Ví dụ rõ hơn:

~~~java
ZoneId businessZone =
    ZoneId.of("Asia/Ho_Chi_Minh");
~~~

Nếu một dịch vụ xử lý lịch hẹn quốc tế, zone nên đến từ account/địa điểm sự kiện, không mặc định lấy timezone của server.

### 13.1. `UTC` và region zone không tương đương

`ZoneOffset.UTC` là offset cố định bằng 0. `Europe/Paris` hay `America/New_York` là region zone có quy tắc thay đổi offset theo thời gian và lịch sử. Một `ZoneId.of("+07:00")` là fixed offset; `ZoneId.of("Asia/Ho_Chi_Minh")` là vùng có dữ liệu lịch sử/có thể thay đổi chính sách trong tương lai.

Nếu nghiệp vụ là “mở cửa lúc 09:00 giờ địa phương tại một thành phố”, cần lưu region zone và quy tắc chuyển đổi phù hợp, không chỉ lưu UTC offset hiện tại.

### 13.2. Timezone DB là dữ liệu có phiên bản

JDK bao gồm timezone rules từ **IANA Time Zone Database (TZDB)** theo bản cập nhật tương ứng. Quốc gia có thể thay đổi quy tắc DST hoặc offset theo quyết định pháp lý. Một bản JDK patch mới có thể cập nhật TZDB, khiến phép tính cho một ngày trong tương lai khác với bản cũ.

Có thể xem version zone rules bằng API:

~~~java
import java.time.zone.ZoneRulesProvider;

String version =
    ZoneRulesProvider.getVersions(
        "America/New_York").lastKey();

System.out.println(version);
~~~

Tập versions và cách báo cáo phụ thuộc provider; test cần ghi JDK/vendor/build và TZDB version khi so sánh.

**Đừng đóng băng offset tương lai trong một assertion nếu nghiệp vụ muốn theo thay đổi pháp lý của múi giờ.** Ngược lại, nếu một lịch giao dịch đã chốt dựa trên một bộ quy tắc tại thời điểm đặt lịch, phải định nghĩa cách xử lý khi TZDB cập nhật.

## 14. DST gap và overlap: kiểm thử bắt buộc cho lịch hẹn

DST tạo hai loại chuyển tiếp nổi bật:

- **Gap:** một khoảng giờ địa phương không tồn tại do đồng hồ nhảy tiến.
- **Overlap:** một khoảng giờ địa phương lặp lại do đồng hồ lùi.

Chúng không phải lỗi của `java.time`. Đây là các trường hợp nghiệp vụ phải định nghĩa cách xử lý.

### 14.1. Ví dụ gap tại New York

Ở `America/New_York`, ngày **10/03/2024** có DST spring-forward, local time `02:30` không tồn tại.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(
    2024, 3, 10, 2, 30);

ZoneRules rules = ny.getRules();

System.out.println(
    rules.getValidOffsets(missing).size()
); // 0 với TZDB quy tắc 2024 của New York
~~~

Khi chuyển `LocalDateTime.atZone(ny)`, API sử dụng quy tắc resolver mặc định và có thể điều chỉnh thời gian local qua gap. Nhưng nếu ứng dụng đặt lịch, không nên tự động thay `02:30` thành thời điểm khác mà người dùng không được thông báo.

Các chính sách có thể là:

1. Từ chối giờ không tồn tại và yêu cầu chọn lại.
2. Chuyển đến thời điểm hợp lệ gần nhất theo quy tắc sản phẩm.
3. Chọn một thời điểm đã được xác định theo hợp đồng riêng của domain.

Test phải kiểm tra chính sách đã chọn, không chỉ kiểm tra API không ném exception.

### 14.2. Ví dụ overlap tại New York

Ngày **03/11/2024**, `01:30` xảy ra hai lần với hai offsets khác nhau.

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime ambiguous = LocalDateTime.of(
    2024, 11, 3, 1, 30);

System.out.println(
    ny.getRules().getValidOffsets(ambiguous).size()
); // 2 với quy tắc New York ở mốc này
~~~

Nếu tạo `ZonedDateTime` chỉ từ `LocalDateTime` và `ZoneId` mà không có chính sách overlap, API có mặc định chọn offset. Lịch hẹn nghiệp vụ có thể phải hỏi người dùng “lần thứ nhất hay thứ hai”, hoặc lưu offset cụ thể.

### 14.3. Dùng `ZoneRules` khi validation

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class AppointmentTime {
    public static ZonedDateTime requireUnambiguous(
            LocalDateTime local,
            ZoneId zone) {
        List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(local);

        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                "Gap or overlap: " + local + " in " + zone);
        }

        return ZonedDateTime.ofStrict(
            local, offsets.get(0), zone);
    }
}
~~~

Ví dụ này định nghĩa một hợp đồng nghiêm ngặt: **chỉ nhận thời gian local có đúng một offset hợp lệ**. Ứng dụng thật có thể có quy tắc khác, nhưng nó phải được test rõ ràng.

### 14.4. Không dùng chênh lệch giờ local thay cho elapsed duration

Một đêm chuyển DST có thể không dài đúng 24 giờ theo elapsed time. So sánh:

~~~java
import java.time.Duration;
import java.time.ZonedDateTime;

ZonedDateTime before =
    ZonedDateTime.parse(
        "2024-03-09T12:00:00-05:00[America/New_York]");
ZonedDateTime after = before.plusDays(1);

System.out.println(
    Duration.between(before, after).toHours()
); // 23 khi qua spring-forward
~~~

`plusDays(1)` làm phép toán lịch theo ngày local, còn `plusHours(24)` làm thay đổi lượng thời gian khác. Với billing, SLA, lịch và token expiration, cần chọn định nghĩa đúng giữa **calendar time** và **elapsed time**.

## 15. Parse và format ngày giờ theo locale

### 15.1. Format hiển thị theo locale

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 10, 1);

String french =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.FRANCE)
        .format(date);

System.out.println(french);
~~~

Output phụ thuộc dữ liệu locale và style. Không dùng nó làm API timestamp bất biến. Dùng format ISO tường minh cho dữ liệu machine-readable:

~~~java
String machineDate =
    DateTimeFormatter.ISO_LOCAL_DATE.format(date);
// 2024-10-01
~~~

### 15.2. Pattern symbol và chữ cái literal

~~~java
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern(
        "dd/MM/uuuu", Locale.ROOT);
~~~

Cần phân biệt `M` (month) với `m` (minute), `u` (proleptic year) với `Y` (week-based year) và `d` (day of month) với `D` (day of year). Một pattern dùng `YYYY` thay `uuuu` có thể cho năm khác ở những ngày gần đầu/cuối năm theo week-based-year rules, vốn chịu ảnh hưởng locale.

Đừng nhầm lỗi format pattern với hồi quy TZDB/CLDR. Test cả các ngày cuối tháng, cuối năm, leap day và transition dates.

### 15.3. WeekFields theo locale

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

DayOfWeek firstInUs =
    WeekFields.of(Locale.US).getFirstDayOfWeek();

DayOfWeek firstInFrance =
    WeekFields.of(Locale.FRANCE).getFirstDayOfWeek();
~~~

Calendar UI và báo cáo theo tuần có thể dùng thứ tự ngày đầu tuần hoặc quy tắc minimal days khác nhau. Nếu sản phẩm yêu cầu ISO week, chọn `WeekFields.ISO`; không dùng default locale rồi giả định tuần luôn bắt đầu thứ Hai.

### 15.4. Lịch không phải lúc nào cũng là Gregorian calendar

Một số locale/calendar extensions biểu diễn các hệ lịch khác. Nếu ứng dụng phục vụ nhiều quốc gia, không nên giả định mọi ngày hiển thị theo cùng niên đại và month names. Có thể cần `Chronology` hoặc format policy cụ thể.

Ở cấp lưu trữ sự kiện, dùng `Instant`/ISO chronology khi hợp đồng quy định, rồi convert sang lịch hiển thị ở ranh giới UI.

## 16. Không để test phụ thuộc `now()` không kiểm soát

Một test dạng:

~~~java
LocalDate today = LocalDate.now();
~~~

có thể thất bại khi chạy qua midnight, ở timezone khác hoặc vào giờ chuyển DST. Sử dụng `Clock` để làm test deterministic:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock frozen = Clock.fixed(
    Instant.parse("2024-10-01T23:30:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate businessDate = LocalDate.now(frozen);

System.out.println(businessDate); // 2024-10-02
~~~

Một thiết kế service nên nhận `Clock` hoặc hàm cung cấp thời gian từ dependency injection. Khi test, inject fixed clock; production dùng `Clock.system(...)` với zone theo hợp đồng.

### 16.1. Test các ranh giới

Bộ test nên gồm:

- Trước/sau midnight trong business zone.
- Trước/sau thời điểm chuyển DST.
- Ngày nhuận 29/02 và ngày 01/03.
- Cuối năm, ISO week 1 và week-based year khác calendar year.
- Timestamp có offset khác nhau nhưng cùng `Instant`.
- Ngày xa trong quá khứ hoặc tương lai, khi dữ liệu TZDB có thể khác.
- Timeouts tính theo `Duration`/monotonic elapsed time thay vì đồng hồ tường để tránh NTP adjustments.

Với timeout nội bộ và đo latency, dùng nguồn thời gian đơn điệu như `System.nanoTime()` theo contract phù hợp, không đo chênh `LocalDateTime.now()` có thể nhảy vì hệ thống chỉnh giờ.

## 17. Ma trận hồi quy đa JDK/locale/charset/timezone

Không phải chạy mọi tổ hợp đều cần thiết; cần ưu tiên các chiều ảnh hưởng thật sự đến ứng dụng.

| Trục | Ví dụ cấu hình | Mục tiêu |
|---|---|---|
| JDK | Bản đang dùng, bản đích, bản patch/vender được hỗ trợ | Phát hiện thay đổi library data/runtime |
| Locale | `vi-VN`, `en-US`, `fr-FR`, `tr-TR`, `ja-JP` | Số, ngày, case, resource bundles |
| Default zone | `UTC`, `Asia/Ho_Chi_Minh`, `America/New_York` | Không phụ thuộc timezone server |
| Charset nguồn | UTF-8, ISO-8859-1, một legacy encoding nếu có | Decode/encode và migration bytes |
| Data form | NFC/NFD, combining marks, supplementary | Unicode handling |
| OS/container | Linux, Windows hoặc image mục tiêu | Locale, filesystem, console, tzdata |
| Protocol | CSV, JSON, DB, broker, file export | End-to-end bytes và schema |

Một ma trận tối thiểu cho ứng dụng bán hàng có thể có:

1. **Vietnam baseline:** `vi-VN`, `Asia/Ho_Chi_Minh`, UTF-8.
2. **Locale contrast:** `fr-FR` để kiểm tra dấu thập phân và nhóm số.
3. **Case mapping:** `tr-TR` để lộ code dùng default lowercase.
4. **DST case:** `en-US` với `America/New_York` tại gap/overlap.
5. **Machine contract:** `Locale.ROOT`, UTC, UTF-8 và ISO formats.
6. **Legacy import:** file có charset nguồn thực tế đã được lưu trong hệ thống cũ.

### 17.1. Chọn test theo rủi ro

- Nếu hệ thống chỉ dùng thời gian Việt Nam, vẫn cần kiểm tra các giờ UTC chuyển ngày và lịch sử zone; DST New York có thể là testcase riêng cho thư viện dùng chung.
- Nếu có tên khách hàng đa ngôn ngữ, Unicode/normalization và database collation phải được ưu tiên.
- Nếu không dùng file legacy, không cần cố định thêm hàng chục charsets chỉ để tăng số test.
- Nếu có global deployment, phải kiểm thử những locales/zones nằm trong support policy của sản phẩm.

### 17.2. Ghi chép environment

Mỗi kết quả cần ghi:

~~~text
JDK vendor:
JDK feature/update/build:
java.version:
java.vendor:
Charset.defaultCharset:
file.encoding:
native.encoding (nếu có):
Locale default:
Locale FORMAT:
Locale DISPLAY:
ZoneId.systemDefault:
TZDB version(s):
OS/container image:
Database collation/encoding:
Test fixture version:
~~~

Thông tin này giúp phân biệt regression JDK với khác biệt CI runner.

## 18. Ví dụ JUnit 5: kiểm thử với locale explicit

Ví dụ dưới đây giả định project có `org.junit.jupiter` dependencies phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class LocaleRegressionTest {

    @ParameterizedTest
    @ValueSource(strings = {"vi-VN", "fr-FR", "en-US"})
    void numberRoundTripWithExplicitLocale(
            String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);

        DecimalFormat format = (DecimalFormat)
            NumberFormat.getNumberInstance(locale);

        format.setGroupingUsed(false);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setParseBigDecimal(true);

        BigDecimal expected = new BigDecimal("1234.50");
        String text = format.format(expected);

        ParsePosition end = new ParsePosition(0);
        Object parsed = format.parse(text, end);

        assertEquals(text.length(), end.getIndex());
        assertEquals(expected, parsed);
    }
}
~~~

Đây là test cho hợp đồng **format–parse nội bộ theo cùng locale**, không khẳng định string representation không đổi qua CLDR versions. Nếu API yêu cầu chuỗi chính xác, thêm test fixture theo contract riêng.

### 18.1. Không để JUnit test đổi Locale global

Các test ở trên truyền locale vào formatter riêng, nên không cần `Locale.setDefault` và có thể chạy đồng thời an toàn hơn. Nếu code legacy chỉ gọi `NumberFormat.getInstance()` không truyền locale, hãy test trong process riêng với default locale được đặt từ startup thay vì đổi trạng thái JVM khi các test khác đang chạy.

### 18.2. Kiểm tra Turkish lowercase

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class CaseMappingTest {

    @Test
    void languageSensitiveLowercaseIsExplicit() {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        assertEquals("ı", "I".toLowerCase(turkish));
        assertEquals("i", "I".toLowerCase(Locale.ROOT));
    }
}
~~~

Test này có expected values rõ ràng theo quy tắc case mapping, giúp phát hiện việc code vô tình dùng default locale.

## 19. Ví dụ JUnit: charset round-trip và malformed bytes

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class CharsetRegressionTest {

    @Test
    void vietnameseTextRoundTripsInUtf8() {
        String original = "Đặng Ánh - Hà Nội - 😀";
        byte[] bytes = original.getBytes(
            StandardCharsets.UTF_8);

        String decoded = new String(
            bytes, StandardCharsets.UTF_8);

        assertEquals(original, decoded);
    }

    @Test
    void rejectsMalformedUtf8() {
        byte[] malformed = {(byte) 0xC3, (byte) 0x28};

        assertThrows(CharacterCodingException.class, () ->
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(malformed))
        );
    }
}
~~~

Đừng viết một test chỉ dùng `new String(original.getBytes())` trên cùng runtime; nếu hai bước cùng dùng sai default charset, test vẫn có thể pass dù dữ liệu không tương thích với hệ thống khác.

**Test cross-boundary:** encode bằng process/runtime nguồn thành file bytes, decode bằng runtime đích, so sánh expected text; làm chiều ngược lại khi hệ thống còn hỗ trợ rollback.

### 19.1. So sánh bytes nơi hợp đồng yêu cầu

Ví dụ hệ thống tạo JSON hoặc CSV có checksum, chữ ký số hoặc hash key phụ thuộc bytes. Cùng chuỗi người đọc nhìn giống nhau có thể có NFC/NFD bytes khác nhau.

Test cần xác định normalization form và encoding trước khi tính hash. Nếu sản phẩm chỉ yêu cầu semantic equality, không cần ép byte hash của output locale-sensitive luôn giống sau mỗi nâng CLDR.

## 20. Ví dụ JUnit: DST gap, overlap và instant

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.jupiter.api.Test;

class ZoneRegressionTest {

    private static final ZoneId NEW_YORK =
        ZoneId.of("America/New_York");

    @Test
    void springForwardHasMissingLocalTime() {
        LocalDateTime local = LocalDateTime.of(
            2024, 3, 10, 2, 30);

        assertEquals(0,
            NEW_YORK.getRules().getValidOffsets(local).size());
    }

    @Test
    void fallBackHasAmbiguousLocalTime() {
        LocalDateTime local = LocalDateTime.of(
            2024, 11, 3, 1, 30);

        assertEquals(2,
            NEW_YORK.getRules().getValidOffsets(local).size());
    }

    @Test
    void calendarDayMayNotBe24ElapsedHours() {
        ZonedDateTime before = ZonedDateTime.parse(
            "2024-03-09T12:00:00-05:00[America/New_York]");

        ZonedDateTime nextDay = before.plusDays(1);

        assertEquals(23,
            Duration.between(before, nextDay).toHours());
    }

    @Test
    void timestampRepresentationRoundTrips() {
        Instant original = Instant.parse(
            "2024-10-01T08:30:00Z");

        assertEquals(original,
            Instant.parse(original.toString()));
    }
}
~~~

Các ngày lịch sử này được chọn để minh họa quy tắc DST New York áp dụng ở các mốc đó. Nếu chạy trên môi trường dùng TZDB đặc biệt hoặc rules khác, test nên ghi version và giải thích sự khác biệt. Với các sự kiện **tương lai**, timezone rules có thể thay đổi theo luật, nên tránh đóng băng offset quá sớm nếu hợp đồng nghiệp vụ cần theo dữ liệu mới.

## 21. Kiểm thử default environment trong process riêng

Để bắt code phụ thuộc JVM defaults, có thể chạy một chương trình chẩn đoán nhỏ:

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class EnvironmentProbe {
    public static void main(String[] args) {
        System.out.println(
            "java.version=" + System.getProperty("java.version"));
        System.out.println(
            "java.vendor=" + System.getProperty("java.vendor"));
        System.out.println(
            "locale=" + Locale.getDefault().toLanguageTag());
        System.out.println(
            "formatLocale=" +
            Locale.getDefault(Locale.Category.FORMAT)
                .toLanguageTag());
        System.out.println(
            "charset=" + Charset.defaultCharset());
        System.out.println(
            "zone=" + ZoneId.systemDefault());
    }
}
~~~

Ví dụ chạy với môi trường locale/timezone định trước:

~~~bash
javac EnvironmentProbe.java

java -Duser.language=vi -Duser.country=VN \
     -Duser.timezone=Asia/Ho_Chi_Minh \
     EnvironmentProbe

java -Duser.language=tr -Duser.country=TR \
     -Duser.timezone=America/New_York \
     EnvironmentProbe
~~~

Các lệnh nối dòng dùng shell kiểu Unix. Trên Windows PowerShell 5.1, đặt lệnh trên một dòng hoặc dùng cú pháp nối dòng phù hợp.

### 21.1. Vì sao process isolation tốt hơn `Locale.setDefault` trong test?

Các options ở startup tạo điều kiện kiểm thử dự đoán được cho **toàn process**. Code phụ thuộc default locale, timezone hoặc default charset có thể được quan sát mà không cạnh tranh với những test khác trong cùng JVM.

Lưu ý: `user.language`/`user.country` không phải giải pháp duy nhất cho mọi locale extension, và timezone/container environment có thể ảnh hưởng thêm. Muốn test định dạng theo locale phức tạp, truyền `Locale` và `ZoneId` trực tiếp vào API vẫn là cách rõ ràng hơn.

### 21.2. Không dùng `-Dfile.encoding` tùy ý thay cho explicit charset

Khi test khác biệt default charset, có thể dùng runtime/source environment thật và chính sách được JDK hỗ trợ. Đặt `-Dfile.encoding=COMPAT` có thể hữu ích như một bước tìm nguyên nhân trong JDK hỗ trợ, nhưng không thay thế việc sửa code để truyền charset tường minh.

Để kiểm thử legacy encoding một cách deterministic, tạo file bytes theo `Charset.forName("...")` phù hợp trong fixture, không dựa vào OS default đang có trên runner.

## 22. Golden fixtures cho dữ liệu quốc tế hóa

Bộ fixtures nên được chọn có mục đích, không chỉ lấy vài tên ASCII.

| Nhóm | Dữ liệu mẫu | Điều cần kiểm tra |
|---|---|---|
| ASCII | `ABC123`, `-_.` | Protocol grammar cố định |
| Tiếng Việt dựng sẵn | `Nguyễn Ánh`, `Đặng Thị Hòa` | UTF-8, collation, case |
| Tiếng Việt phân rã | `a\u0306\u0301` và dạng NFC tương đương | Normalization, uniqueness |
| Chữ Hán/tiếng Nhật | `中文`, `東京` | Unicode decoding, font/output pipeline |
| Arabic script | `العربية` | UTF-8, directionality, bidi |
| Chữ số khác ASCII | `١٢٣` | Validation vs numeral display |
| Supplementary Unicode | `😀` hoặc code point ngoài BMP | UTF-16 vs code point length |
| Ký tự kết hợp | `e\u0301` | NFC/NFD, search |
| Whitespace Unicode | U+00A0, U+2003, tab | Trim/strip/parse differences |
| Dấu thập phân/nhóm số | Locale fr-FR/en-US/vi-VN | NumberFormat, strict parse |
| Ngày nhuận | 29/02/2024 | Calendar/date arithmetic |
| DST gap | New York 10/03/2024 02:30 | Invalid local time |
| DST overlap | New York 03/11/2024 01:30 | Ambiguous local time |
| UTC crossing midnight | 23:30 UTC | Business date theo zone |
| Tuần cuối năm | 29–31/12 và 01–03/01 | ISO week vs locale week |
| File legacy encoding | Bytes ISO-8859-1 hoặc source encoding thật | Migration decode |

### 22.1. Lưu cả text và bytes

Khi xây fixtures cho charset, nên lưu bản đại diện ở **hai cấp**:

~~~text
fixtures/
  customer-utf8.txt
  customer-utf8.sha256
  customer-legacy.bin
  customer-legacy.expected.txt
  nfc-vietnamese.txt
  nfd-vietnamese.txt
  numbers-fr.expected.json
  timezone-cases.json
~~~

Các file `*.bin` cần được tạo từ encoding đã biết và có metadata. Không tự đoán legacy charset khi test chạy.

### 22.2. Ghi lại expectation thuộc loại nào

Một fixture có thể là:

- **Normative/contract fixture:** bytes/text phải bất biến.
- **Semantic fixture:** kết quả parse/timepoint tương đương, presentation có thể khác.
- **Snapshot for review:** output UI có thể thay theo CLDR nhưng phải được review.
- **Migration fixture:** sản phẩm phải đọc dữ liệu do bản cũ tạo, không nhất thiết ghi ngược giống hệt.

Nếu mọi fixture đều dùng exact-string assertions, team sẽ gặp nhiều “false positive” khi locale data được cập nhật. Nếu mọi fixture chỉ kiểm tra parse success, có thể bỏ qua lỗi ngữ nghĩa nghiêm trọng.

## 23. So sánh JDK nguồn và JDK đích

Một kế hoạch thử nghiệm hiệu quả cần giữ càng nhiều biến số cố định càng tốt.

~~~text
Same application commit / artifact
Same dataset / test fixture
Same test matrix
            |
   +--------+--------+
   |                 |
   v                 v
JDK nguồn         JDK đích
   |                 |
   +--------+--------+
            |
            v
Compare:
- semantic values
- exact protocol bytes
- UI snapshot deltas
- logs and environment identity
            |
            v
Classify intentional vs regression
~~~

Nếu upgrade cùng lúc framework, JDK, database collation và container image, hãy thêm các thí nghiệm tách biến:

1. App cũ trên JDK cũ + environment cũ.
2. App cũ trên JDK mới + environment tương đương nếu được hỗ trợ.
3. App mới trên JDK mới + environment cũ khi khả thi.
4. App mới trên environment/container mới.

Không phải mọi tổ hợp đều chạy được; cần ghi rõ blockers. Mục tiêu là xác định **thay đổi nào gây khác biệt**, không đơn thuần tạo nhiều build.

### 23.1. Cross-version read/write

Nếu hệ thống có file export, cache, queue hoặc persisted JSON từ runtime cũ, kiểm tra:

~~~text
Writer JDK cũ -> Reader JDK cũ
Writer JDK cũ -> Reader JDK mới
Writer JDK mới -> Reader JDK mới
Writer JDK mới -> Reader JDK cũ (nếu rollback còn hỗ trợ)
~~~

Một đổi encoding hoặc format có thể khiến binary cũ không đọc được dữ liệu do binary mới ghi. Vì vậy đây cũng là **điều kiện rollback**, không chỉ một bài toán i18n UI.

### 23.2. Chạy đúng artifact trên đúng JVM

Với Maven Toolchains/Gradle toolchains, compiler JDK và test JVM có thể khác nhau. Một artifact compiled `--release 17` không chứng minh test đã chạy trên Java 17. Lưu `java.version`, `java.home`, artifact hash và profile được chọn trong CI.

## 24. CI configuration và tránh flaky tests

### 24.1. Cố định những gì phải cố định

Với test dữ liệu máy–máy, nên chỉ định:

- `Locale.ROOT` hoặc locale tường minh.
- `StandardCharsets.UTF_8` hoặc charset của giao thức.
- `ZoneId.of(...)` hoặc UTC theo contract.
- `Clock.fixed(...)` cho thời điểm hiện tại.
- `DateTimeFormatter.ISO_*` hoặc formatter với pattern được định nghĩa.
- Rounding mode/scale rõ ràng cho giá trị tiền.
- Canonical normalization form khi so sánh định danh.
- Sample data và expected values đã kiểm tra.

### 24.2. Không làm mất khả năng phát hiện regression bằng cách cố định mọi default

Nếu sản phẩm phụ thuộc vào default locale hoặc timezone thật, test chỉ dùng UTC/Locale.ROOT sẽ không phát hiện lỗi. Nên có **hai tầng**:

- Tầng core deterministic với explicit parameters.
- Tầng environment compatibility chạy process dưới những locale/zone đại diện.

Tầng thứ hai cần tách process để tránh race conditions khi các test cùng sửa JVM globals.

### 24.3. Container timezone data

Container image có thể thiếu timezone database ở OS, nhưng JVM có thể dùng timezone rules tích hợp trong JDK. Một số công cụ hệ thống như `date` hoặc thư viện native lại đọc tzdata của OS.

Do đó, việc `date` trên Linux container hiển thị một offset không tự chứng minh `java.time.ZoneId` dùng chính xác cùng nguồn dữ liệu. Ghi và kiểm tra cả hai nếu ứng dụng kết hợp Java và native/OS APIs.

### 24.4. Locale data updates có thể tạo test noise

Nếu snapshot UI đổi vì CLDR, cần:

1. Xác định field nào thay đổi.
2. Xem JDK/CLDR update và locale liên quan.
3. Kiểm tra format vẫn đúng ngữ nghĩa.
4. Review yêu cầu UX và translation.
5. Chỉ cập nhật snapshot có chủ đích.
6. Ghi release note nếu consumer/customer bị ảnh hưởng.

Không tự động bỏ mọi assertion format vì “locale không ổn định”; cần cân bằng giữa linh hoạt dữ liệu và yêu cầu sản phẩm.

## 25. Triệu chứng thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng cần lấy |
|---|---|---|
| Số tiền đổi dấu phân cách | Default locale/CLDR/provider đổi | `Locale`, `NumberFormat`, JDK build |
| Parse đọc một phần chuỗi mà không lỗi | `NumberFormat.parse` chấp nhận prefix | `ParsePosition` và full length |
| `I` lower thành `ı` | Locale tr-TR được dùng ngầm | Lowercase call và default locale |
| Sort order thay | Collation provider/version khác | `Collator`/database collation, fixtures |
| Tên tiếng Việt bị `�` | Decode sai charset/malformed bytes | Hex bytes nguồn, charset nguồn/đích |
| CSV bị lỗi cột đầu tiên | BOM hoặc separator/quote khác | Hex bytes, header, parser config |
| `Properties` đọc sai dấu | Nhầm `load(InputStream)` với UTF-8 | API overload, encoding của file |
| ResourceBundle thiếu bản dịch | Bundle fallback/key hoặc resource packaging | Bundle names, locale, artifact contents |
| Date UI khác thứ tự ngày/tháng | Locale/style provider đổi | Locale, formatter, CLDR version |
| Ngày lịch hẹn lệch một ngày | Default timezone đổi | Instant, zone, systemDefault |
| Lịch hẹn DST bị dời giờ | Gap resolution default | `ZoneRules.getValidOffsets` |
| Hai lịch hẹn trùng giờ hiển thị | DST overlap | Offset từng instant, region zone |
| “Một ngày” chỉ 23/25 giờ | Calendar day vs Duration | Code `plusDays`/`plusHours` |
| Test fail gần midnight | `now()` không được cố định | `Clock`, timezone của CI |
| Test hash khác dù text nhìn giống | NFC/NFD, encoding hoặc newline | Code points, bytes, normalization |
| JDK patch mới làm lịch tương lai khác | TZDB update | TZDB version/rules, policy |
| API trả chuỗi UI thay vì ISO | Locale-dependent format trong protocol | Response bytes/schema, formatter |

### 25.1. In code points thay vì chỉ xem chữ trên log

~~~java
String text = "a\u0306\u0301";

text.codePoints().forEach(cp ->
    System.out.printf("U+%04X%n", cp));
~~~

Hai chuỗi có hình thức hiển thị gần như nhau có thể có các code points khác. Ghi cả code points lẫn bytes mẫu sẽ giúp phân biệt normalization với charset corruption.

Khi log dữ liệu người dùng thật, phải tuân thủ chính sách bảo vệ dữ liệu cá nhân; sử dụng fixtures tổng hợp cho test và ticket báo lỗi.

### 25.2. Phân biệt lỗi parsing với lỗi hiển thị

Một String đã decode sai có thể “đúng” trong bộ nhớ theo những bytes sai và được format locale rất chuẩn—kết quả vẫn lỗi. Ngược lại, bytes/Unicode đúng nhưng UI font thiếu glyph có thể hiển thị hộp vuông; đây không phải lỗi CharsetDecoder.

Điều tra theo từng lớp: source bytes → decoded code points → normalized string → formatted output → font/UI.

## 26. Quy trình migration đề xuất

### Bước 1: Inventory

Tìm những nơi dùng:

~~~text
Locale.getDefault()
Locale.setDefault(...)
ZoneId.systemDefault()
TimeZone.getDefault()
new Date()
LocalDate.now()
LocalDateTime.now()
new String(bytes)
String.getBytes()
InputStreamReader(...)
OutputStreamWriter(...)
String.format(...)
NumberFormat.getInstance()
DateTimeFormatter.ofLocalized...
SimpleDateFormat
Collator
ResourceBundle
MessageFormat
Properties.load(InputStream)
Charset.defaultCharset()
~~~

Không cần sửa tất cả ngay. Phân loại theo tác động: protocol/financial, persistence, user display và debug logs.

### Bước 2: Xác định hợp đồng

Ghi rõ:

- Text encoding ở từng ranh giới.
- Locale và currency policy cho UI.
- UTC instant và region zone cho lịch.
- Normalization và identity policy.
- Các định dạng bất biến cho API/file.
- Fallback resource bundles.
- Khả năng phiên bản cũ đọc dữ liệu mới nếu phải rollback.

### Bước 3: Viết fixtures và unit tests

Tạo bộ dữ liệu đa ngôn ngữ, legacy bytes, locale number/date, DST gaps/overlaps và near-midnight cases. Ưu tiên explicit API parameters và `Clock.fixed`.

### Bước 4: Chạy source và target JDK

Giữ cùng artifact/test matrix khi có thể, ghi runtime/env. Với test locale mặc định, chạy process riêng; với tests theo hợp đồng, dùng explicit locale/charset/zone.

### Bước 5: Test end-to-end

Kiểm tra file import/export, HTTP payloads, DB collation, queue messages, search index và logs. Đừng chỉ test formatter unit-level vì dữ liệu có thể hỏng ở ranh giới bytes.

### Bước 6: Phân loại khác biệt

| Loại khác biệt | Hành động |
|---|---|
| Vi phạm machine contract/bytes | Sửa trước deploy |
| Parse sai hoặc mất Unicode data | Sửa encoding/schema/validation |
| Sai instant hoặc DST nghiệp vụ | Sửa policy/time conversion |
| CLDR display đổi nhưng hợp lệ | Review UX và update snapshot có chủ đích |
| Cần reindex do collation | Lập kế hoạch migration dữ liệu |
| Dữ liệu mới khiến runtime cũ không đọc được | Đóng rollback gate hoặc chuẩn bị fallback-compatible release |

### Bước 7: Canary, giám sát, rollback

Theo dõi lỗi parse, số lượng replacement characters, thất bại resource lookup, timestamp lệch, tỷ lệ rejected input và business invariants. Trước rollback, kiểm tra runtime cũ có đọc/ghi an toàn dữ liệu do bản mới tạo không; rollback binary không tự đưa encoding hoặc data schema về trạng thái cũ.

## 27. Những hiểu nhầm thường gặp

**“Java `String` luôn là UTF-8.”** Không. `String` là abstraction ký tự; UTF-8 là một charset dùng để encode/decode bytes.

**“Java 18 mặc định UTF-8 nên dữ liệu legacy tự động đúng.”** Không. Nếu bytes nguồn thuộc charset khác, cần decode bằng charset nguồn trước khi chuyển đổi.

**“`Properties.load(InputStream)` đọc UTF-8 vì JDK mặc định UTF-8.”** Không. API đó có quy tắc ISO-8859-1; cần phân biệt với `load(Reader)` và `PropertyResourceBundle`.

**“Locale chỉ ảnh hưởng ngôn ngữ thông báo.”** Không. Nó còn ảnh hưởng số, ngày, tên tháng, case mapping và collation.

**“`Locale.ROOT` luôn đúng cho mọi người dùng.”** Không. Nó phù hợp với một số hợp đồng máy–máy/locale-neutral, nhưng UI cần locale của người dùng.

**“Thêm `Locale.setDefault` ở đầu test là đủ.”** Không an toàn với parallel tests và code chạy cùng JVM.

**“Một timestamp không có zone vẫn biểu thị thời điểm duy nhất.”** Không. `LocalDateTime` không chứa offset/zone.

**“UTC+07:00 và `Asia/Ho_Chi_Minh` là cùng một loại dữ liệu.”** Không. Một bên là offset cố định, một bên là region zone có lịch sử/rules.

**“Một ngày luôn bằng 24 giờ.”** Không khi dùng calendar day qua DST hoặc theo hợp đồng lịch khác elapsed duration.

**“DST chỉ gây lỗi khi đổi JDK.”** Không. Lỗi nằm trong domain time model và có thể lộ khi data/TZDB hoặc hạ tầng thay đổi.

**“Có thể hard-code offset của ngày tương lai.”** Rủi ro nếu chính phủ thay đổi timezone rules; cần policy rõ.

**“Hai chuỗi nhìn giống nhau luôn bằng nhau.”** Không. Unicode có canonical-equivalent representations và confusables khác nhau.

**“`String.length()` là số ký tự người dùng nhìn thấy.”** Không. Nó đếm UTF-16 code units.

**“Golden snapshot đổi là regression chắc chắn.”** Chưa chắc; CLDR có thể cập nhật format hợp lệ. Nhưng thay đổi API bytes hoặc ngữ nghĩa nghiệp vụ vẫn là regression.

**“Test trên một JDK đủ chứng minh rollback.”** Không. Nếu dữ liệu mới đã ghi, runtime cũ phải được test đọc/ghi lại theo hợp đồng.

## 28. Checklist kiểm thử hồi quy i18n

- [ ] Đã ghi JDK nguồn/đích, vendor, build và OS/container.
- [ ] Đã biết default Locale FORMAT/DISPLAY, Charset và ZoneId thực tế.
- [ ] Đã kiểm kê những nơi phụ thuộc default locale/charset/timezone.
- [ ] Đã xác định machine contract khác UI formatting.
- [ ] Đã có fixtures tiếng Việt NFC/NFD, non-Latin, combining marks, emoji.
- [ ] Đã test encode/decode UTF-8 và malformed bytes.
- [ ] Đã test chuyển đổi legacy charset thực tế của dữ liệu cũ nếu có.
- [ ] Đã kiểm tra `Properties`/`PropertyResourceBundle` encoding.
- [ ] Đã kiểm tra HTTP, CSV, JSON, JDBC và message payload bytes.
- [ ] Đã test decimal/grouping separators, strict parsing và currency semantics.
- [ ] Đã test locale-dependent case mapping và collation.
- [ ] Đã kiểm tra ResourceBundle fallback, placeholders và missing keys.
- [ ] Đã test UTC instant → local display và near-midnight cases.
- [ ] Đã test leap day, week-based year, DST gap và overlap.
- [ ] Đã xác định chính sách với giờ local không tồn tại hoặc bị trùng.
- [ ] Đã dùng `Clock.fixed` cho những test phụ thuộc thời điểm hiện tại.
- [ ] Đã xem TZDB version nếu kết quả zone rules khác nhau.
- [ ] Đã tách test cần JVM default vào process riêng.
- [ ] Đã chạy ma trận runtime/locale/zone theo support policy thực tế.
- [ ] Đã phân loại snapshot presentation changes với semantic regressions.
- [ ] Đã kiểm tra dữ liệu từ phiên bản mới vẫn tương thích với bản rollback nếu cần.
- [ ] Đã ghi test evidence và review mọi thay đổi format hiển thị có chủ đích.

## 29. Tài liệu kỹ thuật tham khảo

- [JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset ở JDK 18, các giới hạn và tương thích.
- [JEP 252 – Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): dữ liệu locale và thay đổi từ JDK 9.
- [JEP 226 – UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226): encoding khi tải resource bundles.
- [`Locale` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): locale, language tags và categories.
- [`Charset` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): charset và default charset.
- [`StandardCharsets` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset bắt buộc có trong Java.
- [`NumberFormat` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): format/parse số theo locale.
- [`ResourceBundle` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): i18n resources và fallback.
- [`Normalizer` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.
- [`DateTimeFormatter` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): patterns và localized date/time formatting.
- [`ZoneRules` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html): DST gap/overlap và valid offsets.
- [`ZoneRulesProvider` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): phiên bản timezone rules.
- [IANA Time Zone Database](https://www.iana.org/time-zones): dữ liệu múi giờ và các thay đổi theo chính sách địa phương.
- [Unicode Standard](https://www.unicode.org/standard/standard.html): code points, properties và normalization.

Các ví dụ sử dụng APIs hiện đại và cần được chạy trên bản JDK mà dự án hỗ trợ. Khi xác minh một thay đổi CLDR/TZDB/Unicode cụ thể, luôn đối chiếu release notes của **đúng JDK feature/update/vendor** và dữ liệu thời gian/ngôn ngữ mà sản phẩm xử lý.

## 30. Kết luận

**Locale, charset, múi giờ và quốc tế hóa là những hợp đồng dữ liệu có thể đổi hành vi khi nâng JDK, ngay cả khi source không đổi và ứng dụng vẫn khởi động bình thường.** Locale data ảnh hưởng số/ngày/collation; charset quyết định diễn giải bytes; TZDB ảnh hưởng chuyển đổi thời gian theo region; Unicode normalization và phân loại ký tự ảnh hưởng validation/search/định danh.

Chiến lược kiểm thử hồi quy vững chắc là **truyền locale/charset/zone tường minh ở các ranh giới quan trọng, dùng `Clock` trong test, định nghĩa machine format bất biến, lưu fixtures đa ngôn ngữ và chạy ma trận JDK–locale–timezone–encoding**. Khi output khác, cần phân loại khác biệt presentation được chấp nhận với lỗi semantic hoặc mất dữ liệu. Đừng chỉ sửa snapshot hoặc chỉ đổi default môi trường: hãy kiểm chứng cả bytes, code points, instant, business invariants và khả năng đọc dữ liệu chéo phiên bản.

Làm đúng như vậy giúp migration không chỉ “đạt build”, mà còn **giữ được sự chính xác của dữ liệu người dùng quốc tế và các hành vi nghiệp vụ phụ thuộc thời gian/ngôn ngữ**.
