# NamedParameterJdbcTemplate bổ sung tham số theo tên trên Spring JDBC

Khi dùng `JdbcTemplate` truyền thống, SQL thường đánh dấu tham số bằng dấu `?` và code phải cung cấp giá trị **đúng vị trí**. Điều này hoàn toàn hợp lệ với câu SQL ngắn, nhưng dễ đọc nhầm khi một câu truy vấn có nhiều điều kiện, cùng một giá trị được dùng nhiều lần, hoặc các cột được thêm/xóa trong quá trình bảo trì.

`NamedParameterJdbcTemplate` của Spring JDBC cho phép dùng **placeholder có tên** như `:customerId`, `:tenantId` hay `:status`. Code truyền một bảng giá trị theo tên, khiến ý nghĩa mỗi đối số hiện rõ. Bên dưới, Spring vẫn sử dụng JDBC `PreparedStatement`, chuyển placeholder có tên thành placeholder vị trí và bind các giá trị tương ứng. Nó **không phải ORM, không phải công cụ nối chuỗi SQL tự do và không thay thế quản lý transaction**.

Bài học giải thích cơ chế, các nguồn tham số `Map`/`SqlParameterSource`, ví dụ CRUD, `IN (:ids)`, kiểu SQL/`NULL`, batch update, ràng buộc bảo mật, lỗi phổ biến và cách tích hợp với transaction Spring. Phần cuối có chương trình **Java 17+ / Spring JDBC 6.1.14 / H2** chạy được bằng Maven.

## 1. Vấn đề của tham số theo vị trí `?`

Giả sử truy vấn cần tìm bản ghi theo tenant, trạng thái và thời gian:

```java
// Minh họa tích hợp với JdbcTemplate đã cấu hình.
List<OrderRow> orders = jdbc.query(
    """
    SELECT id, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND state = ?
      AND created_at >= ?
    ORDER BY id
    """,
    orderMapper,
    tenantId, state, cutoff
);
```

Câu SQL và code này dùng dấu `?` theo thứ tự **thứ nhất → thứ hai → thứ ba**. Nếu người bảo trì đổi hai điều kiện nhưng quên đổi thứ tự đối số, truy vấn có thể sai dữ liệu hoặc phát sinh lỗi type mà compiler không phát hiện được. Kiểu tham số đều là String/number cũng có thể khiến lỗi trở nên khó thấy.

Cách đặt tên làm quan hệ minh bạch hơn:

```java
String sql = """
    SELECT id, total_amount
    FROM orders
    WHERE tenant_id = :tenantId
      AND state = :state
      AND created_at >= :cutoff
    ORDER BY id
    """;

Map<String, Object> params = Map.of(
    "tenantId", tenantId,
    "state", state,
    "cutoff", cutoff
);

List<OrderRow> orders = namedJdbc.query(sql, params, orderMapper);
```

Hai đoạn là **mã minh họa**, cần các bean, `OrderRow`, mapper, bảng và biến có sẵn. `Map.of` không cho phép key hoặc value là `null`; khi dữ liệu có thể null, dùng `MapSqlParameterSource` như phần sau.

Đổi thứ tự điều kiện SQL không buộc đổi thứ tự các entry trong `Map`: placeholder `:tenantId` luôn lấy giá trị từ key `"tenantId"`. Nếu tên trong SQL không có key tương ứng, Spring báo lỗi thay vì âm thầm dùng giá trị kế bên.

### Khi nào nên dùng?

- Câu SQL có **nhiều tham số** hoặc tham số dễ nhầm vì cùng kiểu.
- Một tham số xuất hiện **nhiều lần** trong câu SQL.
- Có bộ lọc cấu hình rõ ràng, dùng JavaBean hoặc `MapSqlParameterSource`.
- Cần `IN` với danh sách phần tử thay đổi.
- Cần batch update nhiều bộ dữ liệu cùng schema lệnh.
- Muốn SQL vẫn là SQL tường minh, không chuyển sang ORM.

Câu SQL rất ngắn với một dấu `?` vẫn có thể hợp lý khi dùng `JdbcTemplate`. `NamedParameterJdbcTemplate` là **cách diễn đạt tham số**, không phải thay thế bắt buộc cho mọi API của `JdbcTemplate`.

## 2. Vai trò và cơ chế vận hành

`NamedParameterJdbcTemplate` nằm trong package:

```java
org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
```

Nó triển khai giao diện `NamedParameterJdbcOperations`, bọc một `JdbcTemplate` thông thường và ủy quyền cho template đó sau khi xử lý placeholder có tên.

```text
Application / Repository
     |
     | SQL: WHERE tenant_id = :tenantId AND status = :status
     | params: {"tenantId": 10, "status": "ACTIVE"}
     v
NamedParameterJdbcTemplate
     |
     | parse SQL, tìm và sắp thứ tự placeholder có tên
     | thay placeholder bằng JDBC marker ?
     v
Prepared SQL:
WHERE tenant_id = ? AND status = ?
     |
     | bind 10 và "ACTIVE" theo thứ tự phát sinh
     v
JdbcTemplate / PreparedStatement
     |
     v
JDBC driver -> Database -> ResultSet / update count
     |
     v
RowMapper, DataAccessException, transaction-aware resource handling
```

**Cốt lõi:** `:status` không được gửi như một “biến SQL” mới do database tự hiểu. Spring xử lý nó ở phía ứng dụng rồi dùng `PreparedStatement` để truyền dữ liệu. Điều này giữ các giá trị **tách khỏi cấu trúc SQL**, hạn chế SQL injection khi được sử dụng đúng.

### Một tên được lặp lại trong cùng SQL

```sql
SELECT id, full_name
FROM account
WHERE full_name = :term
   OR status = :term;
```

Chỉ cần truyền giá trị `term` **một lần**:

```java
Map<String, Object> params = Map.of("term", "ACTIVE");
```

Spring triển khai tương đương:

```sql
SELECT id, full_name
FROM account
WHERE full_name = ?
   OR status = ?;
```

Cùng giá trị `"ACTIVE"` được bind vào cả hai vị trí. Lặp cùng tên có nghĩa là **lặp cùng tham số**, không phải dùng các tên mới như `term1`, `term2`. Nếu nghiệp vụ cần hai giá trị khác nhau, hãy đặt hai tên riêng.

### SQL vẫn phải viết đúng ngữ pháp database

Cú pháp `:name` chỉ là placeholder của Spring. Các toán tử, hàm, dấu quote, thứ tự `JOIN`, `GROUP BY`, `ORDER BY`, giới hạn `LIMIT/FETCH` và kiểu dữ liệu vẫn phải tuân thủ SQL dialect của database. Named parameters không tự hợp thức hóa SQL không hợp lệ.

Spring có cơ chế parse SQL và cache thông tin parse (template có giới hạn cache có thể cấu hình), nhưng không nên hiểu cache này như query-result cache hoặc bảo đảm giữ một `PreparedStatement` duy nhất mãi mãi. SQL có danh sách `IN` với số phần tử khác nhau có thể tạo số dấu `?` khác nhau.

## 3. Tạo và sở hữu template trong Spring

Có thể khởi tạo từ một `DataSource`:

```java
DataSource dataSource = /* bean DataSource của ứng dụng */;
NamedParameterJdbcTemplate namedJdbc =
    new NamedParameterJdbcTemplate(dataSource);
```

Đây là minh họa, không chạy độc lập. `DataSource` phải tồn tại và được cấu hình với driver, URL và credentials thích hợp.

Trong một ứng dụng Spring, thường tạo template thành **bean** dùng chung, rồi inject vào repository:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class JdbcConfig {
    @Bean
    NamedParameterJdbcTemplate namedParameterJdbcTemplate(DataSource ds) {
        return new NamedParameterJdbcTemplate(ds);
    }
}
```

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public AccountRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
```

Hai class là ví dụ **tích hợp Spring**, cần phần cấu hình `DataSource` và các thao tác repository thực tế.

Sau khi cấu hình xong, `NamedParameterJdbcTemplate` có thể dùng chung giữa các thread; **đừng lưu một bộ tham số mutable chung làm field** rồi liên tục thêm giá trị trong mỗi request. Thay vào đó, mỗi thao tác nên tạo `Map` hay `SqlParameterSource` riêng. `DataSource`/pool thường có vòng đời ứng dụng; template không nên tạo rồi tự đóng pool sau mỗi truy vấn.

### Lấy lại API `JdbcTemplate` truyền thống

Nếu cần API chỉ có ở `JdbcOperations`, có thể gọi:

```java
org.springframework.jdbc.core.JdbcOperations jdbc =
    namedJdbc.getJdbcOperations();
```

Điều này trả giao diện của template JDBC bên dưới, **không tạo một transaction manager mới**. Bạn có thể dùng cả hai cách tiếp cận trong cùng repository khi cần, miễn cùng nguồn dữ liệu và cơ chế giao dịch phù hợp.

## 4. Cung cấp giá trị bằng `Map<String, ?>`

Cách nhanh nhất là map giữa **tên tham số không có dấu `:`** và giá trị:

```java
String sql = """
    SELECT id, full_name
    FROM account
    WHERE tenant_id = :tenantId
      AND status = :status
    ORDER BY id
    """;

Map<String, ?> params = Map.of(
    "tenantId", 10L,
    "status", "ACTIVE"
);

List<AccountView> result = namedJdbc.query(
    sql,
    params,
    (rs, rowNum) -> new AccountView(
        rs.getLong("id"),
        rs.getString("full_name")
    )
);
```

Đây là đoạn tích hợp; `AccountView` được coi là record/class của ứng dụng. Lưu ý tên cột trong `ResultSet` và tên placeholder SQL là **hai cơ chế độc lập**. `RowMapper` quyết định map hàng kết quả ra object; `NamedParameterJdbcTemplate` chỉ bind đầu vào.

**Các quy tắc cho `Map`:**

1. Key dùng `"tenantId"`, không phải `":tenantId"`.
2. Tên placeholder và key phải khớp chính xác. `:tenantId` không tự tìm `"tenant_id"`.
3. Không có key → exception; dùng key sai tên không giống với bind SQL `NULL`.
4. `Map.of(...)` từ Java 9 không nhận giá trị `null`; `Map.of("x", null)` ném `NullPointerException` ngay tại lúc tạo map.
5. Truy vấn nên sử dụng tham số đã bind, không ghép giá trị người dùng trực tiếp vào chuỗi SQL.

`Map` phù hợp khi có ít giá trị, đều không null và không cần chỉ rõ SQL type. Khi cần null, kiểu JDBC hoặc builder linh hoạt, hãy dùng `MapSqlParameterSource`.

## 5. `SqlParameterSource` và `MapSqlParameterSource`

`SqlParameterSource` là giao diện chung mà Spring dùng để lấy giá trị và, khi có, thông tin **JDBC SQL type** cho từng tham số. `MapSqlParameterSource` là implementation thực dụng cho các tham số thêm bằng tên:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource args = new MapSqlParameterSource()
    .addValue("tenantId", 10L)
    .addValue("status", "ACTIVE")
    .addValue("middleName", null, Types.VARCHAR);
```

Trong ví dụ này, `middleName` có chủ đích là SQL `NULL` với type `VARCHAR`. Các `addValue` trả chính đối tượng `MapSqlParameterSource`, nên có thể chain thành một biểu thức.

Áp dụng vào câu ghi:

```java
String sql = """
    INSERT INTO customer(tenant_id, full_name, middle_name)
    VALUES (:tenantId, :fullName, :middleName)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", tenantId)
    .addValue("fullName", fullName)
    .addValue("middleName", middleName, java.sql.Types.VARCHAR);

int inserted = namedJdbc.update(sql, params);
```

Đoạn code tích hợp cần bảng `customer` và các biến đầu vào, không phải chương trình chạy độc lập. `update` trả về **số hàng bị tác động** (thường là 1 nếu một hàng được insert thành công), không phải entity được tạo và không tự trả về generated key.

### Tại sao phải biết SQL type của `null`?

JDBC driver có thể không xác định được kiểu của một giá trị `null` được bind, đặc biệt với tham số có ngữ nghĩa đặc thù hoặc SQL phức tạp. `MapSqlParameterSource.addValue(name, null, Types.VARCHAR)` cung cấp type để driver bind ổn định hơn. Với giá trị không null, Spring và driver thường suy luận được, nhưng một số kiểu vendor-specific vẫn cần type rõ ràng.

Một lựa chọn khác là `registerSqlType("middleName", Types.VARCHAR)` trên một `SqlParameterSource` phù hợp; cách dùng `addValue` kèm type thường trực tiếp hơn khi xây một tập tham số mới.

### Vòng đời dữ liệu của nguồn tham số

`MapSqlParameterSource` có trạng thái mutable. Nên xây nó **trong mỗi lời gọi repository**, không dùng một instance chung cho mọi request. Điều này tránh race condition hoặc giá trị từ request trước rò rỉ sang request sau. Nếu là thông số bất biến, `Map.of` hoặc một bean immutable được bọc bằng nguồn tham số thích hợp cũng là lựa chọn.

## 6. `BeanPropertySqlParameterSource`: đọc giá trị từ JavaBean

Khi các placeholder tương ứng thuộc tính của một JavaBean, không cần tự gọi `addValue` cho từng trường. `BeanPropertySqlParameterSource` truy xuất các **readable properties** qua các getter.

Ví dụ class:

```java
public class AccountFilter {
    private final long tenantId;
    private final String status;

    public AccountFilter(long tenantId, String status) {
        this.tenantId = tenantId;
        this.status = status;
    }

    public long getTenantId() {
        return tenantId;
    }

    public String getStatus() {
        return status;
    }
}
```

Đây là class độc lập về khai báo Java; khi lưu riêng đặt tên `AccountFilter.java`.

Dùng làm nguồn tham số:

```java
String sql = """
    SELECT COUNT(*)
    FROM account
    WHERE tenant_id = :tenantId
      AND status = :status
    """;

SqlParameterSource params =
    new BeanPropertySqlParameterSource(
        new AccountFilter(10L, "ACTIVE")
    );

Long count = namedJdbc.queryForObject(sql, params, Long.class);
```

Đây là đoạn tích hợp; cần import `SqlParameterSource`, bean `namedJdbc` và bảng `account`. Tên `:tenantId` trùng **tên JavaBeans property** từ `getTenantId()`, không phải tên cột `tenant_id`. SQL column `tenant_id` và parameter `:tenantId` có thể khác quy ước.

So sánh:

| Hình thức | Phù hợp khi | Ghi chú |
| --- | --- | --- |
| `Map.of("id", id)` | Vài tham số không null. | Gọn, không có metadata JDBC type rõ ràng. |
| `MapSqlParameterSource` | Cần nullable value, SQL type, builder theo điều kiện. | Mutable; tạo mới mỗi lượt xử lý. |
| `BeanPropertySqlParameterSource(bean)` | DTO/filter có readable JavaBean properties. | Phụ thuộc tên property/getter; không phải mapper kết quả. |
| `SqlParameterSourceUtils.createBatch(...)` | Batch nhiều bean hoặc map. | Tạo mảng tham số cho từng phần tử batch. |

Đừng nhầm `BeanPropertySqlParameterSource` với `BeanPropertyRowMapper`:

- **BeanPropertySqlParameterSource:** đọc **JavaBean → tham số SQL đầu vào**.
- **BeanPropertyRowMapper:** đọc **một hàng ResultSet → JavaBean đầu ra**.

Chúng giải quyết hai hướng dữ liệu khác nhau. Một repository có thể dùng cả hai, nhưng không yêu cầu hai class đó phải đi cùng nhau.

## 7. `query`, `queryForObject` và `update` với tham số có tên

`NamedParameterJdbcTemplate` có những API tương tự `JdbcTemplate`:

### Trả nhiều hàng: `query`

```java
List<AccountView> accounts = namedJdbc.query(
    "SELECT id, full_name FROM account " +
    "WHERE tenant_id = :tenantId ORDER BY id",
    Map.of("tenantId", 10L),
    (rs, rowNum) -> new AccountView(
        rs.getLong("id"),
        rs.getString("full_name")
    )
);
```

`query` trả danh sách, có thể rỗng hoặc chứa nhiều hàng. `RowMapper` vẫn chạy cho từng hàng; placeholder có tên không khiến các hàng được nhóm lại.

### Mong đúng một hàng: `queryForObject`

```java
String fullName = namedJdbc.queryForObject(
    "SELECT full_name FROM account WHERE id = :id",
    Map.of("id", 1L),
    String.class
);
```

`queryForObject` kỳ vọng **một hàng**. Nếu không có hàng, Spring thường ném `EmptyResultDataAccessException`; nếu có nhiều hơn một hàng, `IncorrectResultSizeDataAccessException`. Không nên dùng API này để “lấy hàng đầu tiên”; nếu nghiệp vụ có nhiều hàng thì dùng `query`, hoặc thêm quy tắc chọn bản ghi có `ORDER BY` và giới hạn phù hợp.

Với `queryForObject(..., Class<T>)`, truy vấn thường phải trả **một cột**; nếu cần nhiều cột tạo DTO, truyền `RowMapper<T>`.

### Ghi dữ liệu: `update`

```java
int changed = namedJdbc.update(
    """
    UPDATE account
    SET status = :newStatus
    WHERE tenant_id = :tenantId AND id = :id
    """,
    new MapSqlParameterSource()
        .addValue("newStatus", "SUSPENDED")
        .addValue("tenantId", 10L)
        .addValue("id", 1L)
);
```

Giá trị `changed` là số hàng SQL tác động theo driver/DB. Một update khớp 0 hàng không tự bị xem là Java exception; nếu nghiệp vụ yêu cầu tồn tại một bản ghi, service/repository nên kiểm tra `changed == 1` và quyết định báo lỗi thích hợp.

Tham số theo tên áp dụng cho **đầu vào truy vấn**. Chúng không tự biến kết quả `ResultSet` thành object phức tạp hoặc cung cấp optimistic locking nếu câu SQL không có điều kiện version thích hợp.

## 8. Tham số danh sách `IN (:ids)`

Đây là một khác biệt hữu ích so với JDBC placeholder thuần. Ví dụ tìm ba tài khoản:

```java
String sql = """
    SELECT id, full_name
    FROM account
    WHERE id IN (:ids)
    ORDER BY id
    """;

MapSqlParameterSource params =
    new MapSqlParameterSource("ids", List.of(1L, 3L, 5L));

List<AccountView> accounts = namedJdbc.query(sql, params, mapper);
```

Trong ngữ cảnh JDBC, `mapper` là `RowMapper<AccountView>` có sẵn, không phải chương trình độc lập. Spring thay `:ids` bằng **số lượng dấu `?` tương ứng** với các phần tử:

```sql
SELECT id, full_name
FROM account
WHERE id IN (?, ?, ?)
ORDER BY id;
```

Sau đó Spring bind `1L`, `3L`, `5L`. Không nối `"1,3,5"` vào SQL, và **không** bind cả danh sách vào một dấu `?` duy nhất như một chuỗi.

### Trường hợp danh sách rỗng

`IN ()` không phải cú pháp có tính di động giữa các hệ quản trị; danh sách rỗng có thể tạo SQL không hợp lệ hoặc ngữ nghĩa khác mong muốn. Hãy định nghĩa rõ nghiệp vụ trước:

```java
// Đoạn minh họa trong repository có namedJdbc và mapper.
public List<AccountView> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }

    return namedJdbc.query(
        "SELECT id, full_name FROM account " +
        "WHERE id IN (:ids) ORDER BY id",
        Map.of("ids", ids),
        mapper
    );
}
```

Phương thức là **mã tích hợp**; thiếu class/field bên ngoài để biên dịch một mình. Đây là chính sách “tìm trong tập ID rỗng thì trả danh sách rỗng”. Trong quy trình xóa hay cập nhật, tập rỗng có thể có nghĩa **không làm gì** hoặc là lỗi input cần từ chối. Không được biến danh sách ID rỗng thành query **không có WHERE**, vì vô tình có thể tác động toàn bộ bảng.

### Tập quá lớn và giới hạn DB

Mỗi phần tử `IN` là một placeholder. Với hàng nghìn ID, độ dài SQL, số bound parameters, giới hạn `IN` của database và chi phí parse/plan có thể trở thành vấn đề. Một số hệ quản trị có giới hạn số biểu thức `IN` (ví dụ Oracle thường giới hạn 1.000 phần tử trong một `IN` đơn giản); JDBC không bảo đảm danh sách vô hạn.

Các lựa chọn khi tập rất lớn gồm chia batch có kiểm soát, temporary table, table-valued parameter, array binding hoặc join với bảng dữ liệu trung gian **theo khả năng của DB**. Không cố đưa mọi tập lớn vào một `IN (:ids)` bất kể kích thước.

### Danh sách tuple

Spring cũng hỗ trợ một số dạng danh sách tuple để tạo placeholder nhóm, ví dụ `(col_a, col_b) IN ((?, ?), (?, ?))` khi truyền các cặp giá trị thích hợp. Điều này phụ thuộc SQL dialect và cần test với database đích; không phải tất cả DB hỗ trợ row-value expression trong `IN` giống nhau.

## 9. `LIKE`, wildcard và tham số có tên

Sai lầm phổ biến là viết wildcard bao quanh placeholder trực tiếp:

```sql
-- Không phải cách bind portable, đáng tin:
SELECT id FROM account WHERE full_name LIKE %:keyword%;
```

`%` trong SQL là ký hiệu pattern, nhưng viết `%:keyword%` không phải một tham số hợp lệ được đặt trong expression như mong muốn. Cách rõ ràng nhất là tạo **giá trị pattern ở Java** rồi bind:

```java
String pattern = "%" + keyword + "%";

List<AccountView> matches = namedJdbc.query(
    "SELECT id, full_name FROM account " +
    "WHERE LOWER(full_name) LIKE LOWER(:pattern) ORDER BY id",
    Map.of("pattern", pattern),
    mapper
);
```

Đây là đoạn tích hợp với `keyword`/`mapper` được cung cấp. SQL dialect có thể hỗ trợ nối chuỗi (như `CONCAT`), nhưng cách bind cả pattern thường dễ kiểm soát hơn.

Nếu `keyword` đến từ người dùng và ký tự `%`, `_` cần được coi là văn bản thông thường thay vì wildcard, phải **escape LIKE metacharacters** theo dialect và chỉ định escape clause phù hợp. Bind parameter vẫn chống chèn cú pháp SQL, nhưng không tự ngăn wildcard làm kết quả quá rộng.

Tương tự, khi người dùng nhập chuỗi có dấu nháy `'`, không cần tự ghép quote vào SQL hoặc thay dấu nháy bằng nối chuỗi; driver sẽ bind nó như một giá trị.

## 10. Bảo mật: tham số chỉ bind **giá trị**, không bind **cấu trúc SQL**

Đúng:

```java
String sql = "SELECT id, full_name FROM account WHERE full_name = :name";
namedJdbc.query(sql, Map.of("name", userSuppliedName), mapper);
```

Tên `:name` đại diện cho một **giá trị**; Spring dùng `PreparedStatement`. Dữ liệu chứa `' OR 1=1 --` vẫn được bind như một literal value, không tự trở thành mệnh đề `WHERE`.

Sai:

```java
// Không an toàn: userSuppliedName được ghép trực tiếp vào SQL.
String sql = "SELECT id FROM account WHERE full_name = '" +
             userSuppliedName + "'";
```

**Không thể bind tên bảng, tên cột hoặc chiều sắp xếp bằng `:parameter`.** Ví dụ:

```sql
-- :sortColumn chỉ là giá trị, không đổi thành tên cột để ORDER BY:
SELECT id, full_name FROM account ORDER BY :sortColumn;
```

Nếu ứng dụng cho phép chọn sort field, hãy **whitelist** những cột hợp lệ rồi ghép identifier đã được chọn từ một danh sách cố định. Giá trị lọc vẫn phải bind riêng:

```java
// Đoạn minh họa: sortKey và tenantId là input đã có.
String sortColumn = switch (sortKey) {
    case "name" -> "full_name";
    case "id" -> "id";
    default -> throw new IllegalArgumentException("Unsupported sort key");
};

String sql =
    "SELECT id, full_name FROM account " +
    "WHERE tenant_id = :tenantId ORDER BY " + sortColumn;

List<AccountView> rows = namedJdbc.query(
    sql, Map.of("tenantId", tenantId), mapper
);
```

Chỉ có `"full_name"` hoặc `"id"` do code kiểm soát được đi vào SQL. Không lấy trực tiếp `sortKey` làm identifier. Nếu có phân trang, hãy validate limit/offset và dùng cơ chế bind phù hợp với DB; named parameters không tự giới hạn truy vấn độc hại hoặc quá lớn.

**Không nhầm hai vấn đề:** bind an toàn chống chèn cú pháp SQL; kiểm tra quyền truy cập/tenant vẫn là trách nhiệm ứng dụng. Một query được bind an toàn nhưng thiếu `tenant_id` vẫn có thể lộ dữ liệu tenant khác.

## 11. Batch update với nhiều bộ tham số

Khi cùng một câu SQL cần lặp nhiều lần với các bộ giá trị khác nhau, `batchUpdate` nhận mảng `SqlParameterSource[]` hoặc `Map<String, ?>[]`.

```java
// Minh họa: mỗi ScoreChange là JavaBean có getId/getPoints.
List<ScoreChange> changes = List.of(
    new ScoreChange(1L, 10),
    new ScoreChange(2L, 20)
);

int[] counts = namedJdbc.batchUpdate(
    "UPDATE account SET points = :points WHERE id = :id",
    SqlParameterSourceUtils.createBatch(changes)
);
```

Đây là đoạn tích hợp; `ScoreChange` cần định nghĩa và các import tương ứng. `SqlParameterSourceUtils.createBatch(...)` tạo một nguồn tham số cho **mỗi phần tử**; Spring đưa các bộ này vào JDBC batch tương ứng. Trong ví dụ chạy độc lập phía sau có `ScoreChange` đầy đủ.

Lưu ý:

- `int[]` là kết quả từ JDBC driver cho từng mục. Driver có thể báo số hàng thực hoặc mã như `Statement.SUCCESS_NO_INFO`; không luôn tin mọi phần tử đều chính xác bằng 1 trên mọi DB.
- Batch không tự đảm bảo **tất cả cùng commit hoặc cùng rollback**. Nếu cần nguyên tử, hãy bao quanh bằng transaction Spring với transaction manager/DataSource tương ứng.
- Không batch hàng triệu phần tử một lượt nếu gây áp lực bộ nhớ, log hoặc transaction quá dài.
- Nếu batch có lệnh ảnh hưởng 0 hàng, code nghiệp vụ cần xét đó có phải lỗi (record không tồn tại) hay trạng thái hợp lệ.

Về generated keys, `NamedParameterJdbcTemplate` có overload `update(sql, SqlParameterSource, KeyHolder, ...)` và một số overload batch hỗ trợ `KeyHolder` trong Spring 6.1; khả năng và định dạng key phụ thuộc JDBC driver/database. Không mặc định rằng mọi insert có auto-increment sẽ trả key qua phương thức `update(sql, Map)`.

## 12. Quan hệ với giao dịch Spring và nguồn dữ liệu

Vì `NamedParameterJdbcTemplate` ủy quyền cho `JdbcTemplate`, nó tham gia vòng đời connection theo Spring JDBC. Nếu repository chạy trong transaction Spring đã thiết lập cho **cùng `DataSource`**, các lệnh `namedJdbc.query`/`update` có thể dùng connection đang bind với transaction hiện tại.

Ví dụ:

```java
// Minh họa service chạy qua Spring proxy và cùng transaction manager.
@Transactional
public void renameAndAudit(long id, String name) {
    namedJdbc.update(
        "UPDATE account SET full_name = :name WHERE id = :id",
        Map.of("id", id, "name", name)
    );
    namedJdbc.update(
        "INSERT INTO account_audit(account_id, event) " +
        "VALUES (:id, :event)",
        Map.of("id", id, "event", "RENAMED")
    );
}
```

Đây là đoạn tích hợp; cần schema, bean, imports và transaction management đúng cấu hình.

Nếu thao tác thứ hai ném unchecked exception ra ngoài interceptor, `@Transactional` với rollback rules mặc định thường rollback cả hai thao tác. Nhưng nếu không có transaction đang được Spring quản lý, mỗi statement có thể auto-commit độc lập. **Named parameters không thay đổi các quy tắc commit/rollback**.

Các điểm dễ nhầm:

- Cùng `@Transactional` không có nghĩa tự bao gồm hai `DataSource` khác nhau.
- Self-invocation trực tiếp trong cùng Spring bean (proxy mode) thường không qua transaction interceptor.
- Việc gọi `DataSource.getConnection()` trực tiếp ngoài cơ chế transaction-aware có thể lấy một connection khác; nên ưu tiên template Spring.
- `NamedParameterJdbcTemplate` không quyết định transaction propagation, isolation hay timeout của transaction.
- Không tạo template mỗi câu SQL bằng một `DataSource` mới; quản lý `DataSource`/pool theo ứng dụng.

## 13. Java 17+ chạy độc lập: Map, bean, IN, NULL, batch và rollback

Ví dụ này dùng **Spring JDBC 6.1.14**, **H2 2.2.224** và Maven. Nó tạo dữ liệu H2 in-memory, rồi kiểm chứng những điểm chính:

1. Dùng `MapSqlParameterSource` insert 3 hàng với các tên `:id`, `:tenantId`, `:fullName`, `:status`, `:points`.
2. Dùng `Map.of` truy vấn một giá trị theo hai điều kiện có tên.
3. Lặp placeholder `:term` hai lần và vẫn chỉ bind một giá trị.
4. Dùng `IN (:ids)` để truy vấn danh sách ID.
5. `BeanPropertySqlParameterSource` lấy giá trị từ getter của bean.
6. Bind `null` với `Types.INTEGER` và nhận SQL `NULL`.
7. `batchUpdate` dùng hai bean thay đổi điểm.
8. `TransactionTemplate` rollback thao tác update có named parameter khi xảy ra exception.

**Đây là chương trình Java độc lập hoàn chỉnh trong một file source**, không cần Spring Boot hay ứng dụng server.

### Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>named-parameter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### Tạo `src/main/java/NamedParameterDemo.java`

```java
import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class NamedParameterDemo {
    public record Account(
            long id, String fullName, String status, Integer points) {}

    public static final class Filter {
        private final long tenantId;
        private final String status;

        public Filter(long tenantId, String status) {
            this.tenantId = tenantId;
            this.status = status;
        }

        public long getTenantId() {
            return tenantId;
        }

        public String getStatus() {
            return status;
        }
    }

    public static final class ScoreChange {
        private final long id;
        private final Integer points;

        public ScoreChange(long id, Integer points) {
            this.id = id;
            this.points = points;
        }

        public long getId() {
            return id;
        }

        public Integer getPoints() {
            return points;
        }
    }

    private static void insert(
            NamedParameterJdbcTemplate jdbc,
            long id,
            long tenantId,
            String name,
            String status,
            Integer points) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("tenantId", tenantId)
                .addValue("fullName", name)
                .addValue("status", status)
                .addValue("points", points, Types.INTEGER);

        jdbc.update(
            "INSERT INTO account " +
            "(id, tenant_id, full_name, status, points) " +
            "VALUES (:id, :tenantId, :fullName, :status, :points)",
            params
        );
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:named_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        named.getJdbcOperations().execute(
            "CREATE TABLE account (" +
            "id BIGINT PRIMARY KEY, " +
            "tenant_id BIGINT NOT NULL, " +
            "full_name VARCHAR(80) NOT NULL, " +
            "status VARCHAR(16) NOT NULL, " +
            "points INTEGER)"
        );

        insert(named, 1L, 10L, "An", "ACTIVE", null);
        insert(named, 2L, 10L, "Binh", "ACTIVE", 20);
        insert(named, 3L, 20L, "Chi", "PAUSED", 30);

        String single = named.queryForObject(
            "SELECT full_name FROM account " +
            "WHERE tenant_id = :tenantId AND id = :id",
            Map.of("tenantId", 10L, "id", 1L),
            String.class
        );
        System.out.println("Single: " + single);

        Long repeated = named.queryForObject(
            "SELECT COUNT(*) FROM account " +
            "WHERE status = :term OR full_name = :term",
            Map.of("term", "ACTIVE"),
            Long.class
        );
        System.out.println("Repeated parameter: " + repeated);

        List<Long> ids = named.query(
            "SELECT id FROM account WHERE id IN (:ids) ORDER BY id",
            Map.of("ids", List.of(1L, 3L)),
            (rs, rowNum) -> rs.getLong("id")
        );
        System.out.println("IN list: " + ids);

        SqlParameterSource filter =
            new BeanPropertySqlParameterSource(
                new Filter(10L, "ACTIVE")
            );

        List<Account> selected = named.query(
            "SELECT id, full_name, status, points " +
            "FROM account " +
            "WHERE tenant_id = :tenantId AND status = :status " +
            "ORDER BY id",
            filter,
            (rs, rowNum) -> new Account(
                rs.getLong("id"),
                rs.getString("full_name"),
                rs.getString("status"),
                rs.getObject("points", Integer.class)
            )
        );
        List<String> names = selected.stream()
                .map(Account::fullName)
                .toList();
        System.out.println("Bean filter: " + names);

        int updatedNull = named.update(
            "UPDATE account SET points = :points WHERE id = :id",
            new MapSqlParameterSource()
                .addValue("id", 1L)
                .addValue("points", null, Types.INTEGER)
        );
        Integer maybePoints = named.queryForObject(
            "SELECT points FROM account WHERE id = :id",
            Map.of("id", 1L),
            Integer.class
        );
        System.out.println(
            "Typed NULL: updated=" + updatedNull +
            ", isNull=" + (maybePoints == null)
        );

        List<ScoreChange> changes = List.of(
            new ScoreChange(1L, 11),
            new ScoreChange(2L, 22)
        );
        int[] batchCounts = named.batchUpdate(
            "UPDATE account SET points = :points WHERE id = :id",
            SqlParameterSourceUtils.createBatch(changes)
        );
        System.out.println(
            "Batch counts: " + Arrays.toString(batchCounts)
        );

        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );
        try {
            tx.executeWithoutResult(status -> {
                named.update(
                    "UPDATE account SET status = :nextStatus " +
                    "WHERE id = :id",
                    Map.of("nextStatus", "PAUSED", "id", 1L)
                );
                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback triggered");
        }

        String afterRollback = named.queryForObject(
            "SELECT status FROM account WHERE id = :id",
            Map.of("id", 1L),
            String.class
        );
        System.out.println("Status after rollback: " + afterRollback);
    }
}
```

### Chạy chương trình

Trong thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=NamedParameterDemo
```

Các dòng **`System.out` của ứng dụng** dự kiến:

```text
Single: An
Repeated parameter: 2
IN list: [1, 3]
Bean filter: [An, Binh]
Typed NULL: updated=1, isNull=true
Batch counts: [1, 1]
Rollback triggered
Status after rollback: ACTIVE
```

Maven hoặc logging của thư viện có thể ghi thêm thông báo ngoài các dòng này; đó không phải kết quả do các lệnh `System.out.println` của chương trình sinh ra.

### Giải thích theo thứ tự

1. `Single: An`: SQL dùng hai tên `:tenantId`, `:id`; `Map.of` có thể liệt kê key theo thứ tự khác SQL mà vẫn bind đúng.
2. `Repeated parameter: 2`: `:term` xuất hiện hai lần nhưng cùng nhận `"ACTIVE"`; có hai hàng có trạng thái ACTIVE.
3. `IN list: [1, 3]`: danh sách hai ID trở thành hai JDBC placeholders; `ORDER BY id` làm thứ tự ổn định.
4. `Bean filter: [An, Binh]`: `BeanPropertySqlParameterSource` đọc `getTenantId()` và `getStatus()` của `Filter`; kết quả map từng hàng thành record `Account` bằng RowMapper tường minh.
5. `Typed NULL`: update dùng `MapSqlParameterSource` và `Types.INTEGER`, một hàng khớp; truy vấn lại cột `points` nhận `null`.
6. `Batch counts: [1, 1]`: hai bean `ScoreChange` tạo hai bộ named parameters; trên H2 mỗi `UPDATE` khớp một hàng.
7. `Rollback triggered` và `Status after rollback: ACTIVE`: `TransactionTemplate` giữ hai bước làm việc trong transaction Spring; unchecked exception khiến thay đổi status thành PAUSED bị rollback.

`DriverManagerDataSource` ở đây là nguồn kết nối đơn giản để demo, **không phải connection pool**. Trên production, dùng pool và các cấu hình giao dịch thích hợp. Mục đích ví dụ là xác nhận named-parameter binding và cơ chế ủy quyền cho Spring JDBC.

## 14. Những lỗi thường gặp

| Sai lầm | Triệu chứng/hậu quả | Cách sửa |
| --- | --- | --- |
| Key chứa dấu `:`, ví dụ `Map.of(":id", 1)` | Không tìm thấy giá trị cho `:id`. | Key phải là `"id"`. |
| Nhầm `:tenantId` với key `"tenant_id"` | Thiếu tham số. | Đặt tên placeholder đúng tên key/getter; SQL column có thể khác tên. |
| Dùng `Map.of` với `null` | `NullPointerException` trước khi chạy SQL. | `MapSqlParameterSource` và SQL type khi cần. |
| Truyền danh sách ID thành một chuỗi `"1,2,3"` | Không mở rộng thành nhiều placeholders của `IN`. | Truyền `List<Long>` vào `:ids`. |
| Dùng danh sách rỗng với `IN (:ids)` | SQL `IN ()` có thể không hợp lệ. | Xử lý empty list theo nghiệp vụ trước khi chạy SQL. |
| Dùng nhiều nghìn phần tử `IN` vô hạn | Chạm giới hạn SQL/driver/DB hoặc hiệu năng kém. | Chia batch hoặc dùng giải pháp dữ liệu trung gian phù hợp DB. |
| Dùng `:sortColumn` thay tên cột | Bind thành giá trị, không thành identifier. | Whitelist cột được phép, rồi ghép identifier đã xác minh. |
| Ghép chuỗi người dùng vào SQL | Rủi ro SQL injection. | Bind literal bằng named parameters; whitelist mọi phần cấu trúc động. |
| Bắt `DataAccessException` rồi trả list rỗng cho mọi lỗi | Che giấu lỗi kết nối/SQL/thiếu tham số. | Bắt đúng lỗi nghiệp vụ; log và xử lý tầng phù hợp. |
| Nghĩ `queryForObject` tự trả null nếu không có hàng | Có thể nhận `EmptyResultDataAccessException`. | Dùng chính sách Optional/try-catch theo contract, hoặc `query` nếu cần list. |
| Nhầm `BeanPropertySqlParameterSource` với `BeanPropertyRowMapper` | Lẫn chiều đi của dữ liệu. | Source đọc bean làm input; mapper tạo bean từ ResultSet. |
| Tưởng named parameters tự mở transaction | Nhiều update auto-commit riêng, rollback không đồng bộ. | Dùng `@Transactional`/`TransactionTemplate` thích hợp. |
| Dùng một `MapSqlParameterSource` mutable chung cho các request | Race condition, rò rỉ giá trị giữa request. | Tạo nguồn tham số theo mỗi lần gọi. |
| Tin `batchUpdate` luôn trả `1` cho mọi phần tử | Một số driver trả mã số hàng không xác định. | Xét hằng JDBC `Statement.SUCCESS_NO_INFO` và semantics driver. |

## 15. Cách test và review mã dùng named parameters

Kiểm thử nên kiểm tra **hợp đồng SQL lẫn hành vi dữ liệu**, không chỉ xác nhận phương thức Java được gọi:

1. **Tên chính xác:** Mọi `:parameter` đều có key/getter tương ứng. Một lỗi viết hoa/snake_case trong key phải được phát hiện.
2. **Thứ tự độc lập:** Đảo thứ tự entry trong map hoặc điều kiện SQL mà kết quả vẫn đúng.
3. **Tên lặp lại:** SQL dùng cùng `:name` tại nhiều vị trí và mỗi vị trí nhận cùng giá trị.
4. **Giá trị đặc biệt:** Dấu nháy đơn và chuỗi giống cú pháp SQL được bind như literal, không làm thay đổi cấu trúc câu SQL.
5. **NULL và kiểu JDBC:** Test nullable columns, `Types` phù hợp và tính tương thích driver.
6. **IN-list:** 1 phần tử, nhiều phần tử, 0 phần tử và số lượng lớn; xác định chính sách và giới hạn rõ ràng.
7. **Query cardinality:** 0/1/n hàng nếu repository dùng `queryForObject`; không đổ lỗi vào named parameters khi số hàng không hợp lệ.
8. **Batch update:** Kiểm tra số tác vụ, hàng tác động, xử lý các mã JDBC đặc biệt và rollback khi giữa batch có lỗi.
9. **Transaction:** Hai lần gọi `namedJdbc.update` trong một transaction có rollback cùng nhau khi exception đúng rollback rules.
10. **Phạm vi quyền:** Các điều kiện tenant, soft-delete và kiểm soát dữ liệu vẫn có mặt trong SQL.
11. **Cấu trúc động:** Sort field/table name chỉ từ whitelist; tránh SQL injection bằng chuỗi ghép người dùng.
12. **SQL dialect:** Dùng integration test với DB thật khi liên quan `IN` lớn, tuple IN, generated keys hoặc kiểu chuyên biệt.

Một lỗi tốt nên giữ thông tin chẩn đoán hữu ích: tên câu truy vấn/repository, loại exception, mã nghiệp vụ, số hàng kỳ vọng (nếu liên quan). Đừng ghi mật khẩu, dữ liệu nhạy cảm hoặc nguyên chuỗi SQL với values người dùng vào log không kiểm soát.

## 16. So sánh `JdbcTemplate`, `NamedParameterJdbcTemplate` và `JdbcClient`

| Tiêu chí | `JdbcTemplate` | `NamedParameterJdbcTemplate` | `JdbcClient` (Spring 6.1+) |
| --- | --- | --- | --- |
| Placeholder chính | `?` | `:name` | Cả positional và named. |
| Cách gọi | `query`/`update`/callbacks | Các method tương tự nhưng nhận map/parameter source | Fluent API `sql(...).param(...).query(...)`. |
| Ưu điểm | Trực tiếp, phổ biến, API callback phong phú | Ý nghĩa tham số rõ, hỗ trợ `IN` list và batch theo tên | Cú pháp fluent gọn cho thao tác phổ biến. |
| Transaction | Spring JDBC | Vẫn dùng Spring JDBC bên dưới | Cũng ủy quyền về cơ chế JDBC của Spring. |
| Nên chọn | SQL ngắn, APIs đặc biệt cần JdbcOperations | Nhiều named filters, query dài, batch | Muốn fluent style và dự án đang dùng Spring hỗ trợ. |

`JdbcClient` không làm `NamedParameterJdbcTemplate` lỗi thời ngay lập tức. Một số API nâng cao vẫn thuận tiện hơn với `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`; chọn theo phiên bản Spring, kiểu thao tác và tính nhất quán của codebase.

## 17. Checklist dùng đúng `NamedParameterJdbcTemplate`

Trước khi review một repository, tự hỏi:

- **SQL có ghi đúng `:name` không?** Mọi key/getter nguồn tham số có tên khớp?
- **Các giá trị nullable đã được xử lý?** Không dùng `Map.of` với null; có cần khai báo JDBC type không?
- **Cấu trúc SQL có bị ghép từ input chưa xác minh?** Các identifier/sort fields có whitelist?
- **`IN` có thể nhận tập rỗng hoặc quá lớn không?** Chính sách empty và giới hạn DB đã rõ?
- **Phân biệt input binding với output mapping chưa?** `BeanPropertySqlParameterSource` khác `RowMapper`.
- **Method có đúng contract số hàng không?** `queryForObject` là exactly one, `query` cho many.
- **Transaction có đúng DataSource/manager và rollback rules?** Template không tự tạo transaction nguyên tử cho toàn bộ use case.
- **Batch có phù hợp số phần tử và driver không?** Không dựa tuyệt đối vào update counts như một transaction-level guarantee.
- **Nguồn tham số mutable có bị chia sẻ giữa request không?** Cấu hình template một lần nhưng tạo map/parameter source theo lời gọi.
- **Có test integration cho SQL dialect thực tế không?** Nhất là `IN`, typed NULL và generated keys.

### Ghi nhớ

1. `NamedParameterJdbcTemplate` bổ sung cú pháp **`:name`** lên Spring JDBC và ủy quyền cho `JdbcTemplate` sau khi chuyển thành `?`.
2. Giá trị được bind theo **tên** thông qua `Map` hoặc `SqlParameterSource`; tên lặp lại được bind lặp đúng vị trí.
3. `MapSqlParameterSource` thuận tiện cho giá trị nullable và khai báo `java.sql.Types`; `BeanPropertySqlParameterSource` lấy giá trị từ JavaBean getter.
4. `IN (:ids)` có thể mở rộng danh sách thành nhiều placeholders, nhưng phải xử lý **danh sách rỗng** và **giới hạn database**.
5. Named parameters an toàn cho **giá trị**, không dùng để truyền tên bảng/cột hay keyword SQL động.
6. `query`, `queryForObject`, `update`, `batchUpdate` vẫn tuân theo hợp đồng cardinality và affected rows của Spring JDBC.
7. Giao dịch, kết nối, rollback và bảo mật tenant vẫn cần thiết kế đúng; `NamedParameterJdbcTemplate` không thay thế những trách nhiệm đó.

### Tài liệu tham khảo

- Spring Framework — JDBC core / Using NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC parameter handling và `IN` list: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JDBC batch operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework 6.1 — `NamedParameterJdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework 6.1 — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Spring Framework 6.1 — `BeanPropertySqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/BeanPropertySqlParameterSource.html
