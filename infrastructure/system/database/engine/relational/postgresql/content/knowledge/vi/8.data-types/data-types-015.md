# Mã hóa ký tự, collation và ảnh hưởng đến so sánh trong PostgreSQL

## 1. Vì sao lưu tiếng Việt đúng chưa đủ để so sánh đúng?

Giả sử một ứng dụng PostgreSQL quản lý khách hàng có các tên:

- `Anh`
- `anh`
- `Ánh`
- `Bình`
- `Bình` — có thể trông như “Bình” nhưng được biểu diễn bằng một chuỗi mã Unicode khác

Người dùng có thể kỳ vọng “Anh” và “anh” là cùng tên khi tìm kiếm không phân biệt chữ hoa; hoặc kỳ vọng “Bình” được sắp theo thứ tự tiếng Việt, không đơn giản theo thứ tự byte. Trong khi đó, một hệ thống kiểm tra trùng mã khách hàng có thể muốn **phân biệt chính xác từng ký tự**, không chấp nhận gộp các chuỗi trông gần giống nhau.

Có hai vấn đề riêng:

1. **Mã hóa ký tự (*character encoding*)**: văn bản được chuyển thành những byte nào để lưu trữ và truyền qua kết nối?
2. **Collation (*quy tắc đối chiếu/sắp xếp*)**: PostgreSQL dùng quy tắc nào để so sánh, sắp xếp và trong một số trường hợp xác định hai chuỗi có bằng nhau hay không?

Ngoài ra còn có **Unicode normalization**: những chuỗi mã Unicode khác nhau nhưng có cách hiển thị tương đương có được chuẩn hóa về một dạng thống nhất hay không?

Ba khái niệm cần được phân biệt rõ:

| Câu hỏi | Thuộc lĩnh vực | Ví dụ |
| --- | --- | --- |
| Dãy byte nào biểu diễn ký tự `ế`? | Encoding | UTF-8 biểu diễn `ế` thành nhiều byte |
| `Anh` đứng trước hay sau `Ánh`? | Collation | Phụ thuộc quy tắc sắp xếp |
| `Anh` và `anh` có được coi là bằng nhau? | Collation và quy tắc so sánh | Phụ thuộc kiểu collation/thiết kế tìm kiếm |
| `é` dạng một code point có tương đương `e` + dấu sắc không? | Unicode normalization và collation | Hai dãy mã có thể hiển thị giống nhau |
| Bao nhiêu “ký tự” được tính cho giới hạn `varchar(20)`? | Biểu diễn ký tự của PostgreSQL | Thường tính số ký tự, không phải byte |

**Ý chính:** có database UTF-8 là nền tảng tốt để lưu tiếng Việt, nhưng **không tự đồng nghĩa** với tìm kiếm không phân biệt hoa/thường, không phân biệt dấu hay thứ tự sắp xếp tự nhiên theo ngôn ngữ.

## 2. Encoding là gì?

Máy tính lưu dữ liệu dưới dạng byte. Muốn lưu chuỗi văn bản, cần quy tắc ánh xạ từ **ký tự** sang byte và ngược lại. Quy tắc đó là *character encoding*.

Trong hệ sinh thái Unicode, **UTF-8** rất phổ biến: các ký tự ASCII cơ bản thường dùng một byte; nhiều ký tự tiếng Việt dùng nhiều byte. Các ký tự có thể được ghép từ nhiều Unicode code point, và UTF-8 mã hóa từng code point thành byte tương ứng.

Ví dụ:

```sql
SELECT
    char_length('Tiếng Việt') AS characters,
    octet_length('Tiếng Việt') AS bytes,
    encode(convert_to('Tiếng Việt', 'UTF8'), 'hex') AS utf8_hex;
```

Với chuỗi đã viết theo dạng Unicode tổ hợp sẵn thông dụng (*precomposed*), `char_length('Tiếng Việt')` có thể là **10 ký tự**, còn số byte UTF-8 sẽ lớn hơn vì các chữ có dấu chiếm nhiều byte.

Các hàm:

- `char_length(text)` hoặc `length(text)`: số ký tự trong chuỗi theo cách PostgreSQL xử lý encoding.
- `octet_length(text)`: số **byte** biểu diễn chuỗi.
- `convert_to(text, 'UTF8')`: chuyển chuỗi thành `bytea` theo encoding được yêu cầu.
- `encode(bytea, 'hex')`: hiển thị dữ liệu bytea dưới dạng chuỗi hex.

Không nhầm `char_length` với số byte, và cũng không giả định số ký tự PostgreSQL đếm luôn bằng số ký tự người dùng cảm nhận trên màn hình. Một *grapheme cluster* có thể chứa nhiều code point, ví dụ chữ cái + dấu kết hợp hoặc emoji có nhiều thành phần.

### 2.1. UTF-8 chứa tiếng Việt như thế nào?

UTF-8 là encoding biến độ dài. Một ví dụ về mã ký tự:

```text
'A'     -> U+0041 -> 1 byte UTF-8
'é'     -> U+00E9 -> 2 byte UTF-8
'ế'     -> U+1EBF -> 3 byte UTF-8
```

PostgreSQL không cần “cột NVARCHAR riêng” chỉ để lưu tiếng Việt nếu database dùng UTF-8. Các kiểu `text`, `varchar(n)` và `char(n)` đều lưu dữ liệu theo encoding của database.

Khi thiết kế ứng dụng mới có nhiều ngôn ngữ, **UTF8** thường là lựa chọn phù hợp, nhưng vẫn phải bảo đảm cả client, driver, file import và hệ thống xuất dữ liệu đều dùng đúng encoding.

### 2.2. Encoding khác font hiển thị

Một chuỗi có thể được lưu đúng UTF-8 nhưng terminal thiếu font tiếng Việt hoặc thiết lập locale của ứng dụng khiến nó **hiển thị sai**. Ngược lại, nếu byte bị giải mã theo encoding sai trước khi ghi vào database, chuỗi bị biến đổi (*mojibake*) và có thể được lưu bền vững dưới dạng **nội dung đã sai**.

Ví dụ một ứng dụng đọc file UTF-8 như Windows-1252 rồi gửi chuỗi bị giải mã sai vào PostgreSQL: ngay cả khi database UTF-8, server cũng chỉ lưu nội dung sai mà ứng dụng đưa tới.

**Không nên sửa lỗi hiển thị bằng cách thay collation tùy tiện**; trước hết kiểm tra đường đi của byte và encoding ở từng tầng.

## 3. Server encoding, client encoding và database encoding

PostgreSQL phân biệt:

- **Database/server encoding**: cách chuỗi văn bản được biểu diễn trong một database.
- **Client encoding**: encoding mà một kết nối dùng để trao đổi văn bản với server.

Kiểm tra bằng SQL:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

Ví dụ kết quả:

```text
 server_encoding
-----------------
 UTF8

 client_encoding
-----------------
 UTF8
```

Nếu server và client dùng encoding khác nhau được PostgreSQL hỗ trợ chuyển đổi, PostgreSQL/libpq có thể chuyển mã trên đường truyền. Không phải mọi cặp encoding đều có hỗ trợ chuyển đổi; ký tự không nằm trong bảng mã đích cũng có thể gây lỗi.

### 3.1. Cấu hình client encoding trong psql

Trong một phiên `psql`:

```text
\encoding
\encoding UTF8
```

Hoặc SQL:

```sql
SET client_encoding TO 'UTF8';

SHOW client_encoding;
```

Có thể dùng biến môi trường `PGCLIENTENCODING` trong một số môi trường libpq để chỉ định encoding phía client.

**Chú ý:** đặt `client_encoding = UTF8` không tự sửa file đã được lưu với byte encoding khác. Nếu file thực tế là Latin-1/Windows-1258 nhưng client tuyên bố UTF-8, dữ liệu có thể bị từ chối hoặc chuyển sai. Phải biết **encoding thật của nguồn** trước khi đọc.

### 3.2. Encoding được quyết định ở cấp database

Trong PostgreSQL, một database được tạo với encoding cụ thể, có liên hệ với locale và template được chọn. Với PostgreSQL thông thường, **không thể đổi encoding của một database hiện có bằng một câu `ALTER DATABASE ... SET ENCODING` đơn giản**.

Trước khi chọn encoding cho database mới cần xét:

- Các ngôn ngữ cần lưu.
- Locale/collation của database.
- Template dùng tạo database.
- Những quy tắc tương thích giữa encoding và locale.
- Khả năng ứng dụng/driver xử lý Unicode.

Ví dụ cách kiểm tra thông tin database hiện tại:

```sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding_name,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
```

`datcollate` và `datctype` biểu thị những thông tin locale liên quan database theo catalog/phiên bản. Trên các phiên bản PostgreSQL hiện đại, cơ chế provider và ICU có thể bổ sung những thuộc tính locale khác; vì vậy không nên coi hai cột này là toàn bộ thông tin collation của mọi database.

### 3.3. Một ghi chú về `SQL_ASCII`

`SQL_ASCII` không phải một lựa chọn UTF-8 “nhẹ hơn”. Trong database có encoding `SQL_ASCII`, PostgreSQL có thể xem nhiều byte giá trị cao như dữ liệu không được diễn giải/kiểm tra theo một mã ký tự cụ thể.

Hệ quả là dữ liệu có thể chứa các dãy byte không thể được hiểu nhất quán khi hệ thống cần Unicode, làm conversion, sort và tìm kiếm khó kiểm soát.

Với ứng dụng đa ngôn ngữ mới, nên ưu tiên **UTF8**, trừ khi có lý do tương thích rất cụ thể và đã hiểu rõ giới hạn của phương án khác.

## 4. `text`, `varchar(n)` và `char(n)` có liên quan gì đến encoding?

Ba kiểu dữ liệu chuỗi thông dụng:

| Kiểu | Đặc điểm chính | Gợi ý sử dụng |
| --- | --- | --- |
| `text` | Chuỗi có độ dài biến đổi, không khai báo giới hạn ký tự ở kiểu | Văn bản, tên, mô tả |
| `varchar(n)` | Chuỗi tối đa `n` ký tự theo quy tắc PostgreSQL | Trường có giới hạn nghiệp vụ rõ |
| `char(n)` / `character(n)` | Chuỗi độ dài cố định về mặt khai báo và có đặc điểm padding khoảng trắng | Chỉ dùng khi có yêu cầu tương thích/định dạng cụ thể |

Ví dụ:

```sql
CREATE TABLE text_type_demo (
    title text NOT NULL,
    short_code varchar(12) NOT NULL,
    fixed_code char(4) NOT NULL
);
```

### 4.1. `varchar(n)` không có nghĩa tối đa n byte

```sql
SELECT
    char_length('Tiếng Việt') AS char_count,
    octet_length('Tiếng Việt') AS byte_count;
```

Nếu khai báo `varchar(10)`, điều kiện là số **ký tự**, không phải 10 byte UTF-8. Một chuỗi mười ký tự tiếng Việt có dấu có thể dùng nhiều hơn 10 byte.

Đây là lỗi thiết kế thường gặp khi chuyển từ các hệ thống chỉ xử lý ASCII sang dữ liệu Unicode. Nếu một giao thức bên ngoài giới hạn **byte**, phải có kiểm tra byte riêng phù hợp thay vì chỉ dùng `varchar(n)`.

### 4.2. Độ dài biểu diễn Unicode có thể khác dù nhìn giống nhau

Hai chuỗi:

```sql
SELECT
    char_length(U&'\00E9') AS composed_characters,
    char_length(U&'e\0301') AS decomposed_characters,
    octet_length(U&'\00E9') AS composed_bytes,
    octet_length(U&'e\0301') AS decomposed_bytes;
```

- `U&'\00E9'` là ký tự `é` dạng code point dựng sẵn.
- `U&'e\0301'` là `e` cộng một combining acute accent.

Hai chuỗi có thể **hiển thị rất giống nhau**, nhưng có số ký tự/code point và số byte khác nhau.

Vì vậy, ràng buộc `varchar(n)` không nhất thiết đồng nghĩa với “n chữ hiển thị theo mắt người” trong mọi trường hợp Unicode phức tạp.

### 4.3. `char(n)` và khoảng trắng cuối

`char(n)` có hành vi tự thêm khoảng trắng khi cần để đạt độ dài khai báo; khoảng trắng đệm ở cuối có những quy tắc so sánh riêng. Do đó, không nên chọn `char(n)` chỉ vì một trường “thường có n ký tự”.

Với tên riêng, địa chỉ, mô tả và dữ liệu Unicode thông thường, `text` hoặc `varchar(n)` thường đơn giản hơn. Chọn loại cột **độc lập** với lựa chọn collation: có thể dùng `text COLLATE ...` hoặc `varchar(n) COLLATE ...` theo yêu cầu.

## 5. Collation là gì?

**Collation** là bộ quy tắc dùng để sắp xếp và so sánh các chuỗi ký tự. Nó trả lời những câu hỏi như:

- Ký tự có dấu đứng gần ký tự gốc hay ở một vị trí khác?
- Chữ viết hoa và viết thường có ảnh hưởng đến thứ tự không?
- Các biến thể có dấu có được coi là khác nhau ở cấp so sánh đang dùng không?
- Những chuỗi ký tự có được so sánh theo trật tự ngôn ngữ thay vì theo byte không?

Ví dụ về các kỳ vọng khác nhau:

```text
Cách sắp xếp theo byte:
  các code point/byte được so sánh theo quy tắc C

Cách sắp xếp ngôn ngữ:
  những chữ cái và dấu được phân cấp theo quy tắc locale

Cách tìm không phân biệt chữ hoa:
  có thể muốn "Anh" và "anh" tương đương

Cách kiểm tra mã định danh:
  có thể cần "Anh" khác "anh" và khác "Ánh"
```

**Collation không phải encoding.** Hai cột đều lưu UTF-8 nhưng dùng collation khác nhau có thể có kết quả `ORDER BY` khác nhau.

### 5.1. `COLLATE` trong SQL

PostgreSQL có mệnh đề `COLLATE` để yêu cầu dùng một collation ở vị trí thích hợp.

```sql
SELECT word
FROM (
    VALUES
        ('Anh'),
        ('anh'),
        ('Ánh'),
        ('Bình')
) AS t(word)
ORDER BY word COLLATE "C";
```

`"C"` là một collation thông dụng của PostgreSQL với thứ tự mang tính byte/code point trong encoding phù hợp; nó hữu ích khi cần thứ tự xác định theo máy, **không phải** sắp xếp ngôn ngữ tiếng Việt.

Nếu bỏ `COLLATE "C"`, PostgreSQL dùng collation được suy ra từ biểu thức hoặc collation mặc định phù hợp, và thứ tự có thể khác.

### 5.2. Collation có thể xuất hiện ở nhiều cấp

Một hệ thống có thể dùng:

1. **Default collation của database.**
2. **Collation khai báo cho một cột.**
3. **`COLLATE` tường minh trong một biểu thức/truy vấn.**
4. **Collation được định nghĩa riêng bằng `CREATE COLLATION`.**

Ví dụ cột có collation chỉ định:

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE TABLE encoding_lab.codes (
    code_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_code text COLLATE "C" NOT NULL
);
```

Trong bảng này, `raw_code` có collation `"C"`. Một truy vấn có thể chỉ định collation khác trong `ORDER BY` nếu đã được tạo và tương thích.

Không phải mọi biểu thức mang dữ liệu text đều có thể kết hợp tùy ý với mọi collation. Khi dùng nhiều collation tường minh xung đột trong một biểu thức cần so sánh, PostgreSQL có thể báo lỗi collation conflict thay vì tự đoán quy tắc người dùng muốn.

## 6. Kiểm tra cấu hình locale và collation hiện có

Thông tin chung của phiên/database:

```sql
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

Các giá trị `lc_collate` và `lc_ctype` liên quan đến quy tắc locale của database; trên những phiên bản dùng ICU, cấu hình provider/locale tương ứng cần được kiểm tra bổ sung.

Có thể xem collation đã được cài trong database:

```sql
SELECT
    n.nspname AS schema_name,
    c.collname AS collation_name,
    c.collprovider,
    c.collisdeterministic,
    c.collversion
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE n.nspname IN ('pg_catalog', 'public', 'encoding_lab')
ORDER BY n.nspname, c.collname
LIMIT 80;
```

Ở PostgreSQL hiện đại:

- `collprovider` phân biệt nguồn quy tắc collation, chẳng hạn libc hoặc ICU.
- `collisdeterministic` cho biết collation có deterministic hay không.
- `collversion` lưu thông tin phiên bản quy tắc collation khi provider cung cấp.

Tên cột và thông tin chi tiết trong system catalog có thể thay đổi theo phiên bản; ví dụ `collisdeterministic` có trên các phiên bản hỗ trợ nondeterministic collations. Khi làm việc với server cũ, cần đối chiếu tài liệu phiên bản đang chạy.

Xem phiên bản:

```sql
SHOW server_version;
```

### 6.1. Vì sao máy khác có thể sắp xếp khác?

Nếu hai database dùng locale khác nhau, hoặc cùng tên locale nhưng thư viện libc/ICU khác phiên bản, chúng có thể:

- Sắp xếp tên riêng khác nhau.
- Chọn vị trí chữ có dấu khác nhau.
- Cho kết quả khác đối với những so sánh chịu tác động của collation.
- Có nguy cơ bất nhất giữa thứ tự index cũ và quy tắc collation mới sau nâng cấp thư viện.

Vì thế, **không nên coi tên locale là toàn bộ hợp đồng sắp xếp** nếu cần kết quả giống nhau qua nhiều server/nền tảng.

## 7. `libc`, `ICU` và collation `"C"`

PostgreSQL có các nguồn (*provider*) quy tắc collation. Hai nhóm thường gặp:

| Provider | Nguồn quy tắc | Điều cần biết |
| --- | --- | --- |
| **libc** | C library/locale của hệ điều hành | Phụ thuộc locale được cài và phiên bản thư viện của OS |
| **ICU** | International Components for Unicode | Hỗ trợ đa dạng quy tắc Unicode/locale; cần PostgreSQL build hỗ trợ ICU |
| **C / POSIX** | Quy tắc đơn giản định hướng thứ tự byte | Nhanh, dễ dự đoán cho mã kỹ thuật, không thay thế thứ tự ngôn ngữ |

### 7.1. Khi nào dùng `"C"`?

Ví dụ mã kỹ thuật:

```sql
SELECT code
FROM (
    VALUES ('A-2'), ('A-10'), ('B-1'), ('a-1')
) AS t(code)
ORDER BY code COLLATE "C";
```

Sắp xếp theo `"C"` không tự hiểu “A-2 nhỏ hơn A-10 theo giá trị số”. Nó cũng không tự thực hiện phân biệt/ngang hàng hoa-thường theo ngôn ngữ. Với mã máy cần thứ tự byte ổn định, điều đó có thể là ưu điểm.

Để sắp xếp tự nhiên như “A-2, A-10” theo phần số, có thể cần cấu hình collation ICU có tùy chọn numeric sorting hoặc phân tách mã thành các trường có kiểu dữ liệu rõ ràng. Không nên kỳ vọng `ORDER BY code` mặc định hiểu cấu trúc mã.

### 7.2. ICU hỗ trợ so sánh theo ngôn ngữ

ICU cho phép chọn quy tắc theo locale và các tùy chọn như mức độ mạnh (*collation strength*).

Khái quát:

- **Primary strength** thường tập trung vào khác biệt ký tự cơ bản, có thể bỏ qua nhiều khác biệt dấu và hoa/thường tùy locale.
- **Secondary strength** thường xét thêm khác biệt dấu nhưng bỏ qua khác biệt hoa/thường theo quy tắc tương ứng.
- **Tertiary strength** thường xét thêm khác biệt hoa/thường.

Các quy tắc chính xác còn phụ thuộc locale/ICU; không phải một định nghĩa “xóa tất cả dấu tiếng Việt” dùng được cho mọi ngôn ngữ.

Nếu cần sắp theo ngữ nghĩa tiếng Việt, hãy chọn collation tương ứng và **thử với bộ dữ liệu tiếng Việt đại diện**, thay vì coi `"C"` là sắp xếp tên tự nhiên.

## 8. Deterministic và nondeterministic collation

Đây là khác biệt quan trọng ở PostgreSQL hiện đại.

### 8.1. Deterministic collation

Với collation **deterministic**, khi provider đánh giá hai chuỗi là tương đương ở cấp sắp xếp, PostgreSQL vẫn có thể dùng thứ tự/phân biệt theo byte làm tiêu chí cuối để quyết định sự bằng nhau theo ngữ nghĩa deterministic.

Hệ quả thực tế: hai chuỗi hiển thị giống nhau nhưng có byte Unicode khác nhau vẫn có thể được coi là **khác**.

Ví dụ với `"C"`:

```sql
SELECT
    ('Anh' COLLATE "C" = 'anh' COLLATE "C")
        AS case_sensitive,
    (U&'\00E9' COLLATE "C" = U&'e\0301' COLLATE "C")
        AS representation_sensitive;
```

Cả hai biểu thức trả `false`: chữ hoa khác chữ thường, và code point `é` khác chuỗi `e + combining acute` ở cấp byte.

### 8.2. Nondeterministic collation

Với PostgreSQL hỗ trợ ICU nondeterministic collation (ví dụ PostgreSQL 12+ và build có ICU), bạn có thể định nghĩa collation cho phép coi nhiều chuỗi khác byte là tương đương theo quy tắc ICU được chọn.

Ví dụ tạo trong schema thử nghiệm:

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE COLLATION encoding_lab.case_insensitive (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Ý nghĩa:

- `provider = icu`: quy tắc của ICU.
- `locale = 'und-u-ks-level2'`: locale trung tính với thiết lập strength level 2 trong ICU, hướng đến so sánh ít nhạy với khác biệt hoa/thường nhưng vẫn xét nhiều khác biệt dấu.
- `deterministic = false`: cho phép các chuỗi khác nhau về byte nhưng tương đương theo collation được coi là bằng nhau.

Ví dụ:

```sql
SELECT
    ('Anh' COLLATE encoding_lab.case_insensitive
      = 'anh' COLLATE encoding_lab.case_insensitive)
        AS same_ignoring_case,
    ('Anh' COLLATE encoding_lab.case_insensitive
      = 'Ánh' COLLATE encoding_lab.case_insensitive)
        AS accented_variant;
```

Theo cấu hình ICU được mô tả, `same_ignoring_case` dự kiến là `true`, trong khi `accented_variant` thường là `false` vì khác dấu vẫn được xét ở secondary strength.

**Không mặc định kết quả của một ICU collation là tuyệt đối giống nhau ở mọi phiên bản ICU hoặc mọi locale.** Đây là cấu hình minh họa; phải kiểm tra dữ liệu thực và version của PostgreSQL/ICU.

### 8.3. Collation bỏ qua cả case và nhiều khác biệt dấu

Một ví dụ khác, **chỉ khi nghiệp vụ thật sự muốn gộp**:

```sql
CREATE COLLATION encoding_lab.loose_comparison (
    provider = icu,
    locale = 'und-u-ks-level1',
    deterministic = false
);
```

Primary strength thường bỏ qua cả case và nhiều dấu. Với nhiều cặp chữ Latin, `'resume'` và `'résumé'` có thể được coi là tương đương ở cấp so sánh này. Nhưng việc gộp dấu phải được quyết định theo nghiệp vụ: tiếng Việt phân biệt từ bằng dấu, nên một “tìm kiếm tiện dụng” không đồng nghĩa với “quy tắc nhận dạng định danh”.

**Đừng dùng collation quá lỏng cho khóa chính, username hoặc thông tin pháp lý mà chưa xác định rõ thế nào là trùng.**

### 8.4. Chi phí và hạn chế

Nondeterministic collation có thể có thêm chi phí ở một số phép so sánh/index và giới hạn nhất định tùy phiên bản PostgreSQL. Các thao tác pattern matching như `LIKE`, `ILIKE` và regular expression không có cùng mức hỗ trợ với nondeterministic collation ở mọi phiên bản; ví dụ các bản PostgreSQL cũ có thể từ chối một số thao tác này.

Đừng thêm `deterministic = false` vào mọi cột text chỉ vì muốn tiện tìm kiếm. Trước hết xác định thao tác cần hỗ trợ, kiểu index và phiên bản PostgreSQL đang chạy.

## 9. Ảnh hưởng của collation đến `ORDER BY`

### 9.1. Sắp xếp tên người dùng

Dữ liệu mẫu:

```sql
CREATE TABLE encoding_lab.people (
    person_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL
);

INSERT INTO encoding_lab.people (full_name)
VALUES
    ('Anh'),
    ('anh'),
    ('Ánh'),
    ('Bình'),
    ('Nguyễn'),
    ('Trần'),
    ('Lan');
```

Sắp xếp mặc định:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name, person_id;
```

Sắp xếp theo `"C"`:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE "C", person_id;
```

Sắp xếp theo một ICU collation đã tạo:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY
    full_name COLLATE encoding_lab.case_insensitive,
    person_id;
```

Thứ tự có thể khác giữa ba truy vấn vì quy tắc so sánh khác nhau.

### 9.2. Tại sao thêm `person_id` vào `ORDER BY`?

Với collation coi `'Anh'` và `'anh'` bằng nhau, chúng có thể **đồng hạng theo khóa sắp xếp**. Nếu không có tiêu chí phụ, thứ tự giữa những hàng đồng hạng không được bảo đảm.

```sql
ORDER BY
    full_name COLLATE encoding_lab.case_insensitive,
    person_id
```

sử dụng `person_id` như tiêu chí phá hòa, tạo thứ tự ổn định cho hiển thị và phân trang.

**Phân trang với `LIMIT/OFFSET` hoặc keyset pagination cần quy tắc sắp xếp xác định**, không chỉ dựa vào một cột text mà collation có thể cho nhiều giá trị ngang nhau.

### 9.3. Collation không tự sửa dữ liệu tiếng Việt bị sai encoding

Nếu bảng chứa văn bản đã bị mojibake, `ORDER BY ... COLLATE ...` chỉ sắp xếp những ký tự sai đang được lưu, không khôi phục được tên gốc. Trước tiên phải xác định nguồn lỗi encoding và sửa dữ liệu theo quy trình có bản sao an toàn.

## 10. Ảnh hưởng đến `=`, `<>`, `<` và `>`

Một số biểu thức so sánh chuỗi chịu tác động của collation.

### 10.1. So sánh deterministic theo `"C"`

```sql
SELECT
    ('Anh' COLLATE "C" = 'anh' COLLATE "C") AS equal_case,
    ('abc' COLLATE "C" < 'abd' COLLATE "C") AS less_than,
    ('B' COLLATE "C" < 'a' COLLATE "C") AS lexical_order;
```

Theo collation `"C"`, giá trị cụ thể phụ thuộc thứ tự mã byte; ở UTF-8, chữ ASCII in hoa và thường có mã khác nhau.

### 10.2. So sánh bằng nondeterministic collation

```sql
SELECT
    ('Anh' COLLATE encoding_lab.case_insensitive =
     'anh' COLLATE encoding_lab.case_insensitive)
        AS equal_under_ci;
```

Theo ICU collation ví dụ, kết quả được kỳ vọng là `true`. Điều đó có thể ảnh hưởng trực tiếp đến:

- `WHERE full_name = ...`
- `GROUP BY full_name`
- `DISTINCT full_name`
- `ORDER BY full_name`
- Ràng buộc `UNIQUE` trên cột dùng collation đó.

**Đừng nhầm “so sánh bằng theo quy tắc collation” với “byte giống nhau”.** Với nondeterministic ICU, các chuỗi khác byte vẫn có thể thuộc cùng lớp tương đương.

### 10.3. So sánh hai cột có collation khác nhau

Nếu hai cột có collation khai báo khác nhau, một biểu thức so sánh có thể có xung đột lựa chọn collation, nhất là khi hai bên đều yêu cầu quy tắc tường minh khác nhau.

Giải pháp không phải ép ngẫu nhiên: cần **xác định quy tắc so sánh nghiệp vụ** và dùng một collation có chủ đích:

```sql
-- Minh họa sự lựa chọn tường minh cùng một quy tắc:
SELECT
    ('Anh' COLLATE "C") = ('anh' COLLATE "C") AS exact_result;
```

Trong join giữa mã kỹ thuật và tên người dùng, đừng chọn cùng một collation cho cả hai nếu bản chất dữ liệu khác nhau.

## 11. Collation và ràng buộc `UNIQUE`

Đây là một trong những ảnh hưởng quan trọng nhất của nondeterministic collation.

### 11.1. UNIQUE với collation phân biệt case

```sql
CREATE TABLE encoding_lab.exact_codes (
    code text COLLATE "C" PRIMARY KEY
);

INSERT INTO encoding_lab.exact_codes (code)
VALUES ('ABC'), ('abc');
```

Với `"C"`, hai giá trị khác byte và được coi là khác nhau; có thể cùng tồn tại vì khóa chính không coi chúng trùng.

Điều này có thể đúng khi code là **identifier máy** và chữ hoa/thường có ý nghĩa.

### 11.2. UNIQUE với collation không phân biệt case

```sql
CREATE TABLE encoding_lab.case_insensitive_names (
    name text COLLATE encoding_lab.case_insensitive
        NOT NULL UNIQUE
);

INSERT INTO encoding_lab.case_insensitive_names(name)
VALUES ('Anh');
```

Nếu thêm:

```sql
-- Dự kiến lỗi duplicate key theo case_insensitive collation:
INSERT INTO encoding_lab.case_insensitive_names(name)
VALUES ('anh');
```

PostgreSQL có thể coi hai tên tương đương theo collation và từ chối giá trị thứ hai do `UNIQUE`.

**Hệ quả:** lựa chọn collation trở thành **quy tắc toàn vẹn dữ liệu**, không đơn thuần là sở thích hiển thị.

### 11.3. Chọn collation cho username và email

Các hệ thống khác nhau có chính sách định danh khác nhau. Một số yêu cầu:

- Username không phân biệt case nhưng **có phân biệt dấu**.
- Mã khách hàng phải phân biệt từng byte.
- Tên hiển thị có thể trùng nhưng sắp xếp theo ngôn ngữ.
- Email có quy tắc so sánh và canonicalization riêng, không chỉ `lower(email)`.

Nên tách rõ:

| Dữ liệu | Nhu cầu thường gặp | Hướng thiết kế |
| --- | --- | --- |
| Mã kỹ thuật | Chính xác, không nhập nhằng byte | `text COLLATE "C"`, UNIQUE/PK phù hợp |
| Tên hiển thị | Sắp xếp theo ngôn ngữ | Collation ngôn ngữ |
| Username | Quy tắc đăng ký riêng | Khóa chuẩn hóa + ràng buộc rõ |
| Email | Quy tắc canonicalization được định nghĩa | Không dựa duy nhất vào một ICU collation |
| Tìm kiếm tiện lợi | Có thể bỏ qua hoa/thường hoặc dấu | Công cụ tìm kiếm / expression / collation tùy phiên bản |

Đừng dùng một collation “mềm” áp cho tất cả các cột của database chỉ để giảm số câu lệnh xử lý chuỗi.

## 12. Unicode normalization: cùng hình thức hiển thị, khác dãy mã

Một chuỗi Unicode có thể được biểu diễn ở nhiều dạng tương đương về mặt chuẩn Unicode. Hai dạng quen thuộc:

- **NFC (*Normalization Form C*)**: ưu tiên dạng kết hợp sẵn khi phù hợp.
- **NFD (*Normalization Form D*)**: phân rã ký tự thành các thành phần khi phù hợp.

Ví dụ ký tự `é`:

```text
Dạng dựng sẵn:
  U+00E9
  é

Dạng phân rã:
  U+0065 U+0301
  e + combining acute accent
```

Trong PostgreSQL UTF-8:

```sql
SELECT
    U&'\00E9' AS composed,
    U&'e\0301' AS decomposed,
    U&'\00E9' COLLATE "C" =
      U&'e\0301' COLLATE "C" AS same_bytes;
```

Hai chuỗi có thể trông giống nhau nhưng `same_bytes` là `false` theo cách so sánh `"C"`.

### 12.1. Dùng `normalize`

PostgreSQL hỗ trợ hàm chuẩn hóa Unicode như `normalize(...)` khi database dùng UTF8.

```sql
SELECT
    normalize(U&'\00E9', NFC) AS normalized_one,
    normalize(U&'e\0301', NFC) AS normalized_two,
    normalize(U&'\00E9', NFC) COLLATE "C"
      = normalize(U&'e\0301', NFC) COLLATE "C"
        AS equal_after_nfc;
```

Kết quả `equal_after_nfc` được kỳ vọng là `true`. Việc chuẩn hóa giúp đảm bảo dữ liệu cùng biểu diễn trước khi áp dụng so sánh chính xác.

Một truy vấn kiểm tra độ dài:

```sql
SELECT
    char_length(U&'\00E9') AS nfc_characters,
    char_length(U&'e\0301') AS nfd_characters,
    octet_length(U&'\00E9') AS nfc_bytes,
    octet_length(U&'e\0301') AS nfd_bytes;
```

Ví dụ này cho thấy normalize và encoding/collation là **những khía cạnh liên quan nhưng riêng biệt**.

### 12.2. Khi nào chuẩn hóa đầu vào?

Có thể đặt chính sách chuẩn hóa khi ghi dữ liệu:

```sql
INSERT INTO encoding_lab.people(full_name)
VALUES (normalize(U&'B\0069\0300nh', NFC));
```

Ví dụ dùng chuỗi `Bình` với dấu huyền kết hợp. Khi chuẩn hóa NFC, chuỗi có thể chuyển về biểu diễn dựng sẵn thích hợp.

Nếu một hệ thống cần giữ nguyên văn bản pháp lý hoặc chuỗi chữ ký đã được ký theo byte, **không được tự ý normalize** mà không hiểu yêu cầu lưu bản gốc. Chuẩn hóa làm thay đổi byte và có thể ảnh hưởng hash/chữ ký số.

### 12.3. Normalize không đồng nghĩa bỏ dấu hay lower-case

`normalize(..., NFC)` không nhằm “biến `Đặng` thành `dang`” hoặc “biến `Anh` thành `anh`”. Nó giải quyết tương đương biểu diễn Unicode. Muốn tìm kiếm không phân biệt hoa/thường hoặc dấu, cần **quy tắc riêng** và cân nhắc tác động nghiệp vụ.

## 13. Tìm kiếm với `LIKE` và `ILIKE`

`LIKE` và `ILIKE` được dùng để tìm mẫu văn bản, nhưng không thể coi chúng là hai cách nói khác của collation.

### 13.1. `LIKE`: tìm mẫu

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name LIKE 'Ng%';
```

`%` đại diện cho chuỗi ký tự bất kỳ (có thể rỗng), còn `_` đại diện một ký tự theo cơ chế pattern matching của PostgreSQL.

`LIKE` thông thường phân biệt chữ hoa/thường trong nhiều cấu hình thường gặp. Tuy nhiên, trên những phiên bản PostgreSQL mới, hành vi hỗ trợ nondeterministic collations có thay đổi; không khẳng định mọi phiên bản đều có cùng khả năng pattern matching.

### 13.2. `ILIKE`: không phân biệt case theo locale

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name ILIKE 'ng%';
```

`ILIKE` là phần mở rộng PostgreSQL cho pattern matching không phân biệt chữ hoa/thường theo xử lý locale phù hợp.

**Quan trọng:** `ILIKE` không có nghĩa **tự bỏ dấu**. Một mẫu `'nguyen%'` không chắc khớp `'Nguyễn'` vì ký tự `ễ` không giống `e`. Nếu ứng dụng muốn tìm không phân biệt dấu, cần thiết kế cách chuẩn hóa/tìm kiếm riêng và kiểm tra theo tiếng Việt.

### 13.3. Pattern matching với nondeterministic collation

Khả năng dùng `LIKE`, `ILIKE` và các phép regex với nondeterministic ICU collation **phụ thuộc phiên bản PostgreSQL và từng toán tử**. Một số phiên bản cũ từ chối pattern matching với nondeterministic collation; những phiên bản mới mở rộng hỗ trợ một phần.

Để tránh lỗi production:

1. Kiểm tra `SHOW server_version`.
2. Kiểm tra chính xác toán tử `LIKE`/`ILIKE`/regex cần dùng trên phiên bản đó.
3. Test với collation đã khai báo.
4. Nếu không phù hợp, chọn chiến lược khác như cột chuẩn hóa, expression index hoặc search index.

Không thêm collation không phân biệt case vào cột rồi mặc định mọi query `ILIKE` đều dùng được hoặc dùng index hiệu quả.

## 14. `lower`, `upper` và biểu thức chuẩn hóa case

Một chiến lược phổ biến khi muốn tìm không phân biệt hoa/thường là chuẩn hóa cả hai bên bằng `lower`:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

`lower` và `upper` xử lý văn bản theo quy tắc locale/collation phù hợp, không phải phép biến đổi “ASCII-only” cho mọi dữ liệu. Kết quả có thể khác nhau với một số ngôn ngữ, ví dụ các biến thể chữ I của tiếng Thổ Nhĩ Kỳ.

### 14.1. Index trên biểu thức `lower`

Nếu ứng dụng truy vấn nhiều:

```sql
CREATE INDEX idx_people_full_name_lower
ON encoding_lab.people (lower(full_name));
```

Index có thể được PostgreSQL xem xét cho:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

Truy vấn phải có biểu thức phù hợp với index; việc tạo index không đảm bảo planner chọn index với bảng rất nhỏ.

### 14.2. UNIQUE trên biểu thức `lower`

Nếu quy tắc là không cho phép hai username chỉ khác chữ hoa/thường:

```sql
CREATE TABLE encoding_lab.accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL
);

CREATE UNIQUE INDEX ux_accounts_username_lower
ON encoding_lab.accounts (lower(username));
```

Dữ liệu mẫu:

```sql
INSERT INTO encoding_lab.accounts(username)
VALUES ('Alice');

-- Có thể bị từ chối vì lower(username) trùng:
INSERT INTO encoding_lab.accounts(username)
VALUES ('alice');
```

Điều này minh họa **quy tắc nhất quán trong database**. Nhưng `lower` không giải quyết mọi trường hợp Unicode casefold và normalization. Khi username toàn cầu có chính sách chuẩn hóa phức tạp, phải chọn thiết kế dành riêng cho định danh, không xem `lower` là lời giải vạn năng.

### 14.3. `citext` như một lựa chọn mở rộng

PostgreSQL có extension `citext` phục vụ chuỗi được so sánh **không phân biệt hoa/thường** bằng cách xử lý gần với cơ chế `lower`.

Ví dụ nếu server có extension và tài khoản được phép cài:

```sql
CREATE EXTENSION IF NOT EXISTS citext;
```

Có thể sử dụng kiểu `citext` trong thiết kế riêng. Nhưng cần cân nhắc:

- `citext` là **extension**, không mặc định có trên mọi server.
- Kết quả so sánh phụ thuộc cơ chế case conversion/locale.
- Với những quy tắc Unicode phức tạp, nondeterministic ICU collation có thể cung cấp hành vi khác và đôi khi phù hợp hơn.
- Không tự động chuyển toàn bộ `text` sang `citext` mà không kiểm tra uniqueness, index và compatibility.

## 15. Collation ảnh hưởng đến index B-tree

Index B-tree trên cột text dùng quy tắc so sánh/sắp xếp của collation và operator class phù hợp. Khi thay collation của biểu thức hoặc dùng một collation khác lúc query, một index sẵn có không nhất thiết đáp ứng `ORDER BY` hoặc điều kiện theo quy tắc mới.

### 15.1. Index theo collation mặc định của cột

```sql
CREATE INDEX idx_people_name_default
ON encoding_lab.people (full_name);
```

Index này sử dụng collation của biểu thức `full_name` theo schema và khai báo cột.

Ví dụ:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name
LIMIT 20;
```

PostgreSQL có thể dùng index để hỗ trợ sort tùy kế hoạch, kích thước bảng và độ chọn lọc.

### 15.2. Index theo `"C"` để có thứ tự cụ thể

```sql
CREATE INDEX idx_people_name_c
ON encoding_lab.people (full_name COLLATE "C");
```

Truy vấn tương ứng:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE "C", person_id
LIMIT 20;
```

Index có thể hỗ trợ việc sắp theo `"C"`, nhưng collation mặc định của cột hoặc ICU collation khác **không đồng nghĩa** với `"C"`. Ngoài ra, vì ví dụ còn sort theo `person_id`, planner có thể cần thêm xử lý để bảo đảm tiêu chí thứ hai; muốn index hỗ trợ toàn bộ thứ tự đó, cần xem xét index đa cột tương ứng.

```sql
CREATE INDEX idx_people_name_c_id
ON encoding_lab.people (full_name COLLATE "C", person_id);
```

Đây là ứng viên index phù hợp với `ORDER BY full_name COLLATE "C", person_id`, nhưng chỉ nên giữ các index thật sự cần cho workload.

### 15.3. Index với nondeterministic collation

```sql
CREATE INDEX idx_people_name_ci
ON encoding_lab.people (
    full_name COLLATE encoding_lab.case_insensitive
);
```

Dạng index này dùng collation ICU được tạo trước đó, có thể hỗ trợ so sánh/tìm theo collation tương ứng. Tuy nhiên, so sánh nondeterministic và cấu trúc index có trade-off riêng, chẳng hạn khả năng deduplication của B-tree có thể bị hạn chế. Chi phí hiệu năng cần được đo trên dữ liệu và phiên bản thật.

**Không dùng `EXPLAIN` của một bảng bảy hàng để khẳng định index nào nhanh hơn trong production.** Planner có thể chọn sequential scan vì dữ liệu quá nhỏ.

## 16. Prefix search, `text_pattern_ops` và `pg_trgm`

### 16.1. Prefix `LIKE 'abc%'` không giống range sort theo locale

Một câu:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name LIKE 'Ng%';
```

là tìm theo **tiền tố**. Trong database với collation không phải `"C"`, B-tree index thông thường trên text không nhất thiết tối ưu hóa prefix matching tốt theo mọi trường hợp.

PostgreSQL cung cấp operator class `text_pattern_ops`:

```sql
CREATE INDEX idx_people_name_pattern
ON encoding_lab.people (full_name text_pattern_ops);
```

Index này có thể hữu ích cho những truy vấn `LIKE 'Ng%'` theo tiền tố trên dữ liệu có collation phù hợp. Nó **không thay thế** index để sắp xếp ngôn ngữ thông thường vì dùng quy tắc pattern matching khác.

### 16.2. Dùng `lower(...)` cho prefix không phân biệt case

Ví dụ truy vấn:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) LIKE 'ng%';
```

Một ứng viên index:

```sql
CREATE INDEX idx_people_lower_pattern
ON encoding_lab.people (
    (lower(full_name)) text_pattern_ops
);
```

Điều kiện quan trọng là biểu thức query phải khớp dạng được index hóa, và cần kiểm tra hành vi locale/casefold đúng với nghiệp vụ.

Với các điều kiện chứa wildcard ở đầu như `'%ng%'`, một B-tree prefix index thường không hỗ trợ tìm hiệu quả như trường hợp `'ng%'`.

### 16.3. `pg_trgm` cho contains search

Nếu server có extension `pg_trgm` và tài khoản được phép:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_people_name_trgm
ON encoding_lab.people
USING gin (full_name gin_trgm_ops);
```

Index trigram có thể hữu ích cho:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name ILIKE '%ng%';
```

Nhưng các mẫu quá ngắn hoặc có ít trigram hữu ích có thể không chọn lọc được tốt; ví dụ `'%ng%'` chỉ có hai ký tự và có thể chưa đủ điều kiện hiệu quả cho index trigram. Hãy đo trên query thật và dùng `EXPLAIN`.

Ngoài ra, `pg_trgm` không đồng nghĩa tự bỏ dấu tiếng Việt. Nếu cần tìm “nguyen” để khớp “Nguyễn”, phải thiết kế bước xử lý dấu/normalization phù hợp, có thể kết hợp các chức năng khác nhưng không tự cho rằng `ILIKE` hoặc index trigram giải quyết sẵn.

## 17. Collation và `DISTINCT`, `GROUP BY`, `JOIN`

Collation không chỉ tác động `ORDER BY` mà có thể tác động ý nghĩa nhóm và điều kiện nối khi so sánh chuỗi.

### 17.1. Nhóm theo chuỗi không phân biệt case

```sql
SELECT
    full_name COLLATE encoding_lab.case_insensitive AS name_group,
    COUNT(*) AS how_many
FROM encoding_lab.people
GROUP BY full_name COLLATE encoding_lab.case_insensitive
ORDER BY name_group;
```

Nếu dữ liệu có `Anh` và `anh`, chúng có thể được tính chung một nhóm theo collation nondeterministic. Chuỗi đại diện được hiển thị cho nhóm có thể phụ thuộc những hàng có trong nhóm và kế hoạch; không nên xem cách viết hoa của giá trị đại diện là một quy tắc canonicalization ổn định.

Nếu cần một dạng hiển thị chuẩn, nên lưu riêng giá trị chuẩn hoặc định nghĩa quy tắc chọn đại diện.

### 17.2. `DISTINCT`

```sql
SELECT DISTINCT
    full_name COLLATE encoding_lab.case_insensitive AS unique_name
FROM encoding_lab.people
ORDER BY unique_name;
```

Số hàng có thể ít hơn so với `DISTINCT full_name COLLATE "C"` vì nhiều chuỗi khác byte được coi tương đương theo ICU nondeterministic collation.

### 17.3. JOIN theo tên: rủi ro kết hợp nhầm

```sql
-- Minh họa kiểu điều kiện JOIN không nên mặc định dùng
-- để liên kết hai thực thể bằng tên hiển thị:
SELECT p1.person_id, p2.person_id
FROM encoding_lab.people AS p1
JOIN encoding_lab.people AS p2
  ON p1.full_name COLLATE encoding_lab.case_insensitive
   = p2.full_name COLLATE encoding_lab.case_insensitive
WHERE p1.person_id < p2.person_id;
```

Truy vấn có thể coi `Anh` và `anh` bằng nhau. Nhưng **hai người trùng tên không nhất thiết là cùng người**. Trong mô hình quan hệ, nên JOIN thực thể bằng ID/khóa ngoại có định nghĩa rõ, không bằng tên hiển thị chỉ vì collation cho phép gộp.

Collation có thể hỗ trợ so sánh tên cho tìm kiếm, nhưng không thay thế khóa định danh đáng tin cậy.

## 18. Khi nâng cấp ICU hoặc hệ điều hành, điều gì có thể xảy ra?

Quy tắc sắp xếp không phải luôn bất biến. Sau khi nâng cấp:

- Thư viện ICU có thể thay đổi cách so sánh một số chuỗi.
- Thư viện libc của hệ điều hành có thể thay đổi quy tắc locale.
- Những index được xây dựng với quy tắc cũ có thể không còn có thứ tự nhất quán với quy tắc mới.
- Các ràng buộc `UNIQUE` phụ thuộc collation có thể cần được kiểm tra vì cách xác định sự bằng nhau có thể thay đổi.

### 18.1. Xem phiên bản collation

Một truy vấn quan sát trên các phiên bản hỗ trợ:

```sql
SELECT
    n.nspname,
    c.collname,
    c.collversion AS recorded_version,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
  ON n.oid = c.collnamespace
WHERE n.nspname = 'encoding_lab'
ORDER BY c.collname;
```

Nếu `recorded_version` và `actual_version` khác nhau, cần điều tra những index, constraint và đối tượng phụ thuộc vào collation đó.

### 18.2. `REFRESH VERSION` không tự làm mới index

PostgreSQL hỗ trợ dạng lệnh:

```sql
ALTER COLLATION encoding_lab.case_insensitive
    REFRESH VERSION;
```

Nhưng **lệnh này cập nhật metadata phiên bản đã ghi; nó không tự tái xây dựng những index được sắp theo collation đó**.

Quy trình vận hành cần:

1. Kiểm tra phiên bản database, libc/ICU và cảnh báo collation.
2. Xác định các index/constraint phụ thuộc.
3. Đánh giá nguy cơ các khóa từng được coi khác nay bị coi trùng.
4. Lập kế hoạch **REINDEX** cho các index liên quan bằng phương án phù hợp.
5. Xác nhận tính nhất quán và chức năng ứng dụng.
6. Sau khi đã bảo trì đúng, cập nhật metadata version theo khuyến nghị của PostgreSQL.

Ví dụ lệnh minh họa (chỉ chạy khi đã xác nhận đối tượng phụ thuộc và có kế hoạch vận hành):

```sql
REINDEX INDEX encoding_lab.idx_people_name_ci;

ALTER COLLATION encoding_lab.case_insensitive
    REFRESH VERSION;
```

Đối với **default collation của database**, các phiên PostgreSQL có cơ chế kiểm tra và làm mới phiên bản riêng như `ALTER DATABASE ... REFRESH COLLATION VERSION`, với quy trình tái xây index phụ thuộc tương ứng.

**Không chạy REINDEX tùy tiện trên production**: tùy phương án, thao tác có thể tốn nhiều CPU/I/O, dung lượng và khóa. Nếu quy tắc equality mới tạo xung đột unique, reindex có thể thất bại và cần xử lý dữ liệu theo chính sách nghiệp vụ.

### 18.3. Tại sao không chỉ “ignore warning”?

Một index B-tree được xây dựng theo quy tắc cũ có thể cho những kết quả sai hoặc rủi ro toàn vẹn nếu quy tắc so sánh thay đổi. Vì vậy, cảnh báo collation mismatch là tín hiệu vận hành cần xử lý, không chỉ là thông báo mang tính thẩm mỹ.

## 19. Import/export: UTF-8 và CSV

Trong công việc vận hành, lỗi encoding thường xuất hiện khi nhập tệp từ spreadsheet, hệ thống kế thừa hoặc ứng dụng ngoài.

### 19.1. Dữ liệu CSV phải có encoding được hiểu đúng

Giả sử file `people.csv` có nội dung UTF-8:

```csv
full_name
Nguyễn An
Trần Bình
Lê Chi
```

Có thể dùng `\copy` từ `psql` để nhập file nằm trên máy client:

```text
\copy encoding_lab.people (full_name) FROM 'people.csv' WITH (FORMAT csv, HEADER true)
```

Ở đây bảng `encoding_lab.people` có cột `person_id` identity, nên không cần đưa cột ID vào CSV.

`\copy` là lệnh phía **psql client**: đường dẫn file được hiểu ở máy chạy `psql`. Lệnh SQL `COPY ... FROM '/server/path'` có biến thể đọc từ **máy server**, phụ thuộc quyền và vị trí file. Không nhầm hai nơi đọc file.

### 19.2. Nếu file không phải UTF-8?

Một file legacy có thể dùng mã trang khác. Khi đó cần:

- Xác minh encoding thực tế của file.
- Chuyển file sang UTF-8 đúng cách bằng công cụ được tin cậy, **hoặc**
- Cấu hình conversion/`COPY ENCODING` được PostgreSQL hỗ trợ theo phiên bản và cặp encoding phù hợp.
- Không dùng `SET client_encoding = UTF8` như cách “chuyển mã” file nguồn thực chất không phải UTF-8.

Không nên viết một lệnh convert mẫu tùy tiện cho file chưa biết encoding; giải mã sai có thể tạo dữ liệu mojibake rồi khó phục hồi.

### 19.3. Kiểm tra dữ liệu sau import

Một vài phép kiểm tra:

```sql
SELECT
    person_id,
    full_name,
    char_length(full_name) AS characters,
    octet_length(full_name) AS bytes
FROM encoding_lab.people
ORDER BY person_id;
```

Tìm các chuỗi thường gặp khi UTF-8 bị decode sai, ví dụ những ký tự lạ, chỉ có thể là **gợi ý điều tra**. Không tự động thay thế trên toàn bảng khi chưa xác định dữ liệu gốc và tác động đến tên thật.

### 19.4. Encoding và collation của connection không phải một thứ

Khi chuyển file CSV vào database:

```text
CSV bytes
   |
   | Giải mã đúng encoding file/client
   v
Ký tự gửi PostgreSQL
   |
   | Chuyển sang encoding của database
   v
Text trong cột
   |
   | COLLATE tại lúc ORDER BY / compare
   v
Kết quả hiển thị / tìm kiếm
```

Sai ở tầng byte thì collation không thể làm đúng được dữ liệu. Ngược lại, byte đúng nhưng dùng collation không phù hợp vẫn có thể cho thứ tự tìm kiếm không như người dùng mong muốn.

## 20. Thực hành đầy đủ: so sánh theo từng quy tắc

Các ví dụ sau dành cho một database thử nghiệm dùng UTF8. Tạo ICU collations cần server build có ICU và quyền `CREATE` trong schema. Nếu môi trường không có ICU, vẫn thực hành được các phần `"C"`, Unicode normalization và encoding.

### 20.1. Khởi tạo schema và dữ liệu

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE TABLE encoding_lab.words (
    word_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word text NOT NULL
);

INSERT INTO encoding_lab.words(word)
VALUES
    ('Anh'),
    ('anh'),
    ('Ánh'),
    ('Bình'),
    (U&'Bi\0300nh'),
    ('Nguyễn'),
    ('Lan'),
    ('lan');
```

Dữ liệu `'Bình'` và `U&'Bi\0300nh'` có thể trông tương đương khi hiển thị, nhưng chuỗi thứ hai sử dụng dấu huyền kết hợp sau `i`.

Nếu đã chạy bài nhiều lần, bảng có thể tồn tại và các câu `INSERT` sẽ thêm dữ liệu mới. Dùng database/schema riêng cho lần thực hành; tránh xóa dữ liệu không thuộc bài.

### 20.2. So thứ tự mặc định và `"C"`

```sql
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word, word_id;
```

```sql
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word COLLATE "C", word_id;
```

Đối chiếu thứ tự; đừng cố ghi nhớ một thứ tự duy nhất khi default collation của database còn chưa được xác định.

### 20.3. So hai biểu diễn Unicode

```sql
SELECT
    U&'\00E9' COLLATE "C" =
        U&'e\0301' COLLATE "C" AS exact_equal,
    normalize(U&'\00E9', NFC) COLLATE "C" =
        normalize(U&'e\0301', NFC) COLLATE "C"
        AS normalized_equal;
```

Kỳ vọng:

| Cột | Kết quả |
| --- | --- |
| `exact_equal` | `false` |
| `normalized_equal` | `true` |

Điểm khác biệt do **biểu diễn Unicode**, không phải do database không hỗ trợ chữ có dấu.

### 20.4. Tạo ICU collation không phân biệt case

```sql
CREATE COLLATION encoding_lab.ci_demo (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Chạy:

```sql
SELECT
    ('Anh' COLLATE encoding_lab.ci_demo =
     'anh' COLLATE encoding_lab.ci_demo) AS case_equal,
    ('Anh' COLLATE encoding_lab.ci_demo =
     'Ánh' COLLATE encoding_lab.ci_demo) AS accent_equal;
```

Kỳ vọng theo quy tắc ví dụ: `case_equal` là true; `accent_equal` thường là false. Nếu khác, cần kiểm tra cấu hình ICU/version và mức strength thực tế.

### 20.5. So tác động tới `GROUP BY`

```sql
SELECT
    word COLLATE encoding_lab.ci_demo AS word_group,
    COUNT(*) AS total
FROM encoding_lab.words
GROUP BY word COLLATE encoding_lab.ci_demo
ORDER BY word_group;
```

Đối chiếu với:

```sql
SELECT
    word COLLATE "C" AS word_group,
    COUNT(*) AS total
FROM encoding_lab.words
GROUP BY word COLLATE "C"
ORDER BY word_group;
```

Theo `ci_demo`, các biến thể chỉ khác hoa/thường có thể được nhóm chung. Theo `"C"`, chúng vẫn phân biệt.

### 20.6. Thử `UNIQUE`

```sql
CREATE TABLE encoding_lab.unique_ci_demo (
    word text COLLATE encoding_lab.ci_demo NOT NULL UNIQUE
);

INSERT INTO encoding_lab.unique_ci_demo(word)
VALUES ('Lan');
```

Tiếp:

```sql
-- Dự kiến lỗi duplicate key nếu 'Lan' và 'lan'
-- được ICU collation ci_demo coi bằng nhau:
INSERT INTO encoding_lab.unique_ci_demo(word)
VALUES ('lan');
```

Nếu bạn chạy thử lệnh cố tình gây lỗi trong một transaction lớn, PostgreSQL có thể đặt transaction vào trạng thái aborted. Hãy thực hành lệnh gây lỗi trong transaction riêng hoặc dùng `ROLLBACK` thích hợp để quay lại trạng thái bình thường.

### 20.7. Kiểm tra kế hoạch và index

```sql
CREATE INDEX idx_words_c
ON encoding_lab.words (word COLLATE "C");

EXPLAIN
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word COLLATE "C", word_id
LIMIT 20;
```

Bảng mẫu có rất ít hàng, nên planner có thể chọn `Seq Scan + Sort`. Đây không phải dấu hiệu collation hoặc index sai: scan và sort vài hàng thường rẻ hơn dùng index.

Nếu muốn đánh giá hiệu năng thực, hãy dùng bộ dữ liệu đủ lớn, kiểm tra thống kê, truy vấn đại diện và chi phí ghi/index.

## 21. Những sai lầm thường gặp

| Nhầm lẫn | Vì sao sai? | Hướng xử lý |
| --- | --- | --- |
| “UTF-8 tự sắp xếp tên theo tiếng Việt.” | Encoding chỉ định byte, không định nghĩa sort ngôn ngữ | Chọn collation phù hợp |
| “Chọn ICU collation sẽ sửa chữ bị mojibake.” | Dữ liệu đã bị giải mã sai trước khi lưu | Kiểm tra encoding nguồn và phục hồi dữ liệu |
| “`varchar(20)` tối đa 20 byte.” | Giới hạn theo ký tự, UTF-8 biến độ dài | Dùng `octet_length` nếu có giới hạn byte |
| “`char_length` luôn bằng số chữ người dùng nhìn thấy.” | Một grapheme có thể chứa nhiều code point | Hiểu Unicode normalization và quy tắc đếm |
| “`Anh` và `anh` luôn khác nhau.” | Nondeterministic ICU có thể coi bằng nhau | Xác định collation và chính sách ID |
| “`Anh` và `Ánh` luôn bằng nhau nếu bỏ case.” | Dấu có thể vẫn có ý nghĩa ở secondary strength | Chọn strength đúng nghiệp vụ |
| “`lower` giải quyết mọi ngôn ngữ Unicode.” | Case mapping/locale có những trường hợp phức tạp | Thiết kế canonicalization riêng nếu cần |
| “`ILIKE` tự bỏ dấu tiếng Việt.” | Không bảo đảm accent-insensitive | Chọn search pipeline phù hợp |
| “B-tree index theo locale luôn tối ưu prefix LIKE.” | Pattern matching và sort locale có quy tắc khác | Cân nhắc `text_pattern_ops`/index phù hợp |
| “Index trên `full_name` dùng được cho mọi `COLLATE`.” | Index gắn với collation cụ thể | Kiểm tra index key collation và `EXPLAIN` |
| “Nondeterministic collations hỗ trợ mọi regex/LIKE trên mọi PostgreSQL.” | Hỗ trợ phụ thuộc phiên bản và toán tử | Kiểm tra tài liệu/version và test |
| “Collation chỉ thay đổi `ORDER BY`.” | Còn có thể ảnh hưởng equality, UNIQUE, GROUP BY | Xem collation như quyết định ngữ nghĩa dữ liệu |
| “`UNIQUE` theo case-insensitive vẫn cho phép `'Lan'` và `'lan'`.” | Hai giá trị có thể được coi trùng theo collation | Kiểm tra yêu cầu nhận dạng |
| “NFC là bỏ dấu.” | NFC chuẩn hóa biểu diễn, không loại bỏ dấu | Phân biệt normalization và accent folding |
| “Có thể đổi database encoding bằng ALTER TABLE.” | Encoding thuộc database và có quy tắc khởi tạo | Lập kế hoạch database/migration đúng |
| “Không cần quan tâm khi ICU/OS nâng cấp.” | Thứ tự/equality có thể đổi và ảnh hưởng index | Kiểm tra version và REINDEX |
| “REFRESH VERSION tự REINDEX.” | Lệnh chỉ làm mới metadata version | Xây lại index phụ thuộc theo quy trình |
| “`ORDER BY name` luôn ổn định giữa các bản ghi trùng collation.” | Nhiều giá trị có thể đồng hạng | Thêm khóa phụ như ID |
| “Tên hiển thị đủ an toàn để JOIN hai người.” | Trùng tên không đồng nghĩa cùng định danh | JOIN bằng khóa định danh |
| “Dùng `"C"` cho mọi cột là đơn giản nhất.” | Không đáp ứng sort ngôn ngữ của người dùng | Chọn theo miền dữ liệu |
| “ICU luôn có trên mọi máy chủ.” | PostgreSQL có thể build không có ICU | Kiểm tra môi trường và quyền |

## 22. Bài tập thực hành có gợi ý

### Bài 1. Phân biệt encoding và collation

Một database dùng `UTF8`, nhưng danh sách tên có dấu hiển thị theo thứ tự không phù hợp tiếng Việt. Cần kiểm tra điều gì?

**Gợi ý:** dữ liệu có thể được lưu UTF-8 đúng nhưng dùng `"C"` hoặc một collation khác mong đợi. Kiểm tra default/column/query collation và quy tắc locale; không đổi encoding chỉ để sửa thứ tự sort.

### Bài 2. Kiểm tra byte và ký tự

```sql
SELECT
    char_length('Tiếng Việt'),
    octet_length('Tiếng Việt');
```

**Hỏi:** vì sao hai giá trị có thể khác nhau?

**Trả lời:** trong UTF-8, nhiều ký tự có dấu dùng nhiều byte. `char_length` tính ký tự, `octet_length` tính byte.

### Bài 3. Tại sao một chuỗi không vừa `varchar(3)`?

```sql
CREATE TEMP TABLE single_character (value varchar(1));

-- Cố tình gây lỗi độ dài khi gán dữ liệu vào cột:
INSERT INTO single_character(value) VALUES (U&'e\0301');
```

**Gợi ý:** chuỗi tạo bởi `e` và combining acute có hai code point/ký tự theo cách PostgreSQL đếm, nên không vừa cột `varchar(1)` dù hiển thị như một chữ `é`. Hãy thử sau khi dùng `normalize(..., NFC)`. Lưu ý: **ép kiểu tường minh** sang `varchar(n)` trong PostgreSQL có thể cắt bớt ký tự thay vì báo lỗi; bài tập dùng `INSERT` vào cột có giới hạn để quan sát kiểm tra độ dài khi ghi dữ liệu.

### Bài 4. Hai tên khác chữ hoa cần cùng nhóm

Dữ liệu có `'Anh'` và `'anh'`, muốn GROUP BY như một nhóm. Có những lựa chọn nào?

**Gợi ý:** dùng `GROUP BY lower(name)` nếu quy tắc case mapping của ứng dụng phù hợp, hoặc dùng nondeterministic ICU collation đã được xác minh. Cần quyết định cách chọn dạng hiển thị đại diện.

### Bài 5. Cột mã kỹ thuật phải phân biệt từng byte

Nếu mã `ABC` khác `abc`, có thể dùng loại collation nào?

**Gợi ý:** `text COLLATE "C"` cùng khóa `UNIQUE`/`PRIMARY KEY` phù hợp để phân biệt giá trị theo byte. Với identifier quan trọng, còn cần validation định dạng, khoảng trắng và quy tắc nhập.

### Bài 6. Cần tìm không phân biệt chữ hoa

```sql
SELECT *
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

**Hỏi:** khi dữ liệu rất lớn và query lặp lại, index nào có thể hữu ích?

**Trả lời:** expression index trên `lower(full_name)`, sau đó kiểm tra bằng `EXPLAIN` với dữ liệu đại diện.

### Bài 7. Có thể dùng `ILIKE 'nguyen%'` để chắc chắn tìm `Nguyễn` không?

**Trả lời:** không. `ILIKE` không có nghĩa bỏ dấu. Cần thiết kế xử lý dấu/normalization hoặc tìm kiếm phù hợp ngôn ngữ nếu nghiệp vụ yêu cầu.

### Bài 8. Sau nâng cấp ICU có cảnh báo collation version mismatch

Nên làm gì?

**Gợi ý:** xác định collation/index phụ thuộc, đánh giá thay đổi quy tắc equality/sort và rủi ro unique, lập kế hoạch REINDEX phù hợp, xác minh dữ liệu rồi làm mới metadata version. Không chỉ chạy `REFRESH VERSION` để che cảnh báo.

### Bài 9. `ORDER BY` cần ổn định cho phân trang

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE encoding_lab.case_insensitive
LIMIT 20;
```

**Hỏi:** rủi ro nào tồn tại?

**Trả lời:** nhiều tên có thể đồng hạng theo collation. Thêm `person_id` làm khóa sắp xếp phụ để có thứ tự xác định:

```sql
ORDER BY full_name COLLATE encoding_lab.case_insensitive,
         person_id
```

### Bài 10. Tại sao `UNIQUE` có thể khác nhau trên cùng bộ tên?

**Trả lời:** `UNIQUE` trên `text COLLATE "C"` và trên `text COLLATE encoding_lab.case_insensitive` sử dụng quy tắc equality khác nhau. Với case-insensitive collation, `'Lan'` và `'lan'` có thể bị coi trùng.

### Bài 11. Tìm tiền tố `'Ng%'` không dùng B-tree index như mong đợi

**Gợi ý:** kiểm tra collation, biểu thức trong query, index key, độ chọn lọc và kế hoạch `EXPLAIN`. Với collation không phải C, index `text_pattern_ops` có thể là ứng viên cho prefix `LIKE` khi phù hợp.

### Bài 12. Hai Unicode literal trông giống nhưng `=` trả false

```sql
SELECT
    U&'\00E9' COLLATE "C" =
    U&'e\0301' COLLATE "C" AS equal_before,
    normalize(U&'\00E9', NFC) COLLATE "C" =
    normalize(U&'e\0301', NFC) COLLATE "C" AS equal_after;
```

**Trả lời:** `equal_before` là false do byte/code point khác; `equal_after` là true vì chuẩn hóa về cùng biểu diễn NFC.

### Bài 13. Database UTF-8 nhưng CSV nhập ra chữ lạ

**Gợi ý:** kiểm tra encoding thực của file, cách client đọc file, `client_encoding`, quá trình chuyển mã và dữ liệu đã tồn tại. Không đổi collation để sửa lỗi decode.

### Bài 14. Khi nào không dùng collation bỏ dấu cho username?

Nếu hai username phân biệt bằng dấu có thể thuộc hai người khác nhau, collation bỏ dấu có thể coi chúng trùng, gây từ chối đăng ký hoặc gộp danh tính ngoài ý muốn. Cần chính sách canonicalization được phê duyệt và nhất quán.

## 23. Checklist thiết kế cho dữ liệu văn bản

Trước khi triển khai cột `text` hoặc `varchar`, nên trả lời:

| Câu hỏi | Tại sao quan trọng? |
| --- | --- |
| Database có dùng `UTF8` không? | Đảm bảo lưu dữ liệu đa ngôn ngữ |
| Encoding thực của tệp nguồn là gì? | Tránh mojibake |
| Client/driver truyền văn bản theo encoding nào? | Tránh sai byte trước khi lưu |
| Trường này là mã kỹ thuật hay tên người? | Mỗi loại cần equality/sort khác nhau |
| Có yêu cầu sắp xếp tiếng Việt không? | Chọn locale/collation phù hợp |
| Có phân biệt chữ hoa/thường không? | Ảnh hưởng WHERE và UNIQUE |
| Có phân biệt dấu không? | Ảnh hưởng nhận dạng và tìm kiếm |
| Có cần Unicode normalization không? | Tránh nhiều biểu diễn của chuỗi hiển thị giống |
| Dùng `LIKE`, `ILIKE` hay tìm theo contains? | Chọn đúng toán tử và index |
| Collation có dùng ICU nondeterministic không? | Kiểm tra support, equality và pattern matching |
| Có index B-tree/text_pattern_ops/trigram nào liên quan? | Đảm bảo kế hoạch truy vấn phù hợp |
| Có `UNIQUE` theo tên/username không? | Collation trở thành quy tắc toàn vẹn |
| Có phân trang theo tên không? | Thêm khóa phá hòa ổn định |
| Hệ thống có nâng cấp ICU/libc không? | Cần kế hoạch collation version và REINDEX |
| Dữ liệu có được chia sẻ sang hệ khác không? | Hợp đồng encoding/canonicalization phải nhất quán |

## 24. Tổng kết

Những nguyên tắc cốt lõi về **mã hóa ký tự, collation và so sánh trong PostgreSQL**:

1. **Encoding quyết định byte**, còn **collation quyết định quy tắc so sánh/sắp xếp**. UTF-8 không tự biến mọi tìm kiếm thành không phân biệt case hay dấu.
2. **`server_encoding` và `client_encoding` có vai trò khác nhau**. Cần đảm bảo dữ liệu nguồn, kết nối và file import được giải mã đúng.
3. **`text` và `varchar(n)` lưu chuỗi theo encoding database**. `varchar(n)` giới hạn số ký tự, không đơn giản là n byte; Unicode grapheme có thể phức tạp hơn số code point.
4. **`"C"` phù hợp cho nhiều mã kỹ thuật cần thứ tự byte**, trong khi ICU/libc collations có thể phục vụ thứ tự ngôn ngữ, bao gồm tiếng Việt.
5. **Nondeterministic ICU collation có thể làm các chuỗi khác byte được coi là bằng nhau**. Điều này ảnh hưởng không chỉ `ORDER BY` mà cả `=`, `UNIQUE`, `GROUP BY` và `DISTINCT`.
6. **Unicode normalization giải quyết biểu diễn tương đương**, không tự bỏ dấu hoặc chuyển chữ hoa sang thường. Dùng `normalize(..., NFC)` khi yêu cầu dữ liệu và encoding phù hợp.
7. **`LIKE`, `ILIKE`, `lower`, `citext` và ICU collation là các công cụ khác nhau**. Mức hỗ trợ pattern matching trên nondeterministic collation phụ thuộc phiên bản PostgreSQL.
8. **Collation có thể quyết định khả năng sử dụng index**. Index theo `"C"` không mặc nhiên dùng cho mọi `ORDER BY` khác; prefix search có thể cần `text_pattern_ops`, contains search có thể dùng `pg_trgm`.
9. **Nâng cấp ICU/libc có thể thay đổi thứ tự/equality**, ảnh hưởng index và ràng buộc. `REFRESH VERSION` không tự REINDEX.
10. **Thiết kế theo ý nghĩa dữ liệu**: mã định danh cần so sánh chính xác; tên hiển thị cần sắp xếp hợp ngôn ngữ; tìm kiếm tiện dụng cần chiến lược riêng; username/email cần quy tắc nhận dạng rõ ràng.

Khi làm việc với văn bản tiếng Việt trong PostgreSQL, hãy đặt câu hỏi theo đúng thứ tự: **byte có được mã hóa/giải mã đúng không; chuỗi có cần chuẩn hóa Unicode không; phép so sánh mong muốn là chính xác, không phân biệt case hay theo ngôn ngữ; và index/ràng buộc có thực thi cùng quy tắc đó không?** Trả lời nhất quán bốn vấn đề này sẽ giúp hệ thống vừa lưu đúng ký tự, vừa tìm kiếm và kiểm tra dữ liệu theo ý định nghiệp vụ.
