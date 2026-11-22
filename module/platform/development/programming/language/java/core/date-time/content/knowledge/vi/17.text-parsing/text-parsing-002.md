# Phân tích chuỗi ISO trước khi xây dựng mẫu tùy chỉnh

## Bắt đầu từ dữ liệu, không bắt đầu từ `ofPattern()`

Khi nhận chuỗi `2024-06-15T09:30:45+07:00`, phản xạ viết ngay một mẫu như `"yyyy-MM-dd'T'HH:mm:ssXXX"` thường làm công việc phức tạp hơn cần thiết. Thư viện `java.time` đã có bộ phân tích cho những dạng ISO thông dụng.

Việc cần làm trước là xác định chuỗi mang **ngày**, **giờ**, **ngày giờ địa phương**, hay **thời điểm có độ lệch UTC/múi giờ**. Sau đó chọn kiểu Java giữ đúng thông tin ấy và thử phương thức `parse` có sẵn. Chỉ xây dựng mẫu riêng khi hợp đồng dữ liệu thực sự khác dạng đã được hỗ trợ.

Trong bài này, “phân tích chuỗi” (parsing) là chuyển văn bản thành một giá trị thời gian có kiểu. Nó khác với “định dạng” (formatting), tức chuyển giá trị trở lại văn bản. Dạng văn bản đầu vào và cách hiển thị đầu ra không nhất thiết giống nhau từng ký tự.

## 1. Đọc cấu trúc trước, đọc ý nghĩa tiếp theo

Tách chuỗi ví dụ thành những phần có ý nghĩa:

```text
2024-06-15 T 09:30:45 +07:00
──────────   ──────── ──────
ngày         giờ      độ lệch so với UTC
           ↑
      dấu phân cách ngày và giờ
```

Các dấu hiệu giúp nhận diện:

- `2024-06-15`: ngày theo thứ tự năm–tháng–ngày.
- `09:30:45`: giờ–phút–giây, không tự cho biết ngày hay múi giờ.
- `T`: dấu phân cách giữa phần ngày và phần giờ.
- `.123` sau giây: phần lẻ của giây.
- `Z`: độ lệch UTC bằng không.
- `+07:00`: độ lệch UTC dương bảy giờ; đây chưa phải tên một vùng múi giờ.
- `[Asia/Ho_Chi_Minh]`: mã vùng múi giờ trong dạng mở rộng mà Java hỗ trợ cho ngày giờ có múi giờ.

Dấu `Z` và `+07:00` không phải phần trang trí để xóa cho dễ đọc. Chúng góp phần xác định thời điểm.

Một mẫu trông gần giống ISO chưa chắc khớp với bộ phân tích mặc định: `2024-06-15 09:30:45` có dấu cách thay cho `T`. Ngược lại, ISO cũng không chỉ có một dạng duy nhất: thư viện còn có bộ định dạng cho ngày dạng liền, ngày theo thứ tự trong năm hoặc ngày theo tuần. Hãy kiểm tra đúng biến thể được giao tiếp, thay vì khẳng định mọi chuỗi “ISO” đều được một phương thức nhận.

## 2. Chọn kiểu đích phù hợp với thông tin đầu vào

| Chuỗi ví dụ | Kiểu đích thường phù hợp | Lời gọi ban đầu |
| --- | --- | --- |
| `2024-06-15` | `LocalDate` | `LocalDate.parse(text)` |
| `09:30:45` | `LocalTime` | `LocalTime.parse(text)` |
| `2024-06-15T09:30:45` | `LocalDateTime` | `LocalDateTime.parse(text)` |
| `2024-06-15T09:30:45+07:00` | `OffsetDateTime` | `OffsetDateTime.parse(text)` |
| `2024-06-15T02:30:45Z` | `Instant` nếu cần mốc trên dòng thời gian | `Instant.parse(text)` |
| `2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | `ZonedDateTime.parse(text)` |

Các phương thức mặc định dùng bộ định dạng ISO tương ứng; chẳng hạn `LocalDate.parse` dùng `ISO_LOCAL_DATE`, còn `OffsetDateTime.parse` dùng `ISO_OFFSET_DATE_TIME`. [Tài liệu `LocalDate.parse`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence)), [tài liệu `OffsetDateTime.parse`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html#parse(java.lang.CharSequence))

Một vài điểm cần giữ rõ khi chọn kiểu:

- `LocalDate` không giữ giờ và múi giờ; phù hợp với một ngày học hay ngày sinh.
- `LocalDateTime` không đủ thông tin để tự xác định duy nhất một thời điểm toàn cầu.
- `OffsetDateTime` giữ ngày giờ cùng độ lệch UTC. Chuyển nó sang `Instant` khi cần so sánh hoặc lưu một thời điểm mà không cần giữ độ lệch gốc.
- `ZonedDateTime` giữ thêm mã vùng và quy tắc múi giờ.
- `Instant` đại diện một điểm trên dòng thời gian; chuỗi UTC kết thúc bằng `Z` là dạng thường gặp khi truyền mốc sự kiện. [Tài liệu `Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Ví dụ, nếu thông báo nộp bài đến lúc `09:30:45+07:00`, bỏ `+07:00` rồi giữ `LocalDateTime` sẽ làm mất thông tin thời điểm. Cách thuận tiện khi phân tích chuỗi không được làm thay đổi ý nghĩa của dữ liệu.

## 3. Một chương trình đầy đủ: dùng bộ phân tích có sẵn

Lưu dưới tên `IsoParsingDemo.java`. Chương trình chạy với Java 17 trở lên:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class IsoParsingDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.parse("2024-06-15");
        LocalTime time = LocalTime.parse("09:30:45");
        LocalDateTime local =
                LocalDateTime.parse("2024-06-15T09:30:45.123");

        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-15T09:30:45+07:00");
        Instant instant = Instant.parse("2024-06-15T02:30:45Z");

        ZonedDateTime zoned = ZonedDateTime.parse(
                "2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]");

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("local=" + local);
        System.out.println("offset=" + offset);
        System.out.println("instant=" + instant);
        System.out.println("sameInstant=" + offset.toInstant().equals(instant));
        System.out.println("zone=" + zoned.getZone().getId());

        LocalDate basic =
                LocalDate.parse("20240615", DateTimeFormatter.BASIC_ISO_DATE);
        System.out.println("basic=" + basic);

        try {
            LocalDate.parse("2023-02-29");
            System.out.println("invalidDateAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalidDateRejected");
        }

        try {
            LocalDateTime.parse("2024-06-15 09:30:45");
            System.out.println("spaceAcceptedByDefault");
        } catch (DateTimeParseException ex) {
            System.out.println("spaceRejectedByDefault");
        }

        DateTimeFormatter spaceSeparated =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDateTime imported = LocalDateTime.parse(
                "2024-06-15 09:30:45", spaceSeparated);
        System.out.println("custom=" + imported);

        LocalTime shortTime = LocalTime.parse("09:30:00");
        System.out.println("shortTime=" + shortTime);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 IsoParsingDemo.java
java IsoParsingDemo
```

Stdout:

```text
date=2024-06-15
time=09:30:45
local=2024-06-15T09:30:45.123
offset=2024-06-15T09:30:45+07:00
instant=2024-06-15T02:30:45Z
sameInstant=true
zone=Asia/Ho_Chi_Minh
basic=2024-06-15
invalidDateRejected
spaceRejectedByDefault
custom=2024-06-15T09:30:45
shortTime=09:30
```

Đọc kết quả theo từng nhóm:

1. Các chuỗi ISO thông dụng được chuyển trực tiếp thành kiểu có ý nghĩa, không cần mẫu tự viết.
2. Hai chuỗi `09:30:45+07:00` và `02:30:45Z` xác định cùng một thời điểm; `sameInstant=true` chứng minh phép phân tích giữ đúng độ lệch.
3. Chuỗi ngày dạng liền `20240615` cần bộ `BASIC_ISO_DATE`, nhưng vẫn chưa cần `ofPattern`.
4. Ngày 29/02/2023 không tồn tại nên bị từ chối.
5. Dạng có dấu cách bị bộ mặc định của `LocalDateTime` từ chối; mẫu riêng được dùng vì hợp đồng nhập liệu ở đây đã xác định dấu cách.
6. `shortTime=09:30` cho thấy giá trị thời gian được giữ đúng dù chuỗi khi in ra không giữ nguyên `:00` của đầu vào.

## 4. Có bộ ISO dựng sẵn không có nghĩa là mọi biến thể đều được chấp nhận

Quy trình tra cứu nên đi theo ba nấc:

```text
Đã biết kiểu thời gian và dạng ISO mặc định?
    └─ Có: thử Type.parse(text)

Khác dạng mặc định nhưng có hằng DateTimeFormatter tương ứng?
    └─ Có: dùng Type.parse(text, formatterCóSẵn)

Hợp đồng thực sự có cú pháp riêng?
    └─ Xây dựng mẫu hoặc DateTimeFormatterBuilder phù hợp
```

Ví dụ các hằng thường hữu ích:

| Hằng | Mục đích |
| --- | --- |
| `ISO_LOCAL_DATE` | Ngày dạng `2024-06-15` |
| `ISO_LOCAL_TIME` | Giờ địa phương |
| `ISO_LOCAL_DATE_TIME` | Ngày giờ địa phương, có `T` |
| `ISO_OFFSET_DATE_TIME` | Ngày giờ có độ lệch UTC |
| `ISO_ZONED_DATE_TIME` | Ngày giờ có thông tin vùng múi giờ |
| `BASIC_ISO_DATE` | Ngày dạng liền như `20240615` |

Danh sách dựng sẵn và cú pháp chi tiết có trong [tài liệu `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

Bộ ISO dựng sẵn còn xử lý các thành phần được phép tùy chọn theo từng dạng, chẳng hạn phần giây hoặc phần lẻ của giây. Một mẫu thủ công cố định `HH:mm:ss.SSS` lại thể hiện yêu cầu số chữ số cụ thể. Đừng sao chép mẫu dài từ một chuỗi mẫu duy nhất rồi giả định nó bao quát toàn bộ hợp đồng.

Cũng không nên đổi sang `ISO_DATE_TIME` rộng hơn chỉ để một lần phân tích hết lỗi. Nếu giao diện yêu cầu bắt buộc có độ lệch UTC, cần bảo đảm kiểu đích và bộ phân tích thực sự giữ, kiểm tra thông tin ấy.

## 5. Khi nào một mẫu tùy chỉnh có lý do rõ ràng?

Mẫu riêng có ý nghĩa khi nguồn dữ liệu quy định rõ, ví dụ:

- Tệp nhập cũ dùng `15/06/2024`.
- Ngày giờ dùng dấu cách cố định: `2024-06-15 09:30:45`.
- Tên tháng bằng ngôn ngữ cụ thể xuất hiện trong dữ liệu.
- Đầu vào cần quy tắc cú pháp mà bộ có sẵn không đáp ứng.

Đối với ví dụ dấu cách, chương trình đã khai báo:

```java
DateTimeFormatter spaceSeparated =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Các lựa chọn có chủ đích:

- `uuuu` là năm theo hệ lịch; `yyyy` là năm trong kỷ nguyên, không đồng nghĩa trong mọi tình huống.
- `MM` là tháng, `mm` là phút.
- `HH` là giờ theo hệ 24 giờ.
- `STRICT` yêu cầu kết hợp trường phải tạo được ngày giờ hợp lệ.
- `Locale.ROOT` thể hiện cấu hình độc lập ngôn ngữ cho mẫu số trong ví dụ; nếu mẫu chứa tên tháng, cần chọn đúng ngôn ngữ của dữ liệu.

Mẫu do `ofPattern` tạo mặc định có chế độ phân giải `SMART`; vì vậy, đừng mặc định nó có cùng quy tắc xử lý ngày không tồn tại với bộ ISO chặt chẽ. [Tài liệu tạo mẫu và phân giải](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#ofPattern(java.lang.String))

Đây chỉ là các điểm cần biết để quyết định có cần mẫu riêng. Trước khi mở rộng mẫu cho nhiều dạng, hãy viết rõ những dạng được phép nhận và những dạng phải từ chối.

## 6. Xử lý lỗi theo hợp đồng dữ liệu

`DateTimeParseException` không tự chứng minh rằng cần thêm một mẫu. Nó có thể báo:

- Sai cú pháp: dấu cách thay cho `T`, dấu phân cách không đúng hoặc còn ký tự dư.
- Ngày giờ không hợp lệ: tháng 13, ngày không tồn tại.
- Sai kiểu đích: chuỗi chỉ có ngày nhưng mã lại yêu cầu `LocalDateTime`.
- Thiếu thông tin bắt buộc: hợp đồng cần độ lệch UTC nhưng chuỗi không có.
- Dữ liệu rỗng hoặc khác hoàn toàn định dạng đã thống nhất.

Trước khi sửa mã, lấy một chuỗi đầu vào đại diện và hỏi theo thứ tự: nguồn cam kết dạng gì, chuỗi này có đúng cam kết không, kiểu đích có phù hợp không, rồi mới kiểm tra bộ phân tích.

Ví dụ khung xử lý dưới đây là đoạn minh họa, cần các import `LocalDate` và `DateTimeParseException`:

```java
static LocalDate parseLearningDate(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("Ngay hoc khong duoc rong");
    }

    try {
        return LocalDate.parse(text);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Ngay hoc phai la ngay hop le dang ISO nam-thang-ngay", ex);
    }
}
```

Đoạn này yêu cầu chuỗi đúng dạng ISO đã chọn, không tự `trim()` và không trả về ngày hiện tại khi thất bại. Nếu giao diện cho phép khoảng trắng ngoài cùng, có thể chuẩn hóa theo quy tắc công khai trước khi gọi hàm. Nếu đây là giao thức yêu cầu chuỗi chính xác, giữ nguyên đầu vào để phát hiện lỗi.

Không dùng thao tác `substring`, `replace("T", " ")` hoặc xóa `Z` làm cách sửa chung. Những thao tác đó có thể khiến chuỗi dễ khớp một mẫu hơn nhưng làm mất dữ liệu hoặc che lỗi đầu vào.

## 7. Kiểm chứng cả ý nghĩa, không chỉ việc “không ném lỗi”

Với ví dụ ngày giờ có độ lệch, việc phân tích thành công mới là một phần của kiểm chứng. Hãy kiểm tra cả:

- Kiểu kết quả có giữ đủ thông tin không.
- Các thành phần ngày, giờ và phần lẻ có đúng không.
- Khi có độ lệch, `toInstant()` có cho mốc dự kiến không.
- Dữ liệu sai có bị từ chối đúng không.
- Đầu vào có thành phần tùy chọn đã được hợp đồng cho phép có hoạt động không.

Một bộ ca nhỏ cho hợp đồng `LocalDate` dạng `2024-06-15` có thể gồm:

| Đầu vào | Kết quả dự kiến |
| --- | --- |
| `2024-02-29` | Chấp nhận |
| `2023-02-29` | Từ chối |
| `2024-13-01` | Từ chối |
| `15/06/2024` | Từ chối nếu hợp đồng chỉ cho dạng ISO này |
| `20240615` | Từ chối với parse mặc định; chỉ nhận khi chủ động chọn dạng liền |
| `2024-06-15abc` | Từ chối |

Ngoài ra, “phân tích rồi in ra” không phải lúc nào cũng tái tạo nguyên văn đầu vào. Trong chương trình, `09:30:00` trở thành `09:30`. Nếu cần lưu nguyên văn để truy vết dữ liệu nguồn, lưu văn bản gốc riêng; nếu cần đầu ra có đúng số chữ số, định dạng đầu ra theo hợp đồng rõ ràng.

## 8. Tự thực hành

1. Một API gửi `2024-06-15T09:30:45+07:00`. Nên thử lời gọi nào trước khi viết mẫu riêng?
2. Một tệp gửi `20240615`. Có nhất thiết cần `ofPattern("uuuuMMdd")` không?
3. Vì sao xóa `+07:00` rồi dùng `LocalDateTime` có thể làm sai dữ liệu?
4. Chuỗi `2023-02-29` bị từ chối. Có nên thêm mẫu dự phòng để “đọc được” không?

Gợi ý đáp án:

1. `OffsetDateTime.parse(text)`; nếu cần một thời điểm thuần túy, chuyển kết quả sang `Instant`.
2. Không. Có thể dùng `LocalDate.parse(text, DateTimeFormatter.BASIC_ISO_DATE)`.
3. Vì độ lệch tham gia xác định thời điểm; `LocalDateTime` không giữ thông tin đó.
4. Không. Ngày ấy không tồn tại; cần xử lý dữ liệu không hợp lệ theo hợp đồng.

Thói quen cần hình thành là đọc cấu trúc và ý nghĩa của chuỗi, chọn kiểu đích, tận dụng bộ ISO có sẵn, rồi chỉ bổ sung mẫu khi có khác biệt đầu vào cụ thể cần hỗ trợ.
