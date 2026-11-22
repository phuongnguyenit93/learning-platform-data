# Vai trò của FilteredRowSet và JoinRowSet trong JDBC

## 1. Tại sao cần RowSet ngoại tuyến?

Khi làm việc với **JDBC**, cách phổ biến để đọc dữ liệu là thực thi SQL qua `PreparedStatement` rồi duyệt `ResultSet`. Trong mô hình này, `ResultSet` thường gắn với `Statement` và `Connection` đang mở. Đọc hàng, đóng tài nguyên và xử lý transaction phải diễn ra đúng vòng đời của kết nối.

Nhưng không phải thao tác nào cũng cần giữ kết nối với cơ sở dữ liệu:

- Một màn hình cần lấy danh sách nhân viên **một lần**, rồi chuyển qua lại giữa những tập nhân viên đáp ứng điều kiện lọc mà không truy vấn lại ngay.
- Một công cụ quản trị đã tải hai tập dữ liệu nhỏ và muốn **ghép** chúng tại phía Java để xem thông tin kết hợp.
- Một quy trình cần xử lý bản sao dữ liệu, có thể kiểm tra hoặc chỉnh sửa tạm thời trước khi quyết định đồng bộ trở lại database.
- Một bộ kiểm thử muốn thao tác tập hàng có metadata và con trỏ giống JDBC nhưng không duy trì `Connection` trong toàn bộ bước tính toán.

Các giao diện **RowSet** trong `javax.sql.rowset` hỗ trợ những nhu cầu này. Trong đó:

- **`FilteredRowSet`** cung cấp một góc nhìn được lọc bằng đối tượng `Predicate` trên dữ liệu RowSet.
- **`JoinRowSet`** giúp kết hợp hai hoặc nhiều RowSet dựa trên những cột dùng để ghép (*match columns*).
- **`CachedRowSet`** là kiểu nền tảng hữu ích để giữ bản sao dữ liệu ở bộ nhớ và làm việc khi đã đóng kết nối.

Bài thuộc chương **RowSet ngoại tuyến** của module **JDBC**, gắn với việc lấy dữ liệu qua driver, `DataSource`, `PreparedStatement` và `ResultSet`, xử lý SQL tham số hóa, quản lý kết nối và hiểu ranh giới transaction. Trọng tâm ở đây là **vai trò, cách dùng, giới hạn và tiêu chí lựa chọn** giữa `FilteredRowSet` và `JoinRowSet`, không coi chúng là bản thay thế toàn diện cho SQL.

Sau bài này, bạn có thể tạo RowSet qua `RowSetProvider`, lọc hàng bằng `Predicate`, ghép dữ liệu theo khóa khớp, nhận biết các trường hợp cần SQL `WHERE`/`JOIN` thay vì lọc/ghép phía Java, và tránh hiểu nhầm dữ liệu ngoại tuyến là dữ liệu đang được cập nhật tự động.

## 2. Đặt FilteredRowSet và JoinRowSet vào đúng hệ thống API

Các kiểu liên quan thuộc Java/JDBC chuẩn:

```text
javax.sql.RowSet
  |
  +-- javax.sql.rowset.CachedRowSet
          |
          +-- javax.sql.rowset.WebRowSet
                  |
                  +-- javax.sql.rowset.FilteredRowSet
                  |
                  +-- javax.sql.rowset.JoinRowSet
```

Sơ đồ nhấn mạnh quan hệ mở rộng giao diện; việc tạo đối tượng cụ thể do **RowSet provider** đảm nhiệm.

Trong Java hiện đại, nên dùng factory:

```java
import javax.sql.rowset.RowSetFactory;
import javax.sql.rowset.RowSetProvider;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.FilteredRowSet;
import javax.sql.rowset.JoinRowSet;

RowSetFactory factory = RowSetProvider.newFactory();

CachedRowSet cached = factory.createCachedRowSet();
FilteredRowSet filtered = factory.createFilteredRowSet();
JoinRowSet joined = factory.createJoinRowSet();
```

Đây là ví dụ tạo đối tượng; trong ứng dụng thực tế cần **đóng các RowSet** sau khi sử dụng, chẳng hạn bằng `try-with-resources`. API `RowSetProvider` nằm trong module `java.sql.rowset` khi xây dựng ứng dụng Java sử dụng JPMS.

### 2.1. So sánh nhanh ba loại RowSet

| Giao diện | Trách nhiệm chính | Tình huống phù hợp |
|---|---|---|
| `CachedRowSet` | Giữ một tập hàng/metadata trong bộ nhớ, có thể làm việc sau khi kết nối đã đóng | Đọc snapshot nhỏ, tách bước nhận dữ liệu khỏi bước xử lý |
| `FilteredRowSet` | Hiển thị/điều hướng các hàng thỏa `Predicate` và áp dụng predicate trong những thao tác cập nhật phù hợp | Lọc dữ liệu **đã nạp** theo điều kiện ở Java |
| `JoinRowSet` | Ghép các RowSet theo cột khớp thành một kết quả liên hợp | Kết hợp những tập dữ liệu nhỏ đã có ở phía Java |

Hai điểm quan trọng:

1. **“Ngoại tuyến” không có nghĩa không từng kết nối tới DB.** RowSet có thể được nạp từ `ResultSet` lúc `Connection` đang mở, rồi xử lý về sau khi kết nối đã đóng.
2. **“Ngoại tuyến” không có nghĩa tự đồng bộ trở lại DB.** Nếu RowSet hỗ trợ sửa dữ liệu, việc ghi lại vẫn cần cơ chế đồng bộ, quyền cập nhật, thông tin khóa, kết nối và xử lý conflict phù hợp; chỉ gọi `updateString(...)` hoặc thay bộ lọc không làm DB tự thay đổi.

## 3. Ví dụ dữ liệu: nhân viên và phòng ban

Để thống nhất ví dụ, giả sử cơ sở dữ liệu có hai bảng:

```sql
CREATE TABLE departments (
    id   BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    id            BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL REFERENCES departments(id),
    full_name     VARCHAR(100) NOT NULL,
    status        VARCHAR(15) NOT NULL
);

INSERT INTO departments (id, name)
VALUES (7, 'Engineering'), (8, 'Sales');

INSERT INTO employees (id, department_id, full_name, status)
VALUES
    (101, 7, 'An',   'ACTIVE'),
    (102, 7, 'Bình', 'INACTIVE'),
    (103, 8, 'Chi',  'ACTIVE'),
    (104, 8, 'Dung', 'ACTIVE');
```

DDL và cú pháp chèn nhiều hàng ở đây có tính minh họa; cần điều chỉnh khi driver hoặc hệ quản trị yêu cầu dialect khác.

Hãy xét hai nhu cầu:

- **Lọc:** tải nhân viên phòng ban 7 rồi chỉ hiển thị những người có `status = 'ACTIVE'`.
- **Ghép:** tải danh sách nhân viên phòng ban 7 và thông tin phòng ban 7 thành hai RowSet, sau đó ghép chúng theo `department_id` để có tên nhân viên kèm tên phòng ban.

Các kết quả kỳ vọng:

| Thao tác | Hàng nhìn thấy |
|---|---|
| Dữ liệu nhân viên phòng 7 chưa lọc | An (ACTIVE), Bình (INACTIVE) |
| `FilteredRowSet` với điều kiện ACTIVE | An |
| `JoinRowSet` giữa nhân viên phòng 7 và phòng ban 7, dạng inner join | An — Engineering; Bình — Engineering |
| Inner join khi phòng ban không có hàng ghép phù hợp | Không có hàng tương ứng ở kết quả ghép |

Kết quả của bộ lọc khác kết quả ghép: **lọc chọn một tập con của hàng**, còn **ghép tạo hàng kết hợp từ nhiều nguồn**.

## 4. Vai trò của FilteredRowSet

### 4.1. Predicate là gì?

`FilteredRowSet` dùng một đối tượng triển khai `javax.sql.rowset.Predicate` để xác định hàng nào đáp ứng điều kiện hiển thị. Giao diện có ba phương thức:

```java
boolean evaluate(javax.sql.RowSet rowSet);
boolean evaluate(Object value, int column);
boolean evaluate(Object value, String columnName);
```

Ý nghĩa thực tế:

- **`evaluate(RowSet)`** kiểm tra hàng hiện tại trong quá trình RowSet lọc/điều hướng; có thể đọc các cột của hàng đó qua getter.
- **`evaluate(Object, int)`** và **`evaluate(Object, String)`** giúp đánh giá một giá trị theo vị trí hoặc tên cột trong ngữ cảnh thao tác sửa/thêm dữ liệu mà implementation sử dụng.
- Điều kiện lọc nằm trong **code Java**, không phải mệnh đề `WHERE` được DB thực thi.

Vì `Predicate` không khai báo `throws SQLException`, cần quyết định rõ cách phản ứng nếu đọc dữ liệu hàng gặp lỗi: ví dụ ném một exception không kiểm tra được để làm lỗi lộ ra, thay vì âm thầm đánh dấu mọi hàng là không hợp lệ.

### 4.2. Viết predicate lọc nhân viên ACTIVE

Truy vấn dùng cho ví dụ sẽ lấy bốn cột theo đúng thứ tự:

```sql
SELECT e.id            AS employee_id,
       e.full_name     AS full_name,
       e.status        AS status,
       e.department_id AS department_id
FROM employees e
WHERE e.department_id = ?
ORDER BY e.id
```

Vị trí `status` là cột thứ 3. Predicate sau dùng trạng thái `ACTIVE`:

```java
import javax.sql.RowSet;
import javax.sql.rowset.Predicate;
import java.sql.SQLException;

public final class ActiveEmployeePredicate implements Predicate {
    private static final int STATUS_COLUMN_INDEX = 3;
    private static final String STATUS_COLUMN_NAME = "status";

    @Override
    public boolean evaluate(RowSet row) {
        try {
            return "ACTIVE".equals(row.getString(STATUS_COLUMN_NAME));
        } catch (SQLException failure) {
            throw new IllegalStateException(
                    "Không thể đọc status để lọc RowSet", failure);
        }
    }

    @Override
    public boolean evaluate(Object value, int column) {
        // Chỉ áp dụng điều kiện cho cột status.
        return column != STATUS_COLUMN_INDEX
                || "ACTIVE".equals(value);
    }

    @Override
    public boolean evaluate(Object value, String columnName) {
        return !STATUS_COLUMN_NAME.equalsIgnoreCase(columnName)
                || "ACTIVE".equals(value);
    }
}
```

**Vì sao cần cả ba overload?** Một implementation có thể cần kiểm tra hàng khi di chuyển con trỏ và kiểm tra giá trị của cột khi thao tác sửa/thêm. Mã ví dụ cho phép giá trị của các cột khác đi qua, còn cột `status` phải là `ACTIVE` để thỏa predicate. Việc xác định cột thứ 3 là **ràng buộc theo thứ tự SELECT**; nếu đổi thứ tự các cột, phải cập nhật code hoặc thiết kế mapping khác.

**Lưu ý:** Predicate không phải cơ chế bắt buộc để validate dữ liệu nghiệp vụ ở DB. Ràng buộc về giá trị trạng thái nên có ở nơi thích hợp (schema/validation/service), kể cả khi ứng dụng dùng RowSet để lọc tạm thời.

### 4.3. Nạp FilteredRowSet, đóng JDBC rồi mới lọc

Ví dụ Java 17+ dùng `DataSource`, SQL tham số hóa và `ResultSet`:

```java
import javax.sql.DataSource;
import javax.sql.rowset.FilteredRowSet;
import javax.sql.rowset.RowSetProvider;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class EmployeeFilterService {
    public record Employee(
            long id,
            String fullName,
            String status
    ) {}

    private final DataSource dataSource;

    public EmployeeFilterService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Employee> findActiveInDepartment(long departmentId)
            throws SQLException {
        String sql = """
                SELECT e.id            AS employee_id,
                       e.full_name     AS full_name,
                       e.status        AS status,
                       e.department_id AS department_id
                FROM employees e
                WHERE e.department_id = ?
                ORDER BY e.id
                """;

        try (FilteredRowSet rowSet =
                     RowSetProvider.newFactory().createFilteredRowSet()) {

            // Lấy dữ liệu qua JDBC; populate sao chép các hàng vào RowSet.
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setLong(1, departmentId);

                try (ResultSet rs = ps.executeQuery()) {
                    rowSet.populate(rs);
                }
            }

            // JDBC resources đã đóng; thực hiện lọc trên RowSet.
            rowSet.setFilter(new ActiveEmployeePredicate());
            rowSet.beforeFirst();

            List<Employee> result = new ArrayList<>();
            while (rowSet.next()) {
                long id = rowSet.getLong("employee_id");
                if (rowSet.wasNull()) {
                    throw new SQLException("employee_id không được NULL");
                }

                result.add(new Employee(
                        id,
                        rowSet.getString("full_name"),
                        rowSet.getString("status")
                ));
            }
            return List.copyOf(result);
        }
    }
}
```

Phân biệt rõ ba giai đoạn:

1. **Truy vấn DB:** `PreparedStatement` và `ResultSet` được dùng khi kết nối đang mở, với `department_id = ?` được bind an toàn.
2. **Tạo snapshot:** `rowSet.populate(rs)` sao chép dữ liệu của kết quả vào RowSet. Lúc này chi phí bộ nhớ phụ thuộc số lượng hàng và độ rộng của cột.
3. **Lọc ngoại tuyến:** sau khi đóng connection, `rowSet.setFilter(...)` và `rowSet.next()` hoạt động trên các hàng đã nạp, không gửi lại `SELECT` tới DB trong ví dụ.

Với dữ liệu mục 3, gọi `findActiveInDepartment(7)` trả về danh sách chỉ có **An**. Trạng thái `INACTIVE` của Bình vẫn là dữ liệu đã được lấy từ DB, nhưng không xuất hiện trong vòng lặp khi predicate đang có hiệu lực.

### 4.4. Thay bộ lọc không đồng nghĩa xóa dữ liệu

Một RowSet đã nạp có thể đổi bộ lọc:

```java
rowSet.setFilter(new ActiveEmployeePredicate());
rowSet.beforeFirst();
while (rowSet.next()) {
    // Chỉ các hàng ACTIVE được lộ ra trong lần duyệt này.
}

// Khi muốn bỏ filter, với provider hỗ trợ theo hợp đồng:
rowSet.setFilter(null);
rowSet.beforeFirst();
while (rowSet.next()) {
    // Duyệt tập dữ liệu đã nạp mà không dùng filter.
}
```

Đoạn trích giả định `rowSet` là `FilteredRowSet` còn mở. Dữ liệu bị ẩn do predicate **không tự bị xóa** khỏi bản sao ngoại tuyến. Đây là một điểm khác với SQL `DELETE`, hoặc với việc query DB bằng `WHERE status = 'ACTIVE'` ngay từ đầu.

Vì vậy, **không dùng FilteredRowSet để thực thi bảo mật mức hàng**. Nếu người dùng chỉ có quyền đọc nhân viên trong một tenant, điều kiện tenant và quyền truy cập phải được áp dụng ở tầng DB/API trước khi dữ liệu được tải, thay vì tải tất cả về rồi chỉ ẩn một số hàng bằng predicate.

## 5. FilteredRowSet so với WHERE trong SQL

| Tiêu chí | SQL `WHERE` | `FilteredRowSet` |
|---|---|---|
| Nơi thực thi | Cơ sở dữ liệu | Trong Java, trên dữ liệu RowSet đã có |
| Dữ liệu truyền từ DB | Chỉ những hàng SQL trả về | Vẫn cần truyền những hàng được nạp trước khi lọc |
| Dùng chỉ mục của DB | DB có thể dùng index, optimizer và thống kê | Không thay thế khả năng tối ưu SQL bằng index |
| Điều kiện lọc | Dựa trên SQL/dialect và giá trị bind | Dựa trên `Predicate` Java |
| Thay điều kiện không query lại | Không mặc định; thường cần gửi SQL mới | Có thể thay predicate trên snapshot đang có |
| Dữ liệu mới được cập nhật từ DB | Truy vấn lại lấy dữ liệu theo trạng thái DB hiện tại | Không tự thấy cập nhật bên ngoài nếu không nạp lại |
| Quyền truy cập dữ liệu | Có thể áp dụng khi truy vấn/DB policy | Không phải ranh giới phân quyền |
| Tập dữ liệu lớn | Thường phù hợp hơn khi lọc càng sớm càng tốt | Có thể tiêu thụ nhiều bộ nhớ và CPU nếu đã tải nhiều hàng |

**Nên ưu tiên SQL `WHERE`** khi điều kiện đã biết trước lúc query, nhất là với hàng triệu bản ghi hoặc dữ liệu nhạy cảm. `FilteredRowSet` có lợi khi tập dữ liệu đã được tải và ứng dụng cần nhiều **góc nhìn cục bộ** mà chưa muốn thực hiện thêm round-trip tới DB.

Hai cách không loại trừ nhau. Trong ví dụ, SQL `WHERE department_id = ?` thu hẹp dữ liệu theo phòng ban, còn Java predicate chọn trạng thái ACTIVE trong **tập nhỏ đã nạp**.

## 6. Vai trò của JoinRowSet

### 6.1. Ghép hai tập dữ liệu đã có mà không gửi SQL JOIN mới

`JoinRowSet` cho phép ghép nhiều RowSet dựa trên những cột được chỉ định là **match columns**. Đây là phép kết hợp dữ liệu phía Java và thích hợp cho các tập dữ liệu ngoại tuyến nhỏ.

Khái niệm:

```text
CachedRowSet nhân viên                 CachedRowSet phòng ban
+-------------+---------+              +---------------+-------------+
| employee_id | dept_id |              | department_id | dept_name   |
+-------------+---------+              +---------------+-------------+
| 101         | 7       |              | 7             | Engineering |
| 102         | 7       |              | 8             | Sales       |
+-------------+---------+              +---------------+-------------+
        |                                   |
        +------- match dept_id = department_id ----+
                                                    |
                                                    v
                                  JoinRowSet (inner join)
                                  101, Engineering
                                  102, Engineering
```

`JoinRowSet` có các phương thức như:

- `addRowSet(RowSet rowSet)`: thêm RowSet đã được cấu hình match column.
- `addRowSet(RowSet rowSet, int columnIdx)` hoặc `addRowSet(RowSet rowSet, String columnName)`: thêm RowSet với cột khớp được chỉ định.
- `setJoinType(int joinType)`: chọn loại join được provider hỗ trợ.
- `supportsJoinType(int joinType)`: kiểm tra khả năng hỗ trợ một kiểu join.
- `getJoinType()`: truy vấn loại join đang dùng.
- `getWhereClause()`: cung cấp dạng diễn giải về điều kiện ghép của RowSet; không coi đó là câu SQL để tự thực thi thay vì join.

Bản thân việc `addRowSet` không giống gọi `Connection.prepareStatement("SELECT ... JOIN ...")`. Nó **không thay thế SQL join trong database**; các RowSet nguồn thường đã được nạp vào bộ nhớ phía Java.

### 6.2. Match columns phải có ý nghĩa quan hệ rõ ràng

Với schema ví dụ:

- Cột bên nhân viên: `employee_department_id`.
- Cột bên phòng ban: `department_id`.

Hai cột đều có kiểu `BIGINT` và cùng biểu diễn khóa phòng ban. Không nên ghép hai cột chỉ vì chúng có cùng tên nhưng ý nghĩa khác nhau (ví dụ `employee_id` với `department_id`).

Nếu một phòng ban có 10 nhân viên, inner join theo phòng ban có thể tạo **10 hàng**. Nếu cả hai phía chứa các khóa ghép lặp, số hàng liên hợp có thể tăng theo số cặp khớp. Ví dụ có 2 hàng bên trái và 3 hàng bên phải cùng match key, một phép inner join kiểu quan hệ có thể tạo **6 hàng** cho khóa đó; đừng mặc định đây là kết quả 1–1.

Khi giá trị match key là SQL `NULL` hoặc kiểu dữ liệu khác nhau, cách xử lý và khả năng tương thích phải được kiểm tra với provider và schema thực tế. Trong ví dụ, khóa được thiết kế `NOT NULL` và cùng kiểu để tránh tình huống mơ hồ.

## 7. Ví dụ Java: ghép hai CachedRowSet theo phòng ban

### 7.1. Nạp hai snapshot trong khi còn Connection

Ví dụ dưới đây cố ý tách hai truy vấn và chỉ join sau khi connection đã đóng. Hai truy vấn dùng cùng tham số `departmentId`.

```java
import javax.sql.DataSource;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.JoinRowSet;
import javax.sql.rowset.RowSetFactory;
import javax.sql.rowset.RowSetProvider;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class OfflineEmployeeJoin {
    public record EmployeeDepartment(
            long employeeId,
            String employeeName,
            String departmentName
    ) {}

    private static final String EMPLOYEES_SQL = """
            SELECT e.id            AS employee_id,
                   e.full_name     AS employee_name,
                   e.department_id AS employee_department_id
            FROM employees e
            WHERE e.department_id = ?
            ORDER BY e.id
            """;

    private static final String DEPARTMENTS_SQL = """
            SELECT d.id   AS department_id,
                   d.name AS department_name
            FROM departments d
            WHERE d.id = ?
            """;

    private final DataSource dataSource;

    public OfflineEmployeeJoin(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public List<EmployeeDepartment> joinInMemory(long departmentId)
            throws SQLException {
        RowSetFactory factory = RowSetProvider.newFactory();

        try (CachedRowSet employees = factory.createCachedRowSet();
             CachedRowSet departments = factory.createCachedRowSet();
             JoinRowSet joined = factory.createJoinRowSet()) {

            // Chỉ lúc populate() mới cần JDBC Connection/ResultSet.
            try (Connection connection = dataSource.getConnection()) {
                try (PreparedStatement ps =
                             connection.prepareStatement(EMPLOYEES_SQL)) {
                    ps.setLong(1, departmentId);
                    try (ResultSet rs = ps.executeQuery()) {
                        employees.populate(rs);
                    }
                }

                try (PreparedStatement ps =
                             connection.prepareStatement(DEPARTMENTS_SQL)) {
                    ps.setLong(1, departmentId);
                    try (ResultSet rs = ps.executeQuery()) {
                        departments.populate(rs);
                    }
                }
            }

            // Từ đây Connection đã đóng; join dùng các hàng đã nạp.
            employees.setMatchColumn("employee_department_id");
            departments.setMatchColumn("department_id");

            if (!joined.supportsJoinType(JoinRowSet.INNER_JOIN)) {
                throw new SQLException(
                        "RowSet provider không hỗ trợ INNER_JOIN");
            }
            joined.setJoinType(JoinRowSet.INNER_JOIN);
            joined.addRowSet(employees);
            joined.addRowSet(departments);

            List<EmployeeDepartment> result = new ArrayList<>();
            joined.beforeFirst();

            while (joined.next()) {
                // Alias giúp phân biệt các cột của hai nguồn.
                // Cần kiểm tra metadata cột trên provider cụ thể.
                long employeeId = joined.getLong("employee_id");
                if (joined.wasNull()) {
                    throw new SQLException("employee_id không hợp lệ");
                }

                result.add(new EmployeeDepartment(
                        employeeId,
                        joined.getString("employee_name"),
                        joined.getString("department_name")
                ));
            }
            return List.copyOf(result);
        }
    }
}
```

Ví dụ cho thấy **không dùng `Connection` trong bước ghép**. Mỗi `CachedRowSet` đã chứa dữ liệu và metadata cần thiết. Kết quả từ `JoinRowSet` được ánh xạ thành các Java record; danh sách trả về độc lập với tài nguyên JDBC đã đóng.

Trong một số provider, nhãn/tên cột sau join có thể được xử lý khác nhau, đặc biệt với cột khóa trùng hoặc cột có alias. Vì vậy, **đừng mặc định vị trí hay tên cột của kết quả join y hệt hai nguồn cộng lại**. Có thể đọc `joined.getMetaData()` để kiểm tra `getColumnCount()`, `getColumnLabel(i)`, `getColumnName(i)` và kiểu dữ liệu, sau đó cố định hợp đồng bằng kiểm thử tích hợp.

### 7.2. Kết quả mong đợi và ý nghĩa

Với dữ liệu mục 3:

```text
joinInMemory(7)
    -> EmployeeDepartment(101, "An",   "Engineering")
    -> EmployeeDepartment(102, "Bình", "Engineering")

joinInMemory(8)
    -> EmployeeDepartment(103, "Chi",  "Sales")
    -> EmployeeDepartment(104, "Dung", "Sales")
```

Nếu tập phòng ban không chứa phòng ban tương ứng, **inner join** không trả ra các nhân viên không có hàng ghép. Đó là ngữ nghĩa của join, không phải cơ chế báo lỗi JDBC.

Phép ghép tại Java không tự cập nhật khi dữ liệu phòng ban thay đổi trong database sau khi đã nạp snapshot. Nếu muốn kết quả mới, phải chạy lại bước nhận dữ liệu thích hợp, hoặc dùng một cách đồng bộ rõ ràng.

### 7.3. Xác minh cột sau join bằng ResultSetMetaData

Nếu gặp lỗi như “column not found” ở tên alias sau join, hãy quan sát metadata:

```java
import java.sql.ResultSetMetaData;

ResultSetMetaData meta = joined.getMetaData();
for (int i = 1; i <= meta.getColumnCount(); i++) {
    System.out.printf(
            "column=%d label=%s name=%s type=%d%n",
            i,
            meta.getColumnLabel(i),
            meta.getColumnName(i),
            meta.getColumnType(i)
    );
}
```

Đoạn này giả định `joined` đang mở. Đặt việc kiểm tra trong kiểm thử/diagnostic, không in cấu trúc schema nhạy cảm vào log công khai. Những trường hợp nhiều nguồn có cột cùng tên, có cột bị gộp hoặc thứ tự thay đổi nên được xử lý bằng mapping đã được kiểm chứng trên RowSet provider thực tế.

## 8. JoinRowSet hỗ trợ những loại JOIN nào?

`JoinRowSet` có các hằng loại join, bao gồm:

| Hằng | Ngữ nghĩa quan hệ kỳ vọng |
|---|---|
| `JoinRowSet.INNER_JOIN` | Chỉ giữ các cặp hàng có match key khớp |
| `JoinRowSet.LEFT_OUTER_JOIN` | Giữ cả hàng phía trái không có đối tác, điền NULL cho cột phía phải |
| `JoinRowSet.RIGHT_OUTER_JOIN` | Giữ cả hàng phía phải không có đối tác |
| `JoinRowSet.FULL_JOIN` | Giữ hàng của cả hai phía khi không có đối tác |
| `JoinRowSet.CROSS_JOIN` | Tạo các cặp kết hợp theo tích Đề-các |

**Hằng có trong API không chứng minh implementation hỗ trợ loại join đó.** Nhiều provider chỉ thực sự hỗ trợ `INNER_JOIN`. Phải kiểm tra bằng `supportsJoinType(type)` trước khi gọi `setJoinType(type)` và thử thực tế với provider được dùng.

Ví dụ kiểm tra:

```java
if (joined.supportsJoinType(JoinRowSet.LEFT_OUTER_JOIN)) {
    joined.setJoinType(JoinRowSet.LEFT_OUTER_JOIN);
    // Sau đó tạo join và kiểm tra hàng không có match.
} else {
    // Cân nhắc thực hiện LEFT JOIN bằng SQL tại database.
}
```

Nếu nghiệp vụ **bắt buộc** giữ những hàng bên trái không có khóa khớp, đừng viết code sử dụng `LEFT_OUTER_JOIN` mà bỏ qua khả năng unsupported. Giải pháp thay thế đơn giản hơn thường là SQL `LEFT JOIN` trên DB, hoặc một thuật toán ghép riêng có kiểm thử chặt chẽ.

### 8.1. Những giới hạn thực tế của JoinRowSet

- Tập trung vào ghép theo **cột khớp**, không phải cơ chế đầy đủ để biểu đạt mọi predicate join phức tạp (dải giá trị, bất đẳng thức, nhiều điều kiện tuỳ ý).
- Các nguồn đã được tải vào Java nên bộ nhớ và thời gian xử lý tăng theo số hàng và cấu trúc khóa.
- Nếu có nhiều cặp match, kết quả có thể lớn hơn từng nguồn và cần xem nguy cơ nhân bản hàng.
- Cách biểu diễn NULL, tên cột, thứ tự cột và các chức năng nâng cao có thể khác nhau giữa provider.
- Việc nhận một kết quả join không chứng minh có thể **ghi ngược an toàn vào nhiều bảng**; cập nhật các nguồn thường cần repository/transaction riêng.

## 9. SQL JOIN so với JoinRowSet: chọn đúng nơi xử lý

Nếu hai bảng đều ở cùng database và chỉ cần kết quả kết hợp một lần, SQL thường đơn giản và hiệu quả hơn:

```sql
SELECT e.id AS employee_id,
       e.full_name AS employee_name,
       d.name AS department_name
FROM employees e
JOIN departments d ON d.id = e.department_id
WHERE e.department_id = ?
ORDER BY e.id;
```

`PreparedStatement` gán `department_id` ở dấu `?`. Database có thể dùng index và optimizer để chỉ trả dữ liệu cần thiết, thay vì tải hai RowSet về JVM rồi mới ghép.

| Tiêu chí | `JOIN` trong SQL | `JoinRowSet` |
|---|---|---|
| Nơi xử lý | Database | Ứng dụng Java |
| Cần kết nối trong lúc join | Có cho truy vấn; có thể đóng sau khi lấy kết quả | Không cần kết nối ở bước join nếu các RowSet đã được nạp |
| Khả năng tối ưu | Có optimizer, index, join algorithms của DB | Phụ thuộc RowSet provider và dữ liệu trong bộ nhớ |
| Tính năng join | Theo khả năng dialect SQL (INNER/OUTER/... và predicate) | Phải kiểm tra `supportsJoinType`; thường giới hạn hơn |
| Dữ liệu cần truyền | Có thể chỉ trả projection sau join và filter | Các nguồn phải được truyền/nạp trước khi ghép |
| Thay đổi dữ liệu ngoài ứng dụng | Query lại có thể lấy trạng thái mới | RowSet đã nạp là snapshot, không tự refresh |
| Dữ liệu nguồn từ những kết quả đã có | Có thể cần query lại hoặc đưa dữ liệu trở lại DB | Hữu ích khi đã có nhiều RowSet nhỏ và không muốn query ngay |
| Quyền truy cập | Có thể thực thi tại DB theo schema/policy | Không nên dùng làm ranh giới quyền đọc |

**Quy tắc chọn:** dùng `JoinRowSet` khi giá trị nằm ở việc **tái sử dụng dữ liệu đã nạp** hoặc xử lý ngoại tuyến một tập nhỏ. Nếu mục tiêu là truy vấn dữ liệu lớn từ nhiều bảng trên DB, ưu tiên SQL `JOIN` với `WHERE` và projection phù hợp.

Đừng cố thay hết SQL JOIN bằng JoinRowSet chỉ vì ứng dụng muốn “ít phụ thuộc DB”. Bản thân schema, kiểu dữ liệu và cú pháp chọn dữ liệu vẫn phụ thuộc SQL và driver; việc chuyển join sang Java có thể tăng chi phí mạng/bộ nhớ đáng kể.

## 10. Kết hợp FilteredRowSet và JoinRowSet

Hai giao diện giải quyết hai việc khác nhau nên có thể xuất hiện trong cùng pipeline:

```text
ResultSet (từ SELECT có WHERE phù hợp)
          |
          v
CachedRowSet / FilteredRowSet
          |
   setFilter(Predicate)
          |
          v
Các hàng phù hợp trong snapshot
          |
       match column <------ CachedRowSet phòng ban
          |
          v
JoinRowSet
          |
          v
DTO cho màn hình
```

Ví dụ, lọc nhân viên ACTIVE rồi ghép tên phòng ban. Về ý tưởng, `FilteredRowSet` là một RowSet, nên có thể được cấp làm nguồn cho `JoinRowSet`; tuy nhiên, cần kiểm thử cụ thể việc provider áp dụng predicate lên những hàng nào trong lúc join và cách quản lý match column. Nếu việc lọc là điều kiện bắt buộc của dữ liệu đầu ra, một phương án dễ kiểm chứng hơn là:

1. **Lọc sớm tại SQL** bằng `WHERE e.status = ?` và điều kiện phòng ban/tenant phù hợp.
2. Chỉ populate dữ liệu đã được phép và thực sự cần dùng.
3. Dùng `JoinRowSet` nếu những nguồn này còn phải ghép ngoại tuyến.

Nếu yêu cầu cần thay đổi nhiều bộ lọc tại Java sau khi đã có kết quả join nhỏ, cũng có thể cân nhắc dùng `FilteredRowSet` chứa những hàng kết quả rồi áp dụng `Predicate` trên dữ liệu đó. Nhưng phải kiểm tra metadata, hỗ trợ của provider và chi phí sao chép dữ liệu.

**Không coi chuỗi “FilteredRowSet → JoinRowSet” là một câu SQL ảo được tự tối ưu.** Các phép lọc/ghép diễn ra trên dữ liệu đã được tải, nên thứ tự thực hiện có thể ảnh hưởng đến bộ nhớ, số hàng, và cách nhận diện tên cột.

## 11. Vòng đời kết nối, dữ liệu cũ và việc đồng bộ

### 11.1. RowSet ngoại tuyến không cập nhật khi DB thay đổi

Xét trình tự:

```text
10:00:00  JDBC SELECT -> populate CachedRowSet/FilteredRowSet
10:00:01  Đóng Connection
10:01:00  Một transaction khác sửa departments.name
10:02:00  JoinRowSet ghép dữ liệu đã lưu ở 10:00:00
```

Kết quả join dùng tên phòng ban **cũ trong snapshot**, không tự đồng bộ với transaction lúc 10:01. Nếu nghiệp vụ cần thấy dữ liệu mới, phải thiết kế refresh/repopulate hoặc truy vấn mới.

Thậm chí hai RowSet được nạp ở **hai câu SELECT khác nhau** trên cùng Connection cũng không mặc định là một snapshot nhất quán theo thời gian: mức isolation và cách DB thực thi mỗi truy vấn quyết định điều đó. Nếu yêu cầu đọc nhất quán giữa hai bảng, cần transaction/isolation phù hợp ở bước nạp dữ liệu.

### 11.2. acceptChanges và đồng bộ không phải chức năng của bộ lọc

`CachedRowSet` và các giao diện mở rộng có thể hỗ trợ thao tác sửa hàng và phương thức `acceptChanges(...)` để yêu cầu đồng bộ thay đổi về nguồn dữ liệu theo cơ chế `SyncProvider`/writer của RowSet provider. Tuy nhiên:

- Không có nghĩa chỉ tạo một `FilteredRowSet`, sửa vài trường và gọi `acceptChanges()` là mọi bản ghi được cập nhật thành công. Có thể cần cấu hình command, table name, key columns, DataSource/connection và provider phù hợp.
- Nếu dữ liệu DB đã thay đổi kể từ khi nạp, quá trình đồng bộ có thể gặp **xung đột** và ném `SyncProviderException`; cần đọc và giải quyết theo hợp đồng.
- `JoinRowSet` kết hợp dữ liệu nhiều nguồn **không phải một repository ORM** có thể tự chia một lần update kết quả join thành những lệnh UPDATE đúng cho mọi bảng nguồn.
- Nếu nghiệp vụ phải sửa nhiều bảng cùng nguyên tử, dùng `Connection` và transaction rõ ràng ở tầng repository, thay vì trông cậy vào hiệu ứng phụ không kiểm soát từ một RowSet ngoại tuyến.

Với các ví dụ của bài này, hai giao diện được dùng **để đọc**. Không gọi `acceptChanges()` và không ghi ngược DB, vì trọng tâm là vai trò lọc/ghép.

### 11.3. Trách nhiệm đóng tài nguyên

Trong các ví dụ:

| Tài nguyên | Thời điểm đóng |
|---|---|
| `ResultSet` từ JDBC | Sau khi `populate(...)` đã hoàn tất |
| `PreparedStatement` | Sau khi đã thực thi và lấy dữ liệu |
| `Connection` | Sau khi đã nạp những RowSet cần thiết |
| `FilteredRowSet`/`CachedRowSet`/`JoinRowSet` | Sau khi đã điều hướng, lọc/ghép và ánh xạ kết quả |
| DTO/`List` đã tạo | Có thể sử dụng sau khi mọi tài nguyên JDBC đã đóng |

Đóng kết nối trước khi dùng RowSet ngoại tuyến là mục tiêu của ví dụ, nhưng **không được đóng ResultSet trong lúc `populate(...)` đang còn chạy**. `populate(...)` có thể cần duyệt hết tập kết quả nên với bảng lớn có thể làm giữ kết nối khá lâu.

## 12. Rủi ro về hiệu năng, bộ nhớ và bảo mật

### 12.1. Bộ nhớ và độ lớn snapshot

Nếu một `ResultSet` chứa 500.000 hàng với nhiều cột chuỗi dài hoặc BLOB, việc `populate` tất cả vào RowSet có thể chiếm rất nhiều RAM. Sau đó:

- `FilteredRowSet` chỉ thay góc nhìn; những hàng không phù hợp **vẫn đã được tải**.
- `JoinRowSet` có thể tạo thêm kết quả ghép với số hàng lớn hơn nguồn ban đầu.
- Nếu mã tạo thêm `List<DTO>`, có thể có bản sao dữ liệu khác trong heap.
- Các hàng sau khi tải không được tự giải phóng chỉ vì thay predicate.

Với dữ liệu lớn, nên ưu tiên giới hạn hàng ngay tại SQL, chọn cột cần thiết, phân trang hoặc xử lý `ResultSet` tuần tự. Nếu cần phân tích dữ liệu lớn theo quan hệ, SQL JOIN và DB có thể tận dụng index/optimizer mà RowSet trong bộ nhớ không có.

### 12.2. Dữ liệu nhạy cảm và kiểm soát truy cập

Không được dùng điều kiện `Predicate` làm cơ chế che dữ liệu mà caller không được phép xem. Người dùng có thể bỏ filter hoặc việc debug/serialization có thể vô tình đi qua dữ liệu đã được nạp.

Điều kiện tenant, quyền sở hữu, trạng thái cho phép công bố và chính sách bảo mật phải được kiểm tra **trước khi populate** hoặc thực thi tại DB bằng các cơ chế được thiết kế để phân quyền.

### 12.3. Mã đồng thời và vòng đời

Một RowSet là đối tượng có trạng thái con trỏ và có thể có bộ lọc đang được thay đổi. Không nên chia sẻ cùng `FilteredRowSet` hoặc `JoinRowSet` cho nhiều thread đang gọi `next()`, `setFilter(...)` hoặc thêm nguồn cùng lúc khi chưa có thiết kế đồng bộ tường minh. Dễ hơn là coi mỗi RowSet là tài nguyên thuộc về một luồng xử lý, rồi trả về DTO bất biến.

Với `Predicate` có tham chiếu đến trạng thái bên ngoài thay đổi liên tục, kết quả lọc có thể không nhất quán giữa các lượt duyệt. Nên thiết kế predicate đơn giản, có thể kiểm thử, và tránh tác động phụ trong `evaluate(...)`.

## 13. Lỗi thường gặp và cách khắc phục

| Tình huống | Nguyên nhân | Khắc phục |
|---|---|---|
| `FilteredRowSet` vẫn thấy dữ liệu ngoài mong muốn | Predicate sai hoặc đang duyệt trước khi `setFilter` | Kiểm tra logic `evaluate` và vị trí con trỏ, `beforeFirst()` trước khi duyệt |
| Gọi `evaluate(RowSet)` gây lỗi | Cột không tồn tại, RowSet chưa đứng trên hàng phù hợp, chuyển kiểu sai | Dùng đúng label/kiểu, hiển thị lỗi thay vì âm thầm bỏ qua |
| Đổi thứ tự SELECT khiến predicate giá trị kiểm tra sai cột | Hardcode index cột `status` nhưng schema output đổi | Dùng quy ước vị trí đã kiểm thử hoặc metadata |
| Tin rằng filter đã loại dữ liệu khỏi RAM | Filter chỉ thay cách nhìn hàng đã nạp | Lọc trước bằng SQL nếu cần giảm dữ liệu truyền/bộ nhớ |
| Dùng FilteredRowSet cho phân quyền | Dữ liệu đã tới phía Java | Áp dụng quyền ở DB/API trước khi tải |
| `JoinRowSet` không biết ghép theo cột nào | Chưa cấu hình match column hoặc chọn sai tên | `setMatchColumn(...)` hoặc `addRowSet(..., key)` cho từng nguồn |
| Join trả 0 hàng | Match key khác nhau, thiếu hàng nguồn hoặc inner join loại hàng không khớp | Kiểm tra keys, dữ liệu nguồn và loại join |
| Kết quả join nhân số hàng | Khóa ghép không unique ở một/both phía | Kiểm tra cardinality, không giả định 1–1 |
| `LEFT_OUTER_JOIN` báo không hỗ trợ | Provider chỉ hỗ trợ kiểu join nhất định | `supportsJoinType(...)` và fallback SQL |
| `joined.getString("name")` đọc nhầm cột | Các nguồn có tên cột trùng/metadata khác dự kiến | Alias riêng và kiểm tra metadata sau join |
| Kết quả ngoại tuyến cũ | DB thay đổi sau `populate` | Refresh/repopulate hoặc truy vấn SQL mới |
| `acceptChanges()` gặp conflict | Dữ liệu nguồn đã thay đổi hoặc thiếu cấu hình writer | Xử lý `SyncProviderException` và transaction phù hợp |
| Memory tăng cao | Populate quá nhiều hàng và ghép kết quả nhân bản | Đẩy lọc/join xuống DB, giới hạn dữ liệu |
| Đóng JDBC quá sớm | `ResultSet` đóng trong khi RowSet chưa populate xong | Chờ `populate` hoàn thành, sau đó mới đóng |
| Đọc RowSet sau khi đóng chính RowSet | Vòng đời tài nguyên bị vi phạm | Ánh xạ DTO trước khi kết thúc khối `try` |

Khi bắt `SQLException`, giữ `SQLState`, mã lỗi của driver và nguyên nhân trong logging nội bộ phù hợp, tránh log dữ liệu cá nhân, mật khẩu hoặc chuỗi truy vấn có tham số nhạy cảm. Phân biệt lỗi truy vấn SQL, lỗi metadata, lỗi predicate Java và lỗi đồng bộ RowSet.

## 14. Kiểm thử tích hợp

Nên kiểm thử trên **DB, driver và RowSet provider dự kiến triển khai**, không chỉ với mock. Tối thiểu cần các trường hợp sau:

| Trường hợp | Hành động | Kỳ vọng |
|---|---|---|
| Nạp FilteredRowSet | Populate nhân viên phòng 7 rồi đóng Connection | RowSet vẫn duyệt được các hàng đã nạp |
| Lọc ACTIVE | `setFilter(new ActiveEmployeePredicate())` | Chỉ An được nhìn thấy trong vòng lặp |
| Bỏ filter | `setFilter(null)` và duyệt lại | Có An và Bình, không mất hàng |
| Tập kết quả rỗng | FilteredRowSet populate từ SQL trả 0 hàng | `next()` trả `false`, không đọc getter |
| Predicate đọc sai cột | Đổi alias `status` hoặc xóa cột khỏi SELECT | Lỗi được phát hiện rõ |
| Join chính xác | Nhân viên và phòng ban đều có id 7 | An và Bình được ghép với Engineering |
| Không có phòng ban khớp | Một phía không chứa id tương ứng | Inner join không sinh hàng không khớp |
| Match key khác kiểu | Một phía trả `VARCHAR`, phía khác `BIGINT` | Kiểm tra thông báo lỗi hoặc hành vi cụ thể, không giả định tự ép kiểu |
| Khóa ghép trùng | Nhiều hàng cùng key ở cả hai phía | Xác nhận cardinality và không vô tình lặp nghiệp vụ |
| Loại join khác | Thử `LEFT_OUTER_JOIN` nếu cần | Chỉ dùng khi `supportsJoinType` trả true và kết quả đúng |
| Metadata sau join | In column labels/names bằng `getMetaData()` | Mapper đọc đúng cột cần thiết |
| DB đổi dữ liệu sau populate | Đổi tên phòng ban trong DB sau khi đã đóng Connection | RowSet cũ chưa tự refresh |
| Transaction khi nạp | Hai SELECT dưới isolation phù hợp | Kiểm tra tính nhất quán snapshot nếu nghiệp vụ cần |
| Dữ liệu nhiều hàng | Nạp 100, 10.000, 100.000 hàng | Đo heap, latency, tốc độ populate và join |
| Đồng bộ trở lại DB | Chỉnh sửa RowSet ở một ví dụ riêng | Kiểm tra cấu hình writer và xử lý conflict, không nhầm với filter |

### Bài tập thực hành

Hãy xây dựng một màn hình quản trị phòng ban có dữ liệu mẫu như mục 3:

1. Truy vấn nhân viên phòng 7 bằng `PreparedStatement`, populate `FilteredRowSet`, đóng Connection và đếm số hàng trước/sau khi áp dụng predicate ACTIVE.
2. Tạo thêm predicate lọc theo **tên chứa chuỗi** (ví dụ ký tự "n"), triển khai đủ các overload của `Predicate`, và xác định cách xử lý chuỗi `NULL` nếu schema cho phép.
3. Populate phòng ban vào `CachedRowSet` riêng, tạo `JoinRowSet` với match columns được chỉ định rõ, rồi ánh xạ kết quả thành Java record.
4. Đổi tên phòng ban trong DB sau khi snapshot đã tạo; chứng minh rằng join ngoại tuyến dùng dữ liệu cũ cho tới khi được nạp lại.
5. Thêm một phòng ban không có nhân viên, so sánh kết quả `INNER_JOIN` với yêu cầu “giữ mọi phòng ban”; thử kiểm tra hỗ trợ `LEFT_OUTER_JOIN` hoặc viết SQL `LEFT JOIN`.
6. Đo thời gian và bộ nhớ của cách **SQL WHERE + JOIN** so với **populate + FilteredRowSet + JoinRowSet** trên một tập dữ liệu nhiều hàng. Ghi lại số lượng hàng truyền từ DB và số hàng còn sau lọc.
7. Thêm kiểm thử xác nhận filter không phải biện pháp phân quyền: SQL phải giới hạn dữ liệu theo quyền trước khi được phép đưa vào RowSet.

## 15. Tổng kết

- **`FilteredRowSet`** là RowSet với khả năng áp dụng **`Predicate`** để lọc góc nhìn các hàng đã nạp, phù hợp khi dữ liệu ngoại tuyến nhỏ và cần thay bộ lọc trong Java.
- **`JoinRowSet`** là RowSet hỗ trợ kết hợp dữ liệu từ các RowSet khác qua **match columns**, hữu ích cho các tập dữ liệu đã có trong bộ nhớ; phải kiểm tra **loại join** do provider hỗ trợ.
- **SQL `WHERE`/`JOIN` thường là lựa chọn tốt hơn cho dữ liệu lớn hoặc dữ liệu chưa tải**, vì DB có optimizer, index và khả năng lọc trước khi truyền qua mạng.
- **Ngoại tuyến nghĩa là dùng snapshot**, không phải tự refresh hoặc tự commit. Muốn đồng bộ thay đổi về DB cần cơ chế riêng, xử lý conflict và ranh giới transaction.
- **Cả hai giao diện đều cần kiểm thử về metadata, chi phí bộ nhớ, vòng đời RowSet và driver/provider**. Bộ lọc hoặc join trong Java không được coi là cơ chế bảo mật, thay thế transaction hoặc đảm bảo cập nhật nhiều bảng.
