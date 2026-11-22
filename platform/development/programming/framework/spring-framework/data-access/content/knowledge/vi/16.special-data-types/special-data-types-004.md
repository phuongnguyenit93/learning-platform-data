# Timestamp, offset, múi giờ và độ chính xác khi đọc ghi trong Spring JDBC

## 1. Vì sao lưu thời gian khó hơn lưu một con số?

Một thời điểm có thể được hiển thị bằng nhiều giờ địa phương khác nhau. Chẳng hạn, hai chuỗi sau chỉ **cùng một thời điểm**:

```text
2026-10-30T10:15:30.123456+07:00
2026-10-30T03:15:30.123456Z
```

Chênh lệch 7 giờ ở phần giờ hiển thị được bù bởi offset `+07:00` so với UTC (`Z`). Nhưng chuỗi `2026-10-30 10:15:30` không chứa offset, múi giờ hay quy tắc đổi giờ theo mùa, nên **không đủ để suy ra một thời điểm duy nhất trên trục UTC**.

Trong ứng dụng Spring JDBC, lỗi thời gian thường xuất hiện khi dữ liệu đi qua nhiều lớp:

```text
Client gửi ISO-8601
    ↓ parse
Java Instant / OffsetDateTime / LocalDateTime / ZonedDateTime
    ↓ PreparedStatement.setObject(...)
JDBC driver và connection/session timezone
    ↓
SQL TIMESTAMP / TIMESTAMP WITH TIME ZONE / DATETIME ...
    ↓
JDBC driver và conversion khi SELECT
    ↓ ResultSet.getObject(..., Class)
Java temporal type
    ↓ format với ZoneId của người dùng
JSON / UI / báo cáo
```

Mỗi lớp có thể làm thay đổi cách hiểu về offset, timezone hoặc số chữ số thập phân. Muốn đọc/ghi đúng, trước tiên phải xác định **ý nghĩa nghiệp vụ của dữ liệu thời gian**:

- **Thời điểm đã xảy ra (instant):** đơn hàng được tạo lúc nào, giao dịch ghi nhận lúc nào, token hết hạn lúc nào. Cần lưu một mốc so sánh được trên UTC.
- **Giờ trên đồng hồ địa phương (wall-clock time):** cửa hàng mở cửa 09:00, lịch bắt đầu lúc 08:30 ở một địa điểm. Có thể cần `LocalTime` / `LocalDateTime` cộng với `ZoneId`.
- **Thời điểm có offset cụ thể:** một event được gửi với `2026-10-30T10:15:30+07:00`; cần phân biệt giá trị tuyệt đối với offset mà nguồn đã công bố.
- **Lịch theo múi giờ địa lý:** cuộc hẹn 09:00 tại `Europe/Berlin` trong nhiều tháng tới; cần quy tắc timezone, bao gồm khả năng đổi giờ mùa hè.

Bài này tập trung vào **mapping kiểu timestamp, offset và timezone khi ghi/đọc qua Spring JDBC**, cùng vấn đề **độ chính xác phần giây**.

## 2. Chọn đúng kiểu trong Java 17+

Các lớp chuẩn ở package `java.time` mang ý nghĩa khác nhau:

| Kiểu Java | Thông tin được giữ | Phù hợp nhất cho | Không chứa |
| --- | --- | --- | --- |
| `Instant` | Điểm tuyệt đối trên dòng thời gian UTC | Timestamp của sự kiện, audit, expiration | Giờ địa phương và `ZoneId` |
| `LocalDateTime` | Ngày + giờ trên đồng hồ | Lịch giờ địa phương, SQL timestamp không múi giờ | Offset, `ZoneId`, instant |
| `OffsetDateTime` | Ngày + giờ + offset cố định như `+07:00` | Trao đổi ISO-8601 có offset, JDBC `TIMESTAMP WITH TIME ZONE` được hỗ trợ | Quy tắc múi giờ địa lý |
| `ZonedDateTime` | Ngày + giờ + `ZoneId`, kèm offset theo quy tắc tại thời điểm đó | Hiển thị, lịch đặt trước, xử lý DST | Không có bảo đảm JDBC sẽ lưu lại tên `ZoneId` |
| `LocalDate` | Ngày không giờ | Sinh nhật, ngày kế toán | Giờ và timezone |
| `LocalTime` | Giờ không ngày | Giờ mở cửa mỗi ngày | Ngày và timezone |
| `java.sql.Timestamp` | Giá trị timestamp kiểu JDBC cũ, chứa nanos nhưng không mang `ZoneId` | Tương thích API JDBC cũ | Ý nghĩa timezone tường minh |

Ví dụ Java 17:

```java
import java.time.*;

Instant instant = Instant.parse("2026-10-30T03:15:30.123456Z");
OffsetDateTime withOffset =
        instant.atOffset(ZoneOffset.ofHours(7));
ZonedDateTime inVietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime wallClock = inVietnam.toLocalDateTime();

System.out.println(withOffset);
System.out.println(inVietnam);
System.out.println(wallClock);
```

Đoạn trên là **ví dụ minh họa trong một phương thức/lớp Java**, chưa phải file độc lập. `Instant` là điểm thời gian gốc. `atOffset(...)` và `atZone(...)` chỉ chọn cách thể hiện thời điểm; `toLocalDateTime()` **bỏ thông tin timezone/offset**, nên không tự đảo ngược về `Instant` nếu không có thêm zone hoặc offset đúng.

Không nên gọi `LocalDateTime.now()` rồi gắn tùy tiện `ZoneOffset.UTC` và xem đó là timestamp UTC: `LocalDateTime.now()` lấy giờ theo timezone mặc định của JVM. Muốn mốc hiện tại, dùng `Instant.now()` hoặc một `Clock` được cấu hình rõ.

### Offset khác múi giờ

`ZoneOffset.ofHours(7)` là một độ lệch UTC **cố định**. `ZoneId.of("Asia/Ho_Chi_Minh")` là định danh múi giờ theo cơ sở dữ liệu quy tắc IANA. Một zone có thể có offset khác nhau tùy thời điểm lịch sử hoặc điều chỉnh pháp lý; một offset đơn lẻ không mô tả hết các quy tắc đó.

`ZonedDateTime` là lựa chọn tự nhiên khi nghiệp vụ cần "09:00 giờ địa phương ở một địa điểm", nhất là với lịch tương lai. `OffsetDateTime` hữu ích khi dữ liệu đã có offset, nhưng **offset không cho biết thành phố hay quy tắc DST**.

## 3. Kiểu SQL không mang cùng ý nghĩa ở mọi hệ CSDL

### TIMESTAMP WITHOUT TIME ZONE

Trong PostgreSQL và H2, `TIMESTAMP` / `TIMESTAMP WITHOUT TIME ZONE` lưu **ngày giờ địa phương**, không có offset hay vùng IANA. Java tương ứng thường là `LocalDateTime`:

```sql
-- PostgreSQL/H2:
meeting_local TIMESTAMP(6) WITHOUT TIME ZONE
```

Giá trị `2026-10-30 10:15:30` chỉ là thời gian trên đồng hồ. Nó không thể trở thành `Instant` nếu chưa biết nó thuộc timezone nào và xử lý thế nào khi có khoảng giờ DST không tồn tại hoặc trùng lặp.

Trong PostgreSQL, nếu ép literal kiểu `timestamp without time zone` chứa phần `+07:00`, PostgreSQL **có thể bỏ qua chỉ báo offset** vì kiểu cột/literal đã được xác định là không có timezone. Đừng dùng chuỗi có offset với cột này rồi mặc định offset sẽ được bảo toàn.

### TIMESTAMP WITH TIME ZONE

Tên SQL này **không có nghĩa chắc chắn database lưu tên `Asia/Ho_Chi_Minh` hoặc offset gốc**. Hành vi tùy hệ quản trị:

- **PostgreSQL `TIMESTAMPTZ`:** lưu một thời điểm (chuẩn hóa UTC); **không giữ offset hay zone gốc**. Khi hiển thị bằng SQL, hệ thống chuyển theo tham số timezone của session. PostgreSQL JDBC thường đọc thành `OffsetDateTime` có offset `Z`, dù bạn ghi `+07:00`.
- **H2 `TIMESTAMP WITH TIME ZONE`:** biểu diễn cả ngày-giờ và offset và hỗ trợ mapping `OffsetDateTime`; dữ liệu vẫn không tự giữ ID vùng địa lý IANA.
- **SQL Server `datetimeoffset`:** kiểu riêng lưu thông tin date/time và offset; không phải tên vùng `Europe/Berlin`.
- **MySQL:** `TIMESTAMP` có cơ chế chuyển giữa session timezone và UTC, còn `DATETIME` không thực hiện phép chuyển session timezone tương tự. Không suy diễn rằng tên `TIMESTAMP` trong MySQL giống `TIMESTAMP WITHOUT TIME ZONE` của PostgreSQL/H2.

Một cách ghi chú trong tài liệu schema:

| Hệ CSDL | Kiểu | Ý nghĩa cần ghi nhớ | Java thường dùng |
| --- | --- | --- | --- |
| PostgreSQL | `timestamp(6) without time zone` | Giá trị ngày/giờ địa phương, không có offset | `LocalDateTime` |
| PostgreSQL | `timestamptz(6)` | Điểm thời gian UTC; offset gốc không được giữ | `OffsetDateTime` qua pgJDBC rồi có thể gọi `toInstant()` |
| H2 | `timestamp(6)` | Ngày/giờ địa phương | `LocalDateTime` |
| H2 | `timestamp(6) with time zone` | Ngày/giờ kèm offset | `OffsetDateTime` |
| MySQL | `datetime(6)` | Giá trị ngày/giờ dạng local, không tự chuyển session timezone | Dùng mapping driver phù hợp, thường `LocalDateTime` |
| MySQL | `timestamp(6)` | Được chuyển theo session timezone; không lưu ID vùng | Kiểm tra driver/session/connection khi mapping |

**Kết luận thực dụng:** trước khi chọn kiểu Java, phải biết database, schema, JDBC driver và ý nghĩa nghiệp vụ. Cùng tên SQL `TIMESTAMP` có thể đưa đến kết quả khác giữa các DB.

## 4. Mapping JDBC 4.2 trong Spring JdbcTemplate

Spring `JdbcTemplate` hỗ trợ các câu lệnh JDBC. Nó **không thay thế** cơ chế chuyển đổi ngày giờ của driver; Spring quản lý kết nối, statement, mapping callback và dịch lỗi `SQLException`. Với JDBC 4.2+, cách rõ ý nghĩa là:

**Ghi:** sử dụng `PreparedStatement.setObject(index, value)` với kiểu `java.time` mà driver hỗ trợ.

**Đọc:** sử dụng `ResultSet.getObject(columnLabel, JavaType.class)` trong `RowMapper`. Driver có quyền từ chối conversion chưa hỗ trợ; cần integration test trên DB thật.

Ví dụ một đoạn phương thức repository (đã có biến `JdbcTemplate jdbc`):

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

void save(JdbcTemplate jdbc,
          LocalDateTime localStart,
          OffsetDateTime happenedAt) {
    jdbc.update(
        "INSERT INTO event_times (event_key, local_start, happened_at) " +
        "VALUES (?, ?, ?)",
        ps -> {
            ps.setString(1, "event-001");
            ps.setObject(2, localStart);
            ps.setObject(3, happenedAt);
        }
    );
}
```

Đoạn này **không phải chương trình độc lập**; bảng `event_times` và cách đọc được tạo trong ví dụ đầy đủ ở phần sau. Điểm quan trọng là `setObject(2, LocalDateTime)` nhắm vào cột không có timezone, còn `setObject(3, OffsetDateTime)` nhắm vào cột có timezone. Điều này giúp ý nghĩa dữ liệu tường minh.

Đọc theo kiểu xác định:

```java
LocalDateTime local = rs.getObject("local_start", LocalDateTime.class);
OffsetDateTime withOffset =
        rs.getObject("happened_at", OffsetDateTime.class);
Instant happenedInstant = withOffset.toInstant();
```

Đây là **trích đoạn nằm trong `RowMapper`**, trong đó `rs` là `ResultSet` của hàng hiện tại. Không ép `LocalDateTime` sang `Instant` bằng timezone mặc định vô tình của máy.

Nếu driver yêu cầu SQL type cụ thể, có thể truyền thêm kiểu đích:

```java
import java.sql.Types;

// Trong PreparedStatementSetter:
ps.setObject(2, localStart, Types.TIMESTAMP);
ps.setObject(3, happenedAt, Types.TIMESTAMP_WITH_TIMEZONE);
```

Đây cũng là **đoạn minh họa**, không phải file Java độc lập. Một số driver có giới hạn đối với `Types.TIMESTAMP_WITH_TIMEZONE` hoặc cách chuyển đổi `OffsetDateTime`; lựa chọn overload phải được thử trên driver thật. Với giá trị `null`, có thể dùng `ps.setNull(index, Types.TIMESTAMP)` hoặc `Types.TIMESTAMP_WITH_TIMEZONE` theo kiểu cột; không phải driver nào cũng suy luận chính xác kiểu SQL của `setObject(index, null)`.

## 5. Ví dụ Spring JDBC chạy được: đọc/ghi và kiểm tra round-trip

Ví dụ sử dụng Java 17+, Spring Boot 3.5.7, JDBC và H2. H2 được chọn vì hỗ trợ `TIMESTAMP(6) WITH TIME ZONE` và `OffsetDateTime`. Ví dụ chứng minh **giá trị LocalDateTime**, **instant** và **6 chữ số thập phân của giây** được bảo toàn khi truyền vào DB rồi đọc lại.

Cấu trúc:

```text
timestamp-jdbc-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/timestamp/
    │   └── TimestampJdbcApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>timestamp-jdbc-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE event_times (
    event_key VARCHAR(40) PRIMARY KEY,
    local_start TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL,
    happened_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

**`src/main/resources/application.properties`:**

```properties
spring.datasource.url=jdbc:h2:mem:timestamp_jdbc_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.banner-mode=off
logging.level.root=ERROR
```

**`src/main/java/com/example/timestamp/TimestampJdbcApplication.java`:**

```java
package com.example.timestamp;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TimestampJdbcApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimestampJdbcApplication.class, args);
    }

    private record TimeRow(
            LocalDateTime localStart,
            OffsetDateTime happenedAt) {}

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            LocalDateTime inputLocal =
                    LocalDateTime.of(2026, 10, 30, 9, 15, 30, 123_456_000);
            OffsetDateTime inputOffset =
                    OffsetDateTime.of(
                            2026, 10, 30, 10, 15, 30, 123_456_000,
                            ZoneOffset.ofHours(7));

            int inserted = jdbc.update(
                    "INSERT INTO event_times " +
                    "(event_key, local_start, happened_at) VALUES (?, ?, ?)",
                    ps -> {
                        ps.setString(1, "event-001");
                        ps.setObject(2, inputLocal);
                        ps.setObject(3, inputOffset);
                    });

            TimeRow actual = jdbc.queryForObject(
                    "SELECT local_start, happened_at " +
                    "FROM event_times WHERE event_key = ?",
                    (rs, rowNum) -> new TimeRow(
                            rs.getObject("local_start", LocalDateTime.class),
                            rs.getObject("happened_at", OffsetDateTime.class)),
                    "event-001");

            if (actual == null) {
                throw new IllegalStateException("No row returned");
            }

            Instant storedInstant = actual.happenedAt().toInstant();

            System.out.println("Rows inserted: " + inserted);
            System.out.println("Local time intact: " +
                    inputLocal.equals(actual.localStart()));
            System.out.println("Instant intact: " +
                    inputOffset.toInstant().equals(storedInstant));
            System.out.println("Six-digit fraction intact: " +
                    (actual.localStart().getNano() == 123_456_000 &&
                     actual.happenedAt().getNano() == 123_456_000));
        };
    }
}
```

Yêu cầu máy có JDK 17+ và Maven; đứng tại thư mục `timestamp-jdbc-demo` rồi chạy:

```bash
mvn -q spring-boot:run
```

**Bốn dòng do chương trình in** trong cấu hình H2 mới và bảng trống:

```text
Rows inserted: 1
Local time intact: true
Instant intact: true
Six-digit fraction intact: true
```

Các thông báo từ Maven hoặc runtime có thể phụ thuộc môi trường. Các giá trị nanosecond cố tình kết thúc bằng `000` để tương thích chính xác với cột SQL có **6 chữ số thập phân giây** (microsecond).

Điều cần đọc từ ví dụ:

1. Cột `local_start` có kiểu `TIMESTAMP(6) WITHOUT TIME ZONE`. Khi đọc, nó khớp `LocalDateTime` đã ghi, **không có gì để suy ra UTC instant**.
2. Cột `happened_at` có kiểu `TIMESTAMP(6) WITH TIME ZONE`. Spring JDBC chuyển `OffsetDateTime` qua driver, rồi đọc lại. So sánh `toInstant()` kiểm tra **đúng thời điểm** thay vì giả định offset biểu diễn phải giống chuỗi đầu vào.
3. `123_456_000` nanosecond tương ứng `.123456` giây. Vì cột có precision 6, giá trị được kỳ vọng giữ trọn trên H2.
4. Khi thay H2 bằng PostgreSQL, kiểu và offset được trả về có thể khác; PostgreSQL JDBC thường trả `OffsetDateTime` ở UTC. Kiểm tra instant, không khẳng định offset `+07:00` được lưu.
5. Không dùng `java.sql.Timestamp` để ngầm suy luận timezone; ví dụ chọn các API `java.time` có ý nghĩa tường minh.

**Giới hạn kiểm chứng:** project mẫu được thiết kế cho Spring Boot 3.5.7/H2 và các API JDBC 4.2, nhưng kết quả JDBC cần được chạy trên môi trường/driver thực tế khi áp dụng; không coi H2 thay thế phép thử PostgreSQL, MySQL hay SQL Server.

## 6. Khi nào cần Instant, khi nào giữ LocalDateTime + ZoneId?

### Trường hợp A: Timestamp sự kiện / audit

Lưu "thanh toán xảy ra tại thời điểm nào" bằng một instant. Trong service:

```java
import java.time.*;

Instant createdAt = Instant.parse("2026-10-30T03:15:30.123456Z");

// Nếu driver cần OffsetDateTime cho TIMESTAMP WITH TIME ZONE:
OffsetDateTime forJdbc = createdAt.atOffset(ZoneOffset.UTC);
```

`Instant` là hợp đồng nghiệp vụ. `OffsetDateTime` ở UTC là **kiểu truyền cho JDBC**, không làm mất instant. Với PostgreSQL `timestamptz`, việc này phù hợp hơn lưu timestamp địa phương và tự đoán timezone khi đọc.

Khi hiển thị:

```java
ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime viewerTime = createdAt.atZone(viewerZone);
// 2026-10-30T10:15:30.123456+07:00[Asia/Ho_Chi_Minh]
```

Đây là một đoạn Java minh họa ở trong phương thức. Tên `ZoneId` không nhất thiết được giữ trong cột timestamp; nó có thể đến từ hồ sơ người xem, cấu hình tổ chức hoặc thông tin nghiệp vụ khác.

### Trường hợp B: Lịch hẹn 09:00 theo địa điểm

Giả sử dịch vụ đặt lịch luôn diễn ra lúc 09:00 tại `Europe/Berlin`, kể cả khi offset mùa hè/mùa đông đổi:

```java
LocalDateTime scheduledLocal =
        LocalDateTime.of(2026, 11, 10, 9, 0);
ZoneId venueZone = ZoneId.of("Europe/Berlin");
Instant scheduledInstant =
        scheduledLocal.atZone(venueZone).toInstant();
```

Nếu chỉ lưu `Instant`, bạn biết thời điểm cụ thể đã tính **theo quy tắc timezone hiện tại**; nếu nghiệp vụ yêu cầu lặp lại 09:00 mỗi ngày hoặc phải tính lại khi luật timezone thay đổi, nên giữ thêm **giờ địa phương và `ZoneId` IANA**. Một thiết kế hợp lý có thể gồm `scheduled_local TIMESTAMP`, `zone_id VARCHAR` và một mốc UTC đã tính cho lần thực thi cụ thể. Không đồng nhất `ZoneId` với offset hiện tại.

### DST: Giờ không tồn tại và giờ bị lặp

Vùng có chuyển đổi Daylight Saving Time có thể xảy ra:

- **Gap:** đồng hồ nhảy qua một khoảng, ví dụ 02:30 không tồn tại tại một ngày chuyển mùa.
- **Overlap:** đồng hồ quay lại; 02:30 xuất hiện **hai lần**, tương ứng hai offset và hai instants.

Java cho phép kiểm tra:

```java
import java.time.*;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

if (offsets.size() == 0) {
    throw new IllegalArgumentException("Local time falls in DST gap");
}
if (offsets.size() == 2) {
    throw new IllegalArgumentException(
            "Ambiguous local time; choose an explicit offset");
}
Instant resolved = local.toInstant(offsets.get(0));
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Với quy tắc IANA hiện dùng cho `Europe/Berlin`, 02:30 ngày 25-10-2026 là giờ overlap (hai offset hợp lệ), do đó ví dụ sẽ ném exception trước khi tạo `resolved`. Trong thực tế, một hệ thống đặt lịch cần chính sách rõ khi gặp gap/overlap; tránh mặc định âm thầm tự chuyển đổi giờ. Dữ liệu timezone IANA có thể cập nhật theo luật.

## 7. So sánh thời điểm: equals khác isEqual

Hai `OffsetDateTime` dưới đây chỉ cùng instant nhưng mang hai offset khác nhau:

```java
import java.time.OffsetDateTime;

OffsetDateTime vietnam =
        OffsetDateTime.parse("2026-10-30T10:00:00+07:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2026-10-30T03:00:00Z");

System.out.println(vietnam.equals(utc));
System.out.println(vietnam.isEqual(utc));
System.out.println(vietnam.toInstant().equals(utc.toInstant()));
```

Kết quả của **ba lệnh println**:

```text
false
true
true
```

`equals` kiểm tra đồng thời giờ địa phương và offset; `isEqual` và so sánh `toInstant()` tập trung vào instant. Khi kiểm thử round-trip qua `timestamptz` PostgreSQL, không nên assert `OffsetDateTime.equals` nếu database/driver chuẩn hóa offset về UTC. Hãy so sánh `toInstant()` và, khi cần, kiểm tra sai lệch ở mức precision cho phép.

Với `LocalDateTime`, `equals` chỉ so các trường ngày/giờ; nó không chứng minh hai bản ghi xảy ra cùng một thời điểm nếu không có zone.

## 8. Độ chính xác: 3, 6 hay 9 chữ số sau dấu chấm?

Java `Instant`, `LocalDateTime`, `OffsetDateTime` có thể biểu diễn phần giây đến **nanosecond (9 chữ số)**. Nhưng độ phân giải của **giá trị nguồn** (đồng hồ hệ điều hành, database hay API) và độ chính xác **mà database lưu** là hai chuyện khác nhau.

| Precision SQL | Đơn vị nhỏ nhất theo khai báo | Ví dụ phần giây |
| --- | --- | --- |
| `TIMESTAMP(0)` | Giây | `.0` |
| `TIMESTAMP(3)` | Millisecond = 10^-3 giây | `.123` |
| `TIMESTAMP(6)` | Microsecond = 10^-6 giây | `.123456` |
| `TIMESTAMP(9)` | Nanosecond = 10^-9 giây, **chỉ nếu DB hỗ trợ** | `.123456789` |

Ví dụ:

```java
import java.time.Instant;

Instant value =
        Instant.parse("2026-10-30T03:15:30.123456789Z");

int nanos = value.getNano();  // 123456789
long epochMillis = value.toEpochMilli(); // Độ phân giải chỉ tới mili-giây
```

Đoạn code minh họa trong một phương thức. `toEpochMilli()` **làm mất phần microsecond/nanosecond** nếu bạn chỉ lưu giá trị `long` trả về; `getNano()` của `Instant` có thể giữ đủ 9 chữ số theo dữ liệu ban đầu. `java.sql.Timestamp.getTime()` cũng trả epoch milliseconds, trong khi `Timestamp.getNanos()` lưu phần nanos riêng; không coi `getTime()` là bản sao đầy đủ độ chính xác.

**Ví dụ mất độ chính xác:** `.123456789` ghi vào cột `TIMESTAMP(6)` phải điều chỉnh về tối đa 6 chữ số. Database có thể làm tròn hoặc cắt phần dư tùy engine/setting. H2 được tài liệu mô tả làm tròn `half up` khi cast giảm precision; PostgreSQL hỗ trợ tối đa microsecond. Không tự giả định rằng cả PostgreSQL, H2 và MySQL cùng cắt theo một quy tắc duy nhất.

### Cách kiểm thử độ chính xác hợp lý

- Nếu schema có precision 6 và ứng dụng muốn kiểm tra equality tuyệt đối, dùng input có nano chia hết cho 1000 (như `123456000` trong ví dụ).
- Nếu dữ liệu có nhiều hơn 6 chữ số, đo sai lệch so với giá trị ghi và kiểm tra chính sách rounding của database, tránh assert bằng nhau từng nano.
- Nếu cần thứ tự sự kiện ổn định, **không dựa duy nhất vào timestamp đã làm tròn**. Nhiều sự kiện có thể cùng timestamp; dùng thêm ID/sequence hoặc thứ tự logic.
- Nếu đo thời gian thực thi, dùng `System.nanoTime()` để đo khoảng thời gian trong cùng tiến trình; không dùng timestamp database hoặc `LocalDateTime.now()` để benchmark có độ chính xác nano.
- `Instant.now()` trả về một `Instant` có khả năng lưu nano, **không có nghĩa đồng hồ hệ thống luôn cung cấp độ phân giải nanosecond**.

### Đặc điểm của các DB phổ biến

- **PostgreSQL:** kiểu `timestamp(p)`/`timestamptz(p)` cho phép `p` từ 0 đến 6; độ phân giải thực tế là microsecond. Nếu ứng dụng đòi nanosecond nguyên vẹn, đây không phải một cột đủ thông tin.
- **MySQL 8.x:** `DATETIME(fsp)`/`TIMESTAMP(fsp)` hỗ trợ phần giây đến `fsp = 6`; nếu không chỉ định precision thì cần xem hành vi mặc định của schema/engine (nhiều cột mặc định không lưu phần giây). Đồng thời kiểm tra timezone session đối với `TIMESTAMP`.
- **H2:** `TIMESTAMP(p)`/`TIMESTAMP(p) WITH TIME ZONE` hỗ trợ `p` tới 9; mặc định 6. Vì H2 có thể giữ 9 chữ số mà PostgreSQL chỉ giữ 6, **test trên H2 không thay cho test precision trên PostgreSQL**.

## 9. Tránh đổi timezone ngầm qua java.sql.Timestamp và JVM

API JDBC cũ thường dùng:

```java
import java.sql.Timestamp;
import java.time.Instant;

// Ghi từ một instant:
Timestamp legacy = Timestamp.from(Instant.now());

// Đọc từ ResultSet:
Timestamp loaded = rs.getTimestamp("created_at");
Instant loadedInstant = loaded.toInstant();
```

Đây là **đoạn nằm trong code có `ResultSet rs`**, không phải file độc lập. `Timestamp` có thể chuyển sang/from `Instant`, nhưng quá trình chuyển đổi giữa một cột SQL không chứa timezone và `Timestamp` vẫn bị ảnh hưởng bởi cách driver diễn giải timestamp, timezone JVM hoặc `Calendar` được truyền vào một số overload.

Một số API cũ hỗ trợ:

```java
import java.sql.Timestamp;
import java.util.Calendar;
import java.util.TimeZone;

// Trong PreparedStatementSetter và RowMapper:
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
ps.setTimestamp(1, Timestamp.from(instant), utc);
Timestamp stored = rs.getTimestamp("created_at", utc);
```

Cũng là **đoạn minh họa**, phụ thuộc biến `ps`, `rs`, `instant`. `Calendar` thông báo cách diễn giải timestamp cho driver khi dùng API cũ; nó **không biến một cột `TIMESTAMP WITHOUT TIME ZONE` thành cột lưu timezone**. Với dự án mới có driver hỗ trợ JDBC 4.2, `setObject`/`getObject` với `java.time` sẽ thể hiện ý định rõ hơn.

Đặc biệt tránh:

```java
// Sai nếu "rawLocal" không chắc là giờ UTC:
Instant guessed = rawLocal.toInstant(ZoneOffset.UTC);
```

Dòng trên **giả định** `rawLocal` đã là giờ UTC. Nếu nguồn thực sự là 10:15 ở Việt Nam, gắn UTC sẽ làm timestamp lệch 7 giờ. Chỉ dùng `ZoneOffset.UTC` khi dữ liệu được định nghĩa rõ là giờ UTC; nếu là giờ địa phương, phải lấy `ZoneId` và giải quyết trường hợp DST nếu có.

## 10. Tính đúng đắn của các khoảng thời gian và truy vấn SQL

Nếu người dùng chọn "ngày 30/10 tại Việt Nam", khoảng ngày đó trên UTC phải được tính **từ ngày và múi giờ của người dùng**, thay vì lấy ngày của UTC hoặc áp dụng `DATE(happened_at)` với timezone session không rõ.

```java
import java.time.*;

LocalDate requestedDate = LocalDate.of(2026, 10, 30);
ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        requestedDate.atStartOfDay(viewerZone).toInstant();
Instant endExclusive =
        requestedDate.plusDays(1)
                .atStartOfDay(viewerZone).toInstant();
```

Đây là **đoạn trong phương thức Java**. Sử dụng khoảng **[startInclusive, endExclusive)** (đầu bao gồm, cuối loại trừ) để tránh mất bản ghi có phần giây lớn hơn `23:59:59.999` hoặc chồng lấn khi phân trang.

Nếu database PostgreSQL lưu instant trong `timestamptz`, SQL có thể dùng:

```sql
SELECT event_key, happened_at
FROM event_times
WHERE happened_at >= ?
  AND happened_at < ?
ORDER BY happened_at, event_key;
```

Bind `startInclusive.atOffset(ZoneOffset.UTC)` và `endExclusive.atOffset(ZoneOffset.UTC)` làm `OffsetDateTime`, trên driver có mapping `timestamptz` thích hợp. Đây là **SQL minh họa kiểu PostgreSQL**, không phải lệnh được chạy trong ví dụ H2 trước. Mẫu khoảng nửa mở cũng hữu ích khi dùng index và tránh phụ thuộc hàm trích `DATE` theo timezone session.

Với những múi giờ có DST, "một ngày địa phương" **không bắt buộc dài đúng 24 giờ**. Vì vậy hãy tính mốc đầu ngày kế tiếp bằng `plusDays(1).atStartOfDay(zone)`, không cộng thẳng `Duration.ofHours(24)` vào instant bắt đầu.

## 11. Các lỗi thường gặp khi đọc/ghi

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Timestamp lệch vài giờ | Nhầm timestamp không timezone với UTC; JVM/DB session timezone khác | Xác định kiểu cột, timezone session và nguồn dữ liệu; dùng `Instant`/`OffsetDateTime` có nghĩa rõ ràng |
| Ghi `+07:00` rồi đọc ra `Z` | PostgreSQL `timestamptz` chuẩn hóa instant, không giữ offset gốc | So sánh `toInstant()`; nếu cần offset gốc, lưu riêng |
| Mất tên vùng `Europe/Berlin` | Database chỉ lưu instant/offset, không lưu `ZoneId` | Lưu IANA `zone_id` trong cột riêng khi nghiệp vụ cần |
| Lúc DST ứng dụng chèn nhầm thời điểm | `LocalDateTime` có thể không xác định hoặc có hai offset hợp lệ | Kiểm tra `ZoneRules.getValidOffsets()`, yêu cầu lựa chọn rõ hoặc chính sách xử lý |
| `getObject(..., OffsetDateTime.class)` báo không hỗ trợ | Driver/cột SQL không có mapping phù hợp | Kiểm tra driver, SQL type; dùng `LocalDateTime` với cột local, hoặc mapping có kiểm soát theo vendor |
| So sánh `OffsetDateTime.equals` thất bại dù cùng sự kiện | Offset bị chuẩn hóa nhưng instant vẫn bằng nhau | So sánh `isEqual` hoặc `toInstant` |
| Mất 3 chữ số nanos cuối | Cột chỉ lưu microsecond, input có nano | Chọn precision phù hợp, xét rounding, dùng kiểm thử tolerance |
| Lấy `getTime()` rồi không còn microsecond | `Timestamp.getTime()` và `toEpochMilli()` là millisecond | Giữ `Instant` hoặc `Timestamp.toInstant()` nếu cần phần nhỏ hơn ms |
| Giá trị NULL bị driver từ chối | `setObject(index, null)` không xác định SQL type | Gọi `setNull(index, Types.TIMESTAMP...)` chính xác |
| H2 test tốt, production sai | Khác conversion của PostgreSQL/MySQL, session timezone, precision và JDBC driver | Test integration trên DB/driver thật với timezone khác nhau |
| Timestamp từ `CURRENT_TIMESTAMP` khác JVM clock | Đồng hồ DB khác ứng dụng, semantics thời điểm/transaction và timezone session | Chọn bên cấp timestamp (DB hay app), đồng bộ đồng hồ, test ý nghĩa mốc |
| Hai sự kiện có cùng timestamp | Precision DB/clock không đủ để tạo thứ tự duy nhất | Dùng khóa/sequence hoặc version độc lập |

### Checklist chẩn đoán nhanh

1. **Schema:** cột là `TIMESTAMP WITHOUT TIME ZONE`, `TIMESTAMP WITH TIME ZONE`, `DATETIME` hay kiểu vendor khác? Precision bao nhiêu?
2. **Java model:** dữ liệu là mốc tuyệt đối, giờ đồng hồ, offset cố định hay lịch theo IANA `ZoneId`?
3. **Connection:** timezone mặc định của JVM, session timezone của database, các tham số JDBC URL/driver có gì đặc biệt?
4. **Ghi/đọc:** dùng `setObject`/`getObject` hay legacy `getTimestamp`? Có conversion ngầm?
5. **Kiểm chứng:** cùng dữ liệu thử với UTC và timezone khác, với giá trị nanos 6/9 chữ số và ca gần DST.
6. **Hợp đồng API:** JSON giữ offset/zone nào? Có đang parse ISO-8601 thành `LocalDateTime` và vô tình mất offset?
7. **Kiểu kết quả:** khi kiểm thử instant, so sánh instant; khi kiểm thử local schedule, so ngày/giờ và zone theo ý nghĩa nghiệp vụ.

## 12. Thiết kế lưu trữ đáng tin cậy cho từng use case

**Audit/log/payment:** lưu một instant UTC bằng kiểu SQL có semantics phù hợp với hệ CSDL, ví dụ PostgreSQL `timestamptz(6)`. Trong domain, dùng `Instant`; khi JDBC cần `OffsetDateTime`, chuyển `instant.atOffset(ZoneOffset.UTC)`. Client nên nhận ISO-8601 có offset/UTC rõ ràng.

**Lịch theo địa phương:** lưu `LocalDateTime` **và** `ZoneId` như chuỗi `Europe/Berlin`. Khi cần tạo event thực tế, giải quyết DST và quy đổi sang instant. Nếu lịch theo quy tắc tương lai, đừng chỉ lưu offset `+01:00` vì mùa hè có thể cần `+02:00`.

**Nhập liệu chỉ có ngày giờ:** không thêm "Z" hoặc "+00:00" để làm dữ liệu trông có timezone nếu nguồn không nói vậy. Hỏi hoặc quy định rõ timezone của trường trước khi đưa vào DB.

**Khả năng tái lập dữ liệu:** lưu độ chính xác có chủ đích, ví dụ microsecond nếu DB dùng `TIMESTAMP(6)`. Với dữ liệu đồng bộ hệ thống, document rõ cả timezone và precision; test offset khác nhau, DST và các nanosecond ngoài 6 chữ số.

**Khi cần biết offset gốc:** dù cột `timestamptz` giữ đúng instant, cần thêm cột offset hoặc chuỗi thời gian gốc nếu nghiệp vụ phải chứng minh người gửi khai báo `+07:00`. Nếu cần vùng `Asia/Ho_Chi_Minh`, lưu thêm `zone_id`; offset không suy ra được tên vùng duy nhất.

## 13. Câu hỏi ôn tập

1. `LocalDateTime.of(2026,10,30,10,15)` có thể tự chuyển thành `Instant` không? Vì sao?
2. Tại sao PostgreSQL trả `OffsetDateTime` ở `Z` dù ứng dụng ghi `+07:00`?
3. Khi nào cần lưu `ZoneId` riêng, thay vì chỉ `OffsetDateTime`?
4. `TIMESTAMP(6)` lưu được đầy đủ `123456789` nanosecond hay không? Vì sao H2 có thể khác PostgreSQL?
5. Với ngày địa phương tại nơi có DST, tại sao `end = start.plus(24h)` có thể sai?
6. Vì sao `OffsetDateTime.equals(...)` có thể false khi hai giá trị đại diện cùng một instant?
7. Tại sao chuyển `java.sql.Timestamp` qua `getTime()` có thể làm mất precision dưới millisecond?

Nếu nắm được các câu trên, bạn có thể xây dựng hợp đồng dữ liệu thời gian rõ ràng từ API, Java, JDBC đến database, tránh lỗi lệch giờ và lỗi precision khó phát hiện.

## Tài liệu tham khảo chính thức

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Java 17 — java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java 17 — ResultSet.getObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html)
- [Java 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html)
- [PostgreSQL — Date/Time Types and Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html)
- [pgJDBC — Using Java 8 Date and Time Classes](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes)
- [H2 — Timestamp Types and Precision](https://h2database.github.io/html/datatypes.html)
- [MySQL 8.4 — DATE, DATETIME and TIMESTAMP](https://dev.mysql.com/doc/refman/8.4/en/datetime.html)
