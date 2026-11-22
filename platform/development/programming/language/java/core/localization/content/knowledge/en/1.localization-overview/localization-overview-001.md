# Quốc tế hóa (i18n) và bản địa hóa (l10n) là gì?

## 1. Bài toán: một ứng dụng, nhiều ngôn ngữ và thị trường

Giả sử một ứng dụng Java phục vụ người dùng Việt Nam và Hoa Kỳ. Cùng một dữ liệu, người dùng có thể kỳ vọng giao diện và cách trình bày khác nhau:

| Thành phần | Việt Nam (ví dụ) | Hoa Kỳ (ví dụ) |
| --- | --- | --- |
| Lời chào | Xin chào | Hello |
| Ngày | 28/10/2026 | 10/28/2026 |
| Số | 1.234,5 | 1,234.5 |
| Tiền tệ hiển thị | VND, thường không có chữ số thập phân | USD, thường có hai chữ số thập phân |

Các biểu diễn trên mang tính minh họa; dấu phân cách, khoảng trắng, ký hiệu tiền và thứ tự thành phần có thể thay đổi theo chuẩn dữ liệu ngôn ngữ của môi trường chạy. Ứng dụng còn phải xét múi giờ, cách xưng hô, chiều đọc, độ dài bản dịch và quy tắc địa phương.

Nếu viết cố định mọi chuỗi giao diện, định dạng ngày và tiền ngay trong mã nghiệp vụ, mỗi thị trường mới sẽ đòi hỏi sửa nhiều chỗ. **Quốc tế hóa** và **bản địa hóa** giúp tách phần có thể thay đổi theo thị trường ra khỏi logic cốt lõi.

## 2. Định nghĩa và mối quan hệ

**Quốc tế hóa (internationalization, i18n)** là quá trình **thiết kế và xây dựng phần mềm để có thể thích nghi với nhiều ngôn ngữ, vùng và quy ước văn hóa mà không phải viết lại logic nghiệp vụ cho từng thị trường**. Tên viết tắt “i18n” gồm chữ *i*, 18 chữ cái ở giữa và chữ *n*.

Công việc i18n thường bao gồm:

- Tách văn bản khỏi mã nguồn, đặt trong các tài nguyên có thể thay thế theo ngôn ngữ.
- Biểu diễn lựa chọn ngôn ngữ/vùng bằng `Locale` hoặc thẻ ngôn ngữ BCP 47.
- Dùng các API phù hợp để định dạng ngày, giờ, số, phần trăm, tiền tệ và so sánh/sắp xếp chữ.
- Thiết kế giao diện cho văn bản dài hơn, nhiều hệ chữ, chiều đọc phải-sang-trái; hỗ trợ Unicode.
- Định nghĩa cơ chế chọn ngôn ngữ, ngôn ngữ mặc định và cách xử lý khi thiếu bản dịch.

**Bản địa hóa (localization, l10n)** là quá trình **chuẩn bị và kiểm tra trải nghiệm cụ thể cho một ngôn ngữ, vùng hoặc thị trường đích** trên nền phần mềm đã hỗ trợ i18n. Tên viết tắt “l10n” gồm chữ *l*, 10 chữ cái ở giữa và chữ *n*.

Công việc l10n thường bao gồm:

- Dịch thông điệp sang tiếng Việt, tiếng Anh, tiếng Nhật… và duyệt thuật ngữ theo ngữ cảnh.
- Chọn cách thể hiện ngày, số, tiền tệ, đơn vị đo, địa chỉ và tên người phù hợp đối tượng.
- Điều chỉnh hình ảnh, hướng dẫn, nội dung pháp lý hoặc cách diễn đạt theo văn hóa và quy định liên quan.
- Kiểm thử bản dịch trong giao diện thật, đặc biệt với chữ dài, dấu tiếng Việt và ngữ pháp.

**Quan hệ:** i18n tạo **khả năng thích nghi**; l10n cung cấp và kiểm chứng **nội dung/trải nghiệm cho từng thị trường**. Một ứng dụng có thể được quốc tế hóa tốt nhưng chưa có bản dịch tiếng Việt; cũng có thể dịch vài dòng tiếng Việt mà vẫn chưa quốc tế hóa đúng vì ngày, số hoặc thông báo lỗi còn được hard-code.

| Tiêu chí | i18n | l10n |
| --- | --- | --- |
| Câu hỏi chính | “Hệ thống có hỗ trợ nhiều locale không?” | “Trải nghiệm cho locale này đã đúng chưa?” |
| Thời điểm | Ngay từ thiết kế và phát triển | Khi chuẩn bị hoặc duy trì từng phiên bản địa phương |
| Ví dụ | Mã gọi `ResourceBundle` lấy thông điệp | Tệp `messages_vi.properties` chứa bản dịch |
| Ví dụ khác | Dùng `NumberFormat` theo locale | Kiểm tra cách trình bày số/tiền đối với người dùng Việt |
| Kết quả | Một nền ứng dụng có thể tái sử dụng | Một bản địa hóa đã được kiểm thử |

## 3. `Locale` là thông tin gì trong Java?

`java.util.Locale` mô tả các yếu tố của ngôn ngữ và vùng như **language**, **script**, **region** và **variant** khi có. Ví dụ:

- `vi-VN`: tiếng Việt, vùng Việt Nam.
- `en-US`: tiếng Anh, vùng Hoa Kỳ.
- `en-GB`: tiếng Anh, vùng Vương quốc Anh; vẫn là tiếng Anh nhưng một số quy ước có thể khác `en-US`.
- `zh-Hant-TW`: tiếng Hoa, chữ phồn thể, vùng Đài Loan.

Trong Java, `Locale.forLanguageTag("vi-VN")` tạo locale từ thẻ ngôn ngữ BCP 47. `Locale` **không tự dịch chuỗi** và **không chứa múi giờ**. Cần quản lý riêng `ZoneId` khi hiển thị thời điểm theo vị trí của người dùng; ví dụ, ngôn ngữ tiếng Việt không đồng nghĩa người đó đang ở múi giờ Việt Nam.

Nên dùng locale được chọn rõ ràng theo cấu hình người dùng hoặc lựa chọn hợp lệ từ yêu cầu. `Locale.getDefault()` chỉ phản ánh mặc định của môi trường chạy; trên máy chủ nó có thể khác ngôn ngữ mong muốn của từng người dùng. Tránh thay đổi `Locale.setDefault(...)` toàn tiến trình để phục vụ từng request vì các request đồng thời có thể ảnh hưởng nhau.

## 4. Ví dụ Java 17+: cùng mã, hai bản địa hóa

Ví dụ sau dùng `ResourceBundle` cho thông điệp, `NumberFormat` cho tiền tệ và `DateTimeFormatter` cho ngày. Tạo **bốn tệp cùng một thư mục** với nội dung sau (lưu tệp ở UTF-8).

**`messages.properties`** — thông điệp gốc dự phòng:

```properties
welcome=Welcome
```

**`messages_vi.properties`** — bản dịch tiếng Việt:

```properties
welcome=Xin chào
```

**`messages_en.properties`** — bản dịch tiếng Anh:

```properties
welcome=Hello
```

**`DemoI18n.java`**:

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class DemoI18n {
    public static void main(String[] args) {
        show(Locale.forLanguageTag("vi-VN"));
        show(Locale.forLanguageTag("en-US"));
    }

    private static void show(Locale locale) {
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);
        NumberFormat currency = NumberFormat.getCurrencyInstance(locale);
        DateTimeFormatter date = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

        System.out.println(locale.toLanguageTag() + " | "
                + messages.getString("welcome"));
        System.out.println("  money: " + currency.format(1234567.5));
        System.out.println("  date: " + date.format(LocalDate.of(2026, 10, 28)));
    }
}
```

Biên dịch và chạy từ thư mục chứa cả bốn tệp:

```bash
javac -encoding UTF-8 DemoI18n.java
java -cp . DemoI18n
```

Hai dòng lời chào chắc chắn có dạng **`vi-VN | Xin chào`** và **`en-US | Hello`** (mỗi dòng có các dòng `money` và `date` theo sau). Phần tiền và ngày sẽ có biểu diễn khác nhau theo locale; ký hiệu, khoảng trắng và cách diễn đạt ngày có thể phụ thuộc JDK/CLDR, nên không giả định một stdout cố định cho những phần đó.

Ở đây **i18n** nằm trong việc mã đọc gói tài nguyên và dùng API định dạng theo `locale`; **l10n** nằm trong nội dung từng tệp `.properties` và quyết định bản dịch nào phù hợp. Đổi locale không cần sửa logic `show`.

**Lưu ý về tiền:** `getCurrencyInstance(locale)` dùng quy ước tiền tệ gắn với vùng của locale. Ví dụ chỉ trình diễn định dạng, **không phải phép đổi tỷ giá VND ↔ USD**; hệ thống giao dịch phải lưu giá trị, mã tiền thực tế và nghiệp vụ quy đổi một cách độc lập.

## 5. Cơ chế tra cứu và fallback của `ResourceBundle`

Với basename `messages` và locale `vi-VN`, `ResourceBundle` tìm các ứng viên phù hợp, chẳng hạn `messages_vi_VN.properties`, rồi `messages_vi.properties`. Gói gốc `messages.properties` có thể làm dự phòng. Thuật toán đầy đủ còn xét default locale và quy tắc của `ResourceBundle.Control` nên không nên giả định chỉ có một chuỗi fallback duy nhất trong mọi cấu hình.

Các nguyên tắc thực tế:

1. Dùng **khóa ổn định** như `login.button`, `error.required`, không dùng nguyên câu dịch làm khóa.
2. Đặt bản dịch cùng ý nghĩa ở các locale; nếu một locale thiếu khóa, kiểm tra rõ đường fallback. Nếu không có khóa ở bất kỳ bundle được chọn nào, `getString` có thể ném `MissingResourceException`.
3. Tránh ghép câu bằng các mảnh dịch (`"Hello " + name + "!"`) nếu cấu trúc ngữ pháp có thể thay đổi. Dùng thông điệp có tham số để người dịch chỉnh thứ tự thành phần.
4. Không dùng `Locale.toString()` làm chuẩn trao đổi thẻ ngôn ngữ qua HTTP/API; ưu tiên `toLanguageTag()` và `forLanguageTag(...)` cho BCP 47.
5. Trên Java 9+, `ResourceBundle` đọc `.properties` bằng UTF-8 theo mặc định (có hành vi tương thích để xử lý tệp cũ). Khi làm việc với hệ thống cũ hoặc công cụ đóng gói riêng, vẫn cần kiểm tra encoding thực tế.

Ví dụ thông điệp có tham số:

```properties
order.summary=Order {0}: {1} items
```

Có thể dùng `java.text.MessageFormat` để thay tham số theo locale. Cần chú ý dấu nháy đơn trong cú pháp `MessageFormat`, định dạng tham số và sự khác biệt số ít/số nhiều. `MessageFormat` chuẩn của Java không tự cung cấp toàn bộ quy tắc plural/gender theo mọi ngôn ngữ; nếu sản phẩm cần các thông điệp ngữ pháp phức tạp, cân nhắc thư viện hỗ trợ ICU MessageFormat hoặc một cơ chế đã kiểm thử.

## 6. Những phần không nên nhầm lẫn

**Ngôn ngữ, vùng và múi giờ là ba quyết định khác nhau.** Người dùng chọn tiếng Việt ở London vẫn có thể muốn ngày/giờ theo `Europe/London`. `LocalDate` là ngày lịch; với một sự kiện có thời điểm tuyệt đối, phải dùng `Instant`/ `ZonedDateTime` cùng `ZoneId` phù hợp trước khi format. Chọn locale đơn thuần không chuyển múi giờ.

**Định dạng không đồng nghĩa phân tích dữ liệu.** `NumberFormat` có thể format và parse chuỗi theo locale; dấu phẩy `,` và dấu chấm `.` có thể mang nghĩa khác nhau giữa thị trường. Trong API và lưu trữ dữ liệu, hãy dùng kiểu dữ liệu có cấu trúc, chẳng hạn số và mã tiền, rồi chỉ chuyển sang chuỗi bản địa hóa ở ranh giới giao diện.

**So sánh chữ không luôn giống so sánh byte/ký tự.** Nếu danh sách tên hiển thị cần thứ tự phụ thuộc locale, xem `java.text.Collator`. Việc chuyển hoa/thường có trường hợp đặc biệt theo ngôn ngữ (ví dụ tiếng Thổ Nhĩ Kỳ), vì vậy hãy phân biệt các thao tác dành cho người dùng với các định danh kỹ thuật cần quy tắc ổn định như `Locale.ROOT`.

**Unicode là điều kiện cần, chưa đủ.** UTF-8 giúp lưu nhiều hệ chữ, nhưng giao diện còn phải có font phù hợp, không cắt chữ có dấu, không cố định chiều rộng theo tiếng Anh và xử lý được văn bản từ phải sang trái nếu phạm vi sản phẩm yêu cầu. Với tìm kiếm/so khớp tên người, có thể cần xử lý chuẩn hóa Unicode và quy tắc locale một cách chủ đích.

**Dịch đúng từ chưa chắc đã bản địa hóa đúng.** Ví dụ hướng dẫn nhập địa chỉ, định dạng họ tên, đơn vị đo, nội dung xác nhận thanh toán và giọng điệu xưng hô có thể cần biên tập riêng cho thị trường đích.

## 7. Quy trình áp dụng trong dự án Java

1. **Xác định các locale cần hỗ trợ** và quy tắc chọn locale (ưu tiên người dùng, cấu hình ứng dụng, hoặc `Accept-Language` khi phù hợp); xác định locale dự phòng.
2. **Tách chuỗi giao diện và thông báo lỗi** sang tệp tài nguyên. Đặt khóa có tên rõ nghĩa, dùng tham số thay cho ghép câu và lưu ý ngữ cảnh dịch.
3. **Dùng đúng API ở nơi hiển thị**: `ResourceBundle` cho thông điệp; `NumberFormat` cho số/phần trăm/tiền; `DateTimeFormatter` với locale để hiển thị ngày; `Collator` nếu cần sắp xếp văn bản theo ngôn ngữ.
4. **Giữ logic và dữ liệu chuẩn độc lập với bản dịch**: lưu số bằng kiểu số, tiền kèm mã tiền, thời điểm với thông tin thời gian phù hợp. Không dùng chuỗi đã format làm giá trị tính toán.
5. **Thực hiện l10n có ngữ cảnh**: dịch, duyệt thuật ngữ, kiểm tra các tình huống có tham số, văn bản dài, chữ có dấu và các yêu cầu vùng miền.
6. **Kiểm thử ma trận locale**: ít nhất kiểm tra hai locale có dấu phân cách khác nhau; thiếu khóa và fallback; định dạng số/ngày; lựa chọn múi giờ; giao diện với văn bản dài; ký tự đặc biệt. Với kiểm thử tự động, truyền locale/time zone cố định để tránh phụ thuộc mặc định của máy chạy.

### Lỗi phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Hard-code `"dd/MM/yyyy"` cho mọi người dùng | Trình bày sai quy ước địa phương | Dùng `DateTimeFormatter` theo locale khi hiển thị |
| Nghĩ `Locale` tự dịch văn bản | Giao diện vẫn chỉ có một ngôn ngữ | Cung cấp tài nguyên/bản dịch cho locale |
| Dựa vào default locale của server | Người dùng nhận sai ngôn ngữ | Truyền locale tường minh theo từng thao tác |
| Dùng locale như múi giờ | Ngày/giờ sự kiện sai địa điểm | Quản lý `ZoneId` riêng |
| Coi đổi định dạng tiền là đổi tiền tệ | Nhầm số tiền giao dịch | Xử lý mã tiền và tỷ giá ở nghiệp vụ |
| Ghép câu dịch từ nhiều đoạn | Lỗi ngữ pháp ở ngôn ngữ khác | Dùng thông điệp có tham số và review l10n |
| Kiểm thử duy nhất `en-US` | Bỏ sót lỗi dấu, font, số, ngày | Kiểm thử locale khác quy ước và bản dịch thật |

## 8. Ghi nhớ

- **i18n**: xây dựng một kiến trúc cho phép thay đổi ngôn ngữ và quy ước trình bày theo `Locale`, tránh sửa mã nghiệp vụ cho mỗi thị trường.
- **l10n**: tạo, biên tập và kiểm thử nội dung/trải nghiệm phù hợp cho **một** locale hoặc thị trường cụ thể.
- Trong Java, `Locale`, `ResourceBundle`, `NumberFormat`, `DateTimeFormatter` và khi cần `Collator` là những công cụ nền tảng. Chúng hỗ trợ định dạng, chọn tài nguyên và quy tắc ngôn ngữ; chất lượng bản dịch và quyết định văn hóa vẫn cần con người hoặc quy trình l10n kiểm chứng.
