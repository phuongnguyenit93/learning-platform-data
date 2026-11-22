# SUBSTRING, TRIM, REPLACE và chuẩn hóa văn bản trong SQL

Dữ liệu văn bản trong cơ sở dữ liệu quan hệ thường đến từ nhiều nguồn: biểu mẫu đăng ký, tệp CSV, API, dữ liệu nhập tay hoặc hệ thống cũ. Cùng một tên khách hàng có thể được nhập là `'Nguyen Van An'`, `'  Nguyen Van An  '` hoặc `'Nguyen   Van An'`. Một mã hàng có thể chứa dấu `-` để dễ đọc, trong khi hệ thống đối soát chỉ dùng chữ và số. Nếu so sánh trực tiếp mà không hiểu cách chuỗi được xử lý, các truy vấn tìm kiếm, thống kê và kiểm tra trùng có thể cho kết quả ngoài mong đợi.

Trong SQL, ba nhóm hàm rất thường gặp là:

- **`SUBSTRING` / `SUBSTR`:** lấy một phần văn bản theo vị trí và độ dài.
- **`TRIM` / `LTRIM` / `RTRIM`:** bỏ các ký tự ở đầu hoặc cuối chuỗi, thường là khoảng trắng.
- **`REPLACE`:** thay một chuỗi con xuất hiện trong văn bản bằng chuỗi khác.

Kết hợp các hàm này với `LOWER`, `UPPER`, `CHAR_LENGTH`, `POSITION`, biểu thức chính quy và các quy tắc Unicode sẽ tạo nên một **quy trình chuẩn hóa văn bản**. Tuy nhiên, một thao tác làm sạch hợp lý cho mã hàng chưa chắc phù hợp với tên người, email hoặc địa chỉ: cần xác định **ý nghĩa nghiệp vụ** trước khi thay đổi dữ liệu.

Bài học dùng **PostgreSQL** làm phương ngữ SQL chính để có ví dụ thực hành nhất quán. Phần so sánh cuối bài chỉ ra cú pháp và hành vi cần chú ý trong MySQL, SQL Server và Oracle Database.

## 1. Văn bản được xử lý như thế nào trong SQL?

Một **chuỗi ký tự** (*string*) là dãy ký tự, ví dụ `'Ban phim co'`. Chuỗi có thể chứa khoảng trắng, chữ số, dấu câu, ký tự Unicode, thậm chí các ký tự điều khiển tùy kiểu dữ liệu và DBMS. Trong SQL, hằng chuỗi thường được viết trong **dấu nháy đơn**:

~~~sql
SELECT
    'Ban phim co' AS ten_san_pham,
    'SP-001-A' AS ma_san_pham;
~~~

Dấu nháy kép có mục đích khác trong SQL chuẩn: trích dẫn **định danh** (tên bảng/cột), ví dụ `"Ten Khach Hang"`. Không dùng nháy kép để biểu diễn chuỗi văn bản khi viết SQL theo quy tắc PostgreSQL.

Cần phân biệt:

| Giá trị | Ý nghĩa | Hệ quả khi xử lý |
| --- | --- | --- |
| `'ABC'` | Chuỗi có ba ký tự Latin cơ bản | Có thể cắt theo vị trí ký tự |
| `' ABC '` | Có một khoảng trắng ở mỗi đầu | `TRIM` thông thường có thể đưa về `'ABC'` |
| `'A  B'` | Có hai khoảng trắng **ở giữa** | `TRIM` không tự rút gọn khoảng trắng nội bộ |
| `''` | Chuỗi rỗng trong PostgreSQL | Không phải `NULL` |
| `NULL` | Chưa có/không xác định giá trị | Không phải chuỗi có bốn chữ cái `'NULL'` |
| `'Tiếng Việt'` | Chuỗi Unicode | Số ký tự không nhất thiết bằng số byte UTF-8 |

Hầu hết các hàm chuỗi thông thường trả `NULL` khi đối số văn bản đầu vào là `NULL`. Một biểu thức chuẩn hóa dùng để đối chiếu dữ liệu cần quyết định rõ **giữ `NULL`** hay **thay bằng giá trị khác**, vì hai hành vi mang ý nghĩa nghiệp vụ khác nhau.

### 1.1. Chiều dài ký tự khác chiều dài byte

Trong PostgreSQL với encoding UTF-8:

~~~sql
SELECT
    char_length('SQL') AS so_ky_tu,
    octet_length('SQL') AS so_byte;
~~~

Cả hai đều là `3` với chuỗi ASCII `SQL`. Nhưng ký tự tiếng Việt thường chiếm nhiều byte UTF-8:

~~~sql
SELECT
    char_length('Đ') AS so_ky_tu,
    octet_length('Đ') AS so_byte;
~~~

Với chữ `Đ` được biểu diễn theo Unicode thông dụng, `char_length` là `1` còn `octet_length` là `2`. Hàm `SUBSTRING` trên **kiểu văn bản** trong PostgreSQL sử dụng vị trí ký tự, không phải vị trí byte của chuỗi đã mã hóa. Khi xử lý byte của tệp hay giao thức, phải dùng kiểu nhị phân và hàm nhị phân tương ứng.

Một điểm sâu hơn: **ký tự được đếm theo chuỗi Unicode** cũng không phải lúc nào trùng với “một ký tự mà mắt người nhìn thấy”. Chữ có dấu có thể là một code point dựng sẵn hoặc gồm chữ cơ bản cộng dấu kết hợp; emoji phức tạp có thể gồm nhiều code point. Vì thế không nên lấy `SUBSTRING` theo số ký tự của DBMS để thay thế hoàn toàn một bộ xử lý cụm ký tự (*grapheme cluster*) của giao diện người dùng.

## 2. SUBSTRING: lấy một phần văn bản

`SUBSTRING` nhận một biểu thức chuỗi, vị trí bắt đầu và thường thêm độ dài cần lấy. Cú pháp gần với SQL chuẩn trong PostgreSQL:

~~~sql
SUBSTRING(chuoi FROM vi_tri FOR do_dai)
~~~

Ví dụ:

~~~sql
SELECT
    SUBSTRING('ABCDEFG' FROM 2 FOR 3) AS doan_1,
    SUBSTRING('ABCDEFG' FROM 5) AS doan_2;
~~~

Kết quả:

| doan_1 | doan_2 |
| --- | --- |
| `BCD` | `EFG` |

Trong PostgreSQL, **vị trí ký tự bắt đầu từ 1**: `A` ở vị trí 1, `B` ở vị trí 2. Độ dài `3` nghĩa là lấy ba ký tự. Nếu không có `FOR`, truy vấn lấy từ vị trí bắt đầu đến cuối chuỗi.

### 2.1. Những trường hợp ranh giới

~~~sql
SELECT
    SUBSTRING('ABCDE' FROM 1 FOR 2) AS hai_ky_tu_dau,
    SUBSTRING('ABCDE' FROM 4 FOR 99) AS vuot_dai,
    SUBSTRING('ABCDE' FROM 3 FOR 0) AS do_dai_khong;
~~~

Trong PostgreSQL:

- `hai_ky_tu_dau` là `'AB'`;
- `vuot_dai` là `'DE'` vì chuỗi kết thúc trước khi đạt 99 ký tự;
- `do_dai_khong` là `''`, một chuỗi rỗng.

Không nên giả định cách xử lý vị trí âm, vị trí 0 hoặc độ dài âm **giống nhau giữa các DBMS**. Khi thiết kế thuật toán cắt chuỗi, nên dùng vị trí dương và kiểm tra tính hợp lệ của độ dài; nếu cần cắt từ cuối chuỗi, có thể dùng hàm riêng như `RIGHT` (nếu DBMS hỗ trợ) hoặc công thức đã được kiểm tra.

### 2.2. Cắt mã có cấu trúc cố định

Giả sử mã sản phẩm luôn có định dạng `SP-2026-0007`:

~~~sql
SELECT
    SUBSTRING('SP-2026-0007' FROM 1 FOR 2) AS loai,
    SUBSTRING('SP-2026-0007' FROM 4 FOR 4) AS nam,
    SUBSTRING('SP-2026-0007' FROM 9 FOR 4) AS so_thu_tu;
~~~

Kết quả lần lượt là `SP`, `2026`, `0007`. Cách dùng vị trí cố định **chỉ đúng khi định dạng được bảo đảm**. Nếu dữ liệu có mã `SP-26-7` hoặc dấu phân cách khác, cắt theo vị trí sẽ trả phần sai mà không nhất thiết phát sinh lỗi SQL.

Khi mã có định dạng thay đổi, cần quy tắc phân tách thích hợp, chẳng hạn tìm vị trí dấu phân cách bằng `POSITION`, dùng `SPLIT_PART` trong PostgreSQL, hoặc hàm xử lý biểu thức chính quy. Với mã nhận dạng quan trọng, có thể ràng buộc định dạng ở nơi ghi.

### 2.3. Kết hợp với POSITION khi không biết vị trí trước

Ví dụ muốn lấy phần đứng trước ký tự `@`:

~~~sql
SELECT
    SUBSTRING('an@example.com' FROM 1
        FOR POSITION('@' IN 'an@example.com') - 1
    ) AS phan_truoc_a_cong;
~~~

Kết quả là `an`. `POSITION('@' IN chuoi)` trong PostgreSQL trả vị trí xuất hiện đầu tiên của `@`, hoặc `0` khi không tìm thấy. Vì vậy **cần kiểm tra có dấu phân cách trước khi trừ 1**:

~~~sql
SELECT
    CASE
        WHEN POSITION('@' IN email) > 0
            THEN SUBSTRING(email FROM 1
                FOR POSITION('@' IN email) - 1)
        ELSE NULL
    END AS phan_truoc_a_cong
FROM (VALUES
    ('an@example.com'),
    ('du_lieu_khong_co_a_cong'),
    (NULL)
) AS v(email);
~~~

`CASE` ở đây diễn đạt rõ rằng chuỗi không có `@` không cho kết quả chia hợp lệ. Đây mới chỉ là **tách theo dấu**, không chứng minh đầu vào là địa chỉ email đúng tiêu chuẩn.

## 3. TRIM: bỏ ký tự ở hai đầu chuỗi

`TRIM` được dùng để bỏ ký tự không mong muốn ở **đầu và/hoặc cuối** một chuỗi. Mặc định, cách dùng phổ biến bỏ dấu cách thông thường:

~~~sql
SELECT
    TRIM('   Ban phim   ') AS ca_hai_dau;
~~~

Kết quả là `'Ban phim'`.

Có ba lựa chọn hướng:

~~~sql
SELECT
    TRIM(LEADING  FROM '   SQL   ') AS bo_dau,
    TRIM(TRAILING FROM '   SQL   ') AS bo_cuoi,
    TRIM(BOTH     FROM '   SQL   ') AS bo_hai_dau;
~~~

Trong PostgreSQL:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `TRIM(LEADING FROM '   SQL   ')` | `'SQL   '` | Bỏ khoảng trắng ở đầu |
| `TRIM(TRAILING FROM '   SQL   ')` | `'   SQL'` | Bỏ khoảng trắng ở cuối |
| `TRIM(BOTH FROM '   SQL   ')` | `'SQL'` | Bỏ cả hai đầu |

Hàm riêng của PostgreSQL tương ứng là `ltrim(text)`, `rtrim(text)`, `btrim(text)`. Tên và hành vi mặc định của các hàm riêng có thể khác giữa DBMS; `TRIM` dạng chuẩn thường dễ chuyển đổi hơn.

### 3.1. TRIM không loại bỏ khoảng trắng ở giữa

~~~sql
SELECT
    TRIM('  Nguyen   Van   An  ') AS ho_ten_da_trim;
~~~

Kết quả là `'Nguyen   Van   An'`. Ba dấu cách giữa các từ vẫn còn. Nếu yêu cầu **một dấu cách giữa các từ**, cần bước khác, không thể chỉ dùng `TRIM`.

### 3.2. Chỉ định ký tự cần bỏ

PostgreSQL hỗ trợ:

~~~sql
SELECT
    TRIM(BOTH '-' FROM '---SP-001---') AS ma_da_trim;
~~~

Kết quả là `'SP-001'`. Dấu `-` **ở giữa** vẫn được giữ, vì `TRIM` chỉ bỏ ký tự ở biên.

PostgreSQL còn hỗ trợ hàm `btrim(text, characters)`:

~~~sql
SELECT
    btrim('..--ABC--..', '.-') AS ket_qua;
~~~

Kết quả là `'ABC'`. Ở đây đối số `'.-'` của **`btrim` PostgreSQL** là **tập ký tự**, nghĩa là mỗi dấu `.` hoặc `-` ở hai đầu đều được bỏ cho đến khi gặp ký tự khác. Không phải yêu cầu khớp nguyên chuỗi `'.-'` ở biên.

**Không suy rộng cơ chế “tập ký tự” sang mọi hệ quản trị.** Chẳng hạn MySQL hỗ trợ `TRIM(BOTH remstr FROM str)`, trong đó `remstr` được xử lý như **chuỗi cần loại bỏ lặp lại ở biên**. Với bộ ký tự nhiều phần tử, kết quả có thể khác `btrim` của PostgreSQL.

### 3.3. Khoảng trắng thường, tab, xuống dòng và Unicode

Mặc định `TRIM` không phải một công cụ tổng quát để xóa mọi loại ký tự được con người nhìn nhận là khoảng trắng. Dữ liệu nguồn có thể chứa:

- Dấu cách thông thường `U+0020`;
- Tab `U+0009`, xuống dòng `U+000A`, carriage return `U+000D`;
- Dấu cách không ngắt dòng (*no-break space*, `U+00A0`);
- Những ký tự khoảng trắng Unicode khác.

Ví dụ PostgreSQL khi biết rõ ký tự cần bỏ:

~~~sql
SELECT
    btrim(E'\t  Ban phim  \n', E' \t\n\r') AS ket_qua;
~~~

Kết quả là `'Ban phim'`: đối số thứ hai liệt kê những ký tự biên cần loại. Nếu dữ liệu có NBSP, danh sách phải được thiết kế phù hợp thay vì mặc định rằng `TRIM` sẽ xóa nó.

**Lưu ý:** `TRIM` dùng với dữ liệu văn bản sạch là một thao tác hữu ích, nhưng việc bỏ tab/xuống dòng có thể **làm mất thông tin định dạng** đối với nội dung nhiều dòng. Cần phân biệt cột tên/mã và cột nội dung tự do.

## 4. REPLACE: thay thế chuỗi con

`REPLACE` thay các lần xuất hiện của **một chuỗi con** bằng chuỗi khác. Trong PostgreSQL, cú pháp:

~~~sql
REPLACE(chuoi_nguon, chuoi_can_thay, chuoi_thay_the)
~~~

Ví dụ:

~~~sql
SELECT
    REPLACE('SP-2026-0007', '-', '') AS ma_khong_gach,
    REPLACE('A_B_C', '_', '-') AS ma_doi_dau;
~~~

Kết quả:

| ma_khong_gach | ma_doi_dau |
| --- | --- |
| `SP20260007` | `A-B-C` |

`REPLACE` xử lý **các lần xuất hiện của chuỗi con**, không chỉ một lần đầu tiên. Nó thường hữu ích để xóa ký tự phân cách, đổi quy ước dấu hoặc sửa một đoạn văn bản biết trước.

### 4.1. REPLACE khác TRIM

~~~sql
SELECT
    TRIM(BOTH '-' FROM '--A-B--') AS trim_ket_qua,
    REPLACE('--A-B--', '-', '') AS replace_ket_qua;
~~~

Kết quả:

| trim_ket_qua | replace_ket_qua |
| --- | --- |
| `A-B` | `AB` |

`TRIM` chỉ bỏ dấu `-` ở hai đầu. `REPLACE` xóa **mọi** dấu `-` trong chuỗi. Nếu dấu `-` là một phần có nghĩa của mã, dùng `REPLACE` có thể tạo xung đột: `AB-12` và `A-B12` đều có thể thành `AB12`. Cần xác định trước liệu việc bỏ dấu có được nghiệp vụ cho phép không.

### 4.2. REPLACE không hiểu biểu thức chính quy

~~~sql
SELECT
    REPLACE('A   B', ' ', '') AS xoa_dau_cach,
    REPLACE('A   B', '  ', ' ') AS thay_hai_dau;
~~~

Biểu thức đầu loại **tất cả** dấu cách, trả `AB`. Biểu thức thứ hai chỉ thay những lần xuất hiện của **hai dấu cách liền nhau**, không tự hiểu “một hoặc nhiều dấu cách”. Muốn thay **mọi chuỗi khoảng trắng liên tiếp** bằng một dấu cách, nên dùng hàm regex thích hợp, chẳng hạn `regexp_replace` trong PostgreSQL.

`REPLACE` còn có điểm khác so với một số công cụ tìm và thay thế thông minh: nó không tự động xử lý biến thể chữ hoa/thường, dấu tiếng Việt hoặc Unicode normalization như một quy tắc nghiệp vụ. Trong các tình huống cần chuẩn hóa theo tập ký tự rộng, phải định nghĩa thêm bước xử lý.

### 4.3. REPLACE lồng nhau: thực thi theo thứ tự

~~~sql
SELECT
    REPLACE(
        REPLACE('AB--CD  EF', '--', '-'),
        '  ', ' '
    ) AS ket_qua;
~~~

Kết quả là `'AB-CD EF'`. Hàm bên trong chạy theo ý nghĩa biểu thức trước, hàm bên ngoài xử lý kết quả đó. Với nhiều quy tắc làm sạch, **thứ tự có thể thay đổi kết quả**. Không nên xếp nhiều `REPLACE` lồng nhau mà không giải thích thứ tự và trường hợp ngoại lệ.

## 5. Tạo bộ dữ liệu thực hành

Các ví dụ tiếp theo dùng một bảng tạm trong PostgreSQL, giúp quan sát dữ liệu nguồn và kết quả chuẩn hóa mà chưa cập nhật dữ liệu thật:

~~~sql
CREATE TEMP TABLE lien_he_mau (
    id INTEGER PRIMARY KEY,
    ho_ten TEXT,
    email TEXT,
    ma_khach_hang TEXT,
    ghi_chu TEXT
);

INSERT INTO lien_he_mau
    (id, ho_ten, email, ma_khach_hang, ghi_chu)
VALUES
    (1, '  Nguyen Van An  ', '  AN@example.com  ', 'KH-001', '  Khach moi  '),
    (2, 'Nguyen   Van   An', 'an@example.com', 'KH001', NULL),
    (3, '  Tran Thi Binh',  'BINH@EXAMPLE.COM', 'KH-002', '  Goi lai'),
    (4, 'Le Minh Chi  ',     NULL, 'KH-003', 'Cho phan hoi  '),
    (5, '',                 '   ', 'KH-004', ''),
    (6, NULL,               NULL, 'KH-005', NULL);
~~~

Trong bảng này:

- Dòng 1 có dấu cách ở hai đầu tên và email;
- Dòng 2 có nhiều dấu cách **giữa** các từ trong tên;
- Email dòng 1 và 2 trông như cùng địa chỉ sau khi bỏ khoảng trắng biên và xử lý chữ hoa/thường theo quy tắc ví dụ;
- Dòng 5 có chuỗi rỗng ở tên, còn email chứa ba dấu cách;
- Dòng 6 thật sự có `NULL`.

Tập dữ liệu được cố ý làm chưa chuẩn để minh họa truy vấn. Không nên kết luận hai khách hàng ở dòng 1 và 2 là **cùng một người** chỉ vì tên hoặc email sau chuẩn hóa giống nhau; việc hợp nhất bản ghi cần quy tắc danh tính và quyết định nghiệp vụ riêng.

## 6. Kết hợp SUBSTRING, TRIM và REPLACE trên cột thật

### 6.1. Bỏ khoảng trắng hai đầu

~~~sql
SELECT
    id,
    ho_ten AS ten_goc,
    TRIM(ho_ten) AS ten_da_trim,
    email AS email_goc,
    TRIM(email) AS email_da_trim
FROM lien_he_mau
ORDER BY id;
~~~

Với dòng 1, `TRIM(ho_ten)` trả `'Nguyen Van An'`; `TRIM(email)` trả `'AN@example.com'`. Với dòng 2, `TRIM(ho_ten)` vẫn là `'Nguyen   Van   An'` vì các khoảng trắng dư nằm ở giữa. Dòng 5 có `ho_ten = ''` và `email = '   '`; sau `TRIM`, cả hai thành `''`, **khác `NULL` trong PostgreSQL**.

### 6.2. Loại dấu phân cách trong mã

~~~sql
SELECT
    id,
    ma_khach_hang AS ma_goc,
    REPLACE(ma_khach_hang, '-', '') AS ma_khong_dau
FROM lien_he_mau
ORDER BY id;
~~~

Sau bước thay thế, cả `'KH-001'` và `'KH001'` đều thành `'KH001'`. Đối với mã mà dấu `-` chỉ là định dạng hiển thị, đây có thể là cách tạo **khóa đối chiếu**. Nhưng đối với hệ thống mà `KH-001` và `KH001` có nghĩa khác nhau, phép thay thế đã gây **va chạm**.

### 6.3. Chỉ lấy phần tiền tố của mã

Nếu mã khách luôn bắt đầu bằng hai chữ:

~~~sql
SELECT
    ma_khach_hang,
    SUBSTRING(ma_khach_hang FROM 1 FOR 2) AS tien_to
FROM lien_he_mau;
~~~

Với dữ liệu mẫu, tiền tố là `KH`. Tuy nhiên, nếu mã có thể là `K-001` hoặc `VIP-001`, cắt hai ký tự đầu không còn tương đương với tách **nhóm khách hàng**. Chọn `SUBSTRING` theo vị trí cố định chỉ khi cấu trúc mã đã được kiểm soát.

### 6.4. Tạo khóa so khớp từ nhiều bước

Trong PostgreSQL:

~~~sql
SELECT
    id,
    email,
    lower(btrim(email)) AS email_khoa_so_khop,
    replace(btrim(ma_khach_hang), '-', '') AS ma_khoa_so_khop
FROM lien_he_mau
ORDER BY id;
~~~

Ở đây `btrim` bỏ khoảng trắng biên, `lower` chuyển các ký tự có dạng chữ hoa theo quy tắc DBMS/collation, còn `replace` bỏ dấu `-` trong mã. Giá trị `NULL` tiếp tục là `NULL`, trừ khi dùng thêm một phép xử lý riêng.

**Khóa so khớp** là biểu diễn kỹ thuật để tìm các giá trị tương tự; nó không nhất thiết là giá trị nên hiển thị cho người dùng. Nên lưu/giữ dữ liệu gốc khi cần đối chiếu, truy vết hoặc khôi phục.

## 7. Chuẩn hóa khoảng trắng bên trong văn bản

`TRIM` chỉ xử lý ở biên. Để rút gọn nhiều khoảng trắng liên tiếp trong nội dung thành một dấu cách, PostgreSQL cung cấp `regexp_replace`:

~~~sql
SELECT
    regexp_replace(
        btrim('  Nguyen   Van   An  '),
        '[[:space:]]+',
        ' ',
        'g'
    ) AS ho_ten;
~~~

Kết quả là `'Nguyen Van An'`. Những thành phần chính:

- `btrim(...)`: bỏ khoảng trắng thông thường ở hai đầu;
- `[[:space:]]+`: biểu thức chính quy khớp một hoặc nhiều ký tự thuộc lớp khoảng trắng theo bộ quy tắc regex/collation của PostgreSQL;
- `' '`: thay chuỗi khớp bằng một dấu cách;
- `'g'`: thay **mọi lần khớp**, không chỉ lần đầu.

Ví dụ trên phù hợp cho dữ liệu tên ngắn được phép chuẩn hóa khoảng trắng. Nhưng với địa chỉ nhiều dòng, đoạn mô tả hoặc dữ liệu định dạng sẵn, đổi tất cả tab/xuống dòng thành dấu cách sẽ **làm mất cấu trúc**.

### 7.1. Phân biệt khoảng trắng ASCII và Unicode

Lớp `[[:space:]]` trong regex không bảo đảm được mọi ứng dụng/DBMS diễn giải giống nhau đối với **toàn bộ các ký tự whitespace Unicode**. Nếu nguồn dữ liệu có NBSP (`U+00A0`), zero-width space hay các ký tự điều khiển hiếm gặp, cần xác định rõ bộ ký tự được coi là khoảng trắng trong nghiệp vụ và thử đúng cấu hình encoding/collation.

Với một ký tự cụ thể cần thay, `REPLACE` thường rõ ràng hơn regex. Ví dụ PostgreSQL có thể thay tab bằng dấu cách:

~~~sql
SELECT REPLACE(E'An\tBinh', E'\t', ' ') AS sau_thay;
~~~

Nếu dữ liệu có **nhiều loại whitespace khác nhau**, một pipeline quy định rõ các loại ký tự được chấp nhận sẽ dễ kiểm soát hơn việc giả định một lệnh `TRIM` mặc định luôn làm sạch tất cả.

### 7.2. Thứ tự xử lý thường dùng

Đối với một **trường tên người** nếu nghiệp vụ cho phép rút gọn whitespace:

~~~sql
SELECT
    id,
    ho_ten,
    NULLIF(
        regexp_replace(btrim(ho_ten), '[[:space:]]+', ' ', 'g'),
        ''
    ) AS ho_ten_chuan_hoa
FROM lien_he_mau
ORDER BY id;
~~~

Ý nghĩa:

1. `btrim` bỏ khoảng trắng ở hai đầu;
2. `regexp_replace` rút các nhóm khoảng trắng nội bộ;
3. `NULLIF(..., '')` chuyển **chuỗi rỗng sau làm sạch** thành `NULL`, nếu quy tắc ứng dụng xem tên rỗng là “chưa có”.

`NULLIF` chỉ nên được sử dụng khi đã thống nhất rằng chuỗi rỗng và dữ liệu thiếu có cùng ý nghĩa. Có những miền dữ liệu cần giữ khác biệt giữa “người dùng nhập chuỗi rỗng” và “chưa bao giờ nhập”.

## 8. LOWER, UPPER và các phép chuẩn hóa chữ

`LOWER` chuyển văn bản sang chữ thường, `UPPER` chuyển sang chữ hoa theo quy tắc DBMS/collation. Đây là các phép biến đổi thường được dùng cùng `TRIM` khi tìm kiếm không phân biệt hoa/thường:

~~~sql
SELECT
    lower('SQL Server') AS chu_thuong,
    upper('postgresql') AS chu_hoa;
~~~

Kết quả minh họa với chữ Latin cơ bản là `'sql server'` và `'POSTGRESQL'`.

### 8.1. Chuẩn hóa giá trị để so khớp

~~~sql
SELECT
    id,
    email,
    lower(btrim(email)) AS email_doi_chieu
FROM lien_he_mau
WHERE lower(btrim(email)) = 'an@example.com'
ORDER BY id;
~~~

Với quy tắc so khớp đơn giản trong ví dụ và dữ liệu mẫu, các ID phù hợp là `1` và `2`. Nhưng đối với email thật, **phần domain** được so sánh không phân biệt hoa/thường, còn quy tắc chuẩn hóa phần local-part và các biến thể như dấu `+` hoặc dấu chấm phải được quyết định theo yêu cầu tài khoản/nhà cung cấp. Không nên tự ý xóa dấu `+`, bỏ dấu chấm hoặc gộp mọi địa chỉ có vẻ giống nhau.

### 8.2. Chữ hoa/thường phụ thuộc ngôn ngữ và collation

Quy tắc viết hoa/thường không phải luôn là phép thay 26 chữ cái ASCII. Các ngôn ngữ có ký tự đặc thù, ví dụ chữ `I`/`i` trong tiếng Thổ Nhĩ Kỳ, có thể chịu ảnh hưởng từ locale/collation. Không được mặc định `LOWER` của mọi DBMS và mọi cấu hình sẽ tạo cùng chuỗi byte cho mọi văn bản Unicode.

Nếu ứng dụng cần so sánh không phân biệt hoa/thường ở mức người dùng, cần xác định rõ:

- Collation và locale của cột/truy vấn;
- Bộ quy tắc so khớp chữ hoa/thường, dấu và Unicode;
- Cách chuẩn hóa cả **dữ liệu được lưu** lẫn **tham số truy vấn**;
- Cách thực thi ràng buộc duy nhất theo biểu diễn đã chuẩn hóa.

Với PostgreSQL có thể cân nhắc **expression index** trên `lower(...)` hoặc kiểu `citext` qua extension trong trường hợp phù hợp. Những lựa chọn này không đồng nghĩa với việc giải quyết toàn bộ vấn đề Unicode hoặc định danh nghiệp vụ.

### 8.3. Unicode normalization: chuỗi nhìn giống có thể khác byte

Một chữ có dấu có thể biểu diễn theo nhiều cách Unicode. Ví dụ chữ `é` có thể là:

- **NFC:** một code point dựng sẵn `U+00E9`;
- **NFD:** `U+0065` (chữ `e`) và `U+0301` (dấu sắc kết hợp).

Hai chuỗi có thể nhìn giống nhau nhưng có dãy code point và số byte khác nhau. Trong PostgreSQL có encoding UTF-8, có thể dùng `normalize(text, NFC)` khi cần chuẩn hóa Unicode:

~~~sql
SELECT
    normalize(U&'\0065\0301', NFC) = U&'\00E9'
        AS hai_cach_bieu_dien_tuong_duong;
~~~

Kết quả là `TRUE` với biểu diễn Unicode được nêu. Cú pháp `U&'...'` của PostgreSQL tạo chuỗi từ ký tự Unicode escape, tránh phụ thuộc vào cách trình soạn thảo tự động chuẩn hóa.

Unicode normalization **không giống** chuyển thành chữ thường, bỏ dấu hay phiên âm sang ASCII. Đặc biệt, **NFD/NFC không có nghĩa là “xóa dấu tiếng Việt”**. Nếu một hệ thống cần tìm kiếm không phân biệt dấu, nên xem xét collation, bộ máy tìm kiếm hoặc cơ chế phù hợp, đồng thời giữ nguyên tên gốc để hiển thị.

## 9. Thiết kế quy trình chuẩn hóa có chủ đích

Không có một công thức chung đúng cho tên người, mã sản phẩm, email, địa chỉ và nội dung tự do. Nên tách rõ:

- **Dữ liệu gốc** (*raw/display value*): được lưu hoặc hiển thị để giữ nguyên ý định của người nhập;
- **Giá trị chuẩn hóa** (*normalized/canonical value*): dùng cho so sánh, tìm kiếm, lọc hoặc đối soát theo quy tắc đã định;
- **Quy tắc nghiệp vụ**: định nghĩa loại thay đổi được phép, giá trị rỗng, phạm vi duy nhất và phiên bản của phép chuẩn hóa.

### 9.1. Ví dụ: chuẩn hóa mã sản phẩm

Giả sử **quy ước nghiệp vụ** nói rằng mã hàng không phân biệt chữ hoa/thường và dấu gạch nối `-` chỉ phục vụ hiển thị. Ta có thể tạo khóa đối chiếu:

~~~sql
SELECT
    ma_khach_hang AS ma_goc,
    upper(replace(btrim(ma_khach_hang), '-', '')) AS ma_so_khop
FROM lien_he_mau
ORDER BY id;
~~~

Theo quy ước đó, `'KH-001'` và `'KH001'` có khóa giống nhau. Điều này **đúng khi dấu gạch nối thực sự không có ý nghĩa**. Nếu dấu `-` phân chia mã loại hàng và mã kho, xóa nó có thể làm mất thông tin và tạo khóa giả trùng.

Một cách tiếp cận thận trọng là lưu cả `ma_goc` và `ma_chuan_hoa` (nếu cần), nhưng đặt ràng buộc hoặc công thức sinh để tránh hai giá trị không nhất quán. Không nên để mỗi dịch vụ tự chuẩn hóa theo một quy tắc khác nhau.

### 9.2. Ví dụ: email dùng để so khớp

Với một chính sách đơn giản đã được ứng dụng chấp nhận:

~~~sql
SELECT
    id,
    NULLIF(lower(btrim(email)), '') AS email_key
FROM lien_he_mau
ORDER BY id;
~~~

`email_key` của dòng 1 và 2 đều trở thành `'an@example.com'`. Dòng 5 biến thành `NULL` do sau khi trim còn chuỗi rỗng. Dòng 6 giữ `NULL`.

Đây là một **quy tắc chuẩn hóa phục vụ minh họa**, không phải bộ kiểm tra cú pháp email hoàn chỉnh, cũng không tự kết luận hai khách hàng là cùng một người. Nếu email dùng để đăng nhập, hệ thống còn phải xử lý xác minh quyền sở hữu email, đăng ký trùng và chính sách đổi email.

### 9.3. Ví dụ: chuẩn hóa tên hiển thị

~~~sql
SELECT
    id,
    ho_ten AS ten_goc,
    NULLIF(
        regexp_replace(btrim(ho_ten), '[[:space:]]+', ' ', 'g'),
        ''
    ) AS ten_hien_thi_goi_y
FROM lien_he_mau
ORDER BY id;
~~~

Phép làm sạch khoảng trắng có thể hữu ích cho tên trong nhiều ứng dụng. Tuy vậy không nên **xóa dấu**, tự động viết hoa đầu mỗi từ hoặc đảo thứ tự họ tên nếu yêu cầu chỉ là loại khoảng trắng thừa. Tên người có nhiều quy ước ngôn ngữ và cách viết hợp lệ; ứng dụng nên cho phép người dùng xác nhận tên hiển thị cuối cùng.

### 9.4. Giữ phép biến đổi có thể lặp lại

Một pipeline chuẩn hóa tốt thường có tính **idempotent**: chạy lại trên dữ liệu đã chuẩn hóa không tiếp tục thay đổi kết quả, ví dụ với phép `btrim` và rút gọn khoảng trắng thông thường. Với các phép thay thế có thể tạo ra chuỗi con mới tiếp tục khớp trong vòng sau, tính chất này không còn tự động đúng. Khi chuẩn hóa dữ liệu hàng loạt hoặc đồng bộ nhiều lần, cần quy định rõ phép biến đổi và điều kiện dừng.

Không nên coi sự ổn định của kết quả trên vài mẫu là bằng chứng rằng một pipeline tự viết xử lý đúng mọi ngôn ngữ hoặc mọi dữ liệu Unicode. Phạm vi đầu vào phải được thiết kế rõ ràng.

## 10. NULL, chuỗi rỗng và chuỗi toàn khoảng trắng

Đây là nguồn nhầm lẫn đặc biệt thường gặp khi nhập liệu:

~~~sql
SELECT
    TRIM(NULL::text) AS trim_null,
    TRIM('') AS trim_rong,
    TRIM('   ') AS trim_chi_co_khoang_trang;
~~~

Trong PostgreSQL:

| Đầu vào | Sau TRIM | Ý nghĩa |
| --- | --- | --- |
| `NULL` | `NULL` | Vẫn chưa có dữ liệu |
| `''` | `''` | Chuỗi rỗng |
| `'   '` | `''` | Hết ký tự sau khi bỏ khoảng trắng biên |

Muốn quy ước mọi chuỗi rỗng sau trim thành `NULL`:

~~~sql
SELECT NULLIF(TRIM('   '), '') AS ket_qua;
~~~

Kết quả là `NULL`. Muốn thay `NULL` bằng một giá trị hiển thị mặc định, có thể dùng `COALESCE`:

~~~sql
SELECT COALESCE(NULLIF(TRIM('   '), ''), '(chua cung cap)') AS hien_thi;
~~~

Kết quả là chuỗi `'(chua cung cap)'`. Nhưng **không nên dùng chuỗi này làm dữ liệu gốc để lưu** nếu nghiệp vụ cần phân biệt thực sự chưa có giá trị.

Trong **Oracle**, chuỗi ký tự rỗng `''` thường được xử lý như `NULL` với các kiểu chuỗi thông dụng. Vì vậy phép biến đổi và ràng buộc có thể khác PostgreSQL, nhất là khi dữ liệu từ ứng dụng có chuỗi rỗng. Khi chuyển một quy trình nhập liệu giữa DBMS, phải kiểm tra hành vi này thay vì cho rằng `''` luôn tồn tại như một chuỗi độ dài 0.

## 11. Chuẩn hóa trong truy vấn và chuẩn hóa khi lưu

Có hai chiến lược thường gặp:

**Chiến lược A — Chuẩn hóa khi đọc:** giữ dữ liệu gốc, tính biểu thức trong `SELECT`, `WHERE`, `JOIN`, `GROUP BY`.

~~~sql
SELECT id, email
FROM lien_he_mau
WHERE lower(btrim(email)) = 'an@example.com';
~~~

**Chiến lược B — Chuẩn hóa khi ghi:** ứng dụng hoặc database tính một cột chuẩn hóa nhất quán, lưu giá trị đó hoặc tạo cột generated/index biểu thức. Truy vấn sau này sử dụng khóa chuẩn hóa.

Hai chiến lược có ưu và nhược điểm:

| Tiêu chí | Chuẩn hóa khi đọc | Chuẩn hóa khi ghi / bằng cột/index chuyên dụng |
| --- | --- | --- |
| Giữ dữ liệu gốc | Dễ giữ nguyên nếu không UPDATE | Nên lưu riêng giá trị gốc khi cần |
| Triển khai ban đầu | Thường nhanh, một biểu thức trong truy vấn | Cần định nghĩa schema/migration hoặc quy tắc cập nhật |
| Tính nhất quán | Dễ khác nhau nếu từng truy vấn viết công thức khác | Có thể tập trung một quy tắc |
| Hiệu năng | Hàm trên cột có thể làm chỉ mục thường ít hữu ích | Có thể hỗ trợ index trên khóa chuẩn hóa |
| Đổi chính sách chuẩn hóa | Đổi biểu thức đọc; cần kiểm tra các nơi dùng | Có thể phải tái tính/backfill hoặc xây lại index |

### 11.1. Tìm trùng sau chuẩn hóa

Với dữ liệu mẫu, tìm các khóa email xuất hiện nhiều lần:

~~~sql
SELECT
    lower(btrim(email)) AS email_key,
    COUNT(*) AS so_hang,
    array_agg(id ORDER BY id) AS danh_sach_id
FROM lien_he_mau
WHERE email IS NOT NULL
  AND btrim(email) <> ''
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1
ORDER BY email_key;
~~~

Trong PostgreSQL, truy vấn tìm thấy khóa `an@example.com` ở hai dòng `1` và `2`. `array_agg` là hàm tổng hợp PostgreSQL để hiển thị các ID cùng nhóm; DBMS khác có hàm ghép danh sách riêng. **Dòng trùng khóa so khớp** là tín hiệu cần đối chiếu, không phải chỉ thị tự động xóa hoặc hợp nhất khách hàng.

### 11.2. UNIQUE index trên biểu thức chuẩn hóa

Nếu nghiệp vụ yêu cầu email đã nhập phải duy nhất theo `lower(btrim(email))`, PostgreSQL hỗ trợ:

~~~sql
CREATE TABLE tai_khoan_thu (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT
);

CREATE UNIQUE INDEX ux_tai_khoan_email_key
ON tai_khoan_thu (lower(btrim(email)))
WHERE email IS NOT NULL
  AND btrim(email) <> '';
~~~

Index này kiểm soát **giá trị biểu thức chuẩn hóa** trên các hàng có email không rỗng theo điều kiện. Nó không phải ràng buộc kiểm tra cú pháp email và không tự buộc cột phải có email. Nếu muốn cấm email rỗng hoặc toàn dấu cách, nên bổ sung `CHECK`/validation phù hợp.

**Lưu ý:** bảng `lien_he_mau` đã có hai giá trị email trùng sau chuẩn hóa. Nếu tạo unique index tương tự trực tiếp trên bảng đó, lệnh sẽ bị từ chối cho đến khi dữ liệu được xử lý. Không xóa một bản ghi chỉ để thỏa index khi chưa có quy tắc hợp nhất nghiệp vụ.

### 11.3. Hàm trên cột và khả năng dùng index

Với một index B-tree thông thường trên `email`, câu:

~~~sql
WHERE lower(btrim(email)) = 'an@example.com'
~~~

có thể không tận dụng index trên cột gốc theo cách một điều kiện `email = ...` sử dụng. PostgreSQL có thể hỗ trợ **expression index** trên `lower(btrim(email))` khi workload cần. Tuy nhiên, có index không bảo đảm bộ tối ưu hóa luôn chọn nó; quyết định còn phụ thuộc kích thước bảng, phân bố dữ liệu, statistics, collation và selectivity.

Nếu cần đo:

~~~sql
EXPLAIN
SELECT id
FROM tai_khoan_thu
WHERE lower(btrim(email)) = 'an@example.com';
~~~

`EXPLAIN` mô tả kế hoạch dự kiến. Với bảng thực tế lớn, có thể kiểm tra thêm `EXPLAIN ANALYZE` trong môi trường phù hợp; `ANALYZE` trong lệnh này **thực sự chạy truy vấn**, vì vậy không nên dùng tùy tiện cho câu lệnh có tác dụng thay đổi dữ liệu.

## 12. UPDATE dữ liệu cũ: làm sạch có kiểm soát

Khi cần sửa dữ liệu đang lưu, có thể dùng `UPDATE` kết hợp hàm chuỗi. Với bảng thực hành:

~~~sql
BEGIN;

UPDATE lien_he_mau
SET ho_ten = NULLIF(
    regexp_replace(btrim(ho_ten), '[[:space:]]+', ' ', 'g'),
    ''
)
WHERE ho_ten IS NOT NULL;

SELECT id, ho_ten
FROM lien_he_mau
ORDER BY id;

ROLLBACK;
~~~

Ví dụ mở giao dịch, cập nhật dữ liệu tạm, đọc kết quả, rồi **`ROLLBACK`** để hủy thao tác minh họa. Khi xử lý dữ liệu thật, cần xác định có nên commit không, dữ liệu gốc được sao lưu thế nào và hệ thống nào còn phụ thuộc vào định dạng cũ.

### 12.1. Đừng biến làm sạch thành phá hủy dữ liệu

Một phép thay `REPLACE(so_dien_thoai, '0', '')` có thể xóa các chữ số quan trọng. Tương tự:

- Loại mọi dấu câu trong tên người có thể biến một tên hợp lệ thành tên khác.
- Xóa dấu tiếng Việt có thể làm mất chính tả và tạo xung đột tên.
- Chuyển mọi chữ hoa/thường mà không xét locale có thể không bảo toàn ngữ nghĩa tên riêng.
- Loại dấu `+` trong email có thể làm đổi địa chỉ mà người dùng muốn dùng.
- Cắt chuỗi theo `SUBSTRING(... FOR 10)` có thể mất dữ liệu nếu đầu vào dài hơn dự kiến.

Trước một lần cập nhật hàng loạt, nên xem trước cột gốc và cột sau biến đổi:

~~~sql
SELECT
    id,
    ma_khach_hang AS ma_goc,
    upper(replace(btrim(ma_khach_hang), '-', '')) AS ma_sau_chuan_hoa
FROM lien_he_mau
ORDER BY id;
~~~

Nếu nhiều giá trị gốc ánh xạ vào **cùng một khóa** sau chuẩn hóa, phải định nghĩa cách giải quyết va chạm trước khi áp ràng buộc `UNIQUE` hoặc ghi đè khóa gốc.

## 13. Các khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Khái niệm cắt chuỗi, bỏ ký tự biên, thay chuỗi con khá phổ biến, nhưng cách viết và những tình huống góc khác nhau:

| Mục đích | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| Cắt chuỗi | `SUBSTRING(s FROM p FOR n)` hoặc `substring(s, p, n)` | `SUBSTRING(s, p, n)`, `SUBSTR(s,p,n)` | `SUBSTRING(s, p, n)` | `SUBSTR(s, p, n)` |
| Bỏ dấu cách hai đầu | `TRIM(s)`, `btrim(s)` | `TRIM(s)` | `TRIM(s)` ở phiên bản hỗ trợ | `TRIM(s)` |
| Bỏ dấu cách đầu/cuối | `ltrim(s)`, `rtrim(s)` | `LTRIM(s)`, `RTRIM(s)` | `LTRIM(s)`, `RTRIM(s)` | `LTRIM(s)`, `RTRIM(s)` |
| Thay chuỗi con | `REPLACE(s, old, new)` | `REPLACE(s, old, new)` | `REPLACE(s, old, new)` | `REPLACE(s, old, new)` |
| Đổi chữ thường/hoa | `LOWER(s)`, `UPPER(s)` | `LOWER(s)`, `UPPER(s)` | `LOWER(s)`, `UPPER(s)` | `LOWER(s)`, `UPPER(s)` |
| Chiều dài chuỗi | `char_length(s)` | `CHAR_LENGTH(s)` | `LEN(s)` (có đặc tính riêng với dấu cách cuối) | `LENGTH(s)` |
| Regex thay thế | `regexp_replace(s, pattern, repl, 'g')` | `REGEXP_REPLACE` ở MySQL 8.0+ | Không có hàm regex replace truyền thống tương đương trực tiếp trên mọi phiên bản; kiểm tra tính năng phiên bản | `REGEXP_REPLACE` |

### 13.1. SUBSTRING và SUBSTR không phải lúc nào giống nhau

Trong PostgreSQL:

~~~sql
SELECT SUBSTRING('ABCDEFG' FROM 2 FOR 3);
-- BCD
~~~

Trong MySQL:

~~~sql
SELECT SUBSTRING('ABCDEFG', 2, 3);
-- BCD
~~~

Trong SQL Server:

~~~sql
SELECT SUBSTRING('ABCDEFG', 2, 3);
-- BCD
~~~

Trong Oracle:

~~~sql
SELECT SUBSTR('ABCDEFG', 2, 3) FROM dual;
-- BCD
~~~

Những ví dụ dùng **vị trí dương bắt đầu từ 1**. Nhưng cách diễn giải vị trí âm, 0 và độ dài không hợp lệ khác nhau theo DBMS: MySQL và Oracle có khả năng tính vị trí từ cuối chuỗi với chỉ số âm trong `SUBSTRING`/`SUBSTR` tương ứng; không nên áp dụng phép cắt chỉ số âm đó như một quy tắc chung của SQL.

### 13.2. TRIM với chuỗi cần loại nhiều ký tự

PostgreSQL:

~~~sql
SELECT btrim('..--ABC--..', '.-');
-- ABC
~~~

`btrim` hiểu `'.-'` là tập ký tự có thể bỏ ở biên. Trong MySQL, mẫu:

~~~sql
SELECT TRIM(BOTH '.-' FROM '.-ABC-.');
~~~

loại **chuỗi `'.-'`** ở hai đầu khi khớp toàn bộ, không phải mọi tổ hợp bất kỳ của hai ký tự. Do đó, nếu muốn hành vi “bỏ các ký tự trong tập”, phải thiết kế theo hàm và cú pháp của DBMS đích.

### 13.3. Oracle và chuỗi rỗng

Trong PostgreSQL, `REPLACE('ABC', 'A', '')` trả về `'BC'`; `TRIM('   ')` trả về `''`, một chuỗi rỗng. Trong Oracle, **chuỗi rỗng ở nhiều kiểu dữ liệu ký tự được xử lý như `NULL`**, nên kết quả và cách diễn giải rỗng/thiếu cần được kiểm tra riêng khi chuyển ứng dụng giữa hai hệ quản trị.

### 13.4. SQL Server và chiều dài chuỗi

`LEN` trong SQL Server có đặc tính **không tính các dấu cách ở cuối** chuỗi ký tự theo hành vi thông dụng; điều này khác việc hỏi **có bao nhiêu byte** hay **bao nhiêu ký tự thực sự được lưu**. Với dữ liệu Unicode, kiểu `NVARCHAR` và collation còn ảnh hưởng đến cách hiểu chiều dài, cặp ký tự bổ trợ và vị trí trong hàm chuỗi. Không nên dùng `LEN` như một phép thay thế máy móc cho `octet_length` của PostgreSQL.

### 13.5. Encoding và collation là một phần của ngữ nghĩa

Một câu lệnh `LOWER` hoặc phép so khớp `DISTINCT` sau `REPLACE` có thể cho kết quả khác giữa hai môi trường dù văn bản câu SQL giống nhau. Lý do có thể đến từ collation, locale, Unicode normalization, phiên bản thư viện so sánh hoặc cấu hình chuỗi. Với các trường dùng để tạo khóa duy nhất, nên định nghĩa rõ cả **quy tắc chuẩn hóa** và **cách database so sánh kết quả**.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`SUBSTRING` đếm byte nên chữ tiếng Việt bị cắt giữa byte.” | Với chuỗi văn bản PostgreSQL, vị trí là ký tự; tuy nhiên một ký tự hiển thị có thể gồm nhiều code point Unicode. |
| “Vị trí đầu của SUBSTRING là 0.” | Trong ví dụ chuẩn/PostgreSQL với vị trí dương, ký tự đầu ở vị trí `1`. |
| “`TRIM` xóa mọi khoảng trắng trong chuỗi.” | Nó xử lý các ký tự ở **biên**; khoảng trắng giữa các từ vẫn tồn tại. |
| “TRIM mặc định xóa mọi whitespace Unicode.” | Mặc định và tập ký tự hỗ trợ khác nhau theo DBMS/cấu hình; cần chỉ định rõ nếu có yêu cầu đặc biệt. |
| “`REPLACE` chỉ thay một lần.” | Hàm thông thường thay **mọi lần xuất hiện** của chuỗi con được yêu cầu. |
| “`REPLACE(s,'-','')` tương đương `TRIM(BOTH '-' FROM s)`.” | REPLACE xóa cả dấu ở giữa, TRIM chỉ xóa ở hai đầu. |
| “`REPLACE` hiểu `[0-9]+` là regex.” | REPLACE xử lý **chuỗi con literal**; dùng hàm regex khi cần mẫu biểu thức. |
| “`LOWER` giải quyết mọi trường hợp tiếng Việt và ngôn ngữ khác.” | Quy tắc chữ hoa/thường, Unicode và collation cần được xác định rõ. |
| “`NULL` giống `''` ở mọi DBMS.” | PostgreSQL phân biệt; Oracle có quy tắc xử lý chuỗi rỗng đặc thù. |
| “Hai email sau chuẩn hóa bằng nhau chứng minh cùng khách hàng.” | Chỉ cho thấy hai **khóa so khớp** bằng nhau theo quy tắc đã chọn. |
| “Hàm trên cột luôn dùng index `email` có sẵn.” | Biểu thức trên cột có thể cần expression index hoặc chiến lược lưu khóa chuẩn hóa. |
| “Chuẩn hóa nào cũng nên ghi đè dữ liệu gốc.” | Cần xem mục tiêu, nguy cơ mất thông tin, khả năng khôi phục và kiểm soát va chạm. |

## 15. Bài tập thực hành có lời giải

Các câu sau dùng cú pháp PostgreSQL. Khi tự làm, hãy dự đoán kết quả và giải thích **vì sao** phép biến đổi đúng hoặc sai với mục đích nêu ra.

### Bài 1: Lấy một phần mã

~~~sql
SELECT SUBSTRING('HD-2026-0451' FROM 4 FOR 4) AS nam;
~~~

**Đáp án:** `'2026'`. Vị trí đầu là 1; các ký tự 4–7 tạo thành phần năm. Nếu mã có cấu trúc không cố định, cách cắt này không còn đáng tin cậy.

### Bài 2: TRIM hay REPLACE?

~~~sql
SELECT
    TRIM(BOTH '-' FROM '--AB-CD--') AS a,
    REPLACE('--AB-CD--', '-', '') AS b;
~~~

**Đáp án:** `a = 'AB-CD'`; `b = 'ABCD'`. TRIM giữ dấu `-` ở giữa, REPLACE xóa tất cả dấu đó.

### Bài 3: Khoảng trắng bên trong

~~~sql
SELECT TRIM('  Nguyen   Van  ') AS ket_qua;
~~~

**Đáp án:** `'Nguyen   Van'`; ba dấu cách giữa hai từ vẫn còn. Muốn rút gọn có thể dùng `regexp_replace(btrim(...), '[[:space:]]+', ' ', 'g')`, nhưng chỉ khi quy tắc nghiệp vụ cho phép chuẩn hóa whitespace nội bộ.

### Bài 4: NULL và chuỗi rỗng

~~~sql
SELECT
    TRIM(NULL::text) AS a,
    TRIM('  ') AS b,
    NULLIF(TRIM('  '), '') AS c;
~~~

**Đáp án trong PostgreSQL:** `a = NULL`, `b = ''`, `c = NULL`. Hàm `NULLIF` giúp chủ động đổi chuỗi rỗng thành dữ liệu thiếu nếu đó là chính sách mong muốn.

### Bài 5: Tìm email theo khóa chuẩn hóa

Yêu cầu tìm dòng có email bằng `an@example.com` sau khi bỏ khoảng trắng ở hai đầu và chuyển về chữ thường theo quy tắc minh họa. Viết truy vấn.

**Một lời giải:**

~~~sql
SELECT id, email
FROM lien_he_mau
WHERE lower(btrim(email)) = 'an@example.com'
ORDER BY id;
~~~

Với dữ liệu mẫu, ID `1` và `2` khớp. Đây là so khớp theo biểu thức, không thay đổi email gốc đã lưu.

### Bài 6: Phát hiện mã có thể va chạm

Các mã `'KH-001'`, `'KH001'`, `'K-H001'` có thể cùng thành một giá trị nào sau phép:

~~~sql
SELECT upper(replace(btrim(ma), '-', '')) AS ma_key
FROM (VALUES
    ('KH-001'),
    ('KH001'),
    ('K-H001')
) AS v(ma);
~~~

**Đáp án:** Cả ba thành `'KH001'`. Nếu dấu `-` có ý nghĩa nghiệp vụ thì đây là **va chạm do chuẩn hóa quá mức**, không có nghĩa ba mã gốc tương đương.

### Bài 7: Chuẩn hóa tên mà không xóa dữ liệu gốc

Yêu cầu hiển thị bản rút gọn khoảng trắng của `ho_ten`, nhưng vẫn giữ cột gốc để đối chiếu. Viết câu SELECT.

**Một lời giải:**

~~~sql
SELECT
    id,
    ho_ten AS ho_ten_goc,
    regexp_replace(btrim(ho_ten), '[[:space:]]+', ' ', 'g')
        AS ho_ten_hien_thi
FROM lien_he_mau
ORDER BY id;
~~~

Câu lệnh chỉ tạo **cột kết quả**, chưa cập nhật bản ghi. Cần thêm `NULLIF` nếu chính sách muốn coi tên rỗng sau làm sạch là `NULL`.

### Bài 8: Dùng biểu thức nào cho dữ liệu Unicode?

Hai chuỗi có chữ `é`, một chuỗi dựng sẵn và một chuỗi dùng chữ `e` cộng dấu sắc, có thể nhìn giống nhưng khác biểu diễn. Liệu `TRIM` hay `LOWER` có tự bảo đảm chúng cùng dạng Unicode không?

**Đáp án:** Không. `TRIM` xử lý ký tự biên, `LOWER` xử lý chữ hoa/thường; khi cần quy về cùng dạng Unicode có thể dùng `normalize(..., NFC)` trong PostgreSQL với encoding hỗ trợ, hoặc một thư viện Unicode tương ứng trong ứng dụng. Việc chọn dạng và thứ tự chuẩn hóa cần nhất quán.

### Bài 9: Khi nào dùng index biểu thức?

Giả sử bảng tài khoản lớn, truy vấn thường dùng:

~~~sql
WHERE lower(btrim(email)) = 'an@example.com'
~~~

**Đáp án gợi ý:** Cân nhắc một expression index trên `lower(btrim(email))` hoặc cột normalized riêng được cập nhật nhất quán. Một index thường trên `email` không bảo đảm tối ưu cho biểu thức này. Cần so sánh chi phí ghi, dung lượng index và kế hoạch thực thi trên dữ liệu thực.

### Bài 10: Kiểm soát dữ liệu trước khi UPDATE

Bạn được giao chuẩn hóa mã khách bằng cách xóa mọi dấu `-` và viết hoa. Cần kiểm tra điều gì trước khi ghi đè `ma_khach_hang`?

**Đáp án gợi ý:** Xác nhận dấu gạch nối không mang nghĩa, xem trước mã gốc và mã mới, tìm các mã **khác nhau nhưng trùng sau chuẩn hóa**, xác định cách xử lý các va chạm, bảo đảm ràng buộc `UNIQUE` và những hệ thống phụ thuộc mã cũ được cập nhật, rồi mới quyết định giao dịch ghi dữ liệu. Có thể lưu khóa chuẩn hóa riêng và giữ mã gốc nếu cần truy vết.

## 16. Cách lựa chọn hàm theo yêu cầu

| Yêu cầu | Hàm/kỹ thuật phù hợp | Điều cần chú ý |
| --- | --- | --- |
| Lấy 4 ký tự từ vị trí 3 | `SUBSTRING(s FROM 3 FOR 4)` | Vị trí bắt đầu từ 1 trong PostgreSQL; chuỗi đủ định dạng hay không |
| Bỏ dấu cách đầu/cuối | `TRIM(s)` hoặc `btrim(s)` | Không tự xóa khoảng trắng giữa chuỗi |
| Bỏ một dấu phân cách ở biên | `TRIM(BOTH '-' FROM s)` | Không xóa dấu bên trong |
| Xóa mọi dấu `-` | `REPLACE(s, '-', '')` | Có thể làm mất cấu trúc và gây trùng |
| Thay mọi lần xuất hiện của chuỗi `abc` | `REPLACE(s, 'abc', 'xyz')` | Tìm chuỗi con literal, không phải regex |
| Rút gọn nhóm whitespace nội bộ | `regexp_replace(..., '[[:space:]]+', ' ', 'g')` | Phạm vi ký tự whitespace, bảo toàn xuống dòng |
| So khớp không phân biệt hoa/thường theo chính sách | `LOWER`/`UPPER`, collation phù hợp | Locale, Unicode, dữ liệu gốc |
| Coi chuỗi rỗng sau trim là thiếu dữ liệu | `NULLIF(TRIM(s), '')` | Có đúng ý nghĩa nghiệp vụ không |
| Giữ nguyên giá trị gốc nhưng tìm kiếm theo bản chuẩn | Biểu thức trong SELECT/WHERE, expression index/cột normalized | Hiệu năng và quy tắc so khớp nhất quán |
| Hai chuỗi Unicode nhìn giống có dạng mã khác | Unicode normalization phù hợp | Không đồng nghĩa bỏ dấu hoặc phiên âm |

**Điểm cần ghi nhớ:** `SUBSTRING` chọn một phần chuỗi, `TRIM` xử lý ký tự ở biên, còn `REPLACE` thay mọi lần xuất hiện của một chuỗi con. Chúng là các công cụ thao tác văn bản, **không tự hiểu tính đúng đắn của tên người, mã hàng hay email**. Chuẩn hóa đáng tin cậy đòi hỏi biết rõ định dạng đầu vào, quy tắc nghiệp vụ, `NULL` và Unicode, đồng thời cân nhắc ràng buộc duy nhất, khả năng khôi phục và hiệu năng truy vấn.
