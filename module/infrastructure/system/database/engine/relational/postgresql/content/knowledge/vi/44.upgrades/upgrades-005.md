# Nâng cấp bằng pg_upgrade và lựa chọn chế độ sao chép dữ liệu

`pg_upgrade` là công cụ PostgreSQL dùng để nâng cấp một database cluster giữa các **major versions** mà không cần dump và restore toàn bộ dữ liệu theo cách truyền thống. Công cụ kiểm tra khả năng tương thích, chuẩn bị cluster mới, chuyển relation files và cập nhật system catalogs để cluster mới có thể chạy bằng PostgreSQL binaries của phiên bản đích.

Một quyết định quan trọng khi chạy `pg_upgrade` là chọn cách chuyển relation data files:

- **Copy:** sao chép file dữ liệu sang cluster mới; cluster cũ giữ nguyên.
- **Link:** tạo hard links giữa file cũ và file mới; nhanh và ít tốn dung lượng, nhưng cluster cũ không còn an toàn để sử dụng sau khi cluster mới được khởi động.
- **Clone:** dùng filesystem copy-on-write/reflink nếu được hỗ trợ; tạo bản sao logic nhanh, tiết kiệm dung lượng và giữ cluster cũ độc lập.
- **Copy-file-range:** trên các phiên bản và hệ điều hành hỗ trợ, dùng cơ chế copy trong kernel để tăng tốc sao chép nhưng vẫn tạo file độc lập.

Bài **“Nâng cấp bằng pg_upgrade và lựa chọn chế độ sao chép dữ liệu”**, thuộc chương **Nâng cấp** của module **Database Engine Relational PostgreSQL**, giải thích cách chọn phương pháp, chuẩn bị old/new clusters, chạy kiểm tra, thực hiện upgrade, xử lý extensions/configuration, xác minh dữ liệu và lập kế hoạch rollback.

> **Quy tắc quyết định:** nếu ưu tiên khả năng quay lại cluster cũ, dùng copy hoặc clone. Chỉ chọn link khi chấp nhận rằng sau khi khởi động cluster mới, cluster cũ không thể được dùng như một bản rollback độc lập. Dù chọn phương pháp nào, phải có backup và kiểm thử restore trước khi nâng cấp production.

---

## 1. Major upgrade và minor upgrade

PostgreSQL phân biệt major version và minor release.

- **Major upgrade:** chuyển giữa các major versions, ví dụ PostgreSQL 15 lên 16 hoặc 16 lên 17. Major upgrade có thể thay đổi system catalogs và internal data formats.
- **Minor upgrade:** chuyển giữa các minor releases trong cùng major version, ví dụ 16.2 lên 16.4. Thông thường chỉ cần thay binaries/package theo quy trình phù hợp; không cần chạy `pg_upgrade`.

`pg_upgrade` dành cho major version upgrade. Không dùng nó như bước bắt buộc cho mọi lần cài security/bug-fix update cùng major version.

## 2. pg_upgrade giải quyết vấn đề gì?

Một cách nâng cấp truyền thống là:

1. Dùng `pg_dump`/`pg_dumpall` xuất dữ liệu từ cluster cũ.
2. Khởi tạo cluster mới.
3. Restore schema, roles và data.
4. Rebuild indexes và các objects cần thiết.
5. Kiểm tra ứng dụng rồi chuyển endpoint.

Phương pháp dump/restore linh hoạt và hữu ích khi cần thay đổi encoding, kiến trúc dữ liệu hoặc lọc/chuyển đổi nội dung, nhưng với database lớn có thể tốn thời gian.

`pg_upgrade` tận dụng khả năng tương thích binary của các relation files để chuyển cluster nhanh hơn. Nó cập nhật system catalogs cần thiết cho major version mới và cho phép tránh việc export/import mọi row.

Nó không phải công cụ chuyển đổi tùy ý schema hoặc data model. Nếu ứng dụng cần thay đổi schema, encoding, collation hoặc data transformation phức tạp, có thể cần dump/restore hoặc migration riêng.

## 3. Cluster cũ và cluster mới

`pg_upgrade` làm việc với hai data directories riêng:

~~~text
Old PostgreSQL cluster
  old binaries
  old data directory
        |
        | pg_upgrade
        v
New PostgreSQL cluster
  new binaries
  new data directory
~~~

Thông thường cần:

- Binaries của phiên bản cũ.
- Binaries của phiên bản mới.
- Data directory của cluster cũ.
- Data directory đã được khởi tạo cho cluster mới.
- Cùng một operating-system user phù hợp để chạy quá trình.
- Quyền truy cập tới tablespaces, sockets và các thư mục liên quan.

Không chạy hai cluster cùng dùng một data directory. Không khởi động cluster mới trước khi quá trình upgrade hoàn tất.

## 4. pg_upgrade không phải logical migration

`pg_upgrade` chuyển một cluster hiện có sang major version mới bằng cách xử lý catalog và relation files theo các quy tắc tương thích.

Nó không tự:

- Thiết kế lại schema.
- Đổi kiểu dữ liệu theo yêu cầu ứng dụng.
- Chuyển business logic.
- Tạo lại toàn bộ configuration files như một migration hoàn chỉnh.
- Cài binaries của extensions bên ngoài.
- Xác minh mọi query ứng dụng.
- Tạo backup độc lập thay cho backup strategy.
- Thay thế kế hoạch failover/HA.

Sau upgrade vẫn cần cấu hình, cập nhật extensions, phân tích statistics, kiểm thử và chuyển ứng dụng.

## 5. Điều kiện tương thích

Trước khi bắt đầu, kiểm tra tài liệu `pg_upgrade` đúng major version đích. Các yêu cầu cụ thể thay đổi theo từng release.

Những điều kiện quan trọng thường gồm:

- Old version đang ở một source version được target version hỗ trợ.
- New cluster được khởi tạo bằng initdb của phiên bản đích.
- Cả hai clusters dùng kiến trúc tương thích, bao gồm word size và endianness theo yêu cầu.
- Locale, encoding và các thiết lập initdb quan trọng tương thích.
- Data checksums và các thuộc tính cluster đáp ứng yêu cầu nâng cấp.
- Extensions cần thiết có binaries/control files cho cả hai phiên bản.
- Tablespaces và symbolic links có thể truy cập được.
- Đủ disk space cho phương pháp đã chọn.
- Không còn transaction hoặc process khiến cluster không thể dừng an toàn.

Không suy đoán rằng mọi source version đều có thể nâng thẳng lên target. Nếu target không hỗ trợ direct upgrade từ source, cần nâng qua intermediate major version theo lộ trình được tài liệu hỗ trợ.

## 6. Kiểm tra phiên bản và binaries

Xác định version của các binaries:

~~~bash
/path/to/old/bin/postgres --version
/path/to/new/bin/postgres --version
/path/to/new/bin/pg_upgrade --version
~~~

Dùng `pg_upgrade` từ phiên bản đích. Cần chỉ rõ binary directories để công cụ biết executable của old và new clusters.

Có thể kiểm tra help:

~~~bash
/path/to/new/bin/pg_upgrade --help
~~~

Các options như `--clone` hoặc `--copy-file-range` chỉ dùng được nếu binary hiện tại hỗ trợ. Không copy command line từ một major version khác mà chưa xem help và documentation.

## 7. Kiểm tra cluster hiện tại

Trên old cluster, ghi nhận:

- PostgreSQL version.
- Data directory.
- Port và socket directory.
- Database list.
- Tablespaces.
- Extensions.
- Roles và memberships.
- Replication slots/subscriptions nếu có.
- Configuration overrides.
- SSL certificates và key permissions.
- Backup/WAL archive status.
- Scheduled jobs và external integrations.

Ví dụ SQL:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;

SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace;
~~~

Đây là inventory phục vụ lập kế hoạch và xác minh sau upgrade.

## 8. Backup trước khi nâng cấp

Trước một major upgrade production, cần có backup có thể restore.

Một phương án thường gồm:

- Base backup đầy đủ.
- WAL archive liên tục và được xác minh.
- Backup cấu hình, certificates và secrets theo policy.
- Backup/ghi nhận extension packages và version.
- Snapshot storage nhất quán nếu hạ tầng hỗ trợ và quy trình bảo đảm consistency.
- Restore test trên môi trường độc lập.

Một bản backup chỉ được coi là hữu ích khi có thể restore và khởi động cluster từ đó. Kiểm tra checksum, WAL continuity và thời gian phục hồi.

Không xem old data directory là backup duy nhất, đặc biệt khi dùng `--link`.

## 9. Chọn thời gian maintenance window

`pg_upgrade` thường yêu cầu dừng application writes và các PostgreSQL services liên quan để thực hiện bước upgrade.

Thời gian maintenance phụ thuộc:

- Dung lượng relation files.
- Phương pháp copy/link/clone.
- Số lượng database và objects.
- Số jobs song song.
- Số lượng extensions và kiểm tra.
- Thời gian post-upgrade ANALYZE.
- Thời gian validation và smoke tests.
- Tốc độ storage và network nếu tablespaces ở volume khác.

Chạy rehearsal trên bản sao production-like để đo thời gian. Không ước lượng maintenance window chỉ từ thời gian chạy pg_upgrade mà bỏ qua analyze, validation và application cutover.

## 10. Các chế độ chuyển relation files

`pg_upgrade` cung cấp nhiều lựa chọn tùy phiên bản:

| Mode | Cơ chế | Tốc độ/dung lượng | Old cluster sau khi new start |
|---|---|---|---|
| Copy | Copy file độc lập | Tốn thêm dung lượng, phụ thuộc throughput | Giữ nguyên bản cũ |
| Link | Hard link cùng inode | Rất nhanh, ít tốn thêm blocks | Không còn an toàn để chạy |
| Clone | Reflink/copy-on-write | Thường nhanh, tiết kiệm blocks ban đầu | Vẫn độc lập |
| Copy-file-range | Kernel-assisted file copy | Có thể nhanh hơn copy thông thường | Vẫn độc lập |

Khả năng hỗ trợ phụ thuộc PostgreSQL version, OS và filesystem. Hãy xác nhận option bằng `pg_upgrade --help` của target binaries.

## 11. Mode copy

Copy là phương pháp thông thường và thường là default nếu không chỉ định mode khác.

Trong copy mode:

1. `pg_upgrade` chuẩn bị relation files cho cluster mới.
2. Dữ liệu được copy sang các file mới.
3. Old cluster giữ nguyên các files gốc.
4. New cluster có bản files độc lập.

Ưu điểm:

- Old cluster vẫn giữ dữ liệu gốc.
- Dễ giữ một bản frozen để đối chiếu hoặc rollback trước khi new cluster nhận writes.
- Không cần filesystem hỗ trợ hard links/reflinks.
- Không chia sẻ inode giữa hai clusters.

Nhược điểm:

- Cần đủ dung lượng cho old và new data cùng tồn tại.
- Thời gian phụ thuộc lượng dữ liệu phải copy và throughput storage.
- Copy lớn có thể tạo nhiều I/O và kéo dài maintenance window.

Copy là lựa chọn dễ hiểu nhất khi ưu tiên tính an toàn và khả năng quay lại.

## 12. Mode link

`--link` yêu cầu `pg_upgrade` dùng hard links cho các files phù hợp thay vì copy nội dung.

Ví dụ:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --link
~~~

Hard link là một tên file khác trỏ tới cùng inode. Hai đường dẫn old/new không đại diện hai bản dữ liệu độc lập.

Ưu điểm:

- Rất nhanh với cluster lớn.
- Không cần copy toàn bộ relation data.
- Dung lượng tăng thêm ban đầu thấp.

Nhược điểm và rủi ro:

- Old/new data files chia sẻ inode.
- Hai data directories phải nằm trên filesystem cho phép hard links giữa chúng; thông thường cần cùng filesystem.
- Khi new cluster được khởi động và ghi dữ liệu, các file được chia sẻ thay đổi.
- Old cluster không thể được khởi động như một bản rollback độc lập sau khi new cluster đã chạy.

**Không dùng link mode nếu cần giữ old cluster để chạy lại sau khi new cluster bắt đầu nhận writes.**

## 13. Ranh giới rollback của link mode

Cần phân biệt hai thời điểm:

1. `pg_upgrade` đã hoàn tất nhưng new cluster chưa được khởi động.
2. New cluster đã được khởi động và bắt đầu hoạt động.

Với link mode, trước khi new cluster khởi động, có thể còn khả năng bỏ bản new cluster và quay lại old cluster theo đúng recovery procedure của phiên bản/công cụ. Nhưng sau khi new cluster bắt đầu ghi vào các hard-linked files, old cluster không còn là bản dữ liệu độc lập.

Vì vậy, không coi link mode có rollback thông thường. Phải có backup độc lập và phải xác định rõ điểm không thể quay lại trước khi thực hiện.

## 14. Mode clone

`--clone` dùng filesystem copy-on-write (reflink) nếu filesystem hỗ trợ.

Ví dụ:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --clone
~~~

Với reflink, filesystem tạo một bản sao file logic mới nhưng có thể chia sẻ physical extents ban đầu. Khi một bên ghi, filesystem tạo bản copy-on-write cho những blocks thay đổi.

Ưu điểm:

- Nhanh hơn copy đầy đủ trong nhiều trường hợp.
- Không dùng chung inode như hard links.
- Old cluster vẫn có thể được giữ nguyên về mặt dữ liệu.
- Dung lượng ban đầu có thể thấp, tăng theo blocks bị thay đổi.

Nhược điểm:

- Cần filesystem và storage stack hỗ trợ reflink/copy-on-write clone.
- Không phải mọi mount, volume, network filesystem hoặc storage driver đều hỗ trợ.
- Dung lượng có thể tăng đáng kể khi hai clusters thay đổi nhiều blocks.
- Phải kiểm tra hành vi của filesystem thực tế, không chỉ loại filesystem trên lý thuyết.

Clone là lựa chọn hấp dẫn khi muốn tốc độ gần link mode nhưng vẫn giữ hai clusters độc lập.

## 15. Mode copy-file-range

Một số phiên bản `pg_upgrade` hỗ trợ `--copy-file-range` để dùng syscall/cơ chế kernel copy file ranges.

Ví dụ:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --copy-file-range
~~~

Cơ chế này yêu cầu kernel/filesystem hỗ trợ phù hợp. Nó vẫn tạo file copy độc lập, khác với hard-link sharing.

Lợi ích thực tế phụ thuộc kernel, filesystem, storage backend và kích thước files. Nếu option không được binary hỗ trợ hoặc filesystem không đáp ứng, upgrade có thể thất bại. Không giả định tự động fallback sang copy mode.

## 16. Chọn mode theo ưu tiên

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Ưu tiên rollback và có đủ disk | Copy |
| Cần nâng cấp nhanh, chấp nhận không dùng old cluster sau khi new start | Link |
| Filesystem hỗ trợ reflink và muốn giữ old cluster độc lập | Clone |
| Muốn copy độc lập với kernel-assisted transfer | Copy-file-range nếu được hỗ trợ |
| Không chắc filesystem hỗ trợ gì | Copy |

Không chọn mode chỉ vì tốc độ. Hãy xem backup, rollback requirement, filesystem, free space và recovery objectives.

## 17. Ước lượng dung lượng đĩa

Trước upgrade, ước lượng:

- Tổng relation data files.
- Index files.
- TOAST relations.
- Tablespaces.
- WAL cần thiết cho old/new cluster.
- Temporary files và logs.
- Backup/snapshot overhead.
- Dung lượng tăng thêm khi new cluster hoạt động.

Copy mode thường cần không gian cho cả hai bản dữ liệu. Link mode tiết kiệm blocks ban đầu nhưng có giới hạn rollback. Clone mode chia sẻ extents copy-on-write và tăng dung lượng theo mức độ thay đổi. Copy-file-range tạo file độc lập nên vẫn cần không gian cho bản mới.

Để xem dung lượng database:

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Database size không bao gồm mọi yếu tố vận hành như WAL archive, logs, external tablespaces và backup retention. Kiểm tra filesystem riêng.

## 18. Tablespaces

Tablespaces có thể đặt relation files trên các filesystems/volumes khác nhau.

Trước upgrade:

- Ghi nhận mọi tablespace và location.
- Xác minh old/new OS account có quyền truy cập.
- Đảm bảo volume còn đủ dung lượng.
- Kiểm tra mode link có thể tạo hard links trên từng location liên quan.
- Kiểm tra reflink support nếu dùng clone.
- Không di chuyển hoặc xóa tablespace directories trong lúc upgrade.

Các giới hạn của filesystem có thể khác nhau giữa data directory và tablespace mounts. Kiểm tra tất cả locations, không chỉ filesystem chứa PGDATA.

## 19. Chuẩn bị cluster mới bằng initdb

Khởi tạo data directory mới bằng `initdb` của target version.

Ví dụ minh họa:

~~~bash
/usr/lib/postgresql/17/bin/initdb \
  -D /var/lib/postgresql/17/main \
  --encoding=UTF8 \
  --locale=en_US.UTF-8
~~~

Các tham số initdb quan trọng phải tương thích với old cluster theo yêu cầu của target version:

- Encoding.
- Locale/collation provider và locale settings.
- Data checksums.
- WAL segment size khi có yêu cầu tương thích.
- Block size và các build-time characteristics.
- Authentication bootstrap và superuser phù hợp.

Không dùng nguyên ví dụ locale trên cho mọi môi trường. Lấy giá trị từ old cluster và kiểm tra documentation của phiên bản đích.

## 20. Không copy nguyên postgresql.conf một cách mù quáng

Configuration files của old cluster không tự động trở thành cấu hình tốt cho new cluster.

Sau upgrade, cần review:

- `postgresql.conf`.
- `pg_hba.conf`.
- `pg_ident.conf`.
- `postgresql.auto.conf`.
- SSL certificates/keys.
- `shared_preload_libraries`.
- Extension-specific settings.
- Replication settings.
- Archive/restore commands.
- Logging settings.
- Memory/cost parameters.
- Deprecated/removed parameters.

Một số settings có thể đổi tên, bị loại bỏ hoặc thay đổi semantics. Dùng startup logs và `pg_settings` để kiểm tra cấu hình mới.

## 21. Extensions phải có binaries cho target version

Extension thường có:

- SQL scripts.
- Control file.
- Shared library/native binary.
- Version-specific dependencies.

Trước khi chạy `pg_upgrade`, cài phiên bản extension tương thích với target PostgreSQL. Nếu thiếu library hoặc control file, kiểm tra/upgrade có thể thất bại hoặc extension không load được sau khi khởi động.

Inventory extensions:

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Sau upgrade, kiểm tra extension update paths và chạy `ALTER EXTENSION ... UPDATE` khi cần và khi version hỗ trợ.

## 22. Kiểm tra extension update paths

Trên cluster mới, sau khi cài package extension phù hợp, kiểm tra available versions bằng catalog:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Đối với từng extension, xác minh target version tương thích. Không giả định việc `pg_upgrade` thành công đồng nghĩa extension đã được nâng cấp SQL objects lên phiên bản mới nhất.

## 23. Kiểm tra trước bằng --check

Chạy `pg_upgrade --check` trước maintenance window để phát hiện incompatibilities.

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --check
~~~

`--check` thực hiện các kiểm tra khả năng upgrade mà không hoàn tất quá trình chuyển dữ liệu. Một số kiểm tra có thể cần khởi động các temporary server instances nội bộ.

Chạy lại `--check` sau khi sửa blockers và trước actual upgrade. Đọc toàn bộ output/log thay vì chỉ xem exit code.

## 24. Các loại blocker thường gặp

- Old version không được target hỗ trợ.
- Extension thiếu library hoặc update path.
- Prepared transactions còn tồn tại.
- Logical replication objects/slots có điều kiện version-specific.
- Invalid indexes hoặc catalog inconsistencies.
- Tablespace path không truy cập được.
- Locale/collation mismatch.
- User-defined data types hoặc objects cần xử lý.
- Free disk space không đủ.
- Cluster không thể shutdown sạch.

`pg_upgrade` có thể báo một số điều kiện cụ thể theo version. Hãy giải quyết theo message và tài liệu tương ứng, không bỏ qua cảnh báo.

## 25. Prepared transactions

Prepared transactions có thể tồn tại khi dùng two-phase commit.

Kiểm tra:

~~~sql
SELECT *
FROM pg_prepared_xacts;
~~~

Trước upgrade cần xử lý prepared transactions theo quyết định nghiệp vụ: `COMMIT PREPARED` hoặc `ROLLBACK PREPARED` phù hợp.

Không tự động rollback tất cả prepared transactions chỉ để làm `pg_upgrade` chạy; cần phối hợp với transaction coordinator và ứng dụng.

## 26. Large objects và database objects

Lập inventory các object cần xác minh:

- Databases và schemas.
- Tables, indexes và constraints.
- Sequences.
- Large objects.
- Roles, memberships và grants.
- Tablespaces.
- Extensions.
- Foreign data wrappers/servers.
- Publications/subscriptions và replication slots.
- Event triggers và procedural languages.
- Collations và operator classes.

`pg_upgrade` xử lý nhiều database objects trong cluster upgrade, nhưng một số external dependencies và extension-specific behaviors cần chuẩn bị riêng. Đọc release notes cho các major versions đi qua.

## 27. Dừng workload trước actual upgrade

Trước khi thực hiện:

1. Dừng ứng dụng ghi dữ liệu.
2. Dừng background workers/jobs có thể kết nối.
3. Tắt schedulers hoặc ETL jobs.
4. Xác nhận không còn client writes.
5. Dừng PostgreSQL old cluster sạch sẽ.
6. Đảm bảo new cluster chưa được khởi động như service.
7. Xác nhận data directories và tablespaces đúng.

Không để connection manager tự reconnect vào old cluster trong lúc đang nâng cấp.

## 28. Dừng PostgreSQL

Cách dừng phụ thuộc cách cài đặt.

Ví dụ dùng `pg_ctl`:

~~~bash
/usr/lib/postgresql/16/bin/pg_ctl \
  -D /var/lib/postgresql/16/main \
  -m fast stop
~~~

Hoặc dùng service manager của hệ điều hành. Sau khi dừng, xác minh process đã kết thúc và không có PostgreSQL process khác đang sử dụng data directory.

Không xóa PID file hoặc kill process một cách tùy tiện để giả vờ server đã shutdown sạch.

## 29. Chạy actual upgrade bằng copy mode

Ví dụ minh họa:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --copy
~~~

Các tham số:

- `-b`: old binary directory.
- `-B`: new binary directory.
- `-d`: old data directory.
- `-D`: new data directory.
- `--jobs`: số jobs song song cho những bước hỗ trợ parallelism.
- `--copy`: yêu cầu copy mode nếu binary hỗ trợ explicit option.

Có thể bỏ `--copy` nếu đó là default của version. Luôn kiểm tra help và documentation của binary đích.

## 30. Chạy actual upgrade bằng link mode

Chỉ dùng khi đã quyết định rõ rollback implications:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --link
~~~

Trước khi chạy, xác minh old/new data directories và các relation locations đáp ứng hard-link requirements.

Không khởi động old cluster sau khi new cluster đã bắt đầu ghi vào linked files.

## 31. Chạy actual upgrade bằng clone mode

Nếu filesystem hỗ trợ reflink:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --clone
~~~

Kiểm tra filesystem và storage backend trong môi trường staging. Nếu clone không hỗ trợ, chuyển sang copy mode sau khi xử lý trạng thái cluster và chuẩn bị lại theo hướng dẫn của công cụ.

Không giả định `--clone` sẽ tự chuyển sang `--copy` khi không có reflink.

## 32. Chạy actual upgrade bằng copy-file-range

Nếu target `pg_upgrade` hỗ trợ:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --copy-file-range
~~~

Mode này vẫn tạo files độc lập. Tốc độ thực tế phụ thuộc kernel/filesystem/storage. Xác minh option và hỗ trợ bằng `pg_upgrade --help` cùng tài liệu target version.

## 33. Jobs và parallelism

`--jobs` cho phép chạy nhiều bước upgrade song song khi công cụ hỗ trợ.

Tăng jobs có thể giảm thời gian, nhưng cũng làm tăng:

- Disk I/O concurrency.
- CPU utilization.
- Memory pressure.
- Metadata operations.
- Load trên tablespace volumes.

Không mặc định số jobs bằng số CPU cores. Đo throughput và latency trên staging; với storage yếu, nhiều jobs có thể làm tổng thời gian dài hơn.

## 34. Log và output của pg_upgrade

Đọc output terminal và log files do `pg_upgrade` tạo.

Các thông tin cần lưu:

- Version old/new.
- Command line và mode.
- Thời gian bắt đầu/kết thúc.
- Số jobs.
- Check results.
- Warnings/errors.
- Những objects cần xử lý thủ công.
- Generated scripts.

Giữ log như một phần upgrade record. Không xóa thư mục log trước khi validation và rollback window kết thúc.

## 35. Generated scripts sau upgrade

`pg_upgrade` thường tạo scripts hỗ trợ các bước hậu nâng cấp, chẳng hạn:

- Script chạy ANALYZE để xây dựng planner statistics.
- Script xóa old cluster khi người vận hành quyết định đã an toàn.

Tên script và nội dung phụ thuộc version/OS. Đọc file thực tế được tạo thay vì giả định tên hoặc chạy tự động.

Không chạy script xóa old cluster trước khi đã xác minh new cluster và hoàn tất rollback decision.

## 36. Khởi động cluster mới lần đầu

Sau khi `pg_upgrade` báo thành công:

1. Review configuration mới.
2. Kiểm tra `shared_preload_libraries` và extension libraries.
3. Kiểm tra port/socket và data directory.
4. Đảm bảo application traffic vẫn chưa chuyển vào.
5. Khởi động new cluster bằng đúng binaries target.
6. Đọc startup logs.
7. Kiểm tra `SELECT version()` và `pg_is_in_recovery()` theo topology.

Ví dụ:

~~~bash
/usr/lib/postgresql/17/bin/pg_ctl \
  -D /var/lib/postgresql/17/main \
  -l /var/log/postgresql/postgresql-17.log \
  start
~~~

Không mở application writes trước khi hoàn tất các kiểm tra bắt buộc.

## 37. Kiểm tra version và database list

Trên new cluster:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY datname;
~~~

So sánh inventory với old cluster:

- Database names.
- Database owners.
- Tablespaces.
- Roles.
- Extension list.
- Object counts và các business invariants.

Kích thước có thể khác do catalog/index representation hoặc hoạt động sau upgrade; chênh lệch cần được giải thích, không kết luận chỉ bằng size.

## 38. Chạy ANALYZE sau upgrade

Planner statistics cần được thu thập lại để planner chọn plans phù hợp.

Một cách phổ biến:

~~~bash
/usr/lib/postgresql/17/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

`--analyze-in-stages` thu thập statistics theo các giai đoạn để database sớm có mức statistics hữu ích trong khi quá trình phân tích toàn diện tiếp tục.

Kiểm tra options trên `vacuumdb --help` của target version. Với database lớn, ANALYZE có thể tạo tải đáng kể; theo dõi CPU/I/O và điều chỉnh jobs.

## 39. Extension update sau upgrade

Sau khi server mới chạy và extension libraries đã cài:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Nếu extension có update script cần áp dụng:

~~~sql
ALTER EXTENSION extension_name UPDATE;
~~~

Tên extension và version phải được xác định từ package/vendor documentation. Không chạy UPDATE cho mọi extension một cách mù quáng nếu extension không có update path phù hợp.

Kiểm tra functions, operators, types và dependent applications.

## 40. Collation version và reindex considerations

Thay đổi OS libraries hoặc collation provider/version có thể ảnh hưởng thứ tự sắp xếp của text values.

Sau upgrade:

- Xem collation version metadata.
- Kiểm tra cảnh báo collation mismatch trong logs.
- Xác định indexes phụ thuộc collations bị ảnh hưởng.
- Thực hiện refresh/reindex theo hướng dẫn PostgreSQL và kế hoạch maintenance.

Không bỏ qua collation warnings, vì index ordering có thể không còn tương thích với collation behavior hiện tại.

## 41. Configuration review

So sánh old/new settings:

- Memory: `shared_buffers`, `work_mem`, `maintenance_work_mem`.
- Planner: `effective_cache_size`, `random_page_cost`, `seq_page_cost`.
- Connections: `max_connections`.
- WAL: `wal_level`, `max_wal_size`, `checkpoint_timeout`.
- Replication: `max_wal_senders`, `max_replication_slots`, `hot_standby`.
- Logging: `log_min_duration_statement`, `log_line_prefix`.
- Autovacuum.
- SSL/authentication.
- Extensions và custom GUCs.

Không copy nguyên giá trị chỉ vì cluster cũ đã dùng lâu. Defaults và behavior có thể thay đổi giữa major versions; review release notes và benchmark.

## 42. Kiểm tra schema và objects

Có thể kiểm tra object counts ở mức database:

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

Kiểm tra invalid indexes:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx
  ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
  ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Kết hợp với application-level validation và catalog inventory trước upgrade.

## 43. Kiểm tra roles và privileges

`pg_upgrade` chuyển nhiều cluster-wide objects, nhưng cần xác minh:

- Roles và role memberships.
- Database owners.
- Schema/table/sequence grants.
- Default privileges.
- Tablespace privileges.
- Replication roles.
- Login attributes.
- Password/authentication behavior.

Ví dụ:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolcanlogin
FROM pg_roles
ORDER BY rolname;
~~~

Đừng xuất mật khẩu hoặc secret vào log. Kiểm tra grants bằng catalog/psql và thử login từ application roles.

## 44. Replication và HA sau major upgrade

Nếu cluster nằm trong HA topology:

- Lập kế hoạch nâng cấp primary và standby theo quy trình được hỗ trợ cho HA manager.
- Không để standby cũ kết nối vào primary mới bằng giả định WAL formats tương thích.
- Xác định có thể reuse/rebuild standby hay phải tạo lại từ base backup.
- Cập nhật replication slots và connection strings theo topology.
- Kiểm tra archive_command/restore_command.
- Cập nhật HA manager, monitoring và service endpoints.
- Diễn tập failover sau upgrade.

Một cách thường dùng là upgrade/promote primary theo quy trình, sau đó rebuild/reseed standbys từ primary mới. Cách cụ thể phụ thuộc replication setup và công cụ HA; không tự nâng từng node độc lập nếu chưa có runbook.

## 45. Logical replication và các external consumers

Nếu cluster dùng logical replication hoặc CDC:

- Inventory publications và subscriptions.
- Kiểm tra logical replication slots.
- Xác minh connector/CDC tool hỗ trợ target major version.
- Kiểm tra replication protocol và plugin compatibility.
- Xác minh consumer offsets/LSNs.
- Kiểm tra retention và WAL growth trong thời gian downtime.
- Lập kế hoạch restart/recreate consumers nếu cần.

Không giả định tất cả external consumers tiếp tục hoạt động chỉ vì database đã mở được.

## 46. Kiểm tra application compatibility

Database server chạy được chưa đủ. Kiểm tra:

- Driver/JDBC/libpq versions.
- ORM behavior.
- Deprecated SQL features.
- Data type and protocol behavior.
- Query plans và latency.
- Authentication/TLS.
- Connection pool.
- Stored procedures/extensions.
- Background jobs.
- Backup/monitoring agents.

Chạy smoke tests và representative workload trên staging trước khi chuyển production traffic.

## 47. Rollback với copy mode

Copy mode giữ old cluster files độc lập. Nếu validation thất bại trước khi cho phép writes trên new cluster:

1. Dừng new cluster.
2. Giữ new data directory để điều tra.
3. Khởi động old cluster bằng old binaries.
4. Trả endpoint về old cluster.
5. Khôi phục ứng dụng theo runbook.

Nếu new cluster đã nhận writes, old cluster không chứa những thay đổi mới. Rollback khi đó cần data reconciliation hoặc restore/replay theo thiết kế; không thể chỉ đổi endpoint và kỳ vọng không mất writes.

Copy mode giữ khả năng quay lại **trạng thái cũ tại thời điểm upgrade**, không tự đồng bộ writes phát sinh trên cluster mới.

## 48. Rollback với clone mode

Clone mode tạo bản copy-on-write độc lập. Old cluster có thể được giữ làm frozen fallback.

Tuy vậy, nếu new cluster đã nhận writes, old cluster vẫn thiếu những thay đổi đó. Cần chọn authoritative data và xử lý write divergence trước khi quay lại.

Đừng nhầm khả năng khởi động old cluster với khả năng rollback ứng dụng không mất dữ liệu.

## 49. Rollback với link mode

Link mode có ranh giới rollback nghiêm ngặt:

- Trước khi new cluster start: có thể còn phương án bỏ new cluster và quay lại old cluster theo recovery procedure phù hợp.
- Sau khi new cluster start/ghi dữ liệu: old cluster không còn độc lập vì các files chia sẻ hard links.

Không thử khởi động old cluster sau khi new cluster đã ghi vào linked files. Dùng backup độc lập để phục hồi nếu cần.

## 50. Kiểm thử rollback trước production

Trong rehearsal:

1. Restore backup old cluster.
2. Chạy `pg_upgrade --check`.
3. Thực hiện upgrade với mode dự kiến.
4. Khởi động new cluster.
5. Chạy smoke tests.
6. Mô phỏng lỗi theo rollback plan.
7. Đo thời gian rollback.
8. Xác minh data consistency.
9. Ghi lại điểm không thể quay lại của mode đã chọn.

Nếu chọn link, rehearsal phải chứng minh quy trình backup/restore độc lập, không dựa vào old data directory sau khi new cluster start.

## 51. Các dấu hiệu upgrade chưa hoàn tất

Chưa nên mở production writes nếu còn một trong các tình trạng:

- Startup logs có lỗi extension/library.
- Database hoặc tablespace thiếu.
- Role/application login thất bại.
- Index invalid hoặc object dependency lỗi.
- Collation mismatch chưa xử lý.
- Planner statistics chưa được thu thập đủ.
- Replication/backup/monitoring chưa hoạt động.
- Application smoke tests chưa đạt.
- Chưa xác định được rollback boundary.

Đánh dấu upgrade complete sau khi các owner của database, application và operations xác nhận checklist.

## 52. Những sai lầm thường gặp

### 52.1. Dùng pg_upgrade cho minor update

Sai. Minor release trong cùng major thường không cần chuyển data directory bằng pg_upgrade.

### 52.2. Chạy pg_upgrade mà không backup

Rủi ro cao. Upgrade thay đổi cluster mới và có thể làm old cluster không còn dùng được tùy mode.

### 52.3. Chọn link chỉ vì nhanh

Sai. Link mode làm mất khả năng dùng old cluster độc lập sau khi new cluster start.

### 52.4. Nghĩ clone giống hard link

Sai. Clone copy-on-write tạo file logic độc lập; hard link chia sẻ cùng inode.

### 52.5. Nghĩ copy mode tự rollback mọi writes mới

Sai. Old cluster là snapshot tại thời điểm upgrade; nó không nhận writes trên new cluster.

### 52.6. Bỏ qua filesystem của tablespaces

Sai. Mỗi tablespace có thể nằm trên volume khác và có giới hạn link/clone riêng.

### 52.7. Không cài extension binaries cho target

Sai. SQL objects có thể còn đó nhưng shared libraries/control files không tương thích hoặc không có.

### 52.8. Không chạy ANALYZE sau upgrade

Planner statistics có thể chưa phù hợp; query plans có thể kém cho tới khi thu thập lại.

### 52.9. Copy nguyên configuration cũ

Sai. Settings có thể đổi semantics hoặc bị loại bỏ giữa major versions.

### 52.10. Mở traffic ngay sau khi postgres start

Sai. Cần kiểm tra extensions, roles, schema, replication, backup và application behavior.

## 53. Lab: chuẩn bị hai clusters

Trong hai PostgreSQL lab installations:

1. Cài old và target binaries.
2. Tạo old cluster và thêm database/table/index.
3. Tạo backup có thể restore.
4. Khởi tạo new cluster bằng target `initdb`.
5. Cài extension packages cho target.
6. Ghi lại ports, data directories và tablespaces.

Xác nhận `pg_upgrade --help` hiển thị các options cần dùng.

## 54. Lab: chạy --check

~~~bash
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check
~~~

Ghi lại:

- Check result.
- Warnings/errors.
- Log file path.
- Những extension hoặc objects cần xử lý.
- Disk/filesystem requirements.

Sửa blockers rồi chạy lại `--check`.

## 55. Lab: so sánh copy và link

Thực hiện trên hai bản lab riêng biệt, mỗi bản được restore từ cùng một backup:

- Lab A: dùng `--copy`.
- Lab B: dùng `--link`.

Ghi lại thời gian, dung lượng filesystem trước/sau và behavior của old cluster.

Không dùng chung một old data directory cho hai lần thử liên tiếp nếu lần link đã làm old/new files chia sẻ inode và new cluster đã start.

## 56. Lab: thử clone

Nếu filesystem hỗ trợ reflink:

1. Tạo hai clusters trên storage hỗ trợ clone.
2. Chạy `pg_upgrade --check`.
3. Chạy actual upgrade với `--clone`.
4. Quan sát dung lượng trước/sau.
5. Ghi nhận copy-on-write growth sau khi new cluster thay đổi dữ liệu.
6. Xác minh old cluster vẫn độc lập theo filesystem semantics.

Nếu storage không hỗ trợ, ghi nhận lỗi và thử copy mode.

## 57. Lab: post-upgrade validation

Trên new cluster:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname))
FROM pg_database
ORDER BY datname;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

SELECT pg_is_in_recovery();
~~~

Chạy ANALYZE, kiểm tra roles, tablespaces, indexes, representative queries và application smoke tests.

## 58. Lab: diễn tập rollback

Với copy mode:

1. Upgrade từ bản restore.
2. Chưa cho application writes vào new cluster.
3. Dừng new cluster.
4. Khởi động old cluster.
5. Xác minh ứng dụng có thể kết nối và dữ liệu cũ nguyên vẹn.

Sau đó thực hiện một rehearsal khác cho tình huống new cluster đã nhận writes và ghi rõ cách reconcile dữ liệu.

Với link mode, chỉ kiểm tra old cluster trước khi new cluster start; sau khi new cluster start, không khởi động old cluster.

## 59. Checklist production upgrade

**Trước maintenance**

1. Xác định source/target major versions được hỗ trợ.
2. Đọc release notes và pg_upgrade docs.
3. Inventory databases, roles, tablespaces và extensions.
4. Xác minh backup/restore và WAL archive.
5. Rehearse trên bản sao production-like.
6. Chọn copy/link/clone/copy-file-range theo rollback, disk và filesystem.
7. Cài target binaries và extension packages.
8. Initdb cluster mới với compatible settings.
9. Chạy `pg_upgrade --check`.
10. Chốt maintenance window và rollback boundary.

**Trong maintenance**

11. Dừng writes và scheduled jobs.
12. Shutdown old cluster sạch.
13. Xác nhận data directories và tablespaces.
14. Chạy actual pg_upgrade.
15. Lưu logs và generated scripts.
16. Review configuration mới.
17. Start new cluster và đọc logs.

**Sau upgrade**

18. Chạy ANALYZE theo kế hoạch.
19. Update extensions khi cần.
20. Kiểm tra roles, grants, databases, tablespaces và objects.
21. Kiểm tra collation/index warnings.
22. Khôi phục backup, monitoring và replication.
23. Chạy application smoke tests và representative workload.
24. Chuyển traffic sau khi được xác nhận.
25. Chỉ xóa old cluster sau khi rollback window kết thúc.

## 60. Câu hỏi thường gặp

### pg_upgrade có dùng cho minor version upgrade không?

Thông thường không. Minor update cùng major version thường thay binaries/packages theo quy trình phù hợp, không cần pg_upgrade.

### pg_upgrade có copy từng row qua SQL không?

Không theo cách dump/restore thông thường. Nó chuyển relation files tương thích và cập nhật catalog metadata cho target major version.

### Copy mode có giữ old cluster không?

Có. Nó giữ file dữ liệu cũ độc lập, nhưng old cluster chỉ phản ánh trạng thái trước upgrade và không nhận writes từ new cluster.

### Link mode có cần cùng filesystem không?

Hard links yêu cầu old/new file locations hỗ trợ link trên cùng filesystem. Kiểm tra cả data directory và tablespaces.

### Có thể chạy old cluster sau khi new cluster start trong link mode không?

Không an toàn. Hai cluster chia sẻ inode; new cluster có thể đã thay đổi files.

### Clone khác link thế nào?

Clone dùng copy-on-write/reflink để tạo file logic độc lập; link dùng hard links trỏ tới cùng inode.

### Clone có được hỗ trợ trên mọi filesystem không?

Không. Cần filesystem/storage hỗ trợ reflink và option có trong pg_upgrade target version.

### Copy-file-range có chia sẻ dữ liệu với old cluster không?

Không. Đây là cách kernel-assisted copy tạo files độc lập, khác hard-link mode.

### Có thể dùng nhiều jobs không?

Có thể dùng `--jobs` cho các bước hỗ trợ parallelism. Cần cân bằng CPU và I/O capacity.

### pg_upgrade có tự copy postgresql.conf không?

Không nên giả định configuration được migrate tự động. Review và chuẩn bị các config files cho target version.

### Extensions có cần cài lại không?

Cần có binaries/control files tương thích target trước khi upgrade. Sau upgrade, có thể cần `ALTER EXTENSION ... UPDATE`.

### Vì sao cần ANALYZE sau upgrade?

Planner statistics cần được thu thập lại để estimated rows và plan choices phản ánh dữ liệu hiện tại.

### Có thể rollback sau khi new cluster đã nhận writes không?

Old cluster không có các writes mới. Cần reconcile/replay hoặc restore theo kế hoạch; không chỉ đổi endpoint.

### pg_upgrade có tự rebuild standby không?

Không nên giả định. HA topology cần quy trình riêng để rebuild/rejoin standbys theo target version và HA manager.

### Khi nào được xóa old cluster?

Sau khi new cluster và ứng dụng đã được xác minh, backup mới được kiểm chứng, replication/monitoring ổn định và rollback window kết thúc.

## 61. Tổng kết

Các command patterns quan trọng:

~~~bash
# Kiểm tra options của binary đích.
/path/to/new/bin/pg_upgrade --help

# Kiểm tra khả năng upgrade.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check

# Copy mode.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --copy

# Link mode: chỉ dùng khi chấp nhận old cluster không còn dùng được sau khi new start.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --link

# Clone mode: yêu cầu reflink support.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --clone

# Post-upgrade statistics.
/path/to/new/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

Những nguyên tắc cần nhớ:

1. `pg_upgrade` dành cho major version upgrades; minor updates thường không cần.
2. Dùng binary `pg_upgrade` của target version.
3. Old/new clusters cần đáp ứng compatibility requirements của target.
4. Chạy `--check` trước actual upgrade và giải quyết mọi blockers.
5. Copy mode tạo file độc lập và giữ old cluster nguyên vẹn.
6. Link mode nhanh và tiết kiệm dung lượng nhưng hard-link sharing làm old cluster không an toàn sau khi new cluster start.
7. Clone mode dùng reflink/copy-on-write nếu filesystem hỗ trợ và giữ hai clusters độc lập.
8. Copy-file-range tăng tốc file copy trên những môi trường hỗ trợ nhưng vẫn tạo file độc lập.
9. Tính cả tablespaces và disk capacity khi chọn mode.
10. Backup và restore rehearsal là điều kiện quan trọng trước production upgrade.
11. Cài extension binaries cho target version trước khi chạy.
12. Review configuration files và deprecated settings sau upgrade.
13. Chạy ANALYZE để planner có statistics phù hợp.
14. Xác minh extensions, roles, privileges, collation, indexes và application behavior.
15. Rebuild/rejoin standbys theo HA runbook.
16. Old cluster ở copy/clone mode là frozen fallback; writes mới trên new cluster không tự xuất hiện ở old.
17. Link mode có điểm không thể quay lại khi new cluster start/ghi dữ liệu.
18. Chỉ xóa old cluster sau khi validation và rollback window kết thúc.

Sơ đồ lựa chọn:

~~~text
Cần major version upgrade?
             |
             v
    Backup + restore rehearsal
             |
             v
      pg_upgrade --check
             |
             v
    Chọn file transfer mode
             |
       +-----+------+----------------+
       |            |                |
       v            v                v
     Copy          Link            Clone
       |            |                |
       v            v                v
  Files độc lập  Hard links       Reflink/COW
  Tốn disk       Rất nhanh        Cần FS support
  Old giữ được   Old mất độc lập  Old giữ độc lập
       |            |                |
       +-----+------+----------------+
             |
             v
       Actual pg_upgrade
             |
             v
    Start new cluster + logs
             |
             v
  Analyze + extensions + config
             |
             v
   Validate DB + application + HA
             |
             v
       Cutover traffic
             |
             v
   Hết rollback window và đủ backup?
             |
             v
       Xóa old cluster có kiểm soát
~~~

**Kết luận:** `pg_upgrade` giúp major version upgrade nhanh bằng cách chuyển relation files và cập nhật catalogs. Chọn mode dựa trên filesystem, dung lượng, thời gian downtime và rollback requirement: **copy ưu tiên tính độc lập, link ưu tiên tốc độ nhưng mất old-cluster rollback sau khi new cluster khởi động, clone cân bằng tốc độ và khả năng giữ old cluster khi reflink được hỗ trợ, còn copy-file-range tăng tốc copy mà vẫn giữ file độc lập**. Một lần nâng cấp chỉ hoàn tất khi cluster mới, extensions, configuration, planner statistics, replication và ứng dụng đều được xác minh.
