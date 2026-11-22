# LIKE với ký tự đại diện và ESCAPE

Trong **Database SQL**, điều kiện `LIKE` được dùng khi cần lọc văn bản theo **mẫu (pattern)**, chẳng hạn mã hàng bắt đầu bằng `AB`, tên chứa từ `SQL` hoặc mã có đúng ba ký tự. Khác với phép so sánh `=`, `LIKE` hiểu một số ký tự trong mẫu là **ký tự đại diện (wildcard)**. Vì vậy, một dấu phần trăm `%` hoặc gạch dưới `_` xuất hiện trong dữ liệu có thể làm truy vấn khớp nhiều giá trị hơn dự kiến nếu không được xử lý đúng.

Mệnh đề `ESCAPE` giúp xác định một ký tự dùng để biến `%` và `_` từ **ký tự đại diện** thành **ký tự cần tìm nguyên văn**. Bài học này tập trung vào cú pháp, cách diễn giải mẫu, kết hợp `ESCAPE`, ảnh hưởng của `NULL` và collation, cách truyền mẫu an toàn từ ứng dụng và những khác biệt giữa các hệ quản trị cơ sở dữ liệu (DBMS).

## 1. LIKE hoạt động trên một mẫu như thế nào?

Dạng thường gặp trong câu `SELECT` là:

```sql
SELECT column_name
FROM table_name
WHERE column_name LIKE 'pattern';
```

Biểu thức bên trái là giá trị cần kiểm tra; bên phải là **mẫu chuỗi**. DBMS xác định giá trị có khớp **toàn bộ mẫu** hay không. Để mô tả một phần văn bản xuất hiện ở bất kỳ vị trí nào, ta chủ động đặt các wildcard xung quanh phần cần tìm.

| Mẫu | Ý nghĩa | Ví dụ giá trị khớp |
| --- | --- | --- |
| `'AB'` | Chính xác mẫu `AB`, theo quy tắc so sánh của DBMS/collation | `AB` |
| `'AB%'` | Bắt đầu bằng `AB`, sau đó có thể có 0 hoặc nhiều ký tự | `AB`, `AB1`, `ABCD` |
| `'%AB'` | Kết thúc bằng `AB` | `AB`, `XAB` |
| `'%AB%'` | Chứa `AB` ở vị trí bất kỳ | `AB`, `XABY` |
| `'A_B'` | `A`, tiếp theo đúng một ký tự, sau đó `B` | `A1B`, `A_B` |
| `'A__B'` | `A`, tiếp theo đúng hai ký tự, sau đó `B` | `A12B` |
| `'___'` | Đúng ba ký tự theo quy tắc đếm ký tự của DBMS | `ABC`, `123` |
| `'%'` | Chuỗi bất kỳ, kể cả chuỗi rỗng; không khớp `NULL` | `''`, `ABC` |

Ví dụ dưới đây chạy trực tiếp trên **PostgreSQL**, không cần tạo bảng:

```sql
SELECT
    'AB' LIKE 'AB%'     AS prefix_exact,
    'AB123' LIKE 'AB%'  AS prefix_longer,
    'ZABZ' LIKE '%AB%'  AS contains_ab,
    'A7B' LIKE 'A_B'    AS one_character_between,
    'A77B' LIKE 'A_B'   AS two_characters_not_one;
```

Bốn biểu thức đầu trả `TRUE`, biểu thức cuối trả `FALSE`. Khi mẫu có wildcard, phần không khớp có thể dài tùy ý với `%`, nhưng **mỗi `_` chỉ thay đúng một ký tự theo ngữ nghĩa của DBMS**.

> Tên cột và bảng ở một số ví dụ sau chỉ là tên minh họa. Phần thực hành ở mục 11 sẽ tạo dữ liệu đầy đủ để chạy liên tiếp trên PostgreSQL.

## 2. Hai ký tự đại diện cơ bản: % và _

### Dấu phần trăm %: không hoặc nhiều ký tự

`%` khớp một chuỗi có **độ dài từ 0 ký tự trở lên**, vì vậy `'AB%'` khớp luôn `'AB'`.

```sql
-- Tìm mã sản phẩm bắt đầu bằng AB:
SELECT product_code
FROM products
WHERE product_code LIKE 'AB%';

-- Tìm mã kết thúc bằng 01:
SELECT product_code
FROM products
WHERE product_code LIKE '%01';

-- Tìm mọi tên có đoạn văn bản SQL:
SELECT product_name
FROM products
WHERE product_name LIKE '%SQL%';
```

Trong ví dụ cuối, `'%SQL%'` chỉ kiểm tra một dãy ký tự liền nhau `SQL`. Nó không phải phép tìm kiếm theo từ có phân tích ngôn ngữ tự nhiên, không tự bỏ dấu tiếng Việt, không tìm từ đồng nghĩa và không xếp hạng theo mức liên quan.

### Dấu gạch dưới _: đúng một ký tự

`_` khớp đúng **một ký tự**, không thể khớp chuỗi rỗng.

```sql
SELECT
    'A1' LIKE 'A_'    AS one_character,
    'A12' LIKE 'A_'   AS too_many,
    'A' LIKE 'A_'     AS missing_character,
    'A12' LIKE 'A__'  AS two_characters;
```

Với PostgreSQL, kết quả lần lượt là `TRUE`, `FALSE`, `FALSE`, `TRUE`.

Một vài mẫu kết hợp:

| Mẫu | Ý nghĩa |
| --- | --- |
| `'A_%'` | Bắt đầu `A`, có **ít nhất một** ký tự theo sau |
| `'_AB%'` | Có ít nhất một ký tự trước đoạn `AB`, sau đó tùy ý |
| `'AB__'` | Chính xác bốn ký tự, hai ký tự đầu là `AB` |
| `'%_X'` | Kết thúc bằng `X` và có ít nhất một ký tự trước `X` |
| `'%__%'` | Có ít nhất hai ký tự |
| `'A_%Z'` | Bắt đầu `A`, kết thúc `Z` và có ít nhất một ký tự ở giữa |

Không nhầm `_` với **dấu gạch dưới trong tên cột**, ví dụ `product_code`. Ký tự `_` trong một **identifier** không phải wildcard; nó chỉ mang nghĩa đặc biệt **khi nằm trong mẫu của `LIKE`**.

### “Một ký tự” và Unicode

Trong dữ liệu Unicode, “một ký tự” ở SQL không nhất thiết bằng “một biểu tượng mà người dùng nhìn thấy”. Một chữ có dấu có thể được lưu thành một mã điểm ghép sẵn hoặc gồm ký tự cơ sở và dấu kết hợp; emoji ghép có thể có nhiều mã điểm. Cách `_` khớp được xác định bởi DBMS, mã hóa và trong một số hệ bởi collation. Nếu yêu cầu là “chính xác ba ký tự người dùng nhìn thấy”, phải xác định riêng khái niệm **grapheme cluster** và cách xử lý ở ứng dụng; không mặc nhiên coi `LIKE '___'` là phép đếm ba grapheme dùng được ở mọi hệ.

## 3. LIKE so khớp toàn bộ giá trị, không tự tìm đoạn con

Đây là điểm thường gây lỗi khi mới học:

```sql
-- PostgreSQL:
SELECT
    'SQL Server' LIKE 'SQL' AS match_entire_value,
    'SQL Server' LIKE 'SQL%' AS match_prefix,
    'SQL Server' LIKE '%SQL%' AS match_anywhere,
    'Intro to SQL' LIKE '%SQL' AS match_suffix;
```

`'SQL Server' LIKE 'SQL'` trả `FALSE` vì còn phần ` Server` chưa được mẫu tiêu thụ. Ba biểu thức còn lại trả `TRUE`.

So sánh ý nghĩa của các cách lọc:

| Điều kiện | Câu hỏi được trả lời |
| --- | --- |
| `name = 'SQL'` | Giá trị có bằng `SQL` theo quy tắc so sánh hay không? |
| `name LIKE 'SQL'` | Giá trị có khớp mẫu **không wildcard** `SQL` hay không? |
| `name LIKE 'SQL%'` | Có bắt đầu bằng `SQL` không? |
| `name LIKE '%SQL%'` | Có chứa đoạn `SQL` không? |
| `name LIKE '%SQL'` | Có kết thúc bằng `SQL` không? |

`LIKE` và `=` với mẫu không wildcard có thể khác nhau trong một số tình huống liên quan khoảng trắng, kiểu dữ liệu, collation hoặc quy tắc DBMS. Đừng thay thế cơ học `=` bằng `LIKE` khi muốn kiểm tra khóa định danh **chính xác**.

## 4. Khi % và _ là dữ liệu thật: dùng ESCAPE

Giả sử một mã hàng thực sự có dạng `A_1`, một nhãn phần trăm là `100%` hoặc một dấu `!` xuất hiện trong tên. Muốn tìm các ký tự đó theo **nghĩa nguyên văn**, ta không được để parser `LIKE` hiểu chúng là wildcard.

Cú pháp thông dụng:

```sql
expression LIKE 'pattern' ESCAPE '!'
```

Trong ví dụ này, `!` là **ký tự thoát dành cho mẫu**. Khi đứng trước `%` hoặc `_`, nó khiến ký tự đại diện đó được hiểu theo nghĩa thông thường.

| Mẫu với `ESCAPE '!'` | Khớp với | Không khớp với |
| --- | --- | --- |
| `'A!_1'` | `A_1` | `AB1`, `A%1` |
| `'A!%1'` | `A%1` | `A_1`, `AX1` |
| `'100!%'` | `100%` | `1000` |
| `'A!!B'` | `A!B` | `A_B` |
| `'%!%%'` | Mọi chuỗi chứa ký tự `%` | Chuỗi không chứa `%` |
| `'%!_%'` | Mọi chuỗi chứa ký tự `_` | Chuỗi không chứa `_` |
| `'%!!%'` | Mọi chuỗi chứa ký tự `!` | Chuỗi không chứa `!` |

Đọc kỹ từng trường hợp:

- `!%` nghĩa là một **dấu % thật**, không phải wildcard.
- `!_` nghĩa là một **dấu _ thật**, không phải wildcard.
- `!!` nghĩa là một **dấu ! thật**, vì ký tự escape cũng cần được thoát khi nằm trong mẫu.
- `%` **không có ! phía trước** vẫn mang nghĩa wildcard.

Ví dụ PostgreSQL:

```sql
SELECT
    'A_1' LIKE 'A!_1' ESCAPE '!' AS underscore_literal,
    'AX1' LIKE 'A!_1' ESCAPE '!' AS not_underscore,
    'A%1' LIKE 'A!%1' ESCAPE '!' AS percent_literal,
    'A!B' LIKE 'A!!B' ESCAPE '!' AS escape_character_literal,
    'Giảm 20%' LIKE '%!%%' ESCAPE '!' AS contains_percent;
```

Các biểu thức đúng nghĩa nguyên văn trả `TRUE`; `'AX1' LIKE 'A!_1' ESCAPE '!'` trả `FALSE`.

### Một mẫu có thể dùng cả ký tự nguyên văn và wildcard

```sql
-- Bắt đầu bằng đúng hai ký tự A_, sau đó còn bao nhiêu ký tự cũng được:
SELECT product_code
FROM products
WHERE product_code LIKE 'A!_%' ESCAPE '!';

-- Chứa đúng đoạn A% ở vị trí bất kỳ:
SELECT product_code
FROM products
WHERE product_code LIKE '%A!%%' ESCAPE '!';
```

Mẫu `'A!_%'` được đọc là:

```text
A    ! _    %
|     |     |
|     |     +--- wildcard: 0 hoặc nhiều ký tự phía sau
|     +--------- dấu _ nguyên văn
+--------------- chữ A nguyên văn

Giá trị khớp: A_, A_1, A_2026
Không khớp: AX1, A%1
```

Đây là lợi ích của `ESCAPE`: **chỉ vô hiệu hóa những wildcard cần xem là dữ liệu**, vẫn giữ những wildcard khác nhằm tìm tiền tố/hậu tố/đoạn con.

## 5. Quy tắc chọn ký tự ESCAPE và các lỗi thường gặp

Thông thường, đối số sau `ESCAPE` phải biểu diễn **một ký tự** theo quy tắc DBMS. Bạn có thể chọn `!`, `#` hoặc ký tự khác được hệ hỗ trợ; chọn `!` thường thuận tiện khi muốn tránh sự khác biệt về dấu gạch chéo ngược.

```sql
-- Hai cách tương đương về ý tưởng:
SELECT 'A_1' LIKE 'A!_1' ESCAPE '!' AS using_bang;
SELECT 'A_1' LIKE 'A#_1' ESCAPE '#' AS using_hash;
```

Nếu mẫu cần chứa **chính ký tự escape**, phải nhân đôi nó:

```sql
-- Tìm dấu ! theo nghĩa nguyên văn ở bất kỳ vị trí nào:
SELECT 'A!B' LIKE '%!!%' ESCAPE '!' AS has_bang;
```

Không để ký tự escape đứng cuối mẫu mà thiếu ký tự được nó thoát:

```sql
-- Sai quy tắc mẫu: ! ở cuối không theo sau bởi ký tự cần thoát.
-- Trên PostgreSQL, LIKE có thể báo lỗi khi thực thi:
-- SELECT 'A!' LIKE 'A!' ESCAPE '!';
```

Một số tổ hợp escape không hợp lệ hoặc được xử lý khác nhau theo DBMS. Hãy đặt ký tự escape trước đúng `%`, `_` hoặc chính ký tự escape; không dùng `!` trước mọi chữ cái theo thói quen của ngôn ngữ lập trình.

### ESCAPE của LIKE khác escape của SQL string literal

Câu lệnh có **hai lớp diễn giải**:

1. Parser SQL đọc `'A!_%'` thành một **giá trị chuỗi** có các ký tự `A`, `!`, `_`, `%`.
2. Toán tử `LIKE` đọc **giá trị chuỗi đó** như một mẫu, dựa vào `ESCAPE '!'` để nhận ra `!_` là dấu gạch dưới nguyên văn.

Ví dụ chứa dấu nháy đơn trong cả dữ liệu tìm kiếm:

```sql
-- Muốn tìm tên có đúng đoạn O'Brien (dấu ' là dữ liệu).
-- Trong SQL literal, dấu ' nằm trong dữ liệu phải viết thành ''.
SELECT customer_name
FROM customers
WHERE customer_name LIKE '%O''Brien%';
```

Dấu nháy đơn trong `O'Brien` phải được **nhân đôi trong SQL literal**. Nó không phải wildcard của `LIKE`; vì vậy không cần `ESCAPE` để xử lý dấu nháy đơn ở ví dụ này.

Ngược lại, tìm chính ký tự `%` hay `_` trong văn bản không thể chỉ nhân đôi dấu nháy đơn: phải xử lý **wildcard của `LIKE`** bằng `ESCAPE` hoặc cơ chế đặc thù DBMS.

## 6. NULL, NOT LIKE và logic ba giá trị

Trong SQL, so sánh bằng `LIKE` với `NULL` thường cho kết quả logic **UNKNOWN**. Dòng có `NULL` không được `WHERE` chọn, kể cả khi mẫu là `'%'`.

```sql
-- PostgreSQL:
SELECT
    'ABC' LIKE 'A%' AS normal_match,
    CAST(NULL AS VARCHAR(30)) LIKE 'A%' AS missing_value,
    'ABC' LIKE CAST(NULL AS VARCHAR(30)) AS missing_pattern;
```

`normal_match` là `TRUE`; hai biểu thức còn lại là `NULL` (trạng thái UNKNOWN), không phải `FALSE`.

Điều tương tự xảy ra với `NOT LIKE`:

```sql
SELECT note_text
FROM products
WHERE note_text NOT LIKE '%!%%' ESCAPE '!';
```

Câu này lấy các giá trị **không NULL** và không chứa dấu `%`. Nó **không** lấy các dòng có `note_text IS NULL` vì `NOT UNKNOWN` vẫn là UNKNOWN.

Nếu muốn lấy cả các dòng không có ghi chú:

```sql
SELECT note_text
FROM products
WHERE note_text NOT LIKE '%!%%' ESCAPE '!'
   OR note_text IS NULL;
```

Một điểm nữa: trong các DBMS phân biệt `''` và `NULL` như PostgreSQL, `'' LIKE '%'` là `TRUE` nhưng `NULL LIKE '%'` là UNKNOWN. **Oracle Database** hiện coi chuỗi rỗng là `NULL` trong các ngữ cảnh chuỗi ký tự, do đó kết quả liên quan chuỗi rỗng cần xem riêng theo Oracle.

## 7. Hoa thường, dấu tiếng Việt và collation

`LIKE` không mang quy tắc “luôn phân biệt” hay “luôn bỏ qua” chữ hoa, chữ thường và dấu cho mọi DBMS. Kết quả còn chịu tác động từ **collation**, kiểu ký tự, phiên bản engine hoặc các chế độ so sánh.

| DBMS | Điều cần biết khi dùng LIKE |
| --- | --- |
| **PostgreSQL** | `LIKE` làm việc theo ngữ nghĩa và collation PostgreSQL; `ILIKE` là cú pháp riêng để khớp không phân biệt hoa/thường theo locale. |
| **MySQL / MariaDB** | `LIKE` chịu ảnh hưởng collation của biểu thức/cột: nhiều collation `_ci` không phân biệt hoa thường, các collation `_bin` hoặc `_cs` có hành vi khác. |
| **SQL Server** | Collation, thường có hậu tố `CI`/`CS`, `AI`/`AS`, tác động đến so sánh; T-SQL còn có mẫu ký tự trong ngoặc vuông. |
| **SQLite** | `LIKE` mặc định thường không phân biệt hoa/thường với ASCII cơ bản, nhưng không mở rộng đầy đủ ra Unicode; các extension như ICU có thể thay đổi khả năng này. |
| **Oracle Database** | Hành vi đối chiếu phụ thuộc cấu hình collation, phiên bản và các quy tắc so sánh ngôn ngữ có hiệu lực. |

Ví dụ PostgreSQL:

```sql
-- LIKE và ILIKE là hai toán tử khác nhau trong PostgreSQL:
SELECT
    'Sql' LIKE 'SQL' AS ordinary_like,
    'Sql' ILIKE 'SQL' AS ignore_case_like;

-- Tìm tên có tiền tố Sql không phân biệt hoa thường:
SELECT product_name
FROM products
WHERE product_name ILIKE 'sql%';
```

Không mặc nhiên cho rằng `ILIKE` tự bỏ dấu tiếng Việt hoặc tự thực hiện tìm gần đúng. Không phân biệt hoa thường, không phân biệt dấu, Unicode normalization và tìm kiếm gần đúng là **những yêu cầu khác nhau**.

Nếu ứng dụng cần chính xác quy tắc khớp, hãy ghi rõ DBMS, phiên bản, collation và trường hợp kiểm thử như `'A'`/`'a'`, `'a'`/`'á'`, cũng như chuỗi dùng mã điểm ghép sẵn/tách dấu.

## 8. Phân biệt LIKE với so sánh bằng và biểu thức chính quy

`LIKE` phù hợp với một nhóm mẫu đơn giản, nhưng không phải ngôn ngữ biểu thức chính quy (regular expression).

| Mục tiêu | Dùng |
| --- | --- |
| Bằng chính xác một mã | `=` cùng collation/kiểu dữ liệu phù hợp |
| Bắt đầu bằng một tiền tố | `LIKE 'ABC%'` |
| Chứa đoạn văn bản | `LIKE '%ABC%'` |
| Đúng một ký tự bất kỳ | `LIKE '_'` |
| Tìm dấu `%` hoặc `_` nguyên văn | `LIKE ... ESCAPE '!'` |
| Mẫu nhiều nhóm, lựa chọn `A` hoặc `B`, điều kiện lặp phức tạp | Xem tính năng regex đặc thù DBMS hoặc mô hình dữ liệu khác |
| Tìm văn bản theo từ/ngữ nghĩa/xếp hạng liên quan | Full-text search hoặc công cụ tìm kiếm phù hợp |

Các dấu `^` và `$` **không phải ký tự neo đầu/cuối trong LIKE** như ở nhiều regex engine. Dấu `*` cũng không thay `%`. Ví dụ `LIKE 'A*'` thường chỉ tìm chuỗi hai ký tự `A*` theo nghĩa nguyên văn, chứ không có nghĩa “bắt đầu bằng A”.

Ví dụ:

```sql
-- Với LIKE, * không phải wildcard của SQL chuẩn:
SELECT
    'ABCD' LIKE 'A*' AS regex_assumption_wrong,
    'A*' LIKE 'A*' AS literal_star;
```

Trên PostgreSQL, biểu thức thứ nhất là `FALSE` và biểu thức thứ hai là `TRUE`.

Trong SQL Server, T-SQL `LIKE` còn hỗ trợ thêm cú pháp như `[abc]`, `[a-z]` và `[^abc]`. Đó là **mở rộng riêng**; một mẫu T-SQL có dấu ngoặc vuông không nhất thiết có nghĩa tương tự trên PostgreSQL, MySQL, SQLite hay Oracle. Nếu người dùng có thể nhập `[`/`]` trong chuỗi cần tìm nguyên văn trên SQL Server, phải xử lý các ký tự đặc biệt của T-SQL `LIKE` theo đúng quy tắc SQL Server.

## 9. Dùng LIKE trên dữ liệu nhận từ ứng dụng một cách an toàn

Một tình huống rất phổ biến: ứng dụng nhận từ khóa người dùng, rồi tạo truy vấn tìm sản phẩm có tên chứa từ khóa đó.

**Không nối trực tiếp từ khóa vào văn bản SQL**, vì đầu vào có thể chứa dấu nháy đơn hoặc đoạn mã SQL dẫn đến **SQL injection**.

```java
// Không dùng cách này với dữ liệu từ người dùng:
String sql = "SELECT * FROM products WHERE product_name LIKE '%"
        + userInput + "%'";
```

Giải pháp bảo vệ cú pháp SQL là **prepared statement và bind parameter**. Nhưng cần phân biệt **hai mục tiêu**:

1. **An toàn về SQL injection:** đưa từ khóa vào placeholder, không nối nó thành đoạn câu lệnh.
2. **Tìm kiếm nguyên văn:** nếu `%`, `_` hoặc ký tự escape nằm trong từ khóa, xử lý chúng trước khi đưa vào **pattern**.

Bind parameter chỉ giải quyết mục tiêu thứ nhất. Ví dụ người dùng nhập `A_1` và ứng dụng bind `'%A_1%'`; dù không có SQL injection, dấu `_` vẫn là wildcard, nên kết quả có thể chứa `AX1`.

### 9.1. Tạo pattern nguyên văn trước khi bind

Ví dụ **Java JDBC với PostgreSQL** (cách xử lý pattern với `ESCAPE '!'` cũng dùng được trên nhiều DBMS hỗ trợ cú pháp tương ứng):

```java
// inputText là chuỗi tìm kiếm do người dùng nhập, không phải SQL.
String inputText = "A_1";

// Thoát ký tự escape trước, rồi đến hai ký tự wildcard.
String escaped = inputText
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

// Ghép wildcard do ỨNG DỤNG chủ động thêm để tìm theo dạng "chứa".
String likePattern = "%" + escaped + "%";

String sql = """
        SELECT product_id, product_name
        FROM products
        WHERE product_name LIKE ? ESCAPE '!'
        ORDER BY product_id
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, likePattern);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("product_id")
                    + ": " + rs.getString("product_name"));
        }
    }
}
```

Ví dụ này giả sử `connection` là đối tượng `java.sql.Connection` đã kết nối; các lớp `PreparedStatement`/`ResultSet` thuộc `java.sql`. Trong mã thật, chương trình cần kiểm tra giá trị `null` từ input và quản lý kết nối, lỗi và phân trang theo yêu cầu ứng dụng.

Với `inputText = "A_1"`, biến `likePattern` trở thành `"%A!_1%"`. Mẫu này tìm **đúng chuỗi `A_1`**, nằm ở bất kỳ vị trí nào trong tên. Nó không xem `_` từ người dùng là wildcard.

**Thứ tự thay thế rất quan trọng:** phải thay `!` thành `!!` **trước** khi thêm `!` vào trước `%` hoặc `_`. Nếu làm ngược, thao tác thay `!` sau cùng có thể thoát lần nữa những ký tự escape vừa được tạo, làm thay đổi ý nghĩa mẫu.

### 9.2. Tách rõ kiểu tìm kiếm

Nếu ứng dụng cho người dùng **tự viết mẫu wildcard**, `%` và `_` có thể được phép giữ nguyên ý nghĩa theo thiết kế sản phẩm. Khi đó vẫn dùng prepared statement để chống SQL injection, nhưng công bố rõ cú pháp tìm kiếm, xác định ký tự escape và giới hạn truy vấn tốn tài nguyên nếu cần.

Nếu ứng dụng chỉ cung cấp ô **“Tìm đúng cụm từ tôi nhập”**, nên xử lý wildcard từ người dùng theo nghĩa nguyên văn như ví dụ Java. Hai cách phục vụ nhu cầu khác nhau.

Lưu ý: đoạn mã thay `!`, `%`, `_` là ví dụ cho cú pháp `LIKE` kiểu SQL phổ biến. **SQL Server** có thêm cú pháp mẫu `[...]`, nên ứng dụng SQL Server cần xử lý cả các ký tự đặc biệt của T-SQL khi yêu cầu so khớp nguyên văn; hãy dùng logic dành riêng cho dialect đang thực thi.

## 10. Hiệu năng: điều kiện LIKE nào có thể dùng index?

Một biểu thức `LIKE` có thể duyệt nhiều giá trị để so khớp mẫu. Khả năng dùng index phụ thuộc thứ tự wildcard, kiểu index, collation, DBMS, phân bố dữ liệu và kế hoạch truy vấn.

| Mẫu | Tình huống điển hình |
| --- | --- |
| `'ABC%'` | Có **tiền tố cố định** `ABC`; B-tree index phù hợp có thể hỗ trợ truy tìm theo tiền tố |
| `'ABC_'` | Có tiền tố cố định và phần cuối một wildcard; có thể tận dụng điều kiện tiền tố trong một số kế hoạch |
| `'A!_%' ESCAPE '!'` | Có tiền tố **nguyên văn** `A_`; có thể là điều kiện tiền tố |
| `'%ABC'` | Bắt đầu bằng wildcard; B-tree thông thường thường khó hỗ trợ tìm kiếm hiệu quả |
| `'%ABC%'` | Tìm đoạn con tùy vị trí; thường cần kỹ thuật chỉ mục tìm chuỗi chuyên biệt hoặc quét |
| `'%'` | Có thể khớp mọi giá trị không `NULL`; thường ít tính chọn lọc |

Ví dụ PostgreSQL:

```sql
EXPLAIN
SELECT product_id, product_code
FROM products
WHERE product_code LIKE 'AB%';

EXPLAIN
SELECT product_id, product_code
FROM products
WHERE product_code LIKE '%AB%';
```

Ở database nhỏ, bộ tối ưu có thể chọn **sequential scan** cho cả hai truy vấn vì chi phí thấp hơn dùng index. Với PostgreSQL, để tăng khả năng dùng B-tree cho `LIKE 'prefix%'` dưới collation không phải `C`, có thể cần operator class như `text_pattern_ops`/`varchar_pattern_ops` hoặc chiến lược index phù hợp. Đây là quyết định riêng theo engine và workload, không có nghĩa thêm mọi index đều làm truy vấn nhanh hơn.

Ví dụ nếu cần tìm đoạn con trên dữ liệu lớn, PostgreSQL có extension `pg_trgm` và kiểu index phù hợp để hỗ trợ một số truy vấn `LIKE`/`ILIKE`; DBMS khác có cơ chế khác. Cân nhắc chi phí lưu trữ, cập nhật index và khả năng mở extension trước khi triển khai.

**Một lưu ý khác:** `LOWER(column) LIKE 'abc%'` hoặc `ILIKE` có thể đòi hỏi cách tổ chức index riêng. Nếu mục tiêu là tìm không phân biệt hoa thường, chọn collation/index phù hợp từ thiết kế thay vì mặc nhiên bọc mọi cột bằng hàm và kỳ vọng index cũ vẫn có hiệu quả.

## 11. Thực hành đầy đủ trên PostgreSQL

Phần này tạo bảng `sql_like_lab` riêng trong database thực hành. Các câu `SELECT` sử dụng `COLLATE "C"` ở cột mã khi cần kết quả phân biệt hoa/thường rõ ràng, tránh suy diễn từ collation của môi trường. Nếu đã có bảng cùng tên, dùng database/schema thử nghiệm khác hoặc đổi tên bảng trước khi chạy.

### 11.1. Tạo bảng và dữ liệu

```sql
CREATE TABLE sql_like_lab (
    product_id   INTEGER PRIMARY KEY,
    product_code VARCHAR(20) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    note_text    VARCHAR(100)
);

INSERT INTO sql_like_lab
    (product_id, product_code, product_name, note_text)
VALUES
    (1,  'AB1',  'Áo basic',       'Giảm 20%'),
    (2,  'AB12', 'Áo khoác',       'Mã A_1'),
    (3,  'A_1',  'Áo mẫu',         'Dùng ! để đánh dấu'),
    (4,  'A%1',  'Áo giới hạn',    NULL),
    (5,  'AX1',  'Túi A',          'Giao nhanh'),
    (6,  'B01',  'Giày thể thao',  ''),
    (7,  'AB',   'Áo sơ mi',       'A!B'),
    (8,  'ab3',  'Áo thể thao',    'Đang bán'),
    (9,  'ABC',  'Áo len',         '25% off'),
    (10, 'A!2',  'Áo in',          'x%y');
```

Bảng có mã chứa ký tự chữ/số bình thường (`AB1`, `AX1`), ký tự wildcard theo nghĩa dữ liệu (`A_1`, `A%1`), ký tự escape `A!2`, chuỗi rỗng ở `note_text` của dòng 6 và `NULL` ở `note_text` của dòng 4.

### 11.2. Lọc theo tiền tố và số ký tự

```sql
-- Mã bắt đầu đúng bằng AB, phân biệt chữ hoa/thường:
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'AB%'
ORDER BY product_id;

-- Mã AB theo sau đúng một ký tự:
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'AB_'
ORDER BY product_id;
```

Kết quả dự kiến:

| Điều kiện | `product_id` |
| --- | --- |
| `LIKE 'AB%'` | 1, 2, 7, 9 |
| `LIKE 'AB_'` | 1, 9 |

`AB12` không khớp `AB_` vì có **hai ký tự** sau `AB`; `AB` không khớp vì có **0 ký tự** sau `AB`. `ab3` không khớp cả hai mẫu trong ví dụ có `COLLATE "C"` vì khác chữ hoa/chữ thường.

### 11.3. Nhận thấy lỗi khi quên ESCAPE

```sql
-- Sai nếu chỉ muốn mã A_1: dấu _ ở đây là wildcard.
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'A_1'
ORDER BY product_id;
```

Truy vấn trên khớp ba mã: `A_1` (id 3), `A%1` (id 4) và `AX1` (id 5). Vì `_` đại diện cho đúng một ký tự, cả chữ `X` và dấu `%` trong **dữ liệu** đều được chấp nhận.

Sửa bằng `ESCAPE`:

```sql
-- Chỉ khớp dấu _ thật:
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'A!_1' ESCAPE '!'
ORDER BY product_id;

-- Chỉ khớp dấu % thật:
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'A!%1' ESCAPE '!'
ORDER BY product_id;

-- Chỉ khớp dấu ! thật:
SELECT product_id, product_code
FROM sql_like_lab
WHERE product_code COLLATE "C" LIKE 'A!!2' ESCAPE '!'
ORDER BY product_id;
```

Ba truy vấn trả lần lượt `product_id` 3, 4 và 10.

### 11.4. Tìm ký tự đặc biệt ở bất kỳ vị trí nào

```sql
-- Ghi chú chứa dấu phần trăm % thật:
SELECT product_id, note_text
FROM sql_like_lab
WHERE note_text LIKE '%!%%' ESCAPE '!'
ORDER BY product_id;

-- Ghi chú chứa gạch dưới _ thật:
SELECT product_id, note_text
FROM sql_like_lab
WHERE note_text LIKE '%!_%' ESCAPE '!'
ORDER BY product_id;

-- Ghi chú chứa ký tự escape ! thật:
SELECT product_id, note_text
FROM sql_like_lab
WHERE note_text LIKE '%!!%' ESCAPE '!'
ORDER BY product_id;
```

Kết quả dự kiến:

| Tìm ký tự | `product_id` |
| --- | --- |
| `%` | 1, 9, 10 |
| `_` | 2 |
| `!` | 3, 7 |

Dấu `%` ở **hai bên** của mẫu `'%!%%'` là wildcard dùng để tìm ở bất kỳ vị trí nào. Phần `!%` ở giữa là một dấu phần trăm cần khớp nguyên văn.

### 11.5. NOT LIKE và NULL

```sql
SELECT product_id, note_text
FROM sql_like_lab
WHERE note_text NOT LIKE '%!%%' ESCAPE '!'
ORDER BY product_id;

SELECT product_id, note_text
FROM sql_like_lab
WHERE note_text NOT LIKE '%!%%' ESCAPE '!'
   OR note_text IS NULL
ORDER BY product_id;
```

Truy vấn thứ nhất loại trừ dòng có `NULL` và dòng chứa `%`. Truy vấn thứ hai **bao gồm thêm** dòng có `note_text IS NULL` (id 4). Dòng có chuỗi rỗng (id 6) được cả hai truy vấn chọn vì nó là giá trị chuỗi đã biết và không chứa `%`.

### 11.6. Đếm bản ghi khớp mẫu

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE product_code COLLATE "C" LIKE 'AB%'
    ) AS codes_starting_ab,
    COUNT(*) FILTER (
        WHERE note_text LIKE '%!%%' ESCAPE '!'
    ) AS notes_containing_percent,
    COUNT(note_text) AS non_null_notes
FROM sql_like_lab;
```

Đây là cú pháp `FILTER` hỗ trợ trên PostgreSQL. Với dữ liệu ví dụ, kết quả là:

- `total_rows = 10`.
- `codes_starting_ab = 4`.
- `notes_containing_percent = 3`.
- `non_null_notes = 9` (chuỗi rỗng được `COUNT(column)` đếm vì khác `NULL`).

### 11.7. Xóa bảng thử nếu không cần nữa

```sql
-- Chỉ chạy nếu bảng sql_like_lab do bạn tự tạo cho bài học:
DROP TABLE sql_like_lab;
```

Không dùng `DROP TABLE` trên bảng nghiệp vụ thật hoặc trong database dùng chung.

## 12. Khác biệt cú pháp và hành vi giữa các DBMS

### PostgreSQL

PostgreSQL hỗ trợ `LIKE`, `NOT LIKE`, `ILIKE` và `ESCAPE`:

```sql
-- PostgreSQL:
SELECT 'A_1' LIKE 'A!_1' ESCAPE '!' AS literal_underscore;
SELECT 'Sql' ILIKE 'SQL' AS ignore_case;
```

Trong PostgreSQL, ký tự backslash có thể đóng vai trò escape mặc định trong `LIKE` nếu không viết `ESCAPE`. Đồng thời, cách diễn giải **backslash bên trong SQL string literal** phụ thuộc vào cú pháp literal và cấu hình như `standard_conforming_strings`. Để bài học dễ hiểu và di chuyển hơn, các ví dụ đều chỉ định `ESCAPE '!'` rõ ràng, tránh trộn dấu escape của literal SQL với dấu escape của mẫu.

PostgreSQL còn cho phép một số cú pháp đặc thù như `ESCAPE ''` để tắt escape của mẫu trong những trường hợp được hỗ trợ; không suy ra đây là cú pháp di động cho mọi DBMS.

### MySQL và MariaDB

MySQL/MariaDB hỗ trợ `LIKE` và `ESCAPE`. Khi dùng mẫu có dấu `%` và `_` theo nghĩa nguyên văn:

```sql
-- MySQL / MariaDB:
SELECT 'A_1' LIKE 'A!_1' ESCAPE '!' AS literal_underscore;
SELECT 'A%1' LIKE 'A!%1' ESCAPE '!' AS literal_percent;
```

Kết quả khớp chữ hoa/thường phụ thuộc collation. Ngoài ra, cách xử lý backslash trong **string literal** và **mẫu LIKE** có thể phụ thuộc cấu hình `sql_mode`, đặc biệt `NO_BACKSLASH_ESCAPES`; hãy kiểm tra trước khi dùng các ví dụ gắn với `\`. Chọn `ESCAPE '!'` giúp nêu rõ ý định của mẫu mà không phải dựa vào backslash mặc định.

Một vấn đề thực tế: MySQL và MariaDB có các collation/phiên bản khác nhau. Nếu dự án yêu cầu tìm kiếm có/không phân biệt dấu, hãy kiểm tra **collation cụ thể** thay vì giả định `LIKE` tự bỏ dấu tiếng Việt.

### SQL Server (T-SQL)

SQL Server hỗ trợ `LIKE ... ESCAPE`:

```sql
-- SQL Server:
SELECT
    CASE
        WHEN N'A_1' LIKE N'A!_1' ESCAPE N'!' THEN 1
        ELSE 0
    END AS literal_underscore;
```

Prefix `N` tạo Unicode string literal trong T-SQL. SQL Server còn có ký tự đặc biệt dạng **mẫu ngoặc vuông** như `[A-Z]` hoặc `[^0-9]`. Chúng không thuộc hai wildcard cơ bản của SQL chuẩn; vì thế, bộ xử lý input nguyên văn cho SQL Server phải tính tới quy tắc ngoặc vuông. Không áp dụng mù quáng đoạn mã chỉ thoát `%`, `_`, `!` của một ứng dụng dùng PostgreSQL.

SQL Server thường sử dụng collation để quyết định phân biệt chữ hoa và dấu. Một điều kiện `LIKE N'%Áo%'` có thể có kết quả khác theo hậu tố `CI`/`CS` hoặc `AI`/`AS` của collation.

### SQLite

SQLite hỗ trợ `LIKE` và biểu thức `ESCAPE`:

```sql
-- SQLite:
SELECT 'A_1' LIKE 'A!_1' ESCAPE '!' AS literal_underscore;
```

Cấu hình `LIKE` mặc định thường xử lý không phân biệt hoa/thường cho **ASCII** cơ bản, không có đầy đủ Unicode case folding. SQLite có thể mở rộng khả năng so khớp thông qua extension như ICU, nhưng không mặc định mọi bản cài có extension đó.

Trường hợp dùng `LIKE` cùng `ESCAPE`, chỉ định ký tự escape một cách minh bạch và thử với dữ liệu có dấu để biết hành vi của bản SQLite đang chạy.

### Oracle Database

Oracle hỗ trợ `LIKE ... ESCAPE`, ví dụ:

```sql
-- Oracle Database; FROM DUAL dùng được trong nhiều phiên bản Oracle:
SELECT
    CASE
        WHEN 'A_1' LIKE 'A!_1' ESCAPE '!' THEN 'MATCH'
        ELSE 'NO MATCH'
    END AS matching_result
FROM DUAL;
```

Oracle có những khác biệt về collation, cách xử lý chuỗi rỗng và kiểu Unicode. Nếu cần tìm theo đơn vị ký tự/phần tử Unicode ở cấp độ cụ thể, Oracle còn có các biến thể `LIKEC`, `LIKE2`, `LIKE4` theo phiên bản; không nên coi chúng là cú pháp phổ biến ở các hệ khác.

## 13. Những lỗi hay gặp khi dùng LIKE và ESCAPE

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `LIKE 'A_1'` trả thêm `AX1` | `_` là wildcard một ký tự | `LIKE 'A!_1' ESCAPE '!'` |
| `LIKE '100%'` khớp cả `1000` | `%` là wildcard nhiều ký tự | `LIKE '100!%' ESCAPE '!'` |
| `LIKE 'SQL'` không tìm được `Intro SQL` | Mẫu phải khớp toàn bộ chuỗi | `LIKE '%SQL%'` |
| `LIKE 'AB_'` không khớp `AB` | `_` bắt buộc một ký tự | Dùng `LIKE 'AB%'` nếu cho phép không hoặc nhiều ký tự |
| `LIKE '%!%%'` khó đọc | Có cả wildcard và phần trăm nguyên văn | Tách mẫu thành `%` + `!%` + `%` |
| Mẫu có `!` nguyên văn lại không khớp | `!` được định nghĩa là escape | Đổi `!` thành `!!` trong pattern |
| `NOT LIKE` không trả các dòng `NULL` | `UNKNOWN` không được `WHERE` chọn | Thêm `OR col IS NULL` nếu nghiệp vụ yêu cầu |
| Kết quả thay đổi giữa DBMS | Khác collation, Unicode, cú pháp mẫu | Ghi đúng DBMS/phiên bản/collation; kiểm thử |
| Tìm kiếm từ form trả quá nhiều dòng khi nhập `%` | Wildcard của người dùng chưa được thoát | Bind parameter và thoát `%`/`_`/ký tự escape nếu cần tìm nguyên văn |
| Câu SQL bị lỗi hoặc bị chèn lệnh khi dùng input | Nối trực tiếp dữ liệu vào SQL text | Prepared statement, tham số hóa |
| Tìm `'%abc%'` bị chậm trên bảng lớn | Wildcard đầu mẫu thường không tận dụng B-tree thông thường | Đánh giá index chuyên biệt/chiến lược tìm kiếm và kế hoạch thực thi |
| Dấu `\` làm kết quả khác lạ | Quy tắc SQL string literal hoặc LIKE escape khác DBMS/mode | Dùng `ESCAPE` rõ ràng và tách hai lớp escape |

## 14. Bài tập vận dụng

### Bài 1 — Giải thích wildcard

Cho các chuỗi `AB`, `AB1`, `AB12`, `A_1`, `AX1`, `A%1` và `XYZ`. Hãy liệt kê những chuỗi khớp từng mẫu sau, giả sử cách so khớp phân biệt chữ hoa/thường:

1. `'AB%'`
2. `'AB_'`
3. `'A_1'`
4. `'%1'`
5. `'A%'`

### Bài 2 — Viết ESCAPE

Dùng `ESCAPE '!'` để viết mẫu cho các yêu cầu:

1. Mã sản phẩm **bằng chính xác** `A_1`.
2. Mã sản phẩm **bắt đầu** bằng hai ký tự thật `A%`.
3. Ghi chú **chứa** dấu `%` ở bất kỳ vị trí nào.
4. Ghi chú **chứa** dấu `_` ở bất kỳ vị trí nào.
5. Ghi chú **chứa** dấu `!` ở bất kỳ vị trí nào.

### Bài 3 — Phân biệt hai lớp escape

Vì sao `LIKE '%O''Brien%'` cần viết hai dấu nháy đơn, trong khi `LIKE '%!_%' ESCAPE '!'` lại dùng `!`? Trong hai ví dụ, dấu nào thuộc cú pháp **literal SQL**, dấu nào thuộc **mẫu LIKE**?

### Bài 4 — NULL và NOT LIKE

Bảng `notes` có ba dòng: `note_text = 'Giảm 20%'`, `note_text = 'Chờ duyệt'` và `note_text = NULL`. Viết điều kiện để lấy **những ghi chú không chứa dấu %**, **bao gồm cả bản ghi thiếu ghi chú**.

### Bài 5 — Tìm kiếm từ ứng dụng

Người dùng nhập `A_1` vào ô “Tìm cụm từ nguyên văn”. Vì sao chỉ dùng `PreparedStatement` với pattern `'%A_1%'` vẫn có thể cho kết quả sai? Viết giá trị pattern đúng với `ESCAPE '!'`.

### Bài 6 — Hiệu năng và điều kiện tiền tố

So sánh `WHERE product_code LIKE 'AB%'` với `WHERE product_code LIKE '%AB%'`: câu nào thường có cơ hội tận dụng B-tree index tốt hơn và vì sao? Cần kiểm tra điều kiện nào trước khi khẳng định truy vấn sẽ dùng index?

### Gợi ý đáp án

1. `'AB%'`: `AB`, `AB1`, `AB12`; `'AB_'`: `AB1`; `'A_1'`: `A_1`, `AX1`, `A%1`; `'%1'`: `AB1`, `A_1`, `AX1`, `A%1`; `'A%'`: tất cả các chuỗi bắt đầu bằng `A` trong danh sách.
2. `LIKE 'A!_1' ESCAPE '!'`; `LIKE 'A!%%' ESCAPE '!'`; `LIKE '%!%%' ESCAPE '!'`; `LIKE '%!_%' ESCAPE '!'`; `LIKE '%!!%' ESCAPE '!'`.
3. `''` biểu diễn một dấu nháy đơn trong **SQL literal**; `!_` biểu diễn dấu gạch dưới nguyên văn trong **LIKE pattern** khi đã định nghĩa `ESCAPE '!'`.
4. `WHERE note_text NOT LIKE '%!%%' ESCAPE '!' OR note_text IS NULL`.
5. `PreparedStatement` bảo vệ cú pháp SQL, nhưng dấu `_` trong pattern vẫn mang nghĩa wildcard. Pattern đúng là `'%A!_1%'`.
6. `'AB%'` thường có cơ hội tận dụng index cho tiền tố cố định, trong khi `'%AB%'` có wildcard đầu tiên. Cần xem DBMS, kiểu index/operator class, collation, độ lớn dữ liệu và `EXPLAIN`.

Hiểu `LIKE` là hiểu **ngôn ngữ mẫu**: `%` cho phép một đoạn dài tùy ý, `_` yêu cầu đúng một ký tự, còn `ESCAPE` làm rõ khi các dấu ấy phải được xem là **dữ liệu nguyên văn**. Khi truy vấn được tạo từ input người dùng, hãy dùng tham số SQL và xử lý wildcard theo đúng kiểu tìm kiếm mà ứng dụng công bố.
