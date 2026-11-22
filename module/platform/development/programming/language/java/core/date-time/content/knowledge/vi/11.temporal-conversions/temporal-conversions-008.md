# atStartOfDay(ZoneId) và thời điểm bắt đầu ngày hợp lệ trong Java

`LocalDate.atStartOfDay(ZoneId)` trả về **thời điểm bắt đầu ngày hợp lệ sớm nhất theo quy tắc của một vùng thời gian** dưới dạng `ZonedDateTime`. Đây là phương thức quan trọng khi chuyển **ngày lịch** thành **một mốc thời gian thực**, ví dụ ranh giới tìm kiếm dữ liệu trong ngày, báo cáo doanh thu theo địa phương, thời điểm bắt đầu kỳ thanh toán hoặc giới hạn hiệu lực.

Trực giác “đầu ngày = 00:00” thường đúng, nhưng **không luôn đúng**. Tại những vùng có thay đổi UTC offset ngay lúc nửa đêm, `00:00` có thể không tồn tại; tại những lần điều chỉnh lớn của đường đổi ngày, **cả một ngày lịch có thể bị bỏ qua**. `atStartOfDay(zone)` xử lý theo các quy tắc được nạp trong `ZoneRules`, thay vì đơn thuần ghép số 00:00 vào ngày.

Bài học tập trung vào câu hỏi: **Khi đã có `LocalDate`, làm sao tìm mốc `Instant` bắt đầu ngày theo một `ZoneId` và hiểu đúng hành vi ở gap/overlap?**

## 1. Phân biệt ngày lịch, nửa đêm địa phương và một thời điểm tuyệt đối

Xét ba khái niệm:

- **`LocalDate`:** một ngày lịch ISO như `2024-03-10`; bản thân nó không có giờ, offset hay `Instant`.
- **`LocalDateTime`:** ngày và giờ địa phương như `2024-03-10T00:00`; vẫn không có offset/zone. Một local time có thể hợp lệ hoặc không hợp lệ trong vùng cụ thể.
- **`ZonedDateTime` / `Instant`:** sau khi áp luật vùng và quyết định offset, ta có thời điểm trên timeline.

Ví dụ, `2024-03-10` ở Việt Nam và New York là cùng ký hiệu ngày nhưng **bắt đầu tại các Instant khác nhau**. Do đó, không có “đầu ngày toàn cầu” cho một ngày địa phương nếu không nêu `ZoneId`.

### Hai overload trông giống nhau nhưng khác ý nghĩa

| Lệnh | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `date.atStartOfDay()` | `LocalDateTime` | Ghép ngày với local time `00:00`, **không áp quy tắc múi giờ**. |
| `date.atStartOfDay(zone)` | `ZonedDateTime` | Tìm thời điểm bắt đầu ngày **hợp lệ sớm nhất** theo luật `ZoneId`. |
| `date.atStartOfDay(zone).toInstant()` | `Instant` | Chuyển đầu ngày đã giải quyết về mốc tuyệt đối. |

Điều quan trọng: `date.atStartOfDay()` **không kiểm tra** rằng `00:00` có thật trong vùng nào đó. Không nên dùng nó như một timestamp tuyệt đối; muốn làm vậy phải chọn đúng vùng hoặc offset và xử lý sự nhập nhằng.

Ví dụ minh họa (cần import `java.time` và đặt trong phương thức):

~~~java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

LocalDateTime midnight = date.atStartOfDay();
ZonedDateTime firstValid = date.atStartOfDay(zone);
Instant dayStartInstant = firstValid.toInstant();
~~~

Ở New York ngày này, nửa đêm vẫn hợp lệ với offset `-05:00`; DST bắt đầu lúc 02:00. Vì vậy `firstValid` là `2024-03-10T00:00-05:00[America/New_York]` và `dayStartInstant` là `2024-03-10T05:00:00Z`.

## 2. Quy tắc chính xác của atStartOfDay(zone)

Với mỗi `LocalDate`, Java xem các quy tắc của `ZoneId` tại ranh giới ngày.

1. **Trường hợp thông thường:** local `00:00` hợp lệ với một offset; kết quả bắt đầu tại 00:00.
2. **Gap chứa nửa đêm:** `00:00` và có thể một đoạn đầu ngày bị đồng hồ nhảy qua. Java chọn **giờ hợp lệ sớm nhất sau gap**, chẳng hạn `01:00`, chứ không trả giờ 00:00 không tồn tại.
3. **Overlap chứa nửa đêm:** `00:00` xuất hiện hai lần với hai offset. Java chọn **offset sớm hơn theo thứ tự xuất hiện trên dòng thời gian** (offset trước chuyển đổi), để lấy mốc hợp lệ đầu tiên.
4. **Ngày bị bỏ qua hoàn toàn:** có vùng từng đổi offset đủ lớn để không xuất hiện một ngày lịch. Phương thức có thể trả thời điểm đầu ngày hợp lệ **tiếp theo**, và `toLocalDate()` của kết quả có thể **khác `date` được yêu cầu**.

Quy tắc này nói về **đầu ngày theo lịch ở một vùng**, không phải phép cộng một lượng giây cố định vào `1970-01-01T00:00Z`. Cơ sở dữ liệu múi giờ (TZDB) gắn với JDK/môi trường chạy chứa lịch sử và quy tắc dự kiến. Chính sách múi giờ có thể thay đổi; lịch tương lai cần được kiểm tra khi cập nhật TZDB.

### ZoneId khác ZoneOffset

`ZoneId.of("America/New_York")` đại diện cho vùng có quy tắc thay đổi giữa `-05:00` và `-04:00` ở các giai đoạn khác nhau. `ZoneOffset.ofHours(-5)` chỉ là một offset cố định; nó **không tự chuyển DST**.

Nếu người dùng hỏi đầu ngày của **một thành phố/vùng**, ưu tiên một IANA `ZoneId`. Nếu nghiệp vụ thật sự dùng offset cố định, có thể dùng `ZoneOffset`, nhưng đừng suy luận offset hiện tại là hợp lệ cho mọi ngày quá khứ và tương lai.

## 3. Ví dụ bình thường: đầu ngày ở Việt Nam

Với `Asia/Ho_Chi_Minh` và một ngày thông thường trong năm 2024:

~~~java
LocalDate date = LocalDate.of(2024, 6, 1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime start = date.atStartOfDay(zone);
Instant utc = start.toInstant();
~~~

Đây là mã minh họa, không phải chương trình độc lập. Kết quả:

~~~text
start = 2024-06-01T00:00+07:00[Asia/Ho_Chi_Minh]
utc   = 2024-05-31T17:00:00Z
~~~

Nửa đêm địa phương ngày 01/06 tương ứng **17:00 UTC của ngày trước đó**. Đây là lý do “lấy ngày + `00:00Z`” không phải cách xác định đầu ngày Việt Nam.

Việt Nam hiện không dùng thay đổi DST theo mùa, nhưng điều đó không cho phép loại bỏ `ZoneId` trong phần mềm nhiều khu vực hoặc giả định luật lịch sử không bao giờ khác.

## 4. Gap ngay nửa đêm: ngày bắt đầu tại 01:00

Một ví dụ lịch sử minh họa rõ chính sách này là `America/Sao_Paulo` vào **04/11/2018**. Theo quy tắc thời gian địa phương khi đó, đồng hồ nhảy ngay tại mốc nửa đêm từ cuối ngày trước sang **01:00** đầu ngày mới.

~~~text
America/Sao_Paulo — chuyển sang DST ngày 2018-11-04

2018-11-03 23:59:59 (-03:00)
            ↓ một giây thực
2018-11-04 01:00:00 (-02:00)

00:00 đến 00:59:59... ngày 04/11 không tồn tại.
~~~

Do đó:

~~~java
LocalDate date = LocalDate.of(2018, 11, 4);
ZoneId saoPaulo = ZoneId.of("America/Sao_Paulo");
ZonedDateTime start = date.atStartOfDay(saoPaulo);
~~~

Đoạn mã minh họa. Kết quả dự kiến với TZDB chứa quy tắc lịch sử trên:

~~~text
2018-11-04T01:00-02:00[America/Sao_Paulo]
~~~

Giải thích:

- `date.atStartOfDay()` không tham số chỉ tạo `2018-11-04T00:00`, một `LocalDateTime` chưa gắn vùng.
- `date.atStartOfDay(saoPaulo)` biết rằng 00:00 thuộc gap và trả **01:00 hợp lệ đầu tiên**.
- `start.toInstant()` là `2018-11-04T03:00:00Z`.
- Không có mốc thời gian thật ở `2018-11-04T00:00` theo giờ São Paulo vào ngày này.

**Không nên cộng 1 giờ thủ công** như một thuật toán tổng quát. Gap có thể không dài đúng một giờ và có thể xuất hiện ở thời điểm khác. Hãy để `ZoneRules` giải quyết hoặc truy vấn transition nếu cần giải thích chi tiết.

## 5. Một ngày 23 hoặc 25 giờ vẫn có thể bắt đầu lúc 00:00

Không phải ngày đổi DST nào cũng có gap tại nửa đêm. New York năm 2024 bắt đầu DST lúc 02:00, nên ngày **10/03/2024** vẫn bắt đầu ở `00:00-05:00`, nhưng **ngày tiếp theo** bắt đầu ở `00:00-04:00`.

~~~text
2024-03-10 00:00 -05:00 -> 2024-03-10T05:00Z
2024-03-11 00:00 -04:00 -> 2024-03-11T04:00Z
Khoảng đã trôi qua: 23 giờ.
~~~

Tương tự, ngày New York **03/11/2024** kết thúc DST và kéo dài 25 giờ thực:

~~~text
2024-11-03 00:00 -04:00 -> 2024-11-03T04:00Z
2024-11-04 00:00 -05:00 -> 2024-11-04T05:00Z
Khoảng đã trôi qua: 25 giờ.
~~~

Vì vậy:

- **Bắt đầu ngày** là bài toán tìm ranh giới địa phương hợp lệ.
- **Độ dài của ngày lịch** là khoảng `Duration.between(start, nextStart)` giữa **hai ranh giới đã áp quy tắc vùng**.
- Không lấy `start.plus(Duration.ofHours(24))` làm đầu ngày tiếp theo nếu nghiệp vụ yêu cầu **ngày lịch của vùng**.

`Duration.ofDays(1)` trong Java cũng là 86.400 giây, khác ý nghĩa “dịch sang ngày lịch kế tiếp” khi offset vùng biến đổi.

## 6. Ví dụ Java 17+ độc lập: so sánh ranh giới ngày

Tạo tệp `DayStartDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DayStartDemo {
    static void show(LocalDate date, String zoneName) {
        ZoneId zone = ZoneId.of(zoneName);
        ZonedDateTime start = date.atStartOfDay(zone);
        ZonedDateTime next = date.plusDays(1).atStartOfDay(zone);
        long elapsedHours = Duration.between(start, next).toHours();

        System.out.println("Zone: " + zoneName);
        System.out.println("Date: " + date);
        System.out.println("Start: " + start);
        System.out.println("Next: " + next);
        System.out.println("Start instant: " + start.toInstant());
        System.out.println("Elapsed hours: " + elapsedHours);
    }

    public static void main(String[] args) {
        show(LocalDate.of(2024, 6, 1), "Asia/Ho_Chi_Minh");
        show(LocalDate.of(2024, 3, 10), "America/New_York");
        show(LocalDate.of(2024, 11, 3), "America/New_York");
        show(LocalDate.of(2018, 11, 4), "America/Sao_Paulo");
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac DayStartDemo.java
java DayStartDemo
~~~

Stdout cho các quy tắc lịch sử được TZDB hỗ trợ:

~~~text
Zone: Asia/Ho_Chi_Minh
Date: 2024-06-01
Start: 2024-06-01T00:00+07:00[Asia/Ho_Chi_Minh]
Next: 2024-06-02T00:00+07:00[Asia/Ho_Chi_Minh]
Start instant: 2024-05-31T17:00:00Z
Elapsed hours: 24
Zone: America/New_York
Date: 2024-03-10
Start: 2024-03-10T00:00-05:00[America/New_York]
Next: 2024-03-11T00:00-04:00[America/New_York]
Start instant: 2024-03-10T05:00:00Z
Elapsed hours: 23
Zone: America/New_York
Date: 2024-11-03
Start: 2024-11-03T00:00-04:00[America/New_York]
Next: 2024-11-04T00:00-05:00[America/New_York]
Start instant: 2024-11-03T04:00:00Z
Elapsed hours: 25
Zone: America/Sao_Paulo
Date: 2018-11-04
Start: 2018-11-04T01:00-02:00[America/Sao_Paulo]
Next: 2018-11-05T00:00-02:00[America/Sao_Paulo]
Start instant: 2018-11-04T03:00:00Z
Elapsed hours: 23
~~~

**Đọc kết quả:** trong cùng một chương trình, có ngày đầu tiên hợp lệ là 00:00, có ngày là 01:00; khoảng giữa các mốc đầu ngày có thể 23, 24 hoặc 25 giờ. Đây là hành vi mong đợi theo vùng, không phải lỗi làm tròn.

## 7. Overlap ngay nửa đêm: lấy lần xuất hiện đầu tiên

Gap là trường hợp giờ đầu ngày bị mất. Chiều ngược lại, một số vùng có thể **lặp lại giờ 00:00** khi đồng hồ lùi.

Trong **overlap**, một `LocalDateTime` có thể tương ứng hai offset và hai `Instant`. `date.atStartOfDay(zone)` chọn **mốc hợp lệ sớm nhất** — tương ứng lần xuất hiện đầu tiên của giờ mở đầu ngày, thường dùng offset **trước** chuyển đổi.

Có thể kiểm tra offset hợp lệ của nửa đêm:

~~~java
LocalDate date = LocalDate.of(2020, 11, 1);
ZoneId zone = ZoneId.of("America/Havana");
LocalDateTime midnight = date.atStartOfDay();

List<ZoneOffset> offsets = zone.getRules().getValidOffsets(midnight);
ZonedDateTime start = date.atStartOfDay(zone);
~~~

Đây là **mã minh họa** (cần import `java.time.*` và `java.util.List`). Một ví dụ lịch sử là vùng `America/Havana` kết thúc DST vào ngày này với giờ đầu ngày lặp lại. Nếu hai offset hợp lệ là `-04:00` và `-05:00`, `atStartOfDay(zone)` chọn lần nửa đêm đầu tiên mang `-04:00`.

**Tại sao phải quan tâm?** Nếu chọn nhầm offset sau chuyển đổi, bạn đã bỏ qua những sự kiện xảy ra trong **lượt đầu** của giờ lặp. Với báo cáo theo ngày, bắt đầu ngày phải bao gồm mọi thời điểm hợp lệ thuộc ngày đó.

`ZoneRules.getValidOffsets(midnight)` cho phép biết nửa đêm có 0, 1 hay 2 offset. Đừng tự đoán offset sớm bằng cách lấy số âm nhỏ hơn: `-04:00` và `-05:00` có thứ tự số học khác với thứ tự thời gian xuất hiện.

Nếu ứng dụng cần một **lịch hẹn cụ thể** đúng lúc 00:15 trong overlap, ý định đó không nhất thiết giống yêu cầu “đầu ngày”; khi đặt hẹn, có thể cần người dùng chọn lượt đầu/lượt sau thay vì áp mặc định.

## 8. Trường hợp đặc biệt: cả một ngày lịch bị bỏ qua

Không phải mọi thay đổi vùng đều chỉ cộng/trừ một giờ. `Pacific/Apia` đổi phía đường đổi ngày quốc tế vào cuối năm 2011; địa phương **bỏ qua ngày 30/12/2011**.

Theo quy tắc TZDB cho giai đoạn đó, khi hỏi:

~~~java
ZoneId zone = ZoneId.of("Pacific/Apia");
LocalDate skipped = LocalDate.of(2011, 12, 30);
ZonedDateTime start = skipped.atStartOfDay(zone);
ZonedDateTime next = skipped.plusDays(1).atStartOfDay(zone);
~~~

Đây là mã minh họa, không phải chương trình độc lập. Kết quả nổi bật:

~~~text
start = 2011-12-31T00:00+14:00[Pacific/Apia]
next  = 2011-12-31T00:00+14:00[Pacific/Apia]
~~~

**Kết quả `start.toLocalDate()` là 31/12/2011**, không phải ngày 30/12 được hỏi. Đầu ngày được yêu cầu **không có trong lịch dân sự vùng đó**; Java trả mốc hợp lệ đầu tiên sau khoảng chuyển đổi. Hai ranh giới `start` và `next` cùng một `Instant`, nên phạm vi của ngày bị bỏ qua có độ dài **0 giây**.

Điều này có hai hệ quả:

1. **Không nên khẳng định** mọi `date.atStartOfDay(zone)` đều trả một `ZonedDateTime` mang chính ngày `date`.
2. Khi dữ liệu nghiệp vụ đòi hỏi ngày đó phải thật sự tồn tại (ví dụ ngày phục vụ hoặc ngày giao hàng), phải kiểm tra `start.toLocalDate().equals(date)` và áp quy tắc xử lý đặc biệt nếu sai.

### Ví dụ Java độc lập: phát hiện ngày bị bỏ qua

Lưu `SkippedDayDemo.java`:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class SkippedDayDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Pacific/Apia");
        LocalDate requested = LocalDate.of(2011, 12, 30);

        ZonedDateTime start = requested.atStartOfDay(zone);
        ZonedDateTime end = requested.plusDays(1).atStartOfDay(zone);

        System.out.println("Requested: " + requested);
        System.out.println("Start: " + start);
        System.out.println("End: " + end);
        System.out.println("Date preserved: "
                + start.toLocalDate().equals(requested));
        System.out.println("Hours: "
                + Duration.between(start, end).toHours());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SkippedDayDemo.java
java SkippedDayDemo
~~~

Stdout:

~~~text
Requested: 2011-12-30
Start: 2011-12-31T00:00+14:00[Pacific/Apia]
End: 2011-12-31T00:00+14:00[Pacific/Apia]
Date preserved: false
Hours: 0
~~~

Một ngày bị bỏ qua trong lịch vùng là trường hợp hiếm nhưng rất hữu ích để hiểu đúng ý nghĩa **“earliest valid time”** và tránh sai giả định khi chuyển đổi kiểu ngày → thời điểm.

## 9. Lọc dữ liệu trong một ngày: sử dụng khoảng nửa mở

Một ứng dụng ghi các bản ghi bằng `Instant` (hoặc timestamp đã chuẩn hóa đúng) nhưng cần trả về **mọi sự kiện của một ngày theo múi giờ khách hàng**. Cách an toàn là lấy hai mốc đầu ngày:

~~~java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Đoạn minh họa trên cho:

~~~text
from  = 2024-03-10T05:00:00Z
until = 2024-03-11T04:00:00Z
~~~

Dùng khoảng **[from, until)**, bao gồm `from` và loại trừ `until`:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant;
~~~

SQL chỉ minh họa, cần bind tham số phù hợp kiểu timestamp/driver trong cơ sở dữ liệu. Đặc điểm của khoảng nửa mở:

- Bao phủ mọi thời điểm thuộc ngày lịch tại vùng, kể cả khi ngày chỉ dài 23 giờ hoặc tới 25 giờ.
- Không bỏ sót phần giờ bị lặp trong overlap.
- Không cần chế “23:59:59.999999999” phụ thuộc độ phân giải cột database.
- Các khoảng cho hai ngày liên tiếp có thể nối nhau mà không đếm trùng bản ghi ở đúng ranh giới.

**Không thay `until` bằng `from.plus(Duration.ofHours(24))`** khi ý định là “hết ngày địa phương”. Qua DST, công thức cộng 24 giờ có thể lấy thừa hoặc bỏ thiếu dữ liệu.

Với ngày hoàn toàn bị bỏ qua như `Pacific/Apia` 30/12/2011, `from.equals(until)` và query trả phạm vi rỗng, phù hợp với việc không có thời điểm thực nào mang ngày lịch ấy tại vùng đó. Nghiệp vụ có thể vẫn cần báo lỗi đầu vào nếu việc chọn ngày bỏ qua không có nghĩa.

## 10. Đầu ngày hợp lệ khác thời điểm máy chủ bắt đầu một ngày

Đôi khi “ngày hôm nay” được tính từ máy chủ bằng `LocalDate.now()`, nhưng múi giờ của máy chủ có thể là UTC, trong khi người dùng ở Việt Nam, Nhật Bản hoặc Mỹ.

Khi xác định ngày theo vùng:

~~~java
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate today = LocalDate.now(userZone);
Instant startOfToday = today.atStartOfDay(userZone).toInstant();
~~~

Đây là mã minh họa và không có stdout cố định vì phụ thuộc thời gian hiện tại. Nếu cần viết unit test xác định, sử dụng `Clock.fixed` hoặc inject `Clock` rồi gọi `LocalDate.now(clock)`. `ZoneId` dùng để định nghĩa **ngày của ai**, `Clock` dùng để lấy **thời điểm tham chiếu**.

Không dùng `LocalDateTime.now().toInstant(ZoneOffset.UTC)` để lấy “bây giờ UTC” trừ khi local date/time thực sự đã được định nghĩa là UTC. Phép chuyển với offset sai có thể tạo timestamp sai nhiều giờ.

### Khi nào cần giữ nguyên thời điểm tuyệt đối?

Nếu đã có `Instant` của sự kiện, `instant.atZone(zone)` hiển thị sự kiện theo vùng mà không thay đổi `Instant` gốc. Còn `date.atStartOfDay(zone)` **tạo một mốc** từ ngày lịch theo luật vùng; hai thao tác giải quyết hai bài toán khác nhau.

Nếu cần “một ngày lịch trước”, dùng `date.minusDays(1).atStartOfDay(zone)`; nếu cần “đúng 24 giờ trước”, dùng `instant.minus(Duration.ofHours(24))`. Tránh hoán đổi các khái niệm này.

## 11. So sánh với atZone(), ofStrict() và atStartOfDay() không tham số

### `date.atStartOfDay()` — tạo nhãn giờ địa phương

`LocalDate.atStartOfDay()` trả `LocalDateTime` tại 00:00, **không có ZoneId**. Nó không thể biết gap, overlap hoặc ngày bị bỏ qua trong vùng.

### `date.atStartOfDay(zone)` — tìm ranh giới hợp lệ sớm nhất

Phương thức này hướng đến **phạm vi ngày**. Nó dùng `ZoneRules` để chọn đầu ngày hợp lệ và cố tình không yêu cầu người gọi chọn offset thủ công khi gặp overlap.

### `date.atStartOfDay().atZone(zone)` — cùng ý định khác cách diễn đạt

`LocalDateTime.atZone(zone)` cũng giải quyết gap bằng cách dời tiến và overlap bằng offset trước chuyển đổi. Với các trường hợp ví dụ trên, kết quả khớp `date.atStartOfDay(zone)`. Tuy nhiên `date.atStartOfDay(zone)` **biểu đạt đúng mục đích và ý nghĩa “đầu ngày hợp lệ”** rõ ràng hơn, nên ưu tiên khi lấy ranh giới ngày.

### `ZonedDateTime.ofStrict(local, offset, zone)` — không tự giải quyết thay người dùng

`ofStrict` yêu cầu local date/time và offset đã chọn **đều hợp lệ** trong vùng. Nếu `00:00` thuộc gap, không có offset hợp lệ để chỉ định nên sẽ ném `DateTimeException`. Nếu mục tiêu là **từ chối một giờ người dùng yêu cầu** thay vì tìm ranh giới ngày, cách strict có thể phù hợp hơn.

### Một điểm tinh tế

Nếu là **đặt cuộc hẹn vào lúc 00:30** thì có thể cần xác thực giờ chính xác và offset người dùng chọn. Nhưng nếu là **tính phần bắt đầu của ngày lịch** thì mục tiêu là chọn instant đầu tiên thuộc phạm vi ngày theo vùng, kể cả khi đoạn đầu ngày bị gap. Đó là lý do `atStartOfDay(zone)` có quy tắc mặc định có chủ đích.

## 12. Kiểm thử các trường hợp ranh giới ngày

Một bộ kiểm thử tốt cần ít nhất:

1. **Ngày bình thường:** nửa đêm hợp lệ, thời lượng tới đầu ngày kế tiếp 24 giờ.
2. **DST thay đổi trong ngày nhưng không đúng nửa đêm:** ví dụ New York tháng 3 và tháng 11/2024, đầu ngày vẫn 00:00 nhưng độ dài lần lượt 23 và 25 giờ.
3. **Gap ngay tại nửa đêm:** ví dụ São Paulo 04/11/2018, `atStartOfDay(zone)` trả 01:00 chứ không trả giờ không tồn tại.
4. **Overlap tại nửa đêm:** hai offset hợp lệ, chọn mốc sớm nhất trên timeline.
5. **Ngày bị bỏ qua:** `start.toLocalDate()` có thể không bằng ngày được yêu cầu, `start.equals(next)` hoặc cùng instant.
6. **Truy vấn hai ranh giới:** bản ghi đúng tại `from` được lấy, đúng tại `until` bị loại trừ.
7. **Vùng đúng của người dùng:** không lấy múi giờ hệ thống làm mặc định cho mọi yêu cầu.

Có thể viết test xác định thời điểm với ngày cố định và `ZoneId`; không cần `Thread.sleep` hay đồng hồ thật. Kết quả vùng lịch sử thường ổn định trong TZDB phổ biến, nhưng chính sách tương lai có thể được sửa và kết quả có thể thay đổi khi JDK/TZDB cập nhật.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Hệ quả | Cách đúng |
|---|---|---|
| “`atStartOfDay(zone)` luôn cho 00:00.” | Sai ở gap tại nửa đêm. | Hiểu phương thức trả giờ **hợp lệ sớm nhất**. |
| “`atStartOfDay()` và `atStartOfDay(zone)` chỉ khác kiểu trả về.” | Bỏ qua luật vùng và thời điểm thực. | Phân biệt local label với `ZonedDateTime` đã áp luật. |
| “Một ngày luôn bắt đầu bằng một instant có ngày UTC trùng ngày địa phương.” | Sai với offset ± nhiều giờ. | Chuyển `ZonedDateTime.toInstant()` theo đúng vùng. |
| “Mỗi ngày có đúng 86.400 giây.” | Sai ngày DST và đổi luật vùng. | Dùng `Duration.between` hai đầu ngày. |
| “Đầu ngày kế tiếp = đầu ngày hiện tại + 24 giờ.” | Lấy sai ranh giới khi offset chuyển. | Tính `date.plusDays(1).atStartOfDay(zone)`. |
| “Ngày bị bỏ qua vẫn có thời điểm 00:00 riêng.” | Tạo một mốc không thuộc ngày yêu cầu. | Kiểm tra `start.toLocalDate()` và quy tắc vùng. |
| “`ZoneOffset.ofHours(-5)` là tên múi giờ New York.” | Bỏ qua DST. | Dùng `ZoneId.of("America/New_York")`. |
| “Tự thêm một giờ là đủ cho mọi gap.” | Không đúng mọi khu vực/chính sách. | Dựa trên `ZoneRules` và `ZoneOffsetTransition`. |
| “Giờ server là ngày của khách.” | Sai ngày và query lệch giờ. | Nhận `ZoneId` nghiệp vụ rõ ràng. |
| “Chỉ cần ghi nửa đêm 23:59:59.999999 làm điểm kết thúc.” | Dễ sai độ phân giải DB/overlap. | Dùng khoảng nửa mở `[start,nextStart)`. |

## 14. Câu hỏi tự kiểm tra

**1.** Khác biệt cốt lõi giữa `LocalDate.atStartOfDay()` và `LocalDate.atStartOfDay(ZoneId)` là gì?

**Đáp án:** Bản không tham số chỉ tạo `LocalDateTime` 00:00; bản có vùng trả `ZonedDateTime` tại mốc đầu ngày hợp lệ sớm nhất theo luật `ZoneId`.

**2.** Vì sao `2018-11-04.atStartOfDay(America/Sao_Paulo)` có thể trả 01:00?

**Đáp án:** Vì tại ngày đó vùng chuyển offset ngay lúc nửa đêm; khoảng giờ 00:00–00:59 không tồn tại, nên Java chọn 01:00 hợp lệ đầu tiên.

**3.** Nếu một ngày ở New York bắt đầu 00:00 và ngày kế tiếp cũng bắt đầu 00:00, tại sao khoảng giữa chúng có thể chỉ 23 giờ?

**Đáp án:** Hai nửa đêm dùng offset khác nhau do DST; đổi thành `Instant` sẽ cho hiệu 23 giờ dù nhãn đồng hồ đều là 00:00.

**4.** Tại sao một ngày bị bỏ qua trong `Pacific/Apia` có thể làm `start.toLocalDate()` khác `date`?

**Đáp án:** Không có thời điểm thực thuộc ngày 30/12/2011 theo lịch vùng đó. `atStartOfDay(zone)` trả mốc hợp lệ tiếp theo, rơi vào 31/12/2011.

**5.** Để lọc toàn bộ sự kiện ngày 10/03/2024 theo giờ New York, nên lấy khoảng nào?

**Đáp án:** `[2024-03-10T05:00Z, 2024-03-11T04:00Z)`; khoảng này dài 23 giờ và bao phủ đúng ngày địa phương.

**6.** Khi nhập một cuộc hẹn đúng 00:30 tại vùng có overlap, có nên luôn dùng `date.atStartOfDay(zone)` để đặt hẹn không?

**Đáp án:** Không. `atStartOfDay(zone)` dùng cho **ranh giới ngày**, không phải giải quyết một giờ hẹn bất kỳ. Với lịch hẹn, hãy kiểm tra offset hợp lệ của giờ cụ thể và áp chính sách cho gap/overlap.

## Ghi nhớ

- **`LocalDate.atStartOfDay(ZoneId)` trả thời điểm bắt đầu ngày hợp lệ sớm nhất**, không hứa luôn là `00:00`.
- Nếu có **gap ở nửa đêm**, giờ bắt đầu có thể được dời về sau; nếu có **overlap**, chọn mốc sớm nhất theo thứ tự thời gian.
- **Ngày bị bỏ qua hoàn toàn** có thể khiến ngày trong kết quả khác ngày được yêu cầu và hai ranh giới kế tiếp trùng cùng một `Instant`.
- Để lấy dữ liệu một ngày theo vùng, dùng **`date.atStartOfDay(zone).toInstant()`** và **`date.plusDays(1).atStartOfDay(zone).toInstant()`**, kết hợp truy vấn khoảng nửa mở.
- Không quy đổi một ngày lịch thành mặc định 24 giờ thực; luôn đặt câu hỏi về `ZoneId` và quy tắc tại ngày được xét.
