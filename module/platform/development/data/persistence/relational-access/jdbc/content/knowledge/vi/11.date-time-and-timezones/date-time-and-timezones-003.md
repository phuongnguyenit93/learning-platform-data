# Sử dụng LocalDate, LocalTime và LocalDateTime với JDBC

Khi phát triển ứng dụng Java kết nối cơ sở dữ liệu quan hệ, kiểu dữ liệu ngày giờ cần thể hiện **đúng ý nghĩa nghiệp vụ** trước khi lựa chọn cột SQL hoặc lời gọi JDBC. Một ngày giao hàng, giờ mở cửa và thời điểm bắt đầu cuộc hẹn có thể cùng hiển thị dạng ngày giờ, nhưng mang ý nghĩa khác nhau. Bộ API `java.time` giúp biểu diễn rõ các giá trị này; từ JDBC 4.2, các driver tương thích có thể nhận và trả trực tiếp `LocalDate`, `LocalTime` và `LocalDateTime` qua `PreparedStatement` và `ResultSet`.

Bài học tập trung vào ba kiểu giá trị **không chứa múi giờ** trong `java.time` và cách ánh xạ chúng vào cột `DATE`, `TIME`, `TIMESTAMP`. Sau bài học, bạn có thể:

- Chọn đúng kiểu Java và kiểu SQL cho ngày, giờ hoặc ngày giờ địa phương.
- Ghi/đọc giá trị bằng `setObject` / `getObject(..., Class)` trong JDBC 4.2.
- Dùng các phương thức chuyển đổi `java.sql.Date`, `Time`, `Timestamp` khi phải tương thích driver cũ.
- Tránh nhầm lẫn giữa giờ địa phương, múi giờ (`ZoneId`) và thời điểm tuyệt đối (`Instant`).
- Phát hiện vấn đề về `NULL`, độ chính xác phần giây, điều chỉnh múi giờ, ngày chuyển giờ mùa hè và tương thích hệ quản trị.

## 1. Chọn kiểu theo ý nghĩa dữ liệu

Ba lớp trong `java.time` mô tả ba khái niệm khác nhau:

| Dữ liệu nghiệp vụ | Kiểu Java | Kiểu SQL thường gặp | Ví dụ |
| --- | --- | --- | --- |
| Ngày lịch, không cần giờ | `LocalDate` | `DATE` | Ngày giao hàng: `2026-11-17` |
| Giờ trong ngày, không cần ngày | `LocalTime` | `TIME` hoặc `TIME WITHOUT TIME ZONE` | Giờ mở cửa: `09:30:00` |
| Ngày và giờ theo lịch địa phương | `LocalDateTime` | `TIMESTAMP` hoặc `TIMESTAMP WITHOUT TIME ZONE` | Lịch hẹn: `2026-11-17T09:30:00` |

`LocalDate` **không có thời gian trong ngày**. `LocalTime` **không có ngày**. `LocalDateTime` chứa cả hai, nhưng **không có múi giờ và không có độ lệch UTC**.

Điều này có nghĩa là:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDate day = LocalDate.of(2026, 11, 17);
LocalTime opening = LocalTime.of(9, 30);
LocalDateTime appointment = LocalDateTime.of(day, opening);

System.out.println(day);         // 2026-11-17
System.out.println(opening);     // 09:30
System.out.println(appointment); // 2026-11-17T09:30
~~~

Giá trị `appointment` nói rằng lịch hẹn bắt đầu lúc 09:30 ngày 17/11/2026 theo một lịch địa phương, nhưng tự nó **không trả lời được** “09:30 ở thành phố hoặc múi giờ nào?” và “thời điểm tương ứng theo UTC là khi nào?”.

**Không suy từ chữ “timestamp” rằng giá trị luôn là UTC.** `LocalDateTime` thích hợp với `TIMESTAMP WITHOUT TIME ZONE` khi nghiệp vụ cần giữ nguyên các trường ngày giờ trên đồng hồ, còn việc biểu diễn một thời điểm tuyệt đối đòi hỏi chính sách khác.

## 2. Tạo và thao tác với các giá trị `java.time`

Các lớp `LocalDate`, `LocalTime` và `LocalDateTime` là **immutable**: phương thức như `plusDays` hoặc `plusHours` trả về giá trị mới.

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

LocalDate checkInDay = LocalDate.parse("2026-11-17");
LocalTime checkInHour = LocalTime.parse("14:30:00");
LocalDateTime checkIn = LocalDateTime.of(checkInDay, checkInHour);

LocalDate checkOutDay = checkInDay.plusDays(2);
LocalDateTime reminder = checkIn.minusHours(1);

System.out.println(checkOutDay); // 2026-11-19
System.out.println(reminder);    // 2026-11-17T13:30

DateTimeFormatter displayFormat =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
System.out.println(checkIn.format(displayFormat)); // 17/11/2026 14:30
~~~

Nên phân biệt rõ **giá trị dữ liệu** và **chuỗi hiển thị**:

- `LocalDate.parse("2026-11-17")`, `LocalTime.parse("14:30:00")` và `LocalDateTime.parse("2026-11-17T14:30:00")` hiểu các định dạng ISO mặc định tương ứng.
- `DateTimeFormatter` dùng khi cần nhập/xuất một định dạng cụ thể.
- Khi lưu JDBC, truyền đối tượng `java.time` làm **tham số có kiểu** thay vì định dạng thành chuỗi ngày giờ rồi ghép vào SQL. Driver và cơ sở dữ liệu chịu trách nhiệm ánh xạ kiểu dữ liệu.
- Nếu chuỗi đầu vào có dấu cách giữa ngày và giờ thay vì ký tự `T`, hãy dùng formatter phù hợp hoặc parser của tầng nhập liệu; đừng giả định `LocalDateTime.parse` mặc định chấp nhận mọi định dạng SQL.

### Giá trị hiện tại phụ thuộc đồng hồ và múi giờ

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

LocalDate todayAtBranch = LocalDate.now(businessClock);
LocalDateTime localNowAtBranch = LocalDateTime.now(businessClock);
~~~

Ví dụ này tạo ngày và giờ theo múi giờ kinh doanh. Kết quả `LocalDateTime` **chỉ giữ ngày và giờ**, không lưu lại `ZoneId` đã dùng. Nếu cần tái tạo thời điểm chính xác sau này, phải lưu thêm múi giờ hoặc một biểu diễn thời điểm tuyệt đối phù hợp.

## 3. Ánh xạ Java Time sang SQL qua JDBC 4.2

Đây là ánh xạ thông dụng khi dùng SQL temporal types **không có múi giờ**:

~~~mermaid
flowchart LR
    LD["LocalDate"] --> SET["PreparedStatement.setObject"]
    LT["LocalTime"] --> SET
    LDT["LocalDateTime"] --> SET
    SET --> DB["SQL DATE / TIME / TIMESTAMP"]
    DB --> GET["ResultSet.getObject(..., Class)"]
    GET --> LD2["LocalDate"]
    GET --> LT2["LocalTime"]
    GET --> LDT2["LocalDateTime"]
~~~

Từ JDBC 4.2, ứng dụng có thể truyền trực tiếp các đối tượng hiện đại:

~~~java
LocalDate serviceDate = LocalDate.of(2026, 11, 17);
LocalTime openingTime = LocalTime.of(9, 30);
LocalDateTime beginsAtLocal =
        LocalDateTime.of(2026, 11, 17, 10, 0);

String sql = """
    INSERT INTO service_windows
        (id, service_date, opening_time, begins_at_local)
    VALUES (?, ?, ?, ?)
    """;

// Trong dự án dùng Java 8–14, thay text block ở trên bằng chuỗi SQL thường.
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setObject(2, serviceDate);
    ps.setObject(3, openingTime);
    ps.setObject(4, beginsAtLocal);
    ps.executeUpdate();
}
~~~

**Lưu ý về phiên bản Java:** Text block `"""..."""` là cú pháp Java 15 trở lên; phần thao tác JDBC trong ví dụ vẫn dùng được với Java 8 trở lên khi thay câu SQL thành chuỗi thường.

`setObject` cho driver biết giá trị Java để ánh xạ sang kiểu SQL tương ứng. Nếu cần xác định kiểu SQL rõ ràng, có thể dùng overload nhận `SQLType` hoặc `int` SQL type, chẳng hạn `ps.setObject(2, serviceDate, java.sql.JDBCType.DATE)`, trên driver có hỗ trợ; tính tương thích thực tế cần kiểm tra theo driver. Ở luồng thường gặp, việc khai báo chính xác kiểu cột và truyền `java.time` tương ứng là đủ.

Để tránh mọi mơ hồ về cách ứng dụng lập trình và truy cập dữ liệu, phần tiếp theo dùng một ví dụ đầy đủ hơn với `DataSource`, `PreparedStatement` và `ResultSet`.

## 4. Ví dụ CRUD tối thiểu với `DataSource`

Giả sử hệ thống dịch vụ cần lưu ngày hoạt động, giờ mở cửa và thời điểm bắt đầu một lượt phục vụ theo đồng hồ địa phương của chi nhánh.

### 4.1. Lược đồ cơ sở dữ liệu

~~~sql
CREATE TABLE service_windows (
    id BIGINT PRIMARY KEY,
    service_date DATE NOT NULL,
    opening_time TIME NOT NULL,
    begins_at_local TIMESTAMP NOT NULL
);
~~~

Trong mô hình này, `begins_at_local` chỉ là **giờ tường** (`wall-clock time`) của chi nhánh. Ứng dụng phải biết múi giờ chi nhánh từ cấu hình hoặc một cột riêng nếu cần chuyển sang thời điểm tuyệt đối. Cú pháp cụ thể và ý nghĩa của `TIMESTAMP` có thể khác theo hệ quản trị; ví dụ này giả định cột `TIMESTAMP` giữ ngày giờ **không kèm múi giờ**.

### 4.2. Repository sử dụng JDBC

Đoạn mã sau tương thích cú pháp Java 8+, với điều kiện driver hỗ trợ ánh xạ `java.time` của JDBC 4.2:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class ServiceWindowRepository {
    private final DataSource dataSource;

    public ServiceWindowRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insert(
            long id,
            LocalDate serviceDate,
            LocalTime openingTime,
            LocalDateTime beginsAtLocal) throws SQLException {

        Objects.requireNonNull(serviceDate, "serviceDate");
        Objects.requireNonNull(openingTime, "openingTime");
        Objects.requireNonNull(beginsAtLocal, "beginsAtLocal");

        String sql = "INSERT INTO service_windows "
                + "(id, service_date, opening_time, begins_at_local) "
                + "VALUES (?, ?, ?, ?)";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setObject(2, serviceDate);
            ps.setObject(3, openingTime);
            ps.setObject(4, beginsAtLocal);
            ps.executeUpdate();
        }
    }

    public Optional<LocalDateTime> findStart(long id)
            throws SQLException {
        String sql = "SELECT begins_at_local "
                + "FROM service_windows WHERE id = ?";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không tìm thấy dòng.
                }

                LocalDateTime result =
                        rs.getObject("begins_at_local",
                                     LocalDateTime.class);
                if (result == null) {
                    // Lược đồ có NOT NULL; đây là dữ liệu không hợp lệ.
                    throw new SQLException(
                            "begins_at_local unexpectedly NULL");
                }
                return Optional.of(result);
            }
        }
    }
}
~~~

Ví dụ sử dụng khi ứng dụng đã cấu hình `DataSource` và bảng `service_windows`:

~~~java
ServiceWindowRepository repo =
        new ServiceWindowRepository(dataSource);

LocalDate day = LocalDate.of(2026, 11, 17);
LocalTime open = LocalTime.of(9, 0);
LocalDateTime start = LocalDateTime.of(2026, 11, 17, 9, 30);

repo.insert(101L, day, open, start);

LocalDateTime loaded = repo.findStart(101L)
        .orElseThrow(() -> new IllegalStateException("Không tìm thấy"));

System.out.println(start.equals(loaded)); // Dự kiến: true
~~~

Tùy loại SQL, precision của cột và driver, phần nano giây có thể được làm tròn hoặc cắt bớt. Kỳ vọng `equals` ở trên phù hợp với ví dụ chỉ dùng phút; không nên suy ra mọi cột `TIMESTAMP` đều giữ nguyên nano giây.

Các đặc điểm kỹ thuật quan trọng:

1. **Tham số bắt đầu từ 1.** Cột thứ hai trong `INSERT` nhận `ps.setObject(2, serviceDate)`.
2. **`PreparedStatement` hỗ trợ tham số hóa.** Không ghép ngày giờ trực tiếp thành chuỗi SQL, tránh lỗi định dạng, locale, ký tự SQL và rủi ro SQL injection.
3. **`ResultSet.getObject(column, LocalDateTime.class)`** lấy dữ liệu thành kiểu Java mong muốn; tương tự dùng `LocalDate.class` và `LocalTime.class` cho `DATE` và `TIME`.
4. **`try-with-resources`** đóng `ResultSet`, `PreparedStatement` và `Connection`, kể cả khi có ngoại lệ.
5. **Không có chuyển đổi múi giờ trong `LocalDateTime`.** Chỉ đọc/ghi ngày và giờ tương ứng với ý nghĩa cột; driver hoặc hệ quản trị có thể áp dụng chính sách riêng cho một số loại cột và kết nối.
6. Khi dùng nhiều thao tác ghi phải thành công cùng nhau, dùng `Connection.setAutoCommit(false)` và `commit()/rollback()`; cách ánh xạ kiểu ngày giờ không thay thế quản lý transaction.

### 4.3. Đọc đủ ba trường

~~~java
String sql = "SELECT service_date, opening_time, begins_at_local "
           + "FROM service_windows WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            LocalDate date =
                    rs.getObject("service_date", LocalDate.class);
            LocalTime time =
                    rs.getObject("opening_time", LocalTime.class);
            LocalDateTime dateTime =
                    rs.getObject("begins_at_local",
                                 LocalDateTime.class);

            // Xử lý các giá trị theo nghiệp vụ.
        }
    }
}
~~~

`getObject` trả về `null` nếu giá trị SQL là `NULL`. Với cột `NOT NULL`, việc nhận null thường chỉ ra dữ liệu hoặc ánh xạ bất thường. Với cột được phép `NULL`, cần chủ động mô hình hóa ý nghĩa của nó, chẳng hạn “chưa đặt giờ hẹn”.

### 4.4. Ghi `NULL` theo kiểu SQL

Đối với cột cho phép thiếu ngày giờ:

~~~java
import java.sql.Types;

if (cancelledAtLocal == null) {
    ps.setNull(2, Types.TIMESTAMP);
} else {
    ps.setObject(2, cancelledAtLocal);
}
~~~

Đây là ví dụ riêng cho một câu `PreparedStatement` có tham số số 2 tương ứng cột `TIMESTAMP` nullable. Tương tự, `Types.DATE` hoặc `Types.TIME` dành cho cột tương ứng. Gán kiểu rõ khi truyền null giúp giảm mơ hồ ở các driver hoặc câu SQL cần suy luận kiểu dữ liệu.

## 5. Tương thích với các API JDBC kiểu cũ

Một số hệ thống hoặc driver cũ vẫn sử dụng `java.sql.Date`, `java.sql.Time` và `java.sql.Timestamp`. Các lớp này có phương thức chuyển đổi với `java.time`, nhưng phải chú ý ý nghĩa và độ chính xác:

| Kiểu hiện đại | Kiểu `java.sql` tương ứng | Java → JDBC kiểu cũ | JDBC kiểu cũ → Java |
| --- | --- | --- | --- |
| `LocalDate` | `java.sql.Date` | `Date.valueOf(localDate)` | `date.toLocalDate()` |
| `LocalTime` | `java.sql.Time` | `Time.valueOf(localTime)` | `time.toLocalTime()` |
| `LocalDateTime` | `java.sql.Timestamp` | `Timestamp.valueOf(localDateTime)` | `timestamp.toLocalDateTime()` |

~~~java
import java.sql.Date;
import java.sql.Time;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDate day = LocalDate.of(2026, 11, 17);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime dateTime = LocalDateTime.of(2026, 11, 17, 9, 30);

ps.setDate(1, Date.valueOf(day));
ps.setTime(2, Time.valueOf(time));
ps.setTimestamp(3, Timestamp.valueOf(dateTime));

// Sau khi thực thi truy vấn:
Date sqlDate = rs.getDate("service_date");
Time sqlTime = rs.getTime("opening_time");
Timestamp sqlTimestamp = rs.getTimestamp("begins_at_local");

LocalDate readDay = sqlDate == null ? null : sqlDate.toLocalDate();
LocalTime readTime = sqlTime == null ? null : sqlTime.toLocalTime();
LocalDateTime readDateTime =
        sqlTimestamp == null ? null : sqlTimestamp.toLocalDateTime();
~~~

Lưu ý:

- `java.sql.Date`, `Time` và `Timestamp` là các kiểu API cũ có lịch sử kế thừa cơ chế mốc thời gian của `java.util.Date`. Việc chuyển đổi qua múi giờ mặc định, `Calendar` hay cấu hình driver có thể dẫn tới hành vi không như mong đợi.
- `java.sql.Time` có thể làm mất độ chính xác phần giây nếu dùng các phương thức chuyển đổi kiểu cũ; trong khi `LocalTime` có thể giữ tới nano giây. Nếu cần độ chính xác phần lẻ giây, ưu tiên ánh xạ trực tiếp với driver JDBC 4.2 và kiểm thử cột `TIME` thực tế.
- `Timestamp` có thể mang phần nano giây, nhưng precision được lưu vẫn phụ thuộc hệ quản trị và định nghĩa cột.
- Sử dụng `LocalDate`, `LocalTime` và `LocalDateTime` trực tiếp sẽ giúp code nghiệp vụ rõ ràng hơn. Chỉ dùng các kiểu cũ ở ranh giới tương thích khi cần.

**Đừng chuyển `LocalDateTime` sang `java.util.Date` hoặc `Instant` một cách tùy tiện.** Bước chuyển đó cần một `ZoneId` hoặc `ZoneOffset` để xác định chính xác thời điểm.

## 6. Múi giờ: ba kiểu `Local*` không mang thông tin vùng

Ví dụ hai cửa hàng có lịch “mở cửa lúc 09:00”:

- Chi nhánh tại `Asia/Ho_Chi_Minh` mở cửa 09:00 giờ địa phương.
- Chi nhánh tại `Europe/Paris` cũng mở cửa 09:00 giờ địa phương.

Một `LocalTime.of(9, 0)` có thể lưu **quy tắc mở cửa theo giờ địa phương** của cả hai. Nhưng cùng giờ trên đồng hồ không có nghĩa cả hai bắt đầu làm việc tại cùng một thời điểm toàn cầu.

| Kiểu | Có ngày? | Có giờ? | Có độ lệch/múi giờ? | Xác định được một instant? |
| --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Không |
| `LocalTime` | Không | Có | Không | Không |
| `LocalDateTime` | Có | Có | Không | Không |
| `OffsetDateTime` | Có | Có | Độ lệch UTC | Có |
| `ZonedDateTime` | Có | Có | `ZoneId` và offset | Có |
| `Instant` | Biểu diễn thời điểm UTC | Có | Mốc UTC | Có |

`ZonedDateTime` giữ cả quy tắc múi giờ (`ZoneId`). `OffsetDateTime` giữ độ lệch tại một thời điểm nhưng không đủ để biểu diễn mọi quy tắc chuyển giờ lịch sử/tương lai của một vùng. `Instant` biểu diễn một thời điểm duy nhất trên trục thời gian.

### Chuyển ngày giờ địa phương sang thời điểm tuyệt đối

Nếu ứng dụng có `LocalDateTime` từ lịch chi nhánh và biết `ZoneId` tương ứng:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime localStart =
        LocalDateTime.of(2026, 11, 17, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zonedStart = localStart.atZone(zone);
Instant instant = zonedStart.toInstant();

System.out.println(instant); // 2026-11-17T02:30:00Z
~~~

Đây là ví dụ với một ngày giờ bình thường ở Thành phố Hồ Chí Minh (UTC+07:00). Trong các múi giờ có chuyển giờ mùa hè, `atZone` có quy tắc mặc định để xử lý giờ không tồn tại hoặc bị lặp lại. Nếu nghiệp vụ yêu cầu một thời điểm xác định duy nhất, nên **kiểm tra giờ hợp lệ trước khi chuyển**.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime candidate =
        LocalDateTime.of(2026, 3, 29, 2, 30);

List<ZoneOffset> offsets =
        paris.getRules().getValidOffsets(candidate);

if (offsets.isEmpty()) {
    System.out.println("Giờ không tồn tại do chuyển giờ mùa hè");
} else if (offsets.size() > 1) {
    System.out.println("Giờ mơ hồ: có nhiều offset hợp lệ");
} else {
    ZonedDateTime resolved =
            ZonedDateTime.ofLocal(candidate, paris, offsets.get(0));
    System.out.println(resolved.toInstant());
}
~~~

Ví dụ tại Paris, ngày **29/03/2026 lúc 02:30** không tồn tại khi chuyển sang giờ mùa hè; ngày **25/10/2026 lúc 02:30** xảy ra hai lần do chuyển về giờ chuẩn. Vì vậy, `LocalDateTime` một mình không đủ để bảo đảm một cuộc hẹn hoặc sự kiện tương ứng với đúng một thời điểm.

### Thiết kế dữ liệu theo mục đích

- **Ngày sinh, ngày đến hạn theo lịch:** dùng `LocalDate` + `DATE`.
- **Giờ mở cửa hằng ngày:** dùng `LocalTime` + `TIME`; lưu `ZoneId` cho chi nhánh ở nơi khác nếu cần gắn với thời điểm thực.
- **Lịch hẹn địa phương:** dùng `LocalDateTime` + `ZoneId` (thường dưới dạng chuỗi IANA như `Asia/Ho_Chi_Minh`) nếu cần quy đổi sang `Instant`. Xác định chính sách cho các giờ bị lặp/không tồn tại.
- **Thời điểm tạo bản ghi hoặc thực hiện giao dịch:** ưu tiên mô hình thời điểm tuyệt đối, chẳng hạn `Instant` hoặc `OffsetDateTime` cùng kiểu SQL và chính sách UTC thích hợp với hệ quản trị. Không mặc định rằng `LocalDateTime` lưu trong một cột `TIMESTAMP` sẽ tự động chính xác theo UTC.

Các hệ quản trị có khác biệt đáng kể. Ví dụ, `TIMESTAMP WITHOUT TIME ZONE` và `TIMESTAMP WITH TIME ZONE` là hai khái niệm SQL khác nhau; một số hệ quản trị dùng tên kiểu `TIMESTAMP` với hành vi hoặc cơ chế chuyển đổi theo múi giờ phiên làm việc riêng. Hãy kiểm tra tài liệu và thử nghiệm trên **đúng cơ sở dữ liệu, driver và cấu hình kết nối** mà ứng dụng sử dụng.

## 7. Các bẫy khi đọc và ghi ngày giờ

### 7.1. Độ chính xác của phần giây

`LocalTime` và `LocalDateTime` hỗ trợ độ chính xác tới **nano giây**, nhưng cột SQL, driver hoặc cơ sở dữ liệu có thể chỉ hỗ trợ mili giây hay micro giây.

~~~java
LocalTime preciseTime =
        LocalTime.of(9, 30, 15, 123_456_789);

LocalDateTime preciseDateTime =
        LocalDateTime.of(2026, 11, 17, 9, 30, 15, 123_456_789);
~~~

Một cột `TIME(3)` có thể chỉ giữ đến mili giây; `TIMESTAMP(6)` có thể giữ đến micro giây nếu hệ quản trị hỗ trợ cú pháp và precision đó. Khi ghi `123456789` nano giây vào cột có độ phân giải thấp hơn, driver/cơ sở dữ liệu có thể cắt, làm tròn hoặc từ chối. Chính sách chuẩn hóa nên được xác định rõ cho ứng dụng.

Ví dụ, để bỏ phần nano giây dưới mức micro giây ngay trong Java:

~~~java
import java.time.temporal.ChronoUnit;

LocalDateTime normalized =
        preciseDateTime.truncatedTo(ChronoUnit.MICROS);
// 2026-11-17T09:30:15.123456
~~~

Đây là **phép cắt**, không phải phép làm tròn. Nếu nghiệp vụ đòi hỏi làm tròn, hãy thiết kế quy tắc phù hợp, và kiểm thử ở thời điểm vượt sang giây/phút/ngày mới.

### 7.2. `LocalDateTime` và múi giờ của JVM/phiên SQL

Về mặt miền dữ liệu, `LocalDateTime` không chứa múi giờ. Tuy nhiên, ứng dụng có thể vô tình làm biến đổi giá trị khi chuyển sang `Timestamp`, khi cột SQL áp dụng chuyển đổi múi giờ, hoặc khi driver dùng múi giờ JVM/phiên kết nối.

Để hạn chế lỗi:

1. Chọn kiểu cột thể hiện đúng ý nghĩa (không múi giờ hoặc thời điểm tuyệt đối).
2. Ưu tiên `setObject` / `getObject(..., Class)` với JDBC 4.2 khi driver hỗ trợ.
3. Cấu hình múi giờ JVM và kết nối một cách nhất quán nếu driver/hệ quản trị cần.
4. Viết kiểm thử thực tế khi chạy với **hai múi giờ JVM hoặc phiên SQL khác nhau**, đặc biệt quanh ngày đổi giờ mùa hè.
5. Kiểm tra các thiết lập chuyên biệt của driver/hệ quản trị thay vì giả định tất cả JDBC driver diễn giải `TIMESTAMP` giống nhau.

### 7.3. Định dạng, locale và câu SQL

Không lưu ngày giờ bằng chuỗi đã định dạng theo địa phương như `17/11/2026 09:30` trong cột văn bản nếu cần truy vấn khoảng ngày, sắp xếp hoặc ràng buộc thời gian. Cũng không viết:

~~~java
// Không nên: dễ lỗi định dạng hoặc tiêm SQL.
String unsafe = "SELECT * FROM service_windows "
        + "WHERE service_date = '" + userInput + "'";
~~~

Thay bằng:

~~~java
LocalDate date = LocalDate.parse(userInput); // Ví dụ đầu vào ISO.
String sql = "SELECT * FROM service_windows "
        + "WHERE service_date = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, date);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

Với yêu cầu tìm toàn bộ bản ghi trong một ngày, dùng `DATE` khi nghiệp vụ thực sự lưu ngày. Nếu dùng cột biểu diễn thời điểm tuyệt đối, cần chuyển **hai ranh giới của ngày theo múi giờ kinh doanh** thành một khoảng thời gian phù hợp; không tùy tiện cắt phần ngày theo múi giờ JVM.

### 7.4. Dữ liệu lịch sử và phạm vi ngày

`LocalDate` sử dụng lịch ISO-8601 theo cách biểu diễn lịch Gregory kéo dài về quá khứ (`proleptic Gregorian`). Cơ sở dữ liệu có thể áp dụng giới hạn phạm vi, cách hiển thị hoặc quy tắc lịch sử khác. Với ngày rất xa trong quá khứ hoặc tương lai, hãy kiểm tra khả năng đọc/ghi qua driver và hệ quản trị. Không giả định mọi giá trị hợp lệ của `LocalDate` đều lưu được trong mọi cột `DATE`.

## 8. Kiểm chứng một luồng JDBC ngày giờ

Một bài kiểm thử tích hợp nên dùng đúng **database và driver của ứng dụng**, tạo bảng với `DATE`, `TIME`, `TIMESTAMP` rồi thực hiện ít nhất các trường hợp sau:

| Trường hợp | Giá trị kiểm thử | Điều cần xác minh |
| --- | --- | --- |
| Ngày lịch | `2026-11-17` | `LocalDate` đọc về cùng ngày |
| Giờ trong ngày | `09:30:00` | `LocalTime` không bị đổi giờ |
| Ngày giờ địa phương | `2026-11-17T09:30:00` | `LocalDateTime` giữ đúng trường ngày và giờ |
| Phần giây | `09:30:15.123456789` | Precision lưu được; có cắt/làm tròn không |
| `NULL` ở cột nullable | `null` | `getObject` trả null và ứng dụng xử lý hợp lệ |
| Ngày đổi giờ mùa hè | Paris `2026-03-29T02:30` và `2026-10-25T02:30` | Phát hiện giờ không tồn tại hoặc giờ lặp nếu chuyển sang `Instant` |
| Múi giờ khác nhau | Chạy với cấu hình JVM/DB khác nhau | Không dịch lệch giá trị ngày giờ địa phương ngoài ý muốn |

Khi so sánh kết quả vòng đi-vòng về (`round trip`), dùng `equals` khi cần giữ nguyên **tất cả trường** và đã chọn precision đủ đáp ứng; nếu quy tắc cho phép mất độ chính xác phần giây, chuẩn hóa dữ liệu đầu vào và đầu ra theo cùng độ phân giải trước khi so sánh. Đừng dùng `toString` làm tiêu chí chính cho việc đúng sai của kiểu dữ liệu.

### Câu hỏi tự luyện

1. Một cửa hàng mở cửa lúc `08:00` mỗi ngày. Nên chọn `LocalTime` hay `LocalDateTime`? Tại sao?
2. Giá trị `2026-11-17T09:30` lưu trong `LocalDateTime` có đủ để biết một `Instant` duy nhất không?
3. Ba cách gọi nào dùng để ghi `LocalDate`, `LocalTime`, `LocalDateTime` vào `PreparedStatement` bằng JDBC 4.2?
4. Khi đọc cột `DATE` về `LocalDate`, `ResultSet` cung cấp overload nào?
5. Vì sao phần nano giây của `LocalTime` có thể khác sau khi đọc lại từ cơ sở dữ liệu?
6. Với lịch hẹn lúc 02:30 ở Paris vào một ngày đổi giờ mùa hè, ứng dụng cần kiểm tra thông tin nào trước khi tạo `Instant`?

**Gợi ý đáp án:** (1) `LocalTime` vì đây là quy tắc giờ trong ngày; (2) không, cần biết `ZoneId` hoặc `ZoneOffset` và có thể cần xử lý giờ mơ hồ; (3) `setObject(index, value)` tương ứng từng kiểu; (4) `getObject(column, LocalDate.class)`; (5) precision của cột/driver có thể thấp hơn nano giây; (6) `ZoneId`, quy tắc offset hợp lệ và chính sách xử lý giờ không tồn tại hoặc bị lặp.

Sử dụng `LocalDate`, `LocalTime` và `LocalDateTime` với JDBC đúng cách bắt đầu từ việc **chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ**. Khi sử dụng `PreparedStatement` và `ResultSet` theo JDBC 4.2, bảo đảm schema SQL tương ứng và kiểm thử đầy đủ ranh giới múi giờ, ứng dụng Java có thể lưu trữ và truy vấn ngày giờ một cách rõ ràng, nhất quán.
