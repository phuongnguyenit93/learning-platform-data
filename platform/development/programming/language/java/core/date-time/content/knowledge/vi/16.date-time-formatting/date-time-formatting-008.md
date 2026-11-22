# Định dạng offset, tên múi giờ và ZoneId trong Java

Trong Java `java.time`, formatter có thể hiển thị **UTC offset**, **tên vùng giờ** hoặc **mã `ZoneId`**. Ba thông tin này liên quan nhưng không thể thay thế cho nhau. Ví dụ, một giá trị `ZonedDateTime` ở New York vào mùa hè có thể được trình bày như sau:

~~~text
2025-07-15T09:05:06-04:00[America/New_York]
                      └offset┘ └── ZoneId ──┘
~~~

`-04:00` là offset áp dụng tại thời điểm đó; `America/New_York` là ID vùng có quy tắc lịch sử và DST. Tên như `EDT` hoặc `Eastern Daylight Time` là văn bản hiển thị, phụ thuộc locale và dữ liệu của runtime.

## 1. Phân biệt offset, tên vùng và ZoneId

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `ZoneOffset` | `-04:00`, `+07:00`, `Z` | Độ lệch cố định so với UTC |
| `ZoneId` | `America/New_York`, `Asia/Ho_Chi_Minh` | ID vùng để tra quy tắc offset theo thời gian |
| Tên vùng hiển thị | `EDT`, `Eastern Daylight Time` | Tên ngắn/dài cho con người; phụ thuộc locale và thời điểm |
| `Instant` | `2025-07-15T13:05:06Z` | Điểm thời gian tuyệt đối, độc lập cách trình bày |

Offset `-05:00` không đồng nghĩa với “New York”: nhiều vùng có thể dùng offset đó ở một giai đoạn, còn một vùng có thể đổi offset theo mùa hoặc luật địa phương. Với lịch tương lai, dùng `ZoneId` phù hợp thay vì chỉ lưu offset hiện tại.

`OffsetDateTime` có offset nhưng không giữ ID vùng địa lý; `ZonedDateTime` có cả offset áp dụng và `ZoneId`. `Instant` chỉ biểu diễn một điểm thời gian; muốn hiển thị theo vùng, cần chuyển sang zone hoặc offset mong muốn trước khi định dạng.

## 2. Ký hiệu formatter dành cho offset

Với offset New York là `-04:00`, các pattern phổ biến có kết quả:

| Pattern | Ví dụ | Cách hiểu |
| --- | --- | --- |
| `X` | `-04` | Offset ISO ngắn; zero offset có thể in `Z` |
| `XX` | `-0400` | Offset không có dấu hai chấm |
| `XXX` | `-04:00` | Offset ISO có dấu hai chấm |
| `x` | `-04` | Dạng số; zero offset được in bằng số |
| `xx` | `-0400` | Offset không dấu hai chấm |
| `xxx` | `-04:00` | Offset có dấu hai chấm |
| `Z`, `ZZ`, `ZZZ` | `-0400` | Offset kiểu RFC 822 |
| `ZZZZ` | `GMT-04:00` | Văn bản offset đầy đủ theo locale |
| `ZZZZZ` | `-04:00` | Offset ISO có dấu hai chấm; zero offset có thể in `Z` |
| `O` | `GMT-4` | Văn bản offset ngắn theo locale |
| `OOOO` | `GMT-04:00` | Văn bản offset đầy đủ theo locale |

`X` và `x` khác nhau ở cách biểu diễn offset bằng zero. `X` có thể xuất `Z`; `x` xuất dạng số như `+00`, `+0000` hoặc `+00:00` tùy số ký tự. `XXX` thường phù hợp khi API yêu cầu dạng `+07:00`. Số lượng ký tự hợp lệ phải tuân theo quy tắc `DateTimeFormatter`.

**Pattern chỉ định dạng, không tự chuyển đổi giờ.** Nếu giờ hiện tại là 09:05 tại offset `-04:00`, pattern `XXX` in `-04:00`; giờ vẫn là 09:05. Muốn hiển thị cùng instant theo UTC, hãy chuyển đối tượng sang UTC trước rồi mới format.

## 3. Ký hiệu dành cho tên vùng và ZoneId

| Pattern | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `z` | `EDT` | Tên vùng ngắn, thường phụ thuộc locale và thời điểm |
| `zzzz` | `Eastern Daylight Time` | Tên vùng đầy đủ theo locale |
| `VV` | `America/New_York` | ID vùng giờ |
| `O` | `GMT-4` | Offset dạng văn bản ngắn |
| `OOOO` | `GMT-04:00` | Offset dạng văn bản đầy đủ |
| `XXX` | `-04:00` | Offset ISO |

`VV` phải được viết bằng đúng hai chữ V trong pattern thông thường. `z` phù hợp với giao diện người dùng, nhưng tên như `EDT` và `Eastern Daylight Time` có thể khác theo locale, runtime và thời điểm. Cùng một `America/New_York` có thể hiển thị `EST` mùa đông và `EDT` mùa hè; ID vùng không đổi.

`ZoneId` cũng có thể là `UTC`, `GMT` hoặc ID offset cố định. Nếu cần một vùng địa lý với quy tắc lịch sử, hãy quy định rõ ID như `Asia/Ho_Chi_Minh` thay vì nhận bất kỳ offset cố định nào.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu thành tệp `OffsetZoneFormatDemo.java`:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetZoneFormatDemo {
    public static void main(String[] args) {
        ZonedDateTime newYork = ZonedDateTime.of(
                2025, 7, 15, 9, 5, 6, 0,
                ZoneId.of("America/New_York"));
        Locale us = Locale.US;

        String[] patterns = {
                "XXX", "XX", "X", "xxx", "xx", "x",
                "Z", "ZZZ", "ZZZZ", "ZZZZZ",
                "O", "OOOO", "z", "zzzz", "VV",
                "uuuu-MM-dd HH:mm:ss XXX VV z"
        };

        for (String pattern : patterns) {
            DateTimeFormatter formatter =
                    DateTimeFormatter.ofPattern(pattern, us);
            System.out.println(pattern + "=" + formatter.format(newYork));
        }

        OffsetDateTime local = OffsetDateTime.parse(
                "2025-04-09T10:00:00+07:00");
        System.out.println("instant="
                + DateTimeFormatter.ISO_INSTANT.format(local.toInstant()));
        System.out.println("offsetIso="
                + DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(local));
        System.out.println("zonedIso="
                + DateTimeFormatter.ISO_ZONED_DATE_TIME.format(newYork));
        System.out.println("utcWithZone="
                + newYork.withZoneSameInstant(ZoneOffset.UTC));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac OffsetZoneFormatDemo.java
java OffsetZoneFormatDemo
~~~

Đầu ra đã được kiểm tra trên JDK cục bộ:

~~~text
XXX=-04:00
XX=-0400
X=-04
xxx=-04:00
xx=-0400
x=-04
Z=-0400
ZZZ=-0400
ZZZZ=GMT-04:00
ZZZZZ=-04:00
O=GMT-4
OOOO=GMT-04:00
z=EDT
zzzz=Eastern Daylight Time
VV=America/New_York
uuuu-MM-dd HH:mm:ss XXX VV z=2025-07-15 09:05:06 -04:00 America/New_York EDT
instant=2025-04-09T03:00:00Z
offsetIso=2025-04-09T10:00:00+07:00
zonedIso=2025-07-15T09:05:06-04:00[America/New_York]
utcWithZone=2025-07-15T13:05:06Z[UTC]
~~~

Tên vùng trong stdout phụ thuộc locale và dữ liệu timezone runtime. Ngày giờ và ID vùng trong ví dụ được tạo tường minh để kết quả có thể kiểm tra lại.

## 5. Formatter chuẩn hay pattern tùy chỉnh?

Khi chuỗi trao đổi có schema cố định, ưu tiên formatter chuẩn:

| Formatter | Dùng cho | Ví dụ |
| --- | --- | --- |
| `DateTimeFormatter.ISO_INSTANT` | `Instant` | `2025-04-09T03:00:00Z` |
| `DateTimeFormatter.ISO_OFFSET_DATE_TIME` | Ngày giờ có offset | `2025-04-09T10:00:00+07:00` |
| `DateTimeFormatter.ISO_ZONED_DATE_TIME` | Ngày giờ có zone | `2025-07-15T09:05:06-04:00[America/New_York]` |
| `DateTimeFormatter.ISO_OFFSET_TIME` | Giờ + offset, không ngày | `09:15:30+07:00` |
| `DateTimeFormatter.ISO_LOCAL_DATE_TIME` | Ngày giờ không zone/offset | `2025-04-09T10:00:00` |

Muốn tạo chuỗi UTC từ đầu vào có offset:

~~~java
OffsetDateTime input =
        OffsetDateTime.parse("2025-04-09T10:00:00+07:00");
String utc = DateTimeFormatter.ISO_INSTANT.format(input.toInstant());
// 2025-04-09T03:00:00Z
~~~

Muốn giữ offset đầu vào, dùng `ISO_OFFSET_DATE_TIME`. Muốn giữ ID vùng, đối tượng phải có `ZoneId`; không thể khôi phục `America/New_York` chỉ từ offset `-04:00`.

## 6. Không dùng literal Z để giả vờ đã đổi sang UTC

Một lỗi phổ biến là đặt chữ Z cố định trong pattern:

~~~java
LocalDateTime local = LocalDateTime.parse("2025-04-09T10:00:00");
String wrong = local.format(
        DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss'Z'"));
// 2025-04-09T10:00:00Z, nhưng chưa chuyển sang UTC.
~~~

Chữ trong dấu nháy đơn là literal: nó chỉ được in ra, không thêm offset và không chuyển đổi thời điểm. Chuỗi này có thể khiến hệ thống nhận diễn giải sai giờ địa phương thành UTC.

Nếu nghiệp vụ xác định giờ đó là giờ Việt Nam, hãy áp zone rồi chuyển thành instant:

~~~java
LocalDateTime local =
        LocalDateTime.parse("2025-04-09T10:00:00");
Instant instant = local.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
String utc = DateTimeFormatter.ISO_INSTANT.format(instant);
// 2025-04-09T03:00:00Z
~~~

Hai bước này lần lượt diễn giải local date-time theo zone đã biết và định dạng instant theo UTC. Nếu không biết dữ liệu gốc thuộc vùng nào, không thể tự đoán rằng nó là giờ Việt Nam hay UTC.

## 7. Parse và giữ đúng thông tin

~~~java
OffsetDateTime offsetValue = OffsetDateTime.parse(
        "2025-04-09T10:00:00+07:00");

ZonedDateTime zonedValue = ZonedDateTime.parse(
        "2025-07-15T09:05:06-04:00[America/New_York]");

Instant instant = offsetValue.toInstant();
~~~

Chuỗi thứ nhất chứa offset nhưng không có ID vùng địa lý. Chuỗi thứ hai có offset áp dụng và ID vùng. Nếu parse thành `Instant`, kết quả giữ thời điểm tuyệt đối nhưng không giữ offset hoặc ID vùng ban đầu. Hãy chọn kiểu dữ liệu theo thông tin cần bảo toàn.

Pattern `XXX` cung cấp offset; `VV` yêu cầu zone ID; `z` dùng tên hiển thị và có thể không duy nhất. Với API máy-máy, ID `America/New_York` thường rõ ràng hơn tên viết tắt `EDT`.

## 8. Locale, DST và môi trường triển khai

Tên vùng như `EDT` hoặc `Eastern Daylight Time` phụ thuộc locale và dữ liệu runtime. Nếu gọi `DateTimeFormatter.ofPattern(pattern)` mà không truyền locale, formatter dùng locale mặc định của JVM, nên kết quả có thể khác giữa máy phát triển và máy chủ.

~~~java
DateTimeFormatter stable = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm:ss XXX VV z",
        Locale.US);
~~~

Cố định locale giúp kiểm soát ngôn ngữ của tên hiển thị, nhưng không cố định offset. Offset vẫn phụ thuộc ngày giờ và quy tắc của zone. Bộ dữ liệu timezone của JDK cũng có thể được cập nhật, làm thay đổi cách chuyển đổi lịch sử hoặc tương lai.

Với dữ liệu máy-máy, dùng chuẩn ISO và schema rõ ràng. Với UI, tên vùng theo locale có thể thân thiện hơn. Nếu chuỗi dùng cho kiểm toán hoặc đầu vào hệ thống khác, giữ thông tin cấu trúc gốc thay vì chỉ lưu tên hiển thị.

## 9. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Coi `-04:00` là `America/New_York` | Offset không chứa lịch sử/DST | Lưu `ZoneId` khi cần quy tắc vùng |
| Coi `EDT` là ID vùng ổn định | Tên ngắn có thể mơ hồ | Dùng `America/New_York` làm ID |
| Dùng `XXX` và mong in tên vùng | `XXX` chỉ định dạng offset | Dùng `VV` cho ID hoặc `z` cho tên |
| Dùng `VV` với `OffsetDateTime` và mong có zone gốc | Kiểu này không giữ ID vùng | Dùng `ZonedDateTime` khi có ZoneId |
| Gắn literal `'Z'` vào `LocalDateTime` | Chỉ thêm ký tự, không chuyển UTC | Áp zone đúng rồi đổi sang `Instant` |
| Nghĩ pattern sẽ tự chuyển giờ | Formatter chỉ trình bày trường hiện có | Chuyển giá trị bằng `withZoneSameInstant`/`atZone` trước |
| Bỏ qua locale khi cần tên vùng ổn định | JVM có thể dùng locale mặc định khác | Truyền `Locale` tường minh |
| Lưu tên vùng hiển thị để dựng lại lịch tương lai | Tên hiển thị không thay thế bộ quy tắc | Lưu `ZoneId` và dữ liệu lịch cần thiết |

## 10. Tự kiểm tra

**Câu 1.** Muốn in offset theo dạng `+07:00`, pattern nào phù hợp?

**Đáp án:** `XXX` hoặc `xxx` cho offset khác zero. Chúng định dạng offset, không chuyển giờ sang UTC.

**Câu 2.** Pattern nào in `America/New_York`?

**Đáp án:** `VV` với hai chữ V.

**Câu 3.** `z` và `zzzz` dùng làm gì?

**Đáp án:** Hiển thị tên vùng ngắn/dài theo locale và dữ liệu runtime, ví dụ `EDT` và `Eastern Daylight Time`.

**Câu 4.** Vì sao không dùng pattern `... 'Z'` để chuyển giờ Việt Nam thành UTC?

**Đáp án:** Chữ Z trong dấu nháy là literal. Phải áp đúng zone rồi chuyển thành instant trước khi tạo chuỗi UTC.

**Câu 5.** Có thể khôi phục `America/New_York` chỉ từ offset `-04:00` không?

**Đáp án:** Không. Nhiều vùng có thể cùng dùng offset đó tại một thời điểm; cần lưu ID vùng riêng.

**Ghi nhớ:** `XXX` biểu diễn offset ISO; `z`/`zzzz` hiển thị tên vùng; `VV` biểu diễn `ZoneId`. Chọn formatter dựa trên kiểu dữ liệu có đủ thông tin, không dựa trên việc thêm ký tự vào chuỗi.