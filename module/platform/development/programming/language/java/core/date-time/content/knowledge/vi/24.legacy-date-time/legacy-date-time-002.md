# Tính có thể thay đổi của Date và các phương thức lỗi thời

## 1. Một đối tượng ngày giờ có thể bị đổi từ nơi khác

`java.util.Date` biểu diễn một thời điểm với độ chính xác mili giây, nhưng khác với `Instant`, giá trị của nó **có thể bị thay đổi sau khi tạo**. `setTime(long)` làm chính đối tượng ấy biểu diễn thời điểm khác.

Nếu nhiều nơi giữ cùng tham chiếu, một lời gọi sửa ở nơi này có thể làm nơi khác nhìn thấy thời gian thay đổi ngoài dự kiến. Lỗi không đòi hỏi nhiều luồng: chỉ một chuỗi lời gọi trong một luồng cũng có thể làm lộ vấn đề chia sẻ trạng thái.

Ví dụ minh họa:

```java
Date first = Date.from(Instant.parse("2026-10-25T10:00:00Z"));
Date second = first;
second.setTime(0L);
```

`first` và `second` không phải hai bản sao ngày giờ. Sau lời gọi cuối, cả hai cùng quan sát đối tượng mang giá trị epoch. Đổi tên biến hoặc đánh dấu một biến là `final` không tạo bản sao dữ liệu.

Trong mã mới, kiểu bất biến thường giúp giảm trách nhiệm quản lý trạng thái. Tuy vậy, khi làm việc với thư viện cũ, cần hiểu cả tính có thể thay đổi của Date và những phần API đã lỗi thời để không sửa nhầm hành vi.

## 2. final chỉ giữ tham chiếu, không đóng băng đối tượng

Đoạn sau hợp lệ:

```java
final Date timestamp = Date.from(
        Instant.parse("2026-10-25T10:00:00Z"));
timestamp.setTime(0L);
```

`final` cấm gán `timestamp = new Date(...)` về sau; nó không cấm thay đổi đối tượng mà biến trỏ tới. Một trường `private final Date` trong lớp vì vậy chưa đủ làm lớp bất biến.

Cần phân biệt:

| Tình huống | Điều đang thay đổi |
|---|---|
| `b = a` với hai biến Date | Tham chiếu được sao chép; hai biến cùng trỏ một đối tượng |
| `b.setTime(...)` | Giá trị bên trong đối tượng dùng chung |
| `b = new Date(...)` | Biến b trỏ đối tượng khác; đối tượng cũ không tự đổi |
| `new Date(a.getTime())` | Tạo Date thuần mới với cùng giá trị mili giây |

Khi kiểm tra lỗi, hãy hỏi “ai đang sở hữu đối tượng này và ai có quyền sửa nó”, không chỉ nhìn giá trị tại nơi khởi tạo.

## 3. Đóng kín trạng thái bằng sao chép phòng vệ

Một lớp legacy có thể bị tác động từ hai hướng:

### Đầu vào bị giữ nguyên tham chiếu

Nếu constructor gán trực tiếp `this.timestamp = input`, nơi gọi còn giữ `input` và có thể gọi `setTime` sau khi đối tượng chủ đã được tạo.

Giải pháp cho Date thuần là nhận một bản sao:

```java
this.timestamp = new Date(input.getTime());
```

### Getter trả thẳng tham chiếu nội bộ

Nếu getter trả `this.timestamp`, nơi gọi có thể sửa nó dù lớp không công bố setter. Cần trả một bản sao độc lập khi hợp đồng API vẫn phải dùng Date:

```java
return new Date(timestamp.getTime());
```

Sao chép chỉ ở một phía chưa đóng kín cả hai đường sửa. Chương trình ở phần 7 minh họa đồng thời việc sửa dữ liệu đầu vào sau constructor và sửa dữ liệu trả ra sau getter.

Các lệnh trên áp dụng cho giá trị **java.util.Date thuần theo độ chính xác mili giây**. Nếu đầu vào là kiểu con như `java.sql.Timestamp`, việc tạo lại Date từ `getTime()` không bảo toàn mọi thông tin/đặc tính của kiểu con, chẳng hạn phần nano giây riêng. Phải xác định kiểu và hợp đồng tại ranh giới thay vì áp dụng một hàm sao chép cho mọi lớp con.

`clone()` cũng tồn tại, nhưng một bản sao không tự giải thích được hợp đồng về kiểu con hoặc quyền sở hữu. Trong ví dụ học về Date thuần, tạo lại từ giá trị mili giây giúp thấy rõ dữ liệu nào đang được giữ.

## 4. Ảnh hưởng lên tập hợp và nhiều luồng

Giá trị thời gian tham gia `equals`, `hashCode` và thứ tự so sánh của Date. Nếu sửa một đối tượng đang làm khóa trong `HashMap` hoặc là phần tử trong tập dựa trên băm/thứ tự, cấu trúc đã lập chỉ mục theo giá trị cũ có thể không còn phản ánh giá trị mới.

Không dựa vào một kết quả tình cờ của `contains` để kết luận sửa khóa là an toàn. Hợp đồng cần giữ giá trị khóa ổn định trong thời gian nó nằm trong cấu trúc, hoặc dùng một khóa bất biến như `Instant` phù hợp với ý nghĩa dữ liệu.

Với nhiều luồng, Date có trạng thái có thể thay đổi và không tự cung cấp một chính sách đồng bộ cho ứng dụng. Sao chép phòng vệ ngăn nơi gọi giữ tham chiếu nội bộ, nhưng không tự bảo đảm một đối tượng đầu vào dùng chung đang bị sửa đồng thời được đọc như một ảnh chụp nhất quán.

Cách xử lý phụ thuộc hợp đồng sở hữu: không chia sẻ đối tượng có thể sửa, đồng bộ toàn bộ thao tác liên quan, hoặc chuẩn hóa sang kiểu bất biến. Chỉ thêm `final` vào trường hay sao chép trước một lời gọi không thay thế được việc xác định ai có thể sửa nguồn.

## 5. Những API Date đã deprecated

Không nên đánh đồng “Date có thể thay đổi” với “mọi phương thức sửa Date đều deprecated”. Ví dụ, `setTime(long)` vẫn là phương thức được hỗ trợ; việc nó không deprecated không có nghĩa là đối tượng trở thành bất biến.

Các nhóm cũ cần nhận diện khi đọc mã:

| Nhóm API lỗi thời | Điểm dễ hiểu sai |
|---|---|
| Constructor `Date(int year, int month, int date, ...)` | Năm dùng độ lệch 1900; tháng đánh số từ 0 |
| Constructor `Date(String)` và `Date.parse(String)` | Nhận chuỗi theo cơ chế legacy, không phải hợp đồng parsing hiện đại rõ ràng |
| `getYear()` / `setYear(...)` | Dùng năm trừ 1900, không phải năm lịch trực tiếp |
| `getMonth()` / `setMonth(...)` | Tháng 0–11 |
| `getDate()` / `setDate(...)` | Ngày trong tháng, không phải giá trị Date đầy đủ |
| `getDay()` | Thứ trong tuần với quy ước cũ, không phải DayOfWeek ISO |
| `getHours/getMinutes/getSeconds` và các setter tương ứng | Các thành phần lịch cũ trong ngữ cảnh múi giờ |
| `toGMTString()`, `toLocaleString()`, `Date.UTC(...)` | API định dạng hoặc tạo thời gian cũ đã được thay thế |

Các thành phần còn có thể được chuẩn hóa thay vì từ chối mọi giá trị ngoài phạm vi theo cách người đọc mong đợi. Ví dụ một ngày vượt số ngày của tháng không nhất thiết gây lỗi kiểm tra như một bộ phân tích `STRICT`.

Deprecated nghĩa là API không được khuyến nghị cho cách sử dụng mới và có hướng thay thế; không tự nghĩa là lời gọi đã bị xóa hoặc luôn ném lỗi. Khi đọc mã cũ, cần hiểu hành vi hiện tại trước khi thay đổi, vì một phép thay thế kiểm tra chặt hơn có thể chủ động làm thay đổi các đầu vào từng được chấp nhận.

### Những API không thuộc nhóm deprecated trên

`Date()` lấy thời điểm hiện tại, `Date(long)` nhận epoch mili giây, `getTime()`, `setTime(long)`, `before`, `after`, `compareTo`, `Date.from(Instant)` và `toInstant()` của Date thuần vẫn có thể dùng khi giao tiếp với API legacy.

Lớp `java.util.Date` không bị deprecated toàn bộ. Hãy kiểm tra đúng chữ ký bị cảnh báo, không sửa hàng loạt mọi chỗ có từ `Date` chỉ dựa vào tên lớp.

## 6. Thay API theo ý nghĩa của thao tác

| Mục tiêu | Lựa chọn hiện đại thường phù hợp |
|---|---|
| Lưu một thời điểm | `Instant` |
| Lấy phần ngày theo một vùng | `instant.atZone(zone).toLocalDate()` |
| Tạo một ngày không chứa giờ | `LocalDate.of(year, month, day)` |
| Phân tích hoặc định dạng chuỗi | `DateTimeFormatter` với mẫu/locale/chính sách rõ ràng |
| Điều chỉnh ngày theo lịch | Các phép tính trên LocalDate hoặc TemporalAdjuster phù hợp |

Không chỉ đổi `setDate(getDate() + 1)` thành cộng 86.400.000 mili giây rồi coi là tương đương ngày lịch ở mọi múi giờ. Một lượng 24 giờ và một ngày lịch có thể khác khi vùng có thay đổi DST.

Cũng không đọc năm bằng `getYear()` rồi dùng nó trực tiếp làm năm trong `LocalDate`. Quy ước cũ cần được chuyển đúng; tốt hơn là chuyển Date thuần sang `Instant`, chọn múi giờ cần thiết rồi lấy các trường theo API rõ nghĩa.

Việc chọn `Instant` bất biến có tác động quan trọng: `plusSeconds(...)` trả về giá trị mới, không sửa đối tượng ban đầu. Nếu cần thay trường trong một lớp, bạn sẽ gán một giá trị mới theo hợp đồng lớp, thay vì vô tình sửa một đối tượng chia sẻ.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `MutableDateDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Nó dùng Date thuần và không dựa vào múi giờ mặc định để tạo stdout.

```java
import java.time.Instant;
import java.util.Date;
import java.util.Objects;

public class MutableDateDemo {
    static final class LegacySnapshot {
        private final Date timestamp;

        LegacySnapshot(Date timestamp) {
            Objects.requireNonNull(timestamp);
            this.timestamp = new Date(timestamp.getTime());
        }

        Date timestamp() {
            return new Date(timestamp.getTime());
        }
    }

    public static void main(String[] args) {
        Instant originalInstant = Instant.parse("2026-10-25T10:00:00Z");
        final Date original = Date.from(originalInstant);
        Date alias = original;
        Date copy = new Date(original.getTime());
        LegacySnapshot snapshot = new LegacySnapshot(original);

        System.out.println("before=" + original.toInstant());
        alias.setTime(originalInstant.plusSeconds(3600).toEpochMilli());
        System.out.println("originalAfter=" + original.toInstant());
        System.out.println("aliasAfter=" + alias.toInstant());
        System.out.println("copyAfter=" + copy.toInstant());
        System.out.println("snapshotAfterInputChange="
                + snapshot.timestamp().toInstant());

        Date returned = snapshot.timestamp();
        returned.setTime(0L);
        System.out.println("returnedAfterChange=" + returned.toInstant());
        System.out.println("snapshotAfterOutputChange="
                + snapshot.timestamp().toInstant());

        Instant immutable = copy.toInstant();
        Instant later = immutable.plusSeconds(3600);
        System.out.println("immutableOriginal=" + immutable);
        System.out.println("immutableLater=" + later);
        System.out.println("sameStoredValue="
                + copy.equals(snapshot.timestamp()));
    }
}
```

Biên dịch và chạy:

```shell
javac MutableDateDemo.java
java MutableDateDemo
```

Kết quả chuẩn:

```text
before=2026-10-25T10:00:00Z
originalAfter=2026-10-25T11:00:00Z
aliasAfter=2026-10-25T11:00:00Z
copyAfter=2026-10-25T10:00:00Z
snapshotAfterInputChange=2026-10-25T10:00:00Z
returnedAfterChange=1970-01-01T00:00:00Z
snapshotAfterOutputChange=2026-10-25T10:00:00Z
immutableOriginal=2026-10-25T10:00:00Z
immutableLater=2026-10-25T11:00:00Z
sameStoredValue=true
```

Giải thích:

- `original` được khai báo `final` nhưng vẫn đổi từ 10:00 sang 11:00 qua `alias`.
- `copy` có giá trị ban đầu giống original nhưng là đối tượng độc lập.
- `LegacySnapshot` không bị sửa theo đầu vào vì đã sao chép khi nhận vào.
- Dữ liệu Date lấy ra từ getter có thể bị sửa, nhưng không làm snapshot đổi vì getter trả bản sao.
- `Instant.plusSeconds` tạo giá trị `later`; giá trị `immutable` ban đầu giữ nguyên.

Chương trình cố ý không dùng các phương thức deprecated để chứng minh tính có thể thay đổi. Chỉ `setTime` được hỗ trợ đã đủ gây thay đổi, nên việc xóa các cảnh báo deprecated không tự giải quyết vấn đề chia sẻ trạng thái.

## 8. Đọc và sửa mã legacy có kiểm soát

Khi gặp Date trong một lớp, lần lượt xác định:

1. Đây là `java.util.Date` thuần hay một kiểu con có hợp đồng riêng?
2. Giá trị thật sự là thời điểm hay hệ thống đang dùng nó để giả lập ngày dân sự?
3. Có constructor/getter nào giữ hoặc trả trực tiếp tham chiếu có thể sửa không?
4. Có phương thức deprecated nào dùng năm/tháng theo quy ước cũ không?
5. Các phép biến đổi đang dựa vào múi giờ mặc định hoặc cơ chế chuẩn hóa nào?
6. Chuyển sang kiểu mới có giữ đúng độ chính xác và các đầu vào được phép không?

Compiler có thể hỗ trợ tìm lời gọi lỗi thời qua `-Xlint:deprecation` khi biên dịch tệp chứa các lời gọi đó. Cảnh báo là vị trí để xem xét, không phải lời giải tự động cho hợp đồng nghiệp vụ.

Không chỉ thêm `@SuppressWarnings("deprecation")` để coi như đã xử lý. Nếu phải giữ API cũ vì ràng buộc tương thích, ghi rõ ranh giới và chuyển đổi phù hợp; với đường xử lý mới, chọn kiểu theo ngữ nghĩa thực sự.

Khi kiểm tra sửa đổi, cần thử việc sửa đầu vào sau constructor, sửa giá trị lấy từ getter, kiểm tra múi giờ đã chọn và những điều kiện biên vốn được chuẩn hóa trong mã cũ. Một kết quả đúng ở một ngày thông thường chưa đủ chứng minh việc thay API bảo toàn toàn bộ hành vi.

## 9. Tự thực hành

1. Trong ví dụ, tạm bỏ phép sao chép ở constructor `LegacySnapshot`. Quan sát kết quả `snapshotAfterInputChange` đổi theo `original`, rồi khôi phục phép sao chép.
2. Tạm cho getter trả thẳng `timestamp`. Quan sát việc sửa `returned` làm snapshot đổi; xác định vì sao sao chép đầu vào không ngăn được đường sửa này.
3. Thay trường nội bộ bằng `Instant` trong một phiên bản lớp mới, chuyển Date thuần ở ranh giới nhận/trả. Giải thích vì sao nguồn bất biến giúp tránh sửa chia sẻ bên trong, nhưng vẫn phải xử lý đúng yêu cầu tương thích ở biên.
4. Cho một đoạn mã cũ dùng `getMonth() == 0`. Hãy mô tả ý nghĩa tháng Một trước khi thay bằng `Month.JANUARY`; đừng biến nó thành so sánh tháng 0 ở API mới.

Tham khảo: [java.util.Date — setTime và danh sách phương thức deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html) và [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) trong Java SE 21.
