# `LocalDateTime` kết hợp ngày và giờ nhưng chưa xác định một thời điểm

Khi một người nhập “**09:30 ngày 24/10/2026**”, chương trình đã biết **ngày** và **giờ trên đồng hồ**, nhưng vẫn chưa biết đó là 09:30 tại Hà Nội, Tokyo hay New York. Ba địa điểm có thể cùng hiển thị 09:30 vào một ngày, nhưng sự kiện tại ba nơi **không diễn ra cùng một thời điểm trên dòng thời gian**.

Đây là lý do Java phân biệt `LocalDateTime` với `Instant`, `OffsetDateTime` và `ZonedDateTime`:

- `LocalDateTime` biểu diễn **ngày giờ theo lịch và đồng hồ địa phương**, chưa có múi giờ hay UTC offset.
- `Instant` xác định **một mốc duy nhất trên dòng thời gian**, độc lập với vị trí địa lý.
- `OffsetDateTime` có ngày giờ **và một UTC offset cụ thể**, vì vậy xác định được instant.
- `ZonedDateTime` có ngày giờ **và ZoneId khu vực** cùng offset được giải quyết theo quy tắc múi giờ, vì vậy cũng xác định được instant.

Bài học tập trung vào mô hình dữ liệu `LocalDateTime`: kết hợp ngày và giờ, đọc/ghi, tính toán, khi nào nên dùng, tại sao nó chưa xác định một thời điểm và cách chuyển đổi một cách có chủ đích. Các ví dụ sử dụng Java 17+ và bộ API `java.time`.

## 1. Hiểu `LocalDateTime` bằng một câu hỏi thực tế

Giả sử biểu mẫu đặt lịch có ba trường:

~~~text
Ngày:       2026-10-24
Giờ:        09:30
Địa điểm:   Hà Nội
~~~

Hai trường đầu có thể kết hợp thành `LocalDateTime.of(2026, 10, 24, 9, 30)`. Trường địa điểm giúp ứng dụng tìm `ZoneId` phù hợp, chẳng hạn `Asia/Ho_Chi_Minh`. Sau đó mới có thể biến lịch hẹn thành instant để gửi thông báo, sắp xếp sự kiện hoặc lưu thời điểm thực tế.

Nếu thiếu địa điểm hay timezone, hệ thống **không nên giả định** 09:30 là UTC hoặc timezone của máy chủ. Cùng giá trị `2026-10-24T09:30` có thể được gắn:

| Cách hiểu | Giờ địa phương | Offset của ngày đó | Instant UTC tương ứng |
| --- | --- | --- | --- |
| Hà Nội | 2026-10-24 09:30 | +07:00 | 2026-10-24T02:30:00Z |
| Tokyo | 2026-10-24 09:30 | +09:00 | 2026-10-24T00:30:00Z |
| New York | 2026-10-24 09:30 | -04:00 | 2026-10-24T13:30:00Z |

Bảng này sử dụng quy tắc múi giờ áp dụng trong ngày ví dụ, không giả định offset của mọi khu vực cố định quanh năm. **Một `LocalDateTime` giống nhau có thể ứng với nhiều instant khác nhau.**

Ngược lại, một instant như `2026-10-24T02:30:00Z` chỉ là **một** thời điểm. Nó có thể hiển thị thành 09:30 tại Hà Nội hoặc 11:30 tại Tokyo vào cùng ngày. Vậy “cùng ngày giờ địa phương” và “cùng thời điểm tuyệt đối” là hai quan hệ khác nhau.

## 2. `LocalDateTime` chứa những thành phần nào?

`LocalDateTime` kết hợp `LocalDate` và `LocalTime`:

~~~text
LocalDate           LocalTime
2026-10-24          09:30:45.123
        \              /
         \            /
          LocalDateTime
       2026-10-24T09:30:45.123
~~~

Nó lưu **năm, tháng, ngày, giờ, phút, giây và nano giây** theo lịch ISO-8601. Giây và phần nano có thể bằng 0 nên chuỗi thường được rút gọn, ví dụ `2026-10-24T09:30`. Ký tự `T` chỉ phân tách phần ngày và phần giờ của biểu diễn ISO.

`LocalDateTime` **không lưu**:

- `ZoneId` như `Asia/Ho_Chi_Minh` hoặc `America/New_York`.
- `ZoneOffset` như `+07:00` hoặc `-04:00`.
- Thời điểm tuyệt đối `Instant`.
- Chính sách giải quyết giờ không tồn tại hoặc trùng lặp trong chuyển đổi giờ mùa hè.

Vì thế không thể lấy `LocalDateTime` rồi tự động suy ra epoch seconds/milliseconds một cách đúng đắn mà không bổ sung một giả định về offset hoặc múi giờ. Bản thân nó cũng không dùng để đo elapsed time giữa hai sự kiện ở các vùng khác nhau.

`LocalDateTime` là kiểu **bất biến** (immutable), có thể chia sẻ dưới dạng giá trị: mọi phép `plus...()`, `minus...()` hoặc `with...()` trả về giá trị mới, giữ nguyên biến gốc nếu caller không gán lại.

## 3. Tạo một `LocalDateTime` đúng ý nghĩa

### 3.1. Tạo từ các số thành phần

~~~java
LocalDateTime meeting = LocalDateTime.of(2026, 10, 24, 9, 30);
LocalDateTime precise = LocalDateTime.of(
        2026, 10, 24, 9, 30, 45, 123_000_000);
~~~

Ví dụ đầu tương ứng `2026-10-24T09:30`, ví dụ thứ hai tương ứng `2026-10-24T09:30:45.123`. Hàm `of` kiểm tra giá trị theo lịch ISO: ngày 31/02, giờ 24, phút 60 đều không hợp lệ và gây `DateTimeException`.

**Lưu ý:** đoạn code ngắn trong các phần 3–8 mang tính minh họa và cần import các lớp tương ứng. Phần 9 có chương trình hoàn chỉnh với import, lệnh biên dịch, cách chạy và stdout kiểm chứng.

### 3.2. Ghép `LocalDate` và `LocalTime`

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime fromDate = date.atTime(time);
LocalDateTime fromTime = time.atDate(date);
LocalDateTime fromOf = LocalDateTime.of(date, time);
~~~

Cả ba tạo **cùng giá trị** `2026-10-24T09:30`. Đây là cách phù hợp khi người dùng chọn ngày và giờ từ hai trường riêng trên giao diện. Dù tên hàm có `atTime` hoặc `atDate`, kết quả **vẫn chưa có thông tin múi giờ**.

### 3.3. Đọc chuỗi bằng `parse`

~~~java
LocalDateTime parsed = LocalDateTime.parse("2026-10-24T09:30");
~~~

`parse` mặc định hiểu ISO local date-time, chẳng hạn `2026-10-24T09:30:45`. Chuỗi `24/10/2026 09:30` cần `DateTimeFormatter` riêng:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");

LocalDateTime parsed =
        LocalDateTime.parse("24/10/2026 09:30", formatter);
~~~

Chuỗi parse chỉ chứa ngày giờ địa phương. Việc định dạng hay chuyển từ chuỗi sang đối tượng **không tự bổ sung timezone**. Phân biệt `MM` là tháng, `mm` là phút, `HH` là giờ theo hệ 24 giờ. Khi formatter chứa tên tháng bằng chữ, cần chỉ định `Locale` nếu đầu vào phụ thuộc ngôn ngữ.

### 3.4. Lấy “bây giờ” — đồng hồ và vùng ảnh hưởng kết quả

~~~java
LocalDateTime localNow = LocalDateTime.now();
LocalDateTime hanoiNow = LocalDateTime.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`now()` không tham số đọc đồng hồ hệ thống và **múi giờ mặc định của JVM**. Cùng thời điểm chạy, máy ở các vùng khác nhau có thể tạo giá trị `LocalDateTime` khác nhau. Nếu nghiệp vụ dựa trên vùng cụ thể, hãy truyền `ZoneId` hoặc sử dụng `Clock` được cấu hình rõ:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-10-24T02:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime fixedLocal = LocalDateTime.now(fixedClock);
// 2026-10-24T09:30
~~~

`Clock.fixed` giúp test ổn định, không lệ thuộc ngày giờ thực khi chạy. Nếu mục tiêu cần lưu mốc xảy ra sự kiện, ưu tiên `Instant.now(clock)`; dùng `LocalDateTime.now(clock)` khi thực sự cần **giờ lịch địa phương theo vùng của Clock**.

## 4. Đọc các thành phần và làm việc với giá trị bất biến

`LocalDateTime` có các phương thức:

| Phương thức | Ví dụ với `2026-10-24T09:30:45` |
| --- | --- |
| `toLocalDate()` | `2026-10-24` |
| `toLocalTime()` | `09:30:45` |
| `getYear()` | `2026` |
| `getMonthValue()` | `10` |
| `getDayOfMonth()` | `24` |
| `getDayOfWeek()` | `SATURDAY` |
| `getHour()` | `9` |
| `getMinute()` | `30` |
| `getSecond()` | `45` |
| `getNano()` | `0` |

Nếu cần biểu diễn dạng chuỗi, có thể gọi `toString()` hoặc `format(DateTimeFormatter)`. `toString()` thường xuất ISO local date-time, ví dụ `2026-10-24T09:30`, **không có `Z` hoặc offset**. Đừng tự gắn chữ `Z` vào chuỗi để “biến” dữ liệu thành UTC.

Có thể thay hoặc cộng thành phần theo lịch:

~~~java
LocalDateTime original = LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDateTime nextDay = original.plusDays(1);
LocalDateTime later = original.plusHours(2);
LocalDateTime changedHour = original.withHour(8);

// original    = 2026-10-24T09:30
// nextDay     = 2026-10-25T09:30
// later       = 2026-10-24T11:30
// changedHour = 2026-10-24T08:30
~~~

Những phép toán trên thực hiện trên **lịch địa phương thuần túy**: `plusDays(1)` dịch sang ngày kế tiếp, `plusHours(2)` cộng trên chuỗi ngày/giờ địa phương, nhưng chưa xét DST. Nếu áp vùng sau đó, khoảng cách trên dòng thời gian có thể khác số giờ suy ra từ các số trên đồng hồ.

## 5. Vì sao `LocalDateTime` chưa xác định một `Instant`?

Một instant cần ánh xạ giữa **giờ địa phương** và **UTC**. Quan hệ thông thường có thể hình dung:

~~~text
Giờ UTC = giờ địa phương - UTC offset

09:30 ngày 24/10 tại Hà Nội (+07:00)  -> 02:30Z
09:30 ngày 24/10 tại Tokyo (+09:00)   -> 00:30Z
~~~

Khi chưa có offset hoặc zone, không có thông tin để tính một thời điểm duy nhất. Java phản ánh điều đó ngay trong API: `LocalDateTime` **không có `toInstant()` không tham số**.

Nếu được cung cấp **offset đã xác định**, có thể dùng:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);

Instant instant = local.toInstant(ZoneOffset.ofHours(7));
// 2026-10-24T02:30:00Z
~~~

Phép này chỉ hợp lệ về mặt **nghiệp vụ** nếu offset `+07:00` đúng cho địa điểm/thời điểm đầu vào. Offset là mức chênh UTC cố định; nó không mang lịch sử và các thay đổi DST theo địa phương.

Nếu được cung cấp **ZoneId khu vực**, dùng:

~~~java
ZoneId hanoi = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(hanoi);
Instant instant = zoned.toInstant();
~~~

`atZone` áp dụng quy tắc vùng để chọn offset thích hợp cho **ngày giờ địa phương**. `toInstant` lấy mốc tuyệt đối sau khi vùng và offset đã được giải quyết. `LocalDateTime.atOffset(ZoneOffset)` là một đường khác: nó trả `OffsetDateTime` thay vì `ZonedDateTime`.

| Biến đổi | Kết quả | Có xác định instant? |
| --- | --- | --- |
| `LocalDate.atTime(LocalTime)` | `LocalDateTime` | Chưa |
| `LocalDateTime.atOffset(ZoneOffset)` | `OffsetDateTime` | Có, theo offset chỉ định |
| `LocalDateTime.atZone(ZoneId)` | `ZonedDateTime` | Có, sau khi giải quyết quy tắc vùng |
| `LocalDateTime.toInstant(ZoneOffset)` | `Instant` | Có, theo offset chỉ định |
| `ZonedDateTime.toInstant()` | `Instant` | Có |
| `Instant.atZone(ZoneId)` | `ZonedDateTime` | Có, giữ nguyên instant |

**Không nhầm chiều chuyển đổi:** `instant.atZone(zone)` bắt đầu từ thời điểm tuyệt đối đã biết, nên luôn giữ mốc và chỉ thay cách nhìn. `local.atZone(zone)` bắt đầu từ đồng hồ địa phương chưa biết instant, nên phải giải quyết xem giờ đó ứng với mốc nào.

## 6. Giờ mùa hè: một `LocalDateTime` đôi khi có 0 hoặc 2 cách hiểu

Tại một số khu vực có đổi giờ mùa hè (DST), không phải mọi giờ hiển thị đều hợp lệ duy nhất.

**Gap — giờ địa phương không tồn tại:** vào ngày 08/03/2026 tại New York, đồng hồ nhảy từ khoảng 02:00 lên 03:00. `2026-03-08T02:30` không có một instant tương ứng ở vùng này.

**Overlap — giờ địa phương xuất hiện hai lần:** ngày 01/11/2026 tại New York, giờ `01:30` xảy ra hai lần: một lần theo offset `-04:00` và một lần theo `-05:00`. Hai instant khác nhau nhưng **LocalDateTime như nhau**.

~~~java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
ZonedDateTime adjusted = gap.atZone(newYork);
// 2026-03-08T03:30-04:00[America/New_York]

LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
ZonedDateTime early = overlap.atZone(newYork);
ZonedDateTime late = early.withLaterOffsetAtOverlap();

// early = 2026-11-01T01:30-04:00[America/New_York]
// late  = 2026-11-01T01:30-05:00[America/New_York]
~~~

Đoạn trên minh họa hành vi của API với quy tắc timezone hiện hành cho năm 2026. `atZone` mặc định **đẩy giờ không tồn tại về phía trước theo độ dài gap**; với overlap, nó chọn offset trước khi chuyển giờ về mùa đông, nếu không có offset trước đó cần giữ.

Khi lập lịch nhạy cảm, có thể kiểm tra:

~~~java
List<ZoneOffset> offsets =
        newYork.getRules().getValidOffsets(overlap);

// 0 offset = gap, 1 = bình thường, 2 = overlap.
~~~

Đoạn minh họa cần `import java.util.List;` và các kiểu `java.time`. Nghiệp vụ phải quyết định có **từ chối giờ không tồn tại**, tự dời giờ, hoặc yêu cầu người dùng chọn offset cho giờ bị lặp. Nếu ứng dụng chỉ giữ `LocalDateTime`, nó không ghi lại quyết định offset và do đó có thể không phục hồi được mốc sự kiện.

## 7. Khi nào nên dùng `LocalDateTime` và khi nào không?

| Nhu cầu | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| Người dùng nhập ngày và giờ trong biểu mẫu, chưa chọn khu vực | `LocalDateTime` | Giữ đúng hai thành phần được nhập, chưa gán instant |
| Lịch làm việc “09:00 mỗi thứ Hai tại Hà Nội” | `LocalTime` + quy tắc lịch + `ZoneId`, hoặc `LocalDateTime` cho từng lần | Giờ theo địa phương và lịch tái diễn cần zone |
| Hiển thị một sự kiện đã lưu theo khu vực người dùng | `Instant` → `ZonedDateTime` | Phải bảo toàn cùng instant |
| Timestamp `createdAt` của giao dịch | `Instant` hoặc dạng tương đương rõ nghĩa | Cần mốc nhất quán toàn cầu |
| API chứa `2026-10-24T09:30+07:00` | `OffsetDateTime` | Offset đã được cung cấp |
| Sinh nhật hoặc ngày nghỉ, không cần giờ | `LocalDate` | Không gắn giờ/múi giờ giả tạo |
| Chỉ giờ mở cửa 08:00, không cần ngày | `LocalTime` | Không gắn ngày giả tạo |
| Đo thời lượng xử lý 250 ms | `Duration` hoặc hiệu `System.nanoTime()` | Không dùng giờ lịch để đo thời lượng |

Một trường `LocalDateTime` có thể đúng cho “giờ bắt đầu theo đồng hồ của cửa hàng”, nhưng **không đủ một mình** để bảo đảm thông báo được gửi đúng instant. Khi lưu lịch hẹn có địa điểm, nên giữ thêm `ZoneId`, chính sách xử lý DST và/hoặc instant đã giải quyết. Khi chỉ có instant, việc hiển thị lại theo địa điểm người dùng cần biết `ZoneId`.

Đặc biệt, nếu gửi `LocalDateTime` qua HTTP dưới dạng chuỗi ISO không có offset, dịch vụ nhận phải biết rõ **hợp đồng ngữ nghĩa**: đó là giờ tại vùng nào? Nếu không, hai dịch vụ có thể hiểu cùng dữ liệu thành hai sự kiện khác nhau.

## 8. Những phép so sánh và tính toán dễ gây nhầm

`LocalDateTime` triển khai `isBefore`, `isAfter`, `isEqual`, `compareTo`. Chúng so sánh **giá trị ngày giờ địa phương**, không tự tra múi giờ.

~~~java
LocalDateTime nineInHanoi = LocalDateTime.of(2026, 10, 24, 9, 0);
LocalDateTime eightInTokyo = LocalDateTime.of(2026, 10, 24, 8, 0);

boolean localLater = nineInHanoi.isAfter(eightInTokyo); // true
~~~

Kết luận `localLater` chỉ nói “09:00 muộn hơn 08:00 trên cách ghi local”. Nếu thật sự là **09:00 Hà Nội** và **08:00 Tokyo** ngày đó, thì Hà Nội = 02:00Z, Tokyo = 23:00Z của ngày trước: hai mốc cần so bằng `Instant`. Hãy tránh sắp xếp sự kiện của nhiều múi giờ chỉ bằng `LocalDateTime`.

Ví dụ tính khoảng cách:

~~~java
LocalDateTime start = LocalDateTime.of(2026, 3, 8, 1, 30);
LocalDateTime end = LocalDateTime.of(2026, 3, 8, 3, 30);

long localHours = ChronoUnit.HOURS.between(start, end); // 2
~~~

Kết quả là 2 giờ **theo các số trên đồng hồ địa phương**. Tại New York đúng ngày DST bắt đầu, 01:30 `-05:00` đến 03:30 `-04:00` chỉ trôi qua **1 giờ tuyệt đối**. Nếu bài toán hỏi “đã trôi bao lâu?”, trước tiên xác định hai `Instant` rồi dùng `Duration.between(startInstant, endInstant)`.

Không suy từ `LocalDateTime.plusDays(1)` rằng mỗi lần lặp luôn cách lần trước đúng 24 giờ. `LocalDateTime` không có dữ liệu để kiểm tra sự thay đổi offset.

## 9. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây có đầu vào cố định để minh họa: tạo `LocalDateTime` bằng hai cách, kiểm tra hai vùng với cùng giờ đồng hồ, đối chiếu hai instant và đổi cách nhìn từ Việt Nam sang Tokyo.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class LocalDateTimeMeaningDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30);
        LocalDateTime local = date.atTime(time);

        System.out.println("Local: " + local);
        System.out.println("Ghep tu gio: " + time.atDate(date));
        System.out.println("Ngay: " + local.toLocalDate());
        System.out.println("Gio: " + local.toLocalTime());

        ZoneId hanoiZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId tokyoZone = ZoneId.of("Asia/Tokyo");

        ZonedDateTime hanoi = local.atZone(hanoiZone);
        ZonedDateTime tokyoSameClock = local.atZone(tokyoZone);

        Instant hanoiInstant = hanoi.toInstant();
        Instant tokyoInstant = tokyoSameClock.toInstant();

        System.out.println("Ha Noi: " + hanoi);
        System.out.println("Tokyo cung gio: " + tokyoSameClock);
        System.out.println("Instant Ha Noi: " + hanoiInstant);
        System.out.println("Instant Tokyo: " + tokyoInstant);
        System.out.println("Cung instant: "
                + hanoiInstant.equals(tokyoInstant));

        ZonedDateTime tokyoSameInstant =
                hanoiInstant.atZone(tokyoZone);
        System.out.println("Tokyo cung instant: " + tokyoSameInstant);

        LocalDateTime nextMorning = local.plusDays(1);
        System.out.println("Ngay mai cung gio: " + nextMorning);
        System.out.println("Local goc: " + local);
    }
}
~~~

Lưu file đúng tên `LocalDateTimeMeaningDemo.java` rồi chạy:

~~~bash
javac LocalDateTimeMeaningDemo.java
java LocalDateTimeMeaningDemo
~~~

Đầu ra với dữ liệu múi giờ chuẩn:

~~~text
Local: 2026-10-24T09:30
Ghep tu gio: 2026-10-24T09:30
Ngay: 2026-10-24
Gio: 09:30
Ha Noi: 2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
Tokyo cung gio: 2026-10-24T09:30+09:00[Asia/Tokyo]
Instant Ha Noi: 2026-10-24T02:30:00Z
Instant Tokyo: 2026-10-24T00:30:00Z
Cung instant: false
Tokyo cung instant: 2026-10-24T11:30+09:00[Asia/Tokyo]
Ngay mai cung gio: 2026-10-25T09:30
Local goc: 2026-10-24T09:30
~~~

**Đọc kết quả đúng bản chất:**

1. `date.atTime(time)` hoặc `time.atDate(date)` tạo ra cùng `LocalDateTime`; chưa chọn khu vực.
2. `local.atZone(hanoiZone)` và `local.atZone(tokyoZone)` có **cùng 09:30** trên đồng hồ nhưng hai offset `+07:00` và `+09:00`.
3. Hai instant là 02:30Z và 00:30Z; vì thế `equals` trả `false`. Đây là bằng chứng cùng `LocalDateTime` **chưa xác định một instant**.
4. `hanoiInstant.atZone(tokyoZone)` hiển thị sự kiện ở Nhật thành **11:30**, giữ nguyên 02:30Z. Đây mới là “cùng sự kiện, hai múi giờ”.
5. `plusDays(1)` trả về giờ 09:30 ngày kế tiếp, không thay đổi `local` gốc vì các đối tượng `java.time` là bất biến.

Ví dụ không gọi `now()` và sử dụng khu vực không đổi DST tại mốc chọn, nên kết quả có thể đối chiếu trực tiếp.

## 10. Các lỗi phổ biến khi làm việc với `LocalDateTime`

### 10.1. Coi giờ địa phương là UTC

Sai về ngữ nghĩa:

~~~java
LocalDateTime entered = LocalDateTime.of(2026, 10, 24, 9, 30);
Instant wrong = entered.toInstant(ZoneOffset.UTC);
~~~

Nếu `entered` thực tế là giờ Hà Nội, `wrong` là `09:30Z`, muộn hơn thời điểm đúng **7 giờ**. API vẫn chạy và không báo lỗi vì Java không biết dữ liệu thuộc vùng nào; **lỗi nằm ở giả định nghiệp vụ**.

Đúng khi đã biết vùng:

~~~java
Instant correct = entered
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
// 2026-10-24T02:30:00Z
~~~

### 10.2. Gắn chữ `Z` vào chuỗi không có offset

`entered.toString() + "Z"` chỉ tạo một **chuỗi mang ý nghĩa giả**: nó không đổi 09:30 từ giờ Hà Nội về UTC. Muốn ISO UTC, phải chuyển thật sang instant trước rồi format hoặc gọi `instant.toString()`.

### 10.3. Gọi `atZone(ZoneId.systemDefault())` tùy tiện

Nếu container chạy UTC và laptop chạy giờ Việt Nam, cùng `LocalDateTime` có thể thành hai instant khác nhau. Chọn múi giờ dựa trên **người dùng, cơ sở, địa điểm sự kiện hoặc hợp đồng dữ liệu**, không mặc định JVM là đúng.

### 10.4. Lấy phần ngày giờ từ một instant trước khi quyết định vùng

Một instant cuối ngày UTC có thể là ngày kế tiếp ở châu Á. Để lấy **ngày địa phương**, trước tiên gọi `instant.atZone(zone).toLocalDate()`. Đừng chuyển sang `LocalDateTime` bằng một timezone ngầm định rồi gửi cho hệ thống ở khu vực khác mà không giữ zone.

### 10.5. Lưu lịch hẹn tái diễn chỉ bằng `Instant` của lần đầu

Nếu nghiệp vụ là “09:00 mỗi thứ Hai tại New York”, cách tính lần tiếp theo bằng cách cộng cố định 7 × 24 giờ từ instant có thể làm giờ địa phương đổi sau DST. Cần giữ **quy tắc lặp + ZoneId**, tạo từng `LocalDateTime` theo lịch, rồi giải quyết từng occurrence theo zone và chính sách gap/overlap.

### 10.6. Suy rằng kiểu SQL `TIMESTAMP` luôn đồng nghĩa UTC

Hành vi lưu/đọc `LocalDateTime` qua JDBC/ORM phụ thuộc driver, hệ quản trị, kiểu cột, cấu hình múi giờ và hợp đồng chuyển đổi. `TIMESTAMP WITHOUT TIME ZONE` thường lưu số ngày giờ theo lịch mà không chứa offset, nhưng không thể tự xem giá trị đó là một instant. Không giả định mọi DB hoặc serializer đều bảo toàn `ZoneId` nếu chỉ lưu `LocalDateTime`.

## 11. Quy trình lựa chọn kiểu và chuyển đổi

Khi hệ thống nhận ngày giờ đầu vào, tự trả lời tuần tự:

1. **Dữ liệu đã gồm những gì?** Nếu chỉ có ngày và giờ thì `LocalDateTime` biểu diễn đúng những gì đã biết.
2. **Nó thuộc múi giờ của ai?** Nếu câu hỏi chưa có đáp án, cần bổ sung zone/offset từ người dùng hoặc quy tắc nghiệp vụ trước khi tạo instant.
3. **Đang cần giữ cùng giờ đồng hồ hay cùng thời điểm?** Hai mục tiêu dẫn đến các phép chuyển khác nhau.
4. **Zone có gap/overlap không?** Nếu có, phải xác định chính sách và có thể yêu cầu người dùng lựa chọn.
5. **Dữ liệu sẽ lưu ở đâu?** Timestamp sự kiện thường cần `Instant`; lịch lặp theo địa phương cần `ZoneId` và quy tắc lặp. Ngày/giờ nhập ban đầu cũng có thể cần giữ để hiển thị hoặc giải trình.
6. **Làm sao xác minh?** Dùng ngày và vùng cố định, so sánh `toInstant()`, kiểm tra các trường hợp khác offset, ranh giới ngày và DST.

## 12. Bài tập tự kiểm tra

1. Cho `LocalDateTime.of(2026, 10, 24, 9, 30)`. Vì sao biến này **chưa** xác định được epoch milliseconds?
2. Tạo hai `ZonedDateTime` từ cùng `LocalDateTime` ở Việt Nam và Tokyo. In `toInstant()` của từng cái. Nếu chọn **cùng giờ địa phương**, hai instant có bằng nhau không?
3. Cho `Instant.parse("2026-10-24T02:30:00Z")`. Hiển thị nó ở Hà Nội và Tokyo. Vì sao hai giờ hiển thị khác nhau nhưng là cùng một sự kiện?
4. Phần mềm lưu lịch đặt khám “01:30 ngày 01/11/2026 tại New York”. Tại sao chỉ lưu `LocalDateTime` có thể làm mất khả năng xác định lần 01:30 mà người dùng muốn?
5. `ChronoUnit.HOURS.between` trên hai `LocalDateTime` khác `Duration.between` trên hai `Instant` như thế nào khi đi qua giờ mùa hè?
6. Viết test dùng `Clock.fixed` để khẳng định `LocalDateTime.now(clock)` trả về ngày giờ địa phương trong múi giờ của clock, nhưng `Instant.now(clock)` vẫn là một mốc toàn cầu.
7. Đề xuất thiết kế lưu trữ cho hai bài toán: **ngày giờ dự kiến của một lịch họp theo địa phương** và **thời điểm chính xác tạo một giao dịch**. Chỉ ra chỗ nào cần `LocalDateTime`, `ZoneId`, `Instant`.

**Ghi nhớ:** `LocalDateTime` trả lời **“ngày nào, mấy giờ trên đồng hồ?”** chứ chưa trả lời **“khi nào trên dòng thời gian?”**. Chỉ sau khi áp dụng offset hoặc quy tắc múi giờ phù hợp mới có thể suy ra một `Instant`. Việc chọn đúng mô hình dữ liệu giúp tránh sai lệch lịch hẹn, timestamp, so sánh sự kiện và tính thời lượng trên hệ thống đa múi giờ.