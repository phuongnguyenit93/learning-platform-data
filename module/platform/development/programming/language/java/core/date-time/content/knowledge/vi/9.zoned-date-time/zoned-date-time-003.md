# Giờ bị bỏ qua khi chuyển sang giờ mùa hè (DST gap) trong `ZonedDateTime`

## 1. Vấn đề: vì sao có một giờ địa phương không tồn tại?

Khi một khu vực bắt đầu áp dụng **giờ mùa hè (Daylight Saving Time – DST)**, đồng hồ có thể được chỉnh **tiến lên**. Ví dụ, tại `America/New_York` ngày **10/03/2024**, đồng hồ nhảy từ **01:59:59 (UTC−05:00)** đến **03:00:00 (UTC−04:00)**. Theo quy tắc múi giờ của khu vực này, mọi thời điểm địa phương từ `2024-03-10T02:00` đến trước `03:00` **không hề diễn ra**.

Khoảng thời gian địa phương không hợp lệ này gọi là **gap** (khoảng bị bỏ qua). Nó không phải là một khoảng thời gian mà thế giới ngừng trôi: các `Instant` (mốc tuyệt đối trên dòng thời gian UTC) vẫn liên tục. Chỉ có cách hiển thị giờ theo đồng hồ địa phương bị nhảy.

| Biểu diễn ở New York | UTC tương ứng | Nhận xét |
| --- | --- | --- |
| `2024-03-10T01:59:59-05:00` | `2024-03-10T06:59:59Z` | Giây cuối trước khi đổi giờ |
| `2024-03-10T02:30` | **Không có** | Giờ địa phương rơi vào gap |
| `2024-03-10T03:00:00-04:00` | `2024-03-10T07:00:00Z` | Thời điểm đầu tiên sau khi đổi giờ |

Đừng suy luận rằng DST luôn bắt đầu lúc 02:00, gap luôn dài đúng một giờ hoặc quốc gia nào cũng áp dụng DST. Ngày, giờ, độ dài và thậm chí việc có đổi giờ hay không đều phụ thuộc **`ZoneId` và quy tắc lịch sử** trong cơ sở dữ liệu múi giờ (tzdb) của môi trường Java.

## 2. Phân biệt ba kiểu thời gian trước khi xử lý gap

- **`LocalDateTime`** chỉ chứa ngày và giờ theo đồng hồ (ví dụ `2024-03-10T02:30`), **không có múi giờ hoặc UTC offset**. Giá trị này có thể tạo thành công dù không tồn tại trong một múi giờ cụ thể.
- **`ZoneId`** như `America/New_York` mang bộ quy tắc xác định UTC offset theo từng ngày trong lịch sử/tương lai. `ZoneOffset` như `-05:00` chỉ là một độ lệch cố định, không mô tả đầy đủ việc đổi giờ.
- **`ZonedDateTime`** kết hợp ngày giờ địa phương, `ZoneId` và offset hợp lệ để xác định một `Instant`. Khi được tạo từ một `LocalDateTime` rơi vào gap, các API xây dựng thông thường sẽ **điều chỉnh giờ địa phương tiến thêm đúng độ dài của gap**.

Vì vậy, `LocalDateTime.of(2024, 3, 10, 2, 30)` là hợp lệ về mặt cấu trúc, nhưng **không phải một thời điểm hợp lệ tại** `America/New_York` trong ngày đó.

## 3. Java tự xử lý giờ bị bỏ qua như thế nào?

Với `LocalDateTime.atZone(zone)` hoặc `ZonedDateTime.of(localDateTime, zone)`, Java áp dụng quy tắc:

1. Nếu thời điểm địa phương có **một offset hợp lệ**, dùng offset đó.
2. Nếu thời điểm địa phương nằm trong **gap** (không có offset hợp lệ), dịch `LocalDateTime` **về phía trước một khoảng bằng độ dài gap**, rồi dùng offset **sau** chuyển đổi.
3. Nếu có **hai offset hợp lệ** (overlap khi đồng hồ lùi), đó là tình huống khác với gap; mặc định Java thường chọn offset sớm hơn nếu không có offset ưu tiên hợp lệ.

Tại New York, `2024-03-10T02:30` sẽ được chuẩn hóa thành **`2024-03-10T03:30-04:00[America/New_York]`**. Đây là **chính sách mặc định của API**, không nhất thiết là chính sách phù hợp với mọi nghiệp vụ (ví dụ đặt lịch khám, giờ mở cửa, lệnh giao dịch).

## 4. Ví dụ Java 17+ chạy độc lập: phát hiện và quan sát gap

Lưu mã dưới đây vào `DstGapDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstGapDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime requested = LocalDateTime.of(2024, 3, 10, 2, 30);
        ZoneRules rules = zone.getRules();

        List<ZoneOffset> offsets = rules.getValidOffsets(requested);
        ZoneOffsetTransition transition = rules.getTransition(requested);

        System.out.println("Valid offsets: " + offsets);
        System.out.println("Is gap: " + transition.isGap());
        System.out.println("Before: " + transition.getDateTimeBefore()
                + " " + transition.getOffsetBefore());
        System.out.println("After: " + transition.getDateTimeAfter()
                + " " + transition.getOffsetAfter());
        System.out.println("Gap duration: " + transition.getDuration());

        ZonedDateTime adjusted = requested.atZone(zone);
        System.out.println("atZone: " + adjusted);
        System.out.println("Instant: " + adjusted.toInstant());

        try {
            ZonedDateTime.ofStrict(requested, transition.getOffsetBefore(), zone);
            System.out.println("ofStrict: accepted");
        } catch (DateTimeException ex) {
            System.out.println("ofStrict: rejected invalid local time");
        }

        ZonedDateTime fromUtc = ZonedDateTime.ofInstant(
                Instant.parse("2024-03-10T07:30:00Z"), zone);
        System.out.println("From UTC: " + fromUtc);
    }
}
```

Biên dịch và chạy:

```bash
javac DstGapDemo.java
java DstGapDemo
```

Đầu ra (theo quy tắc tzdb cho `America/New_York` ngày 10/03/2024):

```text
Valid offsets: []
Is gap: true
Before: 2024-03-10T02:00 -05:00
After: 2024-03-10T03:00 -04:00
Gap duration: PT1H
atZone: 2024-03-10T03:30-04:00[America/New_York]
Instant: 2024-03-10T07:30:00Z
ofStrict: rejected invalid local time
From UTC: 2024-03-10T03:30-04:00[America/New_York]
```

Điểm cần hiểu: `getValidOffsets(requested)` trả về danh sách **rỗng** vì không có offset nào làm cho `02:30` là thời điểm địa phương thực sự xảy ra tại New York. `atZone` không báo lỗi mà điều chỉnh lên `03:30`. Ngược lại, `ofStrict` yêu cầu cặp **giờ địa phương + offset** phải thực sự hợp lệ cho `ZoneId` nên ném `DateTimeException` khi gặp gap. Trong ví dụ, ngoại lệ được bắt để chương trình chạy hết.

## 5. API phát hiện và xử lý chuyển đổi DST

`ZoneRules` là điểm vào chính khi ứng dụng cần **kiểm soát nghiệp vụ** trước khi chuyển `LocalDateTime` thành `ZonedDateTime`.

| API | Khi dùng với `LocalDateTime` trong gap |
| --- | --- |
| `zone.getRules().getValidOffsets(local)` | Trả `[]`; số phần tử 0 = gap, 1 = bình thường, 2 = overlap |
| `zone.getRules().getTransition(local)` | Trả `ZoneOffsetTransition` chứa chi tiết lần chuyển đổi; kiểm tra `isGap()` |
| `transition.getDuration()` | Khoảng đồng hồ nhảy tiến, chẳng hạn `PT1H` |
| `transition.getDateTimeBefore()` / `getDateTimeAfter()` | Hai mốc trên đồng hồ ở biên chuyển đổi (ở đây là `02:00` và `03:00`) |
| `local.atZone(zone)` | Tự dịch giờ địa phương trong gap về sau |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Ném `DateTimeException` nếu offset không hợp lệ cho ngày giờ địa phương đó |
| `ZonedDateTime.ofInstant(instant, zone)` | Chuyển một mốc UTC đã xác định sang múi giờ; không phát sinh giờ địa phương không tồn tại |

Một cách kiểm tra tổng quát trước khi tạo lịch:

```java
// Đoạn minh họa dùng các biến LocalDateTime local và ZoneId zone có sẵn.
List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);
if (validOffsets.isEmpty()) {
    // Gap: hỏi người dùng hoặc áp dụng chính sách lịch đã công bố.
} else if (validOffsets.size() == 2) {
    // Overlap: cần phân biệt lần xuất hiện sớm/muộn của cùng giờ địa phương.
} else {
    // Thời điểm địa phương xác định duy nhất một offset.
}
```

Để tránh nhầm lẫn: `getTransition(local)` thường trả `null` nếu thời điểm không thuộc một transition. Hãy kiểm tra `transition != null && transition.isGap()` trước khi sử dụng nó trong code tổng quát. Ví dụ chạy độc lập ở trên đã cố ý chọn thời điểm **biết chắc nằm trong gap**.

## 6. Chọn chính sách nghiệp vụ trước khi lưu lịch

Java mặc định dịch `02:30` thành `03:30`; nghiệp vụ cần xác định rõ đây có phải điều mong muốn hay không. Một số chính sách hợp lý:

| Chính sách | Với yêu cầu 02:30 trong gap 02:00–03:00 | Tình huống |
| --- | --- | --- |
| **Từ chối / yêu cầu chọn lại** | Báo “02:30 không tồn tại tại khu vực/ngày đã chọn” | Đặt vé, thanh toán, lịch hẹn yêu cầu xác nhận |
| **Dịch theo độ dài gap** | Đặt thành 03:30 | Mong muốn duy trì số phút trong giờ và chấp nhận dời lịch |
| **Chuyển đến thời điểm hợp lệ đầu tiên** | Đặt thành 03:00 | Chạy tác vụ càng sớm càng tốt sau gap |
| **Bỏ lần chạy trong ngày** | Không kích hoạt lần chạy đó | Lịch định kỳ có quy tắc bỏ kỳ không hợp lệ |

Sau khi xác nhận gap, để lấy **thời điểm địa phương hợp lệ đầu tiên**, có thể dùng `transition.getDateTimeAfter().atZone(zone)`. Nó khác với `local.atZone(zone)`: đầu vào `02:30` tạo **03:00** theo chính sách “đầu tiên” nhưng tạo **03:30** theo chính sách “dịch nguyên gap”.

Ví dụ một hàm từ chối giờ không tồn tại:

```java
// Đoạn minh họa; đặt trong lớp và import java.time.*.
static ZonedDateTime rejectDstGap(LocalDateTime local, ZoneId zone) {
    if (zone.getRules().getValidOffsets(local).isEmpty()) {
        throw new IllegalArgumentException(
                "Thoi diem dia phuong khong ton tai trong mui gio da chon");
    }
    return local.atZone(zone);
}
```

Hàm này chỉ giải quyết **gap**; nếu nghiệp vụ cần phân biệt hai lần xuất hiện của cùng giờ trong **overlap**, phải xử lý thêm trường hợp `getValidOffsets(local).size() == 2`.

## 7. Cộng thời gian qua gap: thời lượng thực và giờ trên đồng hồ khác nhau

Giả sử tại New York, bạn bắt đầu ở `2024-03-10T01:30-05:00`. Qua lúc chuyển DST:

- **Cộng 1 giờ theo dòng thời gian** (`zoned.plusHours(1)`) đến **03:30-04:00**; thời gian thực trôi qua đúng 60 phút, dù đồng hồ hiển thị tăng hai giờ.
- **Cộng 1 giờ vào `LocalDateTime`** (`local.plusHours(1)`) cho **02:30**, nhưng giờ này **không tồn tại** tại New York; gắn `ZoneId` sau đó sẽ được đẩy lên **03:30**.
- **`Duration.between(start, end)`** trên hai `ZonedDateTime` phản ánh khoảng cách trên dòng thời gian thực. Trong ví dụ từ 01:30-05:00 đến 03:30-04:00, kết quả là **`PT1H`**, không phải hai giờ.

Dù một ví dụ có thể cho cùng kết quả cuối cùng, **quy tắc cộng trên `Instant`, `LocalDateTime` và lịch theo ngày** khác nhau; không suy ra tính tương đương tổng quát. Đặc biệt, `plusDays(1)` trên `ZonedDateTime` theo **ngày địa phương** và có thể tạo khoảng cách thực 23 hoặc 25 giờ gần DST, còn `plusHours(24)` là 24 giờ trên dòng thời gian.

Một lịch “mỗi ngày lúc 02:30 theo giờ New York” vì vậy không thể triển khai chính xác bằng cách cứ cộng `Duration.ofHours(24)` vào `Instant`: giờ địa phương sẽ lệch khi quy tắc offset thay đổi. Hãy lưu **`LocalTime` + `ZoneId` + chính sách gap/overlap**, tính lại từng ngày.

## 8. Chuyển múi giờ đúng mục đích

Hai API của `ZonedDateTime` rất dễ bị nhầm:

- **`withZoneSameInstant(otherZone)`** giữ nguyên mốc UTC, nên giờ đồng hồ địa phương thay đổi theo múi giờ đích; phù hợp khi hiển thị một sự kiện đã xác định.
- **`withZoneSameLocal(otherZone)`** cố giữ nguyên ngày giờ đồng hồ; khi giờ đó rơi vào gap ở múi giờ đích, Java có thể điều chỉnh tiến. Mốc UTC do đó thường thay đổi; phù hợp chỉ khi bạn chủ ý diễn giải một giờ địa phương trong khu vực mới.

Không sửa chuỗi giờ bằng cách thay `-05:00` thành `-04:00` hoặc dùng offset cố định cho toàn năm. Điều đó có thể thay đổi mốc thời gian thực và bỏ qua lịch sử chuyển đổi của `ZoneId`.

## 9. Lưu dữ liệu và thiết kế hệ thống

1. **Lịch hẹn do người dùng nhập:** nhận `LocalDate`, `LocalTime` và `ZoneId` IANA; kiểm tra offset hợp lệ **trước** khi chốt thời điểm. Ghi rõ chính sách nếu gặp gap, không âm thầm dịch giờ trong nghiệp vụ cần giờ chính xác.
2. **Sự kiện đã xảy ra:** lưu `Instant`/timestamp UTC để so sánh, đồng thời lưu `ZoneId` nếu cần tái tạo bối cảnh giờ địa phương. Chỉ lưu `LocalDateTime` dễ khiến mất thông tin múi giờ và không xác định được một mốc UTC duy nhất.
3. **Công việc lặp lại:** lưu quy tắc theo giờ địa phương, `ZoneId` và cách xử lý gap/overlap; mỗi lần chạy tính `Instant` tương ứng với ngày mục tiêu bằng `ZoneRules`.
4. **Kiểm thử:** dùng ngày chuyển DST có quy tắc được xác định trước (như `2024-03-10` cho New York), không dùng `ZoneId.systemDefault()` hay `LocalDateTime.now()` cho ca kiểm thử quyết định.
5. **Vận hành:** quy tắc múi giờ do tzdb cung cấp có thể được cập nhật do thay đổi pháp luật. Cập nhật JDK/tzdb và kiểm tra lại việc lập lịch dài hạn; tuyệt đối không giả định mọi vùng luôn đổi giờ vào cùng ngày.

## 10. Các lỗi phổ biến và cách tránh

- **Nhầm `LocalDateTime` hợp lệ về cú pháp với thời điểm địa phương có thật.** Luôn kiểm tra `ZoneRules.getValidOffsets(local)` khi đầu vào là giờ tường của người dùng và ứng dụng yêu cầu xác nhận tính hợp lệ.
- **Tin rằng `atZone` sẽ ném lỗi khi gặp gap.** API này thường **tự điều chỉnh tiến**; dùng `getValidOffsets` hoặc `ofStrict` khi muốn phát hiện/từ chối.
- **Dùng `ZoneOffset` cố định thay cho `ZoneId`.** Offset không lưu quy tắc DST; một giờ như `02:30-05:00` có thể là mốc UTC hợp lệ dưới dạng `OffsetDateTime` nhưng **không phải** thời điểm địa phương hợp lệ tại New York ngày 10/03/2024.
- **Dùng `plusHours(24)` để lập lịch hằng ngày.** Nó bảo toàn 24 giờ thực, không đảm bảo cùng giờ đồng hồ mỗi ngày.
- **Nhầm gap với overlap.** Gap có **0 offset hợp lệ** (giờ không xảy ra); overlap có **2 offset hợp lệ** (giờ xảy ra hai lần). Hai tình huống cần chính sách khác nhau.
- **Bỏ qua thay đổi tzdb.** Các quy tắc DST mang tính khu vực và thời kỳ; ví dụ lịch sử đúng phải dựa trên vùng/ngày cụ thể.

## 11. Tự kiểm tra kiến thức

**Tình huống A.** Người dùng chọn `2024-03-10 02:45` tại New York. `LocalDateTime.atZone(ZoneId.of("America/New_York"))` cho kết quả nào?

**Đáp án:** `2024-03-10T03:45-04:00[America/New_York]`. Thời điểm 02:45 nằm trong gap dài một giờ nên Java dịch thành 03:45.

**Tình huống B.** `ZoneRules.getValidOffsets(...)` trả `[]`. Bạn có thể sửa bằng cách chọn offset `-05:00` thủ công rồi gọi `ofStrict` không?

**Đáp án:** Không. Không có offset hợp lệ cho **giờ địa phương đó trong ZoneId đó**. `ofStrict` từ chối; ứng dụng cần chọn chính sách với giờ bị bỏ qua.

**Tình huống C.** Có một sự kiện được ghi bằng `Instant`. Khi đổi sang `America/New_York`, liệu kết quả có thể là `2024-03-10T02:30` ở ngày đổi DST nêu trên không?

**Đáp án:** Không. Mọi `Instant` ánh xạ đến một giờ địa phương hợp lệ theo quy tắc vùng; `02:30` ngày đó không tồn tại ở New York.

**Ghi nhớ:** Với `ZonedDateTime`, gap phát sinh khi **đồng hồ địa phương nhảy tiến**. `LocalDateTime` trong gap có 0 offset hợp lệ, `atZone` thường đẩy nó về sau, còn ứng dụng nghiệp vụ phải chủ động quyết định **từ chối, dời lịch hay bỏ lần chạy**.