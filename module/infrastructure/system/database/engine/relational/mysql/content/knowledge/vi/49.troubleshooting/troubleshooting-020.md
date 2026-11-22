# Đánh giá tác động trước khi KILL QUERY, KILL CONNECTION hoặc restart

Khi MySQL chậm, có truy vấn bị treo hoặc connection tăng bất thường, DBA thường cân nhắc dừng một câu lệnh, ngắt một session hoặc restart máy chủ. Mỗi thao tác có phạm vi ảnh hưởng khác nhau. Chọn nhầm session có thể làm mất giao dịch đang xử lý, kéo dài rollback, giải phóng lock chậm hoặc làm gián đoạn toàn bộ ứng dụng. Restart còn ảnh hưởng đến tất cả client, replica, job nền và dịch vụ phụ thuộc.

Bài học này xây dựng quy trình đánh giá tác động trước khi dùng **KILL QUERY**, **KILL CONNECTION** hoặc restart MySQL. Trọng tâm là xác định đúng đối tượng, hiểu transaction và lock đang được giữ, ước lượng phạm vi ảnh hưởng, chọn hành động ít tác động nhất và xác minh hệ thống sau can thiệp.

Trong phạm vi **DATABASE_MYSQL**, việc đánh giá dựa trên kiến thức thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời. Cần kết hợp đọc execution plan, tối ưu truy vấn, phân quyền, sao lưu và hiểu kiến trúc vận hành của cơ sở dữ liệu quan hệ.

## 1. Nguyên tắc trước khi can thiệp

Không thực hiện KILL hoặc restart chỉ vì một dòng trong process list có thời gian chạy lớn. Trước tiên phải trả lời:

1. Session nào đang gây ra vấn đề? Nó là blocker, victim, truy vấn đọc, truy vấn ghi hay tác vụ hệ thống?
2. Câu lệnh đang chạy ở database nào, do user/service nào khởi tạo và thuộc luồng nghiệp vụ nào?
3. Session có transaction đang mở không? Đã sửa bao nhiêu hàng, đang giữ lock nào và có thể cần rollback bao lâu?
4. Nếu dừng câu lệnh hoặc session, ứng dụng có retry không? Retry có thể tạo giao dịch trùng hoặc kết quả không xác định không?
5. Có ảnh hưởng đến replication, backup, migration, failover hoặc job vận hành không?
6. Có cách giảm tải, dừng job từ ứng dụng hoặc chờ transaction hoàn tất với tác động thấp hơn không?

Một quy trình can thiệp tốt có bốn bước:

~~~mermaid
flowchart TD
    A[Phát hiện sự cố] --> B[Thu thập trạng thái và xác định session]
    B --> C[Đánh giá transaction, lock và phạm vi ảnh hưởng]
    C --> D{Mức can thiệp cần thiết?}
    D -->|Câu lệnh riêng| E[KILL QUERY]
    D -->|Session gây tác động| F[KILL CONNECTION]
    D -->|Máy chủ/topology cần phục hồi| G[Restart theo runbook]
    E --> H[Theo dõi rollback, lock và ứng dụng]
    F --> H
    G --> I[Kiểm tra recovery, replication và client]
    H --> J[Xác minh và ghi nhận]
    I --> J
~~~

Thu thập bằng chứng trước khi can thiệp. Ghi timestamp, processlist ID, user, host, database, câu SQL, trạng thái transaction, lock wait và metric liên quan. Nếu sự cố cần xử lý ngay, vẫn nên lưu tối thiểu thông tin nhận diện và lý do hành động.

## 2. Xác định đúng session và câu lệnh

### 2.1. Xem process list

Lệnh cơ bản:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Dùng FULL để xem đầy đủ câu SQL trong cột Info, tránh phần nội dung bị cắt. Các cột cần chú ý:

| Cột | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Id | Processlist ID của connection | Đây có đúng session định can thiệp không? |
| User | Tài khoản MySQL | Thuộc ứng dụng, DBA, backup hay replication? |
| Host | Máy khách và cổng nguồn | Có thể liên hệ với instance/pod/job nào? |
| db | Database mặc định | Đang tác động schema nào? |
| Command | Loại lệnh, thường là Query hoặc Sleep | Đang chạy SQL hay đang idle? |
| Time | Thời gian ở trạng thái hiện tại, tính bằng giây | Query/idle đã kéo dài bao lâu? |
| State | Trạng thái chi tiết của thread | Đang chờ lock, gửi dữ liệu hay thực thi? |
| Info | Câu SQL hiện tại nếu có | Câu lệnh có tác động dữ liệu hoặc DDL không? |

Có thể lọc các session đang hoạt động:

~~~sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
WHERE COMMAND <> 'Sleep'
ORDER BY TIME DESC;
~~~

TIME không phải lúc nào cũng là tổng thời gian từ lúc connection được tạo. Với thread đang chạy query, nó thường biểu thị thời gian ở trạng thái hiện tại. Với session Sleep, đó là thời gian idle ở trạng thái đó. Cần đối chiếu với log ứng dụng và metric query để hiểu đầy đủ.

Không chọn target chỉ bằng TIME lớn nhất. Một session Sleep lâu có thể hoàn toàn bình thường; một transaction mở nhưng Sleep lại có thể giữ lock và gây ảnh hưởng đáng kể.

### 2.2. Phân biệt processlist ID và Performance Schema thread ID

KILL nhận **processlist ID**, không phải THREAD_ID nội bộ của Performance Schema. Có thể liên kết hai loại ID như sau:

~~~sql
SELECT
  THREAD_ID,
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Trước khi KILL, xác minh lại PROCESSLIST_ID, user, host và câu lệnh ngay tại thời điểm thao tác. Connection có thể đã kết thúc và processlist ID có thể được tái sử dụng về sau; không chạy lệnh từ một danh sách cũ mà không kiểm tra lại target.

### 2.3. Nhận diện loại công việc

Xác định session thuộc nhóm nào:

- Request API hoặc worker ứng dụng.
- Truy vấn báo cáo/BI hoặc truy vấn ad hoc.
- Migration, DDL, index build hoặc backfill.
- Backup/restore hoặc công cụ quản trị.
- Replication receiver/applier.
- Event scheduler, monitoring hoặc tài khoản DBA.
- Session quản trị đang điều tra sự cố.

Một câu SQL giống nhau có thể có tác động khác nhau tùy vị trí trong luồng nghiệp vụ. Ví dụ, một UPDATE có thể là job cập nhật dữ liệu có thể chạy lại, hoặc là bước ghi sổ thanh toán không được lặp.

## 3. Đánh giá transaction và lock trước khi KILL

### 3.1. Kiểm tra transaction InnoDB

Liệt kê transaction đang mở:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
  trx_mysql_thread_id AS processlist_id,
  trx_rows_locked,
  trx_rows_modified,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Các thông tin quan trọng:

- trx_started: thời điểm transaction bắt đầu.
- trx_state: trạng thái transaction.
- trx_mysql_thread_id: processlist ID tương ứng.
- trx_rows_locked: số hàng đang bị lock theo thông tin InnoDB.
- trx_rows_modified: số hàng đã được sửa trong transaction.
- trx_query: câu SQL hiện tại, có thể NULL nếu session đang idle giữa các câu lệnh.

trx_rows_modified giúp hình dung quy mô công việc cần rollback nhưng không phải phép đo chính xác thời gian rollback. Undo log, số lượng index, I/O, độ cạnh tranh và trạng thái storage đều ảnh hưởng thời gian thực tế.

Một transaction có thể đã sửa nhiều hàng rồi chuyển sang Sleep trong khi ứng dụng còn giữ transaction mở. Session đó không có query đang chạy nhưng vẫn có thể giữ row lock và làm các transaction khác chờ.

### 3.2. Tìm blocker và victim

Trong tình huống lock wait, cần phân biệt:

- **Waiting session (victim):** transaction đang chờ một lock.
- **Blocking session (blocker):** transaction đang giữ lock khiến session khác không thể tiếp tục.

Xem tổng quan lock wait qua sys schema:

~~~sql
SELECT
  wait_age,
  locked_table,
  locked_index,
  waiting_pid,
  waiting_query,
  blocking_pid,
  blocking_query,
  blocking_trx_age,
  blocking_trx_rows_locked,
  blocking_trx_rows_modified
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
~~~

Nếu sys schema không có hoặc view không khả dụng, có thể kiểm tra Performance Schema:

~~~sql
SELECT
  REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
  REQUESTING_THREAD_ID AS waiting_thread_id,
  BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
  BLOCKING_THREAD_ID AS blocking_thread_id
FROM performance_schema.data_lock_waits;
~~~

Kết hợp với performance_schema.data_locks, performance_schema.threads và information_schema.innodb_trx để tìm session, bảng, index và transaction tương ứng.

Không phải lúc nào cũng nên KILL victim. Dừng một query đang chờ thường chỉ làm lỗi request đó; blocker vẫn tồn tại và các session khác tiếp tục chờ. Ngược lại, KILL blocker có thể giải phóng nhiều session nhưng phải rollback transaction của blocker, gây I/O và thời gian chờ bổ sung. Chọn target dựa trên mục tiêu khôi phục và tác động nghiệp vụ.

### 3.3. Kiểm tra metadata lock

DDL như ALTER TABLE, RENAME TABLE hoặc DROP TABLE có thể chờ metadata lock từ transaction khác. Khi DDL đang chờ, các truy vấn mới cũng có thể bị ảnh hưởng bởi hàng đợi lock.

Xem metadata lock của một schema:

~~~sql
SELECT
  ml.OBJECT_TYPE,
  ml.OBJECT_SCHEMA,
  ml.OBJECT_NAME,
  ml.LOCK_TYPE,
  ml.LOCK_DURATION,
  ml.LOCK_STATUS,
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  t.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'appdb'
  AND ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS;
~~~

Kết quả cho biết lock đang chờ (PENDING) và lock đã được cấp (GRANTED). Đối chiếu các hàng cùng object để tìm transaction hoặc câu lệnh đang giữ lock. Nếu có nhiều đối tượng và nhiều session, cần kết hợp process list, transaction và log migration để dựng lại chuỗi chờ.

Trước khi KILL một DDL đang chờ, xem liệu chính DDL đó có đang tạo hàng đợi làm request mới bị kẹt không. Có thể dừng DDL đang chờ để giảm áp lực trước, sau đó xử lý transaction giữ metadata lock trong một cửa sổ được kiểm soát.

### 3.4. Lưu trạng thái InnoDB

Khi lock hoặc rollback khó hiểu, lưu thêm:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Phần TRANSACTIONS và thông tin deadlock có thể giúp xác định transaction, lock và hoạt động gần nhất. Đây là snapshot tại thời điểm truy vấn; nếu sự cố thay đổi nhanh, lưu nhiều mẫu có timestamp để so sánh.

## 4. Ước lượng phạm vi ảnh hưởng

Trước khi dừng một session, đánh giá ít nhất năm nhóm tác động.

### 4.1. Dữ liệu và transaction

- Query chỉ đọc hay có sửa dữ liệu?
- Transaction đang ở autocommit hay explicit transaction?
- Có bao nhiêu hàng đã sửa và đang giữ lock?
- Dừng query có làm transaction còn mở không?
- Kết quả commit đã được ứng dụng nhận chưa?
- Có thể xác minh hoặc chạy lại nghiệp vụ bằng idempotency key không?

Nếu client mất kết nối trong lúc COMMIT, kết quả có thể không xác định từ phía ứng dụng: server có thể đã commit nhưng phản hồi chưa tới client. Không retry lệnh ghi mù quáng.

### 4.2. Lock và ảnh hưởng dây chuyền

Một blocker có thể làm hàng chục hoặc hàng trăm transaction chờ. Dừng blocker có thể giảm hàng đợi, nhưng rollback của blocker có thể tiếp tục giữ tài nguyên trong một khoảng thời gian.

Đếm số session đang chờ và kiểm tra các bảng/record liên quan. Đánh giá cả lock row và metadata lock; không chỉ nhìn trạng thái Locked trên process list.

### 4.3. Tải và tài nguyên

- Query có đang dùng CPU hoặc I/O lớn không?
- Có tạo temporary table, sort hoặc scan toàn bảng không?
- Dừng query có giải phóng tài nguyên ngay hay phải đợi rollback?
- Việc restart có làm đồng thời nhiều client reconnect và tạo connection storm không?
- Storage còn đủ dung lượng cho rollback, crash recovery và binary log không?

Nếu vấn đề là query chậm do thiếu index, KILL có thể giảm tải tạm thời nhưng không sửa nguyên nhân. Lưu câu SQL và execution plan, sau đó kiểm tra index, cardinality, predicate và thống kê.

### 4.4. Ứng dụng và nghiệp vụ

Xác định owner của session bằng user/host, request ID, application name hoặc log. Đánh giá:

- API nào sẽ trả lỗi?
- Worker có tự retry không?
- Job batch có checkpoint để chạy tiếp không?
- Request ghi có idempotent không?
- Một transaction có cập nhật nhiều bảng hoặc gọi dịch vụ ngoài không?
- Hành động có thể làm mất tiến trình migration, backup hoặc tác vụ đối soát không?

### 4.5. Replication và tính sẵn sàng

Nếu target là primary:

- Replica có đang khỏe và bắt kịp không?
- Transaction đang dừng đã được ghi vào binary log chưa?
- KILL hoặc restart có làm replica lag tăng không?
- Có nguy cơ failover tự động trong lúc thao tác không?

Nếu target là replica:

- Session có phải replication applier/receiver không?
- Dừng thread hoặc restart có làm replica ngừng áp dụng log không?
- Binary log cần thiết có còn retention không?
- Có ảnh hưởng đến read traffic đang route vào replica không?

Không KILL thread hệ thống hoặc replication chỉ vì thời gian chạy dài. Xác định topology và dùng runbook quản trị replication/cluster tương ứng.

## 5. KILL QUERY: dừng câu lệnh hiện tại

### 5.1. Cú pháp và hành vi

Cú pháp:

~~~sql
KILL QUERY 12345;
~~~

12345 là processlist ID của connection mục tiêu.

KILL QUERY yêu cầu MySQL dừng câu lệnh hiện đang chạy trên session đó. Connection vẫn tồn tại để client có thể gửi câu lệnh khác. Đây là lựa chọn phù hợp khi một statement cụ thể cần dừng nhưng session cần được giữ lại.

Tuy nhiên, không được hiểu rằng mọi tác động của session đều biến mất:

- Câu lệnh bị ngắt có thể cần rollback phần công việc của chính statement.
- Nếu session đang ở explicit transaction, transaction có thể vẫn mở.
- Lock được giữ bởi các câu lệnh trước đó trong transaction có thể tiếp tục tồn tại.
- Ứng dụng cần xử lý lỗi statement và chủ động rollback hoặc kết thúc transaction.
- MySQL có thể cần thời gian để thread nhận tín hiệu dừng tại điểm kiểm tra phù hợp.

KILL QUERY không bảo đảm statement dừng tức thì trong mọi trạng thái. Một số thao tác cần thời gian để kết thúc an toàn hoặc hoàn tất cleanup.

### 5.2. Khi nào nên cân nhắc KILL QUERY?

- Một truy vấn báo cáo hoặc ad hoc đang chạy quá lâu và có thể dừng riêng statement.
- Một câu SELECT đang gây tải CPU/I/O lớn, không cần đóng toàn bộ session.
- Một DDL đang chờ metadata lock và chính DDL đó tạo hàng đợi request.
- Một statement bị chạy nhầm, trong khi session cần được giữ để ứng dụng xử lý lỗi hoặc gửi lệnh rollback.

Trước khi chạy, xác minh processlist ID, SQL, user, host, transaction và owner. Nếu query là một phần của transaction ghi quan trọng, liên hệ owner hoặc theo runbook để xác định cách xử lý phần transaction còn lại.

### 5.3. Kiểm tra sau KILL QUERY

~~~sql
SHOW FULL PROCESSLIST;
~~~

Kiểm tra:

- Câu SQL mục tiêu đã biến mất hay chưa.
- Connection còn tồn tại hay đã kết thúc.
- Transaction có còn trong information_schema.innodb_trx không.
- Các session chờ lock đã tiếp tục chưa.
- Ứng dụng đã rollback hoặc xử lý lỗi đúng chưa.

Nếu session còn transaction mở, cần xử lý transaction theo owner hoặc quy trình nghiệp vụ. Không cho rằng lock đã được giải phóng chỉ vì câu query không còn trong process list.

## 6. KILL CONNECTION: ngắt toàn bộ session

### 6.1. Cú pháp và hành vi

Cú pháp:

~~~sql
KILL CONNECTION 12345;
~~~

Có thể viết ngắn:

~~~sql
KILL 12345;
~~~

Nếu không chỉ định loại, KILL mặc định tương đương KILL CONNECTION.

Lệnh này yêu cầu MySQL chấm dứt session. Khi session kết thúc, transaction InnoDB chưa commit sẽ bị rollback. Việc rollback có thể cần thời gian đáng kể nếu transaction đã sửa nhiều hàng hoặc thay đổi nhiều index.

Các tác động cần tính đến:

- Connection vật lý bị đóng; ứng dụng nhận lỗi kết nối hoặc lỗi thực thi.
- Transaction chưa commit bị rollback.
- Lock chỉ được giải phóng khi quá trình kết thúc/rollback giải phóng chúng; không mặc định mọi lock biến mất ngay khi lệnh KILL trả về.
- Connection pool có thể tạo connection thay thế.
- Ứng dụng có thể retry, vì vậy cần đánh giá khả năng ghi trùng.
- Session có thể đang chạy tác vụ backup, migration hoặc công việc quản trị quan trọng.

### 6.2. Khi nào nên cân nhắc KILL CONNECTION?

- Session bị bỏ quên đang giữ transaction và lock lâu, owner không thể kết thúc transaction.
- Connection bị treo hoặc không còn được ứng dụng quản lý, sau khi xác minh không có công việc quan trọng cần giữ.
- Cần chấm dứt toàn bộ session để giải phóng tài nguyên và đã đánh giá tác động đến transaction.
- Một session có hành vi bất thường và cần bị cô lập theo quy trình ứng phó.

Nếu mục tiêu chỉ là dừng một SELECT nhưng giữ session để tiếp tục, KILL QUERY thường có phạm vi hẹp hơn. Nếu session đang giữ transaction gây blocker, KILL CONNECTION có thể cần thiết nhưng phải tính đến rollback.

### 6.3. Theo dõi rollback

Sau KILL CONNECTION, kiểm tra process list và transaction:

~~~sql
SHOW FULL PROCESSLIST;

SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Tìm trạng thái rollback nếu xuất hiện trong process list hoặc thông tin InnoDB. Theo dõi CPU, I/O, lock wait và thời gian rollback. Transaction lớn có thể tiếp tục tiêu tốn tài nguyên sau khi session đã bị yêu cầu đóng.

Không liên tục KILL cùng một ID đã biến mất hoặc ID mới mà chưa xác minh. Có thể session cũ đã kết thúc và ID được tái sử dụng.

## 7. Restart MySQL: tác động toàn máy chủ

### 7.1. Restart rộng hơn KILL một session

Restart tác động đến tất cả connection và hoạt động trên instance:

- Mọi client đang kết nối bị ngắt.
- Query đang chạy bị dừng.
- Transaction chưa commit cần rollback hoặc được xử lý trong quá trình shutdown/recovery.
- Connection pool phải tạo lại connection.
- Replica có thể mất kết nối và cần bắt kịp sau khi server trở lại.
- Backup, migration, event và job nền có thể bị gián đoạn.
- Ứng dụng có thể tạo connection storm khi nhiều instance cùng reconnect.
- Nếu instance là primary hoặc thành viên cluster, topology HA có thể chuyển vai trò hoặc giảm quorum.

Restart có thể cần thiết khi server process không phản hồi, cấu hình yêu cầu khởi động lại, plugin/component bị kẹt hoặc runbook phục hồi yêu cầu. Restart không tự sửa query thiếu index, transaction dài, lock contention hoặc ứng dụng retry lỗi.

### 7.2. Kiểm tra trước restart

**Vai trò và topology**

- Xác nhận đúng instance, hostname, port và môi trường.
- Xác định node là primary, replica, standalone hay thành viên Group Replication/InnoDB Cluster.
- Kiểm tra failover tự động, quorum, router và node dự phòng.
- Xác nhận primary cũ sẽ không tiếp tục nhận ghi khi topology chuyển vai trò.

**Giao dịch và workload**

- Thu thập process list, transaction, lock wait và query đang chạy.
- Xác định backup, restore, migration, DDL hoặc batch job đang hoạt động.
- Dừng nhận workload mới hoặc chuyển ứng dụng sang maintenance nếu runbook yêu cầu.
- Drain request và để transaction ngắn hoàn tất nếu có thể.
- Xác định những giao dịch có thể bị mất hoặc cần đối soát.

**Khả năng phục hồi**

- Kiểm tra backup gần nhất và bằng chứng restore.
- Kiểm tra binary log/GTID và retention nếu cần PITR hoặc tái đồng bộ.
- Kiểm tra dung lượng disk, log và filesystem.
- Đọc error log để xác định restart có thể xử lý nguyên nhân hay làm sự cố nặng hơn.
- Ước lượng thời gian InnoDB recovery dựa trên dữ liệu và lần diễn tập gần nhất.

**Ứng dụng và kết nối**

- Kiểm tra timeout và chính sách reconnect của HikariCP/JDBC.
- Xác định retry có idempotent không.
- Chuẩn bị kiểm tra health/readiness và mở traffic theo từng bước.
- Bảo đảm connection pool không dồn tất cả retry vào cùng một thời điểm.

### 7.3. Restart có kiểm soát

Quy trình cụ thể phụ thuộc hệ điều hành, dịch vụ managed và topology. Với MySQL tự quản lý, shutdown có kiểm soát thường dùng cơ chế quản lý dịch vụ hoặc mysqladmin shutdown, sau đó khởi động lại bằng service manager theo đúng tên service của môi trường.

Một trình tự vận hành tổng quát:

1. Thông báo cửa sổ bảo trì theo quy trình nội bộ và ghi nhận người chịu trách nhiệm.
2. Chuyển ứng dụng sang chế độ bảo trì hoặc ngừng ghi mới.
3. Drain connection và kiểm tra transaction còn mở.
4. Xác nhận replica/HA sẵn sàng nếu có chuyển vai trò.
5. Thực hiện graceful shutdown theo runbook.
6. Khởi động MySQL và theo dõi error log đến khi recovery hoàn tất.
7. Kiểm tra trạng thái server, dữ liệu, replication và quyền.
8. Kiểm thử ứng dụng bằng traffic giới hạn.
9. Mở traffic dần và theo dõi lỗi, latency, connection count.

Không dùng lệnh restart trực tiếp trên node production nếu chưa xác định đúng node và ảnh hưởng topology. Với MySQL managed service, thao tác restart có thể được điều phối qua control plane của nhà cung cấp; dùng runbook và cơ chế failover của dịch vụ.

### 7.4. Khi nào restart có thể làm tình hình xấu hơn?

- Disk đầy: server có thể không khởi động hoặc không ghi được log cần thiết.
- Data corruption hoặc lỗi tablespace: restart không sửa dữ liệu hỏng và có thể làm việc điều tra khó hơn.
- Transaction rollback lớn: sau restart, crash recovery có thể kéo dài.
- Primary đang có replica không khỏe: restart có thể làm mất tính sẵn sàng mà không có node thay thế.
- Ứng dụng retry không kiểm soát: khi server lên lại, hàng loạt request có thể tạo tải đột biến.
- Sự cố do query/job tự khởi chạy: restart xong, workload lỗi có thể chạy lại và tái tạo sự cố.

Khi nghi ngờ corruption, mất dữ liệu hoặc lỗi storage, lưu log và thu thập bằng chứng trước khi restart; thực hiện quy trình ứng phó sự cố dữ liệu thay vì thử restart nhiều lần.

## 8. So sánh các lựa chọn

| Hành động | Phạm vi | Transaction | Connection | Rủi ro chính |
|---|---|---|---|---|
| Chờ query hoàn tất | Một statement | Có thể commit bình thường | Giữ nguyên | Sự cố tiếp tục trong lúc chờ |
| KILL QUERY | Statement hiện tại | Statement bị ngắt; explicit transaction có thể còn mở | Giữ session | Lock từ transaction trước đó có thể còn |
| KILL CONNECTION | Toàn session | Transaction chưa commit bị rollback | Đóng session | Rollback dài, ứng dụng retry, mất trạng thái session |
| Restart MySQL | Toàn instance | Query bị ngắt; transaction chưa commit cần rollback/recovery | Tất cả connection bị ngắt | Gián đoạn dịch vụ, replication lag, reconnect storm, recovery lâu |

Chọn hành động theo mục tiêu:

- Muốn dừng một statement và giữ session: cân nhắc KILL QUERY.
- Muốn kết thúc session đang giữ transaction: cân nhắc KILL CONNECTION, sau khi tính rollback.
- Muốn phục hồi instance không hoạt động hoặc áp dụng thay đổi yêu cầu restart: dùng runbook restart và kiểm tra HA.
- Nếu chỉ là truy vấn chậm, trước hết tìm nguyên nhân trong execution plan, index, dữ liệu, lock và tải.

## 9. Ma trận tình huống thực tế

| Tình huống | Điều cần xác minh | Hướng xử lý thường cân nhắc |
|---|---|---|
| SELECT báo cáo quét toàn bảng, làm CPU tăng | Owner, SQL, execution plan, thời gian còn lại, ảnh hưởng người dùng | Yêu cầu owner dừng; nếu cần, KILL QUERY statement đó; sau đó tối ưu index/filter |
| Session Sleep lâu nhưng không có transaction | Có phải pool giữ idle connection bình thường? | Không KILL chỉ vì Sleep; xem pool sizing và timeout |
| Session Sleep nhưng transaction mở và giữ row lock | innodb_trx, tuổi transaction, hàng đã sửa, owner | Liên hệ owner; nếu không thể kết thúc và cần giải phóng lock, đánh giá KILL CONNECTION cùng rollback |
| Nhiều query chờ một transaction blocker | Waiting/blocking graph, số session bị ảnh hưởng, rollback cost | Xác định blocker; dừng upstream job hoặc kết thúc blocker theo runbook |
| ALTER TABLE đang chờ metadata lock | DDL có tạo hàng đợi không, transaction nào giữ metadata lock | Có thể dừng DDL đang chờ trước, rồi xử lý blocker trong cửa sổ phù hợp |
| Replica applier bị lỗi | Channel, lỗi SQL, GTID, tác động dữ liệu | Dùng runbook replication; không KILL thread tùy tiện |
| MySQL không phản hồi và health check thất bại | Error log, CPU, disk, network, HA và trạng thái node | Cân nhắc failover/restart theo runbook; giữ bằng chứng trước can thiệp |
| Server báo disk full | Filesystem, binlog, tmpdir, data volume | Giải phóng hoặc mở rộng dung lượng theo quy trình; restart không giải quyết dung lượng |
| Connection count tăng nhanh sau restart | Pool reconnect, retry, max_connections, readiness | Giới hạn rollout/reconnect, kiểm tra pool và mở traffic dần |

Các hướng xử lý là điểm bắt đầu điều tra, không phải lệnh tự động. Cần xác minh target và hậu điều kiện trước khi thực hiện.

## 10. Quy trình quyết định và thực hiện an toàn

### 10.1. Trước hành động

- [ ] Xác nhận môi trường, hostname, port và role của instance.
- [ ] Lưu SHOW FULL PROCESSLIST.
- [ ] Ghi nhận processlist ID, user, host, database và SQL mục tiêu.
- [ ] Đối chiếu performance_schema.threads nếu lấy thông tin từ Performance Schema.
- [ ] Kiểm tra information_schema.innodb_trx.
- [ ] Kiểm tra lock wait và metadata lock nếu liên quan.
- [ ] Xác định owner và luồng nghiệp vụ.
- [ ] Ước lượng số session bị ảnh hưởng và transaction rollback.
- [ ] Kiểm tra replication, backup, migration và HA.
- [ ] Chọn hành động có phạm vi nhỏ nhất đáp ứng mục tiêu.

### 10.2. Khi thực hiện

1. Xác minh lại processlist ID ngay trước khi KILL.
2. Kiểm tra user/host/SQL vẫn đúng target.
3. Ghi lại người thực hiện, thời điểm và lý do.
4. Chạy đúng loại lệnh: KILL QUERY hoặc KILL CONNECTION.
5. Nếu restart, dùng đúng runbook cho loại topology và service.
6. Không lặp lệnh KILL hoặc restart liên tục khi chưa biết trạng thái hành động trước.

Ví dụ, sau khi xác minh session ID 12345 đang chạy truy vấn ad hoc cần dừng:

~~~sql
KILL QUERY 12345;
~~~

Nếu đã xác định session 12345 giữ transaction gây blocker, owner không thể kết thúc và rollback được chấp nhận:

~~~sql
KILL CONNECTION 12345;
~~~

Hai lệnh trên chỉ là ví dụ cú pháp. Không sao chép ID minh họa vào production; luôn lấy ID mới từ process list và xác minh lại.

### 10.3. Sau hành động

**Sau KILL QUERY**

- Xác nhận statement đã dừng.
- Kiểm tra session còn sống hay không.
- Kiểm tra transaction có còn mở và lock có còn được giữ không.
- Xác nhận ứng dụng đã rollback hoặc xử lý lỗi đúng cách.
- Theo dõi các session trước đó đang chờ lock.

**Sau KILL CONNECTION**

- Xác nhận session đã kết thúc.
- Theo dõi rollback đến khi hoàn tất và lock được giải phóng.
- Kiểm tra ứng dụng/pool tạo connection mới.
- Đối soát nghiệp vụ nếu kết quả commit không xác định.
- Theo dõi lỗi retry, duplicate key và connection count.

**Sau restart**

- Xác nhận MySQL khởi động và hoàn tất recovery.
- Kiểm tra error log, version, uptime và trạng thái read_only/super_read_only.
- Kiểm tra database, tablespace và truy vấn trọng yếu.
- Kiểm tra GTID, replication channel, lag và trạng thái HA.
- Kiểm tra ứng dụng reconnect, connection pool và health check.
- Mở traffic theo từng bước và theo dõi latency, error rate, CPU, I/O.

## 11. Phân quyền và audit

### 11.1. Quyền xem và dừng session

Người dùng chỉ xem được một phần process list nếu thiếu quyền PROCESS; thông tin của các session khác có thể bị giới hạn. Việc dừng thread của người dùng khác cần quyền quản trị kết nối phù hợp, thường là CONNECTION_ADMIN trong MySQL 8.0/8.4; SUPER là quyền cũ đã bị phân tách và không nên cấp rộng chỉ để xử lý sự cố.

Nếu thread mục tiêu có đặc quyền SYSTEM_USER, người thực hiện cũng cần quyền SYSTEM_USER để dừng thread đó. Tài khoản có thể dừng session của chính nó theo quy tắc MySQL, nhưng việc thao tác session hệ thống cần quyền riêng.

Kiểm tra quyền:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Cấp quyền cần theo nguyên tắc tối thiểu và chính sách DBA của tổ chức. Không cấp SUPER hoặc quyền rộng cho tài khoản ứng dụng để tiện KILL.

### 11.2. Ghi nhận hành động

Audit log nên ghi:

- Người thực hiện và ticket/incident liên quan.
- Host, port, role và môi trường MySQL.
- Processlist ID, user, host và câu SQL (đã xử lý dữ liệu nhạy cảm nếu cần).
- Trạng thái transaction, lock và replica trước hành động.
- Loại hành động và thời điểm.
- Lý do chọn KILL QUERY, KILL CONNECTION hoặc restart.
- Trạng thái rollback/recovery và xác minh sau hành động.
- Tác động nghiệp vụ và hành động khắc phục tiếp theo.

Không đưa mật khẩu, token hoặc dữ liệu cá nhân vào log incident. Giữ lại bằng chứng đủ để giải thích quyết định và cải thiện runbook.

## 12. Tự kiểm tra

**Tình huống 1:** Một session có Command=Sleep trong 25 phút. Có nên KILL ngay không?

**Gợi ý:** Chưa. Kiểm tra session có transaction mở không, có giữ lock không, thuộc connection pool nào và có phải idle connection bình thường không. Sleep lâu tự nó chưa đủ để kết luận có vấn đề.

**Tình huống 2:** Một query bị KILL QUERY nhưng các transaction khác vẫn chờ lock. Vì sao?

**Gợi ý:** Session có thể vẫn còn explicit transaction mở; lock từ những câu lệnh trước đó vẫn được giữ. Cần kiểm tra innodb_trx và yêu cầu ứng dụng rollback hoặc kết thúc session theo quy trình.

**Tình huống 3:** KILL CONNECTION đã trả kết quả nhưng lock chưa được giải phóng ngay. Có phải lệnh không hoạt động?

**Gợi ý:** Không nhất thiết. Transaction chưa commit có thể đang rollback. Theo dõi trạng thái rollback và InnoDB cho đến khi quá trình kết thúc.

**Tình huống 4:** Một replica có Replica_IO_Running=Yes nhưng Replica_SQL_Running=No. Có nên KILL thread rồi restart MySQL không?

**Gợi ý:** Không tự động. Xác định lỗi applier, GTID và dữ liệu trước. Dùng runbook replication để sửa nguyên nhân; restart có thể làm gián đoạn thêm nhưng không giải quyết lỗi dữ liệu.

**Tình huống 5:** Sau khi restart primary, một số request ghi được retry và tạo đơn trùng. Vì sao?

**Gợi ý:** Client có thể mất kết nối sau khi server đã commit nhưng trước khi nhận phản hồi. Retry không idempotent có thể tạo bản ghi trùng. Cần idempotency key hoặc bước xác minh trạng thái nghiệp vụ.

**Tình huống 6:** MySQL báo disk full và không phản hồi. Restart có phải bước đầu tiên không?

**Gợi ý:** Không. Kiểm tra filesystem, data, binary log và tmpdir; bảo toàn log và mở rộng/giải phóng dung lượng theo runbook. Restart khi disk vẫn đầy có thể khiến server không khởi động lại được.

## 13. Điểm cần ghi nhớ

- Xác minh đúng processlist ID, user, host, SQL và owner trước mọi lệnh KILL.
- KILL QUERY dừng statement hiện tại nhưng giữ connection; explicit transaction có thể còn mở và tiếp tục giữ lock.
- KILL CONNECTION đóng session và rollback transaction chưa commit; rollback có thể kéo dài.
- Phân biệt blocker với victim trước khi xử lý lock wait.
- Session Sleep có thể bình thường hoặc đang giữ transaction; cần kiểm tra innodb_trx.
- DDL có thể giữ metadata lock và tạo hàng đợi; xác định cả DDL đang chờ lẫn transaction giữ lock.
- Restart ảnh hưởng tất cả client, transaction, replication, job và connection pool trên instance.
- Không restart để chữa query chậm, thiếu index, disk full hoặc corruption nếu chưa đánh giá nguyên nhân và runbook phục hồi.
- Kết quả COMMIT có thể không xác định sau lỗi mạng; retry ghi cần idempotency hoặc xác minh trạng thái.
- Thu thập bằng chứng trước hành động, theo dõi rollback/recovery và xác minh ứng dụng sau hành động.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: KILL Statement](https://dev.mysql.com/doc/refman/8.4/en/kill.html) — hành vi KILL QUERY và KILL CONNECTION.
- [MySQL 8.4 Reference Manual: SHOW PROCESSLIST](https://dev.mysql.com/doc/refman/8.4/en/show-processlist.html) — xem session và câu lệnh đang chạy.
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html) — transaction, commit và rollback.
- [MySQL 8.4 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html) — cơ chế lock của InnoDB.
- [MySQL 8.4 Reference Manual: Performance Schema data_lock_waits](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-lock-waits-table.html) — quan hệ transaction đang chờ và transaction đang chặn.
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html) — metadata lock và tác động của DDL.
- [MySQL 8.4 Reference Manual: Server Shutdown Process](https://dev.mysql.com/doc/refman/8.4/en/server-shutdown.html) — các giai đoạn shutdown MySQL.
- [MySQL 8.4 Reference Manual: Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html) — PROCESS, CONNECTION_ADMIN và SYSTEM_USER.
