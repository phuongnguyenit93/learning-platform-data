# char, varchar, text và chiều dài chuỗi trong PostgreSQL

Trong PostgreSQL, một cột lưu tên khách hàng, mã sản phẩm hoặc phần mô tả đều chứa **chuỗi ký tự**, nhưng lựa chọn kiểu dữ liệu có thể ảnh hưởng cách PostgreSQL kiểm tra chiều dài, lưu khoảng trắng cuối, so sánh, lập chỉ mục và xử lý dữ liệu Unicode.

Ba kiểu dữ liệu phổ biến nhất là **`character(n)` / `char(n)`**, **`character varying(n)` / `varchar(n)`** và **`text`**. Tên có vẻ tương tự, nhưng `char(n)` có hành vi **đệm khoảng trắng đến độ dài n**, còn `varchar(n)` lưu chuỗi ngắn mà không đệm và kiểm tra giới hạn số ký tự. `text` không yêu cầu giới hạn độ dài ở phần khai báo kiểu.

Bài học thuộc chương *Kiểu dữ liệu* của module *Database Engine Relational PostgreSQL*, tập trung vào việc lựa chọn kiểu đúng ngữ nghĩa và xác định **“độ dài chuỗi” đang được tính bằng ký tự, byte hay kích thước lưu trữ**.

Sau khi học xong, bạn có thể:

- Phân biệt `char(n)`, `varchar(n)`, `varchar` và `text` bằng ví dụ SQL thực thi được.
- Hiểu cách PostgreSQL đệm/bỏ qua khoảng trắng cuối ở `char(n)` và tác động lên phép so sánh.
- Giải thích khi nào chuỗi vượt `n` gây lỗi và khi nào bị cắt trong phép ép kiểu tường minh.
- Dùng `char_length()`, `length()`, `octet_length()`, `bit_length()` và `pg_column_size()` đúng mục tiêu.
- Làm việc với UTF-8, ký tự nhiều byte và các chuỗi có dấu tổ hợp.
- Thiết kế `CHECK`, `UNIQUE`, chỉ mục và kế hoạch thay đổi độ dài cột an toàn.

Các ví dụ dùng cú pháp PostgreSQL thông dụng; phần minh họa Unicode giả định database dùng **UTF8**, có thể kiểm tra bằng `SHOW server_encoding;`. Khi nói tới hành vi bằng nhau của hai chuỗi `text`, chúng ta giả định **collation xác định (*deterministic*) thông thường**, trừ nơi có ghi chú khác.

## 1. Chọn kiểu chuỗi nào? Bảng so sánh nhanh

| Kiểu SQL | Khai báo ví dụ | Chiều dài tối đa trong khai báo | Khi chuỗi ngắn hơn n | Công dụng điển hình |
|---|---|---|---|---|
| `character(n)`, `char(n)` | `CHAR(6)` | Tối đa n **ký tự** | Đệm thêm dấu cách để thành n ký tự | Dữ liệu mã cố định theo chuẩn/legacy nếu chấp nhận ngữ nghĩa đệm |
| `character varying(n)`, `varchar(n)` | `VARCHAR(80)` | Tối đa n **ký tự** | Giữ đúng độ dài gốc, không đệm | Tên, mã, dữ liệu cần giới hạn kỹ thuật |
| `character varying`, `varchar` | `VARCHAR` | Không chỉ định giới hạn n | Không đệm | Hành vi lưu chuỗi tương tự `TEXT` |
| `text` | `TEXT` | Không đặt giới hạn n trong khai báo | Không đệm | Mô tả, nội dung, tên, mã khi muốn quy tắc độ dài bằng constraint |
| `character`, `char` không có n | `CHAR` | Tương đương `CHAR(1)` | Đệm đến 1 ký tự | Rất dễ bị chọn nhầm nếu tưởng là chuỗi không giới hạn |

**Khuyến nghị thực tế:** trong đa số ứng dụng PostgreSQL, hãy bắt đầu bằng `text` hoặc `varchar(n)` khi có giới hạn nghiệp vụ thực sự. Chỉ dùng `char(n)` khi đã hiểu và thật sự muốn ngữ nghĩa đệm khoảng trắng của nó. `char(20)` **không mặc nhiên nhanh hơn** `varchar(20)` hay `text`.

### 1.1. Các tên viết khác nhau có thể là cùng một kiểu

PostgreSQL chấp nhận:

```sql
CREATE TABLE demo_ten_kieu (
    a CHARACTER(10),
    b CHAR(10),
    c CHARACTER VARYING(10),
    d VARCHAR(10),
    e CHARACTER VARYING,
    f VARCHAR,
    g TEXT
);
```

Trong đó:

- `a` và `b` cùng nhóm `character(10)`.
- `c` và `d` cùng nhóm `character varying(10)`.
- `e`, `f` không có giới hạn khai báo và lưu trữ theo hành vi gần giống `text`.
- `g` dùng kiểu `text` của PostgreSQL.

Đừng nhầm SQL `CHAR(n)` với kiểu nội bộ có tên **`"char"`** trong PostgreSQL catalog: kiểu nội bộ một byte đó không phải kiểu được thiết kế để lưu chuỗi nghiệp vụ thông thường.

## 2. Hiểu n là số ký tự, không phải số byte

Với `varchar(n)` và `char(n)`, `n` quy định **số ký tự theo cách PostgreSQL đếm ký tự**, không phải dung lượng byte cần cấp.

Ví dụ dưới đây chạy trên database có encoding UTF8:

```sql
SHOW server_encoding;

SELECT
    char_length('A')   AS so_ky_tu_ascii,
    octet_length('A')  AS so_byte_ascii,
    char_length('é')   AS so_ky_tu_e_dau,
    octet_length('é')  AS so_byte_e_dau,
    char_length('😀')  AS so_ky_tu_emoji,
    octet_length('😀') AS so_byte_emoji;
```

Kết quả dự kiến ở UTF8:

| Chuỗi | `char_length` | `octet_length` |
|---|---:|---:|
| `A` | 1 | 1 |
| `é` (dạng ký tự dựng sẵn) | 1 | 2 |
| `😀` | 1 | 4 |

Vì thế, một cột `varchar(3)` có thể chứa ba ký tự Unicode nhưng tổng số byte lớn hơn 3. Khi thiết kế dung lượng truyền qua API, lưu trữ hoặc giới hạn kích thước payload, phải đo **byte** riêng.

### 2.1. Ký tự Unicode không luôn là “một thứ người dùng nhìn thấy”

Một chữ có dấu có thể được biểu diễn bằng:

1. Một **code point dựng sẵn**, ví dụ `é`.
2. Chữ `e` cùng **dấu sắc tổ hợp** `U+0301`.

Trong PostgreSQL UTF8:

```sql
SELECT
    char_length('é') AS do_dai_dung_san,
    char_length(U&'e\0301') AS do_dai_to_hop,
    octet_length('é') AS byte_dung_san,
    octet_length(U&'e\0301') AS byte_to_hop;
```

Kết quả thông thường:

| Biểu diễn | `char_length` | `octet_length` |
|---|---:|---:|
| `é` | 1 | 2 |
| `e` + dấu sắc tổ hợp | 2 | 3 |

Hai chuỗi có thể **trông giống nhau** nhưng số ký tự mà PostgreSQL đếm khác nhau. `char_length` không phải hàm đếm *grapheme cluster* hay “số hình chữ người dùng nhìn thấy”. Chuỗi có emoji ghép nối và dấu tổ hợp cần quy tắc Unicode/chuẩn hóa rõ ràng nếu giao diện hạn chế số ký tự hiển thị.

### 2.2. Giới hạn kiểu không phải dung lượng đĩa cố định

`varchar(100)` không có nghĩa mỗi hàng tự dành đúng 100 byte. PostgreSQL lưu dữ liệu chuỗi độ dài biến thiên cùng phần overhead cần thiết; mức chiếm chỗ thực tế phụ thuộc byte của nội dung, cấu trúc tuple và cơ chế lưu trữ.

Ngược lại, `char(100)` có thể phải lưu thêm nhiều dấu cách đệm cho một chuỗi ngắn, khiến dữ liệu lớn hơn không cần thiết. Không dùng tên kiểu để suy ra chính xác số byte trên disk.

## 3. Thực hành đầu tiên: tạo bảng với cả ba kiểu

Tạo schema riêng để không đụng bảng ứng dụng:

```sql
CREATE SCHEMA IF NOT EXISTS pg_string_lab;

CREATE TABLE pg_string_lab.loai_chuoi (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_co_dinh CHAR(6),
    ma_gioi_han VARCHAR(6),
    ghi_chu TEXT
);
```

Thêm dữ liệu:

```sql
INSERT INTO pg_string_lab.loai_chuoi
    (ma_co_dinh, ma_gioi_han, ghi_chu)
VALUES
    ('AB',   'AB',   'Dòng thử độ dài ngắn'),
    ('XY12', 'XY12', 'Mã dài hơn một chút'),
    ('VN',   'VN',   'Chuỗi Unicode: tiếng Việt');
```

Truy vấn:

```sql
SELECT
    id,
    ma_co_dinh,
    ma_gioi_han,
    ghi_chu
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

Nhìn kết quả bằng terminal hoặc GUI, hai cột mã có thể trông giống nhau vì nhiều công cụ không hiển thị rõ khoảng trắng ở cuối chuỗi. **Không kết luận hai kiểu lưu giống nhau chỉ dựa trên cách hiển thị.**

### 3.1. Đo độ dài ngay trên dữ liệu đã lưu

```sql
SELECT
    id,
    char_length(ma_co_dinh) AS len_char,
    octet_length(ma_co_dinh) AS bytes_char,
    char_length(ma_gioi_han) AS len_varchar,
    octet_length(ma_gioi_han) AS bytes_varchar
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

Giả sử các mã dùng ký tự ASCII như dữ liệu mẫu:

| id | len_char | bytes_char | len_varchar | bytes_varchar |
|---:|---:|---:|---:|---:|
| 1 | 2 | 6 | 2 | 2 |
| 2 | 4 | 6 | 4 | 4 |
| 3 | 2 | 6 | 2 | 2 |

Đây là bằng chứng trực tiếp:

- `CHAR(6)` đã được **đệm dấu cách đến chiều dài khai báo** trong phần lưu trữ.
- `char_length` đối với giá trị `character(n)` **không tính phần khoảng trắng đệm ở cuối**.
- `octet_length` có thể tính cả byte dấu cách đã đệm của `character(n)`.
- `VARCHAR(6)` giữ dữ liệu ngắn, không tự đệm.

Lưu ý phép đo trên là các giá trị ASCII, mỗi ký tự chiếm một byte ở UTF8; với các ký tự nhiều byte, số byte không còn bằng số ký tự.

## 4. CHAR(n): chuỗi được đệm khoảng trắng

Kiểu `CHAR(n)` (hay `CHARACTER(n)`) là kiểu ký tự **độ dài cố định theo ngữ nghĩa SQL**.

Ví dụ:

```sql
SELECT
    'AB'::CHAR(5) AS gia_tri,
    char_length('AB'::CHAR(5)) AS so_ky_tu,
    octet_length('AB'::CHAR(5)) AS so_byte;
```

Với ASCII và UTF8, kết quả độ dài lần lượt là **2 ký tự** và **5 byte**. PostgreSQL đã thêm ba dấu cách để đủ độ dài vật lý của `CHAR(5)`.

### 4.1. Khoảng trắng đệm thường bị bỏ qua trong so sánh bằng

So sánh hai giá trị đã cùng chuyển thành kiểu `CHAR(5)`:

```sql
SELECT
    'AB'::CHAR(5) = 'AB   '::CHAR(5)
        AS co_bang_nhau_khong;
```

Kết quả **true**: khoảng trắng cuối trong giá trị kiểu `character(n)` không có ý nghĩa khi PostgreSQL so sánh bằng theo ngữ nghĩa của kiểu này.

Điều đó có thể tạo bất ngờ khi dùng mã định danh. Với `CHAR(5)`, chuỗi nhập `'AB'` và `'AB   '` có thể được xem là cùng giá trị trong phép so sánh, dù đầu vào có số ký tự khác nhau.

### 4.2. Khoảng trắng ở đầu vẫn có ý nghĩa

```sql
SELECT
    'AB'::CHAR(5) = ' AB'::CHAR(5)
        AS co_bang_nhau_khong;
```

Với collation thông thường, kết quả **false** vì một chuỗi có dấu cách **đầu** mà chuỗi kia không có. Bỏ qua khoảng trắng cuối không đồng nghĩa PostgreSQL tự trim mọi whitespace ở mọi vị trí.

### 4.3. CAST CHAR(n) sang TEXT/VARCHAR có thể bỏ khoảng trắng cuối

Khi chuyển từ `character(n)` sang kiểu chuỗi khác, PostgreSQL có hành vi loại khoảng trắng đệm cuối:

```sql
SELECT
    char_length('AB'::CHAR(6)) AS len_char,
    octet_length('AB'::CHAR(6)) AS bytes_char,
    char_length(('AB'::CHAR(6))::TEXT) AS len_sau_cast_text,
    octet_length(('AB'::CHAR(6))::TEXT) AS bytes_sau_cast_text;
```

Kết quả minh họa với ASCII:

| len_char | bytes_char | len_sau_cast_text | bytes_sau_cast_text |
|---:|---:|---:|---:|
| 2 | 6 | 2 | 2 |

Vì vậy, các hàm hiển thị hoặc xử lý chuỗi có thể cho kết quả khác với một phép đo byte trực tiếp trên giá trị `CHAR(n)`. Đừng kỳ vọng ép kiểu sang `TEXT` giữ nguyên phần đệm vật lý.

### 4.4. LIKE và biểu thức chính quy không hoàn toàn giống dấu bằng

Theo ngữ nghĩa của kiểu `character(n)`, dấu cách cuối có thể được bỏ qua trong **phép so sánh giá trị character**, nhưng **pattern matching** như `LIKE` hoặc regular expression có quy tắc riêng, nơi khoảng trắng cuối có thể vẫn quan trọng.

Do đó:

```sql
-- Không suy luận kết quả LIKE từ kết quả toán tử =.
SELECT
    ma_co_dinh,
    ma_co_dinh LIKE 'AB%' AS phu_hop_mau
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

Khi viết bộ lọc theo mẫu, cần xét kiểu của toán hạng, ép kiểu, độ dài đệm, collation và mục tiêu nghiệp vụ. Với mã thường xuyên dùng `LIKE`, `CHAR(n)` dễ tạo thêm chi tiết phải nhớ.

### 4.5. Không nên chọn CHAR(n) chỉ để “tối ưu”

Kiểu `CHAR(n)` không có lợi thế tốc độ mặc định so với `VARCHAR(n)` hoặc `TEXT` trong PostgreSQL. Việc đệm khoảng trắng có thể tăng dung lượng và làm phát sinh chi phí xử lý. Những hệ thống dùng `CHAR(n)` thường có lý do chuẩn dữ liệu đã tồn tại, giao tiếp với phần mềm cũ, hoặc yêu cầu rõ về ngữ nghĩa khoảng trắng.

Nếu yêu cầu là **“mã phải đúng 6 ký tự”**, `CHAR(6)` **không tự thay thế** kiểm tra dữ liệu đúng 6 ký tự có ý nghĩa, vì đầu vào ngắn vẫn được đệm. Một `TEXT` hoặc `VARCHAR(6)` kết hợp `CHECK (char_length(code) = 6)` đôi khi phản ánh quy tắc nghiệp vụ rõ hơn.

## 5. VARCHAR(n): giới hạn chiều dài mà không đệm

`VARCHAR(n)` (hay `CHARACTER VARYING(n)`) cho phép từ 0 đến n ký tự nếu không có constraint khác, và giữ nguyên chiều dài thực tế của chuỗi được lưu.

```sql
SELECT
    'AB'::VARCHAR(5) AS gia_tri,
    char_length('AB'::VARCHAR(5)) AS so_ky_tu,
    octet_length('AB'::VARCHAR(5)) AS so_byte;
```

Kết quả với ASCII là **2 ký tự** và **2 byte**, không có ba dấu cách đệm như `CHAR(5)`.

### 5.1. Khoảng trắng cuối là một phần của giá trị

```sql
SELECT
    'AB'::VARCHAR(5) = 'AB   '::VARCHAR(5)
        AS varchar_equal,
    'AB'::TEXT = 'AB   '::TEXT
        AS text_equal;
```

Với collation xác định thông thường, cả hai kết quả là **false**. `VARCHAR` và `TEXT` không bỏ qua khoảng trắng cuối trong phép so sánh bằng theo cùng cách của `CHAR(n)`.

Trường hợp collation **không xác định (*nondeterministic*)** có thể thay đổi quy tắc so sánh những chuỗi khác byte; xem phần collation ở sau. Khi cần tính duy nhất nghiêm ngặt của mã, phải xét cả collation và bước chuẩn hóa đầu vào.

### 5.2. Độ dài tối đa là n ký tự, không phải n byte

```sql
CREATE TABLE pg_string_lab.ma_san_pham (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(8) NOT NULL
);

INSERT INTO pg_string_lab.ma_san_pham (sku)
VALUES ('ABC123');
```

Một chuỗi nhập dài hơn 8 ký tự có nghĩa sẽ vi phạm giới hạn:

```sql
-- Cố tình minh họa một lệnh có lỗi khi chạy:
-- INSERT INTO pg_string_lab.ma_san_pham (sku)
-- VALUES ('ABCDEFGHI');
-- ERROR: value too long for type character varying(8)
```

Vì đây là ví dụ về lệnh thất bại, nó được **chú thích** để người đọc không vô tình dừng cả script thực hành. Việc cập nhật cột `VARCHAR(8)` cũng phải tuân theo giới hạn chiều dài.

### 5.3. Giới hạn có tính tới khoảng trắng cuối theo quy tắc SQL

PostgreSQL tuân theo một ngoại lệ của chuẩn SQL: khi nhập vào cột `VARCHAR(n)` hoặc `CHAR(n)` mà chuỗi dài hơn n, **nếu các ký tự vượt giới hạn đều là khoảng trắng**, chúng có thể bị cắt bỏ để lưu dữ liệu hợp lệ.

Ví dụ cột `VARCHAR(4)`:

```sql
CREATE TABLE pg_string_lab.thu_do_dai (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gia_tri VARCHAR(4)
);

-- Đầu vào có 6 ký tự nhưng hai ký tự vượt quá 4 đều là space.
INSERT INTO pg_string_lab.thu_do_dai (gia_tri)
VALUES ('ABCD  ');

SELECT gia_tri, char_length(gia_tri)
FROM pg_string_lab.thu_do_dai;
```

Kết quả lưu là `ABCD` với chiều dài 4. Đây **không** phải bằng chứng rằng `VARCHAR(4)` cho phép mọi chuỗi dài tùy ý. Nếu ký tự vượt giới hạn khác khoảng trắng thông thường, việc ghi sẽ lỗi.

### 5.4. Ép kiểu tường minh có thể cắt chuỗi mà không báo lỗi

Một ngoại lệ **rất quan trọng**: khi người lập trình **ép kiểu tường minh** sang `VARCHAR(n)` hoặc `CHAR(n)`, PostgreSQL có thể cắt dữ liệu về n ký tự thay vì phát sinh lỗi.

```sql
SELECT
    'ABCDEFGHI'::VARCHAR(4) AS sau_cast_varchar,
    'ABCDEFGHI'::CHAR(4) AS sau_cast_char;
```

Kết quả tương ứng với chuỗi `ABCD`.

Như vậy hai thao tác không đồng nghĩa:

```sql
-- A: Ghi chuỗi dài trực tiếp vào cột giới hạn:
-- Thường lỗi nếu phần vượt giới hạn chứa ký tự không phải space.
-- INSERT INTO pg_string_lab.thu_do_dai(gia_tri)
-- VALUES ('ABCDEFGHI');

-- B: Ép kiểu trước, rồi ghi:
-- Giá trị đã bị cắt còn 4 ký tự trước khi tới cột.
INSERT INTO pg_string_lab.thu_do_dai(gia_tri)
VALUES ('ABCDEFGHI'::VARCHAR(4));
```

Nếu API cần **từ chối dữ liệu vượt giới hạn** thay vì làm mất phần cuối, đừng dùng phép ép kiểu tường minh như một bước xử lý mặc định trước khi lưu. Hãy kiểm tra dữ liệu thô theo quy tắc nghiệp vụ, rồi để constraint bảo vệ dữ liệu.

## 6. VARCHAR không có n và TEXT

Trong PostgreSQL, khai báo:

```sql
CREATE TABLE pg_string_lab.noi_dung (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tieu_de VARCHAR,
    mo_ta TEXT
);
```

có hai cột chuỗi **không gắn giới hạn n trong kiểu khai báo**.

- `VARCHAR` không có `(n)` không áp giới hạn ký tự theo typmod.
- `TEXT` cũng không áp một giới hạn n được khai báo cùng tên kiểu.
- Cả hai là kiểu chuỗi biến thiên, không tự đệm khoảng trắng.
- Vẫn chịu **giới hạn kỹ thuật của PostgreSQL về kích thước một giá trị** và giới hạn tài nguyên của môi trường.

Không nên diễn giải “không có n” là một chuỗi có thể dài vô hạn: trong PostgreSQL, dữ liệu dạng varlena chịu giới hạn kích thước nội bộ (thực tế tối đa xấp xỉ 1 GiB cho một giá trị trước các giới hạn khác), đồng thời bị giới hạn bởi RAM, disk, câu lệnh, protocol và các yêu cầu vận hành.

### 6.1. Chọn TEXT có khiến index không dùng được không?

Không. PostgreSQL hỗ trợ chỉ mục B-tree và các cơ chế indexing phù hợp cho `TEXT` và `VARCHAR`. Việc chọn `VARCHAR(255)` thay `TEXT` **không tự làm index nhanh hơn** hay tiết kiệm dung lượng cho cùng nội dung.

Ví dụ:

```sql
CREATE INDEX noi_dung_tieu_de_idx
ON pg_string_lab.noi_dung (tieu_de);
```

Index có hữu ích hay không còn phụ thuộc dạng truy vấn, selectivity, collation, loại operator và kế hoạch thực thi. `LIKE '%chuoi%'` thông thường không hưởng lợi từ B-tree đơn giản như truy vấn bằng; có thể cần giải pháp indexing khác, chẳng hạn trigram cho workload tìm kiếm con chuỗi.

### 6.2. Khi nào dùng TEXT, khi nào dùng VARCHAR(n)?

Một lựa chọn thường gặp:

| Cột nghiệp vụ | Lựa chọn hợp lý | Vì sao |
|---|---|---|
| Mô tả sản phẩm | `TEXT` | Nội dung có thể dài, không cần giới hạn cố định ở kiểu |
| Tên người dùng hiển thị | `TEXT` kèm `CHECK` hoặc `VARCHAR(100)` | Giới hạn nghiệp vụ cần thể hiện rõ |
| SKU tối đa 32 ký tự | `VARCHAR(32)` hoặc `TEXT CHECK (...)` | Không cho dữ liệu dài ngoài hợp đồng |
| Ghi chú nội bộ | `TEXT` | Hạn chế n không có lợi nếu không có yêu cầu |
| Quốc gia ISO hai chữ cái | `TEXT` + `CHECK`/foreign key, hoặc `VARCHAR(2)` | Cần xác thực đúng bộ mã, không chỉ độ dài |
| Giá trị được tạo bởi máy, ID chuyên biệt | Kiểu phù hợp như `UUID` khi có ngữ nghĩa UUID | Không biến mọi dữ liệu thành chuỗi nếu có kiểu chuyên biệt |

Nếu hệ thống cần chính xác 2 ký tự mã quốc gia, `CHAR(2)` một mình không bảo đảm đầu vào đã có hai chữ có nghĩa vì cơ chế đệm. Ràng buộc về tập giá trị hợp lệ thường quan trọng hơn việc sử dụng kiểu ký tự cố định.

## 7. Những hàm đo chiều dài chuỗi cần phân biệt

PostgreSQL có nhiều hàm liên quan độ dài; mỗi hàm trả lời một câu hỏi khác nhau.

| Hàm | Đo gì? | Ví dụ |
|---|---|---|
| `char_length(text)` | Số ký tự theo cách PostgreSQL đếm | `char_length('é')` có thể là 1 |
| `character_length(text)` | Tương đương `char_length` | Cú pháp gần chuẩn SQL |
| `length(text)` | Số ký tự; với chuỗi thông thường tương đương `char_length` | `length('ABC') = 3` |
| `octet_length(text)` | Số byte của chuỗi ở encoding hiện tại | UTF8 `octet_length('é') = 2` |
| `bit_length(text)` | Số bit của biểu diễn chuỗi | `bit_length('A') = 8` trong UTF8 |
| `pg_column_size(value)` | Số byte để lưu giá trị dưới dạng nội bộ theo ngữ cảnh đo | Có thể gồm overhead/ảnh hưởng nén; không bằng ký tự |

### 7.1. Một truy vấn so sánh các phép đo

```sql
SELECT
    'Tiếng Việt'::TEXT AS gia_tri,
    char_length('Tiếng Việt') AS so_ky_tu,
    octet_length('Tiếng Việt') AS so_byte,
    bit_length('Tiếng Việt') AS so_bit,
    pg_column_size('Tiếng Việt'::TEXT) AS kich_thuoc_noi_bo;
```

Giá trị thực của `pg_column_size` không nên được dùng làm một “định nghĩa mới của độ dài”. Kích thước lưu trữ có thể gồm metadata và chịu ảnh hưởng của dạng lưu thực tế; một số giá trị lớn có thể được nén hoặc lưu tách theo cơ chế TOAST.

### 7.2. char_length và length có khác nhau không?

Đối với `TEXT` và `VARCHAR` thông thường:

```sql
SELECT
    char_length('ABC'::TEXT) AS a,
    character_length('ABC'::TEXT) AS b,
    length('ABC'::TEXT) AS c;
```

Cả ba cùng cho kết quả **3**. Điều cần chú ý hơn là **đối số có phải `CHAR(n)` hay không**, do dấu cách đệm của kiểu này có ngữ nghĩa riêng.

### 7.3. Đo một chuỗi có dấu cách thật ở cuối

```sql
SELECT
    char_length('AB  '::TEXT) AS text_len,
    octet_length('AB  '::TEXT) AS text_bytes,
    char_length('AB  '::VARCHAR(6)) AS varchar_len,
    octet_length('AB  '::VARCHAR(6)) AS varchar_bytes;
```

Với ASCII, kết quả đều là **4** cho các phép đếm trên, vì hai dấu cách cuối **là dữ liệu thật** của `TEXT`/`VARCHAR`.

Đối với `CHAR(n)`, `char_length` không tính dấu cách cuối theo ngữ nghĩa kiểu character. Vì vậy không dùng một mình `char_length(char_col)` để xác định người dùng ban đầu gõ bao nhiêu dấu cách: dữ liệu gốc có thể đã bị padding hoặc chuyển kiểu.

### 7.4. Cắt bỏ whitespace để đo có chủ đích

```sql
SELECT
    char_length('  ABC  '::TEXT) AS len_goc,
    char_length(btrim('  ABC  '::TEXT)) AS len_sau_trim,
    char_length(rtrim('  ABC  '::TEXT)) AS len_sau_rtrim,
    char_length(ltrim('  ABC  '::TEXT)) AS len_sau_ltrim;
```

Kết quả theo ký tự ASCII:

| len_goc | len_sau_trim | len_sau_rtrim | len_sau_ltrim |
|---:|---:|---:|---:|
| 7 | 3 | 5 | 5 |

`btrim` mặc định cắt các **ký tự dấu cách thông thường** ở hai đầu. Nó không đồng nghĩa với chuẩn hóa mọi ký tự whitespace Unicode hay loại bỏ toàn bộ ký tự vô hình. Nếu đầu vào có tab, non-breaking space hoặc zero-width character, cần chính sách xử lý rõ hơn.

## 8. NULL, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng

Ba giá trị sau mang ý nghĩa khác nhau trong PostgreSQL:

```sql
SELECT
    NULL::TEXT AS khong_co_gia_tri,
    ''::TEXT AS chuoi_rong,
    '   '::TEXT AS ba_dau_cach;
```

| Giá trị | Ý nghĩa | `char_length` | So với chuỗi rỗng |
|---|---|---:|---|
| `NULL` | Không có giá trị / chưa biết | `NULL` | Kết quả so sánh là unknown |
| `''` | Chuỗi có 0 ký tự | 0 | Bằng chuỗi rỗng |
| `'   '` | Chuỗi có ba dấu cách | 3 | Khác chuỗi rỗng với collation xác định thông thường |

Kiểm tra bằng:

```sql
SELECT
    NULL::TEXT IS NULL AS null_la_null,
    ''::TEXT IS NULL AS empty_la_null,
    char_length(''::TEXT) AS do_dai_empty,
    char_length('   '::TEXT) AS do_dai_spaces;
```

PostgreSQL **không tự đồng nhất `''` với `NULL`**. Khi thiết kế API, cần quy định rõ một trường không được gửi, được gửi `null`, hoặc được gửi chuỗi rỗng sẽ được xử lý ra sao.

### 8.1. Vì sao NOT NULL chưa đủ?

```sql
CREATE TABLE pg_string_lab.nguoi_dung (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten_hien_thi TEXT NOT NULL
);
```

`NOT NULL` cấm `NULL` nhưng **không cấm chuỗi rỗng**:

```sql
INSERT INTO pg_string_lab.nguoi_dung (ten_hien_thi)
VALUES ('');
```

Nếu quy tắc là tên không được rỗng sau khi bỏ dấu cách hai đầu, cần dùng thêm `CHECK` hoặc validation ở tầng ứng dụng.

## 9. Dùng CHECK để ràng buộc độ dài đúng nghiệp vụ

Thay vì nghĩ “mọi cột chuỗi phải là `VARCHAR(255)`”, hãy mô tả quy tắc:

- Tên hiển thị từ 1 đến 80 ký tự có nghĩa sau khi trim.
- Mã sản phẩm phải dài từ 3 đến 20 ký tự và không có dấu cách hai đầu.
- Nội dung mô tả không có giới hạn nghiệp vụ nhỏ; dùng `TEXT`.
- Trường protocol giới hạn tối đa 500 byte UTF-8, không phải 500 ký tự.

### 9.1. CHECK với char_length

```sql
CREATE TABLE pg_string_lab.ho_so (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    bio TEXT,
    CONSTRAINT chk_display_name_length
        CHECK (char_length(display_name) BETWEEN 1 AND 80),
    CONSTRAINT chk_display_name_not_blank
        CHECK (char_length(btrim(display_name)) > 0)
);
```

`char_length(display_name) BETWEEN 1 AND 80` giới hạn số ký tự PostgreSQL đếm, trong khi `char_length(btrim(display_name)) > 0` ngăn chuỗi chỉ có dấu cách ASCII thông thường.

Đặt cả hai constraint khác nhau giúp trả về thông tin lỗi rõ theo tên constraint nếu ứng dụng chuyển đổi lỗi.

### 9.2. Nếu yêu cầu đúng n ký tự

Đây là một phương án cho mã quốc gia hai chữ cái:

```sql
CREATE TABLE pg_string_lab.quoc_gia (
    ma_quoc_gia TEXT PRIMARY KEY,
    ten_quoc_gia TEXT NOT NULL,
    CONSTRAINT chk_ma_quoc_gia_do_dai
        CHECK (char_length(ma_quoc_gia) = 2),
    CONSTRAINT chk_ma_quoc_gia_chu_hoa
        CHECK (ma_quoc_gia COLLATE "C" ~ '^[A-Z]{2}$')
);
```

`char_length = 2` bắt đúng độ dài ký tự, còn regex `^[A-Z]{2}$` dưới collation `"C"` giới hạn hai chữ ASCII viết hoa cho **quy tắc minh họa**. Nếu nghiệp vụ dùng bộ mã ISO thực tế, nên kiểm tra thêm mã có nằm trong danh sách hợp lệ (bằng foreign key/bảng tham chiếu), không chỉ có đúng hai chữ cái.

### 9.3. Nếu yêu cầu là số byte

Một giao thức có thể đặt giới hạn payload `500 byte`:

```sql
CREATE TABLE pg_string_lab.thong_diep (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    CONSTRAINT chk_payload_bytes
        CHECK (octet_length(payload) <= 500)
);
```

Một chuỗi có 300 ký tự Unicode nhiều byte có thể vượt 500 byte dù `char_length` chưa vượt 500. Đây là lúc phải dùng `octet_length` thay cho `char_length`.

Nếu hệ thống truyền dữ liệu bằng một encoding khác với `server_encoding`, số byte khi mã hóa để truyền có thể khác số byte nội bộ; cần đánh giá theo encoding của giao thức thật.

### 9.4. Có nên vừa dùng VARCHAR(n) vừa dùng CHECK?

Có thể, nếu hai điều kiện kiểm tra **khác nhau**:

```sql
CREATE TABLE pg_string_lab.sku_hop_le (
    sku VARCHAR(20) PRIMARY KEY,
    CONSTRAINT chk_sku_not_blank
        CHECK (char_length(btrim(sku)) > 0),
    CONSTRAINT chk_sku_trimmed
        CHECK (sku = btrim(sku))
);
```

Ở đây `VARCHAR(20)` giới hạn 20 ký tự, còn `CHECK` ngăn mã rỗng toàn dấu cách và yêu cầu không có space ở hai đầu. Với collation xác định thông thường, `sku = btrim(sku)` nhận diện chuỗi có dấu cách đầu/cuối; nếu cần quy tắc byte chính xác trong môi trường collation đặc biệt, phải thiết kế phép kiểm tra phù hợp.

Lưu ý: với một số chuỗi đầu vào dài hơn 20 mà phần vượt chỉ là dấu cách, PostgreSQL có thể cắt phần vượt trước khi constraint thấy giá trị cuối. Nếu nghiệp vụ bắt buộc từ chối **mọi** đầu vào vượt giới hạn, hãy kiểm tra dữ liệu đầu vào thô ở API/ingestion và cân nhắc quy tắc riêng, không chỉ dựa vào kiểu.

## 10. So sánh và tính duy nhất: lưu ý CHAR, khoảng trắng và collation

Chọn kiểu chuỗi không chỉ là bài toán dung lượng. Nó còn ảnh hưởng việc hai giá trị có được xem là bằng nhau hay không.

### 10.1. So sánh CHAR và TEXT

```sql
SELECT
    'A'::CHAR(4) = 'A   '::CHAR(4)
        AS char_equal,
    'A'::VARCHAR(4) = 'A   '::VARCHAR(4)
        AS varchar_equal,
    'A'::TEXT = 'A   '::TEXT
        AS text_equal;
```

Với collation xác định thông thường:

| char_equal | varchar_equal | text_equal |
|---|---|---|
| true | false | false |

Khi một khóa nghiệp vụ phải phân biệt từng dấu cách, `CHAR(n)` thường không thích hợp. Nếu không muốn chấp nhận khoảng trắng đầu/cuối, hãy chuẩn hóa hoặc từ chối ngay ở biên ứng dụng và đặt constraint phù hợp.

### 10.2. UNIQUE trên CHAR(n) có thể coi các biến thể dấu cách là trùng

```sql
CREATE TABLE pg_string_lab.ma_co_dinh_duy_nhat (
    code CHAR(4) UNIQUE
);

INSERT INTO pg_string_lab.ma_co_dinh_duy_nhat (code)
VALUES ('AB');

-- Về ngữ nghĩa, giá trị dưới đây so sánh bằng giá trị vừa lưu,
-- do đó có thể bị UNIQUE từ chối:
-- INSERT INTO pg_string_lab.ma_co_dinh_duy_nhat (code)
-- VALUES ('AB  ');
```

Không chọn `CHAR(n)` để lưu một mã mà dấu cách cuối có vai trò phân biệt trong hệ thống bên ngoài, rồi kỳ vọng `UNIQUE` cho phép cả hai biến thể.

### 10.3. Collation cũng ảnh hưởng phép so sánh

PostgreSQL hỗ trợ collation điều chỉnh cách so sánh và sắp xếp chuỗi. Đặc biệt, **nondeterministic collation** có thể coi một số chuỗi khác byte là bằng nhau (ví dụ theo chính sách không phân biệt dấu/chữ hoa thường).

Vì vậy, câu “`TEXT` phân biệt mọi chuỗi có byte khác nhau trong `=`” không đúng tuyệt đối dưới **mọi collation**. Khi tính duy nhất quan trọng:

1. Xác định collation của cột/index.
2. Xác định có muốn bỏ qua hoa/thường, dấu hoặc dạng Unicode hay không.
3. Chọn quy tắc chuẩn hóa trước khi lưu.
4. Kiểm tra constraint `UNIQUE` theo dữ liệu thật.

Để xem metadata cột và các collation được gắn với schema, có thể sử dụng `information_schema.columns` hoặc các bảng catalog phù hợp. Không nên thay collation production chỉ để “cho kết quả so sánh đẹp hơn” vì có thể ảnh hưởng index và tính duy nhất.

### 10.4. Chuẩn hóa Unicode không tự xảy ra khi chọn VARCHAR

Hai chuỗi cùng hình thức hiển thị nhưng một chuỗi dùng code point dựng sẵn, chuỗi kia dùng dấu tổ hợp có thể khác về byte và độ dài. `VARCHAR(n)` hay `TEXT` không tự chuyển mọi văn bản vào cùng dạng chuẩn hóa Unicode.

Nếu nghiệp vụ cần một mã Unicode duy nhất theo dạng chuẩn (NFC/NFKC tùy yêu cầu), phải áp dụng chính sách normalization nhất quán và hiểu tác động tới dữ liệu đã tồn tại. Đừng dùng `lower()` hoặc `btrim()` thay thế cho Unicode normalization; mỗi hàm giải quyết vấn đề khác nhau.

## 11. Chỉ mục cho CHAR, VARCHAR và TEXT

### 11.1. B-tree có thể dùng cho tất cả các kiểu thông thường

```sql
CREATE INDEX ma_san_pham_sku_idx
ON pg_string_lab.ma_san_pham (sku);

CREATE INDEX ho_so_display_name_idx
ON pg_string_lab.ho_so (display_name);
```

Với cùng nội dung và điều kiện truy vấn, việc khai báo `VARCHAR(n)` thay `TEXT` **không tự biến một truy vấn quét bảng thành index scan**. Optimizer xét tính chọn lọc, thống kê, chi phí I/O, collation và các điều kiện lọc.

### 11.2. Tìm bằng và tìm theo tiền tố là hai nhu cầu

```sql
SELECT *
FROM pg_string_lab.ma_san_pham
WHERE sku = 'ABC123';

SELECT *
FROM pg_string_lab.ma_san_pham
WHERE sku LIKE 'ABC%';
```

Truy vấn `=` thường có thể tận dụng B-tree với operator class phù hợp. Với `LIKE 'ABC%'`, khả năng dùng chỉ mục B-tree thông thường còn phụ thuộc collation và operator class. Nếu workload tìm tiền tố nhiều, có thể cân nhắc `varchar_pattern_ops` cho cột `VARCHAR` hoặc `text_pattern_ops` cho cột `TEXT` theo yêu cầu:

```sql
CREATE INDEX ma_san_pham_sku_prefix_idx
ON pg_string_lab.ma_san_pham (sku varchar_pattern_ops);
```

Không tự động tạo hai chỉ mục cho mọi cột chuỗi. Mỗi index chiếm đĩa và làm tăng chi phí ghi; dùng `EXPLAIN` để kiểm tra workload thực tế.

### 11.3. Tìm chuỗi con và ILIKE

```sql
SELECT *
FROM pg_string_lab.noi_dung
WHERE mo_ta ILIKE '%khuyến mãi%';
```

Tìm một đoạn nằm **ở giữa** chuỗi thường không phù hợp với B-tree cơ bản. PostgreSQL có extension `pg_trgm` hỗ trợ các kiểu index như GIN/GiST phục vụ một số tìm kiếm mẫu, nhưng việc cài extension và tạo index cần quyền, dung lượng và đánh giá phù hợp.

Đây là vấn đề **chiến lược tìm kiếm văn bản**, không phải lý do bỏ `TEXT` để chuyển mọi nội dung sang `VARCHAR(255)`.

## 12. Lưu trữ chuỗi dài, TOAST và hiệu năng

### 12.1. TEXT không có nghĩa tất cả nội dung nằm trực tiếp trong một page

PostgreSQL quản lý các giá trị chuỗi lớn thông qua cơ chế lưu trữ kiểu biến thiên và có thể sử dụng **TOAST** (*The Oversized-Attribute Storage Technique*) để nén hoặc chuyển một số giá trị lớn ra vùng lưu trữ phụ.

Điểm quan trọng:

- `TEXT` và `VARCHAR` đều có thể sử dụng TOAST khi phù hợp.
- `CHAR(n)` không biến mọi giá trị thành một cấu trúc vật lý có kích thước cố định bất kể nội dung.
- Một chuỗi nhỏ không nhất thiết được nén hoặc chuyển sang bảng TOAST.
- Sự tồn tại của TOAST phụ thuộc kích thước tuple, chiến lược storage và cách PostgreSQL tổ chức dữ liệu, không chỉ số ký tự trong một cột.

Hãy xem **bộ nhớ, I/O, kích thước bảng và query plan** thay vì suy từ tên kiểu.

### 12.2. Đo kích thước bảng thực

```sql
SELECT
    pg_size_pretty(
        pg_table_size('pg_string_lab.loai_chuoi')
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('pg_string_lab.loai_chuoi')
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('pg_string_lab.loai_chuoi')
    ) AS total_size;
```

Kích thước bảng có thể bao gồm overhead, metadata, các trang chưa dùng hết, TOAST và phần lưu trữ khác theo cách PostgreSQL định nghĩa. Không lấy `SUM(octet_length(column))` làm tổng kích thước file thật của bảng.

### 12.3. Tại sao VARCHAR(255) không phải “mốc tối ưu” trong PostgreSQL?

Một số nền tảng hoặc hệ quản trị khác có các giới hạn/kỹ thuật đặc thù gắn với số 255. Trong PostgreSQL, `VARCHAR(255)` không tự mang lợi ích hiệu năng phổ quát so với `TEXT`. Chọn n phải dựa trên **hợp đồng dữ liệu** (ví dụ tên hiển thị không quá 100 ký tự), không phải áp một con số quen thuộc cho tất cả cột.

### 12.4. CHAR(n) có thật sự dùng đúng n byte?

Không được đồng nhất **n ký tự** với **n byte** khi dữ liệu có Unicode nhiều byte. PostgreSQL thêm dấu cách đệm để đạt độ dài **theo ký tự**; các ký tự thật có thể chiếm 2–4 byte trong UTF8, và tuple còn có overhead.

Ví dụ `CHAR(5)` chứa hai ký tự có dấu nhiều byte sẽ có kích thước byte khác `CHAR(5)` chứa hai chữ ASCII, dù cả hai cùng được đệm đến năm ký tự.

## 13. Đổi kiểu hoặc giới hạn cột trong bảng đã có dữ liệu

Một dự án bắt đầu với `VARCHAR(20)` rồi muốn tăng thành `VARCHAR(100)`, hoặc đang có `TEXT` nhưng muốn đặt giới hạn 30 ký tự. Cần tránh làm mất dữ liệu do ép kiểu tường minh hoặc khóa bảng kéo dài.

### 13.1. Kiểm tra dữ liệu trước khi siết giới hạn

Giả sử bảng `pg_string_lab.ho_so` đã có dữ liệu:

```sql
SELECT
    id,
    char_length(display_name) AS do_dai,
    display_name
FROM pg_string_lab.ho_so
WHERE char_length(display_name) > 30
ORDER BY do_dai DESC, id;
```

Nếu kết quả có dòng, việc chuyển sang `VARCHAR(30)` có thể thất bại hoặc yêu cầu chính sách xử lý dữ liệu vượt giới hạn. Đừng mặc định cắt đầu vào còn 30 ký tự vì phần bị loại có thể quan trọng.

### 13.2. Thay đổi kiểu bằng ALTER TABLE

Trong môi trường thực hành:

```sql
ALTER TABLE pg_string_lab.ho_so
    ALTER COLUMN display_name TYPE VARCHAR(100);
```

Lệnh này chỉ hợp lý khi dữ liệu phù hợp với giới hạn mới. Với bảng lớn, thay đổi kiểu/typmod có thể đòi hỏi khóa và trong một số trường hợp phải viết lại dữ liệu hoặc index; cần kiểm tra phiên bản và hoạch định bảo trì.

**Lưu ý:** Nếu sau này muốn đổi từ `VARCHAR(100)` về `VARCHAR(30)`, các dòng dài cần được xác định và xử lý có chủ đích trước. Không khuyến nghị:

```sql
-- Không dùng như "cách sửa dữ liệu" mặc định:
-- ALTER TABLE ... ALTER COLUMN display_name TYPE VARCHAR(30)
-- USING left(display_name, 30);
```

Vì `left(...,30)` cố tình cắt mất phần cuối mà có thể không có bất kỳ cảnh báo nghiệp vụ nào.

### 13.3. Giữ TEXT và thêm CHECK có thể dễ diễn đạt hơn

Nếu yêu cầu chỉ là “không quá 100 ký tự”:

```sql
ALTER TABLE pg_string_lab.noi_dung
ADD CONSTRAINT chk_tieu_de_max
CHECK (tieu_de IS NULL OR char_length(tieu_de) <= 100);
```

`TEXT` cùng `CHECK` thể hiện quy tắc bằng biểu thức, thuận tiện khi muốn kết hợp nhiều điều kiện. Tuy nhiên, ràng buộc mới trên bảng lớn có thể kiểm tra dữ liệu đang có và ảnh hưởng vận hành; `CHECK` không phải “miễn phí”. Với quy trình migration, cần cân nhắc chiến lược kiểm chứng và triển khai phù hợp.

### 13.4. Chuyển CHAR(n) sang TEXT/VARCHAR cần thận trọng

Khi chuyển dữ liệu từ `CHAR(n)` sang kiểu chuỗi biến thiên, PostgreSQL thường bỏ phần dấu cách cuối theo ngữ nghĩa cast của `CHAR(n)`. Nếu hệ thống cũ cố ý mã hóa thông tin dựa vào khoảng trắng cuối, **không thể mặc định khôi phục lại dữ liệu đầu vào nguyên bản**: các dấu cách này đã bị đồng nhất với dấu cách đệm ở kiểu `CHAR(n)`.

Trước migration, cần biết dữ liệu kỳ vọng sau chuyển đổi và có kiểm thử truy vấn/unique/index để tránh thay đổi ý nghĩa khóa.

## 14. Quan sát kiểu và giới hạn cột bằng catalog

Trong database thật, người học thường không có sẵn file DDL của mọi bảng. PostgreSQL có catalog để tra cứu.

### 14.1. information_schema.columns

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'pg_string_lab'
  AND table_name = 'loai_chuoi'
ORDER BY ordinal_position;
```

Kỳ vọng:

| column_name | data_type | character_maximum_length |
|---|---|---:|
| id | integer | `NULL` |
| ma_co_dinh | character | 6 |
| ma_gioi_han | character varying | 6 |
| ghi_chu | text | `NULL` |

`character_maximum_length IS NULL` ở `TEXT` không có nghĩa cột **không lưu được dữ liệu**: nó chỉ không có một giới hạn n theo kiểu dữ liệu được khai báo.

### 14.2. pg_catalog.format_type

```sql
SELECT
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS declared_type,
    a.attnotnull AS not_null
FROM pg_attribute AS a
WHERE a.attrelid = 'pg_string_lab.loai_chuoi'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

`format_type` dùng thông tin OID/typmod nội bộ để tạo chuỗi biểu diễn kiểu theo cách dễ đọc, ví dụ `character(6)` hoặc `character varying(6)`.

`atttypmod` là metadata nội bộ, không nên coi raw number của nó luôn chính là n; hãy dùng `format_type` hoặc `information_schema.columns` để hiển thị rõ khai báo.

### 14.3. psql \d

Trong `psql`:

```text
\d pg_string_lab.loai_chuoi
```

Đây là lệnh meta dành cho `psql`, không phải SQL thuần để chạy qua JDBC. Nó hữu ích để xem kiểu cột, constraint và index trong lúc thực hành.

## 15. Thiết kế dữ liệu chuỗi từ góc nhìn Java/JDBC

Ứng dụng Java phổ biến dùng `String` để truyền dữ liệu chuỗi sang PostgreSQL qua `PreparedStatement`. Tuy nhiên, **`String.length()` trong Java đếm UTF-16 code units**, còn `char_length()` trong PostgreSQL UTF8 đếm ký tự theo biểu diễn Unicode của database. Với các ký tự ngoài BMP như emoji, hai phép đếm có thể khác nhau.

### 15.1. Ví dụ chênh lệch độ dài Java và PostgreSQL

Trong Java:

```java
String emoji = "😀";

System.out.println(emoji.length());                  // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
```

Trong PostgreSQL UTF8:

```sql
SELECT
    char_length('😀') AS so_ky_tu,
    octet_length('😀') AS so_byte;
```

Kết quả PostgreSQL là 1 ký tự và 4 byte. Vì vậy, nếu API giới hạn “không quá 20 ký tự theo `char_length` của PostgreSQL”, việc chỉ dùng Java `String.length() <= 20` có thể từ chối không cần thiết hoặc không diễn đạt đúng quy tắc với Unicode.

Java có `codePointCount` để tiến gần hơn cách đếm code point; tuy nhiên, cả hai vẫn khác “số grapheme cluster nhìn thấy” trong các chuỗi ghép dấu/emoji phức tạp.

### 15.2. INSERT qua PreparedStatement

Ví dụ:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductRepository {
    public void insertProduct(
            Connection connection,
            String sku,
            String description
    ) throws SQLException {
        String sql = """
            INSERT INTO pg_string_lab.ma_san_pham (sku)
            VALUES (?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setString(1, sku);
            statement.executeUpdate();
        }
    }
}
```

`PreparedStatement` tách dữ liệu người dùng khỏi cú pháp SQL, giúp tránh SQL injection khi dùng tham số đúng cách. Bất kể Java validation thế nào, giới hạn `VARCHAR(8)` của bảng thực hành vẫn được PostgreSQL kiểm tra khi dữ liệu được lưu.

Tham số `description` trong chữ ký ví dụ chưa được dùng; nếu muốn lưu mô tả, cần thêm cột tương ứng và bind tham số, hoặc bỏ tham số khỏi phương thức cho gọn. Với dự án thực tế, nên khớp chữ ký và SQL chính xác.

### 15.3. Xử lý lỗi dữ liệu quá dài

Khi ghi chuỗi vượt `VARCHAR(n)` mà không thuộc trường hợp ngoại lệ khoảng trắng, PostgreSQL có thể trả SQLSTATE **22001** (*string_data_right_truncation*).

Ứng dụng nên:

1. Xác thực độ dài từ đầu vào và trả thông báo rõ ràng cho người dùng.
2. Để DB constraint làm lớp bảo vệ cuối cùng.
3. Bắt mã SQLSTATE cụ thể khi cần phân biệt lỗi validation với lỗi kết nối.
4. Tránh tự động dùng `substring` hoặc `::varchar(n)` để cắt chuỗi khi chưa có yêu cầu nghiệp vụ.

Không ghi toàn bộ dữ liệu nhạy cảm vào log chỉ vì lỗi quá dài; nên ghi mã trường, giới hạn kỳ vọng và thông tin phục vụ chẩn đoán phù hợp.

## 16. Các tình huống lựa chọn kiểu dữ liệu

### 16.1. Mã đơn hàng tối đa 20 ký tự

Nếu mã đơn hàng luôn phải dưới 20 ký tự nhưng có độ dài biến thiên:

```sql
CREATE TABLE pg_string_lab.don_hang (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(20) NOT NULL UNIQUE,
    note TEXT
);
```

`VARCHAR(20)` thể hiện trần số ký tự và `UNIQUE` tránh trùng mã theo collation/operator semantics đang sử dụng. Nếu mã có format chính xác như `ORD-2026-00001`, cần kiểm tra thêm regex hoặc một nguồn cấp mã hợp lệ.

### 16.2. Mã bưu chính không nên là INTEGER

Ví dụ mã bưu chính có thể bắt đầu bằng `0`. Nếu lưu bằng `INTEGER`, dấu `0` đầu sẽ mất.

```sql
CREATE TABLE pg_string_lab.dia_chi (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    postal_code TEXT,
    address_line TEXT NOT NULL
);
```

Nên lưu bằng kiểu chuỗi, rồi kiểm tra độ dài/định dạng theo quốc gia thay vì coi mọi mã bưu chính là một con số có thể tính toán.

### 16.3. Mô tả dài

Nếu mô tả có thể gồm nhiều đoạn văn, `TEXT` thường phù hợp hơn `CHAR(1000)`. Chọn `CHAR(1000)` cho đoạn mô tả 20 ký tự sẽ khiến phần đệm có thể rất lớn và sinh ngữ nghĩa so sánh không cần thiết.

### 16.4. Mã đúng hai ký tự

Nếu chỉ yêu cầu **chính xác hai chữ ASCII viết hoa**:

```sql
CREATE TABLE pg_string_lab.ma_vung (
    region_code TEXT PRIMARY KEY,
    CONSTRAINT chk_region_code
        CHECK (region_code COLLATE "C" ~ '^[A-Z]{2}$')
);
```

Regex này vừa áp hình thức vừa áp độ dài, rõ ràng hơn việc dựa vào `CHAR(2)` để tự đệm một mã có một chữ. Nếu mã có nhiều kiểu hợp lệ theo ngôn ngữ/quy chuẩn, phải sửa regex theo nghiệp vụ.

## 17. Những nhầm lẫn thường gặp

**1. “`VARCHAR(20)` dành sẵn đúng 20 byte cho mỗi dòng.”** Sai. Đây là giới hạn 20 ký tự; dữ liệu ngắn thường được lưu với độ dài biến thiên.

**2. “`CHAR(20)` lúc nào cũng đúng 20 byte.”** Sai với Unicode nhiều byte và overhead lưu trữ; ý nghĩa là đệm đến độ dài ký tự n.

**3. “`CHAR(n)` tự đảm bảo người dùng gõ đúng n ký tự.”** Sai. Chuỗi ngắn được đệm dấu cách.

**4. “`CHAR(n)` có ngữ nghĩa so sánh giống hệt `TEXT`.”** Sai. Khoảng trắng cuối được xử lý khác trong phép so sánh kiểu `character(n)`.

**5. “Chỉ cần `VARCHAR(n)` là dữ liệu không bao giờ bị cắt.”** Sai. PostgreSQL có ngoại lệ cắt phần dư toàn dấu cách và phép ép kiểu tường minh có thể cắt chuỗi.

**6. “`VARCHAR(255)` luôn nhanh hơn `TEXT`.”** Không có ưu thế mặc định như vậy trong PostgreSQL.

**7. “`TEXT` là vô hạn.”** Sai. Nó không khai báo giới hạn n nhưng vẫn chịu giới hạn giá trị nội bộ/tài nguyên.

**8. “`CHAR` không có n cũng không giới hạn.”** Sai. `CHAR` không ghi n tương đương `CHAR(1)`.

**9. “`char_length` luôn bằng `octet_length`.”** Sai với Unicode nhiều byte và với dấu cách đệm của `CHAR(n)`.

**10. “`char_length` đếm số ký tự hiển thị trên màn hình.”** Không hoàn toàn. Dấu Unicode tổ hợp và emoji ghép có thể gồm nhiều code point trong một biểu tượng.

**11. “`String.length()` Java luôn bằng `char_length()` PostgreSQL.”** Sai với các code point ngoài BMP và một số biểu diễn Unicode.

**12. “`NOT NULL` chặn chuỗi rỗng.”** Sai. `''` khác `NULL` trong PostgreSQL.

**13. “`btrim` xử lý mọi loại whitespace Unicode.”** Không; bản mặc định chủ yếu cắt ký tự dấu cách thường, cần quy tắc cụ thể hơn nếu muốn xử lý ký tự khác.

**14. “`UNIQUE` trên `TEXT` luôn phân biệt mọi chuỗi khác byte.”** Không tuyệt đối dưới collation nondeterministic; phải xét quy tắc so sánh.

**15. “`VARCHAR(n)` làm tìm kiếm `LIKE '%x%'` nhanh.”** Sai. Chiến lược index tùy mẫu truy vấn và operator class/extension.

**16. “Chỉ cần `ALTER COLUMN TYPE VARCHAR(n)` là luôn an toàn.”** Không. Có thể có dữ liệu quá dài, khóa bảng, thay đổi index hoặc nguy cơ cắt dữ liệu nếu cố tình cast.

**17. “Một cột `TEXT` chắc chắn chiếm nhiều đĩa hơn `VARCHAR(50)`.”** Không. Với cùng nội dung và điều kiện lưu trữ, hai kiểu chuỗi biến thiên thường có chi phí tương tự.

**18. “Khoảng trắng đệm không bao giờ ảnh hưởng truy vấn.”** Sai. Nó ảnh hưởng đo byte, ngữ nghĩa so sánh và các trường hợp pattern matching/cast.

## 18. Bài tập thực hành có đáp án

### Bài 1 — Đếm ký tự và byte

Trong database UTF8, hãy dự đoán:

```sql
SELECT
    char_length('é') AS a,
    octet_length('é') AS b,
    char_length('😀') AS c,
    octet_length('😀') AS d;
```

**Đáp án:** `a=1`, `b=2`, `c=1`, `d=4`. `CHAR_LENGTH` đo ký tự; `OCTET_LENGTH` đo byte.

### Bài 2 — CHAR(5) có đệm không?

```sql
SELECT
    char_length('AB'::CHAR(5)) AS a,
    octet_length('AB'::CHAR(5)) AS b;
```

**Đáp án:** Với ASCII/UTF8, `a=2` và `b=5`. Kiểu character có phần đệm dấu cách dù `char_length` không tính nó.

### Bài 3 — So sánh chuỗi có dấu cách cuối

```sql
SELECT
    'AB'::CHAR(4) = 'AB  '::CHAR(4) AS a,
    'AB'::TEXT = 'AB  '::TEXT AS b;
```

**Đáp án:** Với collation xác định thông thường, `a=true` và `b=false`.

### Bài 4 — Lưu giá trị vượt độ dài

Cột `VARCHAR(4)` lần lượt nhận:

1. `'ABCDE'`.
2. `'ABCD  '`.
3. `'ABCDE'::VARCHAR(4)`.

**Đáp án:** Trường hợp 1 gây lỗi quá dài; trường hợp 2 có thể lưu `ABCD` vì các ký tự vượt n đều là dấu cách; trường hợp 3 bị cắt còn `ABCD` ngay trong phép ép kiểu tường minh.

### Bài 5 — Tên hiển thị không được rỗng

**Yêu cầu:** cột `name` có tối đa 80 ký tự, không cho `NULL`, rỗng hoặc toàn dấu cách ASCII.

**Đáp án:**

```sql
CREATE TABLE pg_string_lab.profile_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    CONSTRAINT chk_profile_name
        CHECK (
            char_length(name) <= 80
            AND char_length(btrim(name)) > 0
        )
);
```

Nếu cần loại cả tab/whitespace Unicode hoặc hạn chế grapheme cluster, phải thiết kế quy tắc kiểm tra nâng cao hơn.

### Bài 6 — Mã đúng hai ký tự

**Yêu cầu:** lưu mã khu vực đúng hai chữ ASCII `A–Z`, không chấp nhận chữ thường hoặc dấu cách.

**Đáp án:** `TEXT` cộng `CHECK (code COLLATE "C" ~ '^[A-Z]{2}$')`, hoặc kiểu chuỗi thích hợp cùng constraint tương đương. `CHAR(2)` đơn lẻ không đủ để từ chối đầu vào một ký tự.

### Bài 7 — Vì sao dùng VARCHAR không phải cách tăng tốc?

Một nhóm muốn đổi cột `description TEXT` sang `VARCHAR(255)` chỉ để giảm thời gian `LIKE '%sale%'`.

**Đáp án:** Giới hạn n không tự thay đổi việc tìm kiếm mẫu chứa wildcard ở đầu. Cần phân tích truy vấn, chọn index/operator class hoặc giải pháp tìm kiếm văn bản phù hợp; đồng thời xem mô tả dài hơn 255 ký tự có bị mất hoặc lỗi không.

### Bài 8 — Sửa lỗi độ dài Java

Java báo `"😀".length() == 2` trong khi PostgreSQL UTF8 báo `char_length('😀') == 1`.

**Đáp án:** Java `String.length()` đếm UTF-16 code units; PostgreSQL `char_length()` đếm ký tự/code point theo encoding. Có thể dùng `codePointCount` ở Java nếu hợp đồng là đếm code point, nhưng cần quy định riêng nếu muốn đếm grapheme clusters.

### Bài 9 — Kiểm tra dữ liệu trước migration

**Yêu cầu:** tìm các giá trị `display_name` dài quá 30 ký tự trước khi đổi kiểu thành `VARCHAR(30)`.

**Đáp án:**

```sql
SELECT id, display_name, char_length(display_name) AS len
FROM pg_string_lab.ho_so
WHERE char_length(display_name) > 30
ORDER BY len DESC, id;
```

Không tự cắt dữ liệu để vượt qua migration nếu chưa có quy tắc nghiệp vụ.

### Bài 10 — Đo độ dài của text đã trim

Một giá trị `'  ABC  '` được nhập vào `TEXT`.

**Hỏi:** `char_length` trước/sau `btrim` bằng bao nhiêu?

**Đáp án:** Trước là **7**, sau là **3**. `btrim` mặc định bỏ các dấu cách thường ở hai đầu, không xóa dấu cách bên trong.

### Bài 11 — Vì sao CHAR(2) không phù hợp với mã phải chính xác 2 ký tự?

Người dùng nhập `'A'` vào cột `code CHAR(2)`, PostgreSQL có thể lưu dạng đệm `'A '`.

**Đáp án:** Kiểu `CHAR(2)` không báo lỗi vì chuỗi ngắn hơn n là hợp lệ; nó đệm thêm. Nếu cần đúng hai ký tự có nghĩa, hãy kiểm tra độ dài/format của đầu vào bằng `TEXT` hoặc `VARCHAR` cùng constraint thích hợp.

### Bài 12 — TEXT hay VARCHAR không giới hạn?

**Yêu cầu:** một cột ghi chú không có giới hạn nghiệp vụ n cụ thể, dữ liệu từ vài chữ đến vài đoạn văn.

**Đáp án:** `TEXT` là lựa chọn tự nhiên trong PostgreSQL. `VARCHAR` không ghi n cũng có hành vi lưu chuỗi biến thiên không giới hạn khai báo, nhưng `TEXT` thường rõ nghĩa và dễ đọc hơn.

## 19. Bảng kiểm lựa chọn kiểu chuỗi

Khi thiết kế một cột mới, có thể đi theo quy trình:

1. **Xác định bản chất dữ liệu:** có phải văn bản, mã định danh, email, UUID, ngày giờ hay một kiểu có ngữ nghĩa chuyên biệt khác?
2. **Xác định giới hạn:** tối đa n ký tự, đúng n ký tự, tối đa n byte hay tối đa n grapheme cluster? Đây là những yêu cầu khác nhau.
3. **Chọn ngữ nghĩa khoảng trắng:** có cần giữ chính xác dấu cách đầu/cuối không? Nếu có, tránh các bất ngờ của `CHAR(n)`.
4. **Quyết định kiểu:** dùng `TEXT` khi không cần typmod; `VARCHAR(n)` khi giới hạn ký tự là một phần rõ ràng của hợp đồng; chỉ dùng `CHAR(n)` khi muốn blank-padding.
5. **Thêm constraint:** `NOT NULL`, `CHECK`, `UNIQUE` và foreign key theo ý nghĩa dữ liệu. Không mong tên kiểu tự giải quyết hết validation.
6. **Xét encoding và normalization:** với UTF8, số byte có thể lớn hơn số ký tự; biểu diễn Unicode kết hợp có thể ảnh hưởng chiều dài.
7. **Thiết kế indexing theo truy vấn:** dấu bằng, tiền tố, tìm chuỗi con và collation cần những chiến lược khác nhau.
8. **Kiểm tra dữ liệu hiện tại trước migration:** tránh cắt dữ liệu vô ý hoặc thay đổi tính duy nhất khi đổi từ `CHAR(n)`.
9. **Đối chiếu API/driver:** Java `String.length()`, giới hạn ở frontend và `char_length` PostgreSQL có thể không cùng khái niệm.
10. **Đo thực tế:** dùng `EXPLAIN`, hàm kích thước và workload đại diện; không tối ưu theo truyền thuyết “VARCHAR(255) nhanh hơn TEXT”.

## 20. Tổng kết

Trong PostgreSQL, **`CHAR(n)` là kiểu có đệm khoảng trắng**, còn **`VARCHAR(n)` giới hạn tối đa n ký tự mà không đệm**; **`TEXT` và `VARCHAR` không ghi n** cho phép lưu chuỗi biến thiên mà không đặt giới hạn n trong khai báo. Không có lợi thế hiệu năng mặc định của `CHAR(n)` so với các kiểu còn lại.

**Chiều dài cần được hiểu đúng theo mục tiêu:**

- `char_length` / `length`: đếm ký tự theo ngữ nghĩa hàm và kiểu đầu vào.
- `octet_length`: đếm byte trong encoding hiện hành.
- `bit_length`: đếm bit.
- `pg_column_size`: đo dạng lưu trữ, không phải giới hạn ký tự nghiệp vụ.

Khi có yêu cầu dữ liệu chặt chẽ, hãy kết hợp **kiểu chuỗi phù hợp + `CHECK`/`UNIQUE` + quy tắc chuẩn hóa + kiểm tra ở biên ứng dụng**. Cẩn thận với **dấu cách cuối của `CHAR(n)`**, **ép kiểu tường minh có thể cắt chuỗi**, **Unicode nhiều byte** và **collation** để tránh dữ liệu không đúng dù câu lệnh SQL vẫn chạy thành công.

Tài liệu tham khảo chính thức:

- [PostgreSQL — Character Types](https://www.postgresql.org/docs/current/datatype-character.html).
- [PostgreSQL — String Functions and Operators](https://www.postgresql.org/docs/current/functions-string.html).
- [PostgreSQL — Collation Support](https://www.postgresql.org/docs/current/collation.html).
- [PostgreSQL — TOAST Storage](https://www.postgresql.org/docs/current/storage-toast.html).
