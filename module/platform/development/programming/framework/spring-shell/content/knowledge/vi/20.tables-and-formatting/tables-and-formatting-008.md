# Giá trị số, ngày giờ và quy ước định dạng nhất quán

Một bảng CLI có thể chứa số lượng, tiền tệ, tỷ lệ phần trăm và thời điểm cập nhật. Nếu mỗi command tự chuyển các giá trị này thành chuỗi theo cách riêng, người dùng sẽ gặp những cách viết khác nhau cho cùng một dữ liệu. Ví dụ, cùng một số tiền có thể xuất hiện thành `1234567.5`, `1,234,567.50` hoặc `1.234.567,50` tùy locale và cách format.

Để output dễ đọc và đáng tin cậy, hãy giữ dữ liệu ở kiểu Java phù hợp, chọn locale và múi giờ tường minh, xác định quy tắc làm tròn, rồi định dạng tại lớp hiển thị. Spring Shell 4.0.4 cung cấp table model, formatter và aligner để áp dụng quy ước này theo từng cột.

## 1. Giữ dữ liệu có kiểu trước khi định dạng

Không nên chuyển mọi giá trị thành `String` ngay khi đọc từ database hoặc nhận từ service. Giữ kiểu dữ liệu giúp tính toán, so sánh và kiểm tra chính xác; chỉ chuyển thành chuỗi khi chuẩn bị hiển thị.

| Loại dữ liệu | Kiểu Java phù hợp | Lý do |
|---|---|---|
| Số nguyên đếm được | `int`, `long`, `Integer`, `Long` | Không có phần thập phân |
| Số thập phân cần độ chính xác | `BigDecimal` | Kiểm soát scale và rounding rõ ràng |
| Tiền tệ | `BigDecimal` cùng mã tiền tệ | Tránh sai số nhị phân của `double` và biết đơn vị tiền |
| Tỷ lệ phần trăm | `BigDecimal` hoặc kiểu số phù hợp | Có thể lưu dưới dạng tỷ lệ `0.125` rồi hiển thị `12,5%` |
| Ngày lịch | `LocalDate` | Không có giờ hoặc múi giờ |
| Thời gian địa phương | `LocalDateTime` | Có ngày và giờ nhưng không xác định một instant toàn cầu |
| Thời điểm toàn cầu | `Instant` | Đại diện một điểm trên timeline UTC |
| Thời điểm kèm múi giờ | `ZonedDateTime` hoặc `OffsetDateTime` | Giữ thông tin vùng hoặc offset khi cần |

Ví dụ, tiền không nên lưu bằng `double`:

```java
double price = 0.1 + 0.2;
System.out.println(price); // có thể in 0.30000000000000004
```

Thay vào đó, dùng `BigDecimal` tạo từ chuỗi:

```java
BigDecimal price = new BigDecimal("0.30");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);
```

Không tạo `BigDecimal` từ `double` nếu cần biểu diễn chính xác số thập phân. `new BigDecimal("0.1")` thể hiện đúng giá trị thập phân mong muốn; `new BigDecimal(0.1)` giữ lại biểu diễn nhị phân gần đúng của `double`.

## 2. Locale quyết định dấu thập phân và phân nhóm hàng nghìn

Locale mô tả quy ước ngôn ngữ và vùng khi hiển thị số, ngày giờ hoặc tiền tệ. Cùng một giá trị `1234567.89` có thể được hiển thị khác nhau:

| Locale | Ví dụ hiển thị số |
|---|---|
| `vi-VN` | `1.234.567,89` |
| `en-US` | `1,234,567.89` |
| `de-DE` | `1.234.567,89` |

Dùng `NumberFormat` thay vì tự chèn dấu chấm hoặc dấu phẩy:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
numberFormat.setGroupingUsed(true);
numberFormat.setMinimumFractionDigits(2);
numberFormat.setMaximumFractionDigits(2);

String text = numberFormat.format(new BigDecimal("1234567.89"));
// Ví dụ: 1.234.567,89
```

Không phụ thuộc vào `Locale.getDefault()` nếu output cần ổn định giữa máy phát triển, máy chủ và CI. Hãy lấy locale từ cấu hình người dùng hoặc cấu hình ứng dụng, rồi truyền nó rõ ràng cho formatter.

`NumberFormat` là mutable và không thread-safe. Nếu command bean là singleton và có thể được gọi đồng thời, đừng chia sẻ một instance `NumberFormat` giữa các thread. Tạo formatter trong phạm vi lần gọi, hoặc quản lý riêng theo thread nếu thực sự cần tái sử dụng.

## 3. Định dạng tiền tệ bằng Currency và BigDecimal

Tiền tệ cần cả giá trị số lẫn đơn vị tiền. Không nên chỉ dựa vào locale để suy ra currency nếu nghiệp vụ có thể xử lý nhiều quốc gia hoặc nhiều loại tiền.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
Currency currency = Currency.getInstance("VND");

int fractionDigits = Math.max(currency.getDefaultFractionDigits(), 0);
BigDecimal amount = new BigDecimal("1234567.895")
        .setScale(fractionDigits, RoundingMode.HALF_UP);

NumberFormat currencyFormat = NumberFormat.getCurrencyInstance(locale);
currencyFormat.setCurrency(currency);
currencyFormat.setMinimumFractionDigits(fractionDigits);
currencyFormat.setMaximumFractionDigits(fractionDigits);
currencyFormat.setRoundingMode(RoundingMode.HALF_UP);

String displayAmount = currencyFormat.format(amount);
```

Với `VND`, số chữ số thập phân mặc định theo metadata tiền tệ thường là `0`; với các currency khác, con số này có thể khác. Nếu nghiệp vụ có quy định riêng về scale, hãy áp dụng quy tắc đó thay vì mặc định rằng mọi currency đều có hai chữ số thập phân.

Khi bảng có nhiều currency, hiển thị mã tiền tệ hoặc ký hiệu cho từng dòng. Không cộng trực tiếp `100 USD` với `100 EUR` chỉ vì cả hai đều là `BigDecimal`. Muốn tổng hợp nhiều loại tiền, phải có bước quy đổi với tỷ giá và thời điểm tỷ giá được xác định rõ.

## 4. Làm tròn là quy tắc nghiệp vụ

Định dạng số có thể làm tròn giá trị để hiển thị. Hãy xác định quy tắc làm tròn tại nơi phù hợp và không để formatter âm thầm quyết định kết quả tính toán.

Ví dụ:

```java
BigDecimal raw = new BigDecimal("12.345");

BigDecimal halfUp = raw.setScale(2, RoundingMode.HALF_UP);   // 12.35
BigDecimal halfEven = raw.setScale(2, RoundingMode.HALF_EVEN); // 12.34
```

`HALF_UP` làm tròn về số gần nhất và khi đúng điểm giữa thì làm tăng độ lớn (away from zero); `HALF_EVEN` chọn số chẵn ở chữ số cuối khi đúng điểm giữa. Quy tắc phù hợp phụ thuộc hợp đồng nghiệp vụ, quy định kế toán và loại dữ liệu.

Nên phân biệt:

- Giá trị lưu trữ hoặc tính toán: giữ độ chính xác cần thiết.
- Giá trị được làm tròn theo nghiệp vụ: tạo `BigDecimal` mới với scale và rounding mode được quy định.
- Chuỗi hiển thị: định dạng giá trị đã chọn theo locale và số chữ số cần trình bày.

Không dùng chuỗi đã format để tính toán tiếp. Dấu phân nhóm, ký hiệu tiền và dấu thập phân phụ thuộc locale nên không phải biểu diễn dữ liệu phù hợp cho phép tính.

## 5. Định dạng phần trăm đúng cách

`NumberFormat.getPercentInstance(locale)` xem đầu vào là một tỷ lệ, rồi nhân 100 khi hiển thị. Vì vậy, giá trị `0.125` được trình bày thành `12,5%` ở locale Việt Nam.

```java
NumberFormat percentFormat = NumberFormat.getPercentInstance(locale);
percentFormat.setMinimumFractionDigits(1);
percentFormat.setMaximumFractionDigits(1);

String rate = percentFormat.format(new BigDecimal("0.125"));
// Ví dụ: 12,5%
```

Nếu dữ liệu nguồn lưu `12.5` với ý nghĩa “12,5 phần trăm” thay vì tỷ lệ `0.125`, hãy chuyển đổi về tỷ lệ trước khi dùng percent formatter. Nếu không, kết quả có thể thành `1.250%`.

Ghi rõ đơn vị ở header cột, ví dụ `Tỷ lệ (%)`, để người đọc biết dữ liệu là phần trăm. Tránh khi thì lưu `0.125`, khi thì lưu `12.5` trong cùng một cột.

## 6. Chọn kiểu ngày giờ theo ý nghĩa dữ liệu

Ngày và thời điểm không phải cùng một khái niệm:

- `LocalDate`: ngày lịch như ngày sinh hoặc ngày lập hóa đơn, không cần chuyển múi giờ.
- `LocalDateTime`: ngày giờ địa phương chưa gắn múi giờ. Chỉ dùng khi ngữ cảnh xác định được vùng thời gian ở nơi khác.
- `Instant`: thời điểm tuyệt đối, phù hợp lưu sự kiện xảy ra trên hệ thống.
- `ZonedDateTime`: thời điểm có vùng thời gian, ví dụ `Asia/Ho_Chi_Minh`.
- `OffsetDateTime`: ngày giờ kèm offset UTC như `+07:00`, nhưng không giữ đầy đủ quy tắc lịch sử của vùng IANA.

Với sự kiện hệ thống, thường lưu `Instant` và chọn múi giờ khi hiển thị. Với ngày sinh, ngày đáo hạn hoặc ngày báo cáo, dùng `LocalDate` nếu không có ý nghĩa thời điểm trong ngày.

Không gắn một `ZoneId` tùy ý vào `LocalDateTime` rồi coi đó là thời điểm gốc nếu dữ liệu không xác định vùng thời gian. Hai vùng có thể có cùng giờ địa phương nhưng đại diện các instant khác nhau.

## 7. Dùng DateTimeFormatter với mẫu rõ ràng

`DateTimeFormatter` hỗ trợ mẫu định dạng và locale. Ví dụ ngày theo quy ước Việt Nam:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
DateTimeFormatter dateFormat =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);

String text = dateFormat.format(LocalDate.of(2026, 11, 26));
// 26/11/2026
```

Với timestamp, chọn cả locale lẫn zone:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");
DateTimeFormatter timestampFormat = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm:ss XXX", locale)
        .withZone(displayZone);

String text = timestampFormat.format(Instant.parse("2026-11-26T04:00:00Z"));
// Ví dụ: 26/11/2026 11:00:00 +07:00
```

Formatter có zone rõ ràng giúp cùng một `Instant` hiển thị nhất quán trên máy chạy ở các múi giờ khác nhau. `DateTimeFormatter` immutable và thread-safe, nên có thể tái sử dụng an toàn.

## 8. Tránh nhầm các ký hiệu trong mẫu ngày giờ

Các ký hiệu mẫu có phân biệt chữ hoa và chữ thường:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `d` / `dd` | Ngày trong tháng | `26` |
| `M` / `MM` | Tháng | `11` |
| `MMM` / `MMMM` | Tên tháng | `Nov` / tên tháng theo locale |
| `u` / `uuuu` | Năm theo hệ lịch proleptic | `2026` |
| `Y` / `YYYY` | Năm theo tuần (week-based year) | Có thể khác năm lịch ở ranh giới năm |
| `H` / `HH` | Giờ 0–23 | `14` |
| `h` / `hh` | Giờ 1–12 | `02` |
| `m` / `mm` | Phút | `05` |
| `s` / `ss` | Giây | `09` |
| `X` / `XXX` | Offset UTC | `Z` / `+07:00` |
| `VV` | Tên vùng thời gian | `Asia/Ho_Chi_Minh` |

Hai nhầm lẫn thường gặp:

- `MM` là tháng, `mm` là phút.
- `YYYY` là week-based year, không phải năm lịch thông thường. Dùng `uuuu` cho mẫu ngày lịch phổ biến.

Khi parse input do người dùng nhập, dùng formatter đã công bố và `ResolverStyle.STRICT` nếu cần từ chối ngày không tồn tại thay vì tự điều chỉnh.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter inputDateFormat = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"))
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("26/11/2026", inputDateFormat);
```

## 9. Tách format hiển thị khỏi định dạng trao đổi dữ liệu

Định dạng dành cho người đọc và định dạng dành cho máy có mục tiêu khác nhau.

| Dữ liệu | Hiển thị cho người dùng | Định dạng máy nên ổn định |
|---|---|---|
| Số thập phân | Theo locale, có dấu phân nhóm | JSON number dùng dấu chấm thập phân, không có dấu phân nhóm |
| Tiền tệ | Kèm ký hiệu/mã tiền, quy tắc chữ số rõ ràng | Giá trị số cùng mã currency riêng, hoặc chuỗi decimal theo schema |
| Ngày lịch | `26/11/2026` | ISO `2026-11-26` |
| Thời điểm | Theo zone người dùng, ví dụ `26/11/2026 11:00 +07:00` | ISO-8601 instant, ví dụ `2026-11-26T04:00:00Z` |
| Phần trăm | `12,5%` | Tỷ lệ số `0.125` hoặc trường phần trăm theo schema được công bố |

Không dùng chuỗi tiền tệ có dấu phân nhóm như `1.234.567 ₫` làm giá trị JSON number. JSON number không có quy tắc locale; ký hiệu tiền tệ phải nằm trong một field riêng hoặc được biểu diễn bằng chuỗi theo contract.

Nếu command hỗ trợ cả `--format table` và `--format json`, hãy giữ dữ liệu nguồn giống nhau rồi dùng renderer riêng cho mỗi format. Không lấy output bảng đã căn cột để tạo JSON hoặc CSV.

## 10. Spring Shell Table: mô hình, formatter và căn cột

Spring Shell 4.0.4 cung cấp table API trong package:

```java
org.springframework.shell.jline.tui.table
```

Các thành phần chính:

- `TableModel`: mô hình dữ liệu gồm số hàng, số cột và giá trị của từng ô.
- `ArrayTableModel`: mô hình bảng lấy dữ liệu từ mảng hai chiều `Object[][]`.
- `TableBuilder`: cấu hình cách hiển thị bảng.
- `CellMatchers`: chọn ô hoặc cột cần áp dụng cấu hình.
- `Formatter`: chuyển giá trị thô thành một hoặc nhiều dòng chuỗi.
- `SimpleHorizontalAligner`: căn trái, giữa hoặc phải nội dung ô.
- `BorderStyle`: chọn kiểu đường viền.

Khi tạo `TableBuilder` mà không tùy chỉnh, Spring Shell dùng `toString()` làm format mặc định, căn trái và có thể wrap theo dấu cách. Vì thế, nếu cần số theo locale hoặc ngày giờ theo zone cụ thể, hãy gắn formatter riêng vào cột tương ứng.

Luồng xử lý bảng gồm các giai đoạn: formatter tạo chuỗi từ dữ liệu thô; sizing xác định độ rộng cột; wrapper xử lý xuống dòng; aligner căn nội dung trong từng ô. Định dạng số/ngày giờ nên được quyết định trước khi bảng tính kích thước cột.

## 11. Ví dụ bảng có tiền tệ và thời điểm

Ví dụ sau dùng `BigDecimal` cho số tiền và `Instant` cho thời điểm cập nhật. Cột số tiền được format theo `vi-VN` và căn phải; cột thời điểm hiển thị theo múi giờ Việt Nam.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.Locale;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.jline.tui.table.ArrayTableModel;
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.CellMatchers;
import org.springframework.shell.jline.tui.table.SimpleHorizontalAligner;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.stereotype.Component;

@Component
class RevenueCommands {

    @Command(name = "revenue list", description = "Liệt kê doanh thu")
    public void list(CommandContext context) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Currency currency = Currency.getInstance("VND");
        int fractionDigits = Math.max(currency.getDefaultFractionDigits(), 0);

        NumberFormat moneyFormat = NumberFormat.getCurrencyInstance(locale);
        moneyFormat.setCurrency(currency);
        moneyFormat.setMinimumFractionDigits(fractionDigits);
        moneyFormat.setMaximumFractionDigits(fractionDigits);
        moneyFormat.setRoundingMode(RoundingMode.HALF_UP);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        DateTimeFormatter timeFormat = DateTimeFormatter
                .ofPattern("dd/MM/uuuu HH:mm:ss XXX", locale)
                .withZone(zone);

        Object[][] rows = {
            {"Mã", "Đơn vị", "Doanh thu", "Cập nhật"},
            {"R-101", "Cửa hàng A", new BigDecimal("1234567.50"),
                    Instant.parse("2026-11-26T04:00:00Z")},
            {"R-102", "Cửa hàng B", new BigDecimal("98500.00"),
                    Instant.parse("2026-11-26T05:30:00Z")}
        };

        Table table = new TableBuilder(new ArrayTableModel(rows))
                .on(CellMatchers.column(2))
                    .addFormatter(value -> new String[] {
                        value instanceof BigDecimal amount
                                ? moneyFormat.format(amount)
                                : value == null ? "-" : value.toString()
                    })
                    .addAligner(SimpleHorizontalAligner.right)
                    .and()
                .on(CellMatchers.column(3))
                    .addFormatter(value -> new String[] {
                        value instanceof Instant instant
                                ? timeFormat.format(instant)
                                : value == null ? "-" : value.toString()
                    })
                    .and()
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        context.outputWriter().println(table.render(120));
    }
}
```

Trong ví dụ, `CellMatchers.column(2)` chọn cột doanh thu và `CellMatchers.column(3)` chọn cột thời gian; chỉ số cột bắt đầu từ `0`. Formatter kiểm tra kiểu giá trị để giữ nguyên nội dung header, đồng thời định dạng các giá trị dữ liệu. `SimpleHorizontalAligner.right` căn số về bên phải để dễ so sánh hàng đơn vị, hàng nghìn và phần thập phân.

`render(120)` dùng độ rộng bảng được chỉ định trong ví dụ. Ứng dụng thực tế nên lấy độ rộng từ terminal hoặc chọn một giới hạn phù hợp với môi trường. Nếu bảng có thể được redirect, hãy cân nhắc output CSV/JSON riêng thay vì coi bảng căn cột là định dạng trao đổi dữ liệu.

## 12. Tạo quy ước định dạng dùng chung

Nếu nhiều command hiển thị cùng loại dữ liệu, không nên lặp lại mẫu ngày, locale, currency và rounding mode ở từng method. Tạo một lớp định dạng dùng chung để các command dùng cùng quy tắc.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.Locale;

final class CliFormats {

    private static final Locale LOCALE = Locale.forLanguageTag("vi-VN");
    private static final ZoneId ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    private static final Currency CURRENCY = Currency.getInstance("VND");
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter
            .ofPattern("dd/MM/uuuu HH:mm:ss XXX", LOCALE)
            .withZone(ZONE);

    private CliFormats() {
    }

    static String money(BigDecimal value) {
        int digits = Math.max(CURRENCY.getDefaultFractionDigits(), 0);
        BigDecimal rounded = value.setScale(digits, RoundingMode.HALF_UP);
        NumberFormat format = NumberFormat.getCurrencyInstance(LOCALE);
        format.setCurrency(CURRENCY);
        format.setMinimumFractionDigits(digits);
        format.setMaximumFractionDigits(digits);
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format.format(rounded);
    }

    static String timestamp(Instant value) {
        return TIMESTAMP.format(value);
    }
}
```

Trong ví dụ này, `DateTimeFormatter` là immutable nên có thể dùng chung. `NumberFormat` được tạo mới trong mỗi lần gọi `money` vì nó mutable và không thread-safe. Nếu ứng dụng cần nhiều locale hoặc currency, hãy đưa các lựa chọn đó vào một cấu hình hoặc formatter factory thay vì hard-code ở nhiều command.

## 13. Xử lý giá trị null, zero và dữ liệu thiếu

`null`, số `0` và chuỗi rỗng không đồng nghĩa:

| Giá trị | Ý nghĩa có thể có | Cách hiển thị gợi ý |
|---|---|---|
| `null` | Chưa có dữ liệu hoặc không áp dụng | `-` hoặc `Chưa có` |
| `BigDecimal.ZERO` | Giá trị số bằng 0 | `0` theo quy ước số/currency |
| `""` | Chuỗi có nội dung rỗng | Xử lý theo contract của field |
| `Optional.empty()` | Không có giá trị | Hiển thị theo quy tắc missing value |

Không thay `null` thành `0` chỉ để bảng không có ô trống; điều đó có thể khiến người dùng hiểu nhầm dữ liệu chưa có thành kết quả bằng không. Nếu cần tính tổng, hãy quy định rõ cách xử lý missing values.

## 14. Kiểm thử định dạng nhất quán

Kiểm thử nên xác nhận cả giá trị và cách hiển thị. Các ca cần có:

| Nhóm | Trường hợp | Điều cần xác nhận |
|---|---|---|
| Locale số | `vi-VN`, `en-US`, `de-DE` | Dấu thập phân và phân nhóm đúng locale |
| Currency | VND và currency có chữ số lẻ | Mã/ký hiệu và số chữ số thập phân đúng quy tắc |
| Rounding | Giá trị ngay dưới, đúng tại và ngay trên điểm giữa | Kết quả theo `RoundingMode` đã chọn |
| Percentage | `0`, `0.125`, `1` | Không nhầm tỷ lệ với số phần trăm đã nhân 100 |
| Date | Cuối tháng, năm nhuận, ngày không hợp lệ | Parse strict và hiển thị đúng |
| Timestamp | Cùng một `Instant` ở UTC và `Asia/Ho_Chi_Minh` | Thời điểm tương ứng, offset rõ ràng |
| Table | Cột số, ngày giờ, null | Format đúng, số căn phải, missing value không biến thành zero |
| Machine output | JSON/CSV | Không có dấu phân nhóm hoặc ký hiệu trình bày ngoài schema |

Không chỉ kiểm tra output trên máy phát triển. Chạy test với locale và timezone được chỉ định trong cấu hình, kể cả khi JVM chạy trên máy có default locale/timezone khác.

## 15. Bài tập thực hành

Xây dựng command `sales summary` hiển thị doanh thu theo cửa hàng với các cột: mã cửa hàng, số đơn, doanh thu, tỷ lệ hoàn trả và thời điểm cập nhật cuối.

Hãy thực hiện:

1. Dùng `long` cho số đơn và `BigDecimal` cho doanh thu, tỷ lệ.
2. Chọn currency theo mã ISO 4217 và locale `vi-VN`.
3. Định nghĩa rõ scale và `RoundingMode` cho doanh thu.
4. Lưu thời điểm cập nhật bằng `Instant`.
5. Hiển thị timestamp theo `Asia/Ho_Chi_Minh` và kèm offset.
6. Dùng `ArrayTableModel`, `TableBuilder` và `CellMatchers` để format theo cột.
7. Căn phải cột số và căn trái cột văn bản.
8. Xử lý riêng `null`, zero và dữ liệu không áp dụng.
9. Thêm output JSON hoặc CSV giữ số và timestamp theo contract máy đọc.
10. Viết test cho nhiều locale, rounding, năm nhuận và chuyển đổi múi giờ.

**Kết quả cần nộp:** source command, quy ước locale/currency/zone, bảng kết quả mẫu, output JSON/CSV và test định dạng.

## 16. Checklist trước khi công bố output

- [ ] Dữ liệu số và thời gian được giữ ở kiểu Java phù hợp trước khi render.
- [ ] Tiền tệ dùng `BigDecimal`, không dùng `double` để tính toán chính xác.
- [ ] Locale được chọn tường minh.
- [ ] Currency có mã ISO và quy tắc chữ số thập phân rõ ràng.
- [ ] Rounding mode được xác định theo nghiệp vụ.
- [ ] Percentage dùng quy ước tỷ lệ nhất quán.
- [ ] Ngày lịch và thời điểm toàn cầu dùng kiểu riêng phù hợp.
- [ ] Timestamp có zone/offset hiển thị rõ ràng.
- [ ] Mẫu ngày dùng đúng ký hiệu `MM`/`mm`, `uuuu`/`YYYY`.
- [ ] `DateTimeFormatter` và `NumberFormat` được dùng đúng đặc tính thread-safety.
- [ ] Table formatter áp dụng theo đúng cột và số được căn phải.
- [ ] `null` được phân biệt với số `0`.
- [ ] Output JSON/CSV giữ định dạng máy ổn định, không dùng chuỗi đã locale-format làm số.
- [ ] Đã kiểm thử locale, timezone, rounding và dữ liệu biên.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 API — `TableBuilder`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html)
- [Spring Shell 4.0.4 API — `TableModelBuilder`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModelBuilder.html)
- [Spring Shell 4.0.4 API — `Formatter`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Formatter.html)
- [Spring Shell 4.0.4 API — `CellMatchers`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/CellMatchers.html)
- [Spring Shell 4.0.4 API — `SimpleHorizontalAligner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/SimpleHorizontalAligner.html)
- [Java API — `NumberFormat`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java API — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java API — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java API — `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
