# NULL SQL, Java null và quy tắc của JDBC driver

## 1. Hai thế giới cùng dùng chữ “null”, nhưng không hoàn toàn giống nhau

Trong Java 17+, `null` là một giá trị tham chiếu đặc biệt, biểu thị một reference không trỏ đến object. Một biến kiểu `Integer` hoặc `String` có thể chứa `null`, nhưng biến nguyên thủy kiểu `int` hoặc `boolean` **không** thể. Trong SQL, **`NULL`** là một marker chỉ **giá trị dữ liệu không có/không biết** ở một cột hoặc biểu thức; nó không phải số 0, không phải chuỗi rỗng và không phải một chuỗi văn bản `"NULL"`.

Khi ứng dụng Java đọc/ghi dữ liệu qua JDBC, driver phải chuyển giữa hai hệ thống kiểu dữ liệu ấy. Đây là lý do một đoạn code trông rất đơn giản có thể gây lỗi:

~~~java
int age = rows.getInt("age");
~~~

Nếu cột `age` là SQL `NULL`, Javadoc của `ResultSet.getInt` quy định trả **`0`**. Nếu `age` thật sự bằng **`0`**, method cũng trả **`0`**. Không thể phân biệt hai trường hợp bằng biến `age`; cần gọi **`rows.wasNull()` ngay sau getter**.

Trường hợp khác:

~~~java
String nickname = rows.getString("nickname");
~~~

Nếu cột là SQL `NULL`, `getString` trả Java `null`, nên có thể kiểm tra `nickname == null`. Nếu là chuỗi rỗng, về nguyên tắc giá trị Java sẽ là `""` khi DBMS/driver có phân biệt empty và NULL. Một số DBMS có quy tắc riêng, ví dụ Oracle Database với zero-length character strings; sẽ phân tích ở phần sau.

**Ba lớp cần phân biệt:**

1. **SQL / database:** cột nullable, kiểu SQL, ràng buộc `NOT NULL`, mặc định (default), toán tử ba giá trị, collation và các khác biệt vendor.
2. **JDBC driver:** `PreparedStatement.setNull`, `setObject`, `ResultSet.getInt`, `getString`, `getObject`, `wasNull`, chuyển kiểu SQL–Java và mức hỗ trợ API.
3. **Java / domain:** `null` reference, primitive defaults, boxed types (`Integer`/`Boolean`), `Optional`, DTO/record, validation và quy tắc nghiệp vụ.

**Nguyên tắc:** không tự biến SQL `NULL` thành `0`/`false`/`""` chỉ để tránh null trong Java nếu **sự khác biệt có ý nghĩa**. Và không truyền Java `null` không có kiểu SQL một cách mù quáng khi driver cần biết loại tham số.

Bài dùng các API còn được hỗ trợ trong **Java 17+ và Java SE 25**. Ví dụ có một chương trình độc lập biên dịch/chạy được không cần database; cần phân biệt rõ ví dụ này kiểm thử **application/JDBC API contract** chứ không chứng minh mọi driver và DBMS có cùng hành vi vendor-specific.

## 2. Bảng đối chiếu SQL NULL với Java null và các giá trị không null

| Giá trị ở database | Đọc vào Java | Vì sao cần cẩn thận? |
| --- | --- | --- |
| SQL `NULL` từ cột `VARCHAR` | `getString(...)` → `null` | Khác `""` và `"null"` |
| SQL `NULL` từ cột `INTEGER` | `getInt(...)` → `0`, `wasNull()` → `true` | `0` có thể là giá trị thật |
| SQL `0` từ `INTEGER` | `getInt(...)` → `0`, `wasNull()` → `false` | `wasNull` phân biệt chính xác |
| SQL `NULL` từ `BOOLEAN`/`BIT` | `getBoolean(...)` → `false`, `wasNull()` → `true` | Không biến “chưa biết” thành `false` |
| SQL `FALSE` từ boolean column | `getBoolean(...)` → `false`, `wasNull()` → `false` | Cùng primitive result nhưng khác ngữ nghĩa |
| SQL `NULL` qua `getObject(...)` | Java `null` | Thường tiện hơn khi muốn giữ nullability |
| SQL `NULL` qua `getObject(..., Integer.class)` | Java `null` nếu driver hỗ trợ conversion | Typed getter có thể không được hỗ trợ cho một số conversions |
| SQL `''` (chuỗi rỗng) | Thường `""` với DBMS phân biệt được empty/NULL | Oracle Database có semantics riêng |
| Không có row trong `ResultSet` | `rs.next() == false` | **Không phải** cùng ý nghĩa với một row có cột `NULL` |
| Không truyền parameter JDBC `?` | Thường lỗi unset parameter khi execute | **Không** tự đồng nghĩa SQL NULL hoặc DEFAULT |
| Không có một field trong request/JSON | Tùy application payload contract | **Không** tự coi như yêu cầu set SQL NULL |

**Không dùng tên field để đoán nullability.** Một cột `age` tên như dữ liệu số nhưng có thể nullable; một cột tên `status` có thể bắt buộc `NOT NULL`. Quy tắc thật là schema + business contract + giá trị thực tế mà driver đọc.

### `null` là reference; `NULL` là SQL marker

~~~java
Integer nullableAge = null; // Hợp lệ.
String displayName = null;  // Hợp lệ.

// int age = null;          // Không biên dịch: primitive int không nhận null.
// boolean ready = null;    // Không biên dịch.
int defaultCount = 0;
boolean defaultReady = false;
~~~

Đây là đoạn minh họa trong method. Java `int 0`/`boolean false` là những giá trị thật, không phải SQL null. JDBC phải dùng quy tắc riêng để chuyển SQL NULL về primitive getter và cung cấp `wasNull`.

Cũng không nên dùng câu `String.valueOf(nullableAge)` như cách giữ nguyên missing value: khi đầu vào là `null`, lời gọi có thể cho chuỗi chữ **`"null"`** chứ không phải database SQL NULL. Nên map nullability trước khi format cho UI hay bind SQL.

## 3. `ResultSet.wasNull()`: phải kiểm tra ngay sau getter liên quan

Method chuẩn của JDBC:

~~~java
boolean wasNull() throws SQLException;
~~~

`wasNull()` cho biết **lần đọc cột gần nhất** bằng một `ResultSet` getter có lấy SQL NULL hay không. Nó **không** cho biết liệu **bất kỳ cột nào trong row** đang null, và không phải cờ tồn tại cho cả ResultSet.

Ví dụ đọc cột số nullable:

~~~java
int value = rs.getInt("age");
Integer age = rs.wasNull() ? null : value;
~~~

Đây là đoạn trong method sau khi `rs.next()` đã trả `true`. Nếu DB chứa age NULL, biến `age` cuối cùng là Java null; nếu DB chứa age 0, `age` là Integer 0.

**Sai do kiểm tra chậm:**

~~~java
int age = rs.getInt("age");
String nickname = rs.getString("nickname");
boolean ageWasNull = rs.wasNull(); // SAI: mô tả nickname, không phải age.
~~~

`getString("nickname")` đã thay đổi thông tin của getter gần nhất. Kết quả `ageWasNull` có thể đúng/sai tùy giá trị nickname và hoàn toàn không mô tả cột age nữa.

**Đúng:**

~~~java
int ageValue = rs.getInt("age");
boolean ageWasNull = rs.wasNull(); // Kiểm tra ngay.

String nickname = rs.getString("nickname");
boolean nicknameWasNull = rs.wasNull(); // Kiểm tra riêng.
~~~

Nếu `getString` trả một object, việc kiểm tra `nickname == null` thường đã đủ để biết SQL NULL. Tuy nhiên `wasNull` vẫn hữu ích khi xây mapper thống nhất cho nhiều kiểu getter. Ngược lại, với `getInt`/`getLong`/`getDouble`/`getBoolean`, **phải lưu ý default primitive result**.

### Mẫu mapping với boxed types

~~~java
record Person(long id, Integer age, Boolean verified, String nickname) {}

static Person mapPerson(ResultSet rs) throws SQLException {
    long id = rs.getLong("id");
    if (rs.wasNull()) {
        throw new SQLException("id là NULL nhưng domain yêu cầu có ID");
    }

    int ageRaw = rs.getInt("age");
    Integer age = rs.wasNull() ? null : ageRaw;

    boolean verifiedRaw = rs.getBoolean("verified");
    Boolean verified = rs.wasNull() ? null : verifiedRaw;

    String nickname = rs.getString("nickname");
    return new Person(id, age, verified, nickname);
}
~~~

Đây là **đoạn dùng trong một class/method**, yêu cầu import `java.sql.ResultSet` và `java.sql.SQLException`. `Person` là record Java 17 hợp lệ. Vì `age`/`verified` nullable, chọn **`Integer` và `Boolean`** thay vì primitives để giữ ba trạng thái: absent, zero/false và nonzero/true. `id` bắt buộc non-null theo giả định của domain; nếu schema cho phép NULL, điều đó phải được giải quyết thay vì lấy `0` làm ID giả.

**Lưu ý:** không gọi `rs.next()` ở mapper nếu caller đã điều khiển cursor, trừ khi method đó được thiết kế rõ để điều khiển cursor. Map một row hiện tại **khác** với việc xác nhận row tồn tại. Query không trả row nào là một trạng thái riêng, thường cần return `Optional.empty()` hoặc một kết quả nghiệp vụ không tìm thấy.

### Khi nào dùng `getObject`?

~~~java
Object raw = rs.getObject("age"); // SQL NULL -> Java null.
Integer age = rs.getObject("age", Integer.class);
~~~

Đây là đoạn trong method. Với `getObject(String)`, Java type của giá trị không null tùy **mappings từ SQL type** của JDBC driver (ví dụ SQL DECIMAL thường là `BigDecimal`, không mặc định Integer). Với `getObject(String, Integer.class)`, ta **yêu cầu conversion cụ thể**; nếu driver/type không hỗ trợ, có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException`. Không ép kiểu `(Integer) rs.getObject(...)` nếu không chắc mapping thực tế.

Khi driver hỗ trợ typed `getObject` cho SQL INTEGER, đây là lựa chọn gọn để giữ nullable: `Integer age = rs.getObject("age", Integer.class)`. Hãy kiểm thử với driver và DB thực dùng. Đặc biệt các kiểu `UUID`, JSON, UDT, ARRAY, temporal types hoặc vendor-specific types cần kiểm tra tài liệu driver, không tự suy diễn từ SQL tên cột.

## 4. Ghi SQL NULL bằng `PreparedStatement.setNull`

Cách **rõ ràng và portable** để bind SQL NULL với kiểu biết trước:

~~~java
String sql = "INSERT INTO person (id, age, nickname) VALUES (?, ?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, id);
    ps.setNull(2, Types.INTEGER);
    ps.setNull(3, Types.VARCHAR);
    ps.executeUpdate();
}
~~~

Đây là đoạn trong method có `connection`, `id` và bảng `person` hợp lệ; cần import `java.sql.PreparedStatement` và `java.sql.Types`, xử lý `SQLException`. Parameter JDBC **bắt đầu từ 1**. `setNull(2, Types.INTEGER)` chỉ **bind giá trị NULL** cho dấu `?` thứ hai; nó không tự thực thi câu INSERT.

Javadoc Java SE 25 nói rõ `setNull(int parameterIndex, int sqlType)` yêu cầu mã kiểu từ `java.sql.Types`. Ví dụ:

| Kiểu cột/parameter SQL | `setNull` thông thường |
| --- | --- |
| `INTEGER` | `ps.setNull(i, Types.INTEGER)` |
| `BIGINT` | `ps.setNull(i, Types.BIGINT)` |
| `DECIMAL`/`NUMERIC` | `ps.setNull(i, Types.DECIMAL)` |
| `VARCHAR` | `ps.setNull(i, Types.VARCHAR)` |
| `NVARCHAR` | `ps.setNull(i, Types.NVARCHAR)` khi driver hỗ trợ |
| `BOOLEAN` | `ps.setNull(i, Types.BOOLEAN)`, hoặc SQL type tương ứng driver |
| `DATE` | `ps.setNull(i, Types.DATE)` |
| `TIMESTAMP` | `ps.setNull(i, Types.TIMESTAMP)` |

Không chọn bừa `Types.VARCHAR` cho một cột số chỉ vì mọi giá trị null “trông như nhau”. Database/driver có thể cần biết parameter type để chọn SQL conversion, operator overload, stored procedure signature hoặc execution plan.

### `setObject(index, null, sqlType)` là lựa chọn có kiểu

~~~java
ps.setNull(1, Types.INTEGER);
ps.setObject(2, null, Types.VARCHAR);
ps.setObject(3, nullableScore, Types.INTEGER);
~~~

Đây là đoạn minh họa, phải có ít nhất ba parameter và các biến đã khai báo. `setObject(int,Object,int targetSqlType)` truyền một giá trị Java (kể cả null) cùng target SQL type. Nếu `nullableScore` là một boxed Integer có thể null, API này giúp caller luôn xác định SQL type rõ ràng. Khi dùng `setObject(i, value, SQLType)`, lưu ý overload với `SQLType` có default implementation có thể ném `SQLFeatureNotSupportedException` nếu driver không override; `setObject(..., int Types-code)` thường là lựa chọn dễ tương thích.

### Tại sao không dùng `setObject(index, null)` không kiểu?

~~~java
ps.setObject(2, null); // Không có target SQL type.
~~~

Javadoc ghi nhận **không phải database nào cũng cho phép truyền NULL không có kiểu tới backend**. Với tính portable, ưu tiên `setNull(index, Types.X)` hoặc `setObject(index, null, Types.X)`. Một driver có thể suy ra kiểu từ SQL metadata, driver khác có thể thất bại hoặc tạo phép conversion khác. Không dựa vào việc một vendor chạy được để tuyên bố JDBC bảo đảm mọi nơi.

`PreparedStatement.setString(i, null)` có thể làm việc với một số drivers, nhưng nếu mục đích là **SQL NULL có kiểu VARCHAR**, `setNull(i, Types.VARCHAR)` diễn đạt ý định rõ hơn và tránh những tình huống vendor-dependent. Không thay tất cả dữ liệu null bằng chuỗi `"NULL"`; chuỗi đó là một giá trị **không null**.

### Khi nào cần `setNull(index, type, typeName)`?

JDBC có overload:

~~~java
ps.setNull(index, sqlType, sqlTypeName);
~~~

Với **user-defined SQL types** và `REF`, Javadoc chỉ dẫn truyền cả SQL type code và **fully qualified SQL type name** khi cần tính portable. Những type như `STRUCT`, distinct types, named arrays, `JAVA_OBJECT` có thể có yêu cầu driver-specific. `typeName` không phải Java class name tùy ý; đó là tên type trong SQL database. Nếu dùng JSON/JSONB, ENUM, UUID hoặc UDT theo vendor, hãy kiểm tra **driver và database type mapping** thay vì chọn `Types.OTHER` như một câu thần chú cho mọi DBMS.

### Optional và null ở ranh giới binding

`Optional<Integer>` là một kiểu Java giúp biểu diễn có/không có giá trị ở một số API boundaries; nó **không phải một SQL type tiêu chuẩn** để truyền nguyên object qua `setObject`.

~~~java
Optional<Integer> age = Optional.empty();
if (age.isPresent()) {
    ps.setInt(2, age.get());
} else {
    ps.setNull(2, Types.INTEGER);
}
~~~

Đây là đoạn minh họa bên trong method với `ps`, cần import `java.util.Optional` và `java.sql.Types`. Trong application thật có thể dùng `Integer`/`Optional` theo convention của domain, nhưng phải **unwrap** trước khi bind. Không coi `Optional.empty()` và giá trị request field bị thiếu là cùng ý nghĩa trong mọi API patch.

## 5. SQL NULL tuân theo logic ba giá trị

SQL có **TRUE**, **FALSE**, và **UNKNOWN** khi đánh giá nhiều biểu thức logic liên quan NULL. Quy tắc quan trọng:

~~~sql
-- Không chọn các row có nickname NULL:
SELECT id FROM person WHERE nickname = NULL;

-- Đúng để tìm NULL:
SELECT id FROM person WHERE nickname IS NULL;

-- Đúng để tìm không NULL:
SELECT id FROM person WHERE nickname IS NOT NULL;
~~~

`nickname = NULL` không trả TRUE ngay cả khi nickname là SQL NULL: phép so sánh thông thường với NULL cho **UNKNOWN**. Mệnh đề `WHERE` chỉ giữ các row có điều kiện **TRUE**; UNKNOWN bị loại giống FALSE về mặt filtering. Tương tự, `NULL = NULL` cho UNKNOWN, không phải TRUE.

| Biểu thức SQL | Kết quả logic ba giá trị |
| --- | --- |
| `NULL = NULL` | UNKNOWN |
| `7 = NULL` | UNKNOWN |
| `NULL <> 7` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |
| `FALSE AND UNKNOWN` | FALSE |
| `TRUE AND UNKNOWN` | UNKNOWN |
| `TRUE OR UNKNOWN` | TRUE |
| `FALSE OR UNKNOWN` | UNKNOWN |
| `NOT UNKNOWN` | UNKNOWN |

Các biểu thức trong bảng là mô tả logic SQL chuẩn, không phải những câu SELECT cần chạy trực tiếp trên mọi dialect. Một số DBMS có cú pháp/literal Boolean khác nhau.

### Binding null vào `= ?` không tự biến thành `IS NULL`

~~~java
String sql = "SELECT id FROM person WHERE nickname = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setNull(1, Types.VARCHAR);
    try (ResultSet rs = ps.executeQuery()) {
        // Không có nghĩa nó sẽ tìm những row nickname IS NULL.
    }
}
~~~

Đây là snippet cần connection, schema và imports. Nếu nickname là SQL NULL, điều kiện `nickname = NULL` vẫn UNKNOWN. **Driver bind NULL không có nhiệm vụ rewrite SQL semantics** theo ý định nghiệp vụ.

Nếu business filter là “nickname không có giá trị”:

~~~java
String sql = "SELECT id FROM person WHERE nickname IS NULL";
~~~

Nếu input có thể null hoặc một giá trị cụ thể, hãy xây predicate rõ ràng, không nối giá trị user vào SQL:

~~~java
String sql = nickname == null
        ? "SELECT id FROM person WHERE nickname IS NULL"
        : "SELECT id FROM person WHERE nickname = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    if (nickname != null) ps.setString(1, nickname);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc rows theo filter đã chọn.
    }
}
~~~

Đây là snippet trong method, `nickname` là tham số đã validate, chọn một trong **hai câu SQL cố định**, không ghép nội dung người dùng vào SQL text. Với các điều kiện tùy chọn phức tạp, có thể dùng query builder/framework phù hợp; vẫn cần test null predicates và query plan.

### `IS DISTINCT FROM` và null-safe equality

SQL standard có phép so sánh null-aware như `IS DISTINCT FROM` và `IS NOT DISTINCT FROM`, nhưng support/cú pháp theo **DBMS và version** phải được kiểm tra. Không thay mọi `=` bằng một toán tử mà driver/dialect chưa hỗ trợ. Nếu muốn tương đương “hai giá trị đều NULL cũng coi là match”, hãy xác định domain semantics, viết query theo database cụ thể và có integration tests.

### `NOT IN` chứa NULL là bẫy

~~~sql
-- Nếu subquery có NULL, NOT IN có thể không trả những row như bạn nghĩ:
SELECT id FROM person
WHERE id NOT IN (SELECT owner_id FROM blocked_owner);

-- Một hướng thường rõ hơn cho loại trừ theo quan hệ:
SELECT p.id FROM person p
WHERE NOT EXISTS (
    SELECT 1 FROM blocked_owner b WHERE b.owner_id = p.id
);
~~~

Đây là ví dụ SQL cần bảng thực; `NOT EXISTS` có semantics khác rõ hơn cho “không có record match” khi subquery chứa NULL. Cần bảo đảm business meaning, indexes và dữ liệu owner_id không có lỗi. Với null values trong chính cột so sánh, cũng phải xác định policy cụ thể.

## 6. `COALESCE`, `NULLIF`, DEFAULT và dữ liệu rỗng

### `COALESCE` thay thế NULL trong **kết quả biểu thức**

~~~sql
SELECT id,
       COALESCE(nickname, '(chưa có tên)') AS display_name
FROM person;
~~~

`COALESCE` trả expression không NULL đầu tiên trong danh sách; thường dùng để **hiển thị** hoặc báo cáo. Nó **không sửa trực tiếp dữ liệu lưu trong cột** nếu không nằm trong một câu UPDATE có chủ đích.

**Đừng dùng `COALESCE(age, 0)` rồi quên mất age có thể NULL.** Có thể phù hợp khi domain xác định “không nhập tuổi xem như 0”, nhưng trong nhiều trường hợp 0 tuổi thật và chưa biết tuổi là khác nhau. Nếu cần cả giá trị hiển thị và nullability, giữ cột gốc hoặc thêm một field boolean/metadata riêng.

### `NULLIF` có thể tạo NULL từ hai giá trị bằng nhau

~~~sql
SELECT NULLIF(score, 0) AS score_or_null
FROM result;
~~~

Khi hai arguments bằng nhau, `NULLIF` trả SQL NULL; nếu không thì trả argument đầu. Quy tắc này có ích trong một số phép biến đổi dữ liệu nhưng **có thể làm mất phân biệt** giữa điểm 0 thật và giá trị chưa có điểm. Không dùng chỉ vì muốn tránh code kiểm tra null trong Java.

### Cột có DEFAULT khác với explicit NULL

~~~sql
CREATE TABLE person (
    id BIGINT PRIMARY KEY,
    active BOOLEAN DEFAULT TRUE,
    nickname VARCHAR(100) NULL
);
~~~

Đây là DDL minh họa theo một SQL dialect có `BOOLEAN`; cấu trúc/boolean syntax có thể khác giữa DBMS.

- Nếu câu INSERT **không đưa giá trị cho `active`**, database thường dùng giá trị DEFAULT theo schema.
- Nếu INSERT truyền **SQL NULL tường minh** cho một cột nullable, thường nó sẽ lưu NULL, **không tự đổi thành DEFAULT**, trừ khi có rule/trigger/vendor behavior được cấu hình.
- Nếu cột `NOT NULL` mà caller bind `NULL`, DB có thể từ chối với constraint error, dù cột có DEFAULT, theo DBMS/config.
- JDBC **không tự coi dấu `?` chưa bind là “hãy dùng DEFAULT”**. Nếu cần DEFAULT, viết SQL sử dụng omission hoặc keyword `DEFAULT` theo dialect.

Điều này quan trọng với API PATCH:

| Request trạng thái field | Ý nghĩa ứng dụng có thể muốn |
| --- | --- |
| Field không xuất hiện | Không thay đổi cột hiện tại |
| Field có giá trị JSON `null` | Xóa giá trị, ghi SQL NULL nếu schema cho phép |
| Field có `""` | Ghi chuỗi rỗng, nếu DB giữ phân biệt được |
| Field có `0` | Ghi giá trị số 0 |
| Field có `false` | Ghi Boolean false |

**JSON null** trong payload và **SQL NULL** không tự đồng nghĩa nếu dữ liệu được lưu dưới kiểu JSON/JSONB: JSON literal `null` có thể là một giá trị JSON bên trong một cột **không SQL NULL**. Chuyển đổi này thuộc application/driver/DB semantics. Đừng lập cập nhật kiểu “mọi field absent hoặc JSON null đều gọi `setNull`” nếu PATCH contract cần phân biệt no-change và clear-value.

### Chuỗi rỗng có phải SQL NULL không?

Không có quy tắc chung cho mọi DBMS:

- PostgreSQL, SQL Server và nhiều DBMS có khả năng phân biệt chuỗi rỗng `''` với SQL NULL ở các character types phù hợp.
- **Oracle Database** trong nhiều character/string SQL types coi zero-length character string như NULL. Đây là **vendor semantic**, không phải hành vi của `java.lang.String` hoặc `ResultSet.getString`.
- MySQL có cấu hình/SQL modes ảnh hưởng conversion, nhưng không nên gộp empty với NULL mặc định chỉ vì một hệ thống legacy từng làm thế.

Nếu chuyển ứng dụng giữa DBMS, test **`""`, SQL NULL, chuỗi toàn dấu cách, trailing spaces, `CHAR` padding và Unicode**. Đừng dùng Java `Objects.toString(value, "")` một cách vô thức vì nó gộp null và empty về một chuỗi rỗng.

## 7. Aggregates, JOIN và NULL cũng ảnh hưởng dữ liệu Java đọc được

### `COUNT(*)` khác `COUNT(column)`

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(age) AS rows_with_age,
       SUM(age) AS sum_age,
       AVG(age) AS average_age
FROM person;
~~~

- `COUNT(*)` đếm tất cả rows phù hợp, bao gồm rows có `age` NULL.
- `COUNT(age)` chỉ đếm các giá trị `age` **không NULL**.
- `SUM(age)` và `AVG(age)` nói chung bỏ qua NULL trong tập giá trị; nếu không có giá trị non-NULL, kết quả có thể là SQL NULL.
- `COUNT` trả một số đếm, thường là 0 khi không có rows trong phạm vi; `getLong` có thể phù hợp cho số lượng lớn.

**Không** tự đọc `AVG(age)` bằng `getDouble` rồi xem `0.0` là trung bình có thật khi toàn cột NULL; phải kiểm tra `wasNull()` hoặc dùng `getObject` nullable. Việc chọn `COALESCE(AVG(age), 0)` là **quyết định báo cáo**, không phải kết quả trung bình mặc định có cùng ý nghĩa với 0 thật.

### `LEFT JOIN`: cột bên phải NULL không nhất thiết là dữ liệu thật NULL

~~~sql
SELECT p.id, d.label, d.id AS detail_id
FROM person p
LEFT JOIN person_detail d ON d.person_id = p.id;
~~~

Nếu không có row khớp bên phải, các cột `d.label`/`d.id` sẽ hiện ra SQL NULL trong result. Nếu có row detail nhưng `d.label` thật sự NULL, chỉ nhìn `label` không thể phân biệt tình huống ấy với **không có detail row**.

Khi khóa `d.id` được định nghĩa `NOT NULL`, kiểm tra `detail_id` null có thể giúp xác nhận có match hay không. Tùy schema, composite keys và join condition, phải chọn cột nhận diện phù hợp; không dùng một cột nullable bất kỳ để kết luận quan hệ không tồn tại.

### `ResultSet.next()` và SQL NULL là hai sự kiện khác nhau

~~~java
try (ResultSet rs = ps.executeQuery()) {
    if (!rs.next()) {
        // Query không trả row nào.
    } else {
        String nickname = rs.getString("nickname");
        // Row có tồn tại; nickname có thể SQL NULL.
    }
}
~~~

Snippet cần `ps` đã được chuẩn bị, imports và exception handling. Không viết code `String name = rs.getString("nickname")` trước `rs.next()`; cursor chưa ở một row hợp lệ. Không diễn giải “không tìm thấy user” thành user có nickname NULL.

## 8. Chương trình Java 17+ hoàn chỉnh: kiểm tra binding và getters

Chương trình sau **không kết nối database**. Nó dùng dynamic proxies để mô phỏng tối thiểu hợp đồng `PreparedStatement`/`ResultSet`, với các giá trị có chủ ý:

- Parameter 1 là SQL INTEGER NULL qua `setNull(1, Types.INTEGER)`.
- Parameter 2 là SQL VARCHAR NULL qua `setObject(2, null, Types.VARCHAR)`.
- Parameter 3 là integer `0` thật.
- ResultSet có `age = NULL`, `score = 0`, `enabled = NULL`, `nickname = ""`.
- Getter `getInt`, `getBoolean`, `getString` và typed `getObject` trả kết quả theo mẫu JDBC chuẩn và cập nhật `wasNull`.

**Đây là bài kiểm thử application code và lời gọi API, không đại diện cho một driver vendor hay database thật.** Trong production, cơ chế chuyển đổi SQL/Java thực tế phải được chứng minh bằng integration test với driver + schema + DBMS cụ thể.

Tạo file duy nhất **`JdbcNullSemanticsDemo.java`**:

~~~java
import java.lang.reflect.Proxy;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Types;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public final class JdbcNullSemanticsDemo {
    static PreparedStatement statement(Map<Integer, Object> bound) {
        return (PreparedStatement) Proxy.newProxyInstance(
                JdbcNullSemanticsDemo.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class},
                (p, m, args) -> switch (m.getName()) {
                    case "setNull" -> {
                        int i = (Integer) args[0];
                        int type = (Integer) args[1];
                        if (i != 1 || type != Types.INTEGER)
                            throw new SQLException("Unexpected typed NULL");
                        bound.put(i, null);
                        yield null;
                    }
                    case "setObject" -> {
                        int i = (Integer) args[0];
                        int type = (Integer) args[2];
                        if (i != 2 || type != Types.VARCHAR)
                            throw new SQLException("Unexpected target type");
                        bound.put(i, args[1]);
                        yield null;
                    }
                    case "setInt" -> {
                        bound.put((Integer) args[0], (Integer) args[1]);
                        yield null;
                    }
                    case "executeUpdate" -> 1;
                    case "close" -> null;
                    default -> throw new SQLFeatureNotSupportedException(m.getName());
                });
    }

    static ResultSet result(Map<String, Object> data) {
        AtomicBoolean advanced = new AtomicBoolean();
        AtomicBoolean lastNull = new AtomicBoolean();
        return (ResultSet) Proxy.newProxyInstance(
                JdbcNullSemanticsDemo.class.getClassLoader(),
                new Class<?>[] {ResultSet.class},
                (p, m, args) -> switch (m.getName()) {
                    case "next" -> !advanced.getAndSet(true);
                    case "getInt" -> {
                        Object value = data.get((String) args[0]);
                        lastNull.set(value == null);
                        yield value == null ? 0 : ((Number) value).intValue();
                    }
                    case "getBoolean" -> {
                        Object value = data.get((String) args[0]);
                        lastNull.set(value == null);
                        yield value != null && (Boolean) value;
                    }
                    case "getString" -> {
                        Object value = data.get((String) args[0]);
                        lastNull.set(value == null);
                        yield (String) value;
                    }
                    case "getObject" -> {
                        Object value = data.get((String) args[0]);
                        lastNull.set(value == null);
                        yield value == null ? null : ((Class<?>) args[1]).cast(value);
                    }
                    case "wasNull" -> lastNull.get();
                    case "close" -> null;
                    default -> throw new SQLFeatureNotSupportedException(m.getName());
                });
    }

    public static void main(String[] args) throws SQLException {
        Map<Integer, Object> bound = new HashMap<>();
        try (PreparedStatement ps = statement(bound)) {
            ps.setNull(1, Types.INTEGER);
            ps.setObject(2, null, Types.VARCHAR);
            ps.setInt(3, 0);
            System.out.println("affected rows (fake): " + ps.executeUpdate());
        }
        System.out.println("bound INTEGER NULL: "
                + (bound.containsKey(1) && bound.get(1) == null));
        System.out.println("bound VARCHAR NULL: "
                + (bound.containsKey(2) && bound.get(2) == null));
        System.out.println("bound integer zero: "
                + Integer.valueOf(0).equals(bound.get(3)));

        Map<String, Object> row = new HashMap<>();
        row.put("age", null);
        row.put("score", 0);
        row.put("enabled", null);
        row.put("nickname", "");

        try (ResultSet rs = result(row)) {
            if (!rs.next()) throw new SQLException("No row");
            int age = rs.getInt("age");
            boolean ageNull = rs.wasNull();
            int score = rs.getInt("score");
            boolean scoreNull = rs.wasNull();
            boolean enabled = rs.getBoolean("enabled");
            boolean enabledNull = rs.wasNull();
            String nickname = rs.getString("nickname");
            boolean nicknameNull = rs.wasNull();
            Integer typedAge = rs.getObject("age", Integer.class);

            System.out.println("NULL getInt result: " + age);
            System.out.println("NULL getInt wasNull: " + ageNull);
            System.out.println("zero getInt result: " + score);
            System.out.println("zero getInt wasNull: " + scoreNull);
            System.out.println("NULL getBoolean result: " + enabled);
            System.out.println("NULL getBoolean wasNull: " + enabledNull);
            System.out.println("empty getString preserved: " + nickname.isEmpty());
            System.out.println("empty getString wasNull: " + nicknameNull);
            System.out.println("typed getObject NULL: " + (typedAge == null));
            System.out.println("typed getObject wasNull: " + rs.wasNull());
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**, không cần dependency:

~~~bash
javac --release 17 JdbcNullSemanticsDemo.java
java JdbcNullSemanticsDemo
~~~

**Stdout chính xác**, được biên dịch và chạy trên **OpenJDK 24.0.2 với `--release 17`**:

~~~text
affected rows (fake): 1
bound INTEGER NULL: true
bound VARCHAR NULL: true
bound integer zero: true
NULL getInt result: 0
NULL getInt wasNull: true
zero getInt result: 0
zero getInt wasNull: false
NULL getBoolean result: false
NULL getBoolean wasNull: true
empty getString preserved: true
empty getString wasNull: false
typed getObject NULL: true
typed getObject wasNull: true
~~~

### Giải thích kết quả và giới hạn

- Fake `PreparedStatement` ghi binding vào `Map<Integer,Object>`. Dùng `containsKey` để phân biệt **có parameter được bind thành null** với **parameter chưa có trong map**. `HashMap.get` trả null cho cả key vắng và key gắn null, giống một bẫy thường gặp khi xử lý PATCH payload.
- `ps.setNull(1, Types.INTEGER)`, `ps.setObject(2,null,Types.VARCHAR)` gắn SQL-type intent vào binding; `ps.setInt(3,0)` gắn zero thật. Dòng `affected rows (fake): 1` do Proxy trả giả lập, **không có một row database nào được thay đổi**.
- Getter `getInt("age")` cho `0` và `wasNull()` true; `getInt("score")` cũng cho 0 nhưng `wasNull()` false. Đó là lý do không thể map hai cột vào cùng primitive logic mà không kiểm tra trạng thái.
- `getBoolean("enabled")` trả false khi SQL NULL trong mô phỏng, `wasNull` true. Đừng hiểu false là giá trị Boolean đã xác nhận trong domain.
- `getString("nickname")` trả `""` với `wasNull` false; nó là một giá trị chuỗi rỗng trong mô phỏng, không phải SQL NULL. Database thật có thể có quy tắc khác.
- `getObject("age",Integer.class)` trả null. Với dữ liệu không null, typed conversion phải được driver hỗ trợ; fake `Class.cast` chỉ là bước mô phỏng đơn giản chứ không phải full JDBC conversion.
- Proxy ném `SQLFeatureNotSupportedException` với tất cả method chưa triển khai. **Không được đưa vào production** hoặc coi nó là JDBC driver thực sự; đây là một công cụ học cách dùng API.

## 9. Mã JDBC thực tế: ghi nullable và đọc lại an toàn

Đây là một class kiểu repository dùng **`DataSource` được inject**, để thấy đúng chỗ xử lý null (độc lập với cách tạo pool/driver).

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class PersonRepository {
    private final DataSource dataSource;

    public PersonRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, Integer age, String nickname) throws SQLException {
        String sql = "INSERT INTO person (id, age, nickname) VALUES (?, ?, ?)";
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            if (age == null) ps.setNull(2, Types.INTEGER);
            else ps.setInt(2, age);

            if (nickname == null) ps.setNull(3, Types.VARCHAR);
            else ps.setString(3, nickname);

            ps.executeUpdate();
        }
    }

    public Integer findAge(long id) throws SQLException {
        String sql = "SELECT age FROM person WHERE id = ?";
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new SQLException("Không tìm thấy person");
                int value = rs.getInt(1);
                return rs.wasNull() ? null : value;
            }
        }
    }
}
~~~

**Class này biên dịch trên Java 17**, nhưng để **chạy SQL thật** phải có JDBC driver, database và bảng `person` phù hợp. Nó không có `main` hay stdout cố định. Việc dùng exception cho “not found” là một policy minh họa; API production thường tách “không tìm thấy row” bằng `Optional` hoặc một result type riêng, còn SQL failures dùng `SQLException`. Không chuyển “not found” thành `null age`, vì người dùng với age NULL là một record **thực sự tồn tại**.

Nếu có nhiều statements thuộc cùng transaction, phải dùng **cùng connection và quản lý commit/rollback** theo transaction boundary của framework/ứng dụng. Không tạo/mở DataSource/pool trong mỗi repository method.

### Đọc `Optional` mà không làm mất ý nghĩa no-row

Một phương thức chỉ trả `Optional<Integer>` **không đủ** khi muốn biểu diễn ba trạng thái:
- Không tồn tại row.
- Có row, age SQL NULL.
- Có row, age là số.

Vì `Optional.empty()` có thể đại diện cho cả **no-row** và **SQL NULL**, thiết kế cần kiểu kết quả chứa record hoặc wrapper rõ ràng, ví dụ `Optional<Person>` với `Person.age()` nullable hoặc một sealed result hierarchy do domain định nghĩa.

~~~java
record Person(long id, Integer age) {}

Optional<Person> result;
if (!rs.next()) {
    result = Optional.empty();
} else {
    long id = rs.getLong("id");
    int a = rs.getInt("age");
    Integer age = rs.wasNull() ? null : a;
    result = Optional.of(new Person(id, age));
}
~~~

Đây là **đoạn minh họa trong method**, cần import `java.util.Optional`, có một `ResultSet` đang mở và cursor do method kiểm soát. Java record là immutable, nhưng component `age` vẫn có thể null nếu contract cho phép. Khi domain cấm nullable, validate hoặc map thành lỗi, đừng âm thầm biến null thành 0.

### Tính toán với wrapper phải tránh auto-unboxing null

~~~java
Integer age = null;
// int value = age; // Chạy sẽ ném NullPointerException do unboxing.
int value = age != null ? age : 0; // Chỉ khi domain chấp nhận default 0.
~~~

Đây là đoạn minh họa. Dù code biên dịch, auto-unboxing `Integer` null gây `NullPointerException`. Không đẩy trách nhiệm semantic mapping bằng việc trộn nullable wrapper vào phép toán rồi “chữa” bằng default 0 nếu business không cho phép.

## 10. Quy tắc driver và DBMS cần kiểm chứng

JDBC định nghĩa cách gọi API, nhưng **mức hỗ trợ SQL type, implicit conversion và schema semantics** phụ thuộc driver/database. Các ví dụ thường gặp:

| Chủ đề | Cần kiểm tra |
| --- | --- |
| Untyped `setObject(i, null)` | Backend có thể cần parameter SQL type rõ; ưu tiên `setNull(i, Types.X)` |
| `getObject(..., Integer.class)` | Driver có hỗ trợ typed conversion cho cột này không? SQL NULL có trả null không? |
| `NUMERIC/DECIMAL` | `getObject` thường trả `BigDecimal`, không tự cast `Integer` |
| `BOOLEAN/BIT/TINYINT` | SQL dialect và getter boolean mapping khác nhau; null cần `wasNull` |
| `UUID`/JSON/ARRAY/ENUM/UDT | Có thể cần vendor-specific wrapper, typeName hoặc SQL type code riêng |
| `CHAR`/`VARCHAR` empty string | Oracle zero-length string semantics khác nhiều DBMS |
| `NOT NULL`/DEFAULT | Constraint, trigger, server SQL mode ảnh hưởng insert/update null |
| `COALESCE` và type inference | Driver/server quyết định kiểu biểu thức, đôi khi cần CAST |
| `ResultSetMetaData.isNullable` | Metadata có thể báo nullable, noNulls hoặc unknown; vẫn kiểm tra giá trị thực |
| Parameter metadata | Không phải driver nào cũng suy ra mọi parameter type từ SQL |
| Stored procedure OUT parameters | `CallableStatement.registerOutParameter` xác định SQL type và cách đọc OUT |
| Temporal/timestamp/null | Java `LocalDate`/`OffsetDateTime` conversions cần kiểm tra driver/JDBC mapping |
| Database collation | Equality/order có thể khác raw Java `String.equals`; collation không tự xóa nullability |
| SQL feature unsupported | Có thể ném `SQLFeatureNotSupportedException`; xử lý theo driver/version |

### Oracle và empty string

Oracle Database nổi tiếng ở chỗ zero-length strings trong nhiều SQL character types được xử lý như SQL NULL. Vì thế cùng một Java `setString(i, "")`, khi đọc lại bằng `getString` có thể không thu được `""` như trên PostgreSQL. Đây **không phải lỗi chuẩn JDBC getString**, mà là một khác biệt của **database storage semantics**. Nếu business bắt buộc phân biệt “không có giá trị” và “chuỗi rỗng”, phải thiết kế schema/application rules phù hợp DBMS và test lại khi di chuyển hệ thống.

### `getObject` có thể không trả kiểu Java như bạn đoán

~~~java
Object value = rs.getObject("price");
if (value instanceof java.math.BigDecimal amount) {
    // Tính toán tiền tệ theo decimal, không ép sang double.
}
~~~

Đây là snippet có một ResultSet hợp lệ. JDBC có mapping tiêu chuẩn cho SQL DECIMAL/NUMERIC, nhưng runtime Java type còn phụ thuộc SQL type chính xác và driver. Không làm `(Integer) rs.getObject("price")` chỉ vì giá trị hiển thị có vẻ là số nguyên. Với tiền tệ, `BigDecimal` thường thích hợp hơn vì tránh mất chính xác do floating point.

### SQL NULL cho output parameters

Với stored procedures, `CallableStatement` có `registerOutParameter(index, Types.X)` trước khi execute. Sau đó đọc bằng `getObject/getXxx` và kiểm tra `wasNull` tương tự ResultSet khi dùng primitive. Hợp đồng argument/OUT type, procedure defaults và driver behavior phụ thuộc DBMS. Đừng tự coi một OUT parameter không được set là same as SQL NULL hoặc zero.

## 11. Exception handling, security và logging

### SQL NULL hợp lệ khác lỗi JDBC

- SQL NULL là **một giá trị có thể hợp lệ** trong schema.
- `SQLException` là lỗi truy cập, conversion, constraint, invalid parameter hoặc API usage; có thể chứa SQLState/vendor error code.
- `SQLFeatureNotSupportedException` cho biết một feature/type/conversion không được driver hỗ trợ theo contract.
- `SQLIntegrityConstraintViolationException` có thể chỉ ra constraint violation ở một số drivers, ví dụ cố ghi NULL vào cột `NOT NULL`.

**Không** catch mọi `SQLException` rồi return `null`: hành động đó làm mất phân biệt “truy vấn lỗi” với “row tồn tại nhưng cột SQL NULL”, khiến nghiệp vụ có thể ra quyết định sai. Thay vào đó, propagate hoặc map lỗi thành một loại rõ ràng và log metadata đã sanitize.

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
             "SELECT age FROM person WHERE id = ?")) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            return Optional.empty();
        }
        int raw = rs.getInt("age");
        Integer age = rs.wasNull() ? null : raw;
        return Optional.of(new Person(id, age));
    }
}
~~~

Đây là **đoạn minh họa bên trong một method** có `dataSource`, `id`, record `Person` và method return type `Optional<Person>`; import JDBC/Optional và xử lý SQLExceptions. Nó không phù hợp nếu method nhận một DataSource khác hoặc transaction manager khác mà không điều chỉnh boundary.

### Bind parameters vẫn cần thiết dù giá trị là NULL

Không nối SQL string với user input để tạo điều kiện truy vấn; dùng `PreparedStatement` và các predicate/query variants cố định. Đừng đưa PII, passwords, access tokens hoặc nguyên parameter object vào logs. Một SQL exception có thể chứa câu SQL, tên cột, URL hoặc thông tin DB; log có kiểm soát và không dùng SQLState một cách sơ sài như bằng chứng duy nhất về intent.

### Không dùng NULL như một cơ chế phân quyền

Nếu giá trị `owner_id` NULL có nghĩa “không có chủ”, đừng tự định nghĩa điều đó thành “ai cũng được phép đọc”. Quyền truy cập phải xuất phát từ policy/access control rõ ràng, với behavior cho missing owner. SQL three-valued logic có thể làm predicates bảo mật bị loại trừ hoặc vô tình bao gồm record nếu query dùng `COALESCE` sai. Kiểm thử quyền truy cập với cả null và non-null.

## 12. Nullability trong schema và metadata

Một schema minh họa:

~~~sql
CREATE TABLE person (
    id BIGINT NOT NULL PRIMARY KEY,
    age INTEGER NULL,
    nickname VARCHAR(100) NULL,
    verified BOOLEAN NULL
);
~~~

Đây là DDL minh họa theo dialect có `BOOLEAN`; không phải cú pháp chắc chắn dùng nguyên xi ở mọi DBMS. `NOT NULL` ở `id` bảo vệ tính hợp lệ của khóa; `age` và `verified` cho phép “chưa biết” theo ví dụ. Nếu business thực sự chỉ có hai trạng thái verified, nên dùng `NOT NULL DEFAULT FALSE` (khi có lý do nghiệp vụ) thay vì luôn để nullable và thêm xử lý không cần thiết.

`ResultSetMetaData.isNullable(columnIndex)` có thể trả một trong:
- `ResultSetMetaData.columnNoNulls`;
- `ResultSetMetaData.columnNullable`;
- `ResultSetMetaData.columnNullableUnknown`.

Metadata là thông tin khai báo/ước lượng theo query và driver; nó không thay thế việc đọc **giá trị SQL NULL** thực của một row. Biểu thức SELECT hoặc LEFT JOIN có thể khiến nullability của kết quả khác với cột trong bảng, nên hãy test result của truy vấn thực tế.

**Không phải mọi NULL đều nên được cho phép:** schema và domain nên có `NOT NULL` khi missing value là lỗi. Nullable chỉ nên dùng cho dữ liệu thật sự chưa biết/tùy chọn, chứ không phải để tránh validation.

## 13. Kiểm thử ứng dụng: cần bao phủ các trạng thái khác nhau

### Ma trận test cơ bản

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Row không tồn tại | `rs.next() == false`, tách khỏi row có cột NULL |
| Row tồn tại, `INTEGER NULL` | `getInt` = 0, `wasNull` = true, mapper trả Integer null |
| Row tồn tại, `INTEGER 0` | `getInt` = 0, `wasNull` = false, mapper trả Integer 0 |
| Row tồn tại, `BOOLEAN NULL` | `getBoolean` = false, `wasNull` = true |
| Row tồn tại, `BOOLEAN FALSE` | `getBoolean` = false, `wasNull` = false |
| `VARCHAR NULL` | `getString` = null |
| `VARCHAR ''` | Chuỗi rỗng nếu DBMS phân biệt empty/NULL |
| Typed `getObject` | Null giữ null; conversion non-null đúng nếu driver hỗ trợ |
| `setNull(i, Types.X)` | Driver bind đúng SQL type; NULL được chấp nhận hoặc constraint từ chối |
| `setObject(i, null, Types.X)` | Tương thích với driver cho type cụ thể |
| `setObject(i, null)` | Test hoặc tránh vì inference không portable |
| Parameter không được set | Phải fail hoặc tuân theo driver/SQL contract; không giả định NULL |
| Nullable column với DEFAULT | Omitted khác explicit NULL |
| `WHERE col = ?` với parameter NULL | Không match rows NULL bằng equality thông thường |
| `IS NULL` / `IS NOT NULL` | Rows được lọc đúng |
| `NOT IN` subquery có NULL | Không loại trừ sai do UNKNOWN |
| `COUNT(*)` vs `COUNT(col)` | Khác khi col có NULL |
| `LEFT JOIN` không có match | Column bên phải NULL, tách khỏi row có nullable right-side field |
| Oracle empty string | Regression riêng theo DBMS |
| BLOB/CLOB/JSON/UDT nullable | Kiểm tra typed mapping và driver support |
| Batch/exceptions/transactions | Bind lại mọi parameter và rollback/commit rõ |

### Integration test với DB thật

Một test có ích cần:
1. Database/container test riêng cùng **driver version, schema, SQL dialect** tương tự production.
2. Tạo rows với `age NULL`, `age 0`, `age positive`, `nickname NULL`, `nickname ''` khi DB hỗ trợ.
3. Gọi `setNull`/`setObject` với SQL type cụ thể và kiểm tra `SQLException`/constraint.
4. SELECT lại từng row, gọi `getInt` + `wasNull` ngay lập tức, `getString`, `getObject` và typed `getObject`.
5. Thử `IS NULL`, `COALESCE`, aggregates, joins và nullable filters.
6. Test SQL NULL từ expressions/subqueries, không chỉ cột vật lý.
7. Kiểm tra constraints, DEFAULT, stored procedures, temporal/UDT mappings nếu app sử dụng.
8. Đóng `Connection`, `PreparedStatement`, `ResultSet` qua try-with-resources; không dùng production secrets/DB.
9. Chạy regression khi nâng cấp driver/database để phát hiện khác biệt conversion.
10. Bảo đảm unit tests không ghi đè integration tests: proxy fake chỉ chứng minh mapper code, không chứng minh behavior của vendor database.

### Khi dùng batch update

Với `PreparedStatement.addBatch()`, mỗi iteration phải bind **đầy đủ các parameters** hoặc có chính sách `clearParameters()` thích hợp trước khi bind. Đừng để một giá trị từ lần lặp trước vô tình được tái sử dụng khi field mới absent/null. Với câu SQL UPDATE tùy chọn, tách trường hợp “không thay đổi” khỏi “đặt SQL NULL”, vì một `setNull` nhầm lẫn có thể xóa dữ liệu.

## 14. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `getInt` và bỏ qua `wasNull` | NULL bị biến thành zero | Gọi `wasNull` ngay; map sang Integer |
| Dùng `getBoolean` rồi coi false là đã xác minh | SQL NULL trở thành false | Map sang Boolean hoặc typed getObject |
| Gọi `wasNull` sau một getter khác | Kiểm tra nhầm cột | Gọi ngay sau getter quan tâm |
| Dùng `getString(...).isEmpty()` ngay | Ném NullPointerException nếu SQL NULL | Kiểm tra null trước |
| Dùng `getObject` rồi cast tùy ý | ClassCastException hoặc sai conversion | Kiểm tra SQL type/driver hoặc typed getObject |
| Truyền `setObject(i, null)` không kiểu mọi nơi | Ambiguous parameter type | Dùng `setNull(i, Types.X)` |
| Dùng `setNull(i, Types.VARCHAR)` cho mọi cột | Conversion/type errors | Chọn type theo schema |
| Ghi chuỗi `"NULL"` | Lưu text thật, không phải SQL NULL | Bind typed NULL |
| Ghi `""` để biểu diễn missing number/date | Sai domain và SQL type | Dùng typed null/nullable field |
| Filter `col = NULL` | UNKNOWN, không tìm rows NULL | Dùng `IS NULL` |
| Bind NULL cho `WHERE col = ?` rồi trông chờ null match | Không thể match qua equality | Chọn predicate rõ |
| Dùng `NOT IN` với tập chứa NULL mà không kiểm tra | Bẫy logic UNKNOWN | Cân nhắc `NOT EXISTS` và null policy |
| Đồng nhất `COUNT(*)` với `COUNT(col)` | Sai số thống kê | Biết COUNT(col) bỏ qua NULL |
| Xem `COALESCE(x,0)` là raw value x | Mất phân biệt missing/zero | Giữ raw field và presentation separately |
| Cho rằng explicit NULL kích hoạt DEFAULT | DB có thể lưu NULL hoặc reject | Omit field/keyword DEFAULT theo dialect |
| Coi absent request = JSON null = SQL NULL | PATCH xóa nhầm data | Dùng presence marker và contract rõ |
| Coi `Optional.empty()` thể hiện cả row và column một cách không mất mát | Mất trạng thái “row có nhưng column NULL” | Dùng Optional<Person> hoặc result type có cấu trúc |
| Gộp SQL NULL với empty string theo mọi DBMS | Hỏng data khi migrate | Kiểm tra Oracle/DBMS semantics |
| Thay mọi SQLException bằng Java null | Che lỗi thật như “không có dữ liệu” | Error/result types tường minh |
| Tự sửa `SQLException` bằng setObject untyped | Không portable | SQL type đúng và integration test |
| Chỉ test fake proxy | Không phát hiện driver-specific behavior | Chạy DB/driver integration tests |
| Không đóng JDBC resources | Connection leak và pool exhaustion | Try-with-resources, owner lifecycle |

## 15. Tự kiểm tra

1. **SQL `NULL` và Java `null` có giống nhau tuyệt đối không?** Không. SQL NULL là marker trong dữ liệu/logic ba giá trị; Java null là reference value. JDBC xác định mapping.
2. **`getInt("age")` trả gì khi SQL NULL?** Trả 0; gọi ngay `wasNull()` để phân biệt với zero thật.
3. **`getBoolean("verified")` trả gì với SQL NULL?** Trả false; `wasNull()` cho true.
4. **`getString("nickname")` trả gì khi SQL NULL?** Java null, không phải `""` hoặc `"NULL"`.
5. **Tại sao `wasNull` phải gọi ngay?** Vì nó phản ánh getter **gần nhất** trên ResultSet.
6. **`setNull` cần thông tin nào ngoài parameter index?** SQL type code phù hợp, ví dụ `Types.INTEGER`.
7. **`setObject(index,null)` có portable không?** Không đủ portable; nhiều database cần type rõ. Chọn `setNull` hoặc typed `setObject`.
8. **`WHERE age = NULL` có tìm row age NULL không?** Không; biểu thức là UNKNOWN. Dùng `IS NULL`.
9. **`NULL = NULL` trả TRUE hay UNKNOWN?** UNKNOWN trong SQL logic chuẩn.
10. **`COUNT(*)` và `COUNT(age)` có luôn bằng nhau không?** Không khi có age NULL.
11. **`COALESCE(age,0)` có sửa dữ liệu age trong DB không?** Không nếu chỉ dùng trong SELECT; nó thay giá trị của biểu thức.
12. **Không truyền nickname trong PATCH có đồng nghĩa ghi SQL NULL?** Không; có thể nghĩa là giữ nguyên field.
13. **Cột có DEFAULT, explicit SQL NULL sẽ luôn dùng DEFAULT?** Không; thường lưu null hoặc bị từ chối theo schema.
14. **`getObject("price")` luôn trả Integer nếu chữ số không có phần thập phân?** Không; phụ thuộc SQL type/driver, DECIMAL thường là BigDecimal.
15. **Có thể dùng `Optional<Integer>` vừa biểu thị row không tồn tại vừa biểu thị row có age NULL mà không mất thông tin không?** Không; cần thêm cấu trúc để giữ ba trạng thái.
16. **Zero-length character string có luôn phân biệt với SQL NULL không?** Không; Oracle có rule đặc biệt.
17. **`ResultSet.next() == false` có tương đương “column SQL NULL” không?** Không; query không có row.
18. **Tại sao không catch mọi SQLException rồi return null?** Vì lỗi truy vấn và SQL NULL là hai trạng thái khác.
19. **`SQLFeatureNotSupportedException` giúp gì?** Cho biết method/type conversion không được driver hỗ trợ.
20. **Cần test gì trước khi đổi vendor driver?** Typed NULL binding, getters/wasNull, empty vs null, SQL logic, defaults, metadata và migrations.

## 16. Tài liệu chính thức còn áp dụng

- [Java SE 25 — PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): `setNull`, `setObject` typed/untyped, `setString`, parameter indexes, SQL types và exceptions.
- [Java SE 25 — ResultSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSet.html): `getInt`, `getBoolean`, `getString`, `getObject`, `wasNull` và driver conversion.
- [Java SE 25 — java.sql.Types](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Types.html): SQL type codes cho typed null binding.
- [Java SE 25 — java.sql.JDBCType](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/JDBCType.html): các JDBC SQLType enum values.
- [Java SE 25 — java.sql.ResultSetMetaData](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSetMetaData.html): `isNullable` và thông tin kiểu cột.
- [Java SE 25 — SQLException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLException.html): SQLState, error code và handling.
- [Java SE 25 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): driver không hỗ trợ API/SQL feature.
- [PostgreSQL — Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): SQL NULL, `IS NULL`, `IS DISTINCT FROM` và logic so sánh.
- [PostgreSQL — Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): `COUNT(*)`, `COUNT(expression)`, aggregate null semantics.
- [Oracle Database — Nulls](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Nulls.html): SQL NULL và empty character string semantics của Oracle.
- [Microsoft SQL Server — NULL and UNKNOWN](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/null-and-unknown-transact-sql): logic SQL ba giá trị và cách so sánh với NULL.

**Tóm tắt:** SQL `NULL` là một trạng thái dữ liệu, Java `null` là một reference value, còn JDBC driver là lớp **chuyển đổi có quy tắc**. Khi đọc, primitive getters như `getInt` và `getBoolean` **không giữ được nullability nếu thiếu `wasNull()`**. Khi ghi, bind `NULL` **có SQL type rõ ràng**. Khi truy vấn, dùng `IS NULL`, hiểu logic UNKNOWN, giữ phân biệt no-row/row-with-NULL và không để các giá trị mặc định vô tình xóa mất ý nghĩa nghiệp vụ.