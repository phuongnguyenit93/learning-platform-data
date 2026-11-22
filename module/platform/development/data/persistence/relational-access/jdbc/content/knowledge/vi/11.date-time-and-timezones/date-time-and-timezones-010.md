# Kiểm thử thời điểm chuyển giờ mùa hè và ranh giới ngày trong JDBC

Một ứng dụng đặt lịch, quản lý đơn hàng hoặc ghi nhận giao dịch thường phải trả lời những câu hỏi tưởng như đơn giản: “Sự kiện này xảy ra lúc mấy giờ?”, “Những sự kiện nào thuộc ngày 10/03 của người dùng?” hay “Lịch hẹn lúc 01:30 có hợp lệ không?”. Câu trả lời có thể sai vào ngày **chuyển giờ mùa hè (Daylight Saving Time – DST)** hoặc khi chuyển đổi giữa các múi giờ.

Trong chương **Ngày giờ và múi giờ** của **JDBC**, bài này tập trung vào **cách thiết kế và kiểm thử** các phép chuyển đổi thời gian bằng Java `java.time`, cách tạo khoảng ngày chính xác cho truy vấn SQL tham số hóa bằng `PreparedStatement`, và cách kiểm chứng dữ liệu đọc lại bằng `ResultSet`. Mục tiêu là kiểm thử được cả trường hợp bình thường lẫn các thời điểm mà đồng hồ địa phương nhảy tới, quay lùi hoặc đổi sang ngày khác.

## 1. Phân biệt ba khái niệm trước khi viết test

| Khái niệm Java | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối trên trục thời gian UTC | `2024-11-03T05:30:00Z` |
| `LocalDateTime` | Ngày giờ trên đồng hồ địa phương, **chưa chỉ ra múi giờ** | `2024-11-03T01:30` |
| `ZonedDateTime` | Ngày giờ địa phương gắn với `ZoneId` và bộ quy tắc lịch sử của vùng | `2024-11-03T01:30-04:00[America/New_York]` |
| `OffsetDateTime` | Ngày giờ kèm độ lệch UTC tại một thời điểm | `2024-11-03T01:30-04:00` |
| `LocalDate` | Ngày lịch, không mang giờ hay múi giờ | `2024-11-03` |

**`ZoneId` và `ZoneOffset` không tương đương.** `America/New_York` là một vùng có quy tắc chuyển DST theo thời kỳ; `-05:00` chỉ là một độ lệch UTC cố định. Dùng `ZoneOffset.ofHours(-5)` để tính ranh giới ngày ở New York quanh tháng 3 hoặc tháng 11 sẽ bỏ qua thay đổi DST.

Một `Instant` có thể biểu diễn được duy nhất trên trục thời gian. Một `LocalDateTime` chỉ trở thành thời điểm tuyệt đối sau khi ứng dụng biết múi giờ và giải quyết trường hợp giờ địa phương bị **thiếu** hoặc **lặp lại**.

### Liên hệ với SQL và JDBC

| Dữ liệu nghiệp vụ | Kiểu Java nên cân nhắc | Kiểu SQL và lưu ý |
| --- | --- | --- |
| Ngày sinh/ngày lịch | `LocalDate` | `DATE`; bản thân không chứa múi giờ |
| Giờ trong ngày chưa gắn ngày và vùng | `LocalTime` | `TIME`; không xác định `Instant` |
| Ngày giờ địa phương, chưa gắn vùng | `LocalDateTime` | `TIMESTAMP` không có múi giờ; không tự động đại diện cho một `Instant` |
| Thời điểm xảy ra sự kiện | `Instant` ở tầng nghiệp vụ; `OffsetDateTime` UTC khi bind qua JDBC 4.2 | `TIMESTAMP WITH TIME ZONE` nếu hệ quản trị/driver hỗ trợ đúng quy ước |
| Lịch hẹn theo giờ địa phương của một địa điểm | `LocalDateTime` + `ZoneId` + chính sách xử lý DST | Có thể cần lưu riêng ngày giờ địa phương, mã vùng và lựa chọn offset, tùy nghiệp vụ |

**Không có một quy tắc lưu trữ áp dụng đồng nhất cho mọi cơ sở dữ liệu.** Kiểu `TIMESTAMP WITH TIME ZONE`, việc chuẩn hóa sang UTC và khả năng giữ lại offset/vùng có khác biệt theo hệ quản trị và JDBC driver. Chẳng hạn, kiểu cột mang chữ “time zone” không mặc nhiên lưu `ZoneId` như `America/New_York`. Nếu nghiệp vụ cần nhớ vùng giờ ban đầu, hãy lưu mã vùng trong cột riêng.

Các ví dụ JDBC bên dưới chọn hợp đồng rõ ràng: **sự kiện đã xảy ra được biểu diễn bằng `Instant`, cột `occurred_at` hỗ trợ `TIMESTAMP WITH TIME ZONE`, tham số được bind ở UTC**. Khi dùng hệ quản trị khác, hãy kiểm chứng mapping của driver thay vì giả định tất cả cách lưu đều như nhau.

## 2. DST làm thay đổi những thời điểm nào?

Nhiều khu vực trên thế giới điều chỉnh đồng hồ theo mùa; nhiều khu vực khác không áp dụng DST. Những ngày và quy tắc chuyển giờ cũng có thể thay đổi theo lịch sử hoặc chính sách nhà nước. Dùng `ZoneId` và dữ liệu múi giờ của JDK (**tzdb**) để tính toán, không tự mã hóa quy tắc “tháng 3 tăng một giờ, tháng 11 giảm một giờ” cho mọi nơi.

Để có ví dụ kiểm thử cụ thể, xét `America/New_York` trong năm **2024**:

### 2.1. Khi đồng hồ nhảy tới: giờ không tồn tại (gap)

Ngày **10/03/2024**, đồng hồ ở New York nhảy trực tiếp từ **01:59:59** lên **03:00:00**. Các giờ địa phương từ **02:00** đến trước **03:00** không tồn tại trong vùng giờ này.

| `Instant` UTC | Giờ tại New York | Nhận xét |
| --- | --- | --- |
| `2024-03-10T06:59:59Z` | `01:59:59-05:00` | Trước thời điểm đổi giờ |
| `2024-03-10T07:00:00Z` | `03:00:00-04:00` | Ngay sau thời điểm đổi giờ |
| Không có | `2024-03-10 02:30` | Giờ địa phương **không tồn tại** |

Không có `Instant` nào ánh xạ tới `2024-03-10T02:30` tại `America/New_York`.

Nếu giao diện cho người dùng đặt lịch đúng thời điểm này, hệ thống cần quy định **từ chối**, **yêu cầu chọn giờ khác**, hoặc **dịch theo quy tắc nghiệp vụ**. Không để Java tự điều chỉnh âm thầm khi nghiệp vụ cần kiểm tra tính hợp lệ nghiêm ngặt.

### 2.2. Khi đồng hồ quay lùi: giờ xuất hiện hai lần (overlap)

Ngày **03/11/2024**, đồng hồ New York quay từ **02:00** về **01:00**. Vì vậy `01:30` xảy ra **hai lần**:

| Giờ địa phương | Offset | `Instant` UTC |
| --- | --- | --- |
| `2024-11-03 01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03 01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

Hai sự kiện có thể có cùng nhãn giờ địa phương nhưng cách nhau 60 phút trên trục thời gian. Nếu lưu riêng `LocalDateTime` mà không có vùng và offset đã chọn, dữ liệu không đủ để phân biệt hai thời điểm.

### 2.3. Phát hiện gap/overlap bằng `ZoneRules`

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

ZoneId zone = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
List<ZoneOffset> gapOffsets = zone.getRules().getValidOffsets(gap);
// 0 offset: giờ địa phương không tồn tại

LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
List<ZoneOffset> overlapOffsets =
    zone.getRules().getValidOffsets(overlap);
// 2 offset: -04:00 và -05:00

LocalDateTime normal = LocalDateTime.of(2024, 2, 15, 10, 0);
List<ZoneOffset> normalOffsets =
    zone.getRules().getValidOffsets(normal);
// 1 offset: giờ địa phương được xác định duy nhất
```

Có thể dùng số lượng offset hợp lệ làm một bước xác thực:

- **0 offset:** gap; từ chối hoặc xử lý theo quy tắc đặt lịch.
- **1 offset:** thời điểm được xác định duy nhất từ ngày giờ địa phương và `ZoneId`.
- **2 offset:** overlap; cho người dùng chọn lần thứ nhất hay lần thứ hai, hoặc dùng chính sách được công bố rõ ràng.

```java
import java.time.*;
import java.util.List;

public static Instant resolveAppointment(
    LocalDateTime local,
    ZoneId zone,
    ZoneOffset selectedOffset
) {
    List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

    if (valid.isEmpty()) {
        throw new IllegalArgumentException(
            "Giờ địa phương không tồn tại trong múi giờ đã chọn"
        );
    }
    if (valid.size() > 1 && selectedOffset == null) {
        throw new IllegalArgumentException(
            "Giờ địa phương xuất hiện hai lần, cần chọn offset"
        );
    }

    ZoneOffset offset = selectedOffset;
    if (offset == null) {
        offset = valid.get(0); // Chỉ còn một offset hợp lệ.
    }
    if (!valid.contains(offset)) {
        throw new IllegalArgumentException(
            "Offset không hợp lệ với thời điểm và vùng giờ"
        );
    }
    return local.atOffset(offset).toInstant();
}
```

Đối với **sự kiện đã xảy ra**, thường nên ghi trực tiếp thời điểm tuyệt đối từ đồng hồ hoặc nguồn sự kiện. Đối với **lịch hẹn tương lai theo giờ địa phương**, cần lưu hoặc xử lý đủ thông tin về vùng giờ và chính sách DST. Hai loại nghiệp vụ có yêu cầu khác nhau.

## 3. Ranh giới của một ngày lịch không nhất thiết cách nhau 24 giờ

Giả sử người dùng muốn xem sự kiện của **ngày 10/03/2024 tại New York**. “Ngày” ở đây là ngày trên lịch của New York, không phải ngày UTC.

Khoảng tìm kiếm chuẩn là:

```text
[startInclusive, endExclusive)
= [đầu ngày địa phương, đầu ngày địa phương tiếp theo)
```

Với ngày trên:

```text
Đầu ngày 10/03 tại New York -> 2024-03-10T05:00:00Z
Đầu ngày 11/03 tại New York -> 2024-03-11T04:00:00Z
Khoảng cách thực tế: 23 giờ
```

Ngược lại, **ngày 03/11/2024 tại New York dài 25 giờ**:

```text
Đầu ngày 03/11 tại New York -> 2024-11-03T04:00:00Z
Đầu ngày 04/11 tại New York -> 2024-11-04T05:00:00Z
Khoảng cách thực tế: 25 giờ
```

<details>
<summary>Vì sao một ngày lịch có thể khác 24 giờ?</summary>

Một ngày địa phương là khoảng thời gian trong đó mọi thời điểm được hiển thị cùng một ngày bởi quy tắc múi giờ. Khi offset thay đổi giữa hai đầu ngày, độ dài tính bằng giây cũng thay đổi. Ở các vùng có chuyển đổi gần nửa đêm, thậm chí “00:00” có thể không tồn tại; `LocalDate.atStartOfDay(zone)` trả về thời điểm bắt đầu hợp lệ sớm nhất của ngày đó theo quy tắc Java. Một số trường hợp lịch sử còn có ngày địa phương bị bỏ qua hoàn toàn. Vì vậy phải tính ranh giới **hai đầu ngày riêng biệt**.

</details>

### 3.1. Hàm tạo khoảng ngày an toàn

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public final class DayBounds {
    private DayBounds() {}

    public record InstantRange(
        Instant startInclusive,
        Instant endExclusive
    ) {
        public boolean contains(Instant value) {
            return !value.isBefore(startInclusive)
                && value.isBefore(endExclusive);
        }
    }

    public static InstantRange of(LocalDate date, ZoneId zone) {
        Instant start = date.atStartOfDay(zone).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
        return new InstantRange(start, end);
    }
}
```

**Đúng:** tính `date.plusDays(1).atStartOfDay(zone)` rồi chuyển sang `Instant`.

**Sai trong ngày đổi DST:** lấy `start.plus(Duration.ofHours(24))`, vì phép cộng này giả định mọi ngày đều dài đúng 24 giờ.

**Tránh:** truy vấn `BETWEEN start AND end` khi `end` là đầu ngày kế tiếp, vì `BETWEEN` gồm cả hai đầu và có thể lấy nhầm bản ghi lúc **00:00 ngày sau**.

### 3.2. Múi giờ khác nhau cho ranh giới ngày khác nhau

Ví dụ, đầu ngày **01/01/2024 tại `Asia/Ho_Chi_Minh`** tương ứng:

```text
2024-01-01 00:00 +07:00
= 2023-12-31T17:00:00Z
```

Một thời điểm có thể thuộc ngày 31/12 tại một khu vực và ngày 01/01 tại khu vực khác. Do đó ứng dụng phải xác định rõ **ngày của ai, trong vùng giờ nào**: khách hàng, chi nhánh, địa điểm diễn ra sự kiện hay UTC. Không lấy `LocalDate.now()` theo múi giờ mặc định của server để thay cho ngày người dùng chọn.

## 4. Áp dụng ranh giới ngày vào truy vấn JDBC

Giả sử bảng `events` lưu thời điểm tuyệt đối của sự kiện ở cột `occurred_at`. Với hệ quản trị hỗ trợ `TIMESTAMP WITH TIME ZONE`, một lược đồ minh họa là:

```sql
CREATE TABLE events (
    id          BIGINT PRIMARY KEY,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    description VARCHAR(200)
);
```

Kiểu dữ liệu và cú pháp DDL thực tế có thể khác theo nhà cung cấp; cần kiểm chứng với driver sẽ sử dụng ở production.

Truy vấn các sự kiện thuộc **một ngày địa phương** dùng khoảng nửa mở:

```sql
SELECT id, occurred_at
FROM events
WHERE occurred_at >= ?
  AND occurred_at < ?
ORDER BY occurred_at, id;
```

Hai dấu `?` là **hai `Instant` biên đã chuyển sang UTC**, chứ không phải các chuỗi `2024-03-10 00:00` theo timezone mặc định.

Ví dụ repository hoàn chỉnh cho mục tiêu truy vấn danh sách ID bằng JDBC 4.2:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class EventRepository {
    private final DataSource dataSource;

    public EventRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public List<Long> findIdsOnDay(
        LocalDate localDate,
        ZoneId viewerZone
    ) throws SQLException {
        Objects.requireNonNull(localDate, "localDate");
        Objects.requireNonNull(viewerZone, "viewerZone");

        DayBounds.InstantRange bounds =
            DayBounds.of(localDate, viewerZone);

        String sql = """
            SELECT id, occurred_at
            FROM events
            WHERE occurred_at >= ? AND occurred_at < ?
            ORDER BY occurred_at, id
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setObject(
                1,
                bounds.startInclusive().atOffset(ZoneOffset.UTC),
                Types.TIMESTAMP_WITH_TIMEZONE
            );
            ps.setObject(
                2,
                bounds.endExclusive().atOffset(ZoneOffset.UTC),
                Types.TIMESTAMP_WITH_TIMEZONE
            );

            List<Long> ids = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("id"));
                }
            }
            return ids;
        }
    }
}
```

Ở đây `DataSource` cấp `Connection`; `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` kể cả khi có ngoại lệ. Đối với các trường hợp cần nhiều thao tác trong cùng một transaction, lớp gọi nên quản lý và truyền `Connection` thay vì để mỗi truy vấn tự mở kết nối.

Khi đọc thời điểm từ bảng, có thể dùng mapping `ResultSet.getObject(..., OffsetDateTime.class)` nếu driver hỗ trợ chuẩn này:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;

// Nằm bên trong vòng while (rs.next()):
OffsetDateTime stored = rs.getObject(
    "occurred_at",
    OffsetDateTime.class
);
Instant eventInstant = stored.toInstant();

ZoneId viewerZone = ZoneId.of("America/New_York");
String localDisplay = eventInstant.atZone(viewerZone).toString();
// Hiển thị theo vùng giờ do ứng dụng chọn.
```

`TIMESTAMP WITH TIME ZONE` và JDBC 4.2 hướng tới mapping với `OffsetDateTime`, nhưng mức hỗ trợ và cách chuẩn hóa giá trị phụ thuộc hệ quản trị và phiên bản driver. Không dựa vào offset nhận được từ `ResultSet` để suy ra vùng giờ ban đầu: nếu cần vùng giờ ban đầu, lưu `ZoneId` riêng. Kiểm thử vòng ghi–đọc trên **cùng loại cơ sở dữ liệu và driver sẽ triển khai**.

## 5. Viết unit test xác nhận các mốc DST

Ví dụ dùng **JUnit Jupiter (JUnit 5)** và các API `java.time`. Test Java không cần kết nối cơ sở dữ liệu; nó xác minh thuật toán xác định khoảng ngày và xử lý gap/overlap trước khi kiểm thử JDBC.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;
import org.junit.jupiter.api.Test;

class DayBoundsTest {
    private static final ZoneId NEW_YORK =
        ZoneId.of("America/New_York");

    @Test
    void springForwardCreatesNonexistentLocalTime() {
        LocalDateTime missing =
            LocalDateTime.of(2024, 3, 10, 2, 30);
        ZoneRules rules = NEW_YORK.getRules();

        assertTrue(rules.getValidOffsets(missing).isEmpty());
        assertTrue(rules.getTransition(missing).isGap());

        assertEquals(
            LocalDateTime.of(2024, 3, 10, 1, 59, 59),
            Instant.parse("2024-03-10T06:59:59Z")
                .atZone(NEW_YORK).toLocalDateTime()
        );
        assertEquals(
            LocalDateTime.of(2024, 3, 10, 3, 0),
            Instant.parse("2024-03-10T07:00:00Z")
                .atZone(NEW_YORK).toLocalDateTime()
        );
    }

    @Test
    void fallBackCreatesTwoDifferentInstants() {
        LocalDateTime repeated =
            LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> offsets =
            NEW_YORK.getRules().getValidOffsets(repeated);

        assertEquals(
            List.of(
                ZoneOffset.ofHours(-4),
                ZoneOffset.ofHours(-5)
            ),
            offsets
        );
        assertTrue(
            NEW_YORK.getRules().getTransition(repeated).isOverlap()
        );

        assertEquals(
            Instant.parse("2024-11-03T05:30:00Z"),
            repeated.atOffset(offsets.get(0)).toInstant()
        );
        assertEquals(
            Instant.parse("2024-11-03T06:30:00Z"),
            repeated.atOffset(offsets.get(1)).toInstant()
        );
    }

    @Test
    void springDayHasTwentyThreeHours() {
        DayBounds.InstantRange range = DayBounds.of(
            LocalDate.of(2024, 3, 10), NEW_YORK
        );

        assertEquals(
            Instant.parse("2024-03-10T05:00:00Z"),
            range.startInclusive()
        );
        assertEquals(
            Instant.parse("2024-03-11T04:00:00Z"),
            range.endExclusive()
        );
        assertEquals(
            Duration.ofHours(23),
            Duration.between(
                range.startInclusive(), range.endExclusive()
            )
        );
    }

    @Test
    void fallDayHasTwentyFiveHours() {
        DayBounds.InstantRange range = DayBounds.of(
            LocalDate.of(2024, 11, 3), NEW_YORK
        );

        assertEquals(
            Instant.parse("2024-11-03T04:00:00Z"),
            range.startInclusive()
        );
        assertEquals(
            Instant.parse("2024-11-04T05:00:00Z"),
            range.endExclusive()
        );
        assertEquals(
            Duration.ofHours(25),
            Duration.between(
                range.startInclusive(), range.endExclusive()
            )
        );

        // Cả hai lần xuất hiện của 01:30 đều thuộc cùng ngày.
        assertTrue(range.contains(
            Instant.parse("2024-11-03T05:30:00Z")
        ));
        assertTrue(range.contains(
            Instant.parse("2024-11-03T06:30:00Z")
        ));
    }

    @Test
    void rangeIncludesStartButExcludesNextDayStart() {
        DayBounds.InstantRange range = DayBounds.of(
            LocalDate.of(2024, 3, 10), NEW_YORK
        );

        assertFalse(range.contains(
            Instant.parse("2024-03-10T04:59:59Z")
        ));
        assertTrue(range.contains(
            Instant.parse("2024-03-10T05:00:00Z")
        ));
        assertTrue(range.contains(
            Instant.parse("2024-03-11T03:59:59Z")
        ));
        assertFalse(range.contains(
            Instant.parse("2024-03-11T04:00:00Z")
        ));
    }

    @Test
    void localMidnightCanBeOnPreviousUtcDate() {
        ZoneId hoChiMinh = ZoneId.of("Asia/Ho_Chi_Minh");
        DayBounds.InstantRange range = DayBounds.of(
            LocalDate.of(2024, 1, 1), hoChiMinh
        );

        assertEquals(
            Instant.parse("2023-12-31T17:00:00Z"),
            range.startInclusive()
        );
        assertEquals(
            Duration.ofHours(24),
            Duration.between(
                range.startInclusive(), range.endExclusive()
            )
        );
    }
}
```

Các mốc này được chọn từ **lịch chuyển DST năm 2024 của New York**; không khẳng định mọi năm hoặc mọi vùng giờ đều chuyển tại cùng mốc. Với bài toán lịch hẹn ở tương lai, kiểm thử thêm các năm nghiệp vụ sử dụng và cập nhật tzdb theo vòng đời sản phẩm.

### 5.1. Nếu ứng dụng tự lấy “hôm nay”

Các unit test không nên phụ thuộc múi giờ hoặc ngày giờ hiện tại trên máy chạy CI. Có thể tiêm `Clock`:

```java
Clock clock = Clock.fixed(
    Instant.parse("2024-03-10T06:59:59Z"),
    ZoneOffset.UTC
);

LocalDate todayInNewYork =
    LocalDate.now(clock.withZone(ZoneId.of("America/New_York")));
// 2024-03-10

LocalDate todayInTokyo =
    LocalDate.now(clock.withZone(ZoneId.of("Asia/Tokyo")));
// 2024-03-10
```

Test quan trọng hơn nằm ở các `Instant` sát nửa đêm, nơi hai vùng giờ cho **ngày khác nhau**. Ví dụ:

```java
Instant moment = Instant.parse("2024-01-01T00:30:00Z");

assertEquals(
    LocalDate.of(2023, 12, 31),
    moment.atZone(ZoneId.of("America/New_York")).toLocalDate()
);
assertEquals(
    LocalDate.of(2024, 1, 1),
    moment.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate()
);
```

Trong test có tham số múi giờ, nên truyền `ZoneId` tường minh. Tránh `ZoneId.systemDefault()`, `LocalDate.now()` không có `Clock`, hoặc phụ thuộc cấu hình máy phát triển.

## 6. Kiểm thử tích hợp JDBC với dữ liệu nằm sát ranh giới

Unit test mới xác minh hàm Java. Kiểm thử tích hợp cần xác minh cả **driver**, **mức chính xác timestamp**, **cấu hình session/connection**, **SQL so sánh** và **mapping kết quả**.

Dùng một cơ sở dữ liệu thử nghiệm có kiểu cột phù hợp với production; tạo `events` với các `Instant` fixture được bind bằng `OffsetDateTime` UTC:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Types;
import java.time.Instant;
import java.time.ZoneOffset;

// Ví dụ bên trong transaction thử nghiệm đã được chuẩn bị:
String insertSql =
    "INSERT INTO events (id, occurred_at) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setLong(1, 101L);
    ps.setObject(
        2,
        Instant.parse("2024-03-10T05:00:00Z")
            .atOffset(ZoneOffset.UTC),
        Types.TIMESTAMP_WITH_TIMEZONE
    );
    ps.executeUpdate();
}
```

Để tránh sai lệch do độ chính xác nano/micro giây khác nhau giữa các hệ quản trị, các fixture minh họa chọn **độ chính xác tới giây**. Đối với ứng dụng dùng độ chính xác cao hơn, cần kiểm thử thêm chính sách làm tròn/cắt phần thập phân khi ghi và đọc.

### 6.1. Bộ dữ liệu kiểm thử ngày DST bắt đầu

Với truy vấn ngày **10/03/2024** trong `America/New_York`, khoảng đúng là `[2024-03-10T05:00:00Z, 2024-03-11T04:00:00Z)`.

| ID fixture | Thời điểm lưu UTC | Có trong kết quả? | Giải thích |
| --- | --- | --- | --- |
| 100 | `2024-03-10T04:59:59Z` | Không | 1 giây trước khi ngày địa phương bắt đầu |
| 101 | `2024-03-10T05:00:00Z` | Có | Đúng đầu ngày, bao gồm biên trái |
| 102 | `2024-03-10T06:59:59Z` | Có | Ngay trước bước nhảy 02:00 → 03:00 |
| 103 | `2024-03-10T07:00:00Z` | Có | Ngay sau bước nhảy, không có thời điểm 02:xx |
| 104 | `2024-03-11T03:59:59Z` | Có | Giây cuối trước đầu ngày tiếp theo |
| 105 | `2024-03-11T04:00:00Z` | Không | Đúng đầu ngày tiếp theo, loại biên phải |

Khi gọi `EventRepository.findIdsOnDay(LocalDate.of(2024, 3, 10), ZoneId.of("America/New_York"))` với bảng chỉ chứa sáu fixture trên, kết quả dự kiến theo `ORDER BY` là **`[101, 102, 103, 104]`**.

### 6.2. Bộ dữ liệu kiểm thử ngày DST kết thúc

Với ngày **03/11/2024**, khoảng là `[2024-11-03T04:00:00Z, 2024-11-04T05:00:00Z)`.

| ID fixture | Thời điểm UTC | Có trong kết quả? | Giải thích |
| --- | --- | --- | --- |
| 200 | `2024-11-03T03:59:59Z` | Không | Thuộc ngày địa phương hôm trước |
| 201 | `2024-11-03T04:00:00Z` | Có | Đúng đầu ngày |
| 202 | `2024-11-03T05:30:00Z` | Có | Lần đầu của 01:30, offset -04:00 |
| 203 | `2024-11-03T06:30:00Z` | Có | Lần hai của 01:30, offset -05:00 |
| 204 | `2024-11-04T04:59:59Z` | Có | Ngay trước ngày tiếp theo |
| 205 | `2024-11-04T05:00:00Z` | Không | Đúng đầu ngày tiếp theo |

Kết quả dự kiến là **`[201, 202, 203, 204]`**. Đây là kiểm chứng quan trọng: hai bản ghi có nhãn giờ địa phương `01:30` đều phải xuất hiện một lần trong kết quả và đại diện cho **hai `Instant` khác nhau**.

Một luồng kiểm thử tích hợp có thể thực hiện:

1. Bắt đầu transaction dành riêng cho test, chèn fixture bằng `PreparedStatement` và `OffsetDateTime` UTC.
2. Gọi repository với đúng `LocalDate` và `ZoneId`, so sánh **ID thực tế** với danh sách mong đợi.
3. Đọc lại các giá trị `occurred_at`, chuyển `OffsetDateTime.toInstant()` và kiểm tra chúng giữ đúng `Instant` sau vòng ghi–đọc (trong giới hạn độ chính xác đã chọn).
4. Dọn fixture qua rollback hoặc cơ chế cleanup độc lập của test để các test không ảnh hưởng nhau.
5. Chạy trên môi trường giống production; nếu cơ sở dữ liệu cho phép thay timezone session, kiểm thử thêm ít nhất hai cấu hình session để phát hiện chuyển đổi ngầm.

**Lưu ý về transaction:** các câu lệnh chèn fixture và truy vấn cần nhìn thấy cùng dữ liệu, nhưng repository mẫu tự tạo `Connection`. Để rollback toàn bộ fixture và truy vấn trong một transaction, hãy cung cấp biến thể repository **nhận `Connection` từ test** hoặc dùng cơ chế quản lý transaction của test framework. Không mặc định rằng hai kết nối độc lập chia sẻ cùng một transaction hay nhìn thấy dữ liệu chưa commit.

## 7. Những lỗi thường chỉ xuất hiện trong production

### 7.1. Cộng đúng 24 giờ để tìm cuối ngày

```java
// Sai cho ngày có đổi offset:
Instant end = start.plus(Duration.ofDays(1));

// Đúng: lấy đầu ngày theo lịch, sau đó tính ra Instant:
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
```

Lỗi này thường làm **bỏ sót** một giờ ở ngày dài 25 giờ hoặc **lấy thừa** một giờ của ngày kế tiếp ở ngày dài 23 giờ.

### 7.2. Chuyển `LocalDateTime` sang `Instant` mà không kiểm tra DST

```java
LocalDateTime requested =
    LocalDateTime.of(2024, 3, 10, 2, 30);

ZonedDateTime adjusted =
    requested.atZone(ZoneId.of("America/New_York"));
// java.time có thể điều chỉnh giờ trong gap sang giờ hợp lệ;
// không đồng nghĩa người dùng đã chọn thời điểm đó.
```

Tương tự, trong overlap, `atZone(zone)` mặc định chọn một offset phù hợp (thường là offset sớm hơn theo tài liệu Java). Nếu bài toán cần phân biệt “lần đầu” và “lần hai”, hãy dùng `ZoneRules.getValidOffsets()` và yêu cầu lựa chọn rõ ràng.

### 7.3. Dùng độ lệch UTC cố định để thay vùng giờ

`-05:00` không thay thế được `America/New_York` cho cả năm. Với lịch hẹn tương lai, offset hiện tại cũng không nhất thiết là offset đúng tại ngày được chọn.

### 7.4. Dùng timezone mặc định của máy hoặc kết nối một cách ngầm định

Máy CI có thể chạy UTC trong khi laptop chạy `Asia/Ho_Chi_Minh`. Việc chuyển đổi qua `java.sql.Timestamp`, `getTimestamp()` hoặc các kiểu SQL không chứa timezone có thể phụ thuộc driver và cấu hình session. Quy định rõ quy tắc lưu, mapping và múi giờ hiển thị, rồi kiểm chứng trên driver đang dùng.

### 7.5. Dùng `DATE(occurred_at)` để lọc một ngày

```sql
-- Cần cẩn trọng: ngày tính theo timezone nào?
SELECT id FROM events
WHERE DATE(occurred_at) = ?;
```

Việc ép timestamp thành date có thể dùng múi giờ của session, không phải vùng giờ người dùng chọn; ngoài ra thường khiến chỉ mục trên `occurred_at` khó được tận dụng. Khoảng `occurred_at >= ? AND occurred_at < ?` với hai biên đã tính theo vùng phù hợp dễ kiểm chứng hơn và thường thân thiện với chỉ mục trên cột thời gian.

### 7.6. Lẫn thời gian tuyệt đối với lịch hẹn tương lai

Một giao dịch **đã diễn ra** thường có thể lưu bằng `Instant`. Một cuộc họp **lúc 09:00 mỗi thứ Hai ở New York** là quy tắc theo đồng hồ địa phương; nếu chỉ lưu một `Instant` ban đầu rồi cộng 7×24 giờ để sinh lần tiếp theo, giờ địa phương sẽ bị lệch sau lần đổi DST. Lịch lặp cần giữ quy tắc ngày/giờ địa phương và `ZoneId`, đồng thời xử lý các lần trùng/thiếu theo chính sách.

## 8. Ma trận kiểm thử đề xuất

| Nhóm kiểm thử | Đầu vào trọng tâm | Điều cần xác nhận |
| --- | --- | --- |
| Ngày bình thường | Một `LocalDate` tại vùng không đổi offset trong ngày | Khoảng tương ứng với ngày người dùng chọn |
| Gap | `2024-03-10T02:30` tại New York | Không có offset hợp lệ; chính sách từ chối/dịch giờ được áp dụng |
| Ngay trước/sau gap | `06:59:59Z`, `07:00:00Z` | Chuyển từ `01:59:59` sang `03:00` |
| Overlap | `2024-11-03T01:30` tại New York | Có hai offset và hai `Instant` khác nhau |
| Ngày DST bắt đầu | `2024-03-10` tại New York | Khoảng ngày dài 23 giờ |
| Ngày DST kết thúc | `2024-11-03` tại New York | Khoảng ngày dài 25 giờ |
| Nửa đêm | 1 giây trước, đúng biên, 1 giây sau | Biên trái được lấy, biên phải của ngày kế tiếp bị loại |
| Khác múi giờ | Cùng `Instant` ở New York và Hồ Chí Minh | Có thể thuộc hai `LocalDate` khác nhau |
| JDBC ghi–đọc | `OffsetDateTime` UTC, cùng `Instant` | Không bị dịch thời điểm do session, driver hoặc mapping |
| Độ chính xác DB | Timestamp có phần thập phân giây | Hành vi làm tròn/cắt được kiểm soát |
| Quy tắc múi giờ thay đổi | Ngày tương lai trên JDK/tzdb dùng thực tế | Quy trình cập nhật dữ liệu vùng giờ và test hồi quy phù hợp |

Có thể dùng parameterized tests để mở rộng ma trận này ra nhiều `ZoneId`. Tuy nhiên, đừng mặc định mọi vùng giờ đều đổi DST, hay mọi vùng có DST đều đổi vào 02:00. Các kiểm thử cần xuất phát từ những **quy tắc thời gian thật sự áp dụng cho vùng được chọn**.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao truy vấn sự kiện của ngày 10/03/2024 ở New York không nên đặt `end = start + 24h`?

**Đáp án:** vì ngày đó có DST bắt đầu, chỉ dài **23 giờ** theo thời gian tuyệt đối. Cần tính đầu ngày 11/03 theo `ZoneId` rồi chuyển thành `Instant`.

**Câu 2.** `2024-11-03T01:30` tại New York chỉ ra duy nhất một thời điểm không?

**Đáp án:** không. Có hai offset hợp lệ `-04:00` và `-05:00`, ứng với hai `Instant` khác nhau.

**Câu 3.** Vì sao `WHERE occurred_at >= ? AND occurred_at < ?` phù hợp hơn `BETWEEN` để lọc một ngày?

**Đáp án:** vì khoảng nửa mở gồm đầu ngày đang tìm nhưng **loại đầu ngày kế tiếp**. Cùng một bản ghi đúng nửa đêm sẽ không bị lấy vào hai ngày liền kề.

**Câu 4.** Một test chuyển đổi thời gian chạy đúng trên laptop nhưng sai trên CI. Cần xem xét gì đầu tiên?

**Đáp án:** múi giờ mặc định của JVM, `Clock` hệ thống, phiên bản quy tắc timezone, timezone session của cơ sở dữ liệu, cách JDBC driver ánh xạ timestamp và độ chính xác của cột.

**Câu 5.** Lưu `TIMESTAMP WITH TIME ZONE` có đảm bảo truy xuất lại `America/New_York` không?

**Đáp án:** không. Nhiều hệ quản trị chuẩn hóa hoặc lưu offset mà không giữ mã vùng IANA ban đầu. Nếu cần nhớ vùng giờ để diễn giải hoặc lập lịch theo quy tắc của vùng đó, hãy lưu `ZoneId` riêng.

## Tổng kết

Để kiểm thử ngày giờ trong ứng dụng JDBC đáng tin cậy, cần xác định ba điều trước khi viết SQL: **dữ liệu là thời điểm tuyệt đối hay giờ lịch địa phương, ngày được hiểu theo múi giờ nào, và chính sách xử lý DST là gì**. Dùng `Instant` cho sự kiện đã xảy ra, `ZoneId` để xác định ngày và quy tắc vùng giờ, `ZoneRules` để phát hiện gap/overlap, và khoảng **`[đầu ngày, đầu ngày tiếp theo)`** để lọc dữ liệu.

Sau unit test với các mốc DST và ranh giới ngày, hãy kiểm thử tích hợp với **JDBC driver và hệ quản trị thật**, nhất là thao tác bind `PreparedStatement`, đọc lại `ResultSet` và cấu hình timezone của connection. Nhờ đó hệ thống có thể trả kết quả đúng cả trong các ngày chỉ dài 23 giờ, dài 25 giờ và khi người dùng ở nhiều múi giờ khác nhau.
