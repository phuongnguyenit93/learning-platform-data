# Schema owner

## Mục tiêu bài học

Trong chương Database PAM của module Privileged Access Management (PAM), **schema owner** là chủ thể sở hữu một schema theo mô hình của hệ quản trị cơ sở dữ liệu. Đây là một quyền đặc biệt vì nó có thể tác động tới cấu trúc, phân quyền và khả năng vận hành của một vùng dữ liệu.

Không nên đồng nhất “ứng dụng dùng schema này” với “ứng dụng phải sở hữu schema”. Một ứng dụng có thể chỉ cần đọc hoặc ghi một số bảng, trong khi quyền sở hữu phục vụ quản trị vòng đời và triển khai thay đổi.

Bài học dùng PostgreSQL làm ví dụ kỹ thuật. Các hệ quản trị khác có mô hình schema, user và ownership khác nhau; không sao chép ngữ nghĩa PostgreSQL sang một sản phẩm khác chỉ vì cùng có từ schema.

Sau bài học, bạn có thể:

- Phân biệt schema owner, object owner, quyền sử dụng và quyền tạo đối tượng.
- Nhận diện tác động bảo mật của quyền sở hữu.
- Tách owner role khỏi danh tính runtime và danh tính migration.
- Tích hợp quyền owner với JIT, vault, kiểm soát phiên và phê duyệt thay đổi.
- Kiểm kê ownership, membership và các quyền hiệu lực.
- Quản lý việc chuyển owner, thu hồi và lưu bằng chứng.

Các câu lệnh bên dưới dành cho môi trường thử nghiệm được kiểm soát. Chúng minh họa thiết kế quyền, không phải một migration production hoàn chỉnh và không được thực thi tự động trong bài học.

## 1. Schema owner là gì?

Trong PostgreSQL, schema tổ chức các đối tượng có tên trong một database. Schema có thể chứa bảng, view, sequence, function và các loại đối tượng khác; mỗi đối tượng có quyền sở hữu riêng. Schema cũng không phải ranh giới cô lập cứng như một database riêng. [PostgreSQL: Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html)

Ví dụ:

```text
Database: appdb
  |
  +-- Schema: billing
        Owner: billing_owner
        |
        +-- Table: invoice
        |     Owner: billing_owner
        |
        +-- Table: imported_invoice
        |     Owner: integration_owner
        |
        +-- Function: calculate_fee(...)
              Owner: fee_function_owner
```

Trong ví dụ này, billing_owner sở hữu schema billing nhưng không vì thế trở thành owner của imported_invoice hoặc calculate_fee.

Cần trả lời hai câu hỏi riêng:

1. Ai sở hữu vùng tên schema?
2. Ai sở hữu từng đối tượng nằm trong vùng tên đó?

Một báo cáo chỉ hiển thị schema owner có thể bỏ sót các role vẫn sở hữu bảng hoặc function quan trọng.

### Ownership không phải tên đăng nhập

Owner có thể là một role không được đăng nhập trực tiếp. Các principal được cho phép có thể sử dụng quyền của role đó theo cơ chế membership và kích hoạt phù hợp.

PostgreSQL hỗ trợ role NOLOGIN; role này vẫn có thể giữ quyền và sở hữu đối tượng, nhưng không được dùng làm danh tính đăng nhập ban đầu. [PostgreSQL: CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html)

Vì vậy, không nhất thiết tạo một mật khẩu “schema owner” rồi đưa mật khẩu đó cho nhiều người. Có thể giữ ownership ở role ổn định và kiểm soát chặt những danh tính được sử dụng quyền của nó.

## 2. Ownership khác quyền sử dụng như thế nào?

Cần phân biệt các lớp:

| Khái niệm | Ý nghĩa trong mô hình PostgreSQL |
|---|---|
| Owner của schema | Sở hữu chính schema |
| USAGE trên schema | Cho phép tra cứu và sử dụng đối tượng theo các quyền cần thiết khác |
| CREATE trên schema | Cho phép tạo đối tượng trong schema |
| Owner của bảng hoặc function | Sở hữu chính đối tượng đó |
| SELECT, INSERT, UPDATE và quyền tương ứng | Cho phép một loại thao tác trên đối tượng |
| Membership của role owner | Có thể mở đường sử dụng quyền của owner tùy cấu hình |

USAGE và CREATE là các quyền trên schema; chúng không thay thế quyền trên từng bảng hoặc function. Cú pháp GRANT cũng phân biệt cấp quyền đối tượng với cấp membership của role. [PostgreSQL: GRANT](https://www.postgresql.org/docs/current/sql-grant.html)

### Không suy luận quyền dữ liệu từ tên owner

Một schema owner không tự động có quyền SELECT trên mọi bảng do người khác sở hữu trong schema. Ngược lại, một runtime role có thể có SELECT trên bảng nhưng không có quyền sở hữu schema.

Đây là khác biệt quan trọng giữa quản trị cấu trúc và truy cập dữ liệu.

Tuy nhiên, không có quyền đọc mọi bảng không có nghĩa schema owner là quyền ít rủi ro. Nó vẫn có thể gây tác động nghiêm trọng tới tính toàn vẹn và khả dụng.

### Không biến owner thành một role “chỉ đọc” bằng REVOKE thông thường

Trong PostgreSQL, quyền sửa hoặc hủy đối tượng gắn với ownership. Owner cũng có khả năng cấp lại quyền thông thường của đối tượng mình sở hữu. Vì vậy, thu hồi một quyền dữ liệu khỏi chính owner không tạo ra ranh giới tương đương việc loại bỏ ownership. [PostgreSQL: Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)

Nếu yêu cầu là một principal chỉ được đọc dữ liệu, hãy cấp quyền đọc phù hợp. Không cấp owner rồi hy vọng vài REVOKE sẽ biến nó thành tài khoản chỉ đọc.

## 3. Vì sao schema owner thuộc phạm vi PAM?

### 3.1. Tác động tới khả dụng và phụ thuộc

PostgreSQL cho phép schema owner xóa schema cùng các đối tượng bên trong theo cơ chế tương ứng, kể cả khi owner không sở hữu một số đối tượng đó. CASCADE còn có thể ảnh hưởng các đối tượng phụ thuộc ngoài schema. [PostgreSQL: DROP SCHEMA](https://www.postgresql.org/docs/current/sql-dropschema.html)

Điều này cho thấy một khác biệt:

```text
Không sở hữu một bảng
    không đồng nghĩa
Không thể làm bảng đó mất khả dụng thông qua vòng đời schema
```

Vì vậy, quản lý owner phải xét cả phạm vi phụ thuộc, không chỉ danh sách bảng mà role đọc được.

### 3.2. Quyền tạo đối tượng có thể tác động đường thực thi

Nếu một schema được dùng trong search_path, quyền tạo đối tượng trong schema đó có thể ảnh hưởng cách tên không đầy đủ được phân giải. Vì thế, cần xem ai được CREATE trong các schema mà mã đặc quyền tin cậy. [PostgreSQL: Schema Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH)

Trong thiết kế PAM, quyền tạo đối tượng không nên được coi là một tiện ích phát triển vô hại. Cần đánh giá nó cùng các function, view, migration và ứng dụng sử dụng schema.

### 3.3. Owner có thể là điểm tập trung quyền

Nếu cùng một role sở hữu schema, mọi bảng và nhiều function chạy quyền cao, việc được sử dụng role đó có phạm vi ảnh hưởng lớn.

Điều đó không có nghĩa mọi hệ thống đều phải tách owner cho từng bảng. Nó có nghĩa lựa chọn mức gom nhóm ownership phải dựa trên nhiệm vụ và ranh giới tin cậy.

Một owner role chung cho mọi ứng dụng trong cùng database có thể khiến một nhiệm vụ migration nhỏ trở thành quyền tác động tới nhiều miền nghiệp vụ.

## 4. Thiết kế ba lớp danh tính

Một mô hình thường rõ ràng là tách:

```text
Owner role
  - Sở hữu schema và các đối tượng thuộc phạm vi được giao
  - Không đăng nhập trực tiếp
  - Không dùng làm danh tính runtime

Migration identity
  - Xác thực riêng
  - Chỉ được dùng quyền owner trong luồng triển khai được phép
  - Gắn với job, thay đổi và bằng chứng

Runtime identity
  - Xác thực cho ứng dụng
  - Chỉ có quyền dữ liệu cần thiết
  - Không có đường sử dụng owner
```

### Owner role

Role này là chủ thể sở hữu ổn định theo vòng đời hệ thống, thay vì một tài khoản cá nhân dễ biến mất khi nhân sự thay đổi.

Tổ chức cần xác định ai chịu trách nhiệm nghiệp vụ và ai quản trị quyền sử dụng owner. Tên role không tự là chủ sở hữu có trách nhiệm; phải có người hoặc nhóm phụ trách trong danh mục quản trị.

### Migration identity

Danh tính migration dùng để thực hiện thay đổi đã được phê duyệt. Nó không nên là credential runtime đang nằm trong mọi instance của ứng dụng.

Quyền dùng owner có thể được mở theo job hoặc cửa sổ thay đổi. Khi có khả năng giới hạn thao tác bằng một runner hoặc runbook, có thể áp dụng JEA để giảm phạm vi thực thi.

### Runtime identity

Runtime chỉ cần những thao tác phục vụ chức năng. Nếu ứng dụng chỉ đọc một view, không cấp toàn bộ DML trên mọi bảng chỉ vì cùng schema.

Một lỗi SQL injection hoặc lộ credential runtime sẽ có hậu quả nghiêm trọng hơn nếu runtime được quyền owner. Tách danh tính không loại bỏ lỗ hổng ứng dụng nhưng giúp giới hạn những gì credential đó có thể làm.

### Membership là một đường đặc quyền

NOLOGIN không làm role owner vô hại nếu nhiều principal có thể kế thừa hoặc SET ROLE sang nó.

Cần quản lý cả membership trực tiếp, membership qua role trung gian và quyền cấp lại membership. Một bản ghi owner role không có mật khẩu chưa chứng minh quyền owner đã được kiểm soát.

## 5. Ví dụ PostgreSQL trong database thử nghiệm

Ví dụ dùng các tên bắt đầu bằng lab_. Chỉ thực hiện trong database học tập bằng principal có quyền phù hợp.

Phần xác thực kết nối không được cấu hình bằng mật khẩu nhúng trong script. Khi thực hành thật, dùng cơ chế được môi trường cho phép và quản lý secret riêng.

### 5.1. Tạo các vai trò tách biệt

```sql
CREATE ROLE lab_billing_owner
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE ROLE lab_billing_runtime
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE ROLE lab_billing_migrator
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE SCHEMA lab_billing AUTHORIZATION lab_billing_owner;

REVOKE ALL ON SCHEMA lab_billing FROM PUBLIC;

GRANT USAGE ON SCHEMA lab_billing TO lab_billing_runtime;
```

Đây là một database lab sạch với role mới. Script không tự kiểm tra trùng tên, không quản lý credential và không bao phủ cấu hình kết nối, mạng hay quyền từ những role khác.

Runtime không được cấp membership của lab_billing_owner.

### 5.2. Cho phép migrator kích hoạt owner một cách tường minh

Ví dụ sau dùng membership option của PostgreSQL hỗ trợ INHERIT, SET và ADMIN. Phải đối chiếu phiên bản đang triển khai:

```sql
GRANT lab_billing_owner TO lab_billing_migrator
    WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
```

Ý định thiết kế là migrator không tự nhận quyền owner qua membership này trong hoạt động thông thường, có thể chủ động SET ROLE khi được phép và không được dùng ADMIN của membership này để cấp tiếp.

Đây vẫn là một membership tồn tại sau câu GRANT. Nó không có thời hạn JIT chỉ vì migrator dùng SET ROLE. Trong production, controller hoặc quy trình cấp quyền cần quản lý thời điểm tạo, kết thúc và xác minh membership theo thiết kế.

PostgreSQL phân biệt việc kế thừa quyền với khả năng SET ROLE; quyền sử dụng membership phụ thuộc các option và đường membership liên quan. [PostgreSQL: SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html)

### 5.3. Tạo đối tượng dưới đúng owner

Trong một kết nối lab thực sự xác thực bằng lab_billing_migrator và đã được cấp quyền cần thiết:

```sql
SELECT session_user, current_user;

SET ROLE lab_billing_owner;

SELECT session_user, current_user;

CREATE TABLE lab_billing.invoice (
    invoice_id integer PRIMARY KEY,
    tenant_code text NOT NULL,
    amount numeric(12, 2) NOT NULL
);

GRANT SELECT, INSERT, UPDATE
    ON TABLE lab_billing.invoice
    TO lab_billing_runtime;

RESET ROLE;
```

Điểm cần quan sát là danh tính phiên gốc và danh tính thực thi có thể khác nhau sau SET ROLE. Đồng thời, cần xác minh owner thực tế của bảng, không chỉ tin rằng schema đã có owner mong muốn.

Không dùng cùng một kết nối quản trị mạnh để kết luận runtime không thể SET ROLE. Principal quản trị có thể vẫn có khả năng chuyển role ngoài những quyền mà runtime thật có. Các phép kiểm tra từ chối phải dùng đúng danh tính cần kiểm chứng.

### 5.4. Thiết kế quyền cho đối tượng tương lai

Một migration tạo thêm bảng cần tạo dưới owner mong muốn và có ACL phù hợp. Có thể đặt default privileges cho role tạo đối tượng:

```sql
SET ROLE lab_billing_owner;

ALTER DEFAULT PRIVILEGES
    FOR ROLE lab_billing_owner
    IN SCHEMA lab_billing
    GRANT SELECT, INSERT, UPDATE ON TABLES TO lab_billing_runtime;

RESET ROLE;
```

Default privileges áp dụng cho đối tượng tạo trong tương lai, không sửa ACL của đối tượng đã tồn tại. Chúng gắn với role tạo đối tượng; không tự áp dụng chỉ vì schema thuộc role đó. [PostgreSQL: ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)

Ví dụ chỉ xử lý một tập quyền bảng. Sequence, function, view và các loại đối tượng khác cần được đánh giá theo nhu cầu thực tế. Không tự thêm mọi quyền chỉ để làm hết một thông báo permission denied.

## 6. Kiểm kê owner của schema và đối tượng

Một kiểm tra schema owner có thể dùng catalog:

```sql
SELECT
    n.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(n.nspowner) AS schema_owner
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname = 'lab_billing';
```

pg_namespace lưu định danh schema, owner và ACL của schema. [PostgreSQL: pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)

Tiếp theo cần kiểm tra các đối tượng quan hệ bên trong:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind,
    pg_catalog.pg_get_userbyid(c.relowner) AS object_owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'lab_billing'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY c.relkind, c.relname;
```

pg_class chứa nhiều loại relation và owner tương ứng. Câu truy vấn trên chọn một số loại để minh họa; nó không phải danh mục mọi đối tượng database. [PostgreSQL: pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)

Để kiểm kê hoàn chỉnh, cần bổ sung những loại phù hợp với hệ thống, chẳng hạn routine và type, cùng ACL, default privileges và membership.

### Phân biệt ownership với quyền hiệu lực

Có thể kiểm tra một số quyền cụ thể:

```sql
SELECT
    has_schema_privilege(
        'lab_billing_runtime', 'lab_billing', 'USAGE'
    ) AS can_use_schema,
    has_schema_privilege(
        'lab_billing_runtime', 'lab_billing', 'CREATE'
    ) AS can_create_in_schema,
    has_table_privilege(
        'lab_billing_runtime', 'lab_billing.invoice', 'SELECT'
    ) AS can_select_invoice,
    has_table_privilege(
        'lab_billing_runtime', 'lab_billing.invoice', 'TRUNCATE'
    ) AS can_truncate_invoice;
```

Các hàm hỏi quyền giúp kiểm tra hành động cụ thể, nhưng một kết quả SELECT đúng không chứng minh runtime không có đường ownership hoặc quyền khác. [PostgreSQL: System Information Functions](https://www.postgresql.org/docs/current/functions-info.html)

Danh mục PAM nên lưu cả owner mong muốn, owner quan sát, đường sử dụng owner và người chịu trách nhiệm xử lý khi phát hiện lệch cấu hình.

## 7. Quy trình PAM cho việc sử dụng schema owner

Không nên cấp quyền owner theo lý do chung “cần sửa database”. Một yêu cầu cần gắn với công việc xác định:

```text
Yêu cầu:
  người hoặc workload yêu cầu
  cluster / instance / database
  schema và owner role đích
  migration hoặc runbook được duyệt
  artifact hoặc revision cần thực thi
  thời điểm bắt đầu và deadline
  tác động dữ liệu và phụ thuộc
  người phê duyệt
  cách kết thúc quyền và xác minh
```

Một ticket không tự tạo giới hạn kỹ thuật. Nếu runner có thể thực hiện SQL tùy ý bằng owner, nó vẫn có phạm vi thực thi của owner dù ticket chỉ nói “thêm một cột”.

### Luồng đề xuất

1. Tạo kế hoạch thay đổi với đúng database và schema.
2. Kiểm tra quyền cần thiết, phụ thuộc và khả năng phục hồi.
3. Người có thẩm quyền duyệt đúng revision của kế hoạch.
4. PAM mở đường thực thi cho danh tính riêng của job hoặc người vận hành.
5. Runner xác minh instance, database, schema và role hiện hành.
6. Thực hiện artifact đã được duyệt.
7. Đối soát kết quả, ownership và ACL.
8. Chặn sử dụng mới, thu hồi quyền tạm và xử lý phiên.
9. Lưu bằng chứng và các ngoại lệ chưa hoàn tất.

Nếu thay script sau phê duyệt, phải áp dụng lại điều kiện duyệt tương ứng. Không chỉ so sánh tên file; cùng tên migration có thể chứa nội dung khác.

### JIT và JEA giải quyết hai vấn đề khác nhau

JIT giới hạn thời điểm được dùng owner. JEA giới hạn nhiệm vụ và giao diện thao tác.

Một người có thể chỉ được bấm chạy một artifact đã xác định thay vì nhận một shell SQL mở. Tuy vậy, runner, tham số và nguồn artifact phải được bảo vệ. Nếu người dùng có thể thay artifact hoặc chèn SQL qua tham số, giới hạn giao diện có thể không còn ý nghĩa.

Không đưa credential owner vào một terminal chỉ để chạy một tác vụ mà hệ thống có thể thực thi an toàn hơn qua danh tính job riêng.

## 8. Vault, credential và danh tính owner

### Không nhất thiết có secret cho owner role

Với owner NOLOGIN, secret thường thuộc danh tính đăng nhập hoặc một tích hợp xác thực, không thuộc chính role owner.

Cần quản lý tách biệt:

- Credential để mở kết nối database.
- Membership hoặc cơ chế được dùng để chuyển sang owner.
- Quyền điều khiển runner và job.
- Quyền sửa cấu hình PAM và nơi lưu secret.

Thay mật khẩu của migrator không tự thay owner của schema. Chuyển ownership cũng không tự làm credential bị lộ mất khả năng truy cập những nơi khác.

### Khi có credential dài hạn

Nếu một tích hợp cần credential dài hạn, phải xác định chủ sở hữu, nơi lưu, quyền lấy, rotation và quy trình xử lý lộ lọt. Không ghi credential vào migration repository, log triển khai hoặc ticket.

Không dùng cùng credential migration cho nhiều ứng dụng và môi trường nếu điều đó làm mất khả năng giới hạn phạm vi và quy trách nhiệm.

### Credential ngắn hạn vẫn có thể mang quyền quá rộng

Thời hạn ngắn chỉ giảm một phần cửa sổ sử dụng. Một credential còn sống ít phút nhưng có đường sang owner của mọi schema vẫn có thể tạo thay đổi lâu dài.

Thiết kế cần giới hạn database, owner role và công việc, đồng thời rà soát những đường có thể mở thêm quyền trong cửa sổ đó.

## 9. Bảo vệ function đặc quyền và search_path

Schema thường chứa mã thực thi dưới dạng function hoặc procedure. Vì vậy, inventory owner không nên chỉ liệt kê bảng.

Trong PostgreSQL, SECURITY DEFINER chạy function với quyền của function owner. Tài liệu yêu cầu thận trọng với search_path và quyền EXECUTE, đặc biệt tránh schema mà chủ thể không đáng tin có thể ghi vào. [PostgreSQL: CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY)

### Các câu hỏi thiết kế

- Ai là owner của function?
- Ai được sửa định nghĩa function?
- Ai được EXECUTE?
- Function dùng tên đầy đủ hay phụ thuộc search_path nào?
- Có dynamic SQL hoặc đầu vào ảnh hưởng tên đối tượng không?
- Có thể truy cập secret, dữ liệu hoặc hệ thống khác không?
- Việc đổi owner có làm thay đổi phạm vi thực thi không?

Không cấp runtime quyền owner của function chỉ để nó gọi function. Quyền gọi và quyền thay đổi logic là hai khả năng khác nhau.

### Khi dùng function như giao diện JEA

Một function có thể cung cấp thao tác hẹp thay vì trao owner trực tiếp. Để mô hình này có ý nghĩa, cần:

1. Giới hạn chức năng và đầu vào.
2. Xác minh phạm vi nghiệp vụ.
3. Bảo vệ định nghĩa và owner của function.
4. Quản lý quyền EXECUTE.
5. Dùng cách phân giải tên đối tượng phù hợp.
6. Không để đầu vào biến thành SQL tùy ý.
7. Ghi bằng chứng mà không lộ dữ liệu nhạy cảm.

Một function có tham số “SQL cần chạy” rồi thực thi dưới quyền owner không phải một giao diện quản trị hẹp.

### Không dựa vào cấu hình mặc định mà không kiểm tra

Một database cũ, database được restore và database mới có thể có lịch sử ACL khác nhau. Hãy kiểm tra quyền thực tế trên schema dùng chung, routine và default privileges.

Không coi việc một câu lệnh chạy thành công là bằng chứng search_path và quyền tạo đối tượng đã an toàn.

## 10. Schema owner, table owner và RLS

RLS, Row-Level Security, giới hạn truy cập theo hàng theo policy của bảng. Trong PostgreSQL, table owner thường không chịu RLS theo cách của runtime thông thường; FORCE ROW LEVEL SECURITY thay đổi một phần hành vi này, trong khi superuser và BYPASSRLS có cơ chế riêng. [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

Điểm cần phân biệt:

```text
Schema owner
    khác
Table owner
    khác
Runtime role có quyền dữ liệu và chịu policy hàng
```

Nếu cùng billing_owner sở hữu schema và các bảng, việc kích hoạt role ấy mang cả hai nhóm khả năng. Không được mô tả phiên migration như một phiên runtime chịu đầy đủ mọi giới hạn dữ liệu chỉ vì ứng dụng bình thường dùng RLS.

### RLS không thay thế việc kiểm soát owner

Một principal có khả năng quản trị bảng cần được đánh giá như chủ thể đặc quyền. Không dựa vào một policy hàng hiện tại để chứng minh nó không thể tác động dữ liệu hoặc cấu hình bảo vệ.

Ngược lại, đừng kết luận một schema owner riêng biệt tự động bỏ qua RLS của mọi bảng do người khác sở hữu. Phải kiểm tra đúng table owner, thuộc tính role, membership và quyền thực tế.

### Bài học cho hệ thống nhiều tenant

Nếu ứng dụng dùng một schema chung và RLS để tách tenant, runtime không nên vì tiện migration mà sử dụng owner của các bảng đó.

Nếu tổ chức dùng schema theo tenant, phải kiểm soát đường đi giữa các schema. Tên tenant trong schema không tự giới hạn quyền của một owner role được cấp trên nhiều vùng.

Cả hai cách đều cần ranh giới quyền được kiểm chứng, thay vì dựa vào quy ước đặt tên.

## 11. Chuyển ownership và thay đổi nhân sự

### Không để tài khoản cá nhân giữ ownership lâu dài ngoài ý định

Một developer tạo bảng dưới tài khoản của mình có thể trở thành owner thực tế của bảng. Khi người đó chuyển nhóm, việc xóa quyền truy cập trong một hệ thống khác không tự sửa ownership tại database.

Mô hình owner role ổn định giúp giảm phụ thuộc nhân sự, nhưng phải kiểm tra migration có thực sự tạo đối tượng dưới đúng role không.

### Chuyển schema owner không đồng nghĩa chuyển owner mọi đối tượng

ALTER SCHEMA có thao tác đổi owner của chính schema. Điều kiện và quyền thực thi được quy định riêng. [PostgreSQL: ALTER SCHEMA](https://www.postgresql.org/docs/current/sql-alterschema.html)

Một kế hoạch chuyển ownership cần có bản đồ riêng:

```text
Schema billing:
  owner cũ --> owner mới

Table billing.invoice:
  owner cũ --> owner được chọn

Function billing.calculate_fee(...):
  owner cũ --> owner được chọn

Default privileges:
  cấu hình tạo đối tượng tương lai được rà soát riêng

Membership:
  đường sử dụng owner cũ và mới được rà soát riêng
```

Không suy luận từ một lệnh đổi schema owner rằng toàn bộ bảng, routine, default privileges và đường membership đã được chuyển như ý định.

### Quy trình chuyển đổi đề xuất

1. Chụp inventory ownership và ACL trước thay đổi.
2. Xác định đối tượng cần chuyển và đối tượng có chủ sở hữu khác một cách hợp lệ.
3. Kiểm tra function đặc quyền, RLS và phụ thuộc ứng dụng.
4. Chuẩn bị role đích và đường quản trị cần thiết.
5. Thực hiện những thay đổi đã được duyệt.
6. Đọc lại ownership của schema và các loại đối tượng liên quan.
7. Kiểm tra runtime, migration và các trường hợp từ chối.
8. Xử lý owner cũ, membership và credential theo phạm vi đã xác định.
9. Lưu khác biệt giữa trước và sau.

Tránh một lệnh xử lý ownership diện rộng chỉ vì tên role cũ xuất hiện trong một schema. Role đó có thể sở hữu đối tượng hợp lệ ở vùng khác. Phải xác định đúng phạm vi trước.

### Restore và clone

Sau restore hoặc clone, role, mapping owner và ACL cần được đối soát với môi trường đích. Một bản sao phục vụ thử nghiệm không nên giữ nguyên đường quyền production chỉ vì công cụ phục hồi tạo được đối tượng.

Không chỉ kiểm tra “ứng dụng khởi động được”. Hãy kiểm tra ai sở hữu và ai có thể sử dụng quyền sau phục hồi.

## 12. Kết thúc quyền và xử lý phiên

Trong một luồng JIT, cần tách:

- Ngừng cho phép tạo kết nối hoặc kích hoạt mới.
- Thu hồi membership hoặc grant tạm.
- Xử lý những phiên còn sống.
- Đối soát thay đổi đã được commit.
- Điều tra những đường quyền mới được tạo trong cửa sổ owner.

Không mặc định thay đổi một bản ghi PAM hoặc một membership đã kết thúc mọi hoạt động đang chạy. Hành vi của phiên, role hiện hành và kiểm tra quyền cần được kiểm chứng trên phiên bản, cơ chế kết nối và pool đang dùng.

### Connection pool là một phần của ranh giới quyền

Nếu migration và runtime dùng chung pool hoặc chung danh tính, trạng thái phiên có thể trở thành vấn đề khó kiểm soát.

Thiết kế nên xác định:

- Pool nào được dùng cho migration.
- Có tái sử dụng kết nối cho tác vụ khác không.
- Cách đặt lại role và trạng thái phiên.
- Cách xử lý một kết nối bị lỗi giữa chừng.
- Cách xác định phiên thuộc job hoặc người nào.
- Ai có thể kết thúc phiên và tác động tới giao dịch.

Không chỉ gọi RESET ROLE rồi coi mọi trạng thái nhạy cảm đã được dọn. Cần thiết kế toàn bộ vòng đời kết nối theo khả năng driver và pool.

### Hết hạn không tự hoàn tác thay đổi

Một migration có thể đã commit trước khi quyền hết hạn. Thu hồi owner không đưa dữ liệu hay cấu trúc trở lại trạng thái trước.

Nếu một giao dịch hoặc tác vụ còn chạy ở deadline, cần chính sách dừng, chờ hoặc xử lý ngoại lệ đã xác định. Việc chấm dứt phiên có thể ảnh hưởng lock, rollback và khả dụng; không nên là một thao tác mù chỉ để đóng ticket.

Mục tiêu là kết thúc đúng khả năng sử dụng quyền, đồng thời quản lý an toàn những công việc đang tồn tại.

## 13. Bằng chứng kiểm toán cho schema owner

Một chuỗi bằng chứng cần nối được:

```text
Người hoặc workload
    --> yêu cầu thay đổi
    --> artifact được duyệt
    --> credential hoặc danh tính kết nối
    --> kích hoạt owner
    --> câu lệnh / tác vụ thực thi
    --> kết quả và ownership sau thay đổi
    --> kết thúc quyền và xác minh
```

### Thông tin nên có

| Nhóm | Nội dung điển hình |
|---|---|
| Đích | Instance, database, schema và môi trường |
| Chủ thể | Danh tính gốc, danh tính đăng nhập và role thực thi |
| Thẩm quyền | Request ID, approval reference, artifact revision |
| Phiên | Session reference và thông tin kết nối cần thiết |
| Thao tác | Loại thay đổi, đối tượng, thời điểm và kết quả |
| Trạng thái sau | Owner, ACL và các sai lệch liên quan |
| Kết thúc | Thu hồi gì, phiên nào đã xử lý, phần nào còn chờ xác minh |

Không phải mọi hệ thống audit đều cung cấp đầy đủ các trường trên. Cần thiết kế liên kết ở runner, PAM và database theo khả năng thực tế.

Tên ứng dụng hoặc comment SQL do client gửi có thể hỗ trợ tìm kiếm, nhưng không phải bằng chứng danh tính độc lập nếu client tùy ý sửa được.

### Giữ log có ích mà không tạo kho dữ liệu nhạy cảm

SQL có thể chứa literal, token hoặc dữ liệu cá nhân. Không mặc định ghi mọi tham số và kết quả vào hệ thống giám sát.

Hãy chọn mức chi tiết phù hợp, bảo vệ quyền đọc, áp dụng thời hạn lưu và liên kết bằng các định danh cần thiết. Đối với migration, artifact bất biến cùng metadata thực thi thường hữu ích hơn việc phát tán credential hoặc toàn bộ dữ liệu ra log.

### Những dấu hiệu cần đối soát

- Runtime trở thành owner của schema hoặc bảng ngoài ý định.
- Một tài khoản cá nhân xuất hiện làm owner sau migration.
- Owner role được bật LOGIN ngoài kế hoạch.
- Xuất hiện membership mới tới owner.
- Một function đặc quyền đổi owner hoặc định nghĩa.
- ACL hoặc default privileges mở rộng bất thường.
- Migration thành công nhưng đối tượng mới thuộc sai role.
- Có thao tác owner không liên kết được yêu cầu đã duyệt.

Mỗi dấu hiệu cần chủ sở hữu xử lý và quy trình xác minh. Không tự động xóa mọi quyền khác baseline khi chưa xác định ngoại lệ và ownership của thay đổi.

## 14. Tình huống thực tế: migration tạo bảng dưới sai owner

### Bối cảnh

Một ứng dụng dùng role runtime hẹp. Nhóm triển khai có migrator được phép dùng billing_owner trong một cửa sổ thay đổi.

Script tạo thêm bảng nhưng quên kích hoạt owner. Migrator lại có CREATE trên schema từ một grant cũ, nên câu CREATE TABLE vẫn chạy thành công.

### Hậu quả

Bảng có thể được tạo dưới migrator thay vì owner mong muốn. Default privileges của billing_owner không nhất thiết áp dụng cho đối tượng do role khác tạo. Ứng dụng có thể gặp lỗi quyền, còn tài khoản migration giữ ownership ngoài vòng đời công việc dự kiến.

Nếu nhóm sửa nhanh bằng cách cấp owner cho runtime, sự cố vận hành trở thành mở rộng đặc quyền.

### Cách xử lý đúng phạm vi

1. Xác định principal và role thực tế đã tạo bảng.
2. So sánh owner, ACL với kế hoạch.
3. Kiểm tra phụ thuộc và tác động trước khi chuyển owner.
4. Sửa ownership và quyền dữ liệu theo một thay đổi được phép.
5. Thu hẹp grant CREATE thừa của migrator nếu không còn cần.
6. Sửa runner để xác minh role trước khi thực thi.
7. Kiểm tra đối tượng tương lai được tạo đúng owner.

Một phép kiểm tra trước chạy có thể là:

```sql
SELECT
    current_database() AS database_name,
    session_user AS authenticated_role,
    current_user AS execution_role,
    current_user = 'lab_billing_owner' AS expected_owner_context;
```

Câu SELECT chỉ trả dữ liệu. Runner phải thực sự đọc kết quả và dừng nếu không khớp, đồng thời xác minh đúng instance và database. Không coi việc in expected_owner_context=false ra log là đã thực thi kiểm soát.

## 15. Bài thực hành kiểm chứng ranh giới owner

Dùng database riêng, dữ liệu giả và các role lab mới. Các bước dưới đây không yêu cầu xóa schema có dữ liệu thật hoặc thử câu lệnh phá hủy trên production.

### Bước 1: Xây dựng ma trận mong muốn

| Chủ thể | Dùng schema | DML cần thiết | Tạo / sửa cấu trúc | Sử dụng owner | Cấp tiếp owner |
|---|---|---|---|---|---|
| Runtime | Có | Theo chức năng | Không | Không | Không |
| Migrator khi chưa được kích hoạt | Theo thiết kế | Không mặc định | Không mặc định | Chỉ khi được mở theo quy trình | Không |
| Phiên migration đã kích hoạt | Theo kế hoạch | Theo nhu cầu thay đổi | Trong phạm vi được duyệt | Có trong cửa sổ | Không mặc định |
| Người kiểm toán | Chỉ mức cần thiết | Không mặc định | Không | Không | Không |

Ma trận là yêu cầu thiết kế. Cần ánh xạ vào ACL, membership, runner và kiểm soát nền tảng thực tế.

### Bước 2: Dùng ví dụ role và schema

Áp dụng phần SQL trong môi trường lab nếu đã có điều kiện xác thực và quyền quản trị phù hợp.

Lưu inventory trước và sau. Đặc biệt kiểm tra owner của bảng invoice và việc runtime không có membership tới owner.

Không kiểm chứng runtime bằng một phiên superuser rồi chỉ đổi tên role trong giao diện. Dùng đúng kết nối hoặc cơ chế kiểm thử phản ánh principal thật.

### Bước 3: Kiểm tra các trường hợp

| Tình huống | Kết quả mong đợi |
|---|---|
| Runtime thực hiện DML đã được cấp | Cho phép theo ACL và các policy khác |
| Runtime thử tạo bảng trong schema | Từ chối nếu không có đường quyền khác |
| Runtime thử SET ROLE sang owner | Từ chối |
| Runtime thử cấp membership owner cho người khác | Từ chối |
| Migrator chưa kích hoạt tạo bảng | Không được dựa vào một grant CREATE thừa |
| Migrator kích hoạt đúng owner rồi tạo đối tượng | Owner thực tế khớp kế hoạch |
| Tạo đối tượng dưới sai role | Kiểm soát hoặc đối soát phát hiện |
| Tạo bảng mới sau khi đặt default privileges | ACL khớp cấu hình của role tạo bảng |
| Sửa default privileges rồi xem bảng cũ | Không suy luận bảng cũ đã được sửa ACL |
| Một bảng trong schema có owner khác | Inventory thể hiện rõ, không gộp với schema owner |
| Một function có quyền thực thi đặc biệt | Owner, EXECUTE và đường sửa được rà soát riêng |
| Runtime dùng RLS | Kiểm chứng bằng runtime thật, không bằng owner |
| Kết thúc cửa sổ migration | Quyền mới và phiên còn sống được xử lý theo thiết kế |
| Pool trả kết nối sang tác vụ khác | Không để rò trạng thái owner |
| Restore sang môi trường mới | Ownership, membership và ACL được đối soát |
| Kiểm tra bằng chứng | Nối được danh tính, artifact, quyền và kết quả, không lộ credential |

Với phép thử từ chối, một kết quả thành công ngoài dự kiến cần được điều tra theo tất cả đường quyền: trực tiếp, membership, PUBLIC và thuộc tính đặc biệt. Không chỉ tìm một dòng GRANT trong script.

### Bước 4: Hoàn thiện hồ sơ

Hồ sơ nên có:

- Sơ đồ owner, migrator và runtime.
- Danh mục schema cùng owner của các loại đối tượng liên quan.
- Ma trận quyền mong muốn và quyền quan sát.
- Cách cấp JIT và kết thúc phiên.
- Một tình huống sai owner được phát hiện và xử lý.
- Các giới hạn chưa được kiểm chứng trên môi trường thực tế.

Không cần đưa password, token hoặc dữ liệu nghiệp vụ vào hồ sơ để chứng minh kiểm soát quyền.

## 16. Các lỗi thường gặp

**Cho runtime sở hữu schema để tránh lỗi permission.** Hãy xác định quyền dữ liệu đang thiếu và cấp đúng quyền cần thiết; không dùng ownership như công cụ sửa lỗi chung.

**Cho rằng schema owner sở hữu mọi bảng bên trong.** Inventory phải tách schema owner và object owner.

**Cho rằng không đọc được bảng nghĩa là owner không nguy hiểm.** Quyền quản trị schema vẫn có thể ảnh hưởng khả dụng và phụ thuộc.

**Tạo owner NOLOGIN rồi bỏ qua membership.** Mọi đường kế thừa, SET ROLE và quyền cấp tiếp vẫn cần được quản lý.

**Quên kích hoạt owner trong migration.** Runner cần xác minh role thực thi và kiểm tra ownership sau thay đổi.

**Coi default privileges là cách sửa ACL quá khứ.** Đối tượng đã tồn tại phải được rà soát riêng.

**Đổi schema owner rồi kết luận chuyển đổi hoàn tất.** Cần xử lý owner của đối tượng, routine đặc quyền, default privileges và đường sử dụng role.

**Thu hồi trong PAM nhưng không đối soát database và phiên.** Phải kiểm tra cơ chế thực thi quyền, pool và trạng thái đang tồn tại.

**Ghi mọi SQL và dữ liệu vào log.** Bằng chứng cần đủ liên kết nhưng không trở thành một bản sao dữ liệu nhạy cảm.

**Dùng owner chung cho toàn hệ thống mà không đánh giá phạm vi ảnh hưởng.** Mức gom nhóm ownership phải phù hợp ranh giới ứng dụng và trách nhiệm vận hành.

Schema owner là một thẩm quyền quản trị, không phải điều kiện mặc định để ứng dụng truy cập dữ liệu. Thiết kế PAM rõ ràng giữ ownership ở chủ thể được quản lý, chỉ mở đường sử dụng cho công việc cần thiết và xác minh cả đối tượng lẫn phiên sau thay đổi. Việc tách owner, migrator và runtime giúp quyền có mục đích cụ thể và dễ đối soát hơn trong suốt vòng đời database.
