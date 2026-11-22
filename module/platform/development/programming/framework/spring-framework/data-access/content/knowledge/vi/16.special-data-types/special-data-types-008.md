# Xử lý `null` tường minh và giá trị mặc định với kiểu dữ liệu đặc biệt trong Spring JDBC

## 1. Vì sao bài toán này dễ gây lỗi?

Khi truy cập cơ sở dữ liệu qua Spring JDBC, lập trình viên thường cần biểu diễn ba ý khác nhau:

1. **Không cung cấp giá trị** để cơ sở dữ liệu sử dụng `DEFAULT`.
2. **Chủ động lưu SQL `NULL`** (chưa biết, không tồn tại, hoặc xóa một giá trị cũ theo quy ước nghiệp vụ).
3. **Lưu một giá trị thực nhưng rỗng/trống**, chẳng hạn chuỗi `""`, mảng `[]`, đối tượng JSON `{}` hoặc giá trị JSON `null`.

Ba ý này **không tương đương**. Đặc biệt với các kiểu `UUID`, `JSON/JSONB`, `ARRAY`, `ENUM`, LOB hoặc kiểu tùy chỉnh, việc truyền Java `null` mà không mô tả kiểu SQL có thể khiến driver không xác định được loại tham số. Ngoài ra, truyền `null` vào cột có `DEFAULT` **không tự kích hoạt** giá trị mặc định.

Bài này tập trung vào Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `MapSqlParameterSource` và `PreparedStatement`) cùng quy tắc SQL. Ví dụ cụ thể dùng **PostgreSQL**, Java 17 và Spring Framework 6.x; quy tắc chung áp dụng cho JDBC, nhưng kiểu dữ liệu đặc biệt và cách bind có thể khác ở MySQL, Oracle hay SQL Server.

## 2. Tách bạch các trạng thái giá trị

| Trạng thái mong muốn | Giá trị/SQL tiêu biểu | Dữ liệu được lưu hoặc hành vi |
| --- | --- | --- |
| Cột **không được chỉ định** khi `INSERT` | Bỏ cột khỏi danh sách `INSERT` | Dùng `DEFAULT` nếu khai báo; nếu không có, thường là SQL `NULL` |
| Yêu cầu dùng default | `DEFAULT` trong câu SQL | DBMS tính giá trị mặc định theo schema |
| Chủ động lưu SQL `NULL` | `SET column = NULL` hoặc bind tham số SQL null | Lưu SQL `NULL` (sẽ lỗi nếu cột `NOT NULL`) |
| Chuỗi trống | `''` (PostgreSQL) | Chuỗi độ dài 0, **không phải** SQL `NULL` |
| Mảng trống PostgreSQL | `ARRAY[]::text[]` | Mảng có 0 phần tử, khác SQL `NULL` |
| Đối tượng JSON rỗng | `'{}'::jsonb` | Giá trị JSON là object rỗng |
| JSON literal `null` | `'null'::jsonb` | **Một giá trị JSON**, không phải SQL `NULL` |
| Không sửa cột trong `UPDATE` | Không đưa cột vào mệnh đề `SET` | Giữ nguyên giá trị hiện tại |

Ví dụ với một cột `payload jsonb`:

```sql
-- Giá trị SQL NULL: cột không có giá trị SQL.
SELECT NULL::jsonb IS NULL;           -- true

-- Giá trị JSON null vẫn là một giá trị jsonb.
SELECT 'null'::jsonb IS NULL;         -- false
SELECT jsonb_typeof('null'::jsonb);   -- chuỗi 'null'

-- Object JSON rỗng cũng không phải SQL NULL.
SELECT '{}'::jsonb IS NULL;           -- false
SELECT jsonb_typeof('{}'::jsonb);     -- chuỗi 'object'
```

Vì vậy, kiểm tra JSON `null` bằng `column IS NULL` là chưa đủ. Ngược lại, nếu `payload` là SQL `NULL`, `jsonb_typeof(payload)` cũng cho SQL `NULL`, không trả chuỗi `"null"`. Ở tầng Java, `String json = "null"` chứa bốn ký tự, còn `String json = null` không trỏ tới chuỗi nào.

### Java `null` không tự diễn đạt ý nghĩa nghiệp vụ

Một DTO có trường `tags = null` có thể đại diện cho một trong ba ý: chưa được gửi, muốn xóa, hoặc muốn dùng mặc định. Chỉ nhìn `null` **không thể phân biệt** chúng. Hợp đồng API nên định nghĩa rõ:

- **Absent**: trường không có trong request → giữ nguyên khi cập nhật; hoặc để database default khi tạo mới.
- **Present with null**: trường có mặt và giá trị null → lưu SQL `NULL` hoặc thực hiện hành vi xóa theo thiết kế.
- **Present with value**: trường có mặt với dữ liệu, kể cả `[]`/`{}` → lưu đúng giá trị đó.

Với PATCH, có thể biểu diễn trạng thái bằng một cờ `provided` cộng giá trị, hoặc dùng kiểu wrapper phân biệt “thiếu” với “có mặt nhưng null”. Không nên sử dụng `Optional.ofNullable(...)` **một mình** cho PATCH vì `Optional.empty()` có thể làm mất khác biệt giữa thiếu trường và trường được gửi dưới dạng null.

## 3. Khai báo giá trị mặc định đúng ở schema

Dùng bảng PostgreSQL để minh họa nhiều loại đặc biệt:

```sql
CREATE TABLE demo_null_defaults (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_ref  UUID NULL,
    payload       JSONB NULL,
    labels        TEXT[] DEFAULT ARRAY[]::TEXT[],
    status        VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    attempts      INTEGER NOT NULL DEFAULT 0,
    optional_limit INTEGER NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`labels` có default là **mảng trống**, nhưng vẫn cho phép SQL `NULL` vì không có ràng buộc `NOT NULL`. `status` và `attempts` vừa có default vừa có `NOT NULL`: truyền SQL `NULL` trực tiếp vào hai cột này sẽ bị từ chối, không được thay bằng default.

Các cách chèn sau minh họa bốn trạng thái:

```sql
-- A. Không chỉ định cột: dùng toàn bộ default.
INSERT INTO demo_null_defaults DEFAULT VALUES;

-- B. Chỉ định SQL NULL: default của labels KHÔNG được áp dụng.
INSERT INTO demo_null_defaults (payload, labels)
VALUES (NULL, NULL);

-- C. JSON null; labels dùng DEFAULT nhờ từ khóa SQL.
INSERT INTO demo_null_defaults (payload, labels)
VALUES ('null'::jsonb, DEFAULT);

-- D. JSON object và mảng trống là các giá trị có thật.
INSERT INTO demo_null_defaults (payload, labels)
VALUES ('{}'::jsonb, ARRAY[]::text[]);
```

Để thấy các trạng thái khác nhau:

```sql
SELECT id,
       status,
       attempts,
       labels IS NULL AS labels_sql_null,
       cardinality(labels) AS label_count,
       payload IS NULL AS payload_sql_null,
       jsonb_typeof(payload) AS payload_json_type
FROM demo_null_defaults
ORDER BY id;
```

Nếu bảng vừa được tạo và thực hiện đúng bốn câu lệnh chèn trên, các thuộc tính cần quan sát như sau (ID cụ thể phụ thuộc sequence):

| Hàng | `status` | `attempts` | `labels_sql_null` | `label_count` | `payload_sql_null` | `payload_json_type` |
| --- | --- | ---: | --- | ---: | --- | --- |
| A | `DRAFT` | 0 | `false` | 0 | `true` | SQL `NULL` |
| B | `DRAFT` | 0 | `true` | SQL `NULL` | `true` | SQL `NULL` |
| C | `DRAFT` | 0 | `false` | 0 | `false` | `null` (chuỗi chỉ loại JSON) |
| D | `DRAFT` | 0 | `false` | 0 | `false` | `object` |

**Quy tắc:** Khi muốn dùng default của một cột trên `INSERT`, hãy **bỏ cột** khỏi danh sách chèn hoặc viết `DEFAULT` trong SQL. Không thể dùng `?` hoặc `:parameter` để truyền từ khóa SQL `DEFAULT` như thể nó là dữ liệu. `PreparedStatement` bind *giá trị*; nó không thay đổi cấu trúc câu SQL.

## 4. Gán SQL `NULL` tường minh qua Spring JDBC

### 4.1. `JdbcTemplate` với danh sách kiểu `int[]`

Spring thường suy ra kiểu SQL từ giá trị Java. Với Java `null` không có runtime type, vì vậy cách an toàn là **khai báo kiểu theo đúng cột đích**. Ví dụ cập nhật `JSONB` trong PostgreSQL, kết hợp cast trong SQL:

```java
// Fragment nằm trong repository có JdbcTemplate jdbc và biến long id.
String sql = """
        UPDATE demo_null_defaults
        SET payload = CAST(? AS jsonb)
        WHERE id = ?
        """;

int changed = jdbc.update(
        sql,
        new Object[] {null, id},
        new int[] {Types.VARCHAR, Types.BIGINT}
);
```

Ở đây:

- Tham số 1 là **SQL `NULL`** với kiểu JDBC `VARCHAR`, sau đó PostgreSQL nhận kiểu đích rõ ràng từ `CAST(? AS jsonb)`.
- Tham số 2 là `BIGINT` cho cột `id`.
- `changed` là số hàng cập nhật, không phải ID; nếu hàng `id` không tồn tại, có thể bằng 0.
- Nếu muốn lưu **JSON literal null**, thay đầu vào thứ nhất bằng chuỗi `"null"`; nếu muốn lưu object rỗng, truyền `"{}"`.

`Types.VARCHAR` + `CAST(... AS jsonb)` là một **chiến lược cụ thể với PostgreSQL** cho chuỗi JSON hợp lệ, không phải quy tắc ánh xạ áp dụng cho mọi DBMS. Khi bind trực tiếp một đối tượng PostgreSQL `jsonb` theo driver, có thể cần `Types.OTHER` hoặc `PGobject`.

### 4.2. `NamedParameterJdbcTemplate` và `MapSqlParameterSource`

Tên tham số giúp tránh nhầm vị trí:

```java
// Fragment: giả định đã có NamedParameterJdbcTemplate namedJdbc.
String sql = """
        UPDATE demo_null_defaults
        SET payload = CAST(:payload AS jsonb),
            external_ref = :ref
        WHERE id = :id
        """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("payload", null, Types.VARCHAR)
        .addValue("ref", null, Types.OTHER)
        .addValue("id", 42L, Types.BIGINT);

int changed = namedJdbc.update(sql, params);
```

- `Types.OTHER` là một cách thường dùng với PostgreSQL `UUID` và nhiều kiểu đặc thù; phải kiểm tra hành vi driver đối với loại thật.
- `MapSqlParameterSource.addValue(name, value, sqlType)` lưu **giá trị + mô tả kiểu JDBC**. `value = null` vẫn phải có kiểu xác định khi driver cần.
- Với `UUID` không-null, pgJDBC có thể bind `java.util.UUID` qua `PreparedStatement.setObject(...)`. Không mặc định ép tất cả kiểu đặc biệt sang `VARCHAR`.
- `:payload` và `:ref` là *tham số có tên*, còn `DEFAULT` là cú pháp SQL. Nếu cần `SET status = DEFAULT`, hãy viết `DEFAULT` trực tiếp vào câu SQL cố định.

Trong SQL dùng named parameter, ưu tiên `CAST(:payload AS jsonb)` thay vì viết sát `:payload::jsonb` để tránh sự mơ hồ với cú pháp parser của thư viện.

### 4.3. `SqlParameterValue` khi chỉ một tham số cần kiểu riêng

```java
// Fragment: mọi phương thức cần imports và biến jdbc/id trong repository.
int changed = jdbc.update(
        "UPDATE demo_null_defaults SET payload = CAST(? AS jsonb) WHERE id = ?",
        new SqlParameterValue(Types.VARCHAR, null),
        id
);
```

`SqlParameterValue` mang theo kiểu SQL và giá trị cho **một** placeholder. Khi nhiều giá trị nullable xuất hiện cùng lúc, mảng `int[]` hoặc `MapSqlParameterSource` thường dễ kiểm soát hơn.

### 4.4. `PreparedStatement.setNull` cho `ARRAY` và kiểu driver-specific

Với một cột PostgreSQL `TEXT[]`, dùng `java.sql.Array` cho mảng có dữ liệu và gán null có kiểu tường minh:

```java
// Fragment trong một PreparedStatementSetter/ConnectionCallback.
// ps trỏ tới INSERT hoặc UPDATE có placeholder thứ 1 kiểu text[].
String[] values = {"java", "spring"};
java.sql.Array array = ps.getConnection().createArrayOf("text", values);
try {
    ps.setArray(1, array);              // mảng có hai phần tử
} finally {
    array.free();                        // giải phóng đối tượng SQL Array
}

// Nếu chủ động lưu SQL NULL:
ps.setNull(1, Types.ARRAY);
```

Hai phép gán ở fragment trên minh họa **hai lựa chọn thay thế nhau**, không phải chuỗi thao tác cần làm liền trong một statement. Giữ đối tượng `Array` cho đến khi driver đã dùng xong để thực thi; trong thực tế thường đóng/free **sau `execute`**, không ngay sau `setArray` nếu chưa chạy. Ví dụ hoàn chỉnh ở phần sau chỉ dùng `setNull`.

`ps.setNull(index, Types.ARRAY)` khác `ps.setArray(index, emptyArray)`. Tùy driver, kiểu phần tử mảng cần được suy ra từ SQL (`CAST(? AS text[])`) hoặc đăng ký tên kiểu vendor. Không dùng `Types.NULL` làm câu trả lời chung cho mọi kiểu SQL; cũng đừng nhầm `null` với mảng rỗng.

### Chọn kiểu SQL tường minh

| Cột đích | Giá trị Java hay dùng | Hướng gán null |
| --- | --- | --- |
| `VARCHAR/TEXT` | `String` | `Types.VARCHAR` |
| `INTEGER` nullable | `Integer` | `Types.INTEGER` |
| `BIGINT` nullable | `Long` | `Types.BIGINT` |
| `NUMERIC/DECIMAL` | `BigDecimal` | `Types.NUMERIC` hoặc `Types.DECIMAL` |
| `UUID` của PostgreSQL | `UUID` | Thường `Types.OTHER` hoặc cast SQL có kiểu rõ |
| `JSONB` của PostgreSQL | Chuỗi JSON hợp lệ hoặc `PGobject` | Cast từ chuỗi `VARCHAR` hoặc xử lý `OTHER` theo driver |
| `TEXT[]` của PostgreSQL | `java.sql.Array` | `Types.ARRAY`; xác định kiểu phần tử khi cần |
| `TIMESTAMPTZ` | `OffsetDateTime` | Xem `Types.TIMESTAMP_WITH_TIMEZONE` và khả năng driver |
| `BLOB/CLOB` | Bytes/stream/reader | `Types.BLOB`/`Types.CLOB` và API LOB thích hợp |

Bảng trên là **định hướng**, không đảm bảo mọi cơ sở dữ liệu dùng cùng SQL type code. Với `ENUM`, `STRUCT`, `ARRAY`, `JSON`, kiểu địa lý hoặc kiểu do người dùng định nghĩa, hãy đọc mapping chính thức của driver đang sử dụng và test cả trường hợp **có giá trị** lẫn **SQL NULL**.

## 5. Chương trình Java 17+ chạy được: phân biệt DEFAULT, SQL NULL và JSON null

Ví dụ này dùng PostgreSQL (có kiểu `JSONB` và `TEXT[]`) cùng Spring JDBC. Nó tạo bốn hàng riêng và in ra các trạng thái; không sửa hay xóa dữ liệu hiện có. Trước khi chạy, thực thi `CREATE TABLE` ở phần 3 trên database thử nghiệm.

### 5.1. Maven (`pom.xml`)

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>explicit-null-defaults</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.8</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là phiên bản phụ thuộc minh họa. Trong dự án Spring Boot, nên theo cơ chế quản lý phiên bản đồng bộ của BOM. Cần JDK 17+, Maven và PostgreSQL truy cập được từ máy chạy.

### 5.2. Tệp `src/main/java/ExplicitNullDefaultDemo.java`

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class ExplicitNullDefaultDemo {

    private ExplicitNullDefaultDemo() {}

    // Trả về một mô tả trạng thái, không làm mất SQL NULL của cardinality().
    private record State(
            String status,
            int attempts,
            boolean labelsSqlNull,
            Integer labelCount,
            boolean payloadSqlNull,
            String jsonType
    ) {}

    public static void main(String[] args) {
        var ds = new DriverManagerDataSource(
                requireEnv("DB_URL"),
                requireEnv("DB_USER"),
                requireEnv("DB_PASSWORD")
        );
        var jdbc = new JdbcTemplate(ds);

        long defaultsId = insertUsingDefaults(jdbc);
        long sqlNullId = insertTypedSqlNull(jdbc);
        long jsonNullId = insertJsonValue(jdbc, "'null'::jsonb");
        long emptyObjectId = insertJsonValue(jdbc, "'{}'::jsonb");

        print("DEFAULT", read(jdbc, defaultsId));
        print("SQL NULL", read(jdbc, sqlNullId));
        print("JSON null", read(jdbc, jsonNullId));
        print("JSON object", read(jdbc, emptyObjectId));
    }

    private static long insertUsingDefaults(JdbcTemplate jdbc) {
        Long id = jdbc.queryForObject(
                "INSERT INTO demo_null_defaults DEFAULT VALUES RETURNING id",
                Long.class);
        return Objects.requireNonNull(id);
    }

    private static long insertTypedSqlNull(JdbcTemplate jdbc) {
        // Một fragment JDBC thuần trong ConnectionCallback của Spring.
        // Với cột đặc biệt, CAST trong SQL giúp xác định kiểu đích.
        Long id = jdbc.execute((ConnectionCallback<Long>) connection -> {
            String sql = """
                    INSERT INTO demo_null_defaults
                        (external_ref, payload, labels)
                    VALUES (?, CAST(? AS jsonb), CAST(? AS text[]))
                    RETURNING id
                    """;
            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setNull(1, Types.OTHER);    // PostgreSQL UUID
                ps.setNull(2, Types.VARCHAR);  // SQL NULL -> jsonb
                ps.setNull(3, Types.ARRAY);    // SQL NULL -> text[]

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("INSERT did not return id");
                    }
                    return rs.getLong(1);
                }
            }
        });
        return Objects.requireNonNull(id);
    }

    private static long insertJsonValue(JdbcTemplate jdbc, String literal) {
        // Chỉ chấp nhận hai biểu thức SQL cố định của ví dụ; không
        // truyền chuỗi SQL từ input người dùng vào phương thức này.
        if (!literal.equals("'null'::jsonb")
                && !literal.equals("'{}'::jsonb")) {
            throw new IllegalArgumentException("Invalid demo literal");
        }
        String sql = "INSERT INTO demo_null_defaults (payload) VALUES ("
                + literal + ") RETURNING id";
        Long id = jdbc.queryForObject(sql, Long.class);
        return Objects.requireNonNull(id);
    }

    private static State read(JdbcTemplate jdbc, long id) {
        String sql = """
                SELECT status, attempts,
                       labels IS NULL AS labels_sql_null,
                       cardinality(labels) AS label_count,
                       payload IS NULL AS payload_sql_null,
                       jsonb_typeof(payload) AS json_type
                  FROM demo_null_defaults
                 WHERE id = ?
                """;
        return Objects.requireNonNull(jdbc.queryForObject(
                sql,
                (rs, rowNum) -> new State(
                        rs.getString("status"),
                        rs.getInt("attempts"),
                        rs.getBoolean("labels_sql_null"),
                        rs.getObject("label_count", Integer.class),
                        rs.getBoolean("payload_sql_null"),
                        rs.getString("json_type")),
                id));
    }

    private static void print(String label, State value) {
        String type = value.jsonType() == null
                ? "(SQL NULL)" : value.jsonType();

        System.out.printf(
                "%s: status=%s; attempts=%d; labelsSQLNull=%s; "
                + "labelCount=%s; payloadSQLNull=%s; jsonType=%s%n",
                label,
                value.status(),
                value.attempts(),
                value.labelsSqlNull(),
                value.labelCount(),
                value.payloadSqlNull(),
                type
        );
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + key);
        }
        return value;
    }
}
```

**Vì sao code đúng ý nghĩa của bài?**

- `insertUsingDefaults` không truyền giá trị cho bất kỳ cột nào; PostgreSQL dùng `DEFAULT` của `labels`, `status`, `attempts` và `created_at`.
- `insertTypedSqlNull` cố ý gán `NULL` cho ba cột, bao gồm cột `labels` có default. Default của `labels` **không được dùng**.
- `insertJsonValue(..., "'null'::jsonb")` lưu **JSON null** như một giá trị `jsonb`. `insertJsonValue(..., "'{}'::jsonb")` lưu object JSON rỗng.
- `read(...)` lấy `label_count` bằng `getObject(..., Integer.class)` để giữ được Java `null` khi `cardinality(labels)` trả SQL `NULL`. `getInt(...)` sẽ trả `0` cho SQL `NULL` và phải kết hợp `wasNull()` nếu cột nullable.
- Câu SQL tạo từ `literal` trong ví dụ chỉ dùng **hai chuỗi literal cố định và kiểm tra whitelist**. Trong ứng dụng thật, dùng bind parameters (`?` hoặc `:name`), không nối dữ liệu người dùng vào SQL.

### 5.3. Chạy chương trình

Tạo bảng bằng SQL ở phần 3, rồi trong môi trường terminal Bash thiết lập kết nối tới database thử nghiệm:

```bash
export DB_URL="jdbc:postgresql://localhost:5432/demo"
export DB_USER="demo_user"
export DB_PASSWORD="your_password"

mvn -q compile exec:java -Dexec.mainClass=ExplicitNullDefaultDemo
```

Thay `demo` và thông tin đăng nhập bằng database hiện có. Khi schema mới tạo và driver hoạt động đúng, stdout từ **chương trình Java** (không bao gồm log Maven) là:

```text
DEFAULT: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=true; jsonType=(SQL NULL)
SQL NULL: status=DRAFT; attempts=0; labelsSQLNull=true; labelCount=null; payloadSQLNull=true; jsonType=(SQL NULL)
JSON null: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=false; jsonType=null
JSON object: status=DRAFT; attempts=0; labelsSQLNull=false; labelCount=0; payloadSQLNull=false; jsonType=object
```

Kết quả được suy từ các câu `INSERT ... RETURNING` và phép kiểm tra SQL; chương trình cần PostgreSQL thật để chạy. Nếu bảng đã có dữ liệu, chương trình vẫn tạo bốn hàng mới và chỉ đọc các ID vừa nhận, nên giá trị dự kiến của bốn dòng không đổi. Không xóa bảng hoặc `TRUNCATE` dữ liệu sẵn có.

## 6. Giá trị mặc định ở từng tầng và khi cập nhật

Một hệ thống thường có ít nhất bốn tầng xác định default:

1. **Database schema:** `DEFAULT 'DRAFT'`, `DEFAULT CURRENT_TIMESTAMP`, `DEFAULT ARRAY[]::text[]`; DBMS áp dụng khi thiếu giá trị/viết `DEFAULT`.
2. **SQL của repository:** `COALESCE(:x, value)`, `CASE ...`, `UPDATE ... SET column = DEFAULT`; đây là quy tắc được viết vào câu lệnh.
3. **Java service:** tính fallback bằng `Objects.requireNonNullElse(...)` hoặc kiểm tra null trước khi gọi repository.
4. **API contract/DTO:** giá trị mặc định cho trường bị bỏ qua trong request.

Các tầng có ngữ nghĩa và thời điểm thực thi khác nhau. **Tạo một giá trị Java fallback rồi bind nó** có nghĩa DBMS nhận **giá trị được chỉ định**, không phải tự áp dụng DEFAULT. Default dạng biểu thức (`CURRENT_TIMESTAMP`, sequence, hàm tùy biến) nên để DBMS tính nếu cần tính nhất quán tại thời điểm ghi.

### UPDATE: giữ nguyên, xóa, hay đưa về DEFAULT?

```sql
-- Giữ nguyên labels: không nhắc tới cột này.
UPDATE demo_null_defaults
SET status = 'READY'
WHERE id = 10;

-- Xóa giá trị labels thành SQL NULL.
UPDATE demo_null_defaults
SET labels = NULL
WHERE id = 10;

-- Đưa labels về default (mảng rỗng).
UPDATE demo_null_defaults
SET labels = DEFAULT
WHERE id = 10;

-- Xóa giá trị JSONB, khác với JSON literal null.
UPDATE demo_null_defaults
SET payload = NULL
WHERE id = 10;

-- Lưu JSON null; payload vẫn IS NOT NULL.
UPDATE demo_null_defaults
SET payload = 'null'::jsonb
WHERE id = 10;
```

Các ID chỉ để minh họa: nếu không có hàng `id = 10`, `UPDATE` sẽ không thay đổi hàng nào. `DEFAULT` trong `UPDATE` là cú pháp được PostgreSQL hỗ trợ cho cột, không phải tham số có thể bind.

### `COALESCE` có thể che mất ý định “xóa dữ liệu”

```sql
-- Nếu :payload nhận SQL NULL, câu này GIỮ payload cũ.
UPDATE demo_null_defaults
SET payload = COALESCE(CAST(:payload AS jsonb), payload)
WHERE id = :id;
```

Biểu thức trên phù hợp **chỉ khi** yêu cầu nghiệp vụ quy định “null nghĩa là giữ nguyên”. Nó **không thể dùng** để biểu diễn “null nghĩa là xóa”. Khi viết API PATCH, phân biệt:

| Trạng thái request | SQL thích hợp |
| --- | --- |
| Không có trường `payload` | Không thêm `payload` vào `SET` |
| Có trường `payload: null`, muốn xóa | `SET payload = NULL` |
| Có trường `payload: {}` | `SET payload = CAST(? AS jsonb)`, bind `"{}"` |
| Muốn khôi phục default của `labels` | `SET labels = DEFAULT` |

Khi SQL phải thay đổi theo danh sách cột cập nhật, **chỉ ghép các tên cột đã được định nghĩa sẵn trong code**, bind giá trị qua `PreparedStatement`. Không nhận tên cột hoặc biểu thức SQL tự do từ request để tránh SQL injection.

## 7. Đọc null an toàn ở tầng Java

### Giá trị số nullable

`ResultSet.getInt(...)` trả `0` khi giá trị SQL là `NULL`. Phải kiểm tra `wasNull()` **ngay sau lần đọc** nếu muốn phân biệt SQL `NULL` với số 0:

```java
// Fragment trong RowMapper, giả định ResultSet rs có cột optional_limit.
int raw = rs.getInt("optional_limit");
Integer limit = rs.wasNull() ? null : raw;
```

Khi driver hỗ trợ chuyển đổi JDBC 4.1, cách ngắn hơn là:

```java
// Giữ nguyên Java null nếu optional_limit là SQL NULL.
Integer limit = rs.getObject("optional_limit", Integer.class);
```

`getInt`, `getLong` và `getBoolean` là các getter trả primitive, nên cần lưu ý cùng kiểu nhầm lẫn này. Trong Spring JDBC, `RowMapper` nên trả DTO có trường wrapper `Integer`/`Long`/`Boolean` khi dữ liệu có thể SQL NULL; không mặc định hóa null thành `0` hay `false` trừ khi nghiệp vụ yêu cầu.

### Chuỗi JSON, SQL array và đối tượng vendor

- `rs.getString("payload")` với PostgreSQL có thể trả văn bản JSON; SQL `NULL` thường được biểu diễn thành Java `null`, còn JSON literal `null` có thể là chuỗi `"null"`. Để quyết định đúng, đọc thêm `payload IS NULL` hoặc dùng kiểu/parsing JSON riêng.
- `rs.getArray("labels")` trả `java.sql.Array` hoặc Java `null`. Chỉ gọi `getArray()` trên đối tượng SQL Array khi khác null; trường hợp mảng có 0 phần tử khác hẳn SQL NULL.
- `rs.getObject("external_ref", java.util.UUID.class)` dùng với driver có hỗ trợ map PostgreSQL UUID. Cần kiểm thử kiểu vendor-specific; đối tượng trả về không bắt buộc luôn giống một kiểu Java trên mọi DBMS.
- Có thể dùng `COALESCE` trong truy vấn đọc, ví dụ `COALESCE(optional_limit, 5)`, khi **thật sự muốn** áp dụng fallback ở kết quả. Điều đó làm mất thông tin liệu DB đang lưu null hay 5; không phù hợp khi dữ liệu gốc có ý nghĩa riêng.

## 8. Trường hợp đặc biệt: LOB, ARRAY, UUID và JSON

### BLOB/CLOB

Một trường nhị phân rỗng (`byte[0]`) khác SQL `NULL`. Một chuỗi rỗng dùng cho CLOB có thể có quy tắc riêng theo DBMS (Oracle có những khác biệt với chuỗi rỗng). Khi thao tác dữ liệu lớn, dùng API JDBC (`setBinaryStream`/`setCharacterStream`) hoặc `LobHandler` của Spring theo khả năng driver. Không lấy `new byte[0]` làm “mặc định null” nếu DB/schema phân biệt hai trường hợp.

### ARRAY

`createArrayOf("text", elements)` tạo một giá trị `text[]` có phần tử, trong khi `ARRAY[]::text[]` là mảng rỗng nhưng **có kiểu cụ thể**. Với PostgreSQL, một mảng rỗng phải có kiểu phần tử; không suy ra được mọi tình huống chỉ từ `ARRAY[]` không có cast. `cardinality(NULL::text[])` là SQL `NULL`, còn `cardinality(ARRAY[]::text[])` là 0.

### UUID

`java.util.UUID` mang kiểu miền giá trị cụ thể; không thay bằng chuỗi `""` khi muốn SQL NULL. Với pgJDBC, `Types.OTHER`/`setObject(UUID)` thường thích hợp, nhưng khi nullable cần xác nhận SQL có ngữ cảnh xác định `UUID` hoặc cast tường minh. Có thể gặp lỗi “could not determine data type of parameter” trong các truy vấn mơ hồ như `WHERE ? IS NULL`; hãy dùng kiểu SQL rõ ràng, ví dụ `CAST(? AS uuid) IS NULL` nếu logic yêu cầu.

### JSON/JSONB

JSON object `{}`, array `[]`, string rỗng `""` và literal `null` là **bốn giá trị JSON khác nhau**, và tất cả khác SQL `NULL`. Không dùng một phép kiểm tra `payload IS NULL` để phân loại toàn bộ. Khi cập nhật một trường con trong JSON, PostgreSQL có các hàm/toán tử JSON riêng; phải xác định “xóa key”, “gán key bằng JSON null” và “xóa cả cột” là ba hành động độc lập.

## 9. Lỗi thường gặp, cách kiểm thử và nguyên tắc thiết kế

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ Java `null` sẽ kích hoạt `DEFAULT` | Lưu SQL NULL hoặc lỗi `NOT NULL` | Bỏ cột khi INSERT hoặc viết `DEFAULT` |
| Dùng `Types.NULL`/`Types.OTHER` một cách đại trà | Driver có thể không xác định kiểu | Chọn kiểu theo schema, cast khi phù hợp, test driver |
| Ép `null` sang `""`, `[]`, `{}` mặc định | Mất phân biệt “không có” và “rỗng” | Chỉ chuyển đổi khi nghiệp vụ yêu cầu |
| Nhầm JSON `null` với SQL `NULL` | Kiểm tra IS NULL sai, sai nhánh xử lý | Dùng `IS NULL` và `jsonb_typeof` đúng chỗ |
| Đọc số nullable bằng `getInt` mà quên `wasNull` | NULL bị biến thành 0 | Dùng `getObject(..., Integer.class)` hoặc `wasNull` |
| Dùng `COALESCE` trong PATCH có ý định xóa | Không thể chuyển một giá trị hiện có thành null | Phân biệt request thiếu trường với null chủ động |
| Truyền `DEFAULT` như string parameter | Chỉ lưu một chuỗi hoặc bị lỗi kiểu | `DEFAULT` phải là cú pháp SQL được kiểm soát |
| Xây SQL bằng nối dữ liệu JSON từ request | SQL injection, lỗi escaping | Dùng bind parameters; cast kiểu SQL |
| Coi default Java là default DB | Lệch thời gian/giá trị trên các đường ghi | Chọn một nơi chủ đạo cho default và document rõ |
| Đưa SQL NULL vào cột `NOT NULL` | Vi phạm ràng buộc | Validate trước, để DB chặn sai dữ liệu |
| Mặc định mọi DB hỗ trợ `JSONB` và `TEXT[]` | SQL không chạy trên DBMS khác | Chọn SQL, JDBC type và mapper theo DBMS |

### Checklist kiểm thử thực tế

1. Kiểm tra **schema thật**: `NULL/NOT NULL`, `DEFAULT`, kiểu `UUID/JSON/ARRAY`, scale của số và thời gian.
2. Kiểm thử đủ bốn trường hợp: thiếu trường, null tường minh, rỗng và giá trị bình thường; thêm trường hợp JSON literal `null` khi dùng JSONB.
3. Sau `INSERT/UPDATE`, chạy `SELECT` xác minh giá trị lưu thực tế (không chỉ kiểm tra số dòng cập nhật); với JSON dùng thêm `jsonb_typeof` và `IS NULL`.
4. Kiểm thử DTO PATCH với **absent/present-null/present-value** và đồng bộ hợp đồng API với chính sách lưu trữ.
5. Đo hiệu năng khi bind nhiều null với batch lớn, nếu driver thường xuyên đọc `ParameterMetaData` để suy ra kiểu. Trong một số cấu hình/phiên bản Spring, gán SQL type rõ giúp tránh lỗi hoặc chi phí metadata; mức lợi ích cần đo trên driver thật.
6. Kiểm thử rollback/transaction cho chuỗi cập nhật quan trọng; SQL default và bind null không tự biến một batch thành giao dịch nguyên tử.
7. Đối với PostgreSQL array/JSON/UUID, kiểm thử phiên bản driver, SQL cast, mapper và các giá trị null thực tế trước khi đưa vào production.

### Quy tắc ghi nhớ

**Không có giá trị, chủ động lưu SQL NULL, và dùng giá trị mặc định là ba lựa chọn riêng.** Hãy xác định ý nghĩa ở API/service, chọn SQL phản ánh đúng ý nghĩa đó, khai báo JDBC type rõ cho các tham số null đặc biệt, và giữ được phân biệt SQL NULL với chuỗi/mảng/JSON rỗng khi đọc trở lại.

## Tài liệu tham khảo chính thức

- [Spring Framework – Providing SQL Type Information for Parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `int[] argTypes`, `SqlParameterValue`, `MapSqlParameterSource` và các kiểu đặc biệt.
- [Spring Framework – JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `update`, `queryForObject`, `execute` và `RowMapper`.
- [PostgreSQL – Default Values](https://www.postgresql.org/docs/current/ddl-default.html): cột bị bỏ qua khi chèn, default của schema và biểu thức default.
- [PostgreSQL – INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `DEFAULT VALUES`, `DEFAULT` trong danh sách values, `RETURNING`.
- [PostgreSQL – JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): phân biệt JSON `null` với SQL `NULL`.
- [PostgreSQL – Arrays](https://www.postgresql.org/docs/current/arrays.html): cú pháp `ARRAY` và mảng rỗng.
- [pgJDBC – JDBC driver documentation](https://jdbc.postgresql.org/documentation/): binding `UUID`, `ARRAY` và dữ liệu vendor-specific.
