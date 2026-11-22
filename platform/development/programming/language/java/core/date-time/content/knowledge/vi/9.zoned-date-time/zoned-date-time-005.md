# Cách atZone() xử lý mặc định khoảng trống và chồng lặp

`LocalDateTime` chỉ lưu năm, tháng, ngày, giờ, phút, giây và nano giây; nó **không chứa UTC offset hay tên múi giờ**. Khi gọi `localDateTime.atZone(zone)`, Java dùng quy tắc vùng (`ZoneRules`) để tạo `ZonedDateTime`. Thao tác này thường đơn giản, nhưng tại những nơi có thay đổi đồng hồ như giờ mùa hè (*daylight saving time*, DST), một giờ địa phương có thể **không tồn tại** (*gap*) hoặc **xuất hiện hai lần** (*overlap*).

Đây là ba quy tắc mặc định quan trọng nhất:

1. **Giờ bình thường:** có một offset hợp lệ, nên Java giữ nguyên ngày giờ địa phương và chọn offset đó.
2. **Gap:** không có offset hợp lệ; Java **dời giờ địa phương tiến đúng bằng độ dài khoảng trống** và dùng offset sau lần chuyển đổi.
3. **Overlap:** có hai offset hợp lệ; Java **giữ nguyên ngày giờ địa phương** và ưu tiên **offset trước lần chuyển đổi** (*earlier offset*, thường là offset mùa hè).

Điều này có nghĩa `atZone()` **không luôn chỉ “đính kèm múi giờ”**: nó có thể thay đổi giờ được yêu cầu, hoặc phải chọn một trong hai thời điểm. Cần hiểu quy tắc đó trước khi lưu lịch hẹn, chuyển sang `Instant` hay tính epoch.

## 1. Các kiểu thời gian trong quá trình chuyển đổi

| Kiểu Java | Chứa gì? | Ý nghĩa trong bài |
|---|---|---|
| `LocalDateTime` | Ngày và giờ địa phương, không chứa offset. | Đầu vào, có thể nhập nhằng. |
| `ZoneId` | Danh tính vùng với quy tắc lịch sử/tương lai, ví dụ `America/New_York`. | Cung cấp luật offset tại ngày giờ đang xét. |
| `ZoneOffset` | Độ lệch so với UTC, ví dụ `-04:00`, `-05:00`. | Một lựa chọn offset cụ thể. |
| `ZoneRules` | Quy tắc và các lần chuyển đổi offset của vùng. | Kiểm tra giờ bình thường, gap, overlap. |
| `ZonedDateTime` | Local time, `ZoneId` và offset đã được giải quyết. | Kết quả của `atZone()`. |
| `Instant` | Điểm thời gian tuyệt đối, không phụ thuộc cách hiển thị vùng. | Mốc sự kiện thực tế sau khi chuyển. |

Ví dụ:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 5, 10, 10, 15);
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime resolved = local.atZone(zone);
Instant instant = resolved.toInstant();
~~~

Đoạn trên là **mã minh họa** cần import các kiểu `java.time` và đặt trong phương thức. Ngày 10/05/2024 ở New York là thời gian bình thường với offset `-04:00`, nên `resolved` tương ứng `2024-05-10T10:15-04:00[America/New_York]`.

**`ZoneId` không đồng nghĩa `ZoneOffset`.** Một vùng có thể dùng offset `-05:00` vào mùa đông và `-04:00` vào mùa hè. Nếu chỉ dùng `ZoneOffset.ofHours(-5)` cho toàn bộ năm, bạn đã bỏ qua luật DST.

## 2. Quy tắc tra offset hợp lệ

Java cho phép xem trực tiếp mọi offset phù hợp với một `LocalDateTime`:

~~~java
List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
~~~

Đây là mã minh họa; cần import `java.time.ZoneOffset` và `java.util.List`, cũng như khai báo `zone` và `local`.

| `getValidOffsets(local)` | Trường hợp | `local.atZone(zone)` sẽ làm gì? |
|---|---|---|
| Danh sách **1** phần tử | Giờ bình thường | Giữ local time và áp offset duy nhất. |
| Danh sách **rỗng** | Gap | Dời thời gian theo độ dài gap, chọn offset sau chuyển đổi. |
| Danh sách **2** phần tử | Overlap | Giữ local time, ưu tiên offset trước chuyển đổi. |

`ZoneRules.getTransition(local)` có thể trả `ZoneOffsetTransition` khi local time thuộc gap hoặc overlap. Từ đó có thể tra offset trước/sau, độ dài chuyển đổi và kiểu gap/overlap. Với ngày giờ bình thường, `getTransition(local)` thường trả `null`; đừng gọi phương thức trên kết quả mà không kiểm tra.

Cả hai ví dụ tiếp theo dùng `America/New_York` năm **2024**. Đó là dữ liệu lịch sử cụ thể; không có quy tắc “mọi vùng trên thế giới đều chuyển lúc 02:00 và đúng một giờ”.

## 3. Gap: giờ không tồn tại bị đẩy tiến đến giờ hợp lệ

New York bắt đầu DST vào **10/03/2024**. Đồng hồ nhảy từ `01:59:59-05:00` sang `03:00:00-04:00`:

~~~text
2024-03-10 (America/New_York)

01:59:59 -05:00
        ↓ một giây thực
03:00:00 -04:00

02:00:00 đến 02:59:59.999... không xuất hiện.
~~~

Vì vậy `2024-03-10T02:30` là một giá trị `LocalDateTime` hợp lệ về cấu trúc, nhưng **không phải giờ dân sự từng tồn tại** ở New York trong ngày đó.

~~~java
LocalDateTime requested = LocalDateTime.of(2024, 3, 10, 2, 30);
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime resolved = requested.atZone(newYork);
~~~

Đây là mã minh họa. Giá trị `resolved` là:

~~~text
2024-03-10T03:30-04:00[America/New_York]
~~~

Java đẩy 02:30 tiến **một giờ** thành 03:30 vì gap trong ví dụ dài một giờ. Mốc `Instant` tương ứng là `2024-03-10T07:30:00Z`.

Điểm quan trọng:

- `atZone()` **không tự ném ngoại lệ** khi giờ địa phương thuộc gap.
- Local time bên trong **kết quả** đã chuyển từ 02:30 sang 03:30.
- Biến `requested` gốc không đổi vì `LocalDateTime` là kiểu bất biến.
- Không tồn tại một instant cho chính nhãn “02:30 ở New York” trong ngày đó theo quy tắc vùng.

Gap có thể dài 30 phút, một giờ hoặc khác nữa theo lịch sử từng vùng. Java dời **theo độ dài chuyển đổi** chứ không mã hóa cứng phép cộng một giờ.

Đối với việc đặt lịch, ứng dụng phải quyết định có chấp nhận điều chỉnh mặc định này hay từ chối thời gian do người dùng nhập. Một cuộc hẹn “02:30 chính xác” có thể cần báo lỗi thay vì âm thầm chuyển thành 03:30.

## 4. Overlap: một local time tương ứng hai thời điểm

Ngày **03/11/2024**, New York kết thúc DST. Đồng hồ lùi từ `01:59:59-04:00` về `01:00:00-05:00`:

~~~text
2024-11-03 (America/New_York)

01:00–01:59  -04:00  (lượt đầu)
      ↓ đồng hồ lùi
01:00–01:59  -05:00  (lượt sau)
~~~

Như vậy local time `2024-11-03T01:30` có **hai offset hợp lệ**:

| Local time | Offset | Instant |
|---|---|---|
| `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

Hai instant cách nhau **3600 giây**, nhưng nhãn giờ phút địa phương giống nhau.

Khi gọi:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime first = local.atZone(newYork);
ZonedDateTime second = first.withLaterOffsetAtOverlap();
~~~

Đây là mã minh họa. `atZone()` mặc định chọn offset trước chuyển đổi `-04:00`. `withLaterOffsetAtOverlap()` chọn offset sau chuyển đổi `-05:00`.

Lưu ý: tên *earlier offset* trong Javadoc liên quan **thứ tự trước/sau chuyển đổi**, không có nghĩa offset mang trị số nhỏ hơn. Trong ví dụ, `-04:00` lại lớn hơn `-05:00` theo số học. Đừng tự sắp xếp offset bằng chuỗi rồi xem phần tử nhỏ nhất là lần đầu.

Nếu người dùng thực sự chọn lần 01:30 thứ hai, mã gọi `atZone()` mặc định sẽ tạo **sai instant một giờ** trừ khi ứng dụng ghi nhận và áp lựa chọn cụ thể.

## 5. Ví dụ Java 17+: xem trực tiếp hành vi mặc định

Lưu `AtZoneDefaultsDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AtZoneDefaultsDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime normal = LocalDateTime.of(2024, 5, 10, 10, 15);
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZonedDateTime normalValue = normal.atZone(zone);
        ZonedDateTime gapValue = gap.atZone(zone);
        ZonedDateTime first = overlap.atZone(zone);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();

        System.out.println("Normal: " + normalValue);
        System.out.println("Gap requested: " + gap);
        System.out.println("Gap resolved: " + gapValue);
        System.out.println("Gap instant: " + gapValue.toInstant());
        System.out.println("Overlap default: " + first);
        System.out.println("Overlap later: " + second);
        System.out.println("First instant: " + first.toInstant());
        System.out.println("Second instant: " + second.toInstant());
        System.out.println("Same instant? "
                + first.toInstant().equals(second.toInstant()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AtZoneDefaultsDemo.java
java AtZoneDefaultsDemo
~~~

Stdout (với dữ liệu vùng New York năm 2024):

~~~text
Normal: 2024-05-10T10:15-04:00[America/New_York]
Gap requested: 2024-03-10T02:30
Gap resolved: 2024-03-10T03:30-04:00[America/New_York]
Gap instant: 2024-03-10T07:30:00Z
Overlap default: 2024-11-03T01:30-04:00[America/New_York]
Overlap later: 2024-11-03T01:30-05:00[America/New_York]
First instant: 2024-11-03T05:30:00Z
Second instant: 2024-11-03T06:30:00Z
Same instant? false
~~~

**Đọc kết quả:**

- Dòng `Normal` giữ giờ địa phương 10:15, thêm offset duy nhất.
- `Gap requested` là đầu vào bất hợp lệ theo luật vùng, nhưng `Gap resolved` đã được Java dịch thành 03:30.
- `Overlap default` và `Overlap later` giữ 01:30, khác offset và vì vậy khác `Instant`.

Trong hệ thống thực, hãy kiểm tra **cả offset và instant**, không chỉ so sánh phần năm/tháng/ngày/giờ/phút của `ZonedDateTime`.

## 6. Kiểm tra ZoneRules và ZoneOffsetTransition

`ZoneRules` giúp phát hiện trường hợp cần chính sách riêng. `ZoneOffsetTransition` cho biết độ dài chuyển đổi (dương ở gap, âm ở overlap) và offset hai bên.

Tệp `InspectTransitionsDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class InspectTransitionsDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime normal = LocalDateTime.of(2024, 5, 10, 10, 15);
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZoneOffsetTransition gapTransition = rules.getTransition(gap);
        ZoneOffsetTransition overlapTransition =
                rules.getTransition(overlap);

        System.out.println("Normal offsets: "
                + rules.getValidOffsets(normal));
        System.out.println("Gap offsets: "
                + rules.getValidOffsets(gap));
        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));
        System.out.println("Gap? " + gapTransition.isGap());
        System.out.println("Gap duration: "
                + gapTransition.getDuration());
        System.out.println("Overlap? "
                + overlapTransition.isOverlap());
        System.out.println("Overlap duration: "
                + overlapTransition.getDuration());
    }
}
~~~

Chạy:

~~~bash
javac InspectTransitionsDemo.java
java InspectTransitionsDemo
~~~

Stdout:

~~~text
Normal offsets: [-04:00]
Gap offsets: []
Overlap offsets: [-04:00, -05:00]
Gap? true
Gap duration: PT1H
Overlap? true
Overlap duration: PT-1H
~~~

Trong chương trình minh họa, `getTransition()` trả dữ liệu vì cả `gap` và `overlap` đều thuộc thời điểm chuyển đổi đã xác định. Với một local time bình thường, `getTransition(local)` có thể trả `null`; phải kiểm tra trước khi gọi `isGap()` hoặc `getDuration()`.

Khi xử lý lịch người dùng nhập:

1. Dùng `zone.getRules().getValidOffsets(local)`.
2. Nếu có **0 offset**, yêu cầu nhập lại hoặc áp chính sách dời giờ đã công bố.
3. Nếu có **1 offset**, có thể tạo `ZonedDateTime` tương ứng.
4. Nếu có **2 offset**, yêu cầu chọn offset hoặc áp luật thống nhất cho lần đầu/lần sau.
5. Lưu lại quyết định để audit và chuyển sang `Instant` chính xác.

## 7. Từ chối tự sửa hoặc tự chọn: ZonedDateTime.ofStrict()

Nếu nghiệp vụ yêu cầu giờ địa phương và offset phải hợp lệ đúng như người dùng chọn, sử dụng:

~~~java
ZonedDateTime.ofStrict(local, selectedOffset, zone);
~~~

Đây là mã minh họa cần khai báo `local`, `selectedOffset` và `zone`.

`ofStrict()` khác `atZone()`:

- Gap: không có offset hợp lệ → **ném `DateTimeException`**, không dời giờ.
- Giờ bình thường: chỉ chấp nhận offset hợp lệ duy nhất.
- Overlap: chấp nhận một trong hai offset nếu được chỉ rõ.
- Offset không phù hợp ZoneId/ngày giờ → ném ngoại lệ.

Tệp `StrictResolutionDemo.java` cho thấy cách yêu cầu người dùng chọn offset tại overlap:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictResolutionDemo {
    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, ZoneOffset chosen) {

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException("Nonexistent local time");
        }
        if (valid.size() == 2 && chosen == null) {
            throw new IllegalArgumentException("Ambiguous local time");
        }

        ZoneOffset offset =
                chosen == null ? valid.get(0) : chosen;

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException("Invalid offset");
        }
        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        try {
            resolve(gap, zone, null);
        } catch (IllegalArgumentException e) {
            System.out.println("Gap rejected: " + e.getMessage());
        }

        try {
            resolve(overlap, zone, null);
        } catch (IllegalArgumentException e) {
            System.out.println("Overlap rejected: " + e.getMessage());
        }

        ZonedDateTime earlier =
                resolve(overlap, zone, ZoneOffset.ofHours(-4));
        ZonedDateTime later =
                resolve(overlap, zone, ZoneOffset.ofHours(-5));

        System.out.println("Earlier instant: "
                + earlier.toInstant());
        System.out.println("Later instant: "
                + later.toInstant());
    }
}
~~~

Chạy:

~~~bash
javac StrictResolutionDemo.java
java StrictResolutionDemo
~~~

Stdout:

~~~text
Gap rejected: Nonexistent local time
Overlap rejected: Ambiguous local time
Earlier instant: 2024-11-03T05:30:00Z
Later instant: 2024-11-03T06:30:00Z
~~~

Đây là **một chính sách minh họa**, không phải yêu cầu bắt buộc của mọi ứng dụng. Ví dụ scheduler có thể tự dời tới giờ hợp lệ; còn đặt phòng hoặc thời điểm giao dịch nhạy cảm có thể cần từ chối để bảo toàn ý định người dùng.

## 8. Những API có tên gần nhau nhưng hành vi khác

### LocalDateTime.atZone(zone) và ZonedDateTime.of(local, zone)

`LocalDateTime.atZone(zone)` và `ZonedDateTime.of(local, zone)` sử dụng **cùng quy tắc giải quyết mặc định**: dời tiến gap và ưu tiên offset trước chuyển đổi trong overlap.

### ZonedDateTime.ofLocal(local, zone, preferredOffset)

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` nhận offset **ưu tiên**. Nếu offset này hợp lệ trong overlap, Java sử dụng nó. Nếu không hợp lệ, phương thức có thể quay về quy tắc mặc định. Trong gap, nó vẫn điều chỉnh giờ địa phương. Do đó `ofLocal` **không phải kiểm tra strict**.

### LocalDateTime.atOffset(offset)

`local.atOffset(offset)` tạo `OffsetDateTime` gắn offset cố định, **không tra `ZoneRules` của vùng**. Nó có thể tạo giá trị `2024-03-10T02:30-05:00` dù 02:30 không tồn tại theo đồng hồ New York vào ngày đó. Nếu ý định là “giờ New York”, việc chỉ gắn `-05:00` là không đủ để xác thực.

### withEarlierOffsetAtOverlap() và withLaterOffsetAtOverlap()

Hai phương thức dùng trên `ZonedDateTime` để chọn offset trước/sau chuyển đổi khi ở overlap. Nếu thời gian không thuộc overlap, chúng không ép đổi offset sai quy tắc. Chúng rất hữu ích khi người dùng xác nhận “lượt đầu” hoặc “lượt sau”.

### withZoneSameInstant() và withZoneSameLocal()

- `withZoneSameInstant(otherZone)` đổi cách hiển thị nhưng giữ **cùng `Instant`**.
- `withZoneSameLocal(otherZone)` cố giữ ngày giờ địa phương rồi giải quyết theo quy tắc vùng mới, nên **`Instant` có thể thay đổi**.

Muốn đổi log UTC sang giờ Việt Nam để hiển thị, dùng `instant.atZone(zone)` hoặc `withZoneSameInstant`; đừng dùng `withZoneSameLocal` khi phải giữ nguyên mốc sự kiện.

### Thao tác trên ZonedDateTime hiện có

Khi thực hiện phép toán trên một `ZonedDateTime` đã có offset, một số phép thay đổi local date/time có thể **ưu tiên giữ offset hiện tại nếu nó vẫn hợp lệ** ở vùng overlap. Đây là bối cảnh khác với `LocalDateTime.atZone(zone)` tạo một giá trị mới từ đầu vào không có offset. Vì vậy, không nên suy rộng rằng mọi phép toán với `ZonedDateTime` đều chọn lại offset trước chuyển đổi một cách giống nhau.

## 9. Ví dụ bài toán đặt lịch và dữ liệu lưu trữ

Người dùng đặt lịch `2024-11-03T01:30` tại New York. Nếu chọn **lần xuất hiện thứ hai**, có thể lưu dữ liệu đã diễn giải:

~~~json
{
  "requestedLocalDateTime": "2024-11-03T01:30:00",
  "zoneId": "America/New_York",
  "selectedOffset": "-05:00",
  "resolvedInstant": "2024-11-03T06:30:00Z"
}
~~~

Lưu cả `ZoneId` khi mục đích là lịch theo vùng; offset được chọn tại một lần chạy không có nghĩa toàn bộ các lần chạy tương lai đều dùng offset đó.

Nếu người dùng nhập `2024-03-10T02:30` ở New York, có thể áp chính sách từ chối hoặc dời theo gap. Với chính sách dời, thông tin cần audit có thể như sau:

~~~json
{
  "requestedLocalDateTime": "2024-03-10T02:30:00",
  "zoneId": "America/New_York",
  "resolutionPolicy": "SHIFT_FORWARD_BY_GAP",
  "resolvedLocalDateTime": "2024-03-10T03:30:00",
  "resolvedInstant": "2024-03-10T07:30:00Z"
}
~~~

Hai JSON là **mô hình dữ liệu minh họa**, không phải API tự tạo của Java. Giữ local time được yêu cầu giúp giải thích lý do kết quả khác với giờ nhập.

Đối với sự kiện đã xảy ra, nếu đã biết `Instant` thì có thể chuyển `instant.atZone(zone)` để hiển thị mà không phải chọn một trong hai thời điểm: nguồn instant đã xác định duy nhất. Nhập nhằng xảy ra khi đi theo chiều **local time thiếu offset → instant**.

**Không thể khôi phục chắc chắn instant từ dữ liệu cũ chỉ có chuỗi “2024-11-03 01:30”** nếu không biết zone, offset hoặc quy tắc đã áp. Khi migrate dữ liệu, cần quy ước có căn cứ từ nguồn và ghi nhận những bản ghi nhập nhằng.

### Lịch lặp qua nhiều năm

Một lịch “01:30 mỗi ngày tại New York” phải được tính theo `ZoneRules` tại **ngày của từng lần xuất hiện**. Dùng một offset cố định cho toàn bộ lịch sẽ sai sau chuyển đổi DST. Chính sách nên chỉ rõ:

- Nếu giờ ngày đó không tồn tại: bỏ kỳ, chuyển giờ hay báo người dùng?
- Nếu giờ đó lặp lại: chạy lần đầu, lần sau hay cả hai?
- Nếu quy tắc múi giờ quốc gia thay đổi: cập nhật TZDB và xét lại lịch tương lai như thế nào?

Với xử lý đa vùng, tránh dùng `ZoneId.systemDefault()` trừ khi đồng hồ của hệ thống thực sự là vùng nghiệp vụ. Nên truyền `ZoneId` tường minh từ yêu cầu hoặc cấu hình.

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| “`atZone()` chỉ gắn vùng, không đổi local time.” | Trong gap, giờ được dời tiến. | Kiểm tra `getValidOffsets` và so sánh input/output. |
| “Giờ thuộc gap tự ném exception.” | `atZone` mặc định điều chỉnh, không từ chối. | Kiểm tra trước hoặc dùng `ofStrict`. |
| “Trong overlap chỉ có một mốc UTC.” | Có hai offset, hai instant. | Lưu/chọn offset theo chính sách. |
| “Earlier offset nghĩa là offset có số nhỏ hơn.” | Trình tự trước/sau chuyển đổi khác thứ tự số học. | Dùng `ZoneRules` và `withEarlier/LaterOffsetAtOverlap`. |
| “New York luôn là -05:00.” | DST đổi sang -04:00 ở mùa hè. | Dùng ZoneId với luật của ngày. |
| “`atOffset` cũng kiểm tra DST của New York.” | Nó chỉ gắn offset cố định. | Dùng ZoneId/ZoneRules để xác thực. |
| “`ofLocal` bắt buộc preferredOffset hợp lệ.” | Có thể fallback về mặc định. | Dùng `ofStrict` khi cần kiểm tra chặt. |
| “`withZoneSameLocal` giữ nguyên Instant.” | Nó có thể đổi mốc thời gian. | Dùng `withZoneSameInstant`. |
| “Mọi vùng DST đều đổi đúng một giờ.” | Lịch sử và địa phương có bước chuyển khác. | Tra `ZoneOffsetTransition.getDuration()`. |
| “Giờ máy chủ đủ để biết vùng người dùng.” | Máy chủ có thể ở vùng khác. | Lưu ZoneId của ngữ cảnh nghiệp vụ. |

## 11. Câu hỏi tự kiểm tra

**1.** Gọi `LocalDateTime.of(2024, 3, 10, 2, 30).atZone(ZoneId.of("America/New_York"))` trả gì?

**Đáp án:** `2024-03-10T03:30-04:00[America/New_York]`. Gap một giờ khiến giờ địa phương được dời tiến một giờ.

**2.** Vì sao `2024-11-03T01:30` ở New York có hai instant?

**Đáp án:** Vì đồng hồ chuyển từ `-04:00` về `-05:00`; hai kết quả là `2024-11-03T05:30:00Z` và `2024-11-03T06:30:00Z`.

**3.** `atZone` chọn lượt nào khi gặp overlap này?

**Đáp án:** Mặc định ưu tiên offset trước chuyển đổi, `-04:00`, tương ứng lượt đầu. Dùng `withLaterOffsetAtOverlap()` cho lượt sau.

**4.** `getValidOffsets(local)` có bao nhiêu phần tử nếu local time rơi vào gap?

**Đáp án:** Bằng 0, vì không offset nào khiến giờ địa phương đó hợp lệ trong vùng.

**5.** Muốn bắt buộc người dùng cung cấp offset thật sự hợp lệ và từ chối gap, nên dùng API gì?

**Đáp án:** Kiểm tra `ZoneRules.getValidOffsets` trước, rồi tạo bằng `ZonedDateTime.ofStrict(local, chosenOffset, zone)`.

**6.** Nếu đã có một `Instant` của sự kiện, chuyển sang vùng mới có làm thay đổi mốc sự kiện không?

**Đáp án:** Không. `instant.atZone(zone)` hiển thị cùng mốc theo giờ vùng; không tạo thêm instant. Nhập nhằng gap/overlap liên quan chiều chuyển từ local time thiếu offset sang instant.

## Ghi nhớ

**`LocalDateTime.atZone(zone)` giải quyết luật vùng chứ không chỉ thêm một nhãn múi giờ.** Nó **giữ local time nếu bình thường**, **dời tiến theo độ dài gap**, và **ưu tiên offset trước chuyển đổi trong overlap**. Khi hành vi mặc định không đáp ứng yêu cầu nghiệp vụ, hãy phát hiện bằng `ZoneRules.getValidOffsets` và thực thi chính sách rõ ràng, có thể dùng `ZonedDateTime.ofStrict` để kiểm soát offset. Phân biệt rõ **local time người dùng yêu cầu**, **offset đã chọn** và **Instant cuối cùng**.
