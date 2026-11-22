# Dùng Map và giới hạn suy luận khi giá trị null

## Mục tiêu và tình huống

Trong Spring JDBC, `NamedParameterJdbcTemplate` cho phép viết câu SQL với **tham số có tên** như `:id`, `:nickname`, `:minScore` thay vì phải đếm từng dấu `?`. Cách đơn giản nhất để truyền giá trị là một `Map<String, ?>`:

```java
String sql = """
        SELECT id, display_name
        FROM contacts
        WHERE tenant_id = :tenantId AND score >= :minScore
        ORDER BY id
        """;

Map<String, Object> params = Map.of(
        "tenantId", 7L,
        "minScore", 50
);

List<Contact> contacts = namedJdbc.query(sql, params, CONTACT_MAPPER);
```

Đoạn code này là **minh họa**, giả định `namedJdbc`, `CONTACT_MAPPER` và kiểu `Contact` đã được khai báo ở nơi khác. Với giá trị không null và kiểu dữ liệu đơn giản, truyền `Map` thường ngắn gọn và đủ dùng.

Nhưng có một khác biệt quan trọng giữa:

- **Có khóa trong Map, giá trị bằng `null`**;
- **Không có khóa đó trong Map**;
- **Có giá trị `null` và xác định rõ nó thuộc SQL type nào**.

Khi giá trị là `null`, bản thân đối tượng Java `null` **không chứa thông tin kiểu** để JDBC suy luận một cách chắc chắn. Đó chính là giới hạn mà bài học này giải thích.

Sau bài này, bạn có thể:

1. Dùng `Map<String, ?>` với `NamedParameterJdbcTemplate` cho các tham số đơn giản.
2. Phân biệt hành vi của `Map.of(...)`, `HashMap` và `MapSqlParameterSource` đối với giá trị `null`.
3. Hiểu vì sao một `Map` thông thường thường **không cung cấp SQL type tường minh**, và vì sao bind null có thể phụ thuộc metadata, driver hoặc DBMS.
4. Dùng `MapSqlParameterSource.addValue(name, value, sqlType)` để truyền `null` đúng kiểu như `Types.VARCHAR` hoặc `Types.INTEGER`.
5. Phân biệt **binding null** với **logic SQL `IS NULL`**; tránh hiểu sai `column = NULL`.
6. Viết, chạy và tự kiểm tra ví dụ Java 17+ dùng Spring JDBC + H2, bao gồm một Map có null, một tham số typed null và dữ liệu SQL được trả về.
7. Chọn phương án thích hợp cho optional filter, danh sách `IN` và truy vấn có nhiều tham số.

**Phạm vi:** Đây là bài thuộc nhóm *Tham số có tên* trong Spring Framework data access. Tập trung vào cách truyền giá trị, đặc biệt là `null`; không đi sâu vào mapping toàn bộ entity, distributed transaction hay tối ưu connection pool.

## 1. Từ dấu hỏi ? đến tham số có tên

Với `JdbcTemplate`, SQL thường dùng placeholder dạng vị trí:

```sql
SELECT id, display_name
FROM contacts
WHERE tenant_id = ? AND score >= ?;
```

Khi gọi, tham số phải đi **đúng thứ tự**:

```java
jdbc.query(sql, CONTACT_MAPPER, tenantId, minScore);
```

Với `NamedParameterJdbcTemplate`, cùng ý định có thể viết:

```sql
SELECT id, display_name
FROM contacts
WHERE tenant_id = :tenantId AND score >= :minScore;
```

và cung cấp các tên tương ứng:

```java
Map<String, Object> params = Map.of(
        "tenantId", tenantId,
        "minScore", minScore
);

namedJdbc.query(sql, params, CONTACT_MAPPER);
```

Các đoạn này chỉ minh họa cách dùng API và giả định các biến tương ứng đã tồn tại.

Bên trong, Spring phân tích SQL chứa `:tenantId` và `:minScore`, chuyển chúng thành các JDBC parameter markers phù hợp và bind từng giá trị. Các tham số có tên là **cú pháp do Spring xử lý**, không phải JDBC driver tự hiểu chuỗi `:tenantId`.

Một tên có thể được dùng ở nhiều chỗ trong SQL; Spring sẽ đưa giá trị tương ứng vào từng vị trí theo SQL đã phân tích. Tuy nhiên, mỗi tên tham số cần được cung cấp giá trị qua nguồn tham số. Đừng nhầm `:name` với một tên cột động: tham số vẫn đại diện **giá trị**, không thay được cấu trúc của truy vấn.

## 2. Map<String, ?> hoạt động như thế nào?

### 2.1. Map là danh sách tên và giá trị

Overload ví dụ:

```java
List<Contact> contacts =
        namedJdbc.query(sql, params, CONTACT_MAPPER);
```

với `params` là `Map<String, ?>`, Spring dùng các key làm tên tham số và value làm dữ liệu. Phù hợp khi:

- Số lượng tham số ít hoặc vừa phải;
- Giá trị có kiểu Java rõ, ví dụ `Long`, `Integer`, `String`;
- Không cần khai báo riêng SQL type, scale hay vendor type name;
- Bạn chỉ cần chuyển một nhóm tên/giá trị dùng một lần vào `query`/`update`.

Ví dụ cập nhật:

```java
String updateSql = """
        UPDATE contacts
        SET score = :score
        WHERE id = :id AND tenant_id = :tenantId
        """;

int affected = namedJdbc.update(
        updateSql,
        Map.of("score", 80, "id", 12L, "tenantId", 7L));
```

`affected` là số dòng bị tác động theo JDBC/DBMS, **không phải ID sinh tự động**. `Map.of(...)` không bảo đảm thứ tự duyệt các entry, nhưng điều đó **không quan trọng** với named parameters vì Spring tra giá trị theo **tên**, không theo thứ tự entry của Map.

### 2.2. Kiểu Map là String key, Object value — nhưng kiểu SQL vẫn là chuyện khác

`Map<String, Object>` là kiểu dữ liệu Java. Trong runtime, một value không-null có thể có class cụ thể:

```java
Map<String, Object> params = new HashMap<>();
params.put("score", Integer.valueOf(80));

System.out.println(params.get("score").getClass().getSimpleName());
// Integer
```

Đoạn trên có thể chạy như Java 17 nếu import `java.util.Map` và `java.util.HashMap`.

Tuy vậy:

- Java `Integer.class` không luôn khớp với một SQL column type duy nhất trong mọi DBMS.
- Một driver có thể chọn cách chuyển đổi dữ liệu khác khi statement sử dụng `DECIMAL`, `SMALLINT`, `BIGINT` hoặc kiểu riêng của DB.
- **Một value bằng `null` không có class runtime để đọc qua `getClass()`**. Thử `params.get("nickname").getClass()` khi nickname null sẽ gây `NullPointerException`.
- Generic type `Map<String, String>` cũng không phải metadata JDBC `Types.VARCHAR` tự động đi kèm từng giá trị: Java generics phần lớn bị xóa ở runtime, và một null value không “mang theo” kiểu generic của cột SQL.

Đối với đa số kiểu đơn giản và giá trị không-null, suy luận/thỏa thuận giữa Spring và JDBC driver thường vận hành thuận lợi. Nhưng **không nên đánh đồng thành công trong một query với việc Map luôn biết đúng SQL type**.

### 2.3. Map thiếu key và Map có key nhưng value null

Đây là hai trạng thái khác nhau:

```java
Map<String, Object> params = new HashMap<>();
params.put("nickname", null);

System.out.println(params.containsKey("nickname")); // true
System.out.println(params.get("nickname") == null);   // true
System.out.println(params.containsKey("missing"));    // false
System.out.println(params.get("missing") == null);     // true
```

`Map.get(...) == null` **không đủ** để phân biệt missing key với present-but-null. `containsKey` là cách kiểm tra thích hợp với Map hỗ trợ null.

Đối với một câu SQL dùng `:nickname`:

- Nếu **có key** `nickname` với value null: Spring có một tham số đã được cung cấp, mang giá trị SQL NULL tại lúc bind, dù SQL type có thể chưa được xác định.
- Nếu **không có key** `nickname`: không có giá trị cho tham số SQL bắt buộc; Spring có thể báo `InvalidDataAccessApiUsageException` về tham số còn thiếu trước khi chạy statement.

Đừng coi thiếu key là tương đương SQL NULL; việc thiếu key là **lỗi dữ liệu đầu vào cho query**, còn NULL là **một giá trị SQL hợp lệ** tùy cột/ngữ cảnh.

## 3. Map.of() không chấp nhận null

### 3.1. Vì sao không viết Map.of("nickname", null)?

`Map.of(...)` và `Map.ofEntries(...)` của Java tạo Map bất biến và **không chấp nhận null key hoặc null value**. Ví dụ:

```java
Map<String, String> data = Map.of("nickname", null);
```

Dòng này có thể **biên dịch**, nhưng khi chạy sẽ ném `NullPointerException` **ngay lúc tạo Map**, trước khi SQL hoặc `NamedParameterJdbcTemplate` được gọi. Đây là giới hạn của **Java Collections Factory Methods**, không phải lỗi bản thân Spring JDBC.

Khi các giá trị đều non-null, `Map.of(...)` rất tiện:

```java
Map<String, Object> params =
        Map.of("id", 42L, "score", 75, "status", "ACTIVE");
```

Nhưng nếu bất kỳ value có thể null, đừng chọn `Map.of` mà không xử lý null trước.

### 3.2. Dùng HashMap khi muốn giữ một key có null

`HashMap` cho phép null value:

```java
Map<String, Object> params = new HashMap<>();
params.put("id", 42L);
params.put("nickname", null);

System.out.println(params.containsKey("nickname")); // true
```

Đây là một cách **hợp lệ về cấu trúc Map** khi dùng named parameters, ví dụ:

```java
namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

Tuy nhiên, câu `UPDATE` này còn có vấn đề về **SQL type của tham số null** (phân tích ở phần tiếp theo). `HashMap` giải quyết việc **lưu null trong Map**, chứ không tự giải quyết việc **khai báo kiểu SQL cho null**.

Ngoài `HashMap`, có những cách xây Map cho phép null, nhưng cần đọc hợp đồng cụ thể của implementation. **Đừng suy diễn từ interface `Map` rằng mọi implementation đều chấp nhận null.**

### 3.3. Không sửa một Map.of đã tạo

`Map.of` trả Map không thể chỉnh sửa bằng `put` hoặc `remove`:

```java
Map<String, Integer> values = Map.of("score", 100);
// values.put("score", 200); // UnsupportedOperationException
```

Dòng được comment là ví dụ tình huống lỗi runtime. Nếu muốn build danh sách tham số có điều kiện, có thể dùng `HashMap`, nhưng hãy tạo **Map mới cho mỗi lần gọi repository** để tránh dùng chung mutable state giữa các request. Với tham số null cần type, `MapSqlParameterSource` thường là phương án rõ ràng hơn.

## 4. Tại sao null khiến suy luận SQL type khó hơn?

### 4.1. Giá trị không-null có dấu hiệu về Java type

Giả sử câu SQL:

```sql
UPDATE contacts SET score = :score WHERE id = :id;
```

Với:

```java
Map<String, Object> params =
        Map.of("score", 80, "id", 7L);
```

value của `score` là `Integer`, `id` là `Long`. Spring/JDBC driver có thêm tín hiệu khi chọn kiểu bind, và database cũng có thể suy luận từ cột/biểu thức SQL.

Đến khi `nickname = null`, không có object `String` để Spring nhận diện. Câu SQL có thể cho phép database xác định type vì nó đang gán vào cột `VARCHAR`, **nhưng không phải mọi vị trí của null và mọi driver đều suy luận đáng tin cậy**.

### 4.2. Map thường không có metadata SQL type

Ví dụ:

```java
Map<String, Object> params = new HashMap<>();
params.put("nickname", null);
params.put("id", 7L);
```

Map có key và value, **không có entry riêng để nói `nickname` là JDBC `Types.VARCHAR`**. Khi Spring đưa Map vào `NamedParameterJdbcTemplate`, nó có thể bọc Map dưới dạng `MapSqlParameterSource`, nhưng nếu không đăng ký SQL type thì type của tham số vẫn là unknown theo hợp đồng `SqlParameterSource`.

Khi bind một unknown-type null, Spring có logic hỗ trợ như hỏi `PreparedStatement.getParameterMetaData()`, lựa chọn `setNull` với SQL type fallback hoặc đường xử lý đặc thù driver/database. Cơ chế cụ thể có thể khác giữa phiên bản Spring, DBMS, driver và cấu hình. Do đó:

- Trên H2, một câu đơn giản có thể chạy ổn với `null` chưa có type tường minh;
- Trên PostgreSQL, Oracle, SQL Server hoặc một biểu thức kiểu `:value IS NULL`, hành vi/chi phí có thể khác;
- Việc chạy ổn trong môi trường test không bảo đảm type null sẽ được suy luận giống trên production;
- Nếu đã **biết kiểu cột SQL**, hãy cung cấp metadata đó trực tiếp khi null là một nhánh bình thường của nghiệp vụ.

Không nên kết luận “Map + null luôn lỗi” hoặc “Map + null luôn an toàn”. Cả hai đều là khẳng định quá mức.

### 4.3. Giải pháp được ưu tiên: MapSqlParameterSource có SQL type

Spring cung cấp `org.springframework.jdbc.core.namedparam.MapSqlParameterSource`. Ngoài value, nó cho phép khai báo **SQL type theo tên tham số**:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("id", 7L, Types.BIGINT);

int changed = namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

Đây là đoạn minh họa với `namedJdbc` hợp lệ.

Khác biệt quan trọng nằm ở `addValue("nickname", null, Types.VARCHAR)`:

- Tên tham số: `nickname`;
- Giá trị: `null` (SQL NULL);
- SQL type: `java.sql.Types.VARCHAR` (tương ứng với kiểu cột mong muốn).

`Types.VARCHAR` **không có nghĩa là gắn chuỗi ký tự "null"**. Nó hướng dẫn binding một **giá trị NULL thuộc loại VARCHAR**. Nếu cột là `INTEGER`, dùng `Types.INTEGER`; nếu là `BIGINT`, dùng `Types.BIGINT`; nếu là `TIMESTAMP`, dùng `Types.TIMESTAMP`, v.v. Khi DB có kiểu vendor-specific (ví dụ PostgreSQL enum/UUID), có thể cần type name/`Types.OTHER` hoặc cấu hình driver cụ thể, và nên có integration test trên database thật.

### 4.4. addValue overload và registerSqlType

Những dạng thường dùng:

```java
var params = new MapSqlParameterSource()
        .addValue("id", 7L)                      // type chưa chỉ rõ
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("score", 80, Types.INTEGER);
```

`addValue(String, Object)` lưu giá trị. `addValue(String, Object, int)` lưu giá trị và SQL type. Có overload nhận thêm `typeName` cho những trường hợp driver/DBMS yêu cầu vendor type name.

Cũng có thể tạo từ Map và **đăng ký type sau**:

```java
Map<String, Object> values = new HashMap<>();
values.put("id", 7L);
values.put("nickname", null);

MapSqlParameterSource params = new MapSqlParameterSource(values);
params.registerSqlType("nickname", Types.VARCHAR);
params.registerSqlType("id", Types.BIGINT);
```

Điểm then chốt: `MapSqlParameterSource` implements `SqlParameterSource`, cung cấp `getValue(name)` và `getSqlType(name)` cho Spring, trong khi `Map<String, ?>` thuần chủ yếu chỉ cung cấp tên/giá trị.

Bạn cũng có thể viết một factory method riêng để bind các tham số nullable của cùng nhóm truy vấn cho nhất quán và dễ test.

### 4.5. Khi nào cần chỉ rõ type cho cả giá trị không-null?

Mặc dù mục tiêu chính là `null`, một tham số không-null cũng có thể cần SQL type tường minh khi:

- Kiểu Java có thể ánh xạ đến nhiều kiểu SQL;
- DB column là `DECIMAL/NUMERIC` cần precision/scale theo nghiệp vụ;
- Driver xử lý đặc thù `UUID`, array, JSON, LOB, enum hoặc temporal types;
- Cần behavior nhất quán trên các môi trường/driver;
- Query plan hoặc quá trình binding phụ thuộc type phù hợp.

Ví dụ `addValue("amount", amount, Types.DECIMAL)` có thể hữu ích khi cột là decimal và `amount` là `BigDecimal`. Tuy nhiên, **định nghĩa SQL type không thay thế việc chọn model Java/SQL column đúng**; không dùng `Types.VARCHAR` cho mọi giá trị chỉ để né type inference.

### 4.6. Vì sao không dùng Types.NULL cho mọi tham số?

`java.sql.Types.NULL` mô tả một SQL NULL chung, **không mô tả chính xác kiểu cột cần dùng**. Khi biết cột `nickname` là VARCHAR, `Types.VARCHAR` biểu đạt ý định rõ hơn. Một số driver cần kiểu cụ thể để xử lý biểu thức, chuyển đổi giá trị, parameter metadata hoặc statement planning.

`Types.NULL` có thể là fallback hợp lệ trong một số tình huống nhưng không phải lựa chọn tổng quát tốt hơn so với kiểu SQL thực. Nếu SQL parameter đi vào cột chuyên biệt hoặc biểu thức có nhiều khả năng chuyển kiểu, hãy chọn `Types.*` đúng hoặc type name vendor khi cần.

## 5. Bind null không đồng nghĩa WHERE ... IS NULL

Đây là điểm quan trọng nhất về **ngữ nghĩa SQL**, độc lập với việc Map/MapSqlParameterSource bind thành công.

### 5.1. Biểu thức = NULL không tìm ra dòng NULL

Giả sử bảng `contacts` có `nickname` nullable:

| id | display_name | nickname |
| ---: | --- | --- |
| 1 | Alice | NULL |
| 2 | Bob | NULL |
| 3 | Carol | Caz |

Câu SQL:

```sql
SELECT id
FROM contacts
WHERE nickname = :nickname
ORDER BY id;
```

dù tham số `nickname` được bind thành SQL NULL **đúng kiểu VARCHAR**, biểu thức `nickname = NULL` vẫn có kết quả **UNKNOWN** theo logic ba giá trị của SQL. Trong điều kiện `WHERE`, UNKNOWN không được xem là TRUE. Vì vậy, query trên **không trả Alice hoặc Bob**.

Nếu muốn lọc các dòng nickname thật sự NULL, hãy viết:

```sql
SELECT id
FROM contacts
WHERE nickname IS NULL
ORDER BY id;
```

Câu thứ hai không cần bind `nickname`, vì phép `IS NULL` là **cấu trúc SQL** có ý nghĩa riêng.

### 5.2. Phân biệt ba ý định nghiệp vụ khi input nullable

Một giá trị `nickname = null` có thể mang nhiều ý nghĩa API:

1. **Không cập nhật trường nickname**: caller không gửi thuộc tính, nên SQL `UPDATE` không nên động đến cột này.
2. **Xóa nickname**: caller chủ động yêu cầu đặt cột thành SQL NULL.
3. **Tìm các dòng nickname NULL**: query phải dùng `WHERE nickname IS NULL`.

Ba trường hợp không thể tự suy ra chỉ từ một dòng `map.get("nickname") == null`. Vì cùng có thể trả null khi **key không tồn tại**. Ở API patch, thường cần phân biệt **absent field** và **present field = null** từ request, trước khi xây query. Đây là quyết định nghiệp vụ/contract, không phải chi tiết nhỏ của PreparedStatement.

Với hành vi “bỏ qua filter nếu null”, có thể xây query theo nhánh:

```java
String sql;
MapSqlParameterSource params = new MapSqlParameterSource();

if (nicknameFilter == null) {
    sql = "SELECT id FROM contacts ORDER BY id";
} else {
    sql = """
            SELECT id FROM contacts
            WHERE nickname = :nickname
            ORDER BY id
            """;
    params.addValue("nickname", nicknameFilter, Types.VARCHAR);
}
```

Đoạn trên minh họa cách chọn cấu trúc SQL; biến `nicknameFilter` được giả định có sẵn và chưa có phần thực thi. Với nhiều filter, sử dụng một SQL builder có kiểm soát hoặc các nhánh định nghĩa sẵn sẽ dễ bảo trì hơn.

Nếu input null **có nghĩa là tìm nickname IS NULL**, bạn phải dùng nhánh SQL `WHERE nickname IS NULL`, không phải nhánh “bỏ filter”.

### 5.3. Không tùy tiện viết :value IS NULL OR column = :value

Bạn có thể bắt gặp biểu thức:

```sql
WHERE (:nickname IS NULL OR nickname = :nickname)
```

Nó cố diễn đạt “nicknameFilter null thì bỏ lọc”. Nhưng tại vị trí `:nickname IS NULL`, DBMS có thể gặp vấn đề **suy luận kiểu** của parameter null. Mặt khác, biểu thức OR có thể ảnh hưởng khả năng tối ưu dùng index theo tình huống thực tế.

Khi query và type phức tạp, nên cân nhắc xây điều kiện có kiểm soát theo nhánh, hoặc đảm bảo SQL type được khai báo và kiểm thử trực tiếp trên DBMS thật. Không nên giả định phương án OR với null luôn tương thích hoặc có query plan tốt nhất.

### 5.4. NULL là giá trị, chuỗi "null" không phải SQL NULL

Cần phân biệt:

```java
params.addValue("nickname", null, Types.VARCHAR);    // SQL NULL
params.addValue("nickname", "null", Types.VARCHAR);  // 4 ký tự
params.addValue("nickname", "", Types.VARCHAR);      // chuỗi rỗng
```

Trong đa số DBMS, chuỗi rỗng và NULL có semantics khác nhau; một số DBMS, ví dụ Oracle trong một số kiểu dữ liệu chuỗi, có quy tắc đặc thù. Không chủ động thay nullable text thành `""` hay `"null"` để tránh phải bind null — việc đó thay đổi dữ liệu/nghiệp vụ.

## 6. Ví dụ chạy được với Java 17 + Spring JDBC + H2

Chương trình minh họa trực tiếp sự khác biệt giữa:

- `HashMap` chứa giá trị `null`;
- `Map.of(...)` từ chối `null`;
- `MapSqlParameterSource` đăng ký SQL type cho `null`;
- Câu `nickname = :nickname` và `nickname IS NULL`;
- Một Map bình thường truyền các giá trị non-null vào `NamedParameterJdbcTemplate`;
- Giá trị null trả về từ một cột SQL nullable (không đồng nghĩa truy vấn không trả dòng).

Dùng **Java 17+**, Spring Framework **6.2.12**, H2 **2.3.232**, Gradle tương thích Java 17. Không cần Spring Boot và không cần cài database server.

### 6.1. Cấu trúc project

```text
named-parameter-null-demo/
├── build.gradle
└── src/main/java/example/NamedParameterNullDemo.java
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.NamedParameterNullDemo'
}
```

`spring-jdbc` cung cấp `NamedParameterJdbcTemplate`, `JdbcTemplate` và `DriverManagerDataSource`. H2 được dùng lúc thực thi để tạo H2 in-memory database, không cần import driver H2 trực tiếp ở source Java.

### 6.3. Source Java hoàn chỉnh

Tạo `src/main/java/example/NamedParameterNullDemo.java`:

```java
package example;

import java.sql.Types;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class NamedParameterNullDemo {

    private static final String INSERT = """
            INSERT INTO contacts (id, display_name, nickname, score)
            VALUES (:id, :name, :nickname, :score)
            """;

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:named_null_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(ds);

        jdbc.execute("""
                CREATE TABLE contacts (
                    id BIGINT PRIMARY KEY,
                    display_name VARCHAR(80) NOT NULL,
                    nickname VARCHAR(80),
                    score INTEGER NOT NULL
                )
                """);

        // HashMap cho phép key tồn tại dù value null.
        Map<String, Object> alice = new HashMap<>();
        alice.put("id", 1L);
        alice.put("name", "Alice");
        alice.put("nickname", null);
        alice.put("score", 10);

        System.out.println(
                "keyPresent=" + alice.containsKey("nickname")
                        + ",isNull=" + (alice.get("nickname") == null));

        // Đối với null, khai báo type cụ thể, không dựa vào
        // khả năng suy luận của driver.
        MapSqlParameterSource aliceTyped =
                new MapSqlParameterSource(alice);
        aliceTyped.registerSqlType("nickname", Types.VARCHAR);
        int a = named.update(INSERT, aliceTyped);

        MapSqlParameterSource bob = new MapSqlParameterSource()
                .addValue("id", 2L, Types.BIGINT)
                .addValue("name", "Bob", Types.VARCHAR)
                .addValue("nickname", null, Types.VARCHAR)
                .addValue("score", 20, Types.INTEGER);
        int b = named.update(INSERT, bob);

        // Map.of tiện với các giá trị non-null.
        int c = named.update(
                INSERT,
                Map.of("id", 3L,
                       "name", "Carol",
                       "nickname", "Caz",
                       "score", 30));
        System.out.println("inserted=" + (a + b + c));

        // Map.of từ chối null ngay lúc tạo Map, trước khi gọi SQL.
        boolean mapOfRejectedNull;
        try {
            Map.of("nickname", (String) null);
            mapOfRejectedNull = false;
        } catch (NullPointerException ex) {
            mapOfRejectedNull = true;
        }
        System.out.println("mapOfRejectedNull=" + mapOfRejectedNull);

        // SQL three-valued logic: = NULL không tìm được row.
        MapSqlParameterSource nullNickname =
                new MapSqlParameterSource()
                        .addValue("nickname", null, Types.VARCHAR);
        Integer equalsNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname = :nickname",
                nullNickname,
                Integer.class);
        System.out.println("equalsNullCount=" + equalsNull);

        // IS NULL mới kiểm tra cột thật sự có giá trị NULL.
        Integer isNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname IS NULL",
                Map.of(),
                Integer.class);
        System.out.println("isNullCount=" + isNull);

        // Một hàng tồn tại nhưng giá trị cột nickname có thể null.
        String bobNickname = named.queryForObject(
                "SELECT nickname FROM contacts WHERE id = :id",
                Map.of("id", 2L),
                String.class);
        System.out.println("bobNicknameBefore=" + bobNickname);

        // Cập nhật từ null thành string, vẫn có thể khai báo type.
        int changed = named.update(
                """
                UPDATE contacts
                SET nickname = :nickname
                WHERE id = :id
                """,
                new MapSqlParameterSource()
                        .addValue("nickname", "Bobby", Types.VARCHAR)
                        .addValue("id", 2L, Types.BIGINT));
        System.out.println("updated=" + changed);

        Integer remainingNull = named.queryForObject(
                "SELECT COUNT(*) FROM contacts WHERE nickname IS NULL",
                Map.of(),
                Integer.class);
        System.out.println("remainingNull=" + remainingNull);

        // Map thuần truyền giá trị non-null rất gọn.
        List<String> selected = named.query(
                """
                SELECT display_name
                FROM contacts
                WHERE score >= :minScore
                ORDER BY id
                """,
                Map.of("minScore", 20),
                (rs, rowNum) -> rs.getString("display_name"));
        System.out.println("scoreAtLeast20=" + selected);
    }
}
```

**Các điểm đáng chú ý:**

1. `alice` là một `HashMap` có key `nickname` và value null, được bọc bởi `MapSqlParameterSource`. Đăng ký `Types.VARCHAR` cho key này giúp xác định SQL type tại lúc bind, không dựa vào null tự có class.
2. `bob` dùng trực tiếp `addValue(name, value, sqlType)`, nên source chứa đồng thời giá trị và metadata JDBC.
3. `Carol` có nickname không-null nên `Map.of(...)` ngắn gọn.
4. `Map.of("nickname", (String) null)` ném `NullPointerException` ngay trong Java; đoạn `catch` biến hành vi đó thành output kiểm chứng, chứ không bỏ qua lỗi âm thầm.
5. `nickname = :nickname` với null là điều kiện UNKNOWN, vì vậy count bằng 0 dù có hai rows nickname NULL.
6. `nickname IS NULL` trả 2 trước khi đổi Bob và 1 sau khi đổi Bob.
7. `queryForObject(..., String.class)` có thể trả `null` cho **một hàng hiện hữu** có cột nickname SQL NULL. Điều này khác với **không có dòng**, vốn có thể gây `EmptyResultDataAccessException`.
8. `DriverManagerDataSource` thích hợp demo nhưng không phải pool production; H2 in-memory với `DB_CLOSE_DELAY=-1` tồn tại giữa các kết nối trong cùng tiến trình JVM.

### 6.4. Chạy demo và stdout dự kiến

Từ thư mục chứa `build.gradle`, chạy:

```bash
gradle run
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Gradle có thể in log riêng; **chương trình Java** in ra các dòng theo thứ tự:

```text
keyPresent=true,isNull=true
inserted=3
mapOfRejectedNull=true
equalsNullCount=0
isNullCount=2
bobNicknameBefore=null
updated=1
remainingNull=1
scoreAtLeast20=[Bob, Carol]
```

Giải thích kết quả:

- Ban đầu, Alice và Bob cùng có nickname NULL; Carol có `Caz`.
- Ba lần insert hợp lệ thêm 3 dòng, nên `inserted=3`.
- `Map.of` từ chối null ở Java, nên `mapOfRejectedNull=true`.
- `WHERE nickname = NULL` không chọn hai dòng nickname NULL, nên count bằng 0.
- `WHERE nickname IS NULL` chọn Alice/Bob, nên count bằng 2.
- Truy vấn nickname của ID 2 chỉ trả **một dòng**, nhưng giá trị là NULL nên biến Java là `null`.
- Cập nhật nickname Bob thành `Bobby` tác động một dòng; sau đó chỉ Alice còn nickname NULL.
- `score >= 20` chọn Bob (20) và Carol (30); `ORDER BY id` xác định thứ tự in.

Đây là dự án nhỏ chạy được, không phải cấu hình production hoàn chỉnh. Khi ứng dụng dùng PostgreSQL/Oracle/SQL Server, cần integration test với driver và column types thật, đặc biệt với nullable parameters.

## 7. Nên chọn Map hay MapSqlParameterSource?

| Tiêu chí | `Map<String, ?>` | `MapSqlParameterSource` |
| --- | --- | --- |
| Truyền giá trị theo tên | Có | Có |
| Ngắn gọn cho value không-null | Rất tốt | Tốt |
| Có thể chứa value null | Phụ thuộc implementation: `HashMap` có, `Map.of` không | Có |
| Đăng ký JDBC SQL type cho một param | Không có metadata riêng trong Map thuần | Có, với `addValue(..., sqlType)` hoặc `registerSqlType` |
| Đăng ký type name vendor | Không qua Map thuần | Có overload `addValue(..., sqlType, typeName)` |
| Dùng lại một param nhiều lần trong cùng SQL | Có | Có |
| Tham số optional filter | Cần code quyết định có thêm key/SQL predicate không | Vẫn cần code quyết định SQL predicate; source không tự quyết định nghĩa của null |
| Tính dễ đọc với nhiều tham số nullable | Dễ thiếu SQL type, khó nhận ra ý nghĩa null | Biểu đạt rõ giá trị và type tại cùng nơi |

**Quy tắc thực hành:**

- Dùng `Map.of(...)` khi mọi value đã biết non-null và không cần metadata đặc biệt.
- Dùng `HashMap` nếu cần build động và có thể chứa null, **nhưng không quên vấn đề SQL type**.
- Dùng `MapSqlParameterSource` khi tham số nullable, muốn khai báo type rõ ràng, hoặc có value đặc thù cần JDBC type/type name.
- Đảm bảo SQL thể hiện đúng semantics `NULL`; dù có type đúng, `column = :param` không phải câu tìm cột NULL.

## 8. Khi Map được tạo từ request DTO

Giả sử một API nhận yêu cầu cập nhật:

```json
{
  "id": 2,
  "nickname": null
}
```

Cần xác định hợp đồng: `nickname = null` là yêu cầu xóa nickname hay là “không thay đổi”? Một số JSON serializer/deserializer hoặc DTO có thể biến **field thiếu** và **field explicit null** thành cùng một Java null, trừ khi bạn thiết kế model/flag phân biệt.

Nếu việc người dùng gửi null có nghĩa “xóa nickname”, repository có thể dùng:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", request.id(), Types.BIGINT)
        .addValue("nickname", request.nickname(), Types.VARCHAR);

int changed = namedJdbc.update(
        "UPDATE contacts SET nickname = :nickname WHERE id = :id",
        params);
```

Đây là **đoạn trích**, giả định `request` đã được định nghĩa, `namedJdbc` tồn tại và người dùng được phân quyền cập nhật record đó. `changed` thường bằng 1 khi id tồn tại, 0 khi không có dòng phù hợp. Hãy xử lý theo contract nghiệp vụ.

Nếu “không gửi nickname” nghĩa không thay đổi, đừng tự đưa key `nickname` null vào mọi SQL `UPDATE`. Cần biểu diễn trạng thái absent/explicit-null rõ trong DTO và xây query tương ứng. Không thể chỉ dựa vào `Map.get("nickname") == null` để quyết định vì nó cũng trả null cho key vắng mặt.

Đồng thời, đừng tin giá trị `tenantId` trong request mà không kiểm tra quyền; Map/parameter binding bảo vệ **cú pháp SQL**, không bảo đảm **authorization**.

## 9. Map, SQL type và query có tham số collection

`NamedParameterJdbcTemplate` có khả năng mở rộng tham số là collection cho dạng `IN (:ids)` trong các trường hợp được hỗ trợ.

```java
List<Long> ids = List.of(1L, 2L, 3L);

List<String> names = namedJdbc.query(
        """
        SELECT display_name
        FROM contacts
        WHERE id IN (:ids)
        ORDER BY id
        """,
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getString("display_name"));
```

Đoạn trên chỉ minh họa; giả định `namedJdbc` có sẵn và đã có bảng. Trong quá trình chuẩn bị JDBC statement, Spring có thể mở rộng danh sách thành số lượng `?` tương ứng. Đây là một cơ chế khác việc tự ý ghép giá trị SQL bằng nối chuỗi.

**Giới hạn cần nhớ:**

1. Không mặc định một collection có thể dùng làm **một** JDBC `?` trong mọi database; sự mở rộng là chức năng của named-parameter utility.
2. Danh sách rỗng cần xử lý chủ đích; `IN ()` có thể không hợp lệ hoặc có semantics khác theo dialect. Nếu không có ID nào cần tìm, trả list rỗng từ tầng ứng dụng là một lựa chọn hợp lý.
3. Danh sách cực lớn có thể chạm giới hạn số lượng bind parameters/độ dài SQL của driver/DBMS; cần chia batch hoặc đổi chiến lược (temporary table, join...) khi phù hợp.
4. `List.of(...)` cũng không chấp nhận null elements. Nếu danh sách có thể chứa null, xem xét logic SQL chứ không chỉ đổi sang `ArrayList`.
5. `IN (NULL)` không tự tìm các dòng `id IS NULL` (và ID primary key vốn không NULL). Muốn tìm NULL phải có điều kiện `IS NULL` riêng, khi hợp nghiệp vụ.

Tương tự, khi dùng `LIKE :pattern`, việc bind an toàn **không tự escape wildcard** `%`/`_` của `LIKE`. Chúng vẫn có semantics pattern; hãy escape phù hợp nếu người dùng muốn tìm literal substring.

## 10. Các lỗi và tình huống cần phân biệt

| Tình huống | Biểu hiện có thể gặp | Chẩn đoán/cách làm |
| --- | --- | --- |
| `Map.of("x", null)` | `NullPointerException` trước khi gọi JDBC | Map factory method không nhận null; dùng `MapSqlParameterSource` hoặc Map hỗ trợ null |
| `HashMap.put("x", null)` | Map được tạo thành công | Java Map cho phép null nhưng SQL type vẫn có thể unknown |
| SQL yêu cầu `:id` nhưng Map thiếu `id` | Lỗi Spring về tham số không được cung cấp | Dùng `containsKey`/kiểm thử query params; không đánh đồng missing với null |
| SQL dùng `:nickname` null nhưng driver không suy luận được type | SQLException hoặc `DataAccessException`, tùy DB/driver | Dùng `addValue("nickname", null, Types.VARCHAR)` hoặc type vendor phù hợp |
| `WHERE nickname = :nickname` với NULL | Không lấy dòng nickname NULL | Nếu muốn tìm NULL, viết `IS NULL` |
| Query trả một dòng có cột SQL NULL | Scalar mapped value có thể là Java null | Không nhầm với query 0 dòng |
| Query 0 dòng với `queryForObject` | `EmptyResultDataAccessException` | Chọn API/cardinality phù hợp |
| Client không gửi field nhưng backend đặt null | Có thể vô tình xóa giá trị cũ | Phân biệt absent và explicit-null trong API contract |
| Dùng `Types.NULL` cho mọi null | Type không nêu rõ kiểu cột | Dùng đúng JDBC type của cột, kiểm thử driver |
| Query `:name IS NULL` với untyped null | Một số DBMS có thể không xác định parameter type | Khai báo type hoặc dùng nhánh predicate rõ ràng |
| Dùng `Map.of` rồi `put` thêm key | `UnsupportedOperationException` | Dùng Map có thể thay đổi hoặc tạo Map mới |
| Tham số `IN (:ids)` là list rỗng | SQL có thể không hợp lệ | Quy định hành vi empty list trước khi gọi DB |
| Dùng tên cột từ request như value | `ORDER BY :field` không sort theo identifier | Chọn cột/hướng qua allowlist cấu trúc SQL |
| Chạy được H2 nhưng lỗi kiểu nullable trên production | Khác driver, SQL dialect, metadata và schema | Integration test cùng DBMS/driver và typed parameters |

## 11. Kiểm thử tối thiểu nên có

**Kiểm thử Java Collections:** xác minh `Map.of("key", null)` ném `NullPointerException`; một `HashMap` vẫn có `containsKey("key") == true` khi value null.

**Kiểm thử binding:** một SQL cập nhật cột `VARCHAR NULL` thực thi với `MapSqlParameterSource(..., Types.VARCHAR)`; xác minh DB ghi SQL NULL chứ không phải chuỗi `"null"`.

**Kiểm thử cardinality:** câu `SELECT nickname WHERE id=:id` theo id tồn tại có thể trả Java null; id không tồn tại với `queryForObject` là trường hợp khác và phải được xử lý theo hợp đồng.

**Kiểm thử ngữ nghĩa SQL NULL:** `nickname = :nickname` với typed null không trả hai dòng null; `nickname IS NULL` trả đúng số hàng có NULL.

**Kiểm thử missing key:** SQL dùng `:id` mà param source không có `id` phải fail rõ, không được ngầm lấy null.

**Kiểm thử optional patch:** phân biệt request không có field nickname với request có field nickname explicit null; xác minh không xóa dữ liệu ngoài ý muốn.

**Kiểm thử DB thật:** nullable parameter trong `WHERE :value IS NULL`, enum, UUID, array hoặc JSON phải được kiểm thử với driver/DBMS production, không suy luận từ H2. Quan sát query plan/performance khi câu SQL có nullable filter phức tạp.

## 12. Câu hỏi tự kiểm tra

1. Tại sao `Map.of("nickname", null)` có thể thất bại ngay trước khi Spring tạo statement?
2. `Map.get("nickname") == null` có đủ chứng minh rằng key nickname tồn tại không? Nên gọi thêm gì?
3. Với `HashMap` chứa key nickname và value null, Spring có biết chắc SQL type của nickname là VARCHAR không?
4. Vì sao `MapSqlParameterSource.addValue("nickname", null, Types.VARCHAR)` diễn đạt ý định rõ hơn Map thuần?
5. `Types.NULL` và `Types.VARCHAR` có ý nghĩa giống nhau hoàn toàn không?
6. Tại sao bind `null` cho câu `WHERE nickname = :nickname` vẫn không trả dòng nickname SQL NULL?
7. Nếu yêu cầu tìm các nickname NULL, câu SQL nên dùng `= :nickname` hay `IS NULL`?
8. Với request PATCH, trường nickname vắng mặt và trường nickname explicit-null có nên bị đối xử giống nhau không?
9. Khi parameter SQL có giá trị `Integer`, Java class của value có đảm bảo JDBC type sẽ luôn là `Types.INTEGER` không?
10. SQL dùng `IN (:ids)` sẽ gặp vấn đề gì nếu `ids` là list rỗng?
11. Khi nào `Map.of` phù hợp hơn `MapSqlParameterSource`?
12. Vì sao dùng named parameters không có nghĩa được nối tên cột hoặc `ORDER BY` trực tiếp từ request?

**Ghi nhớ:** `Map<String, ?>` rất tiện để truyền tham số có tên **không-null**. Nếu giá trị có thể null, tách ba câu hỏi: **Map có lưu được null không?**; **JDBC cần SQL type gì để bind null?**; **SQL có hiểu null theo đúng ý định nghiệp vụ không?**. Dùng `MapSqlParameterSource` để mô tả giá trị kèm JDBC type; dùng `IS NULL` và cấu trúc SQL phù hợp để xử lý điều kiện nullable.

### Tài liệu tham khảo

- Spring Framework — [Named Parameters trong JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework — [NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html).
- Spring Framework — [MapSqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- Spring Framework — [SqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html).
- Java SE 17 — [Map.of API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#of()).
- Java SE 17 — [java.sql.Types API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html).
