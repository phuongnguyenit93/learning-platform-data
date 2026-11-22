# Khoảng trống, khoảng trùng do đổi giờ mùa hè (DST gap và overlap) — Java 8

Ở những vùng áp dụng Daylight Saving Time (DST), đồng hồ địa phương có thể **nhảy tiến** hoặc **lùi lại** khi thay đổi độ lệch so với UTC. Hệ quả: một số giờ địa phương **không tồn tại** trong ngày chuyển giờ, và một số giờ **xuất hiện hai lần**. Nếu ứng dụng đặt lịch, thanh toán, chấm công hoặc gửi thông báo chỉ lưu `LocalDateTime` rồi tự suy ra một thời điểm, dữ liệu có thể bị sai dù code không ném lỗi.

Ví dụ theo quy tắc múi giờ của Berlin năm 2026:

- **Gap:** `2026-03-29T02:30` tại `Europe/Berlin` không xảy ra trên đồng hồ địa phương. Đồng hồ nhảy từ 02:00 sang 03:00.
- **Overlap:** `2026-10-25T02:30` tại Berlin xảy ra hai lần: một lần với offset `+02:00`, một lần với `+01:00`. Hai lần này cách nhau một giờ theo `Instant`.

Java 8 có bộ API hiện đại và vẫn đang được sử dụng: `java.time.LocalDateTime`, `ZoneId`, `ZoneRules`, `ZoneOffsetTransition`, `ZoneOffset`, `ZonedDateTime` và `Instant`. Bài học chỉ sử dụng những API hiện còn áp dụng, đúng giới hạn của module. Trọng tâm là **nhận diện**, **quyết định chính sách**, **chuyển đổi an toàn**, **kiểm thử** và **giữ ngữ nghĩa thời gian khi lưu trữ**.

## 1. Phân biệt LocalDateTime, ZoneOffset, ZoneId và Instant

| Thành phần | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| Ngày và giờ đồng hồ | `LocalDateTime` | Ngày giờ **không có múi giờ**, ví dụ 25/10/2026 02:30 |
| Offset | `ZoneOffset` | Độ lệch cụ thể với UTC như +02:00 |
| Danh tính vùng | `ZoneId` | Khu vực như Europe/Berlin, có quy tắc chuyển offset |
| Thời điểm thực | `Instant` | Một điểm duy nhất trên dòng thời gian UTC |
| Thời gian cục bộ đã resolve vùng | `ZonedDateTime` | LocalDateTime + ZoneId + offset hợp lệ của thời điểm đó |

**Một LocalDateTime đơn lẻ không phải một Instant.** Nó chưa cho biết giờ đang ở vùng nào, và ngay cả sau khi biết ZoneId vẫn có trường hợp không có hoặc có tới hai offset hợp lệ.

Ví dụ overlap:

```text
LocalDateTime = 2026-10-25T02:30
ZoneId       = Europe/Berlin

02:30 +02:00  -> 2026-10-25T00:30:00Z
02:30 +01:00  -> 2026-10-25T01:30:00Z

Cùng nhãn 02:30, hai Instant khác nhau đúng một giờ.
```

Không thể chỉ so chuỗi `"02:30"` để xác định hai giao dịch có trùng timestamp thật hay không.

## 2. Gap: khoảng trống khi đồng hồ nhảy tiến

Khi offset đổi từ +01:00 lên +02:00, đồng hồ có thể nhảy:

```text
01:59:59.999999999 +01:00
           ↓ nhảy tới
03:00:00.000000000 +02:00

Các giờ 02:00–02:59:59.999999999 không xuất hiện.
```

Với `LocalDateTime.of(2026,3,29,2,30)` ở Berlin, `LocalDateTime` **hợp lệ về cú pháp và lịch ISO**, nhưng khi kết hợp với `Europe/Berlin` thì **không có offset hợp lệ**. Đó là gap. Nó khác với ngày sai như 31/02, vốn bị Java từ chối ngay khi tạo LocalDate.

Các ứng dụng có thể cần chính sách khác nhau:

- **Từ chối (REJECT):** báo rằng giờ người dùng chọn không tồn tại, đề nghị chọn lại.
- **Dịch tiến (SHIFT_FORWARD):** dịch giờ theo độ dài gap, ví dụ 02:30 thành 03:30 ở Berlin.
- **Bỏ lần chạy (SKIP):** một scheduler lặp có thể bỏ lượt rơi trong gap.
- **Quy tắc nghiệp vụ riêng:** lịch làm, chấm công hoặc dịch vụ tài chính có thể có quy định khác.

Không có lựa chọn nào đúng cho mọi hệ thống. Quan trọng là **không để Java tự dịch giờ mà người dùng không biết** khi ứng dụng cam kết giữ giờ đã chọn.

## 3. Overlap: khoảng trùng khi đồng hồ lùi

Khi offset đổi từ +02:00 xuống +01:00, đồng hồ có thể lặp lại một đoạn:

```text
02:30 +02:00  -> 00:30Z  (lần sớm)
      ... đồng hồ quay lùi ...
02:30 +01:00  -> 01:30Z  (lần muộn)
```

Giờ địa phương như 02:30 là **mơ hồ** nếu chỉ biết LocalDateTime và ZoneId. Hai offset đều hợp lệ; mỗi offset cho một Instant khác nhau.

Chính sách có thể là:

- **REQUIRE_CHOICE:** yêu cầu người dùng chọn lần sớm hay muộn.
- **EARLIER:** chọn Instant trước.
- **LATER:** chọn Instant sau.
- Với lịch chạy lặp, **RUN_ONCE** hoặc **RUN_TWICE** phải được quy định rõ.

Ở Berlin, +02:00 cho Instant **sớm hơn** +01:00 khi local time giống nhau. Không suy từ giá trị số `+02:00` lớn hơn `+01:00` rằng nó xảy ra sau.

## 4. Phát hiện ba trạng thái bằng ZoneRules.getValidOffsets

Java 8 cho phép đọc chính xác quy tắc vùng:

```java
// Đoạn minh họa với import java.time.* và java.util.*.
ZoneId zone = ZoneId.of("Europe/Berlin");
LocalDateTime requested =
    LocalDateTime.of(2026, 10, 25, 2, 30);

List<ZoneOffset> valid =
    zone.getRules().getValidOffsets(requested);
```

| Số offset hợp lệ | Tình trạng | Cách hiểu |
| ---: | --- | --- |
| 0 | **Gap** | Không có Instant ứng với giờ đồng hồ đã chọn |
| 1 | **Normal** | LocalDateTime + ZoneId xác định một Instant |
| 2 | **Overlap** | Có hai offset; cần quyết định chọn lần nào |

Khi `getValidOffsets` trả hai phần tử, các offset có thứ tự từ lần xuất hiện sớm đến lần xuất hiện muộn trên timeline. Khi cần kiểm tra một offset client gửi, dùng `zone.getRules().isValidOffset(local, offset)` hoặc `ZonedDateTime.ofStrict(local,offset,zone)`.

Để lấy thông tin chuyển offset trong gap hoặc overlap:

```java
// Mã minh họa; có thể trả null nếu local không nằm trong transition.
ZoneOffsetTransition transition =
    zone.getRules().getTransition(requested);
```

Với transition khác null có thể kiểm `isGap()`, `isOverlap()`, `getOffsetBefore()`, `getOffsetAfter()`, `getDuration()`. Đừng gọi phương thức trên transition khi chưa xác nhận nó khác null.

**Không hardcode mọi DST chuyển đúng một giờ.** Độ dài và lịch chuyển có thể khác theo ZoneId, và một số khu vực không áp dụng DST.

## 5. Hành vi mặc định của atZone và giới hạn

`LocalDateTime.atZone(zone)` **không nhất thiết từ chối** gap hoặc overlap.

- **Gap:** có thể dịch local time **về phía trước đúng độ dài gap**. Ví dụ Berlin 02:30 ngày 29/03/2026 thành 03:30.
- **Overlap:** khi không có offset ưu tiên, nó chọn offset của lần xuất hiện **sớm hơn trên timeline**, ví dụ Berlin +02:00 ngày 25/10/2026.
- **Normal:** dùng offset duy nhất hợp lệ.

Các phương thức quan trọng khác:

| API Java 8 | Dùng để |
| --- | --- |
| `local.atZone(zone)` | Resolve theo chính sách mặc định, có thể điều chỉnh gap |
| `ZonedDateTime.ofStrict(local, offset, zone)` | **Chỉ chấp nhận** offset hợp lệ, nếu không ném `DateTimeException` |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Ưu tiên offset nếu hợp lệ, nhưng **không phải validation strict** |
| `zdt.withEarlierOffsetAtOverlap()` | Chọn offset cho lần xuất hiện sớm hơn |
| `zdt.withLaterOffsetAtOverlap()` | Chọn offset cho lần xuất hiện muộn hơn |
| `ZoneRules.getValidOffsets(local)` | Phân loại gap/normal/overlap |
| `ZoneRules.getTransition(local)` | Đọc chi tiết transition khi có |
| `ZoneRules.isValidOffset(local, offset)` | Xác thực kết hợp local + offset + region |

**Cảnh báo:** nếu sản phẩm yêu cầu “đặt hẹn đúng 02:30 hoặc báo lỗi”, chỉ gọi `atZone` là chưa đủ; nó có thể trả 03:30 mà không báo lỗi.

## 6. Chương trình 1: kiểm tra gap và overlap ở Berlin

Tệp **`GapOverlapBasicsDemo.java`** sau đây có thể biên dịch/chạy độc lập bằng Java 8.

```java
import java.time.*;
import java.time.zone.*;
import java.util.*;

public class GapOverlapBasicsDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneRules rules = berlin.getRules();

        LocalDateTime gap = LocalDateTime.of(2026, 3, 29, 2, 30);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        ZoneOffsetTransition gapTransition = rules.getTransition(gap);
        ZonedDateTime gapAdjusted = gap.atZone(berlin);

        check(gapOffsets.isEmpty(), "gap has no valid offset");
        check(gapTransition != null && gapTransition.isGap(),
              "gap transition");
        check(gapTransition.getDuration().equals(Duration.ofHours(1)),
              "one hour gap");
        check(gapAdjusted.toLocalTime().equals(LocalTime.of(3, 30)),
              "atZone moves forward by gap duration");

        boolean strictRejected = false;
        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.ofHours(1), berlin);
        } catch (DateTimeException ex) {
            strictRejected = true;
        }
        check(strictRejected, "strict rejects nonexisting wall time");

        LocalDateTime overlap = LocalDateTime.of(2026, 10, 25, 2, 30);
        List<ZoneOffset> overlapOffsets = rules.getValidOffsets(overlap);
        ZoneOffsetTransition overlapTransition =
            rules.getTransition(overlap);
        ZonedDateTime earlier = overlap.atZone(berlin);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        check(overlapOffsets.size() == 2, "two valid offsets");
        check(overlapTransition != null && overlapTransition.isOverlap(),
              "overlap transition");
        check(earlier.toLocalDateTime().equals(later.toLocalDateTime()),
              "same wall time");
        check(Duration.between(earlier.toInstant(), later.toInstant())
              .equals(Duration.ofHours(1)), "distinct instants");
        check(earlier.getOffset().equals(ZoneOffset.ofHours(2))
              && later.getOffset().equals(ZoneOffset.ofHours(1)),
              "chosen offsets");

        System.out.println("gapOffsets=" + gapOffsets);
        System.out.println("gapDuration=" + gapTransition.getDuration());
        System.out.println("gapAdjusted=" + gapAdjusted);
        System.out.println("strictRejected=" + strictRejected);
        System.out.println("overlapOffsets=" + overlapOffsets);
        System.out.println("earlier=" + earlier);
        System.out.println("later=" + later);
        System.out.println("instantDifference=" +
            Duration.between(earlier.toInstant(), later.toInstant()));
        System.out.println("PASS");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 GapOverlapBasicsDemo.java
java GapOverlapBasicsDemo
```

Nếu dùng JDK mới nhưng muốn kiểm tra chỉ dùng API Java 8:

```bash
javac --release 8 -encoding UTF-8 GapOverlapBasicsDemo.java
java GapOverlapBasicsDemo
```

**Stdout đã xác minh:**

```text
gapOffsets=[]
gapDuration=PT1H
gapAdjusted=2026-03-29T03:30+02:00[Europe/Berlin]
strictRejected=true
overlapOffsets=[+02:00, +01:00]
earlier=2026-10-25T02:30+02:00[Europe/Berlin]
later=2026-10-25T02:30+01:00[Europe/Berlin]
instantDifference=PT1H
PASS
```

**Kết quả quan trọng:** danh sách offset rỗng trong gap; có hai offset khi overlap; thời điểm sớm và muộn cách một giờ; `ofStrict` từ chối gap thay vì lặng lẽ sửa giờ. Những assertion đó kiểm hợp đồng thay vì dựa vào log.

## 7. Thiết kế policy tường minh cho ứng dụng

Một ứng dụng đặt lịch cần xác định trước **được phép chỉnh giờ người dùng nhập không** và **có bắt buộc chọn một trong hai lần 02:30 không**.

Bộ chính sách minh họa:

```text
GapPolicy:
  REJECT         = từ chối giờ không tồn tại
  SHIFT_FORWARD  = dịch về giờ hợp lệ theo độ dài gap

OverlapPolicy:
  REJECT         = yêu cầu lựa chọn khác/xác nhận
  EARLIER        = chọn Instant trước
  LATER          = chọn Instant sau
```

Quy trình:

1. Nhận `LocalDateTime` do người dùng chọn và `ZoneId` của địa điểm.
2. Lấy `ZoneRules.getValidOffsets(local)`.
3. Nếu có 1 offset, resolve bình thường bằng `ofStrict`.
4. Nếu 0 offset, áp GapPolicy (từ chối hoặc dịch).
5. Nếu 2 offset, áp OverlapPolicy (từ chối hoặc chọn rõ lần đầu/lần sau).
6. Lưu Instant đã resolve nếu đây là event có thời điểm xác định; khi cần giữ ý định giờ dân sự tương lai, lưu thêm LocalDateTime + ZoneId và policy.

Không sử dụng `ZoneId.systemDefault()` như timezone của client mà không có hợp đồng cho phép. Server triển khai ở nơi khác không có nghĩa lịch hẹn chuyển địa điểm.

## 8. Chương trình 2: resolver có chính sách

Tệp **`ExplicitDstPolicyDemo.java`** triển khai REJECT/SHIFT_FORWARD và REJECT/EARLIER/LATER.

```java
import java.time.*;
import java.time.zone.*;
import java.util.*;

public class ExplicitDstPolicyDemo {
    enum GapPolicy { REJECT, SHIFT_FORWARD }
    enum OverlapPolicy { REJECT, EARLIER, LATER }

    static ZonedDateTime resolve(LocalDateTime local, ZoneId zone,
                                 GapPolicy gapPolicy,
                                 OverlapPolicy overlapPolicy) {
        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
        if (valid.size() == 1) {
            return ZonedDateTime.ofStrict(local, valid.get(0), zone);
        }
        if (valid.isEmpty()) {
            if (gapPolicy == GapPolicy.REJECT) {
                throw new DateTimeException("nonexistent local time");
            }
            // Java 8 atZone shifts a gap forward by its duration.
            return local.atZone(zone);
        }
        if (overlapPolicy == OverlapPolicy.REJECT) {
            throw new DateTimeException("ambiguous local time");
        }
        ZoneOffset chosen = overlapPolicy == OverlapPolicy.EARLIER
            ? valid.get(0) : valid.get(1);
        return ZonedDateTime.ofStrict(local, chosen, zone);
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Berlin");
        LocalDateTime normal = LocalDateTime.of(2026, 2, 12, 9, 0);
        LocalDateTime gap = LocalDateTime.of(2026, 3, 29, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 10, 25, 2, 30);

        ZonedDateTime normalResult = resolve(
            normal, zone, GapPolicy.REJECT, OverlapPolicy.REJECT);

        boolean gapRejected = false;
        try {
            resolve(gap, zone, GapPolicy.REJECT, OverlapPolicy.EARLIER);
        } catch (DateTimeException ex) {
            gapRejected = true;
        }
        ZonedDateTime gapShifted = resolve(
            gap, zone, GapPolicy.SHIFT_FORWARD, OverlapPolicy.EARLIER);

        boolean overlapRejected = false;
        try {
            resolve(overlap, zone, GapPolicy.REJECT, OverlapPolicy.REJECT);
        } catch (DateTimeException ex) {
            overlapRejected = true;
        }
        ZonedDateTime earlier = resolve(
            overlap, zone, GapPolicy.REJECT, OverlapPolicy.EARLIER);
        ZonedDateTime later = resolve(
            overlap, zone, GapPolicy.REJECT, OverlapPolicy.LATER);

        check(normalResult.getOffset().equals(ZoneOffset.ofHours(1)),
              "winter normal");
        check(gapRejected && overlapRejected, "explicit rejection");
        check(gapShifted.toLocalTime().equals(LocalTime.of(3, 30)),
              "explicit shift");
        check(earlier.toLocalDateTime().equals(later.toLocalDateTime())
              && earlier.toInstant().isBefore(later.toInstant()),
              "choice changes moment");

        System.out.println("normal=" + normalResult);
        System.out.println("gapRejected=" + gapRejected);
        System.out.println("gapShifted=" + gapShifted);
        System.out.println("overlapRejected=" + overlapRejected);
        System.out.println("earlier=" + earlier);
        System.out.println("later=" + later);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ExplicitDstPolicyDemo.java
java ExplicitDstPolicyDemo
```

**Stdout đã xác minh:**

```text
normal=2026-02-12T09:00+01:00[Europe/Berlin]
gapRejected=true
gapShifted=2026-03-29T03:30+02:00[Europe/Berlin]
overlapRejected=true
earlier=2026-10-25T02:30+02:00[Europe/Berlin]
later=2026-10-25T02:30+01:00[Europe/Berlin]
PASS
```

Ở môi trường thật, REJECT có thể được chuyển thành lỗi validation rõ ràng cho UI/API thay vì để `DateTimeException` truyền thẳng tới client. Ví dụ dùng exception để minh họa nguyên tắc từ chối dữ liệu mơ hồ.

Lợi ích của resolver này là mọi chính sách nằm trong **một chỗ được đặt tên**; không còn vô tình chọn default của `atZone` ở một màn hình và lựa chọn khác ở màn hình khác.

## 9. Một ngày lịch không luôn là 24 giờ

Các yêu cầu “ngày mai” và “sau 24 giờ” có nghĩa khác nhau:

- **`ZonedDateTime.plusDays(1)`:** thêm một ngày lịch, cố giữ giờ đồng hồ local.
- **`plus(Duration.ofHours(24))`:** thêm đúng 24 giờ thời gian thực.
- **`Instant.plus(Duration.ofHours(24))`:** thêm 24 giờ từ một thời điểm tuyệt đối.
- **`Period.ofDays(1)`:** lượng ngày lịch, không tương đương mọi lúc với 86.400 giây tại một vùng có DST.

Tại New York vào mùa xuân 2026:

```text
2026-03-07T12:00-05:00 + một ngày lịch
    = 2026-03-08T12:00-04:00
      → chỉ 23 giờ thời gian thực.

2026-03-07T12:00-05:00 + đúng 24 giờ
    = 2026-03-08T13:00-04:00.
```

Ngày chuyển giờ mùa thu có thể kéo dài 25 giờ. Đây là tác động trực tiếp của gap và overlap, không phải lỗi của phép cộng.

**Quy tắc chọn kiểu:** TTL, timeout, thời lượng xử lý thường dùng `Duration`; lịch chạy “cùng giờ địa phương ngày hôm sau” thường dùng phép lịch với `ZoneId` và DST policy. Không thay một yêu cầu bằng yêu cầu kia vì chúng có cùng chữ “ngày”.

## 10. Chương trình 3: so thời gian lịch và thời gian thực

Tệp **`CalendarVsElapsedDstDemo.java`**:

```java
import java.time.*;

public class CalendarVsElapsedDstDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime springStart =
            ZonedDateTime.of(2026, 3, 7, 12, 0, 0, 0, ny);
        ZonedDateTime calendarNext = springStart.plusDays(1);
        ZonedDateTime elapsedNext =
            springStart.plus(Duration.ofHours(24));

        LocalDate springDay = LocalDate.of(2026, 3, 8);
        Duration springDayLength = Duration.between(
            springDay.atStartOfDay(ny).toInstant(),
            springDay.plusDays(1).atStartOfDay(ny).toInstant());

        LocalDate fallDay = LocalDate.of(2026, 11, 1);
        Duration fallDayLength = Duration.between(
            fallDay.atStartOfDay(ny).toInstant(),
            fallDay.plusDays(1).atStartOfDay(ny).toInstant());

        check(calendarNext.toLocalTime().equals(LocalTime.NOON),
              "plus one calendar day keeps noon");
        check(elapsedNext.toLocalTime().equals(LocalTime.of(13, 0)),
              "24 hours elapsed becomes 13:00");
        check(springDayLength.equals(Duration.ofHours(23)),
              "spring day");
        check(fallDayLength.equals(Duration.ofHours(25)),
              "fall day");

        System.out.println("springStart=" + springStart);
        System.out.println("calendarNext=" + calendarNext);
        System.out.println("elapsedNext=" + elapsedNext);
        System.out.println("springDayLength=" + springDayLength);
        System.out.println("fallDayLength=" + fallDayLength);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CalendarVsElapsedDstDemo.java
java CalendarVsElapsedDstDemo
```

**Stdout đã xác minh:**

```text
springStart=2026-03-07T12:00-05:00[America/New_York]
calendarNext=2026-03-08T12:00-04:00[America/New_York]
elapsedNext=2026-03-08T13:00-04:00[America/New_York]
springDayLength=PT23H
fallDayLength=PT25H
PASS
```

Để tính thời lượng thực của ngày địa phương, ví dụ tạo hai mốc bằng `LocalDate.atStartOfDay(zone)`, chuyển thành Instant và dùng `Duration.between`. Phép tính này không giả định ngày phải có 24 giờ.

Lưu ý `atStartOfDay(zone)` nghĩa là **đầu ngày hợp lệ theo quy tắc vùng**, không bắt buộc luôn là 00:00 với một offset cố định; ở một số vùng transition có thể xảy ra ngay tại ranh giới ngày.

## 11. Lưu dữ liệu trong overlap: phải giữ đủ thông tin để phân biệt

Hai giao dịch được tạo trong overlap Berlin có thể cùng local timestamp:

```text
2026-10-25T02:30+02:00[Europe/Berlin]
2026-10-25T02:30+01:00[Europe/Berlin]
```

Nếu lưu **chỉ LocalDateTime**, cả hai hiển thị 02:30, không phân biệt được chúng xảy ra trước/sau. Đối với event đã xảy ra:

- Lưu **`Instant`** hoặc timestamp có ngữ nghĩa Instant rõ trong hệ thống.
- Giữ **ZoneId/offset gốc** nếu cần báo cáo, đối soát hoặc hiển thị theo nơi xảy ra.
- Nếu API truyền offset và vùng, kiểm rằng offset **hợp lệ với ZoneId ở local time đó**.
- Đừng tin một cột database `TIMESTAMP WITH TIME ZONE` chắc chắn giữ tên vùng IANA; hành vi của các DB/driver có thể khác nhau.

Nếu một lịch hẹn **tương lai** cam kết giờ đồng hồ địa phương, có thể cần lưu `LocalDateTime + ZoneId + policy` cùng Instant đã resolve. Khi dữ liệu timezone được cập nhật, phải quyết định giữ **Instant cố định** hay giữ **giờ địa phương đã cam kết** rồi tính lại Instant.

## 12. Chương trình 4: hai Instant khác nhau, cùng local time

Tệp **`OverlapInstantStorageDemo.java`** kiểm tra hai offset và round-trip của `ISO_ZONED_DATE_TIME`.

```java
import java.time.*;
import java.time.format.*;

public class OverlapInstantStorageDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
        ZonedDateTime first =
            ZonedDateTime.ofStrict(local, ZoneOffset.ofHours(2), berlin);
        ZonedDateTime second =
            ZonedDateTime.ofStrict(local, ZoneOffset.ofHours(1), berlin);

        String firstSerialized =
            first.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
        ZonedDateTime roundTrip =
            ZonedDateTime.parse(firstSerialized,
                DateTimeFormatter.ISO_ZONED_DATE_TIME);

        boolean sameWall = first.toLocalDateTime()
            .equals(second.toLocalDateTime());
        boolean differentInstants =
            !first.toInstant().equals(second.toInstant());
        boolean zoneRoundTrip = first.equals(roundTrip);
        boolean invalidBerlinOffset =
            berlin.getRules().isValidOffset(
                LocalDateTime.of(2026, 3, 29, 2, 30),
                ZoneOffset.ofHours(1));

        check(sameWall && differentInstants, "overlap double time");
        check(zoneRoundTrip, "keep region and offset");
        check(!invalidBerlinOffset, "gap not allowed");

        System.out.println("sameWall=" + sameWall);
        System.out.println("firstInstant=" + first.toInstant());
        System.out.println("secondInstant=" + second.toInstant());
        System.out.println("differentInstants=" + differentInstants);
        System.out.println("zoneRoundTrip=" + zoneRoundTrip);
        System.out.println("gapOffsetValid=" + invalidBerlinOffset);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 OverlapInstantStorageDemo.java
java OverlapInstantStorageDemo
```

**Stdout đã xác minh:**

```text
sameWall=true
firstInstant=2026-10-25T00:30:00Z
secondInstant=2026-10-25T01:30:00Z
differentInstants=true
zoneRoundTrip=true
gapOffsetValid=false
PASS
```

Hai `ZonedDateTime` có cùng LocalDateTime nhưng không cùng Instant. Đặc biệt, `OffsetDateTime` có offset +01:00 không tự bảo đảm rằng local time của nó hợp lệ **trong vùng Berlin**: phải kiểm quy tắc vùng nếu nghiệp vụ yêu cầu cả region ID.

Mã sử dụng Java formatter để kiểm round-trip trong cùng môi trường Java; nếu API giao tiếp ngôn ngữ khác, phải xác định client có hỗ trợ cú pháp vùng dạng `[Europe/Berlin]` hay không. Không chỉ gửi một chuỗi ngày giờ không offset nếu cần phân biệt overlap.

## 13. DST không phải lúc nào cũng chuyển đúng một giờ

Một số vùng có chuyển đổi offset với độ dài **30 phút**. Ví dụ `Australia/Lord_Howe` theo các quy tắc năm 2026 trong JDK được thử nghiệm:

- `2026-10-04T02:15` nằm trong gap 30 phút.
- Khi tự giải theo quy tắc mặc định, 02:15 trở thành 02:45.
- `2026-04-05T01:45` nằm trong overlap.
- Offset hợp lệ là +11:00 và +10:30.
- Hai Instant của cùng 01:45 cách nhau 30 phút.

Điều này bác bỏ cách xử lý hardcode `plusHours(1)` cho mọi gap hoặc assume mọi overlap có hai Instant cách nhau đúng 3.600 giây. Hãy lấy độ dài thực từ `ZoneOffsetTransition.getDuration()` hoặc dựa trên API có quy tắc vùng.

## 14. Chương trình 5: gap/overlap 30 phút ở Lord Howe

Tệp **`NonHourDstShiftDemo.java`**:

```java
import java.time.*;
import java.time.zone.*;
import java.util.*;

public class NonHourDstShiftDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId lordHowe = ZoneId.of("Australia/Lord_Howe");
        ZoneRules rules = lordHowe.getRules();

        LocalDateTime gap = LocalDateTime.of(2026, 10, 4, 2, 15);
        LocalDateTime overlap = LocalDateTime.of(2026, 4, 5, 1, 45);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        List<ZoneOffset> overlapOffsets = rules.getValidOffsets(overlap);
        ZoneOffsetTransition gapTransition = rules.getTransition(gap);
        ZoneOffsetTransition overlapTransition =
            rules.getTransition(overlap);

        check(gapOffsets.isEmpty() && gapTransition.isGap(),
              "half-hour spring gap");
        check(gapTransition.getDuration().equals(Duration.ofMinutes(30)),
              "gap duration 30 minutes");
        check(overlapOffsets.size() == 2
              && overlapTransition.isOverlap(),
              "half-hour fall overlap");
        check(overlapTransition.getDuration().equals(
            Duration.ofMinutes(-30)), "overlap -30 minutes");

        ZonedDateTime adjustedGap = gap.atZone(lordHowe);
        ZonedDateTime earlier = overlap.atZone(lordHowe);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        Duration delta = Duration.between(
            earlier.toInstant(), later.toInstant());

        check(adjustedGap.toLocalTime().equals(LocalTime.of(2, 45)),
              "gap move forward half an hour");
        check(delta.equals(Duration.ofMinutes(30)),
              "overlap instants half hour apart");

        System.out.println("gapOffsets=" + gapOffsets);
        System.out.println("gapDuration=" + gapTransition.getDuration());
        System.out.println("gapAdjusted=" + adjustedGap);
        System.out.println("overlapOffsets=" + overlapOffsets);
        System.out.println("overlapDuration=" +
            overlapTransition.getDuration());
        System.out.println("earlier=" + earlier);
        System.out.println("later=" + later);
        System.out.println("instantDifference=" + delta);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 NonHourDstShiftDemo.java
java NonHourDstShiftDemo
```

**Stdout đã xác minh:**

```text
gapOffsets=[]
gapDuration=PT30M
gapAdjusted=2026-10-04T02:45+11:00[Australia/Lord_Howe]
overlapOffsets=[+11:00, +10:30]
overlapDuration=PT-30M
earlier=2026-04-05T01:45+11:00[Australia/Lord_Howe]
later=2026-04-05T01:45+10:30[Australia/Lord_Howe]
instantDifference=PT30M
PASS
```

`overlapDuration=PT-30M` mang dấu âm vì offset đã **lùi**, còn `instantDifference=PT30M` là khoảng dương giữa hai lần xuất hiện. Không nhầm duration của transition với thứ tự hai Instant.

## 15. Lịch chạy lặp vào thời gian chuyển DST

Một scheduler “chạy **02:30 hằng ngày ở Berlin**” không thể chỉ cộng một ngày thời gian thực cố định:

1. Ngày bình thường: 02:30 có một Instant.
2. Ngày gap: 02:30 **không có** Instant; phải skip, shift hoặc báo lỗi.
3. Ngày overlap: 02:30 có **hai** Instant; phải chọn một hay cả hai.
4. Nếu luật vùng thay đổi, lịch chạy trong tương lai có thể cần được resolve lại theo ý nghĩa nghiệp vụ.

Mô hình scheduler hợp lý thường gồm **LocalTime**, **ZoneId**, quy tắc ngày chạy, chính sách gap/overlap, và cơ chế lưu lịch sử thực thi. Nếu yêu cầu “chạy một lần mỗi ngày địa phương”, khóa chống trùng không nên chỉ dựa vào chuỗi “02:30”; cần quy tắc ngày lịch và mã job. Nếu yêu cầu **hai lần trong overlap**, phải phân biệt hai Instant/offset.

**Không thay lịch chạy theo giờ dân sự bằng việc gọi Thread.sleep 24 giờ hoặc liên tục cộng Duration 24 giờ** nếu muốn giữ đúng giờ đồng hồ địa phương qua DST.

## 16. Giữ Instant hay giữ giờ đồng hồ cho lịch tương lai?

Giả sử người dùng đặt một cuộc họp trong tương lai với local time và zone. Có hai loại cam kết:

- **Instant cố định:** buổi họp diễn ra tại một thời điểm tuyệt đối đã chốt. Dù timezone rules thay đổi, Instant giữ nguyên; giờ hiển thị ở địa phương có thể thay đổi.
- **Wall time cố định:** buổi họp luôn vào đúng giờ đồng hồ địa phương theo khu vực. Nếu luật chuyển giờ thay đổi, ứng dụng có thể phải tính lại Instant từ LocalDateTime + ZoneId.

Không tự coi hai cam kết này là một. Nếu ứng dụng giữ cả LocalDateTime, ZoneId, offset đã xác nhận và Instant đã resolve, phải xác định **trường nào là nguồn sự thật** khi timezone database được cập nhật.

Các quy tắc IANA timezone trong JDK có thể được cập nhật theo luật địa phương. Unit test dùng Berlin/New York/Lord Howe ở ngày cụ thể để chứng minh cơ chế, nhưng triển khai lịch xa trong tương lai cần chính sách quản lý thay đổi tzdb, không giả định luật giờ mùa hè bất biến.

## 17. API đặt lịch phải nhận đủ dữ liệu

Một request chỉ có:

```json
{"localStart": "2026-10-25T02:30"}
```

**không đủ** để xác định Instant của lịch hẹn khi chưa biết ZoneId và offset được chọn. Một hợp đồng cụ thể hơn:

```json
{
  "localStart": "2026-10-25T02:30",
  "zoneId": "Europe/Berlin",
  "gapPolicy": "REJECT",
  "overlapChoice": "LATER"
}
```

Sau khi người dùng xác nhận, response có thể gửi:

```json
{
  "localStart": "2026-10-25T02:30",
  "zoneId": "Europe/Berlin",
  "selectedOffset": "+01:00",
  "instant": "2026-10-25T01:30:00Z"
}
```

Đây chỉ là schema minh họa, không phải JSON standard bắt buộc. API thực tế cần kiểm:

- ZoneId có tồn tại và được phép cho địa điểm hay không.
- Offset có hợp lệ với giờ local và ZoneId hay không.
- Nếu gap, user phải chọn lại hay cho phép dịch và nhận thông báo.
- Nếu overlap, user chọn EARLIER/LATER hay hệ thống có policy đã được công bố.
- Lưu Instant/ZoneId/giờ local nào để phục vụ hiển thị, truy vết và lịch tương lai.
- Không tự dùng múi giờ máy server làm ZoneId của một yêu cầu do người dùng gửi.

## 18. Lưu trữ và tính khoảng thời gian qua DST

Đối với log/giao dịch đã xảy ra, **`Instant`** là lựa chọn tốt để lưu sự kiện trong timeline; giữ zone/offset để hiển thị hoặc kiểm toán khi cần.

Để đo elapsed time giữa hai thời điểm đã resolve:

```java
// start và end là ZonedDateTime đã được resolve.
Duration elapsed = Duration.between(
    start.toInstant(), end.toInstant());
```

Không dùng `Duration.between(localStart, localEnd)` để khẳng định elapsed hours của một ca qua DST khi thiếu ZoneId. Hai LocalDateTime trong overlap có thể bằng nhau nhưng hai Instant cách nhau 30 hoặc 60 phút.

Để lọc mọi event thuộc một ngày địa phương, dùng khoảng **nửa mở**:

```java
// day là LocalDate, zone là ZoneId của chi nhánh.
Instant start = day.atStartOfDay(zone).toInstant();
Instant endExclusive =
    day.plusDays(1).atStartOfDay(zone).toInstant();
// Chọn các Instant thuộc [start, endExclusive).
```

Cách này không giả định ngày 24 giờ hoặc phải kết thúc ở 23:59:59.999. Ở miền LocalDate.MAX, cần xử lý riêng vì không thể cộng thêm một ngày.

## 19. Ma trận kiểm thử thiết yếu

| Case | Điều kiện | Kết quả cần xác minh |
| --- | --- | --- |
| Normal | Berlin 12/02/2026 09:00 | Có một offset |
| Gap Berlin | 29/03/2026 02:30 | Không có offset |
| Gap + REJECT | Không cho phép dịch | Validation error/exception rõ |
| Gap + SHIFT_FORWARD | Cho phép dịch | 03:30 ở Berlin theo quy tắc thử nghiệm |
| Overlap Berlin | 25/10/2026 02:30 | Hai offset |
| Overlap + REJECT | Cần chọn rõ | Không tự chốt Instant |
| Overlap + EARLIER | Chọn lần trước | 00:30Z |
| Overlap + LATER | Chọn lần sau | 01:30Z |
| Same wall time | Hai ZonedDateTime overlap | LocalDateTime bằng, Instant khác |
| ofStrict với gap | Offset +01:00 | Ném DateTimeException |
| Lord Howe gap | 04/10/2026 02:15 | Gap 30 phút |
| Lord Howe overlap | 05/04/2026 01:45 | Hai offset, cách 30 phút |
| Ngày DST mùa xuân | New York 08/03/2026 | 23 giờ thực |
| Ngày DST mùa thu | New York 01/11/2026 | 25 giờ thực |
| Cộng ngày lịch | plusDays(1) | Giữ giờ local theo quy tắc |
| Cộng giờ thực | plus(Duration.ofHours(24)) | Tăng đúng 24 giờ |
| API thiếu zone | Chỉ localDateTime | Không thể resolve chính xác |
| API offset không hợp vùng | Client gửi offset không hợp lệ | isValidOffset=false hoặc ofStrict từ chối |
| DB round-trip | Hai event overlap | Giữ sự khác nhau của Instant |
| Scheduler gap | 02:30 hằng ngày | Đúng policy skip/shift |
| Scheduler overlap | 02:30 hằng ngày | Đúng policy run once/twice |
| Update tzdb | Quy tắc vùng thay đổi | Đúng cam kết giữ wall time/Instant |

**Không chỉ test trường hợp parse một LocalDateTime thất bại.** 02:30 nằm trong gap vẫn là một LocalDateTime hợp lệ; lỗi chỉ phát sinh khi kết hợp nó với ZoneId và kiểm tra quy tắc vùng.

## 20. Các lỗi phổ biến

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Dùng LocalDateTime như Instant | Không có zone/offset | Resolve, lưu Instant khi thích hợp |
| Gọi atZone và coi như validation strict | Gap có thể bị dịch | getValidOffsets/ofStrict |
| Coi overlap chỉ có một lần 02:30 | Hai Instant hợp lệ | Chọn offset rõ |
| Lưu giờ local đơn lẻ cho log | Mất thứ tự sự kiện | Instant và ngữ cảnh vùng |
| Dùng ZoneOffset cố định cho lịch vùng có DST | Không có quy tắc region | ZoneId IANA |
| Dùng systemDefault cho dữ liệu client | Vùng server có thể khác | ZoneId từ hợp đồng |
| Hardcode dịch DST một giờ | Có vùng dịch 30 phút | ZoneOffsetTransition |
| Cộng 24 giờ để giữ giờ local hàng ngày | Qua DST sẽ lệch | Phép lịch + policy |
| Lịch lặp không có gap/overlap policy | Mất lượt hoặc chạy trùng | Định nghĩa skip/shift/once/twice |
| So LocalDateTime để tính thời lượng thực | Thiếu offset trong gap/overlap | Duration giữa Instants |
| Nghĩ DB luôn lưu region zone | Có thể chỉ giữ UTC/offset | Kiểm mapping và lưu ZoneId riêng |
| Tin offset bất kỳ client gửi là hợp lệ | Không khớp ZoneRules | isValidOffset/ofStrict |
| Xem tzdb không bao giờ thay đổi | Luật vùng có thể cập nhật | Kiểm phiên bản và policy |
| Chỉ test ngày bình thường | Bỏ sót trạng thái 0/2 offset | Test gap, overlap, normal |
| Nghĩ DST có ở mọi ZoneId | Nhiều vùng không chuyển giờ | Dùng ZoneRules cụ thể |

## 21. Bài tập áp dụng

**Bài 1 — lịch bị gap:** user chọn 02:30 ngày 29/03/2026 Berlin, chính sách không được dịch.  
**Đáp án:** kiểm `getValidOffsets`, thấy danh sách rỗng rồi từ chối, đề nghị giờ hợp lệ.

**Bài 2 — chọn lần thứ hai:** user chọn 02:30 ngày 25/10/2026 Berlin và xác nhận lần muộn.  
**Đáp án:** offset +01:00, Instant `2026-10-25T01:30:00Z`.

**Bài 3 — hai giao dịch cùng 02:30:** một giao dịch offset +02:00, một giao dịch +01:00. Có phải cùng timestamp không?  
**Đáp án:** không. Hai Instant cách nhau một giờ. Không gộp event chỉ vì local time trùng.

**Bài 4 — “09:00 mỗi ngày ở New York”:** có nên cộng Duration 24 giờ để tìm lần kế?  
**Đáp án:** không nếu cần giữ 09:00 local. Tính ngày lịch tiếp theo trong ZoneId và resolve theo policy.

**Bài 5 — gap 30 phút:** 02:15 ở Lord Howe trong ngày chuyển offset tiến. Có nên luôn cộng một giờ?  
**Đáp án:** không. Transition chỉ 30 phút; nếu được phép dịch, áp độ dài gap thực.

**Bài 6 — tính giờ làm:** ca làm qua DST, hệ thống tính lương theo thời lượng thực. Dùng gì?  
**Đáp án:** resolve cả hai đầu thành Instant rồi tính `Duration.between`, không chỉ trừ các giờ đồng hồ.

**Bài 7 — chọn dữ liệu cần lưu:** một lịch hẹn tương lai phải luôn ở 09:00 theo Berlin ngay cả khi quy tắc timezone đổi.  
**Đáp án:** bảo toàn LocalDateTime, ZoneId và policy; cân nhắc re-resolve Instant khi quy tắc thay đổi.

**Bài 8 — offset do client gửi:** client đưa LocalDateTime 02:30 ngày 29/03/2026 Berlin với offset +01:00. Có dùng ngay không?  
**Đáp án:** không. Kiểm `isValidOffset` hoặc `ofStrict`; offset đó không hợp lệ ở gap đã nêu.

## 22. Câu hỏi tự kiểm tra

**1. getValidOffsets trả bao nhiêu phần tử trong gap, normal, overlap?**  
Lần lượt 0, 1 và 2.

**2. Tại sao LocalDateTime 02:30 vẫn tạo được trong một gap?**  
Vì LocalDateTime không mang quy tắc timezone. Nó chỉ không hợp lệ khi gắn vào vùng/ngày cụ thể.

**3. atZone làm gì trong gap?**  
Nó có thể dịch thời gian đồng hồ tiến bằng độ dài gap, theo quy tắc API.

**4. atZone chọn offset nào trong overlap khi không có lựa chọn khác?**  
Offset cho lần xuất hiện sớm hơn theo timeline.

**5. ofStrict khác atZone như thế nào?**  
ofStrict chỉ chấp nhận bộ ba local, offset, zone hợp lệ; nó không âm thầm dịch giờ.

**6. DST có bắt buộc chuyển đúng 60 phút không?**  
Không. Có ví dụ 30 phút ở Lord Howe.

**7. plusDays(1) luôn bằng 24 giờ thực sao?**  
Không; ngày DST mùa xuân/mùa thu có thể dài 23/25 giờ.

**8. Khi cần so hai event đã xảy ra, dùng gì?**  
Instant hoặc timestamp được quy đổi thành Instant hợp lệ.

**9. Lịch “02:30 mỗi ngày” luôn chạy một lần sao?**  
Không; ngày gap có thể không có 02:30, ngày overlap có thể có hai lần.

**10. Có nên xem timezone rule không đổi mãi trong tương lai không?**  
Không. Cần nhận thức dữ liệu tzdb có thể đổi và quy tắc sản phẩm phải rõ.

## Tài liệu Java SE 8 chính thức

- [java.time package](https://docs.oracle.com/javase/8/docs/api/java/time/package-summary.html) — mô hình thời gian được hỗ trợ.
- [ZoneId](https://docs.oracle.com/javase/8/docs/api/java/time/ZoneId.html) — danh tính region và quy tắc vùng.
- [ZoneRules](https://docs.oracle.com/javase/8/docs/api/java/time/zone/ZoneRules.html) — `getValidOffsets`, `getTransition`, `isValidOffset`.
- [ZoneOffsetTransition](https://docs.oracle.com/javase/8/docs/api/java/time/zone/ZoneOffsetTransition.html) — gap, overlap, duration và offset trước/sau.
- [LocalDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDateTime.html) — thời gian local và `atZone`.
- [ZonedDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/ZonedDateTime.html) — `ofStrict`, `ofLocal`, chọn offset overlap.
- [ZoneOffset](https://docs.oracle.com/javase/8/docs/api/java/time/ZoneOffset.html) — độ lệch UTC.
- [Instant](https://docs.oracle.com/javase/8/docs/api/java/time/Instant.html) — thời điểm trên dòng thời gian.
- [Duration](https://docs.oracle.com/javase/8/docs/api/java/time/Duration.html) và [Period](https://docs.oracle.com/javase/8/docs/api/java/time/Period.html) — thời lượng thực và lượng lịch.

**Ghi nhớ:** một `LocalDateTime` gắn với một `ZoneId` có thể tương ứng **không có, một hoặc hai Instant**. Gap cần quyết định từ chối/dịch/bỏ; overlap cần quyết định lần sớm/muộn/chạy một hay hai lần. Dùng `ZoneRules` để phát hiện, `ofStrict` để xác nhận, `Instant` để so và lưu sự kiện đã xảy ra, và phân biệt một ngày lịch với đúng 24 giờ.