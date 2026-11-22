# So sánh chuỗi theo hoa thường, dấu và quy tắc đối chiếu

Khi lọc dữ liệu văn bản trong SQL, điều kiện tưởng như đơn giản:

```sql
SELECT id, display_name
FROM customers
WHERE display_name = 'cafe';
```

có thể trả các kết quả khác nhau tùy **hệ quản trị cơ sở dữ liệu (DBMS)**, **kiểu dữ liệu**, **quy tắc đối chiếu (*collation*)** của cột hoặc biểu thức, và đôi khi cả **phiên bản** hoặc **cấu hình**. Trên một cấu hình, `'Cafe'` khác `'cafe'`; trên cấu hình khác, hai chuỗi được xem là bằng nhau. Tương tự, `'cafe'` có thể được coi là bằng `'café'` nếu phép đối chiếu bỏ qua dấu.

Điều này đặc biệt quan trọng với dữ liệu tiếng Việt: tên riêng, địa chỉ, từ khóa tìm kiếm và mã định danh đều chứa chữ hoa/thường và ký tự có dấu. Bài học hướng dẫn cách hiểu ngữ nghĩa so sánh chuỗi trong điều kiện lọc `WHERE`, kiểm soát độ nhạy hoa/thường và dấu, sử dụng `COLLATE`, phân biệt so sánh với tìm kiếm mẫu `LIKE`, và xử lý các khác biệt giữa PostgreSQL, MySQL, SQL Server, SQLite và các DBMS khác.

## 1. Ba câu hỏi phải đặt ra trước khi so sánh chuỗi

Xét các cặp chuỗi:

| Chuỗi thứ nhất | Chuỗi thứ hai | Điểm khác biệt |
| --- | --- | --- |
| `'Cafe'` | `'cafe'` | Chữ hoa/chữ thường |
| `'cafe'` | `'café'` | Dấu trên ký tự |
| `'Hà Nội'` | `'Ha Noi'` | Dấu tiếng Việt |
| `'Hòa'` | `'hòa'` | Hoa/thường |
| `'abc'` | `'abc '` | Khoảng trắng cuối |
| `'é'` dạng U+00E9 | `'e'` + dấu sắc kết hợp U+0301 | Hai cách mã hóa Unicode có thể trông giống nhau |

Trước khi viết điều kiện `=`, `<>`, `LIKE` hoặc `ORDER BY`, hãy xác định:

1. **Có phân biệt hoa và thường không?** Người dùng tìm `'an'` có cần thấy `'An'` hay `'AN'`?
2. **Có phân biệt dấu không?** Tìm `'Ha Noi'` có cần thấy `'Hà Nội'` không?
3. **Quy tắc ngôn ngữ và ký tự nào được áp dụng?** Chuỗi được so sánh như dãy ký tự chính xác, hay theo quy tắc chữ cái của một ngôn ngữ cụ thể?

Không có một câu trả lời duy nhất đúng cho mọi cột. Tên người dùng hiển thị có thể tìm gần đúng; mã giao dịch, token hay một định danh ngoài hệ thống có thể cần đối chiếu nghiêm ngặt.

## 2. Collation là gì?

**Collation (quy tắc đối chiếu)** quy định cách DBMS so sánh hoặc sắp xếp chuỗi ký tự theo bộ quy tắc nhất định. Nó có thể ảnh hưởng đến:

- **Tính bằng nhau:** `'Cafe' = 'cafe'` có được coi là đúng không?
- **Thứ tự sắp xếp:** `ORDER BY name` xếp các chữ có dấu, chữ hoa/thường và ký tự đặc biệt như thế nào?
- **So sánh thứ tự:** `name < 'M'` hoặc `name >= 'N'` được hiểu ra sao?
- **Nhóm/loại trùng và ràng buộc duy nhất:** trong nhiều DBMS, những chuỗi được coi là bằng nhau theo collation cũng tác động đến `DISTINCT`, `GROUP BY` và `UNIQUE`.
- **Một số phép so khớp mẫu:** tùy DBMS, collation hoặc quy tắc riêng của toán tử ảnh hưởng đến `LIKE` và các phép tìm kiếm tương tự.

Collation có thể được gắn ở cấp **database**, **schema**, **cột**, **biểu thức** hoặc **phiên kết nối**, tùy hệ quản trị. Quy tắc áp dụng thực tế có thể là kết quả của nhiều cấp cấu hình.

### 2.1. Phân biệt case-sensitive và case-insensitive

| Thuật ngữ | Viết tắt thường gặp | Ý nghĩa |
| --- | --- | --- |
| **Case-sensitive** | CS | Phân biệt chữ hoa/chữ thường. |
| **Case-insensitive** | CI | Bỏ qua một số khác biệt hoa/thường theo quy tắc collation. |

Ví dụ minh họa:

```text
Case-sensitive:
    'Cafe' = 'cafe'  → FALSE

Case-insensitive:
    'Cafe' = 'cafe'  → TRUE
```

Các ví dụ trên mô tả **ngữ nghĩa mong muốn**. SQL không bảo đảm kết quả này giống nhau trên mọi DBMS nếu không biết collation.

“Không phân biệt hoa/thường” cũng không đơn giản là biến mọi ký tự thành chữ thường theo ASCII. Một số ngôn ngữ có quy tắc đặc biệt như chữ `I`, `i` và `İ` trong tiếng Thổ Nhĩ Kỳ. Kết quả có thể thay đổi theo locale và thuật toán Unicode của collation.

### 2.2. Phân biệt accent-sensitive và accent-insensitive

| Thuật ngữ | Viết tắt thường gặp | Ý nghĩa |
| --- | --- | --- |
| **Accent-sensitive** | AS | Phân biệt dấu/diacritic được collation xem là có ý nghĩa. |
| **Accent-insensitive** | AI | Có thể xem các biến thể khác dấu là tương đương theo quy tắc collation. |

Ví dụ với một collation bỏ qua dấu:

```text
'cafe' = 'café'   → TRUE
'Ha Noi' = 'Hà Nội' → TRUE
```

Nhưng cần thận trọng: **accent-insensitive không có nghĩa mọi chữ cái tiếng Việt đều được thay bằng phiên bản ASCII giống cách gõ không dấu**. Chẳng hạn `'đ'` và `'d'` có thể được xử lý như hai chữ khác nhau trong một số quy tắc ngôn ngữ; sự tương đương phải kiểm chứng với collation cụ thể.

### 2.3. Bốn tổ hợp thường gặp

| Cấu hình ý nghĩa | Hoa/thường | Dấu | Ví dụ |
| --- | --- | --- | --- |
| CS + AS | Phân biệt | Phân biệt | `'Cafe'` khác `'cafe'` và `'café'`. |
| CI + AS | Không phân biệt | Phân biệt | `'Cafe'` bằng `'cafe'`, nhưng khác `'café'`. |
| CS + AI | Phân biệt | Không phân biệt | `'Cafe'` khác `'cafe'`, nhưng có thể bằng `'Café'`. |
| CI + AI | Không phân biệt | Không phân biệt | `'Cafe'`, `'cafe'`, `'Café'` có thể được coi là bằng nhau. |

Đây là **mô hình giải thích**, không phải quy định rằng mọi tên collation ở mọi DBMS đều có đủ bốn biến thể hay so sánh mọi ký tự giống nhau.

## 3. Một ví dụ dữ liệu dùng xuyên suốt

Giả sử có bảng khách hàng:

| id | display_name |
| ---: | --- |
| 1 | Cafe |
| 2 | cafe |
| 3 | Café |
| 4 | CAFÉ |
| 5 | Hà Nội |
| 6 | Ha Noi |
| 7 | Đà Nẵng |
| 8 | Da Nang |
| 9 | `NULL` |

Trên PostgreSQL, có thể tạo bảng thực hành trong database thử nghiệm:

```sql
CREATE TABLE search_demo (
    id INTEGER PRIMARY KEY,
    display_name VARCHAR(100)
);

INSERT INTO search_demo (id, display_name)
VALUES
    (1, 'Cafe'),
    (2, 'cafe'),
    (3, 'Café'),
    (4, 'CAFÉ'),
    (5, 'Hà Nội'),
    (6, 'Ha Noi'),
    (7, 'Đà Nẵng'),
    (8, 'Da Nang'),
    (9, NULL);
```

Các truy vấn sau dùng bảng này làm minh họa. Kết quả của phép so sánh văn bản phải luôn được hiểu **theo collation đang áp dụng**. Khi muốn minh họa hành vi cụ thể, bài sẽ chỉ định collation hoặc điều kiện rõ ràng thay vì ngầm đoán cấu hình mặc định.

## 4. Toán tử = và <> phụ thuộc vào quy tắc so sánh

Câu lọc:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name = 'cafe'
ORDER BY id;
```

không tự nói rõ “có phân biệt hoa, dấu hay không”. DBMS xác định quy tắc từ collation của biểu thức, cột hoặc các thiết lập tương ứng.

Nếu collation phân biệt cả hoa/thường và dấu, dữ liệu mẫu thường chỉ khớp hàng `id = 2`. Nếu collation không phân biệt cả hai, nó có thể khớp `id = 1, 2, 3, 4`.

Tương tự:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name <> 'cafe';
```

cũng phụ thuộc vào collation. Những chuỗi được xem là bằng `'cafe'` theo quy tắc hiện hành sẽ **không** thỏa `<>`. Cột có giá trị `NULL` không được chọn: so sánh `NULL <> 'cafe'` tạo kết quả `UNKNOWN`, không phải `TRUE`.

### 4.1. NULL là một trường hợp độc lập

```sql
-- Không tìm được hàng có display_name NULL bằng cách này.
SELECT *
FROM search_demo
WHERE display_name = NULL;

-- Đúng: tìm hàng thiếu tên.
SELECT *
FROM search_demo
WHERE display_name IS NULL;
```

Collation không biến `NULL` thành một chuỗi rỗng hoặc chuỗi đặc biệt. Việc xét có/không có giá trị phải dùng `IS NULL` hoặc `IS NOT NULL` theo mục đích.

### 4.2. Vì sao so sánh khác tìm kiếm “gần đúng”?

`=` hỏi liệu hai chuỗi **bằng nhau theo phép đối chiếu hiện hành**. Nó không tự sửa lỗi đánh máy, không tự tách từ và không đảm bảo bỏ dấu. Nếu người dùng nhập `'Hanoi'` và dữ liệu lưu `'Hà Nội'` (có khoảng trắng), chỉ bỏ dấu vẫn không giải quyết khác biệt về khoảng trắng.

Tìm kiếm gần đúng có thể cần nhiều bước riêng: chuẩn hóa đầu vào, phân tách từ, full-text search, tìm kiếm n-gram hoặc thuật toán tương tự văn bản. **Collation là một phần của so sánh**, không thay thế toàn bộ hệ thống tìm kiếm.

## 5. Chỉ định COLLATE trong biểu thức SQL

Nhiều DBMS cho phép chọn collation ở cấp biểu thức:

```sql
SELECT ...
FROM ...
WHERE text_column COLLATE some_collation = 'value';
```

Tuy nhiên, **tên collation và nơi đặt cú pháp `COLLATE` khác nhau** giữa PostgreSQL, MySQL và SQL Server. Không thể viết một tên duy nhất chạy trên mọi DBMS.

Collation được chọn trong truy vấn có thể ghi đè hoặc ưu tiên khác với collation mặc định của cột trong phạm vi biểu thức đó, theo quy tắc của DBMS. Điều này không tự thay đổi định nghĩa cột cho những truy vấn khác.

### 5.1. PostgreSQL: phép so sánh phân biệt chính xác theo C collation

Ở PostgreSQL, collation tên `"C"` là một lựa chọn để so sánh/sắp xếp chuỗi theo quy tắc đơn giản, không thực hiện phép đối chiếu bỏ hoa/thường hay bỏ dấu:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE "C" = 'cafe'
ORDER BY id;
```

Với dữ liệu `VARCHAR` ở trên, truy vấn khớp hàng `id = 2`. `'Cafe'` khác `'cafe'`, và `'Café'` khác `'cafe'` trong ví dụ này.

Một phép kiểm tra trực tiếp:

```sql
SELECT
    ('Cafe' COLLATE "C") = 'cafe' AS case_equal,
    ('cafe' COLLATE "C") = 'café' AS accent_equal;
-- case_equal = false
-- accent_equal = false
```

Sử dụng `"C"` để minh họa tính phân biệt ký tự **không đồng nghĩa với bảo đảm tương đương byte trong mọi tình huống**: kiểu dữ liệu (nhất là `CHAR(n)`), khoảng trắng cuối, biểu diễn Unicode và cơ chế chuẩn hóa vẫn cần xét riêng khi nghiệp vụ yêu cầu so khớp tuyệt đối.

### 5.2. PostgreSQL: collation ICU không phân biệt hoa/thường và dấu

PostgreSQL có thể tạo **ICU collation** tùy chỉnh nếu bản cài đặt hỗ trợ ICU. Ví dụ dưới đây dành cho **PostgreSQL 12+ có ICU**, trong môi trường thử nghiệm và với quyền tạo collation phù hợp:

```sql
CREATE COLLATION public.demo_ci_ai (
    provider = icu,
    locale = 'und-u-ks-level1',
    deterministic = false
);
```

Ý nghĩa các lựa chọn:

- `provider = icu`: dùng ICU làm nguồn quy tắc đối chiếu.
- `und-u-ks-level1`: dùng bộ quy tắc Unicode với mức so sánh chính, thường bỏ khác biệt hoa/thường và dấu ở các ví dụ cơ bản.
- `deterministic = false`: cho phép PostgreSQL coi những chuỗi khác byte nhưng tương đương theo quy tắc collation là bằng nhau.

Thử:

```sql
SELECT
    ('Cafe' COLLATE public.demo_ci_ai) = 'cafe'
        AS same_case_insensitive,
    ('cafe' COLLATE public.demo_ci_ai) = 'café'
        AS same_accent_insensitive;
-- Trong cấu hình ICU được mô tả: true, true.
```

Lọc bảng:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE public.demo_ci_ai = 'cafe'
ORDER BY id;
-- Dự kiến: id 1, 2, 3, 4.
```

Đây là **collation ví dụ**. Danh sách locale, khả năng ICU và kết quả với từng ký tự/ngôn ngữ phụ thuộc môi trường. Với tìm kiếm tiếng Việt thực tế, cần thử những cặp quan trọng như `'Đ'`/`'D'`, chữ có dấu kết hợp và cách biểu diễn Unicode trước khi quyết định dùng một collation chung cho toàn hệ thống.

Đặc biệt, PostgreSQL **deterministic collation** thông thường vẫn dùng bước phân biệt chuỗi không đồng nhất ở mức byte khi quyết định bằng nhau; đặt mức ICU chỉ là một phần yêu cầu nếu muốn so khớp không phân biệt dấu/hoa ở phép `=`. Chính vì vậy ví dụ cấu hình `deterministic = false`.

Các thao tác như `LIKE`, pattern matching và một số loại chỉ mục có quy tắc hỗ trợ khác nhau khi kết hợp nondeterministic collation, tùy phiên bản PostgreSQL. Đừng suy ra rằng vì `=` hoạt động theo collation này thì mọi toán tử mẫu đều hỗ trợ giống vậy.

### 5.3. MySQL 8: các hậu tố ai_ci và as_cs

Với dữ liệu kiểu ký tự `utf8mb4` trên **MySQL 8.0**, những tên collation quen thuộc gồm:

- `utf8mb4_0900_ai_ci`: thường **accent-insensitive, case-insensitive**.
- `utf8mb4_0900_as_cs`: thường **accent-sensitive, case-sensitive**.

Ví dụ:

```sql
-- MySQL 8.0, giả sử display_name có character set utf8mb4.
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE utf8mb4_0900_ai_ci = 'cafe'
ORDER BY id;
-- Với dữ liệu ví dụ, có thể khớp Cafe, cafe, Café, CAFÉ.
```

So sánh phân biệt hoa/thường và dấu:

```sql
-- MySQL 8.0, cùng giả định charset utf8mb4.
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE utf8mb4_0900_as_cs = 'cafe'
ORDER BY id;
-- Dự kiến chỉ khớp hàng 'cafe' trong dữ liệu mẫu.
```

**Chú ý:** collation phải phù hợp **character set** của biểu thức. Việc gắn một `utf8mb4` collation vào cột thuộc charset không tương thích có thể gây lỗi. Tên collation `0900` thuộc MySQL 8.0, không nên sao chép nguyên vào MySQL 5.7 hoặc MariaDB rồi mặc định có hỗ trợ.

Muốn kiểm tra collation của cột MySQL hiện tại:

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    character_set_name,
    collation_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'search_demo'
ORDER BY ordinal_position;
```

Các cấu hình mặc định thay đổi theo phiên bản và cách tạo database. Không thể kết luận MySQL luôn bỏ hoa/thường và dấu cho mọi cột chỉ dựa vào tên hệ quản trị.

### 5.4. SQL Server: CI/CS và AI/AS

SQL Server hỗ trợ collation ở cấp cột và biểu thức. Ví dụ dùng tên collation phổ biến:

```sql
-- SQL Server, giả sử bảng dbo.search_demo đã tồn tại.
SELECT id, display_name
FROM dbo.search_demo
WHERE display_name COLLATE Latin1_General_100_CI_AI = N'cafe'
ORDER BY id;
```

`CI_AI` mô tả so sánh **không phân biệt hoa/thường và dấu** theo quy tắc collation này. Tiền tố `N` trong literal `N'cafe'` giúp biểu diễn Unicode dạng `nvarchar` khi cần.

Nếu muốn phân biệt cả hoa/thường và dấu:

```sql
SELECT id, display_name
FROM dbo.search_demo
WHERE display_name COLLATE Latin1_General_100_CS_AS = N'cafe'
ORDER BY id;
```

Tên collation còn có các thành phần như họ ngôn ngữ, phiên bản hoặc thuộc tính bổ sung. Trong SQL Server, nên xem collation ở cấp database/cột khi giải thích kết quả:

```sql
SELECT
    c.name AS column_name,
    c.collation_name
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID(N'dbo.search_demo');
```

Khi `collation_name` của một cột là `NULL`, cột đó có thể không thuộc loại dữ liệu ký tự; không nên áp dụng khái niệm collation như một kiểu dữ liệu cho mọi cột số, ngày hoặc nhị phân.

### 5.5. SQLite: BINARY, NOCASE và RTRIM

SQLite cung cấp một số collation dựng sẵn:

| Collation | Ý nghĩa khái quát |
| --- | --- |
| `BINARY` | So sánh theo chuỗi byte của biểu diễn văn bản, với những quy tắc kiểu dữ liệu cần lưu ý. |
| `NOCASE` | Không phân biệt hoa/thường cho các chữ ASCII cơ bản `A`–`Z`. |
| `RTRIM` | So sánh theo quy tắc bỏ qua khoảng trắng ASCII ở cuối chuỗi. |

Ví dụ:

```sql
-- SQLite:
SELECT
    'Cafe' = 'cafe' COLLATE BINARY AS exact_compare,
    'Cafe' = 'cafe' COLLATE NOCASE AS ascii_case_compare,
    'Á' = 'á' COLLATE NOCASE AS unicode_case_compare;
-- Trong SQLite mặc định: 0, 1, 0.
```

`NOCASE` **không phải cơ chế so khớp Unicode toàn diện**; nó không tự bỏ dấu tiếng Việt và không mặc định gấp chữ hoa/thường cho mọi ký tự Unicode ngoài ASCII. Nếu cần xử lý tiếng Việt toàn diện trong SQLite, có thể phải dùng ICU extension, collation tùy biến hoặc một khóa tìm kiếm chuẩn hóa do ứng dụng tạo. Mỗi lựa chọn cần kiểm tra quy tắc thực tế.

Một điểm riêng của SQLite: `LIKE` có cơ chế đối chiếu riêng, mặc định thường không phân biệt hoa/thường ASCII, và **không chỉ đơn giản tuân theo `COLLATE NOCASE` hoặc `COLLATE BINARY`**. Cần phân biệt hành vi `=` với `LIKE`.

## 6. Dùng LOWER/UPPER để so sánh không phân biệt hoa thường

Khi muốn chủ động so sánh không phân biệt hoa/thường, cách thường gặp là chuyển **hai bên về cùng dạng chữ**:

```sql
SELECT id, display_name
FROM search_demo
WHERE LOWER(display_name) = LOWER('CAFE')
ORDER BY id;
```

Trong môi trường có quy tắc so sánh phân biệt dấu ở kết quả sau `LOWER`, ví dụ này tìm `Cafe` và `cafe`; `Café` và `CAFÉ` vẫn khác `cafe` vì dấu không tự biến mất.

### 6.1. LOWER không đồng nghĩa bỏ dấu

| Giá trị đầu vào | Kết quả ý tưởng của LOWER | Có tự bỏ dấu không? |
| --- | --- | --- |
| `Cafe` | `cafe` | Không cần bỏ dấu. |
| `CAFÉ` | `café` | Không. |
| `HÀ NỘI` | `hà nội` | Không. |
| `ĐÀ NẴNG` | `đà nẵng` | Không. |

Cách biến đổi thực tế của `LOWER` còn phụ thuộc hệ quản trị, locale và thư viện Unicode, đặc biệt với ký tự ngoài ASCII.

Không được coi `LOWER(name) = LOWER(?)` là giải pháp đầy đủ cho mọi quy tắc ngôn ngữ. Nó có thể không giải quyết ký tự ghép Unicode, biến thể chữ đặc biệt hoặc nhu cầu bỏ dấu.

### 6.2. Nếu cần bỏ dấu: xử lý riêng

Trên PostgreSQL, extension `unaccent` cung cấp hàm chuyển đổi có thể hỗ trợ bỏ nhiều dấu chữ Latin. Việc dùng extension cần quyền và cấu hình phù hợp:

```sql
-- PostgreSQL, trong database thử nghiệm nếu có quyền:
CREATE EXTENSION IF NOT EXISTS unaccent;

SELECT
    LOWER(unaccent('Café')) AS normalized_one,
    LOWER(unaccent('CAFE')) AS normalized_two;
-- Với mapping mặc định thông dụng: cafe, cafe.
```

Có thể dùng trong điều kiện:

```sql
SELECT id, display_name
FROM search_demo
WHERE LOWER(unaccent(display_name)) = LOWER(unaccent('cafe'))
ORDER BY id;
```

Đây là **chiến lược chuyển đổi chuỗi để tìm kiếm**, không phải định nghĩa một collation. `unaccent` dùng bảng quy tắc của extension và không được bảo đảm tái hiện mọi cách phiên âm tiếng Việt mong muốn, đặc biệt với các ký tự có vai trò riêng trong ngôn ngữ. Nếu dùng trong production, phải hiểu quy tắc và kiểm tra dữ liệu thực.

### 6.3. Không ép mọi phép so sánh về LOWER

Cách viết `LOWER(column) = LOWER(?)` có thể khiến DBMS **không dùng được chỉ mục B-tree thông thường trên cột thô** cho cùng điều kiện, hoặc cần chỉ mục trên biểu thức đã biến đổi.

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_search_demo_lower_name
ON search_demo (LOWER(display_name));
```

Sau đó câu truy vấn:

```sql
SELECT id, display_name
FROM search_demo
WHERE LOWER(display_name) = LOWER('CAFE');
```

có thể được bộ tối ưu xem xét chỉ mục biểu thức nếu thống kê và điều kiện phù hợp. Không có bảo đảm rằng nó sẽ **luôn** dùng chỉ mục; bảng nhỏ có thể vẫn được quét trực tiếp.

Nếu nghiệp vụ cần tìm kiếm không phân biệt dấu và hoa/thường thường xuyên, hãy cân nhắc **collation phù hợp hoặc cột/biểu thức khóa tìm kiếm được chuẩn hóa** với cơ chế tạo và lập chỉ mục nhất quán, thay vì viết nhiều hàm khác nhau trong mọi truy vấn.

## 7. LIKE, ILIKE và tìm kiếm mẫu dưới ảnh hưởng của collation

Toán tử `=` so sánh **toàn bộ chuỗi** theo ngữ nghĩa tương ứng; `LIKE` kiểm tra **mẫu** có ký tự đại diện:

- `%`: khớp với chuỗi con có độ dài từ 0 trở lên.
- `_`: khớp với một đơn vị ký tự theo ngữ nghĩa của DBMS.

Ví dụ:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name LIKE 'Ca%';
```

Liệu truy vấn có tìm `Cafe`, `cafe`, `Café` hay `CAFÉ` phụ thuộc **quy tắc đối chiếu của toán tử và DBMS**. Không có một quy luật duy nhất áp dụng cho mọi phương ngữ.

### 7.1. PostgreSQL: LIKE và ILIKE

PostgreSQL có hai toán tử thường được dùng:

- `LIKE`: so khớp mẫu với xử lý hoa/thường theo ngữ nghĩa của DBMS và collation.
- `ILIKE`: mở rộng riêng của PostgreSQL để so khớp mẫu không phân biệt hoa/thường theo locale đang áp dụng.

Ví dụ:

```sql
-- PostgreSQL, với collation thông thường phân biệt dấu:
SELECT id, display_name
FROM search_demo
WHERE display_name ILIKE 'caf%'
ORDER BY id;
```

Mẫu `'caf%'` yêu cầu bắt đầu bằng các ký tự tương ứng `c`, `a`, `f` và cho phép các ký tự sau đó, nên ví dụ có thể khớp cả `Cafe`, `cafe`, `Café` và `CAFÉ`. Ký tự có dấu `é` ở cuối nằm trong phần `%`, không phải là bằng chứng `ILIKE` đã **bỏ dấu**.

Hãy thử một mẫu buộc so khớp đầy đủ chữ `e`:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name ILIKE 'cafe'
ORDER BY id;
```

Trong các collation thông thường phân biệt dấu, `Café` không khớp mẫu `cafe`. **ILIKE chủ yếu phục vụ bỏ qua hoa/thường, không mặc định thay thế accent-insensitive collation.**

Lưu ý: các pattern operator có thể có giới hạn riêng khi gặp nondeterministic ICU collation, tùy phiên bản PostgreSQL. Nếu đã tạo collation `demo_ci_ai` ở mục 5.2, không tự suy ra rằng mọi phép `LIKE`/`ILIKE` cũng hỗ trợ và trả cùng tập khớp như `=`.

### 7.2. MySQL và SQL Server: LIKE thường xét collation

Trong MySQL và SQL Server, `LIKE` thường chịu ảnh hưởng rõ từ collation của biểu thức ký tự. Ví dụ một collation `CI_AI` có thể khiến:

```sql
-- SQL Server; ví dụ minh họa với cột NVARCHAR.
SELECT id, display_name
FROM dbo.search_demo
WHERE display_name COLLATE Latin1_General_100_CI_AI LIKE N'cafe%';
```

khớp các biến thể hoa/thường và dấu được collation đó coi là tương đương trong phần mẫu `cafe`.

Cần nhớ `LIKE` vẫn là **so khớp mẫu**: ký tự `%` và `_` có ý nghĩa đặc biệt, không phải ký tự văn bản thông thường trừ khi được escape theo cú pháp DBMS.

### 7.3. SQLite: LIKE có quy tắc riêng

Trong SQLite mặc định:

```sql
SELECT
    'Cafe' LIKE 'cafe' AS ascii_case_match,
    'Café' LIKE 'café' AS unicode_case_match;
```

`LIKE` thường không phân biệt hoa/thường trong ASCII, nhưng không thực hiện case folding đầy đủ cho mọi Unicode như chữ có dấu. Điều này có thể khác `=` với một collation cụ thể. Khi dùng ICU extension hoặc thay thế hàm `LIKE`, hành vi có thể thay đổi.

### 7.4. Mẫu bắt đầu bằng % có thể tốn kém

`LIKE 'caf%'` đôi khi có thể được tối ưu với chỉ mục phù hợp; còn `LIKE '%caf%'` thường khó tận dụng chỉ mục B-tree thông thường vì mẫu không có tiền tố cố định.

Với tìm kiếm substring trên dữ liệu lớn, có thể cân nhắc cơ chế riêng như chỉ mục trigram của PostgreSQL (`pg_trgm`), full-text search hoặc công cụ tìm kiếm chuyên dụng. Việc **bỏ dấu/hoa thường** và việc **tìm chuỗi con nhanh** là hai quyết định thiết kế khác nhau.

## 8. Unicode: chuỗi nhìn giống chưa chắc giống nhau

Unicode cho phép một số ký tự có **nhiều cách biểu diễn**. Ví dụ chữ `é` có thể được mã hóa dưới dạng:

- **NFC/composed:** một code point `U+00E9`.
- **Decomposed:** hai code point `U+0065` (chữ `e`) và `U+0301` (dấu sắc kết hợp).

Khi hiển thị, hai chuỗi thường trông giống nhau:

```text
NFC:  U+00E9
NFD:  U+0065 U+0301
```

Nhưng các dãy code point và byte UTF-8 **khác nhau**. Một phép so sánh nhị phân/phân biệt chính xác có thể coi chúng khác nhau. Một số quy tắc Unicode collation có thể coi chúng tương đương về ngữ nghĩa, nhưng mức độ và điều kiện hỗ trợ khác nhau giữa DBMS.

### 8.1. Chuẩn hóa Unicode là gì?

Những dạng chuẩn hóa thường gặp:

| Dạng | Ý nghĩa khái quát |
| --- | --- |
| **NFC** | Dạng hợp thành chuẩn tắc khi có thể. |
| **NFD** | Dạng phân tách chuẩn tắc. |
| **NFKC** | Dạng hợp thành tương thích, có thể thay đổi một số khác biệt mang ý nghĩa biểu diễn. |
| **NFKD** | Dạng phân tách tương thích. |

Nếu hệ thống cần so khớp chuỗi nhập từ nhiều nguồn, có thể chọn một quy ước chuẩn hóa Unicode **khi ghi hoặc khi tạo khóa tìm kiếm**.

**Không nên tự động dùng NFKC/NFKD cho mọi dữ liệu** nếu những biến thể tương thích có ý nghĩa nghiệp vụ. Tương tự, chuẩn hóa Unicode **không đồng nghĩa bỏ dấu**; mục đích của NFC/NFD là đưa các biểu diễn tương đương về hình thức nhất quán, không biến `'café'` thành `'cafe'`.

### 8.2. Ví dụ kiểm tra mã ký tự trong Java

Với ứng dụng Java, có thể chủ động chuẩn hóa trước khi tạo khóa tìm kiếm:

```java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKeyExample {
    public static String canonicalKey(String input) {
        if (input == null) {
            return null;
        }
        return Normalizer.normalize(input, Normalizer.Form.NFC)
                         .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String composed = "\u00E9";     // é: U+00E9
        String decomposed = "e\u0301"; // e + combining acute accent

        System.out.println(composed.equals(decomposed));
        // false

        System.out.println(
            canonicalKey(composed).equals(canonicalKey(decomposed))
        );
        // true
    }
}
```

`Locale.ROOT` giúp tránh dùng ngẫu nhiên locale mặc định của máy khi tạo khóa quy ước đơn giản; nó **không cung cấp mọi quy tắc so sánh ngôn ngữ**. Ví dụ trên chuẩn hóa hai cách mã hóa của cùng chữ `é`, **không bỏ dấu**, nên `'é'` và `'e'` vẫn không trở thành cùng khóa.

Nếu muốn hỗ trợ tìm kiếm không dấu, cần thêm chính sách riêng: quy tắc ICU, `unaccent`, hoặc bộ chuyển đổi được xác định rõ và kiểm chứng với tiếng Việt.

## 9. So sánh với sắp xếp: ORDER BY chịu ảnh hưởng của collation

`COLLATE` không chỉ tác động đến `WHERE`. Nó có thể thay đổi cả **thứ tự** khi dùng `ORDER BY`:

```sql
-- PostgreSQL:
SELECT id, display_name
FROM search_demo
WHERE display_name IS NOT NULL
ORDER BY display_name COLLATE "C", id;
```

Một collation dựa trên ngôn ngữ có thể sắp `a`, `á`, `à` và `A` gần nhau, trong khi collation `"C"` thường theo thứ tự giá trị byte và cho kết quả khác trực giác từ điển.

Đối với dữ liệu tiếng Việt, thứ tự mong muốn có thể dựa trên quy tắc sắp xếp tiếng Việt của ICU hoặc hệ thống nghiệp vụ. Đừng dùng kết quả `ORDER BY` từ một máy chủ cấu hình theo ngôn ngữ khác rồi kết luận đó là thứ tự chuẩn cho tên người Việt.

### 9.1. So sánh bằng nhau và thứ tự không phải luôn một chuyện

Một collation có thể coi hai chuỗi bằng nhau theo một mức phân biệt, hoặc có quy tắc tiebreak riêng khi sắp xếp. Hành vi chính xác phụ thuộc DBMS và việc collation có deterministic hay không.

Khi sắp theo một cột có nhiều giá trị tương đương theo collation, thêm khóa định danh làm tiêu chí phụ:

```sql
SELECT id, display_name
FROM search_demo
ORDER BY display_name, id;
```

Cách này xác định một thứ tự phụ cho các hàng đồng hạng ở `display_name`, rất quan trọng khi phân trang. Quy tắc vị trí của `NULL` cũng khác giữa các DBMS; muốn ổn định, hãy chỉ định tường minh theo cú pháp được hỗ trợ.

### 9.2. Các toán tử lớn/nhỏ hơn cũng dùng quy tắc đối chiếu

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name >= 'M'
ORDER BY display_name;
```

Điều kiện không thể được hiểu đơn giản như so sánh giá trị byte của ký tự đầu nếu collation mang quy tắc ngôn ngữ. Khi sử dụng phạm vi chuỗi trong phân trang hoặc phân loại chữ cái, cần xác định chính xác collation.

## 10. DISTINCT, GROUP BY và UNIQUE có thể thay đổi theo collation

Một vấn đề dễ bị bỏ sót: lựa chọn collation không chỉ làm “tìm được nhiều kết quả hơn”; nó có thể làm thay đổi **khái niệm trùng nhau** của chuỗi.

### 10.1. DISTINCT

```sql
SELECT DISTINCT display_name
FROM search_demo;
```

Nếu phép bằng nhau theo collation hiện hành coi `'Cafe'`, `'cafe'` và `'Café'` là tương đương, kết quả `DISTINCT` có thể gộp các hàng này lại. Với collation phân biệt hoa/thường và dấu, chúng có thể là ba giá trị khác nhau.

Khi áp dụng collation cụ thể trên PostgreSQL:

```sql
SELECT DISTINCT display_name COLLATE public.demo_ci_ai AS name_group
FROM search_demo
WHERE display_name IS NOT NULL;
```

truy vấn có thể nhóm các chuỗi tương đương theo `demo_ci_ai` đã tạo. **Giá trị văn bản đại diện nào được hiển thị khi các biểu diễn khác nhau bị gộp không nên dùng làm thông tin định danh ổn định** nếu không có quy tắc chọn riêng.

### 10.2. GROUP BY

```sql
SELECT display_name, COUNT(*) AS occurrences
FROM search_demo
GROUP BY display_name
ORDER BY display_name;
```

Tùy collation, các biến thể chữ hoa/thường và dấu có thể chung một nhóm hoặc nằm ở nhóm khác. Nếu báo cáo thống kê theo tên chuẩn hóa, phải nêu rõ **quy tắc nhóm**. Ví dụ “đếm mọi cách viết Cafe/Café như một mục” là quyết định nghiệp vụ chứ không tự phát sinh từ cú pháp `GROUP BY`.

### 10.3. UNIQUE và định danh

Giả sử bảng tài khoản có ràng buộc:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);
```

Nếu collation dùng để kiểm tra tính duy nhất xem `'Alice'` và `'alice'` là bằng nhau, DBMS có thể từ chối chèn hai giá trị này như hai username khác nhau. Với collation phân biệt hoa/thường, hai giá trị có thể được chấp nhận.

Điều này phải được quyết định **trước khi thiết kế UNIQUE**:

- Username có phân biệt hoa/thường không?
- Email có cần áp dụng quy tắc ứng dụng riêng không?
- Có cho phép tên hiển thị trùng nhau dù khác dấu không?
- Nếu quy tắc bị đổi, những bản ghi đang tồn tại có trở thành trùng khóa không?

**Không nên dùng collations bỏ dấu cho mọi mã định danh.** Hai tên tiếng Việt khác nhau có thể bị coi là trùng về mặt kỹ thuật nếu quy tắc bỏ dấu quá rộng. Với token, mã giao dịch, chữ ký hay khóa có yêu cầu khớp ký tự nghiêm ngặt, cần chính sách so sánh phù hợp với định dạng định danh, không mặc định theo quy tắc ngôn ngữ.

## 11. Khoảng trắng, CHAR và các khác biệt ngoài hoa/dấu

Collation không phải yếu tố duy nhất quyết định phép so sánh chuỗi.

### 11.1. Khoảng trắng đầu/cuối

Ví dụ:

```text
'abc'
'abc '
' abc'
```

Các giá trị khác nhau về khoảng trắng. Tuy nhiên, một số DBMS và collation có quy tắc **padding/trailing-space** khiến `'abc'` và `'abc '` được coi là bằng nhau trong một số phép so sánh; những hệ khác có thể phân biệt.

Cần kiểm tra theo **kiểu dữ liệu** `CHAR(n)`, `VARCHAR(n)`, kiểu Unicode, collation và phép toán cụ thể. `CHAR(n)` thường có hành vi đệm khoảng trắng đáng chú ý.

Nếu nghiệp vụ muốn bỏ khoảng trắng đầu/cuối, có thể áp dụng `TRIM` có chủ đích:

```sql
SELECT id, display_name
FROM search_demo
WHERE TRIM(display_name) = 'cafe';
```

`TRIM` không thay thế collation, không tự bỏ dấu và không bảo đảm loại mọi loại khoảng trắng Unicode đặc biệt. Việc chỉnh dữ liệu thường xuyên cũng cần chuẩn hóa nhất quán khi ghi.

### 11.2. Dấu câu và các ký tự đặc biệt

Một số collation có mức phân biệt khác nhau cho dấu câu, ký tự khoảng trắng, độ rộng ký tự (*width sensitivity*) hoặc ký tự Kana, tùy ngôn ngữ/DBMS.

Ví dụ `'co-op'` và `'coop'` có thể được sắp xếp gần nhau hoặc chịu quy tắc dấu câu riêng; không thể suy ra quan hệ bằng nhau chỉ từ nhãn `CI_AI` mà không xem chi tiết collation.

### 11.3. Độ dài và kiểu dữ liệu

Một chuỗi `VARCHAR`, `NVARCHAR`, `CHAR` hay dữ liệu nhị phân có thể được so sánh khác nhau. Khi điều kiện cần đảm bảo **chính xác từng byte**, nên xem xét kiểu nhị phân, mã hóa, độ dài và dữ liệu chuẩn hóa thay vì chỉ thêm một collation “binary” rồi cho rằng mọi đặc tính SQL về padding hoặc kiểu dữ liệu đã biến mất.

## 12. Tác động đến chỉ mục và hiệu năng truy vấn

Ví dụ cột có chỉ mục:

```sql
-- PostgreSQL: chỉ mục thông thường trên cột.
CREATE INDEX idx_search_demo_name
ON search_demo (display_name);
```

Điều kiện dùng chính cột và phép so sánh phù hợp với thứ tự của index có thể được tối ưu tốt:

```sql
SELECT id
FROM search_demo
WHERE display_name = 'cafe';
```

Nhưng nếu truy vấn đổi thành:

```sql
SELECT id
FROM search_demo
WHERE LOWER(display_name) = LOWER('cafe');
```

thì chỉ mục trên **giá trị gốc** không nhất thiết hỗ trợ trực tiếp cho biểu thức `LOWER(display_name)`. PostgreSQL có thể dùng chỉ mục biểu thức như đã trình bày ở mục 6.3.

Tương tự, nếu thay đổi collation ngay trong `WHERE`:

```sql
-- PostgreSQL với collation demo_ci_ai đã tạo:
SELECT id
FROM search_demo
WHERE display_name COLLATE public.demo_ci_ai = 'cafe';
```

DBMS có thể cần một **index tương ứng với collation** mới để hỗ trợ truy vấn hiệu quả. Không nên giả định chỉ mục trên collation mặc định sẽ cho cùng khả năng tối ưu với một phép đối chiếu tùy chỉnh.

### 12.1. Chỉ mục theo collation

Với PostgreSQL, có thể khai báo collation cho khóa chỉ mục:

```sql
CREATE INDEX idx_search_demo_name_ci_ai
ON search_demo (display_name COLLATE public.demo_ci_ai);
```

Điều này hữu ích khi ứng dụng thường xuyên lọc theo quy tắc tương ứng. Dẫu vậy, loại toán tử, hỗ trợ của phiên bản PostgreSQL và mức độ chọn lọc của dữ liệu sẽ quyết định kế hoạch thực thi thực tế.

### 12.2. Khi nào nên có cột tìm kiếm riêng?

Nếu người dùng thường tìm tên tiếng Việt theo nhiều biến thể, mô hình có thể gồm:

```text
display_name      = "Hà Nội"     (giữ nguyên để hiển thị)
search_name_key   = "ha noi"     (khóa tìm kiếm do ứng dụng chuẩn hóa)
```

Các bước tạo khóa có thể gồm NFC, chuyển hoa/thường, quy tắc xử lý dấu và khoảng trắng được xác định rõ. Cần đảm bảo:

1. Khóa được tạo **đồng nhất** khi ghi/sửa dữ liệu.
2. Từ khóa truy vấn cũng đi qua **đúng cùng quy tắc**.
3. Cột khóa có chỉ mục phù hợp với kiểu tìm kiếm.
4. Nếu bộ quy tắc thay đổi, hệ thống có chiến lược xây lại khóa tìm kiếm.

Không nên dùng khóa tìm kiếm đã bỏ dấu để thay thế giá trị hiển thị hoặc làm định danh duy nhất nếu dữ liệu gốc cần phân biệt những tên khác nhau.

### 12.3. Chọn tối ưu sau khi xác định đúng ngữ nghĩa

Đừng đổi từ so sánh phân biệt dấu sang bỏ dấu chỉ vì thấy truy vấn chạy nhanh hơn, và cũng đừng thêm `LOWER`/`unaccent` khi chưa biết nhu cầu nghiệp vụ. Chọn **đúng ý nghĩa so sánh trước**, rồi đánh giá chỉ mục và kế hoạch thực thi sau.

Trên PostgreSQL có thể kiểm tra bằng `EXPLAIN` trong môi trường được phép; trên SQL Server/MySQL có công cụ execution plan tương ứng. Cần xét dữ liệu thực, collation, điều kiện lọc và thống kê khi đánh giá hiệu năng.

## 13. Cách tra cứu collation đang áp dụng

Khi một điều kiện `=` hoặc `LIKE` cho kết quả bất ngờ, hãy tìm **collation của cột và cấu hình database**, không chỉ nhìn câu lệnh.

### 13.1. MySQL: INFORMATION_SCHEMA.COLUMNS

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    character_set_name,
    collation_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'search_demo';
```

Có thể kiểm tra danh sách collation MySQL hiện hỗ trợ:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

### 13.2. PostgreSQL: INFORMATION_SCHEMA và catalog

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    collation_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'search_demo';
```

Trong PostgreSQL, cột `collation_name` của `information_schema.columns` có thể là `NULL` khi cột đang dùng **collation mặc định**. Vì vậy, `NULL` ở đây không có nghĩa “cột không tham gia quy tắc đối chiếu”.

Muốn xem các collation hiện có trên PostgreSQL:

```sql
SELECT
    collname,
    collprovider,
    collisdeterministic
FROM pg_catalog.pg_collation
ORDER BY collname;
```

`pg_catalog` là giao diện riêng của PostgreSQL, không phải SQL portable. Những giá trị metadata cụ thể và các cột được hỗ trợ phụ thuộc phiên bản DBMS.

### 13.3. SQL Server: sys.columns

```sql
SELECT
    c.name AS column_name,
    c.collation_name
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID(N'dbo.search_demo');
```

Ở SQL Server, có thể kiểm tra collation của database hiện tại:

```sql
SELECT DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS database_collation;
```

Khi so sánh hai cột có collation khác nhau, SQL Server có thể yêu cầu chỉ định `COLLATE` rõ ràng để giải quyết xung đột collation. Cần dùng quy tắc phù hợp với nghiệp vụ thay vì ép cả hai sang một collation tùy tiện chỉ để hết lỗi.

### 13.4. SQLite

SQLite không có giao diện `INFORMATION_SCHEMA` tương đương PostgreSQL/MySQL. Collation có thể được khai báo trong định nghĩa cột hoặc áp dụng trong biểu thức, và cũng có thể có collation do ứng dụng đăng ký. Khi đọc schema, có thể xem:

```sql
-- SQLite:
SELECT name, sql
FROM sqlite_schema
WHERE type = 'table'
  AND name = 'search_demo';
```

Không được suy luận rằng SQLite có khả năng so sánh tiếng Việt toàn diện từ tên `NOCASE`; hành vi Unicode cần thử với chính cấu hình hoặc extension đang dùng.

## 14. Thiết kế theo nhu cầu thực tế

### 14.1. Tên hiển thị

**Mục tiêu:** lưu nguyên cách viết `'Nguyễn Văn An'`, cho phép người dùng nhập `'nguyễn'` mà vẫn tìm thấy.

Có thể dùng:

- Collation/công cụ tìm kiếm thích hợp với tiếng Việt.
- Trường tìm kiếm chuẩn hóa theo quy tắc thống nhất.
- `LOWER` để xử lý hoa/thường nếu điều đó đáp ứng đủ yêu cầu.

Không nên sửa giá trị hiển thị thành chữ thường hoặc không dấu chỉ để tìm kiếm dễ hơn. Giá trị hiển thị và khóa tìm kiếm có thể có mục đích khác nhau.

### 14.2. Tìm địa chỉ không dấu

**Mục tiêu:** tìm `'Hà Nội'` khi nhập `'Ha Noi'`.

Chỉ dùng `LOWER` là chưa đủ, vì `'Hà'` và `'Ha'` khác nhau về dấu. Cần accent-insensitive collation phù hợp hoặc quy tắc bỏ dấu có kiểm soát.

Hãy thử thêm cặp `'Đà Nẵng'` / `'Da Nang'`, vì các collation có thể xử lý chữ `Đ/đ` khác với dấu thanh và dấu mũ. Không nên hứa rằng một cấu hình bỏ dấu sẽ tự chuyển mọi chuỗi tiếng Việt thành chữ ASCII người dùng mong đợi.

### 14.3. Mã định danh và token

**Mục tiêu:** so khớp một mã ngoài hệ thống yêu cầu chính xác.

Nên xác định bộ ký tự được phép, chuẩn hóa nếu giao thức yêu cầu, kiểu dữ liệu, độ dài và cách so sánh chính xác. Accent-insensitive/case-insensitive collation có thể làm hai mã vốn khác nhau trở thành tương đương ngoài ý muốn.

Ví dụ mã `'Ab12'` và `'ab12'` có thể là hai mã khác nhau theo hợp đồng tích hợp; khi ấy áp dụng collation CI cho cột chứa mã có thể phá vỡ quy tắc định danh.

### 14.4. Email và username

Không có một câu trả lời đúng cho mọi hệ thống:

- Username có thể được thiết kế không phân biệt hoa/thường.
- Email có các quy tắc tên miền, hộp thư và chính sách sản phẩm riêng; không nên mặc nhiên biến mọi địa chỉ thành cùng một dạng rồi cho rằng luôn tương đương về mặt định danh.
- Tên đăng nhập không phân biệt dấu có thể tiện cho người dùng nhưng cũng có nguy cơ gộp tên khác nhau.

Cần thiết kế quy tắc chuẩn hóa và **ràng buộc duy nhất** song hành; chỉ điều kiện truy vấn `WHERE LOWER(...)` không đủ để ngăn trùng ở thời điểm ghi.

### 14.5. Tìm kiếm và phân trang

Nếu cho người dùng sắp theo tên, áp dụng collation phù hợp ngôn ngữ của đối tượng, và dùng khóa phụ ổn định khi phân trang:

```sql
SELECT id, display_name
FROM search_demo
ORDER BY display_name, id;
```

Nếu cần mỗi người dùng có thứ tự sắp xếp theo ngôn ngữ riêng, hệ thống cần xem khả năng collation theo truy vấn/locale và chi phí chỉ mục. Không nên kỳ vọng một chỉ mục được xây theo mọi quy tắc đối chiếu khác nhau cùng lúc.

## 15. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng `=` luôn phân biệt hoa/thường | Kết quả phụ thuộc collation | Xác định collation cột/biểu thức. |
| Cho rằng `LOWER` tự bỏ dấu | `LOWER` chủ yếu chuyển hoa/thường | Dùng quy tắc bỏ dấu riêng nếu thực sự cần. |
| Cho rằng `ILIKE` luôn bỏ dấu | PostgreSQL `ILIKE` phục vụ case-insensitive pattern matching | Phân biệt chữ hoa/thường và dấu khi thiết kế truy vấn. |
| Dùng SQLite `NOCASE` cho mọi chữ Unicode | `NOCASE` mặc định chủ yếu xử lý ASCII | Cân nhắc ICU/custom collation hoặc search key. |
| Sao chép tên `utf8mb4_0900_ai_ci` sang DBMS khác | Tên collation là đặc thù MySQL 8 | Dùng collation do DBMS mục tiêu hỗ trợ. |
| So chuỗi Unicode nhìn giống nhưng mã hóa khác | NFC/NFD có thể khác code point | Chọn quy tắc chuẩn hóa nếu nghiệp vụ yêu cầu. |
| Bỏ qua `NULL` | `NULL = 'abc'` là `UNKNOWN` | Dùng `IS NULL` hoặc `IS NOT NULL`. |
| Dùng collation bỏ dấu cho mã định danh | Có thể gộp hai mã khác nhau | Dùng chính sách so sánh nghiêm ngặt phù hợp. |
| Thêm `LOWER(column)` rồi giả định index cũ vẫn tối ưu | Biểu thức thay đổi khóa tìm kiếm | Dùng index biểu thức/collation phù hợp và xem plan. |
| Dùng `LIKE '%term%'` cho bảng lớn mà không kiểm tra | Pattern thiếu tiền tố thường khó dùng B-tree | Cân nhắc trigram/full-text search. |
| Đổi collation của cột đang có UNIQUE mà không kiểm tra dữ liệu | Các chuỗi trước đây khác nhau có thể trở thành tương đương | Khảo sát dữ liệu và xung đột trước migration. |

## 16. Bài tập thực hành

Các câu lệnh thực hành dưới đây sử dụng bảng `search_demo` ở mục 3 trên PostgreSQL. Những phần dùng ICU hoặc extension cần môi trường PostgreSQL hỗ trợ tính năng và quyền tương ứng.

### Bài 1. Lọc chính xác chữ và dấu

**Yêu cầu:** Chỉ chọn hàng có `display_name` bằng đúng `'cafe'` theo quy tắc `"C"`.

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE "C" = 'cafe'
ORDER BY id;
```

**Kết quả dự kiến:** `id = 2`.

### Bài 2. Bỏ qua hoa/thường nhưng chưa bỏ dấu

**Yêu cầu:** Tìm `Cafe` và `cafe` bằng cách dùng `LOWER`.

```sql
SELECT id, display_name
FROM search_demo
WHERE LOWER(display_name) = LOWER('CAFE')
ORDER BY id;
```

**Trong môi trường so sánh thông thường phân biệt dấu:** `id = 1, 2`. Hàng `Café` vẫn khác vì dấu sắc không bị xóa.

### Bài 3. Tìm cả biến thể có dấu với ICU collation

Sau khi tạo `public.demo_ci_ai` như mục 5.2:

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name COLLATE public.demo_ci_ai = 'cafe'
ORDER BY id;
```

**Kết quả dự kiến:** `id = 1, 2, 3, 4` đối với các chuỗi của dữ liệu mẫu trên cấu hình ICU đã mô tả.

**Câu hỏi:** Có nên dùng collation này để kiểm tra mã token bí mật? **Không nên** nếu giao thức yêu cầu phân biệt chính xác ký tự.

### Bài 4. Tìm tên bắt đầu bằng “caf”, không phân biệt hoa/thường

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name ILIKE 'caf%'
ORDER BY id;
```

**Trong PostgreSQL với collation thông thường:** các tên `Cafe`, `cafe`, `Café` và `CAFÉ` đều có thể khớp, bởi vì phần ký tự có dấu nằm sau chuỗi `caf` và được `%` chấp nhận.

**Câu hỏi:** Kết quả có chứng minh `ILIKE` bỏ dấu không? **Không.** Thử thêm mẫu `'cafe'` không có `%` để thấy khác biệt.

### Bài 5. Tìm những giá trị bị thiếu

```sql
SELECT id, display_name
FROM search_demo
WHERE display_name IS NULL;
```

**Kết quả dự kiến:** `id = 9`. Collation không ảnh hưởng đến ý nghĩa của `IS NULL`.

### Bài 6. Phân biệt số hàng với số nhóm

```sql
-- Số hàng có tên không NULL:
SELECT COUNT(*) AS total_named
FROM search_demo
WHERE display_name IS NOT NULL;

-- Số nhóm sau khi áp dụng collation demo_ci_ai:
SELECT COUNT(*) AS number_of_groups
FROM (
    SELECT DISTINCT display_name COLLATE public.demo_ci_ai AS value
    FROM search_demo
    WHERE display_name IS NOT NULL
) AS distinct_names;
```

**Câu hỏi:** Vì sao số nhóm có thể nhỏ hơn số hàng? Vì collation có thể xem nhiều chuỗi khác nhau về hoa/dấu là tương đương. Không nên suy luận số nhóm chính xác cho tất cả tên tiếng Việt trước khi kiểm tra quy tắc ICU của môi trường đang dùng.

### Bài 7. Thử Unicode NFC/NFD

Trong Java, tạo hai chuỗi `"\u00E9"` và `"e\u0301"`. Dùng `String.equals` so sánh trước và sau `Normalizer.normalize(..., NFC)`.

**Kết quả dự kiến:** trước chuẩn hóa, hai chuỗi khác nhau ở mức mã ký tự; sau NFC, chúng có cùng biểu diễn trong ví dụ. Việc đó **không** biến `é` thành `e`.

### Bài 8. Chọn chính sách cho hai cột

Cho bảng ứng dụng có:

```text
display_name = tên hiển thị có dấu
external_code = mã từ hệ thống đối tác
```

**Câu hỏi:** Nếu người dùng tìm `'Ha Noi'` muốn ra `'Hà Nội'`, nhưng `'Ab12'` và `'ab12'` là hai mã khác nhau, nên dùng một collation chung bỏ cả hoa và dấu cho mọi cột không?

**Gợi ý đáp án:** Không. `display_name` có thể cần khóa tìm kiếm/collation phục vụ tìm tên tiếng Việt; `external_code` cần chính sách so sánh phù hợp định danh của đối tác. Phải cấu hình và kiểm tra từng cột theo mục đích.

## 17. Mẫu truy vấn tham khảo nhanh

| Mục tiêu | Ví dụ | Ghi chú |
| --- | --- | --- |
| So sánh theo collation mặc định | `WHERE name = 'cafe'` | Kết quả phụ thuộc cột/DBMS. |
| Phân biệt chữ/dấu với PostgreSQL C collation | `WHERE name COLLATE "C" = 'cafe'` | Phù hợp để minh họa so sánh đơn giản, không thay thế quy ước byte-level cho mọi kiểu. |
| So sánh không phân biệt hoa/thường bằng hàm | `WHERE LOWER(name) = LOWER('cafe')` | Không tự bỏ dấu; có thể cần index biểu thức. |
| Tìm mẫu không phân biệt hoa/thường trên PostgreSQL | `WHERE name ILIKE 'caf%'` | Không mặc định bỏ dấu. |
| Bỏ hoa/thường và dấu với PostgreSQL ICU | `WHERE name COLLATE public.demo_ci_ai = 'cafe'` | Cần tạo collation nondeterministic và có ICU. |
| MySQL 8 không phân biệt hoa/dấu | `WHERE name COLLATE utf8mb4_0900_ai_ci = 'cafe'` | Cột/biểu thức phải dùng charset phù hợp. |
| SQL Server không phân biệt hoa/dấu | `WHERE name COLLATE Latin1_General_100_CI_AI = N'cafe'` | Tên collation riêng SQL Server. |
| SQLite không phân biệt hoa/thường ASCII | `WHERE name = 'cafe' COLLATE NOCASE` | Không giải quyết đầy đủ Unicode tiếng Việt. |
| Kiểm tra giá trị thiếu | `WHERE name IS NULL` | Không dùng `name = NULL`. |
| Bỏ khoảng trắng đầu/cuối trước khi so sánh | `WHERE TRIM(name) = 'cafe'` | Không tự bỏ dấu, chú ý chi phí hàm. |
| Lọc tiền tố | `WHERE name LIKE 'caf%'` | Hành vi case/accent tùy DBMS/collation. |
| Sắp xếp ổn định | `ORDER BY name, id` | Xác định collation và khóa phụ. |

Để viết điều kiện chuỗi đáng tin cậy, hãy **xác định ý nghĩa của “bằng nhau” trước khi chọn cú pháp**. Dữ liệu có dấu, chữ hoa/thường và biểu diễn Unicode cần được xử lý theo chính sách rõ ràng. Collation quyết định nhiều quy tắc so sánh và sắp xếp; `LOWER`/`UPPER` chỉ giải quyết một phần nhu cầu; `LIKE`/`ILIKE` có ngữ nghĩa riêng; và cách hỗ trợ của từng DBMS không hoàn toàn giống nhau. Khi nhất quán giữa dữ liệu lưu trữ, truy vấn, ràng buộc `UNIQUE` và chỉ mục, hệ thống sẽ tránh những lỗi lọc tên âm thầm nhưng rất khó phát hiện.
