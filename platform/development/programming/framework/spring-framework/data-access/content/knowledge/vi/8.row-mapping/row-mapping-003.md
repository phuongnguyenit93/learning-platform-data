# Đọc theo tên cột, bí danh hoặc vị trí

## 1. Mục tiêu và bối cảnh

Bài này thuộc nhóm **Ánh xạ kết quả** của Spring Framework Data Access. Sau khi thực thi `SELECT`, JDBC trả về `ResultSet`; trong Spring JDBC, `JdbcTemplate` thường chuyển từng dòng vào `RowMapper<T>`. Vấn đề cốt lõi là: **lấy đúng cột trong mỗi dòng** bằng tên cột, bí danh SQL hoặc vị trí. Sai cách có thể gây đọc nhầm khóa chính khi JOIN, mapping sai kiểu, hoặc lỗi chỉ xuất hiện sau khi ai đó đổi thứ tự `SELECT`.

Bạn sẽ học:

1. Hai overload JDBC `getXxx(String columnLabel)` và `getXxx(int columnIndex)` cùng ý nghĩa khác nhau của tên cột vật lý và **column label**.
2. Sử dụng `AS` để đặt alias duy nhất và tạo hợp đồng rõ ràng giữa truy vấn SQL với Java DTO/record.
3. Quy tắc **column index bắt đầu từ 1**, khác `rowNum` (bắt đầu từ 0) của `RowMapper`.
4. Khi nào nên đọc qua tên/alias, khi nào vị trí là lựa chọn hợp lý, và rủi ro của `SELECT *`.
5. Cách kiểm tra `ResultSetMetaData.getColumnLabel`, `getColumnName`, `getColumnCount`; xử lý SQL `NULL` và kiểu dữ liệu.
6. Mối liên hệ với `RowMapper`, `BeanPropertyRowMapper`, `DataClassRowMapper`, `queryForList` và ánh xạ dạng `Map`.
7. Ví dụ **Java 17 + Spring Framework + H2 chạy độc lập** để kiểm chứng cách đọc và kết quả.

Bài tập trung vào **lựa chọn cột và ánh xạ kết quả**, không đi sâu vào tối ưu truy vấn, lifecycle pool hoặc ranh giới transaction.

## 2. JDBC thực sự cung cấp hai cách định vị cột

Giả sử SQL xuất ba cột:

```sql
SELECT id, full_name, age
FROM customers
WHERE id = ?;
```

Trong một `ResultSet` đã được đưa đến dòng hợp lệ:

```java
long id1 = rs.getLong("id");
String name1 = rs.getString("full_name");
int age1 = rs.getInt("age");

long id2 = rs.getLong(1);
String name2 = rs.getString(2);
int age2 = rs.getInt(3);
```

Đây là **snippet trong callback/JDBC code đã có biến `rs`**, không phải file Java độc lập. Hai nhóm getter tương ứng:

- **Theo chuỗi** `getXxx(String columnLabel)`: JDBC tìm một cột theo **nhãn kết quả**. Nhãn này được lấy từ alias khi SQL có `AS`; nếu không, thường là tên cột.
- **Theo số nguyên** `getXxx(int columnIndex)`: JDBC tìm cột theo **vị trí trong select-list**. Chỉ số đầu tiên là **1**, không phải 0.

Cách viết “đọc theo tên cột” và “đọc theo alias” thực chất **đều sử dụng getter theo `String columnLabel`**, không phải hai loại API khác nhau. Alias là một cách đặt **label** cho cột truy vấn.

### Bảng ví dụ nhanh

| Select-list SQL | Label ở cột 1 | Label ở cột 2 | Lệnh đọc đúng |
| --- | --- | --- | --- |
| `SELECT id, name` | `id` | `name` | `getLong("id")` hoặc `getLong(1)` |
| `SELECT name, id` | `name` | `id` | `getLong(2)` |
| `SELECT id AS user_id, name AS display_name` | `user_id` | `display_name` | `getString("display_name")` |
| `SELECT COUNT(*) AS total` | `total` | Không có | `getLong("total")` hoặc `getLong(1)` |

Bảng này dùng tên label theo cách diễn đạt SQL; case chính xác mà metadata trả về phụ thuộc database/driver và cách quote alias. Không thiết kế code dựa vào việc mọi driver hiển thị label với đúng chữ hoa/chữ thường như SQL được gõ.

## 3. Phân biệt tên cột, bí danh SQL và JDBC column label

Ba khái niệm:

1. **Physical column name:** tên cột định nghĩa trong schema, ví dụ `customers.full_name`.
2. **SQL alias:** tên đặt trong `SELECT` bằng `AS`, ví dụ `full_name AS display_name`.
3. **Column label:** tên do JDBC công bố cho từng cột trong result set và nhận vào `getXxx(String columnLabel)`.

Ví dụ:

```sql
SELECT c.id AS customer_id,
       c.full_name AS display_name
FROM customers c
WHERE c.id = ?;
```

Mapper đúng:

```java
CustomerView customer = new CustomerView(
        rs.getLong("customer_id"),
        rs.getString("display_name"));
```

Đây là snippet nằm trong `RowMapper`; class/record `CustomerView` phải được ứng dụng định nghĩa.

**Không viết mapper phụ thuộc vào việc `rs.getString("full_name")` vẫn tìm được cột sau khi SQL đã đổi label thành `display_name`.** Một số driver có hành vi hỗ trợ tra cứu bằng physical name sau alias, nhưng đó không phải hợp đồng portable nên dựa vào. Hãy dùng label thực tế do `SELECT` xuất ra.

### Alias không thay đổi schema

`AS display_name` chỉ thay **tên biểu diễn trong result set**; nó không đổi tên `full_name` trong bảng. Nhờ đó, ứng dụng có thể giữ giao diện mapping ổn định khi schema được đổi và truy vấn có thể bảo tồn alias:

```sql
-- Trước migration:
SELECT full_name AS display_name FROM customers;

-- Sau migration đổi cột:
SELECT legal_name AS display_name FROM customers;
```

Nếu business meaning hoặc kiểu dữ liệu đổi, mapper vẫn cần được đánh giá lại; alias chỉ giải quyết vấn đề **tên**.

## 4. RowMapper trong Spring JdbcTemplate

`JdbcTemplate.query(...)` có thể nhận một `RowMapper<T>`:

```java
List<Customer> customers = jdbcTemplate.query(
        "SELECT id, name FROM customers ORDER BY id",
        (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("name")));
```

Spring tự mở/đóng `ResultSet`, chuyển con trỏ sang từng dòng và gọi `mapRow(rs, rowNum)`. Mapper chỉ đọc dữ liệu **trên dòng hiện tại** và trả object Java.

Quy tắc:

- **Không gọi `rs.next()`** trong `RowMapper`: template đã điều khiển việc duyệt dòng.
- **Không gọi `rs.close()`** trong mapper: resource do template quản lý.
- `rowNum` là số thứ tự **dòng** từ **0**, còn `getLong(1)` dùng vị trí **cột** từ **1**.
- Mapper phải trả DTO/record hoặc dữ liệu đã tách khỏi result set; không trả raw `ResultSet` để dùng sau khi query hoàn tất.
- Getter có thể ném `SQLException`; để Spring JDBC xử lý/dịch exception thay vì nuốt lỗi và trả kết quả sai.

**Ví dụ sai:**

```java
// SAI: không dùng đoạn này trong ứng dụng.
(rs, rowNum) -> {
    rs.next();                       // Skip dòng do JdbcTemplate điều khiển.
    return rs.getString(rowNum);     // rowNum=0 ở dòng đầu, nhưng index cột từ 1.
}
```

Đừng trộn lẫn vấn đề **cột nào cần đọc** với vấn đề **ai quản lý cursor**.

## 5. Đọc theo tên cột: rõ ràng và ít phụ thuộc thứ tự

Nếu SQL có:

```sql
SELECT id, name, reward_points
FROM customers
WHERE id = ?;
```

thì mapper theo tên có thể là:

```java
RowMapper<CustomerDetails> mapper = (rs, rowNum) ->
        new CustomerDetails(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getInt("reward_points"));
```

Ưu điểm:

- Dễ đối chiếu SQL với Java.
- Đổi thứ tự `SELECT` mà giữ label thì mapper thường vẫn đúng.
- Review thấy được ý nghĩa trường đang đọc.
- Hạn chế nhầm cột sau khi thêm field mới.

Hạn chế:

- Khi SQL đổi alias, mapper cũng phải được sửa hoặc contract alias được bảo toàn.
- JOIN có hai cột cùng tên `id` khiến `getLong("id")` mơ hồ.
- Đây vẫn là chuỗi trong Java: compiler không biết label có thật hay không. Cần integration test chạy query thật.

Với query dùng một mapper tái sử dụng, có thể đặt hằng số tên label; nhưng hằng số không tự kiểm tra SQL có xuất đúng label. Không nên thiết kế một mapper mặc định giả định mọi query đều trả `id`/`name` nếu một số query đã đổi thành `customer_id`/`display_name`.

## 6. Dùng AS để tránh xung đột tên sau JOIN

Giả sử:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL
);

CREATE TABLE purchases (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL
);
```

Query nguy hiểm:

```sql
SELECT c.id, p.id, c.name, p.amount_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Result set có **hai label `id`**. Gọi `rs.getLong("id")` thường lấy **cột khớp đầu tiên**, không tự hiểu bạn muốn `p.id` hay `c.id`. Nếu thay thứ tự `SELECT`, code có thể đọc giá trị khác mà không có lỗi biên dịch.

Sửa bằng alias riêng:

```sql
SELECT p.id AS purchase_id,
       c.id AS customer_id,
       c.name AS buyer_name,
       p.amount_cents AS total_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Đọc:

```java
PurchaseView purchase = new PurchaseView(
        rs.getLong("purchase_id"),
        rs.getLong("customer_id"),
        rs.getString("buyer_name"),
        rs.getLong("total_cents"));
```

**Nguyên tắc:** mỗi cột cần ánh xạ vào một ý nghĩa riêng phải có **label riêng**. Không chỉ đổi `getLong("id")` sang `getLong(2)` để che vấn đề: index 2 không mơ hồ hôm nay nhưng dễ lệch khi chỉnh select-list.

### Biểu thức và aggregate

Các kết quả tính toán cũng nên có alias tường minh:

```sql
SELECT COUNT(*) AS purchase_count,
       COALESCE(SUM(amount_cents), 0) AS total_cents
FROM purchases
WHERE customer_id = ?;
```

Mapper có thể đọc:

```java
long count = rs.getLong("purchase_count");
long cents = rs.getLong("total_cents");
```

Không có alias, metadata của biểu thức `COUNT(*)`, `SUM(...)` hoặc phép tính phức tạp có thể mang label khó đoán/không portable. Alias là phần công khai của **hợp đồng kết quả SQL**.

## 7. Đọc theo vị trí: chỉ đúng khi biết select-list chính xác

Đây là SQL:

```sql
SELECT id, name FROM customers;
```

Vì `id` ở cột đầu và `name` ở cột thứ hai:

```java
(rs, rowNum) -> new Customer(
        rs.getLong(1),
        rs.getString(2))
```

Nếu SQL đổi thành:

```sql
SELECT name, id FROM customers;
```

mapper phải đổi thành:

```java
(rs, rowNum) -> new Customer(
        rs.getLong(2),
        rs.getString(1))
```

**Index là vị trí trong kết quả, không phải ordinal trong định nghĩa bảng.** Index 0 không hợp lệ. Nếu câu SQL chỉ có hai cột, index 3 cũng không hợp lệ. Sự khác biệt này có thể tạo lỗi khó phát hiện khi getter nhận kiểu có thể chuyển đổi: ví dụ cột mới là số nhưng mapper vẫn `getString(2)` và không báo lỗi, dù giá trị đã sai nghiệp vụ.

### Khi dùng index là hợp lý

- Query một cột: `SELECT COUNT(*) ...`, `getLong(1)` rất rõ.
- Projection chỉ một-hai cột được kiểm soát hoàn toàn, mã mapper gần sát SQL.
- Code cần tránh lookup label trong một tác vụ được profiling chứng minh là quan trọng; **đừng tự giả định index luôn nhanh hơn đáng kể**, vì hiệu năng phụ thuộc driver và thường chi phí SQL/network mới là yếu tố chính.

Với query nhiều cột, JOIN hoặc mapper được dùng lại cho nhiều SQL, alias/tên thường dễ bảo trì hơn.

## 8. So sánh ba cách nhìn ở mức thiết kế

| Tiêu chí | Đọc theo tên không alias | Đọc theo alias | Đọc theo vị trí |
| --- | --- | --- | --- |
| Java | `getString("name")` | `getString("buyer_name")` | `getString(2)` |
| SQL phù hợp | `SELECT name` | `SELECT name AS buyer_name` | `SELECT id, name` |
| Đổi thứ tự select-list | Ít ảnh hưởng | Ít ảnh hưởng | **Dễ lệch** |
| Đổi tên cột vật lý | Mapper có thể phải sửa | Có thể giữ alias ổn định | Chỉ số vẫn đúng nếu vị trí/kiểu giữ |
| JOIN trùng `id` | Mơ hồ | **Nên có alias duy nhất** | Đọc được nhưng khó review |
| Biểu thức tổng hợp | Khó dựa vào tên mặc định | Nên alias | Đọc cột đầu nếu biết vị trí |
| Dùng cho DTO | Được nếu tên ổn định | Rõ hợp đồng nhất | Gắn chặt thứ tự SQL |
| Rủi ro | Thiếu/đổi label, trùng label | Alias SQL và Java không đồng bộ | Thứ tự đổi mà code không đổi |

Không có một giải pháp duy nhất cho mọi trường hợp; chọn dựa trên **độ phức tạp và độ ổn định của projection**. Với ứng dụng nghiệp vụ nhiều JOIN/DTO, alias rõ ràng là mặc định đáng tin hơn.

## 9. JDBC metadata: nhìn thấy hợp đồng thực tế

`ResultSetMetaData` cho biết:

- `getColumnCount()`: số cột trả về.
- `getColumnLabel(i)`: tên hiển thị/label, ưu tiên alias `AS` khi có.
- `getColumnName(i)`: tên cột theo JDBC metadata; thường là tên schema cho cột thật, nhưng tùy driver/query và có thể không hữu ích với biểu thức.
- `getColumnType(i)` / `getColumnTypeName(i)`: loại dữ liệu SQL.
- `getTableName(i)`: tên bảng gốc nếu driver cung cấp được, không phải lúc nào cũng có giá trị.

Đoạn minh họa bên trong `ResultSetExtractor`:

```java
int columnCount = rs.getMetaData().getColumnCount();
for (int i = 1; i <= columnCount; i++) {
    System.out.println(
            "index=" + i
            + ", label=" + rs.getMetaData().getColumnLabel(i)
            + ", name=" + rs.getMetaData().getColumnName(i));
}
```

**Dừng đúng:** vòng lặp index chạy từ 1 đến `columnCount`, không từ 0. Nếu SQL có `SELECT name AS "display_name"`, metadata label trên H2 có thể giữ nguyên chuỗi chữ thường `display_name` nhờ quoted identifier. Với alias không quote, H2 thường normalizes thành chữ hoa; PostgreSQL thường thành chữ thường. Đừng suy từ ví dụ H2 rằng mọi driver giữ case nguyên văn.

Nếu một label bị thiếu, đừng sửa code bằng cách “đoán tên khác” nếu chưa xác minh select-list và metadata. Ghi nhận đúng label/kiểu rồi cập nhật query hoặc mapper một cách có chủ đích.

## 10. Quy tắc về chữ hoa/chữ thường và alias quote

Trong câu:

```sql
SELECT name AS display_name FROM customers;
```

database có thể thay đổi case của identifier khi không có dấu quote. JDBC tìm column label thông thường không phân biệt case, nhưng **chuỗi hiển thị** trong `getColumnLabel` có thể không khớp cách bạn gõ.

SQL tiêu chuẩn cho quoted alias:

```sql
SELECT name AS "display_name" FROM customers;
```

Một số hệ quản trị có quy tắc quoting khác (`backtick`, `[brackets]` hoặc chế độ SQL). Hãy ưu tiên alias đơn giản như `customer_id`, `buyer_name` và kiểm tra trên DB dùng thật.

**Tránh thiết kế hai alias chỉ khác case** như `id` và `ID`; nhiều driver có lookup case-insensitive nên không bảo đảm chúng có thể được truy cập phân biệt qua `getXxx(String)`. Nếu cần hai trường khác nhau, đặt label khác nghĩa.

## 11. SQL NULL và getter kiểu nguyên thủy

Lấy đúng cột vẫn chưa đủ nếu cột chứa `NULL`. JDBC getter kiểu primitive trả giá trị mặc định khi dữ liệu SQL là NULL:

- `getInt` / `getLong` → 0;
- `getDouble` → 0.0;
- `getBoolean` → false.

Để phân biệt `NULL` và giá trị hợp lệ bằng 0/false, gọi `rs.wasNull()` **ngay sau getter cần kiểm tra**:

```java
int points = rs.getInt("reward_points");
Integer nullablePoints = rs.wasNull() ? null : points;
```

Nếu bạn gọi thêm `rs.getString("name")` rồi mới `wasNull()`, kết quả phản ánh getter **mới nhất**, không còn phản ánh `reward_points`.

Các getter dạng object thường có khả năng trả `null`, ví dụ `getString(...)` hoặc `getObject("reward_points", Integer.class)` trên driver hỗ trợ. Khi tạo DTO record, chọn `Integer`/`Long` nếu có nghĩa **chưa có dữ liệu**, thay vì `int`/`long`; nếu nghiệp vụ cho phép mặc định 0 thì đặt quy tắc chuyển đổi rõ ràng.

Kiểu dữ liệu cũng quan trọng:

- `BIGINT` → `long/Long` nếu trong phạm vi;
- `VARCHAR` → `String`;
- `DECIMAL` → `BigDecimal` cho tiền tệ/thập phân chính xác;
- `DATE/TIMESTAMP` → API Java time phù hợp với driver và timezone;
- `SUM(...)` có thể trả loại rộng hơn cột đầu vào: kiểm tra trên DB thật.

Đặt alias không tự động ép kiểu hoặc loại bỏ `NULL`.

## 12. Ví dụ hoàn chỉnh: Java 17 + Spring JdbcTemplate + H2

Ứng dụng sau dùng **Spring Framework 6.2.14**, **H2 2.3.232** và **Java 17+**, chạy bằng Gradle. Nó có thể chạy như ứng dụng Java độc lập, không cần Spring Boot hay database bên ngoài. `DriverManagerDataSource` trong ví dụ không có pooling và chỉ dùng để minh họa.

### 12.1. Cấu trúc

```text
column-lookup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ColumnLookupDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'column-lookup-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}
application {
    mainClass = 'demo.ColumnLookupDemo'
}
```

`src/main/java/demo/ColumnLookupDemo.java`:

```java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class ColumnLookupDemo {

    record Customer(long id, String name) {}
    record Purchase(long id, String buyer, long cents) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:lookup_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE customers (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(80) NOT NULL,
                        reward_points INT
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE purchases (
                        id BIGINT PRIMARY KEY,
                        customer_id BIGINT NOT NULL,
                        amount_cents BIGINT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO customers (id, name) VALUES (?, ?)",
                    1L, "Lan");
            jdbc.update("INSERT INTO customers (id, name) VALUES (?, ?)",
                    2L, "Minh");
            jdbc.update("""
                    INSERT INTO purchases (id, customer_id, amount_cents)
                    VALUES (?, ?, ?)
                    """, 101L, 1L, 25_000L);
            jdbc.update("""
                    INSERT INTO purchases (id, customer_id, amount_cents)
                    VALUES (?, ?, ?)
                    """, 102L, 1L, 40_000L);

            // A: Theo tên cột khi SQL không có AS.
            Customer byName = jdbc.queryForObject(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong("id"),
                            rs.getString("name")),
                    1L);
            System.out.println("byName=" +
                    byName.id() + ":" + byName.name());

            // B: Theo vị trí 1-based.
            Customer byIndex = jdbc.queryForObject(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong(1),
                            rs.getString(2)),
                    1L);
            System.out.println("byIndex=" +
                    byIndex.id() + ":" + byIndex.name());

            // C: Đổi SELECT thành name, id thì đổi vị trí getter.
            Customer reordered = jdbc.queryForObject(
                    "SELECT name, id FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong(2),
                            rs.getString(1)),
                    1L);
            System.out.println("reordered=" +
                    reordered.id() + ":" + reordered.name());

            // D: JOIN có alias riêng để không nhầm id giữa các bảng.
            Purchase joined = jdbc.queryForObject("""
                    SELECT p.id AS purchase_id,
                           c.name AS buyer_name,
                           p.amount_cents AS total_cents
                    FROM purchases p
                    JOIN customers c ON c.id = p.customer_id
                    WHERE p.id = ?
                    """,
                    (rs, rowNum) -> new Purchase(
                            rs.getLong("purchase_id"),
                            rs.getString("buyer_name"),
                            rs.getLong("total_cents")),
                    101L);
            System.out.println("joined=" + joined.id() +
                    ":" + joined.buyer() + ":" + joined.cents());

            // E: SQL aggregate có alias rõ ràng.
            Long total = jdbc.queryForObject("""
                    SELECT COALESCE(SUM(amount_cents), 0) AS total_cents
                    FROM purchases
                    WHERE customer_id = ?
                    """,
                    (rs, rowNum) -> rs.getLong("total_cents"),
                    1L);
            System.out.println("sumCents=" + total);

            // F: Đọc alias thay vì tên cột vật lý.
            List<String> names = jdbc.query(
                    "SELECT name AS display_name FROM customers ORDER BY id",
                    (rs, rowNum) -> rs.getString("display_name"));
            System.out.println("names=" + names);

            // G: getColumnLabel thể hiện alias đã quote trên H2.
            Boolean labelMatch = jdbc.queryForObject(
                    "SELECT name AS \"public_name\" FROM customers WHERE id = ?",
                    (rs, rowNum) ->
                            "public_name".equals(
                                    rs.getMetaData().getColumnLabel(1)),
                    1L);
            System.out.println("metadataLabel=" + labelMatch);

            // H: reward_points SQL NULL; primitive int không đủ.
            Boolean pointsNull = jdbc.queryForObject(
                    "SELECT reward_points FROM customers WHERE id = ?",
                    (rs, rowNum) -> {
                        rs.getInt("reward_points");
                        return rs.wasNull();
                    },
                    1L);
            System.out.println("pointsWasNull=" + pointsNull);
        }
    }
}
```

Tại thư mục có `build.gradle`, chạy:

```bash
gradle run
```

Với Gradle Wrapper của dự án, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Phần stdout do các câu `System.out.println` của chương trình tạo ra là:

```text
byName=1:Lan
byIndex=1:Lan
reordered=1:Lan
joined=101:Lan:25000
sumCents=65000
names=[Lan, Minh]
metadataLabel=true
pointsWasNull=true
```

Các log của Gradle/Spring có thể xuất hiện thêm. **Giải thích:**

1. `byName` và `byIndex` lấy cùng khách `id=1` theo hai overload.
2. `reordered` vẫn đúng do đổi index khi `SELECT` đổi thứ tự.
3. `joined` đọc `purchase_id`/`buyer_name`/`total_cents`, không nhầm khóa chính giữa bảng.
4. Hai đơn mua của Lan là 25.000 và 40.000 cents, nên `sumCents=65000`.
5. `names` đọc alias `display_name` và giữ thứ tự `ORDER BY id`.
6. `metadataLabel=true` vì H2 giữ alias có dấu nháy kép `"public_name"` theo đúng chữ thường.
7. `pointsWasNull=true` vì `reward_points` của khách id 1 chưa có giá trị SQL; `getInt` trả 0 nhưng `wasNull` phân biệt được.

Ở mỗi `RowMapper`, `JdbcTemplate` gọi callback trên dòng đã định vị, và quản lý việc đóng result set/statement/connection sau đó.

### 12.2. Tự đổi câu SQL để thấy rủi ro

- Đổi `SELECT id, name` ở case B thành `SELECT name, id` mà không đổi mapper: phương thức `getLong(1)` sẽ nhận cột `name` và có thể ném lỗi chuyển đổi kiểu.
- Đổi `p.id AS purchase_id` thành `p.id AS order_id` ở case D mà giữ `getLong("purchase_id")`: label không còn tồn tại; test phải thất bại.
- Đổi `name AS display_name` thành `name AS buyer_name` ở case F: đổi getter tương ứng hoặc giữ alias cũ nếu muốn bảo tồn contract.
- Thêm `reward_points=0` cho khách id 1: case H phải thành `pointsWasNull=false`, phân biệt được 0 thật với NULL.
- Trong case G, thử alias không quote để quan sát sự khác biệt giữa cách viết SQL và case của metadata trên H2.

**Đừng** sử dụng các biến thể lỗi trên database production; đây là những phép thử giúp hiểu contract.

## 13. Mapping theo property: BeanPropertyRowMapper

Spring có `BeanPropertyRowMapper` để gán các cột vào JavaBean property theo tên. Nếu DTO có field `customerId` và `displayName` (với setter tương ứng), SQL nên xuất label phù hợp:

```sql
SELECT id AS customer_id,
       name AS display_name
FROM customers;
```

Ví dụ minh họa, không thuộc file runnable ở mục 12:

```java
public class CustomerDto {
    private Long customerId;
    private String displayName;

    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) {
        this.customerId = customerId;
    }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

```java
List<CustomerDto> values = jdbcTemplate.query("""
        SELECT id AS customer_id,
               name AS display_name
        FROM customers
        """, new BeanPropertyRowMapper<>(CustomerDto.class));
```

`BeanPropertyRowMapper` hỗ trợ quy ước `snake_case` → `camelCase` trong việc ghép tên. **Nó không tự suy ra** rằng physical column `id` là property `customerId` nếu không có alias phù hợp. Khi mapping không thành công, kiểm tra label thực tế trước khi nghi ngờ getter/setter.

### DataClassRowMapper và record

`DataClassRowMapper` hỗ trợ mapping dữ liệu vào constructor / Java record khi tên tham số/record component và label được đối chiếu theo quy tắc của Spring.

```java
record PurchaseDto(long purchaseId, String buyerName) {}
```

SQL:

```sql
SELECT p.id AS purchase_id,
       c.name AS buyer_name
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Snippet:

```java
List<PurchaseDto> purchases = jdbcTemplate.query(
        sql,
        new DataClassRowMapper<>(PurchaseDto.class));
```

`sql` trong đoạn này đại diện chuỗi truy vấn vừa nêu, chưa phải biến được định nghĩa trong file runnable. Với mapper tự động, nguyên tắc vẫn là **label SQL phải khớp property/constructor parameter**. Khi cần đổi kiểu, nối nhiều trường hoặc tính toán nghiệp vụ, mapper thủ công thường rõ ràng hơn.

## 14. Map, ColumnMapRowMapper và các label trùng

`JdbcTemplate.queryForList` có thể trả về `List<Map<String,Object>>`:

```java
List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
        SELECT id AS customer_id,
               name AS display_name
        FROM customers
        ORDER BY id
        """);
```

Map dùng **column label** làm key theo cơ chế của mapper, nhưng tên hiển thị case và kiểu giá trị phụ thuộc vào driver/Spring. Khi hai cột cùng label (ví dụ hai `ID`), một Map không thể đại diện hai giá trị riêng biệt cùng một key; một giá trị có nguy cơ bị ghi đè/không thể truy cập như mong đợi.

Vì vậy:

- Cần **label duy nhất** cho các field khác nhau, đặc biệt khi JOIN.
- Đừng dựa vào case (`id` và `ID`) làm cách phân biệt.
- Nếu API ngoài yêu cầu key JSON chính xác, map có chủ đích sang DTO hoặc tạo key rõ ràng.
- Với dữ liệu có kiểu quan trọng, `Object` trong Map có thể cần chuyển đổi; đừng tự giả định mọi `BIGINT` luôn được Java driver trả dưới cùng một class khi dùng `getObject`.

Khi đọc một giá trị duy nhất, dùng overload kiểu scalar để tránh viết mapper:

```java
Long count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM customers",
        Long.class);
```

Overload này kỳ vọng kết quả một dòng, một cột; nếu không đúng kích thước result set, Spring có thể ném exception như `EmptyResultDataAccessException` hoặc `IncorrectResultSizeDataAccessException`. Không coi nó là cách đọc nhiều dòng.

## 15. Tránh SELECT * khi cần mapping lâu dài

```sql
SELECT *
FROM customers c
JOIN purchases p ON p.customer_id = c.id;
```

Vấn đề:

1. Có thể có hai cột `id` với label trùng.
2. Khi schema thay đổi, số cột trong `SELECT *` cũng thay đổi.
3. Mapper theo index có thể đọc sai cột sau migration.
4. Query kéo dữ liệu không cần thiết, dễ tăng truyền tải/chi phí.
5. Mapping tự động và Map khó phân biệt các field cùng label.

Làm rõ projection:

```sql
SELECT p.id AS purchase_id,
       c.id AS customer_id,
       c.name AS buyer_name,
       p.amount_cents AS amount_cents
FROM purchases p
JOIN customers c ON c.id = p.customer_id;
```

Khi thay đổi kết quả, cập nhật SQL và Java cùng một lần, kèm test. Nếu một API chung cần trả nhiều projection, đừng dùng cùng một mapper mặc định cho tất cả khi các label không giống nhau.

## 16. Bảo đảm an toàn với tên cột/alias động

Placeholders `?` của JDBC/`JdbcTemplate` dùng để bind **giá trị dữ liệu**:

```sql
SELECT id AS customer_id, name AS display_name
FROM customers
WHERE id = ?;
```

Mã gọi:

```java
Customer result = jdbcTemplate.queryForObject(
        "SELECT id AS customer_id, name AS display_name "
        + "FROM customers WHERE id = ?",
        (rs, rowNum) -> new Customer(
                rs.getLong("customer_id"),
                rs.getString("display_name")),
        selectedId);
```

Không thể dùng `?` để bind **identifier** như tên bảng, tên cột, alias, hoặc từ khóa `ASC/DESC`. Nếu cần chọn cột hoặc `ORDER BY` động, tạo allowlist các identifier được phép và chỉ ghép các giá trị từ allowlist vào SQL. Không ghép trực tiếp input tự do vào SQL chỉ vì getter cuối cùng đọc bằng label.

## 17. Lỗi phổ biến và quy trình chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Giải pháp |
| --- | --- | --- |
| `Column not found: id` | SQL dùng `id AS customer_id`, mapper vẫn `getLong("id")` | Đổi getter theo label hoặc bảo tồn label SQL |
| Kết quả có ID không đúng | JOIN có hai label `id` trùng | Alias riêng `purchase_id`, `customer_id` |
| `getLong(1)` lỗi chuyển đổi | Đổi `SELECT id,name` thành `name,id` | Đổi index hoặc đọc bằng label |
| `getString(0)` lỗi | JDBC index 1-based | Bắt đầu từ 1 |
| Mapper thiếu field | Alias không khớp JavaBean/constructor property | Kiểm tra metadata label và quy tắc mapping |
| Giá trị 0 thay vì null | `getInt`/`getLong` trên SQL NULL | `wasNull()` hoặc wrapper nullable |
| Query scalar trả exception | Không đúng 1 dòng/1 cột | Chọn overload phù hợp và xử lý empty/multiple |
| Metadata label uppercase | Database normalizes unquoted identifier | Xem quy tắc quote/driver, không đổi label tùy tiện |
| Map mất field khi JOIN | Column label trùng | Đặt alias duy nhất |
| `ResultSet closed` | Trả raw result set ra khỏi callback | Materialize DTO/record trong mapper |

**Quy trình debug:** đọc SQL select-list → liệt kê label mong đợi theo thứ tự → xác nhận result set metadata trên driver thật → đối chiếu từng getter/kiểu/nullable → chạy integration test cho trường hợp alias, JOIN, NULL và đổi thứ tự.

## 18. Checklist review pull request

1. Mọi cột được dùng bởi mapper đều có trong select-list?
2. Nếu có `AS`, mapper đọc bằng **alias** chứ không đoán physical name?
3. JOIN có label duy nhất cho các ID/NAME/TOTAL từ nhiều bảng?
4. Với index, bắt đầu từ 1 và vẫn đúng sau khi đổi thứ tự?
5. Mọi `RowMapper` chỉ đọc dòng hiện tại, không tự gọi `next()`/`close()`?
6. `NULL` có được giữ riêng với 0/false khi nghiệp vụ cần?
7. Getter có loại dữ liệu phù hợp, không convert tùy tiện `VARCHAR` sang số?
8. `BeanPropertyRowMapper`/`DataClassRowMapper` có tên SQL label khớp Java property/constructor?
9. `SELECT *` đã được thay bằng projection rõ ràng ở luồng quan trọng?
10. Alias động nếu có đã được validate qua allowlist?
11. Có test từ SQL thực về label/kiểu/NULL, không chỉ unit test mock mapper?
12. Các lỗi thiếu cột được phát hiện chứ không bị nuốt thành dữ liệu giả?

## 19. Bài tập thực hành

**Bài 1 — Đọc theo alias và vị trí.** Cho SQL `SELECT name AS display_name, id AS customer_id FROM customers`. Viết mapper trả record `Customer(long id, String name)` bằng **alias**; sau đó viết lại bằng **index**. Đáp án:

```java
// Theo alias
(rs, rowNum) -> new Customer(
        rs.getLong("customer_id"),
        rs.getString("display_name"))

// Theo index (name ở cột 1, id ở cột 2)
(rs, rowNum) -> new Customer(
        rs.getLong(2),
        rs.getString(1))
```

**Bài 2 — JOIN hai ID.** Từ hai bảng `purchases` và `customers`, xuất `purchase_id`, `customer_id`, `buyer_name` rồi map ra record `PurchaseCustomer(long purchaseId, long customerId, String buyerName)`. Đừng dùng `getLong("id")`.

**Bài 3 — Aggregate.** Viết `SELECT COUNT(*) AS purchase_count, COALESCE(SUM(amount_cents),0) AS total_cents FROM purchases WHERE customer_id=?`. Mapper trả đúng cả số giao dịch và tổng tiền, không phụ thuộc thứ tự các cột.

**Bài 4 — SQL NULL.** Bổ sung khách có `reward_points=0` và khách có `reward_points=NULL`. Dùng `rs.getInt` và `rs.wasNull` để xác nhận hai trường hợp khác nhau. Thử `rs.getObject("reward_points", Integer.class)` trên H2 và so sánh.

**Bài 5 — Metadata và database thật.** Trên H2, truy vấn `SELECT name AS "public_name" ...` rồi in `getColumnLabel(1)` và `getColumnName(1)`. Thử alias không quote; nếu có PostgreSQL/MySQL test, chạy lại và ghi nhận khác biệt. Đừng viết code phụ thuộc vào case/metadata chưa kiểm chứng.

## 20. Tài liệu tham khảo

- Java SE 17, `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17, `ResultSetMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSetMetaData.html
- Spring Framework 6.2, `RowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework 6.2, `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework, JDBC query APIs: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework 6.2, `BeanPropertyRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework 6.2, `DataClassRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html

**Tổng kết:** Đọc theo tên cột và alias đều là đọc theo **column label**; đọc theo vị trí là đọc theo **1-based select-list index**. Với JOIN, biểu thức và DTO dài hạn, hãy đặt alias rõ và duy nhất. Kiểm chứng SQL cùng mapper trên driver/database thực tế để tránh lỗi im lặng.