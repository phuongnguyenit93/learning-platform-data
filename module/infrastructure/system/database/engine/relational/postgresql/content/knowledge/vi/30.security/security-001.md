# Role, LOGIN, thành viên role và quyền kế thừa trong PostgreSQL

Khi thiết kế bảo mật PostgreSQL, câu hỏi không chỉ là **“người dùng có đăng nhập được không?”**, mà còn là **“sau khi đăng nhập, họ được làm gì, quyền đến từ đâu, và có thể chuyển sang vai trò nào?”**.

Giả sử một hệ thống có ba nhóm người dùng:

- Nhân viên báo cáo chỉ được đọc tài liệu.
- Nhân viên biên tập được đọc và, khi thực sự cần, được chỉnh sửa.
- Nhân viên triển khai được tạo bảng và chạy migration, nhưng ứng dụng chạy hằng ngày không được sở hữu schema.

Một thiết kế thiếu phân tách có thể tạo một tài khoản chung `app_user` được cấp `SUPERUSER` hoặc `ALL PRIVILEGES` để “khỏi gặp lỗi permission”. Thiết kế đó hoạt động lúc đầu nhưng tạo rủi ro lớn: SQL injection, ứng dụng bị chiếm quyền, migration sai hoặc lỗi lập trình đều có thể gây tổn hại trên diện rộng.

PostgreSQL cung cấp hệ thống **role-based access control (RBAC)**:

- **Role**: danh tính dùng để sở hữu object, nhận quyền và làm thành viên của role khác.
- **`LOGIN`**: thuộc tính cho phép role được dùng như một tài khoản đăng nhập, còn xác thực và quyền kết nối là các bước riêng.
- **`NOLOGIN`**: role không dùng để đăng nhập trực tiếp, thường dành cho nhóm quyền hoặc ownership.
- **Membership**: quan hệ một role là thành viên của role khác thông qua `GRANT role TO member`.
- **Privilege inheritance**: quyền trên object của role cha có thể được dùng tự động thông qua những đường membership được phép kế thừa.
- **`SET ROLE`**: chủ động chuyển *effective current role* sang role mà session được phép đảm nhận.
- **Admin option**: quyền quản trị membership của role được cấp, không đồng nghĩa mọi quyền trên table hay mọi role attribute.

Bài học thuộc chương **Bảo mật**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ xây một lab có role đọc, role ghi, hai role đăng nhập và các tình huống kế thừa/chuyển role, sau đó mở rộng sang schema privileges, owner, RLS, security và kiểm tra quyền hiệu lực.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt PostgreSQL **role**, tài khoản có `LOGIN`, nhóm quyền `NOLOGIN` và database user theo cách gọi thông dụng.
2. Hiểu phạm vi role **toàn cluster**, khác quyền trên từng database/schema/object.
3. Tạo và thay đổi role bằng `CREATE ROLE` và `ALTER ROLE` theo nguyên tắc tối thiểu quyền.
4. Cấp và thu hồi quyền trên bảng, schema, sequence bằng `GRANT`/`REVOKE`.
5. Cấp role membership, hiểu thành viên trực tiếp và qua nhiều cấp.
6. Phân biệt `INHERIT`, `SET` và `ADMIN` options của membership trong PostgreSQL 16+.
7. Biết sự khác nhau quan trọng giữa PostgreSQL 15 trở xuống và PostgreSQL 16+ khi cấu hình kế thừa.
8. Phân biệt **quyền trên object** và **role attributes** như `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`.
9. Hiểu `session_user`, `current_user` và hành vi `SET ROLE`/`RESET ROLE`.
10. Thiết kế nhóm reader/writer/owner/deployer theo nguyên tắc least privilege.
11. Nhận diện vai trò của `PUBLIC`, schema `USAGE`, database `CONNECT` và default privileges.
12. Kiểm tra quyền hiệu lực bằng `pg_roles`, `pg_auth_members`, `pg_has_role`, `has_table_privilege` và các lệnh psql.
13. Phân tích các tình huống revoke chưa đủ, quyền đến từ đường khác và role membership lồng nhau.
14. Hiểu mối quan hệ giữa role, object ownership, RLS, `SECURITY DEFINER` và quyền ứng dụng.
15. Tránh các cấu hình nguy hiểm như cho app role sở hữu toàn bộ bảng, dùng superuser cho connection pool hoặc lưu password trong SQL log.

## 2. Hệ thống quyền PostgreSQL có những lớp nào?

~~~mermaid
flowchart TD
    LOGIN["Login role: app_editor"] -->|"membership"| R["NOLOGIN role: app_reader"]
    LOGIN -->|"membership (may require SET ROLE)"| W["NOLOGIN role: app_writer"]
    R -->|"USAGE"| SCHEMA["Schema: app"]
    R -->|"SELECT"| TBL["Table: app.documents"]
    W -->|"INSERT/UPDATE"| TBL
    DB["Database: shopdb"] -->|"CONNECT privilege"| LOGIN
    ACL["RLS / table privileges / object owner"] --> TBL
~~~

Để một phiên kết nối bình thường đọc `app.documents`, cần xét nhiều điều kiện:

1. Client có xác thực thành công vào **một role có LOGIN** không?
2. Role có được `CONNECT` vào database không?
3. Role có `USAGE` trên schema `app` không?
4. Role có `SELECT` trên table hay các cột liên quan không?
5. Nếu bật **row-level security**, policy có cho đọc những hàng đó không?
6. Có quyền khác từ role membership, `PUBLIC`, owner hoặc `SECURITY DEFINER` ảnh hưởng kết quả không?

**Không có một câu `GRANT SELECT` đơn lẻ bảo đảm mọi điều kiện còn lại đều đã được đáp ứng.**

## 3. Role và user là gì?

Trong PostgreSQL hiện đại, **user và group được thống nhất dưới khái niệm role**.

Một role có thể:

- Được dùng để xác thực đăng nhập nếu có `LOGIN`.
- Nhận quyền trên bảng, schema, sequence, function, database và các object khác.
- Sở hữu object.
- Là thành viên của role khác.
- Được quản lý bởi một role có đủ quyền thích hợp.

Hai lệnh quen thuộc:

~~~sql
CREATE ROLE app_reader NOLOGIN;

CREATE ROLE app_user LOGIN;
~~~

`app_reader` có thể dùng làm nhóm quyền. `app_user` có thể là danh tính đăng nhập, nhưng chưa tự có quyền đọc mọi table.

### CREATE USER và CREATE GROUP

PostgreSQL vẫn có các bí danh lịch sử:

~~~sql
CREATE USER demo_user;

CREATE GROUP demo_group;
~~~

Về bản chất, chúng là cách viết thân thiện của `CREATE ROLE` với các mặc định khác:

- `CREATE USER` tương ứng với role mặc định có `LOGIN`.
- `CREATE GROUP` tương ứng với role mặc định `NOLOGIN`.

**Một role NOLOGIN không kém “mạnh” về mặt quyền trên object.** Nó chỉ không đăng nhập trực tiếp; một session được phép `SET ROLE` tới role đó có thể sử dụng nó theo quy tắc membership.

## 4. PostgreSQL role có phạm vi toàn cluster

Đây là điều rất dễ bỏ qua nếu bạn quen hệ quản trị khác.

**Role của PostgreSQL là đối tượng cấp database cluster**, không nằm riêng trong một database.

Ví dụ:

~~~sql
CREATE ROLE report_reader NOLOGIN;
~~~

Role này có mặt trong cùng cluster, kể cả khi có nhiều database. Tuy nhiên:

- Quyền `SELECT` trên một bảng thuộc database A **không tự chuyển sang** bảng ở database B.
- Schema và table là object riêng theo database.
- `CONNECT` vào từng database có thể khác nhau.
- PostgreSQL không cho một câu query thông thường join trực tiếp object ở hai database độc lập chỉ vì role tồn tại toàn cluster.

### Hệ quả với môi trường multi-tenant

Nếu mỗi tenant là một database trong cùng cluster, cần:

- Tên role không đụng nhau hoặc có quy ước rõ.
- Kiểm tra membership của role được dùng giữa databases.
- Cấp quyền object riêng cho từng database.
- Không tạo một tài khoản có quyền toàn cluster nếu chỉ cần truy cập một tenant.

**Role toàn cluster không đồng nghĩa quyền truy cập toàn cluster.**

## 5. LOGIN có nghĩa là gì?

Role `LOGIN` có thể được dùng làm danh tính cho một connection, nếu thỏa các bước xác thực và kết nối.

~~~sql
CREATE ROLE lab378_reporter LOGIN;
~~~

Nhưng **`LOGIN` không tự bảo đảm kết nối thành công**:

- Chính sách `pg_hba.conf` phải cho kiểu kết nối/xác thực phù hợp.
- Password hoặc cơ chế xác thực ngoài (SCRAM, certificate, peer, IAM integration...) phải được cấu hình.
- Database phải cho role `CONNECT`.
- Role còn phải thỏa những giới hạn liên quan như expiration/connection limit nếu được cấu hình.
- Mạng, TLS và database availability cũng phải phù hợp.

### Không hard-code mật khẩu

Tránh:

~~~sql
-- Ví dụ KHÔNG NÊN dùng trong source code/CI logs:
CREATE ROLE unsafe_app LOGIN PASSWORD 'plain-text-secret';
~~~

Đoạn trên là **anti-pattern**, không phải đề nghị thực thi.

Trong psql, admin có thể dùng lệnh tương tác:

~~~text
\password lab378_reporter
~~~

Lệnh này giúp tránh gõ password thành một câu SQL nguyên văn trong shell history. Trong production, nên dùng secret manager/credential rotation, chính sách xác thực hiện đại và kết nối được bảo vệ.

### NOLOGIN dùng trong trường hợp nào?

~~~sql
CREATE ROLE lab378_reader NOLOGIN;
CREATE ROLE lab378_writer NOLOGIN;
~~~

Hai role này không cần có mật khẩu. Chúng đại diện cho **bộ quyền** và có thể được cấp làm membership cho những tài khoản có LOGIN.

## 6. Role attributes khác object privileges

Role attributes được khai báo bằng `CREATE ROLE`/`ALTER ROLE`:

| Thuộc tính role | Mục đích |
| --- | --- |
| `LOGIN`/`NOLOGIN` | Cho phép/không cho login trực tiếp |
| `SUPERUSER` | Quyền đặc biệt rất rộng, vượt nhiều kiểm soát thông thường |
| `CREATEDB` | Cho tạo database |
| `CREATEROLE` | Cho quản lý role theo điều kiện/phạm vi version |
| `REPLICATION` | Quyền cho hoạt động replication liên quan |
| `BYPASSRLS` | Bỏ qua row-level security |
| `INHERIT`/`NOINHERIT` | Thuộc tính liên quan đến giá trị mặc định kế thừa membership; semantics theo version |
| `CONNECTION LIMIT` | Giới hạn kết nối phù hợp |
| `PASSWORD`/`VALID UNTIL` | Cấu hình credentials/expiration |

Một role có `CREATEDB` không có nghĩa nó được `SELECT` trên mọi bảng.

Một role có `SELECT` trên một bảng không có nghĩa nó được tạo database.

### Role attributes không được tự động “thừa kế” như table privileges

Giả sử:

~~~sql
CREATE ROLE powerful_owner NOLOGIN CREATEDB;

GRANT powerful_owner TO ordinary_user;
~~~

**Không suy ra** `ordinary_user` tự nhận `CREATEDB` chỉ vì membership có quyền INHERIT. Những role attributes đặc biệt không được kế thừa như quyền SELECT trên object.

Nếu session được phép `SET ROLE powerful_owner`, role hiệu lực và ngữ cảnh quyền có thể đổi theo semantics của `SET ROLE`. Điều này khác việc attribute “được cộng vĩnh viễn” vào role đăng nhập.

**Không dùng `SUPERUSER`/`CREATEROLE`/`BYPASSRLS` cho application connection chỉ để xử lý lỗi permissions.**

## 7. Nguyên tắc least privilege

**Least privilege** nghĩa là mỗi role chỉ có quyền thật sự cần.

Ví dụ vai trò trong một hệ thống:

| Role | LOGIN | Nhiệm vụ | Quyền dự kiến |
| --- | --- | --- | --- |
| `app_reader` | Không | Nhóm đọc | `USAGE` schema, `SELECT` một số tables |
| `app_writer` | Không | Nhóm chỉnh dữ liệu | `SELECT`/`INSERT`/`UPDATE` có chọn lọc |
| `app_owner` | Không | Sở hữu schema/table | Quyền ownership, DDL theo phạm vi |
| `app_web` | Có | API production | Membership giới hạn các nhóm dữ liệu cần thiết |
| `app_deployer` | Có | Chạy migrations | `SET ROLE app_owner` khi được cho phép |
| `app_analyst` | Có | Truy vấn báo cáo | Chỉ membership đọc |

Tại sao tách owner?

- Role login production ít có quyền thay/drop table.
- DDL có đường triển khai/audit riêng.
- Mất credential ứng dụng không tự đồng nghĩa mất mọi object trong schema.
- Dễ review quyền qua nhóm reader/writer thay vì grant lẻ cho từng service.

Đừng hiểu rằng việc có 6 role luôn an toàn hơn có 2 role. Cần role đúng chức năng, tránh role lồng nhau khó giải thích.

## 8. Hai loại GRANT hoàn toàn khác nhau

### 8.1. Cấp quyền trên object

~~~sql
GRANT SELECT
ON TABLE some_schema.some_table
TO app_reader;
~~~

Đây là **object privilege grant**: cho `app_reader` đọc table được chỉ định.

### 8.2. Cấp membership của role

~~~sql
GRANT app_reader TO app_analyst;
~~~

Đây là **role membership grant**: `app_analyst` là thành viên của `app_reader` theo các option áp dụng.

Hai câu lệnh đều dùng `GRANT` nhưng đối tượng khác:

| Câu lệnh | Điều được cấp |
| --- | --- |
| `GRANT SELECT ON table TO role` | Quyền đọc object |
| `GRANT USAGE ON SCHEMA TO role` | Quyền dùng namespace schema |
| `GRANT role_a TO role_b` | Tư cách thành viên role_a cho role_b |
| `GRANT role_a TO role_b WITH ADMIN ...` | Membership kèm một tùy chọn quản lý membership |

**Không thể thay `GRANT SELECT ON table` bằng `GRANT table TO user`.** Table không phải role.

## 9. Membership có thể tạo đồ thị quyền

~~~mermaid
flowchart LR
    U["lab378_editor (LOGIN)"] -->|"INHERIT TRUE"| R["lab378_reader (NOLOGIN)"]
    U -->|"INHERIT FALSE / SET TRUE"| W["lab378_writer (NOLOGIN)"]
    R -->|"SELECT"| T["lab378.documents"]
    W -->|"SELECT/INSERT/UPDATE"| T
~~~

Trong thiết kế PostgreSQL 16+ này:

- Editor đăng nhập với danh tính `lab378_editor`.
- Quyền `SELECT` của reader được kế thừa tự động.
- Quyền ghi của writer **không được tự kế thừa** vì membership edge có `INHERIT FALSE`.
- Khi cần ghi, editor có thể `SET ROLE lab378_writer` nếu edge/path cho `SET TRUE`.
- Sau `RESET ROLE`, current role trở lại role gốc và không giữ quyền writer như một trạng thái hiệu lực vĩnh viễn.

**Membership là quan hệ role; inheritance là hành vi sử dụng quyền.** Hai điều không đồng nhất.

## 10. PostgreSQL 16+ có ba option membership quan trọng

Từ PostgreSQL 16, mỗi membership grant có thể mang các thuộc tính độc lập:

| Membership option | Ý nghĩa |
| --- | --- |
| `INHERIT TRUE/FALSE` | Có tự động sử dụng object privileges của role được cấp qua đường membership hay không |
| `SET TRUE/FALSE` | Có được `SET ROLE` sang role được cấp qua đường membership hay không |
| `ADMIN TRUE/FALSE` | Có quyền quản lý/cấp tiếp membership của role đó theo các quy tắc hiện hành hay không |

Ví dụ **PostgreSQL 16+**:

~~~sql
GRANT lab378_reader TO lab378_reporter
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

### Ba cấu hình tiêu biểu

| INHERIT | SET | Hành vi kỳ vọng |
| --- | --- | --- |
| TRUE | TRUE | Dùng quyền object tự động và có thể `SET ROLE` sang role được cấp |
| FALSE | TRUE | Không tự dùng quyền, nhưng có thể chủ động chuyển role khi cần |
| TRUE | FALSE | Tự dùng quyền được phép kế thừa, nhưng không được trực tiếp chuyển sang role đó theo đường SET này |
| FALSE | FALSE | Membership có thể phục vụ quản trị/cấu trúc, nhưng không tự cấp quyền object và không cho SET qua edge đó |

`ADMIN` là một trục khác. Có thể có `ADMIN TRUE` mà `INHERIT FALSE`; **quyền quản trị membership không tự biến thành SELECT/UPDATE trên bảng**.

### Phân biệt “được member” và “được dùng”

Một role có thể là thành viên trên catalog nhưng không có đường INHERIT thích hợp để tự dùng privilege, cũng không có đường SET phù hợp để chuyển role. Vì vậy chỉ hỏi “user có member role không?” **chưa đủ** để kết luận user thực thi được thao tác gì.

## 11. PostgreSQL 15 trở xuống khác điều gì?

Trước PostgreSQL 16, membership chưa có bộ option `INHERIT`/`SET` trên từng edge như ở PostgreSQL 16+. Hành vi kế thừa gắn nhiều hơn với thuộc tính `INHERIT`/`NOINHERIT` của member role.

Ví dụ lịch sử:

~~~sql
CREATE ROLE old_style_user LOGIN NOINHERIT;

GRANT old_style_group TO old_style_user;
~~~

Trong các phiên bản cũ, `NOINHERIT` cho biết role không tự dùng quyền membership theo cơ chế kế thừa mặc định, trong khi `SET ROLE` vẫn có semantics membership liên quan của version đó.

### Quy tắc quan trọng từ PostgreSQL 16

Ở PostgreSQL 16+:

- Thuộc tính `INHERIT`/`NOINHERIT` trên role liên quan đến **giá trị mặc định INHERIT của những membership grants mới** cho role đó.
- Mỗi membership đã tồn tại có `inherit_option` riêng.
- **`ALTER ROLE some_role NOINHERIT` không được xem là cách sửa hàng loạt/retroactive mọi membership edge đã cấp.**
- Muốn kiểm soát quyền kế thừa hiện có, phải xem và cấu hình options trên membership theo cơ chế version đang chạy.

Do vậy một hướng dẫn chỉ nói “`ALTER ROLE user NOINHERIT` rồi mọi quyền đều bị ngắt” có thể **sai trên PostgreSQL 16+** nếu grant trước đó vẫn mang `INHERIT TRUE`.

**Lab sau đây dùng cú pháp PostgreSQL 16+** để thể hiện rõ cả INHERIT và SET. Với PostgreSQL 15 trở xuống, cần điều chỉnh hướng dẫn membership cho đúng version; không chép máy móc cú pháp `WITH INHERIT FALSE, SET TRUE` vào server cũ.

## 12. Thiết lập lab: các role cấp cluster

**Để thực hành:** cần tài khoản admin có quyền tạo role và cấp membership thích hợp, cùng database thực hành riêng cho schema/table. Role có phạm vi **toàn cluster**, vì vậy không chạy trên cluster đang dùng tên `lab378_*` cho mục đích khác.

Các câu sau chỉ chạy **một lần**. Nếu role đã tồn tại, `CREATE ROLE` sẽ báo lỗi; đừng tự dùng `DROP ROLE ... CASCADE` trên cluster production để “reset” một cách nguy hiểm.

~~~sql
-- Chạy bằng role quản trị có quyền phù hợp.
-- Lab dành cho PostgreSQL 16+.
CREATE ROLE lab378_reader NOLOGIN;
CREATE ROLE lab378_writer NOLOGIN;

CREATE ROLE lab378_reporter LOGIN;
CREATE ROLE lab378_editor LOGIN;

GRANT lab378_reader TO lab378_reporter
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

### Lưu ý xác thực

Hai role login chưa được cấu hình password hay cơ chế xác thực thực tế. Có thể thử bằng `SET ROLE` từ một session quản trị được phép thực hiện thao tác đó, hoặc cấu hình đăng nhập an toàn riêng rồi kết nối trực tiếp.

Không mặc định `CREATE ROLE ... LOGIN` là đủ cho client đăng nhập từ internet.

### Vai trò của các membership

| Login | Đường membership | Quyền được tự dùng | Role có thể SET nếu đủ quyền theo đường đó |
| --- | --- | --- | --- |
| reporter | reader, INHERIT TRUE | Reader | Reader |
| editor | reader, INHERIT TRUE | Reader | Reader |
| editor | writer, INHERIT FALSE | Không tự dùng Writer | Writer |

Đây là mô hình demonstrative để quan sát `SET ROLE`, không phải khuyến nghị mọi ứng dụng web nên chuyển role mỗi request.

## 13. Tạo schema, table và dữ liệu demo

Thực hiện trong **database lab đã chọn**, với role quản trị có quyền tạo schema và table.

~~~sql
-- Chỉ chạy trong database thực hành.
CREATE SCHEMA lab378;

CREATE TABLE lab378.documents (
    doc_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    visibility text NOT NULL DEFAULT 'internal'
        CHECK (visibility IN ('internal', 'public')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

INSERT INTO lab378.documents (
    doc_id, title, body, visibility
)
VALUES
    (1, 'Role basics', 'Roles control privileges.', 'public'),
    (2, 'Internal note', 'For authorized readers.', 'internal'),
    (3, 'Membership', 'Members can inherit or set roles.', 'public');
~~~

Trong lab, admin đã tạo table nên admin là owner ban đầu. Hai group roles chỉ có các quyền mà ta sắp cấp; chúng **không tự sở hữu table**.

### Tại sao không dùng bảng hệ thống thật?

Chúng ta cần kiểm chứng privilege mà không tác động dữ liệu production. Bảng lab giúp dễ quan sát thành công/thất bại của thao tác và dọn dẹp có kiểm soát.

## 14. Cấp quyền schema và table

~~~sql
GRANT USAGE ON SCHEMA lab378
TO lab378_reader, lab378_writer;

GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;

GRANT SELECT, INSERT, UPDATE
ON TABLE lab378.documents
TO lab378_writer;
~~~

Ở đây:

- `lab378_reader` được đọc.
- `lab378_writer` được đọc, INSERT và UPDATE.
- Không role nào được cấp `DELETE` thông qua những grant này.
- Không role nào được cấp `CREATE` trên schema `lab378` thông qua lệnh trên.

### Vì sao writer cũng có SELECT?

SQL UPDATE thực tế thường đọc các cột trong `WHERE`, `RETURNING` hoặc biểu thức `SET`, và PostgreSQL cần SELECT phù hợp cho các cột được đọc. Cấp SELECT cho writer giúp các ví dụ UPDATE có điều kiện hoạt động.

Trong hệ thống chặt hơn, có thể dùng column-level grants hoặc SECURITY DEFINER function được review để giới hạn cách sửa dữ liệu thay vì cho writer mọi quyền đọc rộng.

## 15. Đọc table thường cần quyền ở nhiều lớp

Chỉ có:

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;
~~~

chưa chắc đủ nếu role không có `USAGE` trên schema `lab378`.

Thông thường để truy cập một table bằng tên:

1. Role cần được phép kết nối database.
2. Có quyền `USAGE` trên schema chứa table.
3. Có quyền `SELECT` trên table/các cột phù hợp.
4. Các chính sách RLS, nếu có, còn phải cho thấy hàng cần đọc.

### USAGE và CREATE trên schema khác nhau

~~~sql
GRANT USAGE ON SCHEMA lab378 TO lab378_reader;
~~~

cho phép tìm/định danh object trong schema theo quy tắc, **không cho tạo object mới**.

~~~sql
GRANT CREATE ON SCHEMA lab378 TO some_role;
~~~

mới cấp khả năng tạo object ở schema trong phạm vi được phép. **CREATE trên schema không đồng nghĩa tự có SELECT trên mọi table sẵn có.**

### Kết nối database lại là một privilege khác

`GRANT CONNECT ON DATABASE ...` phải thực hiện trên tên database cụ thể. Ví dụ ý tưởng:

~~~sql
-- MINH HỌA: chỉ dùng nếu thực sự có database shop_training.
GRANT CONNECT ON DATABASE shop_training
TO lab378_reporter, lab378_editor;
~~~

Không chạy câu này nếu database `shop_training` không tồn tại. Nhiều cài đặt PostgreSQL ban đầu đã cho `PUBLIC` quyền CONNECT ở một số database, nhưng chính sách có thể đã bị revoke; **phải kiểm tra cấu hình thực tế**.

## 16. Kiểm tra role và membership từ catalog

### Liệt kê role attributes

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolinherit,
    rolcreatedb,
    rolcreaterole,
    rolsuper,
    rolreplication,
    rolbypassrls
FROM pg_roles
WHERE rolname LIKE 'lab378_%'
ORDER BY rolname;
~~~

Những cột `rolcanlogin`, `rolinherit` và `rolsuper` là **thuộc tính role**, không phải danh sách đầy đủ object privileges.

### Liệt kê membership edges (PostgreSQL 16+)

~~~sql
SELECT
    member_role.rolname AS member_name,
    granted_role.rolname AS granted_role,
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member_role
    ON member_role.oid = m.member
JOIN pg_roles AS granted_role
    ON granted_role.oid = m.roleid
WHERE member_role.rolname LIKE 'lab378_%'
   OR granted_role.rolname LIKE 'lab378_%'
ORDER BY member_name, granted_role;
~~~

Trong PostgreSQL 16+, `pg_auth_members` có các cột `inherit_option`, `set_option`, `admin_option` để quan sát từng grant edge.

### Vì sao không chỉ xem rolinherit?

Đối với PostgreSQL 16+, `rolinherit` không đủ để kết luận **các membership đã tồn tại** hiện cho quyền kế thừa hay không. Cần kiểm tra từng edge ở `pg_auth_members` và các đường membership qua nhiều cấp.

## 17. Kiểm tra quyền tự động kế thừa

PostgreSQL có `pg_has_role`:

~~~sql
SELECT
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'MEMBER'
    ) AS is_reader_member,
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'USAGE'
    ) AS can_use_reader_automatically,
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'SET'
    ) AS can_set_reader;
~~~

Với PostgreSQL 16+, `MEMBER`, `USAGE` và `SET` có những ý nghĩa khác nhau:

- **MEMBER**: có quan hệ thành viên theo semantics được kiểm tra.
- **USAGE**: có thể dùng privileges role được cấp tự động, thông qua đường kế thừa phù hợp.
- **SET**: có thể chuyển sang role đó bằng `SET ROLE` theo những đường được phép.

### So sánh writer

~~~sql
SELECT
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'MEMBER'
    ) AS is_writer_member,
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'USAGE'
    ) AS auto_writer_privileges,
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'SET'
    ) AS can_set_writer;
~~~

Với grant lab, ý định là:

| Kiểm tra | Reader | Writer |
| --- | --- | --- |
| MEMBER | true | true |
| USAGE | true | false |
| SET | true | true |

**`SET` trong `pg_has_role` là lựa chọn kiểm tra của các phiên bản hỗ trợ nó**; trên server trước PostgreSQL 16, hãy dùng syntax/docs tương ứng. Không tự sao chép danh sách option của PG16+ cho server cũ.

## 18. Kiểm tra object privileges hiệu lực

~~~sql
SELECT
    has_schema_privilege(
        'lab378_editor',
        'lab378',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'SELECT'
    ) AS can_read_table,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'INSERT'
    ) AS can_insert_table,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'UPDATE'
    ) AS can_update_table;
~~~

Với thiết kế lab:

- Editor tự dùng được reader privileges (SELECT).
- Editor **chưa tự dùng được writer privileges** (INSERT/UPDATE) qua membership writer có INHERIT FALSE.
- Khi active writer bằng `SET ROLE`, quyền hiệu lực thay đổi.

### Hàm has_table_privilege có giới hạn diễn giải

`has_table_privilege` giúp kiểm tra object ACL/privileges theo ngữ cảnh role đã chọn, nhưng một truy vấn thực tế còn phụ thuộc schema access, RLS, column-level grants, role hiện hành và các ràng buộc khác.

Không viết một UI bảo mật chỉ dựa một boolean `has_table_privilege` rồi bỏ qua kiểm tra truy vấn thực tế và policies.

## 19. session_user, current_user, current_role

Khi một client đăng nhập với role `lab378_editor`, có thể quan sát:

~~~sql
SELECT
    session_user,
    current_user,
    current_role;
~~~

- `session_user`: danh tính session authorization ban đầu/hiện hành theo cơ chế SQL.
- `current_user`: danh tính dùng cho nhiều kiểm tra quyền ở thời điểm thực thi.
- `current_role`: về cơ bản đồng nghĩa với `current_user` trong PostgreSQL.

Thông thường ngay sau khi đăng nhập:

~~~text
session_user = lab378_editor
current_user = lab378_editor
current_role = lab378_editor
~~~

Sau `SET ROLE`, `current_user` đổi nhưng `session_user` thường vẫn là login role ban đầu.

### Tại sao quan trọng?

Một bảng audit ghi `current_user` có thể ghi tên group role `lab378_writer` sau SET ROLE, không còn trực tiếp cho biết nhân viên/login role nào thực hiện thao tác.

Muốn log danh tính session, cần hiểu `session_user` và cả lớp authentication/application identity. Không mặc định hai giá trị luôn giống nhau.

## 20. SET ROLE chuyển effective role

Giả sử đang kết nối như `lab378_editor` và có SET option tới writer:

~~~sql
SELECT session_user, current_user;

SET ROLE lab378_writer;

SELECT session_user, current_user;

RESET ROLE;

SELECT session_user, current_user;
~~~

Dự kiến:

| Thời điểm | session_user | current_user |
| --- | --- | --- |
| Trước SET ROLE | lab378_editor | lab378_editor |
| Sau SET ROLE writer | lab378_editor | lab378_writer |
| Sau RESET ROLE | lab378_editor | lab378_editor |

**`SET ROLE` không yêu cầu bạn nhập mật khẩu của role đích.** Permission được quyết định theo membership/SET path và quy tắc quản trị phù hợp.

### Có thể SET ROLE tới NOLOGIN không?

Có, khi session được phép: `NOLOGIN` chỉ ngăn role làm danh tính đăng nhập trực tiếp. Nó không nhất thiết ngăn một session được ủy quyền chủ động đảm nhận role bằng `SET ROLE`.

### SET ROLE không phải cấp quyền vĩnh viễn

`RESET ROLE` khôi phục ngữ cảnh role tương ứng. Quyền trên object không được sao chép sang role login do một lần SET ROLE.

## 21. Khi SET ROLE writer, không tự giữ tất cả quyền của editor

Một hiểu nhầm:

> “Tôi là editor, đã kế thừa reader. Tôi SET ROLE writer, vậy tôi chắc chắn có cả reader và writer cộng lại.”

Không nên suy luận như vậy.

`SET ROLE lab378_writer` đổi `current_user` sang writer; quyền hiệu lực phụ thuộc writer và các membership của **writer**. Những quyền thuộc login role editor không được mặc nhiên “cộng dồn” vào writer chỉ vì session_user vẫn là editor.

Vì vậy trong lab ta cấp writer cả `SELECT` và `INSERT/UPDATE` để writer có thể thực hiện các UPDATE có WHERE/RETURNING.

### Muốn writer dùng quyền reader thông qua group graph?

Có thể thiết kế:

~~~sql
-- Ví dụ thay đổi role graph; chỉ dùng nếu mong muốn trong chính sách.
GRANT lab378_reader TO lab378_writer
WITH INHERIT TRUE, SET TRUE;
~~~

Khi đó writer có một đường đến reader; các quyền inherited phụ thuộc options toàn đường.

**Tạo role graph lồng nhau cần được ghi rõ.** Không thêm membership tùy tiện để “chữa lỗi permission” rồi quên kiểm tra các đường ủy quyền mới.

## 22. Thực hành read-only như reporter

Hai cách thử:

1. **Tốt nhất:** đăng nhập thật bằng `lab378_reporter` sau khi cấu hình authentication.
2. **Trong lab:** dùng session admin/superuser được phép `SET ROLE lab378_reporter` để mô phỏng hiệu lực quyền.

~~~sql
SET ROLE lab378_reporter;

SELECT
    session_user,
    current_user;

SELECT
    doc_id,
    title,
    visibility
FROM lab378.documents
ORDER BY doc_id;

RESET ROLE;
~~~

Với lab, query SELECT thành công do:

- Reporter được reader membership với `INHERIT TRUE`.
- Reader được `USAGE` schema.
- Reader được `SELECT` table.

### Negative test: reporter không được INSERT

Chạy như reporter trong một câu lệnh riêng:

~~~sql
-- CỐ Ý PHÁT SINH permission denied.
SET ROLE lab378_reporter;

INSERT INTO lab378.documents (
    doc_id, title, body
)
VALUES (
    99, 'Not allowed', 'Should be rejected'
);

RESET ROLE;
~~~

Nếu INSERT báo lỗi ở transaction implicit thông thường, client có thể tiếp tục để RESET. Nếu đang trong **explicit BEGIN; ...**, transaction bị aborted và cần rollback trước khi reset/đi tiếp. Không tự chạy nối tiếp toàn bộ script negative test mà không quản lý trạng thái transaction.

## 23. Thực hành editor đọc tự động nhưng ghi cần SET ROLE

Thử SELECT trong ngữ cảnh editor:

~~~sql
SET ROLE lab378_editor;

SELECT doc_id, title
FROM lab378.documents
ORDER BY doc_id;

RESET ROLE;
~~~

SELECT thành công nhờ inherited reader membership.

### Negative test: ghi trực tiếp như editor

~~~sql
-- CỐ Ý PHÁT SINH permission denied:
SET ROLE lab378_editor;

UPDATE lab378.documents
SET body = 'Edited outside writer role'
WHERE doc_id = 1;

RESET ROLE;
~~~

Trong thiết kế lab PostgreSQL 16+, editor có `INHERIT FALSE` với writer, nên UPDATE không được tự động cấp qua membership writer. Nếu một đường privilege khác (direct grant, PUBLIC, group khác) cấp UPDATE, negative test có thể không thất bại — đây chính là lý do cần **kiểm tra các đường quyền hiệu lực**, không chỉ role grant vừa tạo.

### Positive test: SET ROLE writer

~~~sql
BEGIN;

-- Chạy từ session thật của editor, hoặc session admin
-- được phép mô phỏng các bước SET ROLE tương ứng.
SET ROLE lab378_writer;

UPDATE lab378.documents
SET body = 'Edited using explicit writer role'
WHERE doc_id = 1
RETURNING doc_id, title, body;

RESET ROLE;

ROLLBACK;
~~~

`ROLLBACK` khôi phục dữ liệu lab, nhưng không làm sai kết luận rằng writer có quyền UPDATE trong lúc được chọn.

### Lưu ý session pool

Nếu một connection được tái sử dụng và quên `RESET ROLE`, request tiếp theo có thể chạy với effective role của request trước. Đây là lỗi bảo mật nghiêm trọng trong connection pooling.

**Phải có protocol reset session state**, tốt nhất do pool/framework quản lý và được kiểm thử. Không dựa vào thiện chí lập trình viên nhớ RESET trong mọi đường exception.

## 24. INHERIT TRUE tự động dùng object privileges, không tự cấp LOGIN

Giả sử NOLOGIN role reader có quyền `SELECT` và editor kế thừa reader. Editor có thể đọc table vì **quyền đối tượng** được kế thừa.

Điều đó **không** khiến reader trở thành login account; cũng không khiến editor tự được `CREATEDB`/`SUPERUSER` từ một role khác. Những role attributes có quy tắc riêng.

### Ví dụ phân biệt

~~~sql
-- Chỉ để minh họa, KHÔNG chạy trong lab least privilege:
CREATE ROLE privileged_role NOLOGIN CREATEDB;
GRANT privileged_role TO lab378_reporter;
~~~

Không kết luận reporter có quyền tạo database tự động chỉ vì membership; cũng không nên cấp membership tới role có attribute mạnh trong hệ thống thật mà không xem khả năng SET ROLE/ADMIN OPTION.

**Role membership là một khả năng ủy quyền mạnh**, nhất là khi đích có quyền DDL hoặc special attributes.

## 25. Membership qua nhiều cấp và nhiều đường

Ví dụ đồ thị:

~~~text
analyst
  | INHERIT TRUE
  v
team_reader
  | INHERIT TRUE
  v
app_reader
  | SELECT
  v
app.documents
~~~

Nếu **từng edge trên đường kế thừa** cho phép inheritance, analyst có thể sử dụng quyền reader theo semantics áp dụng.

Nhưng nếu một edge có `INHERIT FALSE`, không thể chỉ nhìn edge đầu tiên rồi kết luận cả đường có thể tự kế thừa.

### Nhiều đường khác nhau

~~~text
analyst -> group_A -> app_reader
analyst -> group_B -> app_reader
~~~

Nếu một đường bị chặn nhưng đường kia vẫn cho inheritance, effective privilege có thể vẫn tồn tại. PostgreSQL kiểm tra quyền theo **các đường grant hiệu lực**, không chỉ một dòng trong catalog.

Do đó việc `REVOKE` một grant hoặc đổi một edge thành `INHERIT FALSE` không nhất thiết loại bỏ privilege nếu role còn đường khác.

## 26. ADMIN option là quyền quản lý membership

Ví dụ PG16+:

~~~sql
GRANT lab378_reader TO lab378_editor
WITH ADMIN TRUE;
~~~

Một member có admin option hợp lệ có thể có quyền cấp tiếp/quản lý membership của role tương ứng trong phạm vi các quy định PostgreSQL hiện hành.

### ADMIN không đồng nghĩa SELECT

Có ADMIN option cho `lab378_reader` không trực tiếp có nghĩa editor tự đọc được `lab378.documents` nếu không có đường inheritance hoặc SET phù hợp.

### Vì sao ADMIN rất nhạy cảm?

Người có thể cấp membership tiếp có thể mở rộng số người nhận quyền. Nếu role đích chứa privileges nhạy cảm, admin option có thể là đường leo thang ủy quyền.

Nguyên tắc:

- App runtime không cần ADMIN option.
- Chỉ admin/deployer thích hợp mới quản lý membership.
- Review người có CREATEROLE và ADMIN option.
- Khi nâng cấp major version, kiểm tra semantics quản lý membership vì PostgreSQL 16 thay đổi đáng kể các quy tắc về role administration.

Không tạo hàng loạt role có ADMIN TRUE để tiện triển khai.

## 27. ALTER ROLE INHERIT/NOINHERIT không phải sửa mọi grant cũ (PG16+)

Giả sử editor đã có:

~~~sql
GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE;
~~~

Sau đó thực hiện:

~~~sql
ALTER ROLE lab378_editor NOINHERIT;
~~~

Ở PostgreSQL 16+, điều này **không được hiểu là sửa retroactive edge reader -> editor đang có**. Thuộc tính trên role ảnh hưởng giá trị mặc định khi tạo membership grants mới, còn edge cũ giữ các options đã được cấp cho đến khi được quản lý lại.

### Làm thế nào kiểm chứng?

~~~sql
SELECT
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS granted
    ON granted.oid = m.roleid
JOIN pg_roles AS member
    ON member.oid = m.member
WHERE granted.rolname = 'lab378_reader'
  AND member.rolname = 'lab378_editor';
~~~

Không dựa riêng vào `pg_roles.rolinherit` để khẳng định quyền inherited của role hiện tại.

**Đây là khác biệt version quan trọng**; các tutorial PostgreSQL cũ có thể mô tả INHERIT theo cách không phản ánh hết cơ chế PG16+.

## 28. Thu hồi membership khác thu hồi object privilege

### Thu hồi role membership

~~~sql
REVOKE lab378_writer
FROM lab378_editor;
~~~

Editor không còn con đường membership writer vừa cấp, trừ khi có những đường cấp khác thông qua role graph.

### Thu hồi table permission

~~~sql
REVOKE UPDATE
ON TABLE lab378.documents
FROM lab378_writer;
~~~

Writer không còn quyền UPDATE **qua grant đó**, nhưng vẫn có thể nhận UPDATE từ role khác, PUBLIC, ownership hoặc một grant khác.

### So sánh

| Lệnh | Điều bị thay đổi |
| --- | --- |
| `REVOKE lab378_writer FROM lab378_editor` | Membership editor vào writer |
| `REVOKE UPDATE ON ... FROM lab378_writer` | Privilege UPDATE của writer trên object |
| `REVOKE SELECT ON ... FROM PUBLIC` | Một privilege được cấp cho pseudo-role PUBLIC |
| `ALTER ROLE ... NOLOGIN` | Khả năng đăng nhập của role |

Trong SQL privilege model, **REVOKE không phải “DENY” có ưu tiên tuyệt đối**. Nó loại bỏ grant được chỉ định; quyền có thể còn đến từ một đường khác.

## 29. PUBLIC là pseudo-role áp dụng cho mọi role

`PUBLIC` không phải một role bình thường để bạn tạo/xóa và quản lý membership như `app_reader`. Nó đại diện cho **mọi role** trong ngữ cảnh object privileges.

Ví dụ:

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO PUBLIC;
~~~

Nếu chạy, mọi role có đủ điều kiện schema/connect và các chính sách khác có thể nhận quyền SELECT thông qua PUBLIC.

**Đây là ví dụ nên tránh trong dữ liệu nhạy cảm**, không phải khuyến nghị mặc định.

### REVOKE FROM PUBLIC

~~~sql
REVOKE SELECT
ON TABLE lab378.documents
FROM PUBLIC;
~~~

Thu hồi direct PUBLIC grant đó, nhưng không nhất thiết loại mọi direct grant và membership privilege khác.

### Mặc định PUBLIC thay đổi theo object/version

Ví dụ:

- Một số database privileges thường được cấp cho PUBLIC theo mặc định khi tạo database.
- Privilege `EXECUTE` trên function có mặc định cần được xem xét.
- Quyền trên schema `public` thay đổi theo PostgreSQL major version và cách database được tạo/upgrade.

Không áp một câu “mọi PostgreSQL đều cho PUBLIC CREATE trên public schema” cho tất cả phiên bản. PostgreSQL 15 đã thay đổi các mặc định liên quan; hãy kiểm tra quyền thực tế.

## 30. Schema public và search_path là ranh giới bảo mật

Nhiều session mặc định có `search_path` như:

~~~text
"$user", public
~~~

Cấu hình thực tế có thể khác.

Nếu một schema trong search_path cho role không tin cậy quyền `CREATE`, họ có thể tạo function/operator/object có tên ảnh hưởng quá trình resolve tên không schema-qualified trong các câu SQL kém an toàn.

### Nguyên tắc

- Không cho application role quyền CREATE tùy ý trên schema dùng chung.
- Schema-qualify các object quan trọng trong migration/security-sensitive SQL.
- Khi dùng `SECURITY DEFINER`, đặt search_path an toàn theo tài liệu PostgreSQL.
- Kiểm tra schema owner và quyền `CREATE` của PUBLIC hoặc các role khác.
- Không nhầm `USAGE` với `CREATE`.

Lệnh xem search_path:

~~~sql
SHOW search_path;

SELECT current_schemas(true);
~~~

Không sửa search_path bừa bãi để “làm hết lỗi relation does not exist”; phải kiểm tra privilege và tên object đúng.

## 31. Quyền SELECT không đồng nghĩa mọi bảng trong schema đều có quyền đọc

~~~sql
GRANT USAGE ON SCHEMA lab378 TO lab378_reader;
~~~

không cấp SELECT từng table.

~~~sql
GRANT SELECT
ON ALL TABLES IN SCHEMA lab378
TO lab378_reader;
~~~

cấp SELECT cho **các relation phù hợp hiện có** trong schema tại thời điểm lệnh chạy.

**Không tự động áp cho mọi table sẽ được tạo về sau.** Muốn điều đó, cần `ALTER DEFAULT PRIVILEGES` theo đúng role tạo object, sẽ học ở phần sau.

### Cẩn thận với ALL TABLES

Lệnh này có thể bao gồm những relation không nên đọc như bảng audit, token hoặc nội dung mật. Trong production, nhiều tổ chức cấp quyền cụ thể cho từng table/view, hoặc chỉ cấp SELECT trên những view được thiết kế cho báo cáo.

Least privilege không phải đồng nghĩa “GRANT SELECT ON ALL TABLES” là an toàn trong mọi schema.

## 32. Quyền trên sequence tách biệt với table

Khi table dùng sequence, ví dụ `serial` hoặc `nextval(...)`, một INSERT có thể cần quyền trên sequence nếu statement thực sự gọi `nextval` theo cách yêu cầu.

Ví dụ:

~~~sql
GRANT USAGE
ON SEQUENCE lab378.some_sequence
TO lab378_writer;
~~~

Đoạn này **minh họa**, chỉ chạy nếu sequence `lab378.some_sequence` tồn tại.

Phải phân biệt:

- `GRANT INSERT ON table`: quyền chèn hàng.
- `GRANT USAGE ON sequence`: dùng một số thao tác của sequence.
- `GRANT SELECT ON sequence`: truy cập các chức năng đọc phù hợp.
- Identity columns có semantics riêng so với tự gọi một sequence, tùy phiên bản và loại thao tác.

**Không cấp ALL ON ALL SEQUENCES chỉ vì một INSERT bị lỗi** mà chưa xác định sequence nào thực sự cần và người gọi đang sử dụng chức năng gì.

## 33. Quyền theo cột và RETURNING

Thay vì toàn bảng, có thể cấp:

~~~sql
GRANT SELECT (doc_id, title)
ON TABLE lab378.documents
TO lab378_reader;
~~~

Đây là ví dụ quyền SELECT mức cột.

### Khi query cần cột chưa được cấp

~~~sql
SELECT doc_id, title, body
FROM lab378.documents;
~~~

Nếu reader chỉ được phép đọc `doc_id` và `title`, cột `body` cần quyền tương ứng; query có thể báo permission denied.

### UPDATE theo cột

~~~sql
GRANT UPDATE (title, body)
ON TABLE lab378.documents
TO lab378_writer;
~~~

Quyền UPDATE trên các cột không tự bảo đảm quyền SELECT trên các cột trong `WHERE`, biểu thức hoặc `RETURNING`. Phải thiết kế ACL theo đúng câu SQL thực tế.

### Hạn chế của column grants

- Không thay RLS nếu yêu cầu lọc hàng theo tenant.
- Không tự ẩn field ở view/function đã được expose theo cách khác.
- Cần bảo trì khi schema thêm cột nhạy cảm.

## 34. Ownership có những quyền đặc biệt

Owner của table thường có quyền quản lý cấu trúc/ACL của object, ví dụ `ALTER TABLE`/`DROP TABLE` theo điều kiện PostgreSQL, không phải chỉ đơn giản `SELECT/UPDATE`.

**Object ownership khác một GRANT SELECT.**

Ví dụ một service production cần UPDATE status, nhưng nếu account service là owner của table, một lỗi SQL nghiêm trọng có thể cho phép thay đổi DDL, quyền hoặc cấu trúc dữ liệu vượt xa nhu cầu.

### Các quyền đặc biệt của owner không chỉ là object privileges được thừa kế như SELECT

Một thành viên của owner role có thể cần `SET ROLE` sang owner để thực thi một số thao tác chỉ owner được phép, tùy operation và membership.

Vì vậy mẫu thông dụng:

- `app_owner NOLOGIN` sở hữu schema/tables.
- `app_runtime LOGIN` chỉ có DML grants thông qua nhóm quyền.
- `app_deployer LOGIN` có `SET ROLE app_owner` với phạm vi được kiểm soát cho migration.

Đừng dùng `GRANT ALL PRIVILEGES ON TABLE ...` để cố cấp quyền `DROP TABLE` cho app; `ALL PRIVILEGES` trên table không tương đương ownership/DDL authority.

## 35. Lab mở rộng: owner role và deployer

Các ví dụ này dành cho môi trường thực hành PG16+ có quyền admin phù hợp.

~~~sql
CREATE ROLE lab378_owner NOLOGIN;
CREATE ROLE lab378_deployer LOGIN;

GRANT CREATE ON SCHEMA lab378 TO lab378_owner;

GRANT lab378_owner TO lab378_deployer
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

Sau khi login bằng `lab378_deployer` hoặc dùng session được phép mô phỏng:

~~~sql
SET ROLE lab378_owner;

CREATE TABLE lab378.owner_example (
    example_id bigint PRIMARY KEY,
    description text NOT NULL
);

RESET ROLE;
~~~

Table `lab378.owner_example` được tạo trong ngữ cảnh effective role owner, nên owner của object là `lab378_owner`.

### Điều quan trọng

`lab378_owner` NOLOGIN không ngăn nó sở hữu table. Deployer có thể `SET ROLE` tới owner vì membership SET option, **không phải vì deployer có superuser**.

Trong production, cần kiểm soát chặt đường cấp SET/ADMIN tới owner; không cho app runtime tự chuyển sang owner nếu nó chỉ cần DML.

## 36. ALTER DEFAULT PRIVILEGES cho object sẽ tạo về sau

Một lệnh:

~~~sql
GRANT SELECT ON ALL TABLES IN SCHEMA lab378 TO lab378_reader;
~~~

chỉ xử lý **những table phù hợp đã tồn tại**. Đối với bảng mới do owner tạo, có thể định nghĩa default privileges:

~~~sql
-- Chạy với tư cách lab378_owner hoặc role có quyền quản lý
-- default privileges cho lab378_owner theo đúng version.
ALTER DEFAULT PRIVILEGES
FOR ROLE lab378_owner
IN SCHEMA lab378
GRANT SELECT ON TABLES TO lab378_reader;
~~~

Sau đó, khi `lab378_owner` tạo table mới trong schema `lab378`, grant mặc định phù hợp được áp dụng.

### Bẫy quan trọng

**Default privileges được chọn theo role tạo object.** Nếu migration chạy với `current_user = lab378_deployer` mà không `SET ROLE lab378_owner`, default privileges đặt `FOR ROLE lab378_owner` **không tự áp dụng chỉ vì deployer là thành viên của owner**.

Ví dụ quy trình rõ:

~~~sql
SET ROLE lab378_owner;

CREATE TABLE lab378.future_reports (
    report_id bigint PRIMARY KEY,
    report_title text NOT NULL
);

RESET ROLE;
~~~

Với default privilege đã thiết lập, reader có thể nhận quyền SELECT mới theo quy tắc.

### Không nhầm scope

Default privileges có thể có phạm vi global hoặc per-schema tùy lệnh, và việc REVOKE ở một scope không nhất thiết đảo ngược grant ở scope khác. Khi dùng `ALTER DEFAULT PRIVILEGES`, cần kiểm tra catalog/psql và đối chiếu quyền thực tế của table mới.

**Không dùng default privileges để mở tất cả bảng mật cho reader một cách vô tình.**

## 37. Permission của function không giống permission table

Một function có thể thực thi logic database trong một security context khác với direct table access.

PostgreSQL thường có các mặc định privilege liên quan `EXECUTE` trên function; tùy cách tạo và default privileges, `PUBLIC` có thể được EXECUTE nếu không revoke.

Ví dụ khái niệm:

~~~sql
REVOKE EXECUTE
ON FUNCTION lab378.some_function(integer)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab378.some_function(integer)
TO lab378_reader;
~~~

Chỉ thực thi nếu function với signature đó tồn tại.

### Vì sao đáng chú ý?

Có thể user không có quyền UPDATE table, nhưng có quyền EXECUTE một function `SECURITY DEFINER` mà function đó được thiết kế để thay table. Đây có thể là API database **có chủ đích**, hoặc lỗ hổng nếu function không validate authorization/input.

Đừng kiểm tra chỉ table ACL rồi tuyên bố user không có cách nào sửa dữ liệu.

## 38. SECURITY INVOKER và SECURITY DEFINER

**SECURITY INVOKER** (mặc định của nhiều function) dùng quyền của caller phù hợp với semantics function.

**SECURITY DEFINER** chạy với quyền của owner function trong phần thực thi thích hợp.

Ví dụ ý tưởng:

~~~sql
CREATE FUNCTION some_schema.safe_operation(p_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema
AS $fn$
BEGIN
    -- Chỉ thao tác đã được review kỹ, schema-qualify object.
    -- Kiểm tra tham số, caller identity và quyền nghiệp vụ phù hợp.
    NULL;
END;
$fn$;
~~~

Đoạn này **minh họa**, không chạy trực tiếp nếu chưa tạo schema/function ownership/security policy đầy đủ.

### Hai rủi ro

1. **Quyền nâng cao:** caller có thể tác động dữ liệu thông qua quyền owner function.
2. **search_path injection:** nếu function resolve tên object từ schema không tin cậy, caller có thể lợi dụng object được tạo để chi phối logic.

Chỉ cấp EXECUTE trên function được review, đặt search_path an toàn và tránh dynamic SQL không được quote đúng. Không bao giờ coi SECURITY DEFINER là cách “vượt permission denied” không cần threat modeling.

### SET ROLE trong SECURITY DEFINER

`SET ROLE` có những hạn chế trong context security-definer; không thiết kế function SECURITY DEFINER như một nơi cho caller tùy ý thực hiện `SET ROLE` để vượt kiểm soát. Dùng mô hình quyền rõ ràng thay vì dựa vào các tương tác session state phức tạp.

## 39. Row-level security (RLS) không được thay bằng role membership

Object privilege trả lời câu hỏi:

> Role này có quyền thực hiện SELECT/UPDATE trên table nói chung không?

RLS trả lời thêm câu hỏi:

> Trong table đó, **những hàng nào** role được phép đọc hoặc sửa?

Ví dụ một table chứa dữ liệu nhiều tenant có `tenant_id`. Một role đã được `GRANT SELECT` vẫn có thể chỉ nhìn thấy một phần hàng theo policy RLS.

### Các điều kiện cần quan tâm

- RLS được bật trên table.
- Policy `USING`/`WITH CHECK` phù hợp SELECT/UPDATE/INSERT.
- Owner table có thể bypass RLS theo mặc định nếu không dùng cơ chế `FORCE ROW LEVEL SECURITY` phù hợp.
- Superuser/role `BYPASSRLS` có thể bỏ qua RLS theo semantics hệ thống.
- `SET ROLE` sang role khác có thể thay current_user và tác động policy matching/quyền hiệu lực.
- Membership không tự biến role thường thành `BYPASSRLS` chỉ vì được cấp role mạnh.

### Cảnh báo về session variable tenant

Một số hệ thống dùng `current_setting('app.tenant_id')` trong RLS policy. Nếu người dùng database trực tiếp có thể tùy ý `SET app.tenant_id`, phải chứng minh cơ chế đó không cho giả mạo tenant theo threat model; session variable không tự là nguồn danh tính tin cậy.

**Role ACL và RLS nên là hai lớp có mục đích khác nhau**, không thay thế nhau.

## 40. Role mặc định và role hệ thống

PostgreSQL có một số predefined roles cho monitoring, đọc thống kê, quản trị chức năng cụ thể, với tên `pg_*`. Mức quyền/semantics có thể khác theo phiên bản.

Không cho application role membership trong một predefined role chỉ vì tên nghe “read only”. Một số predefined roles có thể cho đọc dữ liệu hoặc hành vi vượt nhu cầu của service.

Ví dụ kiểm tra role trong catalog:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_roles
WHERE rolname LIKE 'pg\_%' ESCAPE '\'
ORDER BY rolname;
~~~

Nếu cần dùng predefined role, đọc tài liệu chính thức **đúng major version**, xác định quyền thực tế và đánh giá ảnh hưởng đến RLS, data confidentiality hoặc server-wide monitoring.

### SUPERUSER là ngoại lệ lớn

Superuser được tin cậy quản trị cluster, có khả năng vượt nhiều kiểm tra quyền thông thường. Chỉ dùng cho các tác vụ hành chính thật sự cần và cách ly credentials.

## 41. CREATEROLE không phải “admin an toàn tuyệt đối”

`CREATEROLE` cho quản lý roles trong phạm vi rules PostgreSQL; khả năng cụ thể thay đổi đáng kể qua các phiên bản, đặc biệt PostgreSQL 16.

Một role có CREATEROLE có thể tác động membership, role attributes và đường ủy quyền theo các giới hạn hiện hành. Đây là quyền nhạy cảm không nên cấp cho application runtime.

### Nguyên tắc

- Quản lý role qua IaC/migrations được review.
- Phân biệt role admin và application login.
- Theo dõi membership grants kèm ADMIN option.
- Không dựa vào tài liệu cũ để kết luận chính xác CREATEROLE có/không được làm điều gì trong version mới.
- Có bước xác nhận security reviewer trước khi tạo role đặc quyền cao.

## 42. Quyền với database: CONNECT, CREATE và TEMPORARY

Một database có privilege types đặc thù:

- `CONNECT`: cho phép kết nối database.
- `CREATE`: cho phép tạo schema hoặc một số object cấp database theo semantics.
- `TEMPORARY`/`TEMP`: cho phép tạo temporary tables.

Ví dụ minh họa với một database lab tên `shop_training`:

~~~sql
-- Chỉ dùng nếu database shop_training thực sự tồn tại.
REVOKE CONNECT ON DATABASE shop_training FROM PUBLIC;

GRANT CONNECT ON DATABASE shop_training
TO lab378_reporter, lab378_editor;

GRANT TEMPORARY ON DATABASE shop_training
TO lab378_editor;
~~~

Cần xác định chính sách production trước khi revoke CONNECT khỏi PUBLIC vì có thể làm gián đoạn nhiều client.

### Không nhầm CONNECT và LOGIN

- `LOGIN` là role attribute.
- `CONNECT` là database object privilege.
- Xác thực qua pg_hba/password/TLS là bước riêng.

Một role LOGIN nhưng không CONNECT database mục tiêu có thể bị từ chối. Một NOLOGIN role có CONNECT không thể tự login trực tiếp.

## 43. Default schema privileges và version

Từ PostgreSQL 15, database mới có thay đổi về default ownership/CREATE trên schema `public` so với nhiều cài đặt lịch sử.

Không nên dạy:

> “Mọi user PostgreSQL luôn có CREATE trên schema public”.

Sai với nhiều phiên bản/cài đặt/hệ thống đã harden.

### Cách kiểm tra thay vì đoán

~~~sql
SELECT
    nspname,
    nspowner::regrole AS schema_owner,
    nspacl
FROM pg_namespace
WHERE nspname = 'public';
~~~

Và với một role cụ thể:

~~~sql
SELECT
    has_schema_privilege(
        'lab378_editor',
        'public',
        'USAGE'
    ) AS may_use_public,
    has_schema_privilege(
        'lab378_editor',
        'public',
        'CREATE'
    ) AS may_create_in_public;
~~~

Chỉ dựa trên kết quả của cluster/database thực tế và security policy đã được review.

## 44. \du và \dp trong psql

Khi dùng psql, một số meta-command rất tiện:

~~~text
\du
\du+ lab378_editor
\dn+ lab378
\dp lab378.documents
\ddp
~~~

Ý nghĩa:

| Lệnh psql | Mục đích |
| --- | --- |
| `\du` | Liệt kê role và một số attributes/memberships |
| `\du+` | Thông tin role chi tiết hơn |
| `\dn+` | Schema và privilege liên quan |
| `\dp` / `\z` | Quyền object |
| `\ddp` | Default privileges |

Các lệnh bắt đầu bằng dấu `\` **không phải SQL statement**; chúng do psql client diễn giải. Không chạy trực tiếp chúng qua JDBC `PreparedStatement`.

### Catalog truy vấn chính xác hơn khi nào?

Khi cần:

- Lọc nhiều role theo tiền tố.
- So sánh tùy chọn membership PG16+.
- Export thông tin quyền phục vụ review.
- Truy vấn quyền hiệu lực của một role cụ thể.

Lúc đó dùng `pg_roles`, `pg_auth_members` và các hàm privilege là hợp lý.

## 45. Kiểm tra privilege graph không đơn giản là nhìn ACL

Giả sử table ACL có grant `SELECT TO lab378_reader`. Một account editor đọc được thông qua membership, nhưng không có dòng `GRANT SELECT ... TO lab378_editor` trực tiếp.

Vì vậy:

- `pg_class.relacl`/`\dp` cho biết object grant ACL.
- `pg_auth_members` cho biết membership edges.
- `pg_has_role` cho biết quan hệ/quyền sử dụng role.
- `has_table_privilege` cho biết privilege hiệu lực theo kiểm tra tương ứng.
- Một câu SELECT thực tế dưới role ứng dụng xác nhận kết quả còn phụ thuộc schema/RLS.

**Audit quyền cần ghép thông tin nhiều lớp, không chỉ grep một dòng GRANT.**

## 46. Revocation không luôn chặn quyền ngay theo trực giác

Các tình huống đáng kiểm thử:

1. Role có direct SELECT, đồng thời inherited SELECT → revoke một đường vẫn còn đường kia.
2. PUBLIC được SELECT → revoke khỏi reader chưa làm table private.
3. Role có membership qua hai group → chặn một edge chưa chặn edge còn lại.
4. Session đã `SET ROLE` sang role khác → effective privileges cần xem theo current_user.
5. Function SECURITY DEFINER có thể thực thi một thao tác mà caller không được làm trực tiếp.
6. Owner object có những special rights vượt object ACL thông thường.
7. RLS có thể vẫn lọc hàng dù table SELECT được cấp.

### Quy trình giảm quyền

- Xác định tất cả đường trực tiếp/gián tiếp.
- Thiết kế trạng thái quyền mong muốn.
- Thực hiện REVOKE/GRANT/đổi membership options theo version.
- Kiểm tra `pg_has_role` và `has_*_privilege`.
- Đăng nhập/mô phỏng bằng application role và thử truy vấn thật.
- Kiểm tra connection pool/active sessions và cơ chế refresh quyền khi cần.
- Giám sát permission errors sau triển khai.

Không hứa rằng một lệnh REVOKE đơn lẻ luôn chặn mọi thao tác ngay lập tức trong mọi session/context.

## 47. Role và audit: session_user chưa phải danh tính người dùng web

Trong ứng dụng web, hàng trăm nghìn user có thể dùng cùng database login `app_api`. PostgreSQL nhìn thấy `session_user = app_api`, không tự biết request được gửi bởi người dùng web nào.

Để audit chính xác, hệ thống có thể cần:

- App-layer authenticated user ID.
- Signed/validated request identity từ service tin cậy.
- Các thông tin transaction context được truyền theo giao thức chống giả mạo phù hợp.
- Audit events ghi business actor ID, role DB, transaction/request IDs riêng.
- Quyền hạn chế đối với bảng audit.

### Khi dùng SET ROLE

`current_user` có thể là role NOLOGIN group sau SET ROLE; `session_user` vẫn là DB login. Phân biệt hai trường khi ghi audit.

Không dùng `current_user` đơn độc làm bằng chứng pháp lý rằng một con người cụ thể đã thao tác.

## 48. SET ROLE và connection pooling

Connection pool giữ nhiều session sống lâu. Nếu một request thực hiện:

~~~sql
SET ROLE lab378_writer;
~~~

rồi gặp exception và quên:

~~~sql
RESET ROLE;
~~~

request tiếp theo mượn lại connection có thể chạy với writer privileges.

### Biện pháp

1. Dùng pool có cơ chế reset session state được chứng minh và kiểm thử.
2. Có `try/finally`/transaction boundary rõ khi đổi effective role.
3. Không để user input tùy ý quyết định tên role trong `SET ROLE`.
4. Nếu dùng `SET LOCAL ROLE` (khi phù hợp trong version/ngữ cảnh), hiểu đúng transaction scope và thử rollback/commit.
5. Không dùng connection production superuser làm pool runtime.
6. Theo dõi `session_user/current_user` trong test xác thực.

**SQL role switching là trạng thái security-critical của session**, không chỉ là một biến tiện ích.

## 49. Các lỗi nguy hiểm khi tạo role

### 49.1. Cho app user SUPERUSER

Chỉ để “hết permission denied” nhưng phá nguyên tắc least privilege.

### 49.2. Cho app user sở hữu mọi table

Ứng dụng có quyền DDL/ownership không cần thiết; nên tách owner và runtime.

### 49.3. Dùng một role LOGIN làm nhóm quyền cho mọi service

Có thể mở rộng diện tấn công và khó rotation. NOLOGIN group roles giúp tách privilege bundle khỏi credentials.

### 49.4. Nghĩ NOLOGIN role không thể bị lạm dụng

Một member có SET option hợp lệ có thể đảm nhận NOLOGIN role.

### 49.5. Nghĩ role member tự có mọi attributes

LOGIN/SUPERUSER/CREATEDB/BYPASSRLS không được kế thừa như SELECT.

### 49.6. Nghĩ membership tự luôn cấp privileges

PG16+ có INHERIT FALSE, SET FALSE; membership không đồng nghĩa tự dùng quyền.

### 49.7. Nghĩ ALTER ROLE NOINHERIT sửa retroactively toàn bộ grants

Không đúng ở PG16+ với per-membership inherit_option.

### 49.8. Nhầm ADMIN với SET hoặc INHERIT

Ba option độc lập với mục tiêu khác nhau.

### 49.9. Dùng GRANT ALL PRIVILEGES để thay ownership

Table privileges không tự cho DROP/ALTER như owner.

### 49.10. Chỉ cấp SELECT mà quên schema USAGE

Truy vấn có thể bị từ chối ở bước namespace resolution.

### 49.11. Quên CONNECT database

LOGIN không tự đảm bảo kết nối vào database đã revoke PUBLIC CONNECT.

### 49.12. Quên sequence privilege

Một số INSERT sử dụng sequence có thể báo permission denied.

### 49.13. Cho ALL TABLES IN SCHEMA khi có bảng bí mật

Đọc quá rộng, đặc biệt audit, token, PII.

### 49.14. Nghĩ grant ALL TABLES tự áp cho table tương lai

Cần default privileges phù hợp role tạo object.

### 49.15. Đặt default privileges FOR ROLE sai owner

Migration tạo object bằng role khác nên default grants không được áp.

### 49.16. Nghĩ REVOKE là DENY tuyệt đối

Privilege có thể còn từ PUBLIC, direct grant, membership path khác hoặc ownership.

### 49.17. Không xem pg_auth_members khi debug quyền

Một quyền hiệu lực có thể đến từ nhiều tầng role khác nhau.

### 49.18. Dùng SET ROLE mà không reset connection

Làm rò quyền sang request tiếp theo trong connection pool.

### 49.19. Dùng SECURITY DEFINER không khóa search_path

Tăng nguy cơ object-name hijacking và vượt quyền.

### 49.20. Tưởng RLS tự áp với mọi role kể cả superuser/owner

Có bypass và FORCE RLS semantics cần kiểm tra.

### 49.21. Lưu plaintext password trong migration và logs

Lộ credentials qua git, CI, shell history và error log.

### 49.22. Không phân biệt session_user và current_user

Ghi audit sai danh tính effective role.

### 49.23. Dùng docs PostgreSQL cũ cho options PG16+

Dễ hiểu nhầm inheritance/SET/admin behavior.

### 49.24. Quên kiểm thử role thực tế

Superuser có thể đọc được mọi thứ dù config app role sai; phải test bằng non-superuser tương ứng.

## 50. Quy tắc thực hành phân quyền production

Một phương án thường có các bước:

1. Tạo owner NOLOGIN cho schema/tables.
2. Tạo nhóm NOLOGIN theo thao tác thực tế: reader, writer, reporting.
3. Tạo login role riêng cho từng service hoặc loại client.
4. Cấp `USAGE` schema và object grants chính xác.
5. Cấp memberships với INHERIT/SET/ADMIN options phù hợp version.
6. Chỉ cho deployer SET ROLE owner trong pipeline migration.
7. Không cấp app runtime CREATE/ALTER/DROP nếu không cần.
8. Cấu hình CONNECT/TEMP/database privileges theo policy.
9. Rà soát PUBLIC/default privileges.
10. Bật RLS khi cần isolation hàng và kiểm thử bypass conditions.
11. Hạn chế SECURITY DEFINER và EXECUTE privileges.
12. Quản lý mật khẩu/secret/TLS/pg_hba bên ngoài SQL grant.
13. Kiểm thử negative cases bằng actual login role.
14. Quan sát catalog và lưu changes như migration/IaC.
15. Thu hồi quyền cũ và kiểm tra không còn đường alternative.
16. Kiểm tra connection pool không giữ effective role cũ.

### Phân biệt “quyền kỹ thuật” và “quyền nghiệp vụ”

Một SQL role có UPDATE trên table không tự biết người dùng có quyền sửa **đơn hàng cụ thể** đó hay không. Cần thêm application authorization và có thể RLS/secured functions để thực thi chính sách nghiệp vụ.

## 51. Kịch bản phân quyền theo nhóm đọc/ghi

| Trường hợp | Role login | Membership | Hành vi |
| --- | --- | --- | --- |
| Báo cáo đọc documents | reporter | reader INHERIT TRUE | SELECT được |
| Báo cáo INSERT documents | reporter | reader | INSERT bị chặn nếu không có grant khác |
| Editor đọc bình thường | editor | reader INHERIT TRUE | SELECT được |
| Editor UPDATE trước SET ROLE | editor | writer INHERIT FALSE | UPDATE bị chặn nếu không có grant khác |
| Editor SET ROLE writer rồi UPDATE | editor | writer SET TRUE | UPDATE được theo quyền writer |
| Editor RESET ROLE | editor | role gốc | Quay lại hiệu lực quyền editor |
| Deployer SET ROLE owner | deployer | owner SET TRUE | DDL theo quyền owner |
| Runtime SELECT bảng khác | runtime | chưa có grant | Chỉ được nếu quyền từ đường khác/owner/PUBLIC cho phép |

Bảng này giả định đúng các grants của lab, **không có quyền bất ngờ từ PUBLIC hoặc role khác**. Kết quả thực trên cluster có thể khác nếu tồn tại các đường grant ngoài lab.

## 52. Bài tập thực hành có đáp án

Các bài tập dùng `lab378` và `lab378_*` đã tạo. Những lệnh cố ý gây lỗi nên chạy riêng và khôi phục transaction trước khi tiếp tục. Mỗi ví dụ có thay đổi dữ liệu nên dùng `BEGIN ... ROLLBACK` nếu chỉ thử nghiệm.

### Bài 1. Role là gì?

**Đáp án:** Danh tính PostgreSQL dùng để nhận privileges, sở hữu object và có thể là member của role khác. Role có thể có hoặc không có LOGIN.

### Bài 2. LOGIN khác CONNECT ra sao?

**Đáp án:** LOGIN là role attribute cho phép dùng role làm danh tính kết nối; CONNECT là privilege trên database. Còn cần authentication policy phù hợp.

### Bài 3. NOLOGIN có thể sở hữu table không?

**Đáp án:** Có. Role NOLOGIN có thể sở hữu object; nó chỉ không login trực tiếp.

### Bài 4. Tạo một nhóm read-only

~~~sql
CREATE ROLE example_reader NOLOGIN;
~~~

**Đáp án:** Đây mới là role rỗng; để đọc table cần cấp schema/table privileges hoặc membership phù hợp.

### Bài 5. Cấp SELECT trên table lab

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;
~~~

**Đáp án:** Reader có table SELECT; cần schema USAGE và các quyền/điều kiện khác để chạy query.

### Bài 6. Cấp schema USAGE

~~~sql
GRANT USAGE
ON SCHEMA lab378
TO lab378_reader;
~~~

**Đáp án:** Cho dùng namespace schema, không cấp quyền CREATE và không tự cấp SELECT trên mọi table.

### Bài 7. Cấp membership là gì?

~~~sql
GRANT lab378_reader TO lab378_reporter;
~~~

**Đáp án:** Reporter trở thành member của reader theo grant options/defaults của version; đây không phải direct table grant.

### Bài 8. PG16+: Writer không tự kế thừa nhưng cho SET

~~~sql
GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE;
~~~

**Đáp án:** Editor không tự dùng writer object privileges qua edge đó, nhưng có thể SET ROLE writer nếu có đường permission phù hợp.

### Bài 9. INHERIT và SET có giống nhau?

**Đáp án:** Không. INHERIT điều khiển sử dụng object privileges tự động; SET điều khiển khả năng chuyển current role theo đường membership.

### Bài 10. ADMIN option là gì?

**Đáp án:** Quyền quản trị/cấp membership của role được cấp theo quy tắc PostgreSQL; không tự cho SELECT/UPDATE trên table.

### Bài 11. Role attribute nào không được kế thừa như SELECT?

**Đáp án:** Những special attributes như SUPERUSER, CREATEDB, CREATEROLE, LOGIN, REPLICATION và BYPASSRLS không được tự cộng vào member role qua inheritance như table privileges.

### Bài 12. PostgreSQL role tồn tại ở đâu?

**Đáp án:** Cấp cluster. Object grants trên bảng/schema thường là theo object của database tương ứng.

### Bài 13. current_user sau SET ROLE?

~~~sql
SET ROLE lab378_writer;

SELECT session_user, current_user;

RESET ROLE;
~~~

**Đáp án:** current_user chuyển sang writer; session_user thường vẫn là login role ban đầu.

### Bài 14. Writer NOLOGIN có thể SET ROLE đến không?

**Đáp án:** Có nếu session có quyền SET đến role đó. NOLOGIN chỉ ngăn đăng nhập trực tiếp.

### Bài 15. Editor có tự dùng quyền writer nếu INHERIT FALSE?

**Đáp án:** Không qua edge đó. Nhưng có thể có đường grant khác, nên phải kiểm tra effective privileges tổng thể.

### Bài 16. Đọc quyền membership options

~~~sql
SELECT
    r.rolname AS granted_role,
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS r
    ON r.oid = m.roleid
JOIN pg_roles AS u
    ON u.oid = m.member
WHERE u.rolname = 'lab378_editor';
~~~

**Đáp án:** Dùng trên PostgreSQL 16+ để xem từng membership edge của editor.

### Bài 17. pg_has_role MEMBER khác USAGE?

**Đáp án:** MEMBER kiểm tra quan hệ thành viên, USAGE kiểm tra khả năng dùng role privileges tự động theo các đường kế thừa phù hợp.

### Bài 18. pg_has_role SET?

**Đáp án:** Trên PostgreSQL hỗ trợ, kiểm tra khả năng SET ROLE theo đường membership hợp lệ.

### Bài 19. Kiểm tra editor có SELECT

~~~sql
SELECT has_table_privilege(
    'lab378_editor',
    'lab378.documents',
    'SELECT'
);
~~~

**Đáp án:** Trong lab thường true nhờ reader INHERIT TRUE, trừ khi grants/đường khác đã được chỉnh.

### Bài 20. Kiểm tra editor có UPDATE tự động

~~~sql
SELECT has_table_privilege(
    'lab378_editor',
    'lab378.documents',
    'UPDATE'
);
~~~

**Đáp án:** Trong lab thường false vì writer INHERIT FALSE và không có đường UPDATE khác.

### Bài 21. Tại sao REVOKE một grant có thể không hết quyền?

**Đáp án:** User có thể còn direct grant, PUBLIC privilege, membership qua role khác hoặc owner special rights.

### Bài 22. PUBLIC là role thường không?

**Đáp án:** Không. Đây là pseudo-role đại diện mọi role khi cấp object privileges, không phải group role tạo/dùng như thông thường.

### Bài 23. Một role được SELECT nhưng không USAGE schema?

**Đáp án:** Truy cập relation qua schema có thể bị từ chối; cần quyền USAGE/schema hoặc ngữ cảnh được phép thích hợp.

### Bài 24. ALL TABLES áp cho table tương lai không?

**Đáp án:** Không tự động. Phải dùng ALTER DEFAULT PRIVILEGES cho role tạo object và schema tương ứng.

### Bài 25. Default privileges FOR ROLE owner có áp khi deployer tạo bảng không SET ROLE không?

**Đáp án:** Không tự động chỉ do deployer là member; default privilege gắn với role thực sự tạo object.

### Bài 26. Table owner có thể DROP table do GRANT ALL không?

**Đáp án:** GRANT ALL object privileges không chuyển ownership/DDL rights. DROP/ALTER phụ thuộc owner/membership và các quyền liên quan.

### Bài 27. RLS có giống GRANT SELECT không?

**Đáp án:** Không. SELECT privilege cho phép thao tác trên table; RLS có thể giới hạn từng hàng. Chủ table/superuser/BYPASSRLS có quy tắc bypass cần kiểm tra.

### Bài 28. App role có nên SUPERUSER để tránh permission denied?

**Đáp án:** Không. Dùng least privilege, xử lý đúng schema/table/sequence grants và app authorization.

### Bài 29. SET ROLE trong connection pool cần chú ý gì?

**Đáp án:** Phải reset/kiểm soát session state chắc chắn; nếu không, request sau có thể nhận quyền effective role của request trước.

### Bài 30. SECURE FUNCTION cần lưu ý gì?

**Đáp án:** Với SECURITY DEFINER, kiểm soát owner, EXECUTE, search_path, dynamic SQL, input validation và caller authorization để tránh privilege escalation.

### Bài 31. Khi nào dùng owner NOLOGIN?

**Đáp án:** Khi muốn role sở hữu schema/table không có credentials đăng nhập trực tiếp, và deployer được SET ROLE owner theo quyền quản lý phù hợp.

### Bài 32. Khi nào nên cấp ADMIN TRUE?

**Đáp án:** Chỉ cho role cần quản trị membership. App runtime thông thường không cần ADMIN.

### Bài 33. Vì sao không thể suy quyền chỉ từ rolinherit ở PG16+?

**Đáp án:** Vì inheritance là per-membership option trên từng edge; ALTER ROLE NOINHERIT không tự đổi mọi grant cũ.

### Bài 34. Tại sao chỉ nhìn table ACL chưa đủ?

**Đáp án:** Quyền có thể đến từ role graph, PUBLIC, owner, function SECURITY DEFINER, schema access hoặc RLS. Cần ghép nhiều lớp và thử bằng role thật.

### Bài 35. Có nên dùng mật khẩu literal trong CREATE ROLE migration?

**Đáp án:** Không nên lưu secret plaintext trong repo/CI logs. Dùng secret manager hoặc cơ chế credential setup an toàn.

### Bài 36. Đâu là quy trình gỡ một quyền?

**Đáp án:** Tìm tất cả đường grant, REVOKE hoặc đổi membership cần thiết, xem catalogs/functions, thử bằng application role, kiểm tra connection pool và giám sát permission failures.

## 53. Checklist triển khai

- [ ] Xác định PostgreSQL major version, đặc biệt semantics membership từ PostgreSQL 16.
- [ ] Phân biệt role cluster-wide với object grants theo database/schema.
- [ ] Tạo NOLOGIN roles cho nhóm quyền và owner, LOGIN roles cho connection identities.
- [ ] Không cấp SUPERUSER/CREATEROLE/CREATEDB/BYPASSRLS cho runtime nếu không thật sự cần.
- [ ] Đảm bảo LOGIN role còn thỏa authentication, pg_hba/TLS và database CONNECT.
- [ ] Tách reader, writer, deployer, owner theo trách nhiệm.
- [ ] Cấp schema USAGE và object privileges đủ nhưng không rộng.
- [ ] Chỉ cấp CREATE schema cho role cần tạo object.
- [ ] Cấp membership với INHERIT/SET/ADMIN options rõ trên PG16+.
- [ ] Không suy role attributes được inherited như table SELECT.
- [ ] Kiểm tra nhiều đường membership, không chỉ một edge.
- [ ] Dùng `pg_has_role` để phân biệt MEMBER/USAGE/SET khi version hỗ trợ.
- [ ] Dùng `has_table_privilege`/`has_schema_privilege` và truy vấn thực với non-superuser.
- [ ] Không coi REVOKE là DENY tuyệt đối; kiểm tra PUBLIC/direct/indirect grants.
- [ ] Review PUBLIC privileges và schema public theo version, không dựa giả định lịch sử.
- [ ] Kiểm tra sequence grants khi INSERT dùng sequence.
- [ ] Kiểm soát column-level SELECT/UPDATE khi có dữ liệu nhạy cảm.
- [ ] Phân biệt object owner với table privileges thông thường.
- [ ] SET ROLE owner có kiểm soát trong migration, không để app runtime assume owner.
- [ ] Quản lý ALTER DEFAULT PRIVILEGES đúng role thực sự tạo object.
- [ ] Hạn chế PUBLIC EXECUTE và review SECURITY DEFINER functions.
- [ ] Dùng search_path an toàn cho security-sensitive SQL.
- [ ] Áp RLS khi cần isolation theo hàng; kiểm tra owner/BYPASSRLS behavior.
- [ ] Không dựa DB current_user như định danh end user web duy nhất.
- [ ] Không hard-code password, dùng secret rotation/TLS.
- [ ] Reset role/session state trong connection pool.
- [ ] Thử cả positive và permission-denied cases bằng role không đặc quyền.
- [ ] Có migration/audit trail cho CREATE ROLE/GRANT/REVOKE.
- [ ] Không xóa role cluster-wide khi chưa kiểm tra dependencies và scope.

## 54. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo **major version của server** vì semantics membership và quyền quản trị role đã thay đổi qua nhiều phiên bản:

- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — giới thiệu roles.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html) — LOGIN, SUPERUSER, CREATEDB, CREATEROLE, INHERIT, BYPASSRLS.
- [Role Membership](https://www.postgresql.org/docs/current/role-membership.html) — GRANT/REVOKE role, INHERIT/SET/ADMIN options, các đường membership.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — quyền trên object, PUBLIC, ownership và ACL.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — tạo role.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — thay role attributes.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html) — object privilege grants và role membership.
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html) — thu hồi grants.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html) — thay effective current role.
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html) — grants cho object sẽ được tạo.
- [Information Functions](https://www.postgresql.org/docs/current/functions-info.html) — current_user, pg_has_role, has_table_privilege và các hàm khác.
- [System Catalog pg_auth_members](https://www.postgresql.org/docs/current/catalog-pg-auth-members.html) — thành viên role và options.
- [System View pg_roles](https://www.postgresql.org/docs/current/view-pg-roles.html) — role metadata.
- [Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html) — schema USAGE/CREATE, search_path.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS và bypass conditions.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — kiểm soát function privileges, SECURITY DEFINER.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html) — pg_hba, xác thực.
- [Password Authentication](https://www.postgresql.org/docs/current/auth-password.html) — SCRAM và bảo vệ credentials.

`/current/` trỏ tới tài liệu PostgreSQL hiện hành; khi triển khai trên PostgreSQL 15 hoặc cũ hơn, **không sử dụng mù quáng options membership của PostgreSQL 16+**.

## 55. Tổng kết

**Role là danh tính quyền trong PostgreSQL, LOGIN là khả năng đăng nhập, membership là quan hệ giữa roles, còn quyền kế thừa phụ thuộc cách những quan hệ đó được cấu hình.**

Những điểm cần ghi nhớ:

1. **Role có phạm vi toàn cluster**; quyền schema/table/database vẫn là các object privileges riêng.
2. **LOGIN không tự cấp CONNECT hay SELECT**. Còn cần authentication và các điều kiện quyền khác.
3. **NOLOGIN phù hợp cho permission groups và owner roles**, nhưng session đủ quyền vẫn có thể SET ROLE đến chúng.
4. **`GRANT SELECT ON table TO role` khác `GRANT role TO member`**: một câu cấp quyền object, câu còn lại cấp membership.
5. **PostgreSQL 16+ tách INHERIT, SET và ADMIN theo từng membership grant**. Có membership không có nghĩa tự động dùng privileges, được SET ROLE hay được quản trị membership.
6. **Role attributes đặc biệt không được kế thừa như object privileges**. Không nhầm SUPERUSER/CREATEDB/CREATEROLE/LOGIN với SELECT.
7. **`SET ROLE` đổi current_user**, thường không đổi session_user; `RESET ROLE` trả effective role về ngữ cảnh ban đầu.
8. **ALTER ROLE NOINHERIT ở PG16+ không retroactively đổi mọi membership options đã tồn tại**.
9. **REVOKE không phải DENY tuyệt đối**: quyền có thể còn do PUBLIC, grant trực tiếp, role graph, ownership hoặc routine có nâng quyền.
10. **Schema USAGE, database CONNECT, table privileges, RLS và function EXECUTE là những lớp khác nhau**; phải xem đồng thời.
11. **Owner NOLOGIN + deployer SET ROLE owner + runtime ít quyền** là một mô hình đáng cân nhắc để tách DDL khỏi DML.
12. **Kiểm chứng quyền bằng catalogs, các hàm privilege và truy vấn dưới login role thực tế**, không kết luận chỉ từ một dòng GRANT.
13. **Kết hợp phân quyền với kiểm soát session pool, secrets, SECURITY DEFINER và RLS** để tránh quyền rò rỉ qua những đường không mong muốn.

Khi mô hình hóa rõ **ai đăng nhập, thuộc nhóm quyền nào, tự kế thừa gì, được chuyển sang role nào và có quyền trên object nào**, hệ thống PostgreSQL trở nên dễ kiểm toán, an toàn hơn và dễ mở rộng mà không phải trao đặc quyền quá mức cho ứng dụng.
