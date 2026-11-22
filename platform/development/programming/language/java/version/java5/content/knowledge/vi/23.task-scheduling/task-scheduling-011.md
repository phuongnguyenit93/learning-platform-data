# Phân biệt lịch theo khoảng thời gian với lịch theo ngày giờ nghiệp vụ

## 1. Hai yêu cầu trông giống nhau nhưng có ý nghĩa khác

So sánh:

- “Đợi 10 phút rồi kiểm tra lại.”
- “Mỗi ngày lúc 09:00 theo múi giờ của chi nhánh.”
- “Sau khi xử lý xong, nghỉ 30 giây rồi làm tiếp.”
- “Ngày làm việc đầu tiên của tháng chạy báo cáo.”

Các yêu cầu thứ nhất và thứ ba chủ yếu nói về **khoảng thời gian trôi qua**. Các yêu cầu còn lại nói về **ngày giờ trên lịch và quy tắc nghiệp vụ**.

Không nên chuyển tất cả thành một số giây rồi nghĩ ý nghĩa vẫn giữ nguyên. Một ngày lịch không luôn tương đương 24 giờ trôi qua ở mọi múi giờ; ngày làm việc lại còn phụ thuộc quy tắc riêng.

Bài này giải thích cách chọn mô hình và ranh giới của ScheduledExecutorService. Ví dụ dùng API hiện hành tương thích Java 17+.

## 2. Lịch theo khoảng thời gian

Một số ví dụ:

| Nhu cầu | Cách diễn đạt thường phù hợp |
|---|---|
| Kiểm tra lại sau 10 giây | Một lần `schedule` với delay tương đối |
| Thực hiện theo các mốc cách nhau 5 giây | `scheduleAtFixedRate`, với chính sách chạy trễ đã hiểu |
| Làm xong rồi nghỉ ít nhất 30 giây | `scheduleWithFixedDelay` |

Các phương thức của ScheduledExecutorService nhận delay và period **tương đối**, không nhận một biểu thức lịch theo múi giờ.

Ví dụ minh họa:

```java
scheduler.schedule(task, 10, TimeUnit.MINUTES);
```

Nơi gọi yêu cầu công việc được phép chạy sau khoảng trễ. Nó không nói “lúc đồng hồ lịch chỉ 10:00”.

Tương tự, `scheduleAtFixedRate(task, initialDelay, 24, TimeUnit.HOURS)` dùng một khoảng cố định 24 giờ giữa các mốc dự kiến. Nó không tự đánh giá lại quy tắc “09:00 mỗi ngày tại Europe/Berlin”.

Hợp đồng và lưu ý về đồng hồ được mô tả trong [ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

## 3. Lịch theo ngày giờ nghiệp vụ cần những dữ liệu nào?

Yêu cầu “chạy hàng ngày lúc 09:00” chưa hoàn chỉnh nếu không biết:

1. Múi giờ nào?
2. Những ngày nào được chạy?
3. Nếu thời điểm đó không tồn tại hoặc xuất hiện hai lần thì làm gì?
4. Nếu hệ thống ngừng hoạt động khi tới hạn thì có chạy bù không?
5. Nếu lần trước chưa xong thì bỏ, đợi, gộp hay chạy đồng thời?
6. Nếu đã chạy nhưng chưa kịp ghi nhận thành công thì xử lý lặp thế nào?

Lịch nghiệp vụ không chỉ là một định dạng chuỗi. Nó là tập quy tắc xác định **lần tới cần xử lý cho kỳ nào** và cách ứng dụng phản hồi những trường hợp đặc biệt.

Với lịch của một địa điểm, dùng ZoneId tường minh thay vì tự lấy múi giờ mặc định của máy chủ. Việc chuyển nơi triển khai không nên âm thầm đổi giờ nghiệp vụ.

### ZoneId khác ZoneOffset

ZoneOffset là độ lệch cụ thể so với UTC, như +07:00. ZoneId như Asia/Ho_Chi_Minh hoặc Europe/Berlin liên kết với bộ quy tắc múi giờ.

Đối với lịch tương lai theo địa phương, không nên thay một ZoneId bằng offset đang quan sát tại hôm nay rồi giả định offset ấy áp dụng mãi.

## 4. Các kiểu java.time giúp tách ý nghĩa

| Kiểu | Diễn đạt |
|---|---|
| `Instant` | Một thời điểm trên dòng thời gian |
| `LocalDate` | Một ngày lịch, chưa có múi giờ |
| `LocalTime` | Một giờ trong ngày, chưa có múi giờ |
| `LocalDateTime` | Ngày và giờ địa phương, chưa tự xác định một instant duy nhất |
| `ZoneId` | Múi giờ với các quy tắc liên quan |
| `ZonedDateTime` | Ngày giờ gắn với múi giờ và offset đã xác định |
| `Duration` | Một lượng thời gian theo giây và nano giây |
| `Period` | Một lượng theo năm, tháng và ngày lịch |

Duration một ngày là 24 giờ theo mô hình thời lượng. Period một ngày thể hiện bước dịch chuyển theo lịch, cố giữ giờ địa phương khi áp dụng phù hợp.

Chẳng hạn với ZonedDateTime, thêm một ngày lịch và thêm 24 giờ có thể cho hai giờ địa phương khác nhau qua thời điểm đổi offset.

Xem [Duration API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html) và [Period API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html).

## 5. Vì sao “09:00 ngày mai” có thể chỉ cách 23 giờ?

Ở một múi giờ chuyển sang giờ mùa hè, offset có thể tăng một giờ. Lúc 09:00 hôm sau theo giờ địa phương khi đó tới sớm hơn một giờ so với việc cộng 24 giờ trên dòng thời gian.

Ví dụ lịch sử tại Europe/Berlin:

```text
2024-03-30 09:00, offset +01:00
       |
       +-- thêm 1 ngày lịch --> 2024-03-31 09:00, offset +02:00
       |                      thời gian trôi qua: 23 giờ
       |
       +-- thêm 24 giờ -----> 2024-03-31 10:00, offset +02:00
```

Điều này không phải scheduler chạy sai. Nó là hai yêu cầu khác nhau.

Một vùng không đang dùng đổi giờ mùa hè vẫn cần ZoneId rõ cho lịch địa phương. Ứng dụng có thể phục vụ nhiều vùng hoặc quy tắc địa phương có thể thay đổi; không nên xây mô hình bằng giả định mọi ngày ở mọi nơi đều có cùng độ dài.

Đặc điểm ánh xạ giữa ngày giờ địa phương và Instant được mô tả trong [ZonedDateTime API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html).

## 6. Giờ không tồn tại và giờ có hai cách hiểu

Khi offset thay đổi, một LocalDateTime có thể có:

| Số offset hợp lệ | Tình huống |
|---:|---|
| 1 | Ngày giờ địa phương ánh xạ bình thường |
| 0 | Khoảng trống: giờ đó không tồn tại |
| 2 | Khoảng lặp: giờ đó xuất hiện với hai offset |

Ví dụ tại Europe/Berlin trong năm 2024:

- 02:30 ngày 31/03 nằm trong khoảng giờ bị nhảy qua.
- 02:30 ngày 27/10 xuất hiện với hai offset hợp lệ.

Một quy tắc “chạy lúc 02:30 hàng ngày” cần nói rõ làm gì ở những ngày ấy. Có thể bỏ ngày, dời tới thời điểm hợp lệ, chọn lần đầu, chọn lần sau hoặc từ chối cấu hình. Không có một lựa chọn đúng mặc định cho mọi nghiệp vụ.

Các phương thức tiện ích như atZone có cách giải quyết mặc định. Nếu nghiệp vụ cần chính sách khác, không dùng mặc định mà không nhận biết.

Có thể kiểm tra bằng `zone.getRules().getValidOffsets(localDateTime)`. Xem [ZoneRules API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html).

### Hai lần chạy trong giờ lặp chưa chắc là lỗi trùng

Nếu nghiệp vụ yêu cầu một lần cho mỗi **ngày địa phương**, cần có định danh kỳ theo ngày đó để hai instant trong giờ lặp không tự thành hai lần xử lý nghiệp vụ.

Nếu nghiệp vụ thật sự muốn cả hai lần, phải định danh bằng thông tin đủ phân biệt, chẳng hạn instant hoặc offset. Yêu cầu này cần được xác định trước khi chọn khóa chống lặp.

## 7. Chương trình Java 17+: so sánh 24 giờ và ngày lịch

Ví dụ sử dụng một mốc cố định để không phụ thuộc ngày đang chạy trên máy. Hàm tính 09:00 kế tiếp dùng chính sách **chỉ chấp nhận ngày giờ có đúng một offset**, và chọn mốc nằm sau now một cách nghiêm ngặt.

Lưu thành **`CalendarScheduleDemo.java`**:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class CalendarScheduleDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Berlin");

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 9, 0, 0, 0, zone);

        ZonedDateTime nextCalendarDay = start.plusDays(1);
        ZonedDateTime after24Hours =
                start.plus(Duration.ofHours(24));

        System.out.println("start: " + start);
        System.out.println(
                "next calendar day: " + nextCalendarDay);
        System.out.println(
                "elapsed calendar hours: "
                + Duration.between(
                        start.toInstant(),
                        nextCalendarDay.toInstant()).toHours());
        System.out.println("after 24 hours: " + after24Hours);

        Clock clock = Clock.fixed(
                Instant.parse("2024-03-30T12:00:00Z"),
                ZoneOffset.UTC);

        Instant nextRun = nextDailyStrict(
                clock, zone, LocalTime.of(9, 0));
        System.out.println("next 09:00 instant: " + nextRun);

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println(
                "gap valid offsets: "
                + zone.getRules().getValidOffsets(gap).size());
        System.out.println(
                "overlap valid offsets: "
                + zone.getRules().getValidOffsets(overlap).size());
    }

    private static Instant nextDailyStrict(
            Clock clock, ZoneId zone, LocalTime time) {
        Instant now = clock.instant();
        LocalDate today = now.atZone(zone).toLocalDate();

        ZonedDateTime candidate =
                resolveUnique(today.atTime(time), zone);

        if (!candidate.toInstant().isAfter(now)) {
            candidate = resolveUnique(
                    today.plusDays(1).atTime(time), zone);
        }
        return candidate.toInstant();
    }

    private static ZonedDateTime resolveUnique(
            LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                    "Business time needs an explicit gap/overlap policy");
        }

        return ZonedDateTime.ofLocal(local, zone, offsets.get(0));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CalendarScheduleDemo.java
java CalendarScheduleDemo
```

Stdout chính xác với bộ quy tắc múi giờ chứa các chuyển đổi lịch sử nêu trên:

```text
start: 2024-03-30T09:00+01:00[Europe/Berlin]
next calendar day: 2024-03-31T09:00+02:00[Europe/Berlin]
elapsed calendar hours: 23
after 24 hours: 2024-03-31T10:00+02:00[Europe/Berlin]
next 09:00 instant: 2024-03-31T07:00:00Z
gap valid offsets: 0
overlap valid offsets: 2
```

### Phạm vi của hàm ví dụ

Hàm minh họa việc tính một instant tiếp theo từ ngày, giờ và zone; nó chưa thực hiện lịch bền vững, ngày nghỉ, chạy bù hoặc điều phối nhiều tiến trình.

Chính sách từ chối ở gap/overlap được chọn để không âm thầm đoán nghiệp vụ. Hàm kiểm tra mốc ứng viên theo chính sách ấy; nó không tự bỏ qua ngày đặc biệt hoặc tự chọn một offset.

Nếu now đúng bằng mốc ứng viên, hàm chọn ngày sau. Trong ứng dụng thật, cần quyết định liệu “đúng hạn ngay lúc này” phải được xử lý hôm nay hay chuyển sang lần sau, và kiểm thử chính sách ấy.

Clock.fixed giúp mọi lần kiểm thử có cùng now. Có thể thay bằng Clock được ứng dụng cung cấp khi vận hành. Vai trò nguồn đồng hồ có thể thay thế được mô tả tại [Clock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html).

## 8. Nối thời điểm nghiệp vụ với scheduler tương đối

Sau khi tính một Instant mục tiêu, có thể tính khoảng cách từ now để lập lịch một lần:

```java
Instant now = clock.instant();
Duration remaining = Duration.between(now, target);
long delayMillis = Math.max(0, remaining.toMillis());

scheduler.schedule(task, delayMillis, TimeUnit.MILLISECONDS);
```

Đây là đoạn mã minh họa ở ranh giới hai mô hình. Target, task, clock và scheduler do ứng dụng quản lý.

Cần lưu ý:

- Chuyển sang mili giây có thể cắt phần lẻ nhỏ hơn một mili giây.
- Target đã quá hạn được ví dụ đưa về delay 0; đó là một chính sách cần được xác nhận theo nghiệp vụ.
- Khoảng thời gian quá lớn có thể vượt khả năng chuyển của Duration; phải giới hạn đầu vào phù hợp.
- Từ lúc tính delay tới lúc scheduler thực thi, đồng hồ lịch hoặc dữ liệu quy tắc có thể thay đổi.

Vì thế, một lần chuyển từ Instant sang delay không tự tạo bảo đảm “luôn chạy đúng ngày giờ nghiệp vụ dù hoàn cảnh thay đổi”.

Khi tác vụ được kích hoạt, có thể cần kiểm tra lại kỳ cần xử lý và trạng thái đã thực hiện, thay vì chỉ tin rằng callback tới đồng nghĩa mọi điều kiện nghiệp vụ đều còn đúng.

## 9. Lịch hàng ngày nên tính lần tới theo quy tắc, không chỉ cộng 24 giờ

Với yêu cầu ngày giờ địa phương, một hướng tổ chức là:

```text
Đọc quy tắc lịch và trạng thái kỳ
    -> tính ngày giờ nghiệp vụ tiếp theo
    -> giải quyết zone/gap/overlap
    -> chuyển thành Instant
    -> lập lịch một lần hoặc giao cho hệ thống lập lịch phù hợp
    -> khi được kích hoạt, kiểm tra kỳ và thực hiện
    -> ghi nhận kết quả rồi tính lần tiếp theo theo chính sách
```

Không chỉ lấy giờ bắt đầu thực tế của lần trước rồi cộng 24 giờ nếu mục tiêu là bám 09:00 địa phương.

Cũng không nhất thiết luôn tính từ “thời điểm hoàn tất gần nhất”: nếu công việc chậm một ngày, ứng dụng cần biết phải chạy bù hay bỏ kỳ. Quy tắc lần tới phải dựa trên ý nghĩa nghiệp vụ, không chỉ một phép cộng thời gian.

Nếu dùng callback tự đăng ký lại, cần bảo đảm lỗi không làm mất toàn bộ lịch tương lai và không đăng ký trùng sau retry. Đây là trách nhiệm vòng đời bổ sung, không có sẵn chỉ từ việc gọi schedule lần nữa.

## 10. Khởi động lại, quá hạn và nhiều phiên bản ứng dụng

### Lịch trong bộ nhớ không sống qua lần khởi động

ScheduledExecutorService không tự lưu lịch vào cơ sở dữ liệu. Nếu tiến trình dừng khi tới hạn, lúc khởi động lại phải có cách xác định những kỳ cần xử lý.

Các lựa chọn nghiệp vụ có thể là:

- Bỏ những kỳ đã qua và bắt đầu từ kỳ tiếp theo.
- Chạy một lần bù cho kỳ gần nhất.
- Xử lý đủ các kỳ chưa hoàn tất.
- Chỉ chạy nếu chưa vượt một thời hạn hữu ích.

Không tự mặc định chạy tất cả kỳ quá hạn, vì có thể tạo một đợt tải lớn hoặc các tác động không còn cần thiết.

### Hai tiến trình có thể cùng tính ra một mốc

Nếu hai bản ứng dụng đều dùng cùng quy tắc, cả hai có thể lập lịch và xử lý cùng kỳ.

Cần cơ chế điều phối hoặc nhận việc có tính nguyên tử phù hợp, cùng định danh kỳ và khả năng xử lý lặp an toàn. Một cờ trong bộ nhớ chỉ bảo vệ trong phạm vi tiến trình đó.

Không tuyên bố “chính xác một lần” chỉ vì scheduler có một worker hoặc mỗi lịch có một ScheduledFuture.

## 11. Bộ quy tắc múi giờ và kiểm thử

Quy tắc múi giờ được cung cấp bởi dữ liệu của runtime; thông tin cho tương lai có thể được cập nhật. Khi nâng JDK hoặc dữ liệu zone, những lịch xa trong tương lai có thể cần tính lại theo yêu cầu.

Kiểm thử nên bao gồm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Trước và sau giờ chạy trong ngày bình thường | Chọn đúng ngày ứng viên |
| Đúng bằng mốc chạy | Chính sách có bao gồm hiện tại hay không |
| Ngày có giờ bị nhảy qua | Bỏ, dời hoặc từ chối đúng quy tắc |
| Giờ xuất hiện hai lần | Chọn offset hoặc số lần chạy theo nghiệp vụ |
| Đổi múi giờ mặc định của máy | Lịch dùng ZoneId tường minh vẫn đúng |
| Hệ thống ngừng qua nhiều kỳ | Chạy bù hoặc bỏ kỳ đúng chính sách |
| Hai phiên bản cùng khởi động | Không xử lý trùng ngoài cam kết |
| Công việc kéo dài qua kỳ sau | Không tạo chồng lặp không kiểm soát |

Dùng Clock cố định hoặc nguồn now được tiêm vào thay vì viết kiểm thử phụ thuộc “ngày hôm nay”. Những kiểm thử này xác minh quy tắc lịch; chúng không thay cho kiểm tra vòng đời executor hoặc cơ chế lưu bền.

## 12. Tự kiểm tra

1. “Mỗi 24 giờ” có luôn giữ cùng giờ địa phương mỗi ngày không?
2. LocalDateTime tự nó có luôn xác định một instant duy nhất không?
3. Vì sao một giờ địa phương có thể có 0 hoặc 2 offset hợp lệ?
4. Schedule nhận một thời điểm epoch hay khoảng trễ tương đối?
5. Tính đúng mốc 09:00 có tự giải quyết việc ứng dụng ngừng lúc tới hạn không?
6. Vì sao lịch của chi nhánh nên dùng ZoneId rõ thay vì múi giờ mặc định của máy?

**Gợi ý:** (1) Không, offset có thể đổi. (2) Không. (3) Do khoảng trống hoặc lặp khi quy tắc zone chuyển offset. (4) Khoảng trễ tương đối. (5) Không, cần trạng thái kỳ và chính sách quá hạn. (6) Để ý nghĩa nghiệp vụ không phụ thuộc môi trường triển khai.

Chọn mô hình theo yêu cầu: **khoảng thời gian** mô tả lượng chờ hoặc nhịp thực thi; **lịch nghiệp vụ** mô tả ngày giờ, múi giờ, kỳ xử lý và cách phản hồi những trường hợp đặc biệt.
