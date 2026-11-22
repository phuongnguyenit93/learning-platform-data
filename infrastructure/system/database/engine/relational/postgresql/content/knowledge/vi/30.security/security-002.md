# Chủ sở hữu, superuser và nguyên tắc quyền tối thiểu trong PostgreSQL

Một hệ thống PostgreSQL có thể có cấu trúc bảng được thiết kế tốt, câu SQL dùng tham số và các ràng buộc dữ liệu chặt chẽ nhưng vẫn gặp sự cố nghiêm trọng nếu **ứng dụng kết nối bằng superuser**, **mọi service dùng chung tài khoản sở hữu schema** hoặc **cấp quyền rộng hơn nhu cầu thực tế**.

Hãy xét một cửa hàng có hệ thống API đọc tồn kho và một job nhập hàng. Nếu cả hai kết nối bằng tài khoản có thể `DROP TABLE`, `ALTER ROLE` hoặc bỏ qua Row-Level Security (RLS), một lỗi lập trình, SQL injection hay credential bị lộ có thể gây thiệt hại lớn hơn nhiều so với công việc thực sự mà chương trình cần làm.

PostgreSQL cho phép tách rõ:

- **Chủ sở hữu (*owner*)**: role kiểm soát vòng đời và định nghĩa của một đối tượng như table, schema, view, function.
- **Quyền trên đối tượng (*object privileges*)**: role nào được `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `USAGE`, `EXECUTE`, `CREATE` và những hành động khác.
- **Thuộc tính role (*role attributes*)**: role có thể đăng nhập, tạo database, quản trị role, có `BYPASSRLS` hay có quyền superuser không.
- **Quan hệ thành viên (*role membership*)**: một role có thể nhận hoặc sử dụng quyền từ một role khác theo các quy tắc kế thừa, `SET ROLE` và quyền quản trị.
- **Chính sách theo hàng (*RLS policies*)**: giảm tập hàng có thể đọc/sửa sau khi đã có quyền ở cấp bảng.
- **Nguyên tắc quyền tối thiểu (*least privilege*)**: mỗi ứng dụng, người dùng và tiến trình chỉ có quyền đủ để thực hiện nhiệm vụ được cho phép, trong khoảng thời gian cần thiết.

Ví dụ, một role API chỉ đọc mã SKU và số lượng tồn kho không cần được cấp toàn bộ quyền trên bảng sản phẩm:

```sql
GRANT USAGE ON SCHEMA inventory_api TO app_reader;

GRANT SELECT (sku, stock)
ON TABLE inventory_api.products
TO app_reader;
```

Về mặt ý tưởng, role này có thể đọc hai cột được cấp quyền, nhưng không tự có quyền đọc giá vốn, sửa tồn kho, tạo bảng mới hoặc thay đổi schema. Để đạt ranh giới bảo mật thật sự, cần xét thêm quyền thừa hưởng, grants khác, quyền trên schema và quyền ở các đối tượng liên quan.

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Bảo mật**, tập trung vào cách quản lý **ownership**, hiểu phạm vi quyền của **superuser**, thiết kế **least privilege** và kiểm chứng quyền trên một hệ thống có nhiều vai trò.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **owner**, **privilege**, **membership**, **role attribute** và **RLS policy**.
2. Giải thích tại sao owner có khả năng thay đổi đối tượng mà không thể biểu diễn đơn giản bằng một câu `GRANT ALL`.
3. Phân biệt `LOGIN`, `NOLOGIN`, `INHERIT`, `NOINHERIT` và `SET ROLE`.
4. Thiết kế role **sở hữu đối tượng không đăng nhập trực tiếp** và role runtime chỉ nhận quyền DML cần thiết.
5. Hiểu rủi ro của `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION` và `BYPASSRLS`.
6. Phân biệt role superuser thực sự với các tài khoản “admin” bị giới hạn của dịch vụ PostgreSQL được quản lý.
7. Dùng `GRANT`, `REVOKE`, quyền cấp cột, schema usage và membership đúng mục đích.
8. Hiểu `PUBLIC` là tập tất cả roles, không phải tên một user riêng biệt.
9. Đọc quyền mặc định khi tạo schema, table, function, sequence và database.
10. Dùng `ALTER DEFAULT PRIVILEGES` mà không hiểu nhầm nó sửa các đối tượng đã tồn tại.
11. Phân biệt quyền trên table và quyền sử dụng sequence, function, view, materialized view.
12. Giải thích vì sao table owner thường bỏ qua RLS trừ khi có `FORCE ROW LEVEL SECURITY`, trong khi superuser/role `BYPASSRLS` vẫn có đặc quyền khác.
13. Hiểu view mặc định và view `security_invoker` khác nhau về quyền truy cập đối tượng nền.
14. Viết `SECURITY DEFINER` function với nguyên tắc quyền tối thiểu và `search_path` an toàn.
15. Kiểm tra role attributes, ownership, quyền table/column/schema và grants bằng catalog/function PostgreSQL.
16. Quản lý ownership của schema, table, function khi triển khai migration.
17. Sử dụng `REASSIGN OWNED` và `DROP OWNED` có kiểm soát khi cần giải thể role.
18. Thiết kế mô hình quyền cho API đọc, service ghi, job báo cáo, migration, backup và vận hành.
19. Phân biệt read-only thực sự với “chỉ không cấp UPDATE trực tiếp” nhưng vẫn có đường ghi thông qua function/quyền được thừa hưởng.
20. Xây dựng bộ kiểm thử quyền **cả đường được phép và đường phải bị từ chối**.

**Phạm vi:** PostgreSQL hiện đại. Một số chi tiết về membership options thay đổi từ PostgreSQL 16, còn `security_invoker` cho view được hỗ trợ từ PostgreSQL 15. Cần đối chiếu phiên bản đang chạy khi triển khai. Ví dụ tạo role và cấp quyền chỉ dành cho database lab được ủy quyền; tuyệt đối không chạy các ví dụ thay đổi quyền quản trị trên môi trường sản xuất khi chưa đánh giá tác động.

---

## 2. Mô hình phân quyền: từ kết nối tới một hàng dữ liệu

Một truy vấn đi qua nhiều lớp kiểm soát:

```text
Ứng dụng hoặc người dùng
        |
        | Xác thực (pg_hba.conf, TLS, password/cert/...)
        v
Login role / session
        |
        | Role attributes và role memberships
        v
Có quyền CONNECT vào database?
        |
        v
Có quyền USAGE trên schema?
        |
        v
Có quyền SELECT/INSERT/UPDATE/... trên đối tượng?
        |
        v
Nếu table có RLS, policy nào áp dụng?
        |
        v
Quyền cột, function, view, sequence và constraint
        |
        v
Kết quả hoặc permission denied
```

Sơ đồ nhằm mô tả các lớp cần xem xét; thứ tự kiểm tra nội bộ của PostgreSQL không nhất thiết đi đúng từng bước như một pipeline tuyến tính.

### 2.1. Xác thực không đồng nghĩa phân quyền

Một role đăng nhập được không có nghĩa role đó được đọc mọi bảng. Ngược lại, một role `NOLOGIN` có thể sở hữu bảng và được dùng qua membership/`SET ROLE` mà không thể tự xác thực trực tiếp.

### 2.2. Quyền trên schema không đồng nghĩa quyền trên table

`USAGE ON SCHEMA` chủ yếu cho phép truy cập tên đối tượng trong schema theo cách được cấp phép. Nó **không tự cấp SELECT** trên mọi bảng.

### 2.3. Quyền table không tự thay quyền database/schema

Một role có `GRANT SELECT ON TABLE app.orders` nhưng thiếu các quyền liên quan để truy cập tên đối tượng vẫn có thể không thực hiện truy vấn theo cách mong muốn.

### 2.4. RLS không thay SELECT privilege

RLS lọc hàng trong các trường hợp áp dụng. Một role chưa có quyền SELECT cần thiết không thể chỉ dựa vào policy để đọc bảng.

### 2.5. Ownership là một lớp quyền lực khác

Owner có quyền kiểm soát định nghĩa và phân phối quyền đối tượng. Một consumer chỉ đọc không nên trở thành owner chỉ vì cần một câu SELECT.

---

## 3. PostgreSQL role là gì?

PostgreSQL thống nhất khái niệm user và group vào **role**.

Một role có thể:

- Được phép đăng nhập nếu có thuộc tính `LOGIN`.
- Không thể đăng nhập trực tiếp nếu `NOLOGIN`.
- Là thành viên của role khác.
- Sở hữu database/schema/table/function.
- Được cấp quyền trên đối tượng.
- Có thuộc tính quản trị như `CREATEDB`, `CREATEROLE`, `SUPERUSER`.
- Có hoặc không có khả năng dùng quyền thừa hưởng ngay theo cấu hình membership.

### 3.1. Tạo role không đăng nhập

```sql
CREATE ROLE reporting_reader NOLOGIN;
```

Role này phù hợp làm **nhóm quyền** để nhiều login roles cùng được cấp membership.

### 3.2. Tạo login role

```sql
CREATE ROLE reporting_service LOGIN;
```

Ví dụ này **chưa thiết lập phương thức xác thực an toàn**. Trong production, phải cấu hình mật khẩu/certificate/identity và quyền đăng nhập phù hợp. Không tạo login role không có mật khẩu rồi dựa vào một cấu hình `trust` rộng để bảo mật.

### 3.3. GRANT role cho role

```sql
GRANT reporting_reader TO reporting_service;
```

Theo cấu hình membership/inheritance, reporting_service có thể sử dụng quyền của reporting_reader.

### 3.4. Role là đối tượng của cluster

Role được quản lý ở phạm vi PostgreSQL cluster, không chỉ một schema. Một role có thể có quyền trên nhiều database của cùng cluster.

Vì vậy, xóa hoặc đổi thuộc tính một role có thể ảnh hưởng nhiều ứng dụng/databases. Không xem `DROP ROLE` là thay đổi chỉ liên quan database hiện tại.

### 3.5. NOLOGIN không đồng nghĩa không quyền

Một role `NOLOGIN` có thể được dùng làm owner, được cấp quyền rất rộng hoặc được chọn bằng `SET ROLE` từ một session được phép. NOLOGIN chỉ chặn đăng nhập trực tiếp, không tước đặc quyền trên đối tượng.

---

## 4. Chủ sở hữu (*owner*) khác quyền SELECT/UPDATE

Giả sử table:

```sql
CREATE TABLE app.orders (...);
```

được sở hữu bởi `app_owner`.

Một role khác được cấp:

```sql
GRANT SELECT ON app.orders TO app_reader;
```

Hai role có bản chất quyền khác nhau.

| Năng lực | Owner | Chỉ được GRANT SELECT |
| --- | --- | --- |
| Đọc dữ liệu table | Thông thường có | Có, trong phạm vi grant/RLS |
| INSERT/UPDATE/DELETE | Owner có quyền cơ bản trên đối tượng, còn chịu RLS/constraints | Không chỉ nhờ SELECT |
| ALTER TABLE | Có quyền điều khiển định nghĩa theo các quy tắc sở hữu | Không |
| DROP TABLE | Owner có quyền kiểm soát đối tượng, theo yêu cầu DDL | Không |
| GRANT quyền object cho role khác | Owner có quyền grant | Không, trừ khi có GRANT OPTION hoặc cơ chế phù hợp |
| Đổi owner | Có thể trong điều kiện cho phép | Không |
| Bypass RLS | Table owner thường bypass, trừ FORCE RLS | Không mặc định |
| Quản trị cả cluster | Không chỉ vì sở hữu table | Không |

### 4.1. GRANT ALL không biến một role thành owner

```sql
GRANT ALL PRIVILEGES ON TABLE app.orders TO app_writer;
```

cấp tất cả **grantable table privileges** phù hợp. Nó không chuyển ownership, không tự cho phép ALTER/DROP đối tượng và không biến role thành superuser.

### 4.2. Quyền của owner không chỉ là các ACL được cấp

PostgreSQL xem khả năng sửa/loại bỏ đối tượng là quyền vốn gắn với sở hữu. Không thể “REVOKE quyền DROP TABLE của owner” bằng một GRANT/REVOKE thông thường rồi vẫn để role đó làm owner.

### 4.3. Quyền DML của owner vẫn có thể tương tác với RLS

Đừng hiểu “owner có quyền với table” là có thể bỏ qua tất cả tính năng database. Với `FORCE ROW LEVEL SECURITY`, owner table có thể phải chịu policy RLS; superuser và role BYPASSRLS vẫn là các trường hợp đặc biệt.

### 4.4. Owner không phải người tạo tài khoản PostgreSQL

Một role có thể tạo table, rồi chuyển owner cho role khác nếu được phép. Cần phân biệt *creator*, *owner hiện tại* và *người triển khai migration*.

---

## 5. Vì sao không để tài khoản ứng dụng sở hữu bảng?

Nếu một API service kết nối bằng `app_owner`, một truy vấn bị khai thác có thể tận dụng quyền của owner:

- ALTER hoặc DROP các đối tượng trong phạm vi sở hữu.
- Thay đổi cấp quyền của đối tượng.
- Bỏ hoặc sửa một số cơ chế kiểm soát do owner quản lý.
- Chạm đến dữ liệu không nên công bố nếu owner có quyền rộng.
- Vô tình thay đổi schema khi triển khai lỗi.

### 5.1. Mô hình tốt hơn

```text
migration/admin deployment
         |
         | SET ROLE app_owner khi cần DDL
         v
app_owner (NOLOGIN)
         |
         +-- sở hữu schema/table/function
         |
         +-- GRANT SELECT     --> app_read (NOLOGIN)
         +-- GRANT DML hẹp    --> app_write (NOLOGIN)
                                |
                                +--> login của service được cấp membership
```

### 5.2. Tách account deploy và account runtime

- **Deployment/migration role** được cấp năng lực thay đổi schema theo quy trình.
- **Runtime role** chỉ có SELECT/INSERT/UPDATE/DELETE cần thiết.
- **Reporting role** chỉ đọc những đối tượng báo cáo được công bố.
- **Operator role** có năng lực quan sát hoặc bảo trì được cấp có chủ đích.
- **Superuser/break-glass** dùng rất hạn chế, không nằm trong connection pool của ứng dụng.

### 5.3. Mọi role đều cần quản lý credential

NOLOGIN owner không có credential đăng nhập trực tiếp. Login role của ứng dụng vẫn phải được quản lý secret, rotation, TLS và connection-level access. Không phải cứ tách role là toàn hệ thống tự an toàn.

---

## 6. Superuser: đặc quyền cấp cluster

PostgreSQL có thuộc tính `SUPERUSER`, cấp quyền rất lớn, bao gồm khả năng vượt qua những kiểm tra quyền thông thường trên database objects.

Trong nhiều cluster tự quản lý, tài khoản quản trị ban đầu thường tên `postgres`, nhưng **không bắt buộc**. Trên cloud managed PostgreSQL, tên account “admin” hoặc “postgres” có thể **không có SUPERUSER thật**, vì nhà cung cấp hạn chế quyền hệ thống.

### 6.1. Superuser làm được gì?

Một superuser thực sự có thể thực hiện nhiều thao tác vượt phạm vi owner/table privilege thông thường:

- Truy cập hoặc thay đổi hầu hết đối tượng trong cluster.
- Quản lý role attributes và đặc quyền rất cao.
- Thực hiện nhiều thao tác maintenance, configuration và mở rộng.
- Bỏ qua RLS theo quy tắc PostgreSQL.
- Truy cập các năng lực quản trị nhạy cảm khác mà non-superuser bị hạn chế.

Quyền chính xác còn phụ thuộc cluster, phiên bản, extension và các kiểm soát bên ngoài như hệ điều hành/managed service.

### 6.2. Vì sao dùng superuser cho ứng dụng là rủi ro lớn?

Nếu credentials bị lộ hoặc code có lỗ hổng SQL injection, đối tượng tấn công không còn bị giới hạn bởi grants đọc/ghi của một schema.

### 6.3. Superuser không phải lựa chọn “cho hết lỗi permission denied”

Việc một câu SELECT bị từ chối là dấu hiệu cần tìm thiếu quyền nào, không phải lý do thêm SUPERUSER.

### 6.4. Không có nhu cầu superuser cho phần lớn CRUD

Những thao tác thường ngày như:

```sql
SELECT ...
INSERT ...
UPDATE ...
DELETE ...
```

có thể được cấp chính xác theo database/schema/table/column mà không cần SUPERUSER.

### 6.5. Nguyên tắc vận hành

Giữ đặc quyền quản trị cao cho tài khoản riêng, có audit, bảo vệ credential, truy cập qua quy trình phê duyệt khi cần, và tránh dùng làm login mặc định của service.

---

## 7. Các thuộc tính role có quyền lực cao

Các thuộc tính role đáng chú ý:

| Thuộc tính | Ý nghĩa | Rủi ro nếu cấp rộng |
| --- | --- | --- |
| `SUPERUSER` | Quyền rất cao cấp cluster | Hầu như không còn boundary của object ACL/RLS |
| `CREATEROLE` | Quản trị role/membership trong giới hạn phiên bản | Có thể mở rộng quyền qua role management |
| `CREATEDB` | Tạo database | Tạo tài nguyên mới, có ownership database |
| `REPLICATION` | Khả năng kết nối/thực hiện các thao tác replication tương ứng | Tiếp cận dữ liệu replication/WAL và hệ thống |
| `BYPASSRLS` | Bỏ qua Row-Level Security | Truy cập hàng ngoài policy |
| `LOGIN` | Đăng nhập trực tiếp | Credential cần bảo vệ |
| `INHERIT` | Cấu hình mặc định cho kế thừa quyền thành viên | Có thể nhận rộng quyền hơn dự đoán |
| `CONNECTION LIMIT` | Giới hạn số kết nối theo quy tắc role | Không phải policy quyền dữ liệu |

### 7.1. CREATEROLE không đơn giản là SUPERUSER

CREATEROLE cho phép những thao tác quản trị role trong giới hạn cho phép. Những giới hạn đó thay đổi theo phiên bản; đặc biệt PostgreSQL 16 đã điều chỉnh quyền quản trị membership.

Không đồng nhất CREATEROLE với khả năng tạo hoặc tự cấp mọi đặc quyền của superuser.

### 7.2. BYPASSRLS là quyền rất nhạy cảm

Một role BYPASSRLS có thể vượt qua chính sách bảo vệ hàng. Nếu ứng dụng đa tenant dựa vào RLS, việc cho runtime BYPASSRLS có thể vô hiệu hóa tuyến phòng thủ quan trọng.

### 7.3. CREATEDB không tự cho phép đọc mọi table

Sở hữu database và được tạo database không có nghĩa role mặc nhiên là owner của mọi bảng do người khác tạo trong những database khác.

### 7.4. REPLICATION không nên nằm trong runtime API

Replication và backup là các vai trò chuyên biệt, có khả năng truy cập lượng lớn dữ liệu. Không gắn REPLICATION cho role chỉ làm CRUD.

### 7.5. Thuộc tính role khác GRANT trên table

Một role không có SUPERUSER vẫn có thể đọc bảng khi được GRANT SELECT. Ngược lại, một role có CREATEDB chưa chắc đọc được bảng riêng của application.

---

## 8. LOGIN, NOLOGIN, INHERIT và NOINHERIT

### 8.1. LOGIN/NOLOGIN

```sql
CREATE ROLE security_owner NOLOGIN;
CREATE ROLE security_runtime LOGIN;
```

Owner role thường được thiết kế NOLOGIN, còn runtime login có phương thức xác thực phù hợp.

### 8.2. INHERIT

Với quyền kế thừa phù hợp, role thành viên có thể sử dụng một số quyền của role được cấp mà không cần `SET ROLE` trước.

```sql
GRANT reporting_reader TO security_runtime;
```

### 8.3. NOINHERIT

Role được khai báo NOINHERIT không mặc nhiên sử dụng mọi quyền của các membership theo cách một role INHERIT có thể làm. Tuy nhiên, việc có thể `SET ROLE` hay không còn phụ thuộc quyền membership và phiên bản.

### 8.4. Từ PostgreSQL 16: membership options chi tiết hơn

Các quan hệ membership có các lựa chọn liên quan **INHERIT**, **SET** và **ADMIN**. Vì vậy không chỉ nhìn một thuộc tính `rolinherit` rồi kết luận chính xác mọi đường kế thừa hoặc chuyển role.

Một ví dụ có thể an toàn trong PostgreSQL 15 nhưng cần xem lại cách GRANT role sau khi nâng cấp hoặc thay đổi membership trên PostgreSQL 16+.

### 8.5. INHERIT không có nghĩa role có thể thay owner

Thừa hưởng SELECT trên một table không đồng nghĩa có quyền thực hiện mọi hành động mà owner được phép. Các thao tác owner/DDL và `SET ROLE` có quy tắc riêng.

### 8.6. Đừng dựa vào câu “đã GRANT role” mà bỏ kiểm tra

Trong môi trường thật, kiểm tra từ login runtime:

```sql
SELECT session_user, current_user;
SELECT has_table_privilege(
    current_user,
    'app.orders',
    'SELECT'
);
```

và thử hành động được phép/lẽ ra bị từ chối, với thông tin role membership đang có.

---

## 9. SET ROLE, session_user và current_user

Một kết nối có thể xác thực bằng role A nhưng hoạt động trong ngữ cảnh role B nếu được phép.

```sql
SELECT
    session_user,
    current_user;
```

- `session_user` thường là role của phiên xác thực ban đầu.
- `current_user` là role dùng để kiểm tra nhiều quyền trong ngữ cảnh hiện tại; nó có thể thay đổi sau `SET ROLE` hoặc trong các ngữ cảnh quyền như SECURITY DEFINER.

### 9.1. Đổi role trong session

```sql
SET ROLE security_owner;

-- Thực hiện DDL được ủy quyền.

RESET ROLE;
```

Câu này chỉ hợp lệ khi session có quyền chuyển sang role đó, hoặc có đặc quyền quản trị cho phép.

### 9.2. SET ROLE không tạo session mới

Session vẫn là session hiện tại; nó thay đổi ngữ cảnh quyền theo quy tắc PostgreSQL. Các GUCs, transactions và pooling vẫn cần được quản lý.

### 9.3. Đừng quên RESET ROLE trong migration/test

Nếu connection được tái sử dụng sau khi `SET ROLE`, việc không khôi phục role có thể khiến bước kế tiếp chạy với quyền không mong muốn. Trong production, tốt hơn sử dụng migration connection riêng và quản lý lifecycle rõ ràng.

### 9.4. SECURITY DEFINER và current_user

Trong function SECURITY DEFINER, PostgreSQL thực thi body theo quyền owner của function; `current_user` có thể phản ánh role hiệu lực trong function. Điều này có nghĩa logic phân quyền không được tùy tiện coi `current_user` là danh tính caller đã xác thực trong mọi trường hợp.

### 9.5. Role membership là một đường leo thang nếu cấp sai

Nếu một runtime role được phép `SET ROLE` sang owner role, runtime có thể truy cập quyền owner ở thời điểm đó. Không chỉ nhìn grants trực tiếp mà quên membership với owner.

---

## 10. PUBLIC không phải một login role bình thường

Trong ngữ cảnh GRANT/REVOKE, `PUBLIC` biểu diễn **tất cả roles hiện tại và tương lai**.

Ví dụ:

```sql
GRANT SELECT ON TABLE app.public_catalog TO PUBLIC;
```

có nghĩa mọi role có các quyền liên quan khác để truy cập đối tượng có thể hưởng SELECT đó.

### 10.1. Không cần GRANT membership vào PUBLIC

Mọi role tự thuộc tập PUBLIC theo mô hình privilege của PostgreSQL.

### 10.2. REVOKE FROM PUBLIC

```sql
REVOKE EXECUTE ON FUNCTION
    app.sensitive_operation(INTEGER)
FROM PUBLIC;
```

là ví dụ thu hồi một quyền mặc định hoặc quyền đã từng cấp rộng.

### 10.3. Thu hồi PUBLIC không loại bỏ grants khác

Nếu một role được GRANT trực tiếp hoặc qua một group role, chỉ `REVOKE ... FROM PUBLIC` **không** tước những đường quyền kia.

### 10.4. Đừng hiểu PUBLIC schema và PUBLIC pseudo-role là một

- `public` (schema): đối tượng schema thường có tên `public`.
- `PUBLIC` trong GRANT/REVOKE: tập tất cả roles.

Hai khái niệm khác nhau dù nhìn gần giống nhau.

### 10.5. Kiểm tra quyền mặc định theo phiên bản

Một database PostgreSQL mới có thể có quyền CONNECT/TEMP trên database và USAGE schema public theo mặc định, nhưng khả năng CREATE trong public schema đã thay đổi ở những phiên bản gần đây. Đừng dựa vào một quy tắc thuộc lòng cho mọi cluster đã upgrade hoặc restore.

---

## 11. Lab phân quyền: mô hình role và bảng tồn kho

Ta xây dựng mô hình:

- `sec379_owner`: owner không đăng nhập.
- `sec379_read`: nhóm quyền đọc.
- `sec379_write`: nhóm quyền cập nhật tồn kho.
- `sec379_app_reader`: role mô phỏng một consumer đọc.
- `sec379_app_writer`: role mô phỏng một worker ghi.
- `sec379_lab`: schema demo.

Các role app trong lab cũng là `NOLOGIN` để không tạo tài khoản đăng nhập có credential. Khi kiểm tra, administrator được phép sử dụng `SET ROLE` để mô phỏng ngữ cảnh.

**Cảnh báo vận hành:** Những câu sau cần quyền quản trị role/schema tương ứng và **chỉ nên chạy trên cluster/database thực hành**, nơi tên role và schema được dành riêng cho lab. Không chạy trên môi trường đang phục vụ production, không thêm SUPERUSER cho các role này.

### 11.1. Tạo roles

```sql
CREATE ROLE sec379_owner NOLOGIN;
CREATE ROLE sec379_read NOLOGIN;
CREATE ROLE sec379_write NOLOGIN;
CREATE ROLE sec379_app_reader NOLOGIN INHERIT;
CREATE ROLE sec379_app_writer NOLOGIN INHERIT;

GRANT sec379_read TO sec379_app_reader;
GRANT sec379_write TO sec379_app_writer;
```

Trong môi trường thực, hành vi thừa hưởng quyền phụ thuộc membership options; lab giả định các grants được thiết lập để thành viên có quyền tương ứng.

### 11.2. Tạo schema do owner role sở hữu

```sql
CREATE SCHEMA sec379_lab AUTHORIZATION sec379_owner;
```

Chỉ tạo schema ở database có quyền CREATE phù hợp và không trùng tên hiện có.

### 11.3. Tạo table với owner không đăng nhập

Ở session quản trị được phép chuyển role:

```sql
SET ROLE sec379_owner;

CREATE TABLE sec379_lab.inventory (
    sku TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL
        CONSTRAINT inventory_stock_nonnegative CHECK (stock >= 0),
    unit_cost NUMERIC(12,2) NOT NULL
        CONSTRAINT inventory_cost_nonnegative CHECK (unit_cost >= 0),
    internal_note TEXT
);

INSERT INTO sec379_lab.inventory (
    sku, display_name, stock, unit_cost, internal_note
)
VALUES
    ('SKU-100', 'Bàn phím', 8, 280000.00, 'Cost is confidential'),
    ('SKU-200', 'Chuột', 25, 90000.00, 'Supplier terms private'),
    ('SKU-300', 'Màn hình', 4, 1750000.00, NULL);

RESET ROLE;
```

### 11.4. Kết quả ownership

Table và schema được sở hữu bởi `sec379_owner` trong ví dụ; role này không cần login password cho runtime.

### 11.5. Vì sao có cột nhạy cảm?

`unit_cost` và `internal_note` minh họa trường mà API chỉ hiển thị tồn kho **không nên đọc**. Điều này giúp kiểm tra column-level privilege rõ ràng.

### 11.6. Tách DDL khỏi runtime

Ứng dụng chạy hằng ngày không cần nhận ownership chỉ để SELECT sku và stock. Phần tiếp theo cấp quyền hẹp cho các role consumer.

---

## 12. GRANT USAGE trên schema

Role muốn truy vấn một đối tượng có tên trong schema thường cần quyền `USAGE` trên schema ngoài quyền trên đối tượng.

Trong lab:

```sql
GRANT USAGE ON SCHEMA sec379_lab
TO sec379_read, sec379_write;
```

### 12.1. USAGE không cho tạo bảng

```sql
GRANT USAGE ON SCHEMA sec379_lab TO sec379_read;
```

không cấp `CREATE` trong schema.

### 12.2. CREATE trên schema là quyền nhạy cảm

```sql
GRANT CREATE ON SCHEMA sec379_lab TO some_role;
```

cho phép role tạo đối tượng được hỗ trợ trong schema; nếu schema tham gia search_path của một function SECURITY DEFINER, việc cho untrusted roles tạo object có thể mở đường name shadowing/hijacking.

### 12.3. Một role được SELECT table nhưng thiếu USAGE schema

Dù có table-level grant, role có thể không truy cập tên bảng như mong muốn khi thiếu schema usage. Khi gặp permission denied, kiểm tra đầy đủ layers, đừng thêm SUPERUSER.

### 12.4. Cẩn trọng với schema public

Tạo các bảng nội bộ trong schema riêng giúp quản lý owner và grants theo khu vực rõ hơn so với dồn mọi object vào `public` mà nhiều ứng dụng cùng sử dụng.

### 12.5. Schema ownership không cho owner đọc mọi bảng của role khác

Sở hữu schema cho quyền điều khiển schema theo quy tắc PostgreSQL, nhưng không mặc nhiên biến người sở hữu schema thành owner hoặc người có SELECT trên từng bảng do role khác sở hữu.

---

## 13. Column-level GRANT cho API đọc tồn kho

Thay vì:

```sql
GRANT SELECT ON sec379_lab.inventory TO sec379_read;
```

ta chỉ cấp đúng hai cột:

```sql
GRANT SELECT (sku, stock)
ON TABLE sec379_lab.inventory
TO sec379_read;
```

### 13.1. Truy vấn được phép

Nếu `sec379_app_reader` kế thừa quyền `sec379_read` đúng cách:

```sql
SET ROLE sec379_app_reader;

SELECT sku, stock
FROM sec379_lab.inventory
ORDER BY sku;

RESET ROLE;
```

### 13.2. Truy vấn phải bị từ chối

Chạy riêng từng thử nghiệm thất bại (không gộp vào transaction có nhiều việc cần hoàn thành):

```sql
SET ROLE sec379_app_reader;

-- Dự kiến bị từ chối vì chưa cấp SELECT trên unit_cost.
SELECT sku, unit_cost FROM sec379_lab.inventory;

RESET ROLE;
```

Nếu câu bị lỗi khiến transaction đang mở vào trạng thái aborted, hãy ROLLBACK trước các câu khác. Trong script automation, dùng phiên thử riêng hoặc transaction/savepoint theo quy tắc PostgreSQL.

### 13.3. SELECT * có thể thất bại

```sql
SELECT * FROM sec379_lab.inventory;
```

yêu cầu quyền đối với các cột được truy vấn. Chỉ cấp `SELECT(sku,stock)` không đủ để đọc `unit_cost` và `internal_note`.

### 13.4. Vì sao đây là least privilege?

API chỉ cần hiển thị SKU và số lượng. Nếu tài khoản bị lộ, phạm vi dữ liệu accessible nhỏ hơn so với SELECT toàn bảng.

### 13.5. Cẩn thận với quyền rộng đã cấp từ đường khác

Nếu `sec379_app_reader` còn thừa hưởng một role có `SELECT ON TABLE inventory`, column-level restriction trên không “phủ định” quyền rộng đó. Quyền PostgreSQL nói chung được cộng từ các đường grant hợp lệ; không có cơ chế DENY toàn diện đơn giản cho một cột đã được cấp thông qua đường khác.

---

## 14. GRANT UPDATE cho worker chỉ sửa stock

Worker tồn kho cần đọc SKU/stock để đưa điều kiện và cập nhật stock, nhưng không cần sửa unit_cost hoặc đọc internal_note.

```sql
GRANT SELECT (sku, stock),
      UPDATE (stock)
ON TABLE sec379_lab.inventory
TO sec379_write;
```

### 14.1. UPDATE được phép

```sql
BEGIN;

SET LOCAL ROLE sec379_app_writer;

UPDATE sec379_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-100'
  AND stock >= 1
RETURNING sku, stock;

ROLLBACK;
```

Ví dụ trên là một mẫu **atomic conditional UPDATE** đơn giản. Worker cần quyền SELECT thích hợp để đọc stock trong biểu thức/WHERE/RETURNING và UPDATE trên cột stock.

**Chú ý:** `SET LOCAL ROLE` không phải cú pháp PostgreSQL chung để đổi role theo transaction. Trong lab thực tế, dùng `SET ROLE sec379_app_writer` rồi `RESET ROLE` ở một session phù hợp, hoặc chỉ dùng `SET ROLE` trong transaction đã kiểm soát. Ví dụ thực thi đúng:

```sql
BEGIN;
SET ROLE sec379_app_writer;

UPDATE sec379_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-100'
  AND stock >= 1
RETURNING sku, stock;

ROLLBACK;
-- Sau khi rollback, xác minh role hiệu lực đã trở về ngữ cảnh trước thử nghiệm.
```

### 14.2. UPDATE không được phép

```sql
SET ROLE sec379_app_writer;

-- Dự kiến permission denied vì không được UPDATE unit_cost.
UPDATE sec379_lab.inventory
SET unit_cost = 1
WHERE sku = 'SKU-100';

RESET ROLE;
```

### 14.3. DELETE/TRUNCATE/ALTER vẫn không được cấp

`UPDATE(stock)` không cho worker xóa toàn bảng, truncate hoặc thay đổi cấu trúc.

### 14.4. Không cấp ALL để sửa một cột

```sql
GRANT ALL ON TABLE sec379_lab.inventory TO sec379_write;
```

mở nhiều quyền hơn nhu cầu và khó chứng minh least privilege.

### 14.5. Vẫn cần constraint

Dù role chỉ sửa stock, bảng nên giữ `CHECK (stock >= 0)` để bảo vệ tất cả đường ghi, kể cả owner/migration và những code khác.

---

## 15. Quyền table-level và column-level không giống nhau

Trong PostgreSQL, `SELECT`/`INSERT`/`UPDATE` có thể được cấp ở cấp cột tùy dạng lệnh và loại đối tượng.

| Câu GRANT | Tác động |
| --- | --- |
| `GRANT SELECT ON table` | Đọc các cột của table theo quyền hiện hành |
| `GRANT SELECT(col1,col2) ON table` | Đọc những cột được chỉ định |
| `GRANT INSERT(col1) ON table` | INSERT giá trị vào cột cụ thể, còn phụ thuộc defaults/constraints |
| `GRANT UPDATE(col1) ON table` | UPDATE cột cụ thể |
| `GRANT DELETE ON table` | DELETE hàng, không cấp riêng từng cột |
| `GRANT TRUNCATE ON table` | TRUNCATE table |
| `GRANT REFERENCES ON table` | Dùng table/cột phù hợp trong FK |
| `GRANT TRIGGER ON table` | Tạo trigger theo quyền và quy tắc liên quan |

### 15.1. DELETE là quyền lớn

Dù ứng dụng có thể xóa “một đơn”, việc cấp DELETE cho toàn bảng là năng lực có thể xóa nhiều hàng. Cần kiểm soát bằng nghiệp vụ, RLS, triggers hoặc API boundary phù hợp.

### 15.2. TRUNCATE không giống DELETE

TRUNCATE có cơ chế riêng và không diễn giải đơn giản như DELETE từng hàng theo RLS. Không cấp TRUNCATE cho runtime chỉ vì họ cần xóa một dòng.

### 15.3. REFERENCES không phải SELECT

Để tạo foreign key tham chiếu bảng khác, cần quyền REFERENCES phù hợp. Không cấp quyền đó cho mọi API thông thường.

### 15.4. Column privileges cần kiểm tra truy vấn thật

Một câu `UPDATE stock = stock - 1 WHERE sku = ...` cần UPDATE stock và SELECT cho những cột được đọc, chứ không chỉ UPDATE.

### 15.5. Quyền có thể đến từ nhiều đường

Kiểm tra grants trực tiếp, membership, PUBLIC, ownership và các helper functions, thay vì chỉ đọc một câu GRANT trong migration.

---

## 16. GRANT/REVOKE không phải hệ thống DENY

PostgreSQL dùng mô hình **cấp quyền**: role có quyền nếu được cấp qua một đường hợp lệ hoặc có đặc quyền tương ứng.

### 16.1. REVOKE một grant trực tiếp

```sql
REVOKE SELECT ON sec379_lab.inventory
FROM sec379_read;
```

thu hồi một grant table-level nếu đã có.

### 16.2. Không có nghĩa role mất mọi đường đọc

Nếu role được cấp SELECT qua role khác hoặc PUBLIC, nó vẫn có thể đọc.

### 16.3. Không thể dùng REVOKE để vô hiệu hóa superuser

Một superuser thực sự có quyền vượt qua kiểm tra ACL thông thường. Muốn áp dụng least privilege, phải **không cho runtime trở thành superuser** ngay từ đầu.

### 16.4. Revoking quyền owner có giới hạn

Owner không mất quyền điều khiển object như ALTER/DROP chỉ vì REVOKE DML grants. Nếu cần tách quyền quản trị, chuyển ownership hoặc tách role.

### 16.5. REVOKE ... CASCADE có thể ảnh hưởng người nhận grant tiếp

Khi một role đã cấp quyền cho role khác bằng GRANT OPTION, thu hồi grant option có thể kéo theo thu hồi các grants phụ thuộc theo cơ chế CASCADE. Đừng dùng CASCADE khi chưa hiểu chuỗi ủy quyền.

---

## 17. GRANT OPTION và khả năng phân phối quyền

Một role có thể được cấp quyền **kèm khả năng cấp tiếp** cho người khác.

```sql
GRANT SELECT ON TABLE app.some_report
TO reporting_lead
WITH GRANT OPTION;
```

### 17.1. Rủi ro

Nếu role chỉ cần xem báo cáo, việc cho GRANT OPTION có thể khiến role đó cấp quyền đọc cho các đối tượng ngoài nhóm dự kiến.

### 17.2. Owner có quyền grant vốn có

Owner thường có khả năng phân phối quyền trên đối tượng thuộc sở hữu. Không cần biến owner thành runtime user để đơn giản hóa việc cấp quyền.

### 17.3. GRANT OPTION khác membership ADMIN OPTION

- `WITH GRANT OPTION` trên object privilege: có thể cấp tiếp quyền object tương ứng.
- `ADMIN OPTION` trên role membership: liên quan quyền quản trị membership theo phiên bản.

Không phải cùng một thuộc tính.

### 17.4. Kiểm soát người được phép grant

Dùng deployment scripts, review và catalog audit để phát hiện quyền được cấp rộng ngoài ý định. Least privilege bao gồm cả **quyền có thể tạo thêm quyền**.

---

## 18. Database-level privileges: CONNECT, CREATE, TEMPORARY

Quyền trên database khác quyền trên table.

| Database privilege | Ý nghĩa |
| --- | --- |
| `CONNECT` | Kết nối database theo cơ chế cấp quyền |
| `CREATE` | Tạo schema và một số đối tượng cấp database theo quy tắc PostgreSQL |
| `TEMPORARY`/`TEMP` | Tạo temporary tables khi được phép |

### 18.1. CONNECT không cho đọc mọi table

```sql
GRANT CONNECT ON DATABASE appdb TO app_login;
```

không đồng nghĩa `GRANT SELECT ON ALL TABLES`.

### 18.2. CREATE database privilege không phải CREATEDB role attribute

- `GRANT CREATE ON DATABASE appdb`: năng lực tạo schema/đối tượng cấp database tương ứng bên trong appdb.
- `CREATEDB` role attribute: năng lực tạo **database mới** trong cluster.

### 18.3. TEMP cần đánh giá theo threat model

Temporary table có thể hữu ích cho ETL, nhưng cũng có chi phí storage và cơ chế name resolution, nhất là với các SECURITY DEFINER functions. Không mặc định TEMP là vô hại trong hệ thống đa tenant không tin cậy.

### 18.4. PUBLIC có thể đã có CONNECT/TEMP

Trên nhiều database PostgreSQL, CONNECT và TEMP được cấp cho PUBLIC theo mặc định. Nếu muốn kiểm soát theo allowlist, phải kiểm tra và thu hồi grants phù hợp. Đổi CONNECT trên database đang có client có thể làm ứng dụng/monitoring không kết nối lại được.

### 18.5. Không thay đổi database hệ thống khi học

Không chạy `REVOKE CONNECT ON DATABASE postgres FROM PUBLIC` hoặc thay quyền database đang dùng chung chỉ để minh họa. Tạo database lab riêng và phân tích tác động trước.

---

## 19. Schema public và thay đổi mặc định từ PostgreSQL 15

Một vấn đề lịch sử là nhiều cluster cho mọi role khả năng tạo đối tượng trong schema `public`, trong khi schema đó thường nằm trong `search_path`.

### 19.1. PostgreSQL 15 thay đổi default của database mới

Ở PostgreSQL 15 trở lên, schema `public` trong database mới có mặc định an toàn hơn: quyền CREATE cho PUBLIC không còn được cấp rộng như ở các phiên bản cũ, và ownership gắn với mô hình `pg_database_owner`.

### 19.2. Database đã nâng cấp có thể giữ grants cũ

Một database tạo từ PostgreSQL cũ rồi upgrade/restore có thể vẫn giữ ACL của schema public. Không được kết luận “đang ở PG16 nên chắc chắn PUBLIC không có CREATE”.

### 19.3. Kiểm tra quyền thực tế

```sql
SELECT
    has_schema_privilege(
        'public',
        'USAGE'
    ) AS can_use_public,
    has_schema_privilege(
        'public',
        'CREATE'
    ) AS can_create_in_public;
```

Kết quả được tính theo role hiện tại.

### 19.4. Thu hồi khi có kế hoạch

```sql
-- Chỉ minh họa, cần đánh giá dependencies trước khi chạy:
-- REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Thu hồi CREATE có thể ảnh hưởng công cụ migration hoặc extension cũ nếu trước đây dựa vào quyền rộng đó. Cần cập nhật role/schema chuyên dụng và thử trên staging.

### 19.5. public schema không phải kho dữ liệu public

Tên `public` không có nghĩa mọi table bên trong đều tự được SELECT bởi mọi role. Quyền schema và table là hai lớp khác nhau.

---

## 20. Sequence privileges và identity columns

Khi thiết kế INSERT, cần xem **nguồn tạo khóa**.

Ví dụ table dùng sequence thủ công:

```sql
CREATE SEQUENCE app.order_number_seq;

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY
        DEFAULT nextval('app.order_number_seq'::REGCLASS),
    ...
);
```

Role INSERT không nên được cấp quyền sequence nhiều hơn nhu cầu.

### 20.1. Quyền trên sequence

PostgreSQL hỗ trợ các quyền sequence như `USAGE`, `SELECT` và `UPDATE` theo chức năng tương ứng.

Đối với mẫu gọi `nextval`, quyền `USAGE` (hoặc quyền phù hợp theo quy tắc PostgreSQL) thường là quyền cần xét.

```sql
GRANT USAGE ON SEQUENCE app.order_number_seq
TO app_writer;
```

### 20.2. Không coi table INSERT tự cấp mọi quyền sequence

Nếu một cột có DEFAULT gọi `nextval` từ sequence riêng, quyền trên sequence có thể cần được cấp ngoài quyền INSERT table.

### 20.3. IDENTITY có cơ chế khác SERIAL/default thủ công

Cột `GENERATED ... AS IDENTITY` được PostgreSQL quản lý khác một cột với DEFAULT `nextval` thủ công. Không áp dụng máy móc cùng yêu cầu sequence grant cho mọi trường hợp identity; kiểm tra phiên bản và plan quyền thực tế.

### 20.4. Dùng GRANT ON ALL SEQUENCES có phạm vi rộng

```sql
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_writer;
```

có thể phù hợp một job tổng quát có trách nhiệm nhập dữ liệu ở mọi bảng, nhưng không phải mặc định tốt cho service chỉ ghi vào một sequence.

### 20.5. Sequence không rollback như dữ liệu bảng

Giá trị được lấy từ sequence có thể bị bỏ qua khi transaction rollback. Không dùng các số tăng như bằng chứng tất cả transactions đều thành công hoặc để tính tổng giao dịch.

---

## 21. Quyền EXECUTE trên function

Một function có thể là đường truy cập dữ liệu hoặc đường ghi dữ liệu gián tiếp.

### 21.1. Mặc định EXECUTE trên function

Trong cấu hình PostgreSQL thông thường, function mới được cấp `EXECUTE` cho PUBLIC theo default privileges, trừ khi đã điều chỉnh. Vì vậy việc tạo một SECURITY DEFINER function nhạy cảm mà quên REVOKE có thể tạo bề mặt truy cập không mong muốn.

### 21.2. Ví dụ function có quyền hạn chế

```sql
-- Chỉ chạy trong database đã có schema và table phù hợp.
CREATE FUNCTION app.get_order_status(p_order_id BIGINT)
RETURNS TEXT
LANGUAGE SQL
STABLE
AS $fn$
    SELECT status
    FROM app.orders
    WHERE order_id = p_order_id;
$fn$;

REVOKE ALL ON FUNCTION app.get_order_status(BIGINT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.get_order_status(BIGINT)
TO app_reader;
```

### 21.3. Trong function SECURITY INVOKER

Đây là hành vi mặc định đối với function thông thường: caller cần các quyền đối tượng nền thích hợp trong lúc function chạy.

### 21.4. Trong function SECURITY DEFINER

Function có thể chạy với quyền owner; caller cần quyền EXECUTE function nhưng không nhất thiết có SELECT/UPDATE trực tiếp trên bảng nền mà function đụng tới.

### 21.5. Một read-only role có thể ghi gián tiếp

Nếu role không có UPDATE table nhưng được EXECUTE một SECURITY DEFINER function làm UPDATE, role có thể gây thay đổi database qua function. Do đó “không có table UPDATE” **chưa đủ** chứng minh role read-only về mặt nghiệp vụ.

### 21.6. GRANT EXECUTE cần chỉ rõ chữ ký

Với function overload, cú pháp như:

```sql
GRANT EXECUTE ON FUNCTION app.get_order_status(BIGINT)
TO app_reader;
```

xác định đúng function theo kiểu tham số; không dựa vào tên mà bỏ qua chữ ký.

---

## 22. SECURITY DEFINER và nguyên tắc quyền tối thiểu

Một SECURITY DEFINER function là công cụ mạnh để công bố một thao tác hẹp mà không cấp quyền nền cho caller.

Nhưng chính vì có quyền nâng cao, nó cũng là mục tiêu tấn công nếu search_path, dynamic SQL hoặc input validation không được kiểm soát.

### 22.1. Ví dụ giới hạn kết quả

Trong lab `sec379_lab`, có thể tạo một function chỉ trả stock của một SKU, không trả unit_cost hoặc internal_note:

```sql
SET ROLE sec379_owner;

CREATE FUNCTION sec379_lab.lookup_stock(p_sku TEXT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT i.stock
    FROM sec379_lab.inventory AS i
    WHERE i.sku = p_sku;
$fn$;

REVOKE ALL ON FUNCTION sec379_lab.lookup_stock(TEXT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec379_lab.lookup_stock(TEXT)
TO sec379_read;

RESET ROLE;
```

**Lưu ý:** Function do `sec379_owner` sở hữu. Nó chạy theo quyền owner theo semantics SECURITY DEFINER. Các đối tượng quan trọng được viết rõ schema; search_path chỉ dùng những schema đáng tin.

### 22.2. Vì sao SET search_path quan trọng?

Nếu một function được gọi bằng quyền owner nhưng resolve một tên table/function không định danh đầy đủ qua schema do caller có thể tạo object, caller có thể tìm cách đưa object giả mạo vào đường phân giải tên.

Đặt search_path an toàn và schema-qualify tên quan trọng giúp giảm nguy cơ này.

### 22.3. pg_temp cần cân nhắc vị trí

Temporary schema có quy tắc tìm kiếm tên quan hệ đặc biệt. Khi viết SECURITY DEFINER code, thường nên đặt `pg_temp` ở cuối một search_path được kiểm soát để tránh việc đối tượng tạm che tên đối tượng tin cậy.

### 22.4. Không để PUBLIC EXECUTE mặc định trên function nhạy cảm

Khi triển khai, nên tạo function, thu hồi quyền PUBLIC và cấp riêng role được phép trong **cùng một transaction an toàn** nếu phù hợp, tránh khoảng thời gian function mới xuất hiện với quyền quá rộng.

### 22.5. Không lộ bí mật qua MESSAGE/DETAIL

Một function chỉ trả số stock nhưng khi lỗi lại `RAISE EXCEPTION 'Giá vốn là ...'` vẫn rò thông tin. Cần kiểm tra cả thông điệp, HINT, trả về lỗi và timing theo threat model.

### 22.6. SECURITY DEFINER không thay xác thực tenant

Một function có tham số `p_tenant_id` do client tự nhập và dùng quyền owner để đọc tất cả tenants có thể biến thành lỗ hổng đọc chéo tenant. Phải xác định tenant từ nguồn tin cậy, không chỉ từ input.

### 22.7. Không tạo function đặc quyền nếu GRANT thuần đã đủ

Nếu một role chỉ cần SELECT hai cột trên table, column-level GRANT hoặc view read-only với ownership/permission thích hợp có thể đơn giản hơn dùng SECURITY DEFINER function.

---

## 23. Ownership của view và security_invoker

Một view không phải bản sao dữ liệu vật lý, nhưng nó có owner và quyền SELECT như một đối tượng schema.

### 23.1. View mặc định

Với view thông thường, việc kiểm tra quyền đọc bảng nền và RLS có thể dựa trên **view owner** theo semantics PostgreSQL. Điều này cho phép cấp SELECT trên view mà không cấp SELECT toàn bộ bảng nền trực tiếp cho caller.

### 23.2. Rủi ro

Nếu view owner có quyền rộng hoặc là table owner bypass RLS, một view công bố không được kiểm soát có thể trả hàng mà caller không nên thấy.

### 23.3. security_invoker (PostgreSQL 15+)

```sql
CREATE VIEW app.v_orders_invoker
WITH (security_invoker = true)
AS
SELECT order_id, tenant_id, status
FROM app.orders;
```

Với tùy chọn này, quyền trên bảng nền và RLS được xét theo caller theo quy tắc tính năng, thay vì mặc định theo owner của view.

### 23.4. Một thay đổi có thể làm consumer lỗi permission denied

Nếu caller được cấp SELECT view nhưng không có quyền nền, bật `security_invoker=true` có thể làm họ mất khả năng đọc. Đây là thay đổi bảo mật/hợp đồng, không chỉ là tối ưu SQL.

### 23.5. security_barrier khác security_invoker

- `security_invoker` quyết định ngữ cảnh quyền truy cập bảng nền.
- `security_barrier` hạn chế một số kiểu predicate pushdown nhằm giảm nguy cơ leak khi view dùng để lọc hàng bảo mật.

Không nhầm hai thuộc tính hoặc xem chúng tự thay RLS.

---

## 24. Row-Level Security và owner bypass

RLS cho phép hạn chế những hàng phù hợp với role.

Ví dụ:

```sql
ALTER TABLE app.tenant_orders
ENABLE ROW LEVEL SECURITY;
```

Sau khi bật RLS, policy thích hợp xác định hàng được xem/ghi cho những roles chịu RLS.

### 24.1. Table owner thường bypass RLS

Theo mặc định, table owner không phải chịu RLS như một role thường. Đây là lý do **không dùng table-owner role làm login của API tenant**.

### 24.2. FORCE ROW LEVEL SECURITY

```sql
ALTER TABLE app.tenant_orders
FORCE ROW LEVEL SECURITY;
```

làm cho table owner cũng chịu chính sách RLS theo cơ chế PostgreSQL, trừ các trường hợp đặc quyền vượt RLS.

### 24.3. Superuser và BYPASSRLS

Superuser và role có `BYPASSRLS` vẫn bỏ qua RLS; `FORCE ROW LEVEL SECURITY` không biến chúng thành roles bị giới hạn như user thường.

### 24.4. RLS không phải quyền schema/table

Caller cần quyền SELECT/UPDATE tương ứng trên bảng. RLS kiểm tra tập hàng, không cấp quyền DML vốn chưa có.

### 24.5. RLS policy có thể kết hợp

PostgreSQL hỗ trợ các policy permissive/restrictive và điều kiện khác nhau cho SELECT/INSERT/UPDATE/DELETE. Không suy luận “có một policy tenant filter” là mọi hướng ghi sẽ tự an toàn.

### 24.6. Tránh thiết kế dựa vào SET app.tenant_id tùy ý

Một điều kiện:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::INTEGER
)
```

chỉ là cơ chế đọc session setting. Nếu người gọi SQL không tin cậy có thể tự đặt `app.tenant_id` bằng tenant khác, setting đó **không** phải nguồn xác thực đáng tin.

Muốn dùng session context để enforce tenant phải có kiến trúc xác thực và quản lý connection/pooling chặt chẽ, ngăn client giả mạo, cùng kiểm thử toàn bộ đường truy cập.

---

## 25. Lab mở rộng: kiểm tra RLS theo role

Ta có thể thử một mô hình RLS tối giản với một role chỉ được nhìn tenant 10. Đây là ví dụ học cấu trúc policy; production thường cần mô hình role/identity linh hoạt hơn.

### 25.1. Tạo bảng và dữ liệu

```sql
SET ROLE sec379_owner;

CREATE TABLE sec379_lab.tenant_orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (tenant_id, order_id)
);

INSERT INTO sec379_lab.tenant_orders (
    tenant_id, order_id, amount
)
VALUES
    (10, 1001, 100.00),
    (10, 1002, 200.00),
    (20, 1001, 300.00);

ALTER TABLE sec379_lab.tenant_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant10_reader
ON sec379_lab.tenant_orders
FOR SELECT
TO sec379_app_reader
USING (tenant_id = 10);

GRANT SELECT ON TABLE sec379_lab.tenant_orders
TO sec379_app_reader;

RESET ROLE;
```

### 25.2. Truy vấn bằng role consumer

```sql
SET ROLE sec379_app_reader;

SELECT tenant_id, order_id, amount
FROM sec379_lab.tenant_orders
ORDER BY tenant_id, order_id;

RESET ROLE;
```

Trong ví dụ này, role consumer phù hợp với policy tenant 10 nên chỉ thấy các hàng tenant 10.

### 25.3. Truy vấn bằng owner

Nếu owner query bảng trong môi trường lab, owner theo mặc định bypass RLS và có thể thấy cả tenant 10 và tenant 20.

### 25.4. Thử FORCE RLS

```sql
SET ROLE sec379_owner;

ALTER TABLE sec379_lab.tenant_orders
FORCE ROW LEVEL SECURITY;

RESET ROLE;
```

Sau đó owner có thể bị giới hạn theo policies; nếu không có policy cho owner, kết quả có thể là 0 hàng. Superuser/BYPASSRLS vẫn có quyền vượt RLS theo cơ chế tương ứng.

### 25.5. Không dùng phép thử superuser để chứng minh RLS

Một người quản trị có quyền superuser có thể thấy tất cả hàng, kể cả khi role consumer được RLS giới hạn đúng. Hãy test bằng **role hiệu lực như ứng dụng thật**, không chỉ tài khoản admin.

### 25.6. Policy cho từng role chỉ là minh họa

Không nên tạo hàng chục nghìn policies cố định nếu hệ thống có rất nhiều tenants. Cần chọn mô hình identity/role/session được bảo vệ và vận hành được, đồng thời hiểu chi phí và bề mặt bảo mật của nó.

---

## 26. Default privileges: quyền cho đối tượng tạo trong tương lai

Một câu `GRANT` trên table hiện có **không tự áp dụng cho table tạo ngày mai**.

PostgreSQL cung cấp:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE owner_role
IN SCHEMA some_schema
GRANT SELECT ON TABLES TO reader_role;
```

Ý nghĩa: khi **owner_role** tạo những đối tượng thuộc loại phù hợp trong schema đó về sau, PostgreSQL áp dụng default grants tương ứng.

### 26.1. Chỉ ảnh hưởng đối tượng tương lai

`ALTER DEFAULT PRIVILEGES` không tự thay ACL của toàn bộ bảng đã tồn tại.

### 26.2. Dựa trên role đang tạo đối tượng

Default privileges không đơn giản áp dụng mọi grants của tất cả role memberships. Cần xác định **role tạo object thực tế** trong migration, đặc biệt khi dùng `SET ROLE`.

Nếu migration kết nối bằng `deploy_admin` nhưng không `SET ROLE app_owner`, object có thể được tạo với owner và default privileges của deploy_admin, không phải app_owner như dự định.

### 26.3. Ví dụ trong schema báo cáo tách biệt

Tạo một schema chỉ chứa read models không nhạy cảm:

```sql
CREATE SCHEMA sec379_reports
AUTHORIZATION sec379_owner;

GRANT USAGE ON SCHEMA sec379_reports TO sec379_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE sec379_owner
IN SCHEMA sec379_reports
GRANT SELECT ON TABLES TO sec379_read;
```

Sau đó khi `sec379_owner` tạo bảng/view trong schema báo cáo, default privilege có thể cấp SELECT cho reader theo cấu hình.

### 26.4. Tại sao không áp dụng grant SELECT ALL cho mọi bảng nội bộ?

Nếu schema chứa giá vốn, token, PII, secrets hoặc cột kiểm soát truy cập, quy tắc `GRANT SELECT ON TABLES` cho reader có thể tự động công bố những đối tượng/cột nhạy cảm mới.

Least privilege đòi hỏi **phân tách schema phù hợp và review default privileges**, không đặt mặc định quá rộng để khỏi viết GRANT.

### 26.5. Default privileges toàn cục và theo schema có cách hợp thành

Một default grant toàn cục có thể áp dụng rộng. Một `REVOKE` theo schema không nhất thiết phủ định quyền đã được default grant toàn cục. Cần kiểm tra quy tắc áp dụng và thiết kế chiến lược nhất quán.

### 26.6. Không nhầm với role attribute

`ALTER DEFAULT PRIVILEGES` thay quyền trên **đối tượng được tạo về sau**, không tự thêm LOGIN/CREATEROLE/SUPERUSER hoặc membership cho role.

---

## 27. GRANT ON ALL TABLES khác ALTER DEFAULT PRIVILEGES

Hai lệnh có tác động thời gian khác nhau:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA reporting
TO reporting_reader;
```

và:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE reporting_owner
IN SCHEMA reporting
GRANT SELECT ON TABLES TO reporting_reader;
```

### 27.1. ALL TABLES IN SCHEMA

Áp dụng trên những bảng/view thuộc phạm vi hỗ trợ **đang tồn tại** ở thời điểm chạy lệnh.

### 27.2. ALTER DEFAULT PRIVILEGES

Áp dụng cho **đối tượng sẽ được tạo**, không backfill những đối tượng cũ.

### 27.3. Khi triển khai một schema báo cáo mới

Nếu chính sách thực sự cho phép reader xem tất cả đối tượng báo cáo hiện tại và tương lai, có thể cần cả hai cơ chế.

### 27.4. Khi quyền phải xét từng đối tượng

Nếu reporting schema chứa dataset có mức nhạy cảm khác nhau, không nên dùng broad `ALL TABLES`/default grant. Cấp theo từng view/table được công bố.

### 27.5. Khả năng sở hữu nhiều creator roles

Trong một schema, nếu service A tạo bảng và service B tạo bảng bằng role khác, default privileges của owner_role A không tự điều khiển quyền trên object do B tạo. Kiểm soát **ai chạy DDL** là thành phần của least privilege.

---

## 28. Các predefined roles cần thận trọng

PostgreSQL cung cấp một số roles dựng sẵn cho quản trị/quan sát. Tên và khả năng có thể khác giữa các phiên bản.

Ví dụ:

| Predefined role | Công dụng khái quát |
| --- | --- |
| `pg_monitor` | Năng lực quan sát/monitoring rộng hơn role thường |
| `pg_read_all_settings` | Đọc nhiều thiết lập cấu hình |
| `pg_read_all_stats` | Đọc nhiều thông tin thống kê |
| `pg_signal_backend` | Gửi signal tới các backend theo giới hạn |
| `pg_read_all_data` | Quyền đọc rộng trên dữ liệu theo đặc tính role |
| `pg_write_all_data` | Quyền ghi rộng theo đặc tính role |
| `pg_read_server_files` | Đọc file trên server theo giới hạn và đặc tính nguy hiểm |
| `pg_write_server_files` | Ghi file trên server theo giới hạn và đặc tính nguy hiểm |
| `pg_execute_server_program` | Thực thi chương trình phía server trong ngữ cảnh hỗ trợ |

### 28.1. Không coi predefined roles là “nhóm tiện ích vô hại”

Một role đọc mọi dữ liệu hoặc file server có phạm vi rất lớn. Cần đánh giá tương tự cấp đặc quyền quản trị.

### 28.2. pg_read_all_data không tự bypass mọi RLS

Role này cung cấp phạm vi đọc rộng trên đối tượng theo đặc tính của nó, nhưng **không mặc nhiên có BYPASSRLS**. Điều này khác với superuser hoặc role được gắn BYPASSRLS.

### 28.3. pg_monitor không thay role báo cáo kinh doanh

Một dashboard theo dõi CPU/connections có nhu cầu khác với hệ thống đọc doanh thu hoặc PII. Không cấp pg_monitor chỉ vì role cần đọc một bảng reporting.

### 28.4. File/server-program roles có rủi ro cao

Năng lực đọc/ghi file phía PostgreSQL server hoặc thực thi chương trình có thể mở bề mặt tác động vượt database objects. Chỉ cấp cho operator được tin cậy và có kiểm soát.

### 28.5. Kiểm tra phiên bản

Không giả định mọi predefined role nói trên có ở tất cả PostgreSQL versions; xem danh sách thực tế trong `pg_roles` và tài liệu phiên bản đang triển khai.

---

## 29. CREATEROLE, membership và đường leo thang quyền

Một role có `CREATEROLE` có thể quản lý role trong phạm vi hệ thống cho phép. Nhưng tính năng này có những chi tiết quan trọng về membership và grant option.

### 29.1. Cần hiểu quyền quản trị role khác quyền dữ liệu

Nếu cấp CREATEROLE cho runtime API, API không chỉ đọc/ghi dữ liệu mà còn có khả năng ảnh hưởng mô hình quyền của các role khác trong những giới hạn nhất định.

### 29.2. PostgreSQL 16 thay đổi semantics quản trị membership

Các tùy chọn `ADMIN`, `INHERIT` và `SET` của membership được quản lý chi tiết hơn. Không sao chép scripts phân quyền từ PostgreSQL 14 sang PostgreSQL 16 mà không kiểm tra semantics mới.

### 29.3. Không nên tự gán nhiều membership privileged

Ví dụ một account đã được cấp membership tới owner role có thể có năng lực `SET ROLE` rồi thực hiện DDL tùy membership options. Đây là đường quyền gián tiếp mà kiểm tra ACL trực tiếp rất dễ bỏ sót.

### 29.4. Cần review cả grants role-to-role

Không chỉ audit:

```sql
GRANT SELECT ON table ...
```

mà còn:

```sql
GRANT powerful_role TO runtime_role;
```

và khả năng runtime role thực sự sử dụng quyền đó.

### 29.5. Nguyên tắc

Chỉ những account provisioning/migration được ủy quyền mới cần role administration. Không đưa quyền này vào pool ứng dụng hoặc job đọc báo cáo.

---

## 30. Kiểm tra role attributes qua pg_roles

Catalog `pg_roles` hiển thị những thuộc tính cơ bản của role mà không cần truy cập bảng mật khẩu nhạy cảm.

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolinherit,
    rolconnlimit
FROM pg_catalog.pg_roles
WHERE rolname LIKE 'sec379_%'
ORDER BY rolname;
```

### 30.1. Điều cần xác nhận

Trong lab, các role `sec379_*` được tạo NOLOGIN, không SUPERUSER, không CREATEDB, không CREATEROLE và không BYPASSRLS.

### 30.2. Role attributes không đủ mô tả toàn quyền

Một role `rolsuper=false` vẫn có thể đọc dữ liệu nhạy cảm nếu được GRANT SELECT từ role khác hoặc membership đặc quyền phù hợp.

### 30.3. Không đọc pg_authid trong application

Các thông tin xác thực nhạy cảm thuộc catalog được bảo vệ. Đừng cấp quyền đọc catalog mật khẩu chỉ để kiểm tra role attributes cơ bản; sử dụng `pg_roles` và công cụ quản trị phù hợp.

### 30.4. Query tìm superusers

Trên môi trường được ủy quyền:

```sql
SELECT rolname
FROM pg_catalog.pg_roles
WHERE rolsuper
ORDER BY rolname;
```

Chỉ số lượng superuser cần ít và có chủ đích. Không tự xóa/chỉnh role quản trị nếu không có kế hoạch khôi phục quyền truy cập cluster.

### 30.5. Query tìm BYPASSRLS

```sql
SELECT rolname
FROM pg_catalog.pg_roles
WHERE rolbypassrls
ORDER BY rolname;
```

Đặc biệt quan trọng với hệ thống dùng RLS bảo vệ tenants.

---

## 31. Kiểm tra owner của schema, table và function

### 31.1. Schema owner

```sql
SELECT
    n.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(n.nspowner)
        AS schema_owner
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname IN ('sec379_lab', 'sec379_reports')
ORDER BY n.nspname;
```

### 31.2. Table/view/sequence owner

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_catalog.pg_get_userbyid(c.relowner)
        AS object_owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sec379_lab'
ORDER BY c.relkind, c.relname;
```

Một số `relkind`:

- `r`: ordinary table.
- `p`: partitioned table.
- `v`: view.
- `m`: materialized view.
- `S`: sequence.
- `i`: index.

### 31.3. Function owner

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_catalog.pg_get_userbyid(p.proowner)
        AS function_owner,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS arguments,
    p.prosecdef AS security_definer
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec379_lab'
ORDER BY p.proname;
```

### 31.4. Vì sao kiểm tra owner sau migration?

Nếu một migration chạy bằng `deploy_admin` thay vì `SET ROLE sec379_owner`, table mới có thể thuộc owner ngoài dự kiến. Điều này ảnh hưởng DDL sau đó, default privileges và có thể cả RLS/view semantics.

---

## 32. Kiểm tra quyền hiệu lực bằng has_*_privilege

PostgreSQL cung cấp các hàm kiểm tra quyền hiệu lực cho một role và object cụ thể.

### 32.1. Schema usage

```sql
SELECT pg_catalog.has_schema_privilege(
    'sec379_app_reader',
    'sec379_lab',
    'USAGE'
) AS can_use_schema;
```

### 32.2. Table-level SELECT

```sql
SELECT pg_catalog.has_table_privilege(
    'sec379_app_reader',
    'sec379_lab.inventory',
    'SELECT'
) AS table_select_granted;
```

Trong lab, role chỉ được cấp SELECT ở cấp **cột**. Vì vậy không được suy ra table-level SELECT là TRUE chỉ từ việc có quyền đọc sku/stock.

### 32.3. Column-level SELECT

```sql
SELECT
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'sku',
        'SELECT'
    ) AS can_read_sku,
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'stock',
        'SELECT'
    ) AS can_read_stock,
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'unit_cost',
        'SELECT'
    ) AS can_read_cost;
```

Kỳ vọng can_read_sku/can_read_stock là TRUE, can_read_cost là FALSE nếu không có grants khác làm mở quyền.

### 32.4. Function EXECUTE

```sql
SELECT pg_catalog.has_function_privilege(
    'sec379_app_reader',
    'sec379_lab.lookup_stock(text)',
    'EXECUTE'
) AS can_call_lookup;
```

### 32.5. Quyền hiệu lực không thay thử truy vấn

Một function privilege query có thể cho biết role có quyền EXECUTE, nhưng body function có thể vẫn lỗi do quyền đối tượng nền, search_path, RLS, constraint hoặc logic nghiệp vụ.

Kiểm tra vừa bằng helper functions, vừa bằng truy vấn thực tế từ ngữ cảnh caller.

### 32.6. Đọc ACL thô không đủ

Các cột ACL như `relacl` có thể NULL khi dùng default ACL, và role membership/PUBLIC làm quyền hiệu lực khác với một entry đơn lẻ. Hãy dùng helper functions và kiểm tra role context khi cần xác định “thực sự làm được gì?”.

---

## 33. psql meta-commands để xem quyền

Nếu dùng `psql`:

```text
\du
\du+
\dn+
\dp sec379_lab.*
\z sec379_lab.*
\df+ sec379_lab.*
```

Ý nghĩa khái quát:

- `\du`: roles và role attributes.
- `\dn+`: schemas và quyền liên quan.
- `\dp`/`\z`: access privileges trên relations.
- `\df+`: thông tin function.

Các lệnh này là **psql meta-command**, không phải SQL dùng nguyên văn trong JDBC.

### 33.1. Vì sao phải xem cả nhiều nguồn?

Một role có quyền nhờ:

- Grant trực tiếp.
- Role membership.
- PUBLIC.
- Ownership.
- Predefined role attributes.
- Security-definer view/function.
- Các quyền đặc biệt như superuser/BYPASSRLS.

Một `\dp` không tự trình bày trọn mọi đường quyền gián tiếp cho mọi hành động.

### 33.2. Trong CI/CD

Có thể viết automated permission tests bằng các hàm `has_*_privilege` và truy vấn thử có kiểm soát, thay vì dựa vào việc một operator nhìn output `\du`.

---

## 34. Chuyển owner: ALTER ... OWNER TO

Khi tái cấu trúc quyền, có thể cần chuyển sở hữu đối tượng.

Ví dụ:

```sql
ALTER TABLE app.orders OWNER TO new_owner;
```

### 34.1. Điều kiện không chỉ là có GRANT UPDATE

Thông thường, việc đổi owner yêu cầu role thực hiện có quyền sở hữu/khả năng hành động thay owner theo quy tắc PostgreSQL, có quyền chuyển sang owner mới và owner mới có quyền cần thiết đối với schema. Superuser có thể làm nhiều việc vượt những giới hạn của non-superuser.

### 34.2. Vì sao không chuyển ownership cho login runtime?

Nếu mục đích chỉ là cho service sửa cột stock, `GRANT UPDATE(stock)` phù hợp hơn nhiều so với `ALTER TABLE ... OWNER TO runtime_login`.

### 34.3. Đổi owner ảnh hưởng RLS

Owner mới có thể có trạng thái RLS khác role trước (đặc biệt owner bypass RLS mặc định). Cần kiểm tra policies và view/function ownership cùng lúc.

### 34.4. Đổi owner ảnh hưởng quyền bảo trì/migration

Migration tiếp theo cần chạy dưới role có thể thao tác đối tượng đã đổi owner. Không chuyển owner một cách cục bộ rồi quên toàn bộ pipeline.

### 34.5. Kiểm tra dependencies

Ownership của table, sequences liên quan, views, functions hoặc các đối tượng không tự nhiên luôn đồng nhất chỉ vì đổi một table. Audit từng loại đối tượng và quy tắc PostgreSQL tương ứng.

---

## 35. REASSIGN OWNED và DROP OWNED

Khi một nhân sự nghỉ việc hoặc một role cũ cần được xóa, không nên DROP ROLE ngay nếu role vẫn sở hữu đối tượng.

### 35.1. REASSIGN OWNED

```sql
REASSIGN OWNED BY old_owner TO new_owner;
```

chuyển ownership của những đối tượng thuộc role cũ trong phạm vi PostgreSQL áp dụng, giúp giữ đối tượng thay vì xóa.

### 35.2. DROP OWNED

```sql
DROP OWNED BY old_owner;
```

có thể xóa các đối tượng role sở hữu trong database hiện tại và thu hồi những quyền đã được cấp cho role theo semantics PostgreSQL; **không phải lệnh an toàn để dọn một vài grants nhỏ**.

### 35.3. REASSIGN OWNED không thu hồi mọi grants còn lại

Sau khi chuyển ownership, có thể cần `DROP OWNED BY old_owner` để dọn privileges còn lại trước khi DROP ROLE, nhưng phải hiểu chính xác đối tượng nào bị tác động và chạy có kiểm soát.

### 35.4. Nhiều database trong cùng cluster

Một role có thể sở hữu đối tượng ở nhiều databases. Các bước reassign/cleanup cần được thực hiện theo phạm vi từng database và các đối tượng shared tương ứng; không chỉ chạy ở một database rồi giả định role đã hoàn toàn không còn phụ thuộc.

### 35.5. Quyền thực thi lệnh

REASSIGN OWNED/DROP OWNED có yêu cầu role membership/quyền tương ứng. Không trao các quyền đó cho runtime service chỉ để tiện vận hành.

### 35.6. Không dùng CASCADE khi chưa biết tác động

DROP OWNED với CASCADE có thể ảnh hưởng đối tượng phụ thuộc nằm ngoài một sơ đồ bạn tưởng chỉ có role cũ. Trước khi chạy production phải inventory, backup/restore plan và review dependencies.

---

## 36. Quyền của migration role

Migration cần có năng lực khác runtime. Một mô hình hợp lý:

```text
Deployment pipeline
  |
  +-- xác thực bằng deploy_login có kiểm soát
  |
  +-- SET ROLE app_owner (khi được phép)
        |
        +-- CREATE/ALTER TABLE
        +-- CREATE INDEX
        +-- CREATE/REPLACE VIEW
        +-- CREATE FUNCTION
        +-- ALTER DEFAULT PRIVILEGES theo chính sách
  |
  +-- RESET ROLE
  |
  +-- deploy runtime GRANTs qua script review
```

### 36.1. Ownership nhất quán

Nếu tất cả objects của ứng dụng do `app_owner` (NOLOGIN) sở hữu, các migration sau dễ đoán role nào cần DDL và default grants nào được áp dụng.

### 36.2. Không dùng superuser cho mọi migration

Một số tác vụ quản trị đặc biệt có thể cần quyền cao, nhưng phần lớn CREATE/ALTER đối tượng ứng dụng có thể thực hiện qua owner/migration role được giới hạn.

### 36.3. Tách migration và app pool credentials

Nếu cùng một secret được dùng để deploy schema và chạy HTTP API, sự cố runtime có thể mở cửa DDL. Tách credentials theo trách nhiệm.

### 36.4. Kiểm tra quyền sau mỗi migration

Một migration có thể vô tình tạo function với EXECUTE PUBLIC hoặc view có owner khác; CI/CD nên phát hiện ngay.

### 36.5. Rollback migration không chỉ là DROP

Một migration thay grants/ownership có thể làm application mất quyền hoặc mở quyền. Rollback phải xem lại ACL, default privileges và dependencies, không chỉ bỏ table mới.

---

## 37. Thiết kế vai trò cho một ứng dụng nhiều thành phần

Một hệ thống có thể gồm API đọc, API ghi, job ETL, BI và operator.

| Thành phần | Quyền đề xuất theo nhu cầu | Tránh cấp |
| --- | --- | --- |
| API đọc catalog | USAGE schema + SELECT cột/view cần thiết | SUPERUSER, ALTER/DROP, SELECT PII |
| API cập nhật tồn kho | SELECT/UPDATE cột liên quan hoặc EXECUTE function hẹp | ALL TABLES, BYPASSRLS |
| Job ETL | INSERT/UPDATE bảng staging/target xác định, USAGE sequence khi cần | CREATE ROLE, SUPERUSER |
| Dashboard BI | SELECT views báo cáo đủ phạm vi | Direct SELECT toàn bộ bảng nội bộ |
| Migration pipeline | Quyền DDL qua owner role được kiểm soát | Credentials dùng chung với runtime |
| Monitoring | Predefined role quan sát được chọn và quyền metrics tối thiểu | pg_read_all_data nếu chỉ cần stats |
| Backup | Quyền/công cụ backup được phê duyệt, scope rõ | Dùng chung API login |
| Break-glass admin | Quyền rất cao, có audit và approval | Sử dụng thường xuyên trong ứng dụng |

### 37.1. Không có role “app” cho toàn bộ hệ thống

Một API đọc catalog và một worker vận hành settlement có mức rủi ro khác nhau. Nên tách role theo **task boundary**, không gộp vì cùng một repository.

### 37.2. Không chia quá nhỏ đến mức bất khả vận hành

Least privilege không đòi một role cho mỗi câu SELECT. Có thể gom quyền theo trách nhiệm và dữ liệu tương đương, miễn phạm vi cần thiết và review được.

### 37.3. Quyền có thời hạn

Một tài khoản operator cần quyền nâng cao để xử lý incident có thể dùng cơ chế cấp tạm thời, hết hạn/thu hồi sau công việc. Không giữ membership mạnh vô thời hạn chỉ vì “có thể dùng lần tới”.

### 37.4. Tài khoản service không dùng chung giữa môi trường

Dev, staging và production cần credentials/roles tách biệt theo kiến trúc. Không đem superuser password production vào local developer setup.

---

## 38. Read-only không đơn giản là không có UPDATE trên table

Một role có thể không được trực tiếp UPDATE bảng nhưng vẫn gây thay đổi thông qua:

- EXECUTE một function SECURITY DEFINER có DML.
- Quyền từ một group role khác.
- `SET ROLE` sang owner/privileged role.
- Quyền CREATE trên schema dẫn tới đối tượng độc hại khi được function tin cậy tham chiếu.
- Quyền trên foreign tables/extensions có hành vi ngoài dự kiến.
- Các predefined roles hoặc đặc quyền server-level không được rà soát.

### 38.1. Test thực tế

Không chỉ hỏi:

```sql
SELECT has_table_privilege(..., 'UPDATE');
```

mà cần kiểm thử **mọi đường truy cập được công bố cho runtime** theo threat model.

### 38.2. Role read-only vẫn có thể tốn tài nguyên

SELECT nặng có thể gây CPU/I/O, memory, locks và ảnh hưởng availability. Least privilege về quyền dữ liệu không thay thế statement timeout, quota, pool limits và query governance.

### 38.3. Role read-only có thể đọc thông tin nhạy cảm

Nếu SELECT được grant quá rộng, việc không có UPDATE không giúp bảo vệ PII hoặc secrets. Least privilege phải xét cả **độ nhạy của dữ liệu đọc**.

### 38.4. Bảo vệ các SECURITY DEFINER helpers

Ngay cả một function chỉ có tên `list_orders` cũng có thể có side effects hoặc leak dữ liệu qua lỗi. Review body và owner cùng permissions.

---

## 39. Password, authentication và TLS không thay ACL

PostgreSQL sử dụng nhiều cơ chế xác thực, cấu hình chủ yếu qua `pg_hba.conf`, driver, TLS và hạ tầng.

### 39.1. Credential hợp lệ chỉ cho biết “ai đang kết nối”

Quyền SQL phải được cấu hình tiếp ở role, database, schema và object.

### 39.2. Dùng cơ chế lưu mật khẩu phù hợp

SCRAM-SHA-256 là một cơ chế xác thực mật khẩu hiện đại được PostgreSQL hỗ trợ. Cấu hình cluster và clients phải tương thích; tránh các phương thức đã lỗi thời hoặc cấu hình `trust` rộng trong production.

### 39.3. Không hardcode password trong migration

```sql
-- Phản ví dụ: không lưu một password thật vào file migration công khai.
-- CREATE ROLE app_login LOGIN PASSWORD 'my-real-secret';
```

Provision credentials qua hệ thống secrets/hạ tầng được phê duyệt. Một số lệnh SQL chứa secret có thể lọt vào history, logs hoặc hệ thống CI.

### 39.4. TLS và kết nối từ xa

Quyền tốt vẫn không bảo vệ credential nếu kết nối bị lộ qua mạng hoặc client/server không được xác thực. Cần TLS/certificate validation và chính sách network phù hợp.

### 39.5. Rotate, revoke và disable login

Nếu secret bị lộ, cần rotate/revoke hoặc khóa account theo quy trình incident. Không chỉ thu hồi một grant trên một table nếu account còn quyền qua nhiều đường khác.

---

## 40. Backup/restore và ownership

Một bản backup không chỉ có dữ liệu, mà còn có thể chứa thông tin owner/grants.

### 40.1. Restore có thể gặp role không tồn tại

Nếu dump chứa ownership của `app_owner` nhưng cluster đích không có role đó, một số bước restore có thể báo lỗi hoặc cần mapping.

### 40.2. Restore bằng superuser cần kiểm soát

Superuser có thể restore nhiều object dễ hơn, nhưng kết quả ownership/permissions có thể không đúng ý định nếu options của công cụ thay đổi. Cần rà soát sau restore.

### 40.3. Tùy chọn không restore owner/grants

Các công cụ như `pg_dump`/`pg_restore` có những lựa chọn liên quan ownership và privileges (ví dụ dạng `--no-owner`, `--no-acl`). Dùng chúng thay đổi contract phân quyền của database đích, phải lập kế hoạch reapply grants/default privileges/owners.

### 40.4. Backup role không nhất thiết cần superuser

Tùy cơ chế logical dump, physical backup, RLS và phạm vi dữ liệu, backup role có thể cần những quyền khác nhau. Thiết kế account riêng, chỉ cấp quyền đủ cho công cụ backup được dùng; không tự tái sử dụng application superuser.

### 40.5. Test restore về quyền, không chỉ rows

Sau restore nên kiểm tra:

- Object owners.
- Schema USAGE/CREATE.
- TABLE/SEQUENCE/FUNCTION privileges.
- RLS bật hay tắt, FORCE RLS.
- SECURITY DEFINER function ownership/search_path.
- Application login có đúng quyền hay không.

---

## 41. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “LOGIN role mới tạo tự đọc mọi table.” | LOGIN chỉ nói khả năng xác thực; còn ACL |
| “NOLOGIN nghĩa là role không có quyền.” | NOLOGIN có thể sở hữu object hoặc là group quyền |
| “Role owner chỉ khác reader ở nhiều GRANT hơn.” | Ownership có quyền ALTER/DROP/GRANT vốn có |
| “GRANT ALL trên table biến role thành owner.” | Không |
| “REVOKE SELECT từ owner làm owner mất quyền sửa table.” | Ownership không bị tước như grant thường |
| “Schema owner tự đọc mọi table trong schema.” | Không mặc nhiên |
| “GRANT USAGE ON SCHEMA đồng nghĩa SELECT mọi table.” | Không |
| “GRANT SELECT(table) không cần schema usage.” | Cần xét cả hai lớp |
| “Column GRANT phủ định table-wide SELECT từ role khác.” | Quyền có thể cộng từ nhiều đường |
| “REVOKE FROM PUBLIC chặn cả grants qua membership.” | Không |
| “PUBLIC là một user cụ thể.” | Pseudo-role biểu diễn mọi roles |
| “Schema public là tất cả data công khai.” | Tên schema không quyết định SELECT |
| “Database CONNECT tự cấp quyền trên table.” | Không |
| “GRANT CREATE ON DATABASE là role CREATEDB.” | Hai quyền khác nhau |
| “Table INSERT tự cấp USAGE mọi sequence.” | Cần xét sequence/identity semantics |
| “Function mới mặc định chỉ owner EXECUTE được.” | PUBLIC thường có EXECUTE theo defaults |
| “App không có UPDATE table chắc chắn read-only.” | SECURITY DEFINER/role membership có thể ghi |
| “SET ROLE luôn không cần quyền.” | Phụ thuộc membership/đặc quyền |
| “INHERIT bảo đảm mọi quyền owner/DDL tự truyền.” | Có quy tắc riêng, PG16+ membership options |
| “CREATEROLE đồng nghĩa SUPERUSER.” | Không |
| “CREATEDB cho đọc mọi database.” | Không |
| “pg_read_all_data tự bypass RLS.” | Không mặc nhiên |
| “BYPASSRLS có thể cấp cho API an toàn.” | Phá ranh giới RLS |
| “Table owner luôn chịu RLS.” | Mặc định owner bypass, trừ FORCE |
| “FORCE RLS hạn chế cả superuser.” | Superuser/BYPASSRLS vẫn đặc biệt |
| “SECURITY DEFINER chỉ tiện vì không cần GRANT SELECT.” | Có nguy cơ privilege escalation |
| “security_invoker và security_barrier giống nhau.” | Mục tiêu khác |
| “View không trả PII nghĩa role không thể đọc bảng nền.” | Nếu còn table grant, vẫn đọc được |
| “CREATE schema public luôn mở cho mọi role.” | Mặc định đổi từ PG15; upgraded DB có thể khác |
| “ALTER DEFAULT PRIVILEGES sửa các bảng đang tồn tại.” | Chỉ đối tượng tạo sau |
| “Default ACL của owner A áp dụng cả object role B tạo.” | Phụ thuộc role creator |
| “GRANT ON ALL TABLES áp dụng tự động cho bảng mới.” | Không |
| “REVOKE theo schema phủ định default global grants.” | Không đơn giản như vậy |
| “Object owner sau restore chắc chắn giống source.” | Restore options/roles ảnh hưởng |
| “DROP OWNED chỉ xóa privileges của role.” | Có thể xóa objects và grants |
| “REASSIGN OWNED là đủ để DROP ROLE trên mọi databases.” | Còn grants/ownership ở phạm vi khác |
| “DROP CASCADE có phạm vi nhỏ.” | Có thể kéo theo dependencies |
| “Mỗi migration chạy bằng ai cũng được.” | Owner và default grants thay đổi |
| “pg_roles nói hết các quyền thực tế.” | Cần ACL/membership/RLS |
| “has_table_privilege SELECT false nghĩa không đọc được cột nào.” | Column-level grants có thể cho đọc một số cột |
| “Tài khoản tên admin luôn là superuser.” | Managed service có thể hạn chế |
| “Xác thực TLS nghĩa không cần GRANT/REVOKE.” | Authentication khác authorization |
| “RLS dựa vào session tenant setting bất kỳ là bảo mật.” | Setting có thể bị caller tự thay |
| “SELECT role thấp luôn an toàn khỏi DoS.” | Query nặng vẫn tốn tài nguyên |
| “Permission denied nên cấp SUPERUSER.” | Nên tìm thiếu quyền tối thiểu |
| “Kiểm thử chỉ quyền thành công là đủ.” | Cần cả negative permission tests |

---

## 42. Bài tập thực hành

### Bài 1 — Owner và SELECT

Tạo một bảng bằng role owner và GRANT SELECT cho reader. Nêu ba hành động owner làm được nhưng reader không làm được.

### Bài 2 — NOLOGIN group

Tạo role `warehouse_read NOLOGIN` và một login role phù hợp, cấp membership, rồi kiểm tra quyền SELECT hiệu lực.

### Bài 3 — Phân biệt session_user/current_user

Truy vấn hai biến trước và sau khi được phép `SET ROLE`. Khi nào chúng khác nhau?

### Bài 4 — SUPERUSER

Nêu ít nhất năm rủi ro nếu HTTP API kết nối bằng superuser. Vì sao không sửa lỗi permission denied bằng cách thêm SUPERUSER?

### Bài 5 — CREATEDB và CREATE DATABASE privilege

So sánh role attribute `CREATEDB` với `GRANT CREATE ON DATABASE`.

### Bài 6 — BYPASSRLS

Một hệ thống bảo vệ dữ liệu tenant bằng RLS. Giải thích chuyện gì xảy ra nếu runtime role được gắn BYPASSRLS.

### Bài 7 — pg_roles

Viết query liệt kê các roles có `rolsuper=true`, `rolbypassrls=true` hoặc `rolcreaterole=true`. Vì sao phải review cả roles không thể LOGIN?

### Bài 8 — CREATEROLE

Giải thích vì sao quyền quản trị role cần tách khỏi quyền CRUD. Nêu thay đổi membership options ở PostgreSQL 16+ cần được lưu ý.

### Bài 9 — PUBLIC

Vì sao GRANT SELECT TO PUBLIC không chỉ cấp cho một role tên PUBLIC? REVOKE từ PUBLIC có loại bỏ một GRANT trực tiếp khác không?

### Bài 10 — Schema USAGE

Tạo schema riêng, grant USAGE cho reader nhưng không grant table SELECT. Reader có thể SELECT bảng không?

### Bài 11 — Schema CREATE

Cấp CREATE trên schema cho một role. Vì sao quyền này cần được xem xét đặc biệt nếu schema nằm trong search_path của SECURITY DEFINER function?

### Bài 12 — Column-level SELECT

Tạo bảng có sku, stock, unit_cost và cấp SELECT chỉ sku/stock. Thử SELECT sku,stock và SELECT unit_cost từ role consumer.

### Bài 13 — SELECT *

Một reader chỉ có quyền trên hai cột; chuyện gì xảy ra với `SELECT *`? Vì sao mapper API nên chọn cột tường minh?

### Bài 14 — UPDATE một cột

Cấp UPDATE(stock) và SELECT(sku,stock), thử conditional UPDATE. Vì sao role không thể UPDATE unit_cost?

### Bài 15 — DELETE/TRUNCATE

So sánh quyền DELETE và TRUNCATE. Một role chỉ cập nhật stock cần hai quyền này không?

### Bài 16 — GRANT ALL

Dùng ngôn ngữ chính xác để giải thích vì sao `GRANT ALL ON TABLE` không cho phép `ALTER TABLE ... DROP COLUMN` như owner.

### Bài 17 — Quyền thừa hưởng

Một login role nhận SELECT từ hai group roles khác nhau, một group có quyền toàn table. Vì sao column-level REVOKE ở group còn lại không đủ hạn chế?

### Bài 18 — GRANT OPTION

Đề xuất tình huống role cần WITH GRANT OPTION. Vì sao không cấp cho user chỉ dùng báo cáo?

### Bài 19 — pg_namespace ownership

Viết truy vấn liệt kê schema owner. Khi schema thuộc owner role A nhưng một table thuộc role B, ai kiểm soát ALTER TABLE theo rule sở hữu?

### Bài 20 — pg_class ownership

Liệt kê relname, relkind và owner của tables/views/sequences trong một schema. Vì sao kiểm tra này cần chạy sau migration?

### Bài 21 — Function owner

Liệt kê functions có `prosecdef=true` cùng function owner và chữ ký. Tại sao danh sách này là đầu vào audit bảo mật?

### Bài 22 — PUBLIC EXECUTE

Tạo một function trong schema lab, xem quyền EXECUTE. Thu hồi EXECUTE từ PUBLIC rồi grant cho role cụ thể trong cùng transaction phù hợp.

### Bài 23 — SECURITY INVOKER

Một function đọc table bằng quyền caller. Caller chỉ có EXECUTE function nhưng thiếu SELECT table: có thể xảy ra lỗi gì?

### Bài 24 — SECURITY DEFINER

Tạo function trả số stock của SKU bằng quyền owner. Vì sao cần kiểm tra rằng caller không thể yêu cầu thêm unit_cost qua một đường không định trước?

### Bài 25 — search_path

Giải thích một kịch bản name shadowing trong SECURITY DEFINER. Vì sao schema-qualified tên table và pg_temp ở vị trí phù hợp quan trọng?

### Bài 26 — SECURITY DEFINER và tenant

Một function SECURITY DEFINER nhận p_tenant_id không xác thực và SELECT toàn bộ orders cho tenant đó. Vì sao có nguy cơ đọc chéo tenant?

### Bài 27 — View owner

Tạo view công bố subset cột. Nếu view owner bypass RLS, caller có thể nhìn dữ liệu khác kỳ vọng thế nào?

### Bài 28 — security_invoker

Tạo view `WITH (security_invoker=true)` trên PostgreSQL 15+. Vì sao caller chỉ có SELECT view có thể gặp permission denied bảng nền?

### Bài 29 — RLS owner bypass

Tạo bảng có RLS SELECT chỉ tenant 10. So sánh kết quả role consumer, table owner và superuser (chỉ trong lab được phép).

### Bài 30 — FORCE RLS

Bật FORCE ROW LEVEL SECURITY và thử lại bằng owner. Nó có làm superuser hoặc BYPASSRLS chịu policy không?

### Bài 31 — current_setting tenant context

Một policy dùng `current_setting('app.tenant_id')` nhưng client tự SET được. Đây có phải tenant authorization đáng tin không? Đề xuất cách quản lý identity/context an toàn hơn.

### Bài 32 — Schema public

Trên một database thử nghiệm, kiểm tra ai có USAGE/CREATE trên schema public. Tại sao database tạo trước PG15 rồi upgrade có thể khác database tạo mới?

### Bài 33 — Database CONNECT

Kiểm tra grants CONNECT trên database riêng, phân biệt với SELECT trên table. Thu hồi CONNECT có ảnh hưởng kết nối mới không?

### Bài 34 — Sequence USAGE

Với column có DEFAULT nextval, grant INSERT table mà không cấp quyền sequence. Quan sát và giải thích lỗi có thể phát sinh.

### Bài 35 — IDENTITY vs sequence

So sánh yêu cầu quyền trên một cột identity với DEFAULT nextval thủ công. Vì sao không suy luận hai cơ chế có quyền giống hệt nhau?

### Bài 36 — ALTER DEFAULT PRIVILEGES

Cấu hình default SELECT cho những bảng reporting do một owner role cụ thể tạo. Một bảng tạo trước đó có tự được cấp quyền mới không?

### Bài 37 — ALL TABLES vs defaults

Viết hai lệnh để áp dụng quyền đọc lên những bảng đang tồn tại và những bảng sẽ được tạo sau. Nếu reporting schema chứa thông tin nhạy cảm, nên cân nhắc gì trước?

### Bài 38 — Creator role drift

Một deployment quên `SET ROLE app_owner` nên table mới do deploy_admin sở hữu. Nêu ba tác động về DDL, default ACL và bảo mật.

### Bài 39 — has_column_privilege

Dùng `has_column_privilege` kiểm tra app_reader có SELECT sku,stock nhưng không có unit_cost. Vì sao `has_table_privilege(...,'SELECT')` riêng lẻ có thể chưa đủ mô tả?

### Bài 40 — Permission negative tests

Thiết kế test suite gồm 5 thao tác phải thành công và 5 thao tác phải trả permission denied, chạy dưới role runtime thật thay vì superuser.

### Bài 41 — Predefined roles

So sánh mục đích pg_monitor, pg_read_all_data và pg_write_all_data. Một job chỉ đọc connection stats có cần pg_read_all_data không?

### Bài 42 — DROP OWNED

Một role sở hữu 30 bảng và được cấp SELECT ở 10 schema. Vì sao `DROP OWNED BY role` là lệnh nguy hiểm nếu chỉ muốn thu hồi một grant?

### Bài 43 — REASSIGN OWNED

Thiết kế kế hoạch nghỉ việc/loại bỏ role cũ với REASSIGN OWNED, dọn grants, kiểm tra nhiều databases và chỉ sau đó mới DROP ROLE.

### Bài 44 — Restore ownership

Một dump được restore với --no-owner/--no-acl. Những quyền và owners nào cần được thiết lập lại trước khi cho API nhận traffic?

### Bài 45 — Runtime vs migration

Một hệ thống chạy Flyway hoặc Liquibase và một HTTP API. Hãy thiết kế hai login credentials, owner NOLOGIN, quyền DDL và DML riêng.

### Bài 46 — Role credential incident

Nếu password của runtime app bị lộ, hãy nêu các bước rotate/disable, thu hồi session theo quy trình, kiểm tra quyền ngoài ý định và audit truy vấn.

### Bài 47 — Read-only có thật sự read-only?

Một role không có UPDATE trên bất kỳ table nào nhưng có EXECUTE function SECURITY DEFINER làm INSERT. Role đó có thể làm thay đổi dữ liệu không? Làm sao phát hiện?

### Bài 48 — Production multi-tenant

Thiết kế mô hình quyền cho 1.000 tenants, ba microservices, báo cáo doanh thu, migration pipeline và một số operator có quyền giám sát. Bao gồm ACL, RLS, owner, security_invoker/definer, role membership và negative permission tests.

---

## 43. Checklist triển khai nguyên tắc quyền tối thiểu

| Câu hỏi | Điều phải xác nhận |
| --- | --- |
| Có xác định asset nhạy cảm? | PII, tài chính, tokens, internal metadata |
| Có phân biệt owner và runtime? | Owner NOLOGIN, runtime không sở hữu schema/table |
| Owner có nhất quán? | Schema/table/view/function/sequence |
| Có bao nhiêu superusers? | Ít, có phê duyệt và audit |
| Runtime có SUPERUSER? | Không |
| Runtime có CREATEROLE/CREATEDB? | Chỉ nếu có yêu cầu thực sự đặc biệt |
| Runtime có REPLICATION/BYPASSRLS? | Không trong ứng dụng thường |
| Có predefined roles quá rộng? | pg_read_all_data/pg_write_all_data/file/program |
| Login roles có credential riêng? | Không dùng chung production/dev |
| Có TLS và auth an toàn? | pg_hba, SCRAM/cert, secrets |
| Có role NOLOGIN nhóm quyền? | Tách chức năng và tài khoản |
| Có membership không cần thiết? | Review role-to-role grants |
| Có khả năng SET ROLE sang owner? | Không cấp cho runtime |
| Có kiểm tra PG16+ membership options? | INHERIT/SET/ADMIN |
| Có quyền CONNECT database? | Cấp theo nhu cầu |
| Có quyền TEMP/CREATE database thừa? | Kiểm tra |
| Có schema USAGE? | Chỉ schema cần truy cập |
| Có CREATE trên schema nhạy cảm? | Không cho untrusted roles |
| Schema public có CREATE cho PUBLIC? | Kiểm tra phiên bản và ACL thật |
| Có table SELECT quá rộng? | Column-level hoặc view hẹp khi phù hợp |
| Có INSERT/UPDATE giới hạn? | Cấp đúng bảng/cột cần |
| Có DELETE/TRUNCATE không cần? | Thu hồi |
| Có REFERENCES/TRIGGER thừa? | Review |
| Có sequence privileges? | Chỉ sequence cần dùng |
| Identity/serial có được phân biệt? | Thử quyền với schema thật |
| Có function EXECUTE PUBLIC nhạy cảm? | REVOKE + GRANT role cụ thể |
| Có SECURITY DEFINER function? | Audit owner, body, search_path, input |
| Có tên đối tượng schema-qualified? | Tránh name shadowing |
| Có dynamic SQL trong function privileged? | Bind/quote đúng, kiểm tra input |
| Có view owner đặc quyền rộng? | Review RLS và quyền bảng nền |
| Có security_invoker đúng? | Quyền caller và RLS phù hợp |
| Có security_barrier khi cần? | Không nhầm với invoker/RLS |
| Có ENABLE RLS trên bảng tenant? | Policy SELECT/INSERT/UPDATE/DELETE đúng |
| Table owner có bypass RLS? | Xem FORCE RLS và owner role |
| Có role BYPASSRLS? | Không làm runtime bypass policy |
| Tenant context có đáng tin? | Không do caller SQL tự giả mạo |
| Có default privileges phù hợp? | Creator role/schema/loại object |
| Có grant rộng từ PUBLIC? | Audit |
| Có grant rộng từ membership khác? | Audit hiệu lực |
| Có GRANT OPTION/ADMIN OPTION thừa? | Thu hồi |
| Có tách reporting schema? | Không lộ PII/secret |
| Có migration chạy đúng owner? | SET ROLE hoặc owner identity chuẩn |
| Có kiểm tra ownership sau deploy? | pg_namespace/pg_class/pg_proc |
| Có test permission helpers? | has_schema/table/column/function_privilege |
| Có negative tests? | SELECT nhạy cảm, UPDATE, ALTER phải lỗi |
| Có test với login/role thật? | Không chỉ superuser |
| Có kiểm soát query resource? | Timeout, pool, monitoring |
| Có kế hoạch revoke credential? | Rotate và incident response |
| Có kế hoạch retire role? | REASSIGN OWNED/DROP OWNED/DROP ROLE đúng scope |
| Có nhiều databases? | Ownership/quyền được audit toàn cluster |
| Có test restore role/grants? | --no-owner/--no-acl ảnh hưởng |
| Có tài liệu role matrix? | Tên role, scope, owner, lý do |
| Có review quyền định kỳ? | Drift detection |
| Có kiểm toán sự kiện nhạy cảm? | Logging/audit theo chính sách |
| Có hạn chế superuser trong CI? | Không chia sẻ quyền cao vào pipeline thường |
| Có quản lý thay đổi ACL như code? | Migration/review/rollback |

## Kết luận

**Chủ sở hữu, superuser và nguyên tắc quyền tối thiểu** là nền tảng để vận hành PostgreSQL an toàn. Ba khái niệm cần được tách bạch:

1. **Owner kiểm soát định nghĩa và vòng đời đối tượng.** Quyền ALTER/DROP/GRANT của owner không tương đương một danh sách SELECT/UPDATE được GRANT. Không để login runtime sở hữu bảng chỉ vì ứng dụng cần đọc/ghi.
2. **Superuser có phạm vi quyền rất lớn.** Không dùng superuser như giải pháp thuận tiện cho permission denied; managed PostgreSQL có thể có admin bị giới hạn.
3. **Least privilege là quyền đúng nhiệm vụ, không chỉ là thiếu SUPERUSER.** Cần xét database, schema, table, column, sequence, function, view, role membership, default privileges và RLS.
4. **NOLOGIN owner + role nhóm quyền + runtime login** là một mô hình hữu ích để tách deploy khỏi hoạt động thường ngày.
5. **PUBLIC, membership và GRANT OPTION tạo đường cấp quyền gián tiếp.** Một REVOKE đơn lẻ không mặc nhiên phủ định những grant khác.
6. **Column-level GRANT và view hẹp có thể giảm bề mặt dữ liệu đọc.** Nhưng phải kiểm tra quyền rộng qua các nguồn khác và các functions chạy theo owner.
7. **RLS có ngoại lệ quan trọng.** Table owner thường bypass RLS mặc định; FORCE RLS có giới hạn, và SUPERUSER/BYPASSRLS vẫn có quyền đặc biệt.
8. **SECURITY DEFINER cần thiết kế phòng thủ.** Chữ ký, search_path, EXECUTE PUBLIC, owner và logic tenant đều có thể tạo đường leo thang quyền.
9. **Default privileges phải gắn với đúng creator role và thời điểm tạo object.** Không nhầm với GRANT trên các bảng đã tồn tại.
10. **Ownership và ACL phải được kiểm thử sau migration/restore.** Dùng catalog, các hàm has_*_privilege và chạy cả negative tests dưới role thật.
11. **Đường dọn role cũng có rủi ro.** REASSIGN OWNED, DROP OWNED và DROP ROLE cần kế hoạch có tính đến nhiều databases và dependencies.
12. **Quyền tối thiểu là một quá trình liên tục.** Cần review, logging, điều phối credentials, giám sát role drift và kiểm thử khi hệ thống phát triển.

Một kiến trúc PostgreSQL tốt không chỉ bảo đảm **ai có thể đăng nhập**, mà còn chứng minh được **ai sở hữu đối tượng, ai có thể thay đổi định nghĩa, ai được đọc từng nhóm dữ liệu, ai có thể ghi qua đường gián tiếp và điều gì vẫn bị từ chối khi một tài khoản bị lộ**.
