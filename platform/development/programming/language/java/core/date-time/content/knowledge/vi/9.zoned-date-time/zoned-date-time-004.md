# Giờ lặp lại khi kết thúc giờ mùa hè với `ZonedDateTime`

Một lịch hẹn được đặt lúc **01:30 sáng ngày 01/11/2026 tại New York**. Câu hỏi tưởng đơn giản: lịch hẹn diễn ra lúc nào? Vào ngày đó, đồng hồ ở New York được vặn lùi một giờ để kết thúc giờ mùa hè (Daylight Saving Time, **DST**). Giờ **01:30 xảy ra hai lần**; mỗi lần tương ứng với một thời điểm UTC khác nhau. Nếu phần mềm chỉ lưu ngày, giờ và tên thành phố mà không biết cách giải quyết giờ trùng, một cuộc hẹn có thể sớm hoặc muộn hơn dự định **60 phút**.

Bài học giải thích hiện tượng **overlap** khi kết thúc DST, cách `ZonedDateTime` và `ZoneRules` giải quyết hai offset hợp lệ, cách chọn lần xuất hiện trước/sau, tác động đến cộng giờ và cộng ngày, và những chính sách cần thiết trong ứng dụng đặt lịch. Ví dụ dùng Java 17+ với dữ liệu thời gian xác định để có thể tự kiểm tra.

## 1. Mô hình đúng: giờ địa phương chưa phải một thời điểm

Cần phân biệt các khái niệm:

| Khái niệm / kiểu Java | Câu trả lời |
| --- | --- |
| `LocalDateTime` | “Ngày nào và mấy giờ trên đồng hồ?” |
| `ZoneId` | “Theo quy tắc múi giờ của vùng địa lý nào?” |
| `ZoneOffset` | “Tại thời điểm đó, đồng hồ địa phương lệch UTC bao nhiêu?” |
| `ZonedDateTime` | “Ngày giờ địa phương, vùng và offset đã được chọn là gì?” |
| `Instant` | “Mốc nào trên dòng thời gian toàn cầu?” |

Ví dụ `LocalDateTime.of(2026, 11, 1, 1, 30)` chỉ nói “01:30 ngày 01/11/2026”. Nó **không mang offset**, nên chưa xác định một `Instant`.

Khi kết hợp với `ZoneId.of("America/New_York")`, ta cần xem quy tắc múi giờ của ngày đó. Ở một ngày bình thường, một giờ địa phương có đúng một offset hợp lệ. Khi kết thúc DST, một đoạn giờ địa phương có thể ứng với **hai offset**. Vì thế, việc chuyển từ `LocalDateTime` sang `Instant` không phải lúc nào cũng là ánh xạ một-một.

Dùng `ZonedDateTime` giúp thể hiện kết quả đã chọn với cả vùng, offset và ngày giờ. Nhưng **việc chọn offset phải phù hợp với ý định người dùng**, đặc biệt đối với lịch hẹn và dữ liệu giao dịch quan trọng.

## 2. Đồng hồ “lùi lại” ở thời điểm kết thúc DST

Ở New York năm 2026, theo quy tắc múi giờ áp dụng cho ví dụ, ngày **01/11/2026** kết thúc DST. Khi thời điểm UTC tiến đến `2026-11-01T06:00:00Z`, đồng hồ địa phương chuyển:

- Từ **01:59:59.999…** với offset `-04:00` (giờ mùa hè, EDT).
- Sang **01:00:00** với offset `-05:00` (giờ tiêu chuẩn, EST).

Đồng hồ hiển thị một giờ đã từng hiển thị trước đó. Dòng thời gian toàn cầu **không hề đi lùi**.

~~~text
Dòng thời gian UTC tăng liên tục:
05:00Z       05:30Z       05:59Z       06:00Z       06:30Z       07:00Z
   |            |            |            |            |            |
01:00 -04   01:30 -04    01:59 -04     01:00 -05    01:30 -05    02:00 -05
       Lần xuất hiện thứ nhất          Lần xuất hiện thứ hai
              \                              /
               \_______ 01:30 trùng ________/
~~~

Hai cách hiểu hợp lệ của giờ **01:30 ngày 01/11/2026**:

| Giờ địa phương | Offset | Instant UTC | Ý nghĩa |
| --- | --- | --- | --- |
| `2026-11-01T01:30-04:00` | `-04:00` | `2026-11-01T05:30:00Z` | Lần xuất hiện sớm hơn |
| `2026-11-01T01:30-05:00` | `-05:00` | `2026-11-01T06:30:00Z` | Lần xuất hiện muộn hơn |

Chênh lệch giữa hai instant là **một giờ**, mặc dù cả hai đều có cùng `LocalDateTime` là `2026-11-01T01:30`.

Cần dùng cách gọi chính xác: **“offset sớm hơn”** ở đây tương ứng với offset được áp dụng trước khi đồng hồ lùi (`-04:00`); **“offset muộn hơn”** là offset sau khi đồng hồ lùi (`-05:00`). Không nên so dấu âm rồi tự suy rằng `-05:00` “sớm hơn” vì là số nhỏ hơn.

## 3. Overlap khác với gap

DST tạo ra hai dạng bất thường:

| Đặc điểm | Overlap (giờ trùng) | Gap (giờ bị bỏ qua) |
| --- | --- | --- |
| Cơ chế | Đồng hồ lùi lại | Đồng hồ nhảy tiến |
| Một giờ địa phương trong vùng bất thường | Có thể xảy ra **hai lần** | **Không xảy ra** |
| Số offset hợp lệ | 2 | 0 |
| Ví dụ New York 2026 | `01:30` ngày `01/11` | `02:30` ngày `08/03` |
| Câu hỏi nghiệp vụ | Chọn lần xuất hiện thứ nhất hay thứ hai? | Từ chối giờ hay dời sang giờ hợp lệ? |

Ngày thông thường có đúng **1 offset** hợp lệ. Không phải mọi quốc gia đều áp dụng DST, và lịch/giờ chuyển đổi có thể thay đổi theo chính sách. Vì vậy không tự viết quy tắc “tháng 11 chắc chắn trùng giờ” cho mọi vùng: sử dụng `ZoneRules` thông qua `ZoneId` và dữ liệu múi giờ của JDK.

Bài này tập trung vào **overlap** khi kết thúc DST. Gap được nhắc để phân biệt cách kiểm tra, không nên xử lý cả hai bằng cùng một quy tắc “chọn offset muộn hơn”.

## 4. Cách `LocalDateTime.atZone(ZoneId)` chọn offset mặc định

Khi có `LocalDateTime` và `ZoneId`, phép `atZone` tra quy tắc vùng để tạo `ZonedDateTime`.

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime defaultValue = local.atZone(newYork);
// 2026-11-01T01:30-04:00[America/New_York]
~~~

Với overlap này, `atZone` chọn **offset sớm hơn của lần xuất hiện đầu tiên** (`-04:00`) theo quy tắc mặc định. Đây là **một quyết định mặc định của API**, không phải bằng chứng người dùng đã muốn lịch hẹn ở lần 01:30 đầu.

`ZonedDateTime.of(local, zone)` và `ZonedDateTime.of(year, month, day, hour, minute, second, nano, zone)` cũng giải quyết giờ địa phương dựa trên quy tắc vùng. Nếu yêu cầu bảo toàn một lựa chọn offset cụ thể, đừng dựa vào mặc định một cách ngầm định.

Nếu lịch hẹn quan trọng cần phân biệt hai lần, hệ thống nên hỏi “01:30 trước hay sau khi đồng hồ lùi?”, hoặc thể hiện **offset kèm giờ** trong biểu mẫu.

## 5. Chọn lần xuất hiện đầu hoặc sau một cách tường minh

Sau khi có `ZonedDateTime` nằm trong overlap, dùng hai phương thức:

- `withEarlierOffsetAtOverlap()`: chọn offset hợp lệ của **lần xuất hiện sớm hơn**.
- `withLaterOffsetAtOverlap()`: chọn offset hợp lệ của **lần xuất hiện muộn hơn**.

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime first = local.atZone(zone)
        .withEarlierOffsetAtOverlap();

ZonedDateTime second = local.atZone(zone)
        .withLaterOffsetAtOverlap();

// first  = 2026-11-01T01:30-04:00[America/New_York]
// second = 2026-11-01T01:30-05:00[America/New_York]
~~~

Hai giá trị có **ngày/giờ địa phương giống nhau**, cùng `ZoneId` nhưng **offset khác nhau**.

~~~java
boolean sameLocal = first.toLocalDateTime()
        .equals(second.toLocalDateTime()); // true
boolean sameMoment = first.toInstant()
        .equals(second.toInstant()); // false

Duration separation = Duration.between(
        first.toInstant(), second.toInstant()); // PT1H
~~~

Nếu ngày giờ đang xét không thuộc overlap, các phương thức `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` không thay đổi offset hợp lệ thông thường. Tuy vậy chúng chỉ giải quyết **offset đã tồn tại trong một `ZonedDateTime`**, không thay thế việc phát hiện và xác nhận yêu cầu của người dùng.

Một chuỗi có **offset và zone**, chẳng hạn `2026-11-01T01:30-05:00[America/New_York]`, biểu diễn rõ lần thứ hai. Khi ghi dữ liệu lâu dài, cần hiểu rằng offset của một lần xuất hiện không thay thế được `ZoneId` để lập lịch định kỳ trong tương lai.

## 6. Kiểm tra `ZoneRules.getValidOffsets` trước khi quyết định

API quan trọng nhất để biết một `LocalDateTime` có mơ hồ không:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2026, 11, 1, 1, 30);

List<ZoneOffset> valid =
        zone.getRules().getValidOffsets(requested);

// Trong ví dụ: [-04:00, -05:00]
~~~

Cần import `java.util.List` và các lớp `java.time` nếu biên dịch độc lập.

Diễn giải số phần tử:

1. `valid.size() == 0`: giờ địa phương **không tồn tại** (gap).
2. `valid.size() == 1`: giờ địa phương hợp lệ và **không mơ hồ**.
3. `valid.size() == 2`: giờ thuộc **overlap**, có hai instant có thể chọn.

Với overlap, danh sách trả về có offset sớm hơn trước, offset muộn hơn sau. Sau khi ứng dụng đã nhận lựa chọn của người dùng, có thể dựng kết quả tường minh:

~~~java
ZonedDateTime first = ZonedDateTime.ofLocal(
        requested, zone, valid.get(0));

ZonedDateTime second = ZonedDateTime.ofLocal(
        requested, zone, valid.get(1));
~~~

`ofLocal` nhận offset ưu tiên, áp dụng offset đó **nếu nó hợp lệ trong zone tại giờ địa phương đã chọn**. Khi cần *từ chối* mọi kết hợp offset/vùng không hợp lệ, có thể dùng `ZonedDateTime.ofStrict(requested, chosenOffset, zone)`: phương thức này kiểm tra nghiêm ngặt và ném `DateTimeException` nếu offset không hợp lệ tại địa điểm và ngày giờ tương ứng.

Không tùy tiện dùng `ZoneOffset.ofHours(-4)` cho mọi tháng ở New York; offset thay đổi giữa các mùa. Đặc biệt, một offset sai vẫn có thể tạo một `OffsetDateTime` về mặt cú pháp nhưng diễn giải sai lịch hẹn ở vùng địa lý thật.

## 7. Hiển thị giờ trùng sao cho người dùng phân biệt được

Nếu giao diện chỉ hiển thị:

~~~text
Ngày 01/11/2026 — 01:30
~~~

thì hai cuộc hẹn ở New York có vẻ **giống hệt nhau**, dù xảy ra khác nhau 60 phút. Khi sự phân biệt có ý nghĩa, nên hiển thị thêm:

~~~text
01/11/2026 01:30 (EDT, UTC-04:00) — lần thứ nhất
01/11/2026 01:30 (EST, UTC-05:00) — lần thứ hai
~~~

Trong giao diện đa ngôn ngữ, tên viết tắt như `EDT` và `EST` có thể không đủ rõ hoặc gây nhập nhằng tại các khu vực khác. **Offset số** (`UTC-04:00`, `UTC-05:00`), vùng và lựa chọn “trước/sau khi đồng hồ lùi” giúp người dùng xác nhận chính xác hơn.

Khi hệ thống gửi thời gian qua API, một giá trị như `2026-11-01T01:30:00-05:00` đã xác định được instant, nhưng **chưa giữ được tên vùng** `America/New_York`. Nếu lịch tái diễn theo giờ New York, hãy giữ `ZoneId` riêng. Với một buổi họp đơn lẻ, có thể lưu thêm `Instant` để đối chiếu chính xác.

## 8. Giải thích sâu hơn: cùng local date-time nhưng khác instant

Từ hai `ZonedDateTime` ở trên:

~~~java
Instant firstInstant = first.toInstant();
// 2026-11-01T05:30:00Z

Instant secondInstant = second.toInstant();
// 2026-11-01T06:30:00Z
~~~

`first.toLocalDateTime().equals(second.toLocalDateTime())` là `true` vì cả hai đều `2026-11-01T01:30`. Nhưng `first.toInstant().equals(second.toInstant())` là `false`.

Điều đó có tác động thực tế:

- **Sắp xếp sự kiện:** so theo instant nếu cần thứ tự xảy ra thật, không chỉ theo giờ địa phương.
- **Phát hiện xung đột phòng họp:** hai mục “01:30” có thể cách nhau một giờ; cần xét khoảng thời gian thật của sự kiện.
- **Hạn hết hiệu lực:** hai giá trị 01:30 khác nhau có thể làm deadline sớm/muộn hơn một giờ.
- **Log và audit:** chuỗi ngày giờ không có offset sẽ mất thông tin để phục dựng thứ tự sự kiện.
- **Hiển thị lại dữ liệu:** nếu sau khi lưu `Instant` muốn trình bày theo New York, dùng `instant.atZone(zone)`. Phép đổi từ một instant đã xác định sang zone **không mơ hồ**: một instant cho một offset hợp lệ tại mốc đó.

**Không suy rằng `ZonedDateTime` đã kết hợp vùng thì phép `toLocalDateTime()` vẫn bảo toàn danh tính thời điểm.** `toLocalDateTime()` loại bỏ offset và zone; thao tác ngược `local.atZone(zone)` có thể chọn **lần đầu** ngay cả khi thời điểm gốc là **lần hai**.

## 9. Cộng thời gian qua lúc đồng hồ lùi

Cần phân biệt **cộng theo số giây thật** và **cộng theo lịch địa phương**.

### 9.1. Cộng một giờ thật bằng `plusHours(1)`

Bắt đầu tại lần 01:30 sớm hơn:

~~~java
ZonedDateTime first = LocalDateTime
        .of(2026, 11, 1, 1, 30)
        .atZone(ZoneId.of("America/New_York"));

ZonedDateTime oneHourLater = first.plusHours(1);

// first       = 2026-11-01T01:30-04:00[America/New_York]
// oneHourLater = 2026-11-01T01:30-05:00[America/New_York]
~~~

Sau **một giờ thực**, đồng hồ địa phương vẫn hiển thị **01:30**, chỉ offset đã chuyển từ `-04:00` sang `-05:00`. Đây là hiện tượng bình thường của overlap.

`ZonedDateTime.plusHours(1)` tính trên dòng thời gian đối với đơn vị giờ, nên tương đương thêm `Duration.ofHours(1)` vào instant rồi biểu diễn lại cùng zone.

### 9.2. `plusDays(1)` khác `plusHours(24)`

Bắt đầu từ **12:00 ngày 31/10/2026** tại New York:

~~~java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime start = LocalDateTime
        .of(2026, 10, 31, 12, 0).atZone(ny);

ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);

// start           = 2026-10-31T12:00-04:00[America/New_York]
// nextCalendarDay = 2026-11-01T12:00-05:00[America/New_York]
// after24Hours    = 2026-11-01T11:00-05:00[America/New_York]
~~~

Từ 12:00 ngày 31/10 đến 12:00 ngày 01/11 theo đồng hồ New York có **25 giờ thật**, vì ngày đó xuất hiện thêm một giờ. Nhưng `plusHours(24)` luôn cộng chính xác 24 giờ trên dòng thời gian nên hiển thị 11:00 ngày 01/11.

Sử dụng `plusDays(1)` khi quy tắc là “ngày hôm sau, cùng giờ địa phương”, và `plusHours(24)` hoặc `plus(Duration.ofHours(24))` khi quy tắc là “sau đúng 24 giờ”. Hai yêu cầu khác nhau, đặc biệt quanh thay đổi múi giờ.

### 9.3. `Duration.between` mới trả thời lượng thật

Nếu đã xác định hai `Instant` hoặc hai `ZonedDateTime` tương ứng, dùng `Duration.between` để tính khoảng thời gian thực. Không dùng `ChronoUnit.HOURS.between` trực tiếp trên hai `LocalDateTime` ở hai phía DST để suy ra thời lượng tuyệt đối: các con số trên đồng hồ không chứa offset nên sẽ bỏ mất một giờ lặp lại.

Ví dụ từ `01:30-04:00` đến `01:30-05:00` cùng ngày New York:

~~~java
Duration elapsed = Duration.between(
        first.toInstant(), second.toInstant());
// PT1H
~~~

Nếu chỉ lấy `first.toLocalDateTime()` và `second.toLocalDateTime()` rồi trừ, ta nhận **0 giờ theo đồng hồ địa phương**, dù thật sự đã trôi qua **1 giờ**.

## 10. Ví dụ Java 17+ chạy độc lập, đầu ra xác định

Chương trình dưới đây kiểm tra overlap, danh sách offset hợp lệ, lựa chọn lần đầu/lần sau, instant, phép cộng giờ và ngày. Nó dùng ngày cố định nên không phụ thuộc thời điểm chạy hay múi giờ mặc định của JVM.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class DstOverlapDemo {
    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");
        LocalDateTime ambiguous = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> valid = ny.getRules().getValidOffsets(ambiguous);

        ZonedDateTime first = ambiguous.atZone(ny)
                .withEarlierOffsetAtOverlap();
        ZonedDateTime second = ambiguous.atZone(ny)
                .withLaterOffsetAtOverlap();

        System.out.println("validOffsets=" + valid);
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("firstInstant=" + first.toInstant());
        System.out.println("secondInstant=" + second.toInstant());
        System.out.println("sameLocal=" + first.toLocalDateTime()
                .equals(second.toLocalDateTime()));
        System.out.println("sameInstant=" + first.toInstant()
                .equals(second.toInstant()));
        System.out.println("elapsed=" + Duration.between(
                first.toInstant(), second.toInstant()));
        System.out.println("plusOneHour=" + first.plusHours(1));

        ZonedDateTime dayBefore =
                LocalDateTime.of(2026, 10, 31, 12, 0).atZone(ny);
        ZonedDateTime plusDay = dayBefore.plusDays(1);
        ZonedDateTime plus24Hours = dayBefore.plusHours(24);

        System.out.println("dayBefore=" + dayBefore);
        System.out.println("plusDay=" + plusDay);
        System.out.println("plus24Hours=" + plus24Hours);
        System.out.println("hoursInCalendarDay=" + Duration.between(
                dayBefore.toInstant(), plusDay.toInstant()).toHours());

        Instant event = second.toInstant();
        System.out.println("roundTripSecond="
                + event.atZone(ny).equals(second));
        System.out.println("lostOffsetIfOnlyLocal="
                + second.toLocalDateTime().atZone(ny).toInstant()
                .equals(second.toInstant()));
    }
}
~~~

Lưu đúng tên `DstOverlapDemo.java` rồi chạy:

~~~bash
javac DstOverlapDemo.java
java DstOverlapDemo
~~~

Kết quả tương ứng với quy tắc múi giờ New York năm 2026:

~~~text
validOffsets=[-04:00, -05:00]
first=2026-11-01T01:30-04:00[America/New_York]
second=2026-11-01T01:30-05:00[America/New_York]
firstInstant=2026-11-01T05:30:00Z
secondInstant=2026-11-01T06:30:00Z
sameLocal=true
sameInstant=false
elapsed=PT1H
plusOneHour=2026-11-01T01:30-05:00[America/New_York]
dayBefore=2026-10-31T12:00-04:00[America/New_York]
plusDay=2026-11-01T12:00-05:00[America/New_York]
plus24Hours=2026-11-01T11:00-05:00[America/New_York]
hoursInCalendarDay=25
roundTripSecond=true
lostOffsetIfOnlyLocal=false
~~~

Dòng cuối rất quan trọng: `second.toLocalDateTime().atZone(ny)` sẽ áp lại lựa chọn mặc định của Java, tức `-04:00` cho giờ trùng, nên **không khôi phục được** instant lần thứ hai. Nếu lưu mỗi ngày giờ địa phương và chỉ giữ tên vùng, thông tin offset đã chọn cho một lần sự kiện có thể bị mất.

## 11. Chính sách nghiệp vụ cho cuộc hẹn ở giờ bị lặp

Không có một chính sách duy nhất đúng với tất cả ứng dụng. Một giải pháp đặt lịch cần xác định:

**Cách 1 — Chặn và yêu cầu chọn:** với giờ có `validOffsets.size() == 2`, giao diện cho người dùng chọn “lần đầu, UTC-04:00” hoặc “lần sau, UTC-05:00”. Cách này phù hợp khi sai lệch một giờ ảnh hưởng tới vé, lịch khám, giao dịch tài chính hoặc SLA.

**Cách 2 — Có mặc định được công bố:** một số hệ thống có thể quy định luôn chọn lần đầu hoặc lần sau. Quy tắc phải hiện rõ trong hợp đồng nghiệp vụ/API, có test và phải nhất quán qua các dịch vụ. Không nên ẩn quyết định đó dưới lời gọi `atZone` mà người dùng không biết.

**Cách 3 — Dựa trên instant đã xác định:** nếu dữ liệu nguồn là sự kiện thực sự đã xảy ra, hãy lưu `Instant` và hiển thị theo `ZoneId`. Trường hợp này không cần đoán “lần 01:30 nào” vì instant đã biết. Khi cần giữ nguyên nơi diễn ra sự kiện hoặc quy tắc tái diễn, lưu thêm `ZoneId`.

Một gợi ý luồng xử lý đặt lịch:

~~~text
Người dùng nhập local date-time + chọn địa điểm
              |
              v
Tìm ZoneId của địa điểm và getValidOffsets(local)
              |
       +------+-------+
       |      |       |
     0 offset 1 offset 2 offsets
       |      |       |
     gap    bình      overlap
       |    thường     |
   báo lỗi /  |       yêu cầu chọn
   chính sách |       offset đầu/sau
       |      |       |
       +------+-------+
              |
              v
  Tạo ZonedDateTime với offset hợp lệ
              |
              v
  Ghi nhận Instant + ZoneId + quy tắc/offset đã chọn
~~~

Đối với lịch họp **tái diễn hằng tuần ở New York**, đừng lấy instant của buổi đầu rồi cộng chính xác 7 ngày bằng `Duration` mãi mãi nếu mục tiêu là giữ **09:00 theo giờ địa phương**. Cần lưu **quy tắc lịch + ZoneId**, tạo từng lần theo lịch rồi xử lý gap/overlap của ngày đó.

## 12. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi mọi `LocalDateTime` chỉ có một instant trong zone | Không phát hiện giờ trùng | Kiểm tra `ZoneRules.getValidOffsets` |
| Tự hiểu `atZone` là “đúng lần 01:30 người dùng muốn” | Âm thầm chọn lần đầu theo mặc định | Yêu cầu chọn offset hoặc công bố chính sách |
| Dùng `-04:00` cố định cho New York quanh năm | Sai mùa đông và nhiều thời điểm lịch sử | Dùng `ZoneId` và quy tắc vùng |
| Chỉ lưu `2026-11-01 01:30`, không lưu offset/instant | Không biết sự kiện thuộc lần đầu hay lần sau | Lưu instant, offset đã chọn và ZoneId khi thích hợp |
| Chuyển `ZonedDateTime` thành `LocalDateTime` rồi gắn zone lại | Có thể đổi từ lần hai về lần đầu | Giữ `Instant` hoặc offset |
| Cộng `plusDays(1)` như thể tương đương 24 giờ | Ngày chuyển DST có thể dài 25 giờ | Chọn phép toán theo ý nghĩa nghiệp vụ |
| Chỉ dùng giờ địa phương để tính thời lượng | Giờ trùng cho độ dài bằng 0 dù thật trôi 1 giờ | Dùng `Duration` giữa hai instant |
| Hiển thị hai cuộc hẹn cùng `01:30` mà không có offset | Người dùng không phân biệt được hai lần | Hiển thị offset hoặc nhãn lần đầu/lần sau |
| Dùng timezone mặc định của máy chủ | Kết quả phụ thuộc hạ tầng | Dùng `ZoneId` từ cấu hình nghiệp vụ/địa điểm |
| Bỏ qua dữ liệu múi giờ cập nhật | Lịch tương lai có thể sai khi luật đổi | Cập nhật JDK/tzdb và kiểm thử lịch dự kiến |

## 13. Bài tập thực hành

1. Dùng `America/New_York` và `2026-11-01T01:30`. Gọi `getValidOffsets`, giải thích vì sao có hai offset `-04:00` và `-05:00`.
2. Tạo `ZonedDateTime` của **lần xuất hiện thứ nhất** và **thứ hai** bằng `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()`. So sánh `toLocalDateTime()` và `toInstant()`.
3. Tính `Duration.between(first.toInstant(), second.toInstant())`. Vì sao kết quả một giờ dù đồng hồ hiển thị cùng 01:30?
4. Từ 01:30 `-04:00`, gọi `plusHours(1)`. Giải thích tại sao ngày giờ hiển thị vẫn là `01:30` nhưng offset thay đổi.
5. Từ `2026-10-31T12:00` tại New York, so sánh `plusDays(1)` và `plusHours(24)`. Phép nào phù hợp với thông báo “12:00 ngày hôm sau”, phép nào phù hợp “đúng 24 giờ sau”?
6. Thử `LocalDateTime.of(2026,3,8,2,30)` tại New York. `getValidOffsets` trả bao nhiêu offset? Hãy so sánh với overlap ngày 01/11.
7. Thiết kế API nhận lịch hẹn khi giờ nhập thuộc overlap: yêu cầu đầu vào, cách trả về hai lựa chọn có offset, dữ liệu nào cần lưu và cách hiển thị lại mà không mất lựa chọn.

**Ghi nhớ:** Khi kết thúc DST, một khoảng giờ địa phương **được lặp lại**. `LocalDateTime` và `ZoneId` có thể ứng với **hai instant**; `atZone` chọn offset đầu theo mặc định nhưng không biết ý định người dùng. `ZoneRules.getValidOffsets` giúp phát hiện overlap, còn `withEarlierOffsetAtOverlap` và `withLaterOffsetAtOverlap` cho phép chọn đúng lần xảy ra. Khi cần tính toán, sắp xếp hoặc lưu thời điểm tuyệt đối, phải bảo toàn **instant và thông tin vùng/offset cần thiết**.