# JDBC getObject() và setObject() với java.time: kiểm tra khả năng của trình điều khiển

## 1. API có sẵn chưa bảo đảm mọi trình điều khiển thực hiện giống nhau

JDBC cho phép truyền nhiều giá trị `java.time` trực tiếp qua `PreparedStatement.setObject` và đọc theo kiểu bằng `ResultSet.getObject(column, Class<T>)`. Cách này giữ rõ ý nghĩa ngày, giờ địa phương hoặc thời điểm có độ lệch, thay vì tự chuyển mọi thứ thành chuỗi.

Tuy nhiên, kết quả phụ thuộc vào **kiểu Java + kiểu SQL + phiên bản trình điều khiển + hệ quản trị cơ sở dữ liệu + cấu hình kết nối**. Chương trình dùng JDK 21 không làm một trình điều khiển cũ tự hỗ trợ đầy đủ các ánh xạ JDBC 4.2.

Vì vậy, cần phân biệt ba tầng: chữ ký phương thức tồn tại trong JDK, trình điều khiển có triển khai phép chuyển đổi, và dữ liệu đi qua cột thật có giữ đúng ý nghĩa/độ chính xác hay không.

## 2. Chọn ánh xạ theo ý nghĩa dữ liệu

| Kiểu SQL theo hợp đồng JDBC | Kiểu Java phù hợp | Ý nghĩa cần giữ |
| --- | --- | --- |
| `DATE` | `LocalDate` | Ngày, không có giờ |
| `TIME` | `LocalTime` | Giờ địa phương, không có ngày |
| `TIMESTAMP` | `LocalDateTime` | Ngày giờ địa phương, không có độ lệch/múi giờ |
| `TIME_WITH_TIMEZONE` | `OffsetTime` | Giờ kèm độ lệch, nếu DB/driver hỗ trợ |
| `TIMESTAMP_WITH_TIMEZONE` | `OffsetDateTime` | Ngày giờ kèm độ lệch theo khả năng DB/driver |

Các cặp này dựa trên ánh xạ JDBC 4.2; không phải mọi DB đều có đủ năm kiểu với cùng ngữ nghĩa. [JDBC 4.2: ánh xạ java.time](https://jcp.org/aboutJava/communityprocess/maintenance/jsr221/JDBC4.2MR-January2014.pdf) `Instant`, `ZonedDateTime`, `YearMonth` hoặc `MonthDay` không có một ánh xạ trực tiếp phổ quát để mặc định truyền vào mọi `setObject`.

Ví dụ cụ thể: tài liệu pgJDBC liệt kê `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`; đồng thời nêu `Instant`, `ZonedDateTime` và `OffsetTime` không được hỗ trợ trực tiếp trong nhóm này. Đây là lý do cần đọc tài liệu của đúng driver thay vì chỉ nhìn danh sách kiểu trong Java. [pgJDBC: Java Time](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes)

Nếu cần lưu một thời điểm từ `Instant`, có thể chọn hợp đồng `OffsetDateTime` ở UTC khi DB/driver hỗ trợ. Nếu cần bảo toàn vùng như `Asia/Ho_Chi_Minh`, phải lưu định danh vùng riêng nếu kiểu SQL không giữ nó. Một độ lệch `+07:00` không tương đương với danh tính vùng.

## 3. Ghi bằng setObject: phân biệt các overload

Đoạn minh họa trong phương thức có sẵn `PreparedStatement ps`:

```java
LocalDate date = LocalDate.of(2024, 6, 15);
LocalDateTime local = LocalDateTime.of(2024, 6, 15, 12, 30);

ps.setObject(1, date);                      // Driver suy kiểu từ đối tượng.
ps.setObject(2, local, java.sql.Types.TIMESTAMP); // Chỉ rõ mã kiểu SQL.
```

Còn một overload nhận `SQLType`, ví dụ `JDBCType.TIMESTAMP`. Đây là chữ ký khác với overload nhận mã số `Types.TIMESTAMP`. Một driver có thể hỗ trợ đường gọi này nhưng chưa hỗ trợ đường gọi kia; triển khai mặc định của các overload nhận `SQLType` có thể ném `SQLFeatureNotSupportedException`.

Chỉ rõ kiểu SQL giúp tránh suy luận mơ hồ khi phép chuyển đổi được hỗ trợ; nó không ép driver thực hiện một ánh xạ bất kỳ mà driver chưa triển khai. Đừng coi việc thay `Types.TIMESTAMP` thành `JDBCType.TIMESTAMP` là một sửa lỗi luôn đúng. [PreparedStatement.setObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)

Với giá trị `null`, ưu tiên kiểu SQL rõ ràng:

```java
ps.setNull(1, java.sql.Types.DATE);
// Hoặc setObject có kiểu SQL khi đường gọi đó đã được kiểm chứng.
```

`setObject(index, null)` không kiểu có thể không đủ thông tin cho một số driver hoặc truy vấn. Chỉ số tham số JDBC bắt đầu từ 1.

## 4. Đọc theo kiểu mong muốn

Đoạn minh họa sau giả định `rs` đã được đưa đến một hàng hợp lệ bằng `rs.next()`:

```java
LocalDate date = rs.getObject("business_date", LocalDate.class);
LocalDateTime local = rs.getObject("scheduled_local", LocalDateTime.class);
OffsetDateTime occurred = rs.getObject("occurred_at", OffsetDateTime.class);
```

`getObject(column, LocalDate.class)` yêu cầu driver chuyển sang kiểu đã chọn nếu hỗ trợ. Nó khác với `(LocalDate) rs.getObject(column)`: lời gọi không có `Class` có thể trả một kiểu mặc định như `java.sql.Date`, rồi phép ép kiểu trong Java sẽ thất bại.

Với SQL `NULL`, getter kiểu đối tượng trả `null`; kiểm tra trước khi gọi phương thức trên kết quả. Không thay `NULL` bằng `LocalDate.MIN` hoặc thời điểm epoch nếu nghiệp vụ chưa quy định giá trị thay thế. [ResultSet.getObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)

## 5. Kiểm tra thông tin môi trường và bằng chứng hỗ trợ

`DatabaseMetaData` cung cấp tên/phiên bản driver, tên/phiên bản DB và phiên bản JDBC công bố. Các thông tin này giúp tái hiện lỗi và đối chiếu tài liệu. Tuy nhiên không có một cờ chung kiểu `supportsAllJavaTimeMappings()`.

`supportsConvert` và metadata kiểu SQL không phải bằng chứng đầy đủ rằng một cặp `getObject(column, SpecificClass.class)` hoặc một overload `setObject` cụ thể sẽ hoạt động. Cần thử đúng cặp chuyển đổi sẽ dùng. [DatabaseMetaData](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html)

Quy trình thực tế:

1. Chốt ý nghĩa cột và kiểu SQL trong schema.
2. Ghi nhận phiên bản driver/DB, cấu hình múi giờ và độ chính xác.
3. Đối chiếu tài liệu ánh xạ chính thức của driver.
4. Kiểm tra binding và đọc kiểu, rồi kiểm tra ghi/đọc qua cột thật.
5. Khẳng định đúng thuộc tính cần giữ: ngày/giờ địa phương, thời điểm, độ lệch hay tên vùng.

## 6. Chương trình probe cho PostgreSQL và pgJDBC

Chương trình sau cần **PostgreSQL đang chạy và JAR pgJDBC trên classpath**. Nó dùng truy vấn `SELECT` với tham số có kiểu SQL để kiểm tra binding và đọc lại; không tạo hoặc sửa bảng.

Dữ liệu có phần nano giây là bội của 1.000, phù hợp độ chính xác micro giây của PostgreSQL cho ví dụ. Với kiểu có độ lệch, kiểm tra bằng `toInstant()` để so sánh thời điểm; không yêu cầu cùng độ lệch ban đầu.

Lưu thành `JdbcTimeProbe.java`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Objects;

public class JdbcTimeProbe {
    static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = Objects.requireNonNull(
                System.getenv("JDBC_PASSWORD"), "JDBC_PASSWORD");
        LocalDate date = LocalDate.of(2024, 6, 15);
        LocalDateTime local = LocalDateTime.parse("2024-06-15T12:30:45.123456");
        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-15T12:30:45.123456+07:00");

        String sql = "SELECT CAST(? AS DATE) AS d, "
                + "CAST(? AS TIMESTAMP) AS l, "
                + "CAST(? AS TIMESTAMP WITH TIME ZONE) AS o, "
                + "CAST(? AS DATE) AS n";

        try (Connection connection = DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData meta = connection.getMetaData();
            System.out.println("driver=" + meta.getDriverName() + " "
                    + meta.getDriverVersion());
            System.out.println("database=" + meta.getDatabaseProductName() + " "
                    + meta.getDatabaseProductVersion());

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setObject(1, date);
                ps.setObject(2, local);
                ps.setObject(3, offset);
                ps.setNull(4, Types.DATE);
                try (ResultSet rs = ps.executeQuery()) {
                    check(rs.next(), "No result row");
                    LocalDate readDate = rs.getObject("d", LocalDate.class);
                    LocalDateTime readLocal = rs.getObject("l", LocalDateTime.class);
                    OffsetDateTime readOffset = rs.getObject("o", OffsetDateTime.class);
                    LocalDate readNull = rs.getObject("n", LocalDate.class);

                    check(date.equals(readDate), "DATE mismatch");
                    check(local.equals(readLocal), "TIMESTAMP mismatch");
                    check(readOffset != null
                            && offset.toInstant().equals(readOffset.toInstant()),
                            "TIMESTAMP WITH TIME ZONE instant mismatch");
                    check(readNull == null, "SQL NULL mismatch");
                    System.out.println("roundTrip=PASS");
                }
            }
        }
    }
}
```

Biên dịch chỉ cần JDK 17 trở lên:

```shell
javac --release 17 JdbcTimeProbe.java
```

Đặt `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD` bằng cấu hình môi trường thử nghiệm của bạn; không đưa mật khẩu vào mã nguồn. Với một JAR pgJDBC đã chọn và đổi tên thành `postgresql.jar`, chạy trên Windows:

```shell
java -cp ".;postgresql.jar" JdbcTimeProbe
```

Trên Linux/macOS, dấu phân cách classpath là `:` thay cho `;`. Driver JDBC hiện đại đăng ký qua cơ chế dịch vụ khi JAR có trên classpath; nếu thiếu JAR hoặc URL không khớp driver, kết nối có thể báo không tìm được driver phù hợp.

Tên/phiên bản ở hai dòng đầu thay đổi theo môi trường. Nếu mọi phép binding, chuyển đổi và so sánh đều thành công, dòng cuối là:

```text
roundTrip=PASS
```

Đó là điều kiện đạt của phép probe, không phải bằng chứng rằng mọi driver đều đạt. Để xác nhận lưu trữ của ứng dụng, bổ sung kiểm tra `INSERT`/đọc lại qua **đúng cột và độ chính xác của schema thật** trong cơ sở dữ liệu thử nghiệm. Truy vấn ép kiểu ở trên chưa kiểm tra constraint, trigger hoặc cấu hình cột.

## 7. Những mất mát không được phát hiện bằng so sánh sai tiêu chí

PostgreSQL chuẩn hóa dữ liệu `TIMESTAMP WITH TIME ZONE` theo thời điểm; pgJDBC mô tả kết quả `OffsetDateTime` với độ lệch UTC. Vì vậy, giá trị gửi có `+07:00` có thể đọc lại thành `Z` mà vẫn cùng thời điểm. So sánh `OffsetDateTime.equals` đòi cả thành phần địa phương và độ lệch giống nhau, trong khi `toInstant().equals(...)` kiểm tra cùng thời điểm.

Không suy ra `TIMESTAMP WITH TIME ZONE` luôn giữ chuỗi độ lệch ban đầu hoặc tên vùng ở mọi DB. Nếu đó là dữ liệu nghiệp vụ phải bảo toàn, thiết kế thêm cột riêng và kiểm tra riêng.

Ngược lại, một `LocalDateTime` dùng cho “09:00 giờ địa phương của cửa hàng” không được tự gắn UTC chỉ để qua driver. Nó chưa biểu diễn một thời điểm. Việc chọn múi giờ ở ranh giới chuyển đổi phải có quy tắc rõ ràng.

## 8. Phân biệt không hỗ trợ với lỗi khác

`SQLFeatureNotSupportedException` là dấu hiệu rõ rằng một tính năng/đường gọi không được triển khai. Một `SQLException` khác có thể đến từ sai kiểu cột, lỗi chuyển đổi, giới hạn dữ liệu, SQL sai hoặc kết nối; không được coi mọi `SQLException` đều là “driver không hỗ trợ java.time”.

Ghi nhận lớp ngoại lệ, `SQLState`, mã lỗi nhà cung cấp và chuỗi nguyên nhân cùng phiên bản môi trường. Không ghi mật khẩu hoặc URL chứa thông tin xác thực. Trình điều khiển cũ không tương thích nhị phân cần được nâng cấp, không giải quyết bằng việc ép kiểu kết quả.

Nếu phải dùng API cũ như `java.sql.Date.valueOf(localDate)` và `toLocalDate()`, hãy đặt chuyển đổi trong một adapter có kiểm tra. Với timestamp, phân biệt `Timestamp.valueOf(localDateTime)` cho dữ liệu địa phương và `Timestamp.from(instant)` cho thời điểm; schema/cấu hình vẫn phải đáp ứng ý nghĩa đó. Không tự fallback sang chuỗi hoặc epoch cho mọi lỗi rồi làm thay đổi hợp đồng dữ liệu.

## 9. Tự thực hành

1. Thử đọc một cột `DATE` bằng getter có `LocalDate.class`, rồi đối chiếu với kiểu của `getObject` không có `Class`.
2. Kiểm tra SQL `NULL`, ngày nhuận, timestamp có phần lẻ và giá trị có độ lệch khác UTC.
3. Chạy kiểm tra với đúng phiên bản driver trước và sau một lần nâng cấp; ghi lại khác biệt có bằng chứng.
4. Xác định ứng dụng cần giữ cùng thời điểm hay giữ cả độ lệch/vùng ban đầu, rồi chọn tiêu chí so sánh phù hợp.

Kết quả mong muốn là một hợp đồng chuyển đổi đã được xác nhận trên môi trường cụ thể: loại dữ liệu đúng, giá trị null rõ ràng, độ chính xác được biết và ý nghĩa thời gian không đổi.