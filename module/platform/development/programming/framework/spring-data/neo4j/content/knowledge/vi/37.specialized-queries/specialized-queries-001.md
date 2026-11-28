# Truy vấn thời gian và khoảng thời gian với kiểu dữ liệu phù hợp

Ứng dụng quản lý đơn hàng, lịch hẹn, đặt phòng và lịch sử hoạt động thường xuyên cần lọc dữ liệu theo ngày, thời điểm hoặc khoảng thời gian. Một truy vấn thời gian chính xác bắt đầu từ việc chọn đúng kiểu dữ liệu: ngày lịch, giờ địa phương, thời điểm có múi giờ hay một lượng thời gian đã trôi qua.

Neo4j Cypher có các kiểu temporal riêng như `DATE`, `LOCAL DATETIME`, `ZONED DATETIME` và `DURATION`. Spring Data Neo4j (SDN) ánh xạ các kiểu này với `java.time` để entity và tham số truy vấn giữ đúng ngữ nghĩa. Nếu lưu thời gian dưới dạng chuỗi tùy ý hoặc số nguyên mà không có quy ước rõ ràng, việc so sánh, lọc khoảng và xử lý múi giờ sẽ khó chính xác.

Sau bài học, bạn có thể:

- Chọn kiểu temporal phù hợp với ngày, giờ, thời điểm và thời lượng.
- Ánh xạ các kiểu `java.time` sang kiểu temporal của Neo4j.
- Truyền temporal parameter an toàn qua repository, template và driver.
- Viết truy vấn khoảng theo biên bao gồm/loại trừ rõ ràng.
- Tìm các sự kiện giao với một khoảng thời gian.
- Xử lý múi giờ, giờ mùa hè (DST) và ngày địa phương.
- Dùng `DURATION` cho thời lượng lịch hoặc thời gian đã trôi qua.
- Tạo range index và kiểm tra kế hoạch truy vấn thời gian.

## 1. Chọn đúng kiểu dữ liệu trước khi viết truy vấn

Neo4j hỗ trợ năm kiểu biểu diễn temporal instant và một kiểu biểu diễn lượng thời gian:

| Kiểu Cypher | Ý nghĩa | Kiểu Java thường dùng |
|---|---|---|
| `DATE` | Ngày lịch, không có giờ hoặc múi giờ | `LocalDate` |
| `LOCAL TIME` | Giờ trong ngày, không có ngày và múi giờ | `LocalTime` |
| `ZONED TIME` | Giờ trong ngày kèm offset múi giờ | `OffsetTime` |
| `LOCAL DATETIME` | Ngày và giờ địa phương, không có múi giờ | `LocalDateTime` |
| `ZONED DATETIME` | Một thời điểm có ngày, giờ và múi giờ | `ZonedDateTime` |
| `DURATION` | Lượng thời gian giữa hai mốc hoặc lượng thời gian để cộng/trừ | `Duration`, `Period` hoặc `IsoDuration` |

Chọn theo ý nghĩa nghiệp vụ:

- Ngày sinh, ngày giao hàng dự kiến hoặc ngày nghỉ: dùng `LocalDate`/`DATE`.
- Giờ mở cửa hằng ngày: dùng `LocalTime`/`LOCAL TIME`; nếu quy tắc phụ thuộc vùng địa lý, lưu thêm `ZoneId`.
- Thời điểm một đơn hàng được tạo: dùng `ZonedDateTime` hoặc `Instant` theo quy ước UTC.
- Lịch hẹn lúc 09:00 tại một thành phố: dùng kiểu có múi giờ hoặc lưu ngày/giờ địa phương cùng mã vùng thời gian.
- Thời gian xử lý 90 phút: dùng `Duration` hoặc `DURATION`.

Không dùng `LocalDateTime` để biểu diễn một thời điểm toàn cầu nếu hệ thống có người dùng ở nhiều múi giờ. Ví dụ `2026-11-27T09:00` không xác định duy nhất một thời điểm nếu thiếu thông tin múi giờ.

## 2. Múi giờ và cách Neo4j lưu temporal instant

Với `ZONED DATETIME`, Neo4j nhận thời điểm cùng offset hoặc tên múi giờ. Tên vùng như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin` dựa trên cơ sở dữ liệu múi giờ IANA. Neo4j lưu thời điểm theo UTC nội bộ và áp dụng múi giờ khi biểu diễn giá trị.

Điều này giúp so sánh hai thời điểm theo thứ tự thời gian thực tế, kể cả khi chúng được nhập ở các múi giờ khác nhau. Hai giá trị cùng một instant UTC nhưng mang timezone khác nhau không được xem là bằng nhau; timezone vẫn được giữ lại để biểu diễn và phân biệt giá trị.

Ví dụ:

~~~cypher
RETURN
    datetime('2026-11-27T09:00:00+07:00') AS hcmTime,
    datetime('2026-11-27T02:00:00Z') AS utcTime
~~~

Hai giá trị trên biểu diễn cùng một thời điểm. Khi hiển thị, giá trị có thể giữ offset hoặc tên vùng thời gian được cung cấp.

### Dùng tên múi giờ IANA cho lịch hẹn

Offset cố định như `+07:00` đủ để biểu diễn một thời điểm đã xác định. Nhưng khi tính lịch trong tương lai ở vùng có DST, nên dùng tên vùng IANA thay vì viết cứng offset:

~~~cypher
RETURN datetime({
    year: 2026,
    month: 11,
    day: 27,
    hour: 9,
    minute: 0,
    timezone: 'Europe/Berlin'
}) AS appointmentTime
~~~

Tên vùng cho phép áp dụng quy tắc DST theo ngày cụ thể. Quy tắc múi giờ có thể được cập nhật trong cơ sở dữ liệu IANA; khi quy tắc thay đổi, cách hiển thị giờ địa phương trong tương lai có thể thay đổi trong khi instant UTC đã lưu vẫn giữ nguyên.

Nếu gọi các hàm temporal mà không truyền timezone, Neo4j dùng timezone mặc định của database, có thể cấu hình bằng `db.temporal.timezone`. Để kết quả không phụ thuộc cấu hình môi trường, hãy truyền timezone rõ ràng khi tạo thời điểm nghiệp vụ.

Nếu nghiệp vụ cần bảo toàn cả ý định lịch ban đầu, ví dụ lịch hẹn được tạo lúc 09:00 theo giờ địa phương, có thể lưu thêm `localDateTime` và `zoneId` bên cạnh `startsAt` kiểu `ZONED DATETIME`. Điều này hữu ích khi phải giải thích hoặc tái tính lịch sau khi quy tắc vùng thời gian thay đổi.

### Local time không phải instant

`LOCAL TIME` chỉ có giờ, phút, giây và phần lẻ giây; nó không có ngày. `ZONED TIME` có thêm offset nhưng vẫn không có ngày. Hai kiểu này phù hợp với giờ trong ngày, chẳng hạn giờ mở cửa hoặc thời điểm lặp lại mỗi ngày. Chúng không đủ để xác định một thời điểm tuyệt đối khi cần sắp xếp sự kiện qua nhiều ngày.

## 3. Ánh xạ Java Time với Spring Data Neo4j

SDN hỗ trợ chuyển đổi sẵn nhiều kiểu Java temporal sang kiểu Cypher:

| Kiểu Java | Kiểu Cypher | Ánh xạ native của Driver |
|---|---|---|
| `LocalDate` | `DATE` | Có |
| `LocalTime` | `LOCAL TIME` | Có |
| `OffsetTime` | `ZONED TIME` | Có |
| `LocalDateTime` | `LOCAL DATETIME` | Có |
| `ZonedDateTime` | `ZONED DATETIME` | Có |
| `OffsetDateTime` | `ZONED DATETIME` | Có |
| `Instant` | `ZONED DATETIME` | Qua converter của SDN |
| `Period` | `DURATION` | Có điều kiện: không có giây/nano giây |
| `Duration` | `DURATION` | Có điều kiện: không có tháng/ngày |

Neo4j Java Driver nhận trực tiếp các kiểu temporal Java được hỗ trợ khi truyền query parameter. Trong đó, `ZonedDateTime` và `OffsetDateTime` là kiểu Java cho `ZONED DATETIME`. `Instant` không có múi giờ riêng để Driver ánh xạ native; SDN cung cấp converter cho kiểu này. Driver cũng hỗ trợ `Period` khi duration chỉ có thành phần lịch và `Duration` khi duration chỉ có thành phần giây/nano giây. SDN có converter riêng cho cả hai kiểu này.

Khi đọc kết quả trực tiếp bằng Driver, giá trị được bọc trong `Value`. Có thể dùng `asLocalDate()`, `asZonedDateTime()`, `asLocalDateTime()` hoặc phương thức tương ứng để lấy kiểu Java.

### Instant và ZonedDateTime nên dùng khi nào?

- Dùng `Instant` khi nghiệp vụ chỉ cần một mốc UTC tuyệt đối, ví dụ thời điểm log hoặc thời điểm thanh toán. SDN chuyển đổi nó sang `ZONED DATETIME` theo quy ước UTC.
- Dùng `ZonedDateTime` khi cần giữ cả instant và vùng thời gian, ví dụ lịch hẹn ở một địa điểm cụ thể.
- Dùng `LocalDateTime` khi giá trị thực sự là ngày/giờ trên đồng hồ địa phương và múi giờ được quản lý riêng.

Đối với mã dùng Neo4j Java Driver trực tiếp, nếu có `Instant` hãy chuyển nó sang `ZonedDateTime` ở UTC hoặc `OffsetDateTime` ở UTC trước khi bind parameter.

### Period và Duration trong Java

`Period` biểu diễn khoảng thời gian theo lịch như năm, tháng và ngày. `Duration` biểu diễn lượng thời gian theo giây và nano giây. Ví dụ:

~~~java
Period oneCalendarMonth = Period.ofMonths(1);
Period oneCalendarDay = Period.ofDays(1);

Duration ninetyMinutes = Duration.ofMinutes(90);
Duration twentyFourHours = Duration.ofHours(24);
~~~

Neo4j `DURATION` có các thành phần tháng, ngày, giây và nano giây. Khi dùng Driver trực tiếp, `Period` được hỗ trợ nếu không có thành phần giây/nano giây; `Duration` được hỗ trợ nếu không có thành phần tháng/ngày. Nếu cần một duration kết hợp các nhóm thành phần, dùng `org.neo4j.driver.types.IsoDuration`.

SDN có converter cho cả `Period` và `Duration` sang `DURATION`. Hãy chọn kiểu Java theo ý nghĩa nghiệp vụ, tránh coi một tháng lịch luôn bằng 30 ngày hoặc một ngày lịch luôn bằng đúng 24 giờ.

## 4. Mô hình entity có ngày và thời điểm

Ví dụ hệ thống quản lý lịch hẹn. Mỗi lịch có ngày dịch vụ, thời điểm bắt đầu và kết thúc:

~~~java
package com.acme.graph.domain;

import java.time.LocalDate;
import java.time.ZonedDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Appointment")
public class Appointment {

    @Id
    @GeneratedValue
    private Long id;

    private String appointmentCode;
    private LocalDate serviceDate;
    private ZonedDateTime startsAt;
    private ZonedDateTime endsAt;

    public Long getId() {
        return id;
    }

    public String getAppointmentCode() {
        return appointmentCode;
    }

    public LocalDate getServiceDate() {
        return serviceDate;
    }

    public ZonedDateTime getStartsAt() {
        return startsAt;
    }

    public ZonedDateTime getEndsAt() {
        return endsAt;
    }
}
~~~

`serviceDate` phù hợp để lọc ngày nghiệp vụ. `startsAt` và `endsAt` xác định thời điểm thực tế có timezone. Lưu cả ngày dịch vụ và thời điểm bắt đầu có thể là dư thừa về mặt thông tin, nhưng hữu ích nếu ngày nghiệp vụ khác với ngày UTC hoặc cần truy vấn báo cáo theo lịch địa phương.

## 5. Truy vấn theo ngày bằng DATE

Nếu property lưu kiểu `LocalDate`/`DATE`, truy vấn theo ngày rất trực tiếp:

~~~java
import java.time.LocalDate;
import java.time.ZonedDateTime;
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface AppointmentRepository
        extends Neo4jRepository<Appointment, Long> {

    @Query("""
        MATCH (a:Appointment)
        WHERE a.serviceDate = $serviceDate
        RETURN a
        ORDER BY a.startsAt
        """)
    List<Appointment> findForServiceDate(
        @Param("serviceDate") LocalDate serviceDate
    );
}
~~~

Tham số `LocalDate` được Driver/SDN chuyển thành Cypher `DATE`. Không cần chuyển ngày thành chuỗi rồi ghép vào câu Cypher.

Nếu cần tìm một dải ngày, dùng hai tham số ngày cùng kiểu:

~~~cypher
MATCH (a:Appointment)
WHERE a.serviceDate >= $fromDate
  AND a.serviceDate < $untilDate
RETURN a
ORDER BY a.serviceDate, a.startsAt
~~~

Ví dụ khoảng từ ngày 1 đến trước ngày 8 bao gồm các ngày 1–7. Cách viết này tránh phải tính ngày cuối cùng theo độ chính xác của thời gian.

## 6. Truy vấn thời điểm bằng khoảng nửa mở

Với property kiểu `ZONED DATETIME`, nên biểu diễn khoảng bằng hai biên:

- `fromInclusive`: biên đầu được tính vào kết quả.
- `untilExclusive`: biên cuối không được tính vào kết quả.

Khoảng này thường được viết là `[from, until)`. Một sự kiện đúng tại thời điểm kết thúc sẽ thuộc khoảng tiếp theo, không bị tính hai lần ở hai truy vấn liền nhau.

Phương thức trong `AppointmentRepository`:

~~~java
@Query("""
    MATCH (a:Appointment)
    WHERE a.startsAt >= $fromInclusive
      AND a.startsAt < $untilExclusive
    RETURN a
    ORDER BY a.startsAt
    """)
List<Appointment> findStartingInRange(
    @Param("fromInclusive") ZonedDateTime fromInclusive,
    @Param("untilExclusive") ZonedDateTime untilExclusive
);
~~~

Service gọi repository với hai mốc cùng kiểu:

~~~java
ZonedDateTime from = ZonedDateTime.parse(
    "2026-11-27T00:00:00+07:00[Asia/Ho_Chi_Minh]"
);
ZonedDateTime until = ZonedDateTime.parse(
    "2026-11-28T00:00:00+07:00[Asia/Ho_Chi_Minh]"
);

List<Appointment> appointments =
    appointmentRepository.findStartingInRange(from, until);
~~~

Không nên viết `a.startsAt >= $from AND a.startsAt <= $until` nếu hai khoảng liên tiếp có chung biên. Biên trên loại trừ giúp tránh một sự kiện tại đúng nửa đêm bị trả về ở cả ngày hôm trước và ngày hôm sau.

### Tìm mọi sự kiện trong một ngày địa phương

Nếu người dùng chọn một ngày tại vùng thời gian cụ thể, hãy tạo đầu ngày và đầu ngày kế tiếp trong chính vùng đó:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDate day = LocalDate.of(2026, 11, 27);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime from = day.atStartOfDay(zone);
ZonedDateTime until = day.plusDays(1).atStartOfDay(zone);

List<Appointment> appointments =
    appointmentRepository.findStartingInRange(from, until);
~~~

Hãy dùng `plusDays(1).atStartOfDay(zone)` thay vì cộng cứng 24 giờ. Ở vùng có DST, một ngày địa phương có thể dài 23 hoặc 25 giờ. Cách tạo biên theo lịch bảo đảm truy vấn phản ánh đúng ngày địa phương mà người dùng chọn.

## 7. Tìm các khoảng thời gian giao nhau

Một lịch hẹn hoặc đặt phòng thường chiếm một khoảng `[startsAt, endsAt)`. Để tìm tất cả lịch giao với khoảng yêu cầu `[requestedFrom, requestedUntil)`, dùng điều kiện:

~~~cypher
MATCH (a:Appointment)
WHERE a.startsAt < $requestedUntil
  AND a.endsAt > $requestedFrom
RETURN a
ORDER BY a.startsAt
~~~

Điều kiện này loại trừ hai trường hợp không giao nhau:

- Lịch kết thúc đúng lúc khoảng yêu cầu bắt đầu.
- Lịch bắt đầu đúng lúc khoảng yêu cầu kết thúc.

Ví dụ lịch A từ 09:00 đến 10:00 và lịch B từ 10:00 đến 11:00 không bị xem là chồng lấn nếu dùng khoảng nửa mở. Đây là quy ước hữu ích cho đặt phòng, đặt lịch và phân ca.

Có thể dùng cùng truy vấn trong repository:

~~~java
// Thêm vào AppointmentRepository.
@Query("""
    MATCH (a:Appointment)
    WHERE a.startsAt < $requestedUntil
      AND a.endsAt > $requestedFrom
    RETURN a
    ORDER BY a.startsAt
    """)
List<Appointment> findOverlapping(
    @Param("requestedFrom") ZonedDateTime requestedFrom,
    @Param("requestedUntil") ZonedDateTime requestedUntil
);
~~~

Trước khi truy vấn, service nên kiểm tra `requestedFrom.isBefore(requestedUntil)`. Khoảng rỗng hoặc đảo ngược thường là lỗi đầu vào nghiệp vụ.

## 8. Truyền temporal parameter bằng Neo4jTemplate và Neo4jClient

Các kiểu Java Time có thể được truyền trực tiếp qua map tham số của `Neo4jTemplate`:

~~~java
import java.util.List;
import java.util.Map;

Map<String, Object> parameters = Map.of(
    "from", fromInclusive,
    "until", untilExclusive
);

List<Appointment> results = neo4jTemplate.findAll(
    """
    MATCH (a:Appointment)
    WHERE a.startsAt >= $from
      AND a.startsAt < $until
    RETURN a
    ORDER BY a.startsAt
    """,
    parameters,
    Appointment.class
);
~~~

Với `Neo4jClient`, bind cùng các kiểu temporal:

~~~java
import java.time.ZonedDateTime;
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

record AppointmentSummary(String code, ZonedDateTime startsAt) {}

@Service
public class AppointmentQueryService {

    private final Neo4jClient neo4jClient;

    public AppointmentQueryService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<AppointmentSummary> findBetween(
            ZonedDateTime fromInclusive,
            ZonedDateTime untilExclusive) {

        return neo4jClient.query("""
                MATCH (a:Appointment)
                WHERE a.startsAt >= $from
                  AND a.startsAt < $until
                RETURN a.appointmentCode AS code,
                       a.startsAt AS startsAt
                ORDER BY startsAt
                """)
            .bind(fromInclusive).to("from")
            .bind(untilExclusive).to("until")
            .fetchAs(AppointmentSummary.class)
            .mappedBy((typeSystem, record) ->
                new AppointmentSummary(
                    record.get("code").asString(),
                    record.get("startsAt").asZonedDateTime()
                )
            )
            .all();
    }
}
~~~

Tham số temporal phải có kiểu tương thích với property đang so sánh. Ví dụ, property `serviceDate` là `DATE` thì dùng `LocalDate`; property `startsAt` là `ZONED DATETIME` thì dùng `ZonedDateTime` hoặc kiểu được SDN converter hỗ trợ tương ứng.

## 9. Dùng DURATION để tính thời lượng

`DURATION` biểu diễn lượng thời gian, không phải thời điểm bắt đầu hay kết thúc. Có thể tạo duration bằng chuỗi ISO-8601:

~~~cypher
RETURN
    duration('PT90M') AS ninetyMinutes,
    duration('P1M') AS oneCalendarMonth,
    duration('P1D') AS oneCalendarDay
~~~

Các tiền tố quan trọng:

| Ký hiệu | Ý nghĩa |
|---|---|
| `P` | Bắt đầu một duration |
| `Y` | Năm |
| `M` trước `T` | Tháng |
| `W` | Tuần |
| `D` | Ngày |
| `T` | Bắt đầu phần thời gian |
| `H` | Giờ |
| `M` sau `T` | Phút |
| `S` | Giây |

Ví dụ:

- `P1M`: một tháng lịch.
- `P7D`: bảy ngày lịch.
- `PT24H`: hai mươi bốn giờ.
- `PT90M`: chín mươi phút.
- `P1DT2H30M`: một ngày, hai giờ và ba mươi phút.

### Cộng duration vào temporal instant

~~~cypher
WITH datetime('2026-11-27T09:00:00+07:00') AS startsAt
RETURN
    startsAt + duration('PT90M') AS endsAt
~~~

Có thể dùng duration tham số:

~~~cypher
MATCH (a:Appointment {appointmentCode: $code})
RETURN a.startsAt + $duration AS estimatedEnd
~~~

Trong Java, `Duration.ofMinutes(90)` phù hợp với thời lượng 90 phút. Nếu cần cộng một tháng lịch, dùng `Period.ofMonths(1)` để giữ ngữ nghĩa lịch.

### Tính chênh lệch giữa hai thời điểm

Cypher cung cấp `duration.between(from, to)` để tính duration theo các thành phần lịch:

~~~cypher
MATCH (a:Appointment {appointmentCode: $code})
RETURN duration.between(a.startsAt, a.endsAt) AS elapsed
~~~

Nếu cần số giây nguyên chênh lệch, dùng `duration.inSeconds(from, to)` và đọc thành phần `seconds`:

~~~cypher
MATCH (a:Appointment {appointmentCode: $code})
RETURN duration.inSeconds(a.startsAt, a.endsAt).seconds AS elapsedSeconds
~~~

Nếu cần độ chính xác dưới một giây, đọc thêm thành phần `nanoseconds` và cộng phần đó theo đơn vị giây. Các hàm `duration.inDays` và `duration.inMonths` bỏ qua phần chênh lệch nhỏ hơn một đơn vị nguyên tương ứng. Vì vậy, hãy chọn hàm theo ý nghĩa báo cáo: số giây thực tế, số ngày lịch hay số tháng lịch.

Không so sánh trực tiếp hai `DURATION` bằng toán tử `<` hoặc `>` để quyết định duration nào dài hơn. Tháng và năm có độ dài thay đổi; Cypher không xác định một thứ tự tổng quát cho hai duration và phép so sánh có thể trả `null`. Nếu nghiệp vụ cần so sánh thời gian đã trôi qua, hãy chuẩn hóa về giây/nano giây hoặc so sánh hai instant trên cùng quy ước.

## 10. Phân biệt thời gian đã trôi qua và thời gian lịch

Một ngày lịch không phải lúc nào cũng tương đương 24 giờ thực tế. Khi DST bắt đầu hoặc kết thúc, đồng hồ địa phương có thể nhảy tiến hoặc lùi.

Trong Java:

- `ZonedDateTime.plusDays(1)` tăng một ngày theo lịch tại vùng thời gian.
- `ZonedDateTime.plusHours(24)` cộng 24 giờ đã trôi qua.
- `LocalDate.plusDays(1)` tăng ngày lịch mà không xét timezone.
- `Duration.ofHours(24)` biểu diễn 24 giờ.
- `Period.ofDays(1)` biểu diễn một ngày theo lịch.

Với lịch làm việc, ngày nghỉ hoặc lịch hẹn định kỳ, ưu tiên phép toán theo lịch và timezone. Với timeout, thời gian xử lý hoặc thời gian thuê tính theo số giây, ưu tiên duration theo thời gian đã trôi qua.

## 11. Tối ưu truy vấn temporal bằng range index

Neo4j hỗ trợ index cho các temporal value. Index trên temporal instant hỗ trợ lookup chính xác và range lookup. Ví dụ tạo range index cho thời điểm bắt đầu lịch hẹn:

~~~cypher
CREATE RANGE INDEX appointment_starts_at IF NOT EXISTS
FOR (a:Appointment)
ON (a.startsAt)
~~~

Truy vấn dạng:

~~~cypher
MATCH (a:Appointment)
WHERE a.startsAt >= $from
  AND a.startsAt < $until
RETURN a
ORDER BY a.startsAt
~~~

có thể tận dụng index để tìm các lịch trong khoảng thời gian.

Hạn chế biến đổi property được index ngay trong điều kiện lọc:

~~~cypher
// Nên tránh khi cần range index trên a.startsAt.
MATCH (a:Appointment)
WHERE date(a.startsAt) = $serviceDate
RETURN a
~~~

Thay vào đó, tính hai biên thời gian ở Java rồi truyền vào truy vấn range. Cách này giữ property ở dạng trực tiếp trong predicate:

~~~cypher
MATCH (a:Appointment)
WHERE a.startsAt >= $from
  AND a.startsAt < $until
RETURN a
~~~

Sau khi tạo index, dùng `EXPLAIN` để xem kế hoạch và `PROFILE` trên dữ liệu đại diện để xác nhận operator, số dòng và database hits. Index không bảo đảm truy vấn luôn nhanh nếu điều kiện lọc không chọn lọc hoặc truy vấn phải mở rộng quá nhiều relationship.

## 12. Tham số hóa và kiểm tra kiểu dữ liệu

Luôn truyền temporal value qua parameter:

~~~java
Map<String, Object> parameters = Map.of(
    "serviceDate", LocalDate.of(2026, 11, 27)
);
~~~

Tránh ghép chuỗi ngày giờ trực tiếp vào Cypher:

~~~java
// Không nên: dữ liệu đầu vào được nối vào câu query.
String cypher =
    "MATCH (a:Appointment) WHERE a.startsAt >= datetime('" + input + "') RETURN a";
~~~

Parameter giúp Driver gửi đúng kiểu dữ liệu và tách giá trị khỏi cấu trúc truy vấn. Nếu nhận ngày giờ từ HTTP request dưới dạng chuỗi, hãy parse và validate ở tầng biên ứng dụng:

~~~java
ZonedDateTime startsAt = ZonedDateTime.parse(input);
~~~

Nếu chuỗi đầu vào không có offset hoặc zone nhưng nghiệp vụ yêu cầu một instant, cần yêu cầu client gửi timezone hoặc áp dụng timezone nghiệp vụ đã xác định. Không tự dùng timezone mặc định của máy chủ mà không có quy ước.

Khi so sánh temporal instant, hãy giữ hai vế cùng kiểu Cypher, ví dụ `ZONED DATETIME` với `ZONED DATETIME` hoặc `DATE` với `DATE`. Cypher không tự diễn giải một `DATE` là đầu ngày của một `ZONED DATETIME`; hãy tạo biên thời gian rõ ràng trong ứng dụng.

Có thể kiểm tra kiểu property bằng Cypher:

~~~cypher
MATCH (a:Appointment)
RETURN valueType(a.startsAt) AS startsAtType,
       valueType(a.serviceDate) AS serviceDateType
LIMIT 5
~~~

Điều này giúp phát hiện dữ liệu cũ đã bị ghi dưới dạng STRING thay vì temporal native.

## 13. Những lỗi thường gặp

**Dùng STRING cho ngày giờ.** Chuỗi ISO có thể sắp xếp đúng trong một số trường hợp, nhưng thiếu kiểu temporal native, timezone semantics và toán tử temporal. Hãy dùng `DATE`, `LOCAL DATETIME` hoặc `ZONED DATETIME`.

**Dùng LocalDateTime cho thời điểm toàn cầu.** `LocalDateTime` không có timezone nên có thể mơ hồ khi dữ liệu đến từ nhiều vùng. Dùng `ZonedDateTime` hoặc `Instant` theo quy ước UTC.

**Nhầm Duration với thời điểm.** Duration là lượng thời gian, không có mốc bắt đầu/kết thúc. Lưu start/end bằng temporal instant và dùng duration để tính chênh lệch.

**Cộng 24 giờ để lấy ngày tiếp theo ở mọi timezone.** DST có thể làm một ngày dài 23 hoặc 25 giờ. Tính đầu ngày kế tiếp bằng `date.plusDays(1).atStartOfDay(zone)`.

**Dùng biên trên bao gồm cho hai khoảng liền nhau.** Điều kiện `<= until` có thể khiến sự kiện ở đúng ranh giới xuất hiện hai lần. Dùng khoảng nửa mở `[from, until)`.

**So sánh duration trực tiếp.** Cypher không có thứ tự tổng quát cho hai duration vì tháng và năm có độ dài khác nhau. Chuẩn hóa theo đơn vị nghiệp vụ trước khi so sánh.

**Dùng kiểu Java không khớp property.** So sánh `LocalDate` với `ZONED DATETIME` không tự biến thành truy vấn ngày mong muốn. Dùng tham số có kiểu tương ứng với property.

**Bọc property trong hàm khi lọc range.** `date(a.startsAt)` có thể làm planner không sử dụng range index trên `startsAt` như mong đợi. Tính biên ở Java rồi lọc trực tiếp property.

**Quên phần nano giây.** Temporal values và Java Time hỗ trợ độ chính xác nano giây. Không giả định dữ liệu chỉ có millisecond khi so sánh hoặc kiểm thử biên.

## 14. Tự kiểm tra

1. `DATE`, `LOCAL DATETIME` và `ZONED DATETIME` khác nhau như thế nào?
2. Vì sao `LocalDateTime` không đủ để biểu diễn một thời điểm toàn cầu?
3. Neo4j xử lý timezone và UTC nội bộ như thế nào?
4. SDN ánh xạ `LocalDate`, `ZonedDateTime`, `Instant`, `Period` và `Duration` sang kiểu Cypher nào?
5. Vì sao nên dùng khoảng nửa mở `[from, until)` cho truy vấn thời gian?
6. Điều kiện Cypher nào tìm các lịch hẹn giao với một khoảng yêu cầu?
7. `Period.ofDays(1)` khác `Duration.ofHours(24)` như thế nào khi xử lý DST?
8. Vì sao không nên so sánh trực tiếp hai `DURATION` bằng `<` hoặc `>`?
9. Range index hỗ trợ truy vấn temporal nào?
10. Vì sao nên tính biên thời gian trong Java thay vì gọi `date()` trên property ở điều kiện lọc?

**Bài tập thực hành:** Tạo entity `Appointment` với `serviceDate: LocalDate`, `startsAt: ZonedDateTime` và `endsAt: ZonedDateTime`. Viết repository tìm lịch bắt đầu trong một ngày, dùng khoảng `[from, until)` và tạo biên ngày theo `ZoneId` được truyền vào. Viết thêm truy vấn tìm lịch chồng lấn một khoảng đặt mới. Tạo range index trên `startsAt`, dùng `EXPLAIN`/`PROFILE` để kiểm tra. Cuối cùng, tính thời lượng lịch bằng `duration.between()` và số giây bằng `duration.inSeconds()`, rồi kiểm thử trường hợp qua ngày có DST để phân biệt ngày lịch với 24 giờ đã trôi qua.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Temporal values and time zones](https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/)
- [Neo4j Cypher Manual — Temporal functions](https://neo4j.com/docs/cypher-manual/current/functions/temporal/)
- [Neo4j Cypher Manual — Duration functions](https://neo4j.com/docs/cypher-manual/current/functions/temporal/duration/)
- [Neo4j Cypher Manual — Temporal operators](https://neo4j.com/docs/cypher-manual/current/expressions/temporal-operators/)
- [Neo4j Cypher Manual — Equality, ordering and comparison](https://neo4j.com/docs/cypher-manual/current/values-and-types/ordering-equality-comparison/)
- [Neo4j Cypher Manual — Indexes and temporal range lookups](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Java Driver Manual — Data types and mapping to Cypher types](https://neo4j.com/docs/java-manual/current/data-types/)
- [Spring Data Neo4j — Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
