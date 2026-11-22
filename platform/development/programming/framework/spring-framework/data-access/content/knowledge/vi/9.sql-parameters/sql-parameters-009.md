# IN với tập giá trị và trường hợp danh sách rỗng

## 1. Bài toán: danh sách ID có kích thước thay đổi

Trong Spring Framework phần data-access, câu SQL thường cần lọc theo **một tập giá trị do ứng dụng cung cấp**: danh sách ID khách hàng, mã sản phẩm được chọn, trạng thái hợp lệ, mã quyền được cấp hoặc nhóm đơn hàng cần xử lý.

Ví dụ:

```sql
SELECT id, name
FROM customer
WHERE id IN (1, 3, 5)
ORDER BY id;
```

Nhưng ở thời điểm chạy, ứng dụng có thể nhận `List<Long> ids` với 0, 1, 3 hoặc hàng trăm phần tử. Vì thế không thể cố định ba phần tử trong SQL. Ba vấn đề phải được giải quyết riêng:

1. **Biến số phần tử thành số tham số SQL phù hợp:** `IN (?, ?, ?)` cho ba giá trị; không nối trực tiếp dữ liệu người dùng vào SQL.
2. **Định nghĩa hành vi khi danh sách rỗng:** `IN ()` không phải cú pháp SQL đáng tin cậy trên các hệ quản trị; SQL có thể lỗi hoặc có hành vi phụ thuộc dialect.
3. **Giữ ngữ nghĩa và an toàn nghiệp vụ:** `IN` và `NOT IN` có hành vi khác nhau với danh sách rỗng, `NULL` và thao tác `UPDATE`/`DELETE`.

Bài này minh họa với Java 17+, `JdbcTemplate`, `NamedParameterJdbcTemplate` và SQL chuẩn thông dụng. Mỗi ví dụ chỉ chạy được khi có đúng DB/schema/driver và cấu hình Spring tương ứng; chương trình JDK 17 độc lập ở mục 16 được chú thích riêng.

**Kết luận ban đầu:** `IN` với danh sách rỗng không đơn thuần là một lỗi cú pháp phải “chữa cho chạy”; trước hết phải xác định **tập kết quả nghiệp vụ mong muốn là gì** rồi chọn cách xử lý an toàn.

## 2. Hiểu ngữ nghĩa SQL IN trước khi viết Java

Cú pháp phổ biến:

```sql
WHERE id IN (1, 3, 5)
```

Nó có thể hiểu gần với:

```sql
WHERE id = 1 OR id = 3 OR id = 5
```

Nếu `id` bằng một trong các giá trị, điều kiện đúng. Ngược lại, `NOT IN (1, 3, 5)` tương ứng với “khác tất cả” trong logic SQL:

```sql
WHERE id <> 1 AND id <> 3 AND id <> 5
```

Tuy nhiên SQL có **logic ba giá trị**: TRUE, FALSE và UNKNOWN (thường biểu diễn bằng `NULL`), không giống phép so sánh thông thường trong Java. Điều đó đặc biệt quan trọng với `NOT IN`.

Ví dụ với cột `id` không null:

| ID | `id IN (1, 3)` | `id NOT IN (1, 3)` |
| ---: | --- | --- |
| 1 | TRUE | FALSE |
| 2 | FALSE | TRUE |
| 3 | TRUE | FALSE |
| 4 | FALSE | TRUE |

Nếu danh sách đầu vào về mặt ý nghĩa là tập rỗng, cách hiểu toán học hợp lý:

- **`id IN []`:** không có ID nào thuộc tập rỗng → **không trả hàng nào**.
- **`id NOT IN []`:** không có ID nào bị loại → **không áp điều kiện loại trừ** (chỉ giữ các điều kiện khác).

Nhưng hai ký hiệu `IN []` và `NOT IN []` ở trên là *ký hiệu giải thích*, **không phải SQL để chạy**. Cũng không nên suy luận rằng mọi DB chấp nhận `IN ()`. Với code ứng dụng, cần viết nhánh xử lý riêng hoặc tạo biểu thức SQL được DB hỗ trợ.

### Tại sao `IN (?)` không nhận một List như một giá trị duy nhất?

Một dấu `?` trong `PreparedStatement` là **một vị trí tham số JDBC**, không phải cơ chế mặc định để tự mở rộng một `List` thành nhiều chỗ trống.

Sai về ý định:

```java
String sql = "SELECT id FROM customer WHERE id IN (?)";
jdbcTemplate.query(
    sql,
    (rs, row) -> rs.getLong("id"),
    "1,3,5"
);
```

Chuỗi `"1,3,5"` là **một giá trị kiểu chuỗi**, không phải ba số nguyên. Tùy DB/driver, truy vấn có thể không khớp, lỗi chuyển kiểu hoặc so sánh sai. Tương tự, không được mặc định truyền `List.of(1L, 3L, 5L)` vào một dấu `?` rồi hy vọng JDBC tự hiểu là ba phần tử.

Cách đúng với JDBC thông thường là **tạo đúng số dấu hỏi**, hoặc dùng một API Spring có cơ chế mở rộng tham số danh sách.

## 3. Quy tắc xử lý đầu vào trước khi tạo SQL

Nên xác định hợp đồng cho đầu vào ngay tại ranh giới repository/service:

| Đầu vào | Ý nghĩa có thể chọn | Hành vi khuyến nghị cho truy vấn INCLUDE |
| --- | --- | --- |
| `null` cho toàn bộ danh sách | Không được cung cấp hoặc lỗi lập trình | Báo lỗi đầu vào; **đừng ngầm coi là rỗng** nếu API không định nghĩa như vậy |
| `[]` | Người gọi chọn không ID nào | Trả danh sách rỗng, không gọi DB; hoặc dùng predicate FALSE nếu cần SQL |
| `[3]` | Chọn một ID | `IN (?)` và một tham số |
| `[3, 1]` | Chọn hai ID | `IN (?, ?)` và hai tham số |
| `[3, 1, 3]` | ID 3 xuất hiện hai lần | Có thể khử trùng lặp trước khi bind; kết quả `IN` không tự nhân đôi dòng |
| `[3, null]` | Có phần tử `NULL`, dễ gây hiểu nhầm | Với danh sách khóa ID, nên **từ chối hoặc loại null theo hợp đồng rõ ràng**, không truyền vô thức |

Một helper an toàn cho ID `Long` thường thực hiện:

1. Kiểm tra danh sách không phải `null`.
2. Kiểm tra từng phần tử không phải `null` (nếu nghiệp vụ dùng khóa ID không nullable).
3. Tùy nhu cầu, loại các ID lặp bằng `distinct()` để tránh tạo thêm placeholder.
4. Giữ danh sách đã chuẩn hóa trong phạm vi lời gọi; không phụ thuộc vào việc caller sẽ không thay đổi list sau khi truyền.

Ví dụ:

```java
private static List<Long> checkedIds(List<Long> ids) {
    Objects.requireNonNull(ids, "ids");
    if (ids.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("ids cannot contain null");
    }
    return ids.stream().distinct().toList();
}
```

Đoạn trên cần import `List` và `Objects`; với Java 17, `Stream.toList()` tạo danh sách không chỉnh sửa được. Không tự ý làm `distinct()` nếu ứng dụng cần giữ **số lần xuất hiện** của mỗi giá trị cho một thao tác khác; riêng bộ lọc `IN` theo tập giá trị thì thường không cần trùng.

## 4. Cách 1 — JdbcTemplate với placeholder động

Với `JdbcTemplate`, số `?` phải khớp số giá trị bind. Một cách tạo chuỗi placeholder **chỉ từ kích thước danh sách**, không từ giá trị người dùng:

```java
String marks = String.join(
    ", ",
    Collections.nCopies(ids.size(), "?")
);
```

| Số ID | `marks` | SQL kết quả |
| ---: | --- | --- |
| 1 | `?` | `WHERE id IN (?)` |
| 2 | `?, ?` | `WHERE id IN (?, ?)` |
| 3 | `?, ?, ?` | `WHERE id IN (?, ?, ?)` |
| 0 | chuỗi rỗng | **Không chạy `WHERE id IN ()`** |

Ví dụ hàm truy vấn (mã tích hợp Spring, cần `JdbcTemplate` và kiểu `Customer` đã khai báo):

```java
public List<Customer> findByIdsJdbc(List<Long> inputIds) {
    List<Long> ids = checkedIds(inputIds);
    if (ids.isEmpty()) {
        return List.of();
    }

    String marks = String.join(
        ", ", Collections.nCopies(ids.size(), "?")
    );
    String sql = """
        SELECT id, name
        FROM customer
        WHERE id IN (%s)
        ORDER BY id
        """.formatted(marks);

    return jdbcTemplate.query(
        sql,
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        ),
        ids.toArray()
    );
}
```

Giải thích:

- **Nhánh rỗng đứng trước** việc tạo SQL, tránh `IN ()`.
- Chỉ chèn `?`/dấu phẩy vào cấu trúc SQL, **không chèn số ID thực**.
- `ids.toArray()` cung cấp `Object[]` cho overload `query(String, RowMapper<T>, Object... args)`, nên mỗi giá trị được bind riêng.
- `RowMapper` chuyển từng hàng trả về thành `Customer`.
- `ORDER BY id` tạo thứ tự truy vấn dự đoán được; `IN` tự nó **không giữ thứ tự danh sách ID đầu vào**.
- Với zero ID, trả `List.of()` mà không cần lấy connection; điều này khác việc dùng truy vấn health check và là hành vi có chủ đích.

**Chỉ dùng đoạn này sau khi đặt trong một lớp có `jdbcTemplate` và record `Customer` thích hợp**; mục 6 cung cấp lớp repository hoàn chỉnh. Đừng gọi `String.format`/`formatted` với chuỗi được nhập trực tiếp từ người dùng làm “mẫu SQL”; ở đây mẫu cố định từ code và chèn *chỉ* danh sách dấu hỏi.

### Lỗi bảo mật thường thấy

Không viết:

```java
// Không an toàn nếu phần tử đến từ input chưa được bảo vệ:
String sql = "SELECT id FROM customer WHERE id IN (" +
             userSuppliedCsv + ")";
```

Ví dụ trên ghép nguyên văn chuỗi người dùng vào SQL, mở đường cho lỗi cú pháp hoặc SQL injection. Bind từng giá trị; việc chuỗi placeholder thay đổi **theo số lượng** không đồng nghĩa ghép giá trị đầu vào vào SQL.

## 5. Cách 2 — NamedParameterJdbcTemplate với List

`NamedParameterJdbcTemplate` cho phép đặt tên tham số và **mở rộng danh sách giá trị** thành số placeholder JDBC cần thiết:

```java
String sql = """
    SELECT id, name
    FROM customer
    WHERE id IN (:ids)
    ORDER BY id
    """;

MapSqlParameterSource params =
    new MapSqlParameterSource("ids", ids);

List<Customer> customers = namedJdbcTemplate.query(
    sql,
    params,
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    )
);
```

Khi `ids = List.of(3L, 1L)`, Spring xử lý tham số có tên `:ids` và tạo các vị trí JDBC tương ứng (về ý nghĩa giống `IN (?, ?)`), rồi bind `3` và `1`. Lưu ý `:ids` là cú pháp ở lớp Spring, **không phải cú pháp mà mọi JDBC driver nhận trực tiếp**.

Những điểm phải nhớ:

- Phần tử danh sách đi qua parameter binding; Spring không cần nối giá trị vào SQL.
- Không phải mỗi dấu `:ids` luôn bằng một `?`. Với collection, Spring mở rộng theo số phần tử phù hợp.
- Tên `ids` phải khớp giữa SQL và `MapSqlParameterSource`.
- **NamedParameterJdbcTemplate không tự định nghĩa thay nghiệp vụ ý nghĩa tập rỗng.** Khi list rỗng, SQL được mở rộng có thể thành biểu thức không hợp lệ hoặc phụ thuộc DB; phải chọn chính sách rỗng **trước khi gọi query**.
- API cũng có thể bind các tham số khác bên cạnh `ids`, ví dụ `tenantId`, `status`.

Với nhiều tham số hoặc câu SQL dài, tham số có tên thường dễ đọc và tránh lỗi đảo thứ tự hơn giải pháp tự đếm `?`. Với một truy vấn rất ngắn và hệ thống đã dùng `JdbcTemplate`, cách tạo placeholder động vẫn là hợp lệ.

### Tại sao cả hai cách đều không nên nhận danh sách rỗng một cách mù quáng?

Không có quy tắc liên DB rằng một lần gọi `NamedParameterJdbcTemplate.query` với `ids=[]` luôn phải trả 0 hàng. Một số tổ hợp DB/driver/phiên bản SQL có thể từ chối `IN ()`. Quan trọng hơn, tác vụ **`NOT IN []`** lại có ngữ nghĩa khác hoàn toàn. Vì vậy quyết định rỗng phải nằm ở tầng nghiệp vụ/repository, không dựa vào hành vi tình cờ của framework.

## 6. Lớp Spring JDBC hoàn chỉnh: hai cách truy vấn và nhánh rỗng

Ví dụ sau dành cho ứng dụng Spring Boot/Framework có bean `JdbcTemplate` và `NamedParameterJdbcTemplate`, cùng bảng `customer` như mục 7. Các import và kiểu được cung cấp đủ cho lớp; cần thư viện `spring-jdbc` và `spring-context` trên classpath. Đây là mã tích hợp, **không phải chương trình Java thuần chạy chỉ bằng `javac`**.

Tệp `CustomerInRepository.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerInRepository {
    public record Customer(long id, String name) {}

    private static final RowMapper<Customer> ROW_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name")
        );

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerInRepository(
            JdbcTemplate jdbc,
            NamedParameterJdbcTemplate namedJdbc) {
        this.jdbc = jdbc;
        this.namedJdbc = namedJdbc;
    }

    private static List<Long> checkedIds(List<Long> values) {
        Objects.requireNonNull(values, "ids");
        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "ids cannot contain null"
            );
        }
        return values.stream().distinct().toList();
    }

    public List<Customer> findByIdsJdbc(List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return List.of();
        }

        String marks = String.join(
            ", ", Collections.nCopies(ids.size(), "?")
        );
        String sql = """
            SELECT id, name
            FROM customer
            WHERE id IN (%s)
            ORDER BY id
            """.formatted(marks);

        return jdbc.query(sql, ROW_MAPPER, ids.toArray());
    }

    public List<Customer> findByIdsNamed(List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return List.of();
        }

        return namedJdbc.query(
            """
            SELECT id, name
            FROM customer
            WHERE id IN (:ids)
            ORDER BY id
            """,
            new MapSqlParameterSource("ids", ids),
            ROW_MAPPER
        );
    }

    // Xóa giới hạn theo tenant. Empty = không xóa gì.
    public int deleteForTenant(long tenantId, List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return 0;
        }

        return namedJdbc.update(
            """
            DELETE FROM customer
            WHERE tenant_id = :tenantId
              AND id IN (:ids)
            """,
            new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("ids", ids)
        );
    }

    // Với truy vấn đọc NOT IN: empty = không loại ID nào.
    // Quan trọng: vẫn giữ tenant_id để không truy xuất tenant khác.
    public List<Customer> findExceptForTenant(
            long tenantId, List<Long> excludedInput) {
        List<Long> excluded = checkedIds(excludedInput);

        MapSqlParameterSource params =
            new MapSqlParameterSource("tenantId", tenantId);

        if (excluded.isEmpty()) {
            return namedJdbc.query(
                """
                SELECT id, name
                FROM customer
                WHERE tenant_id = :tenantId
                ORDER BY id
                """,
                params,
                ROW_MAPPER
            );
        }

        return namedJdbc.query(
            """
            SELECT id, name
            FROM customer
            WHERE tenant_id = :tenantId
              AND id NOT IN (:excluded)
            ORDER BY id
            """,
            params.addValue("excluded", excluded),
            ROW_MAPPER
        );
    }
}
```

Bốn phương thức thể hiện hai chính sách không được nhầm:

- `findByIdsJdbc([])` và `findByIdsNamed([])` trả `[]`, không thực thi query.
- `deleteForTenant(tenantId, [])` trả số hàng bị sửa `0`, không thực thi `DELETE`.
- `findExceptForTenant(tenantId, [])` **vẫn truy vấn khách hàng trong đúng tenant** và không áp điều kiện loại trừ.
- `findExceptForTenant(tenantId, [1, 3])` dùng `id NOT IN (:excluded)` với hai giá trị được bind.

Bài học về bảo mật: `WHERE tenant_id = :tenantId` là điều kiện bắt buộc trong những phương thức có phạm vi tenant. Không để nhánh rỗng vô tình bỏ điều kiện phân quyền chỉ vì định bỏ `IN` hoặc `NOT IN`.

Bài học về DB: phương thức `deleteForTenant` chỉ nên gọi trong luồng nghiệp vụ có xác thực/quyền phù hợp và quản lý transaction khi cần. Các thao tác ghi khác nhau có thể cần `@Transactional` và cơ chế đối soát; empty-list handling không thay thế chính sách giao dịch.

## 7. Dữ liệu mẫu và kết quả dự kiến

Có thể tạo schema riêng ở H2 hoặc PostgreSQL để kiểm tra:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(80) NOT NULL
);

INSERT INTO customer (id, tenant_id, name) VALUES
    (1, 10, 'Lan'),
    (2, 10, 'Minh'),
    (3, 10, 'Vy'),
    (4, 20, 'An');
```

Ví dụ nếu chạy trên bảng mẫu bằng hai phương thức include:

| Lời gọi | SQL/predicate thực chất | Kết quả |
| --- | --- | --- |
| `findByIdsNamed([1])` | `id IN (?)` | Lan |
| `findByIdsNamed([3, 1])` | `id IN (?, ?)` | Lan, Vy (theo `ORDER BY id`) |
| `findByIdsJdbc([3, 1, 3])` | `id IN (?, ?)` sau `distinct()` | Lan, Vy; không nhân đôi Vy |
| `findByIdsNamed([])` | Không chạy SQL | Danh sách rỗng |
| `findExceptForTenant(10, [1])` | `tenant_id=10 AND id NOT IN (?)` | Minh, Vy |
| `findExceptForTenant(10, [])` | Chỉ `tenant_id=10` | Lan, Minh, Vy |
| `findExceptForTenant(20, [])` | Chỉ `tenant_id=20` | An |

Nếu `findByIdsNamed([1,4])` không nhận tham số tenant, truy vấn có thể trả cả Lan và An. Đây là **lý do phương thức truy vấn trong ứng dụng multi-tenant thường phải có điều kiện tenant**, chứ không phải lý do bỏ qua cơ chế `IN`. Ví dụ include đầu bài là minh họa thuần về binding; trong hệ thống phân quyền thật phải bổ sung filter đã được kiểm tra.

Đừng suy đoán rằng `IN (3, 1)` sẽ trả Vy trước Lan. `IN` là phép kiểm tra thành viên, không áp thứ tự kết quả. Muốn thứ tự xác định dùng `ORDER BY`; muốn chính xác thứ tự **danh sách đầu vào** phải thiết kế sắp xếp riêng ở DB hoặc reorder kết quả theo danh sách đầu vào ở Java.

## 8. Trường hợp rỗng: phân biệt INCLUDE và EXCLUDE

Đây là phần trọng tâm nhất của bài.

### 8.1. Danh sách include rỗng → kết quả rỗng

Nếu chức năng là “tìm khách hàng có ID thuộc các ID được chọn”, người dùng không chọn ID nào thì **không có khách hàng nào khớp**. Ba cách thể hiện:

**Cách A — early return (thường rõ nhất):**

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Không gọi DB, tránh `IN ()` và giảm tải.

**Cách B — predicate luôn FALSE khi SQL vẫn phải chạy:**

```sql
SELECT id, name
FROM customer
WHERE 1 = 0;
```

Nếu còn điều kiện tenant, có thể viết `WHERE tenant_id = ? AND 1 = 0`. Truy vấn vẫn chạy, nhưng logic bộ lọc là không có hàng. Cách này phù hợp khi caller cần một đường thực thi SQL chung, song không bắt buộc cho mọi use case.

**Cách C — biểu diễn bằng cấu trúc DB riêng:** có thể dùng bảng tạm, JOIN với tập giá trị, hoặc mảng và toán tử riêng của DB. Đây là giải pháp phụ thuộc dialect/hạ tầng, không phải thay thế phổ quát.

Không dùng `IN (NULL)` như “mẹo chuẩn hóa rỗng” một cách vô điều kiện: `NULL` mang logic UNKNOWN, có thể tạo sai khác khi phủ định `NOT IN` hoặc khi thêm phép nối/biểu thức khác. Nếu ứng dụng muốn FALSE, hãy biểu diễn FALSE rõ ràng.

### 8.2. Danh sách exclude rỗng → không loại gì

Yêu cầu “lấy các khách hàng trong tenant 10, ngoại trừ các ID được chỉ định”:

- `excluded=[1,3]`: lấy ID 2 trong tenant 10.
- `excluded=[]`: không ID nào bị loại; lấy ID 1, 2, 3 trong tenant 10.

Cách đúng cho truy vấn đọc là **bỏ riêng predicate `NOT IN`**, không bỏ các predicate nghiệp vụ khác:

```sql
-- Nhánh có giá trị:
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
  AND id NOT IN (:excluded)
ORDER BY id;

-- Nhánh excluded rỗng:
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
ORDER BY id;
```

Nhưng với thao tác ghi như `DELETE ... NOT IN (:excluded)`, ý nghĩa “không loại ID nào” có thể biến thành **xóa tất cả hàng đủ điều kiện khác**. Đừng tự động bỏ `NOT IN` rồi chạy `DELETE` trong trường hợp danh sách rỗng; hãy quy định nghiệp vụ là **từ chối danh sách rỗng** hoặc yêu cầu một chế độ “áp dụng cho tất cả” được xác nhận riêng, kèm kiểm tra quyền.

### 8.3. Chính sách rõ theo loại thao tác

| Dạng yêu cầu | Empty-list policy có thể an toàn | Rủi ro nếu xử lý sai |
| --- | --- | --- |
| `SELECT ... WHERE id IN (:ids)` | Trả `[]` / `WHERE 1=0` | `IN ()` lỗi SQL |
| `COUNT ... WHERE id IN (:ids)` | Trả 0 nếu chỉ đếm các ID được chọn; hoặc SQL FALSE | Lỗi SQL, hoặc đếm toàn bảng ngoài ý muốn |
| `UPDATE ... WHERE id IN (:ids)` | Trả số hàng cập nhật 0 | Bỏ nhầm `WHERE` sẽ cập nhật hàng loạt |
| `DELETE ... WHERE id IN (:ids)` | Trả 0, không thực thi SQL | Xóa dữ liệu không mong muốn |
| `SELECT ... WHERE id NOT IN (:ids)` | Bỏ riêng `NOT IN`, giữ điều kiện khác | Vô tình bỏ tenant/ACL |
| `DELETE ... WHERE id NOT IN (:ids)` | Thường **reject empty** theo hợp đồng fail-closed | Có thể xóa hầu hết hoặc toàn bộ bảng |

Không có một nhánh `if (ids.isEmpty()) return List.of()` đúng cho **mọi** phương thức. Nhánh rỗng phải phụ thuộc ngữ nghĩa thao tác, kiểu trả về và rủi ro mở rộng phạm vi.

## 9. NULL trong danh sách: bẫy SQL three-valued logic

Một danh sách có phần tử `null` **không giống** danh sách rỗng. Ví dụ:

```sql
-- Khi id = 1, kết quả TRUE.
WHERE id IN (1, NULL)

-- Khi id = 2, không thấy 1; so với NULL cho UNKNOWN.
-- Điều kiện WHERE không chọn hàng UNKNOWN.
WHERE id IN (1, NULL)

-- Với id = 2, NOT IN (1, NULL) cũng là UNKNOWN,
-- nên hàng id=2 KHÔNG được chọn như nhiều người dự đoán.
WHERE id NOT IN (1, NULL)
```

Giả sử cột `id` không nullable, so sánh:

| Giá trị id | `id IN (1, NULL)` | `id NOT IN (1, NULL)` |
| ---: | --- | --- |
| 1 | TRUE | FALSE |
| 2 | UNKNOWN | UNKNOWN |
| 3 | UNKNOWN | UNKNOWN |

Trong `WHERE`, chỉ các hàng có điều kiện TRUE mới được giữ. Vì vậy `NOT IN (1, NULL)` có thể làm truy vấn trả **0 hàng**, dù rõ ràng ID 2 và 3 khác 1.

**Khuyến nghị cho danh sách ID:** từ chối phần tử null ngay ở Java, như `checkedIds()`. Nếu nghiệp vụ thật sự muốn bao gồm cột nullable có giá trị SQL NULL, hãy diễn đạt riêng bằng `IS NULL`:

```sql
-- Muốn id thuộc tập ID hoặc giá trị id IS NULL:
WHERE id IN (?, ?) OR id IS NULL
```

Khi dùng `AND` và `OR` với điều kiện khác, **đặt ngoặc đúng**:

```sql
WHERE tenant_id = ?
  AND (external_code IN (?, ?) OR external_code IS NULL)
```

Không viết `WHERE external_code IN (NULL)` rồi mong trả các hàng có `external_code IS NULL`. Cú pháp đúng cho NULL là `IS NULL`; các biểu thức so sánh thông thường theo logic ba giá trị.

Với `NOT IN`, một lựa chọn khi dữ liệu loại trừ đến từ một bảng phụ có thể chứa NULL là dùng `NOT EXISTS` với điều kiện tương quan phù hợp; tuy nhiên phải xác định rõ mong muốn khi cột ở bảng chính là NULL. Không đổi cú pháp chỉ để che đi yêu cầu chưa rõ.

## 10. NOT IN với subquery và NOT EXISTS

Ví dụ muốn tìm khách hàng **không có** bản ghi trong bảng `customer_blocklist`:

```sql
SELECT c.id, c.name
FROM customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_blocklist b
    WHERE b.customer_id = c.id
)
ORDER BY c.id;
```

`NOT EXISTS` trả TRUE khi không có hàng phù hợp từ subquery. Nếu `b.customer_id` nullable, điều kiện `b.customer_id = c.id` không coi một giá trị NULL là bằng ID của khách hàng; hàng NULL trong blocklist không làm mọi khách hàng bị loại như nguy cơ `NOT IN (SELECT ...)`.

Để so sánh, câu:

```sql
SELECT c.id
FROM customer c
WHERE c.id NOT IN (
    SELECT b.customer_id FROM customer_blocklist b
);
```

có thể trả kết quả ngoài dự kiến khi subquery sinh ít nhất một `NULL`, vì `NOT IN` vận hành theo logic SQL UNKNOWN. `NOT EXISTS` thường dễ diễn đạt “không có bản ghi quan hệ phù hợp” hơn.

Đây là trường hợp **tập giá trị đến từ bảng**; nếu đầu vào là `List<Long>` của Java, `NamedParameterJdbcTemplate` vẫn là một lựa chọn phù hợp và phải xử lý list rỗng trước khi thực thi.

## 11. Bộ lọc động kết hợp tenant, trạng thái và quyền

Giả sử service chỉ được đọc hàng của tenant hiện tại và người dùng chọn một số ID:

```sql
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
  AND id IN (:ids)
ORDER BY id;
```

Nếu `ids=[]` và ý nghĩa là “chọn không ID nào”, trả `[]`. Nếu `ids=[1,4]`, query vẫn phải giữ `tenant_id=:tenantId`; ID 4 thuộc tenant 20 sẽ không được trả khi tenant đang là 10.

**Không viết nhánh rỗng kiểu**:

```sql
-- NGUY HIỂM: OR 1=1 làm mất toàn bộ hiệu lực lọc.
WHERE tenant_id = :tenantId
   OR 1 = 1
```

Cũng không dùng `WHERE id IN (:ids) OR :emptyFlag = TRUE` trừ khi bạn đã kiểm tra rõ ngữ nghĩa và ranh giới quyền. Nếu `emptyFlag` đúng, điều kiện OR có thể mở rộng kết quả vượt phạm vi người dùng được phép đọc khi thiếu ngoặc hoặc kết hợp sai.

Hai mẫu an toàn khi include rỗng:

1. **Early return** trong service/repository: rõ ràng, không chạy query.
2. **Predicate FALSE** được đặt đúng chỗ bên trong điều kiện tổng: `WHERE tenant_id = :tenantId AND 1 = 0`.

Với những hệ thống có row-level security, quyền tenant vẫn nên được bảo vệ ở nhiều tầng theo kiến trúc phù hợp; code repository không được mặc định là lớp phòng vệ duy nhất.

## 12. Phần tử trùng, thứ tự và kiểu dữ liệu

### 12.1. IN không nhân đôi hàng vì input có trùng

`id IN (1, 1, 3)` là một **điều kiện lọc**, không phải phép JOIN với một bảng chứa ba giá trị. Nếu bảng `customer` chỉ có một hàng cho ID 1, truy vấn không trả Lan hai lần chỉ vì danh sách ID có hai số 1.

Nên khử trùng lặp đầu vào khi không cần giữ bội số:

```java
List<Long> unique = inputIds.stream().distinct().toList();
```

Trong Java 17, `distinct()` trên stream có thứ tự từ một `List` duy trì thứ tự gặp lần đầu. Tuy nhiên **thứ tự kết quả SQL** vẫn phụ thuộc `ORDER BY`, không phụ thuộc thứ tự `unique`.

### 12.2. Muốn giữ đúng thứ tự ID mà client đưa vào?

Ví dụ `inputIds=[3, 1]` nhưng SQL `ORDER BY id` trả `[1, 3]`. Nếu API cần trả đúng `[3, 1]`:

- Có thể truy vấn một lần rồi xây `Map<Long, Customer>` theo ID, sau đó duyệt `inputIds` để sắp xếp kết quả ở Java (quy định rõ ID lặp có nhân đôi output không).
- Hoặc dùng cú pháp sắp xếp đặc thù DB như `CASE` hoặc hàm sắp xếp của dialect; phải bind giá trị đúng và kiểm tra chi phí query.

Đừng mặc định `IN (...)` là thứ tự. Cũng đừng ép tất cả kết quả về cùng thứ tự input nếu nghiệp vụ cần phân trang hoặc sắp xếp theo cột khác.

### 12.3. Kiểu dữ liệu và chuyển đổi

Nếu `id` là `BIGINT`, dùng `Long`/`setLong` phù hợp. Với UUID, String hay enum, xác định kiểu thật của cột và cách driver bind, thay vì truyền mọi thứ thành chuỗi SQL để DB tự ép kiểu. Nếu cần chỉ định SQL type rõ hơn (đặc biệt với giá trị NULL), Spring có `SqlParameterValue` hoặc `MapSqlParameterSource.registerSqlType`, nhưng trong bài này ID null bị cấm nên không cần xử lý NULL bên trong danh sách.

## 13. Khi có nhiều điều kiện IN cùng lúc

Truy vấn có hai danh sách độc lập:

```sql
SELECT id, name
FROM customer
WHERE tenant_id IN (:tenantIds)
  AND id IN (:customerIds)
ORDER BY id;
```

Nếu mỗi tập là bộ lọc bắt buộc kiểu INCLUDE, **bất kỳ tập nào rỗng** thì kết quả là rỗng. Có thể trả sớm trước khi gửi SQL:

```java
if (tenantIds.isEmpty() || customerIds.isEmpty()) {
    return List.of();
}
```

Nhưng nếu một bộ lọc là **tùy chọn**, phải phân biệt:

- Tham số `null` nghĩa là “không áp bộ lọc” theo hợp đồng API?
- Danh sách `[]` nghĩa là “không lựa chọn giá trị nào” hay “không lọc”?
- Người gọi có được phép bỏ bộ lọc tenant không?

Không nên dùng một kiểu `List` mơ hồ rồi âm thầm quyết định. Có thể tạo DTO request tách hai ý định:

```java
record FilterByIds(boolean enabled, List<Long> ids) {}
```

Đây là kiểu minh họa, chưa bao gồm validate constructor. Nếu `enabled=true, ids=[]`, nghĩa “đang lọc theo tập rỗng” thường phải trả 0 hàng; nếu `enabled=false`, hệ thống có thể bỏ bộ lọc **nếu quyền truy cập cho phép**. Trạng thái “không lọc” không được suy ra tự động từ danh sách rỗng trong các thao tác nhạy cảm.

## 14. Danh sách lớn: giới hạn driver, DB và hiệu năng

`NamedParameterJdbcTemplate` giúp mở rộng list, nhưng **không làm biến mất giới hạn của SQL/DB/driver**. Spring Framework nhắc rõ các hệ quản trị thường đặt giới hạn số biểu thức trong `IN`. Ví dụ tài liệu Spring nêu giới hạn `1000` biểu thức trong list `IN` ở Oracle; các DB và phiên bản có ràng buộc khác, bao gồm tổng số tham số một statement.

Với danh sách rất lớn cần cân nhắc:

1. **Giới hạn kích thước input ở API** dựa trên nhu cầu thật: không để một request bất kỳ xây SQL có hàng chục nghìn placeholder nếu không có lý do.
2. **Đo thời gian chuẩn bị, parse/plan và thực thi:** SQL thay đổi số lượng dấu `?` theo độ dài list, tạo nhiều hình dạng câu lệnh; cache statement/plan có thể kém hiệu quả.
3. **Dùng một bảng tạm/bảng staging/quan hệ có khóa** để lưu tập ID rồi `JOIN` khi danh sách đủ lớn và hệ thống hỗ trợ.
4. **Dùng giải pháp đặc thù DB**: PostgreSQL có mảng SQL và cú pháp `id = ANY(array_expression)`; một mảng rỗng cho kết quả FALSE khi dùng toán tử so sánh thông thường. Nhưng cách bind JDBC `Array`, tên kiểu, xử lý NULL và tài nguyên phụ thuộc driver; không phải cú pháp SQL chuẩn dùng chung.
5. **Chia lô** khi thực sự cần, nhưng phải bảo đảm ngữ nghĩa truy vấn, phân trang, sắp xếp, transaction và phép kết hợp kết quả đúng.

### Chia lô cần chú ý phép AND/OR

Nếu phải tách `IN` thành nhiều nhóm trong **một SQL**, phép kết hợp đúng cho include thường là **OR**:

```sql
WHERE tenant_id = ?
  AND (
      id IN (?, ?, ?)
      OR id IN (?, ?, ?)
  )
```

Nhưng với bộ lọc **NOT IN**, để “không thuộc bất kỳ nhóm loại trừ nào” thì thường cần **AND**:

```sql
WHERE tenant_id = ?
  AND id NOT IN (?, ?, ?)
  AND id NOT IN (?, ?, ?)
```

Với input chứa NULL, phép biến đổi cần xét logic UNKNOWN; đừng phát sinh SQL từ công thức máy móc mà không kiểm thử. Ngoài ra, tách thành **nhiều truy vấn** rồi nối list output có thể làm thay đổi thứ tự toàn cục, giới hạn `LIMIT/OFFSET`, snapshot dữ liệu và tính duy nhất. Một SQL với nhiều nhánh `OR` cũng không vượt được mọi giới hạn tổng tham số của DB. Khi danh sách lớn, nhiều trường hợp bảng staging và JOIN thích hợp hơn.

Đừng cố chọn một “ngưỡng tối ưu” dùng chung cho mọi DB và hệ thống. Thử nghiệm thực tế với schema, indexes, dữ liệu và workload của ứng dụng.

## 15. Quy trình kiểm thử các trường hợp cạnh

Tối thiểu phải kiểm tra:

| Test case | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Rỗng | `[]` | INCLUDE trả `[]`/DML IN trả 0; không phát sinh `IN ()` |
| Một phần tử | `[1]` | Một `?` hoặc một giá trị trong named list; đúng hàng 1 |
| Nhiều phần tử | `[3, 1]` | Hai bind; kết quả theo `ORDER BY`, không phải thứ tự input |
| Trùng | `[3, 1, 3]` | Không nhân đôi hàng; nếu chuẩn hóa thì hai bind |
| Không có ID hợp lệ trong DB | `[999]` | Danh sách rỗng nhưng **có thực thi SQL** |
| Danh sách `null` | `null` | Lỗi đầu vào rõ ràng, không bị coi là “không lọc” |
| Có phần tử null | `[1, null]` | Reject hoặc quy tắc đặc biệt đã viết; không vô thức tạo `NOT IN (..., NULL)` |
| Exclude rỗng | `[]` | Không áp `NOT IN` trong truy vấn đọc; luôn giữ tenant/ACL |
| DELETE IN rỗng | `[]` | Không chạy `DELETE`; số hàng 0 |
| DELETE NOT IN rỗng | `[]` | Phải có chính sách chặn/thao tác all explicit; không tự xóa rộng |
| Nhiều giá trị hơn giới hạn DB | List lớn | Báo lỗi đầu vào hoặc chuyển sang chiến lược khác |
| ID của tenant khác | `[1,4]`, tenant 10 | Không được trả ID 4 nếu API có tenant scope |
| Thứ tự | `[3,1]` | Kiểm tra kết quả theo `ORDER BY id` hoặc chính sách reorder rõ ràng |

Hai nhóm test khác nhau:

- **Unit test**: kiểm tra helper chuẩn hóa list, nhánh empty, số placeholder và số tham số bind, thứ tự, bảo vệ null, không phát sinh SQL cho empty khi thiết kế như vậy.
- **Integration test**: dùng DB tương ứng và Spring JDBC thật, xác minh `NamedParameterJdbcTemplate` mở rộng list, SQL hoạt động, type binding đúng và điều kiện tenant giữ nguyên. Với thao tác xóa/sửa, test trong giao dịch được rollback hoặc DB kiểm thử riêng.

Đặc biệt, test `[]` **không được chỉ xác nhận hàm không ném exception**. Cần kiểm tra xem repository có vô tình truy vấn tất cả hàng hoặc thao tác ghi rộng hay không.

## 16. Chương trình Java 17 độc lập: kế hoạch IN và nhánh rỗng

Ví dụ này **không truy cập DB và không dùng Spring**. Nó minh họa bước quyết định SQL sẽ được thực thi hay không, tạo placeholder theo số ID, loại phần tử lặp và mô phỏng các hàng trả về sau `ORDER BY id`.

Tạo tệp `InListPolicyDemo.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public final class InListPolicyDemo {
    record InPlan(boolean execute, String sql, List<Long> parameters) {}

    static InPlan plan(List<Long> ids) {
        Objects.requireNonNull(ids, "ids");
        if (ids.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("ids cannot contain null");
        }
        List<Long> unique = ids.stream().distinct().toList();
        if (unique.isEmpty()) {
            return new InPlan(false, "", List.of());
        }
        String marks = String.join(", ", Collections.nCopies(unique.size(), "?"));
        String sql = "SELECT id FROM customer WHERE id IN (" + marks + ") ORDER BY id";
        return new InPlan(true, sql, unique);
    }

    static List<Long> simulateDatabase(InPlan plan) {
        if (!plan.execute()) {
            return List.of();
        }
        Set<Long> wanted = new HashSet<>(plan.parameters());
        return List.of(1L, 2L, 3L).stream()
            .filter(wanted::contains)
            .toList();
    }

    public static void main(String[] args) {
        InPlan withIds = plan(List.of(3L, 1L, 3L));
        System.out.println(withIds.sql());
        System.out.println("bind=" + withIds.parameters());
        System.out.println("rows=" + simulateDatabase(withIds));

        InPlan empty = plan(List.of());
        System.out.println("empty.execute=" + empty.execute());
        System.out.println("empty.bind=" + empty.parameters());
        System.out.println("empty.rows=" + simulateDatabase(empty));
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 InListPolicyDemo.java
java InListPolicyDemo
```

Kết quả chính xác:

```text
SELECT id FROM customer WHERE id IN (?, ?) ORDER BY id
bind=[3, 1]
rows=[1, 3]
empty.execute=false
empty.bind=[]
empty.rows=[]
```

Giải thích đầu ra:

- Input `[3,1,3]` được chuẩn hóa thành `[3,1]` → hai placeholder.
- `rows=[1,3]` là danh sách sau bước mô phỏng đọc DB theo `ORDER BY id`, không nhất thiết trùng thứ tự bind.
- Với danh sách rỗng, `execute=false`; không có `IN ()`, không gọi DB và tập hàng mô phỏng rỗng.
- `InPlan` là record tự định nghĩa để học, **không phải lớp của Spring**. Trong repository thật, tham số được bind bằng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`, không dùng bộ lọc Java làm thay chức năng SQL.

Đây cũng là cách tách logic để unit test: hàm `plan(...)` không cần kết nối DB; với Spring thật có thể viết kiểm thử riêng cho repository.

## 17. Các lỗi phổ biến và cách sửa

### Lỗi 1: Truyền chuỗi CSV làm một tham số

`id IN (?)` với `"1,3"` không tương đương `id IN (1,3)`. Sửa bằng placeholder động hoặc named parameter list expansion.

### Lỗi 2: Cho danh sách rỗng đi thẳng vào SQL

Tạo `IN ()` có thể khiến query lỗi cú pháp. Sửa: nhánh `isEmpty()` trước khi gọi DB; xác định return value đúng với nghiệp vụ.

### Lỗi 3: Coi empty list và null list là một

`null` có thể nghĩa “tham số chưa được gửi”, “không áp filter” hoặc lỗi; `[]` thường nghĩa “đã chọn tập rỗng”. Quy định hợp đồng API thay vì trộn chúng.

### Lỗi 4: Xử lý `NOT IN []` giống `IN []`

Với truy vấn đọc, `NOT IN []` thường nghĩa “không loại ai”, không phải trả rỗng. Với thao tác ghi, bỏ predicate khi empty có thể làm **UPDATE/DELETE rộng**; fail closed.

### Lỗi 5: Dùng `IN (NULL)` làm biểu thức rỗng

Có thể gây khác biệt theo logic ba giá trị, đặc biệt khi phủ định và kết hợp điều kiện khác. Nếu muốn FALSE, dùng nhánh return hoặc predicate FALSE rõ ràng.

### Lỗi 6: Cho `null` vào `NOT IN`

`NOT IN (1, NULL)` thường khiến nhiều hàng thành UNKNOWN và không được chọn. Sửa: validate input không null, hoặc thiết kế NULL semantics riêng; cân nhắc `NOT EXISTS` cho subquery.

### Lỗi 7: Nối thẳng giá trị vào SQL

Ghép chuỗi của ID/string không tin cậy vào SQL dễ gây injection. Sửa: chỉ chèn **kết cấu dấu hỏi** được sinh từ số lượng phần tử, còn giá trị đi qua bind.

### Lỗi 8: Chèn động tên bảng/cột bằng `?`

`?` chỉ bind **giá trị**, không thay được tên identifier hoặc từ khóa SQL. Nếu cột cần động, chọn qua whitelist cột cho phép.

### Lỗi 9: Dùng `IN` để kỳ vọng giữ thứ tự ID người dùng

`IN (3,1)` không bảo đảm kết quả [3,1]. Sửa: dùng `ORDER BY` hoặc logic reorder theo input khi thật sự cần.

### Lỗi 10: Nghĩ input trùng làm SQL trả hàng trùng

`IN (3,3)` là predicate; nó không làm một hàng DB xuất hiện hai lần. Nếu query trả trùng, kiểm tra `JOIN`/dữ liệu trước khi đổ lỗi cho list.

### Lỗi 11: Không kiểm soát tenant khi lọc ID

Một danh sách hợp lệ vẫn có thể chứa ID không thuộc phạm vi người gọi. Sửa: mọi SQL phải giữ điều kiện tenant/authorization, kể cả nhánh empty và nhánh `NOT IN`.

### Lỗi 12: Tin list expansion không giới hạn kích thước

DB/driver có giới hạn số biểu thức hoặc tham số. Sửa: chặn list quá lớn, đo hiệu năng, dùng staging table/array đặc thù DB khi thích hợp.

### Lỗi 13: Chia nhiều nhóm `NOT IN` rồi nối bằng OR

`id NOT IN (1,2) OR id NOT IN (3,4)` gần như luôn rộng hơn ý định loại cả hai nhóm. Sửa: với các tập không null và logic “khác tất cả”, kết hợp **AND**.

### Lỗi 14: Phân trang từng chunk rồi ghép tùy tiện

`LIMIT/OFFSET` áp trên từng chunk không tương đương phân trang trên toàn kết quả đã hợp nhất. Sửa: lập kế hoạch truy vấn và thứ tự toàn cục trước khi chia lô.

### Lỗi 15: Không phân biệt “0 hàng khớp” và “không chạy SQL”

`findByIds([999])` vẫn có query và kết quả 0 hàng; `findByIds([])` theo chính sách của bài **không có query**. Điều này có thể ảnh hưởng audit/metrics, nên cần kiểm thử theo yêu cầu vận hành.

## 18. Câu hỏi tự kiểm tra

**1. Tại sao không viết `WHERE id IN (?)` rồi bind một chuỗi `"1,2,3"`?**  
Vì một dấu `?` là một tham số JDBC; chuỗi CSV không tự chuyển thành ba giá trị. Cần ba placeholder hoặc named parameter expansion.

**2. Với `ids = List.of(4L, 1L)`, cách JDBC động tạo mấy `?`?**  
Hai; ví dụ `IN (?, ?)` và truyền hai giá trị bind riêng.

**3. Nếu `ids=[]` và đây là query “chọn đúng các ID được yêu cầu”, kết quả là gì?**  
Danh sách rỗng hoặc predicate FALSE. Không gọi `IN ()` một cách mù quáng.

**4. Nếu `excludedIds=[]` cho truy vấn đọc `NOT IN` thì trả rỗng không?**  
Không, khi ý định là “không loại ai”, chỉ bỏ điều kiện loại trừ và giữ các điều kiện khác như tenant.

**5. Vì sao nhánh empty của `DELETE ... WHERE id NOT IN (:ids)` nguy hiểm?**  
Vì bỏ `NOT IN` có thể khiến DELETE tác động tới mọi hàng còn thỏa điều kiện, thậm chí toàn bảng nếu WHERE khác cũng bị bỏ. Nên từ chối empty hoặc yêu cầu chế độ toàn phạm vi riêng.

**6. `[1, 1, 3]` có tạo ba hàng từ một bảng chỉ có ID 1 và 3 không?**  
Không. `IN` là predicate; mỗi hàng của bảng được chọn theo điều kiện, không nhân số hàng theo số lần input lặp.

**7. `id NOT IN (1, NULL)` có trả ID 2 hay không?**  
Trong `WHERE`, thông thường không: điều kiện là UNKNOWN vì có NULL trong danh sách, nên hàng không được chọn.

**8. `IN (3, 1)` có bảo đảm trả ID 3 trước ID 1?**  
Không. Thứ tự phụ thuộc `ORDER BY` hoặc chính sách sắp xếp sau truy vấn.

**9. Khi danh sách có hàng nghìn ID, chỉ cần tăng độ dài SQL là đủ?**  
Không. Cần kiểm tra giới hạn DB/driver, tổng tham số, chi phí parse/plan, indexing và chiến lược thay thế (bảng staging, array đặc thù DB, batch đúng ngữ nghĩa).

**10. Nếu có hai bộ lọc INCLUDE và một list rỗng, có nên bỏ bộ lọc rỗng để query “không quá ít” không?**  
Không nếu list rỗng nghĩa “không chọn giá trị nào”: kết quả chung phải rỗng. Chỉ bỏ bộ lọc khi contract tuyên bố rõ nó là tùy chọn và caller có quyền làm vậy.

## 19. Ghi nhớ

- `IN` là **phép kiểm tra thành viên**, không quyết định thứ tự và không nhân bản hàng vì ID lặp.
- JDBC `?` đại diện **một giá trị**, vì vậy `JdbcTemplate` cần số `?` tương ứng với số phần tử; `NamedParameterJdbcTemplate` có thể mở rộng `IN (:ids)` từ `List`.
- **Luôn xử lý danh sách rỗng trước khi thực thi**: include rỗng thường trả tập rỗng; exclude rỗng thường bỏ riêng điều kiện loại trừ khi truy vấn đọc; thao tác ghi nhạy cảm cần fail-closed.
- Không coi `null` và `[]` là một; không truyền phần tử `NULL` vào `NOT IN` nếu chưa thiết kế ngữ nghĩa.
- Sinh SQL chỉ từ cấu trúc đáng tin (các dấu `?`), bind giá trị riêng; không ghép CSV/giá trị người dùng vào SQL.
- Giữ nguyên các điều kiện tenant, phân quyền, trạng thái và điều kiện khác khi xử lý nhánh rỗng.
- Theo dõi kích thước danh sách, giới hạn DB/driver và hiệu năng; với input lớn có thể phải chọn bảng staging, JOIN, array đặc thù DB hoặc batch có kiểm chứng.
- Kiểm thử cả 0, 1, N phần tử; trùng, null, ID không tồn tại, ID khác tenant và cả `IN`/`NOT IN` trước khi đưa vào production.

### Tài liệu tham khảo

- [Spring Framework — Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html)
- [Spring Framework — Choosing an Approach for JDBC Database Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html)
- [Spring Framework Javadoc — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html)
- [Spring Framework Javadoc — JdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [PostgreSQL — Row and Array Comparisons (IN, NOT IN, ANY)](https://www.postgresql.org/docs/current/functions-comparisons.html)
