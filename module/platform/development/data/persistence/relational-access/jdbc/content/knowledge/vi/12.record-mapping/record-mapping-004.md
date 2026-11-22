# Xử lý cột nullable và thuộc tính tùy chọn

Trong JDBC, ánh xạ một hàng của `ResultSet` thành đối tượng Java tưởng như chỉ là gọi các phương thức `getXxx()`. Tuy nhiên, khi cột SQL cho phép `NULL`, lựa chọn kiểu Java và cách đọc giá trị quyết định liệu ứng dụng còn phân biệt được **không có dữ liệu**, **giá trị 0**, **`false`**, **chuỗi rỗng** và **không tìm thấy bản ghi** hay không.

Bài học thuộc chủ đề **Ánh xạ bản ghi** của module **JDBC**: sử dụng `DataSource`, `PreparedStatement`, `ResultSet` và các API chuẩn của Java để chuyển dữ liệu quan hệ thành Java record/DTO, ghi lại giá trị nullable, thực hiện CRUD an toàn và kiểm thử tính đúng đắn. Mục tiêu là xây dựng một **hợp đồng null nhất quán giữa schema SQL, mã ánh xạ và logic nghiệp vụ**.

## 1. Xác định chính xác `NULL` có nghĩa gì

`NULL` trong SQL biểu thị **không có một giá trị được biết/xác định** cho cột tại thời điểm đó. Không nên tự động đồng nhất nó với một giá trị mặc định của Java hoặc với việc không tồn tại hàng.

| Trường hợp | Dữ liệu SQL | Ý nghĩa có thể có trong nghiệp vụ | Giá trị Java cần giữ |
| --- | --- | --- | --- |
| Tuổi chưa được cung cấp | `age IS NULL` | Chưa biết tuổi | `Integer age = null` |
| Tuổi bằng không | `age = 0` | Tuổi đã biết và bằng 0 | `Integer.valueOf(0)` |
| Chưa có lựa chọn đồng ý nhận tin | `marketing_consent IS NULL` | Chưa có quyết định | `Boolean consent = null` |
| Từ chối nhận tin | `marketing_consent = FALSE` | Đã trả lời không | `Boolean.FALSE` |
| Chưa có tên hiển thị | `display_name IS NULL` | Chưa nhập | `String displayName = null` |
| Tên hiển thị là chuỗi rỗng | `display_name = ''` | Đã lưu một chuỗi có độ dài 0 | `String displayName = ""` |
| Không có hàng với khóa cần tìm | `SELECT` trả 0 hàng | Không tìm thấy thực thể | `Optional.empty()` ở tầng DAO |

Một số hệ quản trị có cách xử lý chuỗi rỗng khác nhau; ví dụ Oracle thường coi chuỗi ký tự rỗng là `NULL`. Vì vậy, chính sách `NULL`/chuỗi rỗng phải được kiểm tra theo hệ quản trị thực tế. Tương tự, `NULL` không tự động có nghĩa là “người dùng từ chối”; diễn giải của nó phải nằm trong đặc tả trường dữ liệu.

Khi thiết kế model, hãy hỏi: **trường có thật sự được phép vắng mặt không, và nếu có thì người sử dụng dữ liệu cần phân biệt vắng mặt với giá trị mặc định nào?**

## 2. Thống nhất nullability ngay trong schema

Ví dụ quản lý hồ sơ khách hàng trên PostgreSQL:

```sql
CREATE TABLE customer_profiles (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name         VARCHAR(120) NOT NULL,
    display_name      VARCHAR(120) NULL,
    age               INTEGER NULL CHECK (age >= 0),
    marketing_consent BOOLEAN NULL,
    birth_date        DATE NULL
);
```

- `id`, `full_name` bắt buộc có giá trị: mapper có thể đặt bất biến tương ứng cho Java record.
- `display_name`, `age`, `marketing_consent`, `birth_date` được phép `NULL`: mapper cần giữ được trạng thái thiếu dữ liệu.
- `CHECK (age >= 0)` **không loại bỏ `NULL`** theo logic ba giá trị của SQL; ràng buộc `NOT NULL` mới buộc cột không `NULL`.
- Khai báo `DEFAULT` không đồng nghĩa với `NOT NULL`. Khi lệnh `INSERT` **bỏ qua cột** hoặc dùng từ khóa `DEFAULT`, DB có thể áp dụng mặc định; ghi **`NULL` tường minh** vào cột nullable vẫn là `NULL`, còn vào cột `NOT NULL` thường gây lỗi.
- Không tạo `NULL` chỉ vì “để linh hoạt”. Ví dụ `created_at` nếu luôn phải có để truy vết, nên có `NOT NULL` và quy tắc cấp giá trị rõ ràng.

Các ví dụ SQL sau dùng PostgreSQL. Kiểu `DATE`, `INTEGER`, `BOOLEAN` và cách đánh dấu nullable tương đối phổ biến, nhưng cú pháp `IDENTITY`, các kiểu SQL và chuyển đổi JDBC có thể khác giữa các DB/driver.

## 3. Chọn kiểu Java để giữ nguyên khả năng phân biệt

| Kiểu cột SQL | Có thể `NULL`? | Java thường chọn | Tránh |
| --- | --- | --- | --- |
| `BIGINT` khóa chính | Không | `long` nếu model bảo đảm khóa tồn tại | Dùng `0` thay cho bản ghi không tồn tại |
| `INTEGER` | Có | `Integer` | `int` làm mất `NULL` |
| `BOOLEAN` | Có | `Boolean` | `boolean` làm `NULL` thành `false` |
| `DECIMAL(p,s)` | Có | `BigDecimal` | `double` cho dữ liệu tiền và giá trị nullable |
| `VARCHAR` | Có | `String` (có thể `null`) | Tự động thay `NULL` bằng `""` |
| `DATE` | Có | `LocalDate` (có thể `null`) | Biến ngày thuần túy thành timestamp |
| `TIMESTAMP` | Có | Kiểu `java.time` tương ứng với ngữ nghĩa và driver | Suy đoán múi giờ từ JVM |

Các kiểu **primitive** (`int`, `long`, `boolean`...) không thể mang `null`. Các kiểu tham chiếu (`Integer`, `Boolean`, `String`, `LocalDate`...) cho phép `null`, nhưng vẫn cần schema và quy tắc nghiệp vụ quyết định khi nào hợp lệ.

Java `record` (Java 16+) phù hợp để mô tả một hàng đã ánh xạ:

```java
import java.time.LocalDate;
import java.util.Objects;
import java.util.Optional;

public record CustomerProfile(
        long id,
        String fullName,
        String displayName,
        Integer age,
        Boolean marketingConsent,
        LocalDate birthDate) {

    public CustomerProfile {
        Objects.requireNonNull(fullName, "fullName");
    }

    // Phục vụ mã gọi muốn thao tác theo kiểu Optional.
    public Optional<String> optionalDisplayName() {
        return Optional.ofNullable(displayName);
    }
}
```

`record` **không tự động ngăn `null`** ở các thành phần kiểu tham chiếu. Constructor ở đây bảo vệ riêng `fullName`, còn `displayName`, `age`, `marketingConsent` và `birthDate` có thể vắng mặt theo schema. Mọi chỗ sử dụng model phải tôn trọng hợp đồng đó.

Không cần mặc định khai báo mọi thành phần nullable thành `Optional<T>`. `Optional` đặc biệt hữu ích cho **kiểu trả về của phương thức**; với trường dữ liệu lưu trữ, serialization hoặc framework, `T` có thể `null` và một accessor trả `Optional<T>` thường đơn giản hơn. Nếu dự án quy ước record component dùng `Optional`, toàn bộ mapper, serializer và code gọi phải tuân thủ nhất quán: không bao giờ truyền chính `null` làm giá trị cho `Optional`.

## 4. Đọc cột nullable từ `ResultSet`

Đây là phần dễ phát sinh lỗi âm thầm nhất.

### 4.1. Getter trả kiểu primitive cần `wasNull()`

`ResultSet.getInt(...)` trả `0` khi cột SQL là `NULL`; `getBoolean(...)` trả `false`; `getLong(...)` cũng trả `0`. Hãy gọi `rs.wasNull()` **ngay sau getter của cột cần xét**, trước khi đọc cột khác.

```java
int rawAge = rs.getInt("age");
Integer age = rs.wasNull() ? null : rawAge;

boolean rawConsent = rs.getBoolean("marketing_consent");
Boolean consent = rs.wasNull() ? null : rawConsent;
```

Đừng làm như sau:

```java
// SAI: 0 và false có thể là giá trị thực, không chỉ SQL NULL.
Integer age = rs.getInt("age");
Boolean consent = rs.getBoolean("marketing_consent");

// SAI: wasNull() chỉ cho biết trạng thái của cột vừa được đọc gần nhất.
int value = rs.getInt("age");
rs.getString("display_name");
Integer lateCheck = rs.wasNull() ? null : value;
```

`wasNull()` không kiểm tra “một cột có nullable theo schema hay không”; nó chỉ cho biết **lần đọc cột gần nhất** có nhận SQL `NULL` hay không.

### 4.2. Getter trả kiểu tham chiếu

Với các getter tham chiếu thông dụng:

```java
String name = rs.getString("display_name");         // NULL -> null
java.math.BigDecimal budget = rs.getBigDecimal("budget"); // NULL -> null
java.sql.Date sqlDate = rs.getDate("birth_date");   // NULL -> null
```

Không cần `wasNull()` để phân biệt SQL `NULL` khi chính getter đã trả `null`. Tuy nhiên, getter **không** thay thế bước kiểm tra tên cột có tồn tại; nếu `SELECT` không trả cột yêu cầu, driver thường ném `SQLException`.

JDBC 4.2 cũng hỗ trợ `getObject(columnLabel, SomeType.class)` với nhiều kiểu Java; **mức hỗ trợ cụ thể tùy driver**:

```java
Integer age = rs.getObject("age", Integer.class);
Boolean consent = rs.getObject("marketing_consent", Boolean.class);
LocalDate birthDate = rs.getObject("birth_date", LocalDate.class);
```

Với driver hỗ trợ ánh xạ này, SQL `NULL` cho ra `null`. Nếu một driver không hỗ trợ kiểu được yêu cầu, cần dùng cách đọc phù hợp với driver hoặc getter chuẩn, ví dụ đọc `java.sql.Date` rồi gọi `toLocalDate()` khi khác `null`. Tránh ép kiểu bừa `(Integer) rs.getObject(...)` nếu chưa xác nhận DB/driver thực sự trả `Integer`.

### 4.3. Một mapper đầy đủ, phân biệt rõ `NULL`

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public final class CustomerProfileMapper {
    private CustomerProfileMapper() {}

    public static CustomerProfile map(ResultSet rs) throws SQLException {
        long id = rs.getLong("id"); // id là PRIMARY KEY, NOT NULL

        String fullName = rs.getString("full_name");
        if (fullName == null) {
            throw new SQLException("full_name không được NULL");
        }

        String displayName = rs.getString("display_name");

        int rawAge = rs.getInt("age");
        Integer age = rs.wasNull() ? null : rawAge;

        boolean rawConsent = rs.getBoolean("marketing_consent");
        Boolean consent = rs.wasNull() ? null : rawConsent;

        // JDBC 4.2: xác nhận driver hỗ trợ LocalDate.
        LocalDate birthDate =
                rs.getObject("birth_date", LocalDate.class);

        return new CustomerProfile(
                id, fullName, displayName, age, consent, birthDate);
    }
}
```

Mapper trên nhận một `ResultSet` **đã ở hàng hợp lệ** (`rs.next()` đã trả `true`). Nó không tự gọi `next()` và không đóng `ResultSet`: vòng đời tài nguyên thuộc DAO gọi nó. Đây là cách tránh lỗi mapper nhảy qua hàng hoặc đóng tài nguyên trước khi DAO đọc xong.

Cũng nên làm rõ đầu vào của mapper: câu `SELECT` phải trả các nhãn cột `id`, `full_name`, `display_name`, `age`, `marketing_consent` và `birth_date`. Khi có alias, mapper đọc **alias** trong kết quả, không phải tùy tiện tên cột gốc.

## 5. Không tìm thấy hàng khác với hàng chứa `NULL`

Ví dụ DAO tìm hồ sơ theo khóa chính:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerProfileDao {
    private final DataSource dataSource;

    public CustomerProfileDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<CustomerProfile> findById(long id)
            throws SQLException {
        String sql = """
                SELECT id, full_name, display_name, age,
                       marketing_consent, birth_date
                FROM customer_profiles
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không tồn tại hàng.
                }
                return Optional.of(CustomerProfileMapper.map(rs));
            }
        }
    }
}
```

Đoạn code dùng Java 17+ (do có text block `"""`). Nếu chưa dùng phiên bản hỗ trợ text block, thay câu SQL bằng chuỗi ghép thông thường. `try-with-resources` đảm bảo đóng `ResultSet`, `PreparedStatement` và `Connection`, kể cả khi mapper ném ngoại lệ.

Đọc kết quả ở tầng gọi:

```java
Optional<CustomerProfile> found = dao.findById(42L);

if (found.isEmpty()) {
    // Không có hồ sơ id = 42.
} else {
    CustomerProfile profile = found.orElseThrow();
    String label = profile.optionalDisplayName()
            .orElse(profile.fullName());
    // label chỉ là giá trị dùng để hiển thị.
    // profile.displayName() vẫn có thể null và chưa bị thay đổi.
}
```

**Ba trạng thái cần phân biệt:**

1. `Optional.empty()` từ `findById`: không tìm thấy hàng.
2. `Optional.of(profile)` với `profile.displayName() == null`: hàng tồn tại nhưng cột là SQL `NULL`.
3. `Optional.of(profile)` với `profile.displayName().isEmpty()`: hàng tồn tại và cột chứa chuỗi rỗng.

Không dùng `Optional.empty()` cho cả “hàng không tồn tại” lẫn “cột nullable trong một hàng tồn tại” nếu người gọi cần biết sự khác biệt. Cũng không dùng `Optional.of(rs.getString("display_name"))`: phương thức `of` ném `NullPointerException` khi nhận `null`; dùng `ofNullable` khi phù hợp.

## 6. Ghi `NULL` đúng kiểu bằng `PreparedStatement`

SQL tham số hóa bảo vệ cách gửi giá trị và tránh nối chuỗi thủ công. Khi ghi `NULL`, dùng `setNull(index, sqlType)` để JDBC biết **kiểu SQL của tham số**. Đừng mặc định `setObject(index, null)` luôn suy ra đúng kiểu trên mọi driver.

Ví dụ **thay thế toàn bộ nhóm thuộc tính tùy chọn** của một hồ sơ; giá trị Java `null` ở đây có nghĩa là chủ động ghi SQL `NULL`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDate;
import javax.sql.DataSource;

public final class CustomerProfileWriter {
    private CustomerProfileWriter() {}

    public static boolean replaceOptionalFields(
            DataSource dataSource,
            long id,
            String displayName,
            Integer age,
            Boolean marketingConsent,
            LocalDate birthDate) throws SQLException {
        String sql = """
                UPDATE customer_profiles
                SET display_name = ?, age = ?,
                    marketing_consent = ?, birth_date = ?
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            if (displayName == null) ps.setNull(1, Types.VARCHAR);
            else ps.setString(1, displayName);

            if (age == null) ps.setNull(2, Types.INTEGER);
            else ps.setInt(2, age);

            if (marketingConsent == null) ps.setNull(3, Types.BOOLEAN);
            else ps.setBoolean(3, marketingConsent);

            if (birthDate == null) ps.setNull(4, Types.DATE);
            else ps.setObject(4, birthDate); // JDBC 4.2, driver hỗ trợ.

            ps.setLong(5, id);
            return ps.executeUpdate() == 1;
        }
    }
}
```

- `false` và `0` vẫn được ghi là **giá trị thực** bằng `setBoolean` và `setInt`.
- `setNull` dùng loại JDBC phù hợp với cột: `Types.VARCHAR`, `INTEGER`, `BOOLEAN`, `DATE`...
- Các giá trị cho `NOT NULL` nên được kiểm tra trước khi gửi; DB vẫn là lớp bảo vệ cuối cùng.
- Lệnh trả `false` khi `executeUpdate() != 1` (ví dụ không tồn tại id); trong một hệ thống có trigger/DB đặc biệt cần xác nhận ý nghĩa số hàng bị ảnh hưởng. Trường hợp lỗi ràng buộc sẽ ném `SQLException`.
- Nếu nhiều cột liên quan phải thay đổi đồng bộ qua **nhiều lệnh SQL**, dùng một transaction với `commit`/`rollback` rõ ràng. Bản cập nhật bốn cột trong một câu `UPDATE` là một thao tác nguyên tử của DB.

Với `INSERT`, phân biệt:

```sql
-- Bỏ qua cột: DB áp dụng DEFAULT của cột nếu có.
INSERT INTO customer_profiles (full_name)
VALUES ('Lan');

-- Ghi NULL tường minh, dù cột có thể có DEFAULT.
INSERT INTO customer_profiles (full_name, display_name)
VALUES ('Lan', NULL);
```

Khi chuyển sang `PreparedStatement`, hãy xác định trường nào được phép bỏ qua và trường nào được gửi giá trị `NULL`, vì hai hành động này có thể khác nhau.

## 7. Thuộc tính không gửi lên khác với thuộc tính yêu cầu xóa

Trong một API cập nhật một phần (`PATCH`), chỉ dùng `String displayName = null` làm đầu vào là **không đủ**. `null` có thể bị hiểu theo hai cách xung đột:

- Client **không gửi** `displayName`: giữ nguyên dữ liệu cũ.
- Client **gửi** `displayName: null`: xóa tên hiển thị, ghi SQL `NULL`.

Nếu client gửi giá trị `"Linh"`, hệ thống cần ghi giá trị đó. Hãy mô tả ba trạng thái bằng một kiểu độc lập:

```java
import java.util.Objects;

public record PatchField<T>(boolean supplied, T value) {
    public PatchField {
        if (!supplied && value != null) {
            throw new IllegalArgumentException(
                    "Không được có value khi trường không được gửi");
        }
    }

    public static <T> PatchField<T> absent() {
        return new PatchField<>(false, null); // Giữ nguyên.
    }

    public static <T> PatchField<T> clear() {
        return new PatchField<>(true, null);  // Ghi NULL.
    }

    public static <T> PatchField<T> set(T value) {
        return new PatchField<>(true, Objects.requireNonNull(value));
    }
}
```

Ví dụ dùng `PatchField<String>` khi cập nhật một trường:

```java
public static void applyDisplayName(
        DataSource ds, long id, PatchField<String> patch)
        throws SQLException {

    if (!patch.supplied()) {
        return; // Không có thay đổi cho cột này.
    }

    String sql = "UPDATE customer_profiles " +
                 "SET display_name = ? WHERE id = ?";
    try (Connection con = ds.getConnection();
         PreparedStatement ps = con.prepareStatement(sql)) {
        if (patch.value() == null) {
            ps.setNull(1, Types.VARCHAR);
        } else {
            ps.setString(1, patch.value());
        }
        ps.setLong(2, id);
        ps.executeUpdate();
    }
}
```

Đoạn này là ví dụ **cách áp dụng từng cột**: đặt nó trong lớp Java phù hợp, bổ sung các `import` JDBC và `DataSource` như mục 6. Một API sản xuất nên trả trạng thái rõ ràng khi không tìm thấy id, đặc biệt nếu caller cần phân biệt `PATCH` không thay đổi và `UPDATE` tác động 0 hàng.

Khi cập nhật nhiều trường một lúc, chỉ đưa các cột có `supplied() == true` vào `SET`; tên cột phải lấy từ **danh sách cho phép cố định trong code**, còn **giá trị** luôn gửi qua `?`. Không bao giờ ghép tên cột tùy ý từ đầu vào client vào SQL. Dùng transaction nếu thao tác còn gồm các lệnh ghi quan hệ khác.

`Optional<T>` không phải phương tiện tự nhiên để biểu diễn ba trạng thái này: `Optional.empty()` chỉ biểu đạt **một** trạng thái vắng giá trị. Không dùng `Optional<Optional<T>>` như giải pháp mặc định; một kiểu `PatchField` hoặc kiểu biến thể được đặt tên giúp ý nghĩa rõ hơn.

## 8. Truy vấn và bộ lọc với `NULL` trong SQL

`NULL` ảnh hưởng cả việc đọc lẫn cách viết điều kiện `WHERE`.

```sql
-- Đúng: tìm hàng chưa khai báo tuổi.
SELECT id, full_name FROM customer_profiles
WHERE age IS NULL;

-- Đúng: tìm hàng đã khai báo tuổi.
SELECT id, full_name FROM customer_profiles
WHERE age IS NOT NULL;

-- Đúng: tìm người đã đồng ý; FALSE và NULL đều không được chọn.
SELECT id, full_name FROM customer_profiles
WHERE marketing_consent = TRUE;

-- Sai mục đích: = NULL không tương đương IS NULL.
SELECT id, full_name FROM customer_profiles
WHERE age = NULL;
```

SQL vận hành theo logic **TRUE/FALSE/UNKNOWN**; so sánh `x = NULL` cho kết quả `UNKNOWN`, và `WHERE` chỉ giữ các hàng có điều kiện là `TRUE`.

Điều này quan trọng khi xây dựng tìm kiếm tùy chọn:

| Yêu cầu lọc | SQL phù hợp |
| --- | --- |
| Không lọc theo tên hiển thị | Không thêm điều kiện cho `display_name` |
| Chỉ lấy tên hiển thị chưa có | `display_name IS NULL` |
| Chỉ lấy tên hiển thị bằng `"Linh"` | `display_name = ?` và `ps.setString(index, "Linh")` |

Đừng dùng một giá trị `null` duy nhất cho cả “bỏ qua điều kiện” và “tìm các hàng có `NULL`”. Tầng API nên cung cấp lựa chọn lọc có tên rõ ràng, ví dụ `ANY`, `IS_NULL`, `EQUALS`.

`COALESCE(display_name, full_name)` có thể phù hợp khi yêu cầu **hiển thị** tên thay thế, nhưng `COALESCE(age, 0)` dùng tùy tiện sẽ làm mất phân biệt tuổi chưa biết và tuổi bằng 0. Các biểu thức áp hàm lên cột trong `WHERE` còn có thể ảnh hưởng khả năng tận dụng index tùy DB và cấu trúc index. Chỉ dùng mặc định khi đã có quyết định nghiệp vụ rõ ràng.

## 9. `LEFT JOIN`: hàng bên phải không tồn tại hay cột của nó `NULL`?

Một truy vấn `LEFT JOIN` đưa một nguồn `NULL` khác vào kết quả: khi không có hàng khớp bên phải, **tất cả các cột phía bên phải** được trả dưới dạng SQL `NULL`, kể cả cột vốn được khai báo `NOT NULL` trong bảng gốc.

Giả sử bảng `orders` tham chiếu tùy chọn đến `customer_profiles`:

```sql
SELECT o.id AS order_id,
       p.id AS profile_id,
       p.display_name AS profile_display_name
FROM orders o
LEFT JOIN customer_profiles p ON p.id = o.profile_id
WHERE o.id = ?;
```

Đọc `profile_id` để biết **bản ghi bên phải có tồn tại không**, thay vì suy từ `display_name`:

```java
long rawProfileId = rs.getLong("profile_id");
Long profileId = rs.wasNull() ? null : rawProfileId;

if (profileId == null) {
    // Không có hàng customer_profiles khớp.
} else {
    String displayName = rs.getString("profile_display_name");
    // Hồ sơ có tồn tại; displayName vẫn có thể null hợp lệ.
}
```

Không tạo đối tượng `CustomerProfile` giả với id 0 hoặc `fullName == null` chỉ vì `LEFT JOIN` không khớp. Nếu ánh xạ quan hệ một-nhiều, có thể nhận **nhiều hàng SQL cho một đối tượng cha**; phải nhóm theo khóa cha/con và chỉ tạo đối tượng con khi khóa con không `NULL`. Đây là trách nhiệm của mapper cho quan hệ, khác với mapper một hàng trong mục 4.

## 10. Ranh giới chuyển đổi: giữ nguyên dữ liệu hay tạo giá trị hiển thị?

Hãy tách ba tầng trách nhiệm:

| Tầng | Quy tắc |
| --- | --- |
| **DB/JDBC mapper** | Giữ đúng giá trị thực tế và `NULL` theo schema, trừ chuyển đổi đã được định nghĩa rõ |
| **Nghiệp vụ** | Kiểm tra giá trị bắt buộc, quyết định có cho phép thiếu hay không, tính toán dựa trên thông tin đã biết |
| **Hiển thị/API** | Có thể thay `NULL` bằng nhãn như “Chưa cung cấp” nếu hợp đồng trả dữ liệu cho phép |

Ví dụ, ưu tiên:

```java
String display = profile.optionalDisplayName()
        .filter(name -> !name.isBlank())
        .orElse(profile.fullName());
```

Quy tắc trên có ý nghĩa **chỉ ở ngữ cảnh hiển thị**; nó cố ý coi chuỗi trắng/rỗng như không có tên hiển thị. Không áp dụng ngầm khi ghi hoặc khi cần so sánh dữ liệu gốc.

Đối với `marketingConsent`, `Boolean.TRUE.equals(profile.marketingConsent())` là cách kiểm tra an toàn để thực hiện hành động **chỉ khi đã có đồng ý rõ ràng**. Nhưng phép kiểm tra đó trả `false` cả khi người dùng từ chối và khi chưa trả lời; **không** dùng kết quả boolean này để ghi đè trạng thái lưu trữ hay tạo báo cáo thống kê ba trạng thái.

Ngoài ra, `Map.of(...)` của Java **không chấp nhận giá trị `null`**. Nếu chuyển record sang `Map` hoặc JSON, hãy lựa chọn rõ ràng: giữ trường với giá trị null, bỏ trường hoàn toàn hay dùng schema riêng; sự khác biệt rất quan trọng cho các API cập nhật một phần.

## 11. Những trường hợp biên dễ bị bỏ qua

| Trường hợp | Lỗi thường gặp | Cách xử lý |
| --- | --- | --- |
| `SUM(amount)` hoặc `AVG(score)` không có hàng phù hợp | Nghĩ kết quả luôn bằng 0 | Các hàm tổng hợp này có thể trả `NULL`; đọc bằng kiểu tham chiếu và quyết định mặc định theo nghiệp vụ |
| `COUNT(*)` trên tập rỗng | Xử lý như `SUM` | `COUNT` trả 0, không phải SQL `NULL` trong trường hợp thông thường |
| `getInt` rồi `getString` rồi `wasNull` | Đánh giá trạng thái của cột sai | Gọi `wasNull()` ngay sau getter cần xét |
| Projection bỏ cột mà mapper đòi hỏi | Hiểu lỗi `SQLException` thành `null` | Khai báo rõ contract của mapper theo danh sách cột/alias |
| `LEFT JOIN` không có hàng con | Tạo đối tượng con rỗng giả | Kiểm tra khóa chính phía con trước khi khởi tạo |
| DTO dùng primitive cho cột nullable | `NULL` biến thành `0`/`false` | Dùng wrapper hoặc áp quy tắc chuyển đổi có tài liệu hóa |
| Không gửi thuộc tính khi `PATCH` | Bị hiểu là chủ động xóa | Kiểu cập nhật có trạng thái absent/clear/set |
| Ghi `setObject(index, null)` | Driver không suy ra kiểu hoặc không tương thích | Dùng `setNull(index, Types.X)` |
| Giấu `SQLException` trong mapper | Khó xác định cột/kiểu gây lỗi | Giữ thông tin nguyên nhân, bổ sung ngữ cảnh an toàn |
| Mỗi lớp tự thay null bằng giá trị mặc định riêng | API và báo cáo không còn cùng cách hiểu | Quy định hợp đồng chung cho trường, chuyển đổi tại ranh giới rõ ràng |

Khi ghi hàng loạt với `PreparedStatement.addBatch()`, vẫn phải gán **mọi tham số của từng hàng** bằng `setXxx` hoặc `setNull` trước mỗi lần `addBatch()`; không để giá trị từ vòng lặp trước tồn tại ngoài ý muốn. Dùng transaction cho batch khi yêu cầu tất cả thành công hoặc rollback cùng nhau, và xử lý `BatchUpdateException` theo chính sách ứng dụng.

## 12. Kiểm thử ánh xạ nullable

Nên có bài test tích hợp trên DB và driver tương ứng với môi trường thật, vì `getObject(..., SomeType.class)`, kiểu boolean/date và cách xử lý chuỗi rỗng có thể khác nhau.

### Ma trận ca kiểm thử tối thiểu

| Dữ liệu trong DB | Kết quả mapper mong muốn |
| --- | --- |
| `age = NULL` | `profile.age() == null` |
| `age = 0` | `profile.age().equals(0)` |
| `marketing_consent = NULL` | `profile.marketingConsent() == null` |
| `marketing_consent = FALSE` | `Boolean.FALSE.equals(profile.marketingConsent())` |
| `display_name = NULL` | `profile.displayName() == null` |
| `display_name = ''` | Chuỗi rỗng nếu DB hỗ trợ phân biệt; nếu không, ghi rõ giới hạn |
| `birth_date = NULL` | `profile.birthDate() == null` |
| Không tồn tại `id` | `findById(id)` trả `Optional.empty()` |
| `LEFT JOIN` không khớp hàng bên phải | Không tạo đối tượng con giả |
| Tham số ghi `null` qua `setNull` | Đọc lại nhận `null`, không thành 0/false |
| `PATCH` absent / clear / set | Lần lượt giữ nguyên / ghi `NULL` / ghi giá trị mới |

Các phép thử còn nên kiểm tra: vi phạm `NOT NULL` có `SQLException` và không để lại dữ liệu nửa vời; nhãn cột trong câu SQL đúng với mapper; hai lần cập nhật liên tiếp `false` và `NULL` vẫn phân biệt khi đọc lại; kết nối, statement và result set luôn được đóng.

Một phép kiểm nhỏ ở tầng Java để thấy sự khác nhau:

```java
Integer unknownAge = null;
Integer newbornAge = 0;

assert unknownAge == null;
assert newbornAge != null && newbornAge == 0;

Boolean unknownConsent = null;
Boolean declined = false;

assert unknownConsent == null;
assert Boolean.FALSE.equals(declined);
assert !Boolean.TRUE.equals(unknownConsent);
```

`assert` chỉ chạy khi Java được bật assertion (ví dụ `-ea`). Trong bộ kiểm thử thực tế, nên dùng assertion của framework kiểm thử và kiểm tra kết quả từ **JDBC/DB thật** thay vì chỉ kiểm tra những biến Java tự gán.

## 13. Bài tập thực hành

Cho bảng `customer_profiles` ở mục 2 và ba yêu cầu sau:

1. Viết một hàm trả `Optional<CustomerProfile>` theo id; thử với hồ sơ có `age = NULL`, `age = 0` và id không tồn tại. Giải thích vì sao ba kết quả phải khác nhau.
2. Viết chức năng cập nhật `marketing_consent` để phân biệt **không cập nhật**, **xóa câu trả lời** và **đặt `false`**. Chọn kiểu dữ liệu đầu vào và cách bind `PreparedStatement` phù hợp.
3. Viết truy vấn lấy danh sách hồ sơ chưa khai báo ngày sinh; sau đó thêm chức năng lấy các hồ sơ có `display_name = 'Linh'` nhưng không làm thay đổi các hàng có `display_name IS NULL`.

Gợi ý hướng giải:

- Bài 1 dùng `rs.next()` để xác định hàng có tồn tại; dùng `getInt` + `wasNull` hoặc `getObject(..., Integer.class)` được driver hỗ trợ để phân biệt SQL `NULL` và `0`.
- Bài 2 dùng kiểu ba trạng thái như `PatchField<Boolean>`, `setNull(..., Types.BOOLEAN)` khi muốn xóa và `setBoolean(..., false)` khi muốn lưu lời từ chối.
- Bài 3 dùng `WHERE birth_date IS NULL` cho yêu cầu đầu và `WHERE display_name = ?` với `setString` cho yêu cầu sau. Cần phân biệt tham số tìm kiếm không cung cấp với ý định lọc theo `NULL`.

## 14. Checklist khi thêm một cột nullable

Trước khi hoàn tất tính năng JDBC, kiểm tra:

1. Có lý do nghiệp vụ rõ ràng để cột cho phép `NULL`, và ý nghĩa `NULL` đã được ghi nhận?
2. Schema dùng `NULL`/`NOT NULL`, `DEFAULT` và ràng buộc đúng?
3. Java DTO/record dùng reference type cho cột nullable và giữ được `0`/`false`/`""`?
4. Mapper dùng `wasNull()` ngay sau getter primitive hoặc getter tham chiếu phù hợp?
5. DAO phân biệt `rs.next() == false` với hàng tồn tại có cột `NULL`?
6. `PreparedStatement` dùng `setNull` đúng loại và giá trị qua bind parameter?
7. `PATCH` phân biệt **không gửi**, **gửi null**, **gửi giá trị**?
8. Truy vấn dùng `IS NULL`/`IS NOT NULL` đúng ý nghĩa và test có trường hợp biên?
9. Nếu có `JOIN`, mapper kiểm tra khóa phía bảng tùy chọn?
10. Đã xác nhận hành vi driver và DB thật bằng kiểm thử ghi–đọc?

Một mapper JDBC tốt phải **bảo toàn ý nghĩa dữ liệu**. Nó không nên tự biến `NULL` thành `0`, `false` hay chuỗi rỗng vì “cho tiện”; những chuyển đổi đó chỉ đúng khi có quy tắc nghiệp vụ cụ thể. Khi schema, Java record, `ResultSet`, `PreparedStatement` và hợp đồng API đồng nhất về nullability, ứng dụng sẽ tránh được nhiều lỗi âm thầm trong CRUD, truy vấn, báo cáo và cập nhật một phần.
