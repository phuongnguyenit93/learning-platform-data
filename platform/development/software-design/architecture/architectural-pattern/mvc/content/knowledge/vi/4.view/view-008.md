# Định dạng ngày giờ, số và nội dung theo ngôn ngữ

Trong ứng dụng MVC, View có trách nhiệm trình bày dữ liệu sao cho người dùng dễ hiểu trong ngôn ngữ và quy ước vùng của họ. Cùng một giá trị có thể được hiển thị theo nhiều cách: ngày 4 tháng 5 có thể viết là `04/05/2026` hoặc `05/04/2026`; số một nghìn rưỡi có thể dùng dấu chấm hoặc dấu phẩy để phân tách phần thập phân; tiền tệ cần có mã và cách hiển thị phù hợp; thông báo lỗi cần được diễn đạt bằng ngôn ngữ người dùng chọn.

Để làm đúng, ứng dụng cần phân biệt dữ liệu gốc với cách trình bày. Ngày giờ, số lượng và số tiền nên được lưu, truyền và xử lý bằng kiểu dữ liệu có ý nghĩa rõ ràng. View mới chuyển chúng thành chuỗi theo `Locale`, múi giờ và bộ thông điệp phù hợp. Nếu lưu chuỗi đã định dạng làm dữ liệu nghiệp vụ, ứng dụng dễ gặp lỗi khi đổi ngôn ngữ, tổng hợp, sắp xếp hoặc nhận dữ liệu từ một vùng khác.

## 1. Phân biệt ngôn ngữ, vùng và múi giờ

Ba khái niệm này liên quan nhưng không đồng nghĩa:

- **Ngôn ngữ (language)** xác định ngôn ngữ của nhãn, tiêu đề, hướng dẫn và thông báo. Ví dụ: tiếng Việt (`vi`), tiếng Anh (`en`).
- **Locale** biểu diễn ngôn ngữ cùng quy ước vùng, thường gồm mã ngôn ngữ và vùng. Ví dụ: `vi-VN`, `en-US`, `en-GB`. Locale ảnh hưởng cách định dạng ngày, số, tiền tệ và quy tắc sắp xếp.
- **Múi giờ (time zone)** xác định cách chuyển một thời điểm tuyệt đối thành giờ địa phương. Ví dụ: `Asia/Ho_Chi_Minh`, `Europe/London`. Múi giờ có quy tắc lịch sử và giờ mùa hè riêng.

Không nên suy ra múi giờ chỉ từ Locale. Hai người cùng dùng `en-US` có thể sống ở các múi giờ khác nhau. Ngược lại, hai người ở cùng múi giờ có thể chọn ngôn ngữ giao diện khác nhau.

Trong Java, có thể biểu diễn Locale và múi giờ như sau:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale britishEnglish = Locale.forLanguageTag("en-GB");

ZoneId hoChiMinh = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId london = ZoneId.of("Europe/London");
```

Nên dùng mã ngôn ngữ/vùng chuẩn và mã múi giờ IANA. Tránh tự tạo quy tắc như “Việt Nam luôn UTC+7” trong mã xử lý; dùng `ZoneId` để thư viện thời gian áp dụng quy tắc phù hợp.

## 2. Chọn và truyền ngữ cảnh Locale trong MVC

Một ứng dụng có thể xác định Locale theo thứ tự ưu tiên do sản phẩm quy định. Một cách phổ biến là:

1. Ưu tiên lựa chọn ngôn ngữ người dùng đã lưu trong hồ sơ.
2. Nếu chưa có, xem xét ngôn ngữ trình duyệt gửi qua header `Accept-Language`.
3. Nếu không xác định được ngôn ngữ phù hợp, dùng Locale mặc định của ứng dụng.

Với một số sản phẩm, người dùng có thể chọn ngôn ngữ ngay trên URL hoặc tham số request. Cần quy định rõ nguồn nào có ưu tiên cao nhất và kiểm tra giá trị đó nằm trong danh sách Locale được hỗ trợ. Không nên để một tham số tùy ý làm thay đổi cấu hình toàn hệ thống.

Trong MVC:

- **Controller hoặc middleware** xác định Locale và múi giờ của request từ hồ sơ người dùng, cấu hình ứng dụng hoặc header được hỗ trợ.
- **Service và Model** xử lý dữ liệu nghiệp vụ bằng kiểu dữ liệu chuẩn, không phụ thuộc chuỗi hiển thị của View.
- **View** nhận Locale và múi giờ để định dạng giá trị, chọn bộ thông điệp và trình bày nội dung.
- **Hợp đồng API** cần xác định rõ dữ liệu nào dùng định dạng máy đọc được và dữ liệu nào là chuỗi đã bản địa hóa dành cho người dùng.

Không nên lưu Locale hiện tại vào một biến static có thể thay đổi giữa các request. Máy chủ xử lý nhiều người dùng đồng thời; mỗi request có thể có ngôn ngữ và múi giờ riêng. Hãy truyền ngữ cảnh tường minh hoặc dùng cơ chế request-scoped của framework.

## 3. Định dạng ngày và thời gian

### 3.1. Chọn đúng kiểu dữ liệu trước khi định dạng

Java cung cấp các kiểu trong `java.time` để thể hiện những khái niệm thời gian khác nhau:

| Kiểu | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| `LocalDate` | Ngày trên lịch, không có giờ và múi giờ | Ngày sinh, ngày nghỉ phép |
| `LocalTime` | Giờ trên đồng hồ, không có ngày và múi giờ | Giờ mở cửa hằng ngày |
| `LocalDateTime` | Ngày và giờ địa phương, chưa gắn múi giờ | Giờ hẹn cần được hiểu trong một vùng đã biết |
| `Instant` | Một thời điểm tuyệt đối trên dòng thời gian | Thời điểm tạo bản ghi, thời điểm thanh toán |
| `ZonedDateTime` | Ngày giờ cùng múi giờ cụ thể | Lịch họp tại một thành phố |

Chọn sai kiểu có thể tạo lỗi khó nhận ra. Ví dụ, ngày sinh là một ngày lịch nên thường dùng `LocalDate`; nếu chuyển nó thành `Instant` rồi đổi múi giờ, ngày có thể bị lùi hoặc tiến ngoài ý muốn. Ngược lại, thời điểm một giao dịch xảy ra cần biểu diễn được một thời điểm tuyệt đối, nên `Instant` phù hợp hơn.

### 3.2. Lưu thời điểm và hiển thị theo múi giờ người dùng

Một thời điểm có thể được lưu dưới dạng `Instant` (thường ghi vào cơ sở dữ liệu theo UTC), sau đó chuyển sang múi giờ của người xem để trình bày:

```java
Instant createdAt = Instant.parse("2026-11-19T08:30:00Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localDateTime =
    createdAt.atZone(userZone);
```

Khi hiển thị, ứng dụng định dạng `localDateTime` theo Locale. Ví dụ dùng API định dạng ngày giờ theo quy ước vùng:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime value =
    Instant.now().atZone(zone);

DateTimeFormatter formatter =
    DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(locale);

String displayText = formatter.format(value);
```

Các kiểu `DateTimeFormatter` trong `java.time` là immutable và thread-safe, nên có thể tái sử dụng khi cấu hình cố định. Với ngày không có giờ, dùng `ofLocalizedDate`; với giờ, dùng `ofLocalizedTime`.

### 3.3. Khi nào dùng định dạng cố định?

Định dạng theo Locale phù hợp cho giao diện đọc bởi con người. Trong API, log kỹ thuật, tệp trao đổi hoặc dữ liệu cần xử lý tự động, nên dùng định dạng chuẩn có quy ước rõ ràng, chẳng hạn ISO 8601.

Ví dụ:

- API trả ngày lịch: `2026-11-19`.
- API trả thời điểm: `2026-11-19T08:30:00Z`.
- View tiếng Việt hiển thị ngày theo lựa chọn Locale.
- View của người dùng ở múi giờ khác chuyển thời điểm sang múi giờ đó trước khi hiển thị.

Không nên thay đổi định dạng API từ ISO sang `19/11/2026` chỉ vì người dùng chọn tiếng Việt. Chuỗi bản địa hóa có thể mơ hồ và khó phân tích bằng máy.

Nếu nghiệp vụ yêu cầu mẫu cố định, có thể dùng `DateTimeFormatter.ofPattern`, nhưng cần quy định rõ mẫu và Locale:

```java
DateTimeFormatter reportDate =
    DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);

String text = reportDate.format(LocalDate.of(2026, 11, 19));
```

Mẫu cố định nên được chọn theo yêu cầu nghiệp vụ hoặc định dạng tài liệu, không nên tự dùng một mẫu cho mọi ngôn ngữ. Khi có thể, ưu tiên các kiểu định dạng được thư viện cung cấp theo Locale.

### 3.4. Xử lý biểu mẫu ngày giờ

Khi người dùng nhập ngày, ứng dụng cần biết biểu mẫu gửi lên theo hợp đồng nào. Ví dụ, trường HTML `<input type="date">` thường gửi giá trị ngày theo dạng ISO `yyyy-MM-dd`, dù trình duyệt có thể hiển thị giao diện nhập theo vùng của người dùng.

Một trường `datetime-local` gửi ngày giờ địa phương nhưng không kèm múi giờ. Nếu người dùng đặt lịch họp, ứng dụng cần biết múi giờ áp dụng, chẳng hạn từ hồ sơ hoặc lựa chọn địa điểm. Không được tự hiểu giá trị đó theo múi giờ của máy chủ.

Cần kiểm tra dữ liệu nhập có hợp lệ và tồn tại trong múi giờ đó. Một số thời điểm địa phương có thể không tồn tại hoặc xuất hiện hai lần khi khu vực chuyển sang/ra khỏi giờ mùa hè. Với các trường hợp này, ứng dụng nên có quy tắc rõ ràng hoặc yêu cầu người dùng xác nhận múi giờ/thời điểm.

## 4. Định dạng số và phần trăm

### 4.1. Dùng NumberFormat theo Locale

Các vùng khác nhau có thể dùng dấu phân tách hàng nghìn và dấu thập phân khác nhau. Không nên nối chuỗi thủ công hoặc thay dấu chấm bằng dấu phẩy bằng phép thay thế ký tự.

Java cung cấp `NumberFormat`:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale usEnglish = Locale.forLanguageTag("en-US");

NumberFormat viNumber =
    NumberFormat.getNumberInstance(vietnamese);
NumberFormat usNumber =
    NumberFormat.getNumberInstance(usEnglish);

String viText = viNumber.format(1234567.89);
String usText = usNumber.format(1234567.89);
```

Kết quả cụ thể phụ thuộc dữ liệu Locale của môi trường Java, nhưng hai chuỗi có thể khác dấu phân tách nhóm và dấu thập phân. Nếu giao diện cần số chữ số thập phân cố định, có thể cấu hình `setMinimumFractionDigits` và `setMaximumFractionDigits` theo yêu cầu hiển thị.

### 4.2. Định dạng phần trăm

Phần trăm cần phân biệt giá trị lưu và giá trị trình bày. Ví dụ, tỷ lệ `0.125` có thể được hiển thị là `12,5%` tùy Locale. Khi dùng `NumberFormat.getPercentInstance(locale)`, thư viện hiểu giá trị `0.125` là 12,5 phần trăm và tự nhân 100 khi định dạng.

```java
NumberFormat percent =
    NumberFormat.getPercentInstance(
        Locale.forLanguageTag("vi-VN")
    );

percent.setMinimumFractionDigits(1);
percent.setMaximumFractionDigits(1);

String text = percent.format(0.125);
```

Nếu dữ liệu nguồn đã là 12.5 thay vì 0.125, không truyền trực tiếp vào formatter phần trăm vì kết quả sẽ bị nhân thêm 100 lần. Hợp đồng dữ liệu cần nói rõ tỷ lệ được lưu dưới dạng phân số hay số phần trăm.

### 4.3. Phân tích số người dùng nhập

Khi đọc số từ biểu mẫu, hãy dùng Locale tương ứng với cách người dùng được hướng dẫn nhập. Ví dụ `1.234,56` và `1,234.56` có thể mang cùng ý nghĩa số học trong hai quy ước vùng khác nhau.

```java
DecimalFormat numberFormat =
    (DecimalFormat) NumberFormat.getNumberInstance(locale);
numberFormat.setParseBigDecimal(true);

ParsePosition position = new ParsePosition(0);
BigDecimal value = (BigDecimal) numberFormat.parse(
    input.trim(), position
);

if (value == null || position.getIndex() != input.trim().length()) {
    throw new IllegalArgumentException("Invalid number");
}
```

Đoạn mã cấu hình parser để trả về `BigDecimal`, tránh chuyển qua `double` làm mất độ chính xác, đồng thời kiểm tra toàn bộ chuỗi đã được phân tích. API `NumberFormat.parse` có thể chấp nhận một phần chuỗi nếu không kiểm tra vị trí kết thúc, vì vậy không nên mặc định rằng chuỗi có phần dư là hợp lệ.

Không dùng `double` để lưu hoặc tính toán tiền. Kiểu dấu phẩy động nhị phân có thể tạo sai số biểu diễn. Dùng `BigDecimal` với quy tắc scale và rounding được nghiệp vụ xác định.

## 5. Định dạng tiền tệ

Tiền tệ gồm cả số tiền và đơn vị tiền tệ. Con số `100` không cho biết đó là 100 VND, 100 USD hay 100 EUR. Vì vậy, Model nên lưu số tiền cùng mã tiền tệ, thường theo chuẩn ISO 4217, thay vì chỉ lưu một chuỗi có ký hiệu.

Ví dụ Java:

```java
BigDecimal amount = new BigDecimal("1234567.50");
Currency currency = Currency.getInstance("VND");

NumberFormat moneyFormat =
    NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("vi-VN")
    );

moneyFormat.setCurrency(currency);
String displayText = moneyFormat.format(amount);
```

Locale ảnh hưởng cách đặt ký hiệu, khoảng trắng và dấu phân tách. Currency xác định đơn vị tiền. Đặt Currency cho formatter không thay thế quy tắc nghiệp vụ về số chữ số thập phân hoặc làm tròn.

Với tiền, cần xác định rõ:

- Mã tiền tệ của giao dịch.
- Độ chính xác được phép lưu và tính toán.
- Quy tắc làm tròn cho từng nghiệp vụ.
- Cách hiển thị số lẻ và ký hiệu tiền theo Locale.
- Có cho phép người dùng chọn tiền tệ khác với tiền tệ mặc định hay không.

Không suy ra mã tiền chỉ từ Locale. Người dùng ở Việt Nam có thể xem giá bằng USD; người dùng dùng `en-US` có thể giao dịch bằng EUR. Locale là quy ước trình bày, còn mã tiền là dữ liệu nghiệp vụ.

## 6. Nội dung và thông điệp theo ngôn ngữ

### 6.1. Tách thông điệp khỏi mã nguồn

Không viết trực tiếp câu chữ của giao diện trong Controller hoặc View nếu ứng dụng cần hỗ trợ nhiều ngôn ngữ. Thay vào đó, dùng khóa thông điệp và bộ tài nguyên theo Locale.

Ví dụ các tệp tài nguyên:

```text
messages_vi.properties
task.created=Đã tạo công việc.
validation.required=Vui lòng nhập trường này.

messages_en.properties
task.created=Task created.
validation.required=Please enter this field.
```

Trong Java, có thể dùng `ResourceBundle`:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle messages =
    ResourceBundle.getBundle("messages", locale);

String successMessage = messages.getString("task.created");
```

Framework web thường có cơ chế message source riêng và tích hợp Locale theo request. Nên dùng cơ chế thống nhất của framework để hỗ trợ fallback, cache và kiểm thử.

### 6.2. Thông điệp có tham số

Thông báo có thể cần chèn tên, số lượng hoặc ngày tháng. Không nên nối câu bằng nhiều mảnh chuỗi nếu ngữ pháp thay đổi theo ngôn ngữ.

Ví dụ với `MessageFormat`:

```java
String pattern = "Xin chào, {0}. Bạn có {1} thông báo mới.";
String message = new MessageFormat(pattern, locale)
    .format(new Object[] {"An", 3});
```

Cấu trúc câu và vị trí tham số nên nằm trong bộ tài nguyên của từng ngôn ngữ để người dịch có thể sắp xếp lại. Với quy tắc số nhiều, giống, cách xưng hô hoặc cấu trúc câu phức tạp, nên dùng thư viện hỗ trợ ICU MessageFormat hoặc giải pháp i18n tương đương; `MessageFormat` cơ bản không cung cấp đầy đủ quy tắc số nhiều của mọi ngôn ngữ.

Giá trị động phải được escape theo ngữ cảnh khi đưa vào HTML. `MessageFormat` chỉ thay tham số vào mẫu, không tự bảo vệ nội dung khỏi XSS.

### 6.3. Nội dung do người dùng tạo và nội dung biên tập

Không phải mọi nội dung đều cần dịch tự động. Cần phân biệt:

- **Nhãn và thông báo hệ thống:** được quản lý bằng bộ tài nguyên dịch.
- **Nội dung biên tập:** có thể có phiên bản theo từng ngôn ngữ, ví dụ mô tả khóa học hoặc bài viết.
- **Nội dung người dùng nhập:** thường giữ nguyên ngôn ngữ gốc; nếu có bản dịch thì lưu như một nội dung riêng và thể hiện rõ nguồn.
- **Dữ liệu định danh và mã nghiệp vụ:** giữ ổn định, không dịch, ví dụ mã đơn hàng, trạng thái máy đọc được và khóa API.

Nếu một bản dịch nội dung biên tập chưa có, ứng dụng có thể dùng ngôn ngữ dự phòng theo chính sách sản phẩm. Nên thông báo rõ hoặc ghi nhận Locale thực tế của nội dung để người dùng không nhầm bản dịch dự phòng với bản gốc.

### 6.4. Ngôn ngữ trong HTML và khả năng tiếp cận

View nên khai báo ngôn ngữ tài liệu bằng thuộc tính `lang`, chẳng hạn:

```html
<html lang="vi">
```

Với ngôn ngữ viết từ phải sang trái, cần xử lý hướng văn bản bằng thuộc tính `dir` và tránh giả định mọi nội dung đều theo chiều trái sang phải. Ngôn ngữ và hướng hiển thị ảnh hưởng trình đọc màn hình, cách đọc nội dung và bố cục giao diện.

## 7. Hợp đồng dữ liệu giữa Controller, Model và View

Một nguyên tắc quan trọng là dữ liệu trao đổi nội bộ và dữ liệu trình bày có mục đích khác nhau.

Ví dụ, API có thể trả:

```json
{
  "createdAt": "2026-11-19T08:30:00Z",
  "total": "1234567.50",
  "currency": "VND"
}
```

Đây là ví dụ hợp đồng minh họa. Với tiền, dùng chuỗi thập phân trong JSON giúp tránh việc client chuyển số sang kiểu dấu phẩy động có thể mất độ chính xác. API cần công bố rõ quy ước cho từng trường.

View nhận thời điểm, số tiền và Locale, sau đó định dạng để hiển thị. Nếu API phục vụ trực tiếp một giao diện cụ thể, có thể cung cấp thêm trường hiển thị như `formattedTotal`, nhưng trường đó không nên trở thành nguồn dữ liệu để tính toán hoặc lưu ngược lại.

Không nên:

- Lưu `"19/11/2026"` làm ngày nghiệp vụ rồi phân tích lại khi cần truy vấn.
- Lưu `"1.234,56"` làm số lượng rồi dùng chuỗi đó để cộng trừ.
- Lưu `"1.234.567 ₫"` làm giá trị tiền duy nhất.
- Dùng bản dịch như `"Đã duyệt"` làm mã trạng thái trong cơ sở dữ liệu.

Hãy lưu giá trị có kiểu và mã ổn định; chỉ tạo chuỗi hiển thị ở ranh giới trình bày.

## 8. Ví dụ: hiển thị chi tiết đơn hàng theo Locale

Giả sử hệ thống lưu thời điểm tạo đơn dưới dạng `Instant`, tổng tiền dưới dạng `BigDecimal` và mã tiền tệ riêng. Controller chuẩn bị dữ liệu cho View cùng Locale và múi giờ của người dùng:

```java
public record OrderViewModel(
    String orderNumber,
    String createdAtText,
    String totalText,
    String statusText
) {}

public OrderViewModel toViewModel(
        Order order,
        Locale locale,
        ZoneId userZone,
        ResourceBundle messages) {

    DateTimeFormatter dateFormatter =
        DateTimeFormatter
            .ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale);

    String createdAtText = dateFormatter.format(
        order.getCreatedAt().atZone(userZone)
    );

    NumberFormat currencyFormat =
        NumberFormat.getCurrencyInstance(locale);
    currencyFormat.setCurrency(
        Currency.getInstance(order.getCurrencyCode())
    );

    String totalText =
        currencyFormat.format(order.getTotal());

    String statusText = messages.getString(
        "order.status." + order.getStatus().name()
    );

    return new OrderViewModel(
        order.getOrderNumber(),
        createdAtText,
        totalText,
        statusText
    );
}
```

Đoạn mã tập trung minh họa việc chuyển dữ liệu nghiệp vụ thành dữ liệu trình bày. Trong ứng dụng thực tế, việc lấy message bundle, xử lý trường hợp thiếu khóa, chọn formatter và xây dựng ViewModel thường được đóng gói trong thành phần chuyên trách hoặc cơ chế i18n của framework.

Điểm cần giữ là:

- `Order` vẫn chứa dữ liệu có kiểu và trạng thái ổn định.
- Locale quyết định quy ước định dạng và ngôn ngữ thông điệp.
- ZoneId quyết định giờ địa phương của người xem.
- ViewModel chứa chuỗi dành cho hiển thị, không được dùng làm nguồn tính toán ngược.

## 9. Những lỗi thường gặp

### Dùng Locale mặc định của máy chủ

Máy chủ có thể chạy trong container hoặc khu vực khác với người dùng. Nếu dùng `Locale.getDefault()` ở mọi nơi, giao diện có thể đổi cách định dạng sau khi triển khai sang môi trường khác. Hãy xác định Locale theo request hoặc hồ sơ người dùng.

### Dùng múi giờ mặc định của máy chủ

Thời điểm có thể hiển thị sai giờ khi ứng dụng chuyển vùng triển khai. Lưu thời điểm tuyệt đối, xác định múi giờ hiển thị và chuyển đổi rõ ràng.

### Nhầm Locale với Currency

Locale `en-US` không có nghĩa mọi số tiền đều là USD. Lưu mã tiền tệ cùng số tiền và chọn formatter theo cả Locale lẫn Currency.

### Định dạng rồi phân tích lại để tính toán

Chuỗi hiển thị dành cho con người có thể chứa ký hiệu, dấu phân cách hoặc từ ngữ. Không dùng chuỗi này làm dữ liệu đầu vào cho phép tính hoặc truy vấn. Giữ dữ liệu có kiểu xuyên suốt tầng nghiệp vụ.

### Chỉ kiểm thử một ngôn ngữ

Một màn hình có thể trông đúng với `vi-VN` nhưng vỡ bố cục với bản dịch dài hơn, số lớn hoặc ngôn ngữ viết từ phải sang trái. Cần kiểm thử nhiều Locale và dữ liệu biên.

### Nối chuỗi thông báo theo ngữ pháp của một ngôn ngữ

Câu được ghép từ các mảnh cố định có thể sai thứ tự hoặc sai số nhiều trong ngôn ngữ khác. Đưa toàn bộ mẫu câu vào tài nguyên dịch và dùng định dạng thông điệp phù hợp.

### Chia sẻ formatter không an toàn giữa các request

Các lớp `java.text.NumberFormat` và `DecimalFormat` không thread-safe. Không dùng chung một instance có thể bị thay đổi đồng thời giữa nhiều request. Tạo instance theo request hoặc dùng cơ chế an toàn theo framework. `DateTimeFormatter` thuộc `java.time` thì immutable và thread-safe.

### Tin dữ liệu định dạng từ client

Locale và múi giờ do người dùng chọn có thể ảnh hưởng cách hiển thị, nhưng không được dùng để xác định quyền truy cập hoặc bỏ qua xác thực. Dữ liệu đầu vào vẫn phải được kiểm tra theo hợp đồng và quy tắc nghiệp vụ.

## 10. Kiểm thử định dạng theo ngôn ngữ

Nên kiểm thử cả dữ liệu và cách hiển thị. Một ma trận kiểm thử có thể gồm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| `vi-VN` và `en-US` | Dấu thập phân, phân tách nhóm và thứ tự ngày phù hợp |
| Ngày cuối tháng, năm nhuận | Không sai lệch ngày khi parse/format |
| `Instant` ở hai múi giờ | Cùng một thời điểm nhưng giờ hiển thị khác theo ZoneId |
| Thời điểm gần chuyển giờ mùa hè | Xử lý rõ thời điểm thiếu hoặc lặp ở múi giờ có DST |
| Số tiền lớn và số thập phân | Không mất độ chính xác; quy tắc làm tròn đúng |
| Mã tiền khác Locale | Ký hiệu tiền phản ánh mã tiền của giao dịch |
| Thông điệp có tham số | Thứ tự, dấu câu và nội dung đúng với từng ngôn ngữ |
| Thiếu bản dịch | Fallback đúng chính sách và không làm lộ khóa nội bộ |
| Nội dung dài hoặc RTL | Bố cục, hướng văn bản và khả năng đọc vẫn phù hợp |
| Dữ liệu nhập không hợp lệ | Parser từ chối chuỗi sai hoặc còn phần dư ngoài dự kiến |

Với kiểm thử tự động, nên truyền Locale và ZoneId tường minh thay vì phụ thuộc cấu hình mặc định của máy chạy test. Có thể kiểm tra giá trị định dạng chính xác theo JDK và dữ liệu Locale của môi trường được hỗ trợ; với giao diện, cần thêm kiểm thử hiển thị để phát hiện tràn, cắt chữ hoặc sai hướng văn bản.

## 11. Checklist khi xây dựng View đa ngôn ngữ

Trước khi hoàn thiện một màn hình, hãy xác nhận:

1. Locale được xác định theo chính sách rõ ràng và nằm trong danh sách được hỗ trợ.
2. Múi giờ được xác định riêng, không suy ra chỉ từ ngôn ngữ.
3. Ngày, giờ, thời điểm, số lượng và tiền tệ dùng kiểu dữ liệu phù hợp.
4. Dữ liệu lưu trữ và API giữ định dạng ổn định, có thể đọc bằng máy.
5. View định dạng ngày giờ, số và tiền theo Locale cùng ZoneId.
6. Nội dung hệ thống dùng bộ tài nguyên dịch; nội dung người dùng được giữ đúng nguồn gốc.
7. Thông điệp có tham số hỗ trợ thứ tự và quy tắc ngữ pháp của từng ngôn ngữ.
8. HTML khai báo ngôn ngữ và hướng văn bản phù hợp.
9. Dữ liệu động được escape theo ngữ cảnh khi hiển thị.
10. Có kiểm thử cho nhiều Locale, múi giờ, dữ liệu biên và trường hợp thiếu bản dịch.

## Kết luận

Định dạng ngày giờ, số và nội dung theo ngôn ngữ là trách nhiệm trình bày quan trọng của View trong MVC. Ứng dụng cần giữ dữ liệu nghiệp vụ ở dạng có kiểu và ổn định, xác định Locale cùng múi giờ theo từng người dùng, rồi định dạng ở ranh giới hiển thị. Khi Controller truyền đúng ngữ cảnh, Model không phụ thuộc chuỗi bản địa hóa và View sử dụng tài nguyên dịch cùng formatter phù hợp, ứng dụng có thể phục vụ nhiều vùng ngôn ngữ mà vẫn bảo toàn tính chính xác của dữ liệu và hợp đồng API.

