# Locale không tự chứa toàn bộ dữ liệu định dạng

Trong Java, `Locale` biểu diễn **ngôn ngữ và quy ước vùng mà một thao tác nên sử dụng**, chứ không phải một “kho dữ liệu” chứa sẵn tất cả ký hiệu, mẫu ngày tháng, tên tháng, đơn vị tiền tệ hay câu chữ đã dịch. Khi ứng dụng định dạng một giá trị, API định dạng kết hợp `Locale` với **dữ liệu và quy tắc do môi trường chạy cung cấp**, rồi mới tạo ra chuỗi hiển thị.

Ý chính cần nắm: **`Locale` là đầu vào để chọn quy tắc; kết quả định dạng được tính bởi formatter và nguồn dữ liệu locale tại thời điểm chạy.** Hai môi trường cùng sử dụng `Locale.forLanguageTag("vi-VN")` vẫn có thể cho ra chuỗi khác nhau ở một số chi tiết nếu khác phiên bản JDK, nhà cung cấp dữ liệu hoặc cấu hình.

## 1. `Locale` chứa gì và không chứa gì?

Một đối tượng `java.util.Locale` mô tả các thành phần định danh như:

- **Language**: mã ngôn ngữ, ví dụ `vi`, `en`, `fr`.
- **Script**: hệ chữ viết nếu cần, ví dụ `Latn` hoặc `Hant`.
- **Region**: quốc gia/vùng lãnh thổ, ví dụ `VN`, `US`, `TW`.
- **Variant và Unicode extensions**: thông tin bổ sung, có thể đề xuất hệ chữ số, lịch hoặc thứ tự sắp xếp tùy API và nhà cung cấp hỗ trợ.

Ví dụ `vi-VN` biểu thị tiếng Việt trong ngữ cảnh Việt Nam. Đối tượng đó có thể trả về `vi` và `VN`, nhưng **không lưu trong chính đối tượng một bảng đầy đủ** như “dấu thập phân phải là ký tự nào”, “ngày dài gồm những từ gì” hay “tất cả tên tháng được viết ra sao”.

| Thành phần | Vai trò | Có phải dữ liệu nằm trọn trong `Locale`? |
| --- | --- | --- |
| `Locale.forLanguageTag("vi-VN")` | Xác định ngữ cảnh ngôn ngữ/vùng | Có: mã định danh và các thành phần của nó |
| `NumberFormat`, `DecimalFormatSymbols` | Chọn dấu phân cách, chữ số, quy tắc số và tiền tệ | Không: API lấy quy tắc/ký hiệu từ dữ liệu locale được hỗ trợ |
| `DateTimeFormatter` với định dạng localized | Chọn mẫu ngày/giờ và tên tháng/ngày theo locale | Không: mẫu và tên hiển thị đến từ nguồn dữ liệu định dạng |
| `Currency` | Mã tiền tệ, ký hiệu và thông tin liên quan | Không: cần bảng thông tin tiền tệ; locale chỉ giúp xác định ngữ cảnh |
| `ResourceBundle` | Lấy câu chữ do ứng dụng tự dịch | Không: bản dịch phải nằm trong bundle/tệp/tài nguyên của ứng dụng |
| `ZoneId`, dữ liệu múi giờ (tzdb) | Xác định giờ địa phương, độ lệch UTC và quy tắc DST | Không: `Locale` không phải múi giờ |

**Hệ quả:** `Locale.US` không đồng nghĩa với `America/New_York`; nước Mỹ có nhiều múi giờ. `Locale.FRANCE` cũng không chứa tỷ giá EUR hay bản dịch giao diện của ứng dụng.

## 2. Dòng xử lý thực tế: từ `Locale` đến chuỗi hiển thị

Có thể hình dung quá trình theo thứ tự:

1. **Ứng dụng lựa chọn locale**: chẳng hạn `vi-VN` theo lựa chọn của người dùng.
2. **Ứng dụng lựa chọn formatter phù hợp với dữ liệu**: `NumberFormat` cho số/tiền, `DateTimeFormatter` cho ngày giờ, `ResourceBundle` cho thông điệp.
3. **Formatter tra dữ liệu/quy tắc của môi trường**: quy ước nhóm chữ số, mẫu ngày dài, tên tháng, ký hiệu tiền tệ, hoặc bundle do ứng dụng cung cấp.
4. **Formatter kết hợp dữ liệu với giá trị đầu vào** và trả về chuỗi hiển thị.

Các bản JDK hiện đại thường có dữ liệu locale dựa trên **Unicode CLDR** (Common Locale Data Repository). Java có cơ chế nhà cung cấp dữ liệu locale (`LocaleServiceProvider` và các provider tích hợp); chi tiết về dữ liệu có thể đổi giữa các bản JDK, bản CLDR và cấu hình provider. Một thư viện khác như ICU4J có thể sử dụng phiên bản dữ liệu và quy tắc riêng. Vì thế **mã định danh giống nhau không bảo đảm mọi byte/ký tự đầu ra luôn giống nhau trên mọi runtime**.

Ví dụ các dấu cách thông thường, dấu cách không ngắt dòng (`U+00A0`), dấu cách hẹp không ngắt dòng (`U+202F`), thứ tự thành phần ngày và chữ viết tắt có thể khác. Đừng dựa vào hình thức nhìn thấy giống nhau để kết luận hai chuỗi có cùng ký tự Unicode.

## 3. Ví dụ 1 — Nhìn vào `Locale` không thấy toàn bộ định dạng

Tạo tệp `LocaleIdentityDemo.java`:

~~~java
import java.util.Currency;
import java.util.Locale;

public class LocaleIdentityDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");

        System.out.println(locale.toLanguageTag());
        System.out.println(locale.getLanguage());
        System.out.println(locale.getCountry());
        System.out.println(Currency.getInstance(locale).getCurrencyCode());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac LocaleIdentityDemo.java
java LocaleIdentityDemo
~~~

Kết quả:

~~~text
vi-VN
vi
VN
VND
~~~

Ba dòng đầu lấy thông tin định danh có trong `Locale`. Dòng cuối **không chứng minh `Locale` lưu sẵn “VND”**: `Currency.getInstance(locale)` sử dụng thông tin vùng để tra dữ liệu tiền tệ của Java. Việc một API có thể trả ra dữ liệu theo locale không đồng nghĩa dữ liệu đó được chứa bên trong đối tượng locale.

Ngôn ngữ và vùng không thể luôn suy ra lẫn nhau: `vi` không tự động có nghĩa là `VN`; `en` được dùng tại nhiều vùng, mỗi vùng có thể có cách hiển thị số, tiền và ngày khác nhau.

## 4. Ví dụ 2 — Một giá trị, nhiều chuỗi hiển thị

Tạo `LocalizedFormattingDemo.java`:

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedFormattingDemo {
    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale unitedStates = Locale.US;
        double value = 1234567.89;
        LocalDate date = LocalDate.of(2024, 12, 31);

        NumberFormat viNumber = NumberFormat.getNumberInstance(vietnam);
        NumberFormat usNumber = NumberFormat.getNumberInstance(unitedStates);
        NumberFormat usMoney = NumberFormat.getCurrencyInstance(unitedStates);

        DateTimeFormatter viDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(vietnam);

        System.out.println("vi-VN number: " + viNumber.format(value));
        System.out.println("en-US number: " + usNumber.format(value));
        System.out.println("en-US money: " + usMoney.format(value));
        System.out.println("vi-VN date: " + viDate.format(date));
    }
}
~~~

~~~bash
javac LocalizedFormattingDemo.java
java LocalizedFormattingDemo
~~~

Trên một môi trường JDK có quy tắc CLDR thông dụng, hai số có thể lần lượt hiển thị theo dạng `1.234.567,89` và `1,234,567.89`; tiền USD có thể hiện theo dạng `$1,234,567.89`. Dòng ngày dài sẽ dùng mẫu và tên gọi tương ứng với `vi-VN`. **Đó là ví dụ về hình thức**, không phải hợp đồng chuỗi chính xác cho mọi bản JDK/provider. Khi chạy chương trình, hãy quan sát ký tự thực tế, đặc biệt các loại khoảng trắng.

Trong ví dụ:

- `value` vẫn là cùng một số kiểu `double`; formatter không thay đổi giá trị toán học.
- `viNumber` và `usNumber` được tạo từ hai locale khác nhau; chính formatter áp dụng các quy ước tương ứng.
- `usMoney` định dạng giá trị bằng tiền USD theo ngữ cảnh Mỹ; thao tác này **không quy đổi tỷ giá**.
- `viDate` lấy mẫu ngày dài localized; `LocalDate` vẫn là cùng ngày `2024-12-31`, bất kể chuỗi hiển thị.

Nếu muốn dùng một đơn vị tiền cụ thể không trùng đơn vị mặc định của vùng, hãy đặt rõ trên formatter:

~~~java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.US);
money.setCurrency(java.util.Currency.getInstance("EUR"));
System.out.println(money.format(1234.50));
~~~

Đoạn trên minh họa cách cấu hình formatter, **không phải một chương trình độc lập**; đặt bên trong phương thức Java thích hợp. Nó hiển thị số tiền theo quy ước định dạng của `Locale.US` nhưng với đơn vị tiền EUR. Ký hiệu và vị trí hiển thị có thể phụ thuộc dữ liệu locale/provider. `setCurrency` cũng **không thực hiện đổi USD sang EUR**.

### Quy tắc cụ thể có thể được điều chỉnh

`NumberFormat` và các lớp con như `DecimalFormat` hỗ trợ cấu hình nhóm chữ số, số chữ số thập phân, làm tròn và ký hiệu theo trường hợp sử dụng. Ví dụ:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
number.setGroupingUsed(false);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
System.out.println(number.format(1234.5));
~~~

Đây cũng là một **đoạn đặt trong phương thức**. Với `Locale.US` và cấu hình trên, kết quả là:

~~~text
1234.50
~~~

Vậy locale chỉ là **một thành phần đầu vào**; việc ứng dụng chủ động cấu hình formatter cũng quyết định kết quả.

## 5. Phân biệt dữ liệu định dạng với dữ liệu dịch giao diện

`Locale` không tự dịch các chuỗi của ứng dụng như “Đăng nhập”, “Đã lưu” hay “Chào mừng”. Ứng dụng cần cung cấp bản dịch bằng `ResourceBundle` hoặc hệ thống i18n tương đương.

Ví dụ đặt ba tệp cùng thư mục làm việc:

**`Messages.properties`** (bundle gốc):

~~~properties
welcome=Welcome!
~~~

**`Messages_vi.properties`** (bản dịch tiếng Việt):

~~~properties
welcome=Chào mừng!
~~~

**`ResourceBundleDemo.java`**:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceBundleDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle messages =
                ResourceBundle.getBundle("Messages", requested);

        System.out.println(messages.getString("welcome"));
    }
}
~~~

Chạy trong thư mục chứa cả ba tệp:

~~~bash
javac ResourceBundleDemo.java
java -cp . ResourceBundleDemo
~~~

Kết quả:

~~~text
Chào mừng!
~~~

Java tra bundle phù hợp theo chuỗi ứng viên: ở đây không có `Messages_vi_VN.properties`, nhưng có `Messages_vi.properties`, nên lấy bản dịch tiếng Việt. Nếu không có ứng viên phù hợp, cơ chế `ResourceBundle` còn có quy tắc fallback riêng, bao gồm khả năng dùng locale mặc định và bundle gốc tùy tình huống. **Không nên suy diễn rằng mọi API định dạng có cùng thuật toán fallback với `ResourceBundle`.**

Trong JDK 17, tệp `.properties` cho `PropertyResourceBundle` có hỗ trợ đọc UTF-8 (với cơ chế tương thích theo đặc tả); nên lưu các tệp này dưới mã hóa UTF-8 nhất quán. Trong ứng dụng đóng gói, đưa bundle vào **classpath/resources** phù hợp, thay vì phụ thuộc thư mục hiện hành.

Điểm tách biệt rõ ràng: **dữ liệu dịch “Chào mừng!” do ứng dụng viết**; `vi-VN` chỉ định bộ tài nguyên mà ứng dụng yêu cầu.

## 6. `Locale` không thay thế múi giờ, lịch và sở thích người dùng

Một ứng dụng hiển thị thời gian cần xác định độc lập:

- **Instant**: thời điểm trên trục thời gian, không phụ thuộc ngôn ngữ/vùng.
- **ZoneId**: quy tắc để chuyển thời điểm thành ngày giờ địa phương; có thể bao gồm lịch sử thay đổi độ lệch UTC và giờ mùa hè.
- **Locale**: cách ghi tên tháng/thứ, mẫu ngày/giờ localized và thông tin ngôn ngữ khi formatter sử dụng.
- **Chronology hoặc quy tắc nghiệp vụ** nếu ứng dụng dùng lịch khác ISO; không thể cho rằng việc đổi locale tự động đổi toàn bộ lịch/ý nghĩa ngày.
- **Sở thích của người dùng** như chế độ 12/24 giờ hoặc đơn vị đo; một số lựa chọn có thể cần cấu hình riêng, không nên suy ra hoàn toàn từ quốc gia.

Ví dụ độc lập `ZoneDemo.java`:

~~~java
import java.time.Instant;
import java.time.ZoneId;

public class ZoneDemo {
    public static void main(String[] args) {
        Instant timestamp = Instant.parse("2024-01-01T00:00:00Z");
        System.out.println(
                timestamp.atZone(ZoneId.of("Asia/Tokyo")).toLocalTime());
    }
}
~~~

~~~bash
javac ZoneDemo.java
java ZoneDemo
~~~

Kết quả cho thời điểm này tại Tokyo:

~~~text
09:00
~~~

Không cần `Locale.JAPAN` để tính giờ Tokyo: việc chuyển giờ dùng `ZoneId` và dữ liệu múi giờ. Ngược lại, đổi `Locale` chỉ có tác dụng lên chuỗi ngày/giờ khi formatter thực sự dựa vào locale.

## 7. Lựa chọn locale đúng và xử lý fallback

### Cấu tạo rõ ràng bằng BCP 47

`Locale.forLanguageTag(...)` nhận một language tag chuẩn BCP 47, ví dụ:

- `en-US`: tiếng Anh, vùng Mỹ.
- `en-GB`: tiếng Anh, vùng Anh.
- `zh-Hant-TW`: tiếng Trung, hệ chữ Hán phồn thể, vùng Đài Loan.
- `sr-Latn-RS`: tiếng Serbia, hệ Latin, vùng Serbia.
- `th-TH-u-nu-thai`: tiếng Thái tại Thái Lan, có yêu cầu hệ chữ số Thái (`nu=thai`).

Các extension như `nu` là **thông tin yêu cầu/hint**: API hoặc provider có thể hỗ trợ, không nên coi mọi kết hợp đều được tất cả formatter tuân thủ. Khi yêu cầu không được hỗ trợ, formatter có thể dùng quy tắc dự phòng.

Có thể dùng `Locale.Builder` để xây từng thành phần và kiểm tra lỗi cú pháp nghiêm ngặt hơn `forLanguageTag`, ví dụ:

~~~java
Locale serbianLatin = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();
System.out.println(serbianLatin.toLanguageTag());
~~~

Đoạn này đặt trong phương thức Java và cần `import java.util.Locale;`. Kết quả:

~~~text
sr-Latn-RS
~~~

### Fallback không đồng nghĩa với dịch chính xác

Nếu runtime thiếu dữ liệu dành riêng cho tổ hợp locale được yêu cầu, API có thể dùng dữ liệu chung hơn hoặc theo cơ chế fallback của provider. Điều đó giúp chức năng định dạng tiếp tục hoạt động nhưng **không bảo đảm đáp ứng mọi quy ước địa phương**. Vì thế:

- Truyền locale mà người dùng hoặc yêu cầu nghiệp vụ thực sự chọn.
- Có chiến lược fallback bản dịch rõ ràng trong ứng dụng.
- Kiểm thử locale và định dạng quan trọng trên runtime dùng để triển khai.
- Tránh suy luận vùng từ ngôn ngữ hoặc dùng `getDisplayName()` như khóa lưu trữ; nên lưu language tag bằng `toLanguageTag()`.

## 8. Vì sao một `Locale` có thể cho kết quả khác trên hai môi trường?

Hãy xét cùng một lời gọi `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(locale)` hoặc `NumberFormat.getNumberInstance(locale)`:

| Yếu tố thay đổi | Điều có thể thay đổi |
| --- | --- |
| Phiên bản JDK / phiên bản CLDR đi kèm | Mẫu ngày, dấu phân cách, tên gọi, ký hiệu, dạng viết tắt |
| Provider và thứ tự provider được runtime cấu hình | Bộ quy tắc locale được chọn |
| Locale thực tế, kể cả script/region/extensions | Mẫu và chữ số mà formatter ưu tiên |
| Cấu hình trực tiếp trên formatter | Số chữ số, cách làm tròn, ký hiệu, đơn vị tiền |
| `ZoneId` và dữ liệu tzdb | Giờ địa phương, độ lệch UTC, quy tắc DST |
| Dữ liệu dịch của ứng dụng | Câu chữ giao diện trả về từ bundle |

Trong môi trường có yêu cầu tái lập kết quả nghiêm ngặt (snapshot test, ký số, giao thức máy đọc), không nên coi chuỗi localized là biểu diễn chuẩn bất biến. Với dữ liệu trao đổi giữa hệ thống, nên dùng chuẩn không phụ thuộc locale như ISO 8601 cho ngày/giờ, mã tiền tệ ISO 4217 và biểu diễn số thống nhất; chỉ định dạng theo locale tại ranh giới hiển thị cho người dùng.

**Lưu ý về thread safety:** `DateTimeFormatter` trong `java.time` là immutable và an toàn để chia sẻ giữa các luồng. `NumberFormat`/`DecimalFormat` có trạng thái mutable và không được bảo đảm thread-safe; nên tạo formatter theo phạm vi sử dụng hoặc có chiến lược đồng bộ/chia sẻ phù hợp. Đây là đặc tính của **formatter**, không phải nội dung của `Locale`.

## 9. Các ngộ nhận phổ biến

1. **“`Locale` tự chứa dấu phân cách, tên tháng và bản dịch.”** Sai: nó định danh ngữ cảnh; formatter, provider và tài nguyên ứng dụng cung cấp dữ liệu tương ứng.
2. **“Cùng `vi-VN`, kết quả hiển thị bắt buộc giống hệt ở mọi JDK.”** Sai: dữ liệu locale/provider có thể thay đổi; ký tự khoảng trắng còn có thể khác dù trông giống.
3. **“Đổi `Locale.setDefault(...)` chỉ ảnh hưởng đúng một request.”** Sai: locale mặc định có phạm vi toàn JVM (có các category liên quan), dễ gây tác dụng chéo giữa request/luồng. Truyền locale tường minh cho từng formatter trong ứng dụng nhiều người dùng.
4. **“`Locale.US` tự xác định múi giờ.”** Sai: sử dụng `ZoneId` hoặc timezone tường minh.
5. **“`NumberFormat.getCurrencyInstance(locale)` đổi giá trị sang tiền của vùng.”** Sai: chỉ định dạng số với đơn vị/ký hiệu tiền tệ; muốn đổi tiền phải có tỷ giá và quy tắc nghiệp vụ riêng.
6. **“Ngôn ngữ `en` đủ để biết người dùng muốn ngày tháng kiểu Mỹ.”** Sai: `en-US` và `en-GB` có thể khác; không tự đoán vùng nếu thiếu.
7. **“Dùng `Locale.ROOT` sẽ tự tạo ra định dạng cố định cho giao thức.”** Không có bảo đảm đó đối với mọi API localized; hãy chọn định dạng chuẩn tường minh cho máy đọc.

## 10. Cách áp dụng trong ứng dụng thực tế

Giả sử ứng dụng bán hàng phục vụ người dùng Việt Nam và Mỹ:

1. Lưu sở thích ngôn ngữ/vùng của mỗi người dùng bằng language tag, ví dụ `vi-VN` hay `en-US`. Xác định riêng múi giờ `Asia/Ho_Chi_Minh` hoặc `America/Los_Angeles` từ cài đặt hợp lệ của người dùng.
2. Giữ dữ liệu gốc theo kiểu phù hợp: tiền nên dùng `BigDecimal` cùng mã tiền tệ; thời điểm dùng `Instant`; ngày thuần túy dùng `LocalDate` khi đúng nghĩa nghiệp vụ.
3. Khi dựng giao diện, dùng `NumberFormat`/`DateTimeFormatter` với locale và các tùy chọn cụ thể. Lấy thông báo giao diện từ `ResourceBundle`/hệ thống i18n.
4. Đừng áp đặt chuỗi hiển thị localized vào database hoặc giao thức như dữ liệu chuẩn. Phân tích và lưu giá trị theo kiểu dữ liệu, chỉ render ra chuỗi ở lớp trình bày.
5. Kiểm thử các locale và múi giờ thực sự hỗ trợ, kể cả dấu ngăn cách đặc biệt, fallback bundle và dữ liệu định dạng khi nâng cấp JDK.

**Tự kiểm tra kiến thức:**

- Khi `Locale.forLanguageTag("fr-FR")` và `NumberFormat` tạo ra dấu nhóm chữ số, dữ liệu về dấu đó đến từ đâu? — Từ cơ chế định dạng/dữ liệu locale do môi trường cung cấp, không phải bảng ký hiệu tự chứa trong `Locale`.
- Vì sao cần truyền cả `Locale` lẫn `ZoneId` để hiển thị một timestamp? — `ZoneId` xác định giờ địa phương; `Locale` quyết định cách biểu diễn thông tin đó thành văn bản theo ngôn ngữ/vùng.
- Vì sao thiếu `Messages_vi_VN.properties` vẫn có thể hiện “Chào mừng!”? — `ResourceBundle` tìm được bundle `Messages_vi.properties` theo quy tắc ứng viên.
- Khi thay JDK làm một snapshot số tiền thay đổi ký tự khoảng trắng, có nhất thiết dữ liệu tiền thay đổi? — Không; quy tắc/ký hiệu định dạng có thể đổi trong khi giá trị và mã tiền vẫn giữ nguyên.

**Ghi nhớ:** `Locale` là **định danh và ngữ cảnh để lựa chọn quy tắc**. Formatter + dữ liệu locale của runtime + cấu hình ứng dụng mới tạo ra chuỗi; bản dịch và múi giờ là những nguồn dữ liệu riêng cần được quản lý tường minh.