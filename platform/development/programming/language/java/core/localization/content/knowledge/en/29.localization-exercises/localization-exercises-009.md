# Lập bảng chọn API và tự đánh giá các lỗi bản địa hóa thường gặp

## 1. Mục tiêu và cách dùng bài thực hành

Trong Java, “localization” không phải một hàm duy nhất. Dịch một thông báo, định dạng số tiền, sắp tên theo từ điển, xử lý Unicode có dấu và hiển thị chữ phải–trái là **những bài toán khác nhau**. Chọn nhầm API có thể tạo kết quả trông đúng ở máy phát triển nhưng sai trên máy người dùng, hoặc làm thay đổi dữ liệu nghiệp vụ.

Bài Knowledge này xây dựng một **bảng quyết định chọn API** cho Java 17+, sau đó dùng những **tình huống sai–đúng**, **mã runnable**, **bài tập tự chấm điểm** và **checklist kiểm thử** để đánh giá một thiết kế bản địa hóa. Đây là bài thực hành tổng hợp: người học nên dùng được bảng chọn API cả khi đọc code cũ, review pull request và thiết kế chức năng mới.

Sau khi học, bạn cần trả lời được:

1. Dùng **Locale**, **ResourceBundle** hay **MessageFormat** trong tình huống nào?
2. Vì sao **NumberFormat**, **Currency**, **BigDecimal** và tỷ giá không thay thế nhau?
3. Khi nào dùng **LocalDate**, **Instant**, **ZoneId** và **DateTimeFormatter**?
4. Khi nào **String.compareTo** không phù hợp và nên dùng **Collator**?
5. Khi nào cần **Normalizer**, **BreakIterator**, **Character** hoặc **Bidi**?
6. Vì sao một Locale hợp lệ không đồng nghĩa ứng dụng đã có bản dịch?
7. Cách phát hiện lỗi do default Locale, fallback, Unicode spaces, thread safety hoặc timezone?
8. Viết kiểm thử thế nào để tránh đóng đinh một kết quả phụ thuộc phiên bản CLDR/JDK?
9. Đánh giá mức độ nghiêm trọng và ưu tiên sửa lỗi bản địa hóa bằng tiêu chí khách quan?
10. Tách dữ liệu có kiểu khỏi chuỗi hiển thị ra sao để không làm hỏng số tiền hay thời gian?

## 2. Trước hết: chọn đúng lớp vấn đề

Hãy chia yêu cầu thành bảy nhóm. Nếu chưa biết yêu cầu thuộc nhóm nào, khoan chọn API.

| Nhóm | Câu hỏi thực tế | Ví dụ |
| --- | --- | --- |
| **Ngôn ngữ** | Câu, nút, lỗi và nội dung có bản dịch nào? | “Thanh toán” / “Pay” |
| **Định dạng** | Cùng một giá trị được viết theo vùng thế nào? | 1,234.50 so với 1.234,50 |
| **Lịch/thời gian** | Một ngày hoặc thời điểm được hiển thị ở vùng nào? | Giờ đặt hàng ở Việt Nam và Mỹ |
| **So sánh văn bản** | Xếp tên theo mã kỹ thuật hay theo từ điển người đọc? | An, Ánh, Đào |
| **Chuẩn hóa và phân đoạn** | Các cách mã hóa Unicode, biên từ, grapheme được xử lý thế nào? | é và e + dấu sắc |
| **Bố cục và chiều chữ** | LTR/RTL, số, dấu câu được vẽ ra sao? | Mã hàng trong câu Ả Rập |
| **Nghiệp vụ và bảo mật** | Giá trị, ID, đơn vị, permission có đổi do locale không? | EUR, account ID, access policy |

Một số yêu cầu thuộc **nhiều nhóm đồng thời**. Ví dụ email hóa đơn cần: chọn thông điệp theo ngôn ngữ, định dạng tiền theo vùng, chuyển Instant sang ZoneId người nhận và render HTML có escaping/bidi. Điều này không có nghĩa nên tạo một lớp “LocaleUtils” chứa mọi logic; mỗi phần cần hợp đồng rõ.

**Nguyên tắc dẫn đường:** lưu giá trị có kiểu và thứ tự logic; dùng API locale để tạo **biểu diễn** khi cần; không parse ngược biểu diễn nếu không có giao kèo đầu vào chính thức.

## 3. Bảng chọn API Java 17+ theo nhu cầu

Bảng dưới đây là công cụ tra cứu chính. Cột “tránh nhầm” quan trọng không kém cột API.

| Nhu cầu | API/chức năng phù hợp | Tránh nhầm với |
| --- | --- | --- |
| Biểu diễn ngôn ngữ/vùng/script | **java.util.Locale**, Locale.forLanguageTag | Tạo Locale không đảm bảo có bản dịch |
| Chọn một locale từ ưu tiên trình duyệt | **Locale.LanguageRange.parse**, Locale.lookup/filter | Không dùng mọi available locales làm menu app |
| Biết tập locale JDK công bố | **Locale.getAvailableLocales()** | Không chứng minh mọi dịch vụ hoặc UI hỗ trợ |
| Hỏi locale của formatter số | **NumberFormat.getAvailableLocales()** | Không suy từ danh sách Collator |
| Hỏi locale của collation | **Collator.getAvailableLocales()** | Không dùng NumberFormat list để kết luận |
| Tra thông điệp theo key/ngôn ngữ | **ResourceBundle.getBundle**, getString | Không tự dịch nội dung nghiệp vụ |
| Chèn tham số theo ngữ pháp câu | **MessageFormat** | Không nối prefix + amount + suffix cố định |
| Định dạng số thường | **NumberFormat.getNumberInstance(locale)** | Không dùng Double.toString làm format UI |
| Định dạng tỷ lệ 0.125 → 12,5% theo vùng | **NumberFormat.getPercentInstance(locale)** | Không truyền 12.5 nếu input là fraction |
| Định dạng tiền theo vùng | **NumberFormat.getCurrencyInstance(locale)** | Không thay thế tỷ giá hoặc Currency gốc |
| Mô hình hóa đơn vị tiền | **Currency.getInstance("EUR")** | Currency không phải amount và không đổi tiền |
| Tính toán thập phân chính xác | **BigDecimal** | Không dùng new BigDecimal(double) tùy tiện |
| Chọn dấu nhóm/thập phân tường minh | **DecimalFormatSymbols**, DecimalFormat | Không dùng thay mọi tailoring của locale |
| Ngày thuần, không timezone | **LocalDate** | Không tự xem LocalDate là Instant |
| Một thời điểm tuyệt đối | **Instant** | Không xem Instant là local wall-clock |
| Quy tắc giờ địa phương | **ZoneId**, ZonedDateTime | Không suy múi giờ từ Locale |
| Định dạng ngày/giờ Java 17+ | **DateTimeFormatter**, FormatStyle, withLocale | Tránh SimpleDateFormat shared mutable |
| Định dạng kỹ thuật ISO | **DateTimeFormatter.ISO_...**, toString có hợp đồng | Không dùng localized string cho API máy |
| Sắp xếp tên theo ngôn ngữ | **Collator.getInstance(locale)** | Không dùng String.compareTo làm từ điển |
| So sánh kỹ thuật theo UTF-16 | **String.compareTo** | Không xem là locale-aware |
| Chuẩn hóa Unicode chính tắc | **Normalizer** với NFC/NFD | Không đồng nghĩa bỏ dấu/tìm kiếm/collation |
| Chuẩn hóa tương thích có chủ đích | **Normalizer** với NFKC/NFKD | Có thể tạo collision giữa ký tự khác |
| Ngắt từ/câu/cụm ký tự | **BreakIterator** | Không dùng split(" ") cho mọi ngôn ngữ |
| Kiểm tra loại ký tự/hướng/điểm mã | **Character** và String.codePoints | Không giả định mỗi char là một code point |
| Phân tích chữ hai chiều | **java.text.Bidi**, renderer text layout | Không reverse chuỗi RTL |
| Phân biệt chữ hoa/thường theo locale | **String.toLowerCase(locale)** trong policy rõ | Không thay thế Collator hoặc full case-folding |
| Giữ UTF-8 khi lưu/đọc | **StandardCharsets.UTF_8**, reader/writer rõ charset | Không dựa charset máy hoặc sửa lỗi bằng bỏ dấu |
| Phân trang tên qua database | Collation của **DB** + tie-breaker ID nhất quán | Không sort riêng mỗi trang phía client |
| Bảo vệ HTML có tham số người dùng | Template autoescape/contextual escaping | ResourceBundle/MessageFormat không chống XSS |

**Cách dùng:** trước mỗi tính năng, chọn một hàng “nhu cầu”, ghi rõ kiểu dữ liệu đầu vào và tiêu chuẩn đúng; sau đó xác định các API phối hợp. Không lựa chọn chỉ vì một lớp có tên gần giống thuật ngữ của yêu cầu.

## 4. Ma trận dữ liệu → biểu diễn → kiểm thử

Chọn đúng API mới là bước đầu. Phải xác định cái gì được phép thay đổi khi chuyển locale.

| Giá trị gốc | Kiểu nên giữ | Phần được phép đổi | Bất biến phải kiểm tra |
| --- | --- | --- | --- |
| 1234567.89 | BigDecimal | Dấu nhóm, thập phân, glyph chữ số | Giá trị số không đổi |
| 1234.50 EUR | BigDecimal + Currency | Ký hiệu tiền, vị trí ký hiệu, khoảng trắng | Amount và currency code không đổi |
| 0.125 | BigDecimal tỷ lệ | Cách viết 12,5%, vị trí % | Tỷ lệ là 0.125 |
| 2026-10-28 | LocalDate | Thứ tự ngày/tháng, tên tháng | Ngày gốc không đổi |
| 2026-10-28T02:30:00Z | Instant | Giờ/ngày địa phương và format | Instant/epoch không đổi |
| ORD-1028 | String ID | Cách trình bày trong câu RTL có thể cần isolation | Nội dung logic của ID không đổi |
| Tên người | String Unicode | Sort và bố cục theo locale | Không âm thầm xóa dấu |
| order.confirmed | Message key | Nội dung dịch, trật tự tham số | Key và ý nghĩa nghiệp vụ không đổi |

Nếu một phép “localize” đã thay đổi amount, ID, Instant hoặc đơn vị tiền, đó thường là dấu hiệu **trộn trình bày với nghiệp vụ**. Một ngoại lệ cần được đặc tả là chức năng **chuyển đổi tiền tệ** hoặc **chuyển lịch nghiệp vụ** thực sự; ở đó việc đổi dữ liệu là thao tác riêng có quy tắc, không phải side effect của formatter.

## 5. Bảng chọn API: thông điệp và lựa chọn ngôn ngữ

### 5.1. Locale chỉ là danh tính ngôn ngữ/vùng

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

Đoạn minh họa cần import java.util.Locale. Nó biểu diễn locale, **không có nghĩa** UI đã dịch tiếng Việt. Một ứng dụng có thể hỗ trợ hai ngôn ngữ trong khi JDK có dữ liệu locale cho nhiều ngôn ngữ hơn.

Hãy đặt một danh sách **supportedLocales** do sản phẩm kiểm thử và công bố. Để lựa chọn theo ưu tiên, dùng Locale.LanguageRange và Locale.lookup. Không tự sửa Locale.setDefault cho mỗi request trên server; đây là trạng thái JVM có tác động rộng.

### 5.2. ResourceBundle lấy nội dung, MessageFormat tạo câu

ResourceBundle trả mẫu theo key. MessageFormat thay các placeholder **{0}**, **{1}** theo cách người dịch sắp xếp. Ví dụ:

~~~properties
order.summary=Đơn {0} có tổng {1}.
~~~

Với bản tiếng Anh:

~~~properties
order.summary=Order {0} totals {1}.
~~~

Mẫu câu có thể đảo vị trí tham số giữa các ngôn ngữ. Đừng tự ghép cố định phần trước + số tiền + phần sau. Các chuỗi đã định dạng cho tiền/ngày có thể được chèn dưới dạng argument.

**Cạm bẫy MessageFormat:** dấu nháy đơn là ký tự quote trong pattern. Muốn hiển thị dấu nháy đơn literal, thường phải viết **''**. Cần QA tất cả pattern theo locale; có key không đồng nghĩa pattern hợp lệ.

**Cạm bẫy ResourceBundle:** fallback có thể lấy base bundle hoặc ngôn ngữ khác. Nếu getBundle thành công, chưa chứng minh bản dịch vi-VN đầy đủ. Bộ kiểm thử phải so tập key và phát hiện partial translation theo chính sách ứng dụng.

### 5.3. Nhóm nào không thuộc message service?

ResourceBundle **không** quyết định tỷ giá, rounding, ISO currency code, timezone hoặc quyền truy cập. Nếu một key hiển thị là “Thanh toán”, đừng dùng chính văn bản dịch làm action ID; hãy dùng một mã ổn định như payment.submit. Dịch vụ lấy message không được thay đổi domain objects.

## 6. Bảng chọn API: số, tiền, phần trăm

### 6.1. NumberFormat và dữ liệu số có kiểu

~~~java
BigDecimal amount = new BigDecimal("1234.50");
Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat number =
        NumberFormat.getNumberInstance(locale);
NumberFormat money =
        NumberFormat.getCurrencyInstance(locale);
NumberFormat percentage =
        NumberFormat.getPercentInstance(locale);
~~~

Đoạn minh họa cần import java.math.BigDecimal, java.util.Locale và java.text.NumberFormat, đặt trong phương thức.

**getNumberInstance:** nhóm/thập phân. **getCurrencyInstance:** thêm quy tắc tiền (có thể gồm ký hiệu, vị trí và fraction digits). **getPercentInstance:** chuyển giá trị fraction để hiển thị dạng %. Không gộp chúng thành một formatter chỉ thay ký tự.

### 6.2. Currency không phải tỷ giá

~~~java
Currency unit = Currency.getInstance("EUR");
money.setCurrency(unit);
String shown = money.format(amount);
~~~

Đoạn minh họa cần import Currency và các biến money/amount trước đó. Số tiền vẫn là 1234.50 EUR; setCurrency **không** chuyển nó sang VND hoặc USD. Nếu nghiệp vụ yêu cầu quy đổi, cần tỷ giá, thời điểm áp dụng, làm tròn, kiểm toán và một bước tính toán trước formatting.

Một formatter có thể theo mặc định chọn tiền gắn với vùng locale, ví dụ USD với en-US. Khi dữ liệu đơn hàng ghi EUR, phải chỉ rõ EUR; không dùng currency mặc định của người xem để thay mã tiền thực.

### 6.3. BigDecimal và rounding

Dùng **new BigDecimal("0.1")** để giữ thập phân được chỉ định; không dùng **new BigDecimal(0.1)** nếu mong đúng 0.1. Currency.getDefaultFractionDigits() hữu ích cho biểu diễn thông thường, nhưng **không đủ làm chính sách làm tròn tính tiền**. Trong nghiệp vụ tài chính, phân biệt số chữ số lưu trữ, số chữ số của phép tính và số chữ số hiển thị.

### 6.4. Unicode spaces không phải lỗi formatter

Một số locale có **U+00A0 NBSP** hoặc **U+202F NNBSP** giữa số và ký hiệu tiền, hoặc làm dấu phân nhóm. Dùng String.codePoints() để điều tra, không áp trim/replaceAll trên output một cách mù quáng. Hai chuỗi nhìn giống nhau nhưng chứa những code point khác nhau là điều bình thường trong dữ liệu bản địa hóa.

### 6.5. Đọc dữ liệu người dùng nhập

Không parse một chuỗi tiền có dấu nhóm vi-VN bằng Locale.US. NumberFormat.parse có thể chỉ tiêu thụ **một tiền tố hợp lệ**; khi yêu cầu nghiêm ngặt, kiểm tra **ParsePosition.getIndex() == input.length()** và xử lý lỗi. Với tiền chính xác, DecimalFormat hỗ trợ **setParseBigDecimal(true)**; phải hiểu provider và cấu hình đang dùng. Trao đổi giữa máy nên dùng giá trị có kiểu/định dạng kỹ thuật ổn định thay vì localized string.

## 7. Bảng chọn API: ngày, thời gian và timezone

### 7.1. LocalDate, Instant, ZoneId có ý nghĩa khác

- **LocalDate:** ngày lịch thuần, ví dụ ngày sinh hoặc ngày giao hàng 2026-10-28, không gắn giờ.
- **Instant:** thời điểm tuyệt đối trên trục UTC, ví dụ thời điểm thanh toán.
- **ZoneId:** bộ quy tắc giờ vùng, ví dụ Asia/Ho_Chi_Minh hay America/Los_Angeles.
- **ZonedDateTime:** cách xem một local date-time trong zone, đủ thông tin để liên hệ với Instant khi dữ liệu hợp lệ.
- **DateTimeFormatter:** chuyển giá trị thời gian có kiểu thành văn bản theo pattern/FormatStyle/Locale.

**Locale không phải ZoneId.** Cùng một người dùng giao diện tiếng Anh có thể đang ở châu Á; Locale.US không đủ để xác định giờ địa phương.

### 7.2. Định dạng cho người xem và cho máy khác nhau

~~~java
DateTimeFormatter display =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.LONG).withLocale(locale);
~~~

Đoạn minh họa cần import DateTimeFormatter, FormatStyle và biến locale.

**Giao diện:** dùng định dạng localized. **API máy:** dùng ISO 8601/format cố định có hợp đồng. Đừng trả “28 tháng 10 năm 2026” rồi ép client parse bằng MM/dd/yyyy.

### 7.3. Instant trước, hiển thị sau

~~~java
Instant instant =
        Instant.parse("2026-10-28T02:30:00Z");
ZonedDateTime shown =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đoạn minh họa cần imports Instant, ZonedDateTime, ZoneId. Instant không đổi khi xem ở ZoneId khác, nhưng **ngày giờ địa phương có thể đổi**, kể cả rơi vào ngày lịch trước/sau.

### 7.4. SimpleDateFormat hay DateTimeFormatter?

Trong mã Java 17+ mới, ưu tiên java.time/DateTimeFormatter vì API có kiểu rõ, formatter immutable và thread-safe. **SimpleDateFormat** là API cũ mutable, không nên lưu một instance rồi dùng đồng thời trên server mà không đồng bộ/cách ly. Nếu phải duy trì legacy Date/java.util.Calendar, thiết lập chiến lược chuyển đổi rõ và tránh mất timezone.

## 8. Bảng chọn API: sắp xếp, chuẩn hóa và ngắt văn bản

### 8.1. String.compareTo không phải Collator

~~~java
int codeUnitOrder = "Z".compareTo("a");
~~~

**String.compareTo** so **char UTF-16** từ trái qua phải, không theo thứ tự từ điển địa phương. Ví dụ Z đứng trước a về mã kỹ thuật, nhưng một danh sách tên người thường cần chữ hoa/thường ở vị trí gần nhau. Dùng **Collator.getInstance(locale)** khi cần thứ tự tên theo người đọc.

Collator có **PRIMARY, SECONDARY, TERTIARY, IDENTICAL** để chọn mức khác biệt cần xét và có chế độ decomposition. Một số khác biệt case/dấu có thể được xem ngang nhau khi chọn strength thấp; không suy rằng **collator.compare(a,b)==0** tương đương **a.equals(b)**.

**Đặc biệt:** nếu comparator trả 0 cho hai String khác nhau, **TreeSet/TreeMap** có thể coi chúng là cùng key. Dùng ID nghiệp vụ làm định danh, có thể thêm tie-breaker khi muốn một thứ tự toàn phần.

### 8.2. Normalizer giải quyết canonical Unicode, không giải quyết từ điển

Một chữ **é** có thể biểu diễn bằng **U+00E9** hoặc **U+0065 + U+0301**. Nếu cần so canonical equivalence, chuẩn hóa cả hai về **NFC** hoặc **NFD**. Chúng có thể trông như nhau nhưng String.equals trả false trước chuẩn hóa.

**NFKC/NFKD** đi xa hơn tới compatibility normalization, có thể gom một số ký hiệu/fullwidth/ligature thành dạng khác. Chọn có chủ đích, đặc biệt khi xử lý ID, quyền truy cập hoặc dữ liệu có thể xảy ra collision. **Normalizer không phải công cụ sort theo ngôn ngữ**, không phải full search engine và không thay Collator.

### 8.3. BreakIterator chọn biên văn bản, không phải split(" ")

Dùng **BreakIterator.getWordInstance(locale)**, **getSentenceInstance(locale)** hoặc **getCharacterInstance(locale)** để xác định ranh giới theo quy tắc runtime. Trong một số hệ chữ, việc tách từ không thể chỉ dựa vào dấu cách. Cần test emoji, combining marks và câu thực tế; “character instance” không tự giải quyết mọi thao tác UI phức tạp về grapheme trên mọi phiên bản Unicode.

### 8.4. Chữ có dấu và supplementary code points

**String.length()** đếm UTF-16 code units; một Unicode code point ngoài BMP có thể cần hai char. Dùng **String.codePoints()** khi debug dãy điểm mã; **StringBuilder.reverse()** không phải cách xử lý RTL, canonical normalization hay grapheme-safe editing.

## 9. Bảng chọn API: bidi, font và hiển thị

Với nội dung có chữ Latin LTR, chữ Ả Rập/Do Thái RTL, chữ số và dấu câu, Unicode Bidirectional Algorithm quyết định thứ tự nhìn thấy từ chuỗi logic. Lớp **java.text.Bidi** cung cấp phân tích base direction/embedding levels/runs.

Tuy nhiên, **Bidi không phải font shaping engine** và không tự vẽ chữ. Một UI còn cần renderer hỗ trợ shaping/line breaking. Không đảo String bằng reverse để “sửa” câu RTL, vì mã sản phẩm, số điện thoại, dấu ngoặc và thứ tự logic có thể bị hỏng.

Với HTML có tên người dùng RTL trong câu LTR, có thể dùng vùng **bdi dir="auto"** hoặc direction/isolation của nền tảng. **Escaping HTML vẫn bắt buộc**: ResourceBundle, MessageFormat và bdi không thay cơ chế chống XSS.

**Lưu ý bảo mật:** directional overrides như U+202E có thể làm văn bản nhìn khác logic, nên môi trường review code, tên file hoặc log audit phải có chính sách cảnh báo/escape hợp lý. Không cấm văn bản RTL hợp lệ một cách mù quáng.

## 10. Ma trận các anti-pattern và cách sửa

| Dấu hiệu sai | Nguyên nhân | Cách sửa an toàn |
| --- | --- | --- |
| UI Việt nhưng số in kiểu máy chủ | Dùng default Locale | Truyền formatLocale tường minh |
| Menu có 500 ngôn ngữ nhưng app chỉ dịch hai | Dùng Locale.getAvailableLocales làm UI list | Danh sách appSupportedLocales riêng |
| Ngôn ngữ lẫn nhau giữa các câu | ResourceBundle fallback chưa kiểm soát | QA coverage và fallback policy |
| Mẫu câu có dấu nháy bị mất chữ | MessageFormat quote chưa đúng | Nhân đôi dấu ' trong pattern, test |
| USD xuất hiện trên đơn EUR | Currency mặc định của locale | Set Currency gốc của giao dịch |
| Số tiền sai 0.1 | Dùng BigDecimal(double) | BigDecimal từ chuỗi/nguồn chính xác |
| 12.5 hiển thị 1.250% | Nhầm fraction với percent value | Truyền 0.125 cho 12,5% |
| Ngày lệch một ngày | Instant không đi qua ZoneId đúng | Xác định zone trước khi format |
| dd/MM/yyyy gây lỗi trên user Mỹ | Hardcode kiểu ngày UI | DateTimeFormatter localized |
| Hai request làm đổi formatter lẫn nhau | Chia sẻ NumberFormat mutable | Tạo theo request hoặc cách ly |
| Tên hoa/không dấu sắp lạ | String.compareTo dùng cho UI | Collator theo locale |
| Tên khác nhau bị mất trong TreeSet | Collator strength thấp, compare==0 | Dùng ID/Comparator tie-breaker |
| é dựng sẵn và tổ hợp không match | Không normalize theo policy | Normalizer NFC/NFD khi phù hợp |
| Từ tiếng Thái bị split sai | split(" ") | BreakIterator, test rule |
| Mã hàng trong câu RTL hiển thị đảo | Reverse hoặc thiếu isolation | Bidi/layout và vùng hướng đúng |
| Kết quả test đổi sau nâng JDK | Snapshot CLDR không version hóa | Tách invariant test và locale data test |
| API gửi “1.234,50” cho hệ thống khác | Dùng localized output làm data format | Giá trị kiểu số/ISO theo contract |
| HTML hiển thị tên người và lỗ hổng XSS | Chèn raw string | Template autoescape |
| Phân trang A–Z bị đảo giữa các trang | DB/UI dùng hai comparator khác | Một nguồn sort toàn cục + ID tie-break |
| Charset/emoji lỗi khi export | Không kiểm soát UTF-8/font | UTF-8 và renderer/font đủ glyph |

**Câu hỏi reviewer quan trọng:** vấn đề sai do dữ liệu được lưu, do chọn locale, do formatter, do bundle, hay chỉ do renderer? Trước khi “sửa nhanh” bằng replace String, phải xác định ranh giới gây lỗi.

## 11. Ví dụ runnable: bộ kiểm tra bất biến API

**File LocalizationSelfCheck.java**

Ví dụ này đưa vào các giá trị có kiểu, kiểm tra những điều **không phụ thuộc chuỗi format theo CLDR**: lựa chọn ngôn ngữ của ứng dụng, BigDecimal, mã tiền, UTC, Unicode normalization, raw UTF-16 và MessageFormat quote. Mỗi dòng PASS là một điều kiện được xác định theo API Java 17.

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class LocalizationSelfCheck {
    private static void check(String name, boolean condition) {
        System.out.println(name + "="
                + (condition ? "PASS" : "FAIL"));
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        List<Locale> supported = List.of(vi, Locale.US);
        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8");

        Locale chosen = Locale.lookup(ranges, supported);
        check("locale", vi.equals(chosen));

        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.10");
        check("decimal", a.compareTo(b) == 0);

        Currency money = Currency.getInstance("EUR");
        check("currency",
                "EUR".equals(money.getCurrencyCode()));

        Instant event = Instant.parse(
                "2026-10-28T02:30:00Z");
        LocalDate atUtc =
                event.atZone(ZoneId.of("UTC")).toLocalDate();
        check("utcDate",
                LocalDate.of(2026, 10, 28).equals(atUtc));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        check("nfc", Normalizer.normalize(
                composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        check("rawOrder", "Z".compareTo("a") < 0);

        MessageFormat pattern = new MessageFormat(
                "User {0}: it''s ready", Locale.US);
        check("message",
                "User Lan: it's ready".equals(
                        pattern.format(new Object[] {"Lan"})));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LocalizationSelfCheck.java
java LocalizationSelfCheck
~~~

Stdout chính xác:

~~~text
locale=PASS
decimal=PASS
currency=PASS
utcDate=PASS
nfc=PASS
rawOrder=PASS
message=PASS
~~~

### Giải thích bài kiểm tra

- **locale:** Locale.lookup được cho một tập supported có vi-VN, ưu tiên vi-VN cao nhất nên chọn vi-VN.
- **decimal:** BigDecimal.compareTo xem 0.1 và 0.10 bằng nhau về giá trị số, khác với equals có xét scale.
- **currency:** EUR là mã ISO currency đã được chọn rõ, không dựa vào vùng.
- **utcDate:** Instant được chuyển với ZoneId UTC, không lấy timezone máy chủ.
- **nfc:** hai chuỗi tương đương chính tắc được đưa về cùng biểu diễn NFC.
- **rawOrder:** nhắc rằng compareTo là thứ tự UTF-16, không phải danh sách từ điển địa phương.
- **message:** dấu nháy đôi trong MessageFormat pattern đưa ra một dấu nháy đơn literal.

**Hạn chế có chủ đích:** chương trình này không kiểm tra đúng mọi dữ liệu dịch của sản phẩm. Nó xác minh các bất biến và ý nghĩa API cơ bản, không phải chứng nhận rằng vi-VN có đầy đủ mọi bản dịch hoặc mọi kiểu định dạng trong runtime.

## 12. Ví dụ runnable: khảo sát kết quả localized mà không đoán stdout

**File LocaleFormatAudit.java**

Chương trình thứ hai in cùng một BigDecimal/Currency/LocalDate/Instant dưới ba locale. Đây là bài test quan sát **giá trị thực tế từ JDK đang chạy**, không nên gắn một stdout exact cho mọi bản CLDR.

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class LocaleFormatAudit {
    private static void show(
            Locale locale,
            BigDecimal amount,
            Currency currency,
            LocalDate day,
            Instant event) {

        NumberFormat number =
                NumberFormat.getNumberInstance(locale);
        NumberFormat money =
                NumberFormat.getCurrencyInstance(locale);
        money.setCurrency(currency);

        DateTimeFormatter date =
                DateTimeFormatter.ofLocalizedDate(
                        FormatStyle.LONG).withLocale(locale);

        ZoneId zone = ZoneId.of("UTC");
        DateTimeFormatter moment =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.MEDIUM).withLocale(locale);

        System.out.println("locale="
                + locale.toLanguageTag());
        System.out.println("  number="
                + number.format(amount));
        System.out.println("  money="
                + money.format(amount));
        System.out.println("  date="
                + date.format(day));
        System.out.println("  time="
                + moment.format(event.atZone(zone)));
        System.out.println("  currencyCode="
                + currency.getCurrencyCode());
    }

    public static void main(String[] args) {
        BigDecimal amount =
                new BigDecimal("1234.50");
        Currency euro = Currency.getInstance("EUR");
        LocalDate date = LocalDate.of(2026, 10, 28);
        Instant event =
                Instant.parse("2026-10-28T02:30:00Z");

        show(Locale.forLanguageTag("vi-VN"),
                amount, euro, date, event);
        show(Locale.US, amount, euro, date, event);
        show(Locale.GERMANY, amount, euro, date, event);

        System.out.println("sourceAmount="
                + amount.toPlainString());
        System.out.println("sourceCurrency="
                + euro.getCurrencyCode());
        System.out.println("sourceDate=" + date);
        System.out.println("sourceInstant=" + event);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LocaleFormatAudit.java
java LocaleFormatAudit
~~~

Chương trình in ba khối bắt đầu bằng **locale=vi-VN**, **locale=en-US**, **locale=de-DE**. Trong mỗi khối, **number/money/date/time** được tính bởi runtime hiện tại; không nên tự định nghĩa một “golden” hoàn toàn chung cho mọi bản JDK. Tuy nhiên, bốn dòng cuối là giá trị gốc có thể kiểm chứng:

~~~text
sourceAmount=1234.50
sourceCurrency=EUR
sourceDate=2026-10-28
sourceInstant=2026-10-28T02:30:00Z
~~~

**Tiêu chuẩn thành công:** dữ liệu gốc không đổi khi hiển thị cho ba locale, đơn vị tiền vẫn là EUR, Instant vẫn là cùng thời điểm. Khác biệt chữ số, dấu thập phân, dấu cách hoặc tên tháng là **biểu diễn**. Nếu muốn snapshot output theo từng locale chính xác, phải pin runtime/provider và kiểm tra các code point, đặc biệt NBSP/NNBSP.

## 13. Bài tập chẩn đoán nhanh: chọn API nào?

Đọc 15 tình huống; trước khi xem đáp án, tự ghi **API chính + API phụ nếu có + một lỗi cần tránh**.

| Mã | Tình huống |
| --- | --- |
| A1 | Người dùng chọn giao diện vi-VN nhưng máy chủ đang ở en-US |
| A2 | Dịch một câu có tên khách và tổng đơn hàng |
| A3 | Format 1234567.89 với dấu nhóm theo fr-FR |
| A4 | Đơn hàng 1234.50 EUR được xem từ Hoa Kỳ |
| A5 | Hiển thị “12,5%” từ tỷ lệ 0.125 |
| A6 | Hiển thị ngày sinh 2026-10-28 ở nhiều vùng |
| A7 | Hiển thị cùng thời điểm thanh toán ở Hà Nội và California |
| A8 | Sắp xếp danh sách tên có ă, â, đ và dấu thanh |
| A9 | Phát hiện hai cách mã hóa Unicode của chữ é |
| A10 | Chọn từ tiếp theo khi double-click trong tài liệu đa ngữ |
| A11 | Hiển thị mã ORD-1028 giữa câu tiếng Ả Rập |
| A12 | Một TreeSet mất tên chỉ khác hoa/thường |
| A13 | Locale.getAvailableLocales chứa ngôn ngữ app chưa dịch |
| A14 | Hai request in sai tiền khi dùng chung NumberFormat |
| A15 | Parser số đã đọc tiền tố hợp lệ nhưng bỏ rác cuối chuỗi |

### 13.1. Đáp án và lý do

| Mã | Chọn API/cách thiết kế | Lỗi cần tránh |
| --- | --- | --- |
| A1 | LocaleResolver + supportedLocales, truyền Locale tường minh | Không gọi Locale.setDefault theo request |
| A2 | ResourceBundle + MessageFormat, các giá trị format riêng | Không ghép một trật tự câu cố định |
| A3 | NumberFormat.getNumberInstance(Locale.FRANCE) | Không tự thay dấu bằng regex |
| A4 | BigDecimal + Currency EUR + NumberFormat currency với locale người xem | Không tự đổi EUR thành USD |
| A5 | NumberFormat.getPercentInstance(locale) với input 0.125 | Không đưa 12.5 thay ratio |
| A6 | LocalDate + DateTimeFormatter localized | Không gắn timezone giả vào ngày thuần |
| A7 | Instant + ZoneId của mỗi người xem + DateTimeFormatter | Không lấy timezone server |
| A8 | Collator.getInstance(vi-VN), test tên thật | Không dùng String.compareTo làm từ điển |
| A9 | Normalizer NFC hoặc NFD theo policy | Không dùng NFKC tùy tiện cho mọi ID |
| A10 | BreakIterator phù hợp locale | Không split(" ") toàn cầu |
| A11 | Renderer bidi/direction/isolate; java.text.Bidi khi cần phân tích | Không đảo String hoặc thay dấu ngoặc thủ công |
| A12 | Comparator có equality phù hợp ID, strength/tie-breaker | Không nhầm compare==0 với String.equals |
| A13 | App supportedLocales + coverage QA | Không dùng all available locales làm menu |
| A14 | Tạo formatter theo request hoặc cách ly | Không chia sẻ NumberFormat mutable và đổi Currency |
| A15 | ParsePosition/strict validation, parser đúng locale | Không coi parse thành công một phần là thành công toàn bộ |

**Phương pháp chấm:** mỗi tình huống được **2 điểm**: 1 điểm nêu đúng nhóm API, 1 điểm nêu được cạm bẫy. Tổng tối đa **30 điểm**. Nếu chọn đúng API nhưng đề xuất sửa bằng cách “đảo chuỗi”, “xóa dấu” hoặc “đổi ký hiệu tiền mà không đổi giá trị”, hãy tự trừ điểm cạm bẫy.

## 14. Bài tập code review: phát hiện lỗi trước khi sửa

Đoạn sau **cố ý chứa lỗi** và không phải chương trình mẫu nên chạy trên production:

~~~java
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance();

void show(Order order, Locale locale) {
    Locale.setDefault(locale);
    SHARED.setCurrency(Currency.getInstance(locale));
    String amount = SHARED.format(order.amount());
    String day = order.createdAt().toString();
    String text = "Order " + order.id()
            + ": " + amount + ", " + day;
    System.out.println(text);
}
~~~

Giả định Order là kiểu miền có **amount()**, **createdAt()**, **id()**. Tập trung review logic, đừng nhầm đây là code standalone. Những vấn đề cần chỉ ra:

1. **Locale.setDefault(locale)** thay trạng thái JVM cho các request khác.
2. **SHARED** là NumberFormat mutable, có thể gây race.
3. **getCurrencyInstance() không truyền locale**, bị phụ thuộc default của thời điểm khởi tạo, không phải request đang xử lý.
4. **Currency.getInstance(locale)** suy tiền theo vùng người xem, không phải Currency của đơn hàng; một số locale còn không đủ vùng để suy đơn vị.
5. **setCurrency** chỉ đổi nhãn đơn vị, không quy đổi tỷ giá.
6. **createdAt().toString()** có thể là biểu diễn kỹ thuật Instant; không phải ngày giờ ở ZoneId người nhận.
7. **"Order " + ...** hardcode tiếng Anh và thứ tự câu.
8. Không xác định fallback nếu app chưa có bản dịch.
9. Không có policy cho fraction digits/rounding.
10. Không có escaping theo kênh xuất nếu kết quả đưa vào HTML/email.

### 14.1. Bản sửa theo trách nhiệm

Một thiết kế tốt hơn có thể định nghĩa các kiểu/hợp đồng:

~~~java
record PresentationContext(
        Locale uiLocale,
        Locale formatLocale,
        ZoneId zoneId) {}

interface MessageService {
    String render(Locale locale,
                  String key,
                  Object... arguments);
}

interface FormattingService {
    String money(BigDecimal amount,
                 Currency currency,
                 Locale locale);
    String moment(Instant instant,
                  ZoneId zone,
                  Locale locale);
}
~~~

Đây là **các khai báo minh họa**, cần imports Locale, ZoneId, BigDecimal, Currency, Instant. Chúng không phải một chương trình độc lập. Domain giữ **Order.amount + Order.currency + Order.createdAt**. Presenter dùng context người nhận để gọi formatter, sau đó MessageService dựng câu theo key. Formatter mutable được tạo/cách ly mỗi thao tác; không sửa default JVM.

Bản sửa không chỉ “đổi một hàm” mà **giữ ranh giới giữa dữ liệu, chọn locale, định dạng và bản dịch**.

## 15. Bài tự đánh giá theo 10 tiêu chí

Chấm **0 / 1 / 2 điểm** cho từng tiêu chí:

- **0:** không đáp ứng hoặc có rủi ro rõ ràng.
- **1:** đáp ứng một phần, thiếu test/hợp đồng/fallback.
- **2:** thiết kế rõ, có kiểm thử và không dựa ngầm vào môi trường.

| Tiêu chí | Câu hỏi để tự đánh giá | Điểm |
| --- | --- | --- |
| **1. Locale policy** | App có danh sách locale được dịch, được chọn/fallback rõ không? | 0–2 |
| **2. Data model** | Amount/Currency/LocalDate/Instant có được giữ có kiểu không? | 0–2 |
| **3. Messages** | Key ResourceBundle/MessageFormat có coverage và placeholder QA không? | 0–2 |
| **4. Numbers/money** | Formatter nhận Locale tường minh, Currency đúng và rounding policy không? | 0–2 |
| **5. Date/time** | Phân biệt LocalDate/Instant/ZoneId, không lấy timezone máy chủ không? | 0–2 |
| **6. Unicode/text** | Normalization, collation và word boundaries có chọn đúng bài toán không? | 0–2 |
| **7. RTL/render** | Bidi, isolation, fonts, escaping có được test nếu sản phẩm cần không? | 0–2 |
| **8. Concurrency** | Formatter mutable có được cách ly, không set default toàn JVM không? | 0–2 |
| **9. Tests** | Có test invariants, integration locale và dữ liệu CLDR/JDK version không? | 0–2 |
| **10. Operations** | Có metric/log cho missing key, fallback, nâng JDK và error report không? | 0–2 |

**Tổng tối đa: 20 điểm.** Gợi ý diễn giải:

- **0–7:** còn lỗi nền tảng; chưa đủ cơ sở để công bố hỗ trợ đa locale.
- **8–13:** có cấu trúc nhưng còn rủi ro đáng kể; ưu tiên vùng có dữ liệu tài chính/thời gian.
- **14–17:** tương đối tốt; cần đóng các khoảng trống test và vận hành.
- **18–20:** đạt kiểm tra đầu vào ở mức bài học; vẫn cần QA thực tế theo từng locale, kênh và nội dung.

Điểm số là **rubric đào tạo**, không phải chứng chỉ an ninh/chất lượng hay thay thế kiểm thử sản phẩm.

### 15.1. Cách dùng rubric trong pull request

Trong PR, người review có thể:

1. Ghi các locale được hỗ trợ.
2. Gắn nguồn/kiểu dữ liệu của amount, time, message key.
3. Xem các hàm được gọi có nhận Locale/ZoneId/Currency tường minh hay không.
4. Kiểm tra có bản dịch cho key mới và cú pháp pattern hợp lệ.
5. Tìm các singleton NumberFormat/SimpleDateFormat bị chia sẻ.
6. Yêu cầu test mô phỏng ít nhất hai locale và hai timezone.
7. So kết quả với rubric, nêu hành động cụ thể cho mỗi tiêu chí chưa đạt.

**Không tự coi 20/20 là toàn bộ yêu cầu accessibility, pháp lý hoặc dịch thuật.** Đây là bảng để phát hiện lỗi kỹ thuật bản địa hóa phổ biến, cần kết hợp với QA nội dung địa phương.

## 16. Phân loại mức độ nghiêm trọng của lỗi

Không phải lỗi nào cũng có cùng mức ưu tiên.

| Mức | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Critical** | Đổi mã tiền nhưng không tính tỷ giá; rò dữ liệu người dùng qua cache message; lỗi bảo mật injection | Sai tiền/vi phạm bảo mật |
| **High** | Sai ngày thanh toán do timezone; mất record vì comparator TreeSet; parse tiền sai dấu | Sai nghiệp vụ hoặc mất dữ liệu |
| **Medium** | ResourceBundle fallback ngôn ngữ khác; số âm/đơn vị hiển thị khó hiểu; dấu câu RTL sai | Người dùng hiểu sai, khó thao tác |
| **Low** | Một nhãn chưa tự nhiên, khoảng trắng hoặc chữ hoa chưa theo style guide | Chất lượng UX, nhất quán hiển thị |

**Mức độ thực tế phụ thuộc ứng dụng.** Một lỗi ngày trên màn hình lịch cá nhân có thể Medium, nhưng lỗi ngày trong hạn thanh toán hoặc lịch dùng thuốc có thể Critical. Đánh giá theo tác động và khả năng xảy ra; không chỉ theo tên API.

Đừng giải quyết lỗi Critical bằng cách thêm một String.replace ngắn rồi bỏ qua hợp đồng dữ liệu. Hãy sửa ở tầng nguồn thích hợp và bổ sung regression test.

## 17. Ma trận kiểm thử kết hợp

| Kịch bản | Input | Assert ổn định | Phần cần QA runtime |
| --- | --- | --- | --- |
| vi-VN vs en-US | BigDecimal("1234.50") | Giá trị gốc giữ nguyên | Dấu nhóm/thập phân |
| EUR tại en-US | amount EUR | Currency code EUR | Ký hiệu/vị trí |
| Thuế | ratio 0.125 | 0.125 không đổi | % và số chữ số |
| Ngày thuần | LocalDate 2026-10-28 | LocalDate không đổi | Pattern/tên tháng |
| Instant hai zone | Instant cố định | toInstant bằng nhau | Giờ hiển thị theo tzdb |
| Unicode NFC | é và e+combining | NFC giống nhau | Font không phải assert dữ liệu |
| Collator vi-VN | tên có ă/â/đ | Comparator có contract hợp lệ | Thứ tự cụ thể theo rules |
| BreakIterator | câu có dấu/emoji | Boundary index hợp lệ | Ranh giới ngôn ngữ |
| Bidi | mã LTR trong câu RTL | String logic không đổi | Renderer/dấu câu |
| ResourceBundle | key có/không có | Fallback policy rõ | Nội dung dịch |
| HTML | tên người không tin cậy | Có escaping | Hiển thị direction/font |
| Nâng JDK/CLDR | cùng bộ dữ liệu | Value gốc không đổi | Output locale có thể cập nhật |
| Multithreading | nhiều locale/currency | Không dùng shared mutable formatter | So kết quả concurrency |

### 17.1. Đừng snapshot mọi ký tự khi không cần

Nếu format một số tiền trong fr-FR, khoảng trắng có thể là **U+00A0** hoặc **U+202F** tùy dữ liệu runtime. So **String.equals** là cần khi sản phẩm đã pin phiên bản và yêu cầu output exact; nhưng nếu test chỉ nhằm chắc Currency gốc không đổi, đừng dùng một snapshot phụ thuộc CLDR để kiểm tra bất biến ấy.

Chia test thành:

- **Unit test nghiệp vụ:** BigDecimal, Currency, Instant, LocalDate.
- **Unit test lựa chọn locale:** supportedLocales và fallback.
- **Integration test dịch vụ:** NumberFormat, DateTimeFormatter, Collator, BreakIterator.
- **Localization QA:** bundle coverage, ngữ pháp, độ dài chữ và cấu trúc placeholder.
- **Visual/accessibility QA:** font, RTL, dấu câu, HTML/PDF/email.
- **Security test:** escaping, bidi controls trong định danh kỹ thuật, dữ liệu người dùng.

## 18. Câu hỏi trắc nghiệm tự đánh giá

Chọn một đáp án phù hợp nhất cho từng câu. Đáp án ở mục tiếp theo.

**Câu 1.** App có vi-VN và en-US; người dùng yêu cầu fr-CA nhưng không có bản dịch. Cách đúng nhất là gì?

A. Gọi Locale.setDefault(fr-CA), mọi thứ sẽ tự dịch.

B. Chọn locale được app hỗ trợ theo policy fallback và công bố rõ.

C. Dùng Locale.getAvailableLocales() để coi fr-CA đã có bản dịch.

D. Nối tiền tố tiếng Pháp vào mọi câu tiếng Anh.

**Câu 2.** Đơn hàng ghi 100 EUR, người dùng đang ở Hoa Kỳ. Hành động đúng?

A. Tự đổi Currency thành USD vì Locale.US.

B. Dùng Currency EUR của giao dịch, format theo Locale.US nếu phù hợp.

C. Lấy Currency.getInstance(Locale.US) rồi set vào dữ liệu gốc.

D. Bỏ Currency và chỉ in 100.

**Câu 3.** Cần sắp danh sách tên theo từ điển tiếng Việt. Chọn gì?

A. String.compareTo.

B. StringBuilder.reverse.

C. Collator.getInstance(Locale.forLanguageTag("vi-VN")) và test.

D. Integer.parseInt của String.

**Câu 4.** Thời điểm UTC đổi sang giờ California có thể khác ngày lịch; dùng gì?

A. LocalDate.toString không zone.

B. Instant + ZoneId + DateTimeFormatter.

C. Locale.setDefault(Locale.US).

D. Currency.getInstance.

**Câu 5.** Hai chuỗi é dựng sẵn và e+dấu sắc kết hợp cần so canonical-equivalent; dùng gì?

A. Normalizer NFC hai chuỗi rồi so.

B. String.compareToIgnoreCase là đủ cho mọi Unicode.

C. Xóa toàn bộ dấu trước khi lưu.

D. Chỉ thay font.

**Câu 6.** Một NumberFormat static singleton được setCurrency theo từng request; vấn đề chính?

A. NumberFormat immutable nên không có vấn đề.

B. Locale không có Currency.

C. Mutable formatter có thể race/lẫn cấu hình.

D. JVM luôn từ chối mọi Currency khác default.

**Câu 7.** Form nhập số dùng NumberFormat.parse; điều gì cần kiểm tra thêm?

A. Có parse được tiền tố đã đủ hợp lệ cho mọi input.

B. Phải loại mọi NBSP toàn cầu.

C. ParsePosition tiêu thụ hết input theo policy; độ chính xác và kiểu kết quả.

D. Dùng String.compareTo thay parser.

**Câu 8.** Một phần tên Ả Rập trong câu tiếng Anh làm dấu ngoặc chạy sai. Chọn gì?

A. Đảo String.

B. Sửa dữ liệu bằng thay mọi '(' thành ')'.

C. Dùng đúng paragraph direction/isolation và renderer bidi.

D. Thay NumberFormat.

**Câu 9.** ResourceBundle.getBundle trả được base bundle cho fr-CA, điều đó chứng tỏ gì?

A. App đã dịch đầy đủ fr-CA.

B. Chỉ chứng tỏ có tài nguyên tìm được qua lookup/fallback.

C. Timezone mặc định ở Canada.

D. Currency bắt buộc là CAD.

**Câu 10.** Cần so sánh order IDs kỹ thuật theo thứ tự cố định do giao thức quy định, không quan tâm từ điển người xem. Chọn gì?

A. Dùng Collator ở Locale người xem cho mọi ID.

B. Dùng so sánh kỹ thuật được giao thức định nghĩa, có thể là String.compareTo/byte order tùy hợp đồng.

C. Dùng MessageFormat.

D. Xóa mọi chữ số.

### 18.1. Đáp án có giải thích

| Câu | Đáp án | Lý do |
| --- | --- | --- |
| 1 | **B** | Ngôn ngữ app hỗ trợ là một chính sách sản phẩm, không phải kết quả JDK |
| 2 | **B** | EUR là đơn vị giao dịch, Locale.US chỉ quyết định biểu diễn |
| 3 | **C** | Collator xử lý thứ tự ngôn ngữ, compareTo chỉ so UTF-16 |
| 4 | **B** | Instant là thời điểm, ZoneId tạo giờ địa phương |
| 5 | **A** | NFC giải quyết canonical equivalence |
| 6 | **C** | NumberFormat mutable, không sửa chung đồng thời |
| 7 | **C** | Parse có thể không tiêu thụ toàn chuỗi hoặc mất precision |
| 8 | **C** | Bidi/layout xử lý hướng hiển thị; không phá logical order |
| 9 | **B** | ResourceBundle fallback không chứng minh dịch thuật hoàn chỉnh |
| 10 | **B** | ID kỹ thuật cần hợp đồng ổn định, không phụ thuộc người xem |

**Chấm 1 điểm/câu**, tổng 10. Nếu sai các câu 2, 4, 6 hoặc 7, nên ưu tiên ôn phần liên quan **tính đúng của dữ liệu**, vì hậu quả có thể nghiêm trọng hơn một lỗi bố cục thông thường.

## 19. Checklist khi review dự án thật

### Dữ liệu và hợp đồng

- [ ] Số tiền được lưu dưới dạng BigDecimal + Currency, không phải localized String.
- [ ] Không suy Currency hay ZoneId chỉ từ Locale.
- [ ] Ngày thuần và thời điểm tuyệt đối được mô hình hóa bằng kiểu phù hợp.
- [ ] ID và mã nghiệp vụ giữ nguyên thứ tự logic khi hiển thị.
- [ ] Dữ liệu máy dùng định dạng được đặc tả, không parse localized display string tùy tiện.

### Ngôn ngữ, định dạng và Unicode

- [ ] Supported locales của app có bản dịch/QA, không dùng toàn bộ locale của JDK.
- [ ] Locale được truyền tường minh cho formatter, không set default theo request.
- [ ] ResourceBundle có policy fallback và kiểm tra key/placeholder.
- [ ] MessageFormat pattern xử lý dấu nháy, ngoặc nhọn và thứ tự tham số đúng.
- [ ] NumberFormat/Currency/percent dùng đúng input và chính sách rounding.
- [ ] DateTimeFormatter/ZoneId dùng đúng nhu cầu ngày hoặc thời điểm.
- [ ] Collator/Normalizer/BreakIterator được chọn đúng lớp vấn đề.
- [ ] Chữ RTL sử dụng text layout/isolation; không đảo String.
- [ ] Unicode NBSP/NNBSP và code point đặc biệt được test khi quan trọng.

### Vận hành và bảo mật

- [ ] Không chia sẻ rồi sửa NumberFormat/MessageFormat mutable đồng thời.
- [ ] Không cache kết quả thông điệp đã chèn thông tin người dùng chỉ theo key.
- [ ] Có escaping theo HTML/email/URL, không nhầm MessageFormat là bộ bảo mật.
- [ ] Test nhiều locale, nhiều timezone và nhiều luồng.
- [ ] Có regression khi nâng JDK/CLDR/tzdb.
- [ ] Phân trang và cơ sở dữ liệu dùng collation/tie-breaker nhất quán.
- [ ] Log/metric giúp tìm missing translations, fallback và lỗi formatting.

## 20. Cách áp dụng bảng chọn trong một thiết kế mới

Một quy trình sáu bước:

**Bước 1 — Xác định dữ liệu gốc.** Viết rõ amount/ratio, Currency, LocalDate/Instant, ID và thông điệp có key nào. Tránh nhận diện dữ liệu qua chuỗi đã được localize.

**Bước 2 — Xác định người nhận.** Ghi uiLocale, formatLocale, ZoneId và ngữ cảnh render web/email/PDF; không tự xem chúng là một thuộc tính.

**Bước 3 — Tra bảng API.** Với mỗi giá trị và thao tác, chọn API phù hợp. Nếu có tên người và số tiền trong câu, cần cả Collator khi sort, NumberFormat khi format và ResourceBundle/MessageFormat khi ghép câu; không trộn chức năng.

**Bước 4 — Định nghĩa fallback và failure.** Nếu thiếu bản dịch, locale không hỗ trợ, pattern sai hoặc parser không đọc hết chuỗi, hệ thống cần hành vi được quyết định trước.

**Bước 5 — Kiểm thử ở hai mức.** Test dữ liệu bất biến và các điều kiện API có stdout chính xác; test locale-specific output trên runtime/provider mục tiêu. Kết hợp visual test cho Unicode/bidi.

**Bước 6 — Review rủi ro.** Chấm rubric 0–20, ưu tiên rủi ro sai tiền/ngày, mất định danh và bảo mật trước lỗi mỹ thuật. Thêm regression test tương ứng trước khi phát hành.

## 21. Tổng kết

**Chọn đúng API địa phương hóa trong Java là chọn đúng ngữ nghĩa của bài toán.** **Locale** mô tả ngôn ngữ/vùng; **ResourceBundle/MessageFormat** dựng thông điệp; **NumberFormat/Currency/BigDecimal** giữ đúng số và tiền; **LocalDate/Instant/ZoneId/DateTimeFormatter** giải quyết ngày và thời điểm; **Collator/Normalizer/BreakIterator** xử lý các khía cạnh khác nhau của văn bản; **Bidi** và renderer đảm trách hướng hiển thị.

Bảng chọn API giúp tránh sử dụng một hàm tiện lợi sai chỗ; bài tập, đáp án và rubric giúp người học tự phát hiện lỗi thường gặp. Thành công của một sản phẩm đa locale không nằm ở số API được gọi, mà ở **việc dữ liệu nghiệp vụ luôn đúng, câu chữ phù hợp người dùng, fallback minh bạch, Unicode được giữ nguyên và kiểm thử được lặp lại trên môi trường thực sự triển khai**.
