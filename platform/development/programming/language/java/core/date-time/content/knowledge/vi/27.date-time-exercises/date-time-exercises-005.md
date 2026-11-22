# Tính thời gian phiên làm việc qua nửa đêm

## 1. Qua nửa đêm là đổi ngày, không phải phép trừ giờ đặc biệt

Một phiên bắt đầu lúc 22:30 ngày 10/4 và kết thúc lúc 06:15 ngày 11/4 kéo dài 7 giờ 45 phút nếu vùng đó không có thay đổi độ lệch trong khoảng này. Nếu chỉ giữ hai `LocalTime`, phần ngày bị mất và phép trừ sẽ coi 06:15 đứng trước 22:30 trong cùng ngày.

Muốn tính đúng, trước hết xác định hai đầu mốc đầy đủ. Với phiên thực tế, nên có thời điểm bắt đầu/kết thúc, ví dụ hai `Instant`. Nếu người dùng nhập theo đồng hồ địa phương, cần ngày và vùng để chuyển thành thời điểm.

| Dữ liệu đầu vào | Điều có thể tính |
| --- | --- |
| Chỉ giờ bắt đầu và giờ kết thúc | Chưa đủ để biết ngày kết thúc hoặc số ngày của phiên |
| Hai `LocalDateTime` | Chênh lệch theo ngày giờ địa phương |
| Hai `Instant`, hoặc hai mốc có vùng đã phân giải | Thời lượng thực trôi |

`LocalTime` không lưu ngày hoặc múi giờ; gọi `Duration.between` trên hai giờ không tự suy ra “giờ kết thúc là sáng hôm sau”. [LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html)

## 2. Chọn loại thời lượng trước khi tính

Phân biệt hai câu hỏi:

- **Đồng hồ địa phương chênh nhau bao nhiêu?** Có thể tính trên `LocalDateTime` khi đó chính là tiêu chí được yêu cầu.
- **Thực tế đã trôi qua bao lâu?** Chuyển hai mốc đã phân giải sang `Instant` rồi dùng `Duration.between`.

Qua đêm đổi giờ mùa hè, hai kết quả có thể khác nhau. Một phiên 22:00–06:00 theo đồng hồ vẫn trông như 8 giờ, nhưng thực trôi có thể là 7 hoặc 9 giờ. Cách tính được dùng cho chấm công hay quy đổi nghiệp vụ phải được xác định riêng, không tự coi mọi chính sách đều bằng thời lượng thực trôi.

`Duration` giữ lượng giây và nano giây, phù hợp để cộng/trừ thời lượng. Không dùng `Period` cho tổng số giờ phiên làm việc; `Period` mô tả lượng năm/tháng/ngày lịch. [Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)

## 3. Nếu đầu vào chỉ có giờ

Chỉ được bổ sung ngày hôm sau khi hợp đồng nhập đã nói rõ điều đó. Ví dụ một biểu mẫu có ngày bắt đầu và lựa chọn “kết thúc ngày hôm sau” có thể dựng ngày kết thúc từ lựa chọn ấy.

Đoạn minh họa trong một phương thức:

```java
LocalDate startDate = LocalDate.of(2025, 4, 10);
LocalTime startTime = LocalTime.of(22, 30);
LocalTime endTime = LocalTime.of(6, 15);
boolean endsNextDay = true;

LocalDate endDate = endsNextDay ? startDate.plusDays(1) : startDate;
LocalDateTime localStart = LocalDateTime.of(startDate, startTime);
LocalDateTime localEnd = LocalDateTime.of(endDate, endTime);
```

Không dùng quy tắc “nếu kết quả âm thì cộng 24 giờ” cho mọi dữ liệu. Nó có thể che lỗi nhập ngược hai mốc, không xử lý phiên nhiều ngày và bỏ qua ngày dài/ngắn khi đổi giờ.

Cũng cần chốt trường hợp hai giờ bằng nhau: có thể là phiên 0 giờ, phiên 24 giờ hoặc nhiều ngày. Hai `LocalTime` không phân biệt được các khả năng này.

## 4. Các bất biến nên kiểm tra

Với một phiên đã đóng và có thời lượng dương:

1. Hai đầu mốc không được thiếu.
2. Mốc kết thúc phải sau mốc bắt đầu.
3. Khoảng nghỉ cần trừ phải nằm trong phiên.
4. Các khoảng nghỉ không được chồng nhau nếu cộng chúng trực tiếp để trừ.

Biểu diễn các khoảng bằng `[start, end)` giúp hai đoạn nghỉ liền nhau không chồng tại điểm tiếp giáp. Nếu muốn chấp nhận phiên 0 giờ, phải thay kiểm tra và quy định ý nghĩa rõ ràng; ví dụ dưới đây chủ động từ chối.

## 5. Chương trình tính thời lượng và trừ nghỉ

Lưu thành `OvernightSessionDemo.java`. Ví dụ bình thường dùng vùng Việt Nam; hai ví dụ Berlin chọn giờ đầu/cuối không nằm trong khoảng thiếu hoặc trùng giờ.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class OvernightSessionDemo {
    record Span(Instant start, Instant end) {
        Span {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");
            if (!start.isBefore(end)) {
                throw new IllegalArgumentException("End must be after start");
            }
        }

        Duration elapsed() {
            return Duration.between(start, end);
        }
    }

    static Span localSpan(LocalDateTime start, LocalDateTime end, ZoneId zone) {
        return new Span(start.atZone(zone).toInstant(), end.atZone(zone).toInstant());
    }

    static Duration netDuration(Span session, List<Span> breaks) {
        List<Span> ordered = breaks.stream()
                .sorted(Comparator.comparing(Span::start)).toList();
        Duration rest = Duration.ZERO;
        Instant previousEnd = session.start();

        for (Span item : ordered) {
            if (item.start().isBefore(session.start())
                    || item.end().isAfter(session.end())) {
                throw new IllegalArgumentException("Break must be inside session");
            }
            if (item.start().isBefore(previousEnd)) {
                throw new IllegalArgumentException("Breaks must not overlap");
            }
            rest = rest.plus(item.elapsed());
            previousEnd = item.end();
        }
        return session.elapsed().minus(rest);
    }

    static String hoursAndMinutes(Duration value) {
        return value.toHours() + "h " + value.toMinutesPart() + "m";
    }

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Span session = localSpan(
                LocalDateTime.of(2025, 4, 10, 22, 30),
                LocalDateTime.of(2025, 4, 11, 6, 15), vietnam);
        Span rest = localSpan(
                LocalDateTime.of(2025, 4, 11, 2, 0),
                LocalDateTime.of(2025, 4, 11, 2, 30), vietnam);

        System.out.println("grossMinutes=" + session.elapsed().toMinutes());
        System.out.println("gross=" + hoursAndMinutes(session.elapsed()));
        Duration net = netDuration(session, List.of(rest));
        System.out.println("netMinutes=" + net.toMinutes());
        System.out.println("net=" + hoursAndMinutes(net));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime springStart = LocalDateTime.of(2025, 3, 29, 22, 0);
        LocalDateTime springEnd = LocalDateTime.of(2025, 3, 30, 6, 0);
        Span spring = localSpan(springStart, springEnd, berlin);
        Span autumn = localSpan(
                LocalDateTime.of(2025, 10, 25, 22, 0),
                LocalDateTime.of(2025, 10, 26, 6, 0), berlin);

        System.out.println("springWallHours="
                + Duration.between(springStart, springEnd).toHours());
        System.out.println("springElapsedHours=" + spring.elapsed().toHours());
        System.out.println("autumnElapsedHours=" + autumn.elapsed().toHours());
        System.out.println("longSession=" + hoursAndMinutes(Duration.ofHours(30)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 OvernightSessionDemo.java
java OvernightSessionDemo
```

Stdout với dữ liệu IANA tương ứng các quy tắc vùng năm 2025:

```text
grossMinutes=465
gross=7h 45m
netMinutes=435
net=7h 15m
springWallHours=8
springElapsedHours=7
autumnElapsedHours=9
longSession=30h 0m
```

Ngày kết thúc trong ví dụ Việt Nam là 11/4; giờ nghỉ 02:00 cũng thuộc ngày 11/4, không phải ngày bắt đầu. Giữ ngày cho từng đầu mốc làm phép trừ tự nhiên, không cần nhánh vá “qua nửa đêm”.

Hàm trừ nghỉ sắp xếp các khoảng và từ chối chồng nhau để tránh trừ hai lần cùng một phần thời gian. Nó chỉ trừ những khoảng được truyền vào; việc khoảng nào được tính là nghỉ là quy tắc ngoài hàm.

## 6. DST và phân giải giờ nhập

`Duration.between(springStart, springEnd)` trên hai `LocalDateTime` trong chương trình cho 8 giờ theo các thành phần địa phương. Sau khi gắn vùng Berlin và chuyển sang `Instant`, kết quả thực trôi là 7 giờ vì có một lần nhảy giờ trong đêm.

Ở đêm lùi giờ mùa thu, thực trôi là 9 giờ. Không thêm hoặc trừ cứng một giờ theo tháng; dùng quy tắc vùng của đúng ngày.

Nếu đầu vào thật sự nằm trong gap/overlap, `atZone` có chính sách mặc định điều chỉnh hoặc chọn độ lệch. Hàm `localSpan` trong bài chỉ được dùng với các đầu mốc đã biết hợp lệ, không mơ hồ như dữ liệu mẫu. Khi làm biểu mẫu tổng quát, kiểm tra `zone.getRules().getValidOffsets(local)` và yêu cầu xử lý giờ thiếu/trùng rõ ràng trước khi gọi.

Khi đã có mốc từ thiết bị chấm giờ ở dạng `Instant`, dùng trực tiếp hai mốc đó để tính thực trôi; không đổi sang giờ địa phương rồi bỏ vùng để tính lại. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 7. Hiển thị và làm tròn thời lượng

`Duration.toHours()` trả tổng số giờ trọn vẹn; `toHoursPart()` là phần giờ sau khi tách các ngày 24 giờ. Với một phiên 30 giờ, dùng `toHoursPart()` để hiển thị tổng có thể chỉ thấy 6 giờ. Tương tự, không dùng `LocalTime` làm nơi chứa tổng thời lượng vì nó quay vòng trong ngày.

Hàm `hoursAndMinutes` dùng tổng giờ và phần phút để cho `30h 0m`. Nếu dữ liệu có giây hoặc phần lẻ, hàm này chỉ **hiển thị** đến phút, không áp dụng quy tắc làm tròn nghiệp vụ.

Nếu phải quy đổi thành phút hoặc giờ thập phân, cần quyết định cắt/làm tròn theo cách nào và ở bước nào. Làm tròn từng đoạn trước khi cộng có thể khác với cộng thời lượng chính xác rồi làm tròn một lần. Giữ `Duration` hoặc đơn vị đủ chính xác trong tính toán trung gian.

## 8. Phiên nhiều ngày, phiên đang mở và báo cáo theo ngày

Đối với phiên dài hơn một đêm, giữ ngày kết thúc thật; không dùng một cờ “qua ngày” để đại diện mọi khoảng nhiều ngày. Kiểm tra giới hạn độ dài nếu nghiệp vụ có, thay vì tự rút gọn bằng modulo 24 giờ.

Phiên chưa kết thúc cần trạng thái riêng. Có thể tính thời lượng tạm đến một `now` được lấy từ đồng hồ đã chọn, nhưng không ghi mốc tạm đó thành giờ kết thúc thật nếu phiên vẫn mở.

Nếu báo cáo cần chia phiên qua nửa đêm thành từng ngày địa phương, dựng ranh giới đầu ngày theo vùng, cắt khoảng phiên tại các ranh giới rồi tính mỗi đoạn bằng `Instant`. Phần chia ngày và phần tính tổng là hai nhiệm vụ khác nhau; không để việc chia đoạn làm thay đổi tổng thực trôi.

Khi hai đầu mốc có vùng khác nhau, vẫn có thể tính giữa hai `Instant`; còn việc gán phiên cho ngày nghiệp vụ phải chọn vùng báo cáo rõ ràng. [LocalDateTime: dữ liệu không có vùng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)

## 9. Tự kiểm tra

1. Tính phiên 23:50 ngày 31/12/2025 đến 00:20 ngày 1/1/2026 tại Việt Nam.
2. Thêm hai khoảng nghỉ liền nhau rồi thử hai khoảng chồng nhau.
3. So sánh phiên 22:00–06:00 qua hai đêm đổi giờ Berlin trong chương trình.
4. Tạo phiên 30 giờ và xác nhận hiển thị không quay về 06:00.

Đối chiếu: (1) 30 phút; (2) liền nhau được nhận, chồng nhau bị từ chối; (3) thực trôi 7 và 9 giờ dù đồng hồ địa phương chênh 8 giờ; (4) tổng là 30 giờ.