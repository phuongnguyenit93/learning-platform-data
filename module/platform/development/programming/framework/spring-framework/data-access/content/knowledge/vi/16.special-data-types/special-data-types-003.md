# LocalDate, LocalTime, LocalDateTime và Instant: chọn kiểu Java theo ngữ nghĩa cột SQL

**Một giá trị trông giống ngày giờ không nhất thiết đại diện cho một thời điểm tuyệt đối.** Khi thiết kế lớp Java và thao tác với cơ sở dữ liệu qua Spring JDBC, hãy hỏi cột đang diễn đạt điều gì: một ngày trên lịch, một giờ trong ngày, một ngày giờ địa phương, hay một khoảnh khắc duy nhất trên trục thời gian? Câu trả lời quyết định nên dùng `LocalDate`, `LocalTime`, `LocalDateTime` hay `Instant`.

Ví dụ: ngày sinh `2026-07-15` không cần múi giờ; giờ mở cửa `09:00` không cần ngày; lịch hẹn `2026-07-15 16:00` tại một địa điểm là giờ địa phương; sự kiện đăng nhập `2026-07-15T02:30:00Z` là một thời điểm tuyệt đối. Lưu các giá trị này cùng một kiểu `Timestamp` rồi đoán ý nghĩa ở bước đọc là nguồn gây lỗi giờ giấc và timezone khó phát hiện.

Bài học này nằm trong phần **kiểu dữ liệu đặc biệt của Spring Framework Data Access**, tập trung vào **ngữ nghĩa cột, ánh xạ JDBC 4.2, cách bind/đọc bằng `JdbcTemplate`, chuyển đổi múi giờ và các bẫy khi triển khai đa database**.

## 1. Bảng ánh xạ theo ý nghĩa nghiệp vụ

| Ý nghĩa của dữ liệu | Java `java.time` | Kiểu SQL phổ biến | Có ngày? | Có giờ? | Có thông tin vùng/offset? |
| --- | --- | --- | --- | --- | --- |
| Ngày trên lịch: ngày sinh, ngày nghỉ, ngày chốt kỳ | `LocalDate` | `DATE` | Có | Không | Không |
| Giờ trong một ngày: mở cửa 09:00, giờ nhắc định kỳ | `LocalTime` | `TIME` / `TIME WITHOUT TIME ZONE` | Không | Có | Không |
| Ngày giờ dạng lịch tại địa phương: lịch hẹn 16:00 | `LocalDateTime` | `TIMESTAMP` / `TIMESTAMP WITHOUT TIME ZONE` | Có | Có | Không |
| Thời điểm tuyệt đối: sự kiện phát sinh, thời điểm nhận thanh toán | `Instant` | Thường `TIMESTAMP WITH TIME ZONE` qua `OffsetDateTime` của JDBC; hoặc chiến lược UTC được xác định rõ | Có | Có | `Instant` là điểm thời gian UTC, không mang tên múi giờ gốc |
| Ngày giờ kèm **UTC offset** như `+07:00` | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` nếu DB hỗ trợ | Có | Có | Có offset, nhưng chưa chắc có tên vùng |
| Giờ kèm offset, không có ngày | `OffsetTime` | `TIME WITH TIME ZONE` nếu DB hỗ trợ | Không | Có | Có offset |

**Quan trọng:** Bảng trên thể hiện ánh xạ thông dụng theo JDBC 4.2, không phải lời hứa mọi DB đều có cùng tên cột hoặc cùng chính sách chuyển múi giờ. Các kiểu vendor như MySQL `DATETIME`/`TIMESTAMP` hay Oracle `DATE` có quy tắc riêng. Kiểm tra DDL và tài liệu của đúng database/driver trước khi chuyển đổi dữ liệu thực tế.

Bốn kiểu chính của bài đều **immutable** và thuộc gói `java.time`:

- `LocalDate` chứa năm, tháng, ngày; không chứa giờ, offset hay `ZoneId`.
- `LocalTime` chứa giờ, phút, giây, nano trong ngày; không chứa ngày hoặc timezone.
- `LocalDateTime` ghép ngày và giờ địa phương; **không xác định duy nhất một `Instant`**.
- `Instant` chứa điểm thời gian trên timeline UTC (giây/nano từ epoch); không chứa tên múi giờ hiển thị hay lịch dân sự gốc.

## 2. Chọn kiểu từ câu hỏi nghiệp vụ, không từ hình thức chuỗi

### 2.1. `LocalDate` ↔ `DATE`: ngày vẫn là ngày dù người dùng ở đâu

Cột `date_of_birth`, `holiday_date`, `accounting_day` mang ý nghĩa ngày lịch. Giá trị `2026-07-15` phải giữ nguyên khi người dùng mở ứng dụng ở Hà Nội, Paris hay New York.

```java
LocalDate birthday = LocalDate.of(2000, 8, 20);
```

Thiết kế SQL:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    date_of_birth DATE NOT NULL
);
```

Không lưu ngày sinh thành `Instant` với quy ước "0 giờ UTC": khi hiển thị ở múi giờ âm, cùng một `Instant` có thể rơi vào ngày trước đó. Nếu nghiệp vụ thật sự xác định ngày theo **một vùng cụ thể** (ví dụ ngày giao dịch ở thị trường London), vẫn nên định nghĩa rõ vùng nào xác định ranh giới ngày khi tính toán; bản thân cột `DATE` chỉ lưu ngày đã được xác định.

### 2.2. `LocalTime` ↔ `TIME`: giờ theo đồng hồ, chưa phải một sự kiện

"Quán mở cửa lúc 09:00 mỗi ngày" biểu thị một **giờ trong ngày**, chưa có ngày cụ thể nên chưa chuyển được thành `Instant`.

```java
LocalTime opensAt = LocalTime.of(9, 0);
```

Schema:

```sql
CREATE TABLE branch_schedule (
    branch_id BIGINT PRIMARY KEY,
    daily_open_time TIME NOT NULL,
    zone_id VARCHAR(64) NOT NULL
);
```

`zone_id` là một quyết định nghiệp vụ bổ sung nếu cần tính các lần mở cửa thực tế ở nhiều khu vực; ví dụ `Asia/Ho_Chi_Minh` hay `Europe/Paris`. Chỉ lưu `09:00+07:00` dưới dạng offset cố định không mô tả đầy đủ lịch chuyển giờ mùa hè (DST) của một vùng có quy tắc đổi offset.

Nếu cần biểu diễn khoảng giờ chạy qua nửa đêm (22:00–02:00), hai `LocalTime` không tự cho biết khoảng cuối xảy ra ngày hôm sau. Cần quy tắc nghiệp vụ hoặc dữ liệu ngày đi kèm.

### 2.3. `LocalDateTime` ↔ `TIMESTAMP WITHOUT TIME ZONE`: ngày giờ trên lịch, thiếu vùng

```java
LocalDateTime appointment = LocalDateTime.of(2026, 7, 15, 16, 0);
```

```sql
CREATE TABLE local_appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_local TIMESTAMP NOT NULL,
    zone_id VARCHAR(64) NOT NULL
);
```

Giá trị `2026-07-15T16:00` cho biết "4 giờ chiều ngày 15/7" nhưng **chưa cho biết đó là thời điểm nào trên toàn cầu**. Khi kết hợp với `ZoneId`, ứng dụng mới có thể xét quy tắc timezone của nơi diễn ra:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant actualStart = appointment.atZone(zone).toInstant();
```

Đây là đoạn code minh họa sử dụng API `java.time`, giả định `appointment` đã có giá trị. Khi cần lập lịch tương lai ở vùng có DST, phải có chính sách xử lý giờ địa phương không tồn tại hoặc trùng lặp; xem mục 7.

Đừng coi tên SQL `TIMESTAMP` là bằng chứng cột lưu `Instant`. Ở nhiều DB, `TIMESTAMP WITHOUT TIME ZONE` chỉ lưu **ngày giờ địa phương**, không kèm offset. Nếu nghiệp vụ chỉ quan tâm giờ bắt đầu theo đồng hồ của một địa điểm, kiểu này phù hợp, nhưng vùng `ZoneId` cần được quản lý riêng khi chuyển thành một điểm thời gian.

### 2.4. `Instant`: thời điểm trên trục thời gian

`Instant.parse("2026-07-15T02:30:00Z")` và `2026-07-15 09:30:00+07:00` mô tả **cùng một sự kiện**. Dùng `Instant` cho `created_at`, `processed_at`, `payment_received_at`, thời điểm phát log/audit... khi "xảy ra lúc nào" mới là thông tin chính.

```java
Instant occurredAt = Instant.parse("2026-07-15T02:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime displayedAt = occurredAt.atZone(zone).toLocalDateTime();

// displayedAt là 2026-07-15T09:30
```

Một `Instant` không nhớ người tạo sự kiện ở vùng nào. Nếu ứng dụng phải **khôi phục chính xác vùng của người dùng/địa điểm ban đầu** hoặc lịch hẹn tương lai, hãy lưu thêm tên vùng, chẳng hạn `Asia/Ho_Chi_Minh` trong cột `zone_id`. Dữ liệu `UTC+07:00` chỉ là offset của một thời điểm, không thay thế mọi quy tắc lịch sử/tương lai của `ZoneId`.

## 3. Vì sao cùng một `LocalDateTime` có thể thành nhiều `Instant`?

Với thời gian địa phương 09:30 ngày 15/7/2026:

```java
import java.time.*;

class SameWallTime {
    public static void main(String[] args) {
        LocalDateTime local = LocalDateTime.of(2026, 7, 15, 9, 30);
        Instant inHcm = local.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")
        ).toInstant();
        Instant inParis = local.atZone(
            ZoneId.of("Europe/Paris")
        ).toInstant();

        System.out.println("HCMC: " + inHcm);
        System.out.println("Paris: " + inParis);
    }
}
```

Chạy độc lập bằng Java 17+:

```bash
javac SameWallTime.java
java SameWallTime
```

Lưu ý: đoạn trên phải lưu vào file `SameWallTime.java`. Kết quả:

```text
HCMC: 2026-07-15T02:30:00Z
Paris: 2026-07-15T07:30:00Z
```

Ngày 15/7/2026, TP.HCM có offset `+07:00`, Paris đang áp dụng DST với offset `+02:00`. Cùng chữ "09:30" nhưng hai `Instant` lệch nhau 5 giờ. Không có `ZoneId` đi kèm, `LocalDateTime` không chứa thông tin đủ để chọn một kết quả.

Ngược lại, một `Instant` luôn xác định đúng một điểm trên timeline; hiển thị nó qua `atZone(...)` có thể cho ngày và giờ khác nhau ở mỗi nơi **mà bản chất sự kiện không đổi**.

## 4. Ranh giới JDBC 4.2 và Spring JDBC

Spring JDBC cung cấp `JdbcTemplate`, `RowMapper`, `PreparedStatementSetter` và xử lý kết nối/ngoại lệ. **Việc chuyển `java.time` thành kiểu cột SQL và đọc trở lại vẫn đi qua JDBC driver**, nên cần chọn ánh xạ phù hợp với DB.

### 4.1. Ghi bằng `PreparedStatement.setObject`

Với driver hỗ trợ JDBC 4.2, mẫu bind phổ biến:

```java
ps.setObject(1, localDate);       // DATE
ps.setObject(2, localTime);       // TIME WITHOUT TIME ZONE
ps.setObject(3, localDateTime);   // TIMESTAMP WITHOUT TIME ZONE
```

Đây là đoạn minh họa bên trong callback có biến `ps` và ba giá trị đã được tạo. Không dùng `ps.setString(...)` cho mọi cột ngày giờ rồi phụ thuộc vào việc database tự parse string, vì định dạng và timezone có thể phụ thuộc session/vendor.

**Riêng `Instant` không phải kiểu Java bắt buộc trong mapping JDBC 4.2.** Một cách tương thích với H2 và PostgreSQL JDBC là chuyển `Instant` sang `OffsetDateTime` tại UTC rồi bind vào `TIMESTAMP WITH TIME ZONE`:

```java
OffsetDateTime utcValue = OffsetDateTime.ofInstant(
    occurredAt, ZoneOffset.UTC
);
ps.setObject(4, utcValue);
```

Không suy luận rằng `ps.setObject(index, instant)` hoạt động trên mọi driver. Ví dụ driver PostgreSQL hỗ trợ `OffsetDateTime` nhưng không hỗ trợ bind/đọc `Instant` trực tiếp theo mapping `java.time` của nó. H2 có thể hỗ trợ thêm các kiểu Java ngoài mức tối thiểu đó.

Nếu DB không cung cấp `TIMESTAMP WITH TIME ZONE`, hệ thống có thể chọn một **quy ước lưu UTC được định nghĩa và kiểm thử** (với kiểu cột thích hợp của vendor) hoặc lưu epoch integer theo độ chính xác đã thống nhất. Khi đó phải định nghĩa rõ ai chuyển đổi, session timezone, precision, và cách đọc trở lại; không được coi `TIMESTAMP` trần là tự nhiên có cùng nghĩa với `Instant`.

### 4.2. Đọc bằng `ResultSet.getObject(column, Type.class)`

```java
LocalDate day = rs.getObject("business_day", LocalDate.class);
LocalTime time = rs.getObject("opening_time", LocalTime.class);
LocalDateTime localTs = rs.getObject(
    "appointment_local", LocalDateTime.class
);
OffsetDateTime offsetValue = rs.getObject(
    "logged_at", OffsetDateTime.class
);
Instant eventInstant = offsetValue.toInstant();
```

Đây là đoạn minh họa bên trong `RowMapper` hoặc khi đã có `ResultSet rs`. Ưu điểm: mã thể hiện rõ **kiểu Java mong đợi** cho từng cột. Không giả định `rs.getObject("logged_at")` không truyền `Class` sẽ trả thẳng `Instant`; nó có thể trả `java.sql.Timestamp`, `OffsetDateTime` hoặc kiểu vendor khác theo driver.

Nếu cột cho phép `NULL`, `rs.getObject("...", Type.class)` có thể trả `null`. Phải kiểm tra `null` trước khi gọi `offsetValue.toInstant()`; ví dụ hoàn chỉnh bên dưới khai báo cả bốn cột là `NOT NULL`.

### 4.3. Khai báo SQL type khi bind `NULL`

```java
ps.setNull(1, java.sql.Types.DATE);
ps.setNull(2, java.sql.Types.TIME);
ps.setNull(3, java.sql.Types.TIMESTAMP);
ps.setNull(4, java.sql.Types.TIMESTAMP_WITH_TIMEZONE);
```

Đây là bốn lời gọi **minh họa tương ứng cho bốn kiểu cột**, không phải code để thực thi cùng lúc trên một statement thực tế bất kỳ. Khi tham số nullable, nên khai báo đúng SQL type theo schema và driver thay vì tự gửi chuỗi `"null"` hoặc dựa vào suy luận kiểu từ `null`.

Các wrapper Spring như `SqlParameterValue` và `MapSqlParameterSource.addValue(name, value, sqlType)` cũng giúp mang thông tin SQL type khi không viết callback `PreparedStatement` trực tiếp. Nhớ rằng cấu hình SQL type không thay thế được việc chọn đúng **ngữ nghĩa thời gian**.

## 5. Ví dụ chạy độc lập: bốn kiểu cột với JdbcTemplate và H2

Ví dụ lưu đồng thời ngày nghiệp vụ, giờ mở cửa, lịch hẹn địa phương và thời điểm phát sinh tuyệt đối. Để cho thấy sự khác nhau, lịch hẹn được đặt **16:00** trong khi timestamp audit là **02:30 UTC** (tức 09:30 ở TP.HCM).

Sơ đồ dữ liệu:

```text
Java domain                   SQL column                         JDBC bind/read
LocalDate                     business_day DATE                  LocalDate
LocalTime                     opening_time TIME                 LocalTime
LocalDateTime                 appointment_local TIMESTAMP       LocalDateTime
Instant                       logged_at TIMESTAMP WITH TIME ZONE OffsetDateTime UTC <-> Instant
```

Tạo cấu trúc:

```text
temporal-jdbc-demo/
├── build.gradle
└── src/main/java/TemporalJdbcDemo.java
```

Nội dung `build.gradle` (Java 17+, Gradle và Maven Central):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TemporalJdbcDemo'
}
```

Nội dung `src/main/java/TemporalJdbcDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class TemporalJdbcDemo {

    record TemporalRow(
        LocalDate businessDay,
        LocalTime openingTime,
        LocalDateTime appointmentLocal,
        Instant loggedAt
    ) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:temporal_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);

        jdbc.execute("""
            CREATE TABLE temporal_event (
                id BIGINT PRIMARY KEY,
                business_day DATE NOT NULL,
                opening_time TIME NOT NULL,
                appointment_local TIMESTAMP NOT NULL,
                logged_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """);

        LocalDate businessDay = LocalDate.of(2026, 7, 15);
        LocalTime openingTime = LocalTime.of(9, 0);
        LocalDateTime appointmentLocal = LocalDateTime.of(
            2026, 7, 15, 16, 0
        );
        Instant loggedAt = Instant.parse("2026-07-15T02:30:00Z");

        int inserted = jdbc.update("""
            INSERT INTO temporal_event
                (id, business_day, opening_time,
                 appointment_local, logged_at)
            VALUES (?, ?, ?, ?, ?)
            """, ps -> {
                ps.setLong(1, 7L);
                ps.setObject(2, businessDay);
                ps.setObject(3, openingTime);
                ps.setObject(4, appointmentLocal);
                ps.setObject(5, OffsetDateTime.ofInstant(
                    loggedAt, ZoneOffset.UTC
                ));
            });

        TemporalRow row = jdbc.queryForObject("""
            SELECT business_day, opening_time,
                   appointment_local, logged_at
            FROM temporal_event
            WHERE id = ?
            """, (rs, rowNum) -> {
                LocalDate day = rs.getObject(
                    "business_day", LocalDate.class
                );
                LocalTime time = rs.getObject(
                    "opening_time", LocalTime.class
                );
                LocalDateTime local = rs.getObject(
                    "appointment_local", LocalDateTime.class
                );
                OffsetDateTime loggedOffset = rs.getObject(
                    "logged_at", OffsetDateTime.class
                );
                return new TemporalRow(
                    day, time, local, loggedOffset.toInstant()
                );
            }, 7L);

        System.out.println("Inserted rows: " + inserted);
        System.out.println("Business day: " + row.businessDay());
        System.out.println("Opening time: " + row.openingTime());
        System.out.println("Appointment local: " + row.appointmentLocal());
        System.out.println("Logged instant: " + row.loggedAt());
        System.out.println(
            "Logged in HCMC: " + row.loggedAt()
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDateTime()
        );
    }
}
```

Chạy từ thư mục `temporal-jdbc-demo`:

```bash
gradle --quiet run
```

Nếu có Gradle Wrapper trong chính dự án, có thể dùng `./gradlew --quiet run` (Windows PowerShell: `.\gradlew.bat --quiet run`).

Với bảng H2 mới tạo và dữ liệu cố định, stdout của chương trình là:

```text
Inserted rows: 1
Business day: 2026-07-15
Opening time: 09:00
Appointment local: 2026-07-15T16:00
Logged instant: 2026-07-15T02:30:00Z
Logged in HCMC: 2026-07-15T09:30
```

Giải thích từng bước:

1. `DATE` nhận `LocalDate` và trở lại cùng ngày, không cần bù trừ giờ.
2. `TIME` nhận `LocalTime` 09:00, không tự biến thành một timestamp có ngày.
3. `TIMESTAMP` nhận `LocalDateTime` 16:00, không kèm offset.
4. `Instant` được chuyển sang `OffsetDateTime` UTC để bind vào `TIMESTAMP WITH TIME ZONE`. Khi đọc, `toInstant()` khôi phục **điểm thời gian**.
5. Chỉ tại lúc **hiển thị** mới gọi `loggedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))`; dữ liệu audit vẫn giữ nghĩa "sự kiện xảy ra tại 02:30 UTC".
6. `JdbcTemplate` quản lý statement/result set và dịch `SQLException` thành nhánh `DataAccessException` của Spring; callback ở đây chỉ bind hoặc ánh xạ dữ liệu.

Đừng suy luận `appointmentLocal` và `loggedAt` là cùng một loại giá trị chỉ vì cả hai trông giống ngày giờ; một giá trị là 16:00 chưa biết vùng, một giá trị là điểm thời gian tuyệt đối có thể hiển thị thành 09:30 ở Việt Nam.

**Phạm vi của ví dụ:** H2 2.3.x hỗ trợ `LocalDate`, `LocalTime`, `LocalDateTime` và `OffsetDateTime` phù hợp với bốn kiểu cột đã dùng. Khi triển khai PostgreSQL, SQL Server, Oracle hoặc MySQL, tên kiểu, precision và xử lý timezone phải được đối chiếu riêng với driver thực tế.

## 6. Nếu dự án dùng PostgreSQL: ví dụ tách rõ `timestamp` và `timestamptz`

Trong PostgreSQL:

```sql
CREATE TABLE order_events (
    id BIGINT PRIMARY KEY,
    scheduled_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    location_zone_id VARCHAR(64) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Ví dụ nghiệp vụ:

- `scheduled_local` = "2026-07-15 16:00": lịch theo giờ địa phương của chi nhánh.
- `location_zone_id` = "Asia/Ho_Chi_Minh": cung cấp quy tắc vùng để xác định lịch trên timeline.
- `occurred_at` = "2026-07-15T02:30:00Z": điểm thời gian audit.

Driver PostgreSQL ánh xạ thông dụng:

```java
LocalDateTime local = rs.getObject(
    "scheduled_local", LocalDateTime.class
);

OffsetDateTime occurred = rs.getObject(
    "occurred_at", OffsetDateTime.class
);
Instant instant = occurred.toInstant();
```

PostgreSQL `TIMESTAMP WITH TIME ZONE` (thường viết `timestamptz`) lưu thông tin thời điểm theo UTC về mặt ngữ nghĩa; nó **không lưu lại tên vùng ban đầu** và driver PostgreSQL thường trả `OffsetDateTime` ở offset `Z`. Vì vậy:

```text
Input:   2026-07-15T09:30:00+07:00
Read:    2026-07-15T02:30:00Z
Instant: cùng một thời điểm
```

Nếu cần so khớp ý nghĩa thời điểm, hãy so `input.toInstant()` và `read.toInstant()`. Không bắt buộc `OffsetDateTime.equals(...)` phải bằng `true`, vì `OffsetDateTime` còn xét cả local date-time và offset. Nếu cần vùng gốc theo tên IANA hoặc lịch tương lai, lưu thêm `zone_id` có chủ đích.

Với SQL Server, MySQL, Oracle... khái niệm và cách chuyển timestamp theo session/driver có thể khác. Đặc biệt không được tự xem `DATETIME` hay `TIMESTAMP` mang nghĩa UTC chỉ vì ứng dụng đang chạy ở UTC.

## 7. DST: giờ không tồn tại, giờ trùng lặp và tên vùng

Dùng `ZoneId` và `ZoneOffset` đúng vai trò:

- `ZoneOffset.ofHours(7)` là độ lệch **cố định** so với UTC.
- `ZoneId.of("Europe/Paris")` là tên vùng có **quy tắc thay đổi offset** theo ngày, gồm giờ mùa hè.
- `Instant` không có DST; DST là một quy tắc để biểu diễn **giờ dân sự** trong một vùng cụ thể.

Có hai tình huống đặc biệt trong vùng có DST:

**Gap — giờ không tồn tại:** Khi đồng hồ nhảy từ 01:59 lên 03:00, một số giờ như 02:30 không tồn tại vào ngày chuyển mùa. `LocalDateTime` vẫn có thể biểu diễn 02:30 vì nó không biết vùng, nhưng để biến thành `Instant` phải áp dụng chính sách: từ chối lịch hẹn, chuyển sang thời điểm hợp lệ kế tiếp, hoặc hỏi người dùng.

**Overlap — giờ xuất hiện hai lần:** Khi đồng hồ quay lùi, 02:30 có thể ứng với **hai `Instant` khác nhau**. `local.atZone(zone)` có quy tắc mặc định để chọn offset; nếu nghiệp vụ cần chính xác, hãy kiểm tra `zone.getRules().getValidOffsets(local)` và chọn offset theo chính sách rõ ràng thay vì im lặng sử dụng mặc định.

Mẫu kiểm tra trước khi tạo lịch:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

// Giả sử local và zone đến từ dữ liệu đã kiểm tra.
ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    // Gap: local time không tồn tại tại vùng đó.
    throw new IllegalArgumentException("Nonexistent local time");
}
if (offsets.size() > 1) {
    // Overlap: cần chính sách chọn offset / thông báo người dùng.
    throw new IllegalArgumentException("Ambiguous local time");
}

Instant exactMoment = local.atOffset(offsets.get(0)).toInstant();
```

Đây là **mảnh mã cho ứng dụng đã có biến `local`, `zone`**, không phải chương trình độc lập. Nó phù hợp khi yêu cầu từ chối lịch mơ hồ; những nghiệp vụ khác có thể chọn một chính sách khác. Để so sánh/đặt lịch xuyên vùng, sau khi giải quyết ambiguity mới lưu hoặc tính `Instant`.

## 8. NULL, độ chính xác, phạm vi giá trị và đồng hồ

### 8.1. Xử lý cột nullable

`ResultSet.getObject(column, LocalDate.class)` và các kiểu ngày giờ có thể trả `null` nếu SQL `NULL`. Với `Instant` thông qua `OffsetDateTime`:

```java
OffsetDateTime dbValue = rs.getObject(
    "completed_at", OffsetDateTime.class
);
Instant completedAt = (dbValue == null)
    ? null
    : dbValue.toInstant();
```

Đừng gọi `toInstant()` ngay trên `null`. Trong domain, cân nhắc `Optional` ở tầng API/phương thức nếu hữu ích; không tự biến `NULL` thành `Instant.EPOCH`, vì "chưa có thời điểm" khác "1970-01-01T00:00:00Z".

### 8.2. Precision khác nhau giữa Java và database

`java.time` có độ chính xác đến **nanosecond**; database có thể chỉ lưu microsecond, millisecond hoặc giây tùy cột/driver. Ví dụ `TIMESTAMP(3)` ở một số DB lưu ba chữ số thập phân giây; `TIMESTAMP(6)` lưu sáu chữ số. Khi ghi `2026-07-15T09:30:00.123456789`, giá trị đọc lại có thể bị cắt hoặc làm tròn.

Do đó, không mặc định `input.equals(readBack)` nếu schema chỉ giữ phần nhỏ hơn nano. Với test, hãy kiểm tra khả năng precision của DB và nhất quán cách làm tròn, hoặc dùng giá trị cố định không có phần lẻ như ví dụ phần 5.

### 8.3. Clock và test tính quyết định

`Instant.now()` phụ thuộc đồng hồ hiện tại, `LocalDate.now()` và `LocalDateTime.now()` còn phụ thuộc timezone được dùng để tạo giá trị. Trong nghiệp vụ cần đo thời điểm tuyệt đối, inject `Clock` là cách dễ test:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.fixed(
    Instant.parse("2026-07-15T02:30:00Z"),
    java.time.ZoneOffset.UTC
);
Instant createdAt = Instant.now(clock);
```

Đây là mảnh mã minh họa. `Instant.now(clock)` cho giá trị nhất quán khi test; `Clock.systemUTC()` là lựa chọn thường gặp trong runtime. Dù ứng dụng có `Clock` UTC, vẫn phải chọn đúng kiểu cột SQL khi lưu.

### 8.4. Đừng dùng epoch-milliseconds cho mọi loại thời gian

Có thể lưu một `Instant` thành `long epochMillis` trong chiến lược được quy định rõ. Nhưng `LocalDate` là "ngày trên lịch", `LocalTime` là "giờ đồng hồ", không nên biến cả hai thành epoch khi chưa có ngày/vùng; làm thế buộc phải bịa thêm thông tin và dễ lệch ngày. Epoch milliseconds còn mất phần nano nhỏ hơn milli.

## 9. Chuyển đổi từ kiểu JDBC cũ

Các API cũ gồm `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp`. Nếu gặp legacy code, có các phép chuyển tường minh:

```java
LocalDate day = sqlDate.toLocalDate();             // DATE
LocalTime time = sqlTime.toLocalTime();             // TIME
LocalDateTime local = sqlTimestamp.toLocalDateTime(); // TIMESTAMP local
```

Đây là các phép chuyển tương ứng với **giá trị/kiểu SQL đã hiểu rõ**, không phải bằng chứng mọi `Timestamp` tương đương `Instant` trong mọi database. `java.sql.Timestamp` có thể mang cách diễn giải timezone qua driver/session khi đọc `TIMESTAMP WITHOUT TIME ZONE`; chuyển mù `getTimestamp(...).toInstant()` dễ biến một giá trị địa phương thành thời điểm sai.

Với driver hiện đại hỗ trợ JDBC 4.2, ưu tiên `setObject` và `getObject(..., Class)` cho các lớp `java.time` tương ứng. Nếu driver cũ thiếu hỗ trợ, dùng adapter `Date.valueOf(LocalDate)`, `Time.valueOf(LocalTime)`, `Timestamp.valueOf(LocalDateTime)` sau khi kiểm chứng precision và timezone. Với sự kiện tuyệt đối, định nghĩa chính sách UTC/driver cụ thể thay vì áp dụng một phép cast chung.

Không phụ thuộc `TimeZone.setDefault(...)` toàn JVM để "sửa" lỗi cột; thao tác này ảnh hưởng nhiều thư viện và có thể gây lỗi khi hệ thống có nhiều vùng người dùng. Sửa tại mô hình nghiệp vụ, ánh xạ cột, cấu hình connection/session hoặc quy trình chuyển đổi cụ thể.

## 10. Các lỗi thường gặp và dấu hiệu nhận biết

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Lưu `LocalDate` bằng `Instant` đặt 00:00 UTC | Người dùng ở vùng âm có thể thấy ngày trước | Dùng `DATE` và `LocalDate` cho ngày dân sự |
| Lưu giờ mở cửa bằng `TIMESTAMP` tùy ý gắn ngày 1970 | Phát sinh ngày giả và lệch vùng khi chuyển đổi | Dùng `TIME` / `LocalTime`, thêm vùng khi tính lần xảy ra thực tế |
| Dùng `LocalDateTime` cho `created_at` đa vùng mà không có quy ước | Không biết sự kiện xảy ra lúc nào trên timeline | Dùng `Instant` ở domain; cột/layer JDBC có chiến lược instant rõ ràng |
| Xem `TIMESTAMP WITHOUT TIME ZONE` là UTC mặc định | Dữ liệu đọc sai khi session/app đổi timezone | Kiểm tra DDL và chiến lược encode/decode, migrate có chủ đích |
| Gọi `setObject(Instant)` trên driver không hỗ trợ | Driver ném `SQLException` / Spring `DataAccessException` | Dùng `OffsetDateTime` hoặc adapter của driver/DB đã kiểm chứng |
| Đọc `TIMESTAMP WITH TIME ZONE` thành `LocalDateTime` | Bỏ ý nghĩa offset/instant, có thể đổi giờ | Đọc `OffsetDateTime`, chuyển `toInstant()` |
| Nghĩ `TIMESTAMP WITH TIME ZONE` lưu tên vùng `Europe/Paris` | Không khôi phục được vùng và lịch DST gốc | Lưu `ZoneId` ở cột riêng khi nghiệp vụ cần |
| So `OffsetDateTime.equals` khi DB chuẩn hóa về UTC | Cùng `Instant` vẫn có thể bị đánh giá khác | So `toInstant()` cho ngữ nghĩa thời điểm |
| Không xử lý DST gap/overlap cho lịch hẹn tương lai | Giờ không có thật hoặc có hai cách diễn giải | Quy định chính sách vùng/offset khi chuyển `LocalDateTime` |
| So thời gian đến nano với cột chỉ lưu micro/millisecond | Test sai dù DB xử lý đúng precision | Thiết kế test theo độ chính xác thực tế |
| Dùng `LocalDateTime.now()` cho audit | Phụ thuộc timezone mặc định của máy | Dùng `Instant.now(clock)` và chiến lược lưu UTC |

### Ví dụ phân biệt lỗi thực tế

**Tình huống:** người dùng chọn ngày sinh 01/01/2000. Backend biến ngày này thành `2000-01-01T00:00:00Z` rồi lưu như thời điểm tuyệt đối. Một client ở vùng `UTC-08:00` hiển thị `1999-12-31 16:00` và lấy phần ngày là 31/12/1999. Sai lầm nằm ở việc **biến ngày dân sự thành một khoảnh khắc** không thuộc nghiệp vụ. Giải pháp là lưu `DATE` và truyền `LocalDate`; timezone không phải phần của giá trị ngày sinh.

**Tình huống khác:** cuộc họp 16:00 giờ Paris vào một ngày mùa hè. Nếu chỉ lưu `2026-07-15T16:00` rồi backend gán nhầm `UTC`, cuộc họp thực tế bị dịch hai giờ. Giải pháp lưu/biết `Europe/Paris`, giải quyết DST rồi chuyển thành `Instant` theo đúng thời điểm khi cần gửi thông báo.

## 11. Checklist kiểm thử tích hợp

Với mỗi cột thời gian, kiểm tra cả **ý nghĩa nghiệp vụ** và **round-trip dữ liệu** qua đúng driver/DB đích:

1. **`DATE`/`LocalDate`:** ghi ngày cố định, đọc lại cùng ngày, đổi JVM/session timezone không làm thay đổi ngày dân sự trong contract mong muốn.
2. **`TIME`/`LocalTime`:** ghi 09:00, đọc 09:00; kiểm tra phần giây/nano nếu cột hỗ trợ và lịch chạy qua 0 giờ khi ứng dụng có tính năng đó.
3. **`TIMESTAMP`/`LocalDateTime`:** ghi 16:00, đọc 16:00 với đúng schema; không tự trừ/bù timezone khi đây là local wall-time.
4. **`TIMESTAMP WITH TIME ZONE`/`Instant`:** bind `OffsetDateTime` từ `Instant`, đọc thành `OffsetDateTime` và so **`toInstant()`**; thử offset khác nhau nhưng cùng thời điểm.
5. **Timezone:** đọc/ghi khi JVM và connection/session có cấu hình timezone khác nhau; với DB có quy tắc riêng, kiểm tra thực nghiệm.
6. **DST:** thử một thời điểm trong gap và một thời điểm overlap của vùng có DST; áp dụng chính sách đã công bố.
7. **NULL:** thử cột nullable, bảo đảm không phát sinh `NullPointerException` và không thay `NULL` bằng epoch.
8. **Precision:** ghi một thời điểm có phần nano; xác nhận rounding/truncation đúng mức `TIMESTAMP(p)`.
9. **Portability:** test với phiên bản driver/database production; H2 dùng trong ví dụ không chứng minh mọi vendor giống nhau.
10. **JSON/API:** xác nhận `LocalDate` được truyền như chuỗi ngày (ví dụ `2026-07-15`) và `Instant` có offset/UTC rõ (ví dụ `2026-07-15T02:30:00Z`); không gộp chúng thành cùng một dạng chuỗi tùy tiện.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Cột lưu ngày chốt kỳ tài chính `2026-07-31` và phải luôn là 31/7 dù người dùng ở đâu. Chọn gì?

**Trả lời:** `LocalDate` ở Java, `DATE` trong SQL. Nếu ranh giới kỳ được xác định bởi một vùng cụ thể, vùng đó được sử dụng khi **tính ngày**, không biến giá trị ngày đã xác định thành `Instant`.

**Câu 2.** Cột lưu "giao hàng lúc 16:00 tại Paris ngày 15/7/2026". Chỉ có `LocalDateTime` đã xác định được `Instant` chưa?

**Trả lời:** Chưa. Phải biết `ZoneId`, chẳng hạn `Europe/Paris`. Ngày này Paris theo `UTC+02:00`, nên `16:00` địa phương tương ứng `14:00Z`.

**Câu 3.** Cột `processed_at` lưu sự kiện xảy ra thực tế. Ứng dụng dùng PostgreSQL. Nên đưa loại Java nào qua JDBC?

**Trả lời:** Domain nên dùng `Instant`; tại JDBC boundary dùng `OffsetDateTime` (thường ở `ZoneOffset.UTC`) cho cột `TIMESTAMP WITH TIME ZONE`. Đọc `OffsetDateTime` rồi `toInstant()`. Không giả định pgJDBC hỗ trợ `getObject(..., Instant.class)`.

**Câu 4.** Hai `OffsetDateTime` `2026-07-15T09:30+07:00` và `2026-07-15T02:30Z` có phải cùng một thời điểm?

**Trả lời:** Có, vì cùng `Instant`. Hai đối tượng không bắt buộc bằng nhau theo `OffsetDateTime.equals` do offset và trường ngày giờ địa phương khác nhau.

**Câu 5.** Lịch lặp mỗi ngày 09:00 ở một thành phố có DST, chỉ lưu `LocalTime` đủ chưa?

**Trả lời:** Chưa đủ để tính lịch kích hoạt trên timeline. Cần cả ngày áp dụng, tên vùng `ZoneId` và chính sách khi thời điểm địa phương rơi vào gap/overlap.

## 13. Kết luận

Hãy đọc "ý nghĩa cột" trước khi chọn kiểu:

- `DATE` ↔ `LocalDate`: **ngày** trên lịch.
- `TIME` ↔ `LocalTime`: **giờ** trong một ngày.
- `TIMESTAMP WITHOUT TIME ZONE` ↔ `LocalDateTime`: **ngày + giờ địa phương**, không phải một điểm thời gian duy nhất.
- **Thời điểm tuyệt đối** ↔ `Instant` ở domain; khi dùng JDBC 4.2 với cột `TIMESTAMP WITH TIME ZONE`, thường chuyển qua `OffsetDateTime` để ghi/đọc và về `Instant`.

Thành công của JDBC call mới chứng minh câu SQL chạy được. Tính đúng đắn của dữ liệu thời gian còn cần kiểm tra **múi giờ, DST, loại SQL của vendor, precision, NULL và khả năng JDBC driver**. Đúng kiểu theo ngữ nghĩa sẽ giúp bản ghi không bị đổi ngày, đổi giờ hoặc mất bối cảnh khi ứng dụng mở rộng ra nhiều vùng.

### Nguồn tham khảo

- [Spring Framework — JDBC core và `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- [Java 17 — `java.time` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html).
- [JDBC 4.2 Specification — ánh xạ Java time và SQL types](https://download.oracle.com/otndocs/jcp/jdbc-4_2-mrel2-spec/index.html).
- [H2 Database — Data Types](https://h2database.com/html/datatypes.html).
- [PostgreSQL JDBC — Java 8 Date and Time classes](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes).
