# Extension tin cậy, quyền cài đặt và mã chạy phía máy chủ PostgreSQL

PostgreSQL có thể được mở rộng bằng extension, procedural languages, functions, triggers và native modules. Những thành phần này giúp xử lý công việc gần dữ liệu, nhưng cũng tạo ra ranh giới bảo mật quan trọng: **ai được cài extension, installation script chạy với quyền nào, và mã phía máy chủ có thể truy cập những tài nguyên gì**.

Một extension có thể chỉ bổ sung SQL objects, nhưng cũng có thể nạp C code trực tiếp vào backend process. Một procedural language có thể được thiết kế cho user thông thường, hoặc cho phép thực thi mã tùy ý với quyền của hệ điều hành. Vì vậy, không thể coi mọi extension hay mọi ngôn ngữ thủ tục là tương đương nhau.

Bài **“Extension tin cậy, quyền cài đặt và mã chạy phía máy chủ”**, thuộc chương **Mở rộng** của module **Database Engine Relational PostgreSQL**, giải thích:

- Cấu trúc extension: control files, SQL scripts, update scripts và shared libraries.
- Khác biệt giữa extension trusted và untrusted.
- Điều kiện CREATE privilege và yêu cầu superuser.
- Cách thuộc tính trusted ảnh hưởng tới installation scripts và extension ownership.
- Phân biệt cài package ở hệ điều hành với CREATE EXTENSION trong database.
- Procedural languages, C functions, SECURITY DEFINER và server-side code.
- Quyền truy cập file, chương trình và tài nguyên bên ngoài.
- Cách cấp quyền tối thiểu, kiểm tra nguồn gốc extension và audit thay đổi.

> **Nguyên tắc:** quyền cài extension có ảnh hưởng lớn tới bảo mật database. Chỉ cài extension từ nguồn đã được tin cậy, kiểm tra mã và native libraries, hiểu rõ trusted flag, và giới hạn quyền của role thực hiện thao tác.

---

## 1. Extension trong PostgreSQL là gì?

Extension là một gói database objects được quản lý như một đơn vị. Nó có thể cung cấp:

- SQL functions và operators.
- Data types và casts.
- Index access methods hoặc operator classes.
- Views và catalog objects.
- Procedural languages.
- C functions được nạp vào server.
- Background workers hoặc thành phần native khác tùy extension.

Ví dụ extension thường gặp gồm `pg_stat_statements`, `pgcrypto`, `uuid-ossp`, `hstore` và PostGIS.

Không phải mọi extension đều có cùng mức rủi ro. Extension chỉ tạo SQL views khác với extension nạp native C code vào backend.

## 2. CREATE EXTENSION làm gì?

Lệnh `CREATE EXTENSION` cài các objects do extension định nghĩa vào database hiện tại.

~~~sql
CREATE EXTENSION pgcrypto;
~~~

PostgreSQL tìm extension control file, xác định version và installation script, rồi thực thi SQL script để tạo objects.

Kiểm tra extensions đã cài:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Extension được cài ở phạm vi database. Cài extension trong một database không có nghĩa extension tự xuất hiện trong mọi database khác của cluster.

## 3. Extension package gồm những gì?

| Thành phần | Vai trò |
|---|---|
| Control file | Metadata và thuộc tính của extension |
| SQL installation script | Tạo functions, types, operators và objects |
| Update scripts | Chuyển extension giữa các phiên bản SQL |
| Shared library | Native code nếu extension cần |
| Supporting files | Headers, configuration hoặc resources khác |

Trên Linux, package manager thường cài files vào PostgreSQL-specific directories. Trên Windows, installer/package tương ứng cài binaries và SQL files cho đúng PostgreSQL build.

Database role không tự cài native library vào thư mục hệ điều hành. Đây là hai lớp quản trị khác nhau.

## 4. Control file

Control file thường có tên dạng `extension_name.control`.

Ví dụ:

~~~text
comment = 'Example extension'
default_version = '1.0'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
trusted = false
~~~

Các thuộc tính quan trọng:

- `default_version`: phiên bản mặc định.
- `module_pathname`: đường dẫn library được SQL script tham chiếu.
- `relocatable`: extension có thể chuyển schema hay không.
- `schema`: schema mặc định hoặc yêu cầu cài đặt.
- `requires`: các extension phụ thuộc.
- `superuser`: có yêu cầu superuser để cài đặt hay không.
- `trusted`: có cho phép user không phải superuser cài theo cơ chế trusted extension hay không.

Không phải extension nào cũng khai báo mọi thuộc tính. Giá trị mặc định và semantics cần xem theo PostgreSQL version.

## 5. Trusted extension là gì?

Extension được đánh dấu `trusted = true` trong control file có thể được cài bởi user không phải superuser nếu user đó có quyền `CREATE` trên database hiện tại.

Cơ chế này cho phép DBA giao quyền cài một số extension đã được xem xét mà không cần cấp superuser cho người dùng ứng dụng.

Trusted không có nghĩa extension đã được PostgreSQL security team chứng nhận an toàn, không có lỗi hoặc không thể lạm dụng. Đây là thuộc tính do extension author/package maintainer khai báo trong control file.

Vì vậy, DBA vẫn phải đánh giá nguồn gốc và nội dung extension.

## 6. Điều kiện để user cài trusted extension

User không phải superuser có thể cài extension trusted nếu:

1. Extension có control file đặt `trusted = true`.
2. User có quyền `CREATE` trên database hiện tại.
3. Extension package và SQL scripts có sẵn trên server.
4. Dependencies và versions phù hợp.
5. User đáp ứng các quyền cần thiết khác theo extension và objects được tạo.

Ví dụ cấp quyền database:

~~~sql
GRANT CREATE ON DATABASE appdb TO app_extension_admin;
~~~

Sau đó user `app_extension_admin` kết nối tới `appdb` và cài extension trusted được hỗ trợ:

~~~sql
CREATE EXTENSION some_trusted_extension;
~~~

Không cấp quyền này cho mọi application role. Quyền CREATE database cho phép tạo schema và có thể ảnh hưởng namespace; nên dùng role triển khai riêng.

## 7. Trusted không có nghĩa installation script chạy với quyền thường

Một điểm cần hiểu chính xác: với trusted extension, nếu installation script cần các quyền chỉ superuser mới có, PostgreSQL có thể chạy phần script đó với quyền bootstrap superuser theo cơ chế trusted extension.

User gọi `CREATE EXTENSION` vẫn là người yêu cầu cài và trở thành extension owner theo quy tắc PostgreSQL. Nhưng một phần script có thể được thực thi với quyền cao hơn để tạo objects đặc biệt.

Điều này tạo ra yêu cầu bảo mật quan trọng: installation script của trusted extension phải được thiết kế an toàn đối với user không phải superuser có quyền cài nó.

Đừng suy luận rằng script chỉ có thể làm những gì user gọi lệnh có thể làm trực tiếp.

## 8. Untrusted extension

Extension không được đánh dấu trusted thường yêu cầu superuser để cài nếu control file mặc định `superuser = true`.

~~~text
superuser = true
trusted = false
~~~

Role thông thường có quyền CREATE trên database vẫn không đủ. Superuser hoặc quy trình triển khai có đặc quyền phải thực hiện:

~~~sql
CREATE EXTENSION example_extension;
~~~

Một số extension có thể khai báo `superuser = false` nhưng vẫn không được đánh dấu trusted. Hãy xem control file và tài liệu extension thay vì dựa vào tên hoặc giả định.

## 9. Phân biệt superuser và CREATE privilege

| Quyền | Phạm vi | Ý nghĩa |
|---|---|---|
| SUPERUSER | Toàn PostgreSQL instance | Bỏ qua hầu hết kiểm tra quyền |
| CREATE trên database | Một database | Cho phép tạo schema và một số objects |
| CREATE trên schema | Một schema | Cho phép tạo objects trong schema |
| Ownership extension | Một extension | Quản lý một số thao tác ALTER/DROP |
| USAGE trên schema | Một schema | Cho phép truy cập/tra cứu objects theo quyền liên quan |

`CREATE` trên database không tương đương superuser. Tuy nhiên, quyền này vẫn rộng hơn quyền chỉ đọc hoặc chỉ gọi một function.

Cấp quyền theo database và role cụ thể, không dùng `GRANT CREATE ON DATABASE ... TO PUBLIC`.

## 10. Kiểm tra quyền CREATE

Xem role hiện tại:

~~~sql
SELECT
    current_user,
    session_user,
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create_in_database;
~~~

Xem database ACL:

~~~sql
SELECT datname, datacl
FROM pg_database
WHERE datname = current_database();
~~~

Có thể dùng `\l+` trong psql để xem database privileges. Đừng chỉ dựa vào tên role; quyền có thể đến từ membership hoặc PUBLIC.

## 11. Tách role triển khai khỏi application role

Một mô hình thực tế:

- `app_owner`: owner schema/application objects.
- `app_runtime`: role ứng dụng dùng khi chạy.
- `app_extension_admin`: role triển khai extension đã duyệt.
- `db_admin`: DBA có quyền quản trị cao hơn.

Ví dụ:

~~~sql
CREATE ROLE app_runtime LOGIN;
CREATE ROLE app_extension_admin LOGIN;

GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT CONNECT, CREATE ON DATABASE appdb TO app_extension_admin;
~~~

Sau khi cài extension và hoàn tất migration, có thể thu hồi quyền CREATE nếu role không còn cần:

~~~sql
REVOKE CREATE ON DATABASE appdb FROM app_extension_admin;
~~~

Thiết kế cụ thể cần xét schema ownership, migration framework và quy trình triển khai. Không cấp role quản trị extension cho tài khoản được dùng liên tục bởi web application.

## 12. Cài package ở hệ điều hành khác với CREATE EXTENSION

Có hai thao tác riêng:

**Cài package/binaries:** người quản trị OS cài control files, SQL scripts và native libraries vào thư mục PostgreSQL.

**Cài extension trong database:** database role chạy `CREATE EXTENSION` để tạo SQL objects trong database hiện tại.

Ví dụ Debian/Ubuntu, package name tùy PostgreSQL major version và repository:

~~~bash
sudo apt install postgresql-17-pg-stat-statements
~~~

Sau đó kết nối database và chạy:

~~~sql
CREATE EXTENSION pg_stat_statements;
~~~

Tên package chỉ là ví dụ. Kiểm tra repository và package naming của hệ điều hành đang dùng.

Một database superuser không tự động có quyền root để cài OS packages. Ngược lại, OS administrator không tự động có database superuser credentials.

## 13. Vì sao native library cần được cài trước?

Nếu extension cần shared library, control file hoặc SQL scripts mà server không tìm thấy, `CREATE EXTENSION` có thể thất bại.

Ví dụ:

~~~text
ERROR: could not access file "$libdir/example_extension":
No such file or directory
~~~

Lỗi này thường liên quan package/library path, PostgreSQL major version, architecture hoặc dynamic linker dependencies.

Kiểm tra package đúng major version, shared library path, control file, SQL scripts, native dependencies và quyền đọc files của PostgreSQL process.

Không sửa bằng cách copy library tùy tiện từ một server version khác.

## 14. Extension và PostgreSQL major version

Native extensions thường được build cho một PostgreSQL major version cụ thể, vì server APIs/ABI có thể thay đổi.

Khi nâng cấp major version:

- Cài package extension build cho target major version.
- Kiểm tra vendor hỗ trợ target.
- Xác minh library path.
- Kiểm tra extension update scripts.
- Chạy `ALTER EXTENSION ... UPDATE` khi cần.
- Kiểm thử functions và query plans.

Một SQL extension thuần có thể có yêu cầu khác native C extension. Đừng giả định binary của version cũ dùng được trên server mới.

## 15. Kiểm tra extensions có thể cài

View `pg_available_extensions` liệt kê extensions có control files trong server installation và trạng thái cài đặt ở database hiện tại:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

View này không chứng minh mọi native dependencies đã load thành công hoặc extension an toàn. Nó chỉ là một bước inventory.

## 16. Kiểm tra extension versions và dependencies

~~~sql
SELECT
    name,
    version,
    installed
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Một số extensions phụ thuộc extensions khác. Control file có thể khai báo `requires`, nhưng còn có thể tồn tại dependencies ngoài database như OS libraries, services hoặc external data.

Đọc documentation của nhà cung cấp và package metadata trước khi cài.

## 17. Cài extension vào schema cụ thể

Nếu extension relocatable và cho phép schema chỉ định:

~~~sql
CREATE SCHEMA extensions AUTHORIZATION app_owner;

CREATE EXTENSION hstore
WITH SCHEMA extensions;
~~~

Schema cần tồn tại trước, và user thực hiện cần quyền phù hợp. Không phải extension nào cũng relocatable hoặc cho phép chỉ định schema.

Kiểm tra:

~~~sql
SELECT
    extname,
    extrelocatable,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Control file và extension docs quyết định behavior cụ thể.

## 18. Schema và search_path

`search_path` xác định cách PostgreSQL tìm tên objects không schema-qualified.

~~~sql
SHOW search_path;
~~~

Nếu một role có thể tạo objects trong schema xuất hiện trong `search_path` của code đặc quyền, kẻ tấn công có thể tạo object giả để thay đổi cách function resolve tên.

Với security-sensitive code:

- Schema-qualify object references.
- Giữ schema trong search_path có quyền CREATE được kiểm soát.
- Đặt search_path an toàn cho SECURITY DEFINER functions.
- Tránh dùng schema writable bởi untrusted users.

## 19. Trusted extension không đồng nghĩa trusted schema

Hai khái niệm khác nhau:

- **Trusted extension:** control file cho phép user không superuser cài extension theo cơ chế PostgreSQL.
- **Trusted schema:** schema được tin cậy để code đặc quyền tra cứu objects trong đó, thường không cho user không tin cậy quyền CREATE.

Một extension trusted có thể được cài vào schema không phù hợp nếu deployment policy quá lỏng. Một schema an toàn không tự làm extension không đáng tin cậy trở nên an toàn.

## 20. Extension ownership

Extension owner được lưu trong `pg_extension.extowner`.

~~~sql
SELECT
    extname,
    extowner::regrole AS extension_owner,
    extnamespace::regnamespace AS schema_name,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Owner có thể thực hiện các thao tác quản lý extension theo quyền và rules của PostgreSQL. Với trusted extension, user không phải superuser cài đặt thường trở thành owner của extension.

Nên chọn owner là role triển khai ổn định, không phải tài khoản cá nhân hoặc application login dễ bị xóa.

## 21. ALTER EXTENSION và UPDATE

Để nâng extension lên version mới có update path:

~~~sql
ALTER EXTENSION pgcrypto UPDATE;
~~~

Hoặc chỉ định target version:

~~~sql
ALTER EXTENSION example_extension UPDATE TO '2.0';
~~~

Cần có update script tương ứng trên server. Người thực hiện phải có quyền cần thiết; update có thể yêu cầu superuser tùy extension và script.

Kiểm tra version sau cập nhật:

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Đừng nhầm PostgreSQL major upgrade với extension SQL update. Đây là hai quy trình khác nhau.

## 22. DROP EXTENSION và dependencies

~~~sql
DROP EXTENSION example_extension;
~~~

Nếu objects khác phụ thuộc objects của extension, lệnh có thể thất bại. `CASCADE` có thể xóa các dependent objects:

~~~sql
DROP EXTENSION example_extension CASCADE;
~~~

Không dùng CASCADE chỉ để làm lệnh thành công. Inventory dependencies và backup/migration plan trước khi gỡ extension.

## 23. Installation scripts là mã thực thi

Extension SQL scripts có thể tạo functions, cấp grants, tạo operators/types, tạo event triggers, gọi functions đã có, nạp native libraries hoặc thực hiện thao tác catalog/DDL.

Do đó, review installation/update scripts là một phần của security review.

Đặc biệt với trusted extension, cần xem script có sử dụng quyền superuser trong lúc cài hay không và có thể bị ảnh hưởng bởi objects do người cài tạo trước đó không.

Không cài extension chỉ vì nó có mặt trong package repository; xác định vendor, provenance, source và release history.

## 24. Native C extensions

C extension có thể khai báo functions trong SQL và map tới symbols trong shared library.

Ví dụ khái quát:

~~~sql
CREATE FUNCTION example_add(integer, integer)
RETURNS integer
AS '$libdir/example_extension', 'example_add'
LANGUAGE C
STRICT;
~~~

Khi function được gọi, native code chạy trong PostgreSQL backend process.

Rủi ro gồm memory corruption, crash backend/server, buffer overrun, arbitrary code execution trong process context, đọc/ghi tài nguyên OS mà process có quyền và lỗi concurrency/transaction semantics.

C extension phải được xem là code chạy trong trusted computing base của database server.

## 25. Quyền OS của PostgreSQL process

PostgreSQL server thường chạy dưới một OS account riêng, ví dụ `postgres` trên Linux.

Native code được nạp vào backend process thường thừa hưởng quyền OS của process đó. Điều này có nghĩa native extension không tự động chạy với quyền root, nhưng có thể truy cập mọi tài nguyên mà OS account PostgreSQL được phép truy cập.

Vì vậy:

- Không chạy PostgreSQL server bằng root.
- Hạn chế file permissions và service account privileges.
- Không để secrets không cần thiết readable bởi postgres OS user.
- Cô lập network egress khi phù hợp.
- Cập nhật native packages và dependencies.
- Chỉ cài code đã được review.

Database superuser và OS root là hai ranh giới quyền khác nhau, nhưng native code có thể nối hai ranh giới bằng quyền của server process.

## 26. Procedural languages

PostgreSQL hỗ trợ procedural languages để viết functions và procedures phía server.

Ví dụ:

- `plpgsql`: ngôn ngữ mặc định phổ biến, được đánh dấu trusted.
- `plpython3u`: PL/Python untrusted.
- `plperl`: PL/Perl trusted trong cấu hình hỗ trợ.
- `plperlu`: PL/Perl untrusted.
- `pltcl`: PL/Tcl trusted.
- `pltclu`: PL/Tcl untrusted.

Danh sách và packages khả dụng tùy PostgreSQL build/distribution. Kiểm tra catalog và documentation của môi trường.

## 27. Trusted và untrusted procedural languages

Trusted procedural language được thiết kế để user có quyền tạo function trong database sử dụng mà không cần superuser cho mọi thao tác.

Untrusted language cho phép khả năng rộng hơn, thường bao gồm truy cập tài nguyên ngoài database hoặc thực thi mã tùy ý. Việc tạo function bằng untrusted language thường yêu cầu superuser.

Tên language có hậu tố `u` thường biểu thị untrusted trong một số PLs, chẳng hạn `plpython3u` và `plperlu`.

Không dựa vào hậu tố tên một cách tuyệt đối; kiểm tra `pg_language.lanpltrusted` và documentation.

## 28. Xem languages đã cài và trạng thái trust

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;
~~~

`lanpltrusted = true` cho biết language được đánh dấu trusted ở catalog.

Một language trusted vẫn cần được review về implementation và version. Flag này không thay thế security testing.

## 29. PL/pgSQL

PL/pgSQL là procedural language thường được cài mặc định trong database mới.

Ví dụ function:

~~~sql
CREATE OR REPLACE FUNCTION public.order_total(p_order_id bigint)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
    v_total numeric;
BEGIN
    SELECT total_amount
      INTO v_total
      FROM public.orders
     WHERE order_id = p_order_id;

    RETURN v_total;
END;
$$;
~~~

PL/pgSQL phù hợp với logic nghiệp vụ gần dữ liệu, flow control và thao tác SQL. Dù là trusted language, function vẫn chạy với privilege semantics của SECURITY INVOKER hoặc SECURITY DEFINER.

## 30. PL/Python untrusted

PL/Python thường được cung cấp dưới tên `plpython3u`, là untrusted procedural language.

Function có thể thực thi Python code trong backend context và có khả năng truy cập môi trường OS theo quyền của server process, tùy implementation và sandboxing.

Việc cài language và tạo functions cần quyền cao hơn vì code có thể vượt khỏi database object permissions.

Chỉ cài khi có use case rõ, package được tin cậy và threat model chấp nhận. Không cho application users tạo hoặc thay đổi untrusted-language functions.

## 31. SECURITY INVOKER và SECURITY DEFINER

Mặc định, functions chạy theo quyền của user gọi chúng: `SECURITY INVOKER`.

Function `SECURITY DEFINER` chạy với quyền của function owner.

Ví dụ:

~~~sql
CREATE FUNCTION public.get_private_balance(p_account_id bigint)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT balance
    FROM finance.accounts
    WHERE account_id = p_account_id;
$$;
~~~

Nếu owner có quyền đọc bảng, caller có thể dùng function để truy cập dữ liệu theo phạm vi function cho phép.

SECURITY DEFINER hữu ích để cung cấp API quyền hạn hẹp, nhưng sai sót trong function có thể trở thành privilege escalation.

## 32. Bảo vệ SECURITY DEFINER bằng search_path

Function đặc quyền có thể bị tấn công nếu resolve object names từ schema mà user không tin cậy có quyền CREATE.

Ví dụ cách khai báo an toàn hơn:

~~~sql
CREATE FUNCTION admin_api.read_setting(p_name text)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, admin_api, pg_temp
AS $$
BEGIN
    RETURN (
        SELECT setting_value
        FROM admin_api.settings
        WHERE setting_name = p_name
    );
END;
$$;
~~~

Các nguyên tắc:

- Dùng schema-qualify cho sensitive objects.
- Đảm bảo các schemas trước pg_temp không writable bởi untrusted users.
- Đặt search_path tường minh.
- Tránh gọi dynamic SQL không kiểm soát.
- Review function owner và grants.
- Revoke EXECUTE khỏi PUBLIC nếu không cần.

Thứ tự và schema cụ thể phải được thiết kế theo function; không sao chép search_path mẫu mà chưa hiểu object resolution.

## 33. Revoke PUBLIC EXECUTE

Functions mới thường có EXECUTE privilege cho PUBLIC theo mặc định trong nhiều trường hợp. Với function nhạy cảm, thu hồi và cấp rõ:

~~~sql
REVOKE ALL ON FUNCTION admin_api.read_setting(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_api.read_setting(text) TO app_runtime;
~~~

Kiểm tra grants bằng psql hoặc ACL catalog. Không cấp EXECUTE cho application role nếu function không thuộc API của ứng dụng.

## 34. Dynamic SQL và SQL injection phía server

PL/pgSQL có thể xây dựng dynamic SQL bằng `EXECUTE`.

Không nối chuỗi input không tin cậy trực tiếp vào SQL:

~~~sql
-- Nguy hiểm nếu p_name đến từ input không tin cậy:
EXECUTE 'SELECT * FROM users WHERE name = ''' || p_name || '''';
~~~

Dùng parameters cho values:

~~~sql
EXECUTE
    'SELECT count(*) FROM public.users WHERE name = $1'
USING p_name;
~~~

Identifiers không thể bind bằng `$1`; dùng `format('%I', identifier)` để quote identifiers đúng cách và validate allowlist khi có thể.

SQL injection trong SECURITY DEFINER function có thể gây hậu quả nghiêm trọng hơn do function chạy với quyền owner.

## 35. Server-side file access

Một số SQL commands/functions có thể đọc hoặc ghi files trên filesystem của database server.

Ví dụ:

- `COPY ... FROM '/server/path/file.csv'`.
- `COPY ... TO '/server/path/file.csv'`.
- Các large object functions truy cập file server-side.

Các thao tác này khác với `\copy` của psql. `\copy` đọc/ghi file trên máy client, còn SQL `COPY` với filename truy cập filesystem của server.

Không cấp quyền file access chỉ để thuận tiện cho import/export. Ưu tiên client-side transfer hoặc controlled staging locations.

## 36. Predefined roles cho server file access

PostgreSQL cung cấp các predefined roles có quyền đặc biệt, tùy version:

- `pg_read_server_files`: đọc file trên server mà PostgreSQL process có thể truy cập.
- `pg_write_server_files`: ghi file trên server mà PostgreSQL process có thể truy cập.
- `pg_execute_server_program`: thực thi chương trình trên server thông qua các tính năng được bảo vệ.

Ví dụ:

~~~sql
GRANT pg_read_server_files TO controlled_import_role;
~~~

Đây là quyền rộng và có thể làm lộ configuration, data files hoặc secrets mà OS account có thể đọc. Chỉ cấp cho operator đáng tin cậy và trong phạm vi có kiểm soát.

## 37. COPY PROGRAM và thực thi chương trình

`COPY ... PROGRAM` có thể chạy shell command phía server trên các hệ thống hỗ trợ.

Ví dụ dạng cú pháp:

~~~sql
COPY (
    SELECT order_id, total_amount
    FROM public.orders
) TO PROGRAM 'some_command';
~~~

Khả năng này rất nhạy cảm vì command chạy trên host database với OS privileges của PostgreSQL process.

Quyền thường được kiểm soát bởi superuser hoặc role `pg_execute_server_program`. Không cấp role này cho application accounts hoặc user không tin cậy.

Không xây dựng command bằng cách nối trực tiếp user input. Nếu cần export, ưu tiên client-side tools hoặc service chuyên dụng.

## 38. Server-side code và network access

Một số extensions hoặc procedural languages có thể mở network connections, gọi external services hoặc đọc files.

Khả năng này phụ thuộc language/runtime, native library, OS permissions, network policy và container/VM isolation.

Không giả định database function bị giới hạn trong database. Native code hoặc untrusted language có thể tác động tới host trong phạm vi process privileges.

Thiết kế egress firewall và service identity phù hợp cho database hosts.

## 39. Event triggers

Event triggers là trigger ở mức database DDL, có thể chạy function khi một số DDL events xảy ra.

~~~sql
CREATE EVENT TRIGGER audit_ddl
ON ddl_command_end
EXECUTE FUNCTION audit.capture_ddl();
~~~

Event trigger có thể quan sát hoặc phản ứng với DDL. Function phía sau phải được bảo vệ vì nó chạy trong quá trình command xử lý và có thể làm thay đổi behavior hoặc ghi audit data.

Không cho role không tin cậy tạo event triggers có ảnh hưởng toàn database. Kiểm tra owner, function security và quyền DDL.

## 40. Background workers

Một số extensions đăng ký background workers chạy trong PostgreSQL server process lifecycle.

Background workers có thể poll queue/table, thực hiện maintenance, gửi metrics, chạy replication/coordination tasks hoặc tạo connections nội bộ.

Cần review worker lifecycle, restart behavior, shared memory, signal handling, error handling và logging.

Một worker chạy trong database server không phải service sandbox độc lập. Lỗi native code có thể ảnh hưởng server stability.

## 41. Extension có thể thay đổi quyền như thế nào?

Installation script có thể tạo objects và cấp privileges. Sau cài đặt cần kiểm tra:

- Extension owner.
- Object owners.
- Function EXECUTE grants.
- Schema CREATE/USAGE.
- Default privileges.
- SECURITY DEFINER functions.
- Event triggers.
- Native libraries.
- Role memberships được yêu cầu.

Không giả định extension chỉ tạo một namespace cô lập. Đọc installation scripts và catalog changes theo mức rủi ro.

## 42. Review extension trước khi cài

Checklist review:

1. Nguồn package/repository là gì?
2. Maintainer và release history có đáng tin?
3. Source code có công khai và được review?
4. Extension có native C code không?
5. Extension có procedural language dependencies?
6. Có SECURITY DEFINER functions không?
7. Installation scripts có tạo roles/grants không?
8. Có đọc/ghi file hoặc network không?
9. Có background workers không?
10. Có hỗ trợ PostgreSQL target version?
11. Có CVEs hoặc security advisories?
12. Có cách update/rollback?
13. Có thể thử trên staging không?

Không cài extension production chỉ dựa vào một bài blog hoặc tên package.

## 43. Nguồn gốc và supply chain

Extension có thể đến từ PostgreSQL distribution, OS vendor, cloud provider, extension author hoặc repository bên thứ ba.

Kiểm soát supply chain:

- Dùng repository đã được tổ chức phê duyệt.
- Xác minh package signature/checksum theo quy trình OS.
- Pin versions khi cần.
- Theo dõi security advisories.
- Review source/release notes.
- Giới hạn ai có thể cài package lên database host.
- Không tải shared library tùy tiện từ Internet vào `$libdir`.

Cài extension là thay đổi code trên server, không chỉ là thay đổi schema.

## 44. Least privilege cho extension deployment

Mô hình quyền nên có:

- DBA/superuser chịu trách nhiệm cài extensions cần đặc quyền.
- Deployment role chỉ có CREATE database khi cần cài trusted extensions đã duyệt.
- Application role chỉ có CONNECT và quyền sử dụng objects cần thiết.
- Runtime role không có quyền cài/gỡ extension.
- OS package installation do system administrator hoặc automation có kiểm soát.

Thu hồi quyền tạm thời sau deployment nếu không còn nhu cầu.

## 45. Audit extension changes

Inventory extensions:

~~~sql
SELECT
    current_database() AS database_name,
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Kiểm tra languages:

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;
~~~

Kết hợp database logs, DDL audit, change records và package management logs để biết ai cài gì, lúc nào, từ package version nào.

`pg_extension` chỉ cho biết trạng thái hiện tại; nó không phải lịch sử audit đầy đủ.

## 46. Phân biệt extension trusted với SQL function an toàn

Một extension có `trusted = true` không làm mọi function bên trong trở nên an toàn cho mọi user.

Một function có thể trả dữ liệu nhạy cảm, gọi function khác có quyền cao, dùng SECURITY DEFINER, nhận input dynamic SQL, thay đổi objects hoặc gây resource exhaustion.

Đánh giá từng API/function theo quyền và data access. Extension trust chỉ giải quyết một phần điều kiện cài đặt.

## 47. Quyền CREATE trong database và schema

`CREATE ON DATABASE` cho phép tạo schema và objects thuộc phạm vi database theo privilege model. `CREATE ON SCHEMA` cho phép tạo objects trong schema.

Ví dụ:

~~~sql
GRANT CREATE ON SCHEMA extensions TO app_extension_admin;
~~~

Quyền schema không thay thế điều kiện CREATE trên database đối với trusted extension installation. Kiểm tra privilege requirements của lệnh cụ thể và extension.

Sau khi cài, có thể revoke CREATE trên schema để hạn chế việc tạo objects tùy ý.

## 48. SECURITY DEFINER và extension APIs

Một extension có thể cài SECURITY DEFINER functions để cung cấp API với quyền owner.

Khi sử dụng:

- Xác minh owner của function.
- Xem definition.
- Kiểm tra `prosecdef`.
- Kiểm tra `proconfig` và search_path.
- Kiểm tra PUBLIC EXECUTE.
- Xác định data objects được truy cập.
- Kiểm thử với role ứng dụng có ít quyền nhất.

Ví dụ inventory:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.proowner::regrole AS owner,
    p.prosecdef AS security_definer,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
~~~

Đây là điểm bắt đầu để review, không thay thế source review hoặc security testing.

## 49. Untrusted language và superuser boundary

Superuser có thể cài untrusted procedural language và tạo functions sử dụng language đó. Những functions có thể thực thi code trong backend process.

Rủi ro gồm đọc file server, gọi network, chạy subprocess hoặc truy cập tài nguyên OS khác theo quyền process, tùy language/runtime.

Chỉ DBA tin cậy mới nên cài hoặc tạo untrusted-language functions. Không cho user application quyền CREATE trên schema chứa code đặc quyền hoặc quyền tạo language.

## 50. Resource exhaustion

Server-side code có thể tiêu thụ CPU, memory, backend slots, locks, temporary disk, shared memory và I/O.

Một function loop vô hạn hoặc query nặng có thể làm database chậm hoặc hết tài nguyên.

Áp dụng:

- `statement_timeout`.
- `lock_timeout`.
- `idle_in_transaction_session_timeout` khi phù hợp.
- Resource governance ở tầng OS/container.
- Workload isolation.
- Monitoring và cancellation policy.

Timeout của SQL không phải sandbox hoàn chỉnh cho native code hoặc external process.

## 51. Extension trong managed PostgreSQL

Các managed database services có thể giới hạn extensions theo allowlist hoặc phiên bản được nhà cung cấp hỗ trợ.

Một số extension cần superuser, shared preload, OS packages hoặc background workers mà customer không thể tự cài.

Trước khi thiết kế phụ thuộc extension:

- Kiểm tra allowlist của provider.
- Kiểm tra supported versions.
- Kiểm tra parameter group/flags.
- Kiểm tra quyền tạo extension.
- Xác định ai cài native packages.
- Kiểm tra backup/restore và upgrade support.

Không giả định mọi extension có trong PostgreSQL upstream đều được hỗ trợ trên managed service.

## 52. Extension trong container và Kubernetes

Trong containerized PostgreSQL:

- Image phải chứa extension packages phù hợp.
- Native libraries phải khớp PostgreSQL major version và architecture.
- Persistent volume chỉ chứa data; không tự mang theo package files của image.
- Upgrade image phải kiểm tra extension binaries.
- Init scripts cần idempotent và không cấp superuser cho application.
- Security context cần hạn chế OS privileges.

Nếu dùng operator, quản lý package và shared_preload_libraries theo cơ chế được operator hỗ trợ. Không cài package thủ công vào ephemeral container rồi giả định nó tồn tại sau restart.

## 53. Quy trình cài extension có kiểm soát

Một workflow an toàn:

1. Yêu cầu use case và owner.
2. Review extension source, package và security notes.
3. Xác minh PostgreSQL version/OS compatibility.
4. Cài package lên staging.
5. Review control file và SQL scripts.
6. Chạy pg_available_extensions.
7. Kiểm tra trusted/superuser flags từ package source.
8. Chọn deployment role.
9. Chạy CREATE EXTENSION trong database thử nghiệm.
10. Review owner, schema, grants và functions.
11. Test application behavior.
12. Promote package/config/database change qua change process.
13. Audit kết quả và lên kế hoạch update.

## 54. Ví dụ: cài một extension trusted

Giả sử package đã được cài bởi OS administrator và extension được vendor xác nhận `trusted = true`.

DBA cấp quyền tạm thời:

~~~sql
GRANT CONNECT, CREATE ON DATABASE appdb TO app_extension_admin;
~~~

Role triển khai kết nối `appdb`:

~~~sql
CREATE EXTENSION approved_trusted_extension;
~~~

Kiểm tra:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole,
    extnamespace::regnamespace
FROM pg_extension
WHERE extname = 'approved_trusted_extension';
~~~

Sau khi hoàn tất, thu hồi quyền không còn cần:

~~~sql
REVOKE CREATE ON DATABASE appdb FROM app_extension_admin;
~~~

Việc extension có trusted flag không thay thế bước review package và installation script.

## 55. Ví dụ: extension cần superuser

Nếu extension không trusted và yêu cầu superuser, application migration role không thể tự cài chỉ bằng CREATE privilege trên database.

DBA hoặc privileged deployment pipeline thực hiện:

~~~sql
CREATE EXTENSION approved_native_extension;
~~~

Sau đó cấp quyền sử dụng objects cần thiết cho runtime role:

~~~sql
GRANT USAGE ON SCHEMA extension_api TO app_runtime;
GRANT EXECUTE ON FUNCTION extension_api.calculate_value(integer)
TO app_runtime;
~~~

Tên schema/function là minh họa; lấy đúng objects từ extension docs và catalog.

Không cấp superuser cho ứng dụng chỉ để chạy migration cài extension.

## 56. Kiểm tra function security sau cài

~~~sql
SELECT
    n.nspname,
    p.proname,
    p.proowner::regrole,
    p.prosecdef,
    p.prolang,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
ORDER BY n.nspname, p.proname;
~~~

Trong thực tế có thể lọc schema extension. Xem function definitions bằng `pg_get_functiondef()` khi có quyền phù hợp và review functions có SECURITY DEFINER hoặc native language.

## 57. Checklist bảo mật

**Trước khi cài**

- Nguồn package được phê duyệt.
- Version tương thích.
- Control file đã review.
- trusted và superuser flags đã hiểu.
- Native libraries được xác minh.
- Installation scripts đã review.
- Dependencies và update path rõ.

**Quyền**

- Application role không có superuser.
- Không cấp CREATE database cho PUBLIC.
- Trusted extension deployment dùng role riêng.
- Untrusted extension do DBA kiểm soát.
- OS package install tách khỏi database deployment.
- Server file/program roles không cấp tùy tiện.

**Sau khi cài**

- Owner và schema đúng.
- Function grants đúng.
- SECURITY DEFINER/search_path an toàn.
- Languages và event triggers được kiểm tra.
- Monitoring/audit có evidence.
- Update/rollback procedure được ghi nhận.

## 58. Bài tập thực hành

### Bài 1 — Extension

Extension là gì?

**Gợi ý:** gói database objects được PostgreSQL quản lý như một đơn vị.

### Bài 2 — CREATE EXTENSION

Lệnh này tạo gì?

**Gợi ý:** cài các objects được định nghĩa bởi extension trong database hiện tại.

### Bài 3 — Control file

File control có vai trò gì?

**Gợi ý:** metadata, version và installation properties.

### Bài 4 — trusted

`trusted = true` có nghĩa gì?

**Gợi ý:** user có CREATE privilege trên database có thể cài extension theo cơ chế trusted.

### Bài 5 — Superuser

Extension untrusted thường yêu cầu quyền gì?

**Gợi ý:** superuser nếu control file yêu cầu.

### Bài 6 — CREATE privilege

Quyền CREATE database có giống superuser không?

**Gợi ý:** không.

### Bài 7 — Script execution

Vì sao trusted extension installation scripts cần review kỹ?

**Gợi ý:** một phần script có thể chạy với bootstrap superuser khi cần quyền đặc biệt.

### Bài 8 — Extension ownership

Catalog nào lưu extension owner?

**Gợi ý:** pg_extension.

### Bài 9 — OS package

Ai thường cài native extension packages?

**Gợi ý:** OS administrator hoặc deployment automation có kiểm soát.

### Bài 10 — Library version

Vì sao C extension cần đúng PostgreSQL major version?

**Gợi ý:** native API/ABI compatibility.

### Bài 11 — Available extensions

View nào liệt kê extension có thể cài?

**Gợi ý:** pg_available_extensions.

### Bài 12 — Extension versions

View nào liệt kê các extension versions khả dụng?

**Gợi ý:** pg_available_extension_versions.

### Bài 13 — Schema

Có phải extension nào cũng relocatable?

**Gợi ý:** không; kiểm tra extrelocatable/control file.

### Bài 14 — trusted schema

Trusted extension và trusted schema có giống nhau không?

**Gợi ý:** không, là hai khái niệm riêng.

### Bài 15 — ALTER EXTENSION

Lệnh nào cập nhật extension?

**Gợi ý:** ALTER EXTENSION ... UPDATE.

### Bài 16 — DROP CASCADE

Vì sao cần thận trọng với CASCADE?

**Gợi ý:** có thể xóa dependent objects.

### Bài 17 — Native C

C extension chạy ở đâu?

**Gợi ý:** trong PostgreSQL backend process.

### Bài 18 — OS privilege

Native code thừa hưởng quyền nào?

**Gợi ý:** quyền của OS process chạy PostgreSQL.

### Bài 19 — PL/pgSQL

Language này có trạng thái trust nào phổ biến?

**Gợi ý:** trusted.

### Bài 20 — PL/Python

plpython3u là trusted hay untrusted?

**Gợi ý:** untrusted.

### Bài 21 — pg_language

Column nào cho biết language trusted?

**Gợi ý:** lanpltrusted.

### Bài 22 — SECURITY INVOKER

Function mặc định chạy với quyền của ai?

**Gợi ý:** caller.

### Bài 23 — SECURITY DEFINER

Function chạy với quyền của ai?

**Gợi ý:** function owner.

### Bài 24 — search_path

Vì sao SECURITY DEFINER cần search_path an toàn?

**Gợi ý:** tránh object substitution từ schema writable bởi untrusted users.

### Bài 25 — PUBLIC EXECUTE

Vì sao cần revoke PUBLIC EXECUTE trên API nhạy cảm?

**Gợi ý:** giới hạn ai có thể gọi function.

### Bài 26 — Dynamic SQL

Cách bind input values an toàn trong PL/pgSQL?

**Gợi ý:** EXECUTE ... USING.

### Bài 27 — COPY

SQL COPY với filename truy cập file ở đâu?

**Gợi ý:** filesystem của server.

### Bài 28 — psql \copy

\copy truy cập file ở đâu?

**Gợi ý:** máy client chạy psql.

### Bài 29 — pg_read_server_files

Role này cấp quyền gì?

**Gợi ý:** đọc các server files mà PostgreSQL process có thể truy cập.

### Bài 30 — pg_execute_server_program

Role này nhạy cảm vì sao?

**Gợi ý:** cho phép thực thi chương trình trên server qua các tính năng được bảo vệ.

### Bài 31 — Event trigger

Event trigger phản ứng với nhóm sự kiện nào?

**Gợi ý:** DDL events.

### Bài 32 — Background worker

Background worker chạy trong ranh giới nào?

**Gợi ý:** PostgreSQL server process lifecycle.

### Bài 33 — Managed database

Vì sao không phải extension nào cũng cài được trên cloud managed service?

**Gợi ý:** provider giới hạn packages, privileges, preload và native code.

### Bài 34 — Container

Vì sao extension package cần có trong image?

**Gợi ý:** data volume không tự chứa binaries/control files.

### Bài 35 — Least privilege

Application runtime có cần superuser để dùng extension không?

**Gợi ý:** thường không; chỉ cấp quyền trên schema/functions cần thiết.

### Bài 36 — Audit

pg_extension có phải lịch sử ai cài extension không?

**Gợi ý:** không, nó thể hiện trạng thái hiện tại.

### Bài 37 — Supply chain

Nêu hai biện pháp kiểm soát package.

**Gợi ý:** repository được duyệt, signature/checksum, pin version, review source.

### Bài 38 — Resource exhaustion

Server-side function có thể ảnh hưởng tài nguyên nào?

**Gợi ý:** CPU, memory, locks, temp disk, I/O và backend slots.

### Bài 39 — Untrusted language

Ai nên được phép tạo functions bằng untrusted language?

**Gợi ý:** DBA/administrator đáng tin cậy.

### Bài 40 — Deployment workflow

Nêu các bước chính trước và sau CREATE EXTENSION.

**Gợi ý:** review package/control/scripts, test staging, cài với role phù hợp, audit owner/grants và kiểm thử ứng dụng.

## 59. Câu hỏi thường gặp

### Trusted extension có được PostgreSQL bảo đảm an toàn không?

Không. trusted là thuộc tính trong control file để điều khiển quyền cài đặt. Nó không phải chứng nhận security hoặc thay thế code review.

### User không phải superuser có thể cài extension nào?

Các extension được đánh dấu trusted và khi user có CREATE privilege trên database, cùng các điều kiện cần thiết khác.

### Tại sao script trusted extension có thể chạy với bootstrap superuser?

Để thực hiện các thao tác cài đặt cần quyền cao mà user thường không có. Vì vậy installation script phải an toàn trước user có quyền yêu cầu cài extension.

### CREATE trên database có cấp quyền đọc mọi bảng không?

Không. Quyền này cho phép tạo objects trong database; quyền đọc bảng vẫn được kiểm soát riêng bằng ownership và grants.

### Cài extension có cần quyền OS root không?

Không đối với CREATE EXTENSION trong database. Nhưng cài package/native library lên server thường cần quyền OS administrator hoặc automation tương đương.

### Superuser có thể tự cài mọi native library không?

Không. Superuser trong PostgreSQL không tự có quyền ghi vào filesystem hoặc cài OS package. Cần package đã có trên server.

### Native C extension có thể làm sập PostgreSQL không?

Có. Native code chạy trong backend process và lỗi memory/segmentation có thể làm backend hoặc server gặp sự cố.

### SECURITY DEFINER có phải untrusted language không?

Không. Đây là cơ chế function chạy với quyền owner; trusted/untrusted là thuộc tính của procedural language. Hai khái niệm độc lập nhưng có thể kết hợp tạo rủi ro.

### Vì sao search_path có thể là lỗ hổng?

Nếu code đặc quyền resolve object từ schema mà attacker có CREATE, attacker có thể tạo object giả để thay đổi code path hoặc truy cập dữ liệu.

### Có nên cho application role quyền CREATE EXTENSION?

Thông thường không. Tách deployment role và runtime role, chỉ cấp quyền khi cần cho extension trusted đã duyệt.

### pg_read_server_files có thể cấp cho analyst không?

Chỉ khi có use case được duyệt và hiểu phạm vi. Role có thể đọc nhiều files mà OS account PostgreSQL truy cập được, không chỉ một CSV cụ thể.

### \copy và COPY khác nhau thế nào?

\copy là meta-command của psql và xử lý file trên client. SQL COPY với filename hoặc PROGRAM thực hiện truy cập phía server.

### Cài extension trong một database có làm nó xuất hiện ở database khác không?

Không. Cài extension là thao tác theo từng database, dù package/control files có sẵn ở cấp server.

### Có cần ALTER EXTENSION UPDATE sau pg_upgrade không?

Tùy extension và update path. Major server upgrade không tự bảo đảm SQL objects của extension đã ở version mới nhất. Kiểm tra vendor docs và catalog.

### pg_extension có ghi lại lịch sử update không?

Không. Nó thể hiện version hiện tại và owner. Dùng logs/audit/change management để giữ lịch sử.

## 60. Tổng kết

Các truy vấn kiểm tra quan trọng:

~~~sql
-- Extensions đã cài trong database hiện tại.
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;

-- Extensions có thể cài từ files trên server.
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;

-- Extension versions khả dụng.
SELECT
    name,
    version,
    installed
FROM pg_available_extension_versions
ORDER BY name, version;

-- Procedural languages và trusted flag.
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;

-- Role hiện tại có CREATE privilege trên database?
SELECT
    current_user,
    current_database(),
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create;

-- SECURITY DEFINER functions.
SELECT
    n.nspname,
    p.proname,
    p.proowner::regrole AS owner,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
~~~

Những nguyên tắc cần nhớ:

1. Extension là gói database objects được quản lý như một đơn vị.
2. Control file khai báo version, dependencies, relocatable, superuser và trusted flags.
3. Trusted extension có thể được user không phải superuser cài khi user có CREATE privilege trên database.
4. Trusted không phải chứng nhận an toàn; installation scripts vẫn cần review.
5. Một phần script trusted có thể chạy với bootstrap superuser khi cần quyền đặc biệt.
6. Extension owner là người cài theo quy tắc PostgreSQL; kiểm tra trong pg_extension.
7. Untrusted extension thường yêu cầu superuser khi control file đặt superuser = true.
8. CREATE privilege trên database không tương đương superuser.
9. OS package installation và CREATE EXTENSION là hai thao tác khác nhau.
10. Native library phải tương thích PostgreSQL major version, architecture và runtime dependencies.
11. pg_available_extensions liệt kê extension packages mà server có thể nhìn thấy, không chứng minh chúng an toàn.
12. Extension có thể tạo SQL objects, SECURITY DEFINER functions, event triggers và background workers.
13. C extension chạy trong PostgreSQL backend và thừa hưởng OS privileges của process.
14. Trusted/untrusted procedural languages có quyền và threat model khác nhau.
15. SECURITY DEFINER chạy với quyền owner; cần search_path an toàn và grants tối thiểu.
16. Dùng parameter binding cho dynamic SQL values và quote identifiers đúng cách.
17. SQL COPY với server filename/PROGRAM khác psql \copy và có rủi ro server-side.
18. Các predefined roles đọc/ghi file hoặc chạy chương trình có quyền rộng.
19. Không cấp superuser hoặc server-file roles cho application runtime.
20. Kiểm soát package provenance, update, audit và compatibility.
21. Managed PostgreSQL và container images có thể giới hạn extensions.
22. Chỉ cấp quyền sử dụng function/schema cần thiết sau khi DBA cài extension.
23. Kiểm tra owner, schema, grants và extension version sau deployment.
24. Tách quyền OS administrator, database superuser, extension deployment và application runtime.

Sơ đồ quyền cài đặt:

~~~text
OS administrator / package automation
                |
                v
    Install control files, SQL scripts,
        shared libraries and dependencies
                |
                v
          PostgreSQL server
                |
                v
         CREATE EXTENSION request
                |
                v
       Read extension control file
                |
          +-----+------+
          |            |
          v            v
      trusted=true   untrusted/default
          |            |
          v            v
 CREATE privilege?   Superuser required?
      |                   |
   +--+--+             +--+--+
   |     |             |     |
  Yes    No           Yes    No
   |     |             |     |
   v     v             v     v
Install  Denied       Install Denied
   |
   v
SQL installation scripts
   |
   v
Extension objects + owner/grants
   |
   v
Review functions, languages,
native code and server privileges
   |
   v
Grant least privilege to runtime role
~~~

**Kết luận:** PostgreSQL cho phép mở rộng database rất linh hoạt, nhưng extension và server-side code nằm trong vùng tin cậy của hệ thống. Cần phân biệt rõ trusted flag với chứng nhận an toàn, database CREATE privilege với superuser, cài package ở OS với cài extension trong database, và SQL function với native/untrusted code. Quy trình an toàn bắt đầu từ package provenance và review scripts, tiếp tục bằng role triển khai có quyền tối thiểu, rồi xác minh owner, grants, search_path, native libraries và quyền runtime sau khi cài.
