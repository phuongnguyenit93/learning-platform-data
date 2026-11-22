# SQL ARRAY, enum, JSON và kiểu riêng của cơ sở dữ liệu

Khi sử dụng Spring JDBC, các cột `VARCHAR`, `INTEGER`, `BIGINT` thường dễ ánh xạ vì JDBC có những phương thức và kiểu Java thông dụng. Nhưng nhiều hệ quản trị cơ sở dữ liệu còn có **mảng SQL (`ARRAY`)**, **kiểu liệt kê (`ENUM`)**, **JSON/`JSONB`**, **kiểu tự định nghĩa (`DOMAIN`, `STRUCT`/composite)** và các kiểu riêng như `UUID`, range, mạng, không gian địa lý. Chúng có khả năng kiểm tra ràng buộc và truy vấn mạnh ở tầng SQL, song **không có một cách bind/đọc dùng chung cho mọi DBMS**.

Bài này giải thích cách phân biệt kiểu dữ liệu Java, mã kiểu JDBC và kiểu gốc của database; cách chuyển dữ liệu trong `JdbcTemplate`/`NamedParameterJdbcTemplate`; ví dụ Java 17+ trên PostgreSQL; và giới hạn khi đem mã sang MySQL, Oracle hoặc hệ CSDL khác.

## 1. Ba lớp kiểu dữ liệu phải khớp với nhau

Một dữ liệu đi qua ba lớp:

```text
Java domain / DTO
  ├─ String[], List<String>, enum, JsonNode, UUID, record...
  ↓ mapping + validation
JDBC / Spring JDBC
  ├─ java.sql.Array, java.sql.Types, PreparedStatement, ResultSet
  ├─ SqlParameterValue, SqlTypeValue, RowMapper, JdbcTemplate
  └─ Driver extension: ví dụ org.postgresql.util.PGobject
  ↓ driver chuyển kiểu và mã hóa giá trị
Database
  ├─ text[], item_state, jsonb, uuid
  └─ domain, composite, range và các kiểu riêng khác
```

Ví dụ một `String[]` ở Java **không mặc nhiên** là một SQL `text[]`. Tương tự, Java `enum ItemState { NEW, READY }` không tự biến thành PostgreSQL `CREATE TYPE item_state AS ENUM (...)`; chuỗi `"{\\"a\\":1}"` cũng chưa chắc được driver nhận là `jsonb`.

| Khái niệm | Biểu diễn Java | JDBC | Ví dụ PostgreSQL | Cần chú ý |
| --- | --- | --- | --- | --- |
| Mảng SQL | `String[]`, `Integer[]`, đôi khi `Object[]` | `java.sql.Array`, `Types.ARRAY` | `text[]`, `integer[]` | Kiểu phần tử, chiều, NULL, cấp phát/giải phóng |
| Enum database | `enum` hoặc `String` | Thường là driver-specific/`Types.OTHER` | `item_state` | Nhãn và thứ tự label là hợp đồng schema |
| JSON | `String`, `JsonNode`, DTO | `setObject`, cast SQL, `Types.OTHER` tùy driver | `json`, `jsonb` | JSON hợp lệ, cấu trúc và null |
| UUID | `UUID` | `setObject`/`getObject` theo driver | `uuid` | Có driver hỗ trợ trực tiếp, có driver yêu cầu chuyển đổi |
| Kiểu riêng | Object/DTO chuyên biệt | `PGobject`, `Struct`, `SQLData`, extension của driver | `int4range`, domain, composite | Khả năng hỗ trợ API và cú pháp SQL khác nhau |

`java.sql.Types` mô tả **mã SQL type cho JDBC**, không phải một bộ chuyển đổi thần kỳ. `Types.OTHER` có nghĩa JDBC không có kiểu chuẩn cụ thể cho trường hợp ấy; **nó không đủ để biết** một `Object` đang mang kiểu `jsonb`, enum hay range nào.

## 2. SQL ARRAY: mảng SQL khác collection Java

SQL ARRAY cho phép một cột chứa tập phần tử cùng kiểu, ví dụ:

```sql
CREATE TABLE article (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tags TEXT[] NOT NULL
);

INSERT INTO article(tags) VALUES (ARRAY['spring', 'jdbc']);
SELECT tags[1] FROM article; -- 'spring' trong PostgreSQL mặc định
```

PostgreSQL thường bắt đầu chỉ số mảng ở **1**, còn Java bắt đầu tại **0**. PostgreSQL có thể hỗ trợ chỉ số dưới khác 1 khi tạo giá trị mảng đặc biệt, nên code đọc chỉ số SQL cần hiểu chính dữ liệu/cấu trúc mảng. Trong Java, nếu đã chuyển về `String[]` thì phần tử đầu luôn là `tags[0]`.

### 2.1. Ghi ARRAY bằng JDBC chuẩn

Trên driver hỗ trợ API tương ứng, tạo `java.sql.Array` bằng **connection đang thực sự dùng cho câu lệnh**, rồi gọi `PreparedStatement.setArray`:

```java
// Đoạn trích chạy bên trong ConnectionCallback của JdbcTemplate.
java.sql.Array dbArray = connection.createArrayOf(
    "text", new String[] { "spring", "jdbc" }
);
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO article(tags) VALUES (?)")) {
    ps.setArray(1, dbArray);
    ps.executeUpdate();
} finally {
    dbArray.free();
}
```

Ở đây `"text"` là **tên kiểu phần tử** của PostgreSQL; không phải `"text[]"`. Với `integer[]`, có thể dùng `createArrayOf("integer", new Integer[] {1, 2})`. Tên kiểu và phép hỗ trợ phụ thuộc DBMS/driver; một số cơ sở dữ liệu (đặc biệt collection type của Oracle) cần API chuyên biệt.

Vì `Connection.createArrayOf` tạo object phụ thuộc connection, không tạo `java.sql.Array` trên connection A rồi dùng trong statement trên connection B. Spring `JdbcTemplate.execute(ConnectionCallback<T>)` giúp truy cập đúng connection của callback và vẫn hưởng quản lý kết nối/translation lỗi của Spring.

Giải phóng `Array.free()` **sau khi** SQL đã thực thi; không free trước lúc driver sử dụng. Khi gọi API của driver cụ thể, hãy kiểm tra cơ chế quản lý tài nguyên được tài liệu driver cam kết.

### 2.2. Đọc ARRAY bằng ResultSet

```java
// Đoạn trích bên trong RowMapper; cột tags có kiểu text[].
java.sql.Array sqlArray = rs.getArray("tags");
String[] tags;
if (sqlArray == null) {
    tags = null; // SQL NULL khác mảng rỗng.
} else {
    try {
        tags = (String[]) sqlArray.getArray();
    } finally {
        sqlArray.free();
    }
}
```

Với pgJDBC và `text[]`, `getArray()` thường trả `String[]`. Với driver khác hoặc kiểu phần tử khác, kết quả có thể là một mảng Java kiểu khác, nên **không ép mọi `ARRAY` thành `String[]`**. Với mảng lớn có thể cân nhắc `Array.getResultSet()` nếu driver hỗ trợ tốt; cần đóng `ResultSet` và giải phóng `Array`.

### 2.3. Ba trường hợp không được đánh đồng

| Dữ liệu | Ý nghĩa |
| --- | --- |
| SQL `NULL` | Cột không có giá trị ARRAY (nếu schema cho phép) |
| `ARRAY[]::text[]` | Có một mảng nhưng **không có phần tử** |
| `ARRAY[NULL]::text[]` | Mảng có **một phần tử NULL** |

Ở Java, lần lượt có thể tương ứng `null`, `new String[0]`, `new String[] {null}`; cách API trả về và ánh xạ phải được test với driver. Cũng cần phân biệt dấu ngoặc của mảng SQL với mảng trong chuỗi JSON; `text[]` và `jsonb` có dữ liệu `["spring","jdbc"]` là **hai kiểu khác nhau**, có phép truy vấn và mapping khác nhau.

### 2.4. Truy vấn ARRAY trên PostgreSQL

```sql
SELECT id, tags
FROM article
WHERE tags @> ARRAY['spring']::text[];

SELECT id, tags
FROM article
WHERE 'jdbc' = ANY(tags);
```

`@>` là toán tử bao hàm của PostgreSQL cho mảng; `ANY` so sánh một phần tử với phần tử trong mảng. Đây không phải cú pháp SQL ARRAY dùng giống nhau ở mọi DBMS. Với workloads phù hợp có thể dùng chỉ mục `GIN`, nhưng cần kiểm tra execution plan và cardinality thực tế; không gắn chỉ mục tự động cho mọi cột mảng.

Nếu các phần tử cần thuộc tính riêng, thứ tự nghiệp vụ quan trọng, phép nối phức tạp hoặc có thể tăng vô hạn, một bảng con chuẩn hóa thường phù hợp hơn lưu toàn bộ vào ARRAY.

## 3. Enum: phải phân biệt Java enum và enum của database

Với PostgreSQL:

```sql
CREATE TYPE item_state AS ENUM ('NEW', 'READY', 'ARCHIVED');

CREATE TABLE catalog_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state item_state NOT NULL
);
```

Java có thể định nghĩa:

```java
enum ItemState {
    NEW, READY, ARCHIVED
}
```

Hai enum có nhãn giống nhau nhưng **không được liên kết tự động**. Một thay đổi schema như thêm `PAUSED` phải được phản ánh trong parser Java, validation, migration và tương thích phiên bản ứng dụng.

### 3.1. Bind enum theo kiểu PostgreSQL

Một cách rõ ràng với pgJDBC là `PGobject` (extension của PostgreSQL JDBC driver):

```java
PGobject stateValue = new PGobject();
stateValue.setType("item_state");
stateValue.setValue(ItemState.READY.name());

ps.setObject(1, stateValue);
```

Một cách khác không cần `PGobject` trong câu lệnh SQL cụ thể là dùng cast:

```java
// Dùng với PostgreSQL; ? vẫn là tham số JDBC.
jdbc.update(
    "UPDATE catalog_item SET state = CAST(? AS item_state) WHERE id = ?",
    ItemState.READY.name(), id
);
```

Ví dụ `ps.setString(1, "READY")` **không phải lúc nào** cũng được driver/server tự chuyển từ `VARCHAR` sang `item_state` nếu SQL không có cast thích hợp. Dùng `PGobject` hoặc cast tường minh giúp rõ ý định. `Types.OTHER` có thể cần khi bind NULL hoặc dùng API chung; kiểu SQL thực vẫn phải được xác định.

### 3.2. Đọc enum và xử lý thay đổi nhãn

```java
String label = rs.getString("state");
ItemState state = ItemState.valueOf(label);
```

`valueOf` yêu cầu **khớp chính xác** chữ hoa/thường. Nếu DB có nhãn mà code chưa biết, `IllegalArgumentException` là tín hiệu **không tương thích schema** chứ không nên tự thay bằng `NEW` hay `READY`. Trong mô hình phải chấp nhận phiên bản tương thích, hãy định nghĩa quy tắc ánh xạ `UNKNOWN` ở tầng domain thật rõ ràng.

PostgreSQL enum có thứ tự so sánh theo lúc khai báo nhãn. Nó khác Java `ordinal()`; **đừng lưu `ordinal()`** làm giao thức DB vì thay thứ tự hằng trong Java có thể làm dữ liệu bị diễn giải sai. Tương tự, không giả định MySQL `ENUM` và PostgreSQL enum dùng cùng cú pháp DDL hay cùng xử lý thứ tự.

## 4. JSON và JSONB: dữ liệu có cấu trúc không đồng nghĩa chuỗi văn bản tùy ý

Ví dụ PostgreSQL:

```sql
CREATE TABLE example_json (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document JSONB NOT NULL
);

INSERT INTO example_json(document)
VALUES ('{"source":"jdbc","priority":2}'::jsonb);
```

Trong PostgreSQL:

- `json` lưu văn bản JSON hợp lệ theo cách giữ nguyên biểu diễn đầu vào phần lớn trường hợp, gồm khoảng trắng và thứ tự khóa.
- `jsonb` chuyển thành biểu diễn nhị phân có cấu trúc, thường thuận tiện cho kiểm tra bao hàm và indexing. Nó **không giữ nguyên** khoảng trắng, thứ tự khóa object và các khóa trùng nhau như văn bản gốc.
- Cả hai có thể lưu object, array, number, string, boolean và JSON `null`; **JSON null khác SQL NULL**.
- JSON giúp biểu diễn thuộc tính linh hoạt, nhưng **không thay thế ràng buộc domain, schema validation, quản lý phiên bản và các cột quan hệ cho dữ liệu cốt lõi**.

### 4.1. Bind JSONB đúng SQL type

Cách dùng `PGobject`:

```java
PGobject value = new PGobject();
value.setType("jsonb");
value.setValue("{\"source\":\"jdbc\",\"priority\":2}");
ps.setObject(1, value);
```

Hoặc bind chuỗi JSON làm tham số rồi cast trong SQL:

```java
jdbc.update(
    "UPDATE example_json SET document = CAST(? AS jsonb) WHERE id = ?",
    "{\"source\":\"jdbc\",\"priority\":2}", id
);
```

Cả hai đều giữ JSON dưới **parameter binding**; không nối nội dung JSON nhận từ người dùng vào câu SQL. PostgreSQL sẽ xác thực cú pháp JSON khi chuyển sang `jsonb`; ứng dụng nên xác thực cấu trúc và giá trị nghiệp vụ **trước** khi ghi.

Đọc bằng `rs.getString("document")` rồi dùng thư viện JSON (ví dụ Jackson) để parse thành `JsonNode`/DTO. **Không so sánh chuỗi JSONB raw với JSON input theo ký tự**, vì DB có thể đổi khoảng trắng/thứ tự khóa; so sánh cấu trúc hoặc các trường có ý nghĩa.

### 4.2. Truy vấn JSONB

```sql
SELECT id
FROM example_json
WHERE document @> '{"source":"jdbc"}'::jsonb;

SELECT document ->> 'source'
FROM example_json;
```

`@>` là phép bao hàm JSONB của PostgreSQL; `->>` lấy giá trị dạng text. Cột JSONB có truy vấn `@>` nhiều có thể cân nhắc `GIN`; chọn chỉ mục dựa trên câu truy vấn và `EXPLAIN` thay vì giả định mọi chỉ mục `GIN` đều giống nhau.

**Bẫy với pgJDBC:** PostgreSQL có toán tử JSONB `?` để kiểm tra tồn tại key, trong khi `?` là placeholder của `PreparedStatement`. Trong chuỗi SQL truyền cho pgJDBC, viết **`??`** để escape toán tử này; ví dụ:

```java
Boolean hasPriority = jdbc.queryForObject(
    "SELECT document ?? ? FROM example_json WHERE id = ?",
    Boolean.class, "priority", id
);
```

pgJDBC chuyển `??` thành toán tử SQL `?`; dấu `?` kế tiếp vẫn là placeholder cho key `"priority"`. Đây là quy tắc của pgJDBC, không phải SQL syntax áp dụng chung cho driver khác.

### 4.3. JSON NULL và SQL NULL

```sql
SELECT 'null'::jsonb IS NULL; -- false: có giá trị JSON null
SELECT NULL::jsonb IS NULL;   -- true: SQL NULL
```

Jackson `NullNode`, `null` của Java và một thuộc tính JSON **không tồn tại** cần được phân biệt theo quy tắc domain. Đừng tự áp dụng `String.valueOf(null)` để lưu `"null"` mà không xác định rõ nghĩa.

## 5. Ví dụ Java 17+ chạy được: ARRAY + enum + JSONB trong một bảng

Ví dụ sau dùng **Spring JDBC 6.2.x, pgJDBC và PostgreSQL 16**. Nó tạo một bản ghi danh mục với ba kiểu đặc biệt, đọc lại bằng `RowMapper` và kiểm tra truy vấn theo cấu trúc SQL. Phần tạo schema chạy **ngoài chương trình Java**, chỉ để thiết lập môi trường học tập; ứng dụng thực tế cần schema migration.

### 5.1. Tạo PostgreSQL cục bộ

Nếu có Docker, khởi chạy PostgreSQL thử nghiệm:

```bash
docker run --rm --name jdbc-special-types -d \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=jdbc_types_demo \
  -p 5433:5432 \
  postgres:16
```

Chờ database sẵn sàng trước khi chạy script (có thể dùng `docker exec jdbc-special-types pg_isready -U demo -d jdbc_types_demo`). Trên máy đã có PostgreSQL, có thể tạo database và user tương đương thay vì dùng Docker.

Tạo file `schema.sql`:

```sql
-- Chỉ dùng để reset dữ liệu demo.
DROP TABLE IF EXISTS catalog_item;
DROP TYPE IF EXISTS item_state;

CREATE TYPE item_state AS ENUM ('NEW', 'READY', 'ARCHIVED');

CREATE TABLE catalog_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT[] NOT NULL,
    state item_state NOT NULL,
    properties JSONB NOT NULL,
    CONSTRAINT properties_is_object
        CHECK (jsonb_typeof(properties) = 'object')
);
```

Chạy script từ Bash:

```bash
docker exec -i jdbc-special-types \
  psql -v ON_ERROR_STOP=1 -U demo -d jdbc_types_demo < schema.sql
```

Trên Windows PowerShell:

```powershell
Get-Content -Raw schema.sql |
    docker exec -i jdbc-special-types psql -v ON_ERROR_STOP=1 -U demo -d jdbc_types_demo
```

Lệnh `DROP` là để reset **database thử nghiệm** cho output xác định. Không áp dụng trực tiếp vào production.

### 5.2. Cấu hình Gradle

Tạo `settings.gradle`:

```groovy
rootProject.name = 'jdbc-special-types-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.19'
    implementation 'org.postgresql:postgresql:42.7.14'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.19.2'
}

application {
    mainClass = 'JdbcSpecialTypesDemo'
}
```

Đây là các phiên bản cụ thể cho ví dụ, không có ý khẳng định chúng là mới nhất. pgJDBC là `implementation` (không chỉ `runtimeOnly`) vì mã Java dùng trực tiếp lớp `PGobject`.

### 5.3. Chương trình Java hoàn chỉnh

Tạo file `src/main/java/JdbcSpecialTypesDemo.java`:

```java
import java.sql.Array;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class JdbcSpecialTypesDemo {
    enum ItemState {
        NEW, READY, ARCHIVED
    }

    record CatalogItem(
        String title,
        String[] tags,
        ItemState state,
        String propertiesJson
    ) {}

    private JdbcSpecialTypesDemo() {}

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://127.0.0.1:5433/jdbc_types_demo");
        dataSource.setUsername("demo");
        dataSource.setPassword("demo");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        long id = insert(jdbc);
        CatalogItem item = jdbc.queryForObject(
            "SELECT title, tags, state, properties " +
                "FROM catalog_item WHERE id = ?",
            (rs, rowNum) -> mapRow(rs),
            id
        );

        if (item == null) {
            throw new IllegalStateException("Row not found after insert");
        }

        JsonNode json = new ObjectMapper().readTree(item.propertiesJson());
        Boolean matched = jdbc.queryForObject(
            "SELECT EXISTS (" +
                "SELECT 1 FROM catalog_item " +
                "WHERE tags @> ARRAY[?]::text[] " +
                "AND properties @> ?::jsonb " +
                "AND state = ?::item_state)",
            Boolean.class,
            "spring",
            "{\"source\":\"lesson\"}",
            "READY"
        );

        System.out.println("Title: " + item.title());
        System.out.println("State: " + item.state());
        System.out.println("Tags: " + Arrays.toString(item.tags()));
        System.out.println("JSON priority: " + json.path("priority").asInt());
        System.out.println("JSON source: " + json.path("source").asText());
        System.out.println("Query matched: " + Boolean.TRUE.equals(matched));
    }

    private static long insert(JdbcTemplate jdbc) {
        Long id = jdbc.execute((ConnectionCallback<Long>) connection -> {
            Array sqlTags = connection.createArrayOf(
                "text", new String[] { "spring", "jdbc", "json" }
            );

            try {
                PGobject dbState = new PGobject();
                dbState.setType("item_state");
                dbState.setValue(ItemState.READY.name());

                PGobject dbProperties = new PGobject();
                dbProperties.setType("jsonb");
                dbProperties.setValue(
                    "{\"priority\":2,\"source\":\"lesson\"}"
                );

                try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO catalog_item " +
                    "(title, tags, state, properties) " +
                    "VALUES (?, ?, ?, ?) RETURNING id"
                )) {
                    ps.setString(1, "Sample");
                    ps.setArray(2, sqlTags);
                    ps.setObject(3, dbState);
                    ps.setObject(4, dbProperties);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("INSERT returned no id");
                        }
                        return rs.getLong(1);
                    }
                }
            } finally {
                sqlTags.free();
            }
        });

        if (id == null) {
            throw new IllegalStateException("No generated identifier");
        }
        return id;
    }

    private static CatalogItem mapRow(ResultSet rs) throws SQLException {
        Array sqlTags = rs.getArray("tags");
        if (sqlTags == null) {
            throw new SQLException("tags unexpectedly NULL");
        }

        String[] tags;
        try {
            tags = (String[]) sqlTags.getArray();
        } finally {
            sqlTags.free();
        }

        return new CatalogItem(
            rs.getString("title"),
            tags,
            ItemState.valueOf(rs.getString("state")),
            rs.getString("properties")
        );
    }
}
```

**Cần hiểu rõ:**

- `ConnectionCallback` giúp gọi `createArrayOf` trên chính connection mà `PreparedStatement` đang sử dụng. `JdbcTemplate` vẫn quản lý vòng đời connection và chuyển `SQLException` sang hệ `DataAccessException` thích hợp.
- `PGobject.setType("item_state")` và `setType("jsonb")` thông báo kiểu PostgreSQL cho driver. Java không tự suy luận được kiểu enum SQL từ `ItemState`.
- `INSERT ... RETURNING id` là cách nhận khóa sau khi insert **riêng của PostgreSQL**; ví dụ không xem ID là bằng chứng toàn quy trình nghiệp vụ khác đã hoàn tất.
- `RowMapper` dùng `getArray`, `getString`, `ItemState.valueOf`; nếu JSON không đúng schema mong đợi hoặc enum có nhãn mới, cần xử lý lỗi rõ ràng.
- Jackson parse `JSONB` sau khi đọc, nên logic không phụ thuộc thứ tự key/whitespace do PostgreSQL tái biểu diễn.

Khi đã chạy `schema.sql`, dùng JDK 17+ và Gradle tương thích:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, trên Linux/macOS dùng `./gradlew run --quiet`, trên Windows dùng `gradlew.bat run --quiet`.

Với schema vừa reset, **stdout từ chương trình Java** dự kiến là:

```text
Title: Sample
State: READY
Tags: [spring, jdbc, json]
JSON priority: 2
JSON source: lesson
Query matched: true
```

Chương trình không in giá trị `id` để tránh phụ thuộc sequence. Nếu không reset database mà chạy nhiều lần, nó sẽ thêm nhiều bản ghi nhưng các dòng stdout vẫn phản ánh bản ghi vừa tạo nhờ điều kiện `WHERE id = ?`. Bản demo không tự kiểm chứng trên môi trường triển khai thực tế; cần thực thi integration test với PostgreSQL/driver mục tiêu.

## 6. Viết gọn bằng JdbcTemplate và NamedParameterJdbcTemplate

Ví dụ đầy đủ ở trên dùng `ConnectionCallback` vì tạo SQL ARRAY cần connection. Khi SQL type có thể xác định bằng **cast tường minh**, bạn có thể giữ phong cách API cao hơn của Spring:

```java
// Mã minh họa trong repository đã có namedJdbc và id.
String sql = """
    UPDATE catalog_item
       SET state = CAST(:state AS item_state),
           properties = CAST(:json AS jsonb)
     WHERE id = :id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("state", ItemState.ARCHIVED.name())
    .addValue("json", "{\"priority\":3,\"source\":\"api\"}")
    .addValue("id", id);

int updated = namedJdbc.update(sql, params);
```

Đây là **đoạn minh họa trong DAO**, không phải file Java độc lập: nó cần `NamedParameterJdbcTemplate namedJdbc`, `id`, `ItemState` và `MapSqlParameterSource`. Cách `CAST(:json AS jsonb)` rõ ràng hơn trong SQL có named parameters; JSON vẫn được bind như một giá trị.

Nếu driver cần mã JDBC cụ thể, Spring còn có:

```java
// Các phương án truyền thông tin SQL type; lựa chọn tùy API.
new SqlParameterValue(Types.OTHER, dbSpecificValue);

new MapSqlParameterSource()
    .addValue("payload", dbSpecificValue, Types.OTHER);
```

Đây là những *giá trị tham số* minh họa; cần import `org.springframework.jdbc.core.SqlParameterValue`, `org.springframework.jdbc.core.namedparam.MapSqlParameterSource` và `java.sql.Types`. Chỉ định `Types.OTHER` không thay cho việc driver nhận được một `PGobject` đúng `setType` hoặc một cast SQL thích hợp.

Khi xử lý stored procedure có `ARRAY`/`STRUCT` ở `IN`/`OUT`, Spring cung cấp `SqlTypeValue`/`AbstractSqlTypeValue` để tạo đối tượng chuyên biệt trên connection đang dùng; `SqlReturnType` để chuyển giá trị trả về. Chúng thường xuất hiện trong `SqlParameter`/`SqlOutParameter` kết hợp `SimpleJdbcCall`. Không thể giả định driver nào cũng hỗ trợ `Connection.createStruct` hoặc `Connection.createArrayOf` cho mọi kiểu database.

## 7. Kiểu riêng của cơ sở dữ liệu: DOMAIN, composite, range, UUID…

“Kiểu riêng” bao gồm nhiều nhóm khác nhau, không nên gộp mọi kiểu vào `PGobject` một cách máy móc.

### 7.1. PostgreSQL DOMAIN

```sql
CREATE DOMAIN positive_amount AS NUMERIC(12,2)
    CHECK (VALUE >= 0);
```

`DOMAIN` dựa trên một kiểu nền (ở đây `NUMERIC`) và thêm ràng buộc. Ứng dụng có thể dùng `BigDecimal` để bind dữ liệu tùy ngữ cảnh, và database kiểm tra `CHECK`. Khi parameter có kiểu không rõ, cast có thể giúp:

```sql
SELECT CAST(? AS positive_amount);
```

Không nên xem domain như enum: một domain có thể ánh xạ về Java type nền, còn enum có tập nhãn riêng. Lỗi vi phạm `CHECK` phải được dịch thành kết quả hợp đồng nghiệp vụ thích hợp.

### 7.2. PostgreSQL composite và range

```sql
CREATE TYPE shipping_address AS (
    city TEXT,
    postal_code TEXT
);

CREATE TABLE delivery_slot (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    allowed_numbers int4range NOT NULL
);
```

- `shipping_address` là một **composite type**. JDBC có giao diện `java.sql.Struct`/`SQLData`, nhưng mức hỗ trợ `createStruct`, `getObject` và ánh xạ composite **khác nhau giữa driver**. pgJDBC có thể đọc kiểu chưa biết thành `PGobject` chứa biểu diễn text; ứng dụng cần phép chuyển đổi đã được kiểm thử hoặc dùng SQL chiếu từng trường.
- `int4range` là **range type** của PostgreSQL, khác hoàn toàn với một `integer[]` hai phần tử. `[10,20)` diễn tả dải gồm cận dưới 10, loại trừ cận trên 20; range còn có biểu diễn rỗng, cận vô hạn và toán tử riêng. Có thể bind bằng `PGobject` nếu driver/SQL tương ứng hỗ trợ kiểu đó:

```java
// Mã minh họa cho cột int4range PostgreSQL.
PGobject bounds = new PGobject();
bounds.setType("int4range");
bounds.setValue("[10,20)");
jdbc.update(
    "INSERT INTO delivery_slot(allowed_numbers) VALUES (?)",
    bounds
);
```

- `uuid` của PostgreSQL thường được pgJDBC ánh xạ thuận tiện tới `java.util.UUID` qua `setObject`/`getObject(..., UUID.class)`. Nhưng không kết luận mọi hệ CSDL có kiểu UUID hoặc mapping như vậy.
- Các kiểu `inet`/`cidr`, `hstore` extension, `tsvector`, PostGIS `geometry`/ `geography` đòi hỏi kiểm tra kiểu SQL, driver và thư viện extension cụ thể. Chỉ dùng wrapper phù hợp với định dạng và phép truy vấn thực sự được hỗ trợ.

### 7.3. Oracle và MySQL không có hợp đồng giống PostgreSQL

- Oracle có collection/UDT như `VARRAY`, nested table và object type. Một số trường hợp dùng `OracleConnection.createOracleArray(typeName, elements)` qua `connection.unwrap(OracleConnection.class)` theo tài liệu Oracle JDBC, thay vì giả định JDBC `createArrayOf` hoạt động y hệt PostgreSQL.
- MySQL cung cấp kiểu `JSON` và `ENUM` với quy tắc lưu trữ/SQL riêng. Không thể sao chép `CREATE TYPE item_state AS ENUM`, `jsonb @>`, `PGobject`, `text[]` hoặc `int4range` sang MySQL rồi mong chạy được.
- SQL Server, Oracle, PostgreSQL và các driver có thể khác nhau ở loại giá trị trả về từ `ResultSet.getObject`, cơ chế bind `NULL`, cách mã hóa/timezone và quyền truy cập metadata. Khi đổi DBMS, phải thay cả **DDL, SQL, JDBC mapping và integration test**, không chỉ thay connection string.

## 8. Các ranh giới quan trọng khi làm việc với kiểu đặc biệt

### 8.1. NULL, giá trị rỗng và dữ liệu bất hợp lệ

- **ARRAY:** SQL `NULL` khác mảng `{}` và mảng có phần tử `NULL`.
- **ENUM:** `"READY"` là nhãn hợp lệ trong schema ví dụ; `"ready"` khác nhãn nếu chưa cấu hình mapping thích hợp; `"UNKNOWN"` có thể bị database từ chối.
- **JSONB:** SQL `NULL` khác JSON `null`, object `{}` khác array `[]`; schema check `jsonb_typeof(properties)='object'` trong demo từ chối scalar/array nhưng **không xác minh** mọi trường domain.
- **CUSTOM:** giá trị miền âm với `positive_amount` làm vi phạm constraint; biểu diễn range sai cú pháp hoặc sai kiểu khiến driver/server báo lỗi.

Với prepared statement, `ps.setNull(index, Types.ARRAY)`, `Types.OTHER`, hoặc `ps.setObject(index, null)` có thể dẫn đến hành vi khác nhau; khi cần, sử dụng kiểu SQL/cast/tên kiểu rõ ràng và kiểm tra driver. Đừng dùng `""`, `"null"` hay một array rỗng làm đại diện thay SQL NULL nếu domain không quy định như vậy.

### 8.2. Transaction và tính nhất quán

Dù cột là JSONB hay ENUM, câu lệnh `INSERT`/`UPDATE` do Spring JDBC thực thi vẫn chịu ranh giới transaction của connection đang dùng. Nếu service dùng `@Transactional` đúng proxy, các câu lệnh tham gia cùng transaction thường được commit/rollback cùng nhau. JSON/ARRAY có thể được bind thành công nhưng **chưa kết luận transaction commit**, và việc parse/serialize payload không thay thế kiểm tra kết quả nghiệp vụ.

Nếu `PGobject` được tạo sai type, enum label không tồn tại hoặc JSONB có lỗi cú pháp, database có thể phát sinh `SQLException`. `JdbcTemplate` thường dịch thành `DataAccessException`; không bắt mọi lỗi chuyển đổi rồi trả kết quả “ghi thành công”. Những lỗi liên quan schema/version cần log đủ ngữ cảnh (tên kiểu, operation, correlation ID) nhưng tránh ghi toàn bộ JSON nhạy cảm.

### 8.3. Hiệu năng và thiết kế schema

Không phải cứ dùng JSONB/ARRAY là nhanh hoặc linh hoạt hơn một schema quan hệ:

- Tìm kiếm theo phần tử mảng, key JSONB hoặc range phụ thuộc chỉ mục, chọn lọc dữ liệu và toán tử; `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường phù hợp là bằng chứng tốt hơn suy đoán.
- JSONB lớn bị cập nhật thường xuyên có thể làm tăng chi phí ghi/WAL/TOAST; nên cân nhắc cột quan hệ cho trường được cập nhật, lọc, join liên tục.
- Enum database thích hợp cho tập nhãn ổn định, nhưng thêm/đổi nhãn phải có migration và khả năng tương thích phiên bản. Với tập trạng thái thường xuyên thay đổi, bảng tham chiếu có thể phù hợp hơn.
- SQL ARRAY tiện cho tập ngắn, cùng kiểu, ít cần join. Dữ liệu nhiều quan hệ, thứ tự, metadata riêng theo phần tử có thể cần bảng con.
- Custom type thuận tiện khi cần constraint/hàm SQL mạnh, song tăng mức phụ thuộc DBMS. Ghi rõ lựa chọn đó trong tài liệu kiến trúc.

## 9. Kiểm thử mapping ở ranh giới thực

Một integration test có giá trị cần chạy trên **cùng họ database và driver** sẽ triển khai. Bộ tình huống nên bao gồm:

1. **ARRAY bình thường:** `["spring","jdbc"]` ghi và đọc đủ phần tử đúng thứ tự; query `@>` trả đúng kết quả.
2. **ARRAY rỗng/NULL:** phân biệt `new String[0]`, SQL `NULL`, phần tử `NULL`; kiểm tra nhiều chiều nếu thật sự dùng.
3. **ENUM đúng/sai:** nhãn `READY` round-trip; nhãn không tồn tại bị từ chối; Java đọc nhãn mới có cách xử lý tương thích đã định nghĩa.
4. **JSON hợp lệ:** object nhiều tầng, Unicode, số, boolean và mảng; đọc lại bằng JSON parser rồi so sánh cấu trúc, không so sánh chuỗi raw.
5. **JSON không hợp lệ:** thiếu quote/dấu ngoặc, sai type so với `CHECK`, JSON `null` và SQL NULL; xác minh xử lý lỗi.
6. **Kiểu riêng:** domain constraint bị vi phạm, range biên, UUID và composite mapping nếu sử dụng trong dự án.
7. **Transaction:** khi một lệnh thất bại, rollback các cập nhật cùng transaction; kiểm tra bằng transaction/kết nối quan sát độc lập.
8. **Bảo mật & vận hành:** mọi giá trị bind bằng tham số, không lắp ghép literal JSON/enum/ARRAY vào SQL từ input; có giới hạn kích thước payload và timeout hợp lý.

Với Spring Boot/JUnit, có thể dùng Testcontainers PostgreSQL để tạo DB thật cho test; H2 hay database giả lập thường **không mô phỏng chính xác** PostgreSQL enum, JSONB, custom range và pgJDBC. Nếu không có PostgreSQL chạy ở môi trường kiểm thử, chỉ nên khẳng định code được kiểm tra cú pháp, chưa được xác nhận hành vi trên DB thật.

## 10. Tóm tắt cách chọn mapping

| Dữ liệu ở DB | Điểm bắt đầu ở Spring JDBC | Ưu tiên kiểm tra |
| --- | --- | --- |
| PostgreSQL `text[]`/`integer[]` | `Connection.createArrayOf` + `ps.setArray`; đọc `rs.getArray` | Tên kiểu phần tử, NULL/empty, `Array.free()` |
| PostgreSQL enum | `PGobject` đúng type hoặc SQL `CAST(? AS enum_type)`; `getString` rồi parse Java enum | Label/version/case, quyền schema |
| PostgreSQL JSONB | `PGobject("jsonb")` hoặc `CAST(? AS jsonb)`; `getString` + Jackson | SQL NULL khác JSON null, validation, query operators |
| DOMAIN | Bind kiểu nền, cast khi cần | Constraint và scale/precision |
| Composite/`STRUCT` | Driver extension hoặc JDBC `Struct` khi hỗ trợ | Metadata, thứ tự trường, driver compatibility |
| Range/`inet`/UDT | SQL cast, `PGobject` hoặc thư viện driver/type chuyên dụng | Biểu diễn chính xác và toán tử theo DB |
| Oracle collection/UDT | Oracle JDBC extension / `SqlTypeValue` | Tên SQL type, unwrap connection, driver API |

**Nguyên tắc:** Cần thiết kế và kiểm tra mapping ở cả ba phía **Java ↔ JDBC/Spring ↔ database**. Không suy luận rằng dùng `setObject` hoặc `Types.OTHER` thì Spring tự hiểu mọi kiểu đặc biệt, cũng không coi kết quả đọc được một chuỗi JSON/enum là bằng chứng dữ liệu đã đúng quy tắc nghiệp vụ.

### Tài liệu tham khảo

- [Spring Framework — JDBC parameter handling and complex SQL types](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [pgJDBC — PostgreSQL-specific JDBC extensions and arrays](https://jdbc.postgresql.org/documentation/server-prepare/)
- [pgJDBC — Query and question-mark operator escaping](https://jdbc.postgresql.org/documentation/query/)
- [PostgreSQL — Arrays](https://www.postgresql.org/docs/16/arrays.html)
- [PostgreSQL — Enumerated types](https://www.postgresql.org/docs/16/datatype-enum.html)
- [PostgreSQL — JSON types](https://www.postgresql.org/docs/16/datatype-json.html)
- [PostgreSQL — CREATE TYPE](https://www.postgresql.org/docs/16/sql-createtype.html)
