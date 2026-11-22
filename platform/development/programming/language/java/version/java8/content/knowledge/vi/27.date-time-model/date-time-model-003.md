# Giá trị bất biến và khả năng dùng giữa nhiều luồng trong mô hình ngày giờ Java

`java.time` là mô hình ngày giờ chuẩn được giới thiệu từ **Java 8**. Một nguyên tắc cốt lõi của các lớp ngày giờ chính như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime` và `ZonedDateTime` là **bất biến (*immutable*)**: sau khi tạo, trạng thái của một đối tượng không bị thay đổi qua các phương thức tính toán. Thay vì sửa đối tượng gốc, các thao tác như `plusDays`, `minusHours`, `withYear` hay `withZoneSameInstant` trả về kết quả biểu diễn giá trị mới.

Nhờ đặc tính đó, các đối tượng ngày giờ chuẩn có thể được **nhiều luồng đọc và sử dụng chung** mà không cần khóa chỉ để bảo vệ trạng thái nội tại của chúng. Đây là sự khác biệt quan trọng giữa việc **dùng một giá trị ngày giờ** và việc **cập nhật một biến hoặc bộ sưu tập đang chứa giá trị ngày giờ**: giá trị bất biến không loại bỏ race condition ở tầng cấu trúc dữ liệu bao quanh.

Bài học tập trung vào ý nghĩa bất biến, ranh giới an toàn luồng, cách dùng `DateTimeFormatter` và `Clock`, xử lý múi giờ, kiểm thử đa luồng và lỗi thiết kế thực tế. Tất cả API chính được trình bày vẫn **phù hợp với Java hiện đại**; ví dụ hoàn chỉnh chỉ dùng API có từ Java 8 và có thể biên dịch/chạy với **JDK 17+**.

## 1. Bất biến là gì và vì sao nó giúp đồng thời?

Một đối tượng **mutable** có trạng thái có thể thay đổi sau khi tạo. Nếu hai luồng đọc/ghi trạng thái đó không đúng cơ chế đồng bộ, kết quả có thể không nhất quán, mất cập nhật hoặc có race condition.

Một đối tượng **immutable** thì khác:

1. Nó được tạo với một giá trị xác định.
2. Các phương thức công khai không đổi trạng thái nội tại của đối tượng đã tạo.
3. Khi cần giá trị khác, ta nhận **một giá trị kết quả** qua lời gọi mới.
4. Hai luồng cùng dùng một reference đến đối tượng ấy không tranh chấp việc sửa **chính đối tượng ngày giờ**.

Ví dụ với ngày tháng:

~~~java
LocalDate original = LocalDate.of(2024, 2, 28);
LocalDate tomorrow = original.plusDays(1);

System.out.println(original); // 2024-02-28
System.out.println(tomorrow); // 2024-02-29
~~~

Đây là đoạn minh họa, cần `import java.time.LocalDate;` khi đưa vào lớp Java. `2024` là năm nhuận; lời gọi `plusDays(1)` tạo kết quả `2024-02-29` mà **không sửa** `original`.

**Lưu ý chính xác:** lời gọi được mô tả là “trả một giá trị bất biến” chứ không phải cam kết JVM luôn cấp phát một instance khác. Khi phép tính không thay đổi giá trị, implementation có thể trả chính đối tượng hiện tại. Không dựa vào `==` để phân biệt “đã sửa” hay “chưa sửa”; dùng `equals` để so sánh giá trị.

## 2. Những lớp ngày giờ thường dùng và hợp đồng của chúng

| Lớp/API | Giá trị biểu diễn | Bất biến và an toàn luồng? | Khi nên dùng |
| --- | --- | --- | --- |
| `LocalDate` | Ngày không có giờ/múi giờ | Có | Ngày sinh, ngày đến hạn theo lịch |
| `LocalTime` | Giờ trong một ngày, không có ngày/múi giờ | Có | Giờ mở cửa cố định theo lịch địa phương |
| `LocalDateTime` | Ngày + giờ, **không có offset/múi giờ** | Có | Lịch hẹn theo thời gian địa phương khi zone được lưu/biết riêng |
| `Instant` | Một thời điểm trên dòng thời gian | Có | Timestamp sự kiện, thời điểm tạo bản ghi |
| `OffsetDateTime` | Ngày giờ với offset cố định so với UTC | Có | Timestamp có offset gắn kèm |
| `ZonedDateTime` | Ngày giờ gắn với `ZoneId` và quy tắc múi giờ | Có | Lịch họp, múi giờ vùng, DST |
| `ZoneId` / `ZoneOffset` | Định danh vùng / độ lệch UTC | Có trong API chuẩn | Xác định cách diễn giải thời gian địa phương |
| `Duration` | Khoảng thời gian theo giây/nano | Có | Timeout, thời lượng đo trên time-line |
| `Period` | Khoảng thời gian theo năm/tháng/ngày | Có | Cộng kỳ hạn lịch, ngày-tháng-năm |
| `YearMonth` / `MonthDay` | Năm-tháng / tháng-ngày | Có | Kỳ báo cáo, ngày kỷ niệm |
| `DateTimeFormatter` | Quy tắc parse/format ngày giờ | Có | Một formatter được dùng lại ở nhiều luồng |

Các lớp ngày giờ chính của `java.time` được thiết kế immutable và thread-safe. Nhưng **không được suy rộng** đặc tính đó cho **mọi implementation do người dùng tự viết** của các interface mở rộng như `Temporal`, `TemporalAdjuster`, `TemporalQuery`, cho mọi `Clock` tự triển khai sai hợp đồng, hoặc cho mọi cấu trúc dữ liệu tùy biến chứa chúng.

Đặc biệt, `LocalDateTime` **không chứa múi giờ**. Việc nó immutable không làm biến mất câu hỏi “09:00 là 09:00 ở đâu?”. Khi cần một thời điểm tuyệt đối, dùng `Instant` hoặc kết hợp local date-time với `ZoneId`/`ZoneOffset` theo nghiệp vụ.

## 3. Các phương thức `plus`, `minus`, `with` không sửa đối tượng cũ

### 3.1. `plus` và `minus`

~~~java
LocalDate start = LocalDate.of(2024, 2, 28);

LocalDate nextDay = start.plusDays(1);
LocalDate previousMonth = start.minusMonths(1);

// start = 2024-02-28
// nextDay = 2024-02-29
// previousMonth = 2024-01-28
~~~

`start` vẫn giữ nguyên. Các phương thức có tên `plus...` hoặc `minus...` trả một giá trị tương ứng mới (về ngữ nghĩa), không thao tác “cộng trực tiếp” lên object gốc.

Với `LocalDateTime`:

~~~java
LocalDateTime atNight =
    LocalDateTime.of(2024, 2, 28, 23, 30);

LocalDateTime afterTwoHours = atNight.plusHours(2);

// atNight = 2024-02-28T23:30
// afterTwoHours = 2024-02-29T01:30
~~~

Phép này trên `LocalDateTime` chỉ làm toán **theo ngày-giờ địa phương**, chưa xét quy tắc chuyển giờ mùa hè vì đối tượng không có zone.

### 3.2. `with` thay một trường trong giá trị trả về

~~~java
LocalDate date = LocalDate.of(2024, 2, 28);
LocalDate firstOfMonth = date.withDayOfMonth(1);

// date = 2024-02-28
// firstOfMonth = 2024-02-01
~~~

Các thao tác `withYear`, `withMonth`, `withDayOfMonth` và `with(TemporalAdjuster)` tạo ngày-giờ được điều chỉnh **mà không đổi instance gốc**.

### 3.3. Sai lầm thường gặp: quên gán kết quả

~~~java
LocalDate dueDate = LocalDate.of(2024, 2, 28);

dueDate.plusDays(7); // Kết quả không được sử dụng.

// dueDate VẪN là 2024-02-28.
~~~

Cần gán lại biến:

~~~java
dueDate = dueDate.plusDays(7);
// dueDate là 2024-03-06.
~~~

Lúc này **biến tham chiếu** `dueDate` thay đổi để trỏ đến giá trị mới; đối tượng `LocalDate` ban đầu **không bị sửa**. Đây là ví dụ rõ nhất để phân biệt **đối tượng immutable** với **biến có thể gán lại**.

## 4. Bất biến không đồng nghĩa mọi thứ bao quanh đều thread-safe

### 4.1. Biến tham chiếu vẫn có thể bị thay từ nhiều luồng

~~~java
// Phản ví dụ — không dùng làm bộ đếm ngày chung.
private LocalDate current = LocalDate.of(2024, 1, 1);

void advanceOneDay() {
    current = current.plusDays(1);
}
~~~

Đoạn này chỉ minh họa một phần lớp. Mặc dù `LocalDate` immutable, chuỗi **đọc `current` → tính ngày mới → gán `current`** không phải thao tác nguyên tử trên biến chia sẻ. Hai thread có thể cùng đọc một ngày cũ, cùng tạo ngày tiếp theo rồi ghi đè lẫn nhau; một lần tăng bị mất.

Ngay cả thêm `volatile` cho biến chỉ giúp các thao tác đọc/ghi reference có quy tắc hiển thị thích hợp, **không làm phép đọc–tính–ghi trở thành nguyên tử**.

Khi thực sự cần cập nhật đồng thời một giá trị ngày giờ đơn lẻ, cân nhắc `AtomicReference<LocalDate>`:

~~~java
AtomicReference<LocalDate> current =
    new AtomicReference<>(LocalDate.of(2024, 1, 1));

current.updateAndGet(day -> day.plusDays(1));
~~~

Đây là đoạn minh họa cần `import java.util.concurrent.atomic.AtomicReference;`. `updateAndGet` thực hiện vòng lặp cập nhật nguyên tử theo hợp đồng, có thể gọi function **nhiều lần khi tranh chấp**; function phải **không có side effect**. `day -> day.plusDays(1)` là phép biến đổi thuần trên giá trị immutable nên phù hợp.

### 4.2. Một `ArrayList` chứa `LocalDate` vẫn là mutable

~~~java
List<LocalDate> dates = new ArrayList<>();

// Phản ví dụ: nhiều thread gọi add cùng lúc:
dates.add(LocalDate.of(2024, 1, 1));
~~~

Các phần tử `LocalDate` an toàn khi được chia sẻ, nhưng `ArrayList.add` trên **cùng danh sách** không tự trở nên thread-safe. Nếu cần thu thập dữ liệu đồng thời, hãy dùng collector/queue hoặc đồng bộ phù hợp thay vì suy luận từ kiểu của phần tử.

Trong Parallel Stream, cách diễn đạt rõ ràng hơn là:

~~~java
List<LocalDate> dates = IntStream.range(0, 100)
    .parallel()
    .mapToObj(i -> LocalDate.of(2024, 1, 1).plusDays(i))
    .collect(Collectors.toList());
~~~

Đây là ví dụ minh họa; cần imports `List`, `LocalDate`, `IntStream`, `Collectors`. `collect` được framework thực thi theo hợp đồng reducer; **không phải** do một `ArrayList` chia sẻ tùy tiện có thể chịu nhiều `add` đồng thời. Với nguồn `IntStream.range` ordered, kết quả `Collectors.toList` giữ encounter order, nhưng loại/mutability cụ thể của List trả về không được API hứa.

### 4.3. Trạng thái mutable nằm bên trong object nghiệp vụ

~~~java
final class Schedule {
    final LocalDate eventDay;
    final List<String> attendees;

    Schedule(LocalDate eventDay, List<String> attendees) {
        this.eventDay = eventDay;
        this.attendees = attendees;
    }
}
~~~

Đoạn trên chưa tạo một `Schedule` immutable vì `attendees` có thể bị chỉnh sửa từ bên ngoài hay qua reference giữ trong object, dù `eventDay` là immutable. Muốn một giá trị Schedule thực sự ít rủi ro hơn, phải thực hiện defensive copy/không công bố tham chiếu mutable, hoặc sử dụng một lớp collection bất biến phù hợp và có hợp đồng sở hữu rõ ràng.

Trong Java 8 có thể dùng `Collections.unmodifiableList(new ArrayList<>(attendees))` để ngăn sửa qua view công bố và tách khỏi list nguồn, nhưng vẫn lưu ý nếu **chính phần tử trong list mutable** thì chỉ sao chép list là *shallow copy*. Tính immutable của `java.time` chỉ giải quyết phần dữ liệu ngày giờ.

## 5. `DateTimeFormatter`: formatter dùng chung giữa nhiều luồng

`DateTimeFormatter` trong `java.time.format` **immutable và thread-safe**. Có thể tạo một formatter một lần rồi dùng cho nhiều request/worker, kể cả khi nhiều luồng cùng parse/format:

~~~java
private static final DateTimeFormatter FORMATTER =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");
~~~

Đây là thành phần của một lớp Java; cần import `java.time.format.DateTimeFormatter`. Với chuỗi năm-tháng-ngày, dùng ký hiệu `uuuu` (proleptic year) thường thuận tiện hơn `yyyy` khi chọn parsing STRICT; `yyyy` là year-of-era và có thể gây bất ngờ nếu không kèm era hoặc quy tắc resolver phù hợp.

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

String text = FORMATTER.format(date);
// "2024-02-29"

LocalDate parsed = LocalDate.parse(text, FORMATTER);
// LocalDate có cùng giá trị 2024-02-29
~~~

Formatter chỉ đọc cấu hình immutable của nó và ngày cần format/parse, không lưu một bộ đếm/trạng thái parse mutable dùng chung giữa các lời gọi.

### 5.1. Các phương thức `with...` cũng trả formatter mới

~~~java
DateTimeFormatter base =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");

DateTimeFormatter strict =
    base.withResolverStyle(ResolverStyle.STRICT);
~~~

`base` không bị thay đổi. `strict` biểu diễn formatter khác về quy tắc parse, nên nếu muốn dùng cấu hình mới phải **giữ giá trị trả về**.

Tương tự, `withLocale`, `withZone`, `withChronology` và `withDecimalStyle` không chỉnh sửa formatter ban đầu. Điều này giúp ứng dụng dùng một cấu hình gốc và tạo các biến thể cần thiết mà không làm thay đổi kết quả format của các luồng khác đang giữ reference cũ.

### 5.2. `DateTimeFormatterBuilder` không có cùng hợp đồng

**`DateTimeFormatterBuilder` là mutable builder**, được thiết kế để cấu hình trên một luồng trước khi sinh ra formatter:

~~~java
DateTimeFormatter formatter =
    new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .toFormatter();
~~~

Đây là đoạn minh họa; cần import `DateTimeFormatterBuilder` và `DateTimeFormatter`. Sau khi `toFormatter()` trả `DateTimeFormatter` immutable, có thể chia sẻ formatter đó. Không chia sẻ **cùng builder đang bị chỉnh sửa đồng thời** rồi suy rằng “thuộc package java.time nên mọi object đều immutable”.

**Phân biệt rõ:**

| Đối tượng | Dùng chung đồng thời để parse/format? | Lưu ý |
| --- | --- | --- |
| `DateTimeFormatter` | Có | Immutable/thread-safe, có thể `static final` |
| `DateTimeFormatterBuilder` | Không nên dùng chung khi đang cấu hình | Mutable builder dùng trên một luồng |
| `LocalDate`, `Instant`, `ZonedDateTime` | Có | Immutable, kết quả phép tính trả giá trị mới |
| `List<LocalDate>` mutable | Không tự an toàn cho cập nhật đồng thời | Cần collector/collection đồng bộ thích hợp |
| `AtomicReference<LocalDate>` | Có bảo đảm cập nhật reference | Update function có thể retry, nên thuần |

### 5.3. Không dạy lại formatter mutable cũ như chiến lược mặc định

Các lớp định dạng ngày giờ mutable từ API cũ không có hợp đồng chia sẻ đồng thời như `DateTimeFormatter`. Với mã mới, nên dùng `DateTimeFormatter` của `java.time` và giữ nó để tái sử dụng; không phải tạo một formatter mới cho từng lời gọi, cũng không cần bọc mọi lời gọi `format` bằng một global lock chỉ để bảo vệ formatter immutable.

Khi làm việc với hệ thống đã có API cũ, chuyển đổi ở **ranh giới tích hợp**, không đưa kiểu mutable vào sâu trong phần mô hình ngày giờ nếu có lựa chọn hiện đại phù hợp.

## 6. Dùng `Clock` để tách thời điểm hiện tại khỏi hệ thống

Giá trị bất biến là một chuyện; **giá trị được lấy từ “bây giờ”** là chuyện khác. `LocalDate.now()` hay `Instant.now()` hỏi đồng hồ tại thời điểm gọi, nên hai luồng gọi ở các thời điểm khác nhau không nhất thiết nhận cùng kết quả. Điều đó **không phải race condition do đối tượng ngày giờ**, mà là vì nguồn thời gian thực đang tiến.

`Clock` (Java 8+) là abstraction để cung cấp nguồn thời gian và múi giờ. Thay vì rải `now()` không tham số khắp logic nghiệp vụ, có thể tiêm `Clock`:

~~~java
Clock clock = Clock.systemUTC();

Instant recordedAt = Instant.now(clock);
~~~

Đây là đoạn minh họa; cần import `Clock` và `Instant`. `Clock.systemUTC()` tạo clock chuẩn thread-safe, nhưng `Instant.now(clock)` trả **thời gian thực thay đổi**, không phải giá trị bất biến duy nhất cho cả vòng đời ứng dụng.

### 6.1. `Clock.fixed` để có kiểm thử lặp lại được

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2024-02-28T16:30:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate today = LocalDate.now(fixed);
// 2024-02-28

ZonedDateTime nowInZone = ZonedDateTime.now(fixed);
// 2024-02-28T23:30+07:00[Asia/Ho_Chi_Minh]
~~~

`Clock.fixed` trả clock chuẩn immutable, thread-safe và luôn cung cấp cùng một `Instant`. Hữu ích cho unit test qua biên năm, biên ngày, hạn thanh toán, tính tuổi hoặc các quy tắc cut-off. Đồng hồ fix không phải đồng hồ thực tế — không dùng nó làm timestamp production trừ khi đó chính là hành vi được yêu cầu.

### 6.2. Custom `Clock` phải tuân thủ hợp đồng thread-safe

`Clock` là abstract class, không phải mọi object do lập trình viên tự tạo đều tự trở nên an toàn. API yêu cầu các implementation phải thread-safe; nếu tự viết Clock dựa trên một bộ đếm mutable hay nguồn bên ngoài, người viết phải tự đảm bảo đồng bộ, hiển thị dữ liệu và chính sách lỗi phù hợp.

Một `Clock` thread-safe cũng không bảo đảm **hai lời gọi now liên tiếp cho cùng kết quả**; muốn một thời điểm nhất quán xuyên suốt một nghiệp vụ, **chụp một giá trị `Instant` duy nhất** ở đầu tác vụ rồi truyền cho các hàm cần dùng:

~~~java
Instant requestTime = clock.instant();
// Truyền requestTime vào các bước thay vì gọi clock.instant() rải rác.
~~~

Đoạn này giả sử biến `clock` đã được cung cấp. Mỗi `Instant` là immutable và có thể chia sẻ đọc an toàn giữa các bước xử lý.

## 7. Múi giờ không làm mất tính bất biến, nhưng cần đúng ngữ nghĩa

### 7.1. `LocalDateTime` không phải thời điểm tuyệt đối

~~~java
LocalDateTime meeting =
    LocalDateTime.of(2024, 2, 28, 23, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = meeting.atZone(zone);
Instant instant = zoned.toInstant();
// instant = 2024-02-28T16:30:00Z
~~~

Cùng một `LocalDateTime` nếu gắn với **zone khác** có thể biểu diễn **Instant khác**. Tính immutable ngăn object bị thay trong lúc đọc, chứ **không tự xác định zone còn thiếu**. Với dữ liệu trao đổi giữa dịch vụ, thường cần lưu `Instant` hoặc một dạng có đủ offset/zone theo hợp đồng.

### 7.2. Thay zone giữ nguyên instant hay giữ local time?

Hai phương thức của `ZonedDateTime` có ý nghĩa khác nhau:

~~~java
ZonedDateTime hcm =
    ZonedDateTime.of(
        2024, 2, 28, 23, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh")
    );

ZonedDateTime utcSameInstant =
    hcm.withZoneSameInstant(ZoneOffset.UTC);

ZonedDateTime utcSameLocal =
    hcm.withZoneSameLocal(ZoneOffset.UTC);
~~~

- `withZoneSameInstant`: giữ đúng **thời điểm tuyệt đối**, thay cách hiển thị local date-time.
- `withZoneSameLocal`: cố giữ **giờ-địa-phương**, dẫn tới `Instant` khác nếu zone/offset đổi.
- Cả hai trả về giá trị bất biến mới (về ngữ nghĩa); `hcm` không bị sửa.

Với sự kiện thời gian thực, chuyển múi giờ hiển thị thường cần **same instant**, không phải same local. Khi tạo cuộc hẹn tại một giờ địa phương cố định, ngữ nghĩa có thể khác; phải xác định kiểu biểu diễn theo nghiệp vụ.

### 7.3. Daylight saving time (DST) và quy tắc vùng

`ZoneId` như `Europe/Paris` gắn với quy tắc DST; khi chuyển giờ có thể có **gap** (giờ địa phương không tồn tại) hoặc **overlap** (một giờ xảy ra hai lần). `ZonedDateTime` là immutable, nhưng phép `plusDays(1)` theo lịch địa phương và `plusHours(24)` theo dòng thời gian có thể **không cùng kết quả** qua DST.

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime start =
    ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);

ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);
~~~

Đây là mã minh họa; không nên suy rằng “một ngày lịch” luôn bằng “24 giờ thực” ở mọi vùng. Khi có yêu cầu lịch hẹn theo địa phương, dùng toán ngày tháng; khi có yêu cầu elapsed time chính xác, dùng `Instant` và `Duration`/đơn vị thời gian phù hợp.

**Lưu ý cập nhật dữ liệu múi giờ:** đối tượng `ZoneId` bất biến không có nghĩa các quy tắc múi giờ của mọi quốc gia sẽ vĩnh viễn không thay đổi. Cơ sở dữ liệu zone rules/tzdb của JDK có thể được cập nhật giữa các phiên bản hoặc lần triển khai. Không lưu cứng offset `+01:00` thay cho một vùng như `Europe/Paris` nếu nghiệp vụ phụ thuộc quy tắc vùng trong tương lai.

## 8. `Duration` và `Period` cũng là các giá trị bất biến

`Duration` biểu diễn thời lượng theo giây/nanosecond, thường hữu ích cho thời gian trôi qua, timeout và time-line arithmetic:

~~~java
Duration timeout = Duration.ofMinutes(30);
Duration longer = timeout.plusMinutes(15);

// timeout = PT30M
// longer = PT45M
~~~

`Period` biểu diễn lượng theo **năm, tháng, ngày**, phù hợp với ngày lịch:

~~~java
Period term = Period.ofMonths(1);
Period nextTerm = term.plusDays(5);

// term = P1M
// nextTerm = P1M5D
~~~

Cả hai immutable; các lời gọi thay đổi **giá trị trả về** chứ không mutate instance. Đừng coi `Period.ofMonths(1)` luôn tương đương một số giây cố định, bởi độ dài tháng phụ thuộc lịch; tương tự, một ngày lịch trong `ZonedDateTime` có thể không bằng 24 giờ thực qua DST.

Trong hệ thống đa luồng, có thể dùng một hằng `static final Duration TIMEOUT = Duration.ofSeconds(30);` mà không cần khóa để bảo vệ chính `Duration`. Nhưng một biến `remainingTime` được nhiều luồng thay tham chiếu phải được đồng bộ nếu chương trình phụ thuộc trạng thái nhất quán.

## 9. Ví dụ Java hoàn chỉnh: bất biến, formatter chung, Clock cố định và đa luồng

Lưu toàn bộ mã sau thành **`ImmutableDateTimeThreadsDemo.java`**. Mã chỉ dùng API có từ Java 8, có thể biên dịch và chạy với JDK 17+ mà không cần thư viện ngoài.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableDateTimeThreadsDemo {
    private static final LocalDate BASE =
            LocalDate.of(2024, 2, 28);

    private static final DateTimeFormatter SHARED_FORMATTER =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final int WORKERS = 4;
    private static final int PER_WORKER = 500;

    public static void main(String[] args) throws Exception {
        LocalDate nextDay = BASE.plusDays(1);
        LocalDate firstOfMonth = BASE.withDayOfMonth(1);

        System.out.println("original=" + BASE);
        System.out.println("nextDay=" + nextDay);
        System.out.println("stillOriginal=" + BASE);
        System.out.println("firstOfMonth=" + firstOfMonth);

        LocalDate sameValue = LocalDate.of(2024, 2, 28);
        System.out.println("equalByValue="
                + BASE.equals(sameValue));

        LocalDateTime local =
                LocalDateTime.of(2024, 2, 28, 23, 30);
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        Instant instant = local.atZone(zone).toInstant();
        Clock fixed = Clock.fixed(instant, zone);
        ZonedDateTime zoned = ZonedDateTime.now(fixed);

        System.out.println("instant=" + instant);
        System.out.println("clockToday=" + LocalDate.now(fixed));
        System.out.println("zoned=" + zoned);
        System.out.println("sameInstantUTC="
                + zoned.withZoneSameInstant(
                    ZoneOffset.UTC).toInstant().equals(instant));

        DateTimeFormatter dateTimeView =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm", Locale.ROOT)
                        .withZone(zone);
        System.out.println("formatted="
                + dateTimeView.format(instant));

        Duration halfHour = Duration.ofMinutes(30);
        System.out.println("duration="
                + halfHour.plusMinutes(15));
        Period month = Period.ofMonths(1);
        System.out.println("period=" + month.plusDays(5));

        AtomicReference<LocalDate> sharedRef =
                new AtomicReference<>(BASE);
        sharedRef.updateAndGet(d -> d.plusDays(1));
        sharedRef.updateAndGet(d -> d.plusDays(1));
        System.out.println("atomicDate=" + sharedRef.get());
        System.out.println("baseStill=" + BASE);

        ExecutorService pool =
                Executors.newFixedThreadPool(WORKERS);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < WORKERS; worker++) {
                futures.add(pool.submit(() -> {
                    int verified = 0;
                    for (int i = 0; i < PER_WORKER; i++) {
                        LocalDate d = BASE.plusDays(i % 20);
                        String text = SHARED_FORMATTER.format(d);
                        LocalDate parsed =
                                LocalDate.parse(text, SHARED_FORMATTER);

                        if (!d.equals(parsed)) {
                            throw new AssertionError(
                                "Date round trip failed");
                        }
                        verified++;
                    }
                    return verified;
                }));
            }

            int totalVerified = 0;
            for (Future<Integer> future : futures) {
                totalVerified += future.get();
            }
            System.out.println("parallelRoundTrips="
                    + totalVerified);
        } finally {
            pool.shutdown();
        }

        System.out.println("sharedBaseAfter=" + BASE);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ImmutableDateTimeThreadsDemo.java
java ImmutableDateTimeThreadsDemo
~~~

**Đầu ra kỳ vọng (ổn định, không dựa vào thứ tự chạy worker):**

~~~text
original=2024-02-28
nextDay=2024-02-29
stillOriginal=2024-02-28
firstOfMonth=2024-02-01
equalByValue=true
instant=2024-02-28T16:30:00Z
clockToday=2024-02-28
zoned=2024-02-28T23:30+07:00[Asia/Ho_Chi_Minh]
sameInstantUTC=true
formatted=2024-02-28 23:30
duration=PT45M
period=P1M5D
atomicDate=2024-03-01
baseStill=2024-02-28
parallelRoundTrips=2000
sharedBaseAfter=2024-02-28
~~~

### Vì sao ví dụ này đúng về đồng thời?

1. `BASE` là một `LocalDate` immutable. Các worker cùng đọc `BASE` và gọi `plusDays` để tạo ngày cần xử lý; không thread nào sửa BASE.
2. `SHARED_FORMATTER` là `DateTimeFormatter` immutable và được cấu hình một lần. Các worker cùng gọi `format` và `parse` trên formatter đó mà không cần `synchronized`.
3. Mỗi worker có biến cục bộ `d`, `text`, `parsed` và `verified` của riêng mình. Không có `ArrayList` kết quả chung bị nhiều worker `add` trực tiếp.
4. `Future.get()` chỉ được gọi sau khi các task đã hoàn tất hoặc chờ tới khi hoàn tất; mọi lỗi trong task được chuyển về caller thay vì bị bỏ qua.
5. `WORKERS=4`, `PER_WORKER=500` nên có **2.000 lượt kiểm tra**. Thứ tự worker hoàn thành không ảnh hưởng tổng.
6. `AtomicReference<LocalDate>` thể hiện cách cập nhật **reference** an toàn. Hàm `d -> d.plusDays(1)` không có side effect nên phù hợp dù callback có thể bị thử lại khi tranh chấp. Hai lần tăng từ `2024-02-28` đưa kết quả tới `2024-03-01` (2024 có ngày 29/2), trong khi BASE không đổi.
7. `Clock.fixed` loại bỏ phụ thuộc thời gian thực, nên việc thử tính zone và hiển thị thời gian không bị ảnh hưởng bởi giờ máy chạy.
8. Mã chỉ in kết quả khi dữ liệu cần thiết đã sẵn sàng; không in log lẫn lộn từ nhiều worker nên stdout tái lập được.

### Ví dụ không chứng minh điều gì?

Chương trình chứng minh một trường hợp sử dụng API đúng hợp đồng và cho kết quả dễ kiểm tra. Nó **không** tự là benchmark `DateTimeFormatter` so với formatter khác; không kết luận parallel nhanh hơn chỉ từ việc chạy nhiều worker; không chứng minh phần còn lại của một ứng dụng sẽ thread-safe nếu bao quanh giá trị ngày giờ có đối tượng mutable.

## 10. Cách chia sẻ giá trị giữa các luồng đúng hơn

### 10.1. Hằng giá trị không đổi ở cấp lớp

~~~java
private static final ZoneId BUSINESS_ZONE =
    ZoneId.of("Asia/Ho_Chi_Minh");

private static final DateTimeFormatter DATE_FORMAT =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");
~~~

Đây là đoạn minh họa, cần imports `ZoneId` và `DateTimeFormatter`. Với API chuẩn, hai object immutable nên có thể tái sử dụng ở nhiều worker và không cần tạo bản sao cho mỗi request.

Dùng `static final` giúp **reference không bị gán lại**, nhưng bản thân từ khóa `final` **không làm một đối tượng mutable bất kỳ trở nên thread-safe**. Tính an toàn trong ví dụ đến từ **hợp đồng của lớp** cộng với cách publish field phù hợp, không phải chỉ từ từ khóa.

### 10.2. Truyền giá trị thay vì truyền “trạng thái hiện tại” mutable

~~~java
LocalDate calculateDueDate(
        LocalDate createdOn,
        Period paymentTerm) {

    return createdOn.plus(paymentTerm);
}
~~~

Đây là một phương thức minh họa trong lớp Java. Với `createdOn` và `paymentTerm` đều immutable, hàm dễ kiểm thử: cùng input → cùng output, trừ khi có điều kiện lỗi ngoài hợp đồng. Không có trạng thái ngày giờ shared mutable cần cập nhật trong phương thức.

Nếu một workflow cần một thời điểm tham chiếu chung, lấy `Instant snapshot = clock.instant()` ở đầu workflow rồi truyền `snapshot` cho các bước thay vì gọi `now()` lặp nhiều lần.

### 10.3. Bản đồ/cache/schedule state vẫn cần thiết kế concurrency

~~~java
ConcurrentMap<String, LocalDate> deadlines =
    new ConcurrentHashMap<>();

deadlines.compute(
    "invoice-7",
    (id, oldDate) -> oldDate == null
        ? LocalDate.of(2024, 2, 28)
        : oldDate.plusDays(1)
);
~~~

Đây là đoạn minh họa, cần imports `ConcurrentMap` và `ConcurrentHashMap`. `LocalDate` bảo đảm rằng một value đã published không bị sửa từ bên trong; `ConcurrentHashMap.compute` cung cấp thao tác update theo khóa với bảo đảm đồng thời của implementation. Không dùng hai lệnh `get` rồi `put` để cập nhật một deadline chung mà giả định không có lost update.

Một phép cập nhật nhiều key **không** trở thành transaction chỉ vì mỗi value là immutable hoặc vì map là concurrent. Những invariant liên khóa vẫn cần cách tổ chức riêng.

## 11. Những giới hạn cần hiểu để không lạm dụng bất biến

### 11.1. Immutable không có nghĩa cùng reference

~~~java
LocalDate a = LocalDate.of(2024, 2, 28);
LocalDate b = LocalDate.parse("2024-02-28");

boolean sameValue = a.equals(b);  // true
~~~

Không kiểm tra `a == b` để khẳng định “hai ngày giống nhau”. Nhiều kiểu thuộc `java.time` là **value-based classes**: ứng dụng nên đối xử với các instance có giá trị bằng nhau như có thể thay thế về mặt ngữ nghĩa; không dùng reference identity hoặc `synchronized(dateTimeObject)` làm khóa đồng bộ.

### 11.2. Immutable không có nghĩa input luôn hợp lệ

~~~java
// LocalDate.of(2023, 2, 29); // DateTimeException
~~~

Khi tạo giá trị ngày giờ sai lịch, Java có thể ném `DateTimeException`. Khi parse văn bản không đúng format hoặc resolver rules, `DateTimeParseException` có thể xuất hiện. Tính immutable không thay thế việc validate input, lựa chọn timezone hoặc kiểm tra dữ liệu nguồn.

### 11.3. Immutable không có nghĩa kết quả không phụ thuộc môi trường

`LocalDate.now()` phụ thuộc đồng hồ và zone mặc định; `ZonedDateTime.of(...)` có thể phụ thuộc dữ liệu vùng, nhất là vùng có DST. Một đối tượng đã tạo vẫn immutable, nhưng hai lần **tạo giá trị mới** trong hai môi trường/tzdb khác nhau có thể không ra cùng instant nếu quy tắc nguồn khác. Hãy cố định `Clock`, `ZoneId` và các điều kiện đầu vào khi cần test tái lập.

### 11.4. Immutable không giải quyết toàn bộ quy trình nghiệp vụ

Nếu một đơn đặt hàng có deadline `LocalDate` bất biến nhưng nhiều thread cùng thay một trường `Order.deadline`, vẫn có race condition ở **reference của trường**. Nếu một list chứa hàng triệu đối tượng ngày giờ bị nhiều thread chèn/xóa không đồng bộ, list vẫn không an toàn. Nếu một tác vụ vừa ghi database vừa cập nhật cache, không có phép màu atomicity chỉ từ `Instant`.

Phải phân biệt cấp độ: **giá trị** immutable → **reference/collection** được cập nhật nguyên tử khi cần → **workflow liên dịch vụ** có transaction/idempotency theo hợp đồng riêng.

### 11.5. Không áp đặt kết luận cho các class tự triển khai

Những interface như `TemporalAccessor`, `TemporalAdjuster` và `TemporalQuery` cho phép extension tùy chỉnh. Một lambda hoặc class tùy chỉnh chứa state mutable có thể không an toàn dù được truyền vào một API `java.time`. Khi dùng callback/adjuster tự viết, áp dụng nguyên tắc stateless hoặc đồng bộ phù hợp; không suy “có từ khóa Temporal” thì mọi logic đều thread-safe.

## 12. Các lỗi phổ biến và cách tránh

1. **Gọi `date.plusDays(1)` nhưng không dùng kết quả.** Đối tượng không tự thay đổi; phải lưu giá trị mới.
2. **Dùng `==` để so sánh ngày giờ.** Dùng `equals` cho so sánh giá trị, hoặc `isBefore`/`isAfter` cho quan hệ thời gian phù hợp.
3. **Cho rằng `final LocalDate` là mutable không được thay vì “final”.** Trên thực tế `LocalDate` tự immutable; `final` chỉ giới hạn việc gán lại biến, không giải thích toàn bộ tính thread-safe.
4. **Cập nhật `sharedDate = sharedDate.plusDays(1)` từ nhiều thread.** Có thể mất cập nhật; dùng `AtomicReference.updateAndGet`, lock hoặc thiết kế tránh shared mutable reference.
5. **Để nhiều thread thêm vào cùng một `ArrayList<LocalDate>`.** Các element immutable không bảo vệ list; dùng collector hoặc container phù hợp.
6. **Dùng chung `DateTimeFormatterBuilder` mutable như formatter.** Builder được dùng để cấu hình trên một luồng; chia sẻ `DateTimeFormatter` đã tạo mới đúng.
7. **Tạo formatter mỗi lần chỉ vì sợ concurrency.** `DateTimeFormatter` immutable/thread-safe; có thể dùng một instance chung khi cấu hình không đổi.
8. **Giả định `LocalDateTime` chứa múi giờ.** Nó không có zone; phải xác định `ZoneId` hoặc dùng `Instant`/`OffsetDateTime`/`ZonedDateTime` phù hợp.
9. **Đồng nhất một ngày với 24 giờ thực ở mọi nơi.** DST có thể khiến toán theo lịch và toán theo elapsed time khác nhau.
10. **Giả định hai lần gọi `now()` phải giống nhau.** Thời gian thực tiến lên; dùng một `Instant` snapshot hoặc `Clock.fixed` khi cần.
11. **Dùng callback có side effect trong `AtomicReference.updateAndGet`.** Callback có thể bị gọi lại khi tranh chấp; chỉ nên chứa phép biến đổi thuần.
12. **Tin rằng mọi object trong package hoặc interface Temporal đều immutable.** Phân biệt lớp chuẩn, builder mutable và extension do ứng dụng tự triển khai.
13. **Dùng `synchronized(date)` như một lock theo identity.** Tránh khóa trên value-based object; dùng một lock riêng nếu nghiệp vụ cần khóa.
14. **Nhầm `Clock.fixed` với clock sản xuất đang chạy.** Đây là công cụ tạo thời gian cố định có chủ đích, thường phục vụ test.
15. **Bỏ qua cập nhật dữ liệu timezone.** Ngày giờ vùng phải xử lý theo quy tắc vùng hiện hành; không hardcode một offset cho mọi thời điểm tương lai.

## 13. Checklist kiểm tra trước khi chia sẻ ngày giờ giữa nhiều luồng

- Giá trị là một lớp chuẩn immutable của `java.time` hay một object tùy chỉnh có state mutable?
- Phương thức `plus/with/minus` đã được **gán kết quả** đúng nơi chưa?
- Có cần bảo vệ **trường reference, Map hay List** chứa những giá trị đó khi nhiều thread cập nhật không?
- Một hàm update có side effect ngoài ứng dụng không? Nếu có thể retry, side effect có an toàn/idempotent không?
- Formatter dùng chung là `DateTimeFormatter` hay builder mutable chưa hoàn tất cấu hình?
- Có phân biệt **LocalDateTime không zone** với `Instant` là thời điểm tuyệt đối không?
- Khi chuyển múi giờ, nghiệp vụ yêu cầu giữ **same instant** hay **same local time**?
- Với `ZonedDateTime`, có xem xét DST gap/overlap và tzdb khi tính lịch tương lai không?
- Có cần một thời điểm tham chiếu nhất quán qua cả yêu cầu? Nếu có, lấy một `Instant` từ `Clock` rồi truyền đi.
- Unit test có dùng `Clock.fixed`, zone cố định và dữ liệu chuẩn để tái lập được không?
- Có tránh `==`, `synchronized(value-based-date)` và giả định về identity/caching không?
- Có test nhiều luồng trên state bao quanh (map/list/reference), chứ không chỉ test các value immutable không?

**Tóm tắt:** Giá trị ngày giờ chuẩn của `java.time` và `DateTimeFormatter` là **immutable, thread-safe**, vì chúng không phải là các bộ chứa trạng thái được chỉnh sửa tại chỗ. Có thể chia sẻ chúng giữa nhiều thread để đọc, tính toán và định dạng. Nhưng tính an toàn của **reference được gán lại, collection mutable, callback, clock tự triển khai và workflow** vẫn phải được thiết kế riêng. Chọn đúng kiểu biểu diễn (`Instant` so với `LocalDateTime`), xử lý timezone/DST, và dùng `Clock` để kiểm thử ổn định là những thói quen vẫn có giá trị trong Java hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 25 — java.time package: các lớp ngày giờ cốt lõi immutable, thread-safe](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html)
- [Oracle Java SE 25 — LocalDate: bất biến, plus/with và value semantics](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html)
- [Oracle Java SE 25 — LocalDateTime: không chứa timezone](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html)
- [Oracle Java SE 25 — ZonedDateTime: zone/DST, same instant và local time](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html)
- [Oracle Java SE 25 — DateTimeFormatter: immutable và thread-safe](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 25 — DateTimeFormatterBuilder: mutable builder cho một luồng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
- [Oracle Java SE 25 — Clock: injection, fixed clock, hợp đồng thread-safe](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html)
- [Oracle Java SE 25 — ZoneRules và DST gap/overlap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html)
