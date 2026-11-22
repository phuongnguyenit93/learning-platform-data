# Dữ liệu trung lập với locale và cách trình bày cho người dùng trong Java

## 1. Vấn đề cần giải quyết

Cùng một đơn hàng có thể được xem bởi người dùng nói tiếng Việt tại Việt Nam, người dùng tiếng Anh tại Hoa Kỳ hoặc nhân viên hỗ trợ tại Nhật Bản. **Giá trị nghiệp vụ của đơn hàng phải nhất quán**, trong khi chuỗi hiển thị có thể khác theo ngôn ngữ, khu vực và múi giờ.

Ví dụ một giá trị số tiền thực là `1234567.50`, đơn vị `USD`, và thời điểm là `2026-10-28T07:30:00Z`:

- Người dùng `vi-VN` có thể nhìn thấy số với dấu chấm phân nhóm và dấu phẩy thập phân; các nhãn như “Tổng tiền” bằng tiếng Việt.
- Người dùng `en-US` có thể nhìn thấy số với dấu phẩy phân nhóm và dấu chấm thập phân; các nhãn như “Total”.
- Hai người vẫn đang xem **cùng một số tiền và cùng một thời điểm**, chứ không phải hai bản ghi nghiệp vụ khác nhau.

Thiết kế đúng là tách **dữ liệu trung lập với locale (locale-neutral data)** khỏi **cách diễn đạt dành cho người dùng (localized presentation)**. Cần hiểu thêm rằng không phải mọi loại dữ liệu đều nên ép thành UTC hay chỉ còn một con số: một ngày trên lịch, một thời điểm tuyệt đối, một số tiền có đơn vị và một lịch hẹn lặp lại có ngữ nghĩa riêng.

### Mục tiêu của bài

Sau bài này, bạn có thể chọn kiểu Java phù hợp với dữ liệu gốc; lưu và truyền dữ liệu theo hợp đồng ổn định; dùng `Locale`, `ZoneId`, formatter và tài nguyên dịch ở ranh giới trình bày; xử lý đầu vào theo locale mà không đưa chuỗi hiển thị vào dữ liệu nghiệp vụ; và nhận diện lỗi thường gặp.

## 2. Phân biệt giá trị gốc và cách hiển thị

**Dữ liệu trung lập** diễn tả *giá trị có ý nghĩa gì* mà không phụ thuộc dấu phân cách, tên tháng hoặc ngôn ngữ thông báo. **Bản trình bày** diễn tả *người dùng cần nhìn giá trị đó như thế nào*. Cần chọn kiểu gốc dựa vào nghiệp vụ trước, rồi mới chọn formatter.

| Dữ liệu | Dạng gốc / kiểu Java phù hợp | Cách hiển thị có thể thay đổi |
| --- | --- | --- |
| Số lượng nguyên | `long` / `BigInteger` | Phân nhóm chữ số theo locale |
| Số thập phân chính xác | `BigDecimal` | Dấu thập phân, dấu phân nhóm, số chữ số |
| Tiền | `BigDecimal` **cùng** `Currency` / mã ISO 4217 | Ký hiệu tiền, vị trí ký hiệu, phân nhóm; *không tự đổi tiền* |
| Ngày trên lịch | `LocalDate` | Thứ tự ngày/tháng/năm, tên tháng |
| Thời điểm tuyệt đối | `Instant` | Giờ địa phương sau khi chọn `ZoneId` |
| Lịch hẹn theo giờ địa phương | `LocalDateTime` **cùng** múi giờ/quy tắc nghiệp vụ | Quy đổi ra thời điểm thực có xét DST khi cần |
| Dữ liệu phân loại | Mã ổn định như `PAID` / `PENDING` | Nhãn “Đã thanh toán” / “Paid” |
| Thông điệp | Khóa thông điệp và các tham số | Mẫu dịch từ `ResourceBundle` hoặc hệ thống i18n |
| Định danh | Mã hoặc UUID có quy tắc riêng | Thông thường giữ nguyên |

Định dạng không thay đổi giá trị. Ví dụ `1.234,50` và `1,234.50` có thể cùng chỉ số một nghìn hai trăm ba mươi tư phẩy năm; nhưng *không thể đoán chắc* từ chuỗi đơn lẻ nếu thiếu locale và quy tắc nhập. Do đó, **không lưu chuỗi đã format như nguồn chân lý của phép tính**.

Mô hình luồng dữ liệu:

```text
                  DỮ LIỆU NGHIỆP VỤ
BigDecimal + currency | LocalDate | Instant | status code
                        │
              lưu DB / gửi API
               dạng ổn định, rõ kiểu
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
  Người dùng vi-VN               Người dùng en-US
  ngôn ngữ: vi                   ngôn ngữ: en
  ZoneId: Asia/Ho_Chi_Minh       ZoneId: America/New_York
         │                             │
  NumberFormat,                    NumberFormat,
  DateTimeFormatter,               DateTimeFormatter,
  ResourceBundle                   ResourceBundle
         │                             │
  Chuỗi giao diện A               Chuỗi giao diện B
         └──────── cùng dữ liệu ───────┘
```

`Locale` mô tả ngôn ngữ và các quy ước vùng. `ZoneId` là lựa chọn **riêng** về múi giờ. `Currency` mô tả đơn vị tiền; bản thân nó không cho biết tỷ giá. Người dùng dùng tiếng Việt vẫn có thể giao dịch bằng USD và chọn múi giờ Tokyo.

## 3. Chọn kiểu dữ liệu gốc dựa vào ý nghĩa nghiệp vụ

### 3.1. Số, số đo và tiền

Với tiền hoặc số thập phân yêu cầu chính xác theo hệ thập phân, thường dùng `BigDecimal` thay vì `double`:

```java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal subtotal = price.multiply(quantity); // 59.70
```

Khởi tạo bằng chuỗi biểu diễn giá trị thập phân định sẵn, tránh `new BigDecimal(0.1)` vì `0.1` dạng `double` không biểu diễn chính xác trong nhị phân. `BigDecimal.valueOf(0.1)` có hành vi khác và thường phù hợp hơn nếu bắt buộc bắt đầu từ `double`, nhưng với giá trị nghiệp vụ có nguồn thập phân chuẩn, ưu tiên nhận/giữ dạng thập phân ngay từ đầu.

Không chỉ lưu `amount=19.90` rồi đoán đồng tiền từ locale. Lưu cả `currency=USD` (hoặc mã tiền khác) nếu đó là giao dịch tiền tệ. **Định dạng USD cho người dùng `vi-VN` không đồng nghĩa đổi USD thành VND.** Chuyển đổi tiền tệ đòi hỏi tỷ giá, thời điểm hiệu lực và quy tắc làm tròn độc lập.

`BigDecimal` cũng chứa `scale`: `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có cùng giá trị toán học nhưng khác scale; `equals` coi chúng khác, `compareTo` trả 0. Quy định precision, scale, làm tròn và so sánh ngay tại tầng nghiệp vụ. Formatter có thể làm tròn chuỗi hiển thị; điều đó **không thay thế bước làm tròn nghiệp vụ**.

### 3.2. Ngày, giờ và múi giờ

Java `java.time` có các kiểu biểu diễn những ý nghĩa khác nhau:

- `LocalDate`: ngày trên lịch, ví dụ ngày sinh hoặc hạn thanh toán `2026-10-28`; **không có giờ, offset hoặc múi giờ**. Không tự chuyển một `LocalDate` sang UTC.
- `Instant`: thời điểm tuyệt đối trên dòng thời gian, ví dụ lúc tạo đơn hàng `2026-10-28T07:30:00Z`. Hiển thị theo múi giờ cần một `ZoneId`.
- `LocalDateTime`: ngày và giờ trên đồng hồ địa phương **chưa gắn múi giờ**. Chưa xác định duy nhất một thời điểm tuyệt đối; khi múi giờ có DST, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần.
- `ZonedDateTime`: ngày/giờ gắn vùng múi giờ và quy tắc của vùng; hữu ích khi nghiệp vụ gắn với giờ địa phương của địa điểm.
- `OffsetDateTime`: ngày/giờ với offset cố định, chẳng hạn `+07:00`; offset không thay thế đầy đủ múi giờ IANA như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`, nhất là lịch hẹn tương lai.
- `ZoneId`: định danh múi giờ; không phải một thành phần mặc định của `Locale`.

**Phân biệt hai câu hỏi:** “Đơn hàng tạo lúc nào?” → `Instant`. “Hạn trả trước ngày nào?” → `LocalDate`. “Chi nhánh mở cửa lúc 09:00 hằng ngày theo giờ Paris?” → giờ địa phương, vùng `Europe/Paris` và quy tắc lặp; chỉ lưu một `Instant` không đủ diễn tả lịch lặp mãi về sau.

Dữ liệu thời điểm hiển thị theo vùng:

```text
Instant: 2026-10-28T07:30:00Z
    + ZoneId("Asia/Ho_Chi_Minh")
    → giờ địa phương: 2026-10-28 14:30
```

Múi giờ quyết định đồng hồ và ngày địa phương; locale quyết định cách thể hiện ngày/giờ thành ký tự, chẳng hạn tên tháng hoặc thứ tự trường.

### 3.3. Mã nghiệp vụ và văn bản dịch

Trong DB hoặc API, lưu giá trị như `SHIPPED`; trên giao diện lấy nhãn qua khóa `order.status.shipped` và locale người dùng. Đổi ngôn ngữ không làm thay đổi trạng thái nghiệp vụ. Không lưu trực tiếp `"Đã giao"` làm trạng thái canonical vì bản dịch có thể thay đổi và việc so sánh/truy vấn trở nên không ổn định.

**Lưu ý:** Nội dung tự do do người dùng nhập bằng một ngôn ngữ là **dữ liệu thật** và phải được giữ đúng ngôn ngữ/ý nghĩa. “Dữ liệu trung lập với locale” không có nghĩa xóa dấu tiếng Việt hoặc tự dịch mọi giá trị văn bản. Bản dịch giao diện và nội dung người dùng tạo là hai nguồn có quyền sở hữu khác nhau.

## 4. Ví dụ Java 17+: Một bản ghi, nhiều cách trình bày

Tạo tệp `NeutralDataDemo.java`. Ví dụ dùng `record` giữ giá trị gốc, sau đó trình bày cho hai người dùng khác nhau. Không đổi giá trị trong `Order` khi đổi locale.

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class NeutralDataDemo {
    record Order(
            BigDecimal amount,
            Currency currency,
            LocalDate dueDate,
            Instant createdAt
    ) {}

    public static void main(String[] args) {
        Order order = new Order(
                new BigDecimal("1234567.50"),
                Currency.getInstance("USD"),
                LocalDate.of(2026, 10, 28),
                Instant.parse("2026-10-28T07:30:00Z")
        );

        // Giá trị gốc, dùng độc lập với locale.
        System.out.println("amount=" + order.amount().toPlainString());
        System.out.println("currency=" + order.currency().getCurrencyCode());
        System.out.println("dueDate=" + order.dueDate());
        System.out.println("createdAt=" + order.createdAt());

        show(order, Locale.forLanguageTag("vi-VN"),
                ZoneId.of("Asia/Ho_Chi_Minh"));
        show(order, Locale.forLanguageTag("en-US"),
                ZoneId.of("America/New_York"));
    }

    private static void show(Order order, Locale locale, ZoneId zone) {
        NumberFormat money = NumberFormat.getCurrencyInstance(locale);
        money.setCurrency(order.currency());

        // Tạo formatter theo locale có thể chọn số chữ số thập phân
        // mặc định từ tiền tệ của locale đó; USD cần 2 chữ số.
        int digits = order.currency().getDefaultFractionDigits();
        if (digits >= 0) {
            money.setMinimumFractionDigits(digits);
            money.setMaximumFractionDigits(digits);
        }

        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                        .withLocale(locale);

        DateTimeFormatter instantFormat =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                        .withLocale(locale)
                        .withZone(zone);

        System.out.println("--- " + locale.toLanguageTag() + " / " + zone + " ---");
        System.out.println("Money: " + money.format(order.amount()));
        System.out.println("Due date: " + dateFormat.format(order.dueDate()));
        System.out.println("Created: " + instantFormat.format(order.createdAt()));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên, với mã nguồn lưu UTF-8:

```bash
javac -encoding UTF-8 NeutralDataDemo.java
java NeutralDataDemo
```

Bốn dòng đầu chắc chắn là:

```text
amount=1234567.50
currency=USD
dueDate=2026-10-28
createdAt=2026-10-28T07:30:00Z
```

Các dòng sau được in thành hai nhóm `vi-VN / Asia/Ho_Chi_Minh` và `en-US / America/New_York`, với cách trình bày tiền, ngày và thời gian thích hợp. **Không cố định nguyên văn output của các formatter bản địa hóa**: bản dịch tên tháng, dấu cách/nhóm số, ký hiệu tiền và quy ước locale có thể thay đổi theo CLDR/provider, phiên bản JDK và môi trường. Có thể kiểm chứng ngữ nghĩa của thời điểm bằng cách tự chuyển đổi `Instant` theo `ZoneId`.

Điểm quan trọng của ví dụ:

1. `Order` chứa `BigDecimal`, `Currency`, `LocalDate` và `Instant` — không chứa số tiền hay ngày đã định dạng cho màn hình.
2. `Locale` và `ZoneId` được truyền tường minh cho mỗi lần trình bày; không gọi `Locale.setDefault(...)` để sửa trạng thái chung của cả JVM.
3. `NumberFormat` dùng locale để chọn quy ước hiển thị, còn `Currency` lấy từ giao dịch. Khi cần kiểm soát chữ số thập phân, đặt rõ min/max fraction digits như ví dụ.
4. `DateTimeFormatter.ofLocalizedDate(...)` dùng cho ngày không có múi giờ. Định dạng `Instant` cần `withZone(zone)` để chuyển sang giờ địa phương.
5. `NumberFormat` là formatter có trạng thái thay đổi được, không mặc nhiên an toàn khi chia sẻ giữa nhiều luồng. Tạo riêng hoặc quản lý vòng đời đồng bộ; `DateTimeFormatter` bất biến và an toàn để dùng lại.

Trong sản phẩm, nhãn `Money`, `Due date`, `Created` cũng nên lấy từ tài nguyên dịch thay vì hard-code. Ví dụ `ResourceBundle.getBundle("Messages", locale).getString("order.dueDate")`, với bộ khóa và chính sách fallback đã được kiểm thử.

## 5. Lưu trữ và API: hợp đồng trung lập phải có ngữ nghĩa rõ ràng

Một cách mô tả dữ liệu (chỉ là ví dụ về **hợp đồng API**, không bắt buộc mọi API dùng đúng kiểu JSON như vậy):

```json
{
  "amount": "1234567.50",
  "currency": "USD",
  "dueDate": "2026-10-28",
  "createdAt": "2026-10-28T07:30:00Z",
  "businessZone": "Asia/Ho_Chi_Minh",
  "status": "PAID"
}
```

- `amount` ở dạng **chuỗi decimal chuẩn** là một lựa chọn hợp lệ khi cần bảo toàn chính xác biểu diễn thập phân và scale xuyên qua hệ thống/JavaScript. Hợp đồng khác có thể dùng JSON number nếu có quy ước precision, scale và giới hạn phía client rõ ràng. Dù chọn cách nào, **đừng gửi `"1.234.567,50"` làm giá trị tính toán**.
- `currency` là mã ISO 4217, tách khỏi số tiền và locale.
- `dueDate` dạng ngày ISO 8601 (`yyyy-MM-dd`) cho dữ liệu `LocalDate`; không thêm `Z` hoặc múi giờ một cách máy móc.
- `createdAt` dạng thời điểm ISO 8601 có offset/`Z`; nếu cần giữ vùng múi giờ của nghiệp vụ, lưu `businessZone` riêng vì `Z` chỉ cho biết UTC tại thời điểm đó.
- `status` là mã bất biến của nghiệp vụ; dịch nhãn khi hiển thị.
- Khả năng dùng ISO 8601/UTC là **quyết định contract**, cần nhất quán với hệ lưu trữ và thư viện serialization. Một chuỗi ngày/giờ không rõ zone hoặc offset không đủ xác định một instant.

Khi lưu trong cơ sở dữ liệu, cân nhắc `DECIMAL`/`NUMERIC` với precision/scale nghiệp vụ cho tiền, kiểu ngày riêng cho `LocalDate`, và chiến lược lưu `Instant`/UTC tương ứng với hệ DB/driver. Không suy đoán rằng mọi kiểu SQL mang tên `TIMESTAMP` đều tự ghi nhớ múi giờ; cần kiểm tra semantics chính xác của DB và driver. Nếu chỉ lưu ngày hẹn địa phương, giữ cấu trúc liên quan đến `ZoneId` khi nghiệp vụ yêu cầu.

Dữ liệu API phục vụ máy nên có schema chuẩn; một endpoint frontend có thể cung cấp thêm **view model** đã dịch nếu giao diện không tự format, nhưng view model ấy là **kết quả trình bày**, không thay thế nguồn gốc nghiệp vụ.

## 6. Hai chiều dữ liệu: format ra và parse vào

Một lỗi phổ biến là dùng chuỗi format từ màn hình để tính toán hoặc gửi trở lại máy chủ mà không có contract.

```text
Đúng:
  API canonical → parse thành kiểu nghiệp vụ → tính toán
               → format theo Locale + ZoneId → UI

  UI nhập liệu → xác định locale/format đầu vào
               → parse + validate → giá trị kiểu nghiệp vụ
               → lưu/truyền theo schema canonical

Sai:
  BigDecimal → "1.234,50" → lưu cột số dạng text
  Instant    → "28/10/2026 14:30" → lưu text, bỏ ZoneId
```

### 6.1. Vì sao không dùng `Double.parseDouble` cho số người dùng nhập?

`Double.parseDouble("1.234,50")` không hiểu đây là số theo một locale nhất định. Ngoài ra, `double` không phù hợp cho giá trị tiền cần chính xác theo hệ thập phân. Để nhận số đã nhập theo locale, có thể dùng `NumberFormat`/`DecimalFormat` (với `setParseBigDecimal(true)`) hoặc giao diện nhập riêng theo hợp đồng; sau đó kiểm tra đủ ký tự được tiêu thụ, quy định dấu nhóm số và khoảng giá trị.

Ví dụ tệp độc lập `CanonicalInputDemo.java` cho **đầu vào API chuẩn**, không phải chuỗi nhập giao diện địa phương hóa:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

public class CanonicalInputDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        LocalDate date = LocalDate.parse("2026-10-28");
        Instant instant = Instant.parse("2026-10-28T07:30:00Z");

        System.out.println(amount.toPlainString());
        System.out.println(date);
        System.out.println(instant);
    }
}
```

```bash
javac -encoding UTF-8 CanonicalInputDemo.java
java CanonicalInputDemo
```

Output chính xác:

```text
1234.50
2026-10-28
2026-10-28T07:30:00Z
```

### 6.2. Vì sao parse theo locale phải có kiểm tra?

Chuỗi `03/04/2026` có thể biểu thị 3 tháng 4 hoặc 4 tháng 3 theo quy tắc của UI. Dấu `.` và `,` cũng có vai trò khác nhau giữa các locale. Không được tự suy ra locale chỉ từ hình dáng chuỗi; form hoặc API phải định nghĩa locale/format đầu vào.

Với `NumberFormat.parse(...)`, parser có thể chấp nhận một **phần** chuỗi và dừng, hoặc lỏng lẻo với dấu phân nhóm. Khi sử dụng `ParsePosition`, cần bảo đảm toàn bộ chuỗi được phân tích; đồng thời phải có validation nghiệp vụ và các quy tắc nhập nghiêm ngặt nếu hợp đồng yêu cầu. Chỉ kiểm tra “đã tiêu thụ hết ký tự” **chưa đồng nghĩa** kiểm tra chặt mọi dấu phân nhóm. Đối với tiền, xử lý giá trị thành `BigDecimal` thay vì tính toán qua `double`.

Với ngày, chỉ nên parse theo pattern đã công bố hoặc formatter tương ứng với UI. Dùng `ResolverStyle.STRICT` khi cần phát hiện ngày lịch không hợp lệ, và phân biệt pattern có `u` (proleptic year) với `y` (year-of-era) nếu tự viết pattern nghiêm ngặt. Tránh nhận ngày không rõ năm hoặc múi giờ nếu nghiệp vụ cần xác định chính xác.

**Lưu ý an toàn:** Không tin locale tự khai báo là đủ cho hành vi nghiệp vụ nhạy cảm. Hạn mức thanh toán, làm tròn, tỷ giá, múi giờ pháp lý và thời điểm chốt đều phải theo policy/contract có kiểm soát ở server.

## 7. Tài nguyên dịch là lớp trình bày

`ResourceBundle` dùng locale để chọn nội dung tiếng người dùng đọc. Bản chất khóa vẫn ổn định:

```properties
# Messages.properties
order.total=Total
order.status.paid=Paid
```

```properties
# Messages_vi.properties
order.total=Tổng tiền
order.status.paid=Đã thanh toán
```

Ví dụ khi có bundle trên classpath:

```java
import java.util.Locale;
import java.util.ResourceBundle;

Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle messages = ResourceBundle.getBundle("Messages", locale);
String totalLabel = messages.getString("order.total");
```

Đây là **đoạn mã minh họa nằm trong phương thức hoặc chương trình có context**, không phải chương trình Java độc lập. Giá trị `totalLabel` là nhãn đã dịch nếu bundle tương ứng được tìm thấy. Khi bundle/khóa thiếu, hành vi phụ thuộc chuỗi fallback và có thể ném `MissingResourceException`; sản phẩm cần chính sách fallback rõ ràng, kiểm thử đủ khóa và placeholder.

Không dùng bản dịch làm khóa DB, enum hay dữ liệu điều khiển. Chuỗi dịch có thể được sửa chính tả, đổi cách xưng hô hoặc dài/ngắn khác ngôn ngữ. Với thông báo có tham số, dùng `MessageFormat` hoặc thư viện tương đương thay vì ghép nhiều mảnh câu cứng; chú ý ngữ pháp, số nhiều, dấu nháy và escaping.

Với dữ liệu do người dùng viết (tên sản phẩm tự đặt, bình luận, địa chỉ), đừng tự biến đổi chúng theo locale như thể là nhãn của hệ thống. Nếu sản phẩm có đa ngôn ngữ nội dung, thiết kế rõ các biến thể nội dung và quyền sở hữu bản dịch.

## 8. Locale không phải “cấu hình toàn năng”

Một yêu cầu hiển thị thực tế có thể cần nhiều thông số độc lập:

| Thông số | Ví dụ | Quyết định |
| --- | --- | --- |
| `languageLocale` | `vi-VN` | Ngôn ngữ nhãn, thông báo |
| `formattingLocale` | `en-GB` | Quy tắc định dạng dữ liệu |
| `zoneId` | `Asia/Tokyo` | Giờ địa phương của một instant |
| `currency` | `USD` | Loại tiền của giao dịch |
| `unit` | `km` | Đơn vị vật lý/đo lường |
| `calendar` | ISO hoặc lịch khác nếu được hỗ trợ | Ngữ nghĩa lịch và cách trình bày |
| `userPreference` | Định dạng 12/24 giờ | Tùy chọn bổ sung của người dùng |

Trong ứng dụng đơn giản, cùng một `Locale` có thể được dùng cho cả ngôn ngữ và định dạng. Tuy nhiên, kiến trúc cần tránh suy luận “biết locale là biết hết”: locale **không tự quyết định** múi giờ, đổi đơn vị đo, quốc gia cư trú, phương thức thanh toán hay tỷ giá.

Đặc biệt, cả `en-US` và `en-GB` đều biểu diễn tiếng Anh nhưng có thể có cách ghi ngày/số khác nhau. Đảo lại, `fr-CA` và `en-CA` cùng khu vực Canada nhưng khác ngôn ngữ. Sự khác biệt về quy ước định dạng còn phụ thuộc dữ liệu locale/JDK được triển khai, không nên hard-code một danh sách dấu phân cách bất biến.

Có thể dùng `Locale.forLanguageTag("vi-VN")` cho lựa chọn giao diện; còn nếu xử lý machine data, phải **quy định contract** như ISO-8601 và decimal chuẩn, không dựa vào `Locale.getDefault()`. `Locale.ROOT` hữu ích trong một số thao tác kỹ thuật cần quy tắc không phụ thuộc ngôn ngữ người dùng (chẳng hạn case mapping cho mã do ứng dụng kiểm soát), nhưng bản thân `Locale.ROOT` không định nghĩa mọi định dạng giao thức, không thay thế validation hoặc chuẩn hóa Unicode.

## 9. Những ranh giới nên đặt trong kiến trúc

Một thiết kế dịch vụ Java dễ kiểm thử có thể chia trách nhiệm:

1. **Domain/application**: giữ `BigDecimal`, `Currency`, `LocalDate`, `Instant`, trạng thái dạng mã; áp dụng quy tắc số học, làm tròn và ngày hạn.
2. **Persistence/API**: ánh xạ sang schema rõ precision, kiểu ngày/giờ, định danh và version của contract; serial hóa ổn định.
3. **Request/user context**: giải quyết ngôn ngữ và tùy chọn từ profile hoặc negotiation, xác định locale được hỗ trợ; chọn zone theo người dùng hoặc nghiệp vụ.
4. **Presentation adapter/UI**: dịch nhãn qua tài nguyên; format số, tiền, ngày/giờ; cung cấp văn bản cho người dùng.
5. **Input adapter**: parse chuỗi giao diện theo quy tắc đã xác định, kiểm tra lỗi, chuyển về kiểu nghiệp vụ trước khi tính toán/lưu.

Với Java server đa người dùng, **không gọi `Locale.setDefault` hoặc `TimeZone.setDefault` cho từng request**: đây là thay đổi mặc định toàn tiến trình, có thể khiến các request ảnh hưởng nhau. Truyền `Locale` và `ZoneId` qua lời gọi hoặc context có vòng đời được quản lý. `Accept-Language` là danh sách ưu tiên có thể có trọng số, không phải một language tag duy nhất. Đối chiếu với tập locale được hỗ trợ và sở thích đã lưu của người dùng trước khi chọn fallback sản phẩm.

Formatter có đặc tính luồng khác nhau: `DateTimeFormatter` immutable; `NumberFormat` mutable và không thread-safe theo mặc định. Tránh dùng chung một đối tượng `NumberFormat` rồi gọi `setCurrency` liên tiếp từ nhiều request đồng thời.

## 10. Những tình huống dễ sai

| Tình huống | Sai ở đâu? | Cách xử lý |
| --- | --- | --- |
| Lưu `"1.234,50"` rồi tính tiền từ chuỗi | Tự phụ thuộc locale và parsing mơ hồ | Giữ `BigDecimal` và đơn vị tiền; format tại UI |
| Dùng `double` cho tiền | Có sai số nhị phân và quy tắc làm tròn khó kiểm soát | `BigDecimal`, quy định scale/rounding |
| Dựa vào `Locale.US` để suy ra thanh toán USD | Locale hiển thị không phải nguồn chân lý về tiền tệ | Lấy `Currency` từ giao dịch |
| Lưu ngày sinh thành `Instant` lúc nửa đêm UTC | Chuyển zone có thể đổi ngày trên lịch | Giữ `LocalDate` |
| Dùng `LocalDateTime` làm timestamp sự kiện toàn cầu | Không xác định offset/zone nên có thể mơ hồ | Giữ `Instant` hoặc contract thời gian có offset phù hợp |
| Dùng locale để đoán múi giờ | Một quốc gia có thể nhiều múi giờ, người dùng có thể ở nơi khác | Chọn và truyền `ZoneId` riêng |
| Chuyển đổi tiền chỉ bằng formatter | Formatter chỉ tạo chuỗi, không có tỷ giá | Tính chuyển đổi với tỷ giá và policy nghiệp vụ |
| Lưu `"Paid"` thay vì trạng thái `PAID` | Đổi ngôn ngữ làm hỏng logic/đối chiếu | Lưu mã nghiệp vụ; dịch ở lớp giao diện |
| Dùng default locale/zone của máy chủ | Triển khai nơi khác khiến kết quả đổi | Context tường minh, contract chuẩn |
| So sánh toàn bộ chuỗi format trong unit test | JDK/CLDR có thể đổi ký hiệu và dấu cách | Test semantics, kiểm tra định dạng theo dữ liệu môi trường được pin khi cần |

Thêm một điểm khó: hệ thống đặt lịch tương lai theo giờ địa phương phải tính tới **DST** (daylight saving time). Một `LocalDateTime` trong khoảng chuyển DST có thể không tồn tại hoặc bị lặp lại. Trước khi chuyển thành `Instant` phải chọn vùng `ZoneId` và chính sách giải quyết trường hợp gap/overlap theo nghiệp vụ; không tự giả định offset của ngày hiện tại sẽ đúng cho mọi ngày sau này.

## 11. Kiểm thử nên tập trung vào tính bất biến

Thiết kế bộ test theo hai nhóm:

**Tính đúng của dữ liệu gốc:** cùng giá trị số, đơn vị tiền, ngày và instant phải giữ nguyên sau khi format cho nhiều locale; tổng tiền được tính ở domain, không làm tròn lại do số chữ số hiển thị. Kiểm tra round-trip qua API/DB theo schema đã định, trường hợp null/giá trị âm/scale lớn/boundary date nếu có.

**Tính đúng của trình bày:** nhãn dịch có đủ khóa và placeholder; locale được hỗ trợ được chọn đúng; ngày/giờ được chuyển theo zone; định dạng phù hợp data provider/JDK đang chạy. Với kết quả `NumberFormat`/`DateTimeFormatter`, nếu test chính xác chuỗi hiển thị, cần pin môi trường/version CLDR tương ứng hoặc chấp nhận các biến thể được chính sách sản phẩm hỗ trợ.

Một checklist gọn để thực hành:

- Đặt locale mặc định của JVM khác locale request, thử lại để phát hiện dùng default ngầm.
- Dùng hai locale như `vi-VN`, `en-US` và hai zone như `Asia/Ho_Chi_Minh`, `America/New_York`, xác minh **giá trị nghiệp vụ không đổi**.
- Với `LocalDate`, xác minh không có bước “chuyển múi giờ” làm đổi ngày.
- Với `Instant`, xác minh hai giờ địa phương sau format quy về đúng cùng một instant.
- Với số tiền, kiểm tra ký hiệu tiền thay đổi cách hiển thị nhưng mã tiền và số tiền không đổi.
- Với form nhập, thử dữ liệu không hợp lệ: `1,2,3`, dấu cách/ký tự thừa, ngày không tồn tại, số vượt giới hạn; trình bày thông báo lỗi đã dịch nhưng trả về mã lỗi ổn định.

## 12. Bài tập tự kiểm tra

**Bài 1.** API lưu `orderTotal="2500.00"`, `currency="USD"`. Người dùng chuyển ngôn ngữ từ tiếng Anh sang tiếng Việt. Những gì được phép thay đổi?

**Đáp án:** nhãn và hình thức trình bày số/tiền; giá trị decimal `2500.00` và mã tiền `USD` không được tự đổi. Nếu sản phẩm hỗ trợ chuyển đổi tiền, đó là nghiệp vụ riêng với tỷ giá được công bố.

**Bài 2.** Một người sinh ngày `2000-01-01`. Nên lưu `LocalDate` hay `Instant`? Vì sao?

**Đáp án:** thường là `LocalDate` vì dữ liệu biểu diễn ngày trên lịch chứ không phải thời điểm tuyệt đối. Gắn mốc 00:00 UTC rồi hiển thị tại múi giờ khác có thể tạo ngày khác với dữ liệu gốc.

**Bài 3.** Cùng `Instant.parse("2026-10-28T07:30:00Z")` hiển thị theo `Asia/Ho_Chi_Minh` và `America/New_York`. Có phải đã thay đổi sự kiện?

**Đáp án:** không; hai thời gian địa phương là hai biểu diễn của cùng một thời điểm. Sự kiện gốc vẫn là `Instant` nêu trên.

**Bài 4.** Frontend gửi một giá trị `"03/04/2026"` không kèm locale/format. Backend có thể xác định duy nhất ngày không?

**Đáp án:** không. Cần hợp đồng dữ liệu ISO (`yyyy-MM-dd`) hoặc định nghĩa rõ locale/pattern của biểu mẫu, rồi parse và validate.

**Bài 5.** Một hệ thống đặt buổi học lúc 09:00 mỗi thứ Hai theo giờ Paris. Chỉ lưu thời điểm UTC của buổi học tuần này có đủ cho các buổi học tương lai không?

**Đáp án:** không. Quy tắc lặp theo ngày/giờ địa phương cùng `Europe/Paris` phải được lưu để tính các lần diễn ra, kể cả những lần đi qua thay đổi DST.

## 13. Ghi nhớ

- **Giữ dữ liệu gốc theo ngữ nghĩa nghiệp vụ:** số decimal chính xác, mã tiền, ngày trên lịch, thời điểm tuyệt đối và trạng thái mã hóa.
- **Trình bày ở ranh giới giao diện:** `Locale`, `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`; chọn `ZoneId` độc lập.
- **Trao đổi dữ liệu theo contract rõ kiểu:** không để dấu thập phân, tên tháng hay ngôn ngữ UI lọt vào logic hoặc bản lưu canonical.
- **Dữ liệu đầu vào được parse và validate có chủ đích:** locale cho giao diện; định dạng chuẩn cho giao thức giữa hệ thống.
- **Giá trị và cách hiển thị có thể khác nhau, nhưng không được làm sai ý nghĩa của nhau.**
