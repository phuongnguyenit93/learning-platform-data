# Quan hệ giữa ngôn ngữ, khu vực, locale và tài nguyên dịch trong Java

## 1. Vì sao cần phân biệt bốn khái niệm?

Một ứng dụng phục vụ người dùng ở nhiều nơi phải quyết định **ngôn ngữ hiển thị**, **quy ước trình bày theo khu vực**, **bộ quy tắc văn hóa áp dụng** và **nội dung dịch tương ứng**. Chúng liên quan nhau nhưng không đồng nghĩa.

- **Ngôn ngữ (language)**: người dùng đọc hoặc nói bằng ngôn ngữ nào, chẳng hạn tiếng Việt (`vi`), tiếng Anh (`en`), tiếng Pháp (`fr`).
- **Khu vực (region)**: quốc gia/vùng lãnh thổ liên quan đến quy ước địa phương, chẳng hạn Việt Nam (`VN`), Hoa Kỳ (`US`), Canada (`CA`). Cùng một khu vực có thể dùng nhiều ngôn ngữ; một ngôn ngữ có thể dùng ở nhiều khu vực.
- **Locale**: định danh tập hợp sở thích ngôn ngữ và quy ước địa phương, có thể gồm language, script, region, variant và các Unicode extension. Trong Java, `java.util.Locale` biểu diễn định danh này.
- **Tài nguyên dịch (translation resources)**: các chuỗi giao diện hoặc nội dung đã địa phương hóa, thường lưu theo khóa và theo locale trong tệp `.properties` hay nguồn khác. Trong Java, `ResourceBundle` là cơ chế chuẩn để chọn và đọc tài nguyên kiểu này.

Ví dụ: `en-US` và `en-GB` cùng dùng tiếng Anh nhưng có thể khác cách viết từ, ngày tháng và đơn vị. `fr-CA` là tiếng Pháp dùng tại Canada; `en-CA` là tiếng Anh dùng tại Canada. Vì vậy, **không suy ra ngôn ngữ chỉ từ quốc gia**, cũng không suy ra quốc gia chỉ từ ngôn ngữ.

**Internationalization (i18n)** là thiết kế ứng dụng để có thể thích ứng với nhiều locale; **localization (l10n)** là cung cấp dữ liệu, bản dịch và quy tắc thể hiện phù hợp một locale cụ thể. Dịch câu chữ chỉ là một phần của localization.

## 2. Mô hình quan hệ

```text
Người dùng / yêu cầu
    │ ngôn ngữ ưa thích: vi-VN, en-US, ...
    ▼
Locale đã chọn (ví dụ vi-VN)
    ├── language = vi  → ưu tiên câu chữ tiếng Việt
    ├── region   = VN  → quy ước khu vực phù hợp
    ├── script / extension (nếu có)
    │
    ├── ResourceBundle → tra khóa → chuỗi hiển thị
    ├── NumberFormat   → định dạng số, tiền tệ, phần trăm
    └── DateTimeFormatter → định dạng ngày giờ theo ngôn ngữ/quy ước
                                    │
Múi giờ (ZoneId) ────────────────────┘ dữ liệu độc lập, chọn riêng
```

Locale giúp ứng dụng **chọn quy tắc**, nhưng không tự dịch một văn bản bất kỳ. Nếu không có bản dịch, gọi `Locale.forLanguageTag("vi-VN")` cũng không biến chuỗi tiếng Anh thành tiếng Việt. Tương tự, locale **không tự xác định múi giờ, tỷ giá tiền tệ, địa chỉ giao hàng hay luật thuế**.

| Giá trị | Thành phần | Diễn giải |
| --- | --- | --- |
| `vi` | language | Tiếng Việt, chưa nêu khu vực |
| `vi-VN` | language + region | Tiếng Việt tại Việt Nam |
| `en-US` | language + region | Tiếng Anh tại Hoa Kỳ |
| `en-GB` | language + region | Tiếng Anh tại Vương quốc Anh |
| `fr-CA` | language + region | Tiếng Pháp tại Canada |
| `zh-Hant-TW` | language + script + region | Tiếng Trung, chữ Phồn thể, khu vực Đài Loan |

BCP 47 biểu diễn language tag bằng dấu gạch nối (`-`). Tên tệp `ResourceBundle` kiểu `.properties` thường dùng phần hậu tố dấu gạch dưới (`_`), chẳng hạn `Messages_vi_VN.properties`. Đây là **hai cách biểu diễn cho hai mục đích khác nhau**, không nên truyền thẳng tên tệp làm language tag.

## 3. `Locale` trong Java

`java.util.Locale` là đối tượng mô tả locale, không chứa bản dịch. Java 17 có thể tạo locale từ language tag:

```java
import java.util.Locale;

public class LocaleBasics {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("zh-Hant-TW");

        System.out.println(locale.getLanguage());
        System.out.println(locale.getScript());
        System.out.println(locale.getCountry());
        System.out.println(locale.toLanguageTag());
    }
}
```

Lưu trong `LocaleBasics.java` rồi chạy:

```bash
javac -encoding UTF-8 LocaleBasics.java
java LocaleBasics
```

Kết quả:

```text
zh
Hant
TW
zh-Hant-TW
```

Các điểm cần nhớ:

1. `getLanguage()` trả mã ngôn ngữ; `getCountry()` trả mã khu vực, dù tên API dùng từ “country”; `getScript()` trả mã hệ chữ nếu có.
2. `toLanguageTag()` là cách xuất định danh theo chuẩn BCP 47. Tag không chỉ có hai thành phần language/region; script và extension có thể quan trọng cho chọn dữ liệu.
3. `Locale.forLanguageTag(...)` hữu ích khi nhận một tag theo BCP 47. Nếu cần **kiểm tra nghiêm ngặt** tag nhập vào, dùng `new Locale.Builder().setLanguageTag(tag).build()` và xử lý `IllformedLocaleException`; đừng mặc định rằng mọi đầu vào không hợp lệ sẽ khiến `forLanguageTag` ném lỗi.
4. `Locale.getDefault()` lấy locale mặc định của tiến trình/JVM, chịu ảnh hưởng cấu hình môi trường. Gọi `Locale.setDefault(...)` thay đổi mặc định toàn tiến trình, dễ tác động các tác vụ đồng thời; với dịch vụ nhiều người dùng nên **truyền locale tường minh theo từng yêu cầu**.
5. `Locale.ROOT` là locale trung tính, hữu ích trong thao tác cần quy tắc nhất quán, nhưng không đại diện cho một ngôn ngữ hiển thị cụ thể. Mã định danh, giao thức và dữ liệu lưu trữ thường cần quy tắc ổn định riêng thay vì dùng locale giao diện.

## 4. Tài nguyên dịch và cách `ResourceBundle` chọn chúng

Một cách tổ chức đơn giản là giữ **cùng bộ khóa** và tách giá trị theo bản dịch:

```text
src-or-working-directory/
├── App.java
├── Messages.properties
├── Messages_vi.properties
└── Messages_vi_VN.properties
```

`Messages.properties` là tập giá trị gốc (base bundle); `Messages_vi.properties` là bản tiếng Việt chung; `Messages_vi_VN.properties` là phần riêng cho Việt Nam. Với locale `vi-VN`, thứ tự ứng viên đơn giản điển hình là **`Messages_vi_VN` → `Messages_vi` → `Messages`**. Một khóa không có ở bản cụ thể có thể được kế thừa từ bản ít cụ thể hơn.

Ví dụ với các tệp có nội dung như sau.

**`Messages.properties`**

```properties
greeting=Hello, {0}!
action.save=Save
currency.label=Price
```

**`Messages_vi.properties`**

```properties
greeting=Xin chào, {0}!
action.save=Lưu
```

**`Messages_vi_VN.properties`**

```properties
currency.label=Giá
```

**`App.java`**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class App {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");

        // Không chuyển sang locale mặc định của JVM nếu không có bundle yêu cầu.
        ResourceBundle.Control noDefaultFallback =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", locale, noDefaultFallback);

        String pattern = bundle.getString("greeting");
        String greeting =
                new MessageFormat(pattern, locale).format(new Object[]{"Lan"});

        System.out.println("Locale requested: " + locale.toLanguageTag());
        System.out.println("Bundle selected: " + bundle.getLocale().toLanguageTag());
        System.out.println("Greeting: " + greeting);
        System.out.println("Action: " + bundle.getString("action.save"));
        System.out.println("Currency label: " + bundle.getString("currency.label"));
    }
}
```

Đặt cả bốn tệp cùng thư mục và dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 App.java
java -cp . App
```

Kết quả khi terminal hiển thị UTF-8:

```text
Locale requested: vi-VN
Bundle selected: vi-VN
Greeting: Xin chào, Lan!
Action: Lưu
Currency label: Giá
```

Điều gì đã xảy ra?

- `ResourceBundle.getBundle("Messages", ...)` tìm các bundle theo locale, classpath và quy tắc tra cứu. Ví dụ dùng loại `.properties` và loại bỏ bước fallback sang **default locale của JVM** để hành vi dễ giải thích và ổn định.
- Bundle cụ thể được tìm thấy là `Messages_vi_VN.properties`, vì thế `bundle.getLocale()` cho biết `vi-VN`. Phương thức này phản ánh **bundle được chọn**, có thể khác locale đã yêu cầu nếu phải fallback.
- Khóa `currency.label` nằm ngay trong bundle `vi_VN`; hai khóa còn lại được kế thừa từ bundle `vi`. Nếu một khóa không có ở bất kỳ bundle nào trong chuỗi tìm kiếm, `getString` ném `MissingResourceException`.
- `MessageFormat` thay `{0}` bằng tên người dùng và nhận locale tường minh. Dữ liệu đầu vào được truyền riêng, tránh tự nối hoặc chỉnh sửa mẫu thông báo tùy tiện.
- Từ Java 9, `PropertyResourceBundle` mặc định hỗ trợ đọc tệp properties bằng UTF-8 (có cơ chế tương thích cho dữ liệu Latin-1); lưu tệp nguồn UTF-8 và kiểm tra encoding của công cụ build/terminal.

**Lưu ý về fallback thực tế:** Với cách gọi `ResourceBundle.getBundle(baseName, locale)` mặc định, Java còn có thể thử locale mặc định của JVM khi không tìm thấy bundle thích hợp cho locale yêu cầu, rồi mới đến base bundle theo thuật toán của API. Do đó, “luôn tra `vi_VN → vi → base` và dừng” chỉ là mô hình nhập môn; nó không mô tả hết hành vi mặc định của mọi overload. Ví dụ trên chủ động dùng `getNoFallbackControl` để tránh bước phụ thuộc default locale. Trường hợp có script, variant hoặc extension có quy tắc tạo candidate khác, nên kiểm thử với locale thực tế cần hỗ trợ.

Đừng nhầm **fallback của bundle** (chọn tệp) với **fallback của khóa** (kế thừa giá trị từ bundle cha). Một bundle `vi_VN` có thể được chọn thành công mà nhiều khóa vẫn nằm ở `vi` hoặc base.

## 5. Locale tác động đến định dạng dữ liệu, không chỉ bản dịch

Một câu giao diện cần bản dịch, nhưng dữ liệu như số, tiền và ngày thường cần **formatter**. Ví dụ sau chạy được với Java 17:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormattingExample {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");
        LocalDate date = LocalDate.of(2026, 10, 28);

        for (String tag : new String[]{"vi-VN", "en-US"}) {
            Locale locale = Locale.forLanguageTag(tag);
            String number = NumberFormat.getNumberInstance(locale).format(amount);
            String dateText = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale)
                    .format(date);

            System.out.println(tag + " | " + number + " | " + dateText);
        }
    }
}
```

Chạy `javac -encoding UTF-8 FormattingExample.java` rồi `java FormattingExample`. Mỗi dòng có dạng `locale | số đã định dạng | ngày đã định dạng`. Dấu phân nhóm, dấu thập phân, tên tháng và thứ tự thành phần ngày có thể khác giữa `vi-VN` và `en-US`. **Không nên chốt một chuỗi stdout cố định cho ví dụ này** vì dữ liệu locale (CLDR) và phiên bản JDK có thể thay đổi cách hiển thị.

Phân biệt thêm những quyết định thường bị gộp nhầm:

| Nhu cầu | Dùng gì? | Không nên suy diễn |
| --- | --- | --- |
| Văn bản giao diện | `ResourceBundle` hoặc hệ quản lý bản dịch | Locale tự sinh bản dịch |
| Số và phần trăm | `NumberFormat` với locale | Nối chuỗi dấu phẩy/dấu chấm thủ công |
| Tiền tệ | `NumberFormat.getCurrencyInstance(locale)` và `Currency` nếu biết loại tiền | Quốc gia của locale luôn là đồng tiền của giao dịch |
| Ngày/giờ | `DateTimeFormatter.withLocale(locale)` | Locale tự cung cấp múi giờ |
| Thời điểm hiển thị | `Instant`/`ZonedDateTime` và `ZoneId` tường minh | `vi-VN` bắt buộc tương đương một múi giờ duy nhất |
| Sắp xếp văn bản theo ngôn ngữ | `Collator` với locale | So chuỗi theo Unicode code point sẽ giống thứ tự từ điển |

Ví dụ, một giao dịch bằng USD có thể hiển thị cho người dùng dùng tiếng Việt; không tự đổi sang VND chỉ vì locale `vi-VN`. Giá trị tiền, đơn vị tiền, ngôn ngữ của nhãn và định dạng hiển thị là các quyết định liên quan nhưng riêng biệt.

## 6. Chọn locale ở ranh giới ứng dụng

Ứng dụng cần chính sách chọn locale rõ ràng, chẳng hạn:

1. Nếu người dùng đã lưu lựa chọn ngôn ngữ, ưu tiên lựa chọn đó.
2. Nếu chưa có, có thể xem danh sách ngôn ngữ trình duyệt/yêu cầu (ví dụ `Accept-Language`) và so với **các locale thực sự được hỗ trợ**.
3. Nếu không khớp, dùng locale mặc định được sản phẩm xác định rõ; không vô tình dùng `Locale.getDefault()` của máy chủ.
4. Truyền locale đã chọn qua lớp giao diện, tải resource và formatter trong phạm vi yêu cầu; ghi log hoặc test khi cần biết bundle nào đã được chọn.

Ví dụ sản phẩm chỉ có bản dịch `vi` và `en`, người dùng gửi `fr-CA`. Một chiến lược hợp lệ là dùng `en` làm **product fallback**. Đó là quyết định sản phẩm, không phải điều gì BCP 47 hay `Locale` có thể tự suy ra. Nếu người dùng gửi `vi-VN` và sản phẩm chỉ có `vi`, có thể giữ ngôn ngữ hiển thị tiếng Việt và dùng quy ước vùng Việt Nam, miễn là chính sách và định dạng thực sự đáp ứng như vậy.

Header `Accept-Language` có thể chứa nhiều mục và trọng số, ví dụ `vi-VN,vi;q=0.9,en-US;q=0.7`. Đây **không phải một language tag duy nhất** để truyền nguyên chuỗi vào `Locale.forLanguageTag`. Trong Java có `Locale.LanguageRange.parse(...)` và các hàm `Locale.lookup(...)`/`Locale.filter(...)` phục vụ khớp sở thích theo danh sách locale hỗ trợ; hoặc dùng bộ phân giải locale có sẵn của framework.

## 7. Thiết kế bộ dịch dễ bảo trì

- Dùng khóa có ý nghĩa (`checkout.submit`, `error.validation.required`), thống nhất trong mọi bundle; tránh khóa phụ thuộc văn bản tiếng Anh. Giữ một base bundle hoặc chính sách fallback rõ ràng.
- Tách **message pattern** và tham số: `"Xin chào, {0}!"`; không nối các mảnh câu rồi hy vọng thứ tự từ giống nhau giữa mọi ngôn ngữ. Cân nhắc các cách xử lý số nhiều, giống ngữ pháp, thứ tự từ phù hợp ngôn ngữ khi nội dung phức tạp.
- Giữ mã hóa thống nhất UTF-8; xử lý apostrophe và dấu ngoặc nhọn cẩn thận với cú pháp `MessageFormat`. Trong pattern `MessageFormat`, dấu nháy đơn có ý nghĩa đặc biệt: muốn hiện một apostrophe, thường cần viết kép `''`.
- Kiểm tra **đủ khóa**, chênh lệch placeholder giữa bản dịch, chuỗi dài/tràn giao diện, dấu tiếng Việt, định dạng RTL với ngôn ngữ viết từ phải sang trái và khả năng truy cập.
- Không đưa toàn bộ câu dịch hoặc logic chọn ngôn ngữ vào `if/else` rải rác. Tập trung ở tầng tài nguyên và bộ phân giải locale.
- Kiểm thử ít nhất một locale theo ngôn ngữ, một locale có khu vực cụ thể, trường hợp thiếu key/bundle và trường hợp thay đổi default locale JVM để phát hiện fallback ngoài ý muốn.
- Với yêu cầu tải lại bản dịch trong lúc chạy, hiểu rằng `ResourceBundle` có cache; có thể cần chính sách reload/`ResourceBundle.clearCache(...)` hoặc giải pháp quản trị dịch riêng, tùy kiến trúc.

## 8. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Lấy `getCountry()` để quyết định ngôn ngữ | Một quốc gia có thể có nhiều ngôn ngữ | Dùng ngôn ngữ người dùng chọn hoặc negotiation theo chính sách |
| Dùng `en` và mặc định tương đương `en-US` | Ngôn ngữ không xác định mọi quy ước vùng | Lưu/nhận region khi thực sự cần |
| Nghĩ `Locale` tự dịch câu | Locale là định danh, không phải từ điển | Cung cấp bundle hoặc hệ thống bản dịch |
| Mặc định bundle luôn khớp chính xác tag yêu cầu | Có chuỗi ứng viên và fallback | Kiểm tra `bundle.getLocale()` và test thiếu bundle |
| Dùng `Locale.getDefault()` trong xử lý nhiều người dùng | Default thuộc JVM, không thuộc từng request | Truyền locale tường minh |
| Ghép số/ngày bằng tay | Quy ước khác theo locale | Dùng formatter chuẩn |
| Đồng nhất locale với múi giờ/loại tiền | Các thuộc tính có quy tắc lựa chọn riêng | Chọn `ZoneId`, `Currency` theo dữ liệu nghiệp vụ |
| Đặt key chỉ ở bundle vùng, không có fallback cần thiết | Locale khác thiếu key sẽ lỗi hoặc lộ chuỗi không đúng | Xây bộ khóa nền và kiểm thử độ phủ |
| Dịch bằng ghép các mảnh câu | Ngữ pháp và trật tự từ thay đổi | Dùng pattern có tham số và hỗ trợ ngữ pháp khi cần |

## 9. Tự kiểm tra kiến thức

**Tình huống A:** Người dùng tại Canada chọn tiếng Pháp, nhưng máy chủ đặt default locale `en-US`. Nên dùng locale nào để tìm nhãn giao diện? → Ưu tiên `fr-CA` (hoặc `fr` nếu chính sách/dữ liệu hỗ trợ), truyền tường minh vào bộ tải tài nguyên. Không dựa vào default locale của máy chủ.

**Tình huống B:** Có `Messages.properties`, `Messages_vi.properties` nhưng không có `Messages_vi_VN.properties`. Với yêu cầu `vi-VN`, nội dung tiếng Việt có thể hiển thị không? → Có, bundle tiếng Việt `vi` là ứng viên phù hợp. Chính sách fallback sang default locale JVM vẫn phải được kiểm soát riêng.

**Tình huống C:** Một người dùng nói tiếng Anh thanh toán 15 USD khi đang ở Việt Nam. Phải đổi bản dịch, múi giờ và tiền tệ thành giá trị Việt Nam cùng lúc? → Không. Ngôn ngữ giao diện, khu vực định dạng, múi giờ và đồng tiền giao dịch cần lấy từ các nguồn/chính sách thích hợp cho từng dữ liệu.

**Thực hành:** Thêm `Messages_en.properties` với cùng ba khóa trong ví dụ, chạy ứng dụng với `Locale.forLanguageTag("en-GB")`, kiểm tra `bundle.getLocale()`, sau đó xóa thử một khóa ở `Messages_en.properties` để quan sát cơ chế kế thừa từ base. Đối chiếu kết quả với dự đoán trước khi chạy.

**Điểm cốt lõi:** Language trả lời “đọc bằng tiếng gì?”, region giúp xác định “quy ước địa phương nào?”, `Locale` là định danh/chính sách chọn cách trình bày, còn translation resources cung cấp “chuỗi nào đã được dịch”. Thiết kế Java đúng kết hợp bốn khía cạnh này với fallback rõ ràng và kiểm thử theo locale được hỗ trợ.
