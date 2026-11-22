# Tách giờ hiển thị khỏi thời điểm lưu trữ

## 1. Một thời điểm, nhiều cách nhìn

Một giao dịch xảy ra tại `2025-12-31T18:00:45.123456789Z`. Người ở Việt Nam nhìn thấy đầu ngày 1/1/2026; người ở New York vẫn thấy chiều 31/12/2025. Dữ liệu không mâu thuẫn: hai người đang nhìn **cùng một thời điểm** qua hai múi giờ.

Đối với dữ liệu biểu diễn một sự kiện trên trục thời gian, nên giữ mốc có ý nghĩa rõ ràng, chẳng hạn `Instant occurredAt`, rồi định dạng theo vùng và ngôn ngữ ở ranh giới hiển thị. Không sửa giá trị gốc mỗi khi người dùng đổi múi giờ hoặc ngôn ngữ.

```text
Thời điểm gốc
    + ZoneId của cách nhìn
    + Locale và quy cách trình bày
    → chuỗi hiển thị
```

`Instant` không chứa tên vùng hiển thị. Nó là giá trị thời điểm, còn chuỗi UTC có `Z` là một cách biểu diễn chuẩn của giá trị đó. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

## 2. Mỗi lớp dữ liệu giữ trách nhiệm nào?

| Thành phần | Thông tin cần giữ |
| --- | --- |
| Dữ liệu nghiệp vụ của sự kiện | Mốc thời gian thực, ví dụ `Instant` |
| Dữ liệu lưu trữ/trao đổi | Hợp đồng xác định thời điểm và độ chính xác rõ ràng |
| Tùy chọn hiển thị | `ZoneId`, `Locale`, kiểu định dạng |
| Chuỗi trên giao diện | Kết quả định dạng có thể tái tạo từ dữ liệu gốc |

Ví dụ `occurredAt = 2025-12-31T18:00:45Z` không nên được thay bằng một `LocalDateTime` “đã cộng 7 giờ” rồi vẫn ghi lại như thể đó là UTC. Khi cần vùng của sự kiện để truy vết, lưu riêng thông tin vùng/độ lệch nguồn theo hợp đồng.

Dạng SQL cụ thể phụ thuộc DB và trình điều khiển. Đặt phiên kết nối ở UTC không tự làm mọi cột `TIMESTAMP` trở thành một thời điểm có ngữ nghĩa đúng. Cần kiểm tra ánh xạ, cấu hình và giá trị sau khi ghi/đọc.

## 3. ZoneId và Locale giải quyết hai việc khác nhau

`ZoneId` quyết định giờ và ngày địa phương tại một thời điểm. `Locale` quyết định quy cách ngôn ngữ và trình bày, như tên tháng, thứ tự thành phần hoặc cách viết giờ theo formatter được chọn.

Chọn tiếng Việt không tự chọn `Asia/Ho_Chi_Minh`; chọn tiếng Anh cũng không tự chọn múi giờ Mỹ. Một người dùng tiếng Việt vẫn có thể sống ở New York. Nên nhận hai lựa chọn riêng hoặc áp dụng mặc định được mô tả rõ.

`DateTimeFormatter.withZone(zone)` áp dụng vùng khi định dạng một `Instant`; `withLocale(locale)` chọn quy cách địa phương. Formatter bất biến, nên các phương thức này trả formatter mới. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Đoạn minh họa trong một phương thức:

```java
DateTimeFormatter display = DateTimeFormatter.ofLocalizedDateTime(
        java.time.format.FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"))
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
String label = display.format(occurredAt);
```

Chuỗi ngôn ngữ cụ thể có thể thay đổi theo dữ liệu địa phương của JDK. Không dùng nó làm định dạng truyền máy hay khóa nghiệp vụ.

## 4. Đổi cách hiển thị phải giữ cùng Instant

Với `ZonedDateTime`, cần phân biệt hai thao tác:

| Phương thức | Thành phần được giữ | Ý nghĩa |
| --- | --- | --- |
| `withZoneSameInstant(zone)` | Cùng thời điểm | Đổi cách nhìn một sự kiện |
| `withZoneSameLocal(zone)` | Cố giữ ngày/giờ địa phương | Diễn giải lịch địa phương tại vùng khác, có thể đổi thời điểm |

Để hiển thị một giao dịch cho người ở vùng khác, dùng `instant.atZone(viewZone)` hoặc `withZoneSameInstant`. Không dùng `withZoneSameLocal`, vì nó thường làm sự kiện bị chuyển sang một thời điểm khác.

`withZoneSameLocal` còn phải xử lý quy tắc thiếu/trùng giờ tại vùng đích; vì vậy ngay cả việc giữ thành phần địa phương cũng tuân theo quy tắc của API. Nó là thao tác có ý nghĩa riêng, không phải hàm đổi nhãn múi giờ. [ZonedDateTime: chuyển vùng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#withZoneSameInstant(java.time.ZoneId))

## 5. Chương trình: đổi ngày hiển thị nhưng giữ dữ liệu

Lưu thành `DisplayTimeDemo.java`. Ví dụ dùng mẫu số cố định để dễ đối chiếu stdout; giao diện thật có thể dùng mẫu địa phương phù hợp.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DisplayTimeDemo {
    static String display(Instant value, ZoneId zone, Locale locale) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX VV", locale)
                .withZone(zone)
                .format(value);
    }

    public static void main(String[] args) {
        Instant stored = Instant.parse("2025-12-31T18:00:45.123456789Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("vietnam="
                + display(stored, vietnam, Locale.forLanguageTag("vi-VN")));
        System.out.println("newYork=" + display(stored, newYork, Locale.US));
        System.out.println("stored=" + stored);

        ZonedDateTime vietnamView = stored.atZone(vietnam);
        ZonedDateTime sameInstant = vietnamView.withZoneSameInstant(newYork);
        ZonedDateTime sameLocal = vietnamView.withZoneSameLocal(newYork);
        System.out.println("sameInstantEqual="
                + stored.equals(sameInstant.toInstant()));
        System.out.println("sameLocalEqual="
                + stored.equals(sameLocal.toInstant()));
        System.out.println("sameLocalInstant=" + sameLocal.toInstant());

        String wire = DateTimeFormatter.ISO_INSTANT.format(stored);
        Instant readBack = Instant.parse(wire);
        System.out.println("wire=" + wire);
        System.out.println("wireRoundTrip=" + stored.equals(readBack));
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 DisplayTimeDemo.java
java DisplayTimeDemo
```

Stdout với quy tắc IANA tương ứng các vùng và ngày trong ví dụ:

```text
vietnam=2026-01-01 01:00 +07:00 Asia/Ho_Chi_Minh
newYork=2025-12-31 13:00 -05:00 America/New_York
stored=2025-12-31T18:00:45.123456789Z
sameInstantEqual=true
sameLocalEqual=false
sameLocalInstant=2026-01-01T06:00:45.123456789Z
wire=2025-12-31T18:00:45.123456789Z
wireRoundTrip=true
```

Chuỗi hiển thị chỉ có phút, nhưng `stored` vẫn giữ giây và nano giây. Bỏ chi tiết khỏi nhãn không có nghĩa được cắt mất chi tiết trong dữ liệu gốc.

`sameLocalInstant` cho thấy hậu quả của đổi vùng nhưng giữ 01:00 địa phương: mốc mới khác dữ liệu lưu ban đầu. Đây là thay đổi ý nghĩa thời gian, không chỉ là hiển thị.

## 6. Luồng đọc và luồng nhập dữ liệu không đối xứng

Định dạng một thời điểm thành chuỗi cho người xem có thể làm mất thông tin: bỏ giây, độ lệch, vùng hoặc năm. Không bảo đảm phân tích lại chuỗi đó sẽ tái tạo được đúng dữ liệu gốc.

Nếu API nhận một thời điểm, dùng hợp đồng có UTC/độ lệch rõ ràng và độ chính xác được thống nhất. Nếu người dùng nhập giờ địa phương cho một lịch hẹn, cần nhận cả vùng và xử lý thiếu/trùng giờ trước khi tạo `Instant`.

Chuỗi `01/02/2026 09:00` chưa cho biết ngày/tháng theo quy ước nào và cũng chưa có múi giờ. Không tự phân tích theo locale/múi giờ mặc định của máy chủ rồi coi đó là ý định của mọi người dùng.

Đồng thời không chuyển một `LocalDateTime` không có vùng thành `Instant` chỉ bằng cách gắn `Z` vào chuỗi. Đó là bổ sung một giả định về UTC, có thể làm sai thời điểm nhiều giờ.

## 7. Sắp xếp, lọc và nhóm phải dựa trên dữ liệu phù hợp

Sắp xếp sự kiện theo mốc gốc, không theo chuỗi `dd/MM/yyyy HH:mm`; thứ tự từ điển của nhãn không phản ánh thứ tự thời gian. Hai nhãn cùng phút có thể là hai sự kiện khác nhau; giờ địa phương còn có thể xuất hiện hai lần khi lùi giờ mùa hè.

Với bộ lọc “các sự kiện của ngày hôm nay theo giờ người dùng”, vùng hiển thị trở thành đầu vào có ý nghĩa cho phép lọc. Xác định đầu ngày và đầu ngày kế tiếp trong vùng đó, chuyển hai mốc sang `Instant`, rồi lọc khoảng đầu bao gồm/cuối loại trừ.

Đây là một phép chiếu theo ngày địa phương; nó không thay đổi thời điểm sự kiện đang lưu. Không chia ngày bằng cách cố định các đoạn UTC 24 giờ nếu yêu cầu là ngày ở một vùng khác.

Khi xuất báo cáo, ghi rõ vùng đã dùng. Một cột “thời gian” không có nhãn vùng có thể làm người đọc hiểu nhầm dù giá trị lưu trữ hoàn toàn đúng.

## 8. Phạm vi: không phải mọi dữ liệu ngày giờ đều là Instant

Ngày sinh, ngày nghỉ hoặc một ngày hiệu lực thuần lịch thường là `LocalDate`; không cần chuyển thành nửa đêm UTC để áp dụng mô hình của sự kiện. Một giờ mở cửa định kỳ có thể là `LocalTime` cùng quy tắc lịch và vùng.

Với lịch hẹn tương lai cần giữ 09:00 tại địa điểm, lưu ý định địa phương và `ZoneId` có thể là cần thiết; không bỏ chúng chỉ vì đã tính một `Instant`. Quy tắc “giữ thời điểm gốc, định dạng tại giao diện” áp dụng khi dữ liệu gốc thật sự là thời điểm.

Kiểm tra độ chính xác khi đi qua DB/API, chọn rõ vùng mặc định và cách xử lý đầu vào vùng không hợp lệ. Một ưu tiên hiển thị không được vô tình trở thành một thao tác sửa dữ liệu.

## 9. Tự thực hành

1. Định dạng cùng một `Instant` ở Việt Nam và New York; kiểm tra hai kết quả `toInstant()` có bằng nhau không.
2. Đổi từ `withZoneSameInstant` sang `withZoneSameLocal` rồi giải thích vì sao thời điểm thay đổi.
3. Giới hạn hiển thị đến phút nhưng vẫn xác nhận dữ liệu gốc giữ phần lẻ giây.
4. Thiết kế bộ lọc theo một ngày địa phương bằng hai mốc `Instant`.

Đối chiếu: (1) cùng thời điểm dù ngày/giờ khác; (2) đã giữ đồng hồ địa phương thay vì thời điểm; (3) không ghi ngược chuỗi đã rút gọn; (4) lấy ranh giới đầu ngày và đầu ngày sau từ đúng `ZoneId`.