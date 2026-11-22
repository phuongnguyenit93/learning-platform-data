# Phân biệt Instant, LocalDateTime và ZonedDateTime trong Java 17

Java 17 cung cấp API ngày giờ hiện đại trong package `java.time`. Ba kiểu thường gặp là **`Instant`**, **`LocalDateTime`** và **`ZonedDateTime`**, nhưng chúng biểu diễn ba khái niệm khác nhau:

- `Instant` là một **thời điểm trên timeline**, độc lập với múi giờ hiển thị.
- `LocalDateTime` là **ngày và giờ trên đồng hồ địa phương**, không kèm múi giờ hoặc offset nên chưa xác định được một thời điểm duy nhất.
- `ZonedDateTime` là **ngày giờ địa phương gắn với một múi giờ có quy tắc**, trong đó offset cụ thể được xác định cho ngày giờ đó.

Chọn nhầm kiểu có thể làm lịch hẹn lệch giờ, dữ liệu log khó đối chiếu hoặc thời điểm bị diễn giải sai khi người dùng ở múi giờ khác. Bài này giải thích cách chọn, tạo, chuyển đổi, parse, xử lý giờ mùa hè (DST) và kiểm thử ba kiểu bằng API chính thức của Java 17.

## 1. Ba khái niệm cần phân biệt

Hãy xét một sự kiện xảy ra tại một thời điểm thực tế. Người ở Việt Nam có thể thấy sự kiện lúc 15:00, trong khi người ở Paris nhìn thấy cùng sự kiện lúc 09:00 hoặc 10:00 tùy ngày và quy tắc DST. Hai cách hiển thị khác nhau nhưng có thể cùng chỉ đến **một instant**.

| Kiểu | Biểu diễn | Có đủ thông tin để xác định một instant? | Trường hợp dùng phù hợp |
| --- | --- | --- | --- |
| `Instant` | Số thời gian trên timeline UTC | Có | Thời điểm sự kiện đã xảy ra, timestamp log, thời điểm tạo bản ghi |
| `LocalDateTime` | Năm-tháng-ngày và giờ-phút-giây-nano | Không | Giờ mở cửa, giờ hẹn chưa gắn múi giờ, ngày giờ trên biểu mẫu |
| `ZonedDateTime` | Local date-time + zone ID + offset hợp lệ | Có | Hiển thị thời điểm tại một vùng, lịch hẹn gắn múi giờ |

Một ví dụ:

~~~java
Instant instant = Instant.parse("2026-11-15T08:00:00Z");

ZonedDateTime vietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime paris =
        instant.atZone(ZoneId.of("Europe/Paris"));

System.out.println(vietnam);
System.out.println(paris);
~~~

Cả hai `ZonedDateTime` đều biểu diễn cùng `Instant`. Phần ngày giờ địa phương khác nhau vì múi giờ có offset khác nhau tại thời điểm đó.

## 2. Instant: thời điểm trên timeline

`Instant` biểu diễn một điểm trên timeline, tính theo giây và phần nano giây kể từ epoch 1970-01-01T00:00:00Z. Ký hiệu `Z` cho biết UTC (offset zero).

~~~java
import java.time.Instant;

public class InstantDemo {
    public static void main(String[] args) {
        Instant now = Instant.now();
        Instant event = Instant.parse("2026-11-15T08:30:00Z");

        System.out.println("now   = " + now);
        System.out.println("event = " + event);
    }
}
~~~

`Instant.now()` lấy thời điểm hiện tại từ clock hệ thống. `Instant.parse(...)` đọc biểu diễn ISO-8601 có offset UTC trong ví dụ.

### 2.1. Instant không chứa múi giờ địa phương

Một `Instant` không lưu tên vùng như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`. Nó xác định thời điểm tuyệt đối; khi cần hiển thị, phải chọn một zone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T08:30:00Z");

ZonedDateTime local = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(local);
~~~

Zone được dùng để diễn giải/hiển thị instant, không làm thay đổi instant ban đầu.

### 2.2. Các phép toán trên Instant

`Instant` hỗ trợ cộng/trừ khoảng thời gian tuyến tính:

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");

Instant end = start.plusSeconds(90);
Duration elapsed = Duration.between(start, end);

System.out.println(end);
System.out.println(elapsed.toSeconds()); // 90
~~~

Các đơn vị như giây, mili giây, micro giây và nano giây phù hợp với timeline. `Instant` không tự biết “ngày mai lúc 9 giờ tại Hà Nội”; đó là quy tắc lịch địa phương và cần thêm zone.

### 2.3. Dùng Instant cho dữ liệu đã xảy ra

Nên dùng `Instant` cho:

- Thời điểm một đơn hàng được tạo hoặc thanh toán.
- Thời điểm request đến server.
- Thời điểm log hoặc audit event.
- Thời điểm một job thực sự bắt đầu/kết thúc.
- Timestamp trao đổi giữa các dịch vụ.

Khi hiển thị, chuyển instant sang zone của người xem. Khi lưu trữ, một instant giữ nguyên ý nghĩa bất kể server hay người dùng đang ở múi giờ nào.

## 3. LocalDateTime: ngày giờ địa phương chưa có zone

`LocalDateTime` gồm các thành phần lịch và đồng hồ, ví dụ `2026-11-15T15:30`. Nó **không chứa offset và không chứa zone ID**.

~~~java
import java.time.LocalDateTime;

public class LocalDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime meeting =
                LocalDateTime.of(2026, 11, 15, 15, 30);

        System.out.println(meeting);
    }
}
~~~

Giá trị này chỉ nói “ngày 15 tháng 11 năm 2026, lúc 15 giờ 30”. Nếu chưa biết múi giờ, không thể kết luận đó là instant nào trên timeline.

Cùng một `LocalDateTime` có thể ứng với những thời điểm khác nhau ở Hà Nội, Tokyo hoặc Paris. Ở một số vùng và thời điểm chuyển DST, một local date-time thậm chí có thể không tồn tại hoặc xuất hiện hai lần.

### 3.1. Khi nào dùng LocalDateTime?

Phù hợp khi dữ liệu được định nghĩa theo đồng hồ địa phương và zone sẽ được cung cấp ở bước khác, ví dụ:

- Người dùng nhập giờ hẹn nhưng biểu mẫu lưu zone ở một trường riêng.
- Giờ bắt đầu và kết thúc ca làm theo quy định của địa điểm.
- Lịch mở cửa: 08:00–17:00, lặp theo ngày trong tuần.
- Thời gian trên hóa đơn hoặc tài liệu chỉ biểu diễn ngày giờ tại một địa điểm đã được ngữ cảnh xác định.

Không dùng `LocalDateTime` một mình làm timestamp toàn hệ thống nếu cần biết chính xác sự kiện xảy ra trước hay sau một sự kiện khác.

### 3.2. LocalDateTime không phải UTC

Tên “local” không có nghĩa là giờ của máy hiện tại và cũng không có nghĩa UTC. Nó chỉ là các thành phần ngày giờ không kèm thông tin zone.

~~~java
LocalDateTime local = LocalDateTime.now();
~~~

Lời gọi trên lấy các thành phần ngày giờ theo múi giờ mặc định của hệ thống tại thời điểm gọi. Nhưng sau khi tạo, giá trị `LocalDateTime` không lưu múi giờ đó. Nếu cần xác định zone ngay từ đầu, truyền `ZoneId` rõ ràng:

~~~java
LocalDateTime vietnamNow =
        LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Kết quả vẫn là `LocalDateTime`; thông tin `Asia/Ho_Chi_Minh` chỉ được dùng để lấy giờ tại thời điểm gọi, không được lưu trong đối tượng.

### 3.3. LocalDateTime không thể tự chuyển thành Instant

Đoạn sau không có API hợp lệ vì thiếu zone/offset:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 15, 15, 30);

// Không có local.toInstant() không tham số:
// một local date-time chưa đủ thông tin để xác định instant.
~~~

Cần cung cấp `ZoneId` hoặc `ZoneOffset` để giải quyết ngày giờ địa phương thành một thời điểm.

## 4. ZonedDateTime: ngày giờ gắn với múi giờ

`ZonedDateTime` kết hợp:

1. `LocalDateTime` – thành phần ngày giờ trên đồng hồ địa phương.
2. `ZoneId` – tên vùng và tập quy tắc múi giờ.
3. `ZoneOffset` – offset cụ thể được áp dụng tại thời điểm đó.

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedDateTimeDemo {
    public static void main(String[] args) {
        ZonedDateTime meeting = ZonedDateTime.of(
                2026, 11, 15, 15, 30, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(meeting);
        System.out.println(meeting.getZone());
        System.out.println(meeting.getOffset());
    }
}
~~~

Kết quả có dạng:

~~~text
2026-11-15T15:30+07:00[Asia/Ho_Chi_Minh]
Asia/Ho_Chi_Minh
+07:00
~~~

`Asia/Ho_Chi_Minh` là zone ID; `+07:00` là offset áp dụng cho local date-time đó.

### 4.1. ZoneId và ZoneOffset không giống nhau

- `ZoneOffset` là độ lệch cố định so với UTC, ví dụ `+07:00` hoặc `-05:00`.
- `ZoneId` thường là ID vùng như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` và gắn với bộ quy tắc lịch sử/tương lai được cung cấp bởi cơ sở dữ liệu múi giờ (tzdb).
- Một zone vùng có thể dùng nhiều offset khác nhau theo ngày do lịch sử thay đổi pháp lý hoặc DST.

`ZoneOffset.UTC` là một zone cố định hợp lệ. Nhưng dùng `ZoneOffset.ofHours(7)` thay cho `ZoneId.of("Asia/Ho_Chi_Minh")` sẽ bỏ mất ý nghĩa tên vùng và các quy tắc của nó. Chỉ dùng offset cố định khi hợp đồng dữ liệu thực sự yêu cầu offset cố định.

### 4.2. Chuyển ZonedDateTime sang Instant

~~~java
ZonedDateTime zoned = ZonedDateTime.of(
        2026, 11, 15, 15, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant instant = zoned.toInstant();
~~~

Chuyển sang `Instant` giữ nguyên thời điểm trên timeline. Sau đó có thể hiển thị cùng instant ở zone khác:

~~~java
ZonedDateTime tokyo = instant.atZone(ZoneId.of("Asia/Tokyo"));
~~~

### 4.3. ZonedDateTime có thể tạo Instant

Khác `LocalDateTime`, `ZonedDateTime` đã có đủ thông tin để xác định thời điểm. Phương thức `toInstant()` chuyển nó thành `Instant` mà không cần tham số.

## 5. Bảng lựa chọn nhanh

| Câu hỏi của bài toán | Kiểu thường phù hợp | Lý do |
| --- | --- | --- |
| Sự kiện thực sự xảy ra lúc nào? | `Instant` | Xác định một thời điểm duy nhất |
| Người dùng hẹn lúc 09:00 ở chi nhánh Paris? | `LocalDateTime` + `ZoneId` hoặc `ZonedDateTime` | Cần giữ giờ địa phương và vùng |
| Hiển thị timestamp cho người dùng ở Việt Nam? | `Instant` chuyển sang `ZonedDateTime` | Giữ instant, đổi cách nhìn |
| Ca làm lặp lại từ 08:00 đến 17:00 mỗi ngày tại một nơi? | `LocalTime` và zone của địa điểm | Đây là quy tắc giờ địa phương, không phải một instant duy nhất |
| Ngày sinh không quan tâm giờ/múi giờ? | `LocalDate` | Chỉ có ngày lịch |
| Một thời điểm có offset cố định nhưng không cần quy tắc vùng? | `OffsetDateTime` hoặc `Instant` tùy hợp đồng | Offset và zone ID có ý nghĩa khác nhau |

Không chọn kiểu chỉ vì nó có nhiều trường hơn. Hãy chọn theo ý nghĩa của dữ liệu mà hệ thống cần bảo toàn.

## 6. Chuyển đổi giữa ba kiểu

### 6.1. Instant sang ZonedDateTime

Đây là chuyển đổi thường gặp khi hiển thị timestamp:

~~~java
Instant instant = Instant.parse("2026-11-15T08:00:00Z");

ZonedDateTime hanoi =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime tokyo =
        instant.atZone(ZoneId.of("Asia/Tokyo"));

System.out.println(hanoi);
System.out.println(tokyo);
System.out.println(hanoi.toInstant().equals(tokyo.toInstant())); // true
~~~

Cả hai đối tượng có local time và zone khác nhau nhưng cùng biểu diễn một instant.

### 6.2. LocalDateTime sang ZonedDateTime

Khi người dùng nhập ngày giờ địa phương và ứng dụng đã biết zone:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 11, 15, 15, 0);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

`atZone(zone)` áp dụng quy tắc của zone để tìm offset hợp lệ. Với ngày giờ bình thường, thường có đúng một offset. Nhưng khi chuyển DST, có thể có zero hoặc hai offset hợp lệ; phần sau giải thích chi tiết.

### 6.3. LocalDateTime sang Instant qua ZoneOffset

Nếu hợp đồng đã cung cấp offset cố định:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 11, 15, 15, 0);

Instant instant = local.toInstant(ZoneOffset.ofHours(7));
~~~

Cách này xác định instant dựa trên offset. Nó không tra quy tắc vùng như `Asia/Ho_Chi_Minh`. Nếu dữ liệu biểu diễn giờ địa phương của một vùng có quy tắc DST, hãy dùng `ZoneId` thay vì tự đoán offset.

### 6.4. Instant không thể suy ra LocalDateTime nếu không chọn zone

~~~java
Instant instant = Instant.now();

LocalDateTime utcFields =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);

LocalDateTime hanoiFields =
        LocalDateTime.ofInstant(
                instant,
                ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Hai `LocalDateTime` khác nhau vì zone được chọn khác nhau. Bản thân `Instant` vẫn giữ nguyên.

## 7. Hai cách đổi múi giờ: giữ instant hay giữ giờ địa phương

`ZonedDateTime` có hai thao tác dễ nhầm:

- `withZoneSameInstant(zone)`: **giữ nguyên instant**, đổi giờ địa phương và offset để hiển thị ở zone mới.
- `withZoneSameLocal(zone)`: cố gắng **giữ nguyên giờ địa phương**, thay zone và giải quyết offset mới; do DST, giờ địa phương có thể phải điều chỉnh nếu không hợp lệ.

### 7.1. Giữ cùng một thời điểm

~~~java
ZonedDateTime hanoi = ZonedDateTime.of(
        2026, 11, 15, 15, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime paris = hanoi.withZoneSameInstant(
        ZoneId.of("Europe/Paris"));

System.out.println(hanoi.toInstant().equals(paris.toInstant())); // true
~~~

Giờ ở Paris sẽ được tính theo offset của Paris vào instant đó. Đây là lựa chọn đúng khi hiển thị cùng một sự kiện cho người dùng ở các múi giờ khác nhau.

### 7.2. Giữ cùng giờ địa phương

~~~java
ZonedDateTime hanoi = ZonedDateTime.of(
        2026, 11, 15, 15, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime parisSameLocal = hanoi.withZoneSameLocal(
        ZoneId.of("Europe/Paris"));

System.out.println(hanoi.toLocalDateTime());
System.out.println(parisSameLocal.toLocalDateTime());
System.out.println(hanoi.toInstant().equals(parisSameLocal.toInstant()));
~~~

Trong ngày giờ bình thường, hai local date-time có thể giống nhau, nhưng instant khác nhau vì offset khác nhau. Đây là ý nghĩa của “giữ cùng giờ trên đồng hồ”, không phải giữ cùng sự kiện trên timeline.

### 7.3. Chọn đúng thao tác

| Mục tiêu | Dùng |
| --- | --- |
| Một cuộc họp đã chốt instant, hiển thị cho người dùng ở zone khác | `withZoneSameInstant` |
| Chuyển quy tắc “vẫn 09:00” sang một zone khác | `withZoneSameLocal`, sau khi xác định nghiệp vụ |
| Chuyển ngày giờ người dùng nhập thành thời điểm | `LocalDateTime.atZone(zone)` và xử lý DST |
| Chỉ đổi định dạng chuỗi, không đổi dữ liệu | `DateTimeFormatter` |

## 8. DST: vì sao một LocalDateTime có thể không xác định duy nhất?

Một số vùng điều chỉnh đồng hồ theo mùa (Daylight Saving Time, DST). Khi chuyển sang giờ mùa hè, đồng hồ có thể nhảy tới trước và bỏ qua một khoảng local time. Khi trở lại giờ chuẩn, đồng hồ có thể quay lùi và lặp lại một khoảng local time.

Vì thế, với một `LocalDateTime` trong một zone, có ba trường hợp:

1. **Normal:** đúng một offset hợp lệ.
2. **Gap:** không có offset hợp lệ vì đồng hồ nhảy qua khoảng giờ đó.
3. **Overlap:** có hai offset hợp lệ vì đồng hồ lặp lại khoảng giờ đó.

Không phải tất cả các zone đều dùng DST; ví dụ `Asia/Ho_Chi_Minh` hiện dùng offset +07:00 không có quy tắc DST theo dữ liệu tzdb hiện hành. Nhưng ứng dụng xử lý lịch toàn cầu cần tính đến quy tắc của từng vùng.

### 8.1. Kiểm tra bằng ZoneRules

`ZoneId` cung cấp `ZoneRules` để tra offset hợp lệ tại một `LocalDateTime`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId paris = ZoneId.of("Europe/Paris");
ZoneRules rules = paris.getRules();

LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

System.out.println(rules.getValidOffsets(local));
System.out.println(rules.getTransition(local));
~~~

Với quy tắc DST của Paris ở ngày ví dụ, `02:30` nằm trong gap nên danh sách offset hợp lệ rỗng. `getTransition(local)` cung cấp thông tin về chuyển đổi gây ra gap.

Đây là lý do `LocalDateTime` một mình không thể biểu diễn chính xác một sự kiện trên timeline.

### 8.2. Gap: giờ địa phương không tồn tại

Ở Paris ngày 31-03-2024, đồng hồ chuyển từ 02:00 lên 03:00. Vì vậy `2024-03-31T02:30` không tồn tại theo quy tắc vùng đó.

Khi gọi:

~~~java
LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

ZonedDateTime resolved = local.atZone(ZoneId.of("Europe/Paris"));

System.out.println(resolved);
~~~

Java điều chỉnh giờ địa phương tiến lên theo độ dài gap để tạo thời điểm hợp lệ. Với ví dụ này, kết quả là:

~~~text
2024-03-31T03:30+02:00[Europe/Paris]
~~~

Đây là hành vi mặc định của `atZone` khi local date-time rơi vào gap. Nó thuận tiện cho nhiều tình huống, nhưng không phải lúc nào cũng là quy tắc nghiệp vụ mong muốn. Ví dụ đặt lịch tàu hoặc ca trực có thể yêu cầu từ chối giờ không tồn tại thay vì tự đẩy sang giờ sau.

### 8.3. Overlap: giờ địa phương xuất hiện hai lần

Ở Paris ngày 27-10-2024, khoảng giờ từ 02:00 đến 02:59 xuất hiện hai lần: một lần với offset mùa hè +02:00 và một lần với offset chuẩn +01:00.

~~~java
LocalDateTime local =
        LocalDateTime.of(2024, 10, 27, 2, 30);

ZoneId paris = ZoneId.of("Europe/Paris");

System.out.println(paris.getRules().getValidOffsets(local));
~~~

Kết quả có hai offset hợp lệ:

~~~text
[+02:00, +01:00]
~~~

Có hai instant khác nhau cùng hiển thị là 02:30. `LocalDateTime` không thể phân biệt hai lần xuất hiện này.

`ZonedDateTime.of(...)` và `LocalDateTime.atZone(...)` mặc định chọn offset sớm hơn trong overlap (thường là offset mùa hè, ở ví dụ này +02:00). Nếu cần chọn lần xuất hiện còn lại, dùng `withLaterOffsetAtOverlap()`:

~~~java
ZonedDateTime first = local.atZone(paris);
ZonedDateTime second = first.withLaterOffsetAtOverlap();

System.out.println(first);
System.out.println(second);
System.out.println(Duration.between(
        first.toInstant(), second.toInstant()).toMinutes());
~~~

Kết quả:

~~~text
2024-10-27T02:30+02:00[Europe/Paris]
2024-10-27T02:30+01:00[Europe/Paris]
60
~~~

Hai giờ hiển thị giống nhau, nhưng instant cách nhau 60 phút.

### 8.4. Từ chối giờ gap hoặc yêu cầu người dùng chọn overlap

Nếu ứng dụng cần kiểm soát chặt, hãy tra offset hợp lệ trước:

~~~java
List<ZoneOffset> offsets =
        paris.getRules().getValidOffsets(local);

if (offsets.isEmpty()) {
    throw new IllegalArgumentException(
            "Giờ địa phương không tồn tại do chuyển DST");
}

if (offsets.size() == 2) {
    // Yêu cầu nghiệp vụ chọn offset sớm hoặc muộn.
}
~~~

Với trường hợp overlap, có thể lưu lựa chọn offset cùng lịch hẹn để xác định đúng instant. Nếu chỉ gọi `atZone` và không ghi lại chính sách lựa chọn, ứng dụng đang ngầm chấp nhận quy tắc mặc định của Java.

## 9. Parse và format ba kiểu bằng ISO-8601

`java.time` cung cấp formatter ISO dựng sẵn, phù hợp cho nhiều định dạng trao đổi.

| Kiểu | Formatter | Ví dụ |
| --- | --- | --- |
| `Instant` | `DateTimeFormatter.ISO_INSTANT` | `2026-11-15T08:30:00Z` |
| `LocalDateTime` | `DateTimeFormatter.ISO_LOCAL_DATE_TIME` | `2026-11-15T15:30:00` |
| `ZonedDateTime` | `DateTimeFormatter.ISO_ZONED_DATE_TIME` | `2026-11-15T15:30:00+07:00[Asia/Ho_Chi_Minh]` |

Parse:

~~~java
Instant instant =
        Instant.parse("2026-11-15T08:30:00Z");

LocalDateTime local =
        LocalDateTime.parse("2026-11-15T15:30:00");

ZonedDateTime zoned =
        ZonedDateTime.parse(
                "2026-11-15T15:30:00+07:00[Asia/Ho_Chi_Minh]");
~~~

Format tường minh:

~~~java
String instantText =
        DateTimeFormatter.ISO_INSTANT.format(instant);

String localText =
        DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local);

String zonedText =
        DateTimeFormatter.ISO_ZONED_DATE_TIME.format(zoned);
~~~

Một chuỗi chỉ có `2026-11-15T15:30:00` không đủ thông tin để parse thành `Instant`. Chuỗi của `Instant` cần offset/UTC hoặc phải được kết hợp với zone/offset từ một nguồn khác.

### 9.1. ISO string và dữ liệu lưu trữ

- Lưu `Instant` dạng ISO UTC là cách dễ trao đổi timestamp giữa hệ thống.
- Lưu `LocalDateTime` nếu hợp đồng dữ liệu cố ý chỉ mang ngày giờ địa phương; phải lưu zone riêng khi cần xác định thời điểm.
- Lưu `ZonedDateTime` dạng ISO có cả offset và zone ID nếu cần giữ cả thời điểm và vùng hiển thị ban đầu.

Nếu API yêu cầu định dạng riêng, dùng `DateTimeFormatter` với pattern được xác định rõ. Không nên tự cắt chuỗi hoặc cộng/trừ giờ thủ công để chuyển múi giờ.

## 10. Clock: kiểm soát nguồn thời gian và viết test ổn định

Một phương thức gọi `Instant.now()` trực tiếp phụ thuộc đồng hồ hệ thống. Test chạy ở thời điểm khác sẽ nhận giá trị khác, làm khó kiểm thử logic dựa trên thời gian.

`Clock` cho phép truyền nguồn thời gian vào:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return clock.instant();
    }
}
~~~

Trong ứng dụng thực tế:

~~~java
AuditService service =
        new AuditService(Clock.systemUTC());
~~~

Trong test, dùng clock cố định:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-15T08:00:00Z"),
        ZoneOffset.UTC);

AuditService service = new AuditService(fixed);

System.out.println(service.createdAt());
// 2026-11-15T08:00:00Z
~~~

`Clock.fixed` làm thời gian không đổi trong test. Điều này hữu ích để kiểm tra hết hạn, thời điểm tạo bản ghi, thời gian bảo hành hoặc logic tính hạn.

Nếu code cần giờ địa phương theo một zone, dùng `clock.withZone(zone)` hoặc lấy `ZonedDateTime.now(clock)`. Tránh để nhiều lớp tự gọi `LocalDateTime.now()` với zone mặc định khác nhau, vì kết quả sẽ phụ thuộc môi trường chạy.

## 11. Duration và Period: đo khoảng thời gian đúng ý nghĩa

Khi tính khoảng cách giữa các thời điểm, `Duration` biểu diễn lượng thời gian theo giây/nano. Khi tính khoảng cách theo lịch, `Period` biểu diễn năm/tháng/ngày.

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");
Instant end = start.plus(Duration.ofHours(2));

Duration elapsed = Duration.between(start, end);
~~~

Với lịch địa phương:

~~~java
LocalDate today = LocalDate.of(2026, 11, 15);
LocalDate nextMonth = today.plus(Period.ofMonths(1));
~~~

Một ngày lịch không phải lúc nào cũng tương đương 24 giờ trên timeline tại vùng có DST. Nếu cần cộng “một ngày theo lịch địa phương” cho lịch hẹn, thao tác trên `ZonedDateTime`/`LocalDate` với zone phù hợp. Nếu cần cộng chính xác 24 giờ đã trôi qua, thao tác trên `Instant` bằng `Duration.ofHours(24)`.

Ví dụ:

~~~java
ZonedDateTime before = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime sameLocalTimeTomorrow = before.plusDays(1);
ZonedDateTime after24Hours = before.plus(Duration.ofHours(24));
~~~

Ở vùng chuyển DST, hai kết quả có thể khác nhau về giờ địa phương hoặc instant. Cần xác định yêu cầu là “cùng giờ ngày mai” hay “sau đúng 24 giờ”.

## 12. Chọn kiểu dữ liệu khi thiết kế hệ thống

### 12.1. Log và audit

Nên lưu `Instant` cho thời điểm sự kiện thực sự xảy ra:

~~~java
record AuditEvent(String action, Instant occurredAt) {
}
~~~

Khi hiển thị, chuyển sang zone của người xem hoặc zone được yêu cầu trong báo cáo. Không lưu timestamp log chỉ bằng `LocalDateTime` vì sẽ mất thông tin cần để sắp xếp chính xác giữa các máy ở nhiều múi giờ.

### 12.2. Lịch hẹn tương lai

Một lịch hẹn như “09:00 ngày 10 tháng 4 tại chi nhánh Paris” mang ý nghĩa giờ địa phương của một vùng. Có thể lưu:

- `LocalDateTime`: ngày và giờ đã chọn.
- `ZoneId`: `Europe/Paris`.
- Chính sách xử lý gap/overlap nếu thời điểm rơi vào chuyển DST.

Nếu lịch hẹn đã được xác nhận thành một thời điểm cụ thể, có thể lưu thêm `Instant` tương ứng để phục vụ nhắc lịch, đồng bộ và audit. Khi quy tắc múi giờ được cập nhật, sản phẩm cần quyết định ưu tiên giữ “09:00 theo giờ địa phương” hay giữ instant đã chốt.

### 12.3. Giờ mở cửa và lịch lặp

Giờ mở cửa 08:00–17:00 từ thứ Hai đến thứ Sáu không phải là một instant duy nhất. Mô hình phù hợp thường là `LocalTime`, ngày trong tuần và `ZoneId` của địa điểm. Mỗi ngày cụ thể mới được kết hợp với zone rules để tạo ra các thời điểm thực tế.

### 12.4. Ngày sinh hoặc ngày kỷ niệm

Nếu chỉ quan tâm ngày trên lịch, dùng `LocalDate`. Không biến ngày sinh thành `Instant` lúc 00:00 UTC rồi hiển thị ở zone khác, vì người dùng có thể nhìn thấy ngày hôm trước hoặc hôm sau.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cùng một timestamp nhưng UI hiển thị giờ khác | Chuyển cùng instant sang zone khác | Đây là hành vi đúng; thống nhất zone hiển thị |
| Không biết LocalDateTime tương ứng instant nào | Thiếu zone hoặc offset | Kết hợp với `ZoneId` hoặc `ZoneOffset` |
| Lịch hẹn bị lệch khi người dùng đi du lịch | Lưu local date-time nhưng ngầm dùng zone mặc định của server | Lưu zone ID theo địa điểm của lịch hẹn |
| Giờ địa phương không tồn tại khi DST bắt đầu | Local time rơi vào gap | Từ chối, điều chỉnh hoặc yêu cầu chọn theo chính sách nghiệp vụ |
| Giờ địa phương xuất hiện hai lần khi DST kết thúc | Local time rơi vào overlap | Chọn offset sớm/muộn rõ ràng |
| Dùng offset cố định cho vùng có DST | Nhầm ZoneOffset với ZoneId | Dùng ID vùng và zone rules |
| Cộng 24 giờ làm thay đổi giờ lịch | Dùng Duration trong khi yêu cầu là ngày lịch | Phân biệt Duration với Period/plusDays |
| Test thời gian thay đổi theo ngày chạy | Gọi now trực tiếp | Inject Clock và dùng Clock.fixed trong test |
| Ngày sinh lệch ngày | Dùng Instant cho dữ liệu chỉ có ngày | Dùng LocalDate |
| Lưu log không thể sắp xếp giữa các múi giờ | Chỉ lưu LocalDateTime | Lưu Instant, chuyển zone lúc hiển thị |
| Tự cộng/trừ số giờ để đổi múi giờ | Bỏ qua zone rules và DST | Dùng atZone/withZoneSameInstant |

## 14. Ví dụ tổng hợp có thể chạy trên Java 17

Tạo file `TimeTypesDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeTypesDemo {

    private TimeTypesDemo() {
    }

    public static void main(String[] args) {
        Instant event = Instant.parse("2026-11-15T08:00:00Z");

        ZoneId hanoiZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId parisZone = ZoneId.of("Europe/Paris");

        ZonedDateTime hanoi = event.atZone(hanoiZone);
        ZonedDateTime paris = event.atZone(parisZone);

        System.out.println("Instant: " + event);
        System.out.println("Hanoi:   " + hanoi);
        System.out.println("Paris:   " + paris);
        System.out.println("Same instant: "
                + hanoi.toInstant().equals(paris.toInstant()));

        LocalDateTime appointment =
                LocalDateTime.of(2026, 11, 16, 9, 0);

        ZonedDateTime appointmentInHanoi =
                appointment.atZone(hanoiZone);

        System.out.println("Local appointment: " + appointment);
        System.out.println("Resolved appointment: "
                + appointmentInHanoi);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 TimeTypesDemo.java
java TimeTypesDemo
~~~

Kết quả có dạng:

~~~text
Instant: 2026-11-15T08:00:00Z
Hanoi:   2026-11-15T15:00+07:00[Asia/Ho_Chi_Minh]
Paris:   2026-11-15T09:00+01:00[Europe/Paris]
Same instant: true
Local appointment: 2026-11-16T09:00
Resolved appointment: 2026-11-16T09:00+07:00[Asia/Ho_Chi_Minh]
~~~

Phần giờ Paris phụ thuộc zone rules của ngày được chọn. Mục tiêu của ví dụ là cho thấy cùng một `Instant` có nhiều cách hiển thị và `LocalDateTime` cần zone để được giải quyết thành `ZonedDateTime`.

## 15. Bài tập thực hành

### Bài 1 — Cùng instant ở hai vùng

Tạo một `Instant` cố định. Chuyển sang `Asia/Ho_Chi_Minh` và `Europe/Paris`. In local date-time, offset và zone; xác nhận hai kết quả có cùng `toInstant()`.

### Bài 2 — LocalDateTime thiếu thông tin

Tạo `LocalDateTime` cho một cuộc họp lúc 09:00. Hãy giải thích vì sao chưa thể chuyển thành `Instant` nếu chưa biết zone. Thử chuyển nó theo hai zone khác nhau và so sánh kết quả.

### Bài 3 — Giữ instant hay giữ local time?

Tạo một `ZonedDateTime` ở Hà Nội. Gọi `withZoneSameInstant` và `withZoneSameLocal` để chuyển sang Paris. In kết quả và giải thích phương thức nào giữ nguyên instant.

### Bài 4 — DST gap

Dùng `Europe/Paris` với `2024-03-31T02:30`. Kiểm tra `getValidOffsets`, `getTransition` và kết quả của `atZone`. Mô tả chính sách mặc định của Java khi giờ địa phương không tồn tại.

### Bài 5 — DST overlap

Dùng `Europe/Paris` với `2024-10-27T02:30`. In hai offset hợp lệ. Tạo hai `ZonedDateTime` cho offset sớm và muộn, rồi tính chênh lệch instant.

### Bài 6 — Kiểm thử với Clock

Viết dịch vụ trả về thời điểm tạo bản ghi bằng `Clock`. Dùng `Clock.fixed` để test rằng kết quả không đổi giữa các lần gọi.

### Bài 7 — Cộng ngày lịch và cộng 24 giờ

Chọn ngày trước một thời điểm chuyển DST tại Paris. So sánh `plusDays(1)` và `plus(Duration.ofHours(24))`. Giải thích hai yêu cầu nghiệp vụ khác nhau.

## 16. Nguyên tắc cần nhớ

- **`Instant`:** dùng khi cần xác định thời điểm thực tế trên timeline, độc lập với múi giờ hiển thị.
- **`LocalDateTime`:** dùng khi cần lưu ngày giờ trên đồng hồ địa phương mà zone được quản lý riêng hoặc chưa được chọn; không đủ để xác định instant.
- **`ZonedDateTime`:** dùng khi cần ngày giờ địa phương cùng zone rules và offset áp dụng tại thời điểm đó.
- **`ZoneId`** mô tả vùng và quy tắc; **`ZoneOffset`** chỉ là độ lệch cố định so với UTC.
- Khi chuyển zone, phân biệt giữ nguyên instant với giữ nguyên local date-time.
- DST có thể tạo gap (không có offset hợp lệ) hoặc overlap (hai offset hợp lệ); chọn chính sách rõ ràng cho lịch hẹn.
- Dùng `Clock` để kiểm soát nguồn thời gian và viết test có thể tái hiện.
- Phân biệt thời lượng tuyến tính `Duration` với khoảng thời gian lịch `Period`.

Khi chọn đúng kiểu dữ liệu theo ý nghĩa nghiệp vụ, ứng dụng Java 17 có thể lưu timestamp, xử lý lịch hẹn và hiển thị thời gian xuyên múi giờ một cách rõ ràng, tránh tự cộng/trừ giờ và tránh mất thông tin khi chuyển đổi.
