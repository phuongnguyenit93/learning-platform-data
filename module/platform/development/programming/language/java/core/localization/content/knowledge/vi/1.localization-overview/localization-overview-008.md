# Kiến thức nền và trình tự học localization trong Java

> **Phạm vi:** Tổng quan kiến thức và lộ trình học localization cho ứng dụng Java 17+. Mục tiêu là biết cần học gì, theo thứ tự nào, vì sao từng phần quan trọng và tự triển khai được một ví dụ nhỏ trước khi đi sâu vào từng API.

## 1. Localization giải quyết bài toán gì?

Một ứng dụng phục vụ nhiều người dùng không thể giả định tất cả đều đọc cùng ngôn ngữ, viết số và ngày tháng theo cùng quy ước. Ví dụ, cùng một khoản tiền hoặc ngày giao hàng có thể cần được hiển thị khác nhau tùy ngôn ngữ, vùng và đơn vị tiền tệ.

Các khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Internationalization (i18n)** | Thiết kế phần mềm để có thể hỗ trợ nhiều ngôn ngữ/vùng mà không sửa logic nghiệp vụ cho mỗi thị trường. | Đưa thông điệp vào resource bundle, truyền `Locale` cho bộ định dạng. |
| **Localization (l10n)** | Điều chỉnh nội dung và cách trình bày cho một ngôn ngữ/vùng cụ thể. | Bản dịch tiếng Việt, định dạng ngày và số theo `vi-VN`. |
| **Locale** | Ngữ cảnh ngôn ngữ và vùng dùng để chọn quy tắc hiển thị. | `vi-VN`, `en-US`, `fr-FR`. |
| **Time zone** | Quy tắc múi giờ để biến một thời điểm tuyệt đối thành giờ địa phương. | `Asia/Ho_Chi_Minh`, `America/New_York`. |
| **Currency** | Đơn vị tiền tệ thực của dữ liệu/giá trị giao dịch. | VND, USD, EUR; không nên suy đoán từ ngôn ngữ giao diện. |

**i18n là khả năng của thiết kế, l10n là nội dung và quy tắc cụ thể.** Chỉ dịch chuỗi chưa đủ: ứng dụng còn cần xử lý số thập phân, phần trăm, tiền, ngày giờ, thứ tự sắp xếp văn bản, số nhiều, chiều chữ và bố cục giao diện khi phù hợp.

Một luồng xử lý điển hình:

```text
Người dùng / request
    ↓ chọn locale (ưu tiên đã lưu, lựa chọn UI, ngôn ngữ trình duyệt)
Locale + dữ liệu nghiệp vụ + mã thông điệp
    ↓ tra bản dịch và định dạng theo locale, zone, currency rõ ràng
Văn bản hiển thị cho người dùng
```

Dữ liệu gốc nên giữ dạng có kiểu như `BigDecimal`, `Instant`, `LocalDate` và mã thông điệp. Chuỗi đã định dạng chủ yếu là **kết quả ở ranh giới hiển thị**, không nên trở thành dữ liệu nghiệp vụ để tính toán hoặc lưu trữ.

## 2. Kiến thức nền cần có trước khi học API

1. **Java căn bản:** `String`, `Map`, classpath, exception và thao tác với tệp `.properties`. Nắm khái niệm lớp/thư viện và sự khác nhau giữa mã nguồn, tài nguyên và tệp đã biên dịch.
2. **Unicode và encoding:** Unicode mô tả ký tự; UTF-8 là cách mã hóa thành byte. Java `String` biểu diễn văn bản bằng các đơn vị UTF-16, vì vậy `length()` hoặc một `char` không luôn tương ứng một ký tự người dùng nhìn thấy. Khi đọc/ghi tệp, truyền charset rõ ràng (thường `StandardCharsets.UTF_8`).
3. **Ngôn ngữ và vùng:** Mã ngôn ngữ như `vi` hoặc `en` khác mã vùng như `VN` hoặc `US`. Tag BCP 47 như `zh-Hant-TW` còn có thể mang thông tin chữ viết (script). Không coi các tag gần giống là hoàn toàn tương đương.
4. **Kiểu dữ liệu ngày giờ:** Phân biệt `Instant` (thời điểm), `LocalDate` (ngày lịch), `LocalDateTime` (không có múi giờ), `ZonedDateTime` (có zone). `Locale` không quyết định múi giờ.
5. **Phân biệt hiển thị và dữ liệu:** Giá trị `1234.5` vẫn là một số, dù màn hình hiển thị `1.234,5` hay `1,234.5`. Cũng vậy, bản dịch nhãn không làm thay đổi mã trạng thái hoặc định danh.

**Điểm kiểm tra trước khi tiếp tục:** giải thích được tại sao chuyển sang tiếng Việt chưa chắc làm giờ chuyển sang GMT+7, và tại sao không nên dùng dấu phẩy/dấu chấm của chuỗi hiển thị để tính tiền.

## 3. Bản đồ công cụ trong Java

| Nhiệm vụ | API/cơ chế chính | Điều cần hiểu |
| --- | --- | --- |
| Biểu diễn và chọn ngôn ngữ/vùng | `java.util.Locale`, `Locale.forLanguageTag(...)` | Language tag, tag được hỗ trợ, fallback. |
| Tách thông điệp khỏi mã | `java.util.ResourceBundle`, tệp `messages_*.properties` | Base name, key, candidate locales, tài nguyên thiếu. |
| Chèn tham số trong bản dịch | `java.text.MessageFormat` | Placeholder đánh số, escape dấu nháy đơn, format theo locale. |
| Hiển thị/phân tích số, tiền, phần trăm | `java.text.NumberFormat`, `java.util.Currency` | Ký hiệu, dấu nhóm, số chữ số thập phân, currency thực. |
| Hiển thị ngày giờ | `java.time.format.DateTimeFormatter`, `FormatStyle` | Locale ảnh hưởng ngôn ngữ/mẫu hiển thị; `ZoneId` ảnh hưởng giờ. |
| So sánh và phân đoạn văn bản | `java.text.Collator`, `BreakIterator` | Sắp xếp theo ngôn ngữ, biên từ/cụm ký tự. |
| Chuẩn hóa Unicode | `java.text.Normalizer` | Dạng NFC/NFD và so sánh văn bản một cách nhất quán. |
| Kiểm thử | JUnit hoặc chương trình kiểm chứng nhỏ | Bao phủ locale được hỗ trợ, khóa bị thiếu, fallback và dữ liệu biên. |

Java dùng dữ liệu locale của JDK; chi tiết hiển thị có thể khác giữa phiên bản JDK hoặc dữ liệu CLDR. Vì thế, ở các kiểm thử định dạng, cần phân biệt đặc tả bắt buộc với cách hiển thị phụ thuộc dữ liệu locale.

## 4. Trình tự học đề xuất: từ nền tảng đến ứng dụng

### Chặng 1 — Đọc và truyền `Locale`

Thực hành với:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.forLanguageTag("en-US");
System.out.println(vi.toLanguageTag()); // vi-VN
System.out.println(en.getLanguage());    // en
System.out.println(en.getCountry());     // US
```

Đây là đoạn minh họa đặt trong phương thức Java có thể chạy, không phải tệp Java độc lập.

Nắm cách xác định locale từ lựa chọn đã lưu, cài đặt người dùng hoặc tiêu đề `Accept-Language`. Với ứng dụng web, hãy đối chiếu danh sách locale **thực sự hỗ trợ**, đặt locale rõ ràng cho từng request, và có chính sách mặc định nhất quán. `Locale.getDefault()` chỉ là mặc định của tiến trình; gọi `Locale.setDefault(...)` theo từng request trên máy chủ nhiều người dùng dễ gây lẫn ngôn ngữ giữa các request.

**Hoàn thành khi:** phân biệt được locale hiển thị, locale mặc định của JVM và zone của người dùng.

### Chặng 2 — Bóc thông điệp khỏi code bằng `ResourceBundle`

Thay các literal như `"Hello"` rải rác trong mã bằng khóa ổn định, chẳng hạn `welcome`, `order.confirmed`. Chuẩn bị bản dịch riêng cho từng locale được hỗ trợ. Học quy tắc tìm tệp: base name `messages` có thể khớp `messages_vi_VN.properties`, sau đó `messages_vi.properties` và bản gốc `messages.properties` (còn có fallback qua default locale tùy cách gọi API).

Cần biết: khóa nào cũng có bản dịch? Nếu một khóa thiếu thì sao? Nếu toàn bộ bundle thiếu, `ResourceBundle.getBundle(...)` ném `MissingResourceException`; nếu bundle tồn tại nhưng khóa thiếu, `getString(...)` cũng có thể ném lỗi này. Bản gốc `messages.properties` có thể làm fallback, nhưng **không dùng fallback để che giấu bản dịch còn thiếu trong kiểm thử**.

Từ Java 9, tài nguyên `.properties` được `ResourceBundle` nạp theo UTF-8 mặc định (có tương thích ngược trong một số trường hợp). Điều đó không có nghĩa mọi API đọc `.properties` đều cùng một quy tắc; khi đọc tệp tùy ý vẫn phải xét charset của API.

**Hoàn thành khi:** đổi lựa chọn locale và ứng dụng lấy đúng thông điệp, đồng thời giải thích được thứ tự fallback.

### Chặng 3 — Chèn biến vào thông điệp đúng cách

Tránh nối chuỗi theo một thứ tự cố định như `"Hello " + name` khi các ngôn ngữ có thể đảo thứ tự từ. Dùng khóa chứa mẫu `"Hello, {0}!"` rồi định dạng bằng `MessageFormat` với locale cần hiển thị. Đối số số/ngày có thể được định dạng dựa vào locale khi mẫu yêu cầu.

Lưu ý: `MessageFormat` dùng dấu nháy đơn `'` làm ký tự escape trong mẫu. Cần kiểm tra ví dụ có dấu nháy, dấu ngoặc nhọn và tham số sai chỉ số. Ngữ pháp số nhiều và giống ngữ pháp phức tạp không được giải quyết đầy đủ bằng mẫu đơn giản của Java 17; có thể tìm hiểu thư viện như ICU4J khi thực sự cần.

**Hoàn thành khi:** bản dịch có placeholder vẫn có thể đổi thứ tự các tham số mà không sửa code gọi.

### Chặng 4 — Số, phần trăm và tiền tệ

Học `NumberFormat.getNumberInstance(locale)`, `getPercentInstance(locale)` và `getCurrencyInstance(locale)`. Đừng tự chèn dấu nhóm hoặc thay dấu chấm bằng dấu phẩy; bộ định dạng biết cách chọn ký hiệu theo locale. Khi định dạng giao dịch, truyền mã `Currency` của **giao dịch thực**, ví dụ USD, thay vì mặc nhiên coi locale Việt Nam là giá trị VND.

Phân biệt rõ **định dạng** với **quy đổi tiền**: đổi nhãn USD thành VND không làm giá trị được chuyển đổi theo tỷ giá. Với tiền cần độ chính xác, ưu tiên `BigDecimal` và quy tắc làm tròn nghiệp vụ. Khi phân tích chuỗi nhập, dùng API parse cùng locale đã chọn, kiểm tra tiêu thụ toàn bộ chuỗi và xác thực giá trị; không xem một lần parse thành công là bằng chứng đầu vào hợp lệ hoàn toàn.

**Hoàn thành khi:** một giá trị số bất biến được hiển thị đúng với hai locale mà không đổi giá trị nguồn.

### Chặng 5 — Ngày, giờ và múi giờ

Học `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(locale)` để hiển thị `LocalDate`. Sau đó học `Instant.atZone(zoneId)` hoặc `ZonedDateTime` khi một thời điểm cần hiển thị theo múi giờ người dùng.

Ba dữ kiện cần lưu độc lập khi thích hợp: **thời điểm**, **múi giờ** và **locale**. Ví dụ, một `Instant` có thể được chuyển sang `Asia/Ho_Chi_Minh` để ra giờ địa phương, rồi định dạng bằng `vi-VN` để dùng ngôn ngữ/kiểu trình bày phù hợp.

**Hoàn thành khi:** giải thích được vì sao đổi locale từ `en-US` sang `vi-VN` có thể đổi chữ/thứ tự ngày nhưng không tự đổi time zone.

### Chặng 6 — Quy tắc văn bản theo ngôn ngữ

Tìm hiểu `Collator` khi cần sắp xếp chuỗi để hiển thị cho người dùng (thay vì so sánh byte hoặc `String.compareTo`). `BreakIterator` hỗ trợ ranh giới từ/câu/ký tự theo locale; `Normalizer` hỗ trợ chuẩn hóa biểu diễn Unicode. Chú ý việc viết hoa/viết thường có thể phụ thuộc locale, ví dụ chữ I trong tiếng Thổ Nhĩ Kỳ; dùng `toLowerCase(Locale.ROOT)` cho một số xử lý định danh nội bộ khi quy tắc mong muốn độc lập ngôn ngữ, nhưng đừng mặc định đó là giải pháp cho mọi so sánh văn bản.

**Hoàn thành khi:** nhận ra các lỗi do tách chuỗi theo `char`, sắp xếp máy móc hoặc ép chữ hoa/thường theo default locale.

### Chặng 7 — Gắn vào kiến trúc ứng dụng

Thiết kế lớp hoặc dịch vụ nhận **locale của request** và mã thông điệp, trả chuỗi hiển thị. Dữ liệu nghiệp vụ lưu các giá trị có kiểu và khóa ổn định. Quản lý nguồn dịch bằng quy ước đặt key, bản gốc, quy trình review bản dịch, và cơ chế báo thiếu key. Phần giao diện có thể cần mở rộng chiều rộng nhãn, định dạng biểu mẫu, hỗ trợ màn hình đọc và chiều chữ phải sang trái nếu thị trường yêu cầu.

**Hoàn thành khi:** thêm ngôn ngữ mới chủ yếu qua tài nguyên và cấu hình, không nhân bản logic nghiệp vụ theo ngôn ngữ.

### Chặng 8 — Kiểm thử và theo dõi chất lượng

Kiểm tra có chủ đích ít nhất hai locale được hỗ trợ, một locale không hỗ trợ, key còn thiếu, placeholder sai, chuỗi tiếng Việt có dấu, số âm, ngày cuối tháng, và thời điểm sát ngày khi đổi zone. Kiểm tra text mở rộng, pseudo-localization (ví dụ kéo dài nhãn để lộ lỗi UI), và nội dung RTL khi có nhu cầu. Trong CI, đừng chỉ phụ thuộc mặc định của máy chạy: chỉ rõ locale/zone ở những test cần kết quả ổn định.

**Hoàn thành khi:** test chứng minh thay đổi ngôn ngữ không ảnh hưởng dữ liệu nguồn hoặc người dùng khác.

## 5. Ví dụ Java 17+ chạy được: hai ngôn ngữ trong một chương trình

Tạo **ba tệp cùng thư mục**. Với bản demo nhỏ này, `ResourceBundle` chọn tệp tiếng Việt hoặc tiếng Anh, còn `MessageFormat` chèn tên theo mẫu của từng bản dịch.

**`messages_vi.properties`**

```properties
welcome=Xin chào, {0}!
```

**`messages_en.properties`**

```properties
welcome=Hello, {0}!
```

**`LocalizationDemo.java`**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizationDemo {
    private static void greet(String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);
        ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
        MessageFormat message =
                new MessageFormat(bundle.getString("welcome"), locale);
        System.out.println(locale.toLanguageTag() + ": "
                + message.format(new Object[] {"An"}));
    }

    public static void main(String[] args) {
        greet("vi-VN");
        greet("en-US");
    }
}
```

Lưu hai tệp `.properties` ở **UTF-8**. Chạy bằng terminal trong chính thư mục chứa ba tệp:

```bash
javac -encoding UTF-8 LocalizationDemo.java
java -cp . LocalizationDemo
```

Kết quả chính xác của ví dụ:

```text
vi-VN: Xin chào, An!
en-US: Hello, An!
```

**Vì sao chạy đúng?** `Locale.forLanguageTag("vi-VN")` tạo locale tiếng Việt tại Việt Nam. `ResourceBundle` tìm tên cụ thể, sau đó tìm `messages_vi.properties`, lấy `welcome`; `MessageFormat` thay `{0}` bằng `An`. Lặp lại với `en-US` cho bản tiếng Anh. Cả hai bundle đều có sẵn nên kết quả không phụ thuộc vào default locale của JVM.

Để quan sát định dạng số và ngày theo locale, có thể bổ sung vào `greet` sau câu in thông điệp:

```java
java.text.NumberFormat number =
        java.text.NumberFormat.getNumberInstance(locale);
java.time.LocalDate date = java.time.LocalDate.of(2026, 10, 28);
java.time.format.DateTimeFormatter dateFormatter =
        java.time.format.DateTimeFormatter
                .ofLocalizedDate(java.time.format.FormatStyle.LONG)
                .withLocale(locale);
System.out.println(number.format(12345.67));
System.out.println(dateFormatter.format(date));
```

Đoạn bổ sung này nằm **bên trong phương thức `greet`**, dùng biến `locale` đã có. Đầu ra thể hiện quy ước locale và có thể khác đôi chút theo dữ liệu CLDR/JDK; không nên hard-code toàn bộ dấu và tên tháng như một bất biến xuyên mọi phiên bản.

## 6. Các lỗi thường gặp và cách tự kiểm tra

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `Locale.setDefault(...)` cho mỗi request web | Locale mặc định là trạng thái cấp JVM, gây nhiễu giữa request đồng thời. | Truyền `Locale` tường minh qua tầng hiển thị. |
| Coi locale và time zone là một | Ngôn ngữ không xác định vị trí/giờ hiện tại. | Quản lý riêng `Locale` và `ZoneId`. |
| Nối literal vào mã nghiệp vụ | Khó dịch, khó thay thứ tự từ, khó kiểm tra đủ key. | Dùng key + bundle + tham số. |
| Dùng nối chuỗi để định dạng số/ngày/tiền | Sai dấu thập phân, thứ tự ngày, ký hiệu và đơn vị. | Dùng formatter theo locale và dữ liệu tiền tệ thật. |
| Tin rằng locale tự quy đổi tỷ giá | Định dạng tiền không thực hiện chuyển đổi giá trị. | Quy đổi là bài toán nghiệp vụ riêng, với nguồn tỷ giá rõ ràng. |
| Chỉ test mặc định tiếng Anh | Bỏ sót key thiếu, dấu tiếng Việt, thông điệp dài, fallback. | Test ma trận locale và bản dịch. |
| Xem `String.length()` là số ký tự người đọc thấy | Unicode có surrogate pair và chuỗi nhiều code point. | Chọn API theo đơn vị cần xử lý; kiểm tra grapheme/text boundary khi cần. |
| Dùng `String.compareTo` để sắp xếp tên trên UI quốc tế | Thứ tự code unit có thể khác thứ tự chữ của ngôn ngữ. | Dùng `Collator` cho sắp xếp phục vụ người đọc. |
| Chọn bản dịch chỉ theo quốc gia | Một quốc gia có thể dùng nhiều ngôn ngữ; một ngôn ngữ có nhiều biến thể vùng. | Đọc language tag, hỗ trợ fallback và ưu tiên đã chọn. |

### Checklist thực hành để tự đánh giá

- [ ] Phân biệt i18n, l10n, `Locale`, time zone và currency.
- [ ] Đọc được `vi-VN`, `en-US` và biết chọn locale từ tập được hỗ trợ.
- [ ] Tạo được hai tệp resource và lấy thông điệp qua `ResourceBundle`.
- [ ] Dùng `MessageFormat` với placeholder đúng; hiểu lưu ý escape dấu nháy.
- [ ] Hiển thị cùng số/ngày theo hai locale mà không đổi dữ liệu nguồn.
- [ ] Không dùng locale mặc định toàn JVM làm trạng thái theo request.
- [ ] Mô tả được fallback, cách phát hiện key thiếu và cách kiểm thử.
- [ ] Biết khi nào cần học sâu thêm về collation, Unicode, plural/gender và RTL.

## 7. Bài tập nối tiếp theo mức độ

1. **Cơ bản:** mở rộng demo với khóa `farewell` và bản dịch riêng; kiểm chứng cả hai ngôn ngữ. Cố tình xóa một key để quan sát `MissingResourceException`, sau đó khôi phục.
2. **Ứng dụng:** viết phương thức `renderReceipt(Locale locale, BigDecimal amount, Currency currency, LocalDate date)`. Định dạng tiền và ngày theo locale, nhưng giữ nguyên amount và currency; thêm kiểm thử `vi-VN`/`en-US`.
3. **Tích hợp:** ứng dụng nhỏ cho phép đổi ngôn ngữ theo lựa chọn người dùng. Mỗi request dùng locale riêng, có fallback rõ ràng, test trường hợp thiếu tài nguyên và thay đổi đồng thời giữa hai người dùng.

**Thứ tự ghi nhớ:** *Locale và Unicode → ResourceBundle → MessageFormat → định dạng số/tiền/ngày → xử lý văn bản → tích hợp và kiểm thử.* Khi hoàn thành chuỗi này, người học có đủ nền tảng để nghiên cứu sâu từng mảng localization mà không nhầm bản dịch với dữ liệu nghiệp vụ hoặc múi giờ.