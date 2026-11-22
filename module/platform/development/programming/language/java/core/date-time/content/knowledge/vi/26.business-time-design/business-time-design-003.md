# Lịch lặp theo giờ địa phương cần giữ múi giờ và chính sách DST

## 1. “Mỗi ngày lúc 09:00” là một quy tắc lịch

Một lịch lặp như “mỗi ngày lúc 09:00 tại Berlin” không chỉ là một `Instant` đầu tiên rồi cộng một khoảng cố định mãi mãi. Nó có ba thành phần tối thiểu:

- Quy tắc chọn ngày, chẳng hạn mọi ngày hoặc mỗi thứ Hai.
- Giờ danh nghĩa theo đồng hồ địa phương, chẳng hạn `09:00`.
- Vùng thời gian có quy tắc, chẳng hạn `Europe/Berlin`.

**Giờ danh nghĩa** là giờ người dùng yêu cầu trong quy tắc. **Thời điểm thực thi** là `Instant` được xác định cho một ngày cụ thể sau khi áp dụng quy tắc vùng và chính sách xử lý trường hợp đặc biệt.

Khi vùng có đổi giờ mùa hè (daylight saving time, DST), cùng một giờ địa phương có thể:

1. Tương ứng đúng một thời điểm.
2. Không tồn tại vì đồng hồ nhảy về phía trước.
3. Xuất hiện hai lần vì đồng hồ lùi lại.

Vì vậy, lịch còn cần **chính sách DST** để quyết định phải làm gì ở hai trường hợp cuối. Chỉ giữ giờ và tên vùng nhưng để hành vi không được diễn đạt rõ vẫn có thể tạo kết quả khác kỳ vọng nghiệp vụ.

## 2. Phân biệt lịch theo đồng hồ với khoảng thời gian đã trôi qua

| Hợp đồng | Dữ liệu cốt lõi | Điều được giữ |
| --- | --- | --- |
| Mỗi ngày lúc 09:00 theo vùng | Quy tắc ngày + `LocalTime` + `ZoneId` | Giờ danh nghĩa trên lịch địa phương |
| Cứ sau đúng 24 giờ đã trôi qua | Mốc ban đầu + `Duration` | Khoảng cách trên dòng thời gian |
| Một lần tại thời điểm xác định | `Instant` | Một mốc tuyệt đối |

Cả ba đều có ứng dụng phù hợp. Điều cần thiết là chọn đúng hợp đồng.

Ví dụ tại `Europe/Berlin` khi chuyển giờ tháng 03/2024, từ 09:00 ngày trước:

- Cộng đúng 24 giờ đã trôi qua cho 10:00 ngày sau theo đồng hồ địa phương.
- Chọn ngày tiếp theo rồi giữ 09:00 cho 09:00 ngày sau; khoảng cách trên dòng thời gian khi đó chỉ là 23 giờ.

Vì thế, `previousInstant.plus(Duration.ofDays(1))` biểu đạt một khoảng 24 giờ, không đủ để hiện thực lời hứa “cùng giờ địa phương mỗi ngày”.

`ZonedDateTime.plusDays(1)` dùng phép tính theo ngày lịch, nhưng vẫn có quy tắc tự giải quyết gap/overlap. Với một bộ lịch có yêu cầu rõ, nên giữ ngày và giờ danh nghĩa rồi phân giải từng lượt thay vì để giờ đã được dời của lượt trước trở thành quy tắc mới.

## 3. ZoneId phải được giữ cùng quy tắc lặp

`ZoneId` như `Europe/Berlin` cho phép tra quy tắc offset theo ngày giờ. `ZoneOffset` như `+01:00` chỉ là độ lệch cố định.

Nếu lịch được tạo vào mùa đông rồi chỉ lưu `+01:00`, hệ thống đã bỏ mất thông tin cần để biết cùng vùng có thể dùng offset khác ở ngày tương lai.

| Dữ liệu lưu | Có đủ giữ ý định “09:00 tại Berlin mỗi ngày” không? |
| --- | --- |
| Một `Instant` đầu tiên | Chưa đủ để tái tạo quy tắc giờ địa phương |
| `LocalTime 09:00` | Thiếu vùng và quy tắc ngày |
| `LocalTime 09:00 + offset +01:00` | Chỉ mô tả giờ theo độ lệch cố định |
| Quy tắc ngày + `LocalTime 09:00 + ZoneId Europe/Berlin + chính sách` | Biểu đạt được ý định lịch địa phương |

Không dùng `ZoneId.systemDefault()` nếu lịch thuộc về một vùng đã được người dùng hoặc đơn vị lựa chọn. Máy chủ triển khai ở vùng khác không được phép tự đổi ý nghĩa lịch.

Tương tự, `Locale` chỉ phục vụ ngôn ngữ/định dạng và một số quy ước địa phương; nó không thay thế `ZoneId`. Người dùng đọc giao diện tiếng Việt vẫn có thể đặt lịch tại Berlin.

## 4. Dùng ZoneRules để nhận biết ba trường hợp

Theo [ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html), có thể lấy danh sách offset hợp lệ cho một `LocalDateTime`:

```java
LocalDateTime requested = nominalDate.atTime(nominalTime);
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(requested);
```

Với các chuyển đổi thông thường:

| Số offset | Trạng thái | Hệ quả |
| --- | --- | --- |
| `1` | Bình thường | Có một `Instant` phù hợp |
| `0` | Khoảng trống, gọi là gap | Giờ được yêu cầu không tồn tại |
| `2` | Khoảng lặp, gọi là overlap | Có hai `Instant` cùng mang giờ địa phương đó |

Ví dụ dưới dùng dữ liệu quy tắc vùng của môi trường Java đã kiểm chứng cho Berlin năm 2024:

- Ngày 31/03, giờ địa phương nhảy từ 02:00 lên 03:00. `02:30` không tồn tại.
- Ngày 27/10, đoạn giờ từ 02:00 đến trước 03:00 xuất hiện hai lần. `02:30` có thể đi với `+02:00` hoặc `+01:00`.

Không dùng riêng `getOffset(LocalDateTime)` để kết luận giờ có tồn tại hoặc có duy nhất hay không: phương thức đó có cách chọn offset thích hợp trong trường hợp không duy nhất. Danh sách `getValidOffsets` giúp đưa quyết định nghiệp vụ ra rõ ràng.

Trong mã ví dụ, trạng thái số offset ngoài `0/1/2` bị từ chối rõ. Không âm thầm chọn một offset khi hiện thực gặp một cấu hình ngoài phạm vi đã thiết kế.

## 5. Chính sách khi giờ không tồn tại

[ZoneOffsetTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html) cho biết độ dài thay đổi, offset trước/sau và ranh giới của khoảng chuyển đổi. Từ đó có thể hiện thực những chính sách riêng:

| Chính sách gap | Với yêu cầu 02:30 ngày 31/03/2024 tại Berlin |
| --- | --- |
| Bỏ lượt, `SKIP` | Không sinh lần thực thi cho ngày danh nghĩa đó |
| Dời theo độ dài gap, `SHIFT_BY_GAP` | Cộng một giờ của gap, thành 03:30 |
| Chọn mốc hợp lệ đầu tiên sau gap, `NEXT_VALID` | Thành 03:00 |
| Từ chối, `REJECT` | Báo rằng giờ danh nghĩa không tồn tại |

Dời theo độ dài gap và chọn mốc hợp lệ đầu tiên là hai hành vi khác nhau. Không đặt chung một tên “tự sửa giờ” mà không nói cụ thể.

Độ dài chuyển đổi không nên bị mã hóa cứng thành một giờ. Quy tắc vùng có thể có chuyển đổi khác; dùng `transition.getDuration()` để biết độ dài thực tế. Một điều chỉnh còn có thể ảnh hưởng ngày, không chỉ phút và giờ.

Chọn chính sách phải theo loại tác vụ. Ví dụ một lịch cần đúng giờ đã yêu cầu có thể từ chối giờ không tồn tại; một lịch vận hành chấp nhận dời có thể dùng một trong hai cách dời. API Java không quyết định giúp mức chấp nhận đó.

Đối với chính sách bỏ lượt, bộ sinh lịch phải tiếp tục sang ngày danh nghĩa kế tiếp. “Ngày này không có lượt” không có nghĩa là toàn bộ lịch đã kết thúc.

## 6. Chính sách khi giờ xuất hiện hai lần

Với Berlin ngày 27/10/2024 lúc 02:30:

| Offset hợp lệ | Instant |
| --- | --- |
| `+02:00` | `2024-10-27T00:30:00Z` |
| `+01:00` | `2024-10-27T01:30:00Z` |

Hai hàng cùng có ngày giờ địa phương nhưng là hai thời điểm cách nhau một giờ.

Có thể chọn:

- **Lượt sớm trên dòng thời gian**: chọn `00:30Z`.
- **Lượt muộn trên dòng thời gian**: chọn `01:30Z`.
- **Cả hai**: sinh hai lần thực thi.
- **Từ chối**: yêu cầu người cấu hình hoặc nghiệp vụ xác định rõ.

Đặt tên theo `EARLIER_INSTANT`/`LATER_INSTANT` giúp tránh nhầm với so sánh số học của offset. `+02:00` lớn hơn `+01:00` nhưng lại cho thời điểm UTC sớm hơn ở cùng giờ địa phương trong ví dụ.

Một lịch “một lượt cho mỗi ngày danh nghĩa” thường phải chọn một trong hai. Nếu chọn chạy cả hai, đây là hai lượt đã được nghiệp vụ cho phép, không phải một lần bị hệ thống chạy trùng. Cơ chế chống lặp cần biết sự khác nhau đó.

Nếu đang tìm lượt kế tiếp từ `now` và lượt sớm đã qua nhưng lượt muộn chưa tới, phải xét từng `Instant` đã sinh. Không loại cả ngày danh nghĩa chỉ vì một ứng viên của ngày đó đã ở quá khứ.

## 7. Không để hành vi mặc định thay thế hợp đồng nghiệp vụ

[ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html) có các quy tắc phân giải mặc định: gap thường được dời về phía trước theo độ dài gap; overlap có thể giữ offset trước đó nếu hợp lệ hoặc chọn offset sớm hơn theo quy tắc API.

Đối với `LocalDateTime.atZone(zone)` khi không có offset ưu tiên, overlap được giải quyết theo lựa chọn mặc định của API. Phương thức không nhất thiết ném lỗi chỉ vì giờ địa phương mơ hồ.

Do đó, một đoạn mã ngắn chạy thành công chưa chứng minh đã áp dụng đúng chính sách mong muốn:

```java
ZonedDateTime resolved = requested.atZone(zone);
```

Nếu hợp đồng thật sự chọn đúng hành vi đó, có thể sử dụng nó sau khi đã xác định ý nghĩa. Nếu cần bỏ lượt, từ chối, chọn lượt muộn hoặc chạy cả hai, phải hiện thực rõ hơn.

`ZonedDateTime.ofStrict(local, offset, zone)` kiểm tra cặp giờ địa phương và offset có hợp lệ trong vùng hay không. Trong ví dụ, nó được gọi sau khi đã lấy offset hợp lệ hoặc đã điều chỉnh giờ theo chính sách; không dùng nó để âm thầm sửa đầu vào.

## 8. Chương trình Java 17+ đầy đủ

Lưu thành `LocalRecurrenceDstDemo.java`. Chương trình phân giải các lượt trên những ngày được chỉ định; nó không tạo tiến trình hẹn giờ hoặc thực thi một tác vụ bên ngoài.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public class LocalRecurrenceDstDemo {
    enum GapPolicy { SKIP, SHIFT_BY_GAP, NEXT_VALID, REJECT }
    enum OverlapPolicy { EARLIER_INSTANT, LATER_INSTANT, BOTH, REJECT }

    record DailySchedule(
            LocalTime nominalTime,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        DailySchedule {
            Objects.requireNonNull(nominalTime);
            Objects.requireNonNull(zone);
            Objects.requireNonNull(gapPolicy);
            Objects.requireNonNull(overlapPolicy);
        }

        List<Instant> occurrencesOn(LocalDate nominalDate) {
            Objects.requireNonNull(nominalDate);
            LocalDateTime local = nominalDate.atTime(nominalTime);
            ZoneRules rules = zone.getRules();
            List<ZoneOffset> offsets = rules.getValidOffsets(local);

            if (offsets.size() == 1) {
                return List.of(ZonedDateTime.ofStrict(
                        local, offsets.get(0), zone).toInstant());
            }

            if (offsets.isEmpty()) {
                ZoneOffsetTransition transition = rules.getTransition(local);
                if (transition == null || !transition.isGap()) {
                    throw new DateTimeException("Missing gap transition");
                }
                return switch (gapPolicy) {
                    case SKIP -> List.of();
                    case NEXT_VALID -> List.of(transition.getInstant());
                    case SHIFT_BY_GAP -> {
                        LocalDateTime shifted = local.plusSeconds(
                                transition.getDuration().getSeconds());
                        yield List.of(ZonedDateTime.ofStrict(
                                shifted, transition.getOffsetAfter(), zone)
                                .toInstant());
                    }
                    case REJECT -> throw new DateTimeException(
                            "Nonexistent local time");
                };
            }

            if (offsets.size() != 2) {
                throw new DateTimeException("Unexpected offset count");
            }
            List<Instant> candidates = offsets.stream()
                    .map(offset -> ZonedDateTime.ofStrict(
                            local, offset, zone).toInstant())
                    .sorted()
                    .toList();

            return switch (overlapPolicy) {
                case EARLIER_INSTANT -> List.of(candidates.get(0));
                case LATER_INSTANT -> List.of(candidates.get(1));
                case BOTH -> candidates;
                case REJECT -> throw new DateTimeException(
                        "Ambiguous local time");
            };
        }
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalTime time = LocalTime.of(2, 30);
        DailySchedule shifted = new DailySchedule(
                time, berlin, GapPolicy.SHIFT_BY_GAP,
                OverlapPolicy.EARLIER_INSTANT);

        LocalDate first = LocalDate.of(2024, 3, 30);
        for (int index = 0; index < 3; index++) {
            LocalDate nominalDate = first.plusDays(index);
            for (Instant occurrence : shifted.occurrencesOn(nominalDate)) {
                System.out.println("daily " + nominalDate + " -> "
                        + occurrence.atZone(berlin));
            }
        }

        LocalDate gapDate = LocalDate.of(2024, 3, 31);
        System.out.println("gap skip = " + new DailySchedule(
                time, berlin, GapPolicy.SKIP,
                OverlapPolicy.EARLIER_INSTANT).occurrencesOn(gapDate));
        System.out.println("gap next valid = " + new DailySchedule(
                time, berlin, GapPolicy.NEXT_VALID,
                OverlapPolicy.EARLIER_INSTANT).occurrencesOn(gapDate));

        LocalDate overlapDate = LocalDate.of(2024, 10, 27);
        for (OverlapPolicy policy : List.of(
                OverlapPolicy.EARLIER_INSTANT,
                OverlapPolicy.LATER_INSTANT,
                OverlapPolicy.BOTH)) {
            DailySchedule schedule = new DailySchedule(
                    time, berlin, GapPolicy.REJECT, policy);
            System.out.println("overlap " + policy + " = "
                    + schedule.occurrencesOn(overlapDate));
        }

        try {
            new DailySchedule(time, berlin, GapPolicy.REJECT,
                    OverlapPolicy.REJECT).occurrencesOn(gapDate);
        } catch (DateTimeException ex) {
            System.out.println("gap reject = " + ex.getMessage());
        }

        ZonedDateTime morning = LocalDate.of(2024, 3, 30)
                .atTime(9, 0).atZone(berlin);
        System.out.println("plus 24 hours = "
                + morning.plus(Duration.ofHours(24)));
        System.out.println("plus one date day = " + morning.plusDays(1));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LocalRecurrenceDstDemo.java
java LocalRecurrenceDstDemo
```

Stdout đã kiểm chứng với dữ liệu múi giờ của môi trường Java đang dùng:

```text
daily 2024-03-30 -> 2024-03-30T02:30+01:00[Europe/Berlin]
daily 2024-03-31 -> 2024-03-31T03:30+02:00[Europe/Berlin]
daily 2024-04-01 -> 2024-04-01T02:30+02:00[Europe/Berlin]
gap skip = []
gap next valid = [2024-03-31T01:00:00Z]
overlap EARLIER_INSTANT = [2024-10-27T00:30:00Z]
overlap LATER_INSTANT = [2024-10-27T01:30:00Z]
overlap BOTH = [2024-10-27T00:30:00Z, 2024-10-27T01:30:00Z]
gap reject = Nonexistent local time
plus 24 hours = 2024-03-31T10:00+02:00[Europe/Berlin]
plus one date day = 2024-03-31T09:00+02:00[Europe/Berlin]
```

`DailySchedule` lưu `nominalTime` và `ZoneId` cùng hai chính sách. `occurrencesOn` trả một danh sách vì một ngày có thể sinh `0`, `1` hoặc `2` lượt theo chính sách:

- Gap với `SKIP` trả danh sách rỗng.
- Trường hợp bình thường và các chính sách chọn một lượt trả một phần tử.
- Overlap với `BOTH` trả hai `Instant` đã được sắp theo thời gian.

`NEXT_VALID` lấy `transition.getInstant()`, là ranh giới bắt đầu áp dụng offset sau chuyển đổi. Với gap trong ví dụ, đó là 03:00 địa phương, khác `SHIFT_BY_GAP` đưa 02:30 thành 03:30.

Các hàm và constructor kiểm tra dữ liệu bắt buộc; chúng không tự dùng vùng máy chủ khi `zone` thiếu. Mã dùng vùng và ngày cố định để có thể kiểm chứng mà không chờ DST xảy ra thực tế.

## 9. Giữ giờ danh nghĩa để tránh lịch bị lệch dần

Ba dòng đầu của stdout là điểm quan trọng:

```text
30/03: 02:30
31/03: 03:30 do chinh sach SHIFT_BY_GAP
01/04: 02:30
```

Ngày 31/03 được dời, nhưng quy tắc gốc vẫn là `02:30`. Ngày 01/04 được tạo bằng **ngày danh nghĩa mới + giờ danh nghĩa gốc**, nên quay lại `02:30`.

Nếu lấy `ZonedDateTime` đã dời tới 03:30 rồi gọi `plusDays(1)` để tạo lượt kế tiếp, giờ 03:30 có thể tiếp tục được giữ. Khi đó hệ thống đã biến ngoại lệ của một ngày thành lịch mới.

Cách tổ chức nên là:

1. Sinh ngày danh nghĩa theo quy tắc lặp.
2. Ghép với giờ danh nghĩa.
3. Tra quy tắc vùng cho chính ngày giờ đó.
4. Áp dụng chính sách gap/overlap.
5. Đưa những `Instant` kết quả vào cơ chế thực thi.

Với lịch tuần, bước đầu chọn đúng thứ trong tuần. Với lịch tháng, bước đầu còn cần chính sách ngày tháng không tồn tại, chẳng hạn ngày 31 trong tháng ngắn. Chính sách ngày tháng và chính sách DST là hai tầng riêng, cần được mô tả độc lập.

Không cập nhật giờ danh nghĩa hoặc vùng gốc chỉ vì một lần phân giải phải điều chỉnh.

## 10. Dữ liệu cần lưu cho một lịch thực tế

Một cấu hình lịch theo giờ địa phương thường cần:

| Dữ liệu | Mục đích |
| --- | --- |
| Mã lịch và phiên bản cấu hình | Nhận diện và kiểm toán thay đổi |
| Quy tắc chọn ngày | Mỗi ngày, mỗi tuần, mỗi tháng... |
| Ngày bắt đầu/kết thúc nếu có | Giới hạn miền lặp |
| `LocalTime` danh nghĩa | Giữ ý định về đồng hồ địa phương |
| Chuỗi `ZoneId` | Tra quy tắc vùng |
| Chính sách gap | Xử lý giờ không tồn tại |
| Chính sách overlap | Xử lý giờ có hai lần |
| Chính sách tác vụ quá hạn | Xử lý khi hệ thống không chạy đúng lúc |

Có thể lưu thêm `nextFireInstant` để truy vấn và đưa vào hàng thực thi. Nhưng giá trị này là **kết quả đã tính**, không nên là bản thay thế duy nhất cho quy tắc gốc.

Khi cần giải thích một lượt đã chạy, nên ghi ngày giờ danh nghĩa, offset đã chọn, thời điểm thực tế, phiên bản lịch và kết quả áp dụng chính sách. Một `Instant` cho biết lúc nào, nhưng không tự giải thích vì sao tác vụ được đặt vào lúc đó.

Nếu lịch đi theo vùng cố định của một chi nhánh, hãy giữ vùng đó. Nếu lịch phải đi theo vùng hiện tại trong hồ sơ người dùng, cần nêu rõ khi nào đổi vùng có hiệu lực và cách xử lý các lượt đã tạo trước; không để cập nhật hồ sơ âm thầm thay đổi những lượt đang chờ mà không có quy tắc.

## 11. Chính sách DST khác với chính sách tác vụ bị lỡ

Giờ 02:30 không tồn tại do DST là một vấn đề của lịch địa phương. Hệ thống bị tắt lúc 09:00 và khởi động lại lúc 10:00 là một vấn đề vận hành khác.

Đối với tác vụ đã đến hạn khi hệ thống không hoạt động, có thể cần:

- Bỏ lượt quá hạn.
- Chạy bù một lượt.
- Chạy bù từng lượt trong một phạm vi.
- Giới hạn số lượt chạy bù để tránh dồn quá nhiều tác vụ.

Các lựa chọn này không được suy ra từ `GapPolicy` hoặc `OverlapPolicy`. Một lịch có `SKIP` trong gap vẫn có thể yêu cầu chạy bù tác vụ 09:00 bị lỡ do máy chủ dừng.

Tương tự, việc chọn `BOTH` trong overlap không cấp phép chạy lại cùng một lượt vô hạn khi retry. Cần có định danh riêng cho từng lượt được sinh, chẳng hạn mã lịch + phiên bản + vị trí danh nghĩa trong quy tắc + nhánh overlap.

Lưu trạng thái thực thi và bảo đảm tác dụng của tác vụ có thể xử lý retry theo yêu cầu là trách nhiệm của cơ chế thực thi. Chỉ tính đúng `Instant` chưa bảo đảm tác vụ thực sự chạy một lần.

## 12. Quy tắc vùng có thể được cập nhật

Dữ liệu múi giờ do môi trường Java cung cấp có thể thay đổi khi nhà cung cấp cập nhật quy tắc. Một lịch tương lai theo vùng phải cân nhắc điều đó.

Có hai yêu cầu khác nhau:

- “Luôn theo giờ địa phương của vùng với quy tắc mới nhất được hệ thống sử dụng.”
- “Giữ nguyên thời điểm đã xác nhận cho một lần cụ thể.”

Đối với yêu cầu đầu, những lượt tương lai đã tính có thể cần được tính lại khi quy tắc vùng được cập nhật. Đối với yêu cầu thứ hai, giữ `Instant` đã xác nhận và dữ liệu giải thích tương ứng có thể là điều cần thiết. Không tự áp dụng một chính sách cho mọi loại lịch.

Cập nhật phải xét trạng thái lượt đã thực thi, đang chờ và cấu hình lịch. Không tính lại toàn bộ rồi vô tình tạo lượt trùng hoặc bỏ lượt.

Khi cần kiểm toán, có thể ghi phiên bản dữ liệu múi giờ nếu nhà cung cấp cho phép truy xuất, cùng phiên bản ứng dụng và cấu hình lịch. Trong một phép kiểm chứng, dùng các ngày chuyển đổi đã biết trong bộ dữ liệu môi trường và kiểm tra những trường hợp biên.

Các ví dụ Berlin năm 2024 trong bài là dữ liệu để quan sát hành vi đã kiểm chứng, không phải công bố rằng mọi vùng sẽ luôn chuyển đổi theo cùng ngày hoặc cùng độ dài.

## 13. Trường hợp biên cần suy nghĩ thêm

Một thay đổi offset không nhất thiết dài đúng một giờ. Nếu điều chỉnh làm chuyển cả ngày, hai ngày danh nghĩa khác nhau có thể dẫn đến những kết quả va chạm tùy chính sách. Hệ thống cần quyết định chạy hai lượt, hợp nhất hay từ chối cấu hình đó.

Khi sinh hàng loạt lịch, nên giới hạn khoảng ngày hoặc số lượt cần tính. Không tạo một danh sách vô hạn chỉ để tìm lượt kế tiếp. Với chính sách bỏ lượt, tiếp tục duyệt ngày trong giới hạn rõ ràng.

Khi lịch có ngày kết thúc, phải xác định giới hạn đó áp dụng cho ngày danh nghĩa hay cho thời điểm sau điều chỉnh. Một lượt của ngày cuối được dời sang ngày sau có thể được chấp nhận hoặc loại theo hai hợp đồng khác nhau.

Phần minh họa tập trung vào phân giải một lượt mỗi ngày trong miền dữ liệu phù hợp. Một bộ lịch đầy đủ còn phải quản lý giới hạn, dữ liệu ngoài miền, thay đổi cấu hình và trạng thái tác vụ; không nên coi record ví dụ là một hệ thống hẹn giờ hoàn chỉnh.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ lưu một `Instant` rồi cộng 24 giờ | Giờ địa phương có thể đổi qua DST | Giữ quy tắc ngày, giờ danh nghĩa và vùng |
| Chỉ lưu offset ban đầu | Mất quy tắc thay đổi của vùng | Giữ `ZoneId` nếu ý định theo vùng |
| Dùng vùng mặc định máy chủ | Lịch đổi nghĩa theo môi trường | Truyền vùng thuộc cấu hình lịch |
| Gọi `atZone` rồi nghĩ mọi giờ đều có duy nhất | Bỏ qua quy tắc mặc định giải quyết gap/overlap | Định nghĩa chính sách rõ |
| Dời mọi gap đúng một giờ | Sai với chuyển đổi khác độ dài | Đọc `ZoneOffsetTransition` |
| Coi dời theo gap giống chọn giờ hợp lệ đầu tiên | Sai phút thực thi | Phân biệt hai chính sách |
| Lấy giờ đã dời của lượt trước làm giờ gốc | Lịch bị lệch dần | Ghép lại từng ngày với `nominalTime` |
| Chọn cả hai lượt overlap nhưng không có định danh nhánh | Khó chống chạy trùng đúng nghĩa | Nhận diện từng lượt được sinh |
| Gộp DST với tác vụ bị lỡ do dừng hệ thống | Chạy bù hoặc bỏ lượt sai | Tách chính sách vận hành |
| Không xét cập nhật dữ liệu múi giờ | Lượt tương lai có thể khác ý định mới | Có chính sách tính lại/giữ mốc rõ ràng |

## 15. Tự kiểm chứng và thực hành

1. Chạy ví dụ và giải thích vì sao lịch 02:30 chỉ bị dời ở ngày gap, rồi trở lại 02:30 vào ngày tiếp theo.
2. So sánh `SHIFT_BY_GAP` và `NEXT_VALID` tại cùng yêu cầu 02:30. Một cách cho 03:30, cách còn lại cho 03:00.
3. Kiểm tra `SKIP` trả danh sách rỗng nhưng vòng sinh lịch vẫn có thể tiếp tục sang ngày sau.
4. Với overlap, kiểm tra hai `Instant` khác nhau nhưng khi xem theo vùng đều có giờ địa phương 02:30.
5. Dùng chính sách `LATER_INSTANT` và xác nhận lượt được chọn là `01:30Z` trong ví dụ.
6. Thử chính sách `REJECT` cho cả gap và overlap; lỗi phải cho biết lý do theo hợp đồng.
7. Đổi giờ danh nghĩa sang 09:00. So sánh khoảng thời gian thực giữa hai ngày quanh chuyển đổi với quy tắc “đúng 24 giờ”.
8. Mô tả khóa nhận diện lượt nếu lịch chọn `BOTH` và hệ thống cần retry tác vụ.
9. Thiết kế lịch tuần có ngày kết thúc và nêu rõ ngày danh nghĩa hay ngày đã điều chỉnh được dùng để xét giới hạn.
10. Mô tả cách xử lý khi người dùng đổi vùng hoặc dữ liệu múi giờ được cập nhật trong lúc đã có các lượt tương lai chờ chạy.

Một lịch theo giờ địa phương cần giữ ý định ban đầu cùng quy tắc vùng và chính sách cho thời gian không tồn tại hoặc không duy nhất. Các `Instant` được sinh ra là kết quả để thực thi; chúng không thay thế toàn bộ ý nghĩa của lịch lặp.
