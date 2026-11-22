# Instant là một điểm trên dòng thời gian trong Java

Khi hỏi **“Sự kiện xảy ra vào đúng thời điểm nào?”**, ứng dụng cần một giá trị chỉ được cùng một thời điểm dù người xem ở Hà Nội, Tokyo hay New York. Trong Java Date-Time API (`java.time`), **`Instant` là một điểm trên trục thời gian** (*timeline*), thích hợp để biểu diễn một thời điểm thực đã xảy ra hoặc sẽ xảy ra: lúc tạo giao dịch, nhận yêu cầu, xuất bản bản ghi, ghi audit log hoặc bắt đầu một tác vụ.

`Instant` không lưu ngày giờ “trên đồng hồ nhà bạn” như một thuộc tính độc lập; cũng không kèm tên vùng múi giờ. Giá trị này có thể đổi thành ngày giờ địa phương khi biết `ZoneId` hoặc `ZoneOffset`, nhưng **thời điểm gốc không thay đổi**.

## 1. Hình dung trục thời gian và một điểm Instant

Tưởng tượng một đường thẳng có thứ tự từ quá khứ đến tương lai:

~~~text
Quá khứ                          Mốc epoch                         Tương lai
  ... -------- A ----------- B ------ | ------ C ----------- D -------- ...
                     1970-01-01T00:00:00Z
                    sớm hơn  <--- | ---> muộn hơn
~~~

Mỗi `Instant` xác định một **vị trí** trên đường đó. Hai đối tượng `Instant` cùng vị trí biểu diễn **cùng thời điểm**, bất kể được tạo bằng cách nào. Có thể hỏi:

- `a.isBefore(b)`: A có xảy ra trước B không?
- `a.isAfter(b)`: A có xảy ra sau B không?
- `a.equals(b)`: A và B có cùng giá trị thời điểm không?
- `Duration.between(a, b)`: khoảng thời gian đi từ A đến B bao lâu?

Phân biệt **điểm thời gian** với **độ dài thời gian**:

| Khái niệm | Kiểu Java | Ví dụ | Cách hiểu |
|---|---|---|---|
| Điểm trên trục thời gian | `Instant` | `2024-02-29T12:00:00Z` | Một sự kiện xảy ra tại thời điểm này |
| Độ dài giữa hai điểm | `Duration` | `PT15M` | Khoảng 15 phút |
| Ngày và giờ theo một vùng | `ZonedDateTime` | `2024-02-29T19:00+07:00[Asia/Ho_Chi_Minh]` | Cách vùng đó biểu diễn một instant |
| Ngày, giờ không kèm vùng | `LocalDateTime` | `2024-02-29T19:00` | Dữ liệu “giờ địa phương”, chưa đủ để biết một instant duy nhất |
| Ngày lịch, không kèm giờ | `LocalDate` | `2024-02-29` | Ngày theo lịch, chưa xác định điểm trên timeline |

Vì `LocalDateTime` thiếu múi giờ, hai hệ thống không nên coi cùng chuỗi `2024-02-29T19:00` ở hai vùng là cùng một thời điểm thực. Phải biết vùng/offset để chuyển về `Instant`.

## 2. Mốc epoch là tọa độ để định vị Instant

`Instant.EPOCH` tương ứng **1970-01-01T00:00:00Z**. Đây là điểm tham chiếu có tọa độ 0, không phải lúc thời gian bắt đầu.

- Trước epoch: tọa độ theo giây hoặc mili giây là **số âm**.
- Đúng epoch: tọa độ là **0**.
- Sau epoch: tọa độ là **số dương**.

~~~java
Instant epoch = Instant.EPOCH;
Instant before = Instant.parse("1969-12-31T23:59:59.500Z");
Instant after = Instant.parse("1970-01-01T00:00:00.250Z");
~~~

Bảng thể hiện cách các instant nằm trên trục:

| Thời điểm UTC | Epoch seconds | Nano trong giây | Epoch milliseconds |
|---|---:|---:|---:|
| `1969-12-31T23:59:59.500Z` | `-1` | `500_000_000` | `-500` |
| `1969-12-31T23:59:59.999Z` | `-1` | `999_000_000` | `-1` |
| `1970-01-01T00:00:00Z` | `0` | `0` | `0` |
| `1970-01-01T00:00:00.250Z` | `0` | `250_000_000` | `250` |
| `1970-01-01T00:00:01Z` | `1` | `0` | `1000` |

Bản thân `Instant` về mặt mô hình lưu **số giây từ epoch** (`long`) và **số nano giây trong giây** (`int`). Trường nano luôn từ `0` đến `999_999_999`; vì thế thời điểm `-0,5` giây được biểu diễn là `epochSecond=-1` và `nano=500_000_000`. Công thức tính độ lệch giây về mặt khái niệm là:

~~~text
thời điểm tương đối (giây) = epochSecond + nano / 1_000_000_000
-0,5 = -1 + 500_000_000 / 1_000_000_000
~~~

**Điểm dễ nhầm:** `getEpochSecond() == -1` không nhất thiết đồng nghĩa “đúng một giây trước epoch”; cần xét thêm `getNano()`. Với timestamp âm, phép chia nguyên thông thường theo quy tắc làm tròn về 0 của Java cũng có thể dẫn đến kết quả sai khi tự tách giây và nano. Ưu tiên `Instant.ofEpochMilli(...)` hoặc `ofEpochSecond(...)` để Java chuẩn hóa.

Chữ `Z` trong chuỗi ISO-8601 biểu thị offset UTC (`+00:00`). Chuỗi in ra từ `Instant.toString()` theo dạng ISO-8601 có `Z`; nó **không biến `Instant` thành một đối tượng có vùng múi giờ lưu bên trong**.

## 3. Tạo một điểm trên timeline

### Từ chuỗi ISO-8601

~~~java
Instant event = Instant.parse("2024-02-29T12:00:00Z");
~~~

`Instant.parse(...)` phù hợp với biểu diễn thời điểm có quy chiếu UTC rõ ràng. Một chuỗi chỉ có ngày và giờ địa phương, ví dụ `"2024-02-29T12:00:00"`, **chưa xác định một thời điểm duy nhất**; không nên tự hiểu nó theo múi giờ mặc định. Cần xác định offset hoặc vùng múi giờ theo hợp đồng dữ liệu trước.

### Từ epoch seconds, milliseconds và nano

~~~java
Instant epoch = Instant.ofEpochSecond(0);            // 1970-01-01T00:00:00Z
Instant oneSecond = Instant.ofEpochSecond(1);       // 1970-01-01T00:00:01Z
Instant halfBefore = Instant.ofEpochMilli(-500);     // 1969-12-31T23:59:59.500Z
Instant sameBefore = Instant.ofEpochSecond(-1, 500_000_000);
~~~

`ofEpochSecond(seconds, nanoAdjustment)` cho phép truyền một phần nano điều chỉnh và sẽ chuẩn hóa về khoảng hợp lệ. `ofEpochMilli(millis)` nhận mili giây, kể cả số âm.

**Cần xác nhận đơn vị** của mọi giá trị số đọc từ API, log hoặc cơ sở dữ liệu: `1709208000` là epoch **seconds** cho 29/02/2024 12:00 UTC; nếu hiểu là milliseconds sẽ trỏ đến thời điểm hoàn toàn khác.

### Lấy thời điểm hiện tại

~~~java
Instant capturedAt = Instant.now();
~~~

Đây là thời điểm theo đồng hồ hệ thống khi gọi phương thức. Nó **phụ thuộc môi trường chạy**, nên không thể viết sẵn một stdout cố định cho `now()`.

Nếu viết chương trình có kiểm thử, nên truyền `Clock` thay vì gọi `Instant.now()` trực tiếp trong mọi chỗ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

// Mã minh họa trong một phương thức:
Clock clock = Clock.fixed(
        Instant.parse("2024-02-29T12:00:00Z"), ZoneOffset.UTC);
Instant observed = Instant.now(clock);
// observed = 2024-02-29T12:00:00Z
~~~

`Clock.fixed` giúp test có kết quả xác định. Trong hệ thống thực có thể dùng `Clock.systemUTC()` hoặc clock được tiêm từ cấu hình; `ZoneOffset.UTC` trong `Clock` không có nghĩa mỗi `Instant` chứa vùng UTC.

## 4. Đọc và so sánh các điểm thời gian

Những phương thức thường dùng:

| API | Ý nghĩa |
|---|---|
| `instant.getEpochSecond()` | Số giây từ epoch, biểu diễn bằng `long` |
| `instant.getNano()` | Phần nano giây bên trong giây tương ứng |
| `instant.toEpochMilli()` | Số mili giây từ epoch; bỏ độ chính xác dưới mili giây |
| `instant.isBefore(other)` | Có nằm **trước** điểm khác trên timeline? |
| `instant.isAfter(other)` | Có nằm **sau** điểm khác trên timeline? |
| `instant.equals(other)` | Có cùng giá trị thời điểm? |
| `instant.compareTo(other)` | So sánh thứ tự tương đối |
| `instant.plusSeconds(n)` | Trả một instant mới, dịch về phía tương lai n giây |
| `instant.minusSeconds(n)` | Trả một instant mới, dịch về phía quá khứ n giây |

`isBefore` và `isAfter` là so sánh **nghiêm ngặt**: khi hai điểm bằng nhau, cả hai đều trả về `false`. Nếu cần so sánh bao gồm bằng nhau, dùng điều kiện như `!a.isAfter(b)` (“a trước hoặc cùng lúc b”).

`Instant` là kiểu **bất biến** (*immutable*), mọi phép cộng/trừ tạo ra kết quả mà không thay đổi giá trị gốc:

~~~java
Instant event = Instant.parse("2024-02-29T12:00:00Z");
Instant later = event.plusSeconds(90);
// event vẫn là 2024-02-29T12:00:00Z
// later là 2024-02-29T12:01:30Z
~~~

Một phép cộng hoặc chuyển đổi ngoài miền hỗ trợ có thể gây ngoại lệ; không nên giả định mọi phép toán trên thời điểm rất xa đều thực hiện thành công.

### Khoảng thời gian giữa hai điểm

~~~java
Instant start = Instant.parse("2024-02-29T12:00:00Z");
Instant finish = Instant.parse("2024-02-29T12:00:01.250Z");
Duration elapsed = Duration.between(start, finish);
// elapsed = PT1.25S
// elapsed.toMillis() = 1250
~~~

`Duration.between(start, finish)` trả **khoảng có hướng**: nếu `finish` sớm hơn `start`, duration âm. Dùng `Duration` cho khoảng giây/phút/giờ giữa các instant; `Period` dành cho lượng thời gian theo năm/tháng/ngày trên lịch, có ý nghĩa khác.

Với các khoảng đo hiệu năng trong một tiến trình, `System.nanoTime()` là nguồn đồng hồ đơn điệu phù hợp hơn đồng hồ tường. `Instant.now()` giúp ghi thời điểm theo đồng hồ thực; đồng hồ hệ thống có thể được hiệu chỉnh nên chênh lệch của hai lần gọi không luôn phản ánh chính xác thời lượng tác vụ.

## 5. Cùng Instant, nhiều giờ địa phương

Xét thời điểm cố định:

~~~text
2024-02-29T12:00:00Z  (UTC)
2024-02-29T19:00:00+07:00  (UTC+07:00)
~~~

Đây là **cùng một điểm trên timeline**. Phần giờ hiển thị khác nhau vì mỗi vùng cộng độ lệch UTC để diễn giải đồng hồ địa phương. Cả hai khi chuyển về `Instant` đều mang cùng giá trị.

~~~java
Instant event = Instant.parse("2024-02-29T12:00:00Z");

ZonedDateTime inHcm = event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
// Ngày giờ địa phương: 2024-02-29T19:00

ZonedDateTime inUtc = event.atZone(ZoneOffset.UTC);
// Ngày giờ địa phương: 2024-02-29T12:00

boolean same = inHcm.toInstant().equals(inUtc.toInstant()); // true
~~~

`ZoneId` đại diện cho vùng với các quy tắc thay đổi offset theo lịch sử; `ZoneOffset` biểu diễn một offset cố định. Không phải vùng địa lý nào cũng giữ cùng offset tại mọi thời điểm.

### Khi nào nên dùng kiểu nào?

- **`Instant`:** lưu thời điểm sự kiện chính xác hoặc dùng khóa thứ tự các sự kiện toàn cầu.
- **`ZonedDateTime`:** làm việc với thời điểm **trong ngữ cảnh múi giờ cụ thể**, nhất là khi người dùng quan tâm giờ địa phương và các thay đổi giờ mùa hè.
- **`OffsetDateTime`:** ngày giờ kèm offset xác định, thường gặp khi giao tiếp API.
- **`LocalDateTime`:** dữ liệu lịch/giờ địa phương như “họp lúc 09:00”, chưa đủ một instant nếu chưa biết zone.

Khi đã có `Instant`, việc gọi `atZone(...)` chỉ tạo **cách biểu diễn ở vùng được chọn**. Khi chỉ có `LocalDateTime`, việc gắn zone mới là bước **diễn giải** dữ liệu thành một thời điểm cụ thể, có thể cần xử lý giờ bị lặp hoặc không tồn tại tại thời điểm chuyển đổi DST.

## 6. Ví dụ hoàn chỉnh Java 17: nhiều biểu diễn, một timeline

Tạo tệp **`InstantTimelineDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class InstantTimelineDemo {
    public static void main(String[] args) {
        Instant before = Instant.ofEpochSecond(-1, 500_000_000);
        Instant epoch = Instant.EPOCH;
        Instant after = Instant.parse("1970-01-01T00:00:00.250Z");

        System.out.println("before = " + before);
        System.out.println("epoch = " + epoch);
        System.out.println("after = " + after);
        System.out.println("before seconds = " + before.getEpochSecond());
        System.out.println("before nanos = " + before.getNano());
        System.out.println("before millis = " + before.toEpochMilli());
        System.out.println("before < epoch = " + before.isBefore(epoch));
        System.out.println("after > epoch = " + after.isAfter(epoch));
        System.out.println("gap ms = "
                + Duration.between(before, after).toMillis());
        System.out.println("epoch plus 90 s = " + epoch.plusSeconds(90));

        Instant event = Instant.parse("2024-02-29T12:00:00Z");
        OffsetDateTime plusSeven =
                OffsetDateTime.parse("2024-02-29T19:00:00+07:00");
        System.out.println("same instant = "
                + event.equals(plusSeven.toInstant()));
        System.out.println("UTC local time = "
                + event.atZone(ZoneOffset.UTC).toLocalTime());
        System.out.println("HCM local time = "
                + event.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalTime());
        System.out.println("original event = " + event);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac InstantTimelineDemo.java
java InstantTimelineDemo
~~~

Đầu ra được kiểm chứng bằng `javac --release 17`:

~~~text
before = 1969-12-31T23:59:59.500Z
epoch = 1970-01-01T00:00:00Z
after = 1970-01-01T00:00:00.250Z
before seconds = -1
before nanos = 500000000
before millis = -500
before < epoch = true
after > epoch = true
gap ms = 750
epoch plus 90 s = 1970-01-01T00:01:30Z
same instant = true
UTC local time = 12:00
HCM local time = 19:00
original event = 2024-02-29T12:00:00Z
~~~

**Phân tích:**

1. `before` bằng nửa giây trước epoch. Nó được lưu bằng `epochSecond=-1` cộng `500_000_000` nano giây, tức `-500` epoch milliseconds.
2. `after` cách epoch `250` mili giây. Vì `before` sớm hơn epoch `500` ms, khoảng `Duration.between(before, after)` là `750` ms.
3. `plusSeconds(90)` dịch một điểm trên timeline về phía tương lai 90 giây, không sửa `epoch`.
4. `12:00 UTC` và `19:00 tại Asia/Ho_Chi_Minh` là hai cách hiển thị cho cùng instant năm 2024; giá trị `event` không thay đổi.

## 7. Các trường hợp thực tế và những sai lầm thường gặp

### Dữ liệu sự kiện trong API, log và cơ sở dữ liệu

Nếu API gửi thời điểm phát sinh giao dịch, có thể dùng một trong hai dạng đã ghi rõ:

~~~json
{
  "occurredAt": "2024-02-29T12:00:00Z",
  "occurredAtEpochMillis": 1709208000000
}
~~~

Cả hai giá trị trên cùng chỉ một thời điểm. Khi chọn trường số, **cần ghi đơn vị** trong hợp đồng: epoch **seconds**, **milliseconds** và **microseconds** là ba cách đếm khác nhau.

Khi nhận dữ liệu:
- Parse chuỗi có offset rõ ràng thành `Instant`.
- Nếu nhận epoch milliseconds dạng số, dùng `Instant.ofEpochMilli(value)`.
- Lưu `Instant` hoặc thời điểm UTC bằng kiểu dữ liệu phù hợp ở tầng persistence, xác nhận hành vi của driver/DB.
- Chỉ thêm vùng múi giờ khi cần hiển thị theo người dùng hoặc tính lịch địa phương.
- Giữ độ chính xác theo yêu cầu nghiệp vụ; `toEpochMilli()` **bỏ phần nhỏ hơn mili giây** và có thể không biểu diễn được một số giá trị `Instant` ngoài phạm vi của `long` milliseconds.

### Độ chính xác không đồng nghĩa độ đúng của đồng hồ

`Instant` có **khả năng biểu diễn tới nano giây**, nhưng không đảm bảo đồng hồ hệ điều hành thật sự cung cấp độ phân giải nano giây hoặc thời gian đã được đồng bộ chính xác. Hai sự kiện sát nhau có thể ghi cùng timestamp do độ phân giải đồng hồ; một đồng hồ hệ thống bị điều chỉnh có thể tạo timestamp giảm theo thứ tự gọi.

Không lấy `Instant.now()` làm bộ đếm số thứ tự tuyệt đối không trùng nhau cho mọi sự kiện. Nếu nghiệp vụ cần thứ tự toàn phần, hãy kết hợp một định danh hoặc sequence đáng tin cậy với timestamp.

### Bảng phân biệt lỗi

| Lỗi | Hậu quả | Cách đúng |
|---|---|---|
| Xem `Instant` là “giờ 12:00 ở máy mình” | Người ở zone khác dễ diễn giải sai | `Instant` là điểm toàn cục; hiển thị với `atZone(...)` |
| Coi `LocalDateTime` tự đủ để xác định một instant | Thiếu quy tắc múi giờ/offset, có thể mơ hồ | Cung cấp `ZoneId` hoặc `ZoneOffset` |
| Nhầm giây với mili giây | Số timestamp trỏ đến thời điểm sai | Đặt tên trường, ghi đơn vị, dùng factory tương ứng |
| Cho rằng thời gian trước 1970 là không hợp lệ | Loại sai các sự kiện lịch sử | Chấp nhận timestamp âm khi hợp đồng cho phép |
| Lấy `getEpochSecond()` nhưng bỏ qua `getNano()` | Mất phần dưới giây, nhất là ở giá trị âm | Xử lý cả hai thành phần hoặc dùng `toEpochMilli()` với độ chính xác phù hợp |
| Dùng `==` để so sánh hai `Instant` | So sánh tham chiếu, không phải giá trị | Dùng `equals(...)` hoặc `isBefore`/`isAfter` |
| Coi `plusSeconds(...)` thay đổi đối tượng cũ | Quên lưu kết quả dẫn đến không thay đổi nghiệp vụ | Nhận giá trị `Instant` mới |
| Dùng `Period` thay `Duration` để tính chênh lệch giây | `Period` mang ý nghĩa lịch theo năm/tháng/ngày | Dùng `Duration.between(...)` |
| Xem `Instant.now()` là đồng hồ đơn điệu để benchmark | Đồng hồ tường có thể hiệu chỉnh | Dùng `System.nanoTime()` cho đo thời lượng |
| Cho rằng định dạng `toString()` chính là zone người dùng | `toString()` biểu diễn theo UTC với `Z` | Chuyển `atZone(userZone)` để hiển thị |
| Giả định độ chính xác nano của kiểu dữ liệu = độ chính xác thiết bị | Có thể tạo ấn tượng sai về độ chính xác đo đạc | Tách độ phân giải biểu diễn khỏi chất lượng đồng hồ thực |

**Giới hạn kỹ thuật:** `Instant` có dải năm lớn nhưng **hữu hạn**; các phép toán có thể ném `DateTimeException` hoặc `ArithmeticException` khi vượt giới hạn. Mô hình `java.time` dùng `Java Time-Scale` để biểu diễn trục thời gian liên tục và xử lý quy ước giây nhuận; trong các bài toán ngày giờ thông thường, nên hiểu `Instant` là một điểm UTC có thể chuyển đổi và so sánh nhất quán, không tự giả định đây là dữ liệu đồng hồ nguyên tử độ chính xác tuyệt đối.

## 8. Tự kiểm tra

1. `Instant` đại diện điều gì? **Một điểm trên timeline**, độc lập với cách hiển thị giờ theo múi giờ.
2. Hai chuỗi `2024-02-29T12:00:00Z` và `2024-02-29T19:00:00+07:00` có cùng instant không? **Có**.
3. `Instant.ofEpochMilli(-500)` là thời điểm nào? **1969-12-31T23:59:59.500Z**, trước epoch 0,5 giây.
4. Vì sao `Instant.ofEpochMilli(-500).getEpochSecond()` là `-1`? Vì giá trị còn **500 triệu nano giây** nằm trong giây `-1`, tổng ra `-0,5` giây.
5. `Duration.between(a, b)` cho biết điều gì? **Khoảng thời gian có hướng** từ `a` đến `b`.
6. Nếu hai `Instant` bằng nhau, `a.isBefore(b)` và `a.isAfter(b)` là gì? **Cả hai đều false**.
7. Muốn trình bày một `Instant` theo múi giờ của người dùng, dùng phương thức nào? **`instant.atZone(zoneId)`**, sau đó định dạng giá trị địa phương.
8. Để kiểm thử code lấy “thời điểm hiện tại” ổn định, dùng gì? **`Clock.fixed(...)`** và `Instant.now(clock)`.
9. Dùng `Instant.now()` để đo hiệu năng 5 ms có đáng tin như đồng hồ đơn điệu không? **Không**; dùng `System.nanoTime()` cho đo thời lượng chạy.
10. `Instant` có lưu thời điểm theo dạng nano giây nhưng có đảm bảo thiết bị đồng hồ chính xác tới nano giây không? **Không**; khả năng biểu diễn và độ chính xác đồng hồ là hai việc khác nhau.

**Ghi nhớ:** `Instant` trả lời “khi nào trên dòng thời gian?”, `Duration` trả lời “cách nhau bao lâu?”, còn `ZonedDateTime` giúp trả lời “thời điểm đó hiển thị ngày giờ nào tại vùng này?”. Chọn đúng kiểu trước khi lưu, tính toán hoặc trình bày ngày giờ.

### Tài liệu tham khảo

- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html)
