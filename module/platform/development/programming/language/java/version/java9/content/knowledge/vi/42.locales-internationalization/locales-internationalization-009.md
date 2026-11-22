# Kiểm thử tiếng Việt và tránh phụ thuộc chuỗi định dạng của máy

Trong ứng dụng đa ngôn ngữ, cùng một giá trị ngày, số tiền hoặc thông báo có thể được trình bày khác nhau theo `Locale`, múi giờ, dữ liệu bản địa hóa của JDK và encoding. Bài này hướng dẫn kiểm thử tiếng Việt (`vi-VN`) có thể chạy tin cậy trên máy cá nhân, CI và máy chủ, kể cả khi cấu hình hệ điều hành không phải tiếng Việt. Ví dụ dùng những API Java vẫn phù hợp hiện nay; chương trình chính biên dịch được với Java 17 trở lên.

## 1. Mục tiêu và bối cảnh Java 9

Sau bài học, bạn có thể:

- Kiểm tra chuỗi có dấu tiếng Việt qua UTF-8 và các dạng Unicode tương đương mà không làm mất nghĩa dữ liệu.
- Phân biệt **giá trị nghiệp vụ** với **chuỗi hiển thị đã bản địa hóa** và với **bản dịch do nhóm phát triển sở hữu**.
- Truyền tường minh `Locale`, `ZoneId`, `Currency`, `Charset` và thời gian cố định; tránh test phụ thuộc cấu hình máy chạy.
- Viết assertion cho số, tiền, ngày, bản dịch theo hợp đồng thực sự của sản phẩm; biết trường hợp nào nên hoặc không nên so khớp chuỗi format chính xác.
- Chạy test tiếng Việt với nhiều cấu hình mặc định của JVM và chẩn đoán khác biệt ở CI.

**Điểm liên quan đến Java 9:** JDK 9 ưu tiên dữ liệu CLDR (Common Locale Data Repository) cho nhiều dịch vụ locale. Một số kết quả định dạng ngày, số, tên bản địa hóa có thể khác JDK trước đó; CLDR còn được cập nhật theo các đời JDK sau này. Cũng từ Java 9, *property resource bundle* đọc UTF-8 theo mặc định. Hai thay đổi vẫn có ý nghĩa hiện nay: không nên dùng các literal format của một phiên bản JDK làm oracle chung cho mọi runtime, và nên quản lý encoding tài nguyên tiếng Việt rõ ràng.

## 2. Tách ba lớp dữ liệu khi kiểm thử

| Lớp | Ví dụ | Điều cần xác nhận |
| --- | --- | --- |
| Dữ liệu nghiệp vụ | `BigDecimal("123456.50")`, `LocalDate`, `Instant`, `Currency("VND")` | Số, ngày, thời điểm, mã tiền và quy tắc làm tròn đúng |
| Trình bày người dùng | Số có phân nhóm, ngày có tên tháng, tiền có ký hiệu | Đúng Locale, đúng múi giờ, hiển thị có nghĩa theo yêu cầu giao diện |
| Văn bản ứng dụng sở hữu | `"Xin chào, Lan!"`, thông báo lỗi, nhãn tiếng Việt | Chính tả/dấu, câu chữ, key bản dịch, tham số và fallback |

Một `NumberFormat` có thể cho ra hai chuỗi khác nhau từ cùng một số mà cả hai đều hợp lệ theo Locale tương ứng. `DateTimeFormatter` cũng vậy. Ngược lại, một chuỗi dịch viết tay `"Xin chào, Lan!"` do đội sản phẩm sở hữu có thể được kiểm tra đúng từng ký tự.

**Nguyên tắc:** giữ giá trị có kiểu rõ ràng bên trong chương trình; chỉ format tại ranh giới hiển thị. API giữa các dịch vụ nên dùng dữ liệu theo hợp đồng máy-máy, ví dụ JSON number hoặc ISO 8601 cho thời điểm thích hợp, không dùng chuỗi số/ngày hiển thị cho người dùng.

## 3. Vì sao kết quả thay đổi theo máy?

Có ít nhất sáu nguồn ảnh hưởng độc lập:

1. `Locale.getDefault()` và đặc biệt `Locale.getDefault(Locale.Category.FORMAT)` được JVM thiết lập từ môi trường khởi động và có thể thay đổi trong quá trình chạy. Các phương thức không có tham số `Locale` như `NumberFormat.getInstance()` thường dùng FORMAT Locale mặc định. `System.out.printf(...)` cũng nhạy với Locale.
2. `ZoneId.systemDefault()` phản ánh múi giờ máy chạy. Cùng một `Instant` có thể là ngày khác nhau ở UTC và tại Việt Nam. **Locale không đồng nghĩa với múi giờ.**
3. Encoding: khi qua file, byte stream, HTTP hay hệ thống ngoài, dùng `StandardCharsets.UTF_8` nơi cần đảm bảo tái lập chính xác. Đừng giả định default charset giống nhau giữa mọi phiên bản/cấu hình JVM.
4. Dữ liệu CLDR/provider có thể đổi mẫu ngày, dấu thập phân, dấu nhóm, khoảng trắng không ngắt dòng, ký hiệu tiền tệ hoặc cách hiển thị tên. Các giá trị này không phải hằng số bất biến do ứng dụng kiểm soát.
5. `ResourceBundle` có thể fallback khi thiếu bản tiếng Việt. Ứng dụng vẫn hiển thị văn bản nhưng ngôn ngữ sai.
6. Unicode có chuỗi dựng sẵn và chuỗi gồm nhiều dấu tổ hợp trông giống nhau, trong khi `String.equals` vẫn so sánh chính xác các đơn vị mã của chuỗi.

**Thiết kế test tốt:** truyền `Locale` của người dùng vào API định dạng; truyền `ZoneId` của ngữ cảnh hiển thị; đưa `Clock` vào logic phụ thuộc thời gian; xác định encoding khi chuyển thành bytes. Tránh gọi `Locale.setDefault(...)` để đổi môi trường trong test chạy song song, vì mặc định là trạng thái dùng chung toàn JVM.

## 4. Ví dụ Java 17+ tự chạy, không cần thư viện ngoài

Tạo tệp **`VietnameseLocaleChecks.java`** lưu ở UTF-8. Chương trình có 10 phép kiểm tra về Locale, tiếng Việt, Unicode, số, ngày, múi giờ, tiền và mã kỹ thuật.

```java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public final class VietnameseLocaleChecks {
    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final ZoneId VN_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    private static int passed;

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        passed++;
    }

    private static NumberFormat vndFormatter(Locale locale) {
        NumberFormat formatter = NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(Currency.getInstance("VND"));
        return formatter;
    }

    public static void main(String[] args) {
        // 1. Locale vi-VN được tạo qua thẻ ngôn ngữ BCP 47.
        check("vi".equals(VI.getLanguage()) && "VN".equals(VI.getCountry()),
                "Locale vi-VN");

        // 2. Chuyển qua byte UTF-8 vẫn giữ nguyên tiếng Việt có dấu.
        String name = "Tiếng Việt: Tết, Đà Nẵng, Nguyễn Thị Ánh";
        byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
        check(name.equals(new String(utf8, StandardCharsets.UTF_8)),
                "UTF-8 round-trip");

        // 3–4. Ký tự dựng sẵn và các dấu tổ hợp có biểu diễn khác nhau.
        String composed = "\u1EAF";
        String decomposed = "a\u0306\u0301";
        check(!composed.equals(decomposed), "Raw Unicode differs");
        check(Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)),
                "NFC equivalence");

        // 5. Kiểm tra ngữ nghĩa số, không chốt dấu nhóm/thập phân.
        NumberFormat numberFormat = NumberFormat.getNumberInstance(VI);
        double amount = 1234567.5;
        String numberText = numberFormat.format(amount);
        ParsePosition position = new ParsePosition(0);
        Number parsedNumber = numberFormat.parse(numberText, position);
        check(parsedNumber != null
                && position.getIndex() == numberText.length()
                && Math.abs(parsedNumber.doubleValue() - amount) < 0.0000001,
                "Number semantic round-trip");

        // 6. Format và parse lại ngày với cùng Locale tường minh.
        LocalDate date = LocalDate.of(2026, 11, 7);
        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(VI);
        check(date.equals(LocalDate.parse(dateFormat.format(date), dateFormat)),
                "Localized date round-trip");

        // 7. Xác định múi giờ, không dùng múi giờ máy CI.
        Instant moment = Instant.parse("2026-11-07T00:00:00Z");
        check(moment.atZone(VN_ZONE).getHour() == 7, "Explicit zone");

        // 8. Format máy-máy được xác định rõ qua ISO.
        check("2026-11-07T00:00:00Z"
                .equals(DateTimeFormatter.ISO_INSTANT.format(moment)),
                "Stable ISO instant");

        // 9. Tiền tệ có mã VND, không chốt ký hiệu hay khoảng trắng.
        Currency vnd = Currency.getInstance("VND");
        String shownMoney = vndFormatter(VI).format(new BigDecimal("123456"));
        check("VND".equals(vnd.getCurrencyCode()) && !shownMoney.isBlank(),
                "VND presentation");

        // 10. Mã kỹ thuật nên được xử lý theo Locale.ROOT.
        check("admin".equals("ADMIN".toLowerCase(Locale.ROOT)),
                "Stable technical key");

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch, thực thi:

```bash
javac --release 17 -encoding UTF-8 VietnameseLocaleChecks.java
java VietnameseLocaleChecks
```

Stdout khi mọi phép kiểm tra đạt:

```text
PASS: 10 checks
```

Thử cùng chương trình với hai cấu hình default khác nhau. Lưu ý JVM options `-D` nằm trước tên class:

```bash
java -Duser.language=vi -Duser.country=VN -Duser.timezone=Asia/Ho_Chi_Minh VietnameseLocaleChecks
java -Duser.language=en -Duser.country=US -Duser.timezone=UTC VietnameseLocaleChecks
```

Hai lần đều phải hoàn thành 10 checks vì chương trình không sử dụng default Locale/timezone cho logic được test. Đây là bài thử nhỏ giúp phát hiện dependency ngầm; một hệ thống thật cần mở rộng sang kiểm thử endpoint, persistence và giao diện.

### Giải thích các assertion quan trọng

**Số:** mã không so `"1.234.567,5"` vì không muốn khóa dấu phân cách theo phiên bản CLDR. `NumberFormat.parse(String)` có thể chỉ parse tiền tố hợp lệ; vì thế dùng `ParsePosition` và yêu cầu `position.getIndex() == numberText.length()` để đảm bảo không còn rác ở cuối. Round-trip có nghĩa khi mức chính xác format bảo toàn giá trị; ví dụ chọn `.5` để tránh phép làm tròn không mong muốn.

**Ngày:** dùng cùng `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(VI)` cho format và parse, rồi so `LocalDate`. Mẫu/ngôn ngữ của phần trình bày có thể được JDK cập nhật, còn ngày nghiệp vụ phải giữ nguyên.

**Tiền:** `Currency.getInstance("VND")` giúp xác định mã. Cách hiển thị ký hiệu, thứ tự, khoảng trắng và số lẻ có thể do locale data chi phối. Một `NumberFormat` dành cho tiền có thể làm tròn theo đơn vị tiền, vì thế **không** parse chuỗi tiền rồi kỳ vọng luôn lấy lại chính xác `BigDecimal` ban đầu.

**Unicode:** `composed` và `decomposed` không bằng nhau theo `String.equals`, nhưng sau khi cùng chuẩn hóa về NFC thì tương đương. Chuẩn hóa chỉ nên áp dụng nếu hợp đồng xử lý văn bản có yêu cầu; dữ liệu nguồn đôi khi cần được giữ nguyên từng code unit/byte.

## 5. Kiểm thử Unicode tiếng Việt đủ sâu

Dữ liệu kiểm thử nên có `"Nguyễn"`, `"Trường"`, `"Đặng"`, `"Đà Nẵng"`, `"Thừa Thiên Huế"`, `"ắ"`, `"ẫ"`, `"ỵ"`, `"đ/Đ"` và các chuỗi tổ hợp Unicode. Với mỗi ca cần định nghĩa hành vi: lưu/đọc nguyên văn, tìm kiếm, đồng nhất tên, đổi chữ hoa/thường, hiển thị hay xuất báo cáo.

- **UTF-8:** so sánh dữ liệu trước/sau `getBytes(StandardCharsets.UTF_8)` và `new String(..., StandardCharsets.UTF_8)`. Với ứng dụng web/DB/file, kiểm tra cấu hình mã hóa ở từng ranh giới, thay vì chỉ test chuỗi trong bộ nhớ.
- **NFC/NFD:** nếu hệ thống coi hai biểu diễn chuẩn Unicode là cùng một giá trị tìm kiếm, chuẩn hóa hai phía trước khi so sánh. Nếu yêu cầu lưu đúng input, giữ chuỗi gốc và kiểm thử round-trip nguyên văn; không âm thầm normalise khi lưu.
- **Dấu tiếng Việt:** bỏ dấu có thể khiến các tên hoặc từ khác nhau trở thành cùng một chuỗi. `Normalizer` không mặc nhiên “xóa dấu”; nếu có tìm kiếm không phân biệt dấu, đó là một feature riêng cần đặc tả và test.
- **Độ dài:** `String.length()` đếm UTF-16 code unit, không phải số ký tự người dùng nhìn thấy. Chuỗi dấu tổ hợp hoặc ký tự ngoài BMP có thể khiến những con số này khác nhau. Test giới hạn chiều dài cần làm rõ đơn vị tính của sản phẩm.
- **Khoảng trắng và hiển thị:** NBSP/narrow NBSP có thể xuất hiện hợp lệ trong định dạng tiền hoặc số. Không luôn thay toàn bộ whitespace thành dấu cách thường chỉ để assertion dễ qua; điều đó có thể che vấn đề UX hoặc làm sai văn bản.
- **Chữ hoa/thường:** xử lý tên và ngôn ngữ người dùng theo yêu cầu của locale/feature. `toLowerCase(Locale.ROOT)` phù hợp cho **mã kỹ thuật**, không nên coi đó là quy tắc so sánh ngôn ngữ tiếng Việt trong mọi tình huống.

Phân biệt **kiểm tra nội dung do ứng dụng sở hữu** (được quyền so khớp chính xác tên và thông điệp) với **kiểm tra chuỗi do JDK sinh ra** (chọn assertion ngữ nghĩa hoặc kiểm thử giao diện có runtime được kiểm soát).

## 6. Số và tiền: những điểm dễ gây test sai

Dùng đúng API theo chức năng: `NumberFormat.getNumberInstance(locale)`, `getPercentInstance(locale)`, `getCurrencyInstance(locale)`. Không đưa số hiển thị cho người Việt (như có dấu phân nhóm/thập phân) qua API máy-máy nếu hợp đồng không định nghĩa một định dạng như vậy. Hãy lưu số dưới kiểu dữ liệu số, tách bước parse input người dùng khỏi bước format output.

| Tình huống | Kiểm thử bền vững | Cách kiểm thử dễ vỡ |
| --- | --- | --- |
| Tổng tiền sau thuế | So giá trị `BigDecimal`, quy tắc scale và `RoundingMode` đã quy định | So chuỗi tiền từ `NumberFormat` |
| Tiền VND | Kiểm tra mã `"VND"` và giá trị nghiệp vụ | Chốt ký hiệu `₫` cùng vị trí dấu cách ở mọi JDK |
| Số nhập từ UI | Parse theo Locale khai báo, dùng `ParsePosition`, kiểm tra toàn bộ input | `replace(",", ".")` hoặc `replace(".", "")` tùy tiện |
| Phần trăm | Kiểm thử tỷ lệ số trước/sau chính sách format được chỉ định | Giả định ký hiệu `%` luôn cách số giống nhau |
| Dữ liệu API | Kiểu số, JSON number hay decimal string theo schema rõ ràng | Gửi chuỗi format từ Locale máy chủ |

`NumberFormat` là formatter có thể thay đổi trạng thái (`setCurrency`, cấu hình fraction digits...). Đừng dùng chung một instance mutable cho nhiều luồng mà không có cơ chế bảo vệ. Trong code dịch vụ, tạo formatter theo thao tác hoặc chọn thiết kế đảm bảo thread safety; `DateTimeFormatter` thì bất biến và có thể chia sẻ an toàn.

Khi xử lý dữ liệu tài chính đòi hỏi độ chính xác cao, nên giữ `BigDecimal` ở mô hình; nếu parse số thập phân chính xác qua `DecimalFormat`, cấu hình parse thành `BigDecimal` (`setParseBigDecimal(true)`) và xác nhận tiêu thụ hết input. Dù vậy, chuỗi tiền đã làm tròn để hiển thị không phải nguồn khôi phục giá trị kế toán nguyên bản.

## 7. Ngày/giờ: kiểm soát Locale, ZoneId và Clock

Ba khái niệm cần phân biệt:

- `LocalDate`: một ngày trên lịch, không kèm múi giờ.
- `Instant`: một thời điểm tuyệt đối trên trục thời gian.
- `ZoneId`: quy tắc chuyển thời điểm sang ngày/giờ địa phương, ví dụ `Asia/Ho_Chi_Minh`.

`DateTimeFormatter.withLocale(VI)` chọn dữ liệu bản địa hóa khi hiển thị; **không** tự thiết lập múi giờ Việt Nam. Với thông tin giờ từ một `Instant`, phải chuyển rõ sang zone cần hiển thị. Đối với dữ liệu giao tiếp máy-máy, dùng ISO format có kiểu phù hợp, chẳng hạn `DateTimeFormatter.ISO_INSTANT` cho `Instant`.

Nếu logic phụ thuộc “hôm nay”, đừng gọi `LocalDate.now()` ngay trong hàm không thể điều khiển; tiêm một `Clock` để test được:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId vnZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-07T00:00:00Z"), vnZone);
LocalDate todayInVn = LocalDate.now(fixedClock);

if (!LocalDate.of(2026, 11, 7).equals(todayInVn)) {
    throw new AssertionError("Unexpected local date");
}
```

Đây là đoạn code để đặt trong một phương thức hoặc test, **không** phải file Java độc lập. Trong code production, inject `Clock` và `ZoneId` từ bên ngoài thành phần nghiệp vụ.

Một bộ test nên kiểm tra ít nhất hai zone, ví dụ `UTC` và `Asia/Ho_Chi_Minh`, nhất là tại ranh giới ngày. Không dùng `new Date().toString()`, `ZoneId.systemDefault()` hoặc kết quả format mặc định của máy để dựng expected value cho logic thời gian. Khi UI cần một chuỗi ngày chính xác đến từng ký tự, viết test trình bày riêng và quản lý phiên bản runtime/tài nguyên locale dùng cho snapshot.

## 8. Kiểm thử bản dịch ứng dụng và cơ chế fallback

Các thông điệp do ứng dụng viết là dữ liệu có thể khẳng định chính xác. Giả sử có hai file trong classpath, lưu bằng UTF-8:

**`messages.properties`**

```properties
welcome=Hello, {0}!
```

**`messages_vi.properties`**

```properties
welcome=Xin chào, {0}!
```

Mã sau có thể đặt trong phương thức test hoặc `main` sau khi hai tài nguyên đã nằm trong classpath; đây là đoạn minh họa có phụ thuộc file resource, không phải chương trình độc lập:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

Locale vi = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("messages", vi);

// Tránh test vô tình chấp nhận bản dịch bị fallback sang ngôn ngữ khác.
if (!"vi".equals(bundle.getLocale().getLanguage())) {
    throw new AssertionError("Vietnamese bundle was not selected");
}

String actual = new MessageFormat(bundle.getString("welcome"), vi)
        .format(new Object[] {"Lan"});
if (!"Xin chào, Lan!".equals(actual)) {
    throw new AssertionError("Wrong Vietnamese message: " + actual);
}
```

Tên file `messages_vi.properties` là một bản dịch tiếng Việt có thể được chọn cho Locale `vi-VN` nhờ cơ chế candidate locales. So khớp `"Xin chào, Lan!"` là hợp lý vì câu dịch do nhóm sở hữu. Việc kiểm tra `bundle.getLocale()` còn giúp nhận ra tình huống thiếu bundle `vi` mà hệ thống rơi về bản mặc định.

**Encoding:** từ JDK 9, `PropertyResourceBundle` đọc UTF-8 theo mặc định và có cơ chế fallback để tương thích tài nguyên byte cũ. Cách này không đồng nghĩa với tất cả API đọc `.properties` (ví dụ `Properties.load(InputStream)` có quy tắc encoding riêng). Lưu resource bằng UTF-8, xác minh encoding trong build, và khi yêu cầu phát hiện lỗi encoding ngay lập tức thì chọn chế độ đọc nghiêm ngặt theo đặc tả.

Kiểm thử bản dịch cần bao gồm: key bắt buộc, dấu tiếng Việt, placeholder `{0}`, `{1}` và loại tham số, fallback không mong muốn, nhãn quá dài gây tràn giao diện, và thông điệp lỗi khi resource thiếu. Chỉ kiểm tra `getString(key) != null` không thể chứng minh bản dịch tiếng Việt thực sự tồn tại.

## 9. Chữ hoa, so sánh, sắp xếp và mã kỹ thuật

Đối với một ID hoặc key chỉ dùng cho logic kỹ thuật, `Locale.ROOT` tạo phép biến đổi nhất quán giữa môi trường:

```java
String key = "ADMIN".toLowerCase(Locale.ROOT); // "admin"
```

Với nội dung tiếng Việt dành cho người đọc, hãy xác định yêu cầu so sánh cụ thể: phân biệt hoa/thường, phân biệt dấu, chuẩn hóa NFC, hay hỗ trợ tìm kiếm bỏ dấu. `String.compareTo()` dựa trên thứ tự mã không đồng nghĩa sắp xếp tiếng Việt; `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` có thể dùng khi nghiệp vụ cần thứ tự ngôn ngữ. Hãy test tính chất và quy tắc sản phẩm, tránh đóng băng danh sách thứ tự collation của một JDK nếu không có yêu cầu snapshot được kiểm soát.

Cũng không nên gọi `Locale.setDefault(...)` trong từng test JUnit chạy song song để mô phỏng người dùng. `setDefault` làm đổi trạng thái cho cả JVM. Truyền Locale qua dependency hoặc hàm; nếu thực sự cần kiểm thử API phụ thuộc mặc định, cách ly bằng tiến trình JVM khác hoặc môi trường test tuần tự được quản lý rõ ràng.

## 10. Ma trận kiểm thử trên CI

| Nhóm kiểm tra | Cấu hình đề nghị | Tiêu chí đạt |
| --- | --- | --- |
| Tiếng Việt | `vi-VN`, UTF-8, `Asia/Ho_Chi_Minh` | Dữ liệu giữ nguyên dấu; hiển thị theo Locale được truyền |
| Locale khác | `en-US`, có thể thêm `fr-FR` | Không rò rỉ default FORMAT Locale vào kết quả cho `vi-VN` |
| Múi giờ | `UTC` và `Asia/Ho_Chi_Minh` | Logic dựa trên thời điểm/ngày có test ranh giới chính xác |
| Unicode | Ký tự dựng sẵn, dấu tổ hợp, `đ/Đ`, tên có nhiều dấu | So sánh/lưu/truy xuất tuân theo quy tắc đã đặc tả |
| Resource | Bản dịch Việt đầy đủ và tình huống cố ý thiếu key/bundle | Phát hiện fallback sai, thông điệp và tham số không khớp |
| Nâng JDK | Runtime đang hỗ trợ và phiên bản dự kiến nâng cấp | Logic không đổi; thay đổi CLDR được review ở tầng hiển thị |

Khi test CI lỗi, nên log thông tin môi trường **để chẩn đoán**:

```java
System.out.println("java.version=" + System.getProperty("java.version"));
System.out.println("default FORMAT locale="
        + Locale.getDefault(Locale.Category.FORMAT));
System.out.println("system zone=" + java.time.ZoneId.systemDefault());
System.out.println("default charset=" + java.nio.charset.Charset.defaultCharset());
```

Không dùng các dòng này làm expected result hay cấu hình nghiệp vụ. Nếu bắt buộc dùng snapshot pixel/text chính xác cho UI, ghi rõ JDK, Locale và phiên bản dữ liệu bản địa hóa. Khi nâng JDK, phân biệt thay đổi chấp nhận được của cách trình bày với regression thật sự của sản phẩm.

Một phép kiểm tra hữu ích là chạy cùng bộ test với JVM mặc định tiếng Việt rồi tiếng Anh, đồng thời thay vùng thời gian. Nếu phép test được thiết kế chỉ phụ thuộc Locale/Zone đã truyền mà lại thay kết quả theo cài đặt máy, hãy tìm lời gọi API không có Locale/Zone tường minh hoặc dùng charset mặc định.

## 11. Phản mẫu và cách thay thế

| Phản mẫu | Vấn đề | Cách thay thế |
| --- | --- | --- |
| `NumberFormat.getInstance()` rồi so cứng dấu phân cách | Dùng default FORMAT Locale; dữ liệu CLDR có thể đổi | `getNumberInstance(locale)`, kiểm tra ngữ nghĩa |
| `String.format("%,.2f", n)` để gửi API | Đầu ra có thể phụ thuộc Locale máy | Dùng kiểu số/API schema hoặc `String.format(Locale.ROOT, ...)` cho format kỹ thuật |
| `NumberFormat.parse(...)` mà không kiểm tra còn ký tự thừa | Parser có thể chấp nhận tiền tố rồi bỏ phần cuối | Dùng `ParsePosition` và kiểm tra đã tiêu thụ hết |
| `new Date().toString()` làm kết quả mong đợi | Phụ thuộc timezone/format máy | `Instant`, `ZoneId` tường minh, ISO khi cần |
| `LocalDate.now()` trong logic test | Lệ thuộc đồng hồ thực | `Clock.fixed(...)`/inject `Clock` |
| `String.toLowerCase()` cho key hệ thống | Có thể phụ thuộc Locale mặc định | `toLowerCase(Locale.ROOT)` |
| Chỉ assert `getString(...)` không null | Fallback có thể che bản dịch Việt bị thiếu | Kiểm tra locale được chọn, key và text ứng dụng sở hữu |
| Bỏ dấu hoặc thay `,`/`.` hàng loạt | Mất nghĩa tên/số; sai ở locale khác | Quy định normalization/parser theo Locale |
| Dùng `Locale.setDefault(...)` trong test song song | Tạo race condition trên trạng thái JVM | Truyền Locale, hoặc cô lập JVM |
| Dùng chung một `NumberFormat` mutable không đồng bộ | Formatter có trạng thái và không an toàn cho mọi tình huống concurrent | Tạo formatter cục bộ hoặc quản lý truy cập có chủ đích |

## 12. Checklist hoàn thành một chức năng tiếng Việt

- [ ] Có ca UTF-8 qua các ranh giới file/HTTP/DB liên quan; dấu tiếng Việt được bảo toàn.
- [ ] Có ca Unicode NFC/NFD; chính sách giữ nguyên hay chuẩn hóa text được nêu rõ.
- [ ] `Locale` được truyền tường minh khi format/parse số, tiền, ngày và message.
- [ ] `ZoneId`, `Instant`, `LocalDate`, `Clock` được dùng đúng nhiệm vụ; không phụ thuộc đồng hồ hoặc timezone máy.
- [ ] Số/tiền giữ kiểu và precision nghiệp vụ; format cho UI chỉ là bước trình bày.
- [ ] Assertions biết phân biệt ngữ nghĩa với chuỗi UI; không tùy tiện chốt biểu diễn CLDR ở mọi JDK.
- [ ] Resource bundle tiếng Việt có đủ key, tham số, dấu và không fallback âm thầm.
- [ ] Test chạy ổn với hai cấu hình default Locale/Zone khác nhau.
- [ ] Nếu có snapshot UI chính xác, môi trường và quy trình review khi đổi JDK/CLDR được xác định.

## Tài liệu chính thức để đào sâu

- [JDK 9 Migration Guide – Use CLDR Locale Data by Default](https://docs.oracle.com/javase/9/migrate/)
- [JDK 9 Internationalization Enhancements – UTF-8 Properties Files](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-9.htm)
- [Locale (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [NumberFormat (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [DateTimeFormatter (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Normalizer (Java SE)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)

**Ghi nhớ:** `vi-VN` là một yêu cầu bản địa hóa đầu ra, không phải định dạng lưu trữ. Kiểm thử tốt giữ dữ liệu nghiệp vụ chính xác và văn bản tiếng Việt của ứng dụng đúng; các chi tiết format do JDK cung cấp được xác nhận theo mức cam kết thực sự của sản phẩm.
