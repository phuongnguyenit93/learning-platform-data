# Tương thích extension khi sao lưu, phục hồi và nâng cấp PostgreSQL

Extension mở rộng PostgreSQL bằng SQL objects, types, functions, operators và đôi khi cả native libraries chạy trong backend process. Vì vậy, một database backup có thể giữ lại thông tin rằng extension đã được cài, nhưng chưa chắc đã chứa đủ package, shared library, configuration files và dữ liệu riêng của extension để khôi phục một hệ thống hoạt động hoàn chỉnh.

Khi sao lưu, phục hồi hoặc nâng cấp, cần phân biệt ba lớp:

1. **Extension package trên server:** control file, SQL installation/update scripts, shared libraries và dependencies do hệ điều hành hoặc nhà cung cấp cài đặt.
2. **Extension metadata và objects trong database:** extension name/version, ownership, schema và các objects được đánh dấu là thành viên của extension.
3. **Extension configuration/state data:** dữ liệu runtime hoặc cấu hình do extension lưu trong tables, files, external services hoặc catalog objects.

Các lớp này có vòng đời và cơ chế backup khác nhau. `pg_dump` có thể lưu lệnh tạo extension và một số configuration table data, nhưng không đóng gói native library. Physical backup giữ data files của cluster nhưng không tự bảo đảm OS packages, binaries hay các file nằm ngoài data directories được phục hồi.

Bài **“Tương thích extension khi sao lưu, phục hồi và nâng cấp”**, thuộc chương **Mở rộng** của module **Database Engine Relational PostgreSQL**, trình bày cách lập inventory, chọn backup method, chuẩn bị extension packages ở target, restore đúng thứ tự, nâng cấp extension SQL version, dùng `pg_upgrade`, kiểm tra HA và xác minh sau recovery.

> **Nguyên tắc:** backup database và backup khả năng chạy extension là hai việc liên quan nhưng không giống nhau. Hãy lưu cả metadata, package/version inventory, configuration, extension-owned configuration data và hướng dẫn phục hồi; sau đó kiểm thử restore trên môi trường độc lập.

---

## 1. Ba lớp cần bảo vệ

Một hệ thống dùng extension có ít nhất ba lớp cần được quản lý:

| Lớp | Ví dụ | Nơi quản lý |
|---|---|---|
| Package/runtime | control files, SQL scripts, shared libraries, dependencies | OS image/package manager/provider |
| Extension metadata/objects | pg_extension, functions, types, operators | Database catalogs |
| Extension state/configuration | config tables, files, external state | Database hoặc hệ thống bên ngoài |

Một bản `pg_dump` không cài lại package. Một bản sao data directory không nhất thiết mang theo shared libraries từ OS package. Một bản cài package mới cũng không tự khôi phục dữ liệu cấu hình extension.

Recovery plan phải bao phủ cả ba lớp.

## 2. Phân biệt PostgreSQL version và extension version

Có nhiều version độc lập:

- **PostgreSQL server major version:** ví dụ 15, 16 hoặc 17.
- **Extension SQL version:** ví dụ 1.4, 1.5 hoặc 2.0.
- **Package/build version:** phiên bản package hoặc native library do OS/provider phân phối.

Các con số này không nhất thiết giống nhau. Một extension có SQL version 2.1 nhưng package được build riêng cho PostgreSQL 16 và PostgreSQL 17. SQL version giống nhau không có nghĩa shared library của hai major versions có thể dùng chung.

Khi kiểm tra tương thích, phải ghi cả server version, extension SQL version, package version và native library build.

## 3. Extension được lưu trong database như thế nào?

Khi chạy:

~~~sql
CREATE EXTENSION pgcrypto;
~~~

PostgreSQL đọc control file và SQL installation script trên server, rồi tạo extension metadata cùng các database objects.

Xem extensions đang cài trong database:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Extension được cài theo từng database. Nếu cluster có nhiều databases, inventory và backup phải xem xét từng database riêng.

## 4. Extension package không nằm trong pg_extension

`pg_extension` là catalog ghi metadata của extension trong database. Nó không chứa bản sao control file, SQL scripts hoặc native library.

Các files thường được cài trong PostgreSQL installation directories:

- Extension control files.
- SQL installation scripts.
- SQL update scripts.
- Shared libraries.
- Supporting files và dependencies.

Đường dẫn cụ thể phụ thuộc OS, PostgreSQL build, package và provider. Không suy luận vị trí chỉ từ tên extension.

## 5. Control file và compatibility metadata

Control file có thể khai báo:

~~~text
comment = 'Example extension'
default_version = '1.0'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
trusted = false
requires = 'another_extension'
~~~

Các thuộc tính giúp PostgreSQL biết version mặc định, library path, schema behavior, privilege requirements và dependencies.

Control file không phải bằng chứng đầy đủ rằng native library hoạt động trên target. Package có thể hiện diện nhưng thiếu dependency, sai architecture hoặc được build cho PostgreSQL major version khác.

## 6. SQL objects thuộc extension

Các objects được tạo bởi installation script có thể được đánh dấu là thành viên của extension. PostgreSQL quản lý membership qua dependency catalogs.

Điều này quan trọng với dump/restore: `pg_dump` thường lưu lệnh tạo extension thay vì dump từng member object như các objects độc lập.

Khi restore, SQL installation script của extension tạo lại member objects. Nếu package hoặc version script không có trên target, quá trình restore có thể thất bại.

## 7. pg_dump xử lý extension như thế nào?

Logical dump bằng `pg_dump` ghi nhận extension object và lệnh `CREATE EXTENSION` cần thiết cho restore.

Các objects là thành viên của extension không được dump như schema objects độc lập theo cách thông thường, vì chúng sẽ được tạo lại bởi extension installation script.

Vì vậy, dump có thể giữ metadata extension nhưng **không chứa native library hay toàn bộ implementation code**.

Khi restore sang server khác, cần chuẩn bị extension package tương thích trước.

## 8. Kiểm tra extension trong archive dump

Với custom-format archive:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

Có thể liệt kê nội dung archive:

~~~bash
pg_restore --list appdb.dump
~~~

Danh sách có thể cho thấy extension entries và các objects/data khác được dump. Tuy nhiên, nó không chứng minh package files hoặc native libraries đã được cài trên target.

Lưu archive list như một phần evidence, nhưng vẫn cần package inventory riêng.

## 9. Extension configuration tables

Một số extension tạo tables chứa cấu hình hoặc dữ liệu người dùng cần được giữ qua dump/restore.

Extension có thể đánh dấu các tables đó bằng function:

~~~sql
SELECT pg_extension_config_dump(
    'extension_schema.settings',
    ''
);
~~~

Trong installation script, extension author có thể gọi `pg_extension_config_dump()` để khai báo table là extension configuration table. Có thể truyền điều kiện để chỉ dump một phần rows cần thiết.

`pg_dump` sẽ xử lý data của các configuration tables được đánh dấu theo metadata này.

## 10. Không phải mọi extension table data đều tự động được dump

Đây là khác biệt quan trọng:

- Extension member objects thường được tạo lại từ extension script.
- Nội dung của configuration tables được đánh dấu bằng `pg_extension_config_dump()` có thể được đưa vào dump.
- Nội dung các extension tables khác có thể không được dump như dữ liệu ứng dụng thông thường.

Nếu extension lưu user-defined state trong table nhưng không đánh dấu table phù hợp, logical backup có thể không giữ dữ liệu đó.

Đọc documentation của extension và kiểm tra installation scripts để biết state nào cần backup riêng.

## 11. Configuration data và runtime state

Không phải mọi state đều là table data.

Extension có thể lưu trạng thái trong:

- SQL tables.
- Large objects.
- Files bên ngoài PGDATA.
- Shared memory/runtime state.
- WAL hoặc replication metadata.
- External service.
- Object storage hoặc remote endpoint.

Một số runtime state có thể được tái tạo sau restart; một số khác phải backup bằng công cụ riêng. Xác định chính xác extension dùng cơ chế nào.

## 12. Backup inventory cho extension

Một inventory tối thiểu nên ghi:

| Thuộc tính | Ví dụ |
|---|---|
| Extension name | postgis |
| SQL version | 3.x |
| PostgreSQL major | 16 |
| Package name/version | package của distro |
| Native library | library name/path |
| Dependencies | GDAL, GEOS, PROJ... |
| Schema | public hoặc schema riêng |
| Owner | deployment role |
| Configuration tables | tables được đánh dấu |
| Preload requirement | shared_preload_libraries nếu có |
| Update path | version transitions được hỗ trợ |
| Provider support | allowlist/version constraints |

Đây là dữ liệu cần để tái tạo môi trường target và điều tra khi restore thất bại.

## 13. Logical backup và physical backup

| Đặc điểm | Logical backup | Physical backup |
|---|---|---|
| Công cụ phổ biến | pg_dump, pg_dumpall | pg_basebackup, storage snapshot |
| Mức dữ liệu | SQL objects và data | Cluster data files/WAL |
| Restore | Tạo objects/data từ dump | Phục hồi data directory |
| Khác major version | Thường linh hoạt hơn, cần tương thích | Không phải đường nâng major trực tiếp |
| Extension package | Không đóng gói | Không tự bảo đảm OS package |
| Chọn database/object | Linh hoạt | Thường ở mức cluster |

Hai loại backup phục vụ các mục tiêu khác nhau. Nhiều hệ thống cần cả logical backup và physical backup/PITR.

## 14. Logical dump không đóng gói native code

`pg_dump` không đóng gói .so/.dll, OS dependencies hoặc PostgreSQL server binaries.

Nếu dump chứa:

~~~sql
CREATE EXTENSION example_extension;
~~~

thì server đích vẫn phải có control file, SQL scripts và library cần thiết trước khi thực hiện restore.

Nếu package thiếu, restore có thể báo extension không available hoặc không load được library.

## 15. Physical backup không thay thế package inventory

Physical backup chứa cluster data files theo phạm vi công cụ backup. Nó không phải package manager snapshot cho toàn bộ hệ điều hành.

Nếu extension library nằm ngoài PGDATA, việc restore data directory sang host mới không tự tạo lại library đó.

Cần backup/record:

- OS package list.
- PostgreSQL packages.
- Extension package versions.
- Native dependencies.
- Configuration files ngoài PGDATA.
- Certificates, service units và environment settings.
- External files mà extension cần.

## 16. Backup toàn cluster và backup từng database

`pg_dump` làm việc ở mức một database. Nếu cluster có nhiều databases, cần dump từng database hoặc dùng `pg_dumpall` theo mục đích.

Roles và tablespaces là cluster-wide objects; có thể lưu bằng:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

Extensions được cài riêng trong từng database, nên `globals.sql` không thay thế database dumps.

Một recovery runbook cần chỉ rõ database nào có extension nào và thứ tự phục hồi.

## 17. pg_dumpall và extension

`pg_dumpall` tạo dump cho nhiều databases và cluster globals theo cách logical. Nó có thể chứa lệnh tạo extension trong từng database dump tương ứng.

Tuy nhiên, nó cũng không mang theo native libraries hoặc OS dependencies.

Nếu extension yêu cầu superuser hoặc một predefined role đặc biệt, restore user cần có quyền phù hợp. Với trusted extension, cần kiểm tra điều kiện CREATE và behavior của extension.

## 18. Phiên bản pg_dump

Nên dùng `pg_dump` có major version bằng hoặc mới hơn server nguồn theo quy tắc hỗ trợ của PostgreSQL. Một `pg_dump` cũ không thể dump server có major version mới hơn nó.

Dump thường được thiết kế để nạp vào server mới hơn, nhưng compatibility vẫn phụ thuộc SQL features và extensions.

Ghi lại:

~~~bash
pg_dump --version
psql --version
pg_restore --version
~~~

Đừng nhầm version của client utilities với server version.

## 19. Restore logical dump theo đúng thứ tự

Một trình tự thường dùng:

1. Cài PostgreSQL target binaries.
2. Cài extension packages cho đúng target major version.
3. Chuẩn bị roles và tablespaces.
4. Tạo database với encoding/locale phù hợp.
5. Xác minh extension control files và versions khả dụng.
6. Restore dump.
7. Xử lý extension SQL updates nếu cần.
8. Kiểm tra owner, grants và configuration data.
9. Chạy ANALYZE và validation.

Extension package phải có sẵn trước bước restore nếu archive yêu cầu `CREATE EXTENSION`.

## 20. Tạo database trước khi restore

Ví dụ:

~~~bash
createdb \
  --template=template0 \
  --encoding=UTF8 \
  appdb_restore
~~~

Locale, collation provider và encoding cần phù hợp với yêu cầu ứng dụng và nguồn. Không dùng ví dụ trên thay cho inventory thực tế.

Nếu restore vào database có sẵn, cần xem xét `--clean`, dependencies và nguy cơ xóa objects. Thử nghiệm trên staging trước.

## 21. Restore custom-format archive

Ví dụ:

~~~bash
pg_restore \
  --dbname=appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump
~~~

`--exit-on-error` giúp dừng khi gặp lỗi thay vì tiếp tục qua các lỗi có thể làm database restore không đầy đủ.

Có thể dùng `--jobs` để parallelize một số restore operations. Điều này không có nghĩa mọi extension script hoặc object creation có thể chạy song song an toàn trong mọi archive.

## 22. Restore và extension privileges

Nếu extension untrusted yêu cầu superuser, role restore phải có quyền phù hợp để thực hiện `CREATE EXTENSION`.

Trusted extension có thể được cài bởi role có CREATE privilege trên database nếu đáp ứng các điều kiện khác. Tuy nhiên, một số extensions hoặc scripts có requirements riêng.

Không giải quyết lỗi restore bằng cách cấp superuser cho application role lâu dài. Dùng privileged deployment identity trong thời gian restore rồi thu hồi quyền theo policy.

## 23. Extension version trong dump

Dump có thể ghi version extension được cài ở nguồn trong lệnh `CREATE EXTENSION ... VERSION ...`.

Nếu target package không cung cấp version đó, restore có thể thất bại.

Các phương án cần xem xét:

- Cài package target có chứa version nguồn.
- Restore với version tương thích đã được vendor hỗ trợ.
- Sau khi restore thành công, chạy extension update path.
- Dùng migration procedure riêng nếu không có đường update trực tiếp.

Không tự sửa archive SQL để bỏ version clause nếu chưa hiểu tác động lên schema objects và extension state.

## 24. Kiểm tra versions khả dụng trước restore

Trên target server, xem:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

Xem các versions có sẵn:

~~~sql
SELECT
    name,
    version,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Các views này phản ánh những control files server có thể nhìn thấy. Chúng không chứng minh native dependencies load được; cần thử cài trên staging.

## 25. Kiểm tra extension update paths

PostgreSQL có thể liệt kê các update paths khả dụng cho extension:

~~~sql
SELECT *
FROM pg_extension_update_paths('example_extension');
~~~

Kết quả giúp xem các chuyển đổi version có script path hay không.

Một đường update tồn tại trong catalog không thay thế vendor support matrix. Với native extension, cần xác minh SQL migration và binary library tương thích cùng nhau.

## 26. ALTER EXTENSION UPDATE sau restore

Nếu restore cài extension ở version nguồn và target hỗ trợ update path:

~~~sql
ALTER EXTENSION example_extension UPDATE;
~~~

Hoặc chỉ định version đích:

~~~sql
ALTER EXTENSION example_extension UPDATE TO '2.0';
~~~

Trước khi chạy, đọc release notes, xác định thay đổi schema, kiểm tra backup, thử trên bản restore staging, đo thời gian/locks và xác minh dependent objects.

Không phải mọi extension đều hỗ trợ update trực tiếp từ mọi version cũ.

## 27. SQL update và native library update

Có thể phải thay cả hai:

1. Cài native package/library mới trên server.
2. Chạy `ALTER EXTENSION UPDATE` để cập nhật SQL objects.

Thứ tự chính xác phụ thuộc extension vendor và cách release được thiết kế. Một số extension yêu cầu library mới có mặt trước khi SQL update chạy; một số có pre/post-upgrade steps riêng.

Không thay library trong lúc server đang dùng nó mà không theo quy trình deployment/restart được hỗ trợ.

## 28. Extension update không phải PostgreSQL major upgrade

Ba hoạt động khác nhau:

- PostgreSQL major upgrade: thay server major version và catalog/data format theo quy trình như `pg_upgrade` hoặc dump/restore.
- Extension SQL update: chạy scripts chuyển extension objects/version.
- Extension package update: thay files và native libraries ở OS/provider layer.

Một lần nâng PostgreSQL major version có thể yêu cầu cả ba, nhưng chúng không tự động đồng nghĩa với nhau.

## 29. Physical backup và PITR

Physical backup như `pg_basebackup` cùng WAL archive hỗ trợ phục hồi cluster ở cấp physical.

Ví dụ tạo base backup:

~~~bash
pg_basebackup \
  --host=db-primary \
  --username=replication_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

Physical backup thường phục hồi về cùng PostgreSQL major version và môi trường tương thích. Không dùng base backup của major version cũ như thể có thể chạy trực tiếp bằng binaries của major version mới.

Extension packages/native dependencies phải được chuẩn bị riêng trên host phục hồi.

## 30. PITR và extension state

PITR phục hồi database tới một thời điểm dựa trên base backup và WAL.

Nó có thể phục hồi extension catalog changes và table data nếu các thay đổi đó nằm trong WAL timeline được phục hồi.

Nhưng PITR không cài lại OS packages hoặc native libraries. Nếu extension binary bị thiếu hoặc package đã bị thay đổi ngoài database, recovery vẫn có thể không start hoặc không load được extension.

Backup package inventory và cấu hình cùng với physical backup.

## 31. Physical restore và platform compatibility

Physical data directory có các yêu cầu tương thích về:

- PostgreSQL major version.
- Architecture/build characteristics.
- Endianness và block size theo yêu cầu.
- Filesystem và tablespace paths.
- Checksums/build options khi áp dụng.
- WAL compatibility.

Không copy data directory giữa các nền tảng khác biệt rồi giả định PostgreSQL sẽ mở được.

Nếu cần chuyển giữa OS/architecture không tương thích, cân nhắc logical dump/restore hoặc phương pháp migration được hỗ trợ.

## 32. pg_upgrade và extension

`pg_upgrade` chuyển cluster giữa major versions bằng cách xử lý catalogs và relation files. Nó không tự cài mọi extension package trên host mới.

Trước khi chạy:

- Cài extension packages tương thích target major version.
- Cài shared libraries và dependencies.
- Chuẩn bị control files và SQL scripts.
- Kiểm tra các extensions được preload.
- Chạy `pg_upgrade --check`.
- Đọc warnings về extension/module.

Nếu target thiếu native library, server mới có thể không start hoặc function calls có thể lỗi.

## 33. Old và new extension libraries

Trong thời gian upgrade, old cluster dùng binaries/libraries của old major version, còn new cluster cần packages build cho target major version.

Không ghi đè library cũ bằng binary build cho major version mới nếu old cluster còn cần chạy.

Có thể cần cài song song package theo major version, tùy OS package layout. Dùng package manager và repository của vendor để quản lý đúng files.

## 34. pg_upgrade không tự nâng extension SQL version

Sau khi `pg_upgrade` hoàn tất, extension catalog có thể vẫn ghi SQL version cũ.

Kiểm tra:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner
FROM pg_extension
ORDER BY extname;
~~~

Đọc target extension documentation và thực hiện `ALTER EXTENSION UPDATE` khi cần.

Không giả định server major version mới đồng nghĩa extension đã ở SQL version mới nhất.

## 35. shared_preload_libraries và startup dependencies

Một số extensions cần khai báo trong:

~~~text
shared_preload_libraries = 'pg_stat_statements,example_extension'
~~~

Khi phục hồi hoặc nâng cấp:

- Đảm bảo library có trên target.
- Kiểm tra tên module và compatibility.
- Cấu hình target postgresql.conf/parameter group.
- Restart khi setting yêu cầu.
- Đọc startup logs.
- Xác minh extension hoạt động.

Thiếu một module trong `shared_preload_libraries` có thể khiến startup thất bại nếu cấu hình yêu cầu load module đó.

## 36. Background workers và shared memory

Extensions có thể đăng ký background workers hoặc yêu cầu shared memory initialization.

Các thành phần này phụ thuộc server version, package build và cấu hình startup.

Sau restore/upgrade:

- Kiểm tra worker processes.
- Kiểm tra logs.
- Xác minh required GUCs.
- Xem memory/worker limits.
- Kiểm tra extension health endpoints hoặc catalog state.
- Kiểm tra restart behavior.

Không chỉ kiểm tra `CREATE EXTENSION` thành công rồi kết luận extension đã hoạt động đầy đủ.

## 37. Extension config tables sau logical restore

Nếu extension đánh dấu configuration tables bằng `pg_extension_config_dump()`, data có thể được dump và restore.

Sau restore, kiểm tra các config tables và row counts:

~~~sql
SELECT count(*)
FROM extension_schema.settings;
~~~

Tên table chỉ là ví dụ. So sánh các configuration values quan trọng với baseline.

Nếu extension không đánh dấu table data cần giữ, cần export/import bằng công cụ được vendor hỗ trợ hoặc backup riêng trước khi migration.

## 38. Restore dependency order

Một số extensions khai báo `requires` để phụ thuộc extension khác. Các SQL objects của ứng dụng cũng có thể phụ thuộc extension types/functions.

Quy trình restore phải đảm bảo:

1. Native packages/dependencies có trên server.
2. Required extensions có thể được cài.
3. Database và schema prerequisites tồn tại.
4. Extension objects được tạo.
5. Configuration data được restore.
6. Application objects phụ thuộc được tạo/restore.
7. Grants và ownership được khôi phục.

Archive restore có dependency ordering riêng, nhưng external packages và OS-level dependencies vẫn phải chuẩn bị trước.

## 39. Logical replication và extension

Logical replication không phải cơ chế replicate extension installation metadata hoặc DDL một cách tổng quát.

Nó replicate row changes của các tables thuộc publication theo cấu hình, nhưng không tự:

- Cài extension trên subscriber.
- Tạo native libraries.
- Đồng bộ `CREATE EXTENSION`.
- Chuyển toàn bộ schema/DDL changes.
- Bảo đảm extension SQL versions giống nhau.

Provision extension package và objects trên subscriber theo migration plan. Nếu extension-owned tables chứa dữ liệu cần replicate, xác minh publication/subscription và table eligibility riêng.

## 40. Cross-major migration bằng logical replication

Logical replication có thể là chiến lược giảm downtime khi chuyển major versions, nhưng extension compatibility cần được chuẩn bị ở cả source và target.

Cần:

- Cài extension packages tương thích trên target.
- Tạo schema và extension objects trên subscriber.
- Kiểm tra types, operators và functions mà schema dùng.
- Xác định extension tables nào cần replicate.
- Đồng bộ DDL riêng.
- Xác minh sequences và non-table state.
- Kiểm tra replication lag và cutover consistency.

Không giả định logical replication thay thế việc cài extension hoặc chuyển extension configuration.

## 41. High availability và standbys

Trong physical streaming replication, standby cần cùng major version với primary theo topology được hỗ trợ và có binaries/extensions phù hợp để chạy workload sau failover.

Trước major upgrade:

- Inventory extension packages trên mọi nodes.
- Chuẩn bị target packages cho primary và standbys.
- Xác minh `shared_preload_libraries`.
- Lập kế hoạch rebuild/reseed standbys nếu cần.
- Cập nhật monitoring/backup agents.
- Diễn tập failover sau upgrade.

Một primary upgrade thành công không chứng minh standby có thể promote an toàn.

## 42. Replication slots và extension-specific replication

Một số extensions cung cấp output plugins, logical decoding hoặc replication helpers.

Cần kiểm tra:

- Plugin binary có tương thích target không?
- Slot có được giữ hay phải tạo lại?
- Consumer có hỗ trợ target major version?
- WAL retention có đủ trong downtime?
- Extension state có được migrate?
- Consumer offsets có thể tiếp tục không?

Không xóa replication slots hoặc reset consumer offsets chỉ để làm upgrade hoàn tất khi chưa có kế hoạch recovery.

## 43. Managed PostgreSQL services

Managed providers có thể duy trì extension allowlist và package versions riêng.

Khác biệt giữa các providers có thể gồm extension được hỗ trợ, version được phép, cách bật extension, quyền superuser bị giới hạn, shared preload configuration, maintenance/upgrade workflow và backup/PITR semantics.

Trước migration, đối chiếu source và target provider support matrix. Một extension có trên PostgreSQL upstream không chắc có trên dịch vụ managed đích.

## 44. Container và Kubernetes

Trong containerized PostgreSQL, extension package thường thuộc image, còn data nằm trong persistent volume.

Khi thay image hoặc upgrade major version:

- Image target phải có extension packages tương thích.
- Shared libraries phải khớp architecture và server ABI.
- ConfigMaps/parameter settings phải được cập nhật.
- Persistent volume không tự chứa packages từ image cũ.
- Init scripts cần idempotent.
- Operator phải hỗ trợ version transition.
- Backup/restore workflow phải ghi nhận image digest và package list.

Không cài package thủ công vào ephemeral container rồi giả định nó tồn tại sau reschedule/recreate.

## 45. Collation, types và indexes của extension

Extensions có thể cung cấp custom types, operator classes hoặc index access methods. Upgrade có thể thay đổi behavior, serialization hoặc semantics của các objects đó.

Cần đọc release notes để xác định:

- Có thay đổi type representation không?
- Có cần dump/reload dữ liệu không?
- Có cần REINDEX không?
- Có thay đổi operator class semantics không?
- Có yêu cầu ALTER EXTENSION UPDATE trước/sau một bước khác không?
- Có collation dependencies không?

Không tự reindex hoặc rewrite data mà chưa biết yêu cầu cụ thể của extension.

## 46. Extension update có thể không reversible

`ALTER EXTENSION UPDATE` thường chạy SQL migration scripts. Không phải mọi extension đều cung cấp downgrade scripts.

Nếu update đã thay đổi catalog objects hoặc data, việc hạ version package đơn thuần không khôi phục state cũ.

Trước update:

1. Backup database.
2. Lưu extension version.
3. Đọc update script/release notes.
4. Thử trên clone/restore.
5. Kiểm tra locks và thời gian.
6. Xác định rollback bằng restore hoặc forward-fix.
7. Cài package tương thích với kế hoạch rollback.

Không xóa package cũ cho tới khi rollback window kết thúc nếu policy yêu cầu giữ khả năng phục hồi.

## 47. Extension configuration và secrets

Một số extensions giữ credentials hoặc endpoints trong database settings, tables hoặc external files.

Không đưa secrets vào dump/log không mã hóa.

Backup plan cần xác định:

- Secret nào nằm trong database.
- Secret nào nằm trong configuration file.
- Secret nào nằm trong secret manager.
- Cách restore identity/permissions.
- Rotation requirements sau recovery.
- Cách kiểm tra secret không bị lộ trong archive.

Một database restore thành công nhưng thiếu credentials hoặc certificates vẫn có thể khiến extension không hoạt động.

## 48. Quy trình restore có kiểm soát

Một workflow thực tế:

1. Xác định source PostgreSQL và extension versions.
2. Đọc package inventory/backup manifest.
3. Chuẩn bị target PostgreSQL binaries.
4. Cài target extension packages và native dependencies.
5. Cấu hình preload và external services.
6. Tạo roles, tablespaces và database.
7. Xác minh extension versions/control files.
8. Restore logical dump hoặc physical backup.
9. Chạy extension SQL updates nếu cần.
10. Restore/verify extension configuration state.
11. Kiểm tra owners, grants và search_path.
12. Chạy ANALYZE.
13. Kiểm thử extension APIs và application.
14. Xác minh backup mới và replication.

Thứ tự cụ thể phải theo extension vendor instructions và backup type.

## 49. Quy trình major upgrade có kiểm soát

Với `pg_upgrade`, workflow thường gồm:

1. Inventory extensions trên old cluster.
2. Xác định target-compatible packages.
3. Cài song song old/new packages theo OS requirements.
4. Kiểm tra preload libraries và dependencies.
5. Khởi tạo new cluster bằng target initdb.
6. Chạy `pg_upgrade --check`.
7. Backup và rehearsal rollback.
8. Dừng old cluster.
9. Chạy actual pg_upgrade.
10. Khởi động new cluster.
11. Kiểm tra extension versions và logs.
12. Chạy `ALTER EXTENSION UPDATE` khi được hỗ trợ.
13. Analyze và kiểm tra objects.
14. Kiểm thử ứng dụng và HA.

`pg_upgrade` không thay thế package management hoặc extension-specific migration instructions.

## 50. Kiểm tra sau restore/upgrade

Inventory extension:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Kiểm tra packages/versions khả dụng:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Kiểm tra languages nếu extension phụ thuộc procedural language:

~~~sql
SELECT
    lanname,
    lanpltrusted
FROM pg_language
ORDER BY lanname;
~~~

Đối chiếu kết quả với manifest trước backup/upgrade.

## 51. Kiểm tra native library và startup logs

SQL catalog không thể chứng minh mọi shared library load được trong mọi code path.

Kiểm tra:

- PostgreSQL startup logs.
- Undefined symbol/library errors.
- Missing dependency messages.
- Background worker startup failures.
- Preload warnings/errors.
- Function calls đại diện.
- Native package version trên OS.

Với module chỉ được load khi function được gọi, hãy thực hiện smoke tests thực sự gọi các functions quan trọng.

## 52. Kiểm tra extension configuration state

Nếu extension có config tables hoặc external state, xác minh:

- Table tồn tại.
- Rows cần thiết có mặt.
- Ownership và grants đúng.
- Config values khớp baseline.
- External endpoints có thể truy cập.
- Credentials/certificates hợp lệ.
- State có thể được tái tạo nếu không backup được.

Không chỉ so sánh extversion; cùng một extension version có thể có configuration/state data khác nhau.

## 53. Kiểm tra functional behavior

Tạo test cases cho APIs extension được ứng dụng sử dụng.

Ví dụ với extension cung cấp function:

~~~sql
SELECT extension_schema.example_function('test-input');
~~~

Với extension cung cấp index access method/operator class, kiểm tra query plans và kết quả truy vấn. Với extension background worker, xác minh worker hoạt động và log không có lỗi.

Chọn test theo chức năng thực tế, không chỉ kiểm tra extension row trong `pg_extension`.

## 54. Kiểm tra backup mới sau recovery

Sau khi restore hoặc upgrade thành công:

- Tạo base backup mới phù hợp target major version.
- Xác minh WAL archiving.
- Backup extension package inventory.
- Lưu extension versions và package manifests.
- Kiểm tra restore độc lập.
- Ghi nhận configuration và secrets references.
- Cập nhật disaster recovery runbook.

Không tiếp tục dựa vào backup cũ của source version như bản backup duy nhất của hệ thống mới.

## 55. Những lỗi thường gặp

### 55.1. Extension không available

Target thiếu control file/SQL package hoặc package không được provider hỗ trợ.

### 55.2. Shared library không tìm thấy

Native library chưa cài, sai library path hoặc sai PostgreSQL major version.

### 55.3. Undefined symbol

Library được build cho ABI khác hoặc dependency mismatch.

### 55.4. Extension version không có

Dump yêu cầu version nguồn nhưng target package không có installation script tương ứng.

### 55.5. Update path không tồn tại

Không có SQL update script trực tiếp từ version hiện tại tới version đích.

### 55.6. Config table trống sau restore

Extension chưa đánh dấu table bằng `pg_extension_config_dump()` hoặc state được backup bằng cơ chế khác nhưng chưa phục hồi.

### 55.7. Preload failure

`shared_preload_libraries` tham chiếu module thiếu hoặc không tương thích, làm server startup thất bại.

### 55.8. Extension objects thiếu sau logical restore

Extension script không chạy được hoặc archive restore bị lỗi; cần đọc restore logs và xác minh objects.

### 55.9. Standby không promote được

Standby thiếu package, binary, config hoặc chưa được rebuild đúng target major version.

### 55.10. Managed provider từ chối CREATE EXTENSION

Extension hoặc version không nằm trong provider allowlist, hoặc role không có quyền tương ứng.

## 56. Lab: inventory và backup extension

Trong database lab:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole,
    extnamespace::regnamespace
FROM pg_extension
ORDER BY extname;

SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Ghi lại server version, package versions, shared libraries, preload settings và external dependencies.

Tạo logical dump:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

Liệt kê archive:

~~~bash
pg_restore --list appdb.dump
~~~

Ghi lại extension entries và xác định package nào cần cài trên target.

## 57. Lab: restore khi package đã cài

1. Tạo target database lab.
2. Cài extension packages tương thích.
3. Kiểm tra pg_available_extensions.
4. Restore archive bằng pg_restore.
5. Kiểm tra pg_extension.
6. Kiểm tra extension config tables.
7. Gọi các extension functions đại diện.
8. So sánh kết quả với source baseline.

Không dùng production credentials hoặc external services thật trong lab.

## 58. Lab: extension update path

Kiểm tra versions và update paths:

~~~sql
SELECT *
FROM pg_extension_update_paths('example_extension');
~~~

Nếu có đường update được vendor hỗ trợ:

~~~sql
ALTER EXTENSION example_extension UPDATE;
~~~

Ghi lại version trước/sau, script output, locks, elapsed time và behavior của application queries.

Thử trên restored copy trước khi áp dụng vào production.

## 59. Lab: pg_upgrade và extension packages

Trên hai PostgreSQL installations riêng biệt:

1. Cài source major version và extension package tương ứng.
2. Tạo old cluster, cài extension và tạo dữ liệu thử.
3. Backup/restore rehearsal.
4. Cài target major version và target extension package.
5. Chuẩn bị target cluster.
6. Chạy pg_upgrade --check.
7. Rehearse actual upgrade.
8. Khởi động new cluster.
9. Kiểm tra extension versions, native library và preload behavior.
10. Chạy extension update khi cần.
11. Kiểm tra functions, configuration tables và application behavior.

Không ghi đè package old version nếu còn cần old cluster để rollback.

## 60. Bài tập thực hành

### Bài 1 — Ba lớp extension

Kể tên ba lớp cần backup.

**Gợi ý:** package/runtime, database metadata/objects và configuration/state data.

### Bài 2 — pg_dump

pg_dump có đóng gói native shared library không?

**Gợi ý:** không.

### Bài 3 — CREATE EXTENSION

Lệnh restore tạo extension dựa trên những files nào?

**Gợi ý:** control file và SQL installation scripts trên target server.

### Bài 4 — Extension membership

Vì sao pg_dump không dump từng member object như object độc lập?

**Gợi ý:** installation script tạo lại các member objects.

### Bài 5 — Configuration tables

Function nào đánh dấu extension configuration tables?

**Gợi ý:** pg_extension_config_dump.

### Bài 6 — Extension state

Mọi extension table data có tự động được dump không?

**Gợi ý:** không; cần hiểu config table declarations và extension behavior.

### Bài 7 — Physical backup

Physical backup có tự cài OS packages không?

**Gợi ý:** không.

### Bài 8 — Cluster globals

Lệnh nào thường dùng để dump roles và tablespaces?

**Gợi ý:** pg_dumpall --globals-only.

### Bài 9 — Per-database extension

Extension cài trong một database có tự xuất hiện ở database khác không?

**Gợi ý:** không.

### Bài 10 — pg_dump version

pg_dump cũ hơn source server major version có thể dump server mới hơn không?

**Gợi ý:** không được hỗ trợ.

### Bài 11 — Restore order

Vì sao package cần cài trước pg_restore?

**Gợi ý:** CREATE EXTENSION cần control files và scripts.

### Bài 12 — Extension version

Vì sao dump yêu cầu version nguồn có thể thất bại trên target?

**Gợi ý:** target không có installation script của version đó.

### Bài 13 — Update paths

Function nào liệt kê extension update paths?

**Gợi ý:** pg_extension_update_paths.

### Bài 14 — ALTER EXTENSION

Lệnh nào chạy SQL migration của extension?

**Gợi ý:** ALTER EXTENSION ... UPDATE.

### Bài 15 — Native ABI

Vì sao native extension cần build đúng major version?

**Gợi ý:** server ABI/API có thể thay đổi.

### Bài 16 — pg_upgrade

pg_upgrade có tự cài extension package không?

**Gợi ý:** không.

### Bài 17 — Extension SQL version

Sau pg_upgrade, extension SQL version có tự động mới nhất không?

**Gợi ý:** không nhất thiết; kiểm tra extversion và update path.

### Bài 18 — Preload

Vì sao shared_preload_libraries phải được kiểm tra sau upgrade?

**Gợi ý:** module thiếu hoặc sai version có thể làm startup lỗi.

### Bài 19 — PITR

PITR có phục hồi OS shared libraries không?

**Gợi ý:** không.

### Bài 20 — Logical replication

Logical replication có tự replicate CREATE EXTENSION không?

**Gợi ý:** không.

### Bài 21 — Extension config state

Làm sao biết config table có được pg_dump xử lý?

**Gợi ý:** xem extension installation script và pg_extension_config_dump declarations.

### Bài 22 — Standby

Vì sao standby cần extension packages?

**Gợi ý:** khi promote hoặc chạy extension-dependent workload, cần native files/config phù hợp.

### Bài 23 — Managed service

Vì sao phải kiểm tra extension allowlist?

**Gợi ý:** provider có thể giới hạn packages, versions và privileges.

### Bài 24 — Container

Vì sao extension package cần có trong image target?

**Gợi ý:** data volume không tự chứa binaries/control files.

### Bài 25 — Extension rollback

ALTER EXTENSION UPDATE có luôn downgrade được không?

**Gợi ý:** không; nhiều extensions không cung cấp downgrade scripts.

### Bài 26 — Backup manifest

Nêu các trường quan trọng trong extension inventory.

**Gợi ý:** name, SQL version, server major, package, library, dependencies, config tables, preload.

### Bài 27 — Restore validation

Vì sao chỉ kiểm tra pg_extension là chưa đủ?

**Gợi ý:** native libraries, background workers, config state và functional behavior còn cần kiểm tra.

### Bài 28 — Package provenance

Vì sao phải pin và ghi package version?

**Gợi ý:** tái tạo đúng runtime và xác định nguồn gốc binary.

### Bài 29 — External state

Extension gọi external service cần backup thêm gì?

**Gợi ý:** endpoint, credentials, certificates, service state và recovery instructions.

### Bài 30 — New backup

Sau major upgrade nên tạo backup nào?

**Gợi ý:** base backup/WAL strategy phù hợp target major version cùng package/config inventory.

### Bài 31 — Update order

Vì sao cần đọc vendor instructions trước khi thay library và chạy ALTER EXTENSION?

**Gợi ý:** một số extensions yêu cầu thứ tự hoặc restart cụ thể.

### Bài 32 — Config data

Vì sao config table có thể dùng điều kiện trong pg_extension_config_dump?

**Gợi ý:** chỉ dump những rows cần giữ, bỏ rows mặc định/tái tạo được.

### Bài 33 — Restore permissions

Vì sao restore untrusted extension có thể cần superuser?

**Gợi ý:** control file có thể yêu cầu privileged installation.

### Bài 34 — Collation/index

Khi extension thay đổi operator class, cần xem xét điều gì?

**Gợi ý:** index validity/semantics và yêu cầu REINDEX của vendor.

### Bài 35 — Replication plugin

Extension cung cấp logical decoding plugin cần kiểm tra gì?

**Gợi ý:** binary target, slot compatibility, consumers và offsets.

### Bài 36 — Physical version

Có thể dùng physical backup major version cũ để chạy server major version mới trực tiếp không?

**Gợi ý:** không; cần pg_upgrade hoặc migration phù hợp.

### Bài 37 — Archive inspection

Lệnh nào liệt kê nội dung custom-format dump?

**Gợi ý:** pg_restore --list.

### Bài 38 — Startup errors

Nếu shared_preload_libraries thiếu file, có thể xảy ra điều gì?

**Gợi ý:** server startup failure hoặc module load error.

### Bài 39 — Recovery test

Một extension recovery rehearsal cần chứng minh những gì?

**Gợi ý:** package, metadata, config state, functions, permissions và external dependencies đều hoạt động.

### Bài 40 — Backup strategy

Vì sao cần kết hợp database backup và package/config inventory?

**Gợi ý:** dữ liệu database không tự tái tạo môi trường runtime extension.

## 61. Câu hỏi thường gặp

### pg_dump có backup extension không?

Nó lưu extension metadata và lệnh tạo extension cùng những configuration table data được extension khai báo phù hợp. Nó không đóng gói native libraries hoặc OS dependencies.

### Vì sao restore báo extension không available?

Target thiếu control file/SQL scripts hoặc provider không hỗ trợ extension. Cài package đúng PostgreSQL major version rồi kiểm tra lại.

### pg_dump có lưu từng function của extension không?

Member objects thường được tạo lại bởi extension installation script, không dump độc lập như application objects thông thường.

### Extension config tables được backup thế nào?

Extension author có thể đánh dấu bằng pg_extension_config_dump. Kiểm tra script và xác minh dữ liệu sau restore.

### Physical backup có chứa extension binaries không?

Thông thường không. Nó bảo vệ cluster data files; native libraries và packages cần được quản lý riêng.

### pg_upgrade có tự update extension version không?

Không nên giả định. Kiểm tra extversion sau upgrade và chạy ALTER EXTENSION UPDATE theo vendor-supported path khi cần.

### Có thể restore dump từ PostgreSQL 16 sang 17 không?

Thường có thể với logical dump và tương thích SQL, nhưng extension package/version phải có trên target. Rehearse trước production.

### Có thể physical restore PostgreSQL 16 backup vào PostgreSQL 17 không?

Không như một lần start trực tiếp. Physical backup thuộc major version nguồn; dùng pg_upgrade hoặc logical migration để chuyển major.

### Extension version giống nhau có nghĩa native binary giống nhau không?

Không. Cùng SQL version có thể có package builds khác nhau cho từng PostgreSQL major version và architecture.

### Logical replication có chuyển extension không?

Không tự động. Provision extension packages và objects riêng; replicate table data nếu cần và được hỗ trợ.

### Có nên chạy ALTER EXTENSION UPDATE ngay sau restore?

Chỉ sau khi xác minh package, update path, dependencies, backup và vendor instructions. Thử trước trên staging.

### Làm sao biết extension cần shared_preload_libraries?

Đọc extension documentation và package configuration. Kiểm tra cấu hình hiện tại và startup logs.

### Extension có external files thì sao?

Backup các files, permissions, paths, certificates và secrets theo quy trình riêng. Database dump không bảo đảm chứa chúng.

### Có thể xóa package cũ sau khi upgrade không?

Sau khi old cluster không còn cần, rollback window đóng và target extension được xác minh. Tuân theo package manager và deployment policy.

### Khi nào hoàn tất extension recovery?

Khi package/library load được, metadata/version đúng, config state đầy đủ, permissions phù hợp và các APIs/worker của extension hoạt động trong application tests.

## 62. Tổng kết

Các truy vấn và lệnh quan trọng:

~~~sql
-- Extensions được cài trong database hiện tại.
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;

-- Extension packages/versions server nhìn thấy.
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;

-- Các extension versions có sẵn.
SELECT
    name,
    version,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;

-- Extension update paths.
SELECT *
FROM pg_extension_update_paths('example_extension');

-- Sau khi xác minh vendor-supported path:
ALTER EXTENSION example_extension UPDATE;
~~~

~~~bash
# Ghi logical backup cho một database.
pg_dump -Fc -f appdb.dump appdb

# Xem nội dung archive.
pg_restore --list appdb.dump

# Restore vào database đã chuẩn bị package và roles.
pg_restore \
  --dbname=appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump

# Backup cluster globals.
pg_dumpall --globals-only > globals.sql

# Physical base backup; package inventory vẫn phải backup riêng.
pg_basebackup \
  --host=db-primary \
  --username=replication_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

Những nguyên tắc cần nhớ:

1. Extension package, database metadata/objects và extension state là ba lớp riêng.
2. pg_dump ghi extension metadata và lệnh tạo extension; không đóng gói native library.
3. Member objects được tạo lại từ extension installation scripts.
4. Extension configuration tables được dump theo declarations như pg_extension_config_dump().
5. Không phải mọi table data do extension tạo đều tự động được backup.
6. pg_dumpall --globals-only lưu roles/tablespaces, còn extension được cài theo từng database.
7. Physical backup giữ cluster files nhưng không tự cài OS packages hoặc external dependencies.
8. PITR phục hồi database/WAL state, không phục hồi native libraries bị thiếu.
9. Dùng pg_dump version phù hợp với source server.
10. Cài target extension packages trước logical restore.
11. Dump có thể yêu cầu extension SQL version nguồn; kiểm tra versions khả dụng.
12. pg_extension_update_paths() giúp xem SQL update paths.
13. ALTER EXTENSION UPDATE và package update là hai hoạt động khác nhau.
14. pg_upgrade không tự cài packages hoặc bảo đảm extension SQL version mới nhất.
15. Native libraries cần build đúng PostgreSQL major version và architecture.
16. Kiểm tra shared_preload_libraries, background workers và startup logs.
17. Logical replication không tự đồng bộ extension installation hoặc DDL.
18. HA nodes cần package/config phù hợp và quy trình rebuild/rejoin.
19. Managed providers có extension allowlists riêng.
20. Container image target phải chứa packages tương thích.
21. Extension updates có thể không downgrade được.
22. Backup secrets, external files và service state theo quy trình riêng.
23. Sau restore, xác minh metadata, configuration data, permissions và functional behavior.
24. Tạo backup mới cho target major version sau recovery/upgrade.

Sơ đồ tương thích:

~~~text
                 Extension inventory
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Packages    DB metadata   State/config
          and libs    and objects   and external data
             |           |           |
             v           v           v
       Target OS/PG   pg_dump or   Config-table dump,
       version build  physical     files/secrets/service
             |        restore      backup
             |           |           |
             +-----------+-----------+
                         |
                         v
              Restore / pg_upgrade
                         |
                         v
             Extension SQL update path
                         |
                         v
           Startup, preload and dependencies
                         |
                         v
             Functional validation
                         |
                         v
             New backup + DR rehearsal
~~~

**Kết luận:** Tương thích extension khi backup, restore và upgrade đòi hỏi chuẩn bị đồng thời package/runtime, database metadata và extension state. Logical dump có thể tái tạo extension objects qua installation scripts nhưng cần package tương thích trên target; physical backup/PITR giữ database files nhưng không thay thế OS package inventory; pg_upgrade chuyển cluster nhưng không tự cài hoặc cập nhật mọi extension. Hãy ghi rõ versions, dependencies, configuration tables, preload requirements và recovery steps, rồi diễn tập restore/upgrade để chứng minh extension hoạt động trên môi trường đích.
