# SqlParameterValue và khai báo java.sql.Types trong Spring JDBC

## 1. Mục tiêu và vấn đề cần giải quyết

Khi gọi SQL qua `JdbcTemplate`, lập trình viên thường chỉ truyền giá trị Java:

```java
jdbc.update(
    "INSERT INTO customer_notes(customer_id, note) VALUES (?, ?)",
    customerId,
    note
);
```

Phần lớn trường hợp, Spring và JDBC driver có thể suy ra cách bind `Long`, `String`, `BigDecimal` hay `Boolean`. Nhưng với **`null`, kiểu SQL đặc thù, số thập phân có scale, hoặc driver có quy tắc ép kiểu riêng**, giá trị Java không luôn cung cấp đủ thông tin. Đó là lúc khai báo **JDBC SQL type** bằng `java.sql.Types` và dùng `org.springframework.jdbc.core.SqlParameterValue`.

Nội dung bài:
- Phân biệt **kiểu Java**, **mã kiểu JDBC `Types`**, và **kiểu dữ liệu của cột trong database**.
- Hiểu chính xác `SqlParameterValue` lưu `value`, `sqlType`, `scale` hoặc `typeName`, cách truyền vào `JdbcTemplate`.
- Bind an toàn giá trị `null` có kiểu rõ ràng, thay vì đoán kiểu từ Java null.
- So sánh 3 cách khai báo SQL type: `SqlParameterValue`, mảng `int[] argTypes` và `MapSqlParameterSource`/`BeanPropertySqlParameterSource`.
- Áp dụng cho số DECIMAL/NUMERIC, chuỗi, số nguyên, ngày giờ và các kiểu đặc thù.
- Nhận diện giới hạn: khai báo SQL type **không làm NULL bằng giá trị thông thường**, không biến một truy vấn sai thành đúng, không thay thế constraint và không bảo đảm mọi driver hỗ trợ cùng kiểu.
- Viết và kiểm thử chương trình Java 17+, Spring Boot, H2 có kết quả kiểm chứng được.

Bối cảnh: **Spring Framework 6.x, `spring-jdbc`, JDBC blocking, Java 17+**. Nội dung tập trung vào **tham số đầu vào SQL** của `JdbcTemplate`/`NamedParameterJdbcTemplate`, không coi chúng là các tham số `OUT` trong stored procedure.

## 2. Ba lớp khái niệm dễ bị nhầm

### 2.1. Kiểu Java là kiểu của object trong ứng dụng

`String`, `Long`, `Integer`, `BigDecimal`, `LocalDate`, `java.sql.Date`, `Boolean`… định nghĩa giá trị ở phía Java. Khi một biến Java đang là `null`, chính object đó **không còn mang thông tin runtime về kiểu muốn bind**.

Ví dụ:

```java
String nickname = null;
java.math.BigDecimal price = new java.math.BigDecimal("19.90");
```

`nickname` có kiểu tĩnh là String trong Java, nhưng một overload varargs nhận `Object...` có thể chỉ nhận object null tại runtime; Spring/driver không thể luôn khẳng định đó là SQL `VARCHAR` chỉ từ null.

### 2.2. java.sql.Types là mã kiểu JDBC tiêu chuẩn

`java.sql.Types` chứa **hằng số int** chỉ các loại dữ liệu SQL/JDBC chung:

| Mã JDBC | Ý nghĩa chung | Ví dụ cột SQL thường gặp |
|---|---|---|
| `Types.VARCHAR` | Chuỗi ký tự biến độ dài | `VARCHAR(100)` |
| `Types.CHAR` | Chuỗi độ dài cố định | `CHAR(2)` |
| `Types.NVARCHAR` | Chuỗi quốc tế/NCHAR family | `NVARCHAR(100)` |
| `Types.INTEGER` | Số nguyên 32 bit thông dụng | `INTEGER` |
| `Types.BIGINT` | Số nguyên lớn | `BIGINT` |
| `Types.SMALLINT` | Số nguyên nhỏ | `SMALLINT` |
| `Types.DECIMAL` / `Types.NUMERIC` | Số thập phân chính xác | `DECIMAL(12,2)` |
| `Types.REAL` / `Types.DOUBLE` | Số dấu phẩy động | `REAL` / `DOUBLE PRECISION` |
| `Types.BOOLEAN` | Boolean SQL | `BOOLEAN` |
| `Types.DATE` | Ngày (không giờ) | `DATE` |
| `Types.TIME` | Giờ (không ngày) | `TIME` |
| `Types.TIMESTAMP` | Ngày giờ không có thông tin timezone trong loại SQL này | `TIMESTAMP` |
| `Types.TIMESTAMP_WITH_TIMEZONE` | Ngày giờ có xử lý timezone theo SQL/JDBC | `TIMESTAMP WITH TIME ZONE` (tùy DB) |
| `Types.BINARY` / `Types.VARBINARY` | Dữ liệu nhị phân | `BINARY` / `VARBINARY` |
| `Types.BLOB` / `Types.CLOB` | Đối tượng nhị phân/văn bản lớn | `BLOB` / `CLOB` |
| `Types.ARRAY` | SQL array | Hỗ trợ tùy DB/driver |
| `Types.OTHER` | Kiểu DB-specific/không có mã chung phù hợp | UUID, JSONB, enum… tùy DB/driver |
| `Types.NULL` | Mã SQL NULL tổng quát | **Không phải “kiểu cột nullable”** |

`Types.VARCHAR` chỉ là **một số nguyên hằng**, không phải lớp `String`. Các mã này dùng làm input cho JDBC methods như `PreparedStatement.setNull(position, Types.VARCHAR)`, và cho các API Spring có chấp nhận `sqlType`.

### 2.3. Kiểu thực sự của database vẫn quyết định hợp lệ

Một cột `DECIMAL(12,2)` có precision/scale và constraint riêng; một cột PostgreSQL `JSONB` không tự nhiên trở thành một `VARCHAR` tiêu chuẩn. SQL type code giúp **driver biết ý định bind**, nhưng không bảo đảm database sẽ chấp nhận giá trị hoặc tự chuyển đổi như lập trình viên mong muốn.

Ví dụ:
- `String "123"` được bind dưới `Types.VARCHAR` không có nghĩa DB phải nhận nó cho cột số nguyên.
- `BigDecimal("123.456")` với `Types.DECIMAL` không buộc cột `DECIMAL(5,2)` phải giữ đủ 3 chữ số thập phân.
- `Types.OTHER` không phải “cứ dùng cho thứ không hiểu”; cách bind JSON/UUID/enum có thể cần `typeName`, object vendor-specific hoặc cast SQL theo driver.

**Thiết kế đúng:** đọc schema và tài liệu JDBC driver thực tế; dùng `Types` đúng với SQL parameter, rồi xác minh trên database mục tiêu.

## 3. SqlParameterValue là gì?

Lớp `org.springframework.jdbc.core.SqlParameterValue` **mở rộng `SqlParameter`**. Nó đại diện cho **một giá trị tham số đầu vào cụ thể** cùng thông tin kiểu SQL đã khai báo. Spring mô tả nó để dùng trong các phép `JdbcTemplate` nhận **mảng các giá trị tham số dạng thông thường** (bao gồm overload varargs).

Các constructor thông dụng trong Spring Framework 6.x:

```java
new SqlParameterValue(int sqlType, Object value);

new SqlParameterValue(int sqlType, int scale, Object value);

new SqlParameterValue(int sqlType, String typeName, Object value);

new SqlParameterValue(SqlParameter declaredParam, Object value);
```

Chữ ký trên là cách viết minh họa; trong code Java thực, **không** có tên tham số `int sqlType` nằm giữa biểu thức `new` như ở đây. Mỗi constructor nhận giá trị/thông tin tương ứng. Một `SqlParameterValue` có thể cho biết:
- `getSqlType()` — mã JDBC SQL type (kế thừa từ `SqlParameter`).
- `getScale()` — scale đã khai báo nếu có (đặc biệt cho DECIMAL/NUMERIC).
- `getTypeName()` — tên kiểu DB-specific tùy chọn nếu có.
- `getValue()` — giá trị thực, có thể là Java `null`.

Ví dụ hợp lệ:

```java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameterValue;

SqlParameterValue note =
    new SqlParameterValue(Types.VARCHAR, null);

SqlParameterValue customerId =
    new SqlParameterValue(Types.BIGINT, 42L);

SqlParameterValue amount =
    new SqlParameterValue(
        Types.DECIMAL, 2, new BigDecimal("19.90"));
```

**Ý nghĩa:** `note` nói “bind một SQL parameter kiểu VARCHAR, có giá trị NULL”. Nó không phải “giá trị NULL có kiểu Java là String”, cũng không phải khai báo một cột mới. Khi dùng đúng overload của `JdbcTemplate`, Spring nhận thông tin kiểu từ wrapper để cấu hình `PreparedStatement` tương ứng.

### Chọn đúng chỗ dùng

`SqlParameterValue` thường được truyền **tại vị trí một tham số** trong danh sách giá trị:
- `jdbc.update(sql, new SqlParameterValue(...), otherValue)`.
- `jdbc.query(sql, rowMapper, new SqlParameterValue(...))`.
- `jdbc.queryForObject(sql, Long.class, new SqlParameterValue(...))` khi overload hỗ trợ argument varargs.
- Trong `Object[]` parameter values dùng cùng các overload nói trên.

Nó **không** phải DTO kết quả query, không phải `RowMapper`, không phải chỉ dẫn để tạo schema và **không tự thực thi SQL**. Cần có `JdbcTemplate`/API bind SQL để đưa thông tin kiểu vào JDBC driver.

## 4. Khi nào thực sự cần khai báo SQL type?

Trong ứng dụng bình thường, Spring thường suy ra SQL type dựa trên giá trị Java và cơ chế bind của driver. Không cần bọc tất cả String/Long một cách máy móc.

Khai báo tường minh hữu ích khi:
1. **Giá trị nullable:** `note = null` và driver cần biết cột/parameter là `VARCHAR`, `DATE`, `DECIMAL`...
2. **Số DECIMAL/NUMERIC cần scale:** lưu lượng tiền/đại lượng chính xác, muốn khai báo scale rõ theo hợp đồng.
3. **Driver không suy luận đúng một số kiểu:** giá trị Java có nhiều SQL mapping khả dĩ.
4. **Truy vấn có biểu thức hoặc function typed parameter:** cần driver biết kiểu ngay cả khi SQL không đủ ngữ cảnh.
5. **Cổng tích hợp driver/database khác nhau:** một database/driver chấp nhận null không kiểu, cái khác có thể lỗi, hoặc mapping ảnh hưởng đến execution plan. Cần test thật, không phỏng đoán.
6. **Muốn contract rõ trong repository:** các tham số cập nhật nhiều cột nullable được ghi kèm kiểu đích, dễ review và bảo trì.

**Không cần thiết** nếu một giá trị và schema đã rõ, driver xử lý ổn định và việc thêm wrapper chỉ làm code dài thêm. Tối ưu chính là **đúng kiểu khi cần**, không phải “càng nhiều Types càng tốt”.

## 5. Truyền SqlParameterValue trực tiếp cho JdbcTemplate

Giả sử schema:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    note VARCHAR(200),
    price DECIMAL(12,2) NOT NULL,
    active BOOLEAN NOT NULL,
    published_on DATE
);
```

`note` và `published_on` cho phép NULL. Với JDBC, câu INSERT dùng sáu dấu `?`, tương ứng sáu tham số từ trái sang phải:

```java
// Method trong class Spring đã có field JdbcTemplate jdbc.
public int addProduct(long id, String sku,
        String note, BigDecimal price,
        boolean active, LocalDate publishedOn) {

    return jdbc.update("""
            INSERT INTO catalog_products
                (id, sku, note, price, active, published_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
        new SqlParameterValue(Types.BIGINT, id),
        new SqlParameterValue(Types.VARCHAR, sku),
        new SqlParameterValue(Types.VARCHAR, note),
        new SqlParameterValue(Types.DECIMAL, 2, price),
        new SqlParameterValue(Types.BOOLEAN, active),
        new SqlParameterValue(Types.DATE,
            publishedOn == null
                ? null
                : java.sql.Date.valueOf(publishedOn))
    );
}
```

Đoạn này minh họa **method trong class đã import** `BigDecimal`, `LocalDate`, `Types` và `SqlParameterValue`, cùng field `jdbc`. Nó không phải file Java độc lập.

**Lưu ý vị trí:**
- `id` là tham số số 1, `sku` số 2, `note` số 3, `price` số 4, `active` số 5, `published_on` số 6.
- Mọi `SqlParameterValue` giữ kiểu JDBC đã chọn; Spring xử lý nội dung khi bind statement.
- `publishedOn == null` vẫn được bind với `Types.DATE` qua wrapper, tránh không rõ kiểu khi không có ngày.
- `Types.DECIMAL, 2` khai báo scale 2, nhưng **không tự đảm bảo** số `price` có scale hợp lệ hoặc tiền không âm. Cần validate đầu vào, schema `CHECK` nếu nghiệp vụ yêu cầu, và kiểm thử làm tròn/tràn.
- `jdbc.update(...)` trả số hàng tác động, không trả object/row từ query. Nếu unique constraint bị vi phạm, Spring có thể ném `DataIntegrityViolationException` hoặc subtype liên quan, không tự trả 0.

Để đưa giá trị `null` vào SQL, **không bao giờ viết** `'null'` như một chuỗi hoặc nối chữ NULL bằng cách ghép SQL. Cứ dùng placeholder `?` cùng typed parameter.

## 6. Bind SQL NULL có kiểu: tình huống quan trọng nhất

JDBC chuẩn hỗ trợ:

```java
preparedStatement.setNull(3, Types.VARCHAR);
```

Tại vị trí 3, driver biết tham số có SQL type VARCHAR dù không có object Java cụ thể. `SqlParameterValue` cho phép truyền ý định đó vào `JdbcTemplate` mà không tự viết `PreparedStatementSetter` cho từng lệnh:

```java
jdbc.update("""
        UPDATE catalog_products
        SET note = ?
        WHERE id = ?
        """,
    new SqlParameterValue(Types.VARCHAR, null),
    new SqlParameterValue(Types.BIGINT, 42L));
```

Tùy driver, không khai báo type khi null **có thể vẫn hoạt động**, nhưng không nên dựa vào một driver thành công để khẳng định mọi driver đều chấp nhận. Phần tài liệu Spring JDBC về **Providing SQL Type Information for Parameters** nêu rõ khai báo kiểu đôi khi cần thiết để đặt `NULL` đúng cách.

### Các điều không được nhầm

- `new SqlParameterValue(Types.VARCHAR, null)`: SQL parameter mang giá trị NULL, **kiểu dự định là VARCHAR**.
- `new SqlParameterValue(Types.NULL, null)`: chỉ báo generic SQL NULL type, **không tự diễn đạt kiểu cột đích**. Nếu cột là VARCHAR, thường chọn `Types.VARCHAR` chứ không ưu tiên `Types.NULL`.
- `new SqlParameterValue(Types.VARCHAR, "null")`: giá trị **chuỗi bốn chữ cái** n-u-l-l; không phải SQL NULL.
- `new SqlParameterValue(Types.INTEGER, 0)`: giá trị số 0; **không tương đương** SQL NULL.
- `Optional.empty()` không tự là giá trị JDBC NULL theo mọi overload. Hãy đưa ra Java null kèm kiểu và quyết định mapping rõ ở boundary.
- Cột database là `NOT NULL` thì typed NULL vẫn **vi phạm constraint**. Khai báo kiểu không làm NULL được phép lưu.

## 7. Typed NULL khác hoàn toàn với điều kiện WHERE = NULL

Đây là lỗi nghiệp vụ dễ bị che khuất khi bắt đầu dùng typed parameters.

Giả sử cột `note` có một hàng SQL NULL:

```sql
SELECT id
FROM catalog_products
WHERE note = ?;
```

Dù bạn bind:

```java
new SqlParameterValue(Types.VARCHAR, null)
```

thì `note = NULL` trong SQL **không trả TRUE**, mà cho kết quả UNKNOWN theo logic ba giá trị SQL. Do đó lọc bằng phép so sánh `= ?` với parameter null **không tìm được các hàng có note NULL** như người mới thường tưởng.

Để tìm các hàng NULL:

```sql
SELECT id FROM catalog_products WHERE note IS NULL;
```

Nếu filter có thể null và nghiệp vụ muốn “null nghĩa là lọc hàng có note SQL NULL”, hãy tách câu SQL hoặc dùng biểu thức so sánh null-safe phù hợp **dialect** (ví dụ PostgreSQL có `IS NOT DISTINCT FROM`). Đừng tự áp dụng một cú pháp vendor-specific cho mọi DB.

**Phân biệt ba ý nghĩa khi cập nhật nullable field:**
1. Gửi giá trị mới khác null → ghi giá trị đó.
2. Gửi **typed null** → đặt cột SQL NULL.
3. Không muốn thay đổi field → **không đưa field vào SET**, hoặc dùng hợp đồng patch rõ ràng; **không** coi “null đầu vào” vừa nghĩa “xóa cột” vừa nghĩa “bỏ qua cập nhật” trừ khi API đã quy định chính xác.

Với HTTP PATCH hoặc message event, cần kiểu đại diện ba trạng thái absent/null/value trong service; chỉ `Optional<T>` đôi khi chưa đủ phân biệt absent với present null.

## 8. Scale với DECIMAL/NUMERIC và BigDecimal

Constructor:

```java
new SqlParameterValue(
    Types.DECIMAL,
    2,
    new java.math.BigDecimal("19.90"));
```

đăng ký kiểu SQL DECIMAL và scale 2. Scale là **số chữ số sau dấu thập phân**. Với `DECIMAL(p,s)`, `p` là tổng chữ số có nghĩa tối đa, `s` là chữ số thập phân tối đa; giới hạn/điều chỉnh thực tế phụ thuộc SQL dialect và schema.

| Giá trị/kiểu đích | Nhận định |
|---|---|
| `BigDecimal("19.90")`, `DECIMAL(12,2)` | Phù hợp đơn vị tiền 2 chữ số thập phân |
| `BigDecimal("19.999")`, `DECIMAL(12,2)` | Có thể làm tròn hoặc bị từ chối tùy DB/driver/cấu hình; phải kiểm thử và có policy |
| `double 19.90` làm tiền | Không nên vì biểu diễn nhị phân có thể thiếu chính xác |
| `new SqlParameterValue(Types.DECIMAL, 2, amount)` | Khai báo metadata; **không phải** lớp validator tự kiểm tra currency |
| `BigDecimal#setScale(2, RoundingMode.UNNECESSARY)` | Từ chối giá trị không biểu diễn được chính xác ở scale=2; phù hợp nếu nghiệp vụ không cho phép tự làm tròn |

Một utility Java 17 minh họa kiểm tra trước khi bind:

```java
// Phương thức độc lập trong class có import BigDecimal và RoundingMode.
static BigDecimal money(BigDecimal value) {
    if (value == null || value.signum() < 0) {
        throw new IllegalArgumentException("Price must be nonnegative");
    }
    return value.setScale(2, java.math.RoundingMode.UNNECESSARY);
}
```

Nếu nghiệp vụ **cho phép làm tròn**, hãy công bố `RoundingMode.HALF_UP`/`HALF_EVEN` hoặc quy tắc phù hợp, không để driver/database âm thầm quyết định. Với giá trị số nguyên lớn, phải xét overflow và precision cột.

`SqlParameterValue` không thay `BigDecimal`. Nó mô tả **cách bind**, còn BigDecimal lưu **giá trị chính xác** trong Java.

## 9. Một cách khác: truyền mảng int[] argTypes cùng Object[] args

Spring JDBC hỗ trợ các overload cho phép cung cấp SQL type tường minh **song song** với giá trị.

Ví dụ:

```java
Object[] args = {
    42L,
    null,
    new BigDecimal("19.90")
};

int[] argTypes = {
    Types.BIGINT,
    Types.VARCHAR,
    Types.DECIMAL
};

int changed = jdbc.update("""
        UPDATE catalog_products
        SET note = ?, price = ?
        WHERE id = ?
        """,
    new Object[] {
        null,
        new BigDecimal("19.90"),
        42L
    },
    new int[] {
        Types.VARCHAR,
        Types.DECIMAL,
        Types.BIGINT
    });
```

Ở đây mảng `args` đầu tiên chỉ là minh họa ba loại giá trị và type tương ứng; **lệnh UPDATE thực tế** dùng mảng mới theo đúng thứ tự SQL: `note`, `price`, `id`. Khi dùng mảng types, số phần tử phải khớp số `?` và vị trí của mỗi loại phải khớp đối số cùng index.

Mẫu thực tế gọn:

```java
int affected = jdbc.update(
    "UPDATE catalog_products SET note = ? WHERE id = ?",
    new Object[]{null, 42L},
    new int[]{Types.VARCHAR, Types.BIGINT});
```

**So sánh:**

```java
// A: metadata nằm cạnh từng giá trị (chỉ có hai tham số cần typing):
jdbc.update("UPDATE catalog_products SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, null),
    42L);

// B: metadata nằm trong mảng parallel (mọi vị trí có SQL type):
jdbc.update("UPDATE catalog_products SET note = ? WHERE id = ?",
    new Object[]{null, 42L},
    new int[]{Types.VARCHAR, Types.BIGINT});
```

Cả hai diễn đạt ý nghĩa tương đương khi dùng đúng overload. **Không cần vừa bọc mọi argument bằng `SqlParameterValue` vừa truyền thêm mảng `argTypes`**: tài liệu Spring mô tả wrapper dành cho overload với mảng giá trị “plain”, không phải để ghép với biến thể có type array và tạo luật ưu tiên khó hiểu.

**Chọn cách nào?** `SqlParameterValue` hữu ích khi chỉ một vài tham số đặc biệt cần khai báo; mảng `argTypes` có thể phù hợp adapter generic giữ cặp giá trị–kiểu cho mỗi vị trí. Khi truy vấn dài và dễ nhầm thứ tự, named parameters thường dễ đọc hơn.

## 10. Tham số có tên: MapSqlParameterSource

Với `NamedParameterJdbcTemplate`, SQL dùng `:name` thay vì `?`. `MapSqlParameterSource.addValue` chấp nhận SQL type riêng cho từng tên:

```java
// Method trong class có NamedParameterJdbcTemplate namedJdbc.
public int clearNote(long productId) {
    var params = new MapSqlParameterSource()
        .addValue("note", null, Types.VARCHAR)
        .addValue("id", productId, Types.BIGINT);

    return namedJdbc.update("""
            UPDATE catalog_products
            SET note = :note
            WHERE id = :id
            """, params);
}
```

Ưu điểm:
- Tên `note`/`id` tránh phải nhớ vị trí trong câu SQL dài.
- Typed null được đăng ký trên chính named parameter tương ứng.
- Một parameter có tên lặp lại trong câu SQL vẫn sử dụng cùng định nghĩa giá trị và kiểu.
- Không cần tự nối/escape literal SQL.

`MapSqlParameterSource` có overload `addValue(name, value, sqlType, typeName)` khi SQL type cần tên chi tiết. Đây là chức năng khác với constructor `SqlParameterValue(sqlType, typeName, value)`; **đừng đảo thứ tự tham số**.

### Dùng BeanPropertySqlParameterSource khi lấy property từ object

`BeanPropertySqlParameterSource` có thể lấy các property JavaBean/record và cho đăng ký SQL type khi cần:

```java
// Phác họa trong service/repository đã có input object và namedJdbc.
BeanPropertySqlParameterSource source =
    new BeanPropertySqlParameterSource(input);
source.registerSqlType("note", Types.VARCHAR);
source.registerSqlType("id", Types.BIGINT);

namedJdbc.update("""
    UPDATE catalog_products
    SET note = :note
    WHERE id = :id
    """, source);
```

`input` phải có các property `note` và `id` truy cập được. Đoạn này là **snippet trong dự án**, không phải class Java độc lập. Nếu object không có property đúng tên, việc đăng ký SQL type không tự thêm giá trị cho property. Test mapping thực tế thay vì giả định.

**Không nhầm `Map.of("note", null)` với nguồn named param nullable:** Java `Map.of` **không chấp nhận giá trị null**. Dùng `MapSqlParameterSource` hoặc `HashMap` thông thường và khai báo SQL type.

## 11. SqlParameterValue so với SqlParameter và kiểu OUT

`SqlParameter` mô tả **khai báo metadata SQL parameter**, như tên, sqlType, scale, typeName; `SqlParameterValue` bổ sung **giá trị cụ thể**. Ví dụ:

```java
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.SqlParameterValue;

SqlParameter declared = new SqlParameter(Types.DECIMAL);
SqlParameterValue value = new SqlParameterValue(
    declared, new java.math.BigDecimal("15.25"));
```

`SqlParameterValue` biểu diễn input value. Với stored procedure và callable statement, Spring còn có `SqlOutParameter`, `SqlInOutParameter`, `SimpleJdbcCall`, v.v.; đừng dùng một object `SqlParameterValue` để thay thế toàn bộ cơ chế khai báo và đọc OUT parameter.

Tài liệu Spring nói `SqlParameterValue` dành cho những thao tác nhận **plain argument array**. Khi dùng `PreparedStatementCreatorFactory` hoặc stored procedure, hãy theo chính **API/metadata contract** của thành phần đó; không suy đoán tất cả cùng một cách truyền.

## 12. java.sql.Types là thông tin bind, không phải validator schema

Một số lỗi phổ biến khi người mới thấy tên `Types`:
- `Types.VARCHAR` **không ép** string dài 500 ký tự vừa vào cột `VARCHAR(50)`. Database có thể từ chối.
- `Types.INTEGER` **không ép** Java `Long` 9.000.000.000 trở thành int 32-bit an toàn. Có thể tràn hoặc driver ném lỗi.
- `Types.DECIMAL` **không đảm bảo** đúng scale/precision của cột nếu không kiểm tra đầu vào.
- `Types.DATE` không tự giải quyết timezone hay chuyển đổi mọi kiểu ngày giờ. Chọn `LocalDate`/`java.sql.Date` phù hợp và test driver.
- `Types.TIMESTAMP_WITH_TIMEZONE` không đồng nghĩa mọi DB lưu timezone gốc theo cùng cách; ví dụ PostgreSQL chuẩn hóa thời điểm, không giữ tên múi giờ đã nhập.
- `Types.OTHER` không có nghĩa mọi object tùy ý đều được serialize; JSON/UUID có thể cần object driver-specific hoặc CAST.
- `Types.NULL` không phải mã đúng để diễn tả mọi cột nullable; nên chọn mã kiểu **thực** của parameter.

**Bảo vệ dữ liệu:** validate ở service và dùng `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` và datatype thật ở DB. JDBC type declaration chỉ giúp **giao tiếp đúng với driver**.

## 13. Những trường hợp driver/database đặc biệt

### 13.1. UUID

Một số driver ánh xạ `java.util.UUID` tới kiểu UUID riêng của DB; có driver dùng `Types.OTHER`, có driver khác yêu cầu chuỗi/cast hoặc hỗ trợ `setObject` với target SQL type. Không mặc định `new SqlParameterValue(Types.VARCHAR, UUID)` là portable.

Ví dụ PostgreSQL có datatype `uuid`:

```sql
SELECT id FROM customers WHERE external_id = CAST(? AS uuid);
```

Cách bind phần Java phải được xác nhận theo pgjdbc và kiểu argument. Explicit SQL cast có thể giúp làm rõ kiểu trong một số truy vấn nhưng **không** thay nhiệm vụ validate UUID đầu vào.

### 13.2. JSON/JSONB hoặc enum

Một cột PostgreSQL `jsonb` là kiểu đặc thù, không phải `VARCHAR` chung. Nếu driver yêu cầu, có thể dùng object vendor-specific và `Types.OTHER`/typeName hoặc cast `?::jsonb` theo tài liệu chính thức của driver. **Không** cam kết mẫu này chạy trên H2, MySQL và PostgreSQL như nhau.

### 13.3. Arrays và LOBs

- `Types.ARRAY` mô tả SQL array nhưng JDBC `java.sql.Array` có vòng đời riêng, thường cần tạo qua `Connection.createArrayOf` và giải phóng theo contract. Không tự truyền `List<String>` và cho rằng mọi driver hiểu.
- `Types.BLOB`, `CLOB` và stream lớn cần `LobHandler`/`LobCreator` hoặc API JDBC phù hợp, giới hạn memory và lifecycle; một typed parameter không tự quản lý toàn bộ vòng đời stream.
- Với `TIMESTAMP`, `TIMESTAMP_WITH_TIMEZONE`, chuỗi ngày giờ từ API phải được parse/validate ở boundary; tránh gửi raw string và trông chờ DB tự đoán timezone.

**Nguyên tắc portability:** `java.sql.Types` đưa ra tên chung, nhưng hỗ trợ API cụ thể, chuyển đổi object và cách xử lý NULL vẫn phụ thuộc driver. Viết integration test trên **cùng loại DB** dùng trong production khi có kiểu đặc thù.

## 14. Ví dụ Spring Boot + H2 + Java 17 chạy được

Ví dụ hoàn chỉnh dưới đây chứng minh ba cách: `SqlParameterValue`, `int[] argTypes` và `MapSqlParameterSource`. H2 là DB nhúng dùng để học. Đối với sản phẩm PostgreSQL/MySQL/Oracle, thay cấu hình driver/schema và kiểm chứng lại bằng integration test.

### 14.1. Tạo dự án

```text
sql-typed-params-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/SqlTypedParamsDemoApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'sql-typed-params-demo'
```

`build.gradle` — Java 17, Spring Boot 3.3.5:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:typedparamsdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    note VARCHAR(200),
    price DECIMAL(12,2) NOT NULL,
    active BOOLEAN NOT NULL,
    published_on DATE
);
```

`src/main/java/example/jdbc/SqlTypedParamsDemoApplication.java`:

```java
package example.jdbc;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Types;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class SqlTypedParamsDemoApplication {

    private static final String INSERT = """
        INSERT INTO catalog_products
            (id, sku, note, price, active, published_on)
        VALUES (?, ?, ?, ?, ?, ?)
        """;

    public static void main(String[] args) {
        SpringApplication.run(SqlTypedParamsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcTemplate jdbc, NamedParameterJdbcTemplate namedJdbc) {
        return args -> {
            // A: Wrapper chứa sqlType/scale và một VARCHAR NULL.
            jdbc.update(INSERT,
                new SqlParameterValue(Types.BIGINT, 1L),
                new SqlParameterValue(Types.VARCHAR, "BOOK-1"),
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(
                    Types.DECIMAL, 2, new BigDecimal("19.90")),
                new SqlParameterValue(Types.BOOLEAN, true),
                new SqlParameterValue(
                    Types.DATE, Date.valueOf("2026-10-30"))
            );

            // B: Mảng values và JDBC type array song song.
            jdbc.update(INSERT,
                new Object[] {
                    2L,
                    "BOOK-2",
                    "second",
                    new BigDecimal("39.00"),
                    true,
                    Date.valueOf("2026-10-31")
                },
                new int[] {
                    Types.BIGINT,
                    Types.VARCHAR,
                    Types.VARCHAR,
                    Types.DECIMAL,
                    Types.BOOLEAN,
                    Types.DATE
                }
            );

            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM catalog_products",
                Long.class);
            System.out.println("products=" + count);

            String firstNote = jdbc.queryForObject(
                "SELECT note FROM catalog_products WHERE id = ?",
                String.class,
                new SqlParameterValue(Types.BIGINT, 1L));
            System.out.println(
                "firstNoteNull=" + (firstNote == null));

            BigDecimal price = jdbc.queryForObject(
                "SELECT price FROM catalog_products WHERE id = ?",
                BigDecimal.class,
                new SqlParameterValue(Types.BIGINT, 1L));
            System.out.println(
                "firstPrice=" + price.toPlainString());

            // C: Named parameter có type ngay cả khi value=null.
            MapSqlParameterSource params =
                new MapSqlParameterSource()
                    .addValue("note", null, Types.VARCHAR)
                    .addValue("id", 2L, Types.BIGINT);

            int changed = namedJdbc.update("""
                    UPDATE catalog_products
                    SET note = :note
                    WHERE id = :id
                    """, params);
            System.out.println("updatedRows=" + changed);

            String secondNote = jdbc.queryForObject(
                "SELECT note FROM catalog_products WHERE id = ?",
                String.class,
                2L);
            System.out.println(
                "secondNoteNull=" + (secondNote == null));
        };
    }
}
```

**Cách chạy:** cài Java 17 và Gradle 8.x tương thích với Spring Boot plugin ở ví dụ, mở terminal tại `sql-typed-params-demo`:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper trong dự án, có thể thay bằng `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows).

Các dòng do chương trình `System.out.println` tạo theo đúng thứ tự, không tính log startup của Spring/Gradle:

```text
products=2
firstNoteNull=true
firstPrice=19.90
updatedRows=1
secondNoteNull=true
```

Tại sao ra những giá trị đó?
- Bước A insert `BOOK-1`, note là SQL NULL **kiểu VARCHAR**, price 19.90 thuộc DECIMAL.
- Bước B insert `BOOK-2` bằng mảng values và JDBC type codes 1:1; tổng hai row.
- `SELECT COUNT(*)` trả 2.
- Lấy `note` của row 1 trả Java null vì cột chứa SQL NULL (không phải query “không tìm thấy”).
- Đọc `price` của row 1 từ `DECIMAL(12,2)` thành BigDecimal, biểu diễn 19.90.
- Bước C dùng named parameters ghi SQL NULL vào note của row 2; cập nhật đúng một row.
- Query note của row 2 trả null sau UPDATE.

**Giới hạn của demo:** H2 chỉ chứng minh hành vi trong một môi trường cụ thể; không khẳng định mọi JDBC driver suy luận NULL/DATE/BOOLEAN giống nhau. Code cần plugin Gradle, dependencies và H2 để chạy; **không thể biên dịch bằng `javac` trần** nếu không có Spring jars trên classpath.

## 15. Chương trình Java 17 thuần: kiểm tra giá trị Types và scale

Không cần database hoặc Spring để chạy đoạn sau. Nó minh họa bản chất `Types` là hằng số int, còn việc kiểm soát scale thuộc xử lý BigDecimal/logic nghiệp vụ.

Tên file: `SqlTypeAndScaleDemo.java`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Types;

public class SqlTypeAndScaleDemo {

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("19.90");
        BigDecimal normalized = amount.setScale(
            2, RoundingMode.UNNECESSARY);

        System.out.println("VARCHAR=" + Types.VARCHAR);
        System.out.println("DECIMAL=" + Types.DECIMAL);
        System.out.println("BIGINT=" + Types.BIGINT);
        System.out.println("amount=" + normalized.toPlainString());
        System.out.println("scale=" + normalized.scale());
    }
}
```

Chạy:

```bash
javac SqlTypeAndScaleDemo.java
java SqlTypeAndScaleDemo
```

Stdout chính xác theo các mã JDBC được định nghĩa trong Java 17:

```text
VARCHAR=12
DECIMAL=3
BIGINT=-5
amount=19.90
scale=2
```

Đoạn này **không thực hiện bind SQL**, nên không chứng minh driver hỗ trợ kiểu nào. Nó chỉ chứng minh `Types` là mã số chung và `BigDecimal#setScale` cho phép xác minh chính sách scale trước khi ghi.

## 16. Kiểm thử binding: cần test cái gì?

### Ma trận tối thiểu

| Trường hợp | Input | Kỳ vọng |
|---|---|---|
| Nullable VARCHAR | `SqlParameterValue(Types.VARCHAR, null)` | Cột nhận SQL NULL khi schema cho phép |
| String không null | `Types.VARCHAR, "hello"` | Lưu/đọc lại "hello" |
| DECIMAL có scale | `Types.DECIMAL, 2, BigDecimal("19.90")` | Lưu đúng số với scale phù hợp schema/driver |
| DATE | `Types.DATE, java.sql.Date.valueOf(...)` | Truy vấn/đọc lại ngày đúng |
| BOOLEAN | `Types.BOOLEAN, true` | Lưu/đọc lại boolean true |
| Parallel argTypes | Mỗi `?` có một value/type theo thứ tự | Lưu đúng cột, không nhầm thứ tự |
| Named parameter typed null | `addValue("note", null, Types.VARCHAR)` | Ghi NULL đúng cột |
| Invalid precision/length | Giá trị vượt ràng buộc schema | Nhận lỗi, không im lặng cắt/chuyển sai |
| NOT NULL constraint | Bind typed null vào cột NOT NULL | Database từ chối; không coi typed NULL là hợp lệ |
| `WHERE note = ?` và null | Typed null | **Không** tìm các row có note SQL NULL theo `=` |
| `WHERE note IS NULL` | Không cần bind null vào phép so sánh này | Tìm đúng các row có SQL NULL |
| DB-specific UUID/JSONB/ARRAY | Input theo driver | Test trên DB thật để xác định binding đúng |

### JUnit 5 với Spring JDBC

Ví dụ test dùng `JdbcTemplate` thực, schema H2 giống phần 14, trong dự án có `spring-boot-starter-test`:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

Snippet test method trong class có `@JdbcTest`, `@Autowired JdbcTemplate jdbc` và các static imports AssertJ:

```java
@Test
void typedNullIsPersistedAsSqlNull() {
    int inserted = jdbc.update("""
            INSERT INTO catalog_products
                (id, sku, note, price, active, published_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
        new SqlParameterValue(Types.BIGINT, 100L),
        new SqlParameterValue(Types.VARCHAR, "T-100"),
        new SqlParameterValue(Types.VARCHAR, null),
        new SqlParameterValue(
            Types.DECIMAL, 2, new BigDecimal("1.20")),
        new SqlParameterValue(Types.BOOLEAN, true),
        new SqlParameterValue(Types.DATE, null));

    assertThat(inserted).isEqualTo(1);

    Long count = jdbc.queryForObject("""
            SELECT COUNT(*) FROM catalog_products
            WHERE id = ? AND note IS NULL
            """, Long.class, 100L);

    assertThat(count).isEqualTo(1L);
}
```

Đây là **method test minh họa**; để chạy cần import `org.junit.jupiter.api.Test`, `org.assertj.core.api.Assertions.assertThat`, `Types`, `BigDecimal`, `SqlParameterValue` và đã khởi tạo test context/schema/bean. Test trên H2 chưa đủ khi thực tế dùng vendor types PostgreSQL/Oracle; hãy chạy Testcontainers với đúng driver/dialect.

Để bảo đảm SQL type được truyền đúng, có thể spy/mock `PreparedStatement` và xác minh lời gọi `setNull(index, sqlType)`/`setObject` khi cần; tuy nhiên Spring/driver có thể chọn API bind khác nhau tùy phiên bản và JDBC metadata, nên integration test giá trị **read-back từ DB thật** vẫn quan trọng nhất. Đừng viết test quá phụ thuộc chi tiết implementation khi yêu cầu thực sự là dữ liệu lưu chính xác.

## 17. Hiệu năng và tính an toàn

### 17.1. Typed binding không thay thế PreparedStatement

`SqlParameterValue` hoạt động cùng SQL placeholders, **không tạo SQL escaping thủ công**. Câu SQL đúng:

```java
jdbc.update(
    "UPDATE catalog_products SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, userInput),
    new SqlParameterValue(Types.BIGINT, id));
```

Câu SQL sai:

```java
// SAI: SQL injection và escaping hỏng khi nối raw input.
String sql = "UPDATE catalog_products SET note = '" +
    userInput + "' WHERE id = " + id;
jdbc.update(sql);
```

Hai snippet ở context method đã có `jdbc`/`userInput`/`id`, không phải file Java độc lập. SQL type metadata **không bảo vệ** nếu lập trình viên bỏ placeholder rồi ghép chuỗi SQL. Tên table/column không bind được như scalar values; nếu cần dynamic SQL, dùng allowlist các identifier.

### 17.2. Không giả định khai báo SQL type luôn cải thiện hiệu năng

- Type metadata giúp một số driver/backend xác định đúng kiểu, tránh lỗi chuyển đổi hoặc execution plan bất ngờ.
- Nhưng lợi ích hiệu năng phụ thuộc schema, index, cách database tối ưu câu SQL, driver và phân phối dữ liệu.
- Chọn type sai (ví dụ bind VARCHAR trong so sánh với indexed numeric column) đôi khi **làm tăng cast/giảm index utilization**, tùy optimizer.
- Đo query plan/latency với DB thực tế, đừng “tối ưu” bằng cách bọc mọi parameter mà không đo.

### 17.3. Không ghi giá trị nhạy cảm vào log

SQL type declaration có thể được log cho chẩn đoán, nhưng **giá trị** như token, email, nội dung note, số tài khoản không nên log trần. Khi debug “type mismatch”, log tên field và mã JDBC type, correlation ID, SQL operation an toàn; hạn chế SQL đầy đủ chứa dữ liệu nhạy cảm.

## 18. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Nhầm `Types` với lớp/kiểu Java.**

`Types.VARCHAR` là `int`, không phải `String.class`. Khi bind, vẫn cung cấp object giá trị và mã JDBC type tương ứng.

**Lỗi 2 — Truyền `null` và mặc định driver luôn biết kiểu.**

`jdbc.update(sql, (Object) null)` có thể thành công ở DB này nhưng sai ở DB khác. Khi schema/driver cần, dùng `new SqlParameterValue(Types.VARCHAR, null)` hoặc mảng argTypes/named SQL type.

**Lỗi 3 — Dùng `Types.NULL` cho mọi trường nullable.**

`Types.NULL` là generic NULL code. Nếu SQL parameter thuộc cột VARCHAR/DECIMAL/DATE, nên khai báo SQL type tương ứng khi cần.

**Lỗi 4 — Đảo thứ tự constructor scale.**

Đúng: `new SqlParameterValue(Types.DECIMAL, 2, new BigDecimal("10.20"))`. Scale là **tham số thứ hai** ở overload có ba đối số `(int sqlType, int scale, Object value)`. Không phải `new SqlParameterValue(value, Types.DECIMAL)`.

**Lỗi 5 — Dùng mảng types sai thứ tự.**

`Object[]{note, id}` phải đi cùng `int[]{Types.VARCHAR, Types.BIGINT}` khi SQL là `SET note = ? WHERE id = ?`. Một mảng types không bám đúng thứ tự có thể tạo lỗi khó phát hiện.

**Lỗi 6 — Chỉ đăng ký type, không đăng ký value.**

`MapSqlParameterSource.registerSqlType("note", Types.VARCHAR)` không nhất thiết cấp giá trị cho `:note`. Với MapSqlParameterSource, dùng `addValue("note", null, Types.VARCHAR)` nếu muốn bind NULL.

**Lỗi 7 — Nhầm SQL NULL với chuỗi "null" hoặc số 0.**

Chúng có ý nghĩa khác nhau. Test bằng `IS NULL` khi cần, không chỉ so sánh chuỗi từ ResultSet.

**Lỗi 8 — Dùng `WHERE col = ?` với typed null và kỳ vọng trả row NULL.**

Typed binding không đổi logic ba giá trị SQL. Viết `IS NULL`/null-safe predicate phù hợp.

**Lỗi 9 — Coi scale trong SqlParameterValue là validation.**

Phải kiểm tra BigDecimal, currency policy, precision/scale của schema trước ghi; đọc lại dữ liệu để phát hiện làm tròn ngoài ý muốn.

**Lỗi 10 — Cho rằng `Types.OTHER` portable với JSON/UUID.**

Phải xem tài liệu driver, tên kiểu/cast và test DB thật.

**Lỗi 11 — Trộn typed wrapper với overload `int[] argTypes` mà không rõ contract.**

Chọn một cơ chế khai báo SQL type theo đúng overload đã được Spring hỗ trợ.

**Lỗi 12 — Coi typed null là giá trị bị bỏ qua trong UPDATE.**

`SET note = ?` với typed null **xóa giá trị thành SQL NULL**; không có nghĩa “giữ nguyên note”. Định nghĩa riêng semantics PATCH.

## 19. Checklist trước khi merge repository code

- [ ] Từng SQL placeholder `?` có giá trị đúng thứ tự; named param có tên đúng trong SQL.
- [ ] Khi cần type, đã chọn mã `java.sql.Types` phản ánh kiểu SQL thực tế.
- [ ] Nullable parameter được bind rõ, ví dụ `SqlParameterValue(Types.VARCHAR, null)`.
- [ ] Không dùng `Types.NULL` như một “kiểu cột” thay cho VARCHAR/DECIMAL/DATE.
- [ ] Giá trị tiền/DECIMAL dùng BigDecimal và policy precision/scale/range được xác định.
- [ ] Nếu truyền `Object[] args` và `int[] argTypes`, chúng cùng độ dài và cùng thứ tự với dấu `?`.
- [ ] Nếu dùng named parameters, typed null được đăng ký với `MapSqlParameterSource.addValue(..., sqlType)` hoặc SqlParameterSource tương ứng.
- [ ] Không dùng `Map.of` cho một map có giá trị null.
- [ ] Không nhầm kiểu Java, JDBC type code, datatype/constraint của database.
- [ ] Không nhầm bind typed null với tìm dữ liệu NULL bằng `WHERE col = NULL`.
- [ ] Không ghép user input vào SQL; vẫn dùng PreparedStatement placeholders.
- [ ] Mọi kiểu đặc thù như UUID/JSONB/ARRAY/LOB đã kiểm chứng theo driver.
- [ ] Có integration test các giá trị non-null, null, precision/scale và constraint violation.
- [ ] Lỗi SQL/driver được truyền và xử lý, không biến thành “không có dữ liệu” giả.

## 20. Kết luận

**`SqlParameterValue` đóng gói một tham số đầu vào cùng JDBC SQL type và metadata tùy chọn**, cho phép `JdbcTemplate` bind giá trị chính xác hơn khi suy luận tự động chưa đủ — đặc biệt với **SQL NULL** và **DECIMAL/NUMERIC scale**. `java.sql.Types` là hệ **mã kiểu JDBC**, không phải kiểu Java hoặc quy tắc xác thực dữ liệu.

Ba hướng cơ bản là: **bọc từng giá trị bằng `SqlParameterValue`**, **truyền song song `Object[] args` / `int[] argTypes`**, hoặc **khai báo typed named parameter bằng `MapSqlParameterSource`/`SqlParameterSource`**. Chọn hướng dễ đọc nhất với API hiện dùng, đảm bảo thứ tự/kiểu khớp schema, giữ việc bind qua placeholder, và kiểm thử trên driver/database thật.

Thông tin type **không thay thế** SQL semantics, database constraints hoặc business validation: typed NULL vẫn là NULL, `= NULL` vẫn không là TRUE, numeric scale vẫn phải được kiểm soát, và vendor-specific types vẫn cần cách bind phù hợp.

## Tài liệu tham khảo chính thức

- Spring Framework — Providing SQL Type Information for Parameters: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework 6.2 — `SqlParameterValue` API và constructor: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html
- Spring Framework 6.2 — `JdbcTemplate` API (typed arguments): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework 6.2 — `MapSqlParameterSource` addValue và sqlType: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Oracle Java SE 17 — `java.sql.Types` hằng số JDBC chuẩn: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html
