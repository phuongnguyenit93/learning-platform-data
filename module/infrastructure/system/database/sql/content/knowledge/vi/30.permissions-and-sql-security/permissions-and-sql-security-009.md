# Ký tự đại diện LIKE và ý nghĩa khác với bảo vệ SQL injection

SQL LIKE so khớp chuỗi theo một mẫu. Hai ký tự đại diện cơ bản là phần trăm (%) và gạch dưới (_):

- Phần trăm khớp không, một hoặc nhiều ký tự.
- Gạch dưới khớp đúng một ký tự theo quy tắc của hệ quản trị và kiểu dữ liệu.

Ví dụ:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'Phone%';
```

Mẫu này tìm tên bắt đầu bằng Phone. Nó không phải regular expression và cũng không phải một đoạn SQL do người dùng bổ sung.

Khi dữ liệu tìm kiếm đến từ người dùng, cần phân biệt hai vấn đề:

1. **SQL injection:** input không tin cậy bị ghép vào văn bản SQL và có thể thay đổi cú pháp hoặc logic câu lệnh.
2. **LIKE wildcard:** dù tham số đã được bind an toàn, phần trăm và gạch dưới bên trong giá trị pattern vẫn mang nghĩa wildcard, có thể làm kết quả rộng hơn dự định.

> **Prepared statement bảo vệ cấu trúc SQL. Escape LIKE bảo vệ ý nghĩa của mẫu tìm kiếm. Hai việc giải quyết hai vấn đề khác nhau và có thể cần dùng đồng thời.**

Bài thuộc module **Database SQL**, chương **Quyền và SQL an toàn**, chủ đề **“Ký tự đại diện LIKE và ý nghĩa khác với bảo vệ SQL injection”**. PostgreSQL là hệ quản trị minh họa chính; phần sau đối chiếu MySQL, SQL Server, Oracle và SQLite.

## 1. LIKE là so khớp mẫu

Giả sử có bảng:

```sql
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL
);

INSERT INTO products (product_id, product_name, category)
VALUES
    (1, 'Phone Alpha', 'mobile'),
    (2, 'Phone Beta', 'mobile'),
    (3, 'Headphone Mini', 'accessory'),
    (4, 'Phone Case', 'accessory'),
    (5, 'Smart Watch', 'wearable'),
    (6, 'Phone_Pro', 'mobile'),
    (7, '100% Cotton Cable', 'accessory'),
    (8, 'A!B Adapter', 'accessory');
```

### 1.1. Không có wildcard

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'Phone Alpha';
```

Mẫu này so khớp chuỗi theo quy tắc collation của DBMS. Nó không tự tìm chuỗi con ở giữa.

### 1.2. Bắt đầu bằng tiền tố

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'Phone%';
```

Phone% khớp tên bắt đầu bằng Phone, sau đó có thể không có ký tự hoặc có thêm bất kỳ chuỗi nào. Ví dụ Phone Alpha, Phone Beta, Phone Case và Phone_Pro.

### 1.3. Kết thúc bằng hậu tố

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%Mini';
```

%Mini khớp tên kết thúc bằng Mini, ví dụ Headphone Mini.

### 1.4. Chứa chuỗi con

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%Phone%';
```

%Phone% tìm đoạn Phone ở bất kỳ vị trí nào. Kết quả có thể gồm Phone Alpha, Phone Case và Headphone Mini.

### 1.5. Gạch dưới là wildcard

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'Phone_Pro';
```

Dấu gạch dưới ở giữa mẫu khớp một ký tự bất kỳ. Nó không có nghĩa bắt buộc phải là dấu gạch dưới literal. Mẫu có thể khớp Phone_Pro, PhoneXPro hoặc một ký tự đơn khác ở vị trí đó.

## 2. Hai wildcard cơ bản

| Ký tự | Ý nghĩa | Ví dụ |
|---|---|---|
| % | Không hoặc nhiều ký tự | Cat% khớp Cat, Cats, Cat Food |
| _ | Một ký tự | C_t khớp Cat, Cot |
| Không có wildcard | So khớp mẫu nguyên vẹn | Cat |

Thử:

```sql
SELECT
    'Cat' LIKE 'Cat%' AS percent_can_match_empty,
    'Cat' LIKE 'C_t' AS underscore_matches_one,
    'Cart' LIKE 'C_t' AS underscore_is_not_many;
```

Phần trăm có thể khớp chuỗi rỗng, nên Cat LIKE Cat% là TRUE. Gạch dưới chỉ khớp một ký tự, nên Cat LIKE C_t là TRUE còn Cart LIKE C_t là FALSE.

### 2.1. LIKE không phải regex

LIKE có ngôn ngữ pattern đơn giản hơn regular expression:

- Phần trăm khớp không hoặc nhiều ký tự.
- Gạch dưới khớp một ký tự.
- LIKE không cung cấp toàn bộ nhóm, lookahead, quantifier và lựa chọn của regex.
- Một số DBMS bổ sung cú pháp riêng; SQL Server có biểu thức ngoặc vuông.

Nếu cần regex, dùng nhóm hàm phù hợp DBMS. Không cố mô phỏng regex phức tạp bằng LIKE.

## 3. Escape wildcard để tìm ký tự literal

Giả sử người dùng nhập Phone_Pro và muốn tìm đúng dấu gạch dưới. Mẫu %Phone_Pro% chưa đáp ứng yêu cầu vì gạch dưới vẫn là wildcard.

Ta chọn dấu chấm than làm ký tự escape:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%Phone!_Pro%' ESCAPE '!';
```

Trong mẫu:

- !_ biểu diễn dấu gạch dưới literal.
- !% biểu diễn dấu phần trăm literal.
- !! biểu diễn dấu chấm than literal.
- Hai dấu phần trăm ngoài cùng vẫn là wildcard để tìm chuỗi con.

### 3.1. Tìm dấu phần trăm thật

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%100!%%' ESCAPE '!';
```

Mẫu tìm chuỗi chứa 100%. Dấu !% ở giữa là phần trăm literal; hai dấu phần trăm ngoài cùng là wildcard.

### 3.2. Tìm ký tự escape thật

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%A!!B%' ESCAPE '!';
```

Hai dấu chấm than liên tiếp biểu diễn một dấu chấm than trong dữ liệu cần tìm.

### 3.3. Hàm escape ở tầng ứng dụng

Nếu input là văn bản literal, có thể tạo pattern:

```python
def escape_like_literal(value: str) -> str:
    return (
        value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_")
    )

def contains_pattern(value: str) -> str:
    return "%" + escape_like_literal(value) + "%"
```

Phải escape chính ký tự escape trước, rồi mới escape phần trăm và gạch dưới. Nếu thay phần trăm trước, ký tự escape mới tạo có thể bị escape lần nữa và làm sai pattern.

| Input literal | Pattern contains |
|---|---|
| Phone | %Phone% |
| Phone_Pro | %Phone!_Pro% |
| 100% | %100!%% |
| A!B | %A!!B% |
| 100!_% | %100!!!_!%% |

### 3.4. Escape LIKE khác escape SQL string

- SQL string quoting xử lý dấu nháy và ranh giới literal trong câu SQL.
- LIKE escaping điều khiển việc phần trăm và gạch dưới là wildcard hay ký tự cần tìm.

Escape phần trăm và gạch dưới **không chống SQL injection**. Thay dấu nháy thủ công cũng không thay thế prepared statement.

## 4. LIKE wildcard khác SQL injection

### 4.1. SQL injection do nối input vào câu SQL

Code không an toàn:

```python
user_input = request.args["q"]

sql = (
    "SELECT product_id, product_name "
    "FROM products "
    "WHERE product_name LIKE '%" + user_input + "%'"
)
```

Người dùng có thể nhập:

```text
%' OR 1=1 --
```

Sau khi nối, câu SQL có thể thành:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%%' OR 1=1 --%';
```

Dấu nháy đóng literal, OR 1=1 thay đổi logic, và -- có thể mở đầu comment theo cú pháp DBMS. Đây là SQL injection vì input thay đổi cấu trúc câu lệnh.

### 4.2. Wildcard hợp lệ không phải injection

Xét prepared statement:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE ?;
```

Nếu bind tham số chỉ gồm dấu phần trăm, DBMS nhận một giá trị pattern hợp lệ. Nó không thể tự đóng literal hay thêm câu SQL, nhưng vẫn khớp mọi tên không NULL.

Đó là **ngữ nghĩa LIKE**, không phải SQL injection.

### 4.3. Hai lớp bảo vệ

| Trường hợp | Parameter binding | LIKE escaping |
|---|---|---|
| Input có dấu nháy | Không biến thành cú pháp SQL | Không phải nhiệm vụ của LIKE escape |
| Input có % | Không injection, nhưng vẫn wildcard | Escape thành !% nếu cần literal |
| Input có _ | Không injection, nhưng vẫn wildcard | Escape thành !_ |
| Input có %' OR 1=1 -- | Toàn bộ là giá trị, không chèn điều kiện SQL | Escape % nếu muốn literal |
| Input chọn tên bảng | Placeholder không thay identifier | Không liên quan |
| Input chọn ASC/DESC | Placeholder không thay keyword | Không liên quan |

### 4.4. Prepared statement vẫn có thể tìm quá rộng

Nếu bind pattern %100%%, truy vấn an toàn về SQL nhưng tìm các chuỗi bắt đầu bằng 100 rồi theo sau bất kỳ nội dung nào. Nó không nhất thiết tìm literal 100%.

Muốn literal, cần escape phần trăm trong pattern. Một truy vấn có thể **an toàn về SQL nhưng sai semantics tìm kiếm**.

### 4.5. Wildcard abuse là rủi ro riêng

Người dùng nhập phần trăm có thể làm truy vấn trả gần như toàn bộ dữ liệu trong phạm vi được phép. Điều này có thể gây kết quả rộng, query nặng, tải CPU/I/O và tiêu tốn băng thông.

Đó là vấn đề kiểm soát chức năng, phân quyền và tài nguyên. Không gọi mọi trường hợp nhập phần trăm là SQL injection.

## 5. Prepared statement là lớp bảo vệ chính

### 5.1. Java: nối chuỗi không an toàn

```java
String sql =
    "SELECT product_id, product_name " +
    "FROM products " +
    "WHERE product_name LIKE '%" + userInput + "%'";

Statement statement = connection.createStatement();
ResultSet rs = statement.executeQuery(sql);
```

Dữ liệu người dùng được ghép trực tiếp vào SQL text và có thể thay đổi cú pháp.

### 5.2. Java: bind pattern

```java
String sql = """
    SELECT product_id, product_name
    FROM products
    WHERE product_name LIKE ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "%" + userInput + "%");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("product_name"));
        }
    }
}
```

PreparedStatement tách giá trị khỏi cấu trúc SQL. Dấu nháy, comment marker hoặc đoạn OR 1=1 trong input không thể tự biến thành cú pháp SQL.

Nhưng phần trăm và gạch dưới trong userInput vẫn là wildcard. Nếu cần literal search, thêm lớp escape.

### 5.3. Java: bind pattern đã escape

```java
static String escapeLikeLiteral(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String sql = """
    SELECT product_id, product_name
    FROM products
    WHERE product_name LIKE ? ESCAPE '!'
    """;

String pattern =
    "%" + escapeLikeLiteral(userInput) + "%";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("product_name"));
        }
    }
}
```

Hai lớp riêng:

1. Prepared statement bảo vệ cú pháp SQL.
2. Hàm escape bảo vệ nghĩa literal của pattern LIKE.

### 5.4. Pattern search có chủ đích

Nếu tính năng cho phép người dùng nhập Phone% để tìm prefix, hãy bind nguyên pattern và giải thích cú pháp wildcard. Không escape phần trăm/gạch dưới nếu chúng là tính năng có chủ đích, nhưng vẫn giới hạn độ dài và chi phí truy vấn.

Nên tách API searchContainsLiteral(text) và searchByPattern(pattern) thay vì trộn hai chế độ.

## 6. Cú pháp theo từng DBMS

### 6.1. PostgreSQL

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE $1 ESCAPE '!';
```

PostgreSQL có ILIKE để so khớp không phân biệt hoa/thường theo quy tắc locale/collation phù hợp:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name ILIKE $1 ESCAPE '!';
```

ILIKE là mở rộng PostgreSQL, không phải cú pháp phổ quát.

Với JDBC, dùng placeholder ? trong PreparedStatement:

```java
String sql = """
    SELECT product_id, product_name
    FROM products
    WHERE product_name ILIKE ? ESCAPE '!'
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, containsPattern(userInput));
    // executeQuery...
}
```

### 6.2. MySQL

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE ? ESCAPE '!';
```

Hoặc ghép wildcard bằng CONCAT:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE CONCAT('%', ?, '%') ESCAPE '!';
```

Nếu tham số là literal, vẫn escape phần trăm, gạch dưới và ký tự escape trước khi bind.

MySQL có quy tắc backslash và SQL mode liên quan đến escape. Collation của cột/biểu thức ảnh hưởng phân biệt hoa/thường. Dùng ESCAPE rõ ràng giúp hợp đồng pattern dễ đọc hơn, nhưng phải kiểm tra cú pháp theo phiên bản và driver.

### 6.3. SQL Server

```sql
SELECT product_id, product_name
FROM dbo.products
WHERE product_name LIKE @pattern ESCAPE N'!';
```

SQL Server có wildcard dạng ngoặc vuông:

| Pattern | Ý nghĩa |
|---|---|
| [abc] | Một ký tự trong tập a, b, c |
| [a-f] | Một ký tự trong khoảng a đến f theo collation |
| [^abc] | Một ký tự không thuộc tập a, b, c |
| [_] | Dấu gạch dưới literal trong pattern SQL Server |
| [%] | Dấu phần trăm literal trong pattern SQL Server |

Ví dụ:

```sql
SELECT product_id, product_name
FROM dbo.products
WHERE product_name LIKE N'%Phone[_]Pro%';
```

Khi xây helper literal search riêng cho SQL Server, ngoài phần trăm và gạch dưới, cần xử lý cú pháp bracket [ và ] theo quy tắc SQL Server. Pattern thường dùng [ []? Không. Cách biểu diễn thường dùng là [ []? Thực tế pattern cho dấu mở ngoặc vuông là [[] và cho dấu đóng ngoặc vuông là []]. Hãy kiểm thử chuỗi pattern tạo ra trên phiên bản/collation thật.

**Bind tham số không làm mất ý nghĩa wildcard bracket của SQL Server.**

### 6.4. Oracle Database

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE :pattern ESCAPE '!';
```

Oracle hỗ trợ phần trăm, gạch dưới và ESCAPE. So khớp hoa/thường chịu ảnh hưởng collation và thiết lập ngôn ngữ; không giả định mọi schema có cùng kết quả.

### 6.5. SQLite

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE ?1 ESCAPE '!';
```

SQLite mặc định không phân biệt hoa/thường đối với phạm vi ASCII theo hành vi thông dụng, nhưng không có Unicode case folding đầy đủ cho mọi ký tự ngoài ASCII. Extension ICU hoặc collation/hàm riêng có thể thay đổi khả năng này.

Không xem PRAGMA case_sensitive_like là giải pháp mặc định cho ứng dụng mới; pragma này đã được đánh dấu deprecated trong tài liệu SQLite hiện hành.

## 7. Collation, hoa/thường và Unicode

Collation ảnh hưởng cách DBMS so sánh chuỗi: phân biệt hoa/thường, phân biệt dấu, quy tắc ngôn ngữ, thứ tự so sánh và một số hành vi liên quan Unicode/index.

Ví dụ:

```sql
WHERE product_name LIKE 'phone%'
```

có thể khớp Phone Alpha trong collation không phân biệt hoa/thường nhưng không khớp trong collation phân biệt.

| DBMS | Hành vi cần lưu ý |
|---|---|
| PostgreSQL | LIKE và ILIKE; collation/locale |
| MySQL | Collation và character set |
| SQL Server | Collation của cột/biểu thức |
| Oracle | Collation và thiết lập linguistic |
| SQLite | Mặc định case-insensitive cho ASCII; Unicode cần chú ý |

### 7.1. Một ký tự không luôn là một ký tự nhìn thấy

Gạch dưới thường được mô tả là khớp một ký tự, nhưng Unicode có thể biểu diễn một chữ nhìn thấy bằng nhiều code point, chẳng hạn ký tự cơ sở kết hợp dấu. Quy tắc engine, encoding và collation có thể khác nhau.

Không dùng LIKE với một dấu gạch dưới để xác minh số ký tự người dùng nhìn thấy trên giao diện trong mọi ngôn ngữ. Nếu cần giới hạn độ dài theo grapheme cluster, xử lý bằng thư viện Unicode ở tầng ứng dụng.

### 7.2. Khoảng trắng cuối chuỗi

Kiểu CHAR cố định, VARCHAR và collation có thể ảnh hưởng so sánh khoảng trắng cuối. Với mã định danh hoặc chuỗi cần so khớp chính xác, hãy kiểm thử khoảng trắng đầu/cuối, tab, newline, chuỗi rỗng, NULL, chữ hoa/thường và Unicode kết hợp dấu.

Không tự TRIM mọi dữ liệu nếu khoảng trắng có thể là một phần hợp lệ của giá trị.

## 8. NULL và LIKE

NULL không phải chuỗi rỗng:

```sql
SELECT
    NULL LIKE 'A%' AS null_result,
    '' LIKE 'A%' AS empty_result;
```

Biểu thức đầu trả UNKNOWN/NULL; biểu thức sau trả FALSE. Trong WHERE, chỉ điều kiện TRUE được chọn.

Nếu cột nullable và nghiệp vụ muốn coi NULL như chuỗi rỗng, có thể viết:

```sql
WHERE COALESCE(product_name, '') LIKE :pattern
```

Nhưng bọc cột bằng hàm có thể ảnh hưởng index. Hãy quyết định rõ chính sách NULL và thiết kế truy vấn tương ứng.

## 9. LIKE và chỉ mục

### 9.1. Prefix search

```sql
SELECT *
FROM products
WHERE product_name LIKE 'Phone%';
```

B-tree index có thể hỗ trợ một số prefix pattern, tùy collation, DBMS, operator class, thống kê và độ chọn lọc.

```sql
CREATE INDEX products_name_idx
ON products(product_name);
```

Trong PostgreSQL, một số collation có thể cần operator class như text_pattern_ops cho prefix matching. Không tạo index đặc biệt nếu chưa xem execution plan.

### 9.2. Suffix và contains

```sql
WHERE product_name LIKE '%Pro'
```

```sql
WHERE product_name LIKE '%Phone%'
```

Wildcard ở đầu khiến B-tree thông thường khó xác định khoảng prefix liên tục, nên truy vấn có thể phải scan nhiều dòng.

Trong PostgreSQL, pg_trgm có thể hỗ trợ tìm pattern contains bằng GIN/GiST trigram index:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm_idx
ON products
USING GIN (product_name gin_trgm_ops);
```

Đo:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM products
WHERE product_name ILIKE '%phone%';
```

Pattern quá ngắn có thể không cung cấp đủ trigram hữu ích.

### 9.3. Index trên LOWER

PostgreSQL có thể tạo expression index:

```sql
CREATE INDEX products_name_lower_idx
ON products (LOWER(product_name));
```

Truy vấn:

```sql
SELECT *
FROM products
WHERE LOWER(product_name) LIKE LOWER($1);
```

Index expression có thể hỗ trợ biểu thức tương thích. Không đảm bảo mọi dạng wildcard, collation hoặc contains pattern đều tận dụng index.

### 9.4. Đọc plan đúng cách

Seq Scan trên bảng nhỏ có thể nhanh hơn Index Scan. Khi đánh giá, hãy so cùng dữ liệu/điều kiện, xem estimated và actual rows, buffers, pattern length, selectivity và nhiều lần đo. Mục tiêu là hiệu năng phù hợp, không phải ép planner luôn chọn index.

## 10. Identifier động và SQL injection

Placeholder thường bind giá trị, không thay tên bảng, tên cột, toán tử hoặc keyword.

Câu sau không làm điều mong muốn:

```sql
SELECT * FROM ? WHERE product_name LIKE ?;
```

Nếu người dùng chọn cột sắp xếp, ánh xạ lựa chọn qua allowlist:

```java
Map<String, String> sortColumns = Map.of(
    "name", "product_name",
    "price", "unit_price",
    "id", "product_id"
);

String sortColumn = sortColumns.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Invalid sort field");
}

String sql =
    "SELECT product_id, product_name, unit_price " +
    "FROM products WHERE product_name LIKE ? " +
    "ORDER BY " + sortColumn;
```

Identifier được chọn từ tập cố định do ứng dụng kiểm soát; pattern vẫn bind. Chiều sort ASC/DESC cũng nên chọn qua allowlist.

### 10.1. Stored procedure vẫn có thể bị injection

Một stored procedure ghép input vào dynamic SQL vẫn có rủi ro. Dùng bind variable tương ứng DBMS: PostgreSQL EXECUTE ... USING, Oracle EXECUTE IMMEDIATE ... USING, SQL Server sp_executesql có tham số hoặc cơ chế prepared statement của MySQL.

Stored procedure là cách tổ chức logic, không tự làm sạch mọi input.

### 10.2. Không dùng blacklist

Không chỉ xóa dấu nháy, comment marker, dấu chấm phẩy, từ SELECT hay ký tự phần trăm. Blacklist dễ bỏ sót cú pháp và làm hỏng dữ liệu hợp lệ. Dùng bind parameters cho giá trị, allowlist cho cú pháp động và LIKE escaping cho literal pattern.

## 11. Phân quyền dữ liệu độc lập với LIKE

Một truy vấn an toàn về SQL vẫn có thể có lỗi phân quyền:

```sql
SELECT product_id, product_name
FROM products
WHERE tenant_id = :tenant_id
  AND product_name LIKE :pattern;
```

tenant_id phải lấy từ ngữ cảnh xác thực đáng tin cậy ở server hoặc được kiểm tra quyền. Nếu tin tenant_id do client tự gửi, người dùng có thể xem dữ liệu tenant khác dù truy vấn đã parameterize.

Người dùng nhập phần trăm có thể lấy mọi sản phẩm trong phạm vi được phép. Điều đó có thể quá rộng so với chức năng, nhưng không phải injection.

| Lớp | Cơ chế |
|---|---|
| Cấu trúc SQL | Prepared statement/bind parameter |
| Pattern LIKE | Escape wildcard nếu literal |
| Identifier động | Allowlist và quote theo DBMS |
| Phạm vi dữ liệu | Authorization, tenant filter, RLS/view |
| Tải hệ thống | Giới hạn input, timeout, rate limit, pagination |
| Unicode/case | Collation và kiểm thử dữ liệu thật |
| Log | Redaction và retention phù hợp |
| Dynamic SQL | Bind variable và allowlist |

Để giảm wildcard abuse, giới hạn độ dài pattern, số kết quả, thời gian query và tần suất gọi. Có thể yêu cầu độ dài tối thiểu cho contains search hoặc dùng trigram/full-text index khi phù hợp.

LIMIT không thay thế phân quyền; nó chỉ giới hạn số dòng trả về.

## 12. Literal search và pattern search là hai hợp đồng API

### 12.1. Literal search

Người dùng nhập 100% và muốn tìm đúng dấu phần trăm. Ứng dụng escape ký tự escape, phần trăm và gạch dưới, thêm wildcard nếu cần contains, bind pattern và dùng ESCAPE.

### 12.2. Pattern search

Người dùng nhập Phone% và muốn phần trăm là wildcard. Ứng dụng bind nguyên pattern, giải thích cú pháp và giới hạn tài nguyên. Không escape wildcard nếu tính năng cố ý cho phép.

Không dùng một tham số vừa literal vừa pattern theo ngữ nghĩa mơ hồ.

## 13. LIKE, full-text, trigram và regex

LIKE với wildcard đầu và cuối dễ hiểu nhưng không phải công cụ tìm kiếm văn bản tối ưu cho mọi bài toán.

### 13.1. Full-text search

Khi cần tìm theo từ, stemming, tokenizer, ngôn ngữ và xếp hạng, cân nhắc:

- PostgreSQL: tsvector, tsquery, to_tsvector.
- MySQL: FULLTEXT và MATCH ... AGAINST.
- SQL Server: Full-Text Search.
- Oracle: Oracle Text.
- SQLite: FTS5.

Full-text có semantics khác LIKE; tokenizer và ngôn ngữ ảnh hưởng kết quả. Nó không thay thế tìm chuỗi literal.

### 13.2. Trigram

PostgreSQL pg_trgm hữu ích cho contains và tìm gần đúng. Đây là công cụ tìm kiếm/hiệu năng, không phải cơ chế chống SQL injection. Input vẫn cần bind.

### 13.3. Regex

PostgreSQL, MySQL và Oracle có nhóm hàm/toán tử regex; SQLite tùy extension/hàm ứng dụng; SQL Server lõi không có bộ regex tương đương các hệ trên theo cùng cách.

Regex mạnh hơn LIKE và có thể tốn CPU với pattern phức tạp. Cần giới hạn pattern và thời gian thực thi.

## 14. Kiểm thử LIKE và SQL injection

Một test chỉ gửi chuỗi injection không đủ. Cần tách kiểm thử cấu trúc SQL và semantics pattern.

### 14.1. Ma trận input cho literal contains

| Input | Điều cần tìm | Kỳ vọng |
|---|---|---|
| Phone | Chuỗi con Phone | Tìm tên có Phone |
| Phone_Pro | Dấu gạch dưới thật | Không coi _ là wildcard |
| 100% | Dấu phần trăm thật | Không mở rộng thành mọi hậu tố |
| A!B | Dấu escape thật | Escape chính ký tự escape |
| ' OR 1=1 -- | Chuỗi literal | Không đổi cấu trúc SQL |
| % | Dấu phần trăm thật | Chỉ tìm tên có dấu % |
| Chuỗi rỗng | Không có nội dung | Từ chối hoặc áp chính sách rõ |
| NULL | Không có input | Xử lý theo hợp đồng API |

### 14.2. Kiểm thử parameterization

- Bind input chứa dấu nháy.
- Bind input chứa comment marker.
- Bind input chứa dấu chấm phẩy.
- Bind input chứa phần trăm và gạch dưới.
- Xác nhận SQL text không đổi.
- Xác nhận chỉ dữ liệu phù hợp được trả.

Thực hiện trong database thử nghiệm; không cần chạy payload nguy hiểm trên production.

### 14.3. Kiểm thử hàm escape

```python
cases = {
    "Phone": "%Phone%",
    "Phone_Pro": "%Phone!_Pro%",
    "100%": "%100!%%",
    "A!B": "%A!!B%",
}

for raw, expected in cases.items():
    actual = "%" + escape_like_literal(raw) + "%"
    assert actual == expected
```

Đây là unit test cho pattern builder. Vẫn cần integration test trên DBMS thực tế để xác nhận ESCAPE, collation và Unicode.

### 14.4. Kiểm thử collation

Tạo dữ liệu test với Phone/phone, cafe/café, chữ tiếng Việt hoa/thường có dấu, Unicode kết hợp, khoảng trắng cuối và ký tự ngoài ASCII. Ghi lại kết quả theo collation và phiên bản thực tế. Không suy hành vi SQLite cho MySQL hoặc SQL Server.

## 15. Python với SQLite: tìm chuỗi con literal

```python
import sqlite3

def escape_like_literal(value: str) -> str:
    return (
        value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_")
    )

def search_products(connection, user_text: str):
    pattern = "%" + escape_like_literal(user_text) + "%"

    sql = """
        SELECT product_id, product_name
        FROM products
        WHERE product_name LIKE ? ESCAPE '!'
        ORDER BY product_id
        LIMIT 50
    """

    return connection.execute(sql, (pattern,)).fetchall()
```

SQL text cố định; pattern được bind; wildcard được escape vì input là literal. LIMIT giới hạn số dòng trả về, không thay thế phân quyền.

Nếu tính năng muốn người dùng nhập pattern, bind nguyên pattern và giải thích phần trăm/gạch dưới là wildcard:

```python
def search_by_pattern(connection, user_pattern: str):
    sql = """
        SELECT product_id, product_name
        FROM products
        WHERE product_name LIKE ? ESCAPE '!'
        ORDER BY product_id
        LIMIT 50
    """
    return connection.execute(sql, (user_pattern,)).fetchall()
```

## 16. JDBC: kiểm tra input và bind pattern

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductSearch {
    private ProductSearch() {}

    private static String escapeLikeLiteral(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }

    public static void search(
            Connection connection,
            String userText
    ) throws SQLException {
        if (userText == null) {
            throw new IllegalArgumentException(
                "Search text must not be null");
        }
        if (userText.length() > 100) {
            throw new IllegalArgumentException(
                "Search text is too long");
        }

        String pattern =
            "%" + escapeLikeLiteral(userText) + "%";

        String sql = """
            SELECT product_id, product_name
            FROM products
            WHERE product_name LIKE ? ESCAPE '!'
            ORDER BY product_id
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setString(1, pattern);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getString("product_name"));
                }
            }
        }
    }
}
```

Method nhận Connection từ caller nên không tự đóng connection; transaction và connection do tầng sở hữu quản lý. Statement và ResultSet được đóng bằng try-with-resources.

## 17. Dynamic SQL trong stored procedure

Stored procedure dùng SQL tĩnh với tham số thường dễ kiểm soát:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE p_pattern;
```

Nhưng procedure ghép input vào dynamic SQL vẫn có rủi ro:

```text
sql_text = 'SELECT ... WHERE product_name LIKE '''
           + p_pattern + '''';
EXECUTE sql_text;
```

Khi dùng dynamic SQL, bind variables cho giá trị, allowlist cho identifier và keyword động, escape LIKE riêng nếu cần literal. Stored procedure không tự làm sạch input.

## 18. Bảng quyết định

| Yêu cầu | Pattern/cơ chế | Bảo vệ |
|---|---|---|
| Prefix Phone | Phone% | Bind pattern |
| Suffix Mini | %Mini | Bind; đánh giá hiệu năng |
| Contains literal 100% | %100!%% với ESCAPE ! | Bind + LIKE escape |
| Contains literal A_B | %A!_B% | Bind + LIKE escape |
| Cho phép wildcard | Pattern người dùng nhập | Bind, giới hạn tải, phân quyền |
| Không phân biệt hoa/thường | Collation/ILIKE/hàm DBMS | Bind, kiểm tra index |
| Tìm theo từ/ngôn ngữ | Full-text | Bind query, giới hạn tài nguyên |
| Contains trên dữ liệu lớn | Trigram/search index | Bind và authorization |
| Chọn cột sort | Identifier allowlist | Không bind identifier như value |
| Chọn tenant | ID từ ngữ cảnh xác thực | Authorization/RLS |

## 19. Những ngộ nhận thường gặp

1. **Prepared statement làm phần trăm thành ký tự thường.** Sai: phần trăm vẫn là wildcard.
2. **Người dùng nhập phần trăm là SQL injection.** Sai: khi bind đúng, đó là semantics LIKE.
3. **Escape phần trăm và gạch dưới là đủ chống injection.** Sai: vẫn cần parameterization.
4. **Thay dấu nháy bằng hai dấu nháy là đủ.** Không đáng tin cậy như bind parameter.
5. **LIKE giống regex.** Sai: ngôn ngữ pattern đơn giản và khác nhau.
6. **Mọi DBMS có wildcard giống nhau.** Sai: SQL Server có bracket expressions.
7. **ILIKE có ở mọi DBMS.** Sai: đây là mở rộng PostgreSQL.
8. **LIKE với wildcard đầu luôn dùng B-tree.** Thường không hiệu quả.
9. **Placeholder thay tên bảng/tên cột.** Không; identifier cần allowlist.
10. **Stored procedure không thể bị injection.** Sai nếu dynamic SQL ghép input.
11. **LIMIT giải quyết phân quyền.** Sai; quyền phải được kiểm soát riêng.
12. **NULL LIKE phần trăm là TRUE.** Sai; kết quả UNKNOWN.
13. **LIKE luôn phân biệt hoa/thường.** Phụ thuộc collation và DBMS.
14. **Escape hai lần không sao.** Sai; pattern có thể đổi nghĩa.
15. **Literal search và pattern search là cùng API.** Không; cần hợp đồng rõ.
16. **Có parameterization là không cần giới hạn tải.** Sai; wildcard vẫn có thể tạo query rộng.

## 20. Bài tập có lời giải

### Bài 1. Tìm tên bắt đầu bằng Phone

**Đáp án:** mẫu Phone%.

### Bài 2. Tìm tên kết thúc bằng Mini

**Đáp án:** mẫu %Mini.

### Bài 3. Tìm tên có chứa Phone

**Đáp án:** mẫu %Phone%.

### Bài 4. Phần trăm có khớp chuỗi rỗng không?

**Đáp án:** Có. Nó khớp không hoặc nhiều ký tự.

### Bài 5. Gạch dưới khớp bao nhiêu ký tự?

**Đáp án:** Một ký tự theo quy tắc LIKE của DBMS.

### Bài 6. Tìm literal Phone_Pro

```sql
WHERE product_name LIKE '%Phone!_Pro%' ESCAPE '!'
```

**Đáp án:** dấu gạch dưới được escape nên là literal.

### Bài 7. Tìm literal 100%

```sql
WHERE product_name LIKE '%100!%%' ESCAPE '!'
```

**Đáp án:** phần trăm giữa chuỗi được escape; hai phần trăm ngoài là wildcard.

### Bài 8. Tìm literal A!B

```sql
WHERE product_name LIKE '%A!!B%' ESCAPE '!'
```

**Đáp án:** hai dấu chấm than biểu diễn một dấu chấm than thật.

### Bài 9. Vì sao escape dấu chấm than trước?

**Đáp án:** để ký tự escape mới tạo khi thay phần trăm và gạch dưới không bị escape lần nữa.

### Bài 10. Bind phần trăm có gây injection không?

**Đáp án:** Không nếu bind đúng. Nó vẫn có thể mở rộng kết quả vì là wildcard.

### Bài 11. Input %' OR 1=1 -- ghép vào SQL gây gì?

**Đáp án:** có thể đóng literal, thêm điều kiện logic và comment phần còn lại; đây là SQL injection.

### Bài 12. Cách chính chống SQL injection?

**Đáp án:** prepared statement/bind parameter cho giá trị.

### Bài 13. Có cần tự escape dấu nháy trong tham số đã bind?

**Đáp án:** Không để bảo vệ cấu trúc SQL. Nếu literal LIKE thì escape metacharacter pattern theo hợp đồng riêng.

### Bài 14. SQL Server có wildcard riêng nào?

**Đáp án:** biểu thức ngoặc vuông như [abc], [a-f] và [^...].

### Bài 15. PostgreSQL có ILIKE không?

**Đáp án:** Có; đây là mở rộng PostgreSQL cho so khớp không phân biệt hoa/thường.

### Bài 16. MySQL LIKE phân biệt hoa/thường thế nào?

**Đáp án:** Phụ thuộc collation và character set.

### Bài 17. SQLite LIKE với Unicode tiếng Việt?

**Đáp án:** mặc định không có Unicode case folding đầy đủ ngoài ASCII; cần xem ICU hoặc giải pháp riêng.

### Bài 18. NULL LIKE phần trăm trả gì?

**Đáp án:** UNKNOWN/NULL; WHERE không chọn dòng đó.

### Bài 19. Vì sao contains search có thể chậm?

**Đáp án:** wildcard đầu chuỗi thường làm B-tree prefix index khó dùng. Cân nhắc trigram/full-text/search index.

### Bài 20. Placeholder thay tên cột ORDER BY được không?

**Đáp án:** Không. Dùng allowlist identifier và bind các giá trị.

### Bài 21. Stored procedure ghép dynamic SQL có an toàn không?

**Đáp án:** Không tự động. Dùng bind variables và allowlist.

### Bài 22. Literal mode nhận phần trăm xử lý thế nào?

**Đáp án:** escape thành !%, bind pattern và dùng ESCAPE.

### Bài 23. Pattern mode nhận phần trăm xử lý thế nào?

**Đáp án:** giữ wildcard theo chủ đích, nhưng bind tham số và giới hạn tài nguyên.

### Bài 24. Vì sao LIMIT không thay tenant authorization?

**Đáp án:** LIMIT chỉ giới hạn số dòng; không chứng minh người dùng có quyền đọc các dòng đó.

### Bài 25. Khi nào nên dùng full-text search?

**Đáp án:** khi cần tokenization, stemming, ngôn ngữ hoặc xếp hạng liên quan thay vì so khớp chuỗi literal.

### Bài 26. Tại sao không escape hai lần?

**Đáp án:** lần thứ hai có thể thay đổi escape sequence và làm sai pattern.

### Bài 27. SQL Server tìm literal dấu gạch dưới?

**Đáp án:** có thể dùng bracket pattern [_], ví dụ LIKE N'%Phone[_]Pro%'.

### Bài 28. LIKE prefix luôn dùng index?

**Đáp án:** Không. Còn tùy collation, kiểu dữ liệu, thống kê, operator class và planner.

### Bài 29. Contains pattern cho chuỗi rỗng có nghĩa gì?

**Đáp án:** mẫu hai phần trăm có thể khớp mọi chuỗi không NULL; API cần chính sách rõ.

### Bài 30. Hai lớp bảo vệ cho literal contains?

**Đáp án:** prepared statement để chống injection và LIKE escaping để wildcard trở thành literal.

## 21. Quy trình triển khai an toàn

1. Xác định chức năng là literal contains, prefix, suffix hay pattern search.
2. Chọn DBMS, collation và semantics hoa/thường/Unicode.
3. Giữ SQL text cố định; không nối input không tin cậy.
4. Bind mọi giá trị.
5. Nếu literal, escape ký tự escape trước rồi phần trăm và gạch dưới, thêm ESCAPE.
6. Nếu có identifier động, chọn từ allowlist.
7. Áp tenant/owner/role authorization ở server hoặc database.
8. Giới hạn độ dài pattern, số dòng, timeout và tần suất gọi.
9. Chọn B-tree, trigram hoặc full-text theo loại tìm kiếm.
10. Test injection và wildcard semantics riêng.
11. Kiểm thử trên đúng DBMS/collation/version.
12. Theo dõi query rộng, query chậm và log có dữ liệu nhạy cảm.

## 22. Bảng ghi nhớ nhanh

| Nội dung | Ghi nhớ |
|---|---|
| LIKE | So khớp mẫu chuỗi |
| % | Không hoặc nhiều ký tự |
| _ | Một ký tự |
| ESCAPE | Chỉ định ký tự escape của pattern |
| !_ với ESCAPE ! | Dấu gạch dưới literal |
| !% với ESCAPE ! | Dấu phần trăm literal |
| !! với ESCAPE ! | Dấu chấm than literal |
| SQL injection | Input thay đổi cấu trúc SQL |
| Prepared statement | Bind giá trị tách khỏi SQL text |
| Parameterized LIKE | Chống injection nhưng wildcard vẫn hoạt động |
| Literal LIKE | Bind pattern đã escape và dùng ESCAPE |
| PostgreSQL | Có ILIKE và pg_trgm |
| MySQL | Collation và escape mode quan trọng |
| SQL Server | Có bracket wildcard |
| Oracle | Bind variable |
| SQLite | Phần trăm/gạch dưới; Unicode case behavior có giới hạn |
| B-tree | Hữu ích cho một số prefix pattern |
| Contains | Wildcard đầu thường khó dùng B-tree |
| Full-text | Tìm theo từ/ngôn ngữ, khác LIKE |
| Identifier động | Allowlist, không bind như value |
| Phân quyền | Tenant/owner/RLS độc lập với pattern |
| Wildcard abuse | Có thể mở rộng kết quả/tăng tải nhưng không tự là injection |

## 23. Kết luận

LIKE là công cụ so khớp chuỗi theo mẫu. Phần trăm và gạch dưới làm truy vấn linh hoạt, nhưng ứng dụng phải xác định rõ đầu vào là **văn bản literal** hay **mẫu tìm kiếm có wildcard**.

Hai lớp an toàn không thể thay thế nhau:

- **SQL injection được ngăn chặn chủ yếu bằng parameterized queries**, không nối input vào câu SQL.
- **LIKE wildcard được kiểm soát bằng escaping và ESCAPE** khi người dùng cần tìm ký tự literal.

Một prepared statement có thể an toàn khỏi SQL injection nhưng vẫn trả quá nhiều dòng vì pattern chứa phần trăm. Ngược lại, một chuỗi đã escape phần trăm và gạch dưới vẫn có thể bị injection nếu ứng dụng ghép nó vào SQL text không an toàn.

Hãy kết hợp **bind parameters, LIKE escaping theo hợp đồng, allowlist cho cú pháp động, phân quyền dữ liệu và giới hạn tài nguyên**. Khi chuyển giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite, kiểm tra thêm wildcard riêng, collation, Unicode và khả năng sử dụng index.

## Tài liệu tham khảo

- [PostgreSQL — Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html): LIKE, ILIKE, SIMILAR TO, regex và ESCAPE.
- [PostgreSQL — PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): prepared statement và tham số.
- [PostgreSQL — pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): trigram index và pattern search.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries, allowlist và dynamic SQL.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): kiểm tra input theo ngữ nghĩa ứng dụng.
- [MySQL — String Comparison Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/string-comparison-functions.html): LIKE, wildcard và collation.
- [Microsoft Learn — LIKE (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/like-transact-sql): wildcard, bracket expressions và ESCAPE trong SQL Server.
- [Oracle Database — Pattern-matching Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Pattern-matching-Conditions.html): LIKE, ESCAPE và các điều kiện so khớp.
- [SQLite — LIKE Operator](https://www.sqlite.org/lang_expr.html#like): semantics LIKE và ESCAPE.
- [SQLite — PRAGMA Statements](https://www.sqlite.org/pragma.html): trạng thái và lưu ý về case_sensitive_like.

