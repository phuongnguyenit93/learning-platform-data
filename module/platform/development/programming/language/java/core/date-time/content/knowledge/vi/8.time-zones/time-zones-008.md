# ZoneRules, độ lệch hợp lệ và thời điểm chuyển đổi trong Java

## 1. Mục tiêu

Một lịch hẹn ghi **01:30 tại New York ngày 01/11/2026** có thể tương ứng với **hai thời điểm khác nhau**; ngược lại, **02:30 tại New York ngày 08/03/2026** là giờ địa phương **không tồn tại**. Đây là hệ quả của việc thay đổi độ lệch với UTC, thường gắn với daylight saving time (DST, giờ mùa hè). Trong Java, các quy tắc này được mô hình hóa bởi **ZoneRules** trong gói **java.time.zone**.

Bài học giúp:

- Phân biệt **ZoneId**, **ZoneOffset**, **LocalDateTime**, **Instant** và **ZonedDateTime**.
- Tra offset chính xác của một **Instant** bằng **ZoneRules.getOffset(Instant)**.
- Kiểm tra offset hợp lệ của một **LocalDateTime** bằng **getValidOffsets(...)** và **isValidOffset(...)**.
- Nhận diện giờ **bình thường (normal)**, **gap** (giờ không tồn tại), **overlap** (giờ lặp).
- Đọc **ZoneOffsetTransition**, thời điểm thay đổi offset, offset trước/sau và độ dài bước chuyển.
- Phân biệt tra **getOffset(LocalDateTime)** với kiểm tra đầy đủ tính hợp lệ.
- Lựa chọn hành vi khi đổi giờ địa phương sang **Instant**, áp dụng **ofStrict**, **ofLocal**, **withEarlierOffsetAtOverlap** và **withLaterOffsetAtOverlap**.
- Tra thời điểm chuyển đổi kế tiếp/trước đó, đọc quy tắc lịch sử và quy tắc lặp tương lai, hiểu giới hạn của dữ liệu tzdb.

Đối tượng đọc đã biết cơ bản **java.time**; các ví dụ độc lập dùng **Java 17+**. Không cần dùng múi giờ hệ thống của máy để chạy các ví dụ cố định.

## 2. Mô hình thời gian: phải phân biệt đầu vào

| Kiểu | Lưu/diễn tả | Có xác định một mốc tuyệt đối không? |
| --- | --- | --- |
| **Instant** | Mốc trên dòng thời gian, thường hiển thị UTC, ví dụ 2026-10-24T12:00:00Z | **Có** |
| **LocalDateTime** | Ngày và giờ theo đồng hồ địa phương, ví dụ 2026-11-01T01:30 | **Chưa**: không có offset/zone |
| **ZoneOffset** | Độ lệch UTC tại một lần quan sát, ví dụ -04:00 hoặc -05:00 | Tự nó không phải mốc; kết hợp với LocalDateTime thì xác định được Instant |
| **ZoneId** | Vùng có các quy tắc thời gian, ví dụ America/New_York | Tự nó chưa là mốc |
| **ZonedDateTime** | Ngày/giờ địa phương + ZoneId + offset đã chọn | **Có**: có thể lấy toInstant() |
| **ZoneRules** | Tập quy tắc chọn offset theo Instant/local date-time | Không lưu một cuộc hẹn cụ thể |
| **ZoneOffsetTransition** | Một lần thay đổi offset, có mốc chuyển và offset trước/sau | Mô tả sự kiện đổi offset |

Cùng một **Instant** chỉ có **một offset hợp lệ** tại một ZoneId cụ thể. Nhưng từ **LocalDateTime + ZoneId** chưa chắc suy ra một Instant duy nhất. Vì vậy cần ZoneRules khi nhận giờ địa phương do người dùng nhập.

**UTC offset** khác **tên vùng**. Offset **-04:00** nói đồng hồ địa phương chậm hơn UTC 4 giờ; ZoneId **America/New_York** có thể dùng **-04:00** vào mùa hè và **-05:00** vào mùa đông. Cấu hình offset cố định không mang toàn bộ lịch sử và luật chuyển giờ của vùng.

## 3. Lấy ZoneRules từ ZoneId

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneRules rules = newYork.getRules();
~~~

Đây là đoạn trích minh họa, cần import **java.time.ZoneId** và **java.time.zone.ZoneRules**, đặt trong phương thức.

**ZoneRules** là mô hình bất biến và an toàn để dùng từ nhiều luồng trong API Java. Những quy tắc này thường dựa trên dữ liệu múi giờ **tzdb** được đóng gói/cung cấp cùng runtime. Quy tắc chính trị có thể thay đổi về sau; đặc biệt lịch giờ tương lai không được xem là vĩnh viễn nếu hệ thống chưa cập nhật tzdb.

Các API cốt lõi:

| API | Input | Trả về | Khi nào sử dụng |
| --- | --- | --- | --- |
| **getOffset(Instant)** | Instant | **ZoneOffset** | Cần offset chắc chắn tại mốc tuyệt đối |
| **getOffset(LocalDateTime)** | LocalDateTime | **ZoneOffset** phù hợp nhất | Tiện nhưng có thể chưa giải quyết đúng gap/overlap |
| **getValidOffsets(LocalDateTime)** | LocalDateTime | **List<ZoneOffset>** | Muốn biết 0, 1 hay 2 offset hợp lệ |
| **isValidOffset(LocalDateTime, ZoneOffset)** | LocalDateTime + offset | **boolean** | Xác thực offset khách hàng gửi kèm giờ |
| **getTransition(LocalDateTime)** | LocalDateTime | **ZoneOffsetTransition** hoặc null | Xem một thời điểm local có nằm trong gap/overlap không |
| **nextTransition(Instant)** | Instant | Transition sau mốc này hoặc null | Lịch đổi offset kế tiếp |
| **previousTransition(Instant)** | Instant | Transition trước mốc này hoặc null | Điều tra biến đổi gần đây |
| **getTransitions()** | Không | List các transition lịch sử cụ thể | Kiểm tra lịch sử trong dữ liệu quy tắc |
| **getTransitionRules()** | Không | List các quy tắc chuyển đổi định kỳ | Đọc quy tắc lặp dùng cho tính tương lai |
| **getStandardOffset(Instant)** | Instant | ZoneOffset chuẩn | Phân biệt phần bù DST với offset chuẩn |
| **getDaylightSavings(Instant)** | Instant | Duration | Độ chênh do DST tại mốc đó |
| **isDaylightSavings(Instant)** | Instant | boolean | Một Instant có đang trong DST không |
| **isFixedOffset()** | Không | boolean | Quy tắc có offset không thay đổi trong toàn bộ miền quy tắc không |

**Chú ý:** Hai overload **getOffset(Instant)** và **getOffset(LocalDateTime)** nhận đầu vào khác nhau và có ý nghĩa khác nhau. Với Instant, ánh xạ là rõ ràng. Với LocalDateTime, trả về một offset thuận tiện **không chứng minh** giờ đó có thật hoặc chỉ xuất hiện một lần.

## 4. Ba trạng thái của một LocalDateTime

Khi kiểm tra giờ địa phương **local** trong **rules**:

~~~java
List<ZoneOffset> offsets = rules.getValidOffsets(local);
~~~

Đây là đoạn trích với biến rules/local có sẵn và import **java.time.ZoneOffset**, **java.util.List**.

**Trường hợp 1 — Normal:** có **1 offset** hợp lệ. Ví dụ **2026-02-01 12:00 New York** chỉ có **-05:00**, nên mốc UTC tương ứng là **17:00Z**.

**Trường hợp 2 — Gap:** có **0 offset** hợp lệ. Khi đồng hồ nhảy tiến, một số giờ địa phương không tồn tại. Tại New York **08/03/2026**, đồng hồ chuyển từ gần **01:59:59-05:00** sang **03:00-04:00**, nên **02:30** nằm trong gap.

**Trường hợp 3 — Overlap:** thường có **2 offset** hợp lệ. Khi đồng hồ lùi, một khoảng giờ địa phương xuất hiện hai lần. Tại New York **01/11/2026**, đồng hồ từ gần **01:59:59-04:00** quay về **01:00-05:00**, nên **01:30** là một giờ địa phương của cả hai lần.

| LocalDateTime tại America/New_York | Số offset | Danh sách | Ý nghĩa |
| --- | ---: | --- | --- |
| **2026-02-01T12:00** | 1 | [-05:00] | Giờ bình thường |
| **2026-03-08T02:30** | 0 | [] | Không tồn tại |
| **2026-11-01T01:30** | 2 | [-04:00, -05:00] | Xuất hiện hai lần |

Đối với overlap thông thường, danh sách theo Javadoc đặt offset ứng với lần xuất hiện **sớm hơn** trước rồi offset **muộn hơn** sau. Java quy định danh sách là 0/1/2 trong các trường hợp thực tế thông dụng; về mặt lý thuyết thay đổi múi giờ cực đoan có thể dẫn tới cấu hình nhiều offset, vì vậy code kiểm tra logic nghiệp vụ không nên đánh đồng mọi kích thước khác 1 với một loại lỗi cố định.

Một lần đổi offset **không nhất thiết bằng một giờ** và **không phải vùng nào cũng có DST**. Các thay đổi chính phủ có thể làm lịch sử múi giờ phức tạp hơn công thức “mùa xuân cộng một giờ, mùa thu trừ một giờ”.

## 5. GetOffset cho Instant: luôn có lời giải tại một ZoneId

Tại một mốc UTC đã biết, quy tắc vùng xác định offset duy nhất:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

Instant summer = Instant.parse("2026-07-01T12:00:00Z");
Instant winter = Instant.parse("2026-01-01T12:00:00Z");

ZoneOffset summerOffset = rules.getOffset(summer); // -04:00
ZoneOffset winterOffset = rules.getOffset(winter); // -05:00
~~~

Đây là đoạn trích cần import từ java.time và java.time.zone, đặt trong phương thức.

**Instant.atZone(zone)** hoặc **ZonedDateTime.ofInstant(instant, zone)** sẽ chuyển mốc tuyệt đối thành giờ địa phương theo đúng offset tại thời điểm đó. Khi đổi sang một vùng khác bằng **withZoneSameInstant(otherZone)**, đồng hồ hiển thị thay đổi nhưng Instant không đổi.

Đối với sự kiện đã xảy ra (audit, thanh toán, lịch sử truy cập), nên lưu mốc **Instant**; chỉ gắn ZoneId để hiển thị hay tính ngày địa phương. Không cần tự suy đoán offset từ tháng hiện tại hoặc quốc gia.

## 6. GetOffset cho LocalDateTime: kết quả có thể chỉ là “best effort”

**ZoneRules.getOffset(LocalDateTime)** trả **một offset phù hợp nhất** theo quy tắc. Khi local time bình thường, đó là offset duy nhất hợp lệ. Trong **gap** hoặc **overlap**, API này trả **offset trước transition** theo chính sách của Java; kết quả không bảo đảm tổ hợp local+offset là hợp lệ duy nhất.

~~~java
LocalDateTime gap =
        LocalDateTime.of(2026, 3, 8, 2, 30);
ZoneOffset guessed = rules.getOffset(gap); // -05:00
List<ZoneOffset> valid = rules.getValidOffsets(gap); // []
~~~

Đây là đoạn trích cần có biến rules tương ứng America/New_York và import java.time.*. Dù **guessed** là -05:00, **02:30-05:00** không phải giờ địa phương hợp lệ tại New York ngày đó. Nếu ứng dụng dùng guessed rồi gọi **local.toInstant(guessed)**, nó sẽ tạo một Instant toán học, nhưng tổ hợp thời gian và vùng đã bị diễn giải sai.

**Nguyên tắc:** khi tính đúng/sai của một giờ do người dùng nhập, dùng **getValidOffsets(...)**, **isValidOffset(...)** hoặc **getTransition(...)** thay cho chỉ tin **getOffset(LocalDateTime)**.

## 7. ZoneOffsetTransition mô tả đúng bước thay đổi

Lấy transition liên quan tới giờ địa phương:

~~~java
ZoneOffsetTransition transition =
        rules.getTransition(local);
~~~

Đây là đoạn trích cần import **java.time.zone.ZoneOffsetTransition**. Trong **normal**, getTransition(local) trả **null**; trong **gap** hoặc **overlap**, thường trả transition liên quan.

Các thuộc tính quan trọng của **ZoneOffsetTransition**:

| API | Ý nghĩa |
| --- | --- |
| **getInstant()** | Instant mà offset đổi |
| **getOffsetBefore()** | Offset ngay trước bước chuyển |
| **getOffsetAfter()** | Offset ngay sau bước chuyển |
| **getDateTimeBefore()** | LocalDateTime tại đường biên trước thay đổi |
| **getDateTimeAfter()** | LocalDateTime tại đường biên sau thay đổi |
| **getDuration()** | Độ chênh offset, có dấu: gap dương, overlap âm |
| **isGap()** | true khi chuyển tiến tạo giờ không tồn tại |
| **isOverlap()** | true khi chuyển lùi tạo giờ bị lặp |
| **getValidOffsets()** | Danh sách offset hợp lệ cho phần giờ chuyển đổi: gap rỗng, overlap gồm hai offset |
| **toEpochSecond()** | Giây epoch của mốc transition |

**Ví dụ spring gap — New York 08/03/2026:**

- Offset trước: **-05:00**.
- Offset sau: **-04:00**.
- Biên giờ trước: **2026-03-08T02:00**.
- Biên giờ sau: **2026-03-08T03:00**.
- Instant chuyển đổi: **2026-03-08T07:00:00Z**.
- Duration chuyển đổi: **PT1H** (dương).
- Khoảng giờ **[02:00, 03:00)** ở đồng hồ New York không tồn tại.

**Ví dụ autumn overlap — New York 01/11/2026:**

- Offset trước: **-04:00**.
- Offset sau: **-05:00**.
- Biên giờ trước: **2026-11-01T02:00**.
- Biên giờ sau: **2026-11-01T01:00**.
- Instant chuyển đổi: **2026-11-01T06:00:00Z**.
- Duration chuyển đổi: **PT-1H** (âm).
- Khoảng giờ **[01:00, 02:00)** ở đồng hồ New York xuất hiện hai lần.

**Lưu ý dấu:** getDuration() của **ZoneOffsetTransition** phản ánh **độ dịch đồng hồ/offset khi chuyển đổi**, không phải “thời gian làm việc” của một ca. Không áp dụng dấu này để trả lương hay tính duration nghiệp vụ nếu chưa xác định hai Instant cụ thể.

## 8. Giải quyết gap theo chính sách rõ ràng

Người dùng chọn **02:30 ngày 08/03/2026 ở New York**. ZoneRules cho danh sách offset hợp lệ rỗng. Có ít nhất ba cách xử lý nghiệp vụ:

1. **Từ chối** và yêu cầu chọn giờ tồn tại, phù hợp đặt chỗ, giao dịch cần tính xác thực.
2. **Dời theo độ dài gap**: **02:30** được điều chỉnh thành **03:30-04:00**. Đây là chiến lược mặc định khi dùng **LocalDateTime.atZone(zone)** trong nhiều trường hợp.
3. **Chuyển sang mốc hợp lệ đầu tiên sau gap**, ví dụ **03:00-04:00** thay vì 03:30, nếu chính sách riêng yêu cầu.

Những cách này không tương đương. Ví dụ đặt báo thức 02:30 hằng ngày có thể chọn chuyển tới 03:00 hoặc bỏ qua lần đó; một cuộc họp do người dùng đặt có thể yêu cầu xác nhận lại.

### API mặc định và API nghiêm ngặt

~~~java
LocalDateTime requested =
        LocalDateTime.of(2026, 3, 8, 2, 30);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime adjusted = requested.atZone(zone);
// 2026-03-08T03:30-04:00[America/New_York]

ZonedDateTime strict = ZonedDateTime.ofStrict(
        requested, ZoneOffset.ofHours(-5), zone);
// Ném DateTimeException: tổ hợp local + offset + vùng không hợp lệ.
~~~

Đây là đoạn trích minh họa; dòng **ofStrict** ném ngoại lệ và cần try/catch nếu chạy trong ứng dụng. **ofStrict(...)** kiểm tra offset được đưa vào có thực sự hợp lệ cho LocalDateTime và ZoneId; nó không tự điều chỉnh gap. Trong overlap, có thể dùng ofStrict với một trong các offset hợp lệ để tránh mơ hồ.

**Không tự tạo Instant** bằng cách lấy kết quả guessed offset của getOffset(LocalDateTime) khi giờ nằm trong gap; nếu muốn dời lịch, hãy dời LocalDateTime theo chính sách rồi xác minh lại bằng rules.

## 9. Giải quyết overlap: chọn một trong hai thời điểm

Với **2026-11-01T01:30** tại New York:

~~~text
Lần sớm: 2026-11-01T01:30-04:00 -> 2026-11-01T05:30:00Z
Lần muộn: 2026-11-01T01:30-05:00 -> 2026-11-01T06:30:00Z
~~~

Hai giá trị cùng có **LocalDateTime 01:30**, nhưng chênh **60 phút thực**. Nếu ứng dụng lập lịch chấm công, đặt lịch hay thanh toán, cần chọn chính xác lần nào.

Các lựa chọn Java:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneId zone = ZoneId.of("America/New_York");
List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

ZonedDateTime earlier =
        ZonedDateTime.ofStrict(local, valid.get(0), zone);
ZonedDateTime later =
        ZonedDateTime.ofStrict(local, valid.get(1), zone);

// Có thể điều chỉnh offset ở một ZonedDateTime đã tạo:
ZonedDateTime changed = earlier.withLaterOffsetAtOverlap();
~~~

Đây là đoạn trích cần import java.time.* và java.util.List. **valid** ở đây có hai phần tử; trong code tổng quát phải kiểm tra kích thước trước khi gọi get(1).

**LocalDateTime.atZone(zone)** mặc định chọn offset sớm hơn (thường là offset mùa hè) khi không có ngữ cảnh về offset trước đó. **ZonedDateTime.ofLocal(local, zone, preferredOffset)** ưu tiên offset do caller đưa vào **nếu hợp lệ**; nếu không hợp lệ thì tuân theo quy tắc mặc định, và trong gap vẫn có thể tự điều chỉnh. **ZonedDateTime.ofStrict(local, offset, zone)** từ chối cặp không hợp lệ, phù hợp khi API yêu cầu offset do người dùng cung cấp.

**withEarlierOffsetAtOverlap()** và **withLaterOffsetAtOverlap()** chỉ đổi lựa chọn trong khoảng overlap; chúng không đổi mốc local 01:30, nhưng **sẽ đổi Instant** tương ứng. Ngoài overlap, chúng không có tác dụng thay đổi có ý nghĩa.

Nếu đối tác API gửi cả giờ địa phương, ZoneId và offset:

- Kiểm tra **rules.isValidOffset(local, suppliedOffset)**.
- Nếu false, trả lỗi hoặc giải quyết theo chính sách công bố.
- Nếu true, dùng **ZonedDateTime.ofStrict(...)**.
- Nếu thông tin offset vắng mặt và thuộc overlap, hỏi người dùng hoặc dùng chính sách nhất quán đã xác định.

## 10. Demo Java 17+ chạy độc lập

Tạo file **ZoneRulesDemo.java**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class ZoneRulesDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        Instant instant = Instant.parse("2026-10-24T12:00:00Z");
        System.out.println("Instant offset: " + rules.getOffset(instant));

        LocalDateTime normal = LocalDateTime.of(
                2026, 2, 1, 12, 0);
        LocalDateTime gap = LocalDateTime.of(
                2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                2026, 11, 1, 1, 30);

        System.out.println("Normal valid: " +
                rules.getValidOffsets(normal));
        System.out.println("Gap valid: " +
                rules.getValidOffsets(gap));
        System.out.println("Overlap valid: " +
                rules.getValidOffsets(overlap));

        ZoneOffsetTransition spring = rules.getTransition(gap);
        System.out.println("Spring gap: " + spring.isGap());
        System.out.println("Spring offsets: " +
                spring.getOffsetBefore() + " -> " +
                spring.getOffsetAfter());
        System.out.println("Spring instant: " + spring.getInstant());
        System.out.println("Spring duration: " + spring.getDuration());
        System.out.println("Default gap: " + gap.atZone(zone));

        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(-5), zone);
            System.out.println("Strict gap: accepted");
        } catch (DateTimeException ex) {
            System.out.println("Strict gap: rejected");
        }

        ZoneOffsetTransition autumn = rules.getTransition(overlap);
        System.out.println("Autumn overlap: " + autumn.isOverlap());
        System.out.println("Autumn offsets: " +
                autumn.getOffsetBefore() + " -> " +
                autumn.getOffsetAfter());
        System.out.println("Autumn instant: " + autumn.getInstant());
        System.out.println("Autumn duration: " + autumn.getDuration());

        List<ZoneOffset> options = rules.getValidOffsets(overlap);
        ZonedDateTime earlier =
                ZonedDateTime.ofStrict(overlap, options.get(0), zone);
        ZonedDateTime later =
                ZonedDateTime.ofStrict(overlap, options.get(1), zone);

        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());
        System.out.println("Later offset valid: " +
                rules.isValidOffset(overlap, options.get(1)));

        ZoneOffsetTransition next = rules.nextTransition(
                Instant.parse("2026-03-01T00:00:00Z"));
        System.out.println("Next transition: " + next.getInstant());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ZoneRulesDemo.java
java ZoneRulesDemo
~~~

Đầu ra tương ứng với quy tắc New York năm 2026 trong tzdb:

~~~text
Instant offset: -04:00
Normal valid: [-05:00]
Gap valid: []
Overlap valid: [-04:00, -05:00]
Spring gap: true
Spring offsets: -05:00 -> -04:00
Spring instant: 2026-03-08T07:00:00Z
Spring duration: PT1H
Default gap: 2026-03-08T03:30-04:00[America/New_York]
Strict gap: rejected
Autumn overlap: true
Autumn offsets: -04:00 -> -05:00
Autumn instant: 2026-11-01T06:00:00Z
Autumn duration: PT-1H
Earlier instant: 2026-11-01T05:30:00Z
Later instant: 2026-11-01T06:30:00Z
Later offset valid: true
Next transition: 2026-03-08T07:00:00Z
~~~

**Vì sao kết quả đúng?**

- **2026-10-24T12:00Z** xảy ra khi New York còn offset **-04:00**, còn **01/02/2026** dùng **-05:00**.
- Tại giờ gap **02:30 ngày 08/03**, không có offset hợp lệ nên list rỗng. **atZone** mặc định đẩy một giờ đến **03:30-04:00**; **ofStrict** từ chối.
- Transition ngày 08/03 diễn ra lúc **07:00Z**, đổi offset **-05:00 → -04:00**, độ lệch tăng một giờ nên **getDuration()** là **PT1H**.
- Giờ overlap **01:30 ngày 01/11** nhận hai offset. Offset **-04:00** tạo Instant **05:30Z**; offset **-05:00** tạo **06:30Z**.
- Transition ngày 01/11 diễn ra lúc **06:00Z**, offset lùi một giờ nên duration **PT-1H**.
- **nextTransition(...)** sau 01/03/2026 là lần thay đổi vào ngày 08/03/2026.

Ví dụ không lấy giờ hiện tại của máy. Tzdb có thể được cập nhật về sau nếu luật địa phương thay đổi; với hệ thống nghiệp vụ cần dùng JDK/tzdb ở môi trường triển khai thực tế để kiểm thử.

## 11. Tìm transition trước/sau một Instant

Khi biết mốc tuyệt đối, có thể tra:

~~~java
ZoneRules rules =
        ZoneId.of("America/New_York").getRules();

ZoneOffsetTransition upcoming = rules.nextTransition(
        Instant.parse("2026-03-01T00:00:00Z"));

ZoneOffsetTransition previous = rules.previousTransition(
        Instant.parse("2026-11-02T00:00:00Z"));
~~~

Đây là đoạn trích cần import java.time.* và java.time.zone.*.

- **nextTransition(instant)** tìm transition **sau** Instant đầu vào.
- **previousTransition(instant)** tìm transition **trước** Instant đầu vào.
- Kết quả có thể **null** khi không có transition phù hợp.
- Không nên giả định mọi vùng có transition đều đặn mỗi năm; một số vùng cố định không có transition tương lai.
- Khi chuẩn bị lập lịch, dùng kết quả để cảnh báo người dùng về ngày chuyển giờ, kiểm thử biên hoặc tính lịch địa phương có vùng.

### Lịch sử đã lưu và quy tắc lặp trong tương lai

**getTransitions()** cung cấp danh sách transition lịch sử cụ thể được lưu trong ZoneRules. **getTransitionRules()** cung cấp các quy tắc tái diễn (thường dành cho transition tương lai). Hai danh sách **không phải hai biểu diễn tương đương của tất cả những thay đổi đã có và sẽ có**; muốn tìm chuyển đổi kế tiếp tại một Instant cụ thể, nên dùng **nextTransition**. Không giả định số phần tử, không tự diễn giải các quy tắc lặp thành ngày bằng các công thức cố định nếu có thể dùng phương thức cấp cao.

**ZoneOffsetTransitionRule** mô tả kiểu quy tắc chuyển đổi trong năm. Nó có thể tạo transition tại một năm với **createTransition(year)**. Đây là API mức thấp dùng khi làm công cụ khám phá quy tắc và bộ lập lịch đặc thù; ứng dụng chỉ cần ngày/giờ hợp lệ thường sử dụng ZoneRules trực tiếp.

## 12. Standard offset và daylight savings

**getOffset(Instant)** trả offset thực đang áp dụng, trong khi:

- **getStandardOffset(instant)** trả offset chuẩn tại mốc đó.
- **getDaylightSavings(instant)** trả một **Duration** biểu diễn chênh lệch giữa offset thực và offset chuẩn.
- **isDaylightSavings(instant)** cho biết mốc đó có thuộc trạng thái DST theo quy tắc Java không.

Ví dụ New York vào giữa mùa hè 2026 thường có **offset -04:00**, **standard offset -05:00**, nên phần cộng DST là **PT1H**. Mùa đông thường dùng -05:00 và độ bù DST bằng zero.

Tuy vậy:

1. **DST không nhất thiết đúng +1 giờ**; có vùng dùng bước chuyển khác.
2. **Thay đổi standard offset** vì quyết định hành chính không đồng nghĩa với DST.
3. **ZoneRules.isFixedOffset()** cho biết quy tắc không có thay đổi offset; nó không trực tiếp trả lời “cửa hàng này dùng DST theo mùa không?” trong một giai đoạn tùy ý.
4. Kết quả phụ thuộc phạm vi lịch sử và phiên bản dữ liệu vùng do runtime cung cấp.

Không cố suy diễn trạng thái DST chỉ từ tên viết tắt mùa hè/mùa đông hoặc chỉ từ tháng trong năm.

## 13. Chính sách chuyển LocalDateTime thành Instant

Với dữ liệu người dùng nhập **local + zone**, một quy trình an toàn có thể là:

1. Parse thành **LocalDateTime** hợp lệ và nhận **ZoneId** IANA từ địa điểm/người dùng.
2. Lấy **ZoneRules** và **List<ZoneOffset> validOffsets = rules.getValidOffsets(local)**.
3. Nếu danh sách có **1 offset**, dùng **ZonedDateTime.ofStrict(local, thatOffset, zone)** hoặc local.atZone(zone).
4. Nếu danh sách **rỗng (gap)**, chọn chính sách: từ chối hoặc dời đến giờ hợp lệ; kiểm tra lại trước khi ghi.
5. Nếu danh sách **hai offset (overlap)**, cho phép người dùng chọn lần sớm hoặc muộn, hoặc chọn theo quy tắc nghiệp vụ và lưu lựa chọn.
6. Sau khi tạo ZonedDateTime, lưu **toInstant()** nếu đó là cuộc hẹn đã được chốt thành mốc tuyệt đối, cùng thông tin vùng và mục đích lặp lịch khi cần.
7. Đối với lịch lặp theo đồng hồ (ví dụ 09:00 hằng ngày), giữ **LocalTime/LocalDateTime + ZoneId + quy tắc lặp** và tính từng lần phát sinh mới; không cố định một Instant/UTC offset để đại diện cho tất cả các ngày.

Mẫu pseudo-code minh họa ý tưởng, không phải chương trình độc lập:

~~~java
List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);

if (offsets.isEmpty()) {
    // Áp dụng chính sách gap: từ chối hoặc chọn giờ khác.
} else if (offsets.size() == 1) {
    ZonedDateTime resolved =
            ZonedDateTime.ofStrict(local, offsets.get(0), zone);
} else {
    // Overlap: yêu cầu offset ưu tiên hoặc áp dụng chính sách rõ ràng.
    // Sau đó dùng ZonedDateTime.ofStrict(local, chosenOffset, zone).
}
~~~

**Cần thiết để kiểm toán:** lưu chính sách áp dụng, Instant sau khi giải quyết và ZoneId nếu sau này phải giải thích tại sao cuộc hẹn được hiển thị theo giờ địa phương đó. Với lịch trong tương lai xa, quy tắc timezone có thể thay đổi và ứng dụng cần chính sách tái tính hoặc giữ nguyên Instant đã xác nhận.

## 14. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Dùng **getOffset(LocalDateTime)** để coi giờ chắc chắn hợp lệ | Chấp nhận giờ trong gap hoặc bỏ qua lần thứ hai của overlap | Kiểm tra **getValidOffsets**, **isValidOffset** |
| Coi **ZoneOffset** là **ZoneId khu vực** | Không mô hình hóa lịch đổi offset | Lưu ZoneId IANA khi cần quy tắc vùng |
| Giả định mọi giờ local có 1 Instant | Hỏng khi gap/overlap | Xử lý các kích thước danh sách 0/1/2 |
| Dùng **atZone** trong tác vụ nhạy cảm mà không biết mặc định | Âm thầm dời giờ gap hoặc chọn sớm overlap | Chính sách rõ ràng; dùng **ofStrict** khi cần |
| Đọc **getDuration()** của transition như thời lượng ca làm | Nhầm độ đổi đồng hồ với thời lượng nghiệp vụ | Đo Duration giữa hai Instant |
| Cố định DST là cộng/trừ 1 giờ ở mọi vùng | Sai với thay đổi bất thường/historic | Tra ZoneRules từ ZoneId |
| Dùng **getTransitions()** như danh sách tất cả chuyển đổi tương lai | Bỏ qua các quy tắc lặp | Dùng **nextTransition**, đọc thêm getTransitionRules khi cần |
| Gắn giờ local mơ hồ với offset ngẫu nhiên | Ghi sự kiện lệch 1 giờ | Chọn offset qua validOffsets và xác nhận |
| Dùng múi giờ mặc định của server | Kết quả đổi theo môi trường chạy | Nhận ZoneId cấu hình của nghiệp vụ |
| Lưu duy nhất giờ local cho timestamp giao dịch | Không biết mốc thật xảy ra khi nào | Lưu **Instant**, bổ sung zone cho hiển thị |
| Không kiểm thử ca chuyển giờ | Lỗi chỉ xuất hiện một vài ngày trong năm | Kiểm thử gap, overlap, biên và ngày thường |
| Cho rằng quy tắc tương lai là bất biến | Lệch khi chính phủ đổi luật | Theo dõi cập nhật tzdb/JDK và chính sách lịch |

## 15. Bài tập và tình huống tự kiểm tra

**Tình huống A:** Bệnh viện tại New York có lịch hẹn **08/03/2026 02:30**. Hệ thống thấy getValidOffsets() rỗng. Có nên nhận lịch này như giờ bình thường?

**Đáp án:** Không. Giờ này không tồn tại ở khu vực đó. Cần từ chối hoặc dời theo chính sách có thông báo rõ. **ofStrict** sẽ bác bỏ tổ hợp giờ-offset-vùng không hợp lệ.

**Tình huống B:** Đặt lịch **01/11/2026 01:30** tại New York. Hai lựa chọn UTC là gì?

**Đáp án:** **05:30Z** với offset **-04:00**, hoặc **06:30Z** với offset **-05:00**. Hai Instant cách nhau một giờ và phải được phân biệt khi chốt lịch.

**Tình huống C:** Vì sao getOffset(Instant) đủ xác định offset, còn getOffset(LocalDateTime) đôi khi không đủ?

**Đáp án:** Instant đã là một mốc duy nhất trên timeline, nên ZoneRules chọn được offset của vùng tại mốc đó. LocalDateTime chỉ là các con số đồng hồ; khi gap có thể không tồn tại, khi overlap có thể được lặp hai lần.

**Tình huống D:** getTransition(local) trả null. Điều đó có nhất thiết nghĩa vùng đó không có DST suốt năm?

**Đáp án:** Không. Nó chỉ cho biết **local không nằm trong một chuyển đổi** tại vị trí đang hỏi. Vùng có thể đổi offset tại thời điểm khác trong năm. Dùng nextTransition/previousTransition hoặc tra các mốc cụ thể.

**Tình huống E:** Khi yêu cầu “mỗi ngày lúc 09:00 địa phương”, chỉ lưu một Instant ban đầu có đúng không?

**Đáp án:** Không. Cần lưu **giờ đồng hồ và ZoneId**, ngày áp dụng/quy tắc lặp rồi xác định từng lần theo vùng; nếu không, sau DST công việc có thể chạy lúc 08:00 hoặc 10:00 địa phương.

**Tình huống F:** Nếu getValidOffsets(local) trả 2, có thể bỏ qua offset thứ hai bằng cách gọi atZone mà không thông báo?

**Đáp án:** Chỉ phù hợp khi nghiệp vụ đã chủ đích chọn chính sách mặc định và không cần phân biệt hai lần. Với lịch hẹn, ghi nhận giao dịch hay trả lương, cần kiểm tra và giải thích lựa chọn.

## 16. Ghi nhớ

- **ZoneId** biểu diễn vùng; **ZoneOffset** biểu diễn độ lệch UTC tại một mốc hoặc một lựa chọn cụ thể.
- **getOffset(Instant)** trả offset ứng với mốc tuyệt đối; **getOffset(LocalDateTime)** có thể chỉ là offset “best effort”.
- **getValidOffsets(LocalDateTime)**: **1 bình thường**, **0 gap**, **2 overlap** (trường hợp thông dụng).
- **getTransition(LocalDateTime)** trả mô tả bước chuyển nếu local nằm trong vùng mơ hồ/không hợp lệ; **null** nếu bình thường.
- **getOffsetBefore/After**, **getInstant**, **getDateTimeBefore/After**, **getDuration**, **isGap/isOverlap** cho phép hiểu cụ thể việc đồng hồ đã dịch thế nào.
- **ZonedDateTime.ofStrict** xác thực nghiêm; **atZone/ofLocal** có chính sách giải quyết mặc định.
- **nextTransition** và **previousTransition** phục vụ phát hiện thời điểm thay đổi offset trước/sau một Instant.
- Các quy tắc có thể cập nhật, nên cần kiểm thử trên bộ tzdb phù hợp môi trường triển khai.

## Tài liệu tham khảo chính thức

- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): các phương thức xác định offset và transition.
- [Java SE 17 — ZoneOffsetTransition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html): thuộc tính một lần đổi offset.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): chuyển đổi giờ địa phương và cách xử lý gap/overlap.
- [Java SE 17 — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): mã vùng và truy xuất rules.
- [Java SE 17 — ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html): độ lệch với UTC.
- [Java SE 17 — java.time.zone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/package-summary.html): các khái niệm và kiểu dữ liệu zone rules.
