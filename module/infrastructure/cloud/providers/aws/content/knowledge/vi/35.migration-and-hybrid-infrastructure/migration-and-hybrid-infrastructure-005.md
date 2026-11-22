# AWS DMS, full load và change data capture

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, di chuyển database thường phải đáp ứng hai yêu cầu đồng thời: đưa dữ liệu lịch sử sang hệ thống đích và giữ cho dữ liệu mới phát sinh tiếp tục được cập nhật trong thời gian chuẩn bị cutover. AWS Database Migration Service (AWS DMS) hỗ trợ hai cơ chế chính để giải quyết bài toán này: **Full load** đọc và tải dữ liệu hiện có; **Change Data Capture (CDC)** đọc thay đổi từ transaction log của database nguồn rồi áp dụng lên đích.

Kết hợp Full load với CDC giúp tổ chức chuyển đổi database mà không cần dừng ghi trong toàn bộ thời gian sao chép dữ liệu. DMS tải từng bảng, đồng thời ghi nhận thay đổi phát sinh ở nguồn. Sau khi tải bảng, DMS áp dụng các thay đổi đã cache rồi tiếp tục replication liên tục. Đến thời điểm cutover, đội vận hành kiểm tra độ trễ, dừng hoặc hạn chế ghi ở nguồn, chờ thay đổi cuối cùng được áp dụng và chuyển ứng dụng sang database đích.

Sau bài học, người học có thể:

- Phân biệt Full load, CDC-only và Full load + CDC.
- Giải thích cách DMS capture transaction log, cache changes và apply thay đổi lên target.
- Chuẩn bị source endpoint, target endpoint, replication instance hoặc DMS Serverless.
- Xác định yêu cầu CDC theo từng engine như MySQL, PostgreSQL, Oracle và SQL Server.
- Cấu hình table mappings, selection rules, filters, transformations và LOB settings.
- Chọn TargetTablePrepMode, parallel load và task settings phù hợp.
- Bật data validation và phân tích sai lệch giữa source và target.
- Theo dõi FullLoadProgress, CDCLatencySource, CDCLatencyTarget và CloudWatch logs.
- Lập kế hoạch cutover, rollback và kiểm thử sau migration.
- Xử lý các lỗi phổ biến liên quan đến transaction log, primary key, network, KMS, permissions và replication capacity.

## 1. AWS DMS giải quyết bài toán nào?

AWS DMS là dịch vụ di chuyển và replication dữ liệu giữa các database hoặc data store được hỗ trợ. Nguồn có thể là database on-premises, database tự quản trên EC2, database AWS hoặc một số nền tảng database bên ngoài. Đích có thể là Amazon RDS, Aurora, database tự quản, S3, Redshift, DynamoDB, Kinesis, OpenSearch và các target được hỗ trợ khác.

Một migration database thường có các giai đoạn:

1. Chuẩn bị schema và môi trường đích.
2. Kết nối an toàn tới source và target.
3. Tải dữ liệu hiện có.
4. Bắt và áp dụng các thay đổi phát sinh trong lúc tải.
5. Xác minh dữ liệu và hiệu năng.
6. Chuyển ứng dụng sang target.
7. Theo dõi sau cutover và kết thúc migration.

DMS tập trung vào di chuyển dữ liệu và replication. Nó không tự động chuyển đổi mọi schema, stored procedure, trigger, view, function, job, quyền database hoặc logic ứng dụng. Với migration khác engine, cần dùng AWS DMS Schema Conversion hoặc công cụ chuyển đổi schema phù hợp để phân tích và chuyển đổi các đối tượng database trước khi chạy task dữ liệu.

Ví dụ, doanh nghiệp chuyển MySQL on-premises sang Amazon Aurora PostgreSQL. DMS có thể tải row data và replicate các thay đổi được hỗ trợ, nhưng cú pháp SQL, kiểu dữ liệu, stored procedure, trigger và các tính năng đặc thù của MySQL cần được chuyển đổi và kiểm thử riêng.

## 2. Các thành phần của AWS DMS

Một kiến trúc DMS dùng replication instance thường gồm:

- **Source endpoint:** thông tin kết nối và cấu hình đọc database nguồn.
- **Target endpoint:** thông tin kết nối và cấu hình ghi database đích.
- **Replication instance:** compute chạy replication engine, quản lý cache, đọc log và apply thay đổi.
- **Replication subnet group:** nhóm subnet nơi replication instance được triển khai.
- **Replication task:** định nghĩa migration type, table mappings, task settings và trạng thái replication.
- **CloudWatch:** lưu log và metrics phục vụ giám sát.

Sơ đồ:

~~~mermaid
flowchart LR
    S[Source database] -->|Full load + transaction logs| D[AWS DMS replication]
    D -->|Full load rows and CDC events| T[Target database]
    D --> C[Amazon CloudWatch logs and metrics]
    D --> E[Endpoints, task settings and table mappings]
    V[IAM, KMS, Secrets Manager and VPC] --> D
~~~

DMS replication instance nằm trong một VPC. Security group, route table, subnet, NACL, DNS và firewall của source/target phải cho phép kết nối từ replication instance. Nếu source ở on-premises, có thể dùng Site-to-Site VPN, Direct Connect hoặc kết nối mạng được kiểm soát khác.

AWS DMS có hai cách cung cấp replication compute:

| Lựa chọn | Đặc điểm | Khi cân nhắc |
|---|---|---|
| Provisioned replication instance | Người vận hành chọn instance class, storage và Multi-AZ | Workload ổn định, cần kiểm soát sizing và cấu hình |
| AWS DMS Serverless | DMS tự cấp phát và điều chỉnh capacity trong phạm vi cấu hình | Workload biến động hoặc muốn giảm quản trị replication compute |

Serverless không loại bỏ việc chuẩn bị endpoint, network, permissions, task configuration và kiểm thử hiệu năng. Hãy xác nhận migration path và tính năng cần dùng được hỗ trợ bởi loại replication đang chọn.

### 2.1. Replication instance và Multi-AZ

Replication instance dùng CPU, memory và storage để chạy task. Full load tiêu thụ tài nguyên đọc nguồn và ghi đích; CDC tiêu thụ tài nguyên đọc transaction log, buffer thay đổi và apply lên target. Một instance quá nhỏ có thể gây latency, dùng swap hoặc ghi cached changes xuống disk.

Multi-AZ deployment duy trì standby replication instance ở Availability Zone khác để hỗ trợ failover của replication compute. Nó tăng khả năng sẵn sàng của DMS replication instance, nhưng không làm database nguồn hoặc đích trở thành Multi-AZ, cũng không thay thế backup database. Hãy đánh giá chi phí và hiệu năng overhead khi bật Multi-AZ.

## 3. Phân biệt ba migration type

DMS có ba cách chạy task phổ biến:

| Migration type | Hoạt động | Trường hợp sử dụng |
|---|---|---|
| Migrate existing data (Full load) | Tải dữ liệu hiện có sang target rồi dừng | Migration có cửa sổ downtime hoặc dữ liệu tĩnh |
| Replicate data changes only (CDC) | Đọc transaction log và áp dụng thay đổi, không tải baseline | Target đã có dữ liệu tương ứng và có checkpoint đồng bộ |
| Migrate existing data and replicate ongoing changes (Full load + CDC) | Tải baseline, áp dụng cached changes rồi tiếp tục CDC | Migration cần giảm downtime và giữ target gần đồng bộ |

Full load-only không theo dõi thay đổi liên tục sau khi tải xong. Nếu source tiếp tục nhận ghi, target có thể nhanh chóng lệch dữ liệu. CDC-only giả định baseline ở target đã được tạo và tương ứng với điểm bắt đầu CDC; nếu không, kết quả có thể thiếu hoặc lặp dữ liệu.

Full load + CDC là lựa chọn phổ biến cho migration có cutover ngắn. Tuy nhiên, task không tự bảo đảm ứng dụng có thể chuyển ngay khi full load hoàn tất. Cần chờ cached changes được apply, kiểm tra CDC latency, validation và thực hiện quy trình cutover.

## 4. Full load hoạt động như thế nào?

Full load là quá trình đọc dữ liệu hiện có từ source và ghi vào target. DMS xác định các bảng theo table mappings, sau đó tải các bảng hoặc phân đoạn bảng theo cấu hình parallel load.

Một task có thể tải nhiều bảng đồng thời. Số bảng chạy song song và số thread trong mỗi bảng ảnh hưởng trực tiếp tới CPU, memory, network, I/O và tải database. Tăng parallelism có thể tăng throughput nhưng cũng có thể làm source quá tải, target throttling hoặc replication instance thiếu memory.

Các thiết lập thường gặp:

| Setting | Ý nghĩa |
|---|---|
| MaxFullLoadSubTasks | Số bảng hoặc table segment được tải đồng thời |
| ParallelLoadThreads | Số thread dùng để tải dữ liệu song song |
| CommitRate | Số record tối đa được chuyển trong một lần commit |
| TransactionConsistencyTimeout | Thời gian chờ transaction đang mở trước khi bắt đầu full load trong task có CDC |
| CreatePkAfterFullLoad | Tạo primary key sau khi full load hoàn tất nếu target prep và engine path hỗ trợ |

MaxFullLoadSubTasks và ParallelLoadThreads có tác động nhân lên tổng mức song song. Tăng cả hai mà không đo memory/CPU có thể làm replication instance hết tài nguyên. Bắt đầu với cấu hình thận trọng, chạy thử trên dữ liệu đại diện và tăng dần.

### 4.1. TargetTablePrepMode

TargetTablePrepMode xác định DMS xử lý bảng đích như thế nào trước khi full load:

| Mode | Hành vi | Rủi ro/cách dùng |
|---|---|---|
| DO_NOTHING | Không xóa hoặc truncate dữ liệu/schema đích | Dùng khi target đã được chuẩn bị; cần bảo đảm không có dữ liệu cũ gây trùng |
| DROP_AND_CREATE | Xóa bảng đích rồi tạo lại | Có thể làm mất index, constraint hoặc cấu trúc được tạo thủ công |
| TRUNCATE_BEFORE_LOAD | Xóa dữ liệu trong bảng nhưng giữ metadata | Phù hợp khi muốn giữ cấu trúc bảng nhưng nạp lại toàn bộ row |

Không chọn DROP_AND_CREATE trên target production nếu chưa kiểm tra quyền, schema, index, constraint, trigger và dữ liệu hiện có. Nếu dùng DO_NOTHING, cần xác nhận target trống hoặc có trạng thái baseline chính xác.

### 4.2. Dữ liệu LOB

Large Object như BLOB, CLOB hoặc dữ liệu nhị phân lớn cần cấu hình riêng. DMS hỗ trợ các cách xử lý như:

- **Limited LOB mode:** tải LOB trong giới hạn kích thước cấu hình; giá trị vượt giới hạn có thể bị truncate.
- **Full LOB mode:** tải toàn bộ LOB theo chunk; có thể chậm hơn và tiêu thụ nhiều tài nguyên.
- **Inline LOB mode:** với các trường hợp và phiên bản được hỗ trợ, tải LOB nhỏ cùng row data và xử lý LOB lớn theo cơ chế khác.

Hãy kiểm tra kích thước LOB thực tế, yêu cầu không mất dữ liệu và giới hạn của source/target. Nếu chọn limited LOB mode mà không đo kích thước tối đa, dữ liệu có thể bị cắt mà task vẫn tiếp tục. LOB replication thường cần primary key hoặc unique key để định vị row chính xác.

## 5. CDC đọc thay đổi từ transaction log

CDC không liên tục chạy câu SELECT toàn bảng để tìm row mới. DMS đọc transaction log hoặc change stream của database nguồn, diễn giải các thay đổi đã commit rồi áp dụng lên target.

Tùy engine, nguồn log khác nhau:

| Source engine | Cơ chế CDC thường dùng | Chuẩn bị quan trọng |
|---|---|---|
| MySQL/MariaDB/Aurora MySQL | Binary log (binlog) theo row-based logging | Bật automatic backups/binlog retention phù hợp; cấu hình binlog_format và quyền đọc |
| PostgreSQL/Aurora PostgreSQL | Logical replication slot và output plugin được hỗ trợ | Bật logical replication, quyền replication và SELECT; quản lý WAL/slot |
| Oracle | Redo log qua LogMiner hoặc AWS DMS Binary Reader | ARCHIVELOG, supplemental logging, quyền đọc redo/archived logs |
| SQL Server | MS-Replication hoặc MS-CDC tùy cấu hình | Bật CDC/replication và retention log phù hợp |
| Db2 và engine khác | Cơ chế transaction log riêng theo endpoint | Đối chiếu hướng dẫn engine-specific |

DMS cần log còn tồn tại cho đến khi task đọc được. Nếu source xóa hoặc tái sử dụng log trước khi DMS đọc, task có thể không tiếp tục được từ checkpoint cũ. Với RDS sources, AWS khuyến nghị bật backups và giữ change logs đủ lâu; 24 giờ thường là điểm bắt đầu tham khảo, nhưng workload có thể cần lâu hơn nếu task gián đoạn hoặc backlog lớn.

### 5.1. MySQL và MariaDB

Với MySQL-compatible source, DMS đọc row-based binary logs. Kiểm tra binlog format, retention và quyền endpoint user. Trên Amazon RDS for MySQL/MariaDB, automatic backups cần được bật để có binary logging; với Aurora MySQL, cấu hình binlog_format trong parameter group theo yêu cầu của engine.

Ví dụ kiểm tra cấu hình MySQL:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW BINARY LOGS;
~~~

DMS CDC thường cần row-based binlog. Đừng xóa binary logs thủ công trong khi task đang phụ thuộc vào chúng. Hãy theo dõi log retention, replication lag và dung lượng lưu log.

### 5.2. PostgreSQL

DMS sử dụng logical replication slot để đọc thay đổi. Với self-managed PostgreSQL, cần cấu hình logical replication và quyền phù hợp; tài khoản DMS cần quyền đọc các bảng được migrate và quyền replication theo hướng dẫn phiên bản. Với RDS PostgreSQL/Aurora PostgreSQL, endpoint user thường cần role rds_replication và quyền SELECT phù hợp; không mặc định cấp quyền superuser cho tài khoản DMS trên dịch vụ managed.

Logical replication slot giữ WAL cho đến khi consumer đọc. Nếu DMS task ngừng lâu, slot có thể giữ lại lượng WAL lớn và làm storage tăng. Hãy giám sát slot lag, retained WAL và dung lượng database; có runbook xử lý task lỗi để tránh hết storage.

### 5.3. Oracle

DMS có thể dùng Oracle LogMiner hoặc AWS DMS Binary Reader để đọc redo logs. CDC cần ARCHIVELOG, supplemental logging và quyền truy cập phù hợp. Lựa chọn LogMiner/Binary Reader ảnh hưởng tới cách cấp quyền, cấu hình ASM và truy cập archive logs.

Với Oracle tự quản, cần xác minh archive log retention đủ dài và cấu hình supplemental logging theo tài liệu AWS. Không xóa archive logs mà DMS còn cần. Chạy premigration assessment để kiểm tra các điều kiện như ARCHIVELOG, retention và quyền truy cập.

### 5.4. SQL Server

Tùy phiên bản và cấu hình, DMS sử dụng MS-Replication hoặc MS-CDC để lấy thay đổi từ transaction log. Kiểm tra phiên bản/edition có hỗ trợ CDC theo migration path, cấu hình database/table, quyền truy cập và log retention. Một số edition có thể hỗ trợ full load nhưng không hỗ trợ ongoing CDC; không suy luận rằng một source chạy được full load thì chắc chắn chạy được CDC.

## 6. Full load + CDC: cached changes và luồng xử lý

Khi task dùng Full load + CDC, DMS bắt đầu capture thay đổi từ source log trong khi tải dữ liệu hiện có. Các thay đổi phát sinh được giữ trong memory hoặc disk cache. Sau khi một bảng full load xong, DMS áp dụng cached changes cho bảng đó. Khi các cached changes còn tồn được apply, task chuyển sang ongoing CDC.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Start task] --> B[Initialize CDC capture point]
    B --> C[Read source transaction logs]
    C --> D[Cache changes in memory or disk]
    B --> E[Full load tables]
    E --> F[Table full load completed]
    D --> G[Apply cached changes to target]
    F --> G
    G --> H{Cached changes applied?}
    H -- No --> G
    H -- Yes --> I[Ongoing CDC]
    I --> J[Capture and apply new committed changes]
~~~

Ba giai đoạn cần phân biệt:

1. **Full load:** tải baseline của từng bảng.
2. **Cached changes apply:** áp dụng các thay đổi phát sinh trong khi full load đang diễn ra.
3. **Ongoing CDC:** tiếp tục đọc log và apply thay đổi mới.

Cached changes là phần rất quan trọng của full load + CDC. Nếu source có transaction volume cao trong lúc full load kéo dài, backlog có thể lớn. Khi full load kết thúc, DMS cần thời gian để apply backlog; latency có thể tăng trước khi ổn định.

Với transaction dài, DMS có thể phải đợi commit mới nhìn thấy thay đổi theo cơ chế log. Task có thể thể hiện source latency tăng trong khi transaction chưa commit. Hãy chọn cửa sổ full load phù hợp, giảm workload không cần thiết và đánh giá TransactionConsistencyTimeout theo engine.

Full load + CDC không đồng nghĩa tất cả bảng được snapshot ở cùng một thời điểm toàn database. DMS tải các bảng theo tiến trình riêng và capture log song song; nếu ứng dụng có ràng buộc nhất quán xuyên nhiều bảng, cần đánh giá transaction consistency, thời điểm cutover và validation thay vì giả định mọi bảng đã đồng bộ tại một instant chung.

## 7. Chuẩn bị schema và target database

Trước khi tạo task, hãy chuẩn bị target:

- Tạo database/schema và user DMS.
- Chuyển đổi kiểu dữ liệu và schema nếu source/target khác engine.
- Kiểm tra độ dài cột, precision, scale, timezone, collation và encoding.
- Xác định primary key hoặc unique key.
- Quyết định index/constraint nào tạo trước và sau full load.
- Xử lý LOB và kiểu dữ liệu đặc thù.
- Kiểm tra target capacity, connection limits và storage.
- Xác định target table prep mode.

DMS có thể tạo một số bảng đích theo metadata, nhưng không thay thế công cụ schema conversion và không tự di chuyển mọi database object. Index, foreign key, trigger, stored procedure, view, sequence, user, role, job và quyền cần kế hoạch riêng tùy engine và target.

Trong full load, tạo index/constraint quá sớm có thể làm insert chậm. Tạo index sau full load có thể tăng tốc độ tải nhưng phải hoàn thành trước khi ứng dụng sử dụng target. Với CDC, primary key hoặc unique key giúp DMS định vị row cho UPDATE/DELETE; bảng không có key có thể có giới hạn hiệu năng hoặc khả năng apply. Hãy đánh giá riêng các bảng thiếu key.

## 8. Source endpoint, target endpoint và kết nối mạng

Endpoint định nghĩa thông tin kết nối database, engine, hostname, port, database name, credentials và các extra connection attributes.

Một checklist endpoint:

| Thành phần | Kiểm tra |
|---|---|
| Engine/type | Đúng loại database và phiên bản được hỗ trợ |
| Server name/port | DNS phân giải đúng và port mở |
| Credentials | User DMS có quyền tối thiểu cần thiết |
| SSL/TLS | Certificate và encryption setting phù hợp |
| Extra connection attributes | Các tham số CDC/engine-specific được khai báo đúng |
| Secrets Manager | Secret và IAM role có quyền đọc secret |
| Network | Route, security group, NACL, firewall và DNS cho phép kết nối |

Replication instance và endpoint phải có network path hai chiều phù hợp cho việc thiết lập session. Security group của source/target cần cho phép inbound từ security group hoặc địa chỉ của replication instance. Không mở database port ra Internet nếu có thể dùng private routing.

Với database on-premises, kiểm tra VPN/Direct Connect, routing giữa VPC và datacenter, firewall, DNS và MTU. Với database trong VPC khác, có thể dùng VPC peering hoặc Transit Gateway theo kiến trúc mạng.

Nếu replication instance nằm trong private subnet và DMS kết nối tới các AWS services như S3, DynamoDB, Kinesis, Redshift, OpenSearch hoặc Secrets Manager, có thể cần VPC endpoints tương ứng. Với AWS DMS từ phiên bản 3.4.7 trong private network, các VPC endpoint này là điều kiện cần cho những dịch vụ được nêu. Kiểm tra endpoint policy, route và DNS trước khi chạy task.

## 9. IAM, KMS và bảo vệ thông tin kết nối

DMS cần quyền khác nhau cho replication instance, endpoint, log và dữ liệu được mã hóa.

Các nhóm quyền cần xem xét:

- IAM service role cho DMS truy cập tài nguyên cần thiết.
- Quyền quản lý VPC resources và CloudWatch Logs.
- Quyền đọc secret trong Secrets Manager nếu endpoint dùng secret.
- KMS permissions để giải mã secret hoặc truy cập dữ liệu mã hóa theo cấu hình.
- Quyền database của endpoint user trên source và target.
- Quyền truy cập S3/Kinesis/Redshift hoặc target service nếu migration tới các dịch vụ đó.

Không dùng tài khoản database admin nếu không cần. Tạo endpoint user riêng, cấp SELECT/replication privileges ở source và quyền tạo/ghi dữ liệu cần thiết ở target. Khi migration kết thúc, thu hồi hoặc giới hạn quyền không còn cần.

Credentials không nên ghi trong file task settings hoặc log. Dùng Secrets Manager, IAM role và TLS khi endpoint hỗ trợ. Nếu dùng KMS customer managed key, xác nhận key policy cho phép principal DMS hoặc role liên quan thực hiện các thao tác cần thiết.

## 10. Table mappings: chọn bảng và biến đổi dữ liệu

Table mappings xác định schema, table, view và filter nào được migration task xử lý. Có ba nhóm rule thường gặp:

- **Selection rules:** include/exclude schema, table, view hoặc collection.
- **Transformation rules:** đổi tên schema/table/column, thêm hoặc bỏ column, đổi kiểu dữ liệu trong phạm vi được hỗ trợ.
- **Table settings rules:** cấu hình riêng cho một số bảng, ví dụ LOB handling.

Ví dụ chỉ chọn tất cả bảng trong schema sales:

~~~json
{
  "rules": [
    {
      "rule-type": "selection",
      "rule-id": "1",
      "rule-name": "include-sales-tables",
      "object-locator": {
        "schema-name": "sales",
        "table-name": "%"
      },
      "rule-action": "include"
    }
  ]
}
~~~

Có thể thêm exclude rule cho bảng staging hoặc audit không cần chuyển. Rule selection có thể dùng wildcard %, nhưng tên schema/table và cách so khớp có thể phân biệt hoa thường tùy source engine. Hãy test table mapping trên một tập bảng nhỏ trước.

Transformation có thể đổi tên schema/table, thêm prefix, bỏ cột hoặc thay đổi kiểu dữ liệu trong các trường hợp hỗ trợ. Transformation làm thay đổi target schema cần được kiểm tra kỹ; một số thay đổi yêu cầu restart task để được áp dụng đúng. Không dùng DMS transformation như một công cụ chuyển đổi tùy ý cho mọi logic nghiệp vụ.

Views có giới hạn: DMS chỉ tải views trong full load; không replicate thay đổi liên tục của view như bảng CDC thông thường. Nếu cần view, hãy tạo và kiểm thử riêng sau khi base tables đã được migrate.

## 11. Tạo task Full load + CDC

Trước khi tạo task, cần có source endpoint, target endpoint và replication instance hoặc DMS Serverless replication configuration phù hợp. Chạy endpoint connection test để xác nhận network, credentials và permissions.

Task settings và table mappings có thể lưu thành JSON để review và version control. Ví dụ task settings rút gọn:

~~~json
{
  "TargetMetadata": {
    "SupportLobs": true,
    "LimitedSizeLobMode": true,
    "LobMaxSize": 64
  },
  "FullLoadSettings": {
    "TargetTablePrepMode": "DO_NOTHING",
    "CreatePkAfterFullLoad": true,
    "MaxFullLoadSubTasks": 8,
    "TransactionConsistencyTimeout": 600,
    "CommitRate": 10000
  },
  "Logging": {
    "EnableLogging": true
  },
  "ValidationSettings": {
    "EnableValidation": true,
    "ThreadCount": 5,
    "ValidationMode": "ROW_LEVEL"
  }
}
~~~

Đây là ví dụ minh họa cần điều chỉnh theo source/target engine, DMS version và schema. LimitedSizeLobMode có thể truncate LOB vượt LobMaxSize; không dùng cấu hình này nếu yêu cầu giữ nguyên mọi LOB mà chưa đánh giá kích thước. CreatePkAfterFullLoad chỉ dùng khi phù hợp target và task.

Tạo task bằng AWS CLI:

~~~bash
aws dms create-replication-task \
  --replication-task-identifier sales-full-load-cdc \
  --source-endpoint-arn arn:aws:dms:ap-southeast-1:111122223333:endpoint:SOURCE \
  --target-endpoint-arn arn:aws:dms:ap-southeast-1:111122223333:endpoint:TARGET \
  --replication-instance-arn arn:aws:dms:ap-southeast-1:111122223333:rep:REPLICATION \
  --migration-type full-load-and-cdc \
  --table-mappings file://table-mappings.json \
  --replication-task-settings file://task-settings.json \
  --region ap-southeast-1
~~~

ARN và task identifier trong ví dụ là placeholder. Khi task đã tạo, khởi chạy:

~~~bash
aws dms start-replication-task \
  --replication-task-arn arn:aws:dms:ap-southeast-1:111122223333:task:TASK \
  --start-replication-task-type start-replication \
  --region ap-southeast-1
~~~

Các kiểu start thường gặp gồm start-replication, resume-processing và reload-target. Chọn đúng hành vi: resume tiếp tục từ checkpoint; reload-target tải lại bảng theo task settings và có thể ghi đè/truncate target tùy TargetTablePrepMode. Không dùng reload-target như một thao tác retry vô hại trên target đã có dữ liệu production.

## 12. Data validation: kiểm tra source và target

DMS data validation so sánh dữ liệu ở source và target để tìm mismatch. Khi bật validation cho task, DMS bắt đầu kiểm tra bảng sau khi full load của bảng đó hoàn tất; với CDC task, validation tiếp tục kiểm tra thay đổi đang replicate.

Validation có thể tạo tải đọc bổ sung trên source và target. Với bảng lớn, LOB hoặc query phức tạp, hãy đo tác động trước khi bật trên toàn bộ database production.

Những điểm cần kiểm tra:

- Validation cần primary key hoặc unique key phù hợp để đối chiếu row.
- Một số data type, collation, LOB và engine combinations có giới hạn.
- Nếu source/target đang bị ứng dụng khác ghi trong lúc validation, kết quả có thể báo mismatch.
- Validation chỉ xác minh các bảng/column trong phạm vi task và những gì DMS hỗ trợ; không chứng minh mọi database object hay business rule đã chuyển đúng.
- Có thể dùng validation-only task để so sánh dữ liệu mà không thực hiện migration, với các điều kiện cấu hình riêng.

Ví dụ bật validation:

~~~json
{
  "ValidationSettings": {
    "EnableValidation": true,
    "ValidationMode": "ROW_LEVEL",
    "ThreadCount": 5,
    "PartitionSize": 10000,
    "FailureMaxCount": 10000,
    "TableFailureMaxCount": 1000,
    "SkipLobColumns": false
  }
}
~~~

DMS engine 3.5.4 trở lên có thể tự chọn GROUP_LEVEL cho một số migration path được hỗ trợ để cải thiện hiệu năng; các path khác dùng ROW_LEVEL theo mặc định. Hãy xem tài liệu validation theo đúng engine version và migration path.

Khi có mismatch, kiểm tra bảng validation failures, log và metrics; đối chiếu source/target row count, primary key, collation, data type, LOB, concurrent writes và CDC lag. Không kết luận migration thành công chỉ dựa trên trạng thái task là Load complete.

## 13. Cutover: chuyển ứng dụng sang database đích

Full load hoàn tất chưa phải thời điểm tự động chuyển traffic. Với full load + CDC, target cần bắt kịp các thay đổi từ source và được xác minh.

Một runbook cutover mẫu:

1. Xác nhận full load đã hoàn tất cho mọi bảng cần migrate.
2. Xác nhận task đang ở trạng thái ongoing CDC và không có table error chưa xử lý.
3. Kiểm tra CDCLatencySource và CDCLatencyTarget ổn định ở ngưỡng chấp nhận.
4. Chạy data validation và đối chiếu business-critical tables.
5. Thông báo maintenance window và đóng hoặc hạn chế thay đổi schema.
6. Đưa ứng dụng vào read-only hoặc dừng writer ở source.
7. Chờ transaction đang mở hoàn tất hoặc xử lý theo kế hoạch.
8. Đợi DMS capture và apply thay đổi cuối cùng; xác nhận latency về gần 0 theo tiêu chí đã định.
9. Chạy final reconciliation: row counts, tổng tiền, trạng thái đơn hàng và các business invariant.
10. Chặn ghi vào source để tránh split-brain.
11. Chuyển connection string, secret hoặc endpoint ứng dụng sang target.
12. Khởi động writer tại target và chạy smoke test.
13. Theo dõi lỗi, latency, connection pool, lock và business transactions.
14. Giữ source ở read-only trong thời gian rollback window theo chính sách.

Không cho cả source và target cùng nhận ghi trong quá trình cutover nếu chưa có kiến trúc multi-writer và conflict resolution riêng. DMS CDC một chiều không phải cơ chế đồng bộ hai chiều để hợp nhất hai database cùng ghi.

## 14. Rollback và giới hạn của CDC một chiều

Nếu ứng dụng tại target gặp lỗi sau cutover, rollback không đơn giản là đổi connection string về source. Sau khi target nhận ghi mới, source không có các thay đổi đó.

Trước migration, phải chọn chiến lược rollback:

- Giữ source read-only và chỉ rollback trước khi target nhận giao dịch mới.
- Nếu target đã nhận ghi, cần reverse migration/CDC theo hướng ngược lại hoặc quy trình reconciliation có kiểm soát.
- Với rollback có dữ liệu mới, dừng writer tại target, capture điểm cuối, đồng bộ dữ liệu cần thiết về source và kiểm tra xung đột trước khi mở source.
- Nếu không thể đồng bộ ngược an toàn, phải có quyết định nghiệp vụ về việc giữ target làm authoritative hoặc xử lý giao dịch phát sinh.

DMS không tự biến task một chiều thành bidirectional replication. Một task CDC có source và target cố định; muốn replicate ngược phải thiết kế task và permissions theo hướng mới, xác minh engine support, schema và dữ liệu. Hãy thử rollback trong rehearsal, không đợi sự cố production.

## 15. Theo dõi task và CloudWatch metrics

Theo dõi DMS ở ba lớp: replication instance, task và table statistics.

| Metric/trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| FullLoadProgressPercent | Tiến độ full load tổng thể | Theo dõi tải baseline |
| FullLoadThroughputRowsSource | Tốc độ đọc row từ source | Phát hiện source đọc chậm |
| FullLoadThroughputRowsTarget | Tốc độ ghi row tới target | Phát hiện target apply chậm |
| FullLoadThroughputBandwidthSource/Target | Băng thông full load | Đánh giá network và throughput |
| CDCLatencySource | Độ trễ capture từ source log tới replication instance | Cao kéo dài: kiểm tra source/log/replication compute |
| CDCLatencyTarget | Độ trễ apply thay đổi tới target | Cao hơn source nhiều: kiểm tra target/index/locks/network |
| CDCIncomingChanges | Thay đổi đang đến từ source | So sánh tốc độ phát sinh và apply |
| CDCThroughputRowsSource/Target | Tốc độ row CDC vào/ra | Đánh giá backlog |
| CPUUtilization | CPU replication instance | Phát hiện compute bottleneck |
| FreeableMemory và SwapUsage | Áp lực memory/swap | Xác định instance thiếu memory |
| DiskQueueDepth/FreeStorageSpace | Áp lực I/O và dung lượng | Theo dõi cache và log trên replication instance |

CDCLatencySource và CDCLatencyTarget phải được đọc cùng nhau. Nếu cả hai cao và gần nhau, thường cần điều tra capture/source side trước. Nếu CDCLatencySource thấp nhưng CDCLatencyTarget cao, tập trung vào target, index/primary key, lock, database capacity, network và apply settings.

Latency có thể tăng trong batch workload hoặc transaction dài. Một khoảng spike không nhất thiết là lỗi dịch vụ. Điều quan trọng là xu hướng kéo dài, backlog tăng và không giảm sau khi tải nguồn/đích trở lại bình thường.

CloudWatch Logs cung cấp task logs. Bật logging đủ để chẩn đoán; chỉ bật debug logging khi cần vì log chi tiết có thể làm tăng storage và ảnh hưởng replication instance. Control tables của DMS có thể ghi task status, table statistics và apply exceptions trên target database đối với Full load + CDC hoặc CDC-only task.

## 16. Tuning hiệu năng Full load và CDC

Hiệu năng migration phụ thuộc source, target, replication compute, network, schema, index, LOB và transaction workload. Tuning cần thay đổi từng nhóm tham số rồi đo lại.

### Full load

- Chọn replication instance đủ CPU, memory và storage.
- Điều chỉnh MaxFullLoadSubTasks và ParallelLoadThreads có kiểm soát.
- Tăng target capacity và connection limit nếu cần.
- Xem xét tạo secondary index sau full load nếu target prep và cutover cho phép.
- Chia workload theo schema hoặc nhóm bảng để giảm cạnh tranh.
- Xử lý LOB riêng vì LOB lớn làm giảm throughput.
- Chọn cửa sổ migration khi source ít tải.

### CDC

- Giữ transaction log đủ lâu.
- Đảm bảo source có đủ tài nguyên đọc log.
- Đảm bảo target có primary key/index phù hợp để update/delete.
- Theo dõi CDCLatencySource và CDCLatencyTarget.
- Tăng replication capacity nếu CPU/memory/disk là bottleneck.
- Tối ưu target indexes, transaction apply và batch apply theo engine support.
- Tránh transaction quá lớn hoặc DDL thay đổi bất ngờ trong migration.
- Kiểm tra network throughput và packet loss giữa DMS và endpoints.

Không tăng parallelism chỉ để đạt một con số throughput nếu source database bắt đầu ảnh hưởng workload production. Mục tiêu là migration ổn định, dữ liệu đúng và latency giảm về ngưỡng có thể cutover.

## 17. Premigration assessment và kiểm tra trước khi chạy

AWS DMS premigration assessment phân tích cấu hình task, source, target và metadata để cảnh báo các vấn đề có thể gây lỗi hoặc ảnh hưởng migration. Hãy chạy assessment trước full load và CDC, đọc từng finding và xử lý vấn đề quan trọng.

Checklist trước khi chạy:

- Source/target engine version và migration path được hỗ trợ.
- CDC prerequisites đã cấu hình, transaction log retention đủ dài.
- Các bảng có primary key/unique key hoặc có kế hoạch xử lý bảng thiếu key.
- Source endpoint và target endpoint test connection thành công.
- Replication instance hoặc Serverless capacity đáp ứng workload.
- VPC, route, security group, firewall và DNS đã kiểm thử.
- IAM role, database permissions, Secrets Manager và KMS hoạt động.
- Target schema và data types đã được chuyển đổi.
- LOB mode, table mappings và TargetTablePrepMode đã được review.
- Có backup/snapshot trước migration và runbook rollback.
- CloudWatch logs/metrics và cảnh báo đã cấu hình.
- Cutover owner, maintenance window và tiêu chí thành công được xác định.

Premigration assessment không thay thế proof-of-concept và rehearsal. Nó có thể phát hiện cấu hình thiếu nhưng không chứng minh target đủ capacity hoặc ứng dụng tương thích.

## 18. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Test endpoint thất bại | DNS, port, firewall, security group hoặc credentials | Kiểm tra route, SG/NACL, endpoint user và TLS |
| Full load không bắt đầu | Thiếu quyền đọc metadata/table hoặc task mapping sai | Xem task logs, table mapping và database grants |
| Full load chậm | Source I/O, target index/constraint, LOB hoặc replication instance thiếu tài nguyên | Đối chiếu throughput metrics và CPU/memory |
| Table bị suspended | Data error, truncation, schema mismatch hoặc apply exception | Xem table statistics và awsdms_apply_exceptions |
| CDC không bắt đầu sau full load | Log prerequisites sai, không có quyền đọc log hoặc cached changes chưa apply | Kiểm tra source log settings và task status |
| CDCLatencySource cao | DMS không đọc kịp log, source thiếu tài nguyên hoặc transaction dài | Kiểm tra source workload, log access, DMS CPU/memory |
| CDCLatencyTarget cao nhưng source thấp | Target chậm, thiếu key/index, lock hoặc network tới target | Kiểm tra target metrics, indexes, locks và apply throughput |
| PostgreSQL WAL tăng liên tục | Logical replication slot không được consume hoặc task dừng | Kiểm tra slot lag, task state và retained WAL |
| MySQL mất binlog cần thiết | Log retention ngắn hơn thời gian task gián đoạn | Kiểm tra binlog retention; tạo lại task từ điểm hợp lệ nếu log đã mất |
| Oracle CDC lỗi | ARCHIVELOG, supplemental logging hoặc quyền LogMiner/Binary Reader chưa đúng | Chạy assessment và kiểm tra source-specific prerequisites |
| SQL Server CDC lỗi | MS-Replication/MS-CDC hoặc log retention chưa cấu hình | Kiểm tra edition, database/table CDC và SQL Agent |
| Validation mismatch | Concurrent writes, collation/data type/LOB hoặc CDC lag | Chờ lag ổn định, kiểm tra validation failures và schema |
| Task thiếu disk | Cached changes, log hoặc debug logging chiếm storage | Tăng storage/capacity và giảm backlog; kiểm soát log level |
| Resume task thất bại | Transaction log position đã bị xóa khỏi source | Xác định checkpoint còn khả dụng; có thể cần reload/recreate task và đánh giá target impact |

Khi task dừng lâu, DMS có thể phải đọc backlog log từ checkpoint cũ. Nếu source đã xóa log đó, task không thể tiếp tục bình thường. Hãy kiểm tra log retention và checkpoint trước khi stop task dài ngày.

Không xóa task hoặc reload target để xử lý lỗi trước khi xác định tác động lên dữ liệu đích. Một số hành động có thể truncate/drop bảng hoặc làm mất checkpoint. Lưu task ARN, table statistics, checkpoint, CloudWatch logs và error message trước khi sửa.

## 19. Bài thực hành: chuyển MySQL on-premises sang Amazon Aurora

Một doanh nghiệp đang chạy MySQL on-premises và muốn chuyển sang Aurora MySQL tại ap-southeast-1. Ứng dụng phải tiếp tục nhận đơn hàng trong phần lớn thời gian migration. Kế hoạch dùng Full load + CDC, sau đó cutover trong maintenance window ngắn.

### Thiết kế

| Thành phần | Cấu hình minh họa |
|---|---|
| Source | MySQL on-premises |
| Target | Amazon Aurora MySQL |
| DMS compute | Replication instance trong private subnet |
| Network | Direct Connect hoặc Site-to-Site VPN |
| Migration type | Full load and CDC |
| Source CDC | Row-based binlog và retention phù hợp |
| Target prep | DO_NOTHING với schema đã chuẩn bị |
| Table mapping | Include schema sales, exclude bảng staging |
| Validation | Bật cho bảng quan trọng sau khi đánh giá tải |
| Monitoring | CloudWatch logs, CDCLatencySource/Target, table statistics |

### Các bước triển khai

1. Kiểm tra compatibility của MySQL source và Aurora target.
2. Chuyển đổi schema và tạo database/table tại Aurora.
3. Bật binlog row-based và cấu hình retention ở source.
4. Tạo DMS replication instance, subnet group, security group và network path.
5. Tạo source/target endpoint; kiểm tra connection.
6. Chạy premigration assessment và xử lý findings.
7. Tạo table mappings cho schema sales.
8. Tạo task Full load + CDC với validation và CloudWatch logging.
9. Theo dõi full load progress, table errors và cached changes.
10. Chờ task vào ongoing CDC; đo CDCLatencySource và CDCLatencyTarget.
11. So sánh dữ liệu và business totals ở source/target.
12. Mở maintenance window, dừng writer ở source.
13. Chờ CDC latency về ngưỡng cutover và hoàn tất final validation.
14. Chuyển ứng dụng sang Aurora endpoint và chạy smoke test.
15. Giữ source read-only trong rollback window; chỉ kết thúc migration sau khi owner chấp thuận.

### Tiêu chí thành công

- Tất cả bảng trong phạm vi đã full load.
- Không còn table error chưa được chấp nhận.
- CDC đang hoạt động và latency nằm trong ngưỡng được phê duyệt.
- Dữ liệu quan trọng đã validation/reconciliation.
- Ứng dụng đọc/ghi target thành công.
- Không có split-brain giữa source và target.
- Có backup và phương án rollback/reverse sync.
- CloudWatch dashboard và runbook được bàn giao.

## Kết luận

AWS DMS kết hợp Full load và CDC để chuyển dữ liệu hiện có rồi tiếp tục đồng bộ thay đổi phát sinh từ transaction log. Full load tạo baseline; cached changes đưa các bảng vừa tải bắt kịp source; ongoing CDC duy trì replication cho tới khi tổ chức sẵn sàng cutover.

Một migration an toàn cần chuẩn bị schema, endpoint, network, IAM, KMS và log retention theo từng database engine. Table mappings, LOB settings, target prep mode và parallelism phải được kiểm thử với dữ liệu thực tế. Data validation, CloudWatch metrics và premigration assessment giúp phát hiện sai lệch và bottleneck. Cutover chỉ nên diễn ra sau khi full load hoàn tất, CDC bắt kịp, dữ liệu được xác minh và writer ở source đã được kiểm soát.

DMS là một thành phần trong kế hoạch migration. Việc chuyển đổi schema, kiểm thử ứng dụng, quản lý downtime, rollback và quyết định thời điểm mở ghi ở target vẫn cần quy trình do đội vận hành và chủ sở hữu ứng dụng chịu trách nhiệm.

## Tài liệu tham khảo

- [AWS Database Migration Service — User Guide](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html)
- [Working with AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.html)
- [High-level view of AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.HighLevelView.html)
- [Creating tasks for ongoing replication using AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Task.CDC.html)
- [Full-load task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TaskSettings.FullLoad.html)
- [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html)
- [Data validation task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TaskSettings.DataValidation.html)
- [Monitoring AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Monitoring.html)
- [Troubleshooting latency issues in AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Troubleshooting_Latency.html)
- [Using a MySQL database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.MySQL.html)
- [Using a PostgreSQL database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.PostgreSQL.html)
- [Using an Oracle database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.Oracle.html)
- [Using a Microsoft SQL Server database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.SQLServer.html)
- [Setting up a network for a replication instance](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_ReplicationInstance.VPC.html)
- [AWS DMS components](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.Components.html)
- [Choosing an AWS DMS replication instance](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_ReplicationInstance.Types.html)
- [Using table mappings to specify task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.html)
- [Selection rules and actions](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Selections.html)
- [Transformation rules and actions](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Transformations.html)
- [AWS DMS Serverless](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Serverless.html)
- [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_SchemaConversion.html)
- [AWS DMS pricing](https://aws.amazon.com/dms/pricing/)

