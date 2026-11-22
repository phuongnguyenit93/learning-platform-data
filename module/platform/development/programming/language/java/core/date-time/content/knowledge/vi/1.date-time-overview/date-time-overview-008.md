# Lộ trình học Java Date-Time: từ thao tác cơ bản đến múi giờ và kiểm thử

## Mục tiêu và cách học

Bài này là bản đồ học tập cho module **Java core – date-time**. Sau lộ trình, bạn cần tự chọn đúng kiểu dữ liệu ngày giờ, thực hiện phép tính và so sánh, đọc/ghi chuỗi ISO 8601, đổi múi giờ mà không đổi thời điểm thực, nhận biết lỗi chuyển giờ mùa hè (DST), và viết phép kiểm thử độc lập với đồng hồ của máy.

**Điều kiện đầu vào:** biết kiểu dữ liệu, class, method, exception và cách chạy Java 17+. Học theo từng chặng bên dưới: đọc ý tưởng → chạy ví dụ → sửa dữ liệu đầu vào → hoàn thành bài tập → đối chiếu tiêu chí đạt. Có thể học trong khoảng 7 buổi thực hành; tiến độ phụ thuộc kinh nghiệm.

**Nguyên tắc cốt lõi:** trước mỗi phép toán hãy hỏi dữ liệu là **ngày lịch**, **giờ trên đồng hồ**, **thời điểm tuyệt đối** hay **thời điểm theo quy tắc múi giờ**. Chọn kiểu sai ở bước này thường dẫn đến sai lệch cả khi cú pháp Java hoàn toàn đúng.

## 1. Bản đồ kiểu dữ liệu cần biết

| Kiểu hoặc thành phần | Đại diện cho | Dùng khi |
| --- | --- | --- |
| `LocalDate` | Ngày lịch, không có giờ/múi giờ | Ngày sinh, hạn nộp theo ngày, ngày nghỉ |
| `LocalTime` | Giờ trong một ngày, không có ngày/múi giờ | 09:30, giờ mở cửa |
| `LocalDateTime` | Ngày + giờ địa phương, **chưa xác định một thời điểm duy nhất** | Lịch hẹn nhập theo đồng hồ địa phương, cần ghép với `ZoneId` |
| `Instant` | Một thời điểm trên dòng thời gian UTC | Timestamp sự kiện, log, mốc bắt đầu/kết thúc |
| `ZoneId` | Quy tắc múi giờ theo vùng, ví dụ `Asia/Ho_Chi_Minh` | Lịch theo địa phương; cần áp dụng DST lịch sử/tương lai |
| `ZoneOffset` | Độ lệch UTC tại một thời điểm, ví dụ `+07:00` | Đọc/ghi offset cụ thể; không thay thế quy tắc của cả vùng |
| `ZonedDateTime` | Ngày giờ địa phương + múi giờ vùng + offset đã xác định | Cuộc họp tại một thành phố và việc chuyển múi giờ |
| `OffsetDateTime` | Ngày giờ + offset cố định, không giữ quy tắc vùng | API có offset, audit event cần giữ offset đã truyền |
| `Duration` | Lượng thời gian theo giây/nanosecond | Timeout, thời lượng phiên chạy |
| `Period` | Khoảng cách theo năm/tháng/ngày lịch | Cộng tháng, kỳ hạn theo lịch |
| `DateTimeFormatter` | Định dạng và phân tích chuỗi ngày giờ | Biên API, biểu mẫu, giao diện |
| `Clock` | Nguồn thời gian có thể thay thế | Nghiệp vụ có “hôm nay/bây giờ” và unit test |

Phần lớn kiểu trong `java.time` là **immutable**: `plusDays()`, `withYear()`, `atZone()` trả về đối tượng mới. Cần gán kết quả; gọi method mà bỏ giá trị trả về sẽ không sửa biến gốc.

Ba khái niệm rất dễ nhầm:

- **Local date/time**: thông tin trên lịch hoặc đồng hồ; riêng `LocalDateTime.of(2026, 11, 1, 1, 30)` chưa chỉ ra một `Instant` duy nhất tại New York trong giờ DST lặp lại.
- **Instant**: điểm thời gian tuyệt đối. Cùng một `Instant` có thể hiển thị là 19:00 tại TP.HCM và 08:00 tại New York trong mùa hè.
- **ZoneId và ZoneOffset**: vùng `America/New_York` có thể đổi offset từ `-05:00` sang `-04:00`; chuỗi `-05:00` tự nó không biết quy tắc chuyển đổi.

## 2. Lộ trình thực hành theo thứ tự

| Chặng | Trọng tâm | Bài thực hành | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| 1. Khởi đầu | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`; tạo giá trị cố định | Tạo ngày 30/01/2026 và giờ 09:30 | Giải thích được kiểu nào có/không có vùng giờ |
| 2. Phép toán | `plus`/`minus`, `with`, `isBefore`/`isAfter`, `ChronoUnit`, `Period`/`Duration` | Tính hạn sau 3 ngày; cộng 1 tháng | Giải thích vì sao 30/01 + 1 tháng = 28/02/2026 |
| 3. Chuỗi và định dạng | `parse`, `format`, ISO 8601, `DateTimeFormatter` và `Locale` | Đổi `31/12/2026` ↔ `LocalDate` | Biết xử lý chuỗi sai bằng `DateTimeParseException` |
| 4. Dòng thời gian | `Instant`, `ZoneId`, `ZoneOffset`, `ZonedDateTime` | Cùng sự kiện UTC hiển thị tại 2 thành phố | Hiểu chuyển vùng giữ nguyên `Instant` |
| 5. DST và ranh giới | Giờ không tồn tại/giờ trùng, ngày nhuận, cuối tháng, qua nửa đêm | Xử lý 02:30 và 01:30 ở New York | Phát hiện trường hợp phải hỏi quy tắc nghiệp vụ |
| 6. Kiểm thử | `Clock.fixed`, dependency injection, kiểm thử ranh giới | Viết test cho hàm “hôm nay” | Chạy lại cho cùng kết quả ở mọi máy/múi giờ |
| 7. Tích hợp | Thiết kế dữ liệu, lưu trữ, API và lịch hẹn | Mini-project đặt lịch qua múi giờ | Biết lưu `Instant` và giữ `ZoneId` khi nghiệp vụ cần |

### Chặng 1 — Tạo và đọc dữ liệu

- Dùng `LocalDate.of(2026, 1, 30)`, `LocalTime.of(9, 30)` và `LocalDateTime.of(date, time)` khi dữ liệu đã được xác định. `LocalDate.parse("2026-01-30")` nhận chuỗi ISO mặc định.
- Khi lấy ngày/giờ hiện tại, **truyền `Clock` hoặc `ZoneId` có chủ đích**. `LocalDate.now()` và `ZonedDateTime.now()` mặc định phụ thuộc môi trường máy, bất lợi cho ứng dụng nhiều vùng và kiểm thử.
- Hiểu các phép chuyển đổi: `LocalDate.atTime(LocalTime)` tạo `LocalDateTime`; `Instant.atZone(zone)` tạo `ZonedDateTime`; `ZonedDateTime.toInstant()` trả về mốc tuyệt đối.

**Tự kiểm:** “9 giờ sáng mai” chưa đủ để gửi lời mời họp toàn cầu nếu chưa biết địa điểm/múi giờ; trong khi “2026-07-01T12:00:00Z” đã là một `Instant` xác định.

### Chặng 2 — Cộng trừ, so sánh và tính khoảng cách

- Dùng `date.plusDays(3)`, `date.plusMonths(1)`, `date.minusWeeks(2)`, `date.withDayOfMonth(1)`; dùng `isBefore`, `isAfter`, `isEqual` hoặc `compareTo` khi so sánh.
- Ngày 30/01/2026 cộng một tháng cho **28/02/2026**, vì tháng hai năm đó không có ngày 30. Đây là phép toán theo lịch, không phải cộng một số ngày cố định.
- `Period.between(startDate, endDate)` mô tả số năm/tháng/ngày lịch; `ChronoUnit.DAYS.between(startDate, endDate)` cho số ngày nguyên giữa hai ngày; `Duration.between(startInstant, endInstant)` tính thời lượng trên dòng thời gian.
- Không dùng `Duration.ofDays(1)` để mặc định biểu diễn “ngày lịch kế tiếp” khi đi qua DST: duration này luôn bằng 24 giờ; một ngày lịch trong vùng có DST đôi khi dài 23 hoặc 25 giờ.
- Với ca làm qua nửa đêm, nên ghép `LocalTime` với ngày thành `LocalDateTime`/`ZonedDateTime` trước khi tính; `Duration.between(LocalTime.of(23, 0), LocalTime.of(1, 0))` đơn thuần ra **-22 giờ**.

**Bài tập:** tính `ChronoUnit.DAYS.between(LocalDate.of(2026, 1, 30), LocalDate.of(2026, 2, 2))`; đáp án là `3`. Thử `Period.between(...)` và quan sát cách biểu diễn khác với `Duration`.

### Chặng 3 — Parse/format dữ liệu bên ngoài

- Ưu tiên chuẩn ISO 8601 ở máy-máy: `LocalDate` → `2026-01-30`; `Instant` → `2026-07-01T12:00:00Z`. Dữ liệu dành cho người đọc có thể định dạng theo nhu cầu.
- Ví dụ `DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)`, sau đó `LocalDate.parse("31/12/2026", formatter)` và `date.format(formatter)`. Khai báo `Locale` rõ khi pattern có tên tháng/ngày bằng chữ.
- Phân biệt `MM` = tháng với `mm` = phút, `HH` = giờ 0–23 với `hh` = giờ 1–12 cần AM/PM, và `uuuu` (năm lịch proleptic) với `YYYY` (năm tính theo tuần, dễ sai cuối năm). Với parse nghiêm ngặt, `uuuu` hữu ích hơn `yyyy` (year-of-era).
- Chuỗi không hợp lệ có thể ném `DateTimeParseException`. Xác thực ở ranh giới nhập liệu, thông báo lỗi theo trường cụ thể; khi cần strict, dùng `withResolverStyle(ResolverStyle.STRICT)`.
- `DateTimeFormatter` là immutable và thread-safe; có thể dùng lại instance thay vì tạo lại ở mỗi lần gọi.

**Bài tập:** thử parse `31/02/2026` bằng formatter strict, ghi nhận exception, rồi thử `28/02/2026`. Đừng âm thầm sửa ngày không hợp lệ theo ý mình.

### Chặng 4 — Múi giờ và thời điểm thực

- Dùng tên vùng IANA như `Asia/Ho_Chi_Minh` hoặc `America/New_York`. `ZoneId.systemDefault()` chỉ nên dùng khi thật sự muốn cấu hình theo máy chạy.
- Với sự kiện đã có `Instant`: `event.atZone(zone)` đổi cách hiển thị; `event` không đổi. Với `ZonedDateTime`, `withZoneSameInstant(otherZone)` giữ cùng thời điểm; `withZoneSameLocal(otherZone)` giữ số trên đồng hồ, **có thể tạo thời điểm khác**.
- Khi nhập giờ hẹn địa phương, cần cả `LocalDateTime` **và** `ZoneId`, đồng thời kiểm tra DST trước khi quyết định cách chuyển sang `Instant`.
- Để lưu log hoặc timestamp sự kiện, sử dụng một mốc thống nhất (`Instant`/UTC). Nếu sự kiện lặp lại “09:00 thứ Hai ở New York”, cần lưu thêm múi giờ vùng và quy tắc lặp; không thể biểu diễn đúng lịch dài hạn chỉ bằng một offset hoặc chỉ bằng UTC.

### Chặng 5 — DST: giờ thiếu và giờ trùng

Quy tắc DST tùy vùng và được cập nhật bằng cơ sở dữ liệu thời gian (tzdb). Ví dụ cố định tại `America/New_York` trong năm **2026**:

- **Gap:** 08/03/2026, giờ địa phương nhảy từ 01:59:59 lên 03:00. `2026-03-08 02:30` **không tồn tại**. `LocalDateTime.atZone(zone)` mặc định đẩy thành `03:30-04:00`; nghiệp vụ đặt lịch có thể phải báo lỗi thay vì tự dời.
- **Overlap:** 01/11/2026, giờ `01:30` xảy ra **hai lần** (offset `-04:00` rồi `-05:00`). `atZone(zone)` chọn offset sớm hơn theo quy tắc mặc định; `withLaterOffsetAtOverlap()` chọn lần muộn hơn.
- Muốn tự quyết minh bạch, kiểm tra `zone.getRules().getValidOffsets(localDateTime)`: kích thước `0` = gap, `1` = bình thường, `2` = overlap. Khi đúng một offset, có thể dùng `ZonedDateTime.ofStrict(local, offset, zone)`. Khi có 0 hoặc 2, áp dụng chính sách nghiệp vụ: yêu cầu người dùng chọn, từ chối hoặc dời theo quy tắc được công bố.
- Đừng lấy mọi chênh lệch giờ địa phương rồi kết luận đó là elapsed time. Muốn tính thời gian đã trôi qua qua DST, lấy `Duration.between(start.toInstant(), end.toInstant())`.

### Chặng 6 — Kiểm thử có thể tái lập

Tách việc đọc đồng hồ khỏi nghiệp vụ:

```java
import java.time.Clock;
import java.time.LocalDate;

final class DeadlineService {
    private final Clock clock;

    DeadlineService(Clock clock) {
        this.clock = clock;
    }

    LocalDate tomorrow() {
        return LocalDate.now(clock).plusDays(1);
    }
}
```

Đây là **đoạn class để đưa vào project**, không phải chương trình chạy độc lập. Trong test, truyền `Clock.fixed(Instant.parse("2026-01-15T12:00:00Z"), ZoneOffset.UTC)`; gọi `tomorrow()` phải trả `2026-01-16`. Trong ứng dụng, truyền `Clock.system(zone)` từ cấu hình. Có thể dùng JUnit 5 để assert, nhưng ý tưởng không phụ thuộc thư viện kiểm thử.

Ngoài happy path, test ngày 29/02 của năm nhuận, cuối tháng 30/31 ngày, cuối năm, parse sai, thời điểm sát nửa đêm tại các `ZoneId` khác nhau, DST gap/overlap và thời gian đầu/cuối khoảng. Các bài kiểm thử phải truyền **ngày/giờ và vùng cụ thể**; không phụ thuộc `now()` hay múi giờ mặc định ở CI.

### Chặng 7 — Áp dụng vào ứng dụng

Khi thiết kế dữ liệu, xác định nghĩa trước khi chọn trường:

| Trường nghiệp vụ | Mô hình đề xuất | Lý do |
| --- | --- | --- |
| Ngày sinh, ngày nghỉ | `LocalDate` | Không phụ thuộc offset |
| Số giờ làm, timeout | `Duration` hoặc số giây có đơn vị rõ | Khoảng thời gian thực |
| Thời điểm tạo bản ghi | `Instant` | So sánh và sắp xếp thống nhất |
| Giờ bắt đầu cuộc họp một lần | `Instant` và `ZoneId` tùy nhu cầu hiển thị | Giữ mốc thời gian, đồng thời biết vùng tổ chức |
| Lịch mở cửa/công việc lặp ở địa phương | Ngày/giờ địa phương + `ZoneId` + luật lặp | Offset có thể thay đổi theo ngày |

Nếu dùng cơ sở dữ liệu hoặc JSON, ghi rõ semantic của từng trường: chuỗi không có offset là thời gian địa phương hay UTC? Kiểu SQL `TIMESTAMP WITH TIME ZONE` có cách hoạt động phụ thuộc hệ quản trị, không mặc định giữ được tên `ZoneId`; kiểm tra tài liệu của hệ đang dùng. Tránh chuyển đổi qua lại `Date`/`Calendar` cũ nếu API đã hỗ trợ `java.time`; nếu buộc tích hợp API cũ, đặt bước chuyển đổi ở ranh giới.

## 3. Chương trình Java 17+ tổng hợp đã kiểm tra

Ví dụ sau kết hợp ngày lịch, cộng ngày/tháng, chênh lệch ngày, hai múi giờ, `Clock.fixed` và hai trường hợp DST. Tạo tệp **`DateTimeRoadmapDemo.java`**:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class DateTimeRoadmapDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 1, 30);
        LocalDate deadline = start.plusDays(3);
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        Instant event = Instant.parse("2026-07-01T12:00:00Z");
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId ny = ZoneId.of("America/New_York");

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-15T12:00:00Z"),
                ZoneOffset.UTC
        );

        System.out.println("Cong 1 thang: " + start.plusMonths(1));
        System.out.println("Han chot: " + deadline);
        System.out.println("So ngay: " + ChronoUnit.DAYS.between(start, deadline));
        System.out.println("HCM: " + event.atZone(hcm).format(formatter));
        System.out.println("New York: " + event.atZone(ny).format(formatter));
        System.out.println("Ngay co dinh: " + LocalDate.now(fixedClock));
        System.out.println("DST gap: " +
                LocalDateTime.of(2026, 3, 8, 2, 30).atZone(ny));
        System.out.println("DST overlap som: " +
                LocalDateTime.of(2026, 11, 1, 1, 30).atZone(ny).getOffset());
        System.out.println("DST overlap muon: " +
                LocalDateTime.of(2026, 11, 1, 1, 30)
                        .atZone(ny).withLaterOffsetAtOverlap().getOffset());
    }
}
```

Biên dịch/chạy bằng terminal với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 DateTimeRoadmapDemo.java
java DateTimeRoadmapDemo
```

**Kết quả chính xác (với dữ liệu và quy tắc tzdb áp dụng cho các ngày trong ví dụ):**

```text
Cong 1 thang: 2026-02-28
Han chot: 2026-02-02
So ngay: 3
HCM: 2026-07-01 19:00 +07:00
New York: 2026-07-01 08:00 -04:00
Ngay co dinh: 2026-01-15
DST gap: 2026-03-08T03:30-04:00[America/New_York]
DST overlap som: -04:00
DST overlap muon: -05:00
```

Giải thích kết quả: 30/01 cộng một tháng được chuẩn hóa về ngày cuối tháng hai; `ChronoUnit.DAYS` trả về `3` ngày lịch; `event` được biểu diễn theo hai múi giờ mà vẫn chỉ là **một thời điểm**; đồng hồ cố định giúp test ngày hiện tại; giờ thiếu được tự dời và giờ trùng có hai offset hợp lệ. Đây cũng là lý do ứng dụng đặt lịch cần xác định chính sách DST trước khi lưu.

## 4. Bài tập tổng hợp: bộ đặt lịch họp nhiều múi giờ

Xây hàm nhận `LocalDateTime requestedLocal`, `ZoneId organizerZone`, `ZoneId attendeeZone` và trả về mốc `Instant` cùng giờ hiển thị ở hai vùng.

**Yêu cầu nghiệp vụ:**

1. Kiểm tra `organizerZone.getRules().getValidOffsets(requestedLocal)`. Nếu **0** offset, từ chối giờ không tồn tại với thông báo cụ thể. Nếu **2** offset, yêu cầu chọn “lần đầu/lần sau” để xác định đúng một thời điểm; nếu **1**, dùng offset đó.
2. Tạo `ZonedDateTime` bằng `ZonedDateTime.ofStrict(requestedLocal, selectedOffset, organizerZone)` rồi chuyển thành `Instant` để lưu.
3. Hiển thị giờ cho người tham dự bằng `instant.atZone(attendeeZone)`. Kiểm tra `instant.equals(attendeeZoned.toInstant())` phải luôn `true`.
4. Thêm `Clock` vào service khi có điều kiện kiểu “không cho đặt lịch trong quá khứ”; test bằng `Clock.fixed`, không đọc thời gian thực của máy.
5. Truyền vùng dưới dạng `ZoneId` (như `America/New_York`), không chỉ offset `-04:00`, để dự kiến lịch vào mùa đông vẫn đúng.

**Bộ ca kiểm thử tối thiểu:**

| Tình huống | Dữ liệu kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Ngày nhuận hợp lệ | `2028-02-29` | Parse và cộng ngày thành 01/03 |
| Ngày vô lý | `2026-02-29` với parse strict | Báo lỗi |
| Qua cuối năm | `2026-12-31` + 1 ngày | `2027-01-01` |
| Cuối tháng | `2026-01-30` + 1 tháng | `2026-02-28` |
| Cùng instant, khác múi giờ | `2026-07-01T12:00:00Z` ở HCM/NY | 19:00 +07:00 / 08:00 -04:00 |
| Gap New York | `2026-03-08T02:30` | 0 offset hợp lệ; không đặt lịch âm thầm |
| Overlap New York | `2026-11-01T01:30` | 2 offset hợp lệ; yêu cầu lựa chọn |
| Quy tắc “quá khứ” | Đồng hồ `2026-01-15T12:00:00Z` | Kết quả ổn định trên các máy |
| Thời lượng qua DST | Hai `Instant` quanh thời điểm đổi giờ | Tính theo giây thực, không trừ số giờ trên đồng hồ |

**Định nghĩa hoàn thành:** mọi ca kiểm thử chạy tự động; dữ liệu lưu chỉ đến đúng một mốc thời gian khi đó là cuộc họp cụ thể; luồng DST xử lý rõ ràng; việc đổi múi giờ hiển thị không thay đổi `Instant`; service có thể thay đồng hồ trong test.

## 5. Lỗi thường gặp và cách tự kiểm tra

- **Dùng `LocalDateTime` như UTC timestamp:** thiếu vùng/offset nên không thể suy ra instant duy nhất. Sử dụng `Instant` khi ghi nhận sự kiện tuyệt đối.
- **Nhầm `ZoneId` và `ZoneOffset`:** offset `+07:00` không chứa lịch sử, DST hay thay đổi pháp lý của vùng.
- **Dùng 24 giờ như 1 ngày lịch ở mọi nơi:** qua DST có thể khác; chọn `Period`/`plusDays` cho phép toán lịch và `Duration` cho thời lượng thực.
- **Quên tính immutable:** `date.plusDays(1);` không đổi `date`; phải gán `date = date.plusDays(1);`.
- **Dùng `YYYY` để format năm thông thường:** `YYYY` là week-based year; dùng `uuuu` cho năm ISO theo lịch trong pattern ví dụ.
- **Để múi giờ hệ thống lọt vào test:** kết quả khác nhau giữa laptop và CI; truyền `Clock.fixed` và `ZoneId` tường minh.
- **Nhập ngày tháng không xác thực:** formatter mặc định có thể áp dụng resolver style `SMART`; dùng `STRICT` khi nghiệp vụ đòi khước từ ngày sai.
- **Chỉ kiểm happy path:** dễ hỏng ở 29/02, qua nửa đêm, cuối tháng, gap/overlap; đưa ranh giới thành test cố định.

## 6. Checklist sau lộ trình

- [ ] Phân loại được đầu vào thành `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant` hoặc `ZonedDateTime` trước khi viết code.
- [ ] Tính được ngày lịch và duration; giải thích được khác biệt giữa `Period` và `Duration`.
- [ ] Parse/format ISO và pattern tùy chỉnh có `Locale`/strict validation.
- [ ] Chuyển một `Instant` sang hai vùng bằng `ZoneId` mà không đổi thời điểm.
- [ ] Nhận diện DST gap/overlap và đưa ra quy tắc nghiệp vụ công khai.
- [ ] Test phần phụ thuộc “bây giờ” bằng `Clock.fixed`; kiểm thử các mốc ranh giới.
- [ ] Thiết kế dữ liệu lưu trữ phù hợp cho ngày lịch, sự kiện tuyệt đối và lịch lặp theo vùng.

Tài liệu tra cứu chuẩn của JDK 17: [`java.time` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html), [`ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html), [`Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) và [`DateTimeFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).