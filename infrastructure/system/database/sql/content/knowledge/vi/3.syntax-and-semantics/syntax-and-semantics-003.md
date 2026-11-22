# Chuỗi ký tự, dấu nháy đơn và ký tự thoát

Trong **Database SQL**, chuỗi ký tự xuất hiện ở câu lệnh đọc dữ liệu, điều kiện lọc, lệnh thêm/sửa bản ghi, truy vấn mẫu và biểu thức xử lý văn bản. Phần dễ nhầm nhất là: dấu nháy nào xác định *giá trị chuỗi*, cách biểu diễn một dấu nháy đơn ngay bên trong chuỗi, khi nào dấu gạch chéo ngược có ý nghĩa đặc biệt, và vì sao việc “thoát ký tự” trong câu lệnh SQL khác với xử lý tham số đầu vào của ứng dụng.

Bài này trình bày quy tắc SQL phổ biến trước, sau đó chỉ rõ những trường hợp phụ thuộc **hệ quản trị cơ sở dữ liệu (DBMS)**. Các ví dụ được ghi nhãn PostgreSQL, MySQL, SQL Server, SQLite hoặc Oracle khi có cú pháp riêng.

## 1. Chuỗi ký tự là gì?

Một **string literal** (hằng chuỗi) là giá trị văn bản viết trực tiếp trong câu SQL. Theo cú pháp SQL tiêu chuẩn, chuỗi được bao bằng **hai dấu nháy đơn ASCII** (`'`): một dấu mở và một dấu đóng.

```sql
SELECT 'Hello SQL' AS message;
SELECT 'Nguyễn Văn A' AS full_name;
SELECT '123' AS text_value;
SELECT 123 AS numeric_value;
```

Với đa số DBMS, `'123'` là **giá trị chuỗi**, còn `123` là **giá trị số**. DBMS có thể thực hiện chuyển kiểu ngầm trong một số phép so sánh, nhưng không nên dựa vào điều đó vì cách chuyển kiểu, lỗi và hiệu năng có thể khác giữa các hệ.

Các trường hợp cần phân biệt:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `'SQL'` | Chuỗi có ba ký tự S, Q, L |
| `''` | Chuỗi rỗng theo phần lớn DBMS; **Oracle Database xử lý chuỗi rỗng dạng chuỗi ký tự như `NULL`** |
| `' '` | Chuỗi chứa một dấu cách, không phải chuỗi rỗng |
| `'NULL'` | Bốn ký tự N, U, L, L; không phải giá trị rỗng SQL |
| `NULL` | Dấu chỉ không có giá trị SQL; không phải một chuỗi văn bản |
| `'2026-11-14'` | Văn bản có hình thức ngày tháng; muốn xử lý như DATE/TIMESTAMP phải chuyển/ép sang kiểu phù hợp |

Dấu nháy cong trong văn bản soạn thảo, chẳng hạn `‘SQL’` hoặc `“SQL”`, **không phải** cặp dấu nháy đơn ASCII hợp lệ để phân định chuỗi SQL. Hãy gõ ký tự `'` thẳng từ bàn phím hoặc trình soạn mã.

> **Ghi chú môi trường:** Trong Oracle Database, nhiều phiên bản yêu cầu `FROM DUAL` cho câu `SELECT` chỉ lấy giá trị biểu thức (ví dụ `SELECT 'Hello' FROM DUAL;`). Các ví dụ `SELECT '...' AS ...;` không có `FROM` ở đây phù hợp trực tiếp với PostgreSQL, MySQL, SQLite và SQL Server; hãy điều chỉnh phần `FROM` khi dùng Oracle phiên bản cần `DUAL`.

## 2. Dấu nháy đơn khác với dấu nháy kép và dấu tên định danh

Trong SQL tiêu chuẩn:

- `'student'` biểu diễn **giá trị chuỗi**.
- `"student"` biểu diễn **tên định danh được đặt trong dấu nháy** (ví dụ tên cột hoặc tên bảng).
- `student` không có nháy là **tên định danh không đặt trong dấu nháy**, nếu xuất hiện ở vị trí yêu cầu tên cột/bảng.

Ví dụ PostgreSQL:

```sql
-- Chuỗi văn bản:
SELECT 'display_name' AS example_text;

-- Giá trị trong một cột có tên display_name:
SELECT display_name FROM students;

-- Tên cột được bao bởi dấu nháy kép:
SELECT "display_name" FROM students;
```

Đừng dùng dấu nháy kép thay dấu nháy đơn chỉ vì câu lệnh “vẫn chạy” trên một DBMS nào đó. MySQL có chế độ `ANSI_QUOTES` làm thay đổi ý nghĩa dấu nháy kép; SQL Server chịu ảnh hưởng thiết lập `QUOTED_IDENTIFIER`; MySQL thường dùng dấu backtick `...` cho định danh, SQL Server còn có `[Tên cột]`. Muốn viết literal chuỗi dễ chuyển giữa các hệ, **dùng nháy đơn**.

Dấu chấm phẩy, dấu cách hay từ khóa SQL **nằm bên trong** một chuỗi vẫn là dữ liệu:

```sql
SELECT 'SELECT * FROM students;' AS just_text;
SELECT 'a,b;c -- vẫn là văn bản' AS sample;
```

Trong các literal đó, `SELECT`, `;` và `--` không tạo câu lệnh hay chú thích mới.

## 3. Viết dấu nháy đơn bên trong chuỗi: nhân đôi dấu nháy

Muốn đưa dấu `'` vào nội dung của một literal, cách phổ biến và tương thích theo SQL tiêu chuẩn là **viết hai dấu nháy đơn liên tiếp**: `''`.

```sql
SELECT 'O''Brien' AS customer_name;
SELECT 'I''m learning SQL' AS sentence;
SELECT 'She said: ''Hello!''' AS quotation;
```

Giải thích ví dụ thứ nhất:

```text
SQL literal: 'O''Brien'
             ^ ^^     ^
             | ||     |--- dấu kết thúc chuỗi
             | ||--------- hai dấu trong chuỗi biểu diễn một dấu ' ở dữ liệu
             |------------ dấu bắt đầu chuỗi

Giá trị nhận được: O'Brien
```

Hai dấu nháy đơn nằm *liền nhau* ở giữa chuỗi tạo ra một dấu nháy đơn trong dữ liệu. Không có nghĩa là tạo hai chuỗi hay thêm dấu nháy vào kết quả.

Một vài trường hợp đặc biệt:

| Muốn lưu/hiển thị | Viết literal SQL |
| --- | --- |
| `It's ready` | `'It''s ready'` |
| `'SQL'` (có nháy ở hai đầu dữ liệu) | `'''SQL'''` |
| Chỉ một ký tự `'` | `''''` (bốn dấu nháy đơn liên tiếp) |
| Chuỗi rỗng trong PostgreSQL/MySQL/SQL Server/SQLite | `''` |

Hãy **đếm dấu nháy theo cặp**: dấu ngoài cùng mở/đóng literal, mỗi dấu `'` thuộc nội dung được viết thành một cặp `''`. Một lỗi thường gặp là:

```sql
-- SAI: chuỗi bị kết thúc giữa chừng
SELECT 'O'Brien' AS customer_name;

-- ĐÚNG: dấu nháy trong tên được nhân đôi
SELECT 'O''Brien' AS customer_name;
```

Cách nhân đôi dấu nháy giải quyết vấn đề **viết literal trực tiếp trong câu SQL**, nhưng khi giá trị đến từ người dùng/ứng dụng, còn cần **truy vấn tham số hóa** (mục 7).

## 4. Dấu gạch chéo ngược không có cùng ý nghĩa trong mọi DBMS

Trong nhiều ngôn ngữ lập trình, `\n` nghĩa là xuống dòng, `\t` là tab và `\'` dùng để biểu diễn dấu nháy. **SQL không thống nhất toàn bộ cách dùng dấu `\` như các ngôn ngữ đó.**

Theo cách viết string literal thông thường của SQL tiêu chuẩn, dấu nháy đơn bên trong chuỗi được nhân đôi. Một số DBMS hỗ trợ thêm cú pháp backslash escape, có DBMS chỉ hỗ trợ khi dùng literal đặc biệt hoặc bật/tắt chế độ cụ thể.

| DBMS | Quy tắc thực hành nên nhớ |
| --- | --- |
| **PostgreSQL** | Literal `'...'` với `standard_conforming_strings = on` coi backslash là ký tự bình thường; dạng `E'...'` hỗ trợ chuỗi thoát kiểu `\n`, `\t`, `\\` và `\'`. |
| **MySQL / MariaDB** | Literal `'...'` thường xử lý một số backslash escape như `\n`, `\t`, `\\`, `\'`; `NO_BACKSLASH_ESCAPES` thay đổi cách này. Luôn kiểm tra `sql_mode` khi bài phụ thuộc backslash. |
| **SQL Server** | Không dùng `\` làm dấu escape phổ thông trong T-SQL string literal; viết `''` cho nháy đơn. Có thể dùng `CHAR(10)`/`NCHAR(10)` và phép nối chuỗi cho ký tự điều khiển. |
| **SQLite** | Trong literal SQL, backslash là ký tự thông thường; viết `''` cho nháy đơn. Hàm `char(...)` có thể tạo ký tự từ mã số. |
| **Oracle Database** | Dùng `''` hoặc cú pháp trích dẫn thay thế `q'[...]'`; backslash nhìn chung không phải dấu escape trong literal thường. |

### PostgreSQL: phân biệt literal chuẩn và `E'...'`

Ví dụ dưới đây **dành cho PostgreSQL khi `standard_conforming_strings = on`**:

```sql
SHOW standard_conforming_strings;

-- Ký tự \ và n được giữ nguyên:
SELECT 'Dòng 1\nDòng 2' AS text_with_backslash;

-- \n được diễn giải thành ký tự xuống dòng thật:
SELECT E'Dòng 1\nDòng 2' AS text_with_newline;

-- Cách khác để có nháy đơn trong E-string:
SELECT E'It\'s ready' AS sentence;

-- Viết bằng SQL chuẩn, không cần E-prefix:
SELECT 'It''s ready' AS portable_sentence;
```

Hai biểu thức chứa `\n` trông giống nhau, nhưng **kết quả khác nhau** vì cách đọc dấu backslash khác nhau. Không suy đoán kết quả từ ký tự hiển thị: ghi rõ DBMS và chế độ thực thi.

PostgreSQL còn có **dollar-quoted strings**, hữu ích khi nội dung chứa rất nhiều nháy đơn (thường gặp khi viết hàm/thủ tục):

```sql
-- Cú pháp riêng của PostgreSQL:
SELECT $$O'Brien said: 'Hello!'$$ AS statement;
SELECT $note$Line 1
Line 2 with 'quotes'$note$ AS multiline_text;
```

Phần được bao giữa hai delimiter `$$` hoặc `$note$` được giữ làm nội dung chuỗi. Nếu nội dung tự chứa chính delimiter đang dùng, hãy đổi tag delimiter. Đây **không phải cú pháp SQL dùng chung mọi DBMS**.

### MySQL: kiểm tra chế độ SQL

```sql
-- MySQL:
SELECT VERSION() AS engine_version, @@SESSION.sql_mode AS sql_mode;

-- Nếu KHÔNG bật NO_BACKSLASH_ESCAPES, \n có thể tạo ký tự xuống dòng:
SELECT 'Dòng 1\nDòng 2' AS example_value;

-- Luôn dùng cú pháp chuẩn khi biểu diễn nháy đơn:
SELECT 'O''Brien' AS customer_name;
```

Với dữ liệu thực tế như đường dẫn `C:\new\logs`, việc đặt nguyên văn đường dẫn trong literal có backslash escape có thể cho ra kết quả bất ngờ (`\n` bị hiểu thành xuống dòng). Cách bền vững là **truyền giá trị qua tham số**; nếu buộc viết literal trực tiếp, phải dùng đúng quy tắc escape theo DBMS và `sql_mode` tại thời điểm chạy.

### SQL Server, Oracle và Unicode

SQL Server dùng prefix `N` để tạo **Unicode string literal (NVARCHAR)**:

```sql
-- SQL Server:
SELECT N'Tiếng Việt có dấu' AS unicode_text;
SELECT N'O''Brien' AS customer_name;
```

Đối với dữ liệu Unicode trong T-SQL, `N'...'` là lựa chọn thông dụng, đặc biệt khi so sánh hoặc ghi dữ liệu kiểu `NVARCHAR`. Quy tắc nháy đơn bên trong vẫn là `''`.

Oracle Database cung cấp cách trích dẫn thay thế, giảm số nháy đơn phải nhân đôi trong chuỗi nhiều dấu nháy:

```sql
-- Oracle (q-quoting); DUAL dùng cho các phiên bản Oracle cần FROM:
SELECT q'[It's called 'SQL']' AS message FROM DUAL;

-- Cách viết tiêu chuẩn vẫn dùng được:
SELECT 'It''s called ''SQL''' AS message FROM DUAL;
```

Trong `q'[ ... ]'`, `[` và `]` là cặp delimiter cho nội dung chuỗi. Đừng áp dụng cú pháp này cho PostgreSQL/MySQL/SQL Server nếu bài học không chỉ rõ hệ hỗ trợ.

## 5. Ký tự thoát bên trong `LIKE` là một khái niệm khác

Trong điều kiện `LIKE`, hai ký tự có nghĩa đặc biệt trong **mẫu tìm kiếm**:

- `%` khớp với chuỗi bất kỳ dài từ 0 ký tự trở lên.
- `_` khớp với đúng **một** ký tự theo cách khớp của DBMS/collation.

Ví dụ PostgreSQL (giả sử có cột `product_code`):

```sql
-- Các mã bắt đầu bằng A:
SELECT product_code FROM products WHERE product_code LIKE 'A%';

-- Các mã có đúng một ký tự sau A:
SELECT product_code FROM products WHERE product_code LIKE 'A_';
```

Nếu cần tìm **dấu phần trăm hoặc gạch dưới theo nghĩa ký tự thông thường**, có thể chọn một dấu escape riêng bằng mệnh đề `ESCAPE`:

```sql
-- Khớp chính xác chuỗi A_1, không coi _ là wildcard:
SELECT product_code
FROM products
WHERE product_code LIKE 'A!_1' ESCAPE '!';

-- Khớp chính xác chuỗi 100%, không coi % cuối là wildcard:
SELECT product_code
FROM products
WHERE product_code LIKE '100!%' ESCAPE '!';

-- Tìm chuỗi chứa ký tự % ở vị trí bất kỳ:
SELECT product_code
FROM products
WHERE product_code LIKE '%!%%' ESCAPE '!';
```

Trong `LIKE 'A!_1' ESCAPE '!'`:

1. Dấu `'...'` vẫn chỉ **literal SQL**.
2. Ký tự `!` đứng trước `_` khiến `_` được hiểu là ký tự gạch dưới khi **khớp mẫu**.
3. Bản thân dấu `!` không có ý nghĩa escape trong một literal SQL thông thường nếu không đặt `ESCAPE '!'` trong biểu thức `LIKE`.

Tách bạch hai lớp xử lý:

| Vấn đề | Cơ chế |
| --- | --- |
| Viết literal chứa dấu nháy đơn `'` | Nhân đôi `''` trong SQL literal (hoặc dùng tham số) |
| Viết ký tự xuống dòng/tab trong literal | Cú pháp/biểu thức theo DBMS, ví dụ PostgreSQL `E'...\n...'` |
| Tìm ký tự `%` hay `_` thật trong `LIKE` | Dùng `LIKE ... ESCAPE '!'` và `!%` / `!_` |
| Truyền dữ liệu từ ứng dụng vào `WHERE` hoặc `INSERT` | Dùng bind parameter/prepared statement |

Mệnh đề `ESCAPE` được nhiều DBMS hỗ trợ, nhưng có khác biệt về quy tắc mặc định và cú pháp đặc thù (ví dụ SQL Server hỗ trợ mẫu dùng dấu ngoặc vuông). Chọn một ký tự escape rõ ràng, ghi chú hệ đang chạy và **không dựa vào giả định backslash luôn là ký tự escape của `LIKE`**.

## 6. Chuỗi, ký tự đặc biệt và giá trị `NULL`

### Khoảng trắng và phân biệt chữ hoa/chữ thường

Hai literal `'SQL'` và `' SQL '` không chứa cùng chuỗi ký tự. Tuy nhiên, so sánh chuỗi có thể chịu ảnh hưởng bởi **collation**, kiểu cột (ví dụ `CHAR` có độ dài cố định), và quy tắc xử lý dấu cách cuối. Do đó, điều kiện `=` hoặc `LIKE` không nhất thiết cho cùng kết quả trên mọi DBMS/collation.

```sql
-- PostgreSQL: quan sát độ dài và khoảng trắng của giá trị literal.
SELECT length(' SQL ') AS length_with_spaces,
       length('SQL') AS length_without_spaces;
```

Unicode cũng là nội dung chuỗi: ký tự có dấu, emoji hoặc tổ hợp ký tự có thể được mã hóa và đếm khác nhau tùy encoding/collation/hàm. Hãy kiểm tra database/client encoding và kiểu cột, đặc biệt khi truyền văn bản tiếng Việt.

### `NULL` không giống `'NULL'` hay chuỗi rỗng

```sql
-- PostgreSQL / MySQL / SQLite / SQL Server:
SELECT 'NULL' AS visible_text,
       NULL AS missing_value,
       '' AS empty_text;
```

Trong SQL, kiểm tra `NULL` bằng `IS NULL`, không viết `= NULL`:

```sql
-- ĐÚNG: tìm các dòng có ghi chú là NULL
SELECT id FROM notes WHERE note_text IS NULL;

-- KHÔNG ĐÚNG để tìm giá trị NULL:
SELECT id FROM notes WHERE note_text = NULL;
```

Điểm riêng cần nhớ: **Oracle Database xử lý chuỗi rỗng `''` như `NULL` trong nhiều ngữ cảnh kiểu ký tự**. Vì vậy ví dụ hoặc điều kiện phân biệt `''` và `NULL` ở PostgreSQL/SQLite không thể chuyển nguyên xi sang Oracle.

### Tạo ký tự điều khiển trong chuỗi

Không có một cách viết `\n` dùng chung tất cả hệ. Nếu thật sự cần xuống dòng trong kết quả, hãy dùng cú pháp của DBMS:

| DBMS | Ví dụ nối hai chuỗi với ký tự xuống dòng |
| --- | --- |
| PostgreSQL | `'Dòng 1' || CHR(10) || 'Dòng 2'` hoặc `E'Dòng 1\nDòng 2'` |
| MySQL | `CONCAT('Dòng 1', CHAR(10), 'Dòng 2')` |
| SQL Server | `N'Dòng 1' + NCHAR(10) + N'Dòng 2'` |
| SQLite | `'Dòng 1' || char(10) || 'Dòng 2'` |
| Oracle | `'Dòng 1' || CHR(10) || 'Dòng 2'` |

Hiển thị xuống dòng còn phụ thuộc client: một số công cụ bảng kết quả giữ newline trong ô, một số chuyển thành ký hiệu hoặc xuống dòng trực quan.

## 7. Dữ liệu do người dùng nhập: dùng tham số, không tự nối SQL

Giả sử người dùng nhập tên `O'Brien`. Nếu ứng dụng nối chuỗi SQL theo kiểu:

```java
// Ví dụ CẦN TRÁNH: nối trực tiếp nội dung người dùng vào câu SQL.
String sql = "SELECT id, display_name FROM customers WHERE display_name = '"
        + inputName + "'";
```

thì dấu nháy đơn trong `inputName` có thể làm hỏng cú pháp. Nghiêm trọng hơn, khi kẻ tấn công chèn đoạn SQL có chủ ý, cách nối này có nguy cơ gây **SQL injection**. Việc tự gọi `replace("'", "''")` không phải chiến lược phòng vệ tổng quát, vì còn phải tính đến DBMS, encoding, chế độ escape, kiểu dữ liệu và mọi vị trí đưa đầu vào vào câu SQL.

**Giải pháp chuẩn trong ứng dụng là prepared statement/bind parameter:** câu lệnh SQL được định nghĩa tách biệt với giá trị. Ví dụ JDBC (giả sử `connection` là một `java.sql.Connection` đã kết nối):

```java
String sql = "SELECT id, display_name FROM customers WHERE display_name = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, inputName); // inputName có thể là "O'Brien"

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("display_name"));
        }
    }
}
```

Trong ví dụ này, `?` là placeholder giá trị; `setString(1, inputName)` bind chuỗi vào tham số thứ nhất. JDBC driver/DBMS xử lý giá trị phù hợp với giao thức thay vì khiến ứng dụng tự ghép dấu nháy. Có thể áp dụng tương tự cho câu `INSERT`/`UPDATE` và các toán hạng của `WHERE`.

**Giới hạn:** placeholder cho **giá trị dữ liệu**, không tự thay thế tên bảng, tên cột, từ khóa `ORDER BY` hay cả biểu thức SQL. Nếu ứng dụng cho chọn tên cột để sắp xếp, hãy ánh xạ lựa chọn vào **danh sách tên cột hợp lệ đã định sẵn** rồi mới dựng SQL; vẫn bind mọi giá trị lọc.

Mẫu `LIKE` có tham số cần lưu ý thêm: nếu đầu vào người dùng phải được tìm theo nghĩa **văn bản nguyên văn**, ứng dụng phải xử lý riêng `%`, `_` và ký tự escape trong *giá trị pattern*. Bind parameter chống SQL injection nhưng **không tự làm mất ý nghĩa wildcard của `LIKE`**.

## 8. Ví dụ thực hành trên PostgreSQL

Để minh họa trọn vẹn, ví dụ này dành cho **PostgreSQL**, chạy trong một database thực hành và tạo bảng nhỏ riêng. Nếu bảng `sql_string_lab` đã tồn tại, hãy chọn schema/tên khác hoặc kiểm tra trước khi tạo, tránh ghi đè dữ liệu có sẵn.

```sql
CREATE TABLE sql_string_lab (
    id         INTEGER PRIMARY KEY,
    full_name  VARCHAR(100) NOT NULL,
    note_text  VARCHAR(200)
);

INSERT INTO sql_string_lab (id, full_name, note_text)
VALUES
    (1, 'O''Brien', 'Ưu đãi 20%'),
    (2, 'Minh Anh', 'Mã A_1'),
    (3, 'Linh', 'Đường dẫn C:\docs\sql'),
    (4, 'Hà', NULL),
    (5, 'Quang', '');

-- Kiểm tra giá trị có nháy đơn:
SELECT id, full_name
FROM sql_string_lab
WHERE full_name = 'O''Brien';

-- Tìm giá trị chứa ký tự phần trăm thật:
SELECT id, note_text
FROM sql_string_lab
WHERE note_text LIKE '%!%%' ESCAPE '!';

-- Tìm giá trị chứa ký tự gạch dưới thật:
SELECT id, note_text
FROM sql_string_lab
WHERE note_text LIKE '%!_%' ESCAPE '!';

-- Phân biệt NULL và chuỗi rỗng trên PostgreSQL:
SELECT id, note_text
FROM sql_string_lab
WHERE note_text IS NULL;

SELECT id, note_text
FROM sql_string_lab
WHERE note_text = '';

-- Quan sát dấu backslash trong môi trường PostgreSQL chuẩn:
SHOW standard_conforming_strings;
SELECT id, note_text
FROM sql_string_lab
WHERE id = 3;
```

Ở PostgreSQL thông thường, `standard_conforming_strings` được bật, nên chuỗi đường dẫn trong câu `INSERT` được lưu với các dấu `\` đúng như nội dung. Nếu môi trường đã thay đổi thiết lập này, kết quả có thể khác; câu `SHOW` giúp phát hiện điều đó.

Nếu muốn hoàn nguyên dữ liệu thử, chỉ xóa **bảng bạn vừa tự tạo**:

```sql
DROP TABLE sql_string_lab;
```

Đừng chạy lệnh xóa bảng trên database chứa dữ liệu cần giữ.

## 9. Lỗi thường gặp và cách đọc nguyên nhân

| Hiện tượng | Nguyên nhân có khả năng | Cách sửa |
| --- | --- | --- |
| Lỗi cú pháp gần `Brien` trong `'O'Brien'` | Literal đóng ngay tại dấu nháy giữa tên | Viết `'O''Brien'`; ứng dụng phải bind tham số |
| `"hello"` bị coi là tên cột hoặc gây lỗi | Dấu nháy kép biểu diễn identifier hoặc chịu ảnh hưởng DBMS mode | Dùng `'hello'` cho chuỗi |
| `C:\new\logs` biến thành văn bản xuống dòng lạ | DBMS/mode đang hiểu `\n` là escape | Dùng bind parameter hoặc cú pháp phù hợp engine/mode |
| `LIKE 'A_1'` khớp cả `AB1` | `_` có nghĩa wildcard | Viết `LIKE 'A!_1' ESCAPE '!'` |
| `LIKE '100%'` khớp `1000` | `%` có nghĩa wildcard | Viết `LIKE '100!%' ESCAPE '!'` |
| `WHERE col = NULL` không tìm thấy NULL | So sánh với NULL không trả TRUE | Dùng `IS NULL` |
| Điều kiện `col = ''` chạy khác trên Oracle | Oracle xử lý chuỗi rỗng như NULL | Xử lý theo quy tắc Oracle, cân nhắc `IS NULL` và mô hình dữ liệu |
| Tên tiếng Việt bị sai ký tự | Encoding, loại cột, client hoặc cơ chế literal không khớp | Kiểm tra UTF-8/Unicode, kiểu dữ liệu và Unicode literal (ví dụ `N'...'` của T-SQL) |
| SQL viết trong Java có nhiều dấu `\` | Java string literal có lớp escape riêng trước khi SQL được gửi đi | Phân biệt **Java source string → SQL text → SQL literal**; ưu tiên tham số |

**Ba lớp cần theo dõi khi viết SQL từ chương trình:** mã nguồn của ngôn ngữ lập trình có quy tắc string literal riêng; SQL text gửi tới DBMS có quy tắc parser riêng; giá trị chuỗi mà DBMS nhận được là lớp kết quả cuối. Ví dụ `"\n"` trong Java tạo newline trong giá trị Java, còn văn bản hai ký tự `\` và `n` trong Java phải được viết là `"\\n"`. Tương tự, các ví dụ SQL trong tập tin `.sql` không chịu một lớp escape của Java.

## 10. Bài tập áp dụng

**Bài 1 — Xác định giá trị.** Cho các literal `'SQL'`, `'SQL '`, `''`, `'NULL'`, `NULL`. Hãy mô tả giá trị và cho biết trường hợp nào không phải chuỗi.

**Bài 2 — Viết literal hợp lệ.** Chuyển các văn bản sau thành literal SQL dùng nháy đơn: `I'm ready`; `'Database'` (bao gồm cả dấu nháy trong dữ liệu); `O'Brien's book`.

**Bài 3 — LIKE nguyên văn.** Viết biểu thức `LIKE` để lọc chính xác mã `A_1` và để tìm mọi ghi chú chứa dấu phần trăm `%`, chọn `!` làm ký tự escape.

**Bài 4 — Giải thích khác biệt DBMS.** Vì sao `SELECT 'A\nB';` có thể cho kết quả khác giữa PostgreSQL mặc định và MySQL không bật `NO_BACKSLASH_ESCAPES`? Có nên dùng `\'` để thoát dấu nháy đơn trong SQL đa hệ không?

**Bài 5 — Truy vấn an toàn.** Một ứng dụng nhận tên người dùng từ form để truy vấn bảng `customers`. Viết câu SQL có placeholder phù hợp JDBC, rồi nêu bước gán giá trị chuỗi.

### Gợi ý đáp án

1. `'SQL'` là ba ký tự; `'SQL '` có thêm dấu cách cuối; `''` là chuỗi rỗng trong nhiều DBMS nhưng Oracle thường coi là `NULL`; `'NULL'` là chuỗi bốn ký tự; `NULL` không phải chuỗi.
2. `'I''m ready'`, `'''Database'''`, `'O''Brien''s book'`.
3. `LIKE 'A!_1' ESCAPE '!'` và `LIKE '%!%%' ESCAPE '!'`.
4. PostgreSQL với `standard_conforming_strings = on` giữ backslash nguyên văn trong literal thường; MySQL mặc định có thể coi `\n` là xuống dòng. Không nên dùng `\'` làm quy tắc SQL đa hệ; dùng `''` hoặc bind parameter.
5. `SELECT id, display_name FROM customers WHERE display_name = ?`; gọi `PreparedStatement#setString(1, inputName)` để truyền dữ liệu.

Kết quả quan trọng của bài thực hành là biết **phân biệt cú pháp literal chuỗi, quy tắc escape trong mẫu `LIKE` và tham số truy vấn**. Khi cú pháp có yếu tố đặc thù, hãy ghi rõ DBMS cùng phiên bản/chế độ tương thích để người khác lặp lại được ví dụ.
