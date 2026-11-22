# Đổi độ lệch: giữ nguyên thời điểm hay giữ nguyên ngày giờ địa phương?

Trong Java, một `OffsetDateTime` chứa **ngày giờ địa phương và một độ lệch UTC đã xác định**. Khi bạn muốn đổi offset từ `+07:00` sang `-05:00`, có hai nhu cầu **rất khác nhau**:

1. **Giữ cùng thời điểm thực tế trên dòng thời gian** và đổi giờ đồng hồ để phù hợp với offset mới: `withOffsetSameInstant(newOffset)`.
2. **Giữ nguyên số giờ, ngày tháng đang hiển thị**, chỉ thay cách diễn giải chúng dưới offset mới: `withOffsetSameLocal(newOffset)`.

Nhầm hai phương thức có thể làm timestamp bị lệch hàng giờ, thậm chí thay đổi ngày và thứ tự sự kiện. Đây là điểm quan trọng nhất của chủ đề “Ngày giờ có offset” trong `java.time`.

~~~java
OffsetDateTime original =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

ZoneOffset newOffset = ZoneOffset.ofHours(-5);

OffsetDateTime sameInstant =
        original.withOffsetSameInstant(newOffset);
// 2026-01-14T21:00-05:00 — cùng Instant với original.

OffsetDateTime sameLocal =
        original.withOffsetSameLocal(newOffset);
// 2026-01-15T09:00-05:00 — cùng LocalDateTime với original.
~~~

*Đoạn code minh họa đặt trong một method, dùng `import java.time.OffsetDateTime;` và `import java.time.ZoneOffset;`. Một chương trình độc lập có thể chạy nằm ở phần 5.*

## 1. Nền tảng: `OffsetDateTime` gồm hai phần nào?

`OffsetDateTime` lưu:

- **`LocalDateTime`**: năm, tháng, ngày, giờ, phút, giây, nano giây theo đồng hồ địa phương, ví dụ `2026-01-15T09:00`.
- **`ZoneOffset`**: độ lệch với UTC, ví dụ `+07:00`.

Hai thông tin kết hợp cho phép xác định **một `Instant` duy nhất**. Với giờ địa phương `09:00` và offset `+07:00`, thời điểm UTC là `02:00Z`.

~~~text
2026-01-15T09:00+07:00
└─ LocalDateTime ─┘└offset┘
          |
          | UTC = local clock - offset
          v
2026-01-15T02:00:00Z
~~~

Công thức định hướng, áp dụng cho cùng lịch ISO và offset hợp lệ:

**UTC instant = local date-time − offset UTC**.

Do đó khi chỉ thay offset nhưng vẫn giữ local date-time, instant **phải thay đổi**. Ngược lại, khi yêu cầu giữ instant, local date-time **phải được điều chỉnh** để phù hợp offset mới.

`ZoneOffset.ofHours(-5)` là **offset cố định**, không phải khẳng định đang ở New York hoặc một thành phố nào khác. Offset không chứa quy tắc đổi giờ mùa hè (DST). Địa phương như `America/New_York` cần `ZoneId`, vì offset thực tế có thể thay đổi theo ngày.

### So với các kiểu Java khác

| Kiểu | Dữ liệu chứa bên trong | Có xác định instant? | Mục đích |
| --- | --- | --- | --- |
| `LocalDateTime` | Ngày giờ địa phương, không offset/zone | Chưa | Ngày giờ đồng hồ đang chờ ngữ cảnh |
| `OffsetDateTime` | Ngày giờ địa phương + offset | Có | Diễn đạt thời điểm với offset cụ thể |
| `ZonedDateTime` | Ngày giờ địa phương + `ZoneId` + offset đã giải quyết | Có | Diễn đạt thời điểm theo quy tắc vùng |
| `Instant` | Thời điểm tuyệt đối trên UTC timeline | Có | Ghi log, so sánh timestamp, trao đổi mốc sự kiện |

Một `OffsetDateTime` như `2026-01-15T09:00+07:00` đủ để biết sự kiện xảy ra lúc `2026-01-15T02:00:00Z`, nhưng không cho biết **tên khu vực địa lý**. Đây là khác biệt giữa `ZoneOffset` và `ZoneId`.

## 2. `withOffsetSameInstant()`: đổi cách nhìn nhưng không đổi sự kiện

Khi cần hiển thị **cùng một sự kiện** theo offset khác, dùng:

~~~java
OffsetDateTime vietnamTime =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

OffsetDateTime minusFive =
        vietnamTime.withOffsetSameInstant(ZoneOffset.ofHours(-5));

System.out.println(vietnamTime);
// 2026-01-15T09:00+07:00

System.out.println(minusFive);
// 2026-01-14T21:00-05:00
~~~

Cả hai đều ứng với **`2026-01-15T02:00:00Z`**:

| Giá trị | Ngày giờ đồng hồ | Offset | UTC instant |
| --- | --- | --- | --- |
| Ban đầu | `2026-01-15T09:00` | `+07:00` | `2026-01-15T02:00:00Z` |
| `withOffsetSameInstant(-05:00)` | `2026-01-14T21:00` | `-05:00` | `2026-01-15T02:00:00Z` |

Khi chuyển từ `+07:00` xuống `-05:00`, offset giảm **12 giờ**. Để mốc UTC không đổi, đồng hồ địa phương cũng lùi **12 giờ**: 09:00 ngày 15 thành 21:00 ngày 14.

**Bất biến quan trọng** của phương thức:

~~~java
original.toInstant().equals(
        original.withOffsetSameInstant(newOffset).toInstant())
// true nếu chuyển đổi thành công.
~~~

Đoạn trên là **biểu thức** Java đặt trong một method, với `original` và `newOffset` đã khai báo như ví dụ mở đầu. Đây là thuộc tính cần ưu tiên kiểm tra trong unit test.

### Trường hợp nên dùng

- Hiển thị một timestamp cho đối tác hoặc hệ thống yêu cầu offset khác, trong khi **sự kiện gốc không thay đổi**.
- Chuẩn hóa một `OffsetDateTime` về UTC mà giữ instant:

~~~java
OffsetDateTime utcView =
        original.withOffsetSameInstant(ZoneOffset.UTC);
// 2026-01-15T02:00Z
~~~

- Trước khi so sánh timestamp ở nhiều offset: thường còn đơn giản hơn nếu dùng `toInstant()` trực tiếp, không cần đổi đối tượng.

**Không được hiểu `withOffsetSameInstant()` là “đổi múi giờ địa lý”.** Nó chỉ đổi tới offset bạn cung cấp; nếu mục đích là giờ tại Paris hoặc New York vào một ngày cụ thể, nên chuyển qua `ZoneId` và quy tắc vùng.

## 3. `withOffsetSameLocal()`: giữ đồng hồ, diễn giải thành sự kiện khác

Nếu bài toán yêu cầu giữ nguyên `2026-01-15T09:00` nhưng gắn offset `-05:00`, dùng:

~~~java
OffsetDateTime original =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

OffsetDateTime reinterpreted =
        original.withOffsetSameLocal(ZoneOffset.ofHours(-5));

System.out.println(reinterpreted);
// 2026-01-15T09:00-05:00

System.out.println(reinterpreted.toInstant());
// 2026-01-15T14:00:00Z
~~~

So với `original.toInstant()` là `2026-01-15T02:00:00Z`, mốc mới **muộn hơn 12 giờ**. Giá trị ngày giờ địa phương không đổi, nhưng cùng chuỗi số giờ 09:00 được **hiểu là 09:00 tại offset khác**, nên thực chất đang mô tả một sự kiện khác.

| Giá trị | Ngày giờ đồng hồ | Offset | UTC instant |
| --- | --- | --- | --- |
| Ban đầu | `2026-01-15T09:00` | `+07:00` | `2026-01-15T02:00:00Z` |
| `withOffsetSameLocal(-05:00)` | `2026-01-15T09:00` | `-05:00` | `2026-01-15T14:00:00Z` |

**Bất biến quan trọng** của phương thức:

~~~java
original.toLocalDateTime().equals(
        original.withOffsetSameLocal(newOffset).toLocalDateTime())
// true nếu chuyển đổi thành công.
~~~

Đoạn trên là **biểu thức** Java nằm trong method, với biến từ ví dụ đầu bài.

### Trường hợp nên dùng

- Sửa **ngữ cảnh offset của một giờ đồng hồ cố định** vì đầu vào trước đó đã bị gắn sai offset, mà yêu cầu nghiệp vụ xác nhận local time là đúng.
- Diễn giải một lịch theo cùng giờ đồng hồ nhưng offset mới **theo chủ ý**; cần chấp nhận rằng instant thay đổi.

Nếu người dùng chỉ đổi lựa chọn vùng hiển thị sau khi thanh toán đã diễn ra, đây thường **không phải** phương thức đúng. Gán offset mới bằng `withOffsetSameLocal()` sẽ làm thay đổi timestamp của giao dịch.

**Cảnh báo:** Nếu hệ thống cần giữ lịch hẹn “mỗi ngày 09:00 tại một địa điểm”, chỉ lưu một offset cố định là chưa đủ khi địa điểm có DST. Hãy lưu `LocalTime` hoặc `LocalDateTime` của lịch hẹn **cùng `ZoneId` và chính sách DST**, thay vì mặc định đổi offset mỗi khi lịch chuyển mùa.

## 4. Bảng quyết định ngắn gọn

| Câu hỏi nghiệp vụ | Phép chuyển | Cái được giữ | Cái thay đổi |
| --- | --- | --- | --- |
| “Cho tôi xem **chính sự kiện này** ở offset khác” | `withOffsetSameInstant` | `Instant` | Local date-time, offset |
| “Giờ đồng hồ 09:00 là đúng, chỉ sửa **offset được gắn**” | `withOffsetSameLocal` | `LocalDateTime` | Offset, `Instant` |
| “Hiển thị sự kiện này theo **vùng New York** vào đúng ngày xảy ra” | `toInstant().atZone(ZoneId.of("America/New_York"))` | `Instant` | Ngày giờ, offset theo zone, ID vùng |
| “Tạo sự kiện ở 09:00 tại **vùng Paris**” | `LocalDateTime` + `ZoneId`, giải quyết gap/overlap | Ý định giờ địa phương theo chính sách | Offset/instant được xác định theo quy tắc vùng |
| “Lưu mốc sự kiện để xử lý toàn cầu” | `toInstant()` | `Instant` | Bỏ dạng local và offset trên giá trị đích |

**Quy tắc chọn nhanh:** Nếu có một sự kiện đã xảy ra và không được phép thay đổi mốc UTC, **giữ instant**. Nếu bài toán cho phép “đặt lại 09:00” dưới một offset mới, **giữ local** và hiểu rõ rằng đang thay mốc UTC.

## 5. Chương trình Java 17+ chạy được và kết quả chính xác

Tạo tệp **`OffsetSwitchDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class OffsetSwitchDemo {
    public static void main(String[] args) {
        OffsetDateTime original =
                OffsetDateTime.parse("2026-01-15T09:00:00+07:00");
        ZoneOffset target = ZoneOffset.ofHours(-5);

        OffsetDateTime sameInstant =
                original.withOffsetSameInstant(target);
        OffsetDateTime sameLocal =
                original.withOffsetSameLocal(target);

        System.out.println("original = " + original);
        System.out.println("originalInstant = " + original.toInstant());
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("sameInstantUtc = "
                + sameInstant.toInstant());
        System.out.println("sameLocal = " + sameLocal);
        System.out.println("sameLocalUtc = "
                + sameLocal.toInstant());

        System.out.println("sameInstantCheck = "
                + original.isEqual(sameInstant));
        System.out.println("sameLocalCheck = "
                + original.isEqual(sameLocal));
        System.out.println("localUnchanged = "
                + original.toLocalDateTime()
                    .equals(sameLocal.toLocalDateTime()));
        System.out.println("instantEqEquals = "
                + original.equals(sameInstant));

        System.out.println("crossDate = "
                + original.withOffsetSameInstant(ZoneOffset.UTC));

        Instant event = Instant.parse("2024-10-27T00:30:00Z");
        ZonedDateTime paris =
                event.atZone(ZoneId.of("Europe/Paris"));
        System.out.println("parisZone = " + paris);
        System.out.println("offsetAsFixed = "
                + event.atOffset(ZoneOffset.ofHours(2)));

        System.out.println("simpleDiffHours = "
                + Duration.between(
                        original.toInstant(),
                        sameLocal.toInstant()).toHours());

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX");
        System.out.println("pattern = "
                + sameInstant.format(formatter));
    }
}
~~~

Biên dịch và chạy ở thư mục chứa tệp:

~~~bash
javac OffsetSwitchDemo.java
java OffsetSwitchDemo
~~~

Kết quả:

~~~text
original = 2026-01-15T09:00+07:00
originalInstant = 2026-01-15T02:00:00Z
sameInstant = 2026-01-14T21:00-05:00
sameInstantUtc = 2026-01-15T02:00:00Z
sameLocal = 2026-01-15T09:00-05:00
sameLocalUtc = 2026-01-15T14:00:00Z
sameInstantCheck = true
sameLocalCheck = false
localUnchanged = true
instantEqEquals = false
crossDate = 2026-01-15T02:00Z
parisZone = 2024-10-27T02:30+02:00[Europe/Paris]
offsetAsFixed = 2024-10-27T02:30+02:00
simpleDiffHours = 12
pattern = 2026-01-14 21:00 -05:00
~~~

Các biểu thức cốt lõi và stdout được kiểm tra bằng Java. Trong chương trình, các instant là dữ liệu cố định, không lấy ngày giờ hệ thống nên kết quả có thể chạy lại. Phần Paris phụ thuộc quy tắc múi giờ của `Europe/Paris` theo cơ sở dữ liệu `tzdb` trong runtime Java, nhưng ví dụ lịch sử năm 2024 được hỗ trợ trong các bản Java có dữ liệu vùng thông thường.

Phân tích:

- `sameInstantUtc` **bằng** `originalInstant`, dù local time đổi từ 09:00 sang 21:00 ngày hôm trước.
- `sameLocalUtc` **khác** `originalInstant` đúng 12 giờ, dù cả hai đều có đồng hồ 09:00.
- `sameInstantCheck = true` do `isEqual` so sánh cùng một instant.
- `instantEqEquals = false` vì `equals` của `OffsetDateTime` kiểm tra **cả ngày giờ địa phương và offset**, không chỉ mốc UTC.
- `crossDate = 2026-01-15T02:00Z` minh họa offset chuẩn UTC; cách định dạng `toString()` có thể dùng `Z` thay cho `+00:00`.

## 6. Offset khác múi giờ địa lý: không tự suy ra DST

`ZoneOffset` là một **độ lệch tĩnh** so với UTC trong giá trị `OffsetDateTime`. Nó không chứa lịch sử hoặc quy tắc chuyển giờ của bất kỳ địa điểm nào. Ngược lại, `ZoneId` như `Europe/Paris` có thể cho offset `+01:00` hoặc `+02:00` tùy ngày.

Ví dụ mốc UTC:

~~~java
Instant event = Instant.parse("2024-10-27T00:30:00Z");

OffsetDateTime fixedOffset =
        event.atOffset(ZoneOffset.ofHours(2));
// 2024-10-27T02:30+02:00

ZonedDateTime parisView =
        event.atZone(ZoneId.of("Europe/Paris"));
// 2024-10-27T02:30+02:00[Europe/Paris]
~~~

Hai cách hiển thị này có **cùng local time, cùng offset và cùng instant ở chính mốc đó**, nhưng đối tượng `fixedOffset` không biết gì về Paris. Nếu đổi mốc sang mùa đông hoặc một năm khác, **quy tắc Paris có thể cho offset khác**, còn `ZoneOffset.ofHours(2)` vẫn là `+02:00`.

### Vì sao `withOffsetSameLocal` không phải “xử lý DST”?

Trong DST overlap, cùng giờ địa phương có thể xảy ra hai lần với hai offset; đổi offset trong `OffsetDateTime` có thể đổi giữa hai instant **nếu các offset hợp lệ cho cùng vùng/ngày**. Nhưng `OffsetDateTime` **không kiểm tra tính hợp lệ đối với một `ZoneId`**, vì nó không lưu ZoneId.

Nếu input là `2024-10-27T02:30` ở Paris, `ZoneId.of("Europe/Paris").getRules().getValidOffsets(local)` có hai lựa chọn `+02:00` và `+01:00`. Muốn chọn lần nào phải có **quy tắc nghiệp vụ**. Nếu local time rơi vào DST gap, có thể **không có offset hợp lệ**.

Không tự động gọi `withOffsetSameLocal` mỗi khi mùa thay đổi. Với **lịch lặp theo giờ địa phương**, dùng ZoneId để tính từng lần. Với **một mốc đã xảy ra**, ưu tiên `Instant` rồi `atZone(zone)`.

### Chuyển `OffsetDateTime` tới vùng múi giờ thật

~~~java
OffsetDateTime source =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

ZonedDateTime atParis =
        source.atZoneSameInstant(ZoneId.of("Europe/Paris"));
// 2026-01-15T03:00+01:00[Europe/Paris]
~~~

*Đoạn minh họa ở trong method với các import `java.time` cần thiết.* `atZoneSameInstant()` giữ mốc UTC và để ZoneRules tự chọn offset của Paris ở thời điểm đó. Cũng có thể viết `source.toInstant().atZone(parisZone)`. Đây là lựa chọn phù hợp khi câu hỏi thực sự là **“mấy giờ tại Paris?”**, không phải **“nếu offset là -05:00?”**.

## 7. Sự khác biệt khi so sánh: `equals`, `isEqual` và `Instant`

Dùng lại ví dụ:

~~~java
OffsetDateTime a =
        OffsetDateTime.parse("2026-01-15T09:00+07:00");
OffsetDateTime b = a.withOffsetSameInstant(ZoneOffset.ofHours(-5));

boolean sameRepresentation = a.equals(b);
// false: khác local date-time và offset.

boolean sameEvent = a.isEqual(b);
// true: cùng instant.

boolean sameUtc = a.toInstant().equals(b.toInstant());
// true.
~~~

`equals()` của `OffsetDateTime` trả `true` chỉ khi ngày giờ địa phương và offset bằng nhau. `isEqual()` so sánh **thời điểm thực** và bỏ qua việc biểu diễn ở offset nào. Các phép `isBefore()` và `isAfter()` cũng so sánh dựa trên instant.

Nếu hệ thống phân loại hai log cùng timestamp, không dùng `equals()` của `OffsetDateTime` làm tiêu chí duy nhất khi các nguồn có thể gửi các offset khác nhau. Dùng `toInstant()` hoặc `isEqual()` theo mục tiêu nghiệp vụ.

**Lưu ý khi sắp xếp:** `OffsetDateTime.compareTo()` so sánh theo instant trước, và khi instant bằng nhau còn so sánh local date-time để tạo thứ tự nhất quán với `equals()`. Nếu chỉ muốn thứ tự trên UTC timeline, nên so sánh `toInstant()` hoặc dùng `timeLineOrder()`. Không thay `isEqual()` bằng phép `compareTo()==0` nếu điều kiện duy nhất cần kiểm tra là **cùng instant**, vì hai biểu diễn offset khác nhau của cùng instant có thể cho `compareTo()!=0`.

## 8. Những trường hợp thực tế dễ gây mất dữ liệu

### 8.1. Giao dịch thanh toán và audit

Một giao dịch xảy ra lúc **`2026-01-15T02:00:00Z`**. Bản ghi nhận từ dịch vụ A có `2026-01-15T09:00+07:00`. Nếu dịch vụ B yêu cầu gửi dữ liệu dạng offset `-05:00`, phải dùng **`withOffsetSameInstant(-05:00)`** để gửi `2026-01-14T21:00-05:00`.

Nếu gọi `withOffsetSameLocal(-05:00)`, kết quả sẽ mang `2026-01-15T14:00:00Z`: giao dịch trong log **bị đẩy muộn 12 giờ**, dù user interface vẫn nhìn thấy “09:00”. Với dữ liệu tài chính hoặc audit, đây là lỗi logic nghiêm trọng.

### 8.2. Sửa dữ liệu import gắn sai offset

Một nguồn dữ liệu nói “09:00 địa phương” nhưng gắn nhầm `+07:00` dù theo hợp đồng thực tế phải là `-05:00`. Nếu đã xác minh **chính các trường 09:00 là đúng** và offset là dữ liệu bị sai, việc dùng **`withOffsetSameLocal(-05:00)`** có thể thích hợp để **diễn giải lại** dữ liệu.

Tuy nhiên, đây là **sửa ý nghĩa timestamp**, không phải thao tác hiển thị vô hại. Hệ thống nên lưu thông tin nguồn/sai lệch/ai cho phép chỉnh, đặc biệt nếu dữ liệu từng được dùng để tính hạn hoặc chứng minh thời điểm.

### 8.3. Cuộc hẹn “09:00 tại New York”

Nếu người dùng muốn tạo cuộc hẹn **09:00 ở New York**, không bắt đầu bằng offset tự chọn `-05:00` cho mọi ngày. New York có mùa sử dụng `-04:00`. Hãy dùng:

~~~java
LocalDateTime appointment =
        LocalDateTime.of(2026, 7, 15, 9, 0);
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime zoned = appointment.atZone(newYork);
// 2026-07-15T09:00-04:00[America/New_York]
~~~

Lời gọi `atZone` mặc định có chính sách cho giờ không tồn tại (DST gap) hoặc lặp (DST overlap). Với lịch nhạy cảm, phải kiểm tra `getValidOffsets(appointment)` và áp chính sách xác định trước; một offset không đủ cho bài toán lịch lặp.

### 8.4. Lưu trữ API/JSON

Ví dụ hợp đồng có timestamp:

~~~json
{
  "occurredAt": "2026-01-15T09:00:00+07:00",
  "viewerOffset": "-05:00"
}
~~~

Để hiển thị theo `viewerOffset` nhưng giữ sự kiện:

~~~java
OffsetDateTime occurredAt =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");
ZoneOffset viewerOffset = ZoneOffset.of("-05:00");

OffsetDateTime shown =
        occurredAt.withOffsetSameInstant(viewerOffset);
// 2026-01-14T21:00-05:00
~~~

Trong API, trường `occurredAt` biểu diễn mốc sự kiện. Nếu muốn lưu event “khi nào”, có thể chuẩn hóa qua `Instant` khi truyền giữa các hệ thống. **Không mặc nhiên tin rằng mọi cột SQL timestamp giữ lại offset gốc**; một số kiểu database lưu mốc chuẩn hóa mà không bảo tồn biểu diễn offset ban đầu. Nếu cần kiểm toán offset nguồn, lưu metadata riêng theo đặc tả schema.

## 9. Đọc, định dạng và phân biệt dấu offset

Java có thể parse chuỗi ISO 8601 có offset:

~~~java
OffsetDateTime x =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

LocalDateTime local = x.toLocalDateTime();
// 2026-01-15T09:00

ZoneOffset offset = x.getOffset();
// +07:00

Instant timestamp = x.toInstant();
// 2026-01-15T02:00:00Z
~~~

`toLocalDateTime()` cố ý **bỏ offset** nên không còn đủ dữ liệu để dựng lại một instant duy nhất. Đừng lưu giá trị đó thay cho timestamp nếu cần truy vết thời điểm tuyệt đối.

Định dạng trong một offset:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm XXX");
String label = x.format(formatter);
// 15/01/2026 09:00 +07:00
~~~

*Các đoạn minh họa nằm trong method; cần import `java.time` và `java.time.format.DateTimeFormatter`.*

Dấu offset mang ý nghĩa:

- `+07:00`: local time **nhanh hơn UTC 7 giờ**; lấy UTC bằng local trừ 7 giờ.
- `-05:00`: local time **chậm hơn UTC 5 giờ**; lấy UTC bằng local cộng 5 giờ.
- `Z`: ký hiệu ISO cho offset **`+00:00`** (UTC), không phải tên vùng địa lý.

Một người dùng nhìn thấy giờ địa phương có thể cần thêm vùng `Asia/Ho_Chi_Minh` hoặc `America/New_York` để giải thích quy tắc địa điểm; offset `+07:00` chỉ mô tả một độ lệch cụ thể.

## 10. Quy tắc bất biến và giới hạn của phép chuyển

`OffsetDateTime`, `ZoneOffset`, `Instant` là các kiểu giá trị bất biến. Hai phương thức `withOffsetSameInstant()` và `withOffsetSameLocal()` **trả về giá trị mới về mặt ngữ nghĩa**, không sửa đối tượng gốc:

~~~java
OffsetDateTime value =
        OffsetDateTime.parse("2026-01-15T09:00:00+07:00");

value.withOffsetSameInstant(ZoneOffset.UTC);
// Bỏ kết quả; value không đổi.

value = value.withOffsetSameInstant(ZoneOffset.UTC);
// Lúc này biến value giữ biểu diễn UTC của cùng instant.
~~~

Phân biệt **biến được gán lại** với **đối tượng bị sửa**. `value = ...` đổi giá trị tham chiếu của biến; các đối tượng thời gian cũ vẫn bất biến.

`ZoneOffset` được Java giới hạn trong khoảng **-18:00 tới +18:00**. Offset ngoài giới hạn không hợp lệ. Việc đổi sang offset mới cũng có thể gặp lỗi nếu ngày giờ kết quả vượt phạm vi biểu diễn của `OffsetDateTime`, ví dụ gần giới hạn năm hỗ trợ; ứng dụng cần xử lý đầu vào và ngoại lệ phù hợp thay vì mặc định mọi giá trị cực hạn đều chuyển được.

Với các giá trị thông thường, phép chuyển `withOffsetSameInstant` hoạt động dựa trên **độ chênh của hai offset** để cộng/trừ vào local date-time; bản thân offset mới không mang DST. `withOffsetSameLocal` chỉ thay offset, giữ nguyên các trường local date-time, và instant được suy lại theo offset vừa gắn.

## 11. Lỗi thường gặp và cách kiểm tra

| Lỗi | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| Dùng `withOffsetSameLocal` để đổi giờ xem của một giao dịch | Instant bị thay đổi | `withOffsetSameInstant` |
| Dùng `withOffsetSameInstant` khi sửa offset nhập sai nhưng giờ đồng hồ đúng | Local date-time bị dịch | `withOffsetSameLocal` sau khi xác minh ý định |
| Coi `-05:00` tương đương New York quanh năm | New York có DST | `ZoneId.of("America/New_York")` |
| Coi `OffsetDateTime` giữ vùng địa lý | Chỉ giữ offset, không giữ IANA region | Dùng `ZonedDateTime` khi cần region |
| Bỏ giá trị trả về của `withOffset...` | Đối tượng cũ bất biến | Gán lại hoặc tạo biến kết quả |
| Coi hai `OffsetDateTime` có `equals()==false` là hai thời điểm khác nhau | Khác biểu diễn vẫn có thể cùng instant | `isEqual()` hoặc `toInstant()` |
| Dùng `toLocalDateTime()` làm timestamp chính | Mất offset và mốc UTC duy nhất | Giữ `Instant` hoặc offset date-time |
| Hiển thị ngày/tháng sau đổi offset nhưng nghĩ phần ngày không thể đổi | Có thể lùi/sang ngày kế tiếp | Test qua nửa đêm và giao thừa |
| Chuyển đổi bằng cộng giờ thủ công vào `LocalDateTime` | Dễ sai dấu và bỏ ràng buộc offset | Dùng API `withOffsetSameInstant` |
| Đổi offset cho lịch lặp theo địa điểm mà không dùng quy tắc DST | Giờ địa phương trong tương lai có thể sai | Dùng `LocalDateTime`/`ZonedDateTime` và `ZoneId` |

### Câu hỏi tự kiểm tra

1. **`2026-01-15T09:00+07:00` là mấy giờ UTC?** `2026-01-15T02:00:00Z`.
2. **Đổi sang `-05:00` nhưng giữ instant cho kết quả gì?** `2026-01-14T21:00-05:00`, vẫn là `2026-01-15T02:00:00Z`.
3. **Đổi sang `-05:00` nhưng giữ local date-time cho kết quả gì?** `2026-01-15T09:00-05:00`, tức `2026-01-15T14:00:00Z`.
4. **Phép đổi nào có thể đổi phần ngày dù sự kiện không đổi?** `withOffsetSameInstant`, vì nó đổi giờ đồng hồ theo offset.
5. **Phép đổi nào có thể làm thay đổi sự kiện trên timeline dù đồng hồ giữ nguyên?** `withOffsetSameLocal`.
6. **Hai `OffsetDateTime` khác offset nhưng cùng instant có `equals()==true` không?** Thông thường **không**; dùng `isEqual()` nếu chỉ cần kiểm tra cùng mốc UTC.
7. **Muốn xem một instant tại New York, nên dùng offset `-05:00` cố định?** Không nếu mục tiêu là vùng New York; dùng `ZoneId` để lấy offset đúng tại instant đó.
8. **Nếu cùng một giờ đồng hồ được nhập vào dữ liệu nhưng chưa xác định offset, có thể kết luận instant không?** Chưa; cần offset hợp lệ hoặc `ZoneId` cùng chính sách giải quyết gap/overlap.

**Ghi nhớ:** `withOffsetSameInstant()` **giữ nguyên thời điểm**, thay ngày giờ địa phương; `withOffsetSameLocal()` **giữ nguyên ngày giờ địa phương**, thay thời điểm. Quyết định đúng phụ thuộc vào việc bạn muốn bảo toàn **sự kiện đã xảy ra** hay **giờ đồng hồ được người dùng xác nhận**, không phụ thuộc vào phương thức nào có tên ngắn hơn.