# Phân biệt cùng một ngôn ngữ ở các khu vực khác nhau với Java `Locale`

Một ngôn ngữ có thể được dùng tại nhiều quốc gia hoặc vùng lãnh thổ nhưng cách **viết, chọn từ, định dạng số, ngày, tiền tệ và quy ước trình bày** không hoàn toàn giống nhau. Tiếng Anh ở Hoa Kỳ và Vương quốc Anh đều là tiếng Anh; tiếng Bồ Đào Nha ở Brazil và Bồ Đào Nha cùng có mã ngôn ngữ `pt`. Tuy nhiên, ứng dụng không thể chỉ nhìn vào tên ngôn ngữ rồi mặc định mọi người dùng sẽ nhận cùng một cách hiển thị.

Trong Java, `java.util.Locale` là mô hình mô tả **lựa chọn ngôn ngữ/vùng/quy ước địa phương**. Bài này tập trung vào cách phân biệt **cùng ngôn ngữ ở các khu vực khác nhau** và chọn đúng `Locale` khi xử lý giao diện, tài nguyên bản địa hóa và định dạng dữ liệu.

## 1. Phân biệt ngôn ngữ, vùng và Locale

- **Ngôn ngữ (language):** chỉ ngôn ngữ, ví dụ `en` (tiếng Anh), `pt` (tiếng Bồ Đào Nha), `es` (tiếng Tây Ban Nha), `fr` (tiếng Pháp).
- **Vùng (region):** chỉ quốc gia hoặc vùng lãnh thổ, ví dụ `US`, `GB`, `BR`, `PT`, `MX`, `CA`. Một vùng có thể sử dụng nhiều ngôn ngữ; một ngôn ngữ có thể xuất hiện ở nhiều vùng.
- **Hệ chữ viết (script):** khi cần, phân biệt cách viết như `Hans` (chữ Hán giản thể), `Hant` (chữ Hán phồn thể), `Latn` (chữ Latin), `Cyrl` (chữ Cyrillic).
- **Locale:** kết hợp các thành phần cần thiết để mô tả quy ước mong muốn. `Locale` **không** tự chứa bản dịch, múi giờ hoặc danh tính/quốc tịch của người dùng.

| Thẻ Locale theo BCP 47 | Ngôn ngữ | Vùng / script | Ý nghĩa trong giao diện |
| --- | --- | --- | --- |
| `en-US` | English | Hoa Kỳ | Cách dùng tiếng Anh và quy ước thường gặp ở Hoa Kỳ |
| `en-GB` | English | Vương quốc Anh | Cách dùng tiếng Anh và quy ước thường gặp ở Anh |
| `pt-BR` / `pt-PT` | Português | Brazil / Bồ Đào Nha | Từ vựng, lối diễn đạt và định dạng theo khu vực |
| `es-MX` / `es-ES` | Español | Mexico / Tây Ban Nha | Một ngôn ngữ, có khác biệt về cách dùng và quy ước |
| `fr-CA` / `fr-FR` | Français | Canada / Pháp | Khác biệt vùng trong tài nguyên và định dạng |
| `zh-Hans-CN` / `zh-Hant-TW` | 中文 | Script giản thể/phồn thể; Trung Quốc/Đài Loan | Cần nhận diện cả script, không chỉ `zh` |
| `sr-Latn-RS` / `sr-Cyrl-RS` | Serbian | Cùng vùng Serbia, khác script | Vùng giống nhau vẫn có thể cần hai tài nguyên chữ viết |

**Trọng tâm:** `en-US` và `en-GB` có `getLanguage()` giống nhau (`en`), nhưng `getCountry()` khác nhau (`US` và `GB`), vì thế hai đối tượng `Locale` không bằng nhau. Ngược lại, `en` chỉ xác định ngôn ngữ, **chưa chỉ định vùng**. Không nên suy đoán rằng nó luôn là `en-US`.

Các thẻ trên sử dụng **BCP 47** (`language[-Script][-REGION]...`); dấu nối `-` là cú pháp chuẩn. Chữ hoa/thường được chuẩn hóa khi biểu diễn, ví dụ `Locale.forLanguageTag("en-gb").toLanguageTag()` trả `en-GB`. Dấu gạch dưới trong tên file `messages_en_GB.properties` thuộc **quy tắc tên tài nguyên Java**, không phải cú pháp thẻ BCP 47 truyền vào `forLanguageTag`.

## 2. Tạo và so sánh Locale đúng cách

Dùng `Locale.forLanguageTag(...)` cho đầu vào dạng BCP 47. Khi cần tự xây dựng từng thành phần, dùng `Locale.Builder`. `Locale.US`, `Locale.UK`, `Locale.FRANCE`, `Locale.CANADA_FRENCH` là một số hằng được cung cấp sẵn; không phải tổ hợp nào cũng có hằng tương ứng.

**Ví dụ chạy độc lập — Java 17+:** lưu vào `RegionalLocaleDemo.java`.

```java
import java.util.Locale;

public class RegionalLocaleDemo {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale uk = Locale.forLanguageTag("en-GB");
        Locale traditionalChinese = new Locale.Builder()
                .setLanguage("zh")
                .setScript("Hant")
                .setRegion("TW")
                .build();

        System.out.println("Same language: "
                + us.getLanguage().equals(uk.getLanguage()));
        System.out.println("Same Locale: " + us.equals(uk));
        System.out.println(us.toLanguageTag() + " -> "
                + us.getLanguage() + "/" + us.getCountry());
        System.out.println(uk.toLanguageTag() + " -> "
                + uk.getLanguage() + "/" + uk.getCountry());
        System.out.println(traditionalChinese.toLanguageTag() + " -> "
                + traditionalChinese.getLanguage() + "/"
                + traditionalChinese.getScript() + "/"
                + traditionalChinese.getCountry());

        Locale tr = Locale.forLanguageTag("tr-TR");
        System.out.println("ROOT uppercase: "
                + "file".toUpperCase(Locale.ROOT));
        System.out.println("Turkish uppercase: "
                + "file".toUpperCase(tr));
    }
}
```

Biên dịch và chạy:

```bash
javac RegionalLocaleDemo.java
java RegionalLocaleDemo
```

Kết quả (các dòng này dựa trên mã thẻ và chuyển chữ hoa xác định, không phụ thuộc quy tắc định dạng số/ngày của hệ thống):

```text
Same language: true
Same Locale: false
en-US -> en/US
en-GB -> en/GB
zh-Hant-TW -> zh/Hant/TW
ROOT uppercase: FILE
Turkish uppercase: FİLE
```

Dòng cuối cho thấy locale còn ảnh hưởng đến thao tác văn bản nhạy cảm với ngôn ngữ: trong tiếng Thổ Nhĩ Kỳ, chữ `i` viết hoa thành `İ` (chữ I có dấu chấm). Với mã nhận dạng nội bộ cần cách chuyển chữ hoa không phụ thuộc vùng, dùng `Locale.ROOT`; với **văn bản hiển thị cho người dùng**, dùng locale phù hợp khi API có hỗ trợ.

**Khi so khớp:**

- So sánh `getLanguage()` khi chỉ muốn biết có cùng **ngôn ngữ** hay không; kết quả `true` không có nghĩa là có thể dùng chung mọi tài nguyên và định dạng.
- So sánh `equals()` hoặc thẻ chuẩn hóa `toLanguageTag()` khi cần phân biệt đầy đủ những thành phần được cấu hình trong `Locale`. `Locale` còn có thể có variant và Unicode extensions.
- Đừng sử dụng `getDisplayName()` làm khóa: đây là **tên để hiển thị** và kết quả phụ thuộc locale hiển thị. Dùng thẻ/cấu trúc `Locale` cho khóa.
- Đầu vào không đúng cú pháp có thể bị `forLanguageTag` diễn giải lỏng và bỏ một số phần không hợp lệ. Nếu cần từ chối thẻ sai cú pháp, dùng `new Locale.Builder().setLanguageTag(input).build()` và xử lý `IllformedLocaleException`; việc **hợp lệ về cú pháp** chưa chứng minh locale đó được ứng dụng hỗ trợ.

## 3. Vì sao cùng ngôn ngữ vẫn có kết quả khác nhau?

| Khía cạnh | Ví dụ khác biệt giữa các khu vực | API/liên quan trong Java |
| --- | --- | --- |
| Chính tả, từ vựng | `color`/`colour`, `apartment`/`flat` là những ví dụ tiếng Anh có sắc thái vùng | Bản dịch và `ResourceBundle` do dự án cung cấp |
| Định dạng ngày | Thói quen tháng/ngày/năm hoặc ngày/tháng/năm khác nhau | `DateTimeFormatter.ofLocalizedDate` |
| Phân cách và định dạng số | Dấu phân cách hàng nghìn, phần thập phân và cách nhóm có thể khác | `NumberFormat.getNumberInstance(locale)` |
| Đơn vị tiền, ký hiệu và vị trí | `en-US` thường liên hệ USD; `en-GB` thường liên hệ GBP | `NumberFormat.getCurrencyInstance(locale)`, `Currency` |
| Quy tắc sắp xếp | So sánh chuỗi theo cách dùng ngôn ngữ, dấu và chữ cái | `Collator.getInstance(locale)` |
| Hệ chữ viết | `zh-Hans` và `zh-Hant`, `sr-Latn` và `sr-Cyrl` | `getScript()`, tài nguyên đúng script |
| Thông điệp giao diện | Lời gọi, từ địa phương, chính sách trình bày | `ResourceBundle` hoặc hệ thống thông điệp của ứng dụng |

**Cần phân biệt trách nhiệm:** API định dạng của JDK áp dụng dữ liệu quy ước địa phương của runtime; nó **không tự dịch** các câu giao diện hay bảo đảm mọi khác biệt từ vựng. Nội dung dịch phải được biên soạn, kiểm tra và duy trì như tài nguyên riêng.

### Ví dụ định dạng cho hai khu vực dùng tiếng Anh

Lưu vào `LocalizedFormatDemo.java`:

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedFormatDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 12, 5);
        double amount = 12345.67;

        for (String tag : new String[] {"en-US", "en-GB"}) {
            Locale locale = Locale.forLanguageTag(tag);

            String dateText = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.SHORT)
                    .withLocale(locale)
                    .format(date);
            String numberText = NumberFormat
                    .getNumberInstance(locale)
                    .format(amount);
            String moneyText = NumberFormat
                    .getCurrencyInstance(locale)
                    .format(amount);

            System.out.println(tag + ": date=" + dateText
                    + "; number=" + numberText
                    + "; money=" + moneyText);
        }
    }
}
```

```bash
javac LocalizedFormatDemo.java
java LocalizedFormatDemo
```

Chương trình in ra đúng **hai dòng** bắt đầu bằng `en-US:` và `en-GB:`. Các phần `date=`, `number=` và `money=` được tính tại runtime; dạng chi tiết có thể thay đổi theo phiên bản JDK, dữ liệu CLDR/locale provider và cấu hình môi trường, vì vậy không cố định một stdout theo mọi máy. Điểm cần quan sát: `date` và `amount` **giữ nguyên**, chỉ đối tượng `Locale` thay đổi, từ đó lựa chọn định dạng thay đổi. Định dạng tiền mặc định theo locale thường chọn đồng tiền gắn với vùng tương ứng; **đơn vị tiền thực tế của giao dịch** phải được quản lý độc lập (ví dụ một giao dịch USD của người dùng tại Anh vẫn là USD).

Nếu cần chỉ định tiền tệ thực tế, đặt `Currency` tường minh lên formatter:

```java
Locale uk = Locale.forLanguageTag("en-GB");
NumberFormat prices = NumberFormat.getCurrencyInstance(uk);
prices.setCurrency(java.util.Currency.getInstance("USD"));
String shown = prices.format(1234.56);
```

Đây là **đoạn mã nhúng** trong chương trình Java, không phải file chạy độc lập. Nó kết hợp quy tắc trình bày của `en-GB` với mã tiền tệ `USD`. Lưu ý: thay currency trên formatter không bảo đảm mọi thiết lập chữ số thập phân được tự điều chỉnh cho từng loại tiền; hãy cấu hình/kiểm tra chính sách làm tròn và số chữ số thập phân của giao dịch. Tiền tệ không nên suy ra từ vị trí cư trú nếu hệ thống đã có đơn vị tiền của đơn hàng.

### Locale không phải múi giờ

`Locale.forLanguageTag("en-US")` chỉ định lựa chọn ngôn ngữ/vùng, **không chỉ định `America/New_York`, `America/Los_Angeles` hay múi giờ nào khác**. Khi định dạng thời điểm, quản lý `ZoneId` riêng và chuyển `Instant` sang vùng cần hiển thị. Ngay cả hai người dùng cùng `en-US` vẫn có thể có múi giờ khác nhau; ngược lại hai locale khác nhau vẫn có thể chia sẻ một múi giờ.

### Locale không tự quyết định thứ tự sắp xếp

`String.compareTo` so sánh theo giá trị ký tự UTF-16, không diễn đạt đầy đủ quy tắc xếp thứ tự ngôn ngữ. Khi cần sắp xếp tên hiển thị, xem xét `Collator.getInstance(locale)`, xác định yêu cầu bỏ qua phân biệt dấu/hoa-thường qua mức `strength` phù hợp và kiểm thử dữ liệu thật. Không dùng kết quả collator làm định danh ổn định cho hệ thống.

## 4. Chọn đúng tài nguyên thông điệp cho từng vùng

Ví dụ một ứng dụng có lời chào tiếng Anh được biên tập khác nhau cho Hoa Kỳ và Vương quốc Anh. Dùng `ResourceBundle` để cung cấp bản dịch/từ ngữ theo locale thay vì viết nhiều nhánh `if (country.equals(...))` rải rác trong màn hình.

Các file dưới đây nằm **cùng thư mục khi chạy ví dụ trên classpath**:

```text
messages.properties
messages_en.properties
messages_en_US.properties
messages_en_GB.properties
messages_pt_BR.properties
messages_pt_PT.properties
BundleDemo.java
```

Nội dung từng file:

```properties
# messages.properties
greeting=Hello (fallback)
```

```properties
# messages_en.properties
greeting=Hello (generic English)
```

```properties
# messages_en_US.properties
greeting=Hello from the US
```

```properties
# messages_en_GB.properties
greeting=Hello from the UK
```

```properties
# messages_pt_BR.properties
greeting=Ola do Brasil
```

```properties
# messages_pt_PT.properties
greeting=Ola de Portugal
```

Ở ví dụ dùng ASCII để giảm nhiễu về mã hóa; khi biên soạn sản phẩm thực, dùng văn bản dịch tự nhiên, chuẩn Unicode và kiểm tra quy trình đóng gói.

**Chương trình đầy đủ — `BundleDemo.java`:**

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleDemo {
    public static void main(String[] args) {
        String[] tags = {"en-US", "en-GB", "en-AU", "pt-BR", "pt-PT"};

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle =
                    ResourceBundle.getBundle("messages", locale, control);
            System.out.println(tag + ": " + bundle.getString("greeting"));
        }
    }
}
```

```bash
javac BundleDemo.java
java BundleDemo
```

Kết quả khi tạo đúng sáu file `.properties` ở trên:

```text
en-US: Hello from the US
en-GB: Hello from the UK
en-AU: Hello (generic English)
pt-BR: Ola do Brasil
pt-PT: Ola de Portugal
```

**Giải thích:** `messages_en_US.properties` và `messages_en_GB.properties` cho phép cung cấp câu theo vùng; nếu không có tài nguyên `en_AU`, Java có thể tìm `messages_en.properties` như bản tiếng Anh chung. Các file `pt_BR`/`pt_PT` chứa tài nguyên riêng dù đều là `pt`. Với cách gọi `getNoFallbackControl` ở ví dụ, Java **không chuyển sang locale mặc định của JVM** khi thiếu tài nguyên; nó vẫn có thể truy ngược về bundle cha như `messages_en` hoặc `messages`.

Khi dùng overload mặc định `ResourceBundle.getBundle("messages", locale)`, Java còn có cơ chế **fallback sang JVM default locale** nếu không tìm được bundle phù hợp. Điều này đôi khi khiến người dùng nhận nội dung vùng khác ngoài ý muốn. Thiết kế fallback rõ ràng và kiểm thử cấu hình locale mặc định.

Đối với script, có thể tạo các bundle tương ứng như `messages_zh_Hans_CN.properties` và `messages_zh_Hant_TW.properties`. Việc đặt đúng tên quan trọng, nhưng **thứ tự ứng viên** của `ResourceBundle` có quy tắc riêng cho language/script/region/variant; không suy ra chỉ từ cách cắt chuỗi thẻ. Trong ứng dụng module có cấu hình hoặc dùng framework i18n khác, cần kiểm tra cơ chế resolution tương ứng.

## 5. Lựa chọn locale khi có nhiều vùng được hỗ trợ

Ứng dụng không nên lấy ngôn ngữ rồi **tự chọn bừa** một vùng. Cách thực hành phổ biến:

1. Lưu lựa chọn locale tường minh của người dùng khi họ đã chọn, ví dụ `pt-PT` hay `pt-BR`.
2. Nếu chưa có lựa chọn, nhận ưu tiên ngôn ngữ của client qua nguồn hợp lệ (ví dụ HTTP `Accept-Language`), kiểm tra theo **danh sách locale mà ứng dụng thực sự hỗ trợ**.
3. Chọn locale phù hợp để giải quyết bản dịch; với locale chưa có bản dịch vùng riêng, dùng chính sách fallback được thiết kế sẵn (ví dụ `en-AU` → `en`).
4. Truyền locale đã quyết định vào các formatter, bộ thông điệp và thao tác văn bản liên quan. Giữ timezone, currency và các tùy chọn nghiệp vụ độc lập.
5. Khi không thể ghép được lựa chọn ưu tiên với locale hỗ trợ, dùng một locale mặc định **của ứng dụng**, hiển thị nhất quán và cho phép người dùng đổi nếu cần.

Java có thể phân tích các trọng số `q` trong `Accept-Language` bằng `Locale.LanguageRange` và chọn trong danh sách được hỗ trợ bằng `Locale.lookup`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("pt-BR"));

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse("en-GB,pt-BR;q=0.7");
        Locale chosen = Locale.lookup(preferences, supported);

        System.out.println(chosen.toLanguageTag());
    }
}
```

```bash
javac LocaleNegotiationDemo.java
java LocaleNegotiationDemo
```

Stdout:

```text
en-GB
```

Ví dụ có kết quả cụ thể vì `en-GB` là lựa chọn ưu tiên cao nhất **và** có mặt trong `supported`. Trong thực tế, `Locale.lookup(...)` có thể trả `null` nếu không tìm được locale; luôn xử lý trường hợp này. Đừng lấy kết quả lọc/tra cứu gần đúng làm bằng chứng rằng bundle hoặc định dạng của mọi biến thể ngôn ngữ đều đã được hỗ trợ.

**Đặc biệt:** không viết logic `if (language.equals("en")) locale = Locale.US;` cho mọi người dùng tiếng Anh nếu chính sách sản phẩm chưa xác định. Điều đó làm mất khác biệt `en-GB`, `en-AU` và các lựa chọn khác. Với tiếng Trung hoặc tiếng Serbia, điều kiện trên **cả script** có thể cần thiết để chọn tài nguyên đúng.

## 6. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ so sánh `getLanguage()` rồi coi hai locale như nhau | `en-US` và `en-GB` bị gộp, mất quy tắc vùng | So sánh locale/tag phù hợp với yêu cầu; fallback theo chính sách |
| Mặc định `pt` luôn là `pt-BR` hoặc `pt-PT` | Nội dung và định dạng sai đối tượng người dùng | Lưu đủ thẻ vùng khi đã biết; giữ `pt` là bản chung khi chưa biết |
| Dùng `zh-CN` và `zh-TW` mà bỏ qua script trong hệ có nhiều hệ chữ | Chọn văn bản không đúng kiểu chữ cần hiển thị | Xét `Hans`/`Hant` theo thiết kế hỗ trợ |
| Dùng `new Locale("en", "US")` rồi nối/split tùy ý để lưu BCP 47 | Chuẩn hóa và phần script/extensions dễ bị mất | Dùng `forLanguageTag` / `toLanguageTag` / `Builder` |
| Truyền `"en_US"` vào `forLanguageTag` | `_` không phải dấu phân cách BCP 47 | Dùng `"en-US"`; tên bundle Java mới dùng dấu `_` |
| Dùng `Locale.getDefault()` cho mọi request | Server chạy locale khác người dùng; các request ảnh hưởng nhau | Truyền locale của request/user tường minh; tránh `Locale.setDefault` toàn cục |
| Dùng `String.toUpperCase()` mặc định cho khóa kỹ thuật | Có thể biến đổi khác nhau theo default locale | Dùng `toUpperCase(Locale.ROOT)` cho khóa không phụ thuộc ngôn ngữ |
| Cho rằng `Locale` mang theo múi giờ | Hiển thị giờ sai dù tên locale đúng | Chọn `ZoneId` riêng |
| Cho rằng locale quyết định đồng tiền giao dịch | Có thể trình bày sai loại tiền của giá trị | Quản lý `Currency` theo giao dịch; locale điều khiển cách trình bày |
| Lấy kết quả định dạng mẫu làm hợp đồng cố định mọi JDK | Test thất bại khi dữ liệu CLDR/provider đổi | Kiểm thử ý nghĩa hoặc cố định runtime/dữ liệu khi cần snapshot |
| Tự dịch câu bằng cách chọn locale ở `NumberFormat` | API định dạng không dịch UI text | Cung cấp bundle/nguồn bản dịch thực sự |
| Tin vào `forLanguageTag` để kiểm tra mọi đầu vào hoặc hỗ trợ | Có thể có cú pháp hợp lệ nhưng app không có tài nguyên | Validate cú pháp khi cần và đối chiếu allowlist hỗ trợ |

## 7. Kiểm thử phân biệt vùng

Tạo các ca kiểm thử tối thiểu sau cho hệ thống bản địa hóa:

- **Cùng ngôn ngữ, khác vùng:** `en-US` và `en-GB` phải giữ hai locale khác nhau và chọn đúng bản dịch/định dạng theo vùng.
- **Cùng ngôn ngữ, nhiều biến thể:** `pt-BR` và `pt-PT` có thể cần bundle riêng, không giả định nội dung hoán đổi được.
- **Có script:** `zh-Hans-CN` và `zh-Hant-TW` phải bảo toàn script trong thẻ và chọn đúng tài nguyên nếu được cung cấp.
- **Chưa chỉ rõ vùng:** `en` hoặc `pt` cần một quy tắc mặc định/fallback được công bố, không tự suy ra quốc gia.
- **Vùng chưa có bản dịch riêng:** `en-AU` với bộ bundle ví dụ trả lời chào tiếng Anh chung.
- **Ưu tiên không hỗ trợ:** danh sách `Accept-Language` không khớp `supported` phải được xử lý, tránh `NullPointerException`.
- **Nội dung độc lập môi trường:** so sánh `Locale`, thẻ, bundle và các quan hệ logic; với chuỗi ngày/số do JDK tạo, kiểm thử trong runtime đã chốt hoặc kiểm tra quy tắc cần thiết thay vì giả định mọi provider luôn cho cùng một chuỗi.
- **Dữ liệu hiển thị:** số lượng đơn vị, tiền giao dịch, ngày giờ phải được giữ nguyên ngữ nghĩa khi đổi locale; sự khác biệt chỉ là cách trình bày có chủ đích.

Một ví dụ lỗi thực tế: trang chọn `pt-PT`, nhưng server chỉ lưu `"pt"` và dùng `Locale.getDefault()`. Sau đó số tiền và nội dung có thể phụ thuộc vào cấu hình máy chủ thay vì lựa chọn người dùng. Cách khắc phục là lưu `pt-PT` dưới dạng tag, chọn bộ thông điệp phù hợp và đưa `Locale.forLanguageTag("pt-PT")` vào formatter của đúng request. Nếu đơn hàng có tiền tệ cụ thể, cung cấp `Currency` riêng; nếu hiển thị thời điểm, cung cấp `ZoneId` riêng.

## 8. Ghi nhớ

**Ngôn ngữ trả lời “viết/nói bằng tiếng gì?”, vùng trả lời “áp dụng quy ước địa phương nào?”, script trả lời “dùng hệ chữ viết nào?”**. `Locale` phối hợp các lựa chọn này nhưng không thay thế nội dung bản dịch, tiền tệ giao dịch hoặc múi giờ. Với cùng một ngôn ngữ ở nhiều khu vực, lưu và truyền **thẻ BCP 47 đủ thông tin cần thiết**, cung cấp tài nguyên theo vùng khi phù hợp, thiết kế fallback rõ ràng và kiểm thử trên cả những vùng có cùng mã ngôn ngữ.