# Quản lý role, database, schema và quyền sở hữu theo vòng đời trong PostgreSQL

## 1. Vì sao cần quản lý quyền theo vòng đời?

PostgreSQL sử dụng role để quản lý danh tính, quyền đăng nhập, quyền quản trị và quyền truy cập dữ liệu. Một role có thể đại diện cho người dùng, ứng dụng, nhóm quyền hoặc chủ sở hữu của một nhóm objects. Database và schema tổ chức objects; ownership xác định role có quyền quản trị object; ACL grants quyết định những role khác được phép thực hiện thao tác nào.

Nếu chỉ cấp quyền theo yêu cầu tức thời, hệ thống thường tích lũy các grants rời rạc: một user được cấp SELECT trực tiếp trên nhiều bảng, một service dùng chung tài khoản admin, schema có CREATE cho PUBLIC, hoặc objects mới không nhận default privileges như dự kiến. Sau một thời gian, không còn rõ ai sở hữu dữ liệu, quyền nào đến từ membership, quyền nào được cấp trực tiếp và phải thu hồi ở đâu khi nhân sự hoặc service rời hệ thống.

Quản lý theo vòng đời nghĩa là có quy trình nhất quán từ lúc tạo role, cấp membership, tạo database/schema, xác lập owner, cấp quyền cho objects hiện tại và tương lai, thay đổi quyền, audit định kỳ, chuyển giao ownership, vô hiệu hóa login đến khi xóa role an toàn.

Các nguyên tắc nền tảng:

- Dùng role NOLOGIN để đại diện nhóm quyền và ownership.
- Dùng login role riêng cho từng người hoặc service cần xác thực.
- Cấp quyền thông qua group roles thay vì grants trực tiếp rải rác.
- Tách quyền sở hữu objects khỏi quyền runtime của ứng dụng.
- Cấp quyền database, schema và object ở đúng cấp.
- Dùng default privileges để objects mới có ACL đúng ngay khi được tạo.
- Xác minh quyền hiệu lực, membership và ownership trước khi kết thúc change.
- Thu hồi quyền và chuyển ownership trước khi drop role.
- Lưu audit trail cho mọi thay đổi quyền có ảnh hưởng.

```text
                 ROLE LIFECYCLE
                       |
                       v
                 Provision role
                       |
                       v
             Assign group membership
                       |
                       v
             Create database/schema
                       |
                       v
             Set stable object owner
                       |
                       v
          Grant current/default privileges
                       |
                       v
             Validate effective access
                       |
                       v
          Review / rotate / change access
                       |
                       v
             Disable login and sessions
                       |
                       v
             Transfer ownership / revoke
                       |
                       v
                    Drop role
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt role, login role, group role, database, schema và object owner.
2. Giải thích ownership khác với ACL privileges như thế nào.
3. Thiết kế mô hình owner/runtime/migration roles.
4. Tạo và sửa role bằng CREATE ROLE, ALTER ROLE và DROP ROLE.
5. Quản lý LOGIN, NOLOGIN, INHERIT, CREATEDB, CREATEROLE và các thuộc tính đặc quyền.
6. Cấp và thu hồi role membership bằng GRANT/REVOKE.
7. Hiểu INHERIT, SET ROLE và ADMIN OPTION.
8. Cấp quyền database, schema, table, sequence, function và type đúng phạm vi.
9. Phân biệt PUBLIC với một group role thông thường.
10. Dùng default privileges cho objects được tạo trong tương lai.
11. Chuyển quyền sở hữu database, schema và objects.
12. Dùng REASSIGN OWNED và DROP OWNED có kiểm soát.
13. Kiểm tra quyền hiệu lực bằng has_*_privilege và catalog views.
14. Kiểm tra role memberships, object owners và ACLs.
15. Quản lý user/service onboarding, role rotation và offboarding.
16. Thu hồi login, terminate sessions và dọn dependencies.
17. Tránh cấp SUPERUSER, BYPASSRLS hoặc CREATEROLE không cần thiết.
18. Xử lý quyền trên schema public và predefined roles.
19. Thiết kế audit, review và change records.
20. Xây runbook quản trị role/database/schema theo vòng đời.

## 3. Role, user và group role

### 3.1. Role là khái niệm trung tâm

Trong PostgreSQL, role là đối tượng cluster-wide đại diện cho một danh tính hoặc tập quyền. Role có thể đăng nhập nếu có thuộc tính LOGIN, hoặc chỉ dùng để gom quyền nếu là NOLOGIN.

Lệnh CREATE USER là dạng tiện ích tương đương CREATE ROLE ... LOGIN. Tên gọi user không tạo ra một loại đối tượng bảo mật khác. Dùng role để thống nhất mô hình.

### 3.2. Login role

Login role là danh tính dùng để xác thực kết nối:

```sql
CREATE ROLE app_runtime
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;
```

Trong thực tế, credentials cần được cấp qua secret manager hoặc quy trình bảo mật. Không ghi password thật vào file migration, source control, shell history hay tài liệu baseline. Với psql, có thể dùng lệnh \password role_name để nhập password tương tác.

### 3.3. Group role

Group role thường được tạo với NOLOGIN rồi cấp cho login roles:

```sql
CREATE ROLE app_read NOLOGIN;
CREATE ROLE app_write NOLOGIN;
CREATE ROLE app_support NOLOGIN;

GRANT app_read TO app_runtime;
GRANT app_write TO app_runtime;
```

Khi cần thu hồi quyền đọc, có thể thay membership của login role mà không phải tìm và revoke từng table grant.

### 3.4. Owner role

Owner role đại diện quyền sở hữu database/schema/objects. Thông thường role này không đăng nhập trực tiếp:

```sql
CREATE ROLE app_owner NOLOGIN;
```

Migration identity có thể được phép SET ROLE sang app_owner để tạo objects dưới đúng owner. Runtime role chỉ nhận quyền cần để chạy ứng dụng.

### 3.5. Tách danh tính và quyền

Một mô hình phổ biến:

| Role | LOGIN | Vai trò |
| --- | --- | --- |
| app_owner | NOLOGIN | Sở hữu schema và objects |
| app_read | NOLOGIN | Nhóm quyền đọc |
| app_write | NOLOGIN | Nhóm quyền ghi |
| app_migrator | YES | Identity chạy migrations, có thể SET ROLE app_owner |
| app_runtime | YES | Identity của application runtime |
| app_readonly_job | YES | Service chỉ đọc/báo cáo |

Tách biệt này giúp rotate credentials mà không phải thay ACL ownership của hàng nghìn objects.

## 4. Role attributes và đặc quyền

### 4.1. Các thuộc tính phổ biến

| Attribute | Ý nghĩa |
| --- | --- |
| LOGIN / NOLOGIN | Có/không được đăng nhập |
| SUPERUSER / NOSUPERUSER | Có/không có toàn quyền superuser |
| CREATEDB / NOCREATEDB | Có/không được tạo database |
| CREATEROLE / NOCREATEROLE | Có/không được tạo và quản lý một số roles |
| REPLICATION / NOREPLICATION | Có/không được dùng quyền replication đặc biệt |
| BYPASSRLS / NOBYPASSRLS | Có/không bỏ qua row-level security |
| INHERIT / NOINHERIT | Mặc định kế thừa quyền từ memberships theo semantics của version |
| CONNECTION LIMIT | Giới hạn số kết nối đồng thời cho role, với các ngoại lệ hệ thống |
| VALID UNTIL | Thời điểm hết hạn password authentication |

### 4.2. Không cấp SUPERUSER cho application

SUPERUSER vượt qua hầu hết kiểm tra quyền và có thể thay đổi cấu hình, dữ liệu hoặc các objects nhạy cảm. Application runtime, reporting jobs và migration roles thường không cần SUPERUSER.

Nếu một thao tác quản trị đòi superuser, thực hiện bằng break-glass identity có audit và thời hạn, không gắn quyền đó vào credentials chạy thường xuyên.

### 4.3. CREATEROLE là quyền nhạy cảm

CREATEROLE cho phép tạo/quản lý roles trong phạm vi mà PostgreSQL version cho phép. Khả năng quản lý memberships và thuộc tính của role đã thay đổi giữa các major versions. Không coi CREATEROLE tương đương một quyền đọc dữ liệu thông thường; chỉ cấp cho role quản trị identity được kiểm soát.

### 4.4. CREATEDB và REPLICATION

CREATEDB cho phép tạo database. REPLICATION cho phép kết nối replication protocol theo yêu cầu. Chỉ cấp khi công việc cụ thể cần đến; một application không cần hai quyền này chỉ để truy cập bảng.

### 4.5. BYPASSRLS

BYPASSRLS cho phép bỏ qua row-level security. Đây là thuộc tính mạnh và có thể làm mất ranh giới dữ liệu theo tenant. Chỉ dùng cho một số role quản trị/backup được kiểm soát. Superuser cũng bỏ qua RLS; table owner thường bypass RLS trừ khi bật FORCE ROW LEVEL SECURITY.

### 4.6. Kiểm tra attributes

```sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls,
    rolconnlimit,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

pg_roles là view phù hợp để kiểm tra role attributes. Password hash không được hiển thị qua view này.

### 4.7. Sửa role

```sql
ALTER ROLE app_runtime CONNECTION LIMIT 40;
ALTER ROLE app_runtime VALID UNTIL '2027-01-01 00:00:00+00';
ALTER ROLE app_runtime NOLOGIN;
ALTER ROLE app_runtime LOGIN;
```

VALID UNTIL áp dụng cho password authentication; các phương thức xác thực khác có semantics riêng. NOLOGIN là cách vô hiệu hóa khả năng mở login session mới bất kể phương thức auth.

## 5. Role membership, INHERIT và SET ROLE

### 5.1. GRANT role TO role

Cú pháp membership có hướng:

```sql
GRANT app_read TO app_runtime;
```

app_runtime là member của app_read và có thể nhận các quyền của role được grant theo membership options và INHERIT behavior.

### 5.2. Thu hồi membership

```sql
REVOKE app_read FROM app_runtime;
```

Thao tác này thu hồi membership, không xóa role app_read và cũng không xóa các ACL grants đã cấp trực tiếp cho app_runtime.

### 5.3. INHERIT

INHERIT quyết định role có tự động dùng quyền của memberships hay không theo cấu hình/version. Trong các PostgreSQL versions trước 16, thuộc tính INHERIT/NOINHERIT của member role điều khiển hành vi kế thừa tổng thể. Từ PostgreSQL 16, membership grant có thể chỉ định riêng INHERIT và SET options.

Ví dụ cho các versions mới:

```sql
GRANT app_read TO app_runtime
    WITH INHERIT TRUE, SET TRUE;
```

Kiểm tra syntax chính xác theo major version đang chạy.

### 5.4. SET ROLE

SET ROLE chuyển effective role của session sang một role mà session có quyền set:

```sql
SET ROLE app_owner;

SELECT
    session_user,
    current_user;

RESET ROLE;
```

session_user phản ánh danh tính kết nối ban đầu; current_user là identity hiện hành dùng cho permission checks. Sau SET ROLE, objects được tạo thường thuộc role đang là current_user.

### 5.5. Tại sao migration cần SET ROLE?

Nếu migration login là app_migrator nhưng trực tiếp tạo table, table có thể thuộc app_migrator. Default privileges cấu hình cho app_owner sẽ không áp dụng cho objects do app_migrator tạo.

Dùng SET ROLE app_owner trước khi tạo objects để ownership và default privileges nhất quán. Kết thúc bằng RESET ROLE hoặc đóng session.

### 5.6. ADMIN OPTION

ADMIN OPTION cho phép member quản lý membership của role được grant trong phạm vi quyền mà PostgreSQL version cho phép:

```sql
GRANT app_read TO access_admin WITH ADMIN OPTION;
```

Đây là quyền quản trị membership, khác với object privilege WITH GRANT OPTION. Không cấp ADMIN OPTION cho application runtime.

### 5.7. PostgreSQL 16 trở lên: membership options

Từ PostgreSQL 16, membership có các options riêng:

- ADMIN: có thể grant/revoke membership cho role được cấp.
- INHERIT: có tự động kế thừa privileges của role được cấp không.
- SET: có được SET ROLE sang role được cấp không.

Một membership có thể được cấu hình không kế thừa quyền tự động nhưng vẫn cho phép SET ROLE. Đây là cơ sở để migration identity tạm chuyển sang owner role.

### 5.8. Kiểm tra membership

Trên PostgreSQL 16 trở lên:

```sql
SELECT
    member_role.rolname AS member_role,
    granted_role.rolname AS granted_role,
    m.admin_option,
    m.inherit_option,
    m.set_option
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member_role
  ON member_role.oid = m.member
JOIN pg_catalog.pg_roles AS granted_role
  ON granted_role.oid = m.roleid
ORDER BY member_role.rolname, granted_role.rolname;
```

Trên versions cũ hơn, pg_auth_members không có các cột inherit_option và set_option; dùng schema view phù hợp version.

### 5.9. Membership có thể lồng nhau

Role A có thể là member của role B, role B là member của C. Quyền hiệu lực phụ thuộc membership path và INHERIT/SET options. Khi audit, cần xem cả membership trực tiếp và membership lồng nhau, không chỉ một dòng GRANT gần nhất.

## 6. Database, schema và object là các lớp quyền khác nhau

### 6.1. Database

Database là đơn vị kết nối và chứa schemas. Quyền database gồm:

- CONNECT: được kết nối database.
- CREATE: được tạo schema và một số objects ở database level theo semantics.
- TEMPORARY/TEMP: được tạo temporary tables.

Có CONNECT không đồng nghĩa có thể SELECT table.

### 6.2. Schema

Schema là namespace chứa tables, views, sequences, functions, types và các objects khác.

- USAGE: cho phép truy cập/resolve objects trong schema nếu có quyền trên object.
- CREATE: cho phép tạo objects mới trong schema.

Có USAGE trên schema không tự cấp SELECT trên table. Có SELECT trên table nhưng không có USAGE schema cũng không đủ để truy cập bằng tên schema.

### 6.3. Object privileges

Quyền cụ thể trên object phụ thuộc loại object. Ví dụ table có SELECT/INSERT/UPDATE/DELETE; sequence có USAGE/SELECT/UPDATE; function có EXECUTE.

### 6.4. Ownership

Owner có quyền quản trị object, bao gồm khả năng ALTER/DROP và quản lý privileges. Ownership không giống một GRANT ALL thông thường: không thể thay thế toàn bộ quyền owner chỉ bằng cách cấp ACL.

### 6.5. Quyền PUBLIC

PUBLIC là pseudo-role đại diện mọi roles trong cluster. Grant cho PUBLIC áp dụng rộng rãi; revoke từ một user không vô hiệu hóa quyền mà user vẫn nhận qua PUBLIC hoặc membership khác.

### 6.6. Một request cần đủ nhiều lớp

Để app_runtime đọc app.orders, thường cần:

1. CONNECT trên database.
2. USAGE trên schema app.
3. SELECT trên table app.orders.
4. Membership/role attributes phù hợp.
5. Vượt qua RLS policies nếu table bật row-level security.

## 7. Database lifecycle và ownership

### 7.1. Tạo database với owner rõ ràng

CREATE DATABASE không chạy bên trong transaction block:

```sql
CREATE DATABASE appdb OWNER app_owner;
```

Chọn encoding, locale provider, collation và template theo yêu cầu ứng dụng. Các lựa chọn locale có thể ảnh hưởng sort order và index behavior; không coi việc tạo database chỉ là đặt tên.

### 7.2. Cấp quyền kết nối

```sql
GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT CONNECT ON DATABASE appdb TO app_migrator;
```

TEMP chỉ cấp nếu workload cần temporary tables:

```sql
GRANT TEMPORARY ON DATABASE appdb TO app_runtime;
```

### 7.3. Kiểm tra default database ACL

Trong nhiều databases, CONNECT và TEMPORARY được cấp cho PUBLIC theo mặc định. Hãy inspect ACL thực tế, đặc biệt database cũ hoặc database đã nâng cấp:

```sql
SELECT
    datname,
    pg_catalog.pg_get_userbyid(datdba) AS owner,
    datacl
FROM pg_catalog.pg_database
WHERE datname = 'appdb';
```

Nếu muốn giới hạn CONNECT, có thể thu hồi từ PUBLIC rồi grant lại cho các roles cần thiết:

```sql
REVOKE CONNECT ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_runtime, app_migrator;
```

Thực hiện sau khi xác định mọi services, monitoring, backup jobs và operators còn cần kết nối. Nếu bỏ sót role, ứng dụng/maintenance có thể mất kết nối.

### 7.4. Chuyển database owner

```sql
ALTER DATABASE appdb OWNER TO app_owner;
```

Người thực hiện phải đáp ứng yêu cầu ownership/membership và quyền của PostgreSQL. Kiểm tra database owner sau thay đổi.

### 7.5. Database owner không tự động là owner mọi objects

Database ownership không có nghĩa mọi tables trong database đều tự động thuộc database owner. Schema/table/function ownership là thuộc tính riêng. Kiểm kê và chuyển từng loại object nếu cần.

### 7.6. Drop database

```sql
DROP DATABASE appdb;
```

Đây là thao tác phá hủy toàn bộ database. Trước khi thực hiện lifecycle decommission, xác minh backup/retention, dependencies, active connections, subscriptions và owner approval. Không dùng ví dụ này như một bước cleanup tự động.

## 8. Schema lifecycle và quyền trên schema

### 8.1. Tạo schema với owner

```sql
CREATE SCHEMA app AUTHORIZATION app_owner;
```

Schema owner kiểm soát việc thay đổi/drop schema và quản lý quyền schema.

### 8.2. Cấp USAGE và CREATE riêng

```sql
GRANT USAGE ON SCHEMA app TO app_read, app_write;
GRANT CREATE ON SCHEMA app TO app_owner;
```

Runtime roles thường chỉ cần USAGE. Dành CREATE cho owner/migration identity.

### 8.3. Không cấp CREATE cho PUBLIC tùy tiện

Schema public có behavior mặc định khác nhau giữa các PostgreSQL versions và database history. Các database mới tạo trên PostgreSQL 15 trở lên thường có quyền CREATE trên public schema bị thu hồi khỏi PUBLIC theo mặc định, nhưng database nâng cấp/cũ có thể khác. Kiểm tra ACL thực tế:

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner,
    nspacl
FROM pg_catalog.pg_namespace
WHERE nspname IN ('public', 'app')
ORDER BY nspname;
```

Nếu policy yêu cầu, revoke CREATE từ PUBLIC và cấp lại cho owner/migration roles:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_runtime;
```

Không chạy lệnh này mù quáng trên database hiện hữu; kiểm tra extension installation, deployment scripts và users phụ thuộc public schema trước.

### 8.4. Chuyển schema owner

```sql
ALTER SCHEMA app OWNER TO app_owner;
```

Thay owner schema không tự chuyển ownership của tất cả objects bên trong schema. Tables, sequences, functions và types có thể vẫn thuộc roles khác.

### 8.5. Schema naming và boundaries

Dùng schemas để tách application domains hoặc trust boundaries. Tránh để các service không liên quan cùng CREATE vào một schema. Search path cần được kiểm soát để tránh object name shadowing.

### 8.6. Search path

Kiểm tra:

```sql
SHOW search_path;

SELECT
    rolname,
    rolconfig
FROM pg_catalog.pg_roles
WHERE rolname IN ('app_runtime', 'app_migrator');
```

Có thể cấu hình search_path theo role/database. Với SECURITY DEFINER functions, đặt search_path an toàn và schema-qualified object references để tránh object substitution attacks.

## 9. Object privileges theo loại object

### 9.1. Table và view

| Privilege | Ý nghĩa |
| --- | --- |
| SELECT | Đọc rows/columns theo phạm vi ACL và RLS |
| INSERT | Thêm rows |
| UPDATE | Cập nhật rows/columns được cấp |
| DELETE | Xóa rows |
| TRUNCATE | Xóa toàn bộ rows bằng TRUNCATE |
| REFERENCES | Tạo foreign key tham chiếu table |
| TRIGGER | Tạo trigger trên table |

Ví dụ:

```sql
GRANT SELECT ON TABLE app.orders TO app_read;
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.orders TO app_write;
```

Không cấp TRUNCATE hoặc REFERENCES nếu workload không cần.

### 9.2. Cấp quyền cho tất cả tables hiện có

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_read;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app TO app_write;
```

ALL TABLES ở đây áp dụng cho các tables/views/foreign tables phù hợp trong schema tại thời điểm chạy lệnh. Nó không tự áp dụng cho objects tạo trong tương lai.

### 9.3. Sequence

Sequence có privileges riêng:

- USAGE: cho phép nextval và currval.
- SELECT: cho phép currval.
- UPDATE: cho phép nextval và setval.

Ví dụ, runtime insert dùng sequence:

```sql
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_write;
```

Đừng cấp UPDATE nếu application không cần setval.

### 9.4. Functions và procedures

```sql
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_runtime;
```

Function và procedure có thể có security semantics quan trọng. Review SECURITY DEFINER, owner, search_path và quyền thực thi trước khi grant rộng.

### 9.5. Types

Role có thể cần USAGE trên user-defined types để dùng chúng trong khai báo/câu lệnh phù hợp:

```sql
GRANT USAGE ON TYPE app.order_status TO app_runtime;
```

### 9.6. Large objects

Large objects có ACL riêng và không nhất thiết được kiểm soát bởi table grants. Nếu ứng dụng dùng large objects, audit quyền trên các objects đó riêng.

### 9.7. Column-level privileges

PostgreSQL hỗ trợ grants theo cột cho một số table privileges:

```sql
GRANT SELECT (order_id, created_at, status)
ON app.orders TO support_read;
```

Column grants có thể giúp giới hạn việc đọc các cột nhạy cảm, nhưng cần xem các grants cấp table, PUBLIC, role memberships và RLS. Table-level SELECT vẫn cho phép đọc mọi cột.

## 10. Default privileges cho objects tương lai

### 10.1. Vì sao cần default privileges?

GRANT ... ON ALL TABLES IN SCHEMA chỉ cấp cho objects đã tồn tại. Khi migration tạo table mới, runtime roles có thể nhận permission denied nếu không có default privileges.

### 10.2. Default privileges gắn với creator role

Default privileges áp dụng cho objects do role được chỉ định tạo ra. Chúng không tự động áp dụng cho objects được tạo bởi role khác chỉ vì role đó là member của owner role.

Vì vậy, cần bảo đảm migration thực hiện SET ROLE app_owner trước khi tạo objects.

### 10.3. Cấu hình default table privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT ON TABLES TO app_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO app_write;
```

### 10.4. Default sequence privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT USAGE ON SEQUENCES TO app_write;
```

Cấp thêm SELECT nếu reporting cần currval và không muốn cho quyền nextval? Hãy chọn theo semantics sequence và workload; USAGE cho phép nextval/currval, còn SELECT chỉ cho currval.

### 10.5. Default function privileges

EXECUTE trên functions thường được cấp cho PUBLIC theo default PostgreSQL. Nếu policy cần thu hồi mặc định, thực hiện global default revoke cho creator role:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_runtime;
```

Default privilege REVOKE theo schema không thể loại bỏ một grant global đã có; global defaults và per-schema defaults được kết hợp theo quy tắc của PostgreSQL. Hiểu điều này khi thiết kế least privilege.

### 10.6. Default privileges không sửa objects hiện có

Sau khi cấu hình defaults, vẫn cần grant trên objects cũ:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_read;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_write;
```

### 10.7. Kiểm tra default ACL

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_catalog.pg_default_acl
ORDER BY creator_role, schema_name, defaclobjtype;
```

defaclnamespace có thể bằng 0 cho global defaults. Kiểm tra cả global và schema-specific records.

### 10.8. Test object mới

Tạo table test dưới owner role trong schema test/lab, rồi xác minh ACL bằng \dp hoặc catalog query. Đừng giả định default ACL đúng chỉ vì lệnh ALTER DEFAULT PRIVILEGES trả thành công.

## 11. Ownership khác với GRANT

### 11.1. Owner có quyền quản trị đặc biệt

Owner có quyền kiểm soát object, gồm ALTER/DROP và khả năng quản lý privileges. Một role khác có thể được cấp SELECT/UPDATE nhưng không tự động có quyền đổi owner hoặc drop object.

### 11.2. GRANT ALL không chuyển ownership

GRANT ALL PRIVILEGES ON TABLE ... cấp các ACL privileges phù hợp với object type. Nó không biến recipient thành owner.

### 11.3. Membership trong owner role

Membership có thể cho phép role thực hiện quyền owner theo membership semantics. Tuy nhiên, để tạo objects với owner nhất quán và áp dụng default privileges đúng creator, nên SET ROLE sang owner role trước khi DDL.

### 11.4. Owner role nên NOLOGIN

Nếu owner role không có LOGIN, credential của application không thể trực tiếp đăng nhập bằng identity đó. Migration role có quyền SET ROLE có thể thực hiện DDL có kiểm soát.

### 11.5. Object creator quyết định owner mặc định

Object thường thuộc role đang là current_user khi object được tạo. Kiểm tra current_user trong migration session:

```sql
SELECT session_user, current_user;
```

## 12. Mô hình quyền tham khảo cho một ứng dụng

Ví dụ này minh họa một database appdb, schema app, owner role và runtime roles.

### 12.1. Tạo roles

```sql
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_read NOLOGIN;
CREATE ROLE app_write NOLOGIN;

CREATE ROLE app_migrator
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE app_runtime
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT app_read, app_write TO app_runtime;
```

Cấp credentials qua secret manager hoặc secure provisioning flow. Có thể tạo role login trước khi credential được thiết lập.

### 12.2. Cấp khả năng SET ROLE cho migrator

Trên PostgreSQL 16 trở lên:

```sql
GRANT app_owner TO app_migrator
    WITH INHERIT FALSE, SET TRUE;
```

Trên versions cũ hơn, cấu hình membership/NOINHERIT theo semantics tương ứng và kiểm tra SET ROLE trong lab.

### 12.3. Tạo database và schema

Chạy CREATE DATABASE ở autocommit session:

```sql
CREATE DATABASE appdb OWNER app_owner;
```

Kết nối vào appdb rồi tạo schema:

```sql
CREATE SCHEMA app AUTHORIZATION app_owner;

GRANT CONNECT ON DATABASE appdb TO app_runtime, app_migrator;
GRANT USAGE ON SCHEMA app TO app_read, app_write;
```

### 12.4. Thiết lập default privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT ON TABLES TO app_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO app_write;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT USAGE ON SEQUENCES TO app_write;
```

### 12.5. Tạo objects dưới owner role

Kết nối bằng migrator:

```sql
SET ROLE app_owner;

CREATE TABLE app.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

RESET ROLE;
```

Sau đó kiểm tra owner và ACL. Nếu dùng identity columns, PostgreSQL quản lý sequence dependency theo semantics của identity; với serial hoặc sequences tự tạo, cần kiểm tra sequence grants riêng.

### 12.6. Kiểm tra runtime access

```sql
SET ROLE app_runtime;

SELECT count(*) FROM app.orders;

RESET ROLE;
```

Thử INSERT/UPDATE trong transaction test có rollback nếu phù hợp. Đừng xác nhận chỉ bằng một SELECT; quyền đọc và ghi là các lớp riêng.

## 13. Kiểm tra quyền hiệu lực

### 13.1. Database privileges

```sql
SELECT
    has_database_privilege('app_runtime', 'appdb', 'CONNECT') AS can_connect,
    has_database_privilege('app_runtime', 'appdb', 'CREATE') AS can_create_schema,
    has_database_privilege('app_runtime', 'appdb', 'TEMP') AS can_create_temp;
```

### 13.2. Schema privileges

```sql
SELECT
    has_schema_privilege('app_runtime', 'app', 'USAGE') AS can_use_schema,
    has_schema_privilege('app_runtime', 'app', 'CREATE') AS can_create_objects;
```

### 13.3. Table privileges

```sql
SELECT
    has_table_privilege('app_runtime', 'app.orders', 'SELECT') AS can_select,
    has_table_privilege('app_runtime', 'app.orders', 'INSERT') AS can_insert,
    has_table_privilege('app_runtime', 'app.orders', 'UPDATE') AS can_update,
    has_table_privilege('app_runtime', 'app.orders', 'DELETE') AS can_delete,
    has_table_privilege('app_runtime', 'app.orders', 'TRUNCATE') AS can_truncate;
```

### 13.4. Sequence privileges

```sql
SELECT
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'USAGE') AS can_nextval,
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'SELECT') AS can_currval,
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'UPDATE') AS can_setval;
```

Tên sequence ví dụ cần thay bằng tên thực tế. Identity sequence có dependency/visibility riêng; truy vấn catalog hoặc pg_get_serial_sequence khi cần xác định sequence.

### 13.5. Function privileges

```sql
SELECT
    has_function_privilege(
        'app_runtime',
        'app.calculate_total(bigint)',
        'EXECUTE'
    ) AS can_execute;
```

Function identity phải có argument types để phân biệt overloads.

### 13.6. ACL không phải toàn bộ policy

has_*_privilege giúp kiểm tra ACL và quyền hiệu lực theo role. Với RLS, cần kiểm tra policies, row_security, owner/BYPASSRLS và session context. Một role có SELECT vẫn có thể chỉ nhìn thấy một phần rows.

## 14. Catalogs và psql commands để audit

### 14.1. Danh sách roles

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls,
    rolinherit,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### 14.2. Database owners

```sql
SELECT
    datname,
    pg_catalog.pg_get_userbyid(datdba) AS owner,
    datallowconn,
    datconnlimit
FROM pg_catalog.pg_database
ORDER BY datname;
```

### 14.3. Schema owners

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner,
    nspacl
FROM pg_catalog.pg_namespace
WHERE nspname NOT LIKE 'pg_%'
  AND nspname <> 'information_schema'
ORDER BY nspname;
```

### 14.4. Table owners

```sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
```

### 14.5. psql shortcuts

Trong psql:

- \du+: roles và attributes.
- \l+: databases, owners và ACL.
- \dn+: schemas, owners và ACL.
- \dp: table/view/sequence privileges.
- \ddp: default privileges.
- \df+: functions và details.
- \dp app.*: ACL của objects trong schema app.

Các lệnh psql là meta-commands, không phải SQL statements; không gửi nguyên dạng \du qua JDBC như một câu SQL.

### 14.6. Information schema views

Các views như information_schema.table_privileges, role_table_grants và schema_privileges hữu ích cho kiểm tra chuẩn hóa, nhưng visibility có thể giới hạn theo quyền của người chạy. Với audit sâu, kết hợp catalogs và superuser/audit role được kiểm soát.

## 15. Role provisioning: onboarding người dùng và service

### 15.1. Xác định loại identity

Trước khi tạo role, xác định:

- Human user hay service account?
- Cần LOGIN hay chỉ group role?
- Cần quyền đọc, ghi, migration hay vận hành?
- Database/schema nào nằm trong scope?
- Có cần expiry hoặc connection limit?
- Ai là owner và người phê duyệt?
- Cách lưu và rotate credential?

### 15.2. Tạo login role tối thiểu

```sql
CREATE ROLE analyst_alex
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    CONNECTION LIMIT 5;
```

Tên role chỉ là ví dụ. Đặt naming convention theo identity source và service catalog.

### 15.3. Grant group role

```sql
GRANT app_read TO analyst_alex;
```

Nếu cần quyền đọc có giới hạn, tạo group role riêng theo data domain thay vì cấp SELECT toàn bộ database.

### 15.4. Cấp credentials ngoài source control

Dùng SCRAM-SHA-256 theo policy, secret manager và quy trình rotation. Không copy password vào ticket/chat/log. Với human identity, tích hợp authentication phù hợp môi trường như certificate, LDAP/PAM hoặc identity provider nếu đã triển khai.

### 15.5. Set expiry khi cần

```sql
ALTER ROLE analyst_alex VALID UNTIL '2026-12-31 23:59:59+00';
```

Đặt expiry cho temporary access. Nhớ rằng VALID UNTIL tác động password authentication; dùng NOLOGIN để chặn mọi login mới khi offboard.

### 15.6. Kiểm tra kết nối và quyền

Dùng chính identity mới để kết nối qua pg_hba.conf/network path thật. Thử các thao tác được phép và một số thao tác phải bị từ chối. Kiểm tra role memberships, database CONNECT, schema USAGE và object ACL.

## 16. Quản lý service account

### 16.1. Mỗi service có identity riêng

Không dùng chung một login giữa API, reporting job, ETL và migration pipeline. Identity riêng giúp audit query, rotate credentials và thu hồi quyền có phạm vi.

### 16.2. Runtime và migration tách biệt

Runtime role không nên có CREATE/ALTER/DROP trên production schema. Migration role có thể SET ROLE owner trong cửa sổ deploy và được quản lý qua CI/CD secrets.

### 16.3. Connection limit và pool

Có thể đặt CONNECTION LIMIT để giới hạn một role, nhưng đây không thay thế pool sizing, global connection capacity hoặc proxy. Superusers và một số internal connections có thể không chịu giới hạn như client roles thông thường.

### 16.4. Password rotation

Rotation an toàn thường gồm:

1. Tạo/đặt credential mới trong secret manager.
2. Cập nhật một phần clients hoặc hỗ trợ overlap bằng hai identities.
3. Xác minh clients mới kết nối và hoạt động.
4. Thu hồi credential cũ/disable role cũ.
5. Kiểm tra sessions còn tồn tại.
6. Ghi rotation timestamp và owner.

Nếu cùng một role chỉ có một password, lên kế hoạch rollout để tránh downtime khi tất cả instances đổi credential không đồng bộ.

### 16.5. Không dùng SUPERUSER làm health check

Health checks chỉ cần kết nối và query đơn giản. Dùng role riêng chỉ có CONNECT và quyền đọc một object/status phù hợp.

## 17. Thay đổi quyền và thu hồi quyền

### 17.1. Revoke trực tiếp

```sql
REVOKE UPDATE, DELETE
ON TABLE app.orders
FROM app_support;
```

Nếu role vẫn có quyền qua group membership, PUBLIC hoặc một grant khác, revoke trực tiếp chưa chắc làm thao tác bị từ chối.

### 17.2. Revoke membership

```sql
REVOKE app_write FROM app_runtime;
```

Đây thường là cách quản lý nhóm quyền rõ ràng khi runtime identity không còn cần quyền ghi.

### 17.3. REVOKE ... CASCADE

Khi grantor đã grant quyền tiếp cho roles khác bằng GRANT OPTION, thu hồi có thể cần CASCADE để thu hồi các grants phụ thuộc. CASCADE có thể tác động rộng; xem dependency và grant chains trước khi chạy.

### 17.4. Kiểm tra quyền qua PUBLIC

PUBLIC không phải role thông thường trong pg_roles. Grants cho PUBLIC có thể khiến mọi user vẫn truy cập được sau khi revoke một role cụ thể. Inspect ACL và has_*_privilege.

### 17.5. Thu hồi quyền database và schema

```sql
REVOKE CONNECT ON DATABASE appdb FROM app_runtime;
REVOKE CREATE ON SCHEMA app FROM app_migrator;
REVOKE USAGE ON SCHEMA app FROM app_read;
```

Chỉ revoke khi xác nhận role không còn dependency. Nếu application còn active, việc này có thể làm requests thất bại ngay.

### 17.6. Default privileges cần được revoke riêng

Revoke trên object hiện tại không tự xóa default privilege cho objects tương lai. Kiểm tra pg_default_acl và dùng ALTER DEFAULT PRIVILEGES ... REVOKE phù hợp.

## 18. Offboarding và xóa role an toàn

### 18.1. Xác định mọi dependencies trước

Một role có thể:

- Là owner của database/schema/table/function/sequence.
- Có privileges trực tiếp trên objects.
- Là member của roles khác.
- Được các roles khác cấp membership.
- Là owner của tablespaces hoặc shared objects.
- Được dùng trong policies, security-definer functions, jobs hoặc external configuration.
- Có sessions đang hoạt động.

### 18.2. Vô hiệu hóa login trước

```sql
ALTER ROLE analyst_alex NOLOGIN;
```

Điều này ngăn login mới. Nó không tự terminate các sessions đã mở.

### 18.3. Terminate sessions có kiểm soát

```sql
SELECT
    pid,
    datname,
    application_name,
    state,
    query_start
FROM pg_catalog.pg_stat_activity
WHERE usename = 'analyst_alex';
```

Sau khi xác định đúng sessions, có thể terminate:

```sql
SELECT pg_catalog.pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE usename = 'analyst_alex'
  AND pid <> pg_backend_pid();
```

Đây là thao tác gây gián đoạn cho transactions của role. Kiểm tra owner, database, application và tác động trước khi thực hiện. Cần quyền phù hợp để terminate backend.

### 18.4. Chuyển ownership trước khi drop

Để chuyển các objects thuộc role cũ sang owner role:

```sql
REASSIGN OWNED BY analyst_alex TO app_owner;
```

Lệnh tác động objects trong database hiện tại và một số shared objects. Kết nối vào từng database liên quan và lặp lại theo inventory; không giả định một lần chạy trong một database đã xử lý toàn cluster.

### 18.5. DROP OWNED

Sau khi ownership đã được chuyển và đã xác định grants còn lại, DROP OWNED có thể thu hồi privileges của role trên objects trong database hiện tại và shared objects. Nếu role vẫn sở hữu objects chưa được chuyển, lệnh có thể drop chúng.

```sql
DROP OWNED BY analyst_alex;
```

Đây là lệnh có thể phá hủy dữ liệu nếu role còn owner. Chỉ chạy sau khi review ownership và backup/recovery requirements. Thực hiện trong từng database cần cleanup.

### 18.6. Xóa role

```sql
DROP ROLE analyst_alex;
```

DROP ROLE chỉ thành công khi không còn dependencies. Nếu PostgreSQL báo dependency, đọc lỗi và xử lý dependency có chủ đích; không tự động dùng CASCADE như một cách dọn dẹp.

### 18.7. Thứ tự offboarding tham khảo

1. Xác nhận owner và phê duyệt offboarding.
2. Chặn login mới bằng NOLOGIN/credential revocation.
3. Dừng service/jobs sử dụng identity.
4. Terminate sessions theo kế hoạch.
5. Revoke memberships.
6. Inventory ownership và grants.
7. Reassign ownership sang stable owner role.
8. DROP OWNED để thu hồi grants còn lại khi an toàn.
9. Xác minh role không còn và application/maintenance vẫn hoạt động.
10. Lưu evidence và đóng ticket.

## 19. Chuyển giao ownership theo vòng đời

### 19.1. Khi team/service đổi owner

Ownership không nên gắn với một cá nhân đã nghỉ hoặc một deployment identity ngắn hạn. Chuyển sang stable NOLOGIN owner role để ownership không phụ thuộc vòng đời credential.

### 19.2. Chuyển database owner

```sql
ALTER DATABASE appdb OWNER TO app_owner;
```

### 19.3. Chuyển schema owner

```sql
ALTER SCHEMA app OWNER TO app_owner;
```

### 19.4. Chuyển table owner

```sql
ALTER TABLE app.orders OWNER TO app_owner;
```

### 19.5. Chuyển sequence/function owner

```sql
ALTER SEQUENCE app.orders_order_id_seq OWNER TO app_owner;
ALTER FUNCTION app.calculate_total(bigint) OWNER TO app_owner;
```

Function cần signature đầy đủ để phân biệt overload. Với procedures, types, views và các object classes khác, dùng lệnh ALTER ... OWNER tương ứng theo version.

### 19.6. REASSIGN OWNED khi chuyển nhiều objects

```sql
REASSIGN OWNED BY old_migrator TO app_owner;
```

Đây là cách hữu ích khi role cũ sở hữu nhiều objects trong database. Inventory trước và sau; kiểm tra shared objects và các database khác riêng.

### 19.7. Ownership và default privileges

Sau khi chuyển owner, review default privileges của owner mới. ALTER DEFAULT PRIVILEGES FOR ROLE old_owner không tự chuyển thành defaults của new owner. Thiết lập default ACL cho owner mới và xác minh migration chạy dưới đúng role.

## 20. RLS và ownership

### 20.1. ACL và RLS là hai lớp

GRANT SELECT cho phép role truy cập table theo ACL. Row-level security (RLS) tiếp tục lọc rows mà role được phép nhìn hoặc thay đổi.

### 20.2. Table owner thường bypass RLS

Table owner thường không bị áp RLS, trừ khi table bật FORCE ROW LEVEL SECURITY. Superuser và roles có BYPASSRLS luôn bypass RLS.

### 20.3. Runtime không nên là owner

Nếu runtime role sở hữu table, nó có thể bypass RLS mặc định và có quyền ALTER/DROP. Dùng owner NOLOGIN và runtime role chỉ nhận ACL + RLS policies cần thiết.

### 20.4. Kiểm tra RLS flags

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = 'app'
ORDER BY c.relname;
```

### 20.5. Test bằng identity runtime

Không chỉ test dưới owner hoặc superuser. Dùng chính runtime role, tenant context và application path để xác minh policy.

## 21. Predefined roles và quyền quản trị

PostgreSQL cung cấp một số predefined roles cho monitoring và maintenance, ví dụ pg_monitor, pg_read_all_settings, pg_read_all_stats, pg_read_all_data, pg_write_all_data và một số roles khác tùy version.

Các roles này thuận tiện nhưng có phạm vi rộng. Ví dụ, pg_read_all_data cho phép đọc nhiều dữ liệu trong database mà không cần cấp SELECT từng table; nó không tự cấp BYPASSRLS. Đọc tài liệu đúng version trước khi cấp.

### 21.1. Monitoring role

Một monitoring service có thể cần quyền đọc statistics và settings. Cấp predefined role phù hợp thay vì SUPERUSER.

### 21.2. Backup role

Backup tools có thể cần quyền riêng tùy physical/logical backup method. Không dùng một role có BYPASSRLS hoặc SUPERUSER nếu công cụ không yêu cầu.

### 21.3. Maintenance role

Các predefined roles maintenance có thể cho phép thao tác rộng trên nhiều objects. Kiểm tra chính xác khả năng của version và giới hạn role membership.

### 21.4. Audit predefined role memberships

```sql
SELECT
    member.rolname AS member_role,
    granted.rolname AS predefined_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS granted
  ON granted.oid = m.roleid
WHERE granted.rolname LIKE 'pg_%'
ORDER BY member.rolname, granted.rolname;
```

Review từng membership theo owner và business need. Không xóa predefined roles của PostgreSQL.

## 22. Audit và kiểm soát thay đổi quyền

### 22.1. Lưu change record

Mỗi thay đổi quyền nên ghi:

- Request/ticket ID.
- Người yêu cầu và người phê duyệt.
- Role bị thay đổi.
- Database/schema/object scope.
- Privileges hoặc membership trước/sau.
- Thời điểm và operator.
- Lý do và expiry nếu là temporary access.
- Kết quả validation.
- Rollback procedure.

### 22.2. Audit role memberships

Thu thập định kỳ role attributes và memberships. Phát hiện:

- Login roles có SUPERUSER/CREATEROLE/CREATEDB không cần thiết.
- Membership vào owner/admin roles.
- ADMIN OPTION ngoài dự kiến.
- Role cũ không còn owner.
- Roles có LOGIN nhưng không có owner.
- Temporary access quá hạn.

### 22.3. Audit ownership

Kiểm tra database, schema, table, sequence, function và types owners. Tìm objects thuộc cá nhân hoặc migration roles đã decommission.

### 22.4. Audit grants

Review grants trực tiếp, PUBLIC grants, default ACLs và membership inheritance. \dp, \ddp và catalog queries hỗ trợ kiểm tra.

### 22.5. Logging

Có thể dùng PostgreSQL logs, audit extension hoặc hệ thống change management để lưu DDL/security changes. log_statement và pgaudit có trade-offs về volume, sensitive SQL text và overhead; chọn theo policy.

### 22.6. Periodic access review

Định kỳ yêu cầu owner xác nhận:
- Identity còn hoạt động?
- Role có còn cần quyền?
- Quyền có phù hợp nhiệm vụ?
- Temporary grants đã hết hạn?
- Service account có owner và rotation date?
- Có thể giảm scope không?

## 23. Security pitfalls thường gặp

### 23.1. Cấp quyền trực tiếp cho từng user

Grants trực tiếp làm khó audit và offboarding. Dùng group roles theo capability/data domain.

### 23.2. Cấp CREATE cho runtime

CREATE trên schema cho phép tạo objects và có thể gây name shadowing hoặc objects không có owner/default ACL như mong muốn. Dành CREATE cho migration owner.

### 23.3. Dùng chung service account

Shared credentials làm mất attribution, tăng blast radius khi lộ password và gây khó rotation. Dùng identity riêng.

### 23.4. Dùng GRANT ALL mà không hiểu scope

GRANT ALL trên database chỉ áp dụng database privileges; trên schema chỉ schema privileges; trên tables là ACL object hiện có. Nó không chuyển ownership và không tự tạo default privileges.

### 23.5. Quên PUBLIC

Revoke một user nhưng quyền vẫn đến từ PUBLIC. Luôn xem ACL và has_*_privilege.

### 23.6. Default privileges cấu hình sai creator

Defaults cho app_owner không áp dụng nếu migration tạo objects dưới app_migrator. Kiểm tra current_user.

### 23.7. Chuyển schema owner nhưng quên objects

Schema ownership không tự chuyển table/function/sequence ownership. Kiểm kê object owners riêng.

### 23.8. Drop role trước khi xử lý dependencies

Role có thể sở hữu objects hoặc được grants ở nhiều databases. Dùng REASSIGN OWNED/DROP OWNED theo từng database có kiểm soát.

### 23.9. Quên active sessions

NOLOGIN không terminate sessions đang mở. Kiểm tra pg_stat_activity và xử lý session lifecycle.

### 23.10. SECURITY DEFINER không an toàn

Function SECURITY DEFINER chạy với quyền owner. Nếu search_path cho phép attacker tạo object shadowing, function có thể thực thi object không mong muốn. Đặt search_path an toàn, schema qualify references và giới hạn EXECUTE.

## 24. Runbook: onboarding một application mới

1. Xác định service owner, database và schema scope.
2. Tạo owner/group/login roles theo naming convention.
3. Đặt credentials qua secret manager.
4. Tạo database với owner NOLOGIN.
5. Tạo schema với owner role.
6. Cấp CONNECT và USAGE đúng roles.
7. Thiết lập default privileges cho tables, sequences và functions.
8. Cấp membership cho runtime/migrator.
9. Xác minh migrator có thể SET ROLE owner.
10. Tạo một object test dưới owner role.
11. Xác minh owner, ACL và default ACL.
12. Kết nối bằng runtime identity và thử read/write được phép.
13. Thử một số thao tác phải bị từ chối.
14. Kiểm tra RLS nếu dùng multi-tenant data.
15. Ghi inventory và owner của service account.

## 25. Runbook: offboarding một role

1. Xác minh role name, owner và phạm vi database.
2. Dừng ứng dụng/jobs sử dụng role.
3. ALTER ROLE ... NOLOGIN và thu hồi credential.
4. Xem pg_stat_activity; terminate sessions theo kế hoạch.
5. Kiểm tra memberships hai chiều.
6. Kiểm kê objects owned và ACL grants.
7. Reassign owned objects sang stable owner role.
8. Chạy DROP OWNED trong từng database liên quan sau khi review.
9. Xác minh default ACLs, policies và external configs không còn tham chiếu.
10. DROP ROLE.
11. Xác minh login cũ bị từ chối và service khác vẫn hoạt động.
12. Lưu evidence và đóng ticket.

## 26. Runbook: audit ownership và quyền

### Bước 1. Inventory roles

Lấy attributes, login state, validity, privileged flags và connection limits.

### Bước 2. Inventory memberships

Xem role nào là member của owner/admin roles; xem ADMIN/INHERIT/SET options theo version.

### Bước 3. Inventory database/schema owners

Đối chiếu với service/team owner hiện tại.

### Bước 4. Inventory object owners

Tìm objects thuộc login identities, ex-employees hoặc deployment roles không còn hoạt động.

### Bước 5. Inventory ACL/default ACL

Kiểm tra grants cho PUBLIC, direct grants, group grants và default privileges.

### Bước 6. Test effective access

Dùng has_*_privilege và test connection bằng identity thật. Với RLS, test theo user/tenant context.

### Bước 7. Remediate theo change process

Chuyển ownership, revoke grants hoặc thay membership theo ticket có owner. Không tự động xóa role chỉ dựa trên tuổi hoặc trạng thái NOLOGIN.

### Bước 8. Lưu baseline mới

Lưu snapshot roles, memberships, owners và ACLs sau audit để lần review sau có thể đối chiếu.

## 27. Bài tập thực hành có đáp án

Các bài tập giả định bạn có PostgreSQL lab riêng. Không revoke quyền, drop role hoặc chuyển owner production chỉ để làm bài.

### Bài 1. Role trong PostgreSQL là gì?

**Đáp án:** Đối tượng cluster-wide đại diện danh tính hoặc tập quyền, có thể LOGIN hoặc NOLOGIN.

### Bài 2. CREATE USER khác CREATE ROLE thế nào?

**Đáp án:** CREATE USER là dạng CREATE ROLE có LOGIN; không tạo loại object bảo mật khác.

### Bài 3. Group role thường có LOGIN không?

**Đáp án:** Thường là NOLOGIN và dùng để gom privileges/memberships.

### Bài 4. Vì sao cần owner role NOLOGIN?

**Đáp án:** Tách quyền sở hữu khỏi credentials dùng kết nối runtime, giảm nguy cơ owner identity bị lộ.

### Bài 5. Ownership khác GRANT thế nào?

**Đáp án:** Owner có quyền quản trị object như ALTER/DROP và quản lý privileges; GRANT chỉ cấp ACL privileges cụ thể.

### Bài 6. GRANT ALL có chuyển ownership không?

**Đáp án:** Không.

### Bài 7. LOGIN dùng để làm gì?

**Đáp án:** Cho phép role đăng nhập vào PostgreSQL nếu authentication/network policy cho phép.

### Bài 8. NOLOGIN có terminate sessions hiện tại không?

**Đáp án:** Không. Nó chặn login mới; sessions hiện tại cần được xử lý riêng.

### Bài 9. SUPERUSER có nên cấp cho application runtime?

**Đáp án:** Không. Runtime nên có quyền tối thiểu cần cho workload.

### Bài 10. CREATEROLE có nhạy cảm không?

**Đáp án:** Có. Nó cho phép quản lý roles/memberships trong phạm vi version cho phép.

### Bài 11. CREATEDB cho phép gì?

**Đáp án:** Tạo database.

### Bài 12. BYPASSRLS có tác động gì?

**Đáp án:** Bỏ qua row-level security, có thể vượt ranh giới dữ liệu theo tenant.

### Bài 13. GRANT app_read TO app_runtime có nghĩa gì?

**Đáp án:** app_runtime là member của app_read và có thể nhận privileges theo membership options.

### Bài 14. REVOKE membership có xóa group role không?

**Đáp án:** Không. Nó chỉ gỡ membership của member role.

### Bài 15. INHERIT điều khiển gì?

**Đáp án:** Việc tự động kế thừa privileges từ memberships theo semantics/version.

### Bài 16. SET ROLE làm gì?

**Đáp án:** Chuyển effective current_user sang role được phép set trong session.

### Bài 17. session_user khác current_user thế nào?

**Đáp án:** session_user là identity kết nối ban đầu; current_user là effective role hiện tại cho permission checks.

### Bài 18. ADMIN OPTION khác GRANT OPTION thế nào?

**Đáp án:** ADMIN OPTION quản lý role membership; GRANT OPTION cho phép grant tiếp object privilege.

### Bài 19. PostgreSQL 16 thêm membership options nào?

**Đáp án:** ADMIN, INHERIT và SET options riêng cho membership grants.

### Bài 20. Database CONNECT có cấp SELECT table không?

**Đáp án:** Không. Cần thêm schema USAGE và object SELECT.

### Bài 21. Schema USAGE cho phép gì?

**Đáp án:** Resolve/access objects trong schema nếu role có quyền trên object.

### Bài 22. Schema CREATE cho phép gì?

**Đáp án:** Tạo objects mới trong schema.

### Bài 23. Table SELECT có đủ nếu thiếu schema USAGE?

**Đáp án:** Không. Role còn cần quyền truy cập schema.

### Bài 24. PUBLIC là gì?

**Đáp án:** Pseudo-role đại diện mọi roles trong cluster.

### Bài 25. Vì sao phải kiểm tra PUBLIC grants?

**Đáp án:** Một user có thể vẫn có quyền qua PUBLIC dù grants trực tiếp đã bị revoke.

### Bài 26. Database owner có tự động sở hữu mọi table không?

**Đáp án:** Không. Object ownership được quản lý riêng.

### Bài 27. GRANT ALL ON DATABASE có cấp mọi quyền trên tables?

**Đáp án:** Không. Nó chỉ áp dụng các database-level privileges.

### Bài 28. Sequence USAGE cho phép gì?

**Đáp án:** nextval và currval.

### Bài 29. Sequence SELECT cho phép gì?

**Đáp án:** currval.

### Bài 30. Sequence UPDATE cho phép gì?

**Đáp án:** nextval và setval.

### Bài 31. Default privileges áp dụng khi nào?

**Đáp án:** Khi objects mới được tạo bởi creator role đã được cấu hình.

### Bài 32. ALTER DEFAULT PRIVILEGES có sửa objects hiện tại?

**Đáp án:** Không. Cần GRANT riêng trên objects hiện có.

### Bài 33. Default privileges cho app_owner có áp dụng khi app_migrator tạo table?

**Đáp án:** Không, trừ khi effective creator role được chuyển sang app_owner.

### Bài 34. Vì sao migration dùng SET ROLE app_owner?

**Đáp án:** Để objects được tạo thuộc owner role và nhận default privileges của role đó.

### Bài 35. Default function EXECUTE thường được cấp cho ai?

**Đáp án:** PUBLIC theo default PostgreSQL, trừ khi cấu hình default privileges thay đổi.

### Bài 36. Có thể per-schema REVOKE xóa global default grant không?

**Đáp án:** Không. Per-schema defaults được cộng thêm; revoke global grant phải xử lý ở global level.

### Bài 37. pg_default_acl dùng để kiểm tra gì?

**Đáp án:** Default privileges theo creator role và object type, cả global lẫn schema-specific.

### Bài 38. has_schema_privilege dùng để làm gì?

**Đáp án:** Kiểm tra role có USAGE/CREATE hoặc schema privilege được hỏi hay không.

### Bài 39. View nào liệt kê role attributes?

**Đáp án:** pg_roles.

### Bài 40. pg_auth_members lưu gì?

**Đáp án:** Quan hệ membership giữa member role và granted role cùng options liên quan.

### Bài 41. REASSIGN OWNED làm gì?

**Đáp án:** Chuyển ownership của objects thuộc role cũ sang role mới trong phạm vi database hiện tại và shared objects liên quan.

### Bài 42. REASSIGN OWNED có cần chạy ở mọi database liên quan?

**Đáp án:** Có. Chạy trong từng database cần xử lý ownership của objects ở database đó.

### Bài 43. DROP OWNED làm gì?

**Đáp án:** Drop objects vẫn thuộc role trong phạm vi hiện tại và revoke privileges mà role nhận trên objects; có thể phá hủy dữ liệu.

### Bài 44. DROP OWNED có xóa role không?

**Đáp án:** Không. Sau khi dependencies được xử lý mới DROP ROLE.

### Bài 45. Vì sao không dùng DROP ROLE CASCADE tùy tiện?

**Đáp án:** Có thể xóa/revoke dependencies rộng và gây mất objects hoặc quyền không dự kiến.

### Bài 46. NOLOGIN có thay password rotation không?

**Đáp án:** Không. NOLOGIN chặn login; rotation thay credential theo lifecycle riêng.

### Bài 47. VALID UNTIL áp dụng cho gì?

**Đáp án:** Thời hạn password authentication; không phải thay thế NOLOGIN cho mọi auth methods.

### Bài 48. Vì sao service nên có login riêng?

**Đáp án:** Attribution, rotation và offboarding có phạm vi rõ; tránh shared credential.

### Bài 49. Vì sao runtime và migration roles cần tách?

**Đáp án:** Runtime chỉ cần DML; migration cần DDL/SET ROLE owner trong quy trình deploy.

### Bài 50. Schema owner change có chuyển table owners không?

**Đáp án:** Không. Objects bên trong có ownership riêng.

### Bài 51. Table owner thường có bypass RLS không?

**Đáp án:** Có, trừ khi FORCE ROW LEVEL SECURITY; superuser/BYPASSRLS luôn bypass.

### Bài 52. GRANT SELECT có vượt RLS không?

**Đáp án:** Không. ACL và row policies là hai lớp riêng.

### Bài 53. pg_database cho biết gì về owner?

**Đáp án:** Cột datdba là OID owner; dùng pg_get_userbyid để hiển thị tên.

### Bài 54. psql command nào xem roles?

**Đáp án:** \du hoặc \du+.

### Bài 55. psql command nào xem default privileges?

**Đáp án:** \ddp.

### Bài 56. Vì sao cần terminate sessions khi offboard?

**Đáp án:** NOLOGIN không kết thúc sessions đã xác thực trước đó.

### Bài 57. Predefined role pg_read_all_data có nên cấp rộng?

**Đáp án:** Không. Nó có phạm vi đọc rộng; cấp theo need và audit.

### Bài 58. SECURITY DEFINER function có rủi ro gì?

**Đáp án:** Chạy với quyền owner; search_path/object shadowing không an toàn có thể tạo privilege escalation.

### Bài 59. Khi nào tạo baseline role/ACL mới?

**Đáp án:** Sau onboarding/offboarding hoặc access review được chấp nhận, lưu snapshot roles, memberships, owners và ACLs.

### Bài 60. Lập checklist offboarding một role

**Đáp án gợi ý:**

1. Xác định identity, owner, databases và service dependencies.
2. Dừng jobs/services và thu hồi credential.
3. ALTER ROLE NOLOGIN.
4. Kiểm tra/terminate active sessions theo change plan.
5. Kiểm tra membership hai chiều và revoke.
6. Inventory owned objects, database/schema owners và grants.
7. REASSIGN OWNED sang stable owner role trong từng database liên quan.
8. Review và chạy DROP OWNED để revoke grants còn lại khi an toàn.
9. Kiểm tra default ACLs, policies, functions và external configs.
10. DROP ROLE, xác minh không còn dependencies và lưu audit evidence.

## 28. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Role naming | Có convention cho human, service, group và owner |
| Login identities | Mỗi service/người có identity riêng |
| Group roles | Quyền được gom theo capability/domain |
| Owner roles | NOLOGIN và có owner team |
| Runtime privileges | Chỉ quyền cần thiết |
| SUPERUSER | Không cấp cho runtime |
| CREATEROLE/CREATEDB | Có justification và owner |
| REPLICATION | Chỉ cấp cho replication identity |
| BYPASSRLS | Được kiểm soát đặc biệt |
| Password/auth | Secret manager và rotation policy |
| VALID UNTIL | Temporary access có expiry |
| Membership | INHERIT/SET/ADMIN options được review |
| Database owner | Đúng stable owner role |
| CONNECT | Chỉ identities cần kết nối |
| Schema owner | Đúng owner role |
| Schema USAGE | Runtime roles được cấp đúng scope |
| Schema CREATE | Chỉ owner/migration roles |
| PUBLIC | Database/schema/function ACL được kiểm tra |
| Object grants | Table/sequence/function/type privileges tối thiểu |
| Default privileges | Cấu hình theo creator role |
| Migration session | SET ROLE owner trước DDL |
| Existing objects | Có GRANT riêng, không dựa vào defaults |
| Ownership inventory | Tables, sequences, functions và types |
| RLS | Owner/runtime/BYPASSRLS behavior được test |
| SECURITY DEFINER | Owner, search_path và EXECUTE được review |
| Audit | Change ticket, approver, before/after |
| Onboarding | Có provisioning và validation runbook |
| Offboarding | NOLOGIN, sessions, REASSIGN/DROP OWNED |
| Active sessions | Có kiểm tra trước khi drop |
| Cross-database cleanup | Xử lý từng database liên quan |
| Predefined roles | Membership có justification |
| Access review | Có lịch và owner xác nhận |
| Baseline | Roles, memberships, owners và ACLs được lưu |
| Version compatibility | Membership options/catalog columns đúng major version |

## 29. Tổng kết

Quản lý role, database, schema và ownership theo vòng đời giúp PostgreSQL duy trì quyền truy cập rõ ràng khi hệ thống, nhân sự và services thay đổi. Một mô hình bền vững tách login identities, group roles và owner roles; cấp quyền theo từng lớp; dùng default privileges cho objects tương lai; và có quy trình chuyển giao/offboarding an toàn.

Những nguyên tắc quan trọng:

1. **Role là danh tính và đơn vị gom quyền.** LOGIN role dùng kết nối; NOLOGIN role đại diện group hoặc owner.
2. **Tách runtime khỏi ownership.** Runtime không cần sở hữu objects hay có DDL privileges.
3. **Ownership khác GRANT.** GRANT ALL không chuyển quyền sở hữu object.
4. **Database, schema và object là ba lớp quyền riêng.** CONNECT, USAGE và SELECT giải quyết các bước khác nhau.
5. **Membership cần được audit.** INHERIT, SET và ADMIN OPTION ảnh hưởng quyền hiệu lực.
6. **Default privileges gắn với creator role.** Migration phải tạo objects dưới đúng owner role.
7. **Default privileges không áp dụng ngược.** Cấp quyền riêng cho objects hiện có.
8. **PUBLIC có phạm vi toàn cluster.** Kiểm tra grants qua PUBLIC khi audit.
9. **RLS bổ sung lớp kiểm soát rows.** Table ACL không thay row policies.
10. **Schema owner không tự chuyển object owners.** Inventory tables, sequences, functions và types riêng.
11. **Offboarding phải xử lý sessions và dependencies.** NOLOGIN không terminate sessions.
12. **REASSIGN OWNED và DROP OWNED có phạm vi database.** Thực hiện từng database có inventory.
13. **Không drop role trước khi chuyển ownership/revoke grants.** Giữ stable owner role cho objects.
14. **Predefined roles có thể rất rộng.** Cấp theo least privilege.
15. **Audit và baseline phải có lịch sử.** Lưu ai thay đổi gì, vì sao và quyền hiệu lực sau thay đổi.

Mô hình quyền tham khảo:

```text
              app_migrator (LOGIN)
                      |
                  SET ROLE
                      |
                      v
               app_owner (NOLOGIN)
                      |
               owns schema/objects
                      |
             +--------+---------+
             |                  |
             v                  v
         app_read            app_write
          (NOLOGIN)           (NOLOGIN)
             ^                  ^
             |                  |
             +--------+---------+
                      |
                      v
              app_runtime (LOGIN)
                 DML only
```

**Câu hỏi review cuối cùng:** “Khi một service mới được tạo, ai sở hữu database/schema và objects? Runtime identity nhận đúng những quyền nào? Migration có tạo objects dưới owner role để default privileges áp dụng không? Khi service bị decommission, chúng ta có thể vô hiệu hóa login, chuyển ownership và thu hồi grants mà không làm mất dữ liệu của team khác không?” Một quy trình role lifecycle tốt phải trả lời được các câu hỏi đó bằng role model, catalog inventory và audit trail rõ ràng.
