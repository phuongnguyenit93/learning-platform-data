# Extension, schema cài đặt và vòng đời CREATE hoặc ALTER EXTENSION

PostgreSQL extension là cơ chế đóng gói và quản lý một tập đối tượng database có liên quan như functions, operators, data types, casts, index operator classes, tables, views và các thành phần hỗ trợ khác. Thay vì phải chạy thủ công nhiều file SQL theo đúng thứ tự, người quản trị có thể cài đặt một extension bằng một lệnh CREATE EXTENSION, xem phiên bản đang dùng trong catalog và nâng cấp bằng ALTER EXTENSION UPDATE khi extension cung cấp đường nâng cấp tương ứng.

Extension có thể chỉ gồm SQL objects hoặc kết hợp SQL với shared libraries viết bằng C. Vì vậy vòng đời extension không chỉ nằm trong database. Các file control/SQL scripts và thư viện nhị phân phải được cài ở đúng PostgreSQL installation trên server; sau đó extension mới được đăng ký trong từng database. Một extension được cài trong database A không tự xuất hiện trong database B, dù hai database nằm cùng cluster. Trong môi trường HA, các node cần có package và binary tương thích để standby có thể replay WAL hoặc node được promote tiếp tục hoạt động.

Schema cài đặt là một phần quan trọng của thiết kế extension. Một số extension cho phép relocatable, nghĩa là người dùng chọn schema khi CREATE EXTENSION hoặc chuyển schema sau này. Extension khác yêu cầu schema cố định vì SQL scripts có dependencies hoặc references đặc thù. Quyền sở hữu schema, search_path, privileges và trusted installation cũng ảnh hưởng đến security. Đặt extension vào schema phù hợp giúp quản lý namespace, nhưng không thay thế việc kiểm soát quyền EXECUTE/USAGE và nguồn gốc package.

Bài học thuộc chương **Mở rộng** của module **Database Engine Relational PostgreSQL**. Nội dung đi từ cấu trúc package, control file và version scripts tới CREATE EXTENSION, schema, dependencies, ALTER EXTENSION UPDATE, quản lý objects, backup/restore, upgrade compatibility và vận hành extension trong production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích extension đóng gói những đối tượng PostgreSQL nào và khác gì với schema.
- Phân biệt extension package trên server với extension được cài trong database.
- Nhận biết control file, installation script, update script và shared library.
- Dùng pg_available_extensions, pg_available_extension_versions và pg_extension để kiểm tra trạng thái.
- Thực hiện CREATE EXTENSION với schema/version phù hợp.
- Hiểu relocatable, schema cố định, trusted và superuser requirements.
- Kiểm soát quyền, search_path và extension dependencies.
- Nâng cấp extension bằng ALTER EXTENSION UPDATE.
- Hiểu update paths, version labels và các bước migration SQL.
- Quản lý SET SCHEMA, ADD/DROP object và DROP EXTENSION.
- Xử lý extension config tables, pg_dump/restore và major PostgreSQL upgrades.
- Lập inventory, kiểm tra compatibility và xây dựng extension lifecycle runbook.

## 2. Extension là gì?

Extension là một đơn vị được PostgreSQL quản lý trong catalog, đại diện cho các database objects được cài từ một package extension.

### 2.1. Một tập objects có quan hệ

Extension có thể cung cấp functions, types, operators, aggregates, casts, tables, views, indexes, operator classes, procedural languages hoặc các objects khác tùy package.

### 2.2. Một tên và một phiên bản được đăng ký

Sau khi cài đặt, PostgreSQL ghi tên extension, version, schema liên kết và owner trong catalog pg_extension. Extension có thể được kiểm tra bằng SQL.

### 2.3. Dependency tracking

Các objects được extension quản lý có dependency tới extension. Điều này cho phép PostgreSQL biết chúng thuộc cùng một đơn vị cài đặt và xử lý khi update/drop.

### 2.4. Extension không phải schema

Schema là namespace chứa objects. Extension là package/lifecycle unit quản lý một tập objects; objects của extension có thể nằm trong một hoặc nhiều schemas tùy thiết kế.

### 2.5. Extension không phải database-wide package registry

Một package có thể hiện diện trên server, nhưng phải CREATE EXTENSION trong từng database cần dùng. Mỗi database có catalog entry và extension version riêng.

## 3. Hai lớp: package trên server và installation trong database

Để dùng extension, cần cả file package và catalog installation.

~~~text
PostgreSQL server installation
  ├── extension control file
  ├── install SQL script(s)
  ├── update SQL script(s)
  └── optional shared library (.so / .dll)
             |
             | CREATE EXTENSION
             v
Database catalog
  ├── pg_extension row
  ├── extension member objects
  └── dependency records
~~~

### 3.1. Package files

Control files và SQL scripts thường nằm trong thư mục extension thuộc PostgreSQL shared data directory. Shared libraries nằm trong thư mục library của PostgreSQL.

### 3.2. SQL-only extension

Extension chỉ chứa SQL có thể không cần shared library. Package vẫn cần control file và installation/update scripts.

### 3.3. C extension

Extension có C functions thường cần shared library được build cho PostgreSQL major version/ABI phù hợp. Control/SQL files không thể thay thế binary.

### 3.4. Cài package không đồng nghĩa cài database objects

Cài OS package hoặc copy extension files chỉ làm extension available trên server. CREATE EXTENSION mới tạo objects và catalog record trong database.

### 3.5. Cài trong một database không lan sang database khác

Nếu ứng dụng có nhiều databases, mỗi database phải được cài extension riêng. Kiểm kê theo database, không chỉ theo cluster.

## 4. Các thành phần của extension package

Một package thường có control file và một hay nhiều SQL scripts.

### 4.1. Control file

File tên extension.control mô tả metadata và installation behavior: default version, comment, schema, relocatability, privileges và dependencies.

### 4.2. Installation script

File có tên dạng extension--version.sql tạo objects cho một version cụ thể. Đây là nội dung được chạy khi CREATE EXTENSION chọn version đó.

### 4.3. Update scripts

Files dạng extension--oldversion--newversion.sql mô tả thay đổi cần áp dụng khi nâng cấp giữa các versions.

### 4.4. Shared library

C extension có thể cung cấp file .so trên Unix-like systems hoặc .dll trên Windows. SQL functions tham chiếu library qua MODULE_PATHNAME/control metadata.

### 4.5. Documentation và package metadata

OS package có thể cung cấp README, upgrade notes, license và build metadata. Các file này hỗ trợ vận hành nhưng không phải lúc nào cũng được PostgreSQL catalog lưu lại.

## 5. Control file

Control file cho PostgreSQL biết extension có thể cài như thế nào và version nào là mặc định.

Ví dụ minh họa một control file:

~~~ini
comment = 'Example extension'
default_version = '1.2'
module_pathname = '$libdir/example'
relocatable = true
superuser = true
~~~

### 5.1. default_version

Chỉ định version được chọn nếu CREATE EXTENSION không ghi VERSION. Không có nghĩa extension sẽ tự nâng cấp mỗi khi package mới được cài.

### 5.2. comment

Mô tả ngắn về extension, được hiển thị trong metadata như pg_available_extensions.

### 5.3. module_pathname

Cung cấp token/path để installation scripts tham chiếu shared library. SQL scripts thường dùng placeholder MODULE_PATHNAME trong CREATE FUNCTION.

### 5.4. relocatable

Cho biết extension có thể được cài/chuyển sang schema do người dùng chọn hay không. Giá trị này phải phù hợp với thiết kế scripts và object dependencies.

### 5.5. superuser và trusted

superuser điều khiển yêu cầu superuser khi cài. trusted cho phép user có CREATE privilege trên database cài extension theo trusted-installation rules; chỉ package được thiết kế an toàn mới nên khai báo trusted.

## 6. Các metadata khác trong control file

Ngoài các trường thường gặp, control file có thể mô tả requirements và installation details.

### 6.1. requires

Liệt kê các extensions phụ thuộc. PostgreSQL có thể cài dependencies theo thứ tự phù hợp khi sử dụng CASCADE nếu package versions tương thích.

### 6.2. schema

Chỉ định schema cài đặt cố định cho extension không relocatable hoặc có schema requirement. Không thể tự ý chọn schema khác nếu control file yêu cầu schema cụ thể.

### 6.3. directory

Chỉ định thư mục con chứa extension scripts trong sharedir/extension. Mặc định thường là thư mục extension tiêu chuẩn.

### 6.4. encoding

Có thể giới hạn encoding database mà extension scripts hỗ trợ. Kiểm tra control metadata khi extension không available trong database encoding hiện tại.

### 6.5. Per-version control files

Package có thể có control files cho các version cụ thể với metadata override. Khi điều tra version behavior, xem cả base control file và version-specific metadata nếu package cung cấp.

## 7. Installation scripts

Installation script tạo objects thuộc extension trong database.

~~~sql
-- Example extension--1.2.sql
CREATE FUNCTION example_add(integer, integer)
RETURNS integer
AS 'MODULE_PATHNAME', 'example_add'
LANGUAGE C
IMMUTABLE
STRICT;
~~~

### 7.1. File naming

Script version ban đầu thường có tên extension--version.sql. Version label là chuỗi do extension author định nghĩa; không nhất thiết theo semantic versioning.

### 7.2. Objects thuộc extension

CREATE EXTENSION chạy script và đăng ký các objects được tạo như thành viên extension thông qua dependency metadata.

### 7.3. Schema substitution

Extension scripts có thể dùng token như @extschema@ để tham chiếu schema đích. Không hard-code public nếu package cần hỗ trợ schema tùy chọn.

### 7.4. Search path safety

Script cần schema-qualify references quan trọng và tránh phụ thuộc vào search_path không kiểm soát. Extension installation là privileged operation và phải được xem như code execution trong database.

### 7.5. Transaction behavior

CREATE EXTENSION thường thực hiện cài đặt theo một transaction. Một số thao tác SQL đặc biệt không được phép trong transaction blocks nên extension author phải thiết kế scripts phù hợp với extension mechanism.

## 8. Update scripts và version graph

Nâng cấp extension dùng update scripts thay vì chạy lại installation script.

Ví dụ package có thể chứa:

~~~text
example.control
example--1.0.sql
example--1.0--1.1.sql
example--1.1--1.2.sql
example--1.0--1.2.sql
~~~

### 8.1. Source và target version

Tên update script xác định version bắt đầu và version kết thúc. Nội dung chuyển schema/objects từ source state sang target state.

### 8.2. Direct update path

Nếu có script 1.0--1.2.sql, PostgreSQL có thể dùng đường nâng cấp trực tiếp từ 1.0 tới 1.2.

### 8.3. Multi-step path

Nếu không có direct script, PostgreSQL có thể tìm đường qua 1.1 nếu các scripts cần thiết tồn tại.

### 8.4. Version labels

Version labels là identifiers do package author đặt. Không suy ra thứ tự chỉ bằng so sánh số hoặc chuỗi; dùng PostgreSQL update path metadata.

### 8.5. Thiếu update path

Nếu không có đường nâng cấp từ version đang cài tới target, ALTER EXTENSION UPDATE không thể tự suy ra migration. Cần package/script hỗ trợ hoặc kế hoạch migration riêng từ vendor/author.

## 9. Extension catalog và các view kiểm tra

PostgreSQL cung cấp views để phân biệt extension available trên server với extension đã cài trong database.

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 9.1. pg_available_extensions

Liệt kê extensions có package/control files được PostgreSQL nhận diện trong server installation, cùng default và installed versions cho current database.

### 9.2. pg_available_extension_versions

Liệt kê versions có sẵn và metadata như superuser, trusted, relocatable, schema và requires.

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

### 9.3. pg_extension

Liệt kê extensions đã cài trong current database:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS extension_schema,
    extrelocatable
FROM pg_extension
ORDER BY extname;
~~~

### 9.4. Per-database scope

Các views phản ánh database hiện tại. Muốn kiểm kê cluster-wide, phải kết nối từng database hoặc dùng inventory automation.

### 9.5. Package availability không đảm bảo runtime compatibility

Một extension xuất hiện trong pg_available_extensions không chứng minh shared library load được hoặc extension tương thích với workload/version. Cần install/test trong staging.

## 10. Kiểm tra extension update paths

Function pg_extension_update_paths cho biết các update paths mà PostgreSQL nhận diện từ scripts hiện có.

~~~sql
SELECT
    source,
    target,
    path
FROM pg_extension_update_paths('example')
ORDER BY source, target;
~~~

### 10.1. Path metadata

Path cho biết chuỗi version transitions PostgreSQL có thể sử dụng. NULL path thường chỉ ra không có đường update hợp lệ giữa cặp versions đó.

### 10.2. Kiểm tra trước maintenance

Kiểm tra source version hiện tại và target version dự định trước khi chạy ALTER EXTENSION UPDATE.

### 10.3. Direct và indirect paths

Một update path có thể là một script direct hoặc chuỗi nhiều bước. Số lượng scripts và operations quyết định thời gian/locks.

### 10.4. Scripts trên filesystem

SQL scripts phải hiện diện trong đúng PostgreSQL installation. Cài package mới có thể bổ sung update path nhưng không tự thực thi nó.

### 10.5. Không sửa catalog để giả lập version

Không UPDATE trực tiếp pg_extension.extversion. Dùng ALTER EXTENSION UPDATE để objects và version metadata được thay đổi nhất quán.

## 11. CREATE EXTENSION cơ bản

CREATE EXTENSION cài đặt package vào database hiện tại.

~~~sql
CREATE EXTENSION hstore;
~~~

### 11.1. Default version

Nếu bỏ VERSION, PostgreSQL dùng default_version trong control file. Ghi rõ version khi deployment cần pin chính xác.

### 11.2. IF NOT EXISTS

~~~sql
CREATE EXTENSION IF NOT EXISTS hstore;
~~~

IF NOT EXISTS tránh lỗi khi extension đã tồn tại, nhưng không xác nhận installed version hay schema đúng như mong muốn.

### 11.3. VERSION cụ thể

~~~sql
CREATE EXTENSION hstore VERSION '1.8';
~~~

Version phải available và có installation script phù hợp. Pin version giúp migration reproducible.

### 11.4. SCHEMA cụ thể

~~~sql
CREATE EXTENSION hstore WITH SCHEMA extensions;
~~~

Chỉ hoạt động khi extension hỗ trợ schema selection/relocation phù hợp và schema đã tồn tại.

### 11.5. CASCADE

~~~sql
CREATE EXTENSION extension_name CASCADE;
~~~

CASCADE cho phép cài các required extensions còn thiếu theo dependencies. Review dependency tree và package availability trước khi dùng.

## 12. CREATE EXTENSION và quyền cần thiết

Quyền cài đặt phụ thuộc metadata của extension và quyền trên database/schema.

### 12.1. CREATE privilege trên database

User thông thường cần quyền CREATE trên database để cài trusted extension; package không trusted hoặc yêu cầu superuser sẽ cần quyền cao hơn.

### 12.2. Superuser requirement

Control file có thể khai báo superuser=true. Nhiều extensions cần quyền cao vì tạo C functions, access privileged facilities hoặc thực thi script có security implications.

### 12.3. Trusted extension

trusted=true cho phép role có CREATE privilege trên database cài extension theo trusted extension rules. Script được thực thi với elevated installation context nhưng objects được sở hữu theo invoking user semantics của trusted install.

### 12.4. Schema privileges

User cần quyền phù hợp để tạo objects trong target schema; schema ownership/CREATE grants phải được thiết kế trước.

### 12.5. Least privilege

Không cấp superuser thường trực cho application chỉ để cài extension. Dùng DBA/migration role có thời hạn và audit, sau đó ứng dụng chỉ nhận privileges cần thiết.

## 13. Trusted extensions và security

Trusted là cam kết của extension package rằng cơ chế cài đặt an toàn cho user không phải superuser trong điều kiện được tài liệu hóa.

### 13.1. Không tự gắn trusted

Extension author phải xem xét SQL scripts, functions, file access, external calls và privilege boundaries trước khi đánh dấu trusted.

### 13.2. Installation scripts chạy với quyền cao

Trusted installation có special execution semantics. Một script lỗi có thể tạo objects với quyền/ownership không như mong muốn; chỉ dùng package từ nguồn tin cậy.

### 13.3. Extension update scripts cũng là code

ALTER EXTENSION UPDATE thực thi SQL migration scripts. Kiểm tra package source/release notes và test trên staging.

### 13.4. C functions

C shared libraries chạy trong PostgreSQL server process. Bug hoặc malicious code có thể ảnh hưởng toàn server/host theo privileges của process.

### 13.5. Security review

Inventory extensions, versions, package sources, owners, privileges, shared libraries và update cadence. Xem xét vulnerability advisories trước upgrade.

## 14. Chọn schema cài đặt

Schema là namespace cho extension objects và ảnh hưởng cách ứng dụng gọi chúng.

### 14.1. Schema riêng

Một schema như extensions giúp tách extension functions/types khỏi application tables và giảm clutter trong public.

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION hstore WITH SCHEMA extensions;
~~~

### 14.2. Schema public

Nhiều extension mặc định được cài vào public hoặc schema do control file chỉ định. Public tiện nhưng cần kiểm soát CREATE privilege và search_path.

### 14.3. Schema đã tồn tại

Tạo schema và thiết lập owner/grants trước. Không dựa vào CREATE EXTENSION để tạo một namespace với security policy bất ngờ.

### 14.4. Schema qualification

Ứng dụng nên gọi extension functions/types bằng schema-qualified names nếu search_path có thể thay đổi giữa sessions.

### 14.5. Nhiều extensions cùng schema

Có thể cài nhiều extension trong một schema nếu package hỗ trợ và không có object-name conflicts. Schema riêng cho từng extension giúp cô lập namespace nhưng làm quản lý search_path phức tạp hơn.


## 15. Relocatable và non-relocatable extensions

Khả năng di chuyển schema được quyết định bởi control file và cách extension scripts tạo objects.

### 15.1. Relocatable extension

Control file đặt relocatable=true. User có thể chọn schema khi cài và trong một số điều kiện có thể chuyển toàn bộ extension sang schema khác.

### 15.2. Non-relocatable extension

Control file đặt relocatable=false hoặc schema cố định. Extension có thể phụ thuộc vào schema cụ thể, nhiều schemas hoặc object references khiến việc di chuyển không an toàn.

### 15.3. CREATE với schema

Với relocatable extension, có thể dùng WITH SCHEMA để chọn namespace. Với non-relocatable extension, schema chỉ được chỉ định nếu phù hợp với schema mà control file yêu cầu.

### 15.4. Không suy đoán từ tên extension

Không phải extension nào cũng cài được vào schema tùy chọn. Kiểm tra relocatable/schema trong pg_available_extension_versions và tài liệu package.

### 15.5. Thiết kế từ đầu

Chọn schema, owner, grants và search_path trước khi cài. Chuyển schema về sau có thể cần lock và ảnh hưởng application references.

## 16. Search path và namespace security

search_path ảnh hưởng cách PostgreSQL phân giải tên functions, types, operators và relations.

### 16.1. Tránh phụ thuộc public mặc định

Ứng dụng dùng extension trong schema riêng nên gọi schema-qualified names hoặc cấu hình search_path rõ ràng.

### 16.2. Không cho untrusted users CREATE trong schema trên search_path

Nếu user không tin cậy có thể tạo objects trong schema nằm trước schema tin cậy, họ có thể shadow function/type names và gây hành vi không mong muốn.

### 16.3. Schema owner

Chỉ cấp CREATE trên extension schema cho DBA/deployment role cần thiết. Runtime application thường chỉ cần USAGE và quyền cần thiết trên objects.

### 16.4. Function privileges

Cài extension không đồng nghĩa mọi role nên có quyền EXECUTE mọi function. Review default privileges và function grants, đặc biệt functions truy cập file/network/OS.

### 16.5. Kiểm tra search_path

~~~sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
~~~

Đánh giá kết quả theo application role, không chỉ admin session.

## 17. Extension ownership và object membership

PostgreSQL theo dõi objects thuộc extension qua dependency records.

### 17.1. Extension owner

pg_extension.extowner cho biết role sở hữu extension. Owner ảnh hưởng quyền ALTER/DROP extension và quản trị metadata.

### 17.2. Member objects

Các objects được tạo bởi extension scripts được gắn dependency tới extension. Khi extension update/drop, PostgreSQL biết objects nào thuộc package.

### 17.3. Dependency type

Trong pg_depend, dependency type 'e' biểu thị extension membership. Đây là internal dependency mechanism; không sửa trực tiếp catalogs.

### 17.4. Không drop member object tùy tiện

PostgreSQL thường từ chối DROP object là thành viên extension. Dùng ALTER EXTENSION DROP object nếu muốn tách object khỏi package, sau đó mới quản lý object riêng.

### 17.5. Extension owner và object owners

Không giả định thay owner của extension tự động đổi owner của mọi member objects. Kiểm tra object ownership/privileges riêng nếu cần thay đổi security model.

## 18. Kiểm tra objects thuộc extension

Có thể tra pg_depend kết hợp pg_extension để xem objects được extension quản lý.

~~~sql
SELECT
    e.extname,
    e.extversion,
    d.classid::regclass AS catalog,
    d.objid,
    d.objsubid,
    d.refclassid::regclass AS referenced_catalog,
    d.deptype
FROM pg_depend AS d
JOIN pg_extension AS e
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, catalog::text, d.objid;
~~~

### 18.1. Object catalog

classid xác định catalog chứa object, chẳng hạn pg_class, pg_proc hoặc pg_type.

### 18.2. Object identity

objid là OID trong catalog tương ứng. Dùng các system functions như pg_describe_object để hiển thị tên dễ đọc.

~~~sql
SELECT
    e.extname,
    pg_describe_object(d.classid, d.objid, d.objsubid) AS member_object
FROM pg_depend AS d
JOIN pg_extension AS e
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, member_object;
~~~

### 18.3. Catalog query phụ thuộc version

Internal catalogs và object classes có thể thay đổi theo major version. Dùng query để inspect, không dùng nó thay API DDL chính thức.

### 18.4. Không update pg_depend trực tiếp

Thay đổi dependency catalog thủ công có thể làm extension update/drop không nhất quán hoặc khiến database catalog corruption.

### 18.5. Inventory trước migration

Lưu extension name/version/schema/owner và member objects cần thiết trước upgrade hoặc restore rehearsal.

## 19. Extension dependencies

Extension có thể khai báo required extensions trong control file.

### 19.1. requires metadata

Control file liệt kê tên các extensions mà package cần. PostgreSQL kiểm tra dependency khi cài đặt.

### 19.2. CREATE CASCADE

CREATE EXTENSION ... CASCADE cho phép cài dependencies còn thiếu. Không dùng CASCADE nếu chưa biết package nào sẽ được cài thêm.

### 19.3. Version compatibility

Dependency name có thể được yêu cầu nhưng versions vẫn cần tương thích. Đọc extension release notes và update scripts.

### 19.4. Dependency chain

Một extension có thể phụ thuộc extension khác, tạo chain nhiều lớp. Inventory toàn bộ graph trước khi remove/upgrade package.

### 19.5. Drop dependency

Không thể xóa một extension đang được extension khác yêu cầu nếu không xử lý dependency. CASCADE có thể drop cả extensions phụ thuộc và objects của chúng; đánh giá kỹ.

## 20. CREATE EXTENSION và IF NOT EXISTS

IF NOT EXISTS giúp migration scripts chạy lặp trong một số trường hợp, nhưng có thể che giấu state drift.

### 20.1. Không xác nhận version

Nếu extension đã cài version cũ, CREATE EXTENSION IF NOT EXISTS không nâng cấp nó. Dùng ALTER EXTENSION UPDATE riêng.

### 20.2. Không xác nhận schema

Nếu extension đã tồn tại ở schema khác với kỳ vọng, IF NOT EXISTS vẫn chỉ đưa notice. Kiểm tra extnamespace.

### 20.3. Không xác nhận package integrity

Lệnh thành công hoặc notice không chứng minh shared library, binary package và extension scripts là artifacts đúng nguồn.

### 20.4. Migration idempotency

Dùng IF NOT EXISTS cho bootstrap có kiểm soát, sau đó assert version/schema/owner để phát hiện drift.

### 20.5. Failure handling

Nếu CREATE EXTENSION fail giữa installation, transaction semantics thường rollback changes. Xem server log và catalog state trước khi retry.


## 21. ALTER EXTENSION UPDATE

ALTER EXTENSION UPDATE áp dụng update scripts để chuyển extension đã cài sang version khác.

~~~sql
ALTER EXTENSION hstore UPDATE;
~~~

### 21.1. Default target

Nếu bỏ TO, PostgreSQL dùng default_version có sẵn trong package hiện tại.

### 21.2. Target cụ thể

~~~sql
ALTER EXTENSION hstore UPDATE TO '1.8';
~~~

Target version phải có update path từ version đang cài.

### 21.3. Cập nhật từng extension

ALTER EXTENSION UPDATE chỉ nâng cấp extension được chỉ định. Không tự động nâng cấp mọi extension trong database.

### 21.4. Version không đổi

Nếu version đang cài đã là target/default, command có thể báo không cần update. Kiểm tra installed_version và output.

### 21.5. Không sửa extversion trực tiếp

Chỉ ALTER EXTENSION UPDATE mới chạy migration scripts và cập nhật membership/dependencies theo lifecycle. UPDATE catalog column bằng SQL là không an toàn.

## 22. Update script thực hiện gì?

Update script là migration giữa hai extension versions.

### 22.1. Thay đổi functions

Script có thể CREATE OR REPLACE FUNCTION, thay signatures hoặc chuyển implementation sang library mới.

### 22.2. Thay đổi types/operators

Có thể thêm/sửa types, casts, operators và operator classes. Các thay đổi này có thể ảnh hưởng application SQL và query plans.

### 22.3. Chuyển đổi extension data

Nếu extension có tables/configuration data, update script có thể transform dữ liệu. Cần đánh giá duration, locks và rollback semantics.

### 22.4. Dependency changes

Script có thể add/drop objects hoặc thay dependencies giữa các extension objects. Extension author phải duy trì ownership/dependency metadata đúng.

### 22.5. Không chạy lại install script

Không chạy installation script version mới bằng psql để giả lập update. Nó có thể tạo duplicate objects hoặc bỏ qua migration steps.

## 23. Update path và kiểm tra trước khi nâng cấp

Trước khi update, xác định installed version, available target và path.

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
WHERE name = 'hstore';

SELECT source, target, path
FROM pg_extension_update_paths('hstore')
ORDER BY source, target;
~~~

### 23.1. Source version

Lấy từ pg_extension.extversion. Đây là trạng thái thực tế đang được cài trong database.

### 23.2. Target version

Lấy từ pg_available_extension_versions hoặc default_version. Đừng giả định package version mới luôn là version target phù hợp.

### 23.3. Missing path

Nếu path NULL, kiểm tra package files, version-specific scripts và release notes. Có thể cần nâng qua intermediate version nếu path được hỗ trợ.

### 23.4. Test trên clone

Chạy update trên database clone với data size/extensions tương đương. Ghi duration, locks, errors và query behavior sau update.

### 23.5. Production sequencing

Chọn window phù hợp, pause incompatible workloads nếu cần và backup/recovery point theo change policy trước update có rủi ro.

## 24. ALTER EXTENSION SET SCHEMA

Một extension relocatable có thể được chuyển sang schema khác bằng ALTER EXTENSION SET SCHEMA.

~~~sql
ALTER EXTENSION hstore SET SCHEMA extensions;
~~~

### 24.1. Relocatable requirement

Extension phải được khai báo relocatable. Không thể dùng lệnh này để ép non-relocatable extension di chuyển.

### 24.2. Member objects cùng schema

Các objects thuộc extension phải đáp ứng điều kiện relocation; nếu member objects nằm trong schema khác hoặc có cấu trúc không phù hợp, thao tác có thể bị từ chối.

### 24.3. Schema destination

Schema đích phải tồn tại và quyền/ownership phải phù hợp. Kiểm tra object names conflicts trước khi chuyển.

### 24.4. Application references

Schema-qualified references, search_path, functions/views và prepared statements có thể cần cập nhật. Một số applications dùng unqualified names sẽ thay behavior.

### 24.5. Kiểm tra sau relocation

Xem extnamespace, object schemas, grants và application smoke tests. Chuyển schema không phải cách thay quyền sở hữu extension.

## 25. ALTER EXTENSION ADD và DROP object

Hai forms này thay đổi membership của object trong extension, không tạo hoặc xóa object.

~~~sql
ALTER EXTENSION extension_name ADD FUNCTION
    public.custom_helper(integer);

ALTER EXTENSION extension_name DROP FUNCTION
    public.custom_helper(integer);
~~~

### 25.1. ADD object

ADD ghi nhận một object đã tồn tại là member của extension. Object phải thuộc loại được hỗ trợ và thỏa điều kiện dependency/schema.

### 25.2. DROP object

DROP loại object khỏi extension membership. Object vẫn tồn tại trong database và có thể được quản lý riêng.

### 25.3. Khác với DROP FUNCTION

ALTER EXTENSION ... DROP FUNCTION không xóa function. DROP FUNCTION là lệnh xóa object thật và có thể cần xử lý dependencies.

### 25.4. Use cases

Có thể dùng khi extension được fork/customize hoặc muốn tách object do administrator bổ sung khỏi lifecycle của package.

### 25.5. Tránh sửa membership tùy tiện

Khi update extension, script có thể giả định object vẫn là member. Tách object có thể khiến future updates fail hoặc không cập nhật object đó.

## 26. DROP EXTENSION

DROP EXTENSION gỡ extension và các objects là thành viên của nó.

~~~sql
DROP EXTENSION hstore;
~~~

### 26.1. RESTRICT mặc định

Nếu objects bên ngoài extension phụ thuộc vào member objects, DROP EXTENSION mặc định RESTRICT sẽ từ chối thao tác.

### 26.2. CASCADE

~~~sql
DROP EXTENSION extension_name CASCADE;
~~~

CASCADE có thể xóa objects phụ thuộc và các extensions phụ thuộc. Đây là thao tác destructive, cần review dependency graph.

### 26.3. Schema không tự động bị xóa

DROP EXTENSION gỡ member objects, nhưng schema chứa chúng thường vẫn tồn tại. Xóa schema là quyết định riêng.

### 26.4. Data loss

Tables thuộc extension có thể chứa dữ liệu cần thiết. DROP EXTENSION có thể xóa cả tables và data đó; export/backup config data trước khi gỡ.

### 26.5. Không dùng DROP/CREATE để update

Drop/recreate có thể làm mất dữ liệu, privileges, dependent objects và configuration. Dùng ALTER EXTENSION UPDATE khi package hỗ trợ.

## 27. Extension configuration tables

Một số extensions cung cấp tables chứa dữ liệu cấu hình do administrator chỉnh sửa. Extension author có thể đánh dấu chúng để pg_dump lưu dữ liệu.

### 27.1. pg_extension_config_dump

Extension installation script có thể gọi pg_extension_config_dump(regclass, condition) để khai báo table data cần được dump cùng database.

~~~sql
SELECT pg_extension_config_dump(
    'public.example_settings',
    'WHERE setting_scope = ''user'''
);
~~~

### 27.2. Structure và data

CREATE EXTENSION tạo cấu trúc table; pg_dump lưu phần config data được khai báo. Khi restore, extension package phải có mặt để tạo objects trước khi data được nạp.

### 27.3. Condition filter

Condition có thể giới hạn rows được dump, ví dụ chỉ lưu user-modified configuration thay vì built-in defaults.

### 27.4. Không phải mọi extension table đều được dump như application table

Extension member tables không mặc nhiên được dump toàn bộ data. Xem extension documentation và config dump registration.

### 27.5. Kiểm tra restore

Thử dump/restore trên staging và xác nhận extension version, config table structure, retained rows và object dependencies.

## 28. Backup và restore database có extensions

Backup phải tái tạo cả extension package requirements lẫn database installation state.

### 28.1. pg_dump

pg_dump lưu lệnh CREATE EXTENSION cho installed extensions thay vì dump lại toàn bộ member object definitions như objects do user tạo.

### 28.2. Package availability trên target

Trước restore, cài extension packages và shared libraries tương thích trên target PostgreSQL server. Nếu package thiếu, CREATE EXTENSION trong restore sẽ fail.

### 28.3. Version behavior

Restore có thể cần version tương thích với dump hoặc update path phù hợp. Kiểm tra target extension versions và release notes.

### 28.4. Roles và schemas

Tạo roles/owners/schema/privileges cần thiết theo restore order. Extension ownership và schema grants có thể ảnh hưởng việc CREATE EXTENSION.

### 28.5. Restore test

Restore vào isolated database/cluster, xác nhận extension versions, schemas, member objects, config data và application queries.

## 29. Major PostgreSQL upgrade và extension packages

Extension lifecycle là một phần riêng trong major upgrade.

### 29.1. Target-version packages

Cài extension packages được build cho PostgreSQL major version đích. C library binaries từ major version cũ thường không dùng trực tiếp được với server mới.

### 29.2. Control/SQL files

Đảm bảo target installation có control files, installation scripts và update scripts cần thiết cho extension versions.

### 29.3. pg_upgrade

pg_upgrade chuyển database cluster, nhưng extension package/binary compatibility và SQL extension version update là các tasks phải xử lý theo upgrade procedure.

### 29.4. ALTER EXTENSION UPDATE

Sau khi target server và packages sẵn sàng, chạy ALTER EXTENSION UPDATE cho các extensions cần nâng SQL-level version. Không giả định major upgrade tự update tất cả extensions.

### 29.5. Standby/HA nodes

Cài cùng package versions trên các nodes cần chạy PostgreSQL. Nếu node được promote nhưng thiếu shared library hoặc version mismatch, functions của extension có thể fail.

## 30. Shared preload libraries và extension initialization

Một số extensions cần cấu hình server trước khi CREATE EXTENSION.

### 30.1. shared_preload_libraries

Ví dụ pg_stat_statements cần được thêm vào shared_preload_libraries và PostgreSQL restart trước khi dùng đầy đủ functionality.

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

### 30.2. Restart requirement

shared_preload_libraries là setting cần restart. Kiểm tra pending_restart và thực hiện theo maintenance plan.

### 30.3. CREATE EXTENSION sau preload

Sau khi server restart và library được load, kết nối vào từng database cần statistics và chạy:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 30.4. Cluster-level setting, database-level installation

Preload cấu hình server/cluster, còn CREATE EXTENSION tạo SQL objects trong một database. Hai bước có scope khác nhau.

### 30.5. Extension-specific settings

Đọc documentation về GUCs, background workers, hooks, memory requirements và monitoring. Không phải extension nào cũng cần preload.


## 31. Cài đặt extension package ở cấp hệ điều hành

Các extension không có sẵn trong PostgreSQL distribution cần package phù hợp với OS, PostgreSQL version và architecture.

### 31.1. Kiểm tra PostgreSQL installation paths

pg_config cung cấp các thư mục mà PostgreSQL build/install sử dụng.

~~~bash
pg_config --version
pg_config --sharedir
pg_config --pkglibdir
pg_config --includedir-server
~~~

### 31.2. Extension control directory

Control files và SQL scripts thường được đặt dưới sharedir/extension hoặc directory do package/control metadata chỉ định.

### 31.3. Shared library directory

C extension libraries thường nằm dưới pkglibdir hoặc library path tương ứng. Tên file và ABI phải tương thích với server.

### 31.4. Package manager

Cài extension bằng package repository đáng tin cậy của OS/vendor hoặc build process đã kiểm soát. Tránh copy file rời từ một server không rõ build/version.

### 31.5. Restart và library loading

Nếu extension cần shared_preload_libraries hoặc module đã được load trong backend process, làm theo restart/reconnect requirements. Thay binary trên disk không đảm bảo mọi backend đang chạy tự load code mới.

## 32. Cài extension từ source

Một số extensions cần build từ source thay vì package có sẵn.

### 32.1. Source compatibility

Chọn source release tương thích với PostgreSQL major version, compiler, OS libraries và extension dependencies.

### 32.2. Build toolchain

C extension thường cần PostgreSQL server development headers, compiler, make/build system và các libraries ngoài.

### 32.3. pg_config đúng target

Khi build, bảo đảm pg_config trỏ tới PostgreSQL installation đích. Nếu máy có nhiều major versions, dùng sai pg_config có thể cài binary vào sai thư mục.

### 32.4. Reproducible build

Ghi source version/commit, build flags, compiler, dependency versions và artifact checksum. Build riêng cho mỗi target platform/major version khi cần.

### 32.5. Deployment consistency

Đưa control files, SQL scripts và shared libraries vào cùng release artifact/package. Cài đồng nhất trên primary, standby, replicas và DR nodes.

## 33. Extension inventory cho một database

Inventory giúp biết extension nào đang được cài, ai sở hữu và ở schema nào.

~~~sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS schema_name,
    e.extrelocatable,
    a.default_version,
    a.comment
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
LEFT JOIN pg_available_extensions AS a
  ON a.name = e.extname
ORDER BY e.extname;
~~~

### 33.1. Installed version

extversion là version SQL-level đang được cài trong database.

### 33.2. Default version

default_version phản ánh version package mặc định hiện có trên server. Nó có thể khác installed version.

### 33.3. Owner/schema

Ghi owner và namespace để phát hiện extensions được cài bằng role hoặc schema không đúng policy.

### 33.4. Availability gap

Nếu installed extension không xuất hiện trong pg_available_extensions, package files có thể thiếu hoặc server installation đã thay đổi. Không xóa catalog entry để che lỗi.

### 33.5. Inventory nhiều databases

Chạy query trên từng database và tổng hợp bên ngoài. Cluster có thể có extensions khác nhau giữa databases.

## 34. Extension package inventory trên server

Available extensions không đồng nghĩa đã cài trong database.

### 34.1. List available

~~~sql
SELECT name, default_version, comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 34.2. List all versions

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

### 34.3. Installed vs available

installed=true cho biết version đang cài trong current database. Nhiều versions có thể available cùng lúc nhưng chỉ một version của extension được cài trong database.

### 34.4. Missing package

Nếu extension không xuất hiện, kiểm tra OS package, sharedir path, file permissions, server process installation và logs. Restart không tự cài package còn thiếu.

### 34.5. Managed services

Cloud-managed PostgreSQL chỉ hỗ trợ một tập extensions và version được provider cho phép. Kiểm tra allowlist/parameter groups và service documentation.

## 35. Quy trình cài extension mới

Một deployment an toàn cần package, permissions, schema và test trước khi bật cho ứng dụng.

1. Xác định nhu cầu và extension package chính xác.
2. Kiểm tra source, license, security advisories và PostgreSQL compatibility.
3. Cài package vào đúng server installation và tất cả HA/DR nodes.
4. Kiểm tra control files, SQL scripts, shared libraries và available versions.
5. Xác định superuser/trusted requirements và dependencies.
6. Tạo schema/owner/grants nếu cần.
7. Áp dụng server settings/preload và restart nếu extension yêu cầu.
8. Chạy CREATE EXTENSION trong đúng database/version/schema.
9. Xác nhận catalog, objects, privileges và representative function behavior.
10. Cập nhật inventory, backup/restore runbook và monitoring.

### 35.1. Cài ở staging trước

Test extension trên PostgreSQL major version và OS giống production. Kiểm tra performance, locks, background workers và failure behavior.

### 35.2. Pin version

Trong migration/deployment artifact, ghi version rõ ràng khi reproducibility quan trọng.

### 35.3. Schema policy

Không để schema phụ thuộc implicit search_path nếu application cần namespace ổn định.

### 35.4. Post-install grants

Review object privileges; chỉ grant USAGE/EXECUTE/SELECT theo nhu cầu của application roles.

### 35.5. Operational readiness

Thêm extension vào inventory, patch schedule, backup/restore tests, HA node package list và security review cadence.


## 36. Quy trình nâng cấp extension

Nâng cấp extension cần phân biệt package deployment và SQL catalog migration.

1. Đọc release notes và compatibility matrix của extension.
2. Xác định current extversion trong từng database.
3. Cài target package/control/scripts/shared library lên server nodes.
4. Xem pg_available_extension_versions và pg_extension_update_paths.
5. Test ALTER EXTENSION UPDATE trên clone/staging.
6. Đánh giá locks, runtime, data migration, restart/preload requirements.
7. Backup/recovery point và lên maintenance/change window phù hợp.
8. Chạy ALTER EXTENSION UPDATE tới target version.
9. Kiểm tra extversion, objects, privileges, function behavior và query plans.
10. Theo dõi logs, application errors, replication và performance.

### 36.1. Package trước, SQL update sau

Nếu update scripts không tồn tại trên server, PostgreSQL không thể chạy update. Deploy package target trước khi ALTER EXTENSION.

### 36.2. Binary và SQL version

Shared library package version và SQL extension version có thể có lifecycle riêng. Làm theo vendor procedure để tránh SQL objects gọi binary API không tương thích.

### 36.3. Database-by-database

Nếu extension được cài trong nhiều databases, cập nhật từng database theo thứ tự/maintenance policy. Ghi rõ database nào đã hoàn tất.

### 36.4. Restart requirement

Nếu extension thay đổi preload library hoặc cần load binary mới, thực hiện restart theo yêu cầu. ALTER EXTENSION UPDATE không tự restart PostgreSQL.

### 36.5. Post-update validation

Test critical functions, operators, indexes, custom types, query plans, grants và background workers.

## 37. Extension compatibility matrix

Trước deployment cần xác nhận cả server, package, extension SQL version và dependencies.

| Dimension | Cần xác nhận |
|---|---|
| PostgreSQL major | Extension hỗ trợ target major? |
| PostgreSQL minor | Có bug fixes/requirements cụ thể? |
| OS/architecture | Package/binary đúng platform? |
| Shared library ABI | Build đúng target PostgreSQL? |
| Extension SQL version | Có install/update scripts cần thiết? |
| Dependencies | Required extensions/libraries có tương thích? |
| Collation/type | Có assumptions về ordering/types? |
| HA/DR | Mọi node có cùng package và settings? |
| Managed service | Provider có allow extension/version? |
| Application | SQL/API behavior có backward compatible? |

### 37.1. Không chỉ nhìn package version

Một OS package có thể được cài nhưng binary build sai PostgreSQL major hoặc dependency runtime bị thiếu.

### 37.2. Kiểm tra release notes

Đọc breaking changes, deprecated functions, renamed objects, new defaults và migration requirements.

### 37.3. Extension dependencies ngoài database

Một số extension phụ thuộc OS libraries, executable tools, locale packages hoặc external services. Cài SQL package chưa đủ.

### 37.4. Test rollback

Xác định package downgrade có được hỗ trợ không và SQL update có reversible path hay không. Không mặc định ALTER EXTENSION UPDATE có downgrade script.

### 37.5. Provider-specific behavior

Managed service có thể cấm shared library loading, superuser operations hoặc một số extension versions. Thiết kế theo capability thực tế.

## 38. Extension trên HA cluster

Extension packages và settings cần nhất quán trên nodes có thể chạy PostgreSQL.

### 38.1. Primary và standby

Standby replay WAL cho extension-created objects, nhưng khi promote, các functions có C library cần binary tương thích trên node mới.

### 38.2. Install packages đồng đều

Cài cùng compatible package versions trên primary, standbys và DR nodes trước khi failover có thể xảy ra.

### 38.3. Shared preload settings

Nếu extension cần preload, cấu hình nhất quán trên các nodes. Sau failover, node mới phải có setting/binary cần thiết.

### 38.4. Extension SQL update

ALTER EXTENSION UPDATE chạy trên primary/database. Standbys nhận catalog/object changes qua WAL; không chạy cùng SQL update độc lập trên physical standby.

### 38.5. Failover validation

Sau promote, kiểm tra library loading, function execution, background workers, logs và extension versions.

## 39. Extension và logical replication

Logical replication có thể tạo database objects/data nhưng không tự cài extension package trên subscriber.

### 39.1. Schema prerequisites

Tạo extension/schema/types/functions cần thiết ở subscriber theo deployment procedure trước khi replicated tables hoặc application queries phụ thuộc chúng.

### 39.2. DDL propagation

Logical replication không tự replicate mọi DDL. Extension install/update phải được điều phối riêng ở publisher/subscriber.

### 39.3. Data types/operators

Nếu replicated tables dùng extension types/operators, subscriber phải có definitions tương thích trước khi apply changes.

### 39.4. Version alignment

Publisher và subscriber có thể chạy versions khác nhau trong upgrade scenario, nhưng logical data representation và function semantics phải tương thích.

### 39.5. Cutover

Trước chuyển application sang subscriber, kiểm tra extension inventory, versions, schema, functions, operators và indexes.

## 40. Extension trong backup/PITR và disaster recovery

Recovery target cần package và extension state tương thích với database backup/WAL.

### 40.1. Base backup không đóng gói OS extension binaries

Physical backup chứa data directory, nhưng không thay thế việc cài đúng server binaries/shared libraries trên restore host.

### 40.2. WAL replay

Nếu WAL chứa catalog/object changes từ extension update, target cần có compatible server binaries/packages để database khởi động và functions hoạt động sau recovery.

### 40.3. PITR target

Restore về thời điểm trước/sau extension update cần package/runtime tương thích với state đó. Chuẩn bị version inventory cho recovery point.

### 40.4. DR rehearsal

Restore physical/logical backups lên DR environment và test extension functions, C libraries, preload settings, config data và application queries.

### 40.5. Recovery documentation

Ghi package repository/artifact, version, checksum, installation steps, settings và SQL extension versions cùng backup metadata.


## 41. Ví dụ: cài extension hstore vào schema riêng

Ví dụ minh họa một extension SQL/data type được cài trong database ứng dụng.

### 41.1. Kiểm tra availability

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';
~~~

### 41.2. Tạo schema

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions
AUTHORIZATION db_owner;
~~~

### 41.3. Cài extension

~~~sql
CREATE EXTENSION hstore
WITH SCHEMA extensions
VERSION '1.8';
~~~

Version ví dụ phải tồn tại trong package của server. Nếu package có version khác, chọn version thực tế được hỗ trợ.

### 41.4. Kiểm tra installation

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS schema_name,
    extrelocatable
FROM pg_extension
WHERE extname = 'hstore';
~~~

### 41.5. Kiểm tra function/type usage

Dùng schema-qualified names trong application SQL khi cần tránh phụ thuộc search_path. Cấp quyền phù hợp trên schema và objects theo policy.

## 42. Ví dụ: cài pg_stat_statements

pg_stat_statements minh họa sự khác biệt giữa server-level preload và database-level extension installation.

### 42.1. Cấu hình server

Thêm library vào shared_preload_libraries trong configuration source được quản lý:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

Nếu setting đã chứa libraries khác, giữ chúng trong danh sách thay vì ghi đè.

### 42.2. Restart PostgreSQL

Setting này cần restart. Kiểm tra pending_restart và thực hiện theo maintenance procedure.

### 42.3. Cài trong database

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Lặp lại trong mỗi database cần sử dụng view/function của extension.

### 42.4. Cấu hình tracking

Thiết lập pg_stat_statements.track và các settings liên quan theo workload/privacy/overhead requirements.

### 42.5. Validate

Chạy query trên pg_stat_statements, xác nhận permissions, query tracking và monitoring. Extension đã cài nhưng preload thiếu có thể không hoạt động như mong đợi.

## 43. Ví dụ: kiểm tra và nâng cấp extension

Giả sử database đang dùng version 1.0 và server package cung cấp version 1.2.

### 43.1. Đọc installed version

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'example';
~~~

### 43.2. Kiểm tra target version

~~~sql
SELECT name, version, installed
FROM pg_available_extension_versions
WHERE name = 'example'
ORDER BY version;
~~~

### 43.3. Kiểm tra update path

~~~sql
SELECT source, target, path
FROM pg_extension_update_paths('example')
WHERE source = '1.0'
  AND target = '1.2';
~~~

### 43.4. Test update

Trên clone/staging, chạy:

~~~sql
ALTER EXTENSION example UPDATE TO '1.2';
~~~

Ghi duration, locks, logs, object changes và application behavior.

### 43.5. Production update

Sau backup/approval/maintenance checks, chạy update trên đúng database. Kiểm tra pg_extension.extversion và smoke tests trước khi mở traffic.

## 44. Kiểm tra extension configuration tables

Catalog pg_extension có extconfig/extcondition để ghi nhận configuration tables và dump conditions.

~~~sql
SELECT
    extname,
    extconfig,
    extcondition
FROM pg_extension
WHERE extconfig IS NOT NULL;
~~~

### 44.1. extconfig

Lưu OIDs của tables được khai báo là extension configuration tables.

### 44.2. extcondition

Lưu conditions tương ứng để xác định rows cần dump, theo cơ chế extension config dump.

### 44.3. Data ownership

Extension có thể sở hữu table structure trong khi administrator/application quản lý configuration rows. Phân biệt package defaults với user-customized data.

### 44.4. Dump semantics

pg_dump sử dụng metadata này để lưu data cần thiết cho config tables. Không giả định mọi extension tables đều được dump data đầy đủ.

### 44.5. Restore validation

So sánh config rows trước/sau restore và test behavior của extension với cấu hình đã khôi phục.

## 45. Troubleshooting: extension không available

CREATE EXTENSION báo extension không có sẵn trong server installation.

### 45.1. Kiểm tra catalog availability

Query pg_available_extensions và pg_available_extension_versions trong đúng database.

### 45.2. Kiểm tra control file

Xác nhận extension.control có trong sharedir/extension hoặc directory được package cấu hình.

### 45.3. Kiểm tra đúng PostgreSQL installation

Server có thể chạy binary từ một installation trong khi package được cài vào installation khác. Dùng pg_config/service configuration để đối chiếu.

### 45.4. Package repository

Xác nhận OS package đúng PostgreSQL major version, OS release và architecture.

### 45.5. Managed service allowlist

Nếu dùng managed PostgreSQL, extension có thể không được provider hỗ trợ hoặc chưa được enable ở service configuration.

## 46. Troubleshooting: permission denied hoặc requires superuser

### 46.1. Đọc control metadata

Kiểm tra superuser và trusted trong pg_available_extension_versions.

### 46.2. Database CREATE privilege

Trusted extension vẫn yêu cầu invoking role có quyền CREATE trên database theo trusted extension rules.

### 46.3. Schema permissions

Kiểm tra schema tồn tại, owner và CREATE privilege phù hợp.

### 46.4. Dependencies

Extension có thể yêu cầu extensions khác đã được cài hoặc có package available. Xem requires metadata và dependency chain.

### 46.5. Dùng privileged deployment role

Nếu package yêu cầu superuser, thực hiện qua DBA-controlled deployment identity có audit. Không nâng quyền application role chỉ để cài extension.

## 47. Troubleshooting: schema conflict hoặc object already exists

Installation script có thể gặp object cùng tên đã tồn tại.

### 47.1. Inspect existing objects

Xác định object có phải do lần cài thủ công trước, package khác hoặc application tạo hay không.

### 47.2. Không drop ngay

Object có thể đang được application dùng hoặc có data. Ghi dependencies, owner và grants trước khi quyết định.

### 47.3. Chọn schema phù hợp

Nếu extension relocatable, có thể cài vào schema riêng đã chuẩn bị. Không dùng schema khác với requirement của non-relocatable package.

### 47.4. Resolve conflict có kiểm soát

Đổi tên/migrate custom objects hoặc dùng package-supported migration. Tránh xóa objects chỉ để làm CREATE EXTENSION thành công.

### 47.5. Retry sau khi hiểu state

Kiểm tra catalog và transaction rollback sau failed installation. Không giả định partial objects còn hay đã mất mà không inspect.

## 48. Troubleshooting: no update path hoặc update script failure

### 48.1. Kiểm tra source/target

Xác nhận installed version và requested target chính xác.

### 48.2. Kiểm tra update paths

Dùng pg_extension_update_paths và kiểm tra các SQL scripts có mặt trên filesystem.

### 48.3. Intermediate versions

Nếu chỉ có paths qua intermediate version, chọn đường mà package hỗ trợ. Không tự chạy scripts theo thứ tự đoán.

### 48.4. Update script error

Đọc server log và transaction state. ALTER EXTENSION UPDATE thường chạy migration trong transaction; nếu thất bại, command transaction rollback theo semantics, nhưng cần xác nhận catalog/version.

### 48.5. Vendor guidance

Một số releases yêu cầu bước manual trước/sau update. Làm theo upgrade notes thay vì sửa extversion hoặc dependency catalog.


## 49. Troubleshooting: shared library không load được

### 49.1. File missing

Kiểm tra library path, file permissions và package installation trên đúng node.

### 49.2. ABI mismatch

Binary build cho PostgreSQL major version khác có thể không load được. Rebuild/cài package target đúng major.

### 49.3. Missing OS dependency

Shared library có thể phụ thuộc system libraries không có trên host. Dùng OS package metadata/tools để xác định missing dependency.

### 49.4. Preload configuration

Nếu extension cần shared_preload_libraries, kiểm tra setting, pending_restart và startup logs.

### 49.5. HA consistency

Nếu primary có library nhưng standby/DR thiếu, failover có thể khiến functions fail. Kiểm tra mọi eligible nodes.

## 50. Quy trình gỡ extension

Gỡ extension cần đánh giá objects, dependent objects và configuration data.

1. Inventory extension version, schema, owner và dependencies.
2. Xác định applications/functions/tables đang dùng extension.
3. Backup/export extension config data và dependent application data.
4. Tháo references trong application/schema theo migration plan.
5. Kiểm tra dependency graph và chọn RESTRICT hay CASCADE.
6. Chạy DROP EXTENSION trong maintenance window nếu impact yêu cầu.
7. Xác nhận schema/object cleanup và application behavior.
8. Gỡ OS package/shared library chỉ khi không database/node nào còn cần.
9. Cập nhật inventory, HA/DR images và deployment manifests.

### 50.1. Ưu tiên RESTRICT

Dùng default RESTRICT để PostgreSQL báo các dependencies còn lại. Không dùng CASCADE chỉ để làm lệnh chạy qua.

### 50.2. Export data trước

Nếu extension tables chứa data cấu hình/nghiệp vụ, export trước khi drop. Member table data có thể bị xóa cùng extension.

### 50.3. Nhiều databases

Kiểm tra tất cả databases trước khi gỡ package khỏi server. Một database khác có thể vẫn cài extension.

### 50.4. Schema cleanup

Sau DROP EXTENSION, kiểm tra schema còn objects nào. Chỉ DROP SCHEMA khi xác nhận không có application objects cần giữ.

### 50.5. Package cleanup

OS package removal là bước riêng. Chỉ gỡ sau khi database catalog installations và HA/DR requirements đã được xử lý.

## 51. Extension governance và version policy

Extension cần được quản lý như một phần của software supply chain.

### 51.1. Approved list

Duy trì danh sách extensions được phép, owner, purpose, source repository/package và risk classification.

### 51.2. Version pinning

Ghi extension SQL version và OS package version. Tránh environment drift giữa staging/production/DR.

### 51.3. Security updates

Theo dõi CVEs/advisories và vendor releases. Xác định thời gian xử lý security update và test requirements.

### 51.4. Compatibility review

Mỗi PostgreSQL major upgrade cần extension compatibility matrix, package availability, update path và rehearsal.

### 51.5. Ownership and lifecycle

Chỉ định owner chịu trách nhiệm patch, upgrade, monitoring, backup/restore và decommission extension.

## 52. Những lỗi quản trị extension thường gặp

1. Nghĩ rằng cài OS package tự tạo extension objects trong database.
2. Nghĩ CREATE EXTENSION trong một database áp dụng cho mọi databases.
3. Chạy CREATE EXTENSION IF NOT EXISTS và bỏ qua version/schema drift.
4. Cài extension vào public mà không xem xét schema privileges/search_path.
5. Giả định mọi extension đều relocatable.
6. Cấp superuser cho application chỉ để cài extension.
7. Bỏ qua trusted/superuser metadata và package source.
8. Cài SQL scripts nhưng thiếu shared library.
9. Build C extension bằng pg_config của sai PostgreSQL major version.
10. Chỉ cài package trên primary, quên standby/DR nodes.
11. Cho rằng pg_upgrade tự nâng SQL version của mọi extension.
12. Chạy installation script mới thay cho ALTER EXTENSION UPDATE.
13. Sửa pg_extension.extversion hoặc pg_depend trực tiếp.
14. Không kiểm tra update path trước maintenance.
15. Giả định ALTER EXTENSION UPDATE có downgrade script.
16. Dùng CASCADE mà không xem dependency graph.
17. DROP EXTENSION mà không export configuration data.
18. Quên preload/restart requirement của extension.
19. Bỏ qua extension functions trong application smoke tests.
20. Không test dump/restore và disaster recovery với package tương ứng.

## 53. Bài tập thực hành

### Bài 1 — Khái niệm

Extension khác schema như thế nào?

**Đáp án:** Schema là namespace chứa objects; extension là package/lifecycle unit quản lý một tập objects.

### Bài 2 — Package

CREATE EXTENSION có tự cài OS package không?

**Đáp án:** Không; package files phải có sẵn trên server trước.

### Bài 3 — Database scope

Cài extension trong database A có làm database B dùng được ngay không?

**Đáp án:** Không; phải CREATE EXTENSION trong database B.

### Bài 4 — Control file

default_version có ý nghĩa gì?

**Đáp án:** Version mặc định được chọn khi CREATE EXTENSION không chỉ định VERSION.

### Bài 5 — Update scripts

File extension--1.0--1.1.sql dùng khi nào?

**Đáp án:** Chuyển extension từ version 1.0 sang 1.1.

### Bài 6 — Relocatable

relocatable=true cho phép điều gì?

**Đáp án:** Cho phép cài/chuyển extension trong schema theo các điều kiện relocation.

### Bài 7 — Trusted

trusted=true có nghĩa extension an toàn tuyệt đối không?

**Đáp án:** Không; đây là metadata do package author khai báo về trusted installation semantics, vẫn cần review nguồn và code.

### Bài 8 — Superuser

Vì sao extension có thể yêu cầu superuser?

**Gợi ý:** C functions, privileged operations hoặc scripts cần elevated permissions.

### Bài 9 — Availability

View nào liệt kê packages/versions available trên server?

**Đáp án:** pg_available_extensions và pg_available_extension_versions.

### Bài 10 — Installed state

Catalog nào lưu extension đã cài trong current database?

**Đáp án:** pg_extension.

### Bài 11 — CREATE IF NOT EXISTS

Lệnh này có nâng extension version cũ không?

**Đáp án:** Không; cần ALTER EXTENSION UPDATE.

### Bài 12 — Schema

Có thể dùng WITH SCHEMA cho mọi extension không?

**Đáp án:** Không; phụ thuộc relocatable và schema requirements.

### Bài 13 — Search path

Vì sao không cho untrusted user CREATE trong schema nằm trên search_path?

**Gợi ý:** Họ có thể shadow names của trusted objects.

### Bài 14 — Dependencies

requires trong control file làm gì?

**Đáp án:** Khai báo required extensions.

### Bài 15 — CASCADE install

CREATE EXTENSION ... CASCADE có thể làm gì?

**Đáp án:** Cài dependencies còn thiếu theo dependency metadata.

### Bài 16 — Update path

Function nào kiểm tra extension update paths?

**Đáp án:** pg_extension_update_paths(name).

### Bài 17 — ALTER UPDATE

ALTER EXTENSION UPDATE có tự update tất cả extensions không?

**Đáp án:** Không; chỉ extension được chỉ định.

### Bài 18 — SET SCHEMA

Điều kiện chính để ALTER EXTENSION SET SCHEMA?

**Đáp án:** Extension phải relocatable và member objects phải đáp ứng điều kiện relocation.

### Bài 19 — ADD/DROP object

ALTER EXTENSION DROP FUNCTION có xóa function không?

**Đáp án:** Không; chỉ bỏ membership khỏi extension.

### Bài 20 — DROP EXTENSION

DROP EXTENSION RESTRICT làm gì khi có dependent objects?

**Đáp án:** Từ chối drop nếu dependencies còn tồn tại.

### Bài 21 — Config tables

pg_extension_config_dump dùng để làm gì?

**Đáp án:** Đánh dấu extension configuration table data cần được pg_dump lưu.

### Bài 22 — Restore

Vì sao phải cài package trên target trước pg_restore?

**Đáp án:** Restore cần CREATE EXTENSION và target server cần control/SQL/shared library files.

### Bài 23 — Major upgrade

pg_upgrade có tự nâng SQL version mọi extension không?

**Đáp án:** Không; extension packages/binaries và ALTER EXTENSION UPDATE cần được xử lý theo procedure.

### Bài 24 — Preload

pg_stat_statements cần cấu hình gì trước CREATE EXTENSION để hoạt động đầy đủ?

**Đáp án:** Thêm vào shared_preload_libraries và restart server, sau đó CREATE EXTENSION trong database.

### Bài 25 — HA

Vì sao extension package cần có trên standby?

**Đáp án:** Node có thể được promote; C functions/shared libraries phải load được trên node mới.

### Bài 26 — Logical replication

Logical replication có tự replicate CREATE EXTENSION không?

**Đáp án:** Không; DDL/extension installation phải được điều phối riêng.

### Bài 27 — Missing library

SQL objects tồn tại nhưng C function báo library missing. Cần kiểm tra gì?

**Gợi ý:** Shared library package, path, ABI, dependencies và preload requirements.

### Bài 28 — Missing update path

ALTER EXTENSION UPDATE báo không có path. Nên làm gì?

**Đáp án:** Kiểm tra package scripts, source/target versions, intermediate paths và vendor guidance; không sửa catalog version.

### Bài 29 — Decommission

Vì sao nên dùng DROP EXTENSION RESTRICT trước CASCADE?

**Đáp án:** Để phát hiện dependent objects và tránh xóa ngoài dự kiến.

### Bài 30 — Lifecycle

Nêu các bước chính trong vòng đời extension.

**Gợi ý:** Approve/source, install package, inspect metadata, create/schema/privileges, monitor, update scripts/package, backup/restore, upgrade compatibility và decommission.


## 54. Checklist cài đặt và quản lý extension

- [ ] Extension có business/technical owner và purpose rõ?
- [ ] Package source, license, security advisories đã xem?
- [ ] PostgreSQL major/OS/architecture compatibility đã xác nhận?
- [ ] Control file, install/update scripts và shared library có đủ?
- [ ] Dependencies và trusted/superuser requirements đã hiểu?
- [ ] Schema, owner, search_path và grants đã thiết kế?
- [ ] Package đã được cài trên primary/standby/DR nodes?
- [ ] Preload/restart requirements đã thực hiện?
- [ ] CREATE EXTENSION đã chạy trong đúng databases/version/schema?
- [ ] Catalog/member objects/function behavior đã kiểm tra?
- [ ] Backup/restore config tables đã test?
- [ ] Extension inventory và patch policy đã cập nhật?

## 55. Checklist nâng cấp hoặc gỡ extension

### Trước nâng cấp

- [ ] Installed versions theo từng database đã inventory?
- [ ] Target package/shared library đã deploy trên mọi nodes?
- [ ] Update path từ source tới target đã kiểm tra?
- [ ] Release notes/dependencies/security changes đã review?
- [ ] Staging clone test và rollback boundary đã xác định?
- [ ] Backup/recovery point và maintenance window đã sẵn sàng?

### Sau nâng cấp

- [ ] ALTER EXTENSION UPDATE hoàn tất trên mọi database cần thiết?
- [ ] extversion/schema/owner/member objects đã xác nhận?
- [ ] Functions/types/operators/indexes đã smoke test?
- [ ] Preload/library logs và restart requirements đạt?
- [ ] Application queries/performance và replication đã kiểm tra?
- [ ] Inventory/version manifests đã cập nhật?

### Khi gỡ

- [ ] Application references và dependencies đã xử lý?
- [ ] Config/user data đã export?
- [ ] RESTRICT đã được dùng để kiểm tra dependencies?
- [ ] CASCADE chỉ được dùng sau impact review/approval?
- [ ] Mọi databases/nodes đã được kiểm tra trước khi gỡ package?

## 56. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| Extension | Đơn vị quản lý lifecycle của database objects |
| Schema | Namespace chứa objects |
| Control file | Metadata và install behavior |
| Installation script | Tạo objects cho một version |
| Update script | Migration giữa hai versions |
| Shared library | Binary code cho C functions |
| CREATE EXTENSION | Cài extension trong current database |
| IF NOT EXISTS | Không lỗi nếu extension đã tồn tại |
| VERSION | Chọn extension SQL version |
| SCHEMA | Chọn schema nếu package hỗ trợ |
| relocatable | Cho phép relocation theo điều kiện |
| trusted | Cho phép non-superuser install theo trusted rules |
| superuser | Yêu cầu privileged installer |
| requires | Extension dependencies |
| pg_available_extensions | Packages/default/installed version trong current DB context |
| pg_available_extension_versions | Versions và install metadata |
| pg_extension | Extensions đã cài trong current database |
| pg_depend | Object dependency/membership records |
| pg_extension_update_paths | Các đường update scripts có thể đi |
| ALTER EXTENSION UPDATE | Chạy migration scripts |
| ALTER EXTENSION SET SCHEMA | Di chuyển relocatable extension |
| ALTER EXTENSION ADD/DROP | Thay đổi object membership |
| DROP EXTENSION | Gỡ extension và member objects |
| pg_extension_config_dump | Đăng ký config table data cho dump |
| shared_preload_libraries | Nạp libraries khi PostgreSQL start |
| pg_config | Hiển thị build/install paths |
| pg_dump | Dump extension installation và config data |
| pg_upgrade | Major version upgrade tool |

## 57. Kết luận

**Extension là package có vòng đời riêng, kết hợp file cài đặt trên server với catalog objects trong từng database.** Control file xác định version mặc định, schema behavior, dependencies và privilege requirements; installation scripts tạo objects; update scripts chuyển từ version này sang version khác. Cài package ở OS chưa tạo objects trong database, và CREATE EXTENSION trong một database không cài extension cho các database còn lại.

Schema cần được chọn dựa trên relocatable metadata, ownership, search_path và application references. Trusted/superuser requirements là security boundary quan trọng; C shared libraries chạy trong server process nên package source, ABI, dependencies và patch cadence phải được quản lý như software supply chain. pg_available_extensions/versions cho biết package availability, pg_extension cho biết installed state và pg_extension_update_paths giúp xác nhận đường nâng cấp.

ALTER EXTENSION UPDATE là con đường chuẩn để chạy migration scripts. SET SCHEMA chỉ phù hợp với extension relocatable và điều kiện member objects; ADD/DROP object chỉ thay đổi membership; DROP EXTENSION có thể xóa member objects/data và CASCADE có thể xóa thêm dependencies. Backup/restore và major upgrade phải chuẩn bị packages, libraries, preload settings, config table data và SQL extension versions ở target.

Nguyên tắc vận hành: **kiểm tra package và compatibility trước, thiết kế schema/privileges khi cài, dùng update scripts cho version changes, giữ binaries đồng nhất trên HA/DR nodes và diễn tập restore trước khi coi extension là production-ready.**

