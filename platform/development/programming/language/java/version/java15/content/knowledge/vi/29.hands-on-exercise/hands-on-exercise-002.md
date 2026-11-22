# Viết SQL tham số hóa và dữ liệu kiểm thử JSON — thực hành Java 15+

> **Bối cảnh:** Java 15 là tên module học; `PreparedStatement` thuộc JDBC từ lâu và **không phải tính năng mới của Java 15**. Kỹ thuật tách cấu trúc SQL khỏi dữ liệu tiếp tục là lựa chọn chuẩn trên các phiên bản Java hiện đại. Bài thực hành dùng **Java 17 trở lên**, JDBC, cơ sở dữ liệu H2 chạy trong bộ nhớ và Jackson 3 để đọc bộ tình huống JSON. Các phiên bản thư viện trong mẫu đều thuộc các dòng phát hành hiện hành.

## 1. Mục tiêu và kết quả mong đợi

Sau bài này, bạn cần có thể:

1. Giải thích vì sao nối trực tiếp dữ liệu người dùng vào câu SQL dễ dẫn đến **SQL injection** và cách bind biến `?` bằng `PreparedStatement`.
2. Tạo SQL cố định có điều kiện lọc dữ liệu theo **tenant** và bind cả tenant ID lẫn giá trị tìm kiếm đúng thứ tự.
3. Tạo bộ **JSON test cases** kiểm chứng giá trị thường, dấu nháy đơn, Unicode, chuỗi trông giống SQL injection, ký tự `%`/`_`, dữ liệu không tìm thấy, dữ liệu sai kiểu, `null` và trường bị thiếu.
4. Kiểm tra lỗi parse JSON tách biệt lỗi validation; xác định kỳ vọng cho từng case bằng ID bản ghi, thay vì chỉ hỏi “có ném exception không?”.
5. Chạy một chương trình Java thật với JDBC/H2, tự xác minh kết quả rồi đưa những nguyên tắc tương tự vào test tích hợp của dự án.
6. Nhận diện ranh giới của parameterization: placeholder bind **giá trị**, còn tên bảng, cột, hướng sắp xếp và cấu trúc SQL phải được quản lý bằng mã nguồn/allowlist.

Luồng dữ liệu dùng trong ví dụ:

```text
cases.json (dữ liệu kiểm thử)
    |
    v
Jackson JsonMapper -> JsonNode -> kiểm tra kiểu, null, độ dài
    |
    v
String title  +  tenantId từ ngữ cảnh tin cậy
    |
    v
PreparedStatement: SELECT ... WHERE tenant_id = ? AND title = ?
    |                                   |                 |
    |                             setLong(1, ...)    setString(2, ...)
    v
JDBC driver -> database -> ResultSet -> List<Integer>
    |
    v
So sánh với expectedIds trong JSON
```

**Nguyên tắc then chốt:** dữ liệu JSON kiểm thử gồm hai loại thông tin khác nhau. `title` là **đầu vào mô phỏng cho ứng dụng**; `expectedIds`/`error` là **kỳ vọng dành riêng cho bộ test**, không được xem là điều kiện SQL do client cung cấp. Trong ứng dụng thật, tenant ID phải lấy từ ngữ cảnh đã xác thực và kiểm tra quyền, không tin tenant ID tùy ý gửi trong JSON.

## 2. SQL tham số hóa hoạt động như thế nào?

### 2.1. Cách không an toàn: ghép input vào cú pháp SQL

Đây là **đoạn minh họa anti-pattern, không dùng trong sản phẩm**:

```java
String unsafeSql = "SELECT id FROM documents WHERE title = '" + userTitle + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(unsafeSql);
```

Khi `userTitle` là `x' OR 1=1 --`, dữ liệu có thể làm thay đổi điều kiện SQL vì dấu nháy đơn đóng literal, `OR 1=1` thêm điều kiện luôn đúng, còn `--` bắt đầu comment trong nhiều SQL dialect. Hậu quả tùy dialect, câu SQL hoàn chỉnh và quyền DB; điều đáng quan tâm là **input đã được diễn giải thành cú pháp**.

Cũng không an toàn nếu gọi `prepareStatement` **sau khi** ghép chuỗi:

```java
String alreadyUnsafe =
        "SELECT id FROM documents WHERE title = '" + userTitle + "'";
PreparedStatement ps = connection.prepareStatement(alreadyUnsafe);
```

`prepareStatement` không thể đảo ngược việc dữ liệu không tin cậy đã bị đặt vào SQL text.

### 2.2. Cách đúng: SQL structure cố định, bind value riêng

```java
String sql =
        "SELECT id FROM documents WHERE tenant_id = ? AND title = ? ORDER BY id";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, trustedTenantId);
    ps.setString(2, userTitle);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("id"));
        }
    }
}
```

Đây là **đoạn minh họa trong bối cảnh đã có `connection`, `trustedTenantId`, `userTitle`**; chương trình độc lập hoàn chỉnh nằm ở mục 4.

- `?` là parameter marker cho **giá trị**; JDBC đếm chỉ số từ **1**, không phải từ 0.
- `setLong(1,...)` và `setString(2,...)` gửi giá trị cùng kiểu tới driver, tách khỏi phần cú pháp SQL cố định.
- Dấu `'`, khoảng trắng, `--` hoặc `OR` bên trong `userTitle` trở thành dữ liệu literal cần so sánh với cột `title`.
- `executeQuery()` trả `ResultSet` cho `SELECT`; `executeUpdate()` dùng cho `INSERT`, `UPDATE`, `DELETE` khi muốn lấy số bản ghi bị tác động. Với batch nhiều lần insert có thể dùng `addBatch()` và `executeBatch()`.
- `try-with-resources` giải phóng `PreparedStatement` và `ResultSet` ngay cả khi truy vấn hoặc mapping dữ liệu thất bại.
- Parameterization **không tự cấp quyền đọc dữ liệu** và không đảm bảo logic truy vấn đúng; ứng dụng vẫn cần kiểm tra quyền, tenant isolation, phạm vi transaction, giới hạn lượng dữ liệu và ràng buộc schema.

## 3. Dự án mẫu đầy đủ chạy trên Java 17+

Ví dụ dùng **H2 2.5.252** làm JDBC database trong bộ nhớ, **Jackson 3.2.4** để đọc JSON và **Maven** để biên dịch. Mỗi lần chạy chương trình là một lần tạo dữ liệu mới; không cần cài một database server.

Cấu trúc thư mục:

```text
sql-json-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── SqlJsonWorkshop.java
        └── resources/
            └── cases.json
```

Trong dự án dùng Gradle/Spring Boot hiện có, có thể sử dụng các dependency được quản lý bởi BOM tương ứng và đưa bộ JSON thành test resource; Maven ở đây chỉ để bài tự chạy độc lập.

### 3.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>sql-json-test</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <version>2.5.252</version>
    </dependency>
    <dependency>
      <groupId>tools.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>3.2.4</version>
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
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Mẫu dùng Java 17 để có baseline chạy phổ biến; `JsonMapper` và `JsonNode` thuộc **Jackson 3** với package `tools.jackson.*`. Jackson 3 có các method mới như `isString()` và `stringValue()`; không dùng các alias cũ đã deprecated khi viết mã mới. Nếu một dự án đang dùng Jackson 2.x thì package/API có khác, cần theo version được dự án quản lý, không trộn dependency Jackson 2/3 tùy tiện.

### 3.2. `src/main/resources/cases.json`: dữ liệu test và kết quả kỳ vọng

```json
{
  "cases": [
    {"name":"exact match", "title":"Java 15", "expectedIds":[1]},
    {"name":"apostrophe", "title":"O'Reilly", "expectedIds":[2]},
    {"name":"unicode", "title":"Tài liệu tiếng Việt", "expectedIds":[3]},
    {"name":"SQL injection-looking literal", "title":"x' OR 1=1 --", "expectedIds":[4]},
    {"name":"percent and underscore", "title":"50%_done", "expectedIds":[5]},
    {"name":"tenant isolation", "title":"Nội bộ", "expectedIds":[]},
    {"name":"not found", "title":"Không có", "expectedIds":[]},
    {"name":"missing title", "error":"TITLE_REQUIRED"},
    {"name":"JSON null", "title":null, "error":"TITLE_REQUIRED"},
    {"name":"wrong numeric type", "title":15, "error":"TITLE_TYPE"},
    {"name":"wrong object type", "title":{"x":1}, "error":"TITLE_TYPE"},
    {"name":"blank title", "title":"   ", "error":"TITLE_BLANK"},
    {"name":"too long", "title":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "error":"TITLE_TOO_LONG"}
  ]
}
```

Đây là một **file JSON hợp lệ duy nhất** gồm 13 tình huống. Khi input hợp lệ, `expectedIds` chứa các ID phải nhận được. Khi input sai hợp đồng nghiệp vụ, `error` là mã lỗi mong đợi; dữ liệu JSON `null` khác với **không có field** trong JSON nhưng bài này chủ đích ánh xạ cả hai về `TITLE_REQUIRED`. Trường `name` chỉ phục vụ mô tả lỗi test.

Những ca quan trọng:

- `apostrophe` chứng minh dấu nháy đơn là dữ liệu, vẫn tìm đúng dòng.
- `SQL injection-looking literal` kiểm tra giá trị `x' OR 1=1 --` được **lưu thật trong DB** và truy vấn phải chỉ trả về ID 4. Điều này chặt hơn chỉ kiểm tra “không bị crash”: nếu nối chuỗi vào SQL, nó có nguy cơ làm thay đổi logic truy vấn.
- `percent and underscore` dùng điều kiện `title = ?` nên `%` và `_` chỉ là ký tự thông thường, không phải wildcard; riêng `LIKE` có ngữ nghĩa khác, xem mục 6.
- `tenant isolation` nhắm tới bản ghi có thật trong tenant khác nhưng bắt buộc trả về mảng rỗng.
- `wrong numeric type` và `wrong object type` chứng minh bộ parser/validator không tự chuyển số hoặc object thành chuỗi title.
- `too long` xác nhận ứng dụng chặn đầu vào dài hơn giới hạn do ví dụ quy định trước khi driver thực thi SQL.

Để kiểm thử **JSON sai cú pháp**, không thể đưa một fragment JSON sai vào trong file `cases.json` vì như vậy sẽ khiến cả fixture không parse được. Chương trình kiểm tra riêng một fragment `{"title":` để khẳng định parser ném lỗi. Việc phân biệt **lỗi cú pháp JSON** với **lỗi hợp đồng dữ liệu sau parse** là bắt buộc trong thiết kế test.

### 3.3. `src/main/java/demo/SqlJsonWorkshop.java`

```java
package demo;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import java.io.InputStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public final class SqlJsonWorkshop {
    private static final JsonMapper JSON = new JsonMapper();

    // Chỉ chuyển JSON String thật sang String Java; không ép Number/Object thành text.
    static String requireTitle(JsonNode test) {
        JsonNode title = test.path("title");
        if (title.isMissingNode() || title.isNull())
            throw new IllegalArgumentException("TITLE_REQUIRED");
        if (!title.isString())
            throw new IllegalArgumentException("TITLE_TYPE");

        String value = title.stringValue();
        if (value.isBlank())
            throw new IllegalArgumentException("TITLE_BLANK");
        if (value.length() > 120)
            throw new IllegalArgumentException("TITLE_TOO_LONG");
        return value;
    }

    // trustedTenant được cung cấp bởi phía gọi đáng tin cậy, không lấy từ JSON.
    static List<Integer> findIds(Connection conn, long trustedTenant, String title)
            throws Exception {
        String sql =
                "SELECT id FROM documents WHERE tenant_id = ? AND title = ? ORDER BY id";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, trustedTenant);
            ps.setString(2, title);

            try (ResultSet rs = ps.executeQuery()) {
                List<Integer> ids = new ArrayList<>();
                while (rs.next()) ids.add(rs.getInt("id"));
                return ids;
            }
        }
    }

    // Chuẩn bị dữ liệu rõ ràng, có cả chuỗi trông giống SQL injection.
    static void seed(Connection conn) throws Exception {
        try (Statement stmt = conn.createStatement()) {
            stmt.executeUpdate("CREATE TABLE documents "
                    + "(id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, "
                    + "title VARCHAR(120) NOT NULL)");
        }

        Object[][] rows = {
            {1, 7L, "Java 15"},
            {2, 7L, "O'Reilly"},
            {3, 7L, "Tài liệu tiếng Việt"},
            {4, 7L, "x' OR 1=1 --"},
            {5, 7L, "50%_done"},
            {6, 8L, "Nội bộ"}
        };

        try (PreparedStatement ps = conn.prepareStatement(
                "INSERT INTO documents (id, tenant_id, title) VALUES (?, ?, ?)")) {
            for (Object[] row : rows) {
                ps.setInt(1, (Integer) row[0]);
                ps.setLong(2, (Long) row[1]);
                ps.setString(3, (String) row[2]);
                ps.addBatch();
            }
            ps.executeBatch();
        }
    }

    public static void main(String[] args) throws Exception {
        try (Connection conn = DriverManager.getConnection(
                "jdbc:h2:mem:sqljson", "sa", "")) {
            seed(conn);

            try (InputStream in =
                         SqlJsonWorkshop.class.getResourceAsStream("/cases.json")) {
                if (in == null) throw new IllegalStateException("Missing cases.json");

                JsonNode root = JSON.readTree(in);
                if (root == null || !root.path("cases").isArray())
                    throw new IllegalArgumentException("cases must be a JSON array");

                int passed = 0;
                for (JsonNode test : root.path("cases")) {
                    String name = test.path("name").stringValue();

                    try {
                        String title = requireTitle(test);

                        if (!test.path("error").isMissingNode())
                            throw new AssertionError("Expected error in " + name);

                        List<Integer> expectedIds = new ArrayList<>();
                        for (JsonNode id : test.path("expectedIds"))
                            expectedIds.add(id.asInt());

                        List<Integer> actualIds = findIds(conn, 7L, title);
                        if (!expectedIds.equals(actualIds))
                            throw new AssertionError(name + ": expected " + expectedIds
                                    + ", actual " + actualIds);

                    } catch (IllegalArgumentException badValue) {
                        JsonNode error = test.path("error");
                        if (error.isMissingNode()
                                || !badValue.getMessage().equals(error.stringValue()))
                            throw new AssertionError(
                                    name + ": unexpected validation failure", badValue);
                    }
                    passed++;
                }

                // Phép thử cú pháp JSON sai, được tách khỏi file fixture hợp lệ.
                try {
                    JSON.readTree("{\"title\":");
                    throw new AssertionError("Malformed JSON was accepted");
                } catch (JacksonException expectedFailure) {
                    passed++;
                }

                System.out.println("PASS " + passed + " cases");
            }
        }
    }
}
```

Giải thích các quyết định trong chương trình:

1. `root.path("cases")` và `test.path("title")` cho phép phát hiện field thiếu thông qua `isMissingNode()`; JSON `null` được nhận diện bằng `isNull()`. `isString()` từ Jackson 3 kiểm tra đúng loại dữ liệu, rồi `stringValue()` lấy giá trị mà không chuyển đổi ngầm số hoặc object.
2. `findIds` chỉ lắp SQL từ literal do mã nguồn kiểm soát. `tenant_id` và `title` đều bind qua `?`; chuỗi tấn công không được parser SQL coi là biểu thức.
3. `ORDER BY id` bảo đảm thứ tự kết quả ổn định để so sánh `List<Integer>`. Việc có thứ tự xác định giúp test không ngầm phụ thuộc execution plan.
4. `seed` tạo 6 bản ghi, trong đó ID 6 thuộc tenant 8. Bài test luôn truy vấn với tenant 7; nó phải không thấy ID 6 kể cả khi client tìm đúng title.
5. Dùng `addBatch` và `executeBatch` để khởi tạo dữ liệu thông qua `PreparedStatement`. `Statement` chỉ dùng để chạy câu `CREATE TABLE` **cố định** do lập trình viên viết; không có phần ghép từ input.
6. `AssertionError` làm bài test thất bại ngay khi kết quả hoặc error code lệch expected. `IllegalArgumentException` chỉ là lỗi validation có chủ đích; sai cú pháp JSON được kiểm tra riêng với `JacksonException`.
7. Với sản phẩm, nên tách repository, DTO validation, test fixture và test runner thành từng lớp; gộp trong một file ở đây để người học kiểm chứng hành vi end-to-end ngay lập tức.

### 3.4. Chạy và đối chiếu stdout

Đảm bảo máy có Maven 3.9+ và JDK 17+; đứng tại thư mục `sql-json-lab` rồi chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SqlJsonWorkshop
```

Kết quả của chương trình khi các thư viện được tải thành công và tất cả phép kiểm tra đều đúng:

```text
PASS 14 cases
```

**Kết quả này đã được chạy kiểm chứng trên JDK 24, Maven 3.9.12**, với H2 2.5.252 và Jackson 3.2.4. Mười ba case từ JSON cộng một case JSON sai cú pháp tạo thành 14 kiểm tra. Nếu một case thất bại, chương trình ném `AssertionError` và build được đánh dấu lỗi. Khi đưa vào CI thật, nên đặt các kiểm tra thành JUnit Jupiter test trong pha `test` để `mvn test` chạy mặc định; mẫu trên chạy bằng `exec:java` theo đúng hướng dẫn.

## 4. Kết quả mong đợi và cách đọc từng nhóm test

| Case | SQL có chạy không? | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- | --- |
| `exact match` | Có | `[1]` | Query tìm đúng title |
| `apostrophe` | Có | `[2]` | Nháy đơn giữ nguyên như dữ liệu |
| `unicode` | Có | `[3]` | UTF-8 trong fixture và JDBC được giữ chính xác |
| `SQL injection-looking literal` | Có | `[4]` | Input đặc biệt chỉ khớp đúng một row, không làm đổi SQL |
| `percent and underscore` | Có | `[5]` | Với toán tử `=`, `%` và `_` không là wildcard |
| `tenant isolation` | Có | `[]` | Row 6 tồn tại nhưng khác tenant |
| `not found` | Có | `[]` | Không khớp là kết quả rỗng hợp lệ |
| `missing title` | Không | `TITLE_REQUIRED` | Phân biệt field vắng mặt |
| `JSON null` | Không | `TITLE_REQUIRED` | Phân biệt JSON `null` với Java String literal `"null"` |
| `wrong numeric type` | Không | `TITLE_TYPE` | Tránh ép `15` thành `"15"` |
| `wrong object type` | Không | `TITLE_TYPE` | Tránh dùng `{"x":1}` như title |
| `blank title` | Không | `TITLE_BLANK` | Giới hạn input chỉ có whitespace |
| `too long` | Không | `TITLE_TOO_LONG` | Kiểm tra giới hạn 120 UTF-16 code units của ví dụ |
| malformed JSON text | Không | `JacksonException` | Chặn JSON sai ngay ở bước parse |

Kỳ vọng `expectedIds` **không thể dùng như kết quả thật**. Test phải đọc kết quả từ `ResultSet`, so sánh từng ID với mảng JSON rồi fail nếu khác. Khi chỉ kiểm tra số hàng hoặc “không có exception”, một lỗ hổng truy vấn trả thừa dữ liệu vẫn có thể bị bỏ sót.

Trong bộ test lớn, nên đặt tên case thể hiện ý nghĩa nghiệp vụ, không chỉ đặt tên `test1`, `test2`. Ghi rõ **setup → input → hành vi mong đợi → trạng thái DB sau chạy**. Với thao tác ghi, kiểm tra cả dữ liệu có bị sửa ngoài phạm vi dự kiến không.

## 5. Phân biệt JSON hợp lệ, dữ liệu hợp lệ và truy vấn SQL an toàn

Ba cổng kiểm tra giải quyết ba loại vấn đề khác nhau.

**Cổng 1 — JSON syntax:** đầu vào có parse đúng JSON không? `{"title":"ok"}` là JSON hợp lệ; `{"title":` sai vì thiếu giá trị và dấu đóng. Dùng JSON parser chuyên dụng. Không parse bằng `String.split`, regex tự chế hoặc cách bỏ thủ công dấu nháy, vì JSON có escape, Unicode, object/array lồng nhau và các quy tắc cú pháp không đơn giản.

**Cổng 2 — schema/validation:** JSON hợp lệ chưa chắc là dữ liệu ứng dụng chấp nhận. `{"title":15}` là JSON hợp lệ nhưng bài thực hành yêu cầu `title` phải là string. `{"title":null}` hay `{}` cũng hợp lệ về cú pháp, nhưng thiếu title để tìm kiếm. Validation cần diễn đạt hợp đồng: kiểu, field bắt buộc, độ dài, ký tự cho phép, miền giá trị, số phần tử, giới hạn nesting/payload.

**Cổng 3 — SQL binding/authorization:** một giá trị string hợp lệ **vẫn có thể chứa** `'`, `--`, `;` hoặc nội dung trông giống SQL. Không nên dùng input validation như biện pháp thay thế cho bind parameter. Ngược lại, dùng `PreparedStatement` cũng không thay thế kiểm tra quyền đọc/sửa dữ liệu, hoặc giới hạn query quá nặng.

Ví dụ ba dạng input khác nhau:

```json
{"title":"O'Reilly"}
```

```json
{"title":15}
```

```text
{"title":
```

Trường hợp thứ nhất là JSON hợp lệ, title hợp lệ và được bind nguyên văn vào SQL. Trường hợp thứ hai JSON hợp lệ nhưng bị `TITLE_TYPE`. Trường hợp cuối chưa parse được nên báo lỗi cú pháp trước khi đến bước validation.

### 5.1. JSON và SQL `NULL` không hoàn toàn tương đương

Có ba tình huống cần xác định riêng trong hợp đồng API:

- **Thiếu field:** `{}` — không có property `title`.
- **Field có JSON `null`:** `{"title":null}` — property có tồn tại nhưng mang giá trị JSON null.
- **Field là chuỗi "null":** `{"title":"null"}` — string bình thường gồm bốn ký tự, **không phải SQL NULL**.

Nếu yêu cầu nghiệp vụ cho phép gửi `null` để cập nhật cột nullable, hãy bind bằng JDBC với SQL type rõ ràng, ví dụ:

```java
// Minh họa khi đã có PreparedStatement updatePs với cột VARCHAR nullable.
if (note == null) {
    updatePs.setNull(1, java.sql.Types.VARCHAR);
} else {
    updatePs.setString(1, note);
}
```

Không đặt giá trị null vào SQL text bằng thao tác nối `"NULL"`; không dùng `WHERE col = NULL` vì trong SQL cần `IS NULL` để kiểm tra null (và trong logic ba giá trị, `col = NULL` không trả TRUE). Nếu API phân biệt “không gửi field” với “gửi null để xóa giá trị”, phải thiết kế DTO/patch semantics thể hiện rõ sự khác biệt đó.

### 5.2. Kiểm thử số, ngày giờ và Unicode

Ví dụ chỉ dùng cột `INTEGER`, `BIGINT` và `VARCHAR`, nhưng hệ thống thực tế cần kiểm tra tương thích kiểu:

- ID số: ép kiểu có kiểm tra range, không cho JSON `"15"` thay thế JSON number nếu hợp đồng yêu cầu số.
- Giá tiền: ưu tiên `BigDecimal` và kiểu SQL `DECIMAL(p,s)`, tránh dùng `double` rồi so bằng kỳ vọng chính xác tiền tệ.
- Ngày: dùng `LocalDate` và JDBC mapping tương ứng; timestamp có múi giờ cần thống nhất kiểu lưu trữ và zone.
- Unicode: dùng fixture UTF-8, thêm chuỗi có dấu tiếng Việt, emoji/supplementary code point và khoảng trắng đặc biệt. `String.length()` đếm UTF-16 code units; giới hạn độ dài do nghiệp vụ đặt cần rõ đang đếm byte, code point hay code units.
- Chuỗi rất dài, mảng quá nhiều phần tử hoặc nesting quá sâu: đặt giới hạn kích thước request/parser, số kết quả và thời gian query. Không để test dữ liệu vô hạn làm cạn bộ nhớ/CPU.
- Giá trị `null` khi đọc từ `ResultSet`: với getter kiểu primitive như `getInt()`, dùng `wasNull()` nếu cần phân biệt SQL NULL với giá trị 0.

## 6. Các biến thể SQL dễ bị hiểu sai

### 6.1. `LIKE`: chống SQL injection chưa đủ để chống wildcard ngoài ý muốn

Trong truy vấn ở mục 3, `title = ?` so sánh đúng literal. Nếu thay bằng `title LIKE ?`, hai ký tự `%` và `_` trở thành wildcard theo ngữ nghĩa `LIKE`. Parameterization vẫn ngăn chúng thay đổi cấu trúc câu SQL nhưng **không tự escape wildcard**.

Khi nghiệp vụ cần tìm substring theo nghĩa literal, có thể dùng escape character do ứng dụng chọn:

```java
static String escapeLikeLiteral(String text) {
    return text.replace("!", "!!")
               .replace("%", "!%")
               .replace("_", "!_");
}

// Minh họa: SQL và ? cố định, escapedTerm được bind bằng setString.
String sql = "SELECT id FROM documents WHERE tenant_id = ? "
           + "AND title LIKE ? ESCAPE '!' ORDER BY id";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, trustedTenantId);
    ps.setString(2, "%" + escapeLikeLiteral(searchTerm) + "%");
    // executeQuery() và xử lý ResultSet như phần trước.
}
```

Đoạn trên minh họa SQL chuẩn thông dụng; xác minh cú pháp escape và behavior trên chính database sản phẩm. Ký tự escape `!` được viết trong SQL literal cố định, không lấy từ input. Thêm test cho `"50%_done"`, `"!"`, `"a!%b"` và chuỗi rỗng theo hợp đồng tìm kiếm.

### 6.2. Không bind tên bảng, tên cột hoặc `ORDER BY` bằng `?`

Parameter marker chỉ đại diện cho **giá trị** trong vị trí cho phép, không biến thành identifier hoặc SQL keyword. Ví dụ `ORDER BY ?` nếu được database chấp nhận thì nó **không mang ý nghĩa chọn cột theo tên do user gửi**, và không giải quyết nhu cầu sắp xếp linh hoạt.

Dùng mapping cố định, reject giá trị ngoài allowlist:

```java
static String trustedOrderBy(String requestedSort) {
    return switch (requestedSort) {
        case "title" -> "title ASC, id ASC";
        case "newest" -> "id DESC";
        default -> throw new IllegalArgumentException("SORT_NOT_ALLOWED");
    };
}

// Chỉ ghép token tạo ra từ switch do mã nguồn kiểm soát.
String sql = "SELECT id FROM documents WHERE tenant_id = ? ORDER BY "
        + trustedOrderBy(sortOption);
```

**Quan trọng:** `sortOption` không bao giờ được nối trực tiếp vào SQL. Nếu có lựa chọn direction, table hay column, ánh xạ mỗi lựa chọn hợp lệ sang identifier/keyword **cố định do lập trình viên định nghĩa**. Thao tác phân quyền vẫn phải xác minh người dùng có quyền đối với dữ liệu được sắp xếp.

### 6.3. Mệnh đề `IN` với số lượng item thay đổi

Một placeholder `?` không thể thay thế cho cả danh sách giá trị của `IN` theo cách truyền một chuỗi `"1,2,3"`. Cách làm đúng là tự tạo **số lượng marker** từ danh sách đã kiểm tra giới hạn, rồi bind từng giá trị:

```java
// Minh họa: ids là danh sách Integer đã được xác thực.
if (ids.isEmpty()) return List.of(); // Trong hàm trả List<Integer>.
if (ids.size() > 100) throw new IllegalArgumentException("TOO_MANY_IDS");

String placeholders = String.join(",",
        java.util.Collections.nCopies(ids.size(), "?"));
String sql = "SELECT id FROM documents WHERE tenant_id = ? "
           + "AND id IN (" + placeholders + ") ORDER BY id";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, trustedTenantId);
    for (int index = 0; index < ids.size(); index++) {
        ps.setInt(index + 2, ids.get(index));
    }
    // executeQuery() rồi duyệt ResultSet; điều kiện tenant vẫn bắt buộc.
}
```

Đây là **đoạn minh họa bên trong một hàm** đã có các biến `ids`, `connection`, `trustedTenantId` và trả `List<Integer>`; không phải chương trình Java độc lập. Chỉ nối các marker `?` do chính chương trình sinh ra, tuyệt đối không nối trực tiếp các ID JSON vào SQL text. Đặt giới hạn số ID, xử lý mảng rỗng rõ ràng và kiểm tra hiệu năng.

### 6.4. `PreparedStatement` và transaction khi ghi dữ liệu

Ví dụ `SELECT` là đọc dữ liệu. Nếu chuyển sang `INSERT` hoặc `UPDATE`:

- Bind mọi giá trị người dùng như dữ liệu. Kiểm tra số hàng từ `executeUpdate()` để phát hiện cập nhật ngoài kỳ vọng.
- Với nhiều câu lệnh phải thành công hoặc thất bại cùng nhau, dùng transaction (`setAutoCommit(false)`, `commit()`/`rollback()`), và khôi phục trạng thái kết nối nếu sử dụng pool.
- Không để logic như `UPDATE documents SET title = ?` thiếu `WHERE tenant_id = ? AND id = ?`: SQL được tham số hóa vẫn có thể sửa **toàn bộ bảng** nếu điều kiện lọc bị bỏ.
- Tránh log tham số chứa bí mật/PII cùng query; khi cần chẩn đoán, dùng mã lỗi và thông tin tối thiểu đủ tái hiện.

## 7. Kiểm thử đáng tin trên database thật và database test

H2 in-memory phù hợp cho thực hành và kiểm tra nguyên tắc JDBC phổ thông, nhưng **không chứng minh** câu SQL hoạt động giống PostgreSQL/MySQL/SQL Server/Oracle trong mọi trường hợp. Khác biệt có thể xuất hiện ở kiểu `JSON/JSONB`, collation, Unicode sorting, transaction isolation, `LIKE` escape, tính năng index và dialect-specific operators.

Một chiến lược hợp lý cho dự án:

1. **Unit test validator:** dùng JSON fixture để kiểm thử field thiếu/null/sai kiểu/độ dài; không cần DB cho các case này.
2. **Integration test repository:** chạy SQL thật với schema và dữ liệu được tạo trước test. Test cả happy path, injection-like literal, tenant isolation, SQL NULL, duplicate keys, update count và rollback.
3. **Database parity test:** với tính năng đặc thù của DB sản phẩm, chạy test trên chính engine/version tương thích (ví dụ container database trong CI). H2 chỉ là database test tiện lợi cho demo.
4. **API test:** gửi HTTP JSON thật và kiểm tra status code, error body, response IDs, authentication/authorization. Một lỗi JSON sai cú pháp và một lỗi schema phải có cách phản hồi rõ, nhất quán.
5. **Performance/limit test:** kiểm tra số phần tử JSON, độ dài chuỗi, paging, SQL timeout, các trường hợp tải dữ liệu lớn. Chạy có giới hạn và dữ liệu test không chứa bí mật thật.

Nếu dùng JUnit Jupiter (hiện có dòng JUnit 6), tách từng case thành `@ParameterizedTest` hoặc `@Test`, thêm dataset fixture dưới `src/test/resources` và để build task chạy tự động. Khi test có giao dịch, đảm bảo rollback/cleanup dữ liệu để các case độc lập và có thể chạy lại nhiều lần. Không lạm dụng mock `PreparedStatement` để thay cho integration test: mock có thể chứng minh đúng phương thức được gọi, nhưng không chứng minh câu SQL và driver xử lý thế nào.

### 7.1. Dữ liệu kiểm thử JSON nên được thiết kế theo cặp đối chiếu

| Nhóm input | Cặp đối chiếu | Rủi ro phát hiện |
| --- | --- | --- |
| Chuỗi bình thường | `Java 15` / `java 15` | Collation có phân biệt hoa thường không |
| Dấu quote | `O'Reilly` / `O''Reilly` | Tự sửa quote trái hợp đồng, sai kết quả |
| Injection-looking | `x' OR 1=1 --` / `x` | Bị ghép SQL, trả quá nhiều row |
| Wildcard | `50%_done` / `50ABdone` | Nhầm `LIKE` với `=`, wildcard ngoài ý muốn |
| Tenant | cùng title ở tenant 7 và tenant 8 | Lộ dữ liệu giữa tenant |
| Unicode | NFC / NFD, dấu tiếng Việt, emoji | Chuẩn hóa khác nhau hoặc collation bất ngờ |
| JSON field | missing / null / "" / "   " | Gộp sai các trạng thái đầu vào |
| Numeric boundary | `0` / `-1` / số vượt miền | Chuyển kiểu, tràn số, query lỗi |
| SQL nullable | JSON null / chuỗi `"null"` | Nhầm SQL NULL và literal text |
| Dữ liệu lỗi cú pháp | JSON cụt / escape JSON sai | Parser phải từ chối trước khi vào DB |

Không mặc định hai chuỗi khác hoa thường hoặc khác chuẩn Unicode phải tương đương; đây là **quyết định nghiệp vụ kết hợp collation/index của DB**. Với test, đặt expected dựa trên hợp đồng sản phẩm và cấu hình database đã chọn.

### 7.2. Kiểm thử “không làm thay đổi dữ liệu” khi đầu vào có payload SQL

Với `SELECT`, ngoài so sánh chính xác `expectedIds`, có thể:

- Kiểm tra số row trong bảng test trước/sau các input có `'`, `;`, `--`.
- Kiểm tra một bản ghi thuộc tenant khác không xuất hiện trong kết quả.
- Đảm bảo driver không chấp nhận nhiều câu lệnh được nối từ dữ liệu input.
- Kiểm tra người dùng đọc được **chỉ tập bản ghi được phép** theo rule ứng dụng. Bảo vệ query syntax và bảo vệ authorization là hai trách nhiệm riêng biệt.

Không cần “tấn công” vào dữ liệu thật; tất cả ví dụ chỉ dùng một DB in-memory được khởi tạo trong bài test.

## 8. Các lỗi thường gặp cần tránh

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Ghép `title` vào SQL rồi mới tạo `PreparedStatement` | SQL injection đã xảy ra ở bước tạo query | Viết SQL text cố định với `?`, bind dữ liệu riêng |
| Tự escape dấu nháy `'` bằng thay chuỗi | Không thay được quy tắc quoting/encoding của từng database | `setString`, `setInt`, `setLong`, `setNull` đúng kiểu |
| Cho phép client chọn tenant ID trực tiếp | Query an toàn về cú pháp vẫn có thể lộ dữ liệu | Lấy tenant/authorization từ ngữ cảnh được xác thực |
| Dùng `?` để thay tên cột hoặc `ASC/DESC` | Placeholder là data value, không phải identifier/keyword | Map lựa chọn sang SQL token thuộc allowlist cố định |
| Dùng `LIKE ?` nhưng không escape `%`/`_` | Wildcard làm thay đổi số dòng khớp | Kiểm tra intent, escape wildcard nếu cần tìm literal |
| Truyền `"1,2,3"` cho một `IN (?)` | Driver bind một giá trị, không thành danh sách SQL | Tạo N placeholder và bind từng giá trị; giới hạn N |
| Tự ép mọi JSON thành string | JSON number/object/null có thể bị biến thành dữ liệu khác | Kiểm tra node type trước; Jackson 3 `isString()` |
| Xem JSON parse được nghĩa là input hợp lệ | JSON hợp lệ chưa chắc đúng schema | Kiểm tra required/type/range/length riêng |
| Chỉ kiểm tra “truy vấn không ném lỗi” | SQL injection có thể trả quá nhiều row mà vẫn chạy | So sánh ID chính xác và xác nhận không lộ tenant khác |
| Chỉ test H2 rồi kết luận mọi DB giống nhau | SQL dialect, collation, transaction có khác biệt | Integration test trên engine production |
| Thiếu `try-with-resources` | Kết nối, statement, result set có thể bị giữ lâu | Đóng tài nguyên và rollback phù hợp |
| Lưu secret/PII thật vào JSON test | Log và source repository có thể lộ dữ liệu | Dùng dữ liệu giả lập, giá trị tổng hợp |

## 9. Checklist trước khi đưa bài tập vào CI

- [ ] SQL text không nối trực tiếp dữ liệu từ JSON/HTTP/file, bao gồm cả giá trị đã trải qua validation.
- [ ] Placeholder chỉ dùng cho dữ liệu, index bắt đầu từ 1 và trùng thứ tự bind; mỗi giá trị có JDBC type thích hợp.
- [ ] Điều kiện tenant/owner, role và quyền cập nhật được ràng buộc từ ngữ cảnh tin cậy.
- [ ] JSON parser xử lý được chuỗi có escape/Unicode và phân biệt malformed JSON với valid JSON nhưng sai schema.
- [ ] Có fixture cho quote, payload giống SQL injection, wildcard, Unicode, không tìm thấy, missing, `null`, number, object, blank và quá dài.
- [ ] Test so sánh **exact result IDs/rows** và kiểm tra DB state sau các thao tác ghi.
- [ ] Có kiểm tra đặc thù SQL dialect trên database sản phẩm và không giả định hành vi H2 luôn giống DB đó.
- [ ] Test chạy lặp lại độc lập, tự khởi tạo/cleanup dữ liệu, không có secret thật.
- [ ] Với thay đổi mã nguồn, có chạy lại build/test dưới phiên bản JDK mà dự án cam kết hỗ trợ.

## Tài liệu chính thức đang áp dụng

- [Java SE — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): API bind tham số (`setString`, `setNull`, `setObject`), thực thi query và update.
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): cách phòng chống SQL injection bằng parameterized queries, allowlist và quyền tối thiểu.
- [Jackson 3 / JsonNode API](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.2.4/tools.jackson.databind/tools/jackson/databind/JsonNode.html): `isString()`, `stringValue()`, `isMissingNode()` và tree-model hiện hành.
- [Jackson 3 / ObjectMapper API](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.2.2/tools.jackson.databind/tools/jackson/databind/ObjectMapper.html): `readTree` và xử lý lỗi JSON.
- [H2 Database](https://h2database.github.io/): JDBC database nhúng/in-memory dùng cho bài kiểm thử minh họa.
