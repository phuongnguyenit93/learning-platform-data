# Khi nào LocalDateTime phù hợp và khi nào dễ làm mất ý nghĩa thời gian

`LocalDateTime` trong `java.time` biểu diễn **ngày lịch và giờ trên đồng hồ địa phương**, ví dụ `2024-03-01T09:00:00`. Nó chứa năm, tháng, ngày, giờ, phút, giây và nano giây, nhưng **không chứa múi giờ (`ZoneId`), độ lệch UTC (`ZoneOffset`) hay một thời điểm tuyệt đối (`Instant`)**.

Điều đó không phải thiếu sót của Java: đây là một kiểu dữ liệu có chủ đích. `LocalDateTime` rất đúng khi yêu cầu chỉ nói đến **ngày và giờ trên lịch**, nhưng dễ gây lỗi nếu ứng dụng vô tình coi nó là dấu thời gian đủ để xác định một sự kiện đã xảy ra trên trục thời gian.

**Câu hỏi quyết định:** “Giá trị này cho biết *ngày/giờ trên mặt đồng hồ* hay cho biết *một thời điểm duy nhất trên toàn thế giới*?” Hai ý nghĩa đòi hỏi dữ liệu khác nhau.

## 1. Chính xác LocalDateTime chứa gì?

Ví dụ:

```java
import java.time.LocalDateTime;

LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
System.out.println(appointment); // 2024-03-01T09:00
```

Đây là đoạn minh họa để đặt trong phương thức Java. Đối tượng trên cho biết “ngày 01/03/2024, lúc 09:00” nhưng **chưa cho biết** 09:00 đó là tại Hà Nội, New York hay nơi nào khác. Từ nó **không thể** suy ra chính xác giờ UTC.

Các thành phần:

| Trường/đặc tính | LocalDateTime có? | Ví dụ |
| --- | --- | --- |
| Năm–tháng–ngày | Có | `2024-03-01` |
| Giờ–phút–giây–nano giây | Có | `09:00:00.000000000` |
| Múi giờ theo vùng (`ZoneId`) | Không | Không biết `Asia/Ho_Chi_Minh` |
| Offset so với UTC | Không | Không biết `+07:00` |
| Thời điểm tuyệt đối | Không | Không suy được `Instant` |
| Quy tắc lịch ISO | Có | Kiểm tra ngày hợp lệ khi tạo đối tượng |

Vì không có zone/offset, một `LocalDateTime` riêng lẻ cũng không thể cho biết liệu đồng hồ địa phương đã rơi vào khoảng giờ mùa hè bị bỏ qua hoặc bị lặp hay chưa.

## 2. So sánh các kiểu thời gian để chọn đúng

| Kiểu | Nội dung | Dùng khi |
| --- | --- | --- |
| `LocalDate` | Chỉ ngày lịch | Ngày sinh, ngày hóa đơn, ngày nghỉ |
| `LocalTime` | Chỉ giờ địa phương | Giờ mở cửa hằng ngày |
| `LocalDateTime` | Ngày + giờ, không có zone/offset | Giờ hẹn theo lịch địa phương khi chưa gắn vùng; dữ liệu “ngày và giờ” thuần |
| `OffsetDateTime` | Ngày + giờ + offset như `+07:00` | Timestamp có offset cụ thể trong giao thức hoặc hợp đồng dữ liệu |
| `ZonedDateTime` | Ngày + giờ + `ZoneId` và offset đã phân giải | Lịch hẹn theo vùng có quy tắc DST/lịch sử, khi cần biểu diễn giờ của một vùng |
| `Instant` | Mốc thời gian tuyệt đối | Sự kiện đã xảy ra, audit, createdAt, so sánh thời điểm |
| `Duration` | Độ dài theo giây/nano giây | Đo thời lượng trôi qua giữa các thời điểm |

**`OffsetDateTime`** có offset đủ để xác định `Instant` của giá trị đang xét, nhưng không giữ quy tắc múi giờ cho các lần lặp trong tương lai. **`ZonedDateTime`** gắn vùng IANA như `Europe/Paris` hoặc `America/New_York` và dùng quy tắc vùng để biểu diễn thời điểm địa phương. Nếu bài toán là “09:00 mỗi thứ Hai ở Paris”, hãy giữ quy tắc lặp **và `ZoneId`**, không chỉ một `OffsetDateTime` của tuần đầu.

## 3. Khi nào LocalDateTime thực sự phù hợp?

### 3.1. Ngày giờ lịch địa phương là dữ liệu cần lưu

Ví dụ người dùng nhập “01/03/2024 lúc 09:00”, nhưng tại thời điểm nhập, nghiệp vụ chưa xác định địa điểm/múi giờ cho buổi hẹn. `LocalDateTime` biểu diễn chính xác phần thông tin **đã được biết**:

```java
LocalDateTime requestedLocalTime = LocalDateTime.of(2024, 3, 1, 9, 0);
// Chưa thể tính timestamp UTC nếu chưa biết vùng hoặc offset.
```

Đây là đoạn minh họa cần import `java.time.LocalDateTime`. Bạn có thể giữ giá trị này ở tầng giao diện hoặc trạng thái “lịch hẹn chờ chọn chi nhánh”. **Trước khi tạo một thời điểm đặt lịch duy nhất**, hệ thống phải thu thêm vùng/offset và xử lý những trường hợp giờ địa phương không rõ ràng.

### 3.2. Chỉnh sửa thành phần lịch mà không cần mốc UTC ngay lúc đó

`LocalDateTime` tiện cho nghiệp vụ “chuyển cuộc họp trên lịch sang cùng giờ ngày kế tiếp”, xây ngày/giờ từ một form hoặc thao tác với các thành phần:

```java
LocalDateTime original = LocalDateTime.of(2024, 3, 1, 9, 0);
LocalDateTime nextWeek = original.plusWeeks(1); // 2024-03-08T09:00
LocalDateTime newTime = original.withHour(14);  // 2024-03-01T14:00
```

Đây là **phép tính trên trường ngày/giờ địa phương**. Nó chưa quyết định chênh lệch thực giữa hai thời điểm trên trục UTC. Nếu phép cộng băng qua một chuyển đổi DST, cần áp zone sau đó và xử lý chính sách vùng. `plusDays(1)` trên một giờ địa phương không bảo đảm tương đương 24 giờ thực tại mọi múi giờ.

### 3.3. Trao đổi một giá trị mà hợp đồng nói rõ nó là “local wall time”

Một API có thể có hai trường:

```json
{
  "appointmentLocal": "2024-03-01T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Ở đây `appointmentLocal` phù hợp với `LocalDateTime`, nhưng **cả hợp đồng** mới có đủ vùng để xác định ý nghĩa lịch hẹn. Tên trường cần thể hiện rõ “local”. Nếu nghiệp vụ yêu cầu một `Instant` để đặt hàng hoặc nhắc lịch, phía máy chủ vẫn phải phân giải hai trường đó và xử lý vùng giờ.

Nếu dữ liệu thật sự chỉ cần ngày sinh, dùng `LocalDate`; nếu chỉ cần giờ mở cửa hằng ngày, dùng `LocalTime`. Không dùng `LocalDateTime` theo thói quen khi một nửa dữ liệu là không cần thiết.

## 4. Khi nào LocalDateTime làm mất ý nghĩa thời gian?

### 4.1. Chuyển một sự kiện thực thành LocalDateTime rồi bỏ zone

Giả sử cùng một sự kiện xảy ra ở `2024-02-29T23:30:00Z`:

```java
import java.time.*;

Instant event = Instant.parse("2024-02-29T23:30:00Z");

LocalDateTime utcView =
        LocalDateTime.ofInstant(event, ZoneOffset.UTC);
LocalDateTime vietnamView =
        LocalDateTime.ofInstant(event, ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utcView);     // 2024-02-29T23:30
System.out.println(vietnamView); // 2024-03-01T06:30
```

**Hai `LocalDateTime` khác nhau cùng biểu diễn một `Instant` ban đầu**, nếu giữ ngữ cảnh vùng của từng phép chuyển. Khi lưu riêng `2024-03-01T06:30` mà bỏ `Asia/Ho_Chi_Minh`, không còn biết đây là giờ Việt Nam hay một nơi khác, và không thể khôi phục duy nhất `Instant` gốc.

Ví dụ sai về ngữ nghĩa:

```java
// Đây là LocalDateTime tại UTC, không phải một Instant có thông tin UTC!
LocalDateTime utcLookingValue = LocalDateTime.ofInstant(
        event, ZoneOffset.UTC);

// Nếu một máy khác coi cùng LocalDateTime là giờ máy nó,
// thời điểm được suy ra có thể khác.
Instant mistaken = utcLookingValue
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

Đoạn này cần import `java.time.*`. `mistaken` không còn là `event` vì **giờ UTC bị gắn nhầm vùng Việt Nam**. Dùng `Instant` xuyên suốt để lưu thời điểm sự kiện, rồi chỉ chuyển sang `LocalDateTime` để biểu diễn ở một vùng cụ thể khi cần.

### 4.2. Lưu sự kiện “đã xảy ra” bằng local date-time không có vùng

Các trường như `createdAt`, `paidAt`, `sentAt`, `receivedAt`, `loginAt`, `jobStartedAt` thường có ý nghĩa là **một thời điểm thực**. Nếu máy A chạy UTC và máy B chạy giờ Việt Nam, hai bản ghi ghi `LocalDateTime.now()` có thể lệch bảy giờ dù cùng thời điểm.

Ví dụ:

```java
Instant createdAt = clock.instant(); // nguồn thời gian tường minh
ZonedDateTime display = createdAt.atZone(userZone);
```

Đây là đoạn trong service với các biến `clock` (`Clock`) và `userZone` (`ZoneId`) được truyền từ ngoài. Lưu giá trị có ngữ nghĩa `Instant`; hiển thị hoặc xác định ngày nghiệp vụ bằng zone thích hợp. Nếu database/driver không có ánh xạ `Instant` trực tiếp, phải quy định rõ lưu theo UTC với kiểu SQL/adapter và cách đọc tương ứng; tên kiểu SQL và quy tắc chuyển đổi khác nhau tùy DBMS.

### 4.3. Suy offset từ máy chủ hoặc gán UTC vô điều kiện

`LocalDateTime.now()` đọc thời điểm theo **múi giờ mặc định JVM**. `LocalDateTime.now(ZoneId.of("UTC"))` tạo một **giờ địa phương ứng với UTC**, nhưng đối tượng kết quả vẫn không mang thông tin zone. Gọi `localDateTime.toInstant(ZoneOffset.UTC)` chỉ đúng nếu hợp đồng đầu vào **thật sự bảo đảm** giá trị đó được diễn giải theo UTC.

**Không tự thêm ký tự “Z”** vào chuỗi `LocalDateTime` để biến nó thành thời điểm UTC. “Z” xác nhận offset zero nên phải dựa vào ý nghĩa dữ liệu thật, không phải thao tác nối chuỗi.

## 5. Từ LocalDateTime đến một thời điểm thực: phải có ngữ cảnh

Để biến `2024-03-01T09:00` thành một `Instant`, phải xác định **zone hoặc offset**. Với lịch hẹn ở Hà Nội:

```java
LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = appointment.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);
// 2024-03-01T09:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(instant);
// 2024-03-01T02:00:00Z
```

Đây là đoạn minh họa cần import `java.time.*`. `atZone(zone)` áp quy tắc vùng cho ngày giờ địa phương, tạo `ZonedDateTime` đã được phân giải. `toInstant()` lấy thời điểm tuyệt đối tương ứng. Với **một giờ không rơi vào chuyển đổi DST**, quy tắc vùng xác định duy nhất offset.

`LocalDateTime.toInstant(offset)` cũng tồn tại, nhưng bạn phải **có sẵn offset hợp lệ** cho tình huống đó. `ZoneOffset.ofHours(7)` chỉ mô tả `+07:00`, không thay thế mọi quy tắc lịch sử/DST của vùng IANA. Với lịch hẹn tại một địa điểm và quy tắc vùng có thể đổi theo thời gian, thường ưu tiên lưu **`ZoneId`** bên cạnh ý định giờ địa phương.

## 6. DST: giờ địa phương có thể không tồn tại hoặc có hai cách hiểu

Mỗi `LocalDateTime` gồm năm/tháng/ngày/giờ hợp lệ theo lịch ISO, nhưng **không có nghĩa nó hợp lệ như một thời điểm đồng hồ tại mọi vùng**. Một số vùng chuyển sang/ra khỏi giờ mùa hè (DST):

| Trạng thái | Số offset hợp lệ | Ý nghĩa |
| --- | ---: | --- |
| Bình thường | 1 | LocalDateTime và zone phân giải thành một `Instant` |
| *Gap* | 0 | Giờ địa phương không tồn tại do đồng hồ nhảy tới |
| *Overlap* | 2 | Một giờ trên đồng hồ xuất hiện hai lần với hai offset |

### 6.1. Gap: ngày 10/03/2024 tại New York

Ở `America/New_York`, đồng hồ chuyển từ 01:59:59 sang 03:00:00 trong ngày này. Do vậy **02:30 không tồn tại ở New York**, nhưng Java vẫn cho phép tạo `LocalDateTime`:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

int count = ny.getRules().getValidOffsets(gap).size(); // 0
ZonedDateTime adjusted = gap.atZone(ny);

System.out.println(adjusted);
// 2024-03-10T03:30-04:00[America/New_York]
```

`atZone` **tự điều chỉnh** giờ trong gap tiến lên theo độ dài gap. Đó là quy tắc mặc định của API, **không tự động là chính sách đúng của mọi nghiệp vụ**. Nếu lịch hẹn người dùng yêu cầu chính xác 02:30 và không được tự đổi sang 03:30, hãy kiểm tra `getValidOffsets(gap)` trước khi chấp nhận.

### 6.2. Overlap: ngày 03/11/2024 tại New York

Khi đồng hồ lùi, **01:30 xuất hiện hai lần**:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(ny.getRules().getValidOffsets(overlap));
// [-04:00, -05:00]

ZonedDateTime earlier = overlap.atZone(ny);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant()); // 2024-11-03T05:30:00Z
System.out.println(later.toInstant());   // 2024-11-03T06:30:00Z
```

Hai `Instant` **cách nhau một giờ** nhưng cùng có `LocalDateTime` bằng `2024-11-03T01:30`. `atZone` khi gặp overlap thường chọn offset **sớm hơn** (thường là offset mùa hè). Nếu lựa chọn này có ý nghĩa cho việc thanh toán, đặt chỗ hoặc vận hành, bạn phải nêu rõ chính sách và lưu kết quả đã phân giải, không bỏ thông tin offset.

Có thể dùng `ZoneRules.getValidOffsets(localDateTime)` để quyết định: 0 offset → từ chối hoặc điều chỉnh gap; 1 offset → chấp nhận; 2 offset → yêu cầu chọn cách diễn giải hoặc dùng quy tắc nghiệp vụ tường minh. Quy tắc vùng có thể cập nhật theo cơ sở dữ liệu múi giờ của JDK; đối với lịch hẹn tương lai, cần quyết định hệ thống giữ **ý định 09:00 tại địa phương** hay giữ **một `Instant` đã cố định** nếu luật múi giờ thay đổi.

## 7. Chương trình Java 17+ chạy đầy đủ

Tạo tệp **`LocalDateTimeMeaningDemo.java`**:

```java
import java.time.*;

public class LocalDateTimeMeaningDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-02-29T23:30:00Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("UTC wall time: "
                + LocalDateTime.ofInstant(event, ZoneOffset.UTC));
        System.out.println("VN wall time: "
                + LocalDateTime.ofInstant(event, vietnam));

        LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
        ZonedDateTime inVietnam = appointment.atZone(vietnam);
        System.out.println("VN appointment: " + inVietnam);
        System.out.println("VN instant: " + inVietnam.toInstant());

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("Gap valid offsets: "
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("Gap atZone: " + gap.atZone(newYork));

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        System.out.println("Overlap valid offsets: "
                + newYork.getRules().getValidOffsets(overlap));
        ZonedDateTime earlier = overlap.atZone(newYork);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("Earlier occurrence: " + earlier.toInstant());
        System.out.println("Later occurrence: " + later.toInstant());
    }
}
```

Biên dịch và chạy (Java 17 trở lên):

```bash
javac LocalDateTimeMeaningDemo.java
java LocalDateTimeMeaningDemo
```

**stdout thực tế** đã kiểm tra khi biên dịch mã ví dụ với `javac --release 17` và chạy:

```text
UTC wall time: 2024-02-29T23:30
VN wall time: 2024-03-01T06:30
VN appointment: 2024-03-01T09:00+07:00[Asia/Ho_Chi_Minh]
VN instant: 2024-03-01T02:00:00Z
Gap valid offsets: 0
Gap atZone: 2024-03-10T03:30-04:00[America/New_York]
Overlap valid offsets: [-04:00, -05:00]
Earlier occurrence: 2024-11-03T05:30:00Z
Later occurrence: 2024-11-03T06:30:00Z
```

Chương trình cho thấy ba điều khác biệt:

1. **Một `Instant` có nhiều biểu diễn `LocalDateTime`** tùy vùng.
2. **Một `LocalDateTime` có thể trở thành một thời điểm chính xác** khi thêm vùng và giải quyết quy tắc vùng.
3. **Một `LocalDateTime` trong DST có thể tương ứng 0 hoặc 2 thời điểm**: chỉ lưu local date-time làm mất thông tin cần thiết để định danh sự kiện.

## 8. Parse và format: dấu T không mang ý nghĩa UTC

Chuỗi ISO như `2024-03-01T09:00:00` là dạng biểu diễn tự nhiên của `LocalDateTime`. Chữ `T` ngăn phần ngày và phần giờ; **nó không chỉ UTC**.

```java
LocalDateTime local = LocalDateTime.parse("2024-03-01T09:00:00");
System.out.println(local); // 2024-03-01T09:00
```

Đoạn minh họa cần import `java.time.LocalDateTime`. So sánh các chuỗi:

| Chuỗi | Ý nghĩa | Kiểu phù hợp |
| --- | --- | --- |
| `2024-03-01` | Chỉ ngày | `LocalDate` |
| `2024-03-01T09:00:00` | Ngày + giờ địa phương, chưa có offset | `LocalDateTime` |
| `2024-03-01T09:00:00+07:00` | Ngày + giờ với offset +07:00 | `OffsetDateTime` |
| `2024-03-01T02:00:00Z` | Một thời điểm tại UTC | `Instant` |
| `2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]` | Ngày + giờ với vùng và offset đã phân giải | `ZonedDateTime` |

`LocalDateTime.parse` mặc định đọc **ISO local date-time**. Nếu chuỗi đầu vào có offset hoặc vùng, hãy parse vào kiểu tương ứng để **không bỏ dữ liệu**:

```java
OffsetDateTime providedOffset =
        OffsetDateTime.parse("2024-03-01T09:00:00+07:00");
Instant absolute = providedOffset.toInstant();
// 2024-03-01T02:00:00Z

ZonedDateTime providedZone = ZonedDateTime.parse(
        "2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]");
```

Đây là đoạn minh họa cần import `java.time.*`. Chuyển `providedOffset.toLocalDateTime()` là thao tác **cố ý bỏ offset**; chỉ làm khi nghiệp vụ muốn giữ thành phần ngày/giờ địa phương. Với định dạng tiếng Việt/tiếng Anh bằng tên tháng/thứ, hãy cung cấp `Locale` tường minh cho `DateTimeFormatter`. `Locale` quyết định ngôn ngữ định dạng, **không làm phát sinh `ZoneId`** trong `LocalDateTime`.

## 9. LocalDateTime.now() và sai khác giữa các máy

Các cách tạo giá trị “bây giờ” có hàm ý khác nhau:

```java
LocalDateTime first = LocalDateTime.now(); // zone mặc định JVM
LocalDateTime second = LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime third = LocalDateTime.now(clock); // sử dụng zone chứa trong Clock
```

Đây là đoạn minh họa cần import `java.time.*`; `clock` là biến `Clock` do bên ngoài cung cấp. `now()` không tham số phụ thuộc vùng mặc định của JVM và thời gian thực, do đó có thể đưa kết quả khác nhau vào ứng dụng chạy trên nhiều máy hoặc test sát nửa đêm.

Thiết kế tốt hơn là truyền **nguồn thời gian (`Clock`)** và **vùng nghiệp vụ (`ZoneId`)** vào service, đọc `Instant` một lần và chuyển đổi có chủ đích:

```java
import java.time.*;
import java.util.Objects;

public final class EventClock {
    private final Clock clock;
    private final ZoneId businessZone;

    public EventClock(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone = Objects.requireNonNull(businessZone, "businessZone");
    }

    public Instant nowInstant() {
        return clock.instant();
    }

    public LocalDateTime nowBusinessLocal() {
        Instant instant = clock.instant();
        return LocalDateTime.ofInstant(instant, businessZone);
    }
}
```

Đây là class độc lập có thể biên dịch với tên tệp `EventClock.java`, nhưng **không có `main`**, nên chỉ sử dụng như một thành phần trong ứng dụng hoặc test. Production có thể cấp `Clock.systemUTC()`; test có thể cấp `Clock.fixed(Instant.parse("2024-02-29T23:30:00Z"), ZoneOffset.UTC)` để tái lập kết quả.

**Chú ý:** nếu cần cả `nowInstant()` và `nowBusinessLocal()` của **cùng một sự kiện**, đừng gọi hai phương thức riêng rồi giả định cùng mốc thời gian. Lấy một `Instant` tại biên giao dịch, sau đó truyền nó qua các bước cần dùng.

## 10. Cộng ngày giờ: “một ngày lịch” có thể khác “24 giờ thực”

`LocalDateTime.plusDays(1)` tăng ngày/giờ trong miền lịch ISO, không có thông tin DST. Khi thêm zone, thời lượng thực giữa hai giá trị có thể khác 24 giờ.

Ví dụ một cuộc hẹn lúc **12:00** ngày 09/03 và 10/03/2024 ở New York:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime saturdayNoon = LocalDateTime.of(2024, 3, 9, 12, 0);
LocalDateTime sundayNoon = saturdayNoon.plusDays(1);

Instant start = saturdayNoon.atZone(ny).toInstant();
Instant end = sundayNoon.atZone(ny).toInstant();
long hours = Duration.between(start, end).toHours();
// 23 giờ (do chuyển sang DST)
```

Đây là đoạn minh họa cần import `java.time.*`. Nếu người dùng yêu cầu **“12:00 ngày mai theo giờ địa phương”**, phép tính theo ngày lịch có ý nghĩa. Nếu yêu cầu **“sau đúng 24 giờ”**, dùng `Duration.ofHours(24)` trên `Instant` để thể hiện độ dài thực. Không đánh đồng `Period.ofDays(1)` trong lịch với `Duration.ofDays(1)` là đúng 24 giờ thực trong mọi vùng.

Với lịch lặp “mỗi ngày 09:00 tại Paris”, cần giữ `LocalTime`, quy tắc ngày và `ZoneId` để tính từng lần, bởi offset theo UTC có thể thay đổi khi đến mùa khác.

## 11. Lưu trữ và API: tránh mất offset/zone âm thầm

Mỗi hệ quản trị cơ sở dữ liệu có quy tắc riêng cho các kiểu `TIMESTAMP`, `DATETIME`, `TIMESTAMP WITH TIME ZONE` và driver JDBC. **Đừng suy từ tên kiểu SQL rằng nó chắc chắn lưu đúng thông tin vùng IANA**. Cần kiểm tra hợp đồng của DBMS, driver, lớp ORM và cách đọc/ghi.

Quy tắc thiết kế ở cấp ứng dụng:

| Dữ liệu | Nên lưu gì? | Tại sao |
| --- | --- | --- |
| `createdAt`/`paidAt`/`sentAt` | `Instant` hoặc timestamp UTC có hợp đồng rõ | Bảo toàn thời điểm thực |
| Lịch hẹn tại chi nhánh theo giờ địa phương | `LocalDateTime` + `ZoneId`, chính sách DST; lưu thêm thời điểm đã phân giải nếu cần | Bảo toàn ý định giờ địa phương và thời điểm thực |
| Lịch lặp “09:00 mỗi thứ Hai” | Quy tắc lặp + `LocalTime` + `ZoneId` | Tính được lần tương lai theo quy tắc vùng |
| Ngày sinh/ngày nghỉ | `LocalDate` | Không tự ý biến ngày lịch thành timestamp |
| Sự kiện với offset đã được gửi qua API | `OffsetDateTime` hoặc `Instant`, giữ offset nếu nghiệp vụ cần | Không đánh mất offset của nguồn |
| Chỉ giờ mở cửa | `LocalTime` | Không cần gắn một ngày tùy ý |

Ví dụ một hợp đồng JSON không rõ nghĩa:

```json
{
  "createdAt": "2024-03-01T09:00:00"
}
```

Tên trường gợi ý sự kiện đã xảy ra, nhưng chuỗi không có offset/zone. Một client có thể hiểu đây là giờ UTC; client khác hiểu là giờ máy. Nên chọn hợp đồng như:

```json
{
  "createdAt": "2024-03-01T02:00:00Z"
}
```

Nếu bắt buộc giữ ý định giờ địa phương của lịch hẹn:

```json
{
  "appointmentLocal": "2024-03-01T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Khi đọc dữ liệu cũ chỉ còn `LocalDateTime`, không thể phục hồi đúng zone/offset bằng suy đoán nếu trước đó chưa có hợp đồng: phải xác định quy tắc di trú dựa trên nguồn tạo dữ liệu, cấu hình và hồ sơ lịch sử, đồng thời ghi nhận các trường hợp không thể xác định duy nhất.

## 12. Các lỗi thường gặp

1. **Coi `LocalDateTime` là UTC.** Bản thân đối tượng không có UTC. Cần `Instant` hoặc offset/zone được bảo đảm bởi hợp đồng.
2. **Lưu `LocalDateTime.now()` vào `createdAt`.** Kết quả phụ thuộc vùng mặc định của máy. Dùng nguồn `Clock` và một thời điểm `Instant`.
3. **Giữ `toLocalDateTime()` sau khi parse `OffsetDateTime` rồi bỏ offset.** Cách đó mất thông tin thời điểm tuyệt đối. Chỉ tách local date/time khi nghiệp vụ thực sự yêu cầu.
4. **Gọi `atZone` mà không hiểu gap/overlap.** API có quy tắc tự điều chỉnh/chọn offset; nghiệp vụ có thể cần từ chối, chọn rõ offset hoặc giải thích cho người dùng.
5. **Coi một offset cố định bằng một múi giờ thành phố.** Offset có thể thay đổi theo DST và lịch sử; dùng `ZoneId` cho quy tắc vùng.
6. **Dùng `LocalDateTime` cho ngày sinh hoặc chỉ giờ mở cửa.** Thừa dữ liệu dễ dẫn đến suy diễn sai. Dùng `LocalDate` hoặc `LocalTime`.
7. **Giả định cộng một ngày lịch luôn cách đúng 24 giờ.** Khi qua DST, chênh lệch giữa các `Instant` có thể là 23 hoặc 25 giờ.
8. **Nối chữ `Z` vào chuỗi local date-time khi phát API.** Làm sai ý nghĩa dữ liệu. Chỉ gắn UTC khi đã xác định thời điểm và chuyển đúng sang UTC.
9. **Dựa vào zone/locale mặc định để parse hoặc format.** Truyền ngữ cảnh rõ ràng nếu đầu vào/đầu ra phụ thuộc vùng và ngôn ngữ.
10. **Cho rằng hai LocalDateTime bằng nhau là cùng sự kiện.** `equals` chỉ so sánh các trường ngày/giờ, không biết múi giờ hay thời điểm thực.

## 13. Các ca kiểm thử giúp bắt lỗi ngữ nghĩa

| Kịch bản | Cách kiểm tra | Mong đợi |
| --- | --- | --- |
| Một sự kiện hiển thị ở hai vùng | `LocalDateTime.ofInstant(event, UTC/Vietnam)` | Local khác nhau, `Instant` gốc giống nhau |
| Lịch hẹn tại Việt Nam | `2024-03-01T09:00` + `Asia/Ho_Chi_Minh` | `2024-03-01T02:00:00Z` |
| Gap DST ở New York | `2024-03-10T02:30` + `America/New_York` | 0 offset hợp lệ |
| Overlap DST ở New York | `2024-11-03T01:30` + `America/New_York` | 2 offset: `-04:00` và `-05:00` |
| Hai lần 01:30 trong overlap | Hai offset đã phân giải | `Instant` khác nhau một giờ |
| Test “bây giờ” | `Clock.fixed` + vùng chỉ định | Ngày/giờ dự kiến cố định qua mọi lần chạy |
| Cộng một ngày qua DST | Noon New York 09–10/03/2024 | `LocalDateTime` cách một ngày lịch, `Instant` cách 23 giờ |
| Payload sự kiện | Chuỗi `createdAt` có `Z` và parse bằng `Instant` | Xác định được duy nhất một thời điểm |

Trong JUnit 5, dùng `assertEquals` trên `Instant` cho nghiệp vụ xác định thời điểm; dùng `assertEquals` trên `LocalDateTime` cho nghiệp vụ xác định giờ lịch. Với gap/overlap, kiểm tra `getValidOffsets(...).size()` trước khi gọi xử lý chuyển đổi. Việc kiểm thử hai ngữ nghĩa riêng là cách phát hiện những lỗi “đúng giờ trên máy lập trình nhưng sai giờ khi triển khai”.

## 14. Quy tắc chọn nhanh

1. **Chỉ ngày?** Chọn `LocalDate`.
2. **Chỉ giờ trong ngày?** Chọn `LocalTime`.
3. **Ngày + giờ trên lịch, chưa chọn vùng hoặc chỉ cần biểu diễn ý định địa phương?** `LocalDateTime` là phù hợp.
4. **Một sự kiện có thời điểm thực xác định?** Chọn `Instant`; chuyển sang giờ địa phương để hiển thị.
5. **Ngày + giờ cùng offset được nguồn xác định?** Chọn `OffsetDateTime`.
6. **Ngày + giờ theo quy tắc một vùng, đặc biệt với DST/lịch hẹn?** Chọn `ZonedDateTime` hoặc lưu ý định local date-time cùng `ZoneId` và chính sách phân giải.
7. **Đo khoảng thời gian thực?** Chọn `Duration` giữa các `Instant`.

**Thông điệp cốt lõi:** `LocalDateTime` rất hữu ích khi “ngày và giờ trên đồng hồ” là dữ liệu gốc. Nó bắt đầu làm mất ý nghĩa khi một thời điểm thực hoặc quy tắc múi giờ bị thay bằng ngày/giờ không kèm ngữ cảnh. Hãy lưu đủ **thời điểm, vùng hoặc offset** theo đúng nhu cầu và không tự suy diễn thông tin mà `LocalDateTime` không có.
