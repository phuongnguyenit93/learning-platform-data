# Ngày, giờ, thời điểm, múi giờ và duration

Neo4j hỗ trợ các giá trị ngày giờ và khoảng thời gian như những kiểu dữ liệu native. Spring Data Neo4j (SDN) có thể ánh xạ các kiểu thời gian Java tương ứng qua Neo4j Java Driver. Khi thiết kế entity, điều quan trọng là chọn đúng kiểu cho ý nghĩa của dữ liệu: ngày sinh không giống thời điểm một sự kiện xảy ra; giờ mở cửa không giống thời điểm có múi giờ; và khoảng thời gian lịch không phải lúc nào cũng tương đương với một số giây cố định.

Nếu lưu tất cả dưới dạng chuỗi, ứng dụng phải tự phân tích và chuẩn hóa dữ liệu, đồng thời dễ gặp lỗi khi so sánh, sắp xếp hoặc tính toán. Dùng kiểu temporal native giúp Neo4j hiểu giá trị là ngày, giờ, thời điểm hay duration và hỗ trợ các phép toán Cypher phù hợp.

## 1. Các khái niệm thời gian cần phân biệt

Trước khi chọn kiểu Java, hãy xác định dữ liệu đang biểu diễn điều gì:

- **Ngày lịch:** một ngày cụ thể, không kèm giờ hoặc múi giờ, ví dụ ngày sinh hoặc ngày hết hạn.
- **Giờ trong ngày:** một thời điểm trên đồng hồ, không kèm ngày, ví dụ giờ mở cửa hằng ngày.
- **Ngày giờ địa phương:** ngày và giờ theo đồng hồ tại một địa điểm, nhưng chưa xác định múi giờ hoặc offset.
- **Thời điểm tuyệt đối:** một điểm trên dòng thời gian, có thể quy đổi về UTC và so sánh nhất quán giữa các vùng.
- **Múi giờ:** quy tắc địa lý như `Asia/Ho_Chi_Minh`, bao gồm cả thay đổi offset theo lịch sử hoặc quy tắc giờ mùa hè của vùng đó.
- **Duration:** khoảng thời gian. Một khoảng có thể biểu diễn số giây đã trôi qua hoặc một khoảng theo lịch như một tháng.

Hai giá trị có cùng phần ngày giờ nhưng khác múi giờ có thể đại diện cho hai thời điểm khác nhau. Ngược lại, cùng một thời điểm tuyệt đối có thể hiển thị thành các giờ địa phương khác nhau.

## 2. Kiểu temporal trong Neo4j và Java

Neo4j có các kiểu temporal tương ứng với các hàm Cypher như `date()`, `localtime()`, `time()`, `localdatetime()`, `datetime()` và `duration()`.

| Ý nghĩa | Kiểu Java thường dùng | Kiểu temporal Neo4j | Ghi chú |
|---|---|---|---|
| Ngày lịch | `LocalDate` | `DATE` | Không có giờ hoặc múi giờ |
| Giờ địa phương | `LocalTime` | `LOCAL TIME` | Không có ngày hoặc offset |
| Giờ có offset | `OffsetTime` | `TIME` | Có offset so với UTC |
| Ngày giờ địa phương | `LocalDateTime` | `LOCAL DATETIME` | Không xác định được thời điểm tuyệt đối nếu thiếu múi giờ |
| Ngày giờ có offset hoặc vùng | `OffsetDateTime`, `ZonedDateTime` | `DATETIME` | Có thông tin offset; `ZonedDateTime` còn mang ZoneId |
| Khoảng thời gian | `org.neo4j.driver.types.IsoDuration` ở tầng driver | `DURATION` | Có thể chứa tháng, ngày, giây và nano giây |

Các kiểu Java trong bảng thuộc `java.time`, ngoại trừ `IsoDuration` là kiểu của Neo4j Java Driver. Với các phiên bản SDN và driver hiện đại, những kiểu Java temporal được hỗ trợ có thể được ánh xạ qua cơ chế conversion tích hợp. Hãy kiểm tra ma trận tương thích của phiên bản dự án khi dùng kiểu temporal ít phổ biến hoặc kiểu duration riêng.

`Instant` biểu diễn một thời điểm tuyệt đối theo UTC nhưng không mang ZoneId. Nếu mô hình miền dùng `Instant`, hãy xác nhận converter của phiên bản SDN/driver đang dùng; có thể chuyển đổi tường minh sang `OffsetDateTime` ở UTC hoặc đăng ký custom converter để kiểm soát cách lưu và đọc.

## 3. Chọn kiểu Java theo ý nghĩa dữ liệu

### Ngày lịch: `LocalDate`

Dùng `LocalDate` cho ngày sinh, ngày ký hợp đồng hoặc ngày đến hạn khi giờ trong ngày không có ý nghĩa.

```java
import java.time.LocalDate;

private LocalDate birthDate;
```

Giá trị này được ánh xạ thành Neo4j `DATE`. Không nên dùng `LocalDateTime` rồi đặt giờ thành nửa đêm chỉ để lưu một ngày, vì điều đó đưa thêm thông tin giờ không cần thiết vào mô hình.

### Giờ trong ngày: `LocalTime`

Dùng `LocalTime` cho giờ mở cửa, giờ bắt đầu ca làm hoặc giờ nhắc lặp lại mỗi ngày khi không gắn với ngày cụ thể.

```java
import java.time.LocalTime;

private LocalTime opensAt;
```

`LocalTime` không nói rằng 09:00 ở Hà Nội tương ứng với 09:00 ở London hay cùng một thời điểm tuyệt đối. Nếu nghiệp vụ cần offset, hãy xem xét `OffsetTime`; nếu cần ngày và vùng địa lý, hãy lưu ngày giờ có múi giờ phù hợp.

### Ngày giờ địa phương: `LocalDateTime`

Dùng `LocalDateTime` khi dữ liệu là giờ trên đồng hồ địa phương nhưng chưa cần xác định thời điểm tuyệt đối, chẳng hạn giờ ghi trên một biểu mẫu chưa gắn địa điểm hoặc giờ dự kiến trong một lịch chưa chọn múi giờ.

```java
import java.time.LocalDateTime;

private LocalDateTime importedAt;
```

`LocalDateTime` không chứa offset hoặc ZoneId. Không thể chỉ từ `2026-11-26T09:00` xác định được sự kiện xảy ra trước hay sau một thời điểm khác ở múi giờ khác. Nếu dữ liệu thực sự là một sự kiện đã xảy ra, hãy lưu kiểu có offset hoặc chuẩn hóa thời điểm sang UTC.

### Thời điểm có múi giờ: `ZonedDateTime` hoặc `OffsetDateTime`

Dùng `OffsetDateTime` khi cần ngày giờ kèm offset cụ thể như `+07:00`. Dùng `ZonedDateTime` khi cần giữ cả múi giờ địa lý như `Asia/Ho_Chi_Minh`, đặc biệt với lịch hẹn tương lai chịu ảnh hưởng của quy tắc múi giờ.

```java
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;

private OffsetDateTime receivedAt;
private ZonedDateTime scheduledAt;
```

Neo4j `DATETIME` có thể lưu thông tin offset hoặc tên vùng múi giờ. Khi nghiệp vụ cần hiển thị đúng giờ địa phương theo quy tắc của một vùng, giữ ZoneId là điều có ý nghĩa. Offset cố định như `+07:00` không chứa toàn bộ quy tắc lịch sử hoặc thay đổi theo mùa của một vùng địa lý.

## 4. Ví dụ entity chứa nhiều kiểu thời gian

Giả sử ứng dụng quản lý sự kiện. Ngày tổ chức, giờ mở cửa, thời điểm bắt đầu và thời điểm nhập dữ liệu có ý nghĩa khác nhau:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZonedDateTime;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Event")
public class Event {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private LocalDate eventDate;
    private LocalTime doorsOpenAt;
    private ZonedDateTime startsAt;
    private LocalDateTime importedAt;

    protected Event() {
    }

    public Event(String name, LocalDate eventDate,
                 LocalTime doorsOpenAt, ZonedDateTime startsAt) {
        this.name = name;
        this.eventDate = eventDate;
        this.doorsOpenAt = doorsOpenAt;
        this.startsAt = startsAt;
    }

    public Long getId() {
        return id;
    }

    public ZonedDateTime getStartsAt() {
        return startsAt;
    }
}
```

Trong entity này, `eventDate` là ngày lịch, `doorsOpenAt` là giờ trên đồng hồ, `startsAt` là thời điểm bắt đầu có vùng múi giờ, còn `importedAt` là ngày giờ địa phương theo ý nghĩa mà ứng dụng gán cho nó. Nếu `importedAt` thực chất là dấu thời gian audit của một sự kiện đã xảy ra, nên cân nhắc `OffsetDateTime` hoặc `ZonedDateTime` thay cho `LocalDateTime`.

Các kiểu temporal được ánh xạ theo giá trị, không cần chuyển thành chuỗi trước khi lưu. Nếu có yêu cầu định dạng hiển thị, hãy định dạng ở tầng giao diện hoặc API; không biến chuỗi hiển thị thành kiểu lưu trữ chính.

## 5. Tạo giá trị ngày giờ có múi giờ trong Java

Khi cần tạo thời điểm từ ngày và giờ địa phương, phải cung cấp múi giờ để chuyển đổi có ý nghĩa:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime scheduledAt = ZonedDateTime.of(
    LocalDate.of(2026, 11, 26),
    LocalTime.of(9, 30),
    ZoneId.of("Asia/Ho_Chi_Minh")
);
```

Nếu muốn chuẩn hóa một thời điểm về UTC nhưng vẫn giữ nguyên thời điểm tuyệt đối, dùng `withZoneSameInstant`:

```java
import java.time.ZoneOffset;

ZonedDateTime utcTime = scheduledAt.withZoneSameInstant(ZoneOffset.UTC);
```

`withZoneSameInstant` giữ nguyên thời điểm trên dòng thời gian và thay đổi cách biểu diễn. Ngược lại, `withZoneSameLocal` giữ nguyên phần giờ địa phương rồi diễn giải nó trong vùng mới, vì vậy có thể tạo ra một thời điểm tuyệt đối khác. Hai thao tác này không thể thay thế cho nhau.

Nếu cần khôi phục giờ địa phương ban đầu sau khi lưu UTC, hãy lưu thêm ZoneId như `Asia/Ho_Chi_Minh` ở property riêng hoặc giữ `ZonedDateTime` có vùng thích hợp. Chỉ lưu offset `+07:00` không đủ để khôi phục mọi quy tắc của vùng địa lý trong các trường hợp có thay đổi múi giờ.

## 6. Lưu và truy vấn temporal bằng Cypher

Cypher cung cấp hàm tạo các kiểu temporal native. Ví dụ:

```cypher
CREATE (:Event {
    eventDate: date('2026-11-26'),
    doorsOpenAt: localtime('09:00:00'),
    reminderAt: time('09:00:00+07:00'),
    importedAt: localdatetime('2026-11-26T08:45:00'),
    startsAt: datetime('2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]'),
    duration: duration('PT90M')
});
```

Các hàm này tạo giá trị temporal thay vì chuỗi văn bản. Khi truy vấn, có thể so sánh trực tiếp các giá trị cùng loại:

```cypher
MATCH (e:Event)
WHERE e.startsAt >= datetime('2026-11-26T00:00:00Z')
  AND e.startsAt < datetime('2026-11-27T00:00:00Z')
RETURN e
ORDER BY e.startsAt;
```

Khoảng điều kiện dùng cận dưới bao gồm và cận trên không bao gồm. Cách viết này giúp phân chia các khoảng thời gian liên tiếp mà không bị tính trùng sự kiện đúng tại ranh giới.

## 7. Truyền tham số thời gian vào repository

Với truy vấn ứng dụng, hãy bind tham số temporal có kiểu thay vì nối chuỗi ngày giờ vào Cypher. Ví dụ, repository tìm sự kiện trong một khoảng `ZonedDateTime`:

```java
import java.time.ZonedDateTime;
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface EventRepository extends Neo4jRepository<Event, Long> {

    @Query("""
        MATCH (e:Event)
        WHERE e.startsAt >= $from AND e.startsAt < $until
        RETURN e
        ORDER BY e.startsAt
        """)
    List<Event> findStartingBetween(
        @Param("from") ZonedDateTime from,
        @Param("until") ZonedDateTime until
    );
}
```

SDN và driver chuyển giá trị temporal Java được hỗ trợ thành giá trị tương ứng trong Neo4j. Tham số `$from` và `$until` giữ kiểu dữ liệu ngày giờ, vì vậy Neo4j có thể so sánh theo ngữ nghĩa temporal thay vì so sánh chuỗi.

Khi truy vấn theo ngày lịch, dùng `LocalDate` và điều kiện trên property `DATE`. Khi truy vấn theo thời điểm tuyệt đối, dùng kiểu có offset/vùng và thống nhất quy tắc múi giờ của hai cận. Không trộn `LocalDateTime` với `ZonedDateTime` chỉ vì cả hai đều có ngày và giờ.

## 8. Duration: khoảng thời gian theo lịch và thời gian đã trôi qua

Neo4j `DURATION` có bốn thành phần: tháng, ngày, giây và nano giây. Cấu trúc này quan trọng vì một tháng không có số ngày cố định và một ngày theo lịch có thể không luôn tương đương 24 giờ ở những vùng có chuyển đổi giờ mùa hè.

Ví dụ Cypher:

```cypher
RETURN duration('P1M') AS oneCalendarMonth,
       duration('P2DT3H') AS twoDaysAndThreeHours,
       duration('PT90M') AS ninetyMinutes;
```

Một số cách biểu diễn cần phân biệt:

- `P1M`: một tháng theo lịch.
- `P2D`: hai ngày theo lịch.
- `PT24H`: hai mươi bốn giờ đã trôi qua.
- `PT90M`: chín mươi phút.

Trong Java, `java.time.Duration` biểu diễn lượng thời gian theo giây và nano giây; nó phù hợp với khoảng thời gian đã trôi qua. `java.time.Period` biểu diễn năm, tháng và ngày theo lịch. Không nên giả định `Duration.ofDays(1)` luôn có ý nghĩa giống một ngày lịch khi cộng vào thời điểm ở vùng có quy tắc múi giờ.

Ở tầng Neo4j Java Driver, `org.neo4j.driver.types.IsoDuration` biểu diễn đầy đủ thành phần duration của Neo4j. Nếu entity cần dùng `java.time.Duration`, `Period` hoặc một kiểu miền riêng, hãy kiểm tra converter được cung cấp bởi phiên bản SDN/driver; nếu cần giữ đủ cả tháng, ngày, giây và nano giây, hãy cấu hình conversion tường minh sang `IsoDuration` thay vì làm mất thành phần.

## 9. Múi giờ và giờ mùa hè (DST)

Một `LocalDateTime` như `2026-11-26T09:30` không thể xác định thời điểm tuyệt đối nếu thiếu vùng múi giờ. Khi xử lý lịch hẹn, thời gian chạy sự kiện hoặc deadline gắn với địa điểm, hãy lưu đủ thông tin để xác định đúng thời điểm.

Các vùng múi giờ được xác định bằng tên IANA như `Asia/Ho_Chi_Minh`, `Europe/Paris` hoặc `America/New_York`. Một số vùng thay đổi offset theo mùa hoặc theo quyết định hành chính. Offset cố định như `+07:00` chỉ mô tả chênh lệch tại một thời điểm, không chứa quy tắc thay đổi theo ngày.

Khi chuyển giờ địa phương sang `ZonedDateTime`, có thể gặp giờ không tồn tại hoặc giờ bị lặp trong thời điểm chuyển DST. Ví dụ, khi đồng hồ tiến từ 01:59 lên 03:00, một số giờ địa phương không tồn tại; khi đồng hồ lùi, một giờ có thể xuất hiện hai lần. Ứng dụng cần xác định chính sách xử lý các trường hợp này thay vì để dữ liệu nhập vào được diễn giải một cách bất ngờ.

Với hệ thống cần lịch hẹn theo giờ địa phương trong tương lai, nên giữ ZoneId cùng với lịch hẹn. Với log hoặc thời điểm sự kiện đã xảy ra, lưu một thời điểm tuyệt đối và thường chuẩn hóa về UTC để so sánh, sắp xếp và đồng bộ giữa các hệ thống.

## 10. Index và tối ưu truy vấn theo thời gian

Nếu ứng dụng thường tìm sự kiện theo thời điểm bắt đầu, có thể tạo index trên temporal property:

```cypher
CREATE INDEX event_starts_at IF NOT EXISTS
FOR (e:Event)
ON (e.startsAt);
```

Sau đó dùng điều kiện khoảng trên cùng property:

```cypher
MATCH (e:Event)
WHERE e.startsAt >= $from AND e.startsAt < $until
RETURN e
ORDER BY e.startsAt;
```

Index chỉ có ích khi phù hợp với mẫu truy vấn và dữ liệu thực tế. Hãy dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra kế hoạch thực thi và xác nhận Neo4j có thể tận dụng index. Tránh bọc property bằng hàm chuyển đổi trong điều kiện nếu không cần thiết, vì biểu thức có thể làm giảm khả năng sử dụng index.

Lưu temporal dưới dạng chuỗi ISO 8601 có thể thuận tiện khi tích hợp văn bản, nhưng không thay thế hoàn toàn kiểu temporal native. Chuỗi không cung cấp ngữ nghĩa kiểu cho các phép toán ngày giờ, và việc sắp xếp theo chuỗi có thể sai nếu format hoặc offset không được chuẩn hóa thống nhất.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `LocalDateTime` cho sự kiện cần thời điểm tuyệt đối | Không biết sự kiện xảy ra ở múi giờ nào | Dùng `OffsetDateTime` hoặc `ZonedDateTime` |
| Lưu giờ mở cửa dưới dạng `ZonedDateTime` dù không cần ngày | Mô hình mang thông tin thừa và gây nhầm lẫn | Dùng `LocalTime` hoặc `OffsetTime` theo yêu cầu |
| Coi `+07:00` là tên múi giờ địa lý | Mất quy tắc lịch sử và thay đổi theo mùa | Dùng ZoneId IANA khi cần quy tắc vùng |
| Dùng `Duration` cho một tháng lịch | Một tháng không có độ dài cố định | Dùng `Period` hoặc Neo4j `DURATION` với thành phần lịch |
| Lưu tất cả ngày giờ thành chuỗi | Khó so sánh và tính toán theo kiểu temporal | Dùng kiểu temporal native |
| Truy vấn hai cận có múi giờ khác nhau mà không thống nhất ý nghĩa | Khoảng tìm kiếm có thể lệch so với ngày địa phương mong muốn | Chuyển hai cận về cùng quy ước thời điểm trước khi truy vấn |
| Giả định `Instant` luôn được ánh xạ tự động ở mọi phiên bản | Có thể gặp lỗi conversion khi lưu hoặc đọc | Kiểm tra phiên bản và cấu hình converter tường minh nếu cần |

## 12. Quy trình chọn và kiểm thử temporal

1. Xác định dữ liệu là ngày lịch, giờ trong ngày, ngày giờ địa phương, thời điểm tuyệt đối hay duration.
2. Chọn kiểu Java phù hợp: `LocalDate`, `LocalTime`, `OffsetTime`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` hoặc kiểu duration phù hợp.
3. Xác định có cần giữ ZoneId hay chỉ cần offset; thống nhất cách chuẩn hóa UTC cho dữ liệu sự kiện đã xảy ra.
4. Kiểm tra conversion của phiên bản SDN và Neo4j Java Driver, đặc biệt với `Instant`, `Duration`, `Period` và kiểu miền tùy chỉnh.
5. Lưu thử entity và đọc lại, xác nhận kiểu và giá trị không bị chuyển thành chuỗi hoặc mất thông tin múi giờ.
6. Kiểm tra truy vấn khoảng thời gian ở ranh giới, bao gồm thời điểm đúng bằng cận dưới và cận trên.
7. Kiểm thử các tình huống DST nếu ứng dụng xử lý lịch tại vùng có thay đổi giờ mùa hè.
8. Dùng `EXPLAIN` hoặc `PROFILE` để xác nhận index temporal phù hợp với truy vấn thực tế.

## 13. Tự kiểm tra

1. Khi nào nên dùng `LocalDate` thay cho `LocalDateTime`?
2. Vì sao `LocalDateTime` không đủ để xác định một thời điểm tuyệt đối?
3. Khác biệt giữa `OffsetDateTime` và `ZonedDateTime` là gì?
4. Vì sao offset `+07:00` không tương đương với ZoneId `Asia/Ho_Chi_Minh`?
5. `java.time.Duration` khác gì với một duration theo lịch như `P1M`?
6. Khi nào nên dùng kiểu `IsoDuration` của Neo4j Java Driver hoặc custom converter?
7. Vì sao nên dùng điều kiện khoảng có cận trên không bao gồm khi truy vấn sự kiện theo ngày?

Chọn đúng kiểu thời gian giúp dữ liệu trong Neo4j giữ được ý nghĩa của nó: ngày là ngày, giờ là giờ, thời điểm có múi giờ là một điểm xác định trên dòng thời gian, và duration giữ đúng ngữ nghĩa khoảng thời gian. Đây là nền tảng để ánh xạ entity chính xác, truy vấn theo khoảng và đồng bộ dữ liệu thời gian giữa các dịch vụ.
