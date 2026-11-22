# Quy tắc đặt tên, viết hoa và định danh có dấu phân cách trong SQL

Khi học SQL, ta thường chú ý đến các lệnh như `CREATE TABLE`, `INSERT` và `SELECT`. Tuy nhiên, ngay trong một câu lệnh đơn giản, hệ quản trị cơ sở dữ liệu (DBMS) phải phân biệt **từ khóa**, **tên đối tượng**, **giá trị dữ liệu** và các **ký hiệu cú pháp**. Cách đặt tên cũng ảnh hưởng trực tiếp đến việc một câu SQL có chạy đúng trên nhiều DBMS hay không.

Bài này giải thích ba vấn đề có liên hệ chặt chẽ:

1. **Quy tắc đặt tên:** tên bảng, cột, schema, chỉ mục, bí danh... nên tuân theo những giới hạn và quy ước nào?
2. **Quy tắc viết hoa/viết thường:** `SELECT`, `select`, `SanPham` và `sanpham` có luôn tương đương không?
3. **Định danh có dấu phân cách** (*delimited/quoted identifier*): khi nào cần viết `"Ten San Pham"` thay cho `ten_san_pham`, và dấu nháy tác động gì đến tên?

Các ví dụ chạy minh họa chủ yếu sử dụng **PostgreSQL**. Phần so sánh sẽ chỉ ra những khác biệt đáng chú ý ở MySQL, SQL Server và Oracle. Cú pháp và hành vi xử lý tên đối tượng **không hoàn toàn thống nhất giữa các hệ quản trị**, vì vậy cần biết rõ DBMS đang sử dụng trước khi áp dụng một quy tắc đặc thù.

## 1. Định danh là gì?

Trong SQL, **định danh** (*identifier*) là tên dùng để tham chiếu một đối tượng hoặc một phần của câu lệnh, chẳng hạn:

- Tên cơ sở dữ liệu, schema, bảng, view, cột;
- Tên chỉ mục, ràng buộc, sequence, hàm, thủ tục;
- Tên role/user tùy hệ quản trị;
- Bí danh (*alias*) đặt tạm cho bảng, cột hoặc biểu thức trong truy vấn.

Ví dụ:

~~~sql
SELECT sp.ma_san_pham, sp.ten_san_pham
FROM san_pham AS sp
WHERE sp.gia > 100000;
~~~

Ở đây:

| Thành phần | Vai trò |
| --- | --- |
| `SELECT`, `FROM`, `AS`, `WHERE` | **Từ khóa SQL**, cấu thành câu lệnh. |
| `san_pham` | **Định danh** của bảng. |
| `ma_san_pham`, `ten_san_pham`, `gia` | **Định danh** của các cột. |
| `sp` | **Định danh** dùng làm bí danh bảng trong truy vấn. |
| `100000` | **Giá trị số**, không phải định danh. |
| `.`, `,`, `>` | **Ký hiệu/toán tử**, không phải một phần của tên trong ví dụ này. |

Một định danh có thể là tên do người thiết kế tạo ra (ví dụ tên bảng) hoặc tên do câu lệnh gán tạm (ví dụ `sp`). Đặt tên nhất quán giúp câu SQL dễ đọc và giảm nguy cơ phải phụ thuộc vào những cú pháp trích dẫn riêng của DBMS.

## 2. Định danh thông thường: tên không cần dấu phân cách

**Định danh thông thường** (*regular/unquoted identifier*) được viết trực tiếp, không bao bởi dấu nháy định danh:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL,
    gia NUMERIC(12, 2) NOT NULL
);
~~~

Các tên `san_pham`, `ma_san_pham`, `ten_san_pham`, `gia` dễ dùng vì:

- Bắt đầu bằng chữ cái;
- Tiếp theo chỉ gồm chữ cái, chữ số hoặc dấu gạch dưới `_`;
- Không chứa khoảng trắng;
- Không trùng từ khóa SQL đang có tác dụng trong vị trí cú pháp đó;
- Không yêu cầu phân biệt chữ hoa/chữ thường để nhận diện đúng đối tượng.

### 2.1. Một tập quy tắc đặt tên thực dụng

Để tạo tên có thể sử dụng ổn định trên nhiều DBMS và công cụ, có thể chọn quy ước:

~~~text
^[a-z][a-z0-9_]*$
~~~

Đây là **quy ước của dự án**, không phải biểu thức chính thức mô tả toàn bộ tên hợp lệ của SQL. Nó có nghĩa: ký tự đầu tiên là chữ thường ASCII `a`–`z`; các ký tự tiếp theo là chữ thường, số hoặc `_`.

| Tên | Theo quy ước đề xuất | Nhận xét |
| --- | --- | --- |
| `san_pham` | Có | Ngắn, rõ nghĩa, phân tách các từ. |
| `don_hang_2026` | Có | Chữ số ở phía sau là phù hợp. |
| `maKhachHang` | Không | Dùng chữ hoa; có thể chọn `ma_khach_hang`. |
| `2san_pham` | Không | Bắt đầu bằng chữ số; nhiều DBMS không chấp nhận khi không trích dẫn. |
| `ten san pham` | Không | Có khoảng trắng, cần định danh có dấu phân cách nếu giữ tên này. |
| `gia-ban` | Không | Dấu `-` thường được hiểu như phép trừ. |
| `đơn_hàng` | Không | Ký tự Unicode có thể được DBMS hỗ trợ nhưng làm giảm tính nhất quán khi dùng công cụ/dialect khác. |
| `order` | Khớp mẫu ký tự nhưng **không nên dùng** | `ORDER` là từ khóa SQL; quy tắc ký tự chưa đủ để bảo đảm tên không xung đột từ khóa. |

Một số DBMS hỗ trợ tập ký tự rộng hơn, cho phép tên bắt đầu bằng dấu gạch dưới, ký tự Unicode hoặc ký tự đặc biệt trong những hoàn cảnh cụ thể. Tên hợp lệ cũng có **giới hạn độ dài** theo từng hệ quản trị và đôi khi theo từng loại đối tượng. Không nên suy ra rằng mọi tên phù hợp biểu thức trên đều chắc chắn hợp lệ ở mọi DBMS: vẫn phải tránh từ khóa dành riêng và các quy tắc tên hệ thống.

### 2.2. Tránh dùng từ khóa làm tên

Hãy xem ví dụ cố tình đặt tên bảng là `order`:

~~~sql
-- Không nên dùng vì ORDER là từ khóa cú pháp:
-- CREATE TABLE order (id INTEGER);

-- Đặt tên rõ nghĩa và không xung đột:
CREATE TABLE don_hang (
    ma_don_hang INTEGER PRIMARY KEY
);
~~~

Những từ như `SELECT`, `FROM`, `ORDER`, `GROUP` có vai trò cú pháp đặc biệt. **Danh sách từ khóa dành riêng thay đổi theo DBMS và phiên bản**; có từ khóa được phép làm định danh ở một ngữ cảnh nhưng bị cấm ở ngữ cảnh khác. Để dễ bảo trì, ưu tiên tên mô tả nghiệp vụ như `don_hang`, `nhom_san_pham` thay vì dựa vào ngoại lệ của bộ phân tích cú pháp.

### 2.3. Phân biệt hợp lệ về cú pháp và có ý nghĩa

`a1`, `tbl_001` có thể hợp lệ về ký tự nhưng khó hiểu. Tên tốt thường diễn đạt đúng ý nghĩa:

~~~text
Không rõ:  tbl1, data2, value, temp
Rõ hơn:   khach_hang, chi_tiet_don_hang, tong_tien, ngay_tao
~~~

Việc chọn tên số ít hay số nhiều (`san_pham` hay `cac_san_pham`) có thể tùy quy ước nhóm; quan trọng là **nhất quán trong cùng dự án**. Tránh tên quá ngắn, tên mang ý nghĩa thay đổi theo thời gian hoặc có cách viết dễ gây nhầm lẫn.

## 3. Viết hoa, viết thường: từ khóa và định danh không giống nhau

### 3.1. Từ khóa SQL thường không phân biệt chữ hoa/thường

Trong câu lệnh thông dụng, các cách viết sau có cùng ý nghĩa:

~~~sql
SELECT ma_san_pham FROM san_pham;
select ma_san_pham from san_pham;
SeLeCt ma_san_pham FrOm san_pham;
~~~

Do đó, **viết hoa từ khóa** (`SELECT`, `FROM`, `WHERE`, `JOIN`) là quy ước trình bày giúp dễ phân biệt với tên cột và bảng, không phải một điều kiện để SQL hoạt động.

Một phong cách thường dùng:

~~~sql
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE gia >= 100000
ORDER BY ten_san_pham;
~~~

### 3.2. Với định danh, DBMS có quy tắc chuẩn hóa tên riêng

Khi gặp **định danh không có dấu phân cách**, DBMS có thể chuyển tên đó về một kiểu chữ chuẩn trước khi tìm đối tượng:

- **PostgreSQL:** chuyển định danh không trích dẫn sang **chữ thường**.
- **Oracle Database:** chuyển định danh không trích dẫn sang **chữ hoa**.
- **MySQL:** hành vi nhạy cảm hoa/thường của **tên bảng và cơ sở dữ liệu** phụ thuộc hệ điều hành và cấu hình `lower_case_table_names`; tên cột nhìn chung không phân biệt hoa/thường.
- **SQL Server:** việc so sánh tên đối tượng thường phụ thuộc **collation** phù hợp; một số môi trường phân biệt hoa/thường, một số không.

Điều đó dẫn đến một điểm cần nhớ: **SQL keyword thường không nhạy chữ hoa/thường, nhưng không được suy rộng điều này cho mọi tên đối tượng trên mọi DBMS**.

### 3.3. Ví dụ cụ thể trong PostgreSQL

~~~sql
CREATE TABLE KhachHang (
    MaKhachHang INTEGER PRIMARY KEY
);

-- PostgreSQL chuẩn hóa tên không trích dẫn về chữ thường:
SELECT MaKhachHang FROM KhachHang;
SELECT makhachhang FROM khachhang;
SELECT MAKHACHHANG FROM KHACHHANG;
~~~

Ba câu `SELECT` trên đều tham chiếu đến tên được lưu theo dạng chữ thường `khachhang` và `makhachhang` trong PostgreSQL. Tuy nhiên:

~~~sql
-- Trong PostgreSQL, các tên bên dưới được giữ đúng hoa/thường:
-- SELECT "MaKhachHang" FROM "KhachHang";
~~~

Câu lệnh đã được chú thích sẽ báo lỗi nếu trước đó chỉ chạy `CREATE TABLE KhachHang (...)`, bởi `"KhachHang"` khác `khachhang` và `"MaKhachHang"` khác `makhachhang`.

Đối chiếu với Oracle: định danh không trích dẫn `KhachHang` thường được chuẩn hóa thành `KHACHHANG`. Vì vậy cách tương đương khi dùng nháy kép ở Oracle phải khớp tên viết hoa được lưu, ví dụ `"KHACHHANG"`; không thể áp dụng nguyên xi quy tắc chuyển về chữ thường của PostgreSQL.

## 4. Định danh có dấu phân cách là gì?

**Định danh có dấu phân cách** (*delimited identifier*) là tên được bao trong ký hiệu trích dẫn định danh. Theo SQL chuẩn, ký hiệu đó là **dấu nháy kép `"`**.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE "Chi Tiet Don Hang" (
    "Ma Don Hang" INTEGER NOT NULL,
    "Ma San Pham" INTEGER NOT NULL,
    "So Luong" INTEGER NOT NULL
);

SELECT "Ma Don Hang", "So Luong"
FROM "Chi Tiet Don Hang"
WHERE "So Luong" > 0;
~~~

Tên bảng và cột được phép có dấu cách vì được bao bằng dấu nháy kép. Dấu phân cách là **cú pháp**, không được tính là một phần của tên: tên bảng thực tế là `Chi Tiet Don Hang`, không phải chuỗi ký tự có thêm hai dấu `"` ở đầu/cuối.

Định danh có dấu phân cách thường được dùng khi:

1. Tên chứa khoảng trắng, dấu câu hoặc ký tự mà định danh thông thường không chấp nhận.
2. Tên xung đột với một từ khóa SQL.
3. Muốn giữ nguyên cách viết hoa/thường của tên đã khai báo trong hệ quản trị có cơ chế phân biệt phù hợp.
4. Cần truy cập bảng hoặc cột cũ có tên khác quy ước hiện tại.

Không nên dùng tên khó xử lý chỉ vì DBMS cho phép trích dẫn. Mỗi lần viết truy vấn, tạo migration, cấu hình ORM hay truy cập từ công cụ bên ngoài, tên có ký tự đặc biệt hoặc chữ hoa/thường bắt buộc chính xác có thể khiến mã nguồn khó bảo trì hơn.

### 4.1. Nháy kép có thể tạo tên khác với tên thông thường

Trong PostgreSQL, hai bảng dưới đây **có thể cùng tồn tại**:

~~~sql
CREATE TABLE san_pham (
    id INTEGER PRIMARY KEY
);

CREATE TABLE "San_Pham" (
    id INTEGER PRIMARY KEY
);

SELECT * FROM san_pham;     -- Bảng san_pham
SELECT * FROM "San_Pham";   -- Bảng San_Pham
~~~

`"San_Pham"` giữ nguyên chữ hoa `S`, `P`, còn `san_pham` không trích dẫn được dùng theo dạng chữ thường. Vì vậy:

~~~sql
SELECT * FROM San_Pham;     -- Trong PostgreSQL: bảng san_pham
SELECT * FROM "san_pham";   -- Trong PostgreSQL: cũng là bảng san_pham
~~~

Trường hợp này dễ làm người mới tưởng có “lỗi ngẫu nhiên” khi đổi kiểu viết. Thực ra DBMS đang áp dụng hai quy tắc xử lý tên khác nhau. Những câu `CREATE TABLE` trong phần này độc lập với ví dụ đã tạo bảng `san_pham` ở phần trước; hãy chạy trong schema trống hoặc môi trường thử nghiệm mới nếu thực hành từ đầu.

### 4.2. Trích dẫn từ khóa làm định danh

~~~sql
CREATE TABLE "order" (
    "select" INTEGER,
    ghi_chu VARCHAR(200)
);

SELECT "select", ghi_chu
FROM "order";
~~~

Đây là ví dụ hợp lệ trong PostgreSQL khi cố ý dùng tên trùng từ khóa. Nó **minh họa khả năng của dấu phân cách**, không phải khuyến nghị đặt tên. Trong ứng dụng mới, `don_hang` và `ma_lua_chon` sẽ dễ dùng hơn.

### 4.3. Ký tự nháy kép ở bên trong tên

Trong cú pháp định danh dùng nháy kép, muốn đặt **một dấu nháy kép thực sự trong tên** thì viết hai dấu nháy kép liên tiếp:

~~~sql
CREATE TABLE "Bao ""Cao""" (
    id INTEGER PRIMARY KEY
);

SELECT id FROM "Bao ""Cao""";
~~~

Tên bảng được lưu là `Bao "Cao"`. Đây là kỹ thuật escape nháy kép trong định danh, khác với cách escape giá trị chuỗi.

Một số ký tự vẫn bị hạn chế dù dùng dấu phân cách (ví dụ ký tự null trong tên đối tượng ở nhiều DBMS); giới hạn độ dài vẫn áp dụng.

## 5. Đừng nhầm dấu nháy định danh với dấu nháy của giá trị chuỗi

Trong SQL thông dụng:

- **`'...'` (nháy đơn):** biểu diễn hằng chuỗi, chẳng hạn `'Ban phim'`.
- **`"..."` (nháy kép theo SQL chuẩn):** biểu diễn định danh, chẳng hạn `"Ten San Pham"`.
- **Không có nháy:** định danh thông thường hoặc từ khóa, tùy vị trí cú pháp.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE san_pham (
    id INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL
);

INSERT INTO san_pham (id, ten_san_pham)
VALUES (1, 'Ban phim');

SELECT ten_san_pham FROM san_pham;
-- Đọc giá trị của cột ten_san_pham: Ban phim.

SELECT "ten_san_pham" FROM san_pham;
-- Cũng đọc cột ten_san_pham (đúng chính tả chữ thường PostgreSQL).

SELECT 'ten_san_pham' FROM san_pham;
-- Trả về chuỗi cố định 'ten_san_pham' ở mỗi dòng, không đọc cột.
~~~

Sai lầm thường gặp:

~~~sql
-- Sai mục đích nếu muốn đọc cột:
SELECT 'gia' FROM san_pham;

-- Đúng khi đọc cột có tên gia:
-- SELECT gia FROM san_pham;  -- cần cột gia tồn tại trong bảng
~~~

**Lưu ý về phương ngữ:** MySQL mặc định thường dùng nháy kép như một dạng dấu nháy chuỗi nếu không bật chế độ `ANSI_QUOTES`; khi bật `ANSI_QUOTES`, nháy kép được hiểu là dấu trích dẫn định danh. Do đó, không thể bê nguyên mọi câu lệnh có nháy kép từ PostgreSQL sang MySQL mà bỏ qua cấu hình chế độ SQL.

## 6. Dấu phân cách khác nhau giữa các hệ quản trị

| DBMS | Dạng trích dẫn định danh phổ biến | Đặc điểm cần nhớ |
| --- | --- | --- |
| **PostgreSQL** | `"ten_bang"` | Tên không trích dẫn được chuyển sang chữ thường; tên trích dẫn giữ nguyên hoa/thường và cần tham chiếu đúng. |
| **Oracle Database** | `"TEN_BANG"` | Tên không trích dẫn được chuyển sang chữ hoa; tên trích dẫn có thể giữ nguyên hoa/thường và ký tự đặc biệt. |
| **MySQL** | ``ten_bang`` (*backtick*) | Nháy kép làm dấu phân cách định danh khi bật `ANSI_QUOTES`. Tính nhạy hoa/thường của tên bảng/database phụ thuộc hệ điều hành và cấu hình. |
| **SQL Server** | `[ten_bang]` hoặc `"ten_bang"` | Cặp `[]` phổ biến trong T-SQL; nháy kép dùng làm dấu phân cách khi `QUOTED_IDENTIFIER` bật. Nhạy hoa/thường của tên thường phụ thuộc collation. |

Ví dụ tương ứng cho một tên bảng có dấu cách:

~~~sql
-- PostgreSQL, Oracle, và SQL Server khi QUOTED_IDENTIFIER ON:
SELECT * FROM "Danh Muc";

-- MySQL:
SELECT * FROM `Danh Muc`;

-- SQL Server:
SELECT * FROM [Danh Muc];
~~~

Trong khối mã ở trên, hai ký hiệu ``` dùng để biểu thị **backtick** (dấu huyền ngược), không phải nháy đơn. Khi thực thi trong MySQL, nhập dấu backtick thật ở hai đầu tên:

~~~text
Tên có khoảng trắng: Danh Muc
MySQL:             `Danh Muc`
~~~

Cần phân biệt **cú pháp dấu phân cách** với **quy tắc so sánh tên**. Dùng dấu nháy kép không có nghĩa tất cả hệ quản trị đều sẽ phân biệt chữ hoa/thường giống PostgreSQL; trên SQL Server, collation có thể khiến các định danh khác nhau ở chữ hoa/thường vẫn được coi là tương đương.

### 6.1. Tại sao không suy diễn từ hệ quản trị này sang hệ khác?

- Trong PostgreSQL, `CREATE TABLE Demo (...)` tạo tên thường `demo`, còn `CREATE TABLE "Demo" (...)` tạo tên `Demo`.
- Trong Oracle, `CREATE TABLE Demo (...)` tạo tên chuẩn hóa `DEMO`, khác tên trích dẫn `"Demo"`.
- Trong MySQL, hai bảng tên chỉ khác hoa/thường có thể cùng tồn tại hoặc bị coi là trùng nhau tùy cấu hình môi trường. Việc chuyển dữ liệu từ môi trường phát triển sang môi trường triển khai có thể bộc lộ xung đột tên.
- Trong SQL Server, lựa chọn collation ảnh hưởng đến phép so sánh tên theo ngữ cảnh; không nên giả định mọi môi trường luôn không phân biệt hoa/thường.

Với dự án cần di chuyển giữa DBMS, sử dụng **tên chữ thường ASCII dạng `snake_case`, tránh từ khóa và tránh ký tự cần trích dẫn** sẽ giảm số tình huống phụ thuộc phương ngữ.

## 7. Tên đầy đủ, dấu chấm và bí danh

Một tên có dấu chấm trong cú pháp SQL thường chỉ **đường dẫn tới đối tượng**, ví dụ:

~~~sql
SELECT sp.ten_san_pham
FROM public.san_pham AS sp;
~~~

Trong PostgreSQL, `public.san_pham` gồm hai định danh: schema `public` và bảng `san_pham`. `sp.ten_san_pham` gồm bí danh bảng `sp` và cột `ten_san_pham`. Dấu chấm ở đây là dấu phân cách các thành phần, **không phải một phần của một định danh duy nhất**.

Khi cần trích dẫn, trích dẫn từng thành phần:

~~~sql
-- Tạo bảng trong schema public, tên có khoảng trắng:
CREATE TABLE public."San Pham" (
    "Ma San Pham" INTEGER PRIMARY KEY
);

-- Có thể trích dẫn cả schema và bảng riêng biệt:
SELECT "Ma San Pham"
FROM "public"."San Pham";
~~~

Hai cách viết sau **không tương đương**:

~~~sql
FROM "public"."San Pham"  -- Schema public, bảng San Pham.
FROM "public.San Pham"    -- Một định danh duy nhất chứa dấu chấm.
~~~

Dòng thứ hai, nếu nằm trong một câu truy vấn hoàn chỉnh, tìm một đối tượng mang nguyên tên `public.San Pham` trong schema được tìm kiếm; nó không tự tách thành schema và bảng. Đặt dấu nháy đúng vị trí quan trọng khi xây dựng câu SQL tự động.

### 7.1. Bí danh cột để hiển thị tên thân thiện

Tên thật của bảng/cột nên ổn định và dễ lập trình. Khi cần nhãn có khoảng trắng, dấu tiếng Việt hoặc cách viết đẹp để đưa lên báo cáo, có thể dùng **bí danh trích dẫn** trong truy vấn:

~~~sql
SELECT
    sp.ten_san_pham AS "Tên sản phẩm",
    sp.gia AS "Giá bán"
FROM san_pham AS sp
ORDER BY sp.gia DESC;
~~~

Lợi ích: schema vẫn dùng `ten_san_pham`, `gia`, trong khi kết quả truy vấn được hiển thị với nhãn `Tên sản phẩm`, `Giá bán`. Bí danh chỉ ảnh hưởng đến **tên cột của kết quả truy vấn**; nó không đổi tên cột vật lý trong bảng.

Trong một số công cụ ORM, BI hoặc ứng dụng, tên cột kết quả do bí danh tạo ra có thể được dùng làm key để truy cập dữ liệu. Vì vậy nên thống nhất giữa bí danh để hiển thị với tên kỹ thuật dành cho API, tránh vô tình làm hỏng hợp đồng dữ liệu khi đổi nhãn.

## 8. Một bộ quy ước đặt tên có thể áp dụng cho dự án

Với dự án Database SQL mới, có thể thống nhất bảng quy ước sau. Đây là **khuyến nghị thiết kế**, không phải yêu cầu bắt buộc của cú pháp SQL:

| Đối tượng | Quy ước | Ví dụ |
| --- | --- | --- |
| Schema | Chữ thường, ngắn gọn, phản ánh miền nghiệp vụ | `ban_hang` |
| Bảng | Danh từ mô tả thực thể, `snake_case` | `san_pham`, `don_hang`, `chi_tiet_don_hang` |
| Cột | Mô tả ý nghĩa, `snake_case` | `ma_san_pham`, `so_luong`, `ngay_tao` |
| Khóa chính | Một kiểu nhất quán trong dự án | `id` hoặc `ma_san_pham` |
| Khóa ngoại | Chỉ rõ thực thể được tham chiếu | `san_pham_id` |
| Chỉ mục | Tiền tố thể hiện mục đích, tránh tên dài quá giới hạn | `idx_san_pham_ten` |
| Ràng buộc duy nhất | Tiền tố `uq_` và các cột liên quan | `uq_khach_hang_email` |
| Khóa ngoại có tên | Tiền tố `fk_` và mối quan hệ | `fk_don_hang_khach_hang` |
| Bí danh bảng | Ngắn nhưng rõ trong ngữ cảnh | `sp`, `dh`, `ct` |
| Từ khóa SQL | Chữ hoa để phân biệt với định danh | `SELECT`, `JOIN`, `WHERE` |

Ví dụ kết hợp:

~~~sql
CREATE TABLE khach_hang (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_khach_hang_email UNIQUE (email)
);

CREATE TABLE don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL,
    ngay_tao DATE NOT NULL,
    CONSTRAINT fk_don_hang_khach_hang
        FOREIGN KEY (khach_hang_id) REFERENCES khach_hang(id)
);

SELECT
    dh.id AS ma_don_hang,
    kh.ho_ten AS ten_khach_hang,
    dh.ngay_tao
FROM don_hang AS dh
JOIN khach_hang AS kh
    ON kh.id = dh.khach_hang_id
ORDER BY dh.ngay_tao DESC, dh.id DESC;
~~~

Toàn bộ định danh trong ví dụ đều viết thường, dùng gạch dưới và tránh từ khóa. Vì vậy không phải bao thêm dấu phân cách, truy vấn dễ đọc và ít gặp vấn đề do khác biệt chuẩn hóa chữ hoa/thường.

## 9. Ảnh hưởng thực tế khi đổi tên, chuyển DBMS và tạo SQL động

### 9.1. Tên là một phần của hợp đồng giữa các thành phần

Tên bảng/cột có thể xuất hiện đồng thời trong:

- Các file migration và script vận hành;
- Entity/ORM mapping, câu SQL trong repository và stored procedure;
- View, trigger, báo cáo và công cụ BI;
- Truy vấn gọi từ ứng dụng, job nhập dữ liệu và pipeline tích hợp.

Khi đổi `"KhachHang"` thành `khach_hang`, tác động không chỉ nằm ở cú pháp SQL mà còn ở những chương trình đang tham chiếu đúng tên cũ. Một lệnh đổi tên như `ALTER TABLE ... RENAME TO ...` cũng có cú pháp và hậu quả phụ thuộc DBMS; cần xét ràng buộc phụ thuộc, triển khai theo phiên bản và phạm vi dữ liệu sử dụng trước khi thực hiện.

### 9.2. ORM và công cụ sinh SQL có thể tự thêm dấu phân cách

Một ORM có thể sinh câu lệnh dựa trên tên class/property hoặc theo chiến lược đặt tên (*naming strategy*). Ví dụ thuộc tính `productName` có thể được ánh xạ thành `product_name`, `PRODUCT_NAME` hay tên giữ nguyên có dấu phân cách, tùy cấu hình.

Nếu database thực tế chứa cột `product_name` nhưng ORM sinh ra `"productName"` trên PostgreSQL, truy vấn sẽ tìm cột có đúng tên `productName` và có thể báo lỗi. Do đó, quy tắc đặt tên trong migration, ORM, SQL viết tay và công cụ báo cáo cần tương thích với nhau.

### 9.3. Trích dẫn định danh không thay thế truy vấn tham số hóa

Truy vấn có hai loại đầu vào cần xử lý khác nhau:

**Giá trị dữ liệu** nên truyền bằng tham số của driver hoặc ORM:

~~~sql
-- Minh họa placeholder kiểu JDBC/PreparedStatement:
SELECT id, ten_san_pham
FROM san_pham
WHERE ten_san_pham = ?;
~~~

Ứng dụng bind giá trị người dùng vào `?`, thay vì nối trực tiếp dữ liệu vào chuỗi SQL. Cách này giúp tách dữ liệu khỏi cú pháp câu lệnh và giảm nguy cơ SQL injection.

**Tên bảng hoặc cột** thường không thể truyền qua cùng placeholder dành cho giá trị:

~~~sql
-- Không hiểu là bind tên bảng động bằng placeholder:
-- SELECT * FROM ?;
~~~

Khi thật sự cần chọn tên cột/bảng động, ứng dụng nên **giới hạn bằng danh sách tên được phép**, rồi dùng hàm trích dẫn định danh do driver hoặc thư viện dành cho DBMS cung cấp. Không nối chuỗi đầu vào tùy ý để tạo định danh, kể cả khi dự định bao nháy kép. Việc trích dẫn bảo đảm cú pháp định danh, còn kiểm soát nguồn đầu vào mới quyết định người dùng được truy cập đối tượng nào.

### 9.4. Một vài rủi ro cần phân biệt

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| PostgreSQL báo không tìm thấy `"TenKhachHang"` | Cột ban đầu tạo không trích dẫn, thực tế được chuẩn hóa thành `tenkhachhang`. | Tham chiếu đúng tên hoặc đổi schema/mapping một cách có kiểm soát. |
| MySQL chạy được trên máy phát triển nhưng lỗi tên bảng khi chuyển môi trường | Cấu hình `lower_case_table_names` và quy tắc hệ điều hành khác nhau. | Dùng tên nhất quán, kiểm tra cài đặt và quá trình chuyển môi trường. |
| SQL Server gặp tên có dấu cách | Truy vấn không trích dẫn tên theo cú pháp T-SQL. | Dùng `[Ten Cot]` hoặc nháy kép khi thiết lập tương ứng cho phép. |
| Truy vấn trả về chữ `gia` thay vì giá bán | Viết `'gia'` là chuỗi hằng. | Dùng `gia` hoặc định danh trích dẫn đúng. |
| Một ORM sinh tên cột khác migration | Hai bên dùng chiến lược đặt tên/quote khác nhau. | Đồng bộ mapping, tên vật lý và convention. |
| Tên bảng động bị thao túng | Nối input người dùng vào cú pháp SQL. | Dùng allowlist, quyền tối thiểu và quote identifier đúng DBMS. |

## 10. Bài tập củng cố

Các câu dưới đây giả định **PostgreSQL** nếu không ghi chú khác. Hãy dự đoán trước kết quả, sau đó đối chiếu phần giải thích.

### Bài 1: Từ khóa và tên

Ba câu lệnh nào cùng tham chiếu một bảng và một cột, nếu bảng được tạo bằng:

~~~sql
CREATE TABLE HoaDon (
    MaHoaDon INTEGER
);
~~~

Các truy vấn:

~~~sql
-- A
SELECT MaHoaDon FROM HoaDon;

-- B
select mahoadon from hoadon;

-- C
SELECT "MaHoaDon" FROM "HoaDon";

-- D
SELECT "mahoadon" FROM "hoadon";
~~~

**Đáp án:** A, B và D cùng tham chiếu bảng `hoadon` và cột `mahoadon` trong PostgreSQL. C tham chiếu tên có chữ hoa đúng từng ký tự nên không tìm thấy đối tượng được tạo không trích dẫn.

### Bài 2: Nháy đơn hay nháy kép?

Giả sử bảng `khach_hang` có cột `ho_ten`. Hai câu sau khác nhau thế nào?

~~~sql
SELECT 'ho_ten' FROM khach_hang;
SELECT "ho_ten" FROM khach_hang;
~~~

**Đáp án:** Câu đầu trả về hằng chuỗi `ho_ten` cho mỗi dòng kết quả. Câu sau đọc giá trị thực tế của cột `ho_ten`. Trong PostgreSQL, nháy kép giữ chính xác tên cột được trích dẫn.

### Bài 3: Đặt tên có khoảng trắng

Muốn truy vấn bảng mang tên chính xác `Bao Cao Thang` và cột `Tong Tien` trong PostgreSQL, dùng:

~~~sql
SELECT "Tong Tien"
FROM "Bao Cao Thang";
~~~

**Giải thích:** Cả tên cột lẫn tên bảng đều chứa khoảng trắng, vì vậy cần đặt toàn bộ từng định danh trong nháy kép. Nếu bảng nằm trong schema `reporting`, viết `reporting."Bao Cao Thang"` hoặc `"reporting"."Bao Cao Thang"`.

### Bài 4: Quy ước cho bảng mới

Đề xuất tên không cần trích dẫn cho bảng “Chi tiết đơn hàng”, cột “Mã sản phẩm”, và “Số lượng”. Một lựa chọn:

~~~sql
CREATE TABLE chi_tiet_don_hang (
    ma_san_pham INTEGER NOT NULL,
    so_luong INTEGER NOT NULL
);
~~~

**Giải thích:** Dùng `snake_case`, chữ thường ASCII và tên có nghĩa giúp mã dễ đọc, dễ gõ, thuận tiện cho migration và công cụ. Bảng thực tế còn cần thiết kế khóa và ràng buộc tùy yêu cầu nghiệp vụ; bài tập này chỉ tập trung vào quy tắc tên.

### Bài 5: Di chuyển giữa hai DBMS

Một nhóm tạo bảng `"KhachHang"` trên PostgreSQL rồi viết ứng dụng tham chiếu `KhachHang` không trích dẫn. Có vấn đề gì?

**Đáp án:** PostgreSQL chuẩn hóa `KhachHang` không trích dẫn thành `khachhang`, khác với tên có chữ hoa được tạo là `"KhachHang"`. Ứng dụng phải tham chiếu đúng `"KhachHang"` hoặc thiết kế lại tên vật lý và mapping cho nhất quán. Nếu chuyển sang Oracle, quy tắc chuyển tên không trích dẫn là viết hoa, nên phải kiểm tra lại thay vì giả định hai DBMS có hành vi giống nhau.

## 11. Ghi nhớ để viết SQL ổn định

| Nội dung | Quy tắc cốt lõi |
| --- | --- |
| **Từ khóa** | Thông thường không phân biệt hoa/thường; viết `SELECT`, `FROM`, `WHERE` bằng chữ hoa là quy ước dễ đọc. |
| **Định danh thường** | Ưu tiên tên có nghĩa, chữ thường `snake_case`, tránh khoảng trắng, ký tự đặc biệt và từ khóa dành riêng. |
| **Định danh có dấu phân cách** | Nháy kép theo SQL chuẩn có thể cho phép ký tự đặc biệt và giữ cách viết tên; cần dùng đúng cú pháp DBMS. |
| **Cơ chế hoa/thường** | PostgreSQL chuyển tên không trích dẫn sang chữ thường; Oracle sang chữ hoa; MySQL và SQL Server có hành vi phụ thuộc cấu hình/ngữ cảnh. |
| **Nháy đơn** | Dùng cho giá trị chuỗi như `'Ban phim'`; không nhầm với cách trích dẫn tên bảng/cột. |
| **Tên có dấu chấm** | `schema.table` gồm hai định danh; khi trích dẫn, đặt dấu phân cách quanh từng thành phần cần thiết. |
| **Khả năng bảo trì** | Giữ quy ước nhất quán giữa SQL viết tay, migration, ORM, báo cáo và môi trường triển khai. |

Từ một câu lệnh nhỏ như `SELECT ten_san_pham FROM san_pham`, có thể thấy việc **phân biệt đúng từ khóa, định danh và giá trị**, cùng quy tắc **chuẩn hóa chữ hoa/thường** và **sử dụng dấu phân cách đúng lúc**, quyết định DBMS đọc tên đối tượng như thế nào. Nắm chắc các quy tắc này giúp tránh lỗi “không tìm thấy bảng/cột”, giữ SQL dễ bảo trì và giảm rủi ro khi đổi công cụ hoặc hệ quản trị.
