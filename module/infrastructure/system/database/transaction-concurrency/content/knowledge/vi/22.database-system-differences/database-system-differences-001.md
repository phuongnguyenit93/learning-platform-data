# Lập ma trận bảo đảm theo phiên bản, storage engine và cấu hình thực tế

Tên hệ quản trị và mức cô lập được ghi trong tài liệu chưa đủ để kết luận ứng dụng đang nhận được bảo đảm đồng thời nào. Cùng một sản phẩm có thể thay đổi hành vi theo phiên bản, storage engine, loại bảng, cấu hình cấp database, isolation level của session và câu lệnh thực tế. Một kết nối trong connection pool còn có thể được ứng dụng đặt isolation level khác với giá trị mặc định của server.

Vì vậy, khi thiết kế hoặc điều tra lỗi đồng thời, hãy lập **ma trận bảo đảm cho đúng môi trường triển khai**. Ma trận ghi lại phiên bản và engine đang chạy, cấu hình có hiệu lực, hiện tượng được ngăn chặn, các điều kiện cần thiết và bằng chứng kiểm chứng. Nó giúp nhóm phát triển trả lời những câu hỏi cụ thể: truy vấn đọc có dùng snapshot hay khóa chia sẻ, phantom có thể xuất hiện không, write skew có được ngăn không, thao tác tìm hàng chưa tồn tại được bảo vệ ra sao, và ứng dụng cần retry loại lỗi nào.

## 1. Vì sao không thể chỉ ghi tên database và isolation level?

Các tên như READ COMMITTED, REPEATABLE READ và SERIALIZABLE là điểm bắt đầu để mô tả hành vi. Chúng không phải bản mô tả đầy đủ về mọi cơ chế bên trong từng sản phẩm.

Ví dụ:

- PostgreSQL dùng MVCC. READ UNCOMMITTED được xử lý như READ COMMITTED; REPEATABLE READ dùng snapshot isolation và ngăn phantom read theo cách triển khai của PostgreSQL, nhưng vẫn có thể xảy ra write skew. SERIALIZABLE bổ sung Serializable Snapshot Isolation (SSI) và có thể hủy transaction khi phát hiện lịch chạy không tuần tự hóa được.
- MySQL 8.4 có mặc định REPEATABLE READ cho InnoDB. Locking read trên unique index với điều kiện tìm duy nhất có phạm vi khóa khác với range scan. MySQL còn có storage engine khác; MyISAM không hỗ trợ transaction, savepoint hoặc XA như InnoDB.
- SQL Server có thể chạy READ COMMITTED bằng shared lock hoặc row versioning tùy tùy chọn READ_COMMITTED_SNAPSHOT của database. SNAPSHOT là mức riêng và cần ALLOW_SNAPSHOT_ISOLATION được bật. Giá trị mặc định trên SQL Server cài đặt tại chỗ, Azure SQL Managed Instance và Azure SQL Database không hoàn toàn giống nhau.
- Oracle Database mặc định READ COMMITTED với snapshot ở phạm vi câu lệnh. Oracle hỗ trợ SERIALIZABLE và READ ONLY; không cung cấp READ UNCOMMITTED hoặc một mức REPEATABLE READ riêng như nhiều hệ quản trị khác.

Do đó, một dòng kiểu “MySQL REPEATABLE READ bảo vệ phantom” hoặc “SQL Server READ COMMITTED dùng khóa” có thể thiếu điều kiện quan trọng. Cần biết engine, index, cấu hình database và transaction đang chạy thực tế.

## 2. Xác định phạm vi của ma trận

Trước khi ghi bảo đảm, hãy chốt phạm vi mà ma trận mô tả. Ít nhất cần có:

| Thành phần | Thông tin cần ghi |
|---|---|
| Sản phẩm | PostgreSQL, MySQL, SQL Server, Oracle hoặc dịch vụ tương thích |
| Phiên bản | Major, minor, patch/build, cumulative update hoặc release update |
| Edition/dịch vụ | Community/Enterprise, SQL Server boxed, Azure SQL Database, Managed Instance, dịch vụ cloud khác |
| Storage engine/table type | InnoDB, MyISAM, NDB; disk-based hay memory-optimized; table access method hoặc loại bảng đặc biệt |
| Cấu hình database | Isolation mặc định, row-versioning options, durability options, lock/predicate settings |
| Cấu hình session | Isolation level, autocommit, session variables, transaction options |
| Cấu hình transaction | Lệnh SET TRANSACTION, locking hints, read-only/read-write, timeout |
| Schema và index | Primary key, unique index, composite index, partitioning, foreign key, constraint |
| Access path | Index seek, index range scan, table scan, execution plan |
| Ứng dụng | Driver, connection pool, ORM, middleware có thể thay đổi isolation hoặc retry |

Phạm vi nên chỉ rõ database, schema hoặc nhóm bảng được kiểm tra. Trong MySQL, một database có thể chứa các bảng dùng engine khác nhau. Trong SQL Server, disk-based table và memory-optimized table có cơ chế đồng thời khác nhau. Với PostgreSQL, cần ghi table access method hoặc extension đặc biệt nếu có; không nên coi nó tương đương với mô hình pluggable storage engine của MySQL.

Phiên bản cũng phải đủ chi tiết. Ghi “PostgreSQL 18” có ích hơn ghi “PostgreSQL”, nhưng môi trường production còn cần minor release và thời điểm cập nhật. Với SQL Server, ghi build/CU; với Oracle, ghi release và Release Update; với MySQL, ghi chính xác phiên bản server và storage engine của từng bảng quan trọng.

## 3. Phân biệt các loại bảo đảm cần đưa vào ma trận

Không nên gộp tất cả hiện tượng đồng thời thành một cột “ACID”. Hãy ghi từng thuộc tính hoặc lịch chạy mà nghiệp vụ cần bảo vệ.

| Hiện tượng/bảo đảm | Câu hỏi cần trả lời |
|---|---|
| Dirty read | Transaction có thể đọc thay đổi chưa commit của transaction khác không? |
| Non-repeatable read | Đọc lại cùng hàng trong cùng transaction có thể thấy giá trị mới đã commit không? |
| Phantom | Chạy lại cùng predicate có thể thấy thêm hoặc mất hàng không? |
| Lost update | Hai transaction cập nhật dựa trên cùng giá trị cũ có thể làm mất một thay đổi không? |
| Write skew | Hai transaction đọc cùng điều kiện nhiều hàng rồi ghi các hàng khác nhau có thể cùng commit và phá bất biến không? |
| Read-your-writes | Transaction có nhìn thấy thay đổi mà chính nó đã thực hiện không? |
| Missing-row race | Hai transaction cùng kiểm tra một hàng chưa tồn tại rồi cùng chèn có được điều phối không? |
| Same-row write conflict | Hai transaction cùng sửa một hàng được chờ, phát hiện xung đột hay hủy theo cách nào? |
| Predicate/range protection | Hàng mới thỏa điều kiện truy vấn có bị chặn hoặc khiến transaction bị hủy không? |
| Deadlock | Hệ quản trị phát hiện chu trình chờ và chọn nạn nhân theo cách nào? |
| Commit durability | Khi commit trả thành công, dữ liệu được flush hoặc nhân bản theo cấu hình nào? |

Các hiện tượng trên không thay thế lẫn nhau. Ví dụ, ngăn dirty read không có nghĩa ngăn write skew. Ngăn phantom trong một kiểu đọc cũng không đồng nghĩa mọi bất biến tổng hợp đều được bảo vệ. Khả năng phục hồi sau crash là một trục khác với isolation giữa các transaction đang chạy.

## 4. Quy ước trạng thái trong ma trận

Dùng một tập trạng thái rõ ràng thay vì đánh dấu đơn giản “có/không”:

- **Có bảo đảm:** hành vi được engine bảo vệ theo cấu hình và phạm vi đã ghi.
- **Có điều kiện:** chỉ đúng khi thỏa các điều kiện như đúng storage engine, index, isolation level, locking hint hoặc mọi đường ghi cùng tuân thủ giao thức.
- **Không bảo đảm:** transaction có thể gặp hiện tượng đó; cần constraint, khóa hoặc thiết kế ứng dụng bổ sung.
- **Không áp dụng:** tính năng không tồn tại trong engine hoặc loại bảng đang xét.
- **Chưa xác minh:** chưa có bằng chứng từ cấu hình thực tế hoặc kiểm thử. Không được tự chuyển trạng thái này thành “có bảo đảm”.

Ví dụ, “range lock có điều kiện” phải kèm điều kiện: SQL Server SERIALIZABLE với access path phù hợp; hoặc InnoDB REPEATABLE READ với locking read và chỉ mục phù hợp. Không ghi chung “database có range lock” mà bỏ qua phạm vi cụ thể.

## 5. Ma trận tham khảo theo sản phẩm

Bảng dưới đây là **mốc tham khảo để bắt đầu điều tra**, dựa trên tài liệu sản phẩm hiện hành được ghi trong phần nguồn. Nó không thay thế việc kiểm tra phiên bản và cấu hình thực tế của môi trường đang chạy.

| Sản phẩm/phạm vi tham khảo | Mặc định và mô hình đọc | Khóa/phạm vi và SERIALIZABLE | Điểm phải xác minh |
|---|---|---|---|
| MySQL 8.4, bảng InnoDB | InnoDB mặc định REPEATABLE READ. Consistent nonlocking read trong một transaction dùng read view theo quy tắc của mức cô lập. | Locking read/DML trên unique index với điều kiện tìm duy nhất thường khóa record tìm thấy; điều kiện khác có thể khóa index range bằng gap/next-key lock. SERIALIZABLE tăng bảo vệ và thay đổi cách xử lý SELECT trong transaction. | Engine của từng bảng; transaction_isolation; autocommit; index/access path; gap-lock behavior; phiên bản InnoDB. |
| MySQL 8.4, bảng MyISAM | Không có transaction semantics như InnoDB. | Không có row-level transactional locking và rollback của transaction theo mô hình InnoDB. | SHOW ENGINES và ENGINE của từng bảng. Không áp ma trận InnoDB cho MyISAM. |
| PostgreSQL 18 | Mặc định READ COMMITTED; mỗi câu lệnh có snapshot riêng. READ UNCOMMITTED được xử lý như READ COMMITTED. REPEATABLE READ dùng snapshot cấp transaction. | REPEATABLE READ ngăn phantom theo triển khai PostgreSQL nhưng có thể cho write skew. SERIALIZABLE dùng SSI; predicate tracking có thể dẫn đến serialization failure thay vì chặn mọi ghi. | Isolation của transaction; table access method/extension; execution plan; predicate-lock promotion và max_pred_locks_*; ứng dụng có retry SQLSTATE 40001 không. |
| SQL Server (Database Engine) | READ COMMITTED là mặc định. Với READ_COMMITTED_SNAPSHOT OFF, đọc dùng shared locks; khi ON, READ COMMITTED dùng row versions ở phạm vi câu lệnh. SNAPSHOT dùng row versions ở phạm vi transaction. | REPEATABLE READ giữ khóa đọc trên hàng đã đọc nhưng vẫn có thể có phantom. SERIALIZABLE dùng key-range locks. | Build/CU; is_read_committed_snapshot_on; snapshot_isolation_state_desc; table type; optimized locking/ADR nếu phiên bản hỗ trợ. |
| Azure SQL Database | READ_COMMITTED_SNAPSHOT mặc định ON; SNAPSHOT có thể được bật theo mặc định của dịch vụ. | Cùng cần xác minh mức transaction thực tế và các tùy chọn database; không lấy mặc định SQL Server boxed áp sang Azure SQL Database. | Dịch vụ/region/tier, database options và cấu hình hiện tại qua sys.databases. |
| Oracle Database 26 | READ COMMITTED là mặc định và cung cấp statement-level read consistency. Oracle không cho dirty read; không có READ UNCOMMITTED hoặc mức REPEATABLE READ riêng. | SERIALIZABLE và READ ONLY cung cấp transaction-level read consistency. Ghi vào hàng đã bị transaction khác commit thay đổi sau thời điểm bắt đầu có thể nhận ORA-08177. | Release Update; COMPATIBLE; loại transaction; cách ứng dụng đặt SET TRANSACTION; undo capacity/retention và lỗi serialization được xử lý ra sao. |

### 5.1. MySQL: engine là một phần của hợp đồng

Trong MySQL, đừng chỉ ghi phiên bản server. Cần ghi engine của từng bảng tham gia transaction.

InnoDB hỗ trợ transaction, row-level locking, foreign key và savepoint. MyISAM không hỗ trợ transaction, XA hoặc savepoint. MySQL còn có NDB và các engine chuyên dụng khác với mô hình riêng.

Có thể lấy thông tin ban đầu bằng:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@transaction_isolation AS session_isolation,
    @@global.transaction_isolation AS global_isolation,
    @@default_storage_engine AS default_engine,
    @@autocommit AS autocommit,
    @@innodb_flush_log_at_trx_commit AS innodb_flush_log_at_trx_commit,
    @@sync_binlog AS sync_binlog;

SHOW ENGINES;

SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE';
~~~

Giá trị default_storage_engine chỉ cho biết engine mặc định khi tạo bảng. Nó không chứng minh các bảng cũ đang dùng engine đó. Hãy kiểm tra cột ENGINE của đúng các bảng trong transaction.

Với InnoDB, cần ghi cả isolation level và loại câu lệnh. Ở REPEATABLE READ, một SELECT thường dùng snapshot; SELECT ... FOR UPDATE và UPDATE/DELETE dùng cơ chế khóa trên index. Unique equality lookup, range scan và truy vấn thiếu index có thể có phạm vi khóa khác nhau. Ở READ COMMITTED, InnoDB thường không dùng gap lock cho tìm kiếm/quét index thông thường, ngoại trừ các trường hợp như kiểm tra foreign key và duplicate key.

### 5.2. PostgreSQL: phân biệt snapshot với SSI

PostgreSQL không có lựa chọn storage engine theo từng bảng theo kiểu InnoDB/MyISAM. Transaction manager, MVCC và locking là cơ chế của server. Table access method mặc định là heap; nếu môi trường cài extension hoặc access method khác, hãy ghi lại vì nó ảnh hưởng cách lưu dữ liệu và cần được xác minh theo tài liệu của extension.

Lấy thông tin session và cấu hình liên quan:

~~~sql
SELECT version();

SHOW default_transaction_isolation;
SHOW transaction_isolation;
SHOW synchronous_commit;
SHOW fsync;

SHOW max_pred_locks_per_transaction;
SHOW max_pred_locks_per_relation;
SHOW max_pred_locks_per_page;
~~~

default_transaction_isolation là giá trị mặc định cho transaction mới; transaction_isolation phản ánh transaction/session hiện tại theo ngữ cảnh thực thi. Hãy kiểm tra trên connection thực tế mà ứng dụng lấy từ pool, sau khi các interceptor hoặc initialization SQL đã chạy.

Trong PostgreSQL 18, READ COMMITTED tạo snapshot theo câu lệnh. REPEATABLE READ giữ snapshot cấp transaction; triển khai này ngăn phantom read nhưng vẫn có thể cho write skew. SERIALIZABLE theo dõi phụ thuộc đọc–ghi bằng SSI và có thể hủy một transaction với serialization failure. Predicate lock kiểu SIREAD là dữ liệu theo dõi cho SSI, không phải gap lock chặn insert theo cách InnoDB thực hiện.

Các tham số max_pred_locks_* ảnh hưởng số predicate lock và thời điểm hệ thống gộp phạm vi theo dõi. Khi predicate lock được nâng từ page/tuple lên relation, tỷ lệ serialization failure có thể tăng do phạm vi theo dõi rộng hơn. Đây là lý do cần ghi cấu hình và access path vào ma trận; không nên diễn giải việc tăng số lỗi abort là SERIALIZABLE đã mất bảo đảm.

### 5.3. SQL Server: hai tùy chọn row versioning phải được ghi riêng

Trong SQL Server, READ COMMITTED có thể dùng locking hoặc row versioning. Cần ghi riêng:

- READ_COMMITTED_SNAPSHOT (RCSI): READ COMMITTED đọc phiên bản ở phạm vi câu lệnh.
- ALLOW_SNAPSHOT_ISOLATION: cho phép transaction yêu cầu SNAPSHOT với snapshot ở phạm vi transaction.

Đây là hai tùy chọn khác nhau. Bật RCSI không tự động có nghĩa ứng dụng đang chạy SNAPSHOT; bật ALLOW_SNAPSHOT_ISOLATION cũng không tự chuyển mọi transaction READ COMMITTED sang snapshot.

Có thể kiểm tra database hiện tại:

~~~sql
SELECT
    name,
    compatibility_level,
    is_read_committed_snapshot_on,
    snapshot_isolation_state_desc,
    is_accelerated_database_recovery_on
FROM sys.databases
WHERE name = DB_NAME();
~~~

Trên phiên bản hỗ trợ optimized locking, có thể kiểm tra thêm cột is_optimized_locking_on hoặc thuộc tính database tương ứng. Đừng chạy truy vấn chứa cột không tồn tại trên build cũ; xác định phiên bản trước rồi dùng đúng catalog schema.

Một số điểm quan trọng:

- SQL Server boxed và Azure SQL Managed Instance mặc định RCSI OFF; Azure SQL Database mặc định RCSI ON theo tài liệu dịch vụ. Hãy đọc giá trị database thực tế.
- SNAPSHOT cần ALLOW_SNAPSHOT_ISOLATION ON; giá trị mặc định của user database khác nhau giữa các dịch vụ.
- REPEATABLE READ giữ khóa trên dữ liệu đã đọc nhưng không ngăn mọi hàng mới thỏa predicate.
- SERIALIZABLE dùng key-range lock để bảo vệ phạm vi khóa.
- Memory-optimized tables có mô hình đồng thời và cách áp dụng isolation khác disk-based tables; không áp dụng nguyên xi kết luận về khóa hàng truyền thống cho chúng.
- Optimized locking là tính năng phụ thuộc phiên bản và cấu hình; tài liệu hiện hành yêu cầu ADR trước khi bật, và RCSI giúp tận dụng đầy đủ một số thành phần như lock-after-qualification.

### 5.4. Oracle: mức cô lập và snapshot có phạm vi khác

Oracle Database mặc định READ COMMITTED. Mỗi câu query nhìn dữ liệu đã commit trước khi câu query bắt đầu. Khi transaction đặt SERIALIZABLE, các câu lệnh dùng ảnh dữ liệu tại thời điểm transaction bắt đầu, cùng với thay đổi của chính transaction đó. Oracle cũng có chế độ READ ONLY cho transaction chỉ đọc.

Oracle không cung cấp READ UNCOMMITTED và không có mức REPEATABLE READ riêng như một số hệ quản trị khác. Khi SERIALIZABLE transaction cố cập nhật hàng đã bị transaction khác thay đổi và commit sau thời điểm bắt đầu, Oracle có thể trả ORA-08177.

Với Oracle, không nên cố tìm một biến cấu hình duy nhất đại diện cho isolation level hiện hành. Hãy kiểm tra cách ứng dụng khởi tạo transaction, lệnh SET TRANSACTION/ALTER SESSION, framework transaction manager và loại transaction thực tế. SET TRANSACTION ISOLATION LEVEL phải được thực hiện ở vị trí hợp lệ theo quy tắc transaction của Oracle.

Ngoài isolation, hãy ghi release/update, COMPATIBLE, undo configuration và khả năng giữ undo cần thiết cho consistent read. Undo retention và dung lượng undo ảnh hưởng khả năng tái tạo phiên bản cũ; chúng không phải một mức isolation khác.

## 6. Ma trận theo hiện tượng: ví dụ cách ghi kết quả

Bảng sau minh họa cách ghi bảo đảm ở mức khái niệm. Mỗi ô vẫn cần được xác nhận bằng phiên bản và cấu hình của hệ thống thật.

| Hiện tượng | InnoDB REPEATABLE READ | PostgreSQL REPEATABLE READ | SQL Server REPEATABLE READ | Oracle READ COMMITTED |
|---|---|---|---|---|
| Dirty read | Có bảo đảm không đọc dữ liệu chưa commit | Có bảo đảm; READ UNCOMMITTED cũng ánh xạ thành READ COMMITTED | Có bảo đảm | Có bảo đảm |
| Cùng một hàng đọc lại | Consistent read dùng snapshot; locking read có quy tắc riêng | Snapshot transaction ổn định | Khóa đọc được giữ đến cuối transaction trên hàng đã đọc | Mỗi câu query có snapshot riêng; lần query sau có thể thấy commit mới |
| Phantom khi đọc lặp | Consistent read giữ snapshot; locking range read dùng gap/next-key theo điều kiện | REPEATABLE READ không thấy phantom theo triển khai PostgreSQL | Có thể xảy ra | Có thể xảy ra giữa hai câu query |
| Write skew trên các hàng khác nhau | Có thể xảy ra dưới snapshot isolation nếu không phối hợp | Có thể xảy ra | SNAPSHOT cũng cần xem xét bất biến nhiều hàng; REPEATABLE READ không đủ để bảo vệ mọi predicate | READ COMMITTED có thể gặp race khi kiểm tra aggregate rồi ghi |
| Predicate bảo vệ | Có điều kiện theo index, locking read và isolation | SSI chỉ ở SERIALIZABLE; predicate tracking có thể abort | Key-range lock ở SERIALIZABLE | SERIALIZABLE hoặc cơ chế ứng dụng/constraint phù hợp |
| Hàng chưa tồn tại | Phạm vi gap phụ thuộc index, search và isolation | FOR UPDATE không khóa hàng không tồn tại; SERIALIZABLE SSI theo dõi predicate | SERIALIZABLE có thể khóa key range | Row lock không khóa hàng chưa tồn tại; cần constraint hoặc điều phối khác |
| Retry sau xung đột | Deadlock/timeout theo lỗi InnoDB; transaction bị hủy cần chạy lại | Serialization failure 40001; retry toàn bộ transaction | Deadlock victim/update conflict theo error number; transaction mới | ORA-08177 cho serialization conflict; xử lý transaction theo chính sách |

Không so sánh các ô bằng cách đếm dấu tick. Hãy hỏi nghiệp vụ cần bảo đảm nào và xác định cơ chế thực tế cung cấp bảo đảm đó. Ví dụ, PostgreSQL REPEATABLE READ và SQL Server REPEATABLE READ cùng tên nhưng không có cùng hành vi phantom. Oracle READ COMMITTED và PostgreSQL READ COMMITTED đều có snapshot theo câu lệnh, nhưng chi tiết locking và tương tác writer khác nhau.

## 7. Đừng gộp isolation với durability và replication

Một ma trận hoàn chỉnh có thể có nhiều nhóm bảo đảm, nhưng phải tách riêng:

**Isolation/concurrency:** transaction nhìn dữ liệu nào, khóa gì, ngăn anomaly nào, lỗi xung đột nào có thể trả về.

**Atomicity:** thay đổi của transaction được commit hoặc rollback cùng nhau trong phạm vi engine tham gia transaction. Với MySQL, phải xác nhận các bảng liên quan dùng engine có transaction; một thao tác chạm bảng nontransactional không có cùng rollback semantics như InnoDB.

**Durability:** commit đã được ghi bền vững đến mức nào. Ví dụ MySQL có innodb_flush_log_at_trx_commit và sync_binlog; PostgreSQL có fsync và synchronous_commit; SQL Server có delayed durability và ADR; Oracle có các tùy chọn commit write và cấu hình redo/standby. Không suy ra độ bền commit chỉ từ mức SERIALIZABLE.

**Replication/failover:** xác nhận commit ở primary có đồng nghĩa dữ liệu đã có trên replica đồng bộ hay không. Chính sách synchronous/asynchronous replication, failover và replication lag cần một phần riêng trong ma trận.

Nếu một nghiệp vụ cần “đã commit thì không mất khi mất điện” hoặc “đã xác nhận thì replica failover cũng phải có dữ liệu”, hãy ghi yêu cầu đó riêng và kiểm tra đúng tùy chọn durability/replication. Isolation level không trả lời câu hỏi này.

## 8. Thu thập cấu hình có hiệu lực, không chỉ cấu hình dự định

Cấu hình trong file triển khai hoặc IaC cho biết hệ thống được dự định chạy thế nào. Cấu hình runtime cho biết instance thực sự đang chạy thế nào. Cả hai cần được đối chiếu.

Quy trình thu thập:

1. Ghi phiên bản server, edition, patch/build và dịch vụ triển khai.
2. Đọc engine của từng bảng liên quan.
3. Đọc cấu hình global và database.
4. Mở connection theo đúng đường đi của ứng dụng và đọc session settings.
5. Bắt đầu transaction mẫu và xác nhận isolation level thực tế.
6. Kiểm tra ORM, driver, connection pool, middleware và SQL hints có thay đổi cấu hình không.
7. Ghi schema, index, constraint và execution plan của truy vấn quan trọng.
8. Lưu kết quả cùng thời điểm, môi trường và quyền thực thi truy vấn.

Đừng chỉ chạy câu kiểm tra trên một connection quản trị. Connection pool có thể khởi tạo session bằng SQL riêng, tái sử dụng connection có trạng thái cũ hoặc đặt isolation level ở transaction boundary. Hãy kiểm tra connection lấy từ pool sau khi ứng dụng đã áp dụng mọi initialization rule.

## 9. Ghi bằng chứng cho từng ô

Mỗi bảo đảm trong ma trận nên có một bằng chứng có thể kiểm tra lại:

| Loại bằng chứng | Ví dụ |
|---|---|
| Tài liệu phiên bản | Trang tài liệu đúng major/minor release, không dùng trang của phiên bản mới hơn mà không xác nhận |
| Runtime config | Kết quả truy vấn SHOW, @@variable, sys.databases, catalog view hoặc tham số Oracle |
| Schema | DDL, storage engine, primary/unique key, foreign key, check constraint |
| Execution plan | Index seek/scan, range scan, table scan, predicate được dùng |
| Lock/version evidence | Lock wait, deadlock graph, pg_locks, performance_schema.data_locks, sys.dm_tran_locks, công cụ chẩn đoán tương ứng |
| Concurrency test | Hai hoặc nhiều session đồng bộ bằng barrier, ghi lại kết quả commit/abort và trạng thái cuối |
| Application evidence | Isolation do framework đặt, retry policy, connection pool initialization và transaction boundary |

Ghi ngày thu thập và build chính xác. Khi nâng cấp database, đổi engine, thay index hoặc sửa cấu hình, hãy đánh dấu ma trận cần xác minh lại. Một ma trận cũ không tự động còn đúng sau khi thay đổi môi trường.

## 10. Thiết kế bài kiểm thử cho từng bảo đảm

Không thể xác nhận write skew bằng một unit test gọi service hai lần tuần tự. Cần tạo lịch chạy đồng thời có thể tái hiện.

Ví dụ kiểm thử write skew:

1. Tạo hai hàng bác sĩ cùng đang trực.
2. Mở hai connection độc lập.
3. Đặt isolation level đúng với cấu hình cần xác minh.
4. T1 và T2 cùng đọc số người đang trực trước khi một transaction commit.
5. T1 cập nhật hàng bác sĩ 1; T2 cập nhật hàng bác sĩ 2.
6. Đồng bộ thời điểm commit hoặc để engine điều phối.
7. Ghi lại transaction nào commit, transaction nào bị hủy.
8. Kiểm tra bất biến sau khi cả hai kết thúc.

Các lịch chạy khác cần kiểm tra riêng:

- **Dirty read:** T1 cập nhật nhưng chưa commit; T2 thử đọc.
- **Non-repeatable read:** T1 đọc một hàng hai lần, T2 cập nhật và commit ở giữa.
- **Phantom:** T1 đọc một predicate, T2 chèn hàng mới thỏa predicate, T1 đọc lại.
- **Missing-row race:** T1 và T2 cùng tìm khóa chưa tồn tại rồi cùng insert.
- **Lost update:** hai transaction cùng đọc một giá trị, tính giá trị mới và ghi.
- **Deadlock:** hai transaction khóa tài nguyên theo thứ tự ngược nhau.
- **Durability:** commit, sau đó kiểm tra phục hồi theo kịch bản crash/failover được kiểm soát.

Mỗi test phải ghi lại engine, isolation level, session settings, index và execution plan. Nếu không, kết quả chỉ mô tả một lần chạy mà không chứng minh được cấu hình nào đã tạo ra nó.

## 11. Mẫu ma trận triển khai để điền cho môi trường thật

Có thể dùng mẫu dưới đây cho từng môi trường (development, staging, production). Tách hàng theo database/schema hoặc nhóm bảng nếu engine hay cấu hình khác nhau.

~~~text
MÔI TRƯỜNG:
THỜI ĐIỂM THU THẬP:
DATABASE/CLUSTER:
SẢN PHẨM:
VERSION / PATCH / BUILD:
EDITION / CLOUD SERVICE:
DATABASE / SCHEMA:
STORAGE ENGINE / TABLE TYPE:
TABLE ACCESS METHOD:
DEFAULT ISOLATION:
EFFECTIVE SESSION ISOLATION:
TRANSACTION OVERRIDES:
AUTOCOMMIT:
ROW VERSIONING OPTIONS:
LOCK/PREDICATE OPTIONS:
DURABILITY OPTIONS:
REPLICATION / FAILOVER MODE:
SCHEMA / INDEX / CONSTRAINT:
APPLICATION DRIVER / ORM / POOL:
QUERY PLAN EVIDENCE:
TEST RUN ID:

BẢO ĐẢM:
- Dirty read:
- Non-repeatable read:
- Phantom:
- Lost update:
- Write skew:
- Missing-row race:
- Same-row write conflict:
- Predicate/range protection:
- Deadlock behavior:
- Serialization failure behavior:
- Commit durability:
- Replica/failover guarantee:

TRẠNG THÁI MỖI BẢO ĐẢM:
- Có bảo đảm / Có điều kiện / Không bảo đảm / Không áp dụng / Chưa xác minh

ĐIỀU KIỆN VÀ BẰNG CHỨNG:
- Cấu hình:
- Schema/index:
- Tài liệu phiên bản:
- Kết quả kiểm thử:
- Hạn chế:
- Ngày cần xác minh lại:
~~~

Không điền “Có bảo đảm” nếu chỉ mới đọc tài liệu chung mà chưa xác nhận engine và cấu hình. Nếu chưa có quyền xem runtime config, ghi “Chưa xác minh” và nêu rõ phần thiếu.

## 12. Cách cập nhật ma trận khi môi trường thay đổi

Ma trận phải được quản lý như một phần của tài liệu vận hành và thiết kế dữ liệu.

Các thay đổi cần kích hoạt xác minh lại:

- Nâng major/minor version hoặc cài patch/CU/RU.
- Chuyển từ MyISAM sang InnoDB hoặc thay storage engine.
- Bật/tắt RCSI, SNAPSHOT, optimized locking hoặc thay isolation default.
- Thay đổi autocommit hoặc transaction settings trong connection pool.
- Thay index, partitioning, table type hoặc execution plan.
- Đổi từ self-managed sang managed database service.
- Thay đổi synchronous/asynchronous replication hoặc durability policy.
- Thay đổi ORM, driver hoặc framework có thể đặt isolation/hints.

Khi nâng cấp, không chỉ so sánh release notes. Hãy chạy lại các concurrency schedule quan trọng trong môi trường gần production và đối chiếu với kết quả trước đó. Lưu lại chênh lệch: thay đổi nào là mặc định mới, thay đổi nào do cấu hình, và thay đổi nào do access path.

## 13. Những kết luận không nên rút ra từ ma trận

- Không kết luận hai hệ quản trị có cùng bảo đảm chỉ vì chúng cùng ghi REPEATABLE READ.
- Không kết luận toàn bộ MySQL database dùng InnoDB chỉ vì InnoDB là default engine.
- Không kết luận SQL Server READ COMMITTED luôn dùng shared locks khi RCSI có thể bật.
- Không kết luận PostgreSQL REPEATABLE READ tương đương SERIALIZABLE chỉ vì phantom read bị ngăn.
- Không kết luận SELECT ... FOR UPDATE bảo vệ hàng chưa tồn tại ở mọi engine.
- Không kết luận SERIALIZABLE sẽ không bao giờ deadlock hoặc không cần retry.
- Không kết luận transaction đã commit bền vững trên replica chỉ từ isolation level.
- Không kết luận cấu hình global là cấu hình thực tế của connection mà ứng dụng đang sử dụng.

Ma trận tốt phải nói rõ bảo đảm nào được cung cấp, ở đâu, dưới điều kiện nào, và bằng chứng nào chứng minh điều đó. Nếu một ô phụ thuộc index, transaction hint, storage engine hoặc tùy chọn database, hãy ghi chúng ngay trong ô hoặc phần điều kiện đi kèm.

## 14. Checklist hoàn thiện ma trận bảo đảm

- [ ] Ghi chính xác sản phẩm, version, patch/build và edition/service.
- [ ] Xác định engine hoặc table type của từng bảng trong transaction.
- [ ] Phân biệt default isolation với isolation thực tế của session và transaction.
- [ ] Ghi cấu hình row versioning, gap/key-range/predicate locking có liên quan.
- [ ] Ghi schema, unique constraint, index, partition và execution plan.
- [ ] Tách dirty read, non-repeatable read, phantom, lost update và write skew.
- [ ] Đánh giá riêng thao tác tìm hàng chưa tồn tại và predicate read.
- [ ] Ghi deadlock, serialization failure, lock timeout và chính sách retry.
- [ ] Tách isolation khỏi atomicity, durability và replication.
- [ ] Có runtime evidence và concurrency test cho từng bảo đảm quan trọng.
- [ ] Gắn nhãn “Chưa xác minh” khi thiếu bằng chứng.
- [ ] Xác định trigger cập nhật lại ma trận sau mỗi thay đổi phiên bản, engine hoặc cấu hình.

Lập ma trận bảo đảm giúp chuyển những giả định mơ hồ về database thành một hợp đồng kỹ thuật có thể kiểm chứng. Phiên bản cho biết tập tính năng và thay đổi của sản phẩm; storage engine hoặc table type xác định cách transaction và khóa được áp dụng; cấu hình database, session và transaction quyết định chế độ đang chạy; schema và access path quyết định tài nguyên nào bị đọc hoặc khóa. Chỉ khi ghi đủ các chiều này và xác nhận bằng kiểm thử đồng thời, nhóm mới có thể dựa vào ma trận để thiết kế transaction, chọn constraint, xử lý retry và đánh giá tác động của một lần nâng cấp.

## Nguồn tài liệu chính thức để đối chiếu

- [MySQL 8.4 — InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 — InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 — Alternative Storage Engines](https://dev.mysql.com/doc/refman/8.4/en/storage-engines.html)
- [PostgreSQL 18 — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html)
- [PostgreSQL 18 — Lock Management](https://www.postgresql.org/docs/18/runtime-config-locks.html)
- [SQL Server — Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide?view=sql-server-ver17)
- [SQL Server — SET TRANSACTION ISOLATION LEVEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql?view=sql-server-ver17)
- [SQL Server — Optimized Locking](https://learn.microsoft.com/en-us/sql/relational-databases/performance/optimized-locking?view=sql-server-ver17)
- [Oracle Database 26 — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/26/cncpt/data-concurrency-and-consistency.html)
- [Oracle Database 26 — Database Development Guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/adfns/database-development-guide.html)

