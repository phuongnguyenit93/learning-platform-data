# Ánh xạ một hàng thành đối tượng bất biến hoặc Java record trong JDBC

Khi truy vấn cơ sở dữ liệu bằng **JDBC**, ứng dụng Java nhận dữ liệu dưới dạng `ResultSet`: một con trỏ duyệt qua các hàng với những giá trị được đọc theo tên hoặc vị trí cột. Phần lớn mã nghiệp vụ không nên phụ thuộc trực tiếp vào `ResultSet`, vì con trỏ đó gắn với kết nối, câu lệnh SQL và vòng đời tài nguyên JDBC. Thay vào đó, ứng dụng thường **ánh xạ mỗi hàng thành một đối tượng Java có kiểu rõ ràng**.

Với dữ liệu chỉ dùng để đọc, đối tượng **bất biến** (*immutable object*) hoặc **Java record** là lựa chọn tự nhiên: dữ liệu được chốt ngay khi tạo, có thể chuyển ra ngoài khối `try-with-resources`, không bị thay đổi tùy ý bởi những nơi đang tham chiếu đến nó. Bài này tập trung vào cách viết phép ánh xạ tường minh bằng các API chuẩn `DataSource`, `PreparedStatement`, `ResultSet` và `SQLException` mà không cần thư viện ORM.

Sau bài học, bạn cần có thể:

- Thiết kế `record` hoặc lớp `final` để biểu diễn một hàng kết quả.
- Viết hàm `mapRow(ResultSet)` chuyển cột SQL thành các trường có kiểu Java phù hợp.
- Xử lý `NULL`, bí danh cột, kiểu số và ngày tháng một cách có chủ đích.
- Tách mã ánh xạ khỏi mã thực thi truy vấn, bảo đảm dữ liệu vẫn dùng được sau khi đóng `ResultSet`.
- Nhận diện giới hạn khi truy vấn trả nhiều hàng, có quan hệ `JOIN` hoặc lượng dữ liệu lớn.

## 1. Từ hàng SQL đến đối tượng Java

Một truy vấn JDBC đi qua các bước sau:

```text
SQL có tham số
      |
PreparedStatement.executeQuery()
      |
ResultSet  -- next() -->  Hàng hiện tại
                              |
                           mapRow(rs)
                              |
                     AccountRow bất biến
                              |
                     Mã nghiệp vụ / API
```

`ResultSet` không phải một danh sách đối tượng đã có sẵn. Ban đầu con trỏ đứng **trước hàng đầu tiên**. Chỉ sau khi `rs.next()` trả về `true`, các hàm như `getLong`, `getString` và `getBigDecimal` mới đọc các cột của hàng hiện tại. `next()` trả `false` khi đã hết hàng.

Một **ánh xạ hàng** (*row mapping*) thường là hàm có dạng:

```java
static AccountRow mapRow(ResultSet rs) throws SQLException {
    // Gọi khi rs đang trỏ đến một hàng hợp lệ.
    // Đọc đủ các cột và tạo một giá trị Java độc lập với ResultSet.
}
```

Hàm ánh xạ nhận một `ResultSet` đang ở **đúng một hàng**. Nó không gọi `next()`, không đóng `ResultSet`, không chạy truy vấn khác và không giữ tham chiếu tới kết nối. Tầng truy vấn chịu trách nhiệm duyệt hàng và quản lý tài nguyên; tầng ánh xạ chịu trách nhiệm đọc cột và dựng đối tượng.

**Ví dụ xuyên suốt:** ứng dụng quản lý tài khoản khách hàng với số dư, trạng thái hoạt động và ngày đăng ký. Bảng minh họa:

```sql
CREATE TABLE customer_account (
    account_id    BIGINT PRIMARY KEY,
    display_name  VARCHAR(120) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    balance       DECIMAL(12, 2) NOT NULL,
    active        BOOLEAN NOT NULL,
    registered_on DATE NOT NULL,
    closed_on     DATE NULL
);
```

DDL này dùng các kiểu SQL phổ biến để minh họa; tên kiểu và cú pháp chi tiết có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle hoặc hệ quản trị khác. Điểm quan trọng của thiết kế là: `account_id`, `display_name`, `email`, `balance`, `active` và `registered_on` **không được `NULL`**, còn `closed_on` có thể `NULL` nếu tài khoản chưa đóng.

## 2. Dùng Java record cho dữ liệu bất biến

Java **record** (ổn định từ Java 16) khai báo một nhóm thành phần dữ liệu và tự sinh constructor chuẩn, các phương thức truy cập, `equals`, `hashCode` và `toString`. Trường thành phần của record là `private final`; record không có setter để thay các thành phần ấy sau khi khởi tạo.

Ví dụ trong tệp `AccountRow.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Objects;

public record AccountRow(
        long id,
        String displayName,
        String email,
        BigDecimal balance,
        boolean active,
        LocalDate registeredOn,
        LocalDate closedOn) {

    // Compact constructor: kiểm tra hợp đồng dữ liệu khi tạo record.
    public AccountRow {
        Objects.requireNonNull(displayName, "displayName");
        Objects.requireNonNull(email, "email");
        Objects.requireNonNull(balance, "balance");
        Objects.requireNonNull(registeredOn, "registeredOn");
        // closedOn được phép null vì cột SQL tương ứng cho phép NULL.

        if (displayName.isBlank()) {
            throw new IllegalArgumentException("displayName must not be blank");
        }
    }
}
```

Cách dùng:

```java
AccountRow row = new AccountRow(
        1001L,
        "Nguyễn An",
        "an@example.test",
        new BigDecimal("1250.00"),
        true,
        LocalDate.of(2026, 1, 15),
        null);

System.out.println(row.id());          // 1001
System.out.println(row.displayName()); // Nguyễn An
System.out.println(row.balance());     // 1250.00
System.out.println(row.closedOn());    // null: tài khoản chưa đóng
```

Các phương thức truy cập record có tên **`id()`**, **`displayName()`**, ... thay vì bắt buộc theo mẫu `getId()` hoặc `getDisplayName()`. `new AccountRow(...)` đòi hỏi đủ các thành phần theo đúng thứ tự và kiểu của constructor. JDBC **không tự ghép** cột SQL vào record chỉ vì tên gần giống nhau; chúng ta phải viết phép ánh xạ hoặc sử dụng một công cụ hỗ trợ ánh xạ riêng.

Trong ví dụ này, các thành phần `String`, `BigDecimal` và `LocalDate` đều là kiểu bất biến, nên một `AccountRow` sau khi tạo không thể bị sửa từ bên ngoài thông qua các giá trị thành phần. Việc gọi constructor để kiểm tra `NOT NULL` giúp phát hiện nhanh dữ liệu hoặc truy vấn không khớp với hợp đồng Java. Những kiểm tra nghiệp vụ như “số dư không được âm” chỉ nên đưa vào constructor nếu **thực sự** là quy tắc của hệ thống; không tự giả định mọi tài khoản đều cấm số dư âm.

### Record bất biến ở mức nông

**Record không tự biến các thành phần có thể thay đổi thành dữ liệu bất biến sâu.** Với `List`, `Map`, mảng hay một đối tượng mutable, phải chủ động tạo bản sao hoặc dùng kiểu bất biến.

```java
import java.util.List;
import java.util.Objects;

public record AccountTags(long accountId, List<String> tags) {
    public AccountTags {
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
```

`List.copyOf` tạo danh sách không thể sửa qua API danh sách và bảo vệ cấu trúc khỏi thay đổi ở danh sách đầu vào; việc bảo vệ toàn bộ dữ liệu còn phụ thuộc các phần tử có bất biến hay không. Mảng cần sao chép khi nhận **và** khi trả ra qua accessor. Vì vậy, ưu tiên giá trị như `String`, `BigDecimal` và `java.time.LocalDate` để mô tả bản ghi chỉ đọc.

## 3. Viết hàm ánh xạ một hàng từ ResultSet

Một truy vấn có thể chọn nhiều cột và sử dụng **bí danh** để tên cột trong kết quả ổn định:

```sql
SELECT
    account_id AS id,
    display_name,
    email,
    balance,
    active,
    registered_on,
    closed_on
FROM customer_account
WHERE account_id = ?;
```

Trong JDBC, các phương thức `getXxx(String)` tra cứu theo **nhãn cột** (*column label*). Khi có `AS id`, cột đầu tiên có nhãn `id`; ánh xạ bằng `rs.getLong("id")`, thay vì phụ thuộc vào tên gốc `account_id`. Nếu tên cột xuất hiện nhiều lần trong kết quả `JOIN`, cần dùng bí danh riêng để tránh đọc nhầm cột.

Hàm ánh xạ cho record ở trên:

```java
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

private static AccountRow mapRow(ResultSet rs) throws SQLException {
    return new AccountRow(
            rs.getLong("id"),
            rs.getString("display_name"),
            rs.getString("email"),
            rs.getBigDecimal("balance"),
            rs.getBoolean("active"),
            readLocalDate(rs, "registered_on"),
            readLocalDate(rs, "closed_on"));
}

private static LocalDate readLocalDate(ResultSet rs, String label)
        throws SQLException {
    Date date = rs.getDate(label);
    return date == null ? null : date.toLocalDate();
}
```

`rs.getBigDecimal("balance")` giữ dữ liệu `DECIMAL` ở dạng thập phân chính xác, không đi qua `double`. `rs.getDate(...)` trả `java.sql.Date`; chuyển sang `LocalDate` cho phép mô hình Java sử dụng kiểu ngày bất biến. Với `closed_on` là `NULL`, `getDate` trả về `null`, do đó `readLocalDate` cũng trả `null`.

Driver JDBC hiện đại thường hỗ trợ ánh xạ trực tiếp SQL `DATE` sang `LocalDate` bằng `rs.getObject("registered_on", LocalDate.class)` theo JDBC 4.2. Nếu driver không hỗ trợ phép chuyển kiểu cụ thể, dùng `getDate(...).toLocalDate()` như ví dụ và xác minh trên hệ quản trị đích. Với `TIMESTAMP`, cần lựa chọn chính xác `LocalDateTime`, `Instant` hay `OffsetDateTime` theo việc dữ liệu có ngữ nghĩa múi giờ hay không; không tự coi mọi timestamp là một thời điểm UTC.

### Các kiểu đọc thường gặp

| Kiểu cột SQL | Kiểu Java đề xuất | Cách đọc điển hình | Điểm cần chú ý |
| --- | --- | --- | --- |
| `BIGINT NOT NULL` | `long` | `rs.getLong("id")` | Nếu cột có thể `NULL`, kiểu nguyên thủy không đủ biểu diễn |
| `VARCHAR` / `CHAR` | `String` | `rs.getString("name")` | Có thể trả `null` khi SQL là `NULL` |
| `DECIMAL` / `NUMERIC` | `BigDecimal` | `rs.getBigDecimal("balance")` | Tránh đi vòng qua `float` hoặc `double` với số tiền |
| `BOOLEAN NOT NULL` | `boolean` | `rs.getBoolean("active")` | `NULL` bị đọc thành `false` nếu không kiểm tra `wasNull()` |
| `DATE` | `LocalDate` | `rs.getDate("day").toLocalDate()` | Phải xử lý `null` trước khi gọi `toLocalDate()` |
| `TIMESTAMP` | Tùy nghiệp vụ | `getTimestamp` hoặc `getObject` có kiểu | Cân nhắc múi giờ và khả năng hỗ trợ của driver |

## 4. Đặt phép ánh xạ trong repository JDBC

`DataSource` cung cấp kết nối; `PreparedStatement` thực thi SQL tham số hóa; `ResultSet` cung cấp các hàng. Repository giữ trách nhiệm này, còn record chỉ giữ dữ liệu. Ví dụ đầy đủ trong tệp `AccountRepository.java` (sử dụng `AccountRow` đã định nghĩa):

```java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public Optional<AccountRow> findById(long id) throws SQLException {
        String sql = """
                SELECT account_id AS id, display_name, email, balance,
                       active, registered_on, closed_on
                FROM customer_account
                WHERE account_id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(mapRow(rs));
            }
        }
    }

    public List<AccountRow> findActiveSince(LocalDate startDate)
            throws SQLException {
        Objects.requireNonNull(startDate, "startDate");

        String sql = """
                SELECT account_id AS id, display_name, email, balance,
                       active, registered_on, closed_on
                FROM customer_account
                WHERE active = ? AND registered_on >= ?
                ORDER BY account_id
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBoolean(1, true);
            statement.setDate(2, Date.valueOf(startDate));

            try (ResultSet rs = statement.executeQuery()) {
                List<AccountRow> rows = new ArrayList<>();
                while (rs.next()) {
                    rows.add(mapRow(rs));
                }
                return List.copyOf(rows);
            }
        }
    }

    private static AccountRow mapRow(ResultSet rs) throws SQLException {
        return new AccountRow(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email"),
                rs.getBigDecimal("balance"),
                rs.getBoolean("active"),
                readLocalDate(rs, "registered_on"),
                readLocalDate(rs, "closed_on"));
    }

    private static LocalDate readLocalDate(ResultSet rs, String label)
            throws SQLException {
        Date date = rs.getDate(label);
        return date == null ? null : date.toLocalDate();
    }
}
```

Các bước quan trọng:

1. `findById` gọi `rs.next()` **một lần** để tìm hàng; trả `Optional.empty()` nếu không có hàng. Cột khóa chính đảm bảo truy vấn này tối đa một hàng.
2. `findActiveSince` gọi `rs.next()` trong vòng `while`, dựng một `AccountRow` mới cho **mỗi** hàng và trả một `List` không cho thay đổi cấu trúc.
3. `mapRow` chỉ đọc cột của hàng hiện tại, nên cùng một phương thức có thể tái sử dụng giữa các truy vấn có **cùng hợp đồng cột và bí danh**.
4. Cả `ResultSet`, `PreparedStatement` và `Connection` đều được đóng bởi `try-with-resources`, kể cả khi phát sinh `SQLException` hay lỗi khi tạo record. Với `DataSource` dùng connection pool, `close()` thường trả kết nối về pool.
5. `AccountRow` là một giá trị độc lập với `ResultSet`, nên vẫn đọc được `row.balance()` hoặc `row.registeredOn()` sau khi phương thức repository trả về.

Đoạn mã trên dùng Java 17 trở lên (để có `record` và chuỗi nhiều dòng `"""`). Ở dự án dùng Java 16, có thể viết SQL bằng chuỗi thông thường; ở Java cũ hơn cần dùng lớp bất biến thay record. Phần `SQL WHERE` dùng dấu `?`, giúp truyền tham số đúng kiểu qua JDBC và tránh ghép dữ liệu bên ngoài trực tiếp vào chuỗi SQL.

Nếu ứng dụng cần nhiều thao tác trong **cùng transaction**, không nên để từng repository method tùy ý mở kết nối riêng rồi mặc nhiên kỳ vọng chúng cùng transaction. Khi đó có thể đưa `Connection` do tầng transaction quản lý vào phương thức truy vấn và giữ trách nhiệm `commit`/`rollback` ở tầng gọi. Nguyên tắc tách `mapRow` khỏi vòng đời kết nối vẫn giữ nguyên.

## 5. Xử lý SQL NULL mà không mất thông tin

SQL `NULL` có nghĩa “không có giá trị”. Các getter đọc kiểu nguyên thủy trong `ResultSet` có hành vi dễ gây nhầm:

- `getLong`, `getInt` trả `0` nếu cột là `NULL`.
- `getBoolean` trả `false` nếu cột là `NULL`.
- `getString`, `getBigDecimal`, `getDate` và những getter đọc kiểu tham chiếu có thể trả `null`.

Vì vậy, **chỉ dùng `long`, `int`, `boolean` khi cột tương ứng được bảo đảm `NOT NULL`**. Nếu cột nullable, hãy chuyển sang kiểu bao (`Long`, `Integer`, `Boolean`) và kiểm tra `wasNull()` ngay sau getter nguyên thủy.

```java
static Long nullableParentId(ResultSet rs) throws SQLException {
    long value = rs.getLong("parent_account_id");
    return rs.wasNull() ? null : value;
}

static Boolean nullableApproved(ResultSet rs) throws SQLException {
    boolean value = rs.getBoolean("approved");
    return rs.wasNull() ? null : value;
}
```

`wasNull()` cho biết **cột vừa được đọc gần nhất** có phải SQL `NULL` không. Phải gọi ngay sau `getLong` hoặc `getBoolean` tương ứng, trước khi đọc một cột khác. Một số driver hỗ trợ `rs.getObject("parent_account_id", Long.class)` hoặc `rs.getObject("approved", Boolean.class)` để nhận `null` trực tiếp, nhưng nên kiểm tra khả năng hỗ trợ chuyển kiểu của driver thực tế.

Quy tắc khai báo record phải tương thích với SQL:

```java
// Nếu approved ở SQL có thể NULL, dùng Boolean thay cho boolean.
record ApprovalRow(long id, Boolean approved) {}
```

Với `closed_on` trong ví dụ chính, `LocalDate closedOn` cho phép `null` và constructor đã ghi rõ chủ đích đó. Tránh dùng `Optional` làm thành phần record một cách máy móc: `Optional` thường hữu ích ở **kiểu trả về phương thức**, chẳng hạn `findById`, hơn là thay thế mọi trường nullable trong mô hình dữ liệu. Tùy thiết kế API, có thể cung cấp thêm phương thức diễn giải `closedOn == null` mà không làm mất giá trị SQL gốc.

## 6. Ánh xạ theo tên cột, kiểu dữ liệu và hợp đồng truy vấn

`ResultSet` hỗ trợ hai kiểu truy cập:

```java
rs.getString(2);               // Theo chỉ số, bắt đầu từ 1
rs.getString("display_name"); // Theo nhãn cột
```

Đọc theo **nhãn cột** thường dễ bảo trì hơn: đổi thứ tự các cột trong `SELECT` không làm `mapRow` đọc nhầm. Tuy nhiên, nhãn vẫn là một **hợp đồng**: nếu truy vấn sửa `display_name AS name` mà mapper vẫn gọi `getString("display_name")`, driver có thể ném `SQLException` vì không tìm thấy nhãn cột.

Để tránh nhầm lẫn khi `JOIN`, nên đặt bí danh rõ ràng:

```sql
SELECT
    a.account_id AS account_id,
    a.display_name AS account_display_name,
    p.profile_id AS profile_id,
    p.display_name AS profile_display_name
FROM customer_account a
LEFT JOIN customer_profile p ON p.account_id = a.account_id;
```

Ở ví dụ trên, nếu cần `profile_id` nhưng bảng bên phải của `LEFT JOIN` không có hàng tương ứng, cột `profile_id` sẽ là `NULL`; đọc bằng `getLong` rồi kiểm tra `wasNull()` hoặc bằng getter đối tượng được driver hỗ trợ. Cần quyết định tạo một record lồng nhau, đánh dấu thông tin không có, hay dùng một DTO phẳng tùy mục đích truy vấn.

**Không nên dùng `SELECT *` cho mapper cần hợp đồng rõ ràng.** Nêu đích danh các cột giúp tránh các cột trùng tên khi `JOIN`, tránh tải dữ liệu không cần thiết và giúp code review nhìn thấy ngay những trường mapper phụ thuộc.

### Chuẩn hóa và xác thực khi ánh xạ

Constructor record là nơi hợp lý để kiểm tra những điều kiện bất biến thật sự của đối tượng, ví dụ cột `NOT NULL` không thể trở thành `null` hoặc `displayName` trống khi ứng dụng cấm. Nhưng cần tách các trách nhiệm:

- **SQL và JDBC**: chọn cột, thực thi truy vấn, chuyển kiểu JDBC (`getBigDecimal`, `getDate`, ...).
- **Mapper**: ghép từng cột vào đúng thành phần Java; có thể áp dụng quy tắc chuyển đổi rõ ràng.
- **Constructor/domain**: bảo vệ các điều kiện bất biến của đối tượng.
- **Service**: thực hiện quy tắc nghiệp vụ phức tạp hoặc tính toán liên quan nhiều bản ghi.

Ví dụ, tự `trim()` mọi chuỗi ở mapper có thể vô tình thay đổi dữ liệu gốc. Chỉ chuẩn hóa như vậy khi đã có yêu cầu nghiệp vụ hoặc hợp đồng dữ liệu rõ ràng. `BigDecimal` nên được giữ nguyên giá trị đọc từ `DECIMAL`; quy tắc precision, scale và làm tròn cần được quyết định bởi nghiệp vụ và schema, không tự ý áp dụng tại mọi lần đọc.

## 7. Khi nào dùng lớp bất biến thay vì record?

Record ngắn gọn và rất hợp với **snapshot**, **DTO**, hàng kết quả tìm kiếm hoặc dữ liệu gửi sang tầng API. Một lớp `final` vẫn là lựa chọn phù hợp khi dự án dùng Java cũ hơn, muốn che giấu biểu diễn dữ liệu, cần kiểm soát API truy cập theo chuẩn JavaBean, hoặc cần constructor và phương thức tùy biến nhiều hơn.

Ví dụ lớp bất biến tối giản (dùng được trên Java không hỗ trợ record):

```java
import java.util.Objects;

public final class CustomerSummary {
    private final long id;
    private final String name;

    public CustomerSummary(long id, String name) {
        this.id = id;
        this.name = Objects.requireNonNull(name, "name");
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Ánh xạ tương ứng:

```java
static CustomerSummary mapCustomer(ResultSet rs) throws SQLException {
    return new CustomerSummary(
            rs.getLong("customer_id"),
            rs.getString("customer_name"));
}
```

Khai báo `final` ở lớp và các trường `private final` giúp ngăn thay đổi trường sau khi tạo và ngăn kế thừa làm thay đổi hành vi cơ bản. Nhưng **bất biến sâu** vẫn đòi hỏi sao chép phòng vệ khi lớp chứa tham chiếu mutable. Ngoài ra, lớp trên **chưa tự có** `equals`, `hashCode`, `toString` theo giá trị như record; nếu cần ngữ nghĩa bằng nhau theo giá trị, phải tự cài đặt phù hợp. Một record cũng không phải entity ORM có cơ chế theo dõi thay đổi: thay đổi giá trị trong Java (bằng cách tạo một record khác) sẽ không tự động tạo câu lệnh `UPDATE` trong JDBC.

| Tiêu chí | Java record | Lớp `final` bất biến |
| --- | --- | --- |
| Mục đích điển hình | DTO, giá trị đọc từ DB, snapshot | DTO hoặc đối tượng miền có API tùy biến |
| Boilerplate | Ít; Java sinh constructor/accessor/equality | Nhiều hơn; tự viết thành phần cần dùng |
| Truy cập | `row.id()` | Tùy thiết kế, thường `row.getId()` |
| Kiểm tra hợp đồng | Compact constructor / constructor tường minh | Constructor tường minh |
| Bảo vệ cấu trúc mutable | Vẫn phải tự sao chép | Vẫn phải tự sao chép |
| Yêu cầu phiên bản | Java 16+ | Có thể dùng trên Java cũ |

## 8. Những giới hạn khi ánh xạ kết quả phức tạp

### Một hàng không nhất thiết bằng một đối tượng nghiệp vụ hoàn chỉnh

Hàm `mapRow(rs)` ánh xạ **một hàng** thành **một giá trị**. Quy ước này rất hiệu quả với truy vấn phẳng, nhưng một phép `JOIN` một-nhiều có thể lặp cùng thông tin tài khoản trên nhiều hàng:

```text
account_id | account_name | tag
-----------+--------------+----------
1001       | Nguyễn An    | premium
1001       | Nguyễn An    | newsletter
```

Nếu mapper tạo nguyên một `AccountWithTags` cho từng hàng thì sẽ tạo hai đối tượng cho cùng tài khoản. Để tạo **một** tài khoản cùng danh sách tag, cần nhóm các hàng theo khóa, xây danh sách trung gian, sau đó tạo đối tượng bất biến khi đã thu thập đủ. Với dữ liệu lớn, cân nhắc tách truy vấn, phân trang, truy vấn tổng hợp hoặc phương án SQL phù hợp, thay vì mặc nhiên tạo graph đối tượng đầy đủ từ mỗi hàng.

### Kết quả nhiều hàng và bộ nhớ

`findActiveSince` dùng `List.copyOf(rows)` để trả danh sách không thể sửa qua API danh sách. Cách này phù hợp với tập kết quả có kích thước vừa phải. Nếu truy vấn trả hàng triệu hàng, cách gom toàn bộ vào bộ nhớ có thể gây áp lực cấp phát. Hãy giới hạn kết quả bằng `WHERE`, `ORDER BY` và phân trang; khi cần đọc dần, cấu hình `fetchSize` và giao thức streaming theo khả năng hỗ trợ của **driver và DB cụ thể**.

Không trả thẳng `ResultSet` hoặc `Stream` sử dụng `ResultSet` đã bị đóng ra khỏi repository. Nếu cần API đọc tuần tự thật sự, hãy thiết kế rõ ai sở hữu và đóng `Connection`, `Statement`, `ResultSet`, cũng như cách ngừng đọc khi phát sinh lỗi. Với nhiều trường hợp thông thường, trả `List<AccountRow>` đã ánh xạ là đơn giản và an toàn hơn.

### N+1 truy vấn

Nếu `mapRow` tự thực hiện thêm truy vấn để tải quan hệ của từng hàng, một danh sách 100 tài khoản có thể phát sinh 101 truy vấn (1 truy vấn danh sách + 100 truy vấn chi tiết). Việc ánh xạ một hàng nên tránh truy cập mạng hoặc cơ sở dữ liệu bổ sung; nạp dữ liệu cần thiết ở tầng truy vấn bằng `JOIN`, `IN` hoặc nhiều truy vấn theo lô có kế hoạch rõ ràng.

## 9. Xử lý lỗi và kiểm thử ranh giới ánh xạ

Các lỗi có thể xuất hiện ở nhiều tầng khác nhau:

| Lỗi hoặc hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `SQLException: column ... not found` | Mapper đọc nhãn không có trong `SELECT` | So khớp bí danh với các cột trong mapper |
| `NullPointerException` khi gọi `date.toLocalDate()` | SQL `DATE` là `NULL` | Kiểm tra `null` trước khi chuyển đổi |
| Giá trị `NULL` thành `0` hoặc `false` | Dùng getter nguyên thủy mà không gọi `wasNull()` | Chọn kiểu bao và kiểm tra `wasNull()` ngay sau getter |
| `SQLException` lúc đọc hoặc chuyển kiểu | Driver không hỗ trợ chuyển đổi hay dữ liệu không tương thích | Chọn getter phù hợp, xác minh trên driver và DB đích |
| `IllegalArgumentException` khi dựng record | Constructor phát hiện vi phạm hợp đồng Java | Kiểm tra dữ liệu, điều kiện SQL và ràng buộc nghiệp vụ |
| `ResultSet is closed` | Cố đọc lại con trỏ sau khi đóng tài nguyên | Dựng đối tượng đầy đủ bên trong khối mở `ResultSet` |
| Kết quả trùng đối tượng sau `JOIN` | Một đối tượng nghiệp vụ trải trên nhiều hàng | Dùng phép nhóm theo khóa hoặc DTO phẳng đúng mục đích |
| Chậm khi đọc nhiều hàng | Chọn quá nhiều cột, tải quá nhiều hàng hoặc N+1 | Chỉ chọn cột cần thiết, giới hạn trang, đo trên DB thật |

Nên kiểm tra mapper bằng **một cơ sở dữ liệu và driver thật** ở những điểm có thể khác biệt giữa các sản phẩm. Một bộ tình huống tối thiểu cho ví dụ `AccountRow`:

1. **Một hàng hợp lệ**: `findById` trả `Optional` có `AccountRow`, tất cả cột được ánh xạ đúng, `balance` giữ được giá trị `BigDecimal`.
2. **Không tìm thấy hàng**: `findById` trả `Optional.empty()`.
3. **Cột nullable**: `closed_on = NULL` ánh xạ thành `closedOn() == null` mà không phát sinh lỗi.
4. **Nhiều hàng**: `findActiveSince` trả đúng số lượng, đúng thứ tự `ORDER BY` và từng hàng giữ thông tin riêng.
5. **Sai nhãn cột**: thay đổi alias trong truy vấn dẫn tới lỗi dễ phát hiện, từ đó sửa hợp đồng mapper.
6. **Biên số học và ngày**: các giá trị `DECIMAL(12,2)`, ngày trước/sau thời điểm hiện tại và những kiểu dữ liệu đặc biệt của DB được bảo toàn đúng như mong đợi.
7. **Tài nguyên**: thành công hoặc lỗi đều đóng `ResultSet`, `PreparedStatement`, `Connection` đúng cách; đối tượng đã ánh xạ vẫn có thể sử dụng sau khi đóng.

Phân biệt lỗi JDBC với lỗi xác thực: `SQLException` thường phản ánh truy vấn, kết nối hoặc chuyển đổi kiểu ở driver; lỗi từ constructor record phản ánh **hợp đồng đối tượng Java**. Không gộp tất cả vào một ngoại lệ chung mà làm mất thông tin nguyên nhân. Ở tầng ứng dụng, có thể chuyển chúng thành lỗi nghiệp vụ hay lỗi hệ thống phù hợp, kèm ngữ cảnh cần thiết nhưng tránh ghi log dữ liệu riêng tư không cần thiết.

## 10. Thực hành tự kiểm tra

**Bài tập 1 — Đọc record.** Với truy vấn:

```sql
SELECT account_id AS id, display_name, balance
FROM customer_account
WHERE account_id = ?;
```

Hãy thiết kế `record AccountBalance(long id, String displayName, BigDecimal balance)` và hàm `mapAccountBalance(ResultSet rs)`. Hàm phải được gọi **sau** khi `rs.next()` trả `true` và chỉ đọc ba nhãn `id`, `display_name`, `balance`.

**Bài tập 2 — Phân biệt không tìm thấy hàng và cột NULL.** Hãy giải thích vì sao `Optional.empty()` từ `findById` có nghĩa khác với `closedOn() == null` khi đã tìm thấy hàng.

**Gợi ý:** Trường hợp thứ nhất không có hàng thỏa `WHERE`; trường hợp thứ hai có hàng nhưng một thuộc tính được phép chưa có giá trị.

**Bài tập 3 — Kiểm tra `wasNull()`.** Giả sử thêm `manager_id BIGINT NULL` vào truy vấn. Viết cách tạo `Long managerId` không làm `NULL` biến thành `0`:

```java
long rawManagerId = rs.getLong("manager_id");
Long managerId = rs.wasNull() ? null : rawManagerId;
```

**Bài tập 4 — Hiểu giới hạn record.** Vì sao `record GroupRow(long id, List<String> members)` chưa bảo đảm dữ liệu bất biến nếu chỉ giữ nguyên danh sách được truyền vào?

**Gợi ý:** Danh sách đầu vào có thể bị sửa từ nơi khác. Hãy dùng `List.copyOf` trong constructor và xem xét tính bất biến của từng phần tử.

**Bài tập 5 — Thiết kế truy vấn nhiều hàng.** Một phép `LEFT JOIN` giữa `customer_account` và `account_tag` có thể tạo nhiều hàng cho cùng `account_id`. Chọn giữa DTO phẳng cho mỗi hàng hoặc nhóm toàn bộ tag theo `account_id` trước khi tạo đối tượng bất biến; giải thích lựa chọn theo mục đích sử dụng kết quả.

## Tổng kết

Ánh xạ hàng JDBC an toàn bắt đầu bằng việc xác định **hợp đồng cột truy vấn** và **kiểu dữ liệu Java** tương ứng. Repository dùng `PreparedStatement` và `ResultSet` để đọc, gọi `mapRow` ở mỗi hàng hợp lệ, rồi trả về `record` hoặc lớp bất biến độc lập với kết nối. Chú ý xử lý SQL `NULL`, đặt bí danh rõ ràng, dùng getter phù hợp (`getBigDecimal` cho `DECIMAL`, kiểu ngày phù hợp cho `DATE`) và quản lý tài nguyên bằng `try-with-resources`. Khi cấu trúc truy vấn vượt khỏi quan hệ “một hàng, một giá trị”, hãy tổ chức phép nhóm hoặc truy vấn bổ sung có chủ đích thay vì trộn toàn bộ logic vào hàm ánh xạ.
