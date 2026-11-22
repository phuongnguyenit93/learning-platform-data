# Phân tích chuỗi có offset hoặc múi giờ

## Nhận ra thông tin đang xác định thời điểm

Hai chuỗi sau có cùng phần giờ trên mặt đồng hồ nhưng xác định hai thời điểm khác nhau:

```text
2024-06-15T09:30:45+07:00
2024-06-15T09:30:45Z
```

Chuỗi đầu nói “09 giờ 30 phút 45 giây tại độ lệch UTC cộng bảy giờ”; chuỗi sau nói “09 giờ 30 phút 45 giây UTC”. Nếu xóa phần đuôi để cả hai đều vừa `LocalDateTime`, ứng dụng đã mất thông tin quan trọng.

Mục tiêu của bài là đọc đúng phần đuôi, chọn kiểu Java giữ đủ dữ liệu, dùng bộ phân tích phù hợp và kiểm chứng kết quả theo hợp đồng nhập liệu.

## 1. Offset và múi giờ có vùng là hai thông tin khác nhau

**Độ lệch UTC (offset)** là độ chênh giữa giờ địa phương và UTC tại một thời điểm, chẳng hạn `+07:00`, `-04:00` hoặc `Z` cho độ lệch bằng không.

**Mã vùng múi giờ (region zone ID)** như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` chỉ đến một tập quy tắc xác định offset theo thời gian. Một vùng có thể đổi offset do giờ mùa hè hoặc thay đổi lịch sử. Một offset riêng lẻ không đủ để suy ra duy nhất mã vùng. [Tài liệu `ZoneRules`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)

Ví dụ:

```text
2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]
│                  │      │
ngày giờ           offset mã vùng múi giờ
```

Phần mã vùng trong dấu ngoặc vuông là dạng mở rộng được bộ `ISO_ZONED_DATE_TIME` của Java hỗ trợ; không nên giả định mọi hệ thống nói “ISO” đều trao đổi dạng có ngoặc này.

| Đầu vào mang gì? | Kiểu thường phù hợp |
| --- | --- |
| Ngày giờ địa phương, không offset, không vùng | `LocalDateTime` |
| Ngày giờ cùng offset | `OffsetDateTime` |
| Ngày giờ, offset và quy tắc vùng | `ZonedDateTime` |
| Một thời điểm trên dòng thời gian, không cần giữ offset/vùng gốc | `Instant` |

`OffsetDateTime` giữ ngày giờ và offset; `ZonedDateTime` giữ thêm vùng cùng quy tắc liên quan. [Tài liệu `OffsetDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html), [tài liệu `ZonedDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

Nếu đầu vào chỉ có giờ kèm offset, chẳng hạn `09:30:45+07:00`, kiểu tương ứng là `OffsetTime`. Thiếu ngày thì chưa thể suy ra duy nhất một `Instant`.

## 2. Ưu tiên bộ phân tích dựng sẵn

Với các dạng ISO thông dụng, bắt đầu bằng lời gọi trực tiếp:

```java
OffsetDateTime event =
        OffsetDateTime.parse("2024-06-15T09:30:45+07:00");

OffsetDateTime utcEvent =
        OffsetDateTime.parse("2024-06-15T02:30:45Z");

ZonedDateTime regionalEvent = ZonedDateTime.parse(
        "2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]");
```

Đây là đoạn minh họa, cần import các lớp tương ứng trong `java.time`.

`OffsetDateTime.parse` mặc định dùng `ISO_OFFSET_DATE_TIME`; `ZonedDateTime.parse` mặc định dùng `ISO_ZONED_DATE_TIME`. Không phải tạo mẫu thủ công chỉ vì chuỗi có `+`, `Z` hoặc dấu ngoặc vuông. [Các bộ định dạng ISO](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Nếu cần giữ một mốc sự kiện, chuyển kết quả sang `Instant`:

```java
Instant recordedAt = event.toInstant();
```

Với chuỗi UTC thông dụng, cũng có thể phân tích trực tiếp:

```java
Instant recordedAt = Instant.parse("2024-06-15T02:30:45Z");
```

Cần giữ riêng offset hoặc vùng gốc khi nghiệp vụ muốn biết chúng. `Instant` giữ thời điểm, không giữ cách biểu diễn địa phương ban đầu.

## 3. Chương trình hoàn chỉnh: phân tích, kiểm chứng và chuyển đổi

Lưu dưới tên `OffsetZoneParsingDemo.java`. Chương trình dùng Java 17 trở lên và thư viện chuẩn:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class OffsetZoneParsingDemo {
    static ZonedDateTime parseConsistentOffsetAndZone(String text) {
        TemporalAccessor fields =
                DateTimeFormatter.ISO_ZONED_DATE_TIME.parse(text);

        LocalDateTime local = LocalDateTime.from(fields);
        ZoneOffset offset = ZoneOffset.from(fields);
        ZoneId zone = ZoneId.from(fields);

        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-15T09:30:45+07:00");
        OffsetDateTime utc =
                OffsetDateTime.parse("2024-06-15T02:30:45Z");

        ZonedDateTime zoned = ZonedDateTime.parse(
                "2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]");

        System.out.println("offset=" + offset.getOffset());
        System.out.println("instant=" + offset.toInstant());
        System.out.println("sameInstant=" + offset.toInstant().equals(utc.toInstant()));
        System.out.println("zone=" + zoned.getZone().getId());
        System.out.println("zonedInstant=" + zoned.toInstant());

        ZonedDateTime inParis =
                offset.atZoneSameInstant(ZoneId.of("Europe/Paris"));
        System.out.println("paris=" + inParis);

        OffsetTime time = OffsetTime.parse("09:30:45+07:00");
        System.out.println("offsetTime=" + time);

        try {
            LocalDateTime.parse("2024-06-15T09:30:45+07:00");
            System.out.println("localAcceptedOffset");
        } catch (DateTimeParseException ex) {
            System.out.println("localRejectedOffset");
        }

        DateTimeFormatter custom =
                DateTimeFormatter.ofPattern(
                        "uuuu/MM/dd HH:mm:ssXXX", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        OffsetDateTime imported =
                OffsetDateTime.parse("2024/06/15 09:30:45+07:00", custom);
        System.out.println("customInstant=" + imported.toInstant());

        String conflicting =
                "2024-06-15T09:30:45+02:00[Asia/Ho_Chi_Minh]";
        System.out.println("defaultConflict=" + ZonedDateTime.parse(conflicting));

        try {
            parseConsistentOffsetAndZone(conflicting);
            System.out.println("conflictAcceptedByPolicy");
        } catch (DateTimeException ex) {
            System.out.println("conflictRejectedByPolicy");
        }

        ZonedDateTime first = parseConsistentOffsetAndZone(
                "2024-10-27T02:30:00+02:00[Europe/Paris]");
        ZonedDateTime second = parseConsistentOffsetAndZone(
                "2024-10-27T02:30:00+01:00[Europe/Paris]");

        System.out.println("firstOccurrence=" + first.toInstant());
        System.out.println("secondOccurrence=" + second.toInstant());
        System.out.println("minutesApart="
                + Duration.between(first.toInstant(), second.toInstant()).toMinutes());

        try {
            parseConsistentOffsetAndZone(
                    "2024-03-31T02:30:00+01:00[Europe/Paris]");
            System.out.println("gapAcceptedByPolicy");
        } catch (DateTimeException ex) {
            System.out.println("gapRejectedByPolicy");
        }

        Instant direct = Instant.parse("2024-06-15T02:30:45Z");
        System.out.println("directInstant=" + direct);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 OffsetZoneParsingDemo.java
java OffsetZoneParsingDemo
```

Stdout với dữ liệu múi giờ chứa các quy tắc năm 2024 được dùng trong ví dụ:

```text
offset=+07:00
instant=2024-06-15T02:30:45Z
sameInstant=true
zone=Asia/Ho_Chi_Minh
zonedInstant=2024-06-15T02:30:45Z
paris=2024-06-15T04:30:45+02:00[Europe/Paris]
offsetTime=09:30:45+07:00
localRejectedOffset
customInstant=2024-06-15T02:30:45Z
defaultConflict=2024-06-15T14:30:45+07:00[Asia/Ho_Chi_Minh]
conflictRejectedByPolicy
firstOccurrence=2024-10-27T00:30:00Z
secondOccurrence=2024-10-27T01:30:00Z
minutesApart=60
gapRejectedByPolicy
directInstant=2024-06-15T02:30:45Z
```

Các phần sau giải thích vì sao những kết quả này quan trọng khi đọc dữ liệu.

## 4. Giữ thời điểm khi đổi cách hiển thị

Trong chương trình:

```text
09:30:45 +07:00
02:30:45 Z
04:30:45 +02:00 tại Europe/Paris
```

đều mô tả cùng một thời điểm ngày 15/06/2024.

Lời gọi:

```java
offset.atZoneSameInstant(ZoneId.of("Europe/Paris"))
```

giữ nguyên thời điểm và tính cách biểu diễn trong vùng đích. Kiểm tra `toInstant()` giúp phát hiện việc vô tình giữ nguyên giờ địa phương rồi gắn vùng khác.

Đừng dùng thao tác sau làm cách “chuyển múi giờ” chung:

```java
// Minh họa cách làm thay đổi ý nghĩa khi mục tiêu là giữ thời điểm.
offset.toLocalDateTime().atZone(ZoneId.of("Europe/Paris"));
```

Phần `toLocalDateTime()` đã bỏ offset; `atZone` sau đó diễn giải lại giờ địa phương ấy theo Paris. Cách này chỉ phù hợp nếu nghiệp vụ chủ động muốn diễn giải lại giờ, không phải chuyển biểu diễn của cùng mốc sự kiện.

Ngoài ra, `equals` của kiểu có offset/vùng còn xét cấu trúc giá trị tương ứng. Nếu câu hỏi là “có phải cùng thời điểm không?”, hãy so sánh `Instant` hoặc dùng phép so sánh cùng thời điểm của kiểu phù hợp.

## 5. Trường hợp có cả offset và vùng: đừng mặc định chúng đã được đối chiếu

Chuỗi thử nghiệm:

```text
2024-06-15T09:30:45+02:00[Asia/Ho_Chi_Minh]
```

ghép giờ địa phương với offset `+02:00`, trong khi vùng `Asia/Ho_Chi_Minh` dùng `+07:00` tại mốc này.

Bộ phân giải ngày giờ có thể dùng offset để xác định thời điểm, rồi biểu diễn thời điểm đó trong vùng đã cho. Vì vậy, `ZonedDateTime.parse` trong chương trình trả về `14:30:45+07:00` thay vì tự động báo hai phần đầu vào mâu thuẫn. Quy tắc ưu tiên offset khi tính thời điểm được mô tả trong [quy trình phân giải của `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

Hành vi đó có thể phù hợp với một số giao thức, nhưng nếu hợp đồng yêu cầu **giờ địa phương, offset và vùng trong đầu vào phải nhất quán**, cần kiểm tra bổ sung.

Hàm `parseConsistentOffsetAndZone` trong chương trình thực hiện hai việc:

1. Đọc các trường ngày giờ địa phương, offset và vùng từ chuỗi.
2. Gọi `ZonedDateTime.ofStrict(local, offset, zone)` để yêu cầu offset hợp lệ với ngày giờ địa phương trong vùng đó.

Hàm này có thể ném `DateTimeParseException` khi cú pháp sai hoặc `DateTimeException` khi bộ ba không nhất quán. Ở ranh giới nhập dữ liệu, chuyển các lỗi này thành phản hồi phù hợp với ứng dụng; không tự sửa offset rồi tiếp tục âm thầm. [Tài liệu `ZonedDateTime.ofStrict`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#ofStrict(java.time.LocalDateTime,java.time.ZoneOffset,java.time.ZoneId))

`ResolverStyle.STRICT` kiểm soát phân giải trường ngày giờ; không nên hiểu nó là lời bảo đảm rằng mọi chính sách nhất quán offset–vùng của nghiệp vụ đã được thực hiện.

Hàm trên cho phép cả dạng chỉ có offset mà bộ ISO hỗ trợ, khi `ZoneId` thu được chính là offset. Nếu giao diện bắt buộc có **mã vùng** như `Europe/Paris`, còn cần kiểm tra yêu cầu đó riêng; “có một ZoneId” không đồng nghĩa “đã nhận được mã vùng từ nguồn”.

## 6. Vì sao cần quan tâm giờ mùa hè khi đầu vào chỉ có vùng?

Một ngày giờ địa phương kết hợp với vùng có thể rơi vào:

| Trường hợp | Số offset hợp lệ | Ý nghĩa với dữ liệu nhập |
| --- | ---: | --- |
| Bình thường | 1 | Xác định được một thời điểm |
| Khoảng giờ bị bỏ qua (gap) | 0 | Giờ địa phương đó không tồn tại trong vùng |
| Khoảng giờ lặp lại (overlap) | 2 | Một giờ địa phương ứng với hai thời điểm |

Ví dụ của Paris ngày 27/10/2024 cho hai chuỗi có cùng `02:30`, cùng vùng, nhưng offset khác nhau. Cả hai hợp lệ và hai `Instant` cách nhau 60 phút. Offset giúp phân biệt lần xuất hiện mà nguồn muốn nói tới.

Ngược lại, `02:30` ngày 31/03/2024 trong ví dụ rơi vào khoảng giờ bị bỏ qua; `ofStrict` từ chối tổ hợp đó.

Nếu hợp đồng chỉ cung cấp ngày giờ địa phương và mã vùng riêng, có thể kiểm tra:

```java
LocalDateTime local = LocalDateTime.parse("2024-10-27T02:30:00");
ZoneId zone = ZoneId.of("Europe/Paris");
var validOffsets = zone.getRules().getValidOffsets(local);
```

Đây là đoạn minh họa dùng các import trong chương trình. Tùy số lượng offset, ứng dụng có thể chấp nhận, từ chối hoặc yêu cầu nguồn chọn rõ offset. Việc gọi `atZone` trực tiếp có chính sách mặc định xử lý giờ bị bỏ qua/lặp lại; nó không thay bạn quyết định hợp đồng dữ liệu. [Tài liệu `getValidOffsets`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

Cũng đừng giả định chuỗi `2024-10-27T02:30:00[Europe/Paris]` được bộ ISO mặc định nhận như dạng có đầy đủ offset. Nếu nguồn chỉ gửi vùng mà không gửi offset, hãy định nghĩa cú pháp và quy tắc xử lý tính mơ hồ rõ ràng.

## 7. Khi định dạng nguồn không phải dạng ISO mặc định

Ví dụ tệp nhập dùng dấu gạch chéo và dấu cách:

```text
2024/06/15 09:30:45+07:00
```

Chương trình đã dùng mẫu:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu/MM/dd HH:mm:ssXXX", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Ở đây:

- `uuuu` là năm; `MM` là tháng; `dd` là ngày trong tháng.
- `HH:mm:ss` là giờ theo hệ 24 giờ, phút và giây.
- `XXX` đọc offset dạng có dấu hai chấm như `+07:00`, đồng thời hỗ trợ `Z` cho độ lệch bằng không.
- `VV` trong mẫu dành cho mã vùng múi giờ.
- `z` dành cho tên múi giờ dạng văn bản, không thay thế được mọi cách dùng mã vùng.

Một bẫy quan trọng: `'Z'` trong dấu nháy đơn chỉ là **chữ Z cố định**. Nó không tự tạo trường offset bằng không. Mẫu cho phép đọc một ký tự không có nghĩa kiểu kết quả đã giữ ý nghĩa UTC.

Các ký hiệu offset khác nhau theo số lần lặp và chữ hoa/chữ thường; không thay `XXX`, `xx`, `Z` cho nhau theo hình thức. Đọc bảng ký tự theo đúng hợp đồng nguồn. [Bảng mẫu `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Với giao tiếp máy–máy, ưu tiên offset số hoặc mã vùng rõ ràng. Những tên viết tắt như `CST` có thể mơ hồ; đừng dựa vào việc thư viện đoán được một vùng để kết luận dữ liệu đã đủ rõ.

## 8. Lỗi thường gặp và cách kiểm chứng

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `LocalDateTime.parse` báo còn ký tự dư | Chuỗi có offset/vùng mà kiểu hoặc bộ mặc định không nhận |
| Phân tích được nhưng mốc UTC sai | Offset bị bỏ, hoặc giờ địa phương bị gắn lại vùng khác |
| Kết quả có giờ địa phương khác đầu vào | Có thể đầu vào có offset–vùng mâu thuẫn và bộ phân giải ưu tiên offset |
| Chỉ nhận đúng ba chữ số phần lẻ | Mẫu thủ công cố định hẹp hơn hợp đồng nguồn |
| Máy này và máy khác cho kết quả khác | Kiểm tra việc dùng vùng mặc định và phiên bản dữ liệu múi giờ |
| Có mã vùng nhưng chưa chắc có thời điểm duy nhất | Kiểm tra giờ bị bỏ qua/lặp lại và sự hiện diện của offset |

Một bộ ca phù hợp nên có: offset dương, offset âm, `Z`, phần lẻ nếu được phép, thiếu offset, vùng hợp lệ/không hợp lệ, và offset–vùng không nhất quán nếu hợp đồng có cả hai. Với vùng có giờ mùa hè, thêm ca giờ lặp lại/bị bỏ qua.

Kiểm tra không chỉ “không ném ngoại lệ” mà cả `getOffset()`, `getZone()` và `toInstant()` theo thông tin cần giữ. Tránh dùng `ZoneId.systemDefault()` làm phần bù ngầm cho một dữ liệu được trao đổi giữa nhiều máy, trừ khi đó là quy định công khai của ứng dụng.

## 9. Tự thực hành

1. Chuỗi `2024-06-15T09:30:45+07:00` nên được đọc vào kiểu nào nếu cần giữ offset nguồn?
2. Vì sao `+07:00` không đủ để kết luận vùng là `Asia/Ho_Chi_Minh`?
3. Muốn hiển thị cùng sự kiện tại Paris, nên giữ giờ địa phương hay giữ `Instant`?
4. Dùng `STRICT` đã đủ bảo đảm offset và vùng trong chuỗi không mâu thuẫn chưa?
5. Hai chuỗi cùng `02:30` ở Paris vào giờ lặp lại có thể chỉ hai thời điểm khác nhau không?

Gợi ý đáp án:

1. `OffsetDateTime`, rồi chuyển sang `Instant` khi cần.
2. Nhiều vùng có thể cùng offset; offset không chứa danh tính và toàn bộ quy tắc của vùng.
3. Giữ thời điểm, chẳng hạn dùng `atZoneSameInstant`.
4. Chưa; nếu hợp đồng yêu cầu nhất quán, kiểm tra bộ ba ngày giờ địa phương–offset–vùng, chẳng hạn bằng `ofStrict`.
5. Có; ví dụ trong chương trình dùng `+02:00` và `+01:00`, cách nhau một giờ.

Phân tích đúng chuỗi có offset hoặc múi giờ là giữ đúng ý nghĩa thời gian của nguồn, đồng thời kiểm chứng những điều kiện mà giao diện dữ liệu thực sự cam kết.
