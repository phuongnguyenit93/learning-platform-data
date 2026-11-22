# Chuỗi độ dài cố định, chuỗi biến đổi và văn bản dài

Trong cơ sở dữ liệu quan hệ, dữ liệu dạng chữ xuất hiện ở hầu hết các bảng: mã quốc gia, tên người dùng, địa chỉ email, tiêu đề bài viết, mô tả sản phẩm, nội dung bình luận và tài liệu dài. Dù tất cả đều là “chuỗi”, cách lưu trữ và giới hạn độ dài của chúng có thể khác nhau.

SQL có ba nhóm kiểu chuỗi cần phân biệt:

1. **Chuỗi độ dài cố định**: điển hình là `CHAR(n)` hoặc `CHARACTER(n)`.
2. **Chuỗi độ dài biến đổi**: điển hình là `VARCHAR(n)` hoặc `CHARACTER VARYING(n)`.
3. **Văn bản dài**: có thể dùng `TEXT`, `CLOB` hoặc kiểu tương đương tùy hệ quản trị cơ sở dữ liệu (DBMS).

Việc chọn đúng kiểu dữ liệu giúp thể hiện ý nghĩa của cột, kiểm soát giới hạn đầu vào và tránh những lỗi khó thấy liên quan đến dấu cách, Unicode, so sánh chuỗi hay hiệu năng. Bài học sẽ giải thích nguyên lý chung, sau đó dùng **PostgreSQL** làm môi trường thực hành cụ thể. Các khác biệt quan trọng ở MySQL, SQL Server, Oracle và SQLite được nêu riêng vì các DBMS không có ngữ nghĩa hoàn toàn giống nhau.

## 1. Khái niệm nền tảng: “độ dài” của một chuỗi là gì?

Trước khi chọn kiểu dữ liệu, cần phân biệt ít nhất ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Số ký tự** | Số đơn vị ký tự mà DBMS tính theo quy tắc của kiểu/hàm | `'SQL'` có 3 ký tự |
| **Số byte** | Dung lượng biểu diễn chuỗi theo bảng mã (encoding) | `'SQL'` chiếm 3 byte trong UTF-8 |
| **Số ký tự nhìn thấy** | Số cụm ký tự người dùng nhận ra trên màn hình | Một ký tự có dấu có thể được tạo từ nhiều mã Unicode |

Trong UTF-8, ký tự ASCII như `A` thường chiếm 1 byte; nhiều ký tự tiếng Việt có dấu chiếm 2–3 byte; một emoji có thể chiếm 4 byte hoặc là tổ hợp nhiều mã Unicode. Vì vậy, **5 ký tự không nhất thiết là 5 byte**.

Chẳng hạn với một cơ sở dữ liệu PostgreSQL sử dụng UTF-8:

```sql
SELECT
    CHAR_LENGTH('SQL') AS sql_characters,
    OCTET_LENGTH('SQL') AS sql_bytes,
    CHAR_LENGTH('á') AS accent_characters,
    OCTET_LENGTH('á') AS accent_bytes;
```

Kết quả mong đợi là `3, 3, 1, 2`. Trong PostgreSQL, `CHAR_LENGTH` (hoặc `LENGTH` với kiểu chuỗi) đếm ký tự, còn `OCTET_LENGTH` đếm byte. Bạn có thể xem encoding cơ sở dữ liệu bằng:

```sql
SHOW server_encoding;
```

**Lưu ý về Unicode:** “một ký tự” theo hàm SQL không luôn tương đương “một chữ nhìn thấy” theo người dùng. Ví dụ, chữ `á` có thể được lưu dưới dạng một mã Unicode dựng sẵn hoặc tổ hợp `a` với dấu sắc kết hợp; các chuỗi trông giống nhau có thể có số mã Unicode khác nhau nếu chưa được chuẩn hóa.

## 2. `CHAR(n)` — chuỗi độ dài cố định

`CHAR(n)` (tên chuẩn khác: `CHARACTER(n)`) khai báo một kiểu chuỗi có độ dài danh nghĩa là `n` ký tự theo ngữ nghĩa của DBMS. Với các hệ quản trị quan hệ quen thuộc, giá trị ngắn hơn độ dài khai báo thường được **đệm thêm dấu cách bên phải** (*right-padding*).

Ví dụ tư duy với một cột `CHAR(5)`:

```text
Giá trị đưa vào:      'AB'
Độ dài khai báo:      CHAR(5)
Biểu diễn có đệm:     'AB   '
                         ^^^ ba dấu cách bổ sung
```

Điều này **không có nghĩa là chương trình luôn nhìn thấy năm ký tự hữu ích**, hay DBMS nhất thiết dành đúng năm byte vật lý trên đĩa. Cách trả về, so sánh, cắt dấu cách và lưu trữ phụ thuộc hệ quản trị.

### 2.1. Ví dụ với PostgreSQL

```sql
SELECT
    'AB'::CHAR(5) AS fixed_value,
    CHAR_LENGTH('AB'::CHAR(5)) AS logical_characters,
    OCTET_LENGTH('AB'::CHAR(5)) AS padded_bytes,
    CHAR_LENGTH('AB'::VARCHAR(5)) AS varying_characters,
    OCTET_LENGTH('AB'::VARCHAR(5)) AS varying_bytes;
```

Trong PostgreSQL với UTF-8, các cột độ dài tương ứng cho kết quả:

| Biểu thức | Kết quả |
|---|---:|
| `CHAR_LENGTH('AB'::CHAR(5))` | 2 |
| `OCTET_LENGTH('AB'::CHAR(5))` | 5 |
| `CHAR_LENGTH('AB'::VARCHAR(5))` | 2 |
| `OCTET_LENGTH('AB'::VARCHAR(5))` | 2 |

PostgreSQL đệm khoảng trắng cho `CHAR(5)`, nhưng hàm đếm ký tự và phép so sánh với kiểu này xử lý dấu cách đệm theo những quy tắc đặc thù. Đây là một ví dụ tốt về lý do không nên suy diễn rằng **mọi hàm độ dài hoặc phép so sánh** sẽ hành xử như nhau trên mọi kiểu chuỗi.

Trong PostgreSQL, so sánh hai giá trị `CHAR(5)` bỏ qua những khoảng trắng đệm cuối:

```sql
SELECT
    ('AB'::CHAR(5) = 'AB   '::CHAR(5)) AS fixed_equal,
    ('AB'::VARCHAR(5) = 'AB   '::VARCHAR(5)) AS varying_equal;
```

Kết quả:

```text
 fixed_equal | varying_equal
-------------+--------------
 true        | false
```

Ở đây `VARCHAR(5)` giữ lại ba dấu cách cuối như một phần giá trị; trong PostgreSQL, so sánh bình thường của hai giá trị `VARCHAR` phân biệt `'AB'` với `'AB   '`. Khi viết ứng dụng, **không nên dựa vào khoảng trắng đệm như một cách “chuẩn hóa” dữ liệu**. Nếu cần loại bỏ khoảng trắng đầu/cuối, hãy thực hiện chuẩn hóa một cách chủ động theo yêu cầu nghiệp vụ.

### 2.2. Khi nào nên cân nhắc `CHAR(n)`?

Kiểu này có thể phù hợp với **giá trị theo định dạng thực sự cố định**, ví dụ mã quốc gia gồm hai ký tự, mã cờ một ký tự hoặc mã nghiệp vụ có định dạng cố định mà hệ thống đã quy định rõ.

Tuy nhiên, `CHAR(2)` **không tự bảo đảm giá trị phải chứa đúng hai ký tự có ý nghĩa**: chuỗi `'V'` vẫn có thể được nhận và đệm thành độ dài hai. Nếu nghiệp vụ yêu cầu đúng hai ký tự, cần ràng buộc tương ứng, chẳng hạn với PostgreSQL:

```sql
CREATE TABLE country_codes (
    code CHAR(2) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    CONSTRAINT code_exactly_two_chars
        CHECK (CHAR_LENGTH(BTRIM(code)) = 2)
);
```

Ở đây `BTRIM` loại bỏ khoảng trắng đầu/cuối để ràng buộc độ dài không nhầm khoảng trắng đệm là ký tự nội dung. Nếu mã phải thuộc tập hai chữ cái Latinh viết hoa, còn cần kiểm tra định dạng hoặc tham chiếu bảng mã được phép. Trên thực tế, **`VARCHAR(2)` kết hợp `CHECK`** cũng là lựa chọn hợp lý và thường tránh được những bất ngờ do padding.

Đừng mặc định chọn `CHAR(n)` cho số điện thoại, mã bưu chính hoặc mã định danh chỉ vì *trông có vẻ* cố định. Độ dài và dấu `+`, số 0 ở đầu, tiền tố quốc gia hoặc định dạng tương lai có thể thay đổi; những dữ liệu đó vẫn là **chuỗi**, nhưng nhiều khi phù hợp với `VARCHAR` hơn.

## 3. `VARCHAR(n)` — chuỗi độ dài biến đổi

`VARCHAR(n)` (tên đầy đủ: `CHARACTER VARYING(n)`) lưu chuỗi có độ dài **tối đa** theo giới hạn `n`, thay vì đệm về cùng độ dài danh nghĩa.

Ví dụ:

```text
VARCHAR(20)
   'An'                 ← 2 ký tự
   'Nguyễn Văn An'      ← nhiều ký tự hơn
   'sql-starter'        ← một giá trị khác
```

Các giá trị không bị đệm thêm dấu cách chỉ vì cột khai báo `VARCHAR(20)`. Khi giá trị vượt giới hạn, DBMS thường báo lỗi trong thao tác ghi thông thường; tuy nhiên vẫn có những trường hợp ngoại lệ tùy DBMS và cách chuyển kiểu. **Không nên dựa vào việc DBMS tự cắt ngắn mà không báo**.

Ví dụ PostgreSQL:

```sql
CREATE TABLE users_demo (
    user_id INTEGER PRIMARY KEY,
    username VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
);

INSERT INTO users_demo (user_id, username, display_name)
VALUES (1, 'an01', 'Nguyễn Văn An');

SELECT
    username,
    CHAR_LENGTH(username) AS username_length,
    display_name
FROM users_demo;
```

Lệnh trên tạo một người dùng có `username` dài 4 ký tự. Một `username` dài hơn 20 ký tự thông thường bị từ chối khi nạp vào cột `VARCHAR(20)` của PostgreSQL.

### 3.1. `VARCHAR(n)` chỉ kiểm tra độ dài, không kiểm tra định dạng

Ví dụ, `VARCHAR(255)` cho cột email **không bảo đảm** đây là email hợp lệ. `VARCHAR(2)` cho mã quốc gia **không tự bảo đảm** giá trị có đúng hai ký tự. Một giá trị toàn khoảng trắng có thể vẫn vượt qua `NOT NULL`.

Cần kết hợp quy tắc miền dữ liệu (*domain rules*) phù hợp:

```sql
CREATE TABLE categories_demo (
    category_id INTEGER PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL,
    CONSTRAINT nonblank_category_name
        CHECK (CHAR_LENGTH(BTRIM(category_name)) > 0)
);
```

Trong ví dụ này, `NOT NULL` ngăn giá trị `NULL`, còn `CHECK` ngăn tên rỗng hoặc chỉ có dấu cách. Kiểm tra định dạng email, số điện thoại hay mã định danh còn cần quy tắc nghiệp vụ ở ứng dụng và/hoặc cơ sở dữ liệu; không nên coi một biểu thức chính quy đơn giản là đủ để xác minh mọi email thật.

### 3.2. Có bắt buộc luôn đặt `VARCHAR(255)`?

Không. Con số `255` là một thói quen thường gặp trong nhiều dự án, không phải giới hạn SQL bắt buộc cho mọi chuỗi. Chọn `n` dựa trên **độ dài tối đa có ý nghĩa trong nghiệp vụ**. Nếu một loại mã được định nghĩa tối đa 24 ký tự thì `VARCHAR(24)` mô tả quy tắc tốt hơn `VARCHAR(255)`. Nếu văn bản không có giới hạn nghiệp vụ rõ ràng, không nhất thiết tự đặt một giới hạn tùy ý.

Trong PostgreSQL, `VARCHAR` **không có đối số độ dài** cũng được chấp nhận và lưu chuỗi với độ dài biến đổi không đặt giới hạn `n` cụ thể (vẫn chịu giới hạn kỹ thuật của hệ thống). Kiểu `TEXT` thường là lựa chọn trực tiếp và dễ đọc hơn nếu bạn muốn biểu đạt “văn bản không giới hạn nghiệp vụ”.

## 4. `TEXT` và `CLOB` — văn bản dài

Các cột như nội dung bài viết, mô tả chi tiết, ghi chú dài, phản hồi khảo sát hoặc nội dung bình luận có thể vượt quá độ dài phù hợp với một `VARCHAR(n)` thông thường.

Tùy DBMS, người ta dùng:

- **`TEXT`**: kiểu văn bản có độ dài biến đổi, được hỗ trợ trực tiếp trong PostgreSQL, MySQL, SQLite và một số hệ khác, nhưng **giới hạn và hành vi không đồng nhất**.
- **`CLOB`** (*Character Large Object*): kiểu đối tượng lớn dạng ký tự, có trong tiêu chuẩn SQL và các DBMS như Oracle. Có thể cần API hoặc cơ chế đọc/ghi khác so với chuỗi ngắn, tùy sản phẩm.
- **`VARCHAR(MAX)` hoặc `NVARCHAR(MAX)`**: cách biểu diễn chuỗi dài hiện đại trong SQL Server.

**Không nên xem `TEXT` là một kiểu dữ liệu chuẩn có cùng dung lượng, cú pháp và tính năng trên tất cả DBMS.** Ví dụ, PostgreSQL có kiểu `TEXT` tiện dụng, còn SQL Server có kiểu `text` cũ đã không còn được khuyến nghị cho phát triển mới.

Trong PostgreSQL:

```sql
CREATE TABLE articles_demo (
    article_id INTEGER PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL
);

INSERT INTO articles_demo (article_id, title, body)
VALUES (
    1,
    'Học các kiểu chuỗi trong SQL',
    'Phần thứ nhất: CHAR và khoảng trắng.'
      || E'\n'
      || 'Phần thứ hai: VARCHAR và giới hạn độ dài.'
      || E'\n'
      || 'Phần thứ ba: TEXT cho nội dung dài.'
);

SELECT article_id, title, CHAR_LENGTH(body) AS body_length
FROM articles_demo;
```

`TEXT` không buộc bạn khai báo một độ dài `n`, nhưng **không phải vô hạn tuyệt đối**. Giới hạn dung lượng, cách lưu giá trị lớn, chi phí truy vấn và số byte có thể lưu chịu ràng buộc kỹ thuật của DBMS.

### 4.1. Có cần lưu mọi chuỗi vào `TEXT` không?

Không nhất thiết. Một cột `username` nên thể hiện giới hạn độ dài và quy tắc hợp lệ của tên đăng nhập. Một cột `body` chứa bài viết dài phù hợp hơn với kiểu văn bản dài.

Ngược lại, cũng không nên dùng `VARCHAR(10000)` chỉ vì ngại dùng `TEXT` mà chưa xác định giới hạn thực tế. **Ý nghĩa nghiệp vụ** là tiêu chí đầu tiên; cách vận hành, lập chỉ mục và giới hạn cụ thể của DBMS là tiêu chí tiếp theo.

### 4.2. `TEXT` có bị cấm lập chỉ mục hay tìm kiếm không?

Không có quy tắc chung như vậy. Trong PostgreSQL, bạn có thể lập chỉ mục B-tree cho nhiều cột `TEXT`, nhưng một giá trị quá lớn có thể vượt giới hạn kích thước mục chỉ mục và làm cách đó không phù hợp. Truy vấn `LIKE '%từ_khóa%'` trên văn bản dài cũng không tự trở nên nhanh nhờ một chỉ mục B-tree thông thường.

Khi cần tìm kiếm nội dung bài viết quy mô lớn, nên khảo sát **full-text search**, chỉ mục phù hợp hoặc hệ thống tìm kiếm chuyên dụng. Chọn kiểu `TEXT` chỉ giải quyết việc **lưu văn bản**, không tự thiết kế chiến lược tìm kiếm hiệu quả.

## 5. So sánh trực tiếp ba nhóm kiểu

| Tiêu chí | `CHAR(n)` | `VARCHAR(n)` | `TEXT` / `CLOB` hoặc kiểu tương đương |
|---|---|---|---|
| Độ dài khai báo | Danh nghĩa cố định `n` | Tối đa `n` | Thường dùng cho văn bản dài; giới hạn phụ thuộc DBMS |
| Chuỗi ngắn hơn `n` | Thường được đệm dấu cách bên phải | Không đệm theo khai báo | Không có `n` cố định như `CHAR(n)` |
| Trường hợp sử dụng | Mã có định dạng cố định, sau khi cân nhắc padding | Tên, mã, email, tiêu đề có giới hạn nghiệp vụ | Nội dung bài, mô tả dài, tài liệu, ghi chú dài |
| Vấn đề cần chú ý | Dấu cách cuối, so sánh, độ dài logic | Giới hạn tối đa, định dạng đầu vào, byte/ký tự | Giới hạn kích thước, tìm kiếm, API và lập chỉ mục |
| Có tự kiểm tra nội dung đúng mẫu? | Không | Không | Không |
| Có bảo đảm hiệu năng nhanh nhất? | Không | Không | Không |

Một cách chọn nhanh:

```text
Chuỗi cần lưu
     |
     +-- Có độ dài cố định thật sự, quy tắc rõ ràng?
     |       |
     |       +-- Có --> Cân nhắc CHAR(n), hiểu padding;
     |       |          bổ sung CHECK nếu cần đúng định dạng.
     |       |
     |       +-- Không --> Có giới hạn tối đa theo nghiệp vụ?
     |                       |
     |                       +-- Có --> VARCHAR(n)
     |                       |
     |                       +-- Không/ rất dài
     |                                  --> TEXT/CLOB/kiểu dài của DBMS
```

Đây là sơ đồ **gợi ý lựa chọn**, không phải một luật cứng. Ví dụ mã hai chữ cái vẫn có thể chọn `VARCHAR(2)` kết hợp `CHECK` để tránh padding; trên PostgreSQL, `TEXT` cũng phù hợp với chuỗi ngắn không có giới hạn nghiệp vụ, không chỉ với văn bản dài.

## 6. Thực hành kết hợp `CHAR`, `VARCHAR` và `TEXT` trong một bảng

Ví dụ quản lý nội dung bài học đa ngôn ngữ:

```sql
CREATE TABLE learning_articles (
    article_id INTEGER PRIMARY KEY,
    language_code CHAR(2) NOT NULL,
    slug VARCHAR(80) NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    CONSTRAINT unique_language_slug UNIQUE (language_code, slug),
    CONSTRAINT valid_language_code
        CHECK (CHAR_LENGTH(BTRIM(language_code)) = 2),
    CONSTRAINT nonblank_title
        CHECK (CHAR_LENGTH(BTRIM(title)) > 0)
);

INSERT INTO learning_articles
    (article_id, language_code, slug, title, body)
VALUES
    (1, 'vi', 'sql-string-types',
     'Kiểu dữ liệu chuỗi trong SQL',
     'Tìm hiểu CHAR, VARCHAR và TEXT với ví dụ.'),
    (2, 'en', 'sql-string-types',
     'SQL string data types',
     'Learn about CHAR, VARCHAR and TEXT through examples.');

SELECT
    language_code,
    slug,
    title,
    CHAR_LENGTH(body) AS body_characters
FROM learning_articles
ORDER BY article_id;
```

Ở đây:

- `language_code CHAR(2)` biểu diễn mã ngôn ngữ hai ký tự cho ví dụ nhỏ này. Hệ thống hỗ trợ mã ngôn ngữ thực tế như `zh-Hant` hay `en-US` cần một mô hình linh hoạt hơn.
- `slug VARCHAR(80)` có giới hạn phục vụ quy tắc đặt đường dẫn.
- `title VARCHAR(200)` thể hiện giới hạn tiêu đề.
- `body TEXT` cho phép lưu nội dung bài học với độ dài thay đổi nhiều.
- `UNIQUE (language_code, slug)` cho phép cùng một `slug` có bản tiếng Việt và tiếng Anh, nhưng không cho hai bài trùng cả ngôn ngữ lẫn `slug`.

Nếu thử nhập một tiêu đề toàn khoảng trắng, ràng buộc `nonblank_title` sẽ chặn. Nếu thêm lại đúng cặp `('vi', 'sql-string-types')`, ràng buộc `unique_language_slug` sẽ chặn. Kiểu dữ liệu và ràng buộc phối hợp để giữ đúng cấu trúc và quy tắc.

### 6.1. Quan sát khác biệt với dữ liệu có dấu cách

Thử riêng trong PostgreSQL:

```sql
SELECT
    'M'::CHAR(4) AS fixed_value,
    'M'::VARCHAR(4) AS varying_value,
    OCTET_LENGTH('M'::CHAR(4)) AS fixed_bytes,
    OCTET_LENGTH('M'::VARCHAR(4)) AS varying_bytes;
```

Với ký tự `M` trong UTF-8, `fixed_bytes` là `4` và `varying_bytes` là `1`. Đừng diễn giải kết quả này thành quy tắc “`CHAR` luôn chậm hơn” hoặc “`VARCHAR` luôn chiếm ít bộ nhớ nhất”: hệ thống có cách quản lý metadata, hàng, nén và lưu trữ riêng. Điều được minh họa trực tiếp là **padding của `CHAR(n)` có thể ảnh hưởng đến độ dài byte của giá trị**.

### 6.2. Thử một giới hạn độ dài

Để hiểu giới hạn của `VARCHAR(80)`, thử chèn một giá trị có hơn 80 ký tự không phải dấu cách vào `slug`. PostgreSQL sẽ báo lỗi độ dài trong trường hợp ghi thông thường. Bạn có thể chạy ví dụ trong một giao dịch và hủy sau khi thử:

```sql
BEGIN;

INSERT INTO learning_articles
    (article_id, language_code, slug, title, body)
VALUES
    (3, 'vi', REPEAT('x', 81), 'Ví dụ quá dài', 'Nội dung');

ROLLBACK;
```

**Lưu ý:** trong PostgreSQL, khi một câu lệnh trong giao dịch bị lỗi, giao dịch thường chuyển sang trạng thái đã thất bại; `ROLLBACK` giải phóng trạng thái đó. Nếu thao tác qua giao diện hoặc chương trình khác, cần chú ý chế độ autocommit và xử lý lỗi theo công cụ đang dùng. Đừng chạy ví dụ gây lỗi trên bảng dữ liệu thật.

## 7. Khác biệt giữa các hệ quản trị cơ sở dữ liệu

SQL có chuẩn chung, nhưng cách hiểu `n`, tập kiểu chuỗi và khả năng lưu nội dung dài thay đổi theo hệ quản trị:

| DBMS | Chuỗi cố định / biến đổi | Văn bản dài | Điểm cần ghi nhớ |
|---|---|---|---|
| **PostgreSQL** | `CHAR(n)`, `VARCHAR(n)`, `VARCHAR` không giới hạn `n` | `TEXT` | `TEXT` và `VARCHAR` (không giới hạn) có cơ chế lưu trữ tương tự; `CHAR(n)` có padding và xử lý dấu cách cuối đặc thù |
| **MySQL** | `CHAR(M)`, `VARCHAR(M)` | `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | Giới hạn `VARCHAR(M)` theo ký tự nhưng còn chịu ràng buộc byte/row; họ `TEXT` có nhiều mức dung lượng và quy tắc index riêng |
| **SQL Server** | `CHAR(n)`, `VARCHAR(n)`; `NCHAR(n)`, `NVARCHAR(n)` | `VARCHAR(MAX)`, `NVARCHAR(MAX)` | `n` của `VARCHAR` liên quan byte, `n` của `NVARCHAR` liên quan đơn vị 2 byte; kiểu `text`/`ntext` cũ không nên dùng cho thiết kế mới |
| **Oracle Database** | `CHAR(n)`, `VARCHAR2(n)` với ngữ nghĩa độ dài BYTE/CHAR tùy khai báo/cấu hình | `CLOB`, `NCLOB` | Cần phân biệt giới hạn byte và ký tự; `VARCHAR2` được dùng thay vì dựa vào `VARCHAR` như một kiểu riêng |
| **SQLite** | Khai báo `CHAR(n)`, `VARCHAR(n)` có thể được chấp nhận | `TEXT` | SQLite dùng hệ thống kiểu linh hoạt; khai báo `VARCHAR(20)` không tự thực thi giới hạn 20 ký tự như PostgreSQL |

Điểm quan trọng là **không sao chép kết luận của PostgreSQL sang DBMS khác mà chưa kiểm tra tài liệu và cấu hình**.

### 7.1. “`VARCHAR(10)`” không phải lúc nào cũng là “10 ký tự Unicode”

- Trong PostgreSQL, giới hạn `VARCHAR(10)` được tính theo số ký tự theo cách DBMS định nghĩa, không phải đơn giản 10 byte UTF-8.
- Trong MySQL, `VARCHAR(M)` dùng độ dài tối đa theo ký tự, nhưng dung lượng byte, kiểu charset và giới hạn kích thước hàng vẫn quyết định khả năng lưu.
- Trong SQL Server, `VARCHAR(n)` dùng `n` theo **byte**, còn `NVARCHAR(n)` dùng `n` theo **đơn vị 2 byte**. Một ký tự Unicode bổ sung có thể cần hai đơn vị UTF-16, nên `NVARCHAR(10)` không luôn chứa được 10 ký tự người dùng nhìn thấy.
- Trong Oracle, `VARCHAR2(10 BYTE)` và `VARCHAR2(10 CHAR)` có ngữ nghĩa giới hạn khác nhau.
- Trong SQLite, `VARCHAR(10)` thường chỉ là khai báo kiểu/affinity; muốn giới hạn 10 ký tự cần ràng buộc như `CHECK (length(value) <= 10)` và cân nhắc cách đếm Unicode.

Vì vậy, cùng một thiết kế về mặt tên kiểu chưa chắc có thể chuyển nguyên vẹn giữa các hệ thống.

### 7.2. Unicode và các kiểu có tiền tố `N`

Các kiểu `NCHAR`, `NVARCHAR` hoặc `NVARCHAR2` (tùy DBMS) thường liên quan đến cơ chế biểu diễn bộ ký tự quốc gia/Unicode của sản phẩm. Tuy nhiên, **không có quy tắc chung rằng `VARCHAR` luôn không lưu được tiếng Việt**.

Ví dụ, PostgreSQL với database UTF-8 dùng `VARCHAR` và `TEXT` để lưu trực tiếp tiếng Việt. Trong SQL Server, cần hiểu sự khác nhau giữa `VARCHAR` theo collation/encoding và `NVARCHAR` theo Unicode, cùng cú pháp chuỗi ký tự của SQL Server. Khi thiết kế ứng dụng đa ngôn ngữ, phải xem **encoding của cơ sở dữ liệu, kiểu cột, collation và cách driver truyền chuỗi**.

## 8. Dấu cách, so sánh chuỗi và sắp xếp

Chọn kiểu chuỗi ảnh hưởng không chỉ dung lượng mà còn các phép so sánh.

### 8.1. Dấu cách cuối

`CHAR(n)` thường có cơ chế padding; các hệ quản trị có quy tắc khác nhau khi so sánh, trả về hoặc cắt dấu cách cuối. Với PostgreSQL, dấu cách đệm cuối trong phép so sánh `CHAR` được xem là không có ý nghĩa; trong `VARCHAR`/`TEXT`, dấu cách cuối là một phần dữ liệu theo phép so sánh thông thường.

Ví dụ:

```sql
SELECT
    ('code'::CHAR(8) = 'code    '::CHAR(8)) AS char_equal,
    ('code'::TEXT = 'code    '::TEXT) AS text_equal;
```

Kết quả là `true` và `false` trong PostgreSQL. **Không dùng `CHAR` như một cách tự động xử lý dữ liệu người dùng có khoảng trắng thừa**; thay vào đó, quyết định rõ có muốn `TRIM`/`BTRIM` giá trị khi nhập hay không.

### 8.2. Collation, chữ hoa/chữ thường và dấu tiếng Việt

Khác biệt giữa `'a'` và `'A'`, thứ tự `'á'` so với `'a'`, hay việc chuỗi có dấu được coi là tương đương trong tìm kiếm **không thể quyết định chỉ bằng `CHAR`, `VARCHAR` hay `TEXT`**. Các hành vi này còn phụ thuộc **collation** (quy tắc so sánh và sắp xếp), DBMS và toán tử truy vấn.

Ví dụ, `ORDER BY title` sắp xếp theo quy tắc collation áp dụng cho biểu thức/cột. Một truy vấn cần tìm kiếm không phân biệt chữ hoa, chữ thường hoặc dấu phải chọn cách xử lý phù hợp với DBMS và yêu cầu người dùng. Tránh giả định rằng `LOWER(...)` hay `LIKE` tự giải quyết mọi vấn đề Unicode.

### 8.3. `NULL` khác chuỗi rỗng

Trong nhiều DBMS, `NULL` biểu thị không có giá trị; `''` là một chuỗi dài 0 ký tự; `' '` là chuỗi chứa một dấu cách. Ví dụ PostgreSQL:

```sql
SELECT
    CHAR_LENGTH(''::TEXT) AS empty_length,
    CHAR_LENGTH(' '::TEXT) AS space_length,
    (NULL::TEXT IS NULL) AS missing_value;
```

Kết quả tương ứng `0`, `1`, `true`. Với **Oracle**, chuỗi rỗng của kiểu ký tự hiện được xử lý như `NULL` trong nhiều tình huống, nên không thể chuyển nguyên nhận định của PostgreSQL sang Oracle.

Nếu cột `NOT NULL` nhưng muốn cấm cả chuỗi rỗng và chuỗi chỉ toàn dấu cách, cần thêm điều kiện miền dữ liệu phù hợp, chẳng hạn `CHECK (CHAR_LENGTH(BTRIM(title)) > 0)` trong PostgreSQL.

## 9. Lưu trữ và hiệu năng: các ngộ nhận thường gặp

**“`CHAR` luôn nhanh hơn `VARCHAR` vì chiều dài cố định.”** Không có kết luận phổ quát. Việc tìm kiếm, đọc và ghi còn phụ thuộc thiết kế hàng, chỉ mục, collation, bộ nhớ đệm, khối lượng dữ liệu và kế hoạch thực thi. Trong PostgreSQL, `CHAR(n)` có thể tăng chi phí lưu trữ do padding và không có ưu thế hiệu năng mặc định so với `VARCHAR`/`TEXT`.

**“`VARCHAR(255)` luôn cấp phát sẵn 255 byte.”** Không đúng như một quy tắc chung. `VARCHAR` được thiết kế để lưu chuỗi biến đổi; cấu trúc metadata và cách lưu có thể khác nhau giữa các DBMS. Hơn nữa, số byte có thể khác số ký tự.

**“`TEXT` luôn nằm ngoài bảng và không thể tạo index.”** Không đúng cho mọi DBMS và không đúng như một quy tắc đơn giản với PostgreSQL. Giá trị lớn có thể được DBMS lưu theo cơ chế đặc biệt; giới hạn khóa chỉ mục, chi phí `LIKE` hay full-text search cần đánh giá theo từng hệ.

**“Chọn kiểu chuỗi là đủ để dữ liệu đúng.”** Kiểu dữ liệu chỉ là một lớp. `VARCHAR(100)` không tự xác nhận chuỗi là email, tên người hay mã sản phẩm hợp lệ. Cần kết hợp ràng buộc, kiểm tra đầu vào và quy tắc nghiệp vụ.

**“Văn bản dài không cần nghĩ đến dung lượng.”** Văn bản dài vẫn tốn chỗ, băng thông, bộ nhớ, thời gian đọc và sao lưu. Nếu một API chỉ cần danh sách tiêu đề, không nên truy vấn toàn bộ nội dung bài viết `body` rồi trả về ứng dụng. Hãy chọn các cột cần thiết:

```sql
SELECT article_id, title
FROM learning_articles
ORDER BY article_id;
```

Khi cần tìm kiếm nhiều trong `body`, hãy thiết kế chỉ mục hoặc chiến lược tìm kiếm cho loại truy vấn đó. Nếu cần lưu tệp nhị phân như hình ảnh, PDF hoặc video, cần xem các kiểu nhị phân và lưu trữ đối tượng tương ứng; **`TEXT` không phải kiểu dữ liệu phù hợp cho byte nhị phân tùy ý**.

## 10. Gợi ý chọn kiểu dữ liệu theo tình huống thực tế

| Trường dữ liệu | Hướng chọn thường gặp | Lý do và lưu ý |
|---|---|---|
| Mã cờ `A`/`I` | `CHAR(1)` hoặc `VARCHAR(1)` với `CHECK` | Miền giá trị nhỏ, kiểm tra tập giá trị hợp lệ |
| Mã quốc gia hai chữ cái | `CHAR(2)` hoặc `VARCHAR(2)` kết hợp ràng buộc | Cần xác nhận định dạng và hiểu padding |
| Tên đăng nhập | `VARCHAR(n)` | Giới hạn nghiệp vụ, thường có `UNIQUE` và kiểm tra định dạng |
| Email | `VARCHAR(n)` | Giới hạn có chủ đích; cần quy tắc chuẩn hóa và xác thực riêng |
| Số điện thoại | `VARCHAR(n)` | Có dấu `+`, số 0 đầu và nhiều định dạng; không dùng kiểu số để lưu |
| Mã bưu chính | `VARCHAR(n)` | Có thể có chữ cái, dấu cách và số 0 đầu |
| Tiêu đề bài viết | `VARCHAR(n)` hoặc `TEXT` | Chọn theo giới hạn tối đa thực tế của sản phẩm |
| Mô tả sản phẩm dài | `TEXT` hoặc kiểu chuỗi dài phù hợp DBMS | Không có giới hạn ngắn rõ ràng |
| Nội dung bài báo, tài liệu | `TEXT` / `CLOB` / `NVARCHAR(MAX)` tùy DBMS | Cần đánh giá khả năng tìm kiếm, kích thước và cách lấy dữ liệu |
| Nội dung log hoặc JSON | Xem xét kiểu chuyên dụng trước | PostgreSQL có `JSONB` cho dữ liệu JSON cần truy vấn theo cấu trúc; log cũng có thể cần hệ thống lưu trữ riêng |

Một chuỗi *trông cố định* chưa chắc có độ dài cố định cho mọi thị trường. Chẳng hạn mã điện thoại quốc tế, địa chỉ và họ tên có thể dài hơn dữ liệu thử nghiệm ban đầu; giới hạn độ dài cần dựa trên yêu cầu sản phẩm thay vì vài mẫu ngẫu nhiên.

## 11. Kiểm tra kiến thức và bài tập thực hành

### Bài 1 — Đọc kiểu dữ liệu

Giả sử bảng có cấu trúc:

```sql
CREATE TABLE notes_demo (
    note_id INTEGER PRIMARY KEY,
    locale_code CHAR(2),
    short_title VARCHAR(60),
    note_body TEXT
);
```

Hãy giải thích vì sao `locale_code` có kiểu cố định, `short_title` có giới hạn, còn `note_body` dùng `TEXT`. Nếu cần hỗ trợ mã như `en-US`, bạn sẽ sửa kiểu `locale_code` như thế nào? Mã ngôn ngữ mở rộng có thể dài hơn hai ký tự, do đó cần xem lại giới hạn và quy tắc lưu mã.

### Bài 2 — Đo byte và ký tự

Trên PostgreSQL UTF-8, dự đoán kết quả:

```sql
SELECT
    CHAR_LENGTH('á') AS a_char,
    OCTET_LENGTH('á') AS a_bytes,
    CHAR_LENGTH('AB'::CHAR(5)) AS fixed_chars,
    OCTET_LENGTH('AB'::CHAR(5)) AS fixed_bytes;
```

**Đáp án kỳ vọng:** `a_char = 1`, `a_bytes = 2`, `fixed_chars = 2`, `fixed_bytes = 5`. Kết quả cho thấy độ dài ký tự, số byte UTF-8 và khoảng trắng đệm là ba khía cạnh cần phân biệt.

### Bài 3 — Phân biệt ràng buộc độ dài và định dạng

Một cột khai báo `country_code VARCHAR(2) NOT NULL` có nhất thiết ngăn được chuỗi `'X'` không? **Không**: chuỗi một ký tự vẫn nằm trong giới hạn. Với PostgreSQL, có thể thêm:

```sql
CHECK (CHAR_LENGTH(BTRIM(country_code)) = 2)
```

Nếu cần kiểm tra chính xác mã quốc gia được công nhận, tốt hơn nữa là tham chiếu đến bảng danh mục mã hợp lệ hoặc áp dụng quy tắc nghiệp vụ rõ ràng.

### Bài 4 — Chọn kiểu chuỗi

Bạn thiết kế bảng gồm `status_flag` chỉ nhận `Y` hoặc `N`, `display_name` tối đa 120 ký tự và `article_body` dài tùy nội dung. Hãy chọn kiểu và ràng buộc phù hợp. Một đáp án PostgreSQL có thể là:

```sql
CREATE TABLE submissions_demo (
    submission_id INTEGER PRIMARY KEY,
    status_flag CHAR(1) NOT NULL
        CHECK (status_flag IN ('Y', 'N')),
    display_name VARCHAR(120) NOT NULL
        CHECK (CHAR_LENGTH(BTRIM(display_name)) > 0),
    article_body TEXT NOT NULL
);
```

Sau khi tạo, thử các giá trị hợp lệ và không hợp lệ trong một cơ sở dữ liệu thực hành riêng để quan sát lỗi `CHECK` và `NOT NULL`.

### Bài 5 — Khi chuyển DBMS

Một dự án chuyển từ PostgreSQL sang SQL Server và đang dùng `TEXT` cho bài viết. Có nên giữ nguyên định nghĩa `TEXT`? **Không nên suy ra tính tương đương từ tên kiểu**. Cần khảo sát `VARCHAR(MAX)`/`NVARCHAR(MAX)`, yêu cầu Unicode, kiểu dữ liệu của ứng dụng và cách truy cập nội dung dài.

## Kết luận

`CHAR(n)` mô tả chuỗi có độ dài danh nghĩa cố định và thường có **đệm dấu cách**; `VARCHAR(n)` mô tả chuỗi có độ dài biến đổi với **giới hạn tối đa**; `TEXT`, `CLOB` hoặc các kiểu chuỗi lớn tương ứng phục vụ **văn bản dài**. Chúng có mục đích khác nhau, và lựa chọn phải xét cả ý nghĩa cột, ràng buộc nghiệp vụ, Unicode, collation, cách so sánh và giới hạn của DBMS.

Trong thực hành, hãy bắt đầu bằng câu hỏi: *“Giá trị này có thực sự cố định không, có giới hạn nghiệp vụ rõ ràng không, và có thể dài đến mức nào?”* Sau đó chọn kiểu phù hợp và bổ sung `NOT NULL`, `CHECK`, `UNIQUE` khi cần. Nắm được sự khác biệt giữa **ký tự và byte**, giữa **dấu cách đệm và dấu cách thật**, và giữa **giới hạn kiểu dữ liệu với kiểm tra nghiệp vụ** sẽ giúp thiết kế bảng SQL rõ ràng, an toàn và dễ bảo trì hơn.
