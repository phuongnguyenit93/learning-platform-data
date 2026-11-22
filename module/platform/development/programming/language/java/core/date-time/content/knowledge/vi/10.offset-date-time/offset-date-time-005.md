# OffsetTime biểu diễn giờ kèm độ lệch nhưng không có ngày

`OffsetTime` trong Java là kiểu dữ liệu của gói `java.time` biểu diễn **giờ trên đồng hồ kết hợp với độ lệch cố định so với UTC (UTC offset)**, nhưng **không chứa ngày, năm, tháng hay tên múi giờ địa lý**. Ví dụ:

~~~text
09:15:30.123456789+07:00
└── giờ trong ngày ──┘└offset UTC
~~~

Chuỗi này nói rằng đồng hồ hiển thị **09 giờ 15 phút 30 giây, cộng phần lẻ 123456789 nano giây, tại offset UTC+07:00**. Nó không nói giờ ấy xảy ra **vào ngày nào**, cũng không nói đó là giờ của riêng `Asia/Ho_Chi_Minh` hay một địa phương khác.

Điểm mấu chốt: `OffsetTime` chứa *giờ + offset* nhưng **chưa tự xác định duy nhất một `Instant`** (một thời điểm tuyệt đối) vì còn thiếu ngày. Khi cần đặt giá trị lên trục thời gian, hãy bổ sung một `LocalDate`; khi cần quy tắc DST hoặc thay đổi offset theo lịch sử, hãy dùng `ZoneId` cùng các kiểu thích hợp như `ZonedDateTime`.

## 1. So sánh OffsetTime với các kiểu thời gian gần nó

| Kiểu Java | Ngày | Giờ | Offset UTC | ZoneId địa lý | Dùng khi |
| --- | :---: | :---: | :---: | :---: | --- |
| `LocalTime` | Không | Có | Không | Không | Chỉ một giờ theo đồng hồ |
| **`OffsetTime`** | **Không** | **Có** | **Có** | **Không** | Giờ trong ngày kèm offset cụ thể |
| `LocalDateTime` | Có | Có | Không | Không | Ngày và giờ địa phương |
| `OffsetDateTime` | Có | Có | Có | Không | Ngày giờ có offset, đủ xác định instant |
| `ZonedDateTime` | Có | Có | Có | Có | Ngày giờ ở vùng có quy tắc DST/lịch sử |
| `Instant` | Điểm thời gian tuyệt đối | — | Theo trục UTC | Không | Timestamp sự kiện đã xác định |

Khác biệt quan trọng giữa hai giá trị:

~~~text
09:15:30          ← LocalTime: chỉ giờ, không offset
09:15:30+07:00    ← OffsetTime: giờ + độ lệch UTC, không ngày
~~~

Trong trường hợp thứ hai, offset `+07:00` cung cấp **quan hệ giữa giờ địa phương và UTC**, nhưng chưa đủ để xác định ngày tuyệt đối của sự kiện. Chẳng hạn, các ngày 09/04/2025 và 10/04/2025 đều có thể có giờ `09:15+07:00`, tương ứng với **hai instant khác nhau** cách nhau 24 giờ.

`OffsetTime` cũng **không tương đương** với `ZonedDateTime`: offset `+07:00` không có các quy tắc lịch sử, daylight saving time (DST) hay chính sách tương lai của một quốc gia.

## 2. Cấu trúc dữ liệu: LocalTime + ZoneOffset

Một `OffsetTime` về mặt ý nghĩa gồm hai phần:

- `LocalTime`: giờ, phút, giây và nanosecond trong giây (độ phân giải tối đa 1 ns).
- `ZoneOffset`: độ lệch so với UTC, chẳng hạn `Z` (bằng `+00:00`), `+07:00` hoặc `-05:00`.

Java cung cấp getter trực tiếp:

~~~java
OffsetTime value =
        OffsetTime.parse("09:15:30.123456789+07:00");

LocalTime time = value.toLocalTime();
ZoneOffset offset = value.getOffset();

int hour = value.getHour();     // 9
int minute = value.getMinute(); // 15
int second = value.getSecond(); // 30
int nano = value.getNano();     // 123456789
int secondsEastOfUtc = offset.getTotalSeconds(); // 25200
~~~

`getNano()` là **phần lẻ nanosecond trong một giây**, không phải tổng nano giây của ngày. Với `+07:00`, `getTotalSeconds()` trả `7 × 3600 = 25200`; với offset âm, kết quả là số âm.

Các giá trị `OffsetTime` là **immutable** (bất biến) và có thể chia sẻ an toàn giữa các luồng. Các phương thức `plusHours`, `withHour`, `withOffsetSameInstant` và `withOffsetSameLocal` đều trả về đối tượng mới chứ không sửa đối tượng ban đầu.

`ZoneOffset` là **offset cố định**, không phải `ZoneId` của một vùng có quy tắc lịch sử. Java cho phép offset ở dạng giờ, phút và trong một số API còn có độ phân giải giây, nhưng giới hạn hợp lệ tối đa là ±18:00. Đừng giả định mọi offset trên thế giới đều nguyên giờ.

## 3. Tạo OffsetTime từ các thành phần

Có nhiều cách tạo cùng một giờ có offset:

~~~java
import java.time.LocalTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

ZoneOffset offset = ZoneOffset.ofHours(7);
LocalTime localTime = LocalTime.of(9, 15, 30, 123_456_789);

OffsetTime a = OffsetTime.of(localTime, offset);
OffsetTime b = OffsetTime.of(
        9, 15, 30, 123_456_789, offset);
OffsetTime c =
        OffsetTime.parse("09:15:30.123456789+07:00");

// a.equals(b) && b.equals(c) là true.
~~~

Các overload `of` kiểm tra tính hợp lệ của giờ và offset. Ví dụ, giờ `24` hoặc phút `60` sẽ bị từ chối bằng `DateTimeException`. Nếu chỉ truyền `LocalTime.of(9,15)` thì giây và nanosecond bằng `0`.

Khi dùng `OffsetTime.now()`, Java lấy thời điểm hiện tại qua đồng hồ hệ thống và múi giờ mặc định của JVM, rồi suy ra giờ cùng offset **tại thời điểm đó**. Khi cần rõ ràng, dùng `OffsetTime.now(zone)` hoặc `OffsetTime.now(clock)`. Sau khi tạo, đối tượng chỉ giữ `LocalTime` và `ZoneOffset`, **không giữ `ZoneId` đã dùng để tính**.

Ví dụ kiểm thử quyết định được kết quả:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-04-09T02:15:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

OffsetTime fixedValue = OffsetTime.now(fixedClock);
// 09:15:30+07:00
~~~

Đoạn minh họa này cần import `java.time.*`. Dùng `Clock.fixed(...)` giúp tránh những unit test thất bại ngẫu nhiên vì đồng hồ thực hoặc cấu hình timezone của máy chạy.

## 4. Parse OffsetTime từ chuỗi ISO-8601

`OffsetTime.parse(text)` dùng biểu diễn ISO với **giờ và offset**. Ví dụ:

~~~java
OffsetTime a = OffsetTime.parse("09:15+07:00");
OffsetTime b = OffsetTime.parse("09:15:30+07:00");
OffsetTime c = OffsetTime.parse("09:15:30.123456789+07:00");
OffsetTime d = OffsetTime.parse("09:15:30Z");
~~~

Trong đó:

- `09:15` là giờ và phút.
- `:30` là giây (nếu không có thì được hiểu bằng 0).
- `.123456789` là phần lẻ của giây với độ phân giải nanosecond.
- `+07:00` nghĩa là đồng hồ đi trước UTC bảy giờ.
- `Z` nghĩa là offset UTC bằng 0, tương đương `+00:00`.

Ví dụ:

~~~java
OffsetTime z = OffsetTime.parse("09:15:30Z");
OffsetTime zero = OffsetTime.parse("09:15:30+00:00");
// z.equals(zero) == true
~~~

Giá trị `2025-04-09T09:15:30+07:00` **có ngày**, nên thích hợp với `OffsetDateTime.parse(...)`, không phải `OffsetTime.parse(...)` mặc định. Ngược lại, `09:15:30` thiếu offset, nên đọc bằng `LocalTime.parse(...)` hoặc yêu cầu cung cấp thêm offset; đừng tự mặc định UTC nếu hợp đồng dữ liệu không quy định.

Đầu vào sai cú pháp, sai giờ hoặc offset ngoài miền hợp lệ có thể gây `DateTimeParseException`; ứng dụng nên trả thông báo rõ trường nào không hợp lệ, thay vì bắt mọi ngoại lệ rồi ngầm sử dụng một offset khác.

## 5. Chương trình Java 17+ đầy đủ

Lưu nội dung sau vào tệp `OffsetTimeLessonDemo.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetTimeLessonDemo {
    public static void main(String[] args) {
        OffsetTime original = OffsetTime.parse(
                "09:15:30.123456789+07:00");

        OffsetTime utc = original.withOffsetSameInstant(
                ZoneOffset.UTC);
        OffsetTime unchangedLocal = original.withOffsetSameLocal(
                ZoneOffset.UTC);
        OffsetDateTime atDate = original.atDate(
                LocalDate.of(2025, 4, 9));

        System.out.println("original=" + original);
        System.out.println("time=" + original.toLocalTime());
        System.out.println("offset=" + original.getOffset());
        System.out.println("offsetSeconds="
                + original.getOffset().getTotalSeconds());
        System.out.println("hour=" + original.getHour()
                + ",minute=" + original.getMinute()
                + ",second=" + original.getSecond()
                + ",nano=" + original.getNano());

        System.out.println("utcSameInstant=" + utc);
        System.out.println("utcSameLocal=" + unchangedLocal);
        System.out.println("dateAttached=" + atDate);
        System.out.println("instant=" + atDate.toInstant());

        System.out.println("iso="
                + DateTimeFormatter.ISO_OFFSET_TIME
                        .format(original));
        System.out.println("shortFormat=" + original.format(
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSSXXX", Locale.ROOT)));

        System.out.println("sameInstantOfDay="
                + original.isEqual(utc));
        System.out.println("equalObjects="
                + original.equals(utc));
        System.out.println("compareTo="
                + original.compareTo(utc));

        System.out.println("crossMidnight="
                + OffsetTime.parse("00:30+02:00")
                        .withOffsetSameInstant(ZoneOffset.UTC));
        System.out.println("plusHours="
                + OffsetTime.parse("23:30+07:00").plusHours(2));

        System.out.println("parsedZ="
                + OffsetTime.parse("09:15:30Z"));
        System.out.println("parsedZeroOffset="
                + OffsetTime.parse("09:15:30+00:00"));

        Clock fixedClock = Clock.fixed(
                Instant.parse("2025-04-09T02:15:30Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("fixedNow="
                + OffsetTime.now(fixedClock));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OffsetTimeLessonDemo.java
java OffsetTimeLessonDemo
~~~

Kết quả đã kiểm tra với Java:

~~~text
original=09:15:30.123456789+07:00
time=09:15:30.123456789
offset=+07:00
offsetSeconds=25200
hour=9,minute=15,second=30,nano=123456789
utcSameInstant=02:15:30.123456789Z
utcSameLocal=09:15:30.123456789Z
dateAttached=2025-04-09T09:15:30.123456789+07:00
instant=2025-04-09T02:15:30.123456789Z
iso=09:15:30.123456789+07:00
shortFormat=09:15:30.123+07:00
sameInstantOfDay=true
equalObjects=false
compareTo=1
crossMidnight=22:30Z
plusHours=01:30+07:00
parsedZ=09:15:30Z
parsedZeroOffset=09:15:30Z
fixedNow=09:15:30+07:00
~~~

**Giải thích các dòng quan trọng:**

- `utcSameInstant` đổi offset sang UTC và **dịch giờ tương ứng**: 09:15 tại UTC+7 thành 02:15 UTC.
- `utcSameLocal` chỉ thay offset, **giữ giờ 09:15**. Hai giá trị này sẽ biểu diễn các instant khác nhau khi gắn cùng một ngày.
- `dateAttached` mới có **ngày + giờ + offset**, vì vậy có thể gọi `toInstant()`.
- `sameInstantOfDay=true` cùng `equalObjects=false` minh họa sự khác nhau giữa so sánh giờ đã chuẩn hóa theo offset và so sánh đầy đủ hai thành phần.
- `compareTo=1` là kết quả hợp lệ: khi so sánh theo trật tự tự nhiên, `OffsetTime` so sánh theo thời điểm quy chiếu đã chuẩn hóa và dùng giờ địa phương để phân định nếu phần quy chiếu bằng nhau. Không nên thay `isEqual` bằng `compareTo(...) == 0` khi chỉ cần hỏi liệu hai giờ có tương đương về mặt offset hay không.

## 6. Hai cách đổi offset: SameInstant và SameLocal

Đây là khác biệt quan trọng nhất khi dùng `OffsetTime`.

### withOffsetSameInstant(newOffset)

~~~java
OffsetTime original = OffsetTime.parse("09:15+07:00");
OffsetTime converted =
        original.withOffsetSameInstant(ZoneOffset.UTC);
// 02:15Z
~~~

Ý tưởng là giữ **cùng vị trí theo giờ UTC trong một ngày quy chiếu ngầm định**, do đó phải thay đổi giờ địa phương theo chênh lệch offset. Công thức trực quan:

~~~text
giờ UTC quy chiếu = giờ địa phương − offset
09:15 − 07:00 = 02:15
~~~

Tên API dùng chữ `SameInstant`, nhưng vì `OffsetTime` **không có ngày**, bạn vẫn không thể lấy một `Instant` duy nhất từ đối tượng kết quả. Nói chính xác, phép đổi bảo toàn sự tương ứng theo offset của phần thời gian, có thể xảy ra **quay vòng qua nửa đêm**.

Ví dụ:

~~~java
OffsetTime time = OffsetTime.parse("00:30+02:00");
OffsetTime utc = time.withOffsetSameInstant(ZoneOffset.UTC);
// 22:30Z
~~~

`00:30+02:00` tương ứng với `22:30Z` của **ngày UTC trước đó**, nếu có ngày địa phương thật sự. Tuy nhiên `OffsetTime` chỉ giữ `22:30Z` mà **không có chỗ ghi ngày trước đó**. Vì vậy, nếu gắn cùng `LocalDate` vào cả hai giá trị sau chuyển đổi, kết quả `Instant` sẽ **khác nhau đúng một ngày**; thao tác này không phải cách di chuyển một sự kiện có ngày giữa hai múi giờ.

Khi đã có ngày và cần đổi offset bảo toàn instant thật, hãy dùng `OffsetDateTime.withOffsetSameInstant(...)` hoặc `ZonedDateTime.withZoneSameInstant(...)` sau khi kết hợp đầy đủ ngày–giờ.

### withOffsetSameLocal(newOffset)

~~~java
OffsetTime original = OffsetTime.parse("09:15+07:00");
OffsetTime changed =
        original.withOffsetSameLocal(ZoneOffset.UTC);
// 09:15Z
~~~

Phương thức này giữ nguyên **các chữ số giờ địa phương**, chỉ thay offset. Khi gắn cùng một ngày, `09:15+07:00` và `09:15Z` cách nhau **7 giờ về thời điểm tuyệt đối**.

So sánh:

| Phương thức | Từ `09:15+07:00` sang UTC | Điều được giữ |
| --- | --- | --- |
| `withOffsetSameInstant(UTC)` | `02:15Z` | Quan hệ thời gian được quy chiếu về UTC |
| `withOffsetSameLocal(UTC)` | `09:15Z` | Đồng hồ địa phương đọc `09:15` |

Không dùng `withOffsetSameLocal` cho tác vụ “chuyển giờ giữa UTC và Việt Nam” nếu muốn giữ đúng thời điểm; phương thức này **đổi ý nghĩa offset** của cùng giờ trên đồng hồ.

## 7. Muốn có Instant, cần ghép thêm ngày

Một `OffsetTime` **không có `toInstant()` trực tiếp** vì thiếu ngày. Để chuyển sang thời điểm tuyệt đối, phải bổ sung `LocalDate`:

~~~java
OffsetTime clockWithOffset =
        OffsetTime.parse("09:15:30+07:00");
LocalDate calendarDate = LocalDate.of(2025, 4, 9);

OffsetDateTime dated = clockWithOffset.atDate(calendarDate);
Instant instant = dated.toInstant();
// 2025-04-09T02:15:30Z
~~~

`OffsetTime.atDate(LocalDate)` trả `OffsetDateTime`: cùng giờ và offset nhưng đã có ngày. Lúc này công thức chuyển sang UTC đủ dữ kiện và không mơ hồ.

Nếu giá trị là `09:15+07:00` và bạn gắn:

~~~text
2025-04-09 → 2025-04-09T02:15:00Z
2025-04-10 → 2025-04-10T02:15:00Z
~~~

hai instant cách nhau một ngày. Đây là bằng chứng cụ thể rằng **giờ có offset nhưng thiếu ngày không phải timestamp sự kiện**.

Với một `Instant` có sẵn, bạn có thể chuyển sang `OffsetTime` để chỉ giữ giờ và offset:

~~~java
OffsetTime timeInVietnam =
        Instant.parse("2025-04-09T02:15:30Z")
                .atOffset(ZoneOffset.ofHours(7))
                .toOffsetTime();
// 09:15:30+07:00
~~~

**Đổi theo hướng này làm mất ngày**. Không thể khôi phục `Instant` gốc từ `timeInVietnam` nếu không lưu ngày đi kèm.

Nếu một cuộc họp bắt đầu vào ngày xác định trong một vùng địa lý, tốt hơn nên nhận `LocalDate`, `LocalTime` và `ZoneId` rồi tạo `ZonedDateTime` theo quy tắc DST thích hợp. `OffsetTime` không cung cấp đủ mô hình cho lịch họp theo giờ dân sự thay đổi theo mùa.

## 8. So sánh hai OffsetTime: equals, isEqual, isBefore và compareTo

Khi cùng là `OffsetTime`, phải xác định bạn muốn so sánh **chữ số giờ và offset** hay **giờ được chuẩn hóa theo UTC trong một ngày quy chiếu**.

~~~java
OffsetTime vietnam = OffsetTime.parse("09:15+07:00");
OffsetTime utc = OffsetTime.parse("02:15Z");

boolean sameValue = vietnam.equals(utc); // false
boolean sameReferenceTime = vietnam.isEqual(utc); // true
~~~

- `equals` kiểm tra đầy đủ `LocalTime` và `ZoneOffset`. Hai giá trị chỉ bằng nhau khi cả hai thành phần bằng nhau.
- `isEqual` kiểm tra sự tương đương theo offset khi quy chiếu giờ (thường mô tả là **cùng instant trên ngày tham chiếu ngầm định**).
- `isBefore` và `isAfter` so sánh trật tự theo giờ đã chuẩn hóa tương tự; chúng **không có ngày thực tế** để quyết định sự kiện nào xảy ra trước qua nhiều ngày.
- `compareTo`/natural ordering dùng quy tắc riêng: so sánh phần thời gian đã quy chiếu, nếu bằng thì dùng giờ địa phương phân định để bảo đảm thứ tự tự nhiên phù hợp với `equals`. Vì vậy `isEqual` có thể `true` khi `compareTo` khác `0`.

Ví dụ ở chương trình hoàn chỉnh, hai đối tượng `09:15:30.123456789+07:00` và `02:15:30.123456789Z` có `isEqual=true`, `equals=false`, `compareTo=1`.

**Lưu ý về nửa đêm:** Các phép so sánh trên `OffsetTime` không thể biết “22:30 UTC thuộc ngày hôm trước” nếu một giờ tại offset dương đã băng qua ranh giới ngày. Để so sánh **thứ tự hai sự kiện thực sự**, hãy gắn đúng ngày cho từng sự kiện rồi so sánh `Instant` hoặc `OffsetDateTime`. Đừng dùng `OffsetTime.isBefore` để xếp thứ tự các bản ghi nhiều ngày.

## 9. Định dạng OffsetTime với DateTimeFormatter

`OffsetTime.toString()` trả chuỗi ISO mang offset; `DateTimeFormatter.ISO_OFFSET_TIME` là formatter chuẩn cho kiểu này:

~~~java
OffsetTime time =
        OffsetTime.parse("09:15:30.123456789+07:00");

String iso = time.toString();
String formatted = DateTimeFormatter.ISO_OFFSET_TIME.format(time);
// Cả hai: "09:15:30.123456789+07:00"
~~~

Nếu hợp đồng API yêu cầu mili giây (ba chữ số phần lẻ), dùng formatter rõ ràng:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSXXX");
String text = time.format(formatter);
// 09:15:30.123+07:00
~~~

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `HH` | Giờ 00–23 | `09` |
| `mm` | Phút | `15` |
| `ss` | Giây | `30` |
| `SSS` | Ba chữ số phần lẻ (mili giây) | `123` |
| `SSSSSSSSS` | Chín chữ số phần lẻ (nano giây) | `123456789` |
| `X` | Offset ISO dạng ngắn | `+07` |
| `XXX` | Offset ISO với dấu hai chấm | `+07:00` |
| `Z` trong pattern | Offset định dạng RFC 822 tùy độ dài | `+0700` |
| `'Z'` (có nháy đơn) | Chữ `Z` literal, **không tính offset** | Có thể gây hiểu sai dữ liệu |

Nhầm `mm` (phút) với `MM` (tháng) hoặc `XXX` (offset ISO) với ký tự `'Z'` cố định dễ khiến dữ liệu sai. Nếu cần định dạng UTC thực sự, hãy đổi sang offset UTC phù hợp trước khi format; **không được gắn hậu tố `Z` bằng chuỗi literal khi dữ liệu không ở offset 0**.

Mẫu `SSS` lấy ba chữ số phần lẻ, **không tự làm tròn** giá trị nanosecond. Khi parse lại chuỗi đã cắt còn mili giây, bạn không thể khôi phục nanosecond nhỏ hơn 1 ms. Nếu yêu cầu truyền đủ độ chính xác, dùng formatter ISO hoặc mẫu phần lẻ đến 9 chữ số.

Một `OffsetTime` cũng có thể parse theo formatter tùy biến, nhưng định dạng phải chứa đủ trường giờ và offset:

~~~java
DateTimeFormatter fixed = DateTimeFormatter.ofPattern(
        "HH:mm:ss.SSSXXX");
OffsetTime parsed =
        OffsetTime.parse("09:15:30.123+07:00", fixed);
~~~

## 10. OffsetTime không lưu múi giờ và không tự xử lý DST

Cùng offset `+02:00` có thể được nhiều vùng sử dụng trong những giai đoạn khác nhau. Những vùng này có thể có **lịch sử hoặc quy tắc DST khác nhau**. Một `OffsetTime` như `09:00+02:00` chỉ lưu con số offset; nó không cho phép hỏi “đúng 09:00 tháng bảy năm sau ở London thì offset sẽ bằng bao nhiêu?”.

Ví dụ, nếu lịch làm việc của chi nhánh ở New York ghi:

~~~text
09:00 theo giờ America/New_York mỗi ngày làm việc
~~~

thì giờ bắt đầu có thể tương ứng `09:00-05:00` mùa đông và `09:00-04:00` mùa hè, dựa trên quy tắc của thời kỳ đó. Chỉ lưu `OffsetTime.parse("09:00-05:00")` sẽ vô tình cố định offset `-05:00`, làm thời điểm UTC của cuộc hẹn lặp **lệch một giờ** trong giai đoạn có DST.

Nếu cần lịch lặp theo đồng hồ địa phương, hãy lưu **LocalTime + ZoneId** và quy tắc ngày lặp. Khi xác định mỗi lần thực thi, chọn ngày tương ứng, giải quyết gap/overlap rồi chuyển sang `ZonedDateTime` và `Instant`.

Ví dụ ý tưởng:

~~~java
LocalDate meetingDate = LocalDate.of(2025, 7, 15);
LocalTime meetingTime = LocalTime.of(9, 0);
ZoneId meetingZone = ZoneId.of("America/New_York");

ZonedDateTime meeting = ZonedDateTime.of(
        meetingDate, meetingTime, meetingZone);
// Quy tắc múi giờ quyết định offset thích hợp vào ngày này.
~~~

Đây là mã minh họa trong một phương thức với các import `java.time.*`. Với các ngày chuyển DST, một giờ địa phương có thể **không tồn tại** (gap) hoặc **trùng hai lần** (overlap). Nếu chính sách nghiệp vụ cần xử lý đặc biệt, hãy xem `ZoneRules.getValidOffsets(LocalDateTime)` trước khi quyết định.

Ngay cả khi một `OffsetTime` được tạo bằng `OffsetTime.now(ZoneId)`, ZoneId chỉ tham gia **để chọn offset tại thời điểm hiện tại**; ZoneId ấy không còn được lưu trong giá trị trả về.

## 11. Tính toán giờ, tràn ngày và giới hạn không có ngày

Các phép cộng trừ trên `OffsetTime` giữ nguyên offset và tạo giờ mới:

~~~java
OffsetTime original = OffsetTime.parse("23:30+07:00");
OffsetTime later = original.plusHours(2);
// 01:30+07:00
~~~

Kết quả không cho biết đó là 01:30 của **ngày hôm sau**. Điều này tương tự `LocalTime` vì `OffsetTime` không có thành phần ngày. Nếu bạn muốn tính “hai giờ sau sự kiện lúc 23:30 ngày 09/04”, hãy gắn ngày trước:

~~~java
OffsetDateTime original = OffsetTime
        .parse("23:30+07:00")
        .atDate(LocalDate.of(2025, 4, 9));

OffsetDateTime later = original.plusHours(2);
// 2025-04-10T01:30+07:00
~~~

Trong những bài toán cần giữ thời điểm tuyệt đối, dùng `Instant` để tính duration hoặc `ZonedDateTime` theo đúng quy tắc của zone. Phân biệt rõ **cộng 24 giờ thực** với **sang ngày lịch tiếp theo**, đặc biệt tại vùng có DST.

`OffsetTime` không có thông tin về năm nhuận, ngày trong tháng, ngày trong tuần, số giờ của một ngày lịch địa phương tại zone có DST hoặc lần chuyển giờ tương lai. Không nên cố suy ra các thông tin này từ offset hiện có.

## 12. Trường hợp sử dụng phù hợp và không phù hợp

### Có thể phù hợp

- **Trường API chỉ mang giờ và offset đã được khai báo**: ví dụ `"businessClock": "09:15:00+07:00"`, khi hợp đồng khẳng định dữ liệu cố ý **không có ngày**.
- **Dữ liệu giờ đồng hồ theo offset cố định**: một cấu hình xử lý ở `+07:00` không phụ thuộc quy tắc mùa vụ của vùng địa lý.
- **Trao đổi thời gian giữa các hệ thống** cần giữ rõ giá trị đồng hồ và độ lệch UTC mà không cần lưu ngày.
- **Kiểm thử hoặc ví dụ giáo dục** phân biệt `LocalTime`, `ZoneOffset` và `OffsetTime`.

### Thường không phù hợp

- **Timestamp của sự kiện đã xảy ra**: nên lưu `Instant` hoặc `OffsetDateTime` vì phải có ngày để xác định thời điểm.
- **Lịch cuộc họp theo giờ của một thành phố**: cần `LocalDateTime + ZoneId` hoặc `ZonedDateTime`.
- **Ngày giờ phát sinh giao dịch trong database**: chỉ `OffsetTime` làm mất ngày nên không đủ cho audit.
- **Lịch hằng tuần ở vùng có DST**: cần thông tin ngày và mã vùng, không chỉ offset hiện thời.

Trong API JSON, ví dụ hai trường có ngữ nghĩa rất khác:

~~~json
{
  "openingTimeAtFixedOffset": "09:00:00+07:00",
  "createdAt": "2025-04-09T02:00:00Z"
}
~~~

Trường thứ nhất là **giờ kèm offset, không có ngày**; trường thứ hai là **một thời điểm tuyệt đối**. Không nên deserialize hai trường về cùng một kiểu hoặc ghi chuỗi thời gian thiếu ngày vào cột timestamp của sự kiện.

Nếu dùng SQL, một số cơ sở dữ liệu có kiểu dữ liệu `TIME WITH TIME ZONE` gần với khái niệm giờ + offset, nhưng **hành vi của driver và hệ quản trị có thể khác nhau**. Trước khi ánh xạ JDBC `OffsetTime`, cần kiểm tra khả năng hỗ trợ JDBC 4.2, chính sách xử lý offset và kiểu cột cụ thể; không giả định tên kiểu dữ liệu bảo đảm mọi hệ thống xử lý giống nhau.

## 13. Các lỗi phổ biến và cách tránh

| Nhầm lẫn | Tác hại | Cách đúng |
| --- | --- | --- |
| Cho rằng `OffsetTime` đã xác định một instant duy nhất | Còn thiếu ngày nên không có timestamp cụ thể | Bổ sung `LocalDate` bằng `atDate(...)` |
| Coi `+07:00` là tên múi giờ `Asia/Ho_Chi_Minh` | Không có lịch sử hoặc quy tắc tương lai của vùng | Lưu `ZoneId` riêng nếu cần |
| Dùng `withOffsetSameLocal` để “đổi UTC” | Đổi instant sau khi gắn ngày | Phân biệt rõ SameLocal và SameInstant |
| Coi `withOffsetSameInstant` vẫn giữ cả ngày qua nửa đêm | `OffsetTime` không lưu ngày, giờ quay vòng | Gắn ngày trước và dùng `OffsetDateTime` |
| So sánh `equals` như `isEqual` | Các giá trị có giờ + offset khác nhau có thể quy chiếu tương đương | Chọn phép so sánh đúng ý nghĩa |
| Dùng `compareTo==0` để thay `isEqual` | Natural ordering phân định thêm giờ địa phương | Dùng `isEqual` nếu chỉ xét giờ chuẩn hóa |
| Trừ `OffsetTime` để tính thời lượng qua ngày | Không có thông tin ngày bắt đầu/kết thúc | Dùng `OffsetDateTime` hoặc `Instant` |
| Cho rằng `OffsetTime.now(zone)` ghi nhớ `ZoneId` | Mất thông tin vùng sau lúc tạo | Lưu `ZoneId` riêng khi cần |
| Lưu lịch hằng ngày có DST bằng offset cố định | Có thể lệch giờ trong mùa đổi DST | Dùng `LocalTime + ZoneId` theo từng ngày |
| Gắn literal `'Z'` vào giờ offset khác 0 | Khai báo sai quan hệ với UTC | Dùng formatter offset thực |
| Mặc định `09:15` không có giây | Trong `LocalTime`, giây mặc định bằng 0 | Đọc `getSecond()`, chọn format rõ |
| Định dạng `SSS` rồi tưởng vẫn còn đủ nano giây khi parse lại | Mất độ chính xác dưới mili giây | Lưu/serialize đầy đủ phần lẻ nếu cần |

## 14. Bài tập tự kiểm tra

**Câu 1.** `OffsetTime.parse("09:00+07:00")` có xác định một sự kiện đã xảy ra vào instant nào không?

**Đáp án:** Không. Nó thiếu ngày. Khi gắn `2025-04-09` sẽ tương ứng `2025-04-09T02:00:00Z`; khi gắn `2025-04-10` sẽ là một instant khác.

**Câu 2.** Với `09:15+07:00`, hai phép `withOffsetSameInstant(UTC)` và `withOffsetSameLocal(UTC)` khác nhau thế nào?

**Đáp án:** Cách thứ nhất tạo `02:15Z` (dịch giờ theo offset), cách thứ hai tạo `09:15Z` (giữ nguyên giờ địa phương, đổi offset).

**Câu 3.** `OffsetTime.parse("00:30+02:00").withOffsetSameInstant(UTC)` cho kết quả gì và vì sao cần cẩn thận?

**Đáp án:** `22:30Z`. Nếu có ngày thật, giờ UTC đó thuộc **ngày trước**; đối tượng `OffsetTime` không lưu thông tin ấy, nên không thể chuyển ngày chính xác nếu chỉ giữ kết quả.

**Câu 4.** `OffsetTime.parse("09:15+07:00").isEqual(OffsetTime.parse("02:15Z"))` có đúng không?

**Đáp án:** Đúng, vì hai giá trị tương ứng cùng thời gian UTC đã chuẩn hóa trong ngày tham chiếu. Nhưng `equals` là `false` vì thành phần `LocalTime` và `ZoneOffset` khác nhau.

**Câu 5.** Muốn chuyển `OffsetTime` của 09/04/2025 thành một `Instant` thì gọi API nào?

**Đáp án:** `offsetTime.atDate(LocalDate.of(2025,4,9)).toInstant()`. Việc gắn ngày tạo `OffsetDateTime` rồi mới đổi được sang instant.

**Câu 6.** Khi tạo lịch `09:00` tại New York hằng ngày, chỉ lưu `OffsetTime.parse("09:00-05:00")` có đủ không?

**Đáp án:** Không. New York có quy tắc DST và có thể dùng `-04:00` vào mùa hè. Cần giữ `LocalTime` cùng `ZoneId.of("America/New_York")` và xác định offset theo từng ngày.

**Câu 7.** Vì sao `OffsetTime.parse("09:15:30.123456789+07:00").format(DateTimeFormatter.ofPattern("HH:mm:ss.SSSXXX"))` không giữ đủ nanosecond trong chuỗi?

**Đáp án:** Mẫu `SSS` chỉ in ba chữ số phần lẻ giây, tương ứng mili giây. Đối tượng gốc vẫn giữ đủ nano giây, nhưng parse lại chuỗi rút gọn sẽ không thể tái tạo phần độ chính xác đã bỏ.

**Ghi nhớ:** `OffsetTime = LocalTime + ZoneOffset`, tức là **giờ kèm độ lệch nhưng không có ngày và không có ZoneId**. Dùng nó khi dữ liệu cần đúng hai thành phần này. Nếu cần một sự kiện có thời điểm tuyệt đối, bổ sung `LocalDate` để có `OffsetDateTime`; nếu cần lịch theo giờ của thành phố và quy tắc DST, sử dụng `ZoneId` thích hợp.