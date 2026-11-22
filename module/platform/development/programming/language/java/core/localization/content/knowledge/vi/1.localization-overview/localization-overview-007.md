# Ranh giới giữa xử lý dữ liệu, tài nguyên và giao diện trong Java localization

## 1. Vì sao phải tách ba trách nhiệm?

Trong ứng dụng hỗ trợ nhiều ngôn ngữ và khu vực, **dữ liệu nghiệp vụ**, **tài nguyên bản địa hóa** và **cách hiển thị** thay đổi vì những lý do khác nhau. Tách chúng giúp một đơn hàng vẫn là cùng một đơn hàng khi người dùng đổi tiếng Việt sang tiếng Anh, đổi cách viết ngày tháng hoặc sử dụng thiết bị khác.

- **Xử lý dữ liệu (domain/application):** kiểm tra quy tắc nghiệp vụ, tính toán, lưu trữ và trao đổi các giá trị có ý nghĩa ổn định. Ví dụ: mã đơn, số tiền với đơn vị tiền tệ, thời điểm đặt hàng, trạng thái đơn hàng.
- **Tài nguyên bản địa hóa (localization resources):** cung cấp thông điệp, nhãn, bản dịch và mẫu câu theo ngôn ngữ. Ví dụ: khóa `order.summary` có bản tiếng Việt và bản tiếng Anh.
- **Giao diện hoặc lớp trình bày (presentation):** chọn `Locale`, múi giờ và định dạng; lấy đúng thông điệp từ tài nguyên; biến dữ liệu thành văn bản người dùng nhìn thấy. Ví dụ: cùng số tiền 1.234,50 USD có thể được trình bày khác nhau tùy locale.

**Nguyên tắc cốt lõi:** đổi locale phải đổi cách biểu diễn phù hợp mà không làm đổi giá trị nghiệp vụ. Một số nghiệp vụ có quy tắc riêng theo quốc gia (thuế, đơn vị được phép, pháp luật); đó là **business rule được mô hình hóa rõ ràng**, không phải hệ quả tự động của việc đổi ngôn ngữ giao diện.

## 2. Ranh giới trách nhiệm

| Câu hỏi | Lớp chịu trách nhiệm chính | Dạng dữ liệu nên dùng |
| --- | --- | --- |
| Đơn có mã gì và tổng tiền bao nhiêu? | Domain/application | `String` ID, `BigDecimal` và `Currency` |
| Sự kiện xảy ra lúc nào? | Domain/infrastructure | `Instant` hoặc kiểu thời gian phù hợp với ý nghĩa nghiệp vụ |
| Hiển thị câu “Đơn hàng …” bằng ngôn ngữ nào? | Resource + presentation | Khóa thông điệp và `ResourceBundle` |
| Viết dấu thập phân, nhóm nghìn, ngày giờ ra sao? | Presentation | `NumberFormat`, `DateTimeFormatter`, `Locale`, `ZoneId` |
| Dùng múi giờ nào để người đọc xem thời điểm? | Presentation / lựa chọn người dùng | `ZoneId` độc lập với `Locale` |
| Có được đặt hàng bằng đồng tiền này không? | Domain/application | Quy tắc tiền tệ, thị trường và hợp đồng |

Một luồng hiển thị điển hình:

~~~text
Nguồn dữ liệu / API
        |
        v
Domain: Order(id, amount, currency, placedAt)
        |
        v
Application: kiểm tra và xử lý nghiệp vụ
        |
        v
Presentation adapter: (Order, Locale, ZoneId)
        |                         |
        |                         +--> ResourceBundle: bản dịch + mẫu thông điệp
        +--> NumberFormat / DateTimeFormatter
        |
        v
UI hoặc response dành cho người dùng
~~~

Ở chiều ngược lại, **đầu vào từ giao diện** có thể cần parse theo locale (ví dụ `1.234,50`), sau đó kiểm tra hợp lệ và chuyển sang giá trị có cấu trúc trước khi đưa vào domain. Không truyền trực tiếp chuỗi hiển thị vào phép tính tiền hoặc logic nghiệp vụ.

## 3. Dữ liệu nghiệp vụ phải giữ nguyên ý nghĩa

Ví dụ với một đơn hàng:

- Lưu **giá trị tiền** dưới dạng `BigDecimal` và **đơn vị tiền** dưới dạng `Currency` hoặc mã ISO 4217; không chỉ lưu `"$1,234.50"` hay `"1.234,50"`.
- Lưu **thời điểm thực tế** dưới dạng `Instant` khi nghiệp vụ nói đến một sự kiện tuyệt đối. Khi trình bày, kết hợp với `ZoneId`; đừng suy ra múi giờ chỉ từ ngôn ngữ.
- Lưu **trạng thái** bằng mã ổn định (ví dụ `PENDING`, `PAID`); bản dịch “Chờ xử lý”/“Pending” thuộc tài nguyên giao diện. Không dùng bản dịch làm khóa database hoặc giá trị của enum nghiệp vụ.
- Dữ liệu người dùng thật sự nhập (tên người, địa chỉ, văn bản mô tả) là **dữ liệu**, không tự động biến thành khóa dịch. Chỉ dịch trường có thiết kế và nguồn bản dịch rõ ràng.

**Ví dụ sai:** lưu `total = "1.234,50 USD"` rồi tách chuỗi để cộng tiền; hoặc dùng `status = "Đã thanh toán"` để quyết định chuyển trạng thái. **Ví dụ đúng:** lưu `amount = 1234.50`, `currency = USD`, `status = PAID`, sau đó hiển thị theo locale yêu cầu.

Lưu ý: `Locale` không phải tỷ giá. Việc đổi từ `en-US` sang `vi-VN` không chuyển USD thành VND. Nếu hệ thống cần **quy đổi tiền tệ**, đó là một nghiệp vụ riêng có tỷ giá, nguồn tỷ giá, thời điểm áp dụng và quy tắc làm tròn.

## 4. Tài nguyên bản địa hóa chứa ngôn từ, không chứa nghiệp vụ

Java cung cấp `ResourceBundle` để chọn tài nguyên theo `Locale`. Với resource bundle dạng properties, những tệp như `messages_en.properties` và `messages_vi.properties` có cùng **khóa ổn định**, còn giá trị là bản dịch:

~~~properties
# messages_en.properties
order.summary=Order {0}: {1}; placed at {2}
~~~

~~~properties
# messages_vi.properties
order.summary=Đơn hàng {0}: {1}; đặt lúc {2}
~~~

Ở đây, `order.summary` là **định danh thông điệp**, không phải tiếng Anh gốc. Các placeholder `{0}`, `{1}`, `{2}` lần lượt nhận mã đơn, tiền đã định dạng và thời gian đã định dạng; người dịch có thể thay thứ tự từ trong câu mà không thay đổi quy tắc nghiệp vụ.

Các quy tắc quan trọng:

1. Giữ khóa nhất quán giữa các ngôn ngữ, kiểm tra khóa thiếu hoặc dư trong quá trình phát triển.
2. Cung cấp ngữ cảnh cho người dịch: “Order” có thể là danh từ “đơn hàng” hoặc động từ “đặt hàng”.
3. Không ghép câu từ các mảnh dịch rời rạc như “Bạn có ” + số + “ đơn hàng”; thứ tự từ và ngữ pháp có thể khác nhau. Dùng mẫu thông điệp hoàn chỉnh.
4. `MessageFormat` có quy tắc riêng đối với dấu nháy đơn và ngoặc nhọn. Trong pattern, muốn có một dấu nháy đơn literal thường phải viết hai dấu liên tiếp; đừng giả định template là phép nối chuỗi thông thường.
5. `ResourceBundle` có chuỗi tìm kiếm tài nguyên theo locale và có thể fallback sang bundle phù hợp khác hoặc mặc định. **Khóa không tồn tại** có thể gây `MissingResourceException`; đừng cho rằng Java luôn tự in tên khóa.
6. Với Java 17, các tệp resource bundle `.properties` được hỗ trợ đọc nội dung quốc tế theo UTF-8 (cơ chế mặc định từ Java 9). Lưu file đúng encoding; encoding hiển thị của terminal là một vấn đề riêng.

Tài nguyên bản địa hóa không nên chứa câu SQL, quy tắc tính thuế, biểu thức tính tổng tiền hay quyết định phân quyền. Nếu văn bản bản dịch có chứa HTML hoặc dữ liệu do người dùng tạo, lớp hiển thị vẫn phải escape/encode phù hợp với nơi xuất ra (HTML, JSON, v.v.); bản dịch không mặc nhiên là dữ liệu an toàn để chèn vào markup.

## 5. Giao diện kết hợp dữ liệu, tài nguyên và định dạng

**`Locale`** diễn tả các quy ước ngôn ngữ/khu vực; **`ZoneId`** xác định múi giờ; **`Currency`** biểu diễn đơn vị tiền. Ba khái niệm liên quan đến trải nghiệm người dùng nhưng không thay thế cho nhau.

Ví dụ chạy độc lập với **Java 17+**. Đặt ba file bên dưới **trong cùng một thư mục**.

**File `LocalizedOrderDemo.java`:**

~~~java
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

public class LocalizedOrderDemo {
    record Money(BigDecimal amount, Currency currency) {}
    record Order(String id, Money total, Instant placedAt) {}

    static String render(Order order, Locale locale, ZoneId zone) {
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);

        NumberFormat moneyFormat = NumberFormat.getCurrencyInstance(locale);
        Currency currency = order.total().currency();
        moneyFormat.setCurrency(currency);

        // setCurrency không bảo đảm tự cập nhật số chữ số phần thập phân.
        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            moneyFormat.setMinimumFractionDigits(digits);
            moneyFormat.setMaximumFractionDigits(digits);
        }
        String localizedAmount = moneyFormat.format(order.total().amount());

        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                        .withLocale(locale);
        String localizedTime =
                dateFormat.format(order.placedAt().atZone(zone));

        MessageFormat message =
                new MessageFormat(messages.getString("order.summary"), locale);
        return message.format(
                new Object[] {order.id(), localizedAmount, localizedTime});
    }

    public static void main(String[] args) {
        Order order = new Order(
                "A-17",
                new Money(
                        new BigDecimal("1234.50"),
                        Currency.getInstance("USD")),
                Instant.parse("2026-01-15T10:30:00Z"));

        ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("en-US -> " +
                render(order, Locale.US, displayZone));
        System.out.println("vi-VN -> " +
                render(order, Locale.forLanguageTag("vi-VN"), displayZone));
    }
}
~~~

**File `messages_en.properties`:**

~~~properties
order.summary=Order {0}: {1}; placed at {2}
~~~

**File `messages_vi.properties`:**

~~~properties
order.summary=Đơn hàng {0}: {1}; đặt lúc {2}
~~~

**Biên dịch và chạy** từ thư mục chứa ba file:

~~~bash
javac -encoding UTF-8 LocalizedOrderDemo.java
java LocalizedOrderDemo
~~~

Hai dòng kết quả lần lượt bắt đầu với **`en-US -> Order A-17:`** và **`vi-VN -> Đơn hàng A-17:`**. Cả hai hiển thị cùng mã đơn, cùng **1.234,50 USD về mặt giá trị** và cùng thời điểm `2026-01-15T10:30:00Z` được chuyển sang múi giờ `Asia/Ho_Chi_Minh`. Dấu phân cách số, ký hiệu/vị trí mã tiền và cách viết ngày giờ sẽ khác theo locale; chuỗi chính xác có thể khác giữa các phiên bản JDK/CLDR, nên không nên khẳng định nguyên văn toàn bộ stdout cho mọi môi trường.

Trong mã này, lớp domain chỉ giữ `Order`, `Money`, `Instant`. Hàm `render` là **ranh giới trình bày**: nhận lựa chọn locale/múi giờ, tìm thông điệp, format tiền và thời điểm. `ResourceBundle` chỉ giữ từ ngữ. `MessageFormat` sắp xếp các tham số vào câu; nếu cần quy tắc số nhiều, giống, cách chia hoặc bố cục phức tạp hơn, phải thiết kế giải pháp bản địa hóa phù hợp thay vì tự nối các chuỗi cố định.

## 6. Đầu vào và đầu ra: đặt bước chuyển đổi ở biên hệ thống

Một cấu trúc ứng dụng dễ kiểm soát là:

1. **Input adapter (UI/API):** nhận locale và timezone từ cấu hình người dùng hoặc request; phân giải về tập locale được hỗ trợ. Nếu nhập số/ngày dưới dạng văn bản có bản địa hóa, parse ở đây rồi kiểm tra toàn bộ chuỗi đã được tiêu thụ, định dạng hợp lệ và miền giá trị.
2. **Application/domain:** làm việc trên các giá trị chuẩn hóa. Không phải biết câu thông báo đang ở ngôn ngữ nào để tính tổng tiền, kiểm tra trạng thái hay lưu hóa đơn.
3. **Output adapter/presenter:** nhận kết quả có cấu trúc; tạo nhãn và thông báo từ bundle, định dạng thời gian/số và trả về UI.

Đối với **API dùng cho máy**, ưu tiên giữ dữ liệu có cấu trúc, chẳng hạn:

~~~json
{
  "id": "A-17",
  "amount": "1234.50",
  "currency": "USD",
  "placedAt": "2026-01-15T10:30:00Z",
  "status": "PAID"
}
~~~

Giao diện có thể nhận thêm các trường trình bày như `displayAmount` hoặc `displayStatus` khi cần, nhưng **không thay giá trị chuẩn** bằng chuỗi dịch. Client khác có thể tự hiển thị với locale khác mà không làm thay dữ liệu.

Một số điểm cần phân biệt:

- **Locale khác language:** cùng tiếng Anh, `en-US` và `en-GB` có quy ước khác; cùng ngôn ngữ không đồng nghĩa cùng múi giờ hay tiền tệ.
- **Locale khác time zone:** người dùng chọn tiếng Việt ở châu Âu vẫn có thể muốn giờ châu Âu. Thời gian làm việc theo lịch địa phương (ví dụ “9 giờ sáng mỗi thứ Hai”) cần mô hình riêng như `LocalTime` + `ZoneId`, không thể thay tùy tiện bằng một `Instant` không kèm ngữ nghĩa.
- **Locale khác encoding:** UTF-8 giữ ký tự Unicode khi lưu/chuyển dữ liệu; `Locale` quyết định quy ước hiển thị. Không dùng thao tác thay encoding để “dịch” văn bản.
- **Sắp xếp khác định danh:** danh sách tên người có thể dùng `Collator` phù hợp locale cho mục tiêu hiển thị. Định danh kỹ thuật, khóa map, URL slug và quy tắc so khớp nghiệp vụ cần tiêu chí ổn định riêng; không dùng mặc định cách so sánh chữ theo giao diện.
- **Quy tắc chữ hoa/thường:** với mã kỹ thuật không phụ thuộc ngôn ngữ, cân nhắc `Locale.ROOT` khi chuẩn hóa casing. Với văn bản tự nhiên của người dùng, cần xét đúng locale (ví dụ trường hợp chữ `i` trong tiếng Thổ Nhĩ Kỳ).

## 7. Lỗi thường gặp và cách sửa

| Lỗi thiết kế | Hệ quả | Cách sửa |
| --- | --- | --- |
| Domain trả thẳng “Đã thanh toán” | Đổi ngôn ngữ làm đổi giá trị điều kiện và contract | Domain trả mã `PAID`; presenter dịch nhãn |
| Lưu `"1.234,50"` thay vì số | Parse nhầm locale, phép tính sai | Parse ở input boundary, lưu `BigDecimal` |
| Dùng locale để suy ra đồng tiền | USD bị gắn nhãn VND nhưng không quy đổi | Gắn `Currency` với số tiền, quy đổi chỉ qua nghiệp vụ |
| Gọi `Locale.getDefault()` rải rác | Kết quả phụ thuộc máy chủ, test khó ổn định | Truyền locale tường minh tới presenter/formatter |
| Dùng `String.format` và nối nhãn rời rạc cho mọi câu | Ngữ pháp và thứ tự từ không chuyển dịch đúng | Dùng khóa và mẫu thông điệp hoàn chỉnh |
| Bỏ qua key resource thiếu hoặc placeholder sai | Lỗi runtime hoặc thông điệp vô nghĩa | Kiểm tra đồng bộ key, kiểm thử từng bundle |
| Định dạng thời gian mà không chọn múi giờ | Người dùng hiểu sai thời điểm | Domain giữ thời điểm; presenter nhận `ZoneId` |
| Format lại số thành chuỗi rồi tính toán tiếp | Mất độ chính xác, sai làm tròn | Tính toán trên giá trị gốc; format một lần lúc hiển thị |

Không giữ `NumberFormat` hoặc `MessageFormat` mutable làm singleton dùng đồng thời giữa nhiều luồng nếu không đồng bộ phù hợp; tạo formatter theo request hoặc quản lý riêng theo luồng. Ngược lại, `DateTimeFormatter` là immutable và thread-safe nên có thể tái sử dụng khi cấu hình đúng.

## 8. Kiểm thử ranh giới

Thay đổi locale là một phép thử kiến trúc hữu ích: **cùng dữ liệu đầu vào** được render ở ít nhất hai locale; chỉ các phần trình bày được phép thay đổi.

Kiểm tra theo ba lớp:

- **Domain:** tính toán và trạng thái vẫn đúng khi chạy dưới môi trường có default locale khác nhau. Test `Money` và `Order` bằng giá trị, không bằng câu đã dịch.
- **Resources:** các bundle có đủ khóa; mẫu `MessageFormat` parse được và dùng đúng số placeholder; ký tự có dấu xuất hiện đúng; fallback có chủ đích và được kiểm tra.
- **Presentation:** locale tiếng Việt/tiếng Anh cho câu và định dạng phù hợp; cùng `Currency` và `Instant` không đổi; timezone thay đổi giờ hiển thị mà không đổi thời điểm gốc. Với số, ngày và tên tiền tệ, kiểm thử cấu trúc/đặc tính quan trọng hoặc kiểm soát chặt phiên bản locale provider thay vì snapshot toàn bộ chuỗi CLDR trên mọi JDK.

Có thể thêm các ca biên: locale chưa hỗ trợ, thiếu resource key, giá trị âm, đơn vị tiền có 0 hoặc 3 chữ số lẻ, thời điểm sát chuyển giờ mùa hè, văn bản có dấu và ký tự Unicode kết hợp, và chuỗi nhập sai dấu phân cách. Với số và ngày do người dùng nhập, kiểm thử cả trường hợp parser chấp nhận một phần chuỗi rồi bỏ phần đuôi: đó không phải input hợp lệ nếu nghiệp vụ yêu cầu khớp toàn bộ.

## 9. Áp dụng vào dự án

Khi thêm một màn hình hoặc endpoint có nội dung đa ngôn ngữ, hãy tự đối chiếu:

1. Dữ liệu được lưu, tính và truyền giữa các lớp có còn đúng nếu người dùng đổi ngôn ngữ không?
2. Khóa và bản dịch có nằm trong tài nguyên thống nhất, có ngữ cảnh cho người dịch và fallback rõ ràng không?
3. Lớp nào đang quyết định `Locale`, `ZoneId` và quy tắc định dạng? Quyết định đó có được truyền rõ tới nơi render không?
4. Có chỗ nào dùng văn bản đã dịch để so sánh trạng thái, làm phép tính, lập khóa dữ liệu hoặc suy ra tiền tệ không?
5. Khi thêm locale mới, phần lớn thay đổi có tập trung ở resource và presenter, thay vì phải sửa business logic không?

Một thiết kế đạt mục tiêu khi có thể giữ nguyên **đơn hàng và quy tắc nghiệp vụ**, bổ sung một bundle ngôn ngữ mới và điều chỉnh lớp trình bày mà không phải viết lại cách xử lý dữ liệu.
