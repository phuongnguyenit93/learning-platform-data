# Quyền sở hữu, quyền cấp lại và kế thừa vai trò theo hệ quản trị trong SQL

Một tài khoản có thể đọc bảng mà không được sửa, có thể sửa dữ liệu mà không được xóa bảng, hoặc được phép dùng quyền đọc **thông qua vai trò** mà không hề nhận `GRANT SELECT` trực tiếp. Một người có quyền đọc cũng không nhất thiết có quyền **cấp lại** quyền đọc cho người khác.

Chủ đề **“Quyền sở hữu, quyền cấp lại và kế thừa vai trò theo hệ quản trị”** trong chương **Quyền và SQL an toàn** thuộc module **Database SQL** tập trung vào ba câu hỏi:

1. **Ownership:** ai là chủ sở hữu (*owner*) của database object, và ownership khác gì một quyền như `SELECT` hay `UPDATE`?
2. **Delegation:** ai có thể cấp lại quyền trên bảng hoặc cấp tư cách thành viên của một role cho người khác?
3. **Inheritance:** một user được cấp role có tự hưởng các quyền của role đó không, hay phải kích hoạt/chuyển sang role trước?

~~~text
                              Chủ sở hữu bảng
                              lab375_owner
                                     │
                  GRANT SELECT ON lab375.orders
                                     ▼
                              lab375_reader
                                     │
                    GRANT lab375_reader TO Alice
                             INHERIT TRUE
                                     ▼
                              Alice đọc được

               Nhưng quyền cấp lại là đường khác:
   owner -- SELECT WITH GRANT OPTION --> delegator
   delegator -------- SELECT ----------> Carol
~~~

Ví dụ chính dùng **PostgreSQL 16 trở lên**, nơi một membership có các tùy chọn `INHERIT`, `SET` và `ADMIN` riêng. Các phần sau đối chiếu PostgreSQL cũ hơn, SQL Server, MySQL/MariaDB, Oracle và SQLite. Đây là bài học về mô hình quyền: mọi ví dụ tạo role/schema cần **môi trường lab được phép**, không chạy trực tiếp trong production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **owner**, **grantor**, **grantee**, **member role** và **login role**.
- Nói rõ `GRANT ALL PRIVILEGES` không tự chuyển ownership.
- Dùng `GRANT`/`REVOKE` cho bảng, schema, sequence, function và role.
- Phân biệt `WITH GRANT OPTION` (cấp lại quyền đối tượng) với `WITH ADMIN OPTION` (quản trị membership role).
- Hiểu hệ quả của `INHERIT TRUE/FALSE`, `SET TRUE/FALSE`, `ADMIN TRUE/FALSE` trong PostgreSQL 16+.
- Biết tại sao `SET ROLE` không chỉ đơn giản là “cộng tất cả quyền”.
- Phân tích role graph nhiều tầng, các đường cấp quyền song song và hiệu lực của `CASCADE`/`RESTRICT`.
- Hiểu `REVOKE` PostgreSQL không tương đương `DENY` SQL Server.
- Thiết kế owner role không đăng nhập, reader/writer group role và service account ít quyền.
- Cấp quyền cho bảng hiện tại và bảng tương lai bằng `GRANT` cùng `ALTER DEFAULT PRIVILEGES`.
- Kiểm tra quyền hiệu lực bằng `has_table_privilege`, `has_schema_privilege`, `pg_has_role` và catalog.
- Nhận ra khác biệt về role activation, ownership, sequence, view/function, Row-Level Security giữa các DBMS.
- Giải các bài tập phân quyền, thu hồi, kế thừa và kiểm tra sai cấu hình.

## 2. Năm thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Không đồng nghĩa với |
|---|---|---|
| **Owner** | Chủ sở hữu một bảng, schema, hàm hoặc đối tượng | Người vừa INSERT một hàng |
| **Grantee** | User/role được nhận một privilege | Có quyền cấp tiếp privilege |
| **Grantor** | Role được ghi nhận là nguồn cấp một privilege hoặc membership | Luôn là người đăng nhập hiện tại theo tên hiển thị |
| **Member** | Một role đã được gán membership của role khác | Tự động có toàn quyền của role đó trong mọi DBMS |
| **Role administrator** | Principal có quyền cấp/thu hồi membership của role | Chủ sở hữu của mọi bảng mà role có thể SELECT |

Ví dụ:

~~~sql
GRANT SELECT ON TABLE sales.orders TO report_reader;
~~~

Câu này cấp **quyền SELECT** cho `report_reader` trên một bảng, không tạo user đăng nhập và không tự trao quyền cấp lại.

~~~sql
GRANT report_reader TO analyst_01;
~~~

Câu này gán **membership** trong role `report_reader` cho `analyst_01`. Người nhận có sử dụng được SELECT ngay hay không phụ thuộc mô hình kế thừa/kích hoạt role của hệ quản trị.

### 2.1. Đối tượng và quyền

Một hệ quản trị không chỉ có quyền SELECT trên bảng. Nó còn có:

- Quyền kết nối vào database.
- Quyền sử dụng hoặc tạo đối tượng trong schema.
- Quyền đọc/ghi bảng hoặc cột.
- Quyền dùng sequence.
- Quyền gọi function/procedure.
- Quyền quản trị role và ownership.
- Quyền tạo, sửa cấu trúc hoặc vận hành đối tượng trong những tình huống nhất định.

**Kiểm tra quyền phải xét đúng thao tác và đúng đối tượng**, không chỉ xem một role có chữ “admin” trong tên hay không.

## 3. PostgreSQL: user và group đều là ROLE

PostgreSQL thống nhất khái niệm user và group thành **role**. Role có thể có thuộc tính `LOGIN` hoặc `NOLOGIN`.

~~~sql
CREATE ROLE example_owner NOLOGIN;
CREATE ROLE example_reader NOLOGIN;
CREATE ROLE example_user LOGIN;
~~~

- Role **NOLOGIN** thường phù hợp làm owner hoặc nhóm privilege.
- Role **LOGIN** có thể dùng để đăng nhập khi đáp ứng cấu hình xác thực.
- Một role NOLOGIN vẫn có thể là mục tiêu `SET ROLE` nếu principal hiện tại được phép chuyển sang role ấy.
- Role và các membership tồn tại trong phạm vi cụm PostgreSQL, còn grants trên bảng/schema phụ thuộc đối tượng cụ thể.

Ngoài ra còn có những thuộc tính đặc biệt như `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `BYPASSRLS`. **Không được** coi các thuộc tính quản trị này là quyền SELECT trên bảng được thừa hưởng như nhau trong mọi trường hợp; PostgreSQL có quy tắc riêng đối với các role attributes đặc biệt.

### 3.1. Một role có thể là user lẫn nhóm

Không có một ranh giới cứng “user không thể làm group” trong cấu trúc PostgreSQL. Để vận hành dễ hiểu, thông thường thiết kế:

~~~text
owner role:       owns schema/tables     NOLOGIN
reader role:      SELECT                NOLOGIN
writer role:      INSERT/UPDATE         NOLOGIN
application user: LOGIN, nhận memberships
migration user:   LOGIN, có đường SET ROLE tới owner được kiểm soát
~~~

Việc **tách trách nhiệm** quan trọng hơn tên role.

## 4. Ownership khác quyền được GRANT

Khi tạo bảng, role thực thi `CREATE TABLE` thường trở thành **owner**.

~~~sql
CREATE TABLE sales.orders (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL
);
~~~

Giả sử `current_user = sales_owner` lúc chạy lệnh, bảng thuộc sở hữu `sales_owner`.

### 4.1. Owner có các khả năng đặc biệt

Owner trong PostgreSQL có khả năng quản lý định nghĩa đối tượng, gồm những thao tác phù hợp như `ALTER TABLE`, `DROP TABLE` và cấp quyền cho người khác. **DROP/ALTER định nghĩa không phải quyền SELECT/UPDATE có thể GRANT theo cách thông thường**.

Không có ý nghĩa tương đương đơn giản cho:

~~~sql
GRANT DROP ON TABLE sales.orders TO app_user;
~~~

Đây **không phải** cú pháp PostgreSQL để trao quyền DROP. Muốn thao tác theo ownership, cần sở hữu đối tượng hoặc có quyền thông qua membership/đặc quyền phù hợp.

### 4.2. GRANT ALL không biến người nhận thành owner

~~~sql
GRANT ALL PRIVILEGES
ON TABLE sales.orders
TO app_writer;
~~~

Lệnh cấp các privilege có thể GRANT của loại TABLE; nó **không chuyển owner** và không đồng nghĩa app_writer được `DROP TABLE`.

### 4.3. Owner mặc định có quyền thông thường, nhưng có chi tiết quan trọng

PostgreSQL mặc định cấp owner những privilege trên đối tượng. Owner có thể chủ động REVOKE một số quyền thao tác thông thường của chính mình. Tuy vậy, quyền sở hữu để sửa/xóa định nghĩa và quyền cấp lại có tính chất đặc biệt của owner.

Ngoài ra, quyền của owning role có thể truyền qua membership trong những ngữ cảnh thích hợp. Vì thế **không nên cấp membership của owner role bừa bãi** cho các tài khoản ứng dụng.

### 4.4. Owner của schema không tự là owner của mọi bảng

Một schema và một bảng bên trong có thể có **hai owner khác nhau**. Quyền sở hữu schema giúp quản lý schema, nhưng không tự chuyển quyền sở hữu các bảng do role khác tạo. Đây là một khác biệt nền tảng khi thiết kế ứng dụng nhiều nhóm.

## 5. Các quyền đối tượng trong PostgreSQL

| Loại đối tượng | Privileges thường gặp | Ý nghĩa ví dụ |
|---|---|---|
| DATABASE | `CONNECT`, `CREATE`, `TEMPORARY` | Kết nối, tạo schema, dùng bảng tạm |
| SCHEMA | `USAGE`, `CREATE` | Truy cập tên đối tượng, tạo đối tượng |
| TABLE | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER` | Đọc/ghi, tham chiếu, tạo trigger |
| TABLE COLUMN | `SELECT`, `INSERT`, `UPDATE`, `REFERENCES` | Quyền cho từng cột |
| SEQUENCE | `USAGE`, `SELECT`, `UPDATE` | Các hoạt động sequence tương ứng |
| FUNCTION/PROCEDURE | `EXECUTE` | Gọi routine |
| TYPE/DOMAIN | `USAGE` | Sử dụng kiểu theo quy tắc |
| TABLESPACE | `CREATE` | Tạo đối tượng tại tablespace khi đủ điều kiện |

PostgreSQL hiện hành còn có `MAINTAIN` trên quan hệ cho một số thao tác bảo trì; khả năng này và các cú pháp khác nhau theo phiên bản. Không sao chép nguyên danh sách privilege sang SQL Server hoặc MySQL.

### 5.1. Schema USAGE và table SELECT phải xét riêng

~~~sql
GRANT SELECT ON TABLE sales.orders TO report_reader;
~~~

Chỉ câu này có thể chưa đủ để role truy cập đối tượng trong schema `sales`. Thông thường còn cần:

~~~sql
GRANT USAGE ON SCHEMA sales TO report_reader;
~~~

Ngược lại, `USAGE ON SCHEMA` **không** cấp SELECT trên mọi bảng thuộc schema.

### 5.2. Database CONNECT và kết nối thực

Để đăng nhập, principal còn cần xác thực hợp lệ, quyền CONNECT và các điều kiện ở tầng server. Một query có đầy đủ SELECT privilege vẫn không thể chạy nếu user không kết nối được tới database.

### 5.3. Sequence có quyền riêng

Quyền INSERT trên bảng chứa cột `SERIAL` không tự cấp các quyền cần thiết trên sequence được dùng bởi `nextval`. Có thể cần:

~~~sql
GRANT USAGE ON SEQUENCE sales.orders_id_seq
TO app_writer;
~~~

`GENERATED ... AS IDENTITY` có một số ngữ nghĩa/kiểm tra quyền khác `SERIAL`; cần kiểm tra kiểu cột và PostgreSQL version thay vì coi tất cả trường hợp sinh ID giống nhau.

## 6. Thiết lập mô hình thực hành an toàn

Chủ đề ownership/membership cần role và schema thực, nên ví dụ dùng **schema sandbox** thay vì TEMP TABLE. Phải có database thử nghiệm và tài khoản quản trị lab được phép tạo role, schema và SET ROLE. **Không chạy các lệnh này trên production.**

### 6.1. Tạo owner, group và principal mô phỏng

~~~sql
CREATE ROLE lab375_owner NOLOGIN;
CREATE ROLE lab375_reader NOLOGIN;
CREATE ROLE lab375_writer NOLOGIN;
CREATE ROLE lab375_delegator NOLOGIN;

CREATE ROLE lab375_alice NOLOGIN;
CREATE ROLE lab375_bob NOLOGIN;
CREATE ROLE lab375_carol NOLOGIN;
~~~

Trong lab, các principal Alice/Bob/Carol là NOLOGIN để người quản trị kiểm thử qua `SET ROLE` hoặc các hàm kiểm tra quyền. Nếu muốn đăng nhập thật, cần tạo role LOGIN và cấu hình xác thực an toàn, không dùng password hardcode trong tài liệu.

### 6.2. Schema do owner role nắm giữ

~~~sql
CREATE SCHEMA lab375 AUTHORIZATION lab375_owner;
~~~

Để chỉ định chủ sở hữu schema khác bản thân, người thực thi cần quyền tương ứng. Hãy dùng tài khoản quản trị sandbox đủ quyền.

### 6.3. Tạo bảng dưới identity của owner

Khi tài khoản quản trị được phép SET ROLE sang owner:

~~~sql
SET ROLE lab375_owner;

CREATE TABLE lab375.orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO lab375.orders
    (id, customer_id, status, amount)
VALUES
    (101, 10, 'NEW', 100000),
    (102, 20, 'PAID', 250000),
    (103, 10, 'PAID', 180000);

RESET ROLE;
~~~

Bảng `lab375.orders` bây giờ thuộc role `lab375_owner`, không phải Alice, Bob hay reader/writer.

**Điều kiện thực thi:** nếu tài khoản quản trị không có quyền SET ROLE sang `lab375_owner`, lệnh SET ROLE thất bại. Hãy cấu hình quyền từ người quản trị lab, không bỏ qua lỗi và tưởng lệnh CREATE TABLE đã chạy dưới owner mong muốn.

### 6.4. Phân quyền reader

~~~sql
GRANT USAGE ON SCHEMA lab375
TO lab375_reader;

GRANT SELECT ON TABLE lab375.orders
TO lab375_reader;
~~~

### 6.5. Phân quyền writer giới hạn

~~~sql
GRANT USAGE ON SCHEMA lab375
TO lab375_writer;

GRANT SELECT (id, status)
ON TABLE lab375.orders
TO lab375_writer;

GRANT INSERT
ON TABLE lab375.orders
TO lab375_writer;

GRANT UPDATE (status)
ON TABLE lab375.orders
TO lab375_writer;
~~~

Writer trong ví dụ không được cấp `DELETE`, `TRUNCATE` hay quyền UPDATE cột `amount`.

Quyền SELECT (id, status) hữu ích cho các câu UPDATE có `WHERE id = ?` và kiểm tra status. Một service thực còn có thể cần thêm quyền theo chính xác biểu thức SQL mà nó chạy.

## 7. GRANT role TO role: cấp tư cách thành viên

PostgreSQL 16+ cho phép khai báo các tùy chọn membership trực tiếp:

~~~sql
GRANT lab375_reader TO lab375_alice
WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;

GRANT lab375_writer TO lab375_bob
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

Ý nghĩa:

- **Alice** tự dùng quyền do reader cấp (theo inheritance), không có quyền SET ROLE reader qua cạnh ấy và không thể cấp membership reader cho người khác.
- **Bob** là member writer nhưng không tự kế thừa quyền writer. Bob có thể SET ROLE writer theo cạnh này; Bob không được quản lý membership writer.
- **Carol** chưa nhận membership.

### 7.1. Ma trận kỳ vọng

| Principal | Quyền từ membership khi chưa SET ROLE | Khả năng SET ROLE |
|---|---|---|
| Alice | SELECT qua reader, bao gồm USAGE schema | Không SET reader qua cạnh SET FALSE |
| Bob | Không tự dùng writer vì INHERIT FALSE | Có thể SET writer |
| Carol | Không có quyền qua nhóm lab | Không có membership tương ứng |
| lab375_owner | Quyền owner trên bảng/schema | Không cần membership để quản lý đối tượng của mình |

Kết quả thực tế có thể khác nếu principal còn các grants khác, membership khác, PUBLIC grants hoặc đặc quyền admin.

### 7.2. Alice đọc được qua role

Trong session quản trị lab được phép SET ROLE Alice:

~~~sql
SET ROLE lab375_alice;

SELECT id, customer_id, status, amount
FROM lab375.orders
ORDER BY id;

RESET ROLE;
~~~

Kết quả dự kiến có ba đơn 101, 102, 103.

### 7.3. Bob trước SET ROLE

Nếu Bob không có grant khác, việc chạy `SELECT` dưới role Bob khi `INHERIT FALSE` có thể báo thiếu quyền dù role writer có SELECT(id,status). Bob phải dùng đường `SET ROLE lab375_writer` trong session được phép hoặc thay đổi membership sang INHERIT TRUE.

### 7.4. Đừng kiểm tra SET ROLE của Bob bằng session admin rồi nhầm kết quả

Trong PostgreSQL, quyền SET ROLE dựa trên **session user gốc** và các đường SET option hợp lệ. Nếu một superuser đăng nhập rồi chuyển lần lượt sang Bob/Writer, việc chuyển thành công không chứng minh một session **đăng nhập thật sự là Bob** được chuyển giống vậy.

Để kiểm tra quyền SET của Bob mà không tạo tài khoản đăng nhập riêng, dùng:

~~~sql
SELECT pg_has_role(
    'lab375_bob',
    'lab375_writer',
    'SET'
) AS bob_can_set_writer;
~~~

## 8. WITH GRANT OPTION: cấp lại quyền trên đối tượng

Giả sử muốn một người quản lý báo cáo được phép tiếp tục cấp quyền đọc bảng cho người khác:

~~~sql
GRANT USAGE ON SCHEMA lab375
TO lab375_delegator;

GRANT SELECT ON TABLE lab375.orders
TO lab375_delegator
WITH GRANT OPTION;
~~~

`WITH GRANT OPTION` cho phép delegator cấp lại **SELECT trên đúng đối tượng** theo các quy tắc PostgreSQL.

Trong session có quyền SET ROLE delegator:

~~~sql
SET ROLE lab375_delegator;

GRANT SELECT ON TABLE lab375.orders
TO lab375_carol;

RESET ROLE;
~~~

Nếu muốn Carol dùng quyền SELECT bằng tên bảng, còn cần schema USAGE:

~~~sql
GRANT USAGE ON SCHEMA lab375 TO lab375_carol;
~~~

### 8.1. Không nhầm GRANT OPTION với owner

Delegator có thể cấp lại SELECT, nhưng không tự được `DROP TABLE`, `ALTER TABLE` hoặc `GRANT DELETE` nếu không có các khả năng riêng đó.

### 8.2. GRANT SELECT thường không cấp lại được

Nếu Alice chỉ có:

~~~sql
GRANT SELECT ON TABLE lab375.orders
TO lab375_alice;
~~~

mà không có grant option/đường sở hữu phù hợp, Alice không được phép cấp lại SELECT đơn thuần chỉ vì có thể đọc bảng.

### 8.3. Một quyền không tự cho cấp mọi quyền

`WITH GRANT OPTION` gắn với những privilege được cấp trên loại đối tượng tương ứng. Có grant option cho SELECT không có nghĩa được cấp lại UPDATE, TRIGGER, TRUNCATE hoặc ownership.

### 8.4. Không cấp GRANT OPTION cho PUBLIC trong PostgreSQL

PostgreSQL cho phép `GRANT SELECT ON table TO PUBLIC` nhưng **không hỗ trợ cấp grant option cho pseudo-role PUBLIC** theo cùng cách các role cụ thể.

## 9. WITH ADMIN OPTION: quản lý membership role

Đây là một **loại cấp lại khác**:

~~~sql
GRANT lab375_reader TO lab375_delegator
WITH ADMIN TRUE, INHERIT FALSE, SET FALSE;
~~~

Khi đủ điều kiện PostgreSQL, delegator có khả năng cấp/thu hồi membership của `lab375_reader` cho principal khác. Nhưng:

- `INHERIT FALSE` nghĩa là không tự thừa hưởng quyền reader qua cạnh này.
- `SET FALSE` nghĩa là không được chuyển sang reader qua cạnh này.
- `ADMIN TRUE` nghĩa là có khả năng quản lý membership.

### 9.1. Hai OPTION khác nhau

| Cú pháp | Khả năng |
|---|---|
| `GRANT SELECT ON orders TO a` | Đọc bảng |
| `GRANT SELECT ON orders TO a WITH GRANT OPTION` | Đọc và cấp lại SELECT |
| `GRANT reader TO a` | Nhận membership reader; cách sử dụng tùy INHERIT/SET |
| `GRANT reader TO a WITH ADMIN OPTION` | Có thể quản lý membership reader |
| `ALTER TABLE orders OWNER TO a` | Chuyển owner khi đủ điều kiện |

Người có ADMIN OPTION của reader có thể mở rộng số người sử dụng reader bằng cách cấp membership, dù họ không được cấp SELECT WITH GRANT OPTION trực tiếp. Đây là một khả năng nhạy cảm cần giám sát.

### 9.2. ADMIN OPTION không phải tên khác của CREATEROLE

`CREATEROLE` là một thuộc tính quản trị PostgreSQL với các điều kiện, giới hạn và thay đổi theo phiên bản. `ADMIN OPTION` là quyền trên một membership role cụ thể. Không thay hai khái niệm này cho nhau.

## 10. PostgreSQL 16+: ba tùy chọn INHERIT, SET, ADMIN

Một role membership có thể viết:

~~~sql
GRANT granted_role TO member_role
WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;
~~~

### 10.1. Diễn giải

| Option | TRUE | FALSE |
|---|---|---|
| `INHERIT` | Quyền từ granted role tự có hiệu lực qua đường membership này | Không tự hưởng quyền qua cạnh này |
| `SET` | Cho phép chuyển sang granted role qua đường hợp lệ | Không chuyển role qua cạnh này |
| `ADMIN` | Cho phép quản lý việc cấp/thu hồi membership của granted role | Không quản lý membership nhờ cạnh này |

**Ba tùy chọn độc lập về ý nghĩa.** Có INHERIT không nhất thiết có SET; có SET không nhất thiết có ADMIN.

### 10.2. Các tổ hợp hay gặp

| INHERIT | SET | ADMIN | Ngữ nghĩa điển hình |
|---|---|---|---|
| TRUE | FALSE | FALSE | Tự dùng quyền, không chuyển identity hoặc quản lý thành viên |
| FALSE | TRUE | FALSE | Muốn dùng quyền thì SET ROLE |
| TRUE | TRUE | FALSE | Tự dùng và có thể chuyển role, không quản lý membership |
| FALSE | FALSE | TRUE | Quản lý membership nhưng không tự dùng quyền qua cạnh |
| FALSE | FALSE | FALSE | Có membership cấu trúc nhưng không dùng quyền qua cạnh này |
| TRUE | TRUE | TRUE | Cả dùng, chuyển identity và quản lý membership |

### 10.3. Giá trị mặc định

Theo PostgreSQL 16+:

- `ADMIN` mặc định FALSE.
- `SET` mặc định TRUE.
- `INHERIT` lúc tạo cạnh thường lấy từ thuộc tính INHERIT/NOINHERIT của **role nhận membership**, trừ khi chỉ rõ.

Đối với ứng dụng nhạy cảm, **đặt các option tường minh** để tránh suy luận sai mặc định.

### 10.4. Khác với PostgreSQL 15 trở về trước

Ở các bản PostgreSQL cũ hơn 16, cơ chế role inheritance và việc theo dõi phụ thuộc khi thu hồi ADMIN OPTION **khác mô hình membership options mới**. Không chạy nguyên cú pháp `WITH INHERIT FALSE, SET TRUE` ở PostgreSQL 15 rồi tưởng sẽ được hỗ trợ tương tự.

### 10.5. ALTER ROLE NOINHERIT khác sửa một cạnh

~~~sql
ALTER ROLE lab375_bob NOINHERIT;
~~~

đặt thuộc tính role, ảnh hưởng cách hình thành những membership mặc định về sau theo quy tắc PostgreSQL. Nó **không tự sửa mọi membership options đã lưu**. Muốn thay option của cạnh Bob → writer:

~~~sql
GRANT lab375_writer TO lab375_bob
WITH INHERIT FALSE;
~~~

Có thể sửa membership bằng cú pháp `REVOKE INHERIT OPTION FOR` trên PostgreSQL 16+, tương đương mục tiêu đặt FALSE.

## 11. Role graph nhiều tầng

Giả sử:

~~~text
alice
  │  INHERIT TRUE
  ▼
reporting
  │  INHERIT TRUE
  ▼
reader
  │
  └── SELECT orders
~~~

Nếu hai cạnh đều INHERIT TRUE, Alice có thể tự hưởng quyền của reader.

Ví dụ:

~~~sql
CREATE ROLE lab375_reporting NOLOGIN;

GRANT lab375_reader TO lab375_reporting
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab375_reporting TO lab375_alice
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;
~~~

Nếu đổi cạnh reporting → reader sang `INHERIT FALSE`, đường tự kế thừa qua reporting bị ngắt. Nhưng nếu Alice còn **membership trực tiếp** của reader từ phần 7, quyền đọc vẫn có thể tồn tại qua đường trực tiếp.

### 11.1. SET ROLE xuyên nhiều tầng

Một session có thể SET tới role gián tiếp theo đường membership mà **mỗi cạnh có SET TRUE**. Một cạnh SET FALSE có thể chặn đường đó, trừ khi có đường khác cho phép.

### 11.2. Nhiều đường song song

~~~text
                  ┌── reader trực tiếp ──────┐
alice ────────────┤                         ├── SELECT
                  └── reporting → reader ───┘
~~~

Thu hồi một cạnh **không đồng nghĩa** ngắt mọi đường. Đây là lý do phải xem toàn bộ role graph khi điều tra quyền.

### 11.3. PostgreSQL ngăn membership vòng

PostgreSQL không cho tạo vòng role membership. Những hệ quản trị khác có quy tắc riêng; không suy luận mọi DBMS đều giống vậy.

## 12. SET ROLE đổi identity hiệu lực

~~~sql
SELECT session_user, current_user, current_role;

SET ROLE lab375_writer;

SELECT session_user, current_user, current_role;

RESET ROLE;
~~~

Trong PostgreSQL:

- `session_user` thường đại diện role đăng nhập ban đầu.
- `current_user` và `current_role` thay đổi sau SET ROLE.
- Quyền của câu SQL thường được kiểm tra theo current role và đường kế thừa liên quan.
- Quyền chỉ có trên role đăng nhập gốc có thể **không còn hiệu lực** sau khi chuyển identity sang một role khác.
- `RESET ROLE` khôi phục cấu hình role theo ngữ nghĩa session.

**Đừng diễn giải SET ROLE như một phép cộng quyền không giới hạn.** Nó thay đổi identity dùng kiểm tra quyền.

### 12.1. Khi dùng connection pool

Nếu một request trong ứng dụng `SET ROLE` rồi trả connection về pool mà không khôi phục trạng thái an toàn, request khác có thể thừa hưởng context không mong muốn. Cần cơ chế đảm bảo reset/đóng connection hoặc quản lý session state rõ ràng.

### 12.2. Kiểm tra quyền SET của role thật

Không mô phỏng SET của Alice/Bob hoàn toàn bằng superuser rồi cho rằng kết quả thể hiện chính sách trên các principal. Sử dụng kết nối thực sự đăng nhập bằng principal hoặc:

~~~sql
SELECT pg_has_role(
    'lab375_bob',
    'lab375_writer',
    'SET'
);
~~~

## 13. Cảnh báo quan trọng: INHERIT TRUE, SET FALSE với owning role

Một cách cấp như:

~~~sql
GRANT sensitive_owner TO employee
WITH INHERIT TRUE, SET FALSE;
~~~

có thể **không tạo hàng rào an toàn** nếu `sensitive_owner` sở hữu các SQL object mà employee có thể thao tác nhờ quyền kế thừa. PostgreSQL cảnh báo những tình huống role kế thừa quyền owner có thể thao tác object/hàm để đạt hiệu ứng không mong muốn.

Khuyến nghị:

- Tách **owning role NOLOGIN** khỏi các group roles chuyên chứa SELECT/UPDATE.
- Đừng để group role được kế thừa mà SET bị cấm sở hữu những function/bảng nhạy cảm không cần thiết.
- Không cấp membership owner cho application role chỉ để “sửa permission denied”.
- Kiểm tra cả quyền CREATE schema và SECURITY DEFINER/search_path khi đánh giá rủi ro.

## 14. REVOKE không phải lệnh cấm tuyệt đối trong PostgreSQL

Nếu Alice nhận SELECT theo hai nguồn:

~~~text
owner ── GRANT SELECT trực tiếp ───────► Alice
      └─ GRANT SELECT cho reader ────► Alice (membership)
~~~

và owner chạy:

~~~sql
REVOKE SELECT ON TABLE lab375.orders
FROM lab375_alice;
~~~

Alice **có thể vẫn đọc được** qua reader.

### 14.1. Quyền từ nhiều nguồn

Một principal có thể có quyền từ:

- GRANT trực tiếp.
- Role membership INHERIT.
- Quyền sau SET ROLE.
- Pseudo-role PUBLIC.
- Column-level grants.
- Ownership hoặc superuser.
- Đường gián tiếp qua view/function được cấp quyền.

Bởi vậy, khi một REVOKE không làm mất quyền hiệu lực, cần điều tra **tất cả nguồn**, thay vì lặp REVOKE cùng câu.

### 14.2. REVOKE table privilege không giống REVOKE một cột

Nếu Alice đã được SELECT cả bảng, sau đó:

~~~sql
REVOKE SELECT (amount) ON TABLE lab375.orders
FROM lab375_alice;
~~~

không tự cấm cô ấy đọc `amount`: SELECT cấp ở cấp bảng vẫn tồn tại. Muốn chỉ cấp một vài cột thì cần thiết kế column grants hoặc view đúng ngay từ đầu.

### 14.3. Khác với SQL Server DENY

PostgreSQL không có một cơ chế `DENY SELECT ON ...` tương đương T-SQL để phủ định một cách độc lập mọi GRANT. `REVOKE` đơn thuần là thu hồi đường grant được chỉ định.

## 15. REVOKE GRANT OPTION FOR SELECT

Giả sử delegator có:

~~~sql
GRANT SELECT ON TABLE lab375.orders
TO lab375_delegator
WITH GRANT OPTION;
~~~

Muốn chỉ lấy lại **khả năng cấp tiếp**, không nhất thiết lấy quyền đọc:

~~~sql
REVOKE GRANT OPTION FOR SELECT
ON TABLE lab375.orders
FROM lab375_delegator;
~~~

Sau thao tác phù hợp, delegator có thể vẫn được SELECT nhưng không còn grant option theo đường này.

### 15.1. Hai kiểu REVOKE

| Câu lệnh | Tác động chính |
|---|---|
| `REVOKE SELECT ... FROM role` | Thu hồi quyền SELECT được grant theo phạm vi tương ứng |
| `REVOKE GRANT OPTION FOR SELECT ... FROM role` | Thu hồi khả năng cấp lại SELECT, có thể giữ quyền đọc |

Nếu có grant phụ thuộc, `CASCADE` và `RESTRICT` trở nên quan trọng.

## 16. CASCADE và RESTRICT khi quyền được cấp theo chuỗi

~~~text
owner -- SELECT WITH GRANT OPTION --> Alice
Alice ---------- SELECT ----------> Bob
~~~

Để thực hành riêng không ảnh hưởng `lab375.orders`, tạo một bảng:

~~~sql
SET ROLE lab375_owner;

CREATE TABLE lab375.grant_chain (
    id INTEGER PRIMARY KEY,
    note TEXT
);

INSERT INTO lab375.grant_chain
VALUES (1, 'dữ liệu thử cấp quyền');

GRANT SELECT ON TABLE lab375.grant_chain
TO lab375_alice WITH GRANT OPTION;

GRANT USAGE ON SCHEMA lab375
TO lab375_alice, lab375_bob;

RESET ROLE;
~~~

Từ session có quyền `SET ROLE lab375_alice`:

~~~sql
SET ROLE lab375_alice;

GRANT SELECT ON TABLE lab375.grant_chain
TO lab375_bob;

RESET ROLE;
~~~

### 16.1. RESTRICT

~~~sql
REVOKE GRANT OPTION FOR SELECT
ON TABLE lab375.grant_chain
FROM lab375_alice
RESTRICT;
~~~

Nếu có grant phụ thuộc của Bob, PostgreSQL có thể từ chối thu hồi vì không được hủy các quyền phụ thuộc theo chế độ RESTRICT.

### 16.2. CASCADE

~~~sql
REVOKE GRANT OPTION FOR SELECT
ON TABLE lab375.grant_chain
FROM lab375_alice
CASCADE;
~~~

Hệ quản trị có thể thu hồi những grant phụ thuộc thuộc chain tương ứng. Bob có thể mất SELECT **qua Alice**, còn Alice vẫn giữ SELECT nếu chỉ grant option bị thu hồi.

### 16.3. Bob có hai nguồn SELECT thì sao?

Nếu Bob cũng được owner GRANT SELECT trực tiếp, thu hồi chain qua Alice không nhất thiết làm Bob mất quyền đọc. Các grants độc lập khác có thể giữ quyền hiệu lực.

**Không chạy CASCADE trong production mà không khảo sát grants phụ thuộc**; nó có thể gây gián đoạn cho những người nhận quyền gián tiếp.

## 17. REVOKE ADMIN OPTION và membership options

Đối với role:

~~~sql
GRANT lab375_reader TO lab375_delegator
WITH ADMIN TRUE, INHERIT FALSE, SET FALSE;
~~~

Thu hồi riêng quyền quản trị membership:

~~~sql
REVOKE ADMIN OPTION FOR lab375_reader
FROM lab375_delegator;
~~~

Delegator có thể vẫn là member, nhưng không còn khả năng cấp lại membership nhờ cạnh này.

Thu hồi hẳn membership:

~~~sql
REVOKE lab375_reader
FROM lab375_delegator;
~~~

Hai thao tác không tương đương.

### 17.1. Các option còn lại có thể bị thu hồi riêng

PostgreSQL 16+ hỗ trợ kiểu:

~~~sql
REVOKE SET OPTION FOR lab375_writer
FROM lab375_bob;

REVOKE INHERIT OPTION FOR lab375_reader
FROM lab375_alice;
~~~

Chúng thay đổi khả năng SET/INHERIT của cạnh membership phù hợp mà không nhất thiết xóa membership.

### 17.2. CASCADE đối với role membership từ PostgreSQL 16

PostgreSQL 16+ theo dõi các grant membership phụ thuộc quyền ADMIN OPTION. Khi thu hồi ADMIN OPTION, có thể cần `CASCADE`/`RESTRICT` cho các grants membership phụ thuộc. PostgreSQL 15 và cũ hơn không có cùng mô hình tracking này.

## 18. PUBLIC khác group role thông thường

`PUBLIC` trong PostgreSQL biểu thị tập **mọi role hiện tại và tương lai**.

~~~sql
GRANT SELECT ON TABLE lab375.orders
TO PUBLIC;
~~~

Nếu cấp như vậy, mọi role đáp ứng các điều kiện schema/database khác có thể nhận quyền SELECT qua PUBLIC.

Thu hồi:

~~~sql
REVOKE SELECT ON TABLE lab375.orders
FROM PUBLIC;
~~~

chỉ thu hồi đường PUBLIC. Nó không xóa quyền trực tiếp, quyền qua reader hoặc ownership.

### 18.1. Quyền mặc định tới PUBLIC

PostgreSQL mặc định có một số quyền PUBLIC tùy loại đối tượng, ví dụ:

- `CONNECT` và `TEMPORARY` trên database.
- `EXECUTE` trên function/procedure.
- `USAGE` trên một số loại type/language.

Bảng mới thường **không tự cấp SELECT cho PUBLIC**. Defaults có thể bị thay đổi bởi chủ đối tượng hay `ALTER DEFAULT PRIVILEGES`.

### 18.2. Không cấp membership role cho PUBLIC

Không viết:

~~~sql
GRANT lab375_reader TO PUBLIC;
~~~

Trong PostgreSQL, membership của một role thông thường **không được grant cho PUBLIC**.

## 19. Quyền function EXECUTE và khoảng trống mặc định

Vì một số PostgreSQL function/procedure có EXECUTE cho PUBLIC mặc định, function đọc dữ liệu nhạy cảm cần xem quyền gọi.

Ví dụ khi có quyền tạo function trong schema lab:

~~~sql
BEGIN;

SET ROLE lab375_owner;

CREATE FUNCTION lab375.example_value()
RETURNS INTEGER
LANGUAGE SQL
AS $fn$
    SELECT 42;
$fn$;

REVOKE ALL ON FUNCTION lab375.example_value()
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION lab375.example_value()
TO lab375_reader;

RESET ROLE;

COMMIT;
~~~

Tạo và REVOKE trong cùng transaction có thể tránh khoảng thời gian function tồn tại với EXECUTE PUBLIC rồi mới bị thu hồi.

**Lưu ý:** quyền USAGE schema và quyền EXECUTE function vẫn là hai lớp khác nhau. Một function `SECURITY DEFINER` còn có ngữ nghĩa khác đối với quyền truy cập bảng bên trong.

## 20. GRANT hiện tại khác ALTER DEFAULT PRIVILEGES trong tương lai

~~~sql
GRANT SELECT ON ALL TABLES IN SCHEMA lab375
TO lab375_reader;
~~~

Câu trên áp dụng cho **các bảng hiện có** ở thời điểm thực thi; không tự đảm bảo các bảng mới tạo sau đó nhận quyền này.

Đối với các bảng sẽ do `lab375_owner` tạo:

~~~sql
SET ROLE lab375_owner;

ALTER DEFAULT PRIVILEGES IN SCHEMA lab375
GRANT SELECT ON TABLES TO lab375_reader;

CREATE TABLE lab375.future_orders (
    id INTEGER PRIMARY KEY,
    total NUMERIC
);

RESET ROLE;
~~~

Bảng mới `future_orders` nhận SELECT theo chính sách default privileges phù hợp.

### 20.1. Default privileges gắn với role tạo object

Điểm quan trọng: khi tạo một object, PostgreSQL áp dụng defaults của **current role thực sự tạo object**, không cộng defaults của mọi role mà current role thuộc về.

Nếu một migration service tạo bảng khi current_user là `deploy_user`, defaults cấu hình cho `lab375_owner` không nhất thiết được áp dụng dù deploy_user có membership owner. Thiết kế tốt thường dùng `SET ROLE` có kiểm soát trước migration hoặc cấu hình defaults đúng cho từng creator role.

### 20.2. Default privileges không sửa bảng cũ

Thay default privilege hôm nay không tự cấp quyền cho `lab375.orders` đã tạo hôm qua. Cần GRANT trực tiếp cho đối tượng hiện tại.

### 20.3. Global và per-schema defaults

Default privileges có phạm vi global trong database cho creator và phạm vi từng schema. Per-schema defaults thường **bổ sung** vào global defaults; một REVOKE per-schema không thể tùy ý đảo ngược một quyền đã grant mặc định ở cấp global.

### 20.4. Bảng và sequence khác nhau

Nếu creator tạo bảng và các sequence `SERIAL`, cần xử lý quyền trên sequence riêng khi cần. Có thể dùng:

~~~sql
ALTER DEFAULT PRIVILEGES IN SCHEMA lab375
GRANT USAGE ON SEQUENCES TO lab375_writer;
~~~

Câu này phải chạy khi đang là đúng creator role. Nó ảnh hưởng sequence **tương lai** chứ không tự sửa ACL sequence đã tồn tại.

## 21. Chuyển ownership bằng ALTER OWNER

Trong PostgreSQL, có thể đổi chủ sở hữu một bảng:

~~~sql
ALTER TABLE lab375.orders OWNER TO lab375_new_owner;
~~~

Nhưng **không phải role nào cũng chạy được** chỉ vì biết tên owner mới.

Với người không phải superuser, PostgreSQL thường yêu cầu:

- Có quyền chủ sở hữu phù hợp trên bảng.
- Có khả năng `SET ROLE` sang owner mới.
- Owner mới có `CREATE` trên schema chứa bảng.
- Đáp ứng những điều kiện bổ sung của loại đối tượng.

### 21.1. Đổi owner schema không tự đổi owner bảng

~~~sql
ALTER SCHEMA lab375 OWNER TO lab375_new_owner;
~~~

chuyển owner của schema, không có nghĩa mọi bảng/hàm/sequence bên trong tự chuyển ownership.

### 21.2. Owner role NOLOGIN

Một mô hình tốt có thể để `lab375_owner NOLOGIN` sở hữu schema/bảng; ứng dụng chỉ nhận reader/writer; tài khoản migration có quyền SET ROLE owner được quản trị có kiểm soát. Khi service account bị lộ, nó không tự có toàn quyền ALTER/DROP nếu không có đường owner/membership quá rộng.

`NOLOGIN` tự thân không bảo vệ nếu app lại được phép SET ROLE hoặc kế thừa quyền owner.

## 22. Kiểm tra quyền hiệu lực bằng SQL

### 22.1. Kiểm tra SELECT/UPDATE

~~~sql
SELECT
    has_table_privilege(
        'lab375_alice',
        'lab375.orders',
        'SELECT'
    ) AS alice_select,

    has_table_privilege(
        'lab375_alice',
        'lab375.orders',
        'UPDATE'
    ) AS alice_update,

    has_table_privilege(
        'lab375_bob',
        'lab375.orders',
        'INSERT'
    ) AS bob_insert_without_set;
~~~

Theo role graph ban đầu (trước các grants bổ sung): Alice có SELECT, không có UPDATE; Bob không tự có INSERT do INHERIT FALSE.

### 22.2. Kiểm tra schema

~~~sql
SELECT
    has_schema_privilege(
        'lab375_alice',
        'lab375',
        'USAGE'
    ) AS alice_schema_usage;
~~~

`has_table_privilege(...,'SELECT') = TRUE` chưa đủ để khẳng định mọi câu SELECT đầy đủ chạy được nếu role thiếu schema USAGE, bị RLS, thiếu quyền function hoặc có hạn chế khác.

### 22.3. Kiểm tra MEMBER/USAGE/SET

~~~sql
SELECT
    pg_has_role(
        'lab375_bob',
        'lab375_writer',
        'MEMBER'
    ) AS bob_member,

    pg_has_role(
        'lab375_bob',
        'lab375_writer',
        'USAGE'
    ) AS bob_inherits,

    pg_has_role(
        'lab375_bob',
        'lab375_writer',
        'SET'
    ) AS bob_can_set;
~~~

Với membership `INHERIT FALSE, SET TRUE`, các kết quả tương ứng thường là TRUE, FALSE, TRUE.

### 22.4. Catalog membership PostgreSQL 16+

~~~sql
SELECT
    member_role.rolname AS member_name,
    granted_role.rolname AS granted_role_name,
    m.admin_option,
    m.inherit_option,
    m.set_option
FROM pg_auth_members AS m
JOIN pg_roles AS member_role
    ON member_role.oid = m.member
JOIN pg_roles AS granted_role
    ON granted_role.oid = m.roleid
WHERE member_role.rolname LIKE 'lab375_%'
ORDER BY member_role.rolname, granted_role.rolname;
~~~

`inherit_option` và `set_option` là cột của cơ chế mới; PostgreSQL cũ hơn có thể không hỗ trợ.

### 22.5. Catalog owner và ACL

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relacl AS acl_raw
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'lab375'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
ORDER BY c.relname;
~~~

`relacl` NULL không tự có nghĩa không ai có quyền: có defaults, owner, PUBLIC và role membership cần được diễn giải theo ngữ nghĩa PostgreSQL.

### 22.6. psql metacommands

Nếu dùng psql:

~~~text
\du+             xem role/thuộc tính
\drg             xem role grants nếu psql hỗ trợ
\dn+             schema/ACL
\dp lab375.*      quyền bảng/sequence
\ddp             default privileges
~~~

Các câu bắt đầu bằng backslash là **lệnh của psql**, không phải SQL gửi thẳng qua JDBC.

## 23. Quyền trên một cột và trên toàn bảng

Một quản trị viên muốn cho user chỉ xem `id`, `status` mà không xem `amount`.

Có thể:

~~~sql
GRANT SELECT (id, status)
ON TABLE lab375.orders
TO lab375_reader;
~~~

Nhưng nếu role đó **đã có SELECT cả bảng**, cấp SELECT một vài cột không thu hẹp quyền sẵn có. Phải đánh giá/thu hồi quyền table-level thích hợp và các grants đến từ nguồn khác.

### 23.1. View giới hạn cột

Một view chỉ xuất `id,status` cũng là lựa chọn:

~~~sql
CREATE VIEW lab375.order_status_view AS
SELECT id, status
FROM lab375.orders;
~~~

Sau đó cấp quyền SELECT trên view cho role phù hợp. Nhưng hành vi kiểm tra quyền underlying tables còn phụ thuộc **ngữ nghĩa owner/security_invoker** của view theo PostgreSQL version. Cần đảm bảo view không vô tình trở thành đường lộ dữ liệu.

### 23.2. Khi nào dùng row-level security?

Nếu cần “chỉ thấy những đơn thuộc tenant của mình”, column grants chưa đủ. PostgreSQL **Row-Level Security** có thể giới hạn hàng sau khi role có quyền thao tác bảng theo chính sách phù hợp. RLS, table privilege và quyền view/function là những lớp riêng.

## 24. SECURITY DEFINER và quyền gián tiếp

Một function `SECURITY DEFINER` chạy với quyền của **chủ function** thay vì người gọi trong phạm vi thực thi. User có thể không có SELECT trực tiếp trên bảng gốc nhưng gọi một function đã được phép EXECUTE để nhận dữ liệu.

### 24.1. Nguy cơ khi search_path không an toàn

Nếu function chạy với quyền cao và tra cứu object theo search_path có schema do người không tin cậy được CREATE, có thể có nguy cơ đối tượng giả mạo.

Các biện pháp:

- Chỉ dùng SECURITY DEFINER khi cần.
- Schema-qualify tên bảng/hàm nhạy cảm.
- Cố định search_path tin cậy, đặt pg_temp đúng chính sách.
- Hạn chế CREATE trên schema được dùng bởi code quyền cao.
- Không ghép SQL động tùy ý từ input; validate/quote identifier đúng.
- Giới hạn quyền EXECUTE và owner của function.

### 24.2. SET ROLE không phải mọi thứ trong SECURITY DEFINER

Trong PostgreSQL, `SET ROLE` không được sử dụng tự do trong mọi ngữ cảnh function SECURITY DEFINER. Không xây cơ chế ủy quyền bằng cách để function quyền cao tự ý đổi role sang tên do user gửi.

### 24.3. Đường quyền gián tiếp

Thu hồi SELECT trực tiếp trên bảng chưa chắc ngăn được user đọc thông tin nếu user vẫn có EXECUTE trên function hoặc SELECT trên view được phép và các cơ chế đó truy cập bảng dưới quyền phù hợp. Phải đánh giá **effective access**, không chỉ direct grants.

## 25. SQL Server: ownership, database roles và DENY

SQL Server có các loại principal cấp server/database, **login**, **database user**, **database role** và `securable`. Một số khác biệt quan trọng:

- T-SQL hỗ trợ `GRANT`, `DENY`, `REVOKE`.
- `DENY` có tác dụng từ chối quyền theo mô hình SQL Server, thường có thể khắc phục một số grants qua roles nhưng có ngoại lệ và ownership chains.
- Schema có owner, object có thể có owner tường minh khác với schema owner.
- Membership database role thường dùng `ALTER ROLE ... ADD MEMBER`.
- Chuyển ownership dùng `ALTER AUTHORIZATION`, không phải PostgreSQL `ALTER TABLE ... OWNER TO`.

### 25.1. Ví dụ T-SQL

~~~sql
GRANT SELECT ON OBJECT::Sales.Orders
TO ReportReader;

ALTER ROLE ReportReader
ADD MEMBER AnalystUser;

GRANT SELECT ON OBJECT::Sales.Orders
TO ReportDelegator
WITH GRANT OPTION;

ALTER AUTHORIZATION
ON OBJECT::Sales.Orders
TO NewOwnerUser;
~~~

Các principal/object phải tồn tại và người thực thi cần đủ quyền. Đặc biệt, thay ownership trong SQL Server có thể ảnh hưởng quyền explicit trên đối tượng theo quy tắc `ALTER AUTHORIZATION`; không giả định chỉ đổi owner còn ACL y nguyên.

### 25.2. DENY không giống REVOKE PostgreSQL

Trong PostgreSQL, REVOKE một direct grant không chặn quyền đến từ role khác. Trong SQL Server, DENY là một thành phần của hệ thống quyền có thể tác động tới grants qua role, nhưng không được nói tuyệt đối “DENY luôn thắng mọi quyền” vì có các ngoại lệ như ownership và ownership chaining.

## 26. MySQL 8.4: role cần được kích hoạt

MySQL 8.4 có cú pháp cấp privilege:

~~~sql
GRANT SELECT ON sales.orders
TO 'reporter'@'localhost'
WITH GRANT OPTION;
~~~

Và role:

~~~sql
CREATE ROLE 'sales_reader';

GRANT SELECT ON sales.orders
TO 'sales_reader';

GRANT 'sales_reader'
TO 'alice'@'localhost'
WITH ADMIN OPTION;
~~~

**Các account và bảng cần tồn tại.** `WITH GRANT OPTION` ở lệnh thứ nhất là quyền cấp lại privilege; `WITH ADMIN OPTION` ở lệnh cuối liên quan quản lý role membership.

### 26.1. MySQL active/default roles

Grant role không đảm bảo role đã active trong session. MySQL có khái niệm **active roles**, **default roles** và `SET ROLE`:

~~~sql
SET ROLE 'sales_reader';
~~~

Để dùng quyền qua role, cần biết role nào đã active theo cấu hình session. Không copy cú pháp PostgreSQL `WITH INHERIT FALSE, SET TRUE` sang MySQL.

### 26.2. User@host quan trọng

`'alice'@'localhost'` và `'alice'@'%'` có thể là những account khác nhau. Khi đánh giá quyền MySQL, không chỉ đọc phần username.

### 26.3. MySQL/MariaDB không có mô hình owner giống PostgreSQL

Quản lý bảng, schema và definer của stored objects trong MySQL/MariaDB có các quy tắc khác. Không áp dụng trực tiếp `ALTER TABLE ... OWNER TO ...` hoặc giả định schema owner ở PostgreSQL tương ứng 1:1 với tài khoản sở hữu database MySQL.

MariaDB có hỗ trợ role nhưng cú pháp và hành vi có thể khác MySQL theo phiên bản; phải kiểm tra tài liệu đúng sản phẩm.

## 27. Oracle: system/object privileges, roles và PL/SQL

Oracle phân biệt system privileges, object privileges và role grants.

Ví dụ ý tưởng:

~~~sql
GRANT SELECT ON sales.orders TO report_role;

GRANT report_role TO app_user;

GRANT SELECT ON sales.orders
TO report_delegator
WITH GRANT OPTION;
~~~

Oracle hỗ trợ `WITH ADMIN OPTION` trong các quy tắc cấp role/system privileges phù hợp.

### 27.1. Kích hoạt role

Oracle có default roles và `SET ROLE`. Một user có role chưa chắc mọi stored code đều dùng quyền role theo cách câu SQL trực tiếp dùng.

### 27.2. Quyền trong definer-rights PL/SQL

Đặc biệt trong PL/SQL definer-rights, role privileges có quy tắc khác; một stored procedure có thể cần direct grants cho definer thay vì dựa vào grants qua role. Cần phân biệt definer-rights/invoker-rights theo tài liệu Oracle và cách routine được tạo.

### 27.3. Ownership và schema

Trong Oracle, schema gắn với user; quyền tạo và sở hữu object khác mô hình PostgreSQL tách role và schema. Không sao chép lệnh ALTER OWNER PostgreSQL sang Oracle.

## 28. SQLite: không có SQL roles và GRANT như server DBMS

SQLite là engine nhúng, thường dùng quyền file/OS và authorization trong ứng dụng. Không có hệ thống `GRANT SELECT ON ... TO role`, `SET ROLE` hay role membership cấp server giống PostgreSQL.

~~~sql
GRANT SELECT ON orders TO report_reader;
~~~

**Không phải một câu hợp lệ cho mô hình phân quyền SQLite.**

Ứng dụng dùng SQLite có thể phải:

- Xác thực người dùng ở service/UI.
- Bảo vệ file database ở OS.
- Hạn chế thao tác bằng API và thiết kế data access layer.
- Cân nhắc authorization callbacks của thư viện khi phù hợp.

Không dùng khái niệm SQL server ownership để suy luận về quyền file.

## 29. Bảng so sánh nhanh các hệ quản trị

| Vấn đề | PostgreSQL 16+ | SQL Server | MySQL 8.4 | Oracle | SQLite |
|---|---|---|---|---|---|
| Cấp quyền đối tượng | GRANT trên object | GRANT | GRANT ON | GRANT ON | Không có engine GRANT server-role |
| Cấp lại privilege | WITH GRANT OPTION | WITH GRANT OPTION | WITH GRANT OPTION | Với quyền phù hợp | Không áp dụng |
| Cấp lại role membership | ADMIN option | Quản lý role theo security model T-SQL | WITH ADMIN OPTION | WITH ADMIN OPTION theo quy tắc | Không áp dụng |
| Inheritance/kích hoạt | INHERIT/SET từng membership | Role membership, DENY, ownership chains | Active/default roles, SET ROLE | Active/default roles, PL/SQL context | Ứng dụng quản lý |
| Chuyển owner | ALTER ... OWNER TO | ALTER AUTHORIZATION | Cơ chế khác | Schema/user ownership khác | File ownership/ứng dụng |
| DENY độc lập | Không có kiểu T-SQL | Có | Mô hình khác | Mô hình khác | Không có |
| Chú ý đặc biệt | PostgreSQL 16+ membership options | Server vs database principal | User@host | Definer-rights PL/SQL | Không có role catalog |

Bảng này so sánh mô hình, không bao quát mọi privilege hoặc phiên bản. Khi triển khai, hãy kiểm tra bản DBMS cụ thể.

## 30. Mẫu phân quyền: reader group an toàn

Yêu cầu: nhiều nhân viên phân tích chỉ được đọc dữ liệu cần thiết, không được cấp lại membership, không được sửa bảng.

Ý tưởng PostgreSQL:

~~~sql
CREATE ROLE analytics_reader NOLOGIN;

GRANT USAGE ON SCHEMA sales
TO analytics_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA sales
TO analytics_reader;

-- Giả định analyst_01 đã tồn tại:
GRANT analytics_reader TO analyst_01
WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;
~~~

### 30.1. Vì sao không GRANT ALL?

Reader chỉ cần SELECT. `GRANT ALL PRIVILEGES` có thể cấp quyền ghi/quản trị không cần thiết, trái nguyên tắc ít đặc quyền nhất.

### 30.2. Vì sao ADMIN FALSE?

Nếu analyst có ADMIN OPTION trên reader, họ có thể thêm thành viên mới, mở rộng người đọc dữ liệu. Với nhóm reader, quyền quản lý membership nên giao riêng cho role quản trị.

### 30.3. Bảng mới

`GRANT ... ON ALL TABLES IN SCHEMA` là cấp trên các bảng hiện tại. Cần `ALTER DEFAULT PRIVILEGES` của role tạo bảng để bảng tương lai tự nhận SELECT.

### 30.4. Cột nhạy cảm

Nếu bảng chứa token hoặc dữ liệu riêng tư, đừng cấp SELECT cả bảng khi chỉ cần vài cột. Dùng view hoặc column grants/role khác theo mô hình được kiểm tra.

## 31. Mẫu phân quyền: cập nhật riêng cột trạng thái

Ứng dụng chỉ đọc id/status và cập nhật status:

~~~sql
CREATE ROLE order_status_writer NOLOGIN;

GRANT USAGE ON SCHEMA sales
TO order_status_writer;

GRANT SELECT (id, status)
ON sales.orders
TO order_status_writer;

GRANT UPDATE (status)
ON sales.orders
TO order_status_writer;

GRANT order_status_writer TO app_service
WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;
~~~

Ứng dụng có thể dùng prepared statement:

~~~sql
UPDATE sales.orders
SET status = 'PAID'
WHERE id = 101
  AND status = 'NEW';
~~~

Role không được cấp `DELETE`, `TRUNCATE` hay ownership. Tuy vậy, giới hạn privilege không tự ngăn chuyển trạng thái sai về nghiệp vụ; cần transaction validation, authorization, constraint/RLS khi thích hợp.

**Bảo mật nhiều tầng:** least privilege giảm hậu quả khi ứng dụng có lỗi SQL injection, nhưng không thay cho parameterized queries và kiểm tra quyền người dùng cuối.

## 32. Những sai lầm thường gặp

| Sai lầm | Cách hiểu đúng |
|---|---|
| “Có SELECT thì chắc cấp lại SELECT được” | Cần grant option hoặc đường cấp hợp lệ |
| “ADMIN OPTION là chủ bảng” | Chỉ quản lý membership của role tương ứng |
| “GRANT ALL nghĩa là owner” | ALL chỉ gồm những object privileges có thể GRANT |
| “Owner schema sở hữu mọi bảng” | Schema và bảng có owner riêng |
| “Có SELECT là query chắc chạy” | Còn USAGE schema, CONNECT, RLS, function/sequence |
| “REVOKE là cấm tuyệt đối” | PG REVOKE chỉ thu hồi grant/option tương ứng |
| “REVOKE member làm mất mọi quyền” | Có thể có direct grant/PUBLIC/membership khác |
| “INHERIT FALSE ngăn dùng role vĩnh viễn” | SET TRUE vẫn có thể chuyển role |
| “SET FALSE bảo vệ owner role dù INHERIT TRUE” | Kế thừa ownership privilege có thể tạo rủi ro |
| “NOLOGIN không dùng được qua SET ROLE” | NOLOGIN chỉ cấm đăng nhập trực tiếp |
| “Membership options PG16+ có trên PG15” | Có khác biệt cú pháp/ngữ nghĩa |
| “GRANT role TO PUBLIC” | PostgreSQL không hỗ trợ |
| “GRANT table INSERT tự GRANT sequence” | Sequence có quyền riêng |
| “ALL TABLES tự bao phủ future tables” | Cần ALTER DEFAULT PRIVILEGES |
| “Defaults tự kế thừa từ mọi role membership” | Defaults theo role tạo object thực tế |
| “Test bằng superuser chứng minh quyền app” | Superuser bypass privilege checks |
| “has_table_privilege TRUE nghĩa thấy mọi hàng” | RLS và các lớp khác còn tác động |
| “SET ROLE chỉ cộng quyền” | Có thể thay đổi/mất quyền login role ban đầu |
| “SQL Server DENY giống PG REVOKE” | Mô hình khác |
| “MySQL GRANT role tự active” | Cần xem active/default roles |
| “Oracle stored PL/SQL luôn dùng role privileges” | Definer/invoker contexts khác |
| “SQLite có GRANT ROLE như PostgreSQL” | SQLite không có mô hình đó |

## 33. Bài tập thực hành có lời giải

Các bài dùng mô hình `lab375` nếu cần SQL. Những bài cấp/thu hồi quyền là **bài tư duy hoặc chạy trong sandbox**, không thực hiện trong môi trường vận hành. Mỗi lần thay đổi role graph có thể ảnh hưởng kết quả bài sau.

### Bài 1. Phân biệt owner và reader

**Đề:** `lab375_owner` sở hữu `lab375.orders`, `lab375_reader` có SELECT. Ai được ALTER TABLE chỉ dựa trên quyền mô tả?

**Lời giải:** owner có khả năng quản lý định nghĩa theo điều kiện PostgreSQL; reader không được ALTER chỉ vì có SELECT.

### Bài 2. GRANT ALL có cho DROP TABLE không?

**Lời giải:** không. GRANT ALL PRIVILEGES trên bảng không chuyển ownership và không cấp một quyền DROP riêng.

### Bài 3. Thiếu USAGE schema

**Đề:** Alice được SELECT bảng nhưng thiếu schema USAGE. Có chắc chạy được `SELECT * FROM lab375.orders`?

**Lời giải:** không. Cần quyền truy cập schema và bảng, cùng các điều kiện khác.

### Bài 4. INHERIT TRUE, SET FALSE

**Đề:** Alice nhận reader có INHERIT TRUE, SET FALSE. Alice có tự đọc được bảng không?

**Lời giải:** có nếu reader có SELECT và schema USAGE và không có ràng buộc khác. SET FALSE không ngăn kế thừa khi INHERIT TRUE.

### Bài 5. INHERIT FALSE, SET TRUE

**Đề:** Bob được writer với INHERIT FALSE, SET TRUE. Trước SET ROLE, Bob tự có quyền writer không?

**Lời giải:** không qua cạnh ấy. Nhưng Bob có thể SET ROLE writer nếu session/đường membership hợp lệ.

### Bài 6. INHERIT FALSE, SET FALSE

**Đề:** Chỉ có một membership writer với hai option FALSE. Bob dùng quyền qua membership ấy được không?

**Lời giải:** không tự dùng và không SET qua cạnh ấy; nếu có quyền trực tiếp/đường khác, kết luận có thể thay đổi.

### Bài 7. ADMIN TRUE nhưng INHERIT FALSE

**Đề:** Delegator có ADMIN TRUE, INHERIT FALSE, SET FALSE với reader. Delegator được thêm Carol vào reader không, và có tự SELECT qua reader không?

**Lời giải:** có thể quản lý membership khi đáp ứng quy tắc ADMIN; không tự hưởng SELECT qua cạnh vì INHERIT FALSE.

### Bài 8. Grant option trên bảng

**Đề:** Delegator được SELECT WITH GRANT OPTION. Có được GRANT DELETE không?

**Lời giải:** không chỉ vì SELECT grant option. Quyền cấp lại gắn với quyền và đối tượng cụ thể.

### Bài 9. Alice có SELECT nhưng không grant option

**Lời giải:** Alice không thể cấp SELECT cho Carol chỉ nhờ quyền đọc; cần grant option/owner hoặc đường khác cho phép.

### Bài 10. CASCADE và RESTRICT

**Đề:** Owner cấp SELECT WITH GRANT OPTION cho Alice, Alice cấp SELECT cho Bob. Thu hồi grant option của Alice bằng RESTRICT có thể xảy ra gì?

**Lời giải:** có thể bị từ chối vì Bob có quyền phụ thuộc. CASCADE có thể thu hồi các grants phụ thuộc theo chain ấy.

### Bài 11. Hai nguồn quyền

**Đề:** Bob có SELECT qua Alice và từ owner trực tiếp. Thu hồi chain Alice bằng CASCADE có chắc làm Bob hết SELECT?

**Lời giải:** không. Quyền từ owner trực tiếp vẫn có thể giữ hiệu lực.

### Bài 12. Chỉ REVOKE GRANT OPTION

**Đề:** REVOKE GRANT OPTION FOR SELECT từ Alice có nhất thiết lấy cả SELECT?

**Lời giải:** không; mục tiêu là thu hồi khả năng cấp lại, trong khi quyền đọc có thể được giữ.

### Bài 13. REVOKE membership vs REVOKE ADMIN OPTION

**Lời giải:** REVOKE membership xóa membership được chỉ định; REVOKE ADMIN OPTION chỉ xóa quyền quản lý membership của role, có thể vẫn giữ membership.

### Bài 14. Mặc định bảng tương lai

**Đề:** GRANT SELECT ON ALL TABLES IN SCHEMA hôm nay, mai tạo thêm bảng. Bảng mới có tự được cấp SELECT không?

**Lời giải:** không chỉ nhờ câu GRANT ấy. Cần ALTER DEFAULT PRIVILEGES của role tạo bảng hoặc GRANT sau khi tạo.

### Bài 15. Role tạo object

**Đề:** Default privileges đặt cho owner, nhưng migration tạo bảng dưới role deploy khác. Có tự nhận defaults của owner không?

**Lời giải:** không nhất thiết. Default privileges áp dụng theo role thực sự tạo đối tượng, không tự cộng từ mọi role membership.

### Bài 16. SERIAL sequence

**Đề:** Service có INSERT bảng nhưng thiếu quyền sequence dùng bởi SERIAL. Có thể gặp lỗi không?

**Lời giải:** có; sequence có ACL riêng và có thể cần USAGE theo thao tác.

### Bài 17. Chuyển owner

**Đề:** Có SELECT trên bảng và biết role owner mới, đã đủ chạy ALTER TABLE OWNER TO chưa?

**Lời giải:** không. PostgreSQL yêu cầu quyền owner hiện tại, SET ROLE owner mới, owner mới CREATE schema và các điều kiện liên quan.

### Bài 18. Schema owner vs object owner

**Đề:** Role A sở hữu schema, B sở hữu bảng trong schema đó. A có tự là owner của bảng không?

**Lời giải:** không; hai ownership tách biệt. A có quyền quản lý schema nhưng không tự đồng nghĩa owner của mọi object.

### Bài 19. SET ROLE và connection pool

**Đề:** Request SET ROLE writer rồi không RESET khi trả connection vào pool. Rủi ro?

**Lời giải:** request sau có thể thực thi dưới role không mong muốn. Cần khôi phục session state an toàn.

### Bài 20. Kiểm tra quyền Bob

~~~sql
SELECT
    pg_has_role('lab375_bob', 'lab375_writer', 'MEMBER')
        AS is_member,
    pg_has_role('lab375_bob', 'lab375_writer', 'USAGE')
        AS can_inherit,
    pg_has_role('lab375_bob', 'lab375_writer', 'SET')
        AS can_set;
~~~

**Lời giải:** với cạnh INHERIT FALSE, SET TRUE của lab, kết quả thường là TRUE, FALSE, TRUE.

### Bài 21. SQL Server DENY

**Đề:** Vì sao không mô phỏng DENY SQL Server bằng một REVOKE PostgreSQL rồi kỳ vọng mọi role khác cũng mất quyền?

**Lời giải:** REVOKE PG chỉ lấy đi grant tương ứng; các nguồn grant khác có thể còn. SQL Server có DENY với các quy tắc/ngoại lệ riêng.

### Bài 22. MySQL role activation

**Đề:** User được GRANT role MySQL nhưng role chưa active/default. User có chắc dùng ngay các quyền của role không?

**Lời giải:** không. Phải xét active roles/default roles và SET ROLE.

### Bài 23. Oracle definer-rights PL/SQL

**Đề:** Một user dùng SELECT nhờ role trực tiếp, nhưng stored PL/SQL definer-rights không có cùng quyền như kỳ vọng. Vì sao?

**Lời giải:** Oracle có quy tắc đặc biệt về role privileges trong stored PL/SQL; cần direct grant cho definer hoặc thiết kế invoker-rights phù hợp.

### Bài 24. Kiểm tra table và schema privilege

~~~sql
SELECT
    has_table_privilege(
        'lab375_alice', 'lab375.orders', 'SELECT'
    ) AS table_select,
    has_schema_privilege(
        'lab375_alice', 'lab375', 'USAGE'
    ) AS schema_usage;
~~~

**Lời giải:** hai boolean cho hai lớp quyền. Chúng không tự kiểm tra toàn bộ Row-Level Security hoặc ngữ cảnh view/function.

### Bài 25. Thiết kế quyền ít nhất

**Đề:** Service chỉ đọc id/status và UPDATE status, không được DELETE/ALTER/GRANT. Hãy đề xuất mô hình.

**Lời giải:** owner role NOLOGIN riêng, writer group role NOLOGIN có USAGE schema, SELECT(id,status), UPDATE(status), không có DELETE/TRUNCATE/CREATE/GRANT OPTION; service nhận membership INHERIT TRUE, SET FALSE, ADMIN FALSE khi phù hợp; kiểm tra thêm transaction logic, authorization và prepared statements.

## 34. Checklist khi điều tra lỗi “permission denied”

1. Session dùng database nào? `session_user`, `current_user` là gì?
2. Câu SQL thực tế đọc/sửa những cột và object nào?
3. Có `CONNECT` database và `USAGE` schema không?
4. Table/column privileges được cấp trực tiếp hay qua role nào?
5. Role graph có những cạnh INHERIT/SET/ADMIN nào?
6. Có GRANT nào đến từ PUBLIC hoặc đường membership khác không?
7. Đối tượng do role nào sở hữu? Application có vô tình mang quyền owner không?
8. Có sequence `nextval`, function EXECUTE hoặc type USAGE cần quyền riêng không?
9. Có view/function SECURITY DEFINER hoặc security_invoker làm đổi ngữ cảnh không?
10. Có RLS hoặc tenant policy giới hạn dữ liệu không?
11. Có REVOKE/CASCADE ảnh hưởng chain cấp lại khác chưa được kiểm tra không?
12. Có ALTER DEFAULT PRIVILEGES áp dụng đúng creator role cho bảng mới không?
13. Có đang thử quyền bằng superuser, khiến kết quả sai lệch không?
14. Có SET ROLE từ request trước còn tồn tại trên pooled connection không?
15. Có nhầm cú pháp PostgreSQL với SQL Server/MySQL/Oracle không?
16. Có thể cấp **đúng quyền tối thiểu** thay vì GRANT ALL không?

## 35. Tài liệu tham khảo chính thức

Cần kiểm tra phiên bản DBMS thực tế vì permission models không hoàn toàn đồng nhất:

- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html).
- [PostgreSQL — REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html).
- [PostgreSQL — Role Membership](https://www.postgresql.org/docs/current/role-membership.html).
- [PostgreSQL — Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html).
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html).
- [PostgreSQL — Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html).
- [PostgreSQL — SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html).
- [PostgreSQL — ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html).
- [PostgreSQL — System Information Functions](https://www.postgresql.org/docs/current/functions-info.html).
- [MySQL 8.4 — GRANT](https://dev.mysql.com/doc/refman/8.4/en/grant.html).
- [SQL Server — ALTER AUTHORIZATION](https://learn.microsoft.com/en-us/sql/t-sql/statements/alter-authorization-transact-sql).

## 36. Tổng kết

- **Owner** quản lý đối tượng và có những khả năng đặc biệt, khác quyền SELECT/UPDATE thông thường. `GRANT ALL PRIVILEGES` không tự chuyển ownership.
- **`WITH GRANT OPTION`** cho phép cấp lại một privilege trên đối tượng; **`WITH ADMIN OPTION`** cho phép quản lý membership của role. Hai cơ chế khác nhau.
- PostgreSQL 16+ lưu riêng **`INHERIT`**, **`SET`**, **`ADMIN`** trên từng membership. Có membership chưa chắc tự có quyền; INHERIT FALSE vẫn có thể dùng quyền sau SET ROLE nếu SET TRUE.
- Quyền hiệu lực có thể đến từ nhiều đường **direct GRANT, membership, PUBLIC, ownership và object trung gian**. REVOKE một đường không có nghĩa xóa mọi đường.
- `REVOKE ... CASCADE` xử lý grants phụ thuộc, nhưng không tự xóa quyền nhận từ một grant độc lập khác.
- **Schema USAGE, table privileges, sequence/function privileges, RLS và SECURITY DEFINER** phải được xem là các lớp riêng khi đánh giá một câu SQL.
- **ALTER DEFAULT PRIVILEGES** cấp quyền mặc định cho đối tượng tương lai của creator role, không sửa quyền bảng cũ.
- **PostgreSQL, SQL Server, MySQL/MariaDB, Oracle và SQLite** có cách ownership, role activation và quản trị quyền khác nhau; không sao chép cú pháp hay suy luận hành vi giữa các hệ.

Hãy thiết kế SQL security bằng **owner role tách biệt, group roles ít quyền, membership được kiểm soát, quyền cấp lại có giới hạn, thu hồi có hiểu biết về dependencies và kiểm tra quyền thực tế**, thay vì dùng GRANT ALL như cách giải quyết mặc định cho mọi lỗi truy cập.
