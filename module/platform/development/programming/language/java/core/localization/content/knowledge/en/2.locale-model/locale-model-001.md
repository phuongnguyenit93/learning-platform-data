# `Locale` — định danh yêu cầu quy ước văn hóa trong Java

## Mục tiêu của bài

Sau bài học, bạn có thể giải thích `java.util.Locale` dùng để mô tả điều gì, đọc và tạo một định danh locale chuẩn, phân biệt locale với dữ liệu bản địa hóa, và truyền locale tường minh vào những API xử lý ngôn ngữ hoặc quy ước vùng miền. Trọng tâm là **mô hình định danh**: một `Locale` cho biết người dùng hoặc tác vụ muốn áp dụng bộ quy ước nào; bản thân đối tượng này không chứa bản dịch, mẫu ngày tháng hay bảng tỷ giá.

## 1. Locale trả lời câu hỏi gì?

Một ứng dụng có thể phục vụ cùng một nội dung cho nhiều người, nhưng mỗi người mong đợi cách hiển thị khác nhau:

- Người dùng chọn tiếng Việt ở Việt Nam: nhãn giao diện tiếng Việt; số, ngày giờ và tiền tệ hiển thị theo quy ước phù hợp.
- Người dùng chọn tiếng Anh ở Hoa Kỳ: nhãn tiếng Anh, thứ tự ngày tháng và cách nhóm chữ số có thể khác.
- Người dùng chọn tiếng Anh ở Vương quốc Anh: vẫn dùng tiếng Anh, nhưng quy ước tiền tệ hoặc ngày tháng có thể khác Hoa Kỳ.
- Người dùng chọn tiếng Trung phồn thể tại Đài Loan: ngôn ngữ, hệ chữ và vùng đều có ý nghĩa.

`Locale` là **định danh ngữ cảnh ngôn ngữ/văn hóa** được Java dùng làm đầu vào để các thư viện chọn quy tắc tương ứng. Nó **không tự chuyển ngữ một chuỗi**, không chứa tài nguyên dịch thuật và không bảo đảm mọi thư viện đều hỗ trợ mọi định danh.

Hãy tách ba lớp:

1. **Yêu cầu**: `Locale.forLanguageTag("vi-VN")` — “hãy dùng quy ước gắn với tiếng Việt tại Việt Nam khi có thể”.
2. **Nguồn dữ liệu và thuật toán**: `ResourceBundle`, dữ liệu định dạng của JDK, các provider, thư viện i18n, thông điệp do ứng dụng cung cấp.
3. **Kết quả**: nhãn đã được dịch, số/ngày đã định dạng, thứ tự so sánh chuỗi… phụ thuộc API, dữ liệu hiện có và chính sách fallback.

Bởi vậy, hai chương trình nhận cùng `Locale` vẫn có thể tạo kết quả khác nếu dùng API, phiên bản dữ liệu địa phương hóa hoặc tài nguyên ứng dụng khác nhau.

## 2. Thành phần của một định danh locale

Trong Java, `java.util.Locale` là đối tượng bất biến biểu diễn các thành phần như sau:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Language | Ngôn ngữ; thường dùng mã ngôn ngữ theo chuẩn BCP 47 | `vi`, `en`, `sr`, `zh` |
| Script | Hệ chữ viết, khi cần phân biệt | `Latn` (Latin), `Cyrl` (Cyrillic), `Hant` (Hán phồn thể) |
| Region | Quốc gia hoặc vùng lãnh thổ, khi liên quan đến quy ước | `VN`, `US`, `GB`, `TW` |
| Variant | Biến thể có quy tắc riêng; ít dùng trong trường hợp phổ biến | Có thể xuất hiện trong tag hợp lệ |
| Extensions | Yêu cầu bổ sung, chẳng hạn hệ chữ số hoặc lịch | `u-nu-latn` |

Một vài tag minh họa:

- `vi`: yêu cầu tiếng Việt, chưa chỉ định vùng.
- `vi-VN`: tiếng Việt tại Việt Nam.
- `en-US` và `en-GB`: cùng ngôn ngữ, khác vùng.
- `sr-Latn-RS`: tiếng Serbia, hệ Latin, tại Serbia.
- `zh-Hant-TW`: tiếng Trung, hệ phồn thể, tại Đài Loan.
- `en-US-u-nu-latn`: tiếng Anh/Hoa Kỳ kèm Unicode locale extension yêu cầu hệ chữ số Latin.

Ngôn ngữ, hệ chữ và vùng có vai trò riêng. Một vùng có thể có nhiều ngôn ngữ; một ngôn ngữ có thể được dùng ở nhiều vùng; một ngôn ngữ có thể có nhiều hệ chữ. Vì thế **không suy ra ngôn ngữ từ quốc gia, cũng không suy ra quốc gia từ ngôn ngữ**. Ví dụ, `en` không mặc định đồng nghĩa `en-US`; `zh` không mặc định nói rõ giản thể hay phồn thể.

Một tag không mang các thông tin cá nhân như quốc tịch, vị trí GPS, múi giờ hiện tại, hệ điều hành hoặc loại tiền mà người dùng chắc chắn muốn giao dịch. `vi-VN` là một yêu cầu quy ước, không phải bằng chứng người dùng đang ở Việt Nam.

### BCP 47 và biểu diễn trong Java

BCP 47 là cách biểu diễn phổ biến của language tag bằng dấu gạch nối `-`: `en-US`, `zh-Hant-TW`. Trong Java:

- `Locale.forLanguageTag(String)` đọc language tag.
- `locale.toLanguageTag()` xuất định danh phù hợp để trao đổi và lưu cấu hình.
- `getLanguage()`, `getScript()`, `getCountry()`, `getVariant()` và `getExtension(char)` cung cấp từng phần.

Mã ngôn ngữ thường là chữ thường, mã script thường ở dạng Title Case, mã vùng chữ hoa. Java có thể chuẩn hóa cách viết và một số mã lịch sử. Đối tượng `Locale` lưu mô hình đã phân tích, vì vậy tag sau khi `toLanguageTag()` không nhất thiết giữ đúng từng ký tự đầu vào.

Không dùng `toString()` của `Locale` làm định dạng trao đổi chính: cách biểu diễn truyền thống có dấu gạch dưới, ví dụ `en_US`, khác cú pháp BCP 47 `en-US`. Khi cấu hình/API đòi language tag, hãy dùng `toLanguageTag()`.

## 3. Tạo, đọc và kiểm tra Locale trong Java 17+

Ví dụ chạy độc lập sau cho thấy cách tạo locale, lấy thành phần và giữ đúng sự khác biệt giữa ngôn ngữ, hệ chữ, vùng. Nó cũng cho thấy locale có thể ảnh hưởng đến một thao tác xử lý chuỗi.

Tạo tệp `LocaleIdentityDemo.java`:

```java
import java.util.Locale;

public class LocaleIdentityDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        Locale englishUS = Locale.forLanguageTag("en-US");

        Locale serbianLatin = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();

        System.out.println(vietnamese.toLanguageTag());
        System.out.println(englishUS.getLanguage());
        System.out.println(englishUS.getCountry());
        System.out.println(serbianLatin.toLanguageTag());
        System.out.println(Locale.ROOT.toLanguageTag());

        Locale turkish = Locale.forLanguageTag("tr-TR");
        System.out.println("i".toUpperCase(Locale.ROOT));
        System.out.println("i".toUpperCase(turkish));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocaleIdentityDemo.java
java LocaleIdentityDemo
```

Kết quả:

```text
vi-VN
en
US
sr-Latn-RS
und
I
İ
```

Giải thích:

- `getLanguage()` trả `en` còn `getCountry()` trả `US`; đây là các trường riêng, không phải hai cách gọi cùng một giá trị.
- `Locale.Builder` thích hợp khi muốn đặt từng thành phần rõ ràng và phát hiện đầu vào sai chuẩn. Các phương thức `setLanguage`, `setScript`, `setRegion` có thể ném `IllformedLocaleException` nếu giá trị không đúng dạng.
- `Locale.ROOT` là locale trung lập, có language tag `und` (“undetermined”): hữu ích khi cần phép xử lý độc lập với ngôn ngữ/người dùng.
- Chữ `i` được viết hoa thành `I` trong locale trung lập, nhưng thành ký tự `İ` (I hoa có dấu chấm, U+0130) theo quy tắc tiếng Thổ Nhĩ Kỳ. Đó là ví dụ cụ thể vì sao hành vi xử lý ngôn ngữ cần locale, ngay cả khi không hiển thị số hay ngày tháng.

`Locale.forLanguageTag(...)` tiện cho tag nhận từ cấu hình hoặc giao thức. Tuy nhiên đây là bộ phân tích linh hoạt: với chuỗi không đúng chuẩn, Java có thể bỏ qua phần không hợp lệ và trả về locale đã phân tích một phần. Đừng xem việc tạo được `Locale` là bằng chứng tag hợp lệ, nội dung được cho phép hoặc có bản dịch. Khi cần từ chối đầu vào sai, hãy kiểm tra cú pháp/chính sách hỗ trợ của ứng dụng; `Locale.Builder.setLanguageTag(...)` là lựa chọn chặt chẽ hơn cho bước kiểm tra hình thức.

## 4. Định danh khác với dữ liệu và chính sách hỗ trợ

Giả sử giao diện có ba bộ thông điệp `messages_vi.properties`, `messages_en.properties` và một bộ mặc định. Khi chọn `vi-VN`:

- `Locale` mô tả yêu cầu tiếng Việt tại Việt Nam.
- Hệ thống tài nguyên tìm thông điệp thích hợp, có thể dùng tài nguyên tiếng Việt nếu không có biến thể vùng.
- Nếu thiếu khóa hay tài nguyên, hành vi phụ thuộc vào quy tắc fallback của thư viện và cấu hình ứng dụng.

Không có nghĩa mọi khóa dịch sẽ tự xuất hiện hoặc Java tự biết cách dịch nội dung tùy ý. `ResourceBundle` thực thi cơ chế tra cứu tài nguyên; `Locale` chỉ là một đầu vào của cơ chế đó.

Tương tự, `DateTimeFormatter.ofLocalizedDate(...)`, `NumberFormat.getNumberInstance(...)` và `Collator.getInstance(...)` đều có thể nhận locale, nhưng mỗi API dùng locale cho một nhiệm vụ riêng: định dạng ngày, định dạng số, so sánh chuỗi theo quy ước ngôn ngữ. **Cùng tag, nhiều cách sử dụng khác nhau**, không có một “định dạng Locale” duy nhất.

Khả năng hỗ trợ cũng không đồng nhất:

- JDK/locale provider quyết định có dữ liệu định dạng nào cho một vùng và phiên bản cụ thể.
- Ứng dụng quyết định đã dịch những ngôn ngữ nào.
- Thư viện có thể bỏ qua một số extension hoặc fallback sang quy tắc gần nhất.
- Một tag BCP 47 hợp lệ vẫn có thể không nằm trong danh sách ngôn ngữ sản phẩm hỗ trợ.

Để giao diện ổn định, nên phân biệt **locale người dùng yêu cầu** (`requestedLocale`) với **locale thực sự được chọn** (`resolvedLocale`) sau khi so khớp các locale ứng dụng hỗ trợ. Việc fallback không phải thuộc tính sẵn có duy nhất của đối tượng `Locale`: từng API có quy tắc khác nhau.

## 5. Locale được sử dụng ở đâu?

### Định dạng số và tiền tệ

```java
import java.text.NumberFormat;
import java.util.Locale;

Locale viVN = Locale.forLanguageTag("vi-VN");
Locale enUS = Locale.forLanguageTag("en-US");

NumberFormat viNumber = NumberFormat.getNumberInstance(viVN);
NumberFormat usNumber = NumberFormat.getNumberInstance(enUS);

String a = viNumber.format(1234567.89);
String b = usNumber.format(1234567.89);

NumberFormat currency = NumberFormat.getCurrencyInstance(viVN);
String amount = currency.format(1234567.89);
```

Đây là đoạn mã minh họa đặt trong một phương thức, **không phải chương trình chạy độc lập**. Các chuỗi `a`, `b`, `amount` mang định dạng theo locale và provider. Không đóng cứng giả định về ký hiệu khoảng trắng, dấu phân nhóm hay số chữ số thập phân trong output vì dữ liệu bản địa hóa và phiên bản JDK có thể khác. Cũng không nhầm `getCurrencyInstance(viVN)` với quyết định nghiệp vụ rằng giao dịch phải dùng VND; tiền tệ thực tế nên được chỉ định theo dữ liệu giao dịch khi cần.

### Ngày tháng: Locale khác múi giờ

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Locale frFR = Locale.forLanguageTag("fr-FR");
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.FULL)
        .withLocale(frFR);

String label = LocalDate.of(2026, 10, 28).format(formatter);
```

Đây cũng là đoạn minh họa, không phải tệp chạy độc lập. `Locale` quyết định quy ước ngôn ngữ và cách trình bày; `LocalDate` mang ngày theo lịch ISO; `ZoneId` xử lý múi giờ khi chuyển giữa thời điểm tuyệt đối và ngày/giờ địa phương. Chọn `fr-FR` **không** tự chọn múi giờ Paris. Khi ứng dụng hiển thị thời điểm toàn cầu, phải xác định cả `ZoneId` theo yêu cầu.

### Phân loại, sắp xếp và xử lý chữ

So sánh chuỗi theo thứ tự từ điển của một ngôn ngữ có thể dùng `Collator.getInstance(locale)`; chuẩn hóa chữ hoa/chữ thường để hiển thị có thể cần `String.toUpperCase(locale)`. Đây không giống phép so sánh mã ký tự và cũng không bảo đảm phù hợp cho mã định danh kỹ thuật.

Khi xử lý token máy đọc, khóa cấu hình, tên hằng hay giao thức, `Locale.ROOT` thường phù hợp hơn mặc định theo người dùng. Ví dụ `"identifier".toUpperCase(Locale.ROOT)` có hành vi độc lập với việc người dùng chọn tiếng Thổ Nhĩ Kỳ.

### Tài nguyên giao diện

`ResourceBundle.getBundle("messages", locale)` tìm nguồn thông điệp theo cấu trúc và quy tắc fallback của ResourceBundle. Ví dụ, nếu ứng dụng có tệp properties tương ứng, bạn có thể yêu cầu `vi-VN`, nhưng vẫn cần quản lý tập khóa dịch, fallback và khả năng báo thiếu khóa. `Locale` không tự tạo các tệp properties hoặc dịch các khóa chưa có.

## 6. Default locale và ranh giới phạm vi

`Locale.getDefault()` đọc locale mặc định của JVM. Java còn phân biệt:

- `Locale.getDefault(Locale.Category.DISPLAY)`: dùng cho tên hiển thị của các mục như ngôn ngữ, quốc gia.
- `Locale.getDefault(Locale.Category.FORMAT)`: dùng cho những quy tắc định dạng như số/ngày.
- `Locale.setDefault(...)` và các biến thể theo category thay đổi mặc định trong JVM.

Mặc định này là **trạng thái dùng chung của tiến trình**, không phải locale gắn riêng với từng HTTP request hay từng luồng. Vì vậy, một dịch vụ có nhiều người dùng **không nên gọi `Locale.setDefault` mỗi khi có request**: các request chạy đồng thời có thể ảnh hưởng lẫn nhau.

Ưu tiên truyền `Locale` tường minh vào API:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat formatter = NumberFormat.getNumberInstance(locale);
String result = formatter.format(1234.5);
```

Mã trên là đoạn minh họa bên trong một phương thức. Với ứng dụng web, locale của request có thể đến từ tùy chọn đã lưu của người dùng hoặc cơ chế thương lượng ngôn ngữ; sau đó truyền xuống các lớp cần định dạng. Tránh để các lớp sử dụng mặc định JVM ngầm nếu dữ liệu thuộc nhiều ngôn ngữ/vùng.

## 7. Nhận locale từ cấu hình hoặc yêu cầu người dùng

Một chuỗi như `vi-VN` có thể đến từ cài đặt cá nhân, đường dẫn ứng dụng, HTTP `Accept-Language` hay cấu hình hệ thống. Hãy xử lý theo các bước:

1. **Đọc yêu cầu**: ví dụ language tag `vi-VN` hoặc danh sách ưu tiên trong `Accept-Language`.
2. **Kiểm tra và giới hạn**: xác thực cú pháp/độ dài nếu nhận từ bên ngoài; chỉ chấp nhận những lựa chọn mà sản phẩm có hỗ trợ.
3. **So khớp**: chọn một trong các locale đã khai báo của ứng dụng theo chính sách rõ ràng. Việc so khớp `vi-VN` về `vi`, chẳng hạn, là quyết định chính sách nếu sản phẩm chỉ có tài nguyên tiếng Việt chung.
4. **Lưu ngữ cảnh**: giữ locale được giải quyết xuyên suốt request hoặc thao tác; không chỉnh default JVM cho người dùng đó.
5. **Truyền tường minh**: dùng locale để tra cứu thông điệp, định dạng số/ngày và sắp xếp theo nhu cầu; truyền thêm `ZoneId` và `Currency` khi bài toán cần.
6. **Fallback có chủ đích**: nếu không tìm thấy bản dịch hoặc định dạng mong muốn, dùng locale dự phòng đã chọn và ghi nhận tình huống thiếu dữ liệu.

Header `Accept-Language` có thể chứa nhiều ưu tiên và hệ số chất lượng `q`, nên không được giả định toàn bộ header là một language tag duy nhất. Java có `Locale.LanguageRange.parse(...)`, `Locale.filter(...)` và `Locale.lookup(...)` hỗ trợ thương lượng; hãy dùng khi xử lý danh sách ưu tiên, đồng thời áp dụng danh sách locale thực tế ứng dụng hỗ trợ.

Một tag hợp lệ không bảo đảm sản phẩm có nội dung phù hợp; người dùng có thể chọn một locale mà ứng dụng không cung cấp thông điệp. Cần quy tắc ưu tiên và fallback để tránh kết quả lẫn ngôn ngữ.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `Locale("vi-VN")` tương đương mọi API đọc language tag | Hãy dùng `Locale.forLanguageTag("vi-VN")` với cú pháp BCP 47; không đặt cả tag vào trường language của constructor. |
| `vi-VN` nghĩa là người dùng đang ở Việt Nam | Locale diễn đạt quy ước mong muốn, không xác nhận vị trí, quốc tịch hoặc múi giờ. |
| `en` luôn là `en-US` | Locale chỉ có ngôn ngữ chưa nêu rõ vùng; ứng dụng cần chính sách chọn vùng khi cần. |
| `Locale` chứa bản dịch | Bản dịch thuộc tài nguyên của ứng dụng; `Locale` chỉ giúp chỉ ra yêu cầu tra cứu. |
| Tag BCP 47 hợp lệ nghĩa là được hỗ trợ | Mức hỗ trợ phụ thuộc provider, API và tài nguyên đã phát hành. |
| `toString()` là tag gửi qua API | Ưu tiên `toLanguageTag()` cho trao đổi cấu hình theo BCP 47. |
| Đổi locale sẽ đổi múi giờ | Múi giờ là `ZoneId`, độc lập với `Locale`. |
| Đặt `Locale.setDefault` cho mỗi request là an toàn | Default JVM dùng chung; hãy truyền locale trực tiếp đến API hoặc giữ trong request context. |
| `String.toUpperCase()` luôn như nhau ở mọi nơi | Chuyển chữ có trường hợp phụ thuộc ngôn ngữ; dùng locale tường minh hoặc `Locale.ROOT` cho dữ liệu kỹ thuật. |
| Java sẽ luôn hiển thị output giống nhau ở mọi bản JDK | Dữ liệu bản địa hóa và provider có thể khác; test theo ràng buộc xác định và môi trường cụ thể. |

## 9. Bài thực hành tư duy

Một ứng dụng có tài nguyên tiếng Việt chung `vi` và tiếng Anh Mỹ `en-US`. Người dùng gửi `vi-VN` và đặt múi giờ `Asia/Tokyo`.

- **Locale được yêu cầu** là `vi-VN`. Ứng dụng có thể quyết định dùng tài nguyên `vi` sau khi so khớp; việc fallback sang `vi` cần là chính sách được xác nhận.
- **Múi giờ** vẫn là `Asia/Tokyo` nếu đó là lựa chọn của người dùng. Không suy từ `vi-VN` thành `Asia/Ho_Chi_Minh`.
- **Số/ngày** cần truyền locale đã chọn vào formatter; nếu đang đổi một `Instant` thành giờ hiển thị, truyền thêm `ZoneId`.
- **Loại tiền giao dịch** phải đến từ đơn hàng hoặc miền nghiệp vụ; đừng suy hoàn toàn từ locale.
- Nếu người dùng đổi ngôn ngữ sang `en-US` nhưng giữ múi giờ, nhãn và định dạng có thể thay đổi, còn thời điểm thực tế không đổi.

Đây là lợi ích chính của mô hình: giữ **yêu cầu ngôn ngữ/quy ước** riêng với **dữ liệu nội dung**, **múi giờ** và **thông tin nghiệp vụ**.

## 10. Ghi nhớ

`Locale` là **định danh của một yêu cầu quy ước văn hóa** trong Java, thường gồm language, script, region và extension. Dùng BCP 47 và `Locale.forLanguageTag`/`toLanguageTag` để trao đổi định danh, `Locale.Builder` khi cần xây dựng rõ ràng hoặc kiểm tra hình thức chặt hơn, `Locale.ROOT` cho nhiều phép biến đổi kỹ thuật không phụ thuộc người dùng. Locale chỉ có tác dụng khi được một API/tài nguyên sử dụng; kết quả cuối cùng còn phụ thuộc dữ liệu hỗ trợ và chính sách fallback. Trong ứng dụng đa người dùng, hãy giải quyết locale tại ranh giới request rồi truyền tường minh, đồng thời quản lý múi giờ và tiền tệ như những khái niệm độc lập.
