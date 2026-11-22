# TemporalQuery và các truy vấn có sẵn trong TemporalQueries

## 1. Vì sao cần truy vấn ngoài các trường số?

Một đối tượng ngày giờ không chỉ có các số như năm, tháng, giờ. Ta còn có thể muốn biết nó dùng hệ lịch nào, có múi giờ hay không, có thể lấy ngày địa phương hay không hoặc hỗ trợ đơn vị nhỏ nhất nào.

`get(TemporalField)` và `getLong(TemporalField)` thích hợp để đọc một **trường dạng số**. `TemporalQuery<R>` mô tả một **cách truy vấn trả kết quả kiểu R**, chẳng hạn `LocalDate`, `ZoneId`, `Chronology` hoặc một kết quả nghiệp vụ tự định nghĩa.

Ví dụ hai câu hỏi có bản chất khác nhau:

```java
int day = date.get(ChronoField.DAY_OF_MONTH);
LocalDate localDate = temporal.query(TemporalQueries.localDate());
```

Đoạn trên minh họa cách gọi; `date` là `LocalDate`, còn `temporal` là `TemporalAccessor`. Dòng đầu lấy số ngày trong tháng. Dòng sau hỏi liệu đầu vào có cung cấp được một `LocalDate` hay không.

Theo [TemporalQuery](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalQuery.html), truy vấn tách cách lấy thông tin khỏi đối tượng được hỏi. Nhờ đó, cùng một cách truy vấn có thể áp dụng cho nhiều kiểu ngày giờ mà không cần viết một chuỗi `instanceof` cho từng kiểu.

Tuy nhiên, truy vấn không tạo ra thông tin còn thiếu. Một `LocalTime` không chứa ngày; một `LocalDateTime` không chứa múi giờ. Truyền một truy vấn vào không làm các đối tượng đó tự biết thêm dữ liệu.

## 2. TemporalQuery<R> hoạt động như thế nào?

`TemporalQuery<R>` là giao diện hàm có một phương thức chính:

```java
R queryFrom(TemporalAccessor temporal);
```

`R` là kiểu kết quả. Nó có thể là một lớp của Java, một bản ghi do ứng dụng định nghĩa hoặc kiểu bao như `Boolean`. Phương thức nhận đối tượng cần đọc và trả kết quả theo hợp đồng của truy vấn.

Cách gọi thông thường:

```java
TemporalQuery<LocalDate> query = TemporalQueries.localDate();
LocalDate result = temporal.query(query);
```

Có thể gọi trực tiếp `query.queryFrom(temporal)`. Với truy vấn được hiện thực đúng hợp đồng, hai cách biểu đạt tương ứng; cách `temporal.query(query)` thường thể hiện ý định rõ hơn trong mã sử dụng.

Cần phân biệt **đối tượng truy vấn** với **kết quả truy vấn**:

- `TemporalQueries.localDate()` tạo/cung cấp một `TemporalQuery<LocalDate>`.
- `temporal.query(TemporalQueries.localDate())` mới thực hiện truy vấn lên `temporal` và có thể trả một `LocalDate` hoặc `null`.
- Đối tượng truy vấn chuẩn được trả về không phải `null`; kết quả của nó có thể là `null` vì đầu vào thiếu thông tin.

Truy vấn dùng để đọc; nó không được sửa đối tượng đầu vào. Điều này khác `TemporalAdjuster`, vốn biểu đạt một phép điều chỉnh để tạo kết quả thời gian mới.

## 3. Bảy truy vấn có sẵn

[TemporalQueries](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalQueries.html) cung cấp bảy phương thức chuẩn:

| Phương thức | Kiểu kết quả | Câu hỏi được trả lời |
| --- | --- | --- |
| `localDate()` | `LocalDate` | Có thể lấy ngày địa phương theo lịch ISO không? |
| `localTime()` | `LocalTime` | Có thể lấy giờ địa phương không? |
| `zoneId()` | `ZoneId` | Đối tượng có chứa một `ZoneId` theo mô hình của nó không? |
| `zone()` | `ZoneId` | Có `ZoneId`, hoặc nếu thiếu thì có `ZoneOffset` không? |
| `offset()` | `ZoneOffset` | Có thể lấy độ lệch UTC không? |
| `chronology()` | `Chronology` | Đối tượng biểu diễn ngày theo hệ lịch nào? |
| `precision()` | `TemporalUnit` | Đơn vị nhỏ nhất mà kiểu đối tượng hỗ trợ là gì? |

Kết quả phụ thuộc thông tin của đầu vào. Không nên coi `null` là đối tượng bị hỏng: nó thường biểu đạt rằng câu hỏi đó không có câu trả lời trong mô hình đang dùng.

### 3.1. localDate(): ngày địa phương, không phải ngày UTC mặc định

Với `LocalDate`, kết quả là chính ngày đó về mặt giá trị. Với `LocalDateTime`, `OffsetDateTime` hoặc `ZonedDateTime`, truy vấn lấy phần ngày địa phương của đối tượng.

Nó không tự chuyển sang UTC trước khi lấy ngày. Nếu một `ZonedDateTime` đang ở `Asia/Ho_Chi_Minh`, ngày được lấy là ngày địa phương trong đối tượng đó. Muốn ngày ở một múi giờ khác, cần chuyển cùng thời điểm sang múi giờ mong muốn rồi mới lấy ngày.

Với `Instant`, truy vấn này trả `null`. Một thời điểm trên dòng thời gian chưa xác định một ngày địa phương duy nhất nếu chưa chọn múi giờ. Muốn lấy ngày tại một vùng, phải thực hiện bước chọn vùng rõ ràng, chẳng hạn `instant.atZone(zone).toLocalDate()`.

Truy vấn chuẩn lấy ngày thông qua thông tin tương đương `EPOCH_DAY` và trả `LocalDate` theo lịch ISO. Khi đầu vào dùng một hệ lịch khác, kết quả không phải một ngày giữ nguyên lớp lịch gốc; nếu cần thông tin hệ lịch, truy vấn thêm `chronology()` hoặc dùng kiểu ngày theo hệ lịch phù hợp.

### 3.2. localTime(): giờ địa phương mà đối tượng có

`LocalTime`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime` có thông tin giờ nên có thể cung cấp `LocalTime`. `LocalDate` không có giờ; truy vấn không tự gán `00:00`.

Tương tự ngày địa phương, kết quả giờ không bao gồm offset hoặc múi giờ. Sau khi lấy riêng `LocalTime`, ta không còn đủ thông tin để xác định một thời điểm duy nhất trên dòng thời gian.

Truy vấn chuẩn dựa trên thông tin tương đương `NANO_OF_DAY`. Nó không tự đoán giờ từ một chuỗi hiển thị hoặc từ múi giờ mặc định của máy.

### 3.3. chronology(): hệ lịch

`chronology()` trả hệ lịch mà đối tượng dùng để biểu diễn ngày. Các kiểu `LocalDate`, `LocalDateTime`, `YearMonth` và `ZonedDateTime` thông thường dùng `IsoChronology`, thường được in là `ISO`.

`LocalTime` chỉ biểu diễn giờ nên không có hệ lịch ngày để báo. `Instant` biểu diễn thời điểm, không phải ngày lịch địa phương, nên cũng không cung cấp một chronology qua truy vấn này.

Không thay `null` bằng `ISO` một cách vô điều kiện nếu hệ lịch là ràng buộc quan trọng của phép tính. Đó sẽ là một chính sách bổ sung của ứng dụng, không phải thông tin thực sự được lấy từ đầu vào.

### 3.4. precision(): khả năng biểu diễn, không phải độ chính xác đo lường

`precision()` trả đơn vị nhỏ nhất được kiểu đó hỗ trợ, ví dụ:

| Kiểu | Kết quả điển hình |
| --- | --- |
| `LocalDate` | `ChronoUnit.DAYS` |
| `YearMonth` | `ChronoUnit.MONTHS` |
| `Year` | `ChronoUnit.YEARS` |
| `LocalTime` | `ChronoUnit.NANOS` |
| `LocalDateTime` | `ChronoUnit.NANOS` |
| `Instant` | `ChronoUnit.NANOS` |

Một `Instant` được phân tích từ chuỗi chỉ có phần giây vẫn hỗ trợ nano giây; `precision()` vẫn trả `NANOS`. Nó không ghi nhớ “chuỗi đầu vào có bao nhiêu chữ số thập phân”.

Nó cũng không chứng minh đồng hồ hệ điều hành hoặc thiết bị đo thực sự chính xác tới nano giây. Khả năng lưu giá trị, độ phân giải dữ liệu nguồn và độ chính xác phép đo là các vấn đề riêng.

Một đối tượng không biểu diễn ngày/giờ đầy đủ theo nghĩa phù hợp, chẳng hạn `MonthDay`, có thể trả `null`. Không nên giả định mọi `TemporalAccessor` đều có precision.

## 4. zoneId(), zone() và offset(): ba câu hỏi khác nhau

### 4.1. ZoneId và ZoneOffset

`ZoneId` biểu diễn một định danh múi giờ; nó có thể là vùng như `Asia/Ho_Chi_Minh` hoặc một độ lệch cố định. `ZoneOffset` biểu diễn độ lệch so với UTC, chẳng hạn `+07:00`, đồng thời là một lớp con của `ZoneId`.

Một offset cố định không lưu danh tính vùng và toàn bộ các quy tắc thay đổi offset của vùng đó. Nhiều vùng có thể dùng cùng offset tại một thời điểm; từ `+07:00` không thể khôi phục duy nhất tên vùng ban đầu.

### 4.2. zoneId() không tự chuyển offset thành câu trả lời

`zoneId()` yêu cầu đầu vào chứa một `ZoneId` theo mô hình của kiểu:

- `ZonedDateTime` trả `getZone()`.
- `OffsetDateTime` chỉ có offset, nên trả `null`.
- `LocalDateTime` không có cả zone lẫn offset, nên trả `null`.

Từ “yêu cầu chặt hơn” ở đây không có nghĩa là chỉ nhận tên vùng. Một `ZonedDateTime` được tạo với zone cố định `+07:00` vẫn chứa `ZoneId` hợp lệ; `zoneId()` có thể trả chính `+07:00`. Muốn kiểm tra đầu vào có mang tên vùng hay chỉ offset cố định, cần đặt thêm điều kiện rõ ràng.

### 4.3. zone() cho phép dùng offset khi thiếu zone

`zone()` tìm `zoneId()` trước; nếu không có thì thử `offset()`. Vì `ZoneOffset` cũng là `ZoneId`, kiểu kết quả vẫn là `ZoneId`.

| Đầu vào | `zoneId()` | `zone()` | `offset()` |
| --- | --- | --- | --- |
| `ZonedDateTime` với vùng `Asia/Ho_Chi_Minh` trong ví dụ | `Asia/Ho_Chi_Minh` | `Asia/Ho_Chi_Minh` | `+07:00` |
| `OffsetDateTime` có offset `+07:00` | `null` | `+07:00` | `+07:00` |
| `ZonedDateTime` với zone cố định `+07:00` | `+07:00` | `+07:00` | `+07:00` |
| `LocalDateTime` | `null` | `null` | `null` |
| `Instant` | `null` | `null` | `null` |

Hàng `Instant` dễ gây nhầm vì `Instant.toString()` thường kết thúc bằng `Z`. Cách in đó không có nghĩa đối tượng chứa một zone/offset địa phương mà các truy vấn chuẩn sẽ trả về. Muốn một đối tượng có vùng UTC, dùng `instant.atZone(ZoneOffset.UTC)` rõ ràng.

### 4.4. offset() không thay thế quy tắc múi giờ

Với `ZonedDateTime`, `offset()` trả offset đang áp dụng tại ngày giờ đó. Nó không trả toàn bộ quy tắc của vùng và không bảo đảm offset sẽ giống hệt vào một thời điểm khác.

Chọn truy vấn theo điều kiện nghiệp vụ:

- Chỉ cần một zone hoặc offset để tiếp tục thao tác: cân nhắc `zone()`.
- Cần biết đối tượng đã mang `ZoneId`: dùng `zoneId()` và xử lý thiếu.
- Cần độ lệch UTC cụ thể: dùng `offset()`.
- Cần danh tính vùng và quy tắc vùng để diễn giải các ngày khác: kiểm tra dữ liệu vùng theo hợp đồng, không suy ngược từ offset.

## 5. Chương trình Java 17+ đầy đủ

Lưu thành `TemporalQueriesDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;
import java.time.temporal.TemporalQuery;

public class TemporalQueriesDemo {
    static final TemporalQuery<Boolean> IS_MONTH_END = temporal -> {
        LocalDate date = temporal.query(TemporalQueries.localDate());
        if (date == null) {
            return null;
        }
        return date.getDayOfMonth() == date.lengthOfMonth();
    };

    static void showZones(String label, TemporalAccessor temporal) {
        System.out.println(label
                + ": zoneId=" + temporal.query(TemporalQueries.zoneId())
                + ", zone=" + temporal.query(TemporalQueries.zone())
                + ", offset=" + temporal.query(TemporalQueries.offset()));
    }

    public static void main(String[] args) {
        OffsetDateTime offset = OffsetDateTime.parse(
                "2024-06-15T10:20:30+07:00");
        ZonedDateTime zoned = offset.atZoneSameInstant(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("date = "
                + zoned.query(TemporalQueries.localDate()));
        System.out.println("time = "
                + zoned.query(TemporalQueries.localTime()));
        System.out.println("zoneId = "
                + zoned.query(TemporalQueries.zoneId()));
        System.out.println("zone = "
                + zoned.query(TemporalQueries.zone()));
        System.out.println("offset = "
                + zoned.query(TemporalQueries.offset()));
        System.out.println("chronology = "
                + zoned.query(TemporalQueries.chronology()));
        System.out.println("precision = "
                + zoned.query(TemporalQueries.precision()));

        showZones("OffsetDateTime", offset);
        showZones("LocalDateTime", offset.toLocalDateTime());
        showZones("fixed ZonedDateTime",
                offset.atZoneSameInstant(ZoneOffset.ofHours(7)));

        Instant instant = Instant.parse("2024-06-15T03:20:30Z");
        showZones("Instant", instant);
        System.out.println("instant date = "
                + instant.query(TemporalQueries.localDate()));
        System.out.println("instant precision = "
                + instant.query(TemporalQueries.precision()));
        System.out.println("date precision = "
                + LocalDate.of(2024, 6, 15)
                        .query(TemporalQueries.precision()));
        System.out.println("month precision = "
                + YearMonth.of(2024, 6)
                        .query(TemporalQueries.precision()));

        LocalDate last = LocalDate.of(2024, 2, 29);
        LocalDate first = LocalDate.of(2024, 2, 1);
        System.out.println("month-end true = " + last.query(IS_MONTH_END));
        System.out.println("month-end false = " + first.query(IS_MONTH_END));
        System.out.println("month-end absent = "
                + YearMonth.of(2024, 2).query(IS_MONTH_END));

        LocalTime time = LocalTime.of(10, 20, 30);
        System.out.println("optional date = "
                + time.query(TemporalQueries.localDate()));
        try {
            time.query(LocalDate::from);
        } catch (DateTimeException ex) {
            System.out.println("required date -> "
                    + ex.getClass().getSimpleName());
        }

        LocalDate viaMethod = zoned.query(TemporalQueries.localDate());
        LocalDate viaQueryFrom =
                TemporalQueries.localDate().queryFrom(zoned);
        System.out.println("equivalent calls = "
                + viaMethod.equals(viaQueryFrom));

        LocalDateTime local = LocalDateTime.of(2024, 6, 15, 10, 20, 30);
        System.out.println("original local = " + local);
        System.out.println("local has zone = "
                + (local.query(TemporalQueries.zone()) != null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TemporalQueriesDemo.java
java TemporalQueriesDemo
```

Stdout:

```text
date = 2024-06-15
time = 10:20:30
zoneId = Asia/Ho_Chi_Minh
zone = Asia/Ho_Chi_Minh
offset = +07:00
chronology = ISO
precision = Nanos
OffsetDateTime: zoneId=null, zone=+07:00, offset=+07:00
LocalDateTime: zoneId=null, zone=null, offset=null
fixed ZonedDateTime: zoneId=+07:00, zone=+07:00, offset=+07:00
Instant: zoneId=null, zone=null, offset=null
instant date = null
instant precision = Nanos
date precision = Days
month precision = Months
month-end true = true
month-end false = false
month-end absent = null
optional date = null
required date -> DateTimeException
equivalent calls = true
original local = 2024-06-15T10:20:30
local has zone = false
```

Chương trình cung cấp sẵn đầu vào và chọn vùng rõ ràng, không dựa vào ngày hiện tại hoặc múi giờ mặc định của máy. Các dòng đầu minh họa đủ bảy truy vấn. Các dòng tiếp theo đối chiếu trường hợp có vùng, chỉ có offset và thiếu cả hai.

`atZoneSameInstant` trong ví dụ chuyển từ `OffsetDateTime` sang `ZonedDateTime` mà giữ cùng thời điểm. Đó là bước chuyển đổi dữ liệu rõ ràng trước truy vấn, không phải hành vi tự động của `TemporalQueries`.

## 6. null, false và ngoại lệ phải có ý nghĩa riêng

### 6.1. Truy vấn chuẩn có thể không tìm được thông tin

Đọc ngày từ `LocalTime`:

```java
LocalDate date = time.query(TemporalQueries.localDate());
```

Kết quả là `null` vì giờ đơn lẻ không chứa ngày. Nếu thông tin là tùy chọn, nơi gọi có thể kiểm tra `null` hoặc bọc kết quả bằng `Optional.ofNullable` ở biên của ứng dụng.

Không tự gán ngày hôm nay để tránh `null`. Cách đó làm kết quả phụ thuộc đồng hồ, môi trường và ngày chạy, đồng thời che việc đầu vào thiếu dữ liệu.

### 6.2. Tham chiếu phương thức có thể dùng hợp đồng chặt hơn

Một phương thức như `LocalDate.from(TemporalAccessor)` có thể được dùng làm truy vấn:

```java
LocalDate requiredDate = temporal.query(LocalDate::from);
```

Nếu không thể lấy ngày, `LocalDate.from` ném `DateTimeException` thay vì trả `null`. Do đó, `TemporalQueries.localDate()` và `LocalDate::from` gần nhau về loại thông tin cần lấy nhưng **khác hợp đồng khi thiếu thông tin**.

Chương trình dùng `LocalTime` để quan sát rõ: truy vấn chuẩn trả `null`; tham chiếu phương thức ném ngoại lệ. Hãy chọn cách phù hợp với việc ngày là tùy chọn hay bắt buộc.

Tương tự, `ZoneId::from` có thể dùng như một truy vấn yêu cầu lấy được zone, cho phép dùng offset khi phù hợp và ném lỗi nếu không lấy được; không nên coi nó là tên viết khác của truy vấn `zoneId()` chặt hơn.

### 6.3. Hợp đồng của truy vấn tự viết do người viết quyết định

Giao diện `TemporalQuery<R>` không bắt mọi truy vấn phải dùng chung một tín hiệu thất bại. Truy vấn tự viết có thể:

- Trả `null` khi không có thông tin.
- Trả một kiểu kết quả thể hiện rõ trạng thái thiếu.
- Ném ngoại lệ nếu đầu vào không thỏa điều kiện bắt buộc.

Điều cần thiết là nêu rõ hợp đồng và giữ nhất quán. `false` nên biểu đạt một mệnh đề đã đánh giá và không đúng; không nên mặc định dùng nó thay cho “không có đủ dữ liệu để đánh giá”.

## 7. Viết một TemporalQuery nhỏ có thể dùng lại

Trong chương trình, `IS_MONTH_END` trả lời “đây có phải ngày cuối tháng không?”:

1. Truy vấn `LocalDate` từ đầu vào.
2. Nếu thiếu ngày, trả `null`.
3. Nếu có ngày, so sánh ngày trong tháng với độ dài tháng.

Các kết quả được phân biệt:

| Đầu vào | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `LocalDate.of(2024, 2, 29)` | `true` | Có ngày và đó là ngày cuối tháng |
| `LocalDate.of(2024, 2, 1)` | `false` | Có ngày nhưng chưa cuối tháng |
| `YearMonth.of(2024, 2)` | `null` | Biết tháng nhưng chưa có ngày cụ thể để xét |

Phần tính toán không cần tự viết quy tắc năm nhuận; `LocalDate.lengthOfMonth()` cung cấp độ dài tháng đúng theo ngữ cảnh.

Vì kết quả là `Boolean` có thể `null`, viết `if (temporal.query(IS_MONTH_END))` có thể gây `NullPointerException` do tự mở hộp. Nếu ba trạng thái có ý nghĩa, hãy xử lý riêng. `Boolean.TRUE.equals(result)` tránh lỗi mở hộp nhưng gộp `false` và `null` thành nhánh không đúng; chỉ dùng khi chính sách của nơi gọi chấp nhận sự gộp đó.

Truy vấn này đánh giá ngày ISO lấy từ `localDate()`. Nếu yêu cầu là “cuối tháng theo hệ lịch gốc của đầu vào”, cần một truy vấn khác với hợp đồng hệ lịch rõ ràng. Không lấy ngày ISO rồi tuyên bố kết quả đúng cho mọi lịch.

### 7.1. Tránh đệ quy gọi lại chính truy vấn

Một hiện thực kiểu sau không thực hiện việc đọc mà chỉ gọi lại chính mình:

```java
TemporalQuery<LocalDate> broken = new TemporalQuery<>() {
    @Override
    public LocalDate queryFrom(TemporalAccessor temporal) {
        return temporal.query(this);
    }
};
```

Đây là **mã minh họa lỗi, không gọi để chạy thử**. Với kiểu đầu vào không xử lý riêng truy vấn đó, `query` sẽ chuyển về `queryFrom`, tạo đệ quy và có thể dẫn tới `StackOverflowError`.

Trong truy vấn tự viết, hãy thực sự đọc trường hoặc dùng một truy vấn khác đã biết hợp đồng, như `TemporalQueries.localDate()` trong `IS_MONTH_END`.

### 7.2. Tránh trạng thái thay đổi trong truy vấn dùng chung

Truy vấn có thể được dùng từ nhiều luồng. Một lambda chỉ đọc đầu vào và dùng dữ liệu bất biến dễ giữ an toàn hơn một đối tượng truy vấn có bộ đếm hoặc danh sách bị sửa khi chạy.

Không sửa đầu vào, không phụ thuộc ngầm múi giờ hệ thống và không đọc ngày hiện tại trừ khi đó là một phần đã được nêu trong hợp đồng. Nếu truy vấn cần dữ liệu ngoài, hãy cung cấp dữ liệu một cách rõ ràng và giữ ảnh chụp ổn định khi cần kết quả có thể lặp lại.

## 8. Chọn truy vấn hay phương thức cụ thể?

Dùng phương thức của kiểu cụ thể khi nó thể hiện đủ ý định:

```java
LocalDate date = zonedDateTime.toLocalDate();
ZoneId zone = zonedDateTime.getZone();
```

Dùng truy vấn khi cần một cách lấy thông tin có thể dùng lại trên nhiều kiểu `TemporalAccessor` hoặc khi muốn truyền chiến lược lấy kết quả vào một thành phần khác:

```java
TemporalQuery<LocalDate> dateQuery = TemporalQueries.localDate();
```

Không cần biến mọi thao tác đơn giản thành một lớp truy vấn riêng. Giá trị của `TemporalQuery` nằm ở việc biểu đạt một câu hỏi có hợp đồng rõ và có thể áp dụng thống nhất, không phải tăng số lớp trung gian.

Cũng cần nhớ rằng cùng một truy vấn ngày trên `OffsetDateTime` và `ZonedDateTime` lấy ngày địa phương của từng đối tượng. Nếu ứng dụng cần một ngày báo cáo theo múi giờ cố định, hãy chuẩn hóa thời điểm sang vùng báo cáo trước. Chỉ dùng cùng một đối tượng truy vấn chưa đủ để bảo đảm cùng chính sách múi giờ.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi `TemporalQueries.zone()` là zone đã lấy được | Nhầm đối tượng truy vấn với kết quả | Gọi `temporal.query(...)` |
| Đọc `zoneId()` từ `OffsetDateTime` rồi kết luận thiếu mọi thông tin offset | Bỏ qua offset đang có | Dùng `offset()` hoặc `zone()` đúng nhu cầu |
| Coi mọi kết quả `zoneId()` đều là tên vùng | Bỏ qua zone cố định | Kiểm tra hợp đồng yêu cầu vùng rõ ràng |
| Lấy ngày từ `Instant` mà không chọn vùng | Thiếu ngày địa phương | Chọn zone bằng `atZone` trước |
| Thấy `Z` trong chuỗi `Instant` rồi mong `offset()` trả UTC | Nhầm định dạng với thông tin truy vấn | Chuyển sang đối tượng gắn UTC nếu cần |
| Hiểu `precision = NANOS` là độ chính xác đo nano giây | Đánh đồng mô hình với nguồn dữ liệu | Tách khả năng biểu diễn khỏi độ chính xác |
| Coi mọi truy vấn đều trả `null` khi thất bại | Bỏ sót hợp đồng ném ngoại lệ | Đọc hợp đồng từng truy vấn |
| Tự mở hộp `Boolean` có thể `null` | `NullPointerException` | Xử lý rõ trạng thái thiếu |
| Trong `queryFrom` chỉ gọi `temporal.query(this)` | Đệ quy | Thực hiện logic đọc thực sự |
| Lấy ngày ISO rồi đánh giá quy tắc tháng của hệ lịch khác | Sai ý nghĩa lịch | Chọn hệ lịch trong hợp đồng |

## 10. Tự kiểm chứng và thực hành

1. Truy vấn `localDate()`, `localTime()` và `chronology()` trên `LocalDate`, `LocalTime`, `LocalDateTime`. Dự đoán trước trường hợp nào trả `null` rồi kiểm tra.
2. Tạo một `OffsetDateTime` có offset `+07:00`. Giải thích vì sao `zone()` có giá trị nhưng `zoneId()` không có.
3. Chuyển nó sang `ZonedDateTime` với zone cố định `ZoneOffset.ofHours(7)`. Kiểm tra rằng `zoneId()` lúc này có giá trị, dù vẫn không có tên vùng.
4. Dùng một `Instant` gần ranh giới ngày, chẳng hạn `2024-06-14T18:30:00Z`, rồi chọn UTC và `Asia/Ho_Chi_Minh`. Ngày UTC là 14/06, ngày tại vùng `+07:00` trong ví dụ là 15/06. Phân biệt bước chọn vùng với bước lấy ngày.
5. So sánh `precision()` của `Instant` có phần nano bằng `0` với `Instant` có phần nano khác `0`. Cả hai vẫn hỗ trợ `NANOS`.
6. Dùng `IS_MONTH_END` trên một `LocalDateTime` ở ngày cuối tháng và trên `YearMonth`. Giải thích vì sao chỉ có tên tháng chưa đủ để kết luận về một ngày cụ thể.
7. Viết truy vấn trả quý ISO theo kiểu `Integer`, trả `null` nếu không lấy được ngày. Kiểm tra tháng 1, 3, 4 và 12; ghi rõ rằng kết quả dựa trên ngày ISO.
8. Đổi hợp đồng truy vấn cuối tháng thành bắt buộc có ngày bằng `LocalDate.from`. Ghi lại cách nơi gọi phải xử lý đầu vào chỉ có giờ.

Khi dùng `TemporalQuery`, điều quan trọng là biết chính xác đang hỏi thông tin gì, đầu vào có cung cấp được thông tin đó không và hợp đồng biểu diễn sự thiếu thông tin như thế nào.
