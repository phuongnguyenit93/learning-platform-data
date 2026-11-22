# Đặt fetchSize, maxRows và queryTimeout trong JdbcTemplate

Khi sử dụng `JdbcTemplate`, ba thiết lập `fetchSize`, `maxRows` và `queryTimeout` thường cùng xuất hiện trong cấu hình, nhưng **chúng xử lý ba vấn đề khác nhau**:

- **`fetchSize`:** gợi ý cho JDBC driver số hàng nên nạp trong mỗi đợt lấy dữ liệu từ một `ResultSet`. Mục tiêu là cân bằng số lượt trao đổi với DB, độ trễ và bộ nhớ.
- **`maxRows`:** giới hạn số hàng tối đa được phép xuất hiện trong `ResultSet` của câu lệnh. Mục tiêu là tránh trả quá nhiều hàng cho phía đọc kết quả.
- **`queryTimeout`:** giới hạn thời gian thực thi một JDBC statement, tính bằng **giây**. Mục tiêu là tránh để thao tác SQL kéo dài ngoài thời lượng chấp nhận được, trong phạm vi driver hỗ trợ.

Chúng là ba cài đặt **khác nhau trên JDBC `Statement`**; không phải ba cách khác nhau để giới hạn số bản ghi và không đảm bảo tự động tối ưu truy vấn. Bài học này dùng Spring Framework 6.x, Spring Boot 3.3.x và Java 17+ trong ví dụ. Cách driver thực thi `fetchSize`, `maxRows`, việc hủy câu lệnh khi timeout và khả năng streaming phải được kiểm chứng trên DBMS/driver thực tế.

## 1. Bảng phân biệt nhanh

| Thuộc tính | Phương thức Spring | JDBC bên dưới | Đơn vị | Có trực tiếp giới hạn số hàng kết quả không? |
| --- | --- | --- | --- | --- |
| Fetch size | `JdbcTemplate.setFetchSize(int)` | `Statement.setFetchSize(int)` | Hàng/đợt (gợi ý) | **Không** |
| Max rows | `JdbcTemplate.setMaxRows(int)` | `Statement.setMaxRows(int)` | Hàng tối đa của `ResultSet` | **Có** |
| Query timeout | `JdbcTemplate.setQueryTimeout(int)` | `Statement.setQueryTimeout(int)` | **Giây** | **Không**; giới hạn thời gian statement |

Giả sử truy vấn có 50.000 hàng tiềm năng:

- `fetchSize = 200` chỉ yêu cầu driver **ưu tiên lấy từng nhóm khoảng 200 hàng** nếu chế độ driver và DB cho phép. Kết quả vẫn có thể có đủ 50.000 hàng.
- `maxRows = 1_000` yêu cầu JDBC statement chỉ cho phép tối đa **1.000 hàng** trong `ResultSet` của nó; không đồng nghĩa máy chủ SQL chắc chắn chỉ xử lý 1.000 hàng.
- `queryTimeout = 5` yêu cầu áp dụng timeout **5 giây** khi chạy statement; nó không tạo phép phân trang, không đặt timeout cho việc kết nối DB, và không chắc chắn sẽ kết thúc toàn bộ HTTP request trong đúng 5 giây.

Nếu đồng thời đặt cả ba, chúng có thể phối hợp: driver lấy dữ liệu theo lô khi hỗ trợ, bộ kết quả bị giới hạn và statement có giới hạn thời gian. **Không có quan hệ toán học kiểu `fetchSize × maxRows = queryTimeout`**.

## 2. Cơ chế: JdbcTemplate đưa các thiết lập xuống Statement

`JdbcTemplate` tạo/nhận một JDBC `Connection` từ `DataSource` và dùng `Statement`, `PreparedStatement` hoặc `CallableStatement` để chạy SQL. Trong quá trình chuẩn bị statement, nó áp dụng các giá trị được cấu hình vào JDBC API tương ứng.

```text
Service / Repository
       |
       v
  JdbcTemplate
       |
       | cấu hình một lần: fetchSize, maxRows, queryTimeout
       v
JDBC Statement / PreparedStatement
       |
       | setFetchSize(...)    --> gợi ý lấy dữ liệu
       | setMaxRows(...)      --> giới hạn ResultSet
       | setQueryTimeout(...) --> giới hạn thời gian chạy
       v
JDBC driver -------> Database
       |
       v
ResultSet --> RowMapper / RowCallbackHandler / ResultSetExtractor
```

### 2.1. Giá trị mặc định và giá trị 0

Trong Spring Framework 6.x, `JdbcTemplate` dùng mặc định **`-1`** cho cả ba thuộc tính: nghĩa là **không gọi setter tương ứng để ép một giá trị**, để driver xử lý theo mặc định.

| Giá trị | Với `JdbcTemplate` | Với JDBC `Statement` |
| --- | --- | --- |
| `-1` | Mặc định Spring: không áp giá trị cụ thể cho setter tương ứng. | `Statement` chuẩn không chấp nhận số âm ở những setter thông thường. |
| `0` | Spring chuyển `0` xuống setter nếu cấu hình như vậy. | `setFetchSize(0)`: bỏ qua gợi ý; `setMaxRows(0)`: không giới hạn; `setQueryTimeout(0)`: không đặt giới hạn thời gian thực thi statement. |
| Số dương | Spring chuyển xuống driver. | Driver nhận giá trị và áp dụng theo hợp đồng JDBC/khả năng triển khai. |

**Ngoại lệ đặc thù driver:** Spring hỗ trợ chuyển một số giá trị `fetchSize` âm **khác `-1`** xuống driver để dùng cơ chế riêng của nhà cung cấp (ví dụ một số kiểu MySQL sử dụng `Integer.MIN_VALUE`). Đó không phải hành vi portable của JDBC: chỉ dùng khi đã kiểm tra phiên bản driver và cấu hình phù hợp. Không tự chọn các giá trị âm khi chưa hiểu mục đích.

Các phương thức `getFetchSize()`, `getMaxRows()`, `getQueryTimeout()` trên `JdbcTemplate` trả **cấu hình của template**, không phải chứng cứ driver đã thật sự phân lô dữ liệu hoặc đã thực thi timeout theo cách mong muốn.

### 2.2. Phạm vi cài đặt

`setFetchSize`, `setMaxRows` và `setQueryTimeout` trên `JdbcTemplate` là **cấu hình chung** của các statement mà template tạo và chạy. Nó không thay đổi trực tiếp schema DB, không tự thêm `LIMIT` vào chuỗi SQL, và không thiết lập policy toàn cục cho mọi connection ở database.

`JdbcTemplate` được thiết kế an toàn khi chia sẻ giữa các thread **sau khi hoàn tất cấu hình**. Không gọi `jdbcTemplate.setMaxRows(...)` giữa lúc phục vụ các request khác nhau để “tạm” đổi giới hạn cho một request, rồi đổi lại: các request đồng thời có thể quan sát cấu hình bị thay đổi.

## 3. Thiết lập ba thuộc tính bằng Java

Khi tự tạo `JdbcTemplate`, cấu hình trước khi chia sẻ instance đó cho các repository/service:

```java
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;

public final class JdbcTemplateFactory {
    private JdbcTemplateFactory() {}

    public static JdbcTemplate createReportTemplate(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setFetchSize(200);  // gợi ý mỗi đợt lấy 200 hàng
        jdbc.setMaxRows(1_000);  // tối đa 1.000 hàng trong ResultSet
        jdbc.setQueryTimeout(5); // 5 GIÂY, không phải 5 ms
        return jdbc;
    }
}
```

Đây là lớp Java 17+ hợp lệ khi project có Spring JDBC trên classpath; phương thức trả một instance đã cấu hình, nhưng **không phải chương trình `main` chạy độc lập**. Ví dụ có giới hạn maxRows 1.000 để minh họa; ứng dụng thật cần cân nhắc rằng mọi query dùng instance đó sẽ chịu cùng giới hạn, kể cả những query muốn trả danh sách đầy đủ hơn.

### 3.1. Cấu hình Bean chuyên dụng trong Spring

`JdbcTemplate` thường là singleton được inject vào repository. Nếu có truy vấn báo cáo lớn nhưng truy vấn nghiệp vụ nhỏ, dùng **hai template có chính sách ổn định khác nhau**, cùng một `DataSource`:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class JdbcPolicyConfiguration {

    @Bean("normalJdbc")
    public JdbcTemplate normalJdbc(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setQueryTimeout(3);
        return jdbc;
    }

    @Bean("reportJdbc")
    public JdbcTemplate reportJdbc(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setFetchSize(500);
        jdbc.setMaxRows(10_000);
        jdbc.setQueryTimeout(30);
        return jdbc;
    }
}
```

Trong repository:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class ReportRepository {
    private final JdbcTemplate jdbc;

    public ReportRepository(@Qualifier("reportJdbc") JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countAll() {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM invoices", Long.class);
        return count == null ? 0L : count;
    }
}
```

Các lớp trên là **các thành phần của một Spring application** có Bean `DataSource`. Khi có từ hai Bean kiểu `JdbcTemplate`, nên dùng `@Qualifier` rõ ràng tại điểm inject. Cùng `DataSource` không đồng nghĩa mọi câu lệnh có cùng fetch size/timeout; các template sở hữu chính sách statement riêng. Cấu hình một lần trong `@Bean`, không đặt lại theo từng request.

**Lưu ý:** `setMaxRows(10_000)` áp dụng cho số hàng trả trong `ResultSet`, **không** đặt giới hạn cho số hàng được cập nhật bởi `UPDATE` hay `DELETE`, và không thay thế ràng buộc dữ liệu trong SQL.

## 4. fetchSize: cách lấy dữ liệu theo lô

### 4.1. Fetch size là gợi ý, không phải LIMIT

Khi kết quả có nhiều hàng, driver có thể lấy tất cả dữ liệu trong một lượt rồi giữ trong bộ nhớ client, hoặc sử dụng cursor để lấy dần từ DB. `Statement.setFetchSize(n)` báo cho driver rằng ứng dụng muốn dùng khoảng `n` hàng cho một đợt fetch.

Ví dụ có 5.000 hàng và `fetchSize=500`:

```text
Ứng dụng đọc ResultSet
       |
       +-- lô 1: hàng 1..500
       +-- lô 2: hàng 501..1000
       +-- ...
       +-- lô 10: hàng 4501..5000
```

Đây chỉ là **mô hình lý tưởng để hình dung**, không cam kết đúng 10 round-trip. Driver có thể bỏ qua hint hoặc dùng cơ chế riêng, và có thể có các lượt trao đổi khác. Fetch size lớn thường giảm số lần trao đổi nhưng có thể làm tăng bộ nhớ bộ đệm; quá nhỏ có thể tăng latency do nhiều lượt fetch.

Đặc biệt:

- `fetchSize=100` **không** khiến truy vấn `SELECT` chỉ trả 100 hàng.
- `fetchSize=100` **không** tự bảo đảm quá trình xử lý chỉ giữ 100 đối tượng Java.
- `fetchSize=100` **không** nhất thiết bật server cursor khi driver cần điều kiện bổ sung.
- `fetchSize` không sửa SQL query plan hoặc phép sắp xếp/lọc ở DB.
- Hãy thử với driver và hạ tầng thực tế, quan sát network, bộ nhớ, số lần fetch và thời gian.

### 4.2. RowMapper tạo List vẫn tích lũy kết quả

`JdbcTemplate.query(sql, RowMapper<T>)` thường ánh xạ từng hàng rồi trả một `List<T>`. Dù driver lấy dữ liệu theo lô, danh sách kết quả **vẫn có thể chứa tất cả hàng đã đọc**.

Ví dụ:

```java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

public final class UserReader {
    private final JdbcTemplate jdbc;

    public UserReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record UserSummary(long id, String name) {}

    public List<UserSummary> listAll() {
        return jdbc.query(
            "SELECT id, name FROM users ORDER BY id",
            (rs, rowNum) -> new UserSummary(
                rs.getLong("id"),
                rs.getString("name")
            )
        );
    }
}
```

Đây là lớp sử dụng trong application đã có bảng `users` và một `JdbcTemplate` được cấu hình; **không** phải ví dụ standalone có dữ liệu sẵn. Nếu kết quả 1 triệu hàng, một triệu record có thể được tạo và giữ trong `List` dù `fetchSize=200`. Để xử lý kết quả lớn với bộ nhớ ổn định hơn, cân nhắc xử lý từng hàng bằng `RowCallbackHandler`/`ResultSetExtractor` theo thiết kế không tích lũy, hoặc dùng `queryForStream` và **đóng stream** bằng try-with-resources. Driver vẫn phải hỗ trợ cơ chế fetch phù hợp.

### 4.3. Xử lý từng hàng với RowCallbackHandler

Ví dụ dưới đây tính tổng độ dài tên, không tạo danh sách chứa toàn bộ kết quả. Đây là đoạn lớp Java 17+ dùng bên trong Spring application có bảng `users`:

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;

public final class UserStatistics {
    private final JdbcTemplate jdbc;

    public UserStatistics(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long totalNameLength() {
        LongAdder total = new LongAdder();

        jdbc.query(
            "SELECT name FROM users",
            (RowCallbackHandler) rs -> {
                String name = rs.getString("name");
                if (name != null) {
                    total.add(name.length());
                }
            }
        );
        return total.sum();
    }
}
```

`RowCallbackHandler` được gọi lần lượt theo từng hàng; callback **không** tự gọi `rs.next()`. Đoạn mã chỉ giữ bộ đếm, nhưng vẫn có thể tốn bộ nhớ nếu driver đã đệm toàn bộ kết quả trước khi callback được gọi. Với dữ liệu cực lớn hoặc export dài, cần kiểm chứng driver cursor, transaction và giới hạn tài nguyên.

### 4.4. PostgreSQL và điều kiện để fetch bằng cursor

Với PostgreSQL JDBC (pgJDBC), fetch size dương **không tự đủ** để bảo đảm lấy dữ liệu theo lô. Cursor-based fetching thông thường cần:

1. Connection **không ở auto-commit mode** (gắn trong transaction phù hợp); PostgreSQL đóng cursor ở cuối transaction.
2. `ResultSet` là `TYPE_FORWARD_ONLY`.
3. Truy vấn là **một SQL statement**, không ghép nhiều statement trong một lệnh.
4. Driver và protocol hỗ trợ.

Ví dụ Spring với `@Transactional(readOnly = true)` (được transaction manager JDBC quản lý đúng cách):

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostgresUserExportService {
    private final JdbcTemplate reportJdbc;

    public PostgresUserExportService(JdbcTemplate reportJdbc) {
        this.reportJdbc = reportJdbc;
    }

    @Transactional(readOnly = true)
    public long processCount() {
        LongAdder seen = new LongAdder();
        reportJdbc.query(
            "SELECT id FROM users ORDER BY id",
            (RowCallbackHandler) rs -> seen.increment()
        );
        return seen.sum();
    }
}
```

Ở ví dụ này, `reportJdbc` được giả định đã cấu hình `fetchSize` dương, và gọi phương thức thông qua Spring transaction proxy. `@Transactional(readOnly=true)` chủ yếu là yêu cầu giao dịch/chế độ chỉ đọc; phải xác minh trên hệ thống thực tế rằng connection có auto-commit tắt và driver đang dùng cursor. Không áp dụng trực tiếp lập luận này cho H2/MySQL/Oracle mà chưa đọc tài liệu driver tương ứng.

> **Trade-off:** Cursor đọc lâu thường giữ connection và transaction trong thời gian xử lý kết quả. Không nên chạy xử lý CPU nặng hoặc gọi mạng bên trong callback quá lâu; có thể cần chia batch hoặc dùng cursor với quy mô/timeout phù hợp.

## 5. maxRows: giới hạn hàng trả về

`Statement.setMaxRows(1_000)` đặt số hàng tối đa của bất kỳ `ResultSet` nào được sinh từ statement đó (trong phạm vi driver thực thi). Nếu SQL tiềm năng trả 4.000 hàng, template với `maxRows=1_000` sẽ cho phía ứng dụng nhận tối đa 1.000 hàng.

Ví dụ có bảng `users` gồm nhiều hàng:

```java
JdbcTemplate limited = new JdbcTemplate(dataSource);
limited.setMaxRows(100);

var firstHundred = limited.query(
    "SELECT id, name FROM users ORDER BY id",
    (rs, rowNum) -> rs.getLong("id")
);
```

Đây là **đoạn minh họa trong phương thức đã có biến `dataSource`**, không phải Java standalone. Kết quả có tối đa 100 id. Tuy nhiên:

- Nếu SQL **không có `ORDER BY`**, không có khái niệm “100 hàng đầu” ổn định; lần chạy khác có thể trả tập hàng khác.
- `maxRows` là chính sách **JDBC ResultSet**, không nhất thiết là SQL `LIMIT` được tối ưu tại DB. DB vẫn có thể cần scan, sort hoặc join lượng dữ liệu lớn.
- Nó không mang thông tin số trang, tổng số bản ghi hay con trỏ cho trang tiếp theo.
- Những query khác trên **cùng template** cũng bị giới hạn, có thể gây **cắt dữ liệu âm thầm** nếu bạn quên chính sách này.

### 5.1. Giới hạn tại SQL thường đúng hơn cho tính năng phân trang

Với yêu cầu “trang đầu 100 bản ghi mới nhất”, viết rõ giới hạn cùng thứ tự trong SQL phù hợp DBMS:

```sql
-- PostgreSQL/H2 và một số DBMS khác:
SELECT id, name, created_at
FROM users
ORDER BY created_at DESC, id DESC
LIMIT 100;
```

Cặp `created_at DESC, id DESC` giúp thứ tự ổn định hơn khi nhiều hàng có cùng timestamp. Với DBMS hỗ trợ chuẩn SQL, có thể dùng `FETCH FIRST 100 ROWS ONLY`; cú pháp phân trang cụ thể tùy DB. Nếu trang có offset lớn hoặc dữ liệu thay đổi nhiều, có thể cân nhắc keyset pagination để ổn định và giảm chi phí. Thêm `maxRows=100` trên template vẫn có thể đóng vai trò **hàng rào phòng ngừa**, nhưng không thay thế giới hạn trong SQL và thiết kế API phân trang.

### 5.2. Đừng dùng maxRows để kiểm tra cập nhật hàng loạt

`JdbcTemplate.update(...)` trả **số hàng bị tác động** bởi `INSERT`/`UPDATE`/`DELETE`. `maxRows` áp lên kết quả `ResultSet`, không giới hạn số hàng mà một `UPDATE users SET ...` được phép sửa. Để giới hạn tác động của mutation, phải thiết kế `WHERE`, transaction, quyền truy cập và kiểm tra số hàng ảnh hưởng.

## 6. queryTimeout: giới hạn thời gian thực thi statement

`JdbcTemplate.setQueryTimeout(5)` chuyển yêu cầu timeout 5 **giây** xuống `Statement.setQueryTimeout(5)` khi áp dụng cấu hình statement. Theo hợp đồng JDBC, driver phải áp giới hạn cho các phương thức thực thi statement như `executeQuery`, `executeUpdate` và `execute`. Khi timeout xảy ra và driver xác định đã quá hạn, nó cố hủy câu lệnh và báo lỗi (thường là `SQLTimeoutException` ở tầng JDBC).

Trong Spring JDBC, `SQLException` có thể được dịch thành các `DataAccessException` thích hợp, trong đó có `QueryTimeoutException` tùy tình huống/driver/translator. Không viết mã nghiệp vụ dựa vào một thông điệp lỗi SQL cụ thể nếu chưa xác minh driver và cách Spring dịch lỗi.

### 6.1. Timeout nào? Đừng nhầm các tầng

| Timeout | Kiểm soát gì? | Cấu hình điển hình |
| --- | --- | --- |
| JDBC query timeout | Thời gian chờ statement thực thi/cancel theo driver | `JdbcTemplate.setQueryTimeout(seconds)` |
| Spring transaction timeout | Giới hạn thời gian transaction theo transaction manager; có thể được áp xuống JDBC statement | `@Transactional(timeout = 10)` hoặc cấu hình manager |
| Connection acquisition timeout | Thời gian chờ mượn connection từ pool | Hikari `connectionTimeout` (**mili-giây**) |
| Connect/login timeout | Thời gian thiết lập kết nối tới DB | JDBC driver/DataSource property |
| Socket/network timeout | Thời gian chờ thao tác mạng | Driver/network property |
| HTTP/request deadline | Thời hạn của request ở API/gateway | Web server/client/gateway configuration |

**Ví dụ:** `setQueryTimeout(5)` **không** bảo đảm request hoàn tất dưới 5 giây. Request có thể đã đợi lấy connection 2 giây, thực thi nhiều statement liên tiếp, hoặc còn chạy logic Java/HTTP bên ngoài SQL. Timeout statement không phải đồng hồ đo **toàn bộ service method**. Ngoài ra, thời điểm và khả năng hủy thực tế phụ thuộc driver, tình trạng network, DB và transaction state.

### 6.2. Timeout transaction có thể ghi đè timeout template

Spring `JdbcTemplate` ghi rõ: nếu một Spring-managed JDBC transaction có **transaction timeout**, thời gian còn lại của transaction sẽ **ghi đè** giá trị `queryTimeout` của template khi Spring áp timeout xuống statement.

Ví dụ có template đặt `queryTimeout=30` nhưng service thực thi:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LookupService {
    private final ReportRepository repository;

    public LookupService(ReportRepository repository) {
        this.repository = repository;
    }

    @Transactional(timeout = 5, readOnly = true)
    public long countInTransaction() {
        return repository.countAll();
    }
}
```

Giả sử có transaction manager và cơ chế proxy Spring hoạt động đúng, `countAll()` dùng cùng DataSource trong transaction này. **Remaining transaction timeout** (có thể đã trôi một phần trước khi chạy câu SQL) là timeout được ưu tiên áp lên statement. Không khẳng định luôn có đủ 5 giây khi truy vấn bắt đầu.

### 6.3. Timeout không phải rollback bảo đảm ở mọi tầng

Nếu `@Transactional` gặp `DataAccessException` runtime thoát khỏi transactional method, quy tắc rollback mặc định của Spring thường đánh dấu transaction rollback. Nhưng trong thực tế:

- Driver có thể không thể hủy statement ngay lập tức khi mạng/DB gặp vấn đề.
- Một statement bị hủy không đồng nghĩa **mọi** thay đổi ở bên ngoài transaction đã bị hoàn tác.
- Trạng thái transaction sau lỗi phụ thuộc DBMS và cách tổ chức transaction.
- Không nên tự động retry mọi câu `UPDATE`/`INSERT` sau timeout vì thao tác có thể đã thực thi ở phía DB mà client không nhận được phản hồi. Cần kiểm tra idempotency, transaction outcome và chính sách retry.

Để giới hạn tác động do lock hoặc SQL chậm, có thể kết hợp transaction timeout, database statement/lock timeout và hạn mức request phù hợp. Đây là các lớp bảo vệ bổ trợ, không phải một con số duy nhất.

## 7. Ví dụ chạy được: Spring Boot + H2

Ví dụ này kiểm chứng rõ **`maxRows` có hiệu lực với kết quả** và cho thấy cấu hình của cả ba thuộc tính. Không mô phỏng timeout thật, vì kiểm thử thời gian bằng cách ngủ/khóa có thể không ổn định giữa máy và driver; cũng không tuyên bố H2 nhất thiết fetch dữ liệu theo đúng từng lô đã đặt.

Tạo ứng dụng Spring Boot 3.3.x với Java 17+ và Gradle.

### 7.1. Gradle dependencies

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Tệp `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:jdbc_tuning_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` giữ DB H2 in-memory tồn tại trong vòng đời JVM dù connection cuối cùng đóng; dùng cho demo, không phải thiết lập production bắt buộc.

### 7.2. Toàn bộ ứng dụng Java

Tệp `src/main/java/example/JdbcSettingsDemoApplication.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class JdbcSettingsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcSettingsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource) {
        return args -> {
            // Template khởi tạo dữ liệu, không đặt giới hạn số hàng.
            JdbcTemplate setup = new JdbcTemplate(dataSource);
            setup.execute("CREATE TABLE sample (id INT PRIMARY KEY)");

            for (int id = 1; id <= 5; id++) {
                setup.update("INSERT INTO sample(id) VALUES (?)", id);
            }

            // Template riêng, cấu hình xong rồi mới dùng.
            JdbcTemplate limited = new JdbcTemplate(dataSource);
            limited.setFetchSize(2);
            limited.setMaxRows(3);
            limited.setQueryTimeout(5);

            List<Integer> ids = limited.query(
                "SELECT id FROM sample ORDER BY id",
                (rs, rowNum) -> rs.getInt("id")
            );

            System.out.println("fetchSize=" + limited.getFetchSize());
            System.out.println("maxRows=" + limited.getMaxRows());
            System.out.println("queryTimeout=" + limited.getQueryTimeout());
            System.out.println("ids=" + ids);
        };
    }
}
```

Chạy từ project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Khi dependency được tải đầy đủ, Java toolchain phù hợp và H2 thực thi `setMaxRows(3)` theo hợp đồng JDBC, các dòng do `System.out` của chương trình tạo ra là:

```text
fetchSize=2
maxRows=3
queryTimeout=5
ids=[1, 2, 3]
```

Spring Boot có thể in thêm log khởi động. Không có phép đo thời gian nào trong demo, nên `queryTimeout=5` chỉ xác nhận template đã nhận **5 giây**, không chứng minh statement sẽ thất bại sau 5 giây. Tương tự, `fetchSize=2` ở đây chỉ xác nhận cấu hình, không chứng minh driver sử dụng 3 lần fetch. Truy vấn có 5 hàng gốc, được `ORDER BY` xác định thứ tự, và `maxRows=3` chỉ cho kết quả 3 hàng.

**Điều cần rút ra:** `fetchSize` thay đổi chiến lược cấp dữ liệu khi driver áp dụng; `maxRows` thay đổi trần số hàng mà chương trình nhận; `queryTimeout` thay đổi trần thời gian statement. Cùng một `DataSource` có thể phục vụ nhiều template với chính sách khác nhau.

### 7.3. Kiểm tra một thuộc tính tại một thời điểm

Để so sánh có ý nghĩa, thực hiện các phép thử riêng:

1. Giữ SQL, schema và transaction giống nhau; thay `fetchSize` giữa 0, 50, 500, 5.000; đo tốc độ, memory, network/fetch trên driver thực, đặc biệt với nhiều hàng.
2. Giữ SQL có `ORDER BY`; thay `maxRows` giữa 0 (không giới hạn ở JDBC) và 3; kiểm tra số hàng trả về. Tránh dùng API trả dữ liệu lớn không giới hạn trong production chỉ để đo.
3. Kiểm tra `queryTimeout` với một truy vấn chậm được kiểm soát và driver cụ thể; ghi nhận exception, thời gian hủy và trạng thái transaction. Không suy diễn con số timeout lý thuyết thành SLA.
4. So sánh query có `LIMIT`/`FETCH FIRST` với chỉ dùng `maxRows`; quan sát query plan và lượng công việc DB thực hiện.

## 8. Khi nào nên đặt các thuộc tính?

### 8.1. Truy vấn ngắn, kết quả ít

Với một `SELECT ... WHERE id = ?` trả tối đa một hàng theo khóa chính, thường không cần tinh chỉnh `fetchSize`. Nên có timeout statement hoặc transaction hợp lý theo yêu cầu vận hành. `maxRows=1` có thể làm rào chắn phòng ngừa, nhưng kết quả đúng vẫn phụ thuộc điều kiện khóa/unique và API truy vấn.

### 8.2. Tra cứu danh sách có phân trang

Ưu tiên `ORDER BY` và giới hạn/offset hoặc keyset trong SQL. Đặt `maxRows` có thể bảo vệ thêm để không trả quá nhiều hàng; chọn `fetchSize` theo kích thước trang và driver. Cần thêm query timeout phù hợp; đừng trông đợi `maxRows` giải quyết pagination.

### 8.3. Báo cáo hoặc export lớn

Nếu cần đọc rất nhiều hàng:

- Tối ưu SQL/index và chỉ lấy cột cần thiết.
- Chọn `fetchSize` phù hợp driver, cân nhắc cursor/transaction.
- Tránh `RowMapper` tạo `List` cực lớn; dùng callback/stream có xử lý theo hàng và đóng resource.
- Đặt `maxRows` theo giới hạn xuất dữ liệu **nếu nghiệp vụ thực sự cho phép cắt kết quả**. Nếu cần export đầy đủ, không đặt một giới hạn ngầm khiến dữ liệu bị mất.
- Cân nhắc query timeout riêng và ranh giới xử lý ngắn; không giữ transaction/connection vô thời hạn khi chờ network/file I/O.
- Quan sát số hàng, bộ nhớ, thời gian DB, thời gian đọc dữ liệu, pool active và sự cố timeout.

### 8.4. Nhiều loại truy vấn trong cùng ứng dụng

Đừng dùng một giá trị duy nhất chỉ vì một ví dụ cấu hình đã đặt nó. Có thể định nghĩa template chuyên dụng cho OLTP nhỏ và báo cáo dài, hoặc tổ chức repository/cấu hình phù hợp. Chỉ thay đổi thông số trên instance **trước khi** nó được chia sẻ. Nếu bắt buộc có thông số theo từng request, cần cơ chế tùy biến statement theo đúng API và quản lý transaction, không đổi setter của shared singleton trong request.

## 9. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`fetchSize=100` nghĩa là chỉ đọc 100 hàng” | Đây là hint về kích thước đợt fetch. | Dùng `maxRows` hoặc `LIMIT/FETCH FIRST` nếu muốn giới hạn số hàng. |
| “`fetchSize=200` bảo đảm dùng rất ít RAM” | `RowMapper` có thể tích lũy toàn bộ List; driver có thể đệm hết. | Chọn callback/stream và kiểm tra streaming ở driver. |
| “`maxRows=50` làm DB chỉ xử lý 50 hàng” | Giới hạn JDBC ResultSet không bảo đảm DB scan/sort ít. | Giới hạn trong SQL, tối ưu index/query plan. |
| “`maxRows` tạo pagination” | Không có page cursor, offset hay thứ tự ổn định. | Thiết kế `ORDER BY` và keyset/offset hợp lý. |
| “`queryTimeout=5000` là 5 giây” | Đơn vị của `setQueryTimeout` là **giây**. | Dùng `5` cho 5 giây; kiểm tra giá trị với driver. |
| “Query timeout = connection timeout” | Thời gian chờ mượn/kết nối và chạy SQL là các giai đoạn khác nhau. | Cấu hình riêng pool, driver/network, JDBC statement và request. |
| “`@Transactional(timeout=3)` không liên quan `JdbcTemplate`” | Remaining transaction timeout có thể ghi đè setting statement. | Kiểm tra transaction manager và giá trị timeout thực tế. |
| “Có timeout là dữ liệu chắc chắn rollback” | Driver/cancellation, DB, transaction và side effect ngoài DB có quy tắc khác nhau. | Định nghĩa rõ transaction, rollback, idempotency và retry. |
| “Đổi `JdbcTemplate.setMaxRows` trong mỗi request là ổn” | Template chia sẻ có cấu hình mutable, dễ race giữa request. | Cấu hình một lần; dùng instance chuyên dụng. |
| “Thấy `getFetchSize()=200` chứng tỏ có 200 hàng/packet” | Getter chỉ trả cấu hình, không phải network trace. | Đo driver/DB, log, profiling và kiểm thử tải. |

## 10. Câu hỏi tự kiểm tra

**1.** Một truy vấn trả 12.000 hàng, `fetchSize=300` và `maxRows=-1`. Ứng dụng chắc chắn chỉ nhận 300 hàng?

**Đáp án:** Không. `fetchSize` là gợi ý số hàng cho mỗi đợt fetch; không giới hạn tổng số hàng. `maxRows=-1` là không đặt thêm trần từ `JdbcTemplate`, nên kết quả có thể đủ 12.000 hàng.

**2.** `setMaxRows(25)` khác gì `SELECT ... LIMIT 25`?

**Đáp án:** `setMaxRows` giới hạn số hàng trong JDBC ResultSet; `LIMIT` là điều kiện giới hạn ở tầng SQL được DBMS hiểu và có thể tối ưu trong kế hoạch. Muốn chọn 25 bản ghi xác định cần `ORDER BY`; cú pháp SQL giới hạn khác nhau tùy DBMS.

**3.** Truy vấn bị chậm vì đợi mượn connection 20 giây từ pool, trong khi `queryTimeout=5`. Có bảo đảm request thất bại sau 5 giây tổng cộng?

**Đáp án:** Không. `queryTimeout` là giới hạn thực thi JDBC statement, không bao gồm toàn bộ thời gian đợi connection.

**4.** Trong `@Transactional(timeout=4)`, template cấu hình `queryTimeout=20`. Spring thường áp timeout statement thế nào?

**Đáp án:** Khi Spring JDBC transaction manager và `JdbcTemplate` tham gia đúng transaction có timeout, thời gian **còn lại** của transaction được áp lên statement, ghi đè 20 giây cấu hình ở template.

**5.** Có thể kiểm soát memory cho export lớn chỉ bằng `setFetchSize(100)` không?

**Đáp án:** Không. Driver cần hỗ trợ fetch từng lô/cursor, và code phải xử lý dữ liệu theo lô/hàng thay vì gom cả kết quả vào một List khổng lồ.

**6.** `setQueryTimeout(0)` có nghĩa gì trong JDBC chuẩn? `JdbcTemplate` mặc định `-1` khác nó ở đâu?

**Đáp án:** JDBC chuẩn hiểu `0` là không giới hạn thời gian statement; `-1` ở Spring có nghĩa là không gọi setter và để driver dùng mặc định của nó (mặc định driver có thể có timeout riêng). Vì vậy không coi hai cài đặt đồng nghĩa trong mọi môi trường.

## 11. Checklist trước khi merge cấu hình

- [ ] Xác định **mục tiêu**: giảm memory/round trips, giới hạn số hàng hay giới hạn thời gian.
- [ ] Kiểm tra loại DBMS, phiên bản JDBC driver, auto-commit/transaction và support cursor.
- [ ] Với `fetchSize`, đã đo số lượt fetch, memory và thời gian trong bối cảnh driver thực tế.
- [ ] Với `maxRows`, đã kiểm tra thứ tự `ORDER BY` và tác động cắt dữ liệu lên toàn bộ query dùng template.
- [ ] Với pagination, SQL có giới hạn rõ ràng và thứ tự ổn định; không chỉ dựa vào JDBC limit.
- [ ] Với `queryTimeout`, biết đơn vị **giây** và phân biệt nó với Hikari `connectionTimeout` **mili-giây**.
- [ ] Biết transaction timeout có thể ghi đè query timeout; không coi cancel là bảo đảm rollback độc lập.
- [ ] Không thay đổi setting trên `JdbcTemplate` singleton giữa các request.
- [ ] Có chỉ số thực tế về duration SQL, số hàng, bộ nhớ, DB load, connection pool và timeout.
- [ ] Test hành vi trên driver đang triển khai, không chỉ trên H2 trong ví dụ.

## 12. Tài liệu tham khảo

- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): setter/getter, mặc định `-1` và việc transaction timeout ghi đè.
- [Java 21 — java.sql.Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): hợp đồng JDBC của `setFetchSize`, `setMaxRows`, `setQueryTimeout` và đơn vị.
- [Spring Framework — DataSourceUtils](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): cách áp statement timeout theo transaction.
- [pgJDBC — Issuing a Query and Processing the Result](https://jdbc.postgresql.org/documentation/query/): điều kiện cursor-based fetching với fetch size.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): mẫu dùng `JdbcTemplate` và xử lý `ResultSet`.

**Ghi nhớ:** `fetchSize` điều chỉnh **cách lấy** dữ liệu (hint, tùy driver), `maxRows` giới hạn **bao nhiêu hàng được trả** qua JDBC ResultSet, còn `queryTimeout` giới hạn **thời gian thực thi** statement (giây). Kết hợp đúng chúng với SQL có thứ tự/giới hạn, transaction hợp lý và kiểm thử trên driver thật sẽ giúp ứng dụng Spring an toàn và dễ dự đoán hơn.
