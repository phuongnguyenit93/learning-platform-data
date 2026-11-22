# Quản lý extension và quyền cài đặt trong PostgreSQL

PostgreSQL extensions là cơ chế đóng gói các tính năng bổ sung vào database. Một extension có thể tạo functions, operators, data types, casts, indexes, views, tables, configuration parameters hoặc các đối tượng khác để mở rộng khả năng của PostgreSQL. Các ví dụ phổ biến gồm PostGIS cho dữ liệu không gian, pg_stat_statements cho thống kê câu lệnh, pgcrypto cho một số hàm mật mã và uuid-ossp cho UUID.

Quản lý extension cần hiểu cả hai phần: **các file được cài trên máy chủ PostgreSQL** và **các đối tượng extension được tạo bên trong từng database**. Lệnh CREATE EXTENSION chỉ hoạt động khi server đã có control file và các installation scripts tương ứng. Nếu extension có C functions, shared library phù hợp cũng phải có mặt trên server. Những file này không được cài chỉ bằng SQL.

Quyền cài đặt cũng cần được kiểm soát. Theo mặc định, nhiều extensions yêu cầu superuser. Một số extension được tác giả đánh dấu trusted có thể cho phép user có quyền CREATE trên database cài đặt theo cơ chế trusted extension của PostgreSQL. Quyền tạo extension, quyền sở hữu extension, quyền sử dụng các objects sau khi cài và quyền quản lý package trên hệ điều hành là các quyền khác nhau.

Bài học này giải thích cấu trúc extension, cách kiểm tra extension có sẵn, cài đặt và cập nhật, quản lý schema/owner/dependencies, phân quyền an toàn, xử lý backup/restore và HA, cùng các rủi ro khi cài extension từ nguồn không đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích extension là gì và vì sao PostgreSQL dùng extension thay vì chỉ cài các objects rời rạc.
2. Phân biệt package/binary trên server với extension đã được cài trong một database.
3. Kiểm tra extensions có sẵn bằng pg_available_extensions.
4. Xem phiên bản và trạng thái cài đặt bằng pg_available_extension_versions và pg_extension.
5. Hiểu control files, installation scripts, update scripts và shared libraries.
6. Cài extension bằng CREATE EXTENSION và lựa chọn schema/version phù hợp.
7. Hiểu trusted extensions, superuser requirement và database CREATE privilege.
8. Quản lý extension owner, object ownership và grants.
9. Theo dõi dependencies và extension membership.
10. Cập nhật extension bằng ALTER EXTENSION UPDATE.
11. Xử lý extension không relocatable, thiếu update path hoặc thiếu server package.
12. Gỡ extension an toàn và đánh giá tác động của RESTRICT/CASCADE.
13. Quản lý extension trong backup, restore, replication, failover và major-version upgrade.
14. Áp dụng least privilege và quy trình supply-chain security.
15. Xây dựng inventory, change control, monitoring và 80 bài tập thực hành.

## 2. Extension là gì?

Extension là một tập hợp các đối tượng database được PostgreSQL quản lý như một đơn vị. Thay vì cài từng function, type, operator hoặc table bằng các câu lệnh độc lập, người dùng cài một extension có version và metadata.

Ví dụ, PostGIS cung cấp nhiều types và functions để lưu trữ, truy vấn và xử lý dữ liệu không gian. pg_stat_statements cung cấp view thống kê query và các functions liên quan. Các đối tượng do extension tạo được liên kết với extension trong system catalogs.

### 2.1. Lợi ích

- Gom nhiều objects thành một đơn vị cài đặt.
- Theo dõi extension version.
- Quản lý dependencies giữa extensions.
- Hỗ trợ update bằng các migration scripts.
- Giúp pg_dump/pg_restore nhận diện objects thuộc extension.
- Cho phép DBA kiểm tra owner, schema và trạng thái cài đặt.
- Giảm nguy cơ quản lý thủ công một tập objects không nhất quán.

### 2.2. Extension không phải database-wide toggle

Extension được cài trong một database cụ thể. Một cluster có nhiều databases; nếu một extension cần thiết trong ba databases, thường phải chạy CREATE EXTENSION trong từng database đó.

### 2.3. Extension không nhất thiết chỉ là SQL

Một extension có thể chỉ chứa SQL objects, nhưng cũng có thể phụ thuộc vào shared library viết bằng C hoặc ngôn ngữ khác. Một số extensions còn cần background workers, preload configuration hoặc các thành phần ngoài PostgreSQL.

### 2.4. Extension không phải package của hệ điều hành

Package manager cài các file server-side vào đúng thư mục PostgreSQL. CREATE EXTENSION đăng ký và tạo các objects trong database. Hai bước này có quan hệ nhưng không thay thế nhau.

## 3. Hai lớp cài đặt cần phân biệt

~~~text
Operating system / PostgreSQL distribution
    |
    +-- Extension control file
    +-- Installation SQL scripts
    +-- Update SQL scripts
    +-- Shared library (.so / .dll)
    |
    v
PostgreSQL server can discover extension
    |
    v
Connect to a database
    |
    +-- CREATE EXTENSION
    |
    v
System catalogs record extension
    |
    +-- SQL functions/types/operators/tables
    +-- Dependencies and ownership
    +-- Installed extension version
~~~

### 3.1. Server-side files

Các files thường nằm trong PostgreSQL installation directories, ví dụ extension control files, SQL scripts và thư viện động. Đường dẫn cụ thể phụ thuộc OS, package, PostgreSQL major version, build và container image.

### 3.2. Database-side objects

Sau khi chạy CREATE EXTENSION, PostgreSQL tạo objects từ installation script và ghi nhận extension trong catalog pg_extension.

### 3.3. Vì sao CREATE EXTENSION có thể thất bại?

Một số nguyên nhân:
- Extension package chưa được cài trên server.
- Extension không được build cho PostgreSQL major version hiện tại.
- Thiếu shared library dependency.
- Không có installation script cho version mong muốn.
- User không có quyền cần thiết.
- Extension phụ thuộc vào extension khác chưa được cài.
- Managed service không cho phép extension đó.
- Cấu hình preload/restart requirement chưa được đáp ứng.

### 3.4. Mỗi server node cần files tương thích

Với physical replication, catalog/database changes được replicate qua WAL, nhưng package files trong filesystem không được đồng bộ như database objects. Primary, standby và node dự phòng cần cài đúng extension binaries trước khi promotion hoặc sử dụng functions phụ thuộc vào library.

## 4. Kiểm tra extensions có sẵn

View pg_available_extensions liệt kê các extensions mà PostgreSQL server có thể tìm thấy qua control files.

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 4.1. Các cột

- name: tên extension.
- default_version: version mặc định mà server package cung cấp.
- installed_version: version đã cài trong database hiện tại; NULL nếu chưa cài.
- comment: mô tả ngắn trong control file.

### 4.2. Kiểm tra một extension

~~~sql
SELECT *
FROM pg_available_extensions
WHERE name = 'pg_stat_statements';
~~~

Nếu không có dòng kết quả, server có thể chưa có package/control file, hoặc extension không nằm trong đường dẫn mà PostgreSQL đang dùng.

### 4.3. Danh sách có sẵn không đồng nghĩa được phép cài

pg_available_extensions chỉ cho biết server phát hiện extension. Managed service có thể áp dụng allowlist, role restrictions hoặc yêu cầu cấu hình riêng.

### 4.4. Default version

default_version là version mặc định được package/control file khai báo. Nó không nhất thiết là version mới nhất trên internet, version mới nhất được vendor hỗ trợ hoặc version đang được cài.

## 5. Xem các phiên bản khả dụng

pg_available_extension_versions liệt kê các versions mà server có scripts tương ứng và các thuộc tính cài đặt.

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires,
    comment
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Một số cột có thể khác theo PostgreSQL major version; kiểm tra view definition trên server đang dùng trước khi đưa query vào automation.

### 5.1. installed

Cho biết version row đó có phải version đang được cài trong database hiện tại hay không.

### 5.2. superuser và trusted

Hai thuộc tính này mô tả quyền cài đặt theo control file. trusted không phải đánh giá độc lập của PostgreSQL rằng extension an toàn; đó là quyết định do extension author/package maintainer khai báo và DBA cần xem xét.

### 5.3. relocatable và schema

Cho biết extension có thể được cài hoặc chuyển sang schema khác theo quy tắc của extension hay không.

### 5.4. requires

Danh sách extensions phụ thuộc. Dependencies cần được cài theo đúng version/path trước khi extension chính có thể hoạt động.

## 6. Kiểm tra extensions đã cài

pg_extension là catalog ghi nhận các extensions trong database hiện tại.

~~~sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS extension_owner,
    n.nspname AS extension_schema,
    e.extrelocatable,
    e.extconfig,
    e.extcondition
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

### 6.1. extname

Tên extension, ví dụ pgcrypto hoặc pg_stat_statements.

### 6.2. extversion

Version đang được cài trong database. Đây là version catalog hiện ghi nhận, không phải version mới nhất mà package repository có.

### 6.3. extowner

Role sở hữu extension. Owner thường là role đã thực hiện CREATE EXTENSION, trừ các trường hợp provisioning/ownership được quản lý riêng. Owner có quyền quản lý extension theo privilege rules của PostgreSQL.

### 6.4. extnamespace

Schema được ghi nhận là schema chính của extension. Một extension có thể tạo objects trong schema đó; một số extensions hoặc objects có thể có cấu trúc khác theo script và thuộc tính relocatable.

### 6.5. extrelocatable

Cho biết extension có thể chuyển schema bằng ALTER EXTENSION SET SCHEMA hay không.

### 6.6. extconfig và extcondition

Các catalog fields này mô tả những configuration tables và điều kiện dump data do extension khai báo. Chúng liên quan đến cách pg_dump bảo toàn dữ liệu cấu hình của extension.

## 7. Cài extension bằng CREATE EXTENSION

Cú pháp cơ bản:

~~~sql
CREATE EXTENSION pgcrypto;
~~~

Lệnh này yêu cầu server tìm extension control file, kiểm tra dependencies/quyền và chạy installation script trong database hiện tại.

### 7.1. Cài có schema cụ thể

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION pgcrypto
WITH SCHEMA extensions;
~~~

Chỉ định schema khi extension cho phép và schema đã tồn tại hoặc có thể được tạo theo quyền/semantics phù hợp.

### 7.2. Cài version cụ thể

~~~sql
CREATE EXTENSION some_extension
WITH VERSION '1.4';
~~~

Version phải có sẵn trong server package và có installation script tương ứng.

### 7.3. IF NOT EXISTS

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

IF NOT EXISTS tránh lỗi nếu extension đã tồn tại, nhưng không xác minh extension đang có đúng version, schema hoặc configuration mong muốn. Sau lệnh, luôn kiểm tra pg_extension và catalog objects.

### 7.4. Tìm extension trước khi cài

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
WHERE name IN ('pgcrypto', 'pg_stat_statements', 'uuid-ossp');
~~~

### 7.5. Cài theo migration script

Trong production, đặt CREATE EXTENSION trong migration có version, review và rollback plan. Ghi nhận database, schema, requested version, owner và package version của server.

## 8. Extension control file

Control file cung cấp metadata để PostgreSQL biết extension có sẵn, version mặc định, script cài đặt, quyền và dependencies.

Tên file thường có dạng extension_name.control và được cài trong extension directory của PostgreSQL.

Một control file minh họa:

~~~ini
comment = 'Example extension'
default_version = '1.2'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
~~~

Đây chỉ là ví dụ cấu trúc; giá trị thực tế phụ thuộc extension.

### 8.1. Các thuộc tính thường gặp

- comment: mô tả extension.
- default_version: version mặc định.
- module_pathname: đường dẫn thư viện dùng trong SQL scripts.
- relocatable: có thể chuyển extension giữa schemas hay không.
- schema: schema cố định hoặc mặc định theo extension design.
- requires: dependencies.
- superuser: có yêu cầu superuser khi cài hay không.
- trusted: có thể được cài bởi non-superuser có CREATE privilege trên database nếu đáp ứng cơ chế trusted.
- directory: thư mục scripts nếu khác mặc định.
- encoding: encoding requirement của script nếu khai báo.
- no_relocate: schema restrictions cho các dependencies trong một số thiết kế.

Không phải mọi extension đều dùng mọi thuộc tính. Đọc control file và documentation của package đang cài.

### 8.2. Control file không phải SQL script

Control file khai báo metadata. Installation SQL script tạo objects và có thể tham chiếu tới shared library. Chỉ có control file mà thiếu script thì CREATE EXTENSION vẫn thất bại.

### 8.3. Control file và version

PostgreSQL tìm script cài đặt tương ứng với version được chọn, thường theo naming convention của extension. Package maintainer cần cung cấp các files nhất quán.

### 8.4. Không chỉnh control file tùy tiện

Sửa control file trực tiếp trên production có thể làm package drift, bị ghi đè khi upgrade và phá vỡ assumptions về trust/permissions. Quản lý thay đổi qua package/build pipeline có review.

## 9. Installation scripts và update scripts

Một extension thường có:
- Một installation script cho từng version được hỗ trợ.
- Các update scripts để chuyển giữa các versions.
- Control file khai báo metadata và default version.

Ví dụ tên files:

~~~text
example_extension.control
example_extension--1.0.sql
example_extension--1.1.sql
example_extension--1.0--1.1.sql
example_extension--1.1--1.2.sql
~~~

### 9.1. Installation script

Script tạo các objects như functions, types, operators, tables, views, indexes và privileges. Các lệnh trong script chạy trong transaction context theo cơ chế CREATE EXTENSION; một số operations không thể thực hiện trong transaction block cần thiết kế đặc biệt và không phù hợp với extension install scripts thông thường.

### 9.2. Update script

Update script mô tả thay đổi schema/objects giữa hai extension versions. Không nên giả định PostgreSQL tự suy ra cách chuyển đổi chỉ từ version number.

### 9.3. Direct update path

Nếu package cung cấp script từ version hiện tại tới version đích, PostgreSQL có thể dùng đường chuyển đổi đó. Nếu không có direct path, có thể có một chuỗi intermediate paths; điều này phụ thuộc graph các update scripts.

### 9.4. Version naming

Extension version strings là labels do extension author định nghĩa. Không phải mọi extension đều dùng semantic versioning chuẩn x.y.z.

### 9.5. Script idempotency và upgrade safety

Extension author chịu trách nhiệm thiết kế scripts đúng với supported paths. DBA nên đọc release notes, test trên clone và kiểm tra data transformations trước production update.

## 10. Quyền cài đặt extension

Theo mặc định, CREATE EXTENSION yêu cầu superuser nếu control file đánh dấu superuser=true hoặc extension không được khai báo trusted theo cơ chế hỗ trợ. Một số extensions có thể cho phép non-superuser cài đặt khi user có CREATE privilege trên database.

### 10.1. Superuser requirement

Các extensions có thể chứa C code hoặc thực hiện operations cần quyền đặc biệt. PostgreSQL mặc định giới hạn cài đặt để tránh user thường tự đưa code có đặc quyền vào server.

### 10.2. Trusted extension

Extension có thể khai báo trusted=true trong control file. Khi đó, user không phải superuser nhưng có CREATE privilege trên database có thể cài extension theo cơ chế trusted extension.

Trust là một cam kết của extension author/package maintainer về việc script cài đặt có thể được chạy theo cơ chế này. DBA vẫn phải kiểm tra nguồn gốc, phiên bản và security history.

### 10.3. CREATE privilege trên database

Quyền CREATE trên database cho phép tạo objects trong database theo PostgreSQL privilege model. Đây là quyền rộng hơn việc chỉ được gọi một function cụ thể.

~~~sql
GRANT CREATE ON DATABASE appdb TO extension_installer;
~~~

Chỉ cấp trong phạm vi cần thiết và thu hồi sau khi hoàn thành nếu role không cần giữ quyền.

### 10.4. Quyền schema

Tạo objects trong schema còn liên quan tới USAGE/CREATE privileges trên schema, ownership và các quy tắc của extension. CREATE trên database không tự động cấp mọi quyền trên mọi schema.

~~~sql
GRANT USAGE, CREATE ON SCHEMA extensions TO extension_installer;
~~~

Ví dụ này chỉ phù hợp khi user cần tạo objects trực tiếp trong schema đó và extension/DDL path cho phép.

### 10.5. Không cấp superuser chỉ để cài mọi extension

Dùng một DBA/provisioning role được kiểm soát hoặc cơ chế trusted extension khi phù hợp. Không biến application runtime role thành superuser.

## 11. Quản lý role cài đặt và extension owner

Tách role cài đặt khỏi role chạy ứng dụng.

Một mô hình thường dùng:

| Role | Trách nhiệm |
| --- | --- |
| platform_admin | Quản lý PostgreSQL server và package |
| database_owner | Quản lý database/schema theo policy |
| extension_installer | Cài/update extension được phê duyệt |
| application_owner | Sở hữu application objects |
| application_runtime | Đọc/ghi dữ liệu theo grants |
| monitoring_reader | Đọc thống kê cần thiết |

### 11.1. Extension owner

Role sở hữu extension có quyền quản lý extension. Không mặc định để một developer cá nhân sở hữu extension production lâu dài nếu lifecycle cần được vận hành bởi role ổn định.

### 11.2. Chuyển ownership

Có thể chuyển owner extension bằng ALTER EXTENSION ... OWNER TO trong PostgreSQL versions hỗ trợ cú pháp này. Kiểm tra version và quyền; objects bên trong extension vẫn có ownership/dependency semantics riêng và không nên giả định mọi object owner đều tự thay đổi theo cùng cách.

### 11.3. Role không còn tồn tại

Nếu role owner bị drop, PostgreSQL có thể từ chối vì còn objects phụ thuộc. Cần chuyển ownership hoặc xử lý dependencies trước khi drop role.

### 11.4. Không dùng role runtime làm extension owner

Application runtime thường cần quyền thao tác data, không cần quyền cài/update/drop extension. Tách quyền giúp giảm blast radius khi credential ứng dụng bị lộ.

## 12. Schema của extension

Nhiều extensions tạo objects trong một schema riêng hoặc schema do người cài chọn.

### 12.1. Schema riêng

Ví dụ:

~~~sql
CREATE SCHEMA extensions AUTHORIZATION database_owner;
CREATE EXTENSION pgcrypto WITH SCHEMA extensions;
~~~

Schema riêng giúp phân biệt extension objects với application objects và quản lý grants rõ hơn.

### 12.2. Search path

Application có thể gọi function không kèm schema nếu schema extension nằm trong search_path. Điều này tiện nhưng có thể tạo shadowing risk nếu untrusted users có CREATE quyền trong schema nằm trước.

~~~sql
SHOW search_path;
~~~

Ưu tiên schema có ownership/CREATE privileges được kiểm soát. Tránh để schema writable bởi user không đáng tin cậy xuất hiện trước các schemas chứa trusted functions.

### 12.3. SET SCHEMA

Với extension relocatable, có thể chuyển extension:

~~~sql
ALTER EXTENSION pgcrypto SET SCHEMA extensions;
~~~

Lệnh chỉ hợp lệ nếu extension cho phép relocation và schema đích đáp ứng điều kiện. Nó chuyển các member objects theo semantics extension; không phải mọi extension đều relocatable.

### 12.4. Extension không relocatable

Một số extensions yêu cầu schema cố định hoặc objects ở nhiều schemas. Không ép di chuyển bằng cách ALTER các objects riêng lẻ vì có thể phá vỡ extension membership.

### 12.5. Schema grants

Sau cài đặt, cấp USAGE trên schema và EXECUTE/SELECT privileges cần thiết cho application roles. Không cấp CREATE rộng nếu application chỉ cần gọi functions.

## 13. Dependencies giữa extensions

Một extension có thể khai báo requires trong control file để phụ thuộc vào extensions khác.

### 13.1. Kiểm tra requirements

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_available_extension_versions
WHERE name = 'target_extension';
~~~

### 13.2. CREATE EXTENSION ... CASCADE

PostgreSQL có thể cài dependencies cần thiết khi dùng CASCADE nếu versions/permissions phù hợp:

~~~sql
CREATE EXTENSION target_extension CASCADE;
~~~

Dùng cẩn trọng. CASCADE có thể cài thêm extensions mà DBA chưa dự kiến. Review dependency list trước.

### 13.3. Dependency graph

Một extension có thể phụ thuộc extension khác, và extension đó lại có dependencies. Inventory graph trước khi update/drop.

### 13.4. DROP dependency

DROP EXTENSION bị chặn nếu objects ngoài extension phụ thuộc vào objects của nó, trừ khi dùng CASCADE. CASCADE có thể xóa các objects phụ thuộc ngoài extension. Đọc plan/dependencies và backup trước.

### 13.5. pg_depend

System catalog pg_depend lưu dependency records giữa objects. Đây là catalog cấp thấp; dùng pg_describe_object hoặc các catalog views phù hợp để diễn giải OIDs thay vì thao tác trực tiếp.

## 14. Cập nhật extension

Cập nhật extension trong database bằng ALTER EXTENSION UPDATE.

~~~sql
ALTER EXTENSION pgcrypto UPDATE;
~~~

Lệnh dùng default version có sẵn theo server package nếu update path phù hợp.

### 14.1. Chỉ định target version

~~~sql
ALTER EXTENSION some_extension UPDATE TO '2.1';
~~~

Version đích phải có trong server package và có đường update hợp lệ từ version đang cài.

### 14.2. Kiểm tra version trước/sau

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

So sánh với pg_available_extensions và pg_available_extension_versions.

### 14.3. Update path

~~~sql
SELECT *
FROM pg_extension_update_paths('some_extension');
~~~

Function này cho biết các update paths mà PostgreSQL có thể tìm thấy theo package hiện tại. Schema/output có thể khác theo version.

### 14.4. Không có update path

Nếu không có đường chuyển đổi:
- Kiểm tra package có thiếu intermediate scripts không.
- Đọc release notes của extension.
- Xác định có cần cài version trung gian hay không.
- Xem hướng dẫn dump/recreate/migrate của extension author.
- Không sửa extversion trong catalog bằng UPDATE thủ công.

### 14.5. Extension update không phải package update

Cài package version mới trên server chỉ làm scripts/libraries mới khả dụng. Database extension version vẫn có thể ở version cũ cho tới khi ALTER EXTENSION UPDATE được thực hiện.

### 14.6. Update có thể cần restart?

ALTER EXTENSION UPDATE thường thay đổi database objects theo scripts. Nếu extension cần library mới hoặc cấu hình preload, có thể phải restart/reload theo requirements riêng. Package upgrade có thể yêu cầu restart server tùy extension/OS package.

## 15. Quy trình nâng cấp extension an toàn

1. Inventory extension names, versions, owners, schemas và dependencies.
2. Kiểm tra PostgreSQL major version và package versions.
3. Đọc release notes/changelog của extension.
4. Kiểm tra update paths từ version hiện tại tới target.
5. Xác định shared library/preload/restart requirements.
6. Tạo backup phù hợp và xác minh restore path.
7. Clone database hoặc staging environment.
8. Chạy ALTER EXTENSION UPDATE trên clone.
9. Kiểm tra objects, functions, types, indexes và application behavior.
10. Đo lock/downtime và performance impact.
11. Lên maintenance/change window nếu cần.
12. Cài package version tương thích trên tất cả nodes.
13. Thực hiện restart/reload theo yêu cầu.
14. Chạy extension update trên đúng database(s).
15. Xác minh pg_extension, extension functions và application smoke tests.
16. Theo dõi logs, query plans và error rates.
17. Ghi lại version mới và rollback/recovery notes.

### 15.1. Nhiều databases

Extension được cài theo database. Một cluster có thể có extension version khác nhau giữa databases nếu provisioning không đồng bộ. Lập inventory theo từng database.

### 15.2. Nhiều extension dependencies

Cập nhật dependencies theo thứ tự phù hợp với graph và release notes. Tránh update một dependency làm extension khác không tương thích.

### 15.3. Rollback

Không phải mọi extension update đều có downgrade script. Một số thay đổi schema/data không thể đảo ngược bằng ALTER EXTENSION UPDATE. Chuẩn bị restore từ backup hoặc migration-specific rollback trước khi update.

## 16. Gỡ extension

Lệnh cơ bản:

~~~sql
DROP EXTENSION some_extension;
~~~

Mặc định PostgreSQL dùng RESTRICT behavior: không xóa nếu còn objects phụ thuộc ngoài extension.

### 16.1. DROP EXTENSION ... RESTRICT

~~~sql
DROP EXTENSION some_extension RESTRICT;
~~~

Đây là lựa chọn an toàn hơn để phát hiện dependencies đang ngăn việc gỡ.

### 16.2. DROP EXTENSION ... CASCADE

~~~sql
DROP EXTENSION some_extension CASCADE;
~~~

CASCADE có thể xóa các objects phụ thuộc vào objects của extension, kể cả objects do application tạo. Không dùng CASCADE như cách xử lý lỗi nhanh.

### 16.3. Gỡ package không gỡ extension objects

Xóa OS package trong khi database vẫn ghi nhận extension có thể khiến functions không còn load được hoặc restore/upgrade thất bại. Gỡ database extension và server package là hai lifecycle steps khác nhau.

### 16.4. Gỡ extension khỏi nhiều databases

Phải chạy DROP EXTENSION trong từng database có cài extension. Kiểm tra inventory trước khi package removal.

### 16.5. Backup trước khi drop

Nếu extension tạo tables chứa dữ liệu, functions hoặc types mà application cần, drop có thể làm mất objects/data. Xác định data ownership và export nếu cần.

## 17. Kiểm tra objects thuộc extension

pg_depend ghi nhận quan hệ dependency, trong đó objects thuộc extension có dependency type đặc biệt.

Có thể dùng pg_extension và pg_depend để khám phá; tránh dựa vào OIDs hard-coded.

~~~sql
SELECT
    e.extname,
    e.extversion,
    d.classid::regclass AS catalog,
    d.objid,
    d.objsubid,
    d.deptype
FROM pg_extension AS e
JOIN pg_depend AS d
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, catalog::text, d.objid;
~~~

### 17.1. deptype e

Dependency type e biểu thị object là member của extension theo catalog semantics. Các dependency types khác có ý nghĩa riêng.

### 17.2. Không sửa catalog trực tiếp

Không UPDATE/DELETE pg_extension hoặc pg_depend để ép extension version/ownership. Dùng DDL được PostgreSQL hỗ trợ; sửa catalog thủ công có thể làm database metadata không nhất quán.

### 17.3. ALTER EXTENSION ADD/DROP

PostgreSQL có lệnh ALTER EXTENSION ... ADD/DROP object để quản lý membership trong một số trường hợp. Chỉ dùng khi hiểu extension packaging và object ownership; không phải cách chung để sửa một extension cài đặt lỗi.

## 18. Extension configuration tables và pg_dump

Một số extensions tạo tables chứa cấu hình/dữ liệu cần được dump cùng database.

### 18.1. pg_extension_config_dump

Extension installation script có thể gọi pg_extension_config_dump để khai báo table data cần được đưa vào dump và có thể chỉ định filter condition.

### 18.2. extconfig và extcondition

pg_extension lưu metadata về configuration tables và conditions. Kiểm tra:

~~~sql
SELECT
    extname,
    extconfig,
    extcondition
FROM pg_extension
ORDER BY extname;
~~~

### 18.3. Vì sao quan trọng?

pg_dump thường dump extension creation command và xử lý config table data theo metadata. Nếu package/script không khai báo đúng, restore có thể thiếu configuration data cần thiết hoặc dump data không như mong đợi.

### 18.4. Không dump server binaries

pg_dump không đóng gói shared libraries, control files hoặc installation/update scripts. Target phải có package tương thích trước khi restore CREATE EXTENSION.

## 19. Extension và backup/restore

### 19.1. pg_dump

Logical dump có thể lưu lệnh CREATE EXTENSION và dữ liệu cấu hình mà extension khai báo. Nó không chứa toàn bộ server-side package.

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

### 19.2. Restore

Trước khi restore:
1. Cài extension packages tương thích trên target.
2. Kiểm tra target PostgreSQL major version.
3. Kiểm tra shared library dependencies.
4. Xác minh extension version/update paths.
5. Restore schema/data theo plan.
6. Kiểm tra extension objects và application behavior.

### 19.3. Restore vào môi trường không có extension

CREATE EXTENSION trong dump sẽ thất bại nếu target không có control/script files hoặc extension không được hỗ trợ. Không bỏ qua lỗi và tuyên bố restore hoàn tất.

### 19.4. Physical backup

Physical backup có database catalogs và relation files nhưng không thay thế việc quản lý OS packages, shared libraries và runtime dependencies. Với standby/restore host, cài đúng packages trước khi cần sử dụng extension-dependent objects.

### 19.5. PITR

PITR phục hồi database state và extension catalog state theo WAL. Binary/library files vẫn cần tương thích với server version và database state được phục hồi.

## 20. Extension trong physical replication và HA

### 20.1. Catalog objects được replicate

Khi CREATE/ALTER EXTENSION được thực hiện trên primary, database catalog/object changes được ghi WAL và replicate tới physical standby.

### 20.2. Package files không được replicate

OS-level package files không nằm trong WAL. Mỗi node phải có extension binaries, control files và scripts tương thích.

### 20.3. Promotion

Trước failover, xác minh standby có các shared libraries cần thiết. Nếu standby được promote nhưng package thiếu hoặc version không khớp, application queries có thể lỗi khi gọi extension functions.

### 20.4. Rolling upgrades

Với rolling upgrade hoặc standby replacement, xác minh compatibility giữa extension binary, PostgreSQL major version và database extension version trên từng node.

### 20.5. Extension preload

Nếu extension cần shared_preload_libraries, cấu hình phải nhất quán trên các nodes có thể trở thành primary. Một số extensions chỉ load ở session/backend level; một số yêu cầu preload.

## 21. Extension trong logical replication

Logical replication chủ yếu chuyển row changes của publication tables. Nó không tự replicate DDL hoặc cài server-side extensions.

### 21.1. Provision target

Trên subscriber:
- Cài extension packages tương thích.
- Tạo extensions cần thiết.
- Tạo schema/functions/types/indexes theo migration plan.
- Kiểm tra owner/grants.
- Bảo đảm target schema tương thích với changes đang apply.

### 21.2. Extension tables

Nếu extension tạo tables và những tables đó nằm trong publication, row changes có thể được publish theo logical replication rules. Điều đó không có nghĩa toàn bộ extension metadata/functions được chuyển.

### 21.3. Version mismatch

Source và target extension versions có thể khác nếu data types/behavior tương thích và migration được thiết kế rõ. Không giả định mọi version pair an toàn.

### 21.4. CDC consumers

Logical decoding plugin là một loại extension-related component; package, output plugin và server configuration phải được cài/kiểm tra ở nơi cần thiết. Plugin không đồng nghĩa với SQL extension được cài trong mọi database.

## 22. shared_preload_libraries và extensions

Một số extensions cần được load khi PostgreSQL server khởi động.

Ví dụ pg_stat_statements:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

Sau khi cài package và restart server, tạo extension trong từng database cần thống kê:

~~~sql
CREATE EXTENSION pg_stat_statements;
~~~

### 22.1. Hai bước riêng biệt

- shared_preload_libraries load module vào server startup.
- CREATE EXTENSION tạo SQL objects/catalog metadata trong database.

Thiếu một trong hai có thể khiến tính năng không hoạt động đúng.

### 22.2. Restart requirement

shared_preload_libraries cần restart server để áp dụng. ALTER SYSTEM hoặc sửa config rồi reload đơn thuần không đủ.

### 22.3. Nhiều libraries

Có thể cấu hình nhiều module, phân tách bằng dấu phẩy. Khi chỉnh, bảo toàn các libraries đang cần và theo dõi cú pháp/config precedence.

### 22.4. Không phải extension nào cũng cần preload

Đọc documentation của extension. Không thêm module vào shared_preload_libraries chỉ vì đã cài package.

## 23. Extension và quyền sử dụng sau khi cài

Cài extension không tự động có nghĩa mọi application roles được phép sử dụng tất cả objects theo policy mong muốn.

### 23.1. USAGE trên schema

Nếu extension objects nằm trong schema riêng, role cần USAGE trên schema để resolve objects theo quyền phù hợp.

~~~sql
GRANT USAGE ON SCHEMA extensions TO app_runtime;
~~~

### 23.2. EXECUTE trên functions

Functions có ACL riêng. Kiểm tra default privileges và grants sau install/update.

~~~sql
GRANT EXECUTE ON FUNCTION extensions.some_function(text)
TO app_runtime;
~~~

Function signature chỉ là ví dụ; dùng đúng overload thực tế.

### 23.3. Tables và sequences

Nếu extension tạo tables/sequences, cấp SELECT/INSERT/UPDATE hoặc USAGE/SELECT theo nhu cầu. Không cấp ALL PRIVILEGES mặc định.

### 23.4. PUBLIC privileges

Một số extension scripts tạo objects có privileges cho PUBLIC. Kiểm tra ACL và security policy; không giả định tất cả extensions dùng cùng default grants.

### 23.5. SECURITY DEFINER functions

Nếu extension cung cấp SECURITY DEFINER functions, kiểm tra owner, search_path và behavior theo tài liệu. Đây là vùng cần chú ý vì function có thể thực thi với quyền của owner.

## 24. Search path và extension security

search_path ảnh hưởng cách PostgreSQL phân giải tên schema/object không được qualify.

### 24.1. Schema shadowing

Nếu untrusted role có CREATE privilege trong schema đứng trước schema chứa extension functions, role đó có thể tạo objects trùng tên và ảnh hưởng name resolution trong những context không an toàn.

### 24.2. Schema ownership

Giữ quyền CREATE trên schema chứa trusted extension objects cho DBA/owner đáng tin cậy. Application roles thường chỉ cần USAGE và object-specific privileges.

### 24.3. Qualify object names

Trong security-sensitive SQL, dùng schema-qualified function/table names khi phù hợp.

### 24.4. Function search_path

Đối với SECURITY DEFINER code tự viết, đặt search_path an toàn và schema-qualify dependencies. Không thay đổi extension function definitions trực tiếp nếu không có hướng dẫn từ vendor.

## 25. Security và supply chain

Extensions chạy trong cùng PostgreSQL server process. Extension có C code hoặc quyền đặc biệt có thể tác động sâu tới database server.

### 25.1. Nguồn package

Chỉ cài từ:
- Official PostgreSQL distribution/repository phù hợp.
- OS vendor repositories được tin cậy.
- Managed-service catalog chính thức.
- Extension maintainer/release channel có provenance rõ.
- Internal artifact registry đã được kiểm soát.

### 25.2. Kiểm tra compatibility

Xác minh PostgreSQL major version, OS architecture, ABI, compiler/runtime dependencies và extension release compatibility.

### 25.3. Security advisories

Theo dõi CVEs, release notes và security advisories của extension. Extension có thể có vulnerabilities độc lập với PostgreSQL core.

### 25.4. Least privilege

Không cấp superuser cho application roles. Hạn chế database CREATE, schema CREATE, extension ownership và signal privileges.

### 25.5. Artifact integrity

Pin package versions, verify repository/signatures/checksums theo quy trình OS/vendor, ghi SBOM hoặc inventory và quản lý artifact promotion giữa environments.

### 25.6. Production change control

Yêu cầu:
- Ticket/change record.
- Extension name/version.
- Source/provenance.
- Compatibility evidence.
- Permissions required.
- Backup/restore validation.
- Rollback plan.
- Owner và approval.

## 26. Extensions phổ biến và yêu cầu vận hành

### 26.1. pg_stat_statements

Thu thập thống kê query. Thường cần package, shared_preload_libraries và CREATE EXTENSION trong mỗi database muốn sử dụng view/functions. Cần kiểm soát query text visibility và stats reset semantics.

### 26.2. PostGIS

Cung cấp geometry/geography types, spatial functions và operators/index support. Cần cài package tương thích với PostgreSQL/OS; version upgrade có thể bao gồm SQL scripts và data/object transformations. Kiểm tra PostGIS extension family/version theo documentation.

### 26.3. pgcrypto

Cung cấp một số cryptographic functions. Xem xét key management và threat model; extension functions không thay thế thiết kế quản lý secrets/keys an toàn.

### 26.4. uuid-ossp

Cung cấp UUID generation functions. Kiểm tra package availability và privilege/compatibility theo môi trường.

### 26.5. hstore

Cung cấp key/value data type và operators. Cần schema/type compatibility khi dump/restore và khi migrate ứng dụng.

### 26.6. postgres_fdw

Cung cấp foreign data wrapper cho PostgreSQL remote servers. Cần quản lý foreign servers, user mappings, network routes và credentials; các thông tin kết nối không nên bị xem là đã được chuyển chỉ vì extension được cài.

### 26.7. Citus và các extension kiến trúc

Một số extensions thay đổi cách phân phối dữ liệu, planner/executor behavior hoặc cluster topology. Chúng cần deployment-specific installation/upgrade procedures; không áp dụng runbook extension SQL chung mà bỏ qua hướng dẫn vendor.

## 27. Extension trên managed PostgreSQL

Managed providers thường giới hạn extensions có thể cài vì họ kiểm soát server packages, shared libraries, background workers và security surface.

### 27.1. Allowlist

Kiểm tra provider documentation/console để biết:
- Extensions được hỗ trợ.
- Phiên bản được hỗ trợ.
- Required parameter groups.
- Roles được phép cài.
- Extensions cần restart.
- Restrictions theo instance tier/region/engine version.

### 27.2. Parameter groups

Một số extensions cần shared_preload_libraries hoặc custom parameters. Managed service có thể yêu cầu sửa parameter group và reboot/failover.

### 27.3. Role model

Managed superuser thường không phải PostgreSQL superuser thật. Provider có thể cấp role quản trị riêng và hạn chế một số commands. Không giả định quyền trên self-managed PostgreSQL giống managed service.

### 27.4. Upgrade windows

Extension version có thể được provider điều khiển cùng engine upgrade. Kiểm tra compatibility trước khi nâng major engine version.

### 27.5. Không tự cài binary

Nếu provider không cho phép package, CREATE EXTENSION không thể tự tải hoặc cài shared library. Chọn extension được hỗ trợ hoặc kiến trúc thay thế được vendor chấp nhận.

## 28. Extension và PostgreSQL major-version upgrade

Khi nâng major version PostgreSQL, extension binaries phải được build cho major version mới và database extension objects phải có đường upgrade phù hợp.

### 28.1. Inventory trước upgrade

Lưu extension name, extversion, owner, schema, dependencies, package versions và preload settings cho từng database.

### 28.2. Package target trước

Cài đúng extension packages cho target major version. Không dùng shared library được build cho PostgreSQL major version cũ.

### 28.3. pg_upgrade

pg_upgrade có thể kiểm tra một số compatibility conditions và extension requirements. Đọc output/logs và extension vendor guidance; không giả định mọi extension tự upgrade hoàn toàn.

### 28.4. Update SQL sau upgrade

Một số extensions cần ALTER EXTENSION UPDATE sau engine upgrade để chuyển database objects sang version tương ứng.

### 28.5. Test trên clone

Chạy pg_upgrade rehearsal hoặc migration rehearsal với extension packages thực tế, data size đại diện và application queries.

## 29. Extension và containers

Trong containerized PostgreSQL, extension files là một phần image/filesystem của server container.

### 29.1. Immutable image

Đưa extension packages vào Docker image/build artifact có version pin. Không cài thủ công trong một running container rồi kỳ vọng file tồn tại sau khi recreate.

### 29.2. Primary/standby images

Dùng image tương thích trên mọi nodes có thể chạy primary/standby. Kiểm tra architecture, library dependencies và PostgreSQL major version.

### 29.3. Image upgrade

Khi nâng PostgreSQL image, xác minh extension packages có mặt và tương thích trước khi khởi động cluster hoặc promotion.

### 29.4. Security scanning

Scan base image và extension packages, pin versions và cập nhật theo vulnerability management process.

## 30. Inventory và audit extension

Một inventory nên được thu thập theo database và server node.

Query trong database:

~~~sql
SELECT
    current_database() AS database_name,
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS schema_name,
    e.extrelocatable
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Server availability:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 30.1. Inventory fields

Lưu:
- Cluster/environment.
- PostgreSQL version.
- OS/container image.
- Database name.
- Extension name/version.
- Owner/schema.
- Dependencies.
- Trusted/superuser/relocatable flags.
- Package version/provenance.
- Preload requirements.
- Approval/change reference.
- Last reviewed date.

### 30.2. Drift detection

So sánh extension inventory giữa dev, staging, production và HA nodes. Tìm extension thiếu, version lệch, schema khác, owner không đúng hoặc package chưa được cài.

### 30.3. Audit changes

Ghi nhận CREATE/ALTER/DROP EXTENSION và package updates qua change logs/audit system. PostgreSQL logs có thể giúp truy vết DDL nếu logging policy phù hợp.

## 31. Kiểm tra extension health sau cài đặt

Sau CREATE EXTENSION hoặc UPDATE:
1. Kiểm tra pg_extension.extversion.
2. Kiểm tra extension schema và owner.
3. Xác nhận required shared library load được.
4. Chạy một function/type/operator smoke test.
5. Kiểm tra privileges của application role.
6. Kiểm tra logs không có library load errors.
7. Xác nhận preload parameters/restart đã áp dụng nếu cần.
8. Kiểm tra replication/standby compatibility.
9. Kiểm tra backup/restore path.
10. Theo dõi query plans/performance nếu extension ảnh hưởng planner.

### 31.1. Kiểm tra functions

Dùng pg_proc và namespace catalogs để liệt kê functions thuộc schema extension; không giả định mọi extension đặt toàn bộ objects trong một schema.

### 31.2. Kiểm tra types

Dùng pg_type, pg_namespace và extension dependencies để xác định types do extension tạo.

### 31.3. Smoke test theo application

Một extension function chạy được trong psql với owner không chứng minh application_runtime có đủ quyền. Test bằng role thật của ứng dụng.

## 32. Troubleshooting: extension không có sẵn

Thông báo thường gặp có thể nói extension control file không tồn tại.

Nguyên nhân:
- Package chưa cài.
- Package cho PostgreSQL major version khác.
- Extension chưa được build cho OS/architecture.
- Extension không có trong managed-service allowlist.
- PostgreSQL đang chạy binary installation khác với package vừa cài.
- Container image không chứa package.

Hướng xử lý:
1. Xác nhận SHOW server_version.
2. Xác định PostgreSQL installation/package path.
3. Kiểm tra extension control file trong đúng extension directory.
4. Kiểm tra package repository và package name.
5. Xác minh package build target đúng PostgreSQL major version.
6. Với managed service, kiểm tra allowlist/provider policy.
7. Không tự copy files từ một server khác nếu chưa xác minh ABI/dependencies.

## 33. Troubleshooting: permission denied khi CREATE EXTENSION

Nguyên nhân:
- Extension yêu cầu superuser.
- Extension không được đánh dấu trusted.
- User thiếu CREATE trên database.
- User thiếu quyền schema cần thiết.
- Managed service giới hạn extension installer role.
- Extension dependencies yêu cầu quyền cao hơn.

Hướng xử lý:
1. Kiểm tra pg_available_extension_versions.superuser/trusted.
2. Kiểm tra database privileges.
3. Kiểm tra schema ownership/CREATE.
4. Dùng DBA/provisioning role theo policy nếu extension yêu cầu superuser.
5. Không cấp superuser lâu dài cho application user chỉ để vượt lỗi.

## 34. Troubleshooting: shared library không load được

Nguyên nhân:
- Thiếu .so/.dll.
- Library build cho PostgreSQL version khác.
- Thiếu system library dependency.
- module_pathname/control file sai.
- Library không có trong server's library path.
- Package upgrade chưa restart hoặc node chưa được cập nhật.

Hướng xử lý:
1. Đọc server logs để lấy library path/error chính xác.
2. Xác minh package trên đúng host/node/container.
3. Kiểm tra architecture/ABI/dependencies.
4. Kiểm tra control file và module_pathname.
5. Kiểm tra preload settings nếu extension yêu cầu.
6. Restart/reload theo đúng requirement.
7. Test trên standby/promotion node.

## 35. Troubleshooting: ALTER EXTENSION UPDATE thất bại

Nguyên nhân:
- Thiếu update script/path.
- Extension package version không chứa target script.
- Dependency version chưa tương thích.
- Update script gặp dữ liệu cũ hoặc object conflict.
- Quyền owner/superuser không đủ.
- Extension đang bị sử dụng/DDL lock contention.

Hướng xử lý:
1. Ghi lại extversion hiện tại.
2. Kiểm tra pg_available_extension_versions.
3. Dùng pg_extension_update_paths.
4. Đọc release notes và upgrade instructions.
5. Thử trên clone/backup restore.
6. Xác định intermediate versions cần thiết.
7. Không chỉnh catalog extversion thủ công.
8. Nếu update thất bại giữa chừng, kiểm tra transaction/error semantics và object state trước khi retry.

## 36. Troubleshooting: DROP EXTENSION bị chặn

Nguyên nhân:
- Application objects phụ thuộc extension functions/types/operators.
- Views, generated columns hoặc indexes tham chiếu extension objects.
- Extension khác phụ thuộc extension đang gỡ.
- CASCADE policy không được chấp thuận.

Hướng xử lý:
1. Đọc dependency error.
2. Xác định objects phụ thuộc.
3. Dùng pg_depend/catalog inspection để lập dependency map.
4. Xác định object nào cần thay thế hoặc giữ lại.
5. Export dữ liệu/configuration cần thiết.
6. Chỉ dùng CASCADE sau khi review toàn bộ objects có thể bị xóa và có backup/approval.

## 37. Quy trình change management

### Trước khi cài

- Xác định business requirement.
- Xác minh extension có hỗ trợ trên PostgreSQL/OS/provider.
- Đánh giá security/provenance/CVE.
- Xác định owner, schema và privileges.
- Kiểm tra dependencies và preload/restart needs.
- Xác định impact tới HA, replication và backup.
- Thử trên development/staging.
- Tạo change record và rollback plan.

### Khi cài

- Cài package đúng node/image.
- Kiểm tra control/scripts/libraries.
- Cấu hình preload nếu cần.
- Restart/reload theo yêu cầu.
- CREATE EXTENSION với version/schema tường minh.
- Ghi owner và grants.
- Chạy smoke tests.

### Sau khi cài

- Cập nhật inventory.
- Kiểm tra standby nodes.
- Kiểm tra application permissions.
- Theo dõi logs/performance.
- Xác minh backup/restore.
- Ghi lại version và provenance.

## 38. Quy trình update extension production

1. Freeze extension inventory và PostgreSQL version baseline.
2. Xác định version target được vendor/provider hỗ trợ.
3. Kiểm tra control files và update paths trên server.
4. Đọc changelog, CVEs và breaking changes.
5. Xác định DDL locks/data transformations.
6. Kiểm tra dependencies giữa extensions.
7. Tạo backup và kiểm chứng restore.
8. Cài package version tương thích trên mọi HA nodes.
9. Thực hiện required restart nếu có.
10. Chạy ALTER EXTENSION UPDATE trong đúng database.
11. Kiểm tra extversion, schema, owner và function signatures.
12. Chạy application smoke/regression tests.
13. Kiểm tra replica health và failover readiness.
14. Cập nhật inventory và change record.
15. Theo dõi logs/performance sau thay đổi.

## 39. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ chạy CREATE EXTENSION mà không cài package | Thiếu control file/library | Cài server package trước |
| Nhầm package update với extension update | Database vẫn dùng version cũ | Chạy ALTER EXTENSION UPDATE theo path |
| Cài extension bằng superuser cho tiện | Tăng blast radius | Dùng installer role/approved process |
| Cấp CREATE trên database cho runtime role | Runtime có thể tạo objects ngoài ý muốn | Tách provisioning và runtime roles |
| Tin mọi extension là trusted | Có thể chạy code không an toàn | Kiểm tra control file và provenance |
| Cài package chỉ trên primary | Failover node thiếu library | Đồng bộ packages trên mọi nodes |
| Bỏ qua managed allowlist | CREATE EXTENSION không hoạt động | Kiểm tra provider support |
| Dùng IF NOT EXISTS rồi bỏ qua kiểm tra | Version/schema có thể sai | Xác minh pg_extension |
| Update không thử trên clone | Production update lỗi hoặc lock lâu | Rehearsal và backup |
| Sửa extversion trong catalog | Metadata không nhất quán | Dùng ALTER EXTENSION |
| DROP ... CASCADE không review | Xóa application objects | Phân tích dependencies |
| Xóa package trước khi DROP extension | Functions không load được | Theo đúng lifecycle |
| Không kiểm tra search_path | Object shadowing/security risk | Schema ownership và qualified names |
| Quên preload/restart | Extension feature không hoạt động | Theo dõi startup requirements |
| Quên target package khi restore | Restore CREATE EXTENSION thất bại | Provision target packages |
| Giả định logical replication chuyển DDL | Subscriber thiếu extension objects | Provision riêng trên target |
| Không pin package version | Môi trường drift | Versioned artifacts/inventory |
| Không theo dõi CVEs | Extension cũ có lỗ hổng | Security lifecycle |

## 40. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging hoặc môi trường có quyền phù hợp. Không cài/gỡ extension, cấp superuser hoặc chạy CASCADE trên production chỉ để thử nghiệm.

1. **Inventory:** truy vấn pg_available_extensions.
2. **Installed:** truy vấn pg_extension.
3. **Versions:** liệt kê pg_available_extension_versions.
4. **Filter:** tìm pg_stat_statements trong danh sách khả dụng.
5. **Owner:** hiển thị extowner dưới dạng role name.
6. **Schema:** hiển thị extnamespace và schema name.
7. **Relocatable:** tìm extensions có relocatable true/false.
8. **Trusted:** liệt kê trusted flags nếu version hỗ trợ.
9. **Superuser:** so sánh superuser requirements.
10. **Requires:** xem dependencies của một extension.
11. **Install:** cài pgcrypto trong lab.
12. **Schema install:** cài một extension vào schema riêng.
13. **Version pin:** cài version cụ thể nếu package cung cấp.
14. **IF NOT EXISTS:** thử lệnh và xác minh version sau đó.
15. **Available vs installed:** phân biệt package availability với database installation.
16. **Control file:** tìm control file của một extension trên lab host.
17. **SQL scripts:** tìm installation script tương ứng.
18. **Update scripts:** liệt kê các version transition scripts.
19. **Shared library:** xác định module_pathname của extension có C code.
20. **Package manager:** xác định OS package cung cấp extension.
21. **Version compatibility:** kiểm tra package cho PostgreSQL major version hiện tại.
22. **Trusted install:** thử cài trusted extension bằng non-superuser có CREATE privilege trong lab.
23. **Untrusted install:** quan sát permission requirement của extension cần superuser.
24. **Database CREATE:** cấp CREATE trên database cho installer role.
25. **Schema CREATE:** cấp quyền schema phù hợp và kiểm tra installation behavior.
26. **Least privilege:** tạo extension_installer riêng.
27. **Runtime role:** xác nhận application role không có CREATE EXTENSION privileges.
28. **Owner:** kiểm tra extension owner sau install.
29. **Ownership:** chuyển owner theo syntax/version được hỗ trợ.
30. **Search path:** kiểm tra search_path của application role.
31. **Schema shadowing:** mô phỏng object shadowing trong lab và phân tích rủi ro.
32. **USAGE:** cấp USAGE trên extension schema.
33. **EXECUTE:** cấp EXECUTE trên function cụ thể.
34. **ACL:** kiểm tra privileges của extension objects.
35. **Dependencies:** xem requires trong available versions.
36. **CASCADE install:** cài extension có dependency trong lab.
37. **pg_depend:** liệt kê member objects của extension.
38. **Update paths:** gọi pg_extension_update_paths.
39. **Update:** nâng extension giữa hai versions có sẵn trong lab.
40. **Version check:** xác nhận extversion sau update.
41. **Missing path:** mô phỏng package thiếu update script và đọc lỗi.
42. **Intermediate update:** thử update qua version trung gian nếu extension hỗ trợ.
43. **Schema move:** thử ALTER EXTENSION SET SCHEMA với extension relocatable.
44. **Non-relocatable:** xác định extension không thể chuyển schema.
45. **Config tables:** xem extconfig/extcondition.
46. **Dump:** tạo pg_dump và tìm CREATE EXTENSION trong archive listing.
47. **Restore:** restore sang database có package tương thích.
48. **Missing package:** mô phỏng restore khi target không có extension files.
49. **Drop restrict:** thử DROP EXTENSION RESTRICT khi có dependent object.
50. **Drop cascade:** trong lab, xem objects bị xóa khi CASCADE.
51. **Preload:** cấu hình shared_preload_libraries cho pg_stat_statements.
52. **Restart:** xác minh restart requirement của preload.
53. **Create stats extension:** chạy CREATE EXTENSION pg_stat_statements trong database lab.
54. **Extension per database:** cài extension trong hai databases và so sánh catalog.
55. **Physical standby:** cài package trên standby và kiểm tra failover readiness.
56. **Logical subscriber:** provision extension objects trên target trước khi apply workload.
57. **Package drift:** so sánh extension package versions giữa nodes.
58. **Major upgrade:** lập inventory extensions trước PostgreSQL major-version upgrade.
59. **pg_upgrade:** chạy rehearsal có extension packages tương thích.
60. **PostGIS:** kiểm tra version và smoke test PostGIS trong lab nếu package hỗ trợ.
61. **pgcrypto:** chạy một function test và đánh giá key management boundary.
62. **uuid-ossp:** kiểm tra UUID functions trong lab.
63. **postgres_fdw:** cài extension và inventory foreign servers/user mappings.
64. **Managed service:** tìm allowlist extensions của provider.
65. **Provider role:** xác định managed-service extension installer privileges.
66. **CVE:** tìm security advisories của một extension được dùng.
67. **Provenance:** ghi package source, version và checksum.
68. **SBOM:** thêm extension packages vào software inventory.
69. **Image build:** thêm extension package vào PostgreSQL container image.
70. **Image parity:** xác nhận primary/standby dùng image có cùng extension binaries.
71. **Audit:** ghi nhận CREATE/ALTER/DROP EXTENSION trong change log.
72. **Drift:** so sánh extension versions giữa dev/staging/production.
73. **Health:** tạo post-install smoke test cho function/type.
74. **Privileges:** test extension function bằng application_runtime.
75. **Failure:** điều tra control file không tìm thấy.
76. **Failure:** điều tra shared library load error.
77. **Failure:** điều tra permission denied khi CREATE EXTENSION.
78. **Failure:** điều tra ALTER EXTENSION UPDATE không có path.
79. **Runbook:** viết quy trình production extension install/update/drop.
80. **Thiết kế tổng hợp:** lập policy quản lý extension cho PostgreSQL fleet gồm package provenance, allowlist, version pinning, owner/privileges, dependencies, HA/restore, security advisories, upgrade rehearsals và audit.

## 41. Checklist quản trị extension

### Availability và compatibility

- [ ] Extension có trong server package/managed-service allowlist.
- [ ] Package khớp PostgreSQL major version và OS/architecture.
- [ ] Control file, install scripts và update scripts đầy đủ.
- [ ] Shared library dependencies đã được cài.
- [ ] Required preload/restart settings đã xác định.
- [ ] Dependencies và update paths đã kiểm tra.

### Privileges và ownership

- [ ] Đã xác định superuser/trusted requirements.
- [ ] CREATE privilege chỉ cấp cho installer cần thiết.
- [ ] Schema CREATE/USAGE được kiểm soát.
- [ ] Extension owner là role vận hành ổn định.
- [ ] Application runtime không có quyền cài/drop extension.
- [ ] Function/table/sequence grants theo least privilege.
- [ ] Search path và schema ownership an toàn.

### Lifecycle

- [ ] Extension inventory được lưu theo database.
- [ ] Package versions được pin/ghi nhận.
- [ ] CREATE EXTENSION dùng version/schema có chủ đích.
- [ ] IF NOT EXISTS được theo sau bằng verification.
- [ ] ALTER EXTENSION UPDATE có rehearsal.
- [ ] DROP EXTENSION dependencies được review.
- [ ] Không sửa system catalogs thủ công.

### HA, backup và security

- [ ] Packages có trên mọi HA nodes.
- [ ] Restore target có package tương thích.
- [ ] Logical subscribers được provision extension riêng.
- [ ] Managed-service support được xác nhận.
- [ ] CVEs/release notes được theo dõi.
- [ ] Artifact provenance và integrity được kiểm tra.
- [ ] Change record, backup và rollback plan sẵn sàng.

## 42. Tổng kết

Quản lý extension PostgreSQL cần điều phối hai lifecycle: server-side package và database-side extension objects.

~~~text
APPROVE EXTENSION
       |
       v
VERIFY PACKAGE / VERSION / PROVENANCE
       |
       v
INSTALL FILES ON SERVER NODES
       |
       v
CONFIGURE PRELOAD / RESTART IF REQUIRED
       |
       v
CHECK DATABASE PRIVILEGES / SCHEMA
       |
       v
CREATE EXTENSION
       |
       v
VERIFY OWNER / VERSION / OBJECTS / GRANTS
       |
       v
MONITOR / BACKUP / UPGRADE / AUDIT
~~~

Những nguyên tắc quan trọng:

- **Package và CREATE EXTENSION là hai bước riêng.** Server cần control files, SQL scripts và shared libraries trước khi database có thể cài extension.
- **Extension được cài theo database.** Inventory từng database và không giả định cài một lần cho toàn cluster.
- **Trusted không có nghĩa là extension đã được kiểm toán độc lập.** Kiểm tra author, package provenance, CVEs và security policy.
- **Superuser và CREATE privilege có phạm vi khác nhau.** Cấp quyền cài đặt có chủ đích; giữ application runtime role ở mức tối thiểu.
- **Owner/schema/search_path là một phần của security model.** Tránh schema writable bởi untrusted roles và test bằng role ứng dụng thật.
- **Package upgrade không tự cập nhật extension catalog version.** Dùng ALTER EXTENSION UPDATE và kiểm tra update path.
- **Không phải mọi extension đều relocatable hoặc có downgrade path.** Rehearse trên clone và có restore plan.
- **DROP CASCADE có thể xóa application objects.** Phân tích dependencies trước khi gỡ.
- **Binary files không được physical/logical replication chuyển như database objects.** Provision packages trên HA nodes và subscribers theo đúng kiến trúc.
- **Backup/restore cần extension packages tương thích.** pg_dump không đóng gói server-side binaries.
- **Managed services có allowlists và role models riêng.** Xác minh provider support trước khi thiết kế migration.
- **Extension là code chạy trong database server trust boundary.** Pin versions, scan vulnerabilities, audit changes và quản lý artifacts.

Một policy extension tốt giúp PostgreSQL fleet giữ được tính nhất quán giữa environments, giới hạn quyền cài đặt, nâng cấp có kiểm soát và khôi phục được database trên một server mới mà không thiếu thư viện hoặc extension objects cần thiết.

