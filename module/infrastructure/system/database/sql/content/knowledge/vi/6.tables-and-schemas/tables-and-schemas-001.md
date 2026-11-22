# CREATE SCHEMA, CREATE TABLE và tổ chức đối tượng trong SQL

Khi xây dựng cơ sở dữ liệu quan hệ, chúng ta cần quyết định không chỉ **dữ liệu được lưu thành những bảng nào**, mà còn **bảng thuộc nhóm đối tượng nào**, **các bảng tham chiếu nhau ra sao**, **quy tắc nào phải luôn đúng** và **ai có quyền sử dụng chúng**. Hai câu lệnh định nghĩa dữ liệu (DDL — Data Definition Language) nền tảng là:

- `CREATE SCHEMA`: tạo **lược đồ**, tức một không gian tên để tổ chức đối tượng trong những hệ quản trị có hỗ trợ.
- `CREATE TABLE`: tạo **bảng**, định nghĩa các cột, kiểu dữ liệu, khóa, ràng buộc và một số thuộc tính lưu trữ khác.

Bài học sử dụng **PostgreSQL** làm hệ quản trị chính cho những ví dụ thực hành. Khái niệm bảng và namespace cũng xuất hiện ở SQL Server, Oracle, MySQL/MariaDB và SQLite nhưng ý nghĩa của chữ “schema” và cú pháp tạo bảng **không hoàn toàn đồng nhất**. Phần so sánh ở cuối giúp bạn tránh nhầm lẫn khi đổi hệ quản trị.

## 1. Database, schema, table và column khác nhau thế nào?

Trong PostgreSQL, ta có thể hình dung:

~~~text
Máy chủ PostgreSQL
├── Database: ung_dung
│   ├── Schema: ban_hang
│   │   ├── Table: khach_hang
│   │   │   ├── Column: id
│   │   │   ├── Column: ho_ten
│   │   │   └── Column: email
│   │   ├── Table: san_pham
│   │   ├── Table: don_hang
│   │   └── View: v_don_hang
│   └── Schema: nhan_su
│       └── Table: nhan_vien
└── Database: bao_cao
    └── Schema: public
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Database** | Chứa các schema và đối tượng của một cơ sở dữ liệu | `ung_dung` |
| **Schema** | Không gian tên gom các đối tượng có liên quan trong một database | `ban_hang` |
| **Table** | Cấu trúc lưu dữ liệu theo hàng và cột | `ban_hang.khach_hang` |
| **Column** | Thuộc tính có tên và kiểu dữ liệu của mỗi bản ghi | `email VARCHAR(255)` |
| **Row** | Một bản ghi có các giá trị tương ứng với cột | Khách hàng An |
| **Constraint** | Quy tắc dữ liệu phải tuân thủ | `PRIMARY KEY`, `CHECK` |
| **Index** | Cấu trúc hỗ trợ tìm kiếm, sắp xếp hoặc thực thi ràng buộc | Index trên `email` |
| **View** | Truy vấn được đặt tên, có thể truy cập như bảng logic | `ban_hang.v_don_hang` |

**Một PostgreSQL database có thể chứa nhiều schema.** Schema không phải một database riêng và không tự tạo ra máy chủ hay vùng lưu trữ độc lập. Các bảng thuộc các schema khác nhau trong cùng database có thể JOIN với nhau, tạo khóa ngoại qua schema và tham gia cùng một transaction khi quyền cho phép.

### 1.1. Vì sao không đặt tất cả bảng trong một schema?

Khi hệ thống nhỏ, chỉ có vài bảng nên có vẻ không cần phân nhóm. Nhưng hệ thống tăng lên có thể có hai bảng cùng tên `lich_su` phục vụ hai phòng ban khác nhau:

~~~text
ban_hang.lich_su
nhan_su.lich_su
~~~

Phân nhóm bằng schema giúp:

1. **Tránh trùng tên** giữa các nhóm dữ liệu.
2. **Phân biệt miền nghiệp vụ** của bảng mà không phải suy ra từ tên ngắn.
3. **Quản lý quyền** tạo và truy cập đối tượng theo namespace.
4. **Tổ chức migration, backup, quản trị và tài liệu** rõ ràng hơn.
5. **Phân định trách nhiệm** của các nhóm phát triển trong cơ sở dữ liệu dùng chung.

Schema chỉ là một thành phần của bảo mật. Được phép truy cập một schema không đồng nghĩa được xem mọi bảng bên trong. Tách schema cũng không tự cô lập dữ liệu giữa các ứng dụng như tách database, máy chủ hay chính sách bảo mật.

### 1.2. Hai cách hiểu phổ biến của từ “schema”

Từ *schema* có thể chỉ:

- **Schema theo nghĩa mô hình dữ liệu**: thiết kế tổng thể gồm các bảng, cột, khóa và quan hệ.
- **Schema theo nghĩa SQL namespace**: một đối tượng được đặt tên, tạo bằng `CREATE SCHEMA` trong những hệ quản trị như PostgreSQL.

Khi nghe “thay đổi schema”, cần xác định người nói đang muốn `ALTER TABLE` để đổi cấu trúc hay `CREATE/ALTER SCHEMA` để quản lý namespace.

## 2. CREATE SCHEMA: tạo lược đồ

### 2.1. Cú pháp PostgreSQL cơ bản

~~~sql
CREATE SCHEMA ban_hang;
~~~

Lệnh này tạo namespace có tên `ban_hang` bên trong **database hiện đang kết nối**. Nó chưa tạo `khach_hang`, `don_hang` hoặc bảng dữ liệu nào.

Nếu cần tránh lỗi tạo lại schema đã tồn tại, PostgreSQL hỗ trợ:

~~~sql
CREATE SCHEMA IF NOT EXISTS ban_hang;
~~~

`IF NOT EXISTS` có nghĩa bỏ qua bước tạo nếu schema cùng tên đã tồn tại. Nó **không kiểm tra schema đó đúng owner, đúng quyền, đúng danh sách bảng hay chưa**. Do vậy, trong hệ thống thực tế không nên xem `IF NOT EXISTS` là cơ chế migration đầy đủ.

### 2.2. Chủ sở hữu của schema

Một schema có owner; bạn có thể chọn role sở hữu tại lúc tạo nếu role đã tồn tại và người chạy có quyền thích hợp:

~~~sql
-- Chỉ chạy nếu role app_owner đã tồn tại và người thực thi có quyền phù hợp.
CREATE SCHEMA ban_hang AUTHORIZATION app_owner;
~~~

Owner của schema có quyền quản lý schema theo quy tắc PostgreSQL. Tuy nhiên, **owner của một schema và owner của từng bảng có thể là những role khác nhau**. Tạo một bảng trong schema không có nghĩa bảng luôn được gán cho role sở hữu schema.

Để tạo schema thông thường, role cần quyền `CREATE` thích hợp ở cấp database. Để tạo bảng bên trong schema, role cần quyền `CREATE` trên schema (hoặc những quyền quản trị tương đương).

### 2.3. Schema mặc định `public`

Trong PostgreSQL, `public` thường đã tồn tại ở database mới. Câu lệnh không chỉ định schema:

~~~sql
CREATE TABLE vi_du (
    id INTEGER PRIMARY KEY
);
~~~

sẽ tạo bảng trong schema đích mà PostgreSQL chọn qua `search_path` và quyền phiên, **thường** là `public` trong cấu hình đơn giản. Tuy nhiên, không được giả định mọi máy đều đặt `public` làm schema hiện tại.

Chỉ rõ schema sẽ dễ hiểu hơn:

~~~sql
CREATE TABLE public.vi_du (
    id INTEGER PRIMARY KEY
);
~~~

### 2.4. Kiểm tra một schema

Sử dụng SQL chuẩn thông tin metadata:

~~~sql
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'ban_hang';
~~~

Trong chương trình dòng lệnh PostgreSQL `psql`, có thể dùng:

~~~text
\dn
~~~

`\dn` là lệnh meta của `psql`, **không phải câu SQL**; các công cụ SQL khác có thể không hiểu. Trong các giao diện đồ họa, hãy tìm mục Schemas dưới database đang kết nối.

## 3. CREATE TABLE: khai báo bảng và cột

Cấu trúc khái quát:

~~~sql
CREATE TABLE ten_schema.ten_bang (
    ten_cot_1 kieu_du_lieu [rang_buoc_cot],
    ten_cot_2 kieu_du_lieu [rang_buoc_cot],
    ...
    [rang_buoc_muc_bang]
);
~~~

Trong PostgreSQL, hãy tạo bảng khách hàng như sau:

~~~sql
CREATE TABLE ban_hang.khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Diễn giải:

| Định nghĩa | Ý nghĩa |
|---|---|
| `ban_hang.khach_hang` | Bảng tên `khach_hang` thuộc schema `ban_hang` |
| `id BIGINT` | Số nguyên lớn dùng làm định danh |
| `GENERATED ALWAYS AS IDENTITY` | PostgreSQL tự cấp giá trị định danh khi chèn theo cách thông thường |
| `PRIMARY KEY` | ID duy nhất và không NULL |
| `ho_ten VARCHAR(100) NOT NULL` | Tên bắt buộc, dài tối đa 100 ký tự |
| `email ... UNIQUE` | Email bắt buộc và không trùng theo quy tắc so sánh của DBMS |
| `TIMESTAMPTZ` | Thời điểm có ngữ nghĩa múi giờ trong PostgreSQL |
| `DEFAULT CURRENT_TIMESTAMP` | Dùng thời điểm hiện tại của transaction khi bỏ qua cột |

`GENERATED ALWAYS AS IDENTITY` không có nghĩa ID phải liền nhau tuyệt đối: sequence có thể có khoảng trống sau lỗi hoặc transaction rollback. Trong PostgreSQL cũng có cú pháp `GENERATED BY DEFAULT AS IDENTITY` và kiểu khai báo lịch sử `SERIAL`; chúng có quy tắc khác nhau khi người dùng truyền ID tường minh.

`CREATE TABLE` chỉ tạo **cấu trúc**. Bảng mới thường rỗng; muốn có dòng dữ liệu phải `INSERT` hoặc dùng cách nạp dữ liệu khác.

### 3.1. Thêm và đọc dữ liệu

~~~sql
INSERT INTO ban_hang.khach_hang (ho_ten, email)
VALUES
    ('An', 'an@example.test'),
    ('Bình', 'binh@example.test')
RETURNING id, ho_ten, email;
~~~

`RETURNING` là cú pháp PostgreSQL giúp trả về giá trị của các dòng đã chèn, đặc biệt hữu ích với ID sinh tự động. Trong database thử nghiệm mới, ID có thể là 1 và 2; ở môi trường khác không nên đoán ID theo thứ tự.

~~~sql
SELECT id, ho_ten, email
FROM ban_hang.khach_hang
ORDER BY id;
~~~

Ví dụ kết quả:

| id | ho_ten | email |
|---:|---|---|
| 1 | An | an@example.test |
| 2 | Bình | binh@example.test |

Đây là kết quả minh họa giả định ID bắt đầu từ 1; các ID thực tế do máy chủ trả về mới là giá trị đúng.

### 3.2. Kiểu dữ liệu ảnh hưởng đến tính đúng đắn

| Nhu cầu | Ví dụ kiểu PostgreSQL | Ý nghĩa |
|---|---|---|
| Số nguyên | `INTEGER`, `BIGINT` | Số đếm, mã số |
| Văn bản ngắn có giới hạn | `VARCHAR(150)` | Tên, mã, nhãn |
| Văn bản dài | `TEXT` | Mô tả, ghi chú |
| Số thập phân chính xác | `NUMERIC(12,2)` | Giá và lượng tiền được quy định chính xác |
| Ngày | `DATE` | Chỉ ngày |
| Ngày giờ | `TIMESTAMP`, `TIMESTAMPTZ` | Ngày và giờ với ngữ nghĩa khác nhau |
| Có/không | `BOOLEAN` | TRUE, FALSE và NULL nếu cột cho phép |

Một trường có ý nghĩa là số tiền không nên lưu như chuỗi `VARCHAR` nếu cần tính toán, so sánh số học và ràng buộc không âm. Trước khi chọn `NUMERIC(12,2)` cũng cần hiểu phạm vi giá trị và đơn vị tiền của nghiệp vụ.

## 4. Định nghĩa ràng buộc ngay trong CREATE TABLE

Bảng lưu dữ liệu cần diễn đạt được ít nhất những quy tắc cơ bản.

### 4.1. PRIMARY KEY, UNIQUE, NOT NULL, DEFAULT và CHECK

~~~sql
CREATE TABLE ban_hang.san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku VARCHAR(40) NOT NULL,
    ten VARCHAR(150) NOT NULL,
    gia_niem_yet NUMERIC(12,2) NOT NULL,
    dang_ban BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT pk_san_pham PRIMARY KEY (id),
    CONSTRAINT uq_san_pham_sku UNIQUE (sku),
    CONSTRAINT ck_san_pham_gia CHECK (gia_niem_yet >= 0)
);
~~~

Các ràng buộc hoạt động như sau:

- **`PRIMARY KEY`**: nhận diện duy nhất mỗi dòng; một bảng chỉ có một ràng buộc PK nhưng khóa có thể gồm nhiều cột.
- **`UNIQUE`**: bảo đảm tính duy nhất của cột hoặc tổ hợp cột theo quy tắc DBMS. Cách xử lý nhiều giá trị NULL khác nhau giữa các hệ và tùy cấu hình.
- **`NOT NULL`**: yêu cầu cột có giá trị, không được NULL.
- **`DEFAULT`**: dùng giá trị khi cột không được chỉ định trong thao tác chèn hoặc dùng từ khóa DEFAULT; không tự chặn NULL tường minh.
- **`CHECK`**: yêu cầu biểu thức không trả kết quả FALSE; nếu giá trị NULL dẫn đến UNKNOWN, CHECK có thể vẫn cho phép, vì vậy cần `NOT NULL` khi bắt buộc.

Đặt tên như `pk_san_pham`, `uq_san_pham_sku`, `ck_san_pham_gia` giúp dễ nhận diện ràng buộc trong thông báo lỗi hoặc migration.

Thử dữ liệu không hợp lệ:

~~~sql
-- Bị từ chối vì vi phạm CHECK: giá không được âm.
INSERT INTO ban_hang.san_pham (sku, ten, gia_niem_yet)
VALUES ('LOI-01', 'Sản phẩm có giá âm', -1000);
~~~

Lệnh thất bại không làm mất bảng; bản ghi không được thêm. Nếu đang chạy trong transaction PostgreSQL chưa kết thúc, lỗi có thể khiến transaction chuyển sang trạng thái thất bại và cần rollback trước khi tiếp tục.

### 4.2. Khóa ngoại biểu diễn mối quan hệ

Một đơn hàng thuộc về một khách hàng. Ta tạo bảng `don_hang` sau bảng `khach_hang`:

~~~sql
CREATE TABLE ban_hang.don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL,
    ngay_dat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'NEW',
    CONSTRAINT fk_don_hang_khach_hang
        FOREIGN KEY (khach_hang_id)
        REFERENCES ban_hang.khach_hang(id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_don_hang_trang_thai
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED'))
);
~~~

`FOREIGN KEY` bảo đảm mỗi `khach_hang_id` phải trỏ tới một khóa phù hợp của bảng khách hàng. Vì có `NOT NULL`, mỗi đơn bắt buộc có khách hàng. `ON DELETE RESTRICT` ngăn xóa khách hàng khi còn đơn tham chiếu.

**Tên bảng ở vế `REFERENCES` nên ghi đầy đủ schema** trong script cần chắc chắn về phạm vi:

~~~sql
REFERENCES ban_hang.khach_hang(id)
~~~

Nếu chỉ viết `REFERENCES khach_hang(id)`, PostgreSQL sẽ dùng quy tắc tìm kiếm tên và môi trường tạo đối tượng, dễ gây nhầm khi có cùng tên bảng ở nhiều schema.

### 4.3. Khóa chính tổng hợp và bảng liên kết

Một đơn có nhiều sản phẩm, một sản phẩm có thể xuất hiện trong nhiều đơn. Ta dùng `chi_tiet_don_hang`:

~~~sql
CREATE TABLE ban_hang.chi_tiet_don_hang (
    don_hang_id BIGINT NOT NULL,
    san_pham_id BIGINT NOT NULL,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    CONSTRAINT pk_chi_tiet_don_hang
        PRIMARY KEY (don_hang_id, san_pham_id),
    CONSTRAINT fk_chi_tiet_don_hang_don
        FOREIGN KEY (don_hang_id)
        REFERENCES ban_hang.don_hang(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_chi_tiet_don_hang_san_pham
        FOREIGN KEY (san_pham_id)
        REFERENCES ban_hang.san_pham(id)
        ON DELETE RESTRICT
);
~~~

`PRIMARY KEY (don_hang_id, san_pham_id)` cho biết **cặp khóa phải duy nhất**. Mỗi cột riêng lẻ có thể lặp. Thiết kế này phù hợp khi mỗi sản phẩm được gộp thành đúng một dòng trong từng đơn. Nếu nghiệp vụ cho phép cùng sản phẩm xuất hiện nhiều dòng của một đơn, hãy thay cách định danh dòng cho phù hợp.

`don_gia` lưu giá tại thời điểm bán. Nếu chỉ tra `gia_niem_yet` của sản phẩm hiện tại, hệ thống có thể tính sai số tiền của những đơn cũ.

### 4.4. Sơ đồ quan hệ giữa các bảng

~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--o{ CHI_TIET_DON_HANG : chua
    SAN_PHAM ||--o{ CHI_TIET_DON_HANG : xuat_hien
    KHACH_HANG {
        bigint id PK
        varchar ho_ten
        varchar email UK
    }
    DON_HANG {
        bigint id PK
        bigint khach_hang_id FK
        timestamptz ngay_dat
    }
    SAN_PHAM {
        bigint id PK
        varchar sku UK
        numeric gia_niem_yet
    }
    CHI_TIET_DON_HANG {
        bigint don_hang_id PK,FK
        bigint san_pham_id PK,FK
        integer so_luong
        numeric don_gia
    }
~~~

Quan hệ một-nhiều được biểu diễn bằng khóa ngoại ở bảng **phía nhiều**. Quan hệ nhiều-nhiều giữa đơn và sản phẩm được tách thành hai quan hệ một-nhiều qua bảng chi tiết.

## 5. Tạo và đọc dữ liệu trên nhiều bảng cùng schema

Thêm sản phẩm:

~~~sql
INSERT INTO ban_hang.san_pham (sku, ten, gia_niem_yet)
VALUES
    ('SQL-01', 'Sách SQL', 120000),
    ('NOTE-02', 'Sổ ghi chú', 30000)
RETURNING id, sku, ten;
~~~

Tạo đơn của khách hàng An mà không đoán ID:

~~~sql
INSERT INTO ban_hang.don_hang (khach_hang_id)
SELECT id
FROM ban_hang.khach_hang
WHERE email = 'an@example.test'
RETURNING id, khach_hang_id, trang_thai;
~~~

Vì `email` có `UNIQUE` và An tồn tại trong dữ liệu mẫu, câu này thêm một đơn. Nếu không có khách hàng tương ứng, `INSERT ... SELECT` có thể thành công với 0 dòng được thêm. Hãy nhận **ID thực tế** từ `RETURNING` để dùng cho thao tác kế tiếp.

Ví dụ, giả sử lệnh vừa trả về `id = 1` cho đơn và sản phẩm SQL-01 cũng có `id = 1`, có thể thực hành:

~~~sql
-- Dùng đúng ID nhận từ RETURNING, không mặc định mọi database đều trả 1.
INSERT INTO ban_hang.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES (1, 1, 2, 120000);
~~~

Để loại bỏ giả định ID trong ví dụ, có thể dùng truy vấn dựa trên email và SKU trong database thử nghiệm chỉ có một đơn của An:

~~~sql
INSERT INTO ban_hang.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT dh.id, sp.id, 2, 120000
FROM ban_hang.don_hang AS dh
JOIN ban_hang.khach_hang AS kh
    ON kh.id = dh.khach_hang_id
CROSS JOIN ban_hang.san_pham AS sp
WHERE kh.email = 'an@example.test'
  AND sp.sku = 'SQL-01';
~~~

**Chỉ chọn một trong hai cách chèn chi tiết**; nếu chạy cả hai để tạo cùng cặp khóa, lệnh sau sẽ vi phạm PK tổng hợp. Ở hệ thống thật có nhiều đơn của cùng khách hàng, truy vấn thứ hai có thể chọn nhiều đơn, nên cần dùng ID đơn mới tạo chính xác hoặc khóa nghiệp vụ xác định duy nhất đơn cần thao tác.

Truy vấn kết hợp nhiều bảng:

~~~sql
SELECT
    dh.id AS ma_don,
    kh.ho_ten,
    sp.ten AS ten_san_pham,
    ct.so_luong,
    ct.don_gia,
    ct.so_luong * ct.don_gia AS thanh_tien
FROM ban_hang.don_hang AS dh
JOIN ban_hang.khach_hang AS kh
    ON kh.id = dh.khach_hang_id
JOIN ban_hang.chi_tiet_don_hang AS ct
    ON ct.don_hang_id = dh.id
JOIN ban_hang.san_pham AS sp
    ON sp.id = ct.san_pham_id
ORDER BY dh.id, sp.id;
~~~

Kết quả có một dòng Sách SQL với số lượng 2 và thành tiền 240000 trong dữ liệu mẫu. Các tên đầy đủ như `ban_hang.don_hang` chỉ rõ đối tượng thuộc schema nào; khóa ngoại và điều kiện `JOIN` chỉ ra dòng nào liên quan với dòng nào.

## 6. Thứ tự tạo đối tượng và phụ thuộc

Khi tạo bảng có FK, bảng được tham chiếu phải tồn tại và có khóa phù hợp trước. Một thứ tự hợp lý cho hệ bán hàng là:

~~~text
CREATE SCHEMA ban_hang
         ↓
CREATE TABLE ban_hang.khach_hang
CREATE TABLE ban_hang.san_pham
         ↓
CREATE TABLE ban_hang.don_hang
         ↓
CREATE TABLE ban_hang.chi_tiet_don_hang
         ↓
CREATE INDEX / CREATE VIEW
         ↓
INSERT dữ liệu / chạy truy vấn
~~~

Bạn có thể tạo nhiều bảng cha độc lập trước rồi các bảng con theo phụ thuộc. Nếu có quan hệ vòng hoặc khi nhập dữ liệu lịch sử, đôi lúc cần tạo các bảng trước, sau đó thêm khóa ngoại bằng `ALTER TABLE`.

Ví dụ cú pháp thêm FK sau khi tạo bảng:

~~~sql
-- Chỉ là ví dụ cú pháp; không chạy trên bảng don_hang của bài
-- vì FK tới khach_hang đã được định nghĩa ở CREATE TABLE.
ALTER TABLE ban_hang.don_hang
ADD CONSTRAINT fk_don_hang_khach_hang_moi
FOREIGN KEY (khach_hang_id)
REFERENCES ban_hang.khach_hang(id);
~~~

Thêm ràng buộc vào bảng đã có dữ liệu có thể thất bại nếu dữ liệu đang vi phạm. Không nên bỏ FK chỉ để cho một script tạo bảng chạy qua; thay vào đó, hiểu phụ thuộc và lập kế hoạch thứ tự DDL.

## 7. Tên đầy đủ và search_path trong PostgreSQL

### 7.1. Tên có schema và tên không có schema

Câu lệnh này chỉ rõ bảng:

~~~sql
SELECT * FROM ban_hang.khach_hang;
~~~

Còn câu sau chỉ nêu tên ngắn:

~~~sql
SELECT * FROM khach_hang;
~~~

Với tên ngắn, PostgreSQL sử dụng `search_path` để phân giải tên đối tượng theo những schema được cấu hình.

Kiểm tra phiên hiện tại:

~~~sql
SHOW search_path;
SELECT current_schema();
~~~

Thử thay đổi cho phiên kết nối:

~~~sql
SET search_path TO ban_hang, public;

SELECT * FROM khach_hang;

RESET search_path;
~~~

Khi `ban_hang` được tìm trước, tên `khach_hang` thường tương ứng `ban_hang.khach_hang` nếu đối tượng tồn tại và role có quyền cần thiết. Cần nhớ `search_path` có thể được thiết lập ở nhiều cấp (role, database, session), nên câu SQL không đủ schema có thể hoạt động khác nhau giữa các môi trường.

### 7.2. Đụng tên bảng giữa hai schema

Giả sử tồn tại:

~~~text
ban_hang.lich_su
nhan_su.lich_su
~~~

Câu `SELECT * FROM lich_su` phụ thuộc vào việc `search_path` tìm thấy bảng nào trước. Nếu cần chắc chắn đang đọc lịch sử bán hàng:

~~~sql
SELECT * FROM ban_hang.lich_su;
~~~

Đây chỉ là ví dụ tên; câu lệnh chỉ chạy nếu bảng `ban_hang.lich_su` thực sự đã được tạo.

**Khuyến nghị:** dùng tên đầy đủ `schema.table` trong DDL, script migration và các truy vấn cần rõ phạm vi. Tên ngắn hữu ích khi ứng dụng có chính sách `search_path` nhất quán và được quản lý chặt chẽ.

### 7.3. Lưu ý quyền và an toàn của search_path

Một schema nằm trên đường tìm kiếm có thể chứa đối tượng do role khác tạo. Nếu role không đáng tin có quyền `CREATE` ở schema được tìm trước, cách phân giải tên không đầy đủ có thể bị ảnh hưởng. PostgreSQL còn dùng quy tắc tìm tên cho một số loại đối tượng khác ngoài bảng.

Đối với các thao tác nhạy cảm, hàm có quyền cao hoặc migration quan trọng, cần xác định rõ `search_path` và quyền tạo đối tượng trong những schema xuất hiện trên đường tìm kiếm.

## 8. Tổ chức các đối tượng khác bên cạnh bảng

Schema có thể chứa bảng, view, index, sequence, function, procedure, type và những đối tượng khác theo quy tắc DBMS. Mỗi loại đối tượng đóng vai trò riêng.

### 8.1. VIEW: đặt tên cho truy vấn

~~~sql
CREATE VIEW ban_hang.v_don_hang AS
SELECT
    dh.id AS ma_don,
    kh.ho_ten,
    dh.ngay_dat,
    dh.trang_thai
FROM ban_hang.don_hang AS dh
JOIN ban_hang.khach_hang AS kh
    ON kh.id = dh.khach_hang_id;
~~~

Sau đó truy vấn:

~~~sql
SELECT *
FROM ban_hang.v_don_hang
ORDER BY ma_don;
~~~

View thông thường lưu định nghĩa truy vấn; nó **không tự tạo một bản sao dữ liệu cố định** như bảng được xây dựng bằng `CREATE TABLE AS SELECT`. Cách quyền truy cập và khả năng cập nhật qua view phụ thuộc DBMS, định nghĩa view và cấu hình liên quan.

### 8.2. INDEX: tăng tốc tra cứu phù hợp

~~~sql
CREATE INDEX idx_don_hang_khach_hang_id
ON ban_hang.don_hang (khach_hang_id);
~~~

Index có thể hữu ích cho thao tác tìm đơn theo khách hàng và JOIN trên `khach_hang_id`. PostgreSQL tạo index để thực thi `PRIMARY KEY`, `UNIQUE`, nhưng **không tự tạo index cho mọi cột khóa ngoại phía tham chiếu**.

Index cũng tăng chi phí ghi và lưu trữ. Khi dữ liệu lớn, nên đánh giá truy vấn thật bằng `EXPLAIN` hoặc `EXPLAIN ANALYZE` thay vì thêm index vô điều kiện.

### 8.3. Sequence và cột Identity

~~~sql
CREATE TABLE ban_hang.nhom_san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);
~~~

Trong PostgreSQL, identity liên quan đến một sequence dùng để cấp số. ID có thể có khoảng trống, không phải đồng hồ thời gian hay số thứ tự kinh doanh tuyệt đối.

### 8.4. COMMENT giúp mô tả metadata

~~~sql
COMMENT ON SCHEMA ban_hang
IS 'Dữ liệu phục vụ nghiệp vụ bán hàng';

COMMENT ON TABLE ban_hang.don_hang
IS 'Thông tin chung của một đơn hàng';

COMMENT ON COLUMN ban_hang.don_hang.trang_thai
IS 'NEW: mới; PAID: thanh toán; CANCELLED: hủy';
~~~

Comment giúp người đọc hoặc công cụ hiểu mục đích, nhưng không thay thế `CHECK` hoặc những kiểm tra nghiệp vụ thực sự.

## 9. Quyền schema và quyền đối tượng

Trong PostgreSQL, một role muốn đọc bảng trong schema thường cần ít nhất:

- Quyền sử dụng namespace, chẳng hạn `USAGE ON SCHEMA`.
- Quyền `SELECT` trên bảng được đọc (hoặc quyền quản trị tương đương).

Giả sử role `bao_cao_reader` đã tồn tại:

~~~sql
GRANT USAGE ON SCHEMA ban_hang
TO bao_cao_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA ban_hang
TO bao_cao_reader;
~~~

| Quyền | Ý nghĩa |
|---|---|
| `USAGE ON SCHEMA` | Cho phép tiếp cận/phân giải đối tượng trong schema khi có quyền đối tượng |
| `CREATE ON SCHEMA` | Cho phép tạo đối tượng trong schema theo những điều kiện của hệ quản trị |
| `SELECT ON TABLE` | Đọc dữ liệu bảng |
| `INSERT/UPDATE/DELETE ON TABLE` | Thêm, sửa, xóa dữ liệu tương ứng |
| Owner | Quản trị đối tượng do mình sở hữu theo quy tắc DBMS |

Chỉ `USAGE` không cho phép đọc hết bảng; chỉ quyền `SELECT` trên bảng cũng có thể chưa đủ nếu thiếu `USAGE` trên namespace. Điều đó giúp chia trách nhiệm giữa các nhóm người dùng.

**Lưu ý:** `GRANT SELECT ON ALL TABLES IN SCHEMA` áp dụng cho các bảng hiện có tại thời điểm cấp quyền. Muốn đặt quyền mặc định cho bảng được tạo trong tương lai bởi một role nhất định, PostgreSQL có `ALTER DEFAULT PRIVILEGES`:

~~~sql
-- Role app_owner và bao_cao_reader phải tồn tại; cần quyền phù hợp.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
IN SCHEMA ban_hang
GRANT SELECT ON TABLES TO bao_cao_reader;
~~~

Quyền mặc định gắn với role tạo đối tượng. Nếu migration tương lai dùng role khác để tạo bảng, cấu hình trên có thể không được áp dụng. Hãy quản lý vai trò tạo bảng và quyền mới như một phần của quy trình triển khai.

## 10. Kiểm tra danh sách bảng, cột và ràng buộc

Sau DDL, hãy biết cách nhìn metadata thay vì suy đoán từ tên.

### 10.1. Xem các bảng trong schema

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'ban_hang'
ORDER BY table_name;
~~~

Để chỉ xem bảng cơ sở, không gồm view:

~~~sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'ban_hang'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
~~~

Metadata có thể chỉ hiển thị đối tượng mà role hiện tại có quyền nhìn thấy.

### 10.2. Xem định nghĩa cột

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'ban_hang'
  AND table_name = 'don_hang'
ORDER BY ordinal_position;
~~~

Nhờ đó biết cột nào có kiểu gì, cho phép NULL hay không, và các giá trị mặc định mà metadata phản ánh. Muốn xác nhận khóa ngoại phải xem ràng buộc thực tế qua `information_schema.table_constraints`, `key_column_usage` hoặc catalog PostgreSQL; tên cột `khach_hang_id` tự nó không chứng minh có FK.

### 10.3. Lệnh riêng của psql

~~~text
\dn
\dt ban_hang.*
\d ban_hang.don_hang
\dv ban_hang.*
~~~

Các lệnh này lần lượt giúp xem schema, bảng, mô tả chi tiết bảng và view. Chúng chỉ dùng trực tiếp trong `psql` hoặc môi trường có hỗ trợ lệnh meta tương ứng; không phải SQL chuẩn.

## 11. Những dạng CREATE TABLE thường gặp

### 11.1. CREATE TABLE thông thường

~~~sql
CREATE TABLE ban_hang.phan_loai (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);
~~~

Bảng tạo ra rỗng, với các ràng buộc được khai báo rõ. Đây là cách cơ bản để tạo bảng nghiệp vụ.

### 11.2. CREATE TABLE AS SELECT

~~~sql
CREATE TABLE ban_hang.bao_cao_san_pham AS
SELECT sku, ten, gia_niem_yet
FROM ban_hang.san_pham
WHERE dang_ban = TRUE;
~~~

Câu này tạo một **bảng mới chứa dữ liệu từ kết quả SELECT tại thời điểm tạo**. Không nên nhầm với `VIEW`:

- Bảng mới không tự cập nhật theo bảng nguồn.
- PK, FK, UNIQUE và các index từ bảng nguồn **không tự được sao chép**.
- Cột và kiểu dữ liệu phụ thuộc vào các biểu thức của SELECT.

Nếu chỉ cần cấu trúc dạng kết quả SELECT mà không cần dòng dữ liệu:

~~~sql
CREATE TABLE ban_hang.bao_cao_san_pham_rong AS
SELECT sku, ten, gia_niem_yet
FROM ban_hang.san_pham
WHERE FALSE;
~~~

### 11.3. CREATE TABLE ... LIKE

~~~sql
CREATE TABLE ban_hang.san_pham_mau (
    LIKE ban_hang.san_pham
        INCLUDING DEFAULTS
        INCLUDING CONSTRAINTS
        INCLUDING IDENTITY
);
~~~

`LIKE` có thể sao chép nhiều thuộc tính cấu trúc theo tùy chọn `INCLUDING`. Không nên giả định mọi constraint, index, identity, comment và hành vi khác đều tự sao chép mặc định. Phải xem chính xác danh sách tùy chọn và định nghĩa tạo ra.

### 11.4. Bảng tạm TEMP TABLE

~~~sql
CREATE TEMP TABLE tam_ket_qua (
    id INTEGER,
    gia_tri NUMERIC(12,2)
);
~~~

Trong PostgreSQL, bảng tạm tồn tại theo phạm vi phiên với các lựa chọn `ON COMMIT` ảnh hưởng tới dữ liệu/đối tượng khi kết thúc transaction. Bảng tạm dùng schema tạm do hệ thống quản lý, không phải tự thuộc `ban_hang` chỉ vì muốn nhóm theo nghiệp vụ.

Nếu công cụ SQL mở một kết nối khác, bảng tạm của phiên trước có thể không nhìn thấy.

### 11.5. IF NOT EXISTS với bảng

~~~sql
CREATE TABLE IF NOT EXISTS ban_hang.cau_hinh (
    ma VARCHAR(50) PRIMARY KEY,
    gia_tri TEXT
);
~~~

Nếu đối tượng cùng tên đã có, PostgreSQL có thể bỏ qua tạo mới. Nhưng `IF NOT EXISTS` **không kiểm tra bảng cũ có đúng cấu trúc vừa viết**. Một migration đúng phải nêu các thay đổi cột/ràng buộc cần thực hiện.

## 12. Thay đổi bảng sau khi tạo: ALTER TABLE

Hệ thống phát triển theo thời gian, nên cấu trúc bảng cũng có thể phải thay đổi.

### 12.1. Thêm cột

~~~sql
ALTER TABLE ban_hang.khach_hang
ADD COLUMN so_dien_thoai VARCHAR(20);
~~~

Cột mới mặc định cho phép NULL, vì không có `NOT NULL`. Các dòng đã tồn tại chưa có số điện thoại thì phù hợp với điều kiện này.

Nếu cần chuyển sang bắt buộc, hãy có kế hoạch cập nhật dữ liệu cũ trước khi thêm `NOT NULL`, tránh migration thất bại do các dòng hiện tại đang NULL.

### 12.2. Thêm CHECK sau

~~~sql
ALTER TABLE ban_hang.khach_hang
ADD CONSTRAINT ck_khach_hang_email_khong_rong
CHECK (char_length(trim(email)) > 0);
~~~

Nếu dữ liệu cũ vi phạm quy tắc, PostgreSQL có thể từ chối thêm ràng buộc. Điều kiện trên chỉ bảo vệ việc email có ký tự khác khoảng trắng; nó không xác nhận mọi quy tắc hợp lệ của địa chỉ email.

### 12.3. Đổi tên cột hoặc schema

~~~sql
-- Ví dụ thay đổi cấu trúc: không chạy nếu muốn tiếp tục truy vấn dùng ho_ten.
ALTER TABLE ban_hang.khach_hang
RENAME COLUMN ho_ten TO ten_day_du;
~~~

Đổi tên cột làm các câu SQL bên ngoài database đang tham chiếu `ho_ten` cần được cập nhật. Với schema:

~~~sql
-- Ví dụ cú pháp; không chạy trong bộ dữ liệu bài học.
ALTER SCHEMA ban_hang RENAME TO kinh_doanh;
~~~

Đổi tên schema có thể ảnh hưởng tới SQL viết cứng tiền tố `ban_hang.` trong ứng dụng, migration hoặc báo cáo. Khi thay đổi cấu trúc trong sản phẩm thực tế, cần quản lý phiên bản và tính tương thích.

## 13. Giao dịch và DDL

Trong PostgreSQL, nhiều thao tác DDL có thể nằm trong transaction và được rollback:

~~~sql
BEGIN;

CREATE SCHEMA thu_nghiem;
CREATE TABLE thu_nghiem.mau (
    id INTEGER PRIMARY KEY,
    ghi_chu TEXT
);

ROLLBACK;
~~~

Sau khi `ROLLBACK`, schema và bảng vừa tạo trong transaction không còn được giữ. Điều này hữu ích khi muốn thay đổi nhiều đối tượng cùng một lần và cần hoàn tác nếu gặp vấn đề.

Tuy nhiên, **không phải mọi DBMS đều rollback DDL giống PostgreSQL**. Một số lệnh DDL trên MySQL hoặc Oracle có thể tự commit hoặc có ngữ nghĩa transaction khác. Không nên chuyển nguyên giả định này sang hệ khác.

### 13.1. Một lệnh lỗi không đồng nghĩa mọi lệnh trước đều thất bại

Nếu client bật autocommit và chạy:

~~~sql
CREATE TABLE ban_hang.kiem_tra (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0)
);

INSERT INTO ban_hang.kiem_tra (id, so_luong)
VALUES (1, -1);
~~~

Lệnh đầu có thể đã tạo bảng; lệnh hai bị từ chối vì `CHECK`. Khi đọc trạng thái thực tế, phải xét từng statement và transaction đang mở. Nếu hai lệnh trong cùng transaction và sau đó rollback, bảng mới cũng có thể bị hoàn tác.

## 14. Xóa đối tượng: DROP TABLE và DROP SCHEMA

### 14.1. Xóa bảng

~~~sql
DROP TABLE ban_hang.kiem_tra;
~~~

`DROP TABLE` xóa bảng và dữ liệu nếu thành công. Nếu có đối tượng đang phụ thuộc, PostgreSQL có thể chặn thao tác hoặc yêu cầu lựa chọn rõ ràng.

### 14.2. Xóa schema đang có đối tượng

~~~sql
DROP SCHEMA ban_hang;
~~~

PostgreSQL mặc định xử lý theo hướng hạn chế (tương đương `RESTRICT`). Nếu trong schema vẫn có bảng hoặc view, lệnh sẽ báo lỗi.

~~~sql
DROP SCHEMA ban_hang RESTRICT;
~~~

Câu này nhấn mạnh chỉ xóa khi không còn đối tượng phụ thuộc cần ngăn thao tác.

### 14.3. Hiểu CASCADE trước khi dùng

~~~sql
-- Cú pháp minh họa: không chạy trên schema có dữ liệu cần giữ.
DROP SCHEMA ban_hang CASCADE;
~~~

`CASCADE` cho phép xóa các đối tượng chứa trong schema và các đối tượng phụ thuộc theo quy tắc của PostgreSQL, kể cả một số phụ thuộc ở ngoài schema đó. Đây là thao tác có phạm vi rộng; chỉ sử dụng khi đã kiểm tra phụ thuộc và có kế hoạch giữ dữ liệu phù hợp.

### 14.4. Thứ tự tháo dỡ bảng

Trong một cơ sở dữ liệu thử nghiệm chỉ chứa đối tượng mẫu của bài này, nếu không có phụ thuộc ngoài, ta có thể dọn theo thứ tự bảng con → bảng cha:

~~~sql
DROP VIEW IF EXISTS ban_hang.v_don_hang;
DROP TABLE IF EXISTS ban_hang.chi_tiet_don_hang;
DROP TABLE IF EXISTS ban_hang.don_hang;
DROP TABLE IF EXISTS ban_hang.san_pham_mau;
DROP TABLE IF EXISTS ban_hang.bao_cao_san_pham_rong;
DROP TABLE IF EXISTS ban_hang.bao_cao_san_pham;
DROP TABLE IF EXISTS ban_hang.nhom_san_pham;
DROP TABLE IF EXISTS ban_hang.phan_loai;
DROP TABLE IF EXISTS ban_hang.cau_hinh;
DROP TABLE IF EXISTS ban_hang.san_pham;
DROP TABLE IF EXISTS ban_hang.khach_hang;
DROP SCHEMA IF EXISTS ban_hang;
~~~

**Chỉ chạy trên môi trường thực hành mới và do bạn kiểm soát.** Nếu schema có bảng khác hoặc phụ thuộc, bước cuối có thể thất bại vì schema chưa rỗng; điều đó an toàn hơn việc dùng `CASCADE` không kiểm soát.

## 15. Đặt tên và phân nhóm đối tượng

Một quy ước nhất quán làm cấu trúc dễ đọc hơn:

| Đối tượng | Tên minh họa |
|---|---|
| Schema | `ban_hang`, `nhan_su`, `bao_cao` |
| Table | `khach_hang`, `don_hang`, `san_pham` |
| Bảng liên kết | `chi_tiet_don_hang` |
| PK | `id` hoặc khóa tổng hợp rõ nghĩa |
| FK | `khach_hang_id`, `don_hang_id` |
| Unique constraint | `uq_san_pham_sku` |
| Foreign key constraint | `fk_don_hang_khach_hang` |
| Check constraint | `ck_san_pham_gia` |
| Index | `idx_don_hang_khach_hang_id` |
| View | `v_don_hang` |

Đây là quy ước có ích, **không phải chuẩn SQL bắt buộc**. Một dự án có thể dùng cách đặt tên khác, nhưng nên giữ sự nhất quán và dễ hiểu.

### 15.1. Tên không trích dẫn và tên có dấu nháy kép

PostgreSQL chuyển định danh không quote về chữ thường. Ví dụ:

~~~sql
CREATE TABLE ban_hang.ViDu (
    id INTEGER
);
~~~

tạo bảng có tên thực tế là `ban_hang.vidu`. Ngược lại:

~~~sql
CREATE TABLE ban_hang."ViDu" (
    id INTEGER
);
~~~

tạo tên phân biệt chữ hoa/chữ thường, khi tham chiếu thường phải viết chính xác `"ViDu"`.

Vì vậy, cách dễ duy trì là **chữ thường, snake_case, không dấu cách, tránh từ khóa SQL**. Dấu nháy kép cho định danh khác dấu nháy đơn cho giá trị chuỗi:

~~~sql
-- Tên cột
SELECT "email" FROM ban_hang.khach_hang;

-- Chuỗi văn bản
SELECT * FROM ban_hang.khach_hang
WHERE email = 'an@example.test';
~~~

### 15.2. Khi nào nên tách schema?

Có thể chia theo:

~~~text
ung_dung
├── ban_hang
│   ├── khach_hang
│   ├── don_hang
│   └── san_pham
├── nhan_su
│   ├── nhan_vien
│   └── phong_ban
└── bao_cao
    └── các view phục vụ người đọc
~~~

Mức tách hợp lý phụ thuộc miền nghiệp vụ, owner, quyền, nhu cầu triển khai và cách dùng database. Tạo riêng một schema cho từng bảng có thể làm quản lý và phân quyền khó hơn nếu không có lý do rõ ràng.

## 16. Sự khác biệt giữa các hệ quản trị SQL

### 16.1. So sánh nhanh

| Hệ quản trị | Ý nghĩa của CREATE SCHEMA | Tên bảng đủ phạm vi thông dụng |
|---|---|---|
| **PostgreSQL** | Tạo namespace bên trong database hiện tại | `schema.table` |
| **SQL Server** | Tạo namespace đối tượng trong database | `schema.table` hoặc `database.schema.table` |
| **MySQL/MariaDB** | `CREATE SCHEMA` là từ đồng nghĩa của `CREATE DATABASE` | `database.table` |
| **Oracle** | Schema gắn với user sở hữu đối tượng, không tạo namespace tùy ý như PostgreSQL | `schema.table` |
| **SQLite** | Không có `CREATE SCHEMA` theo mô hình PostgreSQL; có `main`, `temp` và attached database | `database_alias.table` |

### 16.2. PostgreSQL

~~~sql
CREATE SCHEMA ban_hang;

CREATE TABLE ban_hang.khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);
~~~

Đây là namespace bên trong database đang kết nối. Các schema khác nhau trong cùng database có thể sử dụng tên bảng giống nhau.

### 16.3. SQL Server

~~~sql
CREATE SCHEMA ban_hang;
GO

CREATE TABLE ban_hang.khach_hang (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ten NVARCHAR(100) NOT NULL
);
GO
~~~

Trong SQL Server, `dbo` là schema thường gặp. `GO` là **dấu phân tách batch của công cụ** như SSMS/sqlcmd, không phải câu T-SQL được gửi trực tiếp tới database engine. Các thư viện kết nối không hiểu `GO` thường cần gửi từng batch riêng. SQL Server hỗ trợ tên nhiều phần như `TenDatabase.ban_hang.khach_hang` theo quy tắc phân giải và quyền riêng.

### 16.4. MySQL và MariaDB

~~~sql
-- CREATE SCHEMA đồng nghĩa CREATE DATABASE trong MySQL.
CREATE SCHEMA ban_hang;

CREATE TABLE ban_hang.khach_hang (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);
~~~

Phần `ban_hang` ở đây chính là **database**, không phải một nhóm con của database như PostgreSQL. Lệnh tạo ID tự tăng dùng `AUTO_INCREMENT` chứ không phải `GENERATED ALWAYS AS IDENTITY` theo cú pháp PostgreSQL.

### 16.5. Oracle

Trong Oracle, schema gắn với **user**. Một user sở hữu các bảng thuộc schema của mình. Ví dụ, khi kết nối bằng user phù hợp:

~~~sql
CREATE TABLE khach_hang (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR2(100) NOT NULL
);
~~~

User khác có quyền truy cập có thể gọi bảng bằng `TEN_SCHEMA.KHACH_HANG`. Việc tạo user/schema là phần quản trị riêng. Oracle có cú pháp `CREATE SCHEMA AUTHORIZATION ...` cho mục đích thực hiện một nhóm câu tạo đối tượng trong schema thuộc user hiện có; không nên hiểu nó tạo namespace bất kỳ giống PostgreSQL.

Oracle còn khác về kiểu dữ liệu, cách quản lý quyền và ngữ nghĩa commit của DDL.

### 16.6. SQLite

SQLite không có `CREATE SCHEMA` với nghĩa namespace như PostgreSQL. Trong một file database:

~~~sql
CREATE TABLE khach_hang (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL
);
~~~

SQLite có `main`, `temp` và có thể `ATTACH` thêm database file:

~~~sql
ATTACH DATABASE 'ban_hang.db' AS ban_hang;

CREATE TABLE ban_hang.khach_hang (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL
);
~~~

`ban_hang` ở đây là **alias của database file được attach**. Không phải vì xuất hiện cú pháp `ban_hang.khach_hang` mà nó có cùng ngữ nghĩa schema với PostgreSQL.

### 16.7. Kiểm tra gì khi chuyển DBMS?

Khi port DDL, cần xem:

1. `CREATE SCHEMA` đang tạo namespace hay database?
2. Kiểu cột ID tự sinh sử dụng cú pháp nào?
3. Tên bảng đầy đủ gồm những thành phần nào?
4. Hỗ trợ `CHECK`, `UNIQUE`, `FOREIGN KEY` và hành vi NULL ra sao?
5. DDL có chạy trong transaction/rollback được không?
6. Cách quote tên, phân biệt hoa/thường, schema mặc định và quyền truy cập thế nào?
7. `IF NOT EXISTS`, `CREATE TABLE AS`, `LIKE` có được hỗ trợ giống nhau không?

Không nên sao chép nguyên một script PostgreSQL sang SQL Server hoặc MySQL mà chỉ thay vài tên kiểu dữ liệu.

## 17. Lỗi thường gặp khi làm việc với schema và bảng

| Tình huống | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `schema "ban_hang" does not exist` | Chưa tạo schema hoặc gõ sai tên | Kiểm tra schema và chạy `CREATE SCHEMA` khi đúng mục tiêu |
| `relation already exists` | Bảng/đối tượng cùng tên đã có | Kiểm tra định nghĩa hiện tại, dùng migration phù hợp |
| `permission denied for schema` | Role không có quyền cần thiết trên namespace | Kiểm tra `USAGE/CREATE` và owner |
| `permission denied for database` | Thiếu quyền cấp database | Xác định thao tác và quyền tương ứng |
| `relation does not exist` khi SELECT tên ngắn | Bảng ở schema khác hoặc `search_path` chưa phù hợp | Dùng tên `schema.table` và xem `SHOW search_path` |
| FK không tạo được | Bảng/khóa được tham chiếu chưa tồn tại hoặc không phù hợp | Tạo bảng cha và ràng buộc khóa trước |
| INSERT vi phạm `NOT NULL` | Truyền NULL hoặc bỏ giá trị bắt buộc không có default | Bổ sung giá trị hợp lệ |
| INSERT vi phạm `CHECK` | Giá trị nằm ngoài miền hợp lệ | Sửa dữ liệu nguồn, kiểm tra nghiệp vụ |
| `DROP SCHEMA` không thành công | Schema còn đối tượng/phụ thuộc | Kiểm tra danh sách đối tượng; dọn có chủ đích |
| Tên `"ViDu"` không tìm thấy bằng `vidu` | Định danh quoted phân biệt chữ hoa/thường | Dùng tên chuẩn hoặc quote chính xác |

Một lỗi dễ mắc là “cứ lỗi thì DROP bảng và tạo lại”. Cách đó có thể làm mất dữ liệu và phá phụ thuộc. Với bảng đang được sử dụng, nên lập migration rõ ràng, xác minh dữ liệu hiện tại và dùng `ALTER TABLE` khi cần thay đổi.

## 18. Thực hành độc lập: tạo schema thư viện

Các bài dưới đây chạy trong **database thử nghiệm PostgreSQL chưa có schema `thu_vien_demo`**. Tránh làm trên database sản xuất hoặc schema của người khác.

### Bài 1. Tạo schema và hai bảng

Yêu cầu:

- Tạo schema `thu_vien_demo`.
- Bảng `tac_gia` có ID tự tăng, tên bắt buộc, email duy nhất.
- Bảng `sach` có ID tự tăng, tên bắt buộc, năm xuất bản tùy chọn và khóa ngoại đến tác giả.
- Một tác giả có thể viết nhiều sách; một sách phải tham chiếu một tác giả.

~~~sql
CREATE SCHEMA thu_vien_demo;

CREATE TABLE thu_vien_demo.tac_gia (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);

CREATE TABLE thu_vien_demo.sach (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tac_gia_id BIGINT NOT NULL,
    ten VARCHAR(150) NOT NULL,
    nam_xuat_ban INTEGER,
    CONSTRAINT ck_sach_nam
        CHECK (nam_xuat_ban BETWEEN 1400 AND 2100),
    CONSTRAINT fk_sach_tac_gia
        FOREIGN KEY (tac_gia_id)
        REFERENCES thu_vien_demo.tac_gia(id)
        ON DELETE RESTRICT
);
~~~

`email` và `nam_xuat_ban` có thể NULL theo thiết kế này. Khoảng năm 1400–2100 là **giả định riêng của bài tập**, không phải quy tắc áp dụng cho mọi thư viện.

### Bài 2. Thêm dữ liệu bằng khóa được tìm từ bảng cha

~~~sql
INSERT INTO thu_vien_demo.tac_gia (ho_ten, email)
VALUES ('Tác giả A', 'tacgiaa@example.test')
RETURNING id;

INSERT INTO thu_vien_demo.sach (tac_gia_id, ten, nam_xuat_ban)
SELECT id, 'Nhập môn SQL', 2025
FROM thu_vien_demo.tac_gia
WHERE email = 'tacgiaa@example.test'
RETURNING id, tac_gia_id, ten;
~~~

Không cần dự đoán ID tác giả. Vì có `UNIQUE` trên email và đã thêm tác giả, lệnh thêm một sách. Nếu không có tác giả phù hợp, `INSERT ... SELECT` thêm 0 dòng.

### Bài 3. JOIN hai bảng bằng tên đầy đủ

~~~sql
SELECT
    s.ten AS ten_sach,
    tg.ho_ten AS tac_gia,
    s.nam_xuat_ban
FROM thu_vien_demo.sach AS s
JOIN thu_vien_demo.tac_gia AS tg
    ON tg.id = s.tac_gia_id
ORDER BY s.id;
~~~

Kết quả mong đợi:

| ten_sach | tac_gia | nam_xuat_ban |
|---|---|---:|
| Nhập môn SQL | Tác giả A | 2025 |

### Bài 4. Thử một khóa ngoại không hợp lệ

~~~sql
-- Giả định không tồn tại tác giả có id 999999.
INSERT INTO thu_vien_demo.sach (tac_gia_id, ten, nam_xuat_ban)
VALUES (999999, 'Sách không có tác giả', 2026);
~~~

Lệnh bị từ chối vì tham chiếu tới tác giả chưa tồn tại. Hãy giải thích vì sao `FOREIGN KEY` ngăn dữ liệu “mồ côi”, thay vì bỏ FK để lệnh chạy được.

### Bài 5. Xem metadata

~~~sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'thu_vien_demo'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
~~~

Đầu ra mong đợi gồm `sach` và `tac_gia`. Với `psql`, thử:

~~~text
\d thu_vien_demo.sach
~~~

và quan sát ràng buộc `fk_sach_tac_gia`.

### Bài 6. Dọn schema thực hành đúng thứ tự

Chỉ trên môi trường thử nghiệm tự quản:

~~~sql
DROP TABLE thu_vien_demo.sach;
DROP TABLE thu_vien_demo.tac_gia;
DROP SCHEMA thu_vien_demo;
~~~

Bảng con `sach` được xóa trước để không còn FK tham chiếu bảng cha. Nếu còn đối tượng khác trong schema, lệnh cuối không thể xóa schema rỗng theo giả định của bài tập.

## 19. Ghi nhớ

Khi tạo một phần mới của hệ thống, hãy đặt các câu hỏi theo thứ tự:

1. **Đang kết nối database nào?** Đây có phải môi trường được phép tạo/sửa dữ liệu?
2. **Đối tượng sẽ thuộc schema nào?** Schema đó có sẵn, đúng owner và quyền không?
3. **Mỗi bảng biểu diễn thực thể gì?** Cột, kiểu dữ liệu, giá trị mặc định có hợp lý không?
4. **Khóa chính của bảng là gì?** Có các quy tắc `UNIQUE` khác cần bảo vệ không?
5. **Quan hệ giữa các bảng thế nào?** Bảng nào là bảng cha, bảng con, bảng liên kết?
6. **Các ràng buộc cần đặt ở đâu?** `NOT NULL`, `CHECK`, `FOREIGN KEY`, chính sách xóa?
7. **Tên trong truy vấn có đủ schema không?** Có phụ thuộc vào `search_path` không?
8. **Ai được đọc, tạo hoặc sửa bảng?** Quyền trên schema và trên đối tượng đã phù hợp chưa?
9. **Cấu trúc sẽ được nâng cấp và dọn dẹp ra sao?** Có migration, thứ tự phụ thuộc và phương án giữ dữ liệu không?

`CREATE SCHEMA` giúp tổ chức namespace, còn `CREATE TABLE` giúp khai báo cấu trúc dữ liệu. Khi dùng chúng cùng tên đầy đủ, kiểu dữ liệu phù hợp, khóa, ràng buộc và quyền rõ ràng, bạn xây dựng được nền tảng SQL dễ đọc, dễ mở rộng và có kiểm soát.
