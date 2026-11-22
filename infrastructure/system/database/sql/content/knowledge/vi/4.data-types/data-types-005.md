# Unicode, bộ ký tự và quy tắc đối chiếu chuỗi

Trong **Database SQL**, kiểu dữ liệu ký tự không chỉ quyết định một cột chứa được bao nhiêu chữ. Cách hệ quản trị cơ sở dữ liệu (**DBMS**) mã hóa văn bản, truyền văn bản qua kết nối và so sánh hoặc sắp xếp các giá trị ảnh hưởng trực tiếp đến tính đúng đắn của truy vấn. Một ứng dụng lưu tiếng Việt có dấu, tên riêng, emoji hoặc dữ liệu đa ngôn ngữ cần phân biệt rõ **Unicode**, **bộ ký tự (character set)**, **mã hóa (encoding)** và **quy tắc đối chiếu (collation)**.

Mục tiêu thực hành của bài là có thể lưu và đọc lại văn bản Unicode, hiểu vì sao hai chuỗi nhìn giống nhau có thể so sánh khác nhau, giải thích thứ tự `ORDER BY` và chọn cấu hình so sánh phù hợp với dữ liệu.

## 1. Bốn khái niệm cần tách bạch

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Unicode** | Ký tự trừu tượng nào được biểu diễn và có mã số gì? | `A` là U+0041, `á` là U+00E1, `😀` là U+1F600 |
| **Bộ ký tự (character set)** | Tập ký tự nào được hệ thống hỗ trợ/ánh xạ? | Unicode; các bộ ký tự lịch sử giới hạn hơn như Latin-1 |
| **Mã hóa (encoding)** | Chuỗi mã số ký tự trở thành byte như thế nào? | UTF-8, UTF-16; UTF-8 của `á` là hai byte `C3 A1` |
| **Quy tắc đối chiếu (collation)** | Chuỗi được so sánh và sắp xếp theo quy tắc nào? | Phân biệt/không phân biệt hoa thường hoặc dấu; thứ tự theo ngôn ngữ |

**Unicode không đồng nghĩa UTF-8.** Unicode mô tả mã điểm (code point) và các thuộc tính ký tự; UTF-8 là một cách mã hóa những mã điểm đó thành byte. Hai hệ thống có thể cùng chứa nội dung Unicode nhưng dùng cách mã hóa lưu trữ khác nhau.

**Collation không phải encoding.** Cùng một văn bản UTF-8 có thể được sắp xếp theo quy tắc byte, theo tiếng Việt hoặc theo một bộ quy tắc không phân biệt chữ hoa/chữ thường. Thay collation không tự sửa văn bản đã bị giải mã sai và không tự chuyển bảng mã.

Một cách hình dung:

```text
Người dùng gõ "Cà phê"
        ↓
Ứng dụng / driver (chuỗi ký tự + mã hóa truyền tải)
        ↓
Kết nối DBMS (client/connection character set)
        ↓
Cột trong database (kiểu dữ liệu + cách mã hóa/lưu trữ)
        ↓
So sánh =, tìm kiếm, ORDER BY (collation / toán tử)
        ↓
Kết quả trả về cho ứng dụng (giải mã và hiển thị)
```

Khi thấy ký tự lỗi hoặc kết quả tìm kiếm bất ngờ, xác định vấn đề nằm ở **lớp biểu diễn byte** hay **lớp quy tắc so sánh** trước khi thay đổi cấu hình.

## 2. Mã điểm Unicode, byte và ký tự người dùng nhìn thấy

Unicode định danh ký tự bằng **mã điểm** ký hiệu `U+...`. Ví dụ:

| Nội dung | Mã điểm Unicode | UTF-8 ở dạng hexadecimal |
| --- | --- | --- |
| `A` | U+0041 | `41` |
| `é` | U+00E9 | `C3 A9` |
| `中` | U+4E2D | `E4 B8 AD` |
| `😀` | U+1F600 | `F0 9F 98 80` |

Trong UTF-8, một mã điểm thường chiếm từ **1 đến 4 byte**. Vì vậy độ dài văn bản theo ký tự và theo byte không nhất thiết bằng nhau.

Còn có ít nhất ba cách đếm độ dài cần phân biệt:

1. **Byte:** lượng dữ liệu theo mã hóa; quan trọng với giới hạn byte và bộ nhớ lưu trữ.
2. **Mã điểm Unicode:** số phần tử Unicode trong chuỗi đã giải mã; thường phù hợp với các hàm đếm ký tự của DBMS dùng UTF-8.
3. **Cụm ký tự hiển thị (grapheme cluster):** một ký tự mà người dùng cảm nhận. Một cụm có thể chứa nhiều mã điểm.

Ví dụ, ký tự `é` có thể được biểu diễn bằng một mã điểm `U+00E9` hoặc bằng chuỗi hai mã điểm `U+0065 U+0301` (chữ `e` và dấu sắc kết hợp). Hai dạng có thể **trông giống nhau** trên màn hình nhưng có độ dài theo mã điểm và số byte khác nhau.

Một emoji ghép người/thành viên gia đình có thể gồm nhiều mã điểm nối bằng ký tự đặc biệt, dù người dùng nhìn như một biểu tượng. Vì thế, **đếm ký tự trong SQL không mặc nhiên tương đương đếm số hình chữ hiển thị trên giao diện**.

### Ví dụ PostgreSQL: đếm ký tự và byte

Đoạn sau áp dụng khi database PostgreSQL dùng mã hóa `UTF8`:

```sql
SHOW server_encoding;

SELECT
    char_length('A') AS a_characters,
    octet_length('A') AS a_bytes,
    char_length('á') AS accented_characters,
    octet_length('á') AS accented_bytes,
    char_length('😀') AS emoji_characters,
    octet_length('😀') AS emoji_bytes;
```

Kết quả kỳ vọng với UTF-8: `A` là 1 ký tự/1 byte, `á` là 1 ký tự/2 byte, `😀` là 1 mã điểm/4 byte.

Để tạo chính xác hai cách biểu diễn `é` mà không phụ thuộc vào bàn phím hoặc việc tự chuẩn hóa của trình soạn thảo, PostgreSQL hỗ trợ Unicode escape literal:

```sql
SELECT
    char_length(U&'\00E9') AS composed_characters,
    octet_length(U&'\00E9') AS composed_bytes,
    char_length(U&'e\0301') AS decomposed_characters,
    octet_length(U&'e\0301') AS decomposed_bytes;
```

Với UTF-8, dạng ghép sẵn là **1 mã điểm, 2 byte**; dạng tách dấu là **2 mã điểm, 3 byte**. Đây là khác biệt của dữ liệu nền, kể cả khi kết quả hiển thị tương tự nhau.

## 3. UTF-8, UTF-16 và những bộ mã hóa khác

### UTF-8

UTF-8 có các tính chất hữu ích cho hệ thống SQL hiện đại:

- Mã hóa Unicode bằng số byte thay đổi theo ký tự (từ 1 đến 4).
- Các ký tự ASCII cơ bản sử dụng byte giống ASCII, giúp tương thích tốt với nhiều công cụ.
- Lưu chữ Latin thường khá gọn; ký tự có dấu, chữ Hán hoặc emoji thường cần nhiều byte hơn.
- Phù hợp với dữ liệu đa ngôn ngữ, API và nhiều ứng dụng web.

**Không suy diễn** rằng một cột khai báo `VARCHAR(100)` luôn chiếm đúng 100 byte. Ý nghĩa giới hạn và dung lượng thực tế phụ thuộc DBMS, charset và định nghĩa kiểu.

### UTF-16

UTF-16 biểu diễn Unicode theo các **đơn vị mã 16 bit (code unit)**. Một mã điểm nằm ngoài Basic Multilingual Plane, chẳng hạn nhiều emoji, cần **hai code unit** (surrogate pair), tương đương 4 byte cho nội dung đó, chưa tính overhead khác.

SQL Server thường lưu `NVARCHAR` theo UTF-16; một số database engine hoặc client khác cũng dùng UTF-16 ở một lớp trong hệ thống. Không áp dụng trực tiếp quy tắc “một ký tự = hai byte”: ký tự bổ sung có thể cần hai đơn vị 16 bit và số byte lưu trữ còn phụ thuộc kiểu dữ liệu, driver và engine.

### Mã hóa khác và nguy cơ mất dữ liệu

Các bộ mã hóa như Latin-1 hoặc mã trang (code page) cũ không biểu diễn được mọi chữ viết/emoji. Khi chèn ký tự không hỗ trợ, hệ thống có thể **báo lỗi, thay ký tự, chuyển đổi dữ liệu** hoặc xử lý theo chính sách DBMS/driver. Một khi dữ liệu đã bị thay bằng dấu hỏi hoặc ký tự thay thế, chỉ thay encoding lúc đọc lại không thể bảo đảm phục hồi bản gốc.

Cũng cần phân biệt:

- **Byte Order Mark (BOM)** là dấu nhận biết mã hóa có thể có trong **tệp văn bản**; không phải tiền tố bắt buộc của mọi giá trị SQL Unicode.
- **Charset của tệp import** (CSV/SQL) có thể khác charset của **kết nối** và charset **cột đích**. Cần cấu hình các lớp này nhất quán.

## 4. Collation: so sánh, tìm kiếm và thứ tự sắp xếp

Một **collation** quy định cách DBMS phân loại và so sánh chuỗi. Những thuộc tính hay gặp:

| Thuộc tính | Câu hỏi thực tế | Ví dụ về sự khác biệt |
| --- | --- | --- |
| **Case sensitivity** | `A` và `a` có được coi ngang nhau khi so sánh? | Case-sensitive (CS) hoặc case-insensitive (CI) |
| **Accent sensitivity** | `e` và `é` có được coi ngang nhau? | Accent-sensitive (AS) hoặc accent-insensitive (AI) |
| **Locale** | Thứ tự chữ cái theo ngôn ngữ/vùng nào? | Tiếng Việt, tiếng Đức, tiếng Thổ Nhĩ Kỳ, collation chung Unicode |
| **Binary/deterministic comparison** | Chuỗi được phân biệt chi tiết theo byte/mã điểm thế nào? | Quy tắc nhị phân thường khác quy tắc ngôn ngữ |
| **Quy tắc phụ trợ** | Có phân biệt ký tự toàn chiều rộng, kana, biến thể khác không? | Phụ thuộc DBMS và tên collation cụ thể |

Không có **một thứ tự sắp xếp “đúng” duy nhất** cho tất cả ngôn ngữ. `ORDER BY name` có thể cho thứ tự khác khi thay collation, ngay trên cùng một tập dữ liệu.

### So sánh bằng (`=`) và sắp xếp (`ORDER BY`) không luôn có cùng cơ chế

Một DBMS có thể dùng collation để quyết định cả **hai chuỗi có bằng nhau không** và **thứ tự trước/sau**. DBMS khác có thể dùng collation chủ yếu để sắp xếp, trong khi kiểm tra bằng nhau còn phụ thuộc tính xác định của collation, kiểu dữ liệu hoặc toán tử.

Chẳng hạn với PostgreSQL, một collation ICU **deterministic** vẫn phân biệt giá trị khác byte khi so sánh bằng nhau dù ICU gán cùng trọng số ở một số cấp so sánh. Nếu muốn xử lý các chuỗi khác byte như bằng nhau theo collation, cần collation **nondeterministic** phù hợp (có điều kiện về phiên bản/tính năng và hiệu năng). Không suy ra rằng cứ đặt tên collation “không phân biệt hoa thường” thì mọi DBMS đều xử lý `=` y hệt.

### Ví dụ tác động đến UNIQUE và JOIN

Giả sử bảng `users` có cột `username`. Nếu định nghĩa cột và unique constraint sử dụng quy tắc **không phân biệt hoa thường**, database có thể xem `'Minh'` và `'minh'` là trùng khóa, tùy DBMS/collation. Với collation phân biệt hoa thường, hai giá trị có thể cùng tồn tại.

Tương tự, `JOIN ... ON a.name = b.name`, `GROUP BY name`, `DISTINCT name` và `COUNT(DISTINCT name)` có thể cho nhóm/giá trị khác nhau nếu quy tắc bằng nhau của collation khác nhau. Vì vậy, **chọn collation là quyết định về ý nghĩa dữ liệu**, nhất là với mã tài khoản, tên đăng nhập và khóa duy nhất.

## 5. Chuẩn hóa Unicode: cùng hình thức, khác chuỗi mã điểm

**Unicode normalization** là quá trình đưa các biểu diễn tương đương về dạng chuẩn. Các dạng thường nhắc tới:

- **NFC:** dạng chuẩn hóa theo hướng kết hợp các chuỗi ký tự thành mã điểm ghép sẵn khi có thể.
- **NFD:** dạng chuẩn hóa theo hướng tách các ký tự có dạng phân rã chuẩn.
- **NFKC/NFKD:** thêm bước xử lý **tương đương tương thích**, có thể thay đổi những khác biệt quan trọng về hình thức/ý nghĩa trong một số ứng dụng.

Ví dụ về NFC và NFD của `é`:

```text
Hình thức hiển thị: é

NFC (thường): U+00E9
NFD:          U+0065 U+0301
```

**Normalization khác collation.** Normalization thay đổi **biểu diễn dữ liệu**; collation quyết định **cách so sánh dữ liệu**. Một collation cho phép so sánh hai dạng giống nhau không có nghĩa DBMS đã chuyển chúng thành cùng dãy byte.

Khi thiết kế ứng dụng nhập liệu đa ngôn ngữ:

1. Xác định có cần chuẩn hóa Unicode lúc nhận dữ liệu hay không, và chọn dạng phù hợp (NFC thường là lựa chọn phổ biến cho dữ liệu văn bản).
2. Chỉ áp dụng thống nhất ở những điểm đã được thiết kế: trước khi tính khóa tìm kiếm, trước khi ghi vào cột được chuẩn hóa hoặc ở tầng xử lý riêng.
3. Không tự áp dụng NFKC/NFKD lên mã định danh, token, chữ ký số hay dữ liệu mà sự khác biệt ký tự là quan trọng.
4. Ghi rõ chiến lược so sánh, bởi **cùng chuẩn hóa Unicode vẫn không tự giải quyết khác biệt hoa/thường hoặc dấu**.

Các ký tự nhìn rất giống nhau thuộc **mã điểm khác** (homoglyph) không nhất thiết tương đương Unicode. Ví dụ chữ Latin `a` và ký tự có hình thức giống `a` thuộc bảng chữ cái khác vẫn có thể là hai mã điểm khác nhau; chuẩn hóa Unicode không tự chuyển toàn bộ các trường hợp này thành một.

## 6. Kiểu dữ liệu ký tự và chiều dài cột

Đặc điểm chính của những kiểu dữ liệu văn bản:

| Kiểu phổ biến | Mục đích | Điều cần chú ý |
| --- | --- | --- |
| `CHAR(n)` | Trường có độ dài cố định hoặc quy định rõ | Có quy tắc padding/khoảng trắng cuối tùy engine; có thể ảnh hưởng `=` và độ dài |
| `VARCHAR(n)` | Văn bản có độ dài thay đổi với giới hạn | `n` có thể tính theo ký tự hoặc đơn vị khác, tùy DBMS/kiểu |
| `TEXT` / `CLOB` / `VARCHAR(MAX)` | Văn bản dài | Hỗ trợ chỉ mục, thao tác và giới hạn cụ thể khác nhau |
| `NCHAR` / `NVARCHAR` | Kiểu Unicode riêng trong một số DBMS | Điển hình SQL Server; không phải mọi hệ đều cần thêm tiền tố `N` |

Một số điểm phân biệt theo DBMS:

- **PostgreSQL:** trong database mã hóa UTF8, `VARCHAR(n)` giới hạn theo số ký tự, còn byte lưu trữ của chuỗi có thể nhiều hơn. `TEXT` hỗ trợ văn bản độ dài thay đổi mà không cần `n`.
- **MySQL:** `CHAR`, `VARCHAR` có character set/collation; charset `utf8mb4` hỗ trợ ký tự Unicode có thể cần đến 4 byte. Giới hạn hàng/cột và dung lượng index cần được tính theo byte khi thiết kế.
- **SQL Server:** `NVARCHAR(n)` dùng `n` tính theo **đơn vị byte-pair** (thường tương ứng code unit UTF-16), không bảo đảm lưu được `n` ký tự người dùng nhìn thấy nếu có surrogate pair. `VARCHAR` dùng code page hoặc UTF-8 theo collation phù hợp.
- **Oracle Database:** `VARCHAR2(n BYTE)` và `VARCHAR2(n CHAR)` phân biệt giới hạn theo byte với giới hạn theo ký tự; `NCHAR` và `NVARCHAR2` dùng national character set.
- **SQLite:** khai báo `VARCHAR(20)` không tự đảm bảo giới hạn 20 ký tự theo cơ chế kiểu dữ liệu linh hoạt thông thường của SQLite; muốn ràng buộc thì cần thiết kế kiểm tra phù hợp.

Khi yêu cầu dữ liệu là *“tối đa 100 ký tự người dùng nhìn thấy”*, đừng mặc nhiên dùng `VARCHAR(100)` rồi coi như đã giải quyết toàn bộ. Giới hạn của SQL và việc đếm grapheme trên giao diện có thể khác nhau. Cần xác định đơn vị cần kiểm soát, DBMS và giới hạn lưu trữ thực tế.

## 7. Thực hành trên PostgreSQL: kiểm tra encoding và collation

Các truy vấn ở mục này dành cho **PostgreSQL**. Chạy trên đúng kết nối/database dùng trong bài thực hành.

### 7.1. Xem thông số của phiên hiện tại

```sql
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;

SELECT current_database() AS database_name,
       pg_encoding_to_char(encoding) AS database_encoding,
       datcollate AS database_collation,
       datctype AS character_classification
FROM pg_database
WHERE datname = current_database();
```

Giải thích:

- `server_encoding` cho biết encoding database/server của kết nối hiện tại; `UTF8` cho phép lưu văn bản đa ngôn ngữ.
- `client_encoding` xác định cách PostgreSQL diễn giải/trả về văn bản từ phía client. Nếu client gửi byte sai với encoding được khai báo, có thể xuất hiện lỗi hoặc văn bản sai.
- `lc_collate` liên quan quy tắc đối chiếu mặc định của database; `lc_ctype` liên quan phân loại ký tự.
- Metadata collation của database có thể gồm cả provider/locale tùy phiên bản PostgreSQL. Hai tên locale tương tự chưa chắc mang cùng quy tắc nếu thư viện locale hoặc phiên bản ICU khác nhau.

### 7.2. Quan sát thứ tự theo byte và thứ tự mặc định

```sql
WITH sample(word) AS (
    VALUES ('A'), ('a'), ('b'), ('á'), ('z'), ('Đ'), ('đ')
)
SELECT word
FROM sample
ORDER BY word COLLATE "C";
```

`COLLATE "C"` áp dụng quy tắc sắp xếp dạng C/binary theo cách PostgreSQL hỗ trợ, hữu ích để đối chiếu với cách sắp xếp theo ngôn ngữ. Thử cùng tập dữ liệu với collation mặc định:

```sql
WITH sample(word) AS (
    VALUES ('A'), ('a'), ('b'), ('á'), ('z'), ('Đ'), ('đ')
)
SELECT word
FROM sample
ORDER BY word;
```

Kết quả thực tế phụ thuộc collation của database; không khẳng định thứ tự “tiếng Việt” nếu chưa xác định locale/provider.

### 7.3. Chỉ định collation cho một biểu thức

PostgreSQL hỗ trợ cú pháp `COLLATE` gắn với biểu thức:

```sql
SELECT 'A' COLLATE "C" < 'a' COLLATE "C" AS c_comparison;
```

Bạn cũng có thể chỉ định collation khi tạo cột hoặc chỉ mục, nhưng **collation phải tồn tại trong database**. Tránh sao chép tên locale từ hệ điều hành khác nếu chưa kiểm tra danh sách collation khả dụng.

Trên các bản PostgreSQL hỗ trợ ICU, khi có quyền tạo collation và database được xây dựng với hỗ trợ ICU, có thể tạo collation chỉ để **thử nghiệm**:

```sql
-- PostgreSQL với ICU; chạy trong database thực hành:
CREATE COLLATION lab_icu_ci (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);

SELECT 'SQL' COLLATE lab_icu_ci = 'sql' AS same_ignoring_case;
```

`und-u-ks-level2` là cấu hình ICU thường dùng cho so sánh **không phân biệt hoa/thường nhưng còn phân biệt dấu**; `deterministic = false` cho phép nhiều chuỗi khác byte được coi tương đương theo collation. Khả năng chạy, chi phí index và các toán tử mẫu như `LIKE` có thể thay đổi theo **phiên bản PostgreSQL**; đây là **ví dụ PostgreSQL có điều kiện**, không phải cú pháp chuẩn cho mọi DBMS. Nếu hệ thống không có ICU hoặc không có quyền `CREATE COLLATION`, bỏ qua phần này.

**Lưu ý bảo trì:** cập nhật phiên bản thư viện collation (ICU/libc) có thể làm thay đổi thứ tự hoặc quan hệ tương đương. Với index phụ thuộc collation, cần tuân theo hướng dẫn của DBMS về kiểm tra version và xây dựng lại index khi cần.

## 8. MySQL và MariaDB: charset và collation ở nhiều cấp

Trong MySQL, character set/collation có thể được cấu hình ở cấp **server, database, table, column và biểu thức**, đồng thời kết nối có các biến character set riêng.

### Kiểm tra môi trường đang chạy

```sql
-- MySQL / MariaDB:
SELECT VERSION() AS dbms_version;

SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT @@character_set_client AS client_charset,
       @@character_set_connection AS connection_charset,
       @@character_set_results AS results_charset,
       @@collation_connection AS connection_collation;
```

Trong MySQL hiện đại, `utf8mb4` là lựa chọn hữu ích để lưu Unicode đầy đủ, gồm cả ký tự bổ sung như nhiều emoji. Một số cấu hình/phiên bản cũ dùng `utf8` dưới nghĩa `utf8mb3` (giới hạn 3 byte), nên không nên dựa vào tên `utf8` mà bỏ qua định nghĩa thực tế. MySQL và MariaDB có **tập tên collation và phiên bản hỗ trợ khác nhau**; không lấy một tên collation của MySQL áp dụng mặc định cho MariaDB.

### Ví dụ collation cụ thể trên MySQL 8.0+

```sql
-- Cú pháp/tên collation của MySQL 8.0+:
CREATE TABLE unicode_customer_lab (
    id INT PRIMARY KEY,
    customer_name VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL
);

INSERT INTO unicode_customer_lab (id, customer_name)
VALUES
    (1, 'Café'),
    (2, 'cafe'),
    (3, 'Cà phê');

SELECT id, customer_name
FROM unicode_customer_lab
WHERE customer_name = 'CAFE'
ORDER BY id;
```

Tên `utf8mb4_0900_ai_ci` cho biết một collation dựa trên Unicode Collation Algorithm 9.0, thiên về **accent-insensitive/case-insensitive**. Truy vấn `WHERE` vì vậy có thể khớp nhiều biến thể hoa thường hoặc dấu; đây là hành vi đáng chú ý nếu dùng cột làm khóa định danh. Với bài mới cần phân biệt dấu và hoa thường, hãy chọn collation phù hợp **có thật trong phiên bản engine**, không chỉ đổi hậu tố tên theo phỏng đoán.

Có thể xem thông tin cột:

```sql
SHOW FULL COLUMNS FROM unicode_customer_lab;
```

Nếu chỉ dùng bảng để thực hành, có thể xóa sau khi kiểm tra và chắc chắn đó là bảng do bạn vừa tạo:

```sql
DROP TABLE unicode_customer_lab;
```

**Về kết nối:** khai báo `utf8mb4` trên cột không thể tự sửa đầu vào bị giải mã sai ở client. Hãy sử dụng driver hỗ trợ Unicode, đảm bảo cấu hình kết nối khớp và xác minh bằng dữ liệu có dấu/emoji.

## 9. SQL Server: NVARCHAR, Unicode literal và hậu tố collation

Trong **Microsoft SQL Server**, hai điểm thường gây nhầm:

1. `NVARCHAR` lưu Unicode theo dạng UTF-16; `VARCHAR` phụ thuộc code page của collation, hoặc có thể dùng UTF-8 với collation `_UTF8` trên những bản SQL Server hỗ trợ.
2. Khi viết **literal Unicode** trong T-SQL, tiền tố `N` rất quan trọng để tránh bị chuyển đổi qua code page của literal thường.

```sql
-- SQL Server:
SELECT N'Tiếng Việt có dấu' AS unicode_value;

SELECT
    SERVERPROPERTY('Collation') AS server_collation,
    DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS database_collation;
```

Tên collation SQL Server thường chứa hậu tố mô tả quy tắc:

- `CI`: case-insensitive; `CS`: case-sensitive.
- `AI`: accent-insensitive; `AS`: accent-sensitive.
- Một số tên có `_SC` để chỉ hỗ trợ supplementary characters theo quy tắc của họ collation đó.
- Một số collation `_UTF8` hỗ trợ mã hóa UTF-8 cho kiểu `VARCHAR` trên các phiên bản SQL Server phù hợp.

Ví dụ chỉ thay collation của một phép so sánh:

```sql
-- SQL Server; dùng Unicode literal N'...':
SELECT
    CASE
        WHEN N'café' COLLATE Latin1_General_100_CI_AI
           = N'CAFE' COLLATE Latin1_General_100_CI_AI
        THEN N'Bằng nhau theo collation'
        ELSE N'Khác nhau'
    END AS comparison_result;
```

**Không tự suy ra** mọi hậu tố `_CI_AI` sẽ có cùng hành vi đối với toàn bộ ký tự Unicode ở mọi họ/phiên bản collation. Hãy xem **tên collation đầy đủ**, database/column thực tế và phiên bản SQL Server.

Khi thay kiểu cột từ `VARCHAR` sang `NVARCHAR`, cần kiểm tra cả ứng dụng, index và dung lượng; khi thay collation cho cột đã có dữ liệu hoặc ràng buộc, phải xem tác động lên các giá trị vốn đang được coi là khác nhau.

## 10. SQLite và Oracle Database: các quy tắc riêng

### SQLite

SQLite hỗ trợ lưu văn bản bằng UTF-8 hoặc UTF-16, nhưng cơ chế cột và collation khác các DBMS dạng server. Các collation mặc định nổi bật:

- `BINARY`: so sánh kiểu nhị phân theo biểu diễn SQLite sử dụng.
- `NOCASE`: không phân biệt hoa/thường **đối với ASCII cơ bản**, không phải case folding Unicode toàn diện.
- `RTRIM`: bỏ qua một số dấu cách cuối theo quy tắc SQLite.

```sql
-- SQLite:
PRAGMA encoding;

SELECT 'A' = 'a' COLLATE NOCASE AS ascii_equal;
SELECT 'Á' = 'á' COLLATE NOCASE AS unicode_case_equal;
```

Kết quả câu thứ nhất thể hiện `NOCASE` đối với ASCII; câu thứ hai không nên kỳ vọng đúng với cách so sánh Unicode đa ngôn ngữ. Muốn collation Unicode nâng cao, ứng dụng cần mở rộng SQLite bằng ICU hoặc tự đăng ký collation phù hợp. Hãy chú ý một thư viện mở rộng không có sẵn trong mọi bản cài SQLite.

### Oracle Database

Oracle Database phân biệt **database character set** và **national character set** dùng cho nhóm kiểu `NCHAR`/`NVARCHAR2`. Bộ ký tự database phổ biến để lưu Unicode đầy đủ là `AL32UTF8`. Có thể kiểm tra:

```sql
-- Oracle Database:
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET');

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP');
```

Collation/so sánh trong Oracle chịu ảnh hưởng phiên bản, định nghĩa cột, các tham số NLS và cơ chế so sánh ngôn ngữ được chọn. Không thay đổi tham số NLS ở môi trường chia sẻ khi chưa hiểu ảnh hưởng tới query/index.

Oracle còn có sự khác biệt đáng chú ý: **chuỗi rỗng `''` thường được xử lý như `NULL`** với kiểu ký tự; khi thiết kế chuẩn hóa và unique constraint, điều này khác PostgreSQL, MySQL và SQL Server.

## 11. Khi đổi collation, những truy vấn nào có thể thay đổi?

Xét dữ liệu khách hàng:

| id | display_name |
| --- | --- |
| 1 | `An` |
| 2 | `an` |
| 3 | `Án` |
| 4 | `Ân` |

Các thao tác sau có thể thay đổi kết quả khi chuyển giữa collation phân biệt hoặc không phân biệt hoa/dấu:

```sql
-- Minh họa cú pháp phổ biến; kết quả phụ thuộc DBMS + collation
SELECT DISTINCT display_name FROM customers;

SELECT display_name, COUNT(*)
FROM customers
GROUP BY display_name;

SELECT id, display_name
FROM customers
WHERE display_name = 'an';

SELECT id, display_name
FROM customers
ORDER BY display_name;
```

Một thay đổi collation còn có thể tác động đến:

- **UNIQUE/PRIMARY KEY theo cột ký tự:** quy tắc trùng khóa có thể đổi; dữ liệu đang có có thể cản trở tạo unique index mới.
- **FOREIGN KEY và JOIN:** các cột tham gia so sánh cần tương thích theo quy tắc DBMS.
- **Index/search plan:** điều kiện có ép collation hoặc dùng hàm `LOWER(...)` có thể cần index phù hợp để tránh quét nhiều dòng.
- **Phân trang:** thứ tự không đủ rõ ràng khi nhiều giá trị cùng trọng số collation; nên bổ sung khóa phụ ổn định như `ORDER BY display_name, id`.
- **Kết quả báo cáo:** `GROUP BY`, `DISTINCT` và thống kê số lượng giá trị riêng có thể thay đổi theo quy tắc tương đương.

Collation được thiết kế cho một miền dữ liệu cụ thể. **Tên người** có thể cần so sánh ngôn ngữ linh hoạt, còn **mã đơn hàng/token/chữ ký** có thể cần quy tắc chính xác theo byte hoặc dạng chuẩn được quy định rõ. Đừng tự áp dụng collation không phân biệt dấu cho mọi cột chỉ vì thao tác tìm tên có vẻ thuận tiện hơn.

## 12. Tình huống thực tế: dữ liệu tiếng Việt bị lỗi và tìm kiếm sai

### Tình huống A: ghi `Tiếng Việt`, đọc ra chuỗi bị biến dạng

Ví dụ hiển thị bất thường như `Tiáº¿ng Viá»‡t` thường gợi ý byte UTF-8 từng được diễn giải bằng một encoding khác tại một lớp trong luồng dữ liệu. Các bước xác minh:

1. Ghi lại **giá trị đầu vào nguyên bản**, nguồn nhập (form, CSV, API) và encoding được khai báo.
2. Kiểm tra **encoding của tệp** và cấu hình import; đừng chỉ nhìn đuôi `.csv` hoặc `.sql`.
3. Kiểm tra **driver, connection encoding**, engine/database encoding và kiểu cột.
4. So sánh kết quả trả về trên hai client độc lập; nếu cả hai đều sai, cần xác định giá trị lưu trong database đã bị thay đổi hay chỉ sai lúc hiển thị.
5. Kiểm tra các giá trị thực/byte nếu có công cụ phù hợp; chỉ chạy quy trình sửa dữ liệu sau khi biết chính xác phép chuyển đổi sai trước đó.

**Không tự động đổi collation** để “sửa dấu tiếng Việt”: collation không khôi phục byte đã bị giải mã nhầm.

### Tình huống B: tìm `cafe` lại khớp `café`

Đây có thể là hệ quả **mong muốn** của collation accent-insensitive. Cần hỏi nghiệp vụ: trường này lưu **tên sản phẩm để tìm kiếm gần đúng** hay **mã định danh phải chính xác tuyệt đối**?

- Với tìm kiếm văn bản, có thể chọn collation hoặc cột tìm kiếm riêng hỗ trợ bỏ qua hoa/dấu.
- Với mã định danh, ràng buộc và chuẩn hóa cần được thiết kế chính thức; chọn kiểu so sánh chính xác tương ứng.

Không tự chuyển sang `LOWER(...)` rồi coi như giải quyết mọi trường hợp: `LOWER` không loại dấu, có quy tắc ngôn ngữ, và có thể làm thay đổi khả năng dùng index.

### Tình huống C: đổi collation làm báo lỗi UNIQUE

Giả sử bảng đang có hai tên `Minh` và `minh`. Khi chuyển cột/unique index sang collation không phân biệt hoa thường, hệ thống có thể phát hiện **khóa trùng**.

Quy trình hợp lý là **khảo sát nhóm dữ liệu có nguy cơ trùng dưới quy tắc mới**, quyết định cách xử lý theo nghiệp vụ, cập nhật dữ liệu hợp lệ rồi mới thay constraint/index trong một đợt migration có phương án hoàn tác. Không xóa ngẫu nhiên một bản ghi để quá trình đổi collation chạy qua.

## 13. Chọn cấu hình ngay từ khi thiết kế database

Một nhóm phát triển có thể ghi quyết định cho từng miền dữ liệu:

| Dữ liệu | Điều nên xác định | Gợi ý kiểm tra |
| --- | --- | --- |
| Tên người/tên sản phẩm | Lưu đủ Unicode, sắp xếp theo ngôn ngữ, có cần tìm không dấu? | `Cà phê`, `Đặng`, `Ánh`, các biểu diễn NFC/NFD |
| Email/username | Chính sách chuẩn hóa và phân biệt hoa/dấu theo quy định ứng dụng | Trùng `A`/`a`, ký tự tương đương, ràng buộc UNIQUE |
| Mã đơn hàng/mã kỹ thuật | So sánh chính xác theo định dạng dữ liệu | `ab-01` so với `AB-01`, khoảng trắng thừa |
| Văn bản mô tả | Đảm bảo lưu được chữ có dấu/emoji và dữ liệu dài | Text tiếng Việt, emoji, ký tự tổ hợp |
| Nội dung nhập CSV | Encoding tệp, delimiter, import pipeline, collation cột đích | Bản ghi trước và sau import có cùng giá trị |

Khi tạo cột mới, nên ghi vào tài liệu thiết kế: **DBMS + phiên bản**, **database encoding**, **kiểu cột**, **collation cột** (nếu chỉ định riêng), **quy tắc normalization**, **đơn vị giới hạn chiều dài**, và **chính sách so sánh/trùng khóa**.

Với ứng dụng đa ngôn ngữ, nên chọn bộ ký tự hỗ trợ toàn bộ Unicode tại những lớp cần thiết. Nhưng việc quyết định **có coi hai chuỗi là một hay không** phải dựa vào nghiệp vụ và quy tắc collation cụ thể, không được suy từ encoding.

## 14. Bài thực hành tổng hợp

**Mục tiêu:** quan sát trực tiếp ba vấn đề độc lập: số byte, biểu diễn Unicode và quy tắc so sánh.

### Phần A — UTF-8 và độ dài (PostgreSQL)

Chạy:

```sql
SHOW server_encoding;
SHOW client_encoding;

SELECT
    char_length('Cà phê') AS character_count,
    octet_length('Cà phê') AS byte_count;

SELECT
    char_length(U&'\00E9') AS nfc_like_count,
    char_length(U&'e\0301') AS nfd_like_count;
```

Ghi lại kết quả, giải thích vì sao `character_count` và `byte_count` khác nhau, rồi giải thích vì sao hai dạng của `é` có thể có số mã điểm khác nhau.

### Phần B — Thứ tự và quy tắc bằng nhau (PostgreSQL)

```sql
WITH names(name) AS (
    VALUES ('An'), ('an'), ('Án'), ('Ân')
)
SELECT name FROM names ORDER BY name COLLATE "C";

WITH names(name) AS (
    VALUES ('An'), ('an'), ('Án'), ('Ân')
)
SELECT name FROM names ORDER BY name;
```

Ghi lại DBMS, database collation và kết quả của từng truy vấn. Nếu hai thứ tự giống nhau, vẫn có ý nghĩa: đó là kết quả của cấu hình đang chạy; không tự khẳng định hai collation luôn đồng nghĩa.

### Phần C — Kiểm tra chính môi trường của bạn

Nếu bạn đang dùng **MySQL/MariaDB**, chạy truy vấn `character_set%`/`collation%` ở mục 8. Nếu dùng **SQL Server**, lấy tên server/database collation ở mục 9. Nếu dùng **SQLite**, kiểm tra `PRAGMA encoding` và `NOCASE`. Nếu dùng **Oracle**, lấy thông số NLS ở mục 10.

Điền biên bản:

```text
DBMS và phiên bản:
Database đang kết nối:
Character set / server encoding:
Client/connection encoding:
Collation mặc định:
Collation của cột đang thử (nếu có):
Quy tắc phân biệt chữ hoa/thường:
Quy tắc phân biệt dấu:
Ví dụ một chuỗi Unicode và độ dài theo byte:
Ví dụ một phép so sánh hoặc ORDER BY:
Ghi chú về normalization / giới hạn chiều dài:
```

### Câu hỏi củng cố

1. **Unicode và UTF-8 có phải là một không?** — Không: Unicode là hệ mã điểm/ký tự; UTF-8 là một cách mã hóa Unicode.
2. **Cùng một chuỗi nhìn thấy có thể có số byte khác nhau không?** — Có, do encoding và cách biểu diễn mã điểm (ví dụ dạng ghép sẵn/tách dấu).
3. **Đổi collation có sửa được văn bản đã bị lỗi encoding không?** — Không; collation thay đổi cách so sánh/sắp xếp.
4. **Vì sao thay collation có thể ảnh hưởng UNIQUE?** — Vì quy tắc xác định hai chuỗi có tương đương hay không có thể thay đổi.
5. **Dùng `LOWER(name)` có thay hoàn toàn collation không?** — Không; còn dấu, locale, normalization, index và các quy tắc so sánh khác.
6. **`NVARCHAR(10)` của SQL Server có bảo đảm chứa 10 emoji bổ sung không?** — Không; `n` tính theo byte-pair/code unit UTF-16, nhiều emoji cần hai đơn vị.

Khi thực hành SQL với văn bản, hãy ghi riêng **giá trị được lưu**, **cách mã hóa**, và **quy tắc so sánh**. Ba lớp này quyết định vì sao dữ liệu hiển thị, truy vấn lọc và thứ tự sắp xếp có thể cho các kết quả khác nhau, dù câu lệnh SQL trông rất đơn giản.
