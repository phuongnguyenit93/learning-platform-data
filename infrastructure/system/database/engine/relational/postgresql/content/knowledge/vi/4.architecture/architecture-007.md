# System catalog, OID và quan hệ giữa các đối tượng trong PostgreSQL

Trong PostgreSQL, một bảng không chỉ gồm những hàng dữ liệu mà ứng dụng đọc và ghi. Hệ quản trị còn phải biết bảng tên gì, thuộc schema nào, có những cột và kiểu dữ liệu nào, khóa chính ở đâu, chỉ mục nào được sử dụng, view nào phụ thuộc vào bảng và role nào có quyền thao tác. Những thông tin đó được gọi là **metadata** — dữ liệu mô tả cấu trúc và hành vi của chính cơ sở dữ liệu.

PostgreSQL lưu phần lớn metadata trong **system catalog**, chủ yếu ở schema `pg_catalog`. Để nối các thông tin nằm ở nhiều catalog, PostgreSQL sử dụng những định danh nội bộ, tiêu biểu là **OID (Object Identifier)**. Hiểu system catalog và OID giúp người học đi từ việc chỉ biết tạo bảng bằng SQL sang hiểu **PostgreSQL quản lý quan hệ giữa các đối tượng như thế nào**.

Bài học này tập trung vào bốn câu hỏi:

1. **System catalog là gì?** Nó khác bảng nghiệp vụ, `information_schema` và những view thống kê ra sao?
2. **OID có nghĩa gì?** Khi nào dùng OID, `regclass`, `regtype`, và vì sao không nên lưu OID như một khóa nghiệp vụ?
3. **Các catalog liên kết thế nào?** Từ schema đến bảng, cột, kiểu dữ liệu, index, constraint, view, function và dependency.
4. **Có thể kiểm tra bằng SQL ra sao?** Tạo mô hình thực hành rồi truy vấn catalog để tự quan sát cấu trúc PostgreSQL.

> Những truy vấn trong bài đọc metadata và phù hợp để học trên PostgreSQL hiện đại. Một số chi tiết catalog có thể thay đổi theo phiên bản. **Không được sửa trực tiếp các hàng trong `pg_catalog`**; hãy dùng các câu lệnh DDL được PostgreSQL hỗ trợ như `CREATE`, `ALTER` và `DROP`.

## 1. PostgreSQL lưu những loại thông tin nào?

Có thể hình dung PostgreSQL quản lý ít nhất ba nhóm thông tin:

| Nhóm | Nội dung | Ví dụ |
|---|---|---|
| **Dữ liệu nghiệp vụ** | Hàng mà ứng dụng tạo, đọc và cập nhật | Khách hàng, đơn hàng, sản phẩm |
| **Metadata cấu trúc** | Mô tả bảng, cột, khóa, index, schema, function, type | `pg_class`, `pg_attribute`, `pg_constraint` |
| **Trạng thái và thống kê vận hành** | Kết nối, số lần quét, số hàng ước tính, truy vấn đang chạy | `pg_stat_activity`, `pg_stat_user_tables` |

Ví dụ ứng dụng chạy:

~~~sql
CREATE TABLE demo_item (
    id BIGINT PRIMARY KEY,
    ten TEXT NOT NULL
);
~~~

Lệnh này không chỉ tạo một nơi lưu dữ liệu. PostgreSQL còn tạo hoặc cập nhật metadata tương ứng với:

- Quan hệ `demo_item` và schema chứa nó.
- Hai cột `id` và `ten`, thứ tự cột và kiểu dữ liệu.
- Ràng buộc `PRIMARY KEY` và `NOT NULL`.
- Chỉ mục duy nhất phục vụ khóa chính.
- Kiểu hàng (composite row type) liên quan tới bảng.
- Các dependency để ngăn việc xóa hoặc thay đổi đối tượng làm hỏng cấu trúc phụ thuộc.

Những metadata đó nằm trong nhiều catalog, được liên kết bằng định danh và cột tham chiếu nội bộ. Khi thực hiện `\d demo_item` trong `psql`, client hỏi PostgreSQL về metadata để hiển thị; `psql` không tự ghi nhớ cấu trúc bảng.

## 2. System catalog là gì?

**System catalog** là tập các quan hệ nội bộ mà PostgreSQL sử dụng để mô tả và quản lý đối tượng database. Phần lớn nằm trong schema `pg_catalog` và có thể được đọc bằng SQL với quyền phù hợp.

Một số catalog quan trọng:

- `pg_namespace`: schema.
- `pg_class`: table, index, view, sequence và nhiều loại relation.
- `pg_attribute`: cột/thuộc tính của relation.
- `pg_type`: kiểu dữ liệu.
- `pg_constraint`: constraint, gồm khóa chính, khóa ngoại, unique và check.
- `pg_index`: metadata đặc trưng của index.
- `pg_attrdef`: biểu thức default của cột và một số giá trị liên quan.
- `pg_proc`: function và procedure.
- `pg_rewrite`: rewrite rules, bao gồm rule phục vụ view.
- `pg_depend`: quan hệ phụ thuộc giữa các đối tượng.
- `pg_description`: comment trên đối tượng.
- `pg_database`: database trong cluster.
- `pg_roles`: view thể hiện thông tin role phù hợp để tra cứu.

Có thể xem một catalog như bảng thông thường:

~~~sql
SELECT oid, nspname
FROM pg_catalog.pg_namespace
ORDER BY nspname;
~~~

Nhưng **đọc được bằng SQL không có nghĩa được cập nhật như bảng ứng dụng**. PostgreSQL dựa vào metadata nội bộ để duy trì tính toàn vẹn. Nếu cố sửa thủ công catalog mà không thực hiện đầy đủ những bước quản lý đối tượng tương ứng, có thể làm database hỏng hoặc hoạt động không xác định.

### 2.1. Vì sao catalog lại là quan hệ?

PostgreSQL quản lý metadata dưới dạng quan hệ vì đây là mô hình có thể truy vấn, nối và quản lý trong hệ thống giao dịch của chính PostgreSQL. Nhiều thay đổi schema bằng DDL được thực hiện theo quy tắc transaction.

Ví dụ:

~~~sql
BEGIN;

CREATE TABLE public.temp_catalog_demo (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
~~~

Sau `ROLLBACK`, bảng được tạo trong transaction này không còn tồn tại, nếu trước đó chưa có bảng cùng tên. Tương ứng, những metadata được tạo cho bảng cũng không trở thành một thay đổi đã commit.

**Điểm cần phân biệt:** catalog được PostgreSQL quản lý có tính giao dịch, nhưng không phải mọi lệnh quản trị đều được phép chạy trong transaction; chẳng hạn `CREATE DATABASE` không chạy bên trong một transaction block theo cách thông thường.

### 2.2. pg_catalog không giống information_schema

`pg_catalog` là bộ catalog và hàm đặc thù của PostgreSQL, thường cung cấp thông tin rất chi tiết về cách PostgreSQL lưu và quản lý đối tượng.

`information_schema` là tập view theo chuẩn SQL giúp tra cứu metadata ở mức khái quát, thường thuận tiện hơn cho ứng dụng cần giảm phụ thuộc vào catalog nội bộ PostgreSQL.

Ví dụ:

~~~sql
-- PostgreSQL-specific:
SELECT c.relname, c.relkind
FROM pg_catalog.pg_class AS c
WHERE c.relname = 'demo_item';

-- Information Schema:
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_name = 'demo_item';
~~~

Hai nguồn phục vụ mục đích khác nhau; kết quả cũng có thể khác do cách phân loại đối tượng và **quyền của người đang kết nối**.

## 3. OID là gì?

**OID (Object Identifier)** là loại định danh nội bộ được PostgreSQL sử dụng cho nhiều đối tượng và bản ghi catalog. Kiểu `oid` là kiểu số nguyên không dấu **4 byte** trong PostgreSQL.

Khi tạo một bảng, PostgreSQL có thể gán OID cho bản ghi mô tả bảng trong `pg_class`. Khi tạo schema, schema có OID trong `pg_namespace`. Khi tạo type, type có OID trong `pg_type`.

Một ví dụ về cách catalog liên kết:

~~~text
pg_namespace
  oid = 18420, nspname = 'catalog_lab'
             ^
             |
             | pg_class.relnamespace
             |
pg_class
  oid = 18451, relname = 'nhan_vien'
             ^
             |
             | pg_attribute.attrelid
             |
pg_attribute
  attrelid = 18451, attname = 'ho_ten'
~~~

**Các con số trên chỉ là minh họa.** OID thật được hệ thống cấp trong môi trường cụ thể; không dự đoán hoặc hardcode OID 18451 khi viết ứng dụng.

### 3.1. Những điều nên hiểu về OID

- OID hỗ trợ **nhận diện một đối tượng trong ngữ cảnh catalog/cluster hiện tại**.
- OID có thể xuất hiện trong cột `oid` hoặc trong những cột tham chiếu như `relnamespace`, `attrelid`, `atttypid`.
- OID giúp hệ thống nối metadata nhanh và chính xác, không cần chỉ dựa vào tên đối tượng.
- OID là định danh nội bộ, **không phải mã nghiệp vụ** như mã khách hàng hay mã đơn hàng.
- Không nên giả định một giá trị OID có ý nghĩa hoặc duy nhất trên mọi PostgreSQL server, mọi database và mọi catalog.
- OID có độ rộng hữu hạn; hệ thống có thể cấp lại giá trị theo thời gian và các quy tắc nội bộ.
- Sau `pg_dump`/restore hoặc khi tạo lại đối tượng, OID **có thể khác** dù tên và cấu trúc giống nhau.
- OID của bảng không đồng nghĩa với vị trí tệp dữ liệu hoặc tên file vật lý trên đĩa.

**Nguyên tắc:** dùng OID khi truy vấn catalog của một môi trường ở thời điểm hiện tại; dùng **tên định danh có schema, migration và khóa nghiệp vụ** khi muốn mô tả hoặc nhận diện đối tượng bền vững qua nhiều lần triển khai.

### 3.2. Vì sao một OID trần không đủ mô tả mọi đối tượng?

PostgreSQL có nhiều catalog mang cột `oid`: `pg_class`, `pg_type`, `pg_proc`, `pg_namespace`... Một giá trị số thiếu ngữ cảnh không nói chắc đó là bảng, function hay kiểu dữ liệu.

Khi nói về một dependency, PostgreSQL thường lưu thêm **catalog chứa đối tượng**, **OID của đối tượng** và đôi khi **số thứ tự của thành phần con**. Ta sẽ gặp bộ ba này ở `pg_depend`.

## 4. regclass, regtype và cách ánh xạ tên với OID

Thay vì tự tìm số OID, PostgreSQL cung cấp các kiểu alias như:

| Kiểu alias | Nhận diện | Ví dụ |
|---|---|---|
| `regclass` | Relation: table, view, index, sequence... | `'catalog_lab.nhan_vien'::regclass` |
| `regtype` | Kiểu dữ liệu | `'numeric'::regtype` |
| `regnamespace` | Schema | `'catalog_lab'::regnamespace` |
| `regproc` | Function theo tên, có giới hạn khi overload | `'lower'::regproc` |
| `regprocedure` | Function cụ thể theo tên và danh sách kiểu tham số | `'lower(text)'::regprocedure` |
| `regrole` | Role | `'some_role'::regrole` |

Các kiểu này cho phép viết SQL gần với tên đối tượng mà PostgreSQL sẽ tra cứu thành OID.

Ví dụ sau chỉ chạy khi bảng `catalog_lab.nhan_vien` đã được tạo ở phần thực hành:

~~~sql
SELECT
    'catalog_lab.nhan_vien'::regclass AS relation_name,
    'catalog_lab.nhan_vien'::regclass::oid AS relation_oid;
~~~

Phép cast `::regclass` tìm relation bằng tên. Phép cast tiếp `::oid` lấy số OID.

Nếu object không tồn tại, cast trực tiếp thành `regclass` có thể báo lỗi. Khi muốn kiểm tra sự tồn tại an toàn hơn:

~~~sql
SELECT to_regclass('catalog_lab.nhan_vien') AS existing_relation;
SELECT to_regclass('catalog_lab.khong_ton_tai') AS missing_relation;
~~~

`to_regclass` trả `NULL` nếu tên không tìm thấy theo quy tắc tra cứu tên, thay vì buộc query lỗi như một cast không hợp lệ.

### 4.1. Search path ảnh hưởng kết quả tên được hiển thị

PostgreSQL sử dụng `search_path` để giải quyết tên không kèm schema:

~~~sql
SHOW search_path;
~~~

Câu:

~~~sql
SELECT 'nhan_vien'::regclass;
~~~

chỉ thành công nếu một relation có tên `nhan_vien` được nhìn thấy theo đường tìm schema hiện tại. Ngay cả cách **in** một giá trị `regclass` cũng có thể rút gọn schema nếu đối tượng không bị mơ hồ trong `search_path`.

Để giảm nhập nhằng, khi viết truy vấn quản trị và tài liệu nên dùng:

~~~sql
SELECT 'catalog_lab.nhan_vien'::regclass;
~~~

Nếu tên bảng/schema có chữ hoa được quote hoặc ký tự đặc biệt, phải tuân thủ quy tắc quote identifier của PostgreSQL. Không ghép trực tiếp tên schema/bảng từ input không đáng tin cậy vào SQL quản trị.

## 5. Chuẩn bị môi trường thực hành

Ta sẽ tạo một mô hình nhỏ, dùng cùng một nhóm đối tượng để quan sát nhiều catalog.

Mô hình:

~~~text
Schema: catalog_lab
  |
  +-- Table: phong_ban
  |       +-- PK: phong_ban_id
  |       +-- UNIQUE: ten_phong
  |
  +-- Table: nhan_vien
  |       +-- PK: nhan_vien_id
  |       +-- FK: phong_ban_id --> phong_ban
  |       +-- UNIQUE: email
  |       +-- CHECK: luong >= 0
  |       +-- Index: idx_nhan_vien_ho_ten
  |
  +-- View: v_nhan_vien
  |       +-- Depends on nhan_vien and phong_ban
  |
  +-- Sequence: so_phieu_seq
  |
  +-- Function: luong_tang_10pct(numeric)
~~~

**Chỉ dùng database thử có thể xóa.** Đoạn DDL ở dưới chứa `DROP SCHEMA ... CASCADE`, có thể xóa mọi đối tượng trong schema `catalog_lab` cùng các đối tượng phụ thuộc. Không chạy trên production hoặc một database dùng chung nếu chưa bảo đảm phạm vi hoàn toàn an toàn.

### 5.1. Tạo schema, bảng, view, sequence và function

Có thể lưu toàn bộ đoạn sau thành `catalog_lab.sql` rồi chạy bằng `psql -v ON_ERROR_STOP=1 --single-transaction -f catalog_lab.sql` trên **database lab**:

~~~sql
-- Chỉ dành cho database thực hành có thể reset.
DROP SCHEMA IF EXISTS catalog_lab CASCADE;
CREATE SCHEMA catalog_lab;

CREATE TABLE catalog_lab.phong_ban (
    phong_ban_id INTEGER PRIMARY KEY,
    ten_phong TEXT NOT NULL UNIQUE
);

CREATE TABLE catalog_lab.nhan_vien (
    nhan_vien_id INTEGER PRIMARY KEY,
    phong_ban_id INTEGER NOT NULL,
    ho_ten TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    luong NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tao_luc TIMESTAMPTZ NOT NULL
        DEFAULT TIMESTAMPTZ '2026-01-01 00:00:00+00',

    CONSTRAINT fk_nhan_vien_phong_ban
        FOREIGN KEY (phong_ban_id)
        REFERENCES catalog_lab.phong_ban(phong_ban_id),

    CONSTRAINT chk_nhan_vien_luong
        CHECK (luong >= 0)
);

CREATE INDEX idx_nhan_vien_ho_ten
ON catalog_lab.nhan_vien (ho_ten);

CREATE VIEW catalog_lab.v_nhan_vien AS
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    nv.email,
    pb.ten_phong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id;

CREATE SEQUENCE catalog_lab.so_phieu_seq START WITH 1;

CREATE FUNCTION catalog_lab.luong_tang_10pct(p_luong NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT p_luong * 1.10
$function$;

COMMENT ON TABLE catalog_lab.nhan_vien
    IS 'Bảng nhân viên dùng cho bài học system catalog';

COMMENT ON COLUMN catalog_lab.nhan_vien.ho_ten
    IS 'Họ và tên nhân viên';

INSERT INTO catalog_lab.phong_ban
    (phong_ban_id, ten_phong)
VALUES
    (1, 'Kỹ thuật'),
    (2, 'Kinh doanh'),
    (3, 'Hỗ trợ');

INSERT INTO catalog_lab.nhan_vien
    (nhan_vien_id, phong_ban_id, ho_ten, email, luong)
VALUES
    (101, 1, 'Nguyễn An',  'an@example.test',   16000000.00),
    (102, 1, 'Trần Bình',  'binh@example.test', 19000000.00),
    (103, 2, 'Lê Chi',    'chi@example.test',  15000000.00),
    (104, 3, 'Phạm Dũng', 'dung@example.test', 13000000.00);
~~~

Các giá trị email thuộc domain dành cho ví dụ, không phải tài khoản thực. Dữ liệu và ID cố định để có thể chạy các truy vấn minh họa; **OID của những đối tượng tạo ra không cố định**.

### 5.2. Quan sát bảng bằng SQL thông thường

~~~sql
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    pb.ten_phong,
    nv.luong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id
ORDER BY nv.nhan_vien_id;
~~~

Đây là truy vấn **dữ liệu nghiệp vụ**. Các phần tiếp theo sẽ tra cứu metadata dùng để PostgreSQL hiểu hai bảng và mối quan hệ giữa chúng.

## 6. Bản đồ liên kết giữa các catalog

Một sơ đồ rút gọn:

~~~text
pg_namespace
    oid <---------------- pg_class.relnamespace
                                |
                                | pg_class.oid
                                |
                     +----------+-------------------+
                     |          |                   |
                     v          v                   v
        pg_attribute.attrelid  pg_index.indrelid   pg_constraint.conrelid
             |                   |
             | atttypid          | indexrelid
             v                   v
           pg_type          pg_class (index relation)

pg_constraint.confrelid -----> pg_class (bảng được FK tham chiếu)
pg_constraint.conkey --------> pg_attribute.attnum (cột nguồn)
pg_constraint.confkey -------> pg_attribute.attnum (cột đích)

pg_rewrite.ev_class ---------> pg_class (view)
pg_depend.classid/objid -----> Đối tượng phụ thuộc
pg_depend.refclassid/refobjid -> Đối tượng được phụ thuộc

pg_proc.pronamespace --------> pg_namespace
pg_description.classoid/objoid -> Đối tượng có comment
~~~

Lưu ý: sơ đồ chỉ là **một phần** của mô hình catalog PostgreSQL, không phải đầy đủ mọi quan hệ nội bộ. Những catalog còn lại sẽ được bổ sung khi cần tìm hiểu sâu về partition, role, trigger, extension hoặc replication.

**Bí quyết đọc catalog:** hãy luôn hỏi “OID này thuộc catalog nào?” và “đây là định danh đối tượng hay số thứ tự cột?”. Không nên JOIN chỉ vì hai cột đều có tên gần giống hoặc cùng kiểu `oid`.

## 7. pg_namespace: schema được nhận diện như thế nào?

`pg_namespace` lưu thông tin về schema, gồm:

- `oid`: OID của schema.
- `nspname`: tên schema.
- `nspowner`: OID của role sở hữu schema.
- `nspacl`: thông tin quyền ở mức schema khi có cấu hình tương ứng.

Truy vấn:

~~~sql
SELECT
    n.oid AS schema_oid,
    n.nspname AS schema_name,
    n.nspowner AS owner_oid
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname = 'catalog_lab';
~~~

Nếu schema đã tạo thành công, kết quả có một dòng cho `catalog_lab`. Giá trị `schema_oid` phụ thuộc database/cluster tại lần chạy.

Các schema hệ thống thường gặp:

- `pg_catalog`: system catalogs và các hàm/kiểu hệ thống.
- `information_schema`: các view metadata theo chuẩn SQL.
- `pg_toast`: các quan hệ phục vụ lưu giá trị lớn của PostgreSQL.
- Các schema tạm như `pg_temp_N` xuất hiện theo nhu cầu session.
- `public`: schema thường có trong một database mới.
- Các schema người dùng tự tạo, như `catalog_lab`.

Câu lệnh:

~~~sql
CREATE SCHEMA catalog_lab;
~~~

thực chất yêu cầu PostgreSQL tạo đối tượng schema và metadata tương ứng; bạn không tự `INSERT` vào `pg_namespace`.

## 8. pg_class: catalog của các relation

Tên `pg_class` dễ gây nhầm vì có chữ “class”, nhưng trong PostgreSQL nó mô tả **relation** theo nghĩa rộng: bảng, index, view, materialized view, sequence và các loại đối tượng giống relation.

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `oid` | Định danh của relation |
| `relname` | Tên relation |
| `relnamespace` | OID schema chứa relation, liên kết với `pg_namespace.oid` |
| `relkind` | Loại relation |
| `relowner` | OID role sở hữu |
| `relpersistence` | Quan hệ permanent, unlogged hoặc temporary |
| `reltype` | OID của row/composite type tương ứng khi có |
| `reltuples` | Ước lượng số hàng theo thống kê |
| `relpages` | Ước lượng số trang dữ liệu |
| `relfilenode` | Một thành phần liên quan đến lưu trữ vật lý, **không đồng nghĩa OID** |

Một số giá trị phổ biến của `relkind`:

| relkind | Loại |
|---|---|
| `r` | Bảng thông thường |
| `p` | Bảng partitioned |
| `i` | Index thông thường |
| `I` | Partitioned index |
| `v` | View |
| `m` | Materialized view |
| `S` | Sequence |
| `f` | Foreign table |
| `c` | Composite type relation |
| `t` | TOAST table |

Các giá trị này mang tính đặc thù PostgreSQL và có thể được mở rộng ở phiên bản khác.

### 8.1. Liệt kê các relation trong schema lab

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.oid AS relation_oid,
    c.relkind,
    c.oid::regclass AS regclass_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY c.relkind, c.relname;
~~~

Ở đây:

- `c.relnamespace` là OID của schema.
- `n.oid` là OID của bản ghi schema trong `pg_namespace`.
- `c.oid::regclass` giúp hiển thị OID dưới dạng tên relation theo quy tắc resolve tên của PostgreSQL.

Kết quả sẽ có bảng `phong_ban`, `nhan_vien`, view `v_nhan_vien`, sequence `so_phieu_seq` và các index (bao gồm index được tạo tự động cho `PRIMARY KEY`/`UNIQUE`). **Không hardcode số lượng index theo tên giả định**; hãy đọc tên thực tế trong môi trường của bạn.

### 8.2. Vì sao pg_class không chỉ chứa bảng?

Một index cũng là một relation có metadata riêng, nên được ghi trong `pg_class`. View cũng được nhận diện như relation, dù view thông thường không lưu kết quả truy vấn dưới dạng bảng dữ liệu riêng. Sequence cũng có đối tượng relation và metadata liên quan.

Do đó khi viết:

~~~sql
SELECT relname
FROM pg_catalog.pg_class;
~~~

bạn sẽ nhìn thấy nhiều đối tượng hơn “danh sách bảng của ứng dụng”. Phải lọc `relkind` và schema tùy mục tiêu.

### 8.3. reltuples là ước lượng

~~~sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

`reltuples` có thể được cập nhật bởi `VACUUM`/`ANALYZE` và các hoạt động khác, không phải `COUNT(*)` cập nhật tức thời. Không dùng nó làm số lượng bản ghi chính xác cho báo cáo tài chính hoặc kiểm thử hàng đã nạp.

## 9. pg_attribute: mỗi cột gắn với relation nào?

`pg_attribute` chứa thông tin về thuộc tính/cột của relation. Những cột quan trọng:

- `attrelid`: OID relation chứa cột, trỏ đến `pg_class.oid`.
- `attname`: tên cột.
- `attnum`: số thứ tự thuộc tính trong relation.
- `atttypid`: OID kiểu dữ liệu, trỏ đến `pg_type.oid`.
- `atttypmod`: thông số kiểu dữ liệu bổ sung, tùy type.
- `attnotnull`: thông tin cột `NOT NULL` ở mức metadata.
- `attisdropped`: cột đã bị drop ở mức logic nhưng có thể còn metadata nội bộ.

Truy vấn:

~~~sql
SELECT
    a.attrelid::regclass AS relation_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    a.atttypid AS type_oid,
    a.attnotnull
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Vì sao có điều kiện:

- `attnum > 0`: chỉ lấy các cột người dùng thông thường, bỏ những thuộc tính hệ thống có số thứ tự đặc biệt.
- `NOT attisdropped`: không hiển thị các cột đã bị `DROP COLUMN`.

**Không lấy toàn bộ `pg_attribute` rồi kết luận mọi hàng đều là cột do người dùng tạo.** PostgreSQL có cả system attributes và metadata phục vụ những loại relation khác.

### 9.1. Kết hợp pg_attribute với pg_type

Để biết tên kiểu:

~~~sql
SELECT
    a.attnum,
    a.attname,
    t.typname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS display_type
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_type AS t
    ON t.oid = a.atttypid
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Kết quả giúp phân biệt:

- `typname`: tên nội bộ của type.
- `format_type`: biểu diễn thân thiện cho DDL, ví dụ `numeric(12,2)` thay vì chỉ nhìn OID type.

Dùng `format_type` thường phù hợp hơn việc tự giải mã `atttypmod` cho các kiểu dữ liệu có tham số.

### 9.2. OID của kiểu dữ liệu không phải OID của cột

Giả sử cột `luong` dùng `NUMERIC(12,2)`. `atttypid` nói cột dùng **kiểu numeric**, trong khi `atttypmod` lưu những thông số bổ sung cần thiết cho biểu diễn kiểu. Cột không nhất thiết có một OID riêng trong `pg_attribute`; nhiều catalog dùng cặp **OID relation + attnum** để nhận diện một cột.

Đây là ví dụ điển hình vì sao **không phải mọi đối tượng con đều được nhận diện bằng một OID duy nhất**.

## 10. pg_type: metadata của kiểu dữ liệu

`pg_type` mô tả các kiểu dữ liệu PostgreSQL:

- Các kiểu built-in như `integer`, `text`, `numeric`, `timestamp`.
- Kiểu composite (bao gồm row type gắn với relation).
- Kiểu enum, domain, range và những kiểu mở rộng.
- Các kiểu array liên quan.

Một số cột:

| Cột | Ý nghĩa |
|---|---|
| `oid` | OID của type |
| `typname` | Tên type |
| `typnamespace` | Schema chứa type |
| `typtype` | Nhóm loại type |
| `typrelid` | Relation liên quan đối với một số composite type |
| `typelem` | Element type đối với những kiểu liên quan array |
| `typbasetype` | Base type đối với domain |

Ví dụ:

~~~sql
SELECT
    t.oid AS type_oid,
    t.typname,
    t.typtype,
    n.nspname AS schema_name
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE t.oid IN (
    'integer'::regtype,
    'text'::regtype,
    'numeric'::regtype
)
ORDER BY t.typname;
~~~

### 10.1. Bảng có row type liên quan

Trong PostgreSQL, một bảng thường có một composite row type đi kèm. Catalog `pg_class` có trường `reltype` tham chiếu tới OID của type đó.

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltype AS row_type_oid,
    t.typname AS row_type_name,
    t.typtype
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.reltype
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

Đây là một liên kết **relation → type** khác với **column → type**. Nó giải thích vì sao PostgreSQL có thể sử dụng kiểu composite tương ứng với hàng của một bảng trong nhiều biểu thức SQL.

## 11. pg_attrdef: default của cột

Khai báo:

~~~sql
luong NUMERIC(12, 2) NOT NULL DEFAULT 0
~~~

không chỉ được lưu thành một chuỗi DDL. Metadata biểu thức default được quản lý, trong đó catalog `pg_attrdef` giữ thông tin như:

- `adrelid`: OID relation chứa cột.
- `adnum`: số thứ tự cột.
- `adbin`: biểu diễn nội bộ của biểu thức default.

Có thể nối `pg_attribute` với `pg_attrdef`:

~~~sql
SELECT
    a.attnum,
    a.attname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS data_type,
    pg_catalog.pg_get_expr(
        d.adbin,
        d.adrelid
    ) AS default_expression
FROM pg_catalog.pg_attribute AS a
LEFT JOIN pg_catalog.pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

`pg_get_expr` chuyển biểu diễn lưu trữ thành một biểu thức SQL đọc được. **Không tự xử lý văn bản ở `adbin` như SQL thuần** vì cấu trúc nội bộ không được thiết kế làm giao diện text ổn định cho ứng dụng.

## 12. pg_constraint: ràng buộc nằm ở đâu?

PostgreSQL lưu nhiều loại constraint trong `pg_constraint`. Những cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `oid` | OID của constraint |
| `conname` | Tên constraint |
| `contype` | Loại constraint |
| `conrelid` | Relation chứa constraint, nếu là constraint trên bảng |
| `contypid` | Type liên quan khi là constraint của domain |
| `confrelid` | Relation được tham chiếu bởi foreign key |
| `conkey` | Danh sách số cột (attnum) phía nguồn |
| `confkey` | Danh sách số cột (attnum) phía được tham chiếu |
| `condeferrable` | Có thể trì hoãn kiểm tra theo cấu hình không |
| `condeferred` | Có kiểm tra deferred theo mặc định không |
| `convalidated` | Constraint đã được xác minh theo trạng thái catalog chưa |

Một số giá trị `contype`:

- `p`: primary key.
- `u`: unique constraint.
- `f`: foreign key.
- `c`: check constraint.
- `x`: exclusion constraint.

Các ràng buộc khác hoặc thay đổi trong phiên bản mới cần đối chiếu tài liệu server đang dùng.

### 12.1. Liệt kê constraint của một bảng

~~~sql
SELECT
    con.oid AS constraint_oid,
    con.conname,
    con.contype,
    con.conrelid::regclass AS source_relation,
    CASE
        WHEN con.confrelid = 0 THEN NULL
        ELSE con.confrelid::regclass
    END AS referenced_relation,
    pg_catalog.pg_get_constraintdef(
        con.oid,
        true
    ) AS definition
FROM pg_catalog.pg_constraint AS con
WHERE con.conrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY con.contype, con.conname;
~~~

Kết quả sẽ mô tả khóa chính, unique trên email, khóa ngoại `fk_nhan_vien_phong_ban` và check `chk_nhan_vien_luong`. Có thể gặp khác biệt ở các thuộc tính `NOT NULL` và dạng hiển thị do phiên bản PostgreSQL, nên không nên coi `pg_constraint` là cách duy nhất để xem mọi thông tin cột không cho NULL.

### 12.2. Foreign key liên kết hai bảng bằng OID

Với foreign key:

~~~sql
FOREIGN KEY (phong_ban_id)
REFERENCES catalog_lab.phong_ban(phong_ban_id)
~~~

catalog giữ:

~~~text
pg_constraint
  contype  = 'f'
  conrelid = OID của catalog_lab.nhan_vien
  confrelid = OID của catalog_lab.phong_ban
  conkey   = {số thứ tự cột phong_ban_id trong nhan_vien}
  confkey  = {số thứ tự cột phong_ban_id trong phong_ban}
~~~

Đây là metadata về **quan hệ khóa ngoại giữa hai bảng**. Khi ứng dụng chèn dòng nhân viên với `phong_ban_id` không tồn tại, engine dùng constraint để từ chối giao dịch theo quy tắc xác định.

### 12.3. Từ conkey/confkey tới tên cột thực tế

Một foreign key có thể gồm nhiều cột. Không nên đoán rằng mọi FK chỉ có một phần tử. PostgreSQL lưu danh sách `attnum` tương ứng; có thể dùng `unnest(... ) WITH ORDINALITY` để lấy các cặp cột theo vị trí:

~~~sql
SELECT
    con.conname,
    con.conrelid::regclass AS source_table,
    src_att.attname AS source_column,
    con.confrelid::regclass AS referenced_table,
    ref_att.attname AS referenced_column,
    keys.ordinal_position
FROM pg_catalog.pg_constraint AS con
CROSS JOIN LATERAL unnest(
    con.conkey,
    con.confkey
) WITH ORDINALITY
    AS keys(source_attnum, referenced_attnum, ordinal_position)
JOIN pg_catalog.pg_attribute AS src_att
    ON src_att.attrelid = con.conrelid
   AND src_att.attnum = keys.source_attnum
JOIN pg_catalog.pg_attribute AS ref_att
    ON ref_att.attrelid = con.confrelid
   AND ref_att.attnum = keys.referenced_attnum
WHERE con.contype = 'f'
  AND con.conrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY con.conname, keys.ordinal_position;
~~~

Ý nghĩa:

- `conrelid` trỏ tới bảng chứa FK.
- `confrelid` trỏ tới bảng được tham chiếu.
- `conkey` và `confkey` là hai dãy `attnum` theo cùng thứ tự thành phần.
- `WITH ORDINALITY` giúp giữ vị trí khi FK có nhiều cột.
- `pg_attribute` đổi số cột thành tên cột dễ đọc.

Đây là một ví dụ điển hình về việc **JOIN nhiều catalog để tái dựng một cấu trúc DDL**.

## 13. pg_index: index cũng có OID và relation riêng

Một index có một bản ghi relation trong `pg_class`, đồng thời có metadata đặc thù trong `pg_index`.

Những cột quan trọng:

- `indexrelid`: OID relation đại diện cho index.
- `indrelid`: OID table hoặc relation mà index phục vụ.
- `indisunique`: index có tính duy nhất hay không.
- `indisprimary`: index phục vụ primary key hay không.
- `indisvalid`: index được coi là valid cho việc sử dụng theo trạng thái metadata.
- `indkey`: thông tin số cột được index; biểu thức phức tạp cần đọc thêm metadata.
- `indexprs`: biểu diễn nội bộ cho một số index expression.
- `indpred`: predicate cho partial index.

### 13.1. Xem index của bảng nhan_vien

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    pg_catalog.pg_get_indexdef(i.indexrelid) AS create_index_sql
FROM pg_catalog.pg_index AS i
WHERE i.indrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

Bạn sẽ gặp ít nhất:

- Index của `PRIMARY KEY (nhan_vien_id)`.
- Index của `UNIQUE (email)`.
- Index thường `idx_nhan_vien_ho_ten` đã tạo.

Tên index tự động của constraint có thể theo quy tắc PostgreSQL và bị ảnh hưởng bởi tên object đã có; hãy dùng kết quả `pg_get_indexdef` thay vì dự đoán tên trong một hệ thống không phải demo.

### 13.2. Index không phải foreign key

Một hiểu nhầm là cứ có `FOREIGN KEY` thì PostgreSQL tự tạo index trên **cột phía tham chiếu**. PostgreSQL yêu cầu một khóa/unique phù hợp ở phía được tham chiếu, nhưng **không tự động tạo index cho mọi cột foreign key phía con**.

Ví dụ nếu ứng dụng hay truy vấn nhân viên theo phòng ban:

~~~sql
SELECT *
FROM catalog_lab.nhan_vien
WHERE phong_ban_id = 1;
~~~

có thể xem xét:

~~~sql
CREATE INDEX idx_nhan_vien_phong_ban
ON catalog_lab.nhan_vien (phong_ban_id);
~~~

Đây là một thay đổi DDL làm xuất hiện relation index mới trong `pg_class` và metadata trong `pg_index`. Có nên tạo hay không phụ thuộc truy vấn, kích thước bảng, thống kê và chi phí ghi, không phải chỉ vì thấy FK.

### 13.3. Vì sao không tự giải mã indkey?

`indkey` liên quan số thuộc tính và có những trường hợp đặc biệt như expression index. Đối với phân tích DDL index ở mức tổng quát, nên dùng:

~~~sql
SELECT pg_catalog.pg_get_indexdef(
    'catalog_lab.idx_nhan_vien_ho_ten'::regclass
);
~~~

Tương tự, có thể dùng `pg_indexes` khi chỉ cần danh sách index và `indexdef` ở mức người dùng:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'catalog_lab'
ORDER BY tablename, indexname;
~~~

Không cần parse các cấu trúc lưu trữ nội bộ nếu PostgreSQL đã có hàm tiện ích deparse phù hợp.

## 14. View: tại sao quan hệ phụ thuộc không hiện đơn giản trong pg_class?

Một view như:

~~~sql
CREATE VIEW catalog_lab.v_nhan_vien AS
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    pb.ten_phong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id;
~~~

tham chiếu hai bảng. PostgreSQL phải biết điều đó để ngăn xóa hoặc sửa những đối tượng làm view không còn hợp lệ.

**Nhưng dependency của view không chỉ là một cột “parent_table_oid” trong `pg_class`.** PostgreSQL quản lý rewrite rule phục vụ view qua `pg_rewrite` và lưu nhiều quan hệ phụ thuộc qua `pg_depend`.

### 14.1. Xem định nghĩa view

~~~sql
SELECT pg_catalog.pg_get_viewdef(
    'catalog_lab.v_nhan_vien'::regclass,
    true
) AS view_definition;
~~~

Hàm `pg_get_viewdef` trả lại biểu diễn SQL của truy vấn view. Đây là cách dễ đọc hơn việc tự giải mã biểu thức và rewrite tree nội bộ.

### 14.2. pg_rewrite đại diện cho rule của view

Các cột đáng chú ý:

- `pg_rewrite.oid`: OID của rule.
- `pg_rewrite.ev_class`: OID relation liên quan, thường là view trong ví dụ.
- `pg_rewrite.rulename`: tên rule; view có rule `_RETURN` phục vụ truy vấn.
- Các metadata về command/event và cây truy vấn.

Có thể quan sát:

~~~sql
SELECT
    r.oid AS rule_oid,
    r.rulename,
    r.ev_class::regclass AS view_name
FROM pg_catalog.pg_rewrite AS r
WHERE r.ev_class = 'catalog_lab.v_nhan_vien'::regclass
ORDER BY r.rulename;
~~~

Một điểm quan trọng khi nghiên cứu dependency: **phụ thuộc của các bảng được tham chiếu bởi view thường được ghi cho rewrite rule của view**, nên chỉ nhìn dependency trực tiếp của OID `pg_class` đại diện view có thể bỏ sót những mối liên hệ mong đợi.

## 15. pg_depend: PostgreSQL ghi lại quan hệ phụ thuộc như thế nào?

**Dependency** là quan hệ ở mức **vòng đời đối tượng database**: nếu đối tượng A sử dụng đối tượng B, PostgreSQL cần biết liệu B có thể bị xóa, thay đổi hoặc có bắt buộc xóa A cùng B không.

Catalog `pg_depend` chứa những trường quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `classid` | OID của catalog chứa đối tượng **phụ thuộc** |
| `objid` | OID của đối tượng phụ thuộc trong catalog đó |
| `objsubid` | Số thành phần con, thường dùng cho cột; 0 khi không có |
| `refclassid` | OID của catalog chứa đối tượng **được tham chiếu** |
| `refobjid` | OID của đối tượng được tham chiếu |
| `refobjsubid` | Số thành phần con của đối tượng được tham chiếu |
| `deptype` | Kiểu phụ thuộc và hành vi xóa liên quan |

Có thể hình dung một cạnh dependency:

~~~text
Đối tượng phụ thuộc (dependent object)
    classid, objid, objsubid
                   |
                   v
Đối tượng được phụ thuộc (referenced object)
    refclassid, refobjid, refobjsubid
~~~

### 15.1. Vì sao phải có classid?

Một `objid` có giá trị số chỉ có ý nghĩa khi biết nó nằm trong catalog nào. `classid` nhận diện catalog chứa đối tượng, còn `objid` nhận diện hàng tương ứng trong catalog đó.

Ví dụ nếu `classid = 'pg_rewrite'::regclass` thì `objid` cần được hiểu là OID của một rule trong `pg_rewrite`. Nếu `classid = 'pg_class'::regclass` thì `objid` nhận diện một relation trong `pg_class`.

Đây là điểm khác biệt giữa **một giá trị OID** và **một tham chiếu metadata đầy đủ**.

### 15.2. Một số deptype thường gặp

- `n` — **normal dependency**: đối tượng phụ thuộc cần đối tượng được tham chiếu; lệnh DROP thường bị hạn chế nếu không xử lý dependency.
- `a` — **auto dependency**: đối tượng phụ thuộc có thể tự động bị loại bỏ khi đối tượng được tham chiếu bị xóa trong tình huống phù hợp.
- `i` — **internal dependency**: đối tượng được quản lý như thành phần nội bộ của đối tượng khác; không nên xử lý độc lập như đối tượng tùy ý.
- `e` — **extension dependency**: đối tượng là thành phần của extension, vòng đời gắn với extension.

Những phiên bản PostgreSQL khác nhau có thể có thêm các mã dependency chuyên dụng, ví dụ liên quan partition. Đừng viết công cụ quản trị mặc định mọi `deptype` chỉ gồm bốn giá trị trên.

### 15.3. Truy dấu view phụ thuộc vào bảng nào

Vì dependency của view liên quan `pg_rewrite`, ta có thể JOIN `pg_rewrite` và `pg_depend` để tìm relation được tham chiếu:

~~~sql
SELECT DISTINCT
    r.ev_class::regclass AS dependent_view,
    referred.oid::regclass AS referenced_relation,
    d.deptype
FROM pg_catalog.pg_rewrite AS r
JOIN pg_catalog.pg_depend AS d
    ON d.classid = 'pg_catalog.pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_catalog.pg_class AS referred
    ON d.refclassid = 'pg_catalog.pg_class'::regclass
   AND d.refobjid = referred.oid
WHERE r.ev_class = 'catalog_lab.v_nhan_vien'::regclass
  AND r.rulename = '_RETURN'
  AND referred.oid <> r.ev_class
ORDER BY referenced_relation::text, d.deptype;
~~~

Với view demo, thông tin dependency hướng về `catalog_lab.nhan_vien` và `catalog_lab.phong_ban`. Có thể có dependency ở mức **cột** thông qua `refobjsubid`, nên `DISTINCT` trong truy vấn giúp gộp các cạnh cùng bảng khi chỉ cần tên relation.

**Mức độ phụ thuộc chính xác của mỗi loại object phụ thuộc cách PostgreSQL lưu trữ metadata.** Đây là một truy vấn minh họa riêng cho view; không dùng nó như thuật toán chung để tìm mọi dependency của mọi object.

### 15.4. DROP RESTRICT và DROP CASCADE

Giả sử có bảng được view sử dụng. Khi chạy:

~~~sql
-- Ví dụ ý tưởng, không chạy trên môi trường có dữ liệu cần giữ:
DROP TABLE catalog_lab.nhan_vien;
~~~

PostgreSQL thường từ chối xóa bảng nếu có view hoặc đối tượng khác phụ thuộc và chưa được xử lý. Có thể thấy gợi ý sử dụng `CASCADE`, nhưng:

~~~sql
-- CỰC KỲ THẬN TRỌNG: có thể xóa các object phụ thuộc.
DROP TABLE catalog_lab.nhan_vien CASCADE;
~~~

có thể xóa thêm view/constraint hoặc đối tượng khác phụ thuộc theo quy tắc PostgreSQL.

`CASCADE` đối với **DROP object** khác hoàn toàn với `ON DELETE CASCADE` của **foreign key**. Một bên xóa các đối tượng schema/DDL; bên kia quy định cách xử lý **hàng dữ liệu** khi xóa một hàng được tham chiếu.

Không dùng `CASCADE` trên production chỉ để “lệnh DROP chạy qua”. Trước tiên hãy hiểu đồ thị dependency và phạm vi ảnh hưởng.

## 16. Foreign key không đồng nghĩa pg_depend

Hai khái niệm quan hệ thường bị nhầm:

### 16.1. Foreign key là ràng buộc dữ liệu

~~~sql
FOREIGN KEY (phong_ban_id)
REFERENCES catalog_lab.phong_ban(phong_ban_id)
~~~

Ý nghĩa: mỗi giá trị `phong_ban_id` trong `nhan_vien` phải tham chiếu một giá trị hợp lệ ở `phong_ban` theo trạng thái transaction và quy tắc của constraint.

Metadata chính để mô tả FK nằm trong `pg_constraint`.

### 16.2. pg_depend là phụ thuộc đối tượng

`pg_depend` giúp PostgreSQL quyết định xử lý DDL như `DROP TABLE`, `DROP VIEW`, `DROP TYPE`, `DROP EXTENSION` khi các object có liên hệ với nhau.

~~~text
FOREIGN KEY:
  Quan hệ giữa dữ liệu/cột của hai bảng,
  phục vụ kiểm tra INSERT/UPDATE/DELETE.

pg_depend:
  Quan hệ vòng đời giữa các object của schema,
  phục vụ kiểm soát DROP/ALTER và tính toàn vẹn metadata.
~~~

Một FK cũng là một đối tượng có dependency nội bộ, nhưng **không được thay truy vấn pg_constraint bằng một JOIN pg_depend tùy ý** rồi cho rằng đã mô tả được tất cả khóa ngoại.

## 17. pg_proc: function và procedure là đối tượng có OID

PostgreSQL lưu metadata function/procedure trong `pg_proc`. Một vài trường quan trọng:

- `oid`: OID của routine.
- `proname`: tên routine.
- `pronamespace`: OID schema.
- `proowner`: role sở hữu.
- `prorettype`: OID kiểu dữ liệu trả về.
- `proargtypes`: các kiểu đối số đầu vào theo biểu diễn catalog.
- `prokind`: phân loại function/procedure và các trường hợp liên quan.

Truy vấn các routine do ta tạo:

~~~sql
SELECT
    p.oid AS routine_oid,
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_catalog.pg_get_function_identity_arguments(
        p.oid
    ) AS identity_arguments,
    pg_catalog.pg_get_function_result(
        p.oid
    ) AS result_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY p.proname;
~~~

Vì PostgreSQL hỗ trợ **overloading** (nhiều function cùng tên nhưng khác kiểu tham số), một tên function trần không luôn đủ nhận diện routine cụ thể.

Ví dụ:

~~~sql
SELECT
    'catalog_lab.luong_tang_10pct(numeric)'::regprocedure
        AS function_identity;

SELECT catalog_lab.luong_tang_10pct(100.00) AS luong_moi;
~~~

Kiểu `regprocedure` nhận diện routine bằng **tên kèm kiểu tham số**, tránh nhập nhằng khi có nhiều bản overload.

**Không ghi OID function vào cấu hình ứng dụng để sử dụng lâu dài.** Nếu routine bị drop/recreate hoặc restore, OID có thể thay đổi. Dùng signature/tên có schema và migration phù hợp.

## 18. pg_description: COMMENT được lưu ở đâu?

PostgreSQL hỗ trợ comment trên table, column, function và nhiều loại object:

~~~sql
COMMENT ON TABLE catalog_lab.nhan_vien
    IS 'Bảng nhân viên dùng cho bài học system catalog';

COMMENT ON COLUMN catalog_lab.nhan_vien.ho_ten
    IS 'Họ và tên nhân viên';
~~~

Thông tin mô tả có thể đọc bằng những hàm công khai:

~~~sql
SELECT pg_catalog.obj_description(
    'catalog_lab.nhan_vien'::regclass,
    'pg_class'
) AS table_comment;

SELECT pg_catalog.col_description(
    'catalog_lab.nhan_vien'::regclass,
    3
) AS column_comment;
~~~

Trong schema demo, cột `ho_ten` đứng thứ ba (`attnum = 3`). Nếu thứ tự cột thay đổi do tái tạo bảng, hardcode `3` không còn an toàn; nên tìm `attnum` theo tên:

~~~sql
SELECT
    a.attname,
    pg_catalog.col_description(
        a.attrelid,
        a.attnum
    ) AS column_comment
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Catalog `pg_description` sử dụng các cột như `classoid`, `objoid` và `objsubid` để gắn mô tả với đối tượng hay thành phần con. Đây là một ví dụ khác về việc **OID cần đi kèm catalog và, với cột, số thuộc tính**.

## 19. pg_database và các shared catalog

Một PostgreSQL cluster có thể chứa nhiều database, mỗi database chứa schema và đối tượng riêng. Những catalog như `pg_database` mô tả đối tượng ở phạm vi cluster.

~~~sql
SELECT
    oid AS database_oid,
    datname AS database_name,
    datallowconn AS allows_connection
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Khác với `pg_class`/`pg_attribute` của một database cụ thể, `pg_database` là catalog ở phạm vi **shared** giữa các database của cluster. Vì vậy phải xem đúng phạm vi khi phân tích OID.

Một số metadata về role và membership cũng có phạm vi cluster, thay vì chỉ thuộc một database đơn lẻ.

### 19.1. Role và quyền

Không nên trực tiếp truy cập các catalog nhạy cảm như `pg_authid` nếu không có quyền hoặc lý do phù hợp. View `pg_roles` cung cấp thông tin role ở mức được thiết kế để quan sát:

~~~sql
SELECT
    oid,
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_catalog.pg_roles
ORDER BY rolname;
~~~

Để kiểm tra quyền đối với một bảng:

~~~sql
SELECT
    current_user AS active_role,
    pg_catalog.has_table_privilege(
        current_user,
        'catalog_lab.nhan_vien',
        'SELECT'
    ) AS can_select;
~~~

**Biết OID của bảng không giúp vượt qua phân quyền**. Query metadata và truy vấn dữ liệu là hai thao tác khác nhau, đều phải tuân thủ quyền được cấp.

## 20. Partition và quan hệ kế thừa: pg_inherits

PostgreSQL có các cấu trúc quan hệ phức tạp hơn một bảng thông thường, bao gồm partitioning và table inheritance. `pg_inherits` ghi liên kết giữa relation con và relation cha.

Các cột trọng tâm:

- `inhrelid`: OID của relation con.
- `inhparent`: OID của relation cha.
- `inhseqno`: thứ tự liên quan trong cấu trúc kế thừa.

Ví dụ câu truy vấn tổng quát:

~~~sql
SELECT
    child.oid::regclass AS child_relation,
    parent.oid::regclass AS parent_relation,
    inh.inhseqno
FROM pg_catalog.pg_inherits AS inh
JOIN pg_catalog.pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = inh.inhparent
ORDER BY parent.oid::regclass::text,
         child.oid::regclass::text;
~~~

Nếu chỉ có schema demo với các bảng thông thường và không tạo partition/inheritance, truy vấn này có thể không trả dòng liên quan `catalog_lab`. Đó là kết quả bình thường.

Một bảng partitioned có thể có `pg_class.relkind = 'p'`; từng partition là relation riêng và có metadata riêng. Không nên kết luận toàn bộ dữ liệu partitioned được lưu trong một bảng vật lý chỉ vì có tên bảng cha.

## 21. Extension và dependency

PostgreSQL có cơ chế extension để đóng gói type, function và đối tượng khác. Metadata extension nằm trong `pg_extension`.

~~~sql
SELECT
    e.oid AS extension_oid,
    e.extname AS extension_name,
    e.extversion,
    n.nspname AS schema_name
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Một extension có thể sở hữu những object mà vòng đời của chúng gắn với extension. Trong `pg_depend`, mã dependency như `e` thể hiện mối liên hệ này theo cơ chế catalog.

Ví dụ khi có một extension được cài:

~~~sql
-- Chỉ minh họa cách xem extension;
-- không tự cài extension nếu chưa có quyền/nhu cầu.
SELECT extname, extversion
FROM pg_catalog.pg_extension
ORDER BY extname;
~~~

Trên managed PostgreSQL, danh sách extension được phép và quyền cài đặt có thể bị giới hạn bởi nhà cung cấp. Việc tra cứu metadata extension không có nghĩa người dùng có thể `CREATE EXTENSION` tùy ý.

## 22. pg_trigger: trigger cũng có quan hệ catalog

Trigger trên table được quản lý trong `pg_trigger`. Một số cột:

- `oid`: OID của trigger.
- `tgname`: tên trigger.
- `tgrelid`: OID table có trigger.
- `tgfoid`: OID function được trigger gọi.
- `tgisinternal`: trigger nội bộ do PostgreSQL quản lý.

Ví dụ xem trigger **không phải nội bộ** của bảng:

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS on_table,
    t.tgfoid::regprocedure AS trigger_function,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
WHERE t.tgrelid = 'catalog_lab.nhan_vien'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Vì demo chưa tạo trigger do người dùng định nghĩa, query thường trả **0 dòng**. Điều đó không có nghĩa database không dùng trigger nội bộ: PostgreSQL có thể sử dụng các thành phần trigger nội bộ để thực thi một số cơ chế constraint, trong đó có foreign key.

Đây là lý do điều kiện `NOT t.tgisinternal` quan trọng khi mục tiêu là kiểm kê trigger do ứng dụng tự tạo.

## 23. Quan sát metadata bằng psql mà không tự JOIN catalog

Nhiều câu hỏi cơ bản có thể được trả lời bằng meta-command của `psql`:

~~~text
\dn                   -- Liệt kê schema
\dt catalog_lab.*     -- Liệt kê bảng trong schema lab
\dv catalog_lab.*     -- Liệt kê view
\ds catalog_lab.*     -- Liệt kê sequence
\di catalog_lab.*     -- Liệt kê index
\d catalog_lab.nhan_vien
\df catalog_lab.*
~~~

Các chuỗi bắt đầu bằng `\` là **meta-command của psql**, không phải câu SQL PostgreSQL chuẩn để gửi trực tiếp qua JDBC.

Ví dụ `\d catalog_lab.nhan_vien` có thể trình bày:

- Các cột, kiểu và default.
- Khóa chính, unique, index.
- Foreign key và những đối tượng liên quan.
- Comment khi dùng những tùy chọn hiển thị phù hợp.

`psql` dùng những truy vấn metadata và xử lý phía client để tạo giao diện mô tả. Vì vậy việc hiểu catalog giúp bạn **hiểu kết quả của psql**, nhưng không nhất thiết phải tự viết JOIN phức tạp cho mọi công việc vận hành.

## 24. information_schema khi cần khả năng di động

Nếu mục tiêu là liệt kê metadata chung của các bảng và cột, có thể bắt đầu từ `information_schema`:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'catalog_lab'
ORDER BY table_name, ordinal_position;
~~~

Ưu điểm:

- Tên cột/view gần với cách mô tả metadata theo chuẩn SQL.
- Thường dễ dùng cho một số loại công cụ sinh tài liệu hoặc ứng dụng cần giảm phụ thuộc vào catalog cụ thể.
- Có thể tự lọc các đối tượng theo quyền nhìn thấy của người đang kết nối.

Nhưng `information_schema` không bao phủ mọi tính năng PostgreSQL-specific ở cùng mức chi tiết như `pg_catalog`, chẳng hạn nhiều trường về MVCC, persistence, internal dependency và storage.

### 24.1. Chọn nguồn nào?

| Câu hỏi | Nguồn phù hợp |
|---|---|
| Bảng có những cột nào? | `information_schema.columns` hoặc `pg_attribute` |
| Index cụ thể được định nghĩa ra sao? | `pg_indexes`, `pg_index`, `pg_get_indexdef` |
| Constraint có những cột nào? | `pg_constraint` kết hợp `pg_attribute` |
| Table/view thuộc schema nào? | `pg_class` kết hợp `pg_namespace` |
| View phụ thuộc bảng nào? | `pg_rewrite` và `pg_depend` cho phân tích chuyên sâu |
| Type của cột là gì? | `format_type`, `pg_type` |
| Table có bao nhiêu dòng chính xác? | `COUNT(*)` trên bảng nghiệp vụ |
| Server đang có bao nhiêu connection? | `pg_stat_activity`/các view thống kê phù hợp |
| Tài khoản có quyền SELECT không? | `has_table_privilege` |
| Chuyển đổi metadata cho công cụ đa DB | Có thể bắt đầu từ `information_schema` |

**Không có nguồn nào là tốt nhất cho mọi câu hỏi.** Cần chọn theo mức chi tiết, tính di động và quyền truy cập cần thiết.

## 25. Một số truy vấn catalog thường dùng trong công việc

### 25.1. Liệt kê bảng người dùng trong một schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.oid AS table_oid
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
~~~

`'r'` là ordinary table và `'p'` là partitioned table. Query không liệt kê view, index hoặc sequence.

### 25.2. Xem cột và kiểu dữ liệu

~~~sql
SELECT
    a.attnum,
    a.attname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS type_name,
    a.attnotnull
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 25.3. Xem khóa ngoại trên mọi bảng thuộc schema lab

~~~sql
SELECT
    con.conname,
    con.conrelid::regclass AS source_table,
    con.confrelid::regclass AS target_table,
    pg_catalog.pg_get_constraintdef(
        con.oid,
        true
    ) AS fk_definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c
    ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND con.contype = 'f'
ORDER BY source_table::text, con.conname;
~~~

### 25.4. Xem index và biểu thức index

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS on_table,
    i.indisunique,
    i.indisprimary,
    pg_catalog.pg_get_indexdef(
        i.indexrelid
    ) AS definition
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY on_table::text, index_name::text;
~~~

### 25.5. Đọc định nghĩa view

~~~sql
SELECT
    c.oid::regclass AS view_name,
    pg_catalog.pg_get_viewdef(c.oid, true) AS definition
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND c.relkind = 'v'
ORDER BY c.relname;
~~~

### 25.6. Lấy OID theo tên và kiểm tra tồn tại

~~~sql
SELECT
    to_regclass('catalog_lab.phong_ban') AS department_table,
    to_regclass('catalog_lab.nhan_vien') AS employee_table,
    to_regclass('catalog_lab.unknown') AS missing_table;
~~~

### 25.7. Hiển thị comment của bảng và cột

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    pg_catalog.obj_description(
        c.oid,
        'pg_class'
    ) AS relation_comment
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

Các ví dụ chỉ đọc metadata. Không cần quyền sửa catalog để tự tìm hiểu cấu trúc database.

## 26. OID khác tên object và đường dẫn tệp vật lý

Ba đại lượng rất dễ bị nhầm:

**Tên object:**

~~~text
catalog_lab.nhan_vien
~~~

**OID trong catalog:**

~~~text
Ví dụ: 18451
~~~

**Vị trí lưu trữ của relation:**

~~~text
Được PostgreSQL quản lý bằng các cấu trúc lưu trữ vật lý
và thông tin mapping tương ứng.
~~~

Một object có thể được đổi tên bằng:

~~~sql
-- Ví dụ lý thuyết trên môi trường thử:
-- ALTER TABLE catalog_lab.nhan_vien RENAME TO nhan_vien_moi;
~~~

khi đó tên thay đổi nhưng không đồng nghĩa đối tượng bị drop/recreate. Ngược lại, nếu `DROP TABLE` rồi `CREATE TABLE` cùng tên, object mới có thể nhận OID khác.

Các thao tác viết lại bảng hoặc index có thể thay đổi vị trí/tệp vật lý trong khi object vẫn có cùng identity ở mức catalog. `pg_class.relfilenode` không phải số OID để dùng thay tên bảng và không nên được lưu như khóa tham chiếu nghiệp vụ.

**Kết luận:** nếu công cụ migration cần biết “bảng logic đang tên gì” thì dùng tên có schema cùng lịch sử migration. Nếu một truy vấn system catalog cần nối metadata của table trong cùng snapshot, dùng OID/regclass phù hợp.

## 27. OID, cache metadata và hoạt động đồng thời

PostgreSQL cần tra cứu catalog khi phân tích và thực thi SQL. Để tránh đọc lại metadata từ đĩa mỗi lần, hệ thống có các cơ chế **cache metadata nội bộ**. DDL được thực hiện theo cơ chế giao dịch và PostgreSQL duy trì tính nhất quán cần thiết giữa những backend.

Ví dụ:

1. Session A bắt đầu đọc từ bảng `catalog_lab.nhan_vien`.
2. Session B muốn thực hiện một DDL thay đổi cấu trúc bảng.
3. PostgreSQL dùng lock, MVCC và cơ chế quản lý catalog phù hợp để tránh biến đổi cấu trúc làm câu lệnh đang chạy trở nên không an toàn.
4. Khi DDL được commit, các session khác có thể quan sát cấu trúc mới theo quy tắc transaction và invalidation nội bộ.

Không nên tự viết một cache OID kéo dài qua nhiều lần deploy rồi giả định mapping vẫn đúng. Một migration, dump/restore, drop/recreate hoặc restart trong những hoàn cảnh cụ thể có thể khiến việc sử dụng OID đã cache không còn hợp lệ.

### 27.1. Catalog query cũng chịu quy tắc transaction

Nếu bạn chạy các truy vấn metadata liên tiếp trong những transaction/snapshot khác nhau trong khi người khác đang tạo/xóa bảng, kết quả có thể thay đổi. Không dùng kết quả `SELECT` từ catalog làm khóa vĩnh viễn cho hệ thống bên ngoài.

Muốn triển khai migration an toàn, nên dùng công cụ migration, quyền và locking thích hợp thay vì chỉ “kiểm tra object tồn tại rồi tự thao tác không transaction” trong môi trường có cạnh tranh DDL.

## 28. Bảo mật khi truy vấn system catalog

Metadata thường chứa thông tin hữu ích cho DBA nhưng cũng có thể phơi lộ chi tiết cấu trúc hệ thống.

Cần hiểu:

- Một số catalog và view có giới hạn quyền hoặc che thông tin nhạy cảm.
- `pg_roles` được thiết kế để tra cứu role phù hợp hơn việc đọc trực tiếp các dữ liệu xác thực nhạy cảm.
- `information_schema` thường lọc thông tin dựa trên quyền của người đang kết nối.
- Có thể đọc tên bảng trong catalog nhưng **không có quyền SELECT dữ liệu bảng**.
- Hàm mô tả metadata và quyền truy vấn phải được sử dụng theo mô hình role đã cấp.
- Trên managed PostgreSQL, quyền superuser đầy đủ có thể bị hạn chế.

Ví dụ:

~~~sql
SELECT
    current_user,
    pg_catalog.has_schema_privilege(
        current_user,
        'catalog_lab',
        'USAGE'
    ) AS can_use_schema,
    pg_catalog.has_table_privilege(
        current_user,
        'catalog_lab.nhan_vien',
        'SELECT'
    ) AS can_read_table;
~~~

**OID không phải “đường tắt” vượt quyền**. Nếu ứng dụng không được cấp quyền đọc dữ liệu thì biết OID của bảng cũng không cho phép truy cập bảng đó.

Ngoài ra, không dùng tên schema/table từ input người dùng để ghép chuỗi SQL không được escape. Khi viết dynamic SQL trong code quản trị, dùng cơ chế quote identifier phù hợp hoặc hàm `format('%I', identifier)` trong ngữ cảnh PL/pgSQL an toàn và tham số hóa dữ liệu khi có thể.

## 29. Tránh sửa catalog trực tiếp

Những thao tác đúng:

~~~sql
ALTER TABLE catalog_lab.nhan_vien
ADD COLUMN ghi_chu TEXT;

COMMENT ON COLUMN catalog_lab.nhan_vien.ghi_chu
IS 'Ghi chú nội bộ';
~~~

PostgreSQL sẽ cập nhật các catalog liên quan theo cơ chế chính thức.

Những thao tác **không được làm**:

~~~sql
-- KHÔNG THỰC HIỆN: ví dụ nguy hiểm, chỉ để nhận diện.
-- UPDATE pg_catalog.pg_attribute
-- SET attname = 'ten_moi'
-- WHERE attrelid = 'catalog_lab.nhan_vien'::regclass
--   AND attname = 'ho_ten';

-- KHÔNG THỰC HIỆN:
-- DELETE FROM pg_catalog.pg_class
-- WHERE relname = 'nhan_vien';
~~~

Tự sửa catalog có thể bỏ qua các bước kiểm tra và cập nhật dependency, index, cache hay những thành phần khác. Nó không phải cách đổi tên bảng/cột hoặc xóa object hợp lệ.

Nếu cần đổi cột, dùng `ALTER TABLE ... RENAME COLUMN`. Nếu cần xóa bảng, dùng `DROP TABLE` sau khi đã hiểu dependency và có kế hoạch backup/phục hồi.

## 30. Các lỗi tư duy thường gặp

### Lỗi 1: “pg_class chỉ có bảng”

Không. `pg_class` chứa nhiều relation như table, index, view và sequence.

**Cách đúng:** lọc `relkind`, schema và tên relation theo mục đích.

### Lỗi 2: “OID là primary key toàn cục vĩnh viễn”

Không. OID là định danh nội bộ có phạm vi và vòng đời; không bảo đảm ổn định qua dump/restore, drop/recreate hoặc nhiều môi trường.

**Cách đúng:** dùng OID để JOIN catalog hiện tại; dùng tên/schema và migration cho nhận diện lâu dài.

### Lỗi 3: “Hai cột cùng kiểu oid thì JOIN được với nhau”

Không. Phải biết catalog nguồn và đích của từng OID.

**Cách đúng:** xem ý nghĩa của `relnamespace`, `attrelid`, `atttypid` hoặc cặp `classid/objid`.

### Lỗi 4: “Foreign key chỉ nằm trong pg_depend”

Không. Metadata FK chủ yếu được mô tả ở `pg_constraint` với `conrelid`, `confrelid`, `conkey` và `confkey`.

**Cách đúng:** dùng `pg_constraint` để hiểu ràng buộc hàng dữ liệu; `pg_depend` để phân tích dependency object.

### Lỗi 5: “View phụ thuộc bảng nên chỉ cần xem pg_class của view”

Không phải luôn đủ. View sử dụng rewrite rule và dependency của rule trong `pg_rewrite`/`pg_depend`.

**Cách đúng:** dùng `pg_get_viewdef` hoặc JOIN catalog phù hợp.

### Lỗi 6: “Các số attnum luôn là cột hiện hữu”

Không. Có system attributes và thông tin cột bị drop.

**Cách đúng:** thường lọc `attnum > 0 AND NOT attisdropped` khi cần danh sách cột người dùng.

### Lỗi 7: “pg_class.reltuples là COUNT(*)”

Không. `reltuples` là số hàng **ước lượng**.

**Cách đúng:** dùng thống kê để ước tính kế hoạch; `COUNT(*)` nếu cần số chính xác.

### Lỗi 8: “OID giống relfilenode”

Không. Identity relation và thông tin lưu trữ vật lý là những khái niệm khác nhau.

**Cách đúng:** không dùng đường dẫn/tên file nội bộ làm định danh nghiệp vụ.

### Lỗi 9: “Có catalog thì sửa metadata bằng UPDATE nhanh hơn ALTER”

Sai và nguy hiểm. Có thể làm hỏng metadata hoặc bỏ qua các kiểm tra nội bộ.

**Cách đúng:** sử dụng DDL và công cụ quản lý migration được hỗ trợ.

### Lỗi 10: “Biết OID thì bỏ qua phân quyền SQL”

Không. Quyền của role vẫn được PostgreSQL thực thi.

**Cách đúng:** xem `has_table_privilege` và cấu hình role.

### Lỗi 11: “information_schema và pg_catalog luôn cho cùng kết quả”

Không. Chúng có mục tiêu, mức chi tiết và quy tắc lọc theo quyền khác nhau.

**Cách đúng:** chọn nguồn phù hợp với truy vấn metadata đang thực hiện.

### Lỗi 12: “DROP CASCADE chỉ xóa một bảng”

Không. `CASCADE` có thể xóa các đối tượng phụ thuộc.

**Cách đúng:** tìm hiểu dependency và đánh giá phạm vi trước khi dùng, đặc biệt trên production.

## 31. Quy trình phân tích một đối tượng trong PostgreSQL

Khi cần biết một bảng hoặc view được liên kết như thế nào, có thể làm theo trình tự:

**Bước 1 — Xác định database và role đang kết nối.**

~~~sql
SELECT current_database(), current_user;
~~~

**Bước 2 — Tìm OID của relation bằng tên có schema.**

~~~sql
SELECT to_regclass('catalog_lab.nhan_vien');
~~~

**Bước 3 — Xem loại relation và schema.**

~~~sql
SELECT
    c.oid,
    c.relname,
    c.relkind,
    n.nspname
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

**Bước 4 — Xem cột và kiểu dữ liệu.** Dùng `pg_attribute` kết hợp `format_type`/`pg_type`.

**Bước 5 — Xem khóa và index.** Dùng `pg_constraint`, `pg_index`, `pg_get_constraintdef` và `pg_get_indexdef`.

**Bước 6 — Xem những đối tượng phụ thuộc.** Với view, tra `pg_rewrite`/`pg_depend`; với FK, tra `pg_constraint`; với partition, tra `pg_inherits`.

**Bước 7 — Xem quyền và comment.** Dùng hàm `has_table_privilege`, `obj_description` và `col_description` khi thích hợp.

**Bước 8 — Chỉ thực hiện DDL khi đã hiểu tác động.** Không chỉnh sửa trực tiếp `pg_catalog` hoặc dùng `CASCADE` theo thói quen.

## 32. Bài tập thực hành

### Bài 1 — Phân biệt ba nhóm dữ liệu

Hãy xếp những thành phần sau vào nhóm phù hợp: `catalog_lab.nhan_vien`, `pg_class`, `pg_stat_activity`, `pg_constraint`, `pg_stat_user_tables`.

**Gợi ý:** bảng nhân viên chứa dữ liệu nghiệp vụ; `pg_class` và `pg_constraint` chứa metadata; `pg_stat_activity` và `pg_stat_user_tables` phục vụ trạng thái/thống kê.

### Bài 2 — OID của bảng

Viết SQL lấy số OID và tên relation của `catalog_lab.nhan_vien`.

**Gợi ý:**

~~~sql
SELECT
    c.oid,
    c.oid::regclass AS relation_name
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

### Bài 3 — Schema chứa bảng

Viết SQL nối `pg_class` và `pg_namespace` để tìm schema của `nhan_vien`.

**Gợi ý:** `pg_class.relnamespace = pg_namespace.oid`.

### Bài 4 — Danh sách cột

Dùng `pg_attribute` liệt kê `attnum`, `attname` và kiểu dữ liệu của `catalog_lab.nhan_vien`, bỏ system attributes và cột đã drop.

**Gợi ý:** `attrelid = 'catalog_lab.nhan_vien'::regclass`, `attnum > 0`, `NOT attisdropped`, `format_type`.

### Bài 5 — Foreign key

Dùng `pg_constraint` xác định bảng nguồn và bảng đích của `fk_nhan_vien_phong_ban`. Tại sao `conrelid` khác `confrelid`?

**Gợi ý:** conrelid trỏ tới bảng `nhan_vien`, confrelid trỏ tới `phong_ban`.

### Bài 6 — Số thứ tự cột

Vì sao không thể hiểu `conkey = {2}` là “cột có OID bằng 2”?

**Gợi ý:** phần tử `conkey` là `attnum` trong quan hệ xác định bởi `conrelid`, không phải OID riêng của cột.

### Bài 7 — Index metadata

Dùng `pg_index` và `pg_class` liệt kê tất cả index của bảng nhân viên. Phân biệt `indexrelid` và `indrelid`.

**Gợi ý:** một bên là index relation, một bên là table được index.

### Bài 8 — Phụ thuộc của view

View `catalog_lab.v_nhan_vien` dùng hai bảng nào? Tại sao phải xét `pg_rewrite` khi dùng `pg_depend`?

**Gợi ý:** view dùng `nhan_vien` và `phong_ban`; dependency của view thường gắn với rule `_RETURN`.

### Bài 9 — Thay đổi tên và OID

Nếu dùng `ALTER TABLE ... RENAME TO`, tên thay đổi; nếu drop/recreate cùng tên, OID có thể thay đổi. Vậy nên lưu tên hay OID trong migration được dùng qua nhiều môi trường?

**Gợi ý:** lưu định danh logic dựa trên schema/tên và phiên bản migration; không hardcode OID.

### Bài 10 — Mô tả kiểu NUMERIC

Tại sao `pg_attribute.atttypid` chưa đủ để in ra `NUMERIC(12,2)`?

**Gợi ý:** còn `atttypmod` và quy tắc trình bày; dùng `format_type(atttypid, atttypmod)`.

### Bài 11 — DROP CASCADE

Một bảng được view tham chiếu. Nếu cố `DROP TABLE ... CASCADE`, đối tượng nào khác có nguy cơ bị xóa? Phân biệt với `ON DELETE CASCADE`.

**Gợi ý:** view hoặc object phụ thuộc khác có thể bị xóa ở mức schema; `ON DELETE CASCADE` tác động tới hàng dữ liệu theo foreign key.

### Bài 12 — Kiểm tra quyền

Viết SQL dùng `has_table_privilege` để xác định role hiện tại có quyền `SELECT` trên bảng nhân viên không.

**Gợi ý:** `has_table_privilege(current_user, 'catalog_lab.nhan_vien', 'SELECT')`.

### Bài 13 — Routine overload

Vì sao `regprocedure` thường thích hợp hơn một tên function trần khi có nhiều function cùng tên?

**Gợi ý:** cần danh sách kiểu đối số để nhận diện đúng signature.

### Bài 14 — Vai trò của information_schema

Khi xây một công cụ liệt kê cột cho nhiều hệ quản trị, nên thử `information_schema.columns` hay tự JOIN những catalog đặc thù PostgreSQL trước?

**Gợi ý:** `information_schema` thường có giao diện gần chuẩn SQL; `pg_catalog` cần khi dùng tính năng chi tiết của PostgreSQL.

### Bài 15 — Comment trên cột

Viết truy vấn đọc comment của `ho_ten` mà không hardcode số cột 3.

**Gợi ý:** JOIN `pg_attribute` hoặc lọc `attname = 'ho_ten'`, rồi dùng `col_description(attrelid, attnum)`.

## 33. Ghi nhớ

- **System catalog** là nơi PostgreSQL quản lý metadata về schema, relation, cột, type, index, constraint, view, function và dependency.
- **`pg_catalog`** là nguồn metadata đặc thù PostgreSQL; **`information_schema`** là lớp view metadata gần chuẩn SQL và có quy tắc lọc quyền riêng.
- **OID** là định danh nội bộ 4 byte cho nhiều loại object, hữu ích trong JOIN catalog nhưng không phải khóa nghiệp vụ bền vững hoặc định danh toàn cục giữa các server.
- **`regclass`, `regtype`, `regprocedure`** giúp ánh xạ tên/identity thành OID và hiển thị lại object dễ đọc.
- **`pg_namespace` ↔ `pg_class`** nối schema với relation.
- **`pg_class` ↔ `pg_attribute` ↔ `pg_type`** mô tả relation, cột và kiểu dữ liệu.
- **`pg_constraint`** mô tả ràng buộc dữ liệu, gồm `conrelid`, `confrelid`, `conkey`, `confkey` để diễn giải foreign key.
- **`pg_index`** nối index relation với table và cung cấp metadata index.
- **`pg_rewrite` + `pg_depend`** giúp hiểu nhiều phụ thuộc của view; dependency object không đồng nghĩa ràng buộc foreign key.
- **`pg_description`** gắn comment với object hoặc cột; **`pg_proc`** mô tả routine; **`pg_inherits`** liên kết các relation kế thừa/partition.
- **OID, số thứ tự cột và tên file vật lý là những khái niệm khác nhau**; không trộn chúng thành một định danh.
- **Không sửa trực tiếp system catalog**, không dùng `DROP ... CASCADE` khi chưa hiểu toàn bộ đối tượng bị tác động.
- Khi tự khảo sát database, ưu tiên tên object có schema, hàm như `pg_get_constraintdef`, `pg_get_indexdef`, `pg_get_viewdef` và những truy vấn catalog chỉ đọc.

Hiểu system catalog và OID là bước quan trọng để nhìn PostgreSQL như **một hệ thống đối tượng quan hệ có cấu trúc và quy tắc phụ thuộc**, thay vì chỉ là nơi lưu các hàng dữ liệu. Khi biết mỗi catalog mô tả điều gì và các OID nối chúng với nhau ra sao, bạn có thể tự giải thích vì sao một khóa ngoại tồn tại, một view không thể bị bỏ phụ thuộc, một index phục vụ bảng nào và một thay đổi schema có thể ảnh hưởng tới những đối tượng nào.
