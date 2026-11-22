# Đánh giá tương thích và chuyển đổi schema database

Di chuyển cơ sở dữ liệu lên AWS hoặc chuyển giữa hai hệ quản trị cơ sở dữ liệu (DBMS) là một thay đổi về dữ liệu, SQL, hành vi ứng dụng và vận hành. Một schema có thể được chuyển đổi cú pháp thành công nhưng ứng dụng vẫn lỗi vì khác biệt về kiểu dữ liệu, collation, transaction, sequence, stored procedure, quyền truy cập hoặc cách xử lý thời gian. Vì vậy, đội dự án cần đánh giá tương thích trước khi chọn đích đến và trước khi lên lịch cutover.

Bài học trình bày cách kiểm kê database nguồn, đánh giá khả năng tương thích với database đích, sử dụng công cụ chuyển đổi schema trong quy trình migration AWS, xử lý phần không tự động chuyển đổi được và kiểm chứng schema sau khi triển khai. Nội dung đặt trong bối cảnh hạ tầng AWS gồm Region/AZ, VPC, IAM, RDS, Aurora, kết nối hybrid và dịch vụ di chuyển dữ liệu. Mục tiêu là giúp người học chọn đích phù hợp, giảm rủi ro chuyển đổi và duy trì tính toàn vẹn, bảo mật, khả năng giám sát của ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Lập inventory database và schema nguồn gồm phiên bản engine, extension, object, dung lượng, workload và phụ thuộc ứng dụng.
- Phân biệt tương thích ở cấp engine, schema, dữ liệu, SQL, ứng dụng, hiệu năng, bảo mật và vận hành.
- Nhận diện các khác biệt quan trọng giữa Oracle, SQL Server, PostgreSQL, MySQL và Amazon Aurora.
- Đọc assessment report, phân loại object tự động chuyển đổi, cần chỉnh sửa và không được hỗ trợ.
- Sử dụng AWS Schema Conversion Tool (AWS SCT) hoặc AWS DMS Schema Conversion khi phù hợp với cặp nguồn/đích được hỗ trợ.
- Hiểu ranh giới giữa chuyển đổi schema và di chuyển dữ liệu bằng AWS Database Migration Service (AWS DMS).
- Thiết kế quy trình chuyển đổi, sửa thủ công, triển khai và kiểm thử schema đích.
- Xác minh dữ liệu, constraint, index, stored code, quyền và hành vi ứng dụng trước cutover.
- Lập kế hoạch rollback, bảo mật kết nối hybrid và theo dõi sau migration.

## 2. Vì sao phải đánh giá tương thích trước khi chuyển đổi

Schema mô tả cấu trúc và quy tắc của database: bảng, cột, kiểu dữ liệu, khóa, constraint, index, view, sequence, function, procedure, trigger, quyền và các đối tượng khác. Mỗi DBMS có dialect SQL, kiểu dữ liệu, mô hình lưu trữ và tính năng riêng. Cùng một câu lệnh có thể có ý nghĩa khác nhau giữa hai engine.

Ví dụ:
- Oracle xử lý chuỗi rỗng như NULL trong nhiều ngữ cảnh; PostgreSQL và MySQL phân biệt chuỗi rỗng với NULL.
- SQL Server có kiểu `uniqueidentifier`; PostgreSQL có `uuid`; cách sinh và truyền giá trị cần được ứng dụng hỗ trợ.
- Oracle dùng package và PL/SQL; PostgreSQL không có package theo cùng mô hình, còn procedure/function có cú pháp và hành vi khác.
- SQL Server có `IDENTITY`; PostgreSQL thường dùng identity column hoặc sequence; MySQL có `AUTO_INCREMENT`.
- Kiểu thời gian, collation, so sánh chuỗi, xử lý timezone và làm tròn số có thể khác nhau.
- Một index hoặc partition strategy tối ưu trên nguồn có thể không phù hợp với optimizer và storage engine của đích.

Một công cụ có thể chuyển đổi DDL nhưng không thể tự quyết định mọi quy tắc nghiệp vụ. Ví dụ, khi nguồn dùng `NUMBER(1)` để biểu diễn trạng thái, công cụ không thể biết chắc cột đó nên là boolean, integer hay enum ở đích nếu thiếu ngữ cảnh nghiệp vụ.

Đánh giá sớm giúp đội dự án:
1. Chọn engine đích phù hợp với workload và kỹ năng vận hành.
2. Ước lượng công sức chuyển đổi code và object.
3. Phát hiện các tính năng nguồn không có tương đương trực tiếp.
4. Lập ngân sách cho refactor, kiểm thử và thời gian downtime.
5. Tránh cam kết lịch cutover dựa trên tỷ lệ chuyển đổi tự động.
6. Xác định yêu cầu bảo mật, license, HA, backup và DR ở đích.

**Schema conversion không đồng nghĩa với database migration hoàn tất.** Schema conversion tạo hoặc điều chỉnh cấu trúc và code database ở đích. Data migration chuyển dữ liệu. Ứng dụng migration cập nhật driver, SQL, cấu hình, secret, connection pool và cách xử lý lỗi. Cả ba phần phải được kiểm chứng cùng nhau.

## 3. Các lớp tương thích cần đánh giá

Một đánh giá đầy đủ nên chia thành các lớp riêng để tránh việc một báo cáo “schema chuyển đổi thành công” che khuất vấn đề ở ứng dụng hoặc vận hành.

| Lớp | Nội dung cần xem | Ví dụ rủi ro |
|---|---|---|
| Engine/platform | Engine, version, edition, extension, license, giới hạn dịch vụ đích | Phiên bản nguồn không nằm trong đường nâng cấp hoặc không được đích hỗ trợ |
| Schema/object | Bảng, cột, constraint, index, view, sequence, routine, trigger | Package PL/SQL không có chuyển đổi trực tiếp |
| Data type/value | Precision, scale, range, encoding, NULL, timezone, LOB | Timestamp bị đổi múi giờ hoặc decimal bị mất precision |
| SQL semantics | Cú pháp, function, transaction, locking, isolation | Query hợp lệ ở nguồn nhưng trả kết quả khác ở đích |
| Application | Driver, ORM, stored code call, generated key, error handling | JDBC driver mới trả kiểu dữ liệu khác |
| Performance | Query plan, index, partition, statistics, concurrency | Query chậm do optimizer chọn plan khác |
| Security | User, role, privilege, encryption, authentication | User nguồn có quyền rộng nhưng role đích thiếu quyền cần thiết |
| Operations | Backup, restore, HA, monitoring, maintenance, DR | Cơ chế failover và endpoint khác với giả định ứng dụng |
| Migration path | Downtime, CDC, replication, network, cutover, rollback | DDL thay đổi trong lúc CDC đang chạy gây sai lệch |

Không nên gom tất cả vào một con số duy nhất. Hãy ghi nhận bằng chứng, mức độ ảnh hưởng, cách xử lý và người chịu trách nhiệm cho từng khác biệt.

## 4. Thu thập inventory database nguồn

Bắt đầu bằng dữ liệu có thể kiểm chứng. Không chỉ hỏi “database có bao nhiêu GB”; cần hiểu cấu trúc, tải, phụ thuộc và hành vi thực tế.

### 4.1 Thông tin engine và môi trường

Ghi nhận:
- DBMS và phiên bản chính/phụ.
- Edition, license, patch level và cấu hình quan trọng.
- Operating system, filesystem, storage và topology hiện tại.
- Character set, national character set, collation và timezone database.
- Extension, plugin, package bổ sung và thư viện native.
- Số database, schema, owner, user, role và quyền.
- Cấu hình HA, replication, backup, retention và DR.
- Mức tăng dung lượng, tốc độ ghi, số kết nối và peak workload.
- Các job, scheduler, ETL, batch, CDC và công cụ BI kết nối database.

Phiên bản nguồn là dữ kiện quan trọng khi đánh giá cặp nguồn/đích. Hai hệ thống cùng tên engine nhưng khác major version có thể khác cú pháp, catalog, kiểu dữ liệu và tính năng.

### 4.2 Kiểm kê object

Lập số lượng theo từng schema và loại object:

| Object | Thông tin cần ghi nhận | Điểm cần đánh giá |
|---|---|---|
| Table | Số bảng, cột, partition, row estimate, dung lượng | Kiểu dữ liệu, default, identity, generated column |
| Primary/foreign key | Số lượng, cột, trạng thái, cascade | Khả năng tạo và thời điểm validate |
| Check/unique constraint | Biểu thức, trạng thái enabled/validated | Khác biệt cú pháp và semantics |
| Index | Loại, cột, expression, partial/filter, included columns | Loại index có tương đương ở đích không |
| View | SQL, dependency, quyền | Function/dialect và thứ tự tạo |
| Materialized view | Query, refresh mode, schedule | Cơ chế refresh ở đích |
| Sequence | Start, increment, cache, cycle | Cách sinh ID và đồng bộ sau load |
| Procedure/function | Ngôn ngữ, dependency, exception, dynamic SQL | Công sức chuyển đổi code |
| Trigger | Event, timing, row/statement level | Thứ tự thực thi và side effect |
| Synonym/package | Phạm vi, dependency, nội dung | Có thể cần refactor kiến trúc |
| Partition | Key, strategy, retention, subpartition | Cách triển khai và pruning |
| User/role/grant | Owner, privilege, role inheritance | Mô hình quyền đích |
| Job/scheduler | Lịch, timezone, retry, credential | Chuyển sang scheduler/workflow phù hợp |

Ngoài object, hãy ghi nhận dữ liệu đặc biệt như XML, JSON, spatial, binary, LOB, encrypted columns, user-defined types và dữ liệu có encoding không phổ biến.

### 4.3 Kiểm kê workload và ứng dụng

Cần biết ai đang sử dụng database và sử dụng như thế nào:

- Ứng dụng Java, .NET, Python, Node.js hoặc ứng dụng đóng gói.
- JDBC/ODBC driver và phiên bản.
- ORM, migration framework, query builder và SQL dialect.
- Stored procedure được gọi từ ứng dụng.
- Query động được sinh từ report, BI hoặc stored code.
- Batch, cron, ETL, replication và data warehouse.
- Kết nối từ on-premises, VPC, account khác hoặc SaaS.
- Cơ chế xác thực, secret rotation và certificate.
- Yêu cầu latency, throughput, RPO, RTO và maintenance window.

Một bảng inventory thực tế có thể gồm:

| Thuộc tính | Ví dụ |
|---|---|
| Database | `orders_prod` |
| Source engine | Oracle 19c |
| Target candidate | Amazon Aurora PostgreSQL-Compatible |
| Schema | `ORDER_APP`, `BILLING` |
| Data size | 3 TB |
| Peak connections | 1.200 |
| Peak write rate | 8.000 transactions/minute |
| Critical objects | 25 packages, 80 triggers |
| Downtime objective | Dưới 15 phút |
| RPO/RTO | 1 phút / 30 phút |
| Application owner | Commerce Platform |
| Evidence | Inventory export, query logs, AWR/monitoring, source code |

Các số liệu trong ví dụ chỉ minh họa cấu trúc inventory, không phải sizing recommendation.

## 5. Chọn database đích và xác minh engine pair

Đích đến có thể là Amazon RDS, Amazon Aurora hoặc database tự quản lý trên Amazon EC2. Mỗi lựa chọn có giới hạn, quyền quản trị và trách nhiệm vận hành khác nhau.

| Đích | Khi phù hợp | Cần kiểm tra |
|---|---|---|
| Amazon RDS for PostgreSQL/MySQL | Muốn dùng managed database engine phổ biến | Phiên bản, extension, parameter group, giới hạn quyền superuser |
| Amazon Aurora PostgreSQL-Compatible | Cần kiến trúc storage phân tán, khả năng mở rộng và tích hợp Aurora | Tương thích PostgreSQL theo phiên bản, extension, tính năng Aurora-specific |
| Amazon Aurora MySQL-Compatible | Ứng dụng phù hợp MySQL và cần đặc tính Aurora | MySQL compatibility version, behavior khác biệt, parameter |
| Amazon RDS for Oracle/SQL Server | Muốn giữ engine hoặc giảm thay đổi ứng dụng | Edition, license, option, feature support và giới hạn RDS |
| Database trên EC2 | Cần quyền kiểm soát OS/engine sâu hoặc tính năng đặc biệt | Tự chịu trách nhiệm patch, backup, HA, monitoring và recovery |

Tên “compatible” không có nghĩa mọi tính năng, extension hoặc hành vi của engine gốc đều giống nhau. Aurora PostgreSQL-Compatible có compatibility theo phiên bản PostgreSQL được công bố, nhưng vẫn có khác biệt ở kiến trúc, extension và tính năng do AWS quản lý. RDS cũng giới hạn một số quyền quản trị cấp hệ điều hành hoặc superuser.

Trước khi chốt đích:
1. Xác nhận source/target engine pair nằm trong danh sách được công cụ migration hỗ trợ.
2. Kiểm tra phiên bản engine đích có hỗ trợ tính năng ứng dụng cần dùng.
3. Đối chiếu extension, plugin, collation, encoding và loại index.
4. Xem giới hạn về connection, storage, transaction, log và replication.
5. Đánh giá license, chi phí, HA, backup, encryption và DR.
6. Thử nghiệm với một schema đại diện, có đủ object khó.

Không chọn đích chỉ dựa vào tên engine hoặc chi phí instance. Tính tương thích và chi phí chuyển đổi code có thể lớn hơn chênh lệch giá compute.

## 6. Các công cụ AWS trong schema assessment và conversion

### 6.1 AWS Schema Conversion Tool (AWS SCT)

AWS SCT là công cụ hỗ trợ đánh giá và chuyển đổi schema/code giữa các hệ quản trị cơ sở dữ liệu khác nhau. Tùy cặp nguồn/đích và phiên bản công cụ, SCT có thể:
- Kết nối database nguồn và đích.
- Phân tích object và tính năng.
- Tạo assessment report.
- Phân loại phần có thể tự động chuyển đổi và phần cần hành động thủ công.
- Sinh DDL hoặc code đích cho các object được hỗ trợ.
- Hỗ trợ chuyển đổi một số ứng dụng hoặc artifact phụ trợ trong các kịch bản được hỗ trợ.

SCT không thể hiểu đầy đủ ý nghĩa nghiệp vụ của mọi stored procedure, trigger hoặc dynamic SQL. Kết quả cần được DBA và application owner review.

### 6.2 AWS DMS Schema Conversion

AWS DMS Schema Conversion cung cấp khả năng đánh giá và chuyển đổi schema trong quy trình migration của AWS DMS cho các engine pair được hỗ trợ. Khả năng, giao diện, loại object và engine pair thay đổi theo phiên bản và dịch vụ. Hãy xác nhận danh sách hỗ trợ hiện hành trong tài liệu AWS trước khi thiết kế quy trình.

Khi lựa chọn công cụ:
- Dùng công cụ phù hợp với source/target pair cụ thể.
- Xác nhận engine version và quyền cần cấp để đọc metadata.
- Đánh giá khả năng xử lý stored code, package, trigger và object đặc thù.
- Lưu lại phiên bản công cụ và cấu hình assessment để có thể tái lập.
- Chạy thử trên bản sao hoặc môi trường staging.

### 6.3 AWS Database Migration Service (AWS DMS)

AWS DMS chủ yếu di chuyển dữ liệu từ nguồn sang đích. Tùy engine và cấu hình, DMS hỗ trợ full load, ongoing replication/change data capture (CDC), hoặc kết hợp hai chế độ.

DMS không tự biến mọi logic database nguồn thành logic tương đương ở đích. DDL và stored code cần được đánh giá/chuyển đổi bằng công cụ schema conversion hoặc quy trình thủ công. DMS task cũng cần cấu hình mapping, table selection, endpoint, network, replication instance/serverless capacity, LOB mode và xử lý lỗi phù hợp.

### 6.4 Phân biệt vai trò

| Thành phần | Vai trò | Không nên giả định |
|---|---|---|
| Schema assessment | Tìm khác biệt giữa nguồn và đích | Điểm assessment cao nghĩa ứng dụng chạy đúng |
| Schema conversion | Sinh/chuyển DDL và code được hỗ trợ | Mọi logic nghiệp vụ được dịch chính xác |
| DMS full load | Tải dữ liệu hiện có | Schema và object đã được chuyển đổi đầy đủ |
| DMS CDC | Đồng bộ thay đổi trong quá trình migration | DDL thay đổi tùy ý sẽ được đồng bộ an toàn |
| Application refactor | Điều chỉnh SQL, driver, config và logic | Chỉ đổi connection string là đủ |
| Validation | Xác nhận schema, dữ liệu và hành vi | Row count giống nhau là chứng minh toàn vẹn |

## 7. Đọc assessment report

Assessment report là danh sách phát hiện về khả năng chuyển đổi và các hành động cần xử lý. Tên nhóm, cách tính và mức độ chi tiết phụ thuộc công cụ và phiên bản, nhưng khi review nên tìm các loại phát hiện sau:

- Object có thể chuyển đổi tự động.
- Object chuyển đổi một phần.
- Object không được hỗ trợ hoặc không có mapping trực tiếp.
- Cú pháp SQL cần viết lại.
- Built-in function cần thay thế.
- Data type cần mapping hoặc xác nhận precision/range.
- Stored procedure/package có code phức tạp.
- Feature nguồn phụ thuộc extension hoặc quyền đặc biệt.
- Object phụ thuộc object khác chưa được chuyển đổi.

Không dùng phần trăm tự động chuyển đổi làm KPI duy nhất. Một schema có 98% object tự động chuyển đổi vẫn có thể chứa một package quan trọng xử lý settlement hoặc tính thuế chưa tương thích. Ngược lại, nhiều object phụ trợ không được dùng có thể làm tỷ lệ chuyển đổi thấp nhưng rủi ro thực tế nhỏ.

### 7.1 Phân loại theo tác động

Có thể lập bảng remediation riêng:

| Mức | Định nghĩa | Ví dụ | Cách xử lý |
|---|---|---|---|
| P0 - Blocker | Không thể cutover nếu chưa xử lý | Procedure ghi nhận giao dịch không có mapping | Thiết kế lại, viết lại và kiểm thử nghiệp vụ |
| P1 - High | Ảnh hưởng correctness, security hoặc workload quan trọng | Khác biệt NULL, timezone, precision | Sửa và kiểm thử hồi quy bắt buộc |
| P2 - Medium | Ảnh hưởng một nhóm chức năng hoặc hiệu năng | Index type không tương đương | Thay thế và benchmark |
| P3 - Low | Ít được dùng hoặc có workaround rõ | Comment, object cũ không còn tham chiếu | Xác minh dependency và loại bỏ có kiểm soát |

Mỗi phát hiện nên ghi:
- Object/schema và vị trí cụ thể.
- Source construct và target limitation.
- Ảnh hưởng đến nghiệp vụ hoặc ứng dụng.
- Cách xử lý được đề xuất.
- Owner và người review.
- Test case chứng minh đã xử lý.
- Trạng thái và bằng chứng.

### 7.2 Xác minh object còn được sử dụng

Không phải mọi object trong catalog đều còn được ứng dụng sử dụng. Tuy nhiên, không được xóa object chỉ vì công cụ đánh dấu khó chuyển đổi.

Dùng nhiều nguồn bằng chứng:
- Dependency trong catalog.
- Query/statement logs và database monitoring.
- Code repository và cấu hình ứng dụng.
- Job scheduler, ETL và BI metadata.
- Phỏng vấn application owner/DBA.
- Quan sát qua chu kỳ nghiệp vụ đủ dài, gồm batch cuối tháng/quý.

Object ít xuất hiện trong log vẫn có thể được gọi bởi quy trình hàng quý hoặc disaster recovery. Việc loại bỏ phải có owner xác nhận và kế hoạch rollback.

## 8. Khác biệt kiểu dữ liệu và giá trị

Mapping kiểu dữ liệu là một trong những phần dễ gây lỗi âm thầm. Hãy kiểm tra không chỉ tên type mà cả miền giá trị, precision, scale, encoding và cách ứng dụng bind/đọc giá trị.

Bảng sau chỉ đưa ra hướng mapping thường gặp. Kiểu đích chính xác phải được chọn theo engine pair, phiên bản, dữ liệu thực tế và yêu cầu ứng dụng.

| Nguồn thường gặp | Đích PostgreSQL/Aurora PostgreSQL | Đích MySQL/Aurora MySQL | Điểm cần xác minh |
|---|---|---|---|
| Oracle `NUMBER(p,s)` | `numeric(p,s)` hoặc integer phù hợp | `DECIMAL(p,s)` hoặc integer | Precision, scale, overflow, rounding |
| Oracle `NUMBER` không precision | `numeric` hoặc kiểu số cụ thể | `DECIMAL` hoặc kiểu số cụ thể | Miền giá trị thực tế và semantics |
| SQL Server `DECIMAL(p,s)` | `numeric(p,s)` | `DECIMAL(p,s)` | Không giảm precision khi mapping |
| Oracle `VARCHAR2(n)` | `varchar(n)`/`text` | `varchar(n)`/`text` | Character vs byte semantics, encoding |
| Oracle `NVARCHAR2` | `varchar` với encoding phù hợp | `varchar` với charset phù hợp | Unicode và giới hạn byte |
| SQL Server `NVARCHAR` | `varchar`/`text` với UTF-8 database | `varchar` với charset phù hợp | Collation, Unicode, độ dài |
| Oracle `DATE` | `timestamp` hoặc `date` theo semantics thực tế | `datetime`/`date` | Oracle DATE có cả giờ/phút/giây |
| Oracle `TIMESTAMP WITH TIME ZONE` | `timestamptz` sau khi xác định semantics | `timestamp` và quy ước timezone rõ ràng | Offset, zone identity, DST |
| SQL Server `DATETIME2` | `timestamp` | `datetime(precision)` phù hợp | Precision và range |
| SQL Server `BIT` | `boolean` hoặc `smallint` | `boolean`/`tinyint(1)` theo quy ước | ORM, driver và giá trị legacy |
| SQL Server `UNIQUEIDENTIFIER` | `uuid` | `char(36)` hoặc `binary(16)` theo thiết kế | Sort/order, representation, index |
| Oracle `RAW` / SQL Server `VARBINARY` | `bytea` | `varbinary`/`blob` | Dung lượng, LOB và cách truyền |
| Oracle `CLOB` / SQL Server `NVARCHAR(MAX)` | `text` | `longtext` | LOB streaming và giới hạn |
| Oracle `BLOB` / SQL Server `VARBINARY(MAX)` | `bytea` hoặc large object theo thiết kế | `longblob` | Dung lượng, memory và API driver |
| JSON | `json`/`jsonb` | `JSON` | Validation, indexing và query semantics |
| XML | `xml` hoặc text/JSON theo thiết kế | `xml` không có native type tương đương ở MySQL; có thể lưu text | Query, validation và namespace |
| Spatial type | PostGIS nếu được hỗ trợ/cài đặt | Spatial type tương ứng | SRID, index và function |
| Array/user-defined type | Type/array PostgreSQL nếu phù hợp | Thiết kế bảng/JSON hoặc type khác | Serialization và ứng dụng |

### 8.1 Precision và scale

Với `DECIMAL(p,s)`, p là tổng số chữ số và s là số chữ số sau dấu thập phân. Nếu nguồn cho phép giá trị lớn hơn đích, load có thể lỗi hoặc dữ liệu bị làm tròn.

Ví dụ:

~~~sql
-- PostgreSQL/Aurora PostgreSQL
CREATE TABLE invoice_line (
    amount numeric(18, 4) NOT NULL
);
~~~

~~~sql
-- MySQL/Aurora MySQL
CREATE TABLE invoice_line (
    amount DECIMAL(18, 4) NOT NULL
);
~~~

Trước khi mapping, truy vấn giá trị lớn nhất/nhỏ nhất, số chữ số nguyên, số chữ số thập phân và số giá trị vượt miền. Đừng tự động chuyển `NUMBER` thành `INTEGER` chỉ vì dữ liệu mẫu hiện tại toàn số nguyên.

### 8.2 Date, time và timezone

Cần phân biệt:
- Ngày lịch không có thời gian.
- Timestamp không có timezone.
- Timestamp có offset/timezone.
- Thời gian UTC được lưu theo quy ước ứng dụng.
- Thời gian địa phương theo múi giờ nghiệp vụ.

Các câu hỏi phải trả lời:
1. Nguồn lưu giá trị theo UTC hay local time?
2. Session timezone có ảnh hưởng đến query không?
3. Có phụ thuộc daylight saving time (DST) không?
4. Ứng dụng có so sánh timestamp từ nhiều Region không?
5. Đích có giữ nguyên instant, offset hay tên timezone?
6. Dữ liệu lịch sử có giá trị ambiguous trong giờ DST không?

Đối với hệ thống giao dịch, nên thống nhất cách lưu instant theo UTC và giữ timezone nghiệp vụ riêng khi cần hiển thị lịch địa phương. Không được chuyển timestamp chỉ bằng cách đổi tên type.

### 8.3 NULL, chuỗi rỗng và default

Oracle coi chuỗi rỗng trong kiểu character như NULL trong nhiều ngữ cảnh. PostgreSQL và MySQL phân biệt `''` với `NULL`.

Nếu ứng dụng dùng chuỗi rỗng để biểu thị “không có dữ liệu”, migration có thể làm thay đổi:
- Kết quả `IS NULL`.
- Unique constraint.
- Filter và aggregate.
- Logic `COALESCE`/`NVL`.
- Validation trong ORM và API.

Cần lập quy tắc rõ ràng: giá trị nào là NULL, giá trị nào là chuỗi rỗng và cách chuẩn hóa dữ liệu lịch sử. Kiểm tra default expression và việc ứng dụng có bỏ qua cột hay truyền NULL tường minh.

### 8.4 Character set và collation

Kiểm tra:
- Encoding database và column.
- Case-sensitive/case-insensitive comparison.
- Accent-sensitive/accent-insensitive behavior.
- Sort order và locale.
- Độ dài ký tự so với byte.
- Index theo collation.
- Unicode normalization và dữ liệu ký tự đặc biệt.

Hai database cùng chứa chuỗi UTF-8 vẫn có thể trả kết quả `ORDER BY`, `LIKE` hoặc unique check khác nhau vì collation. Nếu ứng dụng dựa vào thứ tự hoặc phép so sánh này, hãy tạo test bằng dữ liệu tiếng Việt có dấu, chữ hoa/thường, dấu kết hợp và ký tự ngoài BMP.

## 9. Khác biệt object và SQL dialect

### 9.1 Identity, sequence và generated key

Các DBMS có cơ chế cấp ID khác nhau:
- Oracle thường dùng sequence, có thể kết hợp trigger.
- SQL Server có `IDENTITY` và sequence.
- PostgreSQL hỗ trợ sequence và identity column.
- MySQL sử dụng `AUTO_INCREMENT`.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE customer (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email varchar(320) NOT NULL
);
~~~

Ví dụ MySQL:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    PRIMARY KEY (customer_id)
);
~~~

Sau full load, sequence hoặc identity counter phải được đồng bộ với giá trị lớn nhất đã nạp. Nếu không, lần insert tiếp theo có thể tạo khóa trùng. Kiểm tra cả ứng dụng có tự cấp ID, gọi `RETURNING`, dùng `LAST_INSERT_ID()` hoặc đọc generated key qua JDBC.

### 9.2 Constraint

Kiểm tra:
- Primary key và unique constraint.
- Foreign key và cascade action.
- Check constraint.
- Deferrable/deferred constraint.
- Constraint disabled, not validated hoặc dữ liệu legacy vi phạm.
- Thứ tự tạo và validate constraint trong full load.

Một số engine có thể cho phép constraint tồn tại ở trạng thái chưa validate hoặc có cơ chế deferrable khác nhau. Nếu logic ứng dụng phụ thuộc việc kiểm tra constraint cuối transaction, cần test chính xác trên đích.

### 9.3 Index

Index không chỉ là danh sách cột. Cần đánh giá:
- B-tree, hash, bitmap, full-text, spatial và các loại chuyên biệt.
- Unique, composite, partial/filtered và expression index.
- Included columns, clustered/nonclustered.
- Sort direction, null ordering và collation.
- Index trên function hoặc generated column.
- Maintenance cost và write amplification.

Một index bitmap ở nguồn có thể không có tương đương trực tiếp ở đích. Hãy thiết kế index theo workload và khả năng engine đích, không cố gắng dịch tên index một cách máy móc.

### 9.4 Partitioning

Thu thập partition key, range/list/hash strategy, subpartition, interval, retention và query pattern. Kiểm tra khả năng partition pruning và cách quản lý partition ở đích.

Ví dụ, partition theo ngày trên nguồn có thể cần chuyển sang range partition ở PostgreSQL hoặc partition scheme phù hợp của MySQL. Cú pháp, giới hạn số partition và thao tác attach/detach/drop khác nhau theo engine/version.

### 9.5 View và materialized view

View thường phụ thuộc function, schema, synonym và quyền truy cập. Materialized view có thể có cơ chế refresh, index và scheduler riêng.

Sau conversion:
- Kiểm tra dependency và thứ tự tạo.
- Chạy query để xác nhận kết quả giống nguồn.
- Kiểm tra quyền owner/invoker.
- Xác định cách refresh và lịch refresh ở đích.
- Đánh giá tác động đến query plan.

### 9.6 Stored procedure, function và package

Đây thường là phần có công sức chuyển đổi lớn nhất trong heterogeneous migration.

Khác biệt có thể gồm:
- Ngôn ngữ procedural (PL/SQL, T-SQL, PL/pgSQL).
- Exception handling và error code.
- Cursor, bulk operation và dynamic SQL.
- Temporary table và table variable.
- Transaction control bên trong procedure.
- Package, global variable và session state.
- Function determinism, side effect và quyền thực thi.
- Scheduler, job và external procedure.
- Built-in function và date arithmetic.

Ví dụ Oracle:

~~~sql
CREATE OR REPLACE PROCEDURE close_order (
    p_order_id IN NUMBER
) AS
BEGIN
    UPDATE orders
       SET status = 'CLOSED'
     WHERE order_id = p_order_id;
END;
/
~~~

Một phiên bản PostgreSQL minh họa:

~~~sql
CREATE OR REPLACE PROCEDURE close_order(p_order_id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE orders
       SET status = 'CLOSED'
     WHERE order_id = p_order_id;
END;
$$;
~~~

Hai đoạn code có mục đích gần nhau nhưng chưa chứng minh tương đương trong mọi tình huống. Cần kiểm tra kiểu tham số, transaction, quyền, exception, trigger được kích hoạt, row count và cách ứng dụng gọi procedure.

### 9.7 Trigger

Trigger có thể chạy trước/sau insert/update/delete, theo từng row hoặc statement tùy engine. Thứ tự giữa nhiều trigger, recursion, transition table và transaction behavior có thể khác.

Đặc biệt chú ý trigger dùng để:
- Sinh khóa.
- Ghi audit.
- Cập nhật bảng tổng hợp.
- Enforce business rule.
- Gửi side effect ra ngoài.
- Đồng bộ dữ liệu sang bảng khác.

Khi DMS full load hoặc CDC đang chạy, cần hiểu trigger trên target có được bật hay không và có nguy cơ ghi dữ liệu trùng hoặc tạo side effect ngoài dự kiến. Kế hoạch migration phải quy định thời điểm tạo/bật trigger và cách xử lý dữ liệu do trigger sinh ra.

### 9.8 Synonym, package và database link

Các object phụ thuộc môi trường nguồn như synonym, package, database link, external table hoặc linked server thường cần thiết kế lại. Có thể thay thế bằng:
- Schema-qualified name.
- View hoặc wrapper.
- API/service boundary.
- Federation hoặc integration service.
- ETL/replication pipeline.
- Database link tương ứng nếu đích hỗ trợ và mô hình bảo mật cho phép.

Không mở rộng quyền network giữa hai database chỉ để giữ nguyên một database link mà chưa đánh giá trust boundary.

## 10. SQL semantics và hành vi khác biệt

Một câu query có thể chạy thành công nhưng trả kết quả khác. Hãy kiểm tra semantics chứ không chỉ syntax.

| Chủ đề | Khác biệt cần kiểm tra | Test đề xuất |
|---|---|---|
| Case folding | Cách engine xử lý identifier không quote | Tạo bảng/cột chữ hoa, chữ thường và truy vấn |
| Identifier length | Giới hạn độ dài tên object | Kiểm tra tên dài và tên trùng sau truncate |
| NULL | Three-valued logic, empty string, aggregate | So sánh `IS NULL`, `COUNT`, `COALESCE` |
| String comparison | Collation, accent, case, trailing spaces | So sánh tiếng Việt và chuỗi có khoảng trắng |
| Date arithmetic | Cộng tháng, cuối tháng, timezone | Test ngày cuối tháng và DST |
| Numeric rounding | Precision, scale và rounding mode | Test giá trị sát ranh giới |
| Pagination | `ROWNUM`, `TOP`, `LIMIT`, `OFFSET`, window function | Kiểm tra thứ tự ổn định và bản ghi trùng |
| Upsert/merge | `MERGE`, `ON CONFLICT`, `ON DUPLICATE KEY` | Test insert/update đồng thời |
| Sequence | Cấp ID, cache, restart và đồng bộ | Test sau full load và failover |
| Locking | Row/table lock, deadlock detection | Test concurrency và retry |
| Isolation | Read committed, repeatable read, serializable | Test transaction đồng thời |
| Temporary object | Session/global temp table semantics | Test connection pooling và cleanup |
| Error handling | SQLSTATE, vendor code, exception | Kiểm tra retry và error mapping |
| JSON | Path, null/missing, comparison và index | Test payload thiếu field, null và array |
| Regex | Dialect và collation | Test pattern thực tế |

### 10.1 Identifier và schema naming

PostgreSQL chuyển identifier không quote về chữ thường; Oracle truyền thống xử lý identifier không quote theo chữ hoa. MySQL có hành vi phụ thuộc platform và cấu hình đối với tên database/table. Vì vậy:
- Tránh phụ thuộc vào chữ hoa/thường không nhất quán.
- Chuẩn hóa naming convention.
- Kiểm tra identifier có quote trong code.
- Kiểm tra tên bị trùng hoặc quá dài sau mapping.
- Thay thế dynamic SQL xây tên object theo quy tắc cũ.

### 10.2 SQL function

Các hàm tương tự tên không nhất thiết giống semantics:
- `NVL` thường được thay bằng `COALESCE` hoặc biểu thức phù hợp.
- `SYSDATE`, `CURRENT_TIMESTAMP`, `GETDATE()` có khác biệt về timezone và thời điểm đánh giá.
- `DECODE` có thể cần `CASE`.
- `LISTAGG`, `STRING_AGG`, `GROUP_CONCAT` có cú pháp và thứ tự khác.
- Hàm ngày/tháng, regex, substring và conversion có thể trả kết quả khác.

Không thực hiện replace hàng loạt mà không có test. Hãy kiểm tra null, kiểu dữ liệu, locale và precision cho từng phép chuyển.

### 10.3 Transaction và locking

Đánh giá:
- Isolation level mặc định.
- Snapshot/MVCC behavior.
- Row-level và table-level locking.
- Deadlock detection và victim selection.
- Lock timeout và statement timeout.
- Transaction DDL.
- Savepoint và nested transaction behavior.
- Autocommit trong driver.
- Retry logic trong ứng dụng.

Một ứng dụng có thể phụ thuộc vào lock escalation hoặc cách engine nguồn xử lý concurrent update. Sau migration, test nhiều client ghi cùng một hàng, cập nhật cùng một aggregate và chạy batch cùng giờ cao điểm.

## 11. Ứng dụng và driver compatibility

Schema chỉ là một phần của hợp đồng giữa ứng dụng và database. Hãy rà soát toàn bộ đường đi của dữ liệu.

### 11.1 JDBC và ORM

Với ứng dụng Java:
- Xác nhận JDBC driver version hỗ trợ target engine/version.
- Cập nhật JDBC URL, TLS, authentication và connection properties.
- Kiểm tra mapping `NUMERIC`, `TIMESTAMP`, `UUID`, `BLOB`, `CLOB`, `JSON`.
- Kiểm tra generated keys, batch insert, callable statement và cursor.
- Rà soát Hibernate/JPA dialect hoặc MyBatis type handler.
- Kiểm tra schema validation/generation của ORM.
- Xem lại connection pool, validation query, timeout và retry.
- Kiểm tra exception translation và SQLState.

Không nên chỉ thay driver và hostname rồi đưa thẳng lên production. Hãy chạy test integration bằng chính phiên bản driver và framework dự kiến triển khai.

### 11.2 Dynamic SQL và query nằm ngoài repository

Query có thể nằm trong:
- File cấu hình.
- Report tool.
- Stored procedure.
- ETL script.
- BI dashboard.
- Batch job.
- Notebook và script vận hành.
- Ứng dụng của đối tác.

Dùng log/query history, code search và phỏng vấn owner để phát hiện các query này. Xây một catalog gồm query ID, caller, mức độ quan trọng, engine-specific syntax và trạng thái chuyển đổi.

### 11.3 Connection và authentication

Kiểm tra:
- Endpoint writer/reader.
- DNS resolution và failover behavior.
- Port và network path.
- TLS mode và certificate trust.
- Password auth, IAM database authentication hoặc cơ chế khác được hỗ trợ.
- Secret rotation.
- Connection pool lifetime và stale connection.
- DNS cache của JVM/runtime.
- Timeout, keepalive và retry policy.

Aurora cluster endpoint và RDS endpoint có vai trò khác nhau. Ứng dụng cần dùng endpoint phù hợp với read/write behavior và có khả năng tái kết nối sau failover.

## 12. Đánh giá hiệu năng sau khi chuyển đổi

Một schema hợp lệ không bảo đảm workload chạy nhanh như nguồn. Optimizer, statistics, storage, CPU, memory, connection limit và concurrency khác nhau.

### 12.1 Workload baseline

Trước migration, thu thập:
- Top SQL theo total elapsed time, CPU, reads và executions.
- P50/P95/P99 latency.
- Throughput và transaction rate.
- Peak connections và active sessions.
- Lock wait, deadlock và long-running transaction.
- Buffer/cache hit ratio.
- Storage IOPS, throughput và queue depth.
- Batch duration và thời gian hoàn tất nghiệp vụ.

Chọn workload đại diện cho giờ cao điểm, batch, báo cáo và kỳ chốt sổ.

### 12.2 Index và query plan

Sau khi chuyển đổi:
1. Cập nhật statistics theo hướng dẫn engine đích.
2. Chạy `EXPLAIN`/execution plan cho top SQL.
3. So sánh số lần scan, join order, estimated/actual rows.
4. Xác định index không còn hữu ích hoặc index mới cần thiết.
5. Benchmark cả read và write vì thêm index làm tăng chi phí ghi.
6. Kiểm tra partition pruning và parameter-sensitive plan nếu engine hỗ trợ.

Không tạo index chỉ vì nó tồn tại ở nguồn. Hãy dùng query workload và dữ liệu đích để xác định thiết kế phù hợp.

### 12.3 Kiểm tra dữ liệu lệch phân bố

Optimizer có thể chọn plan sai nếu statistics không phản ánh dữ liệu mới. Với bảng lớn:
- Thu thập statistics sau full load.
- Kiểm tra skew ở các cột filter/join.
- Xem xét histogram hoặc extended statistics nếu được hỗ trợ.
- Kiểm tra partition-level statistics.
- Benchmark với dữ liệu gần production về số lượng và phân bố.

## 13. Bảo mật và quyền ở database đích

Không nên sao chép nguyên trạng mọi quyền từ nguồn. Hãy tái thiết kế theo least privilege và trách nhiệm workload.

Kiểm tra:
- User, role, schema owner và object owner.
- SELECT/INSERT/UPDATE/DELETE/EXECUTE.
- Quyền tạo object và quyền quản trị.
- Row-level security hoặc policy tương đương.
- Encryption at rest và in transit.
- KMS key, key policy và quyền sử dụng.
- Audit logging và log export.
- Secret storage và rotation.
- Quyền DMS replication user.
- Quyền truy cập S3 nếu dùng staging/export.
- Quyền network giữa on-premises và VPC.

Database credential không nên được hardcode trong migration script hoặc source repository. Dùng AWS Secrets Manager hoặc cơ chế quản lý secret được phê duyệt. Nếu ứng dụng dùng IAM database authentication, xác minh engine/instance/driver hỗ trợ và thời hạn token trước khi triển khai.

## 14. Thiết kế kế hoạch schema conversion

Một quy trình có kiểm soát gồm các bước sau.

### Bước 1: chốt source và target

Ghi rõ engine/version, schema scope, target engine/version, Region, VPC, HA, encryption và owner. Xác nhận source/target pair được công cụ hỗ trợ.

### Bước 2: chuẩn bị môi trường assessment

- Cấp quyền đọc metadata cần thiết.
- Thiết lập kết nối an toàn đến nguồn và đích.
- Tạo target database/schema thử nghiệm.
- Cài đặt hoặc mở công cụ đúng phiên bản.
- Ghi nhận cấu hình, thời điểm và danh tính người chạy.
- Dùng bản sao hoặc snapshot khi cần hạn chế tải trên production.

### Bước 3: chạy assessment

Chạy assessment trên toàn bộ schema trong scope. Lưu report gốc, log và danh sách object. Đừng chỉ lưu tổng điểm hoặc phần trăm.

### Bước 4: phân loại và ưu tiên

Phân loại blocker, high, medium, low; xác minh object có được dùng không; gán owner và deadline. Nhóm các vấn đề theo nguyên nhân chung như data type, function, package, collation hoặc security.

### Bước 5: convert tự động

Dùng AWS SCT hoặc AWS DMS Schema Conversion theo engine pair hỗ trợ. Sinh DDL/code vào môi trường đích hoặc artifact có thể review. Không chạy trực tiếp thay đổi trên production chỉ vì công cụ tạo được script.

### Bước 6: sửa thủ công

DBA và application owner xử lý phần không tự động chuyển đổi:
- Viết lại routine.
- Thiết kế lại sequence/identity.
- Chọn data type.
- Thay index/partition.
- Chuyển scheduler và job.
- Thiết kế lại database link hoặc external dependency.
- Cập nhật role/grant.
- Điều chỉnh SQL trong ứng dụng.

Mỗi sửa đổi cần test case và reviewer.

### Bước 7: triển khai theo dependency

Tạo extension/type/schema trước object phụ thuộc. Sau đó tạo table, sequence, constraint, index, view và routine theo thứ tự phù hợp. Constraint hoặc index nặng có thể cần chiến lược riêng để giảm thời gian load.

### Bước 8: lặp lại assessment và review

Chạy lại assessment sau khi thay đổi. So sánh report để bảo đảm blocker đã được xử lý và không tạo ra vấn đề mới.

### Bước 9: đóng băng schema cho migration rehearsal

Quy định thời điểm freeze DDL, cách phê duyệt thay đổi và cách áp dụng hotfix. DDL thay đổi trong khi full load/CDC có thể làm lệch mapping hoặc khiến task lỗi.

## 15. Ví dụ quy trình chuyển đổi Oracle sang Aurora PostgreSQL-Compatible

Tình huống giả định: hệ thống order dùng Oracle làm nguồn và đội dự án đánh giá Aurora PostgreSQL-Compatible làm đích. Mục tiêu là giảm phụ thuộc license và chuẩn hóa nền tảng cho ứng dụng Java.

### 15.1 Inventory

Đội thu thập:
- Phiên bản Oracle và cấu hình character set.
- Danh sách schema, bảng, partition, index.
- Package PL/SQL, procedure, function và trigger.
- Sequence và trigger sinh khóa.
- Materialized view, scheduler job và database link.
- Top SQL, transaction rate, peak connection.
- JDBC driver, ORM, stored procedure call trong ứng dụng.

### 15.2 Assessment

Công cụ assessment phát hiện:
- Table và column mapping phần lớn có thể chuyển đổi.
- Một số `NUMBER` cần xác định precision.
- Một số `DATE` chứa thành phần thời gian.
- Package PL/SQL cần viết lại.
- Một số function dùng `NVL`, `DECODE`, `CONNECT BY` cần thay thế.
- Database link và scheduler job cần thiết kế lại.
- Một số index chuyên biệt cần đánh giá lại.

Đội không lấy tỷ lệ object chuyển đổi tự động làm tiêu chí duy nhất. Package xử lý trạng thái order và tính phí được xếp P0 vì ảnh hưởng trực tiếp đến correctness.

### 15.3 Chuyển đổi và sửa thủ công

- Tạo schema và bảng trên Aurora PostgreSQL.
- Mapping `NUMBER` dựa trên miền giá trị thực tế.
- Chuyển sequence/trigger sang identity hoặc sequence theo cách ứng dụng cấp ID.
- Viết lại procedure/package thành function/procedure PostgreSQL.
- Thay function SQL và query phân cấp.
- Thiết kế lại database link thành service/API hoặc luồng tích hợp có kiểm soát.
- Tạo index dựa trên workload và benchmark.

### 15.4 Kiểm thử

- So sánh số lượng row và checksum theo partition.
- Kiểm tra giá trị decimal cực đại, NULL, chuỗi rỗng và timestamp.
- Chạy test order lifecycle, refund, settlement và batch.
- So sánh query plan và latency.
- Kiểm tra quyền, audit và secret rotation.
- Chạy rehearsal full load + CDC + cutover.

### 15.5 Quyết định cutover

Chỉ chuyển khi:
- Không còn blocker chưa có quyết định được phê duyệt.
- Critical stored code đã có test nghiệp vụ.
- Data validation đạt ngưỡng đã thống nhất.
- Application integration và performance đạt tiêu chí.
- Có owner trực ca, runbook và rollback.
- RPO/RTO và cửa sổ downtime đã được xác nhận.

Đây là ví dụ minh họa quy trình, không phải hướng dẫn chuyển đổi tự động cho mọi database Oracle.

## 16. Di chuyển dữ liệu và phối hợp với AWS DMS

Sau khi schema đích sẵn sàng, nhóm migration mới lập kế hoạch chuyển dữ liệu. AWS DMS thường được dùng cho full load và CDC trong các kịch bản phù hợp.

### 16.1 Trình tự tổng quát

~~~text
Source database
      |
      | Schema assessment / conversion
      v
Target schema (RDS / Aurora)
      |
      | DMS full load
      v
Initial target data
      |
      | DMS CDC from source logs
      v
Target catches up
      |
      | Validation + application tests
      v
Cutover
      |
      v
Target becomes primary
~~~

### 16.2 Full load

Full load sao chép dữ liệu hiện có của các bảng được chọn. Trước khi chạy:
- Xác minh schema, type mapping và target table preparation mode.
- Chọn table mapping và transformation rule.
- Đánh giá LOB mode, batch size và parallel load.
- Kiểm tra FK, trigger và constraint có ảnh hưởng load không.
- Theo dõi task log, table statistics và lỗi từng bảng.
- Xác định cách xử lý bảng quá lớn hoặc bảng không có primary key.

Không giả định mọi bảng được load đồng thời hoặc không ảnh hưởng đến nguồn. Cần benchmark và kiểm soát tải trên production.

### 16.3 Change Data Capture

CDC đọc transaction log của nguồn để đồng bộ thay đổi phát sinh sau khi full load bắt đầu. Yêu cầu phụ thuộc engine:
- Log retention đủ dài.
- Quyền đọc log/transaction.
- Cấu hình supplemental logging hoặc change tracking nếu engine yêu cầu.
- Network ổn định.
- DMS capacity đủ cho tốc độ thay đổi.
- Target schema sẵn sàng cho mapping.
- Theo dõi replication lag và lỗi apply.

DDL có thể không được xử lý giống DML trong mọi cấu hình. Hãy thống nhất quy trình freeze DDL hoặc đồng bộ thay đổi schema riêng. Không chạy migration schema tùy ý trong lúc CDC mà chưa kiểm chứng.

### 16.4 Validation

AWS DMS có các khả năng validation tùy engine và task configuration. Ngoài ra, đội cần kiểm thử độc lập theo yêu cầu nghiệp vụ. Validation có thể tăng tải nguồn và đích, do đó phải được đưa vào kế hoạch capacity.

## 17. Kiểm chứng schema và dữ liệu sau conversion

Không chỉ xác nhận “script chạy không lỗi”. Cần xác minh cấu trúc, giá trị, quan hệ và hành vi.

### 17.1 Schema validation

Kiểm tra:
- Số lượng và tên object.
- Cột, type, precision, scale, nullability.
- Default và generated expression.
- PK/FK/unique/check constraint.
- Index, partition và sequence.
- View/materialized view.
- Procedure/function/trigger.
- User, role, owner và grant.
- Extension và database configuration.

Có thể export DDL đích và so sánh với expected schema sau khi chuẩn hóa khác biệt không ảnh hưởng semantics.

### 17.2 Data validation

Một bộ kiểm tra cơ bản:

| Kiểm tra | Cách thực hiện | Phát hiện |
|---|---|---|
| Row count | Đếm theo bảng/partition | Thiếu hoặc thừa bản ghi |
| Aggregate | SUM, MIN, MAX, COUNT theo business key | Sai lệch số liệu tổng hợp |
| Null distribution | Đếm NULL và empty string | Sai khác mapping |
| Range | Min/max, độ dài chuỗi, precision | Tràn hoặc cắt dữ liệu |
| Referential integrity | Orphan row, FK check | Quan hệ bị mất |
| Hash/checksum | Hash theo khóa hoặc chunk | Sai khác nội dung |
| Sample compare | So sánh record đại diện và edge case | Sai mapping cụ thể |
| Business reconciliation | Tổng đơn hàng, số dư, settlement | Sai lệch nghiệp vụ |

Với bảng lớn, chia theo primary key hoặc partition để tránh query quét toàn bộ gây ảnh hưởng. Hash phải chuẩn hóa biểu diễn dữ liệu; ví dụ timezone, decimal scale và collation có thể khiến hash khác dù giá trị nghiệp vụ tương đương.

### 17.3 Test dữ liệu biên

Tạo test case cho:
- NULL, empty string, whitespace.
- Chuỗi Unicode và ký tự đặc biệt.
- Decimal gần max precision.
- Số âm, zero và giá trị lớn.
- Timestamp qua midnight, cuối tháng, leap year và DST.
- LOB rỗng, nhỏ, lớn và payload vượt ngưỡng.
- UUID, binary và JSON thiếu field/null field.
- Sequence sau khi load dữ liệu.
- FK, unique và check constraint.
- Transaction rollback và concurrent update.

## 18. Kiểm thử ứng dụng và nghiệp vụ

Tạo test suite chạy trên target với phiên bản ứng dụng, driver, ORM và cấu hình dự kiến production.

Các nhóm test:

1. Smoke test: kết nối, đọc/ghi cơ bản, health check.
2. CRUD test: insert, update, delete, select và pagination.
3. Transaction test: commit, rollback, savepoint, concurrency.
4. Stored code test: procedure/function/trigger và error path.
5. Integration test: queue, cache, search, ETL, payment và service phụ thuộc.
6. Security test: role, privilege, TLS, secret rotation và audit.
7. Performance test: throughput, latency, connection pool và batch.
8. Recovery test: failover, reconnect, backup/restore và rollback.

### 18.1 Kiểm tra transaction nghiệp vụ

Ví dụ một giao dịch tạo đơn hàng có thể cần:
- Ghi order header.
- Ghi order lines.
- Trừ tồn kho.
- Ghi payment intent.
- Ghi audit record.

Nếu nguồn thực hiện tất cả trong một transaction, đích cũng phải giữ invariant tương ứng hoặc có thiết kế nhất quán được phê duyệt. Test cả lỗi ở bước giữa, retry, duplicate request và concurrent purchase.

### 18.2 So sánh kết quả, không chỉ thời gian

Với mỗi test case, so sánh:
- Result set.
- Row count.
- Error behavior.
- Side effect.
- Transaction boundary.
- Latency và resource usage.

Query chạy nhanh hơn nhưng trả kết quả khác không phải là thành công. Query trả kết quả giống nhưng chậm hơn nhiều cũng cần xử lý trước cutover.

## 19. Kế hoạch cutover và rollback

Cutover là chuyển hướng ứng dụng sang database đích. Cần có checklist và người ra quyết định rõ ràng.

### 19.1 Trước cutover

- Đã hoàn thành schema conversion và review.
- Full load/CDC đã rehearsal.
- Replication lag đạt ngưỡng.
- Data validation và application test đạt tiêu chí.
- DDL đã freeze.
- Backup/snapshot theo quy trình đã xác nhận.
- DNS, secret, certificate và endpoint đã chuẩn bị.
- Kế hoạch dừng ghi nguồn và drain connection đã được diễn tập.
- Owner, bridge, thời gian và tiêu chí abort đã được xác nhận.

### 19.2 Trình tự cutover mẫu

1. Thông báo maintenance window.
2. Dừng hoặc hạn chế write trên ứng dụng nguồn.
3. Chờ transaction đang mở hoàn tất.
4. Chờ CDC bắt kịp và xác nhận lag trong ngưỡng.
5. Chạy validation cuối cùng.
6. Đổi cấu hình ứng dụng sang endpoint đích.
7. Khởi động workload theo từng nhóm.
8. Chạy smoke test và business transaction.
9. Theo dõi error rate, latency, database metrics và replication.
10. Xác nhận chuyển đổi thành công theo tiêu chí đã phê duyệt.

Trình tự cụ thể tùy engine và kiến trúc. Không giả định có thể đảo chiều CDC sau khi target đã nhận write mới.

### 19.3 Rollback

Rollback phải được thiết kế trước. Câu hỏi quan trọng nhất: điều gì xảy ra với dữ liệu được ghi vào target sau cutover?

Nếu target đã nhận write mới, quay lại source có thể làm mất hoặc phân kỳ dữ liệu. Cần xác định:
- Có dừng write target được không?
- Có cơ chế reverse replication được hỗ trợ và đã kiểm thử không?
- Có thể replay transaction hoặc reconcile dữ liệu không?
- Thời điểm nào rollback không còn an toàn?
- Ai có quyền ra quyết định?
- Mức mất dữ liệu chấp nhận được là bao nhiêu?

Đừng coi việc đổi DNS về endpoint cũ là rollback đầy đủ. Cần một kế hoạch data consistency rõ ràng.

## 20. Kết nối hybrid và bảo mật đường migration

Nguồn có thể ở on-premises, data center, cloud khác hoặc VPC khác. Kết nối hybrid thường dùng AWS Site-to-Site VPN, AWS Direct Connect hoặc kiến trúc kết hợp.

Đánh giá:
- Latency và throughput thực tế.
- Băng thông cho full load và CDC.
- Routing, subnet và DNS.
- Security group, NACL, firewall và port.
- TLS và certificate trust.
- Network segmentation.
- Quyền kết nối của DMS replication environment.
- Transfer window và giới hạn của đường truyền.
- Khả năng dự phòng khi VPN/Direct Connect gián đoạn.

DMS replication instance hoặc replication environment phải có network path đến cả source và target. Không mở inbound từ mọi CIDR để “cho chạy được”. Dùng security group và firewall rule theo endpoint, port và nguồn kết nối cần thiết.

Nếu dùng VPN/Direct Connect, kiểm thử MTU, packet loss, throughput và route failover. Full load có thể chiếm băng thông ảnh hưởng workload khác; cần giới hạn tốc độ hoặc chia batch theo lịch.

## 21. Quan sát và xử lý lỗi

Theo dõi cả tiến trình migration và chất lượng database đích.

### 21.1 Chỉ số migration

- Full load progress và số bảng đang chạy.
- CDC latency/replication lag.
- Throughput và backlog.
- Task/table error và suspended table.
- DMS CPU/memory/storage nếu áp dụng.
- Network throughput và packet loss.
- Source log retention còn lại.
- Target write pressure và lock wait.

### 21.2 Chỉ số database đích

- CPU, memory, storage, IOPS và throughput.
- Database connections và connection saturation.
- Query latency và top SQL.
- Deadlock, lock wait và long transaction.
- Cache hit, temporary file/spill và vacuum/analyze metrics tùy engine.
- Error log và failover events.
- Backup status và replication health.

Amazon CloudWatch có thể dùng để quan sát metric của RDS/Aurora và một số thành phần DMS. Kết hợp database logs, Performance Insights/Database Insights theo tính năng và cấu hình đang có, cùng log ứng dụng để nối sự kiện migration với ảnh hưởng nghiệp vụ.

### 21.3 Xử lý một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Object không convert | Feature nguồn không có mapping | Đọc assessment chi tiết, thiết kế lại hoặc viết thủ công |
| Insert lỗi precision | Target type nhỏ hơn miền giá trị | Kiểm tra min/max, precision/scale và mapping |
| Mất ký tự | Charset/encoding/collation | Kiểm tra byte length, Unicode và connection encoding |
| Duplicate key sau load | Sequence/identity chưa đồng bộ | Kiểm tra current value và generated key |
| CDC lag tăng | Source log, network hoặc target apply chậm | Đọc DMS metrics/log, kiểm tra workload và capacity |
| FK validation thất bại | Dữ liệu nguồn đã vi phạm hoặc load thiếu | Tìm orphan rows và xác định chính sách dữ liệu |
| Query chậm | Index/statistics/plan khác | Chạy execution plan và benchmark |
| Connection reset | Timeout, DNS, failover hoặc pool stale | Kiểm tra endpoint, TLS, pool lifetime và retry |
| Stored procedure sai kết quả | Semantics/exception/transaction khác | Viết test nghiệp vụ và đối chiếu side effect |
| Deadlock tăng | Thứ tự lock và concurrency khác | Thu thập deadlock graph, điều chỉnh transaction/retry |

## 22. Quản trị thay đổi schema sau migration

Sau khi target trở thành primary, schema tiếp tục thay đổi theo vòng đời ứng dụng. Nếu mỗi đội tự chạy DDL, drift sẽ xuất hiện và các môi trường không còn đồng nhất.

Thiết lập:
- Schema migration tool (ví dụ Flyway hoặc Liquibase) phù hợp engine đích.
- Version control cho DDL và database code.
- Pull request/review cho thay đổi schema.
- Quy tắc backward-compatible change.
- Quy trình expand-and-contract khi thay đổi cột hoặc API.
- Kiểm thử migration trên staging có dữ liệu gần production.
- Backup/restore và rollback script khi phù hợp.
- Theo dõi schema drift giữa dev, staging và production.

Mẫu expand-and-contract:
1. Thêm cột hoặc cấu trúc mới tương thích với code cũ.
2. Deploy ứng dụng có thể đọc/ghi cả cấu trúc cũ và mới.
3. Backfill dữ liệu.
4. Chuyển traffic sang cấu trúc mới.
5. Xác minh không còn consumer dùng cấu trúc cũ.
6. Xóa cấu trúc cũ trong một release riêng.

Không drop/rename cột ngay khi deploy ứng dụng mới nếu các instance cũ còn chạy hoặc rollback vẫn cần schema cũ.

## 23. Checklist đánh giá tương thích

Dùng checklist này trước khi chấp thuận target và conversion plan.

- [ ] Source engine, version, edition và patch level đã được ghi nhận.
- [ ] Target engine/version nằm trong danh sách được AWS và công cụ hỗ trợ.
- [ ] Region, VPC, subnet, security group và hybrid connectivity đã được xác minh.
- [ ] Character set, collation và timezone đã được kiểm kê.
- [ ] Table, column, constraint, index và partition inventory đầy đủ.
- [ ] Sequence, identity và generated key behavior đã được đánh giá.
- [ ] View, materialized view, procedure, function, package và trigger đã được kiểm kê.
- [ ] Extension, plugin, spatial, XML, JSON, LOB và user-defined type đã được đánh giá.
- [ ] SQL dialect và built-in function đã có remediation plan.
- [ ] Transaction, isolation, locking và retry semantics đã được kiểm thử.
- [ ] JDBC/ODBC driver, ORM, ETL, BI và dynamic SQL đã được rà soát.
- [ ] User, role, grant, encryption, secret và audit đã được thiết kế lại.
- [ ] Assessment report đã được lưu và phân loại theo mức độ ảnh hưởng.
- [ ] Mọi blocker có owner, phương án xử lý và test case.
- [ ] Performance baseline và workload test đã được xác định.
- [ ] DMS full load/CDC plan có capacity, log retention và network sizing.
- [ ] Data validation, business reconciliation và acceptance criteria đã được thống nhất.
- [ ] Cutover, rollback và thời điểm rollback không còn an toàn đã được ghi rõ.
- [ ] Có runbook, on-call owner và giám sát sau cutover.

## 24. Bài tập thực hành

### Bài 1: Chọn đích database

Một ứng dụng Java dùng Oracle, có nhiều package PL/SQL, database link và materialized view. Đội dự án muốn chuyển sang PostgreSQL-compatible database.

Yêu cầu:
1. Nêu ít nhất năm dữ kiện cần thu thập trước khi chọn target.
2. Xác định ba loại object có khả năng cần refactor.
3. Nêu lý do không thể chỉ đổi JDBC URL.

Đáp án gợi ý:
- Thu thập Oracle version, edition, character set, timezone, data volume, workload, package dependencies, database links, materialized view, JDBC/ORM, RPO/RTO và downtime.
- Package PL/SQL, database link và materialized view cần kiểm tra kỹ.
- SQL dialect, stored code, type mapping, generated key, driver và transaction semantics có thể khác.

### Bài 2: Xử lý chuỗi rỗng

Nguồn Oracle có cột `customer_code` chứa cả NULL và chuỗi rỗng. Target PostgreSQL phân biệt hai giá trị này.

Yêu cầu: đề xuất quy trình xử lý.

Đáp án:
- Xác định ý nghĩa nghiệp vụ của NULL và empty string.
- Đếm và lấy mẫu dữ liệu.
- Thống nhất quy tắc chuẩn hóa với application owner.
- Chuyển dữ liệu theo quy tắc đã duyệt.
- Sửa query và validation.
- Kiểm thử `IS NULL`, unique constraint, filter và API serialization.

### Bài 3: Đồng bộ sequence

Sau full load, bảng target có ID lớn nhất là 950000 nhưng sequence vẫn cấp giá trị 1.

Yêu cầu: điều gì có thể xảy ra và cần kiểm tra gì?

Đáp án: insert mới có thể va chạm primary key. Cần đồng bộ sequence/identity counter với dữ liệu đã nạp theo cú pháp engine đích, sau đó test nhiều insert đồng thời và generated key qua driver.

### Bài 4: Assessment score cao

Công cụ báo 97% object có thể chuyển đổi tự động nhưng một package thanh toán chưa được hỗ trợ.

Yêu cầu: có thể phê duyệt cutover không?

Đáp án: chưa. Package thanh toán là blocker nếu ảnh hưởng correctness. Cần xác minh dependency, viết lại, kiểm thử settlement/refund/error path và được business owner chấp thuận.

### Bài 5: Chọn cách validation

Bảng giao dịch có 800 triệu dòng. Không thể chạy một query checksum toàn bảng trong maintenance window.

Yêu cầu: đề xuất chiến lược.

Đáp án:
- Chia theo partition hoặc khoảng primary key.
- Dùng row count và aggregate theo ngày/trạng thái.
- Hash theo chunk có quy tắc canonical serialization.
- Lấy mẫu có trọng số và test edge case.
- Chạy validation tăng dần trước cutover, giữ final delta validation cho cửa sổ cuối.
- Đánh giá tải query để không ảnh hưởng production.

### Bài 6: CDC lag

Trong rehearsal, CDC lag tăng liên tục khi workload batch bắt đầu.

Yêu cầu: nêu nhóm nguyên nhân và dữ liệu cần xem.

Đáp án:
- Source log throughput/retention.
- Network bandwidth/latency.
- DMS capacity, task log và backlog.
- Target CPU, IOPS, lock wait, index/FK và write throughput.
- Kích thước transaction và batch pattern.
- Thử điều chỉnh capacity, batch window hoặc load strategy trong môi trường kiểm thử.

### Bài 7: Timezone

Ứng dụng lưu thời điểm thanh toán theo local time của nhiều quốc gia. Sau conversion, báo cáo lệch một giờ ở một số ngày.

Yêu cầu: xác định những yếu tố cần điều tra.

Đáp án:
- Source/target session timezone.
- DST transition và timezone database version.
- Kiểu timestamp có/không có timezone.
- JDBC mapping và serialization.
- Cách ứng dụng chuyển đổi local time thành instant.
- Dữ liệu lịch sử ở vùng giờ có DST.

### Bài 8: Rollback sau khi target đã nhận write

Sau cutover, một số đơn hàng mới đã được ghi vào target. Ứng dụng phát sinh lỗi và đội muốn đổi endpoint về source.

Yêu cầu: vì sao việc này nguy hiểm?

Đáp án: source không có các write mới nên hai database phân kỳ. Đổi endpoint có thể làm mất giao dịch hoặc tạo duplicate khi retry. Cần dừng write, đánh giá reverse replication/reconciliation đã được kiểm thử, xác định nguồn dữ liệu có thẩm quyền và quyết định rollback theo runbook.

## 25. Câu hỏi tự kiểm tra

1. Schema conversion khác data migration ở điểm nào?
2. Vì sao assessment score không đủ để quyết định cutover?
3. Những lớp tương thích nào cần đánh giá?
4. Vì sao phải kiểm kê stored procedure và trigger?
5. Oracle `DATE` có thể khác PostgreSQL `date` như thế nào?
6. Vì sao Oracle empty string cần được xử lý đặc biệt?
7. Precision và scale ảnh hưởng ra sao đến dữ liệu tài chính?
8. Khi nào cần đánh giá collation?
9. Identity và sequence có thể gây lỗi gì sau full load?
10. Vì sao index nguồn không nhất thiết phải tạo y nguyên ở đích?
11. AWS SCT/AWS DMS Schema Conversion và AWS DMS có vai trò gì?
12. CDC cần những điều kiện gì ở source và network?
13. DDL thay đổi trong lúc CDC chạy có rủi ro gì?
14. Row count có chứng minh dữ liệu hoàn toàn chính xác không?
15. Cần kiểm thử những gì ngoài SQL syntax?
16. Vì sao phải dùng đúng JDBC driver và ORM version trên target?
17. Rollback sau khi target nhận write cần giải quyết vấn đề nào?
18. Vì sao cần schema migration tool sau cutover?
19. Hybrid connectivity cần kiểm tra những yếu tố nào?
20. Một blocker schema conversion cần có những thông tin quản trị nào?

Gợi ý trả lời:

1. Schema conversion chuyển cấu trúc/code; data migration chuyển dữ liệu.
2. Một object quan trọng không tương thích có thể ảnh hưởng nghiệp vụ dù số lượng object tự động chuyển đổi cao.
3. Engine, schema, data type, SQL semantics, application, performance, security, operations và migration path.
4. Chúng thường chứa logic nghiệp vụ và có khác biệt lớn giữa dialect.
5. Oracle DATE có cả thành phần giờ/phút/giây; PostgreSQL date chỉ biểu diễn ngày.
6. Oracle thường coi chuỗi rỗng như NULL trong kiểu character; PostgreSQL phân biệt.
7. Có thể gây overflow, rounding hoặc mất chữ số.
8. Khi so sánh/sắp xếp chuỗi, unique key hoặc query phụ thuộc locale/case/accent.
9. Sinh ID trùng với ID đã load.
10. Loại index và optimizer khác nhau; cần thiết kế theo workload đích.
11. SCT/DMS Schema Conversion đánh giá/chuyển đổi schema; DMS di chuyển dữ liệu và CDC.
12. Log/permission phù hợp, network ổn định, capacity đủ và target schema sẵn sàng.
13. Task có thể lỗi hoặc schema mapping không còn khớp.
14. Không; cần checksum, aggregate, edge case và business reconciliation.
15. Result set, transaction, side effect, error handling, concurrency và performance.
16. Driver/ORM có thể khác mapping type, generated key, timeout và SQL dialect.
17. Các write mới trên target và tính nhất quán với source.
18. Để version hóa DDL, review và kiểm soát schema drift.
19. Routing, DNS, latency, throughput, MTU, firewall, SG, TLS và failover.
20. Object, khác biệt, tác động, owner, remediation, test evidence và trạng thái.

## 26. Tài liệu tham khảo chính thức

Tham khảo tài liệu AWS để xác nhận engine pair, phiên bản, công cụ và giới hạn hiện hành trước khi triển khai:

- [AWS Schema Conversion Tool](https://docs.aws.amazon.com/SchemaConversionTool/latest/userguide/Welcome.html)
- [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/schema-conversion.html)
- [AWS Database Migration Service User Guide](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html)
- [AWS DMS supported source and target databases](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.Sources.html)
- [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html)
- [AWS DMS best practices](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_BestPractices.html)
- [Amazon RDS DB engine versions](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_DBEngineVersions.html)
- [Amazon Aurora PostgreSQL-Compatible documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraPostgreSQL.html)
- [Amazon Aurora MySQL-Compatible documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMySQL.html)
- [Amazon RDS security](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.html)
- [AWS Site-to-Site VPN](https://docs.aws.amazon.com/vpn/latest/s2svpn/VPC_VPN.html)
- [AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/Welcome.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Amazon CloudWatch monitoring for Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html)

Tính năng và engine pair được hỗ trợ có thể thay đổi theo phiên bản công cụ, engine và Region. Luôn kiểm tra tài liệu tương ứng với môi trường thực tế, chạy assessment trên schema đại diện và xác nhận kết quả bằng kiểm thử độc lập trước khi cutover.

