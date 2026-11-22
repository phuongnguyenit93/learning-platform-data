# So sánh an toàn với NULL và tính khả chuyển trong SQL

## 1. Vì sao so sánh với NULL cần một cách tư duy riêng?

Trong SQL, `NULL` biểu thị **giá trị chưa biết, không có hoặc chưa được cung cấp**, tùy ngữ nghĩa của cột. Nó không phải số `0`, chuỗi rỗng `''`, chuỗi `'NULL'` hay một giá trị đặc biệt có thể đem so sánh bằng dấu `=` như dữ liệu thông thường.

Xét yêu cầu: “Tìm những khách hàng có email chính và email dự phòng giống nhau, kể cả khi cả hai đều chưa có email”. Nếu viết:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email = backup_email;
~~~

thì hai cột cùng `NULL` **không làm cho biểu thức bằng nhau trở thành `TRUE`**. Theo logic SQL thông thường, `NULL = NULL` cho kết quả `UNKNOWN`. Vì mệnh đề `WHERE` chỉ giữ hàng mà điều kiện là `TRUE`, hàng có hai email cùng `NULL` sẽ bị loại.

Bài học này tập trung vào việc chọn đúng cách so sánh khi dữ liệu có thể thiếu và viết truy vấn có thể chuyển giữa các hệ quản trị cơ sở dữ liệu (DBMS). Các câu hỏi then chốt là:

1. Có cần tìm **giá trị thiếu** (`IS NULL`) hay cần **so sánh hai giá trị có thể thiếu** (null-safe equality)?
2. Hai giá trị cùng `NULL` có được nghiệp vụ xem là “tương đương” không?
3. Biểu thức cần trả về **`TRUE`/`FALSE` rõ ràng**, hay chỉ cần hoạt động đúng trong `WHERE` / `JOIN ON`?
4. Câu lệnh cần chạy trên hệ SQL nào, và tính năng so sánh đó có được hỗ trợ ở phiên bản đang dùng không?

## 2. Bảng ví dụ

Các ví dụ chính sử dụng cú pháp SQL tiêu chuẩn được PostgreSQL hỗ trợ. Nếu chạy trên DBMS khác, có thể cần đổi cách khai báo kiểu dữ liệu hoặc literal ngày, nhưng ý tưởng so sánh vẫn giữ nguyên.

~~~sql
CREATE TABLE contacts (
    contact_id       INTEGER PRIMARY KEY,
    primary_email    VARCHAR(100),
    backup_email     VARCHAR(100),
    region_code      VARCHAR(5),
    deactivated_at   DATE
);

INSERT INTO contacts (
    contact_id, primary_email, backup_email, region_code, deactivated_at
)
VALUES
    (1, 'an@example.test',   'an@example.test',   'VN', NULL),
    (2, 'binh@example.test', NULL,                'VN', NULL),
    (3, NULL,                NULL,                'SG', NULL),
    (4, 'chi@example.test',  'oldchi@example.test', NULL, DATE '2026-08-01'),
    (5, NULL,                'ha@example.test',   'VN', NULL),
    (6, 'lan@example.test',  'lan@example.test',   NULL, NULL);
~~~

Hai cột `primary_email` và `backup_email` đều cho phép `NULL`. Bảng này có đủ các trường hợp:

| contact_id | primary_email | backup_email | Quan hệ giá trị |
| ---: | --- | --- | --- |
| 1 | `an@example.test` | `an@example.test` | Cùng một giá trị đã biết |
| 2 | `binh@example.test` | `NULL` | Chỉ một phía thiếu |
| 3 | `NULL` | `NULL` | Cả hai phía thiếu |
| 4 | `chi@example.test` | `oldchi@example.test` | Hai giá trị đã biết khác nhau |
| 5 | `NULL` | `ha@example.test` | Chỉ một phía thiếu |
| 6 | `lan@example.test` | `lan@example.test` | Cùng một giá trị đã biết |

Trong bảng dữ liệu, chữ `NULL` là cách **biểu diễn** một giá trị thiếu, không phải chuỗi ký tự được lưu vào cột.

## 3. Logic ba giá trị: TRUE, FALSE, UNKNOWN

Với các toán tử so sánh thông thường `=`, `<>`, `<`, `>`, `<=` và `>=`, nếu có toán hạng `NULL`, kết quả thường là `UNKNOWN`. SQL sử dụng **logic ba giá trị** (three-valued logic, 3VL) cho biểu thức điều kiện.

| Vế trái | Vế phải | `a = b` | `a <> b` |
| --- | --- | --- | --- |
| `'a'` | `'a'` | TRUE | FALSE |
| `'a'` | `'b'` | FALSE | TRUE |
| `'a'` | `NULL` | UNKNOWN | UNKNOWN |
| `NULL` | `'a'` | UNKNOWN | UNKNOWN |
| `NULL` | `NULL` | UNKNOWN | UNKNOWN |

Hai biểu thức sau **không tìm được hàng có giá trị `NULL`**:

~~~sql
-- Sai nếu mục đích là tìm giá trị thiếu:
SELECT contact_id FROM contacts WHERE primary_email = NULL;

-- Sai nếu mục đích là tìm giá trị đã có:
SELECT contact_id FROM contacts WHERE primary_email <> NULL;
~~~

Trong SQL thông thường, cả hai truy vấn đều không trả về hàng nào: mọi phép so sánh với literal `NULL` ở đây đều là `UNKNOWN`.

Ba giá trị cũng ảnh hưởng đến `AND`, `OR` và `NOT`:

| Biểu thức | Kết quả |
| --- | --- |
| `TRUE AND UNKNOWN` | UNKNOWN |
| `FALSE AND UNKNOWN` | FALSE |
| `TRUE OR UNKNOWN` | TRUE |
| `FALSE OR UNKNOWN` | UNKNOWN |
| `NOT UNKNOWN` | UNKNOWN |

Ví dụ:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email = backup_email
   OR contact_id = 3
ORDER BY contact_id;
~~~

Truy vấn trả `1, 3, 6`. Với hàng 3, phép `primary_email = backup_email` là `UNKNOWN`, nhưng `contact_id = 3` là `TRUE` nên `UNKNOWN OR TRUE` thành `TRUE`. Mệnh đề `WHERE` chỉ chấp nhận `TRUE`; `FALSE` và `UNKNOWN` đều không được chọn.

**Phân biệt quan trọng:** một điều kiện có thể hoạt động đúng như bộ lọc mặc dù giá trị logic của nó đôi khi là `UNKNOWN`. Khi cần xuất một cột flag đúng nghĩa hai giá trị, hoặc đem kết quả sang nơi yêu cầu boolean xác định, cần xử lý rõ trường hợp `NULL`.

## 4. Kiểm tra một giá trị có NULL: IS NULL và IS NOT NULL

Khi muốn biết một cột **đang thiếu giá trị hay không**, dùng toán tử `IS NULL` / `IS NOT NULL`:

~~~sql
-- Các liên hệ chưa có email chính: ID 3 và 5.
SELECT contact_id
FROM contacts
WHERE primary_email IS NULL
ORDER BY contact_id;

-- Các liên hệ đã có email chính: ID 1, 2, 4 và 6.
SELECT contact_id
FROM contacts
WHERE primary_email IS NOT NULL
ORDER BY contact_id;
~~~

`IS NULL` và `IS NOT NULL` trả kết quả xác định (`TRUE` hoặc `FALSE`) cho phép kiểm tra thiếu/không thiếu. Chúng có mặt trong SQL tiêu chuẩn và được hỗ trợ rộng rãi bởi các DBMS phổ biến.

Trong tình huống nghiệp vụ, sự vắng mặt của một ngày thường được dùng để biểu thị trạng thái:

~~~sql
-- Liên hệ chưa có ngày ngừng hoạt động.
SELECT contact_id
FROM contacts
WHERE deactivated_at IS NULL
ORDER BY contact_id;
-- 1, 2, 3, 5, 6
~~~

Tuy nhiên, **`NULL` không tự động có nghĩa “đang hoạt động”**: chỉ diễn giải như vậy khi mô hình dữ liệu và quy tắc nghiệp vụ đã quy định rõ. Ngày ngừng hoạt động có thể chưa được ghi nhận vì lỗi dữ liệu, chứ không chỉ vì đối tượng vẫn hoạt động.

## 5. So sánh bằng nhau an toàn với NULL

### 5.1. So sánh thông thường: chỉ bằng nhau khi cả hai giá trị đã biết

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email = backup_email
ORDER BY contact_id;
-- 1, 6
~~~

Ở hàng 3, cả hai email đều thiếu nên biểu thức so sánh là `UNKNOWN` và hàng này không xuất hiện.

### 5.2. IS NOT DISTINCT FROM: hai NULL được coi là không khác nhau

SQL tiêu chuẩn định nghĩa phép so sánh có xét `NULL`:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email IS NOT DISTINCT FROM backup_email
ORDER BY contact_id;
-- 1, 3, 6
~~~

`a IS NOT DISTINCT FROM b` trả:

- `TRUE` nếu cả hai giá trị đã biết và bằng nhau.
- `TRUE` nếu cả hai đều `NULL`.
- `FALSE` nếu chỉ một phía `NULL`, hoặc hai giá trị đã biết nhưng khác nhau.

Nó là phép **so sánh tương đương có xét `NULL`**, cho ra kết quả hai giá trị (`TRUE` hoặc `FALSE`), không tạo `UNKNOWN` như `=` khi gặp `NULL`.

| a | b | `a = b` | `a IS NOT DISTINCT FROM b` |
| --- | --- | --- | --- |
| `'x'` | `'x'` | TRUE | TRUE |
| `'x'` | `'y'` | FALSE | FALSE |
| `'x'` | `NULL` | UNKNOWN | FALSE |
| `NULL` | `'x'` | UNKNOWN | FALSE |
| `NULL` | `NULL` | UNKNOWN | TRUE |

**Lưu ý về nghĩa:** hai email đều không biết không có nghĩa thực tế chúng cùng một địa chỉ. Phép so sánh này chỉ nói rằng, theo **quy tắc so sánh có xét `NULL` mà người viết chọn**, hai ô đều thiếu được coi là không khác nhau. Không nên áp dụng quy tắc đó nếu nghiệp vụ cần bằng chứng rằng hai email thực sự trùng nhau.

### 5.3. IS DISTINCT FROM: khác nhau an toàn với NULL

Phép đối ngẫu là:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email IS DISTINCT FROM backup_email
ORDER BY contact_id;
-- 2, 4, 5
~~~

`a IS DISTINCT FROM b` trả `TRUE` khi có đúng một phía là `NULL` hoặc hai giá trị đã biết khác nhau; trả `FALSE` khi cả hai là `NULL` hoặc cả hai cùng một giá trị đã biết.

Trái lại, phép `a <> b` chỉ tìm được trường hợp **cả hai không NULL và khác nhau**:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email <> backup_email;
-- 4
~~~

### 5.4. Mẫu viết tương đương để chạy ở nhiều hệ SQL

Không phải DBMS nào cũng hỗ trợ trực tiếp `IS [NOT] DISTINCT FROM` ở mọi phiên bản. Trong ngữ cảnh `WHERE` hoặc `JOIN ON`, có thể diễn đạt điều kiện **chọn cùng các cặp hàng** bằng các toán tử phổ biến:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email = backup_email
   OR (primary_email IS NULL AND backup_email IS NULL)
ORDER BY contact_id;
-- 1, 3, 6
~~~

Hai cột cùng `NULL` làm nhánh thứ hai `TRUE`. Hai cột có giá trị bằng nhau làm nhánh thứ nhất `TRUE`. Nếu chỉ một phía `NULL`, toàn bộ biểu thức có thể là `UNKNOWN`, nhưng `WHERE` vẫn loại hàng đó như mong muốn. Vì vậy đây là phép thay thế **tương đương về kết quả lọc**, chứ không nhất thiết cho ra boolean hai giá trị trong mọi hàng.

Tương tự, để lọc các cặp được coi là khác nhau:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email <> backup_email
   OR (primary_email IS NULL AND backup_email IS NOT NULL)
   OR (primary_email IS NOT NULL AND backup_email IS NULL)
ORDER BY contact_id;
-- 2, 4, 5
~~~

Đây cũng là mẫu điều kiện lọc, có thể trả `UNKNOWN` ở một số tổ hợp nếu dùng như biểu thức trần. Khi cần **cột kết quả hoàn toàn xác định**, sử dụng `CASE`:

~~~sql
SELECT
    contact_id,
    CASE
        WHEN primary_email IS NULL AND backup_email IS NULL THEN 1
        WHEN primary_email IS NULL OR backup_email IS NULL THEN 0
        WHEN primary_email = backup_email THEN 1
        ELSE 0
    END AS emails_equal_null_safe
FROM contacts
ORDER BY contact_id;
~~~

Kết quả:

| contact_id | emails_equal_null_safe |
| ---: | ---: |
| 1 | 1 |
| 2 | 0 |
| 3 | 1 |
| 4 | 0 |
| 5 | 0 |
| 6 | 1 |

Dùng `1`/`0` làm kết quả trong ví dụ để thuận tiện cho những DBMS không cho phép trả trực tiếp kiểu boolean trong danh sách `SELECT`. Nhánh đầu xử lý hai `NULL`, nhánh tiếp theo xử lý một `NULL`, phần còn lại so sánh các giá trị đã biết.

## 6. Chọn cú pháp theo hệ quản trị và phiên bản

Các DBMS đều hỗ trợ `IS NULL` / `IS NOT NULL`, nhưng cách viết **so sánh hai giá trị có thể NULL** không đồng nhất:

| DBMS | Cách thường dùng để so sánh bằng nhau có xét NULL | Ghi chú |
| --- | --- | --- |
| PostgreSQL | `a IS NOT DISTINCT FROM b` | Hỗ trợ cả `IS DISTINCT FROM` |
| MySQL / MariaDB | `a <=> b` | Toán tử null-safe equality đặc thù hệ này; đảo phủ định cho trường hợp “khác nhau” theo yêu cầu |
| SQL Server 2022 trở lên | `a IS NOT DISTINCT FROM b` | Các bản cũ cần mẫu điều kiện `OR ... IS NULL` hoặc `CASE` phù hợp |
| SQLite | `a IS b` hoặc `a IS NOT DISTINCT FROM b` ở phiên bản hỗ trợ | `IS`/`IS NOT` có ngữ nghĩa riêng của SQLite; chú ý khi toán hạng là boolean literal |
| Các hệ hoặc phiên bản khác | Kiểm tra tài liệu của DBMS; dùng mẫu điều kiện phổ biến khi cần | Cú pháp SQL tiêu chuẩn không bảo đảm mọi phiên bản đều đã triển khai |

Ví dụ của MySQL:

~~~sql
-- MySQL/MariaDB:
SELECT contact_id
FROM contacts
WHERE primary_email <=> backup_email;
~~~

Ví dụ của SQLite trong ngữ cảnh so sánh hai cột email:

~~~sql
-- SQLite:
SELECT contact_id
FROM contacts
WHERE primary_email IS backup_email;
~~~

Đừng sao chép nguyên cú pháp `<=>` sang PostgreSQL hoặc SQL Server. Ngược lại, nếu ứng dụng dùng nhiều DBMS, cần xác định dialect ở tầng truy cập dữ liệu và sử dụng cú pháp tương ứng, hoặc chọn một biểu thức điều kiện phổ biến phù hợp với ngữ cảnh.

**Khả chuyển không chỉ là cú pháp.** Kết quả so sánh chuỗi còn phụ thuộc **collation** và kiểu dữ liệu: có hệ phân biệt chữ hoa/thường theo mặc định, có hệ không; cách xử lý ký tự Unicode, dấu tiếng Việt và khoảng trắng cuối chuỗi cũng có thể khác. Chuyển câu lệnh đúng cú pháp chưa chắc giữ nguyên tập kết quả nếu collation thay đổi.

## 7. Các bẫy thường gặp khi NULL xuất hiện trong điều kiện

### 7.1. NOT IN có thể loại tất cả hàng khi tập con chứa NULL

Xét bảng email bị chặn:

~~~sql
CREATE TABLE blocked_emails (
    email VARCHAR(100)
);

INSERT INTO blocked_emails (email)
VALUES ('chi@example.test'), (NULL);
~~~

Câu truy vấn trông có vẻ hợp lý:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email NOT IN (
    SELECT email
    FROM blocked_emails
)
ORDER BY contact_id;
~~~

Với dữ liệu mẫu, câu truy vấn **không trả về hàng nào**. `NOT IN` tương đương về mặt logic với việc yêu cầu giá trị khác tất cả phần tử; một phần tử `NULL` khiến phép so sánh có thể trở thành `UNKNOWN`, và `WHERE` loại hàng đó. Hàng có email bị chặn thật sự thì cũng bị loại.

Để tìm những contact **không trùng email đã biết** với bảng chặn, dùng `NOT EXISTS`:

~~~sql
SELECT c.contact_id
FROM contacts AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_emails AS b
    WHERE b.email = c.primary_email
)
ORDER BY c.contact_id;
-- 1, 2, 3, 5, 6
~~~

`NOT EXISTS` kiểm tra xem có hàng nào thỏa điều kiện tương quan hay không; hàng `b.email = NULL` không tạo phép khớp `TRUE`. Truy vấn này **vẫn giữ** những contact có `primary_email` là `NULL` (ID 3 và 5), bởi không tìm được email trùng trong bảng chặn. Nếu nghiệp vụ chỉ cho phép contact có email đã biết, thêm:

~~~sql
SELECT c.contact_id
FROM contacts AS c
WHERE c.primary_email IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM blocked_emails AS b
      WHERE b.email = c.primary_email
  )
ORDER BY c.contact_id;
-- 1, 2, 6
~~~

Nếu chính sách chặn coi `NULL` là một giá trị cần khớp `NULL`, phải viết điều kiện so sánh có xét `NULL` trong subquery. **Lựa chọn đúng phụ thuộc quy tắc nghiệp vụ, không chỉ ở cú pháp.**

### 7.2. JOIN với khóa NULL

Điều kiện nối thông thường:

~~~sql
SELECT a.contact_id AS left_id, b.contact_id AS right_id
FROM contacts AS a
JOIN contacts AS b
    ON a.region_code = b.region_code
WHERE a.contact_id < b.contact_id
ORDER BY left_id, right_id;
~~~

Các hàng có `region_code = NULL` không khớp với nhau. Với dữ liệu mẫu, hàng 4 và 6 cùng thiếu vùng nhưng không tạo cặp nối bằng điều kiện `=`.

Nếu đề bài **thực sự muốn gom cả hai giá trị vùng chưa biết vào cùng một nhóm khớp**, có thể viết:

~~~sql
-- Hỗ trợ trong PostgreSQL và DBMS có IS NOT DISTINCT FROM:
SELECT a.contact_id AS left_id, b.contact_id AS right_id
FROM contacts AS a
JOIN contacts AS b
    ON a.region_code IS NOT DISTINCT FROM b.region_code
WHERE a.contact_id < b.contact_id
ORDER BY left_id, right_id;
~~~

Mẫu điều kiện `ON` thay thế dùng rộng rãi:

~~~sql
ON a.region_code = b.region_code
   OR (a.region_code IS NULL AND b.region_code IS NULL)
~~~

Cần cân nhắc **đúng ngữ nghĩa**: hai contact chưa xác định vùng không đồng nghĩa với việc chúng cùng vùng. Nếu dùng null-safe join trên cột thiếu dữ liệu, nhiều hàng `NULL` có thể kết hợp thành số lượng cặp rất lớn, gây sai kết quả nghiệp vụ và tăng chi phí truy vấn.

### 7.3. COALESCE không phải phép bằng nhau an toàn mặc định

`COALESCE(x, default_value)` thay `NULL` bằng một giá trị dự phòng, hữu ích cho mục đích hiển thị hoặc tính toán khi có quy tắc rõ ràng. Nhưng việc biến nó thành mẹo so sánh:

~~~sql
-- Dễ sai nếu giá trị dự phòng có thể xuất hiện thật:
WHERE COALESCE(primary_email, 'unknown@example.test')
    = COALESCE(backup_email,  'unknown@example.test')
~~~

có thể nhầm `NULL` với email thực sự bằng `'unknown@example.test'`. Với cột số, chuỗi, ngày/giờ cũng có nguy cơ **đụng giá trị thay thế (sentinel collision)** hoặc phải chuyển kiểu không mong muốn.

Một biểu thức `COALESCE` còn có thể ảnh hưởng đến khả năng tận dụng chỉ mục thông thường nếu biến đổi trực tiếp cột được lọc. Bộ tối ưu có thể tận dụng functional/expression index tùy hệ, nên cần xem kế hoạch thực thi thay vì mặc định rằng cách viết này nhanh.

Nếu cần so sánh có xét `NULL`, ưu tiên `IS NOT DISTINCT FROM` hoặc mẫu điều kiện minh bạch; dùng `COALESCE` khi nghiệp vụ thật sự định nghĩa giá trị mặc định.

### 7.4. NULL với NOT, BETWEEN và phép tính

~~~sql
-- Nếu backup_email là NULL, điều kiện dưới đây là UNKNOWN:
SELECT contact_id
FROM contacts
WHERE NOT (primary_email = backup_email);
-- Chỉ có ID 4, không tự động bao gồm ID 2, 3, 5.
~~~

`NOT UNKNOWN` vẫn là `UNKNOWN`, nên phủ định phép bằng thông thường **không** đồng nghĩa với phép khác nhau an toàn với `NULL`.

Với số học, phép cộng/nhân có một toán hạng `NULL` thường trả `NULL`; với `BETWEEN`, `LIKE` và nhiều phép so sánh khác, `NULL` thường tạo `UNKNOWN`. `NULLIF(x, 0)` thường được dùng để biến mẫu số bằng 0 thành `NULL` trước phép chia:

~~~sql
-- Minh họa công thức tránh chia trực tiếp cho 0:
SELECT 100.0 / NULLIF(0, 0) AS result_value;
-- Trong DBMS hỗ trợ biểu thức này, result_value là NULL.
~~~

Kết quả `NULL` cần được ứng dụng/biểu thức phía sau xử lý phù hợp; nó không tự mang nghĩa “kết quả chia là 0”.

## 8. NULL trong tổng hợp, sắp xếp và ràng buộc

### 8.1. COUNT và GROUP BY

Các hàm tổng hợp thường bỏ qua dữ liệu `NULL` ở **đối số**: `COUNT(col)` chỉ đếm giá trị không `NULL`, trong khi `COUNT(*)` đếm mọi hàng. Các hàm như `SUM` và `AVG` cũng bỏ qua giá trị `NULL`; nếu không còn giá trị phù hợp, kết quả có thể là `NULL` thay vì `0`.

~~~sql
SELECT
    COUNT(*) AS total_contacts,
    COUNT(primary_email) AS contacts_with_primary_email,
    COUNT(backup_email) AS contacts_with_backup_email
FROM contacts;
-- total_contacts = 6
-- contacts_with_primary_email = 4
-- contacts_with_backup_email = 4
~~~

`GROUP BY region_code` gom những hàng có `region_code IS NULL` thành cùng một nhóm phục vụ tổng hợp, dù `NULL = NULL` không bằng `TRUE`. `SELECT DISTINCT region_code` cũng chỉ trả một hàng `NULL` cho các bản ghi có vùng thiếu. Đây là **quy tắc nhóm và loại trùng**, không phải bằng chứng phép `=` đã thay đổi.

### 8.2. Thứ tự NULL khác nhau giữa các DBMS

Với `ORDER BY region_code ASC`, hệ SQL có thể đặt `NULL` trước hoặc sau các giá trị đã biết. Một số DBMS hỗ trợ cú pháp `NULLS FIRST` / `NULLS LAST`, nhưng không phải phiên bản nào cũng có cùng cú pháp. Khi muốn **NULL cuối danh sách** và cần cách viết tương đối dễ chuyển hệ, sử dụng biểu thức sắp xếp phụ:

~~~sql
SELECT contact_id, region_code
FROM contacts
ORDER BY
    CASE WHEN region_code IS NULL THEN 1 ELSE 0 END ASC,
    region_code ASC,
    contact_id ASC;
~~~

Tất cả giá trị đã biết có khóa sắp xếp `0`, các giá trị `NULL` có khóa `1`; do đó nhóm `NULL` nằm cuối bất kể thứ tự mặc định của DBMS. `contact_id` làm tiêu chí phụ giúp đầu ra ổn định khi cùng giá trị `region_code`.

### 8.3. UNIQUE và CHECK không tự thay thế NOT NULL

`UNIQUE` trên cột có thể cho phép nhiều hàng chứa `NULL` trong một số DBMS, trong khi hệ khác có quy tắc giới hạn khác nhau. Vì thế **đừng suy ra quy tắc về NULL chỉ từ chữ UNIQUE**; cần xem DBMS, phiên bản và cấu hình/chỉ mục cụ thể. Nếu cột bắt buộc có giá trị, khai báo `NOT NULL` một cách tường minh.

Với ràng buộc `CHECK`, SQL thông thường coi điều kiện là thỏa ràng buộc nếu kết quả không phải `FALSE` (bao gồm `UNKNOWN`), nên:

~~~sql
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    amount DECIMAL(12, 2) CHECK (amount > 0)
);
~~~

có thể vẫn chấp nhận `amount = NULL` dù có `CHECK (amount > 0)`. Nếu cần số tiền bắt buộc và dương:

~~~sql
CREATE TABLE payments_strict (
    payment_id INTEGER PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL CHECK (amount > 0)
);
~~~

Kết hợp `NOT NULL` và `CHECK` diễn đạt cả yêu cầu **phải có dữ liệu** lẫn **giá trị hợp lệ**.

## 9. So sánh NULL khi tham số đến từ ứng dụng

Trong ứng dụng, giá trị tham số có thể thiếu: người dùng chưa nhập email, dữ liệu chưa đồng bộ, hoặc bộ lọc cho phép chọn “chưa có email”. Đặt `NULL` vào placeholder của phép `=` không biến nó thành phép kiểm tra `IS NULL`.

Ví dụ với JDBC:

~~~java
String sql = "SELECT contact_id FROM contacts WHERE primary_email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setNull(1, java.sql.Types.VARCHAR);
    // Biểu thức primary_email = NULL là UNKNOWN;
    // truy vấn không trả về các hàng primary_email IS NULL.
}
~~~

Muốn thiết kế **bộ lọc email với tham số có thể NULL**, có hai hướng:

**Hướng 1 — Rẽ nhánh theo ý nghĩa bộ lọc ở tầng ứng dụng**, dễ hiểu và tương thích cao:

~~~java
String sql = (email == null)
        ? "SELECT contact_id FROM contacts WHERE primary_email IS NULL"
        : "SELECT contact_id FROM contacts WHERE primary_email = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    if (email != null) {
        statement.setString(1, email);
    }

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            int id = rs.getInt("contact_id");
            System.out.println(id);
        }
    }
}
~~~

Ở đây, giá trị `null` của Java được **định nghĩa** là yêu cầu tìm các email thiếu. Với một API khác, `null` có thể mang nghĩa “không áp dụng bộ lọc”; khi đó không nên tạo `WHERE primary_email IS NULL`. Trước khi chọn cú pháp, phải định nghĩa ngữ nghĩa của tham số.

**Hướng 2 — So sánh an toàn với tham số**, nếu DBMS hỗ trợ:

~~~sql
-- PostgreSQL, SQL Server 2022+ và DBMS có hỗ trợ cú pháp này:
SELECT contact_id
FROM contacts
WHERE primary_email IS NOT DISTINCT FROM ?;
~~~

Ví dụ này dùng dấu `?` làm placeholder minh họa kiểu JDBC, và driver sẽ bind một giá trị có thể `NULL` vào vị trí đó. Dạng placeholder thực tế phụ thuộc thư viện/DBMS (ví dụ tham số có tên, `$1` hoặc `@p1`). MySQL có thể dùng `primary_email <=> ?`. Trong các DBMS không hỗ trợ null-safe operator, ứng dụng có thể rẽ nhánh như hướng 1 hoặc xây dựng điều kiện tương ứng bằng `IS NULL` và `=`.

**An toàn truy vấn:** tham số hóa giúp phân biệt dữ liệu với cú pháp SQL, giảm nguy cơ SQL injection. Không nối trực tiếp giá trị người dùng vào chuỗi SQL, kể cả khi bạn đang tự thêm dấu nháy đơn. Placeholder chỉ đại diện cho **giá trị**, không phải tên bảng/cột hoặc từ khóa.

## 10. Những khác biệt khả chuyển ít được chú ý

| Chủ đề | Khác biệt có thể ảnh hưởng | Hướng xử lý |
| --- | --- | --- |
| Toán tử null-safe | `IS NOT DISTINCT FROM`, `<=>`, `IS` không đồng nhất | Chọn theo dialect, phiên bản hoặc mẫu điều kiện `OR/IS NULL` |
| Biểu diễn boolean | `TRUE`/`FALSE`, kiểu `BOOLEAN`, `BIT` và phép so sánh có thể khác | Dùng kiểu/cú pháp được DBMS hỗ trợ, hoặc `CASE` trả `1`/`0` |
| Chuỗi rỗng | Một số hệ (đặc biệt Oracle với chuỗi ký tự rỗng) có thể xử lý `''` như `NULL` | Xác định rõ “rỗng” khác “chưa có”, thử trên DBMS đích |
| Thứ tự NULL | `ORDER BY` đặt NULL trước/sau khác nhau | Viết `CASE WHEN col IS NULL THEN 1 ELSE 0 END` khi cần nhất quán |
| Collation | So sánh chữ hoa/thường, dấu và quy tắc ký tự khác | Cấu hình collation, chuẩn hóa dữ liệu đúng nghiệp vụ |
| UNIQUE và NULL | Khác nhau về số lượng giá trị NULL được phép | Khai báo `NOT NULL` khi bắt buộc; xem tài liệu chỉ mục/ràng buộc |
| Literal ngày/giờ | `DATE 'YYYY-MM-DD'` và cách chuyển kiểu không đồng nhất | Dùng tham số kiểu ngày từ driver hoặc cú pháp có kiểm chứng |
| Kiểu và ép kiểu | So sánh giữa các kiểu có thể được ép ngầm hoặc báo lỗi | Khai báo kiểu cột/tham số rõ ràng, tránh phụ thuộc ép kiểu ngầm |

Để chuyển ứng dụng sang DBMS khác an toàn, cần kiểm tra đồng thời **câu SQL, schema, kiểu dữ liệu, collation, ràng buộc, driver và phiên bản**. Một câu lệnh chạy thành công chưa chứng minh kết quả khớp trong mọi trường hợp `NULL`.

Đối với hiệu năng, `IS NULL` không mặc định là điều kiện “chậm” hay “không dùng được chỉ mục”. Khả năng dùng chỉ mục phụ thuộc DBMS, thống kê, dữ liệu và loại chỉ mục. Những biểu thức như `COALESCE(column, ...)` hoặc các nhánh `OR` có thể ảnh hưởng cách bộ tối ưu chọn kế hoạch; nên xem `EXPLAIN` / execution plan và đo trên dữ liệu đại diện nếu hiệu năng là yêu cầu quan trọng.

## 11. Bài tập thực hành

Sử dụng bảng `contacts` ở mục 2. Phần bài tập có thể thực hiện bằng SQL trên hệ bạn đang dùng; nếu DBMS không hỗ trợ `IS NOT DISTINCT FROM`, hãy dùng mẫu thay thế ở mục 5.

### Bài 1 — Dự đoán kết quả

Cho các điều kiện:

~~~sql
-- A
WHERE primary_email = backup_email

-- B
WHERE primary_email IS NOT DISTINCT FROM backup_email

-- C
WHERE primary_email IS DISTINCT FROM backup_email

-- D
WHERE primary_email IS NULL
~~~

Hãy liệt kê `contact_id` thỏa từng điều kiện.

**Đáp án:**

| Điều kiện | contact_id |
| --- | --- |
| A | 1, 6 |
| B | 1, 3, 6 |
| C | 2, 4, 5 |
| D | 3, 5 |

Sự khác nhau giữa A và B đến từ hàng 3 có cả hai email `NULL`.

### Bài 2 — Viết SQL có thể chuyển hệ

Không dùng `IS NOT DISTINCT FROM`, hãy lọc các contact có hai email giống nhau theo cách **hai `NULL` được coi là tương đương**.

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email = backup_email
   OR (primary_email IS NULL AND backup_email IS NULL)
ORDER BY contact_id;
~~~

Truy vấn trả `1, 3, 6`. Hãy giải thích thêm vì sao biểu thức lọc có thể là `UNKNOWN` ở hàng 2 hoặc 5 mà kết quả chọn hàng vẫn đúng.

### Bài 3 — Đừng nhầm “khác nhau” với “không bằng”

Hãy tìm những contact có email chính **khác** email dự phòng, bao gồm trường hợp chỉ một email có dữ liệu. Vì sao `primary_email <> backup_email` không đủ?

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email <> backup_email
   OR (primary_email IS NULL AND backup_email IS NOT NULL)
   OR (primary_email IS NOT NULL AND backup_email IS NULL)
ORDER BY contact_id;
-- 2, 4, 5
~~~

Toán tử `<>` không trả `TRUE` khi có một phía `NULL`, nên cần tách các trường hợp thiếu dữ liệu.

### Bài 4 — Phát hiện lỗi với NOT IN

Đoán kết quả khi bảng `blocked_emails` chứa `'chi@example.test'` và `NULL`:

~~~sql
SELECT contact_id
FROM contacts
WHERE primary_email NOT IN (SELECT email FROM blocked_emails);
~~~

Vì sao không có hàng nào được trả về? Hãy sửa truy vấn để lọc những email đã biết không bị chặn. Một đáp án dùng `primary_email IS NOT NULL` kết hợp `NOT EXISTS` như ở mục 7.

### Bài 5 — Chọn giải pháp đúng nghiệp vụ

Một hệ thống chỉ được đánh dấu “email đã xác nhận” khi **hai cột chứa cùng một địa chỉ email thực tế**, không chấp nhận cả hai cùng `NULL` là đã xác nhận. Hãy chọn giữa:

~~~sql
-- Phương án A
WHERE primary_email = backup_email

-- Phương án B
WHERE primary_email IS NOT DISTINCT FROM backup_email
~~~

**Đáp án:** phương án A phù hợp với điều kiện đã có ít nhất một email giống nhau: với cả hai cột `NULL`, A không chọn hàng. Để làm rõ yêu cầu “email thực tế phải được cung cấp”, có thể viết:

~~~sql
WHERE primary_email IS NOT NULL
  AND primary_email = backup_email
~~~

Điều kiện bổ sung giúp người đọc hiểu đúng ý nghĩa nghiệp vụ và dễ bảo trì.

## 12. Kết luận

So sánh an toàn với `NULL` bắt đầu từ việc tách ba mục đích: **kiểm tra thiếu dữ liệu** bằng `IS NULL`, **so sánh giá trị đã biết** bằng `=`/`<>`, và **so sánh hai giá trị có thể thiếu** bằng `IS [NOT] DISTINCT FROM` hoặc mẫu điều kiện tương ứng. Với bộ lọc `WHERE`, điều kiện dùng `OR` và `IS NULL` có thể chọn đúng hàng dù kết quả trung gian đôi khi là `UNKNOWN`; khi cần một cờ chắc chắn hai giá trị, hãy xử lý tường minh bằng `CASE`.

Để SQL có khả năng chuyển hệ, cần chú ý dialect và phiên bản, sự khác nhau giữa chuỗi rỗng và `NULL`, collation, thứ tự sắp xếp, ràng buộc và cách bind tham số. Trước khi viết cú pháp, hãy trả lời câu hỏi nghiệp vụ: **hai giá trị cùng chưa biết có thật sự nên được xem như bằng nhau trong thao tác này hay không?**
