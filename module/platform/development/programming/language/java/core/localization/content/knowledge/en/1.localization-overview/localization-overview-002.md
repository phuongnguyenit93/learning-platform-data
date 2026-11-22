# Vì sao bản địa hóa không chỉ là dịch chuỗi

## 1. Bản địa hóa giải quyết vấn đề gì?

Hãy tưởng tượng một ứng dụng bán hàng đã dịch toàn bộ nút `Buy` thành `Mua`, thông báo `Order completed` thành `Đặt hàng thành công`. Người dùng Việt Nam vẫn có thể gặp những vấn đề sau:

- Giá hiển thị `$1,234.50` trong khi giao dịch thực tế thanh toán bằng VND; dấu phân cách và ký hiệu tiền tệ khiến người đọc hiểu nhầm.
- Ngày `03/04/2026` không nói rõ là ngày 3 tháng 4 hay ngày 4 tháng 3; giờ hẹn lệch một ngày do dùng múi giờ máy chủ.
- Thông báo ghép `1 items` hoặc dịch thành một câu có trật tự từ không tự nhiên.
- Ô nhập họ tên bắt buộc `First name / Last name`, địa chỉ bắt buộc `State` và mã ZIP dù quốc gia người dùng không có cấu trúc đó.
- Kết quả tìm kiếm/sắp xếp tên có dấu sai thứ tự; giao diện cắt mất chữ sau khi dịch hoặc khó sử dụng ở ngôn ngữ viết từ phải sang trái.

Những vấn đề này vẫn tồn tại dù từng chuỗi giao diện đã được dịch chính xác. **Bản địa hóa (localization, l10n) là điều chỉnh toàn bộ cách hệ thống biểu diễn và tương tác để phù hợp với ngôn ngữ, vùng và ngữ cảnh văn hóa của người dùng.** Dịch thuật là một phần của công việc ấy, không bao quát toàn bộ.

Mục tiêu của bài: phân biệt quốc tế hóa và bản địa hóa; nhận diện các dữ liệu và hành vi phụ thuộc locale; triển khai một luồng bản địa hóa cơ bản bằng Java; hiểu giới hạn và cách kiểm thử.

## 2. Phân biệt i18n, l10n và dịch thuật

| Khái niệm | Câu hỏi cần giải quyết | Ví dụ |
| --- | --- | --- |
| **Quốc tế hóa (internationalization, i18n)** | Kiến trúc có hỗ trợ nhiều ngôn ngữ/vùng mà không sửa logic nghiệp vụ mỗi lần thêm một thị trường không? | Tách thông điệp khỏi code; truyền `Locale`, múi giờ và đơn vị tiền tệ vào lớp trình bày |
| **Bản địa hóa (localization, l10n)** | Trải nghiệm cụ thể có phù hợp người dùng mục tiêu không? | Câu chữ tiếng Việt, cách hiển thị ngày/tiền, quy tắc nhập địa chỉ, hình ảnh và luồng giao diện |
| **Dịch thuật (translation)** | Nội dung ngôn ngữ có chuyển đúng nghĩa và đúng ngữ cảnh không? | `Your order is ready` → `Đơn hàng của bạn đã sẵn sàng` |

i18n tạo khả năng thay đổi; l10n thực hiện sự thích ứng cho một đối tượng cụ thể; dịch thuật xử lý nội dung ngôn ngữ. Một sản phẩm có thể dịch hết chuỗi mà vẫn có thiết kế khó bản địa hóa, chẳng hạn công thức tính tiền phụ thuộc dấu phẩy hoặc giao diện cố định chiều rộng theo tiếng Anh.

`Locale` không đồng nghĩa với địa điểm thực tế, múi giờ hay tiền tệ. Một người dùng chọn `vi-VN` nhưng đang ở Tokyo, dùng múi giờ `Asia/Tokyo` và xem hóa đơn thanh toán bằng USD là tình huống hợp lệ.

## 3. Những lớp thích ứng ngoài văn bản

### 3.1. Số, tỷ lệ, tiền tệ và đơn vị đo

Cùng giá trị số 1234,5 có thể được trình bày minh họa là `1,234.5` hoặc `1.234,5`, tùy quy ước. Không được suy ra giá trị số bằng cách tự thay dấu phẩy/dấu chấm trong chuỗi hiển thị. Trong Java, hãy giữ giá trị kiểu số ở tầng dữ liệu và dùng `NumberFormat` để **định dạng đầu ra** theo `Locale`. Với tiền tệ, cần chỉ rõ loại tiền giao dịch bằng mã ISO 4217 như `VND` hay `USD`; ngôn ngữ giao diện không quyết định đồng tiền của đơn hàng.

Tiền phải được tính toán theo chính sách nghiệp vụ, thường bằng `BigDecimal` với độ chính xác và quy tắc làm tròn được xác định. `NumberFormat` phục vụ hiển thị, không thay thế xử lý tiền hoặc tự chuyển đổi tỷ giá. Đơn vị `km`/`mi`, `kg`/`lb`, °C/°F cũng cần chính sách đổi đơn vị riêng; đổi nhãn đơn vị mà không đổi con số là lỗi nghiêm trọng.

### 3.2. Ngày, giờ, múi giờ, lịch và tuần

`03/04/2026` là một chuỗi mơ hồ nếu không có quy tắc vùng. Cùng một thời điểm tuyệt đối còn có thể rơi vào hai **ngày lịch khác nhau** ở hai múi giờ. Bản địa hóa cần giải quyết độc lập:

1. **Instant**: thời điểm xảy ra sự kiện, có thể lưu dưới dạng `Instant`/UTC.
2. **ZoneId**: múi giờ dùng để hiển thị hoặc lên lịch, chẳng hạn `Asia/Ho_Chi_Minh` và `America/Los_Angeles`; quy tắc DST có thể thay đổi theo lịch sử.
3. **Locale**: cách viết tên tháng, thứ, số và định dạng ngày/giờ.
4. **Quy tắc nghiệp vụ**: hạn chót tính theo ngày địa phương nào, tuần bắt đầu ngày nào, ngày nghỉ và lịch nào được áp dụng.

Không dùng múi giờ mặc định của server làm đại diện cho mọi người dùng. Không dùng offset cố định (ví dụ `-07:00`) thay thế tùy tiện một `ZoneId` có daylight saving time.

### 3.3. Ngữ pháp và ngữ cảnh

Dịch từng mảnh chuỗi rồi nối lại thường thất bại với trật tự từ, giống ngữ pháp và số nhiều. Ví dụ, công thức `"You have " + count + " messages"` giả định cấu trúc câu tiếng Anh, không phù hợp với mọi ngôn ngữ. Nên thiết kế **thông điệp hoàn chỉnh** có tham số, để từng bản dịch quyết định thứ tự từ.

Một số ngôn ngữ có nhiều loại số nhiều hơn `one/other`, hoặc thay đổi hình thái theo giới, vai trò từ trong câu và ngữ cảnh. `MessageFormat` tiêu chuẩn của Java xử lý chèn tham số và một số định dạng nhưng **không tự cung cấp đầy đủ quy tắc plural/gender CLDR của mọi ngôn ngữ**. Nếu sản phẩm đa ngôn ngữ cần các quy tắc đó, cân nhắc công cụ thông điệp có ICU MessageFormat/plural rules và kiểm thử cùng biên dịch viên. Tránh tự viết `count == 1` như quy tắc toàn cầu.

Phải cung cấp ngữ cảnh cho người dịch: `Open` có thể là động từ “Mở” hay tính từ “Đang mở”; `Save` là lưu tệp hay tiết kiệm tiền. Key thông điệp rõ nghĩa, ghi chú ngữ cảnh và ví dụ màn hình giúp tránh bản dịch đúng từ nhưng sai chức năng.

### 3.4. Dữ liệu người dùng, tra cứu và Unicode

Tên, địa chỉ, số điện thoại, mã bưu chính và biểu mẫu không có một cấu trúc chung toàn cầu. Không giả định mọi người có hai thành phần họ/tên, mọi vùng có `State`, mọi số điện thoại có đúng một độ dài. Thay đổi nhãn chưa đủ nếu validation hoặc database schema vẫn áp đặt quy tắc của một quốc gia.

Unicode cũng là phần của l10n:

- Cùng ký tự nhìn thấy có thể có nhiều cách biểu diễn mã điểm, chẳng hạn ký tự dựng sẵn `é` và chuỗi `e` + dấu kết hợp. Cân nhắc chuẩn hóa bằng `java.text.Normalizer` trước những phép so khớp phù hợp.
- Phép so sánh chuỗi nhị phân không phải thứ tự từ điển của con người. Có thể dùng `Collator.getInstance(locale)` cho sắp xếp giao diện; cần thiết kế riêng cho truy vấn cơ sở dữ liệu, phân trang và chỉ mục.
- Bỏ dấu để tìm kiếm là lựa chọn sản phẩm, không phải phép biến đổi tương đương nghĩa cho mọi ngôn ngữ. Với tiếng Việt, dấu có thể phân biệt những từ khác nhau.
- Unicode, font, dấu kết hợp, cách xuống dòng và phương pháp nhập liệu phải được kiểm thử bằng dữ liệu thực tế, không chỉ `ASCII`.

### 3.5. Giao diện, hình ảnh và khả năng tiếp cận

Văn bản được dịch có thể dài hơn bản gốc: nút bấm, menu, bảng và cảnh báo cần co giãn, xuống dòng hợp lý và không cắt nội dung quan trọng. Với tiếng Ả Rập hoặc Hebrew, cần kiểm thử hướng hiển thị từ phải sang trái (RTL), vị trí thành phần điều hướng, thứ tự biểu tượng và nội dung trộn chữ số hoặc tên riêng. Không đảo chiều mọi biểu tượng một cách máy móc: biểu tượng phát video hay logo có thể có quy tắc riêng.

Hình ảnh, màu sắc, ví dụ, tên gọi, địa chỉ hỗ trợ, chính sách giao hàng và nội dung pháp lý cũng phụ thuộc bối cảnh địa phương. Nội dung hỗ trợ trình đọc màn hình, nhãn accessible và thông báo lỗi phải dùng cùng ngôn ngữ đang hiển thị. Một bản dịch tự nhiên không có nghĩa là biểu mẫu dùng bàn phím hoặc trình đọc màn hình đã hoạt động đúng.

## 4. Java biểu diễn locale như thế nào?

Java cung cấp `java.util.Locale` để biểu thị tùy chọn ngôn ngữ/vùng. Thẻ ngôn ngữ thường tuân theo BCP 47:

| Thẻ | Ý nghĩa ví dụ |
| --- | --- |
| `vi-VN` | Tiếng Việt dùng trong ngữ cảnh Việt Nam |
| `en-US` | Tiếng Anh dùng trong ngữ cảnh Hoa Kỳ |
| `en-GB` | Tiếng Anh dùng trong ngữ cảnh Vương quốc Anh |
| `zh-Hant-TW` | Tiếng Trung, chữ phồn thể, ngữ cảnh Đài Loan |

Có thể tạo `Locale.forLanguageTag("vi-VN")` và dùng nó cho `NumberFormat`, `DateTimeFormatter`, `Collator`, `ResourceBundle`. Không đồng nhất `Locale.getDefault()` với lựa chọn của người dùng: giá trị mặc định phụ thuộc môi trường chạy và có thể thay đổi. Nên truyền locale một cách tường minh ở ranh giới API và giao diện.

Một thẻ locale là **tín hiệu lựa chọn cách trình bày**, không chứng minh quốc tịch, vị trí hay ngôn ngữ người dùng thực sự thông thạo. Một ứng dụng thường xác định ngôn ngữ theo lựa chọn trong hồ sơ, sau đó mới xét ưu tiên từ request (chẳng hạn `Accept-Language`) và cuối cùng là fallback do sản phẩm quy định. Danh sách locale được hỗ trợ cần được kiểm soát; có locale hợp lệ không đồng nghĩa sản phẩm đã có bản dịch.

## 5. Ví dụ chạy được: thông điệp, tiền và ngày giờ

Tạo ba tệp UTF-8 trong cùng thư mục. Ví dụ cho thấy **nội dung bản dịch**, **locale định dạng**, **đồng tiền giao dịch** và **múi giờ hiển thị** là các đầu vào khác nhau.

**Tệp `messages.properties`** — bộ thông điệp mặc định:

```properties
order.total=Total: {0}
event.time=Event time: {0}
```

**Tệp `messages_vi.properties`** — thông điệp tiếng Việt:

```properties
order.total=Tổng tiền: {0}
event.time=Thời điểm sự kiện: {0}
```

**Tệp `LocalizationDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizationDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag(
                args.length == 0 ? "vi-VN" : args[0]);

        // Lấy ngôn ngữ thông điệp theo locale được chọn.
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);

        // Đồng tiền của đơn hàng là VND, độc lập với locale giao diện.
        BigDecimal amount = new BigDecimal("1234567.50");
        NumberFormat money = NumberFormat.getCurrencyInstance(locale);
        money.setCurrency(Currency.getInstance("VND"));
        String amountText = money.format(amount);

        // Thời điểm là UTC; cách hiển thị dùng múi giờ đã chọn.
        Instant event = Instant.parse("2026-10-28T01:30:00Z");
        ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");
        String eventText = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(locale)
                .withZone(displayZone)
                .format(event);

        MessageFormat totalTemplate =
                new MessageFormat(messages.getString("order.total"), locale);
        MessageFormat timeTemplate =
                new MessageFormat(messages.getString("event.time"), locale);

        System.out.println(totalTemplate.format(new Object[] { amountText }));
        System.out.println(timeTemplate.format(new Object[] { eventText }));
    }
}
```

Biên dịch/chạy bằng JDK 17+ tại thư mục chứa cả ba tệp:

```bash
javac -encoding UTF-8 LocalizationDemo.java
java LocalizationDemo vi-VN
java LocalizationDemo en-US
```

**Quan sát cần kiểm chứng:** chạy với `vi-VN` sẽ lấy câu tiếng Việt từ `messages_vi.properties`; chạy với `en-US` sử dụng thông điệp mặc định tiếng Anh. Số tiền VND và ngày/giờ được định dạng theo locale tương ứng. `2026-10-28T01:30:00Z` tương ứng 08:30 ngày 28/10/2026 ở `Asia/Ho_Chi_Minh`; cách viết ngày/giờ, khoảng trắng và ký hiệu tiền tệ có thể khác theo dữ liệu locale/CLDR và phiên bản JDK, vì vậy không giả định một dòng stdout bất biến cho mọi môi trường. Cả hai lần chạy vẫn biểu diễn **cùng số tiền và cùng thời điểm**.

**Điều đáng chú ý trong ví dụ:**

1. `ResourceBundle` tìm thông điệp theo mức độ phù hợp của locale rồi fallback. Với locale không có bundle, Java còn có cơ chế xét default locale trước base bundle; ứng dụng cần định nghĩa rõ fallback ngôn ngữ và kiểm thử trường hợp thiếu key/bundle. Đừng xem một key bị thiếu là bản dịch hợp lệ.
2. Java 9+ hỗ trợ đọc bundle `.properties` bằng UTF-8 (có fallback tương thích), phù hợp cách tạo tệp ở ví dụ. Cần kiểm tra encoding khi chạy bằng toolchain và dữ liệu thực tế.
3. `MessageFormat` đánh số chỗ thế bằng `{0}`, `{1}`…; bản dịch có thể đổi thứ tự tham số. Cú pháp dấu nháy đơn trong pattern `MessageFormat` có ý nghĩa escape đặc biệt: nội dung dịch chứa apostrophe phải được kiểm thử, không ghép chuỗi tùy tiện.
4. Ví dụ cố định `VND` và `Asia/Ho_Chi_Minh` để minh họa. Trong sản phẩm thật, đồng tiền lấy từ giao dịch và múi giờ lấy từ ngữ cảnh người dùng/nghiệp vụ; cả hai không được suy ra chỉ từ `Locale`.
5. `NumberFormat` quyết định hình thức làm tròn/hiển thị (đặc biệt với tiền tệ không có đơn vị lẻ). Việc thanh toán phải dùng số gốc và chính sách làm tròn nghiệp vụ, không đọc ngược chuỗi đã định dạng.

Đây là một ví dụ nhỏ về **trình bày**, không phải toàn bộ hệ thống bản địa hóa: nó chưa xử lý số nhiều phức tạp, RTL, nhập liệu hay bản dịch có ngữ cảnh.

## 6. Cách thiết kế luồng l10n trong ứng dụng thực tế

**Bước 1 — Giữ dữ liệu nghiệp vụ độc lập với hiển thị.** Lưu giá trị số theo kiểu số; thời điểm theo `Instant` khi cần lưu một sự kiện tuyệt đối; loại tiền theo mã tiền; đơn vị đo theo đơn vị chuẩn rõ ràng. Không lưu chuỗi `"1.234,50 ₫"` như giá trị số của đơn hàng hoặc `"28/10/2026 08:30"` như thời điểm tuyệt đối mà không biết zone.

**Bước 2 — Xác định các tùy chọn riêng.** Một request hoặc hồ sơ người dùng có thể mang `Locale`, `ZoneId`, currency và đơn vị hiển thị. Kiểm tra giá trị hợp lệ, phạm vi hỗ trợ và thứ tự ưu tiên. Múi giờ của lịch hẹn có thể theo địa điểm tổ chức, khác múi giờ của người xem.

**Bước 3 — Tổ chức thông điệp theo ý nghĩa.** Dùng key ổn định như `order.total`, `checkout.paymentFailed`, `profile.nameLabel`; kèm mô tả ngữ cảnh và tham số. Tránh lấy nguyên câu tiếng Anh làm định danh logic, và tránh nối những mảnh câu khi bản dịch cần tự điều chỉnh ngữ pháp.

**Bước 4 — Chuyển đổi tại ranh giới trình bày.** Format số/ngày/tiền và chọn thông điệp khi tạo UI, email hoặc tài liệu cho người nhận cụ thể. Khi trao đổi giữa dịch vụ, sử dụng schema có kiểu dữ liệu rõ ràng. Với input, dùng bộ parser theo locale khi giao diện cho phép nhập số/ngày địa phương, nhưng phải báo lỗi mơ hồ và kiểm soát chặt dữ liệu trước khi đưa vào nghiệp vụ.

**Bước 5 — Duy trì quy trình bản dịch.** Quản lý phiên bản key, phát hiện thiếu bản dịch, cung cấp ngữ cảnh và ảnh chụp màn hình, kiểm tra fallback, review bởi người hiểu ngôn ngữ và cập nhật cùng quá trình phát hành. Khi thay đổi nội dung một key có tác động nghĩa, cần rà soát tất cả bản dịch liên quan.

Ví dụ xử lý sai: dùng `Locale.setDefault(...)` theo từng HTTP request trong ứng dụng nhiều luồng. Đây là trạng thái **toàn JVM**, dễ khiến request của người này ảnh hưởng request khác. Thay vào đó, truyền locale của request trực tiếp tới formatter/template; không dùng mutable global default làm cơ chế chuyển ngôn ngữ theo người dùng.

## 7. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Chỉ tạo file dịch `messages_vi.properties` là coi như xong | Ngày, tiền, đơn vị, địa chỉ và layout vẫn chưa phù hợp | Kiểm kê toàn bộ điểm tương tác và dữ liệu locale-sensitive |
| Nối `"Hello " + name` rồi dịch từng mảnh | Giả định thứ tự câu và dấu câu | Thông điệp hoàn chỉnh có tham số |
| Dùng `Locale.getDefault()` tại mọi nơi | Kết quả phụ thuộc máy chạy, cấu hình hoặc request khác | Truyền locale rõ ràng theo ngữ cảnh |
| Suy ra currency/zone từ language | Một ngôn ngữ được dùng ở nhiều vùng, một giao dịch có tiền tệ riêng | Tách `Locale`, `Currency`, `ZoneId` |
| Tự dùng `String.replace(",", ".")` để parse số | Không hiểu dấu hàng nghìn, dấu thập phân và các kiểu số | Parser theo locale với validation phù hợp |
| Sắp xếp tên bằng thứ tự mã Unicode | Không phản ánh đầy đủ thứ tự chữ cái ngôn ngữ | Collation phù hợp ở UI và lớp tìm kiếm |
| Giả định mọi ngôn ngữ có hai nhánh số nhiều | Bỏ qua quy tắc plural và ngữ pháp | Hệ thống thông điệp có plural rules, test theo từng ngôn ngữ |
| Ép ô nhập/tên/địa chỉ theo mẫu một quốc gia | Chặn dữ liệu hợp lệ ở thị trường khác | Thiết kế schema và validation theo mục đích, quốc gia và chính sách |
| Hiển thị ngày giờ không có zone | Người dùng thấy sai giờ hoặc sai ngày | Lưu ngữ nghĩa thời gian và chuyển zone rõ ràng |
| Dịch toàn bộ chữ nhưng không test UI | Cắt chữ, hỏng RTL, thiếu accessible name | Kiểm thử giao diện ở locale thật và pseudolocale |

Một lỗi khác là đặt văn bản bản địa hóa trực tiếp vào HTML mà không encode theo ngữ cảnh. Bản dịch là dữ liệu đầu vào nội dung; vẫn cần escape/output encoding đúng khi dựng HTML, URL hoặc script. Bản địa hóa không thay thế an toàn đầu ra.

## 8. Kiểm thử thế nào để biết đã bản địa hóa đúng?

Nên kiểm tra cả **tính đúng dữ liệu** lẫn **trải nghiệm sử dụng**:

- **Ngôn ngữ và fallback:** key đủ, câu đúng ngữ cảnh, tham số đúng chỗ, thiếu bản dịch không làm mất nội dung; người dùng chuyển ngôn ngữ không ảnh hưởng phiên khác.
- **Số và tiền:** dấu phân cách, chữ số, số âm, số không, giá trị lớn, quy tắc làm tròn, mã tiền và ký hiệu; cùng một giá trị gốc không bị thay đổi vì format.
- **Ngày và giờ:** ngày mơ hồ, ranh giới nửa đêm, múi giờ khác nhau, chuyển DST, ngày hẹn lặp lại và vùng không dùng chung lịch/tuần.
- **Ngữ pháp:** `0`, `1`, `2`, `5`, số thập phân; dạng câu liên quan đến số nhiều, ngữ cảnh và cách xưng hô nếu sản phẩm dùng.
- **Unicode và tra cứu:** tên tiếng Việt có dấu, chuỗi dựng sẵn/kết hợp, sort/search, dán văn bản, font và nhập liệu.
- **Giao diện:** giả lập chuỗi dài bằng pseudolocalization, RTL nếu hỗ trợ, responsive, lỗi validation, bàn phím, màn hình nhỏ và trình đọc màn hình.
- **Nghiệp vụ vùng:** địa chỉ, định dạng liên lạc, đơn vị, phương thức thanh toán và quy định chỉ ở những thị trường sản phẩm thật sự phục vụ.

Ví dụ một ma trận kiểm thử nhỏ: `vi-VN` với múi giờ `Asia/Ho_Chi_Minh`; `en-US` nhưng vẫn giao dịch VND; `en-GB` với định dạng ngày khác `en-US`; một locale RTL nếu ứng dụng hỗ trợ; một múi giờ có DST cho sự kiện gần thời điểm chuyển giờ. Đừng chỉ chụp ảnh màn hình tiếng Anh và thay text bằng tiếng Việt.

Khi viết automated test cho formatter, cố định locale, zone và dữ liệu đầu vào; nếu so sánh chuỗi đầu ra theo từng ký tự, pin môi trường JDK/dữ liệu locale hoặc kiểm tra thuộc tính thật sự cần thiết. Tránh test mong đợi dấu cách/ký hiệu phụ thuộc phiên bản CLDR mà sản phẩm không cam kết giữ nguyên.

## 9. Ghi nhớ

**Dịch chuỗi trả lời “nói câu gì”, còn bản địa hóa trả lời “người dùng ở ngôn ngữ/vùng/ngữ cảnh này có đọc, nhập, hiểu và hoàn thành công việc một cách chính xác không”.** Một ứng dụng chỉ thực sự có trải nghiệm đa ngôn ngữ khi thông điệp, dữ liệu, định dạng, múi giờ, quy tắc nhập liệu, giao diện và kiểm thử cùng được thiết kế cho sự khác biệt địa phương. Java cung cấp các công cụ nền tảng như `Locale`, `ResourceBundle`, `NumberFormat`, `DateTimeFormatter` và `Collator`, nhưng sản phẩm vẫn phải quyết định và kiểm chứng các quy tắc nghiệp vụ, ngữ pháp và trải nghiệm người dùng.