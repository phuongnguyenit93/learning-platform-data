# Ngày giờ trong chương trình: khái niệm, vai trò và các bài toán thường gặp

Một ứng dụng phải trả lời được “sự kiện xảy ra lúc nào?”, “hôm nay là ngày mấy?”, “đã trôi qua bao lâu?”, “lịch hẹn 9 giờ sáng của người dùng ở quốc gia khác ứng với thời điểm nào?” và “khi nào mã xác thực hết hạn?”. Đây là **những câu hỏi khác nhau**, dù đều liên quan đến ngày giờ. Nếu dùng cùng một kiểu dữ liệu hoặc tùy tiện cộng trừ giờ cho mọi trường hợp, ứng dụng có thể sai ở ranh giới ngày, cuối tháng, giờ mùa hè hoặc khi chạy trên nhiều máy chủ.

Bài học giới thiệu mô hình tư duy, vai trò của ngày giờ trong phần mềm, cách chọn kiểu dữ liệu `java.time` và những bài toán thực tế thường gặp. Mục tiêu là hiểu **ý nghĩa của dữ liệu trước khi chọn API**, để các bài học chuyên sâu sau này có nền tảng vững.

## 1. Ngày giờ được dùng để làm gì?

| Tình huống | Câu hỏi thực sự | Dữ liệu cốt lõi |
| --- | --- | --- |
| Ghi log, tạo đơn, audit | Sự kiện xảy ra ở mốc nào trên dòng thời gian? | Thời điểm tuyệt đối |
| Sinh nhật, ngày nghỉ, ngày quyết toán | Ngày nào theo lịch? | Ngày lịch |
| Giờ mở cửa 08:00–17:00 | Mấy giờ theo đồng hồ địa phương? | Giờ trong ngày, có thể kèm khu vực |
| Họp lúc 09:00 ở Hà Nội | Giờ địa phương đó tương ứng với mốc nào? | Ngày giờ + múi giờ |
| OTP sống thêm 5 phút | Đã qua bao lâu, hết hạn ở mốc nào? | Khoảng thời gian + thời điểm hết hạn |
| Chạy báo cáo “hôm nay” | “Hôm nay” theo múi giờ của ai? | Ranh giới ngày trong múi giờ nghiệp vụ |
| Thống kê tác vụ chạy 125 ms | Tác vụ tốn bao nhiêu thời gian? | Đồng hồ đo thời gian trôi qua |
| Nhắc việc ngày cuối tháng | Tháng kế tiếp có ngày tương ứng không? | Quy tắc lịch, không chỉ số giây |

Điểm chung là các hệ thống cần **xác định, hiển thị, tính toán, so sánh và trao đổi** dữ liệu liên quan đến thời gian. Nhưng “ngày” không đồng nghĩa với “thời điểm”, “một tháng” không đồng nghĩa với “30 ngày”, và “9 giờ sáng” chưa đủ thông tin để xác định một instant.

## 2. Năm khái niệm phải phân biệt

### 2.1. Ngày lịch và giờ trên đồng hồ

**Ngày lịch (calendar date)** gồm năm, tháng, ngày, chẳng hạn `2026-10-24`. Ngày sinh, ngày nghỉ lễ hay ngày xuất hóa đơn thường chỉ cần khái niệm này. Ngày tự nó **không chứa giờ, offset hay múi giờ**.

**Giờ trong ngày (local time)** như `09:30:00` cũng không mang ngày hoặc khu vực. Khi ghép hai giá trị ta có **ngày giờ địa phương (local date-time)**, ví dụ `2026-10-24 09:30`. Tuy nhiên, đây vẫn chỉ là số trên đồng hồ ở một nơi chưa xác định; **không suy ra duy nhất thời điểm toàn cầu**.

### 2.2. Thời điểm tuyệt đối (instant)

**Instant** biểu diễn một mốc duy nhất trên dòng thời gian. Cùng một sự kiện, người ở hai quốc gia có thể nhìn đồng hồ thấy hai giờ khác nhau, nhưng instant của sự kiện vẫn là một.

Ví dụ `2026-06-01T10:15:30Z` là một instant biểu diễn theo UTC (`Z` cho biết offset bằng 0). Ở Việt Nam, mốc đó được hiển thị thành `2026-06-01 17:15:30 +07:00`. Đây là **hai cách hiển thị cùng một sự kiện**.

**Unix epoch** là mốc `1970-01-01T00:00:00Z`. Timestamp dạng số đếm giây/mili giây từ mốc này thường gặp ở hệ thống phân tán. Cần thống nhất **đơn vị**: giây và mili giây chênh nhau 1.000 lần; không đoán chỉ từ số chữ số. `Instant` giữ ngữ nghĩa thời điểm rõ ràng hơn số trần.

### 2.3. UTC offset khác múi giờ

**Offset** như `+07:00` chỉ mức lệch so với UTC **tại một mốc**. **Múi giờ (time zone)** như `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York` là định danh khu vực và bộ quy tắc xác định offset theo thời gian, bao gồm thay đổi lịch sử và giờ mùa hè (DST) ở một số nơi.

Offset cố định không mô tả đầy đủ quy tắc của một địa phương trong các mùa hoặc năm khác nhau. Lịch họp lặp lại “09:00 ở New York mỗi thứ Hai” cần **ZoneId khu vực**, không chỉ một offset của ngày đầu tiên.

### 2.4. Duration và Period

**Duration** biểu diễn lượng thời gian trôi qua, ví dụ 30 giây, 15 phút, 24 giờ. **Period** biểu diễn khoảng lịch bằng năm, tháng, ngày, ví dụ thêm một tháng hoặc một năm.

“Sau đúng 24 giờ” và “cùng giờ vào ngày mai” thường trùng nhau nhưng có thể khác nhau tại khu vực đổi giờ mùa hè. “Thêm một tháng” không phải luôn “thêm 30 ngày”. Hãy dựa vào quy tắc nghiệp vụ để chọn phép tính.

### 2.5. Đồng hồ lịch và đồng hồ đo thời lượng

**Wall clock** dùng để biết “bây giờ” và gắn mốc cho sự kiện. Giờ hệ thống có thể được đồng bộ/điều chỉnh. **Đo thời lượng** như thời gian chạy code cần nguồn đo phù hợp: `System.nanoTime()` có ích khi lấy hiệu giữa hai lần đọc trong **cùng tiến trình JVM**, nhưng giá trị tuyệt đối không phải timestamp và không dùng để lưu ngày giờ. Đừng lấy hiệu hai wall-clock timestamp làm thước đo hiệu năng chính xác cho tác vụ rất ngắn.

## 3. Các kiểu trong Java cần chọn đúng

| Kiểu `java.time` | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| `LocalDate` | Ngày lịch, không có giờ/múi giờ | Ngày sinh, ngày nghỉ, hạn theo ngày |
| `LocalTime` | Giờ trong một ngày | Giờ mở cửa, giờ hẹn cố định |
| `LocalDateTime` | Ngày giờ địa phương nhưng chưa có khu vực | Thời gian người dùng nhập trước khi xác định địa điểm |
| `Instant` | Mốc tuyệt đối trên dòng thời gian | `createdAt`, `updatedAt`, log, sự kiện |
| `OffsetDateTime` | Ngày giờ kèm offset cụ thể | Dữ liệu API có offset |
| `ZonedDateTime` | Ngày giờ kèm múi giờ khu vực và quy tắc | Sự kiện, lịch hẹn tại địa phương |
| `ZoneId` / `ZoneOffset` | Khu vực / độ lệch cố định | Chuyển đổi và hiển thị |
| `Duration` | Khoảng thời gian đo bằng giây/nano giây | Timeout, hiệu lực OTP, độ dài xử lý |
| `Period` | Khoảng lịch theo năm, tháng, ngày | Tuổi, cộng theo tháng, hạn lịch |
| `Clock` | Nguồn thời gian có thể thay thế | Logic “bây giờ”, kiểm thử |

Các lớp ngày giờ chính thuộc `java.time` là immutable: cộng/trừ/chuyển đổi tạo giá trị mới; điều này giúp hạn chế lỗi chia sẻ trạng thái. `DateTimeFormatter` phục vụ parse và format chuỗi. Trong code mới, ưu tiên `java.time`; hệ thống cũ có thể dùng `java.util.Date`, `Calendar`, cần chú ý khi tích hợp.

**Chọn nhanh:** “Ngày nào?” → `LocalDate`; “mấy giờ?” → `LocalTime`; “sự kiện thực sự xảy ra lúc nào?” → `Instant`; “giờ tại địa phương nào?” → `ZonedDateTime`; “bao lâu?” → `Duration` hoặc `Period`.

## 4. Chuyển giữa thời điểm và giờ địa phương

Giả sử máy chủ ghi nhận một đơn hàng tại `2026-06-01T10:15:30Z`. Giao diện có thể hiển thị 17:15:30 ở Việt Nam và 10:15:30 ở UTC. **Instant không thay đổi**, chỉ có góc nhìn địa phương thay đổi.

Luồng đúng là: `Instant` → `atZone(ZoneId)` → `ZonedDateTime` để hiển thị. Theo chiều ngược lại, phải có **ngày giờ địa phương và thông tin ZoneId/offset** mới chuyển về instant. Không “cộng tay 7 giờ rồi lưu lại” và không mặc định timezone của máy chủ chính là timezone người dùng.

Nếu dữ liệu chỉ là `LocalDateTime.of(2026, 6, 1, 9, 0)`, hệ thống **chưa biết** đó là 09:00 Hà Nội, Paris hay New York. Tự biến giá trị này thành UTC làm thay đổi ý nghĩa ban đầu.

## 5. Ví dụ Java 17+ chạy được và có đầu ra cố định

Dùng `Clock.fixed` để kết quả độc lập với đồng hồ thực tế. Ví dụ cho thấy một instant, hiển thị cùng instant tại Việt Nam, tính hạn bằng ngày lịch và hạn hiệu lực bằng phút.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class DateTimeOverviewDemo {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-06-01T10:15:30Z"),
                ZoneOffset.UTC
        );

        Instant createdAt = Instant.now(clock);
        ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime displayedTime = createdAt.atZone(userZone);

        LocalDate today = LocalDate.now(clock.withZone(userZone));
        LocalDate dueDate = LocalDate.of(2026, 6, 15);
        Period untilDue = Period.between(today, dueDate);

        Instant expiresAt = createdAt.plus(Duration.ofMinutes(30));
        long minutes = Duration.between(createdAt, expiresAt).toMinutes();

        DateTimeFormatter fmt =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss XXX");

        System.out.println("Thoi diem UTC: " + createdAt);
        System.out.println("Gio Viet Nam: " + displayedTime.format(fmt));
        System.out.println("Ngay den han: " + dueDate);
        System.out.println("So ngay lich: " + untilDue.getDays());
        System.out.println("So phut hieu luc: " + minutes);
        System.out.println("Het han UTC: " + expiresAt);
    }
}
~~~

Lưu đúng tên `DateTimeOverviewDemo.java`. Biên dịch và chạy:

~~~bash
javac DateTimeOverviewDemo.java
java DateTimeOverviewDemo
~~~

Đầu ra:

~~~text
Thoi diem UTC: 2026-06-01T10:15:30Z
Gio Viet Nam: 2026-06-01 17:15:30 +07:00
Ngay den han: 2026-06-15
So ngay lich: 14
So phut hieu luc: 30
Het han UTC: 2026-06-01T10:45:30Z
~~~

`createdAt` và `expiresAt` là thời điểm tuyệt đối. `displayedTime` chỉ phục vụ trình bày cho người dùng. `dueDate` là ngày lịch chứ không phải nửa đêm UTC. `Period.between` trả **thành phần** năm/tháng/ngày; `getDays()` ở đây cho 14 vì hai ngày cùng tháng. Nếu muốn **tổng số ngày giữa hai ngày** qua nhiều tháng, dùng `ChronoUnit.DAYS.between(startDate, endDate)` thay vì chỉ lấy `Period.getDays()`.

## 6. Những bài toán phổ biến

### 6.1. Ghi thời điểm tạo/cập nhật và hết hạn

Dùng `Instant` cho sự kiện cần xác định trên dòng thời gian:

~~~java
Instant createdAt = Instant.now();
Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));
Instant now = Instant.now();
boolean expired = !now.isBefore(expiresAt);
~~~

Đoạn này cần `import java.time.Instant;` và `import java.time.Duration;`. Quy tắc `!now.isBefore(expiresAt)` có nghĩa là **đúng thời điểm hết hạn cũng đã hết hạn**. Trong tác vụ có nhiều phép kiểm liên quan, lấy `now` một lần để quyết định được nhất quán. Với hạn bảo mật, ưu tiên đồng hồ phía máy chủ đáng tin cậy; không dựa duy nhất vào timestamp do client tự cung cấp.

### 6.2. Ngày sinh, ngày lễ, ngày giao hàng

Dùng `LocalDate` nếu dữ liệu chỉ cần **ngày lịch**. Một người có ngày sinh 24/10 không nên bị đổi thành 23/10 khi giao diện ở vùng có offset âm chỉ vì ngày sinh được lưu thành một timestamp UTC.

Khi hỏi “mọi giao dịch trong ngày 24/10 theo giờ Việt Nam”, ta mới cần **chuyển ranh giới ngày** thành instant theo vùng nghiệp vụ:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 10, 24);

Instant fromInclusive = date.atStartOfDay(zone).toInstant();
Instant toExclusive = date.plusDays(1)
        .atStartOfDay(zone).toInstant();

boolean inDay = !eventInstant.isBefore(fromInclusive)
        && eventInstant.isBefore(toExclusive);
~~~

Đây là **đoạn minh họa**, biến `eventInstant` cần được khai báo từ ngữ cảnh. Khoảng **[bắt đầu, bắt đầu ngày kế tiếp)** tránh trùng sự kiện giữa hai ngày liên tiếp, không phải đoán “giây cuối ngày” dựa trên độ chính xác mili giây. Ở vùng có đổi giờ, hai ranh giới liên tiếp có thể không cách nhau đúng 24 giờ.

### 6.3. Lịch họp theo khu vực

Giờ họp “09:00 ngày 15/06/2026 tại Hà Nội” cần cả ngày giờ địa phương và `ZoneId`:

~~~java
LocalDateTime localStart = LocalDateTime.of(2026, 6, 15, 9, 0);
ZoneId meetingZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meeting = localStart.atZone(meetingZone);
Instant actualMoment = meeting.toInstant();
~~~

Đây cũng là đoạn minh họa; cần import `LocalDateTime`, `ZoneId`, `ZonedDateTime`, `Instant`. Có thể lưu `actualMoment` cho một lần họp cụ thể. Nếu họp **lặp lại 09:00 mỗi thứ Hai theo giờ khu vực**, lưu cả quy tắc lặp và `ZoneId`; chỉ cộng 24 giờ vào instant của buổi đầu sẽ sai giờ địa phương tại khu vực chuyển DST.

### 6.4. “Cộng một ngày”, “cộng một tháng” và thời lượng

- `Duration.ofHours(24)`: đúng 24 giờ đã trôi qua.
- `ZonedDateTime.plusDays(1)`: ngày kế tiếp theo lịch khu vực, thường giữ giờ địa phương.
- `LocalDate.plusMonths(1)`: cộng một tháng lịch; ví dụ 31/01/2026 cộng một tháng thành 28/02/2026.
- `Duration.between(startInstant, endInstant)`: tính độ dài giữa hai thời điểm.
- `Period.between(startDate, endDate)`: chênh lệch theo thành phần lịch năm/tháng/ngày.

Đừng đổi `Period.ofMonths(1)` thành `Duration.ofDays(30)` nếu nghiệp vụ thật sự cần “tháng tiếp theo”. Trong nơi đổi giờ mùa hè, “ngày mai cùng giờ” và “sau 24 giờ” có thể tạo hai instant khác nhau.

### 6.5. Đọc và định dạng chuỗi

Ưu tiên định dạng rõ, ổn định ở ranh giới hệ thống và định dạng theo ngôn ngữ ở giao diện:

~~~java
LocalDate date = LocalDate.parse("2026-10-24"); // ISO date
Instant event = Instant.parse("2026-06-01T10:15:30Z");

DateTimeFormatter viDate =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
String text = date.format(viDate); // "24/10/2026"
~~~

Đoạn minh họa cần import `LocalDate`, `Instant`, `DateTimeFormatter`. `LocalDate.parse` hiểu chuỗi ngày ISO theo mặc định; chuỗi `24/10/2026` muốn parse phải truyền formatter tường minh. Trong pattern, `MM` là **tháng**, `mm` là **phút**; `HH` là giờ 0–23, `hh` là giờ chu kỳ 12 tiếng. Dùng `uuuu` khi cần năm theo lịch ISO. Khi định dạng tên tháng/ngày dạng chữ, đặt `Locale` phù hợp; đừng trông vào locale mặc định của máy chủ.

### 6.6. Dữ liệu qua API và cơ sở dữ liệu

Cho sự kiện tuyệt đối, định dạng ISO-8601 với UTC/offset rõ ràng (ví dụ `2026-06-01T10:15:30Z`) giúp tránh nhập nhằng. Khi cần giữ “giờ 09:00 tại nơi tổ chức”, lưu thêm múi giờ và quy tắc lịch trong miền nghiệp vụ.

Cẩn thận với các kiểu SQL `DATE`, `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE`. **Hành vi giữ offset/múi giờ và chuyển đổi phụ thuộc hệ quản trị, driver và ORM**, không suy đoán từ tên kiểu. Kiểm tra precision (giây, mili giây, micro giây...) khi đọc/ghi. Trường hợp dữ liệu là ngày thuần lịch thì dùng kiểu ngày, không ép thành một instant.

Khi gửi epoch dạng số qua JSON, tài liệu API phải ghi đơn vị rõ ràng. Nếu nhiều dịch vụ viết log, cần cấu hình timezone và đồng bộ đồng hồ; timestamp không bảo đảm thứ tự tuyệt đối của sự kiện phân tán khi đồng hồ các máy bị lệch. Các bài toán thứ tự phức tạp có thể cần sequence/ID logic riêng.

### 6.7. Lập lịch định kỳ

Phân biệt “chạy lại sau mỗi 24 giờ” với “chạy lúc 08:00 mỗi ngày theo giờ cửa hàng”. Cái trước là duration; cái sau là **quy tắc theo lịch + ZoneId**. Lịch hàng tháng vào ngày 31 phải chỉ rõ cách xử lý tháng không có ngày 31. “Ngày làm việc kế tiếp” còn cần quy tắc cuối tuần và danh sách ngày lễ; `LocalDate.plusDays(1)` không tự hiểu ngày làm việc.

## 7. Giờ mùa hè (DST) và giờ địa phương không hợp lệ

Tại một số khu vực, offset thay đổi theo mùa. Điều đó tạo ra:

1. **Gap:** đồng hồ nhảy tiến, một khoảng giờ địa phương không tồn tại (ví dụ một thời điểm 02:30 trong đêm đổi giờ tại vùng áp dụng).
2. **Overlap:** đồng hồ lùi, một giờ địa phương có thể xảy ra **hai lần**, tương ứng hai instant khác nhau.

Vì vậy, chuyển `LocalDateTime` sang `ZonedDateTime` không luôn là ánh xạ một-một. `atZone` có quy tắc giải quyết mặc định, nhưng lịch đặt vé/đặt hẹn quan trọng cần chính sách rõ ràng: báo giờ không hợp lệ, dời giờ, hoặc chọn offset cụ thể.

Có thể dùng `ZoneId.getRules().getValidOffsets(localDateTime)`: danh sách có 0 offset nghĩa là gap; 1 là bình thường; 2 là overlap. Không thay `ZoneId.of("America/New_York")` bằng `ZoneOffset.ofHours(-5)` cho mọi tháng. Quy tắc múi giờ có thể cập nhật khi chính quyền thay đổi quy định; runtime/tzdb của hệ thống cũng cần được duy trì phù hợp.

## 8. Kiểm thử và đo thời gian

Code gọi `Instant.now()` ở khắp nơi khó kiểm thử tình huống hết hạn, qua ngày mới hoặc cuối tháng. Dùng `Clock` có thể thay thế khi test:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-06-01T10:15:30Z"),
        ZoneOffset.UTC
);
Instant now = Instant.now(fixed);
Instant deadline = Instant.parse("2026-06-01T10:15:30Z");
boolean expired = !now.isBefore(deadline); // true
~~~

Đoạn minh họa cần import `Clock`, `Instant` và `ZoneOffset`. Nên test **trước**, **đúng bằng**, **sau** deadline; cuối tháng, năm nhuận; các múi giờ khác nhau và DST gap/overlap nếu bài toán có lịch địa phương.

Muốn đo thời gian thực hiện trong cùng JVM:

~~~java
long started = System.nanoTime();
// Chạy công việc cần đo.
long elapsedNanos = System.nanoTime() - started;
~~~

`elapsedNanos` là **chênh lệch thời gian đo**; không chuyển thành ngày giờ hay so với epoch. Đối với timeout trong hệ thống thật, cần cân nhắc timer/scheduler, độ lệch đồng hồ và tính nhất quán của nguồn thời gian.

## 9. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lưu ngày sinh thành nửa đêm UTC | Người ở vùng khác có thể thấy ngày hôm trước | Dùng `LocalDate` |
| Lưu `LocalDateTime` như thời điểm tuyệt đối | Không biết múi giờ/offset để xác định instant | Dùng `Instant` hoặc dữ liệu có vùng/offset |
| Dùng offset cố định cho lịch địa phương dài hạn | Có thể sai khi múi giờ đổi quy tắc/DST | Giữ `ZoneId` khu vực |
| Tưởng “ngày mai” luôn sau đúng 24 giờ | Sai tại ranh giới chuyển giờ | Phân biệt cộng theo lịch với `Duration` |
| Dùng `Period.getDays()` như tổng số ngày giữa hai tháng | Chỉ là thành phần ngày trong period | Dùng `ChronoUnit.DAYS.between` |
| Nhầm epoch giây và mili giây | Lệch timestamp rất lớn | Xác định đơn vị, dùng API `Instant` |
| Dùng `MM` cho phút | Nhầm tháng với phút | Dùng `mm` và test formatter |
| “Đổi timezone” bằng cộng tay số giờ | Phá ý nghĩa instant, sai DST | Dùng `atZone` và `ZoneId` |
| Tin client timestamp để xác thực hết hạn | Client có thể tự sửa thời gian | Dùng nguồn thời gian dịch vụ đáng tin cậy |
| Lấy ngày bằng `23:59:59` làm cuối khoảng | Bỏ sót phần nhỏ của giây | Dùng [đầu ngày, đầu ngày tiếp theo) |
| Benchmark bằng hiệu giờ đồng hồ thông thường | Đồng hồ có thể bị điều chỉnh | Dùng hiệu `System.nanoTime()` |

## 10. Quy trình chọn giải pháp cho một yêu cầu mới

1. **Xác định ý nghĩa:** ngày lịch, giờ trong ngày, ngày giờ địa phương, instant hay khoảng thời gian?
2. **Xác định chủ sở hữu múi giờ:** người dùng, chi nhánh, nơi diễn ra sự kiện hoặc hệ thống?
3. **Chọn điều cần bảo toàn:** cùng một instant hay cùng một giờ địa phương khi tái diễn?
4. **Định nghĩa phép tính:** cộng 24 giờ thực, cộng một ngày lịch, hay sang ngày làm việc kế tiếp?
5. **Chọn ranh giới:** mốc hết hạn có tính bằng đúng thời điểm kết thúc không? Truy vấn khoảng thời gian nên dùng biên đầu inclusive, biên cuối exclusive khi thích hợp.
6. **Chuẩn hóa giao tiếp:** chuỗi ISO có offset, epoch với đơn vị được công bố, hay ngày thuần lịch?
7. **Kiểm thử biên:** cuối tháng, 29/02, sai lệch timezone, DST, ngày đổi múi giờ, ranh giới hết hạn.

### Tự kiểm tra hiểu bài

- Ngày sinh `24/10/2000` nên lưu bằng `LocalDate` hay `Instant`, và tại sao?
- Hai máy chủ ghi log cùng một sự kiện theo giờ đồng hồ địa phương. Chỉ dùng `LocalDateTime` có đủ để so sánh không?
- Lịch họp 09:00 New York hàng ngày khác gì một tác vụ thực thi sau mỗi 24 giờ?
- Một đơn hàng phát sinh đúng 00:00 ngày kế tiếp có nằm trong khoảng “ngày hôm qua” khi biên cuối exclusive không?
- API gửi số `1792848000`: cần biết thêm điều gì trước khi chuyển nó thành thời gian?

**Ghi nhớ:** ngày giờ là dữ liệu có **ngữ nghĩa nghiệp vụ**. Chọn đúng mô hình từ đầu sẽ giúp lưu trữ nhất quán, hiển thị theo đúng khu vực, tính hạn đúng và lập lịch an toàn trên nhiều hệ thống.