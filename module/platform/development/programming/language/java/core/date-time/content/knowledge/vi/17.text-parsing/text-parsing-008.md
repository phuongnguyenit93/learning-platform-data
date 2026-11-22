# Chuỗi thiếu trường và thông tin bổ sung để tạo kiểu đích

## 1. Thiếu thông tin không đồng nghĩa với chuỗi sai

Một hệ thống thanh toán nhận tháng đối soát là `2025-06`; một biểu mẫu nhận ngày hẹn là `2025-06-10`; một tệp nhận giờ bắt đầu là `14:30`. Cả ba chuỗi đều có thể đúng với mục đích ban đầu, nhưng không chuỗi nào tự mô tả một thời điểm đầy đủ trên dòng thời gian.

Vấn đề xuất hiện khi chương trình yêu cầu kiểu đích giàu thông tin hơn dữ liệu nguồn. `YearMonth` đủ cho tháng đối soát; `LocalDate` cần thêm ngày trong tháng; `LocalDateTime` cần ngày và giờ; muốn có một thời điểm xác định còn phải biết độ lệch UTC hoặc vùng thời gian phù hợp.

Vì vậy, trước khi “sửa lỗi parse”, cần xác định **nguồn có thật sự cung cấp thông tin đó không**. Giá trị bổ sung phải đến từ quy định nghiệp vụ, ngữ cảnh bên ngoài hoặc mặc định đã được định nghĩa; không phải do thư viện đoán được ý định của người nhập.

## 2. Kiểu đích đang yêu cầu thêm điều gì?

| Dữ liệu nguồn | Kiểu giữ đúng mức thông tin hiện có | Nếu muốn kiểu khác thì còn thiếu gì? |
| --- | --- | --- |
| `2025-06` | `YearMonth` | `LocalDate` cần ngày trong tháng |
| `2025-06-10` | `LocalDate` | `LocalDateTime` cần giờ trong ngày |
| `14:30` | `LocalTime` | `LocalDateTime` cần một ngày cụ thể |
| `2025-06-10T09:00` | `LocalDateTime` | `OffsetDateTime` cần độ lệch; `ZonedDateTime` cần vùng/độ lệch phù hợp |
| `09:30` theo quy ước 12 giờ | Chưa đủ để phân biệt sáng/chiều | Cần thông tin AM/PM hoặc quy định ngữ cảnh rõ ràng |

Đây là ví dụ về thông tin, không phải danh sách mọi tập trường có thể tạo ngày. Một ngày cũng có thể được xác định bằng năm và ngày thứ mấy trong năm. Điều cần xét là các trường đọc được có đủ để phân giải thành kiểu đích hay không, không chỉ đếm xem chuỗi có đủ những tên trường quen thuộc hay chưa.

Cũng cần phân biệt:

- **Trường bị thiếu:** không có ngày trong `2025-06`.
- **Trường có giá trị sai:** có ngày 31 trong `2025-02-31`.
- **Sai cú pháp:** dấu phân cách hoặc độ rộng không khớp mẫu.

Bổ sung ngày mặc định có thể xử lý trường hợp đầu nếu hợp đồng cho phép; không được dùng để thay thế hoặc che giấu hai trường hợp sau.

## 3. Ba hướng xử lý có chủ đích

### Giữ kiểu phản ánh đúng dữ liệu

Nếu nghiệp vụ nói đến một tháng, lưu `YearMonth` sẽ giữ đúng ý nghĩa hơn việc tự chọn ngày 1. Khi thực sự cần tính mốc đầu tháng, có thể gọi `atDay(1)` tại bước đó. Như vậy người đọc mã nhìn thấy quyết định chuyển tháng thành ngày.

Tương tự, một ngày sinh chỉ cần `LocalDate`; không bắt buộc đổi thành `LocalDateTime` hoặc `Instant` để tránh dữ liệu “thiếu giờ”. Kiểu ít trường hơn có thể là mô hình chính xác của bài toán, không phải dữ liệu chưa hoàn chỉnh.

### Bổ sung sau khi phân tích bằng phương thức ghép

Nếu quy định cuộc hẹn là 09:00 của ngày được chọn, đọc ngày thành `LocalDate` rồi gọi `atTime(9, 0)`. Nếu tệp chỉ có giờ và ngày được cung cấp bởi tiêu đề báo cáo, đọc `LocalTime` rồi gọi `atDate(reportDate)`.

Theo [Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), ngày không chứa giờ hay vùng thời gian. Các phương thức như `atTime()` tạo giá trị kết hợp; chúng thể hiện rõ thông tin bổ sung được đưa vào ở đâu.

Nếu quy định chọn đầu ngày, `date.atStartOfDay()` tạo `LocalDateTime` lúc 00:00. Với `date.atStartOfDay(zone)`, API chọn thời điểm hợp lệ sớm nhất của ngày theo quy tắc vùng; ở vùng có thay đổi độ lệch, không nên mặc nhiên hiểu kết quả luôn là 00:00. Chọn đầu ngày là một quy định ứng dụng, không phải ý nghĩa mặc định của mọi chuỗi ngày.

### Đưa quy tắc mặc định vào bộ định dạng

Khi một định dạng đầu vào chính thức cho phép bỏ bớt trường, `DateTimeFormatterBuilder.parseDefaulting(field, value)` có thể cung cấp giá trị cho trường chưa được đọc. Quy tắc này thuộc bộ định dạng; mọi nơi dùng bộ định dạng đó sẽ có cùng cách bổ sung.

Theo [Java SE 21 — parseDefaulting()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#parseDefaulting(java.time.temporal.TemporalField,long)), giá trị chỉ được đưa vào nếu trường còn chưa có tại vị trí gọi trong chuỗi bộ dựng. Việc bổ sung có hiệu lực ngay, nên thường đặt các lệnh mặc định sau phần đọc dữ liệu tương ứng.

## 4. Chương trình kiểm chứng đầy đủ

Lưu mã sau vào `MissingFieldsDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.ChronoField;
import java.util.Locale;
import java.util.function.Supplier;

public class MissingFieldsDemo {
    private static void show(String label, Supplier<?> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (DateTimeParseException ex) {
            System.out.println(label + " = DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        show("missing time", () -> LocalDateTime.parse(
                "2025-06-10", DateTimeFormatter.ISO_LOCAL_DATE));
        show("missing day", () -> LocalDate.parse(
                "2025-06", DateTimeFormatter.ofPattern("uuuu-MM")));

        YearMonth billingMonth = YearMonth.parse("2025-06");
        System.out.println("month kept = " + billingMonth);
        System.out.println("chosen first day = " + billingMonth.atDay(1));
        LocalDate date = LocalDate.parse("2025-06-10");
        LocalDateTime appointment = date.atTime(9, 0);
        System.out.println("chosen time = " + appointment);
        System.out.println("time plus date = "
                + LocalTime.parse("14:30").atDate(date));

        DateTimeFormatter monthOrDate = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM[-dd]")
                .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("default day", () -> LocalDate.parse("2025-06", monthOrDate));
        show("provided day", () -> LocalDate.parse("2025-06-15", monthOrDate));
        show("invalid day", () -> LocalDate.parse("2025-02-31", monthOrDate));

        DateTimeFormatter dateOrDateTime = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd['T'HH:mm]")
                .parseDefaulting(ChronoField.HOUR_OF_DAY, 9)
                .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("default clock", () -> LocalDateTime.parse(
                "2025-06-10", dateOrDateTime));
        show("provided clock", () -> LocalDateTime.parse(
                "2025-06-10T14:30", dateOrDateTime));

        ZoneId sourceZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = appointment.atZone(sourceZone);
        System.out.println("chosen zone = " + zoned);
        System.out.println("instant = " + zoned.toInstant());
        show("formatter zone", () -> ZonedDateTime.parse(
                "2025-06-10T09:00:00",
                DateTimeFormatter.ISO_LOCAL_DATE_TIME.withZone(sourceZone)));
        show("zone without time", () -> ZonedDateTime.parse(
                "2025-06-10",
                DateTimeFormatter.ISO_LOCAL_DATE.withZone(sourceZone)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MissingFieldsDemo.java
java MissingFieldsDemo
```

Kết quả:

```text
missing time = DateTimeParseException
missing day = DateTimeParseException
month kept = 2025-06
chosen first day = 2025-06-01
chosen time = 2025-06-10T09:00
time plus date = 2025-06-10T14:30
default day = 2025-06-01
provided day = 2025-06-15
invalid day = DateTimeParseException
default clock = 2025-06-10T09:00
provided clock = 2025-06-10T14:30
chosen zone = 2025-06-10T09:00+07:00[Asia/Ho_Chi_Minh]
instant = 2025-06-10T02:00:00Z
formatter zone = 2025-06-10T09:00+07:00[Asia/Ho_Chi_Minh]
zone without time = DateTimeParseException
```

Hàm `show` chỉ dùng để trình diễn lỗi bằng tên ngoại lệ ổn định. Trong ứng dụng, lỗi cần được giữ hoặc chuyển thành phản hồi nhập liệu thích hợp, thay vì coi tên ngoại lệ là một giá trị thời gian.

Hai lời gọi đầu đã chọn bộ định dạng đọc đúng phần ngày hoặc năm–tháng, nhưng kiểu đích vẫn không tạo được vì thiếu trường. Điều đó cho thấy đọc hết chuỗi thành công chưa bảo đảm đủ dữ liệu để tạo đối tượng mong muốn.

## 5. Đọc kỹ phần tùy chọn và phần mặc định

### Tháng có thể có hoặc không có ngày

Mẫu `uuuu-MM[-dd]` gồm phần năm–tháng bắt buộc và phần `-dd` tùy chọn. Dấu `[]` là cú pháp điều khiển bộ định dạng, không phải hai ký tự phải xuất hiện trong dữ liệu.

Lệnh `.parseDefaulting(ChronoField.DAY_OF_MONTH, 1)` đứng sau mẫu. Trong chương trình:

- `2025-06` không có ngày, nên bổ sung ngày 1 và nhận `2025-06-01`.
- `2025-06-15` đã có ngày 15, nên giữ ngày 15.
- `2025-02-31` đã có ngày 31, nên không thay bằng ngày 1; chế độ `STRICT` từ chối ngày không tồn tại.

Chỉ đặt `parseDefaulting(DAY_OF_MONTH, 1)` phía sau mẫu **bắt buộc** `uuuu-MM-dd` không làm phần ngày trở thành tùy chọn. Bộ đọc vẫn đòi ký tự ngày; nó có thể thất bại trước khi đến lệnh bổ sung. Muốn chấp nhận thiếu trường, phải thiết kế cả cú pháp tùy chọn lẫn giá trị để hoàn thiện kết quả.

Không đặt mặc định trước phần định dạng có thể đọc chính trường đó rồi mong giá trị xuất hiện sau luôn ghi đè. Khi mặc định đã được đưa vào trạng thái phân tích, dữ liệu đọc sau có thể xung đột với nó. Trật tự bộ dựng có ý nghĩa.

### Ngày có thể có hoặc không có giờ

Mẫu `uuuu-MM-dd['T'HH:mm]` cho phép cả phần `T` và giờ–phút cùng vắng mặt. Sau đó hai lệnh mặc định cung cấp 09 giờ và 00 phút nếu chưa có. Vì vậy ngày đơn thuần tạo `LocalDateTime` lúc 09:00, trong khi đầu vào `T14:30` giữ 14:30.

Ở ví dụ này, giây và phần nano không xuất hiện; việc phân giải giờ–phút hoàn thiện các phần nhỏ hơn bằng 0. Không suy ra rằng API tự có đủ mọi mốc lớn hơn: thiếu cả giờ không tự sinh giờ 09:00, và thiếu ngày không tự dùng ngày hiện tại. Các giá trị 09:00 trong bài đến từ lệnh mặc định hoặc `atTime(9, 0)` đã viết rõ.

Mẫu đang dùng chỉ chấp nhận giờ đến phút. Chuỗi có thêm `:ss` không thuộc hợp đồng này nếu chưa bổ sung quy tắc đọc giây. Khai báo mặc định không có tác dụng bỏ qua ký tự thừa hoặc sửa cú pháp khác mẫu.

## 6. Vùng thời gian là thông tin bổ sung riêng

`appointment` trong chương trình chỉ là ngày–giờ địa phương. Khi nguồn được xác định thuộc `Asia/Ho_Chi_Minh`, ta dùng `atZone(sourceZone)` để tạo `ZonedDateTime`, rồi gọi `toInstant()` để có thời điểm. Với ngày giờ của ví dụ, 09:00 ở độ lệch `+07:00` tương ứng 02:00 UTC.

Nếu nguồn quy định trực tiếp độ lệch cố định thay vì tên vùng, có thể dùng `localDateTime.atOffset(ZoneOffset.of("+07:00"))`. Độ lệch cố định và tên vùng không luôn thay thế cho nhau: tên vùng có quy tắc độ lệch theo ngày, trong khi một `ZoneOffset` chỉ biểu diễn một độ lệch cụ thể.

Chương trình còn minh họa `ISO_LOCAL_DATE_TIME.withZone(sourceZone)`: chuỗi không ghi vùng nhưng bộ định dạng cung cấp vùng đã cấu hình, nên có đủ thông tin tạo `ZonedDateTime`. Đây là cấu hình chủ động của ứng dụng; không phải bộ phân tích tự phát hiện địa điểm từ các con số.

Hàng `zone without time` vẫn thất bại vì chỉ có ngày và vùng mà chưa có giờ. `withZone()` không phải mặc định cho mọi trường còn thiếu. Muốn có đầu ngày trong vùng đã biết, hãy lựa chọn rõ `LocalDate.parse(text).atStartOfDay(sourceZone)`; muốn giờ hẹn 09:00 thì ghép giờ trước khi gắn vùng.

Ở các vùng có chuyển đổi giờ mùa hè, giờ địa phương có thể rơi vào khoảng không tồn tại hoặc tương ứng hai độ lệch. Có thêm tên vùng không có nghĩa mọi yêu cầu nghiệp vụ đã được giải quyết; cần xác định cách xử lý những trường hợp đó khi chúng nằm trong phạm vi dữ liệu của ứng dụng.

## 7. Những điều cần giữ rõ khi dùng giá trị bổ sung

**Không dùng thời gian máy để bù thiếu một cách ngẫu nhiên.** Nếu báo cáo chỉ ghi giờ, ngày phải đến từ kỳ báo cáo hoặc ngữ cảnh xác định. Gọi `LocalDate.now()` có thể làm cùng một tệp được nhập vào hai ngày khác nhau cho hai kết quả khác nhau.

**Không đổi chế độ phân giải để mong tạo ra dữ liệu chưa có.** `SMART` hoặc `LENIENT` điều chỉnh cách phân giải các trường; chúng không tự biết năm, ngày hoặc vùng mà nguồn đã bỏ qua. Mặc định cần được mô tả bằng hợp đồng và mã cụ thể.

**Giữ dấu vết nếu cần phân biệt dữ liệu thật với dữ liệu mặc định.** Sau khi đã tạo `LocalDateTime`, đối tượng không ghi nhớ 09:00 được người dùng nhập hay được chương trình bổ sung. Nếu sự khác biệt ảnh hưởng nghiệp vụ, hãy lưu riêng trạng thái trường có được cung cấp hay không, thay vì cố suy ra từ giá trị cuối.

**Bổ sung xong vẫn phải kiểm tra tính hợp lệ.** Ví dụ ngày mặc định 31 không phù hợp cho mọi tháng. Các bộ định dạng trong chương trình dùng `STRICT` để phát hiện tổ hợp không tồn tại; tiếp đó ứng dụng vẫn cần kiểm tra những giới hạn riêng như khoảng ngày nhận lịch.

Bài tập: nếu hợp đồng tháng đối soát đổi thành “lấy ngày cuối tháng”, hãy phân tích `YearMonth` rồi dùng `atEndOfMonth()`, thay vì mặc định ngày 31. Với `2025-02`, kết quả là `2025-02-28`; với `2024-02`, kết quả là `2024-02-29`. Giá trị bổ sung lúc này phụ thuộc tháng và năm, nên một hằng số `parseDefaulting(DAY_OF_MONTH, 31)` không biểu diễn đúng quy tắc.
