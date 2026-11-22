# COALESCE để chọn giá trị khác NULL trong SQL

Khi truy vấn cơ sở dữ liệu, bạn sẽ thường gặp những cột **chưa có giá trị**: khách hàng chưa cung cấp email, nhân viên chưa có tên gọi thân mật, một đơn hàng chưa được áp dụng giảm giá, hoặc phép tổng hợp không có dòng dữ liệu để tính. SQL biểu diễn tình huống “không có giá trị” bằng `NULL`.

Hàm/biểu thức **`COALESCE`** giúp chọn **giá trị đầu tiên khác `NULL`** trong một danh sách biểu thức. Đây là công cụ quan trọng khi trình bày báo cáo, ghép thông tin từ nhiều cột và đưa ra một giá trị dự phòng hợp lý. Tuy nhiên, giá trị dự phòng phải phản ánh đúng ý nghĩa dữ liệu: **“không biết” không tự động đồng nghĩa với số 0 hoặc chuỗi rỗng**.

Bài học thuộc chủ đề **NULL và logic** trong SQL. Các ví dụ thực hành dùng PostgreSQL; cách dùng `COALESCE` cơ bản cũng được hỗ trợ rộng rãi trong các hệ quản trị như MySQL, SQL Server, Oracle Database và SQLite.

## 1. Ôn lại NULL và logic ba giá trị

`NULL` không phải một con số, một chuỗi hay một nhãn đặc biệt. Nó thường biểu diễn một giá trị **chưa biết, chưa cung cấp hoặc không áp dụng**, tùy quy ước của cột.

| Biểu thức | Ý nghĩa |
|---|---|
| `NULL` | Không có một giá trị xác định |
| `0` | Một giá trị số xác định bằng không |
| `''` | Chuỗi ký tự có độ dài bằng không |
| `' '` | Chuỗi có một dấu cách |
| `FALSE` | Giá trị logic sai |
| `'NULL'` | Chuỗi gồm bốn ký tự N, U, L, L |

Những giá trị ở năm dòng cuối đều **khác `NULL`**, dù đôi khi giao diện ứng dụng hiển thị chúng giống như “trống”.

Trong SQL, phép so sánh thông thường với `NULL` thường cho kết quả **UNKNOWN** thay vì `TRUE` hoặc `FALSE`:

```sql
SELECT
    NULL = NULL AS compare_two_nulls,
    NULL = 0 AS compare_with_zero,
    NULL IS NULL AS check_is_null,
    0 IS NOT NULL AS zero_has_value;
```

Trong PostgreSQL, hai biểu thức so sánh `NULL = ...` ở trên trả giá trị logic chưa biết, thường hiển thị thành ô trống hoặc `NULL`; hai phép kiểm tra `IS NULL` và `IS NOT NULL` trả `TRUE`. Đây là lý do nên dùng `IS NULL` và `IS NOT NULL` khi kiểm tra sự thiếu dữ liệu:

```sql
-- Đúng: tìm những bản ghi chưa có email.
SELECT *
FROM customers
WHERE email IS NULL;
```

```sql
-- Sai về ý nghĩa: không tìm được NULL bằng toán tử =.
SELECT *
FROM customers
WHERE email = NULL;
```

Mệnh đề `WHERE` chỉ giữ các dòng mà điều kiện có kết quả `TRUE`; kết quả `FALSE` và `UNKNOWN` đều bị loại. `COALESCE` thường được dùng khi muốn **biến một giá trị có thể NULL thành một giá trị dự phòng có nghĩa**, nhưng không thay thế nguyên tắc kiểm tra `IS NULL`.

## 2. Cú pháp và quy tắc chọn giá trị của COALESCE

Cú pháp tổng quát:

```sql
COALESCE(expression_1, expression_2, ..., expression_n)
```

DBMS xem xét các biểu thức theo thứ tự và trả về giá trị của **biểu thức đầu tiên không phải `NULL`**. Nếu **tất cả** biểu thức đều là `NULL`, kết quả cũng là `NULL`.

Ví dụ đơn giản:

```sql
SELECT
    COALESCE(NULL, 10, 20) AS first_non_null,
    COALESCE(NULL, NULL, 20) AS second_example,
    COALESCE(0, 10, 20) AS zero_is_not_null,
    COALESCE('', 'Giá trị dự phòng') AS empty_is_not_null,
    COALESCE(NULL, NULL) AS still_null;
```

Kết quả dự kiến:

| Cột kết quả | Giá trị |
|---|---|
| `first_non_null` | `10` |
| `second_example` | `20` |
| `zero_is_not_null` | `0` |
| `empty_is_not_null` | `''` (chuỗi rỗng trong PostgreSQL) |
| `still_null` | `NULL` |

Bạn có thể hình dung `COALESCE` như một chuỗi lựa chọn:

```text
COALESCE(A, B, C, D)
     |
     +-- A khác NULL? Có --> lấy A
     |                     Không
     +-- B khác NULL? Có --> lấy B
     |                     Không
     +-- C khác NULL? Có --> lấy C
     |                     Không
     +-- D khác NULL? Có --> lấy D
                           Không --> NULL
```

**Thứ tự đối số quyết định ưu tiên.** Ví dụ, `COALESCE(work_email, personal_email, 'Chưa có email')` ưu tiên email công việc, sau đó email cá nhân và cuối cùng mới dùng thông báo.

### 2.1. COALESCE không phải hàm chọn giá trị “đúng”, “có nội dung” hay “khác 0”

Xem các ví dụ:

```sql
SELECT
    COALESCE(FALSE, TRUE) AS boolean_result,
    COALESCE(0, 99) AS numeric_result,
    COALESCE('   ', 'Chưa nhập') AS whitespace_result,
    COALESCE('N/A', 'Giá trị khác') AS text_result;
```

Kết quả lần lượt là `FALSE`, `0`, chuỗi ba dấu cách và `'N/A'`. Lý do: tất cả đối số đầu tiên đều **không NULL**.

Nếu quy tắc nghiệp vụ muốn coi chuỗi rỗng hoặc toàn dấu cách như “chưa nhập”, hãy **chuẩn hóa dữ liệu trước khi gọi `COALESCE`**, chẳng hạn dùng `NULLIF` kết hợp `TRIM`; phần sau sẽ minh họa.

### 2.2. COALESCE khác với thay đổi dữ liệu lưu trữ

Câu lệnh sau chỉ thay giá trị **trên tập kết quả truy vấn**:

```sql
SELECT COALESCE(email, 'Chưa có email') AS email_display
FROM customers;
```

Nó **không ghi lại** `'Chưa có email'` vào cột `email`. Nếu muốn sửa dữ liệu trong bảng, phải có câu lệnh `UPDATE` hoặc `INSERT` phù hợp, đồng thời cân nhắc việc mất thông tin rằng trường đó vốn chưa được cung cấp.

## 3. Tạo dữ liệu thực hành

Để luyện tập trực tiếp, dùng một bảng hồ sơ thành viên. Các lệnh dưới đây viết theo PostgreSQL và chỉ nên chạy trong **cơ sở dữ liệu thực hành** nơi bạn có quyền tạo bảng.

```sql
CREATE TABLE member_profiles (
    member_id INTEGER PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    work_email VARCHAR(150),
    personal_email VARCHAR(150),
    phone VARCHAR(30),
    city VARCHAR(80),
    discount_percent NUMERIC(5, 2)
);

INSERT INTO member_profiles (
    member_id,
    full_name,
    nickname,
    work_email,
    personal_email,
    phone,
    city,
    discount_percent
)
VALUES
    (
        1, 'Nguyễn An', 'An',
        'an@company.example', NULL,
        '0901000001', 'Hà Nội', 0.00
    ),
    (
        2, 'Trần Bình', NULL,
        NULL, 'binh@example.net',
        NULL, NULL, NULL
    ),
    (
        3, 'Lê Chi', '',
        NULL, NULL,
        '', 'Đà Nẵng', 10.00
    ),
    (
        4, 'Phạm Dũng', NULL,
        NULL, NULL,
        NULL, 'TP. Hồ Chí Minh', NULL
    );
```

Các tên miền `example` và số điện thoại trong ví dụ chỉ dùng để minh họa. Nếu chạy lại lệnh `CREATE TABLE` hoặc `INSERT` trên cùng dữ liệu, có thể gặp lỗi bảng đã tồn tại hoặc trùng khóa chính. Thực hiện phần tạo dữ liệu một lần.

Bảng vừa tạo cố ý chứa nhiều tình huống: `NULL`, chuỗi rỗng `''` và số `0`. Từ đó ta có thể quan sát `COALESCE` thực sự lựa chọn giá trị như thế nào.

## 4. Dùng COALESCE trong SELECT để hiển thị dữ liệu

### 4.1. Hiển thị tên gọi ưu tiên nickname

Giả sử màn hình thành viên muốn hiển thị `nickname` nếu đã có, nếu chưa có thì hiển thị `full_name`:

```sql
SELECT
    member_id,
    COALESCE(nickname, full_name) AS display_name
FROM member_profiles
ORDER BY member_id;
```

Kết quả:

| member_id | display_name |
|---|---|
| 1 | An |
| 2 | Trần Bình |
| 3 | `''` (chuỗi rỗng) |
| 4 | Phạm Dũng |

Hàng của Lê Chi có `nickname = ''`, đây là chuỗi rỗng nhưng **không phải `NULL`**, nên `COALESCE` chọn ngay chuỗi đó. Để loại tình huống này, ta cần chuẩn hóa chuỗi trước:

```sql
SELECT
    member_id,
    COALESCE(NULLIF(TRIM(nickname), ''), full_name) AS display_name
FROM member_profiles
ORDER BY member_id;
```

Các bước xử lý của `NULLIF(TRIM(nickname), '')`:

1. `TRIM(nickname)` loại bỏ dấu cách ở đầu và cuối chuỗi. Nếu `nickname` là `NULL`, kết quả vẫn là `NULL`.
2. `NULLIF(value, '')` trả `NULL` nếu `value` bằng chuỗi rỗng; trong trường hợp khác, nó trả về `value`.
3. `COALESCE(..., full_name)` chọn `full_name` nếu kết quả bước trước là `NULL`.

Nhờ đó, hàng của Lê Chi sẽ hiển thị `Lê Chi`.

**Lưu ý:** `TRIM` và `NULLIF` được hỗ trợ rộng rãi, nhưng các DBMS có thể khác nhau về ký tự được loại bỏ mặc định và cách coi chuỗi rỗng. Đặc biệt, trong Oracle Database, chuỗi ký tự rỗng thường được xem là `NULL` đối với kiểu chuỗi thông dụng.

### 4.2. Ưu tiên email theo thứ tự đã thống nhất

```sql
SELECT
    member_id,
    full_name,
    COALESCE(
        work_email,
        personal_email,
        '(chưa cung cấp email)'
    ) AS preferred_email
FROM member_profiles
ORDER BY member_id;
```

Với dữ liệu ví dụ:

| Thành viên | preferred_email |
|---|---|
| Nguyễn An | `an@company.example` |
| Trần Bình | `binh@example.net` |
| Lê Chi | `(chưa cung cấp email)` |
| Phạm Dũng | `(chưa cung cấp email)` |

Câu truy vấn không tạo email mới, chỉ quyết định **giá trị thể hiện trên kết quả**. Nếu địa chỉ đã có nhưng sai định dạng hoặc không còn dùng được, `COALESCE` vẫn chọn nó vì không phải `NULL`. Xác thực email là quy tắc riêng.

Bạn cũng có thể thêm nhiều giá trị dự phòng:

```sql
SELECT
    member_id,
    COALESCE(
        NULLIF(TRIM(work_email), ''),
        NULLIF(TRIM(personal_email), ''),
        '(không có email)'
    ) AS email_display
FROM member_profiles;
```

### 4.3. Dùng giá trị thay thế khi ghép chuỗi

Trong PostgreSQL, toán tử nối chuỗi `||` thường cho kết quả `NULL` nếu một toán hạng là `NULL`:

```sql
SELECT
    full_name || ' - ' || city AS description
FROM member_profiles
WHERE member_id = 2;
```

Vì `city` của Trần Bình là `NULL`, toàn bộ biểu thức nối có thể thành `NULL`. Dùng `COALESCE` để có nhãn hiển thị:

```sql
SELECT
    full_name || ' - ' || COALESCE(city, 'Chưa rõ thành phố')
        AS description
FROM member_profiles
WHERE member_id = 2;
```

Kết quả: `Trần Bình - Chưa rõ thành phố`.

Một số hệ quản trị có các hàm ghép chuỗi xử lý `NULL` khác nhau, ví dụ `CONCAT` có quy tắc riêng theo DBMS. Vì vậy, việc tự dùng `COALESCE` để biểu đạt ý định khi nối chuỗi giúp câu truy vấn dễ hiểu và ít phụ thuộc vào cách xử lý ngầm.

## 5. Dùng COALESCE với số và phép tính

Giả sử báo cáo cần hiện phần trăm giảm giá, nhưng cột `discount_percent` có thể chưa được nhập:

```sql
SELECT
    member_id,
    full_name,
    COALESCE(discount_percent, 0.00) AS discount_for_display
FROM member_profiles
ORDER BY member_id;
```

Với bảng mẫu, Nguyễn An có **mức giảm giá đã được lưu là 0%**, còn Trần Bình và Phạm Dũng có mức giảm giá **chưa xác định**. Cả ba có thể hiện `0` trong cột `discount_for_display`, nhưng dữ liệu gốc không giống nhau.

Điểm cần quyết định là **ý nghĩa nghiệp vụ**:

- Nếu không có giảm giá nghĩa là **0%**, dùng `COALESCE(discount_percent, 0)` là hợp lý để tính số tiền.
- Nếu `NULL` nghĩa là **chưa được duyệt chính sách giảm giá**, việc thay `0` có thể che giấu hồ sơ chưa hoàn chỉnh.
- Nếu cần giữ cả thông tin đầy đủ/thiếu, chọn thêm cột trạng thái hoặc vẫn lấy cột gốc bên cạnh giá trị hiển thị.

Ví dụ hiển thị cả hai:

```sql
SELECT
    member_id,
    discount_percent AS stored_discount,
    COALESCE(discount_percent, 0.00) AS display_discount,
    CASE
        WHEN discount_percent IS NULL THEN 'Chưa xác định'
        ELSE 'Đã xác định'
    END AS discount_status
FROM member_profiles
ORDER BY member_id;
```

### 5.1. COALESCE trong phép nhân và phép chia

Nếu nghiệp vụ xác định `NULL` ở cột giảm giá là không giảm giá, ta có thể tính giá sau giảm:

```sql
SELECT
    member_id,
    100000.00
        * (1 - COALESCE(discount_percent, 0.00) / 100)
        AS payable_amount
FROM member_profiles
ORDER BY member_id;
```

Với giá gốc giả định `100000.00`, hàng của Lê Chi được giảm 10%, còn các thành viên khác được tính 0% khi hiển thị. Trong hệ thống bán hàng thực tế, cần thêm quy tắc làm tròn và cách xử lý mức giảm chưa xác định.

Một tình huống khác: tránh phép chia cho 0 bằng `NULLIF` rồi quyết định có dùng giá trị dự phòng không.

```sql
SELECT
    100.0 / NULLIF(0, 0) AS undefined_ratio,
    COALESCE(100.0 / NULLIF(0, 0), 0) AS fallback_ratio;
```

Trong PostgreSQL, `NULLIF(0, 0)` là `NULL`; phép chia cho `NULL` cho `NULL`, và `COALESCE(..., 0)` chọn `0`. Dù vậy, **tỷ lệ không xác định do mẫu số bằng 0 không nhất thiết có nghĩa là tỷ lệ bằng 0**. Nếu báo cáo cần phân biệt thiếu dữ liệu và giá trị thật, giữ `NULL` hoặc hiển thị trạng thái thay vì mặc định thay bằng 0.

## 6. COALESCE và hàm tổng hợp: tránh làm sai ý nghĩa thống kê

Các hàm tổng hợp như `SUM` và `AVG` thường **bỏ qua giá trị `NULL`** trong các hàng đầu vào. Điều này dẫn đến khác biệt quan trọng giữa việc đặt `COALESCE` *bên trong* và *bên ngoài* phép tổng hợp.

### 6.1. Tính tổng với các giá trị NULL

```sql
SELECT
    SUM(discount_percent) AS raw_sum,
    COALESCE(SUM(discount_percent), 0) AS display_sum,
    SUM(COALESCE(discount_percent, 0)) AS row_fallback_sum
FROM member_profiles;
```

Với dữ liệu mẫu, `SUM(discount_percent)` là `10.00` vì nó cộng hai giá trị đã biết: `0.00` và `10.00`. Hai cách dùng `COALESCE` cũng cho 10 trong trường hợp này.

Nhưng kết quả có thể **khác nhau** khi tập đầu vào rỗng:

```sql
SELECT
    COALESCE(SUM(discount_percent), 0) AS sum_fallback_after_aggregate,
    SUM(COALESCE(discount_percent, 0)) AS sum_fallback_per_row
FROM member_profiles
WHERE member_id < 0;
```

Vì không có dòng nào thỏa điều kiện, `SUM` trả `NULL`:

- `COALESCE(SUM(...), 0)` trả **0** cho cả nhóm trống.
- `SUM(COALESCE(..., 0))` vẫn trả **NULL**, vì không có hàng nào để tính biểu thức bên trong.

Nếu yêu cầu là “hiển thị tổng bằng 0 khi không có giao dịch”, thường đặt `COALESCE` **ngoài** `SUM`. Nếu yêu cầu là “mỗi hàng NULL được xem như 0 trước khi tính toán”, có thể dùng `COALESCE` bên trong. Hai cách thể hiện hai ý định khác nhau.

### 6.2. Trung bình cộng: NULL không đồng nghĩa với 0

Xét bảng `member_profiles`:

- Nguyễn An: `discount_percent = 0.00`.
- Trần Bình: `discount_percent = NULL`.
- Lê Chi: `discount_percent = 10.00`.
- Phạm Dũng: `discount_percent = NULL`.

Thử so sánh:

```sql
SELECT
    AVG(discount_percent) AS average_known_values,
    AVG(COALESCE(discount_percent, 0)) AS average_treat_null_as_zero
FROM member_profiles;
```

Kết quả:

| Công thức | Cách tính | Kết quả |
|---|---|---|
| `AVG(discount_percent)` | `(0 + 10) / 2` | `5.00` |
| `AVG(COALESCE(discount_percent, 0))` | `(0 + 0 + 10 + 0) / 4` | `2.50` |

Đây là **hai số liệu khác nhau về mặt nghiệp vụ**. Công thức đầu trung bình các giá trị đã biết; công thức sau giả định mọi giá trị bị thiếu đều bằng 0. Không dùng `COALESCE` trước `AVG` chỉ để “loại NULL” vì `AVG` đã tự bỏ qua chúng.

### 6.3. COUNT và COALESCE

`COUNT(*)` đếm số hàng; `COUNT(column)` đếm số giá trị khác `NULL`; `COUNT(COALESCE(column, fallback))` có thể đếm cả những hàng trước đây có `NULL` nếu fallback không NULL.

```sql
SELECT
    COUNT(*) AS total_members,
    COUNT(work_email) AS members_with_work_email,
    COUNT(COALESCE(work_email, personal_email)) AS members_with_any_email
FROM member_profiles;
```

Với dữ liệu mẫu, các kết quả là `4`, `1` và `2`. Đếm “có ít nhất một email” có thể dùng `COALESCE(work_email, personal_email)` nếu dữ liệu đầu vào phân biệt rõ `NULL` với chuỗi rỗng.

## 7. COALESCE trong WHERE, GROUP BY và ORDER BY

### 7.1. Lọc bằng COALESCE: chỉ làm khi có chủ đích

Ví dụ, doanh nghiệp quy định thành viên chưa được khai báo mức giảm giá sẽ **tạm thời có mức giảm 0%**. Khi đó:

```sql
SELECT
    member_id,
    full_name,
    discount_percent
FROM member_profiles
WHERE COALESCE(discount_percent, 0) = 0
ORDER BY member_id;
```

Câu truy vấn lấy cả thành viên có `discount_percent = 0` và thành viên có `discount_percent IS NULL`. Nếu mục đích chỉ là tìm các dòng chưa có dữ liệu, cách đúng là:

```sql
SELECT
    member_id,
    full_name
FROM member_profiles
WHERE discount_percent IS NULL;
```

Còn nếu muốn tìm các dòng đã được gán giảm giá bằng 0, **không bao gồm NULL**, hãy viết:

```sql
SELECT
    member_id,
    full_name
FROM member_profiles
WHERE discount_percent = 0;
```

Ba truy vấn trên đặt ba câu hỏi **khác nhau**. Không dùng `COALESCE` thay cho `IS NULL` khi câu hỏi chỉ là kiểm tra dữ liệu thiếu.

### 7.2. Nhóm các giá trị NULL dưới một nhãn

Ví dụ báo cáo số thành viên theo thành phố:

```sql
SELECT
    COALESCE(city, '(chưa xác định)') AS city_label,
    COUNT(*) AS member_count
FROM member_profiles
GROUP BY COALESCE(city, '(chưa xác định)')
ORDER BY city_label;
```

Trong bảng mẫu, Trần Bình được nhóm dưới nhãn `(chưa xác định)`. Cách làm này hữu ích cho báo cáo, nhưng có một rủi ro: **nếu dữ liệu thật có thành phố mang đúng chuỗi dùng làm nhãn dự phòng**, hai nhóm sẽ bị gộp. Để bảo toàn phân biệt giữa dữ liệu thật và dữ liệu thiếu, có thể nhóm theo cột gốc rồi chỉ thay nhãn khi hiển thị:

```sql
SELECT
    city,
    COALESCE(city, '(chưa xác định)') AS city_label,
    COUNT(*) AS member_count
FROM member_profiles
GROUP BY city
ORDER BY city;
```

Cách thứ hai giữ giá trị `city` ban đầu để người dùng hoặc ứng dụng biết nhóm nào thực sự là `NULL`.

### 7.3. Sắp xếp theo giá trị dự phòng

```sql
SELECT
    member_id,
    full_name,
    city
FROM member_profiles
ORDER BY COALESCE(city, 'ZZZ'), member_id;
```

Ở đây `'ZZZ'` chỉ là một giá trị thay thế để sắp xếp; thứ tự thực tế còn phụ thuộc **collation** (quy tắc so sánh chuỗi) của DBMS. PostgreSQL hỗ trợ cách diễn đạt trực tiếp:

```sql
SELECT
    member_id,
    full_name,
    city
FROM member_profiles
ORDER BY city NULLS LAST, member_id;
```

`NULLS LAST` phù hợp hơn khi mục đích là “đưa dòng thiếu thành phố xuống cuối” mà **không cần biến đổi giá trị để sắp xếp**. Cú pháp `NULLS FIRST/LAST` không được hỗ trợ giống nhau ở mọi DBMS.

### 7.4. Hiệu năng: biểu thức trên cột có thể ảnh hưởng chỉ mục

Điều kiện:

```sql
WHERE COALESCE(discount_percent, 0) = 0
```

đưa cột `discount_percent` vào trong một biểu thức. Với chỉ mục B-tree thông thường trên cột, một số DBMS hoặc kế hoạch thực thi có thể khó sử dụng chỉ mục theo cách tối ưu. Nếu điều kiện thực sự cần lấy **NULL hoặc 0**, có thể viết rõ:

```sql
WHERE discount_percent = 0
   OR discount_percent IS NULL
```

Viết lại như vậy dễ thể hiện ý nghĩa, nhưng **không bảo đảm luôn nhanh hơn**. Hiệu năng phụ thuộc lượng dữ liệu, thống kê, chỉ mục, DBMS và truy vấn đầy đủ. Với các câu quan trọng, xem kế hoạch thực thi (`EXPLAIN` hoặc công cụ tương đương) trước khi kết luận.

## 8. COALESCE trong JOIN: cần tránh tạo những kết quả ghép sai

Giả sử hai bảng có cột mã khách hàng, một số dòng không có mã:

```sql
-- Cần thận trọng với cách nối này.
SELECT *
FROM orders AS o
JOIN customers AS c
    ON COALESCE(o.customer_id, 0)
     = COALESCE(c.customer_id, 0);
```

Cách viết này có thể coi cả hai giá trị `NULL` là số `0` rồi nối với nhau. Nguy hiểm hơn, nếu `0` là một mã khách hàng thật, dòng thiếu mã cũng có thể bị nối vào khách hàng đó. Điều này có thể tạo kết quả sai hoặc phát sinh nhiều cặp nối không mong muốn.

Nếu `NULL` nghĩa là **chưa biết khách hàng**, quan hệ thông thường nên dùng:

```sql
SELECT *
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.customer_id;
```

Nếu yêu cầu thực sự là **so sánh hai giá trị có coi NULL bằng NULL**, một số DBMS có toán tử hoặc cách diễn đạt an toàn hơn. Ví dụ PostgreSQL:

```sql
-- Dùng trong bài toán so sánh hai giá trị có tính đến NULL;
-- vẫn cần kiểm tra xem NULL-NULL có đúng với quan hệ dữ liệu hay không.
SELECT *
FROM table_a AS a
JOIN table_b AS b
    ON a.optional_code IS NOT DISTINCT FROM b.optional_code;
```

`IS NOT DISTINCT FROM` coi hai `NULL` là bằng nhau trong phép so sánh “null-safe”. Tuy nhiên, phép so sánh này **không tự động phù hợp cho khóa ngoại**; hai giá trị đều chưa biết không có nghĩa là chúng thuộc cùng một thực thể.

Một cách dùng rất phổ biến và hữu ích hơn trong `LEFT JOIN` là đặt `COALESCE` ở phần `SELECT` để hiển thị:

```sql
SELECT
    o.order_id,
    COALESCE(c.customer_name, '(khách chưa xác định)') AS customer_display
FROM orders AS o
LEFT JOIN customers AS c
    ON o.customer_id = c.customer_id;
```

Ví dụ giả định hai bảng `orders`, `customers` tồn tại và có các cột được nhắc tới. `LEFT JOIN` giữ tất cả đơn hàng; nếu không khớp khách hàng, cột phía `customers` có thể là `NULL` và `COALESCE` sẽ hiển thị nhãn dự phòng.

## 9. Kiểu dữ liệu của các đối số COALESCE

Các đối số phải có kiểu dữ liệu **có thể được DBMS suy luận hoặc chuyển đổi về một kiểu kết quả tương thích**. Không phải mọi cách kết hợp chữ và số đều hợp lệ.

Ví dụ PostgreSQL:

```sql
SELECT
    COALESCE(NULL::INTEGER, 100) AS numeric_fallback,
    COALESCE(NULL::VARCHAR, 'Chưa có') AS text_fallback,
    COALESCE(NULL::DATE, DATE '2026-11-14') AS date_fallback;
```

`::` là cú pháp ép kiểu của PostgreSQL. Có thể dùng `CAST(expression AS type)` theo cú pháp dễ chuyển đổi giữa các DBMS:

```sql
SELECT
    COALESCE(CAST(NULL AS INTEGER), 100) AS numeric_fallback,
    COALESCE(CAST(NULL AS VARCHAR(100)), 'Chưa có') AS text_fallback;
```

Trong PostgreSQL, biểu thức sau **không phải một cách dự phòng phù hợp** cho cột số:

```sql
-- Có thể báo lỗi chuyển kiểu: giá trị số và chữ không tương thích.
SELECT COALESCE(discount_percent, 'Chưa có')
FROM member_profiles;
```

Nếu cần một **chuỗi hiển thị**, hãy chủ động chuyển số sang chữ trước:

```sql
SELECT
    member_id,
    COALESCE(
        CAST(discount_percent AS VARCHAR(40)),
        'Chưa có'
    ) AS discount_display
FROM member_profiles
ORDER BY member_id;
```

Cách này phù hợp với **lớp trình bày**; nếu còn cần tính toán, tốt hơn nên trả về cột số và trạng thái tách biệt để ứng dụng tự định dạng.

Cũng không nên ép một giá trị ngày giờ thành chuỗi chỉ vì muốn hiển thị `'Chưa xác định'` trong cùng một cột. Khi tính toán ngày giờ hoặc gửi dữ liệu qua API, giữ kiểu ngày giờ đúng thường hữu ích hơn:

```sql
-- Ví dụ hợp lệ: nếu không có ngày giao thì lấy ngày dự kiến.
SELECT
    COALESCE(
        CAST(NULL AS DATE),
        DATE '2026-11-20'
    ) AS relevant_date;
```

**Khác biệt giữa DBMS:** quy tắc chọn kiểu của `COALESCE` có thể phụ thuộc thứ tự ưu tiên kiểu dữ liệu và khả năng chuyển kiểu ngầm. Trong SQL Server, `COALESCE` thường được biến đổi tương tự `CASE` và khác với `ISNULL` về cách chọn kiểu trả về. Hãy kiểm tra schema và ép kiểu có chủ đích, nhất là khi kết quả sẽ đưa vào cột có độ dài hoặc độ chính xác bị giới hạn.

## 10. COALESCE và CASE, NULLIF, các hàm tương tự

### 10.1. COALESCE có thể diễn đạt bằng CASE

Về ý tưởng, biểu thức:

```sql
COALESCE(work_email, personal_email, '(chưa có)')
```

tương đương với logic:

```sql
CASE
    WHEN work_email IS NOT NULL THEN work_email
    WHEN personal_email IS NOT NULL THEN personal_email
    ELSE '(chưa có)'
END
```

Khi chỉ cần lấy **giá trị đầu tiên không NULL**, `COALESCE` ngắn gọn và trực tiếp hơn. Khi muốn điều kiện phức tạp như “chọn email công việc chỉ khi đã xác thực”, `CASE` diễn đạt rõ ràng hơn:

```sql
-- Ví dụ giả định có thêm cột work_email_verified.
CASE
    WHEN work_email IS NOT NULL
         AND work_email_verified = TRUE
        THEN work_email
    WHEN personal_email IS NOT NULL
        THEN personal_email
    ELSE '(chưa có)'
END
```

`COALESCE` chỉ kiểm tra **có NULL hay không**; nó không tự đánh giá tính hợp lệ, xác minh hay ưu tiên theo các điều kiện khác.

### 10.2. NULLIF làm điều gần như ngược lại

`NULLIF(a, b)` trả `NULL` nếu `a` và `b` bằng nhau; nếu không, trả `a`. Kết hợp `NULLIF` và `COALESCE` rất hữu ích khi dữ liệu đầu vào có giá trị đại diện cho “trống”:

```sql
SELECT
    member_id,
    COALESCE(
        NULLIF(TRIM(phone), ''),
        '(chưa có số điện thoại)'
    ) AS phone_display
FROM member_profiles
ORDER BY member_id;
```

`NULLIF(TRIM(phone), '')` biến chuỗi rỗng hoặc toàn dấu cách thành `NULL`, rồi `COALESCE` chọn văn bản dự phòng. Với cột số, có thể dùng `NULLIF(value, 0)` để biến `0` thành `NULL` **nếu và chỉ nếu** `0` là tín hiệu thiếu dữ liệu theo quy ước nghiệp vụ. Không áp dụng quy tắc đó một cách máy móc.

### 10.3. Các hàm tương tự trong từng hệ quản trị

| Cách viết | Hệ quản trị phổ biến | Ý nghĩa và lưu ý |
|---|---|---|
| `COALESCE(a, b, c, ...)` | SQL chuẩn; PostgreSQL, MySQL, SQL Server, Oracle, SQLite | Trả đối số đầu tiên khác `NULL`; hỗ trợ nhiều đối số |
| `IFNULL(a, b)` | MySQL, SQLite | Chọn `a` nếu không NULL, nếu không chọn `b`; chỉ hai đối số |
| `ISNULL(a, b)` | SQL Server | Hàm thay thế NULL với hai đối số; quy tắc chọn kiểu/độ dài khác `COALESCE` |
| `NVL(a, b)` | Oracle Database | Hàm thay thế NULL có hai đối số; có khác biệt về ép kiểu và đánh giá biểu thức |
| `CASE WHEN ...` | SQL chuẩn; nhiều DBMS | Diễn đạt điều kiện tùy ý, không chỉ xử lý NULL |
| `NULLIF(a, b)` | SQL chuẩn; nhiều DBMS | Trả `NULL` khi hai biểu thức bằng nhau |

Lưu ý quan trọng: trong **SQL Server**, `ISNULL` là **hàm hai đối số**, trong khi **MySQL** cũng có `ISNULL(expr)` một đối số để **kiểm tra xem biểu thức có NULL**; cùng tên nhưng cách dùng khác nhau. Nếu muốn viết SQL dễ chuyển đổi, `COALESCE` thường là lựa chọn nhất quán hơn.

### 10.4. Đánh giá đối số và tác dụng phụ

Về ngữ nghĩa, `COALESCE` chọn biểu thức đầu tiên có giá trị khác `NULL`. Không nên suy ra rằng **mọi DBMS đều đảm bảo đánh giá mỗi đối số đúng một lần**, đặc biệt khi đối số chứa truy vấn con, hàm có tác dụng phụ hoặc biểu thức dễ phát sinh lỗi:

- PostgreSQL thường không cần đánh giá biểu thức nằm sau một giá trị đã biết là khác `NULL`, nhưng giai đoạn tối ưu hóa có thể xử lý trước một số biểu thức hằng.
- SQL Server mô tả `COALESCE` như biểu thức được viết lại thành `CASE`; một số biểu thức, chẳng hạn truy vấn con, có thể được đánh giá nhiều lần.
- Các hàm riêng như `NVL` không nhất thiết có cùng hành vi đánh giá đối số với `COALESCE`.

Khi một biểu thức dự phòng tốn tài nguyên hoặc phụ thuộc trạng thái thay đổi liên tục, nên tách công việc thành truy vấn con/CTE hoặc cấu trúc phù hợp và kiểm tra quy tắc của DBMS. `COALESCE` là công cụ chọn giá trị, không nên dựa vào nó để điều khiển tác dụng phụ.

## 11. COALESCE không giống DEFAULT khi định nghĩa bảng

Trong định nghĩa cột, `DEFAULT` quy định giá trị được dùng khi một lệnh `INSERT` **không cung cấp giá trị cho cột** hoặc sử dụng từ khóa `DEFAULT`; nó không đảm bảo mọi giá trị `NULL` đều tự được đổi thành default.

Ví dụ PostgreSQL:

```sql
CREATE TABLE practice_preferences (
    preference_id INTEGER PRIMARY KEY,
    notification_count INTEGER DEFAULT 0
);

INSERT INTO practice_preferences (preference_id)
VALUES (1);

INSERT INTO practice_preferences (preference_id, notification_count)
VALUES (2, NULL);

SELECT
    preference_id,
    notification_count,
    COALESCE(notification_count, 0) AS display_count
FROM practice_preferences
ORDER BY preference_id;
```

Giải thích:

- Hàng `1` không truyền `notification_count` nên database sử dụng giá trị mặc định `0`.
- Hàng `2` truyền **tường minh `NULL`**, vì cột cho phép NULL nên lưu `NULL`.
- `COALESCE(notification_count, 0)` khi `SELECT` hiển thị `0` cho cả hai hàng, nhưng không thay đổi dữ liệu đã lưu.

Nếu nghiệp vụ quy định cột **không bao giờ được thiếu**, kết hợp `NOT NULL` với `DEFAULT` và kiểm tra dữ liệu khi ghi thường phù hợp hơn việc chỉ dùng `COALESCE` trong mọi truy vấn đọc.

## 12. Những lỗi thường gặp

### Lỗi 1: Cho rằng NULL bằng 0 hoặc chuỗi rỗng

```sql
SELECT
    COALESCE(0, 9) AS number_value,
    COALESCE('', 'Dự phòng') AS text_value;
```

Kết quả không phải `9` hay `'Dự phòng'`. Đối số đầu đã khác `NULL`.

**Cách làm:** xác định quy ước dữ liệu; dùng `NULLIF` để chuyển giá trị “trống” thành `NULL` khi thích hợp.

### Lỗi 2: Thay NULL bằng 0 trước mọi phép thống kê

```sql
-- Có thể thay đổi mẫu số trung bình và sai lệch kết quả.
SELECT AVG(COALESCE(discount_percent, 0))
FROM member_profiles;
```

Nếu câu hỏi là “trung bình của các mức giảm giá đã biết”, dùng:

```sql
SELECT AVG(discount_percent)
FROM member_profiles;
```

### Lỗi 3: Dùng COALESCE trong điều kiện lọc dù chỉ muốn tìm NULL

```sql
-- Bao gồm cả NULL và số 0.
WHERE COALESCE(discount_percent, 0) = 0
```

```sql
-- Chỉ tìm giá trị thiếu.
WHERE discount_percent IS NULL
```

### Lỗi 4: Ép kiểu không tương thích

```sql
-- Với cột NUMERIC trong PostgreSQL, đây không phải giá trị dự phòng hợp lệ.
SELECT COALESCE(discount_percent, 'Không rõ')
FROM member_profiles;
```

**Cách làm:** giữ kết quả dạng số với dự phòng số hoặc chủ động ép kiểu sang chuỗi **nếu mục đích thực sự là hiển thị**.

### Lỗi 5: Tin rằng COALESCE sửa dữ liệu gốc

`COALESCE` trong `SELECT` chỉ thay đổi kết quả đọc. Nếu hệ thống cần dữ liệu gốc không NULL, hãy đặt ràng buộc hoặc sửa dữ liệu theo quy trình nhập liệu thích hợp.

### Lỗi 6: Dùng COALESCE để nối các khóa bị thiếu

Ghép `COALESCE(a.id, 0) = COALESCE(b.id, 0)` có thể nối các dòng không có khóa hoặc nối nhầm vào khóa thật `0`. Chỉ dùng logic so sánh “null-safe” khi nghiệp vụ thực sự yêu cầu.

### Lỗi 7: Đặt thứ tự giá trị dự phòng không đúng ưu tiên

```sql
-- Ưu tiên email cá nhân.
COALESCE(personal_email, work_email)

-- Ưu tiên email công việc.
COALESCE(work_email, personal_email)
```

Đều có cú pháp hợp lệ, nhưng kết quả khác nhau nếu cả hai email đều được cung cấp. Hãy để thứ tự phản ánh quy tắc nghiệp vụ.

## 13. Bài tập thực hành có lời giải

Các bài sau sử dụng bảng `member_profiles` đã tạo ở phần 3.

### Bài 1: Dự đoán kết quả biểu thức

Không chạy truy vấn ngay. Hãy tự dự đoán kết quả:

```sql
SELECT
    COALESCE(NULL, 7, 9) AS a,
    COALESCE(0, 7) AS b,
    COALESCE('', 'Hello') AS c,
    COALESCE(NULL, NULL, 'SQL') AS d;
```

**Đáp án:** `a = 7`, `b = 0`, `c = ''` và `d = 'SQL'`. Với PostgreSQL, chuỗi rỗng là giá trị khác `NULL`.

### Bài 2: Hiển thị email ưu tiên

Yêu cầu: với mỗi thành viên, lấy email công việc nếu có; nếu không có, lấy email cá nhân; nếu cả hai đều thiếu, hiển thị `'Chưa liên hệ được'`.

```sql
SELECT
    member_id,
    full_name,
    COALESCE(
        work_email,
        personal_email,
        'Chưa liên hệ được'
    ) AS contact_email
FROM member_profiles
ORDER BY member_id;
```

Với dữ liệu mẫu, kết quả hiển thị theo thứ tự: `an@company.example`, `binh@example.net`, `Chưa liên hệ được`, `Chưa liên hệ được`.

### Bài 3: Sửa lỗi không hiển thị nickname rỗng

Yêu cầu: nếu `nickname` rỗng hoặc chỉ có dấu cách, hãy hiển thị `full_name`.

```sql
SELECT
    member_id,
    COALESCE(
        NULLIF(TRIM(nickname), ''),
        full_name
    ) AS display_name
FROM member_profiles
ORDER BY member_id;
```

**Giải thích:** `TRIM` loại khoảng trắng thừa; `NULLIF(..., '')` đổi chuỗi rỗng thành `NULL`; `COALESCE` chọn tên đầy đủ ở vị trí dự phòng.

### Bài 4: Hai cách tính trung bình khác nhau thế nào?

Chạy truy vấn:

```sql
SELECT
    AVG(discount_percent) AS known_average,
    AVG(COALESCE(discount_percent, 0)) AS zero_filled_average
FROM member_profiles;
```

**Đáp án:** `known_average = 5.00` và `zero_filled_average = 2.50`, vì phép tính thứ nhất chia cho **2 giá trị đã biết**, còn phép tính thứ hai chia cho **4 hàng sau khi thay NULL bằng 0**.

Câu hỏi mở rộng: Trong báo cáo nào nên dùng giá trị thứ hai? Chỉ khi nghiệp vụ **quy định rõ** giảm giá chưa khai báo được tính là 0% trước khi lấy trung bình.

### Bài 5: Đếm số thành viên thiếu email ở cả hai cột

Yêu cầu: chỉ lấy những thành viên có cả `work_email` và `personal_email` là `NULL`.

Cách viết trực tiếp:

```sql
SELECT
    member_id,
    full_name
FROM member_profiles
WHERE work_email IS NULL
  AND personal_email IS NULL
ORDER BY member_id;
```

Một cách khác tương đương cho dữ liệu mẫu:

```sql
SELECT
    member_id,
    full_name
FROM member_profiles
WHERE COALESCE(work_email, personal_email) IS NULL
ORDER BY member_id;
```

Với các cột trên, kết quả là **Lê Chi** và **Phạm Dũng**. Nếu database xem chuỗi rỗng là “không có email” theo quy ước nghiệp vụ, cần chuẩn hóa chuỗi trước khi kiểm tra.

### Bài 6: Phân biệt dữ liệu gốc và giá trị dự phòng

Yêu cầu: hiển thị `0` nếu chưa nhập mức giảm giá, đồng thời có cột `has_discount_value` cho biết mức giảm đã được khai báo hay chưa.

```sql
SELECT
    member_id,
    COALESCE(discount_percent, 0) AS display_discount,
    CASE
        WHEN discount_percent IS NULL THEN FALSE
        ELSE TRUE
    END AS has_discount_value
FROM member_profiles
ORDER BY member_id;
```

Trong PostgreSQL, có thể viết cột trạng thái ngắn gọn:

```sql
SELECT
    member_id,
    COALESCE(discount_percent, 0) AS display_discount,
    discount_percent IS NOT NULL AS has_discount_value
FROM member_profiles
ORDER BY member_id;
```

Hàng Nguyễn An có `display_discount = 0` và `has_discount_value = TRUE`; Trần Bình và Phạm Dũng có `display_discount = 0` nhưng `has_discount_value = FALSE`. Sự khác biệt này rất quan trọng khi lập báo cáo chất lượng dữ liệu.

## 14. Ghi nhớ để dùng COALESCE đúng ngữ nghĩa

| Câu hỏi | Cách viết gợi ý | Lưu ý |
|---|---|---|
| Giá trị đầu tiên khác `NULL` là gì? | `COALESCE(a, b, c)` | Ưu tiên từ trái sang phải |
| Nếu giá trị thiếu thì hiện nhãn gì? | `COALESCE(email, '(chưa có)')` | Chỉ đổi dữ liệu hiển thị |
| Chuỗi rỗng cần được coi là thiếu? | `COALESCE(NULLIF(TRIM(name), ''), fallback)` | Kiểm tra quy ước dữ liệu và DBMS |
| Tổng không có hàng phải hiện 0? | `COALESCE(SUM(amount), 0)` | Đặt bên ngoài phép tổng hợp |
| Tìm những dòng có giá trị thực sự NULL? | `column IS NULL` | Không cần ép về giá trị dự phòng |
| Giữ riêng giá trị không xác định và 0? | Cột gốc + cột hiển thị/trạng thái | Tránh làm mất thông tin |
| Dữ liệu có nhiều loại không tương thích? | `CAST` hoặc tách cột hiển thị | Không giả định DBMS tự ép kiểu như mong muốn |

**`COALESCE` không “xóa NULL” trong cơ sở dữ liệu.** Nó lựa chọn giá trị khác `NULL` để sử dụng trong biểu thức hiện tại. Hãy xác định mục đích của giá trị dự phòng: **để hiển thị dễ hiểu, để tính theo một quy tắc nghiệp vụ hay để chọn dữ liệu ưu tiên**. Chỉ khi ý nghĩa đó rõ ràng, `COALESCE` mới giúp truy vấn vừa ngắn gọn vừa chính xác.

