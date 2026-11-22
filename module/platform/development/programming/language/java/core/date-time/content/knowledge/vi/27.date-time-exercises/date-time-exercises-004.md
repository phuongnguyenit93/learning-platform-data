# Chuyển lịch hẹn giữa hai múi giờ và xử lý DST

## 1. Chuyển cùng cuộc hẹn hay dời giờ hẹn?

Giả sử cuộc hẹn được nhập là “02:30 tại Berlin”. Trước khi hiển thị nó cho người ở New York, phải biết **ngày nào** và phân giải giờ Berlin thành một thời điểm cụ thể. Sau đó đổi cách hiển thị sang New York mà giữ nguyên thời điểm.

Luồng thực hành là:

```text
Ngày giờ địa phương + vùng nguồn
    → kiểm tra giờ thiếu/trùng do đổi giờ
    → chọn độ lệch hợp lệ theo chính sách
    → một thời điểm đã xác định
    → hiển thị cùng thời điểm tại vùng đích
```

Không chuyển bằng cách cộng một chênh lệch cố định như “Berlin luôn hơn New York 6 giờ”. Hai nơi có thể đổi giờ mùa hè vào các ngày khác nhau; chênh lệch còn phụ thuộc thời điểm.

## 2. Dữ liệu đầu vào tối thiểu

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| `LocalDateTime` | `2025-10-26T02:30` | Điều người đặt nhìn trên đồng hồ địa phương |
| `ZoneId` nguồn | `Europe/Berlin` | Quy tắc xác định độ lệch của địa điểm |
| Lựa chọn khi trùng giờ | Lần đầu hoặc lần sau | Chọn một thời điểm nếu có hai khả năng |
| `ZoneId` đích | `America/New_York` | Cách người nhận xem cùng lịch hẹn |

`ZoneOffset` như `+02:00` là độ lệch, không phải định danh vùng. Nếu đầu vào dùng tên vùng, phải kiểm tra lựa chọn độ lệch có hợp lệ với ngày giờ và vùng đó. Nếu chỉ nhận chuỗi giờ `02:30` mà thiếu ngày, chưa đủ thông tin để xử lý DST.

## 3. Ba kết quả khi phân giải giờ nguồn

`sourceZone.getRules().getValidOffsets(localDateTime)` cho các độ lệch hợp lệ của giờ địa phương:

| Số độ lệch | Ý nghĩa thường gặp | Cần làm gì? |
| --- | --- | --- |
| 1 | Giờ thông thường | Dùng độ lệch đó |
| 0 | Khoảng giờ không tồn tại, gọi là gap | Từ chối hoặc điều chỉnh theo chính sách rõ ràng |
| 2 | Giờ xuất hiện hai lần, gọi là overlap | Chọn lần đầu/lần sau hoặc yêu cầu người dùng chọn |

Trong Berlin năm 2025, `2025-03-30T02:30` không tồn tại khi đồng hồ nhảy lên. `2025-10-26T02:30` xuất hiện hai lần với `+02:00` và `+01:00`.

Với overlap, danh sách độ lệch sắp theo lần trước và sau chuyển đổi; chọn `+02:00` ở ví dụ cho thời điểm sớm hơn, còn `+01:00` cho thời điểm muộn hơn. Không chọn bằng cách sắp xếp chuỗi hoặc đoán độ lệch nào “lớn hơn”. [ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

## 4. Chính sách của bài thực hành

Chương trình dưới đây:

- Từ chối giờ nằm trong gap.
- Với overlap, cho phép `REJECT`, `EARLIER` hoặc `LATER` do phía gọi chọn.
- Sau khi giải quyết giờ nguồn, chuyển vùng bằng `withZoneSameInstant`.

`ZonedDateTime.ofStrict(local, offset, zone)` kiểm tra đủ ba thành phần có tương thích hay không. Nó phù hợp khi ứng dụng đã có lựa chọn cụ thể và không muốn thư viện tự sửa giờ.

`LocalDateTime.atZone(zone)` tiện dụng nhưng có mặc định: thường đẩy giờ trong gap về phía trước theo độ dài khoảng nhảy và chọn độ lệch sớm hơn trong overlap nếu không có lựa chọn khác. Chỉ dùng mặc định đó khi nó chính là hợp đồng mong muốn. [ZonedDateTime: phân giải vùng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#ofStrict(java.time.LocalDateTime,java.time.ZoneOffset,java.time.ZoneId))

## 5. Chương trình hoàn chỉnh

Lưu thành `AppointmentZoneDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class AppointmentZoneDemo {
    enum OverlapPolicy { REJECT, EARLIER, LATER }

    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, OverlapPolicy overlapPolicy) {
        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");
        Objects.requireNonNull(overlapPolicy, "overlapPolicy");
        List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException("Local time is in a gap");
        }
        if (offsets.size() == 1) {
            return ZonedDateTime.ofStrict(local, offsets.get(0), zone);
        }
        if (overlapPolicy == OverlapPolicy.REJECT) {
            throw new DateTimeException("Choose an occurrence in the overlap");
        }
        ZoneOffset selected = overlapPolicy == OverlapPolicy.EARLIER
                ? offsets.get(0) : offsets.get(offsets.size() - 1);
        return ZonedDateTime.ofStrict(local, selected, zone);
    }

    public static void main(String[] args) {
        ZoneId source = ZoneId.of("Europe/Berlin");
        ZoneId target = ZoneId.of("America/New_York");
        LocalDateTime overlap = LocalDateTime.of(2025, 10, 26, 2, 30);

        ZonedDateTime earlier = resolve(overlap, source, OverlapPolicy.EARLIER);
        ZonedDateTime later = resolve(overlap, source, OverlapPolicy.LATER);
        ZonedDateTime earlierAtTarget = earlier.withZoneSameInstant(target);

        System.out.println("earlierSource=" + earlier);
        System.out.println("earlierInstant=" + earlier.toInstant());
        System.out.println("earlierTarget=" + earlierAtTarget);
        System.out.println("laterSource=" + later);
        System.out.println("laterInstant=" + later.toInstant());
        System.out.println("laterTarget=" + later.withZoneSameInstant(target));
        System.out.println("occurrenceDistanceMinutes="
                + Duration.between(earlier.toInstant(), later.toInstant()).toMinutes());
        System.out.println("sameInstant="
                + earlier.toInstant().equals(earlierAtTarget.toInstant()));

        ZonedDateTime changedMeaning = earlier.withZoneSameLocal(target);
        System.out.println("sameLocalKeepsInstant="
                + earlier.toInstant().equals(changedMeaning.toInstant()));

        try {
            resolve(overlap, source, OverlapPolicy.REJECT);
        } catch (DateTimeException ex) {
            System.out.println("overlapRejected");
        }

        LocalDateTime gap = LocalDateTime.of(2025, 3, 30, 2, 30);
        try {
            resolve(gap, source, OverlapPolicy.EARLIER);
        } catch (DateTimeException ex) {
            System.out.println("gapRejected");
        }
        System.out.println("defaultGapAdjustment=" + gap.atZone(source));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 AppointmentZoneDemo.java
java AppointmentZoneDemo
```

Stdout với quy tắc IANA Berlin/New York năm 2025:

```text
earlierSource=2025-10-26T02:30+02:00[Europe/Berlin]
earlierInstant=2025-10-26T00:30:00Z
earlierTarget=2025-10-25T20:30-04:00[America/New_York]
laterSource=2025-10-26T02:30+01:00[Europe/Berlin]
laterInstant=2025-10-26T01:30:00Z
laterTarget=2025-10-25T21:30-04:00[America/New_York]
occurrenceDistanceMinutes=60
sameInstant=true
sameLocalKeepsInstant=false
overlapRejected
gapRejected
defaultGapAdjustment=2025-03-30T03:30+02:00[Europe/Berlin]
```

Hai cách chọn 02:30 Berlin cách nhau 60 phút thực trôi và thành hai giờ khác nhau trong ngày trước đó ở New York. Đổi vùng có thể đổi cả ngày; không được chỉ lấy phần giờ để dựng lại ngày nguồn.

`defaultGapAdjustment` minh chứng mặc định của thư viện, không phải nhánh xử lý của hàm `resolve`. Hàm vẫn từ chối đầu vào 02:30 không tồn tại.

## 6. Chuyển cùng thời điểm không tạo mơ hồ mới

Sau khi đã có một `Instant`, hiển thị tại vùng đích bằng `instant.atZone(target)` hoặc `withZoneSameInstant(target)` xác định được một giá trị có độ lệch. Nếu giờ đích thuộc một overlap, độ lệch trong kết quả cho biết đang là lần nào.

Mơ hồ xuất hiện trở lại nếu bỏ độ lệch/vùng rồi chỉ giữ chuỗi giờ địa phương. Vì vậy, khi hiển thị lịch gần chuyển giờ, nên kèm đủ ngày, vùng và/hoặc độ lệch để người nhận hiểu đúng.

`withZoneSameLocal` giữ cách đọc đồng hồ địa phương khi đổi vùng và có thể đổi thời điểm. Nó phù hợp cho một loại dời lịch khác, không phải chuyển cách xem cùng cuộc hẹn. [ZonedDateTime.withZoneSameInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#withZoneSameInstant(java.time.ZoneId))

## 7. Nếu muốn chấp nhận giờ trong gap

Có thể đề nghị giờ hợp lệ đầu tiên sau khoảng nhảy, hoặc dịch giờ nhập về phía trước một lượng bằng độ dài gap. Hai chính sách này khác nhau: với 02:30 và khoảng nhảy 02:00→03:00, chọn giờ hợp lệ đầu tiên cho 03:00, còn dịch theo độ dài gap cho 03:30.

`ZoneOffsetTransition` cung cấp thông tin trước/sau chuyển đổi, `isGap()` và `getDuration()`. Nếu ứng dụng chọn dịch giờ, hãy dùng thông tin chuyển đổi thực thay vì cộng cứng một giờ: không phải mọi thay đổi độ lệch trong mọi vùng đều dài 60 phút. [ZoneOffsetTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html)

Cần trả lại giờ đã chốt cho người dùng để họ biết cuộc hẹn khác giờ nhập ban đầu. Không chỉ lưu kết quả đã sửa rồi làm như người dùng đã chọn nó.

## 8. Lưu lịch hẹn và xử lý các lần lặp

Với lịch theo địa điểm, có thể giữ ngày giờ nhập, vùng nguồn, lựa chọn overlap và thời điểm đã phân giải. Phải nói rõ dữ liệu nào quyết định khi quy tắc múi giờ được cập nhật: giữ ý định giờ địa phương hay giữ thời điểm đã chốt.

Với lịch lặp “mỗi tuần 09:00 Berlin”, sinh ngày địa phương của từng lần rồi phân giải theo quy tắc. Cộng đều `Duration.ofDays(7)` vào thời điểm trước không bảo đảm giữ 09:00 sau một lần đổi giờ mùa hè.

Một cuộc họp đã chốt thành thời điểm cần được gửi cho các bên dưới dạng có thể xác định cùng một `Instant`; thông tin vùng có thể đi kèm để hiển thị. Đừng chỉ gửi `02:30` rồi để mỗi máy tự gắn vùng mặc định.

## 9. Kiểm tra tình huống quan trọng

- Giờ thông thường với đúng một độ lệch.
- Giờ trong gap và từng chính sách chấp nhận/từ chối.
- Hai lần của overlap, xác nhận chúng khác thời điểm.
- Chuyển vùng làm đổi ngày ở phía nhận.
- Ngày mà hai vùng đã đổi giờ ở các thời điểm khác nhau.
- Vòng chuyển nguồn→đích→nguồn, kiểm tra `toInstant()` không đổi khi mục tiêu là cùng cuộc hẹn.

Dữ liệu múi giờ của JDK là một đầu vào của phép tính. Khi kết quả khác giữa môi trường, so sánh vùng, ngày giờ, lựa chọn độ lệch và dữ liệu quy tắc trước khi kết luận chỉ là lỗi định dạng.

## 10. Tự thực hành

1. Đổi vùng đích của chương trình thành `Asia/Ho_Chi_Minh` và đối chiếu cùng `Instant`.
2. Với overlap, thử chính sách `REJECT` và trả thông báo yêu cầu chọn lần đầu/lần sau.
3. Thiết kế phản hồi hiển thị cả giờ nhập và giờ đã điều chỉnh nếu chấp nhận gap.
4. Giải thích vì sao không cần hỏi người xem chọn overlap khi đầu vào đã là một `Instant` xác định.

Đối chiếu: (1) thay cách nhìn, không đổi thời điểm; (2) không tự đoán; (3) cho thấy rõ thay đổi; (4) mỗi thời điểm đã xác định độ lệch tại vùng đích.